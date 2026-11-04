#!/usr/bin/env python3
"""Round 10 module [1] altled: which kind of fall is being forecast (ROUND10_PLAN.md section [1]).

Question. BTC.D falls when alts rise (2017, 2021: an alt season) and when BTC falls faster than alts (mid 2022: a crash). The
bot cares about the first. Does the five-signal skill (fixed5 = study8_baselines.SIGNALS) come from alt seasons, from crashes,
or both, and what does today read for an alt season specifically?

Design (as registered). Weekly panel from study8_common. For every bar t with fall5_26w = 1 the crossing c is the first later
bar within 26 weeks with BTC.D(c) <= BTC.D(t) - 5. The window [t, c] is ALT-LED if TOTAL3 in USD at c is at or above its level
at t, CRASH-LED otherwise; ETH-led (ETH/BTC at c above t) is the second discriminator reported beside it. Targets alt5_26w =
fall5_26w and alt-led, crash5_26w = fall5_26w and crash-led, both withheld 26 weeks like the parent label (the kind reads
TOTAL3 and ETH/BTC only inside [t, c], which lies inside the horizon the label already waits for); a fall week whose kind
cannot be read (TOTAL3 exists from 2017-07-16) enters NO training label (NaN, never imputed); the partial current week is
excluded from the panel. Models through study8_common.walk_forward (expanding window, refit 13 weeks, label lag 26): fixed5
fitted on alt5_26w; fixed5 fitted on crash5_26w; fixed5 fitted on fall5_26w (the round-8 model, unchanged) scored against
alt5_26w and against crash5_26w on common rows; M2 alone and the readiness rule the same way. AUC pooled, by era,
era-stratified, fresh-start; Brier vs the target's training base; the paired difference (generic model's AUC on alt-led minus
on crash-led, 26-week block and episode bands); readiness precision on each kind; today's reading of each fitted model. The
five-signal reference (fixed5 on fall5_26w) is in every comparison with paired block / episode / era-stratified / fresh bands
(study9_candidates.paired_all).

Success (pre-registered, evaluated as written). (a) identifiability gate: alt5_26w has >= 4 positive episodes out of sample
2019-26, else "not identifiable" and the trial stops at description. (b) fixed5 fitted on alt5_26w clears its shifted-target
null p95 pooled and the within-era dwell-time permutation null at p < 0.05 in >= 2 eras. (c) alt-specific only if the generic
model's AUC on alt-led exceeds its AUC on crash-led by >= 0.10 with both the block and the episode band above 0 AND the
reassignment null beaten; crash-specific by the mirror rule; otherwise "both kinds". Beside (c), as a diagnostic and never
instead: the kind-specific AUC with shared negatives (positives of one kind against the non-fall weeks only), because the
as-written version counts a correct fall call of the other kind as a false positive.

Adversary. Shifted-target draws per target through the whole procedure; within-era dwell-time permutations of the target's
episodes and gaps (study8_honest.perm_blocks / apply_order, whole procedure rerun; the last era enumerated when its
arrangements are few); episode leave-one-out with 26-week run-ups; the sub-era decoy of study9_checks (an era-level indicator
and a time trend with no market information) on the same rows; the reassignment null: random relabellings of whole fall
EPISODES into alt-led and crash-led with the real episode counts, the generic model's alt-minus-crash AUC difference
recomputed each time (enumerated exactly when the assignments are few).

Leakage. Truncation test at 20 random Sundays on features, labels (known labels identical, no label inside the horizon) and
predictions; the provisional bar in no label; every monthly series lagged by its publication lag in the loader.

  python3 research/btcd_fractal/study10_altled.py --data research/btcd_fractal/data --out research/btcd_fractal/out10/altled [--nulls N] [--fast]

No network; aggregates only; every timestamp from the data's last bar in US Eastern and UTC. Nothing here touches the bot.
"""
import argparse
import datetime as dt
import itertools
import math
import os
import sys
import tempfile
import time
from multiprocessing import get_context

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import study8_common as C  # noqa: E402
from study8_baselines import SIGNALS  # noqa: E402
import study8_honest as H  # noqa: E402  (ath_drawdown, run_const, perm_blocks, apply_order, era_positions, era_mask, era_strat_auc, episode_loo_runup, psum, pfmt)
import study9_candidates as S9  # noqa: E402  (run_spec, score, paired_all, point_diff, chunks, fmt, DATA_CUT, EVAL_FROM: the round-9 paired protocol)

# ------------------------------------------------------------------------------------------- pre-registered constants
FALL, ALT, CRASH, ETHLED = "fall5_26w", "alt5_26w", "crash5_26w", "ethled5_26w"
KINDS = {"alt": ALT, "crash": CRASH}
TARGETS = [ALT, CRASH, FALL]
MODELS = {"fixed5@alt": (SIGNALS, ALT), "fixed5@crash": (SIGNALS, CRASH), "fixed5@fall": (SIGNALS, FALL),
          "m2@alt": (["m2_yoy"], ALT), "m2@crash": (["m2_yoy"], CRASH), "m2@fall": (["m2_yoy"], FALL)}
REF = "fixed5@fall"                                     # the round-8 model, unchanged: the generic reference
ALL_MODELS = list(MODELS) + ["readiness"]
NULL_MODELS = list(MODELS)
FALL_PTS, HORIZON_W, LAG_W, RUNUP = 5.0, 26, 26, 26
GATE_DD = np.log(0.95)
MIN_ALT_EPISODES = 4
CRIT_DIFF, CRIT_P = 0.10, 0.05
LAST_THREE = {"Jun 2025": "2025-06-15", "Jun 2022": "2022-06-05", "Jan 2021": "2021-01-03"}   # a week inside each named fall's label episode
CONTEXT_ERA = ("2016-2018", "2016-01-01", "2019-01-01")
ERA_NAMES = [e[0] for e in C.ERAS]
POOLED_ERA = S9.POOLED_ERA
MIN_DRAWS, ENUM_UP_TO = S9.MIN_DRAWS, S9.ENUM_UP_TO
OPTIONAL_SERIES = ["CNM2", "EUM2", "JPM2", "GBM2", "USDCNY", "EURUSD", "USDJPY", "GBPUSD", "FEDBS", "RRP", "TGA", "USDC.D", "STABLES"]

_G = {}
_LINES = [0, 0]
fmt = S9.fmt


def say(s):
    if _LINES[0] < 60:
        print(s)
        _LINES[0] += 1
    else:
        _LINES[1] += 1


def pct(d, digits=0):
    return "na" if d is None or not np.isfinite(d) else f"{(math.exp(d) - 1) * 100:+.{digits}f}%"


# ------------------------------------------------------------------------------------------- targets: the kind of a fall window
def kind_targets(P, Y):
    """alt5_26w / crash5_26w / ethled5_26w from the parent fall5_26w, plus the crossing position and the log changes of TOTAL3,
    ETH/BTC (and TOTAL2, a context diagnostic for windows before TOTAL3 exists) over [t, c]. A fall week whose kind cannot
    be read is NaN in alt/crash (no training label); a non-fall week is 0; a NaN parent stays NaN."""
    b = P["BTC.D"].values.astype(float)
    t3 = P["TOTAL3"].values.astype(float) if "TOTAL3" in P else np.full(len(b), np.nan)
    t2 = P["TOTAL2"].values.astype(float) if "TOTAL2" in P else np.full(len(b), np.nan)
    eb = P["ETHBTC"].values.astype(float) if "ETHBTC" in P else np.full(len(b), np.nan)
    f = Y[FALL].values.astype(float)
    n, hb = len(b), C.bars(HORIZON_W, "W")
    alt, crash, eth = f.copy(), f.copy(), f.copy()
    cross = np.full(n, -1)
    d3, d2, de = np.full(n, np.nan), np.full(n, np.nan), np.full(n, np.nan)
    for i in np.where(f == 1)[0]:
        hit = np.where(b[i + 1:i + hb + 1] <= b[i] - FALL_PTS)[0]
        if not len(hit):
            alt[i] = crash[i] = eth[i] = np.nan
            continue
        c = i + 1 + int(hit[0])
        cross[i] = c
        if np.isfinite(t3[i]) and np.isfinite(t3[c]) and t3[i] > 0 and t3[c] > 0:
            d3[i] = math.log(t3[c] / t3[i])
            alt[i] = 1.0 if t3[c] >= t3[i] else 0.0
            crash[i] = 1.0 - alt[i]
        else:
            alt[i] = crash[i] = np.nan
        if np.isfinite(t2[i]) and np.isfinite(t2[c]) and t2[i] > 0 and t2[c] > 0:
            d2[i] = math.log(t2[c] / t2[i])
        if np.isfinite(eb[i]) and np.isfinite(eb[c]) and eb[i] > 0 and eb[c] > 0:
            de[i] = math.log(eb[c] / eb[i])
            eth[i] = 1.0 if eb[c] > eb[i] else 0.0
        else:
            eth[i] = np.nan
    K = pd.DataFrame({ALT: alt, CRASH: crash, ETHLED: eth}, index=P.index)
    W = pd.DataFrame({"cross": cross, "dTotal3": d3, "dTotal2": d2, "dEthBtc": de}, index=P.index)
    return K, W


