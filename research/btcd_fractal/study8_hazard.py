#!/usr/bin/env python3
"""Round 8 trial [4] "hazard": is 'how far off' a survival curve with covariates and a clock that beats a clock-only
model and the five-signal comparator, is it calibrated, and is 'how long' a duration law that is self-similar across
thresholds?

Model: landmark Weibull proportional hazards. Every bar is an origin; T = bars until BTC.D first closes k points below
today's level (the harness tte), right-censored at 104 weeks. S(h | z) = exp(-(h / lambda)^alpha * exp(beta . z)),
z standardised with training-window mean/sd clipped at 3, Newton MLE on (log alpha, log lambda, beta) with ridge 1 on
beta. Expanding window from 2016-06, first forecast 2019-01-06, refit every 13 weeks. At a refit R every training
origin t contributes observed time min(T_t, R - t) and an event only if t + T_t <= R (administrative censoring: nothing
after the refit date is read). Nested models: clock-only, level-only, five-signal (as a hazard and as the logistic it
already is), full, full without M2, full plus seven random-walk decoys. Observable semi-Markov states BASE / FALL /
RECOVERY from crossing rules with their own confirmation delay feed the renewal clock. Daily twin at k = 2 points
(1.5 and 3 as checks), a 3-day middle rung, daily-to-weekly transfer of the standardised betas, a cross-scale duration
law, Weibull sojourn laws per state across thresholds, and a remaining-duration model. Nulls: shifted targets through
standardisation and the Weibull refit, IAAFT surrogates and fBm paths of BTC.D with the real covariates.

Fixer round (after two attacker reviews): rows outside the plan's nested list (cov, cov_renewal, five_clock, m2only_hazard,
fast, one_<covariate>, the ridge-in-crossing-units and transfer_<component> rows) are labelled POST-HOC everywhere and
nothing is promoted; Brier vs base is printed by era for every row (cov_renewal is above base in 2021-22); every row
gets the full shifted-target draw count with era-level p from the pooled shift; the transfer ratio carries a paired
block band and is declared uninterpretable when the weekly model does not beat the clock; increments are reported
against fixed5 AND M2-alone with block and episode bands; Harrell's C is split into within / between run-up pairs and
recomputed on one origin per run-up; calibration (and the recalibrated reading) is given for every model whose number is
quoted; the fBm surrogate is anchored at the real logit median; the administrative-censoring assertion checks the raw
harness columns and a truncated-panel recomputation; OOS spells use R = N - 1 like the PIT; the duration law is labelled
descriptive and a point-in-time remaining-duration form from the crossing bar is scored beside it.

  python3 research/btcd_fractal/study8_hazard.py --data research/btcd_fractal/data --out research/btcd_fractal/out8/hazard [--nulls N] [--fast]

Point in time: states and the clock come from a causal scan (no look-back relabelling); scalers and Weibull parameters
from training rows only; the harness tte is never used raw in training (administrative censoring asserted at every
refit); the duration law is walked forward event by event; the three big events are scored once. No fit-based
p-values are printed: inference only from shifted-target nulls, surrogates and block bootstraps.

Harness note: study8_common.walk_forward drops rows whose label is unknown; survival training needs those rows as
censored spells, so the survival walk lives in this module (surv_walk) with the same schedule, start and window as the
harness. Harrell's C, Kaplan-Meier, the Weibull/Cox/discrete-hazard fitters and the C-index block bootstrap are module
helpers (study8_common has none); the five-signal comparator goes through study8_baselines.run_fixed unchanged.
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

# ------------------------------------------------------------------------------------------- frozen definitions
K_W = (5.0, 10.0)                      # weekly thresholds (points)
K_D = 2.0                              # daily headline threshold
K_D_CHECKS = (1.5, 3.0)                # daily checks (full run only)
K_3D = 3.0                             # 3-day middle rung (full run only)
REV = 0.6                              # trough confirmed on a REV * k bounce from the running minimum
HORIZON_W = 104                        # censoring horizon in weeks
COV = ["btc_dd_ath", "m2_yoy", "ethbtc_ret26w", "btcd_vol13w", "usdtd_vsma30w"]
CLOCK = ["clock_renewal", "halving_sin", "halving_cos"]
LEVEL = ["btcd_fromhi52w"]
FIVE = list(B.SIGNALS)
N_DECOYS = 7
DECOYS = [f"decoy{j}" for j in range(N_DECOYS)]
RIDGE_BETA = 1.0
BINS_W = [(1, 4), (5, 13), (14, 26), (27, 52), (53, 78), (79, 104)]   # discrete-time baseline bins (weeks)
SOJOURN_K = (1.0, 1.5, 2.0, 3.0, 5.0, 10.0)
LAW_MAX_SIZE = 5.0                     # the duration law trains on daily events smaller than this
TRAIN_START = "2016-06-01"
FIRST = "2019-01-06"
REFIT_W = 13
HGRID = np.arange(1, HORIZON_W + 1, dtype=float)    # weeks
FAST = ["ethbtc_ret26w", "btcd_vol13w", "usdtd_vsma30w", "clock_renewal"]   # the within-cycle covariates: COV without the two once-per-cycle series (M2 y/y, BTC drawdown)
MODELS = {"clock": CLOCK, "level": LEVEL, "five": FIVE, "full": COV + CLOCK, "full_noM2": [c for c in COV if c != "m2_yoy"] + CLOCK,
          "full_decoys": COV + CLOCK + DECOYS,
          # POST-HOC rows (added after the first results were seen; decomposition and diagnosis, never the headline):
          "cov": COV, "cov_renewal": COV + ["clock_renewal"], "five_clock": FIVE + CLOCK, "m2only_hazard": ["m2_yoy"], "fast": FAST}
MODELS.update({f"one_{c}": [c] for c in COV + ["clock_renewal"]})       # single-covariate Weibull rows (post-hoc)
PLAN_ROWS = ["clock", "level", "five", "full", "full_noM2", "full_decoys"]                 # the plan's pre-registered nested list
HEADLINE_ROWS = PLAN_ROWS[:3] + ["cov", "cov_renewal", "five_clock", "m2only_hazard", "fast"] + PLAN_ROWS[3:]
SINGLE_ROWS = [f"one_{c}" for c in COV + ["clock_renewal"]]
POST_HOC_ROWS = [r for r in HEADLINE_ROWS + SINGLE_ROWS if r not in PLAN_ROWS] + ["full_ridgeEff", "cov_renewal_ridgeEff", "transfer_cov_renewal", "transfer_fast"]
OWNER_DAYS = 90.0


# ------------------------------------------------------------------------------------------- states (causal scan)
def crossing_states(vals, k, rev=REV):
    """BASE (0): not yet k below the running maximum since the last confirmed trough. FALL (1): from the first close k
    or more below that maximum (the crossing) until the trough is confirmed by a rev*k bounce. RECOVERY (2): from the
    confirmation until the pre-fall maximum is regained (BASE) or a new crossing k below the recovery high (FALL).
    Returns state per bar, index of the last confirmation per bar (-1 before any), completed events, sojourns."""
    vals = np.asarray(vals, float)
    n = len(vals)
    state = np.zeros(n, int)
    conf = np.full(n, -1)
    events, soj = [], {"BASE": [], "FALL": [], "RECOVERY": []}
    st, runmax, runmax_i, entered, last_conf = 0, vals[0], 0, 0, -1
    fall_min = fall_min_i = cross_i = rec_max = rec_max_i = None
    for i in range(n):
        x = vals[i]
        if st == 0:
            if x > runmax:
                runmax, runmax_i = x, i
            elif x <= runmax - k:
                soj["BASE"].append(i - entered)
                st, cross_i, fall_min, fall_min_i, entered = 1, i, x, i, i
        elif st == 1:
            if x < fall_min:
                fall_min, fall_min_i = x, i
            elif x >= fall_min + rev * k:
                last_conf = i
                events.append({"peak_i": runmax_i, "cross_i": cross_i, "trough_i": fall_min_i, "conf_i": i, "peak": runmax, "trough": fall_min,
                               "size": runmax - fall_min, "dur": fall_min_i - runmax_i, "dur_cross": fall_min_i - cross_i})
                soj["FALL"].append(max(1, fall_min_i - cross_i))
                st, rec_max, rec_max_i, entered = 2, x, i, fall_min_i
        else:
            if x > runmax:
                soj["RECOVERY"].append(i - entered)
                st, runmax, runmax_i, entered = 0, x, i, i
            else:
                if x > rec_max:
                    rec_max, rec_max_i = x, i
                if x <= rec_max - k:
                    soj["RECOVERY"].append(i - entered)
                    st, cross_i, fall_min, fall_min_i, entered = 1, i, x, i, i
                    runmax, runmax_i = rec_max, rec_max_i
        state[i] = st
        conf[i] = last_conf
    return state, conf, events, soj


def clock_series(vals, k, bpw):
    state, conf, _, _ = crossing_states(vals, k)
    i = np.arange(len(vals))
    weeks = np.where(conf >= 0, i - conf, i) / bpw
    return np.log1p(weeks), state, conf


def hazard_features(P, X, freq, k, decoys_daily):
    """Covariates + clock + state + decoys for threshold k on panel P (features X from the harness)."""
    cols = list(dict.fromkeys(COV + LEVEL + FIVE))
    F = X[cols].copy()
    bpw = C.bars_per_week(freq)
    clock, state, conf = clock_series(P["BTC.D"].values, k, bpw)
    F["clock_renewal"] = clock
    ph = 2 * np.pi * X["days_since_halving"].values / 1461.0
    F["halving_sin"], F["halving_cos"] = np.sin(ph), np.cos(ph)
    F["state"] = state
    for j in range(N_DECOYS):
        s = decoys_daily[j].reindex(P.index).ffill()
        F[f"decoy{j}"] = (s - s.rolling(C.bars(30, freq)).mean()).values
    return F, state, conf


def targets_for_k(P, freq, k):
    """Harness targets for one threshold with generic names: tte, cens, fall13, fall26, onset26 (fall26 AND fresh)."""
    Y = C.targets(P, freq, falls=(k,), horizons=(13, 26), tte_max_weeks=HORIZON_W)
    ik = int(k)
    out = pd.DataFrame({"tte": Y[f"tte{ik}"], "cens": Y[f"cens{ik}"], "fall13": Y[f"fall{ik}_13w"], "fall26": Y[f"fall{ik}_26w"], "y13": Y["y13"]}, index=P.index)
    fr = C.fresh_mask(P, freq).astype(float)
    out["onset26"] = (out["fall26"] * fr).where(out["fall26"].notna())
    return out


# ------------------------------------------------------------------------------------------- Weibull PH
def weib_ll(theta, ly, d, Z, off, pen):
    al = np.exp(theta[0])
    u = np.minimum(al * (ly - theta[1]) + Z @ theta[2:] + off, 50.0)
    return float(np.sum(d * (theta[0] + u - ly)) - np.sum(np.exp(u)) - 0.5 * np.sum(pen * theta ** 2))


def weib_fit(y, d, Z, lam=RIDGE_BETA, init=None, offset=None, it=80):
    """MLE of (log alpha, log lambda, beta) for S(t|z) = exp(-(t/lambda)^alpha exp(z beta + offset)); ridge on beta."""
    y = np.maximum(np.asarray(y, float), 1e-3)
    d = np.asarray(d, float)
    Z = np.asarray(Z, float).reshape(len(y), -1)
    ly = np.log(y)
    n, p = Z.shape
    off = np.zeros(n) if offset is None else np.asarray(offset, float)
    pen = np.r_[0.0, 0.0, np.ones(p) * lam]
    if init is None or len(init) != p + 2:
        theta = np.r_[0.0, np.log(max(y.sum() / max(d.sum(), 1.0), 1e-3)), np.zeros(p)]
    else:
        theta = np.array(init, float)
    cur = weib_ll(theta, ly, d, Z, off, pen)
    for _ in range(it):
        al = np.exp(theta[0])
        w = al * (ly - theta[1])
        u = np.minimum(w + Z @ theta[2:] + off, 50.0)
        H = np.exp(u)
        du = np.c_[w, -al * np.ones(n), Z]
        g = (d[:, None] * du).sum(0) - (H[:, None] * du).sum(0) - pen * theta
        g[0] += d.sum()
        c = d - H
        Hs = -(du * H[:, None]).T @ du
        Hs[0, 0] += np.sum(c * w)
        Hs[0, 1] -= np.sum(c * al)
        Hs[1, 0] -= np.sum(c * al)
        Hs -= np.diag(pen)
        try:
            step = np.linalg.solve(Hs, -g)
        except np.linalg.LinAlgError:
            step = g / (np.abs(g).max() + 1e-9)
        if g @ step <= 0 or not np.all(np.isfinite(step)):
            step = g / (np.abs(g).max() + 1e-9)
        nrm = np.abs(step).max()
        if nrm > 5.0:
            step = step * (5.0 / nrm)
        s, new, v = 1.0, theta, cur
        for _h in range(25):
            new = theta + s * step
            new[0] = np.clip(new[0], -4.0, 4.0)       # alpha in [0.02, 55]
            new[1] = np.clip(new[1], -8.0, 12.0)      # lambda in weeks (or days for sojourns)
            v = weib_ll(new, ly, d, Z, off, pen)
            if np.isfinite(v) and v >= cur:
                break
            s *= 0.5
        else:
            break
        theta = new
        if v - cur < 1e-10 * (1 + abs(cur)):
            cur = v
            break
        cur = v
    return theta


def weib_S(theta, Z, h, offset=None):
    """Survival matrix (rows x len(h)) at times h (weeks)."""
    Z = np.asarray(Z, float).reshape(-1, len(theta) - 2)
    al = np.exp(theta[0])
    eta = Z @ theta[2:] + (0.0 if offset is None else offset)
    lh = al * (np.log(np.asarray(h, float)) - theta[1])
    return np.exp(-np.exp(np.minimum(lh[None, :] + eta[:, None], 50.0)))


def admin_censor(tte, cens, R, hb):
    """Observed spells for origins 0..R-1 as known at bar R: obs = min(T, R - t, hb), event only if t + T <= R.
    The assertions check against the RAW harness columns, not against obs (which satisfies t + obs <= R by
    construction): every event row must carry the harness tte with its crossing at or before R, and every row whose
    harness crossing is known must either cross after R or have been cut at the horizon."""
    t = np.arange(R)
    raw = tte[:R]
    known = np.isfinite(raw) & (cens[:R] == 0)
    T = np.where(known, raw, np.inf)
    rem = np.minimum(R - t, hb).astype(float)
    ev = T <= rem
    obs = np.where(ev, T, rem)
    assert np.all(obs[ev] == raw[ev]) and np.all(t[ev] + raw[ev] <= R), "administrative censoring violated: event row reads past R"
    late = known & ~ev
    assert np.all((t[late] + raw[late] > R) | (obs[late] >= hb)), "administrative censoring violated: a crossing before R is censored"
    return obs, ev.astype(float)


def oos_spells(tte, cens, N, hb):
    """Spells for scoring at the data end. The last observable close is bar N - 1, so R = N - 1 (the same convention
    as pit_values); the last origin has no future and is padded with obs 0, which the obs >= 1 filters exclude."""
    obs, ev = admin_censor(tte, cens, N - 1, hb)
    return np.r_[obs, 0.0], np.r_[ev, 0.0]


def admin_censor_truncation_check(P, freq, k, R, hb):
    """Recompute the harness targets on the panel truncated at bar R and check that admin_censor on the full-panel
    columns gives the same spells as the truncated panel knows: the strong form of the censoring assertion."""
    Yt = targets_for_k(P.iloc[:R + 1], freq, k)
    Yf = targets_for_k(P, freq, k)
    obs, ev = admin_censor(Yf["tte"].values, Yf["cens"].values, R, hb)
    tt, cc = Yt["tte"].values[:R], Yt["cens"].values[:R]
    t = np.arange(R)
    ev_t = np.isfinite(tt) & (cc == 0)
    obs_t = np.where(ev_t, tt, np.minimum(R - t, hb))
    return {"R": str(P.index[R].date()), "rows": int(R), "eventsMatch": bool(np.array_equal(ev > 0.5, ev_t)), "obsMatch": bool(np.allclose(obs, obs_t)),
            "maxAbsObsDiff": float(np.max(np.abs(obs - obs_t)))}


def surv_walk(Fv, tte, cens, idx, freq, min_events=3, lam=RIDGE_BETA, fixed_beta=None, keep_insample=False, min_train=60, lam_eff=False):
    """Expanding-window landmark Weibull walk. Returns S (rows x HGRID), refits, in-sample P26 per refit, last fit.
    lam_eff: scale the ridge by (training origins / distinct crossing bars) so the penalty is sized to the number of
    independent events rather than to overlapping origins (a check row; the pre-registered ridge is lam on origins)."""
    N = len(idx)
    bpw = C.bars_per_week(freq)
    hb, step = C.bars(HORIZON_W, freq), C.bars(REFIT_W, freq)
    t = int(np.searchsorted(idx, pd.Timestamp(FIRST)))
    S = np.full((N, len(HGRID)), np.nan)
    refits, insample, theta, last, thetas = [], [], None, None, {}
    while t < N:
        tr = np.arange(0, t)
        tr = tr[np.isfinite(Fv[tr]).all(1)]
        if len(tr) >= min_train:
            obs, ev = admin_censor(tte, cens, t, hb)
            obs, ev = obs[tr], ev[tr]
            if ev.sum() >= min_events:
                mu, sd = C.zfit(Fv[tr])
                Z = C.zapply(Fv[tr], mu, sd)
                n_cross = len(np.unique((tr + obs)[ev > 0.5]))
                lam_use = lam * len(tr) / max(n_cross, 1) if lam_eff else lam
                if fixed_beta is None:
                    theta = weib_fit(obs / bpw, ev, Z, lam_use, init=theta)
                else:
                    beta = fixed_beta(idx[t])
                    if beta is None:
                        t += step
                        continue
                    th2 = weib_fit(obs / bpw, ev, np.zeros((len(tr), 0)), lam, init=(None if theta is None else theta[:2]), offset=Z @ beta)
                    theta = np.r_[th2[:2], beta]
                te = np.arange(t, min(t + step, N))
                te = te[np.isfinite(Fv[te]).all(1)]
                if len(te):
                    S[te] = weib_S(theta, C.zapply(Fv[te], mu, sd), HGRID)
                n_admin = int(((ev == 0) & ((t - tr) < hb)).sum())
                refits.append({"t": str(idx[t].date()), "nTrain": int(len(tr)), "nEvents": int(ev.sum()), "nAdminCensored": n_admin, "nCrossingBars": int(n_cross),
                               "ridge": round(float(lam_use), 2)})
                thetas[idx[t]] = theta.copy()
                if keep_insample:
                    insample.append((tr, 1 - weib_S(theta, Z, [26.0])[:, 0]))
                last = {"theta": theta.copy(), "mu": mu, "sd": sd, "tr": tr, "obs": obs, "ev": ev, "t": t}
        t += step
    return {"S": S, "refits": refits, "insample": insample, "last": last, "thetas": thetas}


# ------------------------------------------------------------------------------------------- Cox and discrete hazard
def cox_fit(time, event, Z, lam=RIDGE_BETA, it=40):
    o = np.argsort(-time, kind="stable")
    Z, d, t = Z[o], event[o], time[o]
    n, p = Z.shape
    last = np.searchsorted(-t, -t, side="right") - 1          # last index of each tie group (descending order)
    beta = np.zeros(p)
    for _ in range(it):
        w = np.exp(np.clip(Z @ beta, -30, 30))
        S0 = np.cumsum(w)[last]
        S1 = np.cumsum(w[:, None] * Z, 0)[last]
        S2 = np.cumsum(w[:, None, None] * Z[:, :, None] * Z[:, None, :], 0)[last]
        m1 = S1 / S0[:, None]
        g = (d[:, None] * (Z - m1)).sum(0) - lam * beta
        Hm = -(d[:, None, None] * (S2 / S0[:, None, None] - m1[:, :, None] * m1[:, None, :])).sum(0) - lam * np.eye(p)
        try:
            step = np.linalg.solve(Hm, -g)
        except np.linalg.LinAlgError:
            break
        beta = beta + step
        if np.abs(step).max() < 1e-8:
            break
    return beta


def cox_walk(Fv, tte, cens, idx, freq):
    """Cox partial likelihood on the same schedule; returns the risk score (z beta) per OOS row."""
    N = len(idx)
    bpw = C.bars_per_week(freq)
    hb, step = C.bars(HORIZON_W, freq), C.bars(REFIT_W, freq)
    t = int(np.searchsorted(idx, pd.Timestamp(FIRST)))
    risk = np.full(N, np.nan)
    while t < N:
        tr = np.arange(0, t)
        tr = tr[np.isfinite(Fv[tr]).all(1)]
        if len(tr) >= 60:
            obs, ev = admin_censor(tte, cens, t, hb)
            obs, ev = obs[tr], ev[tr]
            if ev.sum() >= 3:
                mu, sd = C.zfit(Fv[tr])
                beta = cox_fit(obs / bpw, ev, C.zapply(Fv[tr], mu, sd))
                te = np.arange(t, min(t + step, N))
                te = te[np.isfinite(Fv[te]).all(1)]
                risk[te] = C.zapply(Fv[te], mu, sd) @ beta
        t += step
    return risk


def dt_hazard_walk(Fv, tte, cens, idx, freq="W"):
    """Discrete-time logistic hazard on the person-period expansion with six baseline bins (weekly only)."""
    N = len(idx)
    hb, step = C.bars(HORIZON_W, freq), C.bars(REFIT_W, freq)
    nb = len(BINS_W)
    binof = np.zeros(HORIZON_W + 1, int)
    for bi, (lo, hi) in enumerate(BINS_W):
        binof[lo:hi + 1] = bi
    t = int(np.searchsorted(idx, pd.Timestamp(FIRST)))
    S = np.full((N, len(HGRID)), np.nan)
    while t < N:
        tr = np.arange(0, t)
        tr = tr[np.isfinite(Fv[tr]).all(1)]
        if len(tr) >= 60:
            obs, ev = admin_censor(tte, cens, t, hb)
            obs, ev = obs[tr].astype(int), ev[tr]
            if ev.sum() >= 3:
                mu, sd = C.zfit(Fv[tr])
                Z = C.zapply(Fv[tr], mu, sd)
                rows_i = np.repeat(np.arange(len(tr)), obs)
                period = np.concatenate([np.arange(1, o + 1) for o in obs])
                y = np.concatenate([np.r_[np.zeros(o - 1), e] for o, e in zip(obs, ev)])
                Bm = np.zeros((len(period), nb))
                Bm[np.arange(len(period)), binof[period]] = 1.0
                A = np.c_[Bm, Z[rows_i]]
                w = C.logistic_fit(A, y, lam=0.1)
                te = np.arange(t, min(t + step, N))
                te = te[np.isfinite(Fv[te]).all(1)]
                if len(te):
                    Zt = C.zapply(Fv[te], mu, sd)
                    eta_b = w[1:1 + nb][binof[1:]] + w[0]                 # per period 1..104
                    h = 1 / (1 + np.exp(-(eta_b[None, :] + (Zt @ w[1 + nb:])[:, None])))
                    S[te] = np.cumprod(1 - h, axis=1)
        t += step
    return S


# ------------------------------------------------------------------------------------------- metrics helpers
def cindex(risk, time, event):
    """Harrell's C: among pairs where i has the event and i's time is shorter than j's observed time, the share with
    risk_i > risk_j (ties half)."""
    risk, time, event = np.asarray(risk, float), np.asarray(time, float), np.asarray(event, float)
    m = np.isfinite(risk) & np.isfinite(time) & np.isfinite(event)
    risk, time, event = risk[m], time[m], event[m]
    o = np.argsort(time, kind="stable")
    risk, time, event = risk[o], time[o], event[o]
    conc = comp = 0.0
    for i in np.where(event > 0.5)[0]:
        j = np.searchsorted(time, time[i], side="right")
        rj = risk[j:]
        if len(rj) == 0:
            continue
        conc += float((risk[i] > rj).sum()) + 0.5 * float((risk[i] == rj).sum())
        comp += len(rj)
    return None if comp == 0 else float(conc / comp)


def c_split(risk, obs, ev, pos):
    """Harrell's C restricted to comparable pairs whose origins share the same crossing bar (within a run-up: does the
    model rank the later origin riskier) and to pairs from different run-ups (between: mostly a ranking of eras).
    With every bar an origin almost every comparable pair is a between-run-up pair."""
    r, t, e = risk[pos], obs[pos].astype(float), ev[pos]
    cbar = np.where(e > 0.5, pos + obs[pos].astype(int), -1)
    o = np.argsort(t, kind="stable")
    r, t, e, cbar = r[o], t[o], e[o], cbar[o]
    cs = cd = ns = nd = 0.0
    for i in np.where(e > 0.5)[0]:
        j = np.searchsorted(t, t[i], side="right")
        same = cbar[j:] == cbar[i]
        c = (r[i] > r[j:]) + 0.5 * (r[i] == r[j:])
        cs += c[same].sum()
        ns += same.sum()
        cd += c[~same].sum()
        nd += (~same).sum()
    return {"within": (None if ns == 0 else round(float(cs / ns), 3)), "nWithin": int(ns), "between": (None if nd == 0 else round(float(cd / nd), 3)), "nBetween": int(nd)}


def runup_blocks(pos, obs, ev, bl):
    """Blocks of positions (local indices into pos): one block per run-up (origins sharing a crossing bar) and the
    censored origins in blocks of bl bars."""
    cbar = np.where(ev[pos] > 0.5, pos + obs[pos].astype(int), -1)
    blocks = [np.where(cbar == cb)[0] for cb in np.unique(cbar[cbar >= 0])]
    cen = np.where(cbar < 0)[0]
    blocks += [cen[s:s + bl] for s in range(0, len(cen), bl)]
    return blocks


def one_per_runup(pos, obs, ev, bl):
    """The median origin of each run-up plus every bl-th censored origin (so C is a ranking of crossings, not of
    overlapping origins)."""
    cbar = np.where(ev[pos] > 0.5, pos + obs[pos].astype(int), -1)
    keep = [pos[cbar == cb][(cbar == cb).sum() // 2] for cb in np.unique(cbar[cbar >= 0])]
    keep += list(pos[cbar < 0][::bl])
    return np.array(sorted(keep), int)


def blocks_band(fn, blocks, n, rng):
    vals = []
    for _ in range(n):
        pick = rng.integers(0, len(blocks), size=len(blocks))
        v = fn(np.concatenate([blocks[k] for k in pick]))
        if v is not None and np.isfinite(v):
            vals.append(float(v))
    v = np.array(vals)
    return {"n": len(v), "q05": round(float(np.quantile(v, 0.05)), 3), "q50": round(float(np.quantile(v, 0.5)), 3), "q95": round(float(np.quantile(v, 0.95)), 3)} if len(v) else {"n": 0}


def c_block(risk, obs, ev, mask, rng, n_boot, bpw, thin=1):
    """Harrell's C on the masked origins with: a 26-week block band, the within / between run-up split, C on one
    origin per run-up, and a run-up (episode) bootstrap band."""
    pos = np.where(mask)[0][::thin]
    r, tt, ee = risk[pos], obs[pos] / bpw, ev[pos]
    cv = cindex(r, tt, ee)
    out = {"C": (None if cv is None else round(cv, 3)), "nEvents": int(ee.sum()), "nOrigins": int(len(pos))}
    if cv is None:
        return out
    bl = max(1, int(round(26 * bpw / thin)))
    out["C_split"] = c_split(risk, obs, ev, pos)
    one = one_per_runup(pos, obs, ev, bl)
    c1 = cindex(risk[one], obs[one] / bpw, ev[one])
    out["C_onePerRunup"] = (None if c1 is None else round(c1, 3))
    out["nRunups"] = int(ev[one].sum())
    if n_boot:
        out["C_band"] = boot_band(lambda ii: cindex(r[ii], tt[ii], ee[ii]), len(pos), n_boot, bl, rng)
        out["C_runupBand"] = blocks_band(lambda ii: cindex(r[ii], tt[ii], ee[ii]), runup_blocks(pos, obs, ev, bl), n_boot, rng)
    return out


def paired_gain(s, ref, y, pos, n_boot, rng, bl=26):
    """Pooled AUC of s minus AUC of ref on the same rows, with a 26-week block band and an episode band (blocks = each
    positive episode with its 26-week run-up and the negative stretches between)."""
    d = C.auc(s[pos], y[pos]) - C.auc(ref[pos], y[pos])

    def f(ii):
        return (C.auc(s[pos][ii], y[pos][ii]) or 0) - (C.auc(ref[pos][ii], y[pos][ii]) or 0)
    yy = y[pos]
    N = len(pos)
    cuts = [0]
    for s_, e_ in C.episodes(yy):
        cuts += [max(0, s_ - bl), e_ + 1]
    cuts = sorted(set(c for c in cuts if 0 <= c <= N)) + [N]
    blocks = [np.arange(a_, b_) for a_, b_ in zip(cuts[:-1], cuts[1:]) if b_ > a_]
    return {"gain": round(float(d), 3), "blockBand": boot_band(f, N, n_boot, bl, rng), "episodeBand": blocks_band(f, blocks, n_boot, rng), "nEpisodeBlocks": len(blocks)}


def km_curve(time, event, grid):
    o = np.argsort(time)
    t, e = time[o], event[o]
    n = len(t)
    S, out = 1.0, []
    ut = np.unique(t[e > 0.5])
    curves = []
    for u in ut:
        at_risk = n - np.searchsorted(t, u, side="left")
        dd = float(((t == u) & (e > 0.5)).sum())
        S *= 1 - dd / max(at_risk, 1)
        curves.append((u, S))
    for h in grid:
        v = 1.0
        for u, s in curves:
            if u <= h:
                v = s
        out.append(v)
    return np.array(out)


def block_indices(N, bl, rng):
    starts = rng.integers(0, N, size=int(np.ceil(N / bl)))
    return np.concatenate([(np.arange(s, s + bl) % N) for s in starts])[:N]


def boot_band(fn, N, n, bl, rng):
    vals = []
    for _ in range(n):
        v = fn(block_indices(N, bl, rng))
        if v is not None and np.isfinite(v):
            vals.append(float(v))
    v = np.array(vals)
    return {"n": len(v), "q05": round(float(np.quantile(v, 0.05)), 3), "q50": round(float(np.quantile(v, 0.5)), 3), "q95": round(float(np.quantile(v, 0.95)), 3)} if len(v) else {"n": 0}


def era_of(idx):
    out = np.full(len(idx), -1)
    for i, (name, fr, to) in enumerate(C.ERAS):
        out[(idx >= pd.Timestamp(fr)) & (idx < pd.Timestamp(to))] = i
    return out


def lg(p):
    p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def sig(x):
    return 1 / (1 + np.exp(-np.asarray(x, float)))


def evaluate(S, idx, Y, freq, fresh, tte, cens, rng, n_boot, thin=1):
    """AUC/Brier of P13/P26 by era, pooled, fresh-start and onset; Harrell's C with a 26-week block-bootstrap band."""
    p13 = pd.Series(1 - S[:, 12], index=idx)
    p26 = pd.Series(1 - S[:, 25], index=idx)
    out = {"auc13": C.metrics(p13, Y["fall13"], True, is_prob=True), "auc26": C.metrics(p26, Y["fall26"], True, is_prob=True),
           "onset26": C.metrics(p26, Y["onset26"], True, is_prob=True),
           "fresh26": C.metrics(p26[fresh], Y["fall26"][fresh], True, is_prob=True)}
    # era-demeaned AUC (level removed within each era)
    e = era_of(idx)
    lp = lg(p26.values)
    dm = lp.copy()
    for i in range(3):
        m = (e == i) & np.isfinite(lp)
        if m.sum():
            dm[m] = lp[m] - lp[m].mean()
    post = e >= 0
    v = C.auc(dm[post], Y["fall26"].values[post])
    out["auc26_eraDemeaned"] = None if v is None else round(v, 3)
    # Harrell's C on OOS origins, right-censored at the last observable close (R = N - 1, as pit_values)
    hb = C.bars(HORIZON_W, freq)
    bpw = C.bars_per_week(freq)
    obs, ev = oos_spells(tte, cens, len(idx), hb)
    m = post & np.isfinite(p26.values) & (obs >= 1)
    out.update(c_block(p26.values, obs, ev, m, rng, n_boot, bpw, thin))
    return out, p13, p26


