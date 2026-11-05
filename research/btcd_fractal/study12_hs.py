#!/usr/bin/env python3
"""Round 12: head-and-shoulders timing study (ROUND12_PLAN.md, sections [1]-[4]).

Question: once a head-and-shoulders pattern's right shoulder is in play, does it say WHEN the neckline breaks and
WHEN the measured move completes, better than the base rates the forecast already carries?

[1] Detector: point-in-time zigzag on weekly closes (logit space for dominance shares, log space for prices) with a
    reversal threshold r in {0.08, 0.15}. A pivot exists only once the reversal of size r from it has printed. A top
    pattern is five consecutive pivots S1 (peak) T1 (trough) H (peak) T2 (trough) S2 (peak) with the plan's geometry;
    the inverse pattern is the mirror image (the same code on the negated series). A pattern is recorded at the week
    S2 is confirmed (its "in play" week); what followed (break, target, completion, fail, expiry at 78 weeks) is read
    from later closes only. Nothing after S2's confirmation enters the detection, the neckline or the target.
[2] Laws: T1 symmetry (S2 -> break ~ S1 -> T1), T2 shoulder symmetry (H -> S2 ~ S1 -> H), T3 decline duration
    (break -> target ~ H -> T2), T3alt (break -> target ~ 0.5 x S1 -> S2). Each against (a) the naive baseline, the
    expanding median of the same duration over the patterns whose outcome was known before the prediction was made
    (all series pooled, in time order, same threshold), and (b) the same law on placebo series (IAAFT surrogates and
    matched random walks per series, the same detector), one-sided Mann-Whitney real errors < placebo errors.
    Rates: breaks within 13/26/52 weeks of the in-play week, targets within 26/52 weeks of the break, and the move
    of one head height from the in-play week against the matched base rate (all weeks of the same series and era).
    Additional diagnostics beside the pre-registered test (they never replace it): the same block on the patterns
    that were still in play at S2's confirmation (a pattern whose confirming close is already the neckline break
    was never usable), the span-stratified and scale-free rank tests (the placebo patterns are shorter than the
    real ones, so a raw-week error is not on the same footing), the pooled tests with threshold duplicates and
    cross-series clusters counted once, the real against placebo time scale of the detector's output, criteria (i)
    and (iii) replayed on placebo universes subsampled to the real per-era n (the share of noise at or above the
    real value), and the plan's equal-move comparison done literally: a close beyond the neckline level fixed at the
    in-play week, and the target, against matched base rates (era in-sample, era without the pattern's own weeks,
    expanding point in time).
[3] The current patterns on BTC.D (top), USDT.D (inverse) and ETHUSD (either), with the time frame each law gives
    and the historical error band (from the patterns in play at confirmation, the only ones a forming pattern can
    join, or from all patterns for a structure that broke at or before its confirmation; the other band beside it;
    the base-rate bands at the structure's own threshold; every band for an event not yet seen clipped at the
    earliest week it can happen); if the detector finds none, the nearest pivot structure with the checks it fails;
    the same structure read on a horizontal neckline through T2 and across a sweep of reversal thresholds
    (diagnostic, the pre-registered thresholds are unchanged); the joint reading as a paragraph.
[4] Criteria applied verbatim; verdict strings carry the failing criterion; multiple comparisons stated.

Usage: python3 study12_hs.py --data <dir> --out <dir> [--placebos 40] [--workers N] [--fast]
Only numpy, pandas, matplotlib (numba optional). No network.
"""
import argparse
import math
import os
import sys
import textwrap
import time
from datetime import datetime, timedelta, timezone
from multiprocessing import get_context

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from study8_common import iaaft, matched_rw, write_results  # noqa: E402

try:
    from numba import njit
except Exception:  # numba is optional; the zigzag is cheap enough in plain Python
    def njit(*args, **kwargs):
        if len(args) == 1 and callable(args[0]) and not kwargs:
            return args[0]
        return lambda f: f

PLAN = "ROUND12_PLAN.md"
THRESHOLDS = (0.08, 0.15)
EXPIRY_WEEKS = 78          # no break within 78 weeks of S2 -> expired (plan [1])
COMPLETION_WEEKS = 78      # the target is looked for within 78 weeks of the break (the same window, see detector notes)
SHOULDER_TOL = 0.5         # |S1 - S2| <= 0.5 x (H - neckline at S2)
NECK_RISE = 0.5            # |neckline at S2 - neckline at S1| <= 0.5 x head height
SPAN_LO, SPAN_HI = 1.0 / 3.0, 3.0   # right-shoulder span (H -> S2) between 1/3 and 3 x the left (S1 -> H)
BASELINE_MIN = 3           # the expanding median needs this many prior completed patterns to exist
NEAR_LOOKBACK = 130        # weeks: how far back the "nearest structure" search looks for S2
IAAFT_IT = 50
RW_BLOCK_WEEKS = 13
ERAS = (("2013-18", 2013, 2018), ("2019-22", 2019, 2022), ("2023-26", 2023, 2026))
# caps_report.json: the spliced dominance series is CoinMarketCap before this week and TradingView from it on. The
# pooled tests use one BTC-dominance history: BTCD_CMC patterns before the splice week, BTC.D patterns from it on.
SPLICE_WEEK = pd.Timestamp("2018-06-03")
SERIES = ["BTC.D", "BTCD_CMC", "USDT.D", "ETHUSD", "BTCUSD", "TOTAL3", "ETH.D", "OTHERS.D", "TOTAL2", "TOTAL"]
RAW = ["BTC.D", "BTCD_CMC", "USDT.D", "ETHBTC", "BTCUSD", "TOTAL3", "ETH.D", "OTHERS.D", "TOTAL2", "TOTAL"]
CURRENT = {"BTC.D": "top", "USDT.D": "inverse", "ETHUSD": "either"}
LAWS = ["T1", "T2", "T3", "T3alt"]
LAW_TEXT = {
    "T1": {"name": "symmetry", "predicts": "weeks S2 -> break", "from": "weeks S1 -> T1 (the left shoulder's fall)"},
    "T2": {"name": "shoulder symmetry", "predicts": "weeks H -> S2", "from": "weeks S1 -> H"},
    "T3": {"name": "decline duration", "predicts": "weeks break -> target", "from": "weeks H -> T2"},
    "T3alt": {"name": "half span", "predicts": "weeks break -> target", "from": "0.5 x weeks S1 -> S2"},
}
H_BREAK = (13, 26, 52)
H_TARGET = (26, 52)
COL = {"blue": "#2a78d6", "orange": "#eb6834", "aqua": "#1baf7a", "yellow": "#eda100", "bg": "#fcfcfb",
       "text": "#0b0b0b", "text2": "#52514e", "grid": "#e6e5e1"}


# ------------------------------------------------------------------------------------------------- clock
def clock_strings():
    now = datetime.now(timezone.utc)
    est = now - timedelta(hours=5)
    return {"utc": now.strftime("%Y-%m-%d %H:%M UTC"),
            "est": est.strftime("%Y-%m-%d ") + est.strftime("%I:%M %p").lstrip("0") + " EST (UTC-5)"}


# ------------------------------------------------------------------------------------------------- data
def is_share(name):
    return name.endswith(".D") or name.startswith("BTCD_")


def read_daily(data_dir, name):
    f = os.path.join(data_dir, f"{name}_1d.csv")
    if not os.path.exists(f):
        return None
    d = pd.read_csv(f)
    s = pd.Series(d["c"].values.astype(float), index=pd.DatetimeIndex(pd.to_datetime(d["ts"], unit="ms")).normalize())
    s = s[~s.index.duplicated()].sort_index()
    return s[s > 0]


def to_space(v, space):
    v = np.asarray(v, float)
    if space == "logit":
        p = np.clip(v / 100.0, 1e-4, 1 - 1e-4)
        return np.log(p / (1 - p))
    return np.log(np.clip(v, 1e-12, None))


def from_space(z, space):
    z = np.asarray(z, float)
    if space == "logit":
        return 100.0 / (1.0 + np.exp(-z))
    return np.exp(z)


def load_series(data_dir):
    """Weekly closes (W-SUN last, complete weeks only) per series, with the transformed series x."""
    raw = {n: read_daily(data_dir, n) for n in RAW}
    if raw.get("ETHBTC") is not None and raw.get("BTCUSD") is not None:
        e, b = raw["ETHBTC"].align(raw["BTCUSD"], join="inner")
        raw["ETHUSD"] = e * b
    today = pd.Timestamp(datetime.now(timezone.utc).date())
    out = {}
    for n in SERIES:
        s = raw.get(n)
        if s is None or len(s) < 200:
            continue
        w = s.resample("W-SUN").last()
        if w.index[-1] > s.index[-1]:   # the last week has not closed: drop the partial bar
            w = w.iloc[:-1]
        w = w.ffill().dropna()
        space = "logit" if is_share(n) else "log"
        partial = bool(s.index[-1] >= today)   # a bar dated today is still printing: an intraday value as of the fetch
        out[n] = {"weekly": w, "x": to_space(w.values, space), "space": space,
                  "lastDaily": {"date": ds(s.index[-1]), "level": round(float(s.iloc[-1]), 6), "partial": partial,
                                "note": ("the last daily bar is dated today, so its value is an intraday print as of the fetch time, not a close; "
                                         "nothing in the detection or the laws uses it" if partial else
                                         "the last complete daily bar; nothing in the detection or the laws uses it")}}
    return out


def ds(t):
    return pd.Timestamp(t).strftime("%Y-%m-%d")


def era_of(t):
    y = pd.Timestamp(t).year
    for name, a, b in ERAS:
        if a <= y <= b:
            return name
    return ERAS[0][0] if y < ERAS[0][1] else ERAS[-1][0]


def in_pool(name, t):
    """One BTC-dominance history in the pooled tests: CMC before the splice week, TradingView from it on."""
    if name == "BTC.D":
        return bool(pd.Timestamp(t) >= SPLICE_WEEK)
    if name == "BTCD_CMC":
        return bool(pd.Timestamp(t) < SPLICE_WEEK)
    return True


def article(kind):
    return "an" if kind[0] in "aeiou" else "a"


# ------------------------------------------------------------------------------------------------- zigzag
@njit(cache=False)
def _zigzag(x, r):
    """Point-in-time zigzag. A peak (trough) is confirmed at the first bar whose close is r below (above) it.
    Returns pivot indices, types (+1 peak, -1 trough), confirmation indices, the current direction (+1 rising from
    the last trough, -1 falling from the last peak, 0 undecided) and the index of the provisional extreme."""
    n = x.shape[0]
    pi = np.empty(n, np.int64)
    pt = np.empty(n, np.int64)
    pc = np.empty(n, np.int64)
    m = 0
    hi = 0
    lo = 0
    d = 0
    for t in range(1, n):
        v = x[t]
        if d == 0:
            if v > x[hi]:
                hi = t
            if v < x[lo]:
                lo = t
            if v - x[lo] >= r:
                pi[m] = lo; pt[m] = -1; pc[m] = t; m += 1
                d = 1; hi = t
            elif x[hi] - v >= r:
                pi[m] = hi; pt[m] = 1; pc[m] = t; m += 1
                d = -1; lo = t
        elif d == 1:
            if v > x[hi]:
                hi = t
            elif x[hi] - v >= r:
                pi[m] = hi; pt[m] = 1; pc[m] = t; m += 1
                d = -1; lo = t
        else:
            if v < x[lo]:
                lo = t
            elif v - x[lo] >= r:
                pi[m] = lo; pt[m] = -1; pc[m] = t; m += 1
                d = 1; hi = t
    prov = hi if d == 1 else (lo if d == -1 else -1)
    return pi[:m], pt[:m], pc[:m], d, prov


def zigzag(x, r):
    pi, pt, pc, d, prov = _zigzag(np.ascontiguousarray(x, dtype=np.float64), float(r))
    return np.asarray(pi), np.asarray(pt), np.asarray(pc), int(d), int(prov)


# ------------------------------------------------------------------------------------------------- detector
def geometry(iS1, iT1, iH, iT2, iS2, vS1, vT1, vH, vT2, vS2):
    """The plan's geometry in top orientation (y = sign x). Returns (ok, checks, details, slope, head)."""
    slope = (vT2 - vT1) / float(iT2 - iT1)

    def nl(j):
        return vT1 + slope * (j - iT1)
    head = vH - nl(iH)
    left, right = iH - iS1, iS2 - iH
    tol = SHOULDER_TOL * (vH - nl(iS2))
    rise = abs(nl(iS2) - nl(iS1))
    ratio = right / float(left) if left > 0 else float("inf")
    details = {
        "headAboveShoulders": {"pass": bool(vH > vS1 and vH > vS2), "headMinusS1": round(vH - vS1, 4), "headMinusS2": round(vH - vS2, 4)},
        "headAboveNeckline": {"pass": bool(head > 0), "headHeight": round(head, 4)},
        "shouldersAboveNeckline": {"pass": bool(vS1 > nl(iS1) and vS2 > nl(iS2)), "S1aboveNeckline": round(vS1 - nl(iS1), 4), "S2aboveNeckline": round(vS2 - nl(iS2), 4)},
        "shoulderTolerance": {"pass": bool(abs(vS1 - vS2) <= tol), "shoulderGap": round(abs(vS1 - vS2), 4), "limit": round(tol, 4)},
        "necklineRise": {"pass": bool(head > 0 and rise <= NECK_RISE * head), "rise": round(rise, 4), "limit": round(NECK_RISE * head, 4)},
        "spanRatio": {"pass": bool(SPAN_LO <= ratio <= SPAN_HI), "rightOverLeft": round(ratio, 3), "limits": [round(SPAN_LO, 3), SPAN_HI]},
    }
    checks = {k: v["pass"] for k, v in details.items()}
    return all(checks.values()), checks, details, slope, head


def margin_text(name, dd):
    if name == "necklineRise":
        return f"neckline rise {dd['rise']} vs {dd['limit']} allowed"
    if name == "shoulderTolerance":
        return f"shoulder gap {dd['shoulderGap']} vs {dd['limit']} allowed"
    if name == "headAboveShoulders":
        return f"head minus S1 {dd['headMinusS1']}, head minus S2 {dd['headMinusS2']}"
    if name == "spanRatio":
        return f"right/left span {dd['rightOverLeft']} outside {dd['limits'][0]}..{dd['limits'][1]}"
    if name == "shouldersAboveNeckline":
        return f"S1 above neckline {dd['S1aboveNeckline']}, S2 above neckline {dd['S2aboveNeckline']}"
    return f"head height {dd['headHeight']}"


def outcome(y, p, n):
    """What followed S2, read from closes after S2 only (top orientation)."""
    i, conf, head, vS2 = p["i"], p["conf"], p["head"], p["v"]["S2"]
    vT1, slope, iT1, iS2 = p["v"]["T1"], p["slope"], i["T1"], i["S2"]
    brk = fail = comp = None
    last = min(n - 1, iS2 + EXPIRY_WEEKS)
    for j in range(iS2 + 1, last + 1):
        if y[j] < vT1 + slope * (j - iT1):
            brk = j
            break
        if y[j] > vS2:
            fail = j
            break
    tgt = None
    window_open = False
    if brk is not None:
        tgt = vT1 + slope * (brk - iT1) - head
        for j in range(brk, min(n - 1, brk + COMPLETION_WEEKS) + 1):
            if y[j] < tgt:
                comp = j
                break
        status = "completed" if comp is not None else "break"
        window_open = comp is None and (brk + COMPLETION_WEEKS > n - 1)
    elif fail is not None:
        status = "failed"
    elif iS2 + EXPIRY_WEEKS <= n - 1:
        status = "expired"
    else:
        status = "in-play"
    inplay = brk is None or brk > conf
    p.update(iBreak=brk, iFail=fail, iComp=comp, status=status, targetY=tgt, completionWindowOpen=bool(window_open),
             brokenAtConfirmation=bool(brk is not None and brk <= conf), inPlayAtConfirmation=bool(inplay))
    p["w"] = {"S1T1": i["T1"] - i["S1"], "S1H": i["H"] - i["S1"], "HS2": i["S2"] - i["H"], "HT2": i["T2"] - i["H"],
              "S1S2": i["S2"] - i["S1"], "S2Conf": conf - iS2,
              "S2Break": (None if brk is None else brk - iS2), "ConfBreak": (None if brk is None else brk - conf),
              "BreakTarget": (None if comp is None else comp - brk)}
    bw, tw, mw = {}, {}, {}
    for H in H_BREAK:
        observable = inplay and ((brk is not None) or (fail is not None and fail <= conf + H) or (conf + H <= n - 1))
        bw[H] = None if not observable else bool(brk is not None and brk - conf <= H)
        if (not inplay) or conf + H > n - 1:
            mw[H] = None
        else:
            mw[H] = bool(np.min(y[conf + 1:conf + H + 1]) <= y[conf] - head)
    for H in H_TARGET:
        observable = brk is not None and ((comp is not None) or (brk + H <= n - 1))
        tw[H] = None if not observable else bool(comp is not None and comp - brk <= H)
    p["breakWithin"], p["targetWithin"], p["moveWithin"] = bw, tw, mw


def build_pattern(x, zz, k, r, sign, provisional=False):
    """The five pivots starting at pivot k as a pattern dict (the fifth is the provisional extreme when provisional).
    Geometry is evaluated, not enforced, here; outcome() runs only for a confirmed S2."""
    pi, pt, pc, d, prov = zz
    y = sign * x
    n = len(x)
    idx = [int(v) for v in pi[k:k + 4]] + [int(prov) if provisional else int(pi[k + 4])]
    iS1, iT1, iH, iT2, iS2 = idx
    vS1, vT1, vH, vT2, vS2 = (float(y[j]) for j in idx)
    ok, checks, details, slope, head = geometry(iS1, iT1, iH, iT2, iS2, vS1, vT1, vH, vT2, vS2)
    p = {"i": {"S1": iS1, "T1": iT1, "H": iH, "T2": iT2, "S2": iS2}, "v": {"S1": vS1, "T1": vT1, "H": vH, "T2": vT2, "S2": vS2},
         "confT2": int(pc[k + 3]), "slope": slope, "head": head, "sign": sign, "kind": "top" if sign == 1 else "inverse", "r": r,
         "geometryOk": bool(ok), "checks": checks, "checkDetails": details, "s2Provisional": bool(provisional)}
    if provisional:
        p["confirmLevelY"] = vS2 - r
    else:
        p["conf"] = int(pc[k + 4])
        outcome(y, p, n)
    return p


def detect(x, zz, r, sign):
    """All patterns of one orientation (sign +1 top, -1 inverse) from confirmed pivots. No look-ahead."""
    pi, pt = zz[0], zz[1]
    pats = []
    for k in range(len(pi) - 4):
        if pt[k] != sign:
            continue
        p = build_pattern(x, zz, k, r, sign)
        if p["geometryOk"]:
            pats.append(p)
    return pats


def detect_series(x, r, dates, name, placebo=None, seed=None):
    zz = zigzag(x, r)
    recs = []
    for sign in (1, -1):
        for p in detect(x, zz, r, sign):
            t = dates[p["i"]["S2"]]
            p.update(series=name, placebo=placebo, seed=seed, s2date=t, era=era_of(t), pool=in_pool(name, t))
            recs.append(p)
    return recs, zz


def n_fail(p):
    return sum(1 for v in p["checks"].values() if not v)


def nearest_structure(x, zz, r, sign, lookback=NEAR_LOOKBACK):
    """Among the five-pivot windows of the expected orientation whose S2 (a confirmed pivot, or the provisional
    extreme) lies within the lookback, the one failing the fewest geometry checks (ties: the most recent). It is a
    detector pattern only when every check passes and S2 is confirmed."""
    pi, pt, pc, d, prov = zz
    n = len(x)
    cands = []
    for k in range(len(pi) - 4):
        if pt[k] == sign and n - 1 - int(pi[k + 4]) <= lookback:
            cands.append(build_pattern(x, zz, k, r, sign))
    if prov >= 0 and d == sign and len(pi) >= 4 and pt[-4] == sign:
        cands.append(build_pattern(x, zz, len(pi) - 4, r, sign, provisional=True))
    cands = [p for p in cands if p["checks"]["headAboveShoulders"]]   # without the head as the extreme it is no structure at all
    if not cands:
        return None
    return min(cands, key=lambda p: (n_fail(p), -p["i"]["S2"]))


def forming_stage(x, zz, r, sign, dates, w, space):
    """How much of S1 T1 H T2 S2 is confirmed at the data end in the expected orientation, and the provisional
    extreme that would be the next pivot."""
    pi, pt, pc, d, prov = zz
    names = ["S1", "T1", "H", "T2", "S2"]
    for k in (4, 3, 2, 1):
        if len(pi) >= k and pt[-k] == sign:
            conf = [{"pivot": names[j], "date": ds(dates[pi[-k + j]]), "level": round(float(w.values[pi[-k + j]]), 4)} for j in range(k)]
            out = {"confirmed": conf, "provisional": None}
            if prov >= 0:
                y = sign * x
                lvl = y[prov] + (-r if d == sign else r)   # the close that confirms the provisional extreme (in y)
                out["provisional"] = {"pivot": names[k], "date": ds(dates[prov]), "level": round(float(w.values[prov]), 4),
                                      "confirmsAtClose": round(float(from_space(sign * lvl, space)), 4)}
            if k == 4:
                out["note"] = "S1 T1 H T2 confirmed; the right shoulder is forming until S2 confirms"
            elif k == 3:
                out["note"] = "S1 T1 H confirmed; the right shoulder has not begun until T2 confirms"
            else:
                out["note"] = f"{k} of the five pivots confirmed"
            return out
    return None


