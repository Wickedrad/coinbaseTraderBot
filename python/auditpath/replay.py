"""Part B of the audit path (research/audit_path/PREREG-AP.md): the curve calls replayed over recorded days, calls only.

The deployed reader (python/heat_reader: config defaults, Engine, Tables, read_coin, LongStates, window 3000, the deployed
pack in research/oracle_heat/latest) is run at every minute close on Binance one-minute bars, and the lane's own rule
(readHeatCalls and decideCall in bot/heat/heatLane.ts, top 10) is applied to the rows the reader publishes at that close.
Nothing here reads a Kalshi file or a price. The output is a private calls table, one row per decided call.

    cd python && python3 -m auditpath.replay calls --coin BTC --bars <1m.csv> --from 2026-08-01 --to 2026-08-24 \
        --out calls-BTC-2026-08-01_2026-08-24.jsonl.gz [--limit-minutes N] [--decider ts|py]

Minutes. The replayed closes are every minute close T with --from 00:00 UTC <= T <= --to 23:59 UTC (both days whole;
1,440 closes a day). The close T reads the bars that opened before T and none after it (T is the open time of the bar
that would come next). A close with no bar for the minute just before it is not read (the live reader gives no reading
then either) and is counted. "Through 23:59" is read literally as the close time T <= 23:59, so the last call of a
day is made at 23:59 on the bar that opened at 23:58 (the bar closing at 00:00 of the next day is not read). The call's time t0 is T in epoch seconds. Bars before --from are warm-up only.

The lane. The reader writes its file at T and the lane ticks about 3 s later, so every row published at T has barClose
T and is inside the 45 s lag. The replay builds the HeatCallsFile the reader would write (written 3 s after T), hands it
to the lane's own code through research/audit_path/decideCalls.ts (readHeatCalls, run with `node --import tsx`), and
keeps the decided call per coin and horizon. A pair that calls against the single it refines is skipped by the lane
(HEAT_PAIR_CONFLICT=skip): it stays in the table with skip set, so the join MUST drop every row with skip set (PREREG's decided call is the lane's own rule, which makes no trade there). `--decider py` runs a line
by line Python port of the same rule instead (kept equal to the TypeScript by a parity test); the default is the original.

Shards. Each shard must start at an hourly boundary (a whole day does) because the 60-minute readings are read once an
hour and cached, as in the live reader; then any minute gives the same rows whichever shard reads it.

Only aggregates are printed ("AUDITPATH replay {json}"). The table goes to the --out file, which is private.
"""
import argparse
import gzip
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from collections import Counter
from datetime import datetime, timezone
from functools import cmp_to_key

import numpy as np

MIN_MS = 60_000
HOUR_MS = 60 * MIN_MS
DAY_MS = 24 * HOUR_MS
HORIZONS = (15, 60)
COINS = ('BTC', 'ETH', 'SOL', 'XRP')           # never DOGE
WRITE_LAG_MS = 3_000                           # the reader writes its file this long after the minute closes
TICK_LAG_MS = 6_000                            # the lane's tick is about 3 s after that
HERE = os.path.dirname(os.path.abspath(__file__))
PYTHON_DIR = os.path.dirname(HERE)
REPO_DIR = os.path.dirname(PYTHON_DIR)
DECIDE_TS = os.path.join(REPO_DIR, 'research', 'audit_path', 'decideCalls.ts')
BAR_COLS = ('ts', 'o', 'h', 'l', 'c', 'v', 'tb')

# The lane's deployed defaults (bot/config.ts, HEAT_*) that decide a call. decideCalls.ts holds the same numbers.
LANE = {'topN': 10, 'maxAgeSec': 90, 'entryLagSec': 45, 'pairConflict': 'skip', 'horizons': HORIZONS}


class ReplayError(Exception):
    """A run that cannot be faithful: the message says why in plain text."""


# ---- minutes and bars ----

def parse_day(text: str) -> int:
    """Midnight UTC of a YYYY-MM-DD date, in ms."""
    try:
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', text):
            raise ValueError(text)
        d = datetime.strptime(text, '%Y-%m-%d').replace(tzinfo=timezone.utc)
    except ValueError:
        raise ReplayError(f'{text!r} is not a YYYY-MM-DD date') from None
    return int(d.timestamp() * 1000)


