#!/usr/bin/env python3
"""Round 9 module [2] "checks": the two questions round 8 did not answer (ROUND9_PLAN.md section [2]).

QUESTION A (reverse walk-forward). Are the learned relationships cycle-specific? fixed5 (study8_baselines.SIGNALS), M2-only,
M2 + ETH/BTC and the readiness rule are fitted ONCE on 2019+ rows (labels withheld until their 26-week horizon has passed,
i.e. training rows end 26 weeks before the last complete Sunday) and scored, frozen, on 2016-06..2018-12 (the era holding the
Nov 2016 and Dec 2017 waterfalls, never in training). Two training windows are reported with the same criterion:
  - "plan"   : from 2019-01-06, the plan's literal text;
  - "purged" : from the last evaluation row + 27 weeks (2019-07-07), mirroring the forward harness's label lag: the first 26
               training rows of the plan window are labelled by the same Jan-Jun 2019 BTC.D path that labels the Jul-Dec 2018
               evaluation rows (a train/test label overlap the forward harness purges). The purged window is the headline;
               the plan window is printed beside it with a jackknife of every 26-week training block (plan amendment, no
               criterion change: the pass/fail reading is evaluated on both).
Reported per window: AUC on fall5_26w and fall10_26w (own rows and the rows every model can read), Brier against the 2019+
(training) base rate, sub-era AUC (2016-17 / 2018), era-stratified AUC (within-sub-era pairs only), the cross-/within-sub-era
pair decomposition of every AUC, episode leave-one-out (study8_common.episode_loo), the share of rows read at the scaler's
+/-3 sd clip, the reading on the big-event peak weeks, paired differences against fixed5 (26-week block bootstrap and episode
bootstrap; pooled, by sub-era, era-stratified, fresh-start rows), and two nulls scored by the same frozen models: the plan's
shifted-target null of the 2016-18 labels (>= 26 weeks; every admissible shift is enumerated exactly, 83 of them, so the p is
exact rather than 200 draws of those 83 values) and the dwell-time block permutation of the era's label episodes and gaps
(study8_honest.perm_blocks / apply_order; enumerated exactly when the arrangement count is small). Two decoys that carry no
market information are scored by the same nulls beside the models: the sub-era indicator (1 in 2016-17, 0 in 2018) and a
descending time trend, so a pass that is only the 2016-17-vs-2018 level ranking is visible as such.
SUCCESS (pre-registered, evaluated as written): AUC above the shifted null p95 for fixed5 AND for M2-only; a model that ranks
2016-18 at chance is cycle-specific and its forward number is one cycle's fit. Beside it (not instead of it): whether the
model beats the sub-era decoy on the same rows, its within-sub-era (era-stratified) AUC and the permutation p, which say
whether the pass is a within-cycle ranking or the level between the two sub-eras. The forward walk-forward numbers of the
same four models (the standard harness from 2019) are printed so the two can be read together.

QUESTION B (what would change the forecast; the decision threshold). No fitting beyond fixed5 and the readiness gate.
(1) For each fixed5 input, the move from today's value to its value at each big-event peak and the fixed5 reading (last
walk-forward refit, the model behind today's number) if that one input alone were there, the rest at today; readings whose
input sits beyond the scaler's +/-3 sd clip are flagged. (2) The lead from the readiness gate switching on to the start of
the next 5+ point fall, every gate-on spell since 2014 on weekly closes, as a Kaplan-Meier curve (study8_honest.km_curve) and
its median, under the plan's outcome (the next 5+ point fall PEAK found by study8_common.events) and, beside it, the outcome
"BTC.D closes 5+ points under the switch-on level" and the subset of spells that switch on outside an ongoing fall (nine of
twenty spells switch on inside a fall that is already under way). (3) The calendar falsifiers of ROUND8_PLAN.md read on
today's data (block copied from study8_honest.py main, with attribution; TODAY is the data's last bar, not the wall clock).
(4) The decision table: cost ratios 1, 2, 5, 10, 20 -> threshold 1 / (1 + ratio), and which of the round-8 forecast object's
readings (fixed5, in-support spread ends) clear it; spread ends that are the plan's hand-set fallback are labelled so.
SUCCESS: none, this is a report.

  python3 research/btcd_fractal/study9_checks.py --data research/btcd_fractal/data --out research/btcd_fractal/out9/checks [--nulls N] [--fast]

Point in time. The readiness gate uses the true all-time high (study8_honest.ath_drawdown, full BTCUSD history from 2013-02)
and M2 with the shared loader's 6-week publication lag. Labels are built from complete Sunday closes only, so the partial
current week is in no training label and no evaluation label. Every fitted object in question A is fitted on 2019+ rows only;
the frozen models never see a 2016-18 label (the nulls permute 2016-18 labels AFTER the fit and never refit). Bootstraps and
nulls run after all predictions are frozen. --fast: random null draws capped at 20 and bootstraps at 200 (under 3 minutes);
exact (enumerated) nulls are quotable at any size; a random null with fewer than 50 draws prints NO VERDICT. Aggregates only
are printed (public repo).
"""
import argparse
import itertools
import json
import os
import sys
import time

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import study8_common as C  # noqa: E402
import study8_baselines as B  # noqa: E402
import study8_honest as H  # noqa: E402  (ath_drawdown, perm_blocks, apply_order, n_arrangements, km_curve, km_quantiles, era_strat_auc)

# ------------------------------------------------------------------------------------------- pre-registered constants
MODELS = {"fixed5": B.SIGNALS, "m2only": ["m2_yoy"], "m2eth": ["m2_yoy", "ethbtc_fromhi52w"]}
TRAIN_FROM = pd.Timestamp("2019-01-06")                       # question A, plan window: the frozen fit's first training row
REV_ERA = ("2016-2018", "2016-06-01", "2019-01-01")           # the reversed (scoring) era
REV_SUB = [("2016-2017", "2016-06-01", "2018-01-01"), ("2018", "2018-01-01", "2019-01-01")]
TARGETS = ["fall5_26w", "fall10_26w"]
LAG_WEEKS = 26
BLOCK_WEEKS = 26
RUNUP_WEEKS = 26
MIN_DRAWS = 50                                                # no verdict from fewer RANDOM draws (exact nulls are always quotable)
RATIOS = [1, 2, 5, 10, 20]
GATE_LEAD_MAX = 52                                            # "no fall within 52 weeks"
PANEL_FROM = pd.Timestamp("2016-06-01")                       # the harness panel cut used by baselines and honest
FALLBACK_SPREAD = (0.039, 0.35)                               # ROUND8_PLAN "four defensible specifications" 3.9%..35% (fixed5 .. BTC drawdown alone)
CLIP = 3.0                                                    # study8_common.zapply's clip
HEADLINE_WINDOW = "purged"
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
    if isinstance(x, (float, np.floating)):
        return f"{x:.{d}f}" if np.isfinite(x) else "na"
    return str(x)


def stamp(ts):
    """A bar timestamp (naive = UTC) printed in US Eastern and UTC."""
    utc = pd.Timestamp(ts).tz_localize("UTC")
    try:
        et = utc.tz_convert("America/New_York").strftime("%Y-%m-%d %H:%M %Z")
    except Exception:
        et = "ET unavailable"
    return f"{et} / {utc.strftime('%Y-%m-%d %H:%M UTC')}"


def rnd(x, d=4):
    return None if x is None or not np.isfinite(x) else round(float(x), d)


# ------------------------------------------------------------------------------------------- models
def frozen_fit(X, y, cols, train_mask):
    """One logistic fit (the harness's own: z-score + ridge-logistic, study8_common) on the training rows only."""
    A = X[cols].values.astype(float)
    yv = np.asarray(y, float)
    tr = np.where(train_mask & np.isfinite(yv) & np.isfinite(A).all(1))[0]
    mu, sd = C.zfit(A[tr])
    w = C.logistic_fit(C.zapply(A[tr], mu, sd), yv[tr])
    return {"mu": mu, "sd": sd, "w": w, "nTrain": int(len(tr)), "trainFrom": str(X.index[tr[0]].date()), "trainTo": str(X.index[tr[-1]].date()),
            "trainBase": float(yv[tr].mean()), "cols": list(cols), "trIdx": tr}


def frozen_predict(model, X):
    A = X[model["cols"]].values.astype(float)
    ok = np.isfinite(A).all(1)
    out = np.full(len(A), np.nan)
    out[ok] = C.logistic_predict(C.zapply(A[ok], model["mu"], model["sd"]), model["w"])
    return pd.Series(out, index=X.index)


def clipped_share(model, X, mask):
    """Share of the rows in `mask` the frozen model reads with at least one input beyond the scaler's +/-3 sd clip."""
    A = X.loc[mask, model["cols"]].values.astype(float)
    ok = np.isfinite(A).all(1)
    if ok.sum() == 0:
        return {"rows": 0}
    z = (A[ok] - model["mu"]) / model["sd"]
    hit = (np.abs(z) > CLIP)
    return {"rows": int(ok.sum()), "clipped": int(hit.any(1).sum()), "share": rnd(hit.any(1).mean(), 3), "perInput": {c: int(v) for c, v in zip(model["cols"], hit.sum(0))}}


def readiness_rule(dd, m2):
    """study8_honest.run_readiness / study8_baselines: BTC within 5% of its ATH AND M2 y/y > 0; NaN where an input is NaN."""
    r = ((dd >= np.log(0.95)) & (m2 > 0)).astype(float)
    return r.where(dd.notna() & m2.notna())


# ------------------------------------------------------------------------------------------- evaluation helpers
def auc_strat(p, y, g):
    """AUC over within-group pairs only (study8_honest.era_strat_auc on arrays, groups = era ids)."""
    num, den = 0.0, 0.0
    for e in np.unique(g):
        m = g == e
        yy = y[m]
        n1 = int((yy > 0.5).sum())
        n0 = int(len(yy) - n1)
        if n1 == 0 or n0 == 0 or m.sum() < 20:
            continue
        v = C.auc(p[m], yy)
        if v is not None:
            num += n1 * n0 * v
            den += n1 * n0
    return (num / den) if den else None


