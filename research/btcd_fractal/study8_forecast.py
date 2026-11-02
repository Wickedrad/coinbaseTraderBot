#!/usr/bin/env python3
"""Round 8 trial [6] forecast: the single forecast object that follows from the other modules, the pre-registered
stack scored through the shared harness, and the fractal verdict across its three legs.

This module FITS NOTHING. It reads out8/{honest,multiscale,regime,hazard,tda_sig,baselines}/results.json (degrading
gracefully: a missing file or key is listed in notes and contributes nothing), aligns the thinned OOS series the
walk-forward modules wrote, builds the forecast object for the last complete Sunday close, scores the stack with
study8_common (targets rebuilt from the data for the scoring rows only) and prints a summary of at most 60 lines.

  python3 research/btcd_fractal/study8_forecast.py --data research/btcd_fractal/data --out research/btcd_fractal/out8/forecast [--in research/btcd_fractal/out8] [--nulls N] [--fast]

Pre-registered stack (plan section [6]): equal-weight mean in logit space of {stratified rate (honest), 1 - S(26) of the
full Weibull (hazard), TVTP V2 P(fall5_26w) incl. occupancy (regime), fixed5 (five-signal logistic)}; no learned weights;
the spread (min-max across the components) is the headline, not the centre. The regime module writes no fall10 series, so
the 10-point stack degrades to the three remaining components (stated in notes and in the object).

Two disclosures the reader must have. (1) The plan names the regime component twice and differently: section [6] says
"TVTP V2 P(fall5_26w) incl. occupancy" (the Monte-Carlo series V2_pFall5_26w) while Layer 5 says "TVTP hazard incl.
occupancy" (the entry hazard series V2_hazard26). This module follows its own section's sentence for the headline and
scores the other reading side by side (stack_regimeHazard26_altReading); the reader should know that the headline reading
is the better-scoring one of the two and that both fail the success criteria. (2) fixed5 is the honest module's post-hoc
comparator (round 7's most-picked set over refits through 2026, btcd_fromhi52w swapped for btcusd_ret13w), not a
pre-registered one; the brief's literal set (fixed5brief) is a paired tie with it in honest and no module exports its series,
so the stack cannot be re-scored with it here (its today reading is shown).

SMOKE gate: if any consumed module reports fast=True, nulls below its own minimum, or a *_fast folder, every STACK / SUCCESS
/ VERDICT line is prefixed "SMOKE ONLY", success.provisional is true with the per-input flags, and the numbers are to be
re-read after the full module runs exist under the plan's folder names (the regime module's own notes say its --fast output
must not enter the forecast stack).

Alignment (leakage check 2 of the plan): the modules thinned their weekly series every 2 weeks on two different phases
(honest / hazard / tda / fixed5 on 2019-04-07 + 2k weeks; regime / multiscale on 2019-01-06 + 2k weeks). A component's
value for Sunday d is its own value at d when it wrote one, otherwise its value at d - 7 days (a reading made BEFORE d,
at most one week stale); nothing is ever taken from a later date, and a component with neither contributes nothing to that
week. The headline scoring uses only weeks where every stack component is present; the no-carry stack (varying
composition) is scored beside it as a check. Timestamps come from the data's last bar, never from the wall clock.
"""
import argparse
import datetime as dt
import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import study8_common as C  # noqa: E402

# ----------------------------------------------------------------------------------------------- pre-registered constants
STACK5 = ["strat", "hazard", "regime", "fixed5"]       # P(5+ in 26w) components, fixed before any OOS number was read here
STACK10 = ["strat", "hazard", "regime", "fixed5"]      # same for P(10+ in 26w); components without a series drop out (noted)
CARRY_DAYS = 7                                         # a component value may be carried forward by at most one week (from the past)
RUNUP_WEEKS = 26                                       # run-up attached to each label episode in the episode bootstrap
BLOCK_WEEKS = 26                                       # block length of the block bootstrap and the paired block bootstrap
TRAIN_BASE_FROM = "2016-06-01"                         # the harness panel cut: reproduces honest's basetrain series exactly (checked in notes), so the training-base Brier is the comparators' reference
TRAIN_BASE_LAG_WEEKS = 26
MODULE_DIRS = {"honest": ["honest"], "multiscale": ["multiscale"], "regime": ["regime", "regime_fast"],
               "hazard": ["hazard"], "tda_sig": ["tda_sig", "tda_sig_fast"], "baselines": ["baselines"]}
STATE_K5 = {0: "BASE", 1: "FALL", 2: "RECOVERY"}
REGIME_READING = "V2_pFall5_26w"      # headline regime component: plan [6] "TVTP V2 P(fall5_26w) incl. occupancy" (Monte-Carlo P(fall))
REGIME_READING_ALT = "V2_hazard26"    # the other reading the plan names (Layer 5 "TVTP hazard incl. occupancy"): scored side by side, never headline
MIN_NULLS = 50                        # an input whose shifted-null draw count is below this is smoke-sized (multiscale's own minimum)
STACK_INPUTS = ["honest", "hazard", "regime"]   # modules whose series enter the stack: any one of them smoke-sized makes the verdict provisional
# 'all specifications' spread: a declared list of DISTINCT, NON-LEARNED point-target readings; everything else is listed as excluded with its reason
ALL_SPECS_DECLARED = [("component:fixed5", None), ("component:hazard", None), ("component:regime", None), ("component:strat", None),
                      ("honest:m2only", "honest/today/comparators/m2only:fall5_26w"), ("honest:m2eth", "honest/today/comparators/m2eth:fall5_26w"),
                      ("honest:clock", "honest/today/comparators/clock:fall5_26w"), ("honest:offset", "honest/today/comparators/offset:fall5_26w"),
                      ("hazard:cov_renewal", "hazard/today/nestedP26_k5/cov_renewal"), ("hazard:five(hazard)", "hazard/today/nestedP26_k5/five"),
                      ("hazard:full_recalibrated", "hazard/today/recalibratedP26/full"), ("multiscale:logitsum_p91", "multiscale/today/p_fall5_26w_exported"),
                      ("tda:M4", "tda_sig/today/readings/M4:fall5_26w/value"), ("honest:trainBase", "honest/today/trainBase"), ("honest:freshBase2019on", "honest/today/freshBase2019on")]
ALL_SPECS_EXCLUDED = {"honest:stack(learned)": ("honest/today/comparators/stack:fall5_26w", "learned 2-coefficient stack, 19 parameters against 12 episodes, fixed5 input in-sample at fit time"),
                      "honest:km26": ("honest/today/comparators/km26:fall5_26w", "the same stratified conditional rate in survival form (honest notes), not an independent estimate"),
                      "multiscale:p_sigma2_91": ("multiscale/today/p_sigma2_91", "a sigma-unit target, not the 5-point target"),
                      "honest:strat_vol": ("honest/today/comparators/strat_vol:fall5_26w", "a variant of the stratified cell, out of M2 support like it")}

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
    if isinstance(x, bool):
        return "Y" if x else "n"
    if isinstance(x, (int, np.integer)):
        return str(int(x))
    if isinstance(x, float) and not np.isfinite(x):
        return "na"
    if isinstance(x, (float, np.floating)):
        return f"{float(x):.{d}f}"
    return str(x)


