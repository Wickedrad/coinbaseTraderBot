#!/usr/bin/env python3
"""Round 13: the refinement stage (ROUND13_PLAN.md, pre-registered 2026-11-02 18:58 UTC / 1:58 PM EST).

Question. Rounds 8-10 found nothing that beats the five-signal logistic (fixed5 = study8_baselines.SIGNALS) for a 5+ point
BTC.D fall within 26 weeks (fall5_26w on TradingView BTC.D weekly closes, W-SUN). Where fixed5 still fails (A post-season
overconfidence, B pre-season alarms, C under-called onsets, D crash-led falls), does one slight condition-gated adjustment
fitted to that failure improve the calibration (Brier, log loss) without breaking the rest?

Candidates (fixed by the plan; nothing added; all through the round-8 harness: expanding window, refit every 13 weeks,
label lag 26 weeks, study8_common.walk_forward, z-scored inputs and the harness logistic with lam 1):
  R1  fixed5 + condA x (BTC.D minus its trailing 13-week low, points); condA = BTC.D at least 15 points below its trailing
      104-week high (both windows end at t and include it). Expected sign negative.
  R1b fixed5 + condA x log(1 + weeks since the trailing 104-week high). Reported beside R1, not adopted on its own.
  R2  the five inputs with sample weights 0.5 ** (age_weeks / 156), age measured from each refit date.
  R3  a two-parameter logistic map of fixed5's logit, fitted on fixed5's own earlier out-of-sample predictions whose labels
      are known at the refit date (the harness walk-forward over those predictions: label lag 26, refit on fixed5's refit
      dates, min_train 52 = active from the first date with 52 such rows; fixed5 unchanged before). Monotone by construction.
  R4  fixed5 + fresh3 x (BTC.D 8-week change, points); fresh3 = study8_common.fresh_mask(pts 3, weeks 13). Expected positive.
  R+  the passing candidates combined, evaluated once, only if two or more pass (R1b is not adopted on its own, so not in R+).

Criteria (pre-registered; labelled common out-of-sample rows; paired against fixed5; 26-week circular block bootstrap and
episode bootstrap): (i) pooled Brier improvement >= 0.005 with block q05 > 0 and log-loss improvement >= 0.01; (ii) no era
worse by more than 0.005 Brier; (iii) inside the target weeks improvement >= 0.01 with block q05 > 0 and outside no worse than
-0.003 (R1, R1b: condition A weeks; R4: fresh-start weeks; R2, R3: A union B, B = fixed5 p > 0.5 with no fall while BTC.D is
within 3 points of its 52-week high: the registered split uses the outcome, and the same test on outcome-free targets, A union B'
and A alone, is reported beside it as a labelled diagnostic); (iv) the real pooled improvement beats the p95 of
its matched placebo AND the shifted-label null at p < 0.05; (v) no out-of-sample fall week below 2% and the pooled AUC does
not fall by more than 0.01. Verdict: adopted (all five) | condition note ((iii) and (v) pass, (i) or (iv) fails) | not
supported (otherwise, with the failing criteria).

Adversary. Placebos (whole procedure per draw): R1/R1b/R4 = the same raw term gated by random blocks with the condition's own
run lengths, placed at random inside the out-of-sample weeks (and, separately, inside the earlier training weeks, so the
fitted coefficient never sees the real condition); R2 = ages randomly permuted among the training rows at every refit;
R3 = the map fitted on past predictions shuffled in time against their labels. Shifted labels: draws exactly as
study8_common.shift_null (circular shift k uniform in [26, n - 26), i.e. at least 26 weeks in either direction), every model
refitted on the shifted labels, the improvement over the equally shifted fixed5 scored on the labelled common rows (the rows
the real statistic uses) where the shifted label exists.

Leakage. Truncation test at file level (every data file the pipeline reads, including BTCUSD for the true-ATH drawdown and
the CoinMarketCap file, cut to the bars up to the cut date into a temporary folder, and the whole pipeline rebuilt from those
files: conditions, terms, features, labels and every model's predictions unchanged up to the cut) at random Sundays AND at
every fixed5 refit date (label-lag leaks show only at refit dates), R3's activation date among them; explicit window checks
(the 104-week high and 13-week low include t and nothing after it); R3's calibration set holds only rows whose labels are
known at the refit date and the map never changes the ranking inside a refit window; R2's ages; the placebo blocks are drawn
from the condition alone (no label, no prediction); the partial current week is excluded (the last daily row is never a
complete weekly close). Design-level selection (the conditions were read off fixed5's 2019-2026 out-of-sample errors, the
rows scored here) is stated in leakage.designSelection: no adversary here models that choice.

Diagnostics beside the plan (labelled, never verdict inputs): outcome-free (iii) for R2 and R3 (A union B', A alone); R3
against one-parameter recalibrations on its own schedule (intercept only, shrink to the training base rate) and the map's
fixed point at every refit; gate-only controls and the spillover of the gated terms outside their condition; a
term-preserving placebo and the placebo's own-gate (iii)/(v) reach; R1's identification (gate rows in training, the
within-run correlation, the inside gain split by what each refit had seen); the stand-down in the unlabelled tail.

  python3 research/btcd_fractal/study13_refine.py --data research/btcd_fractal/data --out research/btcd_fractal/out13/refine [--nulls 200] [--boots 1000] [--workers N] [--fast]

No network; aggregates only; timestamps from the data's last bar and from the clock, US Eastern and UTC. Nothing here touches
the bot.
"""
import argparse
import datetime as dt
import json
import math
import os
import sys
import tempfile
import time
from multiprocessing import get_context

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")  # one BLAS thread per process: the pool workers must not oversubscribe the cores

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import study8_common as C  # noqa: E402
from study8_baselines import SIGNALS  # noqa: E402
import study8_honest as H  # noqa: E402  (ath_drawdown: the true all-time high from the full BTCUSD history)
import study9_candidates as S9  # noqa: E402  (run_spec: the round-9 harness wrapper; DATA_CUT, EVAL_FROM)
import study10_altled as S10  # noqa: E402  (kind_targets: crash-led / alt-led fall weeks, round 10)

# ------------------------------------------------------------------------------------------- pre-registered constants
TARGET = "fall5_26w"
LAG_W, REFIT_W, MIN_TRAIN = 26, 13, 60          # study8_common.walk_forward defaults (label lag 26 for a 26-week target)
WF_START = "2019-01-06"                         # study8_common.walk_forward default start
DATA_CUT, EVAL_FROM = S9.DATA_CUT, S9.EVAL_FROM  # "2016-06-01", "2019-01-01"
POST_PTS, POST_HI_W, LOW_W = 15.0, 104, 13      # condition A and R1's term
FRESH_PTS, FRESH_W, CHG_W = 3.0, 13, 8          # R4's condition and term
NEAR_PTS, NEAR_HI_W = 3.0, 52                   # failure B's "within 3 points of its 52-week high"
B_P, C_P = 0.5, 0.35                            # failure B (p > 0.5, no fall) and failure C (fall week with p < 0.35)
HALF_LIFE_W = 156.0                             # R2
R3_MIN = 52                                     # R3 active from the first date with >= 52 known-label predictions
FLOOR = 0.02                                    # Steven's 50:1 loss: act above 2%
LL_EPS = 1e-6                                   # log loss: probabilities clipped to [1e-6, 1 - 1e-6]
CRIT = {"brier": 0.005, "logloss": 0.01, "eraWorse": 0.005, "inside": 0.01, "outside": -0.003, "p": 0.05, "aucDrop": 0.01, "floor": FLOOR}
CANDS = ["R1", "R1b", "R2", "R3", "R4"]
ADOPTABLE = ["R1", "R2", "R3", "R4"]            # R1b: "reported beside R1, not adopted on its own"
TERM = {"R1": "r1_term", "R1b": "r1b_term", "R4": "r4_term"}
RAW = {"R1": "rise13", "R1b": "log_wsh", "R4": "chg8"}
GATE = {"R1": "condA", "R1b": "condA", "R4": "fresh3"}
EXPECTED = {"R1": -1, "R1b": None, "R4": 1}
LABEL = {"fixed5": "five-signal logistic", "R1": "season state (A)", "R1b": "season state, alternative form (A)", "R2": "recency weighting (A, B)",
         "R3": "calibration map (A, B)", "R4": "overextension at highs (C, B timing)", "R+": "combination of the passing candidates"}
TARGET_WEEKS = {"R1": "condition A weeks", "R1b": "condition A weeks", "R4": "fresh-start weeks (BTC.D within 3 points of its 13-week high)",
                "R2": "A union B weeks", "R3": "A union B weeks"}
TERM_COLS = ["condA", "rise13", "wsh104", "log_wsh", "r1_term", "r1b_term", "fresh3", "chg8", "r4_term", "near52", "hi104", "lo13", "condA_cmc", "r1cmc_term"]
MIN_DRAWS = 50                                  # no p-value or p95 is quotable from fewer draws
ERA_NAMES = [e[0] for e in C.ERAS]
WINDOWS = [("Dec 2019 - Feb 2020", "2019-12-01", "2020-02-29"), ("May 2021 - Jun 2022", "2021-05-01", "2022-06-30")]

_G = {}
_LINES = [0, 0]


def say(s):
    if _LINES[0] < 60:
        print(s, flush=True)
        _LINES[0] += 1
    else:
        _LINES[1] += 1


def rnd(x, d=4):
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return round(v, d) if math.isfinite(v) else None


def fmt(x, d=4):
    v = rnd(x, d)
    return "na" if v is None else f"{v:+.{d}f}"


def clean(o):
    """JSON-safe copy: numpy scalars to Python (floats to 6 significant digits; every criterion is decided on the unrounded
    numbers before this), NaN/inf to None, timestamps to ISO dates."""
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, np.ndarray):
        return [clean(v) for v in o.tolist()]
    if isinstance(o, (bool, np.bool_)):
        return bool(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, (float, np.floating)):
        v = float(o)
        return float(f"{v:.6g}") if math.isfinite(v) else None
    if isinstance(o, pd.Timestamp):
        return str(o.date())
    return o


