"""One candidate spec -> one score: events (cached) -> calls -> the ten checks. No engine, no network.

  pool_rows(rows, coin, n)         the TA pool: the n best-ranked rows of the coin across every bar size
  run(spec, sets, rows)            per coin events -> decide -> outcomes; returns the joined rubric.Calls (calls, inv, unconf)
  evaluate(spec, sets, rows, lo_ms, hi_ms, blocks)   the ten checks on the window [lo_ms, hi_ms)
  randomized(parts, rng)           the same calls with random sides (the random-side draws of the twin gate)
  fade_fn / baseline               side = fade (PREREG-2.md): the side against the last k minute move, and the ten naive rules at every minute
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


def fade_fn(o, step: float, k: int):
    """side_fn(entry_row) for side = fade: minus the sign of the last k minute move, measured from the open of the entry minute
    (known at entry) back to the open k minutes earlier. 0 where the move is under half a step or the rows are not on the grid."""
    n = len(o)

    def f(e):
        if e < k or e >= n:
            return 0
        return -int(np.sign(np.round((o[e] - o[e - k]) / step)))
    return f


def baseline(spec: C.Spec, sets: dict, lo_ms: int, hi_ms: int) -> dict:
    """{rule: hit rate} of the ten naive rules at EVERY minute of [lo_ms, hi_ms), the spec's coins pooled. The same rows as the calls may
    use (a row needs 60 minutes behind it and its late outcome inside the grid) and the same decided rule (a move of at least FLAT_STEPS)."""
    cnt = {}

    def add(name, hit, dec):
        c = cnt.setdefault(name, [0, 0])
        c[0] += int(hit)
        c[1] += int(dec)
    for coin in spec.coins:
        es = sets[coin]
        step = float(es.step) if es.step else 1.0
        lo = max(60, -(-(lo_ms - es.t0) // C.MIN))
        hi = min(es.n - 1 - spec.horizon, -(-(hi_ms - es.t0) // C.MIN))
        if hi <= lo:
            continue
        e = np.arange(lo, hi)
        mv = (es.o[e + spec.horizon] - es.o[e]) / step
        dec = np.abs(mv) >= rubric.FLAT_STEPS
        sg = np.sign(mv)
        add('up', (sg > 0)[dec].sum(), dec.sum())
        add('down', (sg < 0)[dec].sum(), dec.sum())
        for k in rubric.NAIVE_KS:
            p = np.sign(np.round((es.o[e] - es.o[e - k]) / step))
            ok = dec & (p != 0)
            add(f'follow{k}', (sg == p)[ok].sum(), ok.sum())
            add(f'fade{k}', (sg == -p)[ok].sum(), ok.sum())
    return {k: (h / d if d else float('nan')) for k, (h, d) in cnt.items()}


def decide_coin(spec: C.Spec, es, rows: list, coin: str) -> dict:
    """The raw calls of one coin ({'calls', 'inv', 'unconf'}: entry row, side, key ...), before any outcome is joined."""
    admitted = C.admit(rows, spec, coin)
    pool = pool_rows(rows, coin, spec.ta_pool, spec.horizon) if _ta_on(spec) else []
    want = [k for r in admitted + pool for k in [r['key']] + list(r.get('aliases') or [])]
    step = float(es.step) if es.step else 1.0
    sf = fade_fn(es.o, step, spec.fade_k) if spec.side == 'fade' else None
    return C.decide(es.events_for(want), admitted, spec, pool, side_fn=sf)


def run(spec: C.Spec, sets: dict, rows: list) -> dict:
    """{'calls': Calls, 'inv': Calls | None, 'unconf': Calls | None} over every coin of the spec, all calls of the loaded grid."""
    pc, pi, pu = [], [], []
    for coin in spec.coins:
        es = sets[coin]
        d = decide_coin(spec, es, rows, coin)
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
    base = baseline(spec, sets, lo_ms, hi_ms) if spec.side == 'fade' else None
    out = rubric.score(calls, inv, lo_ms, hi_ms, blocks, seed=seed, unconf=unc, base=base)
    out['_base'] = base
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


def score_calls(calls, inv, unc, lo_ms, hi_ms, blocks='bimonth', seed=rubric.SEED, base=None) -> dict:
    return rubric.score(calls, inv, lo_ms, hi_ms, blocks, seed=seed, unconf=unc, base=base)
