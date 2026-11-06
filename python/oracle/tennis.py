"""Tennis part builder: Kalshi tennis match history (KXATPMATCH / KXWTAMATCH) -> parts/tennis-<TOUR>/.

Implements SPEC.md 2c and the OR-H1 prereg sections "Data" (tennis, start era only), "Decision times, entries, labels,
exits" (tennis), "Features" (tennis + context) and "Mining" (the tennis matched-baseline strata).

    cd python && python3 -m oracle.tennis --tar <KXATPMATCH.tar.gz> --tour ATP --out parts [--code-sha <sha>]
    cd python && python3 -m oracle.tennis --hist <dir holding KXATPMATCH/> --tour ATP --out parts      (an extracted tarball)

Input: the Drive tarball raw/tennis-history/kalshi/<SERIES>.tar.gz (tennis-ta-data.yml: `tar -C data/tennis/kalshi
<SERIES>`), i.e. <SERIES>/<UTC close day>.jsonl (one KalshiHistMarket per line, research/history/kalshiHistory.ts: candles
{ts = candle END, bidO/H/L/C, askO/H/L/C, last, volume, oi} in dollars, startTime = occurrence_datetime) and
<SERIES>/trades/<UTC close day>.jsonl ({ticker, trades: [[ts, yesPx, count, takerSide 1 = YES / 0 = NO]]}). The tarball is
streamed: only day files dated 2026-04-27 .. 2026-11-04 are extracted and parsed (a start-era market closes after
2026-04-27 05:00); every member dated 2026-11-05 or later is skipped unread.

Markets: start era only (startTime >= 2026-04-27T05:00Z, closeTime < 2026-11-05T00:00Z, start < close), settled yes/no;
markets without a start time are skipped (and counted). The two markets of a match share Kalshi's event ticker (else the
ticker less its last '-' part, as tennisTaSim.ts eventOf); group = event index.

Quotes: per market a 1-minute grid t_i = t_0 + i min (t_0 = the END of the market's second stored candle: the first one
is dropped as historyReplay.ts v8 does, its quote can be the listing's), every t_i < closeTime. The YES bid/ask at t_i is
the close of the candle ending at t_i if it is a two-sided book (0 < bid < ask < 1, allpairs.data _book; legacy-cent
markets repaired with allpairs.data.repair_legacy_cents). A minute without a candle carries the last quote for at most
5 minutes (stale.npy = minutes since its candle); a candle that is not a two-sided book, or a 6th empty minute, is NA.

Decisions: every candle minute (a grid minute whose own candle is a two-sided book, stale == 0: a carried quote is never
entered on) from 30 minutes before the start (and at least one minute after the market opened) to the close, with YES
spread <= 0.03 (TENNIS_MAX_SPREAD). Carried quotes only value exits. Sides Y (buy YES at the ask, sell at the YES
bid) and N (buy NO at 1 - YES bid, sell at 1 - YES ask); a side is tradable when its ask is in [0.05, 0.95]. Taker both
legs, C = min(floor(size / ask), 100) (H_LOT_CAP), fee = allpairs.fees.taker_fee (the exact bot/fees.ts port) with the
tennis taker multiplier 1 (bot/kalshi/feeScheduleSnapshot.json: KXATPMATCH / KXWTAMATCH taker 1), no settlement fee.

Primary exit, horizon h in {15, 60} minutes, per side at the entry's own C (simulate()):
  1. take-profit: sell at the bid at the first grid minute j in (k, k + h] (before the close) whose net is >= $5;
  2. else, when the market is still open at minute k + h: sell at its bid (a time exit); if that minute has no book, at
     the first later minute with one; with no book until the close the position settles;
  3. else (the market closes inside the horizon): the position settles.
     DEVIATION from the OR-H1 tennis exit text ("ride to settlement only if in profit at the last candle, else sell at
     that bid"), review of Nov 6: a tennis market closes when the match ends, so its last candle is known to be the last
     only afterwards, and a sale there used information from after the decision (mostly the residual bid of a loser
     whose match was over). A causal position simply holds, and the close settles it. The rulebook hook runs this exit.
hit = the take-profit filled, or the settlement of (3) netted >= $5. best = max(every bid sale in (k, k + h], the
settlement when the market closes inside the horizon, the realized trade). hold = minutes to the exit (settlement:
ceil(minutes to the close)). tradeLat = the same trade entered at minute k + 1 (its ask and C; horizon from k + 1);
tradeCost = entry price + 1c (C and fee at it). trade2 / hit2 at $20.
Leakage guard: a row decided before DEV_END whose exit (or best window) would read a minute or a settlement after DEV_END
is not ok (that variant NaN). close.npy gives each row's market close (the prereg puts a Kalshi decision in a split only
if its contract's close is inside it too; common.split_of looks at t + h only).

Features at decision minute k (int8; strictly from minutes <= k and trades stamped < t_k):
  TA-Lib (python `talib`) on the side's own 1-minute mid in cents (YES mid; NO mid = 100 - YES mid), run separately on
  every run of consecutive non-NA minutes, with high = low = close = mid; warm-up NaN -> 0: RSI14 (>70 +1 / <30 -1),
  STOCH 14/3/3 slowk (>80 / <20), WILLR14 (>-20 / <-80), CCI14 (>100 / <-100), Bollinger %B 20/2 (>1 / <0), MACD
  12/26/9 histogram sign, LINEARREG_SLOPE14 sign, MOM10 sign, ADX14 > 25 with the +DI / -DI direction. RSI, STOCH and
  WILLR read 0 when their window is flat (TA-Lib returns 0 / 50 there, an artifact, not a reading).
  Contract: the side's mid change over 1/3/5/15 minutes (+-1c), the other market's same-side mid change over 5 minutes
  (+-1c), the 5-minute taker flow imbalance (yes - no contracts) / total, side-relative (5 buckets, NA without trades),
  the 5-minute trade count (5 buckets: none + quartiles of dev rows), spread (1/2/3c), the side's ask bucket (0.1 wide),
  the production underdog (0.08-0.25) / favourite (0.75-0.92) band of the side's mid, the side's 60-minute mid change
  (prereg context "60-minute trend", 5 buckets), time from the start (pre 30-0, 0-30, 30-60, 60-120, 120+ min), UTC hour
  / 4 and weekend (prereg context). Side-relative columns are named <feature>@Y / <feature>@N and listed in
  meta.side_features (the PP convention); the others apply to both sides.
rv.npy = -1 (no RV regime for tennis; the HO-1 split is by tour). Strata per side: side ask bucket (10) x phase (pre /
live first 60 min / live later) = 30; -1 = side not tradable. NEVER DOGE.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import tarfile
from dataclasses import dataclass

import numpy as np

try:
    import talib
except ImportError as e:  # pragma: no cover - the study refuses to run without the real TA-Lib
    raise ImportError('oracle.tennis needs python TA-Lib (import talib)') from e

from allpairs.data import _book, _f, repair_legacy_cents
from allpairs.fees import contracts_for_stake, taker_fee

from .common import DAY, DEV_END, HOLD_TO, HORIZONS, MAX_CONTRACTS, MIN, SIDES, SIZE, SIZE2, STEP_MIN, TARGET_USD, dev_rows, key, \
    ms, write_part

CT = 'tennis'
SERIES = {'ATP': 'KXATPMATCH', 'WTA': 'KXWTAMATCH'}
ERA_FROM = ms('2026-04-27T05:00')        # START_ERA_FROM (research/tennisTaSweep.ts, branch 7817be)
FILE_FROM = '2026-04-27'                  # earliest close day a start-era market can have
FILE_TO = '2026-11-05'                    # first day file never read (HOLD_TO's day)
PRE_MIN = 30                              # decisions from 30 minutes before the start (TENNIS_PRE_START_MIN)
MAX_STALE = 5                             # a carried quote is at most 5 minutes old
MAX_SPREAD = 0.03                         # TENNIS_MAX_SPREAD
PRICE_BAND = (0.05, 0.95)                 # side ask
DOG_BAND = (0.08, 0.25)                   # TENNIS_UNDERDOG_MIN / MAX
FAV_BAND = (0.75, 0.92)                   # TENNIS_FAV_MIN / MAX
MAX_C = MAX_CONTRACTS[CT]                 # 100 (H_LOT_CAP)
TAKER_MULT = 1.0                          # tennis taker multiplier (bot/kalshi/feeScheduleSnapshot.json)
COST_STRESS = 0.01                        # adversary: +1c on the entry price
EPS = 1e-9
DMID_MIN = 1.0                            # cents
TREND_EDGES = (3.0, 10.0)                 # cents: |change| < 3 flat, 3-10, >= 10
FLOW_EDGES = (0.2, 0.6)                   # |imbalance| < 0.2 balanced, 0.2-0.6, >= 0.6
SINCE_EDGES = (0, 30, 60, 120)            # minutes from the start
TRADES_FALLBACK = (10.0, 40.0, 120.0)     # trade-count cut points when dev rows are too few to fit quartiles
DAY_RE = re.compile(r'^(\d{4}-\d{2}-\d{2})\.jsonl$')


def _code_sha() -> str:
    try:
        return subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=os.path.dirname(os.path.abspath(__file__)), capture_output=True,
                              text=True, timeout=10).stdout.strip() or 'unknown'
    except Exception:
        return 'unknown'


def check_tour(tour: str) -> str:
    t = str(tour).strip().upper()
    if 'DOGE' in t:
        raise ValueError('DOGE refused (never DOGE)')
    if t not in SERIES:
        raise ValueError(f'unknown tour {tour!r} (one of {sorted(SERIES)})')
    return t


# ---------- reading the history (tarball or extracted directory) ----------

def classify(name: str, series: str):
    """('markets' | 'trades', 'YYYY-MM-DD') for a day file of the series, else None."""
    parts = [p for p in name.replace('\\', '/').split('/') if p not in ('', '.')]
    if len(parts) >= 3 and parts[-2] == 'trades' and parts[-3] == series:
        kind = 'trades'
    elif len(parts) >= 2 and parts[-2] == series:
        kind = 'markets'
    else:
        return None
    m = DAY_RE.match(parts[-1])
    return (kind, m.group(1)) if m else None


def day_allowed(day: str) -> bool:
    return FILE_FROM <= day < FILE_TO


def iter_lines(src: str, series: str, stats: dict):
    """Yield (kind, day, line) for every line of the allowed day files of `series`, from a .tar.gz (streamed) or a
    directory holding <series>/ (or the series directory itself). stats['read'] lists the files parsed, stats['skipped']
    counts the day files left unread (outside 2026-04-27 .. 2026-11-04), stats['odd'] the .jsonl files not named by day."""
    stats.setdefault('read', []); stats.setdefault('skipped', 0); stats.setdefault('odd', 0)

    def take(name):
        if not name.endswith('.jsonl'):
            return None
        c = classify(name, series)
        if c is None:
            p = name.replace('\\', '/')
            if f'{series}/' in p or os.path.basename(os.path.dirname(p)) == series:
                stats['odd'] += 1
            return None
        if not day_allowed(c[1]):
            stats['skipped'] += 1
            return None
        return c

    if os.path.isdir(src):
        root = src if os.path.basename(os.path.normpath(src)) == series else os.path.join(src, series)
        if not os.path.isdir(root):
            raise SystemExit(f'no {series}/ under {src}')
        names = [os.path.join(series, f) for f in sorted(os.listdir(root))]
        if os.path.isdir(os.path.join(root, 'trades')):
            names += [os.path.join(series, 'trades', f) for f in sorted(os.listdir(os.path.join(root, 'trades')))]
        base = os.path.dirname(os.path.normpath(root))
        for name in names:
            c = take(name)
            if c is None:
                continue
            stats['read'].append(name)
            with open(os.path.join(base, name), encoding='utf8') as fh:
                for line in fh:
                    yield c[0], c[1], line
        return
    with tarfile.open(src, mode='r|*') as tf:
        for mem in tf:
            if not mem.isfile():
                continue
            c = take(mem.name)
            if c is None:
                continue
            stats['read'].append(mem.name)
            fh = tf.extractfile(mem)
            for raw in fh:
                yield c[0], c[1], raw.decode('utf8')


@dataclass
class Market:
    ticker: str
    event: str
    start: int
    close: int
    open: int
    result: float           # 1.0 = YES won
    t0: int                 # time of grid minute 0 (a candle END)
    bid: np.ndarray         # (L,) YES bid per grid minute, NaN = no two-sided book
    ask: np.ndarray
    stale: np.ndarray       # (L,) uint8 minutes since the quote's candle

    @property
    def L(self) -> int:
        return len(self.bid)

    @property
    def T(self) -> np.ndarray:
        return self.t0 + MIN * np.arange(self.L, dtype=np.int64)


def event_of(m: dict) -> str:
    ev = m.get('event')
    if isinstance(ev, str) and ev:
        return ev
    tk = str(m.get('ticker', ''))
    return tk[:tk.rfind('-')] if '-' in tk else tk


def minute_series(m: dict):
    """A stored market -> (t0, bid, ask, stale) on its 1-minute grid (see the module doc), or None without candles."""
    close = int(m['closeTime'])
    cands = [c for c in (m.get('candles') or []) if isinstance(c, dict) and isinstance(c.get('ts'), (int, float))]
    repair_legacy_cents(cands)
    cands.sort(key=lambda c: c['ts'])
    cands = [c for c in cands[1:] if int(c['ts']) < close]      # the first stored candle is dropped (historyReplay v8)
    if not cands:
        return None
    t0 = int(cands[0]['ts'])
    L = int(math.ceil((close - t0) / MIN))
    if L <= 0:
        return None
    cb = np.full(L, np.nan); ca = np.full(L, np.nan); has = np.zeros(L, dtype=bool)
    for c in cands:
        i = int(round((int(c['ts']) - t0) / MIN))
        if 0 <= i < L:
            has[i] = True
            b, a = _f(c.get('bidC')), _f(c.get('askC'))
            if _book(b, a):
                cb[i], ca[i] = b, a
            else:
                cb[i] = ca[i] = np.nan
    bid = np.full(L, np.nan); ask = np.full(L, np.nan); stale = np.zeros(L, dtype=np.uint8)
    last = -10 ** 9
    for i in range(L):
        if has[i]:
            if np.isfinite(cb[i]):
                bid[i], ask[i], last = cb[i], ca[i], i
            else:
                last = -10 ** 9
        elif 1 <= i - last <= MAX_STALE:
            bid[i], ask[i], stale[i] = bid[last], ask[last], i - last
    return t0, bid, ask, stale


def read_history(src: str, series: str, log=print):
    """(markets: list[Market], tapes: {ticker: (ts int64, yes contracts, no contracts)}, counts, stats)."""
    stats: dict = {}
    cnt = {k: 0 for k in ('lines', 'no_start', 'pre_era', 'after_cutoff', 'bad_start', 'unsettled', 'no_candles', 'duplicate', 'kept')}
    markets: dict[str, Market] = {}
    tapes: dict[str, tuple] = {}
    for kind, day, line in iter_lines(src, series, stats):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if kind == 'trades':
            tk = r.get('ticker')
            if not isinstance(tk, str) or tk in tapes:
                continue
            tr = np.asarray(r.get('trades') or [], dtype=np.float64)
            if tr.ndim != 2 or tr.shape[1] < 4:
                tr = np.zeros((0, 4))
            tr = tr[np.argsort(tr[:, 0], kind='stable')]
            yes = np.where(tr[:, 3] == 1, tr[:, 2], 0.0)
            no = np.where(tr[:, 3] == 0, tr[:, 2], 0.0)
            tapes[tk] = (tr[:, 0].astype(np.int64), yes, no)
            continue
        cnt['lines'] += 1
        tk, o, c, st = r.get('ticker'), r.get('openTime'), r.get('closeTime'), r.get('startTime')
        if not isinstance(tk, str) or not isinstance(o, (int, float)) or not isinstance(c, (int, float)):
            continue
        if 'DOGE' in tk.upper():
            continue
        if not isinstance(st, (int, float)):
            cnt['no_start'] += 1; continue
        if st < ERA_FROM:
            cnt['pre_era'] += 1; continue
        if c >= HOLD_TO:
            cnt['after_cutoff'] += 1; continue
        if not st < c:
            cnt['bad_start'] += 1; continue
        if r.get('result') not in ('yes', 'no'):
            cnt['unsettled'] += 1; continue
        if tk in markets:
            cnt['duplicate'] += 1; continue
        s = minute_series(r)
        if s is None:
            cnt['no_candles'] += 1; continue
        t0, bid, ask, stale = s
        markets[tk] = Market(tk, event_of(r), int(st), int(c), int(o), 1.0 if r['result'] == 'yes' else 0.0, t0, bid, ask, stale)
        cnt['kept'] += 1
    tapes = {tk: v for tk, v in tapes.items() if tk in markets}
    log(f'tennis {series}: read {len(stats["read"])} day file(s), left {stats["skipped"]} unread (outside {FILE_FROM} .. '
        f'{FILE_TO} exclusive), {stats["odd"]} not named by day; market lines {cnt["lines"]}: kept {cnt["kept"]}, no start '
        f'{cnt["no_start"]}, before the start era {cnt["pre_era"]}, closing at/after the cutoff {cnt["after_cutoff"]}, start '
        f'not before close {cnt["bad_start"]}, unsettled {cnt["unsettled"]}, no candles {cnt["no_candles"]}, duplicate '
        f'{cnt["duplicate"]}; {len(tapes)} tape(s)')
    return list(markets.values()), tapes, cnt, stats


# ---------- the exit ----------

def net_at(b, C, cost):
    """Net $ of selling C contracts at bid b (NaN where b is not a price), on the entry cost (C x ask + entry fee)."""
    b = np.asarray(b, dtype=np.float64)
    ok = np.isfinite(b) & (b > 0) & (b < 1)
    bs = np.where(ok, b, 0.5)
    return np.where(ok, np.round(C * bs - taker_fee(C, bs, TAKER_MULT) - cost, 6), np.nan)


def simulate(bid: np.ndarray, t0: int, close: int, settle: float, k: np.ndarray, px: np.ndarray, size: float, h: int,
             max_c: int = MAX_C, target: float = TARGET_USD) -> dict:
    """The primary exit (module doc) for M positions entered at grid minute k (M,) at price px (M,) (per contract, before
    the fee). bid (L,): the side's bid per grid minute (NaN = no book); settle: 1.0 if the side won, else 0.0.
    Returns trade, best (net $), hit (bool), hold (minutes), read_end (ms: the latest instant the exit or best looked at),
    C; NaN / 0 where the entry is not valid."""
    bid = np.asarray(bid, dtype=np.float64)
    L = len(bid)
    if not (t0 + (L - 1) * MIN < close <= t0 + L * MIN):
        raise ValueError('the grid must cover every minute before the close: L = ceil((close - t0) / 1 min)')
    k = np.asarray(k, dtype=np.int64)
    px = np.asarray(px, dtype=np.float64)
    M = len(k)
    live = (k >= 0) & (k < L) & np.isfinite(px) & (px > 0) & (px < 1)
    kc = np.clip(k, 0, max(L - 1, 0))
    pxs = np.round(np.where(live, px, 0.5), 4)              # the 4-decimal price grid (NO ask = 1 - bid in float)
    C = np.where(live, np.minimum(contracts_for_stake(size, pxs), max_c), 0.0)
    cost = C * pxs + taker_fee(C, pxs, TAKER_MULT)
    tk = t0 + MIN * kc
    fin = np.isfinite(bid) & (bid > 0) & (bid < 1)
    nxt = np.where(fin, np.arange(L), L)
    nxt = np.append(np.minimum.accumulate(nxt[::-1])[::-1], L)       # next minute >= i with a book (L = none)

    j = kc[:, None] + 1 + np.arange(h)[None, :]                       # (M, h): minutes k+1 .. k+h
    inw = j <= L - 1
    net = net_at(np.where(inw, bid[np.minimum(j, L - 1)], np.nan), C[:, None], cost[:, None])
    tp = np.isfinite(net) & (net >= target)
    has_tp = tp.any(axis=1)
    j_tp = np.argmax(tp, axis=1)
    rows = np.arange(M)
    net_tp = net[rows, j_tp]
    settle_net = np.round(C * float(settle) - cost, 6)
    closes_in = kc + h > L - 1                                       # the market is closed at minute k + h
    jn = nxt[np.minimum(kc + h, L)]
    has_q = jn < L
    net_q = net_at(np.where(has_q, bid[np.minimum(jn, L - 1)], np.nan), C, cost)
    to_close = np.ceil((close - tk) / MIN).astype(np.int64)

    tp_ = has_tp
    ride = ~tp_ & closes_in                     # closed inside the horizon without a take-profit: it settles (causal)
    time_q = ~tp_ & ~closes_in & has_q
    time_settle = ~tp_ & ~closes_in & ~has_q
    conds = [tp_, ride | time_settle, time_q]
    trade = np.select(conds, [net_tp, settle_net, net_q], np.nan)
    hold = np.select(conds, [j_tp + 1, to_close, jn - kc], 0)
    exit_t = np.select(conds, [t0 + MIN * (kc + 1 + j_tp), np.full(M, close), t0 + MIN * np.minimum(jn, L)], close)
    read_end = np.maximum(exit_t, np.minimum(tk + h * MIN, close))
    hit = tp_ | (ride & (settle_net >= target))
    wmax = np.max(np.where(np.isfinite(net), net, -np.inf), axis=1) if h > 0 else np.full(M, -np.inf)
    best = np.where(np.isfinite(wmax), wmax, np.nan)
    best = np.fmax(best, np.where(closes_in, settle_net, np.nan))
    best = np.fmax(best, trade)
    return {'trade': np.where(live, trade, np.nan), 'best': np.where(live, best, np.nan), 'hit': live & hit,
            'hold': np.where(live, hold, 0).astype(np.int64), 'read_end': np.where(live, read_end, 0).astype(np.int64), 'C': C}


# ---------- features ----------

TA_NAMES = ['ta_rsi14', 'ta_stoch', 'ta_willr14', 'ta_cci14', 'ta_bb', 'ta_macdh', 'ta_slope14', 'ta_mom10', 'ta_adx14']


def _sign(x, tol: float = 1e-9) -> np.ndarray:
    x = np.asarray(x, dtype=np.float64)
    return np.where(np.isfinite(x) & (x > tol), 1, np.where(np.isfinite(x) & (x < -tol), -1, 0)).astype(np.int8)


def _band_state(x, hi, lo) -> np.ndarray:
    x = np.asarray(x, dtype=np.float64)
    return np.where(np.isfinite(x) & (x > hi), 1, np.where(np.isfinite(x) & (x < lo), -1, 0)).astype(np.int8)


def _flat(x: np.ndarray, w: int) -> np.ndarray:
    """True at i when the w values ending at i exist and are all equal."""
    out = np.zeros(len(x), dtype=bool)
    if len(x) >= w:
        win = np.lib.stride_tricks.sliding_window_view(x, w)
        out[w - 1:] = (win.max(axis=1) - win.min(axis=1)) <= 1e-12
    return out


def ta_states(mid: np.ndarray) -> dict:
    """TA-Lib states (int8 -1/0/+1) of one 1-minute mid series in cents, causal per minute; NaN minutes break it into
    segments that are read separately (warm-up and NaN -> 0)."""
    mid = np.asarray(mid, dtype=np.float64)
    L = len(mid)
    out = {n: np.zeros(L, dtype=np.int8) for n in TA_NAMES}
    v = np.concatenate([[False], np.isfinite(mid), [False]]).astype(np.int8)
    d = np.diff(v)
    for a, b in zip(np.nonzero(d == 1)[0], np.nonzero(d == -1)[0]):
        x = np.ascontiguousarray(mid[a:b])
        if len(x) < 2:
            continue
        with np.errstate(invalid='ignore', divide='ignore'):
            rsi = talib.RSI(x, timeperiod=14)
            out['ta_rsi14'][a:b] = np.where(_flat(x, 15), 0, _band_state(rsi, 70, 30))
            slowk, _ = talib.STOCH(x, x, x, fastk_period=14, slowk_period=3, slowk_matype=0, slowd_period=3, slowd_matype=0)
            out['ta_stoch'][a:b] = np.where(_flat(x, 14), 0, _band_state(slowk, 80, 20))
            wr = talib.WILLR(x, x, x, timeperiod=14)
            out['ta_willr14'][a:b] = np.where(_flat(x, 14), 0, _band_state(wr, -20, -80))
            out['ta_cci14'][a:b] = _band_state(talib.CCI(x, x, x, timeperiod=14), 100, -100)
            up, _, lo = talib.BBANDS(x, timeperiod=20, nbdevup=2, nbdevdn=2, matype=0)
            wid = up - lo
            pb = np.where(np.isfinite(wid) & (wid > 1e-12), (x - lo) / np.where(wid > 1e-12, wid, 1.0), np.nan)
            out['ta_bb'][a:b] = _band_state(pb, 1.0, 0.0)
            out['ta_macdh'][a:b] = _sign(talib.MACD(x, fastperiod=12, slowperiod=26, signalperiod=9)[2])
            out['ta_slope14'][a:b] = _sign(talib.LINEARREG_SLOPE(x, timeperiod=14))
            out['ta_mom10'][a:b] = _sign(talib.MOM(x, timeperiod=10))
            adx = talib.ADX(x, x, x, timeperiod=14)
            di = talib.PLUS_DI(x, x, x, timeperiod=14) - talib.MINUS_DI(x, x, x, timeperiod=14)
            out['ta_adx14'][a:b] = np.where(np.isfinite(adx) & (adx > 25), _sign(di), 0).astype(np.int8)
    return out


def change_state(d) -> np.ndarray:
    """+1 for a mid change >= +1c, -1 for <= -1c, 0 otherwise or NA."""
    d = np.asarray(d, dtype=np.float64)
    return np.where(np.isfinite(d) & (d >= DMID_MIN - 1e-6), 1, np.where(np.isfinite(d) & (d <= -DMID_MIN + 1e-6), -1, 0)).astype(np.int8)


def sym_bucket(x, edges) -> np.ndarray:
    """Symmetric 5-level bucket around 0: 0 = <= -edges[1] .. 2 = |x| < edges[0] .. 4 = >= edges[1]; NA -> -1."""
    x = np.asarray(x, dtype=np.float64)
    fin = np.isfinite(x)
    xs = np.where(fin, x, 0.0)
    a = np.abs(xs)
    m = (a >= edges[0] - 1e-9).astype(np.int64) + (a >= edges[1] - 1e-9).astype(np.int64)
    return np.where(fin, 2 + np.sign(xs).astype(np.int64) * m, -1).astype(np.int8)


def price_bucket(ask) -> np.ndarray:
    """0.1-wide bucket of the side's ask inside [0.05, 0.95]: floor(10 x ask), 0 = [0.05, 0.10) .. 9 = [0.90, 0.95];
    -1 outside the band."""
    ask = np.asarray(ask, dtype=np.float64)
    inb = in_band(ask)
    return np.where(inb, np.clip(np.floor(np.where(inb, ask, 0.5) * 10 + 1e-6), 0, 9), -1).astype(np.int8)


def in_band(ask) -> np.ndarray:
    ask = np.asarray(ask, dtype=np.float64)
    return np.isfinite(ask) & (ask >= PRICE_BAND[0] - EPS) & (ask <= PRICE_BAND[1] + EPS)


def band_bucket(mid) -> np.ndarray:
    """Production entry bands on the side's mid: 1 = underdog [0.08, 0.25], 2 = favourite [0.75, 0.92], 0 = neither."""
    m = np.asarray(mid, dtype=np.float64)
    dog = (m >= DOG_BAND[0] - EPS) & (m <= DOG_BAND[1] + EPS)
    fav = (m >= FAV_BAND[0] - EPS) & (m <= FAV_BAND[1] + EPS)
    return np.where(dog, 1, np.where(fav, 2, 0)).astype(np.int8)


