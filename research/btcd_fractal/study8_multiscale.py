#!/usr/bin/env python3
"""Round 8 trial [2] multiscale: does a scale-free (sigma-unit) regime grammar learned at 5-21-day scales transfer
unchanged to the 91-day scale and add to M2 + BTC drawdown, or is BTC.D self-similar only in the way any
heteroskedastic random walk is?  See ROUND8_PLAN.md section '[2] multiscale'.

  python3 research/btcd_fractal/study8_multiscale.py --data research/btcd_fractal/data --out research/btcd_fractal/out8/multiscale [--nulls N] [--fast]

Point in time. Everything lives on the daily grid; weekly rows are Sundays sampled from it. Every rolling statistic
is closed-left and shifted one bar (the current close enters only as x_t). The HMM is fitted at each 91-day refit on
rows ending 2 x 21 + 7 = 49 days before the refit, its states are labelled FALL / FLAT / RISE by the training-window
mean of btcd_r1 and frozen, and state probabilities are FILTERED by an in-module forward pass along the stride-s
chain ending at t (never smoothed). The logistic scaler and weights come from training rows only. The fractal model
never sees M2, the halving clock or the all-time high; those stay in the comparators. Global sigma exists only as the
decoy. Duration statistics are descriptive (visits ended before t) and never feed a fit.
"""
import argparse
import json
import os
import sys
import time
import warnings
from datetime import datetime, timezone
from multiprocessing import get_context
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import study8_common as C  # noqa: E402
from study8_baselines import SIGNALS, run_fixed  # noqa: E402

try:
    from numba import njit
    HAVE_NUMBA = True
except Exception:  # pragma: no cover - numpy fallback (slow but identical)
    HAVE_NUMBA = False

    def njit(*a, **k):
        if a and callable(a[0]):
            return a[0]
        return lambda f: f

# ------------------------------------------------------------------------------------------- pre-registered constants
SCALES_TRAIN = [5, 7, 13, 21]
SCALES_LADDER = [30, 45, 65, 91]
E0_SCALES = [5, 7, 13, 21, 30, 45, 65, 91]
S_WEEK = 91
KS = (1.5, 2.0, 3.0)
KP = 2.0
FEATS_A = ["btcd_r1", "btcd_r4", "btcd_dd", "btcd_pos", "btcd_vr", "btc_dd", "btc_r1"]
FEATS_B = FEATS_A + ["eth_r1", "eth_r4", "alt_r1", "usdt_r1"]
FEATS_BTCD = ["btcd_r1", "btcd_r4", "btcd_dd", "btcd_pos", "btcd_vr"]  # ablation: BTC.D's own geometry only
EMIS = ["btcd_r1", "btcd_vr", "btc_r1", "eth_r1"]
K_STATES = 3
STATE_NAMES = ["FALL", "FLAT", "RISE"]
FIRST_FORECAST = "2017-10-01"  # warm-up forecasts on thin training so the stack has history; evaluation from EVAL_START
EVAL_START = "2019-01-06"
REFIT_DAYS = 91
LABEL_MARGIN = 7
MIN_SHIFT_DAYS = 182
LOG_LINES = [0]


def say(s):
    if LOG_LINES[0] < 60:
        print(s)
        LOG_LINES[0] += 1


def kn(k):
    return f"fall{k:g}"


def r3(v):
    return None if v is None or (isinstance(v, float) and not np.isfinite(v)) else round(float(v), 3)


# ------------------------------------------------------------------------------------------------- levels, features
def levels(D):
    lev = {"x": pd.Series(C.logit(D["BTC.D"].values), index=D.index), "p": np.log(D["BTCUSD"])}
    if "ETHBTC" in D:
        lev["e"] = np.log(D["ETHBTC"])
    if "TOTAL3" in D:
        lev["a"] = np.log(D["TOTAL3"]) - np.log(D["BTCUSD"])
    if "USDT.D" in D:
        lev["u"] = pd.Series(C.logit(D["USDT.D"].clip(lower=0.01).values), index=D.index)
    return lev


def tsig(x, s):
    """sigma_s(t): std of s-bar changes over the trailing 8s bars, closed-left, shifted one bar."""
    return x.diff(s).rolling(8 * s, min_periods=4 * s).std().shift(1)


def scale_features(lev, s, fixed_sigma=None):
    """Dimensionless features at scale s on the daily grid. Rolling windows end at t-1; x_t enters explicitly."""
    x, p = lev["x"], lev["p"]
    F = pd.DataFrame(index=x.index)
    sig = tsig(x, s) if fixed_sigma is None else pd.Series(float(fixed_sigma), index=x.index)
    F["btcd_r1"] = (x - x.shift(s)) / sig
    F["btcd_r4"] = (x - x.shift(4 * s)) / (2 * sig)
    mx, mn = x.rolling(4 * s).max().shift(1), x.rolling(4 * s).min().shift(1)
    F["btcd_dd"] = (x - mx) / (mx - mn).replace(0, np.nan)
    mx, mn = x.rolling(8 * s).max().shift(1), x.rolling(8 * s).min().shift(1)
    F["btcd_pos"] = (x - mn) / (mx - mn).replace(0, np.nan)
    d = x.diff()
    F["btcd_vr"] = np.log(d.rolling(2 * s).std().shift(1) / d.rolling(8 * s).std().shift(1))
    mx, mn = p.rolling(8 * s).max().shift(1), p.rolling(8 * s).min().shift(1)
    F["btc_dd"] = (p - mx) / (mx - mn).replace(0, np.nan)
    F["btc_r1"] = (p - p.shift(s)) / tsig(p, s)
    if "e" in lev:
        e, se = lev["e"], tsig(lev["e"], s)
        F["eth_r1"] = (e - e.shift(s)) / se
        F["eth_r4"] = (e - e.shift(4 * s)) / (2 * se)
    if "a" in lev:
        F["alt_r1"] = (lev["a"] - lev["a"].shift(s)) / tsig(lev["a"], s)
    if "u" in lev:
        F["usdt_r1"] = (lev["u"] - lev["u"].shift(s)) / tsig(lev["u"], s)
    F["sigma"] = sig
    return F.replace([np.inf, -np.inf], np.nan)


def scale_targets(x, sig, s, ks):
    """fall_k(s): x falls >= k sigma_s(t) below x_t within the next 2s bars (t+1 .. t+2s)."""
    fut = x[::-1].rolling(2 * s).min()[::-1].shift(-1)
    T = pd.DataFrame(index=x.index)
    ok = fut.notna() & sig.notna()
    for k in ks:
        T[kn(k)] = ((fut - x) <= -k * sig).astype(float).where(ok)
    return T


# ------------------------------------------------------------------------------------------------- HMM (numpy/numba)
@njit(cache=False)
def _fb(logB, starts, ends, A, pi):
    """Scaled forward-backward over concatenated sequences. Returns gamma (N,K), summed xi (K,K), log-likelihood."""
    N, K = logB.shape
    gamma = np.zeros((N, K))
    xi = np.zeros((K, K))
    alpha = np.zeros((N, K))
    bt = np.zeros((N, K))
    c = np.zeros(N)
    ll = 0.0
    for q in range(starts.shape[0]):
        a, b = starts[q], ends[q]
        for t in range(a, b):
            m = logB[t, 0]
            for k in range(1, K):
                if logB[t, k] > m:
                    m = logB[t, k]
            tot = 0.0
            for k in range(K):
                bt[t, k] = np.exp(logB[t, k] - m)
                if t == a:
                    alpha[t, k] = pi[k] * bt[t, k]
                else:
                    sacc = 0.0
                    for j in range(K):
                        sacc += alpha[t - 1, j] * A[j, k]
                    alpha[t, k] = sacc * bt[t, k]
                tot += alpha[t, k]
            c[t] = tot
            for k in range(K):
                alpha[t, k] /= tot
            ll += np.log(tot) + m
        beta = np.ones(K)
        for t in range(b - 1, a - 1, -1):
            tot = 0.0
            for k in range(K):
                gamma[t, k] = alpha[t, k] * beta[k]
                tot += gamma[t, k]
            for k in range(K):
                gamma[t, k] /= tot
            if t > a:
                nb = np.zeros(K)
                for j in range(K):
                    sacc = 0.0
                    for k in range(K):
                        v = A[j, k] * bt[t, k] * beta[k] / c[t]
                        xi[j, k] += alpha[t - 1, j] * v
                        sacc += v
                    nb[j] = sacc
                beta = nb
    return gamma, xi, ll


@njit(cache=False)
def _filter(logB, starts, ends, A, pi):
    """Forward filter only: P(state_t | obs_<=t) along each sequence. Never looks ahead."""
    N, K = logB.shape
    alpha = np.full((N, K), np.nan)
    for q in range(starts.shape[0]):
        a, b = starts[q], ends[q]
        for t in range(a, b):
            m = logB[t, 0]
            for k in range(1, K):
                if logB[t, k] > m:
                    m = logB[t, k]
            tot = 0.0
            for k in range(K):
                bk = np.exp(logB[t, k] - m)
                if t == a:
                    alpha[t, k] = pi[k] * bk
                else:
                    sacc = 0.0
                    for j in range(K):
                        sacc += alpha[t - 1, j] * A[j, k]
                    alpha[t, k] = sacc * bk
                tot += alpha[t, k]
            for k in range(K):
                alpha[t, k] /= tot
    return alpha


def gauss_ll(X, mu, var):
    return -0.5 * (np.log(2 * np.pi * var).sum(1)[None, :] + (((X[:, None, :] - mu[None, :, :]) ** 2) / var[None, :, :]).sum(2))


def build_chains(fin, s, end):
    """Stride-s chains (one per phase) over rows < end with finite emissions. Returns (order, starts, ends)."""
    orders, starts, ends, off = [], [], [], 0
    for j in range(s):
        ii = np.arange(j, end, s)
        ii = ii[fin[ii]]
        if len(ii) >= 2:
            orders.append(ii)
            starts.append(off)
            ends.append(off + len(ii))
            off += len(ii)
    if not orders:
        z = np.zeros(0, np.int64)
        return z, z, z
    return np.concatenate(orders).astype(np.int64), np.array(starts, np.int64), np.array(ends, np.int64)


def init_terciles(X):
    q = np.quantile(X[:, 0], [1 / 3, 2 / 3])
    g = np.digitize(X[:, 0], q)
    mu = np.array([X[g == k].mean(0) if (g == k).sum() > 1 else X.mean(0) for k in range(K_STATES)])
    var = np.array([X[g == k].var(0) if (g == k).sum() > 1 else X.var(0) for k in range(K_STATES)]) + 1e-3
    A = np.full((K_STATES, K_STATES), 0.1) + np.eye(K_STATES) * 0.7
    return mu, var, A, np.full(K_STATES, 1.0 / K_STATES)


def hmm_em(X, starts, ends, init, n_iter, tol=1e-5):
    mu, var, A, pi = [np.ascontiguousarray(np.array(v, float)) for v in init]
    ll_prev = -np.inf
    ll = -np.inf
    for _ in range(max(1, n_iter)):
        gamma, xi, ll = _fb(gauss_ll(X, mu, var), starts, ends, A, pi)
        w = gamma.sum(0) + 1e-9
        mu = np.ascontiguousarray((gamma.T @ X) / w[:, None])
        var = np.ascontiguousarray(np.maximum((gamma.T @ (X ** 2)) / w[:, None] - mu ** 2, 1e-3))
        A = np.maximum(xi, 0) + 1e-4
        A = np.ascontiguousarray(A / A.sum(1, keepdims=True))
        pi = gamma[starts].mean(0) + 1e-4
        pi = np.ascontiguousarray(pi / pi.sum())
        if ll - ll_prev < tol * abs(ll):
            break
        ll_prev = ll
    return (mu, var, A, pi), float(ll)


def hmm_fit(X, starts, ends, n_iter, warm=None):
    best = None
    for init in [init_terciles(X)] + ([warm] if warm is not None else []):
        params, ll = hmm_em(X, starts, ends, init, n_iter)
        if best is None or ll > best[1]:
            best = (params, ll)
    return best


def hazard(alpha, A, fall):
    """h_m = 1 - alpha_nonFALL Q^m 1 (includes current FALL occupancy); E[T] = alpha_nonFALL (I-Q)^-1 1 in steps."""
    nf = [k for k in range(K_STATES) if k != fall]
    Q = A[np.ix_(nf, nf)]
    one = np.ones(len(nf))
    a = alpha[:, nf]
    h1 = 1 - a @ (Q @ one)
    h2 = 1 - a @ (Q @ Q @ one)
    ET = a @ np.linalg.solve(np.eye(len(nf)) - Q, one)
    return h1, h2, ET


def hmm_walk(FE, idx, train_scales, all_scales, first, n_iter, freeze=False, fixed_params=None, lag=None, emis=EMIS):
    """Walk-forward HMM: refit every 91 days on rows < t - lag; filtered posteriors for every scale (own forward pass)."""
    N = len(idx)
    lag = lag if lag is not None else 2 * max(train_scales) + LABEL_MARGIN
    E = {s: np.ascontiguousarray(FE[s][list(emis)].values.astype(float)) for s in all_scales}
    fin = {s: np.isfinite(E[s]).all(1) for s in all_scales}
    pt = int(np.searchsorted(idx, pd.Timestamp(first)))
    refits, warm, frozen = [], None, fixed_params
    while pt < N:
        cut = pt - lag
        if frozen is None:
            Xs, sts, ens, off = [], [], [], 0
            for s in train_scales:
                order, st, en = build_chains(fin[s], s, cut)
                if len(order):
                    Xs.append(E[s][order])
                    sts.append(st + off)
                    ens.append(en + off)
                    off += len(order)
            X = np.ascontiguousarray(np.vstack(Xs))
            params, ll = hmm_fit(X, np.concatenate(sts), np.concatenate(ens), n_iter, warm)
            warm, ntr = params, len(X)
            if freeze:
                frozen = params
        else:
            params, ll, ntr = frozen, None, 0
        mu, var, A, pi = params
        te = min(N, pt + REFIT_DAYS)
        alphas = {}
        for s in all_scales:
            order, st, en = build_chains(fin[s], s, te)
            full = np.full((N, K_STATES), np.nan)
            if len(order):
                full[order] = _filter(gauss_ll(E[s][order], mu, var), st, en, A, pi)
            alphas[s] = full
        refits.append({"pt": pt, "cut": cut, "params": params, "fall": int(np.argmin(mu[:, 0])), "ll": ll, "nTrain": ntr, "alphas": alphas})
        pt = te
    return refits