def tz_strings(ts_utc):
    """(UTC string, US Eastern string) for an aware UTC datetime."""
    try:
        from zoneinfo import ZoneInfo
        est = ts_utc.astimezone(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M %Z")
    except Exception:
        est = (ts_utc - dt.timedelta(hours=5)).strftime("%Y-%m-%d %H:%M EST")
    return ts_utc.strftime("%Y-%m-%d %H:%M UTC"), est


def date_runs(dates, sel):
    """Runs of consecutive selected rows as 'start..end (n)' strings."""
    out = []
    for s, e in C.episodes(np.asarray(sel, float)):
        out.append(f"{dates[s].date()}..{dates[e].date()} ({e - s + 1})")
    return out


# ------------------------------------------------------------------------------------------- conditions and terms
def weekly_cmc(data_dir, index):
    """CoinMarketCap BTC dominance on the weekly index (W-SUN last close), for the robustness diagnostic only."""
    f = os.path.join(data_dir, "BTCD_CMC_1d.csv")
    if not os.path.exists(f):
        return None
    d = pd.read_csv(f)
    s = pd.Series(d["c"].values.astype(float), index=pd.DatetimeIndex(pd.to_datetime(d["ts"], unit="ms")).normalize())
    s = s[~s.index.duplicated()].sort_index()
    daily = s.reindex(pd.date_range(s.index[0], max(s.index[-1], index[-1]), freq="D")).ffill()
    return daily.resample("W-SUN").last().reindex(index)


def weeks_since_high(v, w):
    """Weeks since the most recent bar holding the trailing w-week high (window t-w+1..t, t included)."""
    out = np.full(len(v), np.nan)
    for t in range(len(v)):
        if not np.isfinite(v[t]):
            continue
        lo = max(0, t - w + 1)
        win = v[lo:t + 1]
        j = len(win) - 1 - int(np.nanargmax(win[::-1]))
        out[t] = t - (lo + j)
    return out


def terms(P, cmc=None):
    """The plan's conditions and terms on the weekly panel. Every rolling window ends at t and includes it."""
    b = P["BTC.D"].astype(float)
    T = pd.DataFrame(index=P.index)
    T["btcd"] = b
    T["hi104"] = b.rolling(POST_HI_W, min_periods=1).max()
    T["lo13"] = b.rolling(LOW_W, min_periods=1).min()
    T["condA"] = (b <= T["hi104"] - POST_PTS).astype(float)
    T["rise13"] = b - T["lo13"]
    T["wsh104"] = weeks_since_high(b.values, POST_HI_W)
    T["log_wsh"] = np.log1p(T["wsh104"])
    T["r1_term"] = T["condA"] * T["rise13"]
    T["r1b_term"] = T["condA"] * T["log_wsh"]
    T["hi13"] = b.rolling(FRESH_W, min_periods=1).max()
    T["fresh3"] = C.fresh_mask(P, "W", pts=FRESH_PTS, weeks=FRESH_W).astype(float)
    T["chg8"] = b - b.shift(CHG_W)
    T["r4_term"] = T["fresh3"] * T["chg8"]
    T["hi52"] = b.rolling(NEAR_HI_W, min_periods=1).max()
    T["near52"] = (b >= T["hi52"] - NEAR_PTS).astype(float)
    if cmc is not None:
        T["cmc"] = cmc
        T["cmc_hi104"] = cmc.rolling(POST_HI_W, min_periods=1).max()
        T["condA_cmc"] = (cmc <= T["cmc_hi104"] - POST_PTS).astype(float).where(cmc.notna())
        T["r1cmc_term"] = T["condA_cmc"] * T["rise13"]
    else:
        T["cmc"] = T["cmc_hi104"] = T["condA_cmc"] = T["r1cmc_term"] = np.nan
    return T


def build(D, data_dir, last_complete):
    """The whole point-in-time pipeline from the daily panel (main run and truncation test): weekly panel, harness features
    with the true-ATH btc_dd_ath (study8_honest.ath_drawdown, as rounds 9-10), the conditions and terms (computed on the full
    weekly panel from 2014 so the 104-week windows are full at the 2016-06 cut), targets, and round 10's fall kinds."""
    P_full = C.panel(D, "W")
    X_full, _ = C.features(P_full, "W")
    X_full["btc_dd_ath"] = H.ath_drawdown(data_dir, X_full.index)
    T_full = terms(P_full, weekly_cmc(data_dir, P_full.index))
    keep = (X_full.index >= pd.Timestamp(DATA_CUT)) & (X_full.index <= last_complete)
    P, X, T = P_full[keep], X_full[keep], T_full[keep]
    Y = C.targets(P, "W")
    K, _ = S10.kind_targets(P, Y)
    F = pd.concat([X[SIGNALS], T], axis=1)
    return P, Y, K, F


# ------------------------------------------------------------------------------------------- models
def walk_forward_t(X, y, fit, predict, freq="W", start=WF_START, refit_weeks=REFIT_W, label_lag_weeks=LAG_W, min_train=MIN_TRAIN):
    """study8_common.walk_forward line for line, except that fit also receives the training positions and the refit
    position t (R2's ages are measured from t). Identity with the harness is checked in leakage.walkForwardIdentity."""
    idx = X.index
    Xv = X.values.astype(float)
    yv = np.asarray(y, float)
    pred = pd.Series(np.nan, index=idx)
    step, lag = C.bars(refit_weeks, freq), C.bars(label_lag_weeks, freq)
    t = int(np.searchsorted(idx, pd.Timestamp(start)))
    refits = []
    while t < len(idx):
        tr = np.arange(0, max(0, t - lag))
        tr = tr[np.isfinite(yv[tr]) & np.isfinite(Xv[tr]).all(1)]
        te_end = min(t + step, len(idx))
        if len(tr) >= min_train:
            model = fit(Xv[tr], yv[tr], tr, t)
            te = np.arange(t, te_end)
            ok = te[np.isfinite(Xv[te]).all(1)]
            if len(ok):
                p = np.asarray(predict(model, Xv[:te_end], ok), float)
                pred.iloc[ok] = p
            refits.append({"t": str(idx[t].date()), "nTrain": int(len(tr))})
        t = te_end
    return pred, refits


def logistic_fit_w(Xz, y, sw, lam=1.0, it=25):
    """study8_common.logistic_fit with per-row sample weights in the log likelihood (penalty unchanged); sw = 1 reproduces it."""
    A = np.c_[np.ones(len(Xz)), Xz]
    w = np.zeros(A.shape[1])
    reg = lam * np.diag(np.r_[0, np.ones(A.shape[1] - 1)])
    for _ in range(it):
        p = 1 / (1 + np.exp(-A @ w))
        g = A.T @ (sw * (p - y)) + reg @ w
        Hs = (A * (sw * p * (1 - p))[:, None]).T @ A + reg
        w -= np.linalg.solve(Hs + 1e-6 * np.eye(len(w)), g)
    return w


def run_r2(F, y, cols=SIGNALS, perm_seed=None, normalize=False, keep=None, age_log=None):
    """R2: the harness logistic with sample weights 0.5 ** (age / 156), age = refit position minus row position in weeks.
    perm_seed: placebo, ages randomly permuted among the training rows at every refit. normalize: diagnostic, weights / mean."""
    rng = None if perm_seed is None else np.random.default_rng(perm_seed)

    def fit(Xtr, ytr, tr, t):
        age = (t - tr).astype(float)
        if age_log is not None:
            age_log.append({"t": int(t), "minAge": float(age.min()), "maxAge": float(age.max()), "n": int(len(age))})
        if rng is not None:
            age = rng.permutation(age)
        sw = 0.5 ** (age / HALF_LIFE_W)
        if normalize:
            sw = sw / sw.mean()
        mu, sd = C.zfit(Xtr)
        w = logistic_fit_w(C.zapply(Xtr, mu, sd), ytr, sw)
        if keep is not None:
            keep.append((mu, sd, w))
        return (mu, sd, w)

    def predict(m, Xh, te):
        mu, sd, w = m
        return C.logistic_predict(C.zapply(Xh[te], mu, sd), w)
    return walk_forward_t(F[cols], y, fit, predict)


def logit_p(p):
    p = np.clip(np.asarray(p, float), 1e-9, 1 - 1e-9)
    return np.log(p / (1 - p))


def run_r3(base_pred, y, shuffle_seed=None, keep=None, lam=1.0, label_lag=LAG_W):
    """R3: the harness walk-forward over the base model's own out-of-sample predictions: at each of the harness refit dates t
    (fixed5's refit dates) the map logit p' = a + b logit p is fitted (the harness logistic, lam 1, on the z-scored logit with
    NO clip, so the map is strictly monotone) on the rows s < t - 26 (labels known at t) that carry a prediction; active from
    the first refit date with >= 52 such rows (min_train); the base prediction is kept where the map is not active.
    shuffle_seed: placebo, the past predictions shuffled in time against their labels at every refit."""
    rng = None if shuffle_seed is None else np.random.default_rng(shuffle_seed)
    Xc = pd.DataFrame({"logit": logit_p(base_pred.values)}, index=base_pred.index).where(base_pred.notna())

    def fit(Xtr, ytr):
        x = Xtr[:, :1].copy()
        if rng is not None:
            x = x[rng.permutation(len(x))]
        mu, sd = C.zfit(x)
        w = C.logistic_fit(C.zapply(x, mu, sd, clip=np.inf), ytr, lam=lam)
        if keep is not None:
            keep.append({"mu": float(mu[0]), "sd": float(sd[0]), "w": w, "n": int(len(x))})
        return (mu, sd, w)

    def predict(m, Xh, te):
        mu, sd, w = m
        return C.logistic_predict(C.zapply(Xh[te], mu, sd, clip=np.inf), w)
    pred, refits = C.walk_forward(Xc, y, fit, predict, freq="W", label_lag_weeks=label_lag, min_train=R3_MIN)
    return pred.where(pred.notna(), base_pred), refits, pred.notna()


def r3_map(m):
    """(a, b) of logit p' = a + b logit p from a stored R3 fit."""
    w = m["w"]
    return float(w[0] - w[1] * m["mu"] / m["sd"]), float(w[1] / m["sd"])


def run_plus(F, Y, comps, seg_start=None, seed=None, keep=None):
    """R+: fixed5 + the terms of the passing gated candidates (R1, R4), fitted with R2's weights if R2 passed, mapped by R3
    (fitted on the combined model's own earlier out-of-sample predictions) if R3 passed. With seed, every component is
    replaced by its own placebo inside one draw (the joint placebo)."""
    y = Y[TARGET]
    rng = None if seed is None else np.random.default_rng(seed)
    Fp, cols = (F if rng is None else F[SIGNALS].copy()), list(SIGNALS)
    for c in comps:
        if c not in TERM:
            continue
        if rng is None:
            cols.append(TERM[c])
        else:
            nm = "placebo_" + c
            Fp[nm] = placebo_gate(F[GATE[c]].values, seg_start, rng) * F[RAW[c]].values
            cols.append(nm)
    km = None if keep is None else keep.setdefault("base", [])
    if "R2" in comps:
        base, refits = run_r2(Fp, y, cols=cols, perm_seed=(None if rng is None else int(rng.integers(1 << 31))), keep=km)
    else:
        base, refits = S9.run_spec(Fp, Y, cols, keep_models=km)
    if "R3" in comps:
        k3 = None if keep is None else keep.setdefault("map", [])
        out, _, _ = run_r3(base, y, shuffle_seed=(None if rng is None else int(rng.integers(1 << 31))), keep=k3)
        return out, refits
    return base, refits


def model_preds(F, Y, names, plus=None, keep=None):
    """Out-of-sample predictions of fixed5 and the named models on the labels in Y (the real ones or a shifted copy)."""
    y = Y[TARGET]
    out, refits = {}, {}

    def km(n, factory=list):
        if keep is None:
            return None
        keep[n] = factory()
        return keep[n]
    out["fixed5"], refits["fixed5"] = S9.run_spec(F, Y, SIGNALS, keep_models=km("fixed5"))
    for n in names:
        if n in TERM:
            out[n], refits[n] = S9.run_spec(F, Y, SIGNALS + [TERM[n]], keep_models=km(n))
        elif n == "R2":
            out[n], refits[n] = run_r2(F, y, keep=km(n))
        elif n == "R3":
            out[n], refits[n], _ = run_r3(out["fixed5"], y, keep=km(n))
        elif n == "R+":
            out[n], refits[n] = run_plus(F, Y, plus, keep=km(n, dict))
    return out, refits


# ------------------------------------------------------------------------------------------- placebo blocks
def runs_of(mask):
    """Run lengths of True in a boolean array."""
    out, n = [], 0
    for v in np.asarray(mask, bool):
        if v:
            n += 1
        elif n:
            out.append(n)
            n = 0
    if n:
        out.append(n)
    return out


def place_blocks(lengths, N, rng):
    """The blocks (given lengths) in random order at random non-overlapping positions in N weeks: the N - sum(lengths) gap
    weeks are split into len + 1 gaps uniformly over all compositions. Uses the lengths and N only."""
    k, L = len(lengths), int(sum(lengths))
    out = np.zeros(N, bool)
    if k == 0:
        return out
    G = N - L
    order = rng.permutation(k)
    cuts = np.sort(rng.choice(G + k, size=k, replace=False))
    gaps = np.diff(np.r_[-1, cuts, G + k]) - 1
    pos = int(gaps[0])
    for j, g in zip(order, gaps[1:]):
        out[pos:pos + lengths[j]] = True
        pos += lengths[j] + int(g)
    return out


def placebo_gate(gate, seg_start, rng, oos_only=False):
    """The condition replaced by random blocks of its own run lengths: inside the out-of-sample weeks (seg_start..end) and,
    separately, inside the earlier training weeks (0..seg_start), so each segment keeps its total length and the fitted
    coefficient never sees the real condition. oos_only (diagnostic): the training weeks keep the real condition. The only
    inputs are the condition and the segment boundary: no label, no prediction."""
    g = np.nan_to_num(np.asarray(gate, float)) > 0
    out = g.copy()
    segs = [(seg_start, len(g))] if oos_only else [(0, seg_start), (seg_start, len(g))]
    for a, z in segs:
        out[a:z] = place_blocks(runs_of(g[a:z]), z - a, rng)
    return out.astype(float)


def shifted_column(term, gate, seg_start, rng, min_shift=26):
    """Term-preserving placebo (diagnostic): the gated column (gate x term) and its gate circularly shifted together inside
    each segment (the earlier training weeks and the out-of-sample weeks) by k uniform in [26, len - 26), so the run lengths,
    the total length and the term values on the gated weeks all travel together. No label, no prediction."""
    col = np.nan_to_num(np.asarray(term, float))
    g = np.nan_to_num(np.asarray(gate, float)) > 0
    oc, og = col.copy(), g.copy()
    for a, z in ((0, seg_start), (seg_start, len(col))):
        if z - a > 2 * min_shift:
            k = int(rng.integers(min_shift, (z - a) - min_shift))
            oc[a:z] = np.roll(col[a:z], k)
            og[a:z] = np.roll(g[a:z], k)
    return oc, og.astype(float)


def placebo_pred(cand, seed, variant="segments", comps=None):
    """One placebo draw: (predictions, the placebo gate and the placebo column for a gated candidate, or None, None)."""
    F, Y = _G["F"], _G["Y"]
    rng = np.random.default_rng(seed)
    if cand in TERM:
        if variant == "termPreserving":
            col, g = shifted_column(F[TERM[cand]].values, F[GATE[cand]].values, _G["segStart"], rng)
        else:
            g = placebo_gate(F[GATE[cand]].values, _G["segStart"], rng, oos_only=(variant == "oosOnly"))
            col = g * F[RAW[cand]].values
        Fp = F[SIGNALS].copy()
        Fp["placebo"] = col
        return S9.run_spec(Fp, Y, SIGNALS + ["placebo"])[0], g, np.asarray(col, float)
    if cand == "R2":
        return run_r2(F, Y[TARGET], perm_seed=seed)[0], None, None
    if cand == "R3":
        return run_r3(_G["p5"], Y[TARGET], shuffle_seed=seed)[0], None, None
    return run_plus(F, Y, comps, seg_start=_G["segStart"], seed=seed)[0], None, None


def own_gate_stats(p, d, own):
    """Diagnostic for a placebo draw of a gated candidate: criterion (iii) judged on the draw's OWN gate (inside = its
    placebo-gated labelled weeks, block q05 from the shared 26-week block draws) and criterion (v), with the registered bars."""
    yv, pf, IB = _G["yv"], _G["pf"], _G["IB"]
    n_in = int(own.sum())
    row = {"scoredGatedWeeks": n_in}
    if n_in == 0 or n_in == len(own):
        row.update({"iii": None, "v": None})
        return row
    s = own.astype(float)
    den = s[IB].sum(1)
    v = (d * s)[IB].sum(1) / np.maximum(den, 1e-12)
    v = v[den > 0]
    q05 = float(np.quantile(v, 0.05)) if len(v) else None
    ins, out = float(d[own].mean()), float(d[~own].mean())
    fall = yv == 1
    a1, a0 = C.auc(p, yv), C.auc(pf, yv)
    v_ok = bool((p[fall] < FLOOR).sum() == 0 and a1 is not None and a0 is not None and a1 - a0 >= -CRIT["aucDrop"])
    row.update({"inside": ins, "outside": out, "insideQ05": q05,
                "iii": bool(ins >= CRIT["inside"] and q05 is not None and q05 > 0 and out >= CRIT["outside"]), "v": v_ok})
    return row


# ------------------------------------------------------------------------------------------- forked workers
def _job(args):
    kind = args[0]
    out = []
    if kind == "shift":
        _, ks, names, plus = args
        F, Y, lab = _G["F"], _G["Y"], _G["lab"]
        for k in ks:
            Ys = C.shift_targets(Y[[TARGET]], int(k))
            preds, _ = model_preds(F, Ys, names, plus)
            ys = Ys[TARGET]
            # a draw scores the LABELLED common rows (the rows the real statistic uses; the 26 unlabelled tail weeks can receive
            # a rolled label and are left out) where the shifted label exists AND every model forecasts: the rolled 26-week block
            # of unknown labels can land in the first training window and leave the first refit below min_train
            m = np.array((lab & ys.notna()).to_numpy(), dtype=bool, copy=True)   # pandas copy-on-write hands out read-only arrays
            for n in ["fixed5"] + list(names):
                m &= np.isfinite(preds[n].values)
            yv = ys.values[m]
            bf = (preds["fixed5"].values[m] - yv) ** 2
            row = {"k": int(k), "rows": int(m.sum())}
            for n in names:
                row[n] = (float(np.mean(bf - (preds[n].values[m] - yv) ** 2)) if m.any() else None)
            out.append(row)
    elif kind == "placebo":
        _, cand, seeds, variant, comps, tgt = args
        lab, yv, bf = _G["labv"], _G["yv"], _G["bf5"]
        tgt = _G["targets"].get(cand) if tgt is None else tgt
        for seed in seeds:
            pser, g, col = placebo_pred(cand, int(seed), variant, comps)
            p = pser.values[lab]
            d = bf - (p - yv) ** 2
            row = {"seed": int(seed), "pooled": float(d.mean()), "inside": (float(d[tgt].mean()) if tgt is not None and tgt.any() else None)}
            if g is not None:
                own = np.asarray(g, float)[lab] > 0
                row["own"] = own_gate_stats(p, d, own)
                row["own"]["meanTerm"] = (float(np.nanmean(col[lab][own])) if own.any() else None)
            out.append(row)
    elif kind == "trunc":
        _, cuts = args
        F, Y, preds, csv = _G["F"], _G["Y"], _G["preds"], _G["csv"]
        for cut in cuts:
            cut = pd.Timestamp(cut)
            lim = (cut + pd.Timedelta(days=1)).value // 10 ** 6       # bars up to Monday 00:00 UTC after the cut (as the live data ends)
            with tempfile.TemporaryDirectory(prefix="study13_trunc_") as tmp:
                for fn, df in csv.items():
                    df[df["ts"] <= lim].to_csv(os.path.join(tmp, fn), index=False)
                Dc = C.load_daily(tmp)
                su = C.panel(Dc, "W").index
                lc = su[su < Dc.index[-1]][-1]                         # the last complete week, exactly as main() reads it
                _, Yc, _, Fc = build(Dc, tmp, lc)
            row = {"cut": str(cut.date()), "lastCompleteWeekFromCutFiles": str(lc.date()), "cutMatches": bool(lc == cut), "rows": int(len(Fc))}
            cols = [c for c in TERM_COLS + SIGNALS if c in Fc.columns]
            a, b = Fc[cols].values.astype(float), F.loc[Fc.index, cols].values.astype(float)   # every row up to the cut
            both = np.isfinite(a) & np.isfinite(b)
            row["termsMaxAbsDiff"] = float(np.max(np.abs(a[both] - b[both]))) if both.any() else 0.0
            row["termsFiniteMismatch"] = int((np.isfinite(a) != np.isfinite(b)).sum())
            sa, sb = Fc[SIGNALS].values.astype(float), F.loc[Fc.index, SIGNALS].values.astype(float)
            sboth = np.isfinite(sa) & np.isfinite(sb)
            row["signalsMaxAbsDiff"] = {c: (float(np.max(np.abs(sa[sboth[:, j], j] - sb[sboth[:, j], j]))) if sboth[:, j].any() else 0.0) for j, c in enumerate(SIGNALS)}
            yc, yf = Yc[TARGET], Y[TARGET].reindex(Yc.index)
            kn = yc.notna()
            row["labelsMaxAbsDiff"] = float((yc[kn] - yf[kn]).abs().max()) if kn.any() else 0.0
            row["labelsUnknownAtCut"] = int(yc.isna().sum())
            pc, _ = model_preds(Fc, Yc, CANDS)
            worst, worst_cut = 0.0, 0.0
            for n in ["fixed5"] + CANDS:
                full = preds[n].reindex(pc[n].index)
                bb = pc[n].notna() & full.notna()
                if bb.any():
                    worst = max(worst, float((pc[n][bb] - full[bb]).abs().max()))
                if np.isfinite(pc[n].iloc[-1]) and np.isfinite(full.iloc[-1]):
                    worst_cut = max(worst_cut, abs(float(pc[n].iloc[-1]) - float(full.iloc[-1])))
                row.setdefault("finiteMismatch", 0)
                row["finiteMismatch"] += int((pc[n].notna() != full.notna()).sum())
            row["predsMaxAbsDiff"], row["predsAtCutMaxAbsDiff"] = worst, worst_cut
            out.append(row)
    return out


def run_jobs(pool, jobs):
    res = pool.map(_job, jobs) if pool else [_job(j) for j in jobs]
    return [r for part in res for r in part]


def chunks(items, k):
    k = max(1, min(k, len(items)))
    return [items[i::k] for i in range(k)]


# ------------------------------------------------------------------------------------------- scores and bootstraps
def brier_rows(p, y):
    return (np.asarray(p, float) - y) ** 2


def logloss_rows(p, y):
    p = np.clip(np.asarray(p, float), LL_EPS, 1 - LL_EPS)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def era_sel(dates, era):
    return (dates >= pd.Timestamp(era[1])) & (dates < pd.Timestamp(era[2]))


def block_draws(N, n, rng, bl=26):
    """Circular 26-week block bootstrap index draws (n x N), as study8_honest.paired_block_boot draws them."""
    if N == 0:
        return np.zeros((n, 0), int)
    nb = int(np.ceil(N / bl))
    starts = rng.integers(0, N, size=(n, nb))
    ii = (starts[:, :, None] + np.arange(bl)[None, None, :]) % N
    return ii.reshape(n, -1)[:, :N]


def episode_draws(yv, n, rng, runup=26):
    """Episode bootstrap index draws: blocks = each positive label episode with its 26-week run-up, and the stretches
    between (study8_common.episode_boot / study8_tda_sig.paired_episode_boot), resampled with replacement."""
    N = len(yv)
    cuts = [0]
    for s, e in C.episodes(yv):
        cuts += [max(0, s - runup), e + 1]
    cuts = sorted(set(c for c in cuts if 0 <= c <= N)) + [N]
    blocks = [np.arange(a, z) for a, z in zip(cuts[:-1], cuts[1:]) if z > a]
    if not blocks:
        return [], 0
    return [np.concatenate([blocks[k] for k in rng.integers(0, len(blocks), size=len(blocks))]) for _ in range(n)], len(blocks)


def qstats(v):
    v = np.asarray(v, float)
    v = v[np.isfinite(v)]
    if not len(v):
        return {"n": 0}
    return {"n": int(len(v)), "q05": float(np.quantile(v, 0.05)), "q50": float(np.quantile(v, 0.5)), "q95": float(np.quantile(v, 0.95)), "pLE0": float((v <= 0).mean())}


def boot_mean(d, sel, IB, ED):
    """Block and episode bootstrap of the mean of d over the selected rows (the selection travels with its rows)."""
    s = np.asarray(sel, float)
    num, den = (d * s)[IB].sum(1), s[IB].sum(1)
    vb = np.where(den > 0, num / np.maximum(den, 1e-12), np.nan)
    ve = []
    for ii in ED:
        dd = s[ii].sum()
        ve.append((d[ii] * s[ii]).sum() / dd if dd > 0 else np.nan)
    return qstats(vb), qstats(ve)


def oos_scores(p, yv, dates):
    out = {}
    for name, fr, to in list(C.ERAS) + [("pooled", "2000-01-01", "2100-01-01")]:
        m = era_sel(dates, (name, fr, to))
        if m.sum() < 20:
            continue
        out[name] = {"n": int(m.sum()), "positives": int(yv[m].sum()), "base": rnd(yv[m].mean()), "auc": rnd(C.auc(p[m], yv[m])),
                     "brier": rnd(brier_rows(p[m], yv[m]).mean()), "logloss": rnd(logloss_rows(p[m], yv[m]).mean())}
    return out


def paired(pc, ctx):
    """Paired improvements over fixed5 (fixed5 minus candidate: positive = better) of Brier and log loss, pooled and per era,
    with the 26-week block and the episode bootstrap; the pooled AUC difference with its block band (diagnostic)."""
    yv, pf = ctx["yv"], ctx["pf"]
    out = {}
    for metric, fn in (("brier", brier_rows), ("logloss", logloss_rows)):
        d = fn(pf, yv) - fn(pc, yv)
        blk, epi = boot_mean(d, np.ones(len(d), bool), ctx["IB"], ctx["ED"])
        out.setdefault("pooled", {})[metric] = {"fixed5": float(fn(pf, yv).mean()), "candidate": float(fn(pc, yv).mean()), "improvement": float(d.mean()), "block": blk, "episode": epi}
        for e in ERA_NAMES:
            s, IBe, EDe = ctx["eraDraws"][e]
            de = d[s]
            vb = de[IBe].mean(1) if len(de) else np.array([])
            ve = [de[ii].mean() for ii in EDe]
            out.setdefault(e, {})[metric] = {"n": int(s.sum()), "fixed5": float(fn(pf[s], yv[s]).mean()), "candidate": float(fn(pc[s], yv[s]).mean()),
                                            "improvement": float(de.mean()), "block": qstats(vb), "episode": qstats(ve)}
    af, ac = C.auc(pf, yv), C.auc(pc, yv)
    vals = []
    for ii in ctx["IB"][:ctx["nAucBoot"]]:
        a1, a0 = C.auc(pc[ii], yv[ii]), C.auc(pf[ii], yv[ii])
        if a1 is not None and a0 is not None:
            vals.append(a1 - a0)
    out["pooled"]["auc"] = {"fixed5": af, "candidate": ac, "change": ac - af, "block": qstats(vals)}
    return out


def inside_outside(pc, ctx, sel):
    yv, pf = ctx["yv"], ctx["pf"]
    d = brier_rows(pf, yv) - brier_rows(pc, yv)
    res = {}
    for side, s in (("inside", sel), ("outside", ~sel)):
        blk, epi = boot_mean(d, s, ctx["IB"], ctx["ED"])
        res[side] = {"n": int(s.sum()), "positives": int(yv[s].sum()), "brierFixed5": float(brier_rows(pf[s], yv[s]).mean()) if s.any() else None,
                     "brierCandidate": float(brier_rows(pc[s], yv[s]).mean()) if s.any() else None, "improvement": float(d[s].mean()) if s.any() else None,
                     "block": blk, "episode": epi}
    return res


def run_loo(d, sel, dates, cap=24, ED=None):
    """The skeptic's check: the pooled and the inside improvement with each run of target weeks removed in turn; with ED,
    the share of episode-bootstrap draws that hold no week of the longest run (the draws that 'drop' it) and the inside
    improvement over those draws."""
    rows = []
    for s, e in C.episodes(np.asarray(sel, float)):
        keep = np.ones(len(d), bool)
        keep[s:e + 1] = False
        ins = keep & sel
        rows.append({"run": f"{dates[s].date()}..{dates[e].date()}", "weeks": int(e - s + 1), "pooledWithout": rnd(d[keep].mean(), 5),
                     "insideWithout": (rnd(d[ins].mean(), 5) if ins.any() else None), "insideOfRun": rnd(d[s:e + 1].mean(), 5)})
    rows.sort(key=lambda r: -r["weeks"])
    vals = [r["pooledWithout"] for r in rows if r["pooledWithout"] is not None]
    ivals = [r["insideWithout"] for r in rows if r["insideWithout"] is not None]
    out = {"nRuns": len(rows), "minPooledWithout": (min(vals) if vals else None), "minInsideWithout": (min(ivals) if ivals else None), "runs": rows[:cap],
           "runsListed": min(cap, len(rows))}
    eps_sel = C.episodes(np.asarray(sel, float))
    if ED and eps_sel:
        s0, e0 = max(eps_sel, key=lambda r: r[1] - r[0])
        drop, ins = 0, []
        for ii in ED:
            if not ((ii >= s0) & (ii <= e0)).any():
                drop += 1
                m = np.asarray(sel)[ii]
                if m.any():
                    ins.append(float(d[ii][m].mean()))
        out["episodeBootstrapWithoutLongestRun"] = {"run": f"{dates[s0].date()}..{dates[e0].date()}", "shareOfDraws": round(drop / len(ED), 3),
                                                    "insideImprovementInThoseDraws": qstats(ins)}
    return out


def run_boot(d, sel, dates, n, rng):
    """The skeptic's bootstrap: blocks = the runs of target weeks and the stretches between them (on the labelled common
    rows), resampled with replacement, so a draw drops a whole post-season run with the frequency its share of the blocks
    implies. Diagnostic beside the registered block and episode bootstraps."""
    sel = np.asarray(sel, bool)
    if not sel.any() or sel.all():
        return {"n": 0, "note": "the target covers no row or every row"}
    cuts = [0] + [i for i in range(1, len(sel)) if sel[i] != sel[i - 1]] + [len(sel)]
    blocks = [np.arange(a, z) for a, z in zip(cuts[:-1], cuts[1:])]
    runs = [b for b in blocks if sel[b[0]]]
    longest = max(runs, key=len)
    pooled, inside, drop = [], [], 0
    for _ in range(n):
        ii = np.concatenate([blocks[k] for k in rng.integers(0, len(blocks), size=len(blocks))])
        pooled.append(float(d[ii].mean()))
        m = sel[ii]
        inside.append(float(d[ii][m].mean()) if m.any() else np.nan)
        drop += int(not np.isin(longest, ii).any())
    return {"blocks": len(blocks), "targetRuns": len(runs), "longestRun": f"{dates[longest[0]].date()}..{dates[longest[-1]].date()} ({len(longest)})",
            "shareOfDrawsWithoutLongestRun": round(drop / n, 3), "pooled": qstats(pooled), "inside": qstats(inside)}


# ------------------------------------------------------------------------------------------- diagnostics beside the plan
def episode_blocks(yv, runup=26):
    """The episode bootstrap's blocks (episode_draws' cut, returned instead of resampled)."""
    N = len(yv)
    cuts = [0]
    for s, e in C.episodes(yv):
        cuts += [max(0, s - runup), e + 1]
    cuts = sorted(set(c for c in cuts if 0 <= c <= N)) + [N]
    return [np.arange(a, z) for a, z in zip(cuts[:-1], cuts[1:]) if z > a]


def longest_run(sel):
    eps = C.episodes(np.asarray(sel, float))
    return max(eps, key=lambda r: r[1] - r[0]) if eps else None


def episode_band_note(sel, yv, dates):
    """How many episode-bootstrap blocks the longest run of target weeks spans, and the chance that one draw holds none of them."""
    lr = longest_run(sel)
    if lr is None:
        return {"note": "no target weeks"}
    blocks = episode_blocks(yv)
    s0, e0 = lr
    k = sum(1 for b in blocks if ((b >= s0) & (b <= e0)).any())
    nb = len(blocks)
    return {"longestTargetRun": f"{dates[s0].date()}..{dates[e0].date()} ({e0 - s0 + 1})", "episodeBlocks": nb, "blocksTouchingLongestRun": k,
            "probabilityADrawHoldsNoneOfThem": float(((nb - k) / nb) ** nb) if nb else None}


def iii_eval(io):
    """Criterion (iii) with the registered bars on any inside/outside split (used for the labelled outcome-free diagnostics)."""
    ins, ous = io["inside"], io["outside"]
    iq = ins["block"].get("q05")
    ok = bool(ins["improvement"] is not None and ins["improvement"] >= CRIT["inside"] and iq is not None and iq > 0 and ous["improvement"] is not None
              and ous["improvement"] >= CRIT["outside"])
    fail = []
    if not (ins["improvement"] is not None and ins["improvement"] >= CRIT["inside"]):
        fail.append("inside below +0.01")
    if not (iq is not None and iq > 0):
        fail.append("inside block q05 <= 0")
    if not (ous["improvement"] is not None and ous["improvement"] >= CRIT["outside"]):
        fail.append("outside below -0.003")
    return {"status": "pass" if ok else "fail", "inside": ins["improvement"], "insideBlockQ05": iq, "nInside": ins["n"], "outside": ous["improvement"],
            "outsideBlockQ05": ous["block"].get("q05"), "nOutside": ous["n"], "failsOn": fail}


def outcome_free_iii(pc, ctx, sets):
    """(iii) on the two outcome-free targets beside the registered A union B: A union B' (B' = fixed5 p > 0.5 near the 52-week high,
    no outcome) and A alone."""
    return {k: iii_eval(inside_outside(pc, ctx, s)) for k, s in (("AunionBprime", sets["AuBfree"]), ("Aalone", sets["A"]))}


def share_clearing(d, sel, IB, ED, thr):
    """Share of block and episode bootstrap draws whose mean of d over the selected rows is at least thr."""
    s = np.asarray(sel, float)
    den = s[IB].sum(1)
    vb = ((d * s)[IB].sum(1) / np.maximum(den, 1e-12))[den > 0]
    ve = [float((d[ii] * s[ii]).sum() / s[ii].sum()) for ii in ED if s[ii].sum() > 0]
    return {"block": (round(float(np.mean(vb >= thr)), 3) if len(vb) else None), "episode": (round(float(np.mean(np.array(ve) >= thr)), 3) if ve else None),
            "threshold": thr}


def spillover(pc, pf, yv, sel, dates):
    """How far a candidate moves the forecasts inside and outside its target weeks, and the outside Brier change by era and label."""
    dp = pc - pf
    d = brier_rows(pf, yv) - brier_rows(pc, yv)
    out = ~sel
    res = {"meanAbsDeltaPInside": (float(np.abs(dp[sel]).mean()) if sel.any() else None), "meanAbsDeltaPOutside": (float(np.abs(dp[out]).mean()) if out.any() else None),
           "meanDeltaPOutside": (float(dp[out].mean()) if out.any() else None),
           "outsideBrierChangeByEra": {e[0]: (float(d[out & era_sel(dates, e)].mean()) if (out & era_sel(dates, e)).any() else None) for e in C.ERAS},
           "outsideBrierChangeByLabel": {"fall": (float(d[out & (yv == 1)].mean()) if (out & (yv == 1)).any() else None),
                                         "noFall": (float(d[out & (yv == 0)].mean()) if (out & (yv == 0)).any() else None)},
           "byEraSplit": {e[0]: {"all": float(d[era_sel(dates, e)].mean()), "inside": (float(d[sel & era_sel(dates, e)].mean()) if (sel & era_sel(dates, e)).any() else None),
                                 "nInside": int((sel & era_sel(dates, e)).sum()), "outside": (float(d[out & era_sel(dates, e)].mean()) if (out & era_sel(dates, e)).any() else None),
                                 "nOutside": int((out & era_sel(dates, e)).sum())} for e in C.ERAS}}
    return res


def seen_split(d, sel, dates, idx, refit_dates, lag=LAG_W):
    """The longest run of target weeks split by whether the refit in force had any week of that run among its training rows
    (row positions s < t - lag, labels known at t): what the out-of-sample gain was earned with."""
    lr = longest_run(sel)
    if lr is None or not refit_dates:
        return None
    s0, e0 = lr
    rd = [pd.Timestamp(t) for t in refit_dates]
    run_start_pos = int(np.searchsorted(idx, dates[s0]))
    seen = np.zeros(len(dates), bool)
    for i in range(s0, e0 + 1):
        inforce = [t for t in rd if t <= dates[i]]
        if not inforce:
            continue
        ti = int(np.searchsorted(idx, inforce[-1]))
        seen[i] = run_start_pos < ti - lag
    run = np.zeros(len(dates), bool)
    run[s0:e0 + 1] = True
    out = {"run": f"{dates[s0].date()}..{dates[e0].date()} ({e0 - s0 + 1})"}
    for k, m in (("refitHadSeenNoWeekOfTheRun", run & ~seen), ("refitHadSeenPartOfTheRun", run & seen)):
        out[k] = ({"n": int(m.sum()), "from": str(dates[m][0].date()), "to": str(dates[m][-1].date()), "insideImprovement": float(d[m].mean())} if m.any() else {"n": 0})
    return out


def pending_standdown(p, pf5, y, mask, btcd, tl):
    """Diagnostic beside (v): (v) counts labelled fall weeks only, so it cannot see the last 26 common weeks, whose label is
    still pending. Weeks below 2% there, the run of weeks below 2% that ends at the last complete week, today's act/stand-down
    against fixed5's, and whether a 5-point fall has already been observed after any pending week (a label already known to be 1)."""
    m = mask.values
    tail = m & y.isna().values
    pv, fv, b = p.values, pf5.values, btcd.values
    below = tail & (pv < FLOOR)
    run, cur = 0, np.where(m)[0]
    for i in cur[::-1]:
        if pv[i] < FLOOR:
            run += 1
        else:
            break
    seen_fall = np.zeros(len(pv), bool)
    for i in np.where(tail)[0]:
        fut = b[i + 1:i + 1 + C.bars(26, "W")]
        seen_fall[i] = bool(len(fut) and np.nanmin(fut) <= b[i] - 5.0)
    pt, ft = float(p.loc[tl]), float(pf5.loc[tl])
    return {"pendingWeeks": int(tail.sum()), "weeksBelow2pct": int(below.sum()), "fixed5WeeksBelow2pct": int((tail & (fv < FLOOR)).sum()),
            "minP": (rnd(np.nanmin(pv[tail])) if tail.any() else None), "fixed5MinP": (rnd(np.nanmin(fv[tail])) if tail.any() else None),
            "runsBelow2pct": date_runs(p.index, below), "currentRunBelow2pctWeeks": int(run),
            "today": {"asOf": str(tl.date()), "candidate": rnd(pt), "fixed5": rnd(ft), "act50Candidate": bool(pt >= FLOOR), "act50Fixed5": bool(ft >= FLOOR),
                      "flipsFixed5Decision": bool((pt >= FLOOR) != (ft >= FLOOR))},
            "pendingWeeksWithAFallAlreadyObserved": int(seen_fall.sum()), "belowWeeksWithAFallAlreadyObserved": int((seen_fall & below).sum()),
            "what": "labelled diagnostic beside (v), not a verdict input: the unlabelled tail of the common rows, where (v) cannot look"}


def offset_fit(x, y, it=50):
    """Maximum-likelihood intercept c of logit p' = x + c (no penalty)."""
    c = 0.0
    for _ in range(it):
        p = 1 / (1 + np.exp(-(x + c)))
        h = float(np.sum(p * (1 - p))) + 1e-9
        c -= float(np.sum(p - y)) / h
    return c


def run_r3_variant(base_pred, y, kind, lam=None, train_ok=None):
    """One-parameter recalibrations of fixed5 on R3's own schedule (the walk-forward over fixed5's out-of-sample logits: label
    lag 26, fixed5's refit dates, min_train 52; fixed5 kept where not active). Diagnostics, not candidates:
      intercept   logit p' = logit p + c, c by maximum likelihood on the calibration rows;
      shrinkCal   p' = (1 - l) p + l base_cal, l fitted by least squares on the calibration rows (base_cal = their label mean);
      shrinkTrain p' = (1 - lam) p + lam base_train, base_train = the label mean of fixed5's training rows at t (positions s < t - 26
                  with a known label and, through train_ok, finite fixed5 inputs)."""
    Xc = pd.DataFrame({"logit": logit_p(base_pred.values)}, index=base_pred.index).where(base_pred.notna())
    yv_all = np.asarray(y, float)

    def fit(Xtr, ytr, tr, t):
        x = Xtr[:, 0]
        if kind == "intercept":
            return ("intercept", offset_fit(x, ytr))
        if kind == "shrinkCal":
            pp = 1 / (1 + np.exp(-x))
            base = float(ytr.mean())
            dl = base - pp
            ll_ = float(np.clip(np.sum((ytr - pp) * dl) / max(float(np.sum(dl ** 2)), 1e-12), 0.0, 1.0))
            return ("shrink", ll_, base)
        kk = np.arange(0, max(0, t - C.bars(LAG_W, "W")))
        kk = kk[np.isfinite(yv_all[kk]) & (True if train_ok is None else train_ok[kk])]
        return ("shrink", float(lam), float(yv_all[kk].mean()) if len(kk) else np.nan)

    def predict(m, Xh, te):
        x = Xh[te, 0]
        if m[0] == "intercept":
            return 1 / (1 + np.exp(-(x + m[1])))
        return (1 - m[1]) * (1 / (1 + np.exp(-x))) + m[1] * m[2]
    pred, refits = walk_forward_t(Xc, y, fit, predict, min_train=R3_MIN)
    return pred.where(pred.notna(), base_pred), refits


def gate_identification(n, F, y, keep, refits, idx):
    """For a gated candidate: the gate's rows in each refit's training set (by run of the gate over the whole panel), the raw
    term's correlation with the label inside each long run, the share of the term's variance inside the gate that the five
    signals explain, and the refits where the term's sign changed while the gate rows in training did not."""
    g = np.nan_to_num(F[GATE[n]].values) > 0
    raw = F[RAW[n]].values.astype(float)
    yv_all = y.values.astype(float)
    runs = C.episodes(g.astype(float))
    long_runs = [(s, e) for s, e in runs if e - s + 1 >= 20]
    lab = np.isfinite(yv_all)
    per = []
    rdates = [r["t"] for r in refits]
    prev = None
    flips = []
    for k, t in enumerate(rdates):
        ti = int(np.searchsorted(idx, pd.Timestamp(t)))
        tr = np.arange(0, max(0, ti - C.bars(LAG_W, "W")))
        tr = tr[lab[tr] & np.isfinite(F[SIGNALS + [TERM[n]]].values[tr]).all(1)]
        row = {"t": t, "gateRows": int(g[tr].sum()), "trainRows": int(len(tr))}
        if len(long_runs) <= 4:
            row["byRun"] = {f"{idx[s].date()}..{idx[e].date()}": int(((tr >= s) & (tr <= e)).sum()) for s, e in long_runs}
        coef = float(keep[k][2][len(SIGNALS) + 1]) if k < len(keep) else None
        row["termZ"] = rnd(coef)
        if prev is not None and coef is not None and prev[1] is not None and np.sign(coef) != np.sign(prev[1]) and row["gateRows"] == prev[2]:
            flips.append({"from": prev[0], "to": t, "termZFrom": rnd(prev[1]), "termZTo": rnd(coef), "gateRowsInBoth": row["gateRows"],
                          "newTrainRows": int(row["trainRows"] - prev[3]), "newTrainRowsInGate": 0})
        prev = (t, coef, row["gateRows"], row["trainRows"])
        per.append(row)
    corr = []
    for s, e in long_runs:
        m = np.zeros(len(g), bool)
        m[s:e + 1] = True
        m &= lab & np.isfinite(raw)
        if m.sum() >= 20 and np.std(raw[m]) > 0 and np.std(yv_all[m]) > 0:
            corr.append({"run": f"{idx[s].date()}..{idx[e].date()}", "labelledWeeks": int(m.sum()), "corrTermLabel": rnd(np.corrcoef(raw[m], yv_all[m])[0, 1]),
                         "baseRate": rnd(yv_all[m].mean())})
    m = g & lab & np.isfinite(F[SIGNALS].values).all(1) & np.isfinite(raw)
    r2 = None
    if m.sum() > len(SIGNALS) + 5 and np.std(raw[m]) > 0:
        Xa = np.c_[np.ones(int(m.sum())), F[SIGNALS].values[m]]
        beta, *_ = np.linalg.lstsq(Xa, raw[m], rcond=None)
        res = raw[m] - Xa @ beta
        r2 = float(1 - res.var() / raw[m].var())
    return {"gateRowsInTrainingAtRefits": per, "termLabelCorrelationByRun": corr, "withinGateR2OfTermOnFiveSignals": rnd(r2, 3), "withinGateRows": int(m.sum()),
            "signChangesWithUnchangedGateRows": flips,
            "what": ("labelled diagnostic: the gate's rows among each refit's training rows (positions s < t - 26 with a known label and finite inputs), the raw term's "
                     "correlation with the label inside each run of the gate of 20+ weeks (whole panel, labelled rows), and R^2 of the raw term on the five signals inside the gate")}


def term_stats(rows, real):
    """Mean term value on the scored gated weeks per placebo draw, against the real gate's."""
    v = np.array([x["own"]["meanTerm"] for x in rows if x.get("own") and x["own"].get("meanTerm") is not None], float)
    v = v[np.isfinite(v)]
    if not len(v):
        return {"real": real, "n": 0}
    return {"real": real, "n": int(len(v)), "q05": float(np.quantile(v, 0.05)), "median": float(np.median(v)), "q95": float(np.quantile(v, 0.95))}


def placebo_summary(real, vals):
    v = np.array([x for x in vals if x is not None and np.isfinite(x)], float)
    if not len(v):
        return {"n": 0, "real": (None if real is None else float(real))}
    p95 = float(np.quantile(v, 0.95))
    return {"n": int(len(v)), "real": float(real), "median": float(np.median(v)), "mean": float(v.mean()), "p05": float(np.quantile(v, 0.05)),
            "p95": p95, "max": float(v.max()), "realPercentile": round(100.0 * float((v < real).mean()), 1), "beatsP95": bool(real > p95),
            "quotable": bool(len(v) >= MIN_DRAWS)}


def shift_summary(real, vals, rows=None):
    v = [x for x in vals if x is not None and np.isfinite(x)]
    s = C.null_summary(real, v)
    s["quotable"] = bool(s.get("n", 0) >= MIN_DRAWS)
    s["draws"], s["dropped"] = len(vals), len(vals) - len(v)
    if rows:
        s["rowsScoredPerDraw"] = {"min": int(min(rows)), "median": float(np.median(rows)), "max": int(max(rows))}
    s["construction"] = "study8_common.shift_null draws: circular shift k uniform in [26, n - 26) (>= 26 weeks either way); whole procedure refitted per draw"
    return s


def constraint(pc, ctx):
    yv, pf = ctx["yv"], ctx["pf"]
    fall = yv == 1
    af, ac = C.auc(pf, yv), C.auc(pc, yv)
    below_c, below_f = int((pc[fall] < FLOOR).sum()), int((pf[fall] < FLOOR).sum())
    chg = ac - af
    return {"fallWeeks": int(fall.sum()), "fallWeeksBelow2pct": {"fixed5": below_f, "candidate": below_c},
            "minPOnFallWeek": {"fixed5": rnd(pf[fall].min()), "candidate": rnd(pc[fall].min())},
            "aucFixed5": af, "aucCandidate": ac, "aucChange": chg,
            "status": "pass" if (below_c == 0 and chg >= -CRIT["aucDrop"]) else "fail"}


def decision50(p, y, mask, idx):
    """Steven's loss (missed season catastrophic, 50:1): act when p >= 2%; a stand-down week is p < 2%; a miss is a stand-down
    week followed by a 5-point fall within 26 weeks (label 1)."""
    pv, yv, m = p.values, y.values, mask.values
    sd = m & (pv < FLOOR)
    lab = m & np.isfinite(yv)
    miss = lab & (yv == 1) & (pv < FLOOR)
    return {"misses": int(miss.sum()), "missWeeks": [str(d.date()) for d in idx[miss]], "standDownWeeks": int(sd.sum()),
            "standDownLabelled": int((sd & lab).sum()), "standDownLabelPending": int((sd & ~lab).sum()), "standDownRuns": date_runs(idx, sd),
            "anyStandDownFollowedByFall": bool(miss.any()), "commonWeeks": int(m.sum()), "labelledWeeks": int(lab.sum())}


# ------------------------------------------------------------------------------------------- criteria
def criteria(pr, io, plc, sh, cons):
    out = {}
    b, l = pr["pooled"]["brier"], pr["pooled"]["logloss"]
    q05 = b["block"].get("q05")
    ok = bool(b["improvement"] is not None and b["improvement"] >= CRIT["brier"] and q05 is not None and q05 > 0 and l["improvement"] is not None and l["improvement"] >= CRIT["logloss"])
    out["i"] = {"status": "pass" if ok else "fail", "brierImprovement": b["improvement"], "brierBlockQ05": q05, "brierBlockQ95": b["block"].get("q95"),
                "brierEpisodeQ05": b["episode"].get("q05"), "logLossImprovement": l["improvement"], "need": "Brier >= 0.005 with block q05 > 0, and log loss >= 0.01"}
    eras = {e: pr[e]["brier"]["improvement"] for e in ERA_NAMES}
    worst = min(eras, key=lambda e: eras[e] if eras[e] is not None else 9)
    ok = all(v is not None and v >= -CRIT["eraWorse"] for v in eras.values())
    out["ii"] = {"status": "pass" if ok else "fail", "brierImprovementByEra": eras, "worstEra": worst, "need": "no era worse than -0.005"}
    ins, ous = io["inside"], io["outside"]
    iq = ins["block"].get("q05")
    ok = bool(ins["improvement"] is not None and ins["improvement"] >= CRIT["inside"] and iq is not None and iq > 0 and ous["improvement"] is not None and ous["improvement"] >= CRIT["outside"])
    out["iii"] = {"status": "pass" if ok else "fail", "inside": ins["improvement"], "insideBlockQ05": iq, "insideEpisodeQ05": ins["episode"].get("q05"), "nInside": ins["n"],
                  "outside": ous["improvement"], "outsideBlockQ05": ous["block"].get("q05"), "outsideEpisodeQ05": ous["episode"].get("q05"), "nOutside": ous["n"],
                  "need": "inside >= 0.01 with block q05 > 0, outside >= -0.003 (point estimate, as registered; its bands are reported)"}
    ok = bool(plc.get("beatsP95") and sh.get("p") is not None and sh["p"] < CRIT["p"])
    out["iv"] = {"status": "pass" if ok else "fail", "real": plc.get("real"), "placeboP95": plc.get("p95"), "placeboDraws": plc.get("n"), "beatsPlacebo": plc.get("beatsP95"),
                 "shiftP": sh.get("p"), "shiftDraws": sh.get("n"), "quotable": bool(plc.get("quotable") and sh.get("quotable")),
                 "need": "real pooled Brier improvement > placebo p95 AND shifted-label p < 0.05"}
    out["v"] = {"status": cons["status"], "fallWeeksBelow2pct": cons["fallWeeksBelow2pct"]["candidate"], "minPOnFallWeek": cons["minPOnFallWeek"]["candidate"],
                "aucChange": cons["aucChange"], "need": "no fall week below 2%, AUC change >= -0.01"}
    return out


def _f(x, d=4):
    return "na" if x is None else (f"{x:+.{d}f}" if isinstance(x, (float, int, np.floating)) and not isinstance(x, bool) else str(x))


def statuses_without_nulls(pr, io, cons):
    """Criteria (i), (ii), (iii), (v) for a diagnostic variant (no placebo or shifted-label draws are run for variants)."""
    b, l = pr["pooled"]["brier"], pr["pooled"]["logloss"]
    q = b["block"].get("q05")
    ins, ous = io["inside"], io["outside"]
    iq = ins["block"].get("q05")
    eras = {e: pr[e]["brier"]["improvement"] for e in ERA_NAMES}
    st = {"i": bool(b["improvement"] >= CRIT["brier"] and q is not None and q > 0 and l["improvement"] >= CRIT["logloss"]),
          "ii": bool(all(v >= -CRIT["eraWorse"] for v in eras.values())),
          "iii": bool(ins["improvement"] is not None and ins["improvement"] >= CRIT["inside"] and iq is not None and iq > 0 and ous["improvement"] is not None and ous["improvement"] >= CRIT["outside"]),
          "v": cons["status"] == "pass"}
    if st["iii"] and st["v"] and not st["i"]:
        reading = "condition note at most ((iii) and (v) pass, (i) fails; (iv) not run for a variant)"
    elif all(st.values()):
        reading = "adopted only if (iv) also passed ((iv) not run for a variant)"
    else:
        reading = "not supported ((iii) or (v) fails)" if not (st["iii"] and st["v"]) else "condition note or adopted depending on (iv)"
    return {"statuses": st, "brierImprovement": b["improvement"], "brierBlockQ05": q, "logLoss": l["improvement"], "byEra": eras, "inside": ins["improvement"],
            "insideBlockQ05": iq, "outside": ous["improvement"], "aucChange": cons["aucChange"], "wouldRead": reading}


WHY = {"i": lambda c: f"(i) pooled Brier improvement {_f(c['brierImprovement'])} (block q05 {_f(c['brierBlockQ05'])}), log loss {_f(c['logLossImprovement'])}; needs >= +0.005 with q05 > 0 and >= +0.01",
       "ii": lambda c: f"(ii) {c['worstEra']} Brier improvement {_f(c['brierImprovementByEra'][c['worstEra']])}; no era may be worse than -0.005",
       "iii": lambda c: f"(iii) inside {_f(c['inside'])} (block q05 {_f(c['insideBlockQ05'])}, n {c['nInside']}), outside {_f(c['outside'])} (n {c['nOutside']}); needs inside >= +0.01 with q05 > 0 and outside >= -0.003",
       "iv": lambda c: f"(iv) real {_f(c['real'])} vs placebo p95 {_f(c['placeboP95'])} ({c['placeboDraws']} draws), shifted-label p {c['shiftP']} ({c['shiftDraws']} draws); needs real > p95 and p < 0.05",
       "v": lambda c: f"(v) fall weeks below 2%: {c['fallWeeksBelow2pct']}, min p on a fall week {_f(c['minPOnFallWeek'], 3)}, AUC change {_f(c['aucChange'], 4)}; needs 0 and >= -0.01"}


def verdict(cand, crit, provisional):
    st = {k: crit[k]["status"] == "pass" for k in ("i", "ii", "iii", "iv", "v")}
    if all(st.values()):
        word = "adopted"
    elif st["iii"] and st["v"] and (not st["i"] or not st["iv"]):
        word = "condition note"
    else:
        word = "not supported"
    by_rule = word
    note = None
    if cand == "R1b" and word == "adopted":
        word, note = "condition note", "passes all five, but R1b is the alternative form reported beside R1 and is not adopted on its own (plan)"
    failing = [k for k, s in st.items() if not s]
    c = crit

    def mg(x, thr):
        return None if x is None else float(x - thr)
    margins = {"i": {"brier": mg(c["i"]["brierImprovement"], CRIT["brier"]), "blockQ05": mg(c["i"]["brierBlockQ05"], 0.0), "logLoss": mg(c["i"]["logLossImprovement"], CRIT["logloss"])},
               "ii": {"worstEra": mg(c["ii"]["brierImprovementByEra"][c["ii"]["worstEra"]], -CRIT["eraWorse"])},
               "iii": {"inside": mg(c["iii"]["inside"], CRIT["inside"]), "insideBlockQ05": mg(c["iii"]["insideBlockQ05"], 0.0), "outside": mg(c["iii"]["outside"], CRIT["outside"])},
               "iv": {"overPlaceboP95": mg(c["iv"]["real"], c["iv"]["placeboP95"] if c["iv"]["placeboP95"] is not None else float("nan")), "shiftPBelow005": (None if c["iv"]["shiftP"] is None else float(CRIT["p"] - c["iv"]["shiftP"]))},
               "v": {"fallWeeksBelow2pct": -int(c["v"]["fallWeeksBelow2pct"]), "aucChange": mg(c["v"]["aucChange"], -CRIT["aucDrop"])}}
    protection = {"adopted": "passed (iv), the criterion that carries the family's protection (plan); still to be confirmed on weeks after the scored rows (forecast_log.csv)",
                  "condition note": ("UNPROTECTED: a condition note does not require (iv), and (iv) carries the family's protection (plan); the conditions were also read off "
                                     "the same 2019-2026 rows (leakage.designSelection), so it must be confirmed going forward in forecast_log.csv before it counts"),
                  "not supported": None}.get(word)
    return {"word": word, "byRule": by_rule, "passes": {k: bool(v) for k, v in st.items()}, "failing": failing, "why": [WHY[k](crit[k]) for k in failing],
            "margins": margins, "marginsNote": "statistic minus its bar (positive = clears it); for the p-value, 0.05 minus p",
            "note": note, "provisional": bool(provisional), "multiplicityProtection": protection,
            "rule": "adopted = all five pass; condition note = (iii) and (v) pass but (i) or (iv) fails; not supported = otherwise"}


# ------------------------------------------------------------------------------------------- coefficients
def sign_settled(signs, dates):
    """First refit date from which every later sign equals the last sign."""
    if not signs:
        return None
    k = len(signs) - 1
    while k > 0 and signs[k - 1] == signs[-1]:
        k -= 1
    return dates[k] if k < len(dates) else None


def coef_report(name, keep, ref_last, refits=None):
    rdates = [r["t"] for r in (refits or [])]
    if name in TERM:
        cols = SIGNALS + [TERM[name]]
        j = len(cols)
        signs = "".join("+" if m[2][j] > 0 else ("-" if m[2][j] < 0 else "0") for m in keep)
        mu, sd, w = keep[-1]
        exp = EXPECTED[name]
        return {"term": TERM[name], "termZLast": rnd(w[j]), "termPerPointLast": rnd(w[j] / sd[j - 1], 5), "expectedSign": ({-1: "negative", 1: "positive"}.get(exp, "not registered (by analogy with R1: negative)")),
                "signLast": ("negative" if w[j] < 0 else "positive"), "signMatchesExpected": (None if exp is None else bool(np.sign(w[j]) == exp)),
                "signAtRefits": signs, "refitDates": rdates, "signSettledFrom": sign_settled(signs, rdates), "nRefits": len(keep),
                "refitsWithExpectedSign": (None if exp is None else int(sum((m[2][j] > 0) == (exp > 0) and m[2][j] != 0 for m in keep))),
                "coefficientsLast": {"intercept": rnd(w[0]), **{c: rnd(w[i + 1]) for i, c in enumerate(cols)}},
                "termClipShareLast": None}
    if name == "R2":
        mu, sd, w = keep[-1]
        wf = ref_last[2]
        return {"coefficientsLast": {"intercept": rnd(w[0]), **{c: rnd(w[i + 1]) for i, c in enumerate(SIGNALS)}},
                "fixed5CoefficientsLast": {"intercept": rnd(wf[0]), **{c: rnd(wf[i + 1]) for i, c in enumerate(SIGNALS)}},
                "signsAgreeWithFixed5": {c: bool(np.sign(w[i + 1]) == np.sign(wf[i + 1])) for i, c in enumerate(SIGNALS)}, "nRefits": len(keep),
                "expectedSign": "not registered (same inputs as fixed5; the weights move the fit toward recent eras)"}
    if name == "R3":
        maps = [r3_map(m) for m in keep]
        a, b = maps[-1] if maps else (None, None)

        def fixed_point(ab):
            aa, bb = ab
            if abs(1 - bb) < 1e-12:
                return None
            x = aa / (1 - bb)
            return float(1 / (1 + np.exp(-x))) if x > -700 else 0.0
        fps = [fixed_point(m) for m in maps]
        return {"mapLast": {"a": rnd(a), "b": rnd(b), "n": (keep[-1]["n"] if keep else None)}, "bAtRefits": [rnd(x[1], 3) for x in maps], "aAtRefits": [rnd(x[0], 3) for x in maps],
                "refitDates": rdates,
                "fixedPointAtRefits": [(None if v is None else float(f"{v:.3g}")) for v in fps],
                "fixedPointNote": ("p* = sigmoid(a / (1 - b)), the probability the map leaves unchanged: with b < 1 it raises every forecast below p* and lowers every "
                                   "forecast above it, so a p* near the base rate is shrinkage toward it and a p* near 0 is a downward level shift"),
                "expectedSign": ("b < 1 with a < 0 (the plan's mechanism is overconfidence: shrinkage toward the base rate); b > 0 keeps the ranking within a refit window. "
                                 "Observed: see observedMechanism (computed from the fixed points and the forecasts each map acted on)"),
                "aAllNegative": bool(all(x[0] < 0 for x in maps)), "bAllBelow1": bool(all(x[1] < 1 for x in maps)),
                "bBelow1Last": (None if b is None else bool(b < 1)), "allBPositive": bool(all(x[1] > 0 for x in maps)), "nRefits": len(keep)}
    return {}


# ------------------------------------------------------------------------------------------- inventory
def inventory(preds, names, ctx, sets):
    yv, pf = ctx["yv"], ctx["pf"]
    near = ctx["near"]
    out = {}
    for n in names:
        p = preds[n].values[ctx["labv"]]
        se = brier_rows(p, yv)
        sef = brier_rows(pf, yv)
        tot = se.sum()
        row = {}
        for k, s in sets.items():
            if not s.any():
                row[k] = {"n": 0}
                continue
            row[k] = {"n": int(s.sum()), "brierShare": rnd(se[s].sum() / tot), "brier": rnd(se[s].mean()), "meanP": rnd(p[s].mean()), "realized": rnd(yv[s].mean()),
                      "brierImprovementVsFixed5": rnd((sef[s] - se[s]).mean(), 5)}
        row["ownDefinition"] = {"B": int(((p > B_P) & (yv == 0) & near).sum()), "C": int(((yv == 1) & (p < C_P)).sum()),
                                "note": "B and C re-defined with this model's own probability (counts only)"}
        row["totalBrier"] = rnd(se.mean())
        out[n] = row
    return out


# ------------------------------------------------------------------------------------------- charts
SHORT_TARGET = {"R1": "A weeks", "R1b": "A weeks", "R2": "A or B weeks", "R3": "A or B weeks", "R4": "fresh-start weeks", "R+": "union of its parts"}


def charts(out_dir, idx, y, preds, names, io_all, io_extra=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    BLUE, ORANGE, YELLOW = "#2a78d6", "#eb6834", "#eda100"
    BG, TXT, SEC, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e6e5e1"
    plt.rcParams.update({"figure.facecolor": BG, "axes.facecolor": BG, "savefig.facecolor": BG, "text.color": TXT, "axes.labelcolor": TXT,
                         "xtick.color": SEC, "ytick.color": SEC, "axes.edgecolor": GRID, "font.size": 10, "axes.titlesize": 10.5,
                         "font.family": "DejaVu Sans"})
    files = []
    rows = [n for n in names if n != "fixed5"]
    yy = y.values
    # ---- 1. probability paths through the two windows: one row per candidate (small multiples, two lines per panel)
    nrow = len(rows)
    H = 1.85 * nrow + 1.6
    fig, axes = plt.subplots(nrow, 2, figsize=(12, H), gridspec_kw={"width_ratios": [1, 2.7], "hspace": 0.62, "wspace": 0.05}, sharey=True)
    axes = np.atleast_2d(axes)
    fig.subplots_adjust(top=1 - 1.45 / H, bottom=0.35 / H, left=0.06, right=0.99)
    for i, n in enumerate(rows):
        for j, (wname, a, z) in enumerate(WINDOWS):
            ax = axes[i, j]
            sel = (idx >= pd.Timestamp(a)) & (idx <= pd.Timestamp(z))
            ii = np.where(sel)[0]
            for s0, e0 in C.episodes(np.where(sel, yy, np.nan)):
                ax.axvspan(idx[s0] - pd.Timedelta(days=3.5), idx[e0] + pd.Timedelta(days=3.5), color=ORANGE, alpha=0.13, lw=0)
            ax.axhline(FLOOR, color=YELLOW, lw=1.4, ls=(0, (2, 2)))
            ax.plot(idx[ii], preds["fixed5"].values[ii], color=SEC, lw=1.6, solid_capstyle="round", solid_joinstyle="round")
            ax.plot(idx[ii], preds[n].values[ii], color=BLUE, lw=2.0, solid_capstyle="round", solid_joinstyle="round")
            ax.set_ylim(0, 1)
            ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
            ax.grid(axis="y", color=GRID, lw=0.8)
            ax.set_axisbelow(True)
            for sp in ("top", "right"):
                ax.spines[sp].set_visible(False)
            ax.set_xlim(idx[ii][0] - pd.Timedelta(days=4), idx[ii][-1] + pd.Timedelta(days=4))
            ax.xaxis.set_major_locator(mdates.MonthLocator() if j == 0 else mdates.MonthLocator(bymonth=[1, 3, 5, 7, 9, 11]))
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
            ax.tick_params(axis="both", labelsize=9, length=0)
            if j == 0:
                ax.set_title(f"{n}: {LABEL.get(n, n)}", loc="left", color=TXT, fontsize=10.5, pad=6)
            if i == 0:
                pos = ax.get_position()
                fig.text(pos.x0, pos.y1 + 0.38 / H, wname, color=SEC, fontsize=10.5, fontweight="bold", va="bottom", ha="left")
    handles = [Line2D([0], [0], color=SEC, lw=1.6, label="fixed5"), Line2D([0], [0], color=BLUE, lw=2.0, label="candidate (named on the row)"),
               Patch(facecolor=ORANGE, alpha=0.25, label="fall week (5+ point fall within 26 weeks)"), Line2D([0], [0], color=YELLOW, lw=1.4, ls=(0, (2, 2)), label="2% (50:1 act threshold)")]
    top_y = axes[0, 0].get_position().y1
    fig.legend(handles=handles, loc="lower left", ncol=4, frameon=False, bbox_to_anchor=(0.055, top_y + 0.68 / H), fontsize=9.5)
    fig.text(0.06, top_y + 1.08 / H, "P(5+ point BTC.D fall within 26 weeks), out of sample: fixed5 vs each candidate", fontsize=12.5, color=TXT, va="bottom")
    f1 = os.path.join(out_dir, "refine_paths.png")
    fig.savefig(f1, dpi=100)
    plt.close(fig)
    files.append(f1)
    # ---- 2. Brier change inside vs outside the target weeks with bootstrap bands
    entries = [(f"{n}  ({SHORT_TARGET.get(n, '')})", io_all[n], False) for n in rows if n in io_all]
    entries += [(lab_, io_, True) for lab_, io_ in (io_extra or {}).items()]
    nr = len(entries)
    H2 = 0.62 * nr + 2.95
    fig, axes = plt.subplots(1, 2, figsize=(12, H2), sharey=True, gridspec_kw={"wspace": 0.06})
    fig.subplots_adjust(top=1 - 1.15 / H2, bottom=1.4 / H2, left=0.2, right=0.99)
    for ax, side, col, thr, ttl in ((axes[0], "inside", BLUE, CRIT["inside"], "Inside the target weeks\n(criterion: at least +0.01, block q05 > 0)"),
                                     (axes[1], "outside", ORANGE, CRIT["outside"], "Outside the target weeks\n(criterion: no worse than -0.003)")):
        for k, (lab_, io_, diag_) in enumerate(entries):
            r = io_[side]
            yk = nr - 1 - k
            eb, bb = r.get("episode", {}), r.get("block", {})
            if eb.get("n"):
                ax.plot([eb["q05"], eb["q95"]], [yk - 0.2, yk - 0.2], color=col, lw=1.0, alpha=0.6, solid_capstyle="round")
            if bb.get("n"):
                ax.plot([bb["q05"], bb["q95"]], [yk, yk], color=col, lw=2.6, solid_capstyle="round", ls=((0, (1.5, 1.2)) if diag_ else "-"))
            if r.get("improvement") is not None:
                ax.plot([r["improvement"]], [yk], "o", ms=8, color=(BG if diag_ else col), mec=(col if diag_ else BG), mew=2, zorder=3)
                ax.annotate(f"{r['improvement']:+.4f} (n {r['n']})", (r["improvement"], yk), xytext=(0, 8), textcoords="offset points", ha="center", fontsize=8.5, color=TXT,
                            bbox=dict(boxstyle="round,pad=0.15", fc=BG, ec="none"), zorder=4)
        if any(d_ for _, _, d_ in entries):
            nreg = sum(1 for _, _, d_ in entries if not d_)
            ax.axhline(nr - nreg - 0.5, color=GRID, lw=1.2)
        ax.axvline(0, color=SEC, lw=0.9)
        ax.axvline(thr, color=SEC, lw=1.0, ls=(0, (3, 3)))
        ax.text(thr, nr - 0.42, (f" criterion {thr:+.3f}" if side == "inside" else f"criterion {thr:+.3f} "), color=SEC, fontsize=8.5, va="bottom",
                ha=("left" if side == "inside" else "right"))
        ax.set_title(ttl, loc="left", color=TXT, fontsize=10.5)
        ax.grid(axis="x", color=GRID, lw=0.8)
        ax.set_axisbelow(True)
        for sp in ("top", "right", "left"):
            ax.spines[sp].set_visible(False)
        ax.tick_params(axis="both", labelsize=9, length=0)
        ax.set_xlabel("Brier improvement vs fixed5 (positive = better)", color=SEC, fontsize=9)
        ax.set_ylim(-0.6, nr - 0.1)
    axes[0].set_yticks(range(nr))
    axes[0].set_yticklabels([lab_ for lab_, _, _ in reversed(entries)], fontsize=9.5, color=TXT)
    for tl_, (_, _, diag_) in zip(axes[0].get_yticklabels(), list(reversed(entries))):
        if diag_:
            tl_.set_color(SEC)
    handles = [Line2D([0], [0], color=SEC, marker="o", ls="", ms=7, label="point estimate"), Line2D([0], [0], color=SEC, lw=2.6, label="26-week block bootstrap q05-q95"),
               Line2D([0], [0], color=SEC, lw=1.0, alpha=0.6, label="episode bootstrap q05-q95"), Line2D([0], [0], color=SEC, lw=1.0, ls=(0, (3, 3)), label="criterion")]
    fig.legend(handles=handles, loc="upper left", ncol=4, frameon=False, bbox_to_anchor=(0.195, 1 - 0.42 / H2), fontsize=9.5)
    fig.text(0.2, 1 - 0.15 / H2, "Brier change inside vs outside each candidate's target weeks (labelled common out-of-sample rows)", fontsize=12.5, color=TXT, va="top")
    if io_extra:
        fig.text(0.02, 0.12 / H2, ("Rows below the line (hollow markers, dotted bands) are labelled diagnostics, not verdict inputs: R2 and R3 on the outcome-free target A or B'\n"
                                   "(B' = fixed5 p > 0.5 within 3 points of the 52-week high, no outcome). The registered target A or B also requires 'no fall' for B,\n"
                                   "so every B week is a false alarm by construction."), fontsize=9, color=SEC, va="bottom", linespacing=1.35)
    f2 = os.path.join(out_dir, "refine_inside_outside.png")
    fig.savefig(f2, dpi=100)
    plt.close(fig)
    files.append(f2)
    return files


# ------------------------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="Round 13 refinement stage (ROUND13_PLAN.md)")
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--nulls", type=int, default=200, help="placebo and shifted-label draws per candidate")
    ap.add_argument("--boots", type=int, default=1000, help="block and episode bootstrap draws")
    ap.add_argument("--workers", type=int, default=(os.cpu_count() or 1))
    ap.add_argument("--fast", action="store_true", help="smoke run: nulls 20, boots 200")
    a = ap.parse_args()
    if a.fast:
        a.nulls, a.boots = 20, 200
    n_trunc = 6 if a.fast else 20
    a.workers = max(1, int(a.workers))
    t0 = time.time()
    run_utc, run_est = tz_strings(dt.datetime.now(dt.timezone.utc))
    os.makedirs(a.out, exist_ok=True)

    # ---- data: the clock is the data's last bar; the last daily row is never a complete weekly close
    raw = pd.read_csv(os.path.join(a.data, "BTC.D_1d.csv"))
    last_ts = dt.datetime.fromtimestamp(int(raw["ts"].iloc[-1]) / 1000, tz=dt.timezone.utc)
    last_utc, last_est = tz_strings(last_ts)
    D = C.load_daily(a.data)
    last_bar = D.index[-1]
    sundays = C.panel(D, "W").index
    last_complete = sundays[sundays < last_bar][-1]
    provisional = [str(d.date()) for d in sundays[sundays > last_complete]]
    P, Y, K, F = build(D, a.data, last_complete)
    y = Y[TARGET]
    idx = F.index
    say(f"study13_refine  run {run_utc} / {run_est}; data last bar {last_utc} / {last_est}; last complete week {last_complete.date()} (provisional excluded {provisional}); "
        f"fast={a.fast} nulls {a.nulls} boots {a.boots} workers {a.workers}")

    # ---- predictions (frozen before any null or bootstrap)
    keep = {}
    preds, refits = model_preds(F, Y, CANDS, keep=keep)
    mask = pd.Series(idx >= pd.Timestamp(EVAL_FROM), index=idx)
    for n in ["fixed5"] + CANDS:
        mask &= preds[n].notna()
    lab = mask & y.notna()
    labv = lab.values
    yv = y.values[labv]
    dates = idx[labv]
    first_common = mask[mask].index[0]
    seg_start = int(np.searchsorted(idx, first_common))
    pf = preds["fixed5"].values[labv]
    eps = C.episodes(yv)
    say(f"common rows: first forecast {first_common.date()} (fixed5's first: {preds['fixed5'].first_valid_index().date()}), n {int(mask.sum())}, labelled {int(lab.sum())} "
        f"({dates[0].date()}..{dates[-1].date()}), positives {int(yv.sum())} in {len(eps)} label episodes")

    # ---- target-week sets on the labelled common rows
    A = F["condA"].values[labv] > 0
    near = F["near52"].values[labv] > 0
    Bw = (pf > B_P) & (yv == 0) & near
    Bfree = (pf > B_P) & near
    Cw = (yv == 1) & (pf < C_P)
    crash = K["crash5_26w"].values[labv] == 1
    fresh = F["fresh3"].values[labv] > 0
    tsets = {"R1": A, "R1b": A, "R4": fresh, "R2": A | Bw, "R3": A | Bw}
    osets = {"A": A, "AuBfree": A | Bfree}          # outcome-free targets for the labelled (iii) diagnostic of R2 and R3

    # ---- bootstrap draws (shared by every candidate: common random numbers for the paired comparisons)
    brng = np.random.default_rng(1301)
    ctx = {"yv": yv, "pf": pf, "labv": labv, "near": near, "nAucBoot": a.boots}
    ctx["IB"] = block_draws(len(yv), a.boots, brng)
    ctx["ED"], n_ep_blocks = episode_draws(yv, a.boots, brng)
    ctx["eraDraws"] = {}
    for e in C.ERAS:
        s = era_sel(dates, e)
        ctx["eraDraws"][e[0]] = (s, block_draws(int(s.sum()), a.boots, brng), episode_draws(yv[s], a.boots, brng)[0])

    # ---- real scores per candidate
    cand_res = {}
    io_all = {}
    for n in CANDS:
        pc = preds[n].values[labv]
        pr = paired(pc, ctx)
        io = inside_outside(pc, ctx, tsets[n])
        io["target"] = TARGET_WEEKS[n]
        d = brier_rows(pf, yv) - brier_rows(pc, yv)
        dl = logloss_rows(pf, yv) - logloss_rows(pc, yv)
        io["logLossDiagnostic"] = {"inside": (float(dl[tsets[n]].mean()) if tsets[n].any() else None), "outside": (float(dl[~tsets[n]].mean()) if (~tsets[n]).any() else None),
                                   "what": "labelled diagnostic: the log-loss change (fixed5 minus candidate) on the same inside/outside split as the registered Brier test"}
        io["spillover"] = {**spillover(pc, pf, yv, tsets[n], dates),
                           "what": ("labelled diagnostic: how far the candidate moves the forecasts inside and outside its target weeks (a gated term is zero outside its "
                                    "condition, but the refit changes the intercept and the five coefficients, so outside forecasts move too)")}
        if n in ("R2", "R3"):
            free = inside_outside(pc, ctx, A | Bfree)
            io["outcomeFreeDiagnostic"] = {"target": "A union B' (B' = fixed5 p > 0.5 and BTC.D within 3 points of its 52-week high, no outcome)", **free}
            io["outcomeFreeAaloneDiagnostic"] = {"target": "A alone (no outcome)", **inside_outside(pc, ctx, A)}
            bnot = Bfree & ~Bw & ~A
            io["bWeekDecomposition"] = {
                "Bweeks": int((Bw & ~A).sum()), "BweeksRuns": date_runs(dates, Bw & ~A), "BweeksMeanImprovement": (float(d[Bw & ~A].mean()) if (Bw & ~A).any() else None),
                "BweeksShareOfInsideSum": (float(d[Bw & ~A].sum() / d[A | Bw].sum()) if (A | Bw).any() and d[A | Bw].sum() != 0 else None),
                "sameSignatureButFell": int(bnot.sum()), "sameSignatureButFellRuns": date_runs(dates, bnot),
                "sameSignatureButFellAllFallWeeks": bool((yv[bnot] == 1).all()) if bnot.any() else None,
                "sameSignatureButFellMeanImprovement": (float(d[bnot].mean()) if bnot.any() else None),
                "what": ("labelled diagnostic: the registered B weeks (outside A) are false alarms selected by their outcome, so any downward shift scores there; the weeks "
                         "with the same outcome-free signature (fixed5 p > 0.5, near the 52-week high, outside A) that B leaves out because a fall followed sit in the "
                         "registered 'outside' set")}
            io["note"] = ("B (p > 0.5 with no fall) depends on the outcome: the A-union-B split is the plan's reporting split and the verdict input; outcomeFreeDiagnostic "
                          "(A union B') and outcomeFreeAaloneDiagnostic (A alone) are the same test without the outcome (labelled diagnostics)")
        io_all[n] = io
        rlo = run_loo(d, tsets[n], dates, ED=ctx["ED"])
        rlo["longestRunBySeen"] = {**(seen_split(d, tsets[n], dates, idx, [r["t"] for r in refits[n]]) or {}),
                                   "what": ("labelled diagnostic: the longest run of target weeks split by whether the refit in force already had a week of that run among "
                                            "its training rows (positions s < t - 26)")}
        cand_res[n] = {"label": LABEL[n], "oos": {"byEra": oos_scores(pc, yv, dates)}, "paired": pr, "insideOutside": io, "constraint": constraint(pc, ctx),
                       "coefficients": coef_report(n, keep[n], keep["fixed5"][-1], refits[n]), "conditionRunLOO": rlo,
                       "conditionRunBootstrap": run_boot(d, tsets[n], dates, a.boots, np.random.default_rng(1313))}
        cand_res[n]["constraint"]["pendingStandDown"] = pending_standdown(preds[n], preds["fixed5"], y, mask, F["btcd"], last_complete)
        if n in TERM:
            mu, sd, w = keep[n][-1]
            j = len(SIGNALS)
            zt = (F[TERM[n]].values[labv] - mu[j]) / sd[j]
            g = F[GATE[n]].values[labv] > 0
            cand_res[n]["coefficients"]["termClipShareLast"] = rnd(float((np.abs(zt[g]) > 3).mean()) if g.any() else 0.0, 3)
            cand_res[n]["coefficients"]["identification"] = gate_identification(n, F, y, keep[n], refits[n], idx)
    fixed5_oos = oos_scores(pf, yv, dates)

    # R3's mechanism, from its maps and the forecasts each map acted on (labelled diagnostic beside the coefficients)
    c3 = cand_res["R3"]["coefficients"]
    r3d = [pd.Timestamp(t) for t in c3["refitDates"]]
    maps3_ = [r3_map(m) for m in keep["R3"]]
    lowered = []
    p5s = preds["fixed5"]
    for k, (w0, (aa, bb)) in enumerate(zip(r3d, maps3_)):
        w1 = r3d[k + 1] if k + 1 < len(r3d) else idx[-1] + pd.Timedelta(days=1)
        win = p5s[(p5s.index >= w0) & (p5s.index < w1)].dropna().values
        if len(win) and bb < 1:
            lowered.append(float(np.mean(logit_p(win) > aa / (1 - bb))))
        else:
            lowered.append(None)
    every = [t for t, s in zip(c3["refitDates"], lowered) if s is not None and s >= 1.0]
    from_all = None
    for k in range(len(lowered)):
        if all(s is not None and s >= 1.0 for s in lowered[k:]):
            from_all = c3["refitDates"][k]
            break
    fpt = c3["fixedPointAtRefits"]
    c3["shareOfWindowLowered"] = [rnd(s, 3) for s in lowered]
    c3["observedMechanism"] = {
        "fixedPointFirst": (fpt[0] if fpt else None), "fixedPointLast": (fpt[-1] if fpt else None),
        "everyForecastLoweredFromRefit": from_all, "refitsLoweringEveryForecastInTheirWindow": len(every),
        "text": (("a < 0 and b < 1 at every refit" if c3["aAllNegative"] and c3["bAllBelow1"] else "a < 0 and b < 1 do not hold at every refit (aAtRefits, bAtRefits)")
                 + "; the fixed point p* moved from "
                 f"{fpt[0] if fpt else 'na'} at the first refit ({c3['refitDates'][0] if c3['refitDates'] else 'na'}) to {fpt[-1] if fpt else 'na'} at the last"
                 + (f"; from the {from_all} refit on every map lowered every forecast it acted on, a level correction for a falling base rate rather than "
                    "shrinkage toward the base rate" if from_all else "")
                 + ". The ranking is fixed5's only within a refit window: the pooled AUC changes because the map changes between refits "
                 f"(AUC change {cand_res['R3']['constraint']['aucChange']:+.4f})."),
        "what": "labelled diagnostic: shareOfWindowLowered = share of the fixed5 forecasts in each refit window whose logit lies above the map's fixed point (the map lowers them)"}

    # ---- diagnostics beside the registered candidates (never verdict inputs)
    diag = {}
    km_cmc = []
    p_cmc, _ = S9.run_spec(F, Y, SIGNALS + ["r1cmc_term"], keep_models=km_cmc)
    p_r2n, _ = run_r2(F, y, normalize=True)
    p_r3_lag25, _, _ = run_r3(preds["fixed5"], y, label_lag=LAG_W - 1)
    p_r3_ml, _, _ = run_r3(preds["fixed5"], y, lam=1e-6)
    p_int, _ = run_r3_variant(preds["fixed5"], y, "intercept")
    p_shc, _ = run_r3_variant(preds["fixed5"], y, "shrinkCal")
    SHRINK_GRID = (0.1, 0.2, 0.3, 0.5)
    f5_inputs_ok = np.isfinite(F[SIGNALS].values).all(1)   # fixed5's training rows also need finite inputs (ethbtc_fromhi52w starts 2017-06)
    p_sht = {lam_: run_r3_variant(preds["fixed5"], y, "shrinkTrain", lam=lam_, train_ok=f5_inputs_ok)[0] for lam_ in SHRINK_GRID}
    p_gA, _ = S9.run_spec(F, Y, SIGNALS + ["condA"])
    p_gF, _ = S9.run_spec(F, Y, SIGNALS + ["fresh3"])
    r3_like = [("R3_labelKnownAt_s+26<=t", p_r3_lag25, A | Bw, "R3 with the calibration row s = t - 26 included (s + 26 <= t) instead of the harness's s < t - 26"),
               ("R3_unregularisedMap", p_r3_ml, A | Bw, "R3 with the map fitted by plain maximum likelihood (lam 1e-6) instead of the harness's lam 1"),
               ("R3_interceptOnly", p_int, A | Bw, ("one-parameter recalibration on R3's own schedule: logit p' = logit p + c, c by maximum likelihood on the same calibration rows "
                                                   "(no condition, no slope): a global level shift")),
               ("R3_shrinkFittedOnCalibrationRows", p_shc, A | Bw, ("p' = (1 - l) p + l x (label mean of the calibration rows), l in [0, 1] fitted by least squares on the "
                                                                   "calibration rows, on R3's schedule"))]
    r3_like += [(f"R3_shrinkToTrainingBase_lam{lam_}", p_sht[lam_], A | Bw, (f"p' = (1 - {lam_}) p + {lam_} x (label mean of fixed5's training rows at t: known label, finite inputs), "
                                                                           "active where R3's map is; the grid (0.1, 0.2, 0.3, 0.5) is fixed in advance and picking its best "
                                                                           "value would be an in-sample choice")) for lam_ in SHRINK_GRID]
    for nm, pp, sel, what in ([("R1_cmcCondition", p_cmc, F["condA_cmc"].values[labv] > 0, "R1 with condition A on CoinMarketCap dominance (term still TradingView BTC.D)"),
                               ("R2_weightsNormalized", p_r2n, A | Bw, "R2 with the weights rescaled to mean 1 (separates recency from the extra shrinkage of small weights)")]
                              + r3_like
                              + [("gateOnly_condA", p_gA, A, ("control: fixed5 + the condition-A indicator (a refitted intercept inside A, no term values); shows what the gate "
                                                              "alone does inside and outside A")),
                                 ("gateOnly_fresh3", p_gF, fresh, "control: fixed5 + the fresh-start indicator (no term values); the gate-only counterpart of R4")]):
        if pp.reindex(idx)[mask].isna().any():
            diag[nm] = {"what": what, "note": "not finite on every common row"}
            continue
        pc = pp.values[labv]
        pr = paired(pc, ctx)
        io = inside_outside(pc, ctx, sel)
        cons = constraint(pc, ctx)
        diag[nm] = {"what": what, "brierImprovement": pr["pooled"]["brier"], "logLossImprovement": pr["pooled"]["logloss"]["improvement"],
                    "byEra": {e: pr[e]["brier"]["improvement"] for e in ERA_NAMES}, "insideOutside": io, "constraint": cons,
                    "criteriaWithoutNulls": statuses_without_nulls(pr, io, cons), "label": "labelled diagnostic, not a candidate and not a verdict input"}
        if nm.startswith("R3_"):
            of = outcome_free_iii(pc, ctx, osets)
            diag[nm]["criteriaWithoutNulls"]["iiiOutcomeFree"] = of
            diag[nm]["criteriaWithoutNulls"]["wouldReadOutcomeFree"] = (
                "not supported ((iii) fails on both outcome-free targets: " + "; ".join(f"{k} {', '.join(v['failsOn'])}" for k, v in of.items()) + ")"
                if all(v["status"] == "fail" for v in of.values()) else
                "(iii) passes on at least one outcome-free target: " + ", ".join(k for k, v in of.items() if v["status"] == "pass"))
        if nm.startswith("gateOnly"):
            diag[nm]["spillover"] = spillover(pc, pf, yv, sel, dates)
    # R3 against the one-parameter intercept shift on the same schedule (positive = R3 better), paired, same bootstrap draws
    if "brierImprovement" in diag.get("R3_interceptOnly", {}):
        p3v, piv = preds["R3"].values[labv], p_int.values[labv]
        dd = brier_rows(piv, yv) - brier_rows(p3v, yv)
        ddl = logloss_rows(piv, yv) - logloss_rows(p3v, yv)
        blk, epi = boot_mean(dd, np.ones(len(dd), bool), ctx["IB"], ctx["ED"])
        diag["R3_minus_interceptOnly"] = {"brier": float(dd.mean()), "block": blk, "episode": epi, "logLoss": float(ddl.mean()),
                                          "byEra": {e[0]: float(dd[era_sel(dates, e)].mean()) for e in C.ERAS},
                                          "what": ("labelled diagnostic: Brier of the intercept-only map minus Brier of R3 (positive = R3's slope adds something), paired on the "
                                                   "labelled common rows with the shared block and episode draws")}
    if km_cmc:
        mu, sd, w = km_cmc[-1]
        diag["R1_cmcCondition"]["termPerPointLast"] = rnd(w[-1] / sd[-1], 5)
        diag["R1_cmcCondition"]["signAtRefits"] = "".join("+" if m[2][-1] > 0 else "-" for m in km_cmc)
        diag["R1_cmcCondition"]["conditionWeeks"] = {"cmc": int((F["condA_cmc"].values[labv] > 0).sum()), "tradingView": int(A.sum()),
                                                     "cmcRuns": date_runs(dates, F["condA_cmc"].values[labv] > 0), "tradingViewRuns": date_runs(dates, A)}
    for n in ("R2", "R3"):
        diag.setdefault("insideOutsideOutcomeFree", {})[n] = io_all[n]["outcomeFreeDiagnostic"]

    # ---- nulls through the whole procedure (forked workers; the predictions above are frozen)
    rng = np.random.default_rng(13)
    ks = [int(rng.integers(C.bars(26, "W"), len(Y) - C.bars(26, "W"))) for _ in range(a.nulls)]   # exactly study8_common.shift_null's draws
    seeds = {n: [int(s) for s in rng.integers(1, 2 ** 31 - 1, size=a.nulls)] for n in CANDS + ["R+"]}
    seeds_oos = {n: [int(s) for s in rng.integers(1, 2 ** 31 - 1, size=a.nulls)] for n in TERM}
    tpos = rng.integers(max(1, len(idx) // 4), len(idx) - 1, size=n_trunc)
    cuts_random = sorted(set(str(idx[int(p)].date()) for p in tpos))
    cuts_refit = sorted(set([r["t"] for r in refits["fixed5"]] + ([refits["R3"][0]["t"]] if refits["R3"] else [])))   # label-lag leaks show only at refit dates
    cuts = sorted(set(cuts_random) | set(cuts_refit))
    seeds_tp = {n: [int(s) for s in np.random.default_rng(1314 + i).integers(1, 2 ** 31 - 1, size=a.nulls)] for i, n in enumerate(TERM)}   # own stream: the registered seeds are unchanged
    bf5 = brier_rows(pf, yv)
    csv = {}
    for nm_ in list(C.ALL) + ["BTCD_CMC"]:     # every file build() reads: the loader's series (BTCUSD among them, for the true ATH) and the CoinMarketCap file
        fp_ = os.path.join(a.data, f"{nm_}_1d.csv")
        if os.path.exists(fp_):
            csv[f"{nm_}_1d.csv"] = pd.read_csv(fp_)
    _G.update({"F": F, "Y": Y, "mask": mask, "lab": lab, "labv": labv, "yv": yv, "pf": pf, "bf5": bf5, "IB": ctx["IB"], "targets": tsets, "segStart": seg_start,
               "p5": preds["fixed5"], "preds": preds, "csv": csv})
    pool = get_context("fork").Pool(a.workers) if a.workers > 1 else None
    plus_info = {"evaluated": False}
    try:
        nch = a.workers * 2
        shift_raw = run_jobs(pool, [("shift", c, CANDS, None) for c in chunks(ks, nch) if c])
        plc_raw = {n: run_jobs(pool, [("placebo", n, c, "segments", None, None) for c in chunks(seeds[n], nch) if c]) for n in CANDS}
        plc_oos = {n: run_jobs(pool, [("placebo", n, c, "oosOnly", None, None) for c in chunks(seeds_oos[n], nch) if c]) for n in TERM}
        plc_tp = {n: run_jobs(pool, [("placebo", n, c, "termPreserving", None, None) for c in chunks(seeds_tp[n], nch) if c]) for n in TERM}
        trunc_raw = run_jobs(pool, [("trunc", c) for c in chunks(cuts, a.workers * 3) if c])

        provisional_run = bool(a.nulls < MIN_DRAWS or a.boots < 1000)
        for n in CANDS:
            r = cand_res[n]
            real_u = float(np.mean(bf5 - brier_rows(preds[n].values[labv], yv)))
            plc = placebo_summary(real_u, [x["pooled"] for x in plc_raw[n]])
            plc["kind"] = ({"R2": "ages randomly permuted among the training rows at every refit", "R3": "the map fitted on past predictions shuffled in time against their labels"}.get(n)
                           or f"the raw term ({RAW[n]}) gated by random blocks of the condition's own run lengths, placed at random among the out-of-sample weeks (and among the earlier training weeks)")
            plc["insideDiagnostic"] = placebo_summary(float(np.mean((bf5 - brier_rows(preds[n].values[labv], yv))[tsets[n]])), [x["inside"] for x in plc_raw[n]])
            if n in TERM:
                real_term = float(np.nanmean(F[RAW[n]].values[labv][tsets[n]])) if tsets[n].any() else None
                plc["oosOnlyDiagnostic"] = {**placebo_summary(real_u, [x["pooled"] for x in plc_oos[n]]), "kind": "the training weeks keep the real condition; only the out-of-sample weeks are re-blocked"}
                plc["termPreservingDiagnostic"] = {**placebo_summary(real_u, [x["pooled"] for x in plc_tp[n]]),
                                                   "kind": ("labelled diagnostic: the gated column (gate x term) and its gate circularly shifted together inside each segment by "
                                                            "26+ weeks, so the term values on the gated weeks travel with the gate (the registered placebo keeps the raw term "
                                                            "at every week, so its gated weeks carry other term values)"),
                                                   "meanTermOnScoredGatedWeeks": term_stats(plc_tp[n], real_term)}
                plc["meanTermOnScoredGatedWeeks"] = {**term_stats(plc_raw[n], real_term),
                                                     "what": f"labelled diagnostic: mean raw term ({RAW[n]}) on the scored gated weeks, real gate vs the registered placebo's gates"}
                own = [x["own"] for x in plc_raw[n] if x.get("own")]
                sc = [o["scoredGatedWeeks"] for o in own]
                real_sc = int(tsets[n].sum())
                plc["scoredGatedWeeksPerDraw"] = {"real": real_sc, "min": (int(min(sc)) if sc else None), "q05": (float(np.quantile(sc, 0.05)) if sc else None),
                                                  "median": (float(np.median(sc)) if sc else None), "max": (int(max(sc)) if sc else None),
                                                  "shareOfDrawsWithFewerThanReal": (round(float(np.mean(np.array(sc) < real_sc)), 3) if sc else None),
                                                  "what": "labelled diagnostic: placebo-gated weeks that land on the labelled common rows (out-of-sample blocks can fall in the 26 unlabelled weeks)"}
                ok3 = [o for o in own if o.get("iii") is not None]
                plc["ownGateDiagnostic"] = {"draws": len(ok3), "shareIii": (round(float(np.mean([o["iii"] for o in ok3])), 3) if ok3 else None),
                                            "shareV": (round(float(np.mean([o["v"] for o in ok3])), 3) if ok3 else None),
                                            "shareIiiAndV": (round(float(np.mean([o["iii"] and o["v"] for o in ok3])), 3) if ok3 else None),
                                            "insideMedian": (float(np.median([o["inside"] for o in ok3])) if ok3 else None),
                                            "outsideMedian": (float(np.median([o["outside"] for o in ok3])) if ok3 else None),
                                            "what": ("labelled diagnostic: each registered placebo draw judged on its OWN gate with the registered (iii) bars and (v): the share "
                                                     "of random-gated terms that would reach 'condition note' territory ((iii) and (v)) by chance")}
            sh = shift_summary(real_u, [x[n] for x in shift_raw], [x["rows"] for x in shift_raw])
            r["placebo"], r["shiftNull"] = plc, sh
            r["criteria"] = criteria(r["paired"], r["insideOutside"], plc, sh, r["constraint"])
            # labelled diagnostics beside the registered criteria (never verdict inputs)
            d_ = bf5 - brier_rows(preds[n].values[labv], yv)
            ebn = episode_band_note(tsets[n], yv, dates)
            r["criteria"]["i"]["episodeBandDiagnostic"] = {
                "episodeQ05": r["criteria"]["i"]["brierEpisodeQ05"], "conditionRunBootstrapPooled": {k: r["conditionRunBootstrap"].get("pooled", {}).get(k) for k in ("q05", "q95")},
                "conditionRunLOOMinPooledWithout": r["conditionRunLOO"].get("minPooledWithout"), **ebn,
                "why": ((f"the label episodes of the longest target run are short, so that run spans {ebn.get('blocksTouchingLongestRun')} of the {ebn.get('episodeBlocks')} "
                         "episode blocks and the episode bootstrap treats one regime as several independent draws: its band is too narrow for a gain concentrated in that "
                         "run, so 'episode q05 > 0' is not support on its own; the run bootstrap and the leave-one-run-out are shown beside it")
                        if (ebn.get("blocksTouchingLongestRun") or 0) > 1 else
                        (f"the longest target run lies inside {ebn.get('blocksTouchingLongestRun')} of the {ebn.get('episodeBlocks')} episode blocks, so the episode bootstrap "
                         "drops it as often as one block's share implies (probabilityADrawHoldsNoneOfThem) and its band is not narrowed by that run; the run bootstrap and "
                         "the leave-one-run-out are shown beside it" if ebn.get("blocksTouchingLongestRun") == 1 else ebn.get("note", "na"))),
                "label": "labelled diagnostic, not a verdict input"}
            r["criteria"]["iii"]["outsideShareClearingBar"] = {**share_clearing(d_, ~tsets[n], ctx["IB"], ctx["ED"], CRIT["outside"]),
                                                               "what": "labelled diagnostic: share of bootstrap draws whose outside change clears -0.003 (the registered test is the point estimate)"}
            r["criteria"]["iii"]["logLossInside"] = r["insideOutside"]["logLossDiagnostic"]["inside"]
            r["criteria"]["iii"]["logLossOutside"] = r["insideOutside"]["logLossDiagnostic"]["outside"]
            if n in ("R2", "R3"):
                of = outcome_free_iii(preds[n].values[labv], ctx, osets)
                r["criteria"]["iii"]["outcomeFree"] = {**of, "label": ("labelled diagnostic, not a verdict input: (iii) with the registered bars on targets that do not use the "
                                                                       "outcome (A union B', A alone); the registered A union B uses it")}
            r["verdict"] = verdict(n, r["criteria"], provisional_run)
        adopted = [n for n in ADOPTABLE if cand_res[n]["verdict"]["word"] == "adopted"]
        r3 = cand_res["R3"]
        variants3 = {k: diag[k]["criteriaWithoutNulls"] for k in ("R3_labelKnownAt_s+26<=t", "R3_unregularisedMap") if "criteriaWithoutNulls" in diag.get(k, {})}
        of_reg = r3["criteria"]["iii"].get("outcomeFree", {})
        of_all = {"registered": {k: v["status"] for k, v in of_reg.items() if isinstance(v, dict)}, **{k: {kk: vv["status"] for kk, vv in v.get("iiiOutcomeFree", {}).items()} for k, v in variants3.items()}}
        reach_reg = {k: v.get("wouldRead") for k, v in variants3.items()}
        all_fail_free = all(all(st_ == "fail" for st_ in v.values()) for v in of_all.values())
        r3["implementationSensitivity"] = {
            "registered": {"statuses": r3["verdict"]["passes"], "outside": r3["criteria"]["iii"]["outside"], "brierBlockQ05": r3["criteria"]["i"]["brierBlockQ05"], "verdict": r3["verdict"]["word"],
                           "iiiOutcomeFree": of_reg},
            **variants3,
            "outcomeFreeIiiStatus": of_all,
            "note": ("the plan leaves two choices open for R3: which calibration rows count as 'known at t' (the harness's s < t - 26, used here, or s + 26 <= t) and whether the "
                     "two-parameter map carries the harness's lam 1 penalty (used here) or none; the variants are labelled diagnostics, not verdict inputs. Under the registered "
                     "(outcome-selected) A-union-B split the variants read: " + "; ".join(f"{k}: {v}" for k, v in reach_reg.items())
                     + (". Without the outcome (A union B', A alone), (iii) fails for the registered R3 and for every variant, on the inside band (iiiOutcomeFree), so R3 is "
                        "not one implementation choice away from a condition note: any such reading rests on the 8 outcome-selected B weeks"
                        if all_fail_free else ". Without the outcome, (iii) passes for at least one R3 version on at least one outcome-free target (outcomeFreeIiiStatus)"))}

        # ---- R+: evaluated once, only if two or more pass on their own
        if len(adopted) >= 2:
            kp = {}
            pp, _ = run_plus(F, Y, adopted, keep=kp)
            preds["R+"] = pp
            pc = pp.values[labv]
            sel = np.zeros(len(yv), bool)
            for c in adopted:
                sel |= tsets[c]
            tsets["R+"] = sel
            _G["targets"]["R+"] = sel
            pr = paired(pc, ctx)
            io = inside_outside(pc, ctx, sel)
            io["target"] = "union of the target weeks of " + ", ".join(adopted)
            io_all["R+"] = io
            plus_shift = run_jobs(pool, [("shift", c, ["R+"], adopted) for c in chunks(ks, nch) if c])
            plus_plc = run_jobs(pool, [("placebo", "R+", c, "segments", adopted, sel) for c in chunks(seeds["R+"], nch) if c])
            real_u = float(np.mean(bf5 - brier_rows(pc, yv)))
            plc = placebo_summary(real_u, [x["pooled"] for x in plus_plc])
            plc["kind"] = "joint: every component replaced by its own placebo in the same draw"
            plc["insideDiagnostic"] = placebo_summary(float(np.mean((bf5 - brier_rows(pc, yv))[sel])), [x["inside"] for x in plus_plc])
            sh = shift_summary(real_u, [x["R+"] for x in plus_shift], [x["rows"] for x in plus_shift])
            d = bf5 - brier_rows(pc, yv)
            coefs = {}
            if kp.get("base"):
                mu, sd, w = kp["base"][-1]
                cols = SIGNALS + [TERM[c] for c in adopted if c in TERM]
                coefs["coefficientsLast"] = {"intercept": rnd(w[0]), **{c: rnd(w[i + 1]) for i, c in enumerate(cols)}}
            if kp.get("map"):
                aa, bb = r3_map(kp["map"][-1])
                coefs["mapLast"] = {"a": rnd(aa), "b": rnd(bb)}
            res_plus = {"label": LABEL["R+"], "components": adopted, "oos": {"byEra": oos_scores(pc, yv, dates)}, "paired": pr, "insideOutside": io,
                        "constraint": constraint(pc, ctx), "coefficients": coefs, "placebo": plc, "shiftNull": sh, "conditionRunLOO": run_loo(d, sel, dates, ED=ctx["ED"])}
            res_plus["criteria"] = criteria(pr, io, plc, sh, res_plus["constraint"])
            res_plus["verdict"] = verdict("R+", res_plus["criteria"], provisional_run)
            cand_res["R+"] = res_plus
            plus_info = {"evaluated": True, "components": adopted}
        else:
            plus_info = {"evaluated": False, "adoptedOnTheirOwn": adopted,
                         "reason": f"{len(adopted)} candidate(s) passed all five on their own; R+ is evaluated only if two or more pass (R1b is not adopted on its own and does not count)"}
            cand_res["R+"] = plus_info
    finally:
        if pool:
            pool.close()
            pool.join()

    names = ["fixed5"] + CANDS + (["R+"] if plus_info["evaluated"] else [])
    for n in CANDS + (["R+"] if plus_info["evaluated"] else []):
        r = cand_res[n]
        pr, io, c, v = r["paired"]["pooled"], r["insideOutside"], r["criteria"], r["verdict"]
        say(f"{n:4s} Brier {fmt(pr['brier']['improvement'])} blk[{fmt(pr['brier']['block'].get('q05'))},{fmt(pr['brier']['block'].get('q95'))}] ep[{fmt(pr['brier']['episode'].get('q05'))},{fmt(pr['brier']['episode'].get('q95'))}] "
            f"LL {fmt(pr['logloss']['improvement'])} eras {' '.join(fmt(r['paired'][e]['brier']['improvement']) for e in ERA_NAMES)} | in {fmt(io['inside']['improvement'])} (n{io['inside']['n']}, q05 {fmt(io['inside']['block'].get('q05'))}) "
            f"out {fmt(io['outside']['improvement'])} | placebo p95 {fmt(r['placebo'].get('p95'))} pct {r['placebo'].get('realPercentile')} shift p {r['shiftNull'].get('p')} | "
            f"AUC {fmt(r['constraint']['aucChange'], 3)} falls<2% {r['constraint']['fallWeeksBelow2pct']['candidate']} | "
            + " ".join(f"({k}){'P' if c[k]['status'] == 'pass' else 'F'}" for k in ('i', 'ii', 'iii', 'iv', 'v')) + f" -> {v['word'].upper()}{' (provisional)' if v['provisional'] else ''}")

    # ---- multiple comparisons: the family-wise shifted-label null of the best increment
    reals = {n: float(np.mean(bf5 - brier_rows(preds[n].values[labv], yv))) for n in CANDS}
    best = max(reals, key=reals.get)
    fw = [max(row[n] for n in CANDS) for row in shift_raw if all(row[n] is not None for n in CANDS)]
    multiple = {"family": "5 candidates (+1 combination if evaluated) x 5 criteria", "protection": "criterion (iv) carries the family's protection; the verdicts are read jointly (plan)",
                "familyWiseShiftNull": {**shift_summary(reals[best], fw), "bestCandidate": best,
                                        "note": "per shifted-label draw, the best pooled Brier improvement over fixed5 among the five candidates, against the best real improvement"},
                "bonferroni": {"alpha": round(CRIT["p"] / len(CANDS), 4), "shiftPBelow": {n: (None if cand_res[n]["shiftNull"].get("p") is None else bool(cand_res[n]["shiftNull"]["p"] < CRIT["p"] / len(CANDS))) for n in CANDS},
                               "note": "diagnostic: the per-candidate shifted-label p against 0.05 / 5; not a registered criterion"},
                "smallestAttainableP": (round(1.0 / a.nulls, 4) if a.nulls else None),
                "conditionNoteRoute": {
                    "placeboReachIiiAndV": {n: cand_res[n]["placebo"].get("ownGateDiagnostic") for n in TERM},
                    "R3_interceptOnlyWouldRead": diag.get("R3_interceptOnly", {}).get("criteriaWithoutNulls", {}).get("wouldRead"),
                    "note": ("'condition note' requires (iii) and (v) but not (iv), and (iv) carries the family's protection, so a condition note has no multiplicity or "
                             "adversary protection: placeboReachIiiAndV gives, for each gated candidate, the share of its registered placebo draws (random gates) that reach "
                             "(iii) on their own gate and (v); for R2 and R3 the outcome-selected B weeks open the same route (a global level shift with no condition, "
                             "diagnostics.R3_interceptOnly, reads as shown). Any condition-noted candidate is tagged verdict.multiplicityProtection = UNPROTECTED."),
                    "label": "labelled diagnostic, not a verdict input"},
                "selection": ("the conditions (A, B, C), their thresholds, R4's fresh-start window and the terms were read off fixed5's 2019-2026 out-of-sample failure "
                              f"inventory (out8/honest), and the criteria are scored on the same rows ({first_common.date()}..{dates[-1].date()}, labelled): round 13 has "
                              "no untouched holdout, the placebos and the shift null keep each condition's definition fixed and do not model that choice, so (iv) errs in "
                              "the candidates' favour; any adopted or condition-noted candidate must be confirmed going forward (forecast_log.csv, weeks after "
                              f"{last_complete.date()})")}

    # ---- inventory (weekly, labelled common rows; weeks fixed by fixed5's definitions and re-scored for every model)
    sets = {"A": A, "B": Bw, "C": Cw, "D": crash, "rest": ~(A | Bw | Cw)}
    inv = {"definitions": {"A": "BTC.D at least 15 points below its trailing 104-week high (t included)", "B": "fixed5 p > 0.5, no fall (label 0), BTC.D within 3 points of its 52-week high",
                           "C": "fall week (label 1) with fixed5 p < 0.35", "D": "crash-led fall week (round 10: TOTAL3 lower at the 5-point crossing than at t)", "rest": "none of A, B, C"},
           "rows": {"labelled": int(len(yv)), "from": str(dates[0].date()), "to": str(dates[-1].date())},
           "weeks": {k: {"n": int(s.sum()), "runs": date_runs(dates, s)} for k, s in sets.items() if k != "rest"},
           "byModel": inventory(preds, names, ctx, sets),
           "note": "A, B, C, D weeks are fixed by fixed5's probability and the outcome, then re-scored for every model (same weeks); ownDefinition counts B and C with each model's own probability"}
    inv["weeks"]["rest"] = {"n": int((~(A | Bw | Cw)).sum())}
    gap52 = (F["hi52"].values - F["btcd"].values)[labv]
    bnear = (pf > B_P) & (yv == 0) & (gap52 > NEAR_PTS) & (gap52 <= 7.0)
    inv["bNearMissDiagnostic"] = {"definition": "fixed5 p > 0.5, no fall, BTC.D 3 to 7 points below its 52-week high (outside B as registered)", "n": int(bnear.sum()),
                                  "runs": date_runs(dates, bnear),
                                  "byModel": {n: {"brier": rnd(brier_rows(preds[n].values[labv][bnear], yv[bnear]).mean()) if bnear.any() else None,
                                                  "meanP": rnd(preds[n].values[labv][bnear].mean()) if bnear.any() else None} for n in names},
                                  "note": ("the plan lists Dec 2019 and Feb 2020 among B's alarms, but there BTC.D sat 3.1-4.0 (Dec 2019) and 6.6 (Feb 2020) points below its 52-week "
                                           "high, outside the registered 3-point band: B as registered holds only Feb-Mar 2025, and the plan's 7.5% share is reproduced exactly on "
                                           "its sampled weeks (planSampleFixed5); these near misses are listed here as a diagnostic, not added to B")}
    # the plan's numbers came from out8/honest's every-second-week sample: reproduce them for fixed5 on those dates
    try:
        with open(os.path.join(HERE, "out8", "honest", "results.json")) as fh:
            sample_dates = pd.DatetimeIndex([pd.Timestamp(d["t"]) for d in json.load(fh)["series"]["fixed5_fall5_26w"]])
        src = "out8/honest series.fixed5_fall5_26w dates (every second week)"
    except Exception:
        sample_dates, src = dates[::2], "every second labelled common row (out8/honest not found)"
    sm = np.isin(dates, sample_dates)
    sub = {k: s & sm for k, s in sets.items()}
    se = brier_rows(pf, yv)
    inv["planSampleFixed5"] = {"source": src, "n": int(sm.sum()), **{k: {"n": int(s.sum()), "brierShare": rnd(se[s].sum() / se[sm].sum()), "meanP": rnd(pf[s].mean()) if s.any() else None,
                                                                          "realized": rnd(yv[s].mean()) if s.any() else None, "weekShare": rnd(s.sum() / sm.sum())} for k, s in sub.items()},
                               "standDownWeeks": int((sm & (pf < FLOOR)).sum()), "minPOnFallWeek": rnd(pf[sm & (yv == 1)].min()),
                               "plan": "A 49.5% of the loss on 29% of weeks, mean p 0.43 vs realized 0.19; B 7.5%; C 5.6%; 11 of 186 sampled weeks stood down; lowest p on a fall week 0.29",
                               "sampleSizeNote": ("out8/honest ran with the provisional week 2026-11-08 in its panel, so its labels reached one week further (186 sampled labelled "
                                                  "weeks); this module excludes the provisional week, so the same dates hold 185 labelled weeks")}

    # ---- decision record at 50:1
    dec = {"threshold": FLOOR, "rule": "act when p >= 2% (missed season catastrophic, 50:1); stand down below", "byModel": {n: decision50(preds[n], y, mask, idx) for n in names}}

    # ---- today: the last complete week
    tl = last_complete
    Ft = F.loc[tl]
    today = {"asOf": str(tl.date()), "dataLastBarUtc": last_utc, "dataLastBarEst": last_est, "runUtc": run_utc, "runEst": run_est, "btcd": rnd(Ft["btcd"], 2),
             "readings": {n: rnd(preds[n].loc[tl]) for n in names}, "act50": {n: (None if not np.isfinite(preds[n].loc[tl]) else bool(preds[n].loc[tl] >= FLOOR)) for n in names},
             "conditions": {"A_postSeason": bool(Ft["condA"] > 0), "btcdHigh104w": rnd(Ft["hi104"], 2), "pointsBelowHigh104w": rnd(Ft["hi104"] - Ft["btcd"], 2),
                            "A_cmc": (None if not np.isfinite(Ft["condA_cmc"]) else bool(Ft["condA_cmc"] > 0)), "riseFrom13wLow": rnd(Ft["rise13"], 2), "weeksSince104wHigh": int(Ft["wsh104"]),
                            "fresh3": bool(Ft["fresh3"] > 0), "high13w": rnd(Ft["hi13"], 2), "change8w": rnd(Ft["chg8"], 2), "near52wHigh": bool(Ft["near52"] > 0), "high52w": rnd(Ft["hi52"], 2),
                            "Bprime_outcomeFree": bool(Ft["near52"] > 0 and preds["fixed5"].loc[tl] > B_P)},
             "terms": {"r1_term": rnd(Ft["r1_term"]), "r1b_term": rnd(Ft["r1b_term"]), "r4_term": rnd(Ft["r4_term"])},
             "r3MapInForce": (dict(zip(("a", "b"), [rnd(v) for v in r3_map(keep["R3"][-1])])) if keep.get("R3") else None)}
    if plus_info["evaluated"]:
        today["combination"] = {"evaluated": True, "components": plus_info["components"], "reading": today["readings"].get("R+")}
    else:
        ad = list(plus_info.get("adoptedOnTheirOwn", []))
        src = ad[0] if len(ad) == 1 else "fixed5"
        today["combination"] = {"evaluated": False, "components": ad, "readingIs": src, "reading": rnd(preds[src].loc[tl]),
                                "note": (f"R+ is evaluated only if two or more candidates pass all five; {len(ad)} passed, so the combination of the passing candidates is "
                                         + ("that candidate" if len(ad) == 1 else "fixed5 itself") + " (reported here, not evaluated as R+)")}
    for nm, pp in (("R1_cmcCondition", p_cmc), ("R2_weightsNormalized", p_r2n), ("R3_interceptOnly", p_int)):
        today.setdefault("diagnostics", {})[nm] = rnd(pp.loc[tl])
    f5act = today["act50"].get("fixed5")
    flips = [n for n in names if n != "fixed5" and today["act50"].get(n) is not None and today["act50"][n] != f5act]
    today["act50DiffersFromFixed5"] = {"models": flips,
                                       "note": ("The plan treats the act/stand-down decision as settled and aims this pass at sizing; today "
                                                + (", ".join(f"{n} reads {today['readings'][n]} ({'act' if today['act50'][n] else 'stand down'})" for n in flips)
                                                   + f" while fixed5 reads {today['readings']['fixed5']} ({'act' if f5act else 'stand down'}), so "
                                                   + ("that candidate" if len(flips) == 1 else "those candidates") + " would flip today's 50:1 decision "
                                                   "(constraint.pendingStandDown has the unlabelled weeks behind it)" if flips else "no candidate flips fixed5's 50:1 decision")),
                                       "label": "labelled diagnostic, not a verdict input"}
    say(f"TODAY {today['asOf']} BTC.D {today['btcd']} (104w high {today['conditions']['btcdHigh104w']}, A {'on' if today['conditions']['A_postSeason'] else 'off'}; fresh3 "
        f"{'on' if today['conditions']['fresh3'] else 'off'}, 8w change {today['conditions']['change8w']}): " + " ".join(f"{n} {today['readings'][n]}" for n in names)
        + f" | act at 2%: {sum(1 for v in today['act50'].values() if v)}/{len(names)}")

    # ---- leakage checks
    leak = {}
    p_wf, _ = walk_forward_t(F[SIGNALS], y, lambda Xtr, ytr, tr, t: (lambda mu_sd: (mu_sd[0], mu_sd[1], C.logistic_fit(C.zapply(Xtr, *mu_sd), ytr)))(C.zfit(Xtr)),
                             lambda m, Xh, te: C.logistic_predict(C.zapply(Xh[te], m[0], m[1]), m[2]))
    leak["walkForwardIdentity"] = {"maxAbsDiff": float((p_wf - preds["fixed5"]).abs().max()), "ok": bool((p_wf - preds["fixed5"]).abs().max() == 0.0),
                                   "what": "walk_forward_t (passes the refit position to R2's fit) against study8_common.walk_forward on fixed5"}
    Xz = C.zapply(F[SIGNALS].values[labv], *C.zfit(F[SIGNALS].values[labv]))
    w1, w2 = C.logistic_fit(Xz, yv), logistic_fit_w(Xz, yv, np.ones(len(yv)))
    leak["weightedFitIdentity"] = {"maxAbsDiff": float(np.max(np.abs(w1 - w2))), "ok": bool(np.max(np.abs(w1 - w2)) < 1e-9), "what": "logistic_fit_w with unit weights against study8_common.logistic_fit"}
    ages = []
    run_r2(F, y, age_log=ages)
    leak["r2Ages"] = {"minAgeWeeks": (min(x["minAge"] for x in ages) if ages else None), "refits": len(ages), "ok": bool(ages and min(x["minAge"] for x in ages) >= LAG_W + 1),
                      "what": "ages = refit position minus training-row position; every training row is older than the 26-week label lag"}
    # R3: calibration sets point in time, activation, ranking inside every refit window
    rows3, viol, wins, min_b = [], 0, 0, None
    p5v, r3v = preds["fixed5"].values, preds["R3"].values
    xr = np.isfinite(logit_p(p5v)) & np.isfinite(p5v)
    grid = list(range(int(np.searchsorted(idx, pd.Timestamp(WF_START))), len(idx), REFIT_W))
    for t in grid:
        cal = np.where(xr[:max(0, t - LAG_W)] & np.isfinite(y.values[:max(0, t - LAG_W)]))[0]
        te = np.arange(t, min(t + REFIT_W, len(idx)))
        te = te[np.isfinite(p5v[te])]
        if len(cal) >= R3_MIN:
            rows3.append({"t": str(idx[t].date()), "n": int(len(cal)), "lastCalibrationRow": str(idx[cal[-1]].date()), "weeksFromLastRowToT": int(t - cal[-1])})
        if len(te) >= 2:
            wins += 1
            a5, a3 = p5v[te], r3v[te]
            s5 = np.sign(a5[:, None] - a5[None, :])
            s3 = np.sign(a3[:, None] - a3[None, :])
            viol += int((s5 != s3).sum() // 2)
    maps3 = [r3_map(m) for m in keep["R3"]]
    min_b = min(b for _, b in maps3) if maps3 else None
    leak["r3CalibrationSets"] = {"activation": (rows3[0]["t"] if rows3 else None), "refits": len(rows3), "minRows": (min(r["n"] for r in rows3) if rows3 else None),
                                 "minWeeksFromLastRowToT": (min(r["weeksFromLastRowToT"] for r in rows3) if rows3 else None),
                                 "ok": bool(rows3 and min(r["weeksFromLastRowToT"] for r in rows3) >= LAG_W and min(r["n"] for r in rows3) >= R3_MIN),
                                 "first": rows3[:2], "last": rows3[-1:], "matchesHarnessRefits": [r["t"] for r in refits["R3"]] == [r["t"] for r in rows3],
                                 "what": "the map at refit t sees only fixed5 predictions at s with s + 26 < t (labels known at t); fixed5's own refit dates; active from the first date with >= 52 such rows"}
    leak["r3Ranking"] = {"windowsChecked": wins, "pairOrderViolations": viol, "minMapSlopeB": rnd(min_b, 4), "ok": bool(viol == 0 and (min_b is None or min_b > 0)),
                         "what": "inside every refit window (fixed5's and R3's refit dates coincide) the order of R3 equals the order of fixed5 for every pair of weeks"}
    # explicit window checks on BTC.D
    Tfull = terms(C.panel(D, "W"))
    bf_full = Tfull["btcd"].values
    off = int(np.searchsorted(Tfull.index, idx[0]))
    wcheck = 0.0
    for t in np.random.default_rng(5).integers(0, len(idx), size=60):
        tf = t + off
        wcheck = max(wcheck, abs(F["hi104"].values[t] - np.max(bf_full[max(0, tf - POST_HI_W + 1):tf + 1])), abs(F["lo13"].values[t] - np.min(bf_full[max(0, tf - LOW_W + 1):tf + 1])),
                     abs(F["hi52"].values[t] - np.max(bf_full[max(0, tf - NEAR_HI_W + 1):tf + 1])), abs(F["hi13"].values[t] - np.max(bf_full[max(0, tf - FRESH_W + 1):tf + 1])))
    leak["windows"] = {"maxAbsDiff": float(wcheck), "ok": bool(wcheck == 0.0), "checked": 60,
                       "what": "trailing 104-week high, 13-week low, 52-week high and 13-week high recomputed by hand from closes t-w+1..t at 60 random weeks; each includes t and nothing after it"}
    trunc_raw = sorted(trunc_raw, key=lambda r: r["cut"])
    tr_ok = all(r["termsMaxAbsDiff"] <= 1e-9 and r["predsMaxAbsDiff"] <= 1e-9 and r["labelsMaxAbsDiff"] == 0 and r["termsFiniteMismatch"] == 0 and r["finiteMismatch"] == 0
                and r["cutMatches"] for r in trunc_raw)
    refit_set = set(cuts_refit)
    sig_worst = {c: max([r["signalsMaxAbsDiff"].get(c, 0.0) for r in trunc_raw] or [0.0]) for c in SIGNALS}
    leak["truncation"] = {"ok": bool(tr_ok), "tested": len(trunc_raw), "cuts": [r["cut"] for r in trunc_raw],
                          "refitDateCuts": int(sum(1 for r in trunc_raw if r["cut"] in refit_set)), "randomCuts": len(cuts_random),
                          "r3ActivationCut": (refits["R3"][0]["t"] if refits["R3"] else None),
                          "cutsWhoseLastCompleteWeekMatches": int(sum(1 for r in trunc_raw if r["cutMatches"])),
                          "maxAbsDiffTerms": max([r["termsMaxAbsDiff"] for r in trunc_raw] or [0.0]), "maxAbsDiffSignals": sig_worst,
                          "maxAbsDiffPredictions": max([r["predsMaxAbsDiff"] for r in trunc_raw] or [0.0]),
                          "maxAbsDiffPredictionsAtCut": max([r["predsAtCutMaxAbsDiff"] for r in trunc_raw] or [0.0]), "maxAbsDiffKnownLabels": max([r["labelsMaxAbsDiff"] for r in trunc_raw] or [0.0]),
                          "finiteMismatches": int(sum(r["finiteMismatch"] + r["termsFiniteMismatch"] for r in trunc_raw)),
                          "filesCut": sorted(csv),
                          "what": ("file-level cut: every data file the pipeline reads (" + ", ".join(sorted(csv)) + ") cut to the bars with ts <= the cut Sunday + 1 day "
                                   "into a temporary folder, the last complete week re-read from those files as main() reads it, and the whole pipeline (load_daily, features "
                                   "with the true-ATH btc_dd_ath read from the cut BTCUSD file, the CoinMarketCap condition, conditions, terms, labels, fixed5, R1, R1b, R2, R3, "
                                   "R4) rebuilt from them; every value at every row up to the cut must equal the full run's. Cuts: the seeded random Sundays plus every fixed5 "
                                   "refit date (a label-lag leak changes the forecasts only at a refit date), R3's activation date among them")}
    gate_ok = True
    for n in TERM:
        g = F[GATE[n]].values
        for sd_ in seeds[n][:20]:
            pg = placebo_gate(g, seg_start, np.random.default_rng(sd_))
            gate_ok &= bool(pg[:seg_start].sum() == (g[:seg_start] > 0).sum() and pg[seg_start:].sum() == (g[seg_start:] > 0).sum())
    leak["placeboBlocks"] = {"ok": bool(gate_ok), "inputs": "the condition series and the segment boundary only (place_blocks takes run lengths and a length)",
                             "totalLengthPreserved": bool(gate_ok), "segmentBoundary": str(idx[seg_start].date()),
                             "what": "the placebo condition never reads a label or a prediction; each segment keeps the real condition's total length"}
    leak["labels"] = {"lastLabelledRow": str(y[y.notna()].index[-1].date()), "lastCompleteWeek": str(last_complete.date()), "provisionalBarsExcluded": provisional, "labelLagWeeks": LAG_W,
                      "outcomeDependentSplit": ("B (and so the R2/R3 target A union B) uses the outcome: the plan's split and the (iii) verdict input for R2 and R3; "
                                                "insideOutside.outcomeFreeDiagnostic / outcomeFreeAaloneDiagnostic and criteria.iii.outcomeFree drop the outcome (labelled diagnostics)")}
    leak["designSelection"] = {
        "statement": ("design-level look-ahead (not a code leak): the plan derived condition A, the B band, R4's fresh-start window and the term choices from fixed5's "
                      f"2019-2026 out-of-sample failure inventory (out8/honest), and the criteria are scored on the same common rows ({first_common.date()}..{dates[-1].date()} "
                      "labelled). Every registered adversary (random-block placebo, permuted ages, shuffled map, 26-week shift null) keeps the condition's definition "
                      "fixed and none models the choice of that condition from these rows, so a candidate that passed would carry an optimistic (iv) percentile"),
        "consequence": ("verdicts: " + ", ".join(n + " " + cand_res[n]["verdict"]["word"] for n in CANDS) + "; the bias favours the candidates, so a 'not supported' stands, "
                        f"and any pass must be confirmed on weeks after {last_complete.date()} (forecast_log.csv)"),
        "label": "labelled statement beside the registered checks"}
    rep = {}
    for nm, path, key in (("round9", os.path.join(HERE, "out9", "candidates", "results.json"), ("series", "fixed5")),
                          ("round8", os.path.join(HERE, "out8", "honest", "results.json"), ("series", "fixed5_fall5_26w"))):
        try:
            with open(path) as fh:
                ser = json.load(fh)[key[0]][key[1]]
            s = pd.Series({pd.Timestamp(d["t"]): d["v"] for d in ser})
            com = s.index.intersection(preds["fixed5"].dropna().index)
            dd = (s[com] - preds["fixed5"][com]).abs()
            rep[nm] = {"file": os.path.relpath(path, HERE), "commonRows": int(len(com)), "from": str(com[0].date()), "to": str(com[-1].date()), "maxAbsDiff": float(dd.max()),
                       "referenceDigits": 4, "refDatesNotForecastHere": [str(x.date()) for x in s.index.difference(preds["fixed5"].dropna().index)],
                       "ok": bool(dd.max() <= 5e-5 + 1e-12)}
        except Exception as ex:
            rep[nm] = {"file": os.path.relpath(path, HERE), "error": str(ex)}
    leak["fixed5Reproduction"] = rep
    say(f"fixed5 reproduction: " + "; ".join(f"{k} {v.get('commonRows')} rows {v.get('from')}..{v.get('to')} max |diff| {v.get('maxAbsDiff', float('nan')):.2e}" for k, v in rep.items())
        + f" | leakage: truncation {leak['truncation']['ok']} ({leak['truncation']['tested']} cuts, preds {leak['truncation']['maxAbsDiffPredictions']:.1e}), windows {leak['windows']['ok']}, "
        f"R3 sets {leak['r3CalibrationSets']['ok']} (active {leak['r3CalibrationSets']['activation']}), R3 ranking {leak['r3Ranking']['ok']} ({viol} violations, min b {rnd(min_b, 3)}), "
        f"R2 ages {leak['r2Ages']['ok']}, wf identity {leak['walkForwardIdentity']['ok']}, placebo blocks {leak['placeboBlocks']['ok']}")

    # ---- charts
    files = []
    try:
        io_extra = {f"{n}  (A or B', no outcome)": io_all[n]["outcomeFreeDiagnostic"] for n in ("R2", "R3") if "outcomeFreeDiagnostic" in io_all[n]}
        files = charts(a.out, idx, y, preds, names, io_all, io_extra)
    except Exception as ex:  # a chart failure must not lose the results
        files = [f"chart error: {ex}"]

    # ---- numbers the notes quote (all computed above; the notes only read them)
    def g_(dct, *ks, default=None):
        for k in ks:
            if not isinstance(dct, dict) or k not in dct:
                return default
            dct = dct[k]
        return dct

    def f4(x, d=4):
        return "na" if x is None else f"{x:+.{d}f}"
    r1c, r3c = cand_res["R1"], cand_res["R3"]
    r1_ebn = g_(r1c, "criteria", "i", "episodeBandDiagnostic", default={})
    r3_ebn = g_(r3c, "criteria", "i", "episodeBandDiagnostic", default={})
    r1_seen = g_(r1c, "conditionRunLOO", "longestRunBySeen", default={})
    r1_id = g_(r1c, "coefficients", "identification", default={})
    r1_runs = g_(r1c, "conditionRunLOO", "runs", default=[]) or []
    r1_tail = sum(rr["weeks"] for rr in r1_runs[1:]) if len(r1_runs) > 1 else 0
    r1_short_txt = ", ".join(f"{rr['run']} ({rr['weeks']})" for rr in r1_runs[1:]) or "none"
    r1_corr_pos = bool(r1_id.get("termLabelCorrelationByRun")) and all((cc.get("corrTermLabel") or 0) > 0 for cc in r1_id.get("termLabelCorrelationByRun", []))
    r1_oos_long_runs = sum(1 for rr in r1_runs if rr.get("weeks", 0) >= 20)
    flips_txt = "; ".join(f"{fl['from']} {f4(fl['termZFrom'], 3)} to {fl['to']} {f4(fl['termZTo'], 3)} with {fl['gateRowsInBoth']} A rows in both"
                          for fl in r1_id.get("signChangesWithUnchangedGateRows", [])) or "none"
    corr_txt = ", ".join(f"{cc['run']} {f4(cc['corrTermLabel'], 2)}" for cc in r1_id.get("termLabelCorrelationByRun", [])) or "na"
    r3_of = g_(r3c, "criteria", "iii", "outcomeFree", default={})
    r2_of = g_(cand_res["R2"], "criteria", "iii", "outcomeFree", default={})
    r3_bd = g_(r3c, "insideOutside", "bWeekDecomposition", default={})
    r3_runs = g_(r3c, "conditionRunLOO", "runs", default=[]) or []
    r3_pool = g_(r3c, "paired", "pooled", "brier", "improvement")
    r3_share_run = (r3_runs[0]["insideOfRun"] * r3_runs[0]["weeks"] / (r3_pool * len(yv))) if (r3_runs and r3_pool and r3_runs[0].get("insideOfRun") is not None) else None
    int_d = diag.get("R3_interceptOnly", {})
    rmi = diag.get("R3_minus_interceptOnly", {})
    shr = {lam_: g_(diag, f"R3_shrinkToTrainingBase_lam{lam_}", "brierImprovement", "improvement") for lam_ in SHRINK_GRID}
    e23 = era_sel(dates, C.ERAS[2])
    pend = {n: g_(cand_res[n], "constraint", "pendingStandDown", default={}) for n in CANDS}
    pend_on = [n for n in CANDS if (pend[n].get("weeksBelow2pct") or 0) > 0]
    f5_tail_below = pend["R3"].get("fixed5WeeksBelow2pct") if pend.get("R3") else None
    out_share = {n: g_(cand_res[n], "criteria", "iii", "outsideShareClearingBar", "block") for n in CANDS}
    r4p = g_(cand_res["R4"], "placebo", default={})
    sp1 = g_(r1c, "insideOutside", "spillover", default={})
    gA = diag.get("gateOnly_condA", {})

    notes = [
        f"Common rows: every model forecasts from {first_common.date()} (fixed5 needs 60 training rows: ethbtc_fromhi52w is finite from 2017-06 and labels wait 26 weeks); "
        f"{int(lab.sum())} labelled weekly rows ({dates[0].date()}..{dates[-1].date()}), {int(yv.sum())} positives in {len(eps)} label episodes; the last 26 weeks carry no label and enter only 'today' and decision50.",
        "fixed5 = study8_baselines.SIGNALS through study9_candidates.run_spec (study8_common.walk_forward: expanding window, refit every 13 weeks from 2019-01-06, labels withheld 26 weeks, "
        "min_train 60; z-scores clipped at 3; logistic lam 1), btc_dd_ath from the full BTCUSD history (study8_honest.ath_drawdown); it reproduces round 9 and round 8 to their 4-digit rounding (leakage.fixed5Reproduction).",
        "R1/R1b/R4 add one column to fixed5 through the same harness; the column is zero outside its condition, but every refit re-estimates the intercept and the five coefficients "
        "with it, so the forecasts outside the condition move too (insideOutside.spillover, labelled diagnostic: for R1 the mean |p - p_fixed5| is "
        f"{f4(sp1.get('meanAbsDeltaPInside'))} inside A and {f4(sp1.get('meanAbsDeltaPOutside'))} outside, outside shift {f4(sp1.get('meanDeltaPOutside'))}). "
        "Criterion (iii)'s outside half therefore tests that spillover and is not a free pass for a gated term: the registered placebo draws reach (iii) on their own random gate in "
        + ", ".join(f"{n} {g_(cand_res[n], 'placebo', 'ownGateDiagnostic', 'shareIii')}" for n in TERM)
        + " of draws (placebo.ownGateDiagnostic). diagnostics.gateOnly_condA (fixed5 + the bare A indicator, no term values) shows the gate alone: inside "
        f"{f4(g_(gA, 'insideOutside', 'inside', 'improvement'))}, outside {f4(g_(gA, 'insideOutside', 'outside', 'improvement'))}, pooled "
        f"{f4(g_(gA, 'brierImprovement', 'improvement'))}. The harness's clip at 3 standard deviations caps the largest inside values (coefficients.termClipShareLast).",
        f"Condition A uses TradingView BTC.D, whose 2016 levels (up to {F['btcd'].max():.1f} on {F['btcd'].idxmax().date()}) hold the trailing 104-week high above 90 into early 2019, so on the panel "
        f"(from {idx[0].date()}) condition A runs {', '.join(date_runs(idx, F['condA'].values > 0))}; "
        "diagnostics.R1_cmcCondition re-runs R1 with the condition on CoinMarketCap dominance (term unchanged) as a robustness check, not a verdict input.",
        "R1b's expected sign is not registered in the plan (by analogy with R1 it would be negative); R1b is reported beside R1 and is not adopted on its own: if it passed all five its verdict would read "
        "'condition note' with that reason, and it does not count toward R+.",
        "R2's weights are 0.5 ** (age / 156) exactly as registered (age = weeks from the refit date to the training row, at least 27), in the log likelihood of the harness logistic with its lam 1 "
        "unchanged; the z-score scaler is unweighted. Because the weights are below 1 the penalty weighs relatively more; diagnostics.R2_weightsNormalized rescales them to mean 1 to separate the two.",
        "R3 is the harness walk-forward over fixed5's own out-of-sample logits: at each fixed5 refit date t the two-parameter map is fitted on the rows s < t - 26 (labels known at t, so s + 26 <= t holds "
        "with one week to spare, the harness's lag convention) that carry a fixed5 prediction; min_train 52 makes it active from the first date with 52 such rows "
        f"({leak['r3CalibrationSets']['activation']}, which is a refit date), fixed5 before that. The map is the harness logistic (lam 1) on the z-scored logit without the clip, so it is strictly "
        "monotone whenever b > 0 and the ranking inside each refit window is fixed5's (leakage.r3Ranking). diagnostics.R3_labelKnownAt_s+26<=t and R3_unregularisedMap show the sensitivity to the two "
        "implementation choices the plan leaves open; they are labelled diagnostics, not verdict inputs.",
        "R3's mechanism (labelled diagnostics; the registered verdict is unchanged): " + g_(r3c, "coefficients", "observedMechanism", "text", default="na") + " fixed5 over-predicts on the "
        f"labelled common rows (mean p {pf.mean():.3f} against a realized rate of {yv.mean():.3f}; 2023-26: {pf[e23].mean():.3f} against {yv[e23].mean():.3f}). A one-parameter intercept "
        f"shift on R3's own schedule (diagnostics.R3_interceptOnly: no condition, no slope) improves Brier by {f4(g_(int_d, 'brierImprovement', 'improvement'))} against R3's "
        f"{f4(r3_pool)}; R3 minus intercept-only {f4(rmi.get('brier'))} (block [{f4(g_(rmi, 'block', 'q05'))}, {f4(g_(rmi, 'block', 'q95'))}]), and under the registered rule that "
        f"global shift would read '{g_(int_d, 'criteriaWithoutNulls', 'wouldRead', default='na')}', so (iii) on A union B cannot tell a condition-specific nuance from a global "
        "level correction. Shrinking toward the training base rate (the label mean of fixed5's training rows at t) "
        + ("loses at every value of the fixed grid" if all(v_ is not None and v_ < 0 for v_ in shr.values()) else
           f"gains at most {f4(max([v_ for v_ in shr.values() if v_ is not None] or [None]))} on the fixed grid, against the intercept shift's "
           f"{f4(g_(int_d, 'brierImprovement', 'improvement'))}")
        + " (" + ", ".join(f"lam {k_} {f4(v_)}" for k_, v_ in shr.items()) + "; diagnostics.R3_shrinkToTrainingBase_lam*): that base rate sits well above the 2023-26 rate.",
        "Criteria are computed on the labelled common rows with unrounded numbers; improvements are fixed5 minus candidate (positive = better) for Brier and log loss (natural log, p clipped to [1e-6, 1 - 1e-6]). "
        "The 26-week circular block bootstrap and the episode bootstrap (blocks = each label episode with its 26-week run-up and the stretches between) use the same draws for every candidate; per-era bands "
        "resample inside the era's rows; inside/outside bands resample the whole common series and average the target (or non-target) rows each draw, so the clustering of the target weeks is kept.",
        "Criterion (iii)'s outside test is the registered point estimate (>= -0.003); its block and episode bands are reported beside it (criteria.iii.outsideBlockQ05), and the share of block "
        "draws that clear the bar sits inside the noise for several candidates (criteria.iii.outsideShareClearingBar, labelled diagnostic: "
        + ", ".join(f"{n} {out_share[n]}" for n in CANDS) + "). Outside, R3's log loss changes by "
        f"{f4(g_(r3c, 'criteria', 'iii', 'logLossOutside'))} while its Brier changes by {f4(g_(r3c, 'criteria', 'iii', 'outside'))} (criteria.iii.logLossOutside).",
        "B (p > 0.5 with no fall while BTC.D is within 3 points of its 52-week high) is defined with fixed5's own probability and with the outcome: every B week is a false alarm by construction, "
        "so any downward shift scores there. A union B is the plan's split and stays the registered (iii) input for R2 and R3. Without the outcome (criteria.iii.outcomeFree, labelled diagnostic; "
        "B' = fixed5 p > 0.5 within 3 points of the 52-week high): R3 inside "
        f"{f4(g_(r3_of, 'AunionBprime', 'inside'))} (block q05 {f4(g_(r3_of, 'AunionBprime', 'insideBlockQ05'))}) on A union B' and {f4(g_(r3_of, 'Aalone', 'inside'))} "
        f"(q05 {f4(g_(r3_of, 'Aalone', 'insideBlockQ05'))}) on A alone, (iii) {g_(r3_of, 'AunionBprime', 'status')} / {g_(r3_of, 'Aalone', 'status')}: its registered inside significance "
        f"comes from the {r3_bd.get('Bweeks')} outcome-selected B weeks ({f4(r3_bd.get('BweeksMeanImprovement'), 3)} each, {100 * (r3_bd.get('BweeksShareOfInsideSum') or 0):.0f}% of the "
        f"inside sum), while the {r3_bd.get('sameSignatureButFell')} weeks with the same outcome-free signature that B leaves out because a fall followed score "
        f"{f4(r3_bd.get('sameSignatureButFellMeanImprovement'), 3)} each in the registered 'outside' (insideOutside.bWeekDecomposition). Every R3 variant's outcome-free (iii) status is in "
        f"implementationSensitivity.outcomeFreeIiiStatus. R2: (iii) {g_(cand_res['R2'], 'criteria', 'iii', 'status')} registered, {g_(r2_of, 'AunionBprime', 'status')} on A union B', "
        f"{g_(r2_of, 'Aalone', 'status')} on A alone. Any condition note for R2 or R3 under the registered split would rest on outcome-selected weeks.",
        "Placebos (criterion iv) run the whole procedure per draw: R1/R1b/R4 keep the raw term at every week (rise from the 13-week low, log weeks since the 104-week high, 8-week change) and replace the "
        "condition by random blocks of its own run lengths placed at random among the out-of-sample weeks, and separately among the earlier training weeks so the fitted coefficient never sees the real "
        "condition (placebo.oosOnlyDiagnostic keeps the real condition on the training weeks); R2 permutes the ages among the training rows at every refit; R3 shuffles the past predictions in time against "
        "their labels at every refit (the map then has no information and pulls toward the base rate, so this placebo is weak by construction: it is beaten whenever the real map keeps fixed5's ranking).",
        "The R1/R1b/R4 placebo is registered with the raw term kept at every week, so its gated weeks carry other term values (placebo.meanTermOnScoredGatedWeeks, labelled diagnostic: R4's "
        f"chg8 averages {f4(g_(r4p, 'meanTermOnScoredGatedWeeks', 'real'), 2)} on the real fresh-start weeks against a median of {f4(g_(r4p, 'meanTermOnScoredGatedWeeks', 'median'), 2)} "
        "on placebo gates, because fresh3 and chg8 are mechanically linked). placebo.termPreservingDiagnostic shifts the gate and the gated term together "
        f"(R4: p95 {f4(g_(r4p, 'termPreservingDiagnostic', 'p95'))}, real percentile {g_(r4p, 'termPreservingDiagnostic', 'realPercentile')}; registered p95 {f4(r4p.get('p95'))}, percentile "
        f"{r4p.get('realPercentile')}"
        + ("; the registered placebo is the more lenient of the two for R4" if (g_(r4p, "termPreservingDiagnostic", "p95") is not None and r4p.get("p95") is not None
                                                                             and g_(r4p, "termPreservingDiagnostic", "p95") > r4p["p95"]) else "")
        + "). Out-of-sample placebo blocks can land in the 26 unlabelled weeks, so some draws score fewer gated weeks than the real condition "
        "(placebo.scoredGatedWeeksPerDraw).",
        "Shifted-label null: draws exactly as study8_common.shift_null (circular shift k uniform in [26, n - 26), so at least 26 weeks in either direction), every model (fixed5, R1, R1b, R2, R3 with its map "
        "on the shifted fixed5, R4) refitted on the shifted labels and scored on the labelled common rows (the rows the real statistic uses) where the shifted label exists; p = share of draws whose "
        "improvement over the shifted fixed5 is at least the real improvement. Under shifted labels fixed5 itself is overconfident without skill, so a recalibration (R3) can gain there too: the null "
        "asks whether the real gain exceeds that.",
        (lambda r1: "The skeptic's questions: out of sample condition A is one long run "
         f"({r1['conditionRunBootstrap'].get('longestRun')}) plus shorter runs ({r1_short_txt}). The registered episode bootstrap resamples label episodes (each with its 26-week run-up) and the "
         "stretches between; the long A run spans several of those blocks, so a draw drops the whole run in "
         f"{r1['conditionRunLOO'].get('episodeBootstrapWithoutLongestRun', {}).get('shareOfDraws')} of draws (conditionRunLOO.episodeBootstrapWithoutLongestRun). conditionRunBootstrap (diagnostic) "
         "resamples the runs of target weeks and the stretches between, so a draw drops the whole run as often as its share of the blocks implies "
         f"({r1['conditionRunBootstrap'].get('shareOfDrawsWithoutLongestRun')} of draws for R1); conditionRunLOO drops each run in turn; coefficients.signAtRefits and signSettledFrom show when "
         f"R1's sign settles ({r1['coefficients'].get('signSettledFrom')}; the refits before then are fitted on the 2017-19 A run alone).")(cand_res["R1"]),
        f"R1 is not identified out of sample. Condition A holds one out-of-sample episode ({r1_ebn.get('longestTargetRun')}) plus {r1_tail} weeks in shorter runs ({r1_short_txt}). The registered "
        f"episode bootstrap cannot drop that run: it spans {r1_ebn.get('blocksTouchingLongestRun')} of the {r1_ebn.get('episodeBlocks')} episode blocks, so a draw holds none of them with "
        f"probability {(r1_ebn.get('probabilityADrawHoldsNoneOfThem') or 0):.1e} ({g_(r1c, 'conditionRunLOO', 'episodeBootstrapWithoutLongestRun', 'shareOfDraws')} of the draws did); the "
        "plan's 'the episode bootstrap must drop it' is met only by conditionRunLOO and conditionRunBootstrap (diagnostics), and the latter's inside band is degenerate with so few runs "
        f"(q05 {f4(g_(r1c, 'conditionRunBootstrap', 'inside', 'q05'))}, q95 {f4(g_(r1c, 'conditionRunBootstrap', 'inside', 'q95'))}). Without the run, R1's pooled change is "
        f"{f4(g_(r1c, 'conditionRunLOO', 'minPooledWithout'))}. Within the run, the inside gain split by what the refit in force had seen: no week of the run "
        f"({g_(r1_seen, 'refitHadSeenNoWeekOfTheRun', 'n')} weeks, {f4(g_(r1_seen, 'refitHadSeenNoWeekOfTheRun', 'insideImprovement'))}) against part of it "
        f"({g_(r1_seen, 'refitHadSeenPartOfTheRun', 'n')} weeks, {f4(g_(r1_seen, 'refitHadSeenPartOfTheRun', 'insideImprovement'))}) (conditionRunLOO.longestRunBySeen). The term's sign "
        f"changed between refits with the same A rows in training ({flips_txt}), so only non-A rows entering the fit moved it (coefficients.identification). Inside A the raw term "
        f"correlates with the label by run as {corr_txt}, and the five signals explain {g_(r1_id, 'withinGateR2OfTermOnFiveSignals')} of its variance"
        + (", so signMatchesExpected (negative) is a partial effect under collinearity, not support for 'a base built after a big fall means the season is over'"
           if r1_corr_pos else "")
        + (". Even a pass would have rested on one episode." if r1_oos_long_runs == 1 else "."),
        "The episode bootstrap counts the 2021-22 post-season regime as several episodes: its short crash-led label episodes cut the 2021-23 A run into "
        f"{r3_ebn.get('blocksTouchingLongestRun')} of the {r3_ebn.get('episodeBlocks')} episode blocks, so the episode band is too narrow for a gain concentrated in that run. R3 draws "
        + (f"{100 * r3_share_run:.0f}%" if r3_share_run is not None else "na") + " of its pooled Brier gain from it: episode q05 "
        f"{f4(g_(r3c, 'criteria', 'i', 'brierEpisodeQ05'))} against the run bootstrap's pooled q05 {f4(g_(r3c, 'conditionRunBootstrap', 'pooled', 'q05'))} "
        f"(leaving the run out: {f4(g_(r3c, 'conditionRunLOO', 'minPooledWithout'))}); criteria.i.episodeBandDiagnostic shows both, and 'episode q05 > 0' is not support on its own. "
        "Criterion (i) uses the block q05 as registered.",
        "Constraint (v): fall weeks are labelled common rows with label 1; the 2% bar is the plan's rounding of 1/51; the AUC change is the pooled point estimate (its block band is in paired.pooled.auc).",
        "Constraint (v) cannot see the last 26 common weeks, whose labels are pending (constraint.pendingStandDown, labelled diagnostic; the registered (v) is unchanged): "
        + ("; ".join(f"{n} sits below 2% in {pend[n].get('weeksBelow2pct')} of them ({', '.join(pend[n].get('runsBelow2pct') or [])}), today {pend[n].get('today', {}).get('candidate')} "
                     f"against fixed5's {pend[n].get('today', {}).get('fixed5')}" for n in pend_on)
           + f" (fixed5: {f5_tail_below} pending weeks below 2%)" if pend_on else "no candidate sits below 2% in a pending week")
        + ". " + today["act50DiffersFromFixed5"]["note"] + ".",
        "decision50 counts weekly rows (the plan's 186 were every second week from out8/honest; inventory.planSampleFixed5 reproduces the plan's numbers on those dates: 185 labelled weeks here "
        "because out8 kept the provisional week, whose horizon labelled one more sampled week).",
        "Failure B as registered (fixed5 p > 0.5, no fall, BTC.D within 3 points of its 52-week high) holds only Feb-Mar 2025 on the weekly rows; the plan also names Dec 2019 and Feb 2020, where "
        "BTC.D sat 3.1-4.0 and 6.6 points below its 52-week high. The registered definition is used everywhere (it reproduces the plan's 7.5% exactly); inventory.bNearMissDiagnostic lists those weeks.",
        "Shifted-label draws score the labelled common rows (never the 26 unlabelled tail weeks, which a rolled label could otherwise reach) where the shifted label exists and every model "
        "forecasts: when the rolled 26-week block of unknown labels lands in the first training window, the first refit falls below 60 rows and its 13 weeks carry no forecast in that draw "
        "(shiftNull.rowsScoredPerDraw: every draw scores a subset of the real statistic's rows).",
        "R+ combines the candidates whose verdict is 'adopted' (all five criteria) among R1, R2, R3, R4; with fewer than two, candidates.R+ records why it was not evaluated.",
        "Verdicts are 'provisional' when the run used fewer than 50 null draws or fewer than 1000 bootstrap draws (the fast smoke run); only a full run's verdicts are quotable.",
        "Multiple comparisons: five candidates (+ R+ if evaluated) face five criteria each; criterion (iv) carries the family's protection as registered, multipleComparisons adds the family-wise "
        "shifted-label null of the best increment and a Bonferroni reading of the shift p-values as diagnostics.",
        "Selection: the conditions, their thresholds and the terms were chosen from fixed5's 2019-2026 out-of-sample failures, the rows scored here (leakage.designSelection), so round 13 has no "
        "untouched holdout and (iv) errs in the candidates' favour (its placebos and shift null keep each condition fixed). A 'condition note' requires (iii) and (v) but not (iv), so it carries "
        "no multiplicity or adversary protection (verdict.multiplicityProtection; multipleComparisons.conditionNoteRoute gives the share of placebo draws reaching (iii) and (v) on their own "
        f"gate). Any adopted or condition-noted candidate must be confirmed going forward in forecast_log.csv, on weeks after {last_complete.date()}.",
        "Nothing here touches the bot; an adopted candidate joins the forecast reading only after the owner reads it.",
    ]
    if _LINES[1]:
        notes.append(f"{_LINES[1]} summary lines were dropped to stay under the 60-line limit; everything is in results.json.")

    plan = {"file": "ROUND13_PLAN.md", "registered": "2026-11-02 18:58 UTC / 1:58 PM EST", "target": TARGET + " on TradingView BTC.D weekly closes (W-SUN)",
            "rule": "when iteration plateaus after exhaustive attempts, look at where the model still fails and add slight nuance dynamics fitted to those conditions, one final pass",
            "candidates": {"R1": "inside condition A (BTC.D >= 15 points below its trailing 104-week high) BTC.D's rise from its trailing 13-week low (points), zero outside; expected negative",
                           "R1b": "inside condition A log(1 + weeks since the trailing 104-week high), zero outside; reported beside R1, not adopted on its own",
                           "R2": "the five inputs, logistic fit with sample weights 0.5 ** (age_weeks / 156)",
                           "R3": "two-parameter logistic recalibration of fixed5's logit on its own earlier out-of-sample predictions with known labels (26-week lag), refit every 13 weeks, active from 52 rows",
                           "R4": "inside the fresh-start condition (BTC.D within 3 points of its 13-week high) BTC.D's 8-week change (points), zero outside; expected positive",
                           "R+": "the combination of the candidates that pass on their own, evaluated once, only if two or more pass"},
            "criteria": {"i": "pooled Brier improvement >= 0.005 with block q05 > 0, and log-loss improvement >= 0.01",
                         "ii": "no era (2019-20, 2021-22, 2023-26) worse by more than 0.005 Brier",
                         "iii": "inside the target weeks improvement >= 0.01 with q05 > 0; outside no worse than -0.003 (R1, R1b: A; R4: fresh start; R2, R3: A union B)",
                         "iv": "real improvement > p95 of the matched placebo (200 draws) AND shifted-label null p < 0.05",
                         "v": "no out-of-sample fall week below 2%, pooled AUC does not fall by more than 0.01"},
            "verdicts": "adopted (all five) | condition note ((iii) and (v) pass but (i) or (iv) fails) | not supported (otherwise, with the failing criterion)"}
    res = {"module": "study13_refine", "plan": plan, "runUtc": run_utc, "runEst": run_est, "dataLastBarUtc": last_utc, "dataLastBarEst": last_est, "lastCompleteWeek": str(last_complete.date()),
           "fast": bool(a.fast), "settings": {"nulls": a.nulls, "boots": a.boots, "workers": a.workers, "truncationCuts": n_trunc, "episodeBlocks": n_ep_blocks, "minDrawsForP": MIN_DRAWS},
           "rows": {"firstCommonForecast": str(first_common.date()), "common": int(mask.sum()), "labelled": int(lab.sum()), "positives": int(yv.sum()), "labelEpisodes": len(eps),
                    "conditionAWeeks": int(A.sum()), "Bweeks": int(Bw.sum()), "freshWeeks": int(fresh.sum()), "Cweeks": int(Cw.sum()), "crashLedFallWeeks": int(crash.sum())},
           "fixed5": {"oos": {"byEra": fixed5_oos}, "coefficientsLast": {"intercept": rnd(keep["fixed5"][-1][2][0]), **{c: rnd(keep["fixed5"][-1][2][i + 1]) for i, c in enumerate(SIGNALS)}},
                      "refits": len(refits["fixed5"])},
           "inventory": inv, "candidates": cand_res, "verdicts": {n: cand_res[n]["verdict"]["word"] for n in CANDS + (["R+"] if plus_info["evaluated"] else [])},
           "today": today, "decision50": dec, "leakage": leak, "multipleComparisons": multiple, "diagnostics": diag, "charts": [os.path.basename(f) for f in files],
           "series": {n: C.thin(preds[n].where(mask), every=1) for n in names}, "runtimeSeconds": None, "notes": notes}
    res["runtimeSeconds"] = round(time.time() - t0, 1)
    C.write_results(a.out, clean(res))
    say(f"wrote {os.path.join(a.out, 'results.json')} and {len(files)} charts in {res['runtimeSeconds']}s; verdicts: " + "; ".join(f"{k} {v}" for k, v in res["verdicts"].items()))


if __name__ == "__main__":
    main()
