"""Part B of the audit path (research/audit_path/PREREG-AP.md, part 1, part B and amendment 2): the replayed curve calls joined to
Kalshi's one-minute history, scored by the one test (python/auditpath/onetest.py, reused unchanged).

Run (on a runner that holds the calls shards and the history day files, all private Drive data; nothing is fetched here):

    cd python && python3 -m auditpath.joincalls --calls <dir of calls-*.jsonl.gz> --m15 <dir holding KXBTC15M/ and KXETH15M/> \
        --hourly <dir holding KXBTCD/ and KXETHD/> --from 2026-08-01 --to 2026-11-04 --out joined.json

Order, enforced in run() and proved in the tests: (1) the calls shards are read, rows with skip set are dropped (the lane skips those),
h 15 and 60 of BTC and ETH are kept, the shards are checked to cover every UTC day from --from to --to for both coins with no
duplicate (asset, h, t0); (2) ONE sha256 over the kept rows is printed in an "AUDITPATH join" line; (3) only then is a Kalshi file
listed or opened. The hash is over the kept rows sorted by (asset, h, t0), each written as JSON with sorted keys and compact
separators, one per line with a final newline.

History files (the Drive day files, one per UTC day of the CLOSE time, named <YYYY-MM-DD>.jsonl; the compact .jsonl.mdc form must be
decoded first with "npx tsx scripts/mdc.ts expand <dir>", as .github/workflows/dtback.yml does). One JSON line per settled market:
ticker, event (hourly ladders), openTime and closeTime in epoch MILLISECONDS, strike, result ('yes' or 'no'), candles[] of
{ts = candle END in milliseconds, bidO, bidH, bidL, bidC, askO, askH, askL, askC, ...} in dollars (research/history/kalshiHistory.ts,
python/allpairs/data.py load_kalshi). onetest.norm_hist_candles turns the candles into the scorer's form (end in epoch seconds).
Units: the calls table's t0 is epoch SECONDS; closeTime is divided by 1000 and rounded to a second; candle ts likewise.

Entries (PREREG, part B):
  15m call at T0: the KX<COIN>15M contract whose close is 300 to 840 s after T0 (both ends included). None is "no contract".
  60m call at T0: the hourly event closing 600 to 3300 s after T0 (both ends included; none is "no contract"), on the strike whose
  YES mid at T0 (the close of the candle that ends at T0) is nearest 50c among strikes with a two-sided quote (0 < bid < ask < 1);
  a tie goes to the lower strike; none is "no strike". The entry is {id = ticker, coin, kind, close_ts, side, t0}; side is 'yes' for
  dir +1 and 'no' for dir -1; the result is the history line's own.
Several entries on one ticker are fine: the primary count keeps the first scored one, the secondary count keeps all.

Hourly availability. PREREG says the hourly half is "not available" when the history does not hold the strikes near the money. It
gives no number; the literal reading taken here: the hourly half is available when at least half of the 60-minute calls have a
two-sided strike whose YES mid at T0 is inside 10c to 90c (the lane's band). The counts are always printed in an own line. When it
is not available the hourly entries are left out of the analysis and nothing replaces them.

Output: lines "AUDITPATH join <json>", aggregates only (counts, rates, cents, dollars an hour, hashes); no ticker, no call row, no
single timestamp. The full aggregate JSON goes to --out. Hours for dollars an hour = UTC days with at least one analysed entry x 24 (amendment 1);
both that and the calendar day count are printed. When the hourly half is left out, its own analysis is kept in --out (never printed).
"""
import argparse
import bisect
import calendar
import collections
import glob
import gzip
import hashlib
import json
import os
import re
import statistics
import sys
import time

from auditpath import onetest