def era_ids(idx, eras):
    g = np.full(len(idx), -1)
    for k, (name, fr, to) in enumerate(eras):
        g[(idx >= pd.Timestamp(fr)) & (idx < pd.Timestamp(to))] = k
    return g


def slice_metrics(pred, y, mask, base):
    m = mask & pred.notna() & y.notna()
    if m.sum() < 20:
        return {"n": int(m.sum())}
    p, yy = pred[m].values, y[m].values
    return {"n": int(m.sum()), "nPos": int((yy > 0.5).sum()), "auc": rnd(C.auc(p, yy), 3), "aucNote": (None if C.auc(p, yy) is not None else "undefined: one class only"),
            "base": rnd(yy.mean(), 3), "brier": rnd(C.brier(p, yy)),
            "brierBase2019": rnd(np.mean((base - yy) ** 2)), "beatsBase2019": bool(C.brier(p, yy) <= np.mean((base - yy) ** 2))}


def pair_decomp(pred, y, mask, eras):
    """The positive-negative pairs behind an AUC split into cross-sub-era pairs (a positive of one sub-era against a negative
    of the other: a level ranking) and within-sub-era pairs (the within-cycle ranking; its AUC is the era-stratified AUC)."""
    m = mask & pred.notna() & y.notna()
    p, yy = pred[m].values, y[m].values
    g = era_ids(pred.index[m], eras)
    i1, i0 = np.where(yy > 0.5)[0], np.where(yy <= 0.5)[0]
    if len(i1) == 0 or len(i0) == 0:
        return {"pairs": 0, "note": "undefined: one class only"}
    s = (p[i1][:, None] > p[i0][None, :]).astype(float) + 0.5 * (p[i1][:, None] == p[i0][None, :])
    cross = g[i1][:, None] != g[i0][None, :]
    return {"pairs": int(s.size), "crossShare": rnd(cross.mean(), 3), "crossAuc": (rnd(s[cross].mean(), 3) if cross.any() else None),
            "withinPairs": int((~cross).sum()), "withinAuc": (rnd(s[~cross].mean(), 3) if (~cross).any() else None)}


def full_metrics(pred, y, base, era_mask, eras, fresh):
    """AUC/Brier on the era (own rows), by sub-era, era-stratified, fresh-start rows, pair decomposition, episode leave-one-out."""
    out = {"own": slice_metrics(pred, y, era_mask, base)}
    for name, fr, to in eras:
        out[name] = slice_metrics(pred, y, era_mask & (pred.index >= pd.Timestamp(fr)) & (pred.index < pd.Timestamp(to)), base)
    m = era_mask & pred.notna() & y.notna()
    out["eraStratAuc"] = rnd(auc_strat(pred[m].values, y[m].values, era_ids(pred.index[m], eras)), 3)
    out["fresh"] = slice_metrics(pred, y, era_mask & fresh, base)
    out["pairs"] = pair_decomp(pred, y, era_mask, eras)
    loo = C.episode_loo(pred.where(era_mask), y)
    out["episodeLOO"] = {"nEpisodes": loo["nEpisodes"], "min": loo["min"], "minEpisode": loo["minEpisode"], "perEpisode": loo["perEpisode"],
                         "note": ("one event: AUC with the only episode removed is undefined, not identifiable" if loo["nEpisodes"] == 1 else None)}
    return out