def point_in_time_check(data, thresholds, n_cuts=6, seed=0):
    """Leakage self-check: on each series truncated at random weeks, every pattern confirmed by the cut must be the
    same five pivots with the same neckline as in the full run, and every outcome known by the cut (break, fail,
    completion) must agree. Returns {ok, tested, mismatches}."""
    rng = np.random.default_rng(seed)
    tested, mism = 0, []
    for name, d in data.items():
        x, dates = d["x"], d["weekly"].index
        n = len(x)
        for r in thresholds:
            full, _ = detect_series(x, r, dates, name)
            for cut in rng.integers(n // 3, n - 1, size=n_cuts):
                cut = int(cut)
                part, _ = detect_series(x[:cut + 1], r, dates[:cut + 1], name)
                key = lambda p: (p["kind"], tuple(p["i"].values()))
                fk = {key(p): p for p in full if p["conf"] <= cut}
                pk = {key(p): p for p in part}
                tested += 1
                if set(fk) != set(pk):
                    mism.append({"series": name, "r": r, "cut": ds(dates[cut]), "what": "pattern set differs"})
                    continue
                for k, p in pk.items():
                    q = fk[k]
                    for field in ("iBreak", "iFail", "iComp"):
                        a, b = p[field], q[field]
                        if (a is not None and a != b) or (b is not None and b <= cut and a != b):
                            mism.append({"series": name, "r": r, "cut": ds(dates[cut]), "what": f"{field} differs for {k[0]} S2 {ds(dates[k[1][4]])}"})
                    if abs(p["slope"] - q["slope"]) > 1e-12 or abs(p["head"] - q["head"]) > 1e-12:
                        mism.append({"series": name, "r": r, "cut": ds(dates[cut]), "what": "neckline differs"})
    return {"ok": bool(not mism), "tested": tested, "mismatches": mism[:10],
            "rule": "patterns confirmed by the cut and outcomes known by the cut are identical on the truncated and the full series"}


def fixed_level_events(p, x):
    """Beside the plan's break (a diagnostic, it changes no pre-registered quantity): the equal-move event of plan [2]
    for the break, a close beyond the neckline LEVEL fixed at the in-play week within H weeks of it, not censored by a
    close beyond S2. None when the pattern was not in play at confirmation, or the window is still open without it."""
    y = p["sign"] * x
    n = len(y)
    conf = p["conf"]
    lvl = p["v"]["T1"] + p["slope"] * (conf - p["i"]["T1"])
    p["necklineAtInPlayY"] = float(lvl)
    p["fixedBreakWithin"] = {}
    for H in H_BREAK:
        if not p["inPlayAtConfirmation"]:
            p["fixedBreakWithin"][H] = None
            continue
        seg = y[conf + 1:min(n, conf + H + 1)]
        if len(seg) and float(seg.min()) < lvl:
            p["fixedBreakWithin"][H] = True
        else:
            p["fixedBreakWithin"][H] = False if conf + H <= n - 1 else None


# ------------------------------------------------------------------------------------------------- placebos
def placebo_job(job):
    """One surrogate series (built from the series' full weekly history, which is the intended null) run through
    the same detector at every threshold. job = (name, kind, seed, x, dates, thresholds[, tag[, space]]).
    Returns (pattern records, {name, kind, seed, weeks, pivots per r, tag, sameMarginal, native range})."""
    name, kind, seed, x, dates_ns, thresholds = job[:6]
    tag = job[6] if len(job) > 6 else None
    space = job[7] if len(job) > 7 else None
    rng = np.random.default_rng(seed)
    xs = iaaft(x, rng, IAAFT_IT) if kind == "iaaft" else matched_rw(x, rng, RW_BLOCK_WEEKS, "W")
    dates = pd.DatetimeIndex(dates_ns)
    out = []
    meta = {"name": name, "kind": kind, "seed": seed, "weeks": int(len(xs)), "pivots": {}, "tag": tag,
            "sameMarginal": bool(len(xs) == len(x) and np.allclose(np.sort(xs), np.sort(x)))}
    if space is not None:
        nat = from_space(xs, space)
        meta["nativeMin"], meta["nativeMax"] = float(nat.min()), float(nat.max())
    for r in thresholds:
        recs, zz = detect_series(xs, r, dates, name, placebo=kind, seed=seed)
        for p in recs:
            fixed_level_events(p, xs)
            p["tag"] = tag
        out += recs
        meta["pivots"][r] = int(len(zz[0]))
    return out, meta


# ------------------------------------------------------------------------------------------------- statistics
def mw_one_sided(a, b):
    """One-sided Mann-Whitney, H1: a stochastically smaller than b. Normal approximation with tie correction and
    continuity correction. Returns (p, P(a < b))."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    n1, n2 = len(a), len(b)
    if n1 < 3 or n2 < 3:
        return None, None
    allv = np.concatenate([a, b])
    ranks = pd.Series(allv).rank().values
    U1 = ranks[:n1].sum() - n1 * (n1 + 1) / 2.0      # pairs a > b (+ half the ties)
    U = n1 * n2 - U1                                   # pairs a < b (+ half the ties)
    N = n1 + n2
    _, counts = np.unique(allv, return_counts=True)
    tie = float((counts.astype(float) ** 3 - counts).sum())
    var = n1 * n2 / 12.0 * ((N + 1) - tie / (N * (N - 1)))
    prob = float(U / (n1 * n2))
    if var <= 0:
        return 1.0, prob
    z = (U - n1 * n2 / 2.0 - 0.5) / math.sqrt(var)
    return float(0.5 * math.erfc(z / math.sqrt(2.0))), prob


def mw_parts(a, b):
    """The pieces of the one-sided Mann-Whitney (H1: a smaller than b) for a stratified test:
    (U - n1 n2 / 2 with U the pairs a < b, the tie-corrected variance, N, P(a < b))."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    n1, n2 = len(a), len(b)
    allv = np.concatenate([a, b])
    ranks = pd.Series(allv).rank().values
    U1 = ranks[:n1].sum() - n1 * (n1 + 1) / 2.0
    U = n1 * n2 - U1
    N = n1 + n2
    _, counts = np.unique(allv, return_counts=True)
    tie = float((counts.astype(float) ** 3 - counts).sum())
    var = n1 * n2 / 12.0 * ((N + 1) - tie / (N * (N - 1)))
    return U - n1 * n2 / 2.0, var, N, float(U / (n1 * n2))


def mw_z(a, b):
    """The z score behind mw_one_sided (continuity corrected), or None when a group is too small."""
    if len(a) < 3 or len(b) < 3:
        return None
    d, var, _, _ = mw_parts(a, b)
    if var <= 0:
        return None
    return float((d - 0.5) / math.sqrt(var))


def stratified_mw(groups, min_a=2, min_b=5):
    """Stratified one-sided Mann-Whitney (a smaller than b within each stratum), van Elteren weights 1/(N+1).
    groups = [(a values, b values)] per stratum; strata with too few rows are skipped. Returns z, p, the
    real-row-weighted P(a < b) within the strata used, the real rows used and the strata used."""
    num = den = pw = 0.0
    used = strata = 0
    for a, b in groups:
        if len(a) < min_a or len(b) < min_b:
            continue
        d, var, N, prob = mw_parts(a, b)
        if var <= 0:
            continue
        w = 1.0 / (N + 1)
        num += w * d
        den += w * w * var
        used += len(a)
        strata += 1
        pw += len(a) * prob
    if den <= 0 or strata == 0:
        return {"z": None, "p": None, "probRealSmaller": None, "nRealUsed": used, "nStrata": strata}
    z = num / math.sqrt(den)
    return {"z": round(float(z), 3), "p": round(float(0.5 * math.erfc(z / math.sqrt(2.0))), 4), "probRealSmaller": round(pw / used, 3),
            "nRealUsed": used, "nStrata": strata}


# S1 -> S2 span bins (weeks) per threshold for the span-stratified test; other thresholds fall back to quintiles
SPAN_EDGES = {0.08: (0, 12, 16, 20, 26, 40, 10 ** 9), 0.15: (0, 20, 30, 45, 60, 80, 10 ** 9)}


def span_edges(r, rows):
    if r in SPAN_EDGES:
        return SPAN_EDGES[r]
    v = np.array([x["p"]["w"]["S1S2"] for x in rows if x["r"] == r], float)
    if len(v) < 10:
        return (0, 10 ** 9)
    q = np.unique(np.quantile(v, [0.2, 0.4, 0.6, 0.8]))
    return tuple([0] + [float(e) for e in q] + [10 ** 9])


def scale_diagnostics(rr, pr, thresholds, law=None):
    """Not pre-registered; reported beside the plan's raw-week pooled test, never in its place. The placebo
    patterns are shorter than the real ones (fewer weeks S1 -> S2 at the same threshold), and a timing error in
    weeks grows with the pattern's span, so the raw-week test mixes 'the law has no skill' with 'real patterns are
    slower than the surrogates'. Three ways to hold the time scale fixed: (a) the rank test stratified by
    threshold x S1 -> S2 span bin, (b) the scale-free errors |error| / predicted weeks and |error| / span S1 -> S2,
    (c) the raw-week test per placebo kind and the equal-weight combination of the two kinds (IAAFT rows are the
    choppier family and the larger share of the placebo pool). For T2 the scale is S1 -> H, the law's input known when
    its date is issued: S1 -> S2 = S1 -> H + H -> S2 contains T2's own outcome, so it neither defines T2's strata nor
    divides its errors."""
    t2 = law == "T2"
    out = {}
    if t2:
        def scale(x):
            return x["pred"]

        def edges(r, qs):
            v = np.array([scale(x) for x in rr + pr if x["r"] == r], float)
            if len(v) < 10:
                return (0, 10 ** 9)
            return tuple([0] + [float(e) for e in np.unique(np.quantile(v, qs))] + [10 ** 9])
    else:
        def scale(x):
            return x["p"]["w"]["S1S2"]
    groups = []
    for r in thresholds:
        e = edges(r, [0.2, 0.4, 0.6, 0.8]) if t2 else span_edges(r, rr + pr)
        for lo, hi in zip(e[:-1], e[1:]):
            groups.append(([abs(x["err"]) for x in rr if x["r"] == r and lo <= scale(x) < hi],
                           [abs(x["err"]) for x in pr if x["r"] == r and lo <= scale(x) < hi]))
    st = stratified_mw(groups)
    st["nReal"] = len(rr)
    if t2:
        st["strata"] = ("threshold x quintile of the pooled real + placebo S1->H (T2's input; S1->S2 contains its outcome); inner edges (weeks): "
                        + "; ".join(f"r={r}: {[round(q, 1) for q in list(edges(r, [0.2, 0.4, 0.6, 0.8]))[1:-1]]}" for r in thresholds))
    else:
        st["strata"] = "threshold x S1->S2 span bin; edges (weeks): " + "; ".join(f"r={r}: {list(span_edges(r, rr + pr))[:-1]}" for r in thresholds)
    st["test"] = "stratified one-sided Mann-Whitney (van Elteren weights), real |error| < placebo |error| within strata of the same time scale"
    out["spanStratified"] = st
    groups, edges_txt = [], []
    for r in thresholds:
        v = np.array([scale(x) for x in rr + pr if x["r"] == r], float)
        if len(v) < 8:
            continue
        e = [0.0] + [float(q) for q in np.unique(np.quantile(v, [0.25, 0.5, 0.75]))] + [1e9]
        edges_txt.append(f"r={r}: {[round(q, 1) for q in e[1:-1]]}")
        for lo, hi in zip(e[:-1], e[1:]):
            groups.append(([abs(x["err"]) for x in rr if x["r"] == r and lo <= scale(x) < hi],
                           [abs(x["err"]) for x in pr if x["r"] == r and lo <= scale(x) < hi]))
    sq = stratified_mw(groups)
    sq["nReal"] = len(rr)
    scale_label = "S1->H (T2's input)" if t2 else "S1->S2 span"
    sq["strata"] = f"threshold x quartile of the pooled real + placebo {scale_label}; inner edges (weeks): " + "; ".join(edges_txt)
    sq["test"] = st["test"]
    out["spanStratifiedQuartiles"] = sq
    for key, f, what in (("absErrorOverPredicted", lambda x: abs(x["err"]) / max(x["pred"], 1.0), "|error| / predicted weeks (the law's own scale)"),
                         ("absErrorOverSpan", lambda x: abs(x["err"]) / max(x["p"]["w"]["S1S2"], 1.0), "|error| / weeks S1->S2 (the pattern's span)")):
        if t2 and key == "absErrorOverSpan":
            out[key] = {"what": what, "p": None, "nReal": len(rr),
                        "note": ("not computed for T2: S1->S2 = predicted + actual, so the divisor contains T2's outcome; absErrorOverPredicted "
                                 "(|error| / S1->H) is T2's scale-free test")}
            continue
        a, b = [f(x) for x in rr], [f(x) for x in pr]
        p, prob = mw_one_sided(a, b)
        block = {"what": what, "realMedian": med(a), "placeboMedian": med(b), "p": (None if p is None else round(p, 4)),
                 "probRealSmaller": (None if prob is None else round(prob, 3)), "nReal": len(a), "nPlacebo": len(b), "perThreshold": {}}
        for r in thresholds:
            ar, br = [f(x) for x in rr if x["r"] == r], [f(x) for x in pr if x["r"] == r]
            pt, pbt = mw_one_sided(ar, br)
            block["perThreshold"][str(r)] = {"nReal": len(ar), "realMedian": med(ar), "placeboMedian": med(br), "p": (None if pt is None else round(pt, 4)),
                                             "probRealSmaller": (None if pbt is None else round(pbt, 3))}
        out[key] = block
    kinds, zs, nk = {}, [], []
    a = [abs(x["err"]) for x in rr]
    for k in ("iaaft", "rw"):
        b = [abs(x["err"]) for x in pr if x["placebo"] == k]
        p, prob = mw_one_sided(a, b)
        z = mw_z(a, b)
        kinds[k] = {"nPlacebo": len(b), "placeboMedianAbs": med(b), "p": (None if p is None else round(p, 4)), "probRealSmaller": (None if prob is None else round(prob, 3)),
                    "shareOfPlaceboRows": (None if not pr else round(len(b) / len(pr), 3))}
        if z is not None:
            zs.append(z)
            nk.append(len(b))
    eq = None
    if len(zs) == 2:
        # both kinds are ranked against the same real errors, so under H0 the two Mann-Whitney z scores correlate:
        # rho = sqrt(nA nB / ((n1 + nA + 1)(n1 + nB + 1))) (the shared real rows), and the combination is scaled by its sd
        n1 = len(a)
        rho = math.sqrt(nk[0] * nk[1] / ((n1 + nk[0] + 1.0) * (n1 + nk[1] + 1.0)))
        zq = sum(zs) / math.sqrt(2.0 + 2.0 * rho)
        eq = {"z": round(zq, 3), "p": round(float(0.5 * math.erfc(zq / math.sqrt(2.0))), 4), "zCorrelationUnderH0": round(rho, 4),
              "rule": ("the two kinds' z scores combined with equal weight, (z1 + z2) / sqrt(2 + 2 rho): both share the real rows, so they correlate "
                       "with rho = sqrt(nA nB / ((n1 + nA + 1)(n1 + nB + 1))) under H0")}
    out["rawWeeksByPlaceboKind"] = kinds
    out["equalKindWeight"] = eq
    return out


def med(v):
    v = [x for x in v if x is not None]
    return None if len(v) == 0 else round(float(np.median(v)), 2)


def summ(errs):
    """Summary of a list of signed errors (weeks)."""
    e = np.asarray(errs, float)
    if len(e) == 0:
        return {"n": 0}
    a = np.abs(e)
    return {"n": int(len(e)), "medianAbs": round(float(np.median(a)), 2), "meanAbs": round(float(a.mean()), 2),
            "absIQR": [round(float(np.quantile(a, 0.25)), 2), round(float(np.quantile(a, 0.75)), 2)],
            "signedMedian": round(float(np.median(e)), 2), "signedIQR": [round(float(np.quantile(e, 0.25)), 2), round(float(np.quantile(e, 0.75)), 2)],
            "withinTwoWeeks": round(float((a <= 2).mean()), 3), "withinFourWeeks": round(float((a <= 4).mean()), 3)}


def law_rows(recs, dates_of):
    """One row per (pattern, law) with a known actual: prediction, actual, signed error, and the dates at which the
    prediction was made and the actual became known (for the expanding baseline)."""
    rows = []
    for p in recs:
        w, d = p["w"], dates_of[p["series"]]
        for law in LAWS:
            if law == "T1":
                pred, act, tp, to = w["S1T1"], w["S2Break"], p["conf"], p["iBreak"]
            elif law == "T2":
                pred, act, tp, to = w["S1H"], w["HS2"], p["confT2"], p["conf"]
            elif law == "T3":
                pred, act, tp, to = w["HT2"], w["BreakTarget"], p["iBreak"], p["iComp"]
            else:
                pred, act, tp, to = 0.5 * w["S1S2"], w["BreakTarget"], p["iBreak"], p["iComp"]
            if act is None:
                continue
            rows.append({"law": law, "p": p, "pred": float(pred), "act": float(act), "err": float(pred - act),
                         "tPred": d[tp], "tOut": d[to], "series": p["series"], "r": p["r"], "era": p["era"], "pool": p["pool"],
                         "placebo": p["placebo"], "kind": p["kind"]})
    return rows


def add_baselines(real_rows):
    """Expanding median of the actual duration over pool patterns (same law, same threshold, all series) whose outcome
    was known before this pattern's prediction was made. Needs BASELINE_MIN prior patterns."""
    for law in LAWS:
        for r in sorted(set(x["r"] for x in real_rows)):
            hist = sorted([x for x in real_rows if x["law"] == law and x["r"] == r and x["pool"]], key=lambda x: x["tOut"])
            hist_t = np.array([x["tOut"].value for x in hist])
            hist_a = np.array([x["act"] for x in hist])
            for x in [x for x in real_rows if x["law"] == law and x["r"] == r]:
                k = int(np.searchsorted(hist_t, x["tPred"].value, side="left"))   # outcomes strictly before tPred
                if k >= BASELINE_MIN:
                    x["base"] = float(np.median(hist_a[:k]))
                    x["baseN"] = k
                    x["errBase"] = x["base"] - x["act"]
                else:
                    x["base"], x["baseN"], x["errBase"] = None, k, None


def current_baseline(real_rows, law, r):
    """The expanding median as of the data end (all pool outcomes known to date)."""
    hist = [x for x in real_rows if x["law"] == law and x["r"] == r and x["pool"]]
    if len(hist) < BASELINE_MIN:
        return None
    return {"weeks": round(float(np.median([x["act"] for x in hist])), 1), "nPatterns": len(hist)}


def law_report(law, real_rows, plac_rows, thresholds, scale=True):
    """The pre-registered block of one law (plan [2] and [4]); scale=True appends the time-scale diagnostics."""
    rr = [x for x in real_rows if x["law"] == law]
    pr = [x for x in plac_rows if x["law"] == law]
    pool = [x for x in rr if x["pool"]]
    ppool = [x for x in pr if x["pool"]]
    withb = [x for x in pool if x["errBase"] is not None]
    p_pooled, prob = mw_one_sided([abs(x["err"]) for x in pool], [abs(x["err"]) for x in ppool])
    rep = {"law": law, "name": LAW_TEXT[law]["name"], "predicts": LAW_TEXT[law]["predicts"], "from": LAW_TEXT[law]["from"],
           "nRealAll": len(rr), "nRealPool": len(pool), "nRealWithBaseline": len(withb),
           "real": summ([x["err"] for x in pool]),
           "realOnBaselineSet": summ([x["err"] for x in withb]),
           "baseline": summ([x["errBase"] for x in withb]),
           "improvementOverBaselineWeeks": (None if not withb else round(float(np.median([abs(x["errBase"]) for x in withb]) - np.median([abs(x["err"]) for x in withb])), 2)),
           "placebo": summ([x["err"] for x in ppool]),
           "placeboByKind": {k: summ([x["err"] for x in ppool if x["placebo"] == k]) for k in ("iaaft", "rw")},
           "pooledTest": {"test": "one-sided Mann-Whitney, real |error| < placebo |error|", "p": (None if p_pooled is None else round(p_pooled, 4)),
                          "probRealSmaller": (None if prob is None else round(prob, 3)), "nReal": len(pool), "nPlacebo": len(ppool)},
           "thresholdMix": {"realShareAtSmallR": (None if not pool else round(float(np.mean([x["r"] == min(thresholds) for x in pool])), 3)),
                            "placeboShareAtSmallR": (None if not ppool else round(float(np.mean([x["r"] == min(thresholds) for x in ppool])), 3))}}
    per_t = {}
    for r in thresholds:
        a = [x for x in pool if x["r"] == r]
        b = [x for x in ppool if x["r"] == r]
        wb = [x for x in a if x["errBase"] is not None]
        p, pb = mw_one_sided([abs(x["err"]) for x in a], [abs(x["err"]) for x in b])
        per_t[str(r)] = {"nReal": len(a), "medianAbs": med([abs(x["err"]) for x in a]), "baselineMedianAbs": med([abs(x["errBase"]) for x in wb]),
                         "nWithBaseline": len(wb), "placeboMedianAbs": med([abs(x["err"]) for x in b]), "nPlacebo": len(b),
                         "p": (None if p is None else round(p, 4)), "probRealSmaller": (None if pb is None else round(pb, 3))}
    rep["perThreshold"] = per_t
    per_s = {}
    for s in sorted(set(x["series"] for x in rr)):
        a = [x for x in rr if x["series"] == s]
        b = [x for x in pr if x["series"] == s]
        wb = [x for x in a if x["errBase"] is not None]
        p, pb = mw_one_sided([abs(x["err"]) for x in a], [abs(x["err"]) for x in b])
        per_s[s] = {"nReal": len(a), "nInPool": sum(1 for x in a if x["pool"]), "medianAbs": med([abs(x["err"]) for x in a]),
                    "baselineMedianAbs": med([abs(x["errBase"]) for x in wb]), "placeboMedianAbs": med([abs(x["err"]) for x in b]), "nPlacebo": len(b),
                    "p": (None if p is None else round(p, 4)), "probRealSmaller": (None if pb is None else round(pb, 3))}
    rep["perSeries"] = per_s
    per_k = {}
    for k in ("top", "inverse"):
        a = [x for x in pool if x["kind"] == k]
        b = [x for x in ppool if x["kind"] == k]
        p, pb = mw_one_sided([abs(x["err"]) for x in a], [abs(x["err"]) for x in b])
        per_k[k] = {"nReal": len(a), "medianAbs": med([abs(x["err"]) for x in a]), "placeboMedianAbs": med([abs(x["err"]) for x in b]), "p": (None if p is None else round(p, 4))}
    rep["perKind"] = per_k
    per_e = {}
    holds = 0
    for name, _, _ in ERAS:
        a = [x for x in withb if x["era"] == name]
        allera = [x for x in pool if x["era"] == name]
        b = [x for x in ppool if x["era"] == name]
        ml, mb, mp = med([abs(x["err"]) for x in a]), med([abs(x["errBase"]) for x in a]), med([abs(x["err"]) for x in b])
        direction = bool(len(a) >= 3 and ml is not None and mb is not None and ml < mb)
        holds += int(direction)
        per_e[name] = {"nWithBaseline": len(a), "nReal": len(allera), "medianAbsLaw": ml, "medianAbsBaseline": mb, "placeboMedianAbs": mp,
                       "lawBeatsBaseline": direction, "lawBeatsPlacebo": (bool(ml < mp) if (ml is not None and mp is not None) else None)}
    rep["perEra"] = per_e
    rep["erasWhereDirectionHolds"] = holds
    # criteria (plan [4])
    fails = []
    imp = rep["improvementOverBaselineWeeks"]
    nb = len(withb)
    if nb < 10 or imp is None or imp < 2:
        fails.append(f"(i) median |error| {rep['realOnBaselineSet'].get('medianAbs')}w vs baseline {rep['baseline'].get('medianAbs')}w on n={nb} "
                     f"(needs >= 2 weeks better on >= 10 pooled patterns; improvement {imp})")
    if p_pooled is None or p_pooled >= 0.05:
        fails.append(f"(ii) pooled one-sided rank test p={None if p_pooled is None else round(p_pooled, 3)} (needs p < 0.05)")
    if holds < 2:
        fails.append(f"(iii) direction holds in {holds} of 3 eras (needs >= 2)")
    rep["criteria"] = {"i": {"pass": bool(nb >= 10 and imp is not None and imp >= 2), "n": nb, "improvementWeeks": imp},
                       "ii": {"pass": bool(p_pooled is not None and p_pooled < 0.05), "p": (None if p_pooled is None else round(p_pooled, 4))},
                       "iii": {"pass": bool(holds >= 2), "erasHolding": holds, "rule": "law median |error| < baseline median |error| in the era, on >= 3 patterns with a baseline"}}
    rep["verdict"] = "supported" if not fails else "not supported: " + "; ".join(fails)
    if scale:
        rep["scaleDiagnostics"] = scale_diagnostics(pool, ppool, thresholds, law)
    return rep


def leakage_audit(law, real_rows):
    """What the scored rows are: rows from patterns whose S2-confirming close was itself the neckline break (or came
    after it) were never in play under plan [1]. Counts and the note for laws.<law>."""
    pool = [x for x in real_rows if x["law"] == law and x["pool"]]
    bac = [x for x in pool if x["p"]["brokenAtConfirmation"]]
    same = sum(1 for x in bac if x["p"]["iBreak"] == x["p"]["conf"])
    before = len(bac) - same
    out = {"rowsFromPatternsBrokenAtConfirmation": len(bac), "ofWhichBreakInTheConfirmationWeek": same, "ofWhichBreakBeforeConfirmation": before,
           "rowsFromPatternsInPlayAtConfirmation": len(pool) - len(bac), "nRealPool": len(pool)}
    when = (f"{same} with the break in the confirmation week itself" + (f", {before} with it earlier" if before else ", none earlier"))
    if law == "T1":
        out["note"] = (f"{len(bac)} of {len(pool)} pooled T1 rows come from patterns broken at confirmation ({when}). T1 is dated at the "
                       "confirmation week, so for these rows the actual S2 -> break had already printed when the prediction was made; under plan [1] "
                       "the patterns were never in play. The plan scores every completed pattern, so they stay in this pre-registered block; "
                       "inPlayAtConfirmation repeats the whole test on the usable patterns (its baseline is the expanding median over in-play "
                       "patterns, the base rate a forecaster who knows the pattern is unbroken would use), and the current-pattern bands come from it.")
    elif law == "T2":
        out["note"] = (f"{len(bac)} of {len(pool)} pooled rows come from patterns broken at confirmation; T2 is dated at T2's confirmation and its "
                       "actual at S2's, so those rows are not retrodictions for T2, but the whole T2 set is conditioned on the later S2 confirmation "
                       "and geometry (see selectionNote): T2 is descriptive symmetry on completed patterns, not a point-in-time forecast.")
    else:
        out["note"] = (f"{len(bac)} of {len(pool)} pooled {law} rows come from patterns broken at confirmation ({when}). {law} is dated at the "
                       "break, which for these rows is not after the week S2 confirmed, so the prediction was issued before the pattern was ever "
                       "in play. They stay in this pre-registered block; inPlayAtConfirmation repeats the test without them.")
    return out


# ------------------------------------------------------------------------------------------------- rates
def rate(vals):
    v = [bool(x) for x in vals if x is not None]
    return {"n": len(v), "rate": (round(float(np.mean(v)), 3) if v else None)}


def add_base_rates(recs, data):
    """Matched base rate: for a pattern in play at week t with head height h, the share of weeks s of the same series
    and era (all weeks, not only pattern weeks) where the series moved by h in the pattern's direction within H."""
    cache = {}
    for p in recs:
        name, sign = p["series"], p["sign"]
        y = sign * data[name]["x"]
        dates = data[name]["weekly"].index
        if (name, sign) not in cache:
            fm = {}
            for H in H_BREAK:
                s = pd.Series(y)
                fm[H] = s[::-1].rolling(H, min_periods=H).min()[::-1].shift(-1).values   # min(y[s+1..s+H])
            cache[(name, sign)] = (fm, np.array([era_of(t) for t in dates]))
        fm, eras = cache[(name, sign)]
        p["baseRate"] = {}
        for H in H_BREAK:
            m = (eras == p["era"]) & np.isfinite(fm[H])
            if m.sum() < 20 or p["moveWithin"][H] is None:
                p["baseRate"][H] = None
            else:
                p["baseRate"][H] = round(float(np.mean(fm[H][m] <= y[m] - p["head"])), 4)


def rates_report(real, plac, thresholds):
    def block(rs, with_base):
        ip = [p for p in rs if p["inPlayAtConfirmation"]]
        brk = [p for p in rs if p["iBreak"] is not None]
        out = {"nPatterns": len(rs), "nInPlayAtConfirmation": len(ip), "nBrokenAtConfirmation": len(rs) - len(ip), "nBreaks": len(brk),
               "status": {s: sum(1 for p in rs if p["status"] == s) for s in ("in-play", "break", "completed", "failed", "expired")},
               "breakWithinWeeksOfInPlay": {str(H): rate([p["breakWithin"][H] for p in ip]) for H in H_BREAK},
               "targetWithinWeeksOfBreak": {str(H): rate([p["targetWithin"][H] for p in brk]) for H in H_TARGET},
               "headHeightMoveWithinWeeksOfInPlay": {str(H): rate([p["moveWithin"][H] for p in ip]) for H in H_BREAK}}
        if with_base:
            mb = {}
            for H in H_BREAK:
                v = [p["baseRate"][H] for p in ip if p["moveWithin"][H] is not None and p.get("baseRate", {}).get(H) is not None]
                mb[str(H)] = {"n": len(v), "rate": (round(float(np.mean(v)), 3) if v else None)}
            out["matchedBaseRateSameSeriesEra"] = mb
            out["medianWeeksS2ToBreak"] = med([p["w"]["S2Break"] for p in brk])
            out["medianWeeksBreakToTarget"] = med([p["w"]["BreakTarget"] for p in rs if p["iComp"] is not None])
            out["medianWeeksS2ToConfirmation"] = med([p["w"]["S2Conf"] for p in rs])
        return out
    rp = [p for p in real if p["pool"]]
    pp = [p for p in plac if p["pool"]]
    rep = {"definition": {"breakWithinWeeksOfInPlay": "share of patterns in play at confirmation whose first close beyond the neckline came within H weeks of the in-play week",
                          "targetWithinWeeksOfBreak": "share of breaks whose first close beyond the measured-move target came within H weeks of the break",
                          "headHeightMoveWithinWeeksOfInPlay": "share of in-play patterns where the series moved one head height in the pattern's direction within H weeks of the in-play week",
                          "matchedBaseRateSameSeriesEra": ("the same move-by-head-height chance from every week of the same series and era, averaged over the same "
                                                           "patterns; an IN-SAMPLE era rate (the era's weeks include weeks after the in-play week and the "
                                                           "pattern's own weeks), descriptive, not a point-in-time base rate: matchedEqualMove carries the "
                                                           "variants without the pattern's own weeks and the expanding (point-in-time) one"),
                          "breakWithinWeeksOfInPlayCaveat": ("the sloped-neckline break, censored by fails (a close beyond S2 ends the pattern): it is "
                                                             "neither an equal-move base-rate comparison nor comparable with the raw placebo rate (placebo "
                                                             "patterns are shorter); see matchedEqualMove and spanMatchedPlacebo")},
           "real": block(rp, True), "placebo": block(pp, False),
           "perThreshold": {str(r): {"real": block([p for p in rp if p["r"] == r], True), "placebo": block([p for p in pp if p["r"] == r], False)} for r in thresholds},
           "perKind": {k: {"real": block([p for p in rp if p["kind"] == k], True), "placebo": block([p for p in pp if p["kind"] == k], False)} for k in ("top", "inverse")},
           "perSeries": {s: block([p for p in real if p["series"] == s], True) for s in sorted(set(p["series"] for p in real))}}
    return rep


# ------------------------------------------------------------------------------------------------- diagnostics beside the plan
# Nothing below changes a pre-registered number: each block repeats or re-reads the plan's test on a stated subset, time
# scale or reference and is reported next to it, never in its place.
LOW_SHARE = 1.0                 # % share: logit space turns small moves below this level into large reversals
CLUSTER_S2_WEEKS = 8            # near-copy patterns: S2 within 8 weeks of each other ...
CLUSTER_OVERLAP = 0.5           # ... and S1..S2 spans overlapping by >= 50% (intersection over union)
MIRROR_RHO = -0.7               # opposite-kind near-copies on series pairs whose weekly changes correlate below this (GROUP_RHO mirrored)
MIRROR_RHO_ALT = -0.8           # the stricter mirror rule, reported beside as a sensitivity
GROUP_RHO = 0.7                 # |rho| at or above which two series are counted as one history
SWEEP_R = (0.05, 0.06, 0.07, 0.08, 0.10, 0.12, 0.15, 0.20)
NOISE_Q = 0.95
NOISE_DRAWS = 200               # n-matched subsamples per noise universe (criteria (i) and (iii) on noise)
NOISE_SEED = 20261102
BAND_MIN_N = 8                  # a current-pattern date band needs at least this many historical errors
BASE_VARIANTS = ("eraInSample", "eraExcludingOwnWeeks", "expandingPointInTime")
SERIES_ORDER = {n: k for k, n in enumerate(SERIES)}


def _future_min(y, H):
    """min(y[s+1..s+H]) per week s; NaN while the window is incomplete."""
    s = pd.Series(y)
    return s[::-1].rolling(H, min_periods=H).min()[::-1].shift(-1).values


def _base_rate(y, fm, ok, move, strict):
    m = ok & np.isfinite(fm)
    if m.sum() < 20:
        return None
    hit = (fm[m] < y[m] - move) if strict else (fm[m] <= y[m] - move)
    return float(np.mean(hit))


def add_matched_bases(recs, data):
    """Per real pattern, the base rate of an equal move over the same horizon in the same series (plan [2]), three ways:
    eraInSample (every week of the same era, the module's original rule), eraExcludingOwnWeeks (the same without the
    pattern's own weeks S1 .. anchor + H, the plan's 'without a pattern') and expandingPointInTime (weeks of the same
    series whose H-week window had closed by the anchor week). Moves: the fixed-level neckline break (in-play close minus
    the neckline at the in-play week; anchor = in-play week), the head height (anchor = in-play week) and the target
    (break close minus target; anchor = break week)."""
    cache = {}
    for p in recs:
        name, sign = p["series"], p["sign"]
        y = sign * data[name]["x"]
        n = len(y)
        if (name, sign) not in cache:
            cache[(name, sign)] = ({H: _future_min(y, H) for H in sorted(set(H_BREAK + H_TARGET))},
                                   np.array([era_of(t) for t in data[name]["weekly"].index]))
        fm, eras = cache[(name, sign)]
        idx = np.arange(n)
        era_ok = eras == p["era"]

        def three(H, move, strict, anchor):
            own = (idx >= p["i"]["S1"]) & (idx <= anchor + H)
            return {"eraInSample": _base_rate(y, fm[H], era_ok, move, strict),
                    "eraExcludingOwnWeeks": _base_rate(y, fm[H], era_ok & ~own, move, strict),
                    "expandingPointInTime": _base_rate(y, fm[H], idx + H <= anchor, move, strict)}
        mb = {"fixedBreak": {}, "headHeight": {}, "target": {}}
        if p["inPlayAtConfirmation"]:
            for H in H_BREAK:
                mb["fixedBreak"][H] = three(H, y[p["conf"]] - p["necklineAtInPlayY"], True, p["conf"])
                mb["headHeight"][H] = three(H, p["head"], False, p["conf"])
        if p["iBreak"] is not None:
            for H in H_TARGET:
                mb["target"][H] = three(H, y[p["iBreak"]] - p["targetY"], True, p["iBreak"])
        p["matchedBase"] = mb


def _compare(events, bases):
    """Observed event share against the mean matched base rate over the same patterns. z = (observed - expected) /
    sqrt(sum b (1 - b)) treats the patterns as independent draws with their own base rates; they are not (near-copy
    series, both thresholds), so z is optimistic."""
    pairs = [(bool(e), float(b)) for e, b in zip(events, bases) if e is not None and b is not None]
    if not pairs:
        return {"n": 0}
    e = np.array([a for a, _ in pairs], float)
    b = np.array([c for _, c in pairs], float)
    var = float((b * (1 - b)).sum())
    z = None if var <= 0 else float((e.sum() - b.sum()) / math.sqrt(var))
    return {"n": len(pairs), "eventRate": round(float(e.mean()), 3), "matchedBaseRate": round(float(b.mean()), 3),
            "differencePoints": round(100 * float(e.mean() - b.mean()), 1), "z": (None if z is None else round(z, 2)),
            "pOneSided": (None if z is None else round(0.5 * math.erfc(z / math.sqrt(2.0)), 4))}


def _edges_for(r, spans):
    if r in SPAN_EDGES:
        return SPAN_EDGES[r]
    v = np.asarray(spans, float)
    if len(v) < 10:
        return (0, 10 ** 9)
    return tuple([0] + [float(q) for q in np.unique(np.quantile(v, [0.2, 0.4, 0.6, 0.8]))] + [10 ** 9])


def _span_matched(real_ps, plac_ps, get, thresholds):
    """The placebo rate of an event standardised to the real patterns' (threshold x S1->S2 span bin) mix."""
    num = den = 0.0
    for r in thresholds:
        e = _edges_for(r, [p["w"]["S1S2"] for p in real_ps + plac_ps if p["r"] == r])
        for lo, hi in zip(e[:-1], e[1:]):
            a = [v for v in (get(p) for p in real_ps if p["r"] == r and lo <= p["w"]["S1S2"] < hi) if v is not None]
            b = [v for v in (get(p) for p in plac_ps if p["r"] == r and lo <= p["w"]["S1S2"] < hi) if v is not None]
            if not a or len(b) < 5:
                continue
            num += len(a) * float(np.mean(b))
            den += len(a)
    return {"rate": (round(num / den, 3) if den else None), "nRealUsed": int(den)}


def rates_diagnostics(real, plac, thresholds):
    """(1) The plan's comparison for the rates: the fixed-level neckline break, the target and the head-height move
    against the base rate of an equal move over the same horizon in the same series (three base-rate variants).
    (2) The fail-censored sloped-neckline rates against the placebo rate standardised to the real span mix."""
    rp = [p for p in real if p["pool"]]
    pp = [p for p in plac if p["pool"]]
    ip = [p for p in rp if p["inPlayAtConfirmation"]]
    ipp = [p for p in pp if p["inPlayAtConfirmation"]]
    brk = [p for p in rp if p["iBreak"] is not None]
    brkp = [p for p in pp if p["iBreak"] is not None]
    me = {"definition": {"fixedLevelNecklineBreakWithinWeeksOfInPlay": "in-play patterns: a weekly close beyond the neckline LEVEL fixed at the in-play week within H weeks (not censored by fails); move = in-play close minus that level",
                         "targetWithinWeeksOfBreak": "breaks: the pre-registered first close beyond the target within H weeks of the break; move = break close minus target",
                         "headHeightMoveWithinWeeksOfInPlay": "in-play patterns: a move of one head height from the in-play close within H weeks",
                         "eraInSample": "base rate over every week of the same series and era (includes later weeks and the pattern's own weeks)",
                         "eraExcludingOwnWeeks": "the same without the pattern's own weeks S1 .. anchor + H (the plan's 'without a pattern')",
                         "expandingPointInTime": "weeks of the same series whose H-week window had closed by the anchor week (in-play week, or the break week for the target)",
                         "test": "observed share against the mean matched base rate; z = (observed - expected) / sqrt(sum b(1-b)), optimistic because the patterns are not independent"},
          "fixedLevelNecklineBreakWithinWeeksOfInPlay": {}, "targetWithinWeeksOfBreak": {}, "headHeightMoveWithinWeeksOfInPlay": {}}
    for H in H_BREAK:
        ev = [p["fixedBreakWithin"][H] for p in ip]
        me["fixedLevelNecklineBreakWithinWeeksOfInPlay"][str(H)] = {v: _compare(ev, [p["matchedBase"]["fixedBreak"][H][v] for p in ip]) for v in BASE_VARIANTS}
        evm = [p["moveWithin"][H] for p in ip]
        me["headHeightMoveWithinWeeksOfInPlay"][str(H)] = {v: _compare(evm, [p["matchedBase"]["headHeight"][H][v] for p in ip]) for v in BASE_VARIANTS}
    for H in H_TARGET:
        ev = [p["targetWithin"][H] for p in brk]
        me["targetWithinWeeksOfBreak"][str(H)] = {v: _compare(ev, [p["matchedBase"]["target"][H][v] for p in brk]) for v in BASE_VARIANTS}
    sm = {"rule": "placebo rate standardised to the real patterns' threshold x S1->S2 span-bin mix (strata with >= 5 placebo patterns)",
          "breakWithinWeeksOfInPlay": {}, "fixedLevelNecklineBreakWithinWeeksOfInPlay": {}, "targetWithinWeeksOfBreak": {}}
    for H in H_BREAK:
        for key, get in (("breakWithinWeeksOfInPlay", lambda p, H=H: p["breakWithin"][H]),
                         ("fixedLevelNecklineBreakWithinWeeksOfInPlay", lambda p, H=H: p["fixedBreakWithin"][H])):
            sm[key][str(H)] = {"real": rate([get(p) for p in ip]), "placeboRaw": rate([get(p) for p in ipp]), "placeboSpanMatched": _span_matched(ip, ipp, get, thresholds)}
    for H in H_TARGET:
        get = (lambda p, H=H: p["targetWithin"][H])
        sm["targetWithinWeeksOfBreak"][str(H)] = {"real": rate([get(p) for p in brk]), "placeboRaw": rate([get(p) for p in brkp]),
                                                  "placeboSpanMatched": _span_matched(brk, brkp, get, thresholds)}
    return me, sm


def universe_replay(plac, dates_of, laws, draws=NOISE_DRAWS, seed=NOISE_SEED):
    """Criteria (i) and (iii) on noise at the real sample size. A universe is one surrogate of every series (the k-th
    IAAFT, or the k-th matched random walk, of each) with the real patterns' pool rule, expanding baseline and era rule.
    A universe has more rows with a baseline than the real set, and a median over more rows varies less, so each
    universe's rows are subsampled per era to the real per-era counts (`draws` subsamples per universe, without
    replacement; an era where a universe has fewer rows gives all it has): the noise statistic then has the real n and
    the real era coverage (an era with fewer than 3 real rows cannot count toward (iii) in noise either). The noise p is
    the share of draws at or above the real value (every universe weighs the same); beyond noise = the plan rule passes
    and the noise p is below 0.05. The earlier all-rows replay is kept beside it for the record."""
    rng = np.random.default_rng(seed)
    by = {}
    for p in plac:
        by.setdefault((p["placebo"], p["seed"] % 500), []).append(p)
    eras = [e[0] for e in ERAS]
    need = {law: {e: int(laws[law]["perEra"][e]["nWithBaseline"]) for e in eras} for law in LAWS}
    acc = {law: {"imp": [], "eras": [], "nb": [], "passI": 0, "passIII": 0, "nu": 0, "numatched": 0,
                 "impAll": [], "erasAll": [], "nbAll": [], "short": {e: 0 for e in eras}} for law in LAWS}

    def holds_all(wb):
        h = 0
        for e in eras:
            a = [x for x in wb if x["era"] == e]
            ml, mb = med([abs(x["err"]) for x in a]), med([abs(x["errBase"]) for x in a])
            h += int(len(a) >= 3 and ml is not None and mb is not None and ml < mb)
        return h
    for key in sorted(by):
        rows = law_rows(by[key], dates_of)
        add_baselines(rows)
        for law in LAWS:
            wb = [x for x in rows if x["law"] == law and x["pool"] and x["errBase"] is not None]
            if not wb:
                continue
            A = acc[law]
            A["nu"] += 1
            A["impAll"].append(round(float(np.median([abs(x["errBase"]) for x in wb]) - np.median([abs(x["err"]) for x in wb])), 2))
            A["erasAll"].append(holds_all(wb))
            A["nbAll"].append(len(wb))
            Ls, Bs, holds = [], [], np.zeros(draws, int)
            for e in eras:
                k = need[law][e]
                if k == 0:
                    continue
                le = np.array([abs(x["err"]) for x in wb if x["era"] == e], float)
                be = np.array([abs(x["errBase"]) for x in wb if x["era"] == e], float)
                if len(le) < k:
                    A["short"][e] += 1
                m = min(k, len(le))
                if m == 0:
                    continue
                idx = np.argsort(rng.random((draws, len(le))), axis=1)[:, :m]
                Ld, Bd = le[idx], be[idx]
                Ls.append(Ld)
                Bs.append(Bd)
                if m >= 3:
                    holds += (np.round(np.median(Ld, axis=1), 2) < np.round(np.median(Bd, axis=1), 2)).astype(int)
            if not Ls:
                continue
            L_, B_ = np.hstack(Ls), np.hstack(Bs)
            imp = np.round(np.median(B_, axis=1) - np.median(L_, axis=1), 2)
            nb = int(L_.shape[1])
            A["numatched"] += 1
            A["imp"].extend(imp.tolist())
            A["eras"].extend(holds.tolist())
            A["nb"].append(nb)
            A["passI"] += int(((imp >= 2) & (nb >= 10)).sum())
            A["passIII"] += int((holds >= 2).sum())
    out = {}
    for law in LAWS:
        L, A = laws[law], acc[law]
        v, e = np.array(A["imp"], float), np.array(A["eras"], float)
        va, ea = np.array(A["impAll"], float), np.array(A["erasAll"], float)
        nd, nu = len(v), len(va)
        ri, rh = L["improvementOverBaselineWeeks"], L["erasWhereDirectionHolds"]
        pi, piii = L["criteria"]["i"]["pass"], L["criteria"]["iii"]["pass"]

        def q(arr, x):
            return None if len(arr) == 0 else round(float(np.quantile(arr, x)), 2)

        def share(arr, cond):
            return None if len(arr) == 0 else round(float(np.mean(cond)), 3)
        p_i = None if ri is None else share(v, v >= ri)
        p_iii = share(e, e >= rh)
        era_n = need[law]
        thin = [name for name, k in era_n.items() if k < 3]
        short = {k: c for k, c in A["short"].items() if c}
        note = (f"{', '.join(thin)} {'has' if len(thin) == 1 else 'have'} fewer than 3 real rows with a baseline, so that era cannot count toward (iii)"
                + (" and (iii) can only be met by both other eras" if len(thin) == 1 else "") if thin else "every era has >= 3 real rows with a baseline")
        note += ("; the noise draws take the real per-era counts, so an era the real data cannot count cannot count in noise either"
                 + (" (universes with fewer rows than the real count in an era give all they have: " + ", ".join(f"{k}: {c} of {A['numatched']}" for k, c in short.items()) + ")" if short else ""))
        out[law] = {
            "nUniverses": nu, "nUniversesMatched": A["numatched"], "drawsPerUniverse": draws, "nNoiseDraws": nd,
            "universe": ("one surrogate of each series (the k-th IAAFT or the k-th random walk), the same pool, baseline and era rules; its rows with a "
                         f"baseline subsampled per era to the real per-era counts ({draws} draws per universe, without replacement), so the noise "
                         "statistic has the real n and era coverage"),
            "beyondNoiseRule": "the plan rule passes and the noise p (share of n-matched noise draws at or above the real value) is below 0.05",
            "criterionI": {"realImprovementWeeks": ri, "realNWithBaseline": L["nRealWithBaseline"], "realNWithBaselinePerEra": era_n,
                           "matchedNWithBaseline": (None if not A["nb"] else {"median": float(np.median(A["nb"])), "min": int(min(A["nb"])), "max": int(max(A["nb"]))}),
                           "universeMedian": q(v, 0.5), "universeIQR": (None if nd == 0 else [q(v, 0.25), q(v, 0.75)]), "universeP95": q(v, NOISE_Q),
                           "shareOfUniversesBelowReal": (None if ri is None else share(v, v < ri)),
                           "shareOfUniversesAtOrAboveReal": p_i, "noiseP": p_i,
                           "shareOfUniversesPassingThePlanRule": (None if nd == 0 else round(A["passI"] / nd, 3)),
                           "passPlanRule": pi, "passBeyondNoise": bool(pi and p_i is not None and p_i < 0.05),
                           "allRowsNotNMatched": {"universeMedian": q(va, 0.5), "universeP95": q(va, NOISE_Q),
                                                  "shareOfUniversesAtOrAboveReal": (None if ri is None else share(va, va >= ri)),
                                                  "medianUniverseNWithBaseline": (None if nu == 0 else float(np.median(A["nbAll"]))),
                                                  "note": ("the earlier replay, superseded: each universe scored on all of its rows with a baseline (more than the "
                                                           "real n), so its spread is too narrow for the real statistic")}},
            "criterionIII": {"realErasHolding": rh, "erasHoldingShareOfDraws": {str(k): share(e, e == k) for k in range(4)}, "universeP95": q(e, NOISE_Q),
                             "shareOfUniversesAtOrAboveReal": p_iii, "noiseP": p_iii,
                             "shareOfUniversesPassingThePlanRule": (None if nd == 0 else round(A["passIII"] / nd, 3)),
                             "passPlanRule": piii, "passBeyondNoise": bool(piii and p_iii is not None and p_iii < 0.05),
                             "allRowsNotNMatched": {"universeErasHolding": {str(k): int((ea == k).sum()) for k in range(4)}, "universeP95": q(ea, NOISE_Q),
                                                    "shareOfUniversesAtOrAboveReal": share(ea, ea >= rh),
                                                    "note": ("the earlier replay, superseded: universes counted eras the real data cannot (fewer than 3 real rows), "
                                                             "and its rule (real > P95 of a 0..3 count) could not pass when P95 was 3")}},
            "eraCoverage": {"nWithBaselinePerEra": era_n, "universesShortOfTheRealCountPerEra": A["short"], "note": note}}
    return out


def exact_dup_drop(pats):
    """The same five pivots of the same series (and surrogate) found at both thresholds counted once, at the smaller r."""
    seen, out = set(), []
    for p in sorted(pats, key=lambda p: p["r"]):
        k = (p["series"], p.get("placebo"), p.get("seed"), p["kind"], tuple(p["i"].values()))
        if k not in seen:
            seen.add(k)
            out.append(p)
    return out


def weekly_change_corr(data):
    """Correlation of weekly changes (logit for shares, log for prices) over the weeks every series exists."""
    df = pd.DataFrame({n: pd.Series(np.diff(d["x"]), index=d["weekly"].index[1:]) for n, d in data.items()})
    start = max(d["weekly"].index[1] for d in data.values())
    return df.loc[start:].corr(), start


def independence(corr, start):
    """Series joined when |rho| >= GROUP_RHO (connected components), and the participation ratio of the correlation
    matrix's eigenvalues: two readings of how many independent histories the pooled test really has."""
    names = list(corr.columns)
    parent = {n: n for n in names}

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    for k, a in enumerate(names):
        for b in names[k + 1:]:
            if abs(float(corr.loc[a, b])) >= GROUP_RHO:
                parent[find(a)] = find(b)
    groups = {}
    for n in names:
        groups.setdefault(find(n), []).append(n)
    gl = sorted((sorted(g, key=lambda n: SERIES_ORDER.get(n, 99)) for g in groups.values()), key=lambda g: SERIES_ORDER.get(g[0], 99))
    ev = np.linalg.eigvalsh(np.nan_to_num(corr.values))
    pr = float(ev.sum() ** 2 / (ev ** 2).sum()) if (ev ** 2).sum() > 0 else None
    return {"groups": gl, "nGroups": len(gl), "participationRatio": (None if pr is None else round(pr, 2)),
            "rule": f"series joined when |rho| of weekly changes >= {GROUP_RHO} (connected components), over the weeks every series exists (from {ds(start)})",
            "weeklyChangeCorrelation": {a: {b: round(float(corr.loc[a, b]), 2) for b in names} for a in names},
            "note": (f"the {sum(1 for _ in corr.columns)} series are about {len(gl)} independent histories (" + "; ".join(", ".join(g) for g in gl) + "): the pooled "
                     "test's n counts near-copies of the same market moves; see laws.*.robustness for one pattern per cluster")}


def _overlap(a0, a1, b0, b1):
    inter = (min(a1, b1) - max(a0, b0)).days
    union = (max(a1, b1) - min(a0, b0)).days
    return inter / union if union > 0 else 0.0


def cluster_map(pats, dates_of, corr, across, mirror_rho=MIRROR_RHO):
    """Union-find clusters of near-copy pool patterns: the same kind (or the opposite kind on a series pair whose weekly
    changes correlate below mirror_rho), S2 within CLUSTER_S2_WEEKS weeks and S1..S2 spans overlapping >= CLUSTER_OVERLAP
    (intersection over union). The same five pivots at both thresholds are always one cluster; across=True also links
    patterns found at different thresholds (including one series' structure seen at both). Returns {id(p): cluster}."""
    n = len(pats)
    parent = list(range(n))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    span = [(dates_of[p["series"]][p["i"]["S1"]], dates_of[p["series"]][p["i"]["S2"]]) for p in pats]
    for a in range(n):
        for b in range(a + 1, n):
            p, q = pats[a], pats[b]
            same = p["series"] == q["series"]
            if same and p["kind"] == q["kind"] and p["i"] == q["i"]:
                parent[find(a)] = find(b)
                continue
            if (same and (not across or p["r"] == q["r"])) or (not same and not across and p["r"] != q["r"]):
                continue
            if abs((p["s2date"] - q["s2date"]).days) > 7 * CLUSTER_S2_WEEKS or _overlap(*span[a], *span[b]) < CLUSTER_OVERLAP:
                continue
            rho = float(corr.loc[p["series"], q["series"]]) if (p["series"] in corr.index and q["series"] in corr.index) else 0.0
            if p["kind"] == q["kind"] or (not same and rho < mirror_rho):
                parent[find(a)] = find(b)
    return {id(p): find(a) for a, p in enumerate(pats)}


def placebo_cluster_map(pats, dates_of, corr):
    """The across-threshold cluster rule applied inside each surrogate (series, kind, seed): the placebo side of the
    one-per-cluster line merges a surrogate's near-copies across thresholds exactly as the real side does (surrogates
    are independent of each other, so no cluster spans two of them). Returns {id(p): (surrogate, cluster)}."""
    groups, out = {}, {}
    for p in pats:
        groups.setdefault((p["series"], p["placebo"], p["seed"]), []).append(p)
    for g, ps in groups.items():
        for k, c in cluster_map(ps, dates_of, corr, True).items():
            out[k] = (g, c)
    return out


def one_per_cluster(rows, cmap):
    """One row per cluster: among the members with a known actual for this law, the first in the plan's series order
    (named series first), then the smaller threshold, then the earlier S2."""
    best = {}
    for x in rows:
        c = cmap.get(id(x["p"]))
        if c is None:
            continue
        key = (SERIES_ORDER.get(x["series"], 99), x["r"], x["p"]["i"]["S2"])
        if c not in best or key < best[c][0]:
            best[c] = (key, x)
    return [v[1] for v in best.values()]


def robust_line(law, rr, pr, thresholds, what):
    """The pre-registered pooled test and criteria re-run on a reduced pattern set (baselines recomputed on that set)."""
    rows = [dict(x) for x in rr if x["law"] == law and x["pool"]]
    add_baselines(rows)
    L = law_report(law, rows, [x for x in pr if x["law"] == law], thresholds, scale=False)
    c = L["criteria"]
    return {"what": what, "nReal": L["nRealPool"], "nPlacebo": L["pooledTest"]["nPlacebo"], "realMedianAbs": L["real"].get("medianAbs"),
            "placeboMedianAbs": L["placebo"].get("medianAbs"), "p": L["pooledTest"]["p"], "probRealSmaller": L["pooledTest"]["probRealSmaller"],
            "nWithBaseline": L["nRealWithBaseline"], "baselineMedianAbs": L["baseline"].get("medianAbs"), "improvementWeeks": L["improvementOverBaselineWeeks"],
            "erasHolding": L["erasWhereDirectionHolds"], "criteriaPass": {"i": c["i"]["pass"], "ii": c["ii"]["pass"], "iii": c["iii"]["pass"]},
            "verdictOnThisSet": L["verdict"].split(":")[0]}


def low_share_head(p):
    """A dominance-share pattern whose head (its extreme) sits below LOW_SHARE % share."""
    return bool(is_share(p["series"]) and float(from_space(p["sign"] * p["v"]["H"], "logit")) < LOW_SHARE)


def robustness(real, real_rows, plac, plac_post, dates_of, corr, thresholds):
    """Robustness lines for every law (the plan's test on reduced or re-referenced sets) and their summary."""
    pool = [p for p in real if p["pool"]]
    dd_real, dd_plac = exact_dup_drop(real), exact_dup_drop(plac)
    rr_dd, pr_dd = law_rows(dd_real, dates_of), law_rows(dd_plac, dates_of)
    c_same, c_across = cluster_map(pool, dates_of, corr, False), cluster_map(pool, dates_of, corr, True)
    a_same, a_across = cluster_map(pool, dates_of, corr, False, MIRROR_RHO_ALT), cluster_map(pool, dates_of, corr, True, MIRROR_RHO_ALT)
    # placebo side: within one surrogate the same-threshold rule merges only identical five-pivot patterns (= pr_dd);
    # the across-threshold rule also merges a surrogate's near-copies at the two thresholds, as on the real side
    plac_pool = [p for p in plac if p["pool"]]
    pc_across = placebo_cluster_map(plac_pool, dates_of, corr)
    pr_pool = law_rows(plac_pool, dates_of)
    rr_low = law_rows([p for p in real if not low_share_head(p)], dates_of)
    pr_low = law_rows([p for p in plac if not low_share_head(p)], dates_of)
    pr_post = None
    if plac_post:
        post_dates = dict(dates_of)
        post_dates["BTC.D"] = dates_of["BTC.D"][dates_of["BTC.D"] >= SPLICE_WEEK]
        pr_post = law_rows([p for p in plac if p["series"] != "BTC.D"], dates_of) + law_rows(plac_post, post_dates)
    per, alt = {}, {}
    for law in LAWS:
        lr = [x for x in real_rows if x["law"] == law and x["pool"]]
        pr_across = one_per_cluster([x for x in pr_pool if x["law"] == law], pc_across)
        lines = {"thresholdDuplicatesCountedOnce": robust_line(law, rr_dd, pr_dd, thresholds, "the same five pivots found at both thresholds counted once (real and placebo)"),
                 "onePerClusterSameThreshold": robust_line(law, one_per_cluster(lr, c_same), pr_dd, thresholds,
                                                           "one pattern per near-copy cluster (same threshold; threshold duplicates merged, real and placebo)"),
                 "onePerClusterAcrossThresholds": robust_line(law, one_per_cluster(lr, c_across), pr_across, thresholds,
                                                              "one pattern per near-copy cluster, clusters also joined across thresholds (the placebo side clustered the "
                                                              "same way inside each surrogate)"),
                 "excludingLowShareHeads": robust_line(law, rr_low, pr_low, thresholds, f"dominance patterns with the head below {LOW_SHARE:g}% share left out (real and placebo)")}
        if pr_post is not None:
            lines["btcdPlacebosFromPostSpliceSegment"] = robust_line(law, real_rows, pr_post, thresholds,
                                                                    "BTC.D placebos built from the post-splice segment only (the regime of the pooled real BTC.D patterns)")
        per[law] = lines
        alt[law] = (robust_line(law, one_per_cluster(lr, a_same), pr_dd, thresholds, ""), robust_line(law, one_per_cluster(lr, a_across), pr_across, thresholds, ""))
    names = list(corr.columns)
    neg = [(a, b, float(corr.loc[a, b])) for k, a in enumerate(names) for b in names[k + 1:] if float(corr.loc[a, b]) < MIRROR_RHO]
    s2pairs = {}
    for p in pool:
        s2pairs.setdefault((p["series"], p["kind"], p["i"]["S2"]), set()).add(p["r"])
    summary = {"thresholdOverlap": {"identicalFivePivotPatternsAtBothThresholds": len(pool) - sum(1 for p in dd_real if p["pool"]),
                                    "sameS2WeekAtBothThresholds": sum(1 for v in s2pairs.values() if len(v) > 1),
                                    "pooledPWithThresholdDuplicatesCountedOnce": {law: per[law]["thresholdDuplicatesCountedOnce"]["p"] for law in LAWS},
                                    "note": "the pooled test pools both thresholds, so these patterns enter twice (dependence, not leakage)"},
               "nearCopyClusters": {"nPoolPatterns": len(pool), "nClustersSameThreshold": len(set(c_same.values())), "nClustersAcrossThresholds": len(set(c_across.values())),
                                    "rule": (f"same kind, S2 within {CLUSTER_S2_WEEKS} weeks, S1..S2 overlap >= {CLUSTER_OVERLAP:.0%} (intersection over union); opposite kind "
                                             f"for series pairs whose weekly changes correlate below {MIRROR_RHO} (the mirror of the {GROUP_RHO} one-history rule); the same "
                                             "five pivots at both thresholds merged; the across-threshold line clusters each surrogate's placebo patterns by the same rule"),
                                    "seriesPairsBelowMirrorRho": [f"{a}-{b} {r_:.2f}" for a, b, r_ in neg],
                                    "pooledPOnePerClusterSameThreshold": {law: per[law]["onePerClusterSameThreshold"]["p"] for law in LAWS},
                                    "pooledPOnePerClusterAcrossThresholds": {law: per[law]["onePerClusterAcrossThresholds"]["p"] for law in LAWS},
                                    "nRealPerLawOnePerCluster": {law: [per[law]["onePerClusterSameThreshold"]["nReal"], per[law]["onePerClusterAcrossThresholds"]["nReal"]] for law in LAWS},
                                    "nPlaceboPerLawAcrossThresholds": {law: [per[law]["thresholdDuplicatesCountedOnce"]["nPlacebo"], per[law]["onePerClusterAcrossThresholds"]["nPlacebo"]] for law in LAWS},
                                    "mirrorRhoSensitivity": {
                                        "mirrorRho": MIRROR_RHO_ALT,
                                        "seriesPairsLinkedOnlyAtTheMainRule": [f"{a}-{b} {r_:.2f}" for a, b, r_ in neg if r_ >= MIRROR_RHO_ALT],
                                        "nClustersSameThreshold": len(set(a_same.values())), "nClustersAcrossThresholds": len(set(a_across.values())),
                                        "nRealPerLawOnePerCluster": {law: [alt[law][0]["nReal"], alt[law][1]["nReal"]] for law in LAWS},
                                        "pooledPOnePerClusterSameThreshold": {law: alt[law][0]["p"] for law in LAWS},
                                        "pooledPOnePerClusterAcrossThresholds": {law: alt[law][1]["p"] for law in LAWS},
                                        "verdictsOnTheseSets": {law: [alt[law][0]["verdictOnThisSet"], alt[law][1]["verdictOnThisSet"]] for law in LAWS}}},
               "lowShare": {"poolPatternsWithHeadBelowLowShare": sum(1 for p in pool if low_share_head(p)),
                            "pooledPExcludingThem": {law: per[law]["excludingLowShareHeads"]["p"] for law in LAWS}}}
    return per, summary


def t2_selection(data, real, zz_by, thresholds):
    """Four-pivot left halves (S1 T1 H T2 with H beyond S1) at whose T2 confirmation a T2 forecast could be issued, and how
    many of them later became detector patterns (the only ones T2 is scored on). All series, every threshold run."""
    quads = became = 0
    for n, d in data.items():
        for r in thresholds:
            pi, pt = zz_by[(n, r)][0], zz_by[(n, r)][1]
            pats = set((p["kind"], tuple(list(p["i"].values())[:4])) for p in real if p["series"] == n and p["r"] == r)
            for sign in (1, -1):
                y = sign * d["x"]
                for k in range(len(pi) - 3):
                    if pt[k] != sign:
                        continue
                    i4 = tuple(int(v) for v in pi[k:k + 4])
                    if y[i4[2]] > y[i4[0]]:
                        quads += 1
                        became += int((("top" if sign == 1 else "inverse"), i4) in pats)
    return quads, became


def act_over_pred(law, real_rows, plac_rows):
    def blk(rows):
        v = [x["act"] / x["pred"] for x in rows if x["pred"] > 0]
        if not v:
            return {"n": 0}
        return {"n": len(v), "median": round(float(np.median(v)), 2), "IQR": [round(float(np.quantile(v, 0.25)), 2), round(float(np.quantile(v, 0.75)), 2)],
                "shareActualLonger": round(float(np.mean([x["act"] > x["pred"] for x in rows])), 3)}
    rr = [x for x in real_rows if x["law"] == law and x["pool"]]
    pr = [x for x in plac_rows if x["law"] == law and x["pool"]]
    return {"what": "actual / predicted duration (1 = on time; above 1 = the event came later than the law said)", "real": blk(rr), "placebo": blk(pr),
            "realSignedMedianErrorWeeks": med([x["err"] for x in rr])}


def time_scale(real, plac, plac_meta, data, zz_by, thresholds):
    """The detector's output on the real series against each placebo kind: pivot density, pattern density, pool pattern
    span, and the levels the surrogates live at (the raw-week rank test compares errors of patterns of different length)."""
    names = list(data)
    metas = [m for m in plac_meta if m.get("tag") is None]
    out = {}

    def span(ps):
        v = [p["w"]["S1S2"] for p in ps]
        return {"n": len(v), "median": med(v), "IQR": ([round(float(np.quantile(v, 0.25)), 1), round(float(np.quantile(v, 0.75)), 1)] if v else None)}
    for r in thresholds:
        row = {"pivotsPer100Weeks": {"real": round(float(np.mean([100.0 * len(zz_by[(n, r)][0]) / len(data[n]["x"]) for n in names])), 2)},
               "patternsPerSeries": {"real": round(sum(1 for p in real if p["r"] == r) / len(names), 2)},
               "poolS1S2SpanWeeks": {"real": span([p for p in real if p["pool"] and p["r"] == r])}}
        for k in ("iaaft", "rw"):
            ms = [m for m in metas if m["kind"] == k]
            row["pivotsPer100Weeks"][k] = (round(float(np.mean([100.0 * m["pivots"][r] / m["weeks"] for m in ms])), 2) if ms else None)
            row["patternsPerSeries"][k] = round(sum(1 for p in plac if p["r"] == r and p["placebo"] == k) / max(1, len(ms)), 2)
            row["poolS1S2SpanWeeks"][k] = span([p for p in plac if p["pool"] and p["r"] == r and p["placebo"] == k])
        out[f"r={r}"] = row
    per, lv = {}, {}
    for n in names:
        per[n] = {}
        for r in thresholds:
            e = {"real": round(100.0 * len(zz_by[(n, r)][0]) / len(data[n]["x"]), 2)}
            for k in ("iaaft", "rw"):
                ms = [m for m in metas if m["name"] == n and m["kind"] == k]
                e[k] = (round(float(np.mean([100.0 * m["pivots"][r] / m["weeks"] for m in ms])), 2) if ms else None)
            per[n][f"r={r}"] = e
        nat = from_space(data[n]["x"], data[n]["space"])
        e = {"real": [round(float(nat.min()), 4), round(float(nat.max()), 4)]}
        for k in ("iaaft", "rw"):
            ms = [m for m in metas if m["name"] == n and m["kind"] == k and "nativeMin" in m]
            if ms:
                e[k] = [round(float(np.median([m["nativeMin"] for m in ms])), 4), round(float(np.median([m["nativeMax"] for m in ms])), 4)]
        lv[n] = e
    out["pivotsPer100WeeksPerSeries"] = per
    out["nativeRangeMedianMinMax"] = lv
    out["iaaftKeepsTheExactMarginal"] = bool(all(m["sameMarginal"] for m in metas if m["kind"] == "iaaft"))
    out["note"] = ("IAAFT surrogates keep the exact marginal (share series stay inside 0..100) but are choppier than the real series; the matched random "
                   "walk is not level-matched (its levels drift outside the real range), harmless for the translation-invariant logit/log detector. "
                   "Placebo patterns are shorter than real ones at the same threshold, which is why laws.*.scaleDiagnostics holds the time scale fixed.")
    return out


def horizontal_neckline(p, w, dates, space):
    """The chartist's reading beside the plan's sloped neckline: a horizontal line through T2's close. For a top a weekly
    close below it after S2 is the break, for an inverse a close above it. Reporting only; plan [1] defines the break."""
    sign, i = p["sign"], p["i"]
    lvl = float(w.values[i["T2"]])
    last = len(w) - 1
    beyond = [j for j in range(i["S2"] + 1, last + 1) if sign * (float(w.values[j]) - lvl) < 0]
    close = float(w.values[last])
    pts = sign * (close - lvl)
    return {"level": round(lvl, 4), "closedBeyondSinceS2": bool(beyond), "firstCloseBeyond": (ds(dates[beyond[0]]) if beyond else None),
            "weeksBeyondSinceS2": len(beyond), "lastClose": {"date": ds(dates[last]), "level": round(close, 4)},
            "distanceOnUnbrokenSide": {"points": round(pts, 4), "pct": round(100.0 * pts / lvl, 2), "unit": ("percentage points of share" if space == "logit" else "USD")},
            "rule": "a weekly close " + ("below" if sign == 1 else "above") + " the T2 close after S2 is the break; distance > 0 = still on the unbroken side"}


def structure_summary(p, d):
    w, dates, space = d["weekly"], d["weekly"].index, d["space"]
    i = p["i"]
    failed = [k for k, v in p["checks"].items() if not v]
    s = {"kind": p["kind"], "pivots": {k: {"date": ds(dates[i[k]]), "level": round(float(w.values[i[k]]), 4)} for k in ("S1", "T1", "H", "T2", "S2")},
         "s2Provisional": bool(p.get("s2Provisional")), "isDetectorPattern": bool(p["geometryOk"] and not p.get("s2Provisional")),
         "failedChecks": failed, "failedCheckMargins": [margin_text(k, p["checkDetails"][k]) for k in failed]}
    if p.get("s2Provisional"):
        s["status"] = "forming (S2 provisional)"
    else:
        s["status"] = p["status"]
        s["inPlayWeek"] = ds(dates[p["conf"]])
        s["brokenAtConfirmation"] = bool(p["brokenAtConfirmation"])
        for key, f in (("breakWeek", "iBreak"), ("failWeek", "iFail"), ("completionWeek", "iComp")):
            s[key] = None if p[f] is None else ds(dates[p[f]])
    s["horizontalNeckline"] = horizontal_neckline(p, w, dates, space)
    return s


def r_sweep(expected, d):
    """The current structure across reversal thresholds (reporting for plan [3]; the law tests use the plan's two r)."""
    x = d["x"]
    signs = (1,) if expected == "top" else (-1,) if expected == "inverse" else (1, -1)
    rows = []
    for r in SWEEP_R:
        zz = zigzag(x, r)
        pats = [p for sg in signs for p in detect(x, zz, r, sg)]
        inplay = sorted([p for p in pats if p["status"] == "in-play"], key=lambda p: p["i"]["S2"])
        nears = [s for s in (nearest_structure(x, zz, r, sg) for sg in signs) if s is not None]
        near = min(nears, key=lambda p: (n_fail(p), -p["i"]["S2"])) if nears else None
        latest = max(pats, key=lambda p: p["i"]["S2"]) if pats else None
        row = {"r": r, "pivots": int(len(zz[0])), "patternInPlay": (structure_summary(inplay[-1], d) if inplay else None),
               "nearestStructure": (structure_summary(near, d) if near is not None else None)}
        if latest is not None and (near is None or latest["i"] != near["i"] or latest["kind"] != near["kind"]):
            row["latestDetectorPattern"] = structure_summary(latest, d)
        if near is None and not inplay:
            row["formingStage"] = {("top" if sg == 1 else "inverse"): stage_text(forming_stage(x, zz, r, sg, d["weekly"].index, d["weekly"], d["space"])) for sg in signs}
        rows.append(row)
    return rows


def sweep_groups(rows):
    """The sweep's structures (the in-play pattern, else the nearest structure) grouped by head and neckline (kind, T1, H,
    T2): one structure seen at several thresholds, with its S1/S2 variants and status at each r."""
    groups, none = {}, []
    for row in rows:
        s = row["patternInPlay"] or row["nearestStructure"]
        if s is None:
            none.append(row["r"])
            continue
        pv = s["pivots"]
        g = groups.setdefault((s["kind"], pv["T1"]["date"], pv["H"]["date"], pv["T2"]["date"]),
                              {"kind": s["kind"], "T1": pv["T1"]["date"], "H": pv["H"]["date"], "T2": pv["T2"]["date"], "rs": [], "variants": {}})
        g["rs"].append(row["r"])
        v = g["variants"].setdefault((pv["S1"]["date"], pv["S2"]["date"], s["s2Provisional"]),
                                     {"S1": pv["S1"]["date"], "S2": pv["S2"]["date"], "s2Provisional": s["s2Provisional"], "rs": [], "status": s["status"],
                                      "failedChecks": s["failedChecks"], "failedCheckMargins": s["failedCheckMargins"], "breakWeek": s.get("breakWeek"),
                                      "failWeek": s.get("failWeek"), "completionWeek": s.get("completionWeek"),
                                      "horizontalNecklineClosedBeyond": s["horizontalNeckline"]["closedBeyondSinceS2"]})
        v["rs"].append(row["r"])
    out = []
    for g in groups.values():
        g["variants"] = list(g["variants"].values())
        g["statusChangesWithR"] = len(set((v["status"], v["breakWeek"], v["failWeek"]) for v in g["variants"])) > 1
        out.append(g)
    return out, none


def _rs(rs):
    return ", ".join(f"{r:g}" for r in rs)


def variant_text(v, checks=True):
    s = f"S1 {v['S1']}, S2 {v['S2']}{' (provisional)' if v['s2Provisional'] else ''} at r={_rs(v['rs'])}: {v['status']}"
    if v["breakWeek"]:
        s += f" (break {v['breakWeek']}" + (f", target {v['completionWeek']}" if v["completionWeek"] else "") + ")"
    elif v["failWeek"]:
        s += f" ({v['failWeek']})"
    if checks:
        s += ("; fails " + ", ".join(v["failedCheckMargins"])) if v["failedChecks"] else "; passes every check"
    return s


def sweep_text(groups, none):
    parts = [f"{g['kind']} with T1 {g['T1']}, H {g['H']}, T2 {g['T2']}: " + " / ".join(variant_text(v) for v in g["variants"]) for g in groups]
    if none:
        parts.append(f"no structure of the expected kind at r={_rs(none)}")
    return " | ".join(parts)


def sweep_group_of(cur, name, p):
    sw = cur.get(name, {}).get("rSweep")
    if not sw or p is None:
        return None, []
    pv = p["pivots"]
    allr = [row["r"] for row in sw["rows"]]
    return next((g for g in sw["groups"] if (g["kind"], g["T1"], g["H"], g["T2"]) == (p["kind"], pv["T1"]["date"], pv["H"]["date"], pv["T2"]["date"])), None), allr


def sweep_clause(cur, name, p):
    """How the structure a reading uses fares across the threshold sweep."""
    g, allr = sweep_group_of(cur, name, p)
    if not allr:
        return ""
    if g is None:
        return f"; across r={allr[0]:g}-{allr[-1]:g} this head and neckline is not the sweep's structure at any r"
    s = f"; across r={allr[0]:g}-{allr[-1]:g} the same head and neckline is found at r={_rs(g['rs'])}"
    if g["statusChangesWithR"]:
        s += ", and its reading changes with r (" + "; ".join(variant_text(v, checks=False) for v in g["variants"]) + ")"
    other = [r for r in allr if r not in g["rs"]]
    if other:
        s += f"; at r={_rs(other)} the detector sees a different structure or none"
    return s


def placebo_wording(laws):
    """The real-against-placebo comparison of the pre-registered raw-week test, in words."""
    sm, ind, ns = [], [], []
    for law in LAWS:
        t = laws[law]["pooledTest"]
        if t["p"] is not None and t["p"] < 0.05:
            sm.append(law)
        elif t["probRealSmaller"] is not None and t["probRealSmaller"] >= 0.5:
            ind.append(law)
        else:
            ns.append(law)

    def j(ls):
        return ls[0] if len(ls) == 1 else ", ".join(ls[:-1]) + " and " + ls[-1]
    parts = []
    if sm:
        parts.append(f"smaller than placebo errors for {j(sm)}")
    if ns:
        parts.append(f"not smaller than placebo errors for {j(ns)}")
    if ind:
        parts.append(f"indistinguishable for {j(ind)} (" + ", ".join(f"{law}: P(real < placebo) {laws[law]['pooledTest']['probRealSmaller']}, p={laws[law]['pooledTest']['p']}" for law in ind) + ")")
    return "Real-pattern errors (the pre-registered raw-week test) are " + "; ".join(parts)


def scale_wording(laws):
    """The same comparison with the time scale held fixed (span-stratified rank test), in words."""
    bonf = round(0.05 / len(LAWS), 4)
    ps = [(law, laws[law].get("scaleDiagnostics", {}).get("spanStratified", {}).get("p")) for law in LAWS]
    beats = [law for law, p in ps if p is not None and p < bonf]
    nominal = [law for law, p in ps if p is not None and bonf <= p < 0.05]
    border = [law for law, p in ps if p is not None and 0.05 <= p < 0.1]
    s = "held at the same time scale (rank test stratified by threshold x S1->S2 span; T2 by S1->H, since S1->S2 contains its outcome) "
    if beats:
        s += "better than noise of the same time scale for " + ", ".join(beats) + f" (Bonferroni {bonf})"
    else:
        s += "no law is better than noise of the same time scale"
    extra = [f"{law} nominal p={p}, not Bonferroni-proof at {bonf}" for law, p in ps if law in nominal] + [f"{law} borderline, p={p}" for law, p in ps if law in border]
    if extra:
        s += " (" + "; ".join(extra) + ")"
    s += ": " + ", ".join(f"{law} p={p}" for law, p in ps)
    # the scale-free tests (|error| / predicted, |error| / span) beside it whenever one reaches p < 0.05
    sf = {}
    for law in LAWS:
        sd = laws[law].get("scaleDiagnostics", {})
        for key, lab in (("absErrorOverPredicted", "abs error / predicted"), ("absErrorOverSpan", "abs error / span")):
            p = (sd.get(key) or {}).get("p")
            if p is not None and p < 0.05:
                sf.setdefault(law, []).append((lab, p))
    if sf:
        s += "; the scale-free tests reach p < 0.05 for " + "; ".join(
            f"{law} (" + ", ".join(f"{lab} p={p}" for lab, p in v) + ": "
            + ("nominal, not Bonferroni-proof at " + str(bonf) if all(p >= bonf for _, p in v) else "below the Bonferroni " + str(bonf) + " for " + ", ".join(lab for lab, p in v if p < bonf))
            + ")" for law, v in sf.items())
    else:
        s += "; no scale-free test (abs error / predicted, abs error / span) reaches p < 0.05"
    return s


# ------------------------------------------------------------------------------------------------- export
def pattern_record(p, data):
    d = data[p["series"]]
    w, dates, space, sign = d["weekly"], d["weekly"].index, d["space"], p["sign"]
    i = p["i"]

    def nat(yv):
        return round(float(from_space(sign * yv, space)), 6)

    def nl(j):
        return p["v"]["T1"] + p["slope"] * (j - i["T1"])
    rec = {"series": p["series"], "kind": p["kind"], "threshold": p["r"], "era": p["era"], "inPool": p["pool"],
           "space": space, "status": p["status"]}
    for k in ("S1", "T1", "H", "T2", "S2"):
        rec[k] = {"date": ds(dates[i[k]]), "level": round(float(w.values[i[k]]), 6), "inSpace": round(float(sign * p["v"][k]), 5)}
    rec["inPlayWeek"] = ds(dates[p["conf"]])
    rec["weeksS2ToConfirmation"] = p["w"]["S2Conf"]
    rec["inPlayAtConfirmation"] = p["inPlayAtConfirmation"]
    rec["brokenAtConfirmation"] = p["brokenAtConfirmation"]
    rec["headHeightInSpace"] = round(float(p["head"]), 5)
    rec["necklineAtS2"] = nat(nl(i["S2"]))
    rec["necklineSlopePerWeekInSpace"] = round(float(sign * p["slope"]), 6)
    rec["breakWeek"] = None if p["iBreak"] is None else ds(dates[p["iBreak"]])
    rec["targetLevel"] = None if p["targetY"] is None else nat(p["targetY"])
    rec["targetInSpace"] = None if p["targetY"] is None else round(float(sign * p["targetY"]), 5)
    rec["completionWeek"] = None if p["iComp"] is None else ds(dates[p["iComp"]])
    rec["failWeek"] = None if p["iFail"] is None else ds(dates[p["iFail"]])
    rec["completionWindowOpen"] = p["completionWindowOpen"]
    rec["timingsWeeks"] = dict(p["w"])
    rec["lawPredictionsWeeks"] = {"T1_S2ToBreak": p["w"]["S1T1"], "T2_HToS2": p["w"]["S1H"], "T3_BreakToTarget": p["w"]["HT2"], "T3alt_BreakToTarget": 0.5 * p["w"]["S1S2"]}
    rec["breakWithinWeeksOfInPlay"] = {str(k): v for k, v in p["breakWithin"].items()}
    rec["targetWithinWeeksOfBreak"] = {str(k): v for k, v in p["targetWithin"].items()}
    rec["headHeightMoveWithin"] = {str(k): v for k, v in p["moveWithin"].items()}
    rec["matchedBaseRate"] = {str(k): v for k, v in p.get("baseRate", {}).items()}
    return rec


# ------------------------------------------------------------------------------------------------- current patterns
def law_band(laws, law, inplay=False):
    """Historical error band of a law: from the pooled patterns still in play at S2's confirmation (inplay=True), or
    from every pooled pattern (the pre-registered set)."""
    st = (laws[law].get("inPlayAtConfirmation") or {}).get("real", {}) if inplay else laws[law]["real"]
    if not st or st.get("n", 0) == 0:
        return None
    return {"subset": ("pooled patterns in play at S2's confirmation" if inplay else "all pooled patterns (pre-registered set)"),
            "nRealPatterns": st["n"], "medianAbsErrorWeeks": st["medianAbs"], "absErrorIQRWeeks": st["absIQR"], "signedErrorIQRWeeks": st["signedIQR"]}


def date_band(pred_date, n, signed_iqr, earliest=None, min_n=BAND_MIN_N):
    """The actual date's interquartile band from historical signed errors (error = predicted - actual, so the band is
    predicted - [q75, q25]). Returns (band or None, note or None): no band below min_n errors; for an event not seen by
    the data end the band is clipped at the earliest week the event can still happen (None when all of it is earlier)."""
    if signed_iqr is None or not n:
        return None, "no historical errors"
    if n < min_n:
        return None, f"no band: {n} historical errors (fewer than {min_n})"
    lo, hi = pred_date - pd.Timedelta(weeks=signed_iqr[1]), pred_date - pd.Timedelta(weeks=signed_iqr[0])
    if earliest is not None and lo < earliest:
        if hi < earliest:
            return None, f"the whole IQR band ({ds(lo)} to {ds(hi)}) lies before {ds(earliest)}, the earliest week the event can still happen"
        return [ds(earliest), ds(hi)], f"the lower edge {ds(lo)} is clipped to {ds(earliest)}, the earliest week the event can still happen"
    return [ds(lo), ds(hi)], None


def band_context(real):
    """Denominators of the current-pattern bands: how many pooled patterns (all, and those in play at S2's confirmation)
    broke, failed first, expired or are still open, and how many of their breaks completed."""
    def counts(ps):
        brk = [p for p in ps if p["iBreak"] is not None]
        return {"patterns": len(ps), "broke": len(brk), "failedFirst": sum(1 for p in ps if p["status"] == "failed"),
                "expired": sum(1 for p in ps if p["status"] == "expired"), "stillInPlay": sum(1 for p in ps if p["status"] == "in-play"),
                "completed": sum(1 for p in brk if p["iComp"] is not None)}
    pool = [p for p in real if p["pool"]]
    return {"inPlay": counts([p for p in pool if p["inPlayAtConfirmation"]]), "all": counts(pool)}


def band_from_text(law, c, n, inplay):
    """Which errors a band comes from, with the denominator (the T1 rows exist only for patterns that broke, the T3 and
    T3alt rows only for breaks that completed)."""
    if c is None:
        subset = "patterns in play at S2's confirmation" if inplay else "patterns"
        return f"signed errors of the {n} pooled {subset}"
    if law == "T1":
        rest = [f"{c['failedFirst']} failed first"] + ([f"{c['expired']} expired"] if c["expired"] else []) + ([f"{c['stillInPlay']} still in play"] if c["stillInPlay"] else [])
        return (f"signed errors of the {n} of {c['patterns']} pooled {'in-play patterns' if inplay else 'patterns'} that broke ({', '.join(rest)}"
                + ("" if inplay else "; broken-at-confirmation included") + "); conditional on a break")
    return f"signed errors of the {n} of {c['broke']} pooled {'in-play breaks' if inplay else 'breaks'} that completed; conditional on completion"


def share_block(c, what):
    if c is None:
        return None
    if what == "break":
        return {"broke": c["broke"], "of": c["patterns"], "share": (round(c["broke"] / c["patterns"], 3) if c["patterns"] else None),
                "failedFirst": c["failedFirst"], "expired": c["expired"], "stillInPlay": c["stillInPlay"]}
    return {"completed": c["completed"], "ofBreaks": c["broke"], "share": (round(c["completed"] / c["broke"], 3) if c["broke"] else None)}


def describe_current(p, name, data, laws, verdicts, real_rows, ip_rows=None, ctx=None):
    """A pattern (or the nearest structure) as the reader needs it: dates, levels, neckline today, target, status and
    the time frame per law with the historical error band (T1, T3, T3alt: from the patterns in play at S2's
    confirmation, the subset a structure unbroken at its confirmation belongs to, unless the structure broke at or
    before its confirmation, which takes the all-pattern band; the other band beside it)."""
    ip_rows = real_rows if ip_rows is None else ip_rows
    d = data[name]
    w, dates, space, sign = d["weekly"], d["weekly"].index, d["space"], p["sign"]
    n = len(w)
    i = p["i"]
    last = n - 1
    candidate = bool(p.get("s2Provisional"))
    failed = [k for k, v in p["checks"].items() if not v]

    def nat(yv):
        return round(float(from_space(sign * yv, space)), 4)

    def nl(j):
        return p["v"]["T1"] + p["slope"] * (j - i["T1"])
    neck_today = nl(last)
    status = ("forming (S2 not confirmed)" if candidate else p["status"])
    if failed:
        status += "; not a detector pattern, fails " + ", ".join(failed)
    out = {"kind": p["kind"], "threshold": p["r"], "isDetectorPattern": bool(p["geometryOk"] and not candidate),
           "candidateS2Unconfirmed": candidate, "geometryOk": bool(p["geometryOk"]), "failedChecks": failed,
           "failedCheckMargins": [margin_text(k, p["checkDetails"][k]) for k in failed], "checkDetails": p["checkDetails"],
           "status": status,
           "pivots": {k: {"date": ds(dates[i[k]]), "level": round(float(w.values[i[k]]), 4)} for k in ("S1", "T1", "H", "T2", "S2")},
           "necklineToday": {"date": ds(dates[last]), "level": nat(neck_today)},
           "necklineAtS2": nat(nl(i["S2"])),
           "headHeightInSpace": round(float(p["head"]), 4),
           "measuredMoveTarget": nat(neck_today - p["head"]),
           "failLevel": {"rule": "a close beyond S2 before the break", "level": round(float(w.values[i["S2"]]), 4)},
           "lastWeeklyClose": {"date": ds(dates[last]), "level": round(float(w.values[last]), 4)},
           "lastDailyBar": d["lastDaily"],
           "distanceAboveNecklineInPatternDirection": round(float(sign * to_space(w.values[last], space) - neck_today), 4)}
    s2 = dates[i["S2"]]
    out["S2"] = {"date": ds(s2), "level": round(float(w.values[i["S2"]]), 4), "weeksSinceS2": int(last - i["S2"]), "provisional": candidate}
    if candidate and i["S2"] == last:
        out["S2"]["note"] = "S2 is the last weekly close (a provisional extreme, not a pivot): the S2-anchored dates move with every new extreme"
    out["horizontalNeckline"] = horizontal_neckline(p, w, dates, space)
    if not candidate and p["iBreak"] is not None:
        j = p["iBreak"]
        nb = nat(nl(j))
        out["breakDetail"] = {"week": ds(dates[j]), "close": round(float(w.values[j]), 4), "necklineAtBreak": nb,
                              "closeBeyondNecklinePoints": round(abs(float(w.values[j]) - nb), 4),
                              "closeBeyondNecklineInSpace": round(float(nl(j) - sign * to_space(w.values[j], space)), 4),
                              "necklineSlopePerWeekInSpace": round(float(sign * p["slope"]), 5), "space": space,
                              "brokenAtConfirmation": bool(p["brokenAtConfirmation"]), "s2ConfirmedWeek": ds(dates[p["conf"]]),
                              "breakMinusConfirmationWeeks": int(j - p["conf"]),
                              "necklineFailsRiseLimit": bool(not p["checks"]["necklineRise"])}
    if candidate:
        out["confirmation"] = {"rule": f"S2 is confirmed when a weekly close prints {p['r']} away from it in {space} space",
                               "closeNeeded": nat(p["confirmLevelY"])}
    else:
        out["inPlayWeek"] = ds(dates[p["conf"]])
        out["weeksInPlay"] = int(last - p["conf"])
        out["expiryWeek"] = ds(s2 + pd.Timedelta(weeks=EXPIRY_WEEKS))
        out["breakWeek"] = None if p["iBreak"] is None else ds(dates[p["iBreak"]])
        out["targetLevelAtBreak"] = None if p["targetY"] is None else nat(p["targetY"])
        out["completionWeek"] = None if p["iComp"] is None else ds(dates[p["iComp"]])
        out["failWeek"] = None if p["iFail"] is None else ds(dates[p["iFail"]])
        if p["iBreak"] is not None:
            back = sign * to_space(w.values[last], space) > nl(last)
            out["afterBreak"] = ("completed" if p["iComp"] is not None else
                                 ("broke, then closed back above the neckline; the measured move is still open" if back else "below the neckline, the measured move still open"))
    # time frames per law. Bands: a structure unbroken at its confirmation (in play, forming, or broken later) belongs
    # with the patterns in play at S2's confirmation; one that broke at or before its confirmation was never in play,
    # so it takes the all-pattern band; the other band is shown beside. T2's date is issued before S2 exists, so it
    # uses all patterns. A band for an event not seen by the data end is clipped at the earliest week it can happen.
    tf = {}
    S1T1, S1H, HS2, HT2, S1S2 = i["T1"] - i["S1"], i["H"] - i["S1"], i["S2"] - i["H"], i["T2"] - i["H"], i["S2"] - i["S1"]
    ctx = ctx or {}
    c_ip, c_all = ctx.get("inPlay"), ctx.get("all")
    bac = bool((not candidate) and p.get("brokenAtConfirmation"))
    next_week = dates[last] + pd.Timedelta(weeks=1)
    # a forming pattern joins the in-play set only once S2 confirms (next week at the earliest), and its break comes after
    first_inplay = dates[last] + pd.Timedelta(weeks=2) if candidate else next_week
    no_break_yet = candidate or p["iBreak"] is None
    # a failed or expired structure can no longer break under plan [1], so its bands are not clipped to the future
    can_break = no_break_yet and (candidate or p["status"] == "in-play")
    own = {}
    if bac:
        kb = int(p["iBreak"] - p["conf"])
        when = "in the week S2 confirmed" if kb == 0 else f"{-kb} week{'s' if kb < -1 else ''} before S2 confirmed ({ds(dates[p['conf']])})"
        for law in ("T1", "T3", "T3alt"):
            same, before = laws[law].get("ofWhichBreakInTheConfirmationWeek"), laws[law].get("ofWhichBreakBeforeConfirmation")
            own[law] = (f"this structure broke {when}, so it was never in play: its band is the all-pattern one, which includes the {same} pooled {law} rows "
                        f"broken in the confirmation week itself and {before} broken before it" + ("; no pooled pattern broke before its confirmation, so none in "
                                                                                                   "the sample is quite like it" if kb < 0 and not before else ""))

    def law_entry(law, when, e_in, e_all):
        """The primary band (in-play, or all-pattern for a structure broken at confirmation) and both labelled bands."""
        bi, ba = law_band(laws, law, True), law_band(laws, law, False)
        dbi, ni = date_band(when, (bi or {}).get("nRealPatterns"), (bi or {}).get("signedErrorIQRWeeks"), e_in)
        dba, na = date_band(when, (ba or {}).get("nRealPatterns"), (ba or {}).get("signedErrorIQRWeeks"), e_all)
        fi = band_from_text(law, c_ip, (bi or {}).get("nRealPatterns", 0), True)
        fa = band_from_text(law, c_all, (ba or {}).get("nRealPatterns", 0), False)
        e = {"bandSubset": ("all pooled patterns (broken at or before confirmation)" if bac else "pooled patterns in play at S2's confirmation"),
             "dateBandIQR": dba if bac else dbi, "bandFrom": fa if bac else fi, "historicalErrors": ba if bac else bi,
             "dateBandIQRInPlayAtConfirmation": dbi, "bandFromInPlayAtConfirmation": fi, "historicalErrorsInPlayAtConfirmation": bi,
             "dateBandIQRAllPatterns": dba, "bandFromAllPatterns": fa, "historicalErrorsAllPatterns": ba}
        notes = [x for x in (own.get(law), (na if bac else ni)) if x]
        if notes:
            e["bandNote"] = "; ".join(notes)
        other = ni if bac else na
        if other:
            e["bandNoteOther"] = other
        return e
    pred_break = s2 + pd.Timedelta(weeks=S1T1)
    notes = []
    if pred_break < dates[last] and no_break_yet:
        notes.append(f"the T1 date is {int((dates[last] - pred_break).days // 7)} weeks past with no break")
    if not candidate and pred_break <= dates[p["conf"]]:
        notes.append(f"the T1 date was on or before the in-play week {ds(dates[p['conf']])}, so the forecast was already past when the pattern became usable")
    if candidate:
        notes.insert(0, "conditional on the provisional S2 confirming without closing beyond the neckline (the band's patterns were in play at confirmation)")
    tf["T1"] = {"rule": "break = S2 + (T1 - S1)", "weeksFromS2": int(S1T1), "breakWeek": ds(pred_break),
                **law_entry("T1", pred_break, *((first_inplay, next_week) if can_break else (None, None))),
                "breakShare": {"inPlayAtConfirmation": share_block(c_ip, "break"), "allPatterns": share_block(c_all, "break")},
                "verdict": verdicts["T1"], "note": ("; ".join(notes) if notes else None)}
    if not no_break_yet:
        tf["T1"]["actualBreakWeek"] = ds(dates[p["iBreak"]])
        tf["T1"]["errorWeeks"] = int(S1T1 - (p["iBreak"] - i["S2"]))

    def base_entry(rows_, law, anchor_date, earliest, inplay, wkey, dkey, rule):
        """Today's expanding-median base rate at the structure's threshold, with the band from the signed errors of past
        base-rate predictions at that same threshold (the baseline is per threshold, so its errors are too)."""
        cb = current_baseline(rows_, law, p["r"])
        if cb is None:
            return None
        when = anchor_date + pd.Timedelta(weeks=cb["weeks"])
        st = summ([x["errBase"] for x in rows_ if x["law"] == law and x["r"] == p["r"] and x["pool"] and x["errBase"] is not None])
        band, bnote = date_band(when, st.get("n"), st.get("signedIQR"), earliest)
        subset = "patterns in play at confirmation" if inplay else "all patterns"
        e = {"rule": rule, "subset": ("in-play" if inplay else "all-pattern"), wkey: cb["weeks"], "nPatterns": cb["nPatterns"], dkey: ds(when),
             "dateBandIQR": band, "bandFrom": f"signed errors of the {st['n']} past base-rate predictions at the structure's threshold r={p['r']} ({subset})",
             "bandN": st["n"], "medianAbsErrorWeeks": st.get("medianAbs")}
        if bnote:
            e["bandNote"] = bnote
        return e
    e_in, e_all = (first_inplay, next_week) if can_break else (None, None)
    bb_ip = base_entry(ip_rows, "T1", s2, e_in, True, "weeksFromS2", "breakWeek",
                       "break = S2 + expanding median of S2 -> break over the patterns in play at confirmation known to date (same threshold, all series)")
    bb_all = base_entry(real_rows, "T1", s2, e_all, False, "weeksFromS2", "breakWeek",
                        "break = S2 + expanding median of S2 -> break over every pattern known to date, broken-at-confirmation included (same threshold, all series)")
    for e in (bb_ip, bb_all):
        if e is not None and no_break_yet and pd.Timestamp(e["breakWeek"]) < dates[last]:
            e["note"] = f"the base-rate date is {int((dates[last] - pd.Timestamp(e['breakWeek'])).days // 7)} weeks past with no break"
    prim = bb_all if bac else bb_ip
    if prim is not None:
        tf["baselineForBreak"] = dict(prim)
    if bb_ip is not None:
        tf["baselineForBreakInPlayAtConfirmation"] = bb_ip
    if bb_all is not None:
        tf["baselineForBreakAllPatterns"] = bb_all
    pred_s2 = dates[i["H"]] + pd.Timedelta(weeks=S1H)
    ba2 = law_band(laws, "T2", False)
    dba2, na2 = date_band(pred_s2, (ba2 or {}).get("nRealPatterns"), (ba2 or {}).get("signedErrorIQRWeeks"))
    tf["T2"] = {"rule": "S2 = H + (H - S1)", "predictedWeeksHToS2": int(S1H), "predictedS2Week": ds(pred_s2),
                "dateBandIQR": dba2, "bandFrom": ("all pooled patterns (the T2 date is issued before S2 exists; the in-play split is decided at S2's "
                                                  "confirmation, T2's outcome week, so no T2 band uses it)"),
                "historicalErrors": ba2, "verdict": verdicts["T2"], "actualWeeksHToS2": int(HS2),
                "note": (f"the provisional S2 is {int(HS2)} weeks after H; descriptive only: T2 is scored on patterns selected by their later S2" if candidate else
                         "S2 is confirmed; shown for the record (T2 is descriptive symmetry on completed patterns, not a point-in-time forecast)")}
    if na2:
        tf["T2"]["bandNote"] = na2
    anchor_actual = (not candidate) and p["iBreak"] is not None
    anchor = dates[p["iBreak"]] if anchor_actual else pred_break
    completed = anchor_actual and p["iComp"] is not None
    # completion can print in the break week itself, so its earliest week is the break's earliest week (or next week);
    # no clipping once the completion can no longer count (completed, its window closed, or no break possible)
    can_complete = (anchor_actual and not completed and bool(p.get("completionWindowOpen"))) or (not anchor_actual and can_break)
    ec_in, ec_all = (None, None) if not can_complete else ((next_week, next_week) if anchor_actual else (first_inplay, next_week))
    for law, weeks in (("T3", HT2), ("T3alt", 0.5 * S1S2)):
        pred_c = anchor + pd.Timedelta(weeks=weeks)
        tf[law] = {"rule": ("completion = break + (T2 - H)" if law == "T3" else "completion = break + 0.5 x (S2 - S1)"), "weeksAfterBreak": round(float(weeks), 1),
                   "anchor": ("the actual break week" if anchor_actual else "the T1 break week"), "completionWeek": ds(pred_c),
                   **law_entry(law, pred_c, ec_in, ec_all),
                   "completionShare": {"inPlayAtConfirmation": share_block(c_ip, "completion"), "allPatterns": share_block(c_all, "completion")},
                   "verdict": verdicts[law], "bias": laws[law].get("actualOverPredicted", {}).get("real")}
        if completed:
            tf[law]["actualCompletionWeek"] = ds(dates[p["iComp"]])
            tf[law]["errorWeeks"] = round(float(weeks - (p["iComp"] - p["iBreak"])), 1)
        elif anchor_actual and pred_c < dates[last]:
            tf[law]["note"] = f"the {law} date is {int((dates[last] - pred_c).days // 7)} weeks past without completion"
    bc_ip = base_entry(ip_rows, "T3", anchor, ec_in, True, "weeksAfterBreak", "completionWeek",
                       "completion = break + expanding median of break -> target over the patterns in play at confirmation known to date (same threshold, all series)")
    bc_all = base_entry(real_rows, "T3", anchor, ec_all, False, "weeksAfterBreak", "completionWeek",
                        "completion = break + expanding median of break -> target over every pattern known to date (same threshold, all series)")
    for e in (bc_ip, bc_all):
        if e is not None and not completed and pd.Timestamp(e["completionWeek"]) < dates[last]:
            e["note"] = f"the base-rate date is {int((dates[last] - pd.Timestamp(e['completionWeek'])).days // 7)} weeks past without completion"
    prim = bc_all if bac else bc_ip
    if prim is not None:
        tf["baselineForCompletion"] = dict(prim)
    if bc_ip is not None:
        tf["baselineForCompletionInPlayAtConfirmation"] = bc_ip
    if bc_all is not None:
        tf["baselineForCompletionAllPatterns"] = bc_all
    out["timeFrames"] = tf
    return out


def pivots_list(zz, name, data, k=5):
    d = data[name]
    w, dates = d["weekly"], d["weekly"].index
    pi, pt, pc, dd, prov = zz
    out = []
    for j in range(max(0, len(pi) - k), len(pi)):
        out.append({"date": ds(dates[pi[j]]), "level": round(float(w.values[pi[j]]), 4), "type": ("peak" if pt[j] == 1 else "trough"), "confirmed": ds(dates[pc[j]])})
    provisional = None
    if prov >= 0:
        provisional = {"date": ds(dates[prov]), "level": round(float(w.values[prov]), 4), "type": ("peak" if dd == 1 else "trough"), "confirmed": None,
                       "note": "provisional extreme, not a pivot until the reversal prints"}
    return out, provisional


def stage_text(stage):
    if not stage:
        return "fewer than one pivot of the expected orientation confirmed"
    s = ", ".join(f"{c['pivot']} {c['date']} ({c['level']})" for c in stage["confirmed"]) + " confirmed"
    if stage["provisional"]:
        pv = stage["provisional"]
        s += f"; {pv['pivot']} provisional at {pv['date']} ({pv['level']}), confirmed by a close at {pv['confirmsAtClose']}"
    return s


def horiz_text(ns):
    """The horizontal-neckline reading of a confirmed structure, in words."""
    h = ns.get("horizontalNeckline")
    if not h or ns.get("candidateS2Unconfirmed"):
        return ""
    d = h["distanceOnUnbrokenSide"]
    side = "below" if ns["kind"] == "top" else "above"
    u = "pp" if d["unit"].startswith("percentage") else "USD"
    if h["closedBeyondSinceS2"]:
        return f"; on a horizontal neckline through T2 ({h['level']}) it first closed {side} that level on {h['firstCloseBeyond']}"
    return (f"; on a horizontal neckline through T2 ({h['level']}) it has not closed {side} it since S2 (last close {h['lastClose']['level']}, "
            f"{abs(d['points'])} {u} / {abs(d['pct'])}% on the unbroken side)")


def break_text(ns):
    """How decisive the sloped-neckline break was, in words."""
    b = ns.get("breakDetail")
    if not b:
        return ""
    u = "pp" if b["space"] == "logit" else "USD"
    s = (f"; the break close {b['close']} was {b['closeBeyondNecklinePoints']} {u} beyond a neckline at {b['necklineAtBreak']} "
         f"({'rising' if b['necklineSlopePerWeekInSpace'] > 0 else 'falling'} {abs(b['necklineSlopePerWeekInSpace'])} per week in {b['space']} space"
         + (", a neckline that itself fails the rise limit)" if b["necklineFailsRiseLimit"] else ")"))
    k = b["breakMinusConfirmationWeeks"]
    if k < 0:
        s += f", {-k} week{'s' if k < -1 else ''} before S2 confirmed ({b['s2ConfirmedWeek']})"
    elif k == 0:
        s += ", in the week S2 confirmed"
    return s


def finding_text(b, expected):
    ip, ns = b["patternInPlay"], b["nearestStructure"]
    if ip:
        return (f"{ip['kind']} pattern in play since {ip['inPlayWeek']} (S2 {ip['S2']['date']} at {ip['S2']['level']}); neckline today {ip['necklineToday']['level']}, "
                f"measured-move target {ip['measuredMoveTarget']}")
    if ns is None:
        stages = "; ".join(f"{k}: {stage_text(v)}" for k, v in b["formingStage"].items())
        return f"no pattern in play and no five-pivot structure with the head as the extreme in the last {NEAR_LOOKBACK} weeks; pivots at the data end: {stages}"
    piv = ns["pivots"]
    where = f"S1 {piv['S1']['date']} ({piv['S1']['level']}), T1 {piv['T1']['date']}, H {piv['H']['date']} ({piv['H']['level']}), T2 {piv['T2']['date']}, S2 {piv['S2']['date']} ({piv['S2']['level']}{', provisional' if ns['candidateS2Unconfirmed'] else ''})"
    if ns["candidateS2Unconfirmed"] and ns["geometryOk"]:
        return (f"no confirmed pattern in play; {article(ns['kind'])} {ns['kind']} pattern is forming: {where}; S2 confirms on a close "
                f"{'below' if ns['kind'] == 'top' else 'above'} {ns['confirmation']['closeNeeded']}; neckline today {ns['necklineToday']['level']}, target {ns['measuredMoveTarget']}")
    if ns["geometryOk"]:
        s = f"no pattern in play; the latest {ns['kind']} pattern ({where}) is {ns['status']}"
        if ns.get("breakWeek"):
            s += f": broke {ns['breakWeek']}" + (f", completed {ns['completionWeek']}" if ns.get("completionWeek") else f" ({ns.get('afterBreak')})") + break_text(ns)
        elif ns.get("failWeek"):
            s += f": failed {ns['failWeek']}"
        return s + horiz_text(ns)
    s = f"no pattern in play; the nearest {ns['kind']} structure ({where}) fails {', '.join(ns['failedChecks'])} ({'; '.join(ns['failedCheckMargins'])})"
    if not ns["candidateS2Unconfirmed"]:
        if ns.get("breakWeek"):
            s += (f"; read as a pattern anyway it closed beyond its neckline on {ns['breakWeek']} (target {ns['targetLevelAtBreak']})"
                  + (f" and completed on {ns['completionWeek']}" if ns.get("completionWeek") else f" ({ns.get('afterBreak')})") + break_text(ns))
        elif ns.get("failWeek"):
            s += f"; read as a pattern anyway it failed on {ns['failWeek']}"
        else:
            s += f"; read as a pattern anyway it is unbroken (neckline today {ns['necklineToday']['level']}, target {ns['measuredMoveTarget']})"
        s += horiz_text(ns)
    return s


def current_report(data, real, zz_by, laws, verdicts, real_rows, thresholds, ip_rows=None):
    cur = {}
    ctx = band_context(real)
    for name, expected in CURRENT.items():
        if name not in data:
            cur[name] = {"note": "series not available"}
            continue
        d = data[name]
        block = {"expectedKind": expected, "space": d["space"], "lastWeeklyClose": {"date": ds(d["weekly"].index[-1]), "level": round(float(d["weekly"].values[-1]), 4)},
                 "lastDailyBar": d["lastDaily"],
                 "howToRead": ("patternInPlay is the detector's own finding; nearestStructure is the five-pivot window of the expected kind in the last "
                               f"{NEAR_LOOKBACK} weeks that fails the fewest geometry checks (a detector pattern only when isDetectorPattern); formingStage says how "
                               "much of S1 T1 H T2 S2 is confirmed today")}
        signs = (1,) if expected == "top" else (-1,) if expected == "inverse" else (1, -1)
        for r in thresholds:
            pats = [p for p in real if p["series"] == name and p["r"] == r]
            ok = (lambda p: True) if expected == "either" else (lambda p: p["kind"] == expected)
            inplay = sorted([p for p in pats if p["status"] == "in-play" and ok(p)], key=lambda p: p["i"]["S2"])
            other = sorted([p for p in pats if p["status"] == "in-play" and not ok(p)], key=lambda p: p["i"]["S2"])
            recent = sorted([p for p in pats if ok(p)], key=lambda p: p["i"]["S2"])
            zz = zz_by[(name, r)]
            nears = [s for s in (nearest_structure(d["x"], zz, r, sg) for sg in signs) if s is not None]
            near = min(nears, key=lambda p: (n_fail(p), -p["i"]["S2"])) if nears else None
            stages = {("top" if sg == 1 else "inverse"): forming_stage(d["x"], zz, r, sg, d["weekly"].index, d["weekly"], d["space"]) for sg in signs}
            piv, prov = pivots_list(zz, name, data)
            b = {"threshold": r,
                 "patternInPlay": (describe_current(inplay[-1], name, data, laws, verdicts, real_rows, ip_rows, ctx) if inplay else None),
                 "otherKindInPlay": (describe_current(other[-1], name, data, laws, verdicts, real_rows, ip_rows, ctx) if other else None),
                 "nearestStructure": (describe_current(near, name, data, laws, verdicts, real_rows, ip_rows, ctx) if near is not None else None),
                 "formingStage": stages,
                 "latestPatternOfExpectedKind": (describe_current(recent[-1], name, data, laws, verdicts, real_rows, ip_rows, ctx) if recent else None),
                 "lastFivePivots": piv, "provisionalExtreme": prov, "nPatternsOnSeries": len(pats)}
            b["finding"] = finding_text(b, expected)
            block[f"r={r}"] = b
        rows = r_sweep(expected, d)
        groups, none = sweep_groups(rows)
        block["rSweep"] = {"thresholds": list(SWEEP_R), "rows": rows, "groups": groups, "thresholdsWithoutStructure": none, "summary": sweep_text(groups, none),
                           "note": ("reporting for plan [3] only: the same detector and geometry at other reversal thresholds (the law tests use the plan's "
                                    "two); each row is the pattern in play, else the nearest structure, with the check it fails and by how much, its status "
                                    "and the horizontal-neckline reading")}
        cur[name] = block
    return cur


def pick_current(cur, name, thresholds):
    """The structure the reading uses: a pattern in play, else the nearest structure with the fewest failed checks
    (a forming one preferred over a stale one at equal failures), else nothing."""
    b = cur.get(name, {})
    for r in thresholds:
        k = b.get(f"r={r}")
        if k and k["patternInPlay"]:
            return r, k["patternInPlay"], "in play"
    best = None
    for r in thresholds:
        k = b.get(f"r={r}")
        ns = k["nearestStructure"] if k else None
        if ns:
            score = (len(ns["failedChecks"]), 0 if ns["candidateS2Unconfirmed"] else 1)
            if best is None or score < best[0]:
                best = (score, r, ns)
    if best is None:
        return None, None, "none"
    _, r, ns = best
    if ns["candidateS2Unconfirmed"]:
        state = "forming (S2 provisional)" if ns["geometryOk"] else "forming but failing " + ", ".join(ns["failedChecks"])
    elif ns["geometryOk"]:
        state = ns["status"]
    else:
        state = "nearest structure, failing " + ", ".join(ns["failedChecks"])
    return r, ns, state


def btc_condition(pb):
    """What a fresh BTC.D fall still needs, on the level not met yet: a structure already below its sloped neckline but
    never closed below its T2 level is conditioned on the horizontal neckline, with both levels named."""
    last = pb["lastWeeklyClose"]["level"]
    h = pb.get("horizontalNeckline") or {}
    below_sloped = pb.get("distanceAboveNecklineInPatternDirection") is not None and pb["distanceAboveNecklineInPatternDirection"] < 0
    if h and not h.get("closedBeyondSinceS2") and not pb.get("candidateS2Unconfirmed"):
        return (f"BTC.D closing below its T2 level {h['level']}% (today {last}%; "
                + (f"it is already below the sloped neckline at {pb['necklineToday']['level']}%, so that line is no condition" if below_sloped else
                   f"the sloped neckline is at {pb['necklineToday']['level']}%") + ")")
    if below_sloped:
        return f"BTC.D staying below its sloped neckline at {pb['necklineToday']['level']}% (today {last}%)"
    return f"BTC.D closing below its neckline at {pb['necklineToday']['level']}% (today {last}%)"


def joint_reading(cur, laws, verdicts, thresholds, rates):
    def sentence(name, unit):
        r, p, state = pick_current(cur, name, thresholds)
        if p is None:
            return f"{name}: the detector finds no head-and-shoulders structure of the expected kind at either threshold."
        tf, pv = p["timeFrames"], p["pivots"]
        s = (f"{name}: {article(p['kind'])} {p['kind']} structure at r={r}, {state} (S1 {pv['S1']['date']} {pv['S1']['level']}{unit}, H {pv['H']['date']} {pv['H']['level']}{unit}, "
             f"S2 {pv['S2']['date']} {pv['S2']['level']}{unit}{', provisional' if p['candidateS2Unconfirmed'] else ''})")
        if p["failedChecks"]:
            s += f" - it misses the detector's limits ({'; '.join(p['failedCheckMargins'])}), so it is read here as a structure, not a pattern"

        def late(law):
            return f" ({tf[law]['note']})" if tf[law].get("note") else ""
        if p.get("breakWeek"):
            s += f"; it closed beyond its neckline on {p['breakWeek']} with the measured-move target at {p['targetLevelAtBreak']}{unit}" + break_text(p)
            if p.get("completionWeek"):
                s += f" and completed on {p['completionWeek']}"
            else:
                s += (f"; today {p['lastWeeklyClose']['level']}{unit} against a neckline of {p['necklineToday']['level']}{unit} ({p.get('afterBreak')})"
                      f"; T3 puts completion {tf['T3']['weeksAfterBreak']} weeks after that break, {tf['T3']['completionWeek']}{late('T3')}; "
                      f"T3alt {tf['T3alt']['weeksAfterBreak']} weeks, {tf['T3alt']['completionWeek']}{late('T3alt')}")
                bc = tf.get("baselineForCompletion")
                if bc:
                    s += (f"; the {bc['subset']} base rate {bc['completionWeek']} (break + {bc['weeksAfterBreak']} weeks"
                          + (f", {bc['note']}" if bc.get("note") else "")
                          + (f"; IQR band {bc['dateBandIQR'][0]} to {bc['dateBandIQR'][1]}" + (", its lower edge clipped to the first week still possible" if "clipped" in str(bc.get("bandNote")) else "")
                             if bc.get("dateBandIQR") else f"; no band, only {bc['bandN']} past base-rate errors at r={r}") + ")")
        elif p.get("failWeek"):
            s += f"; it failed on {p['failWeek']} (a close beyond S2 before any break)"
        elif str(p.get("status", "")).startswith("expired"):
            s += "; it expired without a break"
        else:
            t1 = tf["T1"]
            band = t1["dateBandIQR"]
            s += f"; neckline today {p['necklineToday']['level']}{unit}, measured-move target {p['measuredMoveTarget']}{unit}"
            bs = (t1.get("breakShare") or {}).get("inPlayAtConfirmation") or {}
            nb = (t1.get("historicalErrors") or {}).get("nRealPatterns")
            s += f"; T1 symmetry puts the break at {t1['breakWeek']}" + (
                (f" (IQR band {band[0]} to {band[1]} from the {nb} of {bs['of']} pooled in-play patterns that broke; {bs['failedFirst']} failed first, so the band "
                 "is conditional on a break)") if band and bs else (f" (IQR band {band[0]} to {band[1]}, {t1['bandFrom']})" if band else ""))
            if t1.get("note"):
                s += f" - {t1['note']}"
            bb = tf.get("baselineForBreak")
            if bb:
                s += (f"; the {bb['subset']} base-rate date is {bb['breakWeek']} (S2 + {bb['weeksFromS2']} weeks, n={bb['nPatterns']}"
                      + (f", IQR band {bb['dateBandIQR'][0]} to {bb['dateBandIQR'][1]}" if bb.get("dateBandIQR") else
                         f"; no band, only {bb['bandN']} past base-rate errors at r={r}") + ")")
            s += f"; T3 then puts the target {tf['T3']['weeksAfterBreak']} weeks after the break ({tf['T3']['completionWeek']}), T3alt {tf['T3alt']['weeksAfterBreak']} weeks ({tf['T3alt']['completionWeek']})"
            bias = tf["T3"].get("bias") or {}
            if bias.get("median"):
                s += f", though break -> target has run a median {bias['median']} x the H -> T2 duration T3 uses"
        s += horiz_text(p)
        if p["S2"].get("note"):
            s += f"; {p['S2']['note']}"
        s += sweep_clause(cur, name, p)
        return s + "."
    parts = [sentence("BTC.D", "%"), sentence("USDT.D", "%"), sentence("ETHUSD", " USD")]
    rb, pb, sb = pick_current(cur, "BTC.D", thresholds)
    ru, pu, su = pick_current(cur, "USDT.D", thresholds)

    def live(p, kind):   # an unfinished structure of the kind: in play, forming, unbroken, or broken with the measured move open
        return (p is not None and p["kind"] == kind and not p.get("completionWeek") and not p.get("failWeek")
                and not str(p.get("status", "")).startswith("expired"))

    def done(p, kind):
        return p is not None and p["kind"] == kind and bool(p.get("completionWeek"))
    btc_down, usdt_up = live(pb, "top"), live(pu, "inverse")
    rare = "the rare kind in round 10 (14 of 16 BTC.D falls since 2016 were alt-led)"
    if btc_down and usdt_up:
        joint = (f"Joint reading: a BTC.D top and a USDT.D inverse live at the same time describe a stables-gaining fall, {rare}: if both necklines go, the share "
                 "BTC.D loses is taken by stables rather than by alts, so TOTAL3 and OTHERS.D need not gain and the alt season a dominance fall usually implies is "
                 "not what these two structures together say.")
    elif btc_down and done(pu, "inverse"):
        joint = (f"Joint reading: the pairing has already happened once: USDT.D's inverse broke its neckline on {pu['breakWeek']} and completed on {pu['completionWeek']} "
                 "(stables gaining share), while BTC.D's structure "
                 + (f"closed beyond its neckline on {pb['breakWeek']}" if pb.get("breakWeek") else "had not broken its neckline")
                 + f"; yet BTC.D stands at {pb['lastWeeklyClose']['level']}% against a measured-move target of {pb.get('targetLevelAtBreak') or pb['measuredMoveTarget']}%, "
                 f"so the stables-gaining fall did not follow through. A fresh one, {rare}, needs a new USDT.D up-leg from today's {pu['lastWeeklyClose']['level']}% "
                 f"together with {btc_condition(pb)}; without it a BTC.D fall from here reads as the common alt-led kind.")
    elif btc_down:
        joint = (f"Joint reading: the BTC.D top without a live USDT.D inverse is the common alt-led kind of fall ({rare}); the stables-gaining reading needs USDT.D "
                 "to turn up through a neckline of its own, and today its inverse structure is " + (su if pu is not None else "absent") + ".")
    elif usdt_up:
        joint = ("Joint reading: USDT.D rising without a BTC.D top in play is a risk-off tilt inside the market rather than a dominance fall; "
                 "the two-pattern stables-gaining reading needs BTC.D to lose its neckline.")
    else:
        joint = "Joint reading: with neither structure live the two-pattern stables-gaining reading does not apply today."
    fragile = []
    for nm, p_ in (("BTC.D", pb), ("USDT.D", pu)):
        if p_ is None:
            continue
        g, allr = sweep_group_of(cur, nm, p_)
        if g is not None and (g["statusChangesWithR"] or len(g["rs"]) < len(allr)):
            fragile.append(f"{nm}'s structure is found at r={_rs(g['rs'])} of the {len(allr)} thresholds swept" + (" and its status changes with r" if g["statusChangesWithR"] else ""))
        h = p_.get("horizontalNeckline") or {}
        if p_.get("breakWeek") and h and not h.get("closedBeyondSinceS2"):
            fragile.append(f"{nm}'s break exists on the sloped neckline only (no weekly close beyond its T2 level {h['level']} since S2)")
    if fragile:
        joint += " The pairing is fragile: " + "; ".join(fragile) + "."
    v = ", ".join(f"{k} {('supported' if verdicts[k] == 'supported' else 'not supported')}" for k in LAWS)
    t1 = laws["T1"]
    t1i = t1.get("inPlayAtConfirmation") or {}
    rr = rates["real"]["breakWithinWeeksOfInPlay"]

    def pc(x):
        return "n/a" if x is None else f"{100 * x:.0f}%"
    tail = f" Timing laws: {v}. {placebo_wording(laws)}; {scale_wording(laws)}."
    if t1i:
        tail += (f" On the patterns still in play at S2's confirmation T1's median |error| is {t1i['real'].get('medianAbs')} weeks (n={t1i['real'].get('n')}) against "
                 f"{t1i['baseline'].get('medianAbs')} for their expanding base rate and {t1i['placebo'].get('medianAbs')} on placebos (p={t1i['pooledTest']['p']}); "
                 f"{t1.get('rowsFromPatternsBrokenAtConfirmation')} of the {t1['nRealPool']} pooled T1 rows broke at or before the confirmation week "
                 f"({t1.get('ofWhichBreakInTheConfirmationWeek')} in that week itself, {t1.get('ofWhichBreakBeforeConfirmation')} before it), and on all rows the median "
                 f"|error| is {t1['real'].get('medianAbs')} weeks; so a structure not broken by its confirmation takes the in-play bands above, one broken at or "
                 "before it the all-pattern bands, and none of the dates is more than a base-rate guess.")
    tail += (f" Rates: the sloped neckline broke within 13/26/52 weeks of the in-play week in {pc(rr['13']['rate'])}/{pc(rr['26']['rate'])}/{pc(rr['52']['rate'])} "
             f"of in-play patterns (n={rr['52']['n']}), a fail-censored share that is not a base-rate comparison")
    me = rates.get("matchedEqualMove") or {}
    fx, tg = me.get("fixedLevelNecklineBreakWithinWeeksOfInPlay", {}), me.get("targetWithinWeeksOfBreak", {})
    if fx and all(fx.get(str(H), {}).get("eraInSample", {}).get("n") for H in H_BREAK):
        e = [fx[str(H)]["eraInSample"] for H in H_BREAK]
        x_ = [fx[str(H)]["eraExcludingOwnWeeks"] for H in H_BREAK]
        tail += (f"; the plan's comparison, a close beyond the neckline level fixed at the in-play week, came within 13/26/52 weeks in "
                 f"{'/'.join(pc(a['eventRate']) for a in e)} against {'/'.join(pc(a['matchedBaseRate']) for a in e)} for an equal move from any week of the same "
                 f"series and era (in-sample, n={'/'.join(str(a['n']) for a in e)}); without the pattern's own weeks {'/'.join(pc(a.get('eventRate')) for a in x_)} "
                 f"against {'/'.join(pc(a.get('matchedBaseRate')) for a in x_)} (n={'/'.join(str(a.get('n')) for a in x_)})")
    if tg and all(tg.get(str(H), {}).get("eraInSample", {}).get("n") for H in H_TARGET):
        e = [tg[str(H)]["eraInSample"] for H in H_TARGET]
        tail += (f", and the target within 26/52 weeks of the break in {'/'.join(pc(a['eventRate']) for a in e)} against {'/'.join(pc(a['matchedBaseRate']) for a in e)} "
                 f"(z {'/'.join(str(a['z']) for a in e)}, optimistic for dependent patterns)")
    tail += "."
    return " ".join(parts) + " " + joint + tail


# ------------------------------------------------------------------------------------------------- charts
def style_axes(ax):
    ax.set_facecolor(COL["bg"])
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(COL["grid"])
    ax.grid(True, color=COL["grid"], lw=0.8)
    ax.tick_params(colors=COL["text2"], labelsize=9)
    ax.title.set_color(COL["text"])


def best_corner(ax, txt, pts):
    """The axes corner whose (estimated) text-box area covers the fewest of the given data points; ties keep the upper
    left. Returns (x, y, ha, va) in axes fractions."""
    lines = txt.split("\n")
    w = min(0.98, 0.0056 * max(len(s) for s in lines) + 0.02)
    h = min(0.9, 0.042 * len(lines) + 0.03)
    ax.get_xlim(), ax.get_ylim()                       # settle the autoscaled view before transforming
    xy = (ax.transScale + ax.transLimits).transform(pts)
    cands = [((0.01, 0.97, "left", "top"), (0.01, 0.01 + w, 0.97 - h, 0.97)), ((0.99, 0.97, "right", "top"), (0.99 - w, 0.99, 0.97 - h, 0.97)),
             ((0.01, 0.03, "left", "bottom"), (0.01, 0.01 + w, 0.03, 0.03 + h)), ((0.99, 0.03, "right", "bottom"), (0.99 - w, 0.99, 0.03, 0.03 + h))]

    def covered(c):
        x0, x1, y0, y1 = c[1]
        return int(((xy[:, 0] >= x0) & (xy[:, 0] <= x1) & (xy[:, 1] >= y0) & (xy[:, 1] <= y1)).sum())
    return min(cands, key=covered)[0]


def chart_current(out_dir, r, data, cur, zz_by, real):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter, NullLocator
    names = [n for n in CURRENT if n in data]
    fig, axes = plt.subplots(len(names), 1, figsize=(12, 4.4 * len(names)), dpi=100, constrained_layout=True)
    fig.patch.set_facecolor(COL["bg"])
    axes = np.atleast_1d(axes)
    handles, labels = [], []
    for ax, name in zip(axes, names):
        style_axes(ax)
        d = data[name]
        w, dates, space = d["weekly"], d["weekly"].index, d["space"]
        n = len(w)
        b = cur[name][f"r={r}"]
        pat = b["patternInPlay"] or b["nearestStructure"]
        live = None
        if b["patternInPlay"]:
            live = max([p for p in real if p["series"] == name and p["r"] == r and p["status"] == "in-play" and (CURRENT[name] == "either" or p["kind"] == CURRENT[name])], key=lambda p: p["i"]["S2"])
        elif b["nearestStructure"]:
            sign = 1 if b["nearestStructure"]["kind"] == "top" else -1
            live = nearest_structure(d["x"], zz_by[(name, r)], r, sign)
        start = n - 208
        if live is not None:
            start = min(start, live["i"]["S1"] - 20)
        start = max(0, start)
        ax.plot(dates[start:], w.values[start:], color=COL["text2"], lw=1.4, label="weekly close")
        pi, pt, pc, dd, prov = zz_by[(name, r)]
        sel = pi[pi >= start]
        ax.scatter(dates[sel], w.values[sel], s=18, color=COL["yellow"], zorder=3, label=f"confirmed pivots (r={r})")
        if live is not None:
            sign, i = live["sign"], live["i"]
            cand = bool(live.get("s2Provisional"))
            open_ended = cand or live.get("status") == "in-play" or (live.get("iBreak") is not None and live.get("iComp") is None)
            for k in ("S1", "T1", "H", "T2", "S2"):
                j = i[k]
                ax.scatter([dates[j]], [w.values[j]], s=70, facecolor=(COL["bg"] if (cand and k == "S2") else COL["blue"]), edgecolor=COL["blue"], lw=1.6, zorder=4)
                ax.annotate(k + ("?" if (cand and k == "S2") else ""), (dates[j], w.values[j]), textcoords="offset points",
                            xytext=(0, 9 if (k in ("S1", "H", "S2")) == (sign == 1) else -14), ha="center", fontsize=9, color=COL["text"])
            end = n - 1 + 30 if open_ended else min(n - 1 + 30, max(v for v in (live.get("iComp"), live.get("iBreak"), live.get("iFail"), i["S2"]) if v is not None) + 20)
            js = np.arange(i["T1"], end + 1)
            dts = [dates[j] if j < n else dates[-1] + pd.Timedelta(weeks=int(j - n + 1)) for j in js]
            nl = live["v"]["T1"] + live["slope"] * (js - i["T1"])
            ax.plot(dts, from_space(sign * nl, space), color=COL["orange"], lw=1.8, ls="--", label="neckline (T1-T2, extended)")
            t0 = i["T2"] - i["T1"]
            ax.plot(dts[t0:], from_space(sign * (nl - live["head"]), space)[t0:], color=COL["aqua"], lw=1.6, ls=":", label="measured-move target")
            ax.plot([dts[t0], dts[-1]], [w.values[i["T2"]]] * 2, color=COL["text2"], lw=1.0, ls=(0, (1, 2)), label="T2 level (horizontal neckline)")
            if live.get("iBreak") is not None:
                ax.scatter([dates[live["iBreak"]]], [w.values[live["iBreak"]]], marker="x", s=70, color=COL["orange"], zorder=5, label="neckline break")
            if live.get("iComp") is not None:
                ax.scatter([dates[live["iComp"]]], [w.values[live["iComp"]]], marker="D", s=45, color=COL["aqua"], zorder=5, label="target reached")
            if live.get("iFail") is not None:
                ax.scatter([dates[live["iFail"]]], [w.values[live["iFail"]]], marker="v", s=60, color=COL["orange"], zorder=5, label="pattern failed")
            tfp = pat["timeFrames"]["T1"]
            txt = f"{pat['kind']}: {pat['status']}"
            if pat["failedChecks"]:
                txt += "\n" + "; ".join(pat["failedCheckMargins"])
            open_still = cand or (live.get("iBreak") is None and live.get("iFail") is None and live.get("status") != "expired")
            if open_still:
                txt += f"\nneckline today {pat['necklineToday']['level']}, measured move {pat['measuredMoveTarget']}"
                pbd = pd.Timestamp(tfp["breakWeek"])
                band = tfp["dateBandIQR"]
                if band:
                    ax.axvspan(pd.Timestamp(band[0]), pd.Timestamp(band[1]), color=COL["blue"], alpha=0.08, lw=0)
                ax.axvline(pbd, color=COL["blue"], lw=1.0, ls="-.", label="T1 break date (band = error IQR of the in-play patterns that broke)")
                nbi = (tfp.get("historicalErrors") or {}).get("nRealPatterns")
                bs = (tfp.get("breakShare") or {}).get("inPlayAtConfirmation") or {}
                txt += f"\nT1 break {tfp['breakWeek']}" + (f" [{band[0]} .. {band[1]}: {nbi} of {bs.get('of')} in-play patterns broke, "
                                                           f"{bs.get('failedFirst')} failed first]" if band else "")
                bb = pat["timeFrames"].get("baselineForBreak")
                if bb:
                    txt += f"\n{bb['subset']} base rate {bb['breakWeek']} (r={pat['threshold']}, n={bb['nPatterns']})"
            elif live.get("iBreak") is not None:
                txt += f"\nbroke {pat['breakWeek']}, target at the break {pat['targetLevelAtBreak']}"
                txt += (f", completed {pat['completionWeek']}" if pat.get("completionWeek") else f"\nneckline today {pat['necklineToday']['level']}; T3 completion {pat['timeFrames']['T3']['completionWeek']}")
                hz = pat.get("horizontalNeckline") or {}
                if hz and not hz.get("closedBeyondSinceS2"):
                    txt += f"\nno weekly close beyond the T2 level {hz['level']} since S2 (on a horizontal neckline: unbroken)"
            elif live.get("iFail") is not None:
                txt += f"\nfailed {pat['failWeek']} (close beyond S2 before any break)"
            else:
                txt += "\nexpired without a break"
        else:
            txt = b["finding"]
        txt = "\n".join(textwrap.fill(line, 105) for line in txt.split("\n"))
        unit = "% share" if space == "logit" else "USD"
        if b["patternInPlay"]:
            short = f"{b['patternInPlay']['kind']} pattern in play"
        elif b["nearestStructure"]:
            ns = b["nearestStructure"]
            short = (f"{ns['kind']} forming, S2 provisional" if (ns["candidateS2Unconfirmed"] and ns["geometryOk"]) else
                     f"latest {ns['kind']} pattern {ns['status']}" if ns["geometryOk"] else f"nearest {ns['kind']} structure fails {', '.join(ns['failedChecks'])}")
        else:
            short = "no structure of the expected kind"
        ax.set_title(f"{name} ({unit}), r={r}: {short}", fontsize=10.5, loc="left", pad=8)
        ax.set_ylabel(unit, color=COL["text2"], fontsize=9)
        if space == "log":
            ax.set_yscale("log")
            ax.yaxis.set_major_locator(LogLocator(base=10.0, subs=(1.0, 1.5, 2.0, 3.0, 5.0, 7.0)))
            ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))
            ax.yaxis.set_minor_locator(NullLocator())
            ax.yaxis.set_minor_formatter(NullFormatter())
        # the text box goes to the corner with the fewest plotted points under it (pattern pivots weigh ten times, so a
        # pivot label is never covered when another corner is free)
        pts = [np.c_[mdates.date2num(np.asarray(dates[start:].values)), w.values[start:]]]
        for ln in ax.get_lines():
            xd, yd = ln.get_xdata(), ln.get_ydata()
            if len(xd) > 1 and ln.get_transform() == ax.transData:   # data lines only (an axvline lives in axes y units)
                pts.append(np.c_[mdates.date2num(np.asarray(pd.DatetimeIndex(xd).values)), np.asarray(yd, float)])
        if live is not None:
            pv = np.array([[mdates.date2num(np.asarray(dates[live["i"][k]:live["i"][k] + 1].values))[0], w.values[live["i"][k]]] for k in ("S1", "T1", "H", "T2", "S2")])
            pts += [pv] * 10
            # the pivot labels sit 9 points above or 14 below their markers: their centres weigh like the pivots
            ax.get_xlim(), ax.get_ylim()
            lab = []
            for (xd, yd), k in zip(pv, ("S1", "T1", "H", "T2", "S2")):
                dy = (9 if (k in ("S1", "H", "S2")) == (live["sign"] == 1) else -14) + 3.5
                disp = ax.transData.transform((xd, yd))
                lab.append(ax.transData.inverted().transform((disp[0], disp[1] + dy * fig.dpi / 72.0)))
            pts += [np.array(lab)] * 10
        (bx, by, ha, va) = best_corner(ax, txt, np.vstack(pts))
        ax.text(bx, by, txt, transform=ax.transAxes, va=va, ha=ha, multialignment="left", fontsize=8.5, color=COL["text"],
                bbox=dict(boxstyle="round,pad=0.4", facecolor=COL["bg"], edgecolor=COL["grid"], alpha=0.9))
        h, l = ax.get_legend_handles_labels()
        for hh, ll in zip(h, l):
            if ll not in labels:
                handles.append(hh)
                labels.append(ll)
    leg = fig.legend(handles, labels, loc="outside lower center", ncol=min(4, max(1, len(labels))), fontsize=8.5, frameon=False)
    for t in leg.get_texts():
        t.set_color(COL["text2"])
    fig.suptitle(f"Round 12: current head-and-shoulders structures at r={r} (point-in-time zigzag on weekly closes)", fontsize=12, color=COL["text"])
    f = os.path.join(out_dir, f"current_patterns_r{str(r).replace('.', '')}.png")
    fig.savefig(f, facecolor=COL["bg"])
    plt.close(fig)
    return f


