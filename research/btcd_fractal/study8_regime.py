#!/usr/bin/env python3
"""Round 8 trial [3] "regime": is the alt-season waterfall a distinct hidden state with a detectable onset and a usable
duration, does a covariate-driven entry hazard (TVTP on M2 y/y and BTC drawdown) add forecast content beyond
continuation, and does the daily chain's 7-step transition matrix equal the weekly one?

Model: a K = 2 (calm / active, ordered by the sigma of the BTC.D increment) Markov-switching model in numpy, EM
(forward filter + backward smoother on the TRAINING window only), on the 1-week logit increment of BTC.D with
multivariate diagonal-Gaussian emissions [y, log rv7, dlog ETH/BTC, dlog BTC]. Variants on one code path:
  V0 y only, fixed P (continuation is the signal)        V1 multivariate emissions, fixed P
  V2 V1 + TVTP: P(calm -> active | x_{t-1}) = sigmoid(a + b . [m2_yoy, btc_dd_ath]), active -> calm constant d
  V3 V2 + state-specific slopes on [btcd_fromhi52w, ethbtc_fromhi52w, usdtd_vsma30w] in the mean of y
Every forecast comes from the FORWARD FILTER run to t with the parameters of the refit at or before t (expanding
window from 2016-07-03, first forecast 2019-01-06, refit every 13 weeks, frozen between refits). Read-outs: P(active
now), entry hazards P_enter(h) on the absorbing chain (including occupancy and pure entry), E[T] to entry, Monte Carlo
P(fall5_13w), P(fall5_26w), P(fall10_26w) and y13_hat with regressors held at x_t, residual dwell. The five-signal
logistic (study8_baselines.SIGNALS), M2 alone and M2 + BTC drawdown run through the same harness as comparators, with
the regime read-outs added to them (fixed offset and a stacked logistic) for the incremental test.

  python3 research/btcd_fractal/study8_regime.py --data research/btcd_fractal/data --out research/btcd_fractal/out8/regime [--nulls N] [--fast]

Point in time: filtered posteriors only; z-scores, clips, EM parameters from the training window; regressors lagged one
week for the transition into t; M2 lagged 6 weeks (harness); realized vol over trailing days through the week-end; the
partial current week is never in any training window and is flagged. --fast runs the truncation test (features,
emissions and the filter recomputed on the daily panel truncated at 20 random t must equal the reported series to 1e-9).
Smoothed probabilities appear only inside EM on the training window and in the clearly flagged "leaky twin".
"""
import argparse
import datetime as dt
import os
import sys
import time
from multiprocessing import get_context

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import study8_common as C  # noqa: E402
import study8_baselines as B  # noqa: E402

try:
    from numba import njit
except Exception:  # numpy fallback (slow but identical)
    def njit(*a, **k):
        if a and callable(a[0]):
            return a[0]
        return lambda f: f

# ------------------------------------------------------------------------------------------- pre-registered constants
EMIS_W = ["y", "lrv7", "dlog_ethbtc", "dlog_btc"]        # weekly emissions (V1+); V0 uses y only
EMIS_D = ["y", "lrv5", "dlog_ethbtc", "dlog_btc"]        # daily twin
REG_TVTP = ["m2_yoy", "btc_dd_ath"]                       # entry-hazard regressors (the a-priori readiness pair, disclosed as found on all eras)
X_CONT = ["btcd_fromhi52w", "ethbtc_fromhi52w", "usdtd_vsma30w"]   # V3 state-specific slopes (the sign-switchers)
KAPPA_W, KAPPA_D = 5.0, 35.0                              # sticky Dirichlet prior on the diagonal (pseudo-counts)
RIDGE_B, RIDGE_SLOPE = 2.0, 1.0
SIG_FLOOR, P_FLOOR = 1e-3, 1e-4
START_PANEL, START_OOS, REFIT_W = "2016-06-01", "2019-01-06", 13
HOLDOUT_SPLIT = "2021-01-03"
# "today" is derived from the data (last daily bar), never hard-coded: the last W-SUN row at or before the last daily
# bar is the last complete Sunday; any later W-SUN row is a partial week (provisional).
ACTIVE_THR = 0.5
RUNUP_W = 8
VARIANTS = {"V0": dict(emis=["y"], tvtp=False, slopes=False),
            "V1": dict(emis=EMIS_W, tvtp=False, slopes=False),
            "V2": dict(emis=EMIS_W, tvtp=True, slopes=False),
            "V3": dict(emis=EMIS_W, tvtp=True, slopes=True)}
HORIZONS = (4, 13, 26)
_G = {}
_LINES = [0]


def say(s):
    if _LINES[0] < 60:
        print(s, flush=True)
    _LINES[0] += 1


def fmt(x, d=3):
    return "na" if x is None or (isinstance(x, float) and not np.isfinite(x)) else (f"{x:.{d}f}" if isinstance(x, (float, np.floating)) else str(x))


def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