def episode_table(P, Y, W):
    """One row per fall episode (run of fall5_26w = 1) since 2016: dates, weeks, kind counts, the first week's window and the
    median window change of TOTAL3 and ETH/BTC, BTC.D at the start, at the first crossing and its trough. Majority kind."""
    b = P["BTC.D"].values.astype(float)
    rows = []
    for s, e in C.episodes(Y[FALL].values):
        a, cr, et = Y[ALT].values[s:e + 1], Y[CRASH].values[s:e + 1], Y[ETHLED].values[s:e + 1]
        n_alt, n_crash, n_unk = int(np.nansum(a)), int(np.nansum(cr)), int(np.isnan(a).sum())
        kind = "not available" if n_alt + n_crash == 0 else ("ALT-LED" if n_alt >= n_crash else "CRASH-LED")
        c0 = int(W["cross"].values[s])
        trough = float(np.nanmin(b[s:min(len(b), e + 1 + C.bars(HORIZON_W, "W"))]))
        era = next((x[0] for x in [CONTEXT_ERA] + list(C.ERAS) if pd.Timestamp(x[1]) <= P.index[s] < pd.Timestamp(x[2])), "pre-2016")
        rows.append({"start": str(P.index[s].date()), "end": str(P.index[e].date()), "weeks": int(e - s + 1), "era": era, "kind": kind,
                     "altWeeks": n_alt, "crashWeeks": n_crash, "kindUnknownWeeks": n_unk, "ethLedWeeks": int(np.nansum(et)), "ethLedKnownWeeks": int(np.isfinite(et).sum()),
                     "mixed": bool(n_alt > 0 and n_crash > 0),
                     "btcdStart": round(float(b[s]), 1), "firstCrossing": (str(P.index[c0].date()) if c0 >= 0 else None), "btcdAtFirstCrossing": (round(float(b[c0]), 1) if c0 >= 0 else None), "btcdTrough": round(trough, 1),
                     "dTotal3FirstWeek": (None if not np.isfinite(W["dTotal3"].values[s]) else round(float(W["dTotal3"].values[s]), 4)),
                     "dTotal3Median": (None if np.isnan(W["dTotal3"].values[s:e + 1]).all() else round(float(np.nanmedian(W["dTotal3"].values[s:e + 1])), 4)),
                     "dEthBtcFirstWeek": (None if not np.isfinite(W["dEthBtc"].values[s]) else round(float(W["dEthBtc"].values[s]), 4)),
                     "dEthBtcMedian": (None if np.isnan(W["dEthBtc"].values[s:e + 1]).all() else round(float(np.nanmedian(W["dEthBtc"].values[s:e + 1])), 4)),
                     "dTotal2FirstWeek": (None if not np.isfinite(W["dTotal2"].values[s]) else round(float(W["dTotal2"].values[s]), 4)),
                     "pos": (int(s), int(e))})
    return rows


def ep_line(r):
    t3 = (f"TOTAL3 {pct(r['dTotal3FirstWeek'])}/{pct(r['dTotal3Median'])}" if r["dTotal3FirstWeek"] is not None else f"TOTAL3 n/a (TOTAL2 {pct(r['dTotal2FirstWeek'])} diag)")
    return (f"  {r['start']}..{r['end']} {r['weeks']:2d}w BTC.D {r['btcdStart']}->{r['btcdAtFirstCrossing']}@{r['firstCrossing']} trough {r['btcdTrough']}: {r['kind']} "
            f"{r['altWeeks']}a/{r['crashWeeks']}c/{r['kindUnknownWeeks']}? ETH-led {r['ethLedWeeks']}/{r['ethLedKnownWeeks']} {t3} ETHBTC {pct(r['dEthBtcFirstWeek'])}/{pct(r['dEthBtcMedian'])}")


# ------------------------------------------------------------------------------------------- pipeline (main run and truncation test)
def build_all(D, data_dir, last_complete):
    P_full = C.panel(D, "W")
    X_full, _ = C.features(P_full, "W")
    X_full["btc_dd_ath"] = H.ath_drawdown(data_dir, X_full.index)       # the true all-time high (full BTCUSD history), as round 9
    keep = (X_full.index >= pd.Timestamp(S9.DATA_CUT)) & (X_full.index <= last_complete)
    X, P = X_full[keep], P_full[keep]
    Y = C.targets(P, "W")
    K, W = kind_targets(P, Y)
    Y = pd.concat([Y, K], axis=1)
    return X, P, Y, W


def readiness_pred(X):
    """study8_baselines / study8_honest.run_readiness: BTC within 5% of its ATH AND M2 y/y > 0; NaN where an input is NaN
    (study9_checks.readiness_rule), not forecast before the first forecast date."""
    r = ((X["btc_dd_ath"] >= GATE_DD) & (X["m2_yoy"] > 0)).astype(float).where(X["btc_dd_ath"].notna() & X["m2_yoy"].notna())
    r[X.index < pd.Timestamp("2019-01-06")] = np.nan
    return r


def fit_all(X, Y, keep_models=None):
    preds, refits = {}, {}
    for name, (cols, tg) in MODELS.items():
        km = [] if keep_models is not None else None
        preds[name], refits[name] = S9.run_spec(X, Y, cols, target=tg, keep_models=km)
        if keep_models is not None:
            keep_models[name] = km
    preds["readiness"] = readiness_pred(X)
    return preds, refits


def pooled_auc(pred, y):
    return C.metrics(pred, y, True).get("pooled", {}).get("auc")


def era_auc_of(pred, y, era):
    return C.metrics(pred, y, True, eras=[era]).get(era[0], {}).get("auc")


def shared_neg(pred, Y, kind):
    """Kind-specific AUC with shared negatives: the other kind's positive weeks are removed, so the positives of `kind` are
    ranked against the non-fall weeks only (diagnostic beside criterion (c), never instead)."""
    other = CRASH if kind == "alt" else ALT
    return pred.where(Y[other] != 1)


# ------------------------------------------------------------------------------------------- the (c) difference with its bands
def label_diff_boot(pred, Y, n, rng, mask=None, block_weeks=26, shared=False):
    """AUC(pred, alt5_26w) - AUC(pred, crash5_26w) for ONE prediction against two labels, with a 26-week circular block
    bootstrap band and an episode bootstrap band (blocks = the FALL episodes with their 26-week run-up and the gaps between,
    the parent of both labels). Adapted with attribution from study8_honest.paired_block_boot (block resampling) and
    study8_tda_sig.paired_episode_boot (episode blocks); the statistic differs (same prediction, two labels), the resampling
    does not. shared=True scores each kind against the non-fall weeks only."""
    m = pred.notna() & Y[ALT].notna() & Y[CRASH].notna() & Y[FALL].notna()
    if mask is not None:
        m &= mask
    p, a, b, f = pred[m].values, Y[ALT][m].values, Y[CRASH][m].values, Y[FALL][m].values
    N = len(p)

    def stat(ii):
        pp, aa, bb = p[ii], a[ii], b[ii]
        if shared:
            va, vb = C.auc(pp[bb != 1], aa[bb != 1]), C.auc(pp[aa != 1], bb[aa != 1])
        else:
            va, vb = C.auc(pp, aa), C.auc(pp, bb)
        return None if va is None or vb is None else va - vb
    out = {"n": int(N), "positivesAlt": int(np.nansum(a)), "positivesCrash": int(np.nansum(b))}
    if N < 20:
        out.update({"diff": None, "block": {"n": 0}, "episode": {"n": 0}})
        return out
    real = stat(np.arange(N))
    out["diff"] = (None if real is None else round(real, 3))
    if shared:
        va, vb = C.auc(p[b != 1], a[b != 1]), C.auc(p[a != 1], b[a != 1])
    else:
        va, vb = C.auc(p, a), C.auc(p, b)
    out["aucAlt"], out["aucCrash"] = (None if va is None else round(va, 3)), (None if vb is None else round(vb, 3))
    bl = block_weeks
    vals = []
    for _ in range(n):
        starts = rng.integers(0, N, size=int(np.ceil(N / bl)))
        ii = np.concatenate([(np.arange(s, s + bl) % N) for s in starts])[:N]
        v = stat(ii)
        if v is not None:
            vals.append(v)
    v = np.array(vals)
    out["block"] = ({"n": len(v), "dropped": int(n - len(v)), "q05": round(float(np.quantile(v, 0.05)), 3), "q50": round(float(np.quantile(v, 0.5)), 3), "q95": round(float(np.quantile(v, 0.95)), 3)} if len(v) else {"n": 0})
    cuts = [0]
    for s, e in C.episodes(f):
        cuts += [max(0, s - RUNUP), e + 1]
    cuts = sorted(set(c for c in cuts if 0 <= c <= N)) + [N]
    blocks = [np.arange(x, z) for x, z in zip(cuts[:-1], cuts[1:]) if z > x]
    vals = []
    for _ in range(n):
        pick = rng.integers(0, len(blocks), size=len(blocks))
        v = stat(np.concatenate([blocks[k] for k in pick]))
        if v is not None:
            vals.append(v)
    v = np.array(vals)
    out["episode"] = ({"n": len(v), "dropped": int(n - len(v)), "nBlocks": len(blocks), "q05": round(float(np.quantile(v, 0.05)), 3), "q50": round(float(np.quantile(v, 0.5)), 3), "q95": round(float(np.quantile(v, 0.95)), 3)} if len(v) else {"n": 0, "nBlocks": len(blocks)})
    return out


def diff_point(pred, Y, mask, shared=False):
    m = mask & pred.notna() & Y[ALT].notna() & Y[CRASH].notna()
    p, a, b = pred[m].values, Y[ALT][m].values, Y[CRASH][m].values
    if shared:
        va, vb = C.auc(p[b != 1], a[b != 1]), C.auc(p[a != 1], b[a != 1])
    else:
        va, vb = C.auc(p, a), C.auc(p, b)
    return None if va is None or vb is None else round(va - vb, 3)


def diff_loo(pred, Y, mask, eps):
    """The (c) difference with each fall episode and its 26-week run-up removed (the blocks of study8_honest.episode_loo_runup)."""
    per = {}
    idx = pred.index
    for s, e in eps:
        keep = mask.copy()
        keep.iloc[max(0, s - RUNUP):e + 1] = False
        per[f"{idx[s].date()}..{idx[e].date()}"] = diff_point(pred, Y, keep)
    vals = {k: v for k, v in per.items() if v is not None}
    return {"perEpisode": per, "min": (min(vals.values()) if vals else None), "minEpisode": (min(vals, key=vals.get) if vals else None),
            "max": (max(vals.values()) if vals else None), "maxEpisode": (max(vals, key=vals.get) if vals else None), "nEpisodes": len(per), "undefined": len(per) - len(vals)}


