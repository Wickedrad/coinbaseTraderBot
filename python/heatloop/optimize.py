"""The scripted optimizer of Amendment 1 sections 4 and 5: coordinate descent over the frozen grid, DEV only. No model, no VAL here.

Round r sweeps group r with every other group at its best so far; rounds 1 to 5 take G1 to G5; round 6 sweeps G2 and then G4 once more.
Every trial is scored on DEV with the ten checks. Best trial = most checks passed, then the larger check-2 lower bound, then the
fewer fields that differ from the round 0 spec, then the smaller spec hash. A trial with under 800 decided calls (300 per coin)
is not eligible. Nothing but DEV numbers is read here: the VAL look is a separate process (heatloop.stage) and its bit never feeds back.
"""
import dataclasses
import itertools
import json

from heatloop import calls as C
from heatloop import evaluate as EV

ALL_TFS = ('1m', '5m', '15m', '60m')
ROUND0 = C.Spec(tfs=ALL_TFS, top_n=10, combiner='hottest', lockout=15, lag=0)
STALL_HIT = 0.003


def g1(b):
    return [dataclasses.replace(b, tfs=t) for t in (('1m',), ('5m',), ('1m', '5m'), ALL_TFS)]


def g2(b):
    return [dataclasses.replace(b, top_n=n, min_share_A=float(a), min_share_B=float(s), min_n_B=m)
            for n, a, s, m in itertools.product((5, 10, 20, 40, 80), (0, 52, 53, 54), (0, 52, 53, 54), (0, 5000, 10000))]


def g3(b):
    base = dataclasses.replace(b, combiner='hottest', vote_k=ROUND0.vote_k, margin=ROUND0.margin)
    return [base] + [dataclasses.replace(b, combiner='vote', vote_k=k, margin=m) for k in (2, 3, 5) for m in (1, 2)]


def g4(b):
    off = dict(ta_confirm='none', ta_conf_k=ROUND0.ta_conf_k, ta_inv_k=0, ta_pool=ROUND0.ta_pool)
    out = [dataclasses.replace(b, **off)]
    for conf, k in [('none', None)] + [(m, k) for m in ('precedes', 'follows') for k in (5, 15, 30)]:
        for inv in (0, 5, 15, 30):
            if conf == 'none' and inv == 0:
                continue
            for pool in (20, 40):
                out.append(dataclasses.replace(b, ta_confirm=conf, ta_conf_k=ROUND0.ta_conf_k if k is None else k, ta_inv_k=inv, ta_pool=pool))
    return out


def g5(b):
    return [dataclasses.replace(b, lag=x) for x in (0, 1, 2)]


PLAN = [('G1 reading bars', [g1]), ('G2 admission', [g2]), ('G3 combiner', [g3]), ('G4 TA layer', [g4]), ('G5 entry delay', [g5]),
        ('G2+G4 once more', [g2, g4])]
BUDGET = 4 + 240 + 7 + 55 + 3 + 240 + 55


def nondefault(spec: C.Spec) -> int:
    a, b = spec.as_dict(), ROUND0.as_dict()
    return sum(a[k] != b[k] for k in a)


def key(res: dict) -> tuple:
    """Sort key, smaller = better. An ineligible trial is worse than every eligible one."""
    lb = res['checks'][1]['value']
    lb = float(lb) if lb is not None and lb == lb else -1.0
    return (0 if res['eligible'] else 1, -res['total'], -lb, nondefault(res['spec']), res['hash'])


def better(a: dict, b: dict) -> bool:
    """a improves on b: eligible, and more checks or the same checks and a strictly larger check-2 lower bound."""
    if not a['eligible']:
        return False
    if not b['eligible']:
        return True
    la, lb = (float(x['checks'][1]['value'] or -1) for x in (a, b))
    return (a['total'], la) > (b['total'], lb) and (a['total'] > b['total'] or la > lb + 1e-12)


def summary(res: dict) -> dict:
    return dict(hash=res['hash'], spec=res['spec'].as_dict(), total=res['total'], core8=res['core8'], gate=res['gate'],
                passed=[int(c['passed']) for c in res['checks']], lb=res['checks'][1]['value'], hit=round(res['hit_rate'], 4),
                n_decided=res['n_decided'], n_by_coin=res['n_dec_by_coin'], flat=round(res['flat_share'], 5), eligible=res['eligible'],
                nondefault=nondefault(res['spec']))


def trial(spec, sets, rows, lo, hi, blocks='bimonth') -> dict:
    res = EV.evaluate(spec, sets, rows, lo, hi, blocks)
    res.pop('_calls')
    res['spec'] = spec
    res['eligible'] = EV.eligible(res) and not res['voided']
    return res


def descend(sets, rows, lo, hi, blocks='bimonth', log=None, rounds=None, start=None, stall=True) -> list:
    """Run the rounds (all by default). Returns one dict per round: start, best, improved, trials. `log(record)` gets every trial."""
    best = trial(start or ROUND0, sets, rows, lo, hi, blocks)
    out, quiet = [], 0
    for r, (name, sweeps) in enumerate(PLAN, 1):
        if rounds is not None and r not in rounds:
            continue
        start_res, n = best, 0
        for sweep in sweeps:
            cur = best
            res = [trial(s, sets, rows, lo, hi, blocks) for s in sweep(cur['spec'])]
            n += len(res)
            for t in res:
                if log:
                    log(dict(round=r, group=name, **summary(t)))
            best = min(res + [cur], key=key)
        improved = better(best, start_res)
        out.append(dict(round=r, group=name, trials=n, start=summary(start_res), best=summary(best), improved=bool(improved)))
        gain_total = best['total'] - start_res['total']
        gain_hit = best['hit_rate'] - start_res['hit_rate']
        quiet = quiet + 1 if (gain_total <= 0 and gain_hit < STALL_HIT) else 0
        out[-1]['quiet_rounds'] = quiet
        if stall and quiet >= 2:
            out[-1]['stalled'] = True
            break
    return out
