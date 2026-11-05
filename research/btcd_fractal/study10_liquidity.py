#!/usr/bin/env python3
"""Round 10 module [2] liquidity: is US M2 the right liquidity input (ROUND10_PLAN.md section [2]).

Question. M2 y/y carries most of the five-signal skill (fixed5 = study8_baselines.SIGNALS) and moves once per cycle. Is it
standing in for broader liquidity, and does a broader or faster measure read differently today?

Candidates (fixed before the run; none added after; each in three forms: SWAP = in place of m2_yoy in fixed5, ADD = beside
it, ALONE = the candidate by itself):
  L1 gm2_yoy          log change over 52 weeks of US M2 + EU M2 x EURUSD + CN M2 / USDCNY + JP M2 / USDJPY (+ GB M2 x GBPUSD
                      when present), every M2 lagged 6 weeks for publication (study8_common.M2_LAG_DAYS); needs at least 3
                      non-US components with their FX on disk, else "not available".
  L2 fedbs_yoy        52-week log change of the Fed balance sheet (FEDBS, 7-day lag); netliq_52w / netliq_13w = the 52- and
                      13-week log changes of net liquidity = FEDBS - RRP - TGA (all three with a 7-day lag), when RRP and TGA
                      are on disk.
  L3 stable_13w/_26w  13- and 26-week log changes of the stablecoin float (USDT.D + USDC.D) / 100 x TOTAL in USD, no lag;
                      needs USDC.D (STABLES, when on disk, is reported beside it and used only if it is long enough).
  L4 m2_yoy_lag13/26  US M2 y/y lagged a further 13 and 26 weeks (if older liquidity information scores as well, the
                      publication lag is not binding; if better, the cycle reads slower than we use it).
  placebo             US M2 y/y with its calendar shifted back by 52 weeks (one cycle; a forward shift would read the future),
                      through the identical procedure as the real m2_yoy swap: it must NOT score as well as the real one.

Design. The round-9 paired protocol by import from study9_candidates (run_spec, score, paired_all, loo_diff, era_context,
criteria, perm_positions, chunks, say, fmt) and study8_honest / study8_tda_sig / study8_common underneath: weekly panel,
expanding window, refit 13 weeks, labels withheld 26 weeks, min_train 60. Common rows per comparison: every model in a
candidate's comparison (its SWAP, ADD, ALONE and fixed5) is scored on exactly the rows where all of them forecast; a
candidate whose history starts late (L3: USDC.D exists from 2018-12) shortens its rows and fixed5 is re-scored on the same
rows (the same expanding-window fixed5, not refit), with the first forecast date printed; beside it, as diagnostics that change
no verdict word: a same-history fixed5 refit on the late starter's own rows, the round-9 single-common-set reading on the
global common rows (all candidates together), the SWAP increment's band with the LOO-max episode removed (a 'worse' that is a
tie without one episode is said so), and an ADD reading word (small everywhere / era- or episode-carried / loses). Paired 26-week block and episode bootstraps against fixed5 pooled, by era, era-stratified and on
fresh-start rows; Brier vs the training-window base rate; within-era dwell-time permutations (model and increment nulls);
shifted-target draws through the whole procedure; the sign of each candidate at every refit; Spearman of each candidate with
m2_yoy on its common rows (|rho| > 0.8 = the same information re-labelled, said in the summary).

Success (pre-registered, evaluated as written). ADD: the round-9 four criteria ((i) paired gain >= +0.03 with q05 > 0,
(ii) no era below -0.02, (iii) fresh-start gain >= 0, (iv) within-era permutation p < 0.05 in >= 2 eras on the increment's
own null). SWAP: "better" only if paired >= +0.03 with q05 > 0 and no era below -0.02; "equivalent" if the band contains 0
and |diff| < 0.03; else "worse". A candidate that is better in SWAP form replaces M2 in the forecast object only after the
owner reads it. A candidate whose series is absent on disk is "not available", never imputed.

  python3 research/btcd_fractal/study10_liquidity.py --data research/btcd_fractal/data --out research/btcd_fractal/out10/liquidity [--nulls N] [--fast]

Point in time. Every monthly series (M2 by the shared loader; CNM2, EUM2, JPM2, GBM2 here) carries the 6-week publication lag
before any feature and its last published value forward (no interpolation); the weekly Fed series carry a 7-day lag; FX bars
are dated at their close (TradingView forex daily bars open at 21:00/22:00 UTC, so the bar is stamped the next calendar day)
and the conversion at row t uses closes <= t; daily market series carry no lag; rows after the panel's last day are dropped
before the forward fill, so a truncated panel never sees a later publication. Every fitted object (z-scores, logistic weights,
training base rate) is fitted on the training window of its refit only; labels enter training 26 weeks after their row; the
partial current week is excluded from the panel altogether (no feature, no label, no reading). Nulls, bootstraps and the LOO
run after all predictions are frozen and feed no fit. The truncation test rebuilds the whole pipeline (series loading
included) on the daily panel cut at 20 random Sundays and asserts features and predictions are unchanged. No network;
aggregates only; the module runs with any subset of the optional series on disk.
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
import study8_honest as H  # noqa: E402  (ath_drawdown, perm_blocks, apply_order, n_arrangements, psum, pfmt, era_mask, paired_block_boot, run_const)
import study8_tda_sig as T  # noqa: E402  (paired_boot)
import study9_candidates as S9  # noqa: E402  (the round-9 paired protocol: run_spec, score, paired_all, loo_diff, era_context, criteria, perm_positions, chunks, say, fmt, point_diff)

# ------------------------------------------------------------------------------------------- pre-registered constants
TARGET = S9.TARGET                           # fall5_26w
SIDE_TARGETS = S9.SIDE_TARGETS               # fall10_26w (binary), y13 (continuous)
DATA_CUT = S9.DATA_CUT                       # 2016-06-01 panel start
EVAL_FROM = S9.EVAL_FROM                     # 2019-01-01
RUNUP = S9.RUNUP                             # 26
MIN_DRAWS = H.MIN_DRAWS_FOR_P                # 50
ENUM_UP_TO = H.ENUMERATE_UP_TO               # 120
CRIT_GAIN, CRIT_ERA_DROP, CRIT_P = S9.CRIT_GAIN, S9.CRIT_ERA_DROP, S9.CRIT_P   # +0.03, -0.02, 0.05
RHO_SAME = 0.8                               # |Spearman with m2_yoy| above this = the same information re-labelled
ERA_NAMES = [e[0] for e in C.ERAS]
POOLED_ERA = S9.POOLED_ERA
FED_LAG_DAYS = 7
MIN_NONUS = 3
PLACEBO_SHIFT_W = 52
L4_LAGS = (13, 26)
# optional series: name -> (publication lag in days, stamp the bar at its close, monthly: stamp moved to the reference month's end)
EXTRA_SPEC = {"CNM2": (C.M2_LAG_DAYS, False, True), "EUM2": (C.M2_LAG_DAYS, False, True), "JPM2": (C.M2_LAG_DAYS, False, True), "GBM2": (C.M2_LAG_DAYS, False, True),
              "USDCNY": (0, True, False), "EURUSD": (0, True, False), "USDJPY": (0, True, False), "GBPUSD": (0, True, False),
              "FEDBS": (FED_LAG_DAYS, False, False), "RRP": (FED_LAG_DAYS, False, False), "TGA": (FED_LAG_DAYS, False, False),
              "USDC.D": (0, False, False), "STABLES": (0, False, False)}
OPTIONAL_SERIES = list(EXTRA_SPEC)
FX_OF = {"EUM2": ("EURUSD", "mul"), "CNM2": ("USDCNY", "div"), "JPM2": ("USDJPY", "div"), "GBM2": ("GBPUSD", "mul")}   # M2 -> (FX, how to put it in USD)
CANDS = ["gm2_yoy", "fedbs_yoy", "netliq_52w", "netliq_13w", "stable_13w", "stable_26w", "m2_yoy_lag13", "m2_yoy_lag26", "m2_yoy_placebo52"]
GROUP = {"gm2_yoy": "L1", "fedbs_yoy": "L2", "netliq_52w": "L2", "netliq_13w": "L2", "stable_13w": "L3", "stable_26w": "L3",
         "m2_yoy_lag13": "L4", "m2_yoy_lag26": "L4", "m2_yoy_placebo52": "placebo"}
FORMS = ("swap", "add", "alone")
NOT_M2 = [s for s in SIGNALS if s != "m2_yoy"]
say, fmt = S9.say, S9.fmt
chunks = S9.chunks
_G = {}


def spec_name(cand, form):
    return f"{cand}:{form}"


def spec_cols(cand, form):
    return {"swap": NOT_M2 + [cand], "add": SIGNALS + [cand], "alone": [cand]}[form]


# ------------------------------------------------------------------------------------------- optional series
def month_end_info(ts):
    """How a monthly series is stamped: the share of raw stamps on the reference month's last day. The publication lag is
    right only when the stamp is the month END (TradingView ECONOMICS stamps it so); a period-START stamp (FRED style) plus
    42 days would precede the real release, so monthly stamps are moved to the month end before the lag (never earlier)."""
    n = pd.DatetimeIndex(ts).normalize()
    me = n + pd.offsets.MonthEnd(0)
    return {"monthEndShareRaw": round(float((n == me).mean()), 3) if len(n) else None, "rowsMovedToMonthEnd": int((n != me).sum()),
            "lastRawStamp": (str(n[-1].date()) if len(n) else None)}


def read_series(data_dir, name, lag_days=0, stamp_close=False, month_end=False, info=None):
    """One CSV as a daily close series. stamp_close: a bar whose open is not at 00:00 UTC closes on the next calendar day
    (forex daily bars open 21:00/22:00 UTC), so it is dated at its close; otherwise the bar's own day. month_end: a monthly
    series is stamped at its reference month's end (a stamp already there is unchanged; an earlier one moves later, never
    earlier). Then the publication lag is added to every date. None when the file is absent."""
    f = os.path.join(data_dir, f"{name}_1d.csv")
    if not os.path.exists(f):
        return None
    d = pd.read_csv(f)
    ts = pd.to_datetime(d["ts"], unit="ms")
    if stamp_close:
        ts = ts.where(ts.dt.hour == 0, ts + pd.Timedelta(days=1))
    idx = pd.DatetimeIndex(ts).normalize()
    if month_end:
        if info is not None:
            info.update(month_end_info(idx))
        idx = idx + pd.offsets.MonthEnd(0)
    idx = idx + pd.Timedelta(days=int(lag_days))
    s = pd.Series(d["c"].values.astype(float), index=idx)
    return s[~s.index.duplicated(keep="last")].sort_index()


def load_extra(data_dir, index):
    """The optional round-10 series on the daily calendar `index` (the shared loader's), each with its publication lag; rows
    dated after index[-1] are dropped BEFORE the forward fill, so a truncated panel never sees a later publication; the last
    published value is carried forward (no interpolation). Returns (DataFrame, meta)."""
    out, meta = {}, {}
    for n, (lag, close, monthly) in EXTRA_SPEC.items():
        info = {}
        s = read_series(data_dir, n, lag, close, monthly, info)
        if s is None:
            meta[n] = {"onDisk": False}
            continue
        s = s[s.index <= index[-1]]
        meta[n] = {"onDisk": True, "lagDays": int(lag), "stampedAtClose": bool(close), "monthly": bool(monthly), "rows": int(len(s)),
                   "firstAvailable": (str(s.index[0].date()) if len(s) else None), "lastAvailable": (str(s.index[-1].date()) if len(s) else None), **info}
        if len(s):
            out[n] = s.reindex(index.union(s.index)).ffill().reindex(index)
    return pd.DataFrame(out, index=index), meta


def stat_diff(h, lag=0):
    """The candidate statistic of a weekly log level: its h-week log change, shifted back `lag` weeks (0 = none)."""
    def f(lev):
        return lev.diff(h).shift(lag) if lag else lev.diff(h)
    return f


def liquidity_frame(P, meta):
    """The candidate columns on the weekly panel from whatever is on disk, with the log-level series and statistic behind
    each (for the matched-random-walk decoys). Returns (frame, availability, levels, stats)."""
    F = pd.DataFrame(index=P.index)
    avail, levels, stats = {}, {}, {}

    def put(cand, lev, stat, info):
        levels[cand], stats[cand] = lev, stat
        F[cand] = stat(lev).replace([np.inf, -np.inf], np.nan).values
        avail[cand] = {"available": True, **info}
    # L1 global M2 in USD
    comps = [m for m in FX_OF if m in P and FX_OF[m][0] in P]
    missing = [m for m in FX_OF if m not in comps]
    if "M2" in P and len(comps) >= MIN_NONUS:
        g = P["M2"].astype(float).copy()
        for m in comps:
            fx, op = FX_OF[m]
            g = g + (P[m] * P[fx] if op == "mul" else P[m] / P[fx])
        put("gm2_yoy", np.log(g.clip(lower=1e-9)), stat_diff(52), {"components": ["M2"] + comps, "missingComponents": missing, "why": "52-week log change of US M2 + the FX-converted non-US M2s"})
    else:
        avail["gm2_yoy"] = {"available": False, "why": f"needs US M2 and at least {MIN_NONUS} non-US M2 components with their FX; on disk {comps}, missing {missing}"}
    # L2 Fed balance sheet and net liquidity
    if "FEDBS" in P:
        put("fedbs_yoy", np.log(P["FEDBS"].clip(lower=1e-9)), stat_diff(52), {"components": ["FEDBS"], "why": "52-week log change of the Fed balance sheet"})
    else:
        avail["fedbs_yoy"] = {"available": False, "why": "FEDBS not on disk"}
    if all(n in P for n in ("FEDBS", "RRP", "TGA")):
        nl = (P["FEDBS"] - P["RRP"] - P["TGA"]).clip(lower=1e-9)
        for cand, h in (("netliq_52w", 52), ("netliq_13w", 13)):
            put(cand, np.log(nl), stat_diff(h), {"components": ["FEDBS", "RRP", "TGA"], "why": f"{h}-week log change of FEDBS - RRP - TGA"})
    else:
        for cand in ("netliq_52w", "netliq_13w"):
            avail[cand] = {"available": False, "why": "needs FEDBS, RRP and TGA on disk; missing " + str([n for n in ("FEDBS", "RRP", "TGA") if n not in P])}
    # L3 stablecoin float
    if all(n in P for n in ("USDT.D", "USDC.D", "TOTAL")):
        fl = ((P["USDT.D"] + P["USDC.D"]) / 100.0 * P["TOTAL"]).clip(lower=1e-9)
        for cand, h in (("stable_13w", 13), ("stable_26w", 26)):
            put(cand, np.log(fl), stat_diff(h), {"components": ["USDT.D", "USDC.D", "TOTAL"], "why": f"{h}-week log change of (USDT.D + USDC.D) / 100 x TOTAL"})
    else:
        for cand in ("stable_13w", "stable_26w"):
            avail[cand] = {"available": False, "why": "needs USDC.D on disk (USDT.D and TOTAL are in the shared panel)"}
    # L4 lagged US M2 y/y and the placebo
    lm2 = np.log(P["M2"].clip(lower=1e-9))
    for lag in L4_LAGS:
        put(f"m2_yoy_lag{lag}", lm2, stat_diff(52, lag), {"components": ["M2"], "why": f"m2_yoy lagged a further {lag} weeks"})
    put("m2_yoy_placebo52", lm2, stat_diff(52, PLACEBO_SHIFT_W), {"components": ["M2"], "why": f"m2_yoy with its calendar shifted back {PLACEBO_SHIFT_W} weeks (placebo)"})
    return F, avail, levels, stats


def build_all(D, data_dir, last_complete):
    """The whole pipeline from the daily panel (main run and truncation test): the optional series on the same calendar, the
    weekly panel, the harness features with the true-ATH drawdown, the targets, the candidate frame."""
    E, meta = load_extra(data_dir, D.index)
    Dx = pd.concat([D, E], axis=1)
    P_full = C.panel(Dx, "W")
    X_full, _ = C.features(P_full, "W")
    dd_harness = X_full["btc_dd_ath"].copy()
    X_full["btc_dd_ath"] = H.ath_drawdown(data_dir, X_full.index)
    keep = (X_full.index >= pd.Timestamp(DATA_CUT)) & (X_full.index <= last_complete)
    X, P = X_full[keep], P_full[keep]
    Y = C.targets(P, "W")
    Lq, avail, levels, stats = liquidity_frame(P_full, meta)
    F = pd.concat([X[SIGNALS], Lq[keep]], axis=1)
    return X, P, Y, F, dd_harness[keep], avail, meta, {k: v[keep] for k, v in levels.items()}, stats


# ------------------------------------------------------------------------------------------- forked null workers
def _job(args):
    kind = args[0]
    F, Y, masks, specs, null_specs, fams_of = _G["F"], _G["Y"], _G["masks"], _G["specs"], _G["nullSpecs"], _G["famsOf"]
    out = []
    if kind == "shift":
        _, seed, n = args
        rng = np.random.default_rng(seed)
        lo = C.bars(26, "W")
        for _ in range(n):
            k = int(rng.integers(lo, len(Y) - lo))
            Ys = C.shift_targets(Y, k)
            row = {}
            for spec in null_specs:
                p, _ = S9.run_spec(F, Ys, specs[spec])
                for fam in fams_of[spec]:
                    row[f"{spec}|{fam}"] = S9.pooled_auc(p.where(masks[fam]), Ys[TARGET])
            out.append(row)
    elif kind == "perm":
        _, era, orders = args
        pos = S9.perm_positions(Y, era)
        blocks = H.perm_blocks(Y[TARGET].values[pos])
        for order in orders:
            Ys = H.apply_order(Y, pos, blocks, order)
            row = {}
            for spec in null_specs:
                p, _ = S9.run_spec(F, Ys, specs[spec])
                for fam in fams_of[spec]:
                    row[f"{spec}|{fam}"] = S9.era_auc_of(p.where(masks[fam]), Ys[TARGET], era)
            out.append(row)
    elif kind == "dfeat":
        _, cand, seeds = args
        lev, stat = _G["levels"][cand], _G["stats"][cand]
        for seed in seeds:
            rng = np.random.default_rng(seed)
            v = lev.values.astype(float).copy()
            fin = np.isfinite(v)
            v[fin] = C.matched_rw(v[fin], rng)
            feat = stat(pd.Series(v, index=lev.index)).replace([np.inf, -np.inf], np.nan)
            fv = feat.where(masks[cand]).dropna()
            res = {"acf1": (None if fv.shape[0] < 30 or fv.std() == 0 else round(float(fv.autocorr(1)), 3))}
            for form in ("add", "swap"):
                Fd = F[SIGNALS].copy()
                Fd["decoy"] = feat.values
                p, _ = S9.run_spec(Fd, Y, (SIGNALS if form == "add" else NOT_M2) + ["decoy"])
                p = p.where(masks[cand])
                met = C.metrics(p, Y[TARGET], True)
                res[form] = {"pooled": met.get("pooled", {}).get("auc"), "byEra": {e: met.get(e, {}).get("auc") for e in ERA_NAMES}, "n": int(p.notna().sum())}
            out.append(res)
    return out


def run_jobs(pool, jobs):
    return pool.map(_job, jobs) if pool else [_job(j) for j in jobs]


# ------------------------------------------------------------------------------------------- verdicts
def ni(reason):
    return {"status": "not identifiable", "why": reason}


def swap_verdict(pdiff):
    """SWAP as pre-registered: better only if paired >= +0.03 with q05 > 0 and no era below -0.02; equivalent if the band
    contains 0 and |diff| < 0.03; else worse."""
    b = pdiff["block"].get("pooled", {})
    if b.get("n", 0) < MIN_DRAWS or b.get("diff") is None:
        return {**ni("fewer than 50 bootstrap draws or no pooled diff")}
    eras = {e: pdiff["block"].get(e, {}).get("diff") for e in ERA_NAMES}
    head = b["diff"] >= CRIT_GAIN and b["q05"] > 0
    out = {"diff": b["diff"], "q05": b["q05"], "q95": b["q95"], "byEra": eras}
    if head and any(v is None for v in eras.values()):
        return {**out, **ni("the pooled gain clears the bar but an era has fewer than 20 common rows, so the no-era-below rule cannot be read")}
    if head and all(v >= CRIT_ERA_DROP for v in eras.values()):
        out["status"] = "better"
    elif b["q05"] <= 0 <= b["q95"] and abs(b["diff"]) < CRIT_GAIN:
        out["status"] = "equivalent"
    else:
        out["status"] = "worse"
        if b["q05"] <= 0 <= b["q95"]:
            out["note"] = "the band contains 0 but |diff| >= 0.03: worse by the rule as written"
        elif b["diff"] >= CRIT_GAIN:
            out["note"] = "pooled gain >= 0.03 with q05 > 0 but an era is below -0.02: not better by the rule, hence worse as written"
    return out


def loo_keep_mask(pred, y, key, runup=RUNUP):
    """The rows study8_honest.episode_loo_runup keeps when it drops the label episode `key` (its 'start..end' key) with its
    run-up: the same episode finding and the same slice (copied from that function so the band below is on exactly its rows)."""
    p, yy = np.asarray(pred, float), np.asarray(y, float)
    m = np.isfinite(p) & np.isfinite(yy)
    idx = pred.index
    for s, e in C.episodes(np.where(m, yy, np.nan)):
        if f"{idx[s].date()}..{idx[e].date()}" == key:
            keep = m.copy()
            keep[max(0, s - runup):e + 1] = False
            return pd.Series(keep, index=idx)
    return None


def add_reading(pdiff_add, loo_add, dfeat_add):
    """A diagnostic word beside the registered ADD verdict: does the candidate fail only the +0.03 bar (small and
    non-negative everywhere: every era, every episode left out) or is it carried by an era or an episode, or does it lose?"""
    b = pdiff_add["block"].get("pooled", {})
    d = b.get("diff")
    eras = [v for v in (pdiff_add["block"].get(e, {}).get("diff") for e in ERA_NAMES) if v is not None]
    out = {"diff": d, "eraMin": (min(eras) if eras else None), "looMin": loo_add.get("min"), "looMax": loo_add.get("max"),
           "decoyP95": dfeat_add.get("decoyP95"), "decoyQuotable": bool(dfeat_add.get("n", 0) >= MIN_DRAWS)}
    if d is None:
        out["word"] = "not identifiable"
    elif d <= 0:
        out["word"] = "loses (increment at or below 0)"
    elif (out["eraMin"] is not None and out["eraMin"] < CRIT_ERA_DROP) or (out["looMin"] is not None and out["looMin"] < CRIT_ERA_DROP):
        out["word"] = "era- or episode-carried (an era or a left-out episode turns it below -0.02)"
    else:
        out["word"] = "small everywhere: fails only the +0.03 bar (no era, episode or sign breaks it)"
    if out["decoyQuotable"] and d is not None and out["decoyP95"] is not None and d <= out["decoyP95"]:
        out["word"] += "; inside the matched-random-walk decoy band"
    return out


# ------------------------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--nulls", type=int, default=200)
    ap.add_argument("--fast", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--within", type=int, default=300, help="within-era dwell-time permutation draws per era (300 as round 9; enumerated exactly when small)")
    a = ap.parse_args()
    t0 = time.time()
    n_shift, n_within, n_boot, n_dfeat, n_trunc = a.nulls, a.within, 1000, 20, 20
    if a.fast:
        n_shift, n_within, n_boot, n_dfeat = min(a.nulls, 20), min(a.within, 20), 200, 3
        a.workers = min(a.workers, 2)
    rng = np.random.default_rng(102)
    phase = {}

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
    X, P, Y, F, dd_harness, avail, meta, levels, stats = build_all(D, a.data, last_complete)
    fresh = C.fresh_mask(P, "W")
    y = Y[TARGET]
    on_disk = [n for n in OPTIONAL_SERIES if meta[n]["onDisk"]]
    absent = [n for n in OPTIONAL_SERIES if not meta[n]["onDisk"]]
    cands = [c for c in CANDS if avail[c]["available"]]
    unavailable = [c for c in CANDS if not avail[c]["available"]]
    say(f"study10_liquidity  data last bar {last_utc} / {last_et} (daily close {last_bar.date()}); last complete Sunday {last_complete.date()}; provisional bars excluded {provisional}; "
        f"fast={a.fast} shift {n_shift} within-era {n_within}/era boots {n_boot} decoy-features {n_dfeat} workers {a.workers}; optional series on disk {len(on_disk)}/{len(OPTIONAL_SERIES)}"
        + (f", absent {absent}" if absent else ""))
    say("candidates: " + "; ".join(f"{c} ({GROUP[c]}) " + ("available, first finite " + str(F[c].first_valid_index().date()) + ", from " + "+".join(avail[c]["components"])
                                                           if avail[c]["available"] else "NOT AVAILABLE: " + avail[c]["why"]) for c in CANDS)
        + "; lags: monthly M2s " + str(C.M2_LAG_DAYS) + " d, Fed series " + str(FED_LAG_DAYS) + " d, FX dated at the bar's close, market series none"
        + (f"; STABLES on disk from {meta['STABLES']['firstAvailable']} ({meta['STABLES']['rows']} rows): too short for a walk-forward, reported in the today block only" if meta["STABLES"]["onDisk"] else ""))

    # ---- predictions (frozen before any null / bootstrap), per-candidate common rows, the training-window base rate
    SPECS = {"fixed5": SIGNALS, "m2only": ["m2_yoy"]}
    for c in cands:
        for form in FORMS:
            SPECS[spec_name(c, form)] = spec_cols(c, form)
    preds, models, refits = {}, {}, {}
    for spec, cols in SPECS.items():
        models[spec] = []
        preds[spec], refits[spec] = S9.run_spec(F, Y, cols, keep_models=models[spec])
    base = H.run_const(X, Y, TARGET)
    base_mask = base.notna() & (F.index >= pd.Timestamp(EVAL_FROM)) & preds["fixed5"].notna() & preds["m2only"].notna()
    masks = {}
    for c in cands:
        m = base_mask.copy()
        for form in FORMS:
            m &= preds[spec_name(c, form)].notna()
        masks[c] = m
    gmask = base_mask.copy()
    for c in cands:
        gmask &= masks[c]
    masks["_fixed5"] = base_mask.copy()
    masks["_global"] = gmask
    rows = {}
    for key, m in masks.items():
        lab = m & y.notna()
        rows[key] = {"firstForecast": (str(m[m].index[0].date()) if m.any() else None), "n": int(m.sum()), "labelled": int(lab.sum()), "positives": int(y[lab].sum()),
                     "episodes": len(C.episodes(np.where(lab, y, np.nan))), "byEra": {e[0]: int((lab & H.era_mask(lab.index, e)).sum()) for e in C.ERAS}}
    late = [c for c in cands if rows[c]["firstForecast"] != rows["_fixed5"]["firstForecast"]]
    say(f"rows: fixed5 alone forecasts from {rows['_fixed5']['firstForecast']} (n {rows['_fixed5']['n']}, positives {rows['_fixed5']['positives']} in {rows['_fixed5']['episodes']} episodes); "
        + (("late starters shorten their own comparison and fixed5 is re-scored on the same rows (a same-history fixed5 refit on the candidate's rows is reported beside it): " + "; ".join(f"{c} from {rows[c]['firstForecast']} (n {rows[c]['n']}, positives {rows[c]['positives']}, episodes {rows[c]['episodes']}, by era {list(rows[c]['byEra'].values())})" for c in late)) if late else "every candidate forecasts from the same first date")
        + f"; global common rows (all candidates) from {rows['_global']['firstForecast']} n {rows['_global']['n']} positives {rows['_global']['positives']} episodes {rows['_global']['episodes']}")
    phase["predictionsSec"] = round(time.time() - t0, 1)

    # ---- scores on each candidate's rows (its three forms and fixed5), paired differences against fixed5, Spearman, signs
    oos, pdiff, rho, signs = {}, {}, {}, {}
    ref = {}
    for key in ("_fixed5", "_global"):
        m = masks[key]
        ref[key] = {s: S9.score(preds[s].where(m), y, base.where(m), fresh) for s in ("fixed5", "m2only")}
        ref[key]["m2only_vs_fixed5"] = S9.paired_all(preds["m2only"].where(m), preds["fixed5"].where(m), y, fresh, n_boot, rng)
    r5, rm = ref["_fixed5"]["fixed5"], ref["_fixed5"]["m2only"]
    d5 = ref["_fixed5"]["m2only_vs_fixed5"]
    say(f"reference on fixed5's rows: fixed5 auc pooled {fmt(r5['byEra']['pooled']['auc'])} eras {' '.join(fmt(r5['byEra'].get(e, {}).get('auc')) for e in ERA_NAMES)} strat {fmt(r5['eraStratAuc'])} fresh {fmt(r5['fresh'].get('pooled'))} "
        f"brier skill vs train-base {' '.join(fmt(r5['byEra'].get(e, {}).get('skillVsTrainBase'), 2) for e in ERA_NAMES + ['pooled'])} | m2only auc pooled {fmt(rm['byEra']['pooled']['auc'])} eras {' '.join(fmt(rm['byEra'].get(e, {}).get('auc')) for e in ERA_NAMES)} "
        f"strat {fmt(rm['eraStratAuc'])} fresh {fmt(rm['fresh'].get('pooled'))} vs fixed5 {fmt(d5['block']['pooled'].get('diff'))} block[{fmt(d5['block']['pooled'].get('q05'))},{fmt(d5['block']['pooled'].get('q95'))}]")
    for c in cands:
        m = masks[c]
        oos[c] = {"fixed5": S9.score(preds["fixed5"].where(m), y, base.where(m), fresh), "m2only": S9.score(preds["m2only"].where(m), y, base.where(m), fresh)}
        pdiff[c] = {}
        for form in FORMS:
            s = spec_name(c, form)
            oos[c][form] = S9.score(preds[s].where(m), y, base.where(m), fresh)
            pdiff[c][form] = S9.paired_all(preds[s].where(m), preds["fixed5"].where(m), y, fresh, n_boot, rng)
        pdiff[c]["alone_vs_m2only"] = S9.paired_all(preds[spec_name(c, "alone")].where(m), preds["m2only"].where(m), y, fresh, n_boot, rng)
        rho[c] = {"spearmanVsM2yoy": C.spearman(F[c].where(m).values, F["m2_yoy"].where(m).values), "acf1": round(float(F[c].where(m).dropna().autocorr(1)), 3)}
        rho[c]["sameInformation"] = bool(abs(rho[c]["spearmanVsM2yoy"]) > RHO_SAME)
        signs[c] = {}
        for form in ("swap", "add"):
            s = spec_name(c, form)
            j = 1 + SPECS[s].index(c)
            sg = [int(np.sign(w[j])) for (_, _, w) in models[s]]
            signs[c][form] = {"signAtRefits": "".join("+" if v > 0 else ("-" if v < 0 else "0") for v in sg), "nPositive": int(sum(v > 0 for v in sg)), "nNegative": int(sum(v < 0 for v in sg)),
                              "nRefits": len(sg), "coefLast": (round(float(models[s][-1][2][j]), 3) if models[s] else None), "refitDates": [r["t"] for r in refits[s]]}
            if form == "add":
                jm = 1 + SPECS[s].index("m2_yoy")
                signs[c][form]["m2CoefLast"] = (round(float(models[s][-1][2][jm]), 3) if models[s] else None)

    def dline(d):
        b, e, st, fr = d["block"]["pooled"], d["episode"]["pooled"], d["strat"], d["fresh"]["pooled"]
        return (f"{fmt(b.get('diff'))} block[{fmt(b.get('q05'))},{fmt(b.get('q95'))}] ep[{fmt(e.get('q05'))},{fmt(e.get('q95'))}] strat {fmt(st.get('diff'))}[{fmt(st.get('q05'))},{fmt(st.get('q95'))}] "
                f"fresh {fmt(fr.get('diff'))}[{fmt(fr.get('q05'))},{fmt(fr.get('q95'))}] eras {' '.join(fmt(d['block'].get(e, {}).get('diff')) for e in ERA_NAMES)}")
    for c in cands:
        f5 = oos[c]["fixed5"]["byEra"]
        parts = [f"{c:16s} rows from {rows[c]['firstForecast']} n{rows[c]['n']} | fixed5 here {fmt(f5['pooled']['auc'])} ({' '.join(fmt(f5.get(e, {}).get('auc')) for e in ERA_NAMES)})"]
        for form in ("swap", "add"):
            r = oos[c][form]["byEra"]
            parts.append(f"{form.upper()} {fmt(r['pooled']['auc'])} ({' '.join(fmt(r.get(e, {}).get('auc')) for e in ERA_NAMES)}) strat {fmt(oos[c][form]['eraStratAuc'])} brier-skill {fmt(r['pooled'].get('skillVsTrainBase'), 2)} vs fixed5 {dline(pdiff[c][form])} sign {signs[c][form]['nPositive']}+/{signs[c][form]['nNegative']}-")
        ra = oos[c]["alone"]["byEra"]
        da = pdiff[c]["alone_vs_m2only"]["block"]["pooled"]
        parts.append(f"ALONE {fmt(ra['pooled']['auc'])} ({' '.join(fmt(ra.get(e, {}).get('auc')) for e in ERA_NAMES)}) vs m2only {fmt(da.get('diff'))}[{fmt(da.get('q05'))},{fmt(da.get('q95'))}] | rho vs m2_yoy {rho[c]['spearmanVsM2yoy']:+.2f}{' SAME INFO' if rho[c]['sameInformation'] else ''} acf1 {rho[c]['acf1']}")
        say(" | ".join(parts))
    gm = masks["_global"]
    gtab = {s: C.metrics(preds[s].where(gm), y, True).get("pooled", {}).get("auc") for s in SPECS}
    say(f"global common rows (from {rows['_global']['firstForecast']}, n {rows['_global']['n']}) pooled auc: fixed5 {fmt(gtab['fixed5'])} m2only {fmt(gtab['m2only'])} | " + " ".join(f"{c} swap/add/alone {fmt(gtab[spec_name(c, 'swap')])}/{fmt(gtab[spec_name(c, 'add')])}/{fmt(gtab[spec_name(c, 'alone')])}" for c in cands))
    # the round-9 single-common-set reading of the plan's sentence, as a diagnostic beside the registered per-candidate rows:
    # every candidate's SWAP and ADD against fixed5 on the global rows (block band pooled and by era, fresh point diff, the SWAP word)
    gdiag = {}
    for c in cands:
        gdiag[c] = {}
        for form in ("swap", "add"):
            bb = H.paired_block_boot(preds[spec_name(c, form)].where(gm), preds["fixed5"].where(gm), y, n_boot, rng)
            d = {"block": bb, "fresh": S9.point_diff(preds[spec_name(c, form)].where(gm & fresh), preds["fixed5"].where(gm & fresh), y)}
            if form == "swap":
                d["status"] = swap_verdict({"block": bb})["status"]
            else:
                b = bb.get("pooled", {})
                eras_g = [bb.get(e, {}).get("diff") for e in ERA_NAMES]
                d["i"] = ("pass" if (b.get("diff") is not None and b["diff"] >= CRIT_GAIN and b["q05"] > 0) else "fail") if b.get("n", 0) >= MIN_DRAWS else "not identifiable"
                d["ii"] = "not identifiable" if any(v is None for v in eras_g) else ("pass" if all(v >= CRIT_ERA_DROP for v in eras_g) else "fail")
                d["iii"] = "not identifiable" if d["fresh"] is None else ("pass" if d["fresh"] >= 0 else "fail")
            gdiag[c][form] = d
    say(f"global common rows, round-9 single-set reading (diagnostic, not the criterion; every candidate loses its 2019-20 rows here): " + "; ".join(
        f"{c} ADD {fmt(gdiag[c]['add']['block']['pooled'].get('diff'))} [{fmt(gdiag[c]['add']['block']['pooled'].get('q05'))},{fmt(gdiag[c]['add']['block']['pooled'].get('q95'))}] (i/ii/iii {gdiag[c]['add']['i'][0]}/{gdiag[c]['add']['ii'][0]}/{gdiag[c]['add']['iii'][0]}) "
        f"SWAP {fmt(gdiag[c]['swap']['block']['pooled'].get('diff'))} [{fmt(gdiag[c]['swap']['block']['pooled'].get('q05'))},{fmt(gdiag[c]['swap']['block']['pooled'].get('q95'))}] {gdiag[c]['swap']['status']}" for c in cands))
    # a late starter's registered reference is fixed5 RE-SCORED on its rows (fitted on the full history); beside it, fixed5 refit on
    # the candidate's own trainable rows (its five features blanked where the candidate is NaN), so the training-window handicap is visible
    samehist = {}
    for c in late:
        F5 = F[SIGNALS].where(F[c].notna())
        p5, _ = S9.run_spec(F5, Y, SIGNALS)
        m = masks[c]
        sh = {"firstForecast": (str(p5[p5.notna()].index[0].date()) if p5.notna().any() else None), "fixed5SameHistory": S9.score(p5.where(m), y, base.where(m), fresh),
              "handicap": {"pooled": None, "byEra": {}}, "vsFixed5SameHistory": {}}
        for form in FORMS:
            sh["vsFixed5SameHistory"][form] = S9.paired_all(preds[spec_name(c, form)].where(m), p5.where(m), y, fresh, n_boot, rng)
        sh["fullHistoryVsSameHistory"] = H.paired_block_boot(preds["fixed5"].where(m), p5.where(m), y, n_boot, rng)
        sh["swapStatusVsSameHistory"] = swap_verdict(sh["vsFixed5SameHistory"]["swap"])["status"]
        ac = sh["vsFixed5SameHistory"]["add"]["block"]["pooled"]
        sh["addIvsSameHistory"] = ("pass" if (ac.get("diff") is not None and ac["diff"] >= CRIT_GAIN and ac["q05"] > 0) else "fail") if ac.get("n", 0) >= MIN_DRAWS else "not identifiable"
        samehist[c] = sh
    if samehist:
        say("late starters vs a same-history fixed5 (fixed5 refit on the candidate's rows; diagnostic beside the registered re-scored fixed5): " + "; ".join(
            f"{c} same-history fixed5 {fmt(v['fixed5SameHistory']['byEra']['pooled']['auc'])} ({' '.join(fmt(v['fixed5SameHistory']['byEra'].get(e, {}).get('auc')) for e in ERA_NAMES)}) vs full-history {fmt(oos[c]['fixed5']['byEra']['pooled']['auc'])} "
            f"(handicap {fmt(v['fullHistoryVsSameHistory']['pooled'].get('diff'))} [{fmt(v['fullHistoryVsSameHistory']['pooled'].get('q05'))},{fmt(v['fullHistoryVsSameHistory']['pooled'].get('q95'))}]); "
            f"ADD {fmt(v['vsFixed5SameHistory']['add']['block']['pooled'].get('diff'))} [{fmt(v['vsFixed5SameHistory']['add']['block']['pooled'].get('q05'))},{fmt(v['vsFixed5SameHistory']['add']['block']['pooled'].get('q95'))}] (i {v['addIvsSameHistory']}) "
            f"SWAP {fmt(v['vsFixed5SameHistory']['swap']['block']['pooled'].get('diff'))} [{fmt(v['vsFixed5SameHistory']['swap']['block']['pooled'].get('q05'))},{fmt(v['vsFixed5SameHistory']['swap']['block']['pooled'].get('q95'))}] -> {v['swapStatusVsSameHistory']}" for c, v in samehist.items()))
    phase["bootstrapsSec"] = round(time.time() - t0 - phase["predictionsSec"], 1)

    # ---- nulls and decoys through the whole procedure (forked workers; predictions above are already frozen)
    null_specs = ["fixed5"] + [spec_name(c, form) for c in cands for form in ("add", "swap")]
    fams_of = {"fixed5": list(cands)}
    for c in cands:
        for form in ("add", "swap"):
            fams_of[spec_name(c, form)] = [c]
    _G.update({"F": F, "Y": Y, "masks": masks, "specs": SPECS, "nullSpecs": null_specs, "famsOf": fams_of, "levels": levels, "stats": stats})
    ctx = get_context("fork")
    pool = ctx.Pool(a.workers) if a.workers > 1 else None
    try:
        jobs = [("shift", 1000 + i, len(ch)) for i, ch in enumerate(chunks(list(range(n_shift)), a.workers * 2)) if len(ch)]
        shift_raw = [r for part in run_jobs(pool, jobs) for r in part]
        perm_raw, arrangements = {}, {}
        for era in C.ERAS + [POOLED_ERA]:
            pos = S9.perm_positions(Y, era)
            nb = len(H.perm_blocks(Y[TARGET].values[pos]))
            K = H.n_arrangements(nb)
            exact = K <= max(n_within, ENUM_UP_TO)
            orders = [np.array(o) for o in itertools.permutations(range(nb))] if exact else [rng.permutation(nb) for _ in range(n_within)]
            arrangements[era[0]] = {"blocks": nb, "distinctArrangements": (int(K) if nb <= 20 else f"{nb}!"), "enumerated": exact, "draws": len(orders)}
            jobs = [("perm", era, ch) for ch in chunks(orders, a.workers * 2) if len(ch)]
            perm_raw[era[0]] = [r for part in run_jobs(pool, jobs) for r in part]
        dfeat_raw = {}
        for i, c in enumerate(cands):
            seeds = [5000 + 100 * i + k for k in range(n_dfeat)]
            jobs = [("dfeat", c, ch) for ch in chunks(seeds, a.workers * 2) if len(ch)]
            dfeat_raw[c] = [r for part in run_jobs(pool, jobs) for r in part]
    finally:
        if pool:
            pool.close()
            pool.join()
    phase["nullsDecoysSec"] = round(time.time() - t0 - phase["predictionsSec"] - phase["bootstrapsSec"], 1)

    null = {"arrangements": arrangements, "byCandidate": {}}
    for c in cands:
        nc = {"shift": {}, "shiftIncrement": {}, "withinEra": {}, "withinEraIncrement": {}}
        k5 = f"fixed5|{c}"
        nc["shift"]["fixed5"] = H.psum(oos[c]["fixed5"]["byEra"]["pooled"]["auc"], [r[k5] for r in shift_raw if r[k5] is not None])
        for form in ("add", "swap"):
            ks = f"{spec_name(c, form)}|{c}"
            nc["shift"][form] = H.psum(oos[c][form]["byEra"]["pooled"]["auc"], [r[ks] for r in shift_raw if r[ks] is not None])
            nc["shiftIncrement"][form] = H.psum(pdiff[c][form]["block"]["pooled"].get("diff"), [r[ks] - r[k5] for r in shift_raw if r[ks] is not None and r[k5] is not None])
        for spec_key, label in ((k5, "fixed5"), (f"{spec_name(c, 'add')}|{c}", "add"), (f"{spec_name(c, 'swap')}|{c}", "swap")):
            nc["withinEra"][label] = {}
            for era in C.ERAS + [POOLED_ERA]:
                vals = [r[spec_key] for r in perm_raw[era[0]] if r[spec_key] is not None]
                real = oos[c][label]["byEra"].get(era[0], {}).get("auc")
                s = H.psum(real, vals, exact=arrangements[era[0]]["enumerated"])
                s["minAttainableP"] = (round(1.0 / arrangements[era[0]]["distinctArrangements"], 4) if arrangements[era[0]]["enumerated"] else (round(1.0 / len(vals), 4) if vals else None))
                nc["withinEra"][label][era[0]] = s
            if label != "fixed5":
                nc["withinEraIncrement"][label] = {}
                for era in C.ERAS + [POOLED_ERA]:
                    vals = [r[spec_key] - r[k5] for r in perm_raw[era[0]] if r[spec_key] is not None and r[k5] is not None]
                    s = H.psum(pdiff[c][label]["block"].get(era[0], {}).get("diff"), vals, exact=arrangements[era[0]]["enumerated"])
                    s["minAttainableP"] = (round(1.0 / arrangements[era[0]]["distinctArrangements"], 4) if arrangements[era[0]]["enumerated"] else (round(1.0 / len(vals), 4) if vals else None))
                    nc["withinEraIncrement"][label][era[0]] = s
        null["byCandidate"][c] = nc
        wi, wm = nc["withinEraIncrement"], nc["withinEra"]
        say(f"nulls {c:16s}: ADD shift auc {H.pfmt(nc['shift']['add'])} increment {fmt(nc['shiftIncrement']['add'].get('real'))} vs med {fmt(nc['shiftIncrement']['add'].get('nullMedian'))} p95 {fmt(nc['shiftIncrement']['add'].get('nullP95'))} {H.pfmt(nc['shiftIncrement']['add'])}; "
            f"ADD within-era model " + " ".join(f"{e[:4]}{e[-2:]} {fmt(wm['add'][e].get('real'))} {H.pfmt(wm['add'][e])}" for e in ERA_NAMES) + "; ADD within-era INCREMENT " + " ".join(f"{e[:4]}{e[-2:]} {fmt(wi['add'][e].get('real'))} p95 {fmt(wi['add'][e].get('nullP95'))} {H.pfmt(wi['add'][e])}" for e in ERA_NAMES)
            + f" | SWAP shift auc {H.pfmt(nc['shift']['swap'])} increment {fmt(nc['shiftIncrement']['swap'].get('real'))} vs p95 {fmt(nc['shiftIncrement']['swap'].get('nullP95'))} {H.pfmt(nc['shiftIncrement']['swap'])}; SWAP within-era model "
            + " ".join(f"{e[:4]}{e[-2:]} {fmt(wm['swap'][e].get('real'))} {H.pfmt(wm['swap'][e])}" for e in ERA_NAMES) + "; SWAP within-era INCREMENT " + " ".join(f"{e[:4]}{e[-2:]} {fmt(wi['swap'][e].get('real'))} {H.pfmt(wi['swap'][e])}" for e in ERA_NAMES))
    fw = {}
    if cands:
        best = {}
        for form in ("add", "swap"):
            reals = {c: pdiff[c][form]["block"]["pooled"].get("diff") for c in cands if pdiff[c][form]["block"]["pooled"].get("diff") is not None}
            if reals:
                bc = max(reals, key=reals.get)
                draws = []
                for r in shift_raw:
                    vals = [r[f"{spec_name(c, form)}|{c}"] - r[f"fixed5|{c}"] for c in cands if r[f"{spec_name(c, form)}|{c}"] is not None and r[f"fixed5|{c}"] is not None]
                    if vals:
                        draws.append(max(vals))
                best[form] = {**H.psum(reals[bc], draws), "bestCandidate": bc, "note": "max over the candidates of the increment over fixed5 (each on its own rows), per shifted-label draw: a family-wise null for 'any candidate adds'"}
        fw = best
    null["shiftIncrementMaxOverCandidates"] = fw
    if fw:
        say("family-wise shift null of the best increment: " + "; ".join(f"{form.upper()} best {v['bestCandidate']} {fmt(v.get('real'))} vs med {fmt(v.get('nullMedian'))} p95 {fmt(v.get('nullP95'))} {H.pfmt(v)}" for form, v in fw.items()))

    # ---- adversary: decoy features (the candidate's statistic on a matched random walk of its log level), episode LOO
    dfeat = {}
    for c in cands:
        rws = dfeat_raw[c]
        f5 = oos[c]["fixed5"]["byEra"]
        d = {"n": len(rws), "acf1Real": rho[c]["acf1"], "acf1DecoyMean": (round(float(np.mean([r["acf1"] for r in rws if r["acf1"] is not None])), 3) if any(r["acf1"] is not None for r in rws) else None), "note": "study8_common.matched_rw of the weekly log level (13-week blocks, random signs), then the same statistic; run as fixed5 + decoy (ADD) and with the decoy in place of m2_yoy (SWAP) on the candidate's rows"}
        for form in ("add", "swap"):
            inc = [r[form]["pooled"] - f5["pooled"]["auc"] for r in rws if r[form]["pooled"] is not None and f5["pooled"]["auc"] is not None]
            d[form] = {"real": pdiff[c][form]["block"]["pooled"].get("diff"), "decoyMedian": (round(float(np.median(inc)), 3) if inc else None), "decoyP95": (round(float(np.quantile(inc, 0.95)), 3) if inc else None),
                       "decoyMax": (round(float(np.max(inc)), 3) if inc else None), "n": len(inc),
                       "byEra": {e: {"real": pdiff[c][form]["block"].get(e, {}).get("diff"), "decoyMax": (round(float(np.max(v)), 3) if (v := [r[form]["byEra"][e] - f5[e]["auc"] for r in rws if r[form]["byEra"].get(e) is not None and f5.get(e, {}).get("auc") is not None]) else None)} for e in ERA_NAMES}}
            d[form]["realAboveDecoyP95"] = bool(d[form]["real"] is not None and d[form]["decoyP95"] is not None and d[form]["real"] > d[form]["decoyP95"])
        dfeat[c] = d
    say("adversary decoy features (matched random walk, same statistic; increment over fixed5 real vs decoy median/p95/max): " + "; ".join(
        f"{c} acf1 {d['acf1Real']}/{d['acf1DecoyMean']} ADD {fmt(d['add']['real'])} vs {fmt(d['add']['decoyMedian'])}/{fmt(d['add']['decoyP95'])}/{fmt(d['add']['decoyMax'])} SWAP {fmt(d['swap']['real'])} vs {fmt(d['swap']['decoyMedian'])}/{fmt(d['swap']['decoyP95'])}/{fmt(d['swap']['decoyMax'])} (n{d['n']}{'' if d['n'] >= MIN_DRAWS else '!'})"
        for c, d in dfeat.items()))
    loo = {}
    for c in cands:
        m = masks[c]
        loo[c] = {form: S9.loo_diff(preds[spec_name(c, form)].where(m), preds["fixed5"].where(m), y) for form in ("add", "swap")}
    say("adversary episode LOO (each label episode + 26-week run-up dropped; increment over fixed5 on the rest, min..max): " + "; ".join(
        f"{c} ADD {fmt(l['add']['min'])}..{fmt(l['add']['max'])} (min at {l['add']['minEpisode']}) SWAP {fmt(l['swap']['min'])}..{fmt(l['swap']['max'])} (min at {l['swap']['minEpisode']})" for c, l in loo.items()))
    # SWAP one-event check: the band of the SWAP increment with the LOO-max episode (and its run-up) removed, beside the era-stratified
    # band; a 'worse' that turns into a tie without one episode is said so beside the verdict word (the word itself stays as registered)
    swap_wo = {}
    for c in cands:
        m = masks[c]
        key = loo[c]["swap"].get("maxEpisode")
        keep = loo_keep_mask(preds[spec_name(c, "swap")].where(m), y, key) if key else None
        if keep is None:
            swap_wo[c] = {"episode": key, "status": "not identifiable"}
            continue
        bb = H.paired_block_boot(preds[spec_name(c, "swap")].where(m & keep), preds["fixed5"].where(m & keep), y, n_boot, rng)
        st = pdiff[c]["swap"]["strat"]
        d = {"episode": key, "withoutEpisode": {k: bb.get("pooled", {}).get(k) for k in ("diff", "q05", "q95", "n")}, "withoutEpisodeByEra": {e: bb.get(e, {}).get("diff") for e in ERA_NAMES},
             "stratBand": {k: st.get(k) for k in ("diff", "q05", "q95")}, "positivesInEpisode": None}
        d["positivesInEpisode"] = int(y[m & ~keep].fillna(0).sum())
        wo = d["withoutEpisode"]
        d["tieWithoutEpisode"] = bool(wo["diff"] is not None and wo.get("n", 0) >= MIN_DRAWS and abs(wo["diff"]) < CRIT_GAIN and wo["q05"] <= 0 <= wo["q95"])
        d["stratBandContainsZero"] = bool(st.get("q05") is not None and st["q05"] <= 0 <= st["q95"])
        d["status"] = "ok"
        swap_wo[c] = d

    # ---- criteria as pre-registered: ADD four criteria on the increment's own within-era null; SWAP better / equivalent / worse
    # a null with fewer than 50 draws (unless enumerated exactly) means no verdict; an era where a late starter has no rows is not a draw shortage
    smoke = (n_shift < MIN_DRAWS) or any(s.get("real") is not None and not s.get("quotable", False) for c in cands for s in null["byCandidate"][c]["withinEraIncrement"]["add"].values())
    crit, verdicts, ctxs = {}, {}, {}
    for c in cands:
        m = masks[c]
        ctxs[c] = S9.era_context({"fixed5": preds["fixed5"].where(m)}, y, m, fresh)
        add_c = S9.criteria(spec_name(c, "add"), pdiff[c]["add"], null["byCandidate"][c]["withinEraIncrement"]["add"], smoke, ctxs[c])
        add_c["ivNote"] = "criterion (iv) is read on the within-era dwell-time permutation null of the INCREMENT over fixed5 (ADD minus fixed5 on the same permuted labels), as round 10 registers it"
        add_c["ceilingEras"] = [e for e in ERA_NAMES if (ctxs[c][e].get("fixed5Auc") or 0) > 0.95]
        add_c["ceilingNote"] = "in an era where fixed5 is above 0.95 no increment can reach the within-era null's p95, so criterion (iv) is in practice decided by the other eras; the shifted-target increment null (fixed5 at chance there) has no power against an increment over a 0.9 reference and is a diagnostic only"
        add_c["reading"] = add_reading(pdiff[c]["add"], loo[c]["add"], dfeat[c]["add"])
        sw = swap_verdict(pdiff[c]["swap"])
        sw["oneEventCheck"] = swap_wo[c]
        sw["readingNote"] = ("worse pooled, but a tie without one episode: " + swap_wo[c]["episode"] + " (" + str(swap_wo[c]["positivesInEpisode"]) + " positives); the era-stratified band " + ("contains 0" if swap_wo[c]["stratBandContainsZero"] else "excludes 0")
                             if sw["status"] == "worse" and swap_wo[c].get("tieWithoutEpisode") else None)
        if samehist.get(c):
            sw["vsSameHistoryFixed5"] = samehist[c]["swapStatusVsSameHistory"]
            add_c["iVsSameHistoryFixed5"] = samehist[c]["addIvsSameHistory"]
            add_c["lateStarterNote"] = f"two eras only (no 2019-20 rows) and a first fit on few rows; against a same-history fixed5 the SWAP reads {samehist[c]['swapStatusVsSameHistory']} and ADD (i) {samehist[c]['addIvsSameHistory']}: the registered loss against the full-history fixed5 is mostly history length"
        crit[c] = {"add": add_c, "swap": sw, "rows": rows[c], "sameInformationAsM2": rho[c]["sameInformation"], "spearmanVsM2yoy": rho[c]["spearmanVsM2yoy"],
                   "globalRowsDiagnostic": gdiag[c], "sameHistoryDiagnostic": ({"swap": samehist[c]["swapStatusVsSameHistory"], "addI": samehist[c]["addIvsSameHistory"]} if samehist.get(c) else None)}
        verdicts[c] = {"add": ("sixth signal (owner reads it first)" if add_c["all"] == "pass" else ("not supported" if add_c["all"] == "fail" else "not identifiable")), "swap": sw["status"]}
    for c in unavailable:
        crit[c] = {"add": {"all": "not available", "why": avail[c]["why"]}, "swap": {"status": "not available", "why": avail[c]["why"]}}
        verdicts[c] = {"add": "not available", "swap": "not available"}
    for c in CANDS:
        if c in cands:
            ac, sw = crit[c]["add"], crit[c]["swap"]
            say(f"criteria {c:16s}: ADD (i) {ac['i']['status']} diff {fmt(ac['i'].get('diff'))} q05 {fmt(ac['i'].get('q05'))} | (ii) {ac['ii']['status']} eras {' '.join(fmt(v) for v in ac['ii']['byEra'].values())} | (iii) {ac['iii']['status']} fresh {fmt(ac['iii'].get('diff'))} | "
                f"(iv) {ac['iv']['status']} increment-null rejects {ac['iv']['erasRejecting']}/3 p {' '.join(fmt(ac['iv']['byEra'][e]['p']) for e in ERA_NAMES)} -> ADD {ac['all'].upper()}: {verdicts[c]['add']} | SWAP {sw['status'].upper()} diff {fmt(sw.get('diff'))} [{fmt(sw.get('q05'))},{fmt(sw.get('q95'))}] eras {' '.join(fmt(v) for v in (sw.get('byEra') or {}).values())}"
                + (f" ({sw['note']})" if sw.get("note") else "") + (f" | |rho| vs m2_yoy {abs(rho[c]['spearmanVsM2yoy']):.2f} > {RHO_SAME}: the same information re-labelled" if rho[c]["sameInformation"] else ""))
        else:
            say(f"criteria {c:16s}: NOT AVAILABLE ({avail[c]['why']})")
    say("beside the verdicts (diagnostics, the words above stay as registered): " + "; ".join(
        f"{c} ADD {crit[c]['add']['reading']['word']}" + (f" | SWAP without {swap_wo[c]['episode']} ({swap_wo[c]['positivesInEpisode']} pos): {fmt(swap_wo[c]['withoutEpisode']['diff'])} [{fmt(swap_wo[c]['withoutEpisode']['q05'])},{fmt(swap_wo[c]['withoutEpisode']['q95'])}] strat {fmt(swap_wo[c]['stratBand']['diff'])} [{fmt(swap_wo[c]['stratBand']['q05'])},{fmt(swap_wo[c]['stratBand']['q95'])}]"
                                                           + (" -> TIE WITHOUT THAT EPISODE" if swap_wo[c].get("tieWithoutEpisode") else "") if swap_wo[c].get("status") == "ok" else "")
        + (f" | vs same-history fixed5: SWAP {samehist[c]['swapStatusVsSameHistory']}, ADD (i) {samehist[c]['addIvsSameHistory']}" if samehist.get(c) else "") for c in cands)
        + f"; ceiling eras (fixed5 > 0.95, criterion (iv) undecidable there): " + str({c: crit[c]["add"]["ceilingEras"] for c in cands if crit[c]["add"]["ceilingEras"]}))
    # the placebo and the L4 lags read against the real m2_yoy (the SWAP comparison is exactly 'this series instead of m2_yoy')
    placebo = {}
    for c in [x for x in ("m2_yoy_placebo52", "m2_yoy_lag13", "m2_yoy_lag26") if x in cands]:
        sw, al = pdiff[c]["swap"]["block"]["pooled"], pdiff[c]["alone_vs_m2only"]["block"]["pooled"]
        placebo[c] = {"swapVsFixed5": {k: sw.get(k) for k in ("diff", "q05", "q95")}, "aloneVsM2only": {k: al.get(k) for k in ("diff", "q05", "q95")}, "swapVerdict": crit[c]["swap"]["status"],
                      "scoresAsWellAsReal": crit[c]["swap"]["status"] in ("better", "equivalent"), "spearmanVsM2yoy": rho[c]["spearmanVsM2yoy"]}
    if "m2_yoy_placebo52" in placebo:
        pz = placebo["m2_yoy_placebo52"]
        pz["passes"] = (None if pz["swapVerdict"] == "not identifiable" else (not pz["scoresAsWellAsReal"]))
        say(f"placebo (m2_yoy shifted back 52 weeks, identical procedure): SWAP vs fixed5 {fmt(pz['swapVsFixed5']['diff'])} [{fmt(pz['swapVsFixed5']['q05'])},{fmt(pz['swapVsFixed5']['q95'])}] -> {pz['swapVerdict']}; ALONE vs m2only {fmt(pz['aloneVsM2only']['diff'])} [{fmt(pz['aloneVsM2only']['q05'])},{fmt(pz['aloneVsM2only']['q95'])}]; "
            f"rho vs m2_yoy {pz['spearmanVsM2yoy']:+.2f}; must NOT score as well as the real one: {'PASS (it does not)' if pz['passes'] else ('FAIL (it scores as well)' if pz['passes'] is False else 'not identifiable')}"
            + " | L4 lags: " + "; ".join(f"{c} SWAP {fmt(v['swapVsFixed5']['diff'])} [{fmt(v['swapVsFixed5']['q05'])},{fmt(v['swapVsFixed5']['q95'])}] -> {v['swapVerdict']} (" + ("older information scores as well: the publication lag is not binding" if v["swapVerdict"] == "equivalent" else ("older information scores better: the cycle reads slower than we use it" if v["swapVerdict"] == "better" else "older information scores worse")) + ")" for c, v in placebo.items() if c != "m2_yoy_placebo52"))
    same = [c for c in cands if rho[c]["sameInformation"]]
    one_event = [c for c in cands if verdicts[c]["swap"] == "worse" and swap_wo[c].get("tieWithoutEpisode")]
    small = [c for c in cands if crit[c]["add"]["reading"]["word"].startswith("small everywhere")]
    beats = [c for c in cands if verdicts[c]["swap"] == "better" or verdicts[c]["add"].startswith("sixth")]
    say("summary: " + "; ".join(f"{c} ADD {verdicts[c]['add']} / SWAP {verdicts[c]['swap']}" for c in CANDS) + (f" | the same information as m2_yoy re-labelled (|rho| > {RHO_SAME}): {same}" if same else " | no candidate is m2_yoy re-labelled (|rho| <= 0.8 for all)")
        + (f" | one-event SWAP losses (a tie without the episode {sorted(set(swap_wo[c]['episode'] for c in one_event))}): {one_event}; within eras these read as M2's equals, not as worse" if one_event else "")
        + (f" | small everywhere, failing only the +0.03 bar (no era, episode or sign breaks it): {small}" if small else "")
        + (f" | late starters judged against a same-history fixed5: " + ", ".join(f"{c} SWAP {samehist[c]['swapStatusVsSameHistory']} / ADD (i) {samehist[c]['addIvsSameHistory']}" for c in samehist) if samehist else "")
        + (" | reading: nothing BEATS m2_yoy in the forecast object" + ("" if not one_event else ", and the losses of " + str(one_event) + " are one event, not 'everything loses to it'") if not beats else f" | reading: {beats} clear a registered bar and wait for the owner")
        + (" | NO VERDICT: a null has fewer than 50 draws (smoke run); the lines above are the provisional reading and the full run's p-values replace them" if smoke else ""))

    # ---- leakage checks
    leak = {"lags": {n: {"lagDays": meta[n].get("lagDays"), "stampedAtClose": meta[n].get("stampedAtClose"), "lastAvailableInPanel": meta[n].get("lastAvailable"),
                         **({"stampConvention": "reference month end (moved there before the lag when the raw stamp is earlier)", "monthEndShareRaw": meta[n].get("monthEndShareRaw"), "rowsMovedToMonthEnd": meta[n].get("rowsMovedToMonthEnd")} if meta[n].get("monthly") else {})} for n in on_disk},
            "m2LagDays": C.M2_LAG_DAYS, "absentSeries": absent, "notImputed": True}
    # the shared loader (study8_common.load_daily, frozen) adds the 42-day lag to US M2's raw stamp: right only when that stamp is the month end
    m2_raw = pd.to_datetime(pd.read_csv(os.path.join(a.data, "M2_1d.csv"))["ts"], unit="ms")
    leak["lags"]["M2"] = {"lagDays": C.M2_LAG_DAYS, "loader": "study8_common.load_daily (raw stamp + lag)", **month_end_info(m2_raw)}
    stamp_ok = bool(leak["lags"]["M2"]["monthEndShareRaw"] == 1.0)
    leak["monthlyStampGuard"] = {"usM2RawStampsAllMonthEnd": stamp_ok, "extrasMovedToMonthEnd": {n: meta[n].get("rowsMovedToMonthEnd") for n in on_disk if meta[n].get("monthly")},
                                 "note": "a period-START stamp (FRED style) plus 42 days would precede the real release; the extras are moved to the month end before the lag, US M2 is checked here" + ("" if stamp_ok else " and FAILS the check: the shared loader's M2 lag is too short for this file")}
    leak["sharedLoaderDxyDating"] = "study8_common.load_daily dates a DXY bar stamped 21:00-23:00 UTC on its open day, so the harness's dxy_* features carry Monday's close in a Sunday row; no model in this module uses a dxy_* feature (SIGNALS and every candidate exclude them); recorded for the harness owner, study8 files are frozen"
    leak["vintage"] = "every macro series (US M2, CNM2, EUM2, JPM2, GBM2, FEDBS, RRP, TGA) is the current TradingView vintage; the publication lag protects timing, not revisions (the 2021 US M2 redefinition and annual seasonal re-estimation are not replayed): point in time on current-vintage data, the same assumption round 8 registered for US M2"
    pf5 = preds["fixed5"]
    Xh = F.copy()
    Xh["btc_dd_ath"] = dd_harness.values
    ph, _ = S9.run_spec(Xh, Y, SIGNALS)
    dd_rows = (F["btc_dd_ath"] - dd_harness).abs()
    differing = dd_rows[dd_rows > 1e-9]
    trainable = F[SIGNALS].notna().all(axis=1) & y.notna()
    first_trainable = trainable[trainable].index[0] if trainable.any() else None
    last_differing = differing.index[-1] if len(differing) else None
    immaterial = bool(first_trainable is not None and (last_differing is None or last_differing < first_trainable))
    leak["athAnchor"] = {"rowsDiffering": int(len(differing)), "lastRowDiffering": (str(last_differing.date()) if last_differing is not None else None), "firstTrainableRow": (str(first_trainable.date()) if first_trainable is not None else None),
                         "fixed5PredMaxAbsDiffOnOwnRows": round(float((ph.where(masks["_fixed5"]) - pf5.where(masks["_fixed5"])).abs().max()), 10), "immaterialHere": immaterial}
    n = len(F)
    cuts = rng.integers(max(1, n // 4), n - 1, size=n_trunc)
    worst_f, worst_p, tested, worst_col = 0.0, 0.0, 0, None
    for cpos in cuts:
        cut_date = F.index[int(cpos)]
        Dc = D[D.index <= cut_date]
        Xc, Pc, Yc, Fc, _, _, _, _, _ = build_all(Dc, a.data, cut_date)
        for col in cands:
            if col not in Fc:
                continue
            fa, fb = Fc[col].iloc[-1], F[col].loc[cut_date]
            if np.isfinite(fa) and np.isfinite(fb):
                dv = abs(float(fa) - float(fb))
                if dv > worst_f:
                    worst_f, worst_col = dv, col
        for c in cands:
            s = spec_name(c, "add")
            pc, _ = S9.run_spec(Fc, Yc, SPECS[s])
            pfull = preds[s].reindex(pc.index)
            both = pc.notna() & pfull.notna()
            if both.any():
                worst_p = max(worst_p, float((pc[both] - pfull[both]).abs().max()))
        tested += 1
    leak["truncation"] = {"ok": bool(worst_f <= 1e-9 and worst_p <= 1e-9), "maxAbsDiffFeatures": worst_f, "worstFeature": worst_col, "maxAbsDiffPredictions": worst_p, "tested": tested, "specsChecked": [spec_name(c, "add") for c in cands],
                          "cuts": [str(F.index[int(cpos)].date()) for cpos in cuts], "note": "the whole pipeline, optional-series loading included, rebuilt on the daily panel cut at each Sunday"}
    leak["labels"] = {"lastLabelledRow": str(y[y.notna()].index[-1].date()), "lastCompleteSunday": str(last_complete.date()), "provisionalBarsExcluded": provisional, "labelLagWeeks": 26}
    leak["windows"] = {"L1": "52-week log change of the USD sum at t; each M2 at its last published value (6-week lag), FX at the last close <= t", "L2": "52/13-week log changes at t of series lagged 7 days",
                       "L3": "13/26-week log changes at t of (USDT.D + USDC.D)/100 x TOTAL, no lag", "L4/placebo": "m2_yoy (6-week lag) shifted back 13 / 26 / 52 weeks", "ath": "running max of weekly closes over the full BTCUSD history"}
    phase["leakageSec"] = round(time.time() - t0 - phase["predictionsSec"] - phase["bootstrapsSec"] - phase["nullsDecoysSec"], 1)
    say(f"leakage: truncation test at {tested} random Sundays (whole pipeline incl. series loading rebuilt on the cut daily panel; every ADD model): features max |diff| {worst_f:.1e}{(' at ' + worst_col) if worst_col and worst_f > 1e-9 else ''}, predictions max |diff| {worst_p:.1e}, ok {leak['truncation']['ok']}; "
        f"publication lags applied before any feature (monthly {C.M2_LAG_DAYS} d, Fed {FED_LAG_DAYS} d, FX at close); last published value carried forward; absent series {absent if absent else 'none'} not imputed; "
        f"ATH anchor {'immaterial here' if immaterial else 'material'} (fixed5 preds max |diff| {leak['athAnchor']['fixed5PredMaxAbsDiffOnOwnRows']:.1e}); last labelled row {leak['labels']['lastLabelledRow']}; "
        f"monthly stamp guard: US M2 raw stamps all month-end {stamp_ok}, extras moved to month end {leak['monthlyStampGuard']['extrasMovedToMonthEnd']} (all before the panel start when non-zero); macro series are current-vintage")

    # ---- today: the last complete Sunday
    tlast = last_complete
    today = {"asOf": str(tlast.date()), "dataLastBarUtc": last_utc, "dataLastBarEt": last_et, "btcd": round(float(P.loc[tlast, "BTC.D"]), 2),
             "readings": {"fixed5": (round(float(preds["fixed5"].loc[tlast]), 4) if np.isfinite(preds["fixed5"].loc[tlast]) else None), "m2only": (round(float(preds["m2only"].loc[tlast]), 4) if np.isfinite(preds["m2only"].loc[tlast]) else None)},
             "trainingBase": (round(float(base.loc[tlast]), 4) if np.isfinite(base.loc[tlast]) else None), "candidateValues": {}, "inputs": {}}
    for c in cands:
        for form in FORMS:
            v = preds[spec_name(c, form)].loc[tlast]
            today["readings"][spec_name(c, form)] = (round(float(v), 4) if np.isfinite(v) else None)
        v = F.loc[tlast, c]
        today["candidateValues"][c] = (round(float(v), 4) if np.isfinite(v) else None)
    today["candidateValues"]["m2_yoy"] = round(float(F.loc[tlast, "m2_yoy"]), 4)
    inp = today["inputs"]
    if "gm2_yoy" in cands:
        comps = avail["gm2_yoy"]["components"]
        usd = {"M2": float(P.loc[tlast, "M2"])}
        for m in comps[1:]:
            fx, op = FX_OF[m]
            usd[m] = float(P.loc[tlast, m] * P.loc[tlast, fx] if op == "mul" else P.loc[tlast, m] / P.loc[tlast, fx])
        inp["globalM2UsdTn"] = {k: round(v / 1e12, 2) for k, v in usd.items()}
        inp["globalM2UsdTn"]["total"] = round(sum(usd.values()) / 1e12, 2)
        inp["globalM2ComponentYoY"] = {m: round(float(np.log(P[m]).diff(52).loc[tlast]), 4) for m in comps}
    if "FEDBS" in P:
        inp["fedbsTn"] = round(float(P.loc[tlast, "FEDBS"]) / 1e12, 3)
    if all(k in P for k in ("FEDBS", "RRP", "TGA")):
        inp["rrpBn"], inp["tgaBn"] = round(float(P.loc[tlast, "RRP"]) / 1e9, 1), round(float(P.loc[tlast, "TGA"]) / 1e9, 1)
        inp["netLiquidityTn"] = round(float(P.loc[tlast, "FEDBS"] - P.loc[tlast, "RRP"] - P.loc[tlast, "TGA"]) / 1e12, 3)
    if "USDC.D" in P:
        inp["stableFloatBn"] = round(float((P.loc[tlast, "USDT.D"] + P.loc[tlast, "USDC.D"]) / 100.0 * P.loc[tlast, "TOTAL"]) / 1e9, 1)
        inp["usdtD"], inp["usdcD"] = round(float(P.loc[tlast, "USDT.D"]), 3), round(float(P.loc[tlast, "USDC.D"]), 3)
    if meta["STABLES"]["onDisk"] and "STABLES" in P and np.isfinite(P.loc[tlast, "STABLES"]):
        st = np.log(P["STABLES"].clip(lower=1e-9))
        fl = np.log(((P["USDT.D"] + P["USDC.D"]) / 100.0 * P["TOTAL"]).clip(lower=1e-9)) if "USDC.D" in P else None
        inp["stablesBn"] = round(float(P.loc[tlast, "STABLES"]) / 1e9, 1)
        inp["stables13w"] = (round(float(st.diff(13).loc[tlast]), 4) if np.isfinite(st.diff(13).loc[tlast]) else None)
        inp["stables26w"] = (round(float(st.diff(26).loc[tlast]), 4) if np.isfinite(st.diff(26).loc[tlast]) else None)
        if fl is not None:
            ov = st.notna() & fl.notna()
            inp["stablesVsConstructedFloat"] = {"overlapWeeks": int(ov.sum()), "spearman13wChanges": C.spearman(st.diff(13)[ov].values, fl.diff(13)[ov].values), "ratioNow": round(float(np.exp(st.loc[tlast] - fl.loc[tlast])), 3)}
    inp["lastPublishedMonthInPanel"] = {}
    for m in ["M2"] + [x for x in FX_OF if meta[x]["onDisk"]]:
        s = read_series(a.data, m, C.M2_LAG_DAYS, False, m != "M2")          # the same 6-week lag the loader (M2, raw stamp) and load_extra (the others, month-end stamp) apply
        s = s[s.index <= tlast]
        inp["lastPublishedMonthInPanel"][m] = (str((s.index[-1] - pd.Timedelta(days=C.M2_LAG_DAYS)).date()) if len(s) else None)
    today["fresh"] = bool(fresh.loc[tlast])
    say(f"TODAY {today['asOf']} (data last bar {last_utc} / {last_et}) BTC.D {today['btcd']}: candidate values " + " ".join(f"{c} {fmt(today['candidateValues'].get(c), 4)}" for c in ["m2_yoy"] + cands)
        + f"; inputs " + ", ".join(f"{k} {v}" for k, v in inp.items() if k not in ("globalM2ComponentYoY", "stablesVsConstructedFloat")))
    say(f"TODAY readings beside fixed5 {fmt(today['readings']['fixed5'])} (m2only {fmt(today['readings']['m2only'])}, train-base {fmt(today['trainingBase'])}): " + " ".join(f"{c} swap/add/alone {fmt(today['readings'].get(spec_name(c, 'swap')))}/{fmt(today['readings'].get(spec_name(c, 'add')))}/{fmt(today['readings'].get(spec_name(c, 'alone')))}" for c in cands)
        + (f"; STABLES vs constructed float: overlap {inp['stablesVsConstructedFloat']['overlapWeeks']} w, spearman of 13-week changes {inp['stablesVsConstructedFloat']['spearman13wChanges']:+.2f}, ratio {inp['stablesVsConstructedFloat']['ratioNow']}" if "stablesVsConstructedFloat" in inp else ""))

    # ---- side targets (contract): fall10_26w AUC and y13 IC for fixed5 and the SWAP / ADD models on each candidate's rows
    side = {}
    for tg, binary in SIDE_TARGETS:
        side[tg] = {"fixed5": {}}
        pb, _ = S9.run_spec(F, Y, SIGNALS, target=tg, binary=binary)
        for c in cands:
            side[tg]["fixed5"][c] = C.metrics(pb.where(masks[c]), Y[tg], binary).get("pooled", {})
            side[tg][c] = {}
            for form in ("swap", "add"):
                p, _ = S9.run_spec(F, Y, SPECS[spec_name(c, form)], target=tg, binary=binary)
                side[tg][c][form] = C.metrics(p.where(masks[c]), Y[tg], binary)
    say("side targets on each candidate's rows (fixed5 | swap / add; fall10 positives in brackets): fall10_26w auc " + " ".join(
        f"{c} {fmt(side['fall10_26w']['fixed5'][c].get('auc'))}|{fmt(side['fall10_26w'][c]['swap'].get('pooled', {}).get('auc'))}/{fmt(side['fall10_26w'][c]['add'].get('pooled', {}).get('auc'))} [{int(round((side['fall10_26w']['fixed5'][c].get('base') or 0) * (side['fall10_26w']['fixed5'][c].get('n') or 0)))}]" for c in cands)
        + " ; y13 ic " + " ".join(f"{c} {fmt(side['y13']['fixed5'][c].get('ic'))}|{fmt(side['y13'][c]['swap'].get('pooled', {}).get('ic'))}/{fmt(side['y13'][c]['add'].get('pooled', {}).get('ic'))}" for c in cands))

    notes = [
        "Common rows per comparison: each candidate's SWAP, ADD and ALONE models and fixed5 are scored on the rows where all four forecast (rows.<candidate>); a late starter (L3 needs USDC.D from 2018-12, 26 weeks of float history, 60 training rows and the 26-week label lag) shortens its own comparison and fixed5 is RE-SCORED on those rows (oos.<candidate>.fixed5: the same expanding-window fixed5, fitted on the full history, not refit). This per-candidate reading of the plan's common-row sentence is the chosen one; the round-9 single-common-set reading (every comparator on the intersection of all candidates' rows, 2021-04 onward, two eras) is given beside it as oos.globalCommonRows and criteria.<candidate>.globalRowsDiagnostic (block bands, the SWAP word and ADD (i)-(iii) on those rows) and is not the criterion; a disagreement between the two readings is visible there.",
        "Late starters: the registered reference (fixed5 re-scored on the candidate's rows) has refit on about three times the history of the candidate's own models at their first refit, so part of a late starter's loss is the training-window handicap; sameHistory.<candidate> refits fixed5 on exactly the candidate's trainable rows (its five features blanked where the candidate is NaN), scores it on the same rows, and gives the SWAP / ADD bands and words against it; criteria.<candidate>.add.lateStarterNote carries that reading beside the registered verdict.",
        "SWAP one-event check (adversary.swapOneEvent): the SWAP increment's block band with the LOO-max episode (the label episode whose removal helps the candidate most, with its 26-week run-up) removed, beside the era-stratified band; a 'worse' that is a tie by the SWAP rule without that one episode is flagged tieWithoutEpisode and said in the summary; the verdict word itself stays as registered (pooled block band).",
        "ADD reading (criteria.<candidate>.add.reading): a diagnostic word beside the registered verdict: 'small everywhere' = increment > 0, every era >= -0.02 and every LOO increment >= -0.02 (fails only the +0.03 bar); 'era- or episode-carried'; 'loses'. criteria.<candidate>.add.ceilingEras lists eras where fixed5 > 0.95: no increment can reject the within-era null there, so criterion (iv) is decided by the other eras; the shifted-target increment null (fixed5 at chance under shifted labels) has no power against an increment over a 0.9 reference and is reported as a diagnostic only.",
        "fixed5 = study8_baselines.SIGNALS through the same walk-forward (expanding window, refit 13 weeks, labels withheld 26 weeks, logistic lam 1); btc_dd_ath is the true-ATH column (study8_honest.ath_drawdown over the full BTCUSD history); the harness anchor is immaterial here (every row it changes precedes the first trainable row).",
        f"Publication lags: US M2 by the shared loader ({C.M2_LAG_DAYS} days), CNM2 / EUM2 / JPM2 / GBM2 the same {C.M2_LAG_DAYS} days, FEDBS / RRP / TGA {FED_LAG_DAYS} days, FX and crypto market series none; FX daily bars (open 21:00/22:00 UTC) are dated at their close so a Sunday row holds Friday's close; every series carries its last published value forward (no interpolation); rows dated after the panel's last day are dropped before the fill.",
        f"Monthly stamp guard: the {C.M2_LAG_DAYS}-day lag is right only when the monthly bar is stamped at the reference month's END (TradingView ECONOMICS does so; a FRED-style period-START stamp plus the lag would precede the real release). CNM2 / EUM2 / JPM2 / GBM2 stamps are moved to the month end before the lag (a stamp already there is unchanged; the move is never earlier) and the raw month-end share and rows moved are in leakage.lags; US M2 is loaded by the frozen shared loader on its raw stamp, so its raw stamps are checked and reported (leakage.monthlyStampGuard). Macro series are current-vintage (leakage.vintage); the shared loader's DXY dating slip is recorded in leakage.sharedLoaderDxyDating and touches no model here.",
        f"Within-era permutation draws: {n_within} per era by default (round 9's count); 2023-26 (5 label blocks, 120 arrangements) is enumerated exactly whatever the count; --within overrides for the runner's budget (settings.nWithinEra says what ran).",
        "L1 global M2 = US M2 + EU M2 x EURUSD + CN M2 / USDCNY + JP M2 / USDJPY + GB M2 x GBPUSD, in USD at the FX close <= t, so a dollar move changes the USD sum (the standard 'global M2 in USD' construct); 52-week log change.",
        "L2 net liquidity = FEDBS - RRP - TGA (all USD; the series are unit-consistent from 2002); L3 stablecoin float = (USDT.D + USDC.D) / 100 x TOTAL; STABLES (CRYPTOCAP, from 2025-05) is too short for any walk-forward and is only compared with the constructed float in the today block.",
        "The placebo is US M2 y/y shifted BACK 52 weeks (a lag of one cycle); a forward shift would read the future. It goes through the identical procedure as every other candidate (SWAP, ADD, ALONE, bands, nulls, decoys, LOO) and is judged by the SWAP rule: it 'scores as well as the real one' when its SWAP verdict is better or equivalent.",
        "Paired bands: 26-week circular block bootstrap (study8_honest.paired_block_boot, pooled and per era), episode bootstrap over label episodes with their 26-week run-up (study8_tda_sig.paired_episode_boot), era-stratified difference (study9_candidates.paired_strat_boot), fresh-start rows (BTC.D within 2 points of its 13-week high).",
        "Within-era nulls are dwell-time block permutations of each era's label episodes and gaps (study8_honest.perm_blocks / apply_order through study9_candidates.perm_positions) with the whole procedure rerun for fixed5 and every ADD and SWAP model; an era is enumerated exactly when its arrangements are at most max(n_within, 120). Criterion (iv) is read on the null of the INCREMENT over fixed5 (ADD minus fixed5 on the same permuted labels), as round 10 registers it; the whole-model null is reported beside it.",
        "Shifted-target nulls (circular shift of every target column by 26+ weeks) rerun the whole procedure for fixed5 and every ADD and SWAP model on the same shifted labels; null.shiftIncrementMaxOverCandidates is the family-wise null of the best increment (ADD and SWAP), reported beside the per-candidate p-values, which carry no multiplicity.",
        "Decoy features: the candidate's own statistic computed on a matched random walk (study8_common.matched_rw, 13-week blocks, random signs) of its weekly log level, run in ADD and SWAP form on the candidate's rows; the lag-1 autocorrelation of the real feature and of the decoys is printed beside the increments.",
        "Spearman of each candidate with m2_yoy is on the candidate's common rows; |rho| > 0.8 is said in the summary as the same information re-labelled (a candidate that passes with |rho| > 0.8 adds a re-labelling of m2_yoy, not new liquidity information).",
        "Brier is reported against the walk-forward training-window base rate (study8_honest.run_const) and the era's own rate (not available in real time).",
        "The last complete weekly bar is the last Sunday strictly before the last daily row, so the last daily row is always provisional whatever time the data were fetched.",
        f"Null draw counts are printed beside every p (n!, i.e. fewer than {MIN_DRAWS}, means resolution 1/n, not a p-value; E = enumerated exactly); only the full run's p-values are quotable.",
        "A candidate that is better in SWAP form replaces M2 in the forecast object only after the owner reads it; nothing here touches the bot.",
    ]
    if S9._LINES[1]:
        notes.append(f"{S9._LINES[1]} summary lines were dropped to stay under the 60-line limit; everything is in results.json.")
    series = {"fixed5": C.thin(preds["fixed5"].where(masks["_fixed5"]), every=2), "m2only": C.thin(preds["m2only"].where(masks["_fixed5"]), every=2)}
    for c in cands:
        for form in ("swap", "add"):
            series[spec_name(c, form)] = C.thin(preds[spec_name(c, form)].where(masks[c]), every=2)
        series[c] = C.thin(F[c].where(masks[c]), every=2)
    series["m2_yoy"] = C.thin(F["m2_yoy"].where(masks["_fixed5"]), every=2)
    res = {"module": "study10_liquidity", "plan": "ROUND10_PLAN.md [2]", "dataLastBarUtc": last_utc, "dataLastBarEt": last_et, "lastCompleteSunday": str(last_complete.date()), "fast": a.fast,
           "runtimeSec": round(time.time() - t0, 1), "settings": {"nShift": n_shift, "nWithinEra": n_within, "nBoot": n_boot, "nDecoyFeatures": n_dfeat, "nTruncation": n_trunc, "workers": a.workers, "minDrawsForP": MIN_DRAWS, "phaseSec": phase},
           "optionalSeries": meta, "availability": avail, "candidates": CANDS, "candidatesAvailable": cands, "candidatesUnavailable": unavailable, "specs": SPECS, "rows": rows,
           "oos": {"fall5_26w": oos, "reference": ref, "globalCommonRows": gtab, "globalRowsPaired": gdiag, "sideTargets": side}, "pairedVsFixed5": pdiff, "sameHistory": samehist, "spearmanVsM2yoy": rho, "signAtRefits": signs,
           "null": null, "adversary": {"decoyFeatures": dfeat, "episodeLOO": loo, "swapOneEvent": swap_wo, "placebo": placebo}, "criteria": crit, "criteriaContext": ctxs, "verdicts": verdicts, "noVerdict": smoke,
           "diagnosticsBesideVerdicts": {"oneEventSwapLosses": one_event, "smallEverywhereAdd": small, "clearsARegisteredBar": beats, "sameHistoryLateStarters": {c: {"swap": v["swapStatusVsSameHistory"], "addI": v["addIvsSameHistory"]} for c, v in samehist.items()}},
           "leakage": leak, "today": today, "series": series, "notes": notes}
    C.write_results(a.out, res)
    say(f"wrote {os.path.join(a.out, 'results.json')} in {time.time() - t0:.0f}s (data last bar {last_utc} / {last_et}); verdicts: " + "; ".join(f"{c} ADD {v['add']} / SWAP {v['swap']}" for c, v in verdicts.items()))


if __name__ == "__main__":
    main()