def clustered_runs(y, gaps=(8, 13, 26)):
    """Diagnostic beside gate (a): label runs merged when the gap between two runs is shorter than `gap` weeks (the
    registered gate counts runs as study8_common.episodes does; this says how many separate events they are)."""
    runs = C.episodes(y)
    out = {"runs": len(runs)}
    for g in gaps:
        merged = []
        for s_, e_ in runs:
            if merged and s_ - merged[-1][1] - 1 < g:
                merged[-1] = (merged[-1][0], e_)
            else:
                merged.append((s_, e_))
        out[f"gapUnder{g}w"] = len(merged)
    return out


def train_positives(X, Y, cols, target, refit_date):
    """Number of positive training labels at the refit dated `refit_date` (study8_common.walk_forward's training rows:
    labels known lag weeks before the refit, finite features)."""
    t = int(np.searchsorted(X.index, pd.Timestamp(refit_date)))
    tr = np.arange(0, max(0, t - C.bars(LAG_W, "W")))
    yv, xv = Y[target].values[tr], X[cols].values[tr]
    ok = np.isfinite(yv) & np.isfinite(xv).all(1)
    return int(np.nansum(yv[ok])), int(ok.sum())


def crash_runs_shared(pred, Y, mask):
    """Diagnostic beside (c): the generic model's shared-negatives AUC of each crash-led run on its own (that run's
    crash-led weeks against the non-fall weeks) with the run's mean prediction, so the reader sees which run carries
    the alt-minus-crash gap."""
    out = {}
    nonfall = (mask & (Y[FALL] == 0) & pred.notna()).values
    for s, e in C.episodes(np.where(mask, Y[CRASH], np.nan)):
        pos = np.zeros(len(Y), bool)
        pos[s:e + 1] = True
        pos &= (Y[CRASH] == 1).values & pred.notna().values
        sel = pos | nonfall
        v = C.auc(pred.values[sel], pos[sel].astype(float))
        out[f"{Y.index[s].date()}..{Y.index[e].date()}"] = {"weeks": int(pos.sum()), "sharedNegAuc": (None if v is None else round(v, 3)), "meanPred": round(float(np.nanmean(pred.values[pos])), 3)}
    return out


# ------------------------------------------------------------------------------------------- forked null workers
def perm_positions(Y, era, target):
    """Labelled rows of the era for `target` (study9_candidates.perm_positions with the target as a parameter): the dwell-time
    permutation reorders that target's episodes and gaps among these rows only; every Y column moves with the same order."""
    pos = H.era_positions(Y, era)
    return pos[np.isfinite(Y[target].values[pos])]


def _job(args):
    kind = args[0]
    X, Y, mask = _G["X"], _G["Y"], _G["mask"]
    out = []
    if kind == "shift":
        _, seed, n = args
        rng = np.random.default_rng(seed)
        lo = C.bars(LAG_W, "W")
        for _ in range(n):
            k = int(rng.integers(lo, len(Y) - lo))
            Ys = C.shift_targets(Y, k)
            preds, _ = fit_all(X, Ys)
            row = {m: {tg: pooled_auc(preds[m].where(mask), Ys[tg]) for tg in TARGETS} for m in NULL_MODELS}
            row[REF]["diffAltCrash"] = diff_point(preds[REF], Ys, mask)
            row[REF]["diffAltCrashShared"] = diff_point(preds[REF], Ys, mask, shared=True)
            out.append(row)
    elif kind == "perm":
        _, era, target, orders = args
        pos = perm_positions(Y, era, target)
        blocks = H.perm_blocks(Y[target].values[pos])
        for order in orders:
            Ys = H.apply_order(Y, pos, blocks, order)
            preds, _ = fit_all(X, Ys)
            out.append({m: {tg: era_auc_of(preds[m].where(mask), Ys[tg], era) for tg in TARGETS} for m in NULL_MODELS})
    return out