def lg(p):
    p = np.clip(np.asarray(p, float), 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


# ------------------------------------------------------------------------------------------- numba kernels
@njit(cache=True)
def _forward(logB, A, pi):
    """Scaled forward filter. logB T x K, A T x K x K (A[t] is the transition into t; A[0] unused), pi K.
    Returns filtered probabilities alpha (T x K) and the one-step-ahead predictive log-likelihood per row."""
    T, K = logB.shape
    alpha = np.empty((T, K))
    ll = np.empty(T)
    a = np.empty(K)
    for t in range(T):
        m = logB[t, 0]
        for j in range(1, K):
            if logB[t, j] > m:
                m = logB[t, j]
        for j in range(K):
            if t == 0:
                pr = pi[j]
            else:
                pr = 0.0
                for i in range(K):
                    pr += alpha[t - 1, i] * A[t, i, j]
            a[j] = pr * np.exp(logB[t, j] - m)
        s = 0.0
        for j in range(K):
            s += a[j]
        for j in range(K):
            alpha[t, j] = a[j] / s
        ll[t] = np.log(s) + m
    return alpha, ll


@njit(cache=True)
def _backward(logB, A, alpha):
    """Smoothed gamma (T x K) and pairwise xi (T x K x K, xi[t] = joint of t-1 and t). Training window only."""
    T, K = logB.shape
    beta = np.ones((T, K))
    gamma = np.empty((T, K))
    xi = np.zeros((T, K, K))
    b = np.empty(K)
    for j in range(K):
        gamma[T - 1, j] = alpha[T - 1, j]
    for t in range(T - 2, -1, -1):
        m = logB[t + 1, 0]
        for j in range(1, K):
            if logB[t + 1, j] > m:
                m = logB[t + 1, j]
        for j in range(K):
            b[j] = np.exp(logB[t + 1, j] - m) * beta[t + 1, j]
        s = 0.0
        for i in range(K):
            acc = 0.0
            for j in range(K):
                acc += A[t + 1, i, j] * b[j]
            beta[t, i] = acc
            s += acc
        for i in range(K):
            beta[t, i] /= s
        g = 0.0
        for i in range(K):
            g += alpha[t, i] * beta[t, i]
        for i in range(K):
            gamma[t, i] = alpha[t, i] * beta[t, i] / g
        tot = 0.0
        for i in range(K):
            for j in range(K):
                v = alpha[t, i] * A[t + 1, i, j] * b[j]
                xi[t + 1, i, j] = v
                tot += v
        for i in range(K):
            for j in range(K):
                xi[t + 1, i, j] /= tot
    return gamma, xi


# ------------------------------------------------------------------------------------------- model pieces
def build(params, E, XR, XC):
    """Emission log-densities (T x K) and the transition tensor (T x K x K) from frozen parameters."""
    K, D = params["mu"].shape
    T = len(E)
    mu_t = np.broadcast_to(params["mu"], (T, K, D)).copy()
    if params["slopes"]:
        mu_t[:, :, 0] += XC @ params["beta"].T
    z = (E[:, None, :] - mu_t) / params["sig"]
    logB = -0.5 * np.sum(z * z, -1) - np.sum(np.log(params["sig"]), -1) - 0.5 * D * np.log(2 * np.pi)
    if params["tvtp"]:
        p = np.clip(sigmoid(params["a"] + XR @ params["b"]), P_FLOOR, 1 - P_FLOOR)
        d = params["d"]
        A = np.empty((T, 2, 2))
        A[:, 0, 1], A[:, 0, 0], A[:, 1, 0], A[:, 1, 1] = p, 1 - p, d, 1 - d
    else:
        A = np.ascontiguousarray(np.broadcast_to(params["P"], (T, K, K)))
    return np.ascontiguousarray(logB), A


def trans_now(params, xr):
    """(p_enter, d) for the forecast transition at the regressor values held at x_t."""
    if params["tvtp"]:
        return np.clip(sigmoid(params["a"] + xr @ params["b"]), P_FLOOR, 1 - P_FLOOR), params["d"]
    P = params["P"]
    return np.full(len(xr), P[0, -1]), P[-1, 0]


def mstep(E, XR, XC, gamma, xi, spec, K, kappa, prev=None, newton_it=8):
    T, D = E.shape
    mu, sig = np.zeros((K, D)), np.ones((K, D))
    Dc = XC.shape[1] if spec["slopes"] else 0
    beta = np.zeros((K, max(Dc, 1)))
    for k in range(K):
        w = gamma[:, k]
        sw = w.sum() + 1e-12
        if spec["slopes"]:
            Z = np.c_[np.ones(T), XC]
            G = (Z * w[:, None]).T @ Z + np.diag(np.r_[0.0, np.full(Dc, RIDGE_SLOPE)])
            coef = np.linalg.solve(G, (Z * w[:, None]).T @ E[:, 0])
            mu[k, 0], beta[k, :Dc] = coef[0], coef[1:]
            r = E[:, 0] - Z @ coef
            sig[k, 0] = np.sqrt((w * r * r).sum() / sw)
            cols = range(1, D)
        else:
            cols = range(D)
        for j in cols:
            mu[k, j] = (w * E[:, j]).sum() / sw
            sig[k, j] = np.sqrt((w * (E[:, j] - mu[k, j]) ** 2).sum() / sw)
    sig = np.maximum(sig, SIG_FLOOR)
    params = {"mu": mu, "sig": sig, "beta": beta, "slopes": spec["slopes"], "tvtp": spec["tvtp"], "K": K,
              "pi": np.clip(gamma[0], P_FLOOR, None) / np.clip(gamma[0], P_FLOOR, None).sum()}
    N = xi[1:].sum(0)
    if spec["tvtp"]:
        x = XR[1:]
        w1, w0 = xi[1:, 0, 1], xi[1:, 0, 0] + kappa / max(1, T - 1)      # sticky prior spread over the rows
        theta = np.r_[prev["a"], prev["b"]] if prev is not None and prev.get("tvtp") else np.r_[lg(0.05), np.zeros(x.shape[1])]
        Z = np.c_[np.ones(len(x)), x]
        reg = np.diag(np.r_[0.0, np.full(x.shape[1], RIDGE_B)])
        for _ in range(newton_it):
            p = sigmoid(Z @ theta)
            g = Z.T @ (w1 - (w0 + w1) * p) - reg @ theta
            H = (Z * ((w0 + w1) * p * (1 - p))[:, None]).T @ Z + reg
            step = np.linalg.solve(H + 1e-8 * np.eye(len(theta)), g)
            theta = theta + np.clip(step, -3, 3)
        params["a"], params["b"] = float(theta[0]), theta[1:]
        params["d"] = float(np.clip(N[1, 0] / (N[1].sum() + kappa), P_FLOOR, 1 - P_FLOOR))
        params["counts"] = N
    else:
        Np = N + kappa * np.eye(K)
        P = Np / Np.sum(1, keepdims=True)
        P = np.clip(P, P_FLOOR, None)
        params["P"] = P / P.sum(1, keepdims=True)
        params["counts"] = N
    return params


def ordered_mstep(E, XR, XC, gamma, xi, spec, K, kappa, prev=None):
    """M-step, then states ordered by the sigma of y (column 0): calm first, active last."""
    params = mstep(E, XR, XC, gamma, xi, spec, K, kappa, prev)
    order = np.argsort(params["sig"][:, 0], kind="stable")
    if not np.array_equal(order, np.arange(K)):
        params = mstep(E, XR, XC, gamma[:, order], xi[:, order][:, :, order], spec, K, kappa, None)
    return params


def em(E, XR, XC, spec, K, kappa, init_gamma=None, params=None, n_iter=100, tol=1e-6):
    """EM on one contiguous training window. Cold start from responsibilities, warm start from parameters."""
    if params is None:
        xi0 = np.zeros((len(E), K, K))
        xi0[1:] = init_gamma[:-1, :, None] * init_gamma[1:, None, :]
        params = ordered_mstep(E, XR, XC, init_gamma, xi0, spec, K, kappa)
    prev_ll = -np.inf
    for _ in range(n_iter):
        logB, A = build(params, E, XR, XC)
        alpha, ll = _forward(logB, A, params["pi"])
        tot = ll.sum()
        if tot - prev_ll < tol:
            break
        prev_ll = tot
        gamma, xi = _backward(logB, A, alpha)
        params = ordered_mstep(E, XR, XC, gamma, xi, spec, K, kappa, params)
    logB, A = build(params, E, XR, XC)
    alpha, ll = _forward(logB, A, params["pi"])
    gamma, xi = _backward(logB, A, alpha)
    params["counts"] = xi[1:].sum(0)
    params["gamma_last"] = gamma[-1]
    return params, float(ll.sum())


def quantile_init(y, K, rng=None, noise=0.0):
    """Deterministic init: rows binned by |y| quantile into K groups (highest |y| = active); optional perturbation."""
    q = np.argsort(np.argsort(np.abs(y))) / max(1, len(y) - 1)
    edges = np.r_[0, 1 - 0.3 * (K - np.arange(1, K)) / (K - 1)] if K > 1 else np.r_[0]
    g = np.full((len(y), K), 0.1 / max(1, K - 1))
    for k in range(K):
        m = (q >= edges[k]) & ((q < edges[k + 1]) if k + 1 < K else True)
        g[m, k] = 0.9
    if noise > 0 and rng is not None:
        g = g + noise * rng.random(g.shape)
    return g / g.sum(1, keepdims=True)


def fit_window(E, XR, XC, spec, K, kappa, n_restart, n_iter, rng, warm=None):
    """Restarts (quantile init + perturbations) plus the warm start; best by TRAINING log-likelihood."""
    best, best_ll, lls = None, -np.inf, []
    for r in range(n_restart):
        g0 = quantile_init(E[:, 0], K, rng, noise=(0.0 if r == 0 else 0.6))
        p, ll = em(E, XR, XC, spec, K, kappa, init_gamma=g0, n_iter=n_iter)
        lls.append(ll)
        if ll > best_ll:
            best, best_ll = p, ll
    if warm is not None and warm["K"] == K and warm["mu"].shape == (K, E.shape[1]):
        p, ll = em(E, XR, XC, spec, K, kappa, params={k: (v.copy() if hasattr(v, "copy") else v) for k, v in warm.items()}, n_iter=n_iter)
        lls.append(ll)
        if ll > best_ll:
            best, best_ll = p, ll
    return best, best_ll, lls


def n_params(params):
    K, D = params["mu"].shape
    n = 2 * K * D + (K - 1)
    if params["slopes"]:
        n += K * params["beta"].shape[1]
    n += (2 + len(params["b"])) if params["tvtp"] else K * (K - 1)
    return int(n)


# ------------------------------------------------------------------------------------------- read-outs
def hazards(p_act, p_enter, d, hs=HORIZONS):
    """Absorbing-chain entry probabilities within h weeks, including current occupancy and pure entry; E[T] to entry."""
    out = {}
    for h in hs:
        out[f"h{h}_incl"] = 1 - (1 - p_act) * (1 - p_enter) ** h
        out[f"h{h}_pure"] = 1 - (1 - p_enter) ** h
    out["ET"] = (1 - p_act) / p_enter
    return out


def monte_carlo(p_act, p_enter, d, mu, sig, lvl, zm0, zs0, n_paths, rng, H=26):
    """Regime paths with Gaussian increments; regressors held at x_t (through p_enter and mu). Returns per row
    P(fall5_13w), P(fall5_26w), P(fall10_26w), mean 13-week logit change. Common random numbers across rows."""
    R = len(p_act)
    U = rng.random((1, n_paths, H))
    Z = rng.standard_normal((1, n_paths, H))
    S = (rng.random((1, n_paths)) < p_act[:, None]).astype(np.int8)            # R x N
    cum = np.zeros((R, n_paths))
    mn13 = np.zeros((R, n_paths))
    mn26 = np.zeros((R, n_paths))
    m13 = np.zeros(R)
    pe = p_enter[:, None]
    for h in range(H):
        u = U[:, :, h]
        S = np.where(S == 0, (u < pe).astype(np.int8), (u >= d).astype(np.int8))
        inc = np.where(S == 1, mu[:, 1:2], mu[:, 0:1]) + np.where(S == 1, sig[1], sig[0]) * Z[:, :, h]
        cum = cum + zm0 + zs0 * inc
        if h < 13:
            mn13 = np.minimum(mn13, cum)
        mn26 = np.minimum(mn26, cum)
        if h == 12:
            m13 = cum.mean(1)
    pct = 100 * sigmoid(lvl)[:, None]
    f13 = pct - 100 * sigmoid(lvl[:, None] + mn13)
    f26 = pct - 100 * sigmoid(lvl[:, None] + mn26)
    return (f13 >= 5).mean(1), (f26 >= 5).mean(1), (f26 >= 10).mean(1), m13


# ------------------------------------------------------------------------------------------- the walk
def standardise(data, t, spec):
    """Training-window moments (rows < t) applied to every row; regressors clipped at 3 sd; NaN -> 0 (no bfill:
    a missing regressor contributes nothing)."""
    E_raw = data["E"][:, spec["cols"]]
    zm, zs = np.nanmean(E_raw[:t], 0), np.nanstd(E_raw[:t], 0) + 1e-9
    E = (E_raw - zm) / zs
    rm, rs = C.zfit(data["XR"][:t])
    cm, cs = C.zfit(data["XC"][:t])
    return {"E": E, "XR": C.zapply(data["XR"], rm, rs), "XRnow": C.zapply(data["XRnow"], rm, rs),
            "XC": C.zapply(data["XC"], cm, cs), "XCnow": C.zapply(data["XCnow"], cm, cs), "zm": zm, "zs": zs}


def walk(data, spec, K=2, kappa=KAPPA_W, n_restart=3, n_iter=100, mc_paths=2000, seed=0, start=START_OOS,
         refit_weeks=REFIT_W, freq="W", keep_blocks=True, fixed_params=None):
    """Expanding-window walk-forward. At each refit date t: fit on rows < t (all complete bars), freeze, filter rows
    0..te_end with the frozen parameters, read out rows t..te_end-1. fixed_params: skip fitting (held-out twin)."""
    idx = data["idx"]
    T = len(idx)
    rng = np.random.default_rng(seed)
    t = int(np.searchsorted(idx, pd.Timestamp(start)))
    step = C.bars(refit_weeks, freq)
    cols = ["p_act", "h4_incl", "h13_incl", "h26_incl", "h26_pure", "ET", "pf5_13", "pf5_26", "pf10_26", "m13", "ll1", "p_enter"]
    S = {c: np.full(T, np.nan) for c in cols}
    refits, blocks, params_log, prev = [], [], [], None
    while t < T:
        te_end = min(t + step, T)
        z = standardise(data, t, spec)
        if fixed_params is None:
            params, ll, lls = fit_window(z["E"][:t], z["XR"][:t], z["XC"][:t], spec, K, kappa, n_restart, n_iter, rng, warm=prev)
        else:
            params, ll, lls = fixed_params, np.nan, []
        logB, A = build(params, z["E"][:te_end], z["XR"][:te_end], z["XC"][:te_end])
        alpha, ll1 = _forward(logB, A, params["pi"])
        te = np.arange(t, te_end)
        p_act = alpha[:, K - 1]
        S["p_act"][te], S["ll1"][te] = p_act[te], ll1[te]
        if K == 2:
            p_enter, d = trans_now(params, z["XRnow"][:te_end])
            hz = hazards(p_act, p_enter, d)
            for k, v in hz.items():
                if k in S:
                    S[k][te] = v[te]
            S["p_enter"][te] = p_enter[te]
            if mc_paths > 0:
                mu = np.broadcast_to(params["mu"][:, 0], (len(te), 2)).copy()
                if params["slopes"]:
                    mu = mu + z["XCnow"][te] @ params["beta"].T
                r = monte_carlo(p_act[te], p_enter[te], d, mu, params["sig"][:, 0], data["lvl"][te], z["zm"][0], z["zs"][0], mc_paths, rng)
                S["pf5_13"][te], S["pf5_26"][te], S["pf10_26"][te], S["m13"][te] = r
            if keep_blocks:
                blocks.append({"t": t, "te_end": te_end, "p_act": p_act.copy(), "h26": hz["h26_incl"].copy()})
        refits.append({"t": str(idx[t].date()), "nTrain": int(t), "ll": round(float(ll), 2) if np.isfinite(ll) else None,
                       "restartLL": [round(float(x), 2) for x in lls], "nParams": n_params(params)})
        params_log.append(params)
        prev = params
        t = te_end
    out = {c: pd.Series(v, index=idx) for c, v in S.items()}
    out.update({"refits": refits, "blocks": blocks, "params": params_log, "K": K})
    return out


# ------------------------------------------------------------------------------------------- data
def weekly_data(D, start=START_PANEL):
    """Weekly panel (Sunday close) with the module's emissions and regressors. Returns (data dict, P, X, Y)."""
    P = C.panel(D, "W")
    X, _ = C.features(P, "W")
    Y = C.extra_targets(P, C.targets(P, "W"), "W")
    lb_d = pd.Series(C.logit(D["BTC.D"].values), index=D.index)
    rv7 = lb_d.diff().rolling(7).std().resample("W-SUN").last()          # trailing 7 days through the week-end
    E = pd.DataFrame({"y": C.level(P, "BTC.D").diff(), "lrv7": np.log(rv7.reindex(P.index).clip(lower=1e-6)),
                      "dlog_ethbtc": np.log(P["ETHBTC"]).diff(), "dlog_btc": np.log(P["BTCUSD"]).diff()}, index=P.index)
    keep = P.index >= pd.Timestamp(start)
    P, X, Y, E = P[keep], X[keep], Y[keep], E[keep]
    ok = E.notna().all(axis=1) & X[REG_TVTP].notna().all(axis=1)
    r0 = int(np.argmax(ok.values))
    P, X, Y, E = P.iloc[r0:], X.iloc[r0:], Y.iloc[r0:], E.iloc[r0:]
    data = {"idx": P.index, "E": E.values.astype(float), "XR": X[REG_TVTP].shift(1).values.astype(float), "XRnow": X[REG_TVTP].values.astype(float),
            "XC": X[X_CONT].shift(1).values.astype(float), "XCnow": X[X_CONT].values.astype(float), "lvl": C.level(P, "BTC.D").values.astype(float),
            "E_names": list(E.columns)}
    return data, P, X, Y


def daily_data(D, start=START_PANEL):
    P = D.copy()
    X, _ = C.features(P, "D")
    lb = pd.Series(C.logit(P["BTC.D"].values), index=P.index)
    rv5 = lb.diff().rolling(5).std()
    E = pd.DataFrame({"y": lb.diff(), "lrv5": np.log(rv5.clip(lower=1e-6)), "dlog_ethbtc": np.log(P["ETHBTC"]).diff(), "dlog_btc": np.log(P["BTCUSD"]).diff()}, index=P.index)
    keep = P.index >= pd.Timestamp(start)
    P, X, E = P[keep], X[keep], E[keep]
    ok = E.notna().all(axis=1) & X[REG_TVTP].notna().all(axis=1)
    r0 = int(np.argmax(ok.values))
    P, X, E = P.iloc[r0:], X.iloc[r0:], E.iloc[r0:]
    return {"idx": P.index, "E": E.values.astype(float), "XR": X[REG_TVTP].shift(1).values.astype(float), "XRnow": X[REG_TVTP].values.astype(float),
            "XC": X[X_CONT].shift(1).values.astype(float), "XCnow": X[X_CONT].values.astype(float), "lvl": lb[keep].iloc[r0:].values.astype(float),
            "E_names": list(E.columns)}


def spec_of(name, data, emis=None):
    v = dict(VARIANTS[name]) if name in VARIANTS else dict(emis=emis, tvtp=False, slopes=False)
    if emis is not None:
        v["emis"] = emis
    v["cols"] = [data["E_names"].index(c) for c in v["emis"]]
    v["name"] = name
    return v


# ------------------------------------------------------------------------------------------- scoring helpers
def score(pred, Y, fresh, is_prob=True, pred10=None):
    """fall5_26w / fall10_26w / onset5_26w AUC + Brier by era, fresh-start AUC on a probability series. fall10_26w is
    scored on pred10 (the model's own 10-point series) when given; otherwise on pred, and the row says so."""
    out = {}
    for tg in ("fall5_26w", "fall10_26w", "onset5_26w"):
        s = pred10 if (tg == "fall10_26w" and pred10 is not None) else pred
        out[tg] = C.metrics(s, Y[tg], True, is_prob=is_prob)
        out[tg]["meanEraAuc"] = mean_era(out[tg])
        if tg == "fall10_26w":
            out[tg]["scoredSeries"] = "own 10-point series" if pred10 is not None else "same series as fall5_26w (no 10-point series)"
    out["fresh_fall5_26w"] = C.metrics(pred.where(fresh), Y["fall5_26w"], True, is_prob=is_prob)
    out["fresh_fall5_26w"]["meanEraAuc"] = mean_era(out["fresh_fall5_26w"])
    return out


def paired_block_boot(pred_a, pred_b, y, n=1000, block_weeks=26, rng=None, metric="auc"):
    """26-week circular block bootstrap of the DIFFERENCE metric(a) - metric(b) on the rows where both are finite
    (the pre-registered incremental statistic: an increment whose band crosses zero is a tie)."""
    rng = rng or np.random.default_rng(0)
    pa, pb, yy = np.asarray(pred_a, float), np.asarray(pred_b, float), np.asarray(y, float)
    m = np.isfinite(pa) & np.isfinite(pb) & np.isfinite(yy)
    pa, pb, yy = pa[m], pb[m], yy[m]
    N, bl = len(pa), block_weeks
    f = C.auc if metric == "auc" else C.spearman
    real = f(pa, yy), f(pb, yy)
    if N < 40 or real[0] is None or real[1] is None:
        return {"n": 0, "rows": int(N)}
    vals = []
    for _ in range(n):
        starts = rng.integers(0, N, size=int(np.ceil(N / bl)))
        ii = np.concatenate([(np.arange(s, s + bl) % N) for s in starts])[:N]
        va, vb = f(pa[ii], yy[ii]), f(pb[ii], yy[ii])
        if va is not None and vb is not None:
            vals.append(va - vb)
    v = np.array(vals)
    return {"n": len(v), "rows": int(N), "real": round(float(real[0] - real[1]), 4), "a": round(float(real[0]), 4), "b": round(float(real[1]), 4),
            "q05": round(float(np.quantile(v, 0.05)), 4), "q50": round(float(np.quantile(v, 0.5)), 4), "q95": round(float(np.quantile(v, 0.95)), 4),
            "pDiffLE0": round(float((v <= 0).mean()), 3), "tie": bool(np.quantile(v, 0.05) <= 0 <= np.quantile(v, 0.95))}


def within_era_rank_auc(pred, y, idx, eras=C.ERAS):
    """Pooled AUC after replacing the prediction by its percentile rank inside each era (removes the era base-rate
    structure that a once-per-cycle variable such as M2 supplies)."""
    r = pd.Series(np.nan, index=idx)
    for e, fr, to in eras:
        m = (idx >= pd.Timestamp(fr)) & (idx < pd.Timestamp(to)) & pred.notna()
        if m.sum():
            r[m] = pred[m].rank(pct=True)
    v = C.auc(r.values, np.asarray(y, float))
    return None if v is None else round(v, 3)


def p_with_n(ns):
    """A null summary's p printed with its draw count; under 20 draws it is labelled as not evidence."""
    n, p = ns.get("n", 0), ns.get("p")
    if p is None:
        return "na"
    return f"{p} (n={n}{', not evidence' if n < 20 else ''})"


def mean_era(met):
    v = [met[e]["auc"] for e, _, _ in [(x[0], 0, 0) for x in C.ERAS] if e in met and met[e].get("auc") is not None]
    return round(float(np.mean(v)), 3) if v else None


def pooled(met, key="auc"):
    return met.get("pooled", {}).get(key)


def train_base_series(Y, tg, idx, lag=26, start=START_OOS, step=REFIT_W):
    """Training-window base rate at each refit (the honest Brier reference)."""
    y = Y[tg].values
    out = np.full(len(idx), np.nan)
    t = int(np.searchsorted(idx, pd.Timestamp(start)))
    while t < len(idx):
        tr = y[:max(0, t - lag)]
        tr = tr[np.isfinite(tr)]
        out[t:t + step] = tr.mean() if len(tr) else np.nan
        t += step
    return pd.Series(out, index=idx)


def brier_skill(pred, base, y):
    out = {}
    for name, fr, to in list(C.ERAS) + [("pooled", "2000-01-01", "2100-01-01")]:
        m = (pred.index >= pd.Timestamp(fr)) & (pred.index < pd.Timestamp(to)) & pred.notna() & y.notna() & base.notna()
        if m.sum() < 20:
            continue
        b, bb = C.brier(pred[m].values, y[m].values), C.brier(base[m].values, y[m].values)
        out[name] = {"brier": round(b, 4), "brierTrainBase": round(bb, 4), "skill": round(1 - b / bb, 3) if bb > 0 else None}
    return out


def regime_features_walkforward(w, idx, oos0):
    """[P(active), logit h26] for the stacked logistic, point in time: rows >= oos0 carry the WALK-FORWARD values
    (produced by the refit that was current at that row, so a later block's training rows see exactly what was read
    out at the time); rows < oos0 carry the first refit's filtered values (its parameters were trained on those rows:
    in-sample for the first fit, disclosed)."""
    reg = np.c_[w["p_act"].values, lg(w["h26_incl"].values)]
    b0 = w["blocks"][0]
    reg[:oos0, 0] = b0["p_act"][:oos0]
    reg[:oos0, 1] = lg(b0["h26"][:oos0])
    return reg


def stack_walk(blocks, F_sig, y, idx, lag=26, min_train=60, use_regime=True, reg=None):
    """Stacked logistic refit at every regime refit: [signals, P(active), logit h26] -> label. reg: the regime feature
    matrix for every row (regime_features_walkforward); when None, the block's own filtered values are used for the
    training rows too (in-sample for the block's parameters: diagnostic only)."""
    pred = np.full(len(idx), np.nan)
    for b in blocks:
        t, te_end = b["t"], b["te_end"]
        if use_regime:
            F = np.c_[F_sig[:te_end], reg[:te_end]] if reg is not None else np.c_[F_sig[:te_end], b["p_act"], lg(b["h26"])]
        else:
            F = F_sig[:te_end]
        tr = np.arange(0, max(0, t - lag))
        tr = tr[np.isfinite(y[tr]) & np.isfinite(F[tr]).all(1)]
        if len(tr) < min_train:
            continue
        mu, sd = C.zfit(F[tr])
        w = C.logistic_fit(C.zapply(F[tr], mu, sd), y[tr])
        te = np.arange(t, te_end)
        ok = te[np.isfinite(F[te]).all(1)]
        pred[ok] = C.logistic_predict(C.zapply(F[ok], mu, sd), w)
    return pd.Series(pred, index=idx)


def nowcast(p_act_oos, p_act_insample, P, idx, thr=ACTIVE_THR):
    """Detection delay from each 5+ event peak to the first week with P(active) > thr, share of the fall still ahead,
    false-alarm rate outside fall windows and their 8-week run-up."""
    ev = C.events(P["BTC.D"], 5.0, freq="W")
    b = P["BTC.D"].values
    oos_start = int(np.searchsorted(idx, pd.Timestamp(START_OOS)))
    rows = []
    for e in ev:
        pk, tr_ = int(idx.get_loc(e["peak"])), int(idx.get_loc(e["trough"]))
        oos = pk >= oos_start
        s = p_act_oos if oos else p_act_insample
        hit = [i for i in range(pk, tr_ + 1) if np.isfinite(s[i]) and s[i] > thr]
        det = hit[0] if hit else None
        rows.append({"peak": str(e["peak"].date()), "trough": str(e["trough"].date()), "points": round(e["from"] - e["to"], 1), "days": e["days"], "oos": oos,
                     "delayWeeks": (None if det is None else det - pk), "shareAhead": (None if det is None else round(float((b[det] - e["to"]) / (e["from"] - e["to"])), 3)),
                     "big": e["from"] - e["to"] >= 20})
    inwin = np.zeros(len(idx), bool)
    for e in ev:
        pk, tr_ = int(idx.get_loc(e["peak"])), int(idx.get_loc(e["trough"]))
        inwin[max(0, pk - RUNUP_W):tr_ + 1] = True
    m = np.isfinite(p_act_oos) & (np.arange(len(idx)) >= oos_start)
    fa = (p_act_oos > thr) & m & ~inwin
    delays = [r["delayWeeks"] for r in rows if r["delayWeeks"] is not None and r["shareAhead"] is not None and r["shareAhead"] >= 0.5]
    delays_oos = [r["delayWeeks"] for r in rows if r["oos"] and r["delayWeeks"] is not None and r["shareAhead"] is not None and r["shareAhead"] >= 0.5]
    return {"events": rows, "falseAlarmRate": round(float(fa.sum() / max(1, m.sum())), 3), "falseAlarmWeeks": int(fa.sum()), "oosWeeks": int(m.sum()),
            "alertWeeksOOS": int(((p_act_oos > thr) & m).sum()),
            "medianDelayHalfAhead": (float(np.median(delays)) if delays else None), "nDetectedHalfAhead": len(delays),
            "nDetected": int(sum(r["delayWeeks"] is not None for r in rows)), "nEvents": len(rows),
            "oosOnly": {"nEvents": int(sum(r["oos"] for r in rows)), "nDetected": int(sum(r["oos"] and r["delayWeeks"] is not None for r in rows)),
                        "nDetectedHalfAhead": len(delays_oos), "medianDelayHalfAhead": (float(np.median(delays_oos)) if delays_oos else None),
                        "note": "criterion (d) is judged here: the pre-2019 events are inside the first training window"}}


def event_table(ser, Y, idx, refit_dates=()):
    """Hazard and P(active) at offsets before each fall5_26w episode start (OOS), plus the full week-by-week path from
    -8 to +2 weeks with refit dates marked (the Oct 2020 - Jan 2021 run specifically: the 2020-10-04 refit sits inside it)."""
    y = Y["fall5_26w"].values.copy()
    oos = int(np.searchsorted(idx, pd.Timestamp(START_OOS)))
    y[:oos] = np.nan
    rd = set(str(pd.Timestamp(x).date()) for x in refit_dates)
    keys = ("p_act", "p_enter", "h26_incl", "pf5_26")
    rows = []
    for s, e in C.episodes(y):
        row = {"start": str(idx[s].date()), "end": str(idx[e].date()), "weeks": e - s + 1}
        for off in (26, 13, 4, 1, 0):
            i = s - off
            if i >= oos:
                row[f"m{off}"] = {k: (round(float(ser[k].iloc[i]), 3) if np.isfinite(ser[k].iloc[i]) else None) for k in ("p_act", "h26_incl", "pf5_26")}
        path = []
        for off in range(-8, 3):
            i = s + off
            if oos <= i < len(idx):
                d = str(idx[i].date())
                path.append({"w": off, "t": d, "refit": d in rd, **{k: (round(float(ser[k].iloc[i]), 3) if np.isfinite(ser[k].iloc[i]) else None) for k in keys}})
        row["path"] = path
        rows.append(row)
    return rows


def dwell(d):
    """Residual duration of the active state (geometric with mean 1/d): median and 90% interval in weeks."""
    q = lambda p: int(np.ceil(np.log(1 - p) / np.log(1 - d)))
    return {"mean": round(1 / d, 1), "median": q(0.5), "q05": q(0.05), "q95": q(0.95)}


def filtered_series(data, spec, params, t_fit, end=None):
    """Filtered P(active) for rows 0..end with frozen params whose z-moments come from rows < t_fit."""
    z = standardise(data, t_fit, spec)
    end = len(data["idx"]) if end is None else end
    logB, A = build(params, z["E"][:end], z["XR"][:end], z["XC"][:end])
    alpha, ll = _forward(logB, A, params["pi"])
    return alpha[:, -1], ll, z


def smoothed_series(data, spec, params, t_fit):
    z = standardise(data, t_fit, spec)
    logB, A = build(params, z["E"], z["XR"], z["XC"])
    alpha, ll = _forward(logB, A, params["pi"])
    gamma, xi = _backward(logB, A, alpha)
    return gamma[:, -1]


# ------------------------------------------------------------------------------------------- null / placebo jobs
def _walk_metrics(data, name, seed, Y, fresh, cfg):
    spec = spec_of(name, data)
    w = walk(data, spec, K=2, kappa=KAPPA_W, n_restart=cfg["restarts"], n_iter=cfg["iters"], mc_paths=cfg["paths"], seed=seed, keep_blocks=False)
    return {"fall5_26w": C.auc(w["pf5_26"].values, Y["fall5_26w"].values), "onset5_26w": C.auc(w["pf5_26"].values, Y["onset5_26w"].values),
            "fresh": C.auc(w["pf5_26"].where(fresh).values, Y["fall5_26w"].values), "y13": C.spearman(w["m13"].values, Y["y13"].values),
            "nowcast_fall5": C.auc(w["p_act"].values, Y["fall5_26w"].values)}


def _exog_job(a):
    """Shifted-exogenous null: roll the regressor block by >= 26 weeks (BTC.D and its emissions stay), rerun the WHOLE
    walk (restarts, EM, filter, Monte Carlo) for V2 and V3."""
    k, seed = a
    g = _G
    data = dict(g["data"])
    df = pd.DataFrame(np.c_[data["XR"], data["XRnow"], data["XC"], data["XCnow"]], index=data["idx"])
    df = C.shift_exog(df, list(df.columns), k)
    v = df.values
    nr, nc = data["XR"].shape[1], data["XC"].shape[1]
    data["XR"], data["XRnow"], data["XC"], data["XCnow"] = v[:, :nr], v[:, nr:2 * nr], v[:, 2 * nr:2 * nr + nc], v[:, 2 * nr + nc:]
    return {n: _walk_metrics(data, n, seed, g["Y"], g["fresh"], g["cfg"]) for n in g["exog_variants"]}


def _placebo_job(a):
    """Placebo emissions (IAAFT per column or 26-week block shuffle of the rows) with the REAL regressors, scored on the
    REAL targets; V0 shows what a regime found on noise forecasts, V2 what the regressors carry alone."""
    kind, seed = a
    g = _G
    rng = np.random.default_rng(seed)
    data = dict(g["data"])
    E = data["E"].copy()
    if kind == "iaaft":
        for j in range(E.shape[1]):
            E[:, j] = C.iaaft(E[:, j], rng, it=30)
    else:
        bl = 26
        n = len(E)
        starts = rng.permutation(np.arange(0, n, bl))
        ii = np.concatenate([np.arange(s, min(n, s + bl)) for s in starts])[:n]
        E = E[ii]
    data["E"] = E
    return {n: _walk_metrics(data, n, seed, g["Y"], g["fresh"], g["cfg"]) for n in ("V0", "V2")}


def _daily_surrogate_job(seed):
    """Daily IAAFT surrogate of the emissions, one V1 fit on the last training window -> 7-step matrix distance."""
    g = _G
    rng = np.random.default_rng(seed)
    data = dict(g["ddata"])
    E = data["E"].copy()
    for j in range(E.shape[1]):
        E[:, j] = C.iaaft(E[:, j], rng, it=30)
    data["E"] = E
    spec = spec_of("V1", data, emis=EMIS_D)
    t = g["d_tfit"]
    z = standardise(data, t, spec)
    params, ll, _ = fit_window(z["E"][:t], z["XR"][:t], z["XC"][:t], spec, 2, KAPPA_D, 2, g["cfg"]["iters"], rng)
    P7 = np.linalg.matrix_power(params["P"], 7)
    return float(np.linalg.norm(P7 - g["Pw"]))


def pool_map(pool, fn, jobs):
    return pool.map(fn, jobs) if pool is not None else [fn(j) for j in jobs]


# ------------------------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--nulls", type=int, default=200)
    ap.add_argument("--fast", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--daily", action="store_true", help="force the daily twin even with --fast (smoke test of that path)")
    a = ap.parse_args()
    t0 = time.time()
    cfg = {"restarts": 3, "iters": 100, "paths": 2000, "nulls": a.nulls, "exog": 100, "placebo": 20, "kgrid": [1, 2, 3, 4], "daily": True, "dsurr": 20, "boot": 1000}
    if a.fast:
        cfg.update({"restarts": 2, "iters": 40, "paths": 500, "nulls": min(a.nulls, 20), "exog": 20, "placebo": 10, "kgrid": [1, 2], "daily": False, "dsurr": 0, "boot": 200})
        a.workers = min(a.workers, 2)
    if a.daily:
        cfg.update({"daily": True, "dsurr": max(cfg["dsurr"], 4)})
    rng = np.random.default_rng(83)
    now_utc = dt.datetime.now(dt.timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        now_et = now_utc.astimezone(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M ET")
    except Exception:
        now_et = "ET unavailable"
    say(f"study8_regime  run {now_utc.strftime('%Y-%m-%d %H:%M UTC')} / {now_et}  fast={a.fast} restarts={cfg['restarts']} iters={cfg['iters']} paths={cfg['paths']} nulls={cfg['nulls']} exog={cfg['exog']}")

    D = C.load_daily(a.data)
    data, P, X, Y = weekly_data(D)
    idx = data["idx"]
    fresh = C.fresh_mask(P, "W")
    last_daily = D.index[-1]                                   # from the data, never a constant
    provisional = [str(d.date()) for d in idx[idx > last_daily]]
    last_complete = idx[idx <= last_daily][-1]
    i_today = int(idx.get_loc(last_complete))
    oos0 = int(np.searchsorted(idx, pd.Timestamp(START_OOS)))
    notes = [f"Rows {len(idx)} from {idx[0].date()} (first week with ETH/BTC increment and rv7); first forecast {START_OOS}; refit every {REFIT_W} weeks; "
             f"last complete Sunday close {last_complete.date()}; provisional bars {provisional} are never in a training window (training rows < refit date) and today's object reads {last_complete.date()}.",
             "Observation is the 1-week logit increment of BTC.D (never the overlapping 13-week change); emissions standardised with training-window moments; "
             "transition regressors are x_{t-1} for the transition into t; M2 carries the harness 6-week lag; rv7 = std of daily logit changes over the 7 days through the Sunday.",
             "x_cont (V3) ethbtc_fromhi52w is NaN before 2017-06-18: in z-units it contributes 0 there (no bfill; state-constant drift applies), flagged.",
             "States ordered by sigma of y after every M-step (K = 2: Hungarian matching is the identity; the previous refit's means are logged for the W-identity check); events never consulted for labelling.",
             "Sticky Dirichlet kappa = 5 (weekly) / 35 (daily) fixed a priori; the kappa grid on the first window is printed as a diagnostic only.",
             "The a-priori readiness pair (M2 y/y, BTC drawdown) was found by looking at all eras in rounds 3-7: disclosed, not a discovery of this module.",
             "The walk never reads targets, so the shifted-TARGET null is scoring-only for the regime series (identical series under any shift); the stacked logistic is refit under every shift.",
             "K is 2 a priori; the training-window BIC winner per refit is logged (K = 3 never switches the forecaster); K in the grid is judged only on OOS one-week-ahead emission log-likelihood (~400 observations)."]
    _G.update({"data": data, "Y": Y, "fresh": fresh, "cfg": cfg, "exog_variants": ["V2", "V3"]})
    say(f"rows {len(idx)} oos-from {idx[oos0].date()} ({len(idx) - oos0} rows) fall5_26w pos {int(Y['fall5_26w'].iloc[oos0:].sum())} in {len(C.episodes(Y['fall5_26w'].values[oos0:]))} episodes; "
        f"fall10_26w pos {int(Y['fall10_26w'].iloc[oos0:].sum())} in {len(C.episodes(Y['fall10_26w'].values[oos0:]))} episode (Oct 2020 - May 2021, none since 2023); onset5_26w pos {int(Y['onset5_26w'].iloc[oos0:].sum())}")

    # ---- kappa diagnostic on the first window (training log-likelihood only; kappa stays 5)
    t_first = oos0
    specV1 = spec_of("V1", data)
    z1 = standardise(data, t_first, specV1)
    kgrid = {}
    for kap in (0.0, 5.0, 20.0):
        p_, ll_, _ = fit_window(z1["E"][:t_first], z1["XR"][:t_first], z1["XC"][:t_first], specV1, 2, kap, 2, cfg["iters"], np.random.default_rng(1))
        kgrid[str(kap)] = {"trainLL": round(ll_, 2), "P": np.round(p_["P"], 4).tolist()}

    # ---- the four variants
    runs, oos, refit_jumps, pcount = {}, {}, {}, {}
    for name in ("V0", "V1", "V2", "V3"):
        spec = spec_of(name, data)
        w = walk(data, spec, K=2, kappa=KAPPA_W, n_restart=cfg["restarts"], n_iter=cfg["iters"], mc_paths=cfg["paths"], seed=10 + len(runs))
        runs[name] = w
        r = score(w["pf5_26"], Y, fresh, pred10=w["pf10_26"])
        r["y13"] = C.metrics(w["m13"], Y["y13"], False)
        mm = np.isfinite(w["m13"].values) & (np.arange(len(idx)) >= oos0)
        r["y13"]["shareNegativePrediction"] = round(float((w["m13"].values[mm] < 0).mean()), 3) if mm.any() else None
        r["nowcast_p_active"] = {tg: C.metrics(w["p_act"], Y[tg], True) for tg in ("fall5_26w", "onset5_26w")}
        r["nowcast_p_active"]["fresh_fall5_26w"] = C.metrics(w["p_act"].where(fresh), Y["fall5_26w"], True)
        r["hazard26_pure"] = {tg: C.metrics(w["h26_pure"], Y[tg], True) for tg in ("fall5_26w", "onset5_26w")}
        r["oosOneStepLL"] = round(float(np.nansum(w["ll1"].values[oos0:])), 2)
        r["withinEraRankAuc_fall5_26w"] = within_era_rank_auc(w["pf5_26"], Y["fall5_26w"], idx)
        oos[name] = r
        # refit artefacts on EVERY scored series, not only P(active) (the forecast series jump more at refits)
        refit_jumps[name] = {s: C.refit_jump_report(w[s], [x["t"] for x in w["refits"]]) for s in ("p_act", "pf5_26", "h26_incl", "p_enter")}
        pcount[name] = C.params_report(w["refits"][-1]["nParams"])
        say(f"{name}: fall5_26w auc mean-of-era {fmt(r['fall5_26w']['meanEraAuc'])} eras {[r['fall5_26w'].get(e[0], {}).get('auc') for e in C.ERAS]} pooled {fmt(pooled(r['fall5_26w']))} within-era-rank {fmt(r['withinEraRankAuc_fall5_26w'])} "
            f"brier {fmt(pooled(r['fall5_26w'], 'brier'), 4)} | onset auc {fmt(pooled(r['onset5_26w']))} fresh {fmt(pooled(r['fresh_fall5_26w']))} | fall10 (own series) {fmt(pooled(r['fall10_26w']))} "
            f"| y13 ic {fmt(pooled(r['y13'], 'ic'))} hit {fmt(pooled(r['y13'], 'hit'))} neg-share {fmt(r['y13']['shareNegativePrediction'])} | P(active) nowcast auc {fmt(pooled(r['nowcast_p_active']['fall5_26w']))} | 1-step LL {r['oosOneStepLL']} | params {w['refits'][-1]['nParams']}")
    base_tr = {tg: train_base_series(Y, tg, idx) for tg in ("fall5_26w", "fall10_26w", "onset5_26w")}
    for name in runs:
        oos[name]["brierSkillVsTrainBase"] = {tg: brier_skill(runs[name]["pf5_26" if tg != "fall10_26w" else "pf10_26"], base_tr[tg], Y[tg]) for tg in ("fall5_26w", "fall10_26w", "onset5_26w")}
    V2, V0, V3 = runs["V2"], runs["V0"], runs["V3"]

    # ---- TVTP stability per refit (V2): the hazard's coefficients, the training entry count and the intercept hazard,
    # and the hazard's per-era ranking power against the RAW regressors it is built from
    tv_rows = []
    for p, r in zip(V2["params"], V2["refits"]):
        N = p["counts"]
        tv_rows.append({"t": r["t"], "a": round(float(p["a"]), 3), "b_m2_yoy": round(float(p["b"][0]), 3), "b_btc_dd_ath": round(float(p["b"][1]), 3),
                        "trainEntries": round(float(N[0, 1]), 1), "trainActiveShare": round(float(N[1].sum() / N.sum()), 3), "pEnterAtTrainingMeanRegressors": round(float(sigmoid(p["a"])), 4),
                        "d": round(float(p["d"]), 4)})
    bm2 = np.array([r["b_m2_yoy"] for r in tv_rows])
    bdd = np.array([r["b_btc_dd_ath"] for r in tv_rows])
    hz_raw = {}
    for e, fr, to in C.ERAS:
        m = (idx >= pd.Timestamp(fr)) & (idx < pd.Timestamp(to))
        hz_raw[e] = {"pEnter": C.auc(V2["p_enter"].values[m], Y["fall5_26w"].values[m]), "h26_pure": C.auc(V2["h26_pure"].values[m], Y["fall5_26w"].values[m]),
                     "raw_m2_yoy": C.auc(data["XRnow"][m, 0], Y["fall5_26w"].values[m]), "raw_btc_dd_ath": C.auc(data["XRnow"][m, 1], Y["fall5_26w"].values[m]),
                     "spearman_pEnter_m2": round(C.spearman(V2["p_enter"].values[m], data["XRnow"][m, 0]), 3)}
        hz_raw[e] = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in hz_raw[e].items()}
    tvtp_stab = {"perRefit": tv_rows, "b_m2_yoy": {"min": float(bm2.min()), "median": float(np.median(bm2)), "max": float(bm2.max()), "negativeRefits": int((bm2 < 0).sum()), "refits": len(bm2)},
                 "b_btc_dd_ath": {"min": float(bdd.min()), "median": float(np.median(bdd)), "max": float(bdd.max())},
                 "trainEntries": {"first": tv_rows[0]["trainEntries"], "last": tv_rows[-1]["trainEntries"]},
                 "interceptHazard26": {"first": round(1 - (1 - tv_rows[0]["pEnterAtTrainingMeanRegressors"]) ** 26, 3), "last": round(1 - (1 - tv_rows[-1]["pEnterAtTrainingMeanRegressors"]) ** 26, 3)},
                 "hazardVsRawRegressorsAucByEra": hz_raw,
                 "interceptOnlyTvtp": "V1 (fixed P) is the intercept-only TVTP: its rows above are the regressor-free reference for V2",
                 "note": "the entry hazard is not one model over the walk: b_m2 changes sign, b_dd dominates until 2023 then collapses, and the intercept rises as the vol collapse relabels the active state (training entries grow)"}
    say(f"TVTP per refit (V2): b_m2 {bm2.min():.2f}..{bm2.max():.2f} (negative in {int((bm2 < 0).sum())}/{len(bm2)} refits) b_dd {bdd.min():.2f}..{bdd.max():.2f}; training entries {tv_rows[0]['trainEntries']} -> {tv_rows[-1]['trainEntries']}, "
        f"intercept h26 {tvtp_stab['interceptHazard26']['first']} -> {tvtp_stab['interceptHazard26']['last']}; p_enter AUC vs raw m2 / raw dd by era: "
        + " ".join(f"{e}: {v['pEnter']}/{v['raw_m2_yoy']}/{v['raw_btc_dd_ath']}" for e, v in hz_raw.items()) + " (2023-26: the hazard inverts what its own regressors carry)")

    # ---- comparators through the harness (identical to study8_baselines) and the incremental tests
    comp = {}
    for cname, cols in (("fixed5", B.SIGNALS), ("m2only", ["m2_yoy"]), ("m2dd", ["m2_yoy", "btc_dd_ath"]), ("clock", ["days_since_halving"])):
        pr = {}
        for tg, binary in (("fall5_26w", True), ("fall10_26w", True), ("y13", False)):
            pred, _ = B.run_fixed(X, Y, tg, "W", binary, cols)
            pr[tg] = pred
        comp[cname] = {"pred": pr, "oos": score(pr["fall5_26w"], Y, fresh, pred10=pr["fall10_26w"]), "y13": C.metrics(pr["y13"], Y["y13"], False), "fall10_26w": C.metrics(pr["fall10_26w"], Y["fall10_26w"], True, is_prob=True)}
        comp[cname]["oos"]["withinEraRankAuc_fall5_26w"] = within_era_rank_auc(pr["fall5_26w"], Y["fall5_26w"], idx)
    eramean = pd.Series(np.nan, index=idx)
    t = oos0
    while t < len(idx):
        tr = Y["fall5_26w"].values[max(0, t - 26 - 104):max(0, t - 26)]
        eramean.iloc[t:t + REFIT_W] = np.nanmean(tr) if np.isfinite(tr).any() else np.nan
        t += REFIT_W
    comp["eramean"] = {"oos": score(eramean, Y, fresh)}
    F5 = X[B.SIGNALS].values.astype(float)
    F2 = X[["m2_yoy", "btc_dd_ath"]].values.astype(float)
    inc = {}
    reg_wf = {}
    for vname in ("V2", "V3"):
        w = runs[vname]
        reg_wf[vname] = regime_features_walkforward(w, idx, oos0)
        st5 = stack_walk(w["blocks"], F5, Y["fall5_26w"].values, idx, reg=reg_wf[vname])
        st2 = stack_walk(w["blocks"], F2, Y["fall5_26w"].values, idx, reg=reg_wf[vname])
        st5_in = stack_walk(w["blocks"], F5, Y["fall5_26w"].values, idx)          # training rows filtered with the block's own parameters: diagnostic
        off5 = pd.Series(sigmoid(lg(comp["fixed5"]["pred"]["fall5_26w"].values) + lg(w["pf5_26"].values) - lg(base_tr["fall5_26w"].values)), index=idx)
        off2 = pd.Series(sigmoid(lg(comp["m2dd"]["pred"]["fall5_26w"].values) + lg(w["pf5_26"].values) - lg(base_tr["fall5_26w"].values)), index=idx)
        # how much better the block's in-sample filtered P(active) is than the walk-forward series on the same rows (last block)
        bl = w["blocks"][-1]
        rows_tr = np.arange(oos0, bl["t"])
        gap = {"rows": int(len(rows_tr)), "aucInSampleFiltered": C.auc(bl["p_act"][rows_tr], Y["fall5_26w"].values[rows_tr]), "aucWalkForward": C.auc(w["p_act"].values[rows_tr], Y["fall5_26w"].values[rows_tr]),
               "meanAbsDiff": round(float(np.nanmean(np.abs(bl["p_act"][rows_tr] - w["p_act"].values[rows_tr]))), 3), "shareDiffOver0_5": round(float(np.nanmean(np.abs(bl["p_act"][rows_tr] - w["p_act"].values[rows_tr]) > 0.5)), 3)}
        inc[vname] = {"stack_fixed5": {"pred": st5, "oos": score(st5, Y, fresh), "features": "walk-forward regime read-outs for training rows >= 2019 (first refit's filter before)"},
                      "stack_m2dd": {"pred": st2, "oos": score(st2, Y, fresh)},
                      "stack_fixed5_insampleFeatures": {"pred": st5_in, "oos": score(st5_in, Y, fresh), "flag": "diagnostic: training-row regime features filtered with the block's own parameters"},
                      "offset_fixed5": {"pred": off5, "oos": score(off5, Y, fresh), "note": "no training: logit(fixed5) + logit(V2 MC) - logit(training base); the headline incremental test"},
                      "offset_m2dd": {"pred": off2, "oos": score(off2, Y, fresh)}, "inSampleFeatureGapLastBlock": gap}
    bb_fixed5 = C.block_boot(comp["fixed5"]["pred"]["fall5_26w"], Y["fall5_26w"], n=cfg["boot"], rng=rng)
    bb_m2dd = C.block_boot(comp["m2dd"]["pred"]["fall5_26w"], Y["fall5_26w"], n=cfg["boot"], rng=rng)
    bb_v2 = C.block_boot(V2["pf5_26"], Y["fall5_26w"], n=cfg["boot"], rng=rng)
    # the pre-registered incremental statistics: paired 26-week block bootstraps of the DIFFERENCE
    y5 = Y["fall5_26w"]
    paired = {"V2-V0": paired_block_boot(V2["pf5_26"], V0["pf5_26"], y5, n=cfg["boot"], rng=rng),
              "V2-m2only": paired_block_boot(V2["pf5_26"], comp["m2only"]["pred"]["fall5_26w"], y5, n=cfg["boot"], rng=rng),
              "V2-m2dd": paired_block_boot(V2["pf5_26"], comp["m2dd"]["pred"]["fall5_26w"], y5, n=cfg["boot"], rng=rng),
              "V2h26pure-m2only": paired_block_boot(V2["h26_pure"], comp["m2only"]["pred"]["fall5_26w"], y5, n=cfg["boot"], rng=rng),
              "stack_fixed5-fixed5": paired_block_boot(inc["V2"]["stack_fixed5"]["pred"], comp["fixed5"]["pred"]["fall5_26w"], y5, n=cfg["boot"], rng=rng),
              "offset_fixed5-fixed5": paired_block_boot(inc["V2"]["offset_fixed5"]["pred"], comp["fixed5"]["pred"]["fall5_26w"], y5, n=cfg["boot"], rng=rng),
              "stack_m2dd-m2dd": paired_block_boot(inc["V2"]["stack_m2dd"]["pred"], comp["m2dd"]["pred"]["fall5_26w"], y5, n=cfg["boot"], rng=rng),
              "offset_m2dd-m2dd": paired_block_boot(inc["V2"]["offset_m2dd"]["pred"], comp["m2dd"]["pred"]["fall5_26w"], y5, n=cfg["boot"], rng=rng),
              "V2-V0:onset": paired_block_boot(V2["pf5_26"], V0["pf5_26"], Y["onset5_26w"], n=cfg["boot"], rng=rng),
              "y13ic:V2-m2only": paired_block_boot(V2["m13"], comp["m2only"]["pred"]["y13"], Y["y13"], n=cfg["boot"], rng=rng, metric="spearman"),
              "y13ic:V2-V0": paired_block_boot(V2["m13"], V0["m13"], Y["y13"], n=cfg["boot"], rng=rng, metric="spearman")}
    pb = lambda k: f"{k} {fmt(paired[k].get('real'))} [{paired[k].get('q05')}, {paired[k].get('q95')}] P(<=0) {paired[k].get('pDiffLE0')}"
    say(f"comparators fall5_26w auc pooled: fixed5 {fmt(pooled(comp['fixed5']['oos']['fall5_26w']))} (block-boot {bb_fixed5.get('q05')}-{bb_fixed5.get('q95')}) m2only {fmt(pooled(comp['m2only']['oos']['fall5_26w']))} "
        f"m2dd {fmt(pooled(comp['m2dd']['oos']['fall5_26w']))} clock {fmt(pooled(comp['clock']['oos']['fall5_26w']))} eramean {fmt(pooled(comp['eramean']['oos']['fall5_26w']))}; fresh: fixed5 {fmt(pooled(comp['fixed5']['oos']['fresh_fall5_26w']))} m2dd {fmt(pooled(comp['m2dd']['oos']['fresh_fall5_26w']))}; "
        f"within-era-rank auc: V2 {fmt(oos['V2']['withinEraRankAuc_fall5_26w'])} V0 {fmt(oos['V0']['withinEraRankAuc_fall5_26w'])} m2only {fmt(comp['m2only']['oos']['withinEraRankAuc_fall5_26w'])} fixed5 {fmt(comp['fixed5']['oos']['withinEraRankAuc_fall5_26w'])}")
    say("paired block-boot of AUC differences (pre-registered incremental statistic; a band containing 0 is a tie): " + "; ".join(pb(k) for k in ("V2-m2dd", "V2-m2only", "V2-V0", "offset_fixed5-fixed5", "stack_fixed5-fixed5", "offset_m2dd-m2dd", "stack_m2dd-m2dd")))
    say(f"y13 IC paired block-boot: {pb('y13ic:V2-m2only')}; {pb('y13ic:V2-V0')}; V2 predicts a fall in {oos['V2']['y13']['shareNegativePrediction']} of OOS weeks (hit {fmt(pooled(oos['V2']['y13'], 'hit'))}); m2only IC {fmt(pooled(comp['m2only']['y13'], 'ic'))}")
    for vname in ("V2", "V3"):
        r = inc[vname]
        say(f"incremental {vname}: fixed5+regime offset {fmt(pooled(r['offset_fixed5']['oos']['fall5_26w']))} stack(wf features) {fmt(pooled(r['stack_fixed5']['oos']['fall5_26w']))} stack(in-sample features, diagnostic) {fmt(pooled(r['stack_fixed5_insampleFeatures']['oos']['fall5_26w']))} (fixed5 {fmt(pooled(comp['fixed5']['oos']['fall5_26w']))}, band {bb_fixed5.get('q05')}-{bb_fixed5.get('q95')}); "
            f"m2dd+regime offset {fmt(pooled(r['offset_m2dd']['oos']['fall5_26w']))} stack {fmt(pooled(r['stack_m2dd']['oos']['fall5_26w']))} (m2dd {fmt(pooled(comp['m2dd']['oos']['fall5_26w']))}); "
            f"fresh stack {fmt(pooled(r['stack_fixed5']['oos']['fresh_fall5_26w']))}/{fmt(pooled(r['stack_m2dd']['oos']['fresh_fall5_26w']))}; brier offset_fixed5 {fmt(pooled(r['offset_fixed5']['oos']['fall5_26w'], 'brier'), 4)} stack {fmt(pooled(r['stack_fixed5']['oos']['fall5_26w'], 'brier'), 4)} vs fixed5 {fmt(pooled(comp['fixed5']['oos']['fall5_26w'], 'brier'), 4)}; "
            f"in-sample-feature gap (last block, {r['inSampleFeatureGapLastBlock']['rows']} training rows): P(active) auc {fmt(r['inSampleFeatureGapLastBlock']['aucInSampleFiltered'])} in-sample vs {fmt(r['inSampleFeatureGapLastBlock']['aucWalkForward'])} walk-forward, {r['inSampleFeatureGapLastBlock']['shareDiffOver0_5']} of rows differ by > 0.5")

    # ---- ablations through the same walk
    abl = {}
    gmm_spec = spec_of("GMM", data, emis=EMIS_W)
    gmm_spec["gmm"] = True

    def gmm_walk():
        """Mixture (no dynamics): the same EM with every transition row equal to the mixing weights; responsibilities
        per row; GMM + counted transitions = the mixture's emissions with the counted P in a forward filter."""
        out_resp, out_cnt = np.full(len(idx), np.nan), np.full(len(idx), np.nan)
        t = oos0
        prev = None
        while t < len(idx):
            te_end = min(t + REFIT_W, len(idx))
            z = standardise(data, t, gmm_spec)
            E = z["E"][:t]
            rng_ = np.random.default_rng(5)
            best, best_ll = None, -np.inf
            for r in range(cfg["restarts"]):
                g = quantile_init(E[:, 0], 2, rng_, noise=(0.0 if r == 0 else 0.6))
                for _ in range(cfg["iters"]):
                    pi = g.mean(0)
                    mu = (g.T @ E) / g.sum(0)[:, None]
                    sig = np.sqrt(np.einsum("tk,tkd->kd", g, (E[:, None, :] - mu) ** 2) / g.sum(0)[:, None])
                    sig = np.maximum(sig, SIG_FLOOR)
                    order = np.argsort(sig[:, 0])
                    pi, mu, sig = pi[order], mu[order], sig[order]
                    zz = (E[:, None, :] - mu) / sig
                    lb = -0.5 * (zz ** 2).sum(-1) - np.log(sig).sum(-1) + np.log(pi)
                    m = lb.max(1, keepdims=True)
                    g = np.exp(lb - m)
                    ll = float((np.log(g.sum(1)) + m[:, 0]).sum())
                    g = g / g.sum(1, keepdims=True)
                if ll > best_ll:
                    best, best_ll = (pi, mu, sig, g), ll
            pi, mu, sig, g = best
            Ea = z["E"][:te_end]
            zz = (Ea[:, None, :] - mu) / sig
            lb = -0.5 * (zz ** 2).sum(-1) - np.log(sig).sum(-1)
            resp = np.exp(lb + np.log(pi) - (lb + np.log(pi)).max(1, keepdims=True))
            resp = resp / resp.sum(1, keepdims=True)
            out_resp[t:te_end] = resp[t:te_end, 1]
            N = g[:-1].T @ g[1:] + KAPPA_W * np.eye(2)
            Pc = N / N.sum(1, keepdims=True)
            A = np.ascontiguousarray(np.broadcast_to(Pc, (te_end, 2, 2)))
            alpha, _ = _forward(np.ascontiguousarray(lb - 0.5 * Ea.shape[1] * np.log(2 * np.pi)), A, pi)
            out_cnt[t:te_end] = alpha[t:te_end, 1]
            t = te_end
        return pd.Series(out_resp, index=idx), pd.Series(out_cnt, index=idx)
    g_resp, g_cnt = gmm_walk()
    abl["gmm_only"] = {"oos": score(g_resp, Y, fresh, is_prob=False)}
    abl["gmm_counted"] = {"oos": score(g_cnt, Y, fresh, is_prob=False)}
    wv = walk(data, spec_of("VOL", data, emis=["lrv7"]), K=2, kappa=KAPPA_W, n_restart=cfg["restarts"], n_iter=cfg["iters"], mc_paths=0, seed=21, keep_blocks=False)
    abl["vol_only_hmm"] = {"oos": score(wv["p_act"], Y, fresh, is_prob=False), "oosOneStepLL_rvOnly": round(float(np.nansum(wv["ll1"].values[oos0:])), 2)}
    rv = pd.Series(data["E"][:, data["E_names"].index("lrv7")], index=idx)
    rv_rule = pd.Series(np.nan, index=idx)
    t = oos0
    while t < len(idx):
        rv_rule.iloc[t:t + REFIT_W] = (rv.iloc[t:t + REFIT_W] > np.nanquantile(rv.iloc[:t], 0.8)).astype(float)
        t += REFIT_W
    abl["rv7_rule_p80"] = {"oos": score(rv_rule, Y, fresh, is_prob=False)}
    mom = pd.Series(-(P["BTC.D"].diff(13)).values, index=idx)
    mom[:oos0] = np.nan
    abl["momentum_13w_fall5"] = {"oos": score((mom >= 5).astype(float).where(mom.notna()), Y, fresh, is_prob=False), "continuous": score(mom, Y, fresh, is_prob=False)["fall5_26w"]}
    # held-out frozen fit: train through 2020, filter 2021-26 with no refit
    t_h = int(np.searchsorted(idx, pd.Timestamp(HOLDOUT_SPLIT)))
    specV2 = spec_of("V2", data)
    zh = standardise(data, t_h, specV2)
    ph, llh, _ = fit_window(zh["E"][:t_h], zh["XR"][:t_h], zh["XC"][:t_h], specV2, 2, KAPPA_W, cfg["restarts"], cfg["iters"], np.random.default_rng(7))
    held = walk(data, specV2, K=2, kappa=KAPPA_W, mc_paths=cfg["paths"], seed=31, start=HOLDOUT_SPLIT, refit_weeks=10000, keep_blocks=False, fixed_params=ph)
    abl["heldout_frozen_2016_2020"] = {"oos": score(held["pf5_26"], Y, fresh, pred10=held["pf10_26"]), "note": "V2 fitted on 2016-07..2020-12 once; 2021-26 filtered with no refit"}
    # same-model test: the LAST refit's parameters frozen over 2021-26 (in-sample for those parameters: shows how far the
    # refit chain's models drift from one another, beside the 2016-20 frozen fit)
    last_fix = walk(data, specV2, K=2, kappa=KAPPA_W, mc_paths=cfg["paths"], seed=32, start=HOLDOUT_SPLIT, refit_weeks=10000, keep_blocks=False, fixed_params=V2["params"][-1])
    abl["frozen_last_fit_2021_2026_insample"] = {"oos": score(last_fix["pf5_26"], Y, fresh, pred10=last_fix["pf10_26"]),
                                                 "flag": "IN-SAMPLE for the parameters (the last refit trained through 2026-09); same-model test only, never a forecast"}
    # leaky twin (flagged): full-sample parameters + smoothed probabilities
    zl = standardise(data, len(idx), specV2)
    pl, _, _ = fit_window(zl["E"][:i_today + 1], zl["XR"][:i_today + 1], zl["XC"][:i_today + 1], specV2, 2, KAPPA_W, cfg["restarts"], cfg["iters"], np.random.default_rng(9))
    sm = pd.Series(smoothed_series(data, specV2, pl, len(idx)), index=idx)
    sm[:oos0] = np.nan
    leaky = C.metrics(sm, Y["fall5_26w"], True)
    abl["leaky_twin_smoothed_fullsample"] = {"oos_fall5_26w": leaky, "gapVsFilteredNowcast": round(float(pooled(leaky) - pooled(oos["V2"]["nowcast_p_active"]["fall5_26w"])), 3),
                                              "flag": "LEAKY: uses the future twice (smoothing and full-sample parameters); diagnostic only"}
    say(f"ablations fall5_26w auc pooled/fresh: gmm_only {fmt(pooled(abl['gmm_only']['oos']['fall5_26w']))}/{fmt(pooled(abl['gmm_only']['oos']['fresh_fall5_26w']))} gmm_counted {fmt(pooled(abl['gmm_counted']['oos']['fall5_26w']))} "
        f"vol_only {fmt(pooled(abl['vol_only_hmm']['oos']['fall5_26w']))}/{fmt(pooled(abl['vol_only_hmm']['oos']['fresh_fall5_26w']))} rv7>p80 {fmt(pooled(abl['rv7_rule_p80']['oos']['fall5_26w']))} "
        f"momentum<=-5 {fmt(pooled(abl['momentum_13w_fall5']['oos']['fall5_26w']))} heldout-frozen-2016-20 {fmt(pooled(abl['heldout_frozen_2016_2020']['oos']['fall5_26w']))} "
        f"(eras {[abl['heldout_frozen_2016_2020']['oos']['fall5_26w'].get(e[0], {}).get('auc') for e in C.ERAS]}) vs refit chain 2021-26 {[oos['V2']['fall5_26w'].get(e[0], {}).get('auc') for e in C.ERAS[1:]]} "
        f"vs last-fit-frozen (in-sample) {[abl['frozen_last_fit_2021_2026_insample']['oos']['fall5_26w'].get(e[0], {}).get('auc') for e in C.ERAS[1:]]}; leaky-twin {fmt(pooled(leaky))} (gap {abl['leaky_twin_smoothed_fullsample']['gapVsFilteredNowcast']})")

    # ---- K grid: OOS one-week-ahead emission log-likelihood (V1 emissions), training BIC log
    kg = {}
    for K in cfg["kgrid"]:
        wk = walk(data, specV1, K=K, kappa=KAPPA_W, n_restart=min(2, cfg["restarts"]), n_iter=cfg["iters"], mc_paths=0, seed=40 + K, keep_blocks=False)
        ll1 = wk["ll1"]
        kg[str(K)] = {"oosOneStepLL": round(float(np.nansum(ll1.values[oos0:])), 2), "perEra": {e: round(float(np.nansum(ll1[(idx >= pd.Timestamp(fr)) & (idx < pd.Timestamp(to))].values)), 2) for e, fr, to in C.ERAS},
                      "trainLL": [r["ll"] for r in wk["refits"]], "nParams": wk["refits"][-1]["nParams"], "nTrain": [r["nTrain"] for r in wk["refits"]]}
    if "2" in kg and "3" in kg:
        bic_pref = []
        for i in range(len(kg["2"]["trainLL"])):
            n = kg["2"]["nTrain"][i]
            b2 = -2 * kg["2"]["trainLL"][i] + kg["2"]["nParams"] * np.log(n)
            b3 = -2 * kg["3"]["trainLL"][i] + kg["3"]["nParams"] * np.log(n)
            bic_pref.append(3 if b3 < b2 else 2)
        kg["bicPreferredK_perRefit"] = bic_pref
    # criterion (e)'s honest comparator: a ONE-state model whose sd scales with last week's realized vol (2 parameters,
    # no hidden state) on the y-only chain; a K = 2 chain that beats K = 1 but not this is vol clustering, not a state
    specV0 = spec_of("V0", data)
    rv_prev = np.r_[np.nan, np.exp(data["E"][:-1, data["E_names"].index("lrv7")])]        # rv7 known at the start of week t
    ll_k1, ll_rv = np.full(len(idx), np.nan), np.full(len(idx), np.nan)
    t = oos0
    while t < len(idx):
        te_end = min(t + REFIT_W, len(idx))
        yz = standardise(data, t, specV0)["E"][:, 0]
        tr = np.arange(1, t)
        mu1, sd1 = yz[tr].mean(), yz[tr].std() + 1e-9
        c2 = np.mean(((yz[tr] - mu1) / rv_prev[tr]) ** 2)
        te = np.arange(t, te_end)
        ll_k1[te] = -0.5 * ((yz[te] - mu1) / sd1) ** 2 - np.log(sd1) - 0.5 * np.log(2 * np.pi)
        sdt = np.sqrt(c2) * rv_prev[te]
        ll_rv[te] = -0.5 * ((yz[te] - mu1) / sdt) ** 2 - np.log(sdt) - 0.5 * np.log(2 * np.pi)
        t = te_end
    kg["yOnlyChain"] = {"K1_constantSd": round(float(np.nansum(ll_k1[oos0:])), 2), "K1_sdScaledByRv7Prev": round(float(np.nansum(ll_rv[oos0:])), 2), "K2_chain_V0": round(float(np.nansum(V0["ll1"].values[oos0:])), 2),
                        "note": "same standardised y per refit; the rv7-scaled one-state model has 2 parameters and no hidden state"}
    say(f"K grid OOS 1-step emission LL (V1 emissions, {len(idx) - oos0} rows): " + " ".join(f"K={k}:{v['oosOneStepLL']}" for k, v in kg.items() if k.isdigit())
        + (f"; BIC prefers K=3 at {sum(x == 3 for x in kg['bicPreferredK_perRefit'])}/{len(kg['bicPreferredK_perRefit'])} refits" if "bicPreferredK_perRefit" in kg else "") + f"; vol-only HMM LL {abl['vol_only_hmm']['oosOneStepLL_rvOnly']} (rv7 only, not comparable); "
        f"y-only chain: K=1 {kg['yOnlyChain']['K1_constantSd']} K=1 sd~rv7(t-1) {kg['yOnlyChain']['K1_sdScaledByRv7Prev']} K=2 (V0) {kg['yOnlyChain']['K2_chain_V0']}")

    # ---- decoy emissions: two random-walk differences appended once
    dec_data = dict(data)
    dec_data["E"] = np.c_[data["E"], rng.standard_normal((len(idx), 2)) * np.nanstd(data["E"][:, 0])]
    dec_data["E_names"] = data["E_names"] + ["decoy1", "decoy2"]
    wd = walk(dec_data, spec_of("DEC", dec_data, emis=EMIS_W + ["decoy1", "decoy2"]), K=2, kappa=KAPPA_W, n_restart=cfg["restarts"], n_iter=cfg["iters"], mc_paths=0, seed=50, keep_blocks=False)
    loads = []
    for p in wd["params"]:
        sep = np.abs(p["mu"][1] - p["mu"][0]) / np.sqrt(0.5 * (p["sig"][0] ** 2 + p["sig"][1] ** 2)) + np.abs(np.log(p["sig"][1] / p["sig"][0]))
        loads.append(int(np.argmax(sep) >= 4))
    decoy = {"refitsWhereActiveSeparationLoadsOnDecoy": int(sum(loads)), "refits": len(loads), "fall5_26w_auc_withDecoys": C.auc(wd["p_act"].values, Y["fall5_26w"].values)}

    # ---- W-identity log: does nearest-mean matching to the previous refit agree with the sigma ordering?
    widentity = {}
    for name in runs:
        ps = runs[name]["params"]
        dis = 0
        for p0, p1 in zip(ps[:-1], ps[1:]):
            same = np.linalg.norm(p1["mu"][1] - p0["mu"][1]) + np.linalg.norm(p1["mu"][0] - p0["mu"][0])
            swap = np.linalg.norm(p1["mu"][1] - p0["mu"][0]) + np.linalg.norm(p1["mu"][0] - p0["mu"][1])
            dis += int(swap < same)
        widentity[name] = {"refitsWhereMeanMatchingDisagreesWithSigmaOrder": dis, "refits": len(ps) - 1}

    # ---- nowcast metrics and the event table (V2)
    def in_sample_series(w):
        """Filtered P(active) under the FIRST refit's parameters (trained 2016-07..2018-12): causal filter, but the
        pre-2019 events are inside that training window, so detections there are in-sample for the parameters."""
        p_in = w["blocks"][0]["p_act"]
        full = np.full(len(idx), np.nan)
        full[:len(p_in)] = p_in
        return full
    nc = {name: nowcast(runs[name]["p_act"].values, in_sample_series(runs[name]), P, idx) for name in ("V0", "V2")}
    act = (V2["p_act"] > ACTIVE_THR) & V2["p_act"].notna()
    btc_r = pd.Series(data["E"][:, data["E_names"].index("dlog_btc")], index=idx)
    split = {"activeWeeksOOS": int(act.sum()), "shareBtcDown": round(float((btc_r[act] < 0).mean()), 3) if act.sum() else None,
             "note": "crash (BTC.D falls because BTC falls faster) vs alt season (alts rise) split of active weeks by the sign of the weekly BTC return"}
    # is P(active) anything but realized vol? raw lrv7 as the nowcast, and two rv7 alert rules at V2's alert count:
    # (i) point in time: lrv7 above the training-window quantile that matches V2's OOS alert share; (ii) descriptive:
    # the top-N OOS weeks by lrv7 with N = V2's OOS alert weeks (not point in time, matched-count comparison only)
    lrv = pd.Series(data["E"][:, data["E_names"].index("lrv7")], index=idx)
    m_oos = np.arange(len(idx)) >= oos0
    alert_share = nc["V2"]["alertWeeksOOS"] / max(1, nc["V2"]["oosWeeks"])
    rv_pit = np.full(len(idx), np.nan)
    t = oos0
    while t < len(idx):      # trailing 104-week quantile (the whole-history quantile never fires after the vol collapse)
        rv_pit[t:t + REFIT_W] = (lrv.values[t:t + REFIT_W] > np.nanquantile(lrv.values[max(0, t - 104):t], 1 - alert_share)).astype(float)
        t += REFIT_W
    rv_pit_in = (lrv.values > np.nanquantile(lrv.values[:oos0], 1 - alert_share)).astype(float)        # pre-2019 rows under the first window's quantile
    thr_top = np.sort(lrv.values[m_oos & np.isfinite(lrv.values)])[::-1][max(0, nc["V2"]["alertWeeksOOS"] - 1)] if nc["V2"]["alertWeeksOOS"] else np.inf
    rv_top = np.where(m_oos, (lrv.values >= thr_top).astype(float), np.nan)
    nc["rv7_rule_pointInTime"] = nowcast(rv_pit, rv_pit_in, P, idx)
    nc["rv7_topN_descriptive"] = nowcast(rv_top, rv_pit_in, P, idx)
    nc["rv7_topN_descriptive"]["flag"] = "NOT point in time (threshold from the whole OOS period): matched-alert-count comparison only"
    vol_credit = {"spearman_pActive_lrv7_OOS": round(C.spearman(V2["p_act"].values[m_oos], lrv.values[m_oos]), 3),
                  "auc_fall5_26w": {"raw_lrv7": C.auc(lrv.values[m_oos], Y["fall5_26w"].values[m_oos]), "V2_pActive": pooled(oos["V2"]["nowcast_p_active"]["fall5_26w"]), "V0_pActive": pooled(oos["V0"]["nowcast_p_active"]["fall5_26w"])},
                  "auc_fresh_fall5_26w": {"raw_lrv7": C.auc(lrv.where(fresh).values[m_oos], Y["fall5_26w"].values[m_oos]), "V2_pActive": pooled(oos["V2"]["nowcast_p_active"]["fresh_fall5_26w"]), "V0_pActive": pooled(oos["V0"]["nowcast_p_active"]["fresh_fall5_26w"])},
                  "activeStateYDriftOverSigma": round(float(V2["params"][-1]["mu"][1, 0] / V2["params"][-1]["sig"][1, 0]), 3)}
    vol_credit["auc_fall5_26w"] = {k: (round(v, 3) if v is not None else None) for k, v in vol_credit["auc_fall5_26w"].items()}
    vol_credit["auc_fresh_fall5_26w"] = {k: (round(v, 3) if v is not None else None) for k, v in vol_credit["auc_fresh_fall5_26w"].items()}
    vol_credit["booking"] = ("realized-vol credit: raw lrv7 scores at least as high as P(active) on fresh-start weeks" if (vol_credit["auc_fresh_fall5_26w"]["raw_lrv7"] or 0) >= (vol_credit["auc_fresh_fall5_26w"]["V2_pActive"] or 0)
                             else "regime credit beyond realized vol on fresh-start weeks")
    i21 = int(idx.get_loc(pd.Timestamp("2021-01-03"))) if pd.Timestamp("2021-01-03") in idx else None
    jan21 = ({"week": "2021-01-03", "btcdChangePts": round(float(P["BTC.D"].iloc[i21] - P["BTC.D"].iloc[i21 - 1]), 2), "dlogBtc": round(float(btc_r.iloc[i21]), 3),
              "lrv7PercentileToDate": round(float((lrv.values[:i21 + 1] <= lrv.values[i21]).mean()), 3), "pActive": round(float(V2["p_act"].iloc[i21]), 3),
              "note": "the only OOS big-event detection at delay 0: BTC.D was flat that week; the state fired on BTC's blow-off volatility"} if i21 else None)
    evt = event_table(V2, Y, idx, refit_dates=[r["t"] for r in V2["refits"]])
    say(f"nowcast V2: detected {nc['V2']['nDetected']}/{nc['V2']['nEvents']} 5+ falls (pre-2019 ones in-sample for the parameters, filter still causal); median delay {nc['V2']['medianDelayHalfAhead']} w on the {nc['V2']['nDetectedHalfAhead']} with >= half ahead, "
        f"OOS ONLY: {nc['V2']['oosOnly']['nDetectedHalfAhead']} of {nc['V2']['oosOnly']['nEvents']} detected with >= half ahead (median {nc['V2']['oosOnly']['medianDelayHalfAhead']}); "
        f"false-alarm rate {nc['V2']['falseAlarmRate']} ({nc['V2']['falseAlarmWeeks']}/{nc['V2']['oosWeeks']} OOS weeks, {nc['V2']['alertWeeksOOS']} alert weeks); active weeks {split['activeWeeksOOS']}, BTC down in {split['shareBtcDown']}")
    say("  per event (peak, delay w, share ahead): " + ", ".join(f"{r['peak'][:7]} {r['delayWeeks']}/{r['shareAhead']}{'*' if r['big'] else ''}" for r in nc["V2"]["events"]) + "  (* big; 2021-01 is the only OOS big one)"
        + (f"; 2021-01-03 week: BTC.D {jan21['btcdChangePts']:+.1f} pts, BTC {jan21['dlogBtc']:+.2f}, rv7 pct {jan21['lrv7PercentileToDate']}" if jan21 else ""))
    say(f"  P(active) vs realized vol: spearman {vol_credit['spearman_pActive_lrv7_OOS']}; fall5_26w auc raw lrv7 {vol_credit['auc_fall5_26w']['raw_lrv7']} vs V2 P(active) {vol_credit['auc_fall5_26w']['V2_pActive']} V0 {vol_credit['auc_fall5_26w']['V0_pActive']}; "
        f"fresh: lrv7 {vol_credit['auc_fresh_fall5_26w']['raw_lrv7']} vs V2 {vol_credit['auc_fresh_fall5_26w']['V2_pActive']}; rv7 rule at the same alert share: point-in-time detected {nc['rv7_rule_pointInTime']['oosOnly']['nDetected']}/{nc['rv7_rule_pointInTime']['oosOnly']['nEvents']} OOS, false alarms {nc['rv7_rule_pointInTime']['falseAlarmWeeks']}; "
        f"({nc['rv7_rule_pointInTime']['alertWeeksOOS']} alerts); top-N (descriptive) {nc['rv7_topN_descriptive']['oosOnly']['nDetected']}/{nc['rv7_topN_descriptive']['oosOnly']['nEvents']}, false alarms {nc['rv7_topN_descriptive']['falseAlarmWeeks']} ({nc['rv7_topN_descriptive']['alertWeeksOOS']} alerts) -> {vol_credit['booking']}")
    big = [r for r in evt if r["start"] >= "2020-09-01" and r["start"] <= "2021-01-31"]
    if big:
        say(f"  Oct 2020 - Jan 2021 episode starting {big[0]['start']}, path w: p_enter/h26/P(fall5_26w) (R = refit that week): "
            + " ".join(f"{p['w']:+d}{'R' if p['refit'] else ''}:{p['p_enter']}/{p['h26_incl']}/{p['pf5_26']}" for p in big[0]["path"]))
    say(f"  refit jumps V2 (median at refit / elsewhere): P(active) {refit_jumps['V2']['p_act']['medianJumpAtRefit']}/{refit_jumps['V2']['p_act']['medianJumpElsewhere']} "
        f"P(fall5_26w) {refit_jumps['V2']['pf5_26']['medianJumpAtRefit']}/{refit_jumps['V2']['pf5_26']['medianJumpElsewhere']} h26 {refit_jumps['V2']['h26_incl']['medianJumpAtRefit']}/{refit_jumps['V2']['h26_incl']['medianJumpElsewhere']} "
        f"p_enter {refit_jumps['V2']['p_enter']['medianJumpAtRefit']}/{refit_jumps['V2']['p_enter']['medianJumpElsewhere']} (the scored forecast series move more at refits than between them)")

    # ---- V3 slopes test: IC on active weeks vs V0 on its own active weeks, with a shifted-target null on those weeks
    def ic_on_active(w, Ys, thr=ACTIVE_THR):
        m = (w["p_act"] > thr).values & np.isfinite(w["m13"].values) & np.isfinite(Ys["y13"].values)
        return C.spearman(w["m13"].values[m], Ys["y13"].values[m]) if m.sum() >= 20 else None     # finite pairs, not active weeks
    v3_act, v0_act = ic_on_active(V3, Y), ic_on_active(V0, Y)
    loose = {"threshold": 0.2, "V3": ic_on_active(V3, Y, 0.2), "V0": ic_on_active(V0, Y, 0.2), "nV3": int((V3["p_act"] > 0.2).sum()), "nV0": int((V0["p_act"] > 0.2).sum()),
             "flag": "secondary diagnostic only: the pre-registered threshold is 0.5 (None = fewer than 20 weeks)"}
    null_v3 = C.shift_null(lambda Ys: ic_on_active(V3, Ys), Y, cfg["nulls"], rng)
    null_v0 = C.shift_null(lambda Ys: ic_on_active(V0, Ys), Y, cfg["nulls"], rng)
    slopes = {"V3_icActiveWeeks": (None if v3_act is None else round(v3_act, 3)), "V0_icActiveWeeks": (None if v0_act is None else round(v0_act, 3)),
              "nActiveV3": int((V3["p_act"] > ACTIVE_THR).sum()), "nActiveV0": int((V0["p_act"] > ACTIVE_THR).sum()),
              "nullV3": C.null_summary(v3_act, null_v3), "nullV0": C.null_summary(v0_act, null_v0), "looseThreshold": loose,
              "lastSlopes": {"calm": dict(zip(X_CONT, np.round(V3["params"][-1]["beta"][0], 3).tolist())), "active": dict(zip(X_CONT, np.round(V3["params"][-1]["beta"][1], 3).tolist()))}}
    say(f"V3 slopes: y13 IC on active weeks {fmt(slopes['V3_icActiveWeeks'])} (n {slopes['nActiveV3']}, null p {slopes['nullV3'].get('p')}) vs V0 {fmt(slopes['V0_icActiveWeeks'])} (n {slopes['nActiveV0']}, p {slopes['nullV0'].get('p')}; None = under 20 weeks); "
        f"at P>0.2: V3 {fmt(loose['V3'])} (n {loose['nV3']}) V0 {fmt(loose['V0'])} (n {loose['nV0']}); "
        f"last slopes calm {slopes['lastSlopes']['calm']} active {slopes['lastSlopes']['active']}")

    # ---- nulls: shifted targets (scoring; stack refit), within-era, shifted-exogenous (whole walk), placebo emissions
    null = {}
    for name in ("V0", "V2", "V3"):
        w = runs[name]
        for tg, ser, key in (("fall5_26w", "pf5_26", "auc"), ("onset5_26w", "pf5_26", "auc"), ("fall10_26w", "pf10_26", "auc"), ("y13", "m13", "ic")):
            real = pooled(oos[name][tg], key)
            f = (lambda Ys, s=w[ser], tg=tg: C.auc(s.values, Ys[tg].values)) if key == "auc" else (lambda Ys, s=w[ser]: C.spearman(s.values, Ys["y13"].values))
            null[f"{name}:{tg}"] = C.null_summary(real, C.shift_null(f, Y, cfg["nulls"], rng))
        fr = (lambda Ys, s=w["pf5_26"].where(fresh): C.auc(s.values, Ys["fall5_26w"].values))
        null[f"{name}:fresh_fall5_26w"] = C.null_summary(pooled(oos[name]["fresh_fall5_26w"]), C.shift_null(fr, Y, cfg["nulls"], rng))
    null["V2:fall5_26w:withinEra"] = {}
    for era in C.ERAS:
        real = oos["V2"]["fall5_26w"].get(era[0], {}).get("auc")
        f = lambda Ys, era=era: C.metrics(V2["pf5_26"], Ys["fall5_26w"], True).get(era[0], {}).get("auc")
        null["V2:fall5_26w:withinEra"][era[0]] = C.null_summary(real, C.within_era_null(f, Y, era, cfg["nulls"], rng))
        ne = null["V2:fall5_26w:withinEra"][era[0]]
        ne["twoSidedP"] = (round(2 * min(ne["p"], 1 - ne["p"]), 3) if ne.get("p") is not None else None)
        ne["wrongSigned"] = bool(ne.get("p") is not None and ne["p"] >= 0.95)       # one-sided p >= 0.95: the era ranks the label the wrong way round against its own shifted null
    st_real = pooled(inc["V2"]["stack_fixed5"]["oos"]["fall5_26w"])
    f_st = lambda Ys: C.auc(stack_walk(V2["blocks"], F5, Ys["fall5_26w"].values, idx, reg=reg_wf["V2"]).values, Ys["fall5_26w"].values)
    null["V2:stack_fixed5:fall5_26w"] = C.null_summary(st_real, C.shift_null(f_st, Y, max(10, cfg["nulls"] // 2), rng))
    for name in ("V0", "V2", "V3"):
        null[f"{name}:y13"]["note"] = "scoring-only shift of the target: NOT a test of the regressors (the series is monotone in slow regressors); the exogenous null and the paired bootstrap vs m2only are the tests"
    we = null["V2:fall5_26w:withinEra"]
    say(f"shifted-target null (scoring only; the walk never sees targets): V2 fall5_26w p {p_with_n(null['V2:fall5_26w'])} (p95 {null['V2:fall5_26w'].get('nullP95')}) onset p {null['V2:onset5_26w'].get('p')} fresh p {null['V2:fresh_fall5_26w'].get('p')} "
        f"y13 p {null['V2:y13'].get('p')} (scoring-only, not a regressor test); within-era real/null-median/one-sided p: " + " ".join(f"{e[0]} {we[e[0]].get('real')}/{we[e[0]].get('nullMedian')}/{we[e[0]].get('p')}{' WRONG-SIGNED (one-sided p >= 0.95)' if we[e[0]].get('wrongSigned') else ''}" for e in C.ERAS)
        + f"; stack(fixed5+V2) p {p_with_n(null['V2:stack_fixed5:fall5_26w'])}")

    ctx = get_context("fork")
    pool = ctx.Pool(a.workers) if a.workers > 1 else None
    t_null = time.time()
    lo = C.bars(26, "W")
    ks = [int(k) for k in rng.integers(lo, len(idx) - lo, size=cfg["exog"])]
    ex = pool_map(pool, _exog_job, [(k, 1000 + i) for i, k in enumerate(ks)])
    exog = {}
    for vname in ("V2", "V3"):
        for stat, key in (("fall5_26w", "fall5_26w"), ("onset5_26w", "onset5_26w"), ("fresh", "fresh_fall5_26w"), ("y13", "y13")):
            k2 = "ic" if stat == "y13" else "auc"
            real = pooled(oos[vname][key], k2) - pooled(oos["V0"][key], k2)
            vals = [r[vname][stat] - pooled(oos["V0"][key], k2) for r in ex if r[vname][stat] is not None]
            exog[f"{vname}-V0:{stat}"] = C.null_summary(real, vals)
            exog[f"{vname}-V0:{stat}"]["absoluteNull"] = {"median": round(float(np.median([r[vname][stat] for r in ex if r[vname][stat] is not None])), 3), "p95": round(float(np.quantile([r[vname][stat] for r in ex if r[vname][stat] is not None], 0.95)), 3)}
    null["shiftedExogenous"] = exog
    exog["note"] = ("V0 (the subtrahend) scores below chance pooled, so V2 - V0 overstates what the regressors add; the paired block bootstrap vs m2dd / m2only is the pre-registered increment"
                    + ("; under 100 draws these p-values are indicative only" if len(ex) < 100 else ""))
    say(f"shifted-exogenous null ({len(ex)} whole-walk reruns{', smoke-sized: indicative only' if len(ex) < 100 else ''}, {time.time() - t_null:.0f}s): V2-V0 fall5 {fmt(exog['V2-V0:fall5_26w'].get('real'))} p {p_with_n(exog['V2-V0:fall5_26w'])} (null p95 {exog['V2-V0:fall5_26w'].get('nullP95')}); onset {fmt(exog['V2-V0:onset5_26w'].get('real'))} p {exog['V2-V0:onset5_26w'].get('p')}; "
        f"fresh {fmt(exog['V2-V0:fresh'].get('real'))} p {exog['V2-V0:fresh'].get('p')}; V3-V0 fall5 p {exog['V3-V0:fall5_26w'].get('p')} y13 ic {fmt(exog['V3-V0:y13'].get('real'))} p {exog['V3-V0:y13'].get('p')}; "
        f"V2 with rolled regressors still scores fall5 median {exog['V2-V0:fall5_26w']['absoluteNull']['median']} (V0 itself {fmt(pooled(oos['V0']['fall5_26w']))}: below chance, so V2-V0 is not the increment)")
    t_pl = time.time()
    pl_jobs = [("iaaft", 2000 + i) for i in range(cfg["placebo"])] + [("block", 3000 + i) for i in range(cfg["placebo"])]
    plr = pool_map(pool, _placebo_job, pl_jobs)
    placebo = {}
    for kind in ("iaaft", "block"):
        rr = [r for (k, _), r in zip(pl_jobs, plr) if k == kind]
        placebo[kind] = {v: {stat: C.null_summary(pooled(oos[v]["fall5_26w" if stat == "fall5_26w" else ("onset5_26w" if stat == "onset5_26w" else "fresh_fall5_26w")]), [x[v][stat] for x in rr if x[v][stat] is not None])
                             for stat in ("fall5_26w", "onset5_26w", "fresh")} for v in ("V0", "V2")}
        placebo[kind]["n"] = len(rr)
    placebo["note"] = "p-values from fewer than 20 draws are not evidence either way (the smoke run); the full run uses 20 per kind"
    say(f"placebo emissions ({cfg['placebo']} IAAFT + {cfg['placebo']} block-shuffle walks, {time.time() - t_pl:.0f}s), fall5_26w auc: V0 real {fmt(pooled(oos['V0']['fall5_26w']))} vs iaaft median {placebo['iaaft']['V0']['fall5_26w'].get('nullMedian')} block {placebo['block']['V0']['fall5_26w'].get('nullMedian')}; "
        f"V2 real {fmt(pooled(oos['V2']['fall5_26w']))} vs iaaft median {placebo['iaaft']['V2']['fall5_26w'].get('nullMedian')} p {p_with_n(placebo['iaaft']['V2']['fall5_26w'])} block {placebo['block']['V2']['fall5_26w'].get('nullMedian')} p {p_with_n(placebo['block']['V2']['fall5_26w'])} (regressors carry the placebo's skill)")
    if pool is not None:
        pool.close()
        pool.join()
        pool = None

    # ---- evidence ceiling on the headline: episode LOO, block bootstrap, clock / era-mean decoys within era
    ceiling = {"episodeLOO_V2": C.episode_loo(V2["pf5_26"], Y["fall5_26w"]), "blockBoot_V2": bb_v2, "blockBoot_fixed5": bb_fixed5, "blockBoot_m2dd": bb_m2dd,
               "episodeLOO_stack_fixed5_V2": C.episode_loo(inc["V2"]["stack_fixed5"]["pred"], Y["fall5_26w"]),
               "decoysWithinEra": {e[0]: {"V2": oos["V2"]["fall5_26w"].get(e[0], {}).get("auc"), "clock": comp["clock"]["oos"]["fall5_26w"].get(e[0], {}).get("auc"), "eramean": comp["eramean"]["oos"]["fall5_26w"].get(e[0], {}).get("auc"), "fixed5": comp["fixed5"]["oos"]["fall5_26w"].get(e[0], {}).get("auc")} for e in C.ERAS},
               "incrementTie": "any increment under 0.05 AUC is inside the 26-week block-bootstrap band and is a tie"}
    say(f"ceiling V2 fall5_26w: block-boot {bb_v2.get('q05')}-{bb_v2.get('q95')}; episode LOO min {ceiling['episodeLOO_V2'].get('min')} at {ceiling['episodeLOO_V2'].get('minEpisode')}; within era V2/clock/eramean/fixed5: "
        + " ".join(f"{e}: {v['V2']}/{v['clock']}/{v['eramean']}/{v['fixed5']}" for e, v in ceiling["decoysWithinEra"].items()))

    # ---- today's reading (last complete Sunday close) with drivers, dwell, transition counts, sensitivities
    pt = V2["params"][-1]
    zt = standardise(data, V2["blocks"][-1]["t"], specV2)
    xr_t = zt["XRnow"][i_today]
    p_enter_t, d_t = trans_now(pt, xr_t[None, :])
    p_enter_t = float(p_enter_t[0])
    e_t = zt["E"][i_today]
    contrib = {n: round(float(-0.5 * ((e_t[j] - pt["mu"][1, j]) / pt["sig"][1, j]) ** 2 - np.log(pt["sig"][1, j]) + 0.5 * ((e_t[j] - pt["mu"][0, j]) / pt["sig"][0, j]) ** 2 + np.log(pt["sig"][0, j])), 3) for j, n in enumerate(EMIS_W)}
    lvl_t = float(data["lvl"][i_today])
    pct_t = 100 * sigmoid(lvl_t)
    mu_act_logit = zt["zm"][0] + zt["zs"][0] * pt["mu"][1, 0]
    dw = dwell(d_t)
    today = {"date": str(last_complete.date()), "btcd": round(float(pct_t), 2), "pActive": round(float(V2["p_act"].iloc[i_today]), 4), "pEnterWeekly": round(p_enter_t, 4), "dExitWeekly": round(float(d_t), 4),
             "hazard": {f"h{h}": {"incl": round(float(V2[f"h{h}_incl"].iloc[i_today]), 4)} for h in (4, 13, 26)}, "hazard26_pure": round(float(V2["h26_pure"].iloc[i_today]), 4),
             "ET_weeksToEntry": round(float(V2["ET"].iloc[i_today]), 1), "pFall5_13w": round(float(V2["pf5_13"].iloc[i_today]), 4), "pFall5_26w": round(float(V2["pf5_26"].iloc[i_today]), 4), "pFall10_26w": round(float(V2["pf10_26"].iloc[i_today]), 4),
             "y13_logit": round(float(V2["m13"].iloc[i_today]), 4), "btcd_in13w": round(float(100 * sigmoid(lvl_t + V2["m13"].iloc[i_today])), 2),
             "dwellWeeks": dw, "expectedFurtherFallPointsIfActive": round(float(-dw["mean"] * mu_act_logit * pct_t / 100 * (1 - pct_t / 100) * 100), 2),
             "transitionCounts": {"calm->active": round(float(pt["counts"][0, 1]), 2), "active->calm": round(float(pt["counts"][1, 0]), 2), "calm->calm": round(float(pt["counts"][0, 0]), 1), "active->active": round(float(pt["counts"][1, 1]), 1)},
             "emissionLLRvsCalm": contrib, "regressors": {"m2_yoy": round(float(data["XRnow"][i_today, 0]), 4), "btc_dd_ath": round(float(data["XRnow"][i_today, 1]), 4)},
             "tvtp": {"a": round(pt["a"], 3), "b": dict(zip(REG_TVTP, np.round(pt["b"], 3).tolist()))},
             "emissionMeans": {"calm": dict(zip(EMIS_W, np.round(pt["mu"][0], 3).tolist())), "active": dict(zip(EMIS_W, np.round(pt["mu"][1], 3).tolist()))},
             "emissionSigmas": {"calm": dict(zip(EMIS_W, np.round(pt["sig"][0], 3).tolist())), "active": dict(zip(EMIS_W, np.round(pt["sig"][1], 3).tolist()))},
             "comparators": {"fixed5": round(float(comp["fixed5"]["pred"]["fall5_26w"].iloc[i_today]), 4), "m2only": round(float(comp["m2only"]["pred"]["fall5_26w"].iloc[i_today]), 4), "m2dd": round(float(comp["m2dd"]["pred"]["fall5_26w"].iloc[i_today]), 4),
                             "stack_fixed5_V2": round(float(inc["V2"]["stack_fixed5"]["pred"].iloc[i_today]), 4), "offset_fixed5_V2": round(float(inc["V2"]["offset_fixed5"]["pred"].iloc[i_today]), 4), "trainBase": round(float(base_tr["fall5_26w"].iloc[i_today]), 4)},
             "variants": {n: {"pActive": round(float(runs[n]["p_act"].iloc[i_today]), 4), "pFall5_26w": round(float(runs[n]["pf5_26"].iloc[i_today]), 4)} for n in runs},
             "provisionalBar": {"date": provisional, "pActive": (round(float(V2["p_act"].iloc[-1]), 4) if provisional else None), "pFall5_26w": (round(float(V2["pf5_26"].iloc[-1]), 4) if provisional else None), "flag": "partial week, not a forecast"}}
    # sensitivity: regressors +/-1 sd and dropped (-> training mean), last emission +/-1 sd re-filtered
    sens = {}
    for j, n in enumerate(REG_TVTP):
        for lab, dv in (("+1sd", 1.0), ("-1sd", -1.0), ("drop", None)):
            x = xr_t.copy()
            x[j] = 0.0 if dv is None else x[j] + dv
            pe, _ = trans_now(pt, x[None, :])
            sens[f"{n}{lab}"] = round(float(1 - (1 - V2["p_act"].iloc[i_today]) * (1 - pe[0]) ** 26), 4)
    for j, n in enumerate(EMIS_W):
        for lab, dv in (("+1sd", 1.0), ("-1sd", -1.0)):
            dd = dict(data)
            E2 = data["E"].copy()
            E2[i_today, j] += dv * zt["zs"][j]
            dd["E"] = E2
            pa, _, _ = filtered_series(dd, specV2, pt, V2["blocks"][-1]["t"], end=i_today + 1)
            sens[f"{n}{lab}"] = round(float(1 - (1 - pa[i_today]) * (1 - p_enter_t) ** 26), 4)
    today["sensitivity_h26_incl"] = sens
    act_means = [float(p["mu"][1, 0] * standardise(data, b["t"], specV2)["zs"][0] + standardise(data, b["t"], specV2)["zm"][0]) for p, b in zip(V2["params"], V2["blocks"])]
    today["activeState"] = {"driftLogitPerWeek": round(float(mu_act_logit), 4), "driftPointsPerWeekAtLevel": round(float(mu_act_logit * pct_t / 100 * (1 - pct_t / 100) * 100), 3),
                            "sigmaPointsPerWeekAtLevel": round(float(zt["zs"][0] * pt["sig"][1, 0] * pct_t / 100 * (1 - pct_t / 100) * 100), 3),
                            "calmSigmaPointsPerWeekAtLevel": round(float(zt["zs"][0] * pt["sig"][0, 0] * pct_t / 100 * (1 - pct_t / 100) * 100), 3),
                            "refitsWithNegativeActiveDrift": int(sum(m < 0 for m in act_means)), "refits": len(act_means),
                            "trainingShareActive": round(float(pt["counts"][1].sum() / pt["counts"].sum()), 3), "meanDwellTrainingWeeks": round(float(1 / d_t), 1),
                            "note": "a state entered ~every 1/p_enter weeks with a dwell of a few weeks is a volatility state, not a rare waterfall state; the MC drift and sigma come from the training window's vol level (2016-18 included), not today's"}
    today["spread_h26_incl"] = [min(sens.values()), max(sens.values())]
    # where today's reading sits in the model's OWN out-of-sample distribution, and what the hazard is made of
    pf_oos = V2["pf5_26"].values[oos0:i_today + 1]
    h_oos = V2["h26_incl"].values[oos0:i_today + 1]
    pe_x0 = float(sigmoid(pt["a"]))
    last_era = C.ERAS[-1][0]
    today["readingInOwnDistribution"] = {"pFall5_26w_percentileOfOOSReadings": round(float(np.nanmean(pf_oos <= today["pFall5_26w"])), 3), "h26_percentileOfOOSReadings": round(float(np.nanmean(h_oos <= today["hazard"]["h26"]["incl"])), 3),
                                         "shareOOSWeeksPFall5Over0_5": round(float(np.nanmean(pf_oos > 0.5)), 3), "oosBaseRate": round(float(np.nanmean(Y["fall5_26w"].values[oos0:])), 3),
                                         "lastEra": {"name": last_era, "pFall5_q05_q50_q95": [round(float(np.nanquantile(V2["pf5_26"][(idx >= pd.Timestamp(C.ERAS[-1][1]))].values, q)), 3) for q in (0.05, 0.5, 0.95)],
                                                     "base": oos["V2"]["fall5_26w"].get(last_era, {}).get("base"), "brierSkillVsTrainBase": oos["V2"]["brierSkillVsTrainBase"]["fall5_26w"].get(last_era, {}).get("skill"), "auc": oos["V2"]["fall5_26w"].get(last_era, {}).get("auc")},
                                         "class": "training-window unconditional reading at today's level: the MC inherits the training window's vol and active-state drift, not today's (13-week vol at its 4th percentile)"}
    today["hazardDecomposition"] = {"pEnterAtTrainingMeanRegressors": round(pe_x0, 4), "pEnterToday": round(p_enter_t, 4), "h26PureAtTrainingMeanRegressors": round(1 - (1 - pe_x0) ** 26, 4), "h26PureToday": round(float(V2["h26_pure"].iloc[i_today]), 4),
                                    "logitContribution": {"intercept": round(float(pt["a"]), 3), **{n: round(float(xr_t[j] * pt["b"][j]), 3) for j, n in enumerate(REG_TVTP)}},
                                    "note": "today's h26 is the intercept: the regressors move it by less than 0.01; the intercept rose over the walk as the training entry count grew (see tvtpStability)"}
    today["sensitivityNote"] = "regressor and emission perturbations only; parameter uncertainty (sign flips of b_m2 across refits) is not propagated, so the spread understates the hazard's uncertainty"
    say(f"TODAY {today['date']} BTC.D {today['btcd']}: P(active) {today['pActive']} | entry hazard/w {today['pEnterWeekly']} (intercept alone {today['hazardDecomposition']['pEnterAtTrainingMeanRegressors']}) -> h26 incl {today['hazard']['h26']['incl']} pure {today['hazard26_pure']} (intercept alone {today['hazardDecomposition']['h26PureAtTrainingMeanRegressors']}) h13 {today['hazard']['h13']['incl']} E[T] {today['ET_weeksToEntry']} w | "
        f"MC P(fall5_13w) {today['pFall5_13w']} P(fall5_26w) {today['pFall5_26w']} P(fall10_26w) {today['pFall10_26w']} y13 {today['y13_logit']} (BTC.D {today['btcd_in13w']} in 13w)")
    rd_ = today["readingInOwnDistribution"]
    say(f"  today's P(fall5_26w) is the {rd_['pFall5_26w_percentileOfOOSReadings']:.0%} percentile of the model's own OOS readings; {rd_['shareOOSWeeksPFall5Over0_5']:.0%} of OOS weeks read > 0.5 against a {rd_['oosBaseRate']:.0%} base; "
        f"in {last_era} readings span {rd_['lastEra']['pFall5_q05_q50_q95']} (q05/q50/q95) against base {rd_['lastEra']['base']}, Brier skill {rd_['lastEra']['brierSkillVsTrainBase']}, auc {rd_['lastEra']['auc']}: a training-window unconditional reading, not a reading of current conditions")
    say(f"  dwell if active: median {dw['median']} w (90% {dw['q05']}-{dw['q95']}), expected further fall {today['expectedFurtherFallPointsIfActive']} pts; transition counts {today['transitionCounts']}; LLR vs calm by emission {contrib}; "
        f"TVTP a {today['tvtp']['a']} b {today['tvtp']['b']}; regressors {today['regressors']}; sensitivity h26 spread {today['spread_h26_incl']}")
    say(f"  active state: drift {today['activeState']['driftPointsPerWeekAtLevel']} pts/w, sigma {today['activeState']['sigmaPointsPerWeekAtLevel']} vs calm {today['activeState']['calmSigmaPointsPerWeekAtLevel']} pts/w at today's level; "
        f"negative drift in {today['activeState']['refitsWithNegativeActiveDrift']}/{today['activeState']['refits']} refits; training share active {today['activeState']['trainingShareActive']}, mean dwell {today['activeState']['meanDwellTrainingWeeks']} w")
    say(f"  comparators today fall5_26w: fixed5 {today['comparators']['fixed5']} m2only {today['comparators']['m2only']} m2dd {today['comparators']['m2dd']} stack(fixed5+V2) {today['comparators']['stack_fixed5_V2']} offset {today['comparators']['offset_fixed5_V2']} base {today['comparators']['trainBase']}; "
        f"variants " + " ".join(f"{n} P(act) {v['pActive']} P(f5) {v['pFall5_26w']}" for n, v in today["variants"].items()) + f"; provisional {provisional}: P(act) {today['provisionalBar']['pActive']}")

    # ---- truncation test (features, emissions and the filter recomputed from the daily panel truncated at t)
    blocks_t = [(b["t"], b["te_end"]) for b in V2["blocks"]]

    def series_at(end_pos):
        """The walk's P(active) read-out rebuilt on the DAILY panel truncated at idx[end_pos]: features, emissions,
        training moments and the filter recomputed; each row scored by the refit block it belongs to. series_at(n-1)
        is therefore the reported series itself, and series_at(t)[t] must equal it to 1e-9."""
        out = np.full(len(idx), np.nan)
        Dt = D[D.index <= idx[end_pos]]
        dt_, _, _, _ = weekly_data(Dt)
        assert dt_["idx"][-1] == idx[end_pos] and len(dt_["idx"]) == end_pos + 1
        for b, (t_, e_) in enumerate(blocks_t):
            if t_ > end_pos:
                break
            end = min(e_, end_pos + 1)
            pa, _, _ = filtered_series(dt_, specV2, V2["params"][b], t_, end=end)
            out[t_:end] = pa[t_:end]
        return out
    trunc = C.truncation_test(series_at, len(idx), n=20, rng=np.random.default_rng(3), tol=1e-9)
    full = V2["p_act"].values
    worst = 0.0
    for tpos in np.random.default_rng(4).integers(oos0, len(idx) - 1, size=20):
        part = series_at(int(tpos))
        worst = max(worst, abs(part[tpos] - full[tpos]))
    trunc["maxAbsDiffVsReported"] = float(worst)
    trunc["ok"] = bool(trunc["ok"] and worst <= 1e-9)
    say(f"truncation test (daily panel cut at t, features+emissions+filter recomputed, {trunc['tested']} + 20 points): ok {trunc['ok']} max diff {trunc['maxAbsDiff']:.2e} / vs reported {worst:.2e}; "
        f"max refit jumps V2 at refit / elsewhere: P(active) {refit_jumps['V2']['p_act']['maxJumpAtRefit']}/{refit_jumps['V2']['p_act']['maxJumpElsewhere']} P(fall5_26w) {refit_jumps['V2']['pf5_26']['maxJumpAtRefit']}/{refit_jumps['V2']['pf5_26']['maxJumpElsewhere']}; params V3 {pcount['V3']['parameters']} vs 12 episodes ({pcount['V3']['note']})")
    if a.fast:
        assert trunc["ok"], "truncation test failed"

    # ---- daily twin and chain self-similarity (full run only)
    selfsim = {"skipped": True}
    if cfg["daily"]:
        t_d = time.time()
        ddata = daily_data(D)
        specD = spec_of("V1", ddata, emis=EMIS_D)
        wdd = walk(ddata, specD, K=2, kappa=KAPPA_D, n_restart=cfg["restarts"], n_iter=cfg["iters"], mc_paths=0, seed=60, freq="D", keep_blocks=False)
        pa_d = wdd["p_act"]
        # weekly value = the daily filtered posterior on the week's last day (the Sunday itself; BTC.D trades every day)
        pa_w = pa_d.reindex(idx)
        pa_w[idx > last_daily] = np.nan
        Pd, Pw = wdd["params"][-1]["P"], runs["V1"]["params"][-1]["P"]
        Pd7 = np.linalg.matrix_power(Pd, 7)
        dist = float(np.linalg.norm(Pd7 - Pw))
        half = int(np.searchsorted(idx, pd.Timestamp("2021-07-04")))
        halves = []
        for lo_, hi_ in ((0, half), (half, i_today + 1)):
            sub = {k: (v[lo_:hi_] if isinstance(v, np.ndarray) else v) for k, v in data.items()}
            sub["idx"] = idx[lo_:hi_]
            zs_ = standardise(sub, hi_ - lo_, specV1)
            ph_, _, _ = fit_window(zs_["E"], zs_["XR"], zs_["XC"], specV1, 2, KAPPA_W, cfg["restarts"], cfg["iters"], np.random.default_rng(11))
            halves.append(ph_["P"])
        half_dist = float(np.linalg.norm(halves[0] - halves[1]))
        _G.update({"ddata": ddata, "d_tfit": int(np.searchsorted(ddata["idx"], pd.Timestamp(wdd["refits"][-1]["t"]))), "Pw": Pw})
        pool_d = ctx.Pool(a.workers) if (a.workers > 1 and cfg["dsurr"]) else None    # forked AFTER the daily globals exist
        sd = pool_map(pool_d, _daily_surrogate_job, [4000 + i for i in range(cfg["dsurr"])]) if cfg["dsurr"] else []
        if pool_d is not None:
            pool_d.close()
            pool_d.join()
        dd_ = float(Pd[1, 0])
        selfsim = {"skipped": False, "Pw": np.round(Pw, 4).tolist(), "Pd": np.round(Pd, 5).tolist(), "Pd7": np.round(Pd7, 4).tolist(), "frobenius_Pd7_vs_Pw": round(dist, 4),
                   "halfSampleWeeklyDistance": round(half_dist, 4), "halves": [np.round(h, 4).tolist() for h in halves],
                   "dailyIaaftSurrogates": ({"n": len(sd), "p05": round(float(np.quantile(sd, 0.05)), 4), "median": round(float(np.median(sd)), 4)} if sd else None),
                   "activeDwell": {"weeklyMeanWeeks": round(1 / float(Pw[1, 0]), 2), "dailyMeanDays_over7": round(1 / dd_ / 7, 2), "weeklyEntryPerWeek": round(float(Pw[0, 1]), 4), "dailyEntryPer7days": round(float(Pd7[0, 1]), 4)},
                   "dailyPActiveOnSundays": score(pa_w, Y, fresh, is_prob=False), "dailyRefits": len(wdd["refits"]), "dailyRows": int(len(ddata["idx"])),
                   "passes": {"belowHalfSample": dist < half_dist, "belowIaaftP05": (bool(dist < np.quantile(sd, 0.05)) if sd else None)}, "runtimeSec": round(time.time() - t_d, 1)}
        say(f"selfsim: ||Pd^7 - Pw||_F {dist:.4f} vs half-sample weekly {half_dist:.4f} vs daily-IAAFT p05 {selfsim['dailyIaaftSurrogates']['p05'] if sd else 'na'}; Pw {selfsim['Pw']} Pd^7 {selfsim['Pd7']}; "
            f"active dwell weekly {selfsim['activeDwell']['weeklyMeanWeeks']} w vs daily/7 {selfsim['activeDwell']['dailyMeanDays_over7']}; daily P(active) on Sundays fall5_26w auc {fmt(pooled(selfsim['dailyPActiveOnSundays']['fall5_26w']))} fresh {fmt(pooled(selfsim['dailyPActiveOnSundays']['fresh_fall5_26w']))} ({time.time() - t_d:.0f}s)")

    # ---- success criteria (a)-(f)
    def era_wins(a_, b_, tg):
        return sum(1 for e in C.ERAS if (oos[a_][tg].get(e[0], {}).get("auc") or 0) > (oos[b_][tg].get(e[0], {}).get("auc") or 0))
    crit = {"a_V2beatsV0_onset": {"erasWon": era_wins("V2", "V0", "onset5_26w"), "pooledGain": round(float(pooled(oos["V2"]["onset5_26w"]) - pooled(oos["V0"]["onset5_26w"])), 3), "exogP": exog["V2-V0:onset5_26w"].get("p")},
            "b_V2_meanEraAuc": {"meanEra": oos["V2"]["fall5_26w"]["meanEraAuc"], "brierSkillEveryEra": all((v.get("skill") or -1) > 0 for e, v in oos["V2"]["brierSkillVsTrainBase"]["fall5_26w"].items() if e != "pooled"),
                                "freshPooled": pooled(oos["V2"]["fresh_fall5_26w"]), "freshNullP95": null["V2:fresh_fall5_26w"].get("nullP95")},
            "c_V3slopes": {"V3icActive": slopes["V3_icActiveWeeks"], "V0icActive": slopes["V0_icActiveWeeks"], "V3nullP": slopes["nullV3"].get("p")},
            "d_nowcast": {"oosOnly": nc["V2"]["oosOnly"], "falseAlarmRate": nc["V2"]["falseAlarmRate"], "allEventsInclInSample": {"medianDelayHalfAhead": nc["V2"]["medianDelayHalfAhead"], "nDetectedHalfAhead": nc["V2"]["nDetectedHalfAhead"], "nDetected": nc["V2"]["nDetected"], "nEvents": nc["V2"]["nEvents"]},
                          "volCredit": vol_credit["booking"], "minOosDetectionsToJudge": 3,
                          "caveat": "judged on OOS events only; the pre-2019 detections use the first refit's parameters (in-sample); undetected falls are listed in nowcast.events"},
            "e_K2beatsK1_oosLL": ({"K1": kg["1"]["oosOneStepLL"], "K2": kg["2"]["oosOneStepLL"], "yOnly": kg["yOnlyChain"]} if "1" in kg and "2" in kg else None),
            "f_selfsim": selfsim.get("passes")}
    crit["a_V2beatsV0_onset"]["pairedBlockBootV2minusV0"] = {k: paired["V2-V0:onset"].get(k) for k in ("real", "q05", "q95", "pDiffLE0")}
    crit["a_V2beatsV0_onset"]["caveat"] = f"V0 scores {fmt(pooled(oos['V0']['fall5_26w']))} pooled (below chance): V2 - V0 is a gain over a below-chance baseline; vs m2dd the paired difference is {paired['V2-m2dd'].get('real')} [{paired['V2-m2dd'].get('q05')}, {paired['V2-m2dd'].get('q95')}]"
    crit["b_V2_meanEraAuc"]["withinEraWrongSigned"] = [e[0] for e in C.ERAS if null["V2:fall5_26w:withinEra"][e[0]].get("wrongSigned")]
    crit["a_pass"] = bool(crit["a_V2beatsV0_onset"]["erasWon"] >= 2 and crit["a_V2beatsV0_onset"]["pooledGain"] > 0 and (crit["a_V2beatsV0_onset"]["exogP"] or 1) < 0.05)
    crit["b_pass"] = bool((crit["b_V2_meanEraAuc"]["meanEra"] or 0) >= 0.70 and crit["b_V2_meanEraAuc"]["brierSkillEveryEra"] and (crit["b_V2_meanEraAuc"]["freshPooled"] or 0) >= 0.60 and (crit["b_V2_meanEraAuc"]["freshPooled"] or 0) > (crit["b_V2_meanEraAuc"]["freshNullP95"] or 1))
    crit["c_pass"] = bool(slopes["V3_icActiveWeeks"] is not None and slopes["V0_icActiveWeeks"] is not None and slopes["V3_icActiveWeeks"] > slopes["V0_icActiveWeeks"] and (slopes["nullV3"].get("p") or 1) < 0.05)
    d_oos = nc["V2"]["oosOnly"]
    crit["d_pass"] = (None if d_oos["nDetectedHalfAhead"] < 3 else bool(d_oos["medianDelayHalfAhead"] <= 3 and nc["V2"]["falseAlarmRate"] < 0.10))     # None = not identifiable
    crit["e_pass"] = bool(crit["e_K2beatsK1_oosLL"] and crit["e_K2beatsK1_oosLL"]["K2"] > crit["e_K2beatsK1_oosLL"]["K1"])
    crit["e_K2beatsRv7ScaledOneState"] = bool(kg["yOnlyChain"]["K2_chain_V0"] > kg["yOnlyChain"]["K1_sdScaledByRv7Prev"])
    crit["e_reading"] = ("K = 2 beats a one-state model whose sd follows last week's rv7: a persistent vol regime beyond simple vol scaling" if crit["e_K2beatsRv7ScaledOneState"]
                         else "K = 2 beats K = 1 but not a one-state model whose sd follows last week's rv7: (e) establishes vol clustering, not a waterfall state")
    crit["f_pass"] = (None if selfsim.get("skipped") else bool(selfsim["passes"]["belowHalfSample"] and selfsim["passes"]["belowIaaftP05"]))
    say(f"criteria: a {crit['a_pass']} (V2>V0 onset in {crit['a_V2beatsV0_onset']['erasWon']}/3 eras, gain {crit['a_V2beatsV0_onset']['pooledGain']} over a below-chance V0, paired band [{paired['V2-V0:onset'].get('q05')}, {paired['V2-V0:onset'].get('q95')}], exog p {crit['a_V2beatsV0_onset']['exogP']}) "
        f"| b {crit['b_pass']} (mean-era {crit['b_V2_meanEraAuc']['meanEra']}, brier skill all eras {crit['b_V2_meanEraAuc']['brierSkillEveryEra']}, fresh {crit['b_V2_meanEraAuc']['freshPooled']} vs p95 {crit['b_V2_meanEraAuc']['freshNullP95']}, wrong-signed within era: {crit['b_V2_meanEraAuc']['withinEraWrongSigned']}) "
        f"| c {crit['c_pass']} | d {crit['d_pass']} (None = not identifiable: {d_oos['nDetectedHalfAhead']} of {d_oos['nEvents']} OOS falls detected with >= half ahead; {vol_credit['booking']}) | e {crit['e_pass']} (vs rv7-scaled one-state {crit['e_K2beatsRv7ScaledOneState']}) | f {crit['f_pass']}; "
        f"W-identity disagreements V2 {widentity['V2']['refitsWhereMeanMatchingDisagreesWithSigmaOrder']}/{widentity['V2']['refits']} (means only: the state's meaning still drifts, see TVTP per refit)")
    ws = crit["b_V2_meanEraAuc"]["withinEraWrongSigned"]
    say(f"verdict: regime read-outs vs fixed5 {fmt(pooled(comp['fixed5']['oos']['fall5_26w']))} (band {bb_fixed5.get('q05')}-{bb_fixed5.get('q95')}): V2 forecast mean-of-era {fmt(oos['V2']['fall5_26w']['meanEraAuc'])} (pooled {fmt(pooled(oos['V2']['fall5_26w']))}, within-era-rank {fmt(oos['V2']['withinEraRankAuc_fall5_26w'])}, "
        f"{'wrong-signed within ' + ', '.join(ws) if ws else 'no era wrong-signed at one-sided p >= 0.95'}), "
        f"V2 - m2dd paired {paired['V2-m2dd'].get('real')} [{paired['V2-m2dd'].get('q05')}, {paired['V2-m2dd'].get('q95')}], offset+fixed5 - fixed5 {paired['offset_fixed5-fixed5'].get('real')} [{paired['offset_fixed5-fixed5'].get('q05')}, {paired['offset_fixed5-fixed5'].get('q95')}]; "
        f"nowcast credit (P(active) alone) {fmt(pooled(oos['V2']['nowcast_p_active']['fall5_26w']))} vs raw rv7 {vol_credit['auc_fall5_26w']['raw_lrv7']} vs forecast credit on fresh starts {fmt(pooled(oos['V2']['fresh_fall5_26w']))}; the pooled numbers rest on two liquidity swings (M2 moves once per cycle): within-era rows above are the test")

    # ---- results.json
    strip = lambda d: {k: v for k, v in d.items() if k != "pred"}
    res = {"module": "study8_regime", "runUtc": now_utc.strftime("%Y-%m-%d %H:%M UTC"), "runEt": now_et, "fast": a.fast, "config": cfg, "runtimeSec": round(time.time() - t0, 1),
           "oos": oos, "comparators": {k: strip(v) for k, v in comp.items()}, "incremental": {v: {k: strip(x) for k, x in r.items()} for v, r in inc.items()},
           "pairedBlockBoot": paired, "tvtpStability": tvtp_stab, "volCredit": vol_credit, "jan2021Week": jan21,
           "ablations": abl, "kgrid": kg, "kappaGridFirstWindow": kgrid, "decoy": decoy, "null": null, "placebo": placebo, "nowcast": nc, "crashVsAltSeason": split, "events": evt,
           "slopesTest": slopes, "today": today, "selfsim": selfsim, "ceiling": ceiling, "refitJumps": refit_jumps, "wIdentity": widentity, "paramsReport": pcount, "truncation": trunc, "criteria": crit,
           "refits": {n: runs[n]["refits"] for n in runs},
           "series": {"V2_pActive": C.thin(V2["p_act"], every=2), "V2_hazard26": C.thin(V2["h26_incl"], every=2), "V2_pFall5_26w": C.thin(V2["pf5_26"], every=2), "V0_pActive": C.thin(V0["p_act"], every=2),
                      "V3_pFall5_26w": C.thin(V3["pf5_26"], every=2), "fixed5": C.thin(comp["fixed5"]["pred"]["fall5_26w"], every=2), "stack_fixed5_V2": C.thin(inc["V2"]["stack_fixed5"]["pred"], every=2)},
           "notes": notes}
    res["notes"] += [f"In-sample big events for the parameters: 2016-11 and 2017-12 are inside every training window; only 2021-01 is out of sample.",
                     f"Parameter counts: " + ", ".join(f"{n} {runs[n]['refits'][-1]['nParams']}" for n in runs) + " against 12 label episodes (3 big events).",
                     "GMM ablation is an in-module mixture EM (no sklearn dependency); hmmlearn is not used (no TVTP / regressors there).",
                     "Monte Carlo holds the regressors at x_t and uses common random numbers within a refit block; the forecast scores are the MC P(fall) series, the nowcast rows score P(active) alone.",
                     "fall10_26w is one episode (Oct 2020 - May 2021): its AUC ranks one event.",
                     "Placebo emissions keep the REAL regressors, so V2's placebo AUC is what M2 + BTC drawdown carry without any regime; V0's placebo AUC is what a regime found on noise forecasts.",
                     "The daily twin uses fixed P (V1) for the chain comparison; the self-similarity distance uses the last refit's parameters on both scales (descriptive, not a forecast).",
                     "fall10_26w rows score each model's OWN 10-point series (pf10_26 for the regime variants, the fixed logistic's fall10 model for comparators); stacks, offsets and ablations without a 10-point series say so in scoredSeries.",
                     "The stacked logistic's regime features for training rows are the walk-forward read-outs (rows >= 2019-01-06) and the first refit's filtered values before; the block's-own-parameters version is kept as a flagged diagnostic (inSampleFeatureGapLastBlock quantifies the gap); the no-training offset is the headline incremental test.",
                     "The entry hazard is not one model over the walk (tvtpStability): b_m2 changes sign, b_dd dominates until 2023 then collapses to 0, the intercept rises as the training entry count grows; today's h26 is the intercept (hazardDecomposition); V1 (fixed P) is the intercept-only TVTP reference; in 2023-26 p_enter ranks fall5_26w below chance while raw M2 and BTC drawdown rank it above 0.8.",
                     "Criterion (d) is judged on OOS events only (pre-2019 detections use the first refit's parameters); P(active) is compared with raw lrv7 and with rv7 alert rules at the same alert share (volCredit); the 2021-01-03 detection was a flat-BTC.D, +23% BTC week (jan2021Week).",
                     "Refit-jump reports cover P(active), P(fall5_26w), h26 and p_enter; events[].path gives the -8..+2 week path with refit weeks marked (the 2020-10-04 refit cut h26 from 0.87 to 0.47 two weeks before the Oct 2020 episode).",
                     "Paired 26-week block bootstraps of AUC/IC differences (pairedBlockBoot) are the pre-registered incremental statistics; V2 - V0 is reported but V0 is below chance pooled, so it is not the increment; y13 is scored against m2only's IC and its shifted-target p is scoring-only.",
                     "'Today' is derived from the last daily bar in the data (last complete Sunday = last W-SUN row at or before it; later rows provisional), never a constant; today's P(fall5_26w) is reported with its percentile in the model's own OOS readings and the last era's Brier skill.",
                     "Criterion (e) is also judged against a one-state model whose sd follows last week's rv7 (kgrid.yOnlyChain): beating K = 1 alone only shows vol clustering.",
                     "Smoke-sized nulls (exog 20, placebo 10 per kind, shifted 20) give indicative p-values only; the full run (exog 100, placebo 20, 3 restarts, 100 iterations, 2000 paths, daily twin) is required before any number enters the forecast stack."]
    C.write_results(a.out, res)
    try:
        chart(a.out, V2, V0, comp, inc, Y, idx, P, oos0)
    except Exception as e:  # charts are optional
        res["notes"].append(f"chart skipped: {e}")
        C.write_results(a.out, res)
    say(f"done {time.time() - t0:.0f}s -> {a.out}/results.json")


def chart(out_dir, V2, V0, comp, inc, Y, idx, P, oos0):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(3, 1, figsize=(12, 9), sharex=True)
    m = idx >= idx[oos0]
    ax[0].plot(idx[m], P["BTC.D"].values[m], color="k", lw=1)
    ax[0].set_ylabel("BTC.D")
    for e in C.events(P["BTC.D"], 5.0, freq="W"):
        if e["peak"] >= idx[oos0]:
            ax[0].axvspan(e["peak"], e["trough"], color="tab:red", alpha=0.15)
    ax[1].plot(idx, V2["p_act"], label="V2 P(active) filtered", color="tab:red")
    ax[1].plot(idx, V0["p_act"], label="V0 P(active)", color="tab:gray", lw=0.8)
    ax[1].plot(idx, V2["h26_incl"], label="V2 hazard 26w incl.", color="tab:orange", lw=0.8)
    for r in V2["refits"]:
        ax[1].axvline(pd.Timestamp(r["t"]), color="k", alpha=0.08)
    ax[1].legend(loc="upper left", fontsize=8)
    ax[2].plot(idx, V2["pf5_26"], label="V2 MC P(fall5_26w)", color="tab:red")
    ax[2].plot(idx, comp["fixed5"]["pred"]["fall5_26w"], label="fixed5", color="tab:blue", lw=0.8)
    ax[2].plot(idx, inc["V2"]["stack_fixed5"]["pred"], label="stack fixed5+V2", color="tab:green", lw=0.8)
    ax[2].fill_between(idx, 0, Y["fall5_26w"].fillna(0).values, color="tab:red", alpha=0.1, step="mid", label="fall5_26w label")
    ax[2].legend(loc="upper left", fontsize=8)
    ax[2].set_xlim(idx[oos0], idx[-1])
    fig.tight_layout()
    fig.savefig(os.path.join(out_dir, "regime_v2.png"), dpi=110)
    plt.close(fig)


if __name__ == "__main__":
    main()