def classifier_walk(refits, FE, TG, idx, feats, train_scales, all_scales, ks, lam=1.0, use_states=True):
    """Harness logistic on [features + 3 filtered state probabilities], trained on pooled small-scale rows < cut,
    z-scored from training rows, applied unchanged at every scale on the test block."""
    N = len(idx)
    preds = {k: {s: np.full(N, np.nan) for s in all_scales} for k in ks}
    models = []
    Fv = {s: FE[s][feats].values.astype(float) for s in all_scales}
    for r in refits:
        pt, cut = r["pt"], r["cut"]
        te = min(N, pt + REFIT_DAYS)
        Xtr, ytr = {k: [] for k in ks}, {k: [] for k in ks}
        for s in train_scales:
            Fm = np.c_[Fv[s], r["alphas"][s]] if use_states else np.c_[Fv[s], np.where(np.isfinite(r["alphas"][s][:, :1]), 0.0, np.nan)]
            m = np.isfinite(Fm).all(1)
            m[cut:] = False
            for k in ks:
                y = TG[s][kn(k)].values
                mk = m & np.isfinite(y)
                Xtr[k].append(Fm[mk])
                ytr[k].append(y[mk])
        mod = {}
        for k in ks:
            X = np.vstack(Xtr[k])
            y = np.concatenate(ytr[k])
            if len(X) < 100 or y.sum() < 5 or (1 - y).sum() < 5:
                continue
            mu, sd = C.zfit(X)
            mod[k] = (mu, sd, C.logistic_fit(C.zapply(X, mu, sd), y, lam=lam))
        for s in all_scales:
            Fm = np.c_[Fv[s][pt:te], r["alphas"][s][pt:te]] if use_states else np.c_[Fv[s][pt:te], np.where(np.isfinite(r["alphas"][s][pt:te, :1]), 0.0, np.nan)]
            ok = np.isfinite(Fm).all(1)
            if not ok.any():
                continue
            for k, (mu, sd, w) in mod.items():
                blk = preds[k][s][pt:te]
                blk[ok] = C.logistic_predict(C.zapply(Fm[ok], mu, sd), w)
        models.append(mod)
    return preds, models


def stitch(refits, scales, N):
    """Point-in-time state probabilities (ordered FALL, FLAT, RISE) and hazards from each refit's own test block."""
    pstate = {s: np.full((N, K_STATES), np.nan) for s in scales}
    haz = {s: {"h1": np.full(N, np.nan), "h2": np.full(N, np.nan), "ET": np.full(N, np.nan)} for s in scales}
    for r in refits:
        pt, te = r["pt"], min(N, r["pt"] + REFIT_DAYS)
        mu, var, A, pi = r["params"]
        order = np.argsort(mu[:, 0])
        for s in scales:
            al = r["alphas"][s][pt:te]
            pstate[s][pt:te] = al[:, order]
            h1, h2, ET = hazard(al, A, r["fall"])
            haz[s]["h1"][pt:te], haz[s]["h2"][pt:te], haz[s]["ET"][pt:te] = h1, h2, ET
    return pstate, haz


# ------------------------------------------------------------------------------------------------- scoring helpers
def n_spells(y):
    return len(C.episodes(np.asarray(y, float)))


def auc_rows(score, y, mask=None):
    score, y = np.asarray(score, float), np.asarray(y, float)
    m = np.isfinite(score) & np.isfinite(y)
    if mask is not None:
        m &= np.asarray(mask, bool)
    if m.sum() < 20:
        return None
    return C.auc(score[m], y[m])


def era_of(index):
    ix = pd.DatetimeIndex(index)
    return np.where(ix < pd.Timestamp(C.ERAS[1][1]), 0, np.where(ix < pd.Timestamp(C.ERAS[2][1]), 1, 2))


def strat_auc(score, y, index, mask=None):
    """Era-stratified AUC: only pairs inside the same era are compared, so between-era base-rate differences
    (0.47 / 0.34 / 0.09) earn nothing. Weighted by each era's number of positive-negative pairs."""
    score, y = np.asarray(score, float), np.asarray(y, float)
    m = np.isfinite(score) & np.isfinite(y)
    if mask is not None:
        m &= np.asarray(mask, bool)
    e = era_of(index)
    num = den = 0.0
    for k in range(3):
        mk = m & (e == k)
        a = C.auc(score[mk], y[mk]) if mk.sum() >= 20 else None
        if a is not None:
            w = float((y[mk] > 0.5).sum() * (y[mk] <= 0.5).sum())
            num += a * w
            den += w
    return r3(num / den) if den > 0 else None


def mean_era_auc(score, y, index):
    score, y = np.asarray(score, float), np.asarray(y, float)
    m = np.isfinite(score) & np.isfinite(y)
    e = era_of(index)
    vals = [C.auc(score[m & (e == k)], y[m & (e == k)]) for k in range(3) if (m & (e == k)).sum() >= 20]
    vals = [v for v in vals if v is not None]
    return r3(np.mean(vals)) if vals else None


def era_indicator_auc(score, y, index):
    """AUC of a hindsight three-valued score (= the era's own label rate) on the rows where `score` is finite: the
    floor a pooled AUC must beat before it says anything beyond 'which era is it'."""
    score, y = np.asarray(score, float), np.asarray(y, float)
    m = np.isfinite(score) & np.isfinite(y)
    e = era_of(index)
    lvl = np.full(len(y), np.nan)
    for k in range(3):
        mk = m & (e == k)
        if mk.any():
            lvl[mk] = y[mk].mean()
    return r3(C.auc(lvl[m], y[m])) if m.sum() >= 20 else None


def stationary(A):
    w, v = np.linalg.eig(A.T)
    p = np.real(v[:, int(np.argmin(np.abs(w - 1)))])
    return p / p.sum()


def feature_table(FE, TG, idx, train, all_scales, feats, k, sun, Y_W, weights=None):
    """Transfer diagnostic without fitting: marginal AUC of each raw feature against its own-scale k-sigma target on
    daily rows from EVAL_START (pooled over the training scales, then per scale), and at s = 91 on Sunday rows
    against fall5_26w by era; the learned small-scale weight beside it. An AUC below 0.5 is a negative association."""
    m0 = idx >= pd.Timestamp(EVAL_START)
    out = {}
    for f in feats:
        row = {"perScale": {str(s): r3(auc_rows(FE[s][f].values, TG[s][kn(k)].values, m0)) for s in all_scales}}
        row["smallPooled"] = r3(auc_rows(np.concatenate([FE[s][f].values for s in train]), np.concatenate([TG[s][kn(k)].values for s in train]), np.concatenate([m0] * len(train))))
        fw = pd.Series(FE[S_WEEK][f].values, index=idx).reindex(sun)
        y5 = Y_W["fall5_26w"].reindex(fw.index)
        mw = np.asarray(fw.index >= pd.Timestamp(EVAL_START))
        row["s91_fall5_26w"] = r3(auc_rows(fw.values, y5.values, mw))
        row["s91_fall5_26w_byEra"] = {e: r3(auc_rows(fw.values, y5.values, mw & np.asarray(fw.index >= pd.Timestamp(fr)) & np.asarray(fw.index < pd.Timestamp(to)))) for e, fr, to in C.ERAS}
        if weights is not None and f in weights:
            row["weightSmallScale_z"] = weights[f]
            a91 = row["perScale"].get(str(S_WEEK))
            row["signFlipSmallTo91"] = bool(a91 is not None and row["smallPooled"] is not None and np.sign(row["smallPooled"] - 0.5) != np.sign(a91 - 0.5))
            row["weightDisagreesWith91"] = bool(a91 is not None and np.sign(weights[f]) != np.sign(a91 - 0.5) and abs(a91 - 0.5) > 0.05)
        out[f] = row
    return out


def joint_matched_rw(series, rng, bl):
    """Block-resampled increments with the SAME block starts and the same random signs for every series, so the
    cross-series vol clustering and co-movement of BTC.D, BTCUSD and ETHBTC survive while every path is destroyed.
    NaN stretches (series that start late) stay NaN."""
    d = [np.nan_to_num(np.diff(np.asarray(v, float))) for v in series]
    n = len(d[0])
    starts = rng.integers(0, max(1, n - bl), size=int(np.ceil(n / bl)) + 1)
    sign = rng.choice([-1.0, 1.0], size=n)
    out = []
    for v, dv in zip(series, d):
        v = np.asarray(v, float)
        inc = np.concatenate([dv[s:s + bl] for s in starts])[:n] * sign
        first = np.argmax(np.isfinite(v)) if np.isfinite(v).any() else 0
        w = np.r_[np.nan_to_num(v[first]), np.nan_to_num(v[first]) + np.cumsum(inc)]
        w[~np.isfinite(v)] = np.nan
        out.append(w)
    return out


def score_weekly(sc, Y_W, fresh, is_prob):
    """Sunday score series vs the harness weekly targets, from EVAL_START: AUC/Brier by era, spells, fresh-start."""
    s = sc.reindex(Y_W.index)
    s = s[s.index >= pd.Timestamp(EVAL_START)]
    out = {}
    for tg in ("fall5_26w", "fall10_26w"):
        y = Y_W[tg].reindex(s.index)
        met = C.metrics(s, y, True, is_prob=is_prob)
        for name, fr, to in list(C.ERAS) + [("pooled", "2000-01-01", "2100-01-01")]:
            m = (s.index >= pd.Timestamp(fr)) & (s.index < pd.Timestamp(to)) & s.notna() & y.notna()
            if name in met:
                met[name]["spells"] = n_spells(y[m].values)
        fm = fresh.reindex(s.index).fillna(False).values.astype(bool)
        met["freshAUC"] = r3(auc_rows(s.values, y.values, fm))
        met["freshN"] = int((fm & s.notna().values & y.notna().values).sum())
        met["freshBase"] = r3(np.nanmean(y.values[fm & s.notna().values]))
        onset = "onset" + tg[4:]
        met["onsetAUC"] = r3(auc_rows(s.values, Y_W[onset].reindex(s.index).values)) if onset in Y_W else None
        met["stratAUC"] = strat_auc(s.values, y.values, s.index)
        met["meanEraAUC"] = mean_era_auc(s.values, y.values, s.index)
        met["eraIndicatorAUC"] = era_indicator_auc(s.values, y.values, s.index)
        met["freshStratAUC"] = strat_auc(s.values, y.values, s.index, fm)
        out[tg] = met
    out["y13"] = C.metrics(-s, Y_W["y13"].reindex(s.index), False)
    for v in out["y13"].values():
        v.pop("hit", None)  # a probability score has no sign; hit is not meaningful
    return out


def score_daily(pred, y, idx, start=EVAL_START):
    pred, y = np.asarray(pred, float), np.asarray(y, float)
    m = (idx >= pd.Timestamp(start)) & np.isfinite(pred) & np.isfinite(y)
    if m.sum() < 20:
        return {"n": int(m.sum()), "auc": None}
    out = {"n": int(m.sum()), "pos": int(y[m].sum()), "spells": n_spells(np.where(m, y, np.nan)), "auc": r3(C.auc(pred[m], y[m])), "byEra": {}}
    for name, fr, to in C.ERAS:
        me = m & (idx >= pd.Timestamp(fr)) & (idx < pd.Timestamp(to))
        out["byEra"][name] = r3(C.auc(pred[me], y[me])) if me.sum() >= 20 else None
    return out


def pooled_e1(preds, TG, idx, scales, k):
    p = np.concatenate([preds[k][s] for s in scales])
    y = np.concatenate([TG[s][kn(k)].values for s in scales])
    ii = np.concatenate([np.arange(len(idx))] * len(scales))
    m = (ii >= np.searchsorted(idx, pd.Timestamp(EVAL_START))) & np.isfinite(p) & np.isfinite(y)
    return r3(C.auc(p[m], y[m])) if m.sum() > 20 else None


def run_stack(X, Y, cols, tg, min_train=30, lam=1.0):
    def fit(Xtr, ytr):
        mu, sd = C.zfit(Xtr)
        return (mu, sd, C.logistic_fit(C.zapply(Xtr, mu, sd), ytr, lam=lam))

    def predict(model, Xh, te):
        mu, sd, w = model
        return C.logistic_predict(C.zapply(Xh[te], mu, sd), w)
    lag = 26 if "26w" in tg else 13
    pred, _ = C.walk_forward(X[cols], Y[tg], fit, predict, freq="W", label_lag_weeks=lag, min_train=min_train)
    return pred


def run_eramean(Y, tg):
    X = pd.DataFrame({"one": 1.0}, index=Y.index)

    def fit(Xtr, ytr):
        return float(np.mean(ytr[-104:]))

    def predict(model, Xh, te):
        return np.full(len(te), model)
    pred, _ = C.walk_forward(X, Y[tg], fit, predict, freq="W", label_lag_weeks=26)
    return pred


def logit_sum(p_base, p_add, prior):
    z = C.logit(100 * p_base) + C.logit(100 * p_add) - C.logit(100 * prior)
    return pd.Series(1 / (1 + np.exp(-z)), index=p_base.index)


def paired_boot(pa, pb, y, n, rng, bl=26):
    pa, pb, y = np.asarray(pa, float), np.asarray(pb, float), np.asarray(y, float)
    m = np.isfinite(pa) & np.isfinite(pb) & np.isfinite(y)
    pa, pb, y = pa[m], pb[m], y[m]
    Nn = len(y)
    vals = []
    for _ in range(n):
        starts = rng.integers(0, Nn, size=int(np.ceil(Nn / bl)))
        ii = np.concatenate([(np.arange(s, s + bl) % Nn) for s in starts])[:Nn]
        a1, a2 = C.auc(pa[ii], y[ii]), C.auc(pb[ii], y[ii])
        if a1 is not None and a2 is not None:
            vals.append(a1 - a2)
    if not vals:
        return {"n": 0}
    v = np.array(vals)
    return {"n": len(v), "q05": r3(np.quantile(v, 0.05)), "q50": r3(np.quantile(v, 0.5)), "q95": r3(np.quantile(v, 0.95))}


