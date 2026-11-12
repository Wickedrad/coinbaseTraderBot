"""Long horizons for the OR-HM1 heat map: 240 and 1440 minutes (4 hours and a day), for perpetuals
(python/oracle/prereg/OR-HM1.md, Amendment 7). It changes no stored table and no line of oracle.heat.

  python3 -m oracle.heat_long coin --asset BTC --csv <1m.csv, cut at HEAT_END> --dom <dir> --out <dir> [--twin N] [--procs 4]
  python3 -m oracle.heat_long league --inputs <dir of <COIN>[-twinN]/{heat.csv.gz,meta.json}> --out <dir>
                                     [--metas <dir of the main run's <COIN>/meta.json>] [--all <dir>] [--stamp <text>]
                                     [--pack <main traded_pack.json> --live-meta <live_meta.json> --more-packs <a.json,b.json>]

coin: the engine (oracle.heat.run_coin) as it is, with the horizons 240 and 1440 minutes in place of 1 to 60: the same
readings, levels, statistics, singles, pair and triple stages. What differs:
  - the labels reach a day ahead (the move from the entry to the close 4 hours / a day later, its best and worst point,
    the minutes price holds on one side, the first touch of +-10/25/50 bps). Holds and first touches are int16 here
    (a day is 1,440 minutes; the engine's int8 tops out at 127). A row counts only when no data gap falls in the next day.
  - the build years' rows end a day before 2025 (so no build label reads a 2025 price) and the check year's rows a day
    before 2026 (the loader reads no 2026 minute, as for the main tables).
  - the zone edges, curve edges and price step come from the build-year bars the MAIN tables used (they end 60 minutes
    before 2025), so a key such as `60m:RSI14=low` means the same level here, in the main packs and in the live reader.
    The league checks this against the main run's meta.json (`edges_as_main_tables`).
Day-wide windows overlap: events a few hours apart share most of their next day, and the t values count days as
independent. The no-signal twin (same code, same overlap) is the yardstick for every count; read the coin against it.

league: the engine's league on these tables (summary.json, league.md, direction_all.csv.gz ...), then the bot's packs at
240 and 1440 minutes: perp_pack.json (schema oracle-heat-pack-1, the singles, as traded_pack.json) and
perp_pair_pack.json (schema oracle-heat-pairs-1, TA against TA, as pair_pack.json). A MAP on coin price, not a
Kalshi-price result. NEVER DOGE.
"""
import argparse
import contextlib
import copy
import json
import os

import numpy as np
import pandas as pd

from oracle import heat
from oracle.common import MIN

LONG = [240, 1440]
MAIN_HMAX = 60                  # the main tables' longest horizon: where their build-year bars (zone edges) end


def labels(m: dict, chunk: int = 20_000) -> dict:
    """oracle.heat.labels with int16 holds and first touches (a day-wide window) and smaller chunks; every quantity is
    computed the same way (tests: equal to the engine's at the engine's horizons)."""
    from numpy.lib.stride_tricks import sliding_window_view
    HZ, HM, TOUCH = heat.HORIZONS, heat.HMAX, heat.TOUCH
    n, o, c, h, l, gap = m['n'], m['o'], m['c'], m['h'], m['l'], m['gap']
    e = np.r_[o[1:], np.nan]
    c1 = np.r_[c[1:], np.nan]
    out = {'gap1': ((e / c - 1) * 1e4).astype(np.float32)}
    hp = np.r_[h[1:], np.full(HM + 1, np.nan)]
    lp = np.r_[l[1:], np.full(HM + 1, np.nan)]
    Wh, Wl = sliding_window_view(hp, HM), sliding_window_view(lp, HM)
    Wc = sliding_window_view(np.r_[c[1:], np.full(HM + 1, np.nan)], HM)
    dead_a = np.broadcast_to(np.asarray(heat.TICK_DEAD * m['tick'] if 'tick' in m else 0.0, np.float64), (n,))
    out['holdU'], out['holdD'] = np.zeros(n, np.int16), np.zeros(n, np.int16)
    for H in HZ:
        fut = np.r_[c[H:], np.full(H, np.nan)]
        out[f'ret{H}'] = ((fut / e - 1) * 1e4).astype(np.float32)
        out[f'retL{H}'] = ((fut / c1 - 1) * 1e4).astype(np.float32)
        for nm in ('up', 'dn', 'dipU', 'dipD'):
            out[f'{nm}{H}'] = np.full(n, np.nan, np.float32)
    for X in TOUCH:
        out[f'tu{X}'], out[f'td{X}'] = np.zeros(n, np.int16), np.zeros(n, np.int16)
    for s in range(0, n, chunk):
        t = min(n, s + chunk)
        ee = e[s:t]
        wh, wl = Wh[s:t], Wl[s:t]
        ar = np.arange(t - s)
        with np.errstate(invalid='ignore'):
            for H in HZ:
                a, b = wh[:, :H], wl[:, :H]
                am = np.where(np.isnan(a), -np.inf, a).argmax(1)
                bm = np.where(np.isnan(b), np.inf, b).argmin(1)
                out[f'up{H}'][s:t] = (a[ar, am] / ee - 1) * 1e4
                out[f'dn{H}'][s:t] = (b[ar, bm] / ee - 1) * 1e4
                out[f'dipU{H}'][s:t] = (np.minimum.accumulate(b, 1)[ar, am] / ee - 1) * 1e4
                out[f'dipD{H}'][s:t] = (np.maximum.accumulate(a, 1)[ar, bm] / ee - 1) * 1e4
            rc = (Wc[s:t] / ee[:, None] - 1) * 1e4
            dd = dead_a[s:t][:, None]
            ab, be = rc > dd, rc < -dd
            out['holdU'][s:t] = np.where(ab.all(1), HM, ab.argmin(1))
            out['holdD'][s:t] = np.where(be.all(1), HM, be.argmin(1))
            del rc, ab, be
            for X in TOUCH:
                for W, up, arr in ((wh, True, out[f'tu{X}']), (wl, False, out[f'td{X}'])):
                    hit = (W >= ee[:, None] * (1 + X / 1e4)) if up else (W <= ee[:, None] * (1 - X / 1e4))
                    arr[s:t] = np.where(hit.any(1), hit.argmax(1) + 1, 0)
    dead = heat.TICK_DEAD * m['tick'] if 'tick' in m else 0.0
    with np.errstate(invalid='ignore'):
        for H in HZ:
            r = out[f'ret{H}']
            out[f'sg{H}'] = np.where(np.isfinite(r) & (np.abs(r) > dead), np.sign(r), 0).astype(np.int8)
    out['tick'] = m['tick'] if 'tick' in m else np.zeros(n, np.float32)
    g = pd.Series(gap.astype(np.int16)[::-1]).rolling(HM + 1, min_periods=1).sum().to_numpy()[::-1]
    valid = (g == 0)
    valid[max(0, n - HM - 1):] = False
    out['valid'] = valid
    return out


