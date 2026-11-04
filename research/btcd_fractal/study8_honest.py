#!/usr/bin/env python3
"""Round 8 trial [1] "honest": the evidence ceiling of this data and the honest conditional base rate with intervals.

Question: is everything above M2-alone era structure, and does anything move inside a cycle?

Model: a stratified base rate on three point-in-time variables (M2 y/y, BTC drawdown from ATH, ETH/BTC vs its 52-week
high) with thresholds fixed as constants below (fixed before this run; the cut points were suggested by the three big
waterfalls, one of which, Jan 2021, lies inside the evaluation window: the threshold-perturbation decoy is the control),
cells with fewer than MIN_EP training label episodes merged into their M2 bucket, rate = (k+1)/(n+4) (Beta(1,3) prior,
mean = the 25% base rate), refit every 13 weeks on an expanding window with labels withheld until their horizon has
passed. Per-stratum Kaplan-Meier on the time to the first 5-point fall (the same conditional rate in survival form, built
from the same rows; every spell open at the refit censored at the refit). Every comparator of the plan (fixed5, M2 alone,
M2 + ETH/BTC, ETH/BTC alone, the brief's literal five-signal set, halving clock, renewal clock, era-mean decoy, readiness
rule, fixed5 + stratified offset / stack, the ex-stablecoin target) goes through the same harness and is scored on the
SAME rows (the intersection of every comparator's forecasts, first forecast 2019-04-07), and the evidence ceiling (block
and episode bootstraps, PAIRED block-bootstrap differences against fixed5, episode leave-one-out with and without the
run-up, dwell-time block-permutation nulls within each era and pooled, era-stratified AUC, fresh-start AUC, Brier against
both the training-window base rate and the era's own rate) is reported for all of them. Pre-registered claims A/B/C are
evaluated as written in ROUND8_PLAN.md, plus a corrected decoy set (era-mean decoy sign-flipped as a bound, renewal clock).

  python3 research/btcd_fractal/study8_honest.py --data research/btcd_fractal/data --out research/btcd_fractal/out8/honest [--nulls N] [--fast]

Point in time: every fitted object (cell counts, merge map, vol terciles, KM curves, logistic weights, stack weights)
is fitted on the training window of its refit only. Bootstraps, episode lists and nulls run after all predictions
are frozen and never feed a fit. Labels are built from complete Sunday closes only, so the partial current week is in
no training set and no evaluation label. btc_dd_ath is rebuilt here from the full BTCUSD history (the shared loader
anchors the all-time high at BTC.D's first date, April 2014, which drops the Dec 2013 high); that changes 30 rows in
2016 and no walk-forward prediction (asserted below), but it changes the readiness rule's record at the Nov 2016
waterfall from 'fired' to 'did not fire'.
"""
import argparse
import datetime as dt
import itertools
import math
import os
import sys
import time
from multiprocessing import get_context

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import study8_common as C  # noqa: E402
import study8_baselines as B  # noqa: E402

# ------------------------------------------------------------------------------------------- pre-registered constants
STRAT_COLS = ["m2_yoy", "btc_dd_ath", "ethbtc_fromhi52w"]           # all three are inside study8_baselines.SIGNALS
STRAT_M2BTC = ["m2_yoy", "btc_dd_ath"]                               # no-ETH/BTC variant: can train from 2016-06
CUTS = {"m2_yoy": (0.0, 0.05),                                      # <0 | 0..5% | >5%
        "btc_dd_ath": (np.log(0.65), np.log(0.95)),                 # >35% under ATH | 5..35% | within 5%
        "ethbtc_fromhi52w": (np.log(0.70), np.log(0.90))}           # >30% under 52w high | 10..30% | within 10%
BUCKET_NAMES = {"m2_yoy": ["m2<0", "m2 0-5%", "m2>5%"], "btc_dd_ath": ["btc>35%dd", "btc 5-35%dd", "btc<5%dd"],
                "ethbtc_fromhi52w": ["eth>30%off", "eth 10-30%off", "eth<10%off"]}
VOL_COL = "btcd_vol13w"
PRIOR_A, PRIOR_B = 1.0, 3.0                                          # Beta(1,3): mean 0.25 = the base rate
MIN_EP = 2                                                           # cells with fewer training episodes merge into M2 bucket
TODAY = pd.Timestamp("2026-11-02")
EP_BIG = "2020-10-18..2021-05-09"                                    # the Oct 2020 - May 2021 episode in fall5_26w
EP_2025 = "2025-04-06..2025-07-13"
JUN2025_PEAK = 65.7
HIGHER_HIGH_FROM = pd.Timestamp("2025-06-29")
FALSIFIER_DATE = pd.Timestamp("2027-11-02")
TARGETS_BIN = ["fall5_26w", "fall10_26w"]
EX_TARGETS = ["exstable_fall5_26w", "exstable_fall10_26w"]
FIXED5_BRIEF = ["usdtd_vsma30w", "ethbtc_fromhi52w", "btc_dd_ath", "btcd_fromhi52w", "m2_yoy"]   # the brief's literal most-picked set
COMPARATORS = ["fixed5", "m2only", "m2eth", "ethonly", "fixed5brief", "clock", "renewal", "eramean", "readiness", "strat", "strat_vol", "strat_m2btc", "offset", "stack"]
NULL_MODELS = ["strat", "fixed5", "m2only", "m2eth", "ethonly", "clock", "renewal", "eramean", "readiness", "strat_vol", "offset", "stack"]
WITHIN_MODELS = ["strat", "fixed5", "m2only", "m2eth", "clock", "renewal", "eramean"]
PERM_POOLED_MODELS = ["strat", "fixed5", "m2only", "m2eth"]
PLACEBO_MATCH = {"episodes": (6, 24), "base": (0.13, 0.52)}         # a surrogate draw is 'matched' when its rebuilt label is within 2x of the real one
MIN_DRAWS_FOR_P = 50                                                 # no p-value or p95 is quoted from fewer draws
ENUMERATE_UP_TO = 120                                                # an era with this many distinct block arrangements or fewer is enumerated exactly
ERA_NAMES = ["2019-2020", "2021-2022", "2023-2026"]

_G = {}            # data shared with forked null workers (set before the pool is created)
_LINES = [0, 0]    # printed, dropped


def say(s):
    if _LINES[0] < 60:
        print(s)
        _LINES[0] += 1
    else:
        _LINES[1] += 1


# ------------------------------------------------------------------------------------------- module features
def ath_drawdown(data_dir, index):
    """log BTCUSD minus its running max over WEEKLY Sunday closes from the first BTCUSD bar (2013-02), on `index`.
    The shared loader starts the panel at BTC.D's first date (2014-04-01) and so anchors the ATH after the Dec 2013 high."""
    d = pd.read_csv(os.path.join(data_dir, "BTCUSD_1d.csv"))
    s = pd.Series(d["c"].values.astype(float), index=pd.DatetimeIndex(pd.to_datetime(d["ts"], unit="ms")).normalize())
    s = s[~s.index.duplicated()].sort_index()
    daily = s.reindex(pd.date_range(s.index[0], max(s.index[-1], index[-1]), freq="D")).ffill()
    w = daily.resample("W-SUN").last().ffill()
    lb = np.log(w)
    return (lb - lb.cummax()).reindex(index)


def renewal_clock(y, lag=26):
    """Decoy: log(1 + weeks since the last positive label KNOWN at t), i.e. the last row i <= t - lag with y_i = 1."""
    v = np.asarray(y, float)
    out = np.full(len(v), np.nan)
    last = -1
    for t in range(len(v)):
        i = t - lag
        if i >= 0 and v[i] == 1:
            last = i
        if last >= 0:
            out[t] = np.log1p(t - last)
    return out


# ------------------------------------------------------------------------------------------- stratified model
def bucket(v, cuts):
    v = np.asarray(v, float)
    return np.where(v < cuts[0], 0, np.where(v < cuts[1], 1, 2))


def encode(X, cuts, cols=STRAT_COLS, vol_thr=None):
    """X: array with columns `cols` (+ VOL_COL last when vol_thr is given). Returns integer cell codes."""
    code = np.zeros(len(X), int)
    for j, c in enumerate(cols):
        code = code * 3 + bucket(X[:, j], cuts[c])
    if vol_thr is not None:
        code = code + (3 ** len(cols)) * np.digitize(X[:, len(cols)], vol_thr)
    return code


def m2_of(code, ncell=27):
    return (code % ncell) // (ncell // 3)


def episode_ids(y):
    ep = np.full(len(y), -1)
    for j, (s, e) in enumerate(C.episodes(y)):
        ep[s:e + 1] = j
    return ep