def closes_for(from_ms: int, to_day_ms: int, limit: int = 0) -> list:
    """The minute closes T of a shard, oldest first: from_ms (00:00 of the first day) through 23:59 of the last day
    (to_day_ms is that day's midnight), both inclusive. limit > 0 keeps only the first `limit` of them. The shard must
    start at an hourly boundary, so the cached 60-minute readings start fresh exactly as they do at any hour's first
    minute."""
    if from_ms % HOUR_MS:
        raise ReplayError('a shard must start at an hourly boundary')
    if to_day_ms < from_ms:
        raise ReplayError('--to is before --from')
    last = to_day_ms + DAY_MS - MIN_MS
    out = list(range(from_ms, last + 1, MIN_MS))
    return out[:limit] if limit > 0 else out


def load_bars(path: str, lo_ms: int, hi_ms: int) -> np.ndarray:
    """The (n, 7) float array of the minutes with lo_ms <= ts < hi_ms from a Binance one-minute CSV (header
    ts,o,h,l,c,v,tb; ts = the minute's open in ms UTC), oldest first, one row per minute. This is the array the live
    reader's minute cache holds."""
    try:
        import pandas as pd
        df = pd.read_csv(path, usecols=list(BAR_COLS), dtype={'ts': np.int64})
        arr = df[list(BAR_COLS)].to_numpy(dtype=np.float64)
    except ImportError:
        arr = np.loadtxt(path, delimiter=',', skiprows=1, usecols=range(len(BAR_COLS)), dtype=np.float64, ndmin=2)
    if arr.size == 0:
        raise ReplayError('the bars file holds no rows')
    if arr[0, 0] < 1e11:
        raise ReplayError('the bars file does not hold ts in ms')
    arr = arr[(arr[:, 0] >= lo_ms) & (arr[:, 0] < hi_ms)]
    order = np.argsort(arr[:, 0], kind='stable')
    arr = arr[order]
    if len(arr):
        keep = np.concatenate(([True], np.diff(arr[:, 0]) > 0))
        arr = arr[keep]
    return arr


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


# ---- the lane's rule, as a Python port (bot/heat/heatLane.ts, line by line) ----

KIND_ORDER = {'single': 0, 'pair': 1, 'triple': 2}


def _cmp(a, b):
    return -1 if a < b else (1 if a > b else 0)


def hotter(a: dict, b: dict) -> float:
    """Negative when a is hotter: the lower rank, then the higher heat, then the key."""
    return (a['rank'] - b['rank']) or (b['heat'] - a['heat']) or _cmp(a['key'], b['key'])


def one_row_per_event(rows: list) -> list:
    seen, out = set(), []
    for r in sorted(rows, key=cmp_to_key(hotter)):
        names = [r['key']] + list(r.get('aliases') or [])
        if any(n in seen for n in names):
            continue
        seen.update(names)
        out.append(r)
    return out


def finer_then_heat(a: dict, b: dict) -> float:
    return (KIND_ORDER[b['kind']] - KIND_ORDER[a['kind']]) or (b['heat'] - a['heat']) or hotter(a, b)


def decide_call(asset: str, h: int, firing: list, top_n: int = 0):
    """decideCall of bot/heat/heatLane.ts. Returns {'asset','h','row','fired','against'[,'single']} or None."""
    events = one_row_per_event(firing)

    def in_batch(r):
        return top_n <= 0 or r['rank'] <= top_n

    single = next((r for r in events if r['kind'] == 'single' and in_batch(r)), None)
    own = set([single['key']] + list(single.get('aliases') or [])) if single else set()

    def refines(r):
        return r['kind'] != 'single' and r.get('trig') is not None and r['trig'] in own

    refiners = sorted([r for r in events if refines(r)], key=cmp_to_key(finer_then_heat))
    refiner = refiners[0] if refiners else None
    lead = dict(refiner, rank=min(single['rank'], refiner['rank'])) if single and refiner else single
    loose = [r for r in events if r['kind'] != 'single' and not refines(r) and in_batch(r)]
    row = lead
    for r in loose:
        if row is None or hotter(r, row) < 0:
            row = r
    if row is None:
        return None
    if row is not lead:
        pick = row
        finer = sorted([r for r in loose if KIND_ORDER[r['kind']] > KIND_ORDER[pick['kind']] and r.get('trig') is not None
                        and r['trig'] == pick.get('trig')], key=cmp_to_key(finer_then_heat))
        row = finer[0] if finer else pick
    chosen = row
    counted = [r for r in events if in_batch(r) or refines(r)]
    out = {'asset': asset, 'h': h, 'row': chosen, 'fired': len(counted), 'against': sum(1 for r in counted if r['dir'] != chosen['dir'])}
    if chosen is lead and refiner:
        out['single'] = single
    return out


