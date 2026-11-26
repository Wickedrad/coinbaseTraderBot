"""S1 of PREREG-3.md: the nested walk-forward sweep at the 15-minute horizon and the verdict inputs E1 to E6 and E8.

Inputs are (cells, days) int arrays pooled over BTC and ETH: ndec (decided calls) and cf (calls where the fade side is right). A rule is
rule id = cell * 2 + side (0 fade, 1 follow). Everything here is a function of those arrays and the block list, so tests can run it on small arrays.
"""
import numpy as np

from dirsweep import grid as G
from dirsweep import infer as I

FIRST_TEST = 4            # test blocks are index 4 .. 13 (2022H1 .. 2026 Jul-Oct)


def rule_scores(st: dict, min_per_day: float = 3.0) -> np.ndarray:
    """(cells, 2) score of each rule on the window of `st`: hit - 1.96 se (fade) or (1 - hit) - 1.96 se (follow); -inf if the rule is not eligible
    (fewer than min_per_day decided calls per day on average) or has no standard error."""
    p, se = st['p'], st['se']
    elig = (st['N'] / max(1, st['days']) >= min_per_day) & np.isfinite(se) & np.isfinite(p)
    sc = np.stack([p - I.Z975 * se, (1.0 - p) - I.Z975 * se], axis=1)
    return np.where(elig[:, None], sc, -np.inf)


