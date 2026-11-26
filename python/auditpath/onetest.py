"""Part 1 of the audit path (research/audit_path/PREREG-AP.md): the one test on Kalshi's one-minute candles, run on the
lane's own paper entries (part A). The rules are the ones written in that file before any read; nothing here is tuned.

Run (on a runner that can reach Kalshi's public API; the trip files come from private Drive and are never printed):

    cd python && python3 -m auditpath.onetest trips --work <dir holding days/trips-*.jsonl> --cache <dir> \
        --from 2026-11-12 --out onetest-a.json [--no-fetch]

Output: lines "AUDITPATH onetest <json>", aggregates only (counts, rates, cents, dollars an hour; no ticker, no per-trip row,
no time of a single trade), and the full aggregate JSON at --out. --no-fetch reads only what the cache folder holds.

The core is pure (no I/O) so that part B can reuse it with another candle source and a calls table in place of trips:

    book  = index(norm_api_candles(rows))          # Kalshi API candles, as lossreview.paths.market_and_candles returns them
    book  = index(norm_hist_candles(market['candles']))   # the Drive history files (ts = candle END in milliseconds)
    entry = {'id': contract id, 'coin': 'BTC', 'kind': '15m' | 'hourly', 'close_ts': epoch s, 'side': 'yes' | 'no', 't0': epoch s}
    bundle = score_entry(entry, book, result)      # result 'yes' | 'no' | None; book None or {} means "no candles"
    out = analyse([bundle, ...], week_fn=..., hours=days * 24)

Both normalizers give one form per minute, in YES terms: (end in epoch seconds, bid low, bid close, ask high, ask close) in
dollars, sorted, one row per end. A candle's minute is (end - 60, end]; T0 is a minute boundary and the quote at T0 is the
close of the candle that ends at T0. analyse() gives the primary count (first scored entry per contract by T0) and the
secondary count (every entry), the three gaps with their slot-bootstrap errors, the verdict words, splits and the money lines.
"""
import argparse
import collections
import json
import math
import os
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from lossreview.fees import taker_fee

COINS = ('BTC', 'ETH', 'SOL', 'XRP')            # DOGE is excluded from all research
SEED = 20261125
DRAWS = 2000
BUDGET = 10.0                                   # dollars per entry: C = floor(10 / p), at least 1
BAND = (10, 90)                                 # the lane's own price band in cents (RISK_MIN_SIDE_PRICE)
MARGIN_C = 1                                    # the +1c margin of the level
DEADLINE_S = {'15m': 120, 'hourly': 360}        # the last counted candle ends this long before the close
ENTRY_WINDOW_S = {'15m': (840, 300), 'hourly': (3300, 600)}   # seconds before the close: first and last entry minute
MIN_CELL = 10                                   # a split cell under this many scored entries is counted but not rated
EPS = 1e-6

# normalized candle tuple fields
END, BID_LOW, BID_CLOSE, ASK_HIGH, ASK_CLOSE = range(5)


# ---------------------------------------------------------------- fee, level, contracts

def fee_c(count, price_c):
    """Taker fee in whole cents for `count` contracts at a whole-cent side price (the shared lossreview rule)."""
    return int(round(taker_fee(count, price_c / 100.0) * 100))


def contracts(price_c):
    """C = floor($10 / p), at least 1."""
    return max(1, int(math.floor(BUDGET * 100 / price_c + 1e-9)))


def level_c(count, price_c):
    """The lowest whole-cent price b (at most 99) with C*b - fee(C, b) >= C*p + fee(C, p) + 1c*C, or None."""
    need = count * price_c + fee_c(count, price_c) + MARGIN_C * count
    for b in range(1, 100):
        if count * b - fee_c(count, b) >= need:
            return b
    return None


# ---------------------------------------------------------------- candle normalizers

