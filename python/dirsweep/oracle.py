"""S2 of PREREG-3.md section 5: the perfect-hindsight oracle strips for the same readings at 5, 15, 30 and 60 minutes.

For every reading cell and every minute of history the engine (hist.cell_arrays) has recorded in hindsight what price did next. Here those strips
are summed over the build, check and final-check periods (A, B, C), turned into heat (calls per day x mean aligned bps per call), ranked, and tested:
a survivor must be in the top 50 by heat in A, have a positive B mean whose day-cluster 90% lower bound is above zero, and a positive C mean.
"""
import numpy as np

from dirsweep import grid as G
from dirsweep import infer as I

TOP_LEAGUE, TOP_SURVIVE = 25, 50


def period_sums(arr: dict, periods: dict) -> dict:
    """{period: {ncall, ndec, cf, sbps: (cells,) float64}} from the (cells, days) arrays."""
    return {name: {k: arr[k][:, lo:hi].sum(1, dtype=np.float64) for k in ('ncall', 'ndec', 'cf', 'sbps')} for name, (lo, hi) in periods.items()}


def live_days(arr: dict, periods: dict) -> dict:
    """Days of each period on which at least one reading was called (the divisor of 'per day'): the cell (k=1, nothing else) is called on every valid minute."""
    live = arr['ncall'][0] > 0
    return {name: int(live[lo:hi].sum()) for name, (lo, hi) in periods.items()}


def side_row(S: dict, cell: int, side: int, days: int) -> dict:
    """One rule's numbers on one period. Aligned bps: the move in the rule's direction, in basis points of the entry open, averaged over called rows."""
    sg = 1.0 if side == 0 else -1.0
    ncall, ndec, cf, sb = S['ncall'][cell], S['ndec'][cell], S['cf'][cell], S['sbps'][cell]
    right = cf if side == 0 else ndec - cf
    return {'calls_per_day': float(ncall / max(1, days)), 'decided_per_day': float(ndec / max(1, days)), 'hit': float(right / ndec) if ndec else None,
            'mean_bps': float(sg * sb / ncall) if ncall else None, 'heat': float(sg * sb / max(1, days))}


def mean_bps_bound(arr: dict, cell: int, side: int, lo: int, hi: int) -> dict:
    """Mean aligned bps per called row over days [lo, hi) with a day-cluster one-sided 90% lower bound."""
    sg = 1.0 if side == 0 else -1.0
    n = arr['ncall'][cell, lo:hi].astype(np.float64)
    s = sg * arr['sbps'][cell, lo:hi].astype(np.float64)
    N, S, p, se = I.ratio_se(n[None, :], s[None, :])
    p, se = float(p[0]), float(se[0])
    return {'mean_bps': p, 'se': se, 'lb90': p - I.Z90 * se}


def league(arr: dict, h: int, periods: dict) -> dict:
    """The league and survivors of one horizon. Returns {'league': [...top 25...], 'survivors': [...], 'eligible_rules': int}."""
    days = live_days(arr, periods)
    S = period_sums(arr, periods)
    A = S['A']
    dA = max(1, days['A'])
    heat = np.stack([A['sbps'] / dA, -A['sbps'] / dA], axis=1)                 # (cells, 2)
    elig = (A['ndec'] / dA >= 1.0)
    heat = np.where(elig[:, None], heat, -np.inf)
    flat = heat.ravel()
    order = np.lexsort((np.arange(flat.size), -flat))[:TOP_SURVIVE]
    order = [int(r) for r in order if np.isfinite(flat[r])]
    rows, survivors = [], []
    for rank, rid in enumerate(order, 1):
        cell, side = divmod(rid, 2)
        row = {'rank': rank, 'rid': rid, 'rule': G.describe(rid), 'h': h}
        for name in periods:
            row[name] = side_row(S[name], cell, side, days[name])
        b = mean_bps_bound(arr, cell, side, *periods['B'])
        row['B_bound'] = b
        row['survivor'] = bool(b['mean_bps'] > 0 and b['lb90'] > 0 and (row['C']['mean_bps'] or 0) > 0)
        if row['survivor']:
            survivors.append(rid)
        rows.append(row)
    return {'h': h, 'days': days, 'eligible_rules': int(2 * elig.sum()), 'league': rows[:TOP_LEAGUE], 'top50': len(rows),
            'survivors': [r for r in rows if r['survivor']], 'n_survivors': len(survivors)}


