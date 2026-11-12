"""Clock add-on to the OR-HM1 heat tables: a finer time of day than the tables' UTC 4-hour block
(python/oracle/prereg/OR-HM1.md, Amendment 6). It changes no stored table.

  python3 -m oracle.heat_clock coin --asset BTC --csv <1m.csv, cut at HEAT_END> --dom <dir> --out <dir> [--twin N] [--procs 4]
  python3 -m oracle.heat_clock league --inputs <dir of <COIN>[-twinN]/{heat.csv.gz,meta.json}> --pack <traded_pack.json>
                                      --out <clock_pack.json> [--all <dir>]

Clock states (each is the state of the ENTRY minute, the minute after the close a reading is known at):
  UTC1h    the UTC hour, 24 levels
  NY30m    the New York half hour (daylight saving followed), 48 levels: 09:30 is the half hour from the stock open
  Weekday  the UTC weekday, 7 levels

coin: the engine's own readings, labels and cell statistics (oracle.heat, unchanged) with two additions to what the
tables hold: (a) every clock level on its own (entries at every 15-minute close while it holds, as the tables' UTC4h),
(b) every event level of every TA reading crossed with the three clock states: a pair relationship is written when a
cell is hot on the build years (the tables' rule), with all its levels. The output has the tables' columns, so the
league's judge and oracle.heat_pairs read it. Coin minutes 2020-01-01 to 2025-12-31 only (the loader refuses a later
minute). `--twin N`: the same on the coin's no-signal twin (what chance alone gives).

league: per coin and horizon the clock rows a bot lane can load (oracle.heat_pairs.build on these tables: no pass mark
as a filter), the clock levels on their own, and the counts against the twins. A MAP on coin price, not a Kalshi-price
result. NEVER DOGE.
"""
import argparse
import gzip
import hashlib
import json
import os
import time

import numpy as np
import pandas as pd

from oracle import heat
from oracle.common import DAY, MIN

NAMES = ('UTC1h', 'NY30m', 'Weekday')
WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
LEVELS = {'UTC1h': [f'{i:02d}' for i in range(24)], 'NY30m': [f'{i // 2:02d}:{30 * (i % 2):02d}' for i in range(48)], 'Weekday': WEEKDAYS}