def incremental(stack, base, Y_W, tg, fresh, rng, nboot):
    rows = stack.notna() & base.notna() & Y_W[tg].notna() & (Y_W.index >= pd.Timestamp(EVAL_START))
    s, b, y = stack[rows], base[rows], Y_W.loc[rows, tg]
    ms, mb = C.metrics(s, y, True, is_prob=True), C.metrics(b, y, True, is_prob=True)
    gain = {e: (r3(ms[e]["auc"] - mb[e]["auc"]) if e in ms and e in mb and ms[e]["auc"] is not None and mb[e]["auc"] is not None else None) for e in ms}
    bg = {e: (r3(mb[e]["brier"] - ms[e]["brier"]) if e in ms and e in mb else None) for e in ms}
    fm = fresh.reindex(s.index).fillna(False).values.astype(bool)
    return {"n": int(rows.sum()), "from": str(s.index[0].date()) if len(s) else None, "stack": ms, "base": mb, "aucGain": gain, "brierGain": bg,
            "bootBand": paired_boot(s.values, b.values, y.values, nboot, rng),
            "freshAUC": {"stack": r3(auc_rows(s.values, y.values, fm)), "base": r3(auc_rows(b.values, y.values, fm))}}


def gain_pooled(stack, base, Y, tg):
    rows = stack.notna() & base.notna() & Y[tg].notna() & (Y.index >= pd.Timestamp(EVAL_START))
    if rows.sum() < 20:
        return None
    a1, a2 = C.auc(stack[rows].values, Y.loc[rows, tg].values), C.auc(base[rows].values, Y.loc[rows, tg].values)
    return None if a1 is None or a2 is None else a1 - a2


# ------------------------------------------------------------------------------------------------- E0 / E4 description
def sigma_events(x, sig, s, k):
    """Centred sigma-unit events (description only): peak = max over +-s bars, fall >= k sigma_s(peak) within 2s."""
    v, sg = x.values.astype(float), sig.values.astype(float)
    N, w = len(v), 2 * s
    cmax = pd.Series(v).rolling(2 * s + 1, center=True, min_periods=1).max().values
    out, last = [], -1
    for i in np.where((v >= cmax) & np.isfinite(sg))[0]:
        if i <= last or i + 1 >= N:
            continue
        seg = v[i + 1:i + w + 1]
        j = int(np.argmin(seg))
        depth = v[i] - seg[j]
        if depth >= k * sg[i] and depth > 0:
            path = v[i:i + j + 2]
            bounce = float((path - np.minimum.accumulate(path)).max())
            out.append({"peak": int(i), "trough": int(i + 1 + j), "depth": float(depth), "dsig": float(depth / sg[i]), "dur": (j + 1) / s, "days": j + 1, "relief": bounce / depth})
            last = i + 1 + j
    return out


def e0_stats(x, FE, scales, ks, profile=True):
    out = {}
    for s in scales:
        sig = FE[s]["sigma"]
        nvalid = int(sig.notna().sum())
        Fv = FE[s][FEATS_A].values
        for k in ks:
            ev = sigma_events(x, sig, s, k)
            key = f"s{s}_k{k:g}"
            if len(ev) < 2:
                out[key] = {"n": len(ev)}
                continue
            dsig, dur, rel = (np.array([e[f] for e in ev]) for f in ("dsig", "dur", "relief"))
            slope = float(np.polyfit(np.log(dur), np.log(dsig), 1)[0]) if len(ev) >= 5 and dur.std() > 0 else None
            row = {"n": len(ev), "rate": r3(len(ev) * s / nvalid), "depthSigma": r3(dsig.mean()), "durOverS": r3(dur.mean()), "durOverSq10_90": [r3(np.quantile(dur, 0.1)), r3(np.quantile(dur, 0.9))],
                   "slope": r3(slope), "relief": r3(rel.mean())}
            if profile:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN windows before a series starts
                    prof = np.array([np.nanmean(Fv[e["peak"] - 4 * s:e["peak"]], 0) for e in ev if e["peak"] >= 4 * s and np.isfinite(Fv[e["peak"] - 4 * s:e["peak"]]).any()])
                row["profile"] = {f: r3(np.nanmean(prof[:, j])) for j, f in enumerate(FEATS_A)} if len(prof) else None
            out[key] = row
    return out


def e0_bands(real, surr, keys=("rate", "depthSigma", "durOverS", "slope", "relief")):
    out = {}
    for key, row in real.items():
        if "n" not in row or row.get("rate") is None:
            continue
        b = {}
        for q in keys:
            vals = np.array([s[key][q] for s in surr if key in s and s[key].get(q) is not None], float)
            if len(vals) >= 3 and row.get(q) is not None:
                b[q] = {"real": row[q], "p05": r3(np.quantile(vals, 0.05)), "p95": r3(np.quantile(vals, 0.95)),
                        "outside": bool(row[q] < np.quantile(vals, 0.05) or row[q] > np.quantile(vals, 0.95))}
        out[key] = b
    return out


def visit_lengths(pfall, s, end):
    """Lengths (steps) of FALL visits (P(FALL) > 0.5) along stride-s chains, only visits ended before `end`."""
    lens = []
    for j in range(s):
        run = 0
        for v in pfall[j:end:s]:
            if np.isfinite(v) and v > 0.5:
                run += 1
            else:
                if run > 0:
                    lens.append(run)
                run = 0
    return lens


# ------------------------------------------------------------------------------------------------- workers (fork)
G = {}


def sunday_series(arr, idx, sun):
    return pd.Series(arr, index=idx).reindex(sun)


def null_task(args):
    """Shifted-target null through labelling, logistic fits, transfer, stacks and scoring (HMM cached: unsupervised).
    era=None: circular shift of the whole daily target panel (and the weekly targets by the same weeks), scored
    pooled and by era ('global shift scored by era'). era=<name>: the targets are rolled ONLY inside that era's rows
    (daily and weekly alike) and the era's own AUC is returned: the within-era null the plan prescribes."""
    seed, era = args
    rng = np.random.default_rng(seed)
    N, idx, sun = G["N"], G["idx"], G["sun"]
    if era is None:
        k = int(rng.integers(MIN_SHIFT_DAYS, N - MIN_SHIFT_DAYS))
        TGs = {s: pd.DataFrame(np.roll(G["TG"][s].values, k, axis=0), index=idx, columns=G["TG"][s].columns) for s in G["TG"]}
        YWs = C.shift_targets(G["Y_W"], int(round(k / 7)))
    else:
        name, fr, to = [e for e in C.ERAS if e[0] == era][0]
        pos = np.where((idx >= pd.Timestamp(fr)) & (idx < pd.Timestamp(to)))[0]
        k = int(rng.integers(MIN_SHIFT_DAYS, len(pos) - MIN_SHIFT_DAYS))
        TGs = {}
        for s in G["TG"]:
            v = G["TG"][s].values.copy()
            v[pos] = np.roll(v[pos], k, axis=0)
            TGs[s] = pd.DataFrame(v, index=idx, columns=G["TG"][s].columns)
        wpos = np.where((G["Y_W"].index >= pd.Timestamp(fr)) & (G["Y_W"].index < pd.Timestamp(to)))[0]
        YWs = G["Y_W"].copy()
        for c in YWs.columns:
            v = G["Y_W"][c].values.copy()
            v[wpos] = np.roll(v[wpos], int(round(k / 7)))
            YWs[c] = v
    preds, _ = classifier_walk(G["refits"], G["FE"], TGs, idx, FEATS_A, G["train"], G["all"], [KP])
    P91 = sunday_series(preds[KP][S_WEEK], idx, sun)
    y5 = YWs["fall5_26w"].reindex(P91.index)
    m = P91.index >= pd.Timestamp(EVAL_START)
    if era is not None:
        me = m & (P91.index >= pd.Timestamp(fr)) & (P91.index < pd.Timestamp(to))
        return {"era": era, "e2era": r3(auc_rows(P91[me].values, y5[me].values)), "s91era": score_daily(preds[KP][S_WEEK], TGs[S_WEEK][kn(KP)].values, idx).get("byEra", {}).get(era)}
    out = {"e2": r3(auc_rows(P91[m].values, y5[m].values)), "e2strat": strat_auc(P91.values, y5.values, P91.index, m), "e1": pooled_e1(preds, TGs, idx, G["train"], KP),
           "s91": score_daily(preds[KP][S_WEEK], TGs[S_WEEK][kn(KP)].values, idx)["auc"],
           "h26": r3(auc_rows(G["H26"].reindex(y5.index)[m].values, y5[m].values)), "byEra": {}}
    for name, fr, to in C.ERAS:
        me = m & (P91.index >= pd.Timestamp(fr)) & (P91.index < pd.Timestamp(to))
        out["byEra"][name] = r3(auc_rows(P91[me].values, y5[me].values))
    XS = G["X_S"].copy()
    XS["p91"] = P91.reindex(XS.index)
    base = run_fixed(G["X_W"], YWs, "fall5_26w", "W", True, ["m2_yoy", "btc_dd_ath"])[0]
    st_h = run_stack(XS, YWs, ["m2_yoy", "btc_dd_ath", "h26"], "fall5_26w")
    st_p = run_stack(XS, YWs, ["m2_yoy", "btc_dd_ath", "p91"], "fall5_26w")
    out["gain_h26"] = r3(gain_pooled(st_h, base, YWs, "fall5_26w"))
    out["gain_p91"] = r3(gain_pooled(st_p, base, YWs, "fall5_26w"))
    return out


def reflect(v, lo=20.0, hi=97.0):
    """Fold a path into [lo, hi] by reflection at the boundaries (keeps every increment's magnitude)."""
    span = hi - lo
    return lo + np.abs(((v - lo) % (2 * span)) - span)


def surrogate_pct(pct, kind, rng):
    """Placebo BTC.D in points: matched random walk (block-resampled increments, random signs, BTC.D's own vol path,
    reflected into [20, 97]), an i.i.d.-resampled walk (same marginal increments, NO vol clustering) or an IAAFT
    surrogate (same marginal distribution and power spectrum)."""
    if kind == "rw":
        return reflect(C.matched_rw(pct, rng, block_weeks=13, freq="D"))
    if kind == "rwiid":
        return reflect(C.matched_rw(pct, rng, block_weeks=1 / 7, freq="D"))  # block of 1 bar = i.i.d. resample
    return C.iaaft(pct, rng, it=30)


def surrogate_task(args):
    kind, seed, do_placebo = args
    rng = np.random.default_rng(seed)
    idx, sun = G["idx"], G["sun"]
    x = G["lev"]["x"]
    lev2 = dict(G["lev"])
    if kind == "rwj":  # joint placebo: BTC.D, BTCUSD and ETHBTC resampled with the same block starts and signs
        pct, pv, ev = joint_matched_rw([G["btcd_pct"], G["lev"]["p"].values, G["lev"]["e"].values], rng, C.bars(13, "D"))
        pct = reflect(pct)
        lev2["p"], lev2["e"] = pd.Series(pv, index=x.index), pd.Series(ev, index=x.index)
    else:
        pct = surrogate_pct(G["btcd_pct"], kind, rng)
    xv = C.logit(pct)
    lev2["x"] = pd.Series(xv, index=x.index)
    scales = sorted(set(G["all"]) | set(E0_SCALES))
    FE2 = {s: scale_features(lev2, s) for s in scales}
    TG2 = {s: scale_targets(lev2["x"], FE2[s]["sigma"], s, [KP]) for s in G["all"]}
    PW2 = pd.DataFrame({"BTC.D": pct}, index=x.index).resample("W-SUN").last().ffill()
    YW2 = C.targets(PW2, "W").reindex(G["Y_W"].index)
    fresh2 = C.fresh_mask(PW2, "W").reindex(G["Y_W"].index).fillna(False)
    refits2 = hmm_walk(FE2, idx, G["train"], G["all"], EVAL_START, G["n_iter"], freeze=True)
    preds2, _ = classifier_walk(refits2, FE2, TG2, idx, FEATS_A, G["train"], G["all"], [KP])
    P91 = sunday_series(preds2[KP][S_WEEK], idx, sun)
    y5 = YW2["fall5_26w"].reindex(P91.index)
    m = P91.index >= pd.Timestamp(EVAL_START)
    fm = fresh2.reindex(P91.index).values.astype(bool)
    out = {"kind": kind, "e2": r3(auc_rows(P91[m].values, y5[m].values)), "e2fresh": r3(auc_rows(P91.values, y5.values, m & fm)), "e2strat": strat_auc(P91.values, y5.values, P91.index, m),
           "e1": pooled_e1(preds2, TG2, idx, G["train"], KP), "ladder": {s: score_daily(preds2[KP][s], TG2[s][kn(KP)].values, idx)["auc"] for s in G["all"]},
           "byEra": {}, "e0": e0_stats(lev2["x"], FE2, E0_SCALES, KS, profile=True)}
    pv, _ = classifier_walk(refits2, FE2, TG2, idx, ["btcd_vr"], G["train"], G["all"], [KP], use_states=False)
    out["e1_vrOnly"] = pooled_e1(pv, TG2, idx, G["train"], KP)
    pn, _ = classifier_walk(refits2, FE2, TG2, idx, FEATS_A, G["train"], G["all"], [KP], use_states=False)
    out["e1_noStates"] = pooled_e1(pn, TG2, idx, G["train"], KP)
    out["e2_noStates"] = r3(auc_rows(sunday_series(pn[KP][S_WEEK], idx, sun)[m].values, y5[m].values))
    if kind == "rwj":
        pb, _ = classifier_walk(refits2, FE2, TG2, idx, FEATS_BTCD, G["train"], G["all"], [KP], use_states=False)
        out["e2_btcdOnly"] = r3(auc_rows(sunday_series(pb[KP][S_WEEK], idx, sun)[m].values, y5[m].values))
    for name, fr, to in C.ERAS:
        me = m & (P91.index >= pd.Timestamp(fr)) & (P91.index < pd.Timestamp(to))
        out["byEra"][name] = r3(auc_rows(P91[me].values, y5[me].values))
    if do_placebo:  # decoy regime: the placebo-fitted HMM filtered on REAL rows, logistic on real rows, real targets
        rp = hmm_walk(G["FE"], idx, G["train"], G["all"], EVAL_START, 0, fixed_params=refits2[0]["params"])
        pp, _ = classifier_walk(rp, G["FE"], G["TG"], idx, FEATS_A, G["train"], G["all"], [KP])
        Pp = sunday_series(pp[KP][S_WEEK], idx, sun)
        yr = G["Y_W"]["fall5_26w"].reindex(Pp.index)
        out["placebo_e2"] = r3(auc_rows(Pp[m].values, yr[m].values))
        out["placebo_e1"] = pooled_e1(pp, G["TG"], idx, G["train"], KP)
    return out


def summarize(real, vals, higher=True):
    vals = [v for v in vals if v is not None]
    return C.null_summary(real, vals, higher_is_better=higher)


