#!/usr/bin/env python3
"""Round 9 module [1] candidates: three additions to fixed5 under the dynamics rule (ROUND9_PLAN.md section [1]).

Question. Does any of the three things round 8 flagged add forecast content to fixed5 (study8_baselines.SIGNALS) for a
5+ point BTC.D fall within 26 weeks, under the condition in which it seemed to work, or is each of them era structure,
continuation credit or selection?

Candidates (fixed before the run; none added after):
  C1 gated halving clock: gate = BTC within 5% of its TRUE all-time high on weekly closes (study8_honest.ath_drawdown, full
     BTCUSD history) AND M2 y/y > 0 (6-week publication lag); terms gate, gate x sin(phase), gate x cos(phase), phase =
     2 pi x days_since_halving / 1460; the un-gated sin/cos version beside it so the gate's effect is a paired comparison.
  C2 BTC.D vol ratio: log(trailing 13-week realized vol of weekly logit increments / trailing 52-week realized vol), both
     ending at t; its sign at every refit and its marginal AUC at daily scale (study8_multiscale.scale_features btcd_vr at
     s = 5, 21 days) and weekly (13 w) on the same rows.
  C3 USDT.D -> BTC.D Levy area over 26 weeks, exactly as study8_tda_sig defines it (level_panel, trailing_stats,
     sig_window imported; not redefined).

Design. Weekly panel from study8_common (features, targets, walk_forward: expanding window, refit 13 weeks, labels withheld
26 weeks, min_train 60), first forecast the first date every comparator can forecast, scored on the common rows. Models:
fixed5; fixed5 + C1 (gated, un-gated); fixed5 + C2; fixed5 + C3; fixed5 + all three; the three pairs (for the interaction
check); each candidate alone. Everything pooled, by era, era-stratified (within-era pairs only), on fresh-start rows, and
Brier against the training-window base rate by era; paired differences against fixed5 with 26-week block-bootstrap and
episode-bootstrap bands. The four pre-registered success criteria, the adversary (decoy clocks, shifted targets through the
whole procedure, within-era dwell-time permutation of episodes and gaps through the whole procedure, matched-random-walk
decoy features, episode leave-one-out with run-up, joint-vs-sum-of-parts), the leakage checks and the today block are
evaluated as written in the plan.

  python3 research/btcd_fractal/study9_candidates.py --data research/btcd_fractal/data --out research/btcd_fractal/out9/candidates [--nulls N] [--fast]

Point in time. Every fitted object (z-scores, logistic weights, training base rate) is fitted on the training window of its
refit only; labels enter training 26 weeks after their row; every candidate feature of row t is a function of closes <= t
(rolling windows end at t; the Levy area uses increments t-25..t and trailing stats ending at t; the ATH is a running max);
the partial current week is excluded from the panel altogether (no feature, no label, no reading). Nulls, bootstraps and
the LOO run after all predictions are frozen and feed no fit. The truncation test rebuilds the whole pipeline on the daily
panel cut at 20 random Sundays and asserts features and predictions are unchanged. No network; aggregates only.
"""
import argparse
import datetime as dt
import itertools
import math
import os
import sys
import time
from multiprocessing import get_context

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")  # one BLAS thread per process: the Pool workers must not oversubscribe the cores

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import study8_common as C  # noqa: E402
from study8_baselines import SIGNALS  # noqa: E402
import study8_honest as H  # noqa: E402  (ath_drawdown, dwell-time permutation null, era_strat_auc, paired_block_boot, episode_loo_runup, run_const, psum)
import study8_tda_sig as T  # noqa: E402  (level_panel, trailing_stats, sig_window = the Levy area; paired_episode_boot, paired_boot)
import study8_multiscale as M  # noqa: E402  (levels, scale_features: the sigma-unit vol ratio btcd_vr at daily scale)

# ------------------------------------------------------------------------------------------- pre-registered constants
TARGET = "fall5_26w"
SIDE_TARGETS = [("fall10_26w", True), ("y13", False)]
PERIOD_DAYS = 1460.0
GATE_DD = np.log(0.95)                      # BTC within 5% of its all-time high
ANCHOR_LO, ANCHOR_HI = "2009-01-01", "2016-12-31"   # decoy clock anchors, uniform
W_AREA = T.W_W                              # 26 weeks
VR_SHORT, VR_LONG = 13, 52
VR_DAILY_SCALES = (5, 21)
VR_ROUND8_SCALE = 91                        # the scale at which round 8 reported the transfer (diagnostic row only; not a candidate)
DATA_CUT = "2016-06-01"
EVAL_FROM = "2019-01-01"
RUNUP = 26
C1G = ["gate", "gate_sin", "gate_cos"]
C1U = ["clk_sin", "clk_cos"]
C2 = ["vr13_52w"]
C3 = ["area_usdtd_btcd"]
SPECS = {"fixed5": SIGNALS,
         "fixed5+C1g": SIGNALS + C1G, "fixed5+C1u": SIGNALS + C1U, "fixed5+C2": SIGNALS + C2, "fixed5+C3": SIGNALS + C3,
         "fixed5+all3": SIGNALS + C1G + C2 + C3,
         "fixed5+C1g+C2": SIGNALS + C1G + C2, "fixed5+C1g+C3": SIGNALS + C1G + C3, "fixed5+C2+C3": SIGNALS + C2 + C3,
         "C1g": C1G, "C1u": C1U, "C2": C2, "C3": C3}
CANDS = ["fixed5+C1g", "fixed5+C1u", "fixed5+C2", "fixed5+C3", "fixed5+all3"]
PAIRS = {"fixed5+C1g+C2": ("fixed5+C1g", "fixed5+C2"), "fixed5+C1g+C3": ("fixed5+C1g", "fixed5+C3"), "fixed5+C2+C3": ("fixed5+C2", "fixed5+C3")}
NULL_SPECS = ["fixed5"] + CANDS
CLOCK_SPECS = {"fixed5+C1g": SIGNALS + C1G, "fixed5+C1u": SIGNALS + C1U, "C1g": C1G, "C1u": C1U}
MIN_DRAWS = H.MIN_DRAWS_FOR_P              # 50: no p-value or p95 quoted from fewer draws
ENUM_UP_TO = H.ENUMERATE_UP_TO             # 120: eras with this many block arrangements or fewer are enumerated exactly
CRIT_GAIN, CRIT_ERA_DROP, CRIT_P = 0.03, -0.02, 0.05
ERA_NAMES = [e[0] for e in C.ERAS]
POOLED_ERA = ("pooled", EVAL_FROM, "2100-01-01")

_G = {}
_LINES = [0, 0]


def say(s):
    if _LINES[0] < 60:
        print(s)
        _LINES[0] += 1
    else:
        _LINES[1] += 1


def fmt(x, d=3):
    if x is None:
        return "na"
    if isinstance(x, (bool, np.bool_)):
        return str(bool(x))
    return f"{x:.{d}f}"


# ------------------------------------------------------------------------------------------- candidate features
def vol_ratio(P):
    """C2: log(13-week realized vol / 52-week realized vol) of weekly BTC.D logit increments, both windows ending at t."""
    d = C.level(P, "BTC.D").diff()
    return np.log(d.rolling(VR_SHORT).std() / d.rolling(VR_LONG).std()).replace([np.inf, -np.inf], np.nan)


def levy_area(L):
    """C3: the 26-week depth-2 Levy area between USDT.D (logit, from 2017-07) and BTC.D (logit), scaled by the product of
    the trailing 104-bar increment sds, through study8_tda_sig.sig_window (A[0, 1] > 0: USDT.D moves first, BTC.D follows).
    Row t uses increments t-W+1..t and trailing stats ending at t, as study8_tda_sig.extra_features does."""
    dX = L.diff()
    _, sd = T.trailing_stats(dX, T.MINP["W"])
    v, s = dX.values, sd.values
    out = np.full(len(L), np.nan)
    for t in range(W_AREA, len(L)):
        win, sd_t = v[t - W_AREA + 1:t + 1], s[t]
        if np.isfinite(win).all() and np.isfinite(sd_t).all() and (sd_t > 0).all():
            A, _, _ = T.sig_window(win, sd_t, want_run=False)
            out[t] = A[0, 1]
    return pd.Series(out, index=L.index)


def clock_cols(index, days, gate, prefix_g="gate", prefix_u="clk"):
    ph = 2 * np.pi * np.asarray(days, float) / PERIOD_DAYS
    s, c = np.sin(ph), np.cos(ph)
    g = np.asarray(gate, float)
    return pd.DataFrame({prefix_g: g, prefix_g + "_sin": g * s, prefix_g + "_cos": g * c, prefix_u + "_sin": s, prefix_u + "_cos": c}, index=index)


def candidate_frame(P, X, L):
    """fixed5 + the candidate terms on the weekly panel (X already carries the true-ATH btc_dd_ath)."""
    F = X[SIGNALS + ["days_since_halving"]].copy()
    gate = ((X["btc_dd_ath"] >= GATE_DD) & (X["m2_yoy"] > 0)).astype(float)
    F = pd.concat([F, clock_cols(X.index, X["days_since_halving"].values, gate.values)], axis=1)
    F[C2[0]] = vol_ratio(P).values
    F[C3[0]] = levy_area(L).values
    return F


