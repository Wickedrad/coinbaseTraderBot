"""Round EA-6 (Nov 25 2026): a fresh-days read of a saved typed rule.

Steven, Nov 22 2026: if edge shows on some days or trades but not others, find the difference and see whether the rule still performs on the same type; if so, save it for that type.
typed_rules.md T1 (BTC and ETH 15-minute, YES buy at 90 to 97 cents from minute 6, only after a day with a low YES share) was found on 206 recorded days (Apr 13 to Nov 4).
The days after that were recorded since and never read. This reads the rule, fixed in advance, on those days: nothing is searched, nothing is tuned, the day-type cut points are
the ones the build days gave. The same pipeline also re-reads the three blocks of the original find, so a plumbing difference would show as a table that does not reproduce.

Recorded days only, paper only, nothing is ordered. Aggregates only.
"""
import argparse
import json
import os

import numpy as np

from subminute import daytypes as DT
from subminute import fampockets as FP
from subminute import pockets as PK


def dnum(s: str) -> int:
    return int(np.datetime64(s, 'D').astype(int))


def read(w, blocks_days: dict, rule: tuple, feature: str, level: str, assets=None, perms: int = 5000, seed: int = 11, log=print) -> dict:
    """rule = (side, bucket low, first placement bar). blocks_days = {'build': (first, last), 'check': ..., 'clean': ..., 'fresh': ...} as 'YYYY-MM-DD'; the cut points of the day
    type come from the build block only. Per scope: typed days, the other days and all days of each block, and a permutation check on the fresh block (the same number of days
    drawn at random from the fresh days: how often does a random pick do as well)."""
    days = np.unique(w.day)
    day0, nd = int(days.min()), int(days.max() - days.min() + 1)
    names = [str(a) for a in w.assets]
    scopes = (list(assets) if assets is not None else names) + ['ALL']
    old_c, old_h = PK.COIN_SLICES, PK.HOUR_SLICES
    PK.COIN_SLICES, PK.HOUR_SLICES = tuple(scopes), ('ALL',)
    try:
        acc = PK.scan(w, day0, nd)
    finally:
        PK.COIN_SLICES, PK.HOUR_SLICES = old_c, old_h
    dn = np.arange(nd) + day0
    have = np.zeros(nd, bool)
    have[(days - day0).astype(int)] = True
    blocks = {name: have & (dn >= dnum(a)) & (dn <= dnum(b)) for name, (a, b) in blocks_days.items()}
    lab, cuts = DT.labels(w, day0, nd, blocks['build'])
    if feature not in lab:
        raise ValueError(f'no label {feature}')
    lv = DT.LEVELS[feature].index(level)
    on, known = (lab[feature] == lv), (lab[feature] >= 0)
    sd, bk0, pl0 = rule
    longest = max(PK.CANCEL)
    cells = [k for k in acc if k[0][3] == longest and k[2] == 'ALL' and k[0][0] == sd and abs(k[0][1][0] - float(bk0)) < 1e-9 and k[0][2][0] == int(pl0)]
    rng = np.random.default_rng(seed)
    rows = []
    for cell in cells:
        (side, bk, pl, cn), sc, _ = cell
        A = acc[cell]
        row = {'scope': sc, 'rule': f'{side} {bk[0]}-{bk[1]} from bar {pl[0]} to {pl[1]}, cancel {cn}', 'type': f'{feature}:{level}'}
        for bn, bm in blocks.items():
            row[bn] = DT._c(DT._stat(A, bm & on, 1))
            row[bn + '_other'] = DT._c(DT._stat(A, bm & ~on & known, 1))
            row[bn + '_all'] = DT._c(DT._stat(A, bm & known, 1))
        pool = np.where(blocks['fresh'] & known)[0]                                    # permutation check on the fresh block
        k = int((blocks['fresh'] & on).sum())
        fills, net = A[:, 4], A[:, 5]
        if k >= 1 and len(pool) > k and fills[pool].sum() > 0:
            typed_idx = np.where(blocks['fresh'] & on)[0]
            obs = net[typed_idx].sum() / max(1.0, fills[typed_idx].sum())
            ge = 0
            for _ in range(perms):
                pick = rng.choice(pool, size=k, replace=False)
                f = fills[pick].sum()
                if f > 0 and net[pick].sum() / f >= obs:
                    ge += 1
            row['fresh_permutation_p'] = round((1 + ge) / (1 + perms), 4)
        rows.append(row)
    pooled = DT.pooled(acc, [k for k in acc if k[0][3] == longest and k[2] == 'ALL' and k[1] == 'ALL'], nd)
    return {'blocks': {n: [str(np.datetime64('1970-01-01') + np.timedelta64(int(dn[m].min()), 'D')), str(np.datetime64('1970-01-01') + np.timedelta64(int(dn[m].max()), 'D')), int(m.sum())] if m.any() else None for n, m in blocks.items()},
            'cuts_from_build': {k: v for k, v in cuts.items() if k == feature}, 'rows': rows, 'levels_all_rules': DT.level_table(pooled, {f: L for f, L in lab.items() if f in ('wkend', feature)}, blocks)}


