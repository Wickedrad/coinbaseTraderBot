"""The evaluator self-test (PREREG.md section 5): the twin gate. A pipeline that leaks, or a rubric that is too loose, shows up here.

  twin_gate(spec, twins, rows, lo, hi, blocks)   the rule on the held-out days of the no-signal twins (one coin's twin at a time):
                                                 each must score 2/10 or less and sit inside 50% +/- 3 day-cluster standard errors
  random_side(calls, inv, unc, lo, hi, ...)      the candidate's own call times with a random side, 200 draws (seed 20261120):
                                                 at least 95% must score 2/10 or less
"""
import dataclasses

import numpy as np

from heatloop import evaluate as EV
from heatloop import rubric

DRAWS = 200
DRAW_SEED = 20261120
MAX_SCORE = 2
Z = 3.0
DRAW_SHARE = 0.95


def twin_gate(spec, twins: dict, rows: list, lo: int, hi: int, blocks='bimonth') -> dict:
    """twins: {(coin, twin id): EventSet}. One result row per twin."""
    out = []
    for (coin, tid), es in sorted(twins.items()):
        res = EV.evaluate(dataclasses.replace(spec, coins=(coin,)), {coin: es}, rows, lo, hi, blocks)
        calls = res['_calls'][0]
        dec, hit = rubric.right(calls.side, calls.move)
        h, day = hit[dec].astype(float), calls.day[dec]
        n = int(dec.sum())
        rate = float(h.mean()) if n else float('nan')
        se = rubric.cluster_se(h, day) if n else float('nan')
        z = (rate - 0.5) / se if n and se > 0 else float('nan')
        ok = n > 0 and res['total'] <= MAX_SCORE and abs(z) <= Z
        out.append(dict(coin=coin, twin=int(tid), n=n, hit=round(rate, 4) if n else None, z=round(z, 2) if z == z else None,
                        total=res['total'], ok=bool(ok)))
    return dict(rows=out, ok=bool(out) and all(r['ok'] for r in out))


def random_side(calls, inv, unc, lo: int, hi: int, blocks='bimonth', draws: int = DRAWS, seed: int = DRAW_SEED) -> dict:
    rng = np.random.default_rng(seed)
    totals = []
    for _ in range(draws):
        c, i, u = EV.randomized(calls, inv, unc, rng)
        totals.append(EV.score_calls(c, i, u, lo, hi, blocks)['total'])
    share = float(np.mean([t <= MAX_SCORE for t in totals]))
    return dict(draws=draws, share_le2=round(share, 4), mean_total=round(float(np.mean(totals)), 2), max_total=int(max(totals)),
                ok=bool(share >= DRAW_SHARE))


def gate(spec, calls_res: dict, twins: dict, rows: list, lo: int, hi: int, blocks='bimonth') -> dict:
    t = twin_gate(spec, twins, rows, lo, hi, blocks) if twins else dict(rows=[], ok=False)
    c, i, u = calls_res['_calls']
    r = random_side(c, i, u, lo, hi, blocks)
    return dict(twins=t, random=r, ok=bool(t['ok'] and r['ok']))