def _num(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _api_px(d, key):
    """An API candle price in dollars: the *_dollars string when present, else cents / 100."""
    if not isinstance(d, dict):
        return None
    v = _num(d.get(key + '_dollars'))
    if v is not None:
        return v
    v = _num(d.get(key))
    return None if v is None else v / 100.0


def norm_api_candles(rows):
    """Kalshi API candles (end_period_ts, yes_bid / yes_ask OHLC in cents and *_dollars) -> the common per-minute form."""
    out = {}
    for c in rows or []:
        e = _num(c.get('end_period_ts'))
        if e is None:
            continue
        yb, ya = c.get('yes_bid'), c.get('yes_ask')
        out[int(round(e))] = (int(round(e)), _api_px(yb, 'low'), _api_px(yb, 'close'), _api_px(ya, 'high'), _api_px(ya, 'close'))
    return [out[k] for k in sorted(out)]


_HIST_KEYS = ('bidO', 'bidH', 'bidL', 'bidC', 'askO', 'askH', 'askL', 'askC', 'last')


def _hist_scale(candles):
    """1 or 100: a market whose every positive price is under a cent had its dollars divided by 100 once more (the history
    repair rule of python/allpairs/data.py); the values are scaled back. A market with some tail prices among normal ones is kept."""
    vals = [c.get(k) for c in candles for k in _HIST_KEYS if isinstance(c.get(k), (int, float)) and c.get(k) > 0]
    return 100.0 if vals and max(vals) < 0.01 else 1.0


def norm_hist_candles(rows):
    """Drive history-file candles (ts = candle END in milliseconds, prices in dollars) -> the common per-minute form."""
    rows = [c for c in (rows or []) if isinstance(c, dict)]
    k = _hist_scale(rows)
    out = {}
    for c in rows:
        ts = _num(c.get('ts'))
        if ts is None:
            continue
        e = int(round(ts / 1000.0))

        def g(name):
            v = _num(c.get(name))
            return None if v is None else (v * k if v < 0.01 else v)
        out[e] = (e, g('bidL'), g('bidC'), g('askH'), g('askC'))
    return [out[x] for x in sorted(out)]


def index(candles):
    """{end: tuple} for the scorer; a dict passes through."""
    if isinstance(candles, dict):
        return candles
    return {c[END]: c for c in candles or []}


# ---------------------------------------------------------------- scoring one side at one minute boundary

def _not_scored(reason):
    return {'scored': False, 'reason': reason, 'window': None}


def side_bid_low(c, side):
    """The side's lowest bid in a normalized candle: YES = the YES bid low; NO = 1 minus the YES ask high."""
    if side == 'yes':
        return c[BID_LOW]
    return None if c[ASK_HIGH] is None else 1.0 - c[ASK_HIGH]


def side_bid_close(c, side):
    if side == 'yes':
        return c[BID_CLOSE]
    return None if c[ASK_CLOSE] is None else 1.0 - c[ASK_CLOSE]


def score_side(book, side, t0, close_ts, kind, result, price=None, count=None):
    """One side bought at the minute boundary t0 on one contract.

    Quote and price: the close of the candle that ends at t0 (two-sided: 0 < bid < ask < 1); YES costs the ask, NO costs 1 minus
    the bid; the cost must be 10c to 90c; C = floor($10 / p). With `price` (dollars, the side price) and `count` given (the
    lane's own fill) there is no quote and no band: the price and size are taken as they are.
    Window: a candle that starts at or after t0 and ends no later than the deadline (close - 120 s for a 15-minute contract,
    close - 360 s for an hourly one) whose lowest side bid is at or above the level.
    Returns a dict: scored, reason (when not scored), window (True / False / None), level_c (None when no price reaches it),
    p_c, C, minutes (to the first window candle's end), gap (a minute without a usable candle between t0 and the deadline),
    sold_c (net cents per contract sold at the side bid close one minute after t0, both fees; None without that candle) and
    held_c (net cents per contract held to settlement, entry fee only; None without the result).
    """
    if not book:
        return _not_scored('no candles')
    if price is None:
        q = book.get(t0)
        if q is None:
            return _not_scored('no candle at T0')
        bid, ask = q[BID_CLOSE], q[ASK_CLOSE]
        if bid is None or ask is None or not (0 < bid < ask < 1):
            return _not_scored('not two-sided')
        pc = int(round((ask if side == 'yes' else 1.0 - bid) * 100))
        if pc < BAND[0] or pc > BAND[1]:
            return _not_scored('price out of band')
        n = contracts(pc)
    else:
        pc = int(round(price * 100))
        n = int(count) if count else 0
        if pc < 1 or pc > 99 or n < 1:
            return _not_scored('no fill price or size')
    lv = level_c(n, pc)
    dl = close_ts - DEADLINE_S[kind]
    window, first, gap = False, None, False
    e = t0 + 60
    while e <= dl:
        c = book.get(e)
        low = None if c is None else side_bid_low(c, side)
        if low is None:
            gap = True
        elif lv is not None and not window and low * 100 >= lv - EPS:
            window, first = True, (e - t0) / 60.0
        e += 60
    fin = n * pc + fee_c(n, pc)             # cents paid with the entry fee
    ex = book.get(t0 + 60)
    xb = None if ex is None else side_bid_close(ex, side)
    sold = None if xb is None else (n * xb * 100 - taker_fee(n, xb) * 100 - fin) / n
    held = None
    if result in ('yes', 'no'):
        held = (n * (100 if result == side else 0) - fin) / n
    return {'scored': True, 'reason': None, 'window': window, 'level_c': lv, 'p_c': pc, 'C': n, 'minutes': first,
            'gap': gap, 'sold_c': sold, 'held_c': held}


def entry_minutes(close_ts, kind):
    """Every minute boundary of the contract's entry window (15-minute: 840 to 300 s before close; hourly: 3300 to 600 s)."""
    a, b = ENTRY_WINDOW_S[kind]
    return [close_ts - s for s in range(a, b - 1, -60)]


def score_entry(entry, book, result):
    """The called side, the opposite side at T0, and the called side at every minute boundary of the entry window."""
    book = index(book) if book else None
    side, t0, close_ts, kind = entry['side'], entry['t0'], entry['close_ts'], entry['kind']
    opp = 'no' if side == 'yes' else 'yes'
    return {'id': entry['id'], 'coin': entry['coin'], 'kind': kind, 'close_ts': close_ts, 'side': side, 't0': t0,
            'called': score_side(book, side, t0, close_ts, kind, result),
            'opp': score_side(book, opp, t0, close_ts, kind, result),
            'mins': [score_side(book, side, m, close_ts, kind, result) for m in entry_minutes(close_ts, kind)]}


# ---------------------------------------------------------------- statistics

def _w(item):
    return None if not item['scored'] else (1.0 if item['window'] else 0.0)


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _r(x, nd=4):
    return None if x is None else round(float(x), nd)


def slot_boot(pairs, draws=DRAWS, seed=SEED):
    """(mean, standard error) of values grouped by slot: whole slots are drawn with replacement (pairs = [(slot, value)])."""
    if not pairs:
        return None, None
    by = collections.OrderedDict()
    for s, v in pairs:
        a = by.setdefault(s, [0.0, 0])
        a[0] += v
        a[1] += 1
    sums = np.array([a[0] for a in by.values()])
    cnt = np.array([a[1] for a in by.values()], dtype=float)
    mean = float(sums.sum() / cnt.sum())
    if len(by) < 2:
        return mean, None
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(by), size=(draws, len(by)))
    means = sums[idx].sum(axis=1) / cnt[idx].sum(axis=1)
    return mean, float(np.std(means, ddof=1))