# ------------------------------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--nulls", type=int, default=100)
    ap.add_argument("--fast", action="store_true")
    ap.add_argument("--procs", type=int, default=4)
    a = ap.parse_args()
    t0 = time.time()
    cfg = {"train": SCALES_TRAIN, "ladder": SCALES_LADDER, "n_iter": 60, "n_shift": a.nulls, "n_within": a.nulls, "n_rw": 100, "n_rwj": 100, "n_iid": 50, "n_iaaft": 50, "n_placebo": 30, "boot": 500}
    if a.fast:
        cfg.update({"train": [7, 21], "ladder": [45, 91], "n_iter": 20, "n_shift": min(a.nulls, 10), "n_within": min(a.nulls, 10), "n_rw": 10, "n_rwj": 10, "n_iid": 5, "n_iaaft": 5, "n_placebo": 10, "boot": 200})
    VERDICT_MIN_NULLS = 50  # below this a p95 is the maximum of a handful of draws: no verdict is printed
    train, all_scales = cfg["train"], cfg["train"] + cfg["ladder"]
    rng = np.random.default_rng(8)
    notes = []
    now_utc = datetime.now(timezone.utc)
    say(f"multiscale start {now_utc.strftime('%Y-%m-%d %H:%M UTC')} / {now_utc.astimezone(ZoneInfo('America/New_York')).strftime('%H:%M %Z')} fast={a.fast} numba={HAVE_NUMBA} "
        f"train={train} ladder={cfg['ladder']} nIter={cfg['n_iter']} nulls={cfg['n_shift']} rw={cfg['n_rw']} iaaft={cfg['n_iaaft']}")

    # ---- data on the daily grid; Sundays are the weekly rows
    D = C.load_daily(a.data)
    idx, N = D.index, len(D)
    lev = levels(D)
    FE = {s: scale_features(lev, s) for s in sorted(set(all_scales) | set(E0_SCALES))}
    TG = {s: scale_targets(lev["x"], FE[s]["sigma"], s, KS) for s in all_scales}
    sun = idx[idx.dayofweek == 6]
    P_W = C.panel(D, "W")
    X_W, _ = C.features(P_W, "W")
    Y_W = C.targets(P_W, "W")
    X_W = X_W[X_W.index >= pd.Timestamp("2016-06-01")]
    Y_W, P_W = Y_W.reindex(X_W.index), P_W.reindex(X_W.index)
    Y_W = C.extra_targets(P_W, Y_W, "W")
    fresh = C.fresh_mask(P_W, "W")
    partial = str(X_W.index[-1].date())
    notes.append(f"Weekly row {partial} is the partial current week (daily panel ends {idx[-1].date()}): provisional, never in training.")

    # ---- leakage check 1: feature rows at t identical on the panel truncated at t and at t+200
    worst = 0.0
    for t in rng.integers(N // 3, N - 250, size=3):
        for end in (int(t), int(t) + 200):
            part = scale_features({k: v.iloc[:end + 1] for k, v in lev.items()}, S_WEEK).iloc[int(t)]
            d = (part - FE[S_WEEK].iloc[int(t)]).abs()
            worst = max(worst, float(np.nanmax(d.values)) if np.isfinite(d.values).any() else 0.0)
    feat_trunc = {"ok": bool(worst <= 1e-9), "maxAbsDiff": worst}

    # ---- real pipeline: HMM walk (refit every 91 days) + classifier walk, all scales filtered
    refits = hmm_walk(FE, idx, train, all_scales, FIRST_FORECAST, cfg["n_iter"])
    preds, models = classifier_walk(refits, FE, TG, idx, FEATS_A, train, all_scales, KS)
    pstate, haz = stitch(refits, all_scales, N)
    t_real = time.time() - t0
    refit_dates = [str(idx[r["pt"]].date()) for r in refits]
    fall_idx = [r["fall"] for r in refits]

    P91 = {k: sunday_series(preds[k][S_WEEK], idx, sun) for k in KS}
    H26 = sunday_series(haz[S_WEEK]["h2"], idx, sun)
    H13 = sunday_series(haz[S_WEEK]["h1"], idx, sun)
    PF91 = sunday_series(pstate[S_WEEK][:, 0], idx, sun)

    # ---- E1 within-scale ceiling and the ladder (sigma target, k = 2, daily rows from EVAL_START)
    within = {str(s): score_daily(preds[KP][s], TG[s][kn(KP)].values, idx) for s in train}
    within["pooled"] = {"auc": pooled_e1(preds, TG, idx, train, KP)}
    within["byK"] = {f"k{k:g}": pooled_e1(preds, TG, idx, train, k) for k in KS}
    ladder = {str(s): score_daily(preds[KP][s], TG[s][kn(KP)].values, idx)["auc"] for s in all_scales}
    within_by_era_s91 = score_daily(preds[KP][S_WEEK], TG[S_WEEK][kn(KP)].values, idx).get("byEra", {})
    say("E1 within-scale AUC (sigma target k=2, daily OOS rows, spells): " + " ".join(f"s{s}={within[str(s)]['auc']}({within[str(s)]['spells']})" for s in train) + f" pooled={within['pooled']['auc']} byK={within['byK']}")
    say("ladder AUC by scale (k=2 sigma target): " + " ".join(f"s{s}={ladder[str(s)]}" for s in all_scales))

    # ---- E2 transfer at s = 91 on Sunday rows against the harness targets
    e2 = {f"classifier_k{k:g}": score_weekly(P91[k], Y_W, fresh, True) for k in KS}
    e2["hazard_h26"] = score_weekly(H26, Y_W, fresh, True)
    e2["hazard_h13"] = score_weekly(H13, Y_W, fresh, True)
    e2["pfall"] = score_weekly(PF91, Y_W, fresh, True)
    y91 = pd.Series(TG[S_WEEK][kn(KP)].values, index=idx).reindex(sun)
    m91 = (P91[KP].index >= pd.Timestamp(EVAL_START))
    e2["sigma2_91"] = C.metrics(P91[KP][m91], y91[m91], True, is_prob=True)
    e2["sigma2_91"]["spells"] = n_spells(y91[m91].values)
    # sigma_91 in points by era: what '2 sigma' meant when each era's AUC was earned, and a k-matched read-out
    # (per Sunday row the trained k in KS closest to 5 points / sigma_91 points) scored on the point label
    p_sun = (D["BTC.D"] / 100.0).reindex(sun)
    sigp_sun = pd.Series(FE[S_WEEK]["sigma"].values, index=idx).reindex(sun) * p_sun * (1 - p_sun) * 100
    sig_by_era = {}
    for name, fr, to in C.ERAS:
        v = sigp_sun[(sigp_sun.index >= pd.Timestamp(fr)) & (sigp_sun.index < pd.Timestamp(to)) & (sigp_sun.index >= pd.Timestamp(EVAL_START))].dropna()
        sig_by_era[name] = {"sigma91_points_median": r3(v.median()), "fivePointsInSigma": r3(5.0 / v.median()) if len(v) and v.median() > 0 else None, "twoSigmaInPoints": r3(2 * v.median()) if len(v) else None}
    e2["sigma91_pointsByEra"] = sig_by_era
    ks_arr = np.array(KS, float)
    k_t = (5.0 / sigp_sun).values
    pick = ks_arr[np.nan_to_num(np.abs(k_t[:, None] - ks_arr[None, :]), nan=1e9).argmin(1)]
    Pk = pd.Series([P91[float(kk)].iloc[j] for j, kk in enumerate(pick)], index=sun).where(np.isfinite(k_t))
    e2["classifier_kmatched"] = score_weekly(Pk, Y_W, fresh, True)
    e2["classifier_kmatched"]["kShare"] = {f"k{kk:g}": r3(np.mean(pick[np.isfinite(k_t) & (sun >= pd.Timestamp(EVAL_START))] == kk)) for kk in KS}
    # hazard arm: is h26 anything beyond FALL occupancy? AUC on the rows where the chain is NOT already in FALL
    pf_w, h_w, y5_w = PF91.reindex(Y_W.index), H26.reindex(Y_W.index), Y_W["fall5_26w"]
    mh = (Y_W.index >= pd.Timestamp(EVAL_START)) & pf_w.notna() & h_w.notna() & y5_w.notna()
    off, on = mh & (pf_w < 0.5), mh & (pf_w >= 0.5)
    e2["hazard_offState"] = {"nOff": int(off.sum()), "nOn": int(on.sum()), "h26_aucOffState": r3(auc_rows(h_w[off].values, y5_w[off].values)), "pfall_aucOffState": r3(auc_rows(pf_w[off].values, y5_w[off].values)),
                             "h26_medianOff": r3(h_w[off].median()), "h26_q10_90_off": [r3(h_w[off].quantile(0.1)), r3(h_w[off].quantile(0.9))], "h26_medianOn": r3(h_w[on].median()) if on.any() else None,
                             "h13_aucOffState": r3(auc_rows(H13.reindex(Y_W.index)[off].values, y5_w[off].values))}
    c2 = e2[f"classifier_k{KP:g}"]
    for tg in ("fall5_26w", "fall10_26w"):
        r = c2[tg]
        say(f"E2 classifier(k=2)->{tg}: " + " ".join(f"{e}={r[e]['auc']}(n{r[e]['n']},sp{r[e]['spells']},brier{r[e].get('brier')}/{r[e].get('brierBase')})" for e in r if isinstance(r[e], dict)) + f" fresh={r['freshAUC']}(n{r['freshN']}) onset={r['onsetAUC']}")
    say(f"E2 classifier(k=2)->sigma2_91: " + " ".join(f"{e}={v['auc']}(brier{v.get('brier')}/{v.get('brierBase')})" for e, v in e2['sigma2_91'].items() if isinstance(v, dict)) + f" | y13 IC pooled={c2['y13'].get('pooled', {}).get('ic')} byEra=" + ",".join(f"{e}:{v['ic']}" for e, v in c2["y13"].items() if e != "pooled"))
    say(f"E2 hazard h26->fall5_26w: " + " ".join(f"{e}={v['auc']}" for e, v in e2['hazard_h26']['fall5_26w'].items() if isinstance(v, dict)) + f" fresh={e2['hazard_h26']['fall5_26w']['freshAUC']} | P(FALL)->fall5: pooled={e2['pfall']['fall5_26w']['pooled']['auc']} | k1.5/k3 pooled fall5={e2['classifier_k1.5']['fall5_26w']['pooled']['auc']}/{e2['classifier_k3']['fall5_26w']['pooled']['auc']} fall10={e2['classifier_k1.5']['fall10_26w']['pooled']['auc']}/{e2['classifier_k3']['fall10_26w']['pooled']['auc']}")
    ho = e2["hazard_offState"]
    say(f"E2 headline (era-stratified AUC, within-era pairs only) fall5_26w: classifier {c2['fall5_26w']['stratAUC']} (mean-of-era {c2['fall5_26w']['meanEraAUC']}, pooled {c2['fall5_26w']['pooled']['auc']}, era-indicator floor {c2['fall5_26w']['eraIndicatorAUC']}, fresh strat {c2['fall5_26w']['freshStratAUC']}) | h26 strat {e2['hazard_h26']['fall5_26w']['stratAUC']} | P(FALL) strat {e2['pfall']['fall5_26w']['stratAUC']} | k-matched-to-5-points strat {e2['classifier_kmatched']['fall5_26w']['stratAUC']} pooled {e2['classifier_kmatched']['fall5_26w']['pooled']['auc']} shares {e2['classifier_kmatched']['kShare']}")
    say(f"sigma_91 in points by era (median; what 2 sigma meant when the AUC was earned): " + " ".join(f"{e}: sigma={v['sigma91_points_median']} 2sig={v['twoSigmaInPoints']}pts 5pts={v['fivePointsInSigma']}sig" for e, v in sig_by_era.items()) + f" | sigma2_91 target spells 2019+: {e2['sigma2_91']['spells']}")
    say(f"hazard off-state (P(FALL)<0.5, n{ho['nOff']} of {ho['nOff'] + ho['nOn']}): h26 AUC {ho['h26_aucOffState']} h13 AUC {ho['h13_aucOffState']} P(FALL) AUC {ho['pfall_aucOffState']} | h26 median off {ho['h26_medianOff']} q10-90 {ho['h26_q10_90_off']} vs on {ho['h26_medianOn']}: h26 is FALL occupancy plus a chain constant")

    # ---- E3 controls on the real series
    ctrl = {}
    # (a) set B features (same HMM), (b) frozen HMM (fit once on 2014-18, like the placebo pipeline), (c) reverse transfer (fit at s=91 only), (d) global-sigma decoy
    predsB, _ = classifier_walk(refits, FE, TG, idx, FEATS_B, train, all_scales, [KP])
    ctrl["setB"] = {"fall5_26w": score_weekly(sunday_series(predsB[KP][S_WEEK], idx, sun), Y_W, fresh, True)["fall5_26w"], "e1": pooled_e1(predsB, TG, idx, train, KP)}
    preds_nh, _ = classifier_walk(refits, FE, TG, idx, FEATS_A, train, all_scales, [KP], use_states=False)
    ctrl["noHMM_featuresOnly"] = {"fall5_26w": score_weekly(sunday_series(preds_nh[KP][S_WEEK], idx, sun), Y_W, fresh, True)["fall5_26w"], "e1": pooled_e1(preds_nh, TG, idx, train, KP),
                                  "ladder": {str(s): score_daily(preds_nh[KP][s], TG[s][kn(KP)].values, idx)["auc"] for s in all_scales}}
    preds_bo, _ = classifier_walk(refits, FE, TG, idx, FEATS_BTCD, train, all_scales, [KP], use_states=False)
    ctrl["btcdOnly_noBTC_noHMM"] = {"fall5_26w": score_weekly(sunday_series(preds_bo[KP][S_WEEK], idx, sun), Y_W, fresh, True)["fall5_26w"], "e1": pooled_e1(preds_bo, TG, idx, train, KP),
                                    "ladder": {str(s): score_daily(preds_bo[KP][s], TG[s][kn(KP)].values, idx)["auc"] for s in all_scales}}
    preds_bs, _ = classifier_walk(refits, FE, TG, idx, FEATS_BTCD, train, all_scales, [KP], use_states=True)
    ctrl["btcdOnly_withHMM"] = {"fall5_26w": score_weekly(sunday_series(preds_bs[KP][S_WEEK], idx, sun), Y_W, fresh, True)["fall5_26w"], "e1": pooled_e1(preds_bs, TG, idx, train, KP)}
    refits_fz = hmm_walk(FE, idx, train, all_scales, EVAL_START, cfg["n_iter"], freeze=True)
    preds_fz, _ = classifier_walk(refits_fz, FE, TG, idx, FEATS_A, train, all_scales, [KP])
    ctrl["frozenHMM"] = {"fall5_26w": score_weekly(sunday_series(preds_fz[KP][S_WEEK], idx, sun), Y_W, fresh, True)["fall5_26w"], "e1": pooled_e1(preds_fz, TG, idx, train, KP)}
    refits_rv = hmm_walk(FE, idx, [S_WEEK], [S_WEEK], EVAL_START, cfg["n_iter"], lag=2 * S_WEEK + LABEL_MARGIN)
    preds_rv, _ = classifier_walk(refits_rv, FE, TG, idx, FEATS_A, [S_WEEK], [S_WEEK], [KP])
    ctrl["reverse_fit91"] = {"fall5_26w": score_weekly(sunday_series(preds_rv[KP][S_WEEK], idx, sun), Y_W, fresh, True)["fall5_26w"],
                             "sigma2_91": score_daily(preds_rv[KP][S_WEEK], TG[S_WEEK][kn(KP)].values, idx)["auc"], "nTrainFirst": refits_rv[0]["nTrain"]}
    preds_vr, _ = classifier_walk(refits, FE, TG, idx, ["btcd_vr"], train, all_scales, [KP], use_states=False)
    ctrl["vrOnly_noHMM"] = {"fall5_26w": score_weekly(sunday_series(preds_vr[KP][S_WEEK], idx, sun), Y_W, fresh, True)["fall5_26w"], "e1": pooled_e1(preds_vr, TG, idx, train, KP),
                            "ladder": {str(s): score_daily(preds_vr[KP][s], TG[s][kn(KP)].values, idx)["auc"] for s in all_scales}}
    FEd = {}  # per-window-demeaned variant (vol-collapse confound): each feature minus its trailing 8s-bar mean, shifted one bar
    for s in all_scales:
        Fd = FE[s][FEATS_A] - FE[s][FEATS_A].rolling(8 * s, min_periods=4 * s).mean().shift(1)
        Fd["sigma"] = FE[s]["sigma"]
        FEd[s] = Fd
    preds_dm, _ = classifier_walk(refits, FEd, TG, idx, FEATS_A, train, all_scales, [KP], use_states=False)
    ctrl["demeaned_noHMM"] = {"fall5_26w": score_weekly(sunday_series(preds_dm[KP][S_WEEK], idx, sun), Y_W, fresh, True)["fall5_26w"], "e1": pooled_e1(preds_dm, TG, idx, train, KP),
                              "ladder": {str(s): score_daily(preds_dm[KP][s], TG[s][kn(KP)].values, idx)["auc"] for s in all_scales}}
    gsig = {s: float(np.nanstd(lev["x"].diff(s).values)) for s in all_scales}
    FEg = {s: scale_features(lev, s, fixed_sigma=gsig[s]) for s in all_scales}
    TGg = {s: scale_targets(lev["x"], FEg[s]["sigma"], s, [KP]) for s in all_scales}
    refits_g = hmm_walk(FEg, idx, train, all_scales, FIRST_FORECAST, cfg["n_iter"])
    preds_g, _ = classifier_walk(refits_g, FEg, TGg, idx, FEATS_A, train, all_scales, [KP])
    ctrl["decoy_globalSigma"] = {"fall5_26w": score_weekly(sunday_series(preds_g[KP][S_WEEK], idx, sun), Y_W, fresh, True)["fall5_26w"], "e1": pooled_e1(preds_g, TGg, idx, train, KP),
                                 "ladder": {str(s): score_daily(preds_g[KP][s], TGg[s][kn(KP)].values, idx)["auc"] for s in all_scales}}
    say("E3 controls fall5_26w pooled AUC: " + " ".join(f"{k}={v['fall5_26w']['pooled']['auc']}" for k, v in ctrl.items()) + f" | E1 pooled: setB={ctrl['setB']['e1']} noHMM={ctrl['noHMM_featuresOnly']['e1']} vrOnly={ctrl['vrOnly_noHMM']['e1']} demeaned={ctrl['demeaned_noHMM']['e1']} frozen={ctrl['frozenHMM']['e1']} globalSigma={ctrl['decoy_globalSigma']['e1']} | reverse sigma2_91={ctrl['reverse_fit91']['sigma2_91']} (first fit n={ctrl['reverse_fit91']['nTrainFirst']})")
    say("E3 controls fall5_26w era-stratified AUC: " + " ".join(f"{k}={v['fall5_26w']['stratAUC']}" for k, v in ctrl.items()))
    weights_small = None
    if models and models[-1].get(KP) is not None:
        weights_small = {n: r3(w) for n, w in zip(["bias"] + FEATS_A + [f"state{j}" for j in range(K_STATES)], models[-1][KP][2])}
    ftab = feature_table(FE, TG, idx, train, all_scales, FEATS_A, KP, sun, Y_W, weights_small)
    say("per-feature marginal AUC (no fitting; own-scale 2-sigma target, daily rows 2019+): " + " ".join(f"{f}: small {v['smallPooled']} -> s91 {v['perScale'].get(str(S_WEEK))} (fall5_26w@91 {v['s91_fall5_26w']}, w {v.get('weightSmallScale_z')}{', MARGINAL FLIPS' if v.get('signFlipSmallTo91') else ''}{', WEIGHT MIS-SIGNED AT 91' if v.get('weightDisagreesWith91') else ''})" for f, v in ftab.items()))

    # ---- comparators through the harness (weekly) and the incremental test
    comp = {}
    for name, cols in (("fixed5", SIGNALS), ("m2only", ["m2_yoy"]), ("m2btc", ["m2_yoy", "btc_dd_ath"]), ("clock", ["days_since_halving"])):
        comp[name] = {}
        for tg in ("fall5_26w", "fall10_26w"):
            pred, _ = run_fixed(X_W, Y_W, tg, "W", True, cols)
            comp[name][tg] = score_weekly(pred, Y_W, fresh, True)[tg]
            comp[name][tg]["today"] = r3(pred.reindex([sun[-1]]).iloc[0]) if pred.notna().any() else None  # last complete Sunday close
            comp[name][tg]["todayProvisionalRow"] = r3(pred.dropna().iloc[-1]) if pred.notna().any() else None  # partial current week
            comp[name][tg + "_pred"] = pred
        pred, _ = run_fixed(X_W, Y_W, "y13", "W", False, cols)
        comp[name]["y13"] = C.metrics(pred, Y_W["y13"], False)
    comp["eraMean"] = {tg: score_weekly(run_eramean(Y_W, tg), Y_W, fresh, True)[tg] for tg in ("fall5_26w", "fall10_26w")}
    base_rate = {tg: r3(Y_W.loc[Y_W.index >= pd.Timestamp(EVAL_START), tg].mean()) for tg in ("fall5_13w", "fall5_26w", "fall10_26w")}
    say("comparators fall5_26w AUC by era/pooled: " + " | ".join(f"{k}: " + ",".join(f"{e}={v['fall5_26w'][e]['auc']}" for e in v["fall5_26w"] if isinstance(v["fall5_26w"][e], dict)) for k, v in comp.items()))
    say("comparators fall10_26w pooled AUC: " + " ".join(f"{k}={v['fall10_26w']['pooled']['auc']}" for k, v in comp.items()) + f" | base rates 2019+ {base_rate} | fall10_26w positive spells 2019+: {n_spells(Y_W.loc[Y_W.index >= pd.Timestamp(EVAL_START), 'fall10_26w'].values)} (Oct 2020 - May 2021 is the only big one)")

    X_S = X_W[["m2_yoy", "btc_dd_ath"] + SIGNALS].copy()
    X_S = X_S.loc[:, ~X_S.columns.duplicated()]
    X_S["h26"] = H26.reindex(X_S.index)
    X_S["p91"] = P91[KP].reindex(X_S.index)
    X_S["p91k3"] = P91[3.0].reindex(X_S.index)
    X_S["pfall"] = PF91.reindex(X_S.index)
    inc = {}
    stacks = {}
    for tg in ("fall5_26w", "fall10_26w"):
        base = comp["m2btc"][tg + "_pred"]
        stacks[("stack_h26", tg)] = run_stack(X_S, Y_W, ["m2_yoy", "btc_dd_ath", "h26"], tg)
        stacks[("stack_p91", tg)] = run_stack(X_S, Y_W, ["m2_yoy", "btc_dd_ath", "p91"], tg)
        stacks[("stack_p91_pfall", tg)] = run_stack(X_S, Y_W, ["m2_yoy", "btc_dd_ath", "p91", "pfall"], tg)
        stacks[("fixed5_p91", tg)] = run_stack(X_S, Y_W, SIGNALS + ["p91"], tg)
        prior = Y_W[tg].shift(26).expanding().mean().clip(0.02, 0.98)
        stacks[("logitsum_p91", tg)] = logit_sum(base, X_S["p91"].reindex(base.index), prior.reindex(base.index))
        stacks[("logitsum_h26", tg)] = logit_sum(base, X_S["h26"].reindex(base.index), prior.reindex(base.index))
        for name in ("stack_h26", "stack_p91", "stack_p91_pfall", "logitsum_p91", "logitsum_h26"):
            inc[f"{name}:{tg}"] = incremental(stacks[(name, tg)], base, Y_W, tg, fresh, rng, cfg["boot"])
        inc[f"fixed5_p91:{tg}"] = incremental(stacks[("fixed5_p91", tg)], comp["fixed5"][tg + "_pred"], Y_W, tg, fresh, rng, cfg["boot"])
    for key in ("stack_h26:fall5_26w", "stack_p91:fall5_26w", "logitsum_p91:fall5_26w", "fixed5_p91:fall5_26w", "stack_p91:fall10_26w"):
        v = inc[key]
        say(f"incremental {key} (from {v['from']}, n{v['n']}): stack AUC " + ",".join(f"{e}={v['stack'][e]['auc']}" for e in v["stack"]) + " | base AUC " + ",".join(f"{e}={v['base'][e]['auc']}" for e in v["base"])
            + f" | gain {v['aucGain']} brierGain {v['brierGain']} band {v['bootBand']} fresh {v['freshAUC']}")

    # ---- nulls and placebos (Pool over fork; HMM fits of the real model cached, labelling + logistic + transfer rerun)
    G.update({"N": N, "idx": idx, "sun": sun, "TG": TG, "FE": FE, "refits": refits, "train": train, "all": all_scales, "Y_W": Y_W, "X_W": X_W, "X_S": X_S,
              "H26": H26, "lev": lev, "fresh": fresh, "n_iter": cfg["n_iter"], "btcd_pct": D["BTC.D"].values.astype(float)})
    t1 = time.time()
    tasks_s = ([("rw", 1000 + i, i < cfg["n_placebo"]) for i in range(cfg["n_rw"])] + [("iaaft", 2000 + i, False) for i in range(cfg["n_iaaft"])]
               + [("rwj", 3000 + i, False) for i in range(cfg["n_rwj"])] + [("rwiid", 4000 + i, False) for i in range(cfg["n_iid"])])
    tasks_w = [(5000 + 1000 * j + i, e[0]) for j, e in enumerate(C.ERAS) for i in range(cfg["n_within"])]
    with get_context("fork").Pool(a.procs) as pool:
        nulls = pool.map(null_task, [(100 + i, None) for i in range(cfg["n_shift"])], chunksize=1)
        wnulls = pool.map(null_task, tasks_w, chunksize=1)
        surr = pool.map(surrogate_task, tasks_s, chunksize=1)
    t_null = time.time() - t1
    rw = [s for s in surr if s["kind"] == "rw"]
    ia = [s for s in surr if s["kind"] == "iaaft"]
    rwj = [s for s in surr if s["kind"] == "rwj"]
    iid = [s for s in surr if s["kind"] == "rwiid"]
    real_e2 = c2["fall5_26w"]["pooled"]["auc"]
    real_e2s = c2["fall5_26w"]["stratAUC"]
    real_e1 = within["pooled"]["auc"]
    null = {"shift": {"e2_fall5_26w": summarize(real_e2, [n["e2"] for n in nulls]), "e1_pooled": summarize(real_e1, [n["e1"] for n in nulls]),
                      "sigma2_91": summarize(e2["sigma2_91"]["pooled"]["auc"], [n["s91"] for n in nulls]),
                      "h26_fall5_26w": summarize(e2["hazard_h26"]["fall5_26w"]["pooled"]["auc"], [n["h26"] for n in nulls]),
                      "gain_stack_h26": summarize(inc["stack_h26:fall5_26w"]["aucGain"].get("pooled"), [n["gain_h26"] for n in nulls]),
                      "gain_stack_p91": summarize(inc["stack_p91:fall5_26w"]["aucGain"].get("pooled"), [n["gain_p91"] for n in nulls]),
                      "e2strat_fall5_26w": summarize(real_e2s, [n.get("e2strat") for n in nulls]),
                      "globalShiftScoredByEra": {e: summarize(c2["fall5_26w"].get(e, {}).get("auc"), [n["byEra"].get(e) for n in nulls]) for e, _, _ in C.ERAS},
                      "withinEra": {e: summarize(c2["fall5_26w"].get(e, {}).get("auc"), [w["e2era"] for w in wnulls if w["era"] == e]) for e, _, _ in C.ERAS},
                      "withinEra_sigma2_91": {e: summarize(within_by_era_s91.get(e), [w["s91era"] for w in wnulls if w["era"] == e]) for e, _, _ in C.ERAS}},
            "placebo_rw": {"e2_fall5_26w": summarize(real_e2, [s["e2"] for s in rw]), "e1_pooled": summarize(real_e1, [s["e1"] for s in rw]), "e2strat_fall5_26w": summarize(real_e2s, [s.get("e2strat") for s in rw]),
                           "e1_vrOnly": summarize(ctrl["vrOnly_noHMM"]["e1"], [s.get("e1_vrOnly") for s in rw]), "e1_noStates": summarize(ctrl["noHMM_featuresOnly"]["e1"], [s.get("e1_noStates") for s in rw]),
                           "e2fresh": summarize(c2["fall5_26w"]["freshAUC"], [s["e2fresh"] for s in rw]),
                           "ladder": {str(s): summarize(ladder[str(s)], [r["ladder"].get(s) for r in rw]) for s in all_scales},
                           "byEra": {e: summarize(c2["fall5_26w"].get(e, {}).get("auc"), [s["byEra"].get(e) for s in rw]) for e, _, _ in C.ERAS}},
            "iaaft": {"e2_fall5_26w": summarize(real_e2, [s["e2"] for s in ia]), "e1_pooled": summarize(real_e1, [s["e1"] for s in ia]), "e2strat_fall5_26w": summarize(real_e2s, [s.get("e2strat") for s in ia]),
                      "ladder": {str(s): summarize(ladder[str(s)], [r["ladder"].get(s) for r in ia]) for s in all_scales}},
            "placebo_rw_joint": {"note": "BTC.D, BTCUSD and ETHBTC block-resampled with the same block starts and signs: like-for-like for the full model (the pre-registered placebo_rw keeps the real BTCUSD/ETHBTC)",
                                 "e2_fall5_26w": summarize(real_e2, [s["e2"] for s in rwj]), "e2strat_fall5_26w": summarize(real_e2s, [s.get("e2strat") for s in rwj]), "e1_pooled": summarize(real_e1, [s["e1"] for s in rwj]),
                                 "e2_noStates": summarize(ctrl["noHMM_featuresOnly"]["fall5_26w"]["pooled"]["auc"], [s.get("e2_noStates") for s in rwj]),
                                 "e2_btcdOnly": summarize(ctrl["btcdOnly_noBTC_noHMM"]["fall5_26w"]["pooled"]["auc"], [s.get("e2_btcdOnly") for s in rwj]),
                                 "ladder": {str(s): summarize(ladder[str(s)], [r["ladder"].get(s) for r in rwj]) for s in all_scales}},
            "placebo_rw_iid": {"note": "i.i.d.-resampled increments (no vol clustering): E1 here is drawdown geometry alone",
                               "e2_fall5_26w": summarize(real_e2, [s["e2"] for s in iid]), "e1_pooled": summarize(real_e1, [s["e1"] for s in iid]),
                               "e1_vrOnly": summarize(ctrl["vrOnly_noHMM"]["e1"], [s.get("e1_vrOnly") for s in iid]), "e1_noStates": summarize(ctrl["noHMM_featuresOnly"]["e1"], [s.get("e1_noStates") for s in iid]),
                               "ladder": {str(s): summarize(ladder[str(s)], [r["ladder"].get(s) for r in iid]) for s in all_scales}},
            "decoys": {"placeboFittedHMM_e2": summarize(real_e2, [s.get("placebo_e2") for s in rw if "placebo_e2" in s]),
                       "placeboFittedHMM_e1": summarize(real_e1, [s.get("placebo_e1") for s in rw if "placebo_e1" in s]),
                       "globalSigma_e2": ctrl["decoy_globalSigma"]["fall5_26w"]["pooled"]["auc"], "clock_e2": comp["clock"]["fall5_26w"]["pooled"]["auc"]}}
    say(f"null shifted-target ({cfg['n_shift']}): E2 {null['shift']['e2_fall5_26w']} | E1 {null['shift']['e1_pooled']} | h26 {null['shift']['h26_fall5_26w']}")
    say(f"null shifted-target gains: stack_h26 {null['shift']['gain_stack_h26']} | stack_p91 {null['shift']['gain_stack_p91']} | E2 strat {null['shift']['e2strat_fall5_26w']} | global shift scored by era: " + " ".join(f"{e}:p={v.get('p')}(p95 {v.get('nullP95')})" for e, v in null["shift"]["globalShiftScoredByEra"].items()))
    say(f"null WITHIN-era shifted-target ({cfg['n_within']} per era, targets rolled only inside the era): " + " ".join(f"{e}: real {v.get('real')} median {v.get('nullMedian')} p95 {v.get('nullP95')} p={v.get('p')}" for e, v in null["shift"]["withinEra"].items()) + " | sigma2_91 by era: " + " ".join(f"{e}:p={v.get('p')}" for e, v in null["shift"]["withinEra_sigma2_91"].items()))
    say(f"placebo JOINT matched-RW ({len(rwj)}, BTC.D+BTCUSD+ETHBTC): E2 {null['placebo_rw_joint']['e2_fall5_26w']} | E2 strat {null['placebo_rw_joint']['e2strat_fall5_26w']} | noStates E2 {null['placebo_rw_joint']['e2_noStates']} | btcdOnly E2 {null['placebo_rw_joint']['e2_btcdOnly']} | E1 {null['placebo_rw_joint']['e1_pooled']}")
    say(f"placebo E1 decomposed: real vrOnly {ctrl['vrOnly_noHMM']['e1']} noStates {ctrl['noHMM_featuresOnly']['e1']} | matched-RW vrOnly {null['placebo_rw']['e1_vrOnly']} noStates {null['placebo_rw']['e1_noStates']} | i.i.d.-RW ({len(iid)}, no vol clustering) E1 {null['placebo_rw_iid']['e1_pooled']} vrOnly {null['placebo_rw_iid']['e1_vrOnly']} E2 {null['placebo_rw_iid']['e2_fall5_26w']}")
    say(f"placebo matched-RW ({len(rw)}): E2 {null['placebo_rw']['e2_fall5_26w']} | E1 {null['placebo_rw']['e1_pooled']} | fresh {null['placebo_rw']['e2fresh']} | ladder p95 " + " ".join(f"s{s}={null['placebo_rw']['ladder'][str(s)].get('nullP95')}" for s in all_scales))
    say(f"placebo IAAFT ({len(ia)}): E2 {null['iaaft']['e2_fall5_26w']} | E1 {null['iaaft']['e1_pooled']} | decoys: placebo-fitted HMM E2 {null['decoys']['placeboFittedHMM_e2']} E1 {null['decoys']['placeboFittedHMM_e1']} globalSigma E2 {null['decoys']['globalSigma_e2']} clock E2 {null['decoys']['clock_e2']}")

    # ---- E0 description (whole history, no fitting) with surrogate bands; E4 unfolding of the big events
    e0 = e0_stats(lev["x"], FE, E0_SCALES, KS, profile=True)
    e0_b = {"rw": e0_bands(e0, [s["e0"] for s in rw]), "iaaft": e0_bands(e0, [s["e0"] for s in ia])}
    for s in (5, 21, 91):
        key = f"s{s}_k2"
        b = e0_b["rw"].get(key, {})
        say(f"E0 s={s} k=2: n={e0[key].get('n')} rate={e0[key].get('rate')} dur/s={e0[key].get('durOverS')} depth/sig={e0[key].get('depthSigma')} relief={e0[key].get('relief')} slope={e0[key].get('slope')} | RW band dur/s [{b.get('durOverS', {}).get('p05')},{b.get('durOverS', {}).get('p95')}] relief [{b.get('relief', {}).get('p05')},{b.get('relief', {}).get('p95')}] rate [{b.get('rate', {}).get('p05')},{b.get('rate', {}).get('p95')}] | profile btcd_r4={e0[key].get('profile', {}).get('btcd_r4')} btc_dd={e0[key].get('profile', {}).get('btc_dd')} btcd_vr={e0[key].get('profile', {}).get('btcd_vr')}")
    n_out = sum(1 for key, b in e0_b["rw"].items() for q, v in b.items() if v.get("outside"))
    n_tot = sum(len(b) for b in e0_b["rw"].values())
    out_names = [f"{key}.{q}" for key, b in e0_b["rw"].items() for q, v in b.items() if v.get("outside")]
    out_by_stat = {q: sum(1 for key, b in e0_b["rw"].items() if b.get(q, {}).get("outside")) for q in ("rate", "depthSigma", "durOverS", "slope", "relief")}
    e0_b["summary"] = {"rwOutside": n_out, "rwTotal": n_tot, "chanceExpectation": r3(0.10 * n_tot), "rwOutsideByStatistic": out_by_stat, "rwOutsideList": out_names,
                       "iaaftOutside": sum(1 for b in e0_b['iaaft'].values() for v in b.values() if v.get('outside')), "iaaftTotal": sum(len(b) for b in e0_b['iaaft'].values()),
                       "note": "description, not a test: the bands come from the run's surrogate count (10 in --fast)"}
    say(f"E0 statistics outside the matched-RW 5-95% band: {n_out} of {n_tot} (chance ~{0.1 * n_tot:.0f}; by statistic {out_by_stat}; IAAFT: {e0_b['summary']['iaaftOutside']} of {e0_b['summary']['iaaftTotal']}) - description only")
    ev91 = sigma_events(lev["x"], FE[S_WEEK]["sigma"], S_WEEK, KP)
    small = [e for s in train for e in sigma_events(lev["x"], FE[s]["sigma"], s, KP)]
    band = {q: [r3(np.quantile([e[q] for e in small], 0.1)), r3(np.quantile([e[q] for e in small], 0.9))] for q in ("dsig", "dur", "relief")} if small else {}
    e4 = {"smallScaleBand10_90": band, "events91_k2": [{"peak": str(idx[e["peak"]].date()), "trough": str(idx[e["trough"]].date()), "days": e["days"], "depthSigma": r3(e["dsig"]), "durOverS": r3(e["dur"]), "relief": r3(e["relief"]),
                                                      "inBand": {q: bool(band[q][0] <= e[q] <= band[q][1]) for q in band}} for e in ev91], "bigEvents": {}}
    for d in C.BIG_EVENTS:
        pos = int(np.searchsorted(idx, pd.Timestamp(d)))
        near = [e for e in ev91 if abs(e["peak"] - pos) <= 60]
        e4["bigEvents"][d] = ({"peak": str(idx[near[0]["peak"]].date()), "depthSigma": r3(near[0]["dsig"]), "durOverS": r3(near[0]["dur"]), "relief": r3(near[0]["relief"])} if near else "no s=91 k=2 event within 60 days")
    say(f"E4 big events at s=91 (depth/sigma, dur/s, relief) vs small-scale 10-90% band {band}: " + "; ".join(f"{d}: {v}" for d, v in e4["bigEvents"].items()) + f" | s=91 k=2 events: {len(ev91)}, last peak {e4['events91_k2'][-1]['peak'] if ev91 else None}")

    # ---- duration: FALL visits (P(FALL) > 0.5) ended before today, per scale, in steps (self-similar if steps agree)
    dur = {}
    for s in all_scales:
        L = visit_lengths(pstate[s][:, 0], s, N - 1)
        dur[str(s)] = ({"visits": len(L), "q10_50_90_steps": [r3(np.quantile(L, q)) for q in (0.1, 0.5, 0.9)], "meanSteps": r3(np.mean(L)), "meanDays": r3(np.mean(L) * s)} if L else {"visits": 0})
    say("duration of FALL visits (steps, visits ended before today): " + " ".join(f"s{s}={dur[str(s)].get('q10_50_90_steps')}(n{dur[str(s)]['visits']})" for s in all_scales))

    # ---- checks: filter truncation, refit jumps, parameters, episode LOO
    last = refits[-1]
    mu_l, var_l, A_l, pi_l = last["params"]
    E91 = np.ascontiguousarray(FE[S_WEEK][EMIS].values.astype(float))
    fin91 = np.isfinite(E91).all(1)

    def fn(end):
        order, st, en = build_chains(fin91, S_WEEK, end + 1)
        out = np.full(N, np.nan)
        if len(order):
            out[order] = _filter(gauss_ll(E91[order], mu_l, var_l), st, en, A_l, pi_l)[:, last["fall"]]
        return out
    trunc = C.truncation_test(fn, N, n=20, rng=rng)
    tt = int(rng.integers(N // 2, N - 60))
    trunc["append50_ok"] = bool(abs(fn(tt + 50)[tt] - fn(tt)[tt]) <= 1e-9) if np.isfinite(fn(tt)[tt]) else None
    jumps = {"p91": C.refit_jump_report(P91[KP], refit_dates), "pfall91": C.refit_jump_report(PF91, refit_dates), "h26": C.refit_jump_report(H26, refit_dates)}
    k_params = K_STATES * len(EMIS) * 2 + K_STATES * (K_STATES - 1) + (K_STATES - 1) + len(FEATS_A) + K_STATES + 1
    params = C.params_report(k_params)
    spells_train = {str(s): n_spells(TG[s][kn(KP)].values) for s in train}
    params["perStage"] = {"hmm": {"parameters": K_STATES * len(EMIS) * 2 + K_STATES * (K_STATES - 1) + (K_STATES - 1), "fittedOn": "unsupervised EM on the pooled small-scale rows", "rowsFirstLast": [refits[0]["nTrain"], refits[-1]["nTrain"]]},
                          "logistic": {"parameters": len(FEATS_A) + K_STATES + 1, "fittedOn": "pooled small-scale daily rows", "sigmaSpellsPerScale_wholeHistory": spells_train, "sigmaSpellsTotal": int(sum(spells_train.values()))},
                          "stacks": {"parameters": "3-5 weights (+bias) at each of ~30 weekly refits", "fittedOn": "weekly rows from 30 upward holding <= 12 label episodes", "note": "the only supervised stage fitted against the weekly label; the component that inverted in 2023-26"}}
    params["note"] += "; per stage: HMM 32 (unsupervised), small-scale logistic 11 vs ~%d sigma spells, learned stacks 3-5 weights per refit vs 12 label episodes" % params["perStage"]["logistic"]["sigmaSpellsTotal"]
    loo = {"E2_fall5_26w": C.episode_loo(P91[KP].reindex(Y_W.index)[Y_W.index >= pd.Timestamp(EVAL_START)], Y_W.loc[Y_W.index >= pd.Timestamp(EVAL_START), "fall5_26w"]),
           "stack_p91_fall5_26w": C.episode_loo(stacks[("stack_p91", "fall5_26w")][Y_W.index >= pd.Timestamp(EVAL_START)], Y_W.loc[Y_W.index >= pd.Timestamp(EVAL_START), "fall5_26w"])}
    bb = {"E2_fall5_26w": C.block_boot(P91[KP].reindex(Y_W.index), Y_W["fall5_26w"], n=cfg["boot"], rng=rng)}
    decoy_eras = {e: {"E2": c2["fall5_26w"].get(e, {}).get("auc"), "clock": comp["clock"]["fall5_26w"].get(e, {}).get("auc"), "eraMean": comp["eraMean"]["fall5_26w"].get(e, {}).get("auc"),
                      "beatsClock": bool((c2["fall5_26w"].get(e, {}).get("auc") or 0) > (comp["clock"]["fall5_26w"].get(e, {}).get("auc") or 1)),
                      "beatsEraMean": bool((c2["fall5_26w"].get(e, {}).get("auc") or 0) > (comp["eraMean"]["fall5_26w"].get(e, {}).get("auc") or 1))} for e, _, _ in C.ERAS}
    say("E2 vs decoys by era (clock=days_since_halving, era-mean): " + " ".join(f"{e}: E2 {v['E2']} clock {v['clock']} eraMean {v['eraMean']} beats={v['beatsClock']}/{v['beatsEraMean']}" for e, v in decoy_eras.items()))
    say(f"checks: feature truncation {feat_trunc} | filter truncation ok={trunc['ok']} maxDiff={trunc['maxAbsDiff']:.1e} tested={trunc['tested']} append50={trunc['append50_ok']} | refits={len(refits)} FALL idx changes={int(np.sum(np.diff(fall_idx) != 0))} | jumps p91 {jumps['p91']} | params {k_params} vs 12 episodes")
    say(f"episode LOO E2 fall5_26w: all={loo['E2_fall5_26w']['all']} min={loo['E2_fall5_26w']['min']} at {loo['E2_fall5_26w']['minEpisode']} (nEp {loo['E2_fall5_26w']['nEpisodes']}) | block boot {bb['E2_fall5_26w']} | stack_p91 LOO min={loo['stack_p91_fall5_26w']['min']} at {loo['stack_p91_fall5_26w']['minEpisode']}")

    # ---- today
    i = N - 1
    p_now = float(D["BTC.D"].iloc[-1]) / 100
    sig91 = float(FE[S_WEEK]["sigma"].iloc[-1])
    sig_pts = sig91 * p_now * (1 - p_now) * 100
    f_now = {f: r3(FE[S_WEEK][f].iloc[-1]) for f in FEATS_A}
    st_now = {STATE_NAMES[j]: r3(pstate[S_WEEK][i, j]) for j in range(K_STATES)}
    pf_hist = pd.Series(pstate[S_WEEK][:, 0], index=idx)
    last_fall = pf_hist[pf_hist > 0.5]
    last_fall_date = str(last_fall.index[-1].date()) if len(last_fall) else None
    runs = C.episodes((pf_hist > 0.5).astype(float).where(pf_hist.notna()).values)
    last_window = [str(idx[runs[-1][0]].date()), str(idx[runs[-1][1]].date())] if runs else None
    last_fall_small = {str(s): (str(pd.Series(pstate[s][:, 0], index=idx).pipe(lambda q: q[q > 0.5]).index[-1].date()) if (pstate[s][:, 0] > 0.5).any() else None) for s in train}
    today = {"date": str(idx[-1].date()), "btcd": r3(100 * p_now), "sigma91_logit": r3(sig91), "sigma91_points": r3(sig_pts), "k2_points": r3(2 * sig_pts), "features91": f_now, "pstate91": st_now,
             "h13": r3(haz[S_WEEK]["h1"][i]), "h26": r3(haz[S_WEEK]["h2"][i]), "ET_steps": r3(haz[S_WEEK]["ET"][i]), "ET_days": r3(haz[S_WEEK]["ET"][i] * S_WEEK),
             "p_sigma2_91": r3(preds[KP][S_WEEK][i]), "p_sigma1.5_91": r3(preds[1.5][S_WEEK][i]), "p_sigma3_91": r3(preds[3.0][S_WEEK][i]),
             "lastFallVisit91": last_fall_date, "lastFallVisitWindow91": last_window, "lastFallVisitWasJun2025": bool(last_window is not None and last_window[0] <= "2025-12-31" and last_window[1] >= "2025-06-01"), "lastFallVisitSmallScales": last_fall_small,
             "transitionMatrixLastRefit": [[r3(v) for v in row] for row in A_l[np.ix_(np.argsort(mu_l[:, 0]), np.argsort(mu_l[:, 0]))]], "stateMeans_btcd_r1": [r3(v) for v in np.sort(mu_l[:, 0])],
             "stacks": {f"{n}:{tg}": r3(stacks[(n, tg)].reindex([sun[-1]]).iloc[0]) for (n, tg) in stacks if stacks[(n, tg)].notna().any()},
             "comparators": {k: {tg: comp[k][tg]["today"] for tg in ("fall5_26w", "fall10_26w")} for k in ("fixed5", "m2only", "m2btc")},
             "comparatorsProvisionalRow": {k: {tg: comp[k][tg]["todayProvisionalRow"] for tg in ("fall5_26w", "fall10_26w")} for k in ("fixed5", "m2only", "m2btc")},
             "weeklyRowUsed": str(sun[-1].date()), "provisional": partial, "asOf": "fractal readings: daily row %s; stacks and comparators: Sunday %s close; comparatorsProvisionalRow: the partial week %s" % (str(idx[-1].date()), str(sun[-1].date()), partial),
             "stationaryFallShare": r3(stationary(A_l)[last["fall"]]), "hazardNote": "h13/h26 = P(FALL within 1/2 steps) read off the frozen transition matrix: FALL occupancy now plus a chain constant (off-state AUC in oos.E2.hazard_offState); E[T] is a chain property, not a market reading",
             "p_fall5_26w_exported": r3(stacks[("logitsum_p91", "fall5_26w")].reindex([sun[-1]]).iloc[0]) if stacks[("logitsum_p91", "fall5_26w")].notna().any() else None}
    mod = models[-1].get(KP)
    if mod is not None:
        mu_z, sd_z, w_z = mod
        row = np.r_[FE[S_WEEK][FEATS_A].values[i], refits[-1]["alphas"][S_WEEK][i]]
        z = C.zapply(row[None, :], mu_z, sd_z)
        names = FEATS_A + [f"state{j}" for j in range(K_STATES)]
        pert = {}
        for j, nme in enumerate(names):
            vals = {}
            for lab, dz in (("drop", None), ("+1sd", 1.0), ("-1sd", -1.0)):
                zz = z.copy()
                zz[0, j] = 0.0 if dz is None else zz[0, j] + dz
                vals[lab] = r3(C.logistic_predict(zz, w_z)[0])
            pert[nme] = vals
        allv = [v for d in pert.values() for v in d.values()]
        today["perturbation"] = {"p_sigma2_91": today["p_sigma2_91"], "min": min(allv), "max": max(allv), "perInput": pert, "weights_z": {n: r3(w) for n, w in zip(["bias"] + names, w_z)}}
    say(f"today {today['date']}: BTC.D {today['btcd']} sigma91={today['sigma91_points']} pts (k=2 -> {today['k2_points']} pts) | P(state)={st_now} h13={today['h13']} h26={today['h26']} E[T]={today['ET_days']} days | P(2-sigma fall in 182d)={today['p_sigma2_91']} (k1.5 {today['p_sigma1.5_91']}, k3 {today['p_sigma3_91']}) perturbation [{today.get('perturbation', {}).get('min')},{today.get('perturbation', {}).get('max')}]")
    say(f"today stacks (Sunday {today['weeklyRowUsed']}): {today['stacks']} | comparators same Sunday {today['comparators']} (provisional row {partial}: {today['comparatorsProvisionalRow']}) | exported P(fall5_26w) = logitsum {today['p_fall5_26w_exported']} | stationary FALL share {today['stationaryFallShare']} | last FALL visit at s=91: {last_window} (covers the Jun 2025 fall? {today['lastFallVisitWasJun2025']}); small scales {last_fall_small}")
    say(f"today features91 {f_now}")

    # ---- pre-registered criteria
    e2_eras = {e: c2["fall5_26w"].get(e, {}).get("auc") for e, _, _ in C.ERAS}
    inc_h = inc["stack_h26:fall5_26w"]
    lad_scales = [s for s in all_scales if s >= 21]
    lad_vals = [ladder[str(s)] for s in lad_scales if ladder[str(s)] is not None]
    e1_auc = within["pooled"]["auc"]
    s91_auc = e2["sigma2_91"]["pooled"]["auc"]
    ratio_sigma = r3((s91_auc - 0.5) / (e1_auc - 0.5)) if e1_auc not in (None, 0.5) and s91_auc is not None else None
    ratio_pts = r3((real_e2 - 0.5) / (e1_auc - 0.5)) if e1_auc not in (None, 0.5) and real_e2 is not None else None
    rw_med = {str(s): null["placebo_rw"]["ladder"][str(s)].get("nullMedian") for s in all_scales}
    excess = {str(s): (r3(ladder[str(s)] - rw_med[str(s)]) if ladder[str(s)] is not None and rw_med[str(s)] is not None else None) for s in all_scales}
    ex21, ex91 = excess.get("21"), excess.get(str(S_WEEK))
    ratio_excess = r3(ex91 / ex21) if ex21 is not None and ex91 is not None and abs(ex21) >= 0.02 else None  # None: the small-scale excess over the walk is ~0, so no ratio is identifiable
    rwj_p95 = null["placebo_rw_joint"]["e2_fall5_26w"].get("nullP95")
    crit = {
        "i": {"pass": bool(real_e2 is not None and real_e2 > (null["shift"]["e2_fall5_26w"].get("nullP95") or 1) and real_e2 > (null["placebo_rw"]["e2_fall5_26w"].get("nullP95") or 1)
                          and all(v is not None and v > 0.5 for v in e2_eras.values()) and (c2["fall5_26w"]["freshAUC"] or 0) > 0.55),
              "e2": real_e2, "shiftP95": null["shift"]["e2_fall5_26w"].get("nullP95"), "rwP95": null["placebo_rw"]["e2_fall5_26w"].get("nullP95"), "byEra": e2_eras, "fresh": c2["fall5_26w"]["freshAUC"],
              "stratified": {"e2strat": real_e2s, "eraIndicatorFloor": c2["fall5_26w"]["eraIndicatorAUC"], "meanEra": c2["fall5_26w"]["meanEraAUC"], "shiftP95": null["shift"]["e2strat_fall5_26w"].get("nullP95"), "rwP95": null["placebo_rw"]["e2strat_fall5_26w"].get("nullP95"),
                             "pass": bool(real_e2s is not None and real_e2s > (null["shift"]["e2strat_fall5_26w"].get("nullP95") or 1) and real_e2s > (null["placebo_rw"]["e2strat_fall5_26w"].get("nullP95") or 1))},
              "jointPlacebo": {"rwJointP95": rwj_p95, "passJoint": bool(real_e2 is not None and rwj_p95 is not None and real_e2 > rwj_p95), "withinEraP": {e: v.get("p") for e, v in null["shift"]["withinEra"].items()}}},
        "ii": {"pass": bool((inc_h["aucGain"].get("pooled") or -1) >= 0.03 and (inc_h["brierGain"].get("pooled") or -1) > 0 and (inc_h["aucGain"].get("2021-2022") or -1) > 0 and (inc_h["aucGain"].get("2023-2026") or -1) > 0),
               "gain": inc_h["aucGain"], "brierGain": inc_h["brierGain"], "band": inc_h["bootBand"],
               "secondary_stack_p91": {"gain": inc["stack_p91:fall5_26w"]["aucGain"], "brierGain": inc["stack_p91:fall5_26w"]["brierGain"], "band": inc["stack_p91:fall5_26w"]["bootBand"]}},
        "iii": {"pass": bool(len(lad_vals) >= 2 and max(lad_vals) - min(lad_vals) <= 0.10), "ladder": {str(s): ladder[str(s)] for s in lad_scales}, "spread": r3(max(lad_vals) - min(lad_vals)) if lad_vals else None,
                "excessOverRWMedian": excess, "rwMedian": rw_med, "note": "the raw ladder rises with s and so does the matched-RW band (overlapping labels on few spells); excess = real minus RW median is the comparable number"},
        "iv": {"pass": bool(ratio_sigma is not None and ratio_sigma >= 0.5), "ratioSigmaTarget": ratio_sigma, "ratioPointTarget": ratio_pts, "e1": e1_auc, "e2sigma": s91_auc, "e2points": real_e2,
               "ratioExcessOverRW": ratio_excess, "excess21": ex21, "excess91": ex91, "note": "the raw ratio passes trivially because the larger scale is easier; the excess ratio (s91 excess / s21 excess over the RW median) is the honest version"},
    }
    e1_real = bool(e1_auc is not None and e1_auc > (null["placebo_rw"]["e1_pooled"].get("nullP95") or 1) and e1_auc > (null["shift"]["e1_pooled"].get("nullP95") or 1))
    if all(crit[c]["pass"] for c in ("i", "ii", "iii", "iv")):
        verdict = "all four pass: the premise gains support and the stack gains a within-cycle hazard"
    elif crit["i"]["pass"]:
        verdict = "(i) passes, (ii) fails: the grammar is real but contained in M2 + BTC drawdown" if not crit["ii"]["pass"] else "(i) and (ii) pass but the ladder/transfer ratio fails: partial"
    elif e1_real:
        verdict = "(i) fails while E1 passes: structure exists at daily scale and does not scale up (the premise fails in the sense the thesis needs)"
    else:
        verdict = "E1 fails too: no conditional grammar beyond a heteroskedastic random walk"
    crit["E1_beats_placebos"] = e1_real
    nulls_ok = cfg["n_shift"] >= VERDICT_MIN_NULLS and cfg["n_rw"] >= VERDICT_MIN_NULLS
    crit["verdictGated"] = {"printed": nulls_ok, "minNulls": VERDICT_MIN_NULLS, "nShift": cfg["n_shift"], "nRW": cfg["n_rw"]}
    if not nulls_ok:
        verdict = f"NO VERDICT (shifted draws {cfg['n_shift']}, matched-RW placebos {cfg['n_rw']}; both must be >= {VERDICT_MIN_NULLS}): a p95 of so few draws is the maximum of a handful of numbers; provisional reading would be: {verdict}"
    nh = ctrl["noHMM_featuresOnly"]["fall5_26w"]["pooled"]["auc"]
    bo = ctrl["btcdOnly_noBTC_noHMM"]["fall5_26w"]["pooled"]["auc"]
    ph = null["decoys"]["placeboFittedHMM_e2"]
    crit["diagnostics"] = {"E2_withHMM": real_e2, "E2_noHMM": nh, "hmmAddsAUC": r3(real_e2 - nh) if nh is not None else None,
                           "placeboFittedHMM_p": ph.get("p"), "E2_btcdOnly": bo, "btcdOnlyBeatsRW": bool(bo is not None and bo > (null["placebo_rw"]["e2_fall5_26w"].get("nullP95") or 1)),
                           "withinEraShiftP": {e: v.get("p") for e, v in null["shift"]["withinEra"].items()}, "globalShiftScoredByEraP": {e: v.get("p") for e, v in null["shift"]["globalShiftScoredByEra"].items()},
                           "ladderS91_vs_RW_p95": [ladder[str(S_WEEK)], null["placebo_rw"]["ladder"][str(S_WEEK)].get("nullP95")],
                           "E2_strat": real_e2s, "eraIndicatorFloor": c2["fall5_26w"]["eraIndicatorAUC"], "E2_demeaned_noHMM": ctrl["demeaned_noHMM"]["fall5_26w"]["pooled"]["auc"], "E2_vrOnly": ctrl["vrOnly_noHMM"]["fall5_26w"]["pooled"]["auc"],
                           "h26_offStateAUC": e2["hazard_offState"]["h26_aucOffState"], "featureTable": ftab}
    interp = []
    interp.append("HMM states add " + (f"{crit['diagnostics']['hmmAddsAUC']:+.3f} AUC over the same features without them" if nh is not None else "n/a") + f"; a placebo-fitted HMM on real rows scores p={ph.get('p')} (p<0.05 would mean the real fit matters)")
    interp.append(f"BTC.D-only features (no BTC term) transfer at {bo} vs RW p95 {null['placebo_rw']['e2_fall5_26w'].get('nullP95')}: " + ("the transfer survives without BTC drawdown" if crit["diagnostics"]["btcdOnlyBeatsRW"] else "the transfer needs the BTC drawdown feature"))
    interp.append("within-era shifted-target p (targets rolled inside the era): " + ", ".join(f"{e} {v}" for e, v in crit["diagnostics"]["withinEraShiftP"].items()) + " (the pooled number rests on the eras with p<0.05); global shift scored by era p: " + ", ".join(f"{e} {v.get('p')}" for e, v in null["shift"]["globalShiftScoredByEra"].items()))
    interp.append(f"era-stratified E2 {real_e2s} vs era-indicator floor {c2['fall5_26w']['eraIndicatorAUC']} (pooled {real_e2}): " + ("within-era ranking beats the hindsight era level" if (real_e2s or 0) > (c2['fall5_26w']['eraIndicatorAUC'] or 1) else "a three-valued hindsight era indicator ranks the weeks at least as well as the pooled transfer"))
    interp.append(f"joint placebo (BTC.D+BTCUSD+ETHBTC resampled together) p95 {rwj_p95} vs E2 {real_e2}: " + ("beaten" if crit['i']['jointPlacebo']['passJoint'] else "not beaten") + f"; ladder excess over RW median s21 {ex21} -> s91 {ex91} (ratio {ratio_excess})")
    flips = [f for f, v in ftab.items() if v.get("signFlipSmallTo91")]
    missigned = [f for f, v in ftab.items() if v.get("weightDisagreesWith91")]
    interp.append("per-feature transfer: marginal sign flips between the training scales and s=91 for " + (", ".join(flips) if flips else "no feature") + "; learned small-scale weight mis-signed against the s=91 marginal for " + (", ".join(missigned) if missigned else "no feature") + "; best single raw input at s=91 on fall5_26w: " + max(ftab, key=lambda f: ftab[f]["s91_fall5_26w"] or 0) + f" {max(v['s91_fall5_26w'] or 0 for v in ftab.values())} vs transferred classifier {real_e2}")
    interp.append(f"sigma-target AUC at s=91 {ladder[str(S_WEEK)]} vs matched-RW p95 {null['placebo_rw']['ladder'][str(S_WEEK)].get('nullP95')}: " + ("real beats the walk on its own sigma target" if (ladder[str(S_WEEK)] or 0) > (null['placebo_rw']['ladder'][str(S_WEEK)].get('nullP95') or 1) else "a heteroskedastic walk is at least as predictable on the sigma target (drawdown mechanics + vol clustering)"))
    crit["interpretation"] = interp
    crit["verdict"] = verdict
    say(f"criteria: (i) {crit['i']['pass']} E2={real_e2} vs shift p95 {crit['i']['shiftP95']} RW p95 {crit['i']['rwP95']} eras {e2_eras} fresh {crit['i']['fresh']} | (ii) {crit['ii']['pass']} gain {inc_h['aucGain'].get('pooled')} brier {inc_h['brierGain'].get('pooled')} 21-22 {inc_h['aucGain'].get('2021-2022')} 23-26 {inc_h['aucGain'].get('2023-2026')}")
    say("interpretation: " + " | ".join(interp))
    say(f"criteria: (iii) {crit['iii']['pass']} ladder spread {crit['iii']['spread']} | (iv) {crit['iv']['pass']} ratio sigma={ratio_sigma} points={ratio_pts} | E1 beats placebos: {e1_real} | VERDICT: {verdict}")

    # ---- notes
    notes += [
        "Fractal model inputs: logit BTC.D, log BTCUSD, log ETHBTC (set B adds TOTAL3/BTC and USDT.D); never M2, the halving clock or the ATH. Comparators keep M2 with its 6-week lag.",
        "All rolling windows end at t-1 (closed-left, shifted one bar); x_t enters explicitly. HMM EM window ends 49 days (2 x 21 + 7) before each refit; states labelled by training mean btcd_r1 and frozen; forward filter only along the stride-s chain ending at t.",
        "btcd_vr uses 1-bar increments over 2s vs 8s bars (dimensionless) instead of s-bar increments, which have ~2 independent samples in a 2s window.",
        f"Warm-up forecasts begin {FIRST_FORECAST} on thin training so the stacked logistic has history; all metrics start {EVAL_START}. Stacks use min_train 30 weekly rows and start when 30 labelled rows with a transferred score exist.",
        "E2 classifier scores are P(>= 2 sigma_91 fall within 182 days), not P(5-point fall): their Brier against fall5_26w is reported but miscalibrated by construction; the stacks are calibrated to the point targets.",
        "Global-sigma decoy: features and the sigma target normalised by the full-sample std of s-bar changes (the leaky constant is the point of the decoy), scored on the real point targets.",
        "Placebos are built in points: matched RW = BTC.D's block-resampled daily point increments with random signs, reflected into [20, 97]; IAAFT keeps BTC.D's marginal distribution and spectrum. Logit-space walks drift to 99-100% where 5-point falls cannot occur, which is why they are not used.",
        "Placebo pipelines (matched RW, IAAFT, placebo-fitted HMM) fit the HMM once on rows before 2018-11-18 and then walk the logistic forward; the real 'frozenHMM' control is the like-for-like comparison.",
        "Shifted-target null: the daily sigma-target panel is rolled by >= 182 days and the weekly harness targets by the same number of weeks; HMM fits are cached (unsupervised), labelling, logistic, transfer, stacks and scoring rerun.",
        "fall10_26w rests on one 2019+ episode (Oct 2020 - May 2021) plus whatever Jun 2025 adds; its AUCs rank one event. Sigma-unit spell counts are printed beside n rows and are not point-event counts (9 five-point events since 2016 at every scale).",
        "hit rate omitted for probability scores on y13.",
        "FALL-visit durations are descriptive (visits ended before t) and never feed a fit. E0/E4 centred event definitions (peak = max over +-s bars, fall within 2s) are description only.",
        "Equal-weight 'logitsum' = logit(p_m2btc) + logit(p_transfer) - logit(training base rate): no learned weight, usable from the first evaluation week. It is the exported series.p_fall5_26w; the learned stacks are diagnostics only.",
        "Headline metric: the era-stratified AUC (pairs within one era only) with the hindsight era-indicator AUC printed as the floor; the pooled AUC over era base rates 0.47/0.34/0.09 rewards any slowly drifting score and is secondary. The pre-registered criteria (i)-(iv) are evaluated as written on the pooled number and the stratified version is reported beside them.",
        "Nulls: 'globalShiftScoredByEra' is the whole-panel circular shift evaluated inside each era (imports other eras' label runs); 'withinEra' rolls the daily sigma targets and the weekly targets only inside the era's rows (>= 182 days) and reruns labelling, logistic and transfer: that is the within-era null the plan prescribes.",
        "Placebos: the pre-registered matched RW and IAAFT replace BTC.D only and keep the real BTCUSD/ETHBTC, so their btc_dd/btc_r1/eth_r1 channels are noise; placebo_rw_joint resamples BTC.D, BTCUSD and ETHBTC with the same block starts and signs and is the like-for-like placebo for the full model; placebo_rw_iid removes vol clustering so E1 there is drawdown geometry alone; E1 is also decomposed (vr-only, no-states) for real and placebo.",
        "The transferred score is P(>= 2 sigma_91 fall) and 2 sigma_91 was a different number of points in each era (oos.E2.sigma91_pointsByEra); classifier_kmatched reads, per Sunday, the trained k in {1.5, 2, 3} closest to 5 points / sigma_91 and is scored on the point label as the scale-matched diagnostic. The sigma2_91 target has few positive spells since 2019 (printed).",
        "Hazard arm: h13/h26 are read off the frozen transition matrix and equal FALL occupancy plus a chain constant (FALL visits last a median of 1 step at every scale); oos.E2.hazard_offState scores them on the rows where the chain is not already in FALL. E[T] is reported with the stationary FALL share as a chain property.",
        "Per-feature marginal AUC across scales (criteria.diagnostics.featureTable) is the direct transfer diagnostic: a feature whose marginal sign flips between the training scales and s=91 cannot transfer with a fixed weight.",
        "Per-window-demeaned variant (each feature minus its trailing 8s-bar mean, shifted one bar; no HMM) is run as controls.demeaned_noHMM for the vol-collapse confound; hourly rungs not run.",
        "Verdict line is printed only when the shifted-target and matched-RW counts are both >= 50; under --fast the module prints 'SMOKE ONLY' with the provisional reading, because a p95 of 10 draws is the maximum of 10 numbers.",
        "E0 is description: the surrogate bands come from this run's surrogate count and about 10% of the statistics fall outside a 5-95% band by chance; the outside list is named in e0.bands.summary.",
        "Today's table: fractal readings are the daily row; stacks AND comparators are read on the last complete Sunday; the partial-week comparator values are printed separately as comparatorsProvisionalRow.",
    ]
    if not HAVE_NUMBA:
        notes.append("numba not available: pure-Python forward-backward (slow, same numbers).")
    jp = jumps["p91"]
    if jp.get("maxJumpAtRefit") is not None and jp.get("maxJumpElsewhere") is not None and jp["maxJumpAtRefit"] > jp["maxJumpElsewhere"]:
        notes.append(f"Refit artefacts: the largest week-to-week jump of the transferred score at a refit date ({jp['maxJumpAtRefit']}) exceeds the largest elsewhere ({jp['maxJumpElsewhere']}); medians {jp['medianJumpAtRefit']} vs {jp['medianJumpElsewhere']}.")
    notes.append(f"Run config: {cfg}; the GitHub runner's full run uses nulls={a.nulls if not a.fast else 100}, rw=100, iaaft=50, placebos=30.")

    series = {"p_fall5_26w": C.thin(stacks[("logitsum_p91", "fall5_26w")], every=2), "p_fall10_26w": C.thin(stacks[("logitsum_p91", "fall10_26w")], every=2),
              "p_fall5_26w_source": "logitsum_p91 = logit(p_m2btc) + logit(p_transfer) - logit(training base rate), no learned weight; the learned stack_p91 (AUC 0.15 in 2023-26 in the full run) is kept below under its own name and must not enter the forecast stack",
              "p_active": C.thin(PF91, every=2), "p_sigma2_91": C.thin(P91[KP], every=2), "h26": C.thin(H26, every=2), "h13": C.thin(H13, every=2),
              "p_fall5_26w_stack_p91_learned": C.thin(stacks[("stack_p91", "fall5_26w")], every=2), "p_fall10_26w_stack_p91_learned": C.thin(stacks[("stack_p91", "fall10_26w")], every=2),
              "p_fall5_26w_stack_h26": C.thin(stacks[("stack_h26", "fall5_26w")], every=2)}
    for k in list(comp):
        for tg in ("fall5_26w", "fall10_26w"):
            comp[k].pop(tg + "_pred", None)
    res = {"oos": {"E2": e2, "controls": ctrl}, "within_scale": within, "ladder": ladder, "reverse": ctrl["reverse_fit91"], "comparators": comp, "baseRates2019": base_rate, "incremental": inc,
           "null": null, "e0": {"real": e0, "bands": e0_b}, "e4": e4, "duration": dur, "today": today, "series": series, "criteria": crit,
           "checks": {"featureTruncation": feat_trunc, "filterTruncation": trunc, "refitJumps": jumps, "params": params, "episodeLOO": loo, "blockBoot": bb, "refitDates": refit_dates, "fallStateIndexPerRefit": fall_idx, "decoysByEra": decoy_eras,
                      "hmmTrainRowsFirstLast": [refits[0]["nTrain"], refits[-1]["nTrain"]]},
           "config": {k: v for k, v in cfg.items()}, "notes": notes,
           "runtime": {"realPipelineSec": round(t_real, 1), "nullsAndPlacebosSec": round(t_null, 1), "totalSec": round(time.time() - t0, 1),
                       "finishedUTC": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), "finishedET": datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M:%S %Z")}}
    C.write_results(a.out, res)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(12, 4))
        ax.plot(P91[KP].index, P91[KP].values, label="P(2-sigma fall, 182d) transferred", lw=0.8)
        ax.plot(H26.index, H26.values, label="h26 (HMM hazard)", lw=0.8)
        st = stacks[("stack_p91", "fall5_26w")]
        ax.plot(st.index, st.values, label="stack m2+btc_dd+p91 -> P(fall5_26w)", lw=0.8)
        y = Y_W["fall5_26w"].reindex(P91[KP].index)
        ax.fill_between(y.index, 0, y.fillna(0).values, alpha=0.12, color="grey", label="fall5_26w label")
        for d in refit_dates:
            ax.axvline(pd.Timestamp(d), color="k", alpha=0.08, lw=0.5)
        ax.set_xlim(pd.Timestamp("2018-01-01"), idx[-1])
        ax.legend(fontsize=7, loc="upper left")
        ax.set_title("multiscale: transferred s=91 scores (refit dates marked)")
        fig.tight_layout()
        fig.savefig(os.path.join(a.out, "multiscale_series.png"), dpi=110)
        plt.close(fig)
    except Exception as ex:  # charts are optional
        notes.append(f"chart skipped: {ex}")
    say(f"done in {res['runtime']['totalSec']}s (real pipeline {res['runtime']['realPipelineSec']}s, nulls+placebos {res['runtime']['nullsAndPlacebosSec']}s) at {res['runtime']['finishedUTC']} UTC / {res['runtime']['finishedET']}; results {os.path.join(a.out, 'results.json')}")


if __name__ == "__main__":
    main()
