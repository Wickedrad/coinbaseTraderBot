#!/usr/bin/env python3
"""Round 10 module [3] sixth: the vol ratio that transferred, and a clock decoy with power (ROUND10_PLAN.md section [3]).

Question. Round 8's multiscale module found one sigma-unit feature that transferred from daily to weekly scale: the BTC.D vol
ratio at s = 91 days (windows 2s / 8s = 182 / 728 days = 26 / 104 weeks). Round 9 registered it as 13w / 52w by mistake and
judged that. This module judges the feature that actually transferred, C2b = log(trailing 26-week realized vol / trailing
104-week realized vol of weekly BTC.D logit increments), as a sixth signal beside fixed5 (study8_baselines.SIGNALS) under
the round-9 four criteria, and as a conditional under a vol-compression gate (C2b x [C2b below its trailing 104-week 20th
percentile at t]: "a compressed BTC.D precedes the fall"). And it gives round 9's halving-clock adversary the power it
lacked: 200 decoy clocks with a random PERIOD (uniform 600..2200 days, phase anchored at the first halving 2012-11-28, sine
and cosine terms, gated by readiness and un-gated) through the whole procedure; the real 1460-day gated clock's increment
over fixed5 must beat the random-period p95 pooled and in 2021-22.

Candidates (fixed before the run; none added after):
  C2b   vr26_104w        = study8_multiscale.scale_features(levels(P), s = 13)["btcd_vr"] on the weekly panel: the same function
                           and the same 2s / 8s windows (26 / 104 bars) that produced the s = 91 transfer on the daily grid.
  C2bg  vr26_104w_gated  = C2b x 1[C2b < trailing 104-week 20th percentile of C2b at t] (the dynamics-rule conditional).
  C1g / C1u              = the real halving clock of round 9 (study9_candidates.clock_cols: gate, gate x sin, gate x cos with
                           phase = 2 pi days_since_halving / 1460; un-gated sin / cos), rerun here only as the clock-decoy target.

Design. Round-9 paired protocol, by import from study9_candidates (run_spec, score, paired_all, loo_diff, subset_scores,
era_context, criteria, perm_positions, clock_cols) and study8_honest / study8_tda_sig / study8_common underneath: weekly panel,
expanding window, refit 13 weeks, labels withheld 26 weeks, common rows (every model and fixed5 forecast on the same rows; a
candidate whose history starts late shortens the rows and says so), paired 26-week block and episode bootstraps against
fixed5 pooled, by era, era-stratified and on fresh-start rows, Brier vs the training-window base rate, sign at every refit,
within-era dwell-time permutations, shifted-target nulls through the procedure, matched-random-walk decoy features, episode
leave-one-out with 26-week run-ups, the daily-scale marginal of C2b at 5, 21 and 91 days on the same rows (diagnostic).

Success (pre-registered, evaluated as written): the round-9 four criteria for fixed5 + C2b and for fixed5 + C2bg; for the
clock: the real gated clock's increment over fixed5 beats the random-period decoys' p95 pooled AND in 2021-22.

  python3 research/btcd_fractal/study10_sixth.py --data research/btcd_fractal/data --out research/btcd_fractal/out10/sixth [--nulls N] [--fast]

Point in time. Every fitted object (z-scores, logistic weights, training base rate) is fitted on the training window of its
refit only; labels enter training 26 weeks after their row; C2b at row t uses weekly closes up to t (the multiscale windows
end at t-1, closed-left); the compression threshold is the 20th percentile of C2b over the 104 weeks ending at t; the ATH is
a running max over the full BTCUSD history; the clock uses past halvings and the published next date only; the partial
current week is excluded from the panel altogether (no feature, no label, no reading). Nulls, bootstraps and the LOO run
after all predictions are frozen and feed no fit. The truncation test rebuilds the whole pipeline on the daily panel cut at
20 random Sundays and asserts features and predictions are unchanged. No network; aggregates only; none of the round-10
liquidity series (CNM2 .. STABLES) is read here, so the module runs the same with any subset of them on disk.
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
import study8_honest as H  # noqa: E402  (ath_drawdown, perm_blocks, apply_order, n_arrangements, psum, pfmt, era_mask, era_strat_auc, paired_block_boot, run_const)
import study8_multiscale as M  # noqa: E402  (levels, scale_features: the vol ratio btcd_vr = log(std over 2s bars / std over 8s bars))
import study9_candidates as S9  # noqa: E402  (the round-9 paired protocol: run_spec, score, paired_all, loo_diff, subset_scores, era_context, criteria, clock_cols, perm_positions, say, fmt)
import study8_tda_sig as T  # noqa: E402  (paired_boot for the own-row supplement)

# ------------------------------------------------------------------------------------------- pre-registered constants
TARGET = S9.TARGET                           # fall5_26w
SIDE_TARGETS = S9.SIDE_TARGETS               # fall10_26w (binary), y13 (continuous)
VR_S = 13                                    # weekly bars: scale_features windows 2s / 8s = 26 / 104 weeks (= s 91 on the daily grid: 182 / 728 days)
VR_DAILY_SCALES = (5, 21, 91)                # the daily-scale marginal (10/40, 42/168, 182/728 days) on the same rows
Q_WINDOW, Q_LEVEL = 104, 0.20                # vol-compression gate: C2b below its trailing 104-week 20th percentile at t
PERIOD_DAYS = S9.PERIOD_DAYS                 # 1460: the real clock
PERIOD_LO, PERIOD_HI = 600.0, 2200.0         # decoy clocks: random period, uniform
CLOCK_ANCHOR = pd.Timestamp("2012-11-28")    # decoy phase anchored at the first halving
CLOCK_SEED = 2012                            # the decoy periods' seed (printed)
GATE_DD = S9.GATE_DD                         # readiness gate: BTC within 5% of its true all-time high (and M2 y/y > 0)
DATA_CUT = S9.DATA_CUT                       # 2016-06-01 panel start
EVAL_FROM = S9.EVAL_FROM                     # 2019-01-01
RUNUP = S9.RUNUP                             # 26
C2B = ["vr26_104w"]
C2BG = ["vr26_104w_gated"]
C1G, C1U = S9.C1G, S9.C1U
SPECS = {"fixed5": SIGNALS, "fixed5+C2b": SIGNALS + C2B, "fixed5+C2bg": SIGNALS + C2BG,
         "fixed5+C1g": SIGNALS + C1G, "fixed5+C1u": SIGNALS + C1U, "C2b": C2B, "C2bg": C2BG}
# Supplements beside the registered candidates (reported with both bands, never a criterion, not in the common-row mask):
#   fixed5+C2bg0   the same gated term with the gate's undefined weeks (before its 104-week percentile exists) read as 'off' (term 0)
#                  instead of NaN, so the model keeps fixed5's training rows: separates the term from the lost 2017-18 history.
#   fixed5+C2b_d91 round 8's daily-grid s = 91 ratio (182 / 728 days, study8_multiscale on the daily panel) read on the Sundays:
#                  the feature the plan's parenthesis names; the registered candidate is the weekly-increment form.
#   fixed5+gate    the readiness gate alone (no sin / cos): what the gated clock's increment owes to the gate term.
C2BG0 = ["vr26_104w_gated0"]
VRD91 = ["vr_d91"]
SUPP_SPECS = {"fixed5+C2bg0": SIGNALS + C2BG0, "fixed5+C2b_d91": SIGNALS + VRD91, "fixed5+gate": SIGNALS + ["gate"]}
CANDS = ["fixed5+C2b", "fixed5+C2bg", "fixed5+C1g", "fixed5+C1u"]
CRIT_CANDS = ["fixed5+C2b", "fixed5+C2bg"]                       # the four criteria are registered for these two
NULL_SPECS = ["fixed5"] + CANDS
CLOCK_SPECS = {"fixed5+C1g": SIGNALS + C1G, "fixed5+C1u": SIGNALS + C1U}
MIN_DRAWS = H.MIN_DRAWS_FOR_P                # 50
ENUM_UP_TO = H.ENUMERATE_UP_TO               # 120
ERA_NAMES = [e[0] for e in C.ERAS]
POOLED_ERA = S9.POOLED_ERA
OPTIONAL_SERIES = ["CNM2", "EUM2", "JPM2", "GBM2", "USDCNY", "EURUSD", "USDJPY", "GBPUSD", "FEDBS", "RRP", "TGA", "USDC.D", "STABLES"]
say, fmt = S9.say, S9.fmt
_G = {}


# ------------------------------------------------------------------------------------------- candidate features
def c2b_series(P):
    """C2b through study8_multiscale.scale_features at s = 13 on the weekly panel: btcd_vr = log(std of 1-bar logit increments
    over 2s = 26 bars / over 8s = 104 bars), both windows closed-left (ending at t-1, as that function shifts them)."""
    return M.scale_features(M.levels(P), VR_S)["btcd_vr"]


def compression_gate(vr):
    """1 when C2b is below the 20th percentile of its own trailing 104 weeks ending at t (inclusive); NaN until 104 weeks exist."""
    q = vr.rolling(Q_WINDOW, min_periods=Q_WINDOW).quantile(Q_LEVEL)
    return (vr < q).astype(float).where(q.notna() & vr.notna()), q


def period_clock_cols(index, gate, period, anchor=CLOCK_ANCHOR):
    """A strictly periodic clock of `period` days anchored at `anchor`: gate, gate x sin, gate x cos, sin, cos (the same column
    names as study9_candidates.clock_cols so the clock specs run unchanged)."""
    ph = 2 * np.pi * np.asarray((index - anchor).days, float) / float(period)
    s, c = np.sin(ph), np.cos(ph)
    g = np.asarray(gate, float)
    return pd.DataFrame({"gate": g, "gate_sin": g * s, "gate_cos": g * c, "clk_sin": s, "clk_cos": c}, index=index)


def candidate_frame(P, X):
    """fixed5 + the real clock (round 9) + C2b + gated C2b on the weekly panel (X already carries the true-ATH btc_dd_ath)."""
    F = X[SIGNALS + ["days_since_halving"]].copy()
    gate = ((X["btc_dd_ath"] >= GATE_DD) & (X["m2_yoy"] > 0)).astype(float)
    F = pd.concat([F, S9.clock_cols(X.index, X["days_since_halving"].values, gate.values)], axis=1)
    vr = c2b_series(P)
    vg, q = compression_gate(vr)
    F[C2B[0]] = vr.values
    F["vgate"] = vg.values
    F["vq20"] = q.values
    F[C2BG[0]] = (vr * vg).values
    F[C2BG0[0]] = (vr * vg.fillna(0.0)).where(vr.notna()).values      # supplement: gate undefined -> off (0), not NaN
    return F


def train_positives_at_refits(F, Y, cols, target, start="2019-01-06", refit_weeks=13, min_train=60):
    """Mirror of study8_common.walk_forward's training-row selection: for every refit, the test block it covers and the number
    of positive labels among its training rows (rows before t minus the label lag with a finite label and finite features).
    A refit with no positive label is a degenerate logistic fit whose ranking carries no information about the term."""
    lag, step = C.bars(26 if "26w" in target else 13, "W"), C.bars(refit_weeks, "W")
    idx, Xv, yv = F.index, F[cols].values.astype(float), Y[target].values.astype(float)
    t, out = int(np.searchsorted(idx, pd.Timestamp(start))), []
    while t < len(idx):
        tr = np.arange(0, max(0, t - lag))
        tr = tr[np.isfinite(yv[tr]) & np.isfinite(Xv[tr]).all(1)]
        te_end = min(t + step, len(idx))
        if len(tr) >= min_train:
            out.append({"t": idx[t], "tEnd": idx[te_end - 1], "nTrain": int(len(tr)), "trainPositives": int((yv[tr] > 0.5).sum())})
        t = te_end
    return out


def build_all(D, data_dir, last_complete):
    """The whole feature / target pipeline from the daily panel (main run and truncation test)."""
    P_full = C.panel(D, "W")
    X_full, _ = C.features(P_full, "W")
    dd_harness = X_full["btc_dd_ath"].copy()
    X_full["btc_dd_ath"] = H.ath_drawdown(data_dir, X_full.index)
    F_full = candidate_frame(P_full, X_full)                  # C2b and its gate need the 2014-04.. history before the panel cut
    F_full[VRD91[0]] = M.scale_features(M.levels(D), 91)["btcd_vr"].reindex(F_full.index).values   # supplement: the daily-grid s = 91 ratio read on Sundays (windows end at t-1 on the daily grid)
    keep = (X_full.index >= pd.Timestamp(DATA_CUT)) & (X_full.index <= last_complete)
    X, P, F = X_full[keep], P_full[keep], F_full[keep]
    Y = C.targets(P, "W")
    return X, P, Y, F, dd_harness[keep]


run_spec, pooled_auc, era_auc_of = S9.run_spec, S9.pooled_auc, S9.era_auc_of


# ------------------------------------------------------------------------------------------- forked null workers (the round-9 worker shape)
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
        pos = S9.perm_positions(Y, era)
        blocks = H.perm_blocks(Y[TARGET].values[pos])
        for order in orders:
            Ys = H.apply_order(Y, pos, blocks, order)
            row = {}
            for spec in NULL_SPECS:
                p, _ = run_spec(F, Ys, SPECS[spec])
                row[spec] = era_auc_of(p.where(mask), Ys[TARGET], era)
            out.append(row)
    elif kind == "clock":
        _, periods = args
        for period in periods:
            Fd = pd.concat([F[SIGNALS], period_clock_cols(F.index, F["gate"].values, period)], axis=1)
            row = {"period": round(float(period), 1)}
            for spec, cols in CLOCK_SPECS.items():
                p, _ = run_spec(Fd, Y, cols)
                p = p.where(mask)
                row[spec] = {"pooled": pooled_auc(p, Y[TARGET]), "2021-2022": era_auc_of(p, Y[TARGET], C.ERAS[1]), "strat": H.era_strat_auc(p, Y[TARGET])["eraStratAuc"]}
            out.append(row)
    elif kind == "dfeat":
        _, which, seeds = args
        P, pf5, y = _G["P_full"], _G["predsFixed5"], Y[TARGET]
        for seed in seeds:
            rng = np.random.default_rng(seed)
            x = C.level(P, "BTC.D")
            Ps = P.copy()
            Ps["BTC.D"] = 100.0 / (1 + np.exp(-C.matched_rw(x.values, rng)))      # back to pct so c2b_series reads it as BTC.D
            vr_full = c2b_series(Ps)                                               # on the full 2014-04.. history, exactly as candidate_frame builds the real column
            feat = (vr_full if which == "C2b" else vr_full * compression_gate(vr_full)[0]).reindex(F.index)   # the gate BEFORE the panel cut, as the real gate
            Fd = F[SIGNALS].copy()
            Fd["decoy"] = feat.values
            p, _ = run_spec(Fd, Y, SIGNALS + ["decoy"])
            p = p.where(mask)
            met = C.metrics(p, y, True)
            f5_same = C.metrics(pf5.where(p.notna()), y, True)                     # fixed5 on the decoy's own rows: the increment is paired by construction
            fv = feat.where(mask).dropna()
            n_lab = int((p.notna() & y.notna()).sum())
            out.append({"pooled": met.get("pooled", {}).get("auc"), "byEra": {e: met.get(e, {}).get("auc") for e in ERA_NAMES},
                        "fixed5SameRowsPooled": f5_same.get("pooled", {}).get("auc"), "fixed5SameRowsByEra": {e: f5_same.get(e, {}).get("auc") for e in ERA_NAMES},
                        "acf1": (None if fv.shape[0] < 30 or fv.std() == 0 else round(float(fv.autocorr(1)), 3)), "n": int(p.notna().sum()), "nLabelled": n_lab,
                        "rowsMatchCommon": bool(n_lab == _G["nCommonLabelled"]), "firstForecast": (str(p.first_valid_index().date()) if p.first_valid_index() is not None else None)})
    return out


def run_jobs(pool, jobs):
    return pool.map(_job, jobs) if pool else [_job(j) for j in jobs]


chunks = S9.chunks


def own_row_pair(F, Y, cand, base_mask, y, fresh, n_boot, rng, cols=None):
    """The candidate against fixed5 on every row the pair can forecast (the common rows may be shorter): block and episode
    bands pooled, block by era, fresh-start diff. A supplement beside the criteria, never a criterion."""
    pa, _ = run_spec(F, Y, SPECS[cand] if cols is None else cols)
    pb, _ = run_spec(F, Y, SIGNALS)
    m = base_mask & pa.notna() & pb.notna()
    pa, pb = pa.where(m), pb.where(m)
    fa, fb = pa.where(fresh), pb.where(fresh)
    return {"firstRow": str(m[m].index[0].date()), "n": int(m.sum()), "block": H.paired_block_boot(pa, pb, y, n_boot, rng),
            "episode": {"pooled": T.paired_episode_boot(pa, pb, y, n_boot, rng, True)},
            "fresh": {"diff": S9.point_diff(fa, fb, y), **T.paired_boot(fa, fb, y, n_boot, "W", rng, True)}}


def band(d):
    """'[q05,q95]' of a bootstrap dict."""
    return f"[{fmt(d.get('q05'))},{fmt(d.get('q95'))}]"


def side_target_metrics(F, Y, cols, tg, binary, mask):
    """Side-target metrics on the common rows; a binary target whose fit was degenerate (a refit with no positive training label
    covering common rows) is reported as not available with the AUC on the non-degenerate refits' rows beside it."""
    p, _ = run_spec(F, Y, cols, target=tg, binary=binary)
    met = C.metrics(p.where(mask), Y[tg], binary)
    if not binary:
        return met
    ref = train_positives_at_refits(F, Y, cols, tg)
    deg = [r for r in ref if r["trainPositives"] == 0 and mask.loc[r["t"]:r["tEnd"]].any()]
    if deg:
        ok = mask & (F.index > deg[-1]["tEnd"])
        met_ok = C.metrics(p.where(ok), Y[tg], binary)
        return {"pooled": {"auc": None, "n": met.get("pooled", {}).get("n"), "notAvailable": f"degenerate fit: {len(deg)} refit(s) ({deg[0]['t'].date()}..{deg[-1]['t'].date()}) had no positive {tg} label in the training window",
                           "aucAfterLastDegenerateRefit": met_ok.get("pooled", {}).get("auc"), "nAfterLastDegenerateRefit": int((ok & Y[tg].notna()).sum()), "positivesAfterLastDegenerateRefit": int(Y[tg][ok].sum()),
                           "rawAucNotQuotable": met.get("pooled", {}).get("auc")},
                "byEra": {e: r.get("auc") for e, r in met.items() if e != "pooled"}, "degenerateRefits": [str(r["t"].date()) for r in deg]}
    return met