def matrix(arr: dict, periods: dict, k: int = 15) -> dict:
    """Pair tables at lookback k and the given horizon of `arr`: z x a, z x r, a x r (phase all) and z x phase (a and r off), per period:
    the fade hit rate, mean aligned bps of the fade side and decided calls per day."""
    ik = G.K.index(k)
    days = live_days(arr, periods)
    S = period_sums(arr, periods)

    def entry(iz, ia, ir, ip):
        c = G.cell(ik, iz, ia, ir, ip)
        e = {}
        for name in periods:
            r = side_row(S[name], c, 0, days[name])
            e[name] = [None if r['hit'] is None else round(r['hit'], 4), None if r['mean_bps'] is None else round(r['mean_bps'], 3), round(r['decided_per_day'], 2)]
        return e

    zl = ['off'] + [str(x) for x in G.TZ]
    al = ['off'] + [str(x) for x in G.TA]
    rl = ['off'] + [str(x) for x in G.TR]
    out = {'k': k, 'cell': '[fade hit, fade mean aligned bps, decided per day]', 'z': zl, 'a': al, 'r': rl, 'phase': list(G.PH_NAMES)}
    out['z_x_a'] = [[entry(iz, ia, 0, 0) for ia in range(G.NA)] for iz in range(G.NZ)]
    out['z_x_r'] = [[entry(iz, 0, ir, 0) for ir in range(G.NR)] for iz in range(G.NZ)]
    out['a_x_r'] = [[entry(0, ia, ir, 0) for ir in range(G.NR)] for ia in range(G.NA)]
    out['z_x_phase'] = [[entry(iz, 0, 0, ip) for ip in range(G.NP)] for iz in range(G.NZ)]
    return out


def short(rule: dict) -> str:
    """One-line name of a rule, for the tables."""
    a = '-' if rule['a'] is None else f"{rule['a']:g}"
    return f"{rule['side']} k{rule['k']} z{rule['z']:g} a{a} r{rule['r']:g} {rule['phase']}"


def _pct(x) -> str:
    return '-' if x is None else f'{100 * x:.2f}'


def render_league(lg: dict) -> list:
    """Markdown rows of one horizon's league (top 25 by A heat) with B and C numbers; the survivors count and best survivor follow."""
    out = [f"### h = {lg['h']} min: {lg['eligible_rules']} eligible rules, {lg['n_survivors']} survivors among the top {lg['top50']} by A heat (live days A/B/C = {lg['days']['A']}/{lg['days']['B']}/{lg['days']['C']})", '',
           '| # | rule | A dec/day | A hit % | A bps/call | A heat bps/day | B hit % | B bps | B lb90 | C hit % | C bps | survivor |', '|---|---|---|---|---|---|---|---|---|---|---|---|']
    for r in lg['league']:
        A, B, C = r['A'], r['B'], r['C']
        f = lambda x, d=3: '-' if x is None else f'{x:.{d}f}'
        out.append(f"| {r['rank']} | {short(r['rule'])} | {A['decided_per_day']:.1f} | {_pct(A['hit'])} | {f(A['mean_bps'])} | {A['heat']:.1f} | {_pct(B['hit'])} | {f(B['mean_bps'])} | {f(r['B_bound']['lb90'])} | {_pct(C['hit'])} | {f(C['mean_bps'])} | {'yes' if r['survivor'] else 'no'} |")
    if lg['survivors']:
        s = lg['survivors'][0]
        out += ['', f"Largest-A-heat survivor: rank {s['rank']}, {short(s['rule'])}, A heat {s['A']['heat']:.1f} bps/day, hit A/B/C = {_pct(s['A']['hit'])}/{_pct(s['B']['hit'])}/{_pct(s['C']['hit'])} %, bps A/B/C = {s['A']['mean_bps']:.3f}/{s['B']['mean_bps']:.3f}/{s['C']['mean_bps']:.3f}"]
    out.append('')
    return out


def render_matrix(mx: dict) -> list:
    """Markdown tables of the pair matrix: fade hit % and fade mean aligned bps per call, each as A/B/C."""
    out = [f"### Pair matrix, lookback {mx['k']} min, horizon 15 min, fade side (cells A/B/C)", '']
    pairs = (('z_x_a', 'z', 'a', 'z (rows) by taker-flow a (columns), r off, phase all'), ('z_x_r', 'z', 'r', 'z (rows) by relative volume r (columns), a off, phase all'),
             ('a_x_r', 'a', 'r', 'a (rows) by r (columns), z off, phase all'), ('z_x_phase', 'z', 'phase', 'z (rows) by clock phase (columns), a and r off'))
    for key, rk, ck, title in pairs:
        for what, idx, fmt in (('fade hit %', 0, lambda x: '-' if x is None else f'{100 * x:.1f}'), ('fade mean aligned bps per call', 1, lambda x: '-' if x is None else f'{x:.2f}')):
            out += [f'**{what}: {title}**', '', '| ' + rk + ' \\ ' + ck + ' | ' + ' | '.join(mx[ck]) + ' |', '|---|' + '---|' * len(mx[ck])]
            for i, row in enumerate(mx[key]):
                out.append(f'| {mx[rk][i]} | ' + ' | '.join('/'.join(fmt(c[p][idx]) for p in ('A', 'B', 'C')) for c in row) + ' |')
            out.append('')
    return out