def levels_at(ts_ms: int) -> dict:
    """The clock levels of the minute that OPENS at ts_ms (the entry minute)."""
    t = pd.Timestamp(int(ts_ms), unit='ms', tz='UTC')
    ny = t.tz_convert('America/New_York')
    return {'UTC1h': LEVELS['UTC1h'][t.hour], 'NY30m': LEVELS['NY30m'][ny.hour * 2 + ny.minute // 30], 'Weekday': WEEKDAYS[t.dayofweek]}


def clock_readings(m: dict) -> list:
    """The three clock states as engine readings: bar i's code is the state of the bar AFTER it (known at bar i's
    close, it is the state of the entry minute), as heat.context_readings does for UTC4h."""
    t0, n = int(m['t0']), int(m['n'])
    R = []
    for name, k in (('UTC1h', 60), ('NY30m', 30), ('Weekday', 1440)):
        nb = n // k
        t = pd.to_datetime(t0 + (np.arange(nb, dtype=np.int64) + 1) * k * MIN, unit='ms', utc=True)
        if name == 'UTC1h':
            codes = t.hour.to_numpy()
        elif name == 'NY30m':
            ny = t.tz_convert('America/New_York')
            codes = ny.hour.to_numpy() * 2 + ny.minute.to_numpy() // 30
        else:
            codes = t.dayofweek.to_numpy()
        R.append({'name': name, 'k': k, 'codes': codes.astype(np.int8), 'levels': LEVELS[name], 'ctx': True, 'state': True, 'base': name})
    return R


def run_coin(asset: str, csv: str, dom: str, out: str, end: int = heat.HEAT_END, twin: int = 0, procs: int = 0, log=print) -> dict:
    if 'DOGE' in asset.upper():
        raise SystemExit('NEVER DOGE')
    os.makedirs(out, exist_ok=True)
    procs = procs or min(4, os.cpu_count() or 1)
    t_start = time.time()
    el = lambda: f'{time.time() - t_start:.0f}s'
    m = heat.load_minutes(csv, end=end)                             # strict: refuses a minute at or after HEAT_END
    label = asset
    if twin:
        m = heat.make_twin(m, twin)
        label = f'{asset}~twin{twin}'
    lab = heat.labels(m)
    g = heat.Grid(m, lab)
    if g.sp['A'].N == 0:
        raise SystemExit(f'{label}: split A has no valid minute')
    readings, _, _, missing, _ = heat.build_readings(m, g, dom, log)
    if missing:
        raise SystemExit(f'{label}: TA-Lib functions missing from this install: {missing}')
    n_ta = len(readings)
    clock = clock_readings(m)
    readings = readings + clock
    cl = [(n_ta + i, R) for i, R in enumerate(clock)]
    log(f'{label}: {n_ta} readings and {len(clock)} clock states ({el()})')

    rows = heat.Rows()
    n_alone = 0
    for _, R in cl:                                                 # (a) every clock level on its own
        for lv, side, lname in heat.event_levels(R):
            ev = heat.level_events(R, lv, side)
            st = {s: g.full(g.in_split(ev, s), s) for s in heat.SPLITS}
            rows += heat.full_rows('single', f'{R["name"]}={lname}', st)
            n_alone += 1

    # (b) every event level of the TA readings against the clock states
    singles = [(0.0, ri, lv, f'{R["name"]}={lname}', side) for ri, R in enumerate(readings[:n_ta]) if not R.get('ctx')
               for lv, side, lname in heat.event_levels(R)]
    xs = {}
    for s in heat.SPLITS:
        sp, xs[s] = g.sp[s], {}
        for H in heat.HORIZONS:
            if sp.N:
                xs[s][(H, 'e')] = (lab[f'ret{H}'][sp.rows] - np.float32(sp.base[H]['mean'])).astype(np.float32)
                xs[s][(H, 's')] = (lab[f'sg{H}'][sp.rows] - np.float32(sp.base[H]['msign'])).astype(np.float32)
    heat._W.update(g=g, readings=readings, conds=cl, ctx=cl, xs=xs)
    heat._W['cbase'] = dict(heat._pmap(heat._cond_base_job, [ci for ci, _ in cl], procs))      # the clock level's own effect over all minutes
    del xs
    heat._W.pop('xs')
    tested, rels = 0, []
    for n_t, r in heat._pmap(heat._pair_job, [(x, True) for x in singles], procs):
        tested += n_t
        rels += r
    log(f'{label}: {len(singles):,} event levels x {len(cl)} clock states: {tested:,} cell-horizons tested, {len(rels):,} relationships with a hot cell ({el()})')
    n_hot_cells = int(sum(int(r[5].sum()) for r in rels))
    for score, x, ci, cA, cB, hot in rels:
        cA, cB = heat.unpack(cA), None if cB is None else heat.unpack(cB)
        R = readings[ci]
        ex = lambda i, x=x, R=R: {'trig': x[3], 'cond': R['name'], 'lv': R['levels'][i]}
        key = f'{x[3]} | {R["name"]}'
        rows += heat.cell_rows('pair', key, 'A', g, cA, R['levels'], extra=ex)
        if cB is not None:
            rows += heat.cell_rows('pair', key, 'B', g, cB, R['levels'], extra=ex)
    heat._W.clear()

    df = rows.frame()
    df.insert(0, 'coin', label)
    df.to_csv(os.path.join(out, 'heat.csv.gz'), index=False, compression='gzip', float_format='%.6g')
    sha = hashlib.sha256()
    with gzip.open(os.path.join(out, 'heat.csv.gz'), 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            sha.update(chunk)
    base = {s: {'n': g.sp[s].base.get('n', 0), 'per_day': g.sp[s].base.get('per_day', 0), 'hold_up': g.sp[s].base.get('hold_up'), 'hold_dn': g.sp[s].base.get('hold_dn'),
                **{str(H): g.sp[s].base[H] for H in heat.HORIZONS if H in g.sp[s].base}} for s in heat.SPLITS}
    meta = {'schema': 'oracle-heat-clock-1', 'asset': asset, 'label': label, 'twin': int(twin), 'minutes': m['n'],
            'from': str(pd.Timestamp(m['t0'], unit='ms')), 'end': str(pd.Timestamp(min(end, heat.HEAT_END), unit='ms')),
            'clock': {R['name']: R['levels'] for _, R in cl}, 'clock_levels_alone': n_alone, 'event_levels': len(singles),
            'tested': {'pair': tested, 'triple': 0}, 'relationships_hot': len(rels), 'relationships_written': len(rels), 'pair_hot_cells_A': n_hot_cells,
            'rows': len(df), 'table_sha256': sha.hexdigest(), 'base': base, 'seconds': round(time.time() - t_start)}
    with open(os.path.join(out, 'meta.json'), 'w') as f:
        json.dump(meta, f, indent=1)
    log(json.dumps({k: v for k, v in meta.items() if k not in ('base', 'clock')}))
    return meta


def league(inputs: str, pack: dict, out: str, all_dir: str = '', horizons=(15, 60), top: int = 40, top_lift: int = 20, per_trigger: int = 3, log=print) -> dict:
    """clock_pack.json: the pair pack's rows on the clock tables, the clock levels on their own and the counts against the twins."""
    from oracle import heat_pairs
    pp = heat_pairs.build(inputs, pack, horizons, top, top_lift, per_trigger, all_dir, log=log, same_table=False)
    alone, counts = [], {}
    for d in sorted(os.listdir(inputs)):
        if not os.path.exists(os.path.join(inputs, d, 'heat.csv.gz')):
            continue
        mt, j = heat_pairs.judged(os.path.join(inputs, d))
        nm = 'twin' if int(mt['twin']) else 'real'
        c = counts.setdefault(nm, {'sets': 0, 'pair_cells_tested': 0, 'hot_on_A': 0, 'replicated_on_B': 0, 'clock_levels_alone': 0, 'alone_kept_direction_on_B': []})
        x = j[j.kind == 'pair']
        c['sets'] += 1
        c['pair_cells_tested'] += int(mt['tested']['pair'])
        c['hot_on_A'] += int(x.hot_odds.sum())
        c['replicated_on_B'] += int(x.rep_odds.sum())
        s = heat._direction(j)
        s = s[s.h.isin(list(horizons))]
        c['clock_levels_alone'] += int(len(s))
        c['alone_kept_direction_on_B'] += (s.odds_B > 0).tolist()
        if nm == 'real':
            for r in s.sort_values(['h', 'oheat_B'], ascending=[True, False]).itertuples():
                alone.append({'coin': mt['asset'], 'h': int(r.h), 'key': r.key, 'dir': int(r.dir), 'call': 'up' if r.dir > 0 else 'down', 'n_A': int(r.n_A), 'n_B': int(r.n_B),
                              **{k: heat_pairs._f(getattr(r, k)) for k in ('wd_B', 'share_A', 'share_B', 'share_over_B', 'odds_A', 'odds_B', 't_A', 't_B', 'oheat_B', 'hold_B')}})
    for c in counts.values():
        k = c.pop('alone_kept_direction_on_B')
        c['alone_kept_direction_on_B'] = round(float(np.mean(k)), 4) if k else None
        c['replicated_share'] = round(c['replicated_on_B'] / c['hot_on_A'], 4) if c['hot_on_A'] else None
    pp.update(schema='oracle-heat-clock-pack-1', clock={n: LEVELS[n] for n in NAMES}, counts_against_twins=counts, alone=alone)
    pp['fires'] += ' The clock levels are those of the entry minute (oracle.heat_clock.levels_at(close time)); `alone` rows are a clock level on its own, ' \
                   'entered at every 15-minute close while it holds.'
    with open(out, 'w') as f:
        json.dump(pp, f, indent=1, allow_nan=False)
    return pp


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    c = sub.add_parser('coin')
    c.add_argument('--asset', required=True)
    c.add_argument('--csv', required=True)
    c.add_argument('--dom', default='')
    c.add_argument('--out', required=True)
    c.add_argument('--twin', type=int, default=0)
    c.add_argument('--procs', type=int, default=0)
    lg = sub.add_parser('league')
    lg.add_argument('--inputs', required=True)
    lg.add_argument('--pack', required=True)
    lg.add_argument('--out', required=True)
    lg.add_argument('--all', default='')
    lg.add_argument('--metas', default='')                           # the heat run's <COIN>/meta.json (zone edges) ...
    lg.add_argument('--live-meta', default='')                       # ... to rewrite live_meta.json with the clock rows' readings
    lg.add_argument('--more-packs', default='')
    lg.add_argument('--stamp', default='')
    a = ap.parse_args()
    if a.cmd == 'coin':
        run_coin(a.asset, a.csv, a.dom, a.out, twin=a.twin, procs=a.procs)
    else:
        with open(a.pack) as f:
            pack = json.load(f)
        pp = league(a.inputs, pack, a.out, a.all)
        if a.stamp:
            pp['stamp'] = a.stamp
            with open(a.out, 'w') as f:
                json.dump(pp, f, indent=1, allow_nan=False)
        if a.live_meta:
            from oracle import heat_pack
            more = heat_pack.more_readings(a.more_packs.split(','))
            for r in pp['rows']:
                more.setdefault(r['coin'], set()).update(r['readings'])
            with open(a.live_meta, 'w') as f:
                json.dump(heat_pack.live_meta(pack, heat_pack._coin_files(a.metas, 'meta.json'), more=more), f, separators=(',', ':'), allow_nan=False)
        print(f'{a.out}: {len(pp["rows"])} pair rows, {len(pp["alone"])} clock levels alone')
        print('against twins:', json.dumps(pp['counts_against_twins']))
        print('chance:', json.dumps(pp['chance']))


if __name__ == '__main__':
    main()