def pick(scores: np.ndarray, nact: np.ndarray, allowed: np.ndarray = None):
    """Best rule: largest score; ties by fewer active filters, then rule id. Returns (rule id, score) or (None, -inf) when nothing is eligible."""
    s = scores.copy()
    if allowed is not None:
        s[~allowed] = -np.inf
    flat = s.ravel()
    mx = flat.max()
    if not np.isfinite(mx):
        return None, -np.inf
    cand = np.flatnonzero(flat == mx)
    order = np.lexsort((cand, nact[cand // 2]))
    return int(cand[order[0]]), float(mx)


def side_counts(ndec, cf, rid: int, lo: int, hi: int) -> tuple:
    """(decided, right) per day of one rule over days [lo, hi)."""
    cell, side = divmod(int(rid), 2)
    n = ndec[cell, lo:hi].astype(np.float64)
    c = cf[cell, lo:hi].astype(np.float64)
    return n, (c if side == 0 else n - c)


def bench_allowed(n_cell: int, bench_cells) -> np.ndarray:
    a = np.zeros((n_cell, 2), bool)
    a[list(bench_cells)] = True
    return a


def run_nested(ndec, cf, blocks: list, nact: np.ndarray, bench_cells, coins: dict = None, first_test: int = FIRST_TEST, min_per_day: float = 3.0) -> dict:
    """Nested out-of-sample result of section 4. For each test block: train on every earlier block except the last day of the block just before it,
    choose the rule with the best training score, score it (and the best unfiltered rule) on the test block. `coins` = {name: (ndec, cf)} for the
    by-coin report."""
    n_cell = ndec.shape[0]
    allowed = bench_allowed(n_cell, bench_cells)
    folds, sel_n, sel_r, ben_n, ben_r = [], [], [], [], []
    for t in range(first_test, len(blocks)):
        lo_t, hi_t = blocks[t]
        tr_hi = lo_t - 1                      # purge: the last day of block t-1 is not trained on
        st = I.window_stats(ndec, cf, 0, tr_hi)
        sc = rule_scores(st, min_per_day)
        rid, score = pick(sc, nact)
        brid, bscore = pick(sc, nact, allowed)
        f = {'block': t, 'train_days': [0, tr_hi], 'test_days': [lo_t, hi_t], 'rid': rid, 'bench_rid': brid, 'train_score': score, 'bench_train_score': bscore}
        if rid is None:
            folds.append(dict(f, hit=None))
            continue
        cell, side = divmod(rid, 2)
        f['rule'] = G.describe(rid)
        f['train_hit'] = float(st['p'][cell] if side == 0 else 1.0 - st['p'][cell])
        f['train_calls_per_day'] = float(st['N'][cell] / st['days'])
        n, r = side_counts(ndec, cf, rid, lo_t, hi_t)
        f['test'] = I.pooled_hit(n, r)
        f['test_calls_per_day'] = float(n.sum() / (hi_t - lo_t))
        sel_n.append(n), sel_r.append(r)
        if brid is not None:
            bn, br = side_counts(ndec, cf, brid, lo_t, hi_t)
            ben_n.append(bn), ben_r.append(br)
            f['bench_rule'] = G.describe(brid)
            f['bench_test'] = I.pooled_hit(bn, br)
        if coins:
            f['test_by_coin'] = {name: I.pooled_hit(*side_counts(a, b, rid, lo_t, hi_t))['hit'] for name, (a, b) in coins.items()}
        folds.append(f)
    out = {'folds': folds}
    if sel_n and len(sel_n) == len(folds):
        n, r = np.concatenate(sel_n), np.concatenate(sel_r)
        out['pooled'] = I.pooled_hit(n, r)
        out['sel_n'], out['sel_r'] = n, r
        if ben_n and len(ben_n) == len(folds):
            bn, br = np.concatenate(ben_n), np.concatenate(ben_r)
            out['bench_pooled'] = I.pooled_hit(bn, br)
            out['ben_n'], out['ben_r'] = bn, br
        if coins:
            by = {}
            for name, (a, b) in coins.items():
                nn, rr = [], []
                for f in folds:
                    x, y = side_counts(a, b, f['rid'], *f['test_days'])
                    nn.append(x), rr.append(y)
                by[name] = I.pooled_hit(np.concatenate(nn), np.concatenate(rr))
            out['pooled_by_coin'] = by
    return out


def freeze(ndec, cf, blocks: list, nact: np.ndarray, coins: dict = None, min_per_day: float = 3.0, top: int = 10) -> dict:
    """The final rule: the same choice on all days of all blocks (no test block left), with its numbers per block and per coin and the top rules."""
    n_days = ndec.shape[1]
    st = I.window_stats(ndec, cf, 0, n_days)
    sc = rule_scores(st, min_per_day)
    rid, score = pick(sc, nact)
    out = {'rid': rid, 'score': score}
    flat = sc.ravel()
    order = np.lexsort((np.arange(flat.size), nact[np.arange(flat.size) // 2], -flat))[:top]
    out['top'] = []
    for r in order:
        if not np.isfinite(flat[r]):
            continue
        cell, side = divmod(int(r), 2)
        out['top'].append({'rid': int(r), 'rule': G.describe(int(r)), 'score': float(flat[r]),
                           'hit': float(st['p'][cell] if side == 0 else 1.0 - st['p'][cell]), 'calls_per_day': float(st['N'][cell] / n_days)})
    if rid is None:
        return out
    out['rule'] = G.describe(rid)
    n, r = side_counts(ndec, cf, rid, 0, n_days)
    out['all'] = I.pooled_hit(n, r)
    out['calls_per_day'] = float(n.sum() / n_days)
    out['by_block'] = [dict(block=j, **I.pooled_hit(n[lo:hi], r[lo:hi]), calls_per_day=float(n[lo:hi].sum() / (hi - lo))) for j, (lo, hi) in enumerate(blocks)]
    out['last_block_calls_per_day'] = out['by_block'][-1]['calls_per_day']
    if coins:
        out['by_coin'] = {name: I.pooled_hit(*side_counts(a, b, rid, 0, n_days))['hit'] for name, (a, b) in coins.items()}
    return out


def verdict(nested: dict, fr: dict, rc: dict, pbo: dict, pair: dict) -> dict:
    """E1 to E6 and E8 of section 4 (E7 compares three twin runs and is read off their `nested_hit` lines). Thresholds are the pre-registered ones."""
    pooled = nested.get('pooled')
    hits = [f['test']['hit'] for f in nested['folds'] if f.get('test')]
    e = {}
    e['E1'] = bool(pooled and pooled['hit'] >= 0.530)
    e['E2'] = bool(pooled and pooled['lb975'] > 0.510)
    e['E3'] = bool(len(hits) >= 10 and sum(h > 0.5 for h in hits) >= 8 and min(hits) >= 0.480)
    e['E4'] = bool(rc and rc['p'] < 0.05)
    e['E5'] = bool(pair and pair['diff'] >= 0.010 and pair['lb90'] > 0)
    e['E6'] = bool(pbo and pbo['pbo'] <= 0.30)
    e['E8'] = bool(fr.get('calls_per_day', 0) >= 10 and fr.get('last_block_calls_per_day', 0) >= 5)
    e['all_but_E7'] = all(e.values())
    return e
