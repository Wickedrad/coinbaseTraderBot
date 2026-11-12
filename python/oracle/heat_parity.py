"""Parity of the live reader (oracle.heat_live) with the heat tables' engine, on real history.

  python3 -m oracle.heat_parity --asset BTC --csv <1m.csv, cut at HEAT_END> --meta <the coin's meta.json> --dom <dir>
                                --out <dir> [--days 3] [--window 3000] [--procs 4]

1. Whole history, the engine's way: every reading's level codes on 2020-2025 with the zone edges taken from split A.
   The edges must equal the ones stored in the coin's meta.json (a fingerprint of every value series: if they agree,
   this recomputation is the table's).
2. The fixture: for the last `days` days of 2025, the event keys the engine fires at each minute close
   (fixture.json.gz: public price data, keys only).
3. The live reader on a window ending at sampled minutes of those days (every 5-minute close, and every 7th other
   minute), against the fixture. parity.json: how often the key sets agree, per timeframe, and which readings differ.

Reads coin minutes 2020-01-01 to 2025-12-31 only (the loader refuses a later minute). No label or return is computed.
NEVER DOGE.
"""
import argparse
import gzip
import json
import os
import time
from collections import Counter

import numpy as np

from oracle import heat, heat_live
from oracle.common import MIN

_W = {}