def decoy_clock_cols(F, anchor):
    """A strictly periodic clock (period 1460 days) from one anchor; the real clock restarts at each halving (intervals
    1411 / 1419 / 1440 days), so a decoy differs from it by a phase offset plus the restart gaps, never by structure."""
    days = (F.index - pd.Timestamp(anchor)).days % int(PERIOD_DAYS)
    return clock_cols(F.index, days, F["gate"].values)


def perm_positions(Y, era):
    """Rows of an era that carry a label: the dwell-time permutation reorders episodes and gaps among these only, so the
    unlabelled 26-week tail (and any other NaN) stays where it is and the null is scored on the real run's rows."""
    pos = H.era_positions(Y, era)
    return pos[np.isfinite(Y[TARGET].values[pos])]


def build_all(D, data_dir, last_complete):
    """The whole feature / target pipeline from the daily panel (used for the main run and for the truncation test)."""
    P_full = C.panel(D, "W")
    X_full, _ = C.features(P_full, "W")
    dd_harness = X_full["btc_dd_ath"].copy()
    X_full["btc_dd_ath"] = H.ath_drawdown(data_dir, X_full.index)
    keep = (X_full.index >= pd.Timestamp(DATA_CUT)) & (X_full.index <= last_complete)
    X, P = X_full[keep], P_full[keep]
    Y = C.targets(P, "W")
    L = T.level_panel(P, ["USDT.D", "BTC.D"])
    F = candidate_frame(P, X, L)
    return X, P, Y, F, dd_harness[keep]


# ------------------------------------------------------------------------------------------- harness wrapper
def run_spec(F, Y, cols, target=TARGET, binary=True, keep_models=None):
    """Mirrors study8_baselines.run_fixed (same scaler, same logistic / ridge, same label lag) and keeps the fitted
    (mu, sd, w) of every refit when asked (for the C2 sign-at-every-refit report and today's spread)."""
    def fit(Xtr, ytr):
        mu, sd = C.zfit(Xtr)
        w = C.logistic_fit(C.zapply(Xtr, mu, sd), ytr) if binary else C.ridge_fit(C.zapply(Xtr, mu, sd), ytr)
        if keep_models is not None:
            keep_models.append((mu, sd, w))
        return (mu, sd, w)

    def predict(model, Xh, te):
        mu, sd, w = model
        Z = C.zapply(Xh[te], mu, sd)
        return C.logistic_predict(Z, w) if binary else C.ridge_predict(Z, w)
    lag = 26 if "26w" in target else 13
    return C.walk_forward(F[cols], Y[target], fit, predict, freq="W", label_lag_weeks=lag)


def pooled_auc(pred, y):
    return C.metrics(pred, y, True).get("pooled", {}).get("auc")


def era_auc_of(pred, y, era):
    return C.metrics(pred, y, True, eras=[era]).get(era[0], {}).get("auc")


# ------------------------------------------------------------------------------------------- forked null workers
def _job(args):
    kind = args[0]
    F, Y, mask = _G["F"], _G["Y"], _G["mask"]
    out = []
    if kind == "shift":
        _, seed, n = args
        rng = np.random.default_rng(seed)
        lo = C.bars(26, "W")
        for _ in range(n):
            k = int(rng.integers(lo, len(Y) - lo))
            Ys = C.shift_targets(Y, k)
            row = {}
            for spec in NULL_SPECS:
                p, _ = run_spec(F, Ys, SPECS[spec])
                row[spec] = pooled_auc(p.where(mask), Ys[TARGET])
            out.append(row)
    elif kind == "perm":
        _, era, orders = args
        pos = perm_positions(Y, era)
        blocks = H.perm_blocks(Y[TARGET].values[pos])
        for order in orders:
            Ys = H.apply_order(Y, pos, blocks, order)
            row = {}
            for spec in NULL_SPECS:
                p, _ = run_spec(F, Ys, SPECS[spec])
                row[spec] = era_auc_of(p.where(mask), Ys[TARGET], era)
            out.append(row)
    elif kind == "clock":
        _, anchors = args
        real = _G["clockPreds"]
        for anchor in anchors:
            Fd = pd.concat([F[SIGNALS], decoy_clock_cols(F, anchor)], axis=1)
            row = {"anchor": str(pd.Timestamp(anchor).date())}
            for spec, cols in CLOCK_SPECS.items():
                p, _ = run_spec(Fd, Y, cols)
                p = p.where(mask)
                row[spec] = {"pooled": pooled_auc(p, Y[TARGET]), "2021-2022": era_auc_of(p, Y[TARGET], C.ERAS[1]), "strat": H.era_strat_auc(p, Y[TARGET])["eraStratAuc"],
                             "spearmanVsReal": C.spearman(p.values, real[spec].values)}
            out.append(row)
    elif kind == "dfeat":
        _, which, seeds = args
        P, L = _G["P"], _G["L"]
        for seed in seeds:
            rng = np.random.default_rng(seed)
            if which == "C2":
                x = C.level(P, "BTC.D")
                Ps = P.copy()
                Ps["BTC.D"] = 100.0 / (1 + np.exp(-C.matched_rw(x.values, rng)))      # back to pct so vol_ratio reads it as BTC.D
                feat = vol_ratio(Ps)
            else:
                Ls = L.copy()
                for col in Ls.columns:
                    v = Ls[col].values.copy()
                    fin = np.isfinite(v)
                    v[fin] = C.matched_rw(v[fin], rng)
                    Ls[col] = v
                feat = levy_area(Ls)
            Fd = F[SIGNALS].copy()
            Fd["decoy"] = feat.values
            p, _ = run_spec(Fd, Y, SIGNALS + ["decoy"])
            p = p.where(mask)
            met = C.metrics(p, Y[TARGET], True)
            out.append({"pooled": met.get("pooled", {}).get("auc"), "byEra": {e: met.get(e, {}).get("auc") for e in ERA_NAMES},
                        "acf1": (None if feat.where(mask).dropna().shape[0] < 30 else round(float(feat.where(mask).dropna().autocorr(1)), 3)),
                        "n": int(p.notna().sum())})
    return out


def run_jobs(pool, jobs):
    return pool.map(_job, jobs) if pool else [_job(j) for j in jobs]


def chunks(items, k):
    k = max(1, min(k, len(items)))
    return [items[i::k] for i in range(k)]


# ------------------------------------------------------------------------------------------- scoring
def score(pred, y, base_pred, fresh):
    met = C.metrics(pred, y, True, is_prob=True)
    bm = C.metrics(base_pred.where(pred.notna()), y, True, is_prob=True)
    for era, row in met.items():
        row["brierTrainBase"] = bm.get(era, {}).get("brier")
        row["brierOwnEra"] = row.pop("brierBase")
        row["skillVsTrainBase"] = (None if row["brierTrainBase"] in (None, 0) else round(1 - row["brier"] / row["brierTrainBase"], 3))
    fr = C.metrics(pred.where(fresh), y, True)
    return {"byEra": met, **H.era_strat_auc(pred, y), "fresh": {e: r.get("auc") for e, r in fr.items()}, "freshN": {e: r.get("n") for e, r in fr.items()}}


def paired_strat_boot(pa, pb, y, n, rng, bl=26):
    """Paired 26-week block bootstrap of the era-stratified AUC difference (blocks resampled inside each era; eras weighted
    by their positive x negative pair counts, as study8_honest.era_strat_auc weights them)."""
    groups = []
    for era in C.ERAS:
        m = H.era_mask(pa.index, era) & pa.notna() & pb.notna() & y.notna()
        if m.sum() >= 20:
            groups.append((pa[m].values, pb[m].values, y[m].values))

    def strat(sel):
        na = nb = den = 0.0
        for (a, b, yy), ii in zip(groups, sel):
            va, vb = C.auc(a[ii], yy[ii]), C.auc(b[ii], yy[ii])
            if va is None or vb is None:
                continue
            n1 = float((yy[ii] > 0.5).sum())
            w = n1 * (len(ii) - n1)
            na, nb, den = na + w * va, nb + w * vb, den + w
        return (na - nb) / den if den else None
    real = strat([np.arange(len(g[2])) for g in groups])
    vals = []
    for _ in range(n):
        sel = []
        for g in groups:
            N = len(g[2])
            starts = rng.integers(0, N, size=int(np.ceil(N / bl)))
            sel.append(np.concatenate([(np.arange(s, s + bl) % N) for s in starts])[:N])
        v = strat(sel)
        if v is not None:
            vals.append(v)
    v = np.array(vals)
    return {"diff": (None if real is None else round(real, 3)), "n": len(v), "q05": (round(float(np.quantile(v, 0.05)), 3) if len(v) else None),
            "q50": (round(float(np.quantile(v, 0.5)), 3) if len(v) else None), "q95": (round(float(np.quantile(v, 0.95)), 3) if len(v) else None)}


def point_diff(pa, pb, y):
    m = pa.notna() & pb.notna() & y.notna()
    if m.sum() < 20:
        return None
    va, vb = C.auc(pa[m].values, y[m].values), C.auc(pb[m].values, y[m].values)
    return None if va is None or vb is None else round(va - vb, 3)


