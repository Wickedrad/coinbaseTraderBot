"""Day-clustered statistics and the three overfitting checks of PREREG-3.md section 4: Reality Check (E4), paired day bootstrap (E5), PBO (E6).

Arrays are per cell and per UTC day, both coins pooled: `ndec` decided calls, `cf` calls where the FADE side is right (the follow side is right on
ndec - cf). A rule is a cell and a side; hit rates and standard errors are ratio estimators clustered by day.
"""
import itertools

import numpy as np

Z975 = 1.959963984540054        # one-sided 97.5%
Z90 = 1.2815515655446004        # one-sided 90%
CH = 2520                       # cells per chunk (float64 chunk = 2520 x 2496 x 8 B = 50 MB)


def ratio_se(n: np.ndarray, c: np.ndarray) -> tuple:
    """n, c: (R, d) per-day counts. Returns (N, C, p, se) with p = C/N and se = day-cluster standard error of p:
    sqrt(D/(D-1) * sum_d (c_d - p n_d)^2) / N, D = days with a decided call. nan where N = 0 or D < 2."""
    N, C = n.sum(1), c.sum(1)
    with np.errstate(divide='ignore', invalid='ignore'):
        p = C / N
        res = c - p[:, None] * n
        ss = (res * res).sum(1)
        d = (n > 0).sum(1)
        se = np.sqrt(ss * d / np.maximum(d - 1, 1)) / N
    se = np.where(d > 1, se, np.nan)
    return N, C, p, se


def window_stats(ndec: np.ndarray, cf: np.ndarray, lo: int, hi: int) -> dict:
    """Per cell over days [lo, hi): decided N, fade-right count, fade hit p, cluster se."""
    n_cell = ndec.shape[0]
    out = {x: np.zeros(n_cell) for x in ('N', 'R', 'p', 'se')}
    for s in range(0, n_cell, CH):
        sl = slice(s, min(n_cell, s + CH))
        N, R, p, se = ratio_se(ndec[sl, lo:hi].astype(np.float64), cf[sl, lo:hi].astype(np.float64))
        out['N'][sl], out['R'][sl], out['p'][sl], out['se'][sl] = N, R, p, se
    out['days'] = hi - lo
    return out


def pooled_hit(n: np.ndarray, r: np.ndarray) -> dict:
    """One rule's per-day decided and right counts -> pooled hit, day-cluster se and the 97.5% lower bound."""
    n, r = np.asarray(n, float), np.asarray(r, float)
    N, R, p, se = ratio_se(n[None, :], r[None, :])
    N, R, p, se = float(N[0]), float(R[0]), float(p[0]), float(se[0])
    return {'N': int(N), 'right': int(R), 'hit': p, 'se': se, 'lb975': p - Z975 * se}


def stationary_indices(rng, n_boot: int, n_days: int, mean_block: float) -> np.ndarray:
    """Stationary bootstrap (Politis and Romano) of day indices: each step continues the block with probability 1 - 1/mean_block, else restarts at a random day."""
    restart = rng.random((n_boot, n_days)) < 1.0 / mean_block
    restart[:, 0] = True
    starts = rng.integers(0, n_days, size=(n_boot, n_days))
    pos = np.arange(n_days)
    seg = np.maximum.accumulate(np.where(restart, pos, 0), axis=1)
    base = np.take_along_axis(starts, seg, axis=1)
    return (base + pos - seg) % n_days


def counts_matrix(idx: np.ndarray, n_days: int) -> np.ndarray:
    """(B, D) how many times each day appears in each resample."""
    n_boot = idx.shape[0]
    flat = (np.arange(n_boot)[:, None] * n_days + idx).ravel()
    return np.bincount(flat, minlength=n_boot * n_days).reshape(n_boot, n_days).astype(np.float64)


def reality_check(ndec: np.ndarray, cf: np.ndarray, seed: int = 20261123, n_boot: int = 2000, mean_block: float = 5.0, min_per_day: float = 3.0) -> dict:
    """White's Reality Check, studentised (E4): statistic = max over every eligible rule of (hit - 0.5) / se, on all days; the null distribution is the
    stationary bootstrap of days, recentred at the sample excess. A cell and its follow twin have opposite excess, so the max over both sides is the max of |t|."""
    n_cell, n_days = ndec.shape
    rng = np.random.default_rng(seed)
    W = counts_matrix(stationary_indices(rng, n_boot, n_days, mean_block), n_days)
    eligible = ndec.sum(1) / n_days >= min_per_day
    obs_max, obs_cell = -np.inf, -1
    boot_max = np.full(n_boot, -np.inf)
    for s in range(0, n_cell, CH):
        sl = slice(s, min(n_cell, s + CH))
        ok = np.flatnonzero(eligible[sl])
        if not len(ok):
            continue
        n = ndec[sl][ok].astype(np.float64)
        c = cf[sl][ok].astype(np.float64)
        N, R, p, se = ratio_se(n, c)
        good = np.isfinite(se) & (se > 0)
        if not good.any():
            continue
        n, c, N, R, p, se = n[good], c[good], N[good], R[good], p[good], se[good]
        cells = (s + ok[good])
        t_obs = np.abs(p - 0.5) / se
        j = int(np.argmax(t_obs))
        if t_obs[j] > obs_max:
            obs_max, obs_cell = float(t_obs[j]), int(cells[j])
        x = c - 0.5 * n
        Xb = W @ x.T
        Nb = W @ n.T
        with np.errstate(divide='ignore', invalid='ignore'):
            tb = np.abs(Xb / Nb - (p - 0.5)[None, :]) / se[None, :]
        boot_max = np.maximum(boot_max, np.nanmax(tb, axis=1))
    p_value = float((1 + (boot_max >= obs_max).sum()) / (1 + n_boot))
    return {'p': p_value, 'max_t': obs_max, 'cell': obs_cell, 'eligible_cells': int(eligible.sum()), 'boot_max_q95': float(np.quantile(boot_max, 0.95)),
            'n_boot': n_boot, 'seed': seed}