def pit_values(S, idx, tte, cens, freq):
    """PIT for uncensored OOS origins, one per distinct crossing bar (the median origin of each). Returns the raw
    u = S_t(T_t) the plan asks for and the censoring-adjusted v = (1 - S_t(T_t)) / (1 - S_t(C_t)), C_t = min(104w,
    data end - t): for an event known to fall before C_t only v is uniform under a correct model (u is biased toward 1
    by construction when S_t(C_t) is large)."""
    bpw = C.bars_per_week(freq)
    N = len(idx)
    hb = C.bars(HORIZON_W, freq)
    post = np.arange(N) >= np.searchsorted(idx, pd.Timestamp(FIRST))
    ok = post & np.isfinite(S[:, 0]) & np.isfinite(tte) & (cens == 0)
    pos = np.where(ok)[0]
    cross = pos + tte[pos].astype(int)
    u_out, v_out, dates = [], [], []
    for cb in np.unique(cross):
        grp = pos[cross == cb]
        o = grp[len(grp) // 2]
        T = tte[o] / bpw
        Cc = min(hb, N - 1 - o) / bpw
        u = float(np.interp(T, HGRID, S[o]))
        SC = float(np.interp(Cc, HGRID, S[o]))
        v = (1 - u) / max(1 - SC, 1e-9)
        u_out.append(u)
        v_out.append(float(np.clip(v, 0, 1)))
        dates.append(str(idx[cb].date()))
    return np.array(u_out), np.array(v_out), dates


def ks_uniform(u):
    u = np.sort(u)
    n = len(u)
    if n == 0:
        return None
    i = np.arange(1, n + 1)
    return float(max(np.max(i / n - u), np.max(u - (i - 1) / n)))


# ------------------------------------------------------------------------------------------- null workers (fork)
_G = {}


def _run_scale(F, cols, Y, idx, freq, tte=None, cens=None, min_events=3, lam_eff=False):
    Fv = F[cols].values.astype(float)
    tte = Y["tte"].values if tte is None else tte
    cens = Y["cens"].values if cens is None else cens
    w = surv_walk(Fv, tte, cens, idx, freq, min_events=min_events, lam_eff=lam_eff)
    return w


def _score(S, Y, idx, freq, fresh):
    p26 = pd.Series(1 - S[:, 25], index=idx)
    p13 = pd.Series(1 - S[:, 12], index=idx)
    met26 = C.metrics(p26, Y["fall26"], True)
    met13 = C.metrics(p13, Y["fall13"], True)
    hb = C.bars(HORIZON_W, freq)
    obs, ev = oos_spells(Y["tte"].values, Y["cens"].values, len(idx), hb)
    post = np.arange(len(idx)) >= np.searchsorted(idx, pd.Timestamp(FIRST))
    m = post & np.isfinite(p26.values) & (obs >= 1)
    pos = np.where(m)[0][::(7 if freq == "D" else 1)]
    cv = cindex(p26.values[pos], obs[pos], ev[pos])
    fr = C.metrics(p26[fresh], Y["fall26"][fresh], True).get("pooled", {}).get("auc")
    return {"auc26": met26.get("pooled", {}).get("auc"), "auc13": met13.get("pooled", {}).get("auc"), "C": cv, "fresh26": fr,
            "eras26": {k: v.get("auc") for k, v in met26.items() if k != "pooled"}}


def _shift_worker(args):
    scale, model, k_shift = args
    g = _G[scale]
    Ys = C.shift_targets(g["Y"], k_shift)
    w = _run_scale(g["F"], MODELS[model], Ys, g["idx"], g["freq"])
    return _score(w["S"], Ys, g["idx"], g["freq"], g["fresh"])


def _within_era_worker(args):
    scale, model, era_i, k_shift = args
    g = _G[scale]
    name, fr, to = C.ERAS[era_i]
    Y = g["Y"]
    m = (Y.index >= pd.Timestamp(fr)) & (Y.index < pd.Timestamp(to))
    pos = np.where(m)[0]
    Ys = Y.copy()
    for c in Y.columns:
        v = Y[c].values.copy()
        v[pos] = np.roll(v[pos], k_shift)
        Ys[c] = v
    w = _run_scale(g["F"], MODELS[model], Ys, g["idx"], g["freq"])
    p26 = pd.Series(1 - w["S"][:, 25], index=g["idx"])
    return C.metrics(p26, Ys["fall26"], True).get(name, {}).get("auc")


def _transfer_worker(args):
    """Shifted-target null for the daily-to-weekly transfer: the weekly targets rolled by k weeks and the daily targets
    by 7k days, the daily walk refit on the rolled daily targets, its betas frozen into the weekly walk, scored."""
    name, k_shift = args
    gw, gd = _G["W:5"], _G[f"D:{K_D:g}"]
    Yw = C.shift_targets(gw["Y"], k_shift)
    Yd = C.shift_targets(gd["Y"], 7 * k_shift)
    wD = _run_scale(gd["F"], MODELS[name], Yd, gd["idx"], "D")
    betas = {d: th[2:].copy() for d, th in wD["thetas"].items()}

    def fixed_beta(date):
        keys = [d for d in betas if d <= date]
        return betas[max(keys)] if keys else None
    wT = surv_walk(gw["F"][MODELS[name]].values.astype(float), Yw["tte"].values, Yw["cens"].values, gw["idx"], "W", fixed_beta=fixed_beta)
    return _score(wT["S"], Yw, gw["idx"], "W", gw["fresh"])


def surrogate_panel(sur_logit_daily):
    """Rebuild the BTC.D-derived inputs (targets, clock, vol, from-high, fresh mask) from a surrogate daily logit path."""
    g = _G["daily_base"]
    sd = pd.Series(100 / (1 + np.exp(-sur_logit_daily)), index=g["didx"])
    out = {}
    for scale in ("W",):
        gw = _G[scale]
        Pw = sd.resample("W-SUN").last().ffill().reindex(gw["full_idx"]).ffill()
        Pf = pd.DataFrame({"BTC.D": Pw})
        x = pd.Series(C.logit(Pw.values), index=Pw.index)
        F = gw["F_full"].copy()
        F["btcd_vol13w"] = (x.diff().rolling(13).std() * np.sqrt(52)).values
        F["btcd_fromhi52w"] = (x - x.rolling(52).max()).values
        F["clock_renewal"] = clock_series(Pw.values, gw["k"], 1.0)[0]
        Yk = targets_for_k(Pf, "W", gw["k"])
        fresh = C.fresh_mask(Pf, "W").values
        cut = Pw.index >= pd.Timestamp(TRAIN_START)
        out[scale] = (F[cut], Yk[cut], fresh[cut])
    return out, sd


def _surrogate_worker(args):
    kind, sur = args
    pan, sd = surrogate_panel(sur)
    F, Yk, fresh = pan["W"]
    w = _run_scale(F, MODELS["full"], Yk, F.index, "W")
    sc = _score(w["S"], Yk, F.index, "W", fresh)
    # duration-law slope on the surrogate's own daily events (size < LAW_MAX_SIZE), vol from the surrogate itself
    vol13 = (pd.Series(C.logit(sd.values), index=sd.index).diff().rolling(91).std() * np.sqrt(365)).values
    law = fit_law(law_events(sd.values, vol13, k=1.0), None)
    return {"kind": kind, "auc26": sc["auc26"], "C": sc["C"], "lawSlope": (None if law is None else law["beta"][1]), "lawVol": (None if law is None else law["beta"][2])}


# ------------------------------------------------------------------------------------------- duration block
def law_events(b_daily, vol_daily, k=1.0, rev=REV):
    """Reversal-ended daily events with size, duration (peak to trough, days) and vol at the peak."""
    _, _, ev, _ = crossing_states(b_daily, k, rev)
    rows = []
    for e in ev:
        v0 = vol_daily[e["peak_i"]]
        if e["dur"] >= 1 and np.isfinite(v0) and v0 > 0:
            rows.append({"peak_i": e["peak_i"], "trough_i": e["trough_i"], "conf_i": e["conf_i"], "size": e["size"], "dur": e["dur"], "vol0": v0, "dur_cross": e["dur_cross"]})
    return rows


def fit_law(rows, before_i, max_size=LAW_MAX_SIZE, min_n=10):
    """OLS log(dur) = a + s log(size) + c log(vol0) on events of size < max_size confirmed before bar before_i."""
    sel = [r for r in rows if r["size"] < max_size and (before_i is None or r["conf_i"] < before_i)]
    if len(sel) < min_n:
        return None
    A = np.array([[1.0, np.log(r["size"]), np.log(r["vol0"])] for r in sel])
    y = np.array([np.log(r["dur"]) for r in sel])
    beta = np.linalg.lstsq(A, y, rcond=None)[0]
    res = y - A @ beta
    s = float(np.sqrt(np.sum(res ** 2) / max(len(y) - 3, 1)))
    b0 = np.array([y.mean(), 0.0, 0.0])
    s0 = float(np.std(y, ddof=1))
    return {"beta": beta.tolist(), "sd": s, "n": len(sel), "blind": [b0.tolist(), s0]}


def score_law(mu, s, x, alpha=0.2):
    z = 1.2816
    lo, hi = mu - z * s, mu + z * s
    inside = lo <= x <= hi
    iscore = (hi - lo) + (2 / alpha) * (max(lo - x, 0) + max(x - hi, 0))
    logscore = -0.5 * np.log(2 * np.pi * s * s) - 0.5 * ((x - mu) / s) ** 2
    return bool(inside), float(iscore), float(logscore)


def sojourn_block(b_daily, ks, n_boot, rng):
    out = {}
    for k in ks:
        _, _, ev, soj = crossing_states(b_daily, k, REV)
        row = {"nEvents": len(ev)}
        for st, lens in soj.items():
            arr = np.maximum(np.array(lens, float), 1.0)
            if len(arr) < 5:
                row[st] = {"n": len(arr)}
                continue
            th = weib_fit(arr, np.ones(len(arr)), np.zeros((len(arr), 0)), lam=0.0)
            boots = []
            for _ in range(n_boot):
                a2 = arr[rng.integers(0, len(arr), len(arr))]
                boots.append(weib_fit(a2, np.ones(len(a2)), np.zeros((len(a2), 0)), lam=0.0, init=th)[:2])
            boots = np.array(boots)
            row[st] = {"n": len(arr), "shape": round(float(np.exp(th[0])), 3), "scaleDays": round(float(np.exp(th[1])), 1),
                       "shape05": round(float(np.exp(np.quantile(boots[:, 0], 0.05))), 3), "shape95": round(float(np.exp(np.quantile(boots[:, 0], 0.95))), 3),
                       "medianDays": round(float(np.median(arr)), 1)}
        pt = np.maximum(np.array([e["dur"] for e in ev], float), 1.0)
        if len(pt) >= 5:
            th = weib_fit(pt, np.ones(len(pt)), np.zeros((len(pt), 0)), lam=0.0)
            row["PEAK_TO_TROUGH"] = {"n": len(pt), "shape": round(float(np.exp(th[0])), 3), "scaleDays": round(float(np.exp(th[1])), 1), "medianDays": round(float(np.median(pt)), 1)}
        out[str(k)] = row
    ks_ok = [k for k in ks if "scaleDays" in out[str(k)].get("FALL", {})]
    if len(ks_ok) >= 3:
        lk = np.log(ks_ok)
        ls = np.log([out[str(k)]["FALL"]["scaleDays"] for k in ks_ok])
        out["logLogSlope_FALL"] = round(float(np.polyfit(lk, ls, 1)[0]), 3)
        lp = np.log([out[str(k)]["PEAK_TO_TROUGH"]["scaleDays"] for k in ks_ok if "PEAK_TO_TROUGH" in out[str(k)]])
        if len(lp) == len(ks_ok):
            out["logLogSlope_PEAK_TO_TROUGH"] = round(float(np.polyfit(lk, lp, 1)[0]), 3)
        sh = [out[str(k)]["FALL"]["shape"] for k in ks_ok]
        out["shapeRange_FALL"] = [round(min(sh), 3), round(max(sh), 3)]
    return out


def remaining_rows(b_daily, rows, before_i, fracs=(0.25, 0.5, 0.75), max_size=None):
    """Training rows (log elapsed, log depth, remaining) at fractions of each completed event's duration, for events
    confirmed before bar before_i (all sizes unless max_size is given)."""
    out = []
    for r in rows:
        if (max_size is not None and r["size"] >= max_size) or (before_i is not None and r["conf_i"] >= before_i) or r["dur"] < 4:
            continue
        for f in fracs:
            i = r["peak_i"] + max(1, int(round(f * r["dur"])))
            if i >= r["trough_i"]:
                continue
            depth = max(b_daily[r["peak_i"]] - b_daily[i], 0.05)
            out.append([np.log(i - r["peak_i"]), np.log(depth), float(r["trough_i"] - i)])
    return np.array(out)


def fbm_path(n, H, rng):
    """Davies-Harte fractional Gaussian noise (unit variance), cumulated; None if the embedding fails."""
    m = 1
    while m < 2 * n:
        m *= 2
    k = np.arange(0, m // 2 + 1, dtype=float)
    g = 0.5 * (np.abs(k + 1) ** (2 * H) - 2 * np.abs(k) ** (2 * H) + np.abs(k - 1) ** (2 * H))
    row = np.concatenate([g, g[-2:0:-1]])
    lam = np.real(np.fft.fft(row))
    if lam.min() < 0:
        return None
    V = np.zeros(m, complex)
    V[0] = rng.standard_normal()
    V[m // 2] = rng.standard_normal()
    a = rng.standard_normal(m // 2 - 1) + 1j * rng.standard_normal(m // 2 - 1)
    V[1:m // 2] = a / np.sqrt(2)
    V[m // 2 + 1:] = np.conj(a[::-1]) / np.sqrt(2)
    x = np.real(np.fft.fft(np.sqrt(lam) * V)) / np.sqrt(m)
    return np.cumsum(x[:n])


def thin_aligned(series, every_days=14, anchor="2019-04-07", digits=4):
    """Thin a dated series to the date grid anchor + n * every_days (the grid the honest and multiscale modules use,
    so the forecast module's date join finds the same Sundays)."""
    s = series.dropna()
    a = pd.Timestamp(anchor)
    keep = [((t - a).days % every_days) == 0 for t in s.index]
    return [{"t": str(t.date()), "v": round(float(v), digits)} for t, v in s[keep].items()]


def weib_q(p, lam_, a_):
    return lam_ * (-np.log(1 - p)) ** (1 / a_)


def hurst_var(x, lags=(1, 2, 4, 8, 16, 32, 64)):
    v = [np.var(x[l:] - x[:-l]) for l in lags]
    return float(np.polyfit(np.log(lags), np.log(v), 1)[0] / 2)


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
    if a.fast:
        a.nulls = min(a.nulls, 20)
    n_sur = 20 if a.fast else max(20, a.nulls // 2)
    n_boot = 100 if a.fast else 200
    n_soj = 100 if a.fast else 500
    rng = np.random.default_rng(8)
    now_utc = dt.datetime.now(dt.timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        now_et = now_utc.astimezone(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M %Z")
    except Exception:
        now_et = "n/a"
    lines = []

    def say(s):
        lines.append(s)
        print(s)

    say(f"study8_hazard run {now_et} / {now_utc.strftime('%Y-%m-%d %H:%M UTC')} fast={a.fast} nulls={a.nulls} surrogates={n_sur}")
    D = C.load_daily(a.data)
    decoys_daily = [pd.Series(np.cumsum(rng.standard_normal(len(D.index))), index=D.index) for _ in range(N_DECOYS)]
    res = {"module": "study8_hazard", "runUtc": now_utc.strftime("%Y-%m-%d %H:%M UTC"), "runEt": now_et, "fast": a.fast, "oos": {}, "null": {}, "today": {},
           "series": {}, "duration": {}, "transfer": {}, "calibration": {}, "checks": {}, "notes": [], "definitions": {
               "k_W": K_W, "k_D": K_D, "rev": REV, "horizonWeeks": HORIZON_W, "COV": COV, "CLOCK": CLOCK, "ridgeBeta": RIDGE_BETA, "models": MODELS}}

    # ------------------------------------------------------------------ panels
    scales = {}
    for freq, ks in (("W", K_W), ("D", (K_D,) + (() if a.fast else K_D_CHECKS)), ("3D", () if a.fast else (K_3D,))):
        if not ks:
            continue
        P = C.panel(D, freq)
        X, _ = C.features(P, freq)
        cut = P.index >= pd.Timestamp(TRAIN_START)
        for k in ks:
            F, state, conf = hazard_features(P, X, freq, k, decoys_daily)
            Yk = targets_for_k(P, freq, k)
            fresh = C.fresh_mask(P, freq).values
            scales[(freq, k)] = {"P": P[cut], "X": X[cut], "F": F[cut], "Y": Yk[cut], "fresh": fresh[cut], "idx": P.index[cut], "freq": freq, "k": k,
                                 "F_full": F, "full_idx": P.index, "state_full": state}
    W5 = scales[("W", K_W[0])]
    idxW = W5["idx"]
    provisional = [str(d.date()) for d in idxW if d > D.index[-1]]
    nposW = {f"k{int(k)}": {"posWeeks": int(scales[('W', k)]['Y']['fall26'].loc['2019':].sum()), "episodes": len(C.episodes(scales[('W', k)]['Y']['fall26'].loc['2019':].values))} for k in K_W}
    evW5 = crossing_states(W5["P"]["BTC.D"].values, K_W[0])[2]
    say(f"weekly rows {len(idxW)} from {idxW[0].date()} (provisional {provisional}); fall26 2019+: k5 {nposW['k5']['posWeeks']} weeks / {nposW['k5']['episodes']} episodes, "
        f"k10 {nposW['k10']['posWeeks']} / {nposW['k10']['episodes']} (one episode Oct 2020 - May 2021, none since 2023); weekly k5 crossings since 2016: {len(evW5)}")

    # ------------------------------------------------------------------ weekly models
    oos, walks = {}, {}
    for k in K_W:
        g = scales[("W", k)]
        names = list(MODELS) if k == K_W[0] else ["clock", "five", "full", "full_noM2"]
        for name in names:
            w = _run_scale(g["F"], MODELS[name], g["Y"], g["idx"], "W")
            w["insample"] = None
            if name == "full":
                w = surv_walk(g["F"][MODELS[name]].values.astype(float), g["Y"]["tte"].values, g["Y"]["cens"].values, g["idx"], "W", keep_insample=True)
            walks[("W", k, name)] = w
            ev, p13, p26 = evaluate(w["S"], g["idx"], g["Y"], "W", g["fresh"], g["Y"]["tte"].values, g["Y"]["cens"].values, rng, n_boot)
            ev["refits"] = len(w["refits"])
            ev["lastRefit"] = w["refits"][-1] if w["refits"] else None
            oos[f"W:k{int(k)}:{name}"] = ev
            if name == "full":
                res["series"][f"p_fall{int(k)}_26w"] = thin_aligned(p26)
                res["series"][f"p_fall{int(k)}_13w"] = thin_aligned(p13)
            if name == "cov_renewal" and k == K_W[0]:
                res["series"]["p_fall5_26w_cov_renewal"] = thin_aligned(p26)
        if k == K_W[0]:
            res["series"]["state_k5"] = thin_aligned(g["F"]["state"].astype(float), digits=0)
            # check rows: the same models with the ridge sized to distinct crossing bars instead of overlapping origins
            for name in ("full", "cov_renewal"):
                w = _run_scale(g["F"], MODELS[name], g["Y"], g["idx"], "W", lam_eff=True)
                walks[("W", k, name + "_ridgeEff")] = w
                ev, _, _ = evaluate(w["S"], g["idx"], g["Y"], "W", g["fresh"], g["Y"]["tte"].values, g["Y"]["cens"].values, rng, n_boot)
                ev["ridgeLastRefit"] = w["refits"][-1]["ridge"] if w["refits"] else None
                oos[f"W:k{int(k)}:{name}_ridgeEff"] = ev
        # comparators through the harness: the five-signal logistic, M2 alone
        for cname, cols in (("fixed5", FIVE), ("m2only", ["m2_yoy"])):
            Yh = C.targets(g["P"], "W")
            tg26, tg13 = f"fall{int(k)}_26w", f"fall{int(k)}_13w"
            pr26, _ = B.run_fixed(g["X"], Yh, tg26, "W", True, cols)
            pr13, _ = B.run_fixed(g["X"], Yh, tg13, "W", True, cols)
            e26 = C.metrics(pr26, g["Y"]["fall26"], True, is_prob=True)
            e13 = C.metrics(pr13, g["Y"]["fall13"], True, is_prob=True)
            hb = C.bars(HORIZON_W, "W")
            obs, evv = oos_spells(g["Y"]["tte"].values, g["Y"]["cens"].values, len(g["idx"]), hb)
            post = era_of(g["idx"]) >= 0
            m = post & np.isfinite(pr26.values) & (obs >= 1)
            oos[f"W:k{int(k)}:{cname}_logistic"] = {"auc26": e26, "auc13": e13, "fresh26": C.metrics(pr26[g["fresh"]], g["Y"]["fall26"][g["fresh"]], True, is_prob=True),
                                                   "onset26": C.metrics(pr26, g["Y"]["onset26"], True, is_prob=True),
                                                   "today": (round(float(pr26.iloc[-1]), 4) if np.isfinite(pr26.iloc[-1]) else None)}
            oos[f"W:k{int(k)}:{cname}_logistic"].update(c_block(pr26.values, obs, evv, m, rng, n_boot, 1.0))
            walks[("W", k, cname)] = {"p26": pr26, "p13": pr13}
    # Cox and discrete-time hazard (weekly k=5 full)
    g = W5
    Fv = g["F"][MODELS["full"]].values.astype(float)
    risk = cox_walk(Fv, g["Y"]["tte"].values, g["Y"]["cens"].values, g["idx"], "W")
    hb = C.bars(HORIZON_W, "W")
    obs, evv = oos_spells(g["Y"]["tte"].values, g["Y"]["cens"].values, len(g["idx"]), hb)
    post = era_of(g["idx"]) >= 0
    m = post & np.isfinite(risk) & (obs >= 1)
    oos["W:k5:cox_full"] = {"C": round(cindex(risk[m], obs[m], evv[m]), 3), "auc26": C.metrics(pd.Series(risk, index=g["idx"]), g["Y"]["fall26"], True)}
    # positive episodes per era (the independent information behind every era AUC)
    y26w = g["Y"]["fall26"]
    epi_by_era = {name: len(C.episodes(y26w[(g["idx"] >= pd.Timestamp(fr)) & (g["idx"] < pd.Timestamp(to))].values)) for name, fr, to in C.ERAS}
    res["checks"]["positiveEpisodesByEra"] = epi_by_era
    if not a.fast:
        Sd = dt_hazard_walk(Fv, g["Y"]["tte"].values, g["Y"]["cens"].values, g["idx"], "W")
        evd, _, _ = evaluate(Sd, g["idx"], g["Y"], "W", g["fresh"], g["Y"]["tte"].values, g["Y"]["cens"].values, rng, 0)
        oos["W:k5:dtlogistic_full"] = evd
    res["oos"] = oos

    def fmt(x, d=3):
        return "na" if x is None else (f"{x:.{d}f}" if isinstance(x, float) else str(x))

    def row(key):
        e = oos[key]
        a26, a13 = e["auc26"].get("pooled", {}), e["auc13"].get("pooled", {})
        band = e.get("C_band", {})
        return (f"{key:<22} C {fmt(e.get('C'))} [{fmt(band.get('q05'))},{fmt(band.get('q95'))}] AUC13 {fmt(a13.get('auc'))} AUC26 {fmt(a26.get('auc'))} "
                f"brier26 {fmt(a26.get('brier'), 4)}/{fmt(a26.get('brierBase'), 4)} fresh26 {fmt(e['fresh26'].get('pooled', {}).get('auc'))} "
                f"onset26 {fmt(e['onset26'].get('pooled', {}).get('auc'))} eraDemeaned {fmt(e.get('auc26_eraDemeaned'))}")
    say("-- weekly k=5 nested (C = Harrell's C on tte5 with -S(26) as risk [26w block band]; AUC/Brier vs fall5_13w/fall5_26w; headline = full; rows marked * are POST-HOC decomposition, not pre-registered)")
    for name in HEADLINE_ROWS + ["fixed5_logistic", "m2only_logistic"]:
        say(("*" if name in POST_HOC_ROWS else " ") + row(f"W:k5:{name}"))
    ERAS3 = ["2019-2020", "2021-2022", "2023-2026"]

    def eras_of(key):
        return "/".join(fmt(oos[key]["auc26"].get(e, {}).get("auc")) for e in ERAS3)

    def briers_of(key):
        return "/".join(fmt(oos[key]["auc26"].get(e, {}).get("brier"), 3) for e in ERAS3)
    say(f"W:k5 AUC26 by era (2019-20/2021-22/2023-26; bases " + "/".join(fmt(oos['W:k5:full']['auc26'].get(e, {}).get('base')) for e in ERAS3)
        + "; positive episodes " + "/".join(str(epi_by_era[e]) for e in ERAS3) + ", so 2023-26 is a two-episode ranking): "
        + ", ".join(f"{n} {eras_of('W:k5:' + n)}" for n in ["clock", "five", "cov", "cov_renewal", "five_clock", "m2only_hazard", "fast", "full", "full_noM2", "fixed5_logistic", "m2only_logistic"]))
    say("W:k5 Brier by era (base " + "/".join(fmt(oos['W:k5:full']['auc26'].get(e, {}).get('brierBase'), 3) for e in ERAS3) + "; a row above base in 2021-22 loses in the era holding the only big event): "
        + ", ".join(f"{n} {briers_of('W:k5:' + n)}" for n in ["clock", "five", "cov", "cov_renewal", "m2only_hazard", "fast", "full", "full_noM2", "fixed5_logistic", "m2only_logistic"]))
    say("*W:k5 single-covariate Weibull AUC26 pooled (eras): " + ", ".join(f"{c} {fmt(oos['W:k5:one_' + c]['auc26'].get('pooled', {}).get('auc'))} ({eras_of('W:k5:one_' + c)})" for c in COV + ["clock_renewal"])
        + "; ridge sized to crossing bars (lam x origins/crossings): " + ", ".join(f"{n} C {fmt(oos['W:k5:' + n + '_ridgeEff'].get('C'))} AUC26 {fmt(oos['W:k5:' + n + '_ridgeEff']['auc26'].get('pooled', {}).get('auc'))} (ridge {oos['W:k5:' + n + '_ridgeEff'].get('ridgeLastRefit')})" for n in ("full", "cov_renewal")))
    say("-- weekly k=10 (fall10_26w is ONE episode, Oct 2020 - May 2021: a ranking of one event) C / AUC26 / brier26 / fresh26: "
        + "; ".join(f"{n} {fmt(oos['W:k10:' + n].get('C'))}/{fmt(oos['W:k10:' + n]['auc26'].get('pooled', {}).get('auc'))}/{fmt(oos['W:k10:' + n]['auc26'].get('pooled', {}).get('brier'), 3)}/{fmt(oos['W:k10:' + n]['fresh26'].get('pooled', {}).get('auc'))}"
                    for n in ["clock", "five", "full", "full_noM2", "fixed5_logistic"]) + f" (base brier {fmt(oos['W:k10:full']['auc26'].get('pooled', {}).get('brierBase'), 3)})"
        + f" | other estimators of full: Cox C {oos['W:k5:cox_full']['C']}" + ("" if a.fast else f"; discrete-time logistic hazard (6 bins) C {oos['W:k5:dtlogistic_full']['C']} AUC26 {oos['W:k5:dtlogistic_full']['auc26'].get('pooled', {}).get('auc')} AUC13 {oos['W:k5:dtlogistic_full']['auc13'].get('pooled', {}).get('auc')}"))

    # ------------------------------------------------------------------ incremental value over the five-signal logistic (weekly k=5)
    g = W5
    wfull = walks[("W", K_W[0], "full")]
    p26h = pd.Series(1 - wfull["S"][:, 25], index=g["idx"])
    p26f = walks[("W", K_W[0], "fixed5")]["p26"]
    mean_logit = pd.Series(sig(0.5 * (lg(p26h.values) + lg(p26f.values))), index=g["idx"])
    # stacked logistic: five signals + logit(hazard P26); training rows use the in-sample hazard P26 of the same refit
    X5 = g["X"][FIVE].values.astype(float)
    y26 = g["Y"]["fall26"].values
    stack = pd.Series(np.nan, index=g["idx"])
    step = C.bars(REFIT_W, "W")
    N = len(g["idx"])
    t = int(np.searchsorted(g["idx"], pd.Timestamp(FIRST)))
    ri = 0
    while t < N and ri < len(wfull["insample"]):
        tr, pin = wfull["insample"][ri]
        lab = tr < t - 26
        tr2 = tr[lab]
        pin2 = pin[lab]
        ok = np.isfinite(y26[tr2]) & np.isfinite(X5[tr2]).all(1)
        if ok.sum() >= 60 and y26[tr2][ok].sum() >= 3:
            A = np.c_[X5[tr2][ok], lg(pin2[ok])]
            mu, sd = C.zfit(A)
            w = C.logistic_fit(C.zapply(A, mu, sd), y26[tr2][ok], lam=1.0)
            te = np.arange(t, min(t + step, N))
            te = te[np.isfinite(X5[te]).all(1) & np.isfinite(p26h.values[te])]
            if len(te):
                stack.iloc[te] = C.logistic_predict(C.zapply(np.c_[X5[te], lg(p26h.values[te])], mu, sd), w)
        t += step
        ri += 1
    inc = {}
    both = np.isfinite(p26f.values) & np.isfinite(p26h.values) & np.isfinite(y26) & (era_of(g["idx"]) >= 0)
    for nm, s in (("hazard_full", p26h), ("fixed5", p26f), ("logitMean", mean_logit), ("stacked", stack)):
        inc[nm] = {"auc26": C.metrics(s, g["Y"]["fall26"], True, is_prob=True), "fresh26": C.metrics(s[g["fresh"]], g["Y"]["fall26"][g["fresh"]], True).get("pooled", {}).get("auc")}
    pos = np.where(both & np.isfinite(stack.values) & np.isfinite(mean_logit.values))[0]
    for nm, s in (("hazard_full", p26h), ("logitMean", mean_logit), ("stacked", stack)):
        d_real = C.auc(s.values[pos], y26[pos]) - C.auc(p26f.values[pos], y26[pos])
        band = boot_band(lambda ii, s=s: (C.auc(s.values[pos][ii], y26[pos][ii]) or 0) - (C.auc(p26f.values[pos][ii], y26[pos][ii]) or 0), len(pos), n_boot, 26, rng)
        inc[nm]["aucGainOverFixed5"] = round(float(d_real), 3)
        inc[nm]["gainBand"] = band
    res["oos"]["incremental_W_k5"] = inc
    say("-- incremental over fixed5 (pooled AUC26 gain, 26-week block-bootstrap band; |gain| < 0.05 or a band containing 0 is a tie)")
    say("   " + " | ".join(f"{nm}: AUC26 {fmt(inc[nm]['auc26'].get('pooled', {}).get('auc'))} brier {fmt(inc[nm]['auc26'].get('pooled', {}).get('brier'), 4)} fresh {fmt(inc[nm]['fresh26'])}"
                          + (f" gain {inc[nm]['aucGainOverFixed5']:+.3f} [{inc[nm]['gainBand'].get('q05')},{inc[nm]['gainBand'].get('q95')}]" if 'aucGainOverFixed5' in inc[nm] else "")
                          for nm in ("fixed5", "hazard_full", "logitMean", "stacked"))
        + " || by era: " + " | ".join(f"{nm} " + "/".join(fmt(inc[nm]['auc26'].get(e, {}).get('auc')) for e in ERAS3) for nm in ("fixed5", "hazard_full", "stacked")))
    # every nested hazard row against fixed5 AND M2-alone (logistic), block and episode bands: a component model that does
    # not beat m2only is the liquidity cycle re-labelled
    p26m2 = walks[("W", K_W[0], "m2only")]["p26"]
    inc_rows = {}
    for nm in ("five", "cov_renewal", "cov", "fast", "m2only_hazard", "one_m2_yoy", "full"):
        s_ = pd.Series(1 - walks[("W", K_W[0], nm)]["S"][:, 25], index=g["idx"])
        pos_ = np.where(both & np.isfinite(s_.values) & np.isfinite(p26m2.values))[0]
        inc_rows[nm] = {"vsFixed5": paired_gain(s_.values, p26f.values, y26, pos_, n_boot, rng), "vsM2only": paired_gain(s_.values, p26m2.values, y26, pos_, n_boot, rng)}
        # within-era, era-demeaned comparison with M2 alone (the within-cycle question)
        e_ = era_of(g["idx"])
        dm_s, dm_m = lg(s_.values).copy(), lg(p26m2.values).copy()
        for i in range(3):
            mm = (e_ == i) & np.isfinite(dm_s) & np.isfinite(dm_m)
            if mm.sum():
                dm_s[mm] -= dm_s[mm].mean()
                dm_m[mm] -= dm_m[mm].mean()
        inc_rows[nm]["eraDemeanedAUC26"] = {"row": (None if C.auc(dm_s[pos_], y26[pos_]) is None else round(C.auc(dm_s[pos_], y26[pos_]), 3)), "m2only": (None if C.auc(dm_m[pos_], y26[pos_]) is None else round(C.auc(dm_m[pos_], y26[pos_]), 3))}
    res["oos"]["incremental_nested_W_k5"] = inc_rows

    def gfmt(gd):
        return f"{gd['gain']:+.3f} [{gd['blockBand'].get('q05')},{gd['blockBand'].get('q95')}] ep[{gd['episodeBand'].get('q05')},{gd['episodeBand'].get('q95')}]"
    say("*  nested rows: AUC26 gain vs fixed5 / vs m2only_logistic (26w block band, episode band; era-demeaned AUC26 row vs m2only): "
        + " | ".join(f"{nm} {gfmt(v['vsFixed5'])} / {gfmt(v['vsM2only'])} (dm {fmt(v['eraDemeanedAUC26']['row'])} vs {fmt(v['eraDemeanedAUC26']['m2only'])})" for nm, v in inc_rows.items()))
    say("   C within-run-up / between-run-up pairs (n pairs), C on one origin per run-up (n crossing bars), [run-up bootstrap band of the all-origin C]: "
        + " | ".join(f"{nm} {fmt(oos['W:k5:' + nm]['C_split']['within'])}/{fmt(oos['W:k5:' + nm]['C_split']['between'])} ({oos['W:k5:' + nm]['C_split']['nWithin']}/{oos['W:k5:' + nm]['C_split']['nBetween']}), one-per {fmt(oos['W:k5:' + nm].get('C_onePerRunup'))} ({oos['W:k5:' + nm].get('nRunups')}) [{fmt(oos['W:k5:' + nm].get('C_runupBand', {}).get('q05'))},{fmt(oos['W:k5:' + nm].get('C_runupBand', {}).get('q95'))}]"
                     for nm in ("full", "cov_renewal", "five", "m2only_hazard", "fixed5_logistic")) + "; with every bar an origin C is a between-run-up (era) ranking")

    # ------------------------------------------------------------------ calibration (weekly k=5, OOS origins only) for every model whose number is quoted
    hb = C.bars(HORIZON_W, "W")
    obs, evv = oos_spells(g["Y"]["tte"].values, g["Y"]["cens"].values, len(g["idx"]), hb)
    last_complete = int(np.where(g["idx"] <= D.index[-1])[0][-1])
    cal_rows = {"full": (p26h, wfull["S"]), "cov_renewal": (pd.Series(1 - walks[("W", K_W[0], "cov_renewal")]["S"][:, 25], index=g["idx"]), walks[("W", K_W[0], "cov_renewal")]["S"]),
                "five": (pd.Series(1 - walks[("W", K_W[0], "five")]["S"][:, 25], index=g["idx"]), walks[("W", K_W[0], "five")]["S"]),
                "fixed5": (p26f, None), "m2only": (p26m2, None)}
    for cname, (pc, Sc) in cal_rows.items():
        cal = {}
        m = both & np.isfinite(pc.values)
        lp = lg(pc.values[m])
        yy = y26[m]
        w = C.logistic_fit(lp[:, None], yy, lam=1e-3)
        cal["slope"], cal["intercept"] = round(float(w[1]), 3), round(float(w[0]), 3)
        cal["slopeBand"] = boot_band(lambda ii: C.logistic_fit(lp[ii][:, None], yy[ii], lam=1e-3)[1], len(lp), n_boot, 26, rng)
        cal["interceptBand"] = boot_band(lambda ii: C.logistic_fit(lp[ii][:, None], yy[ii], lam=1e-3)[0], len(lp), n_boot, 26, rng)
        pt = pc.iloc[last_complete]
        cal["todayRaw"] = (round(float(pt), 4) if np.isfinite(pt) else None)
        cal["todayRecalibrated"] = (round(float(sig(w[0] + w[1] * lg(pt))), 4) if np.isfinite(pt) else None)
        if Sc is not None:
            # Kaplan-Meier vs mean predicted S at 13, 26, 52 weeks in risk terciles
            mk = (era_of(g["idx"]) >= 0) & np.isfinite(pc.values) & (obs >= 1)
            pos = np.where(mk)[0]
            terc = np.quantile(pc.values[pos], [1 / 3, 2 / 3])
            cal["terciles"] = {}
            for ti, sel in enumerate([pc.values[pos] <= terc[0], (pc.values[pos] > terc[0]) & (pc.values[pos] <= terc[1]), pc.values[pos] > terc[1]]):
                pp = pos[sel]
                km = km_curve(obs[pp].astype(float), evv[pp], [13, 26, 52])
                pred = np.nanmean(Sc[pp][:, [12, 25, 51]], 0)
                cal["terciles"][f"T{ti + 1}"] = {"n": int(len(pp)), "KM": [round(float(v), 3) for v in km], "predS": [round(float(v), 3) for v in pred]}
            kms = [v["KM"][1] for v in cal["terciles"].values()]
            cal["kmMonotoneAcrossTerciles"] = bool(kms[0] >= kms[1] >= kms[2])
            pit_u, pit_v, pit_dates = pit_values(Sc, g["idx"], g["Y"]["tte"].values, g["Y"]["cens"].values, "W")
            cal["pitWeekly"] = {"u_raw": [round(float(u), 3) for u in pit_u], "v_censoringAdjusted": [round(float(v), 3) for v in pit_v], "crossings": pit_dates, "vMean": round(float(np.mean(pit_v)), 3),
                                "note": "reported, not tested; u = S_t(T_t) is biased toward 1 for events known to precede the censoring time, v = (1-S(T))/(1-S(C)) is the uniform one"}
        res["calibration"][f"W_k5_{cname}"] = cal
    cal = res["calibration"]["W_k5_full"]
    say(f"-- calibration W:k5:full (OOS origins): slope {cal['slope']} [{cal['slopeBand'].get('q05')},{cal['slopeBand'].get('q95')}] intercept {cal['intercept']} [{cal['interceptBand'].get('q05')},{cal['interceptBand'].get('q95')}]; "
        + "KM vs predicted S(13/26/52) by risk tercile: " + "; ".join(f"T{i + 1} KM {v['KM']} pred {v['predS']}" for i, v in enumerate(cal['terciles'].values()))
        + f"; weekly PIT over {len(cal['pitWeekly']['v_censoringAdjusted'])} OOS crossings: raw u mean {np.mean(cal['pitWeekly']['u_raw']):.2f}, censoring-adjusted v mean {cal['pitWeekly']['vMean']:.2f} (uniform expected; not tested at weekly)")
    say("   calibration slope/intercept [slope band] and today's P26 raw -> recalibrated on the model's own OOS line; hazard rows add KM S(26) by tercile (monotone?) and PIT v mean: "
        + " | ".join(f"{cn} {v['slope']}/{v['intercept']} [{v['slopeBand'].get('q05')},{v['slopeBand'].get('q95')}] {v['todayRaw']} -> {v['todayRecalibrated']}"
                     + (f" KM {[t['KM'][1] for t in v['terciles'].values()]} {'mono' if v['kmMonotoneAcrossTerciles'] else 'NOT mono'} PIT {v['pitWeekly']['vMean']}" if 'terciles' in v else "")
                     for cn, v in ((cn, res["calibration"]["W_k5_" + cn]) for cn in cal_rows)))

    # ------------------------------------------------------------------ daily twin, 3-day rung, transfer
    daily_full = None
    for (freq, k), g2 in scales.items():
        if freq == "W":
            continue
        names = ["clock", "five", "cov_renewal", "fast", "full"] if (freq == "D" and k == K_D) else ["clock", "full"]
        for name in names:
            w = _run_scale(g2["F"], MODELS[name], g2["Y"], g2["idx"], freq)
            ev, p13, p26 = evaluate(w["S"], g2["idx"], g2["Y"], freq, g2["fresh"], g2["Y"]["tte"].values, g2["Y"]["cens"].values, rng, (n_boot if name == "full" else 0), thin=(7 if freq == "D" else 3))
            ev["refits"] = len(w["refits"])
            oos[f"{freq}:k{k:g}:{name}"] = ev
            walks[(freq, k, name)] = w
            if freq == "D" and k == K_D and name == "full":
                daily_full = w
                res["series"]["p_fall2_26w_daily"] = thin_aligned(p26)
                pit_u_d, pit_d, _ = pit_values(w["S"], g2["idx"], g2["Y"]["tte"].values, g2["Y"]["cens"].values, "D")
                ks = ks_uniform(pit_d)
                # block-bootstrap critical value: KS of resampled (centred) PIT sequences, blocks of 3 events
                def ks_boot(ii, u=pit_d):
                    ub = u[ii]
                    us = np.sort(ub)
                    n = len(us)
                    ref = np.searchsorted(np.sort(u), us, side="right") / len(u)
                    return float(np.max(np.abs(ref - np.arange(1, n + 1) / n))) if n else None
                bb = boot_band(ks_boot, len(pit_d), n_boot, 3, rng)
                crit = bb.get("q95")
                res["calibration"]["D_k2_pit"] = {"n": int(len(pit_d)), "ks": round(ks, 3), "ksBootP95": crit, "rejected": (None if crit is None else bool(ks > crit)),
                                                  "hist10": np.histogram(pit_d, bins=10, range=(0, 1))[0].tolist(), "rawUMean": round(float(np.mean(pit_u_d)), 3),
                                                  "note": "v = (1-S(T))/(1-S(C)) censoring-adjusted PIT; KS vs uniform with a block-bootstrap (3 events) critical value"}
        if freq == "D" and k == K_D:
            def drow(name):
                key = f"{freq}:k{k:g}:{name}"
                e = oos[key]
                return (f"{key} C {fmt(e.get('C'))} [{fmt(e.get('C_band', {}).get('q05'))},{fmt(e.get('C_band', {}).get('q95'))}] AUC13 {fmt(e['auc13'].get('pooled', {}).get('auc'))} AUC26 {fmt(e['auc26'].get('pooled', {}).get('auc'))} "
                        f"brier26 {fmt(e['auc26'].get('pooled', {}).get('brier'), 4)}/{fmt(e['auc26'].get('pooled', {}).get('brierBase'), 4)} fresh26 {fmt(e['fresh26'].get('pooled', {}).get('auc'))} "
                        f"eras " + "/".join(fmt(e['auc26'].get(er, {}).get('auc')) for er in ERAS3) + f" origin-events {e['nEvents']} (distinct crossing bars {e.get('nRunups')})")
            say("-- daily k=2 (every 7th origin for C): " + drow("clock") + " | " + drow("five"))
            say("   " + drow("cov_renewal") + " | " + drow("fast") + " | " + drow("full"))
    checks_rows = [k for k in oos if (k.startswith("D:k1.5") or k.startswith("D:k3") or k.startswith("3D:")) and k.endswith(":full")]
    if checks_rows:
        say("   daily checks (full model; C [band] / AUC26 / eras / events): " + "; ".join(
            f"{key} {fmt(oos[key].get('C'))} [{fmt(oos[key].get('C_band', {}).get('q05'))},{fmt(oos[key].get('C_band', {}).get('q95'))}] / {fmt(oos[key]['auc26'].get('pooled', {}).get('auc'))} / "
            + "/".join(fmt(oos[key]['auc26'].get(er, {}).get('auc')) for er in ERAS3) + f" / {oos[key]['nEvents']}" for key in checks_rows))
    if "D_k2_pit" in res["calibration"]:
        pd_ = res["calibration"]["D_k2_pit"]
        say(f"   daily k=2 censoring-adjusted PIT over {pd_['n']} OOS crossings: KS {pd_['ks']} vs block-bootstrap p95 {pd_['ksBootP95']} -> {'REJECTED' if pd_['rejected'] else 'not rejected'}; decile counts {pd_['hist10']}")
    # transfer: daily-fitted standardised betas (k=2, same refit dates) applied unchanged to weekly k=5 z-scores; alpha and
    # lambda refit weekly with beta frozen (C and AUC depend on beta only; Brier needs the weekly time scale)
    res["transfer"] = {}
    hbW = C.bars(HORIZON_W, "W")
    obsW, evW = oos_spells(W5["Y"]["tte"].values, W5["Y"]["cens"].values, len(W5["idx"]), hbW)
    p26clock = 1 - walks[("W", K_W[0], "clock")]["S"][:, 25]
    for name in ("full", "cov_renewal", "fast"):
        wD = walks.get(("D", K_D, name))
        if wD is None or not wD["thetas"]:
            continue
        betas = {d: th[2:].copy() for d, th in wD["thetas"].items()}

        def fixed_beta(date, betas=betas):
            keys = [d for d in betas if d <= date]
            return betas[max(keys)] if keys else None
        wT = surv_walk(W5["F"][MODELS[name]].values.astype(float), W5["Y"]["tte"].values, W5["Y"]["cens"].values, W5["idx"], "W", fixed_beta=fixed_beta)
        walks[("W", K_W[0], "transfer_" + name)] = wT
        evT, _, _ = evaluate(wT["S"], W5["idx"], W5["Y"], "W", W5["fresh"], W5["Y"]["tte"].values, W5["Y"]["cens"].values, rng, n_boot)
        oos[f"W:k5:transfer_{name}"] = evT
        cC, cF, cT = oos["W:k5:clock"]["C"], oos[f"W:k5:{name}"]["C"], evT["C"]
        ratio = None if (cC is None or cF is None or cT is None or abs(cF - cC) < 1e-9) else round((cT - cC) / (cF - cC), 2)
        # paired 26-week block bootstrap of the ratio, of C_T - C_W and of the gains over the alpha/lambda-only baseline (C = 0.5)
        pW, pT = 1 - walks[("W", K_W[0], name)]["S"][:, 25], 1 - wT["S"][:, 25]
        mm = (era_of(W5["idx"]) >= 0) & np.isfinite(pW) & np.isfinite(pT) & np.isfinite(p26clock) & (obsW >= 1)
        posT = np.where(mm)[0]
        rW, rT, rC, tt, ee = pW[posT], pT[posT], p26clock[posT], obsW[posT], evW[posT]
        rat, dif, nul = [], [], []
        for _ in range(n_boot):
            ii = block_indices(len(posT), 26, rng)
            cw, ct, cc = cindex(rW[ii], tt[ii], ee[ii]), cindex(rT[ii], tt[ii], ee[ii]), cindex(rC[ii], tt[ii], ee[ii])
            if cw is None or ct is None or cc is None:
                continue
            dif.append(ct - cw)
            nul.append((ct - 0.5) / (cw - 0.5) if abs(cw - 0.5) >= 0.02 else np.nan)
            if abs(cw - cc) >= 0.02:
                rat.append((ct - cc) / (cw - cc))

        def q(v):
            v = np.array([x for x in v if np.isfinite(x)])
            return ({"n": int(len(v)), "q05": round(float(np.quantile(v, 0.05)), 3), "q50": round(float(np.quantile(v, 0.5)), 3), "q95": round(float(np.quantile(v, 0.95)), 3)} if len(v) else {"n": 0})
        thD = wD["last"]["theta"]
        res["transfer"][name] = {"postHoc": name != "full", "C_clock": cC, "C_weekly": cF, "C_transfer": cT, "gainRecovered": ratio, "gainRecoveredBand": q(rat),
                                 "ratioInterpretable": bool(cF is not None and cC is not None and cF - cC >= 0.02),
                                 "C_transfer_minus_weekly": (None if cT is None or cF is None else round(cT - cF, 3)), "C_transfer_minus_weekly_band": q(dif),
                                 "gainOverNullBaseline": (None if cT is None or cF is None or abs(cF - 0.5) < 0.02 else round((cT - 0.5) / (cF - 0.5), 2)), "gainOverNullBaselineBand": q(nul),
                                 "auc26_transfer": evT["auc26"].get("pooled", {}).get("auc"),
                                 "auc26_weekly": oos[f"W:k5:{name}"]["auc26"].get("pooled", {}).get("auc"), "eras26_transfer": {e: evT["auc26"].get(e, {}).get("auc") for e in ERAS3},
                                 "betaDailyLast": dict(zip(MODELS[name], [round(float(v), 3) for v in thD[2:]])),
                                 "betaWeeklyLast": dict(zip(MODELS[name], [round(float(v), 3) for v in walks[("W", K_W[0], name)]["last"]["theta"][2:]]))}
    if res["transfer"]:
        say("-- transfer daily(k=2)->weekly(k=5), betas frozen from the daily refit at the same date (ratio = (C_T - C_clock)/(C_W - C_clock), paired 26w block band; "
            "undefined when the weekly model does not beat the clock; also C_T - C_W [band] and (C_T - 0.5)/(C_W - 0.5) [band]; full is pre-registered, the others post-hoc):")
        say("   " + " | ".join(
            f"{n}: C {fmt(v['C_transfer'])} vs weekly {fmt(v['C_weekly'])} vs clock {fmt(v['C_clock'])} -> ratio {v['gainRecovered']} [{v['gainRecoveredBand'].get('q05')},{v['gainRecoveredBand'].get('q95')}]{'' if v['ratioInterpretable'] else ' (NOT interpretable)'}, "
            f"T-W {v['C_transfer_minus_weekly']} [{v['C_transfer_minus_weekly_band'].get('q05')},{v['C_transfer_minus_weekly_band'].get('q95')}], vs0.5 {v['gainOverNullBaseline']} [{v['gainOverNullBaselineBand'].get('q05')},{v['gainOverNullBaselineBand'].get('q95')}], "
            f"AUC26 {fmt(v['auc26_transfer'])} vs {fmt(v['auc26_weekly'])}, eras " + "/".join(fmt(v['eras26_transfer'][e]) for e in ERAS3) for n, v in res["transfer"].items()))
        say("   betas daily/weekly: cov_renewal " + ", ".join(f"{c} {res['transfer']['cov_renewal']['betaDailyLast'][c]:+.2f}/{res['transfer']['cov_renewal']['betaWeeklyLast'][c]:+.2f}" for c in MODELS["cov_renewal"])
            + " | fast (M2 and BTC drawdown removed: the once-per-cycle series that share the calendar across scales) " + ", ".join(f"{c} {res['transfer']['fast']['betaDailyLast'][c]:+.2f}/{res['transfer']['fast']['betaWeeklyLast'][c]:+.2f}" for c in MODELS["fast"]) if "fast" in res["transfer"] and "cov_renewal" in res["transfer"] else "")

    # ------------------------------------------------------------------ decoys as passengers
    wd = walks[("W", K_W[0], "full_decoys")]["last"]
    if wd is not None:
        b = wd["theta"][2:]
        nreal = len(COV + CLOCK)
        res["checks"]["decoyBetas"] = {"meanAbsReal": round(float(np.mean(np.abs(b[:nreal]))), 3), "meanAbsDecoy": round(float(np.mean(np.abs(b[nreal:]))), 3),
                                       "maxAbsDecoy": round(float(np.max(np.abs(b[nreal:]))), 3), "real": dict(zip(COV + CLOCK, [round(float(v), 3) for v in b[:nreal]]))}

    # ------------------------------------------------------------------ nulls (one rng: shifts and surrogates drawn here, walks in the pool)
    ctx = get_context("fork")
    for (freq, k), g2 in scales.items():
        _G[f"{freq}:{k:g}"] = {"F": g2["F"], "Y": g2["Y"], "idx": g2["idx"], "freq": freq, "fresh": g2["fresh"], "k": k, "F_full": g2["F_full"], "full_idx": g2["full_idx"]}
    _G["W"] = _G["W:5"]
    _G["daily_base"] = {"didx": D.index}
    lo = 26
    jobs = []
    for name in HEADLINE_ROWS:                      # every row that carries a number gets the full draw count (a weekly walk is well under a second)
        for _ in range(a.nulls):
            jobs.append(("W:5", name, int(rng.integers(lo, len(idxW) - lo))))
    for _ in range(max(5, a.nulls // 4)):
        jobs.append(("W:10", "full", int(rng.integers(lo, len(idxW) - lo))))
    nD = len(scales[("D", K_D)]["idx"])
    for _ in range(max(5, a.nulls // 4)):
        jobs.append((f"D:{K_D:g}", "full", int(rng.integers(26 * 7, nD - 26 * 7))))
    tr_jobs = []
    for name in ("full", "cov_renewal", "fast"):
        for _ in range(a.nulls if a.fast else max(20, a.nulls // 2)):
            tr_jobs.append((name, int(rng.integers(lo, len(idxW) - lo))))
    era_jobs = []
    for model in ("full", "five", "cov_renewal"):
        for ei, (name, fr, to) in enumerate(C.ERAS):
            npos = int(((idxW >= pd.Timestamp(fr)) & (idxW < pd.Timestamp(to))).sum())
            for _ in range(max(10, a.nulls // 2)):
                if npos > 2 * lo:
                    era_jobs.append(("W:5", model, ei, int(rng.integers(lo, npos - lo))))
    # surrogates of BTC.D (daily logit): IAAFT and fBm matched on H, real covariates
    xl = C.logit(D["BTC.D"].values)
    Hhat = float(np.clip(hurst_var(xl), 0.05, 0.95))
    sur_jobs = []
    for _ in range(n_sur):
        sur_jobs.append(("iaaft", C.iaaft(xl, rng, it=30)))
    sd_inc = float(np.std(np.diff(xl)))
    x_anchor = float(np.median(xl))     # anchored at the real series' median level: anchored at the first value (BTC.D 99.6%) 15 of 20 paths never left 93-100% and had no events
    for _ in range(n_sur):
        f = fbm_path(len(xl), Hhat, rng)
        if f is None:
            f = np.cumsum(rng.standard_normal(len(xl)))
        sur_jobs.append(("fbm", x_anchor + sd_inc * f))
    workers = max(1, min(a.workers, os.cpu_count() or 1))
    tn = time.time()
    with ctx.Pool(workers) as pool:
        null_out = pool.map(_shift_worker, jobs, chunksize=4)
        tr_out = pool.map(_transfer_worker, tr_jobs, chunksize=2)
        era_out = pool.map(_within_era_worker, era_jobs, chunksize=4)
        sur_out = pool.map(_surrogate_worker, sur_jobs, chunksize=2)
    null = {}
    for (scale, name, _), r in zip(jobs, null_out):
        key = f"{scale}:{name}"
        null.setdefault(key, {"auc26": [], "auc13": [], "C": [], "fresh26": [], "eras26": {e: [] for e in ERAS3}})
        for stat in ("auc26", "auc13", "C", "fresh26"):
            if r.get(stat) is not None:
                null[key][stat].append(r[stat])
        for e in ERAS3:
            if (r.get("eras26") or {}).get(e) is not None:
                null[key]["eras26"][e].append(r["eras26"][e])
    for (name, _), r in zip(tr_jobs, tr_out):
        key = f"W:5:transfer_{name}"
        null.setdefault(key, {"auc26": [], "auc13": [], "C": [], "fresh26": [], "eras26": {e: [] for e in ERAS3}})
        for stat in ("auc26", "auc13", "C", "fresh26"):
            if r.get(stat) is not None:
                null[key][stat].append(r[stat])
        for e in ERAS3:
            if (r.get("eras26") or {}).get(e) is not None:
                null[key]["eras26"][e].append(r["eras26"][e])
    nres = {}
    for key, d in null.items():
        scale, name = key.rsplit(":", 1)
        freq, k = scale.split(":")
        ok = f"{freq}:k{k}:{name}"
        e = oos[ok]
        nres[ok] = {"auc26": C.null_summary(e["auc26"].get("pooled", {}).get("auc"), d["auc26"]), "auc13": C.null_summary(e["auc13"].get("pooled", {}).get("auc"), d["auc13"]),
                    "C": C.null_summary(e.get("C"), d["C"]), "fresh26": C.null_summary(e["fresh26"].get("pooled", {}).get("auc"), d["fresh26"]),
                    # era-level p under the POOLED shift (the shifted series keeps its dwell times; the era value is the shifted model's AUC inside that era)
                    "eras26": {er: C.null_summary(e["auc26"].get(er, {}).get("auc"), d["eras26"][er]) for er in ERAS3}}
    we = {}
    for (scale, model, ei, _), v in zip(era_jobs, era_out):
        we.setdefault(model, {}).setdefault(C.ERAS[ei][0], []).append(v)
    for model, d in we.items():
        nres[f"W:k5:{model}:withinEra"] = {era: C.null_summary(oos[f"W:k5:{model}"]["auc26"].get(era, {}).get("auc"), [v for v in vals if v is not None]) for era, vals in d.items()}
    sur = {"iaaft": [r for r in sur_out if r["kind"] == "iaaft"], "fbm": [r for r in sur_out if r["kind"] == "fbm"]}
    nres["surrogates"] = {"H_hat": round(Hhat, 3), "fbmAnchor": "median of the real daily logit"}
    for kind, rows in sur.items():
        nres["surrogates"][kind] = {"auc26": C.null_summary(oos["W:k5:full"]["auc26"].get("pooled", {}).get("auc"), [r["auc26"] for r in rows if r["auc26"] is not None]),
                                   "C": C.null_summary(oos["W:k5:full"]["C"], [r["C"] for r in rows if r["C"] is not None]),
                                   "lawSlope": [r["lawSlope"] for r in rows if r["lawSlope"] is not None], "nDrawn": len(rows), "nUsable": int(sum(r["auc26"] is not None for r in rows))}
    res["null"] = nres
    res["checks"]["nullRuntimeSec"] = round(time.time() - tn, 1)

    def nrow(name):
        n_ = nres[f"W:k5:{name}"]
        return (f"{name} C p{fmt(n_['C'].get('p'))}(n{n_['C'].get('n')},p95 {fmt(n_['C'].get('nullP95'))}) A26 p{fmt(n_['auc26'].get('p'))}(p95 {fmt(n_['auc26'].get('nullP95'))}) A13 p{fmt(n_['auc13'].get('p'))} fr p{fmt(n_['fresh26'].get('p'))} "
                f"era p " + "/".join(fmt(n_['eras26'][er].get('p')) for er in ERAS3) + " (era p95 " + "/".join(fmt(n_['eras26'][er].get('nullP95'))[:4] for er in ERAS3) + ")")
    say(f"-- shifted-target nulls through standardisation and the Weibull refit ({a.nulls} draws per row, p = share of nulls >= real; with n = {a.nulls} the p resolution is {1 / a.nulls:.2f}; era p = the era-level AUC under the pooled shift)")
    nrows = HEADLINE_ROWS + [f"transfer_{n}" for n in ("full", "cov_renewal", "fast") if f"W:k5:transfer_{n}" in nres]
    for i in range(0, len(nrows), 3):
        say("   " + " | ".join(nrow(n) for n in nrows[i:i + 3]))
    say(f"   W:k10:full C p {fmt(nres['W:k10:full']['C'].get('p'))} (n {nres['W:k10:full']['C'].get('n')}) AUC26 p {fmt(nres['W:k10:full']['auc26'].get('p'))} | D:k2:full C p {fmt(nres['D:k2:full']['C'].get('p'))} (n {nres['D:k2:full']['C'].get('n')}) AUC26 p {fmt(nres['D:k2:full']['auc26'].get('p'))} AUC13 p {fmt(nres['D:k2:full']['auc13'].get('p'))}"
        + " | within-era shifted null AUC26 (targets rolled inside one era; a one-event era makes this a one-event test): "
        + "; ".join(f"{model} " + ", ".join(f"{era[:4]} p {fmt(v.get('p'))} (n {v.get('n')}, p95 {fmt(v.get('nullP95'))})" for era, v in nres[f"W:k5:{model}:withinEra"].items()) for model in we))
    say(f"   surrogates (BTC.D replaced, real covariates; H_hat {Hhat:.2f}; fBm anchored at the real logit median): IAAFT AUC26 p95 {fmt(nres['surrogates']['iaaft']['auc26'].get('nullP95'))} p {fmt(nres['surrogates']['iaaft']['auc26'].get('p'))} (usable {nres['surrogates']['iaaft']['nUsable']}/{nres['surrogates']['iaaft']['nDrawn']}), C p {fmt(nres['surrogates']['iaaft']['C'].get('p'))}; "
        f"fBm AUC26 p95 {fmt(nres['surrogates']['fbm']['auc26'].get('nullP95'))} p {fmt(nres['surrogates']['fbm']['auc26'].get('p'))} (usable {nres['surrogates']['fbm']['nUsable']}/{nres['surrogates']['fbm']['nDrawn']})")

    # ------------------------------------------------------------------ duration block (daily)
    Pd = C.panel(D, "D")
    Xd, _ = C.features(Pd, "D")
    bd = Pd["BTC.D"].values
    vold = Xd["btcd_vol13w"].values
    rows = law_events(bd, vold, k=1.0)
    harness_ev = C.events(Pd["BTC.D"].loc["2016":], 5.0, freq="D")
    # the nine test events are the harness's 5+ point falls since 2016 (13-week peaks, 26-week window), as the plan says;
    # the reversal-rule (rev 0.4/0.6/0.8) durations of the daily k=5 crossing events are printed beside them
    pos_of = {d: i for i, d in enumerate(Pd.index)}
    tests = [{"peak_i": pos_of[e["peak"]], "trough_i": pos_of[e["trough"]], "size": e["from"] - e["to"], "dur": max(1, e["days"]), "peak": e["peak"]} for e in harness_ev]
    dur = {"nDailyEventsK1": len(rows), "nSmall": int(sum(r["size"] < LAW_MAX_SIZE for r in rows)), "tests": [], "rules": {}}
    for rv in (0.4, 0.6, 0.8):
        ev_r = [e for e in crossing_states(bd, 5.0, rv)[2] if Pd.index[e["peak_i"]] >= pd.Timestamp("2016-01-01")]
        dur["rules"][f"rev{rv}"] = [{"peak": str(Pd.index[e["peak_i"]].date()), "days": int(e["dur"]), "size": round(float(e["size"]), 1)} for e in ev_r]
    dur["rules"]["harnessWindowed"] = [{"peak": str(e["peak"].date()), "days": e["days"], "size": round(e["from"] - e["to"], 1)} for e in harness_ev]
    scores = {"law": [], "blind": [], "owner90": [], "sur": []}
    sur_laws = [r for r in sur["iaaft"] if r["lawSlope"] is not None]
    fits_by_event = []
    for e in tests:
        law = fit_law(rows, e["peak_i"])
        x = np.log(max(e["dur"], 1))
        rec = {"peak": str(Pd.index[e["peak_i"]].date()), "trough": str(Pd.index[e["trough_i"]].date()), "size": round(float(e["size"]), 1), "days": int(e["dur"]),
               "big": str(Pd.index[e["peak_i"]].date())[:7] in ("2016-11", "2017-12", "2021-01")}
        if law is None:
            rec["note"] = "too few training events"
            dur["tests"].append(rec)
            continue
        v0 = vold[e["peak_i"]]
        z = np.array([1.0, np.log(e["size"]), np.log(v0)])
        mu = float(z @ np.array(law["beta"]))
        rec["lawMedianDays"] = round(float(np.exp(mu)), 1)
        rec["lawBand10_90"] = [round(float(np.exp(mu - 1.2816 * law["sd"])), 1), round(float(np.exp(mu + 1.2816 * law["sd"])), 1)]
        rec["nTrain"] = law["n"]
        rec["slope"] = round(law["beta"][1], 3)
        scores["law"].append(score_law(mu, law["sd"], x))
        b0, s0 = law["blind"]
        scores["blind"].append(score_law(float(b0[0]), s0, x))
        scores["owner90"].append(abs(np.log(OWNER_DAYS) - x))
        if sur_laws:
            # surrogate law: score each surrogate's own slopes (real intercept and residual sd) and take the median score
            sl = []
            for r in sur_laws:
                beta_s = np.array([law["beta"][0], r["lawSlope"], r["lawVol"]])
                sl.append(score_law(float(z @ beta_s), law["sd"], x))
            scores["sur"].append((float(np.median([v[0] for v in sl])), float(np.median([v[1] for v in sl])), float(np.median([v[2] for v in sl]))))
        rec["lawAbsLogErr"] = round(abs(mu - x), 3)
        rec["owner90AbsLogErr"] = round(float(abs(np.log(OWNER_DAYS) - x)), 3)
        fits_by_event.append(law)
        dur["tests"].append(rec)

    def agg(lst):
        if not lst:
            return None
        return {"coverage": f"{int(sum(v[0] >= 0.5 for v in lst))}/{len(lst)}", "intervalScore": round(float(np.mean([v[1] for v in lst])), 3), "logScore": round(float(np.mean([v[2] for v in lst])), 3)}
    dur["lawScores"] = {"law": agg(scores["law"]), "sizeBlind": agg(scores["blind"]), "iaaftLaw": agg(scores["sur"]), "owner90AbsLogErr": (round(float(np.mean(scores["owner90"])), 3) if scores["owner90"] else None),
                        "lawAbsLogErr": (round(float(np.mean([t["lawAbsLogErr"] for t in dur["tests"] if "lawAbsLogErr" in t])), 3) if scores["law"] else None)}
    big = [t for t in dur["tests"] if t.get("big") and "lawMedianDays" in t]
    dur["bigThree"] = {"coverage": f"{sum(t['lawBand10_90'][0] <= t['days'] <= t['lawBand10_90'][1] for t in big)}/{len(big)}", "events": big}
    law_all = fit_law(rows, None)
    dur["lawFullSample"] = law_all
    dur["H_fromLaw"] = (round(1 / law_all["beta"][1], 3) if law_all and law_all["beta"][1] > 0 else None)
    slopes = nres["surrogates"]["iaaft"]["lawSlope"]
    fslopes = nres["surrogates"]["fbm"]["lawSlope"]
    dur["lawSlopeNull"] = {"real": (round(law_all["beta"][1], 3) if law_all else None), "iaaft": C.null_summary(law_all["beta"][1] if law_all else None, slopes), "fbm": C.null_summary(law_all["beta"][1] if law_all else None, fslopes)}
    say(f"-- duration law log(days) = a + s log(size) + c log(vol0), daily reversal-ended events size < {LAW_MAX_SIZE:g} (n {dur['nSmall']} of {dur['nDailyEventsK1']}), walked forward event by event over the {len(tests)} harness 5+ falls since 2016")
    la = law_all["beta"] if law_all else [None] * 3
    say(f"   full-sample law: s {fmt(la[1])} (H = 1/s {fmt(dur['H_fromLaw'])}) c {fmt(la[2])} sd {fmt(law_all['sd'] if law_all else None)}; slope null IAAFT median {fmt(dur['lawSlopeNull']['iaaft'].get('nullMedian'))} [{fmt(dur['lawSlopeNull']['iaaft'].get('nullP05'))},{fmt(dur['lawSlopeNull']['iaaft'].get('nullP95'))}] fBm median {fmt(dur['lawSlopeNull']['fbm'].get('nullMedian'))} [{fmt(dur['lawSlopeNull']['fbm'].get('nullP05'))},{fmt(dur['lawSlopeNull']['fbm'].get('nullP95'))}]")
    say(f"   scores (10-90% band): law {dur['lawScores']['law']} | size-blind {dur['lawScores']['sizeBlind']} | IAAFT-law {dur['lawScores']['iaaftLaw']} | owner 90d abs log err {dur['lawScores']['owner90AbsLogErr']} vs law {dur['lawScores']['lawAbsLogErr']}; big three covered {dur['bigThree']['coverage']}")
    say("   events (peak, size, harness days | law median [10-90] on n train): " + "; ".join(f"{t['peak'][:7]} {t['size']} {t['days']}d | {t.get('lawMedianDays')} {t.get('lawBand10_90')} n{t.get('nTrain')}" for t in dur["tests"]))
    say("   daily k=5 crossing events by reversal rule (peak month:days): rev0.4 " + ",".join(f"{e['peak'][2:7]}:{e['days']}" for e in dur["rules"]["rev0.4"])
        + " | rev0.6 " + ",".join(f"{e['peak'][2:7]}:{e['days']}" for e in dur["rules"]["rev0.6"]) + " | rev0.8 " + ",".join(f"{e['peak'][2:7]}:{e['days']}" for e in dur["rules"]["rev0.8"])
        + " (the harness window caps a fall at 26 weeks from a 13-week peak; a reversal rule splits 2017 and 2021 into several legs)")
    # sojourn laws per state across thresholds
    soj = sojourn_block(bd, SOJOURN_K, n_soj, rng)
    dur["sojourns"] = soj
    say("   sojourn Weibull (daily, FALL = crossing to trough): " + "; ".join(f"k{k:g} shape {soj[str(k)]['FALL'].get('shape')} [{soj[str(k)]['FALL'].get('shape05')},{soj[str(k)]['FALL'].get('shape95')}] scale {soj[str(k)]['FALL'].get('scaleDays')}d n {soj[str(k)]['FALL'].get('n')}" for k in SOJOURN_K)
        + f"; log-log slope scale vs k {soj.get('logLogSlope_FALL')} (peak-to-trough {soj.get('logLogSlope_PEAK_TO_TROUGH')}) vs law s {fmt(la[1])}")
    # remaining-duration model
    rem = {"tests": []}
    cov_r, cov_n = [], []
    is_r, is_n = [], []
    for e in tests:
        R = remaining_rows(bd, rows, e["peak_i"])          # all completed daily events confirmed before this event's peak
        if len(R) < 20:
            continue
        Z = R[:, :2]
        mu, sd = C.zfit(Z)
        th = weib_fit(R[:, 2], np.ones(len(R)), C.zapply(Z, mu, sd), lam=RIDGE_BETA)
        th0 = weib_fit(R[:, 2], np.ones(len(R)), np.zeros((len(R), 0)), lam=0.0)
        al = np.exp(th[0])
        for f in (0.25, 0.5, 0.75):
            i = e["peak_i"] + max(1, int(round(f * e["dur"])))
            if i >= e["trough_i"]:
                continue
            depth = max(bd[e["peak_i"]] - bd[i], 0.05)
            z = C.zapply(np.array([[np.log(i - e["peak_i"]), np.log(depth)]]), mu, sd)
            lam_i = np.exp(th[1] - (z @ th[2:])[0] / al)
            q = weib_q
            realised = float(e["trough_i"] - i)
            lo_, hi_ = q(0.1, lam_i, al), q(0.9, lam_i, al)
            lo0, hi0 = q(0.1, np.exp(th0[1]), np.exp(th0[0])), q(0.9, np.exp(th0[1]), np.exp(th0[0]))
            cov_r.append(lo_ <= realised <= hi_)
            cov_n.append(lo0 <= realised <= hi0)
            is_r.append((np.log(hi_) - np.log(lo_)) + 10 * (max(np.log(lo_) - np.log(realised), 0) + max(np.log(realised) - np.log(hi_), 0)))
            is_n.append((np.log(hi0) - np.log(lo0)) + 10 * (max(np.log(lo0) - np.log(realised), 0) + max(np.log(realised) - np.log(hi0), 0)))
            rem["tests"].append({"peak": str(Pd.index[e["peak_i"]].date()), "frac": f, "elapsed": int(i - e["peak_i"]), "depth": round(float(depth), 1), "remaining": int(realised),
                                 "median": round(float(q(0.5, lam_i, al)), 1), "band10_90": [round(float(lo_), 1), round(float(hi_), 1)], "naiveBand": [round(float(lo0), 1), round(float(hi0), 1)]})
    rem["coverage"] = f"{int(sum(cov_r))}/{len(cov_r)}"
    rem["naiveCoverage"] = f"{int(sum(cov_n))}/{len(cov_n)}"
    rem["intervalScore"], rem["naiveIntervalScore"] = (round(float(np.mean(is_r)), 3) if is_r else None), (round(float(np.mean(is_n)), 3) if is_n else None)
    rem["note"] = "DESCRIPTIVE: evaluated at fractions of the realised duration with depth from the centred harness peak (both known only afterwards)"
    dur["remaining"] = rem
    # forecast form (point in time): at the k=5 crossing bar + 7 / 14 / 28 days, elapsed days since the running maximum and
    # depth below it (both known at that bar), model trained on daily events confirmed before the crossing bar; the target is
    # the days from that bar to the harness trough
    ev5 = crossing_states(bd, 5.0, REV)[2]
    ff = {"tests": [], "note": "point-in-time form: origin = k5 crossing bar + 7/14/28 days; elapsed and depth from the running max known at that bar; target = days to the harness trough"}
    cov_f, cov_fn, is_f, is_fn, unscorable = [], [], [], [], 0
    for e in tests:
        c5 = [x for x in ev5 if e["peak_i"] <= x["cross_i"] <= e["trough_i"]]
        if not c5:
            unscorable += 1
            continue
        x = c5[0]
        R = remaining_rows(bd, rows, x["cross_i"])
        if len(R) < 20:
            unscorable += 1
            continue
        Z = R[:, :2]
        mu, sd = C.zfit(Z)
        th = weib_fit(R[:, 2], np.ones(len(R)), C.zapply(Z, mu, sd), lam=RIDGE_BETA)
        th0 = weib_fit(R[:, 2], np.ones(len(R)), np.zeros((len(R), 0)), lam=0.0)
        al = np.exp(th[0])
        for dd_ in (7, 14, 28):
            i = x["cross_i"] + dd_
            if i >= e["trough_i"] or i >= len(bd):
                continue
            depth = max(x["peak"] - bd[i], 0.05)
            z = C.zapply(np.array([[np.log(i - x["peak_i"]), np.log(depth)]]), mu, sd)
            lam_i = np.exp(th[1] - (z @ th[2:])[0] / al)
            realised = float(e["trough_i"] - i)
            lo_, hi_ = weib_q(0.1, lam_i, al), weib_q(0.9, lam_i, al)
            lo0, hi0 = weib_q(0.1, np.exp(th0[1]), np.exp(th0[0])), weib_q(0.9, np.exp(th0[1]), np.exp(th0[0]))
            cov_f.append(lo_ <= realised <= hi_)
            cov_fn.append(lo0 <= realised <= hi0)
            is_f.append((np.log(hi_) - np.log(lo_)) + 10 * (max(np.log(lo_) - np.log(realised), 0) + max(np.log(realised) - np.log(hi_), 0)))
            is_fn.append((np.log(hi0) - np.log(lo0)) + 10 * (max(np.log(lo0) - np.log(realised), 0) + max(np.log(realised) - np.log(hi0), 0)))
            ff["tests"].append({"peak": str(Pd.index[e["peak_i"]].date()), "crossing": str(Pd.index[x["cross_i"]].date()), "daysAfterCrossing": dd_, "elapsed": int(i - x["peak_i"]), "depth": round(float(depth), 1),
                                "remaining": int(realised), "median": round(float(weib_q(0.5, lam_i, al)), 1), "band10_90": [round(float(lo_), 1), round(float(hi_), 1)], "naiveBand": [round(float(lo0), 1), round(float(hi0), 1)], "nTrain": int(len(R))})
    ff["coverage"], ff["naiveCoverage"] = f"{int(sum(cov_f))}/{len(cov_f)}", f"{int(sum(cov_fn))}/{len(cov_fn)}"
    ff["intervalScore"], ff["naiveIntervalScore"] = (round(float(np.mean(is_f)), 3) if is_f else None), (round(float(np.mean(is_fn)), 3) if is_fn else None)
    ff["unscorableEvents"] = unscorable
    dur["remainingForecastForm"] = ff
    dur["lawNote"] = "DESCRIPTIVE: the law's regressor is the realised size (known at the trough) and the test events are 13-week-centred peaks; its coverage is a scaling check, not a forecast score"
    hd = [e["days"] for e in harness_ev]
    dur["forecastInput"] = {"empiricalRangeDays": [int(min(hd)), int(max(hd))], "medianDays": float(np.median(hd)), "n": len(hd),
                            "note": "the only duration input for the forecast object: the empirical 9-event range, unidentified; the law and the remaining-duration models are descriptive"}
    res["duration"] = dur
    say(f"   remaining-duration model (Weibull, log scale on log elapsed + log depth, daily events ended before each test event): DESCRIPTIVE form at 25/50/75% of realised duration coverage {rem['coverage']} vs naive {rem['naiveCoverage']}, interval score {rem['intervalScore']} vs {rem['naiveIntervalScore']}"
        f" | FORECAST form at the k5 crossing + 7/14/28d (elapsed/depth from the running max known then): coverage {ff['coverage']} vs naive {ff['naiveCoverage']}, interval score {ff['intervalScore']} vs {ff['naiveIntervalScore']} ({ff['unscorableEvents']} events unscorable)"
        f" | forecast input = empirical range {dur['forecastInput']['empiricalRangeDays']} d (median {dur['forecastInput']['medianDays']:.0f}), unidentified")

    # ------------------------------------------------------------------ today
    today = {"asOf": str(D.index[-1].date()), "lastCompleteSunday": str(max(d for d in idxW if d <= D.index[-1]).date()), "provisionalBars": provisional, "btcd": round(float(D["BTC.D"].iloc[-1]), 2)}
    g = W5
    last_complete = int(np.where(g["idx"] <= D.index[-1])[0][-1])
    for k in K_W:
        w = walks[("W", k, "full")]
        for lbl, pos in (("lastCompleteSunday", last_complete), ("provisional", len(g["idx"]) - 1)):
            S = w["S"][pos]
            if not np.isfinite(S[0]):
                continue
            med = next((int(h) for h, s in zip(HGRID, S) if s <= 0.5), None)
            p10 = next((int(h) for h, s in zip(HGRID, S) if s <= 0.9), None)
            p90 = next((int(h) for h, s in zip(HGRID, S) if s <= 0.1), None)
            lf = w["last"]
            z = C.zapply(g["F"][MODELS["full"]].values[pos:pos + 1].astype(float), lf["mu"], lf["sd"])[0]
            contrib = dict(zip(MODELS["full"], [round(float(b * zz), 3) for b, zz in zip(lf["theta"][2:], z)]))
            rd = {"P13": round(float(1 - S[12]), 4), "P26": round(float(1 - S[25]), 4), "P52": round(float(1 - S[51]), 4), "medianWeeks": (med if med else f"> {HORIZON_W}w"),
                  "w10": p10, "w90": (p90 if p90 else f"> {HORIZON_W}w"), "hazardNextWeek": round(float(1 - S[0]), 4),
                  "drivers": {c: contrib[c] for c in COV}, "clockContribution": {c: contrib[c] for c in CLOCK}, "alpha": round(float(np.exp(lf["theta"][0])), 3), "lambdaWeeks": round(float(np.exp(lf["theta"][1])), 1)}
            today[f"k{int(k)}_{lbl}"] = rd
        # sensitivity at the last complete Sunday: each covariate dropped (refit on the last training set) and +/-1 sd
        lf = w["last"]
        sens = {}
        Ftr = g["F"][MODELS["full"]].values.astype(float)
        bpw = 1.0
        for j, c in enumerate(MODELS["full"]):
            keep = [i for i in range(len(MODELS["full"])) if i != j]
            mu, sd = C.zfit(Ftr[lf["tr"]][:, keep])
            th = weib_fit(lf["obs"] / bpw, lf["ev"], C.zapply(Ftr[lf["tr"]][:, keep], mu, sd))
            S = weib_S(th, C.zapply(Ftr[last_complete:last_complete + 1][:, keep], mu, sd), [26.0])[0, 0]
            z = C.zapply(Ftr[last_complete:last_complete + 1], lf["mu"], lf["sd"])
            zp, zm = z.copy(), z.copy()
            zp[0, j] += 1
            zm[0, j] -= 1
            sens[c] = {"dropped": round(float(1 - S), 4), "plus1sd": round(float(1 - weib_S(lf["theta"], zp, [26.0])[0, 0]), 4), "minus1sd": round(float(1 - weib_S(lf["theta"], zm, [26.0])[0, 0]), 4)}
        today[f"k{int(k)}_sensitivityP26"] = sens
        vals = [v[x] for v in sens.values() for x in ("dropped", "plus1sd", "minus1sd")]
        today[f"k{int(k)}_sensitivitySpread"] = [round(min(vals), 4), round(max(vals), 4)]
    stateW = int(W5["F"]["state"].iloc[last_complete])
    stateD = int(scales[("D", K_D)]["F"]["state"].iloc[-1])
    today["stateWeeklyK5"] = ["BASE", "FALL", "RECOVERY"][stateW]
    today["stateDailyK2"] = ["BASE", "FALL", "RECOVERY"][stateD]
    today["weeksSinceConfirmedTroughK5"] = round(float(np.expm1(W5["F"]["clock_renewal"].iloc[last_complete])), 1)
    today["weeksSinceConfirmedTroughDailyK2"] = round(float(np.expm1(scales[("D", K_D)]["F"]["clock_renewal"].iloc[-1])), 1)
    vol_hist = W5["X"]["btcd_vol13w"].iloc[:last_complete + 1].dropna()
    today["btcdVol13wPercentile"] = round(float((vol_hist <= vol_hist.iloc[-1]).mean() * 100), 1)
    # comparators read at the last complete Sunday (the same bar as the hazard reading; oos[...]["today"] is the provisional bar)
    today["fixed5_P26"] = (round(float(p26f.iloc[last_complete]), 4) if np.isfinite(p26f.iloc[last_complete]) else None)
    today["m2only_P26"] = (round(float(p26m2.iloc[last_complete]), 4) if np.isfinite(p26m2.iloc[last_complete]) else None)
    today["fixed5_P26_provisionalBar"] = oos["W:k5:fixed5_logistic"]["today"]
    today["stacked_P26"] = (round(float(stack.iloc[last_complete]), 4) if np.isfinite(stack.iloc[last_complete]) else None)
    today["logitMean_P26"] = (round(float(mean_logit.iloc[last_complete]), 4) if np.isfinite(mean_logit.iloc[last_complete]) else None)
    today["baseRate2019"] = round(float(W5["Y"]["fall26"].loc["2019":].mean()), 3)
    today["nestedP26_k5"] = {n: (round(float(1 - walks[("W", K_W[0], n)]["S"][last_complete, 25]), 4) if np.isfinite(walks[("W", K_W[0], n)]["S"][last_complete, 25]) else None) for n in HEADLINE_ROWS}
    today["nestedP26_k10"] = {n: (round(float(1 - walks[("W", K_W[1], n)]["S"][last_complete, 25]), 4) if np.isfinite(walks[("W", K_W[1], n)]["S"][last_complete, 25]) else None) for n in ["clock", "five", "full", "full_noM2"]}
    vals5 = [v for v in today["nestedP26_k5"].values() if v is not None] + [today["fixed5_P26"], today["m2only_P26"]]
    today["spreadP26_k5_allSpecs"] = [round(min(vals5), 4), round(max(vals5), 4)]
    today["recalibratedP26"] = {cn: res["calibration"][f"W_k5_{cn}"]["todayRecalibrated"] for cn in cal_rows}
    rc = [v for v in today["recalibratedP26"].values() if v is not None]
    today["spreadP26_recalibrated"] = [round(min(rc), 4), round(max(rc), 4)] if rc else None
    today["shapeValidated"] = False
    today["shapeNote"] = "the Weibull shape fails its checks (calibration slope band excludes 1, KM terciles not monotone, PIT skewed): medianWeeks / w10 / w90 are NOT forecasts"
    # sign stability of each driver: AUC26 by era of the raw covariate with the fitted sign (a driver whose 2023-26 AUC is below 0.5 pulls today's reading the wrong way in the only era like today)
    lf5 = walks[("W", K_W[0], "full")]["last"]
    stab = {}
    for j, c in enumerate(MODELS["full"]):
        sgn = 1.0 if lf5["theta"][2 + j] >= 0 else -1.0
        met = C.metrics(pd.Series(sgn * W5["F"][c].values, index=W5["idx"]), W5["Y"]["fall26"], True)
        stab[c] = {"betaSign": int(sgn), "auc26ByEra": [met.get(e, {}).get("auc") for e in ERAS3], "invertedIn2023_26": bool((met.get("2023-2026", {}).get("auc") or 0.5) < 0.5)}
    today["driverSignStability"] = stab
    dd = scales[("D", K_D)]
    SD = daily_full["S"][-1] if daily_full is not None else None
    if SD is not None and np.isfinite(SD[0]):
        today["dailyK2"] = {"P13": round(float(1 - SD[12]), 4), "P26": round(float(1 - SD[25]), 4), "medianWeeks": next((int(h) for h, s in zip(HGRID, SD) if s <= 0.5), f"> {HORIZON_W}w")}
    res["today"] = today
    t5 = today.get("k5_lastCompleteSunday", {})
    t10 = today.get("k10_lastCompleteSunday", {})
    say(f"-- today ({today['lastCompleteSunday']}, BTC.D {today['btcd']}, state weekly k5 {today['stateWeeklyK5']} / daily k2 {today['stateDailyK2']}, {today['weeksSinceConfirmedTroughK5']} weeks since the confirmed 5-pt trough, vol13w pct {today['btcdVol13wPercentile']})")
    def wk(v):
        return v if isinstance(v, str) else f"{v}w"
    say(f"   5-pt fall: P13 {t5.get('P13')} P26 {t5.get('P26')} P52 {t5.get('P52')} median {wk(t5.get('medianWeeks'))} (10-90% {wk(t5.get('w10'))} to {wk(t5.get('w90'))}) hazard/wk {t5.get('hazardNextWeek')} alpha {t5.get('alpha')} lambda {t5.get('lambdaWeeks')}w | fixed5 {today['fixed5_P26']} m2only {today['m2only_P26']} stacked {today['stacked_P26']} logitMean {today['logitMean_P26']} base {today['baseRate2019']}")
    say(f"   drivers (beta*z): {t5.get('drivers')} clock {t5.get('clockContribution')}; sensitivity P26 spread {today.get('k5_sensitivitySpread')} (drop/+-1sd each input); "
        f"drivers whose fitted sign is INVERTED in 2023-26 (raw AUC26 < 0.5 in that era): {[c for c, v in today['driverSignStability'].items() if v['invertedIn2023_26']]}; "
        f"recalibrated P26 on each model's own OOS line {today['recalibratedP26']} spread {today['spreadP26_recalibrated']} (raw spread {today['spreadP26_k5_allSpecs']}); median/10-90% weeks NOT forecasts (shape fails calibration)")
    say(f"   10-pt fall: P13 {t10.get('P13')} P26 {t10.get('P26')} median {wk(t10.get('medianWeeks'))} | daily k=2: {today.get('dailyK2')} | nested P26 today k5 {today['nestedP26_k5']} k10 {today['nestedP26_k10']}; spread over all specs {today['spreadP26_k5_allSpecs']} (headline: the spread, not the centre)")

    # ------------------------------------------------------------------ cheap checks
    chk = res["checks"]
    bpw = 1.0
    bfull = scales[("W", K_W[0])]["P"]["BTC.D"].values
    chk["truncation"] = C.truncation_test(lambda end: clock_series(bfull[:end + 1], K_W[0], bpw)[0], len(bfull), n=20, rng=rng)
    chk["refitJumps"] = C.refit_jump_report(p26h, [r["t"] for r in wfull["refits"]])
    chk["params"] = C.params_report(2 + len(MODELS["full"]), nposW["k5"]["episodes"])
    firstW = int(np.searchsorted(W5["idx"], pd.Timestamp(FIRST)))
    obs5, ev5w = oos_spells(W5["Y"]["tte"].values, W5["Y"]["cens"].values, len(W5["idx"]), C.bars(HORIZON_W, "W"))
    postW = np.arange(len(W5["idx"])) >= firstW
    dP = scales[("D", K_D)]["P"]
    evD = crossing_states(dP["BTC.D"].values, K_D)[2]
    firstD = int(np.searchsorted(dP.index, pd.Timestamp(FIRST)))
    chk["sample"] = {"weeklyK5CrossingsTotal": len(evW5), "weeklyK5CrossingsBeforeFirstForecast": int(sum(e["cross_i"] < firstW for e in evW5)), "weeklyK5CrossingsOOS": int(sum(e["cross_i"] >= firstW for e in evW5)),
                     "firstRefit": {"origins": wfull["refits"][0]["nTrain"], "originEvents": wfull["refits"][0]["nEvents"], "distinctCrossingBars": wfull["refits"][0].get("nCrossingBars")},
                     "oos": {"origins": int(postW.sum()), "originEvents": int(ev5w[postW].sum()), "distinctCrossingBars": int(len(np.unique((np.arange(len(W5["idx"])) + obs5)[postW & (ev5w > 0.5)])))},
                     "dailyK2CrossingsOOS": int(sum(e["cross_i"] >= firstD for e in evD)), "dailyK2CrossingsByYear": {str(y): int(n) for y, n in pd.Series([dP.index[e["cross_i"]].year for e in evD if e["cross_i"] >= firstD]).value_counts().sort_index().items()},
                     "note": "the Weibull likelihood treats every origin as independent; the independent information is the crossings (8 before 2019, 10 OOS, 43 daily k=2 OOS), so the ridge of 1 on standardised betas is negligible and the pre-registered model fits 10 parameters on 8 crossings"}
    chk["params"]["crossingsAtFirstRefit"] = chk["sample"]["weeklyK5CrossingsBeforeFirstForecast"]
    chk["params"]["noteCrossings"] = "more parameters than independent crossings at the first refit" if chk["params"]["parameters"] > chk["params"]["crossingsAtFirstRefit"] else "fewer parameters than crossings"
    chk["adminCensoringTruncatedPanel"] = admin_censor_truncation_check(W5["P"], "W", K_W[0], firstW, C.bars(HORIZON_W, "W"))
    chk["episodeLOO_W_k5_full"] = C.episode_loo(p26h[era_of(g["idx"]) >= 0], y26[era_of(g["idx"]) >= 0])
    chk["episodeLOO_W_k5_fixed5"] = C.episode_loo(p26f[era_of(g["idx"]) >= 0], y26[era_of(g["idx"]) >= 0])
    # clock and era-mean decoys within each era (harness walk)
    Yh = C.targets(g["P"], "W")
    pr_h, _ = B.run_fixed(g["X"], Yh, "fall5_26w", "W", True, ["days_since_halving"])

    def fit_mean(Xtr, ytr):
        return float(np.mean(ytr[-104:]))

    def pred_mean(model, Xh, te):
        return np.full(len(te), model)
    pr_m, _ = C.walk_forward(g["X"][["m2_yoy"]], Yh["fall5_26w"], fit_mean, pred_mean, freq="W", label_lag_weeks=26)
    chk["decoysByEra"] = {"halvingClock": {e: v.get("auc") for e, v in C.metrics(pr_h, g["Y"]["fall26"], True).items()}, "eraMean": {e: v.get("auc") for e, v in C.metrics(pr_m, g["Y"]["fall26"], True).items()},
                          "hazardFull": {e: v.get("auc") for e, v in oos["W:k5:full"]["auc26"].items()}}
    chk["decoysByEra"]["eraMeanInverted"] = {e: (None if v is None else round(1 - v, 3)) for e, v in chk["decoysByEra"]["eraMean"].items()}
    # refractory decoys (sign learned in the walk): trailing 104-week frequency of KNOWN labels (lagged 26 weeks) and weeks since the last known positive label
    lab = Yh["fall5_26w"].shift(26)
    freq104 = lab.rolling(104, min_periods=26).mean()
    last_pos = pd.Series(np.where(lab.values == 1, np.arange(len(lab)), np.nan), index=lab.index).ffill()
    Xdec = pd.DataFrame({"labelFreq104w": freq104.values, "weeksSinceLastPos": np.log1p(np.arange(len(lab)) - last_pos.values)}, index=g["X"].index)
    for cols_ in (["labelFreq104w"], ["weeksSinceLastPos"], ["labelFreq104w", "weeksSinceLastPos"]):
        pr_r, _ = B.run_fixed(Xdec, Yh, "fall5_26w", "W", True, cols_)
        chk["decoysByEra"]["refractory_" + "+".join(cols_)] = {e: v.get("auc") for e, v in C.metrics(pr_r, g["Y"]["fall26"], True).items()}
    chk["adminCensoring"] = {"assertedEveryRefit": True, "lastRefit": wfull["refits"][-1], "firstRefit": wfull["refits"][0]}
    # optimiser convergence at the last weekly refit: gradient norm of the Weibull log-likelihood
    lf = wfull["last"]
    Zl = C.zapply(Fv[lf["tr"]], lf["mu"], lf["sd"])
    th = lf["theta"]
    eps = 1e-5
    ll0 = weib_ll(th, np.log(np.maximum(lf["obs"], 1e-3)), lf["ev"], Zl, np.zeros(len(Zl)), np.r_[0, 0, np.ones(Zl.shape[1]) * RIDGE_BETA])
    gnum = [(weib_ll(th + eps * np.eye(len(th))[j], np.log(np.maximum(lf["obs"], 1e-3)), lf["ev"], Zl, np.zeros(len(Zl)), np.r_[0, 0, np.ones(Zl.shape[1]) * RIDGE_BETA]) - ll0) / eps for j in range(len(th))]
    chk["weibullConvergence"] = {"maxAbsGradLastRefit": round(float(np.max(np.abs(gnum))), 4), "logLik": round(float(ll0), 2)}
    smp = chk["sample"]
    say(f"-- checks: truncation ok {chk['truncation']['ok']} (max diff {chk['truncation']['maxAbsDiff']:.1e}); P26 jump at refits {chk['refitJumps']['maxJumpAtRefit']} vs elsewhere {chk['refitJumps']['maxJumpElsewhere']}; "
        f"params {chk['params']['parameters']} vs {chk['params']['labelEpisodes']} label episodes and {chk['params']['crossingsAtFirstRefit']} crossings at the first refit ({chk['params']['noteCrossings']}); "
        f"admin censoring asserted against the raw columns at every refit, truncated-panel check events/obs match {chk['adminCensoringTruncatedPanel']['eventsMatch']}/{chk['adminCensoringTruncatedPanel']['obsMatch']} (first refit {chk['adminCensoring']['firstRefit']}); "
        f"Weibull max |grad| at last refit {chk['weibullConvergence']['maxAbsGradLastRefit']}")
    say(f"   SAMPLE (the counts that matter are crossings, not origin-events): weekly k5 crossings {smp['weeklyK5CrossingsTotal']} total, {smp['weeklyK5CrossingsBeforeFirstForecast']} before 2019-01-06, {smp['weeklyK5CrossingsOOS']} OOS; "
        f"first refit {smp['firstRefit']['origins']} origins / {smp['firstRefit']['originEvents']} origin-events / {smp['firstRefit']['distinctCrossingBars']} distinct crossing bars; OOS {smp['oos']['origins']} origins / {smp['oos']['originEvents']} origin-events / {smp['oos']['distinctCrossingBars']} crossing bars; "
        f"daily k2 crossings OOS {smp['dailyK2CrossingsOOS']} by year {smp['dailyK2CrossingsByYear']}")
    lo5 = chk["episodeLOO_W_k5_full"]
    dbe = chk["decoysByEra"]
    say(f"   episode LOO W:k5:full AUC26 all {lo5['all']} min {lo5['min']} ({lo5['minEpisode']}); fixed5 min {chk['episodeLOO_W_k5_fixed5']['min']} ({chk['episodeLOO_W_k5_fixed5']['minEpisode']}); decoys by era halving " + "/".join(fmt(dbe['halvingClock'].get(e)) for e in ERAS3)
        + " era-mean " + "/".join(fmt(dbe['eraMean'].get(e)) for e in ERAS3) + " (inverted " + "/".join(fmt(dbe['eraMeanInverted'].get(e)) for e in ERAS3) + ") refractory: label-freq104w " + "/".join(fmt(dbe['refractory_labelFreq104w'].get(e)) for e in ERAS3)
        + " weeks-since-last-positive " + "/".join(fmt(dbe['refractory_weeksSinceLastPos'].get(e)) for e in ERAS3) + " both " + "/".join(fmt(dbe['refractory_labelFreq104w+weeksSinceLastPos'].get(e)) for e in ERAS3)
        + " (sign learned in the walk) vs hazard full " + "/".join(fmt(dbe['hazardFull'].get(e)) for e in ERAS3) + " cov_renewal " + eras_of('W:k5:cov_renewal') + " five " + eras_of('W:k5:five'))
    if "decoyBetas" in chk:
        say(f"   decoy passengers (full_decoys last refit): mean |beta| real {chk['decoyBetas']['meanAbsReal']} vs decoys {chk['decoyBetas']['meanAbsDecoy']} (max {chk['decoyBetas']['maxAbsDecoy']}); real betas {chk['decoyBetas']['real']}")

    # ------------------------------------------------------------------ success criteria (as pre-registered in ROUND8_PLAN.md [4])
    e_full, e_clock, e_five, e_fx = oos["W:k5:full"], oos["W:k5:clock"], oos["W:k5:five"], oos["W:k5:fixed5_logistic"]
    cF, cC, cV = e_full.get("C"), e_clock.get("C"), e_five.get("C")
    a26F, a26X = e_full["auc26"].get("pooled", {}).get("auc"), e_fx["auc26"].get("pooled", {}).get("auc")
    b26F, b26X = e_full["auc26"].get("pooled", {}).get("brier"), e_fx["auc26"].get("pooled", {}).get("brier")
    crit = {
        "C_beats_clock_and_five_by_0.03_p<0.05": bool(cF is not None and cC is not None and cV is not None and cF - cC >= 0.03 and cF - cV >= 0.03 and (nres["W:k5:full"]["C"].get("p") or 1) < 0.05),
        "AUC26_within_0.03_of_fixed5_with_Brier<=": bool(a26F is not None and a26X is not None and a26F >= a26X - 0.03 and b26F is not None and b26F <= b26X),
        "calibration_slope_band_contains_1": bool(cal["slopeBand"].get("q05", 9) <= 1 <= cal["slopeBand"].get("q95", -9)),
        "AUC13>0.6_p<0.05": bool((e_full["auc13"].get("pooled", {}).get("auc") or 0) > 0.6 and (nres["W:k5:full"]["auc13"].get("p") or 1) < 0.05),
        "daily_PIT_not_rejected": (None if "D_k2_pit" not in res["calibration"] else (not res["calibration"]["D_k2_pit"]["rejected"])),
        "transfer_recovers_80pct_of_C_gain": (None if "full" not in res["transfer"] or res["transfer"]["full"].get("gainRecovered") is None else bool(res["transfer"]["full"]["ratioInterpretable"] and res["transfer"]["full"]["gainRecovered"] >= 0.8)),
        "duration_law_coverage>=7of9_and_beats_blind_and_iaaft": (None if dur["lawScores"]["law"] is None else bool(int(dur["lawScores"]["law"]["coverage"].split("/")[0]) >= 7 and dur["lawScores"]["law"]["intervalScore"] < (dur["lawScores"]["sizeBlind"] or {}).get("intervalScore", 9e9)
                                                                                                       and dur["lawScores"]["law"]["intervalScore"] < ((dur["lawScores"]["iaaftLaw"] or {}).get("intervalScore") or 9e9))),
    }
    cr = oos["W:k5:cov_renewal"]
    crb = {e: (cr["auc26"].get(e, {}).get("brier"), cr["auc26"].get(e, {}).get("brierBase")) for e in ERAS3}
    worse = [e for e, (b, bb) in crb.items() if b is not None and bb is not None and b > bb]
    g_m2 = inc_rows["cov_renewal"]["vsM2only"]
    crit["_componentNote"] = (f"POST-HOC decomposition (not pre-registered): dropping the halving sin/cos terms gives cov_renewal C {fmt(cr.get('C'))} vs full {fmt(cF)} vs clock {fmt(cC)}, "
                              f"but cov_renewal's Brier is ABOVE base in {worse if worse else 'no era'} (" + ", ".join(f"{e} {fmt(b, 3)}/{fmt(bb, 3)}" for e, (b, bb) in crb.items()) + ") and its AUC26 gain over M2-alone is "
                              f"{g_m2['gain']:+.3f} with bands [{g_m2['blockBand'].get('q05')},{g_m2['blockBand'].get('q95')}] / ep[{g_m2['episodeBand'].get('q05')},{g_m2['episodeBand'].get('q95')}] (a tie: the liquidity cycle re-labelled)")
    crit["_transferNote"] = ("the pre-registered transfer ratio is " + ("" if res["transfer"].get("full", {}).get("ratioInterpretable") else "NOT ") + "interpretable (the weekly full model must beat the clock for the ratio to mean anything); "
                             "the post-hoc cov_renewal ratio carries a wide band and its C_T - C_W band straddles 0; the 'fast' row (M2 and BTC drawdown removed) is the transfer test for within-cycle covariates")
    crit["_durationNote"] = "the duration-law criterion is scored on the DESCRIPTIVE law (realised size, centred peaks); the point-in-time forecast form is reported beside it and is not better than naive"
    crit["_CNote"] = "Harrell's C with every bar an origin is a between-run-up (era) ranking; the per-era AUC, Brier vs base and fresh-start AUC are the headline, C secondary"
    res["criteria"] = crit
    say("-- pre-registered success criteria: " + "; ".join(f"{k} {v}" for k, v in crit.items() if not k.startswith("_"))
        + ". The pooled numbers rest on about two liquidity swings (M2 moves once per cycle): judge the within-era p and the no-M2 row, not the pooled AUC. " + crit["_componentNote"] + ". " + crit["_transferNote"])

    res["notes"] += [
        f"Last complete Sunday close {today['lastCompleteSunday']}; bars {provisional} are provisional (partial week) and are never in a training set (an origin's spell is censored at the refit).",
        "Onsets dated at the crossing bar; states and the renewal clock come from a causal scan (crossing_states) with the trough confirmed on a 0.6k bounce; the clock counts from the confirmation bar; before the first confirmation it counts from the series start (2014-04).",
        "Administrative censoring: at refit R each training origin t contributes min(T_t, R - t) with event only if t + T_t <= R (asserted every refit); the harness tte is never used raw in training.",
        "Scalers and Weibull parameters from training rows only; the walk is expanding from 2016-06, first forecast 2019-01-06, refit every 13 weeks; warm start from the previous refit only.",
        "Comparator: the five-signal logistic through study8_baselines.run_fixed (unchanged) with the same panel cut; incremental value as a stacked logistic (five signals + logit of the hazard P26, training rows use in-sample hazard P26 of the same refit) and as an equal-weight logit mean.",
        "fall10_26w has one positive episode (Oct 2020 - May 2021) and none since 2023: every k=10 metric ranks one event.",
        "Survival walk, Harrell's C, KM, Weibull/Cox/discrete-hazard fitters, PIT and the C-index block bootstrap are module helpers; study8_common and study8_baselines are not edited.",
        "The duration law is a scaling description (size is known only at the end); the remaining-duration model is the forecasting form. The three big events are inside the nine and are scored once.",
        "No fit-based p-values anywhere: shifted-target nulls (targets rolled >= 26 weeks through standardisation and the Weibull refit), within-era nulls, IAAFT / fBm surrogates of BTC.D with the real covariates, and 26-week block bootstraps.",
        "Decoys: seven random walks generated once on the daily index with the run's single rng, used as deviation from a 30-week mean; never regenerated per refit.",
        "M2 from the harness with its 42-day publication lag; revised vintage.",
        "Daily twin uses the daily panel (every calendar day), k = 2 points, refit every 91 days; its C bootstrap uses every 7th origin to keep pairs independent-ish; the 3-day rung uses k = 3.",
        f"POST-HOC rows {POST_HOC_ROWS} were added after the first results were seen (decomposition and diagnosis of the pre-registered full model); the headline and the success criteria stay on 'full' and nothing is promoted. series.p_fall5_26w is the full model, series.p_fall5_26w_cov_renewal the component without the halving terms.",
        "CORRECTION of the first report: cov_renewal does NOT beat the base-rate Brier in every era; it is above base in 2021-22 (the era holding the only big event), exactly as fixed5 is; only its pooled Brier is below base, because the 2023-26 era (base 0.09) dominates the pool. m2_yoy alone as a Weibull scores at least as well as cov_renewal (one_m2_yoy row), so the covariate hazards are the M2 liquidity cycle re-labelled; the five-signal hazard loses to its own logistic form.",
        "Harrell's C with every bar an origin: about 99% of comparable pairs are between run-ups, so C mainly ranks eras by time to the next crossing; the within-run-up C, the one-origin-per-run-up C and the run-up bootstrap band are printed beside it. Under Weibull PH with one alpha, -S(26) is monotone in beta.z, so C carries the same information as AUC26 and validates nothing survival-specific.",
        "The Weibull SHAPE is falsified by its own checks (calibration slope 0.2-0.5 with the band excluding 1 for the hazard rows, KM terciles not monotone, censoring-adjusted PIT skewed low at both scales): median and 10-90% weeks-to-crossing are not forecasts and are flagged shapeValidated = False in today.",
        "Today's reading is printed raw and recalibrated on each model's own OOS calibration line; the recalibrated spread is no narrower than the raw one and the ordering changes. The two largest drivers of the full model today (halving phase, BTC.D vol in points) are inverted in 2023-26; the vol term is the mechanical-rarity confound the plan flagged (the last two falls began from today's vol percentile). Dynamics-rule iterations left for the next round: gate or drop the halving phase, state vol in sigma units with a regime gate, count the renewal clock from the last fall of the headline size (the Dec 2024 2-point crossing resets it just before the Apr 2025 fall).",
        "Transfer: the pre-registered ratio is undefined when the weekly full model does not beat the clock (it does not); the post-hoc cov_renewal ratio is reported with a paired block band and C_T - C_W, and its betas that carry it (m2_yoy, btc_dd_ath) move once per cycle and share the calendar across scales, so their sign agreement is not evidence of self-similarity; the 'fast' row removes them and is the honest transfer test for within-cycle covariates.",
        "Nulls: every headline row, the transfer rows and the within-era nulls for full / five / cov_renewal now get the same draw count (20 in --fast: p resolution 0.05, 'p 0.00' means above the maximum of 20 draws); the fBm surrogate is anchored at the real logit's median (anchored at the first value, 99.6% BTC.D, 15 of 20 paths produced no events); usable draw counts are printed beside every p95.",
        "Sample: the Weibull likelihood treats every origin as independent, but the independent information is the crossings (checks.sample); the pre-registered ridge of 1 on standardised betas is negligible against hundreds of overlapping origins, so a check row with the ridge scaled by origins / crossing bars is reported (not headline).",
        "Duration: the law and the fraction-of-duration remaining model are DESCRIPTIVE (realised size, centred peaks, fractions of the realised duration); the point-in-time forecast form (crossing bar + 7/14/28 days, elapsed and depth from the running max known then) is reported and is not better than naive; the forecast module should take only duration.forecastInput (the empirical 9-event range, unidentified).",
        "The 2016-11 event cannot be scored by the walked-forward duration law: BTC.D sat at 95-99 through 2014-16 and only 4 daily 1-point events precede it (the law needs 10).",
        "PIT: the plan's u = S_t(T_t) over uncensored origins is reported raw; it is biased toward 1 by construction (events known to precede the censoring time), so the test uses the censoring-adjusted v = (1 - S(T)) / (1 - S(C)), which is uniform under a correct model.",
    ]
    res["runtimeSec"] = round(time.time() - t0, 1)
    C.write_results(a.out, res)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(1, 2, figsize=(12, 4.2))
        for k in K_W:
            w = walks[("W", k, "full")]
            S = w["S"][last_complete]
            if np.isfinite(S[0]):
                ax[0].plot(HGRID, S, label=f"full k={int(k)}")
            for name in ("clock", "five"):
                S2 = walks[("W", k, name)]["S"][last_complete]
                if np.isfinite(S2[0]):
                    ax[0].plot(HGRID, S2, ls="--", lw=0.8, label=f"{name} k={int(k)}")
        ax[0].set_title(f"Survival of today's level ({today['lastCompleteSunday']}): P(no k-pt fall by h)")
        ax[0].set_xlabel("weeks ahead")
        ax[0].legend(fontsize=7)
        ax[0].set_ylim(0, 1)
        xs = np.array([r["size"] for r in rows])
        ys = np.array([r["dur"] for r in rows])
        ax[1].scatter(xs, ys, s=5, alpha=0.4, label=f"daily k=1 events (n {len(rows)})")
        for t_ in dur["tests"]:
            ax[1].scatter([t_["size"]], [t_["days"]], c=("red" if t_.get("big") else "orange"), s=30)
        if law_all:
            gx = np.linspace(1, 35, 50)
            vmed = np.nanmedian([r["vol0"] for r in rows])
            ax[1].plot(gx, np.exp(law_all["beta"][0] + law_all["beta"][1] * np.log(gx) + law_all["beta"][2] * np.log(vmed)), "k-", label=f"law slope {law_all['beta'][1]:.2f}")
        ax[1].set_xscale("log")
        ax[1].set_yscale("log")
        ax[1].set_xlabel("size (points)")
        ax[1].set_ylabel("days peak to trough")
        ax[1].set_title("Duration law (red = big three, orange = other 5+ falls)")
        ax[1].legend(fontsize=7)
        fig.tight_layout()
        fig.savefig(os.path.join(a.out, "hazard_today.png"), dpi=110)
        plt.close(fig)
    except Exception as ex:  # charts are optional
        res["notes"].append(f"chart skipped: {ex}")
        C.write_results(a.out, res)
    say(f"-- wrote {os.path.join(a.out, 'results.json')} in {res['runtimeSec']}s ({len(lines) + 1} summary lines)")
    assert len(lines) <= 60, f"summary has {len(lines)} lines (> 60)"


if __name__ == "__main__":
    main()