def usual_sides(bundles):
    """The side called most often for each (coin, kind) in this count (a tie goes to YES)."""
    c = collections.defaultdict(collections.Counter)
    for b in bundles:
        c[(b['coin'], b['kind'])][b['side']] += 1
    return {k: ('yes' if v['yes'] >= v['no'] else 'no') for k, v in c.items()}


def _gap_stat(bundles, fn, draws, seed):
    """{n, called, control, gap, se, passes}: fn(b) -> (called window, control window) or None; the error is by slot."""
    rows = [(b['close_ts'], fn(b)) for b in bundles]
    rows = [(s, v) for s, v in rows if v is not None]
    if not rows:
        return {'n': 0, 'called': None, 'control': None, 'gap': None, 'se': None, 'above_zero': False, 'passes': False}
    g, se = slot_boot([(s, v[0] - v[1]) for s, v in rows], draws, seed)
    ok = g is not None and g > 0 and se is not None and g >= 2 * se - 1e-12
    return {'n': len(rows), 'called': _r(_mean(v[0] for _, v in rows)), 'control': _r(_mean(v[1] for _, v in rows)),
            'gap': _r(g), 'se': _r(se), 'above_zero': bool(g is not None and g > 0), 'passes': bool(ok)}


def core_stats(bundles, usual, draws=DRAWS, seed=SEED):
    """Window rates and the three gaps for a list of bundles; `usual` is the usual-side map of the whole count."""
    def rand_side(b):
        c, o = _w(b['called']), _w(b['opp'])
        return None if c is None or o is None else (c, (c + o) / 2.0)

    def rand_min(b):
        c = _w(b['called'])
        m = _mean(_w(i) for i in b['mins'])
        return None if c is None or m is None else (c, m)

    def usual_side(b):
        c = _w(b['called'])
        u = _w(b['called'] if b['side'] == usual.get((b['coin'], b['kind'])) else b['opp'])
        return None if c is None or u is None else (c, u)

    called = [b for b in bundles if b['called']['scored']]
    win = [b for b in called if b['called']['window']]
    first = [b['called']['minutes'] for b in win]
    return {'n_entries': len(bundles), 'n_called_scored': len(called),
            'called_rate': _r(_mean(_w(b['called']) for b in bundles)),
            'opposite_rate': _r(_mean(_w(b['opp']) for b in bundles)),
            'median_minutes_to_first_window': _r(statistics.median(first), 2) if first else None,
            'G_random_side': _gap_stat(bundles, rand_side, draws, seed),
            'same_side_random_minute': _gap_stat(bundles, rand_min, draws, seed),
            'usual_side': _gap_stat(bundles, usual_side, draws, seed)}


