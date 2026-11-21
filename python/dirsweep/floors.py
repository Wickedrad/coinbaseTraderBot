"""AMENDMENT-3.md: the frequency frontier. The nested walk-forward of PREREG-3.md section 4 repeated with the eligibility floor (decided calls a day a rule
must average in a window) raised from 3 to 6, 10, 15, 20, 30, 40, 60; the lockout replay of every rule chosen; E9; the FINAL sizing; and the
rule that picks the one FINAL candidate. Nothing here changes how a rule is scored; the floor is the only knob.
"""
import math

import numpy as np

from dirsweep import infer as I
from dirsweep import nested as N

FLOORS = (3, 6, 10, 15, 20, 30, 40, 60)
SIZE_CALLS = 1000          # the FINAL window is sized to expect this many decided calls (the pass bar stays 800)
BAR_CALLS = 800
MAX_WEEKS = 8
E9_HIT, E9_LB = 0.530, 0.510


def weeks_needed(calls_per_day: float, target: int = SIZE_CALLS, cap: int = MAX_WEEKS):
    """Whole ISO weeks until `target` decided calls are expected at `calls_per_day`; None when more than `cap` weeks would be needed."""
    if not calls_per_day or calls_per_day <= 0:
        return None
    w = math.ceil(target / (7.0 * calls_per_day))
    return int(w) if w <= cap else None


def _sum_coins(replayers: dict, rid: int, lo: int, hi: int) -> dict:
    tot = {'calls': np.zeros(hi - lo), 'decided': np.zeros(hi - lo), 'right': np.zeros(hi - lo)}
    per = {}
    for name, rp in replayers.items():
        out = rp.replay(rid, lo, hi)
        per[name] = out
        for k in tot:
            tot[k] += out[k]
    return {'tot': tot, 'per': per}


def lockout_nested(replayers: dict, folds: list) -> dict:
    """Every fold's chosen rule replayed on its own test block with the 15-minute lockout (both coins). Pooled, by fold, by coin."""
    nn, rr, by_fold = [], [], []
    coin_n = {c: [] for c in replayers}
    coin_r = {c: [] for c in replayers}
    for f in folds:
        if f.get('rid') is None:
            continue
        lo, hi = f['test_days']
        out = _sum_coins(replayers, f['rid'], lo, hi)
        t = out['tot']
        nn.append(t['decided'])
        rr.append(t['right'])
        for c, o in out['per'].items():
            coin_n[c].append(o['decided'])
            coin_r[c].append(o['right'])
        h = I.pooled_hit(t['decided'], t['right'])
        by_fold.append({'block': f['block'], 'hit': h['hit'], 'N': h['N'], 'calls_per_day': float(t['calls'].sum() / (hi - lo))})
    if not nn:
        return {}
    n, r = np.concatenate(nn), np.concatenate(rr)
    pooled = I.pooled_hit(n, r)
    return {'pooled': pooled, 'decided_per_day': float(n.sum() / len(n)), 'excess_per_day': float(n.sum() / len(n) * (pooled['hit'] - 0.5)),
            'by_fold': by_fold, 'by_coin': {c: I.pooled_hit(np.concatenate(coin_n[c]), np.concatenate(coin_r[c]))['hit'] for c in replayers}}


def frozen_replay(replayers: dict, rid: int, blocks: list, periods: dict) -> dict:
    """The frozen rule replayed with the lockout over every day: totals, last period (C), and each block."""
    nd = blocks[-1][1]
    out = _sum_coins(replayers, rid, 0, nd)['tot']
    lo, hi = periods['C']
    c_days = hi - lo
    res = {'decided_per_day': float(out['decided'].sum() / nd), 'calls_per_day': float(out['calls'].sum() / nd),
           'decided_per_day_C': float(out['decided'][lo:hi].sum() / c_days), 'hit': I.pooled_hit(out['decided'], out['right'])['hit'],
           'by_block': [I.pooled_hit(out['decided'][a:b], out['right'][a:b])['hit'] for a, b in blocks]}
    res['weeks'] = weeks_needed(res['decided_per_day_C'])
    return res