def paired_all(pa, pb, y, fresh, n, rng):
    """Paired differences AUC(pa) - AUC(pb) on the common rows: block bootstrap (pooled, by era), episode bootstrap
    (pooled, by era), era-stratified, fresh-start rows (pooled, by era point estimates, pooled block band)."""
    out = {"block": H.paired_block_boot(pa, pb, y, n, rng), "episode": {"pooled": T.paired_episode_boot(pa, pb, y, n, rng, True)}}
    out["episode"]["pooled"]["diff"] = point_diff(pa, pb, y)
    for era in C.ERAS:
        m = H.era_mask(pa.index, era)
        r = T.paired_episode_boot(pa.where(m), pb.where(m), y, n, rng, True)
        r["diff"] = point_diff(pa.where(m), pb.where(m), y)
        out["episode"][era[0]] = r
    out["strat"] = paired_strat_boot(pa, pb, y, n, rng)
    fa, fb = pa.where(fresh), pb.where(fresh)
    out["fresh"] = {"pooled": {"diff": point_diff(fa, fb, y), **T.paired_boot(fa, fb, y, n, "W", rng, True)}}
    for era in C.ERAS:
        m = H.era_mask(pa.index, era)
        out["fresh"][era[0]] = {"diff": point_diff(fa.where(m), fb.where(m), y), "n": int((fa.where(m).notna() & y.notna()).sum())}
    return out


def loo_diff(pa, pb, y):
    """Episode leave-one-out with the 26-week run-up: the increment over fixed5 with each label episode removed."""
    la, lb = H.episode_loo_runup(pa, y, runup=RUNUP), H.episode_loo_runup(pb, y, runup=RUNUP)
    per = {k: (None if la["pooled"][k] is None or lb["pooled"].get(k) is None else round(la["pooled"][k] - lb["pooled"][k], 3)) for k in la["pooled"]}
    vals = {k: v for k, v in per.items() if v is not None}
    by_era = {e: {k: (None if la["byEra"][e][k] is None or lb["byEra"][e].get(k) is None else round(la["byEra"][e][k] - lb["byEra"][e][k], 3)) for k in la["byEra"][e]} for e in ERA_NAMES}
    return {"perEpisode": per, "byEra": by_era, "min": (min(vals.values()) if vals else None), "minEpisode": (min(vals, key=vals.get) if vals else None),
            "max": (max(vals.values()) if vals else None), "maxEpisode": (max(vals, key=vals.get) if vals else None), "nEpisodes": len(per)}


def subset_scores(preds, y, sub, specs, n, rng):
    out = {}
    for spec in specs:
        met = C.metrics(preds[spec].where(sub), y, True)
        lab = preds[spec].notna() & sub & y.notna()
        row = {"auc": {e: r.get("auc") for e, r in met.items()}, "n": {e: r.get("n") for e, r in met.items()},
               "rowsByEra": {era[0]: {"n": int((lab & H.era_mask(lab.index, era)).sum()), "positives": int(y[lab & H.era_mask(lab.index, era)].sum()),
                                      "positiveRuns": len(C.episodes(np.where(lab & H.era_mask(lab.index, era), y, np.nan)))} for era in C.ERAS}}
        if spec != "fixed5":
            pa, pb = preds[spec].where(sub), preds["fixed5"].where(sub)
            row["vsFixed5"] = {"diff": point_diff(pa, pb, y), **T.paired_boot(pa, pb, y, n, "W", rng, True)}
            row["vsFixed5ByEra"] = {era[0]: point_diff(pa.where(H.era_mask(pa.index, era)), pb.where(H.era_mask(pa.index, era)), y) for era in C.ERAS}
        out[spec] = row
    return out


# ------------------------------------------------------------------------------------------- criteria
def ni(reason):
    return {"status": "not identifiable", "why": reason}


def era_context(preds, y, mask, fresh):
    """What the era and fresh-start criteria rest on: rows, positives, label episodes and fresh rows per era, the fresh rows'
    era shares, and fixed5's own era AUC (a reference at ceiling leaves a candidate no room to gain in that era)."""
    lab = mask & y.notna()
    ctx = {}
    fresh_total = int((lab & fresh).sum())
    for era in C.ERAS:
        m = lab & H.era_mask(lab.index, era)
        ctx[era[0]] = {"n": int(m.sum()), "positives": int(y[m].sum()), "episodes": len(C.episodes(np.where(m, y, np.nan))),
                       "freshRows": int((m & fresh).sum()), "freshPositives": int(y[m & fresh].sum()),
                       "freshShareOfPooled": (round(float((m & fresh).sum() / fresh_total), 3) if fresh_total else None),
                       "fixed5Auc": C.metrics(preds["fixed5"].where(m), y, True).get(era[0], {}).get("auc")}
    ctx["freshRowsPooled"] = fresh_total
    return ctx


def criteria(cand, pdiff, within, smoke, ctx=None):
    """The four pre-registered criteria as written: (i) pooled paired block-boot diff q05 > 0 and >= +0.03; (ii) no era with a
    paired diff below -0.02; (iii) fresh-start paired diff >= 0; (iv) within-era dwell-time permutation p < 0.05 in >= 2 eras.
    `ctx` (era_context) is attached beside (ii) and (iii) so a one-episode era or a ceiling reference is visible; it changes no status."""
    out = {}
    b = pdiff["block"].get("pooled", {})
    if b.get("n", 0) < MIN_DRAWS or b.get("diff") is None:
        out["i"] = ni("fewer than 50 bootstrap draws or no pooled diff")
    else:
        out["i"] = {"status": "pass" if (b["diff"] >= CRIT_GAIN and b["q05"] > 0) else "fail", "diff": b["diff"], "q05": b["q05"], "q95": b["q95"]}
    eras = {e: pdiff["block"].get(e, {}).get("diff") for e in ERA_NAMES}
    if any(v is None for v in eras.values()):
        out["ii"] = {**ni("an era has fewer than 20 common rows"), "byEra": eras}
    else:
        out["ii"] = {"status": "pass" if all(v >= CRIT_ERA_DROP for v in eras.values()) else "fail", "byEra": eras, "minEra": min(eras, key=eras.get)}
    f = pdiff["fresh"]["pooled"]
    out["iii"] = ni("no fresh-start rows") if f.get("diff") is None else {"status": "pass" if f["diff"] >= 0 else "fail", "diff": f["diff"], "q05": f.get("q05"), "q95": f.get("q95")}
    if ctx:
        out["ii"]["context"] = {e: {k: ctx[e][k] for k in ("n", "positives", "episodes", "fixed5Auc")} for e in ERA_NAMES}
        out["ii"]["thinEras"] = {"rule": "fewer than 3 label episodes or at most 20 positives, or the reference above 0.95 (no room to gain)",
                                 "eras": [e for e in ERA_NAMES if ctx[e]["episodes"] < 3 or ctx[e]["positives"] <= 20 or (ctx[e]["fixed5Auc"] or 0) > 0.95]}
        out["iii"]["context"] = {"freshRowsPooled": ctx["freshRowsPooled"], "freshShareByEra": {e: ctx[e]["freshShareOfPooled"] for e in ERA_NAMES},
                                 "freshPositivesByEra": {e: ctx[e]["freshPositives"] for e in ERA_NAMES}, "byEraDiff": {e: pdiff["fresh"].get(e, {}).get("diff") for e in ERA_NAMES}}
    rej, attainable, per = 0, 0, {}
    for e in ERA_NAMES:
        s = within.get(e, {})
        quotable = s.get("quotable", False)
        min_p = s.get("minAttainableP")
        can = bool(quotable and min_p is not None and min_p < CRIT_P)
        attainable += can
        hit = bool(can and s.get("p") is not None and s["p"] < CRIT_P)
        rej += hit
        per[e] = {"p": s.get("p"), "n": s.get("n"), "exact": s.get("exact"), "quotable": quotable, "minAttainableP": min_p, "rejects": hit}
    if rej >= 2:
        out["iv"] = {"status": "pass", "erasRejecting": rej, "byEra": per}
    elif attainable < 2:
        out["iv"] = {**ni("fewer than two eras can attain p < 0.05 (draw count or arrangement count)"), "erasRejecting": rej, "byEra": per}
    else:
        out["iv"] = {"status": "fail", "erasRejecting": rej, "byEra": per}
    st = [out[k]["status"] for k in ("i", "ii", "iii", "iv")]
    out["all"] = "pass" if all(s == "pass" for s in st) else ("fail" if "fail" in st else "not identifiable")
    out["smoke"] = smoke
    return out