def run_jobs(pool, jobs):
    return pool.map(_job, jobs) if pool else [_job(j) for j in jobs]


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
    n_shift, n_within, n_reassign, n_boot, n_trunc = a.nulls, 300, 200, 1000, 20
    if a.fast:
        n_shift, n_within, n_reassign, n_boot = min(a.nulls, 20), 20, 20, 200
        a.workers = min(a.workers, 2)
    rng = np.random.default_rng(101)

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
    last_complete = sundays[sundays < last_bar][-1]
    provisional = [str(d.date()) for d in sundays[sundays > last_complete]]
    on_disk = sorted(n for n in OPTIONAL_SERIES if os.path.exists(os.path.join(a.data, f"{n}_1d.csv")))
    X, P, Y, W = build_all(D, a.data, last_complete)
    fresh = C.fresh_mask(P, "W")
    y = {tg: Y[tg] for tg in TARGETS}
    say(f"study10_altled  data last bar {last_utc} / {last_et} (daily close {last_bar.date()}); last complete Sunday {last_complete.date()}; provisional bars excluded {provisional}; "
        f"fast={a.fast} shift {n_shift} within-era {n_within} reassign {n_reassign} boots {n_boot} workers {a.workers}; optional round-10 series on disk {len(on_disk)}/{len(OPTIONAL_SERIES)} (none used here)")

    # ---- description: every fall episode since 2016 with its kind
    eps_all = episode_table(P, Y, W)
    say(f"fall episodes since 2016 ({len(eps_all)}; kind = TOTAL3 at the crossing vs at the week, majority over the episode's weeks; a/c/? = alt-led / crash-led / kind not readable weeks; "
        f"changes first week / median over the episode; TOTAL3 exists from {P['TOTAL3'].first_valid_index().date()}):")
    for r in eps_all:
        say(ep_line(r))
    counts = {}
    for tg in (ALT, CRASH, ETHLED, FALL):
        counts[tg] = {}
        for era in [CONTEXT_ERA] + list(C.ERAS) + [POOLED_ERA]:
            m = H.era_mask(Y.index, era) & Y[tg].notna()
            counts[tg][era[0]] = {"labelledWeeks": int(m.sum()), "positiveWeeks": int(Y[tg][m].sum()), "episodes": len(C.episodes(np.where(m, Y[tg], np.nan))),
                                  "kindUnknownFallWeeks": (int((H.era_mask(Y.index, era) & (Y[FALL] == 1) & Y[tg].isna()).sum()) if tg != FALL else 0)}
    say("positive weeks / episodes per target per era: " + " | ".join(f"{tg.replace('5_26w', '')}: " + " ".join(f"{e[0][:4]}{e[0][-2:]} {counts[tg][e[0]]['positiveWeeks']}/{counts[tg][e[0]]['episodes']}" for e in [CONTEXT_ERA] + list(C.ERAS) + [POOLED_ERA]) for tg in (ALT, CRASH, ETHLED, FALL))
        + f"; fall weeks whose kind is not readable (TOTAL3 absent): {counts[ALT]['2016-2018']['kindUnknownFallWeeks']} in 2016-18, {counts[ALT]['pooled']['kindUnknownFallWeeks']} since 2019")

    # ---- (a) identifiability gate on the label itself (out of sample 2019-26)
    oos_lab = (Y.index >= pd.Timestamp(S9.EVAL_FROM)) & Y[ALT].notna()
    n_alt_eps = len(C.episodes(np.where(oos_lab, Y[ALT], np.nan)))
    n_crash_eps = len(C.episodes(np.where(oos_lab, Y[CRASH], np.nan)))
    clus = clustered_runs(np.where(oos_lab, Y[ALT], np.nan))
    clus_c = clustered_runs(np.where(oos_lab, Y[CRASH], np.nan))
    gate = {"status": "pass" if n_alt_eps >= MIN_ALT_EPISODES else "not identifiable", "altEpisodes2019on": n_alt_eps, "crashEpisodes2019on": n_crash_eps, "required": MIN_ALT_EPISODES,
            "clusteredAltEvents": clus, "clusteredCrashEvents": clus_c, "note": "the gate counts label runs (study8_common.episodes) as registered; the clustered counts beside it merge runs separated by fewer than 8 / 13 / 26 weeks (diagnostic)"}
    say(f"criterion (a) identifiability gate: alt5_26w positive episodes out of sample 2019-26 = {n_alt_eps} (crash5_26w {n_crash_eps}), required >= {MIN_ALT_EPISODES} -> {gate['status'].upper()}; "
        f"diagnostic: the {n_alt_eps} alt runs are {clus['gapUnder8w']} events with gaps under 8 weeks merged, {clus['gapUnder13w']} under 13, {clus['gapUnder26w']} under 26 (the label's own horizon); crash runs {n_crash_eps} -> {clus_c['gapUnder8w']} / {clus_c['gapUnder13w']} / {clus_c['gapUnder26w']}; "
        f"the registered gate is met by label runs, the episode bands treat runs a few weeks apart as independent")
    # the crash-led class under the registered rule (TOTAL3 at the crossing below its level at t, any margin): how far below, and ETH-led or not
    cwk = np.where((Y[CRASH] == 1).values & oos_lab.values)[0]
    cmarg = {f"below{int(m * 100)}pct": int((W["dTotal3"].values[cwk] < -m).sum()) for m in (0.0, 0.03, 0.05, 0.10, 0.15)}
    crash_diag = {"weeks": len(cwk), "dTotal3": [round(float(v), 3) for v in W["dTotal3"].values[cwk]], "dEthBtc": [round(float(v), 3) for v in W["dEthBtc"].values[cwk]],
                  "ethLedWeeks": int(np.nansum(Y[ETHLED].values[cwk])), "marginSweep": cmarg,
                  "note": "diagnostic only: the registered rule has no margin; a margin would be a round-11 pre-registration, not a change here"}
    say(f"crash-led weeks since 2019 under the registered rule (TOTAL3 at the crossing < at t, no margin): {len(cwk)}; TOTAL3 change {' '.join(pct(v) for v in W['dTotal3'].values[cwk])}; ETH/BTC change {' '.join(pct(v) for v in W['dEthBtc'].values[cwk])}; "
        f"ETH-led {crash_diag['ethLedWeeks']}/{len(cwk)} (every crash-led week is ETH-led: the two registered discriminators disagree on all of them); weeks with TOTAL3 down more than 3% / 5% / 10% / 15%: {cmarg['below3pct']} / {cmarg['below5pct']} / {cmarg['below10pct']} / {cmarg['below15pct']} "
        f"-> 'crash-led' here means 'alt cap flat to slightly down at the crossing', not the BTC-falls-faster crash of the question")
    res = {"module": "study10_altled", "plan": "ROUND10_PLAN.md [1]", "dataLastBarUtc": last_utc, "dataLastBarEt": last_et, "lastCompleteSunday": str(last_complete.date()), "fast": a.fast,
           "settings": {"nShift": n_shift, "nWithinEra": n_within, "nReassign": n_reassign, "nBoot": n_boot, "nTruncation": n_trunc, "workers": a.workers, "minDrawsForP": MIN_DRAWS},
           "optionalSeriesOnDisk": on_disk, "episodes": eps_all, "counts": counts, "crashWeeksDiagnostic": crash_diag, "criteria": {"a": gate}}
    if gate["status"] != "pass":
        res.update({"oos": {}, "null": {}, "today": {"asOf": str(last_complete.date()), "dataLastBarUtc": last_utc, "dataLastBarEt": last_et}, "series": {}, "verdict": "not identifiable",
                    "notes": ["Identifiability gate (a) failed: fewer than 4 alt-led positive episodes out of sample 2019-26; the trial stops at description as registered."]})
        C.write_results(a.out, res)
        say("NOT IDENTIFIABLE: the trial stops at description (criterion (a)).")
        return

    # ---- predictions (frozen before any null), common rows, training base per target
    models = {}
    preds, refits = fit_all(X, Y, keep_models=models)
    base = {tg: H.run_const(X, Y, tg) for tg in TARGETS}
    mask = (X.index >= pd.Timestamp(S9.EVAL_FROM))
    for tg in TARGETS:
        mask &= base[tg].notna()
    first_own = {}
    for m in ALL_MODELS:
        fv = preds[m].first_valid_index()
        first_own[m] = (str(fv.date()) if fv is not None else None)
        mask &= preds[m].notna()
    pm = {m: preds[m].where(mask) for m in ALL_MODELS}
    bm = {tg: base[tg].where(mask) for tg in TARGETS}
    lab = mask & Y[FALL].notna() & Y[ALT].notna()
    fall_eps = C.episodes(np.where(lab, Y[FALL], np.nan))
    first_common = str(mask[mask].index[0].date())
    ep_kind = []
    for s, e in fall_eps:
        na, nc = int(np.nansum(Y[ALT].values[s:e + 1])), int(np.nansum(Y[CRASH].values[s:e + 1]))
        ep_kind.append("alt" if na >= nc else "crash")
    n_ep_alt, n_ep_crash = ep_kind.count("alt"), ep_kind.count("crash")
    say(f"common rows: first forecast {first_common} (own first forecast " + " ".join(f"{m} {first_own[m]}" for m in ALL_MODELS) + f"), n {int(mask.sum())} labelled {int(lab.sum())}; "
        f"positives alt {int(Y[ALT][lab].sum())} crash {int(Y[CRASH][lab].sum())} fall {int(Y[FALL][lab].sum())} in {len(fall_eps)} fall episodes ({n_ep_alt} alt-led, {n_ep_crash} crash-led by majority; "
        f"mixed episodes {sum(1 for s, e in fall_eps if 0 < np.nansum(Y[ALT].values[s:e + 1]) < e - s + 1 - np.isnan(Y[ALT].values[s:e + 1]).sum())}); "
        f"fresh-start rows {int((lab & fresh).sum())}; reference fixed5@fall on fall5 auc {fmt(pooled_auc(pm[REF], y[FALL]))}, training base at the last refit alt {fmt(base[ALT].loc[last_complete])} crash {fmt(base[CRASH].loc[last_complete])} fall {fmt(base[FALL].loc[last_complete])}")

    # ---- scores on every target; paired differences against the reference (fixed5 on fall5_26w) on alt5 and crash5
    oos, pdiff = {}, {}
    for tg in TARGETS:
        oos[tg], pdiff[tg] = {}, {}
        for m in ALL_MODELS:
            oos[tg][m] = S9.score(pm[m], y[tg], bm[tg], fresh)
            if tg != FALL:
                kname = "alt" if tg == ALT else "crash"
                sn = shared_neg(pm[m], Y, kname)
                oos[tg][m]["sharedNegatives"] = {"byEra": {e: r.get("auc") for e, r in C.metrics(sn, y[tg], True).items()}, **H.era_strat_auc(sn, y[tg]),
                                                 "fresh": {e: r.get("auc") for e, r in C.metrics(sn.where(fresh), y[tg], True).items()}}
                if m != REF:
                    pdiff[tg][m] = S9.paired_all(pm[m], pm[REF], y[tg], fresh, n_boot, rng)
    for tg in (ALT, CRASH):
        for m in ALL_MODELS:
            r = oos[tg][m]
            d = pdiff[tg].get(m)
            dl = ("" if d is None else f" | vs ref {fmt(d['block']['pooled'].get('diff'))} block[{fmt(d['block']['pooled'].get('q05'))},{fmt(d['block']['pooled'].get('q95'))}] "
                  f"ep[{fmt(d['episode']['pooled'].get('q05'))},{fmt(d['episode']['pooled'].get('q95'))}] strat {fmt(d['strat'].get('diff'))}[{fmt(d['strat'].get('q05'))},{fmt(d['strat'].get('q95'))}] "
                  f"fresh {fmt(d['fresh']['pooled'].get('diff'))}[{fmt(d['fresh']['pooled'].get('q05'))},{fmt(d['fresh']['pooled'].get('q95'))}] eras {' '.join(fmt(d['block'].get(e, {}).get('diff')) for e in ERA_NAMES)}")
            sn = r["sharedNegatives"]
            say(f"{tg.replace('5_26w', ''):5s} {m:12s} auc {fmt(r['byEra'].get('pooled', {}).get('auc'))} eras {' '.join(fmt(r['byEra'].get(e, {}).get('auc')) for e in ERA_NAMES)} strat {fmt(r['eraStratAuc'])} fresh {fmt(r['fresh'].get('pooled'))} "
                f"brier-skill {' '.join(fmt(r['byEra'].get(e, {}).get('skillVsTrainBase'), 2) for e in ERA_NAMES + ['pooled'])} | shared-neg auc {fmt(sn['byEra'].get('pooled'))} ({' '.join(fmt(sn['byEra'].get(e)) for e in ERA_NAMES)}) strat {fmt(sn['eraStratAuc'])}{dl}")

    # ---- the (c) difference: the generic model's AUC on alt-led minus on crash-led (as written) and with shared negatives
    cdiff = {"asWritten": {}, "sharedNegatives": {}}
    for key, shared in (("asWritten", False), ("sharedNegatives", True)):
        cdiff[key]["pooled"] = label_diff_boot(pm[REF], Y, n_boot, rng, mask, shared=shared)
        for era in C.ERAS:
            cdiff[key][era[0]] = label_diff_boot(pm[REF], Y, n_boot, rng, mask & H.era_mask(Y.index, era), shared=shared)
        cdiff[key]["fresh"] = label_diff_boot(pm[REF], Y, n_boot, rng, mask & fresh, shared=shared)
        # era-stratified: within-era pairs only (study8_honest.era_strat_auc) for each label, then the difference
        sa = H.era_strat_auc(pm[REF] if not shared else shared_neg(pm[REF], Y, "alt"), y[ALT])["eraStratAuc"]
        sc = H.era_strat_auc(pm[REF] if not shared else shared_neg(pm[REF], Y, "crash"), y[CRASH])["eraStratAuc"]
        cdiff[key]["strat"] = {"aucAlt": sa, "aucCrash": sc, "diff": (None if sa is None or sc is None else round(sa - sc, 3))}
    def cline(key):
        c = cdiff[key]
        return (f"[{key}] {fmt(c['pooled']['diff'])} (alt {fmt(c['pooled']['aucAlt'])} crash {fmt(c['pooled']['aucCrash'])}) block[{fmt(c['pooled']['block'].get('q05'))},{fmt(c['pooled']['block'].get('q95'))}] (n{c['pooled']['block'].get('n')}) "
                f"ep[{fmt(c['pooled']['episode'].get('q05'))},{fmt(c['pooled']['episode'].get('q95'))}] (n{c['pooled']['episode'].get('n')}/{c['pooled']['episode'].get('nBlocks')} blocks) eras {' '.join(fmt(c[e]['diff']) for e in ERA_NAMES)} strat {fmt(c['strat']['diff'])} fresh {fmt(c['fresh']['diff'])}")
    say("(c) generic model AUC on alt-led minus on crash-led, pooled: " + cline("asWritten") + "; " + cline("sharedNegatives") + "; a crash-led AUC is undefined in an era with no crash-led positive (na)")

    # ---- readiness precision on each kind
    rule = pm["readiness"]
    ready = {}
    for tg in TARGETS:
        ready[tg] = {}
        for era in list(C.ERAS) + [POOLED_ERA]:
            m = mask & H.era_mask(Y.index, era) & y[tg].notna() & rule.notna()
            on, off = m & (rule > 0), m & (rule == 0)
            ready[tg][era[0]] = {"weeksOn": int(on.sum()), "precisionOn": (round(float(y[tg][on].mean()), 3) if on.sum() else None), "precisionOff": (round(float(y[tg][off].mean()), 3) if off.sum() else None),
                                 "positivesOn": int(y[tg][on].sum()), "positivesOff": int(y[tg][off].sum())}
    say("readiness rule (BTC within 5% of ATH and M2 y/y > 0) precision on / off by kind, pooled: " + "; ".join(
        f"{tg.replace('5_26w', '')} {fmt(ready[tg]['pooled']['precisionOn'])} / {fmt(ready[tg]['pooled']['precisionOff'])} ({ready[tg]['pooled']['positivesOn']}/{ready[tg]['pooled']['weeksOn']} positives on)" for tg in TARGETS)
        + f"; on-weeks by era {' '.join(str(ready[ALT][e]['weeksOn']) for e in ERA_NAMES)}; rule on now {bool(preds['readiness'].loc[last_complete] > 0)}")

    # ---- nulls through the whole procedure (forked workers; predictions above are frozen)
    _G.update({"X": X, "Y": Y, "mask": mask})
    ctx = get_context("fork")
    pool = ctx.Pool(a.workers) if a.workers > 1 else None
    perm_raw, arrangements = {}, {}
    try:
        jobs = [("shift", 1000 + i, len(c)) for i, c in enumerate(S9.chunks(list(range(n_shift)), a.workers * 2)) if len(c)]
        shift_raw = [r for part in run_jobs(pool, jobs) for r in part]
        for kname, tg in KINDS.items():
            perm_raw[kname], arrangements[kname] = {}, {}
            for era in list(C.ERAS) + [POOLED_ERA]:
                pos = perm_positions(Y, era, tg)
                npos = int(np.nansum(Y[tg].values[pos]))
                nb = len(H.perm_blocks(Y[tg].values[pos]))
                K = H.n_arrangements(nb)
                exact = K <= max(n_within, ENUM_UP_TO)
                if npos == 0 or nb < 2:
                    arrangements[kname][era[0]] = {"blocks": nb, "positives": npos, "distinctArrangements": 1, "enumerated": True, "draws": 0, "note": "no positive of this kind in the era: the null is empty"}
                    perm_raw[kname][era[0]] = []
                    continue
                orders = [np.array(o) for o in itertools.permutations(range(nb))] if exact else [rng.permutation(nb) for _ in range(n_within)]
                arrangements[kname][era[0]] = {"blocks": nb, "positives": npos, "distinctArrangements": (int(K) if nb <= 20 else f"{nb}!"), "enumerated": exact, "draws": len(orders)}
                jobs = [("perm", era, tg, c) for c in S9.chunks(orders, a.workers * 2) if len(c)]
                perm_raw[kname][era[0]] = [r for part in run_jobs(pool, jobs) for r in part]
    finally:
        if pool:
            pool.close()
            pool.join()
    null = {"shift": {}, "withinEra": {}, "arrangements": arrangements}
    for m in NULL_MODELS:
        null["shift"][m] = {}
        for tg in TARGETS:
            real = oos[tg][m]["byEra"].get("pooled", {}).get("auc")
            null["shift"][m][tg] = H.psum(real, [r[m][tg] for r in shift_raw if r[m][tg] is not None])
    null["shift"]["diffAltCrash"] = H.psum(cdiff["asWritten"]["pooled"]["diff"], [r[REF]["diffAltCrash"] for r in shift_raw if r[REF]["diffAltCrash"] is not None])
    null["shift"]["diffAltCrashShared"] = H.psum(cdiff["sharedNegatives"]["pooled"]["diff"], [r[REF]["diffAltCrashShared"] for r in shift_raw if r[REF]["diffAltCrashShared"] is not None])
    for kname, tg in KINDS.items():
        null["withinEra"][kname] = {"permutedLabel": tg, "scoredOn": tg, "models": {}}
        for m in NULL_MODELS:
            null["withinEra"][kname]["models"][m] = {}
            for era in list(C.ERAS) + [POOLED_ERA]:
                arr = arrangements[kname][era[0]]
                vals = [r[m][tg] for r in perm_raw[kname][era[0]] if r[m][tg] is not None]
                s = H.psum(oos[tg][m]["byEra"].get(era[0], {}).get("auc"), vals, exact=arr["enumerated"])
                s["minAttainableP"] = (round(1.0 / arr["distinctArrangements"], 4) if arr["enumerated"] and isinstance(arr["distinctArrangements"], int) and arr["draws"] else (round(1.0 / len(vals), 4) if vals else None))
                if arr["draws"] == 0:
                    s["quotable"] = False
                    s["note"] = arr["note"]
                null["withinEra"][kname]["models"][m][era[0]] = s
    for m in ("fixed5@alt", "fixed5@crash", REF):
        wa, wc = null["withinEra"]["alt"]["models"][m], null["withinEra"]["crash"]["models"][m]
        say(f"nulls {m:12s}: shift pooled alt auc {fmt(null['shift'][m][ALT].get('real'))} med {fmt(null['shift'][m][ALT].get('nullMedian'))} p95 {fmt(null['shift'][m][ALT].get('nullP95'))} {H.pfmt(null['shift'][m][ALT])}, "
            f"crash auc {fmt(null['shift'][m][CRASH].get('real'))} p95 {fmt(null['shift'][m][CRASH].get('nullP95'))} {H.pfmt(null['shift'][m][CRASH])} | within-era dwell-time perm on alt5: "
            + " ".join(f"{e[:4]}{e[-2:]} {fmt(wa[e].get('real'))} p95 {fmt(wa[e].get('nullP95'))} {H.pfmt(wa[e])}" for e in ERA_NAMES + ['pooled']) + " | on crash5: "
            + " ".join(f"{e[:4]}{e[-2:]} {fmt(wc[e].get('real'))} p95 {fmt(wc[e].get('nullP95'))} {H.pfmt(wc[e])}" for e in ERA_NAMES + ['pooled']))
    say(f"nulls m2@alt / m2@crash shift pooled: alt auc {fmt(null['shift']['m2@alt'][ALT].get('real'))} p95 {fmt(null['shift']['m2@alt'][ALT].get('nullP95'))} {H.pfmt(null['shift']['m2@alt'][ALT])}, "
        f"crash auc {fmt(null['shift']['m2@crash'][CRASH].get('real'))} p95 {fmt(null['shift']['m2@crash'][CRASH].get('nullP95'))} {H.pfmt(null['shift']['m2@crash'][CRASH])}; within-era m2@alt on alt5 "
        + " ".join(f"{e[:4]}{e[-2:]} {H.pfmt(null['withinEra']['alt']['models']['m2@alt'][e])}" for e in ERA_NAMES)
        + f" | shift null of the generic model's alt-minus-crash difference: real {fmt(null['shift']['diffAltCrash'].get('real'))} med {fmt(null['shift']['diffAltCrash'].get('nullMedian'))} p95 {fmt(null['shift']['diffAltCrash'].get('nullP95'))} {H.pfmt(null['shift']['diffAltCrash'])} (diagnostic)")

    # ---- reassignment null: whole fall episodes relabelled alt / crash with the real episode counts; generic model rescored
    n_eps = len(fall_eps)
    K = math.comb(n_eps, n_ep_crash) if n_ep_crash else 1
    exact = K <= max(n_reassign, ENUM_UP_TO)
    assigns = ([set(c) for c in itertools.combinations(range(n_eps), n_ep_crash)] if exact else [set(rng.choice(n_eps, size=n_ep_crash, replace=False).tolist()) for _ in range(n_reassign)])
    fall_v = Y[FALL].values
    ep_of = np.full(len(Y), -1)
    for j, (s, e) in enumerate(fall_eps):
        ep_of[s:e + 1] = j
    vals, vals_sh, vals_w = [], [], []
    ep_len = [e - s + 1 for s, e in fall_eps]
    real_crash_w = sum(ep_len[j] for j, k in enumerate(ep_kind) if k == "crash")
    for crash_set in assigns:
        is_crash = np.isin(ep_of, list(crash_set)) if crash_set else np.zeros(len(Y), bool)
        vals_w.append(sum(ep_len[j] for j in crash_set))
        Yn = Y.copy()
        Yn[ALT] = np.where(fall_v == 1, np.where(is_crash, 0.0, 1.0), fall_v)
        Yn[CRASH] = np.where(fall_v == 1, np.where(is_crash, 1.0, 0.0), fall_v)
        v, vs = diff_point(pm[REF], Yn, mask), diff_point(pm[REF], Yn, mask, shared=True)
        vals.append(v)
        vals_sh.append(vs)
    vals_w = np.array(vals_w)
    size_matched = {}
    for capname, cap in (("crashWeeksAtMostReal", real_crash_w), ("crashWeeksAtMost2xReal", 2 * real_crash_w)):
        sel = vals_w <= cap
        size_matched[capname] = {"cap": int(cap), "asWritten": H.psum(cdiff["asWritten"]["pooled"]["diff"], [v for v, ok in zip(vals, sel) if ok and v is not None], exact=exact),
                                 "sharedNegatives": H.psum(cdiff["sharedNegatives"]["pooled"]["diff"], [v for v, ok in zip(vals_sh, sel) if ok and v is not None], exact=exact)}
    okw = np.array([v is not None for v in vals])
    corr_w = (round(float(np.corrcoef(vals_w[okw], np.array([v for v in vals if v is not None], float))[0, 1]), 3) if okw.sum() > 2 else None)
    vals = [v for v in vals if v is not None]
    vals_sh = [v for v in vals_sh if v is not None]
    # the real difference under the same episode-pure labelling (apples to apples with the null; the criterion uses the week-level real)
    is_crash_real = np.isin(ep_of, [j for j, k in enumerate(ep_kind) if k == "crash"])
    Yr = Y.copy()
    Yr[ALT] = np.where(fall_v == 1, np.where(is_crash_real, 0.0, 1.0), fall_v)
    Yr[CRASH] = np.where(fall_v == 1, np.where(is_crash_real, 1.0, 0.0), fall_v)
    reassign = {"episodes": n_eps, "altEpisodes": n_ep_alt, "crashEpisodes": n_ep_crash, "distinctAssignments": int(K), "enumerated": exact, "draws": len(assigns),
                "asWritten": H.psum(cdiff["asWritten"]["pooled"]["diff"], vals, exact=exact), "sharedNegatives": H.psum(cdiff["sharedNegatives"]["pooled"]["diff"], vals_sh, exact=exact),
                "realEpisodeMajorityLabels": {"asWritten": diff_point(pm[REF], Yr, mask), "sharedNegatives": diff_point(pm[REF], Yr, mask, shared=True)},
                "realCrashEpisodeWeeks": int(real_crash_w), "crashWeeksPerAssignment": {"min": int(vals_w.min()), "median": float(np.median(vals_w)), "max": int(vals_w.max())},
                "corrCrashWeeksDiff": corr_w,
                "sizeMatched": size_matched, "sizeMatchedNote": "diagnostic beside the registered null: 'with the real counts' is implemented as the real EPISODE counts, so most assignments label many more weeks crash-led than the real 6; the subsets keep only assignments with at most the real (or twice the real) number of crash-labelled weeks",
                "episodeKinds": [{"episode": f"{Y.index[s].date()}..{Y.index[e].date()}", "kind": k} for (s, e), k in zip(fall_eps, ep_kind)]}
    reassign["asWritten"]["pLE"] = (round(float(np.mean(np.array(vals) <= cdiff["asWritten"]["pooled"]["diff"])), 3) if vals and cdiff["asWritten"]["pooled"]["diff"] is not None else None)
    say(f"reassignment null ({n_ep_crash} of {n_eps} fall episodes relabelled crash-led, {'all ' + str(K) + ' assignments enumerated' if exact else str(len(assigns)) + ' random draws'}): as-written diff real {fmt(reassign['asWritten'].get('real'))} "
        f"(episode-majority labels {fmt(reassign['realEpisodeMajorityLabels']['asWritten'])}) null med {fmt(reassign['asWritten'].get('nullMedian'))} p05 {fmt(reassign['asWritten'].get('nullP05'))} p95 {fmt(reassign['asWritten'].get('nullP95'))} {H.pfmt(reassign['asWritten'])}; "
        f"shared-negatives diff real {fmt(reassign['sharedNegatives'].get('real'))} null med {fmt(reassign['sharedNegatives'].get('nullMedian'))} p95 {fmt(reassign['sharedNegatives'].get('nullP95'))} {H.pfmt(reassign['sharedNegatives'])}; "
        f"crash-labelled weeks per assignment {reassign['crashWeeksPerAssignment']['min']}-{reassign['crashWeeksPerAssignment']['max']} (median {reassign['crashWeeksPerAssignment']['median']:.0f}) vs real {real_crash_w}: size-matched subsets (diagnostic) "
        + " ".join(f"<= {size_matched[k]['cap']} weeks: as-written {H.pfmt(size_matched[k]['asWritten'])} p95 {fmt(size_matched[k]['asWritten'].get('nullP95'))}, shared-neg {H.pfmt(size_matched[k]['sharedNegatives'])} p95 {fmt(size_matched[k]['sharedNegatives'].get('nullP95'))}" for k in size_matched))

    # ---- episode leave-one-out with 26-week run-ups
    loo = {"fixed5@alt_on_alt": H.episode_loo_runup(pm["fixed5@alt"], y[ALT], runup=RUNUP), "fixed5@crash_on_crash": H.episode_loo_runup(pm["fixed5@crash"], y[CRASH], runup=RUNUP),
           "generic_on_alt": H.episode_loo_runup(pm[REF], y[ALT], runup=RUNUP), "generic_on_crash": H.episode_loo_runup(pm[REF], y[CRASH], runup=RUNUP),
           "genericDiffAltCrash": diff_loo(pm[REF], Y, mask, fall_eps)}
    for k in list(loo):
        if k != "genericDiffAltCrash":
            mname = REF if k.startswith("generic") else k.split("_on_")[0]
            loo[k] = {"model": mname, "all": oos[ALT if k.endswith("alt") else CRASH][mname]["byEra"].get("pooled", {}).get("auc"), "min": loo[k]["min"], "minEpisode": loo[k]["minEpisode"], "perEpisode": loo[k]["pooled"], "byEra": loo[k]["byEra"]}
    ld = loo["genericDiffAltCrash"]
    say(f"episode LOO (each episode + 26-week run-up dropped): fixed5@alt on alt5 min auc {fmt(loo['fixed5@alt_on_alt']['min'])} at {loo['fixed5@alt_on_alt']['minEpisode']}; generic on alt5 min {fmt(loo['generic_on_alt']['min'])} at {loo['generic_on_alt']['minEpisode']}; "
        f"fixed5@crash on crash5 min {fmt(loo['fixed5@crash_on_crash']['min'])} at {loo['fixed5@crash_on_crash']['minEpisode']}; generic alt-minus-crash diff over {ld['nEpisodes']} fall episodes min {fmt(ld['min'])} at {ld['minEpisode']} max {fmt(ld['max'])} at {ld['maxEpisode']} ({ld['undefined']} undefined: dropping a crash-led episode leaves too few crash positives)")

    # ---- the sub-era decoy of study9_checks (no market information), on the same rows: an era-level indicator and a time trend
    # (study9_checks main: sub_ind = (index < sub-era cut), trend = -arange; here the cut is the first forward era boundary)
    decoys = {"decoy_subEra": pd.Series((Y.index < pd.Timestamp(C.ERAS[1][1])).astype(float), index=Y.index).where(mask),
              "decoy_trend": pd.Series(-np.arange(len(Y), dtype=float), index=Y.index).where(mask)}
    decoy = {}
    for name, p in decoys.items():
        decoy[name] = {tg: {"byEra": {e: r.get("auc") for e, r in C.metrics(p, y[tg], True).items()}, **H.era_strat_auc(p, y[tg])} for tg in TARGETS}
    say("sub-era decoys (no market information; study9_checks): " + "; ".join(f"{n} pooled auc alt {fmt(decoy[n][ALT]['byEra'].get('pooled'))} crash {fmt(decoy[n][CRASH]['byEra'].get('pooled'))} fall {fmt(decoy[n][FALL]['byEra'].get('pooled'))} (strat alt {fmt(decoy[n][ALT]['eraStratAuc'])})" for n in decoys)
        + f"; models' pooled alt auc fixed5@alt {fmt(oos[ALT]['fixed5@alt']['byEra'].get('pooled', {}).get('auc'))} generic {fmt(oos[ALT][REF]['byEra'].get('pooled', {}).get('auc'))} vs their era-stratified {fmt(oos[ALT]['fixed5@alt']['eraStratAuc'])} / {fmt(oos[ALT][REF]['eraStratAuc'])}: the part above the decoy's level ranking is the within-era ranking")

    # ---- criteria as pre-registered
    smoke = n_shift < MIN_DRAWS or any(not null["withinEra"][k]["models"]["fixed5@alt"][e].get("quotable", False) and null["arrangements"][k][e]["draws"] > 0 for k in KINDS for e in ERA_NAMES) or (not exact and len(assigns) < MIN_DRAWS)
    sh = null["shift"]["fixed5@alt"][ALT]
    wa = null["withinEra"]["alt"]["models"]["fixed5@alt"]
    rej, attainable, per = 0, 0, {}
    for e in ERA_NAMES:
        s = wa[e]
        can = bool(s.get("quotable", False) and s.get("minAttainableP") is not None and s["minAttainableP"] < CRIT_P)
        hit = bool(can and s.get("p") is not None and s["p"] < CRIT_P)
        attainable += can
        rej += hit
        per[e] = {"p": s.get("p"), "n": s.get("n"), "exact": s.get("exact"), "quotable": s.get("quotable"), "minAttainableP": s.get("minAttainableP"), "rejects": hit}
    shift_ok = (None if not sh.get("quotable") or sh.get("real") is None else bool(sh["real"] > sh["nullP95"]))
    # within-era part: pass when >= 2 attainable eras reject; fail when even every unresolved era rejecting could not reach 2; else unresolved
    unresolved = len(ERA_NAMES) - attainable
    within_ok = (True if rej >= 2 else (False if rej + unresolved < 2 else None))
    if shift_ok is False or within_ok is False:
        b_status = "fail"
    elif shift_ok is None or within_ok is None:
        b_status = "not identifiable"
    else:
        b_status = "pass"
    corr_ref = (round(float(pm["fixed5@alt"].corr(pm[REF])), 4) if pm["fixed5@alt"].notna().sum() > 2 else None)
    shift_prov = (None if sh.get("real") is None or sh.get("nullP95") is None else bool(sh["real"] > sh["nullP95"]))
    rej_prov = sum(1 for e in ERA_NAMES if per[e]["p"] is not None and per[e]["p"] < CRIT_P)
    prov_b = (None if shift_prov is None else ("pass" if (shift_prov and rej_prov >= 2) else "fail"))
    crit_b = {"status": b_status, "withinEraStatus": within_ok, "predictionCorrWithReference": corr_ref,
              "readingNote": "fixed5@alt is fitted on a label that shares all but a handful of positives with fall5_26w, so (b) is a retest of the round-8/9 fixed5 skill on nearly the same label, not evidence of alt-specific skill", "shiftPooled": {"real": sh.get("real"), "nullP95": sh.get("nullP95"), "p": sh.get("p"), "n": sh.get("n"), "quotable": sh.get("quotable"), "clears": shift_ok},
              "withinEra": {"erasRejecting": rej, "erasAttainable": attainable, "byEra": per},
              "provisional": {"status": prov_b, "shiftClears": shift_prov, "erasRejecting": rej_prov, "note": "draw counts ignored: the reading a smoke run gives; the full run's p-values replace it"}}
    say(f"criterion (b) fixed5@alt: shift null pooled auc {fmt(sh.get('real'))} vs p95 {fmt(sh.get('nullP95'))} {H.pfmt(sh)} -> {'clears' if shift_ok else ('does not clear' if shift_ok is not None else 'na: not quotable')}; within-era perm rejects {rej}/3 "
        f"(p {' '.join(fmt(per[e]['p']) for e in ERA_NAMES)}; attainable {attainable}) -> {b_status.upper()}" + (f" (provisional, draw counts ignored: shift clears {shift_prov}, eras rejecting {rej_prov}/3 -> {str(prov_b).upper()})" if b_status == "not identifiable" else "")
        + f"; reading: fixed5@alt's predictions correlate {fmt(corr_ref)} with the reference fixed5@fall (alt5 shares {int(Y[ALT][lab].sum())} of {int(Y[FALL][lab].sum())} positives with fall5), so (b) is a retest of fixed5's round-8/9 skill, not alt-specific evidence")
    cw = cdiff["asWritten"]["pooled"]
    bq, eq = cw["block"], cw["episode"]
    ra = reassign["asWritten"]
    pieces = {"diff": cw["diff"], "blockQ05": bq.get("q05"), "blockQ95": bq.get("q95"), "episodeQ05": eq.get("q05"), "episodeQ95": eq.get("q95"), "reassignP95": ra.get("nullP95"), "reassignP05": ra.get("nullP05"),
              "blockDraws": bq.get("n", 0), "episodeDraws": eq.get("n", 0), "reassignDraws": ra.get("n", 0)}
    if cw["diff"] is None or bq.get("n", 0) < MIN_DRAWS or eq.get("n", 0) < MIN_DRAWS or not ra.get("quotable", False):
        c_status, c_word = "not identifiable", "not identifiable (a band or the reassignment null has too few valid draws, or a crash-led AUC is undefined)"
    elif cw["diff"] >= CRIT_DIFF and bq["q05"] > 0 and eq["q05"] > 0 and cw["diff"] > ra["nullP95"]:
        c_status, c_word = "pass", "alt-specific"
    elif cw["diff"] <= -CRIT_DIFF and bq["q95"] < 0 and eq["q95"] < 0 and cw["diff"] < ra["nullP05"]:
        c_status, c_word = "pass", "crash-specific"
    else:
        c_status, c_word = "fail", "both kinds"
    csn = cdiff["sharedNegatives"]["pooled"]
    crun = crash_runs_shared(pm[REF], Y, mask)
    n_crash_runs = len(C.episodes(np.where(lab, Y[CRASH], np.nan)))
    c_qual = (f"crash side not identifiable as evidence: {int(Y[CRASH][lab].sum())} crash-led weeks in {n_ep_crash} episodes ({n_crash_runs} runs), below the 4-episode gate the plan registered for the alt side only; "
              f"the generic model's shared-negatives AUC per crash run is {' / '.join(fmt(r['sharedNegAuc']) for r in crun.values())} (mean prediction {' / '.join(fmt(r['meanPred']) for r in crun.values())} vs alt-week median {fmt(float(np.nanmedian(pm[REF][(Y[ALT] == 1) & lab])))})")
    crit_c = {"status": c_status, "content": c_word, "qualifier": c_qual, "crashRunsSharedNegatives": crun, **pieces, "rule": "alt-specific if diff >= +0.10, block q05 > 0, episode q05 > 0 and diff > reassignment p95; crash-specific by the mirror; else both kinds",
              "sharedNegativesDiagnostic": {"diff": csn["diff"], "aucAlt": csn["aucAlt"], "aucCrash": csn["aucCrash"], "blockQ05": csn["block"].get("q05"), "episodeQ05": csn["episode"].get("q05"), "reassignP95": reassign["sharedNegatives"].get("nullP95"),
                                            "wouldRead": ("alt-specific" if csn["diff"] is not None and csn["diff"] >= CRIT_DIFF and (csn["block"].get("q05") or -1) > 0 and (csn["episode"].get("q05") or -1) > 0 and reassign["sharedNegatives"].get("nullP95") is not None and csn["diff"] > reassign["sharedNegatives"]["nullP95"] else
                                                          ("crash-specific" if csn["diff"] is not None and csn["diff"] <= -CRIT_DIFF and (csn["block"].get("q95") or 1) < 0 and (csn["episode"].get("q95") or 1) < 0 and reassign["sharedNegatives"].get("nullP05") is not None and csn["diff"] < reassign["sharedNegatives"]["nullP05"] else "both kinds"))}}
    say(f"criterion (c) as written: diff {fmt(cw['diff'])} (>= {CRIT_DIFF}: {cw['diff'] is not None and cw['diff'] >= CRIT_DIFF}), block q05 {fmt(bq.get('q05'))}, episode q05 {fmt(eq.get('q05'))}, reassignment p95 {fmt(ra.get('nullP95'))} {H.pfmt(ra)} -> {c_status.upper()}: forecast content reads {c_word}; "
        f"beside it (diagnostic, never instead; added at implementation time, not pre-registered) shared-negatives diff {fmt(csn['diff'])} (alt {fmt(csn['aucAlt'])} crash {fmt(csn['aucCrash'])}) block q05 {fmt(csn['block'].get('q05'))} ep q05 {fmt(csn['episode'].get('q05'))} reassign p95 {fmt(reassign['sharedNegatives'].get('nullP95'))} would read {crit_c['sharedNegativesDiagnostic']['wouldRead']}; "
        f"bands drop draws with no positive of a kind: block {bq.get('dropped', 0)} / episode {eq.get('dropped', 0)} of {n_boot} dropped (the band is conditional on a crash-led positive being present)")
    say(f"criterion (c) qualifier (beside the registered word, never instead): {c_qual}")
    verdict = f"(a) {gate['status']}; (b) {b_status}; (c) {c_status}: {c_word}"
    verdict_qual = f"(b) is a fixed5 retest (prediction correlation with the reference {fmt(corr_ref)}); (c) {c_qual.split(':')[0]}"
    if smoke:
        say("NO VERDICT: a null has fewer than 50 draws (smoke run); the criteria lines above are the provisional reading and the full run's p-values replace them.")

    # ---- leakage: truncation test on features, labels and predictions at random Sundays; the provisional bar in no label
    n = len(X)
    cuts = rng.integers(max(1, n // 4), n - 1, size=n_trunc)
    worst_f, worst_p, worst_l, horizon_ok, tested = 0.0, 0.0, 0, True, 0
    btc_raw = pd.read_csv(os.path.join(a.data, "BTCUSD_1d.csv"))
    btc_days = pd.to_datetime(btc_raw["ts"], unit="ms").dt.normalize()
    for c in cuts:
        cut_date = X.index[int(c)]
        Dc = D[D.index <= cut_date]
        # the true-ATH anchor (study8_honest.ath_drawdown) reads BTCUSD_1d.csv itself, so the cut is applied to a copy of that
        # file in a temporary folder: every input of the rebuilt pipeline is truncated, none re-reads the full history
        with tempfile.TemporaryDirectory() as tdir:
            btc_raw[btc_days <= cut_date].to_csv(os.path.join(tdir, "BTCUSD_1d.csv"), index=False)
            Xc, Pc, Yc, _ = build_all(Dc, tdir, cut_date)
        for col in X.columns:
            fa, fb = Xc[col].iloc[-1], X[col].loc[cut_date]
            if np.isfinite(fa) and np.isfinite(fb):
                worst_f = max(worst_f, abs(float(fa) - float(fb)))
        for tg in (ALT, CRASH, FALL):
            known = Yc[tg].dropna()
            if len(known):
                horizon_ok &= bool(known.index[-1] <= cut_date - pd.Timedelta(weeks=LAG_W))
                worst_l = max(worst_l, int((known != Y[tg].reindex(known.index)).sum()))
        pc_all, _ = fit_all(Xc, Yc)
        for m in ALL_MODELS:
            pc = pc_all[m]
            both = pc.notna() & preds[m].reindex(pc.index).notna()
            if both.any():
                worst_p = max(worst_p, float((pc[both] - preds[m].reindex(pc.index)[both]).abs().max()))
        tested += 1
    leak = {"truncation": {"ok": bool(worst_f <= 1e-9 and worst_p <= 1e-9 and worst_l == 0 and horizon_ok), "maxAbsDiffFeatures": worst_f, "maxAbsDiffPredictions": worst_p, "labelsDiffering": worst_l,
                           "noLabelInsideHorizon": horizon_ok, "tested": tested, "cuts": [str(X.index[int(c)].date()) for c in cuts], "featuresCompared": int(len(X.columns)), "modelsCompared": ALL_MODELS,
                           "athAnchorTruncated": "BTCUSD_1d.csv cut at the Sunday in a temporary folder before study8_honest.ath_drawdown reads it"},
            "labels": {"lastLabelledRow": {tg: str(Y[tg].dropna().index[-1].date()) for tg in TARGETS}, "lastCompleteSunday": str(last_complete.date()), "provisionalBarsExcluded": provisional, "labelLagWeeks": LAG_W,
                       "kindWindow": "TOTAL3 and ETH/BTC read at t and at the crossing c only, c <= t + 26 weeks, inside the horizon the parent label waits for"},
            "lags": {"M2": f"{C.M2_LAG_DAYS} days in study8_common.load_daily", "marketSeries": "none (daily closes)"}}
    say(f"leakage: truncation test at {tested} random Sundays (pipeline rebuilt on the cut daily panel, BTCUSD file behind the ATH anchor cut too): all {len(X.columns)} features max |diff| {worst_f:.1e}, all {len(ALL_MODELS)} models' predictions max |diff| {worst_p:.1e}, known labels differing {worst_l}, "
        f"no label inside the 26-week horizon {horizon_ok} -> ok {leak['truncation']['ok']}; last labelled row {leak['labels']['lastLabelledRow'][ALT]}; provisional bars excluded {provisional}")

    # ---- today
    tlast = last_complete
    today = {"asOf": str(tlast.date()), "dataLastBarUtc": last_utc, "dataLastBarEt": last_et, "btcd": round(float(P.loc[tlast, "BTC.D"]), 2),
             "readings": {m: (round(float(preds[m].loc[tlast]), 4) if np.isfinite(preds[m].loc[tlast]) else None) for m in ALL_MODELS},
             "trainingBase": {tg: (round(float(base[tg].loc[tlast]), 4) if np.isfinite(base[tg].loc[tlast]) else None) for tg in TARGETS},
             "inputs": {c: round(float(X.loc[tlast, c]), 4) for c in SIGNALS}, "readinessOn": bool(preds["readiness"].loc[tlast] > 0), "fresh": bool(fresh.loc[tlast]),
             "trainingPositivesAtLastRefit": {m: dict(zip(("positives", "nTrain"), train_positives(X, Y, cols, tg, refits[m][-1]["t"]))) for m, (cols, tg) in MODELS.items() if refits[m]},
             "lastThreeFalls": {}}
    tp = today["trainingPositivesAtLastRefit"]
    today["readingNotes"] = {m: f"no information: {tp[m]['positives']} training positives of {tp[m]['nTrain']}; the reading is the training base rate {fmt(today['trainingBase'][MODELS[m][1]])}" for m in MODELS if m in tp and tp[m]["positives"] < 10}
    for name, d in LAST_THREE.items():
        ts = pd.Timestamp(d)
        r = next((r for r in eps_all if pd.Timestamp(r["start"]) <= ts <= pd.Timestamp(r["end"])), None)
        if r is None:
            r = min(eps_all, key=lambda r: abs((pd.Timestamp(r["start"]) - ts).days)) if eps_all else None
        today["lastThreeFalls"][name] = (None if r is None else {k: r[k] for k in ("start", "end", "kind", "altWeeks", "crashWeeks", "ethLedWeeks", "ethLedKnownWeeks", "dTotal3FirstWeek", "dTotal3Median", "dEthBtcFirstWeek", "dEthBtcMedian", "firstCrossing")})
    say(f"TODAY {today['asOf']} (data last bar {last_utc} / {last_et}) BTC.D {today['btcd']}: readings " + " ".join(f"{m} {fmt(v)}" + (f" [no information: {tp[m]['positives']} training positives, reads the base rate]" if m in today["readingNotes"] else "") for m, v in today["readings"].items())
        + f"; training base alt {fmt(today['trainingBase'][ALT])} crash {fmt(today['trainingBase'][CRASH])} fall {fmt(today['trainingBase'][FALL])}; readiness {'ON' if today['readinessOn'] else 'OFF'}; fresh {today['fresh']}; "
        + " ".join(f"{c} {v:+.3f}" for c, v in today["inputs"].items()))
    say("TODAY the last three falls: " + "; ".join((f"{n}: {r['start']}..{r['end']} {r['kind']} ({r['altWeeks']}a/{r['crashWeeks']}c, ETH-led {r['ethLedWeeks']}/{r['ethLedKnownWeeks']}) TOTAL3 {pct(r['dTotal3FirstWeek'])} first week / {pct(r['dTotal3Median'])} median, ETH/BTC {pct(r['dEthBtcFirstWeek'])} / {pct(r['dEthBtcMedian'])}"
                                                   if r else f"{n}: no fall episode found") for n, r in today["lastThreeFalls"].items()))

    notes = [
        "Kind of a fall window [t, c]: c = first bar within 26 weeks with BTC.D <= BTC.D(t) - 5; ALT-LED if TOTAL3 (USD) at c >= TOTAL3 at t, else CRASH-LED; ETH-led = ETH/BTC at c > at t (second discriminator, reported, not modelled). "
        "The kind is a label property (read only inside [t, c], inside the 26-week horizon), so alt5_26w / crash5_26w carry the same 26-week label lag as fall5_26w in study8_common.walk_forward.",
        f"A fall week whose kind cannot be read (TOTAL3 exists from {P['TOTAL3'].first_valid_index().date()}) is NaN in alt5/crash5 and enters no training label for those targets (it stays a positive of fall5_26w for the generic model): "
        f"{counts[ALT]['2016-2018']['kindUnknownFallWeeks']} such weeks, all in the 2016-17 waterfall; TOTAL2 (ex BTC) is printed for that episode as a context diagnostic only. The alt/crash models therefore train on slightly fewer positives than the generic one.",
        "Under this definition nearly every fall since 2017 is alt-led (TOTAL3 held or rose while BTC.D fell); crash-led weeks are the Oct 2021 and May-Jun 2022 windows only, so crash5_26w has positives in 2021-22 alone and its AUC is undefined in the other eras "
        "('na'); every by-era crash number and the by-era (c) difference are 2021-22 numbers.",
        "Criterion (c) as written scores the generic model (fixed5 fitted on fall5_26w, unchanged from round 8) against alt5_26w and against crash5_26w on the common rows, where the other kind's positive weeks count as negatives: a correct fall call "
        "of the other kind is penalised. The shared-negatives AUC (one kind's positives against the non-fall weeks only) is printed beside it as a diagnostic and is not a criterion.",
        "Bands for (c): 26-week circular block bootstrap of the rows and an episode bootstrap over the FALL episodes with their 26-week run-up (the parent of both labels); draws in which a kind has no positive are dropped and the valid count is printed "
        "(n); criterion (c) is 'not identifiable' when a band has fewer than 50 valid draws.",
        "Reassignment null: whole fall episodes (runs of fall5_26w = 1 on the labelled common rows) are relabelled alt-led / crash-led with the real episode counts by majority kind, and the generic model's alt-minus-crash difference is rescored "
        "(no refit: the generic model never sees the kind); enumerated exactly when the distinct assignments are at most max(n, 120). The real statistic uses the week-level kind (the criterion); the same statistic under episode-majority labels is "
        "printed beside it because the null is episode-pure.",
        "Within-era nulls: dwell-time block permutations of the TARGET's episodes and gaps (study8_honest.perm_blocks / apply_order on the labelled rows of the era, every Y column moved together, whole procedure rerun with every model refitted); "
        "an era with no positive of the kind has an empty null (not identifiable); an era is enumerated exactly when its arrangements are at most max(n_within, 120) and the smallest attainable p is 1 / arrangements.",
        "Shifted-target nulls: every target column shifted together by 26+ weeks, every model refitted on the shifted labels, scored on the same rows; the generic model's alt-minus-crash difference has its own shift null (diagnostic). "
        "The circular shift moves the NaN kind weeks of the 2016-17 waterfall and the 26-week NaN tail with the labels (the round-9 convention), so a shifted alt5/crash5 draw trains on slightly different rows than the real run; the real row mask is reapplied for scoring.",
        "Within-era nulls keep the dwell structure of the PERMUTED kind only: the other kind's runs sit inside that kind's gap blocks and travel with them, so under the alt-kind null the crash runs (and the parent fall5 run count) can merge or split; fine for (b), which permutes the alt kind.",
        "Shared-negatives AUC, the per-crash-run AUCs, the clustered event counts, the crash-week margin sweep, the size-matched reassignment subsets, the prediction correlation with the reference and the training-positive tags were added at implementation time as diagnostics "
        "beside the registered criteria; none enters a criterion's status and 'wouldRead' never replaces the registered content word.",
        "Criterion (c)'s crash side rests on 6 crash-led weeks in 2 episodes (3 runs), all in 2021-22 and all ETH-led, below the 4-episode identifiability gate the plan registered for the alt side only; the as-written gap is carried by the May-Jun 2022 weeks "
        "(the Oct 2021 crash-led weeks score like alt weeks), so 'both kinds' is the only reading the sample can give and is not a finding about crashes; a crash-side gate would be a round-11 pre-registration.",
        "Paired bands against the reference (fixed5 on fall5_26w) on alt5 and crash5: study9_candidates.paired_all (26-week block bootstrap pooled and by era, episode bootstrap over the target's episodes with run-up, era-stratified, fresh-start rows).",
        "Readiness rule = BTC within 5% of its true all-time high (study8_honest.ath_drawdown, full BTCUSD history) AND M2 y/y > 0 (6-week publication lag in the loader); its precision on each kind is the share of rule-on weeks that are positives of that kind.",
        "Sub-era decoys (study9_checks): an indicator of the first forward era (1 before 2021-01-01) and a descending time trend, scored on the same rows; a pooled AUC that does not exceed theirs is a level ranking across eras, the era-stratified AUC is the within-era part.",
        "The last complete weekly bar is the last Sunday strictly before the last daily row; the provisional bar is in no feature, label or reading. Every monthly series is lagged by its publication lag in study8_common.load_daily before any feature.",
        f"Optional round-10 series on disk at run time: {on_disk or 'none'}; this module uses none of them (its inputs are BTC.D, TOTAL3, ETHBTC, BTCUSD, USDT.D, M2), so no candidate here depends on an absent series.",
        f"Null draw counts are printed beside every p (n!, i.e. fewer than {MIN_DRAWS}, means resolution 1/n, not a p-value; E = enumerated exactly); only the full run's p-values are quotable. Nothing here touches the bot.",
    ]
    if _LINES[1]:
        notes.append(f"{_LINES[1]} summary lines were dropped to stay under the 60-line limit; everything is in results.json.")
    series = {m: C.thin(preds[m], every=2) for m in ALL_MODELS}
    series[ALT] = C.thin(Y[ALT], every=1, digits=0)
    series[CRASH] = C.thin(Y[CRASH], every=1, digits=0)
    series["trainingBaseAlt"] = C.thin(base[ALT], every=2)
    res.update({"runtimeSec": round(time.time() - t0, 1), "models": {m: {"signals": cols, "target": tg} for m, (cols, tg) in MODELS.items()}, "reference": REF,
                "rows": {"firstCommonForecast": first_common, "n": int(mask.sum()), "labelled": int(lab.sum()), "fallEpisodes": len(fall_eps), "altEpisodesByMajority": n_ep_alt, "crashEpisodesByMajority": n_ep_crash, "firstOwnForecast": first_own,
                         "refits": {m: len(refits[m]) for m in MODELS}},
                "oos": oos, "pairedVsReference": pdiff, "diffAltCrash": cdiff, "readiness": ready, "null": null, "adversary": {"reassignment": reassign, "episodeLOO": loo, "decoys": decoy},
                "criteria": {"a": gate, "b": crit_b, "c": crit_c}, "verdict": verdict, "verdictQualifier": verdict_qual, "noVerdict": smoke, "leakage": leak, "today": today, "series": series, "notes": notes})
    C.write_results(a.out, res)
    say(f"wrote {os.path.join(a.out, 'results.json')} in {time.time() - t0:.0f}s (data last bar {last_utc} / {last_et}); verdict: {verdict}" + (" [NO VERDICT: smoke run]" if smoke else "") + f"; qualifier: {verdict_qual}")


if __name__ == "__main__":
    main()