def split_rows(m: dict, s: str = 'A') -> tuple:
    """(lo, hi) minute rows of a split, as heat.Grid takes them."""
    a, b = heat.SPLITS[s]
    lo = max(0, int(np.ceil((a - m['t0']) / MIN)) - 1)
    hi = max(lo, min(int((b - heat.HMAX * MIN - m['t0']) // MIN), m['n']))
    return lo, hi


def _live(row: int) -> tuple:
    m, meta, dom, window = _W['m'], _W['meta'], _W['dom'], _W['window']
    a = max(0, (row + 1 - (window + 2) * 60) // 1440 * 1440)            # a UTC midnight, far enough back for the 1-hour window
    sub = {x: (None if m[x] is None else m[x][a:row + 1]) for x in ('o', 'h', 'l', 'c', 'v', 'tb', 'gap')}
    sub['t0'], sub['n'] = m['t0'] + a * MIN, row + 1 - a
    r = heat_live.active_keys(sub, meta, dom=dom, window=window)
    return row, r['closed'], r['events']


def run(asset: str, csv: str, meta_path: str, dom_dir: str, out: str, days: int = 3, window: int = heat_live.WINDOW_BARS, procs: int = 4, log=print,
        max_rows: int = None) -> dict:
    if asset.upper() == 'DOGE':
        raise SystemExit('never DOGE')
    t_start = time.time()
    os.makedirs(out, exist_ok=True)
    meta = heat_live.load_meta(meta_path)
    m = heat.load_minutes(csv)                                          # strict: refuses a minute at or after HEAT_END
    lo, hi = m['n'] - days * 1440, m['n']
    a_rows = split_rows(m, 'A')
    edges, step = meta.get('edges', {}), meta.get('price_step')
    by_row, n_read, e_same, e_diff, e_max = {}, 0, 0, [], 0.0
    for k in heat.TFS:
        R, used, _ = heat_live.tf_codes(m, k, edges=None, step=step, window=None, a_rows=a_rows)
        for name, e in used.items():
            st = edges.get(name)
            if st is not None and np.array_equal(np.asarray(e), np.asarray(st)):
                e_same += 1
            else:
                e_diff.append(name)
                if st is not None:
                    e_max = max(e_max, float(np.abs(np.asarray(e) - np.asarray(st)).max()))
        e_diff += [x for x in edges if x.startswith(f'{k}m:') and x not in used]
        for r in R:
            n_read += 1
            for row, key in heat_live.events_at(r, lo, hi):
                by_row.setdefault(row, []).append(key)
        del R
        log(f'{asset} {k}m: codes on the whole history done ({time.time() - t_start:.0f}s)')
    for r in heat.context_readings(m, dom_dir):
        for row, key in heat_live.events_at(r, lo, hi):
            by_row.setdefault(row, []).append(key)
    fixture = {'coin': asset, 'from_ms': m['t0'] + lo * MIN, 'to_ms': m['t0'] + hi * MIN, 'note': 'key = close time in ms of the minute (the entry minute opens then)',
               'table_sha256': meta.get('table_sha256'), 'minutes': {str(m['t0'] + (row + 1) * MIN): sorted(ks) for row, ks in sorted(by_row.items())}}
    with gzip.open(os.path.join(out, 'fixture.json.gz'), 'wt') as f:
        json.dump(fixture, f, separators=(',', ':'))

    import pandas as pd
    dom = {}
    for sym in ('BTC.D', 'USDT.D'):
        p = os.path.join(dom_dir, f'{sym}_1d.csv')
        if os.path.exists(p):
            d = pd.read_csv(p)[['ts', 'c']]
            dom[sym] = d[d.ts < heat.HEAT_END]
    rows = [r for r in range(lo, hi) if (r + 1) % 5 == 0 or (r - lo) % 7 == 0]
    if max_rows and len(rows) > max_rows:                               # (tests only: an even subsample)
        rows = rows[::-(-len(rows) // max_rows)]
    _W.update(m=m, meta=meta, dom=dom, window=window)
    if procs > 1:
        import multiprocessing as mp
        with mp.get_context('fork').Pool(procs) as pool:
            res = pool.map(_live, rows, chunksize=8)
    else:
        res = [_live(r) for r in rows]
    tf_of = lambda key: int(key.split('m:', 1)[0]) if 'm:' in key and key.split('m:', 1)[0].isdigit() else 0      # 0 = context state
    closes, same_close, keys = Counter(), Counter(), {'both': Counter(), 'engine_only': Counter(), 'live_only': Counter()}
    miss = Counter()
    for row, closed, ev in res:
        want, got = set(by_row.get(row, [])), set(ev)
        for k in closed + ([0] if (row + 1) % 15 == 0 else []):
            w, g = {x for x in want if tf_of(x) == k}, {x for x in got if tf_of(x) == k}
            closes[k] += 1
            same_close[k] += w == g
            keys['both'][k] += len(w & g)
            keys['engine_only'][k] += len(w - g)
            keys['live_only'][k] += len(g - w)
            for x in w ^ g:
                miss[x.rsplit('=', 1)[0]] += 1
    tot = lambda c: int(sum(c.values()))
    par = {'coin': asset, 'window_bars': window, 'days': days, 'minutes_checked': len(rows), 'readings': n_read,
           'edges': {'same_as_meta': e_same, 'different': len(e_diff), 'different_names': sorted(e_diff)[:40], 'max_abs_diff': e_max},
           'per_timeframe': {('context' if k == 0 else f'{k}m'): {'bar_closes': int(closes[k]), 'identical_key_sets': int(same_close[k]),
                                                                    'keys_both': int(keys['both'][k]), 'engine_only': int(keys['engine_only'][k]),
                                                                    'live_only': int(keys['live_only'][k])} for k in sorted(closes)},
           'keys_both': tot(keys['both']), 'engine_only': tot(keys['engine_only']), 'live_only': tot(keys['live_only']),
           'agreement': round(tot(keys['both']) / max(1, tot(keys['both']) + tot(keys['engine_only']) + tot(keys['live_only'])), 5),
           'readings_that_differ': miss.most_common(40), 'table_sha256': meta.get('table_sha256'), 'seconds': round(time.time() - t_start)}
    with open(os.path.join(out, 'parity.json'), 'w') as f:
        json.dump(par, f, indent=1)
    log(json.dumps({k: v for k, v in par.items() if k not in ('readings_that_differ',)}, indent=1))
    log('readings that differ most: ' + ', '.join(f'{a} x{b}' for a, b in miss.most_common(15)))
    return par


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--asset', required=True)
    ap.add_argument('--csv', required=True)
    ap.add_argument('--meta', required=True)
    ap.add_argument('--dom', default='')
    ap.add_argument('--out', required=True)
    ap.add_argument('--days', type=int, default=3)
    ap.add_argument('--window', type=int, default=heat_live.WINDOW_BARS)
    ap.add_argument('--procs', type=int, default=4)
    a = ap.parse_args()
    run(a.asset, a.csv, a.meta, a.dom, a.out, a.days, a.window, a.procs)


if __name__ == '__main__':
    main()