def verdict_word(cand, crit):
    if crit[cand]["all"] == "pass":
        if cand == "fixed5+C1g" and crit["fixed5+C1u"]["all"] != "pass":
            return "conditional signal (reported with its gate)"
        return "sixth signal (owner reads it first)"
    if crit[cand]["all"] == "fail":
        return "not supported under its condition"
    return "not identifiable"


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
    n_shift, n_clock, n_within, n_boot, n_dfeat, n_trunc = a.nulls, 200, 300, 1000, 20, 20
    if a.fast:
        n_shift, n_clock, n_within, n_boot, n_dfeat = min(a.nulls, 20), 20, 20, 200, 3
        a.workers = min(a.workers, 2)
    rng = np.random.default_rng(91)

    # ---- data: the clock is the data's last bar, never the wall clock
    raw = pd.read_csv(os.path.join(a.data, "BTC.D_1d.csv"))
    last_ts = dt.datetime.fromtimestamp(int(raw["ts"].iloc[-1]) / 1000, tz=dt.timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        last_et = last_ts.astimezone(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M ET")
    except Exception:
        last_et = "ET unavailable"
    last_utc = last_ts.strftime("%Y-%m-%d %H:%M UTC")
    D = C.load_daily(a.data)
    last_bar = D.index[-1]
    sundays = C.panel(D, "W").index
    last_complete = sundays[sundays < last_bar][-1]     # strictly before the last daily row: that row is never a complete weekly close
    provisional = [str(d.date()) for d in sundays[sundays > last_complete]]
    X, P, Y, F, dd_harness = build_all(D, a.data, last_complete)
    fresh = C.fresh_mask(P, "W")
    L = T.level_panel(P, ["USDT.D", "BTC.D"])
    say(f"study9_candidates  data last bar {last_utc} / {last_et} (daily close {last_bar.date()}); last complete Sunday {last_complete.date()}; "
        f"provisional bars excluded {provisional}; fast={a.fast} shift {n_shift} clocks {n_clock} within-era {n_within} boots {n_boot} decoy-features {n_dfeat} workers {a.workers}")

    # ---- predictions (frozen before any null / bootstrap), the common row mask, the training-window base rate
    preds, models, refits = {}, {}, {}
    for spec, cols in SPECS.items():
        models[spec] = []
        preds[spec], refits[spec] = run_spec(F, Y, cols, keep_models=models[spec])
    base = H.run_const(X, Y, TARGET)
    mask = base.notna() & (F.index >= pd.Timestamp(EVAL_FROM))
    first_own = {}
    for spec in SPECS:
        fv = preds[spec].first_valid_index()
        first_own[spec] = (str(fv.date()) if fv is not None else None)
        mask &= preds[spec].notna()
    own_masks = {spec: preds[spec].notna() & base.notna() & (F.index >= pd.Timestamp(EVAL_FROM)) for spec in SPECS}
    for spec in SPECS:
        preds[spec] = preds[spec].where(mask)
    base = base.where(mask)
    y = Y[TARGET]
    first_common = str(mask[mask].index[0].date())
    lab = mask & y.notna()
    eps = C.episodes(np.where(lab, y, np.nan))
    n_pos = int(y[lab].sum())
    first_feat = {c: str(F[c].first_valid_index().date()) for c in C1G[1:2] + C2 + C3}
    acf = {c: round(float(F[c].where(mask).dropna().autocorr(1)), 3) for c in C2 + C3}
    say(f"common rows: first forecast {first_common} (fixed5 alone could forecast from {first_own['fixed5']}; C3 from {first_own['fixed5+C3']}: USDT.D exists from 2017-07, "
        f"trailing stats + 26-week window + 60 training rows + 26-week label lag), n {int(mask.sum())} labelled {int(lab.sum())} positives {n_pos} in {len(eps)} episodes; "
        f"first finite feature {first_feat}; lag-1 acf vr {acf[C2[0]]} area {acf[C3[0]]}; gate-on weeks (eval) {int((F['gate'].where(mask) > 0).sum())}")

    # ---- scores by era, pooled, stratified, fresh, Brier vs training base; paired differences against fixed5
    oos, pdiff = {}, {}
    for spec in SPECS:
        oos[spec] = score(preds[spec], y, base, fresh)
        if spec != "fixed5":
            pdiff[spec] = paired_all(preds[spec], preds["fixed5"], y, fresh, n_boot, rng)
    for spec in SPECS:
        r = oos[spec]
        eras = " ".join(f"{e[:4]}{e[-2:]} {fmt(r['byEra'].get(e, {}).get('auc'))}" for e in ERA_NAMES)
        d = pdiff.get(spec, {})
        dl = ("" if spec == "fixed5" else f" | vs fixed5 {fmt(d['block']['pooled'].get('diff'))} block[{fmt(d['block']['pooled'].get('q05'))},{fmt(d['block']['pooled'].get('q95'))}] "
              f"ep[{fmt(d['episode']['pooled'].get('q05'))},{fmt(d['episode']['pooled'].get('q95'))}] strat {fmt(d['strat'].get('diff'))}[{fmt(d['strat'].get('q05'))},{fmt(d['strat'].get('q95'))}] "
              f"fresh {fmt(d['fresh']['pooled'].get('diff'))}[{fmt(d['fresh']['pooled'].get('q05'))},{fmt(d['fresh']['pooled'].get('q95'))}] eras {' '.join(fmt(d['block'].get(e, {}).get('diff')) for e in ERA_NAMES)}")
        say(f"{spec:14s} auc pooled {fmt(r['byEra'].get('pooled', {}).get('auc'))} {eras} strat {fmt(r['eraStratAuc'])} fresh {fmt(r['fresh'].get('pooled'))} "
            f"brier skill vs train-base {' '.join(fmt(r['byEra'].get(e, {}).get('skillVsTrainBase'), 2) for e in ERA_NAMES + ['pooled'])}{dl}")

    # ---- own-row supplement: each candidate against fixed5 on every row the pair can forecast (C3 shortens the common set)
    own_pairs = {}
    for cand in ("fixed5+C1g", "fixed5+C1u", "fixed5+C2"):
        pa, _ = run_spec(F, Y, SPECS[cand])
        pb, _ = run_spec(F, Y, SIGNALS)
        m = own_masks[cand] & pb.notna()
        own_pairs[cand] = {"firstRow": str(m[m].index[0].date()), "n": int(m.sum()), "block": H.paired_block_boot(pa.where(m), pb.where(m), y, n_boot, rng)}
    say("own-row supplement (pair rows from " + ", ".join(f"{k} {v['firstRow']} n{v['n']}: diff {fmt(v['block']['pooled'].get('diff'))} [{fmt(v['block']['pooled'].get('q05'))},{fmt(v['block']['pooled'].get('q95'))}] eras {' '.join(fmt(v['block'].get(e, {}).get('diff')) for e in ERA_NAMES)}" for k, v in own_pairs.items()) + "); criteria use the common rows only")

    # ---- C1: readiness-on and readiness-off rows scored separately
    gate = F["gate"].where(mask)
    readiness = {"on": subset_scores(preds, y, gate > 0, ["fixed5", "fixed5+C1g", "fixed5+C1u", "C1g", "C1u"], n_boot, rng),
                 "off": subset_scores(preds, y, gate == 0, ["fixed5", "fixed5+C1g", "fixed5+C1u", "C1g", "C1u"], n_boot, rng)}
    for side in ("on", "off"):
        rr = readiness[side]
        cnt = rr["fixed5"]["rowsByEra"]
        say(f"C1 gate-{side} rows (n {rr['fixed5']['n'].get('pooled')}, base {fmt(y[mask & ((gate > 0) if side == 'on' else (gate == 0))].mean(), 2)}; by era n/pos/positive runs "
            + " ".join(f"{cnt[e]['n']}/{cnt[e]['positives']}/{cnt[e]['positiveRuns']}" for e in ERA_NAMES) + "): " + "; ".join(
            f"{s} auc {fmt(rr[s]['auc'].get('pooled'))}" + ("" if s == "fixed5" else f" vs fixed5 {fmt(rr[s]['vsFixed5'].get('diff'))}[{fmt(rr[s]['vsFixed5'].get('q05'))},{fmt(rr[s]['vsFixed5'].get('q95'))}] eras {' '.join(fmt(v) for v in rr[s]['vsFixed5ByEra'].values())}")
            for s in rr) + ("; the pooled gate-on AUC ranks across eras, within-era it is scoreable in one era only" if side == "on" else ""))
    readiness["note"] = ("gate-on rows are few and era-concentrated (see rowsByEra): within-era the conditional comparison is scoreable in one era (2023-26, one episode), "
                         "so the pooled gate-on difference is mostly a cross-era level ranking and its two-block band is not a conditional result")

    # ---- C2: sign at every refit, marginal AUC at daily (5, 21 d) and weekly (13 w) scale on the same rows
    j = 1 + SPECS["fixed5+C2"].index(C2[0])
    signs = [int(np.sign(w[j])) for (_, _, w) in models["fixed5+C2"]]
    sign_str = "".join("+" if s > 0 else ("-" if s < 0 else "0") for s in signs)
    c2 = {"signAtRefits": sign_str, "refitDates": [r["t"] for r in refits["fixed5+C2"]], "nPositive": int(sum(s > 0 for s in signs)), "nNegative": int(sum(s < 0 for s in signs)),
          "coefLast": round(float(models["fixed5+C2"][-1][2][j]), 3), "marginalAuc": {}}
    c2["marginalAuc"]["weekly13w/52w"] = {e: r.get("auc") for e, r in C.metrics(F[C2[0]].where(mask), y, True).items()}
    lev = M.levels(D)
    for s in VR_DAILY_SCALES + (VR_ROUND8_SCALE,):
        vr_d = M.scale_features(lev, s)["btcd_vr"].reindex(F.index)      # study8_multiscale btcd_vr at scale s: 2s / 8s bars of 1-day increments
        c2["marginalAuc"][f"daily s={s} ({2 * s}/{8 * s}d)"] = {e: r.get("auc") for e, r in C.metrics(vr_d.where(mask), y, True).items()}
    # diagnostic (not the registered C2): the weekly ratio with the round-8 s = 91 windows (26 w / 104 w), on the same rows
    d26 = C.level(P, "BTC.D").diff()
    vr26 = np.log(d26.rolling(2 * VR_SHORT).std() / d26.rolling(2 * VR_LONG).std()).replace([np.inf, -np.inf], np.nan)
    c2["marginalAuc"]["weekly26w/104w (diagnostic)"] = {e: r.get("auc") for e, r in C.metrics(vr26.where(mask), y, True).items()}
    c2["marginalAucC2aloneWalkForward"] = {e: r.get("auc") for e, r in oos["C2"]["byEra"].items()}
    c2["windowNote"] = ("the registered C2 is 13w / 52w; round 8's transferring feature was study8_multiscale btcd_vr at s = 91, whose windows are 2s / 8s = 182 / 728 days "
                        "(26 w / 104 w), so the s = 91 and 26w/104w rows are the transfer claim read on these rows and the 13w/52w row is the candidate; only the candidate is judged")
    say(f"C2 sign at {len(signs)} refits: {sign_str} ({c2['nPositive']}+ / {c2['nNegative']}-; last coef {c2['coefLast']}); marginal AUC on the common rows (pooled | by era): "
        + " | ".join(f"{k} {fmt(v.get('pooled'))} ({' '.join(fmt(v.get(e)) for e in ERA_NAMES)})" for k, v in c2["marginalAuc"].items()) + f"; C2-alone walk-forward {fmt(oos['C2']['byEra'].get('pooled', {}).get('auc'))}"
        + "; the registered 13w/52w term is the candidate, s=91 (= 26w/104w) is round 8's transferring feature read on the same rows (diagnostic, not a candidate)")

    # ---- nulls and decoys through the whole procedure (forked workers; predictions above are already frozen)
    _G.update({"F": F, "Y": Y, "mask": mask, "P": P, "L": L, "clockPreds": {s: preds[s] for s in CLOCK_SPECS}})
    ctx = get_context("fork")
    pool = ctx.Pool(a.workers) if a.workers > 1 else None
    try:
        jobs = [("shift", 1000 + i, len(c)) for i, c in enumerate(chunks(list(range(n_shift)), a.workers * 2)) if len(c)]
        shift_raw = [r for part in run_jobs(pool, jobs) for r in part]
        perm_raw, arrangements = {}, {}
        for era in C.ERAS + [POOLED_ERA]:
            pos = perm_positions(Y, era)
            nb = len(H.perm_blocks(Y[TARGET].values[pos]))
            K = H.n_arrangements(nb)
            exact = K <= max(n_within, ENUM_UP_TO)
            orders = [np.array(o) for o in itertools.permutations(range(nb))] if exact else [rng.permutation(nb) for _ in range(n_within)]
            arrangements[era[0]] = {"blocks": nb, "distinctArrangements": (int(K) if nb <= 20 else f"{nb}!"), "enumerated": exact, "draws": len(orders)}
            jobs = [("perm", era, c) for c in chunks(orders, a.workers * 2) if len(c)]
            perm_raw[era[0]] = [r for part in run_jobs(pool, jobs) for r in part]
        lo, hi = pd.Timestamp(ANCHOR_LO), pd.Timestamp(ANCHOR_HI)
        anchors = [lo + pd.Timedelta(days=int(d)) for d in rng.integers(0, (hi - lo).days + 1, size=n_clock)]
        jobs = [("clock", c) for c in chunks(anchors, a.workers * 2) if len(c)]
        clock_raw = [r for part in run_jobs(pool, jobs) for r in part]
        dfeat_raw = {}
        for which in ("C2", "C3"):
            seeds = [5000 + (0 if which == "C2" else 500) + i for i in range(n_dfeat)]
            jobs = [("dfeat", which, c) for c in chunks(seeds, a.workers * 2) if len(c)]
            dfeat_raw[which] = [r for part in run_jobs(pool, jobs) for r in part]
    finally:
        if pool:
            pool.close()
            pool.join()

    null = {"shift": {}, "shiftIncrement": {}, "withinEra": {}, "withinEraIncrement": {}, "arrangements": arrangements}
    for spec in NULL_SPECS:
        real = oos[spec]["byEra"].get("pooled", {}).get("auc")
        null["shift"][spec] = H.psum(real, [r[spec] for r in shift_raw if r[spec] is not None])
        if spec != "fixed5":
            inc = [r[spec] - r["fixed5"] for r in shift_raw if r[spec] is not None and r["fixed5"] is not None]
            null["shiftIncrement"][spec] = H.psum(pdiff[spec]["block"]["pooled"].get("diff"), inc)
        null["withinEra"][spec] = {}
        for era in C.ERAS + [POOLED_ERA]:
            vals = [r[spec] for r in perm_raw[era[0]] if r[spec] is not None]
            s = H.psum(oos[spec]["byEra"].get(era[0], {}).get("auc"), vals, exact=arrangements[era[0]]["enumerated"])
            s["minAttainableP"] = (round(1.0 / arrangements[era[0]]["distinctArrangements"], 4) if arrangements[era[0]]["enumerated"] else (round(1.0 / len(vals), 4) if vals else None))
            null["withinEra"][spec][era[0]] = s
    # diagnostics beside the pre-registered nulls (not criteria): the within-era null of the INCREMENT over fixed5 on the same
    # permuted labels (criterion (iv) as written tests the whole model, which fixed5 alone already passes), and the shift null of
    # the best increment over the five candidates (the family-wise reading a pass would have needed)
    for spec in CANDS:
        null["withinEraIncrement"][spec] = {}
        for era in C.ERAS + [POOLED_ERA]:
            vals = [r[spec] - r["fixed5"] for r in perm_raw[era[0]] if r[spec] is not None and r["fixed5"] is not None]
            real_inc = pdiff[spec]["block"].get(era[0], {}).get("diff")
            null["withinEraIncrement"][spec][era[0]] = H.psum(real_inc, vals, exact=arrangements[era[0]]["enumerated"])
    best_real = max(v for v in (pdiff[s]["block"]["pooled"].get("diff") for s in CANDS) if v is not None)
    best_null = [max(r[s] - r["fixed5"] for s in CANDS) for r in shift_raw if all(r[s] is not None for s in NULL_SPECS)]
    null["shiftIncrementMaxOverCandidates"] = {**H.psum(best_real, best_null), "bestCandidate": max(CANDS, key=lambda s: pdiff[s]["block"]["pooled"].get("diff") or -9),
                                               "note": "max over the five candidate models of the increment over fixed5, per shifted-label draw: a family-wise null for 'any candidate adds'"}
    for spec in NULL_SPECS:
        w = null["withinEra"][spec]
        say(f"within-era dwell-time permutation {spec:12s}: " + "  ".join(f"{e[:4]}{e[-2:]} auc {fmt(w[e].get('real'))} med {fmt(w[e].get('nullMedian'))} p95 {fmt(w[e].get('nullP95'))} {H.pfmt(w[e])}" for e in ERA_NAMES + ['pooled'])
            + (f" | shift null pooled med {fmt(null['shift'][spec].get('nullMedian'))} p95 {fmt(null['shift'][spec].get('nullP95'))} {H.pfmt(null['shift'][spec])}" if spec in ("fixed5",) else
               f" | shift: auc {H.pfmt(null['shift'][spec])}, increment over fixed5 med {fmt(null['shiftIncrement'][spec].get('nullMedian'))} p95 {fmt(null['shiftIncrement'][spec].get('nullP95'))} {H.pfmt(null['shiftIncrement'][spec])}"))
    wi = null["withinEraIncrement"]
    say("within-era null of the INCREMENT over fixed5 (diagnostic beside (iv), same permuted labels): " + "; ".join(
        f"{s.replace('fixed5+', '')} " + " ".join(f"{e[:4]}{e[-2:]} {fmt(wi[s][e].get('real'))} p95 {fmt(wi[s][e].get('nullP95'))} {H.pfmt(wi[s][e])}" for e in ERA_NAMES) for s in CANDS)
        + f" | family-wise shift null of the best increment ({null['shiftIncrementMaxOverCandidates']['bestCandidate']} {fmt(best_real)}): med {fmt(null['shiftIncrementMaxOverCandidates'].get('nullMedian'))} p95 {fmt(null['shiftIncrementMaxOverCandidates'].get('nullP95'))} {H.pfmt(null['shiftIncrementMaxOverCandidates'])}")

    # ---- adversary (a): decoy clocks
    decoy = {"n": len(clock_raw), "anchorsUniform": [ANCHOR_LO, ANCHOR_HI], "periodDays": PERIOD_DAYS, "models": {}}
    for spec in CLOCK_SPECS:
        realp = oos[spec]["byEra"].get("pooled", {}).get("auc")
        real21 = oos[spec]["byEra"].get("2021-2022", {}).get("auc")
        reals = oos[spec]["eraStratAuc"]
        vp = [r[spec]["pooled"] for r in clock_raw if r[spec]["pooled"] is not None]
        v21 = [r[spec]["2021-2022"] for r in clock_raw if r[spec]["2021-2022"] is not None]
        vs = [r[spec]["strat"] for r in clock_raw if r[spec]["strat"] is not None]
        row = {"pooled": H.psum(realp, vp), "2021-2022": H.psum(real21, v21), "strat": H.psum(reals, vs)}
        row["beatsP95Both"] = bool(realp is not None and real21 is not None and len(vp) and len(v21) and realp > row["pooled"]["nullP95"] and real21 > row["2021-2022"]["nullP95"])
        row["quotable"] = bool(len(vp) >= MIN_DRAWS)
        # power diagnostic: a sin + cos clock spans the same space for every anchor of one period (sin(t + phi) is a linear
        # combination of sin t and cos t), so the decoys are rotations of one clock and their predictions nearly coincide; the
        # only difference from the real clock is its restart at each halving. The decoy spread and the rank correlation of each
        # decoy's prediction with the real-anchor prediction say how much the test can tell apart.
        sp = [r[spec]["spearmanVsReal"] for r in clock_raw]
        row["rotationInvariance"] = {"decoySpreadPooledP05toP95": (round(row["pooled"]["nullP95"] - row["pooled"]["nullP05"], 4) if len(vp) else None),
                                     "decoySpread2021P05toP95": (round(row["2021-2022"]["nullP95"] - row["2021-2022"]["nullP05"], 4) if len(v21) else None),
                                     "spearmanDecoyVsRealMin": (round(float(np.min(sp)), 4) if sp else None), "spearmanDecoyVsRealMedian": (round(float(np.median(sp)), 4) if sp else None),
                                     "identifiable": False,
                                     "why": "the decoy family is a phase rotation of the real clock (same period, sin and cos both in the model); the real clock differs only by its halving restarts (1411 / 1419 / 1440 days vs 1460), so 'beats the decoy p95' cannot separate a real anchor from chance timing"}
        decoy["models"][spec] = row
    decoy["identifiable"] = False
    say("adversary (a) decoy clocks (random anchor, same 1460-day period, whole procedure): " + "; ".join(
        f"{s}: pooled {fmt(r['pooled'].get('real'))} vs decoy p95 {fmt(r['pooled'].get('nullP95'))} {H.pfmt(r['pooled'])}, 2021-22 {fmt(r['2021-2022'].get('real'))} vs p95 {fmt(r['2021-2022'].get('nullP95'))} {H.pfmt(r['2021-2022'])}"
        f" -> beats both {r['beatsP95Both']}" for s, r in decoy["models"].items()))
    say("adversary (a) power: NOT IDENTIFIABLE as pre-registered (sin+cos model is invariant to the anchor phase; decoys differ from the real clock only by its halving restarts): "
        + "; ".join(f"{s} decoy spread p05..p95 pooled {fmt(r['rotationInvariance']['decoySpreadPooledP05toP95'])} 2021-22 {fmt(r['rotationInvariance']['decoySpread2021P05toP95'])}, "
                    f"spearman decoy-vs-real min {fmt(r['rotationInvariance']['spearmanDecoyVsRealMin'])}" for s, r in decoy["models"].items()))

    # ---- adversary (b): decoy features (26-week statistics of matched random walks)
    dfeat = {}
    for which, cand in (("C2", "fixed5+C2"), ("C3", "fixed5+C3")):
        rows = dfeat_raw[which]
        f5 = oos["fixed5"]["byEra"]
        inc = [r["pooled"] - f5["pooled"]["auc"] for r in rows if r["pooled"] is not None]
        inc_era = {e: [r["byEra"][e] - f5[e]["auc"] for r in rows if r["byEra"].get(e) is not None and f5.get(e, {}).get("auc") is not None] for e in ERA_NAMES}
        dfeat[which] = {"n": len(rows), "acf1Real": acf[SPECS[cand][-1]], "acf1DecoyMean": (round(float(np.mean([r["acf1"] for r in rows if r["acf1"] is not None])), 3) if rows else None),
                        "incrementOverFixed5": {"real": pdiff[cand]["block"]["pooled"].get("diff"), "decoyMedian": (round(float(np.median(inc)), 3) if inc else None),
                                                "decoyP95": (round(float(np.quantile(inc, 0.95)), 3) if inc else None), "decoyMax": (round(float(np.max(inc)), 3) if inc else None), "n": len(inc)},
                        "incrementByEra": {e: {"real": pdiff[cand]["block"].get(e, {}).get("diff"), "decoyMedian": (round(float(np.median(v)), 3) if v else None), "decoyMax": (round(float(np.max(v)), 3) if v else None)} for e, v in inc_era.items()},
                        "note": ("vol ratio of a matched random walk of the BTC.D logit (block 13 w, random signs)" if which == "C2" else "26-week Levy area between matched random walks of the USDT.D and BTC.D logits")}
    say("adversary (b) decoy feature (matched random walk, same statistic): " + "; ".join(
        f"{w}: acf1 real {d['acf1Real']} decoy {d['acf1DecoyMean']}, increment over fixed5 real {fmt(d['incrementOverFixed5']['real'])} vs decoy median {fmt(d['incrementOverFixed5']['decoyMedian'])} p95 {fmt(d['incrementOverFixed5']['decoyP95'])} max {fmt(d['incrementOverFixed5']['decoyMax'])} (n{d['n']}{'' if d['n'] >= MIN_DRAWS else '!'})"
        for w, d in dfeat.items()))

    # ---- adversary (c): episode leave-one-out with the 26-week run-up
    loo = {cand: loo_diff(preds[cand], preds["fixed5"], y) for cand in CANDS}
    say("adversary (c) episode LOO (each label episode + 26-week run-up dropped; increment over fixed5 on the rest): " + "; ".join(
        f"{c} min {fmt(l['min'])} at {l['minEpisode']} max {fmt(l['max'])} at {l['maxEpisode']}" for c, l in loo.items()) + f" ({loo[CANDS[0]]['nEpisodes']} episodes)")

    # ---- adversary (d): the all-three model against the sum of the parts
    gain = {s: pdiff[s]["block"]["pooled"].get("diff") for s in pdiff}
    singles = {"fixed5+C1g": gain["fixed5+C1g"], "fixed5+C2": gain["fixed5+C2"], "fixed5+C3": gain["fixed5+C3"]}
    sum_single = (None if any(v is None for v in singles.values()) else round(sum(singles.values()), 3))
    inter = {"jointGain": gain["fixed5+all3"], "sumOfSingles": sum_single, "jointExceedsSum": (None if sum_single is None or gain["fixed5+all3"] is None else bool(gain["fixed5+all3"] > sum_single)), "pairs": {}}
    for pair, (p1, p2) in PAIRS.items():
        s2 = (None if gain[p1] is None or gain[p2] is None else round(gain[p1] + gain[p2], 3))
        inter["pairs"][pair] = {"pairGain": gain[pair], "sumOfParts": s2, "interaction": (None if s2 is None or gain[pair] is None else round(gain[pair] - s2, 3))}
    say(f"adversary (d) joint vs sum of parts: all3 gain {fmt(gain['fixed5+all3'])} vs C1g+C2+C3 singles {fmt(sum_single)} ({'joint exceeds sum' if inter['jointExceedsSum'] else 'no excess'}); pair interactions "
        + ", ".join(f"{k.replace('fixed5+', '')} {fmt(v['interaction'])}" for k, v in inter["pairs"].items()))

    # ---- criteria as pre-registered
    smoke = any(not s.get("quotable", False) for spec in CANDS for s in null["withinEra"][spec].values()) or n_shift < MIN_DRAWS or n_clock < MIN_DRAWS
    ctx = era_context(preds, y, mask, fresh)
    crit = {cand: criteria(cand, pdiff[cand], null["withinEra"][cand], smoke, ctx) for cand in CANDS}
    verdicts = {cand: verdict_word(cand, crit) for cand in CANDS}
    say("criteria context: per era n/positives/episodes " + " ".join(f"{e[:4]}{e[-2:]} {ctx[e]['n']}/{ctx[e]['positives']}/{ctx[e]['episodes']} (fixed5 auc {fmt(ctx[e]['fixed5Auc'])})" for e in ERA_NAMES)
        + f"; fresh-start rows {ctx['freshRowsPooled']} of which by era " + " ".join(f"{ctx[e]['freshRows']} ({ctx[e]['freshPositives']} pos, share {fmt(ctx[e]['freshShareOfPooled'], 2)})" for e in ERA_NAMES)
        + "; an era with one label episode or a reference at ceiling makes (ii) there and most of (iii) a one-episode reading; (iv) is a whole-model skill test that fixed5 alone passes")
    for cand in CANDS:
        c = crit[cand]
        say(f"criteria {cand:12s}: (i) {c['i']['status']} diff {fmt(c['i'].get('diff'))} q05 {fmt(c['i'].get('q05'))} | (ii) {c['ii']['status']} eras {' '.join(fmt(v) for v in c['ii']['byEra'].values())} | "
            f"(iii) {c['iii']['status']} fresh {fmt(c['iii'].get('diff'))} | (iv) {c['iv']['status']} rejects {c['iv']['erasRejecting']}/3 p {' '.join(fmt(c['iv']['byEra'][e]['p']) for e in ERA_NAMES)} -> {c['all'].upper()}: {verdicts[cand]}")
    if smoke:
        say("NO VERDICT: a null has fewer than 50 draws (smoke run); the criteria lines above are the provisional reading and the full run's p-values replace them.")

    # ---- leakage checks
    leak = {}
    pf5 = preds["fixed5"]
    Xh = F.copy()
    Xh["btc_dd_ath"] = dd_harness.values
    ph, _ = run_spec(Xh, Y, SIGNALS)
    dd_rows = (F["btc_dd_ath"] - dd_harness).abs()
    differing = dd_rows[dd_rows > 1e-9]
    trainable = F[SIGNALS].notna().all(axis=1) & y.notna()
    first_trainable = trainable[trainable].index[0] if trainable.any() else None
    last_differing = differing.index[-1] if len(differing) else None
    immaterial = bool(first_trainable is not None and (last_differing is None or last_differing < first_trainable))
    leak["athAnchor"] = {"rowsDiffering": int(len(differing)), "maxAbsDiff": round(float(dd_rows.max()), 4), "lastRowDiffering": (str(last_differing.date()) if last_differing is not None else None),
                         "firstTrainableRow": (str(first_trainable.date()) if first_trainable is not None else None), "fixed5PredMaxAbsDiffOnCommonRows": round(float((ph.where(mask) - pf5).abs().max()), 10),
                         "immaterialHere": immaterial,
                         "note": ("btc_dd_ath rebuilt from the full BTCUSD history (study8_honest.ath_drawdown) for the gate and for fixed5; "
                                  + ("the rows it changes all precede the first trainable row (ethbtc_fromhi52w needs 52 weeks of ETHBTC), so no training row, gate value or prediction "
                                     "in this module depends on the anchor and the zero prediction difference is true by construction, not a test passed" if immaterial else
                                     "the rows it changes overlap the training rows; the prediction difference above measures the anchor's effect"))}
    n = len(F)
    cuts = rng.integers(max(1, n // 4), n - 1, size=n_trunc)
    worst_f, worst_p, tested = 0.0, 0.0, 0
    pall = preds["fixed5+all3"]
    for c in cuts:
        cut_date = F.index[int(c)]
        Dc = D[D.index <= cut_date]
        Xc, Pc, Yc, Fc, _ = build_all(Dc, a.data, cut_date)
        for col in C1G[1:] + C2 + C3:
            fa, fb = Fc[col].iloc[-1], F[col].loc[cut_date]
            if np.isfinite(fa) and np.isfinite(fb):
                worst_f = max(worst_f, abs(float(fa) - float(fb)))
        pc, _ = run_spec(Fc, Yc, SPECS["fixed5+all3"])
        both = pc.notna() & pall.reindex(pc.index).notna()
        if both.any():
            worst_p = max(worst_p, float((pc[both] - pall.reindex(pc.index)[both]).abs().max()))
        tested += 1
    leak["truncation"] = {"ok": bool(worst_f <= 1e-9 and worst_p <= 1e-9), "maxAbsDiffFeatures": worst_f, "maxAbsDiffPredictions": worst_p, "tested": tested,
                          "cuts": [str(F.index[int(c)].date()) for c in cuts]}
    leak["labels"] = {"lastLabelledRow": str(y[y.notna()].index[-1].date()), "lastCompleteSunday": str(last_complete.date()), "provisionalBarsExcluded": provisional, "labelLagWeeks": 26}
    leak["clock"] = {"halvings": [str(h.date()) for h in C.HALVINGS], "note": "days_since_halving counts from the last past halving; 2028-04-15 is the published next date and only sets the phase after it"}
    leak["windows"] = {"levyArea": "increments t-25..t, trailing 104-bar sds ending at t (study8_tda_sig)", "volRatio": "13- and 52-week std of increments ending at t", "ath": "running max of weekly closes"}
    say(f"leakage: truncation test at {tested} random Sundays (whole pipeline rebuilt on the cut daily panel): features max |diff| {worst_f:.1e}, predictions max |diff| {worst_p:.1e}, ok {leak['truncation']['ok']}; "
        f"ATH anchor rebuilt (rows differing {leak['athAnchor']['rowsDiffering']}, last {leak['athAnchor']['lastRowDiffering']}, first trainable row {leak['athAnchor']['firstTrainableRow']}: "
        f"{'immaterial here, no training row sees the anchor' if leak['athAnchor']['immaterialHere'] else 'material'}; fixed5 preds max |diff| {leak['athAnchor']['fixed5PredMaxAbsDiffOnCommonRows']:.1e}); last labelled row {leak['labels']['lastLabelledRow']}")

    # ---- today: the last complete Sunday
    tlast = last_complete
    today = {"asOf": str(tlast.date()), "dataLastBarUtc": last_utc, "dataLastBarEt": last_et, "btcd": round(float(P.loc[tlast, "BTC.D"]), 2),
             "readings": {spec: (round(float(preds[spec].loc[tlast]), 4) if np.isfinite(preds[spec].loc[tlast]) else None) for spec in SPECS},
             "trainingBase": (round(float(base.loc[tlast]), 4) if np.isfinite(base.loc[tlast]) else None)}
    dd = float(F.loc[tlast, "btc_dd_ath"])
    rally = 0.0 if dd >= GATE_DD else (0.95 * math.exp(-dd) - 1) * 100
    today["gate"] = {"on": bool(F.loc[tlast, "gate"] > 0), "btcDrawdownFromAthPct": round((math.exp(dd) - 1) * 100, 1), "btcRallyToWithin5pctOfAthPct": round(rally, 1),
                     "m2YoY": round(float(F.loc[tlast, "m2_yoy"]), 4), "m2Condition": bool(F.loc[tlast, "m2_yoy"] > 0)}
    today["candidates"] = {"daysSinceHalving": int(F.loc[tlast, "days_since_halving"]), "phaseTurns": round(float(F.loc[tlast, "days_since_halving"]) / PERIOD_DAYS, 3),
                           "clk_sin": round(float(F.loc[tlast, "clk_sin"]), 3), "clk_cos": round(float(F.loc[tlast, "clk_cos"]), 3),
                           C2[0]: round(float(F.loc[tlast, C2[0]]), 3), C3[0]: round(float(F.loc[tlast, C3[0]]), 3), "fresh": bool(fresh.loc[tlast])}
    mu, sd, w = models["fixed5"][-1]
    x0 = F.loc[tlast, SIGNALS].values.astype(float)
    spread = {}
    for i, c in enumerate(SIGNALS):
        pair = []
        for sgn in (-1, 1):
            xx = x0.copy()
            xx[i] += sgn * sd[i]
            pair.append(round(float(C.logistic_predict(C.zapply(xx[None, :], mu, sd), w)[0]), 4))
        spread[c] = {"minus1sd": pair[0], "plus1sd": pair[1], "value": round(float(x0[i]), 4), "trainSd": round(float(sd[i]), 4)}
    allv = [v for s in spread.values() for v in (s["minus1sd"], s["plus1sd"])]
    today["fixed5Spread"] = {"perInput": spread, "min": min(allv), "max": max(allv)}
    say(f"TODAY {today['asOf']} (data last bar {last_utc} / {last_et}) BTC.D {today['btcd']}: readings " + " ".join(f"{s} {fmt(v, 3)}" for s, v in today["readings"].items()) + f" train-base {fmt(today['trainingBase'])}")
    say(f"TODAY gate {'ON' if today['gate']['on'] else 'OFF'}: BTC {today['gate']['btcDrawdownFromAthPct']}% from ATH, rally of {today['gate']['btcRallyToWithin5pctOfAthPct']}% needed to be within 5%; M2 y/y {today['gate']['m2YoY']:+.3f} ({'>' if today['gate']['m2Condition'] else '<='} 0); "
        f"days since halving {today['candidates']['daysSinceHalving']} (phase {today['candidates']['phaseTurns']} turns, sin {today['candidates']['clk_sin']} cos {today['candidates']['clk_cos']}); vr13/52 {today['candidates'][C2[0]]}; area USDT.D>BTC.D {today['candidates'][C3[0]]}; fresh {today['candidates']['fresh']}")
    say(f"TODAY fixed5 spread under +/-1 training sd of each input: {today['fixed5Spread']['min']:.3f}..{today['fixed5Spread']['max']:.3f} (" + ", ".join(f"{c} {s['minus1sd']:.3f}/{s['plus1sd']:.3f}" for c, s in spread.items()) + ")")

    # ---- side targets (contract): fall10_26w AUC and y13 IC for every model, no nulls
    side = {}
    for tg, binary in SIDE_TARGETS:
        side[tg] = {}
        for spec, cols in SPECS.items():
            p, _ = run_spec(F, Y, cols, target=tg, binary=binary)
            side[tg][spec] = C.metrics(p.where(mask), Y[tg], binary)
    say("side targets (common rows): fall10_26w auc " + " ".join(f"{s} {fmt(side['fall10_26w'][s].get('pooled', {}).get('auc'))}" for s in ["fixed5"] + CANDS)
        + " | y13 ic " + " ".join(f"{s} {fmt(side['y13'][s].get('pooled', {}).get('ic'))}" for s in ["fixed5"] + CANDS))

    notes = [
        f"Common rows: every metric and criterion is on the intersection of all models' forecast rows (first {first_common}, n {int(mask.sum())}); C3 (USDT.D from 2017-07 + 104-bar trailing stats + 26-week window + 60 training rows + 26-week label lag) sets that start, which removes 2019-01..2019-09 for everyone; the own-row supplement scores C1 and C2 against fixed5 on their own longer row set and is not a criterion.",
        "fixed5 = study8_baselines.SIGNALS through the same walk-forward (expanding window, refit 13 weeks, labels withheld 26 weeks, logistic lam 1); its btc_dd_ath is the true-ATH column (full BTCUSD history). In this panel the anchor is immaterial: the rows it changes (2016-06..2016-12, before the Dec-2013 high was exceeded) all precede the first trainable row (2017-06, when ethbtc_fromhi52w becomes finite), so no training row, gate value or prediction depends on it and the zero prediction difference in leakage.athAnchor is true by construction, not a test passed.",
        "C1 gate = BTC within 5% of its all-time high on weekly closes AND M2 y/y > 0 (M2 lagged 6 weeks by the loader); phase = 2 pi days_since_halving / 1460 with the clock restarting at each past halving; gate x sin / gate x cos are zero off-gate, so the clock can only matter while the gate is on; the un-gated sin/cos model is the paired control for the gate. The conditional (gate-on) comparison is scoreable within one era only (oos.readiness.on.*.rowsByEra): the pooled gate-on difference is mostly a cross-era level ranking and is not quoted as a conditional result.",
        "C2 = log(13-week / 52-week realized vol of weekly BTC.D logit increments), windows ending at t, as registered. Round 8's transferring feature was study8_multiscale btcd_vr at s = 91, whose windows are 2s / 8s bars = 182 / 728 days (26 w / 104 w), not 13 w / 52 w; the daily rows of oos.c2.marginalAuc are btcd_vr at s = 5, 21 (10/40 and 42/168 days) and at s = 91 (closed-left, one-bar shift), and a weekly 26w/104w row is added, all on the common Sundays, so the transfer claim is read on the same rows and label. The registered 13w/52w term is the only candidate judged; the 26w/104w ratio is a diagnostic here and a candidate only if round 10 registers it.",
        "C3 = the 26-week Levy area A[USDT.D, BTC.D] from study8_tda_sig.sig_window on the two-series level panel (identical to the five-series value for that pair: areas are pairwise), scaled by the trailing 104-bar increment sds.",
        "Paired bands: 26-week circular block bootstrap (study8_honest.paired_block_boot, pooled and per era), episode bootstrap over label episodes with their 26-week run-up (study8_tda_sig.paired_episode_boot), era-stratified difference (blocks resampled inside each era, eras weighted by positive x negative pairs), fresh-start rows (BTC.D within 2 points of its 13-week high; the block bootstrap there runs over the fresh subsequence, whose rows are not contiguous).",
        "Within-era nulls are dwell-time block permutations of each era's label episodes and gaps (study8_honest.perm_blocks / apply_order) with the whole procedure rerun; the permutation runs over the era's LABELLED rows only, so the unlabelled 26-week tail stays in place and every draw is scored on the real run's rows (study8_honest permuted the tail inside the last gap; same blocks, same arrangement count); an era is enumerated exactly when its arrangements are at most max(n_within, 120), and the smallest attainable p is 1 / arrangements (reported as minAttainableP); criterion (iv) counts only eras that can attain p < 0.05.",
        "Criterion (iv) as pre-registered tests the candidate MODEL's era AUC, not the increment: fixed5 alone rejects in every era, so any addition that does not destroy fixed5 passes (iv); null.withinEraIncrement gives the same permutation null for the increment over fixed5 (candidate minus fixed5 on the same permuted labels) as a diagnostic beside it, not a criterion.",
        "Shifted-target nulls (circular shift of every target column by 26+ weeks) rerun the whole procedure for every candidate model and fixed5 on the same shifted labels, so the increment over fixed5 has its own null. No multiplicity is carried in the per-candidate p-values or the +0.03 bar (C3 was the best of 15 data-chosen areas, five candidate models face four criteria each); null.shiftIncrementMaxOverCandidates is the family-wise null of the best increment, reported beside them, and a pass would have needed it.",
        "Criteria (ii) and (iii) context (criteria.*.ii.context, iii.context): 2023-26 holds 16 positives in 2 label episodes (one a single week) and fixed5 scores at ceiling there, so that era's paired difference is a one-episode number with no room to gain; 148 of the 207 fresh-start rows are in 2023-26, so the pooled fresh criterion is mostly that era's continuation ranking; the statuses are computed exactly as registered.",
        "Decoy clocks: anchors uniform over 2009-01-01..2016-12-31 with the same 1460-day period, run gated and un-gated through the whole procedure; the real anchor must beat the decoys' p95 pooled AND in 2021-22 (as registered). This adversary is NOT IDENTIFIABLE by construction: a model with both sin and cos of the phase spans the same space for every anchor (sin(t + phi) = sin t cos phi + cos t sin phi), so the decoys are phase rotations of one strictly periodic clock and their predictions nearly coincide (adversary.decoyClocks.models.*.rotationInvariance: decoy spread and rank correlation with the real-anchor prediction); the real clock differs only by its restart at each halving (1411 / 1419 / 1440 days vs 1460), which no decoy carries. 'Does not beat the decoy p95' is therefore not evidence of chance timing, and its p is not quoted; a decoy family with power (random period or random restart dates) is a round-10 registration.",
        "Decoy features: the candidate's own statistic computed on matched random walks (study8_common.matched_rw: block-resampled increments, random signs) of the input series, run as fixed5 + decoy; their lag-1 autocorrelation is printed beside the real feature's.",
        "Brier is reported against the walk-forward training-window base rate by era (study8_honest.run_const) and the era's own rate (oracle climatology, not available in real time).",
        "Readiness-on rows and readiness-off rows are scored separately for C1 (counts in oos.readiness.*.*.rowsByEra); their paired block bands run over the subsequence of those rows (not contiguous), and eras with fewer than 20 such rows print na.",
        "The last complete weekly bar is the last Sunday strictly before the last daily row, so the last daily row is always provisional whatever time the data were fetched.",
        "The round-8 C3 increment (+0.07 mean-of-era) was measured against fixed5 + a vol block with block-wise regularisation (study8_tda_sig M1r); the plan's specification here is fixed5 + the raw area through the baseline logistic (lam 1), which is the comparison the criteria use.",
        f"Null draw counts are printed beside every p (n!, i.e. fewer than {MIN_DRAWS}, means resolution 1/n, not a p-value; E = enumerated exactly); only the full run's p-values are quotable.",
        "Nothing here touches the bot; a candidate that passes becomes a sixth signal only after the owner reads it; a conditional that passes is written with its gate (dynamics rule).",
    ]
    if _LINES[1]:
        notes.append(f"{_LINES[1]} summary lines were dropped to stay under the 60-line limit; everything is in results.json.")
    series = {spec: C.thin(preds[spec], every=2) for spec in ["fixed5"] + CANDS}
    series["gate"] = C.thin(F["gate"].where(mask), every=2, digits=0)
    series[C2[0]] = C.thin(F[C2[0]].where(mask), every=2)
    series[C3[0]] = C.thin(F[C3[0]].where(mask), every=2)
    res = {"module": "study9_candidates", "plan": "ROUND9_PLAN.md [1]", "dataLastBarUtc": last_utc, "dataLastBarEt": last_et, "lastCompleteSunday": str(last_complete.date()), "fast": a.fast,
           "runtimeSec": round(time.time() - t0, 1), "settings": {"nShift": n_shift, "nDecoyClocks": n_clock, "nWithinEra": n_within, "nBoot": n_boot, "nDecoyFeatures": n_dfeat, "nTruncation": n_trunc, "workers": a.workers, "minDrawsForP": MIN_DRAWS},
           "specs": SPECS, "candidates": CANDS, "rows": {"firstCommonForecast": first_common, "n": int(mask.sum()), "labelled": int(lab.sum()), "positives": n_pos, "episodes": len(eps), "firstOwnForecast": first_own, "firstFiniteFeature": first_feat, "acf1": acf},
           "oos": {"fall5_26w": oos, "sideTargets": side, "readiness": readiness, "ownRowSupplement": own_pairs, "c2": c2},
           "pairedVsFixed5": pdiff, "null": null, "adversary": {"decoyClocks": decoy, "decoyFeatures": dfeat, "episodeLOO": loo, "interactions": inter},
           "criteria": crit, "verdicts": verdicts, "noVerdict": smoke, "leakage": leak, "today": today, "series": series, "notes": notes}
    C.write_results(a.out, res)
    say(f"wrote {os.path.join(a.out, 'results.json')} in {time.time() - t0:.0f}s (data last bar {last_utc} / {last_et}); verdicts: " + "; ".join(f"{k} {v}" for k, v in verdicts.items()))


if __name__ == "__main__":
    main()