def paired_bootstrap(n_a, r_a, n_b, r_b, seed: int = 20261124, n_boot: int = 2000) -> dict:
    """E5: rule A's pooled hit minus rule B's, resampling whole days (the same days for both); 90% lower bound."""
    n_a, r_a, n_b, r_b = (np.asarray(x, float) for x in (n_a, r_a, n_b, r_b))
    d = len(n_a)
    rng = np.random.default_rng(seed)
    W = counts_matrix(rng.integers(0, d, size=(n_boot, d)), d)
    with np.errstate(divide='ignore', invalid='ignore'):
        diff = (W @ r_a) / (W @ n_a) - (W @ r_b) / (W @ n_b)
    point = r_a.sum() / n_a.sum() - r_b.sum() / n_b.sum()
    return {'diff': float(point), 'lb90': float(np.nanquantile(diff, 0.10)), 'ub90': float(np.nanquantile(diff, 0.90)), 'n_boot': n_boot, 'seed': seed}


def pbo(ndec: np.ndarray, cf: np.ndarray, blocks: list, min_per_day: float = 3.0, split_chunk: int = 300) -> dict:
    """E6, probability of backtest overfitting by combinatorial symmetric cross-validation (Bailey et al.): every split of the blocks into two equal
    halves; the rule with the best pooled hit on one half is ranked on the other. A block counts for a rule only if the rule averages min_per_day
    decided calls per day there; a rule is in a split only if it has a counting block in both halves. PBO = share of splits whose in-sample winner
    ranks at or below the median out of sample (logit of its relative rank <= 0)."""
    n_cell = ndec.shape[0]
    nb = len(blocks)
    Nb, Rb = np.zeros((n_cell, nb)), np.zeros((n_cell, nb))
    for j, (lo, hi) in enumerate(blocks):
        Nb[:, j] = ndec[:, lo:hi].sum(1, dtype=np.float64)
        Rb[:, j] = cf[:, lo:hi].sum(1, dtype=np.float64)
        keep = Nb[:, j] / (hi - lo) >= min_per_day
        Nb[:, j] *= keep
        Rb[:, j] *= keep
    half = nb // 2
    combos = list(itertools.combinations(range(nb), half))
    is_mask = np.zeros((nb, len(combos)))
    for j, cmb in enumerate(combos):
        is_mask[list(cmb), j] = 1.0
    oo_mask = 1.0 - is_mask
    lam, perf_is, perf_oo = [], [], []
    for s in range(0, len(combos), split_chunk):
        sl = slice(s, min(len(combos), s + split_chunk))
        n_is, r_is = Nb @ is_mask[:, sl], Rb @ is_mask[:, sl]
        n_oo, r_oo = Nb @ oo_mask[:, sl], Rb @ oo_mask[:, sl]
        incl = (n_is > 0) & (n_oo > 0)
        with np.errstate(divide='ignore', invalid='ignore'):
            p_is, p_oo = r_is / n_is, r_oo / n_oo
        valid = np.concatenate([incl, incl])                       # fade rows then follow rows
        pi = np.where(valid, np.concatenate([p_is, 1 - p_is]), -np.inf)
        po = np.where(valid, np.concatenate([p_oo, 1 - p_oo]), np.nan)
        best = np.argmax(pi, axis=0)
        cols = np.arange(pi.shape[1])
        sel = po[best, cols]
        cnt = valid.sum(0)
        less = (po < sel[None, :]).sum(0)
        eq = (po == sel[None, :]).sum(0)
        rank = less + (eq + 1) / 2.0
        omega = rank / (cnt + 1.0)
        lam.append(np.log(omega / (1.0 - omega)))
        perf_is.append(pi[best, cols])
        perf_oo.append(sel)
    lam = np.concatenate(lam)
    return {'pbo': float((lam <= 0).mean()), 'splits': int(len(combos)), 'median_logit': float(np.median(lam)),
            'mean_is_best': float(np.mean(np.concatenate(perf_is))), 'mean_oos_of_best': float(np.nanmean(np.concatenate(perf_oo)))}