COINS = ('BTC', 'ETH')                          # the coins whose history is on Drive; never DOGE
HORIZONS = (15, 60)
KIND = {15: '15m', 60: 'hourly'}
CLOSE_AFTER_S = {'15m': (300, 840), 'hourly': (600, 3300)}   # a contract qualifies when close - T0 is in this range, both ends in
BAND_X2 = 80                                    # hourly availability: 2 x |mid - 50c| in whole cents, at most 80 (mid in 10c to 90c)
AVAILABLE_SHARE = 0.5                           # hourly availability: at least this share of the 60-minute calls have such a strike
ONE_SIDED = ('no candles', 'no candle at T0', 'not two-sided')
LINE_LIMIT = 2800
DAY_FILE = re.compile(r'^(\d{4}-\d{2}-\d{2})\.jsonl$')
STRIKE_TAIL = re.compile(r'-[TB]([0-9]+(?:\.[0-9]+)?)$')


class JoinError(Exception):
    """A join that cannot be faithful: the message gives counts only, never a row."""


# ---------------------------------------------------------------- small helpers

def day_number(text):
    """Days since 1970 of a YYYY-MM-DD date (UTC)."""
    try:
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', text):
            raise ValueError(text)
        return calendar.timegm(time.strptime(text, '%Y-%m-%d')) // 86400
    except ValueError:
        raise JoinError('%r is not a YYYY-MM-DD date' % text) from None


def day_text(n):
    return time.strftime('%Y-%m-%d', time.gmtime(n * 86400))


def month_key(b):
    """The month split: UTC month of T0, e.g. 2026-08."""
    return time.strftime('%Y-%m', time.gmtime(b['t0']))


def _month(t0):
    return time.strftime('%Y-%m', time.gmtime(t0))


def emit(log, name, obj, limit=LINE_LIMIT):
    """One line 'AUDITPATH join <json>' per block; a block over the limit is split by its keys into several lines."""
    s = json.dumps({'block': name, **obj} if isinstance(obj, dict) else {'block': name, 'value': obj}, separators=(',', ':'))
    if len(s) > limit and (not isinstance(obj, dict) or len(obj) < 2):
        raise JoinError('a printed block cannot be split under %d characters: %s (%d)' % (limit, name, len(s)))
    if len(s) <= limit:
        if 'KX' in s:
            raise JoinError('a printed block would hold a ticker: %s' % name)
        log('AUDITPATH join ' + s)
        return
    keys = list(obj)
    half = len(keys) // 2
    emit(log, name + '.1', {k: obj[k] for k in keys[:half]}, limit)
    emit(log, name + '.2', {k: obj[k] for k in keys[half:]}, limit)


# ---------------------------------------------------------------- step 1: the calls table

class Series:
    """The kept calls of one (asset, h): sorted T0 in epoch seconds, the direction, and what the join did with each call
    (state 0 none found, 1 entered, 2 hourly event found but no strike)."""

    def __init__(self, rows):
        rows.sort(key=lambda r: r[0])
        self.t0 = [r[0] for r in rows]
        self.dir = [r[1] for r in rows]
        self.state = bytearray(len(rows))
        self.in_band = bytearray(len(rows))


class Calls:
    def __init__(self, series, digest, info):
        self.series, self.digest, self.info = series, digest, info