def _split_cell(bs, usual, draws, seed):
    s = core_stats(bs, usual, draws, seed)
    if s['n_called_scored'] < MIN_CELL:
        return {'n_entries': s['n_entries'], 'n_called_scored': s['n_called_scored'], 'withheld': 'under %d scored' % MIN_CELL}
    g, m = s['G_random_side'], s['same_side_random_minute']
    return {'n_entries': s['n_entries'], 'n_called_scored': s['n_called_scored'], 'called_rate': s['called_rate'],
            'G': g['gap'], 'G_se': g['se'], 'minute_gap': m['gap'], 'minute_gap_se': m['se']}


def splits(bundles, usual, key_fns, draws=DRAWS, seed=SEED):
    out = {}
    for name, fn in key_fns.items():
        groups = collections.OrderedDict()
        for b in bundles:
            groups.setdefault(str(fn(b)), []).append(b)
        out[name] = {k: _split_cell(groups[k], usual, draws, seed) for k in sorted(groups)}
    return out


def money(bundles, hours):
    """Cents per contract after fees and dollars an hour, for the called entries and each control, at both exits.
    Per entry, a control's value is the mean over its priced items; entries count equally. Dollars an hour = cents per contract
    x mean contracts per entry x entries per hour (entries with a value / hours)."""
    usual = usual_sides(bundles)

    def vals(b, key, which):
        """(cents, contracts) for the row `which` of one bundle, or None."""
        def one(it):
            return None if not it['scored'] or it[key] is None else (it[key], it['C'])
        if which == 'called':
            return one(b['called'])
        if which == 'opposite':
            return one(b['opp'])
        if which == 'usual_side':
            return one(b['called'] if b['side'] == usual.get((b['coin'], b['kind'])) else b['opp'])
        if which == 'random_side':
            a, o = one(b['called']), one(b['opp'])
            return None if a is None or o is None else ((a[0] + o[0]) / 2.0, (a[1] + o[1]) / 2.0)
        ms = [x for x in (one(i) for i in b['mins']) if x is not None]
        return None if not ms else (_mean(x[0] for x in ms), _mean(x[1] for x in ms))

    out = {}
    for which in ('called', 'random_side', 'same_side_random_minute', 'usual_side', 'opposite'):
        row = {}
        for key, name in (('sold_c', 'sold_1m'), ('held_c', 'settlement')):
            v = [x for x in (vals(b, key, which) for b in bundles) if x is not None]
            if not v:
                row[name] = {'n': 0, 'cents_per_contract': None, 'dollars_per_hour': None}
                continue
            cents, cc = _mean(x[0] for x in v), _mean(x[1] for x in v)
            row[name] = {'n': len(v), 'cents_per_contract': _r(cents, 3), 'mean_contracts': _r(cc, 2),
                         'dollars_per_hour': _r(cents / 100.0 * cc * len(v) / hours, 2) if hours else None}
        out[which] = row
    return out


