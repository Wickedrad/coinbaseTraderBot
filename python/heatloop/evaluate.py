"""One candidate spec -> one score: events (cached) -> calls -> the ten checks. No engine, no network.

  pool_rows(rows, coin, n)         the TA pool: the n best-ranked rows of the coin across every bar size
  run(spec, sets, rows)            per coin events -> decide -> outcomes; returns the joined rubric.Calls (calls, inv, unconf)
  evaluate(spec, sets, rows, lo_ms, hi_ms, blocks)   the ten checks on the window [lo_ms, hi_ms)
  randomized(parts, rng)           the same calls with random sides (the random-side draws of the twin gate)
"""
import dataclasses

import numpy as np

from heatloop import calls as C
from heatloop import rubric


def pool_rows(rows: list, coin: str, n: int, horizon: int = 15) -> list:
    rs = [r for r in rows if r['coin'] == coin and int(r['h']) == horizon]
    rs.sort(key=lambda r: (int(r['rank_coin']), r['key']))
    return rs[:n]


def _ta_on(spec) -> bool:
    return spec.ta_confirm != 'none' or spec.ta_inv_k > 0


def run(spec: C.Spec, sets: dict, rows: list) -> dict:
    """{'calls': Calls, 'inv': Calls | None, 'unconf': Calls | None} over every coin of the spec, all calls of the loaded grid."""
    pc, pi, pu = [], [], []
    for coin in spec.coins:
        es = sets[coin]
        admitted = C.admit(rows, spec, coin)
        pool = pool_rows(rows, coin, spec.ta_pool, spec.horizon) if _ta_on(spec) else []
        want = [k for r in admitted + pool for k in [r['key']] + list(r.get('aliases') or [])]
        d = C.decide(es.events_for(want), admitted, spec, pool)
        step = float(es.step) if es.step else 1.0
        mk = lambda items: C.outcomes(coin, items, es.o, step, spec.horizon, es.t0, rows_hi=es.n)
        pc.append(mk(d['calls']))
        pi.append(mk(d['inv']))
        pu.append(mk(d['unconf']))
    calls, inv, unc = C.to_calls(pc), C.to_calls(pi), C.to_calls(pu)
    if spec.ta_confirm == 'follows':
        calls.conf = None                      # made calls are the confirmed set; the lapsed base calls (unconf) are the comparison
    else:
        unc = None
    return {'calls': calls, 'inv': inv if len(inv) else None, 'unconf': unc if unc is not None and len(unc) else None}


def window(c, lo_ms: int, hi_ms: int):
    """The calls with lo_ms <= ts < hi_ms (the grid holds calls from the warm-up too; they are never scored)."""
    if c is None:
        return None
    m = (np.asarray(c.ts) >= lo_ms) & (np.asarray(c.ts) < hi_ms)
    return c.pick(m)


def evaluate(spec: C.Spec, sets: dict, rows: list, lo_ms: int, hi_ms: int, blocks='bimonth', seed: int = rubric.SEED) -> dict:
    r = run(spec, sets, rows)
    calls, inv, unc = (window(r[k], lo_ms, hi_ms) for k in ('calls', 'inv', 'unconf'))
    out = rubric.score(calls, inv, lo_ms, hi_ms, blocks, seed=seed, unconf=unc)
    out['n_by_coin'] = {k: int((calls.coin == k).sum()) for k in spec.coins}
    dec, _ = rubric.right(calls.side, calls.move)
    out['n_dec_by_coin'] = {k: int(((calls.coin == k) & dec).sum()) for k in spec.coins}
    out['hash'] = C.spec_hash(spec)
    out['_calls'] = (calls, inv, unc)
    return out


def eligible(res: dict, floor_total: int = 800, floor_coin: int = 300) -> bool:
    return res['n_decided'] >= floor_total and all(v >= floor_coin for v in res['n_dec_by_coin'].values())


def randomized(calls, inv, unc, rng):
    """The same call times and outcomes with a random side on every call (and every dropped / lapsed call)."""
    def flip(c):
        if c is None or not len(c):
            return c
        out = dataclasses.replace(c)
        out.side = np.where(rng.random(len(c)) < 0.5, 1, -1)
        return out
    return flip(calls), flip(inv), flip(unc)


def score_calls(calls, inv, unc, lo_ms, hi_ms, blocks='bimonth', seed=rubric.SEED) -> dict:
    return rubric.score(calls, inv, lo_ms, hi_ms, blocks, seed=seed, unconf=unc)