def run_floor(floor: int, ndec, cf, blocks: list, nact: np.ndarray, bench_cells, coins: dict, replayers: dict, periods: dict) -> dict:
    nested = N.run_nested(ndec, cf, blocks, nact, bench_cells, coins=coins, min_per_day=floor)
    fr = N.freeze(ndec, cf, blocks, nact, coins=coins, min_per_day=floor)
    rc = I.reality_check(ndec, cf, min_per_day=floor)
    pb = I.pbo(ndec, cf, blocks, min_per_day=floor)
    pair = None
    if 'ben_n' in nested and 'sel_n' in nested:
        pair = I.paired_bootstrap(nested['sel_n'], nested['sel_r'], nested['ben_n'], nested['ben_r'])
    ver = N.verdict(nested, fr, rc, pb, pair)
    ln = lockout_nested(replayers, nested['folds'])
    every_fold = all(f.get('rid') is not None for f in nested['folds'])               # a test block with no eligible rule fails E9 as it fails E1 to E3
    e9 = bool(every_fold and ln and ln['pooled']['hit'] >= E9_HIT and ln['pooled']['lb975'] > E9_LB)
    out = {'floor': floor, 'nested_hit': nested.get('pooled', {}).get('hit'), 'nested': nested.get('pooled'), 'bench_hit': nested.get('bench_pooled', {}).get('hit'),
           'by_coin': nested.get('pooled_by_coin'),
           'folds': [{'block': f['block'], 'rule': f.get('rule'), 'hit': (f.get('test') or {}).get('hit'), 'N': (f.get('test') or {}).get('N'),
                      'calls_per_day': f.get('test_calls_per_day')} for f in nested['folds']],
           'verdict': dict(ver, E9=e9), 'reality_check': rc, 'pbo': pb, 'paired': pair, 'lockout_nested': ln,
           'frozen': {k: fr.get(k) for k in ('rid', 'rule', 'all', 'calls_per_day', 'last_block_calls_per_day', 'by_coin')}}
    if fr.get('rid') is not None:
        out['frozen_lockout'] = frozen_replay(replayers, fr['rid'], blocks, periods)
        out['frozen']['by_block'] = [round(b['hit'], 4) for b in fr.get('by_block', [])]
    return out


def choose(results: dict) -> dict:
    """The one FINAL candidate (AMENDMENT-3.md section 4). `results` = {twin number: {'floors': [run_floor output...]}}; twin 0 is the real data.
    A floor qualifies when E1 to E6, E8, E9 pass on the real data, E7 passes (every twin's nested pooled hit within 49% to 51% at that floor) and
    the frozen rule's lockout calls a day in 2026 need at most 8 weeks for 1,000 expected calls. Among qualifying floors take the largest
    nested lockout excess (decided calls a day x (hit - 0.5)); ties go to the lower floor."""
    real = {f['floor']: f for f in results[0]['floors']}
    rows = []
    for fl, f in sorted(real.items()):
        twin_hits = [next((x['nested_hit'] for x in results[t]['floors'] if x['floor'] == fl), None) for t in (1, 2, 3) if t in results]
        e7 = len(twin_hits) == 3 and all(h is not None and 0.49 <= h <= 0.51 for h in twin_hits)
        v = dict(f['verdict'])
        v['E7'] = e7
        base = all(v.get(k) for k in ('E1', 'E2', 'E3', 'E4', 'E5', 'E6', 'E7', 'E8', 'E9'))
        fl_out = f.get('frozen_lockout') or {}
        weeks = fl_out.get('weeks')
        ex = (f.get('lockout_nested') or {}).get('excess_per_day')
        rows.append({'floor': fl, 'passes': v, 'qualifies': bool(base and weeks), 'weeks': weeks, 'excess_per_day': ex, 'twin_hits': twin_hits,
                     'rid': f['frozen'].get('rid'), 'rule': f['frozen'].get('rule')})
    q = [r for r in rows if r['qualifies']]
    best = None
    if q:
        best = sorted(q, key=lambda r: (-(r['excess_per_day'] or 0.0), r['floor']))[0]
    return {'candidate': best, 'floors': rows}