def _clean(r: dict) -> dict:
    """The lane reads an empty trig as none (heatSource.ts checkRow)."""
    return {k: v for k, v in r.items() if not (k == 'trig' and v in ('', None))}


def lane_decide_py(now: int, file: dict) -> dict:
    """readHeatCalls of bot/heat/heatLane.ts for a coin per horizon, with the deployed settings: {'fresh', 'unfit'}."""
    fresh, unfit = [], []
    if now - file['writtenAt'] > 2 * LANE['maxAgeSec'] * 1000:
        return {'fresh': fresh, 'unfit': unfit}
    lag_ms = LANE['entryLagSec'] * 1000
    for asset in COINS:
        coin = (file.get('coins') or {}).get(asset)
        if not coin:
            continue
        why = None
        if not coin['ok']:
            why = 'reader not ok' + (f': {coin["why"]}' if coin.get('why') else '')
        elif now - coin['asOf'] > LANE['maxAgeSec'] * 1000:
            why = 'calls stale'
        for h in LANE['horizons']:
            firing = [_clean(r) for r in (coin.get('calls') or []) if r['h'] == h and 0 <= now - r['barClose'] <= lag_ms]
            call = decide_call(asset, h, firing, LANE['topN'])
            if not call:
                continue
            single = call.get('single')
            conflict = bool(single and single['dir'] != call['row']['dir'] and LANE['pairConflict'] != 'pair')
            reason = why or ('pair against single' if conflict else None)
            if reason:
                unfit.append(dict(call, why=reason))
            else:
                fresh.append(call)
    return {'fresh': fresh, 'unfit': unfit}


# ---- the reader, minute by minute ----

def reader_file(tables, coin: str, coin_obj: dict, t_ms: int) -> dict:
    """The HeatCallsFile the reader writes at the close t_ms (3 s later), holding this coin only."""
    return {'v': 1, 'source': 'oracle-heat', 'run': tables.run, 'packSha': tables.pack_sha, 'writtenAt': int(t_ms + WRITE_LAG_MS),
            'coins': {coin: coin_obj}}


def read_minutes(read, rows: np.ndarray, closes: list, coin: str, tables, window: int, long, stats: Counter, on_file) -> None:
    """Read each close in time order with `read` (the reader's read_coin) and hand the file the reader would write to
    on_file(t_ms, file) when the coin is ok and a row of a traded horizon fired. rows: all bars loaded, oldest first.
    The reader sees rows[:i1] only: the bars that opened before the close, none after it."""
    ts = rows[:, 0]
    table = tables.coins[coin]
    for t in closes:
        i1 = int(np.searchsorted(ts, t))
        if i1 == 0 or ts[i1 - 1] != t - MIN_MS:
            stats['minutes_missing_bar'] += 1
            continue
        try:
            coin_obj, _facts = read(table, rows[:i1], t, window, long)
        except Exception as e:                                # the live loop marks the coin not ok and goes on
            stats['engine_errors'] += 1
            stats[f'error:{type(e).__name__}'] += 1
            continue
        if not coin_obj['ok']:
            stats['minutes_not_ok'] += 1
            stats['why:' + str(coin_obj.get('why', ''))[:48]] += 1
            continue
        stats['minutes_read'] += 1
        calls = [c for c in coin_obj['calls'] if c['h'] in HORIZONS]
        stats['rows_fired'] += len(calls)
        if calls:
            on_file(t, reader_file(tables, coin, dict(coin_obj, calls=calls), t))


# ---- the lane, through the original TypeScript or the port ----

def decide_ts(lines: list, node_cwd: str) -> list:
    """Run research/audit_path/decideCalls.ts (the lane's own readHeatCalls) over the input lines (JSON text of
    {id, now, file})."""
    if not lines:
        return []
    with tempfile.TemporaryDirectory() as d:
        src, dst = os.path.join(d, 'in.jsonl'), os.path.join(d, 'out.jsonl')
        with open(src, 'w') as f:
            for x in lines:
                f.write(x + '\n')
        p = subprocess.run(['node', '--import', 'tsx', DECIDE_TS, src, dst], cwd=node_cwd, capture_output=True, text=True)
        if p.returncode != 0:
            raise ReplayError(f'decideCalls.ts failed with exit code {p.returncode} (its error text is not printed: it may quote call rows)')
        with open(dst) as f:
            out = [json.loads(x) for x in f if x.strip()]
    if len(out) != len(lines):
        raise ReplayError('decideCalls.ts answered a different number of lines')
    return out