def rnd(x, d=4):
    if x is None:
        return None
    if isinstance(x, (float, np.floating)):
        return None if not np.isfinite(x) else round(float(x), d)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    if isinstance(x, dict):
        return {k: rnd(v, d) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [rnd(v, d) for v in x]
    return x


# ----------------------------------------------------------------------------------------------- inputs
class Inputs:
    """Holds the modules' results.json dicts; every read goes through get() so a missing key is recorded, not fatal."""

    def __init__(self, root, notes):
        self.d, self.path, self.missing, self.notes = {}, {}, [], notes
        for name, cands in MODULE_DIRS.items():
            for c in cands:
                f = os.path.join(root, c, "results.json")
                if os.path.exists(f):
                    try:
                        with open(f) as fh:
                            self.d[name] = json.load(fh)
                        self.path[name] = f
                    except Exception as e:  # noqa: BLE001
                        notes.append(f"{name}: {f} could not be parsed ({e}); treated as missing")
                    break
            if name not in self.d:
                notes.append(f"missing input: {name} (looked for {[os.path.join(root, c, 'results.json') for c in cands]})")

    def has(self, name):
        return name in self.d

    def get(self, name, path, default=None, quiet=False):
        o = self.d.get(name)
        if o is None:
            return default
        for k in path.split("/"):
            if isinstance(o, dict) and k in o:
                o = o[k]
            else:
                if not quiet:
                    self.missing.append(f"{name}:{path}")
                return default
        return o

    def series(self, name, key, as_of=None):
        """A module's thinned series -> pd.Series on Sunday dates; rows after as_of (provisional) are dropped."""
        s = self.get(name, f"series/{key}")
        if not s:
            return None
        try:
            idx = pd.DatetimeIndex([pd.Timestamp(x["t"]) for x in s])
            v = np.array([float(x["v"]) if x["v"] is not None else np.nan for x in s])
        except Exception as e:  # noqa: BLE001
            self.notes.append(f"{name}:series/{key} unreadable ({e})")
            return None
        out = pd.Series(v, index=idx).sort_index()
        out = out[~out.index.duplicated()]
        if as_of is not None:
            out = out[out.index <= as_of]
        return out


# ----------------------------------------------------------------------------------------------- alignment and the stack
def align(components, grid, carry_days=CARRY_DAYS):
    """components: {name: pd.Series}. Returns (values DataFrame on grid, exact-flag DataFrame).
    value at d = own value at d, else own value at d - carry_days (a past reading), else NaN. Never from a later date."""
    vals, exact = pd.DataFrame(index=grid), pd.DataFrame(index=grid)
    for k, s in components.items():
        if s is None:
            vals[k], exact[k] = np.nan, False
            continue
        own = s.reindex(grid)
        prev = s.reindex(grid - pd.Timedelta(days=carry_days))
        prev.index = grid
        v = own.where(own.notna(), prev)
        vals[k] = v.values
        exact[k] = own.notna().values
    return vals, exact


def logit_mean(df, cols):
    """Equal-weight logit mean over the named columns; NaN where any column is missing."""
    X = df[cols].values.astype(float)
    L = C.logit(np.clip(X, 1e-4, 1 - 1e-4) * 100.0)
    m = np.isfinite(L).all(1)
    out = np.full(len(df), np.nan)
    out[m] = 1 / (1 + np.exp(-L[m].mean(1)))
    return pd.Series(out, index=df.index)


def logit_mean_available(df, cols):
    """The no-carry variant's rule: the mean over whichever components are present that week (composition varies)."""
    X = df[cols].values.astype(float)
    L = C.logit(np.clip(X, 1e-4, 1 - 1e-4) * 100.0)
    cnt = np.isfinite(L).sum(1)
    out = np.full(len(df), np.nan)
    ok = cnt > 0
    out[ok] = 1 / (1 + np.exp(-np.nanmean(np.where(np.isfinite(L), L, np.nan)[ok], 1)))
    return pd.Series(out, index=df.index), pd.Series(cnt, index=df.index)


# ----------------------------------------------------------------------------------------------- scoring helpers
def train_base_series(Y, target, grid, start=TRAIN_BASE_FROM, first="2019-01-06", refit_weeks=13, lag_weeks=TRAIN_BASE_LAG_WEEKS):
    """Training-window base rate at each refit (labels known at the refit, i.e. rows < refit - lag), stepped forward."""
    y = Y[target]
    idx = Y.index
    out = pd.Series(np.nan, index=grid)
    t = pd.Timestamp(first)
    rates = []
    while t <= grid[-1]:
        m = (idx >= pd.Timestamp(start)) & (idx < t - pd.Timedelta(weeks=lag_weeks)) & y.notna()
        rates.append((t, float(y[m].mean()) if m.sum() else np.nan))
        t = t + pd.Timedelta(weeks=refit_weeks)
    for (t0, r), (t1, _) in zip(rates, rates[1:] + [(grid[-1] + pd.Timedelta(days=1), None)]):
        out[(grid >= t0) & (grid < t1)] = r
    return out


def era_rows(idx, era):
    name, fr, to = era
    return (idx >= pd.Timestamp(fr)) & (idx < pd.Timestamp(to))


def score(pred, y, fresh, tb, label):
    """Per era and pooled: AUC, Brier vs the era's own base and vs the training base, fresh-start and onset AUC."""
    met = C.metrics(pred, y, True, is_prob=True)
    out = {"byEra": {}}
    for name, fr, to in list(C.ERAS) + [("pooled", "2000-01-01", "2100-01-01")]:
        m = era_rows(pred.index, (name, fr, to)) & pred.notna().values & y.notna().values
        row = dict(met.get(name, {}))
        if m.sum() >= 20:
            yy, pp = y.values[m], pred.values[m]
            tbv = tb.values[m] if tb is not None else None
            if tbv is not None and np.isfinite(tbv).all():
                row["brierTrainBase"] = round(float(np.mean((tbv - yy) ** 2)), 4)
                row["skillVsTrainBase"] = round(1 - row["brier"] / row["brierTrainBase"], 3) if row["brierTrainBase"] > 0 else None
                row["beatsTrainBase"] = bool(row["brier"] <= row["brierTrainBase"])
            row["skillVsOwnEra"] = round(1 - row["brier"] / row["brierBase"], 3) if row.get("brierBase") else None
            row["beatsOwnEra"] = bool(row["brier"] <= row["brierBase"]) if row.get("brierBase") is not None else None
            fm = m & (fresh.values > 0)
            row["freshAuc"] = (None if fm.sum() < 20 or C.auc(pred.values[fm], y.values[fm]) is None else round(C.auc(pred.values[fm], y.values[fm]), 3))
            row["freshN"] = int(fm.sum())
            on = (y.values * fresh.values)
            a = C.auc(pp, on[m]) if np.isfinite(on[m]).all() else None
            row["onsetAuc"] = None if a is None else round(a, 3)
            eps = C.episodes(np.where(m, y.values, np.nan))
            row["episodes"] = int(len(eps))
        if row:
            out["byEra"][name] = row
    aucs = [(out["byEra"][e[0]].get("auc"), out["byEra"][e[0]].get("n"), out["byEra"][e[0]].get("base")) for e in C.ERAS if e[0] in out["byEra"]]
    valid = [(a, n, b) for a, n, b in aucs if a is not None and n and b is not None]
    out["meanOfEraAuc"] = round(float(np.mean([a for a, _, _ in valid])), 3) if valid else None
    w = [(n * b) * (n * (1 - b)) for _, n, b in valid]
    out["eraStratAuc"] = round(float(sum(a * ww for (a, _, _), ww in zip(valid, w)) / sum(w)), 3) if valid and sum(w) > 0 else None
    out["label"] = label
    return out


def honest_episode_blocks(idx, episodes, runup_weeks=RUNUP_WEEKS):
    """Blocks on idx from an episode list [(start, end)] computed elsewhere after all predictions were frozen."""
    N = len(idx)
    cuts = {0, N}
    for s, e in episodes:
        sp = int(np.searchsorted(idx, pd.Timestamp(s)))
        ep = int(np.searchsorted(idx, pd.Timestamp(e), side="right"))
        cuts.add(max(0, sp - runup_weeks))
        cuts.add(min(N, ep))
    cuts = sorted(cuts)
    return [np.arange(a, b) for a, b in zip(cuts[:-1], cuts[1:]) if b > a]


def boot_blocks(blocks, fn, n, rng):
    vals = []
    for _ in range(n):
        pick = rng.integers(0, len(blocks), size=len(blocks))
        ii = np.concatenate([blocks[k] for k in pick])
        v = fn(ii)
        if v is not None and np.isfinite(v):
            vals.append(float(v))
    v = np.array(vals)
    return ({"n": len(v), "q05": round(float(np.quantile(v, 0.05)), 3), "q50": round(float(np.quantile(v, 0.5)), 3), "q95": round(float(np.quantile(v, 0.95)), 3)} if len(v) else {"n": 0})


def paired_block_boot(a, b, y, n, rng, block=BLOCK_WEEKS):
    """Circular block bootstrap of AUC(a) - AUC(b) on the common rows."""
    a, b, y = np.asarray(a, float), np.asarray(b, float), np.asarray(y, float)
    m = np.isfinite(a) & np.isfinite(b) & np.isfinite(y)
    a, b, y = a[m], b[m], y[m]
    N = len(a)
    if N < 40:
        return {"n": 0, "rows": int(N)}
    real = C.auc(a, y) - C.auc(b, y)
    vals = []
    for _ in range(n):
        starts = rng.integers(0, N, size=int(np.ceil(N / block)))
        ii = np.concatenate([(np.arange(s, s + block) % N) for s in starts])[:N]
        ua, ub = C.auc(a[ii], y[ii]), C.auc(b[ii], y[ii])
        if ua is not None and ub is not None:
            vals.append(ua - ub)
    v = np.array(vals)
    return {"n": len(v), "rows": int(N), "real": round(float(real), 4), "q05": round(float(np.quantile(v, 0.05)), 4), "q50": round(float(np.quantile(v, 0.5)), 4),
            "q95": round(float(np.quantile(v, 0.95)), 4), "pDiffLE0": round(float((v <= 0).mean()), 3), "tie": bool(abs(real) < 0.05)}


def calibration_deciles(pred, y, idx, episodes):
    p, yy = np.asarray(pred, float), np.asarray(y, float)
    m = np.isfinite(p) & np.isfinite(yy)
    if m.sum() < 40:
        return []
    qs = np.quantile(p[m], np.linspace(0, 1, 11))
    rows = []
    for i in range(10):
        lo, hi = qs[i], qs[i + 1]
        sel = m & (p >= lo) & ((p < hi) if i < 9 else (p <= hi))
        if sel.sum() == 0:
            continue
        dates = idx[sel]
        n_ep = sum(1 for s, e in episodes if ((dates >= pd.Timestamp(s)) & (dates <= pd.Timestamp(e))).any())
        rows.append({"decile": i + 1, "lo": round(float(lo), 4), "hi": round(float(hi), 4), "n": int(sel.sum()), "meanPred": round(float(p[sel].mean()), 4),
                     "realised": round(float(yy[sel].mean()), 4), "episodesTouched": int(n_ep)})
    return rows


def decile_of(value, deciles):
    for r in deciles:
        if r["lo"] <= value <= r["hi"]:
            return r
    if deciles and value < deciles[0]["lo"]:
        return deciles[0]
    return deciles[-1] if deciles else None


# ----------------------------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--in", dest="inp", default=None, help="out8 root holding the modules' folders (default: parent of --out)")
    ap.add_argument("--nulls", type=int, default=200, help="scoring-only shifted-target draws for the stack (it has no fit)")
    ap.add_argument("--boot", type=int, default=1000)
    ap.add_argument("--fast", action="store_true", help="identical pipeline (already under a minute); kept for the contract")
    a = ap.parse_args()
    root = a.inp or os.path.dirname(os.path.abspath(a.out.rstrip("/")))
    rng = np.random.default_rng(86)
    notes, missing_keys = [], []
    t_start = pd.Timestamp.now()

    # ---- data: only to rebuild the scoring labels and the fresh-start mask on the aligned rows; nothing is fitted
    D = C.load_daily(a.data)
    P = C.panel(D, "W")
    P = P[P.index >= pd.Timestamp("2016-06-01")]
    Y = C.targets(P, "W")
    fresh_all = C.fresh_mask(P, "W").astype(float)
    data_last = D.index[-1]
    last_bar_utc = dt.datetime(data_last.year, data_last.month, data_last.day, tzinfo=dt.timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        last_bar_et = last_bar_utc.astimezone(ZoneInfo("America/New_York"))
        et_label = last_bar_et.strftime("%Y-%m-%d %H:%M %Z")
    except Exception:  # noqa: BLE001
        et_label = (last_bar_utc - dt.timedelta(hours=5)).strftime("%Y-%m-%d %H:%M EST(fixed offset)")
    utc_label = last_bar_utc.strftime("%Y-%m-%d %H:%M UTC")
    # the W-SUN panel labels each week by its Sunday; a Sunday after the last daily bar is the partial current week
    as_of = P.index[P.index <= data_last][-1]
    provisional = [str(t.date()) for t in P.index if t > data_last]

    inp = Inputs(root, notes)
    say(f"study8_forecast  data through {utc_label} = {et_label}; last complete Sunday {as_of.date()}; provisional {provisional}; "
        f"fast={a.fast}; inputs found {sorted(inp.d.keys())}; fits nothing")
    # SMOKE gate: an input is smoke-sized if it says fast=True, if its own null count is below MIN_NULLS or its own gate says
    # the verdict was not printed, or if it was read from a *_fast folder instead of the plan's folder name
    smoke = {}
    for name in inp.d:
        src = inp.get(name, "runUtc", None, quiet=True) or inp.get(name, "runtime/finishedUTC", None, quiet=True)
        fast = inp.get(name, "fast", None, quiet=True)
        folder = os.path.basename(os.path.dirname(inp.path[name]))
        nulls = inp.get(name, "config/nulls", None, quiet=True)
        if nulls is None:
            nulls = inp.get(name, "config/n_shift", None, quiet=True)
        if nulls is None and name == "baselines":
            nulls = inp.get(name, "W/fixed/fixed5:fall5_26w/null/n", None, quiet=True)
        if nulls is None and name == "honest":
            nulls = inp.get(name, "null/shifted/fixed5:fall5_26w/n", None, quiet=True)
        if nulls is None and name == "hazard":
            nulls = inp.get(name, "null/W:k5:full/auc26/n", None, quiet=True)
        gated = inp.get(name, "criteria/verdictGated/printed", None, quiet=True)
        own_note = any("required before any number enters the forecast stack" in str(n) for n in (inp.get(name, "notes", [], quiet=True) or []))
        reasons = [r for r, ok in (("fast=True", bool(fast)), (f"nulls {nulls} < {MIN_NULLS}", nulls is not None and nulls < MIN_NULLS),
                                   ("module's own verdict gate not printed", gated is False), (f"read from folder '{folder}' not the plan's", folder != name),
                                   ("module's notes say its --fast output must not enter the stack", own_note)) if ok]
        smoke[name] = {"smoke": bool(reasons), "fast": fast, "nulls": nulls, "folder": folder, "reasons": reasons}
        notes.append(f"input {name}: {inp.path[name]} (module run {src}; fast={fast}; nulls {nulls}; smoke-sized: {bool(reasons)} {reasons})")
    provisional_run = any(smoke.get(n, {}).get("smoke") for n in STACK_INPUTS if n in smoke) or any(n not in smoke for n in STACK_INPUTS)
    TAG = "SMOKE ONLY " if provisional_run else ""
    if provisional_run:
        notes.append("SMOKE ONLY: at least one stack input is a smoke-sized run (" + "; ".join(f"{n}: {smoke[n]['reasons']}" for n in STACK_INPUTS if n in smoke and smoke[n]["smoke"]) +
                     "). Every STACK / SUCCESS / VERDICT number below is provisional and must be re-read after the full module runs exist under the plan's folder names.")
    say(f"{TAG}inputs smoke-sized: " + ", ".join(f"{n} {'Y' if v['smoke'] else 'n'} (fast={v['fast']}, nulls {v['nulls']}, folder {v['folder']})" for n, v in smoke.items())
        + ("; VERDICT PROVISIONAL until the full runs exist" if provisional_run else ""))
    mod_as_of = {n: inp.get(n, p, None, quiet=True) for n, p in (("honest", "today/asOf"), ("regime", "today/date"), ("hazard", "today/lastCompleteSunday"), ("multiscale", "today/weeklyRowUsed"), ("tda_sig", "today/asOf"))}
    for n, v in mod_as_of.items():
        if v is not None and str(v) != str(as_of.date()):
            notes.append(f"{n} today block is dated {v}, this run's last complete Sunday is {as_of.date()}: the object mixes dates")

    # ---- component series (thinned, OOS, walk-forward; provisional rows dropped)
    comp5 = {"strat": inp.series("honest", "strat_fall5_26w", as_of), "hazard": inp.series("hazard", "p_fall5_26w", as_of),
             "regime": inp.series("regime", REGIME_READING, as_of), "fixed5": inp.series("honest", "fixed5_fall5_26w", as_of)}
    regime_alt = inp.series("regime", REGIME_READING_ALT, as_of)   # the plan's other wording of the regime component (Layer 5): scored beside, never headline
    notes.append(f"Regime component: the plan names it twice ([6] 'TVTP V2 P(fall5_26w) incl. occupancy' = series {REGIME_READING}; Layer 5 'TVTP hazard incl. occupancy' = series {REGIME_READING_ALT}). "
                 f"The headline follows section [6]; the Layer-5 reading is scored side by side as stack_regimeHazard26_altReading. The reader should know the [6] reading is the better-scoring of the two.")
    comp10 = {"strat": inp.series("honest", "strat_fall10_26w", as_of), "hazard": inp.series("hazard", "p_fall10_26w", as_of),
              "regime": inp.series("regime", "V2_pFall10_26w", as_of), "fixed5": inp.series("honest", "fixed5_fall10_26w", as_of)}
    for comp, tg in ((comp5, "fall5_26w"), (comp10, "fall10_26w")):
        if comp["fixed5"] is None:   # fallback: the same walk-forward series as written by the baselines module
            s = inp.get("baselines", f"W/fixed/fixed5:{tg}/series")
            if s:
                comp["fixed5"] = pd.Series([float(x["v"]) for x in s], index=pd.DatetimeIndex([pd.Timestamp(x["t"]) for x in s]))
                comp["fixed5"] = comp["fixed5"][comp["fixed5"].index <= as_of]
                notes.append(f"fixed5 {tg} series taken from baselines (honest series missing)")
    extra = {"p_active_regime": inp.series("regime", "V2_pActive", as_of), "hazard26_regime": inp.series("regime", "V2_hazard26", as_of),
             "state_k5_hazard": inp.series("hazard", "state_k5", as_of), "stratum_code": inp.series("honest", "stratum_code", as_of),
             "multiscale_p_fall5_26w": inp.series("multiscale", "p_fall5_26w", as_of), "multiscale_p_active": inp.series("multiscale", "p_active", as_of),
             "tda_M4_fall5_26w": inp.series("tda_sig", "M4:fall5_26w", as_of), "basetrain_honest": inp.series("honest", "basetrain_fall5_26w", as_of)}
    inp.missing = [m for m in inp.missing if not m.endswith("series/V2_pFall10_26w")]
    if comp10["regime"] is None:
        notes.append("regime wrote no P(fall10_26w) series: the 10-point stack uses {strat, hazard, fixed5} over the OOS rows; the regime module's own 10-point reading today is shown in the spread only")
    avail5 = [k for k in STACK5 if comp5[k] is not None]
    avail10 = [k for k in STACK10 if comp10[k] is not None]
    for k in STACK5:
        if comp5[k] is None:
            notes.append(f"stack component {k} (fall5) missing: it contributes nothing")

    # today's exact readings are placed at as_of (the thinned series may have skipped that Sunday)
    today_comp5 = {"strat": inp.get("honest", "today/stratum/rate"), "hazard": inp.get("hazard", "today/k5_lastCompleteSunday/P26"),
                   "regime": inp.get("regime", "today/pFall5_26w"), "fixed5": inp.get("honest", "today/comparators/fixed5:fall5_26w")}
    today_comp10 = {"strat": inp.get("honest", "today/stratum/rate10"), "hazard": inp.get("hazard", "today/k10_lastCompleteSunday/P26"),
                    "regime": inp.get("regime", "today/pFall10_26w"), "fixed5": inp.get("honest", "today/comparators/fixed5:fall10_26w")}
    for comp, tod in ((comp5, today_comp5), (comp10, today_comp10)):
        for k, v in tod.items():
            if comp.get(k) is not None and v is not None and mod_as_of.get({"strat": "honest", "hazard": "hazard", "regime": "regime", "fixed5": "honest"}[k]) == str(as_of.date()):
                comp[k] = comp[k].copy()
                comp[k][as_of] = float(v)
                comp[k] = comp[k].sort_index()
    today_regime_alt = inp.get("regime", "today/hazard/h26/incl", None, quiet=True)
    if regime_alt is not None and today_regime_alt is not None and mod_as_of.get("regime") == str(as_of.date()):
        regime_alt = regime_alt.copy()
        regime_alt[as_of] = float(today_regime_alt)
        regime_alt = regime_alt.sort_index()

    # ---- alignment on the union of Sunday dates
    first = min([s.index[0] for s in list(comp5.values()) + list(comp10.values()) if s is not None])
    grid = P.index[(P.index >= first) & (P.index <= as_of)]
    V5, E5 = align(comp5, grid)
    V10, E10 = align(comp10, grid)
    VX, EX = align(extra, grid)
    stack5 = logit_mean(V5, avail5)
    stack10 = logit_mean(V10, avail10)
    V5alt, _ = align({**comp5, "regime": regime_alt}, grid)
    stack5_alt = logit_mean(V5alt, avail5) if (regime_alt is not None and "regime" in avail5) else None
    stack5_nocarry, ncomp5_nocarry = logit_mean_available(pd.DataFrame({k: comp5[k].reindex(grid) for k in avail5}, index=grid), avail5)
    full5 = V5[avail5].notna().all(axis=1)
    exact_share = {k: round(float(E5[k][full5].mean()), 3) for k in avail5}
    carried_share = {k: round(float((V5[k].notna() & ~E5[k])[full5].mean()), 3) for k in avail5}
    say(f"alignment: union grid {grid[0].date()}..{grid[-1].date()} {len(grid)} Sundays; fall5 stack {avail5} complete on {int(full5.sum())} rows "
        f"(first {grid[full5][0].date() if full5.any() else 'none'}); exact share {exact_share}; carried<=7d-from-the-past share {carried_share}; fall10 stack {avail10}")
    notes.append(f"Alignment: component values at Sunday d are the module's own value at d, else its value at d-7 (never later); exact shares {exact_share}; "
                 f"the stack's headline rows are the {int(full5.sum())} Sundays with every component present; the modules' full weekly series exist only inside the modules.")

    # ---- labels on the grid (built from the data; the only use of the data here)
    y5 = Y["fall5_26w"].reindex(grid)
    y10 = Y["fall10_26w"].reindex(grid)
    fresh = fresh_all.reindex(grid)
    tb5 = train_base_series(Y, "fall5_26w", grid)
    tb10 = train_base_series(Y, "fall10_26w", grid)
    if VX["basetrain_honest"].notna().any():
        dd = (VX["basetrain_honest"] - tb5).abs()[EX["basetrain_honest"].values]   # compare on the dates honest wrote, not on carried weeks
        notes.append(f"training-base rate recomputed from {TRAIN_BASE_FROM} with a {TRAIN_BASE_LAG_WEEKS}-week label lag at 13-week refits; max abs diff vs honest's basetrain series on its own dates {float(dd.max()):.4f}")

    # honest's episode list (computed by the honest module after its predictions were frozen) drives the episode bootstrap
    ep_src = inp.get("honest", "evidence_ceiling/episodeLOO/fixed5:fall5_26w/perEpisode", {}) or {}
    episodes5 = [tuple(k.split("..")) for k in ep_src.keys()] if ep_src else []
    ep10_src = inp.get("honest", "evidence_ceiling/episodeLOO/fixed5:fall10_26w/perEpisode", {}) or {}
    episodes10 = [tuple(k.split("..")) for k in ep10_src.keys()] if ep10_src else []
    own_eps5 = [(str(grid[s].date()), str(grid[e].date())) for s, e in C.episodes(np.where(full5.values, y5.values, np.nan))]
    if not episodes5:
        episodes5 = own_eps5
        notes.append("honest episode list missing: episodes recomputed from the labels on the aligned rows")
    else:
        notes.append(f"episode bootstrap uses the honest module's {len(episodes5)} fall5 episodes (frozen after its predictions); the labels on the aligned rows give {len(own_eps5)} episodes")

    # ---- scoring
    oos = {"fall5_26w": {}, "fall10_26w": {}}
    pred5 = {"stack": stack5.where(full5), **{k: V5[k].where(full5) for k in avail5}}
    pred10 = {"stack": stack10.where(V10[avail10].notna().all(axis=1)), **{k: V10[k].where(V10[avail10].notna().all(axis=1)) for k in avail10}}
    for name, pr in pred5.items():
        oos["fall5_26w"][name] = score(pr, y5, fresh, tb5, name)
    for name, pr in pred10.items():
        oos["fall10_26w"][name] = score(pr, y10, fresh, tb10, name)
    oos["fall5_26w"]["stack_nocarry_varyingComposition"] = score(stack5_nocarry, y5, fresh, tb5, "no-carry stack (composition varies by week)")
    oos["fall5_26w"]["stack_nocarry_varyingComposition"]["meanComponents"] = round(float(ncomp5_nocarry[stack5_nocarry.notna()].mean()), 2)
    posthoc = [k for k in avail5 if k != "regime"]
    if len(posthoc) >= 2 and "regime" in avail5:
        oos["fall5_26w"]["POSTHOC_stack_without_regime"] = score(logit_mean(V5, posthoc).where(full5), y5, fresh, tb5, "POST-HOC diagnostic, not pre-registered")
    full5_alt = full5 & V5alt["regime"].notna() if stack5_alt is not None else None
    if stack5_alt is not None:
        oos["fall5_26w"]["stack_regimeHazard26_altReading"] = score(stack5_alt.where(full5_alt), y5, fresh, tb5, f"the plan's Layer-5 wording of the regime component ({REGIME_READING_ALT} in place of {REGIME_READING}); scored side by side, not headline")
        oos["fall5_26w"]["regime_altReading_component"] = score(V5alt["regime"].where(full5_alt), y5, fresh, tb5, f"{REGIME_READING_ALT} alone on the aligned rows")

    S5 = oos["fall5_26w"]["stack"]["byEra"]
    F5 = oos["fall5_26w"].get("fixed5", {}).get("byEra", {})
    eras = [e[0] for e in C.ERAS]

    # evidence-ceiling checks on the stack through the shared functions
    nb = a.boot
    ceiling = {}
    m5 = full5.values & y5.notna().values
    ceiling["episodeLOO_stack"] = C.episode_loo(pred5["stack"], y5)
    ceiling["blockBoot_stack"] = C.block_boot(pred5["stack"], y5, n=nb, block_weeks=BLOCK_WEEKS, rng=np.random.default_rng(1))
    ceiling["episodeBoot_stack_sharedFn"] = C.episode_boot(pred5["stack"], y5, n=nb, runup_weeks=RUNUP_WEEKS, rng=np.random.default_rng(2))
    blocks5 = honest_episode_blocks(grid, episodes5)
    pv, yv = pred5["stack"].values, y5.values

    def auc_on(ii):
        mm = m5[ii]
        return C.auc(pv[ii][mm], yv[ii][mm]) if mm.sum() > 20 else None
    ceiling["episodeBoot_stack_honestEpisodes"] = {**boot_blocks(blocks5, auc_on, nb, np.random.default_rng(3)), "nBlocks": len(blocks5)}
    if "fixed5" in avail5:
        ceiling["blockBoot_fixed5_sameRows"] = C.block_boot(pred5["fixed5"], y5, n=nb, block_weeks=BLOCK_WEEKS, rng=np.random.default_rng(1))
        ceiling["paired_stack_minus_fixed5"] = paired_block_boot(pred5["stack"].values, pred5["fixed5"].values, y5.values, nb, np.random.default_rng(4))
        for k in avail5:
            if k != "fixed5":
                ceiling[f"paired_{k}_minus_fixed5"] = paired_block_boot(pred5[k].values, pred5["fixed5"].values, y5.values, max(200, nb // 5), np.random.default_rng(5))
    f5_band_honest = inp.get("honest", "evidence_ceiling/blockBoot/fixed5:fall5_26w")
    f5_band = f5_band_honest or ceiling.get("blockBoot_fixed5_sameRows")
    ceiling["fixed5BandSource"] = "honest" if f5_band_honest else "recomputed on the aligned rows"
    ceiling["calibrationDeciles_stack"] = calibration_deciles(pv, yv, grid, episodes5)
    ceiling["calibrationDecilesNote"] = "a calibration DIAGNOSTIC of the stack on its own OOS rows; the honest module wrote no calibration deciles, so the plan's criterion 'interval contains the realised rate in the honest module's calibration deciles' is not computable as written"
    if "fixed5" in avail5:
        ceiling["calibrationDeciles_fixed5"] = calibration_deciles(pred5["fixed5"].values, yv, grid, episodes5)
        if stack5_alt is not None:
            ceiling["paired_stackAltReading_minus_fixed5"] = paired_block_boot(stack5_alt.where(full5_alt).values, pred5["fixed5"].values, y5.values, nb, np.random.default_rng(4))
    if stack5_alt is not None:
        ceiling["episodeLOO_stackAltReading"] = C.episode_loo(stack5_alt.where(full5_alt), y5)
    # honest's fixed5 disclosure carried into the stack's pre-registration note: fixed5 is a post-hoc comparator; fixed5brief (the brief's literal set) is a paired tie with it
    f5b_paired = inp.get("honest", "oos/pairedVsFixed5/fixed5brief:fall5_26w", None, quiet=True)
    if f5b_paired is None:
        f5b_paired = next((n for n in (inp.get("honest", "notes", [], quiet=True) or []) if str(n).startswith("fixed5brief vs fixed5")), None)
    ceiling["fixed5Disclosure"] = {"honestNote": next((n for n in (inp.get("honest", "notes", [], quiet=True) or []) if "post-hoc comparator" in str(n)), None),
                                   "fixed5briefPairedVsFixed5_honest": f5b_paired, "fixed5briefToday": inp.get("honest", "today/comparators/fixed5brief:fall5_26w", None, quiet=True),
                                   "stackWithFixed5brief": "not computable here: no module exports a fixed5brief weekly series (honest reports the paired tie above)"}

    # scoring-only shifted-target null of the stack (legitimate here: the stack has no fit, so nothing could follow the target)
    Yg = Y[["fall5_26w", "fall10_26w"]].copy()

    def run_null(Ys):
        yy = Ys["fall5_26w"].reindex(grid).values
        mm = np.isfinite(pv) & np.isfinite(yy)
        return C.auc(pv[mm], yy[mm]) if mm.sum() > 40 else None
    null_vals = C.shift_null(run_null, Yg, a.nulls, np.random.default_rng(6), freq="W")
    null = {"stack_fall5_26w_scoringOnlyShift": {**C.null_summary(S5.get("pooled", {}).get("auc"), null_vals), "note": "scoring-only circular shift of the labels by >= 26 weeks: valid for the stack because it has no fit; the components' own p-values are inherited below"}}
    null["inherited"] = {
        "honest.strat.fall5_26w.shifted": inp.get("honest", "null/shifted/strat:fall5_26w"), "honest.fixed5.fall5_26w.shifted": inp.get("honest", "null/shifted/fixed5:fall5_26w"),
        "honest.fixed5.withinEra": inp.get("honest", "null/withinEra/fixed5"), "honest.strat.withinEra": inp.get("honest", "null/withinEra/strat"),
        "hazard.full.auc26.shifted": inp.get("hazard", "null/W:k5:full/auc26"), "hazard.full.eras26": inp.get("hazard", "null/W:k5:full/eras26"),
        "regime.V2.fall5_26w.shifted": inp.get("regime", "null/V2:fall5_26w"), "regime.V2.withinEra": inp.get("regime", "null/V2:fall5_26w:withinEra"),
        "multiscale.E2.shifted": inp.get("multiscale", "null/shift/e2_fall5_26w"), "multiscale.E2.matchedRW": inp.get("multiscale", "null/placebo_rw/e2_fall5_26w"),
        "tda.M4.pooled": inp.get("tda_sig", "null/M4:fall5_26w/pooled"), "tda.M4.increment": inp.get("tda_sig", "null/M4:fall5_26w/increment")}

    # ---- summary lines: components, stack by era, checks
    def era_str(by, key="auc"):
        return "/".join(fmt(by.get(e, {}).get(key)) for e in eras + ["pooled"])
    for k in avail5:
        b = oos["fall5_26w"][k]["byEra"]
        say(f"component {k:7s} fall5_26w AUC {era_str(b)} Brier {era_str(b, 'brier')} beats train base {''.join(fmt(b.get(e, {}).get('beatsTrainBase')) for e in eras)} "
            f"own-era {''.join(fmt(b.get(e, {}).get('beatsOwnEra')) for e in eras)} fresh {era_str(b, 'freshAuc')}")
    say(f"{TAG}STACK fall5_26w (logit mean of {avail5}; regime = {REGIME_READING}, plan [6] wording) AUC {era_str(S5)} Brier {era_str(S5, 'brier')} vs own-era base {era_str(S5, 'brierBase')} vs train base {era_str(S5, 'brierTrainBase')}")
    if stack5_alt is not None:
        SA = oos["fall5_26w"]["stack_regimeHazard26_altReading"]["byEra"]
        RA = oos["fall5_26w"]["regime_altReading_component"]["byEra"]
        pa = ceiling.get("paired_stackAltReading_minus_fixed5", {})
        say(f"{TAG}  same stack with regime = {REGIME_READING_ALT} (plan Layer-5 wording, NOT headline): AUC {era_str(SA)} Brier {era_str(SA, 'brier')}; that component alone AUC {era_str(RA)}; "
            f"paired vs fixed5 {fmt(pa.get('real'))} [{fmt(pa.get('q05'))},{fmt(pa.get('q95'))}]; the headline reading scores better on every metric and both readings fail the criteria")
    say(f"  stack era-stratified AUC {fmt(oos['fall5_26w']['stack']['eraStratAuc'])} mean-of-era {fmt(oos['fall5_26w']['stack']['meanOfEraAuc'])}; fresh-start AUC {era_str(S5, 'freshAuc')} (n {era_str(S5, 'freshN')}); onset AUC {era_str(S5, 'onsetAuc')}; "
        f"episodes {era_str(S5, 'episodes')}")
    pf = ceiling.get("paired_stack_minus_fixed5", {})
    inside = (f5_band is not None and S5.get("pooled", {}).get("auc") is not None and f5_band.get("q05") <= S5["pooled"]["auc"] <= f5_band.get("q95"))
    say(f"  stack vs fixed5: paired AUC diff {fmt(pf.get('real'))} [{fmt(pf.get('q05'))},{fmt(pf.get('q95'))}] P(diff<=0) {fmt(pf.get('pDiffLE0'))} tie={fmt(pf.get('tie'))}; "
        f"fixed5 block-boot band ({ceiling['fixed5BandSource']}) [{fmt(f5_band.get('q05') if f5_band else None)},{fmt(f5_band.get('q95') if f5_band else None)}] contains stack: {fmt(inside)}")
    lo = ceiling["episodeLOO_stack"]
    bb, eb, eh = ceiling["blockBoot_stack"], ceiling["episodeBoot_stack_sharedFn"], ceiling["episodeBoot_stack_honestEpisodes"]
    say(f"  stack episode LOO min {fmt(lo.get('min'))} ({lo.get('minEpisode')}; {lo.get('nEpisodes')} episodes); block boot [{fmt(bb.get('q05'))},{fmt(bb.get('q95'))}]; "
        f"episode boot shared-fn [{fmt(eb.get('q05'))},{fmt(eb.get('q95'))}] honest-episodes [{fmt(eh.get('q05'))},{fmt(eh.get('q95'))}] ({eh.get('nBlocks')} blocks)")
    nn = null["stack_fall5_26w_scoringOnlyShift"]
    own_p = {"strat": (null["inherited"].get("honest.strat.fall5_26w.shifted") or {}), "hazard": (null["inherited"].get("hazard.full.auc26.shifted") or {}),
             "regime": (null["inherited"].get("regime.V2.fall5_26w.shifted") or {}), "fixed5": (null["inherited"].get("honest.fixed5.fall5_26w.shifted") or {})}
    clearing = [k for k, v in own_p.items() if v.get("p") is not None and v["p"] < 0.05]
    null["componentsClearingOwnShiftedNull"] = {"clearing": clearing, "p": {k: v.get("p") for k, v in own_p.items()}, "n": {k: v.get("n") for k, v in own_p.items()},
                                                "note": "the stack's scoring-only null clearance is inherited from the components that clear their own null; the others fail theirs (smoke-sized draws)"}
    own_str = ", ".join(f"{k} p {fmt(v.get('p'), 2)} n {v.get('n')}" for k, v in own_p.items())
    say(f"  stack scoring-only shifted null (n {nn.get('n')}): real {fmt(nn.get('real'))} null median {fmt(nn.get('nullMedian'))} p95 {fmt(nn.get('nullP95'))} p {fmt(nn.get('p'))}; "
        f"components clearing their OWN shifted null: {clearing or 'none'} ({own_str}; smoke-sized draws): the stack's clearance is inherited from {clearing or 'no component'}")
    for k in avail5:
        if k != "fixed5" and f"paired_{k}_minus_fixed5" in ceiling:
            pk = ceiling[f"paired_{k}_minus_fixed5"]
            say(f"  paired {k} - fixed5: {fmt(pk.get('real'))} [{fmt(pk.get('q05'))},{fmt(pk.get('q95'))}] P(diff<=0) {fmt(pk.get('pDiffLE0'))}")
    nc = oos["fall5_26w"]["stack_nocarry_varyingComposition"]["byEra"]
    say(f"  check: no-carry stack (composition varies, mean {oos['fall5_26w']['stack_nocarry_varyingComposition']['meanComponents']} components) AUC {era_str(nc)}"
        + (f"; POST-HOC stack without regime AUC {era_str(oos['fall5_26w']['POSTHOC_stack_without_regime']['byEra'])} Brier {era_str(oos['fall5_26w']['POSTHOC_stack_without_regime']['byEra'], 'brier')}" if "POSTHOC_stack_without_regime" in oos["fall5_26w"] else ""))
    S10 = oos["fall10_26w"].get("stack", {}).get("byEra", {})
    F10 = oos["fall10_26w"].get("fixed5", {}).get("byEra", {})
    say(f"{TAG}STACK fall10_26w ({avail10}) AUC {era_str(S10)} Brier {era_str(S10, 'brier')} vs own-era base {era_str(S10, 'brierBase')} vs train base {era_str(S10, 'brierTrainBase')}; fixed5 AUC {era_str(F10)}; "
        f"ONE positive episode ({episodes10[0] if episodes10 else 'Oct 2020 - May 2021'}), none since 2023: a ranking of one event")

    # leakage alarm and success criteria
    comp_names = [k for k in avail5]
    beats_all = all(all((S5.get(e, {}).get("auc") or 0) > (oos["fall5_26w"][k]["byEra"].get(e, {}).get("auc") or 0) for k in comp_names) for e in eras)
    brier_le_fixed5 = {e: (S5.get(e, {}).get("brier") is not None and F5.get(e, {}).get("brier") is not None and S5[e]["brier"] <= F5[e]["brier"]) for e in eras}
    brier_le_base = {e: bool(S5.get(e, {}).get("beatsOwnEra")) for e in eras}
    brier_le_train = {e: bool(S5.get(e, {}).get("beatsTrainBase")) for e in eras}
    success = {"provisional": bool(provisional_run), "provisionalReason": ("SMOKE ONLY: stack inputs are smoke-sized runs; re-read after the full module runs" if provisional_run else None),
               "perInputSmoke": smoke, "regimeReadingUsed": REGIME_READING, "regimeReadingAlt": REGIME_READING_ALT,
               "stackBrierLeFixed5EveryEra": all(brier_le_fixed5.values()), "stackBrierLeOwnEraBaseEveryEra": all(brier_le_base.values()),
               "stackBrierLeTrainBaseEveryEra": all(brier_le_train.values()), "stackPooledAucInsideFixed5Band": bool(inside), "byEra": {"vsFixed5": brier_le_fixed5, "vsOwnEraBase": brier_le_base, "vsTrainBase": brier_le_train},
               "intervalContainsRealisedRateInHonestCalibrationDeciles": "not identifiable as written: the honest module wrote no calibration deciles; the stack's own-decile table is kept as a diagnostic only",
               "leakageAlarm_stackBeatsEveryComponentEveryEra": bool(beats_all),
               "fixed5IsPostHocComparator": "yes (honest notes): fixed5 is round 7's most-picked set over refits through 2026; the 'pre-registered' claim covers the stack's composition and weights, not fixed5's own selection"}
    if stack5_alt is not None:
        SA_ = oos["fall5_26w"]["stack_regimeHazard26_altReading"]["byEra"]
        pa_ = ceiling.get("paired_stackAltReading_minus_fixed5", {})
        inside_alt = (f5_band is not None and SA_.get("pooled", {}).get("auc") is not None and f5_band.get("q05") <= SA_["pooled"]["auc"] <= f5_band.get("q95"))
        success["altReading_regimeHazard26"] = {"stackBrierLeFixed5EveryEra": all(SA_.get(e, {}).get("brier") is not None and F5.get(e, {}).get("brier") is not None and SA_[e]["brier"] <= F5[e]["brier"] for e in eras),
                                                "stackBrierLeOwnEraBaseEveryEra": all(bool(SA_.get(e, {}).get("beatsOwnEra")) for e in eras),
                                                "stackBrierLeTrainBaseEveryEra": all(bool(SA_.get(e, {}).get("beatsTrainBase")) for e in eras), "stackPooledAucInsideFixed5Band": bool(inside_alt),
                                                "pairedVsFixed5": pa_.get("real"), "byEraBrier": {e: SA_.get(e, {}).get("brier") for e in eras}}
    say(f"  leakage alarm (stack beats every component in every era): {fmt(beats_all)}" + ("  -> RE-CHECK LEAKAGE" if beats_all else "  (no alarm)"))

    # ---- TODAY: the forecast object
    hz = inp.get("hazard", "today/k5_lastCompleteSunday", {}) or {}
    hz10 = inp.get("hazard", "today/k10_lastCompleteSunday", {}) or {}
    st = inp.get("honest", "today/stratum", {}) or {}
    p_active = inp.get("regime", "today/pActive")
    state = {"regime_pActive": p_active, "regime_pEnterWeekly": inp.get("regime", "today/pEnterWeekly"), "regime_hazard26_inclOccupancy": inp.get("regime", "today/hazard/h26/incl"),
             "hazard_state_k5": inp.get("hazard", "today/stateWeeklyK5"), "hazard_weeksSinceConfirmedTroughK5": inp.get("hazard", "today/weeksSinceConfirmedTroughK5"),
             "hazard_btcdVol13wPercentile": inp.get("hazard", "today/btcdVol13wPercentile"),
             "stratum": {k: st.get(k) for k in ("code", "name", "n", "k", "nEp", "level", "rate", "rate10", "extrapolation")}, "stratumSupport": st.get("support"),
             "multiscale_pstate91": inp.get("multiscale", "today/pstate91"), "multiscale_lastFallVisitWasJun2025": inp.get("multiscale", "today/lastFallVisitWasJun2025"),
             "fresh": inp.get("honest", "today/fresh"), "readinessOn": inp.get("honest", "today/readinessOn"), "btcd": inp.get("honest", "today/btcd"), "btcd_exstable": inp.get("honest", "today/btcd_exstable"),
             "inputs": inp.get("honest", "today/inputs")}
    c5 = {k: v for k, v in today_comp5.items() if v is not None and k in avail5}
    c10 = {k: v for k, v in today_comp10.items() if v is not None and k in avail10}
    t5 = float(logit_mean(pd.DataFrame([c5]), list(c5.keys())).iloc[0]) if c5 else None
    t10 = float(logit_mean(pd.DataFrame([c10]), list(c10.keys())).iloc[0]) if c10 else None
    spread5 = [min(c5.values()), max(c5.values())] if c5 else None          # the plan's raw component min-max: always printed
    spread10 = [min(c10.values()), max(c10.values())] if c10 else None
    # each endpoint's own qualification: the module's extrapolation flag and the component's Brier skill in the current era (2023-26)
    cur_era = eras[-1]
    strat_extrap = bool(st.get("extrapolation"))
    comp_tags = {}
    for k in c5:
        row = oos["fall5_26w"].get(k, {}).get("byEra", {}).get(cur_era, {})
        comp_tags[k] = {"brierSkillVsOwnEra_2023_26": row.get("skillVsOwnEra"), "brierBeatsOwnEra_2023_26": row.get("beatsOwnEra"), "auc_2023_26": row.get("auc"),
                        "extrapolation": (strat_extrap if k == "strat" else False),
                        "moduleFlag": ({"strat": "out of its cell's M2 support (honest), enters only through its interval", "regime": "intercept-dominated h26 (regime notes); MC reads > 0.5 in most OOS weeks; ranks 2023-26 below chance"}.get(k)
                                       if (k == "strat" and strat_extrap) or (k == "regime" and (row.get("auc") or 1) < 0.5) else None)}
    in_support_c5 = {k: v for k, v in c5.items() if not comp_tags[k]["extrapolation"]}
    calibrated_c5 = {k: v for k, v in c5.items() if comp_tags[k]["brierBeatsOwnEra_2023_26"]}
    spread5_inSupport = [min(in_support_c5.values()), max(in_support_c5.values())] if in_support_c5 else None
    spread5_calibrated = [min(calibrated_c5.values()), max(calibrated_c5.values())] if calibrated_c5 else None
    spread5_honestInSupport = inp.get("honest", "today/spreadFall5_26w_inSupport", None, quiet=True)
    t5_noStrat = float(logit_mean(pd.DataFrame([in_support_c5]), list(in_support_c5.keys())).iloc[0]) if (strat_extrap and len(in_support_c5) >= 2) else None
    # 'all specifications': the declared list of distinct, non-learned point-target readings; the rest are listed as excluded with reasons
    all_specs, specs_excluded = {}, {}
    strat_iv = [(st.get("episodeBoot90") or {}).get("q05"), (st.get("episodeBoot90") or {}).get("q95")]
    for lab, path in ALL_SPECS_DECLARED:
        if path is None:
            k = lab.split(":")[1]
            if k in c5:
                if k == "strat" and strat_extrap:
                    specs_excluded[lab] = {"value": c5[k], "reason": f"extrapolation: outside its cell's M2 support (honest), enters only through its interval {strat_iv}"}
                else:
                    all_specs[lab] = c5[k]
            continue
        mod, pth = path.split("/", 1)
        v = inp.get(mod, pth, None, quiet=True)
        if v is not None:
            all_specs[lab] = v
    for lab, (path, why) in ALL_SPECS_EXCLUDED.items():
        mod, pth = path.split("/", 1)
        v = inp.get(mod, pth, None, quiet=True)
        if v is not None:
            specs_excluded[lab] = {"value": v, "reason": why}
    spread_all = [min(all_specs.values()), max(all_specs.values())] if all_specs else None
    spread_all_raw = [min(list(all_specs.values()) + [x["value"] for x in specs_excluded.values()]), max(list(all_specs.values()) + [x["value"] for x in specs_excluded.values()])] if all_specs else None
    # 90% interval for today's stack reading: the realised rate among OOS weeks in the same stack decile, bootstrapped over honest's episodes
    dec = decile_of(t5, ceiling["calibrationDeciles_stack"]) if t5 is not None else None
    interval5, dec_rows = None, None
    if dec is not None:
        sel = m5 & (pv >= dec["lo"]) & ((pv <= dec["hi"]) if dec["decile"] == 10 else (pv < dec["hi"]))   # same rule as the decile table
        dec_rows = int(sel.sum())

        def rate_on(ii):
            ss = sel[ii]
            return float(yv[ii][ss].mean()) if ss.sum() >= 5 else None
        interval5 = {**boot_blocks(blocks5, rate_on, nb, np.random.default_rng(7)), "decile": dec, "rowsInDecile": dec_rows, "realisedRateInDecile": dec["realised"],
                     "note": "DIAGNOSTIC, not the plan's criterion: the realised rate of the OOS weeks in the stack's own decile, bootstrapped over honest's episode blocks; "
                             "the plan's 'episode bootstrap of the stack' is undefined for a no-fit point and honest wrote no calibration deciles; the interval rests on the episodes touching the decile"}
        if interval5.get("n", 0):
            interval5["stackPointInsideInterval"] = bool(interval5["q05"] <= t5 <= interval5["q95"])
    # S(h) h = 1..52 from the hazard module's Weibull at today's covariates (shape flagged by the hazard module itself)
    curve = None
    if hz.get("alpha") and hz.get("lambdaWeeks") and isinstance(hz.get("drivers"), dict):
        eta = float(sum(hz["drivers"].values()) + sum((hz.get("clockContribution") or {}).values()))
        h = np.arange(1, 53)
        S = np.exp(-((h / float(hz["lambdaWeeks"])) ** float(hz["alpha"])) * np.exp(eta))
        curve = {"S_h_1_52": [round(float(x), 4) for x in S], "etaLogHazardRatio": round(eta, 4), "P13_check": round(float(1 - S[12]), 4), "P26_check": round(float(1 - S[25]), 4), "P26_reported": hz.get("P26"),
                 "reproduces": bool(abs(1 - S[25] - float(hz.get("P26") or 0)) < 0.002), "shapeValidated": inp.get("hazard", "today/shapeValidated"), "shapeNote": inp.get("hazard", "today/shapeNote")}
    onset = {"components_fall5_26w": c5, "componentTags": comp_tags, "stack_fall5_26w": t5, "stack_fall5_26w_withoutExtrapolatedStratum": t5_noStrat,
             "stack_fall5_26w_regimeAltReading": (float(logit_mean(pd.DataFrame([{**c5, "regime": float(today_regime_alt)}]), list(c5.keys())).iloc[0]) if (today_regime_alt is not None and "regime" in c5) else None),
             "regime_altReading_today_h26incl": today_regime_alt,
             "spread_fall5_26w_components": spread5, "spread_fall5_26w_componentsInSupport": spread5_inSupport, "spread_fall5_26w_componentsCalibratedIn2023_26": spread5_calibrated,
             "spread_fall5_26w_honestInSupport": spread5_honestInSupport,
             "spread_fall5_26w_allSpecifications": spread_all, "spread_fall5_26w_allSpecificationsIncludingExcluded": spread_all_raw, "allSpecifications": all_specs, "allSpecificationsExcluded": specs_excluded,
             "interval90_fall5_26w_stack": interval5, "interval90_fall5_26w_stratified_honest": [st.get("episodeBoot90", {}).get("q05"), st.get("episodeBoot90", {}).get("q95")] if st else None,
             "components_fall10_26w": c10, "regime_pFall10_26w_notInStack": today_comp10.get("regime"), "stack_fall10_26w": t10, "spread_fall10_26w_components": spread10,
             "P13": {"hazard_k5": hz.get("P13"), "hazard_k10": hz10.get("P13"), "regime_pFall5_13w": inp.get("regime", "today/pFall5_13w"), "multiscale_h13": inp.get("multiscale", "today/h13")},
             "P26_other": {"regime_hazard26_pure": inp.get("regime", "today/hazard26_pure"), "multiscale_h26": inp.get("multiscale", "today/h26")},
             "S_h": curve, "timeToCrossing_hazard": {k: hz.get(k) for k in ("medianWeeks", "w10", "w90", "hazardNextWeek")},
             "timeToFirst5ptFall_KM_stratum": st.get("kmWeeksToFirst5ptFall"), "regime_ET_weeksToEntry": inp.get("regime", "today/ET_weeksToEntry"),
             "fall10_note": "fall10_26w has one positive episode since 2019 (Oct 2020 - May 2021) and none since 2023: every 10-point probability is unidentified"}
    # duration
    hd = inp.get("hazard", "duration", {}) or {}
    hon_d = inp.get("honest", "duration", {}) or {}
    duration = {"conditionalOnStart": {"empiricalRangeDays_9falls": (hd.get("forecastInput") or {}).get("empiricalRangeDays"), "medianDays": (hd.get("forecastInput") or {}).get("medianDays"),
                                       "honest_fall5_q10_50_90_days": (hon_d.get("fall5") or {}).get("q10_50_90"), "uniform14_182_q10_50_90": (hon_d.get("fall5") or {}).get("uniform14_182_q10_50_90"),
                                       "ksVsUniform": (hon_d.get("fall5") or {}).get("ksVsUniform"), "fall25_n": (hon_d.get("fall25") or {}).get("n"), "fall25_q10_50_90_days": (hon_d.get("fall25") or {}).get("q10_50_90"),
                                       "lawBigThree": hd.get("bigThree"), "lawScores": hd.get("lawScores"), "lawNote": (hd.get("forecastInput") or {}).get("note"), "ownerPoint": "about 3 months (90 days)"},
                "continuationMode": {"active": bool(p_active is not None and p_active > 0.5), "pActive": p_active,
                                     "ifActive": {"regime_residualDwellWeeks": inp.get("regime", "today/dwellWeeks"), "regime_expectedFurtherFallPoints": inp.get("regime", "today/expectedFurtherFallPointsIfActive"),
                                                  "hazard_remainingDuration": {"coverageDescriptive": (hd.get("remaining") or {}).get("coverage"), "coverageForecastForm": (hd.get("remainingForecastForm") or {}).get("coverage"),
                                                                                "intervalScore": (hd.get("remainingForecastForm") or {}).get("intervalScore"), "naiveIntervalScore": (hd.get("remainingForecastForm") or {}).get("naiveIntervalScore")}}}}
    # drivers: top three contributions per component
    def top3(d):
        if not isinstance(d, dict):
            return None
        items = [(k, v) for k, v in d.items() if isinstance(v, (int, float))]
        return [{"name": k, "contribution": round(float(v), 4)} for k, v in sorted(items, key=lambda kv: -abs(kv[1]))[:3]]
    f5_contrib = inp.get("tda_sig", "today/readings/M0:fall5_26w/featureContrib", None, quiet=True)
    drivers = {"fixed5": {"top3LogitContributions": top3(f5_contrib), "source": "tda_sig today.readings M0 (= fixed5 through the same harness)" if f5_contrib else None,
                          "dropOneReading": inp.get("honest", "today/sensitivity/fixed5Drop")},
               "hazard": {"top3": top3({**(hz.get("drivers") or {}), **(hz.get("clockContribution") or {})}), "driversInvertedIn2023_26": [k for k, v in (inp.get("hazard", "today/driverSignStability", {}) or {}).items() if isinstance(v, dict) and v.get("invertedIn2023_26")] or None},
               "regime": {"top3LogitContributions": top3(inp.get("regime", "today/hazardDecomposition/logitContribution")), "emissionLLRvsCalm": inp.get("regime", "today/emissionLLRvsCalm"),
                          "note": inp.get("regime", "today/hazardDecomposition/note")},
               "strat": {"cell": st.get("name"), "outOfSupport": (st.get("support") or {}).get("outOfSupport"), "m2pm1pt": inp.get("honest", "today/sensitivity/m2pm1pt")}}
    # fractal legs
    ms = inp.get("multiscale", "criteria", {}) or {}
    leg1 = {"criteria": {"i_E2_above_shift_and_RW_p95_and_eras": {"pass": (ms.get("i") or {}).get("pass"), "E2": (ms.get("i") or {}).get("e2"), "shiftP95": (ms.get("i") or {}).get("shiftP95"), "rwP95": (ms.get("i") or {}).get("rwP95"), "byEra": (ms.get("i") or {}).get("byEra"), "fresh": (ms.get("i") or {}).get("fresh")},
                         "ii_stack_gain_ge_0.03": {"pass": (ms.get("ii") or {}).get("pass"), "gain": (ms.get("ii") or {}).get("gain"), "band": (ms.get("ii") or {}).get("band")},
                         "iii_ladder_flat_within_0.10": {"pass": (ms.get("iii") or {}).get("pass"), "ladder": (ms.get("iii") or {}).get("ladder"), "spread": (ms.get("iii") or {}).get("spread"), "excessOverRWMedian": (ms.get("iii") or {}).get("excessOverRWMedian")},
                         "iv_transfer_ratio_ge_0.5": {"pass": (ms.get("iv") or {}).get("pass"), "ratioPointTarget": (ms.get("iv") or {}).get("ratioPointTarget"), "ratioExcessOverRW": (ms.get("iv") or {}).get("ratioExcessOverRW")}},
            "E1_beats_placebos": ms.get("E1_beats_placebos"), "verdictGated": ms.get("verdictGated"), "moduleVerdict": ms.get("verdict")}
    l1p = [leg1["criteria"][k]["pass"] for k in leg1["criteria"]]
    if not ms:
        leg1["verdict"] = "not identifiable: multiscale results missing"
    elif any(p is None for p in l1p):
        leg1["verdict"] = "not identifiable: a criterion was not computed"
    else:
        gated = (ms.get("verdictGated") or {}).get("printed") is False
        leg1["verdict"] = ("FAIL" if not all(l1p) else "PASS") + (f" (provisional: nulls below the module's minimum, {ms.get('verdictGated')})" if gated else "")
    ss = inp.get("regime", "selfsim", {}) or {}
    if not ss or ss.get("skipped"):
        leg2 = {"verdict": "not identifiable: the regime module's daily twin was not run (selfsim skipped in --fast); needs the full run with --daily", "selfsim": ss}
    else:
        leg2 = {"frobenius_Pd7_vs_Pw": ss.get("frobenius_Pd7_vs_Pw"), "halfSampleWeeklyDistance": ss.get("halfSampleWeeklyDistance"), "dailyIaaftP05": (ss.get("dailyIaaftSurrogates") or {}).get("p05"),
                "passes": ss.get("passes"), "activeDwell": ss.get("activeDwell")}
        p_ = ss.get("passes") or {}
        leg2["verdict"] = ("not identifiable: IAAFT p05 missing" if p_.get("belowIaaftP05") is None else ("PASS" if (p_.get("belowHalfSample") and p_.get("belowIaaftP05")) else "FAIL"))
    soj = hd.get("sojourns") or {}
    shapes = {k: v["FALL"] for k, v in soj.items() if isinstance(v, dict) and isinstance(v.get("FALL"), dict) and v["FALL"].get("shape05") is not None}
    common_lo = max((v["shape05"] for v in shapes.values()), default=None)
    common_hi = min((v["shape95"] for v in shapes.values()), default=None)
    shape_const = (common_lo is not None and common_hi is not None and common_lo <= common_hi)
    law_slope = (hd.get("lawSlopeNull") or {}).get("real")
    H_law = hd.get("H_fromLaw")
    scale_slope = soj.get("logLogSlope_FALL")
    hcrit = inp.get("hazard", "criteria", {}) or {}
    law_cov = ((hd.get("lawScores") or {}).get("law") or {}).get("coverage")
    n_scoreable = (int(str(law_cov).split("/")[1]) if law_cov and "/" in str(law_cov) else None)
    leg3 = {"sojournShapeFALL_byK": {k: {"shape": v["shape"], "band": [v["shape05"], v["shape95"]]} for k, v in shapes.items()},
            "shapeConstantWithinBands": bool(shape_const), "commonShapeBand": [common_lo, common_hi],
            "shapeTestNote": "this module's own operationalisation (non-empty intersection of the FALL Weibull-shape 90% bands across k); the hazard module has no shape-constancy criterion of its own",
            "scaleVsK_logLogSlope_FALL": scale_slope, "lawSlope_logDurationOnLogSize": law_slope, "H_fromLaw": H_law, "expectedSlope_1_over_H": (round(1 / H_law, 3) if H_law else None),
            "scaleGrowsAsK_1overH": "not identifiable: the hazard module writes the scale-vs-k slope as a point (no bootstrap band), so 'at the same H as the duration law' cannot be tested; the two numbers are printed side by side only",
            "lawSlopeInsideIAAFT": (hd.get("lawSlopeNull") or {}).get("iaaft"), "lawSlopeInsideFBm": (hd.get("lawSlopeNull") or {}).get("fbm"), "lawScores": hd.get("lawScores"),
            "lawCriterion_coverage_ge_7of9_and_beats_blind_and_iaaft": hcrit.get("duration_law_coverage>=7of9_and_beats_blind_and_iaaft"),
            "lawCriterionNote": f"scored by the hazard module on its DESCRIPTIVE law (realised size, centred peaks) over {n_scoreable} scoreable events (the plan says 7 of 9; one event is unscorable), not on the point-in-time forecast form: {hcrit.get('_durationNote')}"}
    if not hd:
        leg3["verdict"] = "not identifiable: hazard results missing"
    else:
        iaaft_p = ((hd.get("lawSlopeNull") or {}).get("iaaft") or {}).get("p")
        generic = iaaft_p is not None and 0.05 < iaaft_p < 0.95
        leg3["lawGeneric"] = bool(generic)
        leg3["verdict"] = ("PASS" if (shape_const and hcrit.get("duration_law_coverage>=7of9_and_beats_blind_and_iaaft")) else "FAIL") + \
            (" (shape constant within bands by this module's reading; k^(1/H) clause not identifiable; law slope inside the IAAFT surrogate band: generic, not evidence; coverage criterion fails on the descriptive law)" if (shape_const and generic) else "")
    fals = inp.get("honest", "falsifiers", {}) or {}
    cal_status = {k: (v.get("status") if isinstance(v, dict) else None) for k, v in fals.items()}
    fractal = {"leg1_grammarTransfer_multiscale": leg1, "leg2_chainSelfSimilarity_regime": leg2, "leg3_durationScaling_hazard": leg3, "calendarFalsifiers_honest": fals, "calendarStatus": cal_status}
    legs = [leg1["verdict"], leg2["verdict"], leg3["verdict"]]
    n_pass = sum(1 for v in legs if v.startswith("PASS"))
    n_fail = sum(1 for v in legs if v.startswith("FAIL"))
    n_ni = sum(1 for v in legs if v.startswith("not identifiable"))
    fractal["overall"] = ("SUPPORTED" if n_pass == 3 and all(s == "not-yet" or s == "pass" for s in cal_status.values()) else
                          ("NOT SUPPORTED" if n_fail >= 2 else ("PARTIAL" if n_pass >= 1 and n_fail <= 1 else "NOT SUPPORTED / NOT IDENTIFIABLE"))) + f" (legs pass {n_pass} / fail {n_fail} / not identifiable {n_ni})"

    # spread note
    spread_note = None
    if c5 and interval5 and interval5.get("n"):
        lo_k, hi_k = min(c5, key=c5.get), max(c5, key=c5.get)
        inside_all = all(interval5["q05"] <= v <= interval5["q95"] for v in c5.values())
        outside = [k for k, v in c5.items() if not (interval5["q05"] <= v <= interval5["q95"])]
        spread_note = (f"The components disagree by {c5[hi_k] - c5[lo_k]:.2f} ({lo_k} {c5[lo_k]:.3f} to {hi_k} {c5[hi_k]:.3f}"
                       + (f"; the upper end {hi_k} is flagged by its module: {comp_tags[hi_k]['moduleFlag']}" if comp_tags.get(hi_k, {}).get("moduleFlag") else "")
                       + f"); the stack's own-decile diagnostic interval [{interval5['q05']:.3f}, {interval5['q95']:.3f}] (realised rate of the {dec_rows} OOS weeks in the stack's own decile, "
                       f"{len(blocks5)} honest-episode blocks, {dec['episodesTouched']} episode(s) touching the decile) "
                       + ("contains every component: the disagreement is inside the band." if inside_all else f"excludes {outside}: the disagreement is NOT inside the band.")
                       + (f" The stratified point is an extrapolation (honest) and enters only through its interval {strat_iv}; without it the component spread is {[round(x, 3) for x in spread5_inSupport]}; honest's own in-support spread is {spread5_honestInSupport}." if strat_extrap and spread5_inSupport else ""))
    today = {"asOf": str(as_of.date()), "dataThrough": {"utc": utc_label, "et": et_label}, "provisionalBars": provisional, "state": state, "onset": onset, "duration": duration, "drivers": drivers,
             "fractal": {k: (v.get("verdict") if isinstance(v, dict) else v) for k, v in fractal.items() if k.startswith("leg")}, "calendarFalsifiers": cal_status, "spread_note": spread_note,
             "honestClaim_fromHonestModule": inp.get("honest", "claims/honestClaim")}
    today["provisionalReadings"] = {"fixed5": inp.get("honest", "today/provisionalReading/fixed5", None, quiet=True), "hazard_P26": inp.get("hazard", "today/k5_provisional/P26", None, quiet=True),
                                    "regime_pFall5_26w": inp.get("regime", "today/provisionalBar/pFall5_26w", None, quiet=True), "flag": "partial current week, not a forecast"}

    say(f"TODAY {as_of.date()} BTC.D {fmt(state['btcd'], 1)} ({fmt(state['btcd_exstable'], 1)} ex-stable): state = regime P(active) {fmt(p_active, 4)} | hazard {state['hazard_state_k5']} {fmt(state['hazard_weeksSinceConfirmedTroughK5'], 0)} w since confirmed trough, vol pct {fmt(state['hazard_btcdVol13wPercentile'], 1)} "
        f"| stratum '{st.get('name')}' n {st.get('n')} k {st.get('k')} nEp {st.get('nEp')}{' EXTRAPOLATION (' + ','.join((st.get('support') or {}).get('outOfSupport') or []) + ' out of support)' if st.get('extrapolation') else ''} | multiscale FALL {fmt((state['multiscale_pstate91'] or {}).get('FALL'))} | fresh {fmt(state['fresh'])} readiness {fmt(state['readinessOn'])}")
    def tag_str(k):
        t = comp_tags.get(k, {})
        return f"{k} {c5[k]:.3f}" + (" EXTRAPOLATION" if t.get("extrapolation") else "") + f" (2023-26 Brier skill {fmt(t.get('brierSkillVsOwnEra_2023_26'), 2)})"
    say(f"{TAG}  P(5+ in 26w): components {{{', '.join(f'{k} {v:.3f}' for k, v in c5.items())}}} -> STACK {fmt(t5)}"
        + (f" (without the extrapolated stratum point {fmt(t5_noStrat)}; with regime = {REGIME_READING_ALT} {fmt(onset['stack_fall5_26w_regimeAltReading'])})" if t5_noStrat is not None else "")
        + f"; RAW component spread [{fmt(spread5[0] if spread5 else None)}, {fmt(spread5[1] if spread5 else None)}] = {tag_str(min(c5, key=c5.get))} .. {tag_str(max(c5, key=c5.get))}")
    say(f"  P(5+ in 26w) qualified spreads: components minus module-flagged extrapolations {spread5_inSupport and [round(x, 3) for x in spread5_inSupport]} (honest's own in-support spread {spread5_honestInSupport}); "
        f"components with 2023-26 Brier skill > 0: {list(calibrated_c5) or 'none'} {spread5_calibrated and [round(x, 3) for x in spread5_calibrated]}; declared distinct non-learned specifications [{fmt(spread_all[0] if spread_all else None)}, {fmt(spread_all[1] if spread_all else None)}] "
        f"({len(all_specs)} readings; excluded {sorted(specs_excluded)}; with them [{fmt(spread_all_raw[0] if spread_all_raw else None)}, {fmt(spread_all_raw[1] if spread_all_raw else None)}])")
    say(f"  stack own-decile interval (DIAGNOSTIC, not the plan's criterion) {('[' + fmt(interval5['q05']) + ', ' + fmt(interval5['q95']) + '] (decile ' + str(dec['decile']) + ', realised ' + fmt(dec['realised']) + ', ' + str(dec_rows) + ' rows, ' + str(dec['episodesTouched']) + ' episode(s): rests on that many events)') if interval5 and interval5.get('n') else 'na'}; "
        f"stratified interval (honest episode bootstrap) {onset['interval90_fall5_26w_stratified_honest']}")
    say(f"  P(10+ in 26w): components {{{', '.join(f'{k} {v:.4f}' for k, v in c10.items())}}} -> STACK {fmt(t10, 4)} (regime's own 10-pt reading {fmt(today_comp10.get('regime'))} not in the stack); unidentified (one episode). "
        f"P13: hazard {fmt(hz.get('P13'))} regime MC {fmt(onset['P13']['regime_pFall5_13w'])} multiscale h13 {fmt(onset['P13']['multiscale_h13'])}")
    say(f"  shape S(h): hazard Weibull eta {fmt(curve['etaLogHazardRatio'] if curve else None)} reproduces P26 {fmt(curve['reproduces'] if curve else None)}; S(13/26/52) {fmt(curve['S_h_1_52'][12] if curve else None)}/{fmt(curve['S_h_1_52'][25] if curve else None)}/{fmt(curve['S_h_1_52'][51] if curve else None)}; "
        f"time to crossing median {hz.get('medianWeeks')} w10 {hz.get('w10')} w90 {hz.get('w90')} (NOT forecasts: shape fails its checks, per hazard); KM stratum weeks w10/50/90 {st.get('kmWeeksToFirst5ptFall')}; regime E[T to entry] {fmt(onset['regime_ET_weeksToEntry'], 1)} w")
    cd = duration["conditionalOnStart"]
    say(f"  duration | start: empirical 9-fall range {cd['empiricalRangeDays_9falls']} d median {cd['medianDays']}, q10/50/90 {cd['honest_fall5_q10_50_90_days']} vs uniform(14,182) {cd['uniform14_182_q10_50_90']} KS p {fmt((cd['ksVsUniform'] or {}).get('p'), 2)}; "
        f"25-pt falls n {cd['fall25_n']} q10/50/90 {cd['fall25_q10_50_90_days']}; law on the big two coverage {(cd['lawBigThree'] or {}).get('coverage')}; owner's 90 d is a median with a 2-week-to-6-month band")
    cm = duration["continuationMode"]
    say(f"  continuation mode {'ON' if cm['active'] else 'OFF'} (P(active) {fmt(p_active, 4)} <= 0.5): if active, regime residual dwell median {(cm['ifActive']['regime_residualDwellWeeks'] or {}).get('median')} w [{(cm['ifActive']['regime_residualDwellWeeks'] or {}).get('q05')},{(cm['ifActive']['regime_residualDwellWeeks'] or {}).get('q95')}], "
        f"expected further fall {fmt(cm['ifActive']['regime_expectedFurtherFallPoints'], 2)} pts; hazard remaining-duration forecast form coverage {cm['ifActive']['hazard_remainingDuration']['coverageForecastForm']} vs naive (not better than naive)")
    say(f"  drivers: fixed5 {[(d['name'], d['contribution']) for d in (drivers['fixed5']['top3LogitContributions'] or [])]} | hazard {[(d['name'], d['contribution']) for d in (drivers['hazard']['top3'] or [])]} "
        f"| regime {[(d['name'], d['contribution']) for d in (drivers['regime']['top3LogitContributions'] or [])]} (intercept-dominated) | strat cell {drivers['strat']['cell']}, m2 -1pt -> {((drivers['strat']['m2pm1pt'] or {}).get('-0.01') or {}).get('strat')}")
    say(f"FRACTAL leg 1 grammar transfer: {leg1['verdict']}; i E2 {fmt(leg1['criteria']['i_E2_above_shift_and_RW_p95_and_eras']['E2'])} vs shift p95 {fmt(leg1['criteria']['i_E2_above_shift_and_RW_p95_and_eras']['shiftP95'])} RW p95 {fmt(leg1['criteria']['i_E2_above_shift_and_RW_p95_and_eras']['rwP95'])} eras {leg1['criteria']['i_E2_above_shift_and_RW_p95_and_eras']['byEra']}; "
        f"ii gain {(leg1['criteria']['ii_stack_gain_ge_0.03']['gain'] or {}).get('pooled')} band {leg1['criteria']['ii_stack_gain_ge_0.03']['band']}; iii ladder spread {leg1['criteria']['iii_ladder_flat_within_0.10']['spread']}; iv ratio {leg1['criteria']['iv_transfer_ratio_ge_0.5']['ratioPointTarget']} (excess ratio {leg1['criteria']['iv_transfer_ratio_ge_0.5']['ratioExcessOverRW']}); E1 beats placebos {fmt(leg1['E1_beats_placebos'])}")
    say(f"FRACTAL leg 2 chain self-similarity: {leg2['verdict']}" + (f"; ||Pd^7-Pw|| {leg2.get('frobenius_Pd7_vs_Pw')} vs half-sample {leg2.get('halfSampleWeeklyDistance')} vs IAAFT p05 {leg2.get('dailyIaaftP05')}" if "frobenius_Pd7_vs_Pw" in leg2 else ""))
    say(f"FRACTAL leg 3 duration scaling: {leg3['verdict']}; FALL sojourn shapes {[(k, v['shape']) for k, v in leg3['sojournShapeFALL_byK'].items()]} common band {leg3['commonShapeBand']} (this module's reading of 'constant'); "
        f"scale~k slope {leg3['scaleVsK_logLogSlope_FALL']} vs 1/H {leg3['expectedSlope_1_over_H']} (no band: k^(1/H) clause not identifiable; law slope {leg3['lawSlope_logDurationOnLogSize']}, IAAFT p {((hd.get('lawSlopeNull') or {}).get('iaaft') or {}).get('p')}); "
        f"law coverage {law_cov} (descriptive law, {n_scoreable} scoreable events) interval score {((hd.get('lawScores') or {}).get('law') or {}).get('intervalScore')} vs blind {((hd.get('lawScores') or {}).get('sizeBlind') or {}).get('intervalScore')} vs IAAFT-law {((hd.get('lawScores') or {}).get('iaaftLaw') or {}).get('intervalScore')}")
    say(f"FRACTAL calendar falsifiers: {cal_status}; (i) max weekly close since Jun 2025 {(fals.get('i_higherHighAbove65.7') or {}).get('maxWeeklyCloseSince2025-06-29')} vs 65.7; (ii) deadline {(fals.get('ii_engineImminentSinceFeb2023') or {}).get('deadline')}, engine 'imminent' {(fals.get('ii_engineImminentSinceFeb2023') or {}).get('weeksEngineHasSaidImminent')} weeks; (iii) new 5+ fall started {(fals.get('iii_nextFallWhileEngineFit<0.8') or {}).get('newFallStarted')}")
    say(f"FRACTAL overall: {fractal['overall']}")
    if spread_note:
        say(f"SPREAD NOTE: {spread_note}")
    alt_s = success.get("altReading_regimeHazard26", {})
    say(f"{TAG}SUCCESS [6]: stack Brier <= fixed5 every era {fmt(success['stackBrierLeFixed5EveryEra'])} {success['byEra']['vsFixed5']}; <= own-era base every era {fmt(success['stackBrierLeOwnEraBaseEveryEra'])}; <= train base every era {fmt(success['stackBrierLeTrainBaseEveryEra'])}; "
        f"pooled AUC inside fixed5 band {fmt(success['stackPooledAucInsideFixed5Band'])}; interval-vs-honest-calibration-deciles criterion NOT IDENTIFIABLE as written (honest wrote none; diagnostic: today's point inside its own-decile interval {fmt(interval5.get('stackPointInsideInterval') if interval5 else None)})"
        + (f"; alt regime reading: Brier<=fixed5 {fmt(alt_s.get('stackBrierLeFixed5EveryEra'))} <=own-era {fmt(alt_s.get('stackBrierLeOwnEraBaseEveryEra'))} inside band {fmt(alt_s.get('stackPooledAucInsideFixed5Band'))}" if alt_s else "")
        + (f"; fixed5 is a post-hoc comparator (honest), fixed5brief today {fmt(ceiling['fixed5Disclosure'].get('fixed5briefToday'))}, no series to re-score the stack with" if ceiling.get("fixed5Disclosure") else ""))
    stack_pass = success["stackBrierLeFixed5EveryEra"] and success["stackBrierLeOwnEraBaseEveryEra"] and success["stackPooledAucInsideFixed5Band"]
    verdict = ("the pre-registered stack PASSES its criteria" if stack_pass else "the pre-registered stack FAILS its criteria") + (" under both regime readings" if alt_s and not (alt_s.get("stackBrierLeFixed5EveryEra") and alt_s.get("stackBrierLeOwnEraBaseEveryEra") and alt_s.get("stackPooledAucInsideFixed5Band")) else "") + \
        f"; the forecast object's headline is the spread, not the centre: P(5+ in 26w) raw components {fmt(spread5[0] if spread5 else None)}..{fmt(spread5[1] if spread5 else None)} (upper end {max(c5, key=c5.get) if c5 else 'na'} is flagged by its module: {comp_tags.get(max(c5, key=c5.get), {}).get('moduleFlag') if c5 else ''}), " + \
        f"honest's in-support spread {spread5_honestInSupport}, declared specifications {fmt(spread_all[0] if spread_all else None)}..{fmt(spread_all[1] if spread_all else None)}; " + \
        f"honest claim stands: {inp.get('honest', 'claims/honestClaim', 'base rate plus readiness, with intervals')}; fractal thesis {fractal['overall']}" + \
        ("; ALL OF THIS IS SMOKE ONLY: re-run after the full module runs exist under the plan's folder names" if provisional_run else "")
    say(f"{TAG}VERDICT: {verdict}")

    # ---- results.json
    if inp.missing:
        notes.append(f"missing keys (contributed nothing): {sorted(set(inp.missing))}")
    notes.append("No fitting here: every number is read from the modules' results.json or computed from their frozen OOS series; the labels and the fresh-start mask are rebuilt from the data only on the scoring rows.")
    notes.append("The stack's components and equal logit weights were fixed in the plan before any OOS number was read here; the stack's shifted-target null is scoring-only, which is valid because the stack has no fit. "
                 "Two qualifications: fixed5 itself is the honest module's post-hoc comparator (round 7's most-picked set over refits through 2026; fixed5brief, the brief's literal set, is a paired tie with it in honest and no module exports its series), "
                 "and the regime component's wording is ambiguous in the plan (see the regime-component note): the pre-registration covers composition and weights, not fixed5's selection or that wording.")
    notes.append("The 'all specifications' spread is a DECLARED list of distinct, non-learned point-target readings (ALL_SPECS_DECLARED); readings excluded with reasons are in today.onset.allSpecificationsExcluded "
                 "(the learned honest stack, km26 = the stratified rate in survival form, the sigma-unit multiscale target, strat_vol; the stratified point itself when out of support). The raw component min-max is always printed as the plan requires.")
    notes.append("The plan's success criterion 'the object's interval contains the realised rate in the honest module's calibration deciles' is not identifiable as written (honest wrote no calibration deciles); "
                 "the stack's own-decile realised-rate interval is kept as a diagnostic and the tautological 'contains realised rate' flag was dropped.")
    notes.append(f"Today's object reads the last complete Sunday close {as_of.date()}; the provisional bar(s) {provisional} are flagged and never scored; timestamps come from the data's last daily bar, not the wall clock.")
    notes.append("fall10_26w: one positive episode (Oct 2020 - May 2021, 27 weeks) and none since 2023; every 10-point AUC ranks one event and every 10-point probability is unidentified.")
    if not stack_pass:
        notes.append("The equal-weight stack is dragged by its weakest components (the regime MC reads > 0.5 in most OOS weeks; the stratified rate and the Weibull hazard are wrong-signed in 2023-26): a failed trial is a result; no weights were learned to rescue it.")
    series = {"stack_fall5_26w": C.thin(stack5.where(full5), every=2), "stack_fall10_26w": C.thin(stack10.where(V10[avail10].notna().all(axis=1)), every=2),
              "stack_fall5_26w_regimeAltReading": (C.thin(stack5_alt.where(full5_alt), every=2) if stack5_alt is not None else None),
              "stack_fall5_26w_nocarry": C.thin(stack5_nocarry, every=2), "nComponents_fall5": C.thin(V5[avail5].notna().sum(axis=1).astype(float), every=2, digits=0),
              "regime_pActive_aligned": C.thin(VX["p_active_regime"], every=2), "hazard_state_k5_aligned": C.thin(VX["state_k5_hazard"], every=2, digits=0), "stratum_code_aligned": C.thin(VX["stratum_code"], every=2, digits=0)}
    res = {"module": "study8_forecast", "dataThroughUtc": utc_label, "dataThroughEt": et_label, "asOf": str(as_of.date()), "provisionalBars": provisional, "fast": bool(a.fast),
           "runtimeSec": round(float((pd.Timestamp.now() - t_start).total_seconds()), 1), "inputs": {"root": root, "found": inp.path, "moduleAsOf": mod_as_of, "smoke": smoke, "provisional": bool(provisional_run)},
           "design": {"stack5": STACK5, "stack5Used": avail5, "stack10": STACK10, "stack10Used": avail10, "weights": "equal, logit space, pre-registered", "carryDays": CARRY_DAYS, "blockWeeks": BLOCK_WEEKS, "runupWeeks": RUNUP_WEEKS,
                      "regimeReading": {"used": REGIME_READING, "planSentence": "[6] 'TVTP V2 P(fall5_26w) incl. occupancy'", "alternative": REGIME_READING_ALT, "alternativePlanSentence": "Layer 5 'TVTP hazard incl. occupancy'",
                                        "disclosure": "the plan names the component both ways; the [6] wording is the headline and scores better than the Layer-5 wording on every metric; both are scored and both fail"},
                      "fixed5": {"source": inp.get("honest", "comparator/fixed5", None, quiet=True), "status": "post-hoc comparator per honest (round 7's most-picked set over refits through 2026); fixed5brief = the brief's literal set, a paired tie in honest, no exported series"},
                      "allSpecsDeclared": [lab for lab, _ in ALL_SPECS_DECLARED], "allSpecsExcluded": {k: v[1] for k, v in ALL_SPECS_EXCLUDED.items()},
                      "trainBaseFrom": TRAIN_BASE_FROM, "episodeSource": "honest evidence_ceiling.episodeLOO fixed5:fall5_26w perEpisode", "episodes5": episodes5, "episodes10": episodes10},
           "alignment": {"grid": [str(grid[0].date()), str(grid[-1].date())], "rows": int(len(grid)), "fullCompositionRows": int(full5.sum()), "exactShare": exact_share, "carriedShare": carried_share},
           "oos": oos, "evidence_ceiling": ceiling, "null": null, "success": success, "today": today, "fractal": fractal, "series": series, "notes": notes, "printedLines": _LINES[0], "droppedLines": _LINES[1]}
    C.write_results(a.out, rnd(res, 4))
    if _LINES[1]:
        print(f"({_LINES[1]} lines dropped by the 60-line cap)")


if __name__ == "__main__":
    main()