def verdict(row: dict, min_fills: int = 100) -> dict:
    """Written before the days were read: the rule is SUPPORTED on the fresh days if, over ALL scope, the typed days' mean is above zero with at least `min_fills` fills and at least a
    quarter of a cent above the other days; CONTRADICTED if the typed days' mean is at or below zero or below the other days'; otherwise too thin to say."""
    f, o = row.get('fresh'), row.get('fresh_other')
    if f is None or f['fills'] < min_fills:
        return {'verdict': 'too thin', 'why': 'under the fill floor on the typed fresh days'}
    gap = None if o is None else f['net_c'] - o['net_c']
    if f['net_c'] <= 0 or (gap is not None and gap < 0):
        return {'verdict': 'contradicted', 'gap_c': gap}
    if gap is None or gap < DT.MIN_DIFF * 100:
        return {'verdict': 'too thin', 'gap_c': gap, 'why': 'positive but under a quarter cent above the other days'}
    return {'verdict': 'supported', 'gap_c': gap}


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--hist', required=True)
    ap.add_argument('--assets', required=True)
    ap.add_argument('--kind', default='m15', choices=sorted(FP.KINDS))
    ap.add_argument('--out', required=True)
    ap.add_argument('--rule', default='yes:0.9:6', help='side:bucket low:first placement bar')
    ap.add_argument('--type', default='ptrend:low', help='feature:level')
    ap.add_argument('--build', default='2026-04-13:2026-07-24')
    ap.add_argument('--check', default='2026-07-25:2026-09-13')
    ap.add_argument('--clean', default='2026-09-14:2026-11-04')
    ap.add_argument('--fresh', default='2026-11-05:2026-11-25')
    ap.add_argument('--perms', type=int, default=5000)
    a = ap.parse_args()
    split = lambda s: tuple(s.split(':'))
    with FP.pk_settings(a.kind):
        w = DT.load(a.hist, a.kind, [x.strip().upper() for x in a.assets.split(',')], None, log=lambda *x: None)
        r = read(w, {'build': split(a.build), 'check': split(a.check), 'clean': split(a.clean), 'fresh': split(a.fresh)}, tuple(a.rule.split(':')), *a.type.split(':'),
                 perms=a.perms, log=lambda *x: None)
    os.makedirs(a.out, exist_ok=True)
    for row in r['rows']:
        row['verdict'] = verdict(row)
    json.dump(r, open(os.path.join(a.out, 'fresh_read.json'), 'w'), indent=1, sort_keys=True, default=float)
    print('HEATLOOP fresh-blocks ' + json.dumps({'blocks': r['blocks'], 'cuts_from_build': r['cuts_from_build']}, sort_keys=True), flush=True)
    cell = lambda x: '-' if x is None else (f"{x['net_c']:+.2f}c" + ('' if x['lo_c'] is None else f" [{x['lo_c']}]") + f" ({x['days']}d,{x['fills']})")
    for row in r['rows']:
        print('HEATLOOP fresh-rule ' + json.dumps({k: (cell(v) if isinstance(v, dict) and 'net_c' in v else v) for k, v in row.items()}, sort_keys=True), flush=True)
    lv = {k: ' | '.join(cell(v.get(b)) for b in ('clean', 'fresh')) for k, v in sorted(r['levels_all_rules'].items())}
    print('HEATLOOP fresh-levels (mean rule by day type, clean | fresh) ' + json.dumps(lv, sort_keys=True), flush=True)