def chart_laws(out_dir, laws, real_rows, plac_rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    fig, axes = plt.subplots(2, 2, figsize=(12, 8.5), dpi=100, constrained_layout=True)
    fig.patch.set_facecolor(COL["bg"])
    for ax, law in zip(axes.ravel(), LAWS):
        style_axes(ax)
        real = np.array([abs(x["err"]) for x in real_rows if x["law"] == law and x["pool"]], float)
        plac = np.array([abs(x["err"]) for x in plac_rows if x["law"] == law and x["pool"]], float)
        base = np.array([abs(x["errBase"]) for x in real_rows if x["law"] == law and x["pool"] and x["errBase"] is not None], float)
        pooled = np.concatenate([real, plac]) if (len(real) + len(plac)) else np.array([10.0])
        hi = max(10.0, float(np.quantile(pooled, 0.95)))
        step = max(1.0, float(round(hi / 20)))
        bins = np.arange(0, hi + step, step)
        top = float(bins[-1])
        xb = top + 1.5 * step            # the 'beyond the axis' bars sit apart from the histogram, hatched, with counts
        heights = [0.0]
        for v, col, alpha, lab in ((plac, COL["orange"], 0.45, f"placebo patterns (n={len(plac)})"), (real, COL["blue"], 0.55, f"real patterns (n={len(real)})")):
            if len(v):
                inside = v[v <= top]
                hh, _, _ = ax.hist(inside, bins=bins, weights=np.full(len(inside), 1.0 / len(v)), color=col, alpha=alpha, label=lab)
                heights.append(float(np.max(hh)) if len(hh) else 0.0)
        beyond = []
        for k, (v, col) in enumerate(((plac, COL["orange"]), (real, COL["blue"]))):
            if len(v):
                nb = int((v > top).sum())
                ax.bar(xb + (k - 0.5) * 0.8 * step, nb / len(v), width=0.8 * step, facecolor="none", edgecolor=col, hatch="///", lw=1.2)
                beyond.append((nb, nb / len(v)))
            else:
                beyond.append((0, 0.0))
        ymax = max(heights + [b[1] for b in beyond]) or 1.0
        ax.annotate(f"beyond {top:g}w\nplacebo {beyond[0][0]}\nreal {beyond[1][0]}", (xb, max(b[1] for b in beyond)), textcoords="offset points", xytext=(0, 4),
                    ha="center", va="bottom", fontsize=7.5, color=COL["text2"])
        if len(real):
            ax.axvline(np.median(real), color=COL["blue"], lw=1.8, label=f"real median {np.median(real):.1f}w")
        if len(plac):
            ax.axvline(np.median(plac), color=COL["orange"], lw=1.8, ls="--", label=f"placebo median {np.median(plac):.1f}w")
        if len(base):
            ax.axvline(np.median(base), color=COL["yellow"], lw=1.8, ls=":", label=f"baseline median {np.median(base):.1f}w (n={len(base)})")
        ax.set_xlim(0, xb + 1.6 * step)
        ax.set_ylim(0, ymax * 1.45)
        tstep = step * max(1, int(round(len(bins) / 6)))
        ticks = [float(t) for t in np.arange(0, top + 1e-9, tstep)]
        ax.set_xticks(ticks + [xb])
        ax.set_xticklabels([f"{t:g}" for t in ticks] + [f">{top:g}"])
        L = laws[law]
        p = L["pooledTest"]["p"]
        ax.set_title(f"{law} {L['name']}: {L['predicts']} ~ {L['from']}\n|error| in weeks; one-sided rank test real < placebo p={p}; {L['verdict'].split(':')[0]}",
                     fontsize=9.5, loc="left")
        ax.set_xlabel("absolute timing error (weeks); hatched bars = errors beyond the axis", fontsize=9, color=COL["text2"])
        ax.set_ylabel("share of patterns per bin", fontsize=9, color=COL["text2"])
        if len(real) or len(plac):
            h, l = ax.get_legend_handles_labels()
            h.append(Patch(facecolor="none", edgecolor=COL["text2"], hatch="///", label=f"beyond {top:g} weeks (counts above the bars)"))
            l.append(f"beyond {top:g} weeks (counts above the bars)")
            leg = ax.legend(h, l, fontsize=8, frameon=True, facecolor=COL["bg"], edgecolor=COL["grid"], loc="upper center")
            for t in leg.get_texts():
                t.set_color(COL["text2"])
    fig.suptitle("Round 12: timing-law errors, real patterns against placebo series (IAAFT surrogates and matched random walks)", fontsize=12, color=COL["text"])
    f = os.path.join(out_dir, "law_errors.png")
    fig.savefig(f, facecolor=COL["bg"])
    plt.close(fig)
    return f


# ------------------------------------------------------------------------------------------------- json
def jsonable(o):
    if isinstance(o, dict):
        return {str(k): jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [jsonable(v) for v in o]
    if isinstance(o, (np.bool_, bool)):
        return bool(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, (pd.Timestamp, datetime)):
        return ds(o)
    if isinstance(o, np.ndarray):
        return [jsonable(v) for v in o.tolist()]
    return o


# ------------------------------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data", default=os.path.join(HERE, "data"))
    ap.add_argument("--out", default=os.path.join(HERE, "out12", "hs"))
    ap.add_argument("--placebos", type=int, default=40, help="IAAFT surrogates and matched random walks per series (each)")
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    ap.add_argument("--fast", action="store_true", help="smoke mode: 3 placebos, threshold 0.08 only")
    a = ap.parse_args()
    t0 = time.time()
    clock = clock_strings()
    thresholds = (0.08,) if a.fast else THRESHOLDS
    n_plac = 3 if a.fast else a.placebos
    os.makedirs(a.out, exist_ok=True)
    print(f"round 12 H&S timing | start {clock['utc']} / {clock['est']} | thresholds {thresholds} | placebos {n_plac} x 2 kinds per series | workers {a.workers}")

    data = load_series(a.data)
    print("series:", ", ".join(f"{n} {len(d['weekly'])}w {ds(d['weekly'].index[0])}..{ds(d['weekly'].index[-1])}" for n, d in data.items()))
    zigzag(next(iter(data.values()))["x"], 0.08)   # compile once before the pool forks

    # real patterns
    real, zz_by = [], {}
    for name, d in data.items():
        for r in thresholds:
            recs, zz = detect_series(d["x"], r, d["weekly"].index, name)
            real += recs
            zz_by[(name, r)] = zz
    add_base_rates(real, data)
    for p in real:
        fixed_level_events(p, data[p["series"]]["x"])
    add_matched_bases(real, data)
    pit = point_in_time_check(data, thresholds)
    print(f"point-in-time check: {'ok' if pit['ok'] else 'MISMATCH'} on {pit['tested']} truncations" + ("" if pit["ok"] else f": {pit['mismatches'][:3]}"))
    dates_of = {n: d["weekly"].index for n, d in data.items()}
    real_rows = law_rows(real, dates_of)
    add_baselines(real_rows)

    # placebos: the pre-registered family (seeds unchanged), plus BTC.D surrogates of the post-splice segment (a diagnostic)
    jobs = []
    for si, (name, d) in enumerate(data.items()):
        for kind in ("iaaft", "rw"):
            for k in range(n_plac):
                jobs.append((name, kind, 1000 * si + (0 if kind == "iaaft" else 500) + k, d["x"], d["weekly"].index.values, thresholds, None, d["space"]))
    if "BTC.D" in data:
        d = data["BTC.D"]
        m = np.asarray(d["weekly"].index >= SPLICE_WEEK)
        if m.sum() >= 200:
            for kind in ("iaaft", "rw"):
                for k in range(n_plac):
                    jobs.append(("BTC.D", kind, 900000 + (0 if kind == "iaaft" else 500) + k, d["x"][m], d["weekly"].index.values[m], thresholds, "btcdPostSplice", d["space"]))
    plac, plac_post, plac_meta = [], [], []

    def take(out, meta):
        (plac if meta["tag"] is None else plac_post).extend(out)
        plac_meta.append(meta)
    if a.workers > 1 and len(jobs) > 1:
        with get_context("fork").Pool(a.workers) as pool:
            for out, meta in pool.imap_unordered(placebo_job, jobs, chunksize=2):
                take(out, meta)
    else:
        for j in jobs:
            take(*placebo_job(j))
    # one fixed order (the pool returns jobs as they finish), so every diagnostic is reproducible run to run
    for lst in (plac, plac_post):
        lst.sort(key=lambda p: (p["series"], p["placebo"], p["seed"], p["r"], p["i"]["S2"], p["kind"]))
    plac_meta.sort(key=lambda m: (m["name"], m["kind"], m["seed"]))
    plac_rows = law_rows(plac, dates_of)
    n_main_jobs = sum(1 for j in jobs if j[6] is None)
    print(f"patterns: real {len(real)} ({sum(p['pool'] for p in real)} in pool), placebo {len(plac)} from {n_main_jobs} surrogate series "
          f"(+{len(plac_post)} from {len(jobs) - n_main_jobs} post-splice BTC.D surrogates, diagnostic only); {time.time() - t0:.0f}s")

    # the pre-registered test (plan [2], [4]); nothing after this line changes these numbers
    laws = {law: law_report(law, real_rows, plac_rows, thresholds) for law in LAWS}
    verdicts = {law: laws[law]["verdict"] for law in LAWS}
    rates = rates_report(real, plac, thresholds)

    # diagnostics beside it
    ip_real_rows = law_rows([p for p in real if p["inPlayAtConfirmation"]], dates_of)
    add_baselines(ip_real_rows)
    ip_plac_rows = law_rows([p for p in plac if p["inPlayAtConfirmation"]], dates_of)
    corr, corr_start = weekly_change_corr(data)
    indep = independence(corr, corr_start)
    uni = universe_replay(plac, dates_of, laws)
    rob, rob_summary = robustness(real, real_rows, plac, plac_post, dates_of, corr, thresholds)
    t2q, t2b = t2_selection(data, real, zz_by, thresholds)
    keep = ("nRealPool", "nRealWithBaseline", "real", "realOnBaselineSet", "baseline", "improvementOverBaselineWeeks", "placebo", "pooledTest",
            "perThreshold", "perEra", "erasWhereDirectionHolds", "criteria", "scaleDiagnostics")
    for law in LAWS:
        L = laws[law]
        L.update(leakage_audit(law, real_rows))
        ipb = law_report(law, ip_real_rows, ip_plac_rows, thresholds)
        L["inPlayAtConfirmation"] = {"what": ("the same test on the patterns still in play at S2's confirmation (no close beyond the neckline by the "
                                              "confirming close), real and placebo alike; baseline = expanding median over in-play patterns only"),
                                     **{k: ipb[k] for k in keep}, "verdictOnThisSubset": ipb["verdict"]}
        if law == "T2":
            L["inPlayAtConfirmation"]["conditionedOnTheOutcome"] = (
                "for T2 this split is decided at S2's confirmation, which is T2's outcome week (later than the T2 date's issue at T2's "
                "confirmation): the subset is selected on the outcome, so it is descriptive only and no current-pattern T2 band uses it")
        L["actualOverPredicted"] = act_over_pred(law, real_rows, plac_rows)
        L["noiseUniverses"] = uni[law]
        L["robustness"] = rob[law]
    pool_ip = [p for p in real if p["pool"] and p["inPlayAtConfirmation"]]
    stale = [p for p in pool_ip if p["i"]["S2"] + p["w"]["S1T1"] <= p["conf"]]
    stale_err = [abs(p["w"]["S1T1"] - p["w"]["S2Break"]) for p in stale if p["w"]["S2Break"] is not None]
    laws["T1"]["predictionAlreadyPastAtInPlay"] = {
        "count": len(stale), "nInPlayPoolPatterns": len(pool_ip), "withBreak": len(stale_err), "medianAbsErrorWeeksOnThem": med(stale_err),
        "rule": "S2 + (T1 - S1) on or before the in-play week: the T1 date is already past when the pattern first becomes usable, so its error is known to be negative at issue"}
    t2r = [x for x in real_rows if x["law"] == "T2" and x["pool"]]
    t2p = [x for x in plac_rows if x["law"] == "T2" and x["pool"]]

    def ratio_summ(rows):
        v = [x["act"] / x["pred"] for x in rows if x["pred"] > 0]
        return ({"n": len(v), "median": round(float(np.median(v)), 3), "IQR": [round(float(np.quantile(v, 0.25)), 3), round(float(np.quantile(v, 0.75)), 3)],
                 "min": round(float(np.min(v)), 3), "max": round(float(np.max(v)), 3)} if v else {"n": 0})
    cap = {k: (round(float(max(abs(x["err"]) / x["pred"] for x in rows)), 3) if rows else None) for k, rows in (("real", t2r), ("placebo", t2p))}
    laws["T2"]["selectionNote"] = {
        "leftHalvesAtT2Confirmation": t2q, "becameDetectorPatterns": t2b, "maxAbsErrorOverS1H": cap, "capBySpanFilter": round(SPAN_HI - 1.0, 3),
        "note": (f"T2 is dated at T2's confirmation, but a T2 row exists only when the left half later became a confirmed pattern passing the geometry: "
                 f"{t2b} of the {t2q} four-pivot left halves (S1 T1 H T2 with H beyond S1, all series, thresholds {list(thresholds)}) did. The span-ratio check "
                 f"(H -> S2 within {SPAN_LO:.3f}..{SPAN_HI:g} x S1 -> H) caps |error| at {SPAN_HI - 1.0:g} x S1 -> H (observed max {cap['real']} real, "
                 f"{cap['placebo']} placebo). T2 is descriptive symmetry on completed patterns, not a realizable point-in-time forecast; the placebo "
                 "family is selected the same way, so criterion (ii) stays fair, and a 'supported' T2 would have been an artefact of the selection.")}
    laws["T2"]["errorAsRatio"] = {"what": "HS2 / S1H (1 = perfect shoulder symmetry; the span filter bounds it to 1/3 .. 3)", "real": ratio_summ(t2r), "placebo": ratio_summ(t2p)}
    rates["matchedEqualMove"], rates["spanMatchedPlacebo"] = rates_diagnostics(real, plac, thresholds)
    rr_, me_ =rates["real"]["breakWithinWeeksOfInPlay"], rates["matchedEqualMove"]["fixedLevelNecklineBreakWithinWeeksOfInPlay"]
    rates["readingNote"] = (
        f"breakWithinWeeksOfInPlay ({'/'.join(str(rr_[str(H)]['rate']) for H in H_BREAK)} within {'/'.join(str(H) for H in H_BREAK)} weeks) is the sloped-neckline "
        "break censored by fails; set against raw placebo rates measured on shorter patterns it is not a pattern-against-base-rate result. The plan's "
        "comparison is matchedEqualMove: the fixed-level neckline break " + "/".join(str(me_[str(H)]["eraInSample"].get("eventRate")) for H in H_BREAK)
        + " against an equal move " + "/".join(str(me_[str(H)]["eraInSample"].get("matchedBaseRate")) for H in H_BREAK) + " (same series and era, in-sample), "
        "with the variants without the pattern's own weeks and point in time beside it; spanMatchedPlacebo compares the sloped rates with placebo "
        "patterns of the same time scale.")
    cur = current_report(data, real, zz_by, laws, verdicts, real_rows, thresholds, ip_real_rows)
    cur["jointReading"] = joint_reading(cur, laws, verdicts, thresholds, rates)

    series_info = {}
    for name, d in data.items():
        w = d["weekly"]
        info = {"space": d["space"], "weeks": int(len(w)), "start": ds(w.index[0]), "end": ds(w.index[-1]), "lastWeeklyClose": round(float(w.values[-1]), 6),
                "lastDailyBar": d["lastDaily"], "inPoolRule": ("S2 on or after the splice week 2018-06-03" if name == "BTC.D" else "S2 before the splice week 2018-06-03" if name == "BTCD_CMC" else "all patterns")}
        for r in thresholds:
            ps = [p for p in real if p["series"] == name and p["r"] == r]
            info[f"r={r}"] = {"pivots": int(len(zz_by[(name, r)][0])), "patterns": len(ps), "top": sum(p["kind"] == "top" for p in ps), "inverse": sum(p["kind"] == "inverse" for p in ps),
                              "status": {s: sum(1 for p in ps if p["status"] == s) for s in ("in-play", "break", "completed", "failed", "expired")}}
        series_info[name] = info

    n_series = len(data)
    mc = {"planStatement": "2 thresholds x 9 series x 3 laws (the plan's count); the pooled test is the one that counts",
          "seriesRun": n_series, "thresholdsRun": len(thresholds), "lawsRun": len(LAWS),
          "perSeriesTests": len(thresholds) * n_series * len(LAWS), "perThresholdPooledTests": len(thresholds) * len(LAWS), "pooledTestsThatCount": len(LAWS),
          "bonferroniForPooled": round(0.05 / len(LAWS), 4),
          "note": ("Only the pooled one-sided rank test per law (all series and thresholds, BTC-dominance deduplicated) decides criterion (ii); the per-series, "
                   "per-threshold, per-kind and per-era tests are descriptive and not corrected. T3alt is T3's alternative, so four pooled tests are reported "
                   "where the plan counted three laws.")}
    mc["thresholdOverlap"] = rob_summary["thresholdOverlap"]
    mc["nearCopyClusters"] = rob_summary["nearCopyClusters"]
    mc["lowShare"] = rob_summary["lowShare"]
    mc["effectiveIndependentHistories"] = indep
    mc["diagnosticTestsNotPreRegistered"] = (
        "Added beside the pre-registered test, never in its place, none corrected and none deciding a verdict: per law the in-play-at-confirmation "
        "re-run, the span-stratified rank tests (fixed bins and quartiles), the scale-free |error|/predicted and |error|/span tests, per placebo kind and "
        "the equal-kind-weight combination, the noise-universe replay of criteria (i) and (iii) at the real per-era n, and the robustness re-runs "
        "(threshold duplicates once, one pattern per near-copy cluster at one and across thresholds with the mirror rule at -0.7 and -0.8, low-share "
        "heads out, BTC.D placebos from the post-splice segment).")
    tscale = time_scale(real, plac, plac_meta, data, zz_by, thresholds)
    pool_all = [p for p in real if p["pool"]]
    low = [p for p in pool_all if low_share_head(p)]
    amp = float(to_space(0.4, "logit") - to_space(0.3, "logit"))
    low_share_note = (f"logit space turns small moves at low shares into large reversals (from 0.3% to 0.4% share is {amp:.2f} in logit, more than "
                      f"r={max(thresholds)}): {len(low)} of the {len(pool_all)} pooled patterns have the head below {LOW_SHARE:g}% share"
                      + (" (" + ", ".join(f"{p['series']} r={p['r']} S2 {ds(p['s2date'])}" for p in low) + ")" if low else "")
                      + "; laws.*.robustness.excludingLowShareHeads repeats the test without them")
    if "BTC.D" in data:
        dx, wk = np.diff(data["BTC.D"]["x"]), data["BTC.D"]["weekly"].index[1:]
        pre, post = dx[np.asarray(wk < SPLICE_WEEK)], dx[np.asarray(wk >= SPLICE_WEEK)]
        if len(pre) > 10 and len(post) > 10:
            low_share_note += (f". BTC.D's TradingView history before the splice week has a weekly logit-change std of {float(np.std(pre)):.3f} against "
                               f"{float(np.std(post)):.3f} after it (early coverage of few coins); the splice rule keeps those weeks out of the real pool, while "
                               "the pre-registered BTC.D placebos are built from the whole series (laws.*.robustness.btcdPlacebosFromPostSpliceSegment re-runs "
                               "the test with post-splice BTC.D surrogates)")
    mc["placeboComparisonWording"] = placebo_wording(laws)
    mc["timeScaleWording"] = scale_wording(laws)
    mc["diagnosticSummary"] = {law: {
        "verdictPreRegistered": verdicts[law].split(":")[0],
        "inPlayAtConfirmation": {"n": laws[law]["inPlayAtConfirmation"]["nRealPool"], "p": laws[law]["inPlayAtConfirmation"]["pooledTest"]["p"],
                                 "improvementWeeks": laws[law]["inPlayAtConfirmation"]["improvementOverBaselineWeeks"],
                                 "verdict": laws[law]["inPlayAtConfirmation"]["verdictOnThisSubset"].split(":")[0]},
        "spanStratifiedP": laws[law]["scaleDiagnostics"]["spanStratified"]["p"], "spanQuartileStratifiedP": laws[law]["scaleDiagnostics"]["spanStratifiedQuartiles"]["p"],
        "absErrorOverPredictedP": laws[law]["scaleDiagnostics"]["absErrorOverPredicted"]["p"],
        "absErrorOverSpanP": laws[law]["scaleDiagnostics"]["absErrorOverSpan"]["p"],
        "criterionIBeyondNoise": laws[law]["noiseUniverses"]["criterionI"]["passBeyondNoise"], "criterionINoiseP": laws[law]["noiseUniverses"]["criterionI"]["noiseP"],
        "criterionIIIBeyondNoise": laws[law]["noiseUniverses"]["criterionIII"]["passBeyondNoise"], "criterionIIINoiseP": laws[law]["noiseUniverses"]["criterionIII"]["noiseP"],
        "onePerClusterP": [laws[law]["robustness"]["onePerClusterSameThreshold"]["p"], laws[law]["robustness"]["onePerClusterAcrossThresholds"]["p"]]} for law in LAWS}

    charts = []
    try:
        for r in thresholds:
            charts.append(chart_current(a.out, r, data, cur, zz_by, real))
        charts.append(chart_laws(a.out, laws, real_rows, plac_rows))
    except Exception as e:  # charts never block the results
        print("chart error:", repr(e))

    res = {
        "plan": {"file": PLAN, "round": 12, "question": "once a head-and-shoulders right shoulder is in play, does the pattern say when the neckline breaks and when the measured move completes, better than the base rates?",
                 "preRegisteredUTC": "2026-11-02 17:27 UTC", "sections": ["[1] detector", "[2] timing laws and rates", "[3] current patterns", "[4] criteria"]},
        "runUTC": clock["utc"], "runEST": clock["est"],
        "args": {"data": a.data, "out": a.out, "placebos": n_plac, "workers": a.workers, "fast": bool(a.fast), "thresholds": list(thresholds)},
        "detector": {"input": "weekly closes (W-SUN last, complete weeks only); dominance shares in logit space (share/100), prices in log space; ETHUSD = ETHBTC x BTCUSD on common dates",
                     "lowShareCaveat": low_share_note,
                     "zigzag": "a peak (trough) is a pivot only once a weekly close r below (above) it has printed; the pivot's confirmation week is recorded",
                     "thresholds": list(thresholds), "pattern": "five consecutive pivots S1 T1 H T2 S2 (top: peak trough peak trough peak; inverse: the mirror on the negated series)",
                     "geometry": {"headAboveShoulders": "H above S1 and S2", "shoulderTolerance": "|S1 - S2| <= 0.5 x (H - neckline at S2)",
                                  "neckline": "the line through T1 and T2; |rise over S1..S2| <= 0.5 x head height (H - neckline at H)",
                                  "shoulderSpan": "H -> S2 between 1/3 and 3 x S1 -> H", "shouldersAboveNeckline": "S1 and S2 above the neckline at their own weeks (a well-formed, unbroken pattern)"},
                     "inPlayWeekRule": "the week S2 is confirmed (the first close r away from S2); detection uses nothing after it",
                     "outcomes": {"break": "first weekly close beyond the neckline after S2 (may fall before the in-play week: brokenAtConfirmation)",
                                  "target": "neckline at the break -/+ head height", "completion": f"first close beyond the target, looked for within {COMPLETION_WEEKS} weeks of the break",
                                  "failed": "a close beyond S2 before the break", "expired": f"no break within {EXPIRY_WEEKS} weeks of S2", "in-play": "none of the above yet at the data end"},
                     "baseline": f"expanding median of the law's actual duration over pool patterns whose outcome was known before the prediction date (same threshold, all series; needs {BASELINE_MIN} prior patterns)",
                     "placebos": {"iaaft": f"IAAFT surrogate of the transformed weekly series ({IAAFT_IT} iterations)", "rw": f"matched random walk: the series' own increments resampled in {RW_BLOCK_WEEKS}-week blocks with random signs",
                                  "perSeries": n_plac, "sameDetector": True, "poolRule": "the same BTC-dominance splice rule as the real patterns",
                                  "history": ("surrogates are built from each series' full weekly history (its amplitude distribution and power spectrum, or "
                                              "its increments), not point in time: that is the intended null, and it enters no real-pattern quantity because "
                                              "the detector then runs point in time on each surrogate"),
                                  "timeScale": tscale,
                                  "postSpliceBTCD": ("diagnostic only: BTC.D surrogates built from the post-splice segment (the regime of the pooled real BTC.D "
                                                     "patterns), used in laws.*.robustness.btcdPlacebosFromPostSpliceSegment; the pre-registered family is unchanged")},
                     "pool": "all series; BTC.D patterns with S2 before 2018-06-03 and BTCD_CMC patterns with S2 from 2018-06-03 on are left out so one BTC-dominance history is counted",
                     "nearestStructure": f"when no pattern is in play: the five-pivot window of the expected kind with S2 in the last {NEAR_LOOKBACK} weeks (the provisional extreme allowed as S2) that fails the fewest checks",
                     "pointInTimeCheck": pit,
                     "eras": {n: f"{a_}-{b_}" for n, a_, b_ in ERAS}, "rankTest": "one-sided Mann-Whitney (normal approximation, tie and continuity corrected), real |error| < placebo |error|"},
        "series": series_info,
        "patterns": [pattern_record(p, data) for p in sorted(real, key=lambda p: (p["series"], p["r"], p["i"]["S2"]))],
        "laws": laws, "rates": rates, "current": cur, "verdicts": verdicts, "multipleComparisons": mc,
        "charts": [os.path.basename(c) for c in charts], "runtimeSeconds": round(time.time() - t0, 1),
    }
    res = jsonable(res)
    write_results(a.out, res)

    # summary
    print()
    print(f"ROUND 12 head-and-shoulders timing  ({clock['utc']} / {clock['est']})")
    for name, info in series_info.items():
        print("  " + name.ljust(9) + " ".join(f"r={r}: {info[f'r={r}']['pivots']} pivots, {info[f'r={r}']['patterns']} patterns ({info[f'r={r}']['top']} top/{info[f'r={r}']['inverse']} inv) " for r in thresholds))
    print(f"  pool: {sum(p['pool'] for p in real)} real patterns; placebo patterns {len(plac)}")
    for law in LAWS:
        L = laws[law]
        print(f"  {law:5s} {L['name']:18s} n={L['nRealPool']:3d} (with baseline {L['nRealWithBaseline']:3d}) median|err| real {L['real'].get('medianAbs')}w  baseline {L['baseline'].get('medianAbs')}w  "
              f"placebo {L['placebo'].get('medianAbs')}w  p={L['pooledTest']['p']}  eras {L['erasWhereDirectionHolds']}/3 -> {L['verdict'].split(':')[0]}")
    print("  diagnostics beside the pre-registered test (none decides a verdict):")
    for law in LAWS:
        L = laws[law]
        Li, sd, nu, rb = L["inPlayAtConfirmation"], L["scaleDiagnostics"], L["noiseUniverses"], L["robustness"]
        print(f"   {law:5s} in play at confirmation: n={Li['nRealPool']} median|err| {Li['real'].get('medianAbs')}w base {Li['baseline'].get('medianAbs')}w plac "
              f"{Li['placebo'].get('medianAbs')}w p={Li['pooledTest']['p']} improvement {Li['improvementOverBaselineWeeks']}w ({L['rowsFromPatternsBrokenAtConfirmation']} of "
              f"{L['nRealPool']} rows broken at confirmation)")
        print(f"         same time scale: span-stratified p={sd['spanStratified']['p']} (quartiles {sd['spanStratifiedQuartiles']['p']}), |err|/pred p={sd['absErrorOverPredicted']['p']}; "
              f"noise at the real n ({nu['nUniversesMatched']} universes x {nu['drawsPerUniverse']} draws): improvement {nu['criterionI']['realImprovementWeeks']}w vs p95 "
              f"{nu['criterionI']['universeP95']}w, noise p {nu['criterionI']['noiseP']} -> (i) {'beyond noise' if nu['criterionI']['passBeyondNoise'] else 'not beyond noise'}, "
              f"eras {nu['criterionIII']['realErasHolding']}, noise p {nu['criterionIII']['noiseP']} -> (iii) "
              f"{'beyond noise' if nu['criterionIII']['passBeyondNoise'] else 'not beyond noise'}; one per cluster "
              f"n={rb['onePerClusterSameThreshold']['nReal']}/{rb['onePerClusterAcrossThresholds']['nReal']} p={rb['onePerClusterSameThreshold']['p']}/{rb['onePerClusterAcrossThresholds']['p']}")
    print(f"  {placebo_wording(laws)}; {scale_wording(laws)}")
    print(f"  near-copies: {mc['nearCopyClusters']['nPoolPatterns']} pooled patterns -> {mc['nearCopyClusters']['nClustersSameThreshold']} clusters "
          f"({mc['nearCopyClusters']['nClustersAcrossThresholds']} across thresholds); {mc['thresholdOverlap']['identicalFivePivotPatternsAtBothThresholds']} identical at both "
          f"thresholds; about {indep['nGroups']} independent histories ({'; '.join(', '.join(g) for g in indep['groups'])})")
    rr = rates["real"]["breakWithinWeeksOfInPlay"]
    rp = rates["placebo"]["breakWithinWeeksOfInPlay"]
    sm = rates["spanMatchedPlacebo"]["breakWithinWeeksOfInPlay"]
    print(f"  rates, sloped neckline (fail-censored, not a base-rate comparison): break within 13/26/52w of in-play: real {rr['13']['rate']}/{rr['26']['rate']}/{rr['52']['rate']} "
          f"(n={rr['52']['n']}), placebo raw {rp['13']['rate']}/{rp['26']['rate']}/{rp['52']['rate']}, placebo span-matched "
          + "/".join(str(sm[str(H)]["placeboSpanMatched"]["rate"]) for H in H_BREAK))
    fx, tg = rates["matchedEqualMove"]["fixedLevelNecklineBreakWithinWeeksOfInPlay"], rates["matchedEqualMove"]["targetWithinWeeksOfBreak"]

    def trio(blk, hs, key):
        """One base-rate variant: its own event rate and n beside its own matched base rate (each variant drops the
        patterns it has no base rate for, so the event rates differ by variant)."""
        g = [blk[str(H)][key] for H in hs]
        return (f"{'/'.join(str(x.get('eventRate')) for x in g)} (n={'/'.join(str(x.get('n')) for x in g)}) vs "
                f"{'/'.join(str(x.get('matchedBaseRate')) for x in g)}")
    print(f"  rates, the plan's equal-move comparison (event rate vs matched base rate, per variant): fixed-level neckline break within 13/26/52w: "
          f"era in-sample {trio(fx, H_BREAK, 'eraInSample')}; own weeks out {trio(fx, H_BREAK, 'eraExcludingOwnWeeks')}; point in time "
          f"{trio(fx, H_BREAK, 'expandingPointInTime')}. Target within 26/52w: era in-sample {trio(tg, H_TARGET, 'eraInSample')}; own weeks out "
          f"{trio(tg, H_TARGET, 'eraExcludingOwnWeeks')}; point in time {trio(tg, H_TARGET, 'expandingPointInTime')}")
    for name in CURRENT:
        if name in cur:
            for r in thresholds:
                print(f"  {name} r={r}: {cur[name][f'r={r}']['finding']}")
            print(f"  {name} r-sweep: {cur[name]['rSweep']['summary']}")
    print("  " + cur["jointReading"])
    print(f"  verdicts: " + "; ".join(f"{k}: {v.split(':')[0]}" for k, v in verdicts.items()))
    print(f"  wrote {os.path.join(a.out, 'results.json')} and {len(charts)} charts; runtime {res['runtimeSeconds']}s")


if __name__ == "__main__":
    main()
