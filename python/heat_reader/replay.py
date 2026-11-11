"""Parity replay: the reader's own code path on minutes the full engine has already answered for.

The oracle's parity job (python/oracle/heat_parity.py) wrote, for every minute close of Dec 29 to 31, 2025, the keys
the full-history engine fires (research/oracle_heat/parity/<COIN>/fixture.json.gz on the oracle branch: `minutes`
maps a close time in ms to its keys). This replays those minutes the way the server reads a live minute: Binance
minutes through the same fetch and cache, the same frame, grid, active_keys and join (reader.read_minutes), with the
window cut at each minute. It reports how many pack keys the two agree on.

  python3 -m heat_reader.replay --fixtures <dir holding <COIN>/fixture.json.gz> --out parity.json [--all]
                                [--max-minutes N] [the reader's own flags: --pack-file, --meta-dir ...]

By default the minutes are the parity job's own sample (every 5-minute close and every 7th other minute). Rows the
pack marks live_parity false never fire in the reader and are left out of both sides. NEVER DOGE.
"""
import argparse
import gzip
import json
import os
import sys
import time
from collections import Counter

import numpy as np

from heat_reader import MIN, config
from heat_reader import cache as minute_cache
from heat_reader.binance import Binance
from heat_reader.engine import Engine, frame
from heat_reader.pack import Tables
from heat_reader.reader import read_minutes


def sample(from_ms: int, to_ms: int, every: bool = False, cap: int = 0) -> list:
    """Minute closes to replay between from_ms (exclusive) and to_ms (inclusive): all of them, or the parity job's
    sample. More than `cap` (when set) are thinned evenly."""
    closes = [t for t in range(from_ms + MIN, to_ms + MIN, MIN)
              if every or t % (5 * MIN) == 0 or ((t - from_ms) // MIN - 1) % 7 == 0]
    if cap and len(closes) > cap:
        closes = closes[::-(-len(closes) // cap)]
    return closes


def replay_coin(engine: Engine, table, top: int, rows: np.ndarray, fixture: dict, window: int, closes: list) -> dict:
    """Replay the closes and count, over the pack's rows: keys both fire, keys only the full engine fires, keys only
    the reader fires."""
    need = engine.need_minutes(window, table.tfs) * MIN
    ts = rows[:, 0]
    live = [r for r in table.rows if r.get('live_parity') is not False]
    both = eng_only = rdr_only = missing = not_ok = 0
    diff = Counter()
    t0 = time.monotonic()
    for t in closes:
        fired = set(fixture['minutes'].get(str(t), []))
        want = {r['key'] for r in live if r['key'] in fired or any(a in fired for a in (r.get('aliases') or []))}
        i1 = int(np.searchsorted(ts, t))
        got = set()
        if i1 == 0 or ts[i1 - 1] != t - MIN:                    # Binance has no bar for this minute: the reader would not read it
            missing += 1
        else:
            i0 = int(np.searchsorted(ts, t - need))
            coin, _ = read_minutes(engine, table, top, frame(rows[i0:i1]), t, window)
            if coin['ok']:
                got = {c['key'] for c in coin['calls']}
            else:
                not_ok += 1
        both += len(want & got)
        eng_only += len(want - got)
        rdr_only += len(got - want)
        diff.update(want ^ got)
    total = both + eng_only + rdr_only
    return {'minutes': len(closes), 'missing_minutes': missing, 'not_ok_minutes': not_ok, 'keys_both': both, 'engine_only': eng_only,
            'reader_only': rdr_only, 'share': None if not total else round(both / total, 5), 'rows_left_out': len(table.rows) - len(live),
            'keys_that_differ': diff.most_common(10), 'seconds': round(time.monotonic() - t0, 1)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog='python3 -m heat_reader.replay', add_help=True)
    ap.add_argument('--fixtures', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--all', action='store_true', help='every minute, not the parity job\'s sample')
    ap.add_argument('--max-minutes', type=int, default=0)
    a, rest = ap.parse_known_args(sys.argv[1:] if argv is None else argv)
    try:
        s = config.load(rest)
    except config.ConfigError as e:
        print(f'heat-reader replay: {e}', flush=True)
        return 2
    engine = Engine(s.oracle_path)
    tables = Tables(s.pack_file, s.meta_dir, s.assets, s.run)
    tables.refresh()
    source = Binance(s.binance_api)
    source.sync_clock()
    out = {'window_bars': s.window_bars, 'pack_sha': tables.pack_sha, 'coins': {}}
    for coin in s.assets:
        table = tables.coins.get(coin)
        path = os.path.join(a.fixtures, coin, 'fixture.json.gz')
        if tables.problem or table is None or table.problem or not os.path.isfile(path):
            out['coins'][coin] = {'skipped': tables.problem or (table.problem if table is not None and table.problem else 'no fixture for this coin')}
            continue
        table.check_edges(engine.zone_levels)
        with gzip.open(path, 'rt') as f:
            fixture = json.load(f)
        if table.problem or fixture.get('table_sha256') != table.table_sha:
            out['coins'][coin] = {'skipped': table.problem or 'the fixture is of another table than the pack'}
            continue
        lo, hi = int(fixture['from_ms']), int(fixture['to_ms'])
        need = engine.need_minutes(s.window_bars, table.tfs) * MIN
        cache = minute_cache.MinuteCache(os.path.join(s.reader_dir, 'replay', f'{coin}.min'))
        rows, got = minute_cache.update(cache, source, coin, lo - need, until_ms=hi)
        if got['error'] is not None:
            out['coins'][coin] = {'skipped': f'Binance fetch failed: {got["error"]}'}
            continue
        res = replay_coin(engine, table, tables.top, rows, fixture, s.window_bars, sample(lo, hi, a.all, a.max_minutes))
        res['minutes_loaded'] = int(len(rows))
        out['coins'][coin] = res
        print(f'heat-reader replay {coin}: {json.dumps({k: v for k, v in res.items() if k != "keys_that_differ"})}', flush=True)
        del rows
    done = [c for c in out['coins'].values() if 'share' in c]
    tot = {k: sum(c[k] for c in done) for k in ('keys_both', 'engine_only', 'reader_only')}
    n = sum(tot.values())
    out.update(tot, share=None if not n else round(tot['keys_both'] / n, 5))
    with open(a.out, 'w') as f:
        json.dump(out, f, indent=1)
    print(f'heat-reader replay: share of pack keys that agree {out["share"]} ({tot})', flush=True)
    return 0 if done else 1


if __name__ == '__main__':
    raise SystemExit(main())
