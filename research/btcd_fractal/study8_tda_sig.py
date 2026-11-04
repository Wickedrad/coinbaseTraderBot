#!/usr/bin/env python3
"""Round 8 trial [5] tda_sig: persistent homology and path signatures as alt-season forecasters.

Question. Is geometric instability (persistent homology of a delay embedding of the five-series increment path)
anything beyond realized vol, and does the ORDER of moves across series (path-signature Levy areas, in particular
stablecoin share leading dominance) add to the five signals plus a vol block, within eras and on fresh-start weeks,
with the same sign at daily scale?

Design (ROUND8_PLAN.md section [5]). Inputs logit BTC.D, logit USDT.D (2017-07+), log TOTAL3 (2017-07+), log ETHBTC,
log BTCUSD. Window W = 26 weeks (52 as the only sweep) at weekly, 90 days at daily. TDA block: increments standardised
by TRAILING 104-bar mean/sd (raw) or inside the window (scale-free); delay embedding d = 3, tau = 1; Vietoris-Rips to
H1 (ripser, numpy fallback); 8 summaries. Signature block: window path rebased to zero, time-augmented, depth 2 by
iterated sums; 10 Levy areas + 5 time-areas (scaled by trailing sds), 15 symmetric products (ablation), 10 depth-3
timing terms; block-shuffled decoys. Vol block: five *_vol13w + vol-of-vol. Nested models M0..M6 through the shared
harness (C.walk_forward, expanding, first forecast 2019-01-06 or when min_train 60 is reached, refit 13 weeks, labels
lagged by their horizon). Daily replica and daily-to-weekly transfer with a matched-random-walk control. Nulls:
shifted targets on every model and on the increment over M1, within-era shifted targets, block-shuffled area features,
IAAFT surrogate panels through the whole feature pipeline.

  python3 research/btcd_fractal/study8_tda_sig.py --data research/btcd_fractal/data --out research/btcd_fractal/out8/tda_sig [--nulls 200] [--fast]

Review fixes (round-8 fixer): every increment, band, null and the verdict are taken against the same model fitted on the
SAME training rows (M1r / M0r / M1t2), since the 5-series blocks only exist from 2018-01 while M0/M1 fitted from 2016-06
hold the Dec 2017 waterfall; mean-of-era AUC, Brier versus the training-window base rate by era and an episode bootstrap
are printed beside the pooled numbers; the single-area null is a circular shift of the real area series (the per-bar
block shuffle is white); the M4d decoy keeps one permutation per 26-bar segment; a base-rate-matched random-walk placebo
level is printed for every absolute AUC; daily null p is 'na' below 20 draws; the verdict no longer fails a p of 0.

Point in time: every feature of bar t is a function of closes <= t (windows end at t; trailing stats end at t); every
fitted object (z-scores, residualisation betas, coefficients) is fitted on training rows whose label horizon has
elapsed, refit every 13 weeks and frozen for the test block. The --fast run asserts, at 20 random t, that the
features recomputed on the panel truncated at t equal the reported values exactly.
"""
import argparse
import json
import os
import sys
import time
from multiprocessing import get_context

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")  # one BLAS thread per process: the Pool(4) workers must not oversubscribe 4 cores

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import study8_common as C  # noqa: E402
from study8_baselines import SIGNALS  # noqa: E402

try:
    from ripser import ripser as _ripser
    HAVE_RIPSER = True
except Exception:  # pragma: no cover
    HAVE_RIPSER = False

# ----------------------------------------------------------------------------------------- constants (a priori)
SERIES5 = ["USDT.D", "BTC.D", "TOTAL3", "ETHBTC", "BTCUSD"]  # USDT.D first so area_USDT.D>BTC.D reads "stablecoin share leads dominance"
SERIES4 = ["TOTAL2", "BTC.D", "ETHBTC", "BTCUSD"]        # long-history variant (no USDT.D / TOTAL3)
LATE_START = {"USDT.D": "2017-07-14", "TOTAL3": "2017-07-14"}  # USDT.D is near zero before; never bfilled
W_W, W_SWEEP, W_D = 26, 52, 90                             # window in bars: weekly, weekly sweep, daily
TRAIL = 104                                               # trailing bars for the increment mean/sd
MINP = {"W": 13, "D": 26}                                 # min bars before a trailing sd is used
EMB_D, EMB_TAU = 3, 1
GRID = np.linspace(0.0, 2.0, 41)                          # landscape grid, standardised units (fixed)
N_LANDMARKS = 40
BLOCK = 4                                                 # decoy block-shuffle block length (bars)
START = "2019-01-06"
VOL_PROXY_CORR = 0.8
DATA_CUT = "2016-06-01"
VOL_COLS = ["btcd_vol13w", "usdtd_vol13w", "total3_vol13w", "ethbtc_vol13w", "btcusd_vol13w", "btcd_volvol"]
TDA_NAMES = ["h0tot", "h0max", "h1tot", "h1max", "h1n", "ent", "land1", "land2"]
BIG = [pd.Timestamp(x) for x in C.BIG_EVENTS]

LINES = []


def say(s):
    LINES.append(s)


def fmt(v, d=3):
    return "na" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f"{v:.{d}f}"


# ----------------------------------------------------------------------------------------- regularised GLMs
def logistic_fit_lam(Xz, y, lam, it=25):
    """C.logistic_fit with a per-feature ridge penalty (lam per block: 1 for blocks <= 10 features, 10 above)."""
    A = np.c_[np.ones(len(Xz)), Xz]
    w = np.zeros(A.shape[1])
    reg = np.diag(np.r_[0.0, np.asarray(lam, float)])
    for _ in range(it):
        p = 1 / (1 + np.exp(-A @ w))
        g = A.T @ (p - y) + reg @ w
        H = (A * (p * (1 - p))[:, None]).T @ A + reg
        w -= np.linalg.solve(H + 1e-6 * np.eye(len(w)), g)
    return w


def ridge_fit_lam(Xz, y, lam):
    A = np.c_[np.ones(len(Xz)), Xz]
    I = np.diag(np.r_[0.0, np.asarray(lam, float)])
    return np.linalg.solve(A.T @ A + I, A.T @ y)


# ----------------------------------------------------------------------------------------- levels and increments
def level_panel(P, series):
    L = pd.DataFrame(index=P.index)
    for n in series:
        x = C.level(P, n)
        if n in LATE_START:
            x = x.where(P.index >= pd.Timestamp(LATE_START[n]))
        L[n] = x.values
    return L


def trailing_stats(dX, minp):
    """Trailing TRAIL-bar mean/sd of the increments ending at t (inclusive), computed window by window (no online
    recursion, so a truncated panel reproduces the full-panel value bit for bit)."""
    v = dX.values.astype(float)
    n, m = v.shape
    mu = np.full((n, m), np.nan)
    sd = np.full((n, m), np.nan)
    for t in range(n):
        w = v[max(0, t - TRAIL + 1):t + 1]
        for j in range(m):
            wj = w[:, j]
            wj = wj[np.isfinite(wj)]
            if len(wj) >= minp:
                mu[t, j] = wj.mean()
                sd[t, j] = wj.std(ddof=1)
    return pd.DataFrame(mu, index=dX.index, columns=dX.columns), pd.DataFrame(sd, index=dX.index, columns=dX.columns)


# ----------------------------------------------------------------------------------------- path signatures
def sig_window(dx, sd_t, want_run=True):
    """Depth-2 signature of the window path (rows = increments, last row = bar t), time-augmented (dt = 1/W).
    S2_ij = sum_{s<r} X_i(s) X_j(r) + 0.5 sum_r X_i(r) X_j(r). Levy area A = 0.5 (S2 - S2^T): A_ij > 0 when i moves
    first and j follows. Sym = 0.5 (S2 + S2^T) = 0.5 dX_i dX_j (momentum products). Timing T = mean_r A(r) - 0.5 A(W):
    the running area integrated against time, zero when the area accrues linearly, positive when it accrued early.
    Everything scaled by the product of the trailing sds (time gets scale 1)."""
    W, m = dx.shape
    X = np.c_[dx, np.full(W, 1.0 / W)]
    Cm = np.cumsum(X, 0)
    Cprev = np.r_[np.zeros((1, m + 1)), Cm[:-1]]
    sc = np.r_[sd_t, 1.0]
    sc = np.outer(sc, sc)
    if not want_run:
        S2 = Cprev.T @ X + 0.5 * X.T @ X
        return 0.5 * (S2 - S2.T) / sc, None, None
    O = Cprev[:, :, None] * X[:, None, :] + 0.5 * X[:, :, None] * X[:, None, :]
    S2run = np.cumsum(O, 0)
    S2 = S2run[-1]
    A = 0.5 * (S2 - S2.T)
    Sym = 0.5 * (S2 + S2.T)
    Arun = 0.5 * (S2run - np.swapaxes(S2run, 1, 2))
    T = Arun.mean(0) - 0.5 * A
    return A / sc, Sym / sc, T / sc


def sig_names(series):
    m = len(series)
    pairs = [(i, j) for i in range(m) for j in range(i + 1, m)]
    area = [f"area_{series[i]}>{series[j]}" for i, j in pairs]
    tarea = [f"tarea_{series[i]}" for i in range(m)]
    sym = [f"sym_{series[i]}*{series[j]}" for i in range(m) for j in range(i, m)]
    tim = [f"tim_{series[i]}>{series[j]}" for i, j in pairs]
    return pairs, area, tarea, sym, tim


def block_shuffle(win, rng, block=BLOCK):
    n = len(win)
    blocks = [win[s:s + block] for s in range(0, n, block)]
    order = rng.permutation(len(blocks))
    return np.concatenate([blocks[k] for k in order], 0)


# ----------------------------------------------------------------------------------------- persistent homology
def maxmin_landmarks(pts, k):
    n = len(pts)
    chosen = [0]
    dmin = np.linalg.norm(pts - pts[0], axis=1)
    for _ in range(k - 1):
        j = int(np.argmax(dmin))
        chosen.append(j)
        dmin = np.minimum(dmin, np.linalg.norm(pts - pts[j], axis=1))
    return pts[np.sort(chosen)]


def rips_fallback(pts, max_n=N_LANDMARKS):
    """Vietoris-Rips H0 (Prim MST) and H1 (Z2 column reduction of the triangle boundary with bitset columns) on at
    most max_n maxmin landmarks. Returns [H0 bars, H1 bars] with finite deaths only (ripser's convention minus the
    one infinite H0 bar)."""
    if len(pts) > max_n:
        pts = maxmin_landmarks(pts, max_n)
    n = len(pts)
    Dm = np.sqrt(np.maximum(((pts[:, None, :] - pts[None, :, :]) ** 2).sum(-1), 0.0))
    visited = np.zeros(n, bool)
    visited[0] = True
    mind = Dm[0].copy()
    deaths = []
    for _ in range(n - 1):
        mind[visited] = np.inf
        j = int(np.argmin(mind))
        deaths.append(float(mind[j]))
        visited[j] = True
        mind = np.minimum(mind, Dm[j])
    h0 = np.c_[np.zeros(len(deaths)), np.array(deaths)]
    iu, ju = np.triu_indices(n, 1)
    ev = Dm[iu, ju]
    order = np.argsort(ev, kind="stable")
    rank = np.empty(len(ev), int)
    rank[order] = np.arange(len(ev))
    ev_sorted = ev[order]
    eid = np.full((n, n), -1, int)
    eid[iu, ju] = rank
    eid[ju, iu] = rank
    tris = []
    for i in range(n):
        for j in range(i + 1, n):
            for k in range(j + 1, n):
                e1, e2, e3 = int(eid[i, j]), int(eid[i, k]), int(eid[j, k])
                mx = max(e1, e2, e3)
                tris.append((ev_sorted[mx], mx, (1 << e1) | (1 << e2) | (1 << e3)))
    tris.sort(key=lambda z: (z[0], z[1]))
    pivots = {}
    h1 = []
    for tval, _, col in tris:
        low = col.bit_length() - 1
        while col and low in pivots:
            col ^= pivots[low]
            low = col.bit_length() - 1
        if col:
            pivots[low] = col
            b = ev_sorted[low]
            if tval > b:
                h1.append((b, tval))
    h1 = np.array(h1, float).reshape(-1, 2) if h1 else np.zeros((0, 2))
    return [h0, h1]


def rips(pts):
    if HAVE_RIPSER:
        dg = _ripser(pts, maxdim=1)["dgms"]
        h0 = dg[0]
        h0 = h0[np.isfinite(h0[:, 1])]
        return [h0.astype(float), dg[1].astype(float)]
    return rips_fallback(pts)


def landscape_norms(bars, grid=GRID, k=2):
    if len(bars) == 0:
        return [0.0] * k
    b, d = bars[:, 0][:, None], bars[:, 1][:, None]
    tent = np.maximum(0.0, np.minimum(grid[None, :] - b, d - grid[None, :]))
    srt = -np.sort(-tent, axis=0)
    dx = grid[1] - grid[0]
    return [float(np.sqrt((srt[j] ** 2).sum() * dx)) if j < len(srt) else 0.0 for j in range(k)]


def embed(Z, d=EMB_D, tau=EMB_TAU):
    W, m = Z.shape
    n = W - (d - 1) * tau
    pts = np.concatenate([Z[k * tau:k * tau + n] for k in range(d)], axis=1)
    return pts / np.sqrt(d * m)   # a point is d*m standardised coordinates; /sqrt(dm) keeps typical distances ~sqrt 2