def verdict_word(cand, crit):
    if crit[cand]["all"] == "pass":
        if cand == "fixed5+C2bg" and crit["fixed5+C2b"]["all"] != "pass":
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
    rng = np.random.default_rng(103)

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
    optional_on_disk = [n for n in OPTIONAL_SERIES if os.path.exists(os.path.join(a.data, f"{n}_1d.csv"))]
    say(f"study10_sixth  data last bar {last_utc} / {last_et} (daily close {last_bar.date()}); last complete Sunday {last_complete.date()}; provisional bars excluded {provisional}; "
        f"fast={a.fast} shift {n_shift} clocks {n_clock} (period seed {CLOCK_SEED}) within-era {n_within} boots {n_boot} decoy-features {n_dfeat} workers {a.workers}; "
        f"optional round-10 series on disk {len(optional_on_disk)}/{len(OPTIONAL_SERIES)} (none used here)")

    # ---- predictions (frozen before any null / bootstrap), the common row mask, the training-window base rate
    preds, models, refits = {}, {}, {}
    for spec, cols in SPECS.items():
        models[spec] = []
        preds[spec], refits[spec] = run_spec(F, Y, cols, keep_models=models[spec])
    base = H.run_const(X, Y, TARGET)
    base_mask = base.notna() & (F.index >= pd.Timestamp(EVAL_FROM))
    mask = base_mask.copy()
    first_own = {}
    for spec in SPECS:
        fv = preds[spec].first_valid_index()
        first_own[spec] = (str(fv.date()) if fv is not None else None)
        mask &= preds[spec].notna()
    for spec in SPECS:
        preds[spec] = preds[spec].where(mask)
    base = base.where(mask)
    y = Y[TARGET]
    first_common = str(mask[mask].index[0].date())
    lab = mask & y.notna()
    eps = C.episodes(np.where(lab, y, np.nan))
    n_pos = int(y[lab].sum())
    first_feat = {c: str(F[c].first_valid_index().date()) for c in C2B + C2BG + ["vq20"]}
    acf = {c: round(float(F[c].where(mask).dropna().autocorr(1)), 3) for c in C2B + C2BG}
    shortener = max(SPECS, key=lambda s: pd.Timestamp(first_own[s] or "2000-01-01"))
    say(f"common rows: first forecast {first_common} (fixed5 alone from {first_own['fixed5']}, fixed5+C2b from {first_own['fixed5+C2b']}, fixed5+C2bg from {first_own['fixed5+C2bg']}: the gate's trailing "
        f"104-week percentile is first finite {first_feat['vq20']}, then 60 training rows + 26-week label lag; {shortener} sets the start), n {int(mask.sum())} labelled {int(lab.sum())} positives {n_pos} "
        f"in {len(eps)} episodes; first finite C2b {first_feat[C2B[0]]}; lag-1 acf C2b {acf[C2B[0]]} gated {acf[C2BG[0]]}; compression-gate-on weeks (eval) {int((F['vgate'].where(mask) > 0).sum())}; "
        f"readiness-gate-on weeks {int((F['gate'].where(mask) > 0).sum())}")

    # ---- scores by era, pooled, stratified, fresh, Brier vs training base; paired differences against fixed5
    oos, pdiff = {}, {}
    for spec in SPECS:
        oos[spec] = S9.score(preds[spec], y, base, fresh)
        if spec != "fixed5":
            pdiff[spec] = S9.paired_all(preds[spec], preds["fixed5"], y, fresh, n_boot, rng)
    for spec in SPECS:
        r = oos[spec]
        eras = " ".join(f"{e[:4]}{e[-2:]} {fmt(r['byEra'].get(e, {}).get('auc'))}" for e in ERA_NAMES)
        d = pdiff.get(spec, {})
        dl = ("" if spec == "fixed5" else f" | vs fixed5 {fmt(d['block']['pooled'].get('diff'))} block[{fmt(d['block']['pooled'].get('q05'))},{fmt(d['block']['pooled'].get('q95'))}] "
              f"ep[{fmt(d['episode']['pooled'].get('q05'))},{fmt(d['episode']['pooled'].get('q95'))}] strat {fmt(d['strat'].get('diff'))}[{fmt(d['strat'].get('q05'))},{fmt(d['strat'].get('q95'))}] "
              f"fresh {fmt(d['fresh']['pooled'].get('diff'))}[{fmt(d['fresh']['pooled'].get('q05'))},{fmt(d['fresh']['pooled'].get('q95'))}] eras {' '.join(fmt(d['block'].get(e, {}).get('diff')) for e in ERA_NAMES)}")
        say(f"{spec:12s} auc pooled {fmt(r['byEra'].get('pooled', {}).get('auc'))} {eras} strat {fmt(r['eraStratAuc'])} fresh {fmt(r['fresh'].get('pooled'))} "
            f"brier skill vs train-base {' '.join(fmt(r['byEra'].get(e, {}).get('skillVsTrainBase'), 2) for e in ERA_NAMES + ['pooled'])}{dl}")

    # ---- own-row supplement: each candidate against fixed5 on every row the pair can forecast (the gate shortens the common set)
    own_pairs = {cand: own_row_pair(F, Y, cand, base_mask, y, fresh, n_boot, rng) for cand in CANDS}
    say("own-row supplement (pair rows from " + ", ".join(f"{k} {v['firstRow']} n{v['n']}: diff {fmt(v['block']['pooled'].get('diff'))} block{band(v['block']['pooled'])} ep{band(v['episode']['pooled'])} "
        f"eras {' '.join(fmt(v['block'].get(e, {}).get('diff')) for e in ERA_NAMES)} fresh {fmt(v['fresh'].get('diff'))}" for k, v in own_pairs.items()) + "); criteria use the common rows only")

    # ---- supplements beside the registered candidates (SUPP_SPECS): scored on the common rows against fixed5 with both bands, and
    # on the pair's own rows; none is a criterion and none enters the common-row mask.
    supp, preds_supp = {}, {}
    for spec, cols in SUPP_SPECS.items():
        p, _ = run_spec(F, Y, cols)
        preds_supp[spec] = p.where(mask)
        supp[spec] = {"cols": cols, "firstOwnForecast": (str(p.first_valid_index().date()) if p.first_valid_index() is not None else None),
                      "common": {"auc": {e: r.get("auc") for e, r in C.metrics(preds_supp[spec], y, True).items()}, **S9.paired_all(preds_supp[spec], preds["fixed5"], y, fresh, n_boot, rng)},
                      "ownRows": own_row_pair(F, Y, spec, base_mask, y, fresh, n_boot, rng, cols=cols)}
    corr_d91 = round(float(F[VRD91[0]].where(mask).corr(F[C2B[0]].where(mask))), 3)
    say("supplements on the common rows vs fixed5 (not criteria): " + "; ".join(
        f"{s} auc {fmt(v['common']['auc'].get('pooled'))} diff {fmt(v['common']['block']['pooled'].get('diff'))} block{band(v['common']['block']['pooled'])} ep{band(v['common']['episode']['pooled'])} "
        f"eras {' '.join(fmt(v['common']['block'].get(e, {}).get('diff')) for e in ERA_NAMES)} fresh {fmt(v['common']['fresh']['pooled'].get('diff'))} | own rows from {v['ownRows']['firstRow']} n{v['ownRows']['n']} diff {fmt(v['ownRows']['block']['pooled'].get('diff'))} "
        f"block{band(v['ownRows']['block']['pooled'])} ep{band(v['ownRows']['episode']['pooled'])}" for s, v in supp.items())
        + f"; corr(C2b weekly, daily s=91) on the common rows {corr_d91:.3f} (the registered candidate is the weekly-increment form; s=91 is the plan's parenthetical)")

    # ---- diagnostic beside the criteria: fixed5 fitted on the gated candidate's own training rows. The gate's column is NaN before
    # its first finite week, so the harness drops those rows from the candidate's training window but not from fixed5's; this
    # separates what the term carries from what the lost training history costs (not a criterion).
    same_train = {}
    for cand in ("fixed5+C2bg",):
        col = SPECS[cand][-1]
        Fs = F.copy()
        Fs.loc[F[col].isna(), SIGNALS] = np.nan
        pb, _ = run_spec(Fs, Y, SIGNALS)
        pb = pb.where(mask)
        cnt = {}
        for tg in (TARGET, "fall10_26w"):
            early = F.index < pd.Timestamp(first_common)
            m5 = F[SIGNALS].notna().all(axis=1) & Y[tg].notna() & early
            mg = F[SPECS[cand]].notna().all(axis=1) & Y[tg].notna() & early
            cnt[tg] = {"fixed5TrainRows": int(m5.sum()), "fixed5TrainPositives": int(Y.loc[m5, tg].sum()), "candTrainRows": int(mg.sum()), "candTrainPositives": int(Y.loc[mg, tg].sum())}
        same_train[cand] = {"trainRowsFrom": first_feat[col], "labelledRowsBeforeFirstCommonForecast": cnt,
                            "fixed5SameTrainAuc": {e: r.get("auc") for e, r in C.metrics(pb, y, True).items()},
                            "candVsFixed5SameTrain": H.paired_block_boot(preds[cand], pb, y, n_boot, rng),
                            "candVsFixed5SameTrainEpisode": T.paired_episode_boot(preds[cand], pb, y, n_boot, rng, True),
                            "fixed5SameTrainVsFixed5": H.paired_block_boot(pb, preds["fixed5"], y, n_boot, rng),
                            "fixed5SameTrainVsFixed5Episode": T.paired_episode_boot(pb, preds["fixed5"], y, n_boot, rng, True)}
    st = same_train["fixed5+C2bg"]
    say(f"same-training-rows diagnostic (fixed5 fitted on fixed5+C2bg's rows, from {st['trainRowsFrom']}; labelled rows / positives before {first_common}: fixed5 {st['labelledRowsBeforeFirstCommonForecast'][TARGET]['fixed5TrainRows']}/{st['labelledRowsBeforeFirstCommonForecast'][TARGET]['fixed5TrainPositives']}, "
        f"gated {st['labelledRowsBeforeFirstCommonForecast'][TARGET]['candTrainRows']}/{st['labelledRowsBeforeFirstCommonForecast'][TARGET]['candTrainPositives']}; fall10 positives {st['labelledRowsBeforeFirstCommonForecast']['fall10_26w']['fixed5TrainPositives']} vs {st['labelledRowsBeforeFirstCommonForecast']['fall10_26w']['candTrainPositives']}): "
        f"fixed5-same-train auc pooled {fmt(st['fixed5SameTrainAuc'].get('pooled'))} eras {' '.join(fmt(st['fixed5SameTrainAuc'].get(e)) for e in ERA_NAMES)}; fixed5+C2bg minus it {fmt(st['candVsFixed5SameTrain']['pooled'].get('diff'))} "
        f"block{band(st['candVsFixed5SameTrain']['pooled'])} ep{band(st['candVsFixed5SameTrainEpisode'])} eras {' '.join(fmt(st['candVsFixed5SameTrain'].get(e, {}).get('diff')) for e in ERA_NAMES)}; it minus fixed5 {fmt(st['fixed5SameTrainVsFixed5']['pooled'].get('diff'))} "
        f"block{band(st['fixed5SameTrainVsFixed5']['pooled'])} ep{band(st['fixed5SameTrainVsFixed5Episode'])} (the lost 2017-18 training history's cost; a diagnostic, not a criterion)")

    # ---- the compression gate's own condition: gate-on and gate-off rows scored separately (the conditional's target rows)
    vgate = F["vgate"].where(mask)
    gated = {"on": S9.subset_scores(preds, y, vgate > 0, ["fixed5", "fixed5+C2b", "fixed5+C2bg", "C2b", "C2bg"], n_boot, rng),
             "off": S9.subset_scores(preds, y, vgate == 0, ["fixed5", "fixed5+C2b", "fixed5+C2bg", "C2b", "C2bg"], n_boot, rng)}
    for side in ("on", "off"):
        rr = gated[side]
        cnt = rr["fixed5"]["rowsByEra"]
        sub = (vgate > 0) if side == "on" else (vgate == 0)
        runs = sum(cnt[e]["positiveRuns"] for e in ERA_NAMES)
        rr["scoreable"] = bool(runs >= 3)                                             # fewer than 3 positive runs: a band over one or two events is not a band
        for s in rr:
            if isinstance(rr[s], dict) and "vsFixed5" in rr[s]:
                rr[s]["vsFixed5Episode"] = T.paired_episode_boot(preds[s].where(sub), preds["fixed5"].where(sub), y, n_boot, rng, True)
        say(f"compression gate-{side} rows (n {rr['fixed5']['n'].get('pooled')}, base {fmt(y[mask & sub].mean(), 2)}; by era n/pos/positive runs "
            + " ".join(f"{cnt[e]['n']}/{cnt[e]['positives']}/{cnt[e]['positiveRuns']}" for e in ERA_NAMES) + f"; {'scoreable' if rr['scoreable'] else 'NOT scoreable: fewer than 3 positive runs, bands are one or two events'}): " + "; ".join(
            f"{s} auc {fmt(rr[s]['auc'].get('pooled'))}" + ("" if s == "fixed5" else f" vs fixed5 {fmt(rr[s]['vsFixed5'].get('diff'))} block{band(rr[s]['vsFixed5'])} ep{band(rr[s]['vsFixed5Episode'])} eras {' '.join(fmt(v) for v in rr[s]['vsFixed5ByEra'].values())}")
            for s in rr if isinstance(rr[s], dict)))

    # ---- C2b: sign at every refit, marginal AUC weekly and at daily scale (5, 21, 91 d) on the same rows
    c2b = {"marginalAuc": {}, "signAtRefits": {}}
    for spec, col in (("fixed5+C2b", C2B[0]), ("fixed5+C2bg", C2BG[0])):
        j = 1 + SPECS[spec].index(col)
        signs = [int(np.sign(w[j])) for (_, _, w) in models[spec]]
        c2b["signAtRefits"][spec] = {"signs": "".join("+" if s > 0 else ("-" if s < 0 else "0") for s in signs), "refitDates": [r["t"] for r in refits[spec]],
                                     "nPositive": int(sum(s > 0 for s in signs)), "nNegative": int(sum(s < 0 for s in signs)), "coefLast": round(float(models[spec][-1][2][j]), 3)}
    c2b["marginalAuc"]["weekly 26w/104w (C2b)"] = {e: r.get("auc") for e, r in C.metrics(F[C2B[0]].where(mask), y, True).items()}
    c2b["marginalAuc"]["weekly gated (C2bg)"] = {e: r.get("auc") for e, r in C.metrics(F[C2BG[0]].where(mask), y, True).items()}
    lev = M.levels(D)
    for s in VR_DAILY_SCALES:
        vr_d = M.scale_features(lev, s)["btcd_vr"].reindex(F.index)      # study8_multiscale btcd_vr at scale s on the daily grid, read on the Sundays
        c2b["marginalAuc"][f"daily s={s} ({2 * s}/{8 * s}d)"] = {e: r.get("auc") for e, r in C.metrics(vr_d.where(mask), y, True).items()}
    d_t = C.level(P, "BTC.D").diff()
    vr_t = np.log(d_t.rolling(2 * VR_S).std() / d_t.rolling(8 * VR_S).std()).replace([np.inf, -np.inf], np.nan)
    c2b["marginalAuc"]["weekly 26w/104w windows ending at t (round-9 diagnostic form)"] = {e: r.get("auc") for e, r in C.metrics(vr_t.where(mask), y, True).items()}
    c2b["marginalAucAloneWalkForward"] = {spec: {e: r.get("auc") for e, r in oos[spec]["byEra"].items()} for spec in ("C2b", "C2bg")}
    c2b["definition"] = ("study8_multiscale.scale_features(levels(P_weekly), s=13)['btcd_vr'] = log(std of 1-week logit increments over 26 weeks / over 104 weeks), "
                         "windows ending at t-1 (closed-left, as the multiscale function shifts them); gated = C2b x 1[C2b < 20th percentile of its trailing 104 weeks ending at t]")
    sg = c2b["signAtRefits"]
    say(f"C2b sign at {len(sg['fixed5+C2b']['signs'])} refits: {sg['fixed5+C2b']['signs']} ({sg['fixed5+C2b']['nPositive']}+ / {sg['fixed5+C2b']['nNegative']}-; last coef {sg['fixed5+C2b']['coefLast']}); "
        f"gated term: {sg['fixed5+C2bg']['signs']} ({sg['fixed5+C2bg']['nPositive']}+ / {sg['fixed5+C2bg']['nNegative']}-; last coef {sg['fixed5+C2bg']['coefLast']})")
    say("C2b marginal AUC on the common rows (pooled | by era): " + " | ".join(f"{k} {fmt(v.get('pooled'))} ({' '.join(fmt(v.get(e)) for e in ERA_NAMES)})" for k, v in c2b["marginalAuc"].items())
        + f"; alone walk-forward C2b {fmt(oos['C2b']['byEra'].get('pooled', {}).get('auc'))} C2bg {fmt(oos['C2bg']['byEra'].get('pooled', {}).get('auc'))} (daily rows are a diagnostic beside the weekly candidate)")

    # ---- nulls and decoys through the whole procedure (forked workers; predictions above are already frozen)
    phase = {"predictionsBootstrapsSec": round(time.time() - t0, 1)}
    _G.update({"F": F, "Y": Y, "mask": mask, "P_full": C.panel(D, "W").loc[:last_complete],      # the provisional bar enters no decoy increment pool either
               "predsFixed5": preds["fixed5"], "nCommonLabelled": int(lab.sum())})
    ctx = get_context("fork")
    pool = ctx.Pool(a.workers) if a.workers > 1 else None
    try:
        jobs = [("shift", 1000 + i, len(c)) for i, c in enumerate(chunks(list(range(n_shift)), a.workers * 2)) if len(c)]
        shift_raw = [r for part in run_jobs(pool, jobs) for r in part]
        perm_raw, arrangements = {}, {}
        for era in C.ERAS + [POOLED_ERA]:
            pos = S9.perm_positions(Y, era)
            nb = len(H.perm_blocks(Y[TARGET].values[pos]))
            K = H.n_arrangements(nb)
            exact = K <= max(n_within, ENUM_UP_TO)
            orders = [np.array(o) for o in itertools.permutations(range(nb))] if exact else [rng.permutation(nb) for _ in range(n_within)]
            arrangements[era[0]] = {"blocks": nb, "distinctArrangements": (int(K) if nb <= 20 else f"{nb}!"), "enumerated": exact, "draws": len(orders)}
            jobs = [("perm", era, c) for c in chunks(orders, a.workers * 2) if len(c)]
            perm_raw[era[0]] = [r for part in run_jobs(pool, jobs) for r in part]
        prng = np.random.default_rng(CLOCK_SEED)
        periods = [float(p) for p in prng.uniform(PERIOD_LO, PERIOD_HI, size=n_clock)]
        jobs = [("clock", c) for c in chunks(periods, a.workers * 2) if len(c)]
        clock_raw = [r for part in run_jobs(pool, jobs) for r in part]
        periodic_real = run_jobs(pool, [("clock", [PERIOD_DAYS])])[0][0]      # the strictly periodic 1460-day clock (diagnostic row, not a decoy)
        dfeat_raw = {}
        for which in ("C2b", "C2bg"):
            seeds = [5000 + (0 if which == "C2b" else 500) + i for i in range(n_dfeat)]
            jobs = [("dfeat", which, c) for c in chunks(seeds, a.workers * 2) if len(c)]
            dfeat_raw[which] = [r for part in run_jobs(pool, jobs) for r in part]
    finally:
        if pool:
            pool.close()
            pool.join()
    phase["nullsDecoysSec"] = round(time.time() - t0 - phase["predictionsBootstrapsSec"], 1)

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
    for spec in CANDS:
        null["withinEraIncrement"][spec] = {}
        for era in C.ERAS + [POOLED_ERA]:
            vals = [r[spec] - r["fixed5"] for r in perm_raw[era[0]] if r[spec] is not None and r["fixed5"] is not None]
            null["withinEraIncrement"][spec][era[0]] = H.psum(pdiff[spec]["block"].get(era[0], {}).get("diff"), vals, exact=arrangements[era[0]]["enumerated"])
    best_real = max(v for v in (pdiff[s]["block"]["pooled"].get("diff") for s in CRIT_CANDS) if v is not None)
    best_null = [max(r[s] - r["fixed5"] for s in CRIT_CANDS) for r in shift_raw if all(r[s] is not None for s in ["fixed5"] + CRIT_CANDS)]
    null["shiftIncrementMaxOverCandidates"] = {**H.psum(best_real, best_null), "bestCandidate": max(CRIT_CANDS, key=lambda s: pdiff[s]["block"]["pooled"].get("diff") or -9),
                                               "note": "max over the two C2b candidate models of the increment over fixed5, per shifted-label draw: a family-wise null for 'either adds'"}
    def floor_of(era):
        a = arrangements[era]
        return f" floor {a['distinctArrangements']} arrangements, min p {fmt(1.0 / a['distinctArrangements'])}, any era AUC above the 5th-best arrangement scores {fmt(5.0 / a['distinctArrangements'])}" if a["enumerated"] else ""
    for spec in NULL_SPECS:
        w = null["withinEra"][spec]
        say(f"within-era dwell-time permutation {spec:11s}: " + "  ".join(f"{e[:4]}{e[-2:]} auc {fmt(w[e].get('real'))} med {fmt(w[e].get('nullMedian'))} p95 {fmt(w[e].get('nullP95'))} {H.pfmt(w[e])}" for e in ERA_NAMES + ['pooled'])
            + (f" | shift null pooled med {fmt(null['shift'][spec].get('nullMedian'))} p95 {fmt(null['shift'][spec].get('nullP95'))} {H.pfmt(null['shift'][spec])} (fixed5 at chance under shifted labels, so a sixth term's increment null below is wide by construction)" if spec == "fixed5" else
               f" | shift: auc {H.pfmt(null['shift'][spec])}, increment over fixed5 med {fmt(null['shiftIncrement'][spec].get('nullMedian'))} p95 {fmt(null['shiftIncrement'][spec].get('nullP95'))} {H.pfmt(null['shiftIncrement'][spec])}"))
    say("within-era null floors: " + "; ".join(f"{e[:4]}{e[-2:]}{floor_of(e) or ' random draws ' + str(arrangements[e]['draws']) + ' of ' + str(arrangements[e]['distinctArrangements'])}" for e in ERA_NAMES)
        + "; the shifted-label increment null is uninformative (the base loses its skill): read the increment against the within-era increment null below")
    wi = null["withinEraIncrement"]
    say("within-era null of the INCREMENT over fixed5 (diagnostic beside (iv), same permuted labels): " + "; ".join(
        f"{s.replace('fixed5+', '')} " + " ".join(f"{e[:4]}{e[-2:]} {fmt(wi[s][e].get('real'))} p95 {fmt(wi[s][e].get('nullP95'))} {H.pfmt(wi[s][e])}" for e in ERA_NAMES) for s in CANDS)
        + f" | family-wise shift null of the best C2b increment ({null['shiftIncrementMaxOverCandidates']['bestCandidate']} {fmt(best_real)}): med {fmt(null['shiftIncrementMaxOverCandidates'].get('nullMedian'))} p95 {fmt(null['shiftIncrementMaxOverCandidates'].get('nullP95'))} {H.pfmt(null['shiftIncrementMaxOverCandidates'])}")

    # ---- adversary: random-period decoy clocks (the power round 9's random-anchor family lacked)
    f5p, f521 = oos["fixed5"]["byEra"]["pooled"]["auc"], oos["fixed5"]["byEra"].get("2021-2022", {}).get("auc")
    decoy = {"n": len(clock_raw), "periodSeed": CLOCK_SEED, "periodsUniformDays": [PERIOD_LO, PERIOD_HI], "anchor": str(CLOCK_ANCHOR.date()), "realPeriodDays": PERIOD_DAYS,
             "realPeriodPercentileAmongDrawn": (round(float(np.mean(np.array(periods) <= PERIOD_DAYS)), 3) if periods else None),
             "drawnPeriodsMinMedianMax": ([round(min(periods), 1), round(float(np.median(periods)), 1), round(max(periods), 1)] if periods else None), "models": {}}
    for spec in CLOCK_SPECS:
        realp, real21 = pdiff[spec]["block"]["pooled"].get("diff"), pdiff[spec]["block"].get("2021-2022", {}).get("diff")
        rows = [r for r in clock_raw if r[spec]["pooled"] is not None and f5p is not None]
        incp = [r[spec]["pooled"] - f5p for r in rows]
        rows21 = [r for r in clock_raw if r[spec]["2021-2022"] is not None and f521 is not None]
        inc21 = [r[spec]["2021-2022"] - f521 for r in rows21]
        row = {"incrementPooled": H.psum(realp, incp), "increment2021-2022": H.psum(real21, inc21),
               "aucPooled": H.psum(oos[spec]["byEra"]["pooled"]["auc"], [r[spec]["pooled"] for r in rows]),
               "auc2021-2022": H.psum(oos[spec]["byEra"].get("2021-2022", {}).get("auc"), [r[spec]["2021-2022"] for r in rows21]),
               "strat": H.psum(oos[spec]["eraStratAuc"], [r[spec]["strat"] for r in clock_raw if r[spec]["strat"] is not None])}
        if incp:
            k = int(np.argmax(incp))
            row["bestDecoyPooled"] = {"periodDays": rows[k]["period"], "increment": round(float(incp[k]), 3)}
            row["realIncrementRankAmongDecoysPooled"] = (round(float(np.mean(np.array(incp) < realp)), 3) if realp is not None else None)
        if inc21:
            k = int(np.argmax(inc21))
            row["bestDecoy2021-2022"] = {"periodDays": rows21[k]["period"], "increment": round(float(inc21[k]), 3)}
            row["realIncrementRankAmongDecoys2021-2022"] = (round(float(np.mean(np.array(inc21) < real21)), 3) if real21 is not None else None)
        row["periodicRealPeriodNoRestart"] = {"pooledIncrement": (None if periodic_real[spec]["pooled"] is None or f5p is None else round(periodic_real[spec]["pooled"] - f5p, 3)),
                                              "increment2021-2022": (None if periodic_real[spec]["2021-2022"] is None or f521 is None else round(periodic_real[spec]["2021-2022"] - f521, 3)),
                                              "note": "the same 1460-day period anchored at 2012-11-28 without the halving restarts: the decoy family's member at the real period"}
        gp, g21 = supp["fixed5+gate"]["common"]["block"]["pooled"].get("diff"), supp["fixed5+gate"]["common"]["block"].get("2021-2022", {}).get("diff")
        gap, ga21 = supp["fixed5+gate"]["common"]["auc"].get("pooled"), supp["fixed5+gate"]["common"]["auc"].get("2021-2022")
        row["gateOnly"] = {"incrementPooled": gp, "increment2021-2022": g21, "clockMinusGateOnlyPooled": (None if realp is None or gp is None else round(realp - gp, 3)),
                           "clockMinusGateOnly2021-2022": (None if real21 is None or g21 is None else round(real21 - g21, 3)),
                           "decoysOverGateOnlyPooled": H.psum((None if realp is None or gp is None else realp - gp), [r[spec]["pooled"] - gap for r in rows if gap is not None]),
                           "decoysOverGateOnly2021-2022": H.psum((None if real21 is None or g21 is None else real21 - g21), [r[spec]["2021-2022"] - ga21 for r in rows21 if ga21 is not None]),
                           "note": "fixed5 + the readiness gate alone (no sin / cos) on the same rows: the part of every gated clock's increment that is the gate term, shared by the real clock and every decoy"}
        row["quotable"] = bool(len(incp) >= MIN_DRAWS and len(inc21) >= MIN_DRAWS)
        row["beatsP95Pooled"] = bool(realp is not None and incp and realp > row["incrementPooled"]["nullP95"])
        row["beatsP95_2021-2022"] = bool(real21 is not None and inc21 and real21 > row["increment2021-2022"]["nullP95"])
        row["beatsP95Both"] = bool(row["beatsP95Pooled"] and row["beatsP95_2021-2022"])
        row["status"] = ("not identifiable" if not row["quotable"] else ("pass" if row["beatsP95Both"] else "fail"))
        decoy["models"][spec] = row
    g = decoy["models"]["fixed5+C1g"]
    pmm = decoy["drawnPeriodsMinMedianMax"] or ["na"] * 3
    say(f"clock decoy (random period {PERIOD_LO:.0f}..{PERIOD_HI:.0f} d, seed {CLOCK_SEED}, anchor {CLOCK_ANCHOR.date()}, n {decoy['n']}; real period {PERIOD_DAYS:.0f} d sits at the {fmt(decoy['realPeriodPercentileAmongDrawn'], 2)} quantile of the drawn periods "
        f"[min {pmm[0]} median {pmm[1]} max {pmm[2]}]): " + "; ".join(
        f"{s} increment over fixed5 pooled {fmt(r['incrementPooled'].get('real'))} vs decoy med {fmt(r['incrementPooled'].get('nullMedian'))} p95 {fmt(r['incrementPooled'].get('nullP95'))} {H.pfmt(r['incrementPooled'])}, "
        f"2021-22 {fmt(r['increment2021-2022'].get('real'))} vs p95 {fmt(r['increment2021-2022'].get('nullP95'))} {H.pfmt(r['increment2021-2022'])} -> beats both {r['beatsP95Both']}" for s, r in decoy["models"].items()))
    say("clock decoy detail: " + "; ".join(
        f"{s}: real increment ranks above {fmt(r.get('realIncrementRankAmongDecoysPooled'), 2)} of decoys pooled / {fmt(r.get('realIncrementRankAmongDecoys2021-2022'), 2)} in 2021-22; best decoy pooled period {r.get('bestDecoyPooled', {}).get('periodDays')} d "
        f"increment {fmt(r.get('bestDecoyPooled', {}).get('increment'))}, best in 2021-22 period {r.get('bestDecoy2021-2022', {}).get('periodDays')} d increment {fmt(r.get('bestDecoy2021-2022', {}).get('increment'))}; "
        f"strictly periodic 1460 d without halving restarts: pooled {fmt(r['periodicRealPeriodNoRestart']['pooledIncrement'])} 2021-22 {fmt(r['periodicRealPeriodNoRestart']['increment2021-2022'])}" for s, r in decoy["models"].items()))
    go = g["gateOnly"]
    say(f"clock attribution: fixed5+gate alone (no sin/cos) increment over fixed5 pooled {fmt(go['incrementPooled'])} 2021-22 {fmt(go['increment2021-2022'])}; the real gated clock minus gate-only pooled {fmt(go['clockMinusGateOnlyPooled'])} 2021-22 {fmt(go['clockMinusGateOnly2021-2022'])}; "
        f"decoy gated clocks over gate-only: pooled med {fmt(go['decoysOverGateOnlyPooled'].get('nullMedian'))} p95 {fmt(go['decoysOverGateOnlyPooled'].get('nullP95'))}, 2021-22 med {fmt(go['decoysOverGateOnly2021-2022'].get('nullMedian'))} p95 {fmt(go['decoysOverGateOnly2021-2022'].get('nullP95'))} "
        f"(what the sin/cos terms add at the real period and at random periods once the gate term is removed)")

    # ---- adversary: decoy features (the same statistic on matched random walks of the BTC.D logit)
    dfeat = {}
    for which, cand in (("C2b", "fixed5+C2b"), ("C2bg", "fixed5+C2bg")):
        rows_all = dfeat_raw[which]
        rows = [r for r in rows_all if r["rowsMatchCommon"]]                      # a decoy that forecasts on other rows is not comparable and is left out (counted)
        inc = [r["pooled"] - r["fixed5SameRowsPooled"] for r in rows if r["pooled"] is not None and r["fixed5SameRowsPooled"] is not None]      # paired on the decoy's own rows
        inc_era = {e: [r["byEra"][e] - r["fixed5SameRowsByEra"][e] for r in rows if r["byEra"].get(e) is not None and r["fixed5SameRowsByEra"].get(e) is not None] for e in ERA_NAMES}
        acfs = [r["acf1"] for r in rows if r["acf1"] is not None]
        inc_all = [r["pooled"] - r["fixed5SameRowsPooled"] for r in rows_all if r["pooled"] is not None and r["fixed5SameRowsPooled"] is not None]   # every decoy, each paired on its own rows
        dfeat[which] = {"n": len(rows), "nNotComparable": len(rows_all) - len(rows), "firstForecasts": sorted(set(r["firstForecast"] for r in rows_all if r["firstForecast"])),
                        "labelledRowsOfDecoys": sorted(set(r["nLabelled"] for r in rows_all)), "nCommonLabelled": int(lab.sum()),
                        "allDecoysPairedOnOwnRows": {"n": len(inc_all), "decoyMedian": (round(float(np.median(inc_all)), 3) if inc_all else None), "decoyMax": (round(float(np.max(inc_all)), 3) if inc_all else None),
                                                     "note": "a decoy whose random walk saturates the logit clip has zero-variance windows (C2b undefined there) and forecasts on fewer rows; here each decoy is differenced against fixed5 on its own rows"},
                        "acf1Real": acf[SPECS[cand][-1]], "acf1DecoyMean": (round(float(np.mean(acfs)), 3) if acfs else None),
                        "incrementOverFixed5": {"real": pdiff[cand]["block"]["pooled"].get("diff"), "realBlockQ05": pdiff[cand]["block"]["pooled"].get("q05"), "realBlockQ95": pdiff[cand]["block"]["pooled"].get("q95"),
                                                "realEpisodeQ05": pdiff[cand]["episode"]["pooled"].get("q05"), "realEpisodeQ95": pdiff[cand]["episode"]["pooled"].get("q95"),
                                                "decoyMedian": (round(float(np.median(inc)), 3) if inc else None), "decoyP95": (round(float(np.quantile(inc, 0.95)), 3) if inc else None),
                                                "decoyMax": (round(float(np.max(inc)), 3) if inc else None), "n": len(inc),
                                                "realAboveDecoyShare": (round(float(np.mean(np.array(inc) < pdiff[cand]["block"]["pooled"].get("diff"))), 3) if inc and pdiff[cand]["block"]["pooled"].get("diff") is not None else None)},
                        "incrementByEra": {e: {"real": pdiff[cand]["block"].get(e, {}).get("diff"), "decoyMedian": (round(float(np.median(v)), 3) if v else None), "decoyMax": (round(float(np.max(v)), 3) if v else None)} for e, v in inc_era.items()},
                        "note": ("C2b (and its compression gate, built on the full 2014-04.. history before the panel cut exactly as the real column) computed on a matched random walk of the BTC.D logit "
                                 "(study8_common.matched_rw: block 13 w, random signs, increments from the complete weekly bars only), run as fixed5 + decoy; the increment is decoy AUC minus fixed5 AUC on the decoy's own rows, "
                                 "and a decoy whose forecast rows differ from the common rows is not comparable and is excluded")}
    say("decoy feature (matched random walk, same statistic, paired on identical rows): " + "; ".join(
        f"{w}: acf1 real {d['acf1Real']} decoy {d['acf1DecoyMean']}, increment over fixed5 real {fmt(d['incrementOverFixed5']['real'])} block[{fmt(d['incrementOverFixed5']['realBlockQ05'])},{fmt(d['incrementOverFixed5']['realBlockQ95'])}] "
        f"ep[{fmt(d['incrementOverFixed5']['realEpisodeQ05'])},{fmt(d['incrementOverFixed5']['realEpisodeQ95'])}] vs decoy median {fmt(d['incrementOverFixed5']['decoyMedian'])} p95 {fmt(d['incrementOverFixed5']['decoyP95'])} max {fmt(d['incrementOverFixed5']['decoyMax'])} "
        f"(real above {fmt(d['incrementOverFixed5']['realAboveDecoyShare'], 2)} of decoys; n{d['n']}{'' if d['n'] >= MIN_DRAWS else '!'}, {d['nNotComparable']} on other rows left out; all {d['allDecoysPairedOnOwnRows']['n']} each paired on its own rows: median {fmt(d['allDecoysPairedOnOwnRows']['decoyMedian'])} max {fmt(d['allDecoysPairedOnOwnRows']['decoyMax'])})"
        for w, d in dfeat.items()))

    # ---- adversary: episode leave-one-out with the 26-week run-up
    loo = {cand: S9.loo_diff(preds[cand], preds["fixed5"], y) for cand in CANDS}
    say("episode LOO (each label episode + 26-week run-up dropped; increment over fixed5 on the rest): " + "; ".join(
        f"{c} min {fmt(l['min'])} at {l['minEpisode']} max {fmt(l['max'])} at {l['maxEpisode']}" for c, l in loo.items()) + f" ({loo[CANDS[0]]['nEpisodes']} episodes)")

    # ---- criteria as pre-registered
    smoke = any(not s.get("quotable", False) for spec in CRIT_CANDS for s in null["withinEra"][spec].values()) or n_shift < MIN_DRAWS or n_clock < MIN_DRAWS
    ctx = S9.era_context(preds, y, mask, fresh)
    crit = {cand: S9.criteria(cand, pdiff[cand], null["withinEra"][cand], smoke, ctx) for cand in CRIT_CANDS}
    crit_diag = {cand: S9.criteria(cand, pdiff[cand], null["withinEra"][cand], smoke, ctx) for cand in ("fixed5+C1g", "fixed5+C1u")}   # beside, not registered for the clock
    verdicts = {cand: verdict_word(cand, crit) for cand in CRIT_CANDS}
    clock_status = decoy["models"]["fixed5+C1g"]["status"]
    go = g["gateOnly"]
    attribution = (f"its 2021-22 increment {fmt(g['increment2021-2022'].get('real'))} is the readiness-gate term's (fixed5 + gate alone {fmt(go['increment2021-2022'])}, every decoy carries the same gate); "
                   f"the sin/cos terms add {fmt(go['clockMinusGateOnly2021-2022'])} in 2021-22 and {fmt(go['clockMinusGateOnlyPooled'])} pooled over the gate at the real period, "
                   f"and decoy periods add median {fmt(go['decoysOverGateOnly2021-2022'].get('nullMedian'))} / {fmt(go['decoysOverGateOnlyPooled'].get('nullMedian'))}")
    verdicts["clock"] = {"pass": "real 1460-day gated clock beats the random-period decoys pooled and in 2021-22 (" + attribution + ")",
                         "fail": "real 1460-day gated clock does not beat the random-period decoys in both places; " + attribution,
                         "not identifiable": "fewer than 50 decoy clocks (provisional: " + attribution + ")"}[clock_status]
    # era negatives (an era with few negatives is as thin as one with few positives) and label episodes that straddle an era boundary
    # (the same event then drives (ii) in two eras); study9_candidates' thin-era rule counts positives and episodes only.
    for e in ERA_NAMES:
        ctx[e]["negatives"] = ctx[e]["n"] - ctx[e]["positives"]
    straddle = []
    for s0, e0 in eps:                                   # positions into F.index (episodes were taken on the full-length labelled array)
        d0, d1 = F.index[s0], F.index[e0]
        era0 = next((e[0] for e in C.ERAS if pd.Timestamp(e[1]) <= d0 < pd.Timestamp(e[2])), None)
        era1 = next((e[0] for e in C.ERAS if pd.Timestamp(e[1]) <= d1 < pd.Timestamp(e[2])), None)
        if era0 != era1:
            straddle.append(f"{d0.date()}..{d1.date()} ({era0} -> {era1})")
    ctx["episodesStraddlingEraBoundary"] = straddle
    ctx["thinEraNegatives"] = [e for e in ERA_NAMES if ctx[e]["negatives"] < 20]
    say("criteria context: per era n/positives/negatives/episodes " + " ".join(f"{e[:4]}{e[-2:]} {ctx[e]['n']}/{ctx[e]['positives']}/{ctx[e]['negatives']}/{ctx[e]['episodes']} (fixed5 auc {fmt(ctx[e]['fixed5Auc'])})" for e in ERA_NAMES)
        + f"; eras with under 20 negatives {ctx['thinEraNegatives']}; episodes straddling an era boundary {straddle}"
        + f"; fresh-start rows {ctx['freshRowsPooled']} of which by era " + " ".join(f"{ctx[e]['freshRows']} ({ctx[e]['freshPositives']} pos, share {fmt(ctx[e]['freshShareOfPooled'], 2)})" for e in ERA_NAMES)
        + "; an era with one label episode, few negatives or a reference at ceiling makes (ii) there and most of (iii) a one-episode reading; (iv) is a whole-model skill test that fixed5 alone passes")
    for cand in CRIT_CANDS:
        c = crit[cand]
        say(f"criteria {cand:11s}: (i) {c['i']['status']} diff {fmt(c['i'].get('diff'))} q05 {fmt(c['i'].get('q05'))} | (ii) {c['ii']['status']} eras {' '.join(fmt(v) for v in c['ii']['byEra'].values())} | "
            f"(iii) {c['iii']['status']} fresh {fmt(c['iii'].get('diff'))} | (iv) {c['iv']['status']} rejects {c['iv']['erasRejecting']}/3 p {' '.join(fmt(c['iv']['byEra'][e]['p']) for e in ERA_NAMES)} -> {c['all'].upper()}: {verdicts[cand]}")
    say(f"criterion clock (fixed5+C1g increment over fixed5 beats the random-period p95 pooled AND in 2021-22): pooled {fmt(g['incrementPooled'].get('real'))} vs p95 {fmt(g['incrementPooled'].get('nullP95'))} "
        f"{'beats' if g['beatsP95Pooled'] else 'does not beat'}, 2021-22 {fmt(g['increment2021-2022'].get('real'))} vs p95 {fmt(g['increment2021-2022'].get('nullP95'))} {'beats' if g['beatsP95_2021-2022'] else 'does not beat'} "
        f"-> {clock_status.upper()}: {verdicts['clock']}; un-gated beside it: {decoy['models']['fixed5+C1u']['status']}")
    # beside the registered verdict (which does not change): what the gated candidate's numbers measure, from the diagnostics above
    s0 = supp["fixed5+C2bg0"]["common"]
    verdicts["fixed5+C2bgAnnotation"] = (f"the registered form's loss ({fmt(pdiff['fixed5+C2bg']['block']['pooled'].get('diff'))}) is the lost training window: fixed5 on the same training rows loses {fmt(st['fixed5SameTrainVsFixed5']['pooled'].get('diff'))} "
                                         f"and the gated term over it reads {fmt(st['candVsFixed5SameTrain']['pooled'].get('diff'))}; with the gate's undefined weeks read as off (supplement fixed5+C2bg0) the term reads {fmt(s0['block']['pooled'].get('diff'))} "
                                         f"block{band(s0['block']['pooled'])} ep{band(s0['episode']['pooled'])}, a tie under criterion (i); the registered condition is contradicted in sign on these rows "
                                         f"(gate-on label base rate {fmt(y[mask & (vgate > 0)].mean(), 2)} vs {fmt(y[mask & (vgate == 0)].mean(), 2)} off; fitted gated term {sg['fixed5+C2bg']['nPositive']}+ / {sg['fixed5+C2bg']['nNegative']}-)")
    say("beside the fixed5+C2bg verdict: " + verdicts["fixed5+C2bgAnnotation"])
    if smoke:
        say("NO VERDICT: a null has fewer than 50 draws (smoke run); the criteria lines above are the provisional reading and the full run's p-values replace them.")

    # ---- leakage checks
    leak = {}
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
                         "firstTrainableRow": (str(first_trainable.date()) if first_trainable is not None else None), "fixed5PredMaxAbsDiffOnCommonRows": round(float((ph.where(mask) - preds["fixed5"]).abs().max()), 10),
                         "immaterialHere": immaterial, "note": "btc_dd_ath rebuilt from the full BTCUSD history (study8_honest.ath_drawdown) for the readiness gate and for fixed5; see study9_candidates for why the anchor is immaterial on this panel"}
    n = len(F)
    cuts = rng.integers(max(1, n // 4), n - 1, size=n_trunc)
    worst_f, worst_p, tested = 0.0, 0.0, 0
    check_specs = ("fixed5+C2bg", "fixed5+C1g")
    for c in cuts:
        cut_date = F.index[int(c)]
        Dc = D[D.index <= cut_date]
        Xc, Pc, Yc, Fc, _ = build_all(Dc, a.data, cut_date)
        for col in C2B + C2BG + C2BG0 + VRD91 + ["vq20", "vgate", "gate_sin", "clk_sin"]:
            fa, fb = Fc[col].iloc[-1], F[col].loc[cut_date]
            if np.isfinite(fa) and np.isfinite(fb):
                worst_f = max(worst_f, abs(float(fa) - float(fb)))
        for spec in check_specs:
            pc, _ = run_spec(Fc, Yc, SPECS[spec])
            pfull = preds[spec].reindex(pc.index)
            both = pc.notna() & pfull.notna()
            if both.any():
                worst_p = max(worst_p, float((pc[both] - pfull[both]).abs().max()))
        tested += 1
    leak["truncation"] = {"ok": bool(worst_f <= 1e-9 and worst_p <= 1e-9), "maxAbsDiffFeatures": worst_f, "maxAbsDiffPredictions": worst_p, "tested": tested, "specsChecked": list(check_specs),
                          "cuts": [str(F.index[int(c)].date()) for c in cuts]}
    phase["leakageSec"] = round(time.time() - t0 - phase["predictionsBootstrapsSec"] - phase["nullsDecoysSec"], 1)
    leak["labels"] = {"lastLabelledRow": str(y[y.notna()].index[-1].date()), "lastCompleteSunday": str(last_complete.date()), "provisionalBarsExcluded": provisional, "labelLagWeeks": 26}
    leak["clock"] = {"halvings": [str(h.date()) for h in C.HALVINGS], "note": "the real clock counts days from the last past halving (2028-04-15 is the published next date and only sets the phase after it); decoys are strictly periodic from 2012-11-28"}
    leak["windows"] = {"C2b": "std of weekly logit increments over the 26 and 104 bars ending at t-1 (study8_multiscale closed-left)", "gate": "20th percentile of C2b over the 104 weeks ending at t",
                       "ath": "running max of weekly closes over the full BTCUSD history", "m2": f"M2 lagged {C.M2_LAG_DAYS} days by the loader"}
    say(f"leakage: truncation test at {tested} random Sundays (whole pipeline rebuilt on the cut daily panel; {', '.join(check_specs)}): features max |diff| {worst_f:.1e}, predictions max |diff| {worst_p:.1e}, ok {leak['truncation']['ok']}; "
        f"ATH anchor rebuilt (rows differing {leak['athAnchor']['rowsDiffering']}, last {leak['athAnchor']['lastRowDiffering']}, first trainable row {leak['athAnchor']['firstTrainableRow']}: "
        f"{'immaterial here' if immaterial else 'material'}; fixed5 preds max |diff| {leak['athAnchor']['fixed5PredMaxAbsDiffOnCommonRows']:.1e}); last labelled row {leak['labels']['lastLabelledRow']}; no optional series read")

    # ---- today: the last complete Sunday
    tlast = last_complete
    today = {"asOf": str(tlast.date()), "dataLastBarUtc": last_utc, "dataLastBarEt": last_et, "btcd": round(float(P.loc[tlast, "BTC.D"]), 2),
             "readings": {spec: (round(float(preds[spec].loc[tlast]), 4) if np.isfinite(preds[spec].loc[tlast]) else None) for spec in SPECS},
             "trainingBase": (round(float(base.loc[tlast]), 4) if np.isfinite(base.loc[tlast]) else None)}
    dd = float(F.loc[tlast, "btc_dd_ath"])
    rally = 0.0 if dd >= GATE_DD else (0.95 * math.exp(-dd) - 1) * 100
    today["readinessGate"] = {"on": bool(F.loc[tlast, "gate"] > 0), "btcDrawdownFromAthPct": round((math.exp(dd) - 1) * 100, 1), "btcRallyToWithin5pctOfAthPct": round(rally, 1),
                              "m2YoY": round(float(F.loc[tlast, "m2_yoy"]), 4), "m2Condition": bool(F.loc[tlast, "m2_yoy"] > 0)}
    vr_now, q_now = float(F.loc[tlast, C2B[0]]), float(F.loc[tlast, "vq20"])
    vr_hist = F[C2B[0]].loc[:tlast].dropna()
    today["compressionGate"] = {"on": bool(F.loc[tlast, "vgate"] > 0), "c2b": round(vr_now, 3), "trailing104wP20": round(q_now, 3), "gatedTerm": round(float(F.loc[tlast, C2BG[0]]), 3),
                                "c2bPercentileInTrailing104w": round(float((vr_hist.iloc[-Q_WINDOW:] <= vr_now).mean()), 3), "vol26wOver104wRatio": round(math.exp(vr_now), 3),
                                "distanceToGateLogUnits": round(vr_now - q_now, 3), "note": "the gate opens when C2b falls below its trailing 20th percentile (BTC.D quieter over 26 weeks than over 104)"}
    mu_g, sd_g, w_g = models["fixed5+C2bg"][-1]
    xg = F.loc[tlast, SPECS["fixed5+C2bg"]].values.astype(float)
    xg_off = xg.copy()
    xg_off[-1] = 0.0                                                             # the gated term with the gate forced off (zero), the rest at today
    today["compressionGate"]["fixed5C2bgReadingGateForcedOff"] = round(float(C.logistic_predict(C.zapply(xg_off[None, :], mu_g, sd_g), w_g)[0]), 4)
    today["compressionGate"]["hairsBreadth"] = bool(abs(vr_now - q_now) < 0.05)
    today["clock"] = {"daysSinceHalving": int(F.loc[tlast, "days_since_halving"]), "phaseTurns": round(float(F.loc[tlast, "days_since_halving"]) / PERIOD_DAYS, 3),
                      "clk_sin": round(float(F.loc[tlast, "clk_sin"]), 3), "clk_cos": round(float(F.loc[tlast, "clk_cos"]), 3), "fresh": bool(fresh.loc[tlast])}
    today["supplementReadings"] = {spec: (round(float(preds_supp[spec].loc[tlast]), 4) if np.isfinite(preds_supp[spec].loc[tlast]) else None) for spec in SUPP_SPECS}
    mu, sd, w = models["fixed5+C2b"][-1]
    x0 = F.loc[tlast, SPECS["fixed5+C2b"]].values.astype(float)
    spread = {}
    for i, c in enumerate(SPECS["fixed5+C2b"]):
        pair = []
        for sgn in (-1, 1):
            xx = x0.copy()
            xx[i] += sgn * sd[i]
            pair.append(round(float(C.logistic_predict(C.zapply(xx[None, :], mu, sd), w)[0]), 4))
        spread[c] = {"minus1sd": pair[0], "plus1sd": pair[1], "value": round(float(x0[i]), 4), "trainSd": round(float(sd[i]), 4)}
    allv = [v for s in spread.values() for v in (s["minus1sd"], s["plus1sd"])]
    today["fixed5C2bSpread"] = {"perInput": spread, "min": min(allv), "max": max(allv)}
    say(f"TODAY {today['asOf']} (data last bar {last_utc} / {last_et}) BTC.D {today['btcd']}: readings " + " ".join(f"{s} {fmt(v, 3)}" for s, v in today["readings"].items()) + f" train-base {fmt(today['trainingBase'])}")
    cg = today["compressionGate"]
    say(f"TODAY compression gate {'ON' if cg['on'] else 'OFF'}{' by a hair' if cg['hairsBreadth'] else ''}: C2b {cg['c2b']} (26w/104w vol ratio {cg['vol26wOver104wRatio']}) vs trailing 104-week 20th percentile {cg['trailing104wP20']} (C2b at the {cg['c2bPercentileInTrailing104w']:.2f} quantile of its trailing 104 weeks; "
        f"{cg['distanceToGateLogUnits']:+.3f} log units from the gate; fixed5+C2bg reads {fmt(today['readings']['fixed5+C2bg'], 3)} with the gate as it is and {fmt(cg['fixed5C2bgReadingGateForcedOff'], 3)} with it forced off: the rule, not the data, sets that reading); "
        f"supplements " + " ".join(f"{s} {fmt(v, 3)}" for s, v in today["supplementReadings"].items()) + f"; readiness gate {'ON' if today['readinessGate']['on'] else 'OFF'} (BTC {today['readinessGate']['btcDrawdownFromAthPct']}% from ATH, rally of {today['readinessGate']['btcRallyToWithin5pctOfAthPct']}% needed; "
        f"M2 y/y {today['readinessGate']['m2YoY']:+.3f}); clock {today['clock']['daysSinceHalving']} days since halving (phase {today['clock']['phaseTurns']} turns, sin {today['clock']['clk_sin']} cos {today['clock']['clk_cos']}); fresh {today['clock']['fresh']}")
    say(f"TODAY fixed5+C2b spread under +/-1 training sd of each input: {today['fixed5C2bSpread']['min']:.3f}..{today['fixed5C2bSpread']['max']:.3f} (" + ", ".join(f"{c} {s['minus1sd']:.3f}/{s['plus1sd']:.3f}" for c, s in spread.items()) + ")")

    # ---- side targets (contract): fall10_26w AUC and y13 IC for every model, no nulls
    side = {}
    for tg, binary in SIDE_TARGETS:
        side[tg] = {}
        for spec, cols in {**SPECS, **SUPP_SPECS}.items():
            side[tg][spec] = side_target_metrics(F, Y, cols, tg, binary, mask)
    def side_auc(s):
        r = side["fall10_26w"][s].get("pooled", {})
        return fmt(r.get("auc")) if r.get("auc") is not None else f"not available ({r.get('notAvailable', 'fewer than 20 rows')}; after it {fmt(r.get('aucAfterLastDegenerateRefit'))} on {r.get('nAfterLastDegenerateRefit')} rows with {r.get('positivesAfterLastDegenerateRefit')} positives)"
    say("side targets (common rows): fall10_26w auc " + " ".join(f"{s} {side_auc(s)}" for s in ["fixed5"] + CANDS + list(SUPP_SPECS))
        + " | y13 ic " + " ".join(f"{s} {fmt(side['y13'][s].get('pooled', {}).get('ic'))}" for s in ["fixed5"] + CANDS + list(SUPP_SPECS)))

    notes = [
        f"Common rows: every metric and criterion is on the intersection of all models' forecast rows (first {first_common}, n {int(mask.sum())}); the gated C2b (its trailing 104-week percentile is first finite {first_feat['vq20']}, + 60 training rows + 26-week label lag) sets that start and removes {first_own['fixed5']}..{first_common} for everyone (the Sep 2019 episode leaves the criteria set); the own-row supplement scores each candidate against fixed5 on the pair's own longer rows and is not a criterion.",
        "fixed5 = study8_baselines.SIGNALS through the same walk-forward (expanding window, refit 13 weeks, labels withheld 26 weeks, logistic lam 1, study9_candidates.run_spec); its btc_dd_ath is the true-ATH column (study8_honest.ath_drawdown, full BTCUSD history).",
        "C2b = study8_multiscale.scale_features(levels(P_weekly), s = 13)['btcd_vr']: log(std of weekly BTC.D logit increments over 2s = 26 bars / over 8s = 104 bars), windows closed-left (ending at t-1) as that function shifts them; this is the same function and window ratio that produced round 8's s = 91 transfer on the daily grid (182 / 728 days), computed on the weekly grid. Round 9's registered 13w/52w term is not judged here. The t-ending form (round 9's 26w/104w diagnostic) is reported as a marginal AUC beside it; its correlation with C2b is 0.99.",
        "C2bg = C2b x 1[C2b < 20th percentile of its own trailing 104 weeks ending at t] (one term: the dynamics-rule conditional 'a compressed BTC.D precedes the fall'); zero when the gate is off. Gate-on and gate-off rows are scored separately (oos.compressionGate) as the conditional's own target rows; their paired bands run over non-contiguous subsequences.",
        (f"Compression-gate rows on the common set: {gated['on']['fixed5']['n'].get('pooled')} gate-on weeks with label base rate {fmt(y[mask & (vgate > 0)].mean(), 2)} vs {gated['off']['fixed5']['n'].get('pooled')} gate-off weeks at {fmt(y[mask & (vgate == 0)].mean(), 2)}; "
         f"gate-on weeks by era {' / '.join(str(gated['on']['fixed5']['rowsByEra'][e]['n']) for e in ERA_NAMES)} with {sum(gated['on']['fixed5']['rowsByEra'][e]['positiveRuns'] for e in ERA_NAMES)} positive runs (the gate-on subset is {'scoreable' if gated['on']['scoreable'] else 'NOT scoreable: fewer than 3 positive runs, its bands are one or two events'}). "
         "A gate whose rows carry a lower fall rate than the rest says the condition is the opposite of 'a compressed BTC.D precedes the fall' on these rows; the fitted gated term's positive sign (oos.c2b.signAtRefits: a higher, i.e. less compressed, C2b raises the forecast) reads the same way: the registered hypothesis is contradicted in sign, which is stronger than 'not supported'."),
        ("Supplements (oos.supplements; both bands; never a criterion; not in the common-row mask): fixed5+C2bg0 reads the gate's undefined weeks (before its 104-week percentile exists) as 'off' (term 0) instead of NaN, so the model keeps fixed5's training rows and the comparison isolates the term from the lost history; "
         "fixed5+C2b_d91 is round 8's daily-grid s = 91 ratio (182 / 728 days) read on the Sundays, the feature the plan's parenthesis names (the registered candidate is the weekly-increment form named in its first clause; their correlation on the common rows is printed); fixed5+gate is the readiness gate alone. "
         "The registered forms are judged as written; a supplement that reads better is not a re-registration and waits for the owner."),
        (f"Training-window effect of the gate's late start (oos.sameTrainingRows): the gated column is NaN before {first_feat['vq20']}, and study8_common.walk_forward drops rows with a non-finite feature from that model's training window only, so before {first_common} "
         f"fixed5+C2bg trains on {st['labelledRowsBeforeFirstCommonForecast'][TARGET]['candTrainRows']} labelled rows with {st['labelledRowsBeforeFirstCommonForecast'][TARGET]['candTrainPositives']} fall5 positives where fixed5 has {st['labelledRowsBeforeFirstCommonForecast'][TARGET]['fixed5TrainRows']} rows with "
         f"{st['labelledRowsBeforeFirstCommonForecast'][TARGET]['fixed5TrainPositives']} (it loses the 2017-06..2018-03 rows that hold the Dec-2017 waterfall); fixed5 fitted on the same rows is reported beside the criteria as a diagnostic. On the fall10_26w side target the gated model's window holds "
         f"{st['labelledRowsBeforeFirstCommonForecast']['fall10_26w']['candTrainPositives']} positives until the Oct-2020 fall enters training in 2021, so its fall10 fit is degenerate (no positive label) at the early refits; a binary side-target AUC whose refits include a degenerate fit on common rows is reported as not available (oos.sideTargets.*.pooled.notAvailable) with the AUC after the last degenerate refit beside it."),
        "Clock decoy with power: 200 strictly periodic clocks with a random period uniform on 600..2200 days (seed printed), phase anchored at the first halving 2012-11-28, sin and cos terms, run gated by readiness (gate, gate x sin, gate x cos) and un-gated, each through the whole procedure on the same rows and labels; the increment over fixed5 is decoy AUC minus the frozen fixed5 AUC (same rows). The real clock is round 9's: phase = 2 pi days_since_halving / 1460 restarting at each halving. A random period changes the function space (sin(2 pi t / T) for different T are not linear combinations of one another), so unlike round 9's random-anchor family this one has power; the strictly periodic 1460-day member anchored at 2012-11-28 is reported beside (adversary.decoyClocks.models.*.periodicRealPeriodNoRestart).",
        "Criterion for the clock as pre-registered: the real gated clock's increment over fixed5 must exceed the decoys' p95 pooled AND in 2021-22; the un-gated clock is reported beside it; the round-9 four criteria are computed for the clock models as a diagnostic (criteriaDiagnostic) but are not registered for them. "
        "Attribution beside it (adversary.decoyClocks.models.*.gateOnly): the readiness gate term is shared by the real gated clock and every gated decoy, so fixed5 + gate alone is scored on the same rows and the clock's increment over the gate-only model, and the decoys' increments over it, say what the sin / cos terms add once the gate term is removed; the pass / fail rule itself is unchanged.",
        "Shifted-label nulls: under shifted labels fixed5 itself has no skill, so the null of a sixth term's increment over a skill-less base is wide by construction and says little about the real increment; the within-era dwell-time null of the increment (null.withinEraIncrement, same permuted labels, fixed5 keeps its structure) is the informative one and is the one to read, era by era. In the enumerated 2023-26 era (5 blocks, 120 arrangements) every model whose era AUC beats the 5th-best arrangement scores the same p = 5/120 = 0.042, the null's resolution floor there; criterion (iv) counts it as registered.",
        "Paired bands: 26-week circular block bootstrap (study8_honest.paired_block_boot, pooled and per era), episode bootstrap over label episodes with their 26-week run-up (study8_tda_sig.paired_episode_boot), era-stratified difference (study9_candidates.paired_strat_boot), fresh-start rows (BTC.D within 2 points of its 13-week high).",
        "Within-era nulls are dwell-time block permutations of each era's label episodes and gaps (study8_honest.perm_blocks / apply_order) over the era's labelled rows with the whole procedure rerun (study9_candidates.perm_positions); an era is enumerated exactly when its arrangements are at most max(n_within, 120); criterion (iv) counts only eras that can attain p < 0.05. Criterion (iv) as registered tests the candidate MODEL's era AUC, which fixed5 alone passes; null.withinEraIncrement gives the same permutation null for the increment over fixed5 as a diagnostic.",
        "Shifted-target nulls (circular shift of every target column by 26+ weeks) rerun the whole procedure for every candidate model and fixed5 on the same shifted labels, so the increment over fixed5 has its own null; null.shiftIncrementMaxOverCandidates is the family-wise null of the better of the two C2b increments.",
        "Decoy features: C2b and its compression gate computed on matched random walks of the BTC.D logit (study8_common.matched_rw on the complete weekly bars), the gate built on the full history before the panel cut exactly as the real column, run as fixed5 + decoy and differenced against fixed5 on the decoy's own rows (paired by construction; a decoy whose rows differ from the common rows is excluded as not comparable); their lag-1 autocorrelation is printed beside the real feature's. Episode leave-one-out drops each label episode with its 26-week run-up (study9_candidates.loo_diff).",
        "Criteria context adds each era's negatives (an era with under 20 negatives is as thin as one with under 20 positives; study9_candidates' thin-era rule counts positives and episodes) and the label episodes that straddle an era boundary, where one event drives (ii) in two eras; no status changes.",
        "Daily-scale marginal of the vol ratio at s = 5, 21, 91 days (study8_multiscale btcd_vr on the daily grid, read on the common Sundays) is a diagnostic beside the weekly candidate, never a candidate; s = 91 is the round-8 transfer read on these rows.",
        "Brier is reported against the walk-forward training-window base rate by era (study8_honest.run_const) and the era's own rate (oracle climatology, not available in real time).",
        "The last complete weekly bar is the last Sunday strictly before the last daily row, so the last daily row is always provisional whatever time the data were fetched; it enters no feature, label or reading.",
        f"None of the round-10 liquidity series is read by this module ({len(optional_on_disk)} of {len(OPTIONAL_SERIES)} were on disk: {optional_on_disk}); the module runs identically with any subset present.",
        f"Null draw counts are printed beside every p (n!, i.e. fewer than {MIN_DRAWS}, means resolution 1/n, not a p-value; E = enumerated exactly); only the full run's p-values are quotable.",
        "Nothing here touches the bot; a candidate that passes becomes a sixth signal only after the owner reads it; a conditional that passes is written with its gate (dynamics rule).",
    ]
    if S9._LINES[1]:
        notes.append(f"{S9._LINES[1]} summary lines were dropped to stay under the 60-line limit; everything is in results.json.")
    series = {spec: C.thin(preds[spec], every=2) for spec in ["fixed5"] + CANDS}
    series.update({spec: C.thin(preds_supp[spec], every=2) for spec in SUPP_SPECS})
    series["readinessGate"] = C.thin(F["gate"].where(mask), every=2, digits=0)
    series["compressionGate"] = C.thin(F["vgate"].where(mask), every=2, digits=0)
    series[C2B[0]] = C.thin(F[C2B[0]].where(mask), every=2)
    series["vq20"] = C.thin(F["vq20"].where(mask), every=2)
    res = {"module": "study10_sixth", "plan": "ROUND10_PLAN.md [3]", "dataLastBarUtc": last_utc, "dataLastBarEt": last_et, "lastCompleteSunday": str(last_complete.date()), "fast": a.fast,
           "runtimeSec": round(time.time() - t0, 1), "settings": {"nShift": n_shift, "nDecoyClocks": n_clock, "clockPeriodSeed": CLOCK_SEED, "nWithinEra": n_within, "nBoot": n_boot, "nDecoyFeatures": n_dfeat, "nTruncation": n_trunc, "workers": a.workers, "minDrawsForP": MIN_DRAWS, "phaseSec": phase},
           "optionalSeriesOnDisk": optional_on_disk, "specs": SPECS, "candidates": CANDS, "criteriaCandidates": CRIT_CANDS,
           "rows": {"firstCommonForecast": first_common, "n": int(mask.sum()), "labelled": int(lab.sum()), "positives": n_pos, "episodes": len(eps), "firstOwnForecast": first_own, "firstFiniteFeature": first_feat, "acf1": acf, "shortenedBy": shortener},
           "oos": {"fall5_26w": oos, "sideTargets": side, "compressionGate": gated, "ownRowSupplement": own_pairs, "sameTrainingRows": same_train, "c2b": c2b,
                   "supplements": {**supp, "corrC2bWeeklyVsDailyS91OnCommonRows": corr_d91, "specs": SUPP_SPECS}},
           "pairedVsFixed5": pdiff, "null": null, "adversary": {"decoyClocks": decoy, "decoyFeatures": dfeat, "episodeLOO": loo},
           "criteria": crit, "criteriaContext": ctx, "criteriaDiagnostic": crit_diag, "clockCriterion": decoy["models"]["fixed5+C1g"], "verdicts": verdicts, "noVerdict": smoke, "leakage": leak, "today": today, "series": series, "notes": notes}
    C.write_results(a.out, res)
    say(f"wrote {os.path.join(a.out, 'results.json')} in {time.time() - t0:.0f}s (data last bar {last_utc} / {last_et}); verdicts: " + "; ".join(f"{k} {v}" for k, v in verdicts.items()))


if __name__ == "__main__":
    main()