def decide_lines(lines: list, decider: str, node_cwd: str) -> list:
    if decider == 'ts':
        return decide_ts(lines, node_cwd)
    parsed = [json.loads(x) for x in lines]
    return [dict(id=x['id'], **lane_decide_py(x['now'], x['file'])) for x in parsed]


def table_row(t_ms: int, d: dict, skip=None) -> dict:
    """One row of the calls table from a decided call of the lane. Nothing about prices."""
    r, s = d['row'], d.get('single')
    return {'asset': d['asset'], 'h': d['h'], 't0': t_ms // 1000, 'dir': r['dir'], 'key': r['key'], 'kind': r['kind'],
            'rank': r['rank'], 'of': r['of'], 'fired': d['fired'], 'against': d['against'], 'tf': r['tf'], 'heat': r['heat'],
            'share': r['share'], 'odds': r['odds'], 'trig': r.get('trig'), 'single_key': s['key'] if s else None,
            'single_dir': s['dir'] if s else None, 'skip': skip}


def rows_of(answer: dict, t_ms: int) -> list:
    """The table rows of one lane answer: the calls the lane would act on, then the ones it skips (marked), by horizon."""
    if answer.get('error'):
        raise ReplayError(f'the lane refused the reader file at {t_ms} (its error text is not printed: it may quote call rows)')
    out = [table_row(t_ms, d) for d in answer['fresh']]
    out += [table_row(t_ms, d, 'pair_against_single' if str(d.get('why', '')).startswith('pair against single') else str(d.get('why'))[:60])
            for d in answer['unfit']]
    return sorted(out, key=lambda x: (x['h'], x['asset']))


def write_table(path: str, rows: list) -> str:
    """Write the rows as gzip JSON lines the same way every time (no file time in the header), via a temp file."""
    tmp = path + '.tmp'
    with open(tmp, 'wb') as raw:
        with gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0, compresslevel=6) as gz:
            for r in rows:
                gz.write((json.dumps(r, separators=(',', ':'), allow_nan=False) + '\n').encode())
    os.replace(tmp, path)
    return sha256_file(path)


def aggregates(rows: list) -> dict:
    by_h = {}
    for h in HORIZONS:
        mine = [r for r in rows if r['h'] == h]
        live = [r for r in mine if not r['skip']]
        multi = [r for r in live if r['kind'] != 'single']
        by_h[str(h)] = {'decided': len(live), 'up': sum(1 for r in live if r['dir'] > 0), 'down': sum(1 for r in live if r['dir'] < 0),
                        'skipped_pair_against_single': len(mine) - len(live), 'by_pair_or_triple': len(multi),
                        'share_pair_or_triple': round(len(multi) / len(live), 4) if live else None}
    return by_h


# ---- the run ----