class _MainCut:
    """The grid as build_readings sees it: split A's bars end where the main tables' did (60 minutes before 2025) for the
    zone edges, curve edges and price step; every statistic still goes through the real grid (rows a day before 2025)."""

    def __init__(self, g, hi: int):
        self._g = g
        spA = copy.copy(g.sp['A'])
        spA.hi = hi
        self.sp = {**g.sp, 'A': spA}

    def __getattr__(self, k):
        return getattr(self._g, k)


def main_cut_hi(g) -> int:
    a, b = heat.SPLITS['A']
    lo = g.sp['A'].lo
    return max(lo, min(int((b - MAIN_HMAX * MIN - g.t0) // MIN), g.n))


@contextlib.contextmanager
def long_horizons():
    """oracle.heat with the long horizons for the length of the block (the pool forks, so its workers see them too)."""
    saved = (heat.HORIZONS, heat.HMAX, heat.labels, heat.build_readings)
    engine_build = heat.build_readings

    def build_readings(m, g, dom, log=print):
        return engine_build(m, _MainCut(g, main_cut_hi(g)), dom, log)

    heat.HORIZONS, heat.HMAX, heat.labels, heat.build_readings = list(LONG), max(LONG), labels, build_readings
    try:
        yield
    finally:
        heat.HORIZONS, heat.HMAX, heat.labels, heat.build_readings = saved


def run_coin(asset: str, csv: str, dom: str, out: str, end: int = heat.HEAT_END, twin: int = 0, procs: int = 0, log=print) -> dict:
    if 'DOGE' in asset.upper():
        raise SystemExit('NEVER DOGE')
    with long_horizons():
        mt = heat.run_coin(asset, csv, dom, out, end=end, twin=twin, procs=procs, log=log)
    mt.update(addon='long', horizons=list(LONG), hmax=max(LONG),
              edges_from='build-year bars up to 60 minutes before 2025, as the main tables (OR-HM1 Amendment 7)')
    with open(os.path.join(out, 'meta.json'), 'w') as f:
        json.dump(mt, f, indent=1)
    return mt


def edges_check(metas: dict, main: dict) -> dict:
    """{COIN: same / different readings and price step} of the long tables' zone edges against the main run's."""
    out = {}
    for coin, mt in sorted(metas.items()):
        mm = main.get(coin)
        if mm is None:
            out[coin] = None
            continue
        a, b = mt.get('edges', {}), mm.get('edges', {})
        diff = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
        out[coin] = {'same': sum(1 for k in set(a) & set(b) if a[k] == b[k]), 'different': diff, 'n_different': len(diff),
                     'price_step_same': mt.get('price_step') == mm.get('price_step')}
    return out


def league(inputs: str, out: str, main_metas: dict = None, all_dir: str = '', top: int = 40, top_share: int = 20, pair_top: int = 40,
           top_lift: int = 20, per_trigger: int = 3, stamp: str = '', log=print) -> dict:
    from oracle import heat_pack, heat_pairs
    if any('DOGE' in d.upper() for d in os.listdir(inputs)):
        raise SystemExit('never DOGE')
    os.makedirs(out, exist_ok=True)
    hz = tuple(LONG)
    with long_horizons():
        summ = heat.league(inputs, out)
        d = pd.read_csv(os.path.join(out, 'direction_all.csv.gz'), low_memory=False)
        pk = heat_pack.build(d, summ, hz, top, top_share, source='direction_all.csv.gz')
        pp = heat_pairs.build(inputs, pk, hz, pair_top, top_lift, per_trigger, all_dir, log=log)
    chk = edges_check(heat_pack._coin_files(inputs, 'meta.json'), main_metas) if main_metas else None
    bad = {c: set(v['different']) for c, v in (chk or {}).items() if v and v['n_different']}
    for r in pk['rows']:
        r['readings'] = sorted({k.rsplit('=', 1)[0] for k in [r['key']] + r['aliases']})
    for p in (pk, pp):
        p['addon'] = 'long horizons for perpetuals (OR-HM1 Amendment 7): 240 and 1440 minutes'
        p['edges_as_main_tables'] = chk
        if stamp:
            p['stamp'] = stamp
        for r in p['rows']:
            nb = bad.get(r['coin'], set())
            r['edges_as_main'] = None if chk is None else not any(x.removesuffix(' sign') in nb for x in r['readings'])
    pk['limits'] = ('Day-wide windows overlap (events hours apart share most of their next day) and the t values count days as independent, '
                    'so read every count against the no-signal twin (chance). wd_B for 1440 minutes is at most 1 (one day window per day). '
                    'A map on coin price, not a Kalshi-price result.')
    for nm, p in (('perp_pack.json', pk), ('perp_pair_pack.json', pp)):
        with open(os.path.join(out, nm), 'w') as f:
            json.dump(p, f, indent=1, allow_nan=False)
    return {'summary': summ, 'pack': pk, 'pairs': pp, 'edges_as_main_tables': chk}


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    c = sub.add_parser('coin')
    c.add_argument('--asset', required=True)
    c.add_argument('--csv', required=True)
    c.add_argument('--dom', required=True)
    c.add_argument('--out', required=True)
    c.add_argument('--twin', type=int, default=0)
    c.add_argument('--procs', type=int, default=0)
    lg = sub.add_parser('league')
    lg.add_argument('--inputs', required=True)
    lg.add_argument('--out', required=True)
    lg.add_argument('--metas', default='')                       # the main run's <COIN>/meta.json: the edges check
    lg.add_argument('--all', default='')
    lg.add_argument('--stamp', default='')
    lg.add_argument('--pack', default='')                        # the main traded_pack.json ...
    lg.add_argument('--live-meta', default='')                   # ... to rewrite live_meta.json with the perp packs' readings added
    lg.add_argument('--more-packs', default='')                  # the pair and clock packs (their readings stay in the file)
    a = ap.parse_args()
    if a.cmd == 'coin':
        mt = run_coin(a.asset, a.csv, a.dom, a.out, twin=a.twin, procs=a.procs)
        print(json.dumps({k: v for k, v in mt.items() if k not in ('base', 'edges')}, indent=1))
        return
    from oracle import heat_pack
    main_metas = heat_pack._coin_files(a.metas, 'meta.json') if a.metas else None
    r = league(a.inputs, a.out, main_metas, a.all, stamp=a.stamp)
    pk, pp = r['pack'], r['pairs']
    print('by kind:', json.dumps(r['summary'].get('by_kind'))[:2000])
    print('direction (real vs twin):', json.dumps({h: r['summary'].get('direction', {}).get(str(h)) for h in LONG})[:3000])
    print('edges as the main tables:', json.dumps({c: v and {k: v[k] for k in ('same', 'n_different', 'price_step_same')} for c, v in (r['edges_as_main_tables'] or {}).items()}))
    n = pd.DataFrame(pk['rows']).groupby(['coin', 'h']).size().to_dict() if pk['rows'] else {}
    print(f'perp_pack.json: {len(pk["rows"])} rows {n}; perp_pair_pack.json: {len(pp["rows"])} rows; pair chance: {json.dumps(pp.get("chance"))[:1500]}')
    if a.live_meta:
        if not (a.pack and main_metas):
            raise SystemExit('--live-meta needs --pack and --metas')
        with open(a.pack) as f:
            pack = json.load(f)
        more = heat_pack.more_readings([x for x in a.more_packs.split(',') if x] + [os.path.join(a.out, 'perp_pack.json'), os.path.join(a.out, 'perp_pair_pack.json')])
        lm = heat_pack.live_meta(pack, main_metas, more=more)
        with open(a.live_meta, 'w') as f:
            json.dump(lm, f, separators=(',', ':'), allow_nan=False)
        print(f'{a.live_meta}: ' + ', '.join(f'{c} {len(v["edges"])} readings with edges, {len(v["no_edges"])} without' for c, v in lm.items()))


if __name__ == '__main__':
    main()