def paired_boot(pa, pb, y, mask, n, rng, g=None, block=BLOCK_WEEKS, runup=RUNUP_WEEKS):
    """Paired AUC(pa) - AUC(pb) on the common rows of `mask` with (i) a circular block bootstrap (after
    study8_honest.paired_block_boot; the 26-week block is shortened to N // 4 when fewer than two blocks fit, and the
    band says so, instead of printing a rotation of the whole set as an interval) and (ii) an episode bootstrap (blocks =
    each positive episode with its 26-week run-up and the gaps between, after study8_common.episode_boot). With g (era ids)
    the statistic is the era-stratified AUC."""
    m = mask & pa.notna() & pb.notna() & y.notna()
    pos = np.where(m)[0]
    a, b, yy = pa.values[pos], pb.values[pos], y.values[pos]
    gg = None if g is None else g[pos]
    N = len(pos)
    if N < 20:
        return {"rows": int(N)}
    block_eff, block_note = block, None
    if N < 2 * block:
        block_eff = max(4, N // 4)
        block_note = f"block shortened to {block_eff} weeks: {N} rows hold fewer than two 26-week blocks"

    def stat(ii):
        if gg is None:
            va, vb = C.auc(a[ii], yy[ii]), C.auc(b[ii], yy[ii])
        else:
            va, vb = auc_strat(a[ii], yy[ii], gg[ii]), auc_strat(b[ii], yy[ii], gg[ii])
        return None if va is None or vb is None else va - vb
    real = stat(np.arange(N))
    blk = []
    for _ in range(n):
        starts = rng.integers(0, N, size=int(np.ceil(N / block_eff)))
        ii = np.concatenate([(np.arange(s, s + block_eff) % N) for s in starts])[:N]
        v = stat(ii)
        if v is not None:
            blk.append(v)
    cuts = [0]
    for s, e in C.episodes(yy):
        cuts += [max(0, s - runup), e + 1]
    cuts = sorted(set(c for c in cuts if 0 <= c <= N)) + [N]
    blocks = [np.arange(x, z) for x, z in zip(cuts[:-1], cuts[1:]) if z > x]
    epi = []
    for _ in range(n):
        pick = rng.integers(0, len(blocks), size=len(blocks))
        v = stat(np.concatenate([blocks[k] for k in pick]))
        if v is not None:
            epi.append(v)

    def q(v):
        v = np.array(v)
        return {"n": len(v), "q05": rnd(np.quantile(v, 0.05), 3), "q50": rnd(np.quantile(v, 0.5), 3), "q95": rnd(np.quantile(v, 0.95), 3), "pLE0": rnd((v <= 0).mean(), 3)} if len(v) else {"n": 0}
    out = {"rows": int(N), "diff": rnd(real, 3), "block": {**q(blk), "blockWeeks": block_eff}, "episode": {**q(epi), "nBlocks": len(blocks)}}
    if block_note:
        out["block"]["note"] = block_note
    return out


def paired_set(preds, ref, y, mask, eras, fresh, n, rng, names=None):
    """Paired differences of every model against the reference: pooled, by era, era-stratified, fresh-start."""
    out = {}
    for name, p in preds.items():
        if name == ref or (names is not None and name not in names):
            continue
        row = {"pooled": paired_boot(p, preds[ref], y, mask, n, rng)}
        for ename, fr, to in eras:
            row[ename] = paired_boot(p, preds[ref], y, mask & (y.index >= pd.Timestamp(fr)) & (y.index < pd.Timestamp(to)), n, rng)
        row["eraStrat"] = paired_boot(p, preds[ref], y, mask, n, rng, g=era_ids(y.index, eras))
        row["fresh"] = paired_boot(p, preds[ref], y, mask & fresh, n, rng)
        out[name] = row
    return out


def auc_str(r):
    return fmt(r.get("auc")) if r.get("auc") is not None else (f"na(n{r.get('n')},base {fmt(r.get('base'), 2)})" if r.get("n", 0) >= 20 else f"na(n{r.get('n')})")


def pb_str(r):
    if "diff" not in r:
        return f"na(n{r.get('rows')})"
    bl = r["block"]
    return f"{fmt(r['diff'])}[n{r['rows']}; blk {fmt(bl.get('q05'))},{fmt(bl.get('q95'))}{'(b' + str(bl['blockWeeks']) + ')' if bl.get('note') else ''}; epi {fmt(r['episode'].get('q05'))},{fmt(r['episode'].get('q95'))}]"


def null_summary(real, vals, exact=False):
    s = C.null_summary(real, vals)
    s["exact"] = bool(exact)
    s["quotable"] = bool(exact or s["n"] >= MIN_DRAWS)
    if not s["quotable"]:
        s["note"] = f"{s['n']} random draws: resolution 1/{max(1, s['n'])}, not a p-value"
    return s


def ns_str(s):
    return f"p95 {fmt(s.get('nullP95'))} p {fmt(s.get('p'))}(n{s.get('n')}{'E' if s.get('exact') else ('' if s.get('quotable') else '!')})"


# ------------------------------------------------------------------------------------------- question A nulls (frozen models, no refit)
def frozen_nulls(preds, Y, tg, pos, n, rng):
    """Shifted-target null (>= 26 weeks, inside the reversed era's rows; every admissible shift enumerated exactly) and the
    dwell-time block-permutation null (enumerated exactly when the arrangement count is <= max(n, ENUMERATE_UP_TO), else n
    random draws) of the 2016-18 labels, scored by the frozen predictions on each model's own finite rows."""
    out = {k: {"shift": [], "perm": []} for k in preds}
    y = Y[tg].values.astype(float)
    lo = C.bars(LAG_WEEKS, "W")
    shifts = list(range(lo, len(pos) - lo))
    for k in shifts:
        ys = y.copy()
        ys[pos] = np.roll(y[pos], k)
        for name, p in preds.items():
            v = C.auc(p.values[pos], ys[pos])
            if v is not None:
                out[name]["shift"].append(float(v))
    blocks = H.perm_blocks(y[pos])
    nb = len(blocks)
    perm_exact = bool(H.n_arrangements(nb) <= max(n, H.ENUMERATE_UP_TO))
    orders = list(itertools.permutations(range(nb))) if perm_exact else [rng.permutation(nb) for _ in range(n)]
    for order in orders:
        yp = H.apply_order(Y[[tg]], pos, blocks, np.asarray(order))[tg].values
        for name, p in preds.items():
            v = C.auc(p.values[pos], yp[pos])
            if v is not None:
                out[name]["perm"].append(float(v))
    out["_meta"] = {"nBlocks": nb, "distinctShifts": len(shifts), "shiftExact": True, "permExact": perm_exact, "permDraws": len(orders),
                    "distinctArrangements": (int(H.n_arrangements(nb)) if nb <= 20 else f"{nb}!")}
    return out


def jackknife_blocks(X, y, cols, train_mask, rev_pos, block=BLOCK_WEEKS):
    """Refit the frozen model with each consecutive `block`-week block of its training rows dropped and score the reversed
    era: the delta of the boundary block (the first training rows, whose labels share the 2019-H1 path with the late-2018
    evaluation labels) against the spread of every other block."""
    yv = np.asarray(y, float)
    full = frozen_fit(X, y, cols, train_mask)
    p = frozen_predict(full, X).values
    own = rev_pos[np.isfinite(p[rev_pos]) & np.isfinite(yv[rev_pos])]
    base = C.auc(p[own], yv[own])
    tr = full["trIdx"]
    deltas = []
    for i in range(0, len(tr), block):
        tm = train_mask.copy()
        tm[tr[i:i + block]] = False
        pj = frozen_predict(frozen_fit(X, y, cols, tm), X).values
        v = C.auc(pj[own], yv[own])
        deltas.append((str(X.index[tr[i]].date()), rnd(None if v is None or base is None else v - base, 3)))
    rest = np.array([d for _, d in deltas[1:] if d is not None])
    return {"auc": rnd(base, 3), "nBlocks": len(deltas), "boundaryBlock": deltas[0][0], "boundaryDelta": deltas[0][1],
            "otherBlocks": {"maxAbsDelta": (rnd(np.abs(rest).max(), 3) if len(rest) else None), "mean": (rnd(rest.mean(), 3) if len(rest) else None)}, "perBlock": deltas}


# ------------------------------------------------------------------------------------------- question B helpers
def last_refit_model(X, Y, tg="fall5_26w"):
    """The fixed5 model behind today's forward reading: the last refit of the standard walk-forward (study8_baselines.run_fixed),
    re-fitted here on exactly its training rows and asserted equal to the harness series on the last complete Sunday."""
    pred, refits = B.run_fixed(X, Y, tg, "W", True, B.SIGNALS)
    t = int(np.searchsorted(X.index, pd.Timestamp(refits[-1]["t"])))
    lag = C.bars(LAG_WEEKS, "W")
    mask = np.zeros(len(X), bool)
    mask[:max(0, t - lag)] = True
    m = frozen_fit(X, Y[tg], B.SIGNALS, mask)
    assert m["nTrain"] == refits[-1]["nTrain"], (m["nTrain"], refits[-1]["nTrain"])
    return m, pred, refits


def m2_yoy_long(data_dir, index):
    """m2_yoy exactly as study8_common.features defines it (M2 lagged M2_LAG_DAYS by the loader, 52-week log change on Sunday
    closes), computed on the M2 file's own history so the gate exists from the panel's first week (2014-04) instead of a year later."""
    d = pd.read_csv(os.path.join(data_dir, "M2_1d.csv"))
    s = pd.Series(d["c"].values.astype(float), index=pd.DatetimeIndex(pd.to_datetime(d["ts"], unit="ms")).normalize() + pd.Timedelta(days=C.M2_LAG_DAYS))
    s = s[~s.index.duplicated()].sort_index()
    daily = s.reindex(pd.date_range(index[0] - pd.Timedelta(weeks=60), index[-1], freq="D")).ffill()
    w = daily.resample("W-SUN").last().ffill()
    return np.log(w).diff(C.bars(52, "W")).reindex(index)


def merge_spells(spells, gap_weeks=13):
    """Secondary reading: on-spells separated by fewer than `gap_weeks` weeks of gate-off are one spell (first switch-on counts)."""
    out = []
    for sp in spells:
        if out and (pd.Timestamp(sp["start"]) - pd.Timestamp(out[-1]["end"])).days // 7 < gap_weeks:
            out[-1]["end"] = sp["end"]
            out[-1]["merged"] = out[-1].get("merged", 1) + 1
        else:
            out.append(dict(sp))
    return out


def km_block(spells, tkey, ekey):
    """Kaplan-Meier summary of a spell list on one (time, event) definition, censored at 52 weeks or the data end."""
    if not spells:
        return {"n": 0}
    S = H.km_curve(np.array([s[tkey] for s in spells], float), np.array([s[ekey] for s in spells], float), hmax=GATE_LEAD_MAX)
    q = H.km_quantiles(S)
    return {"n": len(spells), "nEvents": int(sum(s[ekey] for s in spells)), "kmWeeks": q, "kmP_within26w": rnd(1 - S[26], 3), "kmP_within52w": rnd(1 - S[GATE_LEAD_MAX], 3),
            "S": [round(float(v), 3) for v in S]}


def gate_spells(gate, bw, Y):
    """Every readiness-gate-on spell on weekly closes: start, weeks on, lead (weeks) from the switch-on to the next 5+ point
    fall's peak (study8_common.events on complete weekly closes) or 'no fall within 52 weeks' (censored) [the plan's outcome],
    plus the second outcome 'BTC.D first closes 5 points under the switch-on level' (tte5 at the switch-on week, same censoring)
    and whether the spell switches on inside a fall that is already under way (peak < start <= trough of an events() fall)."""
    g = gate.fillna(0).values > 0.5
    idx = gate.index
    ev = C.events(bw, 5.0, freq="W")
    peaks = pd.DatetimeIndex([e["peak"] for e in ev])
    spells = []
    i = 0
    while i < len(g):
        if g[i] and (i == 0 or not g[i - 1]):
            j = i
            while j + 1 < len(g) and g[j + 1]:
                j += 1
            start = idx[i]
            nxt = peaks[peaks >= start]
            lead = int((nxt[0] - start).days // 7) if len(nxt) else None
            weeks_to_end = int((bw.index[-1] - start).days // 7)
            if lead is None or lead > GATE_LEAD_MAX:
                time_, event = min(GATE_LEAD_MAX, weeks_to_end), 0
            else:
                time_, event = lead, 1
            e0 = ev[list(peaks).index(nxt[0])] if (lead is not None and lead <= GATE_LEAD_MAX) else None
            tte = Y["tte5"].get(start, np.nan)
            cens = Y["cens5"].get(start, np.nan)
            if np.isfinite(tte) and cens == 0 and tte <= GATE_LEAD_MAX:
                t5, e5 = int(tte), 1
            else:
                t5, e5 = min(GATE_LEAD_MAX, weeks_to_end), 0
            inside = [e for e in ev if e["peak"] < start <= e["trough"]]
            spells.append({"start": str(start.date()), "end": str(idx[j].date()), "weeksOn": int(j - i + 1), "leftCensoredStart": bool(i == 0),
                           "leadWeeksToNextFallPeak": lead, "kmTime": int(time_), "kmEvent": int(event), "censoredByDataEnd": bool(event == 0 and weeks_to_end < GATE_LEAD_MAX),
                           "nextFall": ({"peak": str(e0["peak"].date()), "from": round(e0["from"], 1), "to": round(e0["to"], 1), "days": e0["days"]} if e0 else "no fall within 52 weeks"),
                           "tte5WeeksFromStartLevel": (None if not np.isfinite(tte) else (int(tte) if cens == 0 else f">= {int(tte)} (censored)")),
                           "km5Time": int(t5), "km5Event": int(e5),
                           "startsInsideFall": (f"{inside[0]['peak'].date()}->{inside[0]['trough'].date()}" if inside else None)})
            i = j + 1
        else:
            i += 1
    return spells, ev


# ------------------------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--nulls", type=int, default=200)
    ap.add_argument("--fast", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    n_null, n_boot = a.nulls, 1000
    if a.fast:
        n_null, n_boot = min(a.nulls, 20), 200
    rng = np.random.default_rng(92)
    notes = []

    # ---- data: weekly Sunday closes, true-ATH drawdown, labels from complete closes only
    D = C.load_daily(a.data)
    raw = pd.read_csv(os.path.join(a.data, "BTC.D_1d.csv"))
    last_bar = pd.Timestamp(int(raw["ts"].iloc[-1]), unit="ms")
    TODAY = D.index[-1]
    P_full = C.panel(D, "W")
    X_full, _ = C.features(P_full, "W")
    dd_harness = X_full["btc_dd_ath"].copy()
    X_full["btc_dd_ath"] = H.ath_drawdown(a.data, X_full.index)
    keep = X_full.index >= PANEL_FROM
    X, P = X_full[keep], P_full[keep]
    provisional = X.index[X.index > TODAY]
    last_complete = X.index[X.index <= TODAY][-1]
    P_done = P[P.index <= last_complete]
    Y = C.extra_targets(P_done, C.targets(P_done, "W"), "W").reindex(X.index)
    fresh = C.fresh_mask(P, "W")
    say(f"study9_checks  data last bar {stamp(last_bar)}; last complete Sunday close {last_complete.date()} (bar {stamp(last_complete)}); provisional {[str(d.date()) for d in provisional]}; "
        f"fast={a.fast} random nulls {n_null} boots {n_boot}")
    notes.append(f"Last complete Sunday close {last_complete.date()}; provisional bars {[str(d.date()) for d in provisional]} enter no training label and no evaluation label.")
    notes.append("btc_dd_ath is the true-ATH drawdown (study8_honest.ath_drawdown, weekly closes from 2013-02) for every model including the forward fixed5 reference (identical to three decimals to the baselines' harness-anchored fixed5); the harness column (anchored 2014-04) is kept only for the readiness_harnessATH comparator.")

    # ======================================================================================= QUESTION A: reverse walk-forward
    rev_mask = (X.index >= pd.Timestamp(REV_ERA[1])) & (X.index < pd.Timestamp(REV_ERA[2]))
    rev_pos = np.where(rev_mask)[0]
    rev_last = X.index[rev_mask][-1]
    purged_from = rev_last + pd.Timedelta(weeks=LAG_WEEKS + 1)          # the forward harness's gap: training rows < t - lag
    WINDOWS = {"plan": TRAIN_FROM, "purged": purged_from}
    A = {"design": {"windows": {k: str(v.date()) for k, v in WINDOWS.items()}, "headlineWindow": HEADLINE_WINDOW, "scoreEra": REV_ERA, "subEras": REV_SUB, "labelLagWeeks": LAG_WEEKS,
                    "purgeNote": f"the plan window's first {LAG_WEEKS} training rows are labelled by the same {rev_last.year + 1}-H1 BTC.D path that labels the last {LAG_WEEKS} evaluation rows; "
                                 f"the purged window starts {LAG_WEEKS + 1} weeks after the last evaluation row ({rev_last.date()}), as the forward harness's label lag does"},
         "models": {}, "oos": {}, "paired": {}, "null": {}, "peaks": {}, "forward": {}, "decoys": {}, "jackknife": {}, "success": {}}
    preds_all, models = {}, {}
    # decoys with no market information: the sub-era indicator (1 in 2016-17, 0 in 2018) and a descending time trend
    sub_ind = pd.Series((X.index < pd.Timestamp(REV_SUB[1][1])).astype(float), index=X.index)
    trend = pd.Series(-np.arange(len(X), dtype=float), index=X.index)
    for win, tfrom in WINDOWS.items():
        train_mask = (X.index >= tfrom) & (X.index <= last_complete)
        preds_all[win], A["oos"][win], A["paired"][win], A["null"][win], A["models"][win], A["decoys"][win], A["peaks"][win] = {}, {}, {}, {}, {}, {}, {}
        for tg in TARGETS:
            preds = {}
            for name, cols in MODELS.items():
                m = frozen_fit(X, Y[tg], cols, train_mask)
                models[(win, name, tg)] = m
                preds[name] = frozen_predict(m, X)
            preds["readiness"] = readiness_rule(X["btc_dd_ath"], X["m2_yoy"])                      # the rule under the true (2013) ATH anchor (no fitted object: identical in both windows)
            preds["readiness_harnessATH"] = readiness_rule(dd_harness[keep], X["m2_yoy"])        # and under the harness (2014) anchor
            common = rev_mask & Y[tg].notna()
            for p in preds.values():
                common &= p.notna()
            decoys = {"decoy_subEra": sub_ind, "decoy_subEra_commonRows": sub_ind.where(common), "decoy_trend": trend, "decoy_trend_commonRows": trend.where(common)}
            preds_all[win][tg] = preds
            base = models[(win, "fixed5", tg)]["trainBase"]
            A["oos"][win][tg] = {}
            for name, p in preds.items():
                r = full_metrics(p, Y[tg], base, rev_mask, REV_SUB, fresh)
                r["common"] = slice_metrics(p, Y[tg], common, base)
                if (win, name, tg) in models:
                    r["clip"] = clipped_share(models[(win, name, tg)], X, rev_mask)
                A["oos"][win][tg][name] = r
            A["decoys"][win][tg] = {name: {"auc": rnd(C.auc(p.values[rev_pos], Y[tg].values[rev_pos]), 3), "n": int((p.notna() & Y[tg].notna() & rev_mask).sum())} for name, p in decoys.items()}
            A["paired"][win][tg] = paired_set(preds, "fixed5", Y[tg], rev_mask, REV_SUB, fresh, n_boot, rng)
            nulls = frozen_nulls({**preds, **decoys}, Y, tg, rev_pos, n_null, rng)
            A["null"][win][tg] = {"meta": nulls["_meta"]}
            for name in preds:
                real = A["oos"][win][tg][name]["own"].get("auc")
                A["null"][win][tg][name] = {"shift": null_summary(real, nulls[name]["shift"], exact=True), "perm": null_summary(real, nulls[name]["perm"], exact=nulls["_meta"]["permExact"])}
            for name in decoys:
                real = A["decoys"][win][tg][name]["auc"]
                A["decoys"][win][tg][name].update({"shift": null_summary(real, nulls[name]["shift"], exact=True), "perm": null_summary(real, nulls[name]["perm"], exact=nulls["_meta"]["permExact"])})
            A["models"][win][tg] = {name: {"nTrain": m["nTrain"], "trainFrom": m["trainFrom"], "trainTo": m["trainTo"], "trainBase": rnd(m["trainBase"]),
                                           "coef_z": {c: rnd(w) for c, w in zip(["intercept"] + m["cols"], m["w"])}} for (w_, name, t), m in models.items() if t == tg and w_ == win}
        # readings on the big-event peak weeks
        for e in C.BIG_EVENTS:
            t = pd.Timestamp(e)
            row = {"inTraining": bool(t >= tfrom), "label_fall5_26w": rnd(Y["fall5_26w"].get(t, np.nan), 0), "label_fall10_26w": rnd(Y["fall10_26w"].get(t, np.nan), 0)}
            for tg in TARGETS:
                row[tg] = {name: rnd(p.get(t, np.nan)) for name, p in preds_all[win][tg].items()}
            row["inputs"] = {c: rnd(X.loc[t, c]) for c in B.SIGNALS}
            A["peaks"][win][e] = row
        # jackknife of the training blocks (fall5 only; the boundary block is the one the purge removes)
        if win == "plan":
            A["jackknife"] = {name: jackknife_blocks(X, Y["fall5_26w"], cols, train_mask, rev_pos) for name, cols in MODELS.items()}

    ep_rev = {tg: len(C.episodes(Y[tg].values[rev_pos])) for tg in TARGETS}
    say(f"A reverse: scored on {REV_ERA[1]}..{REV_ERA[2]}: {len(rev_pos)} rows, fall5 base {fmt(float(np.nanmean(Y['fall5_26w'].values[rev_pos])))} in {ep_rev['fall5_26w']} episodes, "
        f"fall10 base {fmt(float(np.nanmean(Y['fall10_26w'].values[rev_pos])))} in {ep_rev['fall10_26w']} episode(s); fixed5/m2eth rows start {preds_all['plan']['fall5_26w']['fixed5'][rev_mask].dropna().index[0].date()} (ETH/BTC 52w high undefined before); "
        f"shifted null enumerated exactly ({A['null']['plan']['fall5_26w']['meta']['distinctShifts']} admissible shifts); perm null fall5 {A['null']['plan']['fall5_26w']['meta']['nBlocks']} blocks ({'exact' if A['null']['plan']['fall5_26w']['meta']['permExact'] else str(A['null']['plan']['fall5_26w']['meta']['permDraws']) + ' random draws'}), "
        f"fall10 {A['null']['plan']['fall10_26w']['meta']['nBlocks']} blocks ({'exact, ' + str(A['null']['plan']['fall10_26w']['meta']['permDraws']) + ' arrangements' if A['null']['plan']['fall10_26w']['meta']['permExact'] else 'random'})")
    for win in WINDOWS:
        m5, m10 = models[(win, "fixed5", "fall5_26w")], models[(win, "fixed5", "fall10_26w")]
        say(f" window {win} (train {m5['trainFrom']}..{m5['trainTo']}, {m5['nTrain']} rows, base fall5 {fmt(m5['trainBase'])} / fall10 {fmt(m10['trainBase'])}){' [HEADLINE]' if win == HEADLINE_WINDOW else ' [plan text; see jackknife]'}: "
            f"model | fall5 AUC own (n) common | 2016-17 2018 strat fresh | pairs cross-share/within-AUC | LOO nEp/min | clip | Brier vs base2019 | shift perm || fall10 AUC shift LOO")
        for name in preds_all[win]["fall5_26w"]:
            if win != "plan" and name.startswith("readiness"):
                continue                                                                  # no fitted object: identical to the plan window's line
            r5, r10 = A["oos"][win]["fall5_26w"][name], A["oos"][win]["fall10_26w"][name]
            n5, n10 = A["null"][win]["fall5_26w"][name], A["null"][win]["fall10_26w"][name]
            pr, l5, l10 = r5["pairs"], r5["episodeLOO"], r10["episodeLOO"]
            clip = r5.get("clip", {})
            say(f"  {name:<21} {fmt(r5['own'].get('auc'))} (n{r5['own'].get('n')}) {fmt(r5['common'].get('auc'))} | {auc_str(r5['2016-2017'])} {auc_str(r5['2018'])} {fmt(r5['eraStratAuc'])} {fmt(r5['fresh'].get('auc'))} | "
                f"{fmt(pr.get('crossShare'), 2)}/{fmt(pr.get('withinAuc'))} | {l5['nEpisodes']}/{fmt(l5['min'])} | {clip.get('clipped', '-')}/{clip.get('rows', '-')} | {fmt(r5['own'].get('brier'), 4)} vs {fmt(r5['own'].get('brierBase2019'), 4)} | "
                f"shift {ns_str(n5['shift'])} perm {ns_str(n5['perm'])} || {fmt(r10['own'].get('auc'))} shift {ns_str(n10['shift'])} LOO {l10['nEpisodes']}/{fmt(l10['min'])}{' (one event)' if l10['nEpisodes'] == 1 else ''}")
        for name, row in A["paired"][win]["fall5_26w"].items():
            say(f"  paired {name}-fixed5 fall5: pooled {pb_str(row['pooled'])} 2016-17 {pb_str(row['2016-2017'])} 2018 {pb_str(row['2018'])} strat {pb_str(row['eraStrat'])} fresh {pb_str(row['fresh'])}; fall10 pooled {pb_str(A['paired'][win]['fall10_26w'][name]['pooled'])}")
        pk = A["peaks"][win]
        say(f"  peak-week readings P(fall5_26w), {win} window: " + "; ".join(f"{e}{' (in training)' if pk[e]['inTraining'] else ''}: " + ", ".join(f"{n} {fmt(v)}" for n, v in pk[e]["fall5_26w"].items()) for e in C.BIG_EVENTS)
            + " [na = ETH/BTC 52-week high undefined]")
    dc = A["decoys"]["plan"]
    say("  decoys (no market information, same nulls): " + "; ".join(f"{k} fall5 AUC {fmt(v['auc'])} (n{v['n']}) shift {ns_str(v['shift'])} perm {ns_str(v['perm'])}" for k, v in dc["fall5_26w"].items())
        + " | fall10: " + ", ".join(f"{k} {fmt(v['auc'])} shift p {fmt(v['shift'].get('p'))}" for k, v in dc["fall10_26w"].items()))
    jk = A["jackknife"]
    say("  jackknife (plan window, fall5, drop each 26-week training block and refit): " + "; ".join(f"{k} boundary block {v['boundaryBlock']} delta {fmt(v['boundaryDelta'])} vs other {v['nBlocks'] - 1} blocks max|delta| {fmt(v['otherBlocks']['maxAbsDelta'])}" for k, v in jk.items())
        + f"; purged - plan AUC: " + ", ".join(f"{k} {fmt(None if A['oos']['purged']['fall5_26w'][k]['own'].get('auc') is None or A['oos']['plan']['fall5_26w'][k]['own'].get('auc') is None else A['oos']['purged']['fall5_26w'][k]['own']['auc'] - A['oos']['plan']['fall5_26w'][k]['own']['auc'])}" for k in MODELS))

    # pre-registered success: AUC above the shifted null p95 for fixed5 and for M2-only (evaluated as written, on each window)
    for win in WINDOWS:
        crit = {}
        for tg in TARGETS:
            for name in ("fixed5", "m2only"):
                s = A["null"][win][tg][name]["shift"]
                real = A["oos"][win][tg][name]["own"].get("auc")
                ok = (real is not None and s.get("nullP95") is not None and real > s["nullP95"])
                crit[f"{name}:{tg}"] = {"auc": real, "nullP95": s.get("nullP95"), "p": s.get("p"), "draws": s["n"], "exact": s["exact"], "quotable": s["quotable"], "margin": rnd(None if not ok else real - s["nullP95"], 3),
                                        "verdict": ("NO VERDICT (provisional: " + ("pass" if ok else "fail") + ")") if not s["quotable"] else ("pass" if ok else "fail"),
                                        "oneEvent": bool(A["oos"][win][tg][name]["episodeLOO"]["nEpisodes"] == 1)}
        chance = {name: (A["oos"][win]["fall5_26w"][name]["own"].get("auc") is not None and A["null"][win]["fall5_26w"][name]["shift"].get("nullP95") is not None
                         and A["oos"][win]["fall5_26w"][name]["own"]["auc"] <= A["null"][win]["fall5_26w"][name]["shift"]["nullP95"]) for name in preds_all[win]["fall5_26w"]}
        # beside the criterion: does the pass survive the sub-era decoy, the within-sub-era ranking and the dwell-time permutation?
        reading = {}
        for name in ("fixed5", "m2only", "m2eth", "readiness"):
            r = A["oos"][win]["fall5_26w"][name]
            dkey = "decoy_subEra_commonRows" if name in ("fixed5", "m2eth") else "decoy_subEra"
            dec = A["decoys"][win]["fall5_26w"][dkey]["auc"]
            pp = A["null"][win]["fall5_26w"][name]["perm"]
            beats = (r["own"].get("auc") is not None and dec is not None and r["own"]["auc"] > dec)
            within, wpairs = r["eraStratAuc"], r["pairs"].get("withinPairs")
            perm_txt = (f"permutation p {fmt(pp.get('p'))}" + ("" if pp.get("p") is None else (" < 0.05" if pp["p"] < 0.05 else " >= 0.05"))) if pp.get("quotable") else f"permutation null not quotable ({pp.get('n')} draws)"
            decoy_txt = (f"pooled AUC above the sub-era decoy's {fmt(dec)} on the same rows" if beats else f"pooled AUC below the sub-era decoy's {fmt(dec)} on the same rows, so the pooled number is mostly the 2016-17 vs 2018 level")
            if chance[name]:
                kind = "at chance on 2016-18 (cycle-specific)"
            elif within is None:
                kind = "within-sub-era ranking undefined; " + decoy_txt
            elif within <= 0.5:
                kind = f"LEVEL ONLY: passes the shifted null through the 2016-17 vs 2018 level ranking; within-sub-era AUC {fmt(within)} ({wpairs} pairs) is at or below chance; {perm_txt}; {decoy_txt}"
            else:
                kind = f"within-cycle ranking present: within-sub-era AUC {fmt(within)} ({wpairs} pairs), {perm_txt}; {decoy_txt}"
            reading[name] = {"auc": r["own"].get("auc"), "subEraDecoyAucSameRows": dec, "beatsDecoy": bool(beats), "within2018Auc": r["2018"].get("auc"), "eraStratAuc": within, "withinSubEraPairs": wpairs,
                             "crossSubEraPairShare": r["pairs"].get("crossShare"), "permP": pp.get("p"), "permQuotable": pp.get("quotable"), "clippedRows": r.get("clip", {}).get("share"), "reading": kind}
        A["success"][win] = {"criterion": "AUC on 2016-18 above the shifted-target null p95 for fixed5 and for M2-only (fall5_26w headline; fall10_26w beside it, one event)", "trainFrom": str(WINDOWS[win].date()), "perModel": crit,
                             "headline": ("NO VERDICT" if not all(c["quotable"] for c in crit.values()) else ("pass" if all(c["verdict"] == "pass" for k, c in crit.items() if k.endswith("fall5_26w")) else "fail")),
                             "cycleSpecific_fall5_atChance": chance, "readThrough": reading}
        c5f, c5m = crit["fixed5:fall5_26w"], crit["m2only:fall5_26w"]
        say(f"A SUCCESS {win} window{' [HEADLINE]' if win == HEADLINE_WINDOW else ''} (fall5_26w): fixed5 {c5f['verdict']} (AUC {fmt(c5f['auc'])} vs exact p95 {fmt(c5f['nullP95'])}, p {fmt(c5f['p'])}; {reading['fixed5']['reading']}; clipped rows {fmt(reading['fixed5']['clippedRows'], 2)}); "
            f"m2only {c5m['verdict']} (AUC {fmt(c5m['auc'])} vs p95 {fmt(c5m['nullP95'])}, p {fmt(c5m['p'])}, margin {fmt(c5m['margin'])}; {reading['m2only']['reading']}); "
            f"fall10 (one event): fixed5 {crit['fixed5:fall10_26w']['verdict']} m2only {crit['m2only:fall10_26w']['verdict']}; at chance on 2016-18 (cycle-specific): {[k for k, v in chance.items() if v] or 'none'} -> {A['success'][win]['headline']}")
    A["success"]["headline"] = A["success"][HEADLINE_WINDOW]["headline"]
    A["success"]["headlineWindow"] = HEADLINE_WINDOW
    A["success"]["windowsAgree"] = bool(A["success"]["plan"]["headline"] == A["success"]["purged"]["headline"])
    A["success"]["selectionNote"] = ("The reversed era is out of sample for the fitted coefficients only: the readiness rule's thresholds (within 5% of ATH, M2 y/y > 0) were read off what preceded the three big waterfalls (ROUND8_BRIEF item 3), two of which are in 2016-18, "
                                     "and fixed5's five inputs are round 7's most-picked signals from a selection whose training windows start 2016-06-01 (ROUND8_BRIEF item 6); M2-only is the only comparator whose variable choice is blind to 2016-18.")

    # ---- forward reference: the same four models through the standard harness from 2019 (no nulls here: baselines has them)
    fwd_preds = {}
    for tg in TARGETS:
        fp = {}
        for name, cols in MODELS.items():
            fp[name], _ = B.run_fixed(X, Y, tg, "W", True, cols)
        rule = readiness_rule(X["btc_dd_ath"], X["m2_yoy"])
        fp["readiness"] = rule.where(X.index >= TRAIN_FROM)
        fwd_preds[tg] = fp
        fmask = (X.index >= TRAIN_FROM) & Y[tg].notna()
        for p in fp.values():
            fmask &= p.notna()
        A["forward"][tg] = {"rows": int(fmask.sum()), "firstRow": str(X.index[fmask][0].date()), "oos": {}, "paired": paired_set(fp, "fixed5", Y[tg], fmask, C.ERAS, fresh, n_boot, rng)}
        for name, p in fp.items():
            met = C.metrics(p.where(fmask), Y[tg], True, is_prob=True)
            r = {k: {"n": v["n"], "auc": v["auc"], "base": v["base"], "brier": v["brier"]} for k, v in met.items()}
            r["eraStratAuc"] = H.era_strat_auc(p.where(fmask), Y[tg])["eraStratAuc"]
            r["fresh"] = {k: v.get("auc") for k, v in C.metrics(p.where(fmask & fresh), Y[tg], True).items()}
            r["today"] = rnd(p.get(last_complete, np.nan))
            A["forward"][tg][name] = r
    f5 = A["forward"]["fall5_26w"]
    say(f"A forward (standard harness from 2019, common rows n{f5['rows']} from {f5['firstRow']}) P(fall5_26w) AUC pooled / 2019-20 / 2021-22 / 2023-26 / strat / fresh; paired-fixed5 pooled [blk; epi], strat, fresh:")
    for name in fwd_preds["fall5_26w"]:
        r = f5[name]
        pr = f5["paired"].get(name)
        say(f"  {name:<21} {fmt(r['pooled']['auc'])} / {fmt(r.get('2019-2020', {}).get('auc'))} / {fmt(r.get('2021-2022', {}).get('auc'))} / {fmt(r.get('2023-2026', {}).get('auc'))} / {fmt(r['eraStratAuc'])} / {fmt(r['fresh'].get('pooled'))}; "
            + (f"paired {pb_str(pr['pooled'])} strat {pb_str(pr['eraStrat'])} fresh {pb_str(pr['fresh'])}; " if pr else "reference; ") + f"fall10 AUC {fmt(A['forward']['fall10_26w'][name]['pooled']['auc'])}; today {fmt(r['today'], 4)}")
    say("A reverse (purged / plan) vs forward P(fall5_26w) AUC: " + "; ".join(f"{n} {fmt(A['oos']['purged']['fall5_26w'][n]['own'].get('auc'))} / {fmt(A['oos']['plan']['fall5_26w'][n]['own'].get('auc'))} vs {fmt(f5[n]['pooled']['auc'])}" for n in preds_all["plan"]["fall5_26w"] if n in f5))

    # ======================================================================================= QUESTION B: what would change the forecast
    Bq = {}
    # (1) one input at a time at its big-event-peak value, the rest at today (fixed5, last walk-forward refit)
    m5, fwd_fixed5, refits = last_refit_model(X, Y, "fall5_26w")
    xt = X.loc[last_complete, B.SIGNALS].values.astype(float)
    p_today = float(C.logistic_predict(C.zapply(xt[None, :], m5["mu"], m5["sd"]), m5["w"])[0])
    harness_today = float(fwd_fixed5.get(last_complete, np.nan))
    assert abs(p_today - harness_today) < 1e-9, (p_today, harness_today)
    one = {"model": {"lastRefit": refits[-1]["t"], "nTrain": m5["nTrain"], "coef_z": {c: rnd(w) for c, w in zip(["intercept"] + B.SIGNALS, m5["w"])}, "trainSd": {c: rnd(s) for c, s in zip(B.SIGNALS, m5["sd"])}, "clipSd": CLIP},
           "today": {"asOf": str(last_complete.date()), "fixed5": rnd(p_today), "inputs": {c: rnd(v) for c, v in zip(B.SIGNALS, xt)}, "z": {c: rnd((v - mu) / sd, 2) for c, v, mu, sd in zip(B.SIGNALS, xt, m5["mu"], m5["sd"])}}, "peaks": {}}
    for e in C.BIG_EVENTS:
        t = pd.Timestamp(e)
        xp = X.loc[t, B.SIGNALS].values.astype(float)
        zp = (xp - m5["mu"]) / m5["sd"]
        row = {"readingAllAtPeak": None, "inputsAtClipAllAtPeak": [c for c, z in zip(B.SIGNALS, zp) if np.isfinite(z) and abs(z) > CLIP], "perInput": {}}
        if np.isfinite(xp).all():
            row["readingAllAtPeak"] = rnd(C.logistic_predict(C.zapply(xp[None, :], m5["mu"], m5["sd"]), m5["w"])[0])
        for j, c in enumerate(B.SIGNALS):
            if not np.isfinite(xp[j]):
                row["perInput"][c] = {"peakValue": None, "move": None, "moveSd": None, "zAtPeak": None, "atClip": None, "reading": None, "note": "not identifiable (input undefined at that week)"}
                continue
            x1 = xt.copy()
            x1[j] = xp[j]
            at_clip = bool(abs(zp[j]) > CLIP)
            row["perInput"][c] = {"peakValue": rnd(xp[j]), "move": rnd(xp[j] - xt[j]), "moveSd": rnd((xp[j] - xt[j]) / m5["sd"][j], 2), "zAtPeak": rnd(zp[j], 2), "atClip": at_clip,
                                  "reading": rnd(C.logistic_predict(C.zapply(x1[None, :], m5["mu"], m5["sd"]), m5["w"])[0]),
                                  "note": (f"the model consumes this input at the {'-' if zp[j] < 0 else '+'}{CLIP:.0f} sd clip (z {zp[j]:.1f}): the reading is what the clipped value gives, a larger move adds nothing" if at_clip else None)}
        one["peaks"][e] = row
    Bq["oneInputAtPeak"] = one
    say(f"B1 fixed5 (last refit {refits[-1]['t']}, {m5['nTrain']} rows) today {fmt(p_today, 4)}; inputs " + ", ".join(f"{c} {fmt(v)}" for c, v in zip(B.SIGNALS, xt)) + "; coef(z) " + ", ".join(f"{c} {fmt(w, 2)}" for c, w in zip(B.SIGNALS, m5['w'][1:]))
        + f"; [clip] = the input sits beyond the scaler's +/-{CLIP:.0f} sd clip at that peak")
    for e in C.BIG_EVENTS:
        row = one["peaks"][e]
        say(f"  {e}: all inputs at peak -> {fmt(row['readingAllAtPeak'], 4)}{' (clipped: ' + ','.join(row['inputsAtClipAllAtPeak']) + ')' if row['inputsAtClipAllAtPeak'] else ''}; one at a time (move, sd, reading): " + "; ".join(
            f"{c} {fmt(r['move'])} ({fmt(r['moveSd'], 1)}sd) -> {fmt(r['reading'], 4)}{' [clip]' if r['atClip'] else ''}" if r["reading"] is not None else f"{c} na" for c, r in row["perInput"].items()))

    # (2) readiness-gate spells since 2014 on weekly closes and the lead to the next 5+ point fall (Kaplan-Meier)
    m2_long = m2_yoy_long(a.data, P_full.index)                                # the loader's definition (6-week lag, 52-week log change) on a longer M2 history
    dd_long = H.ath_drawdown(a.data, P_full.index)
    chk = float((m2_long - X_full["m2_yoy"]).abs().max())
    assert chk < 1e-9, chk
    gate_long = readiness_rule(dd_long, m2_long)
    gate_long = gate_long[gate_long.index <= last_complete]
    Y_long = C.targets(P_full[P_full.index <= last_complete], "W")
    spells, ev5 = gate_spells(gate_long, P_full["BTC.D"][P_full.index <= last_complete], Y_long)
    km_plan = km_block(spells, "kmTime", "kmEvent")                            # the plan's outcome: lead to the next 5+ point fall PEAK
    km_lvl = km_block(spells, "km5Time", "km5Event")                           # 5+ points under the switch-on level
    outside = [s for s in spells if s["startsInsideFall"] is None]
    km_out_plan = km_block(outside, "kmTime", "kmEvent")
    km_out_lvl = km_block(outside, "km5Time", "km5Event")
    n_ev = km_plan["nEvents"]
    gate_now = bool(gate_long.iloc[-1] > 0.5)
    dd_now = float(X.loc[last_complete, "btc_dd_ath"])
    rally_needed = float(np.exp(np.log(0.95) - dd_now) - 1) if dd_now < np.log(0.95) else 0.0
    Bq["gateLead"] = {"spells": spells, "nSpells": len(spells), "nWithFallWithin52w": n_ev, "nStartInsideFall": len(spells) - len(outside),
                      "kmS": km_plan["S"], "kmWeeks": km_plan["kmWeeks"], "kmP_fallWithin26w": km_plan["kmP_within26w"], "kmP_fallWithin52w": km_plan["kmP_within52w"],
                      "outcomeDefinitions": {"leadToNextFallPeak_allSpells": {k: v for k, v in km_plan.items() if k != "S"},
                                             "fivePointsUnderSwitchOnLevel_allSpells": {k: v for k, v in km_lvl.items() if k != "S"},
                                             "leadToNextFallPeak_spellsStartingOutsideAFall": {k: v for k, v in km_out_plan.items() if k != "S"},
                                             "fivePointsUnderSwitchOnLevel_spellsStartingOutsideAFall": {k: v for k, v in km_out_lvl.items() if k != "S"},
                                             "note": "the plan's outcome is the first; a spell that switches on inside a fall already under way is credited with the lead to the FOLLOWING peak under it, "
                                                     "and with the weeks to 5 points under its own switch-on level under the second; neither definition makes flickers of one run-up independent"},
                      "gateFirstRow": str(gate_long.dropna().index[0].date()), "falls5ptSince2014": [{"peak": str(e["peak"].date()), "from": round(e["from"], 1), "to": round(e["to"], 1), "days": e["days"]} for e in ev5],
                      "today": {"gateOn": gate_now, "btc_dd_ath": rnd(dd_now), "btcRallyNeededToWithin5pctOfATH": rnd(rally_needed), "m2_yoy": rnd(float(X.loc[last_complete, "m2_yoy"])), "m2Above0": bool(X.loc[last_complete, "m2_yoy"] > 0)}}
    merged = merge_spells(spells)
    kmm = km_block(merged, "kmTime", "kmEvent")
    kmm5 = km_block(merged, "km5Time", "km5Event")
    Bq["gateLead"]["mergedSpells_gapUnder13w"] = {"n": len(merged), "nWithFall": kmm["nEvents"], "leads": [x["leadWeeksToNextFallPeak"] for x in merged], "kmWeeks": kmm["kmWeeks"], "kmP_fallWithin26w": kmm["kmP_within26w"], "kmP_fallWithin52w": kmm["kmP_within52w"],
                                                  "fivePointsUnderSwitchOnLevel": {k: v for k, v in kmm5.items() if k != "S"},
                                                  "note": "flickers of the gate inside one run-up counted once; the plan's every-spell reading is the primary one; at most five independent run-ups either way"}
    leads = [s["leadWeeksToNextFallPeak"] for s in spells]
    say(f"B2 readiness gate (true ATH, M2 y/y > 0) since {Bq['gateLead']['gateFirstRow']}: {len(spells)} on-spells, {n_ev} followed by a 5+ fall peak within 52 weeks; leads (weeks) {leads}; "
        f"KM median lead {km_plan['kmWeeks'].get('w50')} w (10/90% {km_plan['kmWeeks'].get('w10')}/{km_plan['kmWeeks'].get('w90')}), P(fall peak within 26 w) {fmt(km_plan['kmP_within26w'])}, within 52 w {fmt(km_plan['kmP_within52w'])} [plan outcome: next fall PEAK]; "
        f"today gate {'ON' if gate_now else 'OFF'}: BTC {fmt(100 * (1 - np.exp(dd_now)), 1)}% under ATH, needs +{fmt(100 * rally_needed, 1)}% to within 5%; M2 y/y {fmt(100 * X.loc[last_complete, 'm2_yoy'], 1)}% ({'>' if X.loc[last_complete, 'm2_yoy'] > 0 else '<='} 0)")
    say(f"   other outcome definitions: 5+ points under the switch-on level (all {km_lvl['n']} spells): {km_lvl['nEvents']} events, KM median {km_lvl['kmWeeks'].get('w50')} w (10/90% {km_lvl['kmWeeks'].get('w10')}/{km_lvl['kmWeeks'].get('w90')}), P(26 w) {fmt(km_lvl['kmP_within26w'])}, P(52 w) {fmt(km_lvl['kmP_within52w'])}; "
        f"{Bq['gateLead']['nStartInsideFall']} of {len(spells)} spells switch on inside a fall already under way; the {len(outside)} that start outside one: next-peak median {km_out_plan.get('kmWeeks', {}).get('w50')} w ({km_out_plan.get('nEvents')} events, P(26 w) {fmt(km_out_plan.get('kmP_within26w'))}), "
        f"5-pt-under-level median {km_out_lvl.get('kmWeeks', {}).get('w50')} w ({km_out_lvl.get('nEvents')} events, P(26 w) {fmt(km_out_lvl.get('kmP_within26w'))}); the median lead is a definitional choice between these, from at most five independent run-ups")
    mg = Bq["gateLead"]["mergedSpells_gapUnder13w"]
    say(f"   merged spells (gap < 13 w counted once): {mg['n']} spells, {mg['nWithFall']} with a fall peak within 52 w, leads {mg['leads']}, KM median {mg['kmWeeks'].get('w50')} w (10/90% {mg['kmWeeks'].get('w10')}/{mg['kmWeeks'].get('w90')}), P(within 26 w) {fmt(mg['kmP_fallWithin26w'])}, P(within 52 w) {fmt(mg['kmP_fallWithin52w'])}; "
        f"5-pt-under-level: median {kmm5['kmWeeks'].get('w50')} w, P(26 w) {fmt(kmm5['kmP_within26w'])}")
    say("   spells: " + "; ".join(f"{s['start']}({s['weeksOn']}w{', in fall' if s['startsInsideFall'] else ''})->" + (f"{s['nextFall']['peak']} lead {s['leadWeeksToNextFallPeak']}w {s['nextFall']['from']}->{s['nextFall']['to']}" if isinstance(s['nextFall'], dict) else ("data end" if s['censoredByDataEnd'] else "none in 52w"))
                                  + f" | 5pt-under {s['km5Time']}w{'' if s['km5Event'] else '+'}" for s in spells))

    # (3) calendar falsifiers: block copied from study8_honest.py main (section "falsifiers (calendar)"), TODAY = the data's last bar
    bw = P_done["BTC.D"]
    after = bw[bw.index >= H.HIGHER_HIGH_FROM]
    hh = float(after.max())
    ev5w = C.events(bw, 5.0, freq="W")
    last5 = ev5w[-1] if ev5w else None
    ev10w = C.events(bw, 10.0, freq="W")
    last10 = ev10w[-1] if ev10w else None
    post_trough_hi = float(bw[bw.index > last5["trough"]].max()) if last5 is not None else None
    new_fall_pts = (post_trough_hi - float(bw.loc[last_complete])) if post_trough_hi is not None else None
    falsifiers = {
        "i_higherHighAbove65.7": {"status": "FAIL (thesis falsified for this cycle)" if hh > H.JUN2025_PEAK else "not-yet", "maxWeeklyCloseSince2025-06-29": round(hh, 2), "date": str(after.idxmax().date()), "threshold": H.JUN2025_PEAK,
                                  "lastCompleteClose": round(float(bw.loc[last_complete]), 2), "pointsToThreshold": round(H.JUN2025_PEAK - float(bw.loc[last_complete]), 2)},
        "ii_engineImminentSinceFeb2023": {"status": ("not-yet" if TODAY < H.FALSIFIER_DATE else "FAIL"), "deadline": str(H.FALSIFIER_DATE.date()), "daysToDeadline": int((H.FALSIFIER_DATE - TODAY).days),
                                          "last10ptFallPeak": (str(last10["peak"].date()) if last10 else None), "weeksEngineHasSaidImminent": int((TODAY - pd.Timestamp("2023-02-01")).days // 7),
                                          "note": "the engine's current mapping is read from docs/FRACTAL.md (10 Dec 2017 week since Feb 2023); this module records only the calendar and the falls"},
        "iii_nextFallWhileEngineFit<0.8": {"status": "not-yet", "last5ptFall": ({"peak": str(last5["peak"].date()), "trough": str(last5["trough"].date()), "days": last5["days"]} if last5 else None),
                                           "postTroughHigh": (round(post_trough_hi, 2) if post_trough_hi is not None else None), "pointsBelowPostTroughHigh": (round(new_fall_pts, 2) if new_fall_pts is not None else None),
                                           "newFallStarted": bool(new_fall_pts is not None and new_fall_pts >= 5.0),
                                           "note": "not identifiable here: needs the engine's live fit and lead window at the start of the next 5+ fall; this module records whether such a fall has started"},
        "source": "copied from study8_honest.py main (calendar falsifier block), TODAY taken from the data's last bar; the 65.7 threshold and the 2027-11-02 deadline are ROUND8_PLAN's hand-set constants"}
    Bq["falsifiers"] = falsifiers
    say(f"B3 falsifiers (TODAY = data last bar {TODAY.date()}; thresholds hand-set by ROUND8_PLAN): (i) {falsifiers['i_higherHighAbove65.7']['status']} max weekly close since 2025-06-29 {hh:.1f} vs 65.7 (last close {falsifiers['i_higherHighAbove65.7']['lastCompleteClose']}, {falsifiers['i_higherHighAbove65.7']['pointsToThreshold']} pts below); "
        f"(ii) {falsifiers['ii_engineImminentSinceFeb2023']['status']} {falsifiers['ii_engineImminentSinceFeb2023']['daysToDeadline']} days to 2027-11-02, engine 'imminent' {falsifiers['ii_engineImminentSinceFeb2023']['weeksEngineHasSaidImminent']} weeks, last 10pt fall peak {falsifiers['ii_engineImminentSinceFeb2023']['last10ptFallPeak']}; "
        f"(iii) {falsifiers['iii_nextFallWhileEngineFit<0.8']['status']} last 5pt fall {last5['peak'].date() if last5 else None}->{last5['trough'].date() if last5 else None}, now {fmt(new_fall_pts, 1)} pts under the post-trough high (new fall started: {falsifiers['iii_nextFallWhileEngineFit<0.8']['newFallStarted']})")

    # (4) decision table: threshold = 1 / (1 + ratio); which readings of the round-8 forecast object clear it
    readings = {"fixed5": p_today, "m2only": A["forward"]["fall5_26w"]["m2only"]["today"]}
    spread, src = None, None
    for path, key in ((os.path.join(os.path.dirname(a.out.rstrip("/")), "..", "out8", "forecast", "results.json"), ("today", "onset", "spread_fall5_26w_componentsInSupport")),
                      (os.path.join(os.path.dirname(a.out.rstrip("/")), "..", "out8", "honest", "results.json"), ("today", "spreadFall5_26w_inSupport"))):
        try:
            with open(path) as fh:
                r = json.load(fh)
            for k in key:
                r = r[k]
            if r and len(r) == 2:
                spread, src = [float(r[0]), float(r[1])], os.path.normpath(path) + ":" + "/".join(key)
                break
        except Exception:
            continue
    hand_set = spread is None
    if hand_set:
        spread, src = list(FALLBACK_SPREAD), "ROUND8_PLAN.md 'four defensible specifications' 3.9%..35% (no out8/forecast or out8/honest results.json present): HAND-SET fallback, not a model reading"
    lo_key, hi_key = ("spreadLow_handSetFallback", "spreadHigh_handSetFallback") if hand_set else ("spreadLow", "spreadHigh")
    readings[lo_key], readings[hi_key] = spread[0], spread[1]
    table = []
    for r in RATIOS:
        thr = 1.0 / (1.0 + r)
        table.append({"costRatio_missedSeason_to_falseAlarm": r, "threshold": round(thr, 4), "clearedBy": [k for k, v in readings.items() if v is not None and v >= thr],
                      "clearedByComputedReadings": [k for k, v in readings.items() if v is not None and v >= thr and not k.endswith("handSetFallback")]})
    Bq["decision"] = {"readings": {k: rnd(v) for k, v in readings.items()}, "computedReadings": ["fixed5", "m2only"], "spreadSource": src, "spreadHandSet": hand_set, "table": table, "rule": "act when P(fall5_26w) >= 1 / (1 + ratio)"}
    say(f"B4 decision table (act when P >= 1/(1+ratio)); computed readings fixed5 {fmt(p_today, 3)}, m2only {fmt(readings['m2only'], 3)}; in-support spread [{fmt(spread[0], 3)}, {fmt(spread[1], 3)}] ({'HAND-SET plan fallback 3.9%..35%, no out8 forecast/honest results present: a typed number, not a model reading' if hand_set else src}): "
        + "; ".join(f"ratio {t['costRatio_missedSeason_to_falseAlarm']} thr {t['threshold']:.3f} -> {t['clearedBy'] or 'none'}" for t in table))

    # ======================================================================================= leakage checks
    # truncation: the readiness gate and the frozen fixed5 score (headline window) recomputed on the panel truncated at t equal the full values
    def gate_at(end_pos):
        Pt = P_full.iloc[:end_pos + 1]
        Xt, _ = C.features(Pt, "W")
        ddt = H.ath_drawdown(a.data, Xt.index)
        return readiness_rule(ddt, Xt["m2_yoy"]).values

    def fixed5_at(end_pos):
        Pt = P_full.iloc[:end_pos + 1]
        Xt, _ = C.features(Pt, "W")
        Xt["btc_dd_ath"] = H.ath_drawdown(a.data, Xt.index)
        return frozen_predict(models[(HEADLINE_WINDOW, "fixed5", "fall5_26w")], Xt).values
    tr_gate = C.truncation_test(gate_at, len(P_full), n=20, rng=rng)
    tr_f5 = C.truncation_test(fixed5_at, len(P_full), n=20, rng=rng)
    train_mask = (X.index >= TRAIN_FROM) & (X.index <= last_complete)
    first_train_label = X.index[train_mask & Y["fall5_26w"].notna()]
    label_horizon_ok = bool((first_train_label[-1] + pd.Timedelta(weeks=LAG_WEEKS)) <= last_complete)
    purged_first = pd.Timestamp(models[("purged", "fixed5", "fall5_26w")]["trainFrom"])
    purge_ok = bool(purged_first + pd.Timedelta(weeks=1) > rev_last + pd.Timedelta(weeks=LAG_WEEKS))      # the first purged training label window (t+1w..t+26w) starts after the last evaluation label window ends
    leak = {"truncationGate": tr_gate, "truncationFixed5Frozen": tr_f5, "trainLabelsEnd": str(first_train_label[-1].date()), "lastCompleteSunday": str(last_complete.date()),
            "labelsWithheld26w": label_horizon_ok, "reverseEraRowsInTraining": int((train_mask & rev_mask).sum()), "provisionalBarsInLabels": int(Y.loc[provisional].notna().any(axis=1).sum()) if len(provisional) else 0,
            "purgedWindowFirstRow": str(purged_first.date()), "purgedLabelWindowsDisjointFromEvaluationLabelWindows": purge_ok,
            "planWindowTrainRowsSharingLabelPathWithEvaluation": int(((X.index >= TRAIN_FROM) & (X.index < purged_first)).sum()),
            "lastRefitFixed5EqualsHarnessToday": bool(abs(p_today - harness_today) < 1e-9), "m2LongEqualsHarness": bool(chk < 1e-9),
            "dxyUs10yEveningStamp": "DXY / US10Y daily bars are stamped 21-23 UTC the evening before the session, so the shared loader dates a Monday session to Sunday and the W-SUN panel folds it into the prior week (a one-day look-ahead in dxy_* / us10y_* features); no model in this module uses those columns"}
    say(f"leakage: truncation gate ok {tr_gate['ok']} ({tr_gate['tested']} pts, max {tr_gate['maxAbsDiff']:.1e}), frozen fixed5 ok {tr_f5['ok']} ({tr_f5['tested']} pts, max {tr_f5['maxAbsDiff']:.1e}); training labels end {leak['trainLabelsEnd']} (26 w before {last_complete.date()}: {label_horizon_ok}); "
        f"2016-18 rows in training {leak['reverseEraRowsInTraining']}; plan-window training rows sharing a label path with evaluation rows {leak['planWindowTrainRowsSharingLabelPathWithEvaluation']} (purged window from {leak['purgedWindowFirstRow']}: disjoint {purge_ok}); "
        f"provisional bars with a label {leak['provisionalBarsInLabels']}; last-refit fixed5 == harness today {leak['lastRefitFixed5EqualsHarnessToday']}; DXY/US10Y evening stamp noted (unused here)")
    if not (tr_gate["ok"] and tr_f5["ok"] and label_horizon_ok and leak["reverseEraRowsInTraining"] == 0 and leak["provisionalBarsInLabels"] == 0 and purge_ok):
        notes.append("LEAKAGE CHECK FAILED: see leakage block.")

    # ======================================================================================= results
    notes += [
        "Question A fits each model ONCE on 2019+ rows (training rows end 26 weeks before the last complete Sunday) and scores it frozen on 2016-06..2018-12; the shifted-target and dwell-time permutation nulls permute the 2016-18 labels after the fit (no refit: the models never see a 2016-18 label).",
        f"PLAN AMENDMENT (no criterion change): the plan's literal window (train from {TRAIN_FROM.date()}) has no purge gap: its first 26 training rows (2019-H1, every fall5 label 0) are labelled by the same Jan-Jun 2019 BTC.D path that labels the Jul-Dec 2018 evaluation rows. "
        f"The headline is the purged window (train from {purged_first.date()}, the last evaluation row + 27 weeks, as the forward harness's label lag), the plan window is reported beside it with a jackknife of every 26-week training block; the pre-registered criterion is evaluated on both.",
        "The shifted-target null is enumerated exactly over every admissible shift (>= 26 weeks, 83 of them on 135 rows) instead of 200 random draws of those 83 values, so its p is exact and quotable at any --nulls; the permutation null is enumerated exactly when its arrangement count is <= max(nulls, 120) (fall10: 3 blocks, 6 arrangements, so p >= 1/6 by construction), else drawn at random.",
        "Decoys with no market information (the 2016-17 vs 2018 sub-era indicator and a descending time trend) are scored by the same nulls: a model whose AUC does not exceed the sub-era decoy's on the same rows passes the shifted null through the level between the two sub-eras, not through a within-cycle ranking; the era-stratified (within-sub-era) AUC, the within-2018 AUC and the permutation p are printed beside the criterion for that reading.",
        "fall10_26w has ONE positive episode in the reversed era (2016-10-02..2017-12-24 on all rows; 2017-06-18..2017-12-24 on fixed5's rows): its reverse AUC is the ranking of one waterfall against the rest and episode leave-one-out is undefined; it is reported as one event, not identifiable.",
        "fixed5 and M2+ETH/BTC cannot read 2016-06..2017-06 (ethbtc_fromhi52w needs 52 weeks of ETH/BTC, first finite 2017-06-18): their reversed-era rows start 2017-06-18, so the Nov 2016 waterfall is scored only by M2-only and the readiness rule; 'common' rows are the rows every model can read (= fixed5's rows). The 2016-17 sub-era on those rows has every label 1, so their 2016-17 AUC is undefined and the era-stratified AUC reduces to 2018.",
        "SELECTION: the reversed era is out of sample for the fitted coefficients only. The readiness rule's thresholds were read off what preceded the three big waterfalls (two of them in 2016-18, ROUND8_BRIEF item 3) and fixed5's five inputs are round 7's most-picked signals from a selection run on windows starting 2016-06-01 (ROUND8_BRIEF item 6); M2-only is the only comparator whose variable choice is blind to 2016-18.",
        "The readiness rule has no fitted object; it is scored as a 0/1 score (AUC of a binary rule). readiness_harnessATH anchors the ATH at 2014-04 (the shared loader) and is shown because the anchor decides whether the rule fired at Nov 2016 (true anchor: BTC 26% under its Dec 2013 high, so the rule did not fire before the Nov 2016 waterfall).",
        "BTC.D 2016-18 is TradingView's back-computed series; its fall5_26w base rate (58%) is far above 2019+ (26%), so Brier against the 2019+ base rate penalises every model for the level, and AUC is the ranking statistic. The 2019+-fitted scaler clips a share of the reversed-era rows at +/-3 sd (printed per model).",
        "Forward numbers are the standard harness (expanding window from 2016-06, refit 13 weeks, label lag 26) on the rows every model can forecast; their shifted-target nulls are in out8/baselines.",
        "Question B fits nothing beyond fixed5's last walk-forward refit (asserted equal to the harness series today) and the readiness gate. The gate-lead Kaplan-Meier is given under the plan's outcome (lead to the next 5+ point fall PEAK) and under 'BTC.D 5+ points under the switch-on level', over all spells and over the spells that switch on outside an ongoing fall, and over merged spells; every reading rests on at most five independent run-ups.",
        "The decision-table 'in-support spread' is read from out8/forecast or out8/honest when present, else the plan's 3.9%..35% hand-set spread, labelled handSetFallback in the table so it cannot be quoted as a computed clearance; the table is a report, not a success criterion.",
        "Paired bootstrap bands whose slice holds fewer than two 26-week blocks (the fresh-start slice, 22 rows) use a shortened block (N // 4) and say so, instead of printing a rotation of the whole set as an interval.",
        leak["dxyUs10yEveningStamp"] + " (a later round should floor evening-stamped bars to the next calendar day before normalize(); study8_common.py is frozen this round).",
        f"Printed {_LINES[0]} lines, dropped {_LINES[1]}; runtime {time.time() - t0:.1f}s."]
    if a.fast or n_null < MIN_DRAWS:
        notes.append(f"SMOKE: {n_null} random null draws (< {MIN_DRAWS}): the random (fall5 permutation) null prints NO VERDICT; the exact (enumerated) shifted-target null that carries the pre-registered criterion is quotable at any size.")
    hw = HEADLINE_WINDOW
    series = {"reverse_fixed5_fall5_26w": C.thin(preds_all[hw]["fall5_26w"]["fixed5"][rev_mask], every=2), "reverse_m2only_fall5_26w": C.thin(preds_all[hw]["fall5_26w"]["m2only"][rev_mask], every=2),
              "reverse_fixed5_fall5_26w_planWindow": C.thin(preds_all["plan"]["fall5_26w"]["fixed5"][rev_mask], every=2),
              "reverse_readiness": C.thin(preds_all[hw]["fall5_26w"]["readiness"][rev_mask], every=2), "forward_fixed5_fall5_26w": C.thin(fwd_preds["fall5_26w"]["fixed5"], every=2),
              "gateLeadKM_S": km_plan["S"], "gateLeadKM_S_fivePointsUnderLevel": km_lvl["S"]}
    today = {"asOf": str(last_complete.date()), "dataLastBar": {"utc": stamp(last_bar).split(" / ")[1], "et": stamp(last_bar).split(" / ")[0]}, "provisionalBars": [str(d.date()) for d in provisional],
             "fixed5": rnd(p_today), "forwardReadings": {name: A["forward"]["fall5_26w"][name]["today"] for name in fwd_preds["fall5_26w"]}, "readinessGate": Bq["gateLead"]["today"],
             "oneInputAtPeak": one["peaks"], "falsifiers": {k: (v.get("status") if isinstance(v, dict) else v) for k, v in falsifiers.items()}, "decision": Bq["decision"]}
    res = {"module": "study9_checks", "fast": bool(a.fast), "nulls": n_null, "boots": n_boot, "runtimeSec": round(time.time() - t0, 1),
           "oos": {"reverse": A["oos"], "reverseHeadlineWindow": hw, "forward": {tg: {k: v for k, v in A["forward"][tg].items() if k != "paired"} for tg in TARGETS}},
           "null": A["null"], "today": today, "series": series, "notes": notes,
           "questionA": {"design": A["design"], "models": A["models"], "decoys": A["decoys"], "jackknife": A["jackknife"], "paired_reverse": A["paired"], "paired_forward": {tg: A["forward"][tg]["paired"] for tg in TARGETS}, "peaks": A["peaks"], "success": A["success"]},
           "questionB": Bq, "leakage": leak}
    C.write_results(a.out, res)
    say(f"wrote {os.path.join(a.out, 'results.json')}; runtime {time.time() - t0:.1f}s; headline window {hw}: {A['success']['headline']} (plan window {A['success']['plan']['headline']}); "
        f"{'random perm null NO VERDICT (smoke: ' + str(n_null) + ' draws); shifted null exact' if n_null < MIN_DRAWS else 'random nulls quotable (' + str(n_null) + ' draws); shifted null exact'}")


if __name__ == "__main__":
    main()