def summarize(bundles, hours, key_fns, usual=None, draws=DRAWS, seed=SEED):
    """Everything reported for one count (primary or secondary)."""
    usual = usual if usual is not None else usual_sides(bundles)
    s = core_stats(bundles, usual, draws, seed)
    reasons = {}
    for label, items in (('called', [b['called'] for b in bundles]), ('opposite', [b['opp'] for b in bundles]),
                         ('random_minute_items', [i for b in bundles for i in b['mins']])):
        c = collections.Counter(i['reason'] for i in items if not i['scored'])
        reasons[label] = {'scored': sum(1 for i in items if i['scored']), 'not_scored': dict(sorted(c.items()))}
    called = [b['called'] for b in bundles if b['called']['scored']]
    opp = [b['opp'] for b in bundles if b['opp']['scored']]
    sides = collections.Counter(b['side'] for b in bundles)
    s.update({
        'not_scored': reasons,
        'share_with_missing_minute': _r(_mean(1.0 if i['gap'] else 0.0 for i in called)),
        'share_with_level': _r(_mean(1.0 if i['level_c'] is not None else 0.0 for i in called)),
        'share_by_side': {k: _r(v / len(bundles)) for k, v in sorted(sides.items())} if bundles else {},
        'opposite_median_minutes_to_first_window': _r(statistics.median([i['minutes'] for i in opp if i['window']]), 2)
        if any(i['window'] for i in opp) else None,
        'money': money(bundles, hours),
        'splits': splits(bundles, usual, key_fns, draws, seed),
    })
    return s


def primary_count(bundles):
    """One entry per contract: the first (by T0, then input order) whose called side is scored."""
    best = {}
    for i, b in enumerate(bundles):
        if not b['called']['scored']:
            continue
        cur = best.get(b['id'])
        if cur is None or b['t0'] < cur[0]['t0']:
            best[b['id']] = (b, i)
    return [x[0] for x in sorted(best.values(), key=lambda v: v[1])]


def verdict(primary, secondary):
    """The words. 'direction found' needs G >= 2 x its standard error on the primary count (and G above zero); the plain sign
    is always said too. The same-side-random-minute gap passing while G does not is timing, not direction. Primary and
    secondary counts giving different words is mixed (the call is the owner's)."""
    def one(s):
        g, m = s['G_random_side'], s['same_side_random_minute']
        if g['passes']:
            return 'direction found'
        if m['passes']:
            return 'timing, not direction'
        return 'direction not found'
    p, s = one(primary), one(secondary)
    g = primary['G_random_side']
    sign = 'above random by any amount' if g['above_zero'] else 'not above random by any amount'
    final = 'mixed' if p != s else p
    return {'verdict': final, 'primary': p, 'secondary': s, 'G_sign_primary': sign,
            'G_primary': g['gap'], 'G_se_primary': g['se'], 'G_secondary': secondary['G_random_side']['gap'],
            'G_se_secondary': secondary['G_random_side']['se']}