def spread_bucket(spread) -> np.ndarray:
    s = np.asarray(spread, dtype=np.float64)
    return np.where(s <= 0.01 + 1e-6, 0, np.where(s <= 0.02 + 1e-6, 1, 2)).astype(np.int8)


def since_bucket(t, start) -> np.ndarray:
    m = (np.asarray(t, dtype=np.int64) - start) / MIN
    return np.searchsorted(np.asarray(SINCE_EDGES, dtype=np.float64), m, side='right').astype(np.int8)


def phase_of(t, start) -> np.ndarray:
    """Matched-baseline phase: 0 = pre-match, 1 = first 60 live minutes, 2 = later."""
    m = (np.asarray(t, dtype=np.int64) - start) / MIN
    return np.where(m < 0, 0, np.where(m < 60, 1, 2)).astype(np.int8)


def trade_edges_of(counts: np.ndarray, dev: np.ndarray) -> tuple[list, str]:
    """Quartile cut points of the positive 5-minute trade counts on dev rows (before DEV_END); fixed fallback."""
    v = counts[dev & (counts > 0)]
    if len(v) >= 40:
        q = np.quantile(v, [0.25, 0.5, 0.75])
        if np.all(np.diff(q) > 0):
            return [float(x) for x in q], f'quartiles of positive values on {len(v)} dev rows'
    return list(TRADES_FALLBACK), 'fixed fallback (too few dev rows to fit quartiles)'