def run_calls(a) -> int:
    from heat_reader import config
    from heat_reader.engine import Engine
    from heat_reader.pack import Tables
    from heat_reader.reader import LongStates, read_coin

    coin = a.coin.upper()
    if coin not in COINS:
        raise ReplayError(f'{a.coin!r} is not a coin of this project (BTC, ETH, SOL, XRP; never DOGE)')
    from_ms, to_day = parse_day(a.from_), parse_day(a.to)
    closes = closes_for(from_ms, to_day, a.limit_minutes)
    argv = ['--window-bars', str(a.window)] + (['--pack-dir', a.pack_dir] if a.pack_dir else [])
    s = config.load(argv, env={})                                   # the deployed defaults, whatever the environment says
    engine = Engine(s.oracle_path)
    tables = Tables(s.pack_dir, s.assets, s.run, s.max_rank, s.clock_pack, s.perp_packs)
    tables.refresh()
    if tables.problem or tables.coins.get(coin) is None or tables.coins[coin].problem:
        raise ReplayError(f'the pack cannot be used: {tables.problem or tables.coins[coin].problem}')
    for t in tables.coins.values():
        t.check_edges(engine.zone_levels, engine.zone_states)
    table = tables.coins[coin]
    if table.problem:
        raise ReplayError(f'the pack cannot be used: {table.problem}')
    need_ms = engine.need_minutes(s.window_bars, table.tfs) * MIN_MS
    lo_ms = from_ms - need_ms - HOUR_MS
    rows = load_bars(a.bars, lo_ms, closes[-1] + MIN_MS)
    if not len(rows) or rows[0, 0] > from_ms - need_ms:
        raise ReplayError(f'the bars start too late for the warm-up: {need_ms // DAY_MS + 1} days before {a.from_} are needed')
    stats = Counter()
    long = LongStates()
    firing_ids, firing_lines = [], []

    def read(tb, rws, t, window, lg):
        return read_coin(engine, tb, tables.top, rws, t, window, lg)

    def on_file(t, f):
        firing_ids.append(t)
        firing_lines.append(json.dumps({'id': t, 'now': t + TICK_LAG_MS, 'file': f}, separators=(',', ':'), allow_nan=False))

    t0 = time.monotonic()
    read_minutes(read, rows, closes, coin, tables, s.window_bars, long, stats, on_file)
    read_sec = time.monotonic() - t0
    t1 = time.monotonic()
    answers = decide_lines(firing_lines, a.decider, a.node_cwd or REPO_DIR)
    decide_sec = time.monotonic() - t1
    out_rows = []
    for t, ans in zip(firing_ids, answers):
        if ans['id'] != t:
            raise ReplayError('the lane answered lines out of order')
        out_rows += rows_of(ans, t)
    out_sha = write_table(a.out, out_rows)
    n = len(closes)
    agg = {'coin': coin, 'from': a.from_, 'to': a.to, 'minutes_planned': n, 'minutes_read': stats['minutes_read'],
           'minutes_missing_bar': stats['minutes_missing_bar'], 'minutes_not_ok': stats['minutes_not_ok'],
           'engine_errors': stats['engine_errors'], 'minutes_with_fired_rows': len(firing_lines), 'rows_fired_h15_h60': stats['rows_fired'],
           'calls': aggregates(out_rows), 'decider': a.decider, 'window_bars': s.window_bars,
           'sec_per_coin_minute': round((read_sec + decide_sec) / n, 4) if n else None, 'read_sec': round(read_sec, 1),
           'decide_sec': round(decide_sec, 1), 'warmup_days': round(need_ms / DAY_MS, 2), 'bars_loaded': int(len(rows)),
           'run': tables.run, 'pack_sha256': {k: v.get('sha256') for k, v in tables.files.items()},
           'table_sha256': table.table_sha, 'out_rows': len(out_rows), 'out_sha256': out_sha}
    errs = sorted(((v, k[6:]) for k, v in stats.items() if k.startswith('error:')), reverse=True)[:3]
    if errs:
        agg['engine_error_types'] = [{'n': v, 'type': k} for v, k in errs]
    why = sorted(((v, k[4:]) for k, v in stats.items() if k.startswith('why:')), reverse=True)[:3]
    if why:
        agg['not_ok_reasons'] = [{'n': v, 'why': k} for v, k in why]
    print('AUDITPATH replay ' + json.dumps(agg, separators=(',', ':'), allow_nan=False), flush=True)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog='python3 -m auditpath.replay', description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    c = sub.add_parser('calls', help='the decided calls of one coin over whole days')
    c.add_argument('--coin', required=True)
    c.add_argument('--bars', required=True, help='Binance one-minute CSV: ts,o,h,l,c,v,tb')
    c.add_argument('--from', dest='from_', required=True, help='first day, YYYY-MM-DD (00:00 UTC)')
    c.add_argument('--to', required=True, help='last day, YYYY-MM-DD (through 23:59 UTC)')
    c.add_argument('--out', required=True, help='calls-<COIN>-<from>_<to>.jsonl.gz')
    c.add_argument('--limit-minutes', type=int, default=0, help='smoke run: only the first N closes')
    c.add_argument('--decider', choices=('ts', 'py'), default='ts')
    c.add_argument('--window', type=int, default=3000, help='the reader window (the deployed value is 3000; tests only)')
    c.add_argument('--pack-dir', default='', help='the pack folder (default: research/oracle_heat/latest; tests only)')
    c.add_argument('--node-cwd', default='', help='the folder `node --import tsx` is run from (default: the repository)')
    a = ap.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        return run_calls(a)
    except ReplayError as e:
        print(f'AUDITPATH replay {json.dumps({"error": str(e)[:300]})}', flush=True)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