def strat_fit(Xtr, ytr, cuts=CUTS, use_vol=False, continuous=False, cols=STRAT_COLS):
    nb = 3 ** len(cols)
    vol_thr = np.quantile(Xtr[:, len(cols)], [1 / 3, 2 / 3]) if use_vol else None
    code = encode(Xtr, cuts, cols, vol_thr)
    ncell = nb * 3 if use_vol else nb
    n = np.bincount(code, minlength=ncell).astype(float)
    k = np.bincount(code, weights=ytr, minlength=ncell)
    m2b = m2_of(np.arange(ncell), nb)
    n_m2 = np.bincount(m2_of(code, nb), minlength=3).astype(float)
    k_m2 = np.bincount(m2_of(code, nb), weights=ytr, minlength=3)
    if continuous:
        nep = n.copy()
        nep_m2 = n_m2.copy()
        min_ep = 8.0
        rate_c, rate_m2, rate_g = k / (n + 4.0), k_m2 / (n_m2 + 4.0), ytr.sum() / (len(ytr) + 4.0)
        nep_g = float(len(ytr))
    else:
        ep = episode_ids(ytr)
        pos = ytr > 0.5
        pairs = np.unique(code[pos] * 10000 + ep[pos])
        nep = np.bincount(pairs // 10000, minlength=ncell).astype(float)
        pairs_m2 = np.unique(m2_of(code[pos], nb) * 10000 + ep[pos])
        nep_m2 = np.bincount(pairs_m2 // 10000, minlength=3).astype(float)
        nep_g = float(len(C.episodes(ytr)))
        min_ep = float(MIN_EP)
        rate_c, rate_m2 = (k + PRIOR_A) / (n + PRIOR_A + PRIOR_B), (k_m2 + PRIOR_A) / (n_m2 + PRIOR_A + PRIOR_B)
        rate_g = (ytr.sum() + PRIOR_A) / (len(ytr) + PRIOR_A + PRIOR_B)
    level = np.where(nep >= min_ep, 0, np.where(nep_m2[m2b] >= min_ep, 1, 2))
    rate = np.where(level == 0, rate_c, np.where(level == 1, rate_m2[m2b], rate_g))
    merged = np.where(level == 0, np.arange(ncell), np.where(level == 1, 100 + m2b, 200))
    return {"rate": rate, "level": level, "merged": merged, "n": n, "k": k, "nEp": nep, "n_m2": n_m2, "k_m2": k_m2, "nEp_m2": nep_m2,
            "rate_m2": rate_m2, "rate_g": rate_g, "nEp_g": nep_g, "cuts": cuts, "vol_thr": vol_thr, "cols": list(cols), "base": float(np.mean(ytr)),
            "nTrain": int(len(ytr)), "cellsInUse": int(len(np.unique(merged[n > 0]))), "nb": nb}


def strat_predict(model, Xh, te):
    code = encode(Xh[te], model["cuts"], model["cols"], model["vol_thr"])
    return model["rate"][code]


def strat_cols(use_vol, cols=STRAT_COLS):
    return list(cols) + ([VOL_COL] if use_vol else [])


def lag_of(target):
    return 13 if target == "y13" else 26


def run_strat(X, Y, target, cuts=CUTS, use_vol=False, cols=STRAT_COLS):
    cont = target == "y13"
    pred, refits = C.walk_forward(X[strat_cols(use_vol, cols)], Y[target], lambda a, b: strat_fit(a, b, cuts, use_vol, cont, cols), strat_predict,
                                  label_lag_weeks=lag_of(target))
    return pred, refits


def run_const(X, Y, target, last=None):
    """Decoy: the mean label of the training window (last=None) or of its last `last` weeks."""
    def fit(Xtr, ytr):
        return float(np.mean(ytr if last is None else ytr[-last:]))

    def predict(model, Xh, te):
        return np.full(len(te), model)
    pred, _ = C.walk_forward(X[["m2_yoy"]], Y[target], fit, predict, label_lag_weeks=lag_of(target))
    return pred


def run_readiness(X, Y, target):
    rule = ((X["btc_dd_ath"] >= np.log(0.95)) & (X["m2_yoy"] > 0)).astype(float)
    rule[X.index < pd.Timestamp("2019-01-06")] = np.nan
    return rule


def run_renewal(X, Y, target):
    """Recency decoy with a learned sign: the renewal clock built from the target's own known labels, through the logistic."""
    Xr = X[["m2_yoy"]].copy()
    Xr["renewal"] = renewal_clock(Y[target].values, lag=lag_of(target))
    return B.run_fixed(Xr, Y, target, "W", target != "y13", ["renewal"])[0]


def run_combo(X, Y, target, mode):
    """fixed5 plus the stratified rate. offset: logit(fixed5) + logit(strat) - logit(train base), no learned weight.
    stack: a 2-coefficient logistic on the two in-sample logits (6 + cells + 3 parameters; said so in notes)."""
    cols = B.SIGNALS
    si = [cols.index(c) for c in STRAT_COLS]

    def lg(p):
        p = np.clip(p, 1e-4, 1 - 1e-4)
        return np.log(p / (1 - p))

    def fit(Xtr, ytr):
        mu, sd = C.zfit(Xtr)
        w = C.logistic_fit(C.zapply(Xtr, mu, sd), ytr)
        sm = strat_fit(Xtr[:, si], ytr)
        ws = None
        if mode == "stack":
            z = np.c_[lg(C.logistic_predict(C.zapply(Xtr, mu, sd), w)), lg(strat_predict(sm, Xtr[:, si], np.arange(len(Xtr))))]
            ws = C.logistic_fit(z, ytr)
        return (mu, sd, w, sm, ws)

    def predict(model, Xh, te):
        mu, sd, w, sm, ws = model
        pf = C.logistic_predict(C.zapply(Xh[te], mu, sd), w)
        ps = strat_predict(sm, Xh[te][:, si], np.arange(len(te)))
        if mode == "offset":
            return 1 / (1 + np.exp(-(lg(pf) + lg(ps) - lg(sm["base"]))))
        return C.logistic_predict(np.c_[lg(pf), lg(ps)], ws)
    pred, _ = C.walk_forward(X[cols], Y[target], fit, predict, label_lag_weeks=lag_of(target))
    return pred


# ------------------------------------------------------------------------------------------- Kaplan-Meier per stratum
def km_curve(times, events, hmax=104):
    """Survival S(h) for h = 0..hmax from integer times and event flags (1 = event, 0 = censored)."""
    S = np.ones(hmax + 1)
    times = np.asarray(times, float)
    events = np.asarray(events, float)
    s = 1.0
    for h in range(1, hmax + 1):
        at_risk = float((times >= h).sum())
        d = float(((times == h) & (events > 0.5)).sum())
        if at_risk > 0:
            s *= 1 - d / at_risk
        S[h] = s
    return S


def km_quantiles(S):
    out = {}
    for q, name in ((0.1, "w10"), (0.5, "w50"), (0.9, "w90")):
        hit = np.where(S <= 1 - q)[0]
        out[name] = int(hit[0]) if len(hit) else None
    return out


def km_spells(tte, cens, t, idx):
    """Point-in-time spells for rows idx (< t): event at tte if it happened by t, else censored at min(t - i, 104)."""
    i = np.asarray(idx)
    hit = (cens[i] == 0) & np.isfinite(tte[i]) & (i + tte[i] <= t)
    times = np.where(hit, tte[i], np.minimum(t - i, 104.0))
    return times, hit.astype(float)


def run_km(X, Y, start="2019-01-06", refit_weeks=13, lag_weeks=26, min_train=60):
    """Walk-forward 1 - S(26) per stratum (merged as the rate model at the same refit). Returns (pred, last_fit)."""
    idx = X.index
    Xs = X[STRAT_COLS].values.astype(float)
    y = Y["fall5_26w"].values.astype(float)
    tte, cens = Y["tte5"].values.astype(float), Y["cens5"].values.astype(float)
    pred = pd.Series(np.nan, index=idx)
    t = int(np.searchsorted(idx, pd.Timestamp(start)))
    last = None
    while t < len(idx):
        tr = np.arange(0, max(0, t - lag_weeks))
        tr = tr[np.isfinite(y[tr]) & np.isfinite(Xs[tr]).all(1)]
        te_end = min(t + refit_weeks, len(idx))
        if len(tr) >= min_train:
            sm = strat_fit(Xs[tr], y[tr])
            rows = np.arange(0, t)
            rows = rows[np.isfinite(Xs[rows]).all(1)]
            times, ev = km_spells(tte, cens, t, rows)
            key = sm["merged"][encode(Xs[rows], CUTS)]
            curves = {kk: km_curve(times[key == kk], ev[key == kk]) for kk in np.unique(key)}
            curves[200] = km_curve(times, ev)                      # global curve: the fallback for a key with no spells yet
            te = np.arange(t, te_end)
            te = te[np.isfinite(Xs[te]).all(1)]
            kte = sm["merged"][encode(Xs[te], CUTS)]
            pred.iloc[te] = [1 - curves[kk if kk in curves else 200][26] for kk in kte]
            last = {"t": idx[t], "curves": curves, "model": sm, "nSpells": int(len(rows)), "nEvents": int(ev.sum()),
                    "nLabelEpisodes": len(C.episodes(y[tr]))}
        t = te_end
    return pred, last


# ------------------------------------------------------------------------------------------- model registry
def run_model(kind, X, Y, target):
    binary = target != "y13"
    if kind == "fixed5":
        return B.run_fixed(X, Y, target, "W", binary)[0]
    if kind == "fixed5brief":
        return B.run_fixed(X, Y, target, "W", binary, FIXED5_BRIEF)[0]
    if kind == "m2only":
        return B.run_fixed(X, Y, target, "W", binary, ["m2_yoy"])[0]
    if kind == "m2eth":
        return B.run_fixed(X, Y, target, "W", binary, ["m2_yoy", "ethbtc_fromhi52w"])[0]
    if kind == "ethonly":
        return B.run_fixed(X, Y, target, "W", binary, ["ethbtc_fromhi52w"])[0]
    if kind == "clock":
        return B.run_fixed(X, Y, target, "W", binary, ["days_since_halving"])[0]
    if kind == "renewal":
        return run_renewal(X, Y, target)
    if kind == "eramean":
        return run_const(X, Y, target, last=104)
    if kind == "basetrain":
        return run_const(X, Y, target)
    if kind == "readiness":
        return run_readiness(X, Y, target)
    if kind == "strat":
        return run_strat(X, Y, target)[0]
    if kind == "strat_vol":
        return run_strat(X, Y, target, use_vol=True)[0]
    if kind == "strat_m2btc":
        return run_strat(X, Y, target, cols=STRAT_M2BTC)[0]
    if kind in ("offset", "stack"):
        return run_combo(X, Y, target, kind)
    raise ValueError(kind)


# ------------------------------------------------------------------------------------------- nulls (forked workers)
def perm_blocks(v):
    """Blocks of a binary label: each run of 1s and each stretch between runs (NaN counts as gap), as position arrays."""
    n = len(v)
    cuts = [0]
    for s, e in C.episodes(v):
        cuts += [s, e + 1]
    cuts = sorted(set(c for c in cuts if 0 <= c <= n)) + [n]
    return [np.arange(a, b) for a, b in zip(cuts[:-1], cuts[1:]) if b > a]


def era_positions(Y, era):
    name, fr, to = era
    return np.where((Y.index >= pd.Timestamp(fr)) & (Y.index < pd.Timestamp(to)))[0]


def apply_order(Y, pos, blocks, order):
    """Dwell-time null: inside the era's rows `pos`, reorder the label's episodes and gaps (`blocks`) by `order`; every
    target column is moved with the same row order so the targets stay aligned with each other."""
    ii = pos[np.concatenate([blocks[j] for j in order])]
    Ys = Y.copy()
    for c in Y.columns:
        v = Y[c].values.copy()
        v[pos] = v[ii]
        Ys[c] = v
    return Ys


def n_arrangements(nb):
    return math.factorial(nb)


def _null_job(a):
    kind, target, seed, n, era, method = a
    rng = np.random.default_rng(seed)
    X, Y, mask = _G["X"], _G["Y"], _G["mask"][target]
    key = era[0] if era else "pooled"

    def run(Ys):
        pred = run_model(kind, X, Ys, target).where(mask)
        return C.metrics(pred, Ys[target], True).get(key, {}).get("auc")
    if method in ("perm", "perm_all"):
        pos = era_positions(Y, era)
        blocks = perm_blocks(Y[target].values[pos])
        orders = list(itertools.permutations(range(len(blocks)))) if method == "perm_all" else [rng.permutation(len(blocks)) for _ in range(n)]
        vals = []
        for order in orders:
            v = run(apply_order(Y, pos, blocks, order))
            if v is not None:
                vals.append(float(v))
        return vals
    return C.shift_null(run, Y, n, rng)


def _surrogate_job(a):
    kind, which, seed, n = a
    rng = np.random.default_rng(seed)
    X, Y, P, mask = _G["X"], _G["Y"], _G["P"], _G["mask"]["fall5_26w"]
    b = P["BTC.D"].values.astype(float)
    out = []
    for _ in range(n):
        s = C.iaaft(b, rng, it=20) if which == "iaaft" else C.matched_rw(b, rng)
        Ps = P.copy()
        Ps["BTC.D"] = np.clip(s, 1.0, 99.0)
        Ys = C.extra_targets(Ps, C.targets(Ps, "W"), "W").reindex(X.index)
        pred = run_model(kind, X, Ys, "fall5_26w").where(mask)
        ev = Ys.loc[mask, "fall5_26w"].values
        v = C.metrics(pred, Ys["fall5_26w"], True).get("pooled", {}).get("auc")
        out.append({"auc": (None if v is None else float(v)), "base": round(float(np.nanmean(ev)), 3), "episodes": len(C.episodes(ev)),
                    "outOfBounds": bool(s.min() < 0 or s.max() > 100)})
    return out


def pooled_jobs(pool, jobs):
    out = {}
    res = pool.map(_fn_of(jobs[0]), [j[1] for j in jobs]) if pool else [_fn_of(j)(j[1]) for j in jobs]
    for (label, _), r in zip(jobs, res):
        out.setdefault(label, []).extend(r)
    return out


def _fn_of(job):
    return _surrogate_job if len(job[1]) == 4 else _null_job


# ------------------------------------------------------------------------------------------- evaluation helpers
def era_mask(index, era):
    return (index >= pd.Timestamp(era[1])) & (index < pd.Timestamp(era[2]))


def era_strat_auc(pred, y):
    """AUC over within-era pairs only (each era's AUC weighted by its number of positive x negative pairs), plus the
    plain mean of era AUCs. Removes the cross-era level ranking that the pooled AUC rewards."""
    num, den, per = 0.0, 0.0, []
    for era in C.ERAS:
        m = era_mask(pred.index, era) & pred.notna() & y.notna()
        yy = y[m].values
        n1, n0 = int((yy > 0.5).sum()), int((yy <= 0.5).sum())
        v = C.auc(pred[m].values, yy) if m.sum() >= 20 else None
        if v is not None:
            num += n1 * n0 * v
            den += n1 * n0
            per.append(v)
    return {"eraStratAuc": (round(num / den, 3) if den else None), "meanOfEraAuc": (round(float(np.mean(per)), 3) if per else None)}


def paired_block_boot(pa, pb, y, n, rng, block_weeks=26):
    """Paired circular block bootstrap of AUC(pa) - AUC(pb) on the common rows: pooled and per era."""
    out = {}
    for name, era in [("pooled", ("pooled", "2000-01-01", "2100-01-01"))] + [(e[0], e) for e in C.ERAS]:
        m = era_mask(pa.index, era) & pa.notna() & pb.notna() & y.notna()
        a, b, yy = pa[m].values, pb[m].values, y[m].values
        N = len(yy)
        if N < 20:
            continue
        bl = block_weeks
        diffs = []
        for _ in range(n):
            starts = rng.integers(0, N, size=int(np.ceil(N / bl)))
            ii = np.concatenate([(np.arange(s, s + bl) % N) for s in starts])[:N]
            va, vb = C.auc(a[ii], yy[ii]), C.auc(b[ii], yy[ii])
            if va is not None and vb is not None:
                diffs.append(va - vb)
        d = np.array(diffs)
        ra, rb = C.auc(a, yy), C.auc(b, yy)
        out[name] = {"diff": (None if ra is None or rb is None else round(ra - rb, 3)), "n": len(d),
                     "q05": (round(float(np.quantile(d, 0.05)), 3) if len(d) else None), "q50": (round(float(np.quantile(d, 0.5)), 3) if len(d) else None),
                     "q95": (round(float(np.quantile(d, 0.95)), 3) if len(d) else None), "pLE0": (round(float((d <= 0).mean()), 3) if len(d) else None)}
    return out


def episode_loo_runup(pred, y, runup=26):
    """Headline AUC with each positive episode AND its `runup` weeks removed (the blocks the episode bootstrap uses):
    pooled and per era."""
    p, yy = np.asarray(pred, float), np.asarray(y, float)
    m = np.isfinite(p) & np.isfinite(yy)
    eps = C.episodes(np.where(m, yy, np.nan))
    idx = pred.index
    out = {"pooled": {}, **{e[0]: {} for e in C.ERAS}}
    for s, e in eps:
        keep = m.copy()
        keep[max(0, s - runup):e + 1] = False
        key = f"{idx[s].date()}..{idx[e].date()}"
        out["pooled"][key] = (lambda v: None if v is None else round(v, 3))(C.auc(p[keep], yy[keep]))
        for era in C.ERAS:
            km = keep & era_mask(idx, era)
            v = C.auc(p[km], yy[km]) if km.sum() >= 20 else None
            out[era[0]][key] = (None if v is None else round(v, 3))
    vals = {k: v for k, v in out["pooled"].items() if v is not None}
    return {"pooled": out["pooled"], "byEra": {e[0]: out[e[0]] for e in C.ERAS}, "min": (min(vals.values()) if vals else None),
            "minEpisode": (min(vals, key=vals.get) if vals else None), "dropBigEpisode": {"pooled": out["pooled"].get(EP_BIG), "2021-2022": out["2021-2022"].get(EP_BIG)},
            "drop2025": {"pooled": out["pooled"].get(EP_2025), "2023-2026": out["2023-2026"].get(EP_2025)}}


def ceiling(pred, y, base_pred, fresh, onset, n_boot, rng):
    """Metrics by era with Brier vs the training-window base rate AND vs the era's own rate (an oracle climatology),
    era-stratified AUC, fresh-start AUC, onset AUC, bootstraps, episode LOO with and without the run-up.
    pred and base_pred are already on the common row mask, so every comparison is on the same rows."""
    met = C.metrics(pred, y, True, is_prob=True)
    bm = C.metrics(base_pred.where(pred.notna()), y, True, is_prob=True)
    for era, row in met.items():
        row["brierTrainBase"] = bm.get(era, {}).get("brier")
        row["brierOwnEra"] = row.pop("brierBase")
        row["skillVsTrainBase"] = (None if row["brierTrainBase"] in (None, 0) else round(1 - row["brier"] / row["brierTrainBase"], 3))
        row["skillVsOwnEra"] = (None if row["brierOwnEra"] in (None, 0) else round(1 - row["brier"] / row["brierOwnEra"], 3))
        row["beatsTrainBase"] = (row["brier"] is not None and row["brierTrainBase"] is not None and row["brier"] <= row["brierTrainBase"])
        row["beatsOwnEra"] = (row["brier"] is not None and row["brierOwnEra"] is not None and row["brier"] <= row["brierOwnEra"])
    fr = C.metrics(pred.where(fresh), y, True)
    on = C.metrics(pred, onset, True)
    loo = C.episode_loo(pred, y)
    return {"byEra": met, **era_strat_auc(pred, y), "fresh": {e: r.get("auc") for e, r in fr.items()}, "freshN": {e: r.get("n") for e, r in fr.items()},
            "onsetAuc": {e: r.get("auc") for e, r in on.items()},
            "blockBoot": C.block_boot(pred, y, n=n_boot, rng=rng), "episodeBoot": C.episode_boot(pred, y, n=n_boot, rng=rng),
            "episodeLOO": {"all": loo["all"], "nEpisodes": loo["nEpisodes"], "min": loo["min"], "minEpisode": loo["minEpisode"],
                           "dropBigEpisode": loo["perEpisode"].get(EP_BIG), "drop2025": loo["perEpisode"].get(EP_2025), "perEpisode": loo["perEpisode"]},
            "episodeLOOwithRunup": episode_loo_runup(pred, y)}


def era_auc(ce, era):
    return ce["byEra"].get(era, {}).get("auc")


def episode_counts(Y, idx_from="2019-01-01"):
    out = {}
    for tg in TARGETS_BIN + ["onset5_26w"] + EX_TARGETS:
        out[tg] = {}
        for name, fr, to in C.ERAS + [("pooled", idx_from, "2100-01-01")]:
            m = (Y.index >= pd.Timestamp(max(fr, idx_from))) & (Y.index < pd.Timestamp(to))
            v = Y.loc[m, tg].values
            out[tg][name] = {"n": int(np.isfinite(v).sum()), "pos": int(np.nansum(v)), "episodes": len(C.episodes(v))}
    return out


def last_train_rows(X, y, refit_date, lag):
    t = int(np.searchsorted(X.index, pd.Timestamp(refit_date)))
    tr = np.arange(0, max(0, t - lag))
    Xv, yv = X.values.astype(float), np.asarray(y, float)
    return tr[np.isfinite(yv[tr]) & np.isfinite(Xv[tr]).all(1)]


def today_interval(Xtr, ytr, xrow, n, rng, runup=26):
    """Episode bootstrap of today's stratified rate: resample training blocks (episodes with run-up, negative stretches)."""
    N = len(ytr)
    cuts = [0]
    for s, e in C.episodes(ytr):
        cuts += [max(0, s - runup), e + 1]
    cuts = sorted(set(c for c in cuts if 0 <= c <= N)) + [N]
    blocks = [np.arange(a, b) for a, b in zip(cuts[:-1], cuts[1:]) if b > a]
    vals = []
    for _ in range(n):
        ii = np.concatenate([blocks[j] for j in rng.integers(0, len(blocks), size=len(blocks))])
        sm = strat_fit(Xtr[ii], ytr[ii])
        vals.append(float(strat_predict(sm, xrow[None, :], np.array([0]))[0]))
    v = np.array(vals)
    return {"n": len(v), "nBlocks": len(blocks), "q05": round(float(np.quantile(v, 0.05)), 3), "q50": round(float(np.quantile(v, 0.5)), 3),
            "q95": round(float(np.quantile(v, 0.95)), 3)}


def weeks_to_decide(rate, p0=0.25, z=1.96, per_obs_weeks=26):
    """Independent 26-week outcomes needed for a normal-approximation test of rate vs p0 at p 0.05 (one effective
    observation per 26 weeks). Returns (observations, weeks) or None when the rate equals the base rate."""
    if rate is None or abs(rate - p0) < 0.005:
        return None
    m = int(np.ceil(z ** 2 * p0 * (1 - p0) / (rate - p0) ** 2))
    return {"effectiveObs": m, "weeks": m * per_obs_weeks, "years": round(m * per_obs_weeks / 52, 1)}


def cell_name(code):
    code = int(code) % 27
    m2, dd, eth = code // 9, (code // 3) % 3, code % 3
    return " | ".join([BUCKET_NAMES["m2_yoy"][m2], BUCKET_NAMES["btc_dd_ath"][dd], BUCKET_NAMES["ethbtc_fromhi52w"][eth]])


def fmt(x, d=3):
    return "na" if x is None else (f"{x:.{d}f}" if isinstance(x, float) else str(x))


def psum(real, vals, higher_is_better=True, exact=False):
    """null_summary with the realised draw count and a quotable flag (no p from fewer than MIN_DRAWS_FOR_P draws,
    unless the null was enumerated exactly)."""
    s = C.null_summary(real, vals, higher_is_better)
    s["quotable"] = bool(exact or s["n"] >= MIN_DRAWS_FOR_P)
    s["exact"] = bool(exact)
    if not s["quotable"]:
        s["note"] = f"{s['n']} draws: resolution 1/{max(1, s['n'])}, not a p-value"
    return s


def pfmt(s):
    return f"p{fmt(s.get('p'))}(n{s.get('n')}{'E' if s.get('exact') else ('' if s.get('quotable') else '!')})"


# ------------------------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--nulls", type=int, default=200)
    ap.add_argument("--fast", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    t0 = time.time()
    n_null, n_boot, n_surr, n_pert, n_within = a.nulls, 1000, 100, 10, 300
    n_comp = max(50, n_null // 2)
    if a.fast:
        n_null, n_boot, n_surr, n_pert, n_within, n_comp = min(a.nulls, 50), 200, 10, 10, 50, 50
        a.workers = min(a.workers, 2)
    rng = np.random.default_rng(81)
    now_utc = dt.datetime.now(dt.timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        now_et = now_utc.astimezone(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M ET")
    except Exception:
        now_et = "ET unavailable"
    say(f"study8_honest  run {now_utc.strftime('%Y-%m-%d %H:%M UTC')} / {now_et}  fast={a.fast} nulls strat {n_null} / comparator {n_comp} / within-era {n_within} boots {n_boot} surrogates {n_surr}")

    # ---- data (weekly, Sunday close); labels from complete bars only; evaluation on the common forecast rows
    D = C.load_daily(a.data)
    P_full = C.panel(D, "W")
    X_full, _ = C.features(P_full, "W")
    dd_harness = X_full["btc_dd_ath"].copy()
    X_full["btc_dd_ath"] = ath_drawdown(a.data, X_full.index)       # true ATH anchor (full BTCUSD history)
    keep = X_full.index >= pd.Timestamp("2016-06-01")
    X, P = X_full[keep], P_full[keep]
    provisional = X.index[X.index > TODAY]
    last_complete = X.index[X.index <= TODAY][-1]
    P_done = P[P.index <= last_complete]                             # complete Sunday closes only
    Y = C.extra_targets(P_done, C.targets(P_done, "W"), "W").reindex(X.index)
    fresh = C.fresh_mask(P, "W")
    dd_diff = (X["btc_dd_ath"] - dd_harness[keep]).abs()
    dd_rows = dd_diff[dd_diff > 1e-9]
    first_strat_row = X[STRAT_COLS].dropna().index[0]
    notes = [f"Last complete Sunday close {last_complete.date()}; bars {[str(d.date()) for d in provisional]} are provisional (partial week): labels are built from complete closes only, so the provisional bar is in no training set and no evaluation label.",
             f"Training labels for every model that uses ethbtc_fromhi52w (fixed5, m2eth, strat, strat_vol, offset, stack, km26) begin {first_strat_row.date()} (first finite ETH/BTC 52-week high): the Nov 2016 - May 2017 waterfall is outside every one of their fits; only its Dec 2017 tail is ever trained on. strat_m2btc (M2 x BTC drawdown, no ETH/BTC) trains from 2016-06 and is reported beside it.",
             "BTC.D 2016-18 is TradingView's back-computed series: training only; all metrics are on the common forecast rows (see firstForecast).",
             "M2 is the revised vintage with a 6-week publication lag; today's reading is shown with m2_yoy moved +/-1 point.",
             "tte5 spells: at each refit every spell open at the refit is censored there (no 104-week lag needed: nothing after the refit is read). The KM 1-S(26) is the SAME conditional rate as the stratified model in survival form (same cells, same rows), not an independent estimate; its effective events are label episodes, not spells.",
             "Stratum thresholds, the merge rule (nEp < 2 -> M2 bucket) and the Beta(1,3) prior are source constants fixed before this run; the cut points (M2 > 5%, BTC within 5% of ATH, ETH/BTC within 10%/30% of its high) were suggested by round 3's look at the three big waterfalls, one of which (Jan 2021) lies inside the evaluation window, so 'pre-registered' means fixed before this run, not chosen blind to the evaluation era; the threshold-perturbation decoy is the control.",
             "fixed5 (study8_baselines.SIGNALS) is round 7's most-picked set over refits through 2026 with btcd_fromhi52w swapped for btcusd_ret13w in the baselines module: a post-hoc comparator, not a pre-registered one; the brief's literal set is reported as fixed5brief.",
             "Bootstraps, episode lists and nulls run after all predictions are frozen; none feeds a fit.",
             "offset = logit(fixed5) + logit(strat) - logit(training base), no learned weight; stack = 2-coefficient logistic on in-sample logits (its fixed5 input is in-sample at fit time, so the stack weights lean to fixed5).",
             "Brier is reported against two references on the same rows: the walk-forward training-window base rate (what a forecaster could have used) and the era's own rate (an oracle climatology, not available in real time). A model that beats only the first is better than a stale constant, not calibrated to the era.",
             f"btc_dd_ath is rebuilt from the full BTCUSD history (weekly closes from 2013-02): {len(dd_rows)} rows differ from the harness column ({dd_rows.index.min().date() if len(dd_rows) else None}..{dd_rows.index.max().date() if len(dd_rows) else None}, max {dd_diff.max():.3f}); no walk-forward prediction changes (asserted in checks)."]
    _G.update({"X": X, "Y": Y, "P": P_done})
    epc = episode_counts(Y)
    say(f"rows {len(X)} eval-from 2019: fall5_26w pos {epc['fall5_26w']['pooled']['pos']} in {epc['fall5_26w']['pooled']['episodes']} episodes; "
        f"fall10_26w pos {epc['fall10_26w']['pooled']['pos']} in {epc['fall10_26w']['pooled']['episodes']} episode(s) "
        f"(2023-26: {epc['fall10_26w']['2023-2026']['pos']}); onset5_26w pos {epc['onset5_26w']['pooled']['pos']} in {epc['onset5_26w']['pooled']['episodes']}")

    # ---- predictions (all frozen before any bootstrap / null), then the common row mask per target
    preds = {}
    base_pred = {}
    refits_strat = None
    first_unmasked = {}
    for tg in TARGETS_BIN + EX_TARGETS:
        base_pred[tg] = run_model("basetrain", X, Y, tg)
        kinds = COMPARATORS if tg in TARGETS_BIN else ["fixed5", "strat", "offset"]
        for kind in kinds:
            if kind == "strat" and tg == "fall5_26w":
                preds[(kind, tg)], refits_strat = run_strat(X, Y, tg)
            else:
                preds[(kind, tg)] = run_model(kind, X, Y, tg)
            if tg == "fall5_26w":
                fv = preds[(kind, tg)].first_valid_index()
                first_unmasked[kind] = str(fv.date()) if fv is not None else None
    km_pred, km_last = run_km(X, Y)
    preds[("km26", "fall5_26w")] = km_pred
    level_pred, _ = C.walk_forward(X[STRAT_COLS], Y["fall5_26w"], lambda a, b: strat_fit(a, b), lambda m, Xh, te: m["level"][encode(Xh[te], m["cuts"])],
                                   label_lag_weeks=26)
    masks = {}
    for tg in TARGETS_BIN + EX_TARGETS:
        m = base_pred[tg].notna()
        for (kind, t2), p in preds.items():
            if t2 == tg and kind != "km26":
                m &= p.notna() | (X.index > last_complete)      # the provisional bar has no label anyway
        masks[tg] = m & (X.index >= pd.Timestamp("2019-01-01"))
        base_pred[tg] = base_pred[tg].where(masks[tg])
        for (kind, t2) in list(preds):
            if t2 == tg:
                preds[(kind, t2)] = preds[(kind, t2)].where(masks[tg])
    level_pred = level_pred.where(masks["fall5_26w"])
    _G["mask"] = masks
    first_forecast = str(masks["fall5_26w"][masks["fall5_26w"]].index[0].date())
    n_common = {tg: int(masks[tg].sum()) for tg in TARGETS_BIN}
    say(f"common forecast rows: first {first_forecast} (plan said 2019-01-06; the 2019-01-06 refit has only 54 rows with finite ETH/BTC features < min_train 60), "
        f"n fall5 {n_common['fall5_26w']} fall10 {n_common['fall10_26w']}; unmasked first forecast m2only/clock/eramean/strat_m2btc {first_unmasked['m2only']}, fixed5/strat {first_unmasked['fixed5']}")
    notes.append(f"Every metric is on the intersection of all comparators' forecast rows (first forecast {first_forecast}, n {n_common['fall5_26w']}); the 13 weeks 2019-01-06..2019-03-31 (all label 0) that m2only/clock/eramean could forecast are excluded for everyone, which lowers their 2019-20 AUC and raises the base-rate Brier there relative to a per-model row set.")
    level_share = {}
    for name, fr, to in C.ERAS + [("pooled", "2019-01-01", "2100-01-01")]:
        v = level_pred[(level_pred.index >= pd.Timestamp(fr)) & (level_pred.index < pd.Timestamp(to))].dropna()
        if len(v):
            level_share[name] = {"cell": round(float((v == 0).mean()), 3), "m2bucket": round(float((v == 1).mean()), 3), "global": round(float((v == 2).mean()), 3), "n": int(len(v))}
    y13 = {}
    for kind in ("fixed5", "m2only", "m2eth", "strat"):
        p = run_model(kind, X, Y, "y13")
        y13[kind] = C.metrics(p, Y["y13"], False)
    refit_dates = [r["t"] for r in refits_strat]

    # ---- evidence ceiling for every model
    ce = {}
    for (kind, tg), p in preds.items():
        ce[f"{kind}:{tg}"] = ceiling(p, Y[tg], base_pred[tg], fresh, Y["onset" + tg[4:]] if tg in TARGETS_BIN else Y["onset5_26w"], n_boot, rng)
    paired = {}
    for kind in COMPARATORS + ["km26"]:
        if kind != "fixed5":
            paired[kind] = paired_block_boot(preds[(kind, "fall5_26w")], preds[("fixed5", "fall5_26w")], Y["fall5_26w"], n_boot, rng)
    paired["m2eth_vs_m2only"] = paired_block_boot(preds[("m2eth", "fall5_26w")], preds[("m2only", "fall5_26w")], Y["fall5_26w"], n_boot, rng)
    say("-- fall5_26w: AUC 19-20/21-22/23-26/pooled/eraStrat | Brier<=trainBase | Brier<=ownEra | fresh | boot q05-q95 | LOO -big/-2025/min | LOO+runup -big(21-22)/-2025(23-26)")
    for kind in COMPARATORS + ["km26"]:
        c = ce[f"{kind}:fall5_26w"]
        e = c["byEra"]
        bb, lo, lr = c["blockBoot"], c["episodeLOO"], c["episodeLOOwithRunup"]
        say(f"{kind:11s} {fmt(era_auc(c, '2019-2020'))}/{fmt(era_auc(c, '2021-2022'))}/{fmt(era_auc(c, '2023-2026'))}/{fmt(era_auc(c, 'pooled'))}/{fmt(c['eraStratAuc'])} | "
            f"{''.join('Y' if e.get(k, {}).get('beatsTrainBase') else 'n' for k in ERA_NAMES)} | {''.join('Y' if e.get(k, {}).get('beatsOwnEra') else 'n' for k in ERA_NAMES)} | "
            f"{fmt(c['fresh'].get('pooled'))} | {fmt(bb.get('q05'))}-{fmt(bb.get('q95'))} | {fmt(lo['dropBigEpisode'])}/{fmt(lo['drop2025'])}/{fmt(lo['min'])} | "
            f"{fmt(lr['dropBigEpisode']['2021-2022'])}/{fmt(lr['drop2025']['2023-2026'])}")
    say("fall10_26w pooled AUC (ONE episode, a ranking of one event): " + "  ".join(f"{k} {fmt(era_auc(ce[f'{k}:fall10_26w'], 'pooled'))}" for k in COMPARATORS))
    say("paired block-boot AUC diff vs fixed5 (pooled diff [q05,q95] P(diff<=0); 21-22 diff): " + "  ".join(
        f"{k} {fmt(v['pooled']['diff'])}[{fmt(v['pooled']['q05'])},{fmt(v['pooled']['q95'])}]P{fmt(v['pooled']['pLE0'])};{fmt(v.get('2021-2022', {}).get('diff'))}"
        for k, v in paired.items() if k in ("m2only", "m2eth", "ethonly", "fixed5brief", "strat", "offset", "stack")) + f"  m2eth-m2only pooled {fmt(paired['m2eth_vs_m2only']['pooled']['diff'])} 21-22 {fmt(paired['m2eth_vs_m2only'].get('2021-2022', {}).get('diff'))}")
    say("strat forecast source share (cell / M2 bucket / global): " + "  ".join(f"{e} {v['cell']}/{v['m2bucket']}/{v['global']}" for e, v in level_share.items()))
    say("y13 IC/hit: " + "  ".join(f"{k} {fmt(v.get('pooled', {}).get('ic'))}/{fmt(v.get('pooled', {}).get('hit'))}" for k, v in y13.items())
        + "   exstable fall5/fall10 pooled AUC: " + "  ".join(f"{k} {fmt(era_auc(ce[f'{k}:exstable_fall5_26w'], 'pooled'))}/{fmt(era_auc(ce[f'{k}:exstable_fall10_26w'], 'pooled'))}" for k in ("fixed5", "strat", "offset")))
    # learned sign of ethbtc_fromhi52w inside fixed5 at every refit
    eth_signs = []
    for rf in refits_strat:
        trr = last_train_rows(X[B.SIGNALS], Y["fall5_26w"], rf["t"], 26)
        A = X[B.SIGNALS].values[trr]
        mu, sd = C.zfit(A)
        w = C.logistic_fit(C.zapply(A, mu, sd), Y["fall5_26w"].values[trr])
        eth_signs.append(float(w[1 + B.SIGNALS.index("ethbtc_fromhi52w")]))
    eth_sign = {"min": round(min(eth_signs), 2), "max": round(max(eth_signs), 2), "negativeAt": int(sum(s < 0 for s in eth_signs)), "refits": len(eth_signs)}

    # ---- nulls: shifted targets (pooled), dwell-time block permutation within each era and pooled, surrogates, perturbation
    ctx = get_context("fork")
    workers = max(1, min(a.workers, os.cpu_count() or 1))
    jobs = []
    seed = 1000
    for kind in NULL_MODELS:
        for tg in TARGETS_BIN:
            nn = n_null if kind == "strat" else n_comp
            per = int(np.ceil(nn / workers))
            for w in range(workers):
                jobs.append((f"shift:{kind}:{tg}", (kind, tg, seed, per, None, "shift")))
                seed += 1
    perm_eras = C.ERAS + [("pooled", "2019-01-01", "2100-01-01")]
    arrangements = {}
    for era in perm_eras:
        nb = len(perm_blocks(Y["fall5_26w"].values[era_positions(Y, era)]))
        exact = n_arrangements(nb) <= max(n_within, ENUMERATE_UP_TO)
        arrangements[era[0]] = {"blocks": nb, "distinctArrangements": (n_arrangements(nb) if nb <= 20 else f"{nb}!"), "enumerated": exact}
    for kind in WITHIN_MODELS:
        for era in perm_eras:
            if era[0] == "pooled" and kind not in PERM_POOLED_MODELS:
                continue
            if arrangements[era[0]]["enumerated"]:
                jobs.append((f"perm:{kind}:{era[0]}", (kind, "fall5_26w", seed, 0, era, "perm_all")))
                seed += 1
                continue
            per = int(np.ceil(n_within / workers))
            for w in range(workers):
                jobs.append((f"perm:{kind}:{era[0]}", (kind, "fall5_26w", seed, per, era, "perm")))
                seed += 1
    sjobs = []
    for kind in ("strat", "fixed5"):
        for which in ("iaaft", "rw"):
            per = int(np.ceil(n_surr / workers))
            for w in range(workers):
                sjobs.append((f"surr:{kind}:{which}", (kind, which, seed, per)))
                seed += 1
    pool = ctx.Pool(workers) if workers > 1 else None
    try:
        null_raw = pooled_jobs(pool, jobs)
        surr_raw = pooled_jobs(pool, sjobs)
    finally:
        if pool:
            pool.close()
            pool.join()
    null = {}
    for kind in NULL_MODELS:
        for tg in TARGETS_BIN:
            null[f"{kind}:{tg}"] = psum(era_auc(ce[f"{kind}:{tg}"], "pooled"), null_raw[f"shift:{kind}:{tg}"])
    within = {}
    for kind in WITHIN_MODELS:
        within[kind] = {}
        for era in perm_eras:
            if f"perm:{kind}:{era[0]}" in null_raw:
                within[kind][era[0]] = psum(era_auc(ce[f"{kind}:fall5_26w"], era[0]), null_raw[f"perm:{kind}:{era[0]}"], exact=arrangements[era[0]]["enumerated"])
    # reference: the circular-shift within-era null (shift range 26..n-26) on frozen predictions, to show its bias below 0.5
    circ_ref = {}
    for kind in ("fixed5", "m2only"):
        circ_ref[kind] = {}
        p = preds[(kind, "fall5_26w")]
        for era in C.ERAS:
            m = era_mask(p.index, era) & p.notna() & Y["fall5_26w"].notna()
            pv, yv = p[m].values, Y["fall5_26w"][m].values
            n = len(yv)
            if n <= 52:
                continue
            v = [C.auc(pv, np.roll(yv, int(rng.integers(26, n - 26)))) for _ in range(300)]
            v = [x for x in v if x is not None]
            circ_ref[kind][era[0]] = {"nullMedian": round(float(np.median(v)), 3), "nullP95": round(float(np.quantile(v, 0.95)), 3), "n": len(v)}
    placebo = {}
    for kind in ("strat", "fixed5"):
        for which in ("iaaft", "rw"):
            draws = surr_raw[f"surr:{kind}:{which}"]
            valid = [d for d in draws if d["auc"] is not None]
            matched = [d for d in valid if PLACEBO_MATCH["episodes"][0] <= d["episodes"] <= PLACEBO_MATCH["episodes"][1] and PLACEBO_MATCH["base"][0] <= d["base"] <= PLACEBO_MATCH["base"][1]]
            real = era_auc(ce[f"{kind}:fall5_26w"], "pooled")
            placebo[f"{kind}:{which}"] = {"drawn": len(draws), "validAuc": len(valid), "matchedLabelProcess": len(matched), "outOfBounds": int(sum(d["outOfBounds"] for d in draws)),
                                          "baseQ": ([round(float(q), 3) for q in np.quantile([d["base"] for d in draws], [0, 0.5, 1])] if draws else None),
                                          "episodesQ": ([int(q) for q in np.quantile([d["episodes"] for d in draws], [0, 0.5, 1])] if draws else None),
                                          "allValid": psum(real, [d["auc"] for d in valid]), "matched": psum(real, [d["auc"] for d in matched])}
    pert = []
    for j in range(n_pert):
        u = rng.uniform(0.5, 1.5, size=3)
        cuts = {"m2_yoy": (0.0, 0.05 * u[0]), "btc_dd_ath": tuple(np.array(CUTS["btc_dd_ath"]) * u[1]), "ethbtc_fromhi52w": tuple(np.array(CUTS["ethbtc_fromhi52w"]) * u[2])}
        p, _ = run_strat(X, Y, "fall5_26w", cuts=cuts)
        pert.append({"scale": [round(float(x), 3) for x in u], "auc": C.metrics(p.where(masks["fall5_26w"]), Y["fall5_26w"], True).get("pooled", {}).get("auc")})
    real_auc = era_auc(ce["strat:fall5_26w"], "pooled")
    pert_aucs = [q["auc"] for q in pert if q["auc"] is not None]
    pert_rank = 1 + sum(v > real_auc for v in pert_aucs)
    say("shifted-target null (pooled AUC real, p95, p(n draws; ! = fewer than 50, not a p-value)): " + "  ".join(f"{k} {fmt(null[f'{k}:fall5_26w']['real'])}/{fmt(null[f'{k}:fall5_26w'].get('nullP95'))} {pfmt(null[f'{k}:fall5_26w'])}" for k in ("strat", "fixed5", "m2only", "m2eth", "ethonly", "clock", "renewal", "offset", "stack")))
    say("fall10_26w null p: " + "  ".join(f"{k} {pfmt(null[f'{k}:fall10_26w'])}" for k in ("strat", "fixed5", "m2only", "clock", "renewal", "offset")))
    say("within-era DWELL-TIME PERMUTATION null (episodes and gaps reordered, whole procedure rerun); blocks/arrangements(E = all enumerated, exact p): " + "  ".join(f"{e} {v['blocks']}/{v['distinctArrangements']}{'E' if v['enumerated'] else ''}" for e, v in arrangements.items()))
    for kind in WITHIN_MODELS:
        say(f"  perm {kind:8s}: " + "  ".join(f"{e[0]} auc {fmt(within[kind][e[0]].get('real'))} med {fmt(within[kind][e[0]].get('nullMedian'))} p95 {fmt(within[kind][e[0]].get('nullP95'))} {pfmt(within[kind][e[0]])}" for e in perm_eras if e[0] in within[kind]))
    say("  reference: the plan's circular-shift within-era null (26..n-26) on frozen preds has medians " + "  ".join(f"{k} " + "/".join(fmt(circ_ref[k][e].get("nullMedian")) for e in ERA_NAMES if e in circ_ref[k]) for k in circ_ref) + " (biased below 0.5: a 52-week roll of a half-positive era anti-aligns the label), so it is not used")
    say("surrogate BTC.D (targets rebuilt) pooled AUC: drawn/valid/matched-label-process, out-of-bounds, label base q0/50/100, episodes q0/50/100, p95 over matched: " + "  ".join(
        f"{k} {v['drawn']}/{v['validAuc']}/{v['matchedLabelProcess']} oob {v['outOfBounds']} base {v['baseQ']} ep {v['episodesQ']} p95 {fmt(v['matched'].get('nullP95'))}{'' if v['matched']['quotable'] else '!'}" for k, v in placebo.items()))
    say(f"threshold perturbation: pre-registered set ranks {pert_rank} of {len(pert_aucs) + 1} (AUC {fmt(real_auc)}; perturbed median {fmt(float(np.median(pert_aucs)) if pert_aucs else None)}); ethbtc_fromhi52w weight in fixed5 negative at {eth_sign['negativeAt']}/{eth_sign['refits']} refits ({eth_sign['min']}..{eth_sign['max']})")

    # ---- claims (pre-registered, as written) and the corrected decoy set
    f5, st = ce["fixed5:fall5_26w"], ce["strat:fall5_26w"]
    bb = f5["blockBoot"]
    claimA = {"stratPooledAuc": era_auc(st, "pooled"), "fixed5Band": [bb.get("q05"), bb.get("q95")],
              "insideBand": bool(bb.get("q05") is not None and bb["q05"] <= era_auc(st, "pooled") <= bb["q95"]),
              "stratBrierBeatsTrainBaseAllEras": all(st["byEra"].get(e, {}).get("beatsTrainBase", False) for e in ERA_NAMES),
              "stratBrierBeatsOwnEraAllEras": all(st["byEra"].get(e, {}).get("beatsOwnEra", False) for e in ERA_NAMES),
              "pairedVsFixed5": paired["strat"]["pooled"]}
    claimA["pass"] = claimA["insideBand"] and claimA["stratBrierBeatsTrainBaseAllEras"]
    decoy_auc = {}
    for d in ("clock", "renewal", "eramean"):
        decoy_auc[d] = {e: era_auc(ce[f"{d}:fall5_26w"], e) for e in ERA_NAMES}
    decoy_auc["eramean_flipped"] = {e: (None if v is None else round(max(v, 1 - v), 3)) for e, v in decoy_auc["eramean"].items()}   # bound for a sign-learning recency decoy
    close = {}
    for d in decoy_auc:
        close[d] = sum(1 for e in ERA_NAMES if decoy_auc[d][e] is not None and era_auc(f5, e) is not None and decoy_auc[d][e] >= era_auc(f5, e) - 0.05)
    fixed5_loo_big = f5["episodeLOO"]["dropBigEpisode"]
    claimB = {"decoyWithin0.05InEras": close, "fixed5PooledWithoutBigEpisode": fixed5_loo_big,
              "skepticWinsAsWritten": bool(max(close["clock"], close["eramean"]) >= 2 and fixed5_loo_big is not None and fixed5_loo_big < 0.75),
              "skepticWinsCorrectedDecoys": bool(max(close.values()) >= 2 and fixed5_loo_big is not None and fixed5_loo_big < 0.75)}
    beats = {k: {e: bool(within[k][e].get("real") is not None and within[k][e].get("nullP95") is not None and within[k][e]["real"] > within[k][e]["nullP95"]) for e in ERA_NAMES} for k in WITHIN_MODELS}
    claimC = {"beatsWithinEraPermP95": beats, "skepticWins": not any(v["2019-2020"] and v["2023-2026"] for v in beats.values()),
              "null": "dwell-time block permutation within the era, whole procedure rerun (the plan's circular shift is biased below 0.5 and is reported only as a reference)"}
    margin_written = {e: min((era_auc(f5, e) or 0) - (decoy_auc[d][e] or 0) for d in ("clock", "eramean")) for e in ERA_NAMES}
    margin_corr = {e: min((era_auc(f5, e) or 0) - (decoy_auc[d][e] or 0) for d in ("clock", "renewal", "eramean_flipped")) for e in ERA_NAMES}
    strong = {"fixed5AucWithoutBigEpisode>=0.85": bool(fixed5_loo_big is not None and fixed5_loo_big >= 0.85),
              "beatsDecoysBy0.10EveryEra": all(v >= 0.10 for v in margin_corr.values()),
              "decoyMarginsAsWritten": {k: round(v, 3) for k, v in margin_written.items()}, "decoyMarginsCorrected": {k: round(v, 3) for k, v in margin_corr.items()},
              "clearsWithinEraP95in1920and2326": bool(beats["fixed5"]["2019-2020"] and beats["fixed5"]["2023-2026"])}
    strong["pass"] = all(v for k, v in strong.items() if not k.startswith("decoyMargins"))
    honest_claim = ("M2 x ETH/BTC x BTC drawdown is a real two-condition forecaster (all three strong tests pass)" if strong["pass"]
                    else "base rate plus readiness, with intervals (the strong test fails: " + ", ".join(k for k, v in strong.items() if not k.startswith("decoyMargins") and not v) + ")")
    say(f"claim A (strat inside fixed5 band {claimA['fixed5Band']} and Brier<=trainBase all eras): {'PASS' if claimA['pass'] else 'FAIL'} "
        f"(auc {fmt(claimA['stratPooledAuc'])}, inside {claimA['insideBand']}, brier<=trainBase {claimA['stratBrierBeatsTrainBaseAllEras']}, <=ownEra {claimA['stratBrierBeatsOwnEraAllEras']}; paired diff vs fixed5 {fmt(paired['strat']['pooled']['diff'])} P(<=0) {fmt(paired['strat']['pooled']['pLE0'])})")
    say(f"claim B skeptic (decoy within 0.05 of fixed5 in >=2 eras: {close}; fixed5 w/o big episode {fmt(fixed5_loo_big)} < 0.75): as written {'SKEPTIC WINS' if claimB['skepticWinsAsWritten'] else 'not met'}, corrected decoys {'SKEPTIC WINS' if claimB['skepticWinsCorrectedDecoys'] else 'not met'}")
    say(f"claim C skeptic (no model beats within-era permutation p95 in both 19-20 and 23-26): {'SKEPTIC WINS' if claimC['skepticWins'] else 'not met'}; beats both: {[k for k, v in beats.items() if v['2019-2020'] and v['2023-2026']]}")
    say(f"strong test for fixed5: {strong}")
    say(f"HONEST CLAIM: {honest_claim}")

    # ---- duration block (daily events, 5 / 10 / 25 points from 2016) vs uniform(14, 182)
    Pd = C.panel(D, "D")
    bd = Pd["BTC.D"][(Pd.index >= pd.Timestamp("2016-01-01")) & (Pd.index <= last_complete)]
    duration = {}
    for k in (5, 10, 25):
        ev = C.events(bd, float(k), freq="D")
        days = np.array([e["days"] for e in ev], float)
        row = {"n": len(ev), "events": [{"peak": str(e["peak"].date()), "days": e["days"], "points": round(e["from"] - e["to"], 1)} for e in ev]}
        if len(days) >= 2:
            bs = np.array([np.quantile(rng.choice(days, len(days)), [0.1, 0.5, 0.9]) for _ in range(n_boot)])
            un = np.array([np.quantile(rng.uniform(14, 182, len(days)), [0.1, 0.5, 0.9]) for _ in range(n_boot)])
            row["q10_50_90"] = [round(float(q), 1) for q in np.quantile(days, [0.1, 0.5, 0.9])]
            row["bootQ50_of_q10_50_90"] = [round(float(q), 1) for q in np.median(bs, 0)]
            row["boot90band_median"] = [round(float(q), 1) for q in np.quantile(bs[:, 1], [0.05, 0.95])]
            row["uniform14_182_q10_50_90"] = [round(float(q), 1) for q in np.median(un, 0)]
            row["uniform90band_median"] = [round(float(q), 1) for q in np.quantile(un[:, 1], [0.05, 0.95])]
            cdf = np.sort(days)
            ks = float(np.max(np.abs(np.arange(1, len(days) + 1) / len(days) - np.clip((cdf - 14) / 168, 0, 1))))
            ks_null = [float(np.max(np.abs(np.arange(1, len(days) + 1) / len(days) - np.sort(rng.uniform(0, 1, len(days)))))) for _ in range(n_boot)]
            row["ksVsUniform"] = {"stat": round(ks, 3), "p": round(float(np.mean(np.array(ks_null) >= ks)), 3)}
        duration[f"fall{k}"] = row
    d5 = duration["fall5"]
    say(f"duration (daily events from 2016): 5pt n={d5['n']} days q10/50/90 {d5.get('q10_50_90')} median 90% band {d5.get('boot90band_median')} vs uniform(14,182) {d5.get('uniform14_182_q10_50_90')} band {d5.get('uniform90band_median')} KS p {d5.get('ksVsUniform', {}).get('p')}; "
        f"10pt n={duration['fall10']['n']} {duration['fall10'].get('q10_50_90')}; 25pt n={duration['fall25']['n']} {[e['days'] for e in duration['fall25']['events']]}")

    # ---- falsifiers (calendar), pass / fail / not-yet with numbers, on complete closes
    bw = P_done["BTC.D"]
    after = bw[bw.index >= HIGHER_HIGH_FROM]
    hh = float(after.max())
    ev5w = C.events(bw, 5.0, freq="W")
    last5 = ev5w[-1] if ev5w else None
    ev10w = C.events(bw, 10.0, freq="W")
    last10 = ev10w[-1] if ev10w else None
    post_trough_hi = float(bw[bw.index > last5["trough"]].max()) if last5 is not None else None
    new_fall_pts = (post_trough_hi - float(bw.loc[last_complete])) if post_trough_hi is not None else None
    falsifiers = {
        "i_higherHighAbove65.7": {"status": "FAIL (thesis falsified for this cycle)" if hh > JUN2025_PEAK else "not-yet", "maxWeeklyCloseSince2025-06-29": round(hh, 2), "date": str(after.idxmax().date()), "threshold": JUN2025_PEAK},
        "ii_engineImminentSinceFeb2023": {"status": ("not-yet" if TODAY < FALSIFIER_DATE else "FAIL"), "deadline": str(FALSIFIER_DATE.date()), "daysToDeadline": int((FALSIFIER_DATE - TODAY).days),
                                          "last10ptFallPeak": (str(last10["peak"].date()) if last10 else None), "weeksEngineHasSaidImminent": int((TODAY - pd.Timestamp("2023-02-01")).days // 7),
                                          "note": "the engine's current mapping is read from docs/FRACTAL.md (10 Dec 2017 week since Feb 2023); this module records only the calendar and the falls"},
        "iii_nextFallWhileEngineFit<0.8": {"status": "not-yet", "last5ptFall": ({"peak": str(last5["peak"].date()), "trough": str(last5["trough"].date()), "days": last5["days"]} if last5 else None),
                                           "postTroughHigh": (round(post_trough_hi, 2) if post_trough_hi is not None else None), "pointsBelowPostTroughHigh": (round(new_fall_pts, 2) if new_fall_pts is not None else None),
                                           "newFallStarted": bool(new_fall_pts is not None and new_fall_pts >= 5.0),
                                           "note": "not identifiable here: needs the engine's live fit and lead window at the start of the next 5+ fall; this module records whether such a fall has started"}}
    say(f"falsifiers: (i) {falsifiers['i_higherHighAbove65.7']['status']} max close since Jun-2025 {hh:.1f} vs 65.7; (ii) {falsifiers['ii_engineImminentSinceFeb2023']['status']} {falsifiers['ii_engineImminentSinceFeb2023']['daysToDeadline']} days to 2027-11-02, engine 'imminent' {falsifiers['ii_engineImminentSinceFeb2023']['weeksEngineHasSaidImminent']} weeks; "
        f"(iii) {falsifiers['iii_nextFallWhileEngineFit<0.8']['status']} last 5pt fall {last5['peak'].date() if last5 else None}->{last5['trough'].date() if last5 else None}, now {fmt(new_fall_pts, 1)} pts under post-trough high")

    # ---- today
    tr_last = last_train_rows(X[STRAT_COLS], Y["fall5_26w"], refit_dates[-1], 26)
    Xs = X[STRAT_COLS].values.astype(float)
    sm = strat_fit(Xs[tr_last], Y["fall5_26w"].values[tr_last])
    sm10 = strat_fit(Xs[tr_last], Y["fall10_26w"].values[tr_last])
    xrow = Xs[X.index.get_loc(last_complete)]
    code = int(encode(xrow[None, :], CUTS)[0])
    key = int(sm["merged"][code])
    curve = km_last["curves"].get(key) if km_last else None
    kmq = km_quantiles(curve) if curve is not None else {}
    tint = today_interval(Xs[tr_last], Y["fall5_26w"].values[tr_last], xrow, n_boot, rng)
    cell_stats = {"n": int(sm["n"][code]), "k": int(sm["k"][code]), "nEp": int(sm["nEp"][code]), "level": ["cell", "m2bucket", "global"][int(sm["level"][code])],
                  "n_used": int(sm["n"][code] if sm["level"][code] == 0 else (sm["n_m2"][m2_of(code)] if sm["level"][code] == 1 else sm["nTrain"])),
                  "nEp_used": int(sm["nEp"][code] if sm["level"][code] == 0 else (sm["nEp_m2"][m2_of(code)] if sm["level"][code] == 1 else sm["nEp_g"]))}
    # covariate support of the rows the reading comes from (the merged key's training rows)
    used_rows = tr_last[sm["merged"][encode(Xs[tr_last], CUTS)] == key]
    support = {}
    out_of_support = []
    for j, c in enumerate(STRAT_COLS):
        v = Xs[used_rows, j]
        inside = bool(v.min() <= xrow[j] <= v.max())
        support[c] = {"min": round(float(v.min()), 4), "max": round(float(v.max()), 4), "today": round(float(xrow[j]), 4), "inSupport": inside}
        if not inside:
            out_of_support.append(c)
    yr = pd.Series(Y["fall5_26w"].values[used_rows], index=X.index[used_rows])
    support["rowsDates"] = [str(X.index[used_rows[0]].date()), str(X.index[used_rows[-1]].date())]
    support["labelMeanByYear"] = {int(k): round(float(v), 2) for k, v in yr.groupby(yr.index.year).mean().items()}
    support["rowsByYear"] = {int(k): int(v) for k, v in yr.groupby(yr.index.year).size().items()}
    support["outOfSupport"] = out_of_support
    today_rate = float(sm["rate"][code])
    comp_today = {}
    for (kind, tg), p in preds.items():
        v = p.get(last_complete)
        comp_today[f"{kind}:{tg}"] = (round(float(v), 4) if v is not None and np.isfinite(v) else None)
    comp_today["basetrain:fall5_26w"] = round(float(base_pred["fall5_26w"].get(last_complete)), 4)
    fresh_base = float(Y.loc[(Y.index >= "2019-01-01") & fresh, "fall5_26w"].mean())
    sens = {"stratAdjacent": {}}
    for j, c in enumerate(STRAT_COLS):
        cur = int(bucket(xrow[j:j + 1], CUTS[c])[0])
        for nb in (cur - 1, cur + 1):
            if 0 <= nb <= 2:
                alt = code + (nb - cur) * (9 if j == 0 else (3 if j == 1 else 1))
                sens["stratAdjacent"][f"{c}->{BUCKET_NAMES[c][nb]}"] = round(float(sm["rate"][alt]), 3)
    Xf = X[B.SIGNALS]
    trf = last_train_rows(Xf, Y["fall5_26w"], refit_dates[-1], 26)
    xf = Xf.loc[last_complete].values.astype(float)

    def fixed5_today(cols_idx, shift=None):
        A = Xf.values[trf][:, cols_idx]
        mu, sd = C.zfit(A)
        w = C.logistic_fit(C.zapply(A, mu, sd), Y["fall5_26w"].values[trf])
        z = C.zapply(xf[cols_idx][None, :], mu, sd)
        if shift is not None:
            z = z + shift
        return float(C.logistic_predict(z, w)[0])
    allc = list(range(len(B.SIGNALS)))
    sens["fixed5Drop"] = {B.SIGNALS[j]: round(fixed5_today([i for i in allc if i != j]), 4) for j in allc}
    sens["fixed5Pm1sd"] = {}
    for j in allc:
        sh = np.zeros((1, len(allc)))
        sh[0, j] = 1.0
        sens["fixed5Pm1sd"][B.SIGNALS[j]] = [round(fixed5_today(allc, -sh), 4), round(fixed5_today(allc, sh), 4)]
    m2i = B.SIGNALS.index("m2_yoy")
    sens["m2pm1pt"] = {}
    for d in (-0.01, 0.01):
        xr2 = xrow.copy()
        xr2[0] += d
        xf2 = xf.copy()
        xf2[m2i] += d
        A = Xf.values[trf]
        mu, sd = C.zfit(A)
        w = C.logistic_fit(C.zapply(A, mu, sd), Y["fall5_26w"].values[trf])
        sens["m2pm1pt"][f"{d:+.2f}"] = {"strat": round(float(sm["rate"][int(encode(xr2[None, :], CUTS)[0])]), 3), "fixed5": round(float(C.logistic_predict(C.zapply(xf2[None, :], mu, sd), w)[0]), 4)}
    skip = ("readiness", "basetrain")
    spec_all = {k: v for k, v in comp_today.items() if k.endswith(":fall5_26w") and v is not None and not k.startswith(skip)}
    strat_like = ("strat:", "strat_vol:", "km26:")       # readings that come from today's stratum cell
    spec_in = {k: v for k, v in spec_all.items() if not (out_of_support and k.startswith(strat_like))}
    today = {"asOf": str(last_complete.date()), "provisionalBars": [str(d.date()) for d in provisional],
             "btcd": round(float(P.loc[last_complete, "BTC.D"]), 2), "btcd_exstable": round(float(Y.loc[last_complete, "btcd_exstable"]), 2),
             "inputs": {c: round(float(X.loc[last_complete, c]), 4) for c in STRAT_COLS + [VOL_COL, "usdtd_vsma30w", "btcusd_ret13w"]},
             "fresh": bool(fresh.loc[last_complete]), "readinessOn": bool(preds[("readiness", "fall5_26w")].get(last_complete, 0) > 0),
             "stratum": {"code": code, "name": cell_name(code), **cell_stats, "rate": round(today_rate, 3), "rate10": round(float(sm10["rate"][code]), 3),
                         "episodeBoot90": tint, "support": support, "extrapolation": bool(out_of_support),
                         "kmWeeksToFirst5ptFall": kmq, "kmP26": (round(float(1 - curve[26]), 3) if curve is not None else None),
                         "kmSpells": (km_last["nSpells"] if km_last else None), "kmEvents": (km_last["nEvents"] if km_last else None), "kmLabelEpisodesInTraining": (km_last["nLabelEpisodes"] if km_last else None)},
             "comparators": comp_today, "trainBase": comp_today["basetrain:fall5_26w"], "freshBase2019on": round(fresh_base, 3),
             "spreadFall5_26w_allSpecs": [round(min(spec_all.values()), 4), round(max(spec_all.values()), 4)] if spec_all else None,
             "spreadFall5_26w_inSupport": [round(min(spec_in.values()), 4), round(max(spec_in.values()), 4)] if spec_in else None,
             "headline": {"spread": [round(min(spec_in.values()), 4), round(max(spec_in.values()), 4)] if spec_in else None, "stratInterval90": [tint["q05"], tint["q95"]],
                          "freshBase": round(fresh_base, 3), "note": "the stratified point (and its KM / vol variants) is an extrapolation outside its cell's M2 support and enters only through its interval" if out_of_support else "all specifications in support"},
             "sensitivity": sens, "weeksToDecide": {"strat": weeks_to_decide(today_rate), "fixed5": weeks_to_decide(comp_today.get("fixed5:fall5_26w"))},
             "provisionalReading": {k: (round(float(run_model(k, X, Y, "fall5_26w").iloc[-1]), 4) if len(provisional) else None) for k in ("strat", "fixed5", "offset")}}
    say(f"TODAY {today['asOf']} BTC.D {today['btcd']} (ex-stable {today['btcd_exstable']}) m2 {today['inputs']['m2_yoy']:+.3f} btc_dd {today['inputs']['btc_dd_ath']:+.3f} eth_fromhi {today['inputs']['ethbtc_fromhi52w']:+.3f} fresh {today['fresh']} readiness {today['readinessOn']}")
    say(f"stratum [{cell_name(code)}] level {cell_stats['level']} n {cell_stats['n']} k {cell_stats['k']} nEp {cell_stats['nEp']} (used n {cell_stats['n_used']} nEp {cell_stats['nEp_used']}): P(5+ in 26w) {today_rate:.3f} 90% episode-boot [{tint['q05']}, {tint['q95']}]; P(10+) {today['stratum']['rate10']:.3f}; KM w10/50/90 {kmq} P26 {today['stratum']['kmP26']} (same cell, same rows)")
    say(f"  support of that cell: rows {support['rowsDates'][0]}..{support['rowsDates'][1]} label mean by year {support['labelMeanByYear']}; " + "; ".join(f"{c} [{support[c]['min']:.3f},{support[c]['max']:.3f}] today {support[c]['today']:.3f}{'' if support[c]['inSupport'] else ' OUT'}" for c in STRAT_COLS)
        + (f" -> EXTRAPOLATION ({', '.join(out_of_support)} outside the cell's range)" if out_of_support else ""))
    say("comparators P(5+ in 26w): " + "  ".join(f"{k} {fmt(comp_today.get(f'{k}:fall5_26w'), 3)}" for k in ("fixed5", "fixed5brief", "m2only", "m2eth", "ethonly", "clock", "renewal", "eramean", "strat", "strat_vol", "strat_m2btc", "offset", "stack", "km26")) + f"  trainBase {today['trainBase']:.3f} freshBase {fresh_base:.3f}")
    say(f"HEADLINE P(5+ pt fall in 26w): in-support specifications {today['headline']['spread'][0]:.3f} .. {today['headline']['spread'][1]:.3f} (all specs {today['spreadFall5_26w_allSpecs'][0]:.3f} .. {today['spreadFall5_26w_allSpecs'][1]:.3f}); stratified 90% interval [{tint['q05']}, {tint['q95']}]; fresh base {fresh_base:.3f}; weeks to separate strat from 25%: {today['weeksToDecide']['strat']}; fixed5: {today['weeksToDecide']['fixed5']}")
    say(f"sensitivity strat adjacent bucket: {sens['stratAdjacent']}; m2 +/-1pt: {sens['m2pm1pt']}; fixed5 drop-one: {sens['fixed5Drop']}; +/-1sd: {sens['fixed5Pm1sd']}")

    # ---- cheap checks: truncation test, refit jumps, parameter count, ATH anchor invariance, readiness record
    Pf = P_full

    def strat_series_at(end_pos):
        Xt, _ = C.features(Pf.iloc[:end_pos + 1], "W")
        Xt["btc_dd_ath"] = ath_drawdown(a.data, Xt.index)
        v = Xt[STRAT_COLS].values.astype(float)
        ok = np.isfinite(v).all(1)
        out = np.full(len(Pf), np.nan)
        out[:end_pos + 1][ok] = encode(v[ok], CUTS)
        return out
    trunc = C.truncation_test(strat_series_at, len(Pf), n=20, rng=rng)
    jumps = C.refit_jump_report(preds[("strat", "fall5_26w")], refit_dates)
    params = {"strat": C.params_report(sm["cellsInUse"], epc["fall5_26w"]["pooled"]["episodes"]), "fixed5": C.params_report(6, epc["fall5_26w"]["pooled"]["episodes"]),
              "stack": C.params_report(6 + sm["cellsInUse"] + 3, epc["fall5_26w"]["pooled"]["episodes"])}
    Xh = X.copy()
    Xh["btc_dd_ath"] = dd_harness[keep]
    anchor = {}
    for kind in ("fixed5", "strat", "m2eth", "offset"):
        ph = run_model(kind, Xh, Y, "fall5_26w").where(masks["fall5_26w"])
        anchor[kind] = round(float(np.nanmax(np.abs(ph - preds[(kind, "fall5_26w")]))), 6)
    ready = {}
    for nm, col in (("harnessAnchor2014", Xh["btc_dd_ath"]), ("trueAnchor2013", X["btc_dd_ath"])):
        r = ((col >= np.log(0.95)) & (X["m2_yoy"] > 0))
        ready[nm] = {"firedAtBigEventPeaks": {e: bool(r.get(pd.Timestamp(e), False)) for e in C.BIG_EVENTS}, "drawdownAtPeaks": {e: round(float(col.get(pd.Timestamp(e), np.nan)), 3) for e in C.BIG_EVENTS}}
    say(f"checks: truncation ok {trunc['ok']} (maxAbsDiff {trunc['maxAbsDiff']:.2e}, {trunc['tested']} points); strat jump at refit {jumps['maxJumpAtRefit']} vs elsewhere {jumps['maxJumpElsewhere']}; "
        f"params strat {sm['cellsInUse']} cells / fixed5 6 / stack {6 + sm['cellsInUse'] + 3} vs 12 episodes; ATH-anchor max |pred diff| {anchor}; readiness fired at big-event peaks true-anchor {sum(ready['trueAnchor2013']['firedAtBigEventPeaks'].values())}/3 (harness {sum(ready['harnessAnchor2014']['firedAtBigEventPeaks'].values())}/3)")
    if params["stack"]["parameters"] > 12:
        notes.append("stack has more parameters than label episodes (" + str(params["stack"]["parameters"]) + " vs 12).")
    if sm["cellsInUse"] > 12:
        notes.append("stratified model has more cells in use than label episodes.")
    if not trunc["ok"]:
        notes.append("TRUNCATION TEST FAILED: stratum series depends on the future.")
    if max(anchor.values()) > 1e-9:
        notes.append(f"ATH ANCHOR CHANGES PREDICTIONS: {anchor}")
    nfired = sum(ready["trueAnchor2013"]["firedAtBigEventPeaks"].values())
    notes.append(f"Readiness rule (BTC within 5% of ATH and M2 y/y > 0): with the ATH anchored on the full BTCUSD history it fired at {nfired} of the 3 big-waterfall peak weeks "
                 f"(drawdowns {ready['trueAnchor2013']['drawdownAtPeaks']}); the brief's 3-of-3 record came from the harness anchor at April 2014 ({ready['harnessAnchor2014']['drawdownAtPeaks']}). "
                 "Its 2019+ precision (54% on / 22% off) is unchanged because no 2019+ row differs. The 'readiness' leg of the honest claim is therefore a 2-of-3 record on three events.")
    for e in ERA_NAMES:
        r = f5["byEra"].get(e, {})
        if r and not r.get("beatsOwnEra"):
            notes.append(f"fixed5 loses to the era's own rate on Brier in {e} (brier {r.get('brier')} vs own-era {r.get('brierOwnEra')}, skill {r.get('skillVsOwnEra')}): it beats the training-window base there ({r.get('brierTrainBase')}) only because that constant is stale; mis-calibrated in the era holding the only big event." if e == "2021-2022"
                         else f"fixed5 loses to the era's own rate on Brier in {e} (skill {r.get('skillVsOwnEra')}).")
    for kind in ("strat", "offset", "stack", "m2eth", "m2only", "fixed5brief"):
        pr = paired[kind]["pooled"]
        notes.append(f"{kind} vs fixed5 pooled AUC: paired 26-week block-bootstrap difference {pr['diff']:+.3f} [{pr['q05']}, {pr['q95']}], P(diff<=0) {pr['pLE0']}"
                     + ("; a tie (band contains 0)." if pr["q05"] is not None and pr["q05"] <= 0 <= pr["q95"] else "; the band excludes 0.")
                     + (" By era: " + ", ".join(f"{e} {paired[kind][e]['diff']:+.3f} [{paired[kind][e]['q05']}, {paired[kind][e]['q95']}]" for e in ERA_NAMES if e in paired[kind]) if kind in ("m2only", "m2eth") else ""))
    notes.append(f"fixed5's increment over M2 is ethbtc_fromhi52w (fixed5 vs m2eth paired diff {paired['m2eth']['pooled']['diff']:+.3f} [{paired['m2eth']['pooled']['q05']}, {paired['m2eth']['pooled']['q95']}]: tie; drop-one at today's refit shows the other three signals are passengers), "
                 f"with a NEGATIVE learned weight at {eth_sign['negativeAt']}/{eth_sign['refits']} refits ({eth_sign['min']}..{eth_sign['max']}): ETH/BTC far below its 52-week high -> higher P(fall), the opposite sign of the brief's readiness precursor (ETH/BTC up 61% before each big start). "
                 f"m2eth minus m2only in 2021-22: {paired['m2eth_vs_m2only'].get('2021-2022', {}).get('diff')}; ethbtc alone pooled AUC {fmt(era_auc(ce['ethonly:fall5_26w'], 'pooled'))}, 2019-20 {fmt(era_auc(ce['ethonly:fall5_26w'], '2019-2020'))}. The increment is sign-unstable across eras and its 2023-26 share is the single Apr-Jul 2025 episode.")
    notes.append(f"Duration: {d5['n']} daily 5+ point falls since 2016 last {d5.get('q10_50_90')} days (q10/50/90); the 10-point and 25-point counts from the shared events() are {duration['fall10']['n']} and {duration['fall25']['n']} (the 2016-17 waterfall is a 13.7-point event at the 26-week window).")
    notes.append("fall10_26w is one episode (Oct 2020 - May 2021, none since 2023): every fall10 AUC is a ranking of one event.")
    kmc = ce["km26:fall5_26w"]
    notes.append(f"km26 (per-stratum KM 1-S(26)) scores pooled {fmt(era_auc(kmc, 'pooled'))}, by era {fmt(era_auc(kmc, '2019-2020'))}/{fmt(era_auc(kmc, '2021-2022'))}/{fmt(era_auc(kmc, '2023-2026'))}, era-stratified {fmt(kmc['eraStratAuc'])}. "
                 "The implementer's run reported 0.810 pooled / 0.670 in 2023-26: its 'global' fallback curve was the KM over the spells of cells that had themselves been merged to global (a subset), and a stratum with no such spell got NaN. "
                 "The fallback consistent with the rate model (the KM over ALL spells, as the global rate is over all training rows) is used now; it changes every global-level forecast (about a quarter of all rows, a third of 2023-26) and the KM collapses in 2023-26 exactly as the stratified rate does. "
                 "The 0.81 was an artefact of an inconsistent fallback, not a second, more data-efficient estimate.")
    lr5 = f5["episodeLOOwithRunup"]
    notes.append(f"Episode LOO with the 26-week run-up removed (the blocks the episode bootstrap uses): fixed5 pooled without Oct 2020 - May 2021 + run-up {lr5['dropBigEpisode']['pooled']}, 2021-22 {lr5['dropBigEpisode']['2021-2022']} (plain LOO, positives only: {f5['episodeLOO']['dropBigEpisode']}); "
                 f"without Apr-Jul 2025 + run-up the 2023-26 era has NO positive left (the Nov 2024 single-week episode lies inside that run-up), so the 2023-26 AUC of every model is one episode: {lr5['drop2025']['2023-2026']}.")
    notes.append(f"Within-era permutation null for fixed5 in 2023-26: {within['fixed5']['2023-2026']}; with {arrangements['2023-2026']['distinctArrangements']} arrangements the smallest attainable p is {1 / arrangements['2023-2026']['distinctArrangements']:.3f}, and the real AUC clears p95 by {(within['fixed5']['2023-2026'].get('real') or 0) - (within['fixed5']['2023-2026'].get('nullP95') or 0):+.3f}.")
    ls = level_share.get("2023-2026", {})
    notes.append(f"Stratified model: pooled AUC {fmt(era_auc(st, 'pooled'))} but era-stratified (within-era pairs only) {fmt(st['eraStratAuc'])}: its ranking is cross-era level only. In 2023-26 AUC {fmt(era_auc(st, '2023-2026'))}; {ls.get('m2bucket', 0) + ls.get('global', 0):.0%} of its forecasts there came from a merged M2 bucket or the global rate "
                 "(the M2<0 state of 2023 had no training episode at all, so it was scored at the global rate while nothing happened; the Apr-Jul 2025 fall came in a cell rated near the bucket floor). That is era inheritance made visible, not a forecast. "
                 f"KM 1-S(26): pooled {fmt(era_auc(ce['km26:fall5_26w'], 'pooled'))}, era-stratified {fmt(ce['km26:fall5_26w']['eraStratAuc'])}.")
    notes.append(f"Surrogate BTC.D placebos are reported with their rebuilt label's base rate and episode count per draw: the shared matched_rw leaves [0, 100] in most draws (clipped at 99) and its labels have the wrong base rate and episode count, IAAFT labels have about twice the real episode count; only draws whose label process is within 2x of the real one (episodes {PLACEBO_MATCH['episodes']}, base {PLACEBO_MATCH['base']}) count, and no p95 is quoted from fewer than {MIN_DRAWS_FOR_P} such draws. No 'surrogate ceiling' is claimed: for models without a BTC.D-derived input the shifted-target null already is the label-process placebo.")
    notes.append(f"Within-era nulls are dwell-time block permutations of each era's label (episodes and gaps reordered, whole procedure rerun; arrangements {arrangements}); the plan's circular shift restricted to 26..n-26 anti-aligns a half-positive era (frozen-prediction medians {circ_ref}) and is not used. "
                 + "fixed5 beats the permutation p95: " + ", ".join(f"{e} {beats['fixed5'][e]} (p {within['fixed5'][e].get('p')}, n {within['fixed5'][e].get('n')})" for e in ERA_NAMES) + "; m2eth: " + ", ".join(f"{e} {beats['m2eth'][e]}" for e in ERA_NAMES) + "; m2only: " + ", ".join(f"{e} {beats['m2only'][e]}" for e in ERA_NAMES)
                 + ". The 2023-26 era has 5 blocks (120 arrangements): its p rests on where the single Apr-Jul 2025 episode lands in the ranking.")
    notes.append(f"Decoys: the era-mean decoy (mean of the last 104 known labels) is anti-predictive by construction (AUC {decoy_auc['eramean']}), so claim B and the strong-test margins are also computed against its sign-flipped bound ({decoy_auc['eramean_flipped']}) and against a renewal clock (log weeks since the last known positive label, sign learned through the logistic: {decoy_auc['renewal']}); margins as written {strong['decoyMarginsAsWritten']}, corrected {strong['decoyMarginsCorrected']}. The strong test fails on the 2021-22 halving-clock margin either way.")
    notes.append(f"Null draw counts are printed beside every p (n!, i.e. fewer than {MIN_DRAWS_FOR_P}, means resolution 1/n, not a p-value); quote only the full run's p-values. Surrogate draws dropped for an undefined AUC are counted (drawn/valid/matched).")
    if out_of_support:
        notes.append(f"TODAY'S STRATIFIED READING IS AN EXTRAPOLATION: {', '.join(out_of_support)} lies outside the range of the {len(used_rows)} training rows of its cell ({support['rowsDates'][0]}..{support['rowsDates'][1]}, label mean by year {support['labelMeanByYear']}); the headline spread uses the in-support specifications and the stratified rate enters only through its 90% episode-bootstrap interval {[tint['q05'], tint['q95']]}.")
    if _LINES[1]:
        notes.append(f"{_LINES[1]} summary lines were dropped by the 60-line cap.")

    # ---- charts (optional)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        os.makedirs(a.out, exist_ok=True)
        fig, ax = plt.subplots(2, 1, figsize=(12, 7), sharex=True)
        s = preds[("strat", "fall5_26w")].dropna()
        ax[0].plot(s.index, s.values, label="stratified rate", lw=1.2)
        ax[0].plot(preds[("fixed5", "fall5_26w")].dropna().index, preds[("fixed5", "fall5_26w")].dropna().values, label="fixed5", lw=0.8)
        ax[0].plot(km_pred.dropna().index, km_pred.dropna().values, label="KM 1-S(26)", lw=0.8)
        yy = Y["fall5_26w"].reindex(s.index)
        ax[0].fill_between(s.index, 0, yy.values, step="mid", alpha=0.15, color="k", label="fall5_26w label")
        for d in refit_dates:
            ax[0].axvline(pd.Timestamp(d), color="grey", lw=0.3, alpha=0.5)
        ax[0].legend(loc="upper right", fontsize=8)
        ax[0].set_title("P(5+ point BTC.D fall within 26 weeks), walk-forward on the common rows; grey = refit dates")
        ax[1].plot(P.index, P["BTC.D"], lw=0.8, color="k")
        ax[1].set_ylabel("BTC.D")
        fig.tight_layout()
        fig.savefig(os.path.join(a.out, "honest_fall5_26w.png"), dpi=110)
        plt.close(fig)
    except Exception as ex:  # charts are optional
        notes.append(f"chart skipped: {ex}")

    # ---- results.json
    oos = {}
    for key, c in ce.items():
        oos[key] = {"byEra": c["byEra"], "eraStratAuc": c["eraStratAuc"], "meanOfEraAuc": c["meanOfEraAuc"], "freshAuc": c["fresh"], "freshN": c["freshN"], "onsetAuc": c["onsetAuc"]}
    oos["y13"] = y13
    oos["episodeCounts"] = epc
    oos["stratForecastSourceShare"] = level_share
    oos["firstForecast"] = {"common": first_forecast, "unmaskedByModel": first_unmasked, "nCommonRows": n_common, "firstTrainingRowWithEthbtc": str(first_strat_row.date())}
    oos["pairedVsFixed5"] = paired
    oos["ethbtcWeightInFixed5"] = eth_sign
    km_table = {}
    if km_last:
        for kk, cv in km_last["curves"].items():
            km_table[cell_name(kk) if kk < 100 else (f"m2bucket:{BUCKET_NAMES['m2_yoy'][kk - 100]}" if kk < 200 else "global")] = {**km_quantiles(cv), "p26": round(float(1 - cv[26]), 3)}
    last_rates = {cell_name(c): {"rate": round(float(sm["rate"][c]), 3), "level": ["cell", "m2bucket", "global"][int(sm["level"][c])], "n": int(sm["n"][c]), "k": int(sm["k"][c]), "nEp": int(sm["nEp"][c])}
                  for c in range(27) if sm["n"][c] > 0}
    res = {"module": "study8_honest", "runUtc": now_utc.strftime("%Y-%m-%d %H:%M UTC"), "runEt": now_et, "fast": a.fast, "runtimeSec": round(time.time() - t0, 1),
           "oos": oos,
           "null": {"shifted": null, "withinEra": within, "withinEraMethod": claimC["null"], "withinEraArrangements": arrangements, "withinEraCircularFrozenReference": circ_ref,
                    "nNull": n_null, "nComparator": n_comp, "nWithinEra": n_within, "minDrawsForP": MIN_DRAWS_FOR_P},
           "today": today,
           "series": {"strat_fall5_26w": C.thin(preds[("strat", "fall5_26w")]), "strat_fall10_26w": C.thin(preds[("strat", "fall10_26w")]),
                      "fixed5_fall5_26w": C.thin(preds[("fixed5", "fall5_26w")]), "fixed5_fall10_26w": C.thin(preds[("fixed5", "fall10_26w")]),
                      "offset_fall5_26w": C.thin(preds[("offset", "fall5_26w")]), "offset_fall10_26w": C.thin(preds[("offset", "fall10_26w")]),
                      "km26": C.thin(km_pred), "basetrain_fall5_26w": C.thin(base_pred["fall5_26w"]), "strat_level": C.thin(level_pred, digits=0),
                      "stratum_code": C.thin(pd.Series(encode(Xs, CUTS).astype(float), index=X.index).where(np.isfinite(Xs).all(1)), digits=0)},
           "duration": duration, "placebo": placebo, "thresholdPerturbation": {"runs": pert, "rankOfPreregistered": pert_rank, "of": len(pert_aucs) + 1},
           "falsifiers": falsifiers,
           "evidence_ceiling": {"blockBoot": {k: c["blockBoot"] for k, c in ce.items()}, "episodeBoot": {k: c["episodeBoot"] for k, c in ce.items()},
                                "episodeLOO": {k: c["episodeLOO"] for k, c in ce.items()}, "episodeLOOwithRunup": {k: c["episodeLOOwithRunup"] for k, c in ce.items()},
                                "decoys": decoy_auc, "paired": paired,
                                "withinEra": within, "fresh": {k: c["fresh"] for k, c in ce.items()}},
           "claims": {"A": claimA, "B": claimB, "C": claimC, "strongTestFixed5": strong, "honestClaim": honest_claim},
           "stratifiedModelLastRefit": {"refit": refit_dates[-1], "nTrain": sm["nTrain"], "cellsInUse": sm["cellsInUse"], "cells": last_rates, "m2bucketRates": [round(float(v), 3) for v in sm["rate_m2"]], "globalRate": round(float(sm["rate_g"]), 3), "km": km_table},
           "checks": {"truncation": trunc, "refitJumps": jumps, "params": params, "refits": len(refit_dates), "athAnchorMaxPredDiff": anchor, "readinessRule": ready,
                      "btcDdAthRowsChanged": int(len(dd_rows)), "printedLines": _LINES[0], "droppedLines": _LINES[1]},
           "comparator": {"fixed5": B.SIGNALS, "fixed5brief": FIXED5_BRIEF, "source": "study8_baselines.run_fixed"}, "notes": notes}
    C.write_results(a.out, res)
    say(f"wrote {os.path.join(a.out, 'results.json')} in {time.time() - t0:.0f}s ({now_utc.strftime('%H:%M UTC')} / {now_et})")


if __name__ == "__main__":
    main()