def trades_bucket(counts, edges) -> np.ndarray:
    c = np.asarray(counts, dtype=np.float64)
    return np.where(c > 0, 1 + np.searchsorted(np.asarray(edges), c, side='right'), 0).astype(np.int8)


def hour4(t) -> np.ndarray:
    return (((np.asarray(t, dtype=np.int64) // 3_600_000) % 24) // 4).astype(np.int8)


def weekend(t) -> np.ndarray:
    wd = (np.asarray(t, dtype=np.int64) // DAY + 4) % 7        # 1970-01-01 was a Thursday: 0 = Sunday .. 6 = Saturday
    return ((wd == 0) | (wd == 6)).astype(np.int8)


BOTH = [
    ('k_since', 'bucket', 5, ['pre', '0-30', '30-60', '60-120', '120+'],
     'minutes from the published start: pre-match (30-0 before), 0-30, 30-60, 60-120, 120+'),
    ('k_spread', 'bucket', 3, ['1c', '2c', '3c'], 'YES ask - YES bid (= the NO spread): <= 1c, <= 2c, <= 3c'),
    ('k_trades5', 'bucket', 5, None, 'trades on the tape in [t - 5 min, t): 0 = none, 1..4 split at {edges} ({how})'),
    ('ctx:hour4', 'bucket', 6, ['00-04', '04-08', '08-12', '12-16', '16-20', '20-24'], 'UTC hour of the decision instant / 4'),
    ('ctx:weekend', 'bucket', 2, ['weekday', 'weekend'], 'UTC Saturday or Sunday at the decision instant'),
]
PER_SIDE = [
    ('ta_rsi14', 'state', 'RSI14 of the side mid: +1 > 70, -1 < 30 (0 on a flat 15-minute window)'),
    ('ta_stoch', 'state', 'STOCH 14/3/3 slowk of the side mid: +1 > 80, -1 < 20 (0 on a flat 14-minute window)'),
    ('ta_willr14', 'state', 'WILLR14 of the side mid: +1 > -20, -1 < -80 (0 on a flat 14-minute window)'),
    ('ta_cci14', 'state', 'CCI14 of the side mid: +1 > 100, -1 < -100'),
    ('ta_bb', 'state', 'Bollinger %B 20/2 of the side mid: +1 > 1 (above the upper band), -1 < 0'),
    ('ta_macdh', 'state', 'MACD 12/26/9 histogram sign of the side mid'),
    ('ta_slope14', 'state', 'LINEARREG_SLOPE14 sign of the side mid'),
    ('ta_mom10', 'state', 'MOM10 sign of the side mid'),
    ('ta_adx14', 'state', 'ADX14 > 25: +1 when +DI > -DI, -1 when -DI > +DI (0 otherwise or ADX <= 25)'),
    ('k_dmid1', 'state', "the side's mid change over 1 minute: +1 >= +1c, -1 <= -1c, 0 otherwise or NA"),
    ('k_dmid3', 'state', "the side's mid change over 3 minutes (+-1c)"),
    ('k_dmid5', 'state', "the side's mid change over 5 minutes (+-1c)"),
    ('k_dmid15', 'state', "the side's mid change over 15 minutes (+-1c)"),
    ('k_other5', 'state', "the other market's same-side mid change over 5 minutes (+-1c; Y: its YES mid, N: its NO mid); "
                          '0 when the match has no second market or NA'),
    ('k_flow5', 'bucket', "taker flow imbalance on the tape in [t - 5 min, t), side-relative (Y: (yes - no) / total "
                          'contracts, N: its negative): 0 <= -0.6, 1 (-0.6, -0.2], 2 |x| < 0.2, 3 [0.2, 0.6), 4 >= 0.6; -1 = no trades'),
    ('k_price', 'bucket', "the side's ask: floor(10 x ask), 0 = [0.05, 0.10) .. 9 = [0.90, 0.95]; -1 outside the band"),
    ('k_band', 'bucket', "production entry bands on the side's mid: 0 neither, 1 underdog [0.08, 0.25], 2 favourite [0.75, 0.92]"),
    ('k_trend60', 'bucket', "the side's mid change over 60 minutes (prereg context, 60-minute trend): 0 <= -10c, 1 (-10, -3], "
                            '2 |x| < 3c, 3 [3, 10), 4 >= 10c; -1 = NA'),
]
PER_SIDE_LEVELS = {'k_flow5': 5, 'k_price': 10, 'k_band': 3, 'k_trend60': 5}


def feature_meta(edges, how) -> list:
    out = []
    for name, kind, L, names, desc in BOTH:
        f = {'name': name, 'kind': kind, 'levels': list(range(L)),
             'desc': desc.format(edges=[round(x, 3) for x in edges], how=how)}
        if names:
            f['level_names'] = names
        out.append(f)
    for name, kind, desc in PER_SIDE:
        levels = [-1, 0, 1] if kind == 'state' else list(range(PER_SIDE_LEVELS[name]))
        for sl in ('Y', 'N'):
            out.append({'name': f'{name}@{sl}', 'kind': kind, 'levels': levels, 'desc': desc, 'side': sl, 'base': name})
    return out


# ---------- one market ----------

def _shift(x: np.ndarray, m: int) -> np.ndarray:
    """x[i - m] (NaN for i < m)."""
    out = np.full(len(x), np.nan)
    if m < len(x):
        out[m:] = x[:len(x) - m]
    return out


def _flow(tape, t: np.ndarray):
    """(yes contracts, no contracts, trades) on the tape in [t - 5 min, t) for each decision instant t."""
    if tape is None or not len(tape[0]):
        z = np.zeros(len(t))
        return z, z, z
    ts, yes, no = tape
    cy = np.concatenate([[0.0], np.cumsum(yes)]); cn = np.concatenate([[0.0], np.cumsum(no)])
    lo = np.searchsorted(ts, t - 5 * MIN, side='left')
    hi = np.searchsorted(ts, t, side='left')
    return cy[hi] - cy[lo], cn[hi] - cn[lo], (hi - lo).astype(np.float64)


def market_rows(mk: Market, other: Market | None, tape) -> dict | None:
    """Decision rows of one market: times, per-side tradability, labels and features (feature arrays per name)."""
    L = mk.L
    T = mk.T
    bid, ask = mk.bid, mk.ask
    book = np.isfinite(bid) & np.isfinite(ask)
    spread = ask - bid
    # Decisions only at candle minutes (stale == 0): a carried quote is never entered on (prereg "every candle minute";
    # a carried ask beside fresh features would be a free option). Carried quotes still value exits.
    gate = book & (mk.stale == 0) & (T >= mk.start - PRE_MIN * MIN) & (T >= mk.open + MIN) & (spread <= MAX_SPREAD + EPS)
    sb = np.stack([bid, 1.0 - ask])           # side bids (2, L): Y, N
    sa = np.stack([ask, 1.0 - bid])           # side asks
    sok = gate[None, :] & in_band(sa)
    idx = np.nonzero(sok.any(axis=0))[0]
    if not len(idx):
        return None
    t = T[idx]
    out = {'t': t, 'stale': mk.stale[idx], 'tmin': ((t - mk.start) // MIN).astype(np.int64), 'sok': sok[:, idx]}

    # Labels per side / horizon / variant.
    for s, sl in enumerate(SIDES[CT]):
        settle = mk.result if s == 0 else 1.0 - mk.result
        oks = sok[s, idx]
        a_k = np.where(oks, sa[s, idx], np.nan)
        a_k1 = np.where(oks & (idx + 1 < L), sa[s, np.minimum(idx + 1, L - 1)], np.nan)
        for h in HORIZONS[CT]:
            prim = simulate(sb[s], mk.t0, mk.close, settle, idx, a_k, SIZE[CT], h)
            two = simulate(sb[s], mk.t0, mk.close, settle, idx, a_k, SIZE2[CT], h)
            lat = simulate(sb[s], mk.t0, mk.close, settle, idx + 1, a_k1, SIZE[CT], h)
            cst = simulate(sb[s], mk.t0, mk.close, settle, idx, a_k + COST_STRESS, SIZE[CT], h)
            # Leakage guard: a decision before DEV_END may not read past it (its exit, its best window, a settlement).
            vis = lambda r: (t >= DEV_END) | (r['read_end'] <= DEV_END)
            okp = oks & vis(prim)
            out[key('ok', sl, h)] = okp
            out[key('guard', sl, h)] = oks & ~okp
            out[key('trade', sl, h)] = np.where(okp, prim['trade'], np.nan)
            out[key('best', sl, h)] = np.where(okp, prim['best'], np.nan)
            out[key('hit', sl, h)] = okp & prim['hit']
            out[key('hold', sl, h)] = np.where(okp, prim['hold'], 0)
            ok2 = okp & vis(two)
            out[key('trade2', sl, h)] = np.where(ok2, two['trade'], np.nan)
            out[key('hit2', sl, h)] = ok2 & two['hit']
            out[key('tradeLat', sl, h)] = np.where(okp & vis(lat), lat['trade'], np.nan)
            out[key('tradeCost', sl, h)] = np.where(okp & vis(cst), cst['trade'], np.nan)

    # Features.
    ymid = (bid + ask) / 2.0 * 100.0                               # YES mid in cents, NaN = no book
    omid = None
    if other is not None:
        off = int(round((other.t0 - mk.t0) / MIN))
        omid = np.full(L, np.nan)
        om = (other.bid + other.ask) / 2.0 * 100.0
        i0, i1 = max(0, off), min(L, off + other.L)
        if i1 > i0:
            omid[i0:i1] = om[i0 - off:i1 - off]
    yes5, no5, n5 = _flow(tape, t)
    tot = yes5 + no5
    imb = np.where(tot > 0, (yes5 - no5) / np.where(tot > 0, tot, 1.0), np.nan)
    f: dict[str, np.ndarray] = {
        'k_since': since_bucket(t, mk.start), 'k_spread': spread_bucket(spread[idx]), 'ctx:hour4': hour4(t), 'ctx:weekend': weekend(t)}
    out['trades5_raw'] = n5
    for s, sl in enumerate(SIDES[CT]):
        m = ymid if s == 0 else 100.0 - ymid
        ta = ta_states(m)
        for n in TA_NAMES:
            f[f'{n}@{sl}'] = ta[n][idx]
        for w in (1, 3, 5, 15):
            f[f'k_dmid{w}@{sl}'] = change_state((m - _shift(m, w))[idx])
        if omid is not None:
            om_s = omid if s == 0 else 100.0 - omid
            f[f'k_other5@{sl}'] = change_state((om_s - _shift(om_s, 5))[idx])
        else:
            f[f'k_other5@{sl}'] = np.zeros(len(idx), dtype=np.int8)
        f[f'k_flow5@{sl}'] = sym_bucket(imb if s == 0 else -imb, FLOW_EDGES)
        f[f'k_price@{sl}'] = price_bucket(sa[s, idx])
        f[f'k_band@{sl}'] = band_bucket(m[idx] / 100.0)
        f[f'k_trend60@{sl}'] = sym_bucket((m - _shift(m, 60))[idx], TREND_EDGES)
    out['feat'] = f
    out['phase'] = phase_of(t, mk.start)
    return out


# ---------- build ----------

def build(src: str, tour: str, out_root: str, code_sha: str | None = None, log=print, trade_edges=None) -> str:
    tour = check_tour(tour)
    series = SERIES[tour]
    if 'DOGE' in os.path.basename(os.path.normpath(src)).upper():
        raise ValueError('DOGE input refused')
    markets, tapes, cnt, stats = read_history(src, series, log)
    if not markets:
        raise SystemExit('no start-era markets')
    markets.sort(key=lambda m: (m.start, m.event, m.ticker))
    by_event: dict[str, list] = {}
    for i, m in enumerate(markets):
        by_event.setdefault(m.event, []).append(i)
    ev_order = sorted(by_event, key=lambda e: (min(markets[i].start for i in by_event[e]), e))
    ev_index = {e: j for j, e in enumerate(ev_order)}
    one_legged = sum(1 for e in by_event if len(by_event[e]) == 1)
    crowded = sum(1 for e in by_event if len(by_event[e]) > 2)

    per = []
    for i, m in enumerate(markets):
        mates = by_event[m.event]
        other = markets[[j for j in mates if j != i][0]] if len(mates) == 2 else None
        r = market_rows(m, other, tapes.get(m.ticker))
        if r is None:
            continue
        r['mkt'] = np.full(len(r['t']), i, dtype=np.int32)
        r['group'] = np.full(len(r['t']), ev_index[m.event], dtype=np.int64)
        r['close'] = np.full(len(r['t']), m.close, dtype=np.int64)
        per.append(r)
    if not per:
        raise SystemExit('no decision rows')
    cat = lambda name: np.concatenate([r[name] for r in per])
    t = cat('t')
    mkt = cat('mkt')
    order = np.lexsort((mkt, t))
    take = lambda a: np.asarray(a)[order]
    t, mkt = t[order], mkt[order]
    R = len(t)

    n5 = take(cat('trades5_raw'))
    if trade_edges is None:
        edges, how = trade_edges_of(n5, dev_rows(t, max(HORIZONS[CT])))
    else:
        edges, how = [float(x) for x in trade_edges], 'given'
    fmeta = feature_meta(edges, how)
    names = [f['name'] for f in fmeta]
    X = np.empty((R, len(names)), dtype=np.int8)
    for j, name in enumerate(names):
        X[:, j] = trades_bucket(n5, edges) if name == 'k_trades5' else take(np.concatenate([r['feat'][name] for r in per]))
    side_features = {sl: [j for j, f in enumerate(fmeta) if f.get('side') == sl] for sl in SIDES[CT]}

    phase = take(cat('phase')).astype(np.int16)
    sok = take(np.concatenate([r['sok'] for r in per], axis=1).T)        # (R, 2)
    arrays = {'t': t.astype(np.int64), 'group': take(cat('group')), 'asset': np.zeros(R, dtype=np.int8), 'X': X,
              'rv': np.full(R, -1, dtype=np.int8), 'hour': ((t // 3_600_000) % 24).astype(np.int8),
              'mkt': mkt.astype(np.int32), 'close': take(cat('close')), 'tmin': take(cat('tmin')).astype(np.int16),
              'stale': take(cat('stale')).astype(np.uint8)}
    guards = {}
    for s, sl in enumerate(SIDES[CT]):
        pb = X[:, names.index(f'k_price@{sl}')].astype(np.int16)
        arrays[f'stratum_{sl}'] = np.where(sok[:, s] & (pb >= 0), pb * 3 + phase, -1).astype(np.int16)
        for h in HORIZONS[CT]:
            arrays[key('ok', sl, h)] = take(cat(key('ok', sl, h))).astype(np.uint8)
            guards[key('ok', sl, h)] = int(take(cat(key('guard', sl, h))).sum())
            for name, dt in (('hit', np.uint8), ('trade', np.float32), ('best', np.float32), ('hold', np.uint16),
                             ('hit2', np.uint8), ('trade2', np.float32), ('tradeLat', np.float32), ('tradeCost', np.float32)):
                a = take(cat(key(name, sl, h)))
                if name == 'hold':
                    a = np.clip(a, 0, 65535)
                arrays[key(name, sl, h)] = a.astype(dt)

    used = np.unique(mkt)
    meta = {
        'ct': CT, 'scope': tour, 'assets': [tour], 'sides': SIDES[CT], 'horizons': HORIZONS[CT], 'size_usd': SIZE[CT],
        'size2_usd': SIZE2[CT], 'step_min': STEP_MIN[CT], 'code_sha': code_sha or _code_sha(), 'features': fmeta,
        'side_features': side_features,
        'strata_desc': 'stratum_<s> = k_price@<s> x 3 + phase: 10 side-ask buckets (0.1 wide, [0.05, 0.95]) x phase (0 pre-match, '
                       '1 first 60 minutes after the published start, 2 later) = 30; -1 = side not tradable at the decision',
        'notes': NOTES, 'series': series, 'tour': tour, 'era_from': '2026-04-27T05:00Z', 'era_close_before': '2026-11-05T00:00Z',
        'price_band': list(PRICE_BAND), 'max_spread': MAX_SPREAD, 'max_stale_min': MAX_STALE, 'pre_start_min': PRE_MIN,
        'max_contracts': MAX_C, 'taker_multiplier': TAKER_MULT, 'cost_stress_usd': COST_STRESS, 'trade_edges': edges,
        'trade_edges_how': how,
        'tickers': [m.ticker for m in markets], 'events': ev_order,
        'extra_arrays': {'mkt': 'int32 market index within the part (meta.tickers; markets sorted by start, event, ticker)',
                         'close': "int64 the row's market closeTime (ms; actual close, a window bound only, never a feature)",
                         'tmin': 'int16 minutes from the published start (negative before it)',
                         'stale': 'uint8 minutes since the candle whose quote the decision uses: always 0 (decisions are '
                                  'candle minutes only; carried quotes value exits)'},
        'deviations': DEVIATIONS,
        'counts': {**cnt, 'markets_with_rows': int(len(used)), 'events': len(by_event), 'one_legged_events': one_legged,
                   'events_with_more_than_two_markets': crowded, 'rows': int(R), 'dev_guard_not_ok': guards,
                   'day_files_read': len(stats['read']), 'day_files_unread': stats['skipped']},
    }
    path = os.path.join(out_root, f'{CT}-{tour}')
    write_part(path, meta, arrays)
    log(f'{CT}-{tour}: wrote {R} rows x {X.shape[1]} features ({len(used)} markets, {len(by_event)} events, {one_legged} '
        f'one-legged) to {path}')
    return path


# Departures from the OR-H1 text, decided before any tennis HO-1 opening (review of Nov 6); copied into frozen.json.
DEVIATIONS = [
    'tennis exit: when the market closes inside the horizon without a take-profit the position settles; the OR-H1 text '
    '"ride to settlement only if in profit at the last candle, else sell at that bid" is not causal (the last candle of a '
    'match is known to be the last only after the match ended)',
    'tennis decisions: candle minutes only (stale == 0); quotes carried over empty minutes value exits but are never '
    'entered on (OR-H1 "every candle minute")',
]

NOTES = ('Rows = 1-minute decisions of start-era tennis match markets (both markets of each event), from 30 minutes before '
         'the published start to the close, at candle minutes only (the candle close is a two-sided YES book; a quote '
         'carried at most 5 minutes over empty minutes values exits but is never entered on) with spread <= 3c; a row has '
         'at least one side whose ask is in [0.05, 0.95]. Sides Y (buy YES at the ask, '
         'sell at the YES bid) and N (buy NO at 1 - YES bid, sell at 1 - YES ask), taker both legs, C = min(floor(size / '
         'ask), 100), bot/fees.ts taker fee (tennis multiplier 1), no settlement fee. Exit at horizon h: take-profit at the '
         'bid at the first minute in (k, k + h] with net >= $5; else, market open at k + h: sell at its bid (or the first '
         'later bid; settle if none); else (close inside the horizon): the position settles (DEVIATION from the OR-H1 text '
         '"ride only if in profit at the last candle, else sell at that bid": the last candle of a match is known only '
         'after the match ended, so that sale was not causal; review of Nov 6). hit = TP or a settlement inside the horizon '
         'netting >= $5. Prices are rounded to 4 decimals before sizing and fees. best = max(bid sales in (k, k + h], the '
         'settlement if the close is inside the horizon, the trade). hold in minutes (settlement: ceil to the close). '
         'tradeLat = entry at minute k + 1; tradeCost = entry price + 1c. A row decided before DEV_END whose exit or best '
         'window reads past DEV_END is not ok. SIDE FEATURES: columns named <feature>@Y / <feature>@N are side-relative (TA '
         'and changes on the side\'s own mid, the other market\'s same-side change, the side-relative flow, the side\'s ask '
         'bucket and band); meta.side_features lists per side the X columns that apply to it, and a column listed in neither '
         'applies to both sides (k_since, k_spread, k_trades5, ctx:hour4, ctx:weekend). Mining side s reads the unlisted '
         'columns plus side_features[s], with the @s suffix stripped. group = event index (the two markets of a match share '
         'it; meta.events); mkt.npy = market index (meta.tickers); rv = -1 (tennis has no RV regime; scope = tour).')


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description='Build parts/tennis-<TOUR>/ (oracle SPEC 2c).')
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument('--tar', help='the history tarball <SERIES>.tar.gz (raw/tennis-history/kalshi on Drive)')
    src.add_argument('--hist', help='a directory holding the extracted <SERIES>/ (or the series directory itself)')
    ap.add_argument('--tour', required=True, help='ATP or WTA')
    ap.add_argument('--out', required=True, help='parts root; writes <out>/tennis-<TOUR>/')
    ap.add_argument('--code-sha', default=None)
    a = ap.parse_args(argv)
    build(a.tar or a.hist, a.tour, a.out, a.code_sha)


if __name__ == '__main__':
    main()