def _read_shard(path):
    with gzip.open(path, 'rt', encoding='utf8') as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def load_calls(calls_dir, day_from, day_to, shard_reader=_read_shard):
    """Every row of every shard under calls_dir; skip rows dropped; coverage and duplicates checked; the sha256 over the kept rows.
    day_from and day_to are day numbers (inclusive)."""
    files = sorted(set(glob.glob(os.path.join(calls_dir, '**', 'calls-*.jsonl.gz'), recursive=True)))
    if not files:
        raise JoinError('no calls shard under the calls folder')
    lo_t, hi_t = day_from * 86400, (day_to + 1) * 86400
    kept, total, skipped, ignored = [], 0, 0, 0
    days_seen = {a: set() for a in COINS}
    for f in files:
        for r in shard_reader(f):
            total += 1
            a, h = r.get('asset'), r.get('h')
            if a not in COINS or h not in HORIZONS:
                ignored += 1
                continue
            t0 = r.get('t0')
            if not isinstance(t0, (int, float)) or isinstance(t0, bool) or t0 != int(t0) or t0 % 60 or not lo_t <= t0 < hi_t:
                raise JoinError('a calls row has a t0 that is not a whole minute in epoch seconds inside the range (rows so far: %d)' % total)
            days_seen[a].add(int(t0) // 86400)
            if r.get('skip'):
                skipped += 1
                continue
            d = r.get('dir')
            if d not in (1, -1):
                raise JoinError('a kept calls row has a dir that is not +1 or -1')
            kept.append((a, int(h), int(t0), int(d), json.dumps(r, sort_keys=True, separators=(',', ':'), allow_nan=False)))
    want = set(range(day_from, day_to + 1))
    short = {a: len(want - days_seen[a]) for a in COINS}
    if any(short.values()):
        raise JoinError('the shards do not cover every day: days without any row by coin %s of %d' % (json.dumps(short, sort_keys=True), len(want)))
    kept.sort(key=lambda r: (r[0], r[1], r[2]))
    dups = sum(1 for i in range(1, len(kept)) if kept[i][:3] == kept[i - 1][:3])
    if dups:
        raise JoinError('%d duplicate (asset, h, t0) among the kept rows' % dups)
    sha = hashlib.sha256()
    for r in kept:
        sha.update(r[4].encode('utf8') + b'\n')
    grouped = collections.defaultdict(list)
    for a, h, t0, d, _ in kept:
        grouped[(a, h)].append((t0, d))
    series = {k: Series(v) for k, v in grouped.items()}
    for a in COINS:
        for h in HORIZONS:
            series.setdefault((a, h), Series([]))
    info = {'shards': len(files), 'rows_read': total, 'rows_skipped': skipped, 'rows_ignored_other_coin_or_h': ignored,
            'rows_kept': len(kept), 'days': len(want),
            'kept_by_coin_h': {'%s%d' % (a, h): len(series[(a, h)].t0) for a in COINS for h in HORIZONS}}
    return Calls(series, sha.hexdigest(), info)


# ---------------------------------------------------------------- step 2: the history files

def open_text(path):
    return open(path, encoding='utf8')


def list_days(root, series, day_from, day_to_plus, lister=os.listdir):
    """({day number: path} of the plain day files, set of day numbers present only in compact form) for days in [day_from, day_to_plus]."""
    d = os.path.join(root, series)
    try:
        names = lister(d)
    except OSError:
        return {}, set()
    plain, compact = {}, set()
    for n in names:
        m = DAY_FILE.match(n)
        if m:
            k = day_number(m.group(1))
            if day_from <= k <= day_to_plus:
                plain[k] = os.path.join(d, n)
        elif n.endswith('.jsonl.mdc') and re.match(r'^\d{4}-\d{2}-\d{2}\.', n):
            k = day_number(n[:10])
            if day_from <= k <= day_to_plus:
                compact.add(k)
    return plain, compact - set(plain)


def _lines(path, opener):
    with opener(path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                m = json.loads(line)
            except ValueError:
                yield None
                continue
            yield m if isinstance(m, dict) else None


def _close_ts(m):
    c = m.get('closeTime')
    if isinstance(c, bool) or not isinstance(c, (int, float)) or c != c:
        return None
    return int(round(c / 1000.0))


def _result(m):
    r = m.get('result')
    return r if r in ('yes', 'no') else None


def _strike(m):
    v = m.get('strike')
    try:
        if v is not None and not isinstance(v, bool):
            return float(v)
    except (TypeError, ValueError):
        pass
    t = STRIKE_TAIL.search(str(m.get('ticker') or ''))
    return float(t.group(1)) if t else None


def quote_two_sided(q):
    """(bid close, ask close) of a normalized candle when two-sided (0 < bid < ask < 1), else None; the scorer's own rule."""
    if q is None:
        return None
    bid, ask = q[onetest.BID_CLOSE], q[onetest.ASK_CLOSE]
    if bid is None or ask is None or not (0 < bid < ask < 1):
        return None
    return bid, ask


def pick_strike(books, t0):
    """The strike ladder at T0: books = [(strike, ticker, result, book)]. Returns (chosen item or None, two-sided count, 2 x |mid - 50c|
    of the chosen in whole cents). Nearest 50c on the YES mid at T0 among two-sided strikes; a tie goes to the lower strike."""
    best, n2 = None, 0
    for it in books:
        q = quote_two_sided(it[3].get(t0))
        if q is None:
            continue
        n2 += 1
        dist = abs(int(round(q[0] * 100)) + int(round(q[1] * 100)) - 100)
        key = (dist, it[0])
        if best is None or key < best[0]:
            best = (key, it)
    if best is None:
        return None, 0, None
    return best[1], n2, best[0][0]


class Joiner:
    def __init__(self, calls, opener=open_text):
        self.calls, self.opener = calls, opener
        self.bundles = []
        self.seen = set()
        self.cnt = collections.Counter()
        self.strikes_per_event = []
        self.two_sided_per_call = []
        self.missing = {}                      # (coin, kind) -> set of day numbers without a plain day file
        self.stats = collections.Counter()

    def _entry(self, ticker, coin, kind, close, t0, d):
        return {'id': ticker, 'coin': coin, 'kind': kind, 'close_ts': close, 'side': 'yes' if d == 1 else 'no', 't0': t0}

    def _score(self, entry, book, result, cache):
        b = onetest.score_entry(entry, book, result)
        # The minute items of one contract and side do not depend on the entry, so they are shared to keep memory small.
        b['mins'] = cache.setdefault(entry['side'], b['mins'])
        self.bundles.append(b)

    def m15_market(self, coin, m):
        series = self.calls.series[(coin, 15)]
        ticker, close = str(m.get('ticker') or ''), _close_ts(m)
        if close is None or not ticker:
            self.stats['market_without_ticker_or_close'] += 1
            return
        lo = bisect.bisect_left(series.t0, close - CLOSE_AFTER_S['15m'][1])
        hi = bisect.bisect_right(series.t0, close - CLOSE_AFTER_S['15m'][0])
        if hi <= lo:
            return
        if (coin, ticker) in self.seen:
            self.stats['duplicate_ticker_skipped'] += 1
            return
        self.seen.add((coin, ticker))
        book = onetest.index(onetest.norm_hist_candles(m.get('candles')))
        res, cache = _result(m), {}
        for i in range(lo, hi):
            if series.state[i]:
                self.stats['call_matched_by_two_contracts'] += 1
                continue
            series.state[i] = 1
            self._score(self._entry(ticker, coin, '15m', close, series.t0[i], series.dir[i]), book, res, cache)

    def hourly_group(self, coin, close, items):
        """items = [(strike, ticker, result, book)] of one event closing at `close`."""
        series = self.calls.series[(coin, 60)]
        lo = bisect.bisect_left(series.t0, close - CLOSE_AFTER_S['hourly'][1])
        hi = bisect.bisect_right(series.t0, close - CLOSE_AFTER_S['hourly'][0])
        if hi <= lo:
            return
        self.strikes_per_event.append(len(items))
        caches = {}
        for i in range(lo, hi):
            if series.state[i]:
                self.stats['call_matched_by_two_events'] += 1
                continue
            t0 = series.t0[i]
            it, n2, dist = pick_strike(items, t0)
            self.two_sided_per_call.append(n2)
            if it is None:
                series.state[i] = 2
                continue
            series.state[i] = 1
            series.in_band[i] = 1 if dist <= BAND_X2 else 0
            self._score(self._entry(it[1], coin, 'hourly', close, t0, series.dir[i]), it[3], it[2], caches.setdefault(it[1], {}))

    def hourly_day(self, coin, path):
        series = self.calls.series[(coin, 60)]
        groups = collections.OrderedDict()
        for m in _lines(path, self.opener):
            if m is None:
                self.stats['unreadable_history_line'] += 1
                continue
            ticker, close = str(m.get('ticker') or ''), _close_ts(m)
            if close is None or not ticker:
                self.stats['market_without_ticker_or_close'] += 1
                continue
            if bisect.bisect_right(series.t0, close - CLOSE_AFTER_S['hourly'][0]) <= \
                    bisect.bisect_left(series.t0, close - CLOSE_AFTER_S['hourly'][1]):
                continue                        # no call could enter this event: its candles are not even normalized
            if (coin, ticker) in self.seen:
                self.stats['duplicate_ticker_skipped'] += 1
                continue
            self.seen.add((coin, ticker))
            strike = _strike(m)
            if strike is None:
                self.stats['hourly_market_without_strike'] += 1
                continue
            ev = str(m.get('event') or ticker.rsplit('-', 1)[0])
            groups.setdefault((ev, close), []).append(
                (strike, ticker, _result(m), onetest.index(onetest.norm_hist_candles(m.get('candles')))))
        for (ev, close), items in groups.items():
            self.hourly_group(coin, close, items)

    def run_history(self, m15_dir, hourly_dir, day_from, day_to):
        last = day_to + 1                          # a contract closing just after midnight sits in the next day's file
        for coin in COINS:
            for kind, root, name in (('15m', m15_dir, 'KX%s15M' % coin), ('hourly', hourly_dir, 'KX%sD' % coin)):
                plain, compact = list_days(root, name, day_from, last)
                self.missing[(coin, kind)] = {d for d in range(day_from, last + 1) if d not in plain}
                self.stats['%s_%s_days_found' % (coin, kind)] = len([d for d in plain if d <= day_to])
                self.stats['%s_%s_days_missing' % (coin, kind)] = len([d for d in range(day_from, day_to + 1) if d not in plain])
                self.stats['%s_%s_days_compact_only' % (coin, kind)] = len([d for d in compact if d <= day_to])
                for d in sorted(plain):
                    if kind == '15m':
                        for m in _lines(plain[d], self.opener):
                            if m is None:
                                self.stats['unreadable_history_line'] += 1
                            else:
                                self.m15_market(coin, m)
                    else:
                        self.hourly_day(coin, plain[d])

    # ---- counts

    def entry_counts(self):
        """Calls, entries, no contract, no strike by kind and coin and by kind and month; no ticker, no time of one call."""
        by_kc, by_km = collections.defaultdict(collections.Counter), collections.defaultdict(collections.Counter)
        for (coin, h), s in sorted(self.calls.series.items()):
            kind = KIND[h]
            lo_hi = CLOSE_AFTER_S[kind]
            miss = self.missing.get((coin, kind), set())
            for i, t0 in enumerate(s.t0):
                st = s.state[i]
                names = ['calls']
                if st == 1:
                    names.append('entries')
                elif st == 2:
                    names.append('no_strike')
                else:
                    names.append('no_contract')
                    if (t0 + lo_hi[0]) // 86400 in miss or (t0 + lo_hi[1]) // 86400 in miss:
                        names.append('no_contract_day_file_missing')
                for n in names:
                    by_kc['%s %s' % (kind, coin)][n] += 1
                    by_km['%s %s' % (kind, _month(t0))][n] += 1
        fix = lambda d: {k: dict(sorted(v.items())) for k, v in sorted(d.items())}
        return {'by_kind_coin': fix(by_kc), 'by_kind_month': fix(by_km)}

    def hourly_availability(self):
        """The counts behind 'the hourly half is available', and the answer under the literal reading in the module docstring."""
        n = events_with_calls = entered = in_band = 0
        for coin in COINS:
            s = self.calls.series[(coin, 60)]
            n += len(s.t0)
            entered += sum(1 for x in s.state if x == 1)
            in_band += sum(s.in_band)
        share = in_band / n if n else 0.0
        med = lambda xs: statistics.median(xs) if xs else None
        return {'calls_60m': n, 'calls_with_a_two_sided_strike': entered, 'calls_with_a_strike_mid_10c_to_90c': in_band,
                'share_with_a_strike_mid_10c_to_90c': round(share, 4), 'rule': 'available when that share is at least %.2f' % AVAILABLE_SHARE,
                'events_with_calls_seen': len(self.strikes_per_event),
                'strikes_per_event_median': med(self.strikes_per_event), 'strikes_per_event_max': max(self.strikes_per_event, default=None),
                'two_sided_strikes_per_call_median': med(self.two_sided_per_call),
                'two_sided_strikes_per_call_max': max(self.two_sided_per_call, default=None),
                'available': bool(n and share >= AVAILABLE_SHARE)}


# ---------------------------------------------------------------- books on these days

def books_by_month_and_kind(bundles):
    """The share of entries whose called side is not scored for a one-sided or missing quote, by month and kind (all entries)."""
    out = collections.defaultdict(collections.Counter)
    for b in bundles:
        key = '%s %s' % (b['kind'], month_key(b))
        c = b['called']
        out[key]['entries'] += 1
        if not c['scored'] and c['reason'] in ONE_SIDED:
            out[key]['one_sided_or_missing'] += 1
        elif not c['scored']:
            out[key]['other_not_scored'] += 1
    res = {}
    for k, c in sorted(out.items()):
        res[k] = {'entries': c['entries'], 'one_sided_or_missing': c['one_sided_or_missing'],
                  'share_one_sided_or_missing': round(c['one_sided_or_missing'] / c['entries'], 4), 'other_not_scored': c['other_not_scored']}
    return res


# ---------------------------------------------------------------- the run

LEGEND = {
    'order': 'the calls hash is printed before any history file is listed or opened',
    'hash': 'sha256 over the kept rows sorted by asset, h, t0: json with sorted keys, compact separators, one per line',
    'entries': 'a 15m call enters the contract closing 300 to 840 s after T0; a 60m call the hourly event closing 600 to 3300 s after T0, on the two-sided strike with the YES mid nearest 50c (a tie: the lower strike)',
    'no_contract': 'no contract (or no hourly event) closes in the range; no_contract_day_file_missing says how many of them have a history day file missing for that range',
    'month': 'the split by UTC month of T0 (the part A week split is replaced)',
    'books': 'share of entries whose called side is not scored for a one-sided or missing quote, by kind and month',
    'not_replayed': 'the lane\'s stateful gates are not replayed; the primary count (first scored entry per contract) is the closest stateless match',
    'passes': onetest.LEGEND['passes'],
    'G_random_side': onetest.LEGEND['G_random_side'],
    'same_side_random_minute': onetest.LEGEND['same_side_random_minute'],
    'usual_side': onetest.LEGEND['usual_side'],
    'sold_1m': onetest.LEGEND['sold_1m'],
    'settlement': onetest.LEGEND['settlement'],
    'cells': onetest.LEGEND['cells'],
}


def run(calls_dir, m15_dir, hourly_dir, from_text, to_text, log=print, opener=open_text, shard_reader=_read_shard):
    day_from, day_to = day_number(from_text), day_number(to_text)
    if day_to < day_from:
        raise JoinError('--to is before --from')
    calls = load_calls(calls_dir, day_from, day_to, shard_reader)
    emit(log, 'calls', {'sha256': calls.digest, 'from': from_text, 'to': to_text, **calls.info})
    # Nothing of Kalshi has been listed or opened before this line.
    j = Joiner(calls, opener)
    j.run_history(m15_dir, hourly_dir, day_from, day_to)
    counts = j.entry_counts()
    avail = j.hourly_availability()
    emit(log, 'history', dict(sorted(j.stats.items())))
    emit(log, 'entries.by_kind_coin', counts['by_kind_coin'])
    emit(log, 'entries.by_kind_month', counts['by_kind_month'])
    emit(log, 'hourly_availability', avail)
    if not avail['available']:
        emit(log, 'hourly', {'status': 'not available', 'reason': 'the hourly history does not hold strikes near the money (counts in hourly_availability); nothing replaces it'})
    bundles = [b for b in j.bundles if avail['available'] or b['kind'] != 'hourly']
    # Amendment 1: hours = UTC days with at least one entry x 24 (onetest.analyse does that when hours is None). Both numbers are printed.
    calendar_days = day_to - day_from + 1
    days_with_entry = onetest.days_covered(bundles)
    emit(log, 'days', {'calendar_days': calendar_days, 'days_with_an_entry': days_with_entry, 'hours_used': days_with_entry * 24,
                       'rule': 'hours for dollars an hour = UTC days with at least one analysed entry x 24 (PREREG part 1, amendment 1)'})
    hours = days_with_entry * 24
    res = {'part': 'B', 'sha256': calls.digest, 'from': from_text, 'to': to_text, 'hours': hours, 'calendar_days': calendar_days,
           'days_with_an_entry': days_with_entry, 'calls': calls.info,
           'history': dict(sorted(j.stats.items())), 'entries': counts, 'hourly_availability': avail,
           'hourly_in_analysis': bool(avail['available']), 'entries_analysed': len(bundles), 'analysis': None}
    if bundles:
        res['analysis'] = _month_analysis(bundles)
    # The books line covers every entry, also the hourly ones when the hourly half is left out of the analysis.
    res['books'] = books_by_month_and_kind(j.bundles) if j.bundles else {}
    # Held-out read: when the hourly half is left out, its own analysis is still computed and kept in --out only (never printed), so
    # a later decision on the availability threshold needs no second read.
    hourly_only = [b for b in j.bundles if b['kind'] == 'hourly']
    if hourly_only and not avail['available']:
        res['hourly_only_analysis_not_printed'] = _month_analysis(hourly_only)
    print_analysis(res, log)
    return res


def _month_analysis(bundles):
    """onetest.analyse with the month key where part A passed its week function; hours = days with an entry x 24."""
    a = onetest.analyse(bundles, week_fn=month_key, hours=None)
    for c in ('primary', 'secondary'):
        a[c]['splits']['month'] = a[c]['splits'].pop('week')
    return a


def print_analysis(res, log=print):
    emit(log, 'books', res['books'])
    emit(log, 'legend', LEGEND)
    a = res['analysis']
    if a is None:
        emit(log, 'analysis', {'status': 'no entries to score'})
        return
    emit(log, 'head', {k: a[k] for k in ('hours', 'days', 'contracts', 'contracts_with_a_scored_entry', 'contracts_without_a_scored_entry')})
    emit(log, 'verdict', a['verdict'])
    for c in ('primary', 'secondary'):
        s = a[c]
        emit(log, c + '.rates', {k: v for k, v in s.items() if k not in ('money', 'splits', 'not_scored')})
        emit(log, c + '.not_scored', s['not_scored'])
        emit(log, c + '.money', s['money'])
        for name, v in s['splits'].items():
            emit(log, '%s.split.%s' % (c, name), v)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--calls', required=True, help='folder holding calls-*.jsonl.gz')
    ap.add_argument('--m15', required=True, help='folder holding KXBTC15M/ and KXETH15M/ day files')
    ap.add_argument('--hourly', required=True, help='folder holding KXBTCD/ and KXETHD/ day files')
    ap.add_argument('--from', dest='day_from', required=True)
    ap.add_argument('--to', dest='day_to', required=True)
    ap.add_argument('--out', required=True)
    a = ap.parse_args(argv)
    res = run(a.calls, a.m15, a.hourly, a.day_from, a.day_to)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, 'w', encoding='utf-8') as fh:
        json.dump(res, fh, indent=1)
    return 0


if __name__ == '__main__':
    sys.exit(main())