def week_fn_from(week2_start_ts):
    """key function: 'week1' before the given epoch second, 'week2' from it on (part A: Nov 12-18 and Nov 19 on, UTC)."""
    return lambda b: 'week1' if b['t0'] < week2_start_ts else 'week2'


def days_covered(bundles):
    return len({b['t0'] // 86400 for b in bundles})


def analyse(bundles, week_fn, hours=None, draws=DRAWS, seed=SEED):
    """Primary and secondary counts, verdict, splits and money for a list of scored bundles. hours defaults to the calendar
    days with an entry x 24."""
    if hours is None:
        hours = days_covered(bundles) * 24
    keys = {'kind': lambda b: b['kind'], 'coin': lambda b: b['coin'], 'side': lambda b: b['side'], 'week': week_fn}
    prim = primary_count(bundles)
    ps = summarize(prim, hours, keys, usual_sides(prim), draws, seed)
    ss = summarize(bundles, hours, keys, usual_sides(bundles), draws, seed)
    return {'hours': hours, 'days': hours // 24, 'contracts': len({b['id'] for b in bundles}),
            'contracts_with_a_scored_entry': len(prim),
            'contracts_without_a_scored_entry': len({b['id'] for b in bundles}) - len(prim), 'primary': ps, 'secondary': ss, 'verdict': verdict(ps, ss)}


# ---------------------------------------------------------------- part A: the lane's own trips

LIMIT_PER_S = 8.0       # about eight requests a second in total, four worker threads at most
WORKERS = 4


def iso_epoch(ts):
    import calendar
    return calendar.timegm(time.strptime(ts[:19], '%Y-%m-%dT%H:%M:%S'))


def entry_from_trip(r, market_close=None):
    """A trip row -> (entry dict, why not). Heat lane, with a ticker, a side and a time; T0 = order_t else entry_t, rounded down
    to the minute; the close from the trip's window_close_t else the market's close_time; the kind from the trip."""
    if r.get('lane') != 'heat':
        return None, 'other lane'
    side = str(r.get('side') or '').lower()
    tk = r.get('ticker')
    t = r.get('order_t') or r.get('entry_t')
    if not tk or side not in ('yes', 'no') or not t:
        return None, 'no ticker, side or time'
    kind = r.get('kind')
    if kind not in DEADLINE_S:
        return None, 'unknown kind'
    close = r.get('window_close_t') or market_close
    if not close:
        return None, 'no close time'
    coin = str(r.get('coin') or '').upper()
    if coin not in COINS:
        return None, 'coin not in the four'
    return {'id': tk, 'coin': coin, 'kind': kind, 'close_ts': int(close), 't0': int(t) // 60 * 60, 'side': side}, None


def fill_item(r, book, result, entry):
    """Part A only: the same test at the lane's own fill price and size, candles from the first minute boundary at or after the
    fill (the fill time is order_t, else entry_t)."""
    px, n = r.get('entry_fill_px'), r.get('count_filled')
    t = r.get('order_t') or r.get('entry_t')
    if not book:
        return _not_scored('no candles')
    if not px or not n or not t:
        return _not_scored('no fill price or size')
    tf = -(-int(t) // 60) * 60
    return score_side(index(book), entry['side'], tf, entry['close_ts'], entry['kind'], result, price=float(px), count=int(n))


class Limiter:
    """At most `rate` calls a second in total over all threads."""

    def __init__(self, rate):
        self.gap, self.lock, self.next = 1.0 / rate, threading.Lock(), 0.0

    def wait(self):
        with self.lock:
            now = time.monotonic()
            at = max(now, self.next)
            self.next = at + self.gap
        if at > now:
            time.sleep(at - now)


def _clean_stale(cache, ticker):
    """A cached market without a result was cached before it settled: drop it so it is fetched again."""
    p = os.path.join(cache, 'k-%s.json' % ticker)
    try:
        d = json.load(open(p))
        if (d.get('market') or {}).get('result') not in ('yes', 'no') or not d.get('candles'):
            os.remove(p)
    except (OSError, ValueError):
        pass


def fetch_markets(tickers, cache, fetch=True):
    """{ticker: (market, candles)} through lossreview.paths.market_and_candles, cached in `cache`. Returns (map, errors)."""
    from lossreview import paths
    os.makedirs(cache, exist_ok=True)
    out, errors, lock = {}, [0], threading.Lock()
    if fetch:
        lim, orig = Limiter(LIMIT_PER_S), paths.get

        def limited(url, tries=4):
            lim.wait()
            return orig(url, tries)
        paths.get = limited

    def one(tk):
        try:
            if not fetch and not os.path.exists(os.path.join(cache, 'k-%s.json' % tk)):
                return tk, ({}, [])
            if fetch:
                _clean_stale(cache, tk)
            return tk, paths.market_and_candles(tk, cache)
        except Exception:  # noqa: BLE001 - counted, the entry is then not scored
            with lock:
                errors[0] += 1
            return tk, ({}, [])
    try:
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            for tk, v in ex.map(one, sorted(tickers)):
                out[tk] = v
    finally:
        if fetch:
            paths.get = orig
    return out, errors[0] + getattr(paths, 'FETCH_ERRORS', 0)


def extras_a(pairs):
    """Part A only. pairs = [(bundle, trip row, fill item)]: the fill-price test and the lane's realized cents per contract."""
    items = [p[2] for p in pairs]
    sc = [i for i in items if i['scored']]
    win = [i for i in sc if i['window']]
    def _cnt(r):
        try:
            return float(r.get('count_filled') or 0)
        except (TypeError, ValueError):
            return 0.0
    # Counts are taken as recorded (a paper fill can hold a fraction of a contract); a trip with none is left out.
    pnl = [(float(r['pnl']), _cnt(r)) for _, r, _ in pairs if r.get('pnl') is not None and _cnt(r) > 0]
    reasons = collections.Counter(i['reason'] for i in items if not i['scored'])
    return {'entries': len(pairs), 'fill_test_scored': len(sc), 'fill_test_window_rate': _r(len(win) / len(sc)) if sc else None,
            'fill_test_median_minutes_to_first_window': _r(statistics.median([i['minutes'] for i in win]), 2) if win else None,
            'fill_test_not_scored': dict(sorted(reasons.items())),
            'realized_trips': len(pnl),
            'realized_cents_per_contract': _r(100.0 * sum(p for p, _ in pnl) / sum(n for _, n in pnl), 3) if pnl else None,
            'realized_cents_per_contract_mean_of_trips': _r(_mean(100.0 * p / n for p, n in pnl), 3) if pnl else None,
            'fidelity_flagged_kept': sum(1 for _, r, _ in pairs if r.get('fidelity_flag'))}


def run_trips(work, cache, day_from, fetch=True, log=print):
    from lossreview import daily
    days = daily.load_days(work, scoring=False)
    rows = [r for d in sorted(days) if d >= day_from for r in days[d]]
    heat = [r for r in rows if r.get('lane') == 'heat']
    # Only the four coins and known kinds are ever fetched; other rows are dropped later with their reason.
    tickers = {r['ticker'] for r in heat if r.get('ticker') and str(r.get('coin') or '').upper() in COINS
               and r.get('kind') in DEADLINE_S}
    mk, errs = fetch_markets(tickers, cache, fetch)
    pairs, dropped = [], collections.Counter()
    for r in heat:
        mc = None
        if r.get('ticker') in mk and mk[r['ticker']][0].get('close_time'):
            try:
                mc = iso_epoch(mk[r['ticker']][0]['close_time'])
            except (ValueError, TypeError):
                mc = None
        e, why = entry_from_trip(r, mc)
        if e is None:
            dropped[why] += 1
            continue
        market, candles = mk.get(e['id'], ({}, []))
        book = index(norm_api_candles(candles)) if candles else None
        res = market.get('result') if market.get('result') in ('yes', 'no') else None
        pairs.append((score_entry(e, book, res), r, fill_item(r, book, res, e)))
    bundles = [p[0] for p in pairs]
    week2 = iso_epoch('2026-11-19T00:00:00')
    out = analyse(bundles, week_fn_from(week2))
    prim_ids = {id(b) for b in primary_count(bundles)}
    out['part'] = 'A'
    out['from'] = day_from
    out['days_on_drive'] = len([d for d in days if d >= day_from])
    out['rows'] = {'rows_since_from': len(rows), 'heat_rows': len(heat), 'entries': len(bundles), 'dropped': dict(sorted(dropped.items())),
                   'tickers': len(tickers), 'tickers_without_candles': sum(1 for t in tickers if not mk.get(t, ({}, []))[1]),
                   'fetch_errors': errs}
    out['extras_a'] = {'secondary': extras_a(pairs),
                       'primary': extras_a([p for p in pairs if id(p[0]) in prim_ids])}
    return out


# ---------------------------------------------------------------- output

def emit(name, obj, limit=2800, out=sys.stdout):
    """One line 'AUDITPATH onetest <json>' per block; a block over the limit is split by its keys into several lines."""
    s = json.dumps({'block': name, **obj} if isinstance(obj, dict) else {'block': name, 'value': obj}, separators=(',', ':'))
    if len(s) <= limit or not isinstance(obj, dict) or len(obj) < 2:
        print('AUDITPATH onetest ' + s, file=out)
        return
    keys = list(obj)
    half = len(keys) // 2
    emit(name + '.1', {k: obj[k] for k in keys[:half]}, limit, out)
    emit(name + '.2', {k: obj[k] for k in keys[half:]}, limit, out)


LEGEND = {
    'passes': 'gap >= 2 x its standard error AND gap above zero (the zero guard is added; the plain sign is also said)',
    'above_zero': 'gap above zero by any amount',
    'G_random_side': 'called side minus the opposite side at T0 (random side), the deciding gap',
    'same_side_random_minute': 'called entry minus the same side at every minute boundary of the entry window',
    'usual_side': 'called entry minus the side called most often for that coin and kind in this count',
    'sold_1m': 'cents per contract sold at the side bid close one minute after T0, both fees',
    'settlement': 'cents per contract held to settlement, entry fee only',
    'cells': 'split cells under 10 scored entries are counted but not rated',
    'fill_time': 'the fill test uses order_t (at or before the real fill) as the fill time, a proxy',
    'price': 'prices are rounded to whole cents with round() (half to even) for the band, C, L and the entry fee',
    'primary_not_scored': 'the primary count keeps only entries whose called side is scored, so its not_scored block is empty',
}


def print_blocks(res, out=sys.stdout):
    emit('head', {k: res[k] for k in ('part', 'from', 'days', 'hours', 'days_on_drive', 'contracts', 'contracts_with_a_scored_entry', 'contracts_without_a_scored_entry', 'rows') if k in res}, out=out)
    emit('legend', LEGEND, out=out)
    emit('verdict', res['verdict'], out=out)
    for c in ('primary', 'secondary'):
        s = res[c]
        emit(c + '.rates', {k: v for k, v in s.items() if k not in ('money', 'splits', 'not_scored')}, out=out)
        emit(c + '.not_scored', s['not_scored'], out=out)
        emit(c + '.money', s['money'], out=out)
        for name, v in s['splits'].items():
            emit('%s.split.%s' % (c, name), v, out=out)
    if 'extras_a' in res:
        emit('extras_a', res['extras_a'], out=out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    t = sub.add_parser('trips', help='part A: the lane\'s own paper entries')
    t.add_argument('--work', required=True, help='folder holding days/trips-*.jsonl')
    t.add_argument('--cache', required=True, help='candle cache folder')
    t.add_argument('--from', dest='day_from', default='2026-11-12')
    t.add_argument('--out', required=True)
    t.add_argument('--no-fetch', action='store_true', help='read only what the cache holds')
    a = ap.parse_args(argv)
    res = run_trips(a.work, a.cache, a.day_from, fetch=not a.no_fetch)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, 'w', encoding='utf-8') as fh:
        json.dump(res, fh, indent=1)
    print_blocks(res)
    print('fetch errors: %d' % res['rows']['fetch_errors'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