def tda_summaries(pts):
    h0, h1 = rips(pts)
    h0p = h0[:, 1] - h0[:, 0]
    h1p = (h1[:, 1] - h1[:, 0]) if len(h1) else np.zeros(0)
    allp = np.r_[h0p, h1p]
    allp = allp[allp > 0]
    if len(allp):
        p = allp / allp.sum()
        ent = float(-(p * np.log(p)).sum())
    else:
        ent = 0.0
    l1, l2 = landscape_norms(h1)
    return [float(h0p.sum()), float(h0p.max()) if len(h0p) else 0.0, float(h1p.sum()), float(h1p.max()) if len(h1p) else 0.0,
            float(len(h1)), ent, l1, l2]


# ----------------------------------------------------------------------------------------- feature builder
def extra_features(L, W, minp, tag="", with_tda=True, with_decoy=True, with_sf=True, with_btcd=True, last_only=False, decoy_seed=12345):
    """All module features for the level panel L (columns = series): signature blocks, decoys, TDA raw / scale-free /
    BTC.D-only. Row t uses increments (t-W+1..t) and trailing stats ending at t. Returns (DataFrame, blocks)."""
    series = list(L.columns)
    dX = L.diff()
    mu, sd = trailing_stats(dX, minp)
    pairs, area, tarea, sym, tim = sig_names(series)
    n = len(L)
    cols = {}
    blocks = {}

    def add_block(name, names):
        blocks[name + tag] = [c + tag for c in names]
        for c in names:
            cols[c + tag] = np.full(n, np.nan)
    add_block("area", area)
    add_block("tarea", tarea)
    add_block("sym", sym)
    add_block("tim", tim)
    if with_decoy:
        add_block("dec_area", ["dec_" + c for c in area])
        add_block("dec_tarea", ["dec_" + c for c in tarea])
    if with_tda:
        add_block("tda_raw", ["tda_" + c for c in TDA_NAMES])
        if with_sf:
            add_block("tda_sf", ["tdasf_" + c for c in TDA_NAMES])
        if with_btcd:
            add_block("tda_btcd", ["tdab_" + c for c in TDA_NAMES])
    dXv, muv, sdv = dX.values, mu.values, sd.values
    m = len(series)
    rows = [n - 1] if last_only else range(W, n)
    for t in rows:
        if t < W:
            continue
        win = dXv[t - W + 1:t + 1]
        sd_t, mu_t = sdv[t], muv[t]
        if not (np.isfinite(win).all() and np.isfinite(sd_t).all() and (sd_t > 0).all()):
            continue
        A, S, T = sig_window(win, sd_t)
        for q, (i, j) in enumerate(pairs):
            cols[area[q] + tag][t] = A[i, j]
            cols[tim[q] + tag][t] = T[i, j]
        for i in range(m):
            cols[tarea[i] + tag][t] = A[i, m]
        q = 0
        for i in range(m):
            for j in range(i, m):
                cols[sym[q] + tag][t] = S[i, j]
                q += 1
        if with_decoy:
            # one block permutation per W-bar segment (seed changes every W bars, never per bar): consecutive windows
            # share the permutation, so the decoy keeps an autocorrelation like the real area instead of being white
            rng = np.random.default_rng(decoy_seed + t // W)
            Ad, _, _ = sig_window(block_shuffle(win, rng), sd_t, want_run=False)
            for q, (i, j) in enumerate(pairs):
                cols["dec_" + area[q] + tag][t] = Ad[i, j]
            for i in range(m):
                cols["dec_" + tarea[i] + tag][t] = Ad[i, m]
        if with_tda:
            Z = (win - mu_t) / sd_t
            v = tda_summaries(embed(Z))
            for c, x in zip(TDA_NAMES, v):
                cols["tda_" + c + tag][t] = x
            if with_sf:
                Zs = (win - win.mean(0)) / (win.std(0, ddof=1) + 1e-12)
                v = tda_summaries(embed(Zs))
                for c, x in zip(TDA_NAMES, v):
                    cols["tdasf_" + c + tag][t] = x
            if with_btcd:
                v = tda_summaries(embed(Z[:, [series.index("BTC.D")]]))
                for c, x in zip(TDA_NAMES, v):
                    cols["tdab_" + c + tag][t] = x
    return pd.DataFrame(cols, index=L.index), blocks


def area_shift_null(X, cols, post, y, n, rng, min_shift=W_W):
    """Autocorrelation-preserving null for the single-feature |AUC - 0.5| of each area: the REAL feature series (all
    columns together, rows where every column is finite) is circularly shifted by >= min_shift bars and rescored on
    the same rows and labels. Returns per-column {realAuc, realAbsAuc, p, shiftP95} plus the family-wise p for every
    column (share of draws whose max over the columns of |AUC - 0.5| reaches the column's real value) and nBeat."""
    valid = X[cols].notna().all(axis=1)
    A = X.loc[valid, cols].values.astype(float)
    sel = (post & valid)[valid].values
    yy = np.asarray(y, float)[(post & valid).values]
    real = np.array([C.auc(A[sel, j], yy) for j in range(len(cols))], float)
    real_abs = np.abs(real - 0.5)
    draws, mx = [], []
    N = len(A)
    for _ in range(n):
        if N <= 2 * min_shift:
            break
        k = int(rng.integers(min_shift, N - min_shift))
        S = np.roll(A, k, 0)
        v = np.array([abs(C.auc(S[sel, j], yy) - 0.5) for j in range(len(cols))], float)
        draws.append(v)
        mx.append(float(np.nanmax(v)))
    Dr = np.array(draws) if draws else np.zeros((0, len(cols)))
    mx = np.array(mx)
    out = {}
    for j, c in enumerate(cols):
        pj = float((Dr[:, j] >= real_abs[j]).mean()) if len(Dr) else None
        out[c] = {"realAuc": round(float(real[j]), 4), "realAbsAuc": round(float(real_abs[j]), 4), "p": (None if pj is None else round(pj, 3)),
                  "shiftP95": (round(float(np.quantile(Dr[:, j], 0.95)), 4) if len(Dr) else None),
                  "pFamily": (round(float((mx >= real_abs[j]).mean()), 3) if len(mx) else None)}
    return out, int(sum(1 for c in out if out[c]["p"] is not None and out[c]["p"] < 0.05)), len(Dr)


def areas_shuffled(L, W, minp, seed):
    """Levy areas + time-areas of the block-shuffled window at every bar (one shuffle per bar) for the shuffle null.
    NOTE: a fresh shuffle per bar makes this null feature white (lag-1 autocorrelation ~0.08) while the real 26-bar
    area has ~0.96, so its p-values are too small; it is kept for comparison only, area_shift_null is the headline."""
    series = list(L.columns)
    dX = L.diff()
    _, sd = trailing_stats(dX, minp)
    pairs, area, tarea, _, _ = sig_names(series)
    dXv, sdv = dX.values, sd.values
    n, m = len(L), len(series)
    out = np.full((n, len(area) + len(tarea)), np.nan)
    rng = np.random.default_rng(seed)
    for t in range(W, n):
        win = dXv[t - W + 1:t + 1]
        sd_t = sdv[t]
        if not (np.isfinite(win).all() and np.isfinite(sd_t).all() and (sd_t > 0).all()):
            continue
        Ad, _, _ = sig_window(block_shuffle(win, rng), sd_t, want_run=False)
        out[t, :len(area)] = [Ad[i, j] for i, j in pairs]
        out[t, len(area):] = [Ad[i, m] for i in range(m)]
    return pd.DataFrame(out, index=L.index, columns=area + tarea)


def iaaft_levels(L, rng, it=30):
    """IAAFT surrogate of every series' increments (same marginal and spectrum, cross-series order destroyed)."""
    Ls = L.copy()
    for c in L.columns:
        x = L[c]
        d = x.diff()
        m = d.notna().values
        if m.sum() < 10:
            continue
        ds = C.iaaft(d.values[m], rng, it=it)
        first = x[x.notna()].index[0]
        new = np.full(len(x), np.nan)
        new[np.where(m)[0]] = x.loc[first] + np.cumsum(ds)
        new[x.index.get_loc(first)] = x.loc[first]
        Ls[c] = new
    return Ls


def weekly_fall_base(btcd_daily, idx, start=START, pts=5.0, h=26):
    """2019+ base rate of a pts-point fall within h weeks for a daily BTC.D (pct) array on index idx (weekly resample)."""
    b = pd.Series(btcd_daily, index=idx).resample("W-SUN").last().ffill()
    fut = pd.concat([b.shift(-k) for k in range(1, h + 1)], axis=1)
    mn = fut.min(axis=1).where(fut.notna().all(axis=1))
    f = ((mn - b) <= -pts).astype(float).where(mn.notna())
    f = f[f.index >= pd.Timestamp(start)].dropna()
    return float(f.mean()) if len(f) else np.nan


def rw_panel(P, rng, freq, match_base=None):
    """P with the five crypto series replaced by matched random walks of their levels (macro series kept). With
    match_base, BTC.D's walk is rescaled (in logit space, about its start) so its 2019+ fall5_26w base rate is the
    closest on a fixed grid to match_base (a placebo must have the real target frequency, not the real range)."""
    Q = P.copy()
    for n in SERIES5:
        x = C.level(P, n).values.astype(float)
        m = np.isfinite(x)
        if n in LATE_START:
            m &= (P.index >= pd.Timestamp(LATE_START[n]))
        y = np.full(len(x), np.nan)
        w = C.matched_rw(x[m], rng, block_weeks=13, freq=freq)
        # affine range match in level space (a random walk stays a random walk): keeps 5-point falls possible
        w = (w - w.min()) / max(1e-9, w.max() - w.min()) * (x[m].max() - x[m].min()) + x[m].min()
        if n == "BTC.D" and match_base is not None and freq == "D":
            best = None
            for s in np.geomspace(0.25, 5.0, 40):
                ws = w[0] + s * (w - w[0])
                bb = weekly_fall_base(100.0 / (1.0 + np.exp(-ws)), P.index[m])
                if np.isfinite(bb) and (best is None or abs(bb - match_base) < best[0]):
                    best = (abs(bb - match_base), s, ws)
            if best is not None:
                w = best[2]
        y[m] = w
        if n in C.PCT:
            y = 100.0 / (1.0 + np.exp(-y))
        else:
            y = np.exp(y)
        Q[n] = y
    Q = Q.ffill()
    return Q


# ----------------------------------------------------------------------------------------- models
def lam_for(blocks, names):
    return np.concatenate([np.full(len(blocks[b]), 1.0 if len(blocks[b]) <= 10 else 10.0) for b in names])


def label_lag(target):
    if target.startswith("y"):
        return int(target[1:])
    return int(target.split("_")[-1][:-1])


def run_spec(spec, X, Y, target, freq, binary, blocks):
    """One model through C.walk_forward. spec = {blocks: [...], kind: glm|eramean|trainmean, resid: (blk, volblk) | None,
    restrict: blk | None}. Returns (pred, refits, fitted models, columns)."""
    kind = spec.get("kind", "glm")
    names = spec["blocks"]
    cols = sum((blocks[b] for b in names), [])
    lam = lam_for(blocks, names)
    Xm = X[cols].copy()
    if spec.get("restrict"):
        Xm = Xm.where(X[blocks[spec["restrict"]]].notna().all(axis=1))
    resid = spec.get("resid")
    ti = vi = None
    if resid:
        ti = np.array([cols.index(c) for c in blocks[resid[0]]])
        vi = np.array([cols.index(c) for c in blocks[resid[1]]])
    store = []
    nb = C.bars(104, freq)

    def fit(Xtr, ytr):
        if kind == "eramean":
            return ("const", float(ytr[-nb:].mean()))
        if kind == "trainmean":
            return ("const", float(ytr.mean()))
        Xa, beta = Xtr, None
        if resid:
            Av = np.c_[np.ones(len(Xtr)), Xtr[:, vi]]
            beta = np.linalg.lstsq(Av, Xtr[:, ti], rcond=None)[0]
            Xa = Xtr.copy()
            Xa[:, ti] = Xtr[:, ti] - Av @ beta
        mu, sd = C.zfit(Xa)
        Z = C.zapply(Xa, mu, sd)
        w = logistic_fit_lam(Z, ytr, lam) if binary else ridge_fit_lam(Z, ytr, lam)
        mdl = ("glm", mu, sd, w, beta)
        store.append(mdl)
        return mdl

    def predict(model, Xh, te):
        if model[0] == "const":
            return np.full(len(te), model[1])
        _, mu, sd, w, beta = model
        Xa = Xh[te]
        if beta is not None:
            Xa = Xa.copy()
            Xa[:, ti] = Xa[:, ti] - np.c_[np.ones(len(te)), Xa[:, vi]] @ beta
        Z = C.zapply(Xa, mu, sd)
        return C.logistic_predict(Z, w) if binary else C.ridge_predict(Z, w)
    pred, refits = C.walk_forward(Xm, Y[target], fit, predict, freq=freq, start=START, label_lag_weeks=label_lag(target))
    return pred, refits, store, cols


DEFAULT_REF = "M1r"   # the reference for every increment: fixed5 + vol fitted on the SAME training rows as the tested model


def ref_of(spec):
    return spec.get("ref", DEFAULT_REF)


def weekly_specs(has_sweep, has_t2):
    """Nested models. The 5-series blocks exist from 2018-01 (USDT.D / TOTAL3 from 2017-07 + the 26-bar window), so
    every geometric model trains on fewer rows than M0/M1 fitted from 2016-06 (which hold the two in-sample big
    waterfalls). The reference for an increment is therefore the SAME model restricted to the same rows: M1r for the
    M1-based families, M0r for the M0-based ones, M1t2 for the TOTAL2 variant. M0 and M1 (long history) are kept as
    external comparators; their 'increment' is the history premium over M0r / M1r."""
    S = {
        "M0": {"blocks": ["fixed5"], "ref": "M0r"},
        "M1": {"blocks": ["fixed5", "vol"], "ref": "M1r"},
        "M2": {"blocks": ["fixed5", "vol", "tda_raw"]},
        "M2r": {"blocks": ["fixed5", "vol", "tda_raw"], "resid": ("tda_raw", "vol")},
        "M2b": {"blocks": ["fixed5", "vol", "tda_btcd"]},
        "M3": {"blocks": ["fixed5", "vol", "tda_sf"]},
        "M4": {"blocks": ["fixed5", "vol", "area", "tarea"]},
        "M1A1": {"blocks": ["fixed5", "vol", "area1"]},
        "M0A1": {"blocks": ["fixed5", "area1"], "ref": "M0r"},
        "M0S": {"blocks": ["fixed5", "area", "tarea"], "ref": "M0r"},
        "M0T": {"blocks": ["fixed5", "tda_raw"], "ref": "M0r"},
        "M5": {"blocks": ["fixed5", "vol", "sig2"]},
        "M6": {"blocks": ["fixed5", "vol", "area", "tarea", "tim"]},
        "M4d": {"blocks": ["fixed5", "vol", "area", "tarea", "dec_area", "dec_tarea"]},
        "S_only": {"blocks": ["area", "tarea"]},
        "T_only": {"blocks": ["tda_raw"]},
        "V_only": {"blocks": ["vol"]},
        "M0r": {"blocks": ["fixed5"], "restrict": "area", "ref": "M0r"},
        "M1r": {"blocks": ["fixed5", "vol"], "restrict": "area", "ref": "M0r"},   # M1r - M0r = what the vol block adds on the same rows
        "clock": {"blocks": ["clock"]},
        "eramean": {"blocks": ["fixed5"], "kind": "eramean"},
        "trainmean": {"blocks": ["fixed5"], "kind": "trainmean"},
        "trainmean_r": {"blocks": ["fixed5"], "kind": "trainmean", "restrict": "area"},   # training-window base rate on the 5-series rows
    }
    if has_sweep:
        S["M2w52"] = {"blocks": ["fixed5", "vol", "tda_raw_w52"]}
        S["M4w52"] = {"blocks": ["fixed5", "vol", "area_w52", "tarea_w52"]}
    if has_t2:
        S["M4t2"] = {"blocks": ["fixed5", "vol", "area_t2", "tarea_t2"], "ref": "M1t2"}
        S["M1t2"] = {"blocks": ["fixed5", "vol"], "restrict": "area_t2"}
        S["trainmean_t2"] = {"blocks": ["fixed5"], "kind": "trainmean", "restrict": "area_t2"}
    return S


def base_model_for(spec):
    """Which training-mean comparator shares the model's training rows (for Brier versus the training base rate)."""
    r = spec.get("restrict")
    if r == "area_t2" or any(b.endswith("_t2") for b in spec["blocks"]):
        return "trainmean_t2"
    if r or any(b not in ("fixed5", "vol", "clock") for b in spec["blocks"]):
        return "trainmean_r"
    return "trainmean"


# ----------------------------------------------------------------------------------------- scoring
def n_episodes(y, mask):
    return len(C.episodes(np.where(mask.values, y.values, np.nan)))


def evaluate(pred, y, fresh, binary):
    out = {"byEra": C.metrics(pred, y, binary, is_prob=binary)}
    for era, fr, to in list(C.ERAS) + [("pooled", "2000-01-01", "2100-01-01")]:
        if era in out["byEra"]:
            m = (pred.index >= pd.Timestamp(fr)) & (pred.index < pd.Timestamp(to)) & pred.notna() & y.notna()
            out["byEra"][era]["nEp"] = n_episodes(y, pd.Series(m, index=pred.index)) if binary else None
    out["meanEra"] = mean_of_era(out["byEra"], "auc" if binary else "ic")
    if binary:
        fr = C.metrics(pred.where(fresh), y, binary)
        out["fresh"] = {e: r.get("auc") for e, r in fr.items()}
        out["freshN"] = {e: r.get("n") for e, r in fr.items()}
    return out


def increment(p, pref, y, binary, fresh=None):
    """Metric of p minus metric of pref on their common rows, by era and pooled (and pooled on fresh rows)."""
    m = p.notna() & pref.notna() & y.notna()
    key = "auc" if binary else "ic"
    a, b = C.metrics(p.where(m), y, binary), C.metrics(pref.where(m), y, binary)
    inc = {}
    for e in b:
        va, vb = a.get(e, {}).get(key), b.get(e, {}).get(key)
        inc[e] = None if va is None or vb is None else round(va - vb, 4)
    inc["meanEra"] = mean_of_era(inc)
    if binary and fresh is not None:
        mf = m & fresh
        va, vb = C.auc(p[mf].values, y[mf].values), C.auc(pref[mf].values, y[mf].values)
        inc["fresh"] = None if va is None or vb is None else round(va - vb, 4)
    return inc, int(m.sum())


def mean_of_era(d, key=None):
    """Mean over the three eras of d[era] (or d[era][key]); None unless all three eras are present."""
    vals = []
    for e in ("2019-2020", "2021-2022", "2023-2026"):
        v = d.get(e)
        if key is not None and isinstance(v, dict):
            v = v.get(key)
        if v is None:
            return None
        vals.append(float(v))
    return round(float(np.mean(vals)), 4)


def brier_vs_base(p, pbase, y):
    """Brier(model) - Brier(training-window base rate) by era and pooled on their common rows (negative = better)."""
    out = {}
    for era, fr, to in list(C.ERAS) + [("pooled", "2000-01-01", "2100-01-01")]:
        m = (p.index >= pd.Timestamp(fr)) & (p.index < pd.Timestamp(to)) & p.notna() & pbase.notna() & y.notna()
        if m.sum() < 20:
            continue
        out[era] = round(C.brier(p[m].values, y[m].values) - C.brier(pbase[m].values, y[m].values), 4)
    return out


def paired_episode_boot(p1, p2, y, n, rng, binary, runup_weeks=26):
    """Bootstrap over label episodes (each positive episode with its 26-week run-up, and the gaps between) of
    metric(p1) - metric(p2) on the common rows: the honest effective-sample-size band (about 12 episodes)."""
    if not binary:
        return {"n": 0, "note": "episodes are undefined for a continuous target"}
    a, b, yy = np.asarray(p1, float), np.asarray(p2, float), np.asarray(y, float)
    m = np.isfinite(a) & np.isfinite(b) & np.isfinite(yy)
    a, b, yy = a[m], b[m], yy[m]
    N = len(a)
    if N < 30:
        return {"n": 0}
    cuts = [0]
    for s, e in C.episodes(yy):
        cuts += [max(0, s - runup_weeks), e + 1]
    cuts = sorted(set(c for c in cuts if 0 <= c <= N)) + [N]
    bl = [np.arange(x, z) for x, z in zip(cuts[:-1], cuts[1:]) if z > x]
    f = C.auc if binary else C.spearman
    vals = []
    for _ in range(n):
        pick = rng.integers(0, len(bl), size=len(bl))
        ii = np.concatenate([bl[k] for k in pick])
        v1, v2 = f(a[ii], yy[ii]), f(b[ii], yy[ii])
        if v1 is not None and v2 is not None:
            vals.append(v1 - v2)
    v = np.array(vals)
    return {"n": len(v), "nBlocks": len(bl), "q05": round(float(np.quantile(v, 0.05)), 3), "q50": round(float(np.quantile(v, 0.5)), 3), "q95": round(float(np.quantile(v, 0.95)), 3)} if len(v) else {"n": 0}


def paired_boot(p1, p2, y, n, freq, rng, binary, block_weeks=26):
    """26-week circular block bootstrap of metric(p1) - metric(p2) on the common rows."""
    a, b, yy = np.asarray(p1, float), np.asarray(p2, float), np.asarray(y, float)
    m = np.isfinite(a) & np.isfinite(b) & np.isfinite(yy)
    a, b, yy = a[m], b[m], yy[m]
    N, bl = len(a), C.bars(block_weeks, freq)
    f = C.auc if binary else C.spearman
    vals = []
    if N < 30:
        return {"n": 0}
    for _ in range(n):
        starts = rng.integers(0, N, size=int(np.ceil(N / bl)))
        ii = np.concatenate([(np.arange(s, s + bl) % N) for s in starts])[:N]
        v1, v2 = f(a[ii], yy[ii]), f(b[ii], yy[ii])
        if v1 is not None and v2 is not None:
            vals.append(v1 - v2)
    v = np.array(vals)
    return {"n": len(v), "q05": round(float(np.quantile(v, 0.05)), 3), "q50": round(float(np.quantile(v, 0.5)), 3), "q95": round(float(np.quantile(v, 0.95)), 3)} if len(v) else {"n": 0}


def loo_summary(pred, y):
    lo = C.episode_loo(pred, y)
    big = [k for k in lo["perEpisode"] if "2020-08" <= k[:7] <= "2020-12"]
    y25 = [k for k in lo["perEpisode"] if "2025-02" <= k[:7] <= "2025-06"]
    return {"all": lo["all"], "nEpisodes": lo["nEpisodes"], "min": lo["min"], "minEpisode": lo["minEpisode"],
            "dropBigEpisode": (lo["perEpisode"][big[0]] if big else None), "drop2025": (lo["perEpisode"][y25[0]] if y25 else None)}


# ----------------------------------------------------------------------------------------- parallel workers
G = {}


def _walk_set(X, Y, specs, blocks, names, targets, freq):
    out = {}
    for tg, binary in targets:
        key = "auc" if binary else "ic"
        cache = {}

        def pred_of(nme):
            if nme not in cache:
                cache[nme] = run_spec(specs[nme], X, Y, tg, freq, binary, blocks)[0]
            return cache[nme]
        for nme in names:
            p = pred_of(nme)
            met = C.metrics(p, Y[tg], binary)
            inc, _ = increment(p, pred_of(ref_of(specs[nme])), Y[tg], binary)
            out[f"{nme}:{tg}"] = {"byEra": {e: r.get(key) for e, r in met.items()}, "inc": inc}
    return out


def rw_placebo_worker(k):
    """One matched-random-walk panel (base-rate matched on fall5_26w) through the weekly feature pipeline and the
    weekly walks of the named models: the placebo level of each model's ABSOLUTE pooled AUC."""
    g = G["RW"]
    rr = np.random.default_rng(7000 + k)
    Qd = rw_panel(g["PD"], rr, "D", match_base=g["base"])
    Qw = C.panel(Qd, "W")
    Xq, _ = C.features(Qw, "W")
    Yq = C.targets(Qw, "W")
    kq = Xq.index >= pd.Timestamp(DATA_CUT)
    Xq, Yq, Qw = Xq[kq], Yq[kq], Qw[kq]
    Xq["btcd_volvol"] = Xq["btcd_vol13w"].diff().rolling(13).std()
    Xq = pd.concat([Xq, extra_features(level_panel(Qw, SERIES5), W_W, MINP["W"], with_tda=False, with_decoy=False, with_sf=False, with_btcd=False)[0]], axis=1)
    post = Yq.index >= pd.Timestamp(START)
    row = {"seed": 7000 + k, "base": round(float(Yq.loc[post, "fall5_26w"].mean()), 3), "nEp": len(C.episodes(Yq.loc[post, "fall5_26w"].values))}
    pq = {}
    for n in g["names"]:
        pq[n] = run_spec(g["specs"][n], Xq, Yq, "fall5_26w", "W", True, g["blocks"])[0]
        row[n] = C.metrics(pq[n], Yq["fall5_26w"], True).get("pooled", {}).get("auc")
    for n in ("M4", "M1A1", "M2"):
        if n in pq and "M1r" in pq:
            row[f"{n}-M1r"] = increment(pq[n], pq["M1r"], Yq["fall5_26w"], True)[0].get("pooled")
    if "M0A1" in pq and "M0r" in pq:
        row["M0A1-M0r"] = increment(pq["M0A1"], pq["M0r"], Yq["fall5_26w"], True)[0].get("pooled")
    return row


def null_worker(task):
    g = G[task[0]]
    kind, k = task[1], task[2]
    Y = g["Y"]
    if kind == "shift":
        Ys = C.shift_targets(Y, k)
    else:  # within-era shift: roll the targets inside one era's rows only
        name, fr, to = task[3]
        m = (Y.index >= pd.Timestamp(fr)) & (Y.index < pd.Timestamp(to))
        pos = np.where(m)[0]
        Ys = Y.copy()
        for c in Y.columns:
            v = Y[c].values.copy()
            v[pos] = np.roll(v[pos], k)
            Ys[c] = v
    return _walk_set(g["X"], Ys, g["specs"], g["blocks"], g["names"], g["targets"], g["freq"])


def surrogate_worker(seed):
    g = G["W"]
    rng = np.random.default_rng(100000 + seed)
    Ls = iaaft_levels(g["L"], rng)
    Xe, _ = extra_features(Ls, W_W, MINP["W"], with_decoy=False, with_sf=False, with_btcd=False)
    X = g["X"].copy()
    for c in Xe.columns:
        if c in X:
            X[c] = Xe[c].values
    names = ["M1", "M2", "M4", "M5"]
    return _walk_set(X, g["Y"], g["specs"], g["blocks"], names, g["targets"], "W")


# ----------------------------------------------------------------------------------------- transfer
def transfer_predict(Xw, cols, wk_models, wk_refits, dy_models, dy_refits, freq="W"):
    """Daily-fitted coefficients applied to weekly rows at the same refit date cuts. 'coef': daily standardised
    coefficients on weekly z-scores (weekly training mu/sd at that refit); 'raw': the daily model applied unchanged."""
    dmap = {r["t"]: m for r, m in zip(dy_refits, dy_models)}
    wmap = {r["t"]: m for r, m in zip(wk_refits, wk_models)}
    idx = Xw.index
    Xv = Xw[cols].values.astype(float)
    pc, pr = pd.Series(np.nan, index=idx), pd.Series(np.nan, index=idx)
    t = int(np.searchsorted(idx, pd.Timestamp(START)))
    step = C.bars(13, freq)
    while t < len(idx):
        te_end = min(t + step, len(idx))
        date = str(idx[t].date())
        te = np.arange(t, te_end)
        ok = te[np.isfinite(Xv[te]).all(1)]
        if date in dmap and len(ok):
            _, mud, sdd, wd, _ = dmap[date]
            pr.iloc[ok] = C.logistic_predict(C.zapply(Xv[ok], mud, sdd), wd)
            if date in wmap:
                _, muw, sdw, ww, _ = wmap[date]
                pc.iloc[ok] = C.logistic_predict(C.zapply(Xv[ok], muw, sdw), wd)
        t = te_end
    return pc, pr


def coef_table(models, cols, names):
    """Mean standardised coefficient and share of refits with a positive sign, per named feature."""
    out = {}
    if not models:
        return out
    Wm = np.array([m[3][1:] for m in models])
    for c in names:
        j = cols.index(c)
        out[c] = {"mean": round(float(Wm[:, j].mean()), 4), "posShare": round(float((Wm[:, j] > 0).mean()), 3)}
    return out


# ----------------------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--nulls", type=int, default=200)
    ap.add_argument("--fast", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    timing = {}
    _tk = [time.time()]

    def tick(name):
        timing[name] = round(time.time() - _tk[0], 1)
        _tk[0] = time.time()
    n_sur, n_shuf, n_boot, n_rw, sweep, n_rw_placebo = 50, 100, 1000, 5, True, 10
    if a.fast:
        a.nulls, n_sur, n_shuf, n_boot, n_rw, sweep, n_rw_placebo = 20, 10, 30, 200, 2, False, 6
    n_daily_nulls = max(8, a.nulls // 5) if a.fast else max(40, a.nulls // 5)   # p printed as 'na' below 20 draws
    n_area_shift = 500   # circular shifts of the real area series (cheap: no fit)
    rng = np.random.default_rng(85)
    utc = pd.Timestamp.now(tz="UTC")
    try:
        from zoneinfo import ZoneInfo
        et = utc.tz_convert(ZoneInfo("America/New_York"))
    except Exception:
        et = utc - pd.Timedelta(hours=5)
    res = {"module": "tda_sig", "runUtc": str(utc)[:19], "runEt": str(et)[:19], "fast": a.fast, "notes": [], "checks": {}}
    notes = res["notes"]
    D = C.load_daily(a.data)
    last_daily = D.index[-1]

    # ------------------------------------------------------------------ weekly panel, harness features, targets
    P = C.panel(D, "W")
    X, hblocks = C.features(P, "W")
    Y = C.extra_targets(P, C.targets(P, "W"), "W")
    keep = X.index >= pd.Timestamp(DATA_CUT)
    X, Y, P = X[keep], Y[keep], P[keep]
    fresh = C.fresh_mask(P, "W")
    X["btcd_volvol"] = X["btcd_vol13w"].diff().rolling(13).std()
    last_complete = P.index[P.index <= last_daily][-1]
    provisional = [str(d.date()) for d in P.index[P.index > last_daily]]
    L5 = level_panel(P, SERIES5)
    L4 = level_panel(P, SERIES4)
    t1 = time.time()
    Xe, eblocks = extra_features(L5, W_W, MINP["W"])
    blocks = {"fixed5": SIGNALS, "vol": VOL_COLS, "clock": ["days_since_halving"]}
    blocks.update(eblocks)
    blocks["sig2"] = eblocks["area"] + eblocks["tarea"] + eblocks["sym"]
    blocks["area1"] = ["area_USDT.D>BTC.D"]   # the one pre-registered candidate: stablecoin share leading dominance
    if sweep:
        Xs, sblocks = extra_features(L5, W_SWEEP, MINP["W"], tag="_w52", with_decoy=False, with_sf=False, with_btcd=False)
        Xe = pd.concat([Xe, Xs[sblocks["area_w52"] + sblocks["tarea_w52"] + sblocks["tda_raw_w52"]]], axis=1)
        blocks.update({k: sblocks[k] for k in ("area_w52", "tarea_w52", "tda_raw_w52")})
    Xt2, t2blocks = extra_features(L4, W_W, MINP["W"], tag="_t2", with_tda=False, with_decoy=False)
    Xe = pd.concat([Xe, Xt2[t2blocks["area_t2"] + t2blocks["tarea_t2"]]], axis=1)
    blocks.update({k: t2blocks[k] for k in ("area_t2", "tarea_t2")})
    X = pd.concat([X, Xe], axis=1)
    feat_sec = time.time() - t1
    tick("weeklyFeatures")
    specs = weekly_specs(sweep, True)
    targets = [("fall5_26w", True), ("fall10_26w", True), ("y13", False)]
    usdt_btcd = "area_USDT.D>BTC.D"
    first_feat = X[blocks["area"]].dropna().index[0]
    first_tda = X[blocks["tda_raw"]].dropna().index[0]

    # ------------------------------------------------------------------ checks: truncation, fallback vs ripser
    def series_fn(end):
        Xp, _ = extra_features(L5.iloc[:end + 1], W_W, MINP["W"], with_decoy=False, with_sf=False, with_btcd=False, last_only=True)
        return (Xp[usdt_btcd].values + Xp["tda_h1tot"].values + Xp["tim_USDT.D>BTC.D"].values)
    full_vec = X[usdt_btcd].values + X["tda_h1tot"].values + X["tim_USDT.D>BTC.D"].values
    worst, tested = 0.0, 0
    for t in rng.integers(len(X) // 2, len(X) - 1, size=20):
        part = series_fn(int(t))
        if np.isfinite(full_vec[t]) and np.isfinite(part[t]):
            worst = max(worst, float(abs(part[t] - full_vec[t])))
            tested += 1
    res["checks"]["truncation"] = {"ok": bool(worst <= 1e-9), "maxAbsDiff": worst, "tested": tested, "features": [usdt_btcd, "tda_h1tot", "tim_USDT.D>BTC.D"]}
    fb = {"ripser": HAVE_RIPSER}
    if HAVE_RIPSER:
        dXv = L5.diff().values
        _, sdv = trailing_stats(L5.diff(), MINP["W"])
        diffs = []
        for t in rng.integers(len(X) // 2, len(X) - 1, size=3):
            win = dXv[t - W_W + 1:t + 1]
            if not np.isfinite(win).all():
                continue
            pts = embed((win - win.mean(0)) / win.std(0, ddof=1))
            r1, r2 = rips(pts), rips_fallback(pts)
            for k in (0, 1):
                a1, a2 = np.sort(r1[k], axis=0), np.sort(r2[k], axis=0)
                diffs.append(float(np.abs(a1 - a2).max()) if a1.shape == a2.shape and len(a1) else (0.0 if a1.shape == a2.shape else 1.0))
        fb["maxDiffVsFallback"] = max(diffs) if diffs else None
        fb["ok"] = bool(max(diffs) < 1e-4) if diffs else None
    res["checks"]["fallback"] = fb
    tick("checks")

    # ------------------------------------------------------------------ weekly walks
    preds, refits, models, colsets = {}, {}, {}, {}
    for nme, spec in specs.items():
        for tg, binary in targets:
            p, r, mdl, cols = run_spec(spec, X, Y, tg, "W", binary, blocks)
            preds[(nme, tg)] = p
            refits[(nme, tg)] = r
            models[(nme, tg)] = mdl
            colsets[nme] = cols
    first_fc = {nme: (str(preds[(nme, "fall5_26w")].dropna().index[0].date()) if preds[(nme, "fall5_26w")].notna().any() else None) for nme in specs}
    oos, incs, bands, loos, bvb = {}, {}, {}, {}, {}
    BAND_MODELS = ("M2", "M2r", "M3", "M4", "M5", "M6", "M4d", "M2b", "M2w52", "M4w52", "M4t2", "M0", "M1", "M1r", "V_only", "M1A1", "M0A1", "M0S", "M0T", "M2h")

    def score_one(nme, tg, p):
        binary = tg != "y13"
        key = f"{nme}:{tg}"
        oos[key] = evaluate(p, Y[tg], fresh, binary)
        oos[key]["firstForecast"] = (str(p.dropna().index[0].date()) if p.notna().any() else None)
        refname = ref_of(specs[nme])
        ref = preds[(refname, tg)]
        inc, ncommon = increment(p, ref, Y[tg], binary, fresh)
        incs[key] = {"inc": inc, "nCommon": ncommon, "ref": refname}
        if refname != "M1" and nme not in ("M0", "M1", "M0r", "M1r"):   # the long-history reference kept for the record
            incs[key]["incVsLongRef"] = {"ref": ("M0" if refname.startswith("M0") else "M1"), "inc": increment(p, preds[(("M0" if refname.startswith("M0") else "M1"), tg)], Y[tg], binary, fresh)[0]}
        if nme in BAND_MODELS:
            bands[key] = {"block": paired_boot(p, ref, Y[tg], n_boot, "W", rng, binary), "episode": paired_episode_boot(p, ref, Y[tg], n_boot, rng, binary)}
        if binary:
            loos[key] = loo_summary(p, Y[tg])
            bvb[key] = brier_vs_base(p, preds[(base_model_for(specs[nme]), tg)], Y[tg])
    for (nme, tg), p in list(preds.items()):
        score_one(nme, tg, p)

    tick("weeklyWalks")
    # ------------------------------------------------------------------ vol proxies, signs, event ranks
    pre = X.index < pd.Timestamp(START)
    volz = X.loc[pre, VOL_COLS[:5]]
    volz = ((volz - volz.mean()) / volz.std()).mean(axis=1)
    corr_vol = {}
    for b in ("tda_raw", "tda_sf", "tda_btcd", "area", "tarea", "tim", "sym"):
        for c in blocks[b]:
            s = X.loc[pre, c]
            corr_vol[c] = {"meanVol": round(float(s.corr(volz)), 3), "btcdVol": round(float(s.corr(X.loc[pre, "btcd_vol13w"])), 3)}
    proxies = [c for c, v in corr_vol.items() if max(abs(v["meanVol"]), abs(v["btcdVol"])) > VOL_PROXY_CORR]
    tda_keep = [c for c in blocks["tda_raw"] if c not in proxies]
    if tda_keep and len(tda_keep) < len(blocks["tda_raw"]):
        blocks["tda_keep"] = tda_keep
        specs["M2h"] = {"blocks": ["fixed5", "vol", "tda_keep"]}
        for tg, binary in targets:
            p, r, mdl, cols = run_spec(specs["M2h"], X, Y, tg, "W", binary, blocks)
            preds[("M2h", tg)], refits[("M2h", tg)], models[("M2h", tg)], colsets["M2h"] = p, r, mdl, cols
            score_one("M2h", tg, p)
    signs = {tg: coef_table(models[("M4", tg)], colsets["M4"], blocks["area"] + blocks["tarea"]) for tg, _ in targets}
    signs["M6_tim:y13"] = coef_table(models[("M6", "y13")], colsets["M6"], blocks["tim"])
    signs["M4d:fall5_26w"] = coef_table(models[("M4d", "fall5_26w")], colsets["M4d"], blocks["area"] + blocks["dec_area"])
    ev = C.events(P["BTC.D"], 5.0, freq="W")
    ev_dates = [e["peak"] for e in ev]
    big_rank = {}
    for c in blocks["area"] + blocks["tarea"] + blocks["tda_raw"] + blocks["area_t2"]:
        vals = X.loc[ev_dates, c]
        ok = vals.notna()
        ranks = (-vals[ok]).rank().astype(int)
        big_rank[c] = {"nEventsWithValue": int(ok.sum()), "nEvents": len(ev),
                       "bigRank": {str(b.date()): (int(ranks[d]) if (d in ranks.index) else None) for b in BIG for d in [min(ev_dates, key=lambda x: abs((x - b).days))] if abs((d - b).days) <= 28}}
    res["events5w"] = [{"peak": str(e["peak"].date()), "trough": str(e["trough"].date()), "from": round(e["from"], 1), "to": round(e["to"], 1), "days": e["days"]} for e in ev]

    tick("weeklyExtras")
    # ------------------------------------------------------------------ weekly nulls (shifted targets, within era)
    null_names = ["M0", "M0r", "M1", "M1r", "M2", "M2r", "M2b", "M3", "M4", "M5", "M6", "M4d", "S_only", "T_only", "V_only", "clock", "M1A1", "M0A1", "M0S", "M0T"] + (["M2h"] if "M2h" in specs else [])
    G["W"] = {"X": X, "Y": Y, "specs": specs, "blocks": blocks, "names": null_names, "targets": targets, "freq": "W", "L": L5}
    lo = C.bars(26, "W")
    tasks = [("W", "shift", int(rng.integers(lo, len(Y) - lo))) for _ in range(a.nulls)]
    era_n = max(5, a.nulls // 4)
    for era in (C.ERAS[0], C.ERAS[2]):
        name, fr, to = era
        npos = int(((Y.index >= pd.Timestamp(fr)) & (Y.index < pd.Timestamp(to))).sum())
        tasks += [("W", "era", int(rng.integers(lo, npos - lo)), era) for _ in range(era_n)]
    ctx = get_context("fork")
    with ctx.Pool(4) as pool:
        null_out = pool.map(null_worker, tasks, chunksize=2)
        sur_out = pool.map(surrogate_worker, list(range(n_sur)), chunksize=1)
    tick("weeklyNullsAndSurrogates")
    shift_out = [o for t, o in zip(tasks, null_out) if t[1] == "shift"]
    era_out = {era[0]: [o for t, o in zip(tasks, null_out) if t[1] == "era" and t[3][0] == era[0]] for era in (C.ERAS[0], C.ERAS[2])}
    null = {}
    for nme in null_names:
        for tg, binary in targets:
            key = f"{nme}:{tg}"
            head = "auc" if binary else "ic"
            real = oos[key]["byEra"].get("pooled", {}).get(head)
            real_inc = incs[key]["inc"].get("pooled")
            nv = [o[key]["byEra"].get("pooled") for o in shift_out if o[key]["byEra"].get("pooled") is not None]
            ni = [o[key]["inc"].get("pooled") for o in shift_out if o[key]["inc"].get("pooled") is not None]
            null[key] = {"pooled": C.null_summary(real, nv), "increment": C.null_summary(real_inc, ni)}
            if tg == "fall5_26w":
                null[key]["withinEra"] = {}
                for ename, outs in era_out.items():
                    r_e = incs[key]["inc"].get(ename)
                    n_e = [o[key]["inc"].get(ename) for o in outs if o[key]["inc"].get(ename) is not None]
                    null[key]["withinEra"][ename] = C.null_summary(r_e, n_e)
    surrogates = {}
    for nme in ("M2", "M4", "M5"):
        for tg, binary in targets:
            key = f"{nme}:{tg}"
            real_inc = incs[key]["inc"].get("pooled")
            vals = [o[key]["inc"].get("pooled") for o in sur_out if o[key]["inc"].get("pooled") is not None]
            surrogates[key] = C.null_summary(real_inc, vals)

    # ------------------------------------------------------------------ block-shuffled single-area null
    post = (X.index >= pd.Timestamp(START)) & Y["fall5_26w"].notna()
    yv = Y.loc[post, "fall5_26w"].values
    real_abs = {c: abs(C.auc(X.loc[post, c].values, yv) - 0.5) for c in blocks["area"] + blocks["tarea"]}
    shuf_abs = {c: [] for c in real_abs}
    for s in range(n_shuf):
        Sh = areas_shuffled(L5, W_W, MINP["W"], seed=777 + s)
        for c in real_abs:
            v = C.auc(Sh.loc[post, c].values, yv)
            if v is not None:
                shuf_abs[c].append(abs(v - 0.5))
    shuffle_null = {c: {"realAbsAuc": round(real_abs[c], 4), "realAuc": round(C.auc(X.loc[post, c].values, yv), 4), "p": round(float((np.array(shuf_abs[c]) >= real_abs[c]).mean()), 3),
                        "shufP95": round(float(np.quantile(shuf_abs[c], 0.95)), 4)} for c in real_abs}
    n_beat = sum(1 for c in shuffle_null if shuffle_null[c]["p"] < 0.05)
    # headline null: circular shift of the REAL area series (keeps its autocorrelation), family-wise p over the 15 areas
    shift_null_area, n_beat_shift, n_shift_done = area_shift_null(X, blocks["area"] + blocks["tarea"], post, Y["fall5_26w"], n_area_shift, rng)
    ac1 = lambda s: (round(float(pd.Series(np.asarray(s, float)).autocorr(1)), 3) if np.isfinite(np.asarray(s, float)).sum() > 30 else None)  # noqa: E731
    Sh0 = areas_shuffled(L5, W_W, MINP["W"], seed=777)
    autocorr = {"realArea": ac1(X.loc[post, usdt_btcd]), "perBarShuffledArea": ac1(Sh0.loc[post, usdt_btcd]), "decoyArea": ac1(X.loc[post, "dec_" + usdt_btcd]),
                "target": ac1(Y.loc[post, "fall5_26w"]), "shiftNullArea": "same as realArea by construction (circular shift of the real series)"}
    # the pre-registered area as a single feature: by era, on fresh rows, its overlap with the five signals, and after
    # residualising on them (in-sample OLS, descriptive only: the standalone number is in-sample by construction)
    s_area = X[usdt_btcd]
    area_alone = {}
    for era, fr, to in list(C.ERAS) + [("pooled", "2000-01-01", "2100-01-01")]:
        m = post & s_area.notna() & (X.index >= pd.Timestamp(fr)) & (X.index < pd.Timestamp(to))
        mf = m & fresh
        a_era = None if m.sum() < 20 else C.auc(s_area[m].values, Y.loc[m, "fall5_26w"].values)
        area_alone[era] = {"auc": (None if a_era is None else round(a_era, 3)),
                           "freshAuc": (None if mf.sum() < 20 or C.auc(s_area[mf].values, Y.loc[mf, "fall5_26w"].values) is None else round(C.auc(s_area[mf].values, Y.loc[mf, "fall5_26w"].values), 3)),
                           "n": int(m.sum()), "nEp": n_episodes(Y["fall5_26w"], pd.Series(m, index=X.index))}
    m = post & s_area.notna()
    overlap = {f5: round(C.spearman(s_area[m].values, X.loc[m, f5].values), 3) for f5 in SIGNALS}
    Af = np.c_[np.ones(int(m.sum())), X.loc[m, SIGNALS].values]
    resid_a = s_area[m].values - Af @ np.linalg.lstsq(Af, s_area[m].values, rcond=None)[0]
    area_alone["residualisedOnFixed5Auc"] = round(C.auc(resid_a, Y.loc[m, "fall5_26w"].values), 3)
    area_alone["overlapSpearman"] = overlap

    tick("shuffleNull")
    # ------------------------------------------------------------------ daily replica
    PD = C.panel(D, "D")
    XD, _ = C.features(PD, "D")
    YD = C.targets(PD, "D", falls=(3.0, 5.0), horizons=(4, 13))
    keepd = XD.index >= pd.Timestamp(DATA_CUT)
    XD, YD, PD = XD[keepd], YD[keepd], PD[keepd]
    freshd = C.fresh_mask(PD, "D")
    XD["btcd_volvol"] = XD["btcd_vol13w"].diff().rolling(13).std()
    LD = level_panel(PD, SERIES5)
    t1 = time.time()
    XeD, dblocks = extra_features(LD, W_D, MINP["D"], with_tda=False, with_decoy=False)
    XD = pd.concat([XD, XeD], axis=1)
    blocksD = {"fixed5": SIGNALS, "vol": VOL_COLS, "clock": ["days_since_halving"]}
    blocksD.update(dblocks)
    blocksD["sig2"] = dblocks["area"] + dblocks["tarea"] + dblocks["sym"]
    blocksD["area1"] = ["area_USDT.D>BTC.D"]
    feat_sec_d = time.time() - t1
    specsD = {k: v for k, v in weekly_specs(False, False).items() if k in ("M0", "M0r", "M1", "M1r", "M4", "M5", "M6", "S_only", "V_only", "M0A1", "trainmean", "trainmean_r")}
    targetsD = [("fall3_4w", True), ("fall3_13w", True), ("fall5_13w", True), ("y13", False)]
    predsD, refitsD, modelsD, colsD = {}, {}, {}, {}
    for nme, spec in specsD.items():
        for tg, binary in targetsD:
            p, r, mdl, cols = run_spec(spec, XD, YD, tg, "D", binary, blocksD)
            predsD[(nme, tg)], refitsD[(nme, tg)], modelsD[(nme, tg)], colsD[nme] = p, r, mdl, cols
    daily = {"base2019on": {tg: round(float(YD.loc[YD.index >= pd.Timestamp(START), tg].mean()), 3) for tg, b in targetsD if b},
             "events5d": len(C.events(PD["BTC.D"], 5.0, freq="D")), "oos": {}, "increments": {}, "signs": {}}
    for (nme, tg), p in predsD.items():
        binary = tg != "y13"
        e = evaluate(p, YD[tg], freshd, binary)
        e["firstForecast"] = (str(p.dropna().index[0].date()) if p.notna().any() else None)
        daily["oos"][f"{nme}:{tg}"] = e
        inc, nc = increment(p, predsD[(ref_of(specsD[nme]), tg)], YD[tg], binary, freshd)
        daily["increments"][f"{nme}:{tg}"] = {"inc": inc, "nCommon": nc, "ref": ref_of(specsD[nme])}
        if nme in ("M4", "M5", "M6", "M1A1") and ("M0r", tg) in predsD:
            daily["increments"][f"{nme}:{tg}"]["incVsM0r"] = increment(p, predsD[("M0r", tg)], YD[tg], binary, freshd)[0]
        if binary:
            daily["oos"][f"{nme}:{tg}"]["brierVsBase"] = brier_vs_base(p, predsD[(base_model_for(specsD[nme]), tg)], YD[tg])
    daily["signs"] = {tg: coef_table(modelsD[("M4", tg)], colsD["M4"], dblocks["area"] + dblocks["tarea"]) for tg, _ in targetsD}
    tick("dailyWalks")
    G["D"] = {"X": XD, "Y": YD, "specs": specsD, "blocks": blocksD, "names": ["M1", "M1r", "M4", "M5", "M0A1", "M0", "M0r"], "targets": [("fall3_13w", True), ("fall5_13w", True), ("y13", False)], "freq": "D"}
    lod = C.bars(26, "D")
    tasksD = [("D", "shift", int(rng.integers(lod, len(YD) - lod))) for _ in range(n_daily_nulls)]
    with ctx.Pool(4) as pool:
        nullD_out = pool.map(null_worker, tasksD, chunksize=1)
    daily["null"] = {"nDraws": len(nullD_out), "note": "p is reported as 'na' in the summary below 20 draws"}
    for nme in ("M1", "M1r", "M4", "M5", "M0A1", "M0", "M0r"):
        for tg, binary in G["D"]["targets"]:
            key = f"{nme}:{tg}"
            head = "auc" if binary else "ic"
            real = daily["oos"][key]["byEra"].get("pooled", {}).get(head)
            real_inc = daily["increments"][key]["inc"].get("pooled")
            daily["null"][key] = {"pooled": C.null_summary(real, [o[key]["byEra"].get("pooled") for o in nullD_out if o[key]["byEra"].get("pooled") is not None]),
                                  "increment": C.null_summary(real_inc, [o[key]["inc"].get("pooled") for o in nullD_out if o[key]["inc"].get("pooled") is not None])}

    tick("dailyNulls")
    # ------------------------------------------------------------------ transfer daily -> weekly (and RW control)
    def transfer_block(Xw, Yw, freshw, wk_models, wk_refits, dy_models, dy_refits, cols, pw):
        pc, pr = transfer_predict(Xw, cols, wk_models, wk_refits, dy_models, dy_refits)
        out = {}
        for tgw in ("fall5_26w", "fall5_13w"):
            if tgw not in Yw:
                continue
            m = pc.notna() & pw.notna() & Yw[tgw].notna()
            out[tgw] = {"weeklyFit": C.metrics(pw.where(m), Yw[tgw], True), "coefTransfer": C.metrics(pc.where(m), Yw[tgw], True),
                        "rawTransfer": C.metrics(pr.where(m), Yw[tgw], True), "rawTransferAllRows": C.metrics(pr, Yw[tgw], True),
                        "freshCoefTransfer": C.metrics(pc.where(m & freshw), Yw[tgw], True).get("pooled", {}).get("auc"),
                        "freshWeeklyFit": C.metrics(pw.where(m & freshw), Yw[tgw], True).get("pooled", {}).get("auc")}
        return out, pc, pr
    tr, pc, pr = transfer_block(X, Y, fresh, models[("M4", "fall5_26w")], refits[("M4", "fall5_26w")], modelsD[("M4", "fall5_13w")], refitsD[("M4", "fall5_13w")], colsets["M4"], preds[("M4", "fall5_26w")])
    sign_cmp = {}
    for tgw, tgd in (("fall5_26w", "fall5_13w"), ("y13", "y13")):
        sw, sdd = signs[tgw], daily["signs"][tgd]
        agree = {c: bool(np.sign(sw[c]["mean"]) == np.sign(sdd[c]["mean"])) for c in sw if c in sdd}
        top = sorted(sw, key=lambda c: -abs(sw[c]["mean"]))[:5]
        sign_cmp[f"W:{tgw}|D:{tgd}"] = {"agreeShare": round(float(np.mean(list(agree.values()))), 3), "agreeTop5": {c: agree[c] for c in top},
                                         "usdtLeadsBtcd": {"weekly": sw[usdt_btcd], "daily": sdd[usdt_btcd]}}
    transfer = {"scores": tr, "signs": sign_cmp, "rwControl": []}
    for k in range(n_rw):
        rr = np.random.default_rng(5000 + k)
        Qd = rw_panel(PD, rr, "D")
        Qw = C.panel(Qd, "W")
        Xq, _ = C.features(Qw, "W")
        Yq = C.targets(Qw, "W")
        Xq["btcd_volvol"] = Xq["btcd_vol13w"].diff().rolling(13).std()
        Xq = pd.concat([Xq, extra_features(level_panel(Qw, SERIES5), W_W, MINP["W"], with_tda=False, with_decoy=False)[0]], axis=1)
        XqD, _ = C.features(Qd, "D")
        YqD = C.targets(Qd, "D", falls=(3.0, 5.0), horizons=(4, 13))
        XqD["btcd_volvol"] = XqD["btcd_vol13w"].diff().rolling(13).std()
        XqD = pd.concat([XqD, extra_features(level_panel(Qd, SERIES5), W_D, MINP["D"], with_tda=False, with_decoy=False)[0]], axis=1)
        pw_q, rw_q, mw_q, cq = run_spec(specs["M4"], Xq, Yq, "fall5_26w", "W", True, blocks)
        pd_q, rd_q, md_q, _ = run_spec(specsD["M4"], XqD, YqD, "fall5_13w", "D", True, blocksD)
        trq, _, _ = transfer_block(Xq, Yq, C.fresh_mask(Qw, "W"), mw_q, rw_q, md_q, rd_q, cq, pw_q)
        g = trq.get("fall5_26w", {})
        transfer["rwControl"].append({"weeklyFit": g.get("weeklyFit", {}).get("pooled", {}).get("auc"), "coefTransfer": g.get("coefTransfer", {}).get("pooled", {}).get("auc"),
                                      "rawTransfer": g.get("rawTransfer", {}).get("pooled", {}).get("auc"), "base": g.get("weeklyFit", {}).get("pooled", {}).get("base")})

    # matched-random-walk PLACEBO level of every model's absolute pooled AUC (base-rate matched panels, weekly only)
    real_base = float(Y.loc[Y.index >= pd.Timestamp(START), "fall5_26w"].mean())
    G["RW"] = {"PD": PD, "base": real_base, "specs": specs, "blocks": blocks, "names": ["M0", "M0r", "M1", "M1r", "M4", "M1A1", "M0A1", "V_only", "S_only", "clock"]}
    with ctx.Pool(4) as pool:
        rw_rows = pool.map(rw_placebo_worker, list(range(n_rw_placebo)), chunksize=1)
    rw_df = pd.DataFrame(rw_rows)
    rw_placebo = {"nPanels": len(rw_rows), "realBase": round(real_base, 3), "panels": rw_rows,
                  "median": {c: (round(float(rw_df[c].median()), 3) if rw_df[c].notna().any() else None) for c in rw_df.columns if c != "seed"},
                  "max": {c: (round(float(rw_df[c].max()), 3) if rw_df[c].notna().any() else None) for c in rw_df.columns if c != "seed"},
                  "p95": {c: (round(float(rw_df[c].quantile(0.95)), 3) if rw_df[c].notna().any() else None) for c in rw_df.columns if c != "seed"}}
    rw_placebo["excess"] = {n: (round(oos[f"{n}:fall5_26w"]["byEra"]["pooled"]["auc"] - rw_placebo["median"][n], 3) if rw_placebo["median"].get(n) is not None and oos[f"{n}:fall5_26w"]["byEra"].get("pooled", {}).get("auc") is not None else None) for n in G["RW"]["names"]}
    tick("transferAndRw")
    # ------------------------------------------------------------------ today
    def today_reading(nme, tg, row_date):
        mdl = models[(nme, tg)]
        if not mdl:
            return None
        _, mu, sd, w, beta = mdl[-1]
        cols = colsets[nme]
        x = X.loc[row_date, cols].values.astype(float)[None, :]
        if beta is not None:
            spec = specs[nme]
            ti = np.array([cols.index(c) for c in blocks[spec["resid"][0]]])
            vi = np.array([cols.index(c) for c in blocks[spec["resid"][1]]])
            x = x.copy()
            x[:, ti] = x[:, ti] - np.c_[np.ones(1), x[:, vi]] @ beta
        z = C.zapply(x, mu, sd)[0]
        contrib = z * w[1:]
        by_block = {}
        for b in specs[nme]["blocks"]:
            ii = [cols.index(c) for c in blocks[b]]
            by_block[b] = round(float(contrib[ii].sum()), 4)
        p = float(C.logistic_predict(z[None, :], w)[0]) if tg != "y13" else float(C.ridge_predict(z[None, :], w)[0])
        drops, perturb = {}, {}
        for j, c in enumerate(cols):
            z2 = z.copy()
            z2[j] = 0.0
            drops[c] = round(float(C.logistic_predict(z2[None, :], w)[0]), 4) if tg != "y13" else round(float(C.ridge_predict(z2[None, :], w)[0]), 4)
            lo_hi = []
            for dlt in (-1.0, 1.0):
                z2 = z.copy()
                z2[j] = np.clip(z2[j] + dlt, -3, 3)
                lo_hi.append(float(C.logistic_predict(z2[None, :], w)[0]) if tg != "y13" else float(C.ridge_predict(z2[None, :], w)[0]))
            perturb[c] = [round(min(lo_hi), 4), round(max(lo_hi), 4)]
        allv = list(drops.values()) + [v for lh in perturb.values() for v in lh]
        return {"value": round(p, 4), "intercept": round(float(w[0]), 4), "blockContrib": by_block, "featureContrib": {c: round(float(contrib[j]), 4) for j, c in enumerate(cols)},
                "spreadDropsPerturb": [round(min(allv), 4), round(max(allv), 4)], "fittedAt": refits[(nme, tg)][-1]["t"]}
    today = {"asOf": str(last_complete.date()), "provisionalBars": provisional, "btcd": round(float(P.loc[last_complete, "BTC.D"]), 2), "fresh": bool(fresh.loc[last_complete]),
             "readings": {}, "provisionalReadings": {}, "areasNow": {c: round(float(X.loc[last_complete, c]), 4) for c in blocks["area"] + blocks["tarea"]},
             "tdaNow": {c: round(float(X.loc[last_complete, c]), 4) for c in blocks["tda_raw"]}, "volNow": {c: round(float(X.loc[last_complete, c]), 4) for c in VOL_COLS}}
    for nme in ("M0", "M0r", "M1", "M1r", "M2", "M2r", "M3", "M4", "M5", "M6", "M4d", "S_only", "T_only", "M1A1", "M0A1", "M0S", "M0T"):
        for tg, _ in targets:
            today["readings"][f"{nme}:{tg}"] = today_reading(nme, tg, last_complete)
            pv = preds[(nme, tg)].iloc[-1]
            today["provisionalReadings"][f"{nme}:{tg}"] = (round(float(pv), 4) if np.isfinite(pv) else None)
            if today["readings"][f"{nme}:{tg}"] is not None and tg != "y13":
                worse = [e for e, v in bvb.get(f"{nme}:{tg}", {}).items() if e != "pooled" and v is not None and v > 0]
                today["readings"][f"{nme}:{tg}"]["calibration"] = ("ok (Brier <= training base in every era)" if not worse else f"not calibrated (Brier > training base in {', '.join(worse)})")
    today["readinessOn"] = bool((X.loc[last_complete, "btc_dd_ath"] >= np.log(0.95)) and (X.loc[last_complete, "m2_yoy"] > 0))

    # ------------------------------------------------------------------ other cheap checks
    res["checks"]["refitJump"] = {k: C.refit_jump_report(preds[(k, "fall5_26w")], [r["t"] for r in refits[(k, "fall5_26w")]]) for k in ("M1", "M4", "M2")}
    res["checks"]["params"] = {k: C.params_report(len(colsets[k]) + 1) for k in ("M0", "M1", "M2", "M4", "M5", "M6")}
    res["checks"]["timeReversal"] = "The time-reversed window has exactly the negated Levy areas (depth-2 antisymmetry), so it is collinear with the real feature and is not offered as a decoy; the block-shuffled window is."
    big_ep = {tg: {e: oos[f"M1:{tg}"]["byEra"].get(e, {}).get("nEp") for e in ("2019-2020", "2021-2022", "2023-2026", "pooled")} for tg in ("fall5_26w", "fall10_26w")}

    # ------------------------------------------------------------------ summary lines
    def era_str(key, head="auc"):
        e = oos[key]["byEra"]
        return "/".join(fmt(e.get(k, {}).get(head)) for k in ("2019-2020", "2021-2022", "2023-2026", "pooled"))

    def inc_str(key):
        i = incs[key]["inc"]
        b = bands.get(key, {})
        bb, be = b.get("block", {}), b.get("episode", {})
        band = (f" [{fmt(bb.get('q05'))},{fmt(bb.get('q95'))}]" if bb.get("n") else "") + (f" ep[{fmt(be.get('q05'))},{fmt(be.get('q95'))}]" if be.get("n") else "")
        return "/".join(fmt(i.get(k)) for k in ("2019-2020", "2021-2022", "2023-2026", "pooled")) + f" mE {fmt(i.get('meanEra'))}" + band + (f" fresh {fmt(i.get('fresh'))}" if "fresh" in i else "")

    def bvb_str(key):
        d = bvb.get(key, {})
        return "/".join(("na" if d.get(k) is None else f"{d[k]:+.3f}") for k in ("2019-2020", "2021-2022", "2023-2026"))

    def p_str(d, n_min=20):
        if not d or d.get("p") is None:
            return "na"
        return f"{d['p']:.2f}" if d.get("n", 0) >= n_min else f"na(n{d.get('n', 0)})"
    tick("today")
    runtime = time.time() - t0
    res["timing"] = timing
    decoys = {"areaShiftNull": shift_null_area, "nBeatShift": n_beat_shift, "nShiftDraws": n_shift_done, "areaAlone": area_alone, "autocorrLag1": autocorr,
              "blockShuffleNull": shuffle_null, "nBeatBlockShuffle": n_beat, "nBlockShuffles": n_shuf, "M4dCoefs": signs["M4d:fall5_26w"],
              "note": "areaShiftNull (circular shift of the real area series, keeps its autocorrelation) is the headline; blockShuffleNull draws a fresh shuffle per bar, so its null feature is white and its p-values are too small (kept for comparison). The pre-registered candidate was chosen after its full-sample AUC had been seen (ROUND8_PLAN [5]), so areaAlone is a confirmation of an in-sample number, not a new test."}
    res.update({"runtimeSec": round(runtime, 1), "firstForecast": first_fc, "oos": oos, "increments": incs, "incrementBands": bands, "brierVsBase": bvb, "looEvent": loos, "null": null, "surrogates": surrogates,
                "decoys": decoys, "rwPlacebo": rw_placebo, "corrVol": corr_vol, "volProxies": proxies, "signs": signs, "bigEventRank": big_rank,
                "daily": daily, "transfer": transfer, "today": today, "blocks": {k: v for k, v in blocks.items()}})
    C.write_results(a.out, res)
    try:
        summarise(a, res, locals())
    except Exception:
        import traceback
        res["notes"].append("summary failed: " + traceback.format_exc()[-800:])
        C.write_results(a.out, res)
        raise


def summarise(a, res, V):
    globals().update({k: v for k, v in V.items() if k not in ("a", "res")})
    runtime = V["runtime"]
    say(f"tda_sig  {res['runUtc']} UTC / {res['runEt']} ET  fast={a.fast} nulls={a.nulls} surrogates={n_sur} ripser={HAVE_RIPSER} features {feat_sec:.0f}s weekly / {feat_sec_d:.0f}s daily; stage seconds {timing}")
    say(f"weekly rows {len(X)} from {X.index[0].date()}; 5-series features from {first_feat.date()} (TDA {first_tda.date()}); first forecast reached: M4 {first_fc['M4']}, M0 {first_fc['M0']}, M4t2 {first_fc.get('M4t2')} (min_train 60, labels lagged 26)")
    say(f"base 2019+: fall5_26w {fmt(float(Y.loc[post, 'fall5_26w'].mean()))} (episodes {big_ep['fall5_26w']}), fall10_26w {fmt(float(Y.loc[X.index >= pd.Timestamp(START), 'fall10_26w'].mean()))} (episodes {big_ep['fall10_26w']}: ONE episode Oct 2020-May 2021, none since 2023); fresh share {fmt(float(fresh[X.index >= pd.Timestamp(START)].mean()))}; 5+ events since 2016: {len(ev)}")
    say(f"truncation test {res['checks']['truncation']['ok']} (max diff {res['checks']['truncation']['maxAbsDiff']:.1e}, {tested} t); ripser vs numpy fallback max diff {fb.get('maxDiffVsFallback')}")
    say("-- fall5_26w AUC 19-20/21-22/23-26/pooled (mE = mean of eras) | fresh pooled | Brier minus TRAINING-base Brier by era (neg = better) | increment over REF (same training rows: M1r; M0r for M0*/M1r; M1t2 for M4t2; M0/M1 rows show the 2016-18 history premium over M0r/M1r) by era/pooled mE [26w block-boot 5-95%] ep[episode-boot] fresh | shift-null p (pooled, increment) | LOO -big/min")
    order = ["M0", "M0r", "M1", "M1r", "M2", "M2r", "M2h", "M3", "M2w52", "M0T", "M4", "M4w52", "M4t2", "M1A1", "M0A1", "M0S", "M5", "M6", "M4d"]  # M2b, S_only, T_only rows in results.json (S_only/T_only on the decoys line)
    for nme in order:
        key = f"{nme}:fall5_26w"
        if key not in oos:
            continue
        nl = null.get(key, {})
        lo_ = loos.get(key, {})
        say(f"{nme:7s} {era_str(key)} mE {fmt(oos[key].get('meanEra'))} | {fmt(oos[key]['fresh'].get('pooled'))} | BvB {bvb_str(key)} | {incs[key]['ref']}: {inc_str(key)} | p {p_str(nl.get('pooled'))},{p_str(nl.get('increment'))} | {fmt(lo_.get('dropBigEpisode'))}/{fmt(lo_.get('min'))}")
    say("single blocks and decoys, fall5_26w AUC by era/pooled: " + "; ".join(f"{k} {era_str(f'{k}:fall5_26w')}" for k in ("V_only", "S_only", "T_only", "clock", "eramean")) + " (every model must beat clock and era-mean within each era); S_only and V_only sit FAR below 0.5 in 2021+ (sign learned in 2018-20 inverted out of sample), a gating candidate, not a forecaster")
    rwm, rwx, rwe = rw_placebo["median"], rw_placebo["max"], rw_placebo["excess"]
    say(f"matched-random-walk PLACEBO level ({rw_placebo['nPanels']} base-rate-matched panels, real base {rw_placebo['realBase']}, panel bases {[r['base'] for r in rw_placebo['panels']]}): pooled fall5_26w AUC median/max -> " + " ".join(f"{n} {fmt(rwm.get(n))}/{fmt(rwx.get(n))} (real {fmt(oos[f'{n}:fall5_26w']['byEra'].get('pooled', {}).get('auc'))}, excess {fmt(rwe.get(n))})" for n in ("M0", "M0r", "M1r", "M4", "M1A1", "V_only", "S_only")) + f"; placebo M4-M1r median {fmt(rwm.get('M4-M1r'))} M1A1-M1r {fmt(rwm.get('M1A1-M1r'))} M0A1-M0r {fmt(rwm.get('M0A1-M0r'))}")
    say("fall10_26w pooled AUC (ONE OOS episode; the 5-series models see no fall10 positive in training before 2021): " + " ".join(f"{k} {fmt(oos[f'{k}:fall10_26w']['byEra'].get('pooled', {}).get('auc'))}" for k in ("M0", "M0r", "M1", "M2", "M2r", "M4", "M0A1", "M5", "M6")) + f"; by era in results.json")
    say("-- y13 IC by era/pooled mE | hit pooled | increment over REF (same rows) by era/pooled mE [bands] | p (pooled, inc)")
    for nme in ("M0", "M1", "M1r", "M2", "M2r", "M4", "M0A1", "M0S", "M5", "M6"):
        key = f"{nme}:y13"
        nl = null.get(key, {})
        say(f"{nme:7s} {era_str(key, 'ic')} mE {fmt(oos[key].get('meanEra'))} | {fmt(oos[key]['byEra'].get('pooled', {}).get('hit'))} | {incs[key]['ref']}: {inc_str(key)} | p {p_str(nl.get('pooled'))},{p_str(nl.get('increment'))}")
    we = null["M4:fall5_26w"].get("withinEra", {})
    wa = null["M0A1:fall5_26w"].get("withinEra", {})
    say(f"within-era shifted null of the increment (real, p; {era_n} draws per era): M4-{incs['M4:fall5_26w']['ref']} 19-20 {fmt(we.get('2019-2020', {}).get('real'))},{fmt(we.get('2019-2020', {}).get('p'), 2)} 23-26 {fmt(we.get('2023-2026', {}).get('real'))},{fmt(we.get('2023-2026', {}).get('p'), 2)} | M0A1-{incs['M0A1:fall5_26w']['ref']} 19-20 {fmt(wa.get('2019-2020', {}).get('real'))},{fmt(wa.get('2019-2020', {}).get('p'), 2)} 23-26 {fmt(wa.get('2023-2026', {}).get('real'))},{fmt(wa.get('2023-2026', {}).get('p'), 2)} | M2-{incs['M2:fall5_26w']['ref']} 19-20 p {fmt(null['M2:fall5_26w'].get('withinEra', {}).get('2019-2020', {}).get('p'), 2)} 23-26 p {fmt(null['M2:fall5_26w'].get('withinEra', {}).get('2023-2026', {}).get('p'), 2)}")
    say(f"IAAFT surrogate panels ({n_sur}): increment over {incs['M4:fall5_26w']['ref']} fall5_26w real/p: M2 {fmt(surrogates['M2:fall5_26w'].get('real'))}/{fmt(surrogates['M2:fall5_26w'].get('p'), 2)} M4 {fmt(surrogates['M4:fall5_26w'].get('real'))}/{fmt(surrogates['M4:fall5_26w'].get('p'), 2)} M5 {fmt(surrogates['M5:fall5_26w'].get('real'))}/{fmt(surrogates['M5:fall5_26w'].get('p'), 2)}; y13 M4 {fmt(surrogates['M4:y13'].get('real'))}/{fmt(surrogates['M4:y13'].get('p'), 2)}")
    tda_c = {c: corr_vol[c]["meanVol"] for c in blocks["tda_raw"]}
    say(f"corr(TDA raw, mean realized vol) pre-2019: " + " ".join(f"{c[4:]} {v:+.2f}" for c, v in tda_c.items()) + f"; vol proxies (|corr|>{VOL_PROXY_CORR}): {len(proxies)} -> {[p[4:] if p.startswith('tda_') else p for p in proxies][:8]}"
        + f"; corr(areas, mean vol) max |r| {max(abs(corr_vol[c]['meanVol']) for c in blocks['area'] + blocks['tarea']):.2f}, usdt>btcd area r {corr_vol[usdt_btcd]['meanVol']:+.2f}, sym products max |r| {max(abs(corr_vol[c]['meanVol']) for c in blocks['sym']):.2f}")
    s5 = signs["fall5_26w"][usdt_btcd]
    s13 = signs["y13"][usdt_btcd]
    sn = shift_null_area[usdt_btcd]
    say(f"usdt>btcd area (DATA-CHOSEN candidate, one of 15, picked after its full-sample AUC was seen): learned sign fall5_26w {s5['mean']:+.3f} (pos share {s5['posShare']}), y13 {s13['mean']:+.3f} ({s13['posShare']}); now {today['areasNow'][usdt_btcd]:+.3f}; single-feature AUC 2019+ {sn['realAuc']} (in-sample by construction) vs circular-shift null of the real series ({n_shift_done} draws >= 26w): p {fmt(sn['p'], 2)}, p95 |AUC-.5| {fmt(sn['shiftP95'])}, family-wise over 15 areas p {fmt(sn['pFamily'], 2)}; {n_beat_shift}/15 areas beat p<0.05 (per-bar block-shuffle null, white: {n_beat}/15, p {shuffle_null[usdt_btcd]['p']}, p95 {shuffle_null[usdt_btcd]['shufP95']})")
    aa = area_alone
    br = big_rank[usdt_btcd]
    t2a = big_rank.get("area_TOTAL2>BTC.D_t2", {"bigRank": None, "nEventsWithValue": 0})
    say(f"usdt>btcd area alone by era AUC (fresh rows): " + " ".join(f"{e[:4]}-{e[7:]} {fmt(aa[e]['auc'])} ({fmt(aa[e]['freshAuc'])}, {aa[e]['nEp']} ep)" for e in ("2019-2020", "2021-2022", "2023-2026")) + f"; residualised on fixed5 (in-sample OLS) {fmt(aa['residualisedOnFixed5Auc'])}; spearman with fixed5: " + " ".join(f"{k} {v:+.2f}" for k, v in aa["overlapSpearman"].items())
        + f"; big-event rank among {len(ev)} 5+ event starts (1 = largest): usdt>btcd {br['bigRank']} (values at {br['nEventsWithValue']} events), tda_h1tot {big_rank['tda_h1tot']['bigRank']}, t2 total2>btcd {t2a['bigRank']} ({t2a['nEventsWithValue']} events)")
    say(f"lag-1 autocorrelation: real area {autocorr['realArea']}, per-bar shuffled null {autocorr['perBarShuffledArea']}, M4d decoy (segment-constant permutation) {autocorr['decoyArea']}, target {autocorr['target']}; M4d decoy |coef| mean {np.mean([abs(signs['M4d:fall5_26w'][c]['mean']) for c in blocks['dec_area']]):.3f} vs real {np.mean([abs(signs['M4d:fall5_26w'][c]['mean']) for c in blocks['area']]):.3f} (descriptive; a smoother column draws a larger ridge coefficient whatever its content)")
    say(f"-- daily replica (W=90d, first forecast {daily['oos']['M4:fall5_13w']['firstForecast']}): base 2019+ {daily['base2019on']}; distinct 5-point daily events {daily['events5d']}; AUC/IC pooled (19-20/21-22/23-26) inc over REF (same rows; M4 also vs M0r), null p (pooled, inc; {daily['null']['nDraws']} draws, na below 20) for fall5_13w")
    for nme in ("M0", "M0r", "M1", "M4", "M0A1", "M5"):   # D M1r equals D M1 (same rows at daily scale) and M6 are in results.json
        parts = []
        for tg, binary in targetsD:
            key = f"{nme}:{tg}"
            head = "auc" if binary else "ic"
            e = daily["oos"][key]["byEra"]
            i = daily["increments"][key]["inc"]
            extra = f" (vsM0r {fmt(daily['increments'][key]['incVsM0r'].get('pooled'))})" if "incVsM0r" in daily["increments"][key] and tg == "fall5_13w" else ""
            parts.append(f"{tg} {fmt(e.get('pooled', {}).get(head))} ({fmt(e.get('2019-2020', {}).get(head))}/{fmt(e.get('2021-2022', {}).get(head))}/{fmt(e.get('2023-2026', {}).get(head))}) inc {fmt(i.get('pooled'))}{extra}")
        nd = daily["null"].get(f"{nme}:fall5_13w", {})
        say(f"D {nme:6s} {daily['increments'][f'{nme}:fall5_13w']['ref']}: " + " | ".join(parts) + (f" | p {p_str(nd.get('pooled'))},{p_str(nd.get('increment'))}" if nd else ""))
    tf = tr.get("fall5_26w", {})
    say(f"transfer daily->weekly (M4, same refit dates, common rows n {tf.get('weeklyFit', {}).get('pooled', {}).get('n')}): weekly-fit AUC {fmt(tf.get('weeklyFit', {}).get('pooled', {}).get('auc'))}, daily coefs on weekly z {fmt(tf.get('coefTransfer', {}).get('pooled', {}).get('auc'))}, daily model raw {fmt(tf.get('rawTransfer', {}).get('pooled', {}).get('auc'))} (all rows {fmt(tf.get('rawTransferAllRows', {}).get('pooled', {}).get('auc'))}); fresh weekly {fmt(tf.get('freshWeeklyFit'))} vs transfer {fmt(tf.get('freshCoefTransfer'))}"
        + "; by era (coef/wk): " + " ".join(f"{e[:4]}-{e[7:]} {fmt(tf.get('coefTransfer', {}).get(e, {}).get('auc'))}/{fmt(tf.get('weeklyFit', {}).get(e, {}).get('auc'))}" for e in ("2019-2020", "2021-2022", "2023-2026")) + f"; RW control weekly-fit/coef/raw: " + " ".join(f"{fmt(r['weeklyFit'])}/{fmt(r['coefTransfer'])}/{fmt(r['rawTransfer'])}" for r in transfer["rwControl"]))
    sc = sign_cmp["W:fall5_26w|D:fall5_13w"]
    sc2 = sign_cmp["W:y13|D:y13"]
    say(f"area sign agreement daily vs weekly: fall5 {sc['agreeShare']} (top-5 weekly {sum(sc['agreeTop5'].values())}/5), y13 {sc2['agreeShare']} (top-5 {sum(sc2['agreeTop5'].values())}/5); usdt>btcd daily fall5 {sc['usdtLeadsBtcd']['daily']['mean']:+.3f} y13 {sc2['usdtLeadsBtcd']['daily']['mean']:+.3f}")
    rd = today["readings"]
    say(f"TODAY {today['asOf']} (provisional bar {provisional}): BTC.D {today['btcd']} fresh {today['fresh']} readiness {today['readinessOn']}; P(5+ in 26w): " + " ".join(f"{k} {fmt(rd[f'{k}:fall5_26w']['value']) if rd.get(f'{k}:fall5_26w') else 'na'}" for k in ("M0", "M0r", "M1", "M1r", "M2", "M2r", "M4", "M1A1", "M0A1", "M0S", "M5", "M6", "S_only", "T_only")) + "; P(10+): " + " ".join(f"{k} {fmt(rd[f'{k}:fall10_26w']['value'], 4) if rd.get(f'{k}:fall10_26w') else 'na'}" for k in ("M0", "M0r", "M1", "M4")) + "; y13: " + " ".join(f"{k} {fmt(rd[f'{k}:y13']['value']) if rd.get(f'{k}:y13') else 'na'}" for k in ("M0", "M1", "M4")))
    if rd.get("M4:fall5_26w"):
        bc = rd["M4:fall5_26w"]["blockContrib"]
        say(f"M4 today logit blocks: intercept {rd['M4:fall5_26w']['intercept']:+.2f} " + " ".join(f"{b} {v:+.2f}" for b, v in bc.items()) + f"; spread under drops/+-1sd {rd['M4:fall5_26w']['spreadDropsPerturb']}; M1 spread {rd['M1:fall5_26w']['spreadDropsPerturb']}; M1r spread {rd['M1r:fall5_26w']['spreadDropsPerturb']}"
            + "; calibration (Brier vs training base by era): " + "; ".join(f"{k} {rd[f'{k}:fall5_26w']['calibration'].replace('(Brier <= training base in every era)', '').replace('Brier > training base in ', '')}" for k in ("M0", "M0r", "M1r", "M4", "M1A1", "M0A1") if rd.get(f"{k}:fall5_26w")))
    rj = res["checks"]["refitJump"]["M4"]
    say(f"refit jumps M4: max at refit {rj['maxJumpAtRefit']} vs elsewhere {rj['maxJumpElsewhere']}; params M4 {len(colsets['M4']) + 1}, M5 {len(colsets['M5']) + 1}, M6 {len(colsets['M6']) + 1} vs 12 label episodes (3 big events)")
    # verdict (pre-registered criteria)
    def ge(v, thr):
        return v is not None and v >= thr

    def passes(nme):
        k = f"{nme}:fall5_26w"
        i = incs[k]["inc"]
        i13 = incs[f"{nme}:y13"]["inc"]
        pool_ok = ge(i.get("pooled"), 0.03) or ge(i13.get("pooled"), 0.08)
        era_ok = all((i.get(e) is None) or (i.get(e) >= 0) for e in ("2019-2020", "2021-2022", "2023-2026"))
        p = null.get(k, {}).get("increment", {}).get("p")
        null_ok = p is not None and p < 0.05   # (p or 1) would turn a p of exactly 0 into a FAIL
        fresh_ok = ge(i.get("fresh"), 0.03)
        me, me13 = i.get("meanEra"), i13.get("meanEra")
        return {"incPooled": pool_ok, "incEveryEra": era_ok, "nullP": null_ok, "fresh": fresh_ok, "all": bool(pool_ok and era_ok and null_ok and fresh_ok), "ref": incs[k]["ref"],
                "incPooledValue": i.get("pooled"), "incMeanEra": me, "incMeanEraIC": me13, "meanEraWouldPass": bool(ge(me, 0.03) or ge(me13, 0.08)),
                "pooledMeanEraDisagree": bool(i.get("pooled") is not None and me is not None and np.sign(i["pooled"]) != np.sign(me) and (abs(i["pooled"]) >= 0.01 or abs(me) >= 0.01))}
    verdict = {nme: passes(nme) for nme in ("M2", "M2r", "M3", "M4", "M5", "M6", "M2b", "M1A1", "M0A1", "M0S", "M0T") if f"{nme}:fall5_26w" in incs}
    say("verdict vs SAME-ROWS reference (all four required: inc>=+0.03 pooled AUC or >=+0.08 IC; inc>=0 every era; shift-null p<0.05; +0.03 on fresh): " + " ".join(f"{k} {'PASS' if v['all'] else 'fail'}({''.join('1' if v[c] else '0' for c in ('incPooled', 'incEveryEra', 'nullP', 'fresh'))})" for k, v in verdict.items())
        + "; mean-of-era increment would pass the +0.03 bar for: " + (", ".join(k for k, v in verdict.items() if v["meanEraWouldPass"]) or "none") + "; pooled and mean-of-era increments disagree in sign for: " + (", ".join(f"{k} ({fmt(v['incPooledValue'])} vs {fmt(v['incMeanEra'])})" for k, v in verdict.items() if v["pooledMeanEraDisagree"]) or "none"))
    coef_ok = (tf.get("coefTransfer", {}).get("pooled", {}).get("auc") is not None) and (tf.get("weeklyFit", {}).get("pooled", {}).get("auc") is not None) and abs(tf["coefTransfer"]["pooled"]["auc"] - tf["weeklyFit"]["pooled"]["auc"]) <= 0.05
    rw_fail = all((r["coefTransfer"] is None) or (r["weeklyFit"] is None) or abs(r["coefTransfer"] - r["weeklyFit"]) > 0.05 or r["coefTransfer"] < 0.55 for r in transfer["rwControl"])
    say(f"transfer verdict: daily-fitted within 0.05 of weekly-fitted {coef_ok}; top-5 signs agree {sum(sc['agreeTop5'].values())}/5; RW control fails transfer {rw_fail} -> {'PASS' if coef_ok and sum(sc['agreeTop5'].values()) >= 4 and rw_fail else 'fail'}")
    say(f"runtime {runtime:.0f}s")

    # ------------------------------------------------------------------ write
    res["notes"].extend([
        f"Last complete Sunday close {last_complete.date()}; bars {provisional} are provisional (partial week), never in a training set (label lag >= 13 weeks); today's reading is the {last_complete.date()} row, the provisional row is reported separately.",
        f"USDT.D and TOTAL3 enter from {LATE_START['USDT.D']} (never bfilled): 5-series features from {first_feat.date()}; with min_train 60 and labels lagged 26 weeks the first M4 forecast is {first_fc['M4']} (M0/M1 fit from {first_fc['M0']} on more history: M0r/M1r are the same models restricted to M4's rows). M4t2 (TOTAL2 instead of USDT.D/TOTAL3, no stablecoin share) is the long-history variant from {first_fc.get('M4t2')}.",
        "TDA: increments standardised by trailing 104-bar mean/sd (raw) or in-window (scale-free), delay embedding d=3 tau=1, coordinates divided by sqrt(d*m) so typical point distances are ~sqrt(2); Rips H0/H1 via ripser (numpy MST + Z2 bitset reduction fallback, 40 maxmin landmarks); landscapes on a fixed 0-2 grid. corr with realized vol printed; features above 0.8 are vol proxies and M2h drops them.",
        "Signatures: window path (W increments ending at bar t) rebased to zero, time-augmented; depth-2 iterated sums; Levy area A_ij > 0 means series i moved first and j followed; scaled by the product of trailing sds; timing terms = running area integrated against time minus half the final area; decoys = areas of the 4-bar block-shuffled window (same ridge). Per-block ridge: 1 for blocks of <= 10 features, 10 above (sig2 = 30 features).",
        "Vol-residualised TDA (M2r): at each refit each TDA summary is regressed on the vol block over training rows and the residual is the feature, beta frozen for the test block.",
        "fall10_26w rests on one OOS episode (Oct 2020 - May 2021): every fall10 AUC ranks one event. No duration output from this module.",
        "The time-reversed window gives exactly the negated Levy areas (depth-2 antisymmetry), so it is not offered as a decoy (it would be collinear); the block-shuffled window is.",
        f"REFERENCE (round-8 fixer): every increment, band, null and the verdict are taken against the same model fitted on the SAME training rows as the tested model (M1r = fixed5 + vol restricted to the 5-series rows from {first_feat.date()}; M0r for the M0-based families). M0/M1 fitted from 2016-06 hold the two in-sample big waterfalls and are worth about +0.11 (fixed5) / +0.03 (fixed5+vol) pooled AUC on the common rows by history alone; they stay in the table as external comparators and their row's 'increment' is that history premium. The increments against the long-history M0/M1 are kept in increments[*].incVsLongRef.",
        "Headline columns: AUC by era and mean-of-era beside pooled (era bases 0.63/0.34/0.09 on the 5-series rows make the pooled AUC reward cross-era level ordering), Brier minus the TRAINING-window base-rate Brier by era (trainmean_r = the training mean on the same rows), the 26-week block bootstrap AND the episode bootstrap of every increment, and the verdict's pre-registered pooled criterion with the mean-of-era increment reported beside it (and any sign disagreement named).",
        "Nulls: shifted targets rerun every model (fit included) per shift; the increment null is the distribution of (model - reference) pooled AUC/IC under the shift; within-era nulls shift only the era's rows; IAAFT surrogate panels replace the five level series' increments (per series, cross-order destroyed) and rerun the whole feature pipeline and the walks against the real targets. Single-area null: the real area series circularly shifted by >= 26 weeks (keeps its lag-1 autocorrelation of ~0.96; the per-bar block-shuffle null is white at ~0.08 and its p-values are too small, kept only for comparison), with a family-wise p over the 15 areas. Matched-random-walk placebo: base-rate-matched random-walk panels of the five crypto series (macro kept) through the weekly pipeline give the placebo level of every model's absolute pooled AUC; real minus placebo median is the excess.",
        "M4d decoys: areas of the 4-bar block-shuffled window with ONE permutation per 26-bar segment (a fresh shuffle per bar gave a white decoy that no ridge would weight like a smooth real area); the decoy-vs-real coefficient comparison stays descriptive.",
        "S_only and V_only have OOS AUC far below 0.5 in 2021-22 and 2023-26 (0.17-0.27 / 0.20): the sign learned in 2018-20 inverted after 2021, the brief's sign-switcher phenomenon again. With 12 episodes that inversion is one observation (training era vs test era), so neither is a forecaster, but the plan's dynamics rule says gate it (regime module), not drop it.",
        "Daily and weekly walks share refit dates (13 weeks = 91 days from 2019-01-06); the transfer applies the daily fall5_13w M4 coefficients to weekly rows of the same refit block only, scored against weekly fall5_26w and fall5_13w on rows where the weekly-fitted model also has a forecast; the random-walk control replaces the five crypto series by matched random walks (macro kept) and runs the same transfer.",
        "Pooled AUCs rest on about two liquidity swings (M2 moves once per cycle): judge within-era increments and the within-era null, not the pooled number alone.",
        "The vol block alone (V_only) is below 0.5 and adding it to fixed5 lowers the pooled AUC (M1r - M0r on the same rows is in the M1r row), so M1r is a weaker reference than M0r: every family is therefore also stacked directly on fixed5 (M0T, M0S, M0A1 with ref M0r).",
        f"The single USDT.D>BTC.D area was chosen in ROUND8_PLAN [5] after its full-sample AUC (0.67-0.69) had been computed on these rows, so it is a DATA-CHOSEN candidate, one of 15 areas looked at; its standalone 2019+ AUC here is a confirmation of an in-sample number, not a new test (decoys.areaAlone, decoys.areaShiftNull with the family-wise p). Its measured overlaps are with the five signals as printed (spearman in decoys.areaAlone.overlapSpearman: largest with btc_dd_ath, negative with usdtd_vsma30w), and residualised on fixed5 in sample its AUC falls to {area_alone['residualisedOnFixed5Auc']}; its learned sign is positive at weekly and negative at daily scale.",
        f"Daily shifted-target nulls: {daily['null']['nDraws']} draws in this run (p printed as 'na' below 20; the full run uses 40+).",
        "Today's readings are the last fitted model applied to the last complete Sunday row; M0r/M1r (same training rows as the geometric models) are printed beside M0/M1, and each reading carries a calibration flag (Brier vs training base by era); a flagged reading (M4 in both event-bearing eras) is a model output, not a forecast to quote.",
        "Transfer: the daily-fitted M4 coefficients applied to weekly rows score within 0.05 of the weekly fit, but so do matched random walks (rwControl), and the standardised area signs disagree between scales, so the transfer is carried by the shared fixed5 + vol part, not by the areas.",
        "events() is used only for description (event table, big-event ranks); the fresh-start filter uses only the trailing 13-week high.",
    ])
    if a.fast:
        res["notes"].append(f"--fast: 20 shifted nulls, 10 surrogates, 30 block shuffles, {n_area_shift} area shifts, 200 bootstrap draws, no W=52 sweep, 2 random-walk transfer controls, {n_rw_placebo} random-walk placebo panels, {n_daily_nulls} daily nulls.")
    every = 2
    series = {}
    for nme in ("M0", "M1", "M2", "M2r", "M4", "M5", "M6", "S_only", "T_only", "M0A1", "M0S"):
        for tg, _ in targets:
            series[f"{nme}:{tg}"] = C.thin(preds[(nme, tg)], every=every)
    series["transfer_coef:fall5_26w"] = C.thin(pc, every=every)
    series[usdt_btcd] = C.thin(X[usdt_btcd][X.index >= pd.Timestamp("2018-01-01")], every=every)
    series["tda_h1tot"] = C.thin(X["tda_h1tot"][X.index >= pd.Timestamp("2018-01-01")], every=every)
    series["P(fall5_26w)"] = series["M4:fall5_26w"]
    series["P(fall10_26w)"] = series["M4:fall10_26w"]
    res.update({"series": series, "verdict": verdict, "summary": LINES, "refits": {k: [r["t"] for r in refits[(k, "fall5_26w")]] for k in ("M0", "M1", "M4")}})
    C.write_results(a.out, res)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(2, 1, figsize=(12, 7), sharex=True)
        for k, c in (("M0", "gray"), ("M1", "tab:blue"), ("M4", "tab:red"), ("M2", "tab:green")):
            ax[0].plot(preds[(k, "fall5_26w")].index, preds[(k, "fall5_26w")].values, c, lw=1, label=k)
        ax[0].plot(Y.index, Y["fall5_26w"].values * 0.98, "k.", ms=2, label="fall5_26w")
        for r in refits[("M4", "fall5_26w")]:
            ax[0].axvline(pd.Timestamp(r["t"]), color="k", alpha=0.08)
        ax[0].legend(loc="upper left", fontsize=8)
        ax[0].set_title("P(5+ point BTC.D fall within 26 weeks), out of sample; refits marked")
        ax[1].plot(X.index, X[usdt_btcd].values, "tab:purple", lw=1, label=usdt_btcd)
        ax[1].plot(X.index, X["tda_h1tot"].values / max(1e-9, np.nanmax(X["tda_h1tot"].values)) , "tab:olive", lw=1, label="tda_h1tot (scaled)")
        ax[1].plot(X.index, X["btcd_vol13w"].values / max(1e-9, np.nanmax(X["btcd_vol13w"].values)), "k", lw=0.8, alpha=0.5, label="btcd_vol13w (scaled)")
        ax[1].legend(loc="upper left", fontsize=8)
        ax[1].set_xlim(pd.Timestamp("2018-01-01"), X.index[-1])
        fig.tight_layout()
        fig.savefig(os.path.join(a.out, "tda_sig.png"), dpi=110)
    except Exception as e:  # pragma: no cover
        res["notes"].append(f"chart skipped: {e}")
        C.write_results(a.out, res)
    for s in LINES[:60]:
        print(s)
    if len(LINES) > 60:
        print(f"(+{len(LINES) - 60} more summary lines in results.json)")


if __name__ == "__main__":
    main()
