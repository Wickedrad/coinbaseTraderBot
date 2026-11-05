#!/usr/bin/env python3
"""Round 14: Steven's July-2016 fractal, tested as pre-registered in ROUND14_PLAN.md (2026-11-02 20:36 UTC / 3:36 PM EST).

Steven's mapping (doc comment 2026-11-02 20:27 UTC / 3:27 PM EST): the parent is BTC.D from the July 2016 waterfall
(P0 its top, P1 its bottom) through the rise (P2) and the mid-December 2016 fall (P3), on to the end of 2017; the child
is the 2017-18 waterfall (C0 its top, C1 the 2018 bottom), the central hump (C2) and the 2021 fall (C3), on to today.

  series     TV (TradingView CRYPTOCAP:BTC.D), TVc (TV with its 2014-2018 index steps replaced by CoinMarketCap's
             logit change over the same market day, CMC's labels moved back one day to TradingView's close; back-anchored,
             so TVc = TV after the last step), CMC (CoinMarketCap dominance, canonical file as built). Weekly W-SUN
             closes of complete weeks, logit of the share throughout.
  anchors    the plan's rules on each series' weekly closes (no tuning); checked against the expected TV dates.
  placement  anchored DTW forced through (P0,C0), (P1,C1), (P2,C2), (P3,C3), open-ended after (P3,C3); level map
             child = a + b * parent from the four anchor pairs (b clipped to [0.35, 2.5]) or the z-scored shape
             variant; a run of child-only steps holds at most `cap` child weeks on one parent week; a parent-only
             step costs the median squared residual of the anchored part (a fixed point of the anchored alignment).
  family     series x level map x cap x anchor sets: today's parent week p10/p50/p90; T1 robustness.
  read-out   the parent's next waterfall after the placed week, three clocks, the level-map diagnostic.
  T2         D = open-part mean squared residual; placebo parents given the same anchor search as the real parent.
  T3         walk-forward from C3 + 26 weeks: p(t) from the TV family; Brier against climatology and fixed5.

The DTW is exact: one dynamic programme over the union of the anchored rectangles with a sliding-window minimum per
parent column for the run-length cap (O(child x parent) per pass), numba-compiled when numba is installed.

  python3 research/btcd_fractal/study14_july2016.py --data research/btcd_fractal/data --out <dir> [--fast]
"""
import argparse
import datetime as dt
import hashlib
import json
import math
import multiprocessing as mp
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
sys.dont_write_bytecode = True  # leave the research folder untouched (no new __pycache__ files)
import study8_common as C8  # noqa: E402  (targets: round 8's fall5_26w; block_boot's circular block scheme)

try:  # numba is optional: the pure-Python kernel gives the same answers, only slower
    from numba import njit
    HAVE_NUMBA = True
except Exception:  # pragma: no cover
    HAVE_NUMBA = False

PLAN_FILE = os.path.join(HERE, "ROUND14_PLAN.md")
INF = 1e18
ANCH = ["P0", "P1", "P2", "P3", "C0", "C1", "C2", "C3"]
EXPECTED_TV = {"P0": "2016-06-19", "P1": "2016-07-24", "P2": "2016-11-20", "P3": "2016-12-18",
               "C0": "2017-12-10", "C1": "2018-01-14", "C2": "2019-09-08", "C3": "2021-05-16"}
EXPECTED_TV_VARIANTS = {"C2'": "2021-01-03"}
CAPS = (16, 32, 64)
PRIMARY_CAP = 32
MAPS = ("affine", "shape")
BMIN, BMAX = 0.35, 2.5
WF_FALL, WF_WEEKS = 15.0, 16          # the parent's next waterfall: a >= 15-point fall within the next 16 weeks
STEP_PTS, STEP_LOG = 0.75, 0.20       # TVc step rule
STEP_FROM, STEP_TO = "2014-04-01", "2018-12-31"
LONG_FROM = "2014-04-01"              # surrogates are built on the series' weekly logit from here to the parent end
OFFSET_FROM, OFFSET_TO = "2014-04-01", "2016-04-30"
T3_LAG = 26                           # T3 starts at C3 + 26 weeks
LABEL_H = 26                          # fall5_26w horizon
SHAPE_MIN_NORM = 4                    # minimum weeks in the shape variant's open-part parent normalisation window
SHAPE_LITERAL_END = "2017-03-05"      # the plan's literal shape-variant window end on TV (labelled diagnostic only)
C3P_WINDOW = ("2021-07-01", "2022-06-30")  # C3' window: its value is known only once the window has closed
TRAIL_CLIM_WEEKS = 208                # trailing (4-year) point-in-time climatology, a T3 diagnostic
CAP_SWEEP = (8, 12, 16, 18, 20, 24, 28, 32, 40, 48, 64, 96, 128, 300)
BASE_SEED = 20261102
FAM_KEYS = ["a_iaaft", "b_block8", "c_walk", "d_offset", "e_other"]
FAM_LABEL = {"a_iaaft": "(a) IAAFT", "b_block8": "(b) 8-week block", "c_walk": "(c) matched walk", "d_offset": "(d) offset windows",
             "e_other": "(e) other series", "f_reversed": "(f) reversed parent"}
SERIES = ["TV", "TVc", "CMC"]
COL = {"blue": "#2a78d6", "orange": "#eb6834", "aqua": "#1baf7a", "yellow": "#eda100", "bg": "#fcfcfb", "text": "#0b0b0b",
       "sec": "#52514e", "grid": "#e6e5e1"}


def say(*a):
    print(*a, flush=True)


# ------------------------------------------------------------------------------------------------------------------
# helpers copied from study.py (weekly, iaaft, block_shuffle, matched_walk, zigzag, waterfalls) and study2.py (fwd,
# inv); copied rather than imported because study.py imports numba at module level and numba is optional here
def weekly(s):
    return s.resample("W-SUN").last().dropna()


def iaaft(x, rng, iters=200):
    xs = np.sort(x)
    amp = np.abs(np.fft.rfft(x - x.mean()))
    y = rng.permutation(x)
    for _ in range(iters):
        Y = np.fft.rfft(y - y.mean())
        Y = amp * np.exp(1j * np.angle(Y))
        y = np.fft.irfft(Y, n=len(x)) + x.mean()
        y = xs[np.argsort(np.argsort(y))]
    return y


def block_shuffle(x, rng, blk=8):
    d = np.diff(x)
    blocks = [d[i:i + blk] for i in range(0, len(d), blk)]
    order = rng.permutation(len(blocks))
    dd = np.concatenate([blocks[k] for k in order])
    y = np.concatenate([[x[0]], x[0] + np.cumsum(dd)])
    return y


def matched_walk(x, rng):
    d = np.diff(x)
    sd = d.std()
    lo, hi = x.min(), x.max()
    y = [x[0]]
    for _ in range(len(d)):
        v = y[-1] + rng.normal(0, sd)
        if v < lo or v > hi:
            v = y[-1] - (v - y[-1])
        y.append(float(np.clip(v, lo, hi)))
    return np.array(y)


def zigzag(x, rev):
    piv = [0]
    direction = 0
    ext = 0
    for i in range(1, len(x)):
        if direction >= 0:
            if x[i] > x[ext]:
                ext = i
            elif x[ext] - x[i] >= rev:
                piv.append(ext)
                direction = -1
                ext = i
                continue
        if direction <= 0:
            if x[i] < x[ext]:
                ext = i
            elif x[i] - x[ext] >= rev:
                piv.append(ext)
                direction = 1
                ext = i
    piv.append(ext if ext != piv[-1] else len(x) - 1)
    out = []
    for p in piv:
        if not out or out[-1] != p:
            out.append(p)
    return out


def waterfalls(parent, rev=6.0, minfall=15.0, drift=0.15):
    piv = zigzag(parent, rev)
    out = []
    for p, q in zip(piv[:-1], piv[1:]):
        depth = parent[p] - parent[q]
        if depth >= minfall:
            start = p
            for k in range(p, q + 1):
                if parent[p] - parent[k] >= drift * depth:
                    start = max(p, k - 1)
                    break
            out.append((start, q))
    return out, piv


def fwd(x, space="logit"):
    if space == "log":
        return np.log(np.clip(x, 0.1, None))
    if space == "logit":
        p = np.clip(np.asarray(x, float) / 100.0, 0.005, 0.995)
        return np.log(p / (1 - p))
    return np.asarray(x, float)


def inv(y, space="logit"):
    if space == "log":
        return np.exp(y)
    if space == "logit":
        return 100.0 / (1.0 + np.exp(-np.asarray(y, float)))
    return y


# ------------------------------------------------------------------------------------------------------------------
# JSON and time helpers
def clean(o):
    """JSON-safe copy: numpy scalars to Python, NaN/inf to None, timestamps to YYYY-MM-DD."""
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
    if isinstance(o, (pd.Timestamp, dt.datetime, dt.date)):
        return str(pd.Timestamp(o).date())
    return o


def utc_est(ts_utc):
    """(UTC, US Eastern) strings; Eastern shown as EST = UTC-5 (in force since 2026-11-01)."""
    est = ts_utc - dt.timedelta(hours=5)
    return ts_utc.strftime("%Y-%m-%d %H:%M UTC"), est.strftime("%Y-%m-%d %H:%M EST (") + est.strftime("%-I:%M %p").lstrip("0") + " EST)"


def ds(d):
    return str(pd.Timestamp(d).date())


def r4(x, d=4):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return round(v, d) if math.isfinite(v) else None


# ------------------------------------------------------------------------------------------------------------------
# data
def load_series(data_dir, name):
    f = os.path.join(data_dir, f"{name}_1d.csv")
    if not os.path.exists(f):
        return None
    d = pd.read_csv(f)
    s = pd.Series(d["c"].values.astype(float), index=pd.DatetimeIndex(pd.to_datetime(d["ts"], unit="ms")).normalize())
    return s[~s.index.duplicated()].sort_index().dropna()


def on_index(s, idx):
    u = s.reindex(s.index.union(idx)).ffill()
    return u.reindex(idx)


def align_cmc_to_tv(cmc):
    """CoinMarketCap's row dated d is its snapshot at d 00:02 UTC, i.e. the close of TradingView's daily bar d-1
    (TradingView labels a bar by its 00:00 UTC open; the bar closes at d+1 00:00). Moving CMC's labels back one day puts
    both on the same market day."""
    out = cmc.copy()
    out.index = out.index - pd.Timedelta(days=1)
    return out


def build_tvc(tv, cmc, t2, bu, align_cmc=True, back_anchor=True):
    """TVc on TradingView's daily calendar. A day in STEP_FROM..STEP_TO is an index step when |dTV - dCMC| >= 0.75
    points and dlog TOTAL2 - dlog BTCUSD >= 0.20 in the direction that moves BTC.D the way the TV-CMC gap does. On step
    days logit TVc moves by CoinMarketCap's logit change, on all other days (and after 2018) by TradingView's.
    align_cmc: compare TradingView's day d with CoinMarketCap's change over the same market day (align_cmc_to_tv).
    back_anchor: anchor the chain at the end, so TVc = TV on and after the last step day ("TV with index steps removed":
    the steps are taken out of the history before them); otherwise chained forward from TradingView's first day."""
    idx = tv.index
    cm = align_cmc_to_tv(cmc) if align_cmc else cmc
    D = pd.DataFrame({"tv": tv, "cmc": on_index(cm, idx), "t2": on_index(t2, idx), "bu": on_index(bu, idx)}, index=idx)
    dtv = D["tv"].diff()
    dcmc = D["cmc"].diff()
    gap = dtv - dcmc
    dl_t2 = np.log(D["t2"]).diff()
    dl_bu = np.log(D["bu"]).diff()
    ex = dl_t2 - dl_bu
    win = (idx >= pd.Timestamp(STEP_FROM)) & (idx <= pd.Timestamp(STEP_TO))
    cond = (gap.abs() >= STEP_PTS) & (((gap < 0) & (ex >= STEP_LOG)) | ((gap > 0) & (ex <= -STEP_LOG)))
    step = np.asarray(win) & cond.fillna(False).values
    Ltv = pd.Series(fwd(D["tv"].values), index=idx)
    Lcmc = pd.Series(fwd(D["cmc"].values), index=idx)
    dL = Ltv.diff()
    dLc = Lcmc.diff()
    dL[step] = dLc[step]
    L = float(Ltv.iloc[0]) + dL.fillna(0.0).cumsum()
    fwd_off = float(L.iloc[-1] - Ltv.iloc[-1])  # the forward chain's offset after the last step = sum of the corrections
    if back_anchor:
        L = L - fwd_off
    steps = []
    for d in idx[step]:
        steps.append({"date": ds(d), "dTV": r4(dtv[d], 3), "dCMC": r4(dcmc[d], 3), "gapTVminusCMC": r4(gap[d], 3),
                      "dlogTOTAL2": r4(dl_t2[d], 4), "dlogBTCUSD": r4(dl_bu[d], 4), "altExcess": r4(ex[d], 4),
                      "tvLevelBefore": r4(D["tv"].shift(1)[d], 2), "tvLevelAfter": r4(D["tv"][d], 2),
                      "cmcLevelBefore": r4(D["cmc"].shift(1)[d], 2), "cmcLevelAfter": r4(D["cmc"][d], 2),
                      "logitCorrection": r4(dLc[d] - Ltv.diff()[d], 4)})
    info = {"alignedCMC": bool(align_cmc), "backAnchored": bool(back_anchor), "forwardChainOffsetLogit": fwd_off,
            "logitOffsetVsTVAfterLastStep": float(L.iloc[-1] - Ltv.iloc[-1]),
            "lastStepDay": ds(idx[step][-1]) if step.any() else None}
    return L, steps, step, D, info


def cmc_alignment_evidence(tv, cmc, data_dir):
    """Why CMC's labels move back one day: the correlation of daily logit changes, TradingView day d against CMC's change
    under label d (lag 0) and label d+1 (lag +1), by period; and the snapshot time in data/cmc_raw_sample.json (each
    quote's originalScore is its Unix time)."""
    dtv = pd.Series(fwd(tv.values), index=tv.index).diff()
    dcm = pd.Series(fwd(cmc.values), index=cmc.index).reindex(tv.index).diff()
    rows = []
    for lo, hi in (("2014-04-01", "2016-12-31"), ("2017-01-01", "2018-12-31"), ("2019-01-01", "2022-12-31"), ("2023-01-01", "2026-12-31")):
        m = (tv.index >= pd.Timestamp(lo)) & (tv.index <= pd.Timestamp(hi))
        row = {"period": f"{lo}..{hi}"}
        for k, nm in ((0, "lag0"), (1, "lagPlus1")):
            b = dcm.shift(-k)
            ok = m & dtv.notna().values & b.notna().values
            row[nm] = r4(np.corrcoef(dtv[ok], b[ok])[0, 1], 3) if ok.sum() > 10 else None
        rows.append(row)
    snap = None
    f = os.path.join(data_dir, "cmc_raw_sample.json")
    if os.path.exists(f):
        try:
            import re
            txt = open(f).read()
            pairs = re.findall(r'"timestamp": "([^"]+)", "searchInterval"[^}]*?"originalScore": "(\d+)"', txt)
            ex = []
            n_0002 = 0
            for lab, sc in pairs:
                t_snap = dt.datetime.fromtimestamp(int(sc), dt.timezone.utc)
                lab_d = pd.Timestamp(lab).tz_localize(None).normalize() if pd.Timestamp(lab).tzinfo else pd.Timestamp(lab).normalize()
                n_0002 += int(t_snap.date() == lab_d.date() and t_snap.hour == 0 and t_snap.minute <= 5)
                if len(ex) < 3:
                    ex.append({"labelDate": ds(lab_d), "originalScore": sc, "snapshotDateUTC": t_snap.strftime("%Y-%m-%d"),
                               "snapshotClockUTC": t_snap.strftime("%H:%M")})
            snap = {"file": "data/cmc_raw_sample.json", "nQuotesParsed": len(pairs), "nSnapshotAtLabelDay0000to0005UTC": n_0002, "examples": ex}
        except Exception as e_:  # evidence only
            snap = {"error": f"{type(e_).__name__}: {e_}"}
    return {"rule": "CoinMarketCap's row dated d is its snapshot at d 00:02 UTC = the close of TradingView's daily bar d-1 "
                    "(TradingView labels a bar by its 00:00 UTC open); CMC's labels move back one day before the plan's same-day "
                    "comparison |dTV(d) - dCMC(d)|, the step-day substitution and the chain",
            "dailyLogitChangeCorrelation": rows, "snapshotTimes": snap}


def week_of(day):
    d = pd.Timestamp(day)
    return d + pd.Timedelta(days=(6 - d.weekday()))


def make_series(name, wpct=None, wlogit=None):
    if wlogit is None:
        wlogit = pd.Series(fwd(wpct.values), index=wpct.index)
    if wpct is None:
        wpct = pd.Series(inv(wlogit.values), index=wlogit.index)
    return {"name": name, "dates": pd.DatetimeIndex(wpct.index), "pct": np.ascontiguousarray(wpct.values, dtype=float),
            "x": np.ascontiguousarray(wlogit.values, dtype=float)}


# ------------------------------------------------------------------------------------------------------------------
# anchors (the plan's rules, weekly closes)
def rule_anchors(dates, pct):
    n = len(dates)
    ar = np.arange(n)

    def sel(lo, hi):
        return np.where((dates >= pd.Timestamp(lo)) & (dates <= pd.Timestamp(hi)))[0]

    def amin(ii):
        ii = np.asarray(ii)
        return int(ii[np.argmin(pct[ii])])

    def amax(ii):
        ii = np.asarray(ii)
        return int(ii[np.argmax(pct[ii])])
    A = {}
    A["P1"] = amin(sel("2016-07-01", "2016-08-31"))
    A["P0"] = amax(np.arange(max(0, A["P1"] - 8), A["P1"]))
    A["P2"] = amax(np.where((ar > A["P1"]) & (dates <= pd.Timestamp("2017-01-31")))[0])
    A["P3"] = amin(np.arange(A["P2"] + 1, A["P2"] + 5))
    A["C1"] = amin(sel("2018-01-01", "2018-03-31"))
    A["C0"] = amax(np.arange(A["C1"] - 8, A["C1"]))
    A["C3"] = amin(sel("2021-01-01", "2021-06-30"))
    A["C2"] = amax(np.arange(A["C1"] + 1, A["C3"]))
    split = pd.Timestamp("2020-06-30")
    if dates[A["C2"]] <= split:
        c2p = amax(np.where((dates > split) & (ar < A["C3"]))[0])
        c2p_rule = "primary C2 is the 2019 hump: C2' = max weekly close in (2020-06-30, C3)"
    else:
        c2p = amax(np.where((ar > A["C1"]) & (dates <= split))[0])
        c2p_rule = "primary C2 is the 2021 spike: C2' = the 2019 hump = max weekly close in (C1, 2020-06-30]"
    V = {"C2'": c2p, "C3'": amin(sel("2021-07-01", "2022-06-30")), "P3'": amin(np.arange(A["P2"] + 1, A["P2"] + 9))}
    return A, V, c2p_rule


# ------------------------------------------------------------------------------------------------------------------
# the dynamic programme. Cells (i, j): child week C0 + i matched to parent week P0 + j. Valid cells are the union of
# the rectangles [C_k, C_k+1] x [P_k, P_k+1] (k = 0..2) and the open rectangle [C3, t] x [P3, end]; two diagonal moves
# per anchor that would skip its corner are forbidden, so every path passes through every anchor cell.
# A[i, j]: best cost of a path whose vertical run on column j starts at row i (entered diagonally or parent-only);
# V[i, j] = S[i, j] + min over run starts i' in [i - cap + 1, i] of (A[i', j] - S[i', j]), S = column cumsum of E.
def _dp_py(E, jlo, jhi, ac, ap, lam, cap, nrows):
    m = E.shape[1]
    V = np.empty((nrows, m))
    RS = np.empty((nrows, m), np.int32)
    MV = np.empty((nrows, m), np.int8)
    S = np.zeros(m)
    dqi = np.empty((m, nrows), np.int32)
    dqv = np.empty((m, nrows))
    head = np.zeros(m, np.int32)
    tail = np.zeros(m, np.int32)
    last = np.full(m, -5, np.int32)
    nk = ac.shape[0]
    for i in range(nrows):
        lo = jlo[i]
        hi = jhi[i]
        plo = 1
        phi = 0
        if i > 0:
            plo = jlo[i - 1]
            phi = jhi[i - 1]
        for j in range(lo, hi + 1):
            if last[j] != i - 1:
                head[j] = 0
                tail[j] = 0
                S[j] = 0.0
            last[j] = i
            e = E[i, j]
            best = INF
            mv = -1
            if i == 0 and j == 0:
                best = 0.0
                mv = 2
            else:
                if i > 0 and j > 0 and j - 1 >= plo and j - 1 <= phi:
                    ok = True
                    for k in range(nk):
                        if (i == ac[k] and j == ap[k] + 1) or (i == ac[k] + 1 and j == ap[k]):
                            ok = False
                    if ok:
                        v = V[i - 1, j - 1]
                        if v < best:
                            best = v
                            mv = 0
                if j - 1 >= lo:
                    v = V[i, j - 1] + lam
                    if v < best:
                        best = v
                        mv = 1
            MV[i, j] = mv
            S[j] += e
            if best < INF:
                val = best + e - S[j]
                while tail[j] > head[j] and dqv[j, tail[j] - 1] >= val:
                    tail[j] -= 1
                dqi[j, tail[j]] = i
                dqv[j, tail[j]] = val
                tail[j] += 1
            lim = i - cap + 1
            while tail[j] > head[j] and dqi[j, head[j]] < lim:
                head[j] += 1
            if tail[j] > head[j]:
                V[i, j] = S[j] + dqv[j, head[j]]
                RS[i, j] = dqi[j, head[j]]
            else:
                V[i, j] = INF
                RS[i, j] = -1
    return V, RS, MV


def _bt_py(RS, MV, i, j, oi, oj):
    """Backtrack from the end of a vertical run at (i, j); cells written end-first. Returns the cell count (-1 on
    failure)."""
    k = 0
    while True:
        s = RS[i, j]
        if s < 0:
            return -1
        r = i
        while r >= s:
            oi[k] = r
            oj[k] = j
            k += 1
            r -= 1
        mv = MV[s, j]
        if mv == 2:
            return k
        if mv == 0:
            i = s - 1
            j = j - 1
        elif mv == 1:
            i = s
            j = j - 1
        else:
            return -1


if HAVE_NUMBA:
    DP = njit(cache=False, nogil=True)(_dp_py)
    BT = njit(cache=False, nogil=True)(_bt_py)
else:  # pragma: no cover
    DP, BT = _dp_py, _bt_py


def warm_up():
    E = np.random.default_rng(0).random((12, 8))
    c = np.array([0, 2, 5, 8], np.int64)
    p = np.array([0, 1, 3, 5], np.int64)
    jlo, jhi = grid_bounds(c, p, 7, 12, False)
    V, RS, MV = DP(E, jlo, jhi, c[1:].copy(), p[1:].copy(), 0.1, 4, 12)
    oi = np.empty(40, np.int64)
    oj = np.empty(40, np.int64)
    BT(RS, MV, 11, 7, oi, oj)


def grid_bounds(c, p, e, nrows, anchored_only):
    jlo = np.full(nrows, 1 << 30, np.int64)
    jhi = np.full(nrows, -1, np.int64)
    rects = [(c[0], c[1], p[0], p[1]), (c[1], c[2], p[1], p[2]), (c[2], c[3], p[2], p[3])]
    if not anchored_only:
        rects.append((c[3], nrows - 1, p[3], e))
    for (r0, r1, q0, q1) in rects:
        r1 = min(int(r1), nrows - 1)
        if r1 < r0:
            continue
        jlo[r0:r1 + 1] = np.minimum(jlo[r0:r1 + 1], q0)
        jhi[r0:r1 + 1] = np.maximum(jhi[r0:r1 + 1], q1)
    return jlo, jhi


def backtrack(RS, MV, i, j, nbuf):
    oi = np.empty(nbuf, np.int64)
    oj = np.empty(nbuf, np.int64)
    k = BT(RS, MV, int(i), int(j), oi, oj)
    if k < 0:
        return None
    return oi[:k][::-1].copy(), oj[:k][::-1].copy()


def z_of(v):
    mu = float(np.mean(v))
    sd = float(np.std(v))
    return (v - mu) / (sd if sd > 1e-12 else 1.0)


def affine_ab(pa, ca):
    pa = np.asarray(pa, float)
    ca = np.asarray(ca, float)
    vp = float(np.var(pa))
    b_raw = float(np.mean((pa - pa.mean()) * (ca - ca.mean())) / vp) if vp > 1e-12 else 1.0
    b = float(np.clip(b_raw, BMIN, BMAX))
    a = float(np.mean(ca - b * pa))
    return a, b, b_raw


def wf_next(pct, P0, end):
    """flag[k]: the parent falls >= 15 points within the next 16 weeks from week k (looking no further than the parent
    end). nxt[k]: the first flagged week after k (absolute index), -1 if none."""
    seg = np.asarray(pct[P0:end + 1], float)
    L = len(seg)
    flag = np.zeros(L, bool)
    for k in range(L - 1):
        hi = min(k + WF_WEEKS, L - 1)
        if seg[k + 1:hi + 1].min() <= seg[k] - WF_FALL:
            flag[k] = True
    nxt = np.full(L, -1, np.int64)
    cur = -1
    for k in range(L - 1, -1, -1):
        nxt[k] = cur
        if flag[k]:
            cur = P0 + k
    return flag, nxt


def anchored_lambda(E, c, p, cap, max_iter=12):
    """The parent-only penalty as a fixed point: lambda = median squared residual of the anchored part's path, the path
    computed with that lambda (start at 0, iterate until the path stops changing)."""
    nrows = int(c[3]) + 1
    jlo, jhi = grid_bounds(c, p, int(p[3]), nrows, True)
    ac = np.ascontiguousarray(c[1:], dtype=np.int64)
    ap = np.ascontiguousarray(p[1:], dtype=np.int64)
    nbuf = nrows + int(p[3]) + 8

    def run(lam):
        V, RS, MV = DP(E, jlo, jhi, ac, ap, float(lam), int(cap), nrows)
        if V[c[3], p[3]] >= INF / 2:
            return None
        cells = backtrack(RS, MV, c[3], p[3], nbuf)
        if cells is None:
            return None
        return float(V[c[3], p[3]]), cells
    res = run(0.0)
    if res is None:
        return None
    lam, conv, it = 0.0, False, 0
    for it in range(max_iter):
        cells = res[1]
        lam_new = float(np.median(E[cells[0], cells[1]]))
        res_new = run(lam_new)
        same = len(res_new[1][0]) == len(cells[0]) and np.array_equal(res_new[1][0], cells[0]) and np.array_equal(res_new[1][1], cells[1])
        lam, res = lam_new, res_new
        if same:
            conv = True
            break
    cost, cells = res
    return {"lam": lam, "acost": cost, "cells": cells, "conv": conv, "iters": it + 1,
            "amse": float(np.mean(E[cells[0], cells[1]]))}


def prep_member(par_x, par_pct, child_y, mem, Tmax):
    """Everything about one family member that does not depend on t: its grid, residual matrix (the shape variant's
    open block is filled per t), the anchored fixed point and the parent's waterfall calendar."""
    P0, P1, P2, P3 = (int(v) for v in mem["P"])
    C0, C1, C2, C3 = (int(v) for v in mem["C"])
    end = int(mem["end"])
    if not (0 <= P0 < P1 < P2 < P3 < end <= len(par_x) - 1):
        return None
    if not (0 <= C0 < C1 < C2 < C3 < Tmax <= len(child_y) - 1):
        return None
    px = np.ascontiguousarray(par_x[P0:end + 1], dtype=float)
    cy = np.ascontiguousarray(child_y[C0:Tmax + 1], dtype=float)
    c = np.array([0, C1 - C0, C2 - C0, C3 - C0], np.int64)
    p = np.array([0, P1 - P0, P2 - P0, P3 - P0], np.int64)
    e = end - P0
    flag, nxt = wf_next(par_pct, P0, end)
    pr = {"px": px, "cy": cy, "c": c, "p": p, "e": e, "P0": P0, "C0": C0, "end": end, "nxt": nxt, "flag": flag}
    if mem["map"] == "affine":
        a, b, b_raw = affine_ab(px[p], cy[c])
        E = (cy[:, None] - a - b * px[None, :]) ** 2
        pr.update(a=a, b=b, b_raw=b_raw)
    else:
        E = np.zeros((len(cy), len(px)))
        for k in (2, 1, 0):  # corners keep the earlier segment's values
            r0, r1, q0, q1 = c[k], c[k + 1], p[k], p[k + 1]
            E[r0:r1 + 1, q0:q1 + 1] = (z_of(cy[r0:r1 + 1])[:, None] - z_of(px[q0:q1 + 1])[None, :]) ** 2
        p3 = int(p[3])
        fl = np.where(flag[p3 + 1:])[0]
        W = p3 + 1 + int(fl[0]) if len(fl) else e
        W_eff = int(min(max(W, p3 + SHAPE_MIN_NORM), e))
        if mem.get("normEndAbs") is not None:  # labelled diagnostic: an explicit window end (absolute parent index)
            W = int(mem["normEndAbs"]) - P0
            W_eff = int(min(max(W, p3 + 1), e))
        win = px[p3 + 1:W_eff + 1]
        sd = float(np.std(win))
        pr.update(zp_open=(px[p3:] - float(np.mean(win))) / (sd if sd > 1e-12 else 1.0), corner=float(E[c[3], p3]),
                  normW=P0 + W, normWeff=P0 + W_eff, normFound=bool(len(fl)))
    pr["E"] = np.ascontiguousarray(E)
    fx = anchored_lambda(pr["E"], c, p, int(mem["cap"]))
    if fx is None:
        return None
    pr.update(lam=fx["lam"], acost=fx["acost"], amse=fx["amse"], conv=fx["conv"], iters=fx["iters"])
    return pr


def fill_open(pr, r):
    """The shape variant at child row r: the child's open part z-scored over (C3, t] (data up to t only)."""
    c3, p3, e = int(pr["c"][3]), int(pr["p"][3]), int(pr["e"])
    cy = pr["cy"]
    w = cy[c3 + 1:r + 1]
    mu = float(np.mean(w)) if len(w) else float(cy[c3])
    sd = float(np.std(w)) if len(w) > 1 else 0.0
    zc = (cy[c3:r + 1] - mu) / (sd if sd > 1e-12 else 1.0)
    pr["E"][c3:r + 1, p3:e + 1] = (zc[:, None] - pr["zp_open"][None, :]) ** 2
    pr["E"][c3, p3] = pr["corner"]


def place_row(V, r, p3, e):
    row = V[r, p3 + 1:e + 1]
    if len(row) == 0:
        return -1
    k = int(np.argmin(row))
    if row[k] >= INF / 2:
        return -1
    return int(p3 + 1 + k)


def walk_family(par, child_y, members, t_list, primary_idx=None, want_path_at_last=False):
    """Place every member at every child week t in t_list (ascending) using child data up to t only.
    par: {"x", "pct"} parent source arrays (absolute indices in member specs). Returns placements (absolute parent
    indices, -1 = not placed), per-member info, and the primary member's clock track."""
    t_list = np.asarray(t_list, np.int64)
    Tmax = int(t_list[-1])
    nM, nT = len(members), len(t_list)
    place = np.full((nM, nT), -1, np.int64)
    info = []
    prim = None
    for mi, mem in enumerate(members):
        pr = prep_member(par["x"], par["pct"], child_y, mem, Tmax)
        if pr is None:
            info.append({"feasible": False})
            continue
        c, p, e, C0, P0 = pr["c"], pr["p"], int(pr["e"]), pr["C0"], pr["P0"]
        nrows_all = Tmax - C0 + 1
        jlo, jhi = grid_bounds(c, p, e, nrows_all, False)
        ac = np.ascontiguousarray(c[1:], dtype=np.int64)
        ap = np.ascontiguousarray(p[1:], dtype=np.int64)
        cap = int(mem["cap"])
        lam = float(pr["lam"])
        is_prim = primary_idx is not None and mi == primary_idx
        C3m = int(mem["C"][3])
        act = int(mem.get("activeFrom", -1))  # first child week at which the member's anchors are all known (C3')
        if is_prim:
            prim = {"t": t_list.copy(), "jstar": np.full(nT, -1, np.int64), "delta": np.full(nT, -1, np.int64),
                    "clock": np.full(nT, np.nan), "h": np.full(nT, np.nan), "lam": lam, "a": pr.get("a"), "b": pr.get("b"),
                    "b_raw": pr.get("b_raw"), "acost": pr["acost"], "amse": pr["amse"], "conv": pr["conv"]}
        nbuf = nrows_all + e + 8

        def track(V, RS, MV, ti, r, j):
            cells = backtrack(RS, MV, r, j, nbuf)
            if cells is None:
                return
            oi, oj = cells
            sel = oj[oi == r - 52]
            if len(sel):
                d = int(j - sel.max())
                prim["delta"][ti] = d
                prim["clock"][ti] = 52.0 / d if d > 0 else np.inf
                prim["h"][ti] = d / 2.0 if d > 0 else 0.0
            prim["jstar"][ti] = P0 + j
            if want_path_at_last and ti == nT - 1:
                Ecur = pr["E"]
                op = oi > c[3]
                prim["path"] = {"child": (C0 + oi).tolist(), "parent": (P0 + oj).tolist()}
                prim["D"] = float(np.mean(Ecur[oi[op], oj[op]])) if op.any() else float("nan")
                prim["nOpenCells"] = int(op.sum())
        if mem["map"] == "affine":
            V, RS, MV = DP(pr["E"], jlo, jhi, ac, ap, lam, cap, nrows_all)
            for ti, t in enumerate(t_list):
                if t <= C3m or t < act:
                    continue
                r = int(t - C0)
                j = place_row(V, r, int(p[3]), e)
                if j >= 0:
                    place[mi, ti] = P0 + j
                    if is_prim:
                        track(V, RS, MV, ti, r, j)
        else:
            for ti, t in enumerate(t_list):
                if t <= C3m or t < act:
                    continue
                r = int(t - C0)
                fill_open(pr, r)
                V, RS, MV = DP(pr["E"], jlo, jhi, ac, ap, lam, cap, r + 1)
                j = place_row(V, r, int(p[3]), e)
                if j >= 0:
                    place[mi, ti] = P0 + j
                    if is_prim:
                        track(V, RS, MV, ti, r, j)
        inf_ = {"feasible": True, "lam": lam, "acost": pr["acost"], "amse": pr["amse"], "conv": pr["conv"], "iters": pr["iters"],
                "P0": P0, "end": pr["end"], "nxt": pr["nxt"], "a": pr.get("a"), "b": pr.get("b")}
        if mem["map"] == "shape":
            inf_.update(normW=pr["normW"], normWeff=pr["normWeff"], normFound=pr["normFound"])
        info.append(inf_)
    return place, info, prim


def family_prob(place, info, h):
    """p(t): share of the placed members whose placed week is within h(t) parent weeks before their next waterfall."""
    nM, nT = place.shape
    p = np.full(nT, np.nan)
    nplaced = np.zeros(nT, np.int64)
    for ti in range(nT):
        hit, tot = 0, 0
        for mi in range(nM):
            j = place[mi, ti]
            if j < 0:
                continue
            nx = info[mi]["nxt"][j - info[mi]["P0"]]
            tot += 1
            if nx >= 0 and np.isfinite(h[ti]) and (nx - j) <= h[ti]:
                hit += 1
        nplaced[ti] = tot
        p[ti] = hit / tot if tot else np.nan
    return p, nplaced


def eval_member(par, child_y, P, C, end, T, mapkind="affine", cap=PRIMARY_CAP):
    """One member placed at today's week T with its full path, open-part D and the read-out ingredients."""
    mem = {"map": mapkind, "cap": cap, "P": tuple(int(v) for v in P), "C": tuple(int(v) for v in C), "end": int(end), "label": "single"}
    place, info, prim = walk_family(par, child_y, [mem], [int(T)], primary_idx=0, want_path_at_last=True)
    if not info[0]["feasible"] or place[0, 0] < 0 or prim is None or "D" not in prim:
        return None
    return {"place": int(place[0, 0]), "D": prim["D"], "lam": prim["lam"], "a": prim["a"], "b": prim["b"], "b_raw": prim["b_raw"],
            "acost": prim["acost"], "amse": prim["amse"], "conv": prim["conv"], "path": prim["path"], "delta": int(prim["delta"][0]),
            "clock": float(prim["clock"][0]), "nxt": info[0]["nxt"], "P0": info[0]["P0"], "end": info[0]["end"]}


def anchored_cost(par_x, child_y, P, C, cap=PRIMARY_CAP):
    """The anchored part's cost (affine map from the four pairs, the fixed-point penalty) per child week."""
    P0, P1, P2, P3 = (int(v) for v in P)
    C0, C1, C2, C3 = (int(v) for v in C)
    px = par_x[P0:P3 + 1]
    cy = child_y[C0:C3 + 1]
    c = np.array([0, C1 - C0, C2 - C0, C3 - C0], np.int64)
    p = np.array([0, P1 - P0, P2 - P0, P3 - P0], np.int64)
    a, b, _ = affine_ab(px[p], cy[c])
    E = np.ascontiguousarray((cy[:, None] - a - b * px[None, :]) ** 2)
    fx = anchored_lambda(E, c, p, cap)
    if fx is None:
        return None
    return fx["acost"] / (C3 - C0 + 1)


# ------------------------------------------------------------------------------------------------------------------
# the T2 anchor search (the same freedom Steven had)
def local_extrema(x, lo, hi, w0, w1, kind):
    out = []
    for i in range(max(lo, w0 + 1), min(hi, w1 - 1) + 1):
        if kind == "min" and x[i] < x[i - 1] and x[i] <= x[i + 1]:
            out.append(i)
        elif kind == "max" and x[i] > x[i - 1] and x[i] >= x[i + 1]:
            out.append(i)
    return out


def search_anchors(par_x, w0, w1, child_y, C, cap=PRIMARY_CAP):
    """P1 among the 3 deepest local minima in the window's first 30 weeks, P0 = max of the 8 weeks before P1, P2 among
    the 3 highest local maxima within 30 weeks after P1, P3 = min of the 4 weeks after P2; the combination with the
    lowest anchored cost against the real child (C0..C3) wins. Everything stays inside the window [w0, w1]."""
    mins = local_extrema(par_x, w0, w0 + 29, w0, w1, "min")
    p1c = sorted(mins, key=lambda i: (par_x[i], i))[:3]
    combos = []
    for P1 in p1c:
        lo = max(w0, P1 - 8)
        if lo >= P1:
            continue
        P0 = lo + int(np.argmax(par_x[lo:P1]))
        maxs = local_extrema(par_x, P1 + 1, P1 + 30, w0, w1, "max")
        for P2 in sorted(maxs, key=lambda i: (-par_x[i], i))[:3]:
            hi = min(P2 + 4, w1 - 1)
            if hi <= P2:
                continue
            P3 = P2 + 1 + int(np.argmin(par_x[P2 + 1:hi + 1]))
            combos.append((P0, P1, P2, P3))
    best, rows = None, []
    for P in combos:
        cst = anchored_cost(par_x, child_y, P, C, cap)
        rows.append({"P": P, "cost": cst})
        if cst is not None and (best is None or cst < best[1]):
            best = (P, cst)
    return best, rows


def open_split(ev, par_x, child_y, C3):
    """D of the open part split into bias^2 (squared mean residual: a level mismatch) and variance (shape mismatch);
    D = bias^2 + variance exactly (labelled T2 diagnostic)."""
    ch = np.asarray(ev["path"]["child"])
    pa = np.asarray(ev["path"]["parent"])
    op = ch > C3
    if not op.any():
        return None, None, None
    res = child_y[ch[op]] - (ev["a"] + ev["b"] * par_x[pa[op]])
    return float(np.mean(res ** 2)), float(np.mean(res) ** 2), float(np.var(res))


def t2_one(par, w0, w1, child_y, C, T):
    best, rows = search_anchors(par["x"], w0, w1, child_y, C)
    out = {"nCombos": len(rows), "nFeasible": int(sum(r["cost"] is not None for r in rows))}
    if best is None:
        out.update(D=None, P=None)
        return out
    ev = eval_member(par, child_y, best[0], C, w1, T)
    if ev is None:
        out.update(D=None, P=list(best[0]), anchoredCost=best[1])
        return out
    _, b2, vv = open_split(ev, par["x"], child_y, C[3])
    out.update(D=ev["D"], P=[int(v) for v in best[0]], anchoredCost=best[1], place=ev["place"] - w0, b=ev["b"],
               bRaw=ev["b_raw"], bias2=b2, var=vv)
    return out


def wf_episodes(pct, P0, end, flag):
    """Labelled diagnostic: runs of the 15-in-16 flag merged across gaps under 16 weeks. Per episode (absolute indices):
    first and last flagged week, the top (max close over the flagged span), the first decline week (the first week after
    the top that closes below every close from the first flag to the top) and the low (min close in (top, last flag +
    16 weeks])."""
    idx = np.flatnonzero(flag)
    if not len(idx):
        return []
    runs = []
    s = e = int(idx[0])
    for k in idx[1:]:
        k = int(k)
        if k - e < WF_WEEKS:
            e = k
        else:
            runs.append((s, e))
            s = e = k
    runs.append((s, e))
    eps = []
    for s, e in runs:
        a0, a1 = P0 + s, P0 + e
        top = a0 + int(np.argmax(pct[a0:a1 + 1]))
        pre_min = float(np.min(pct[a0:top + 1]))
        dec = next((j for j in range(top + 1, end + 1) if pct[j] < pre_min), None)
        hi = min(a1 + WF_WEEKS, end)
        low = top + 1 + int(np.argmin(pct[top + 1:hi + 1])) if hi > top else top
        eps.append({"firstFlag": a0, "lastFlag": a1, "top": top, "firstDecline": dec, "low": low})
    return eps


def episode_class(j, eps):
    """Where a placed parent week sits relative to the next waterfall episode (labelled diagnostic)."""
    for ep in eps:
        if j > ep["low"]:
            continue
        if j < ep["firstFlag"]:
            return "beforeEpisode"
        if j < ep["top"]:
            return "runUpBeforeTop"
        if j == ep["top"]:
            return "atTop"
        if ep["firstDecline"] is not None and j < ep["firstDecline"]:
            return "betweenTopAndFirstDeclineWeek"
        return "insideDecline"
    return "afterLastEpisodeLow"


def coarse_class(j, ep):
    """plateau (before the first decline week) / decline (first decline week .. low) / later (after the low)."""
    if ep is None:
        return "noEpisode"
    if ep["firstDecline"] is None or j < ep["firstDecline"]:
        return "plateau"
    if j <= ep["low"]:
        return "decline"
    return "later"


def auc_score(s, y):
    """Mann-Whitney AUC of score s for binary y (ties count one half); None when a class is empty."""
    s, y = np.asarray(s, float), np.asarray(y, float)
    pos, neg = s[y == 1], s[y == 0]
    if not len(pos) or not len(neg):
        return None
    gt = (pos[:, None] > neg[None, :]).mean()
    eq = (pos[:, None] == neg[None, :]).mean()
    return float(gt + 0.5 * eq)


# ------------------------------------------------------------------------------------------------------------------
# families
def jitter_offsets(fast):
    return (-2, 2) if fast else (-2, -1, 0, 1, 2)


def anchor_sets(P, Cc, P3p, C2p, C3p, fast):
    """(label, P tuple, C tuple): primary, C2', C3', P3' (where it differs), single-anchor jitters (the plan's 40 = 8
    anchors x offsets -2..+2; the 0 offsets reproduce the primary set)."""
    sets = [("primary", tuple(P), tuple(Cc))]
    sets.append(("C2'", tuple(P), (Cc[0], Cc[1], C2p, Cc[3])))
    sets.append(("C3'", tuple(P), (Cc[0], Cc[1], Cc[2], C3p)))
    if P3p != P[3]:
        sets.append(("P3'", (P[0], P[1], P[2], P3p), tuple(Cc)))
    for k, nm in enumerate(ANCH):
        for off in jitter_offsets(fast):
            Pj, Cj = list(P), list(Cc)
            if k < 4:
                Pj[k] += off
            else:
                Cj[k - 4] += off
            sets.append((f"jit:{nm}{off:+d}", tuple(Pj), tuple(Cj)))
    return sets


def build_members(P, Cc, P3p, C2p, C3p, end_rule, fast, real=True, c3p_from=None):
    """Members: level map x cap x anchor set. For a real series the parent ends at C0 - 1 week (2017-12-03 on TV); a C0
    jitter's parent ends at min(its own C0 - 1, the primary C0 - 1), so no parent runs into its own child or past the
    plan's 2017-12-03. For a placebo parent the end is its window end. c3p_from: the first child week at which the C3'
    anchor is known (the week after its window closes); the C3' members are not placed before it (data up to t only)."""
    out = []
    for lab, Ps, Cs in anchor_sets(P, Cc, P3p, C2p, C3p, fast):
        end = min(Cs[0] - 1, Cc[0] - 1) if real else end_rule
        act = int(c3p_from) if (lab == "C3'" and c3p_from is not None) else -1
        for mp_ in MAPS:
            for cap in CAPS:
                out.append({"map": mp_, "cap": cap, "P": Ps, "C": Cs, "end": int(end), "aset": lab, "activeFrom": act,
                            "label": f"{mp_}/cap{cap}/{lab}"})
    prim = next(i for i, m in enumerate(out) if m["aset"] == "primary" and m["map"] == "affine" and m["cap"] == PRIMARY_CAP)
    return out, prim


# ------------------------------------------------------------------------------------------------------------------
# placebo parents
def long_window(S, A):
    """The series' weekly logit from LONG_FROM to the parent end (C0 - 1 week), and the parent window inside it."""
    i0 = int(np.searchsorted(S["dates"], pd.Timestamp(LONG_FROM)))
    i1 = A["C0"] - 1
    x = S["x"][i0:i1 + 1].copy()
    return x, A["P0"] - i0, i1 - i0, i0


def t2_sources(sname, S_all, A_all, n_plc, seed):
    """Placebo parent sources per family: list of (key, x array, w0, w1)."""
    S, A = S_all[sname], A_all[sname]
    xl, w0, w1, i0 = long_window(S, A)
    L = w1 - w0 + 1
    rng = np.random.default_rng(seed)
    fam = {k: [] for k in FAM_KEYS}
    for i in range(n_plc):
        fam["a_iaaft"].append((f"a{i}", iaaft(xl, rng), w0, w1))
    for i in range(n_plc):
        fam["b_block8"].append((f"b{i}", block_shuffle(xl, rng, 8), w0, w1))
    for i in range(n_plc):
        fam["c_walk"].append((f"c{i}", matched_walk(xl, rng), w0, w1))
    d = S["dates"]
    starts = np.where((d >= pd.Timestamp(OFFSET_FROM)) & (d <= pd.Timestamp(OFFSET_TO)))[0]
    starts = [s for s in starts if s + L - 1 < len(d)]
    n_off_avail = len(starts)
    if len(starts) > n_plc:
        starts = [starts[int(round(q))] for q in np.linspace(0, len(starts) - 1, n_plc)]
    for s in starts:
        fam["d_offset"].append((f"d@{ds(d[s])}", S["x"], int(s), int(s + L - 1)))
    others = ["CMC", "OTHERS.D"] if sname in ("TV", "TVc") else ["TV", "OTHERS.D"]
    pend = S["dates"][A["C0"] - 1]
    cand = []
    for on in others:
        O = S_all[on]
        od = O["dates"]
        for s in range(len(od) - L + 1):
            if od[s + L - 1] <= pend:
                cand.append((f"e:{on}@{ds(od[s])}", on, s))
    n_other_avail = {on: sum(1 for c_ in cand if c_[1] == on) for on in others}
    if len(cand) > n_plc:
        cand = [cand[int(round(q))] for q in np.linspace(0, len(cand) - 1, n_plc)]
    for key, on, s in cand:
        fam["e_other"].append((key, S_all[on]["x"], int(s), int(s + L - 1)))
    rev = S["x"][A["P0"]:A["C0"]][::-1].copy()
    meta = {"surrogateWindow": [ds(S["dates"][i0]), ds(S["dates"][A["C0"] - 1])], "parentLengthWeeks": L,
            "parentCalendarPositions": [ds(S["dates"][A["P0"]]), ds(S["dates"][A["C0"] - 1])],
            "offsetStartsAvailable": n_off_avail, "offsetStartsUsed": len(starts),
            "offsetStartRange": [ds(d[starts[0]]), ds(d[starts[-1]])] if starts else None,
            "otherSeries": others, "otherWindowsAvailable": n_other_avail,
            "otherWindowsUsed": {on: sum(1 for c_ in cand if c_[1] == on) for on in others},
            "otherWindowRule": "every window of the parent's length ending on or before the parent end, spread evenly to the placebo count"}
    return fam, ("f_reversed", rev, 0, len(rev) - 1), meta


def pct_of(x):
    return inv(x)


# ------------------------------------------------------------------------------------------------------------------
# workers
_G = {}


def _init(G):
    _G.clear()
    _G.update(G)


def _job(args):
    kind = args[0]
    if kind == "family":
        return _job_family(args[1])
    if kind == "t2":
        return _job_t2(*args[1:])
    if kind == "t3":
        return _job_t3(*args[1:])
    if kind == "t1null":
        return _job_t1null(args[1])
    raise ValueError(kind)


def _job_family(sname):
    t0 = time.time()
    S = _G["S"][sname]
    members, prim = _G["members"][sname], _G["prim"][sname]
    t_list = _G["tlist"][sname]
    place, info, pt = walk_family({"x": S["x"], "pct": S["pct"]}, S["x"], members, t_list, primary_idx=prim, want_path_at_last=True)
    p, nplaced = family_prob(place, info, pt["h"])
    slim = [{k: v for k, v in i.items() if k != "nxt"} for i in info]
    return {"kind": "family", "series": sname, "place": place, "info": slim, "nxt": [i.get("nxt") for i in info], "prim": pt,
            "p": p, "nplaced": nplaced, "sec": time.time() - t0}


def _job_t2(sname, fam, items):
    S = _G["S"][sname]
    A = _G["A"][sname]
    C = (A["C0"], A["C1"], A["C2"], A["C3"])
    out = []
    for key, x, w0, w1 in items:
        r = t2_one({"x": x, "pct": pct_of(x)}, w0, w1, S["x"], C, _G["T"][sname])
        r["key"] = key
        out.append(r)
    return {"kind": "t2", "series": sname, "fam": fam, "rows": out}


def _job_t3(sname, fam, key, x, w0, w1, child_y=None):
    """One placebo parent's walk-forward: its anchors searched once against the real child's anchored part, then the same
    family and walk-forward as the real parent. child_y replaces the child (the leakage self-test feeds a child whose weeks
    after a cut are noise)."""
    t0 = time.time()
    S = _G["S"][sname]
    A, V = _G["A"][sname], _G["Vr"][sname]
    cy = S["x"] if child_y is None else child_y
    C = (A["C0"], A["C1"], A["C2"], A["C3"])
    best, _ = search_anchors(x, w0, w1, cy, C)
    if best is None:
        return {"kind": "t3", "series": sname, "fam": fam, "key": key, "ok": False, "sec": time.time() - t0}
    P = best[0]
    hi = min(P[2] + 8, w1 - 1)
    P3p = P[2] + 1 + int(np.argmin(x[P[2] + 1:hi + 1]))
    members, prim = build_members(P, C, P3p, V["C2'"], V["C3'"], w1, _G["fast"], real=False, c3p_from=_G["c3pFrom"][sname])
    t_list = _G["tlist_lab"][sname]
    place, info, pt = walk_family({"x": x, "pct": pct_of(x)}, cy, members, t_list, primary_idx=prim)
    if pt is None:
        return {"kind": "t3", "series": sname, "fam": fam, "key": key, "ok": False, "sec": time.time() - t0}
    p, nplaced = family_prob(place, info, pt["h"])
    return {"kind": "t3", "series": sname, "fam": fam, "key": key, "ok": True, "P": [int(v) - w0 for v in P], "p": p,
            "nplaced": nplaced, "nFeasible": int(sum(i["feasible"] for i in info)), "nMembers": len(members),
            "sec": time.time() - t0}


def _job_t1null(batch):
    """Labelled diagnostic (T1 null calibration and the placement base rate): the TV family placed at today's week on
    synthetic children = the real C0..C3 plus a synthetic open part. batch: list of (null kind, i, open-part logit)."""
    S, A, T = _G["S"]["TV"], _G["A"]["TV"], _G["T"]["TV"]
    members = _G["members"]["TV"]
    out = []
    for nk, i, op in batch:
        y = S["x"][:T + 1].copy()
        y[A["C3"] + 1:T + 1] = op
        place, _, _ = walk_family({"x": S["x"], "pct": S["pct"]}, y, members, [T])
        out.append({"nullKind": nk, "i": int(i), "places": place[:, 0].copy()})
    return {"kind": "t1null", "rows": out}


# ------------------------------------------------------------------------------------------------------------------
# scoring
def brier(p, y):
    p, y = np.asarray(p, float), np.asarray(y, float)
    return float(np.mean((np.clip(p, 0, 1) - y) ** 2))


def boot_mean(d, n=2000, bl=26, seed=0):
    """Circular block bootstrap of a mean (study8_common.block_boot's scheme: ceil(N/bl) random block starts)."""
    d = np.asarray(d, float)
    N = len(d)
    if N < 3:
        return {"n": 0}
    bl = max(1, min(int(bl), N))
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(N / bl))
    starts = rng.integers(0, N, size=(n, nb))
    idx = ((starts[:, :, None] + np.arange(bl)[None, None, :]) % N).reshape(n, nb * bl)[:, :N]
    v = d[idx].mean(axis=1)
    return {"n": int(n), "blockRows": bl, "q05": float(np.quantile(v, 0.05)), "q50": float(np.quantile(v, 0.5)), "q95": float(np.quantile(v, 0.95))}


def qdates(vals_ord, qs=(0.1, 0.5, 0.9)):
    v = np.asarray(vals_ord, float)
    v = v[np.isfinite(v)]
    if not len(v):
        return [None] * len(qs)
    return [float(np.quantile(v, q, method="nearest")) for q in qs]


def ord_to_date(o):
    if o is None or not np.isfinite(o):
        return None
    return ds(pd.Timestamp.fromordinal(int(round(o))))


# ------------------------------------------------------------------------------------------------------------------
# charts
def charts(out_dir, S_all, A_all, Vr_all, steps, fam_res, readout, t2res, wfp, labels_tv, fixed5_map):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "DejaVu Sans", "figure.facecolor": COL["bg"], "axes.facecolor": COL["bg"],
                         "savefig.facecolor": COL["bg"], "text.color": COL["text"], "axes.labelcolor": COL["sec"],
                         "xtick.color": COL["sec"], "ytick.color": COL["sec"], "axes.edgecolor": "#c9c8c3"})

    def style(ax, title=None):
        if title:
            ax.set_title(title, loc="left", fontsize=11, color=COL["text"])
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        ax.grid(axis="y", color=COL["grid"], linewidth=0.8)
        ax.tick_params(labelsize=8.5)
        ax.set_axisbelow(True)
    files = []
    S, A = S_all["TV"], A_all["TV"]
    d, pct = S["dates"], S["pct"]
    ro = readout["TV"]
    fr = fam_res["TV"]
    # 1) the anchored alignment
    fig, axs = plt.subplots(2, 1, figsize=(12, 8.2), dpi=100, gridspec_kw={"height_ratios": [1, 1]})
    ax = axs[0]
    i0p, i1p = A["P0"], A["C0"] - 1
    ax.plot(d[i0p:i1p + 1], pct[i0p:i1p + 1], color=COL["blue"], lw=2, label="parent: TradingView BTC.D, weekly close")
    if ro.get("nextWaterfall"):
        w = ro["nextWaterfall"]
        ax.axvspan(pd.Timestamp(w["start"]), pd.Timestamp(w["low"]), color=COL["orange"], alpha=0.13, lw=0,
                   label=f"parent's next waterfall {w['start']} to {w['low']} (low of the 16-week window)")
    pw = pd.Timestamp(ro["placedWeek"])
    ax.axvline(pw, color=COL["orange"], lw=2, label=f"today placed at parent week {ro['placedWeek']} (primary setting)")
    sd_ = [pd.Timestamp(s["date"]) for s in steps if d[i0p] - pd.Timedelta(days=6) <= pd.Timestamp(s["date"]) <= d[i1p]]
    ylo, yhi = float(np.min(pct[i0p:i1p + 1])), float(np.max(pct[i0p:i1p + 1]))
    rng_ = yhi - ylo
    ax.set_ylim(ylo - 0.16 * rng_, yhi + 0.14 * rng_)
    if sd_:
        ax.scatter(sd_, [ylo - 0.10 * rng_] * len(sd_), marker="^", s=46, color=COL["yellow"], zorder=5,
                   label="index-step day (TradingView TOTAL2 jump, see indexSteps)")
    offs = {"P0": (8, 6), "P1": (6, -16), "P2": (-8, 8), "P3": (8, -14)}
    for k in ("P0", "P1", "P2", "P3"):
        ax.scatter([d[A[k]]], [pct[A[k]]], s=64, color=COL["text"], zorder=6, edgecolors=COL["bg"], linewidths=1.5)
        ax.annotate(f"{k} {ds(d[A[k]])}\n{pct[A[k]]:.2f}", (d[A[k]], pct[A[k]]), textcoords="offset points", xytext=offs[k],
                    fontsize=8.5, color=COL["text"], ha="left" if offs[k][0] >= 0 else "right", va="bottom" if offs[k][1] >= 0 else "top")
    ax.set_ylabel("BTC.D %")
    ax.legend(fontsize=8.2, frameon=False, loc="center left", bbox_to_anchor=(0.0, 0.42))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    style(ax, "Parent: TradingView BTC.D, Jun 2016 - Dec 2017 (anchors P0-P3 by the plan's rules)")
    ax = axs[1]
    T = len(d) - 1
    ax.plot(d[A["C0"]:T + 1], pct[A["C0"]:T + 1], color=COL["blue"], lw=2, label="child: TradingView BTC.D, weekly close")
    path = fr["prim"].get("path")
    if path is not None and ro.get("a") is not None:
        ch = np.array(path["child"])
        pa = np.array(path["parent"])
        mapped = inv(ro["a"] + ro["b"] * S["x"][pa])
        # one value per child week (the last parent week matched)
        dfm = pd.DataFrame({"c": ch, "v": mapped}).groupby("c").last()
        ax.plot(d[dfm.index.values], dfm["v"].values, color=COL["orange"], lw=1.6,
                label=f"parent along the alignment, mapped child = a + b x parent in logit (a {ro['a']:.2f}, b {ro['b']:.2f})")
    cl, ch_ = float(np.min(pct[A["C0"]:T + 1])), float(np.max(pct[A["C0"]:T + 1]))
    cr = ch_ - cl
    ax.set_ylim(cl - 0.42 * cr, ch_ + 0.16 * cr)
    coffs = {"C0": (9, 2, "left", "bottom", True), "C1": (9, -4, "left", "top", True), "C2": (0, 9, "center", "bottom", False),
             "C3": (9, -8, "left", "top", True)}
    for k in ("C0", "C1", "C2", "C3"):
        ox, oy, ha, va, two = coffs[k]
        ax.scatter([d[A[k]]], [pct[A[k]]], s=64, color=COL["text"], zorder=6, edgecolors=COL["bg"], linewidths=1.5)
        txt = f"{k} {ds(d[A[k]])}\n{pct[A[k]]:.2f}" if two else f"{k} {ds(d[A[k]])}  {pct[A[k]]:.2f}"
        ax.annotate(txt, (d[A[k]], pct[A[k]]), textcoords="offset points", xytext=(ox, oy), fontsize=8.5, color=COL["text"], ha=ha, va=va)
    ax.scatter([d[T]], [pct[T]], s=50, color=COL["orange"], zorder=6, edgecolors=COL["bg"], linewidths=1.5)
    ax.annotate(f"today {ds(d[T])}\n{pct[T]:.2f}", (d[T], pct[T]), textcoords="offset points", xytext=(-8, 10), fontsize=8.5,
                ha="right", va="bottom", color=COL["text"])
    ax.set_ylabel("BTC.D %")
    ax.legend(fontsize=8.2, frameon=False, loc="lower right", ncol=1)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    style(ax, "Child: TradingView BTC.D, Dec 2017 - today (anchors C0-C3)")
    eq_to = float(inv(fwd(70.0) - (fwd(97.0) - fwd(95.0))))
    fig.text(0.01, 0.005, "Alignment on logit(BTC.D share): equal logit moves are equal shape moves; 97 -> 95 % in the parent is the same "
             f"logit move as 70 -> {eq_to:.0f} % in the child (before b). Levels in %.",
             fontsize=8.2, color=COL["sec"], ha="left", va="bottom")
    fig.tight_layout(rect=(0, 0.025, 1, 1))
    f1 = os.path.join(out_dir, "1_anchored_alignment.png")
    fig.savefig(f1)
    plt.close(fig)
    files.append(f1)

    # 2) walk-forward placement path
    rows = wfp
    if rows:
        xd = pd.DatetimeIndex([r["date"] for r in rows])
        p10 = pd.DatetimeIndex([r["p10"] for r in rows])
        p50 = pd.DatetimeIndex([r["p50"] for r in rows])
        p90 = pd.DatetimeIndex([r["p90"] for r in rows])
        pri = pd.DatetimeIndex([r["primary"] if r["primary"] else r["p50"] for r in rows])
        fig, axs = plt.subplots(3, 1, figsize=(12, 10.2), dpi=100, sharex=True, gridspec_kw={"height_ratios": [1.5, 1.0, 1.1]})
        ax = axs[0]
        ax.fill_between(xd, mdates.date2num(p10), mdates.date2num(p90), color=COL["blue"], alpha=0.16, lw=0, label="TV family p10-p90")
        ax.plot(xd, mdates.date2num(p50), color=COL["blue"], lw=2, label="TV family p50")
        ax.plot(xd, mdates.date2num(pri), color=COL["orange"], lw=1.4, label="primary setting (affine, cap 32, rule anchors)")
        ylo_ = mdates.date2num(min(p10.min(), pri.min()) - pd.Timedelta(weeks=5))
        yhi_ = mdates.date2num(max(p90.max(), pri.max()) + pd.Timedelta(weeks=3))
        if ro.get("nextWaterfall"):
            w = ro["nextWaterfall"]
            ws_, wl_ = mdates.date2num(pd.Timestamp(w["start"])), mdates.date2num(pd.Timestamp(w["low"]))
            yhi_ = max(yhi_, ws_ + 7 * 5)
            ax.axhspan(ws_, wl_, color=COL["orange"], alpha=0.10, lw=0,
                       label=f"parent's 2017 waterfall: start {w['start']} (first rule week after today's placement), low {w['low']}")
        ax.set_ylim(ylo_, yhi_)
        ax.yaxis_date()
        ax.yaxis.set_major_locator(mdates.MonthLocator())
        ax.yaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
        ax.set_ylabel("placed parent week")
        ax.legend(fontsize=8.2, frameon=False, loc="lower right")
        style(ax, "Walk-forward placement: the parent week matched to each child week, child data up to that week only")
        ax = axs[1]
        pp = np.array([r["p"] if r["p"] is not None else np.nan for r in rows])
        cl = np.array([r["clim"] if r["clim"] is not None else np.nan for r in rows])
        ax.plot(xd, pp, color=COL["blue"], lw=1.8, label="fractal p(t)")
        ax.plot(xd, cl, color=COL["sec"], lw=1.4, label="expanding climatology")
        f5x = [pd.Timestamp(r["date"]) for r in rows if r.get("fixed5") is not None]
        f5y = [r["fixed5"] for r in rows if r.get("fixed5") is not None]
        if f5x:
            ax.plot(f5x, f5y, color=COL["aqua"], lw=1.4, label="fixed5 (out-of-sample rows)")
        ax.set_ylim(-0.03, 1.42)
        ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
        ax.set_ylabel("P(5-pt fall in 26 w)")
        ax.legend(fontsize=8.2, frameon=False, loc="upper left", ncol=3)
        style(ax, None)
        ax = axs[2]
        lv = np.array([r["btcd"] for r in rows])
        ax.plot(xd, lv, color=COL["blue"], lw=2, label="TradingView BTC.D, weekly close")
        yv = np.array([r["y"] if r["y"] is not None else np.nan for r in rows])
        first = True
        for k in range(len(rows)):
            if yv[k] == 1:
                ax.axvspan(xd[k] - pd.Timedelta(days=3.5), xd[k] + pd.Timedelta(days=3.5), color=COL["orange"], alpha=0.18, lw=0,
                           label="fall week: a 5+ point fall within the next 26 weeks" if first else None)
                first = False
        ax.set_ylabel("BTC.D %")
        ax.legend(fontsize=8.2, frameon=False, loc="upper left")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
        style(ax, None)
        fig.tight_layout()
        f2 = os.path.join(out_dir, "2_walkforward_path.png")
        fig.savefig(f2)
        plt.close(fig)
        files.append(f2)

    # 3) T2 placebo distributions
    fig, axs = plt.subplots(3, 1, figsize=(12, 10.5), dpi=100)
    for ax, sname in zip(axs, SERIES):
        res = t2res.get(sname)
        if not res:
            ax.axis("off")
            continue
        names = [k for k in FAM_KEYS if res["families"].get(k, {}).get("n", 0) > 0]
        allv = []
        ticks = []
        for i, k in enumerate(names):
            v = np.array([x if x is not None else np.nan for x in res["families"][k].get("values", [])], float)
            v = v[np.isfinite(v)]
            pc = res["families"][k].get("realPercentile")
            ticks.append(f"{FAM_LABEL[k]}\nn {len(v)}, real at pct {pc:.0f}" if pc is not None else f"{FAM_LABEL[k]}\nn {len(v)}")
            if not len(v):
                continue
            allv += list(v)
            xs = i + np.random.default_rng(i).uniform(-0.22, 0.22, len(v))
            ax.scatter(xs, v, s=9, color=COL["sec"], alpha=0.35, lw=0)
            q05 = np.quantile(v, 0.05)
            ax.plot([i - 0.3, i + 0.3], [q05, q05], color=COL["aqua"], lw=2.2, label="placebo 5th percentile (pass line)" if i == 0 else None)
        xr = len(names)
        rv = (res.get("reversed") or {}).get("D")
        if rv is not None:
            ax.scatter([xr], [rv], s=70, color=COL["yellow"], zorder=5, edgecolors=COL["text"], linewidths=0.8, label=f"(f) reversed parent, D {rv:.4f}")
            allv.append(rv)
        if res.get("realD") is not None:
            ax.axhline(res["realD"], color=COL["blue"], lw=2, label=f"real parent with the anchor search, D {res['realD']:.4f}")
            allv.append(res["realD"])
        sv = res.get("stevenAnchorsD") if res.get("stevenAnchorsD") is not None else res.get("realRuleAnchorsD")
        if sv is not None:
            lab = "Steven's anchors (= the rule anchors)" if res.get("stevenAnchorsD") is not None else "the rule anchors (no search)"
            ax.axhline(sv, color=COL["orange"], lw=1.6, label=f"real parent, {lab}, D {sv:.4f}")
            allv.append(sv)
        ax.set_xticks(list(range(len(names))) + [xr], ticks + [FAM_LABEL["f_reversed"]], fontsize=8.2)
        av = np.array(allv, float)
        av = av[np.isfinite(av) & (av > 0)]
        if len(av):
            ax.set_yscale("log")
            ax.set_ylim(av.min() / 1.6, av.max() * 14)
        ax.set_xlim(-0.6, xr + 0.6)
        ax.set_ylabel("D (open-part MSR, logit^2)")
        ax.legend(fontsize=8.0, frameon=False, loc="upper left", ncol=2)
        style(ax, f"T2 {sname}: D of the open part, real parent vs placebo parents (each with the same anchor search)"
              + ("  [verdict series]" if sname == "TV" else ""))
    fig.tight_layout()
    f3 = os.path.join(out_dir, "3_t2_placebos.png")
    fig.savefig(f3)
    plt.close(fig)
    files.append(f3)
    return files


# ------------------------------------------------------------------------------------------------------------------
def main():
    ap_ = argparse.ArgumentParser(description="Round 14: Steven's July-2016 fractal (ROUND14_PLAN.md)")
    ap_.add_argument("--data", required=True)
    ap_.add_argument("--out", required=True)
    ap_.add_argument("--placebos", type=int, default=200, help="T2 placebo parents per family")
    ap_.add_argument("--wf-placebos", type=int, default=40, help="T3 walk-forward placebo parents per family (a)-(d)")
    ap_.add_argument("--workers", type=int, default=os.cpu_count() or 2)
    ap_.add_argument("--fast", action="store_true", help="placebos 20, wf-placebos 5, jitters thinned to +-2")
    a = ap_.parse_args()
    t_start = time.time()
    if a.fast:
        a.placebos, a.wf_placebos = 20, 5
    os.makedirs(a.out, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc)
    run_utc, run_est = utc_est(now)
    say(f"round 14 study start {run_utc} / {run_est}; numba {'on' if HAVE_NUMBA else 'OFF (pure-Python kernel, slow)'}; "
        f"workers {a.workers}; fast {a.fast}")
    notes = []
    diagnostics = {}

    # ---------------------------------------------------------------- data
    raw = {n: load_series(a.data, n) for n in ("BTC.D", "BTCD_CMC", "TOTAL2", "BTCUSD", "OTHERS.D")}
    for n, s in raw.items():
        if s is None:
            say(f"missing {n}_1d.csv")
            return 1
    last_day = raw["BTC.D"].index[-1]
    # the plan's TVc: CMC on TradingView's market day, chain anchored at the end (TVc = TV after the last step)
    L_tvc, steps, step_mask, Dd, tvc_info = build_tvc(raw["BTC.D"], raw["BTCD_CMC"], raw["TOTAL2"], raw["BTCUSD"])
    # labelled diagnostics: the first build (raw CMC labels, chained forward) and the forward chain on the aligned steps
    _, steps_raw, _, _, raw_info = build_tvc(raw["BTC.D"], raw["BTCD_CMC"], raw["TOTAL2"], raw["BTCUSD"],
                                             align_cmc=False, back_anchor=False)
    L_fwd, _, _, _, fwd_info = build_tvc(raw["BTC.D"], raw["BTCD_CMC"], raw["TOTAL2"], raw["BTCUSD"], back_anchor=False)
    align_ev = cmc_alignment_evidence(raw["BTC.D"], raw["BTCD_CMC"], a.data)

    def wk(s):
        w = weekly(s)
        return w[w.index <= last_day]
    S_all = {"TV": make_series("TV", wpct=wk(raw["BTC.D"])),
             "TVc": make_series("TVc", wlogit=wk(L_tvc)),
             "CMC": make_series("CMC", wpct=wk(raw["BTCD_CMC"])),
             "OTHERS.D": make_series("OTHERS.D", wpct=wk(raw["OTHERS.D"]))}
    partial = weekly(raw["BTC.D"])
    partial = partial[partial.index > last_day]
    lastw = S_all["TV"]["dates"][-1]
    if len(partial):
        notes.append(f"Weekly = W-SUN last close of complete weeks: the daily files end {ds(last_day)}, so the week ending "
                     f"{ds(partial.index[-1])} (BTC.D {partial.iloc[-1]:.2f} so far) is partial and excluded; today's child week is "
                     f"{ds(lastw)} (BTC.D {S_all['TV']['pct'][-1]:.2f}).")
    say(f"TV weekly {ds(S_all['TV']['dates'][0])}..{ds(lastw)} ({len(S_all['TV']['dates'])}); index steps 2014-2018: {len(steps)}")
    for s in steps:
        say(f"  step {s['date']}: dTV {s['dTV']:+.3f} dCMC {s['dCMC']:+.3f} dlogTOTAL2 {s['dlogTOTAL2']:+.3f} dlogBTCUSD {s['dlogBTCUSD']:+.3f}")

    # ---------------------------------------------------------------- anchors
    A_all, Vr_all, rules_c2p = {}, {}, {}
    series_out = {}
    for sn in SERIES:
        S = S_all[sn]
        A, V, c2r = rule_anchors(S["dates"], S["pct"])
        A_all[sn], Vr_all[sn], rules_c2p[sn] = A, V, c2r
        d = S["dates"]
        anch = {k: {"date": ds(d[A[k]]), "level": r4(S["pct"][A[k]], 2), "logit": r4(S["x"][A[k]], 4),
                    "expectedTV": EXPECTED_TV[k], "matchesExpectedTV": ds(d[A[k]]) == EXPECTED_TV[k]} for k in ANCH}
        var = {k: {"date": ds(d[V[k]]), "level": r4(S["pct"][V[k]], 2)} for k in V}
        var["C2'"]["rule"] = c2r
        var["C3'"]["rule"] = "min weekly close in 2021-07-01..2022-06-30"
        var["P3'"]["rule"] = "min weekly close in (P2, P2 + 8 weeks]"
        var["P3'"]["differsFromP3"] = bool(V["P3'"] != A["P3"])
        if sn == "TV":
            var["C2'"]["expectedTV"] = EXPECTED_TV_VARIANTS["C2'"]
            var["C2'"]["matchesExpectedTV"] = var["C2'"]["date"] == EXPECTED_TV_VARIANTS["C2'"]
        mism = [k for k in ANCH if not anch[k]["matchesExpectedTV"]]
        series_out[sn] = {"source": {"TV": "data/BTC.D_1d.csv (TradingView CRYPTOCAP:BTC.D); the W-SUN weekly close is the Sunday bar's "
                                           "close (Monday 00:00 UTC)",
                                     "TVc": "TV with index steps removed (see indexSteps and construction); equal to TV on and after the "
                                            "last step day",
                                     "CMC": "data/BTCD_CMC_1d.csv (CoinMarketCap global dominance, the plan's canonical file, as built). Its "
                                            "row dated d is the snapshot at d 00:02 UTC, so the W-SUN weekly close is CMC's snapshot at "
                                            "Sunday 00:02 UTC, i.e. Saturday's close, one day before TradingView's weekly close (the "
                                            "Sunday-close version is diagnostics.cmcSundayClose)"}[sn],
                          "weeklyFrom": ds(d[0]), "weeklyTo": ds(d[-1]), "nWeeks": len(d), "anchors": anch, "variants": var,
                          "parentWindow": [ds(d[A["P0"]]), ds(d[A["C0"] - 1])], "childWindow": [ds(d[A["C0"]]), ds(d[-1])],
                          "allAnchorsMatchExpectedTV": not mism, "anchorsDifferingFromExpectedTV": mism,
                          "today": {"date": ds(d[-1]), "level": r4(S["pct"][-1], 2)}}
        say(f"{sn} anchors: " + ", ".join(f"{k} {ds(d[A[k]])} ({S['pct'][A[k]]:.2f})" for k in ANCH)
            + f" | C2' {ds(d[V[chr(67) + '2' + chr(39)]])}, C3' {ds(d[V['C3' + chr(39)]])}, P3' {ds(d[V['P3' + chr(39)]])}"
            + (f" | differ from expected TV dates: {mism}" if mism else " | all match the expected TV dates"))
    tvc_off = float(S_all["TVc"]["x"][-1] - S_all["TV"]["x"][-1])  # 0 by construction (back-anchored)
    tvc_parent_levels = ", ".join("%s %.2f" % (k, S_all["TVc"]["pct"][A_all["TVc"][k]]) for k in ("P0", "P1", "P2", "P3"))
    tv_parent_levels = ", ".join("%.2f" % S_all["TV"]["pct"][A_all["TV"][k]] for k in ("P0", "P1", "P2", "P3"))
    series_out["TVc"]["construction"] = {"rule": "a day in 2014-04-01..2018-12-31 is a step when |dTV - dCMC| >= 0.75 points and "
                                                 "dlog TOTAL2 - dlog BTCUSD >= 0.20 in the direction that moves BTC.D the way the gap does; "
                                                 "on step days logit TVc moves by CoinMarketCap's logit change, otherwise by TradingView's",
                                         "cmcAlignment": "CoinMarketCap's labels moved back one day (its row dated d+1 is the close of "
                                                         "TradingView's day d), so dCMC(d) is the same market day as dTV(d); evidence in "
                                                         "indexSteps.alignment",
                                         "chain": "back-anchored to TV after the last step: TVc = TV on and after the last step day "
                                                  f"({tvc_info['lastStepDay']}), so the steps are removed from the history before it",
                                         "nStepDays": len(steps), "logitOffsetVsTVAfterLastStep": r4(tvc_off, 6),
                                         "forwardChainOffsetLogit": r4(tvc_info["forwardChainOffsetLogit"], 4),
                                         "note": "the forward chain (from TradingView's first day) is TVc shifted by the sum of the step "
                                                 f"corrections ({tvc_info['forwardChainOffsetLogit']:+.3f} logit)",
                                         "caveat": "back-anchoring turns TradingView's narrow-index 2016 logit moves into larger percentage "
                                                   f"moves: TVc's parent anchors read {tvc_parent_levels} (TV: {tv_parent_levels})"}

    # ---------------------------------------------------------------- index-step audit (T0)
    def near_rows(step_list, sn):
        d = S_all[sn]["dates"]
        rows = []
        allA = dict(A_all[sn])
        allA.update({k: v for k, v in Vr_all[sn].items()})
        for k, idx in allA.items():
            aw = d[idx]
            hits = [s["date"] for s in step_list if abs((week_of(s["date"]) - aw).days) <= 7]
            rows.append({"anchor": k, "date": ds(aw), "stepsWithin1Week": hits, "nearStep": bool(hits)})
        return rows
    near = {sn: near_rows(steps, sn) for sn in SERIES}
    # one-day prints: a step day whose TradingView move reverses (>= half) on a neighbouring day that is not a step
    Ltv_d = pd.Series(fwd(Dd["tv"].values), index=Dd.index)
    Lcm_d = pd.Series(fwd(Dd["cmc"].values), index=Dd.index)
    step_days = set(s["date"] for s in steps)
    prints = []
    for s in steps:
        d0 = pd.Timestamp(s["date"])
        for nb in (d0 - pd.Timedelta(days=1), d0 + pd.Timedelta(days=1)):
            if nb not in Dd.index or ds(nb) in step_days:
                continue
            dnb = float(Dd["tv"].diff()[nb])
            if np.sign(dnb) == -np.sign(s["dTV"]) and abs(dnb) >= 0.5 * abs(s["dTV"]):
                a0, a1 = min(d0, nb) - pd.Timedelta(days=1), max(d0, nb)
                tv2, cm2, tc2 = (float(Ltv_d[a1] - Ltv_d[a0]), float(Lcm_d[a1] - Lcm_d[a0]), float(L_tvc[a1] - L_tvc[a0]))
                prints.append({"stepDay": s["date"], "neighbourDay": ds(nb), "dTVstep": s["dTV"], "dTVneighbour": r4(dnb, 3),
                               "twoDayLogitTV": r4(tv2, 4), "twoDayLogitCMC": r4(cm2, 4), "twoDayLogitTVc": r4(tc2, 4),
                               "residualTVcMinusTV": r4(tc2 - tv2, 4), "residualTVcMinusCMC": r4(tc2 - cm2, 4)})
    index_steps = {"window": f"{STEP_FROM}..{STEP_TO}", "thresholds": {"gapPoints": STEP_PTS, "altExcessLog": STEP_LOG},
                   "steps": steps, "nSteps": len(steps), "anchorsNearSteps": near,
                   "nearRule": "a step is within 1 week of an anchor when the step's W-SUN week is the anchor's week or the week before/after",
                   "alignment": align_ev,
                   "oneDayPrintResiduals": {"rows": prints,
                                            "note": "a one-day print shared by both days of a pair is only half-corrected by the plan's rule: "
                                                    "the step day takes CoinMarketCap's move while the reverting neighbour (not a step) keeps "
                                                    "TradingView's, so TVc keeps the step day's correction over the pair"},
                   "rawLabelSteps": "the list built on CMC's raw labels (one day late) is in diagnostics.indexStepsRawLabels"}
    diagnostics["indexStepsRawLabels"] = {
        "status": "labelled diagnostic: the step detector on CoinMarketCap's raw labels, i.e. TradingView's day d against CMC's "
                  "previous market day (the first build); superseded by the aligned list in indexSteps",
        "steps": steps_raw, "nSteps": len(steps_raw), "forwardChainOffsetLogit": r4(raw_info["forwardChainOffsetLogit"], 4),
        "droppedByAlignment": sorted(set(s["date"] for s in steps_raw) - step_days),
        "addedByAlignment": sorted(step_days - set(s["date"] for s in steps_raw)),
        "anchorsNearStepsTV": [r["anchor"] for r in near_rows(steps_raw, "TV") if r["nearStep"]]}
    near_tv_al = [r["anchor"] for r in near["TV"] if r["nearStep"]]
    near_tv_raw = diagnostics["indexStepsRawLabels"]["anchorsNearStepsTV"]
    index_steps["readingTV"] = (f"on a same-market-day comparison the TV anchors within 1 week of a step are {near_tv_al or 'none'} "
                                f"(on CMC's raw labels, one day late: {near_tv_raw or 'none'}); "
                                + ("the July-2016 bottom (P1) is not on a step: CoinMarketCap fell with TradingView in July 2016"
                                   if "P1" not in near_tv_al else "the July-2016 bottom (P1) sits within 1 week of a step"))

    # ---------------------------------------------------------------- labels, climatology, fixed5
    tvd = S_all["TV"]["dates"]
    P_tv = pd.DataFrame({"BTC.D": S_all["TV"]["pct"]}, index=tvd)
    Y = C8.targets(P_tv, "W", falls=(5.0,), horizons=(LABEL_H,))
    ylab = Y["fall5_26w"].values.astype(float)
    clim = np.full(len(tvd), np.nan)
    cs = np.nancumsum(np.nan_to_num(ylab, nan=0.0))
    cn = np.cumsum(np.isfinite(ylab).astype(float))
    for t in range(len(tvd)):
        s = t - LABEL_H
        if s >= 0 and cn[s] > 0:
            clim[t] = cs[s] / cn[s]
    clim4 = np.full(len(tvd), np.nan)  # labelled T3 diagnostic: trailing 4-year climatology, labels known at t only
    for t in range(len(tvd)):
        s = t - LABEL_H
        if s >= 0:
            w_ = ylab[max(0, s - TRAIL_CLIM_WEEKS + 1):s + 1]
            w_ = w_[np.isfinite(w_)]
            if len(w_):
                clim4[t] = float(w_.mean())
    f5 = {}
    f5src = []
    f5check = {}
    for rel, key in (("out8/honest/results.json", "fixed5_fall5_26w"), ("out9/candidates/results.json", "fixed5")):
        fp = os.path.join(HERE, rel)
        if not os.path.exists(fp):
            continue
        try:
            dd = json.load(open(fp))
            rows = dd["series"][key]
        except Exception:
            continue
        diffs = []
        n_new = 0
        had = bool(f5)
        for r in rows:
            if r["t"] in f5:
                diffs.append(abs(f5[r["t"]] - float(r["v"])))
            else:
                f5[r["t"]] = float(r["v"])
                n_new += 1
        f5src.append({"file": f"research/btcd_fractal/{rel}", "key": f"series.{key}", "rows": len(rows), "first": rows[0]["t"], "last": rows[-1]["t"]})
        if diffs:
            f5check["maxAbsDiffOnCommonDates"] = max(diffs)
            f5check["nCommonDates"] = len(diffs)
        if had:
            f5check["nDatesOnlyInSecondFile"] = n_new
    say(f"fixed5 out-of-sample rows: {len(f5)} dates from {[s['file'] for s in f5src]}")

    # ---------------------------------------------------------------- families and t grids
    T_all, members_all, prim_all, tlist_all, tlist_lab, c3p_from = {}, {}, {}, {}, {}, {}
    for sn in SERIES:
        S, A, V = S_all[sn], A_all[sn], Vr_all[sn]
        T = len(S["dates"]) - 1
        T_all[sn] = T
        P = (A["P0"], A["P1"], A["P2"], A["P3"])
        Cc = (A["C0"], A["C1"], A["C2"], A["C3"])
        # C3' (min weekly close in 2021-07-01..2022-06-30) is known only once its window has closed: its members are
        # placed from the first week after 2022-06-30 (in T3 and in every placebo walk-forward)
        c3p_from[sn] = int(np.searchsorted(S["dates"], pd.Timestamp(C3P_WINDOW[1]), side="right"))
        members_all[sn], prim_all[sn] = build_members(P, Cc, V["P3'"], V["C2'"], V["C3'"], None, a.fast, real=True,
                                                      c3p_from=c3p_from[sn])
        tlist_all[sn] = np.arange(A["C3"] + T3_LAG, T + 1, dtype=np.int64)
        tlist_lab[sn] = np.arange(A["C3"] + T3_LAG, T - LABEL_H + 1, dtype=np.int64)
    say(f"family size per series: {len(members_all['TV'])} (2 maps x 3 caps x {len(members_all['TV']) // 6} anchor sets)")

    if HAVE_NUMBA:
        tw = time.time()
        warm_up()
        say(f"kernel compiled in {time.time() - tw:.1f}s")

    # ---------------------------------------------------------------- placebo sources
    t2src, t2rev, t2meta = {}, {}, {}
    for si, sn in enumerate(SERIES):
        fam, rev, meta = t2_sources(sn, S_all, A_all, a.placebos, BASE_SEED + 101 * si)
        t2src[sn], t2rev[sn], t2meta[sn] = fam, rev, meta
    t3src = {}
    for sn in SERIES:
        lst = []
        for fk in FAM_KEYS[:4]:
            items = t2src[sn][fk]
            if fk == "d_offset" and len(items) > a.wf_placebos:
                items = [items[int(round(q))] for q in np.linspace(0, len(items) - 1, a.wf_placebos)]
            else:
                items = items[:a.wf_placebos]
            lst += [(fk, it) for it in items]
        t3src[sn] = lst

    # synthetic children (labelled diagnostics: the T1 null calibration and the placement base rate): the real C0..C3 plus
    # an open part that is either a logit random walk matched to the child's post-C3 increment sd or an 8-week block
    # bootstrap of the child's own post-C3 increments; plus one child frozen at C3's level
    S, A = S_all["TV"], A_all["TV"]
    T = T_all["TV"]
    post = S["x"][A["C3"]:T + 1]
    inc = np.diff(post)
    sd_inc = float(np.std(inc))
    nopen = T - A["C3"]
    rng = np.random.default_rng(BASE_SEED + 55)
    n_syn = 40 if a.fast else 200
    syn_parts = []
    for kind in ("walk", "block"):
        for i in range(n_syn):
            if kind == "walk":
                op = S["x"][A["C3"]] + np.cumsum(rng.normal(0.0, sd_inc, nopen))
            else:
                bl = 8
                nb = int(np.ceil(nopen / bl))
                st_ = rng.integers(0, len(inc), size=nb)
                ii = np.concatenate([(np.arange(s, s + bl) % len(inc)) for s in st_])[:nopen]
                op = S["x"][A["C3"]] + np.cumsum(inc[ii])
            syn_parts.append((kind, i, op))
    syn_parts.append(("flat", 0, S["x"][A["C3"]] + np.random.default_rng(BASE_SEED + 56).normal(0.0, 0.01, nopen)))

    G = {"S": S_all, "A": A_all, "Vr": Vr_all, "T": T_all, "members": members_all, "prim": prim_all, "tlist": tlist_all,
         "tlist_lab": tlist_lab, "fast": a.fast, "c3pFrom": c3p_from}
    _init(G)

    # ---------------------------------------------------------------- run everything in the pool
    jobs = [("family", sn) for sn in SERIES]
    jobs += [("t1null", syn_parts[k:k + 10]) for k in range(0, len(syn_parts), 10)]
    for sn in SERIES:
        for fk, (key, x, w0, w1) in t3src[sn]:
            jobs.append(("t3", sn, fk, key, x, w0, w1))
    for sn in SERIES:
        for fk in FAM_KEYS:
            items = t2src[sn][fk]
            for k in range(0, len(items), 25):
                jobs.append(("t2", sn, fk, items[k:k + 25]))
        jobs.append(("t2", sn, "f_reversed", [t2rev[sn][:1] + t2rev[sn][1:]]))
    say(f"{len(jobs)} jobs ({sum(j[0] == 't3' for j in jobs)} walk-forward placebos, {sum(j[0] == 't2' for j in jobs)} T2 batches, "
        f"{sum(j[0] == 't1null' for j in jobs)} T1-null batches of {len(syn_parts)} synthetic children) on {a.workers} workers")
    tp = time.time()
    results = []
    try:
        ctx = mp.get_context("fork")
    except ValueError:  # pragma: no cover
        ctx = None
    if a.workers > 1:
        with ProcessPoolExecutor(a.workers, mp_context=ctx, initializer=_init, initargs=(G,)) as ex:
            for k, r in enumerate(ex.map(_job, jobs, chunksize=1)):
                results.append(r)
                if (k + 1) % max(1, len(jobs) // 10) == 0:
                    say(f"  {k + 1}/{len(jobs)} jobs done, {time.time() - tp:.0f}s")
    else:
        for r in map(_job, jobs):
            results.append(r)
    say(f"pool done in {time.time() - tp:.0f}s")
    fam_res = {r["series"]: r for r in results if isinstance(r, dict) and r.get("kind") == "family"}
    t3_res = [r for r in results if isinstance(r, dict) and r.get("kind") == "t3"]
    t2_rows = [r for r in results if isinstance(r, dict) and r.get("kind") == "t2"]
    null_rows = [row for r in results if isinstance(r, dict) and r.get("kind") == "t1null" for row in r["rows"]]

    # ---------------------------------------------------------------- placement, T1, steady clock, read-out
    placement = {"primary": {}, "family": {}, "steadyClock": {}}
    readout = {}
    pooled_ord = []
    for sn in SERIES:
        S, A = S_all[sn], A_all[sn]
        d = S["dates"]
        fr = fam_res[sn]
        mem = members_all[sn]
        place_today = fr["place"][:, -1]
        prim_i = prim_all[sn]
        jp = int(place_today[prim_i])
        pt = fr["prim"]
        ords = np.array([d[j].toordinal() if j >= 0 else np.nan for j in place_today], float)
        feas = np.array([i["feasible"] for i in fr["info"]])
        ok = np.isfinite(ords)
        pooled_ord += list(ords[ok])
        q = qdates(ords[ok])
        by = {}
        for key, f in (("map", lambda m: m["map"]), ("cap", lambda m: str(m["cap"])), ("anchorSet", lambda m: m["aset"].split(":")[0] if m["aset"].startswith("jit") else m["aset"])):
            grp = {}
            for mi, m in enumerate(mem):
                grp.setdefault(f(m), []).append(mi)
            by[key] = {g: {"n": len(ix), "nPlaced": int(ok[ix].sum()), "p50": ord_to_date(qdates(ords[ix][ok[ix]], (0.5,))[0]) if ok[ix].any() else None}
                       for g, ix in grp.items()}
        infeasible = [m["label"] for mi, m in enumerate(mem) if not feas[mi]]
        segs_ = [(f"C{k}..C{k + 1}", A[f"C{k + 1}"] - A[f"C{k}"] + 1, f"P{k}..P{k + 1}", A[f"P{k + 1}"] - A[f"P{k}"] + 1) for k in range(3)]
        tight_ = max(segs_, key=lambda s_: s_[1] / s_[3])
        need_ = int(math.ceil(tight_[1] / tight_[3]))
        placement["family"][sn] = {"n": len(mem), "nPlaced": int(ok.sum()), "nInfeasible": int((~feas).sum()),
                                   "p10": ord_to_date(q[0]), "p50": ord_to_date(q[1]), "p90": ord_to_date(q[2]), "by": by,
                                   "infeasibleMembers": infeasible[:80],
                                   "infeasibleNote": (f"no path exists for {int((~feas).sum())} members (a cap below what an anchored segment "
                                                      f"needs); on the primary anchors the tightest segment puts the {tight_[1]} child weeks "
                                                      f"{tight_[0]} on the {tight_[3]} parent weeks {tight_[2]}, so caps below {need_} have no "
                                                      "path there")}
        lvl = float(S["pct"][jp]) if jp >= 0 else None
        placement["primary"][sn] = {"setting": "affine level map, cap 32, rule anchors", "placedWeek": ds(d[jp]) if jp >= 0 else None,
                                    "placedLevel": r4(lvl, 2), "a": r4(pt["a"], 4), "b": r4(pt["b"], 4), "bUnclipped": r4(pt["b_raw"], 4),
                                    "penaltyLambda": r4(pt["lam"], 6), "lambdaFixedPointConverged": bool(pt["conv"]),
                                    "anchoredMSR": r4(pt["amse"], 6), "openD": r4(pt.get("D"), 6),
                                    "parentWeeksAfterP3": int(jp - A["P3"]) if jp >= 0 else None}
        # steady clock through (P1, C1) and (P3, C3)
        T = T_all[sn]
        rate = (A["P3"] - A["P1"]) / (A["C3"] - A["C1"])
        jst = A["P1"] + (T - A["C1"]) * rate
        jr = int(round(jst))
        placement["steadyClock"][sn] = {"childWeeksPerParentWeek": r4(1 / rate, 3), "parentWeekFractional": r4(jst - A["P1"], 2),
                                        "parentWeeksAfterP1": r4(jst - A["P1"], 2),
                                        "date": ds(d[A["P1"]] + pd.Timedelta(weeks=float(jst - A["P1"]))),
                                        "nearestWeek": ds(d[jr]) if jr < len(d) else None,
                                        "levelAtNearestWeek": r4(S["pct"][jr], 2) if jr < len(d) else None}
        # read-out
        ro = {"placedWeek": ds(d[jp]) if jp >= 0 else None, "placedLevel": r4(lvl, 2), "today": ds(d[T]), "todayLevel": r4(S["pct"][T], 2)}
        end = A["C0"] - 1
        flag_s, nxt = wf_next(S["pct"], A["P0"], end)
        wfs = int(nxt[jp - A["P0"]]) if jp >= 0 else -1
        if wfs >= 0:
            hi = min(wfs + WF_WEEKS, end)
            low = wfs + 1 + int(np.argmin(S["pct"][wfs + 1:hi + 1]))
            low_all = wfs + 1 + int(np.argmin(S["pct"][wfs + 1:end + 1]))
            k_s, k_l = wfs - jp, low - jp
            clocks = {}
            loc = float(pt["clock"][-1]) if np.isfinite(pt["clock"][-1]) else None
            avg = (T - A["C3"]) / (jp - A["P3"]) if jp > A["P3"] else None
            steady = (A["C3"] - A["C1"]) / (A["P3"] - A["P1"])
            for nm, ck in (("local52", loc), ("avg2021today", avg), ("steady2018to2021", steady)):
                if ck is None:
                    clocks[nm] = None
                    continue
                cw_s, cw_l = k_s * ck, k_l * ck
                clocks[nm] = {"childWeeksPerParentWeek": r4(ck, 3), "childWeeksToStart": r4(cw_s, 1), "childWeeksToLow": r4(cw_l, 1),
                              "startDate": ds(d[T] + pd.Timedelta(weeks=float(cw_s))), "lowDate": ds(d[T] + pd.Timedelta(weeks=float(cw_l)))}
            if clocks.get("local52") is not None:  # labelled diagnostic: is the local clock a parking artefact?
                dl52 = int(pt["delta"][-1])
                clocks["local52"].update({
                    "deltaParentWeeksOverLast52ChildWeeks": dl52, "parked": bool(0 <= dl52 <= 1),
                    "parkedNote": (f"parked: the last 52 child weeks advance the path by {dl52} parent week (one parent week holds at "
                                   f"most {PRIMARY_CAP} child weeks, so 52 weeks need 2 columns); the clock reads 52 by construction, "
                                   "not from a matched shape" if 0 <= dl52 <= 1 else "not parked")})
            a_, b_ = pt["a"], pt["b"]
            mv = float(S["x"][low] - S["x"][jp])
            cy = S["x"][A["C0"]:T + 1]
            crange = float(cy.max() - cy.min())
            proj_abs = a_ + b_ * float(S["x"][low])
            proj_anch = float(S["x"][T]) + b_ * mv
            ro.update({"nextWaterfall": {"start": ds(d[wfs]), "startLevel": r4(S["pct"][wfs], 2), "low": ds(d[low]), "lowLevel": r4(S["pct"][low], 2),
                                         "parentWeeksToStart": int(k_s), "parentWeeksToLow": int(k_l),
                                         "lowRule": "min weekly close in (start, start + 16 weeks], the rule's own window",
                                         "parentLowToEnd": {"date": ds(d[low_all]), "level": r4(S["pct"][low_all], 2)},
                                         "expectedOnTV": "about 2017-03-05" if sn == "TV" else None},
                       "clocks": clocks,
                       "levelMap": {"a": r4(a_, 4), "b": r4(b_, 4), "parentLogitMovePlacedToLow": r4(mv, 4),
                                    "parentPointsMovePlacedToLow": r4(S["pct"][low] - S["pct"][jp], 2),
                                    "mappedChildLogitMove": r4(b_ * mv, 4), "childWholeLogitRange": r4(crange, 4),
                                    "ratioParentMoveToChildRange": r4(abs(mv) / crange if crange > 0 else None, 3),
                                    "projectionThroughAB": {"childLogit": r4(proj_abs, 4), "btcdPct": r4(inv(proj_abs), 2)},
                                    "projectionAnchoredAtToday": {"childLogit": r4(proj_anch, 4), "btcdPct": r4(inv(proj_anch), 2)},
                                    "outOfRange": bool(abs(mv) > crange or abs(b_ * mv) > crange),
                                    "flagRule": "out of range when the parent's logit move from the placed week to the waterfall low "
                                                "(raw or times b) exceeds the child's whole logit range C0..today",
                                    "status": "diagnostic only"}})
            # the first rule week after P3 (the waterfall's start as seen from the open part's start)
            f_after = int(nxt[A["P3"] - A["P0"]])
            ro["waterfallStartAfterP3"] = ds(d[f_after]) if f_after >= 0 else None
        else:
            ro["nextWaterfall"] = None
            ro["note"] = "no week after the placed week satisfies the 15-points-in-16-weeks rule inside the parent"
        # labelled diagnostic: the waterfall calendar for every placeable week (P3, end] and the episode reading
        eps = wf_episodes(S["pct"], A["P0"], end, flag_s)
        cal = []
        for j in range(A["P3"] + 1, end + 1):
            nx = int(nxt[j - A["P0"]])
            cal.append({"week": ds(d[j]), "level": r4(S["pct"][j], 2), "ruleFlag": bool(flag_s[j - A["P0"]]),
                        "nextWaterfallStart": ds(d[nx]) if nx >= 0 else None, "parentWeeksToStart": int(nx - j) if nx >= 0 else None,
                        "mappedChildLevelPrimary": r4(inv(pt["a"] + pt["b"] * S["x"][j]), 2) if pt.get("a") is not None else None,
                        "episodeClass": episode_class(j, eps)})
        one_wk = [r["week"] for r in cal if r["parentWeeksToStart"] == 1]
        ro["waterfallCalendar"] = {
            "status": "labelled diagnostic beside the plan's read-out",
            "weeks": cal,
            "episodes": [{"firstFlag": ds(d[ep["firstFlag"]]), "lastFlag": ds(d[ep["lastFlag"]]), "top": ds(d[ep["top"]]),
                          "topLevel": r4(S["pct"][ep["top"]], 2),
                          "firstDeclineWeek": ds(d[ep["firstDecline"]]) if ep["firstDecline"] is not None else None,
                          "firstDeclineLevel": r4(S["pct"][ep["firstDecline"]], 2) if ep["firstDecline"] is not None else None,
                          "low": ds(d[ep["low"]]), "lowLevel": r4(S["pct"][ep["low"]], 2)} for ep in eps],
            "episodeRule": "flag runs merged across gaps under 16 weeks; top = max close over the flagged span; first decline week = "
                           "the first week after the top that closes below every close from the first flag to the top; low = min close "
                           "in (top, last flag + 16 weeks]",
            "placedWeekClass": episode_class(jp, eps) if jp >= 0 else None,
            "nOpenPartWeeks": len(cal),
            "nWeeksWithNextStartWithin4": int(sum(1 for r in cal if r["parentWeeksToStart"] is not None and r["parentWeeksToStart"] <= 4)),
            "nWeeksWithNextStartAtPlus1": len(one_wk),
            "note": (f"the 15-in-16 flag holds on {int(flag_s.sum())} parent weeks; the read-out's next start is the placed week + 1 for "
                     f"{len(one_wk)} of the {len(cal)} placeable weeks ({one_wk[0]}..{one_wk[-1]}), including weeks inside the decline, "
                     "so 'next waterfall at +1 week' does not by itself say the placement is before the fall; the episode class does"
                     if one_wk else "no placeable week has the next rule week one week later")}
        ro["a"], ro["b"] = pt["a"], pt["b"]
        readout[sn] = ro
    pq = qdates(pooled_ord)
    placement["family"]["pooled"] = {"n": len(pooled_ord), "p10": ord_to_date(pq[0]), "p50": ord_to_date(pq[1]), "p90": ord_to_date(pq[2])}
    # T1 on the TV family
    frT = fam_res["TV"]
    dT = S_all["TV"]["dates"]
    ordT = np.array([dT[j].toordinal() if j >= 0 else np.nan for j in frT["place"][:, -1]], float)
    okT = np.isfinite(ordT)
    med = float(np.quantile(ordT[okT], 0.5, method="nearest"))
    within = np.abs(ordT[okT] - med) <= 28
    share = float(within.mean())
    memT = members_all["TV"]
    nz = np.array([not m["aset"].endswith("+0") for m in memT])
    okz = okT & nz
    medz = float(np.quantile(ordT[okz], 0.5, method="nearest"))
    share_z = float((np.abs(ordT[okz] - medz) <= 28).mean())
    share_inf = float(within.sum() / len(memT))
    placement["T1"] = {"series": "TV", "familyMedian": ord_to_date(med), "share": r4(share, 4), "threshold": 0.8,
                       "nMembersPlaced": int(okT.sum()), "nMembers": len(memT), "verdict": "robust" if share >= 0.8 else "fragile",
                       "rule": "share of the placed TV family members within +-4 parent weeks of the TV family median",
                       "diagnostics": {"shareWithoutZeroOffsetJitters": r4(share_z, 4), "medianWithoutZeroOffsetJitters": ord_to_date(medz),
                                       "verdictWithoutZeroOffsetJitters": "robust" if share_z >= 0.8 else "fragile",
                                       "shareCountingInfeasibleAsMisses": r4(share_inf, 4),
                                       "note": (f"the plan's 40 single-anchor jitters (8 anchors x offsets -2..+2) include "
                                                f"{len({m['aset'] for m in memT if m['aset'].endswith('+0')})} zero offsets that repeat the "
                                                "primary anchor set; the share without them is shown beside the verdict"
                                                if (~nz).any() else "this run's jitters have no zero offsets (--fast thins them to +-2), "
                                                "so the share without them equals the share")}}
    placement["T1byRerun"] = {}
    for sn in ("TVc", "CMC"):
        fr = fam_res[sn]
        d = S_all[sn]["dates"]
        o = np.array([d[j].toordinal() if j >= 0 else np.nan for j in fr["place"][:, -1]], float)
        ok = np.isfinite(o)
        m_ = float(np.quantile(o[ok], 0.5, method="nearest"))
        sh = float((np.abs(o[ok] - m_) <= 28).mean())
        placement["T1byRerun"][sn] = {"familyMedian": ord_to_date(m_), "share": r4(sh, 4), "verdict": "robust" if sh >= 0.8 else "fragile",
                                      "status": "reported beside TV, never a verdict input"}
    say(f"T1 (TV family): median {ord_to_date(med)}, share within +-4 weeks {share:.3f} -> {placement['T1']['verdict']}")
    placement["T1"]["diagnostics"]["verdictCountingInfeasibleAsMisses"] = "robust" if share_inf >= 0.8 else "fragile"
    placement["T1"]["diagnostics"]["denominatorNote"] = (
        f"the verdict counts placed members only ({int(okT.sum())} of {len(memT)}); {len(memT) - int(okT.sum())} members have no "
        f"feasible path; counting them as misses gives {share_inf:.3f} ({'robust' if share_inf >= 0.8 else 'fragile'} under that plain "
        "reading of 'share of the TV family')")

    # ---------------------------------------------------------------- T1 labelled diagnostics beside the verdict
    S, A = S_all["TV"], A_all["TV"]
    d = S["dates"]
    T = T_all["TV"]
    par_tv = {"x": S["x"], "pct": S["pct"]}
    Pp = (A["P0"], A["P1"], A["P2"], A["P3"])
    Cp = (A["C0"], A["C1"], A["C2"], A["C3"])
    end_tv = A["C0"] - 1
    n_open = T - A["C3"]
    jp_tv = int(frT["place"][prim_all["TV"], -1])
    flag_tv, nxt_tv = wf_next(S["pct"], A["P0"], end_tv)
    eps_tv = wf_episodes(S["pct"], A["P0"], end_tv, flag_tv)
    ep0 = next((ep for ep in eps_tv if ep["low"] > A["P3"]), None)
    a_p, b_p = frT["prim"]["a"], frT["prim"]["b"]
    # (i) the cap: members placed per cap, the primary member's cap sweep, the per-segment clocks
    by_cap = {}
    for cap in CAPS:
        ix = [mi for mi, m in enumerate(memT) if m["cap"] == cap]
        wk_ = [ds(dT[int(frT["place"][mi, -1])]) for mi in ix if frT["place"][mi, -1] >= 0]
        by_cap[str(cap)] = {"nMembers": len(ix), "nPlaced": len(wk_),
                            "weeks": {k: int(v) for k, v in pd.Series(wk_, dtype=object).value_counts().sort_index().items()} if wk_ else {},
                            "shareOfPlacedWithinPm4OfFamilyMedian": r4(float(np.mean([abs(pd.Timestamp(w).toordinal() - med) <= 28 for w in wk_])), 4) if wk_ else None}
    sweep = []
    for cap in CAP_SWEEP:
        e_ = eval_member(par_tv, S["x"], Pp, Cp, end_tv, T, "affine", cap)
        floor = A["P3"] + int(math.ceil((T - A["C3"] + 1) / cap)) - 1
        sweep.append({"cap": cap, "feasible": e_ is not None, "placedWeek": ds(d[e_["place"]]) if e_ else None, "D": r4(e_["D"], 4) if e_ else None,
                      "capFloorWeek": ds(d[floor]) if floor <= end_tv else "beyond the parent end",
                      "placedAtCapFloor": bool(e_ is not None and e_["place"] == floor),
                      "episodeClass": episode_class(e_["place"], eps_tv) if e_ else None})
    seg = []
    for c0k, c1k, p0k, p1k in (("C0", "C1", "P0", "P1"), ("C1", "C2", "P1", "P2"), ("C2", "C3", "P2", "P3")):
        cw, pw = A[c1k] - A[c0k], A[p1k] - A[p0k]
        seg.append({"segment": f"{c0k}-{c1k} / {p0k}-{p1k}", "childWeeks": int(cw), "parentWeeks": int(pw), "childPerParent": r4(cw / pw, 2)})
    if jp_tv > A["P3"]:
        seg.append({"segment": "open part (C3, today] / (P3, placed week]", "childWeeks": int(T - A["C3"]), "parentWeeks": int(jp_tv - A["P3"]),
                    "childPerParent": r4((T - A["C3"]) / (jp_tv - A["P3"]), 2)})
    seg.append({"segment": "steady clock (P1,C1)-(P3,C3)", "childWeeks": int(A["C3"] - A["C1"]), "parentWeeks": int(A["P3"] - A["P1"]),
                "childPerParent": r4((A["C3"] - A["C1"]) / (A["P3"] - A["P1"]), 2)})
    rat = [s_["childPerParent"] for s_ in seg[:3]]
    n16_, m16_ = by_cap["16"]["nPlaced"], by_cap["16"]["nMembers"]
    infeas_caps = [s_["cap"] for s_ in sweep if not s_.get("feasible")]
    floor_caps = [s_["cap"] for s_ in sweep if s_.get("placedAtCapFloor")]
    placement["capDiagnostics"] = {
        "status": "labelled diagnostic beside T1 (TV)", "byCap": by_cap, "capSweepPrimary": sweep, "segmentClocks": seg,
        "note": (f"the anchors alone need {min(rat):.1f} to {max(rat):.1f} child weeks per parent week across the three anchored segments "
                 f"(the mapping is not one time scale); cap 16 places {n16_} of its {m16_} members "
                 f"(cap 32: {by_cap['32']['nPlaced']} of {by_cap['32']['nMembers']}; cap 64: {by_cap['64']['nPlaced']} of "
                 f"{by_cap['64']['nMembers']})"
                 + ("; with most cap-16 members infeasible, the plan's cap robustness is largely untested at the small end"
                    if n16_ < 0.5 * m16_ else "")
                 + (f"; the primary anchors are infeasible at caps {infeas_caps}" if infeas_caps else "")
                 + (f"; the primary placement sits on the cap floor at caps {floor_caps} (capSweepPrimary)" if floor_caps
                    else "; the primary placement is never on the cap floor in the sweep (capSweepPrimary)"))}
    # (ii) T1 null calibration: the same TV family on synthetic children (real C0..C3, synthetic open part)
    syn_prim = {"walk": [], "block": [], "flat": []}
    null_cal = {}
    for nk in ("block", "walk", "flat"):
        sh_, sha_, meds_ = [], [], []
        for r_ in [r for r in null_rows if r["nullKind"] == nk]:
            pl_ = np.asarray(r_["places"])
            syn_prim[nk].append(int(pl_[prim_all["TV"]]))
            o_ = np.array([dT[j].toordinal() if j >= 0 else np.nan for j in pl_], float)
            ok_ = np.isfinite(o_)
            if not ok_.any():
                continue
            m_ = float(np.quantile(o_[ok_], 0.5, method="nearest"))
            w_ = np.abs(o_[ok_] - m_) <= 28
            sh_.append(float(w_.mean()))
            sha_.append(float(w_.sum() / len(o_)))
            meds_.append(ord_to_date(m_))
        sh_ = np.array(sh_, float)
        sha_ = np.array(sha_, float)
        null_cal[nk] = {"n": int(len(sh_)), "passShare": r4(float(np.mean(sh_ >= 0.8)), 4) if len(sh_) else None,
                        "shareMean": r4(float(np.mean(sh_)), 4) if len(sh_) else None,
                        "shareQ05Q50Q95": [r4(float(np.quantile(sh_, q_)), 4) for q_ in (0.05, 0.5, 0.95)] if len(sh_) else None,
                        "shareAllMembersMean": r4(float(np.mean(sha_)), 4) if len(sha_) else None,
                        "realSharePercentile": r4(100.0 * float(np.mean(sh_ < share) + 0.5 * np.mean(sh_ == share)), 2) if len(sh_) else None,
                        "realSharePercentileRule": "mid-rank: null shares below the real share plus half of the ties",
                        "nullShareAtOrAboveReal": r4(float(np.mean(sh_ >= share)), 4) if len(sh_) else None,
                        "familyMedianWeeks": {k: int(v) for k, v in pd.Series(meds_, dtype=object).value_counts().head(5).items()}}
    nb_, nw_ = null_cal["block"].get("passShare"), null_cal["walk"].get("passShare")
    placement["T1"]["nullCalibration"] = {
        "status": "labelled diagnostic beside the plan's T1 verdict",
        "design": f"the full TV family ({len(memT)} members) placed at today's week on synthetic children: the real C0..C3 plus an open part "
                  f"of {n_open} weeks that is an 8-week block bootstrap of the child's own post-C3 logit increments ({n_syn}), a logit random "
                  f"walk matched to their sd {sd_inc:.4f} ({n_syn}), or the child frozen at C3's level (1); T1 share computed as for the real "
                  "child (placed members, +-4 weeks of the family median)",
        "realShare": r4(share, 4), "byNull": null_cal,
        "reading": (f"{100 * nb_:.0f}% of block-bootstrap children and {100 * nw_:.0f}% of matched walks also pass T1, so a 'robust' "
                    + ("placement is the expected outcome under the null, not evidence that the child follows the parent"
                       if min(nb_, nw_) >= 0.5 else
                       "placement is common under the null and is not evidence on its own that the child follows the parent"
                       if max(nb_, nw_) >= 0.2 else "placement is uncommon under the null")
                    if nb_ is not None and nw_ is not None else None)}
    # (iii) the level lookup: what the open-end DTW compares
    co = S["x"][A["C3"] + 1:T + 1]
    lk_rows = []
    for j in range(A["P3"] + 1, end_tv + 1):
        lk_rows.append({"week": ds(d[j]), "parentLevel": r4(S["pct"][j], 2), "mappedChildLevel": r4(inv(a_p + b_p * S["x"][j]), 2),
                        "class": coarse_class(j, ep0)})
    plat = [j for j in range(A["P3"] + 1, end_tv + 1) if coarse_class(j, ep0) == "plateau"]
    jmax = max(plat, key=lambda j: a_p + b_p * S["x"][j]) if plat else None
    mapped_max = float(inv(a_p + b_p * S["x"][jmax])) if jmax is not None else None
    mapped_min_plat = float(min(inv(a_p + b_p * S["x"][j]) for j in plat)) if plat else None
    j_low = ep0["low"] if ep0 else None
    j_dec = ep0["firstDecline"] if ep0 else None
    share_above = float(np.mean(inv(co) > mapped_max)) if mapped_max is not None else None
    # positive controls: a crash in the child's last 26 weeks, and a child planted as the mapped parent through week J
    crash = []
    for Lp in (55, 50, 45, 40, 35, 30, 25, 20, 15, 10, 5):
        y = S["x"][:T + 1].copy()
        y[T - 25:T + 1] = np.linspace(S["x"][T - 26], float(fwd(Lp)), 27)[1:]
        e_ = eval_member(par_tv, y, Pp, Cp, end_tv, T)
        crash.append({"childEndLevel": Lp, "placedWeek": ds(d[e_["place"]]) if e_ else None,
                      "placedParentLevel": r4(S["pct"][e_["place"]], 2) if e_ else None,
                      "class": coarse_class(e_["place"], ep0) if e_ else None})
    entry = max([c_["childEndLevel"] for c_ in crash if c_["class"] == "decline"], default=None)
    replica = []
    for J in ("2017-02-26", "2017-03-26", "2017-04-30", "2017-05-21", "2017-07-16", "2017-08-27", "2017-10-29", "2017-12-03"):
        tsJ = pd.Timestamp(J)
        if tsJ not in d:
            continue
        jj = int(d.get_loc(tsJ))
        if not (A["P3"] < jj <= end_tv):
            continue
        src = a_p + b_p * S["x"][A["P3"]:jj + 1]
        tt = np.linspace(0, len(src) - 1, n_open + 1)[1:]
        y = S["x"][:T + 1].copy()
        y[A["C3"] + 1:T + 1] = np.interp(tt, np.arange(len(src)), src) - src[0] + S["x"][A["C3"]]
        e_ = eval_member(par_tv, y, Pp, Cp, end_tv, T)
        replica.append({"plantedThrough": J, "childEndLevel": r4(inv(y[T]), 2), "placedWeek": ds(d[e_["place"]]) if e_ else None,
                        "parentWeeksFromPlanted": int(e_["place"] - jj) if e_ else None})
    placement["levelLookup"] = {
        "status": "labelled diagnostic (TV, primary affine map)", "a": r4(a_p, 4), "b": r4(b_p, 4),
        "weeks": lk_rows,
        "childOpenPartRangePct": [r4(inv(co.min()), 2), r4(inv(co.max()), 2)], "childOpenPartMeanPct": r4(inv(co.mean()), 2),
        "childTodayPct": r4(S["pct"][T], 2),
        "mappedPlateauMax": {"week": ds(d[jmax]) if jmax is not None else None, "mappedChildLevel": r4(mapped_max, 2)},
        "shareOfChildOpenWeeksAboveMappedPlateauMax": r4(share_above, 4) if share_above is not None else None,
        "firstDeclineWeek": ds(d[ep0["firstDecline"]]) if ep0 and ep0["firstDecline"] is not None else None,
        "mappedLevelAtFirstDeclineWeek": r4(inv(a_p + b_p * S["x"][ep0["firstDecline"]]), 2) if ep0 and ep0["firstDecline"] is not None else None,
        "childLevelAtWhichPlacementEntersDecline": entry,
        "childLevelRule": "the highest end level (5-point grid) of the crash control whose placement lies inside the decline",
        "reading": (f"under the map the parent's open part reads {mapped_min_plat:.1f}-{mapped_max:.1f}% on the plateau ({ds(d[plat[0]])}.."
                    f"{ds(d[plat[-1]])}), {float(inv(a_p + b_p * S['x'][j_dec])):.1f}% at the first decline week ({ds(d[j_dec])}) and "
                    f"{float(inv(a_p + b_p * S['x'][j_low])):.1f}% at the low ({ds(d[j_low])}); the child's open part runs "
                    f"{inv(co.min()):.1f}-{inv(co.max()):.1f}% (mean {inv(co.mean()):.1f}%), with {100 * share_above:.0f}% of its weeks above "
                    "the plateau's mapped maximum"
                    + (", so the open-end DTW parks today on the highest reachable parent weeks (the top just before the fall)"
                       if share_above >= 0.5 else "")
                    + "; the placement moves with the child's level (placement.positiveControls)"
                    if mapped_max is not None and j_dec is not None and j_low is not None else None)}
    placement["positiveControls"] = {
        "status": "labelled diagnostic (TV, primary setting)",
        "crash": {"design": "the child's last 26 weeks replaced by a straight logit line to the given level", "rows": crash},
        "plantedReplica": {"design": "the child's open part replaced by the mapped parent from P3 through week J, stretched over the open "
                                     "part and started at C3's level", "rows": replica}}

    # ---------------------------------------------------------------- T2
    t2out = {}
    for sn in SERIES:
        S, A = S_all[sn], A_all[sn]
        d = S["dates"]
        T = T_all[sn]
        C = (A["C0"], A["C1"], A["C2"], A["C3"])
        par = {"x": S["x"], "pct": S["pct"]}
        st = eval_member(par, S["x"], (A["P0"], A["P1"], A["P2"], A["P3"]), C, A["C0"] - 1, T)
        sr = t2_one(par, A["P0"], A["C0"] - 1, S["x"], C, T)
        exp_ok = all(series_out["TV"]["anchors"][k]["matchesExpectedTV"] for k in ANCH)
        steven = None
        if sn == "TV":
            Pexp = tuple(int(d.get_loc(pd.Timestamp(EXPECTED_TV[k]))) for k in ("P0", "P1", "P2", "P3"))
            Cexp = tuple(int(d.get_loc(pd.Timestamp(EXPECTED_TV[k]))) for k in ("C0", "C1", "C2", "C3"))
            ev = eval_member(par, S["x"], Pexp, Cexp, Cexp[0] - 1, T)
            steven = r4(ev["D"], 6) if ev else None
        fams = {}
        for fk in FAM_KEYS:
            rows = [r for b in t2_rows if b["series"] == sn and b["fam"] == fk for r in b["rows"]]
            vals = np.array([r["D"] if r["D"] is not None else np.nan for r in rows], float)
            fin = vals[np.isfinite(vals)]
            real = sr["D"]
            if len(fin):
                q05 = float(np.quantile(fin, 0.05))
                fams[fk] = {"label": FAM_LABEL[fk], "n": len(rows), "nValid": int(len(fin)), "q05": r4(q05, 6), "q50": r4(np.median(fin), 6),
                            "q95": r4(np.quantile(fin, 0.95), 6), "min": r4(fin.min(), 6),
                            "realPercentile": r4(100.0 * float(np.mean(fin <= real)), 2) if real is not None else None,
                            "pass": bool(real is not None and real < q05), "values": [r4(v, 6) for v in vals.tolist()]}
            else:
                fams[fk] = {"label": FAM_LABEL[fk], "n": len(rows), "nValid": 0, "pass": False, "values": []}
        revrows = [r for b in t2_rows if b["series"] == sn and b["fam"] == "f_reversed" for r in b["rows"]]
        revD = revrows[0]["D"] if revrows else None
        pooled = np.array([v for fk in FAM_KEYS for v in fams[fk]["values"] if v is not None], float)
        npass = int(sum(fams[fk]["pass"] for fk in FAM_KEYS))
        rev_worse = bool(revD is not None and sr["D"] is not None and revD > sr["D"])
        t2pass = bool(npass >= 4 and rev_worse)
        Ps = sr.get("P")
        # labelled T2 diagnostics: what D is made of (level vs shape), b clipping, copies and distinct configurations
        co_ = S["x"][A["C3"] + 1:T + 1]
        flat_D = float(np.var(co_))
        st_split = open_split(st, S["x"], S["x"], A["C3"]) if st else (None, None, None)
        real_D, real_var = sr.get("D"), sr.get("var")
        rule_P = (A["P0"], A["P1"], A["P2"], A["P3"])
        diag_f = {}
        for fk in FAM_KEYS:
            rows = [r for b in t2_rows if b["series"] == sn and b["fam"] == fk for r in b["rows"]]
            good = [r for r in rows if r.get("D") is not None and r.get("bias2") is not None]
            if not good:
                diag_f[fk] = {"n": 0}
                continue
            D_ = np.array([r["D"] for r in good], float)
            b2_ = np.array([r["bias2"] for r in good], float)
            v_ = np.array([r["var"] for r in good], float)
            br_ = np.array([r["bRaw"] for r in good], float)
            clip_ = (br_ < BMIN) | (br_ > BMAX)
            uD = np.unique(np.round(D_, 6))
            ent = {"n": len(good), "medianBiasShareOfD": r4(float(np.median(b2_ / np.maximum(D_, 1e-12))), 3),
                   "corrLogDLogBias2": r4(float(np.corrcoef(np.log(D_), np.log(b2_ + 1e-12))[0, 1]), 3) if len(good) > 2 and np.std(D_) > 0 else None,
                   "varianceOnlyQ05": r4(float(np.quantile(v_, 0.05)), 6),
                   "varianceOnlyRealPercentile": r4(100.0 * float(np.mean(v_ <= real_var)), 2) if real_var is not None else None,
                   "shareBeatingFlatLine": r4(float(np.mean(D_ < flat_D)), 4),
                   "shareBClipped": r4(float(clip_.mean()), 4), "shareBClippedHigh": r4(float(np.mean(br_ > BMAX)), 4),
                   "shareBClippedLow": r4(float(np.mean(br_ < BMIN)), 4),
                   "medianDClipped": r4(float(np.median(D_[clip_])), 6) if clip_.any() else None,
                   "medianDUnclipped": r4(float(np.median(D_[~clip_])), 6) if (~clip_).any() else None,
                   "nDistinctD": int(len(uD)),
                   "realPercentileAmongDistinctD": r4(100.0 * float(np.mean(uD <= real_D)), 2) if real_D is not None else None}
            if fk in ("d_offset", "e_other"):
                ent["nDistinctAnchorSets"] = len(set((r["key"].split("@")[0], tuple(r["P"])) for r in good))
            if fk == "d_offset":
                Preal_s = tuple(Ps) if Ps else None
                over = [r for r in good if r["P"][0] <= A["P3"] and r["P"][3] >= A["P0"]]
                keep = np.array([r["D"] for r in good if not (r["P"][0] <= A["P3"] and r["P"][3] >= A["P0"]) and tuple(r["P"]) != Preal_s], float)
                ent["copiesOfRealParent"] = {"nEqualRealSearchAnchors": sum(1 for r in good if Preal_s is not None and tuple(r["P"]) == Preal_s),
                                             "nEqualRuleAnchors": sum(1 for r in good if tuple(r["P"]) == rule_P),
                                             "nOverlappingRealP0toP3": len(over)}
                ent["dPrime"] = {"rule": "(d) without the windows whose searched anchors equal the real search anchors or overlap the real "
                                         "P0..P3 span", "n": int(len(keep)),
                                 "q05": r4(float(np.quantile(keep, 0.05)), 6) if len(keep) else None,
                                 "realPercentile": r4(100.0 * float(np.mean(keep <= real_D)), 2) if len(keep) and real_D is not None else None,
                                 "pass": bool(len(keep) and real_D is not None and real_D < float(np.quantile(keep, 0.05)))}
            diag_f[fk] = ent
        bsh_ = [diag_f[fk]["medianBiasShareOfD"] for fk in FAM_KEYS if diag_f[fk].get("medianBiasShareOfD") is not None]
        cor_ = [diag_f[fk]["corrLogDLogBias2"] for fk in FAM_KEYS if diag_f[fk].get("corrLogDLogBias2") is not None]
        rs_bias = (sr.get("bias2") / real_D) if (real_D and sr.get("bias2") is not None) else None
        rr_bias = (st_split[1] / st_split[0]) if (st_split[0] and st_split[1] is not None) else None
        dist_ = "; ".join(f"{fk[0]}: {diag_f[fk]['nDistinctD']} distinct D in {diag_f[fk]['n']} windows"
                          for fk in ("d_offset", "e_other") if diag_f[fk].get("n"))
        cop_ = diag_f["d_offset"].get("copiesOfRealParent", {}) if diag_f["d_offset"].get("n") else {}
        t2_note = ((f"the level mismatch (bias^2) is {100 * rs_bias:.0f}% of the real parent's D under the search anchors" if rs_bias is not None else
                    "the real parent's D split is unavailable")
                   + (f" and {100 * rr_bias:.0f}% under the rule anchors" if rr_bias is not None else "")
                   + (f", against a median of {100 * min(bsh_):.0f}-{100 * max(bsh_):.0f}% across the placebo families" if bsh_ else "")
                   + (f"; across placebos corr(log D, log bias^2) is {min(cor_):.2f}-{max(cor_):.2f} per family"
                      + (", so D's ranking largely follows the level match of the 4-point affine map" if min(cor_) >= 0.5 else "")
                      if cor_ else "")
                   + "; the variance-only percentiles show whether the fail survives with the level removed"
                   + (f"; {dist_} (nDistinctD, nDistinctAnchorSets)" if dist_ else "")
                   + (f"; {cop_['nEqualRealSearchAnchors']} (d) window{'s' if cop_['nEqualRealSearchAnchors'] > 1 else ''} reproduce"
                      f"{'' if cop_['nEqualRealSearchAnchors'] > 1 else 's'} the real parent's search anchors (dPrime drops them)"
                      if cop_.get("nEqualRealSearchAnchors") else ""))
        t2diag = {"status": "labelled diagnostics beside the plan's T2",
                  "decomposition": "D = bias^2 (squared mean open-part residual: a level mismatch of the 4-point affine map) + variance "
                                   "(the shape mismatch); varianceOnly* use the variance alone (bias removed)",
                  "flatLineD": r4(flat_D, 6),
                  "flatLineRule": "a flat line at the child's own open-part mean: D = var(child logit over (C3, today])",
                  "realSearch": {"D": r4(real_D, 6), "bias2": r4(sr.get("bias2"), 6), "variance": r4(real_var, 6), "b": r4(sr.get("b"), 4),
                                 "bUnclipped": r4(sr.get("bRaw"), 4), "beatsFlatLine": bool(real_D is not None and real_D < flat_D)},
                  "realRuleAnchors": {"D": r4(st_split[0], 6), "bias2": r4(st_split[1], 6), "variance": r4(st_split[2], 6),
                                      "b": r4(st["b"], 4) if st else None, "bUnclipped": r4(st["b_raw"], 4) if st else None,
                                      "beatsFlatLine": bool(st_split[0] is not None and st_split[0] < flat_D)},
                  "families": diag_f,
                  "note": t2_note}
        t2out[sn] = {"statistic": "D = mean squared residual over the open part's path cells (child (C3, today]) under the primary setting",
                     "realD": r4(sr["D"], 6), "realSearchAnchors": ({k: ds(d[v]) for k, v in zip(("P0", "P1", "P2", "P3"), Ps)} if Ps else None),
                     "realSearchCombos": sr["nCombos"], "realSearchFeasible": sr["nFeasible"],
                     "realRuleAnchorsD": r4(st["D"], 6) if st else None, "stevenAnchorsD": steven if sn == "TV" else None,
                     "stevenAnchorsNote": ("the expected TV dates; identical to the rule anchors" if exp_ok else "the expected TV dates (the rules differ)") if sn == "TV" else None,
                     "realSearchPlacedWeek": ds(d[A["P0"] + sr["place"]]) if sr.get("place") is not None else None,
                     "families": fams, "familiesPassing": npass, "reversed": {"D": r4(revD, 6), "worseThanReal": rev_worse,
                                                                             "percentileAmongPlacebos": r4(100.0 * float(np.mean(pooled <= revD)), 2) if revD is not None and len(pooled) else None},
                     "pass": t2pass, "rule": "real D below the placebo 5th percentile in >= 4 of the 5 families (a)-(e), and (f) worse than the real parent",
                     "meta": t2meta[sn], "diagnostics": t2diag}
        say(f"T2 {sn}: real D (search) {sr['D']}, rule anchors {st['D'] if st else None}; families passing {npass}/5; reversed {revD}; pass {t2pass}")

    # ---------------------------------------------------------------- T3
    t3out = {}
    t3diag = {}
    wfp_rows = []
    yser = pd.Series(ylab, index=tvd)
    cser = pd.Series(clim, index=tvd)
    for sn in SERIES:
        S, A = S_all[sn], A_all[sn]
        d = S["dates"]
        fr = fam_res[sn]
        tl = tlist_all[sn]
        tlab = tlist_lab[sn]
        nlab = len(tlab)
        p_all = fr["p"]
        dates_t = d[tl]
        p_lab = p_all[:nlab]
        dl = d[tlab]
        yv = yser.reindex(dl).values
        cv = cser.reindex(dl).values
        okm = np.isfinite(p_lab) & np.isfinite(yv) & np.isfinite(cv)
        bf = brier(p_lab[okm], yv[okm])
        bc = brier(cv[okm], yv[okm])
        dloss = (cv[okm] - yv[okm]) ** 2 - (np.clip(p_lab[okm], 0, 1) - yv[okm]) ** 2
        bb = boot_mean(dloss, bl=26, seed=BASE_SEED + 7)
        # fixed5 on common weeks
        f5v = np.array([f5.get(ds(x), np.nan) for x in dl], float)
        okf = okm & np.isfinite(f5v)
        fx = {}
        if okf.sum() >= 3:
            bfx = brier(f5v[okf], yv[okf])
            bf_c = brier(p_lab[okf], yv[okf])
            bc_c = brier(cv[okf], yv[okf])
            dl5 = (f5v[okf] - yv[okf]) ** 2 - (np.clip(p_lab[okf], 0, 1) - yv[okf]) ** 2
            spacing = int(np.median(np.diff(np.where(okf)[0]))) if okf.sum() > 1 else 1
            fx = {"nCommonWeeks": int(okf.sum()), "rowSpacingWeeks": spacing, "brierFractal": r4(bf_c, 5), "brierFixed5": r4(bfx, 5),
                  "brierClimatology": r4(bc_c, 5), "improvementFractalOverFixed5": r4(bfx - bf_c, 5),
                  "improvementFractalOverClimatologyOnCommonWeeks": r4(bc_c - bf_c, 5),
                  "boot": {k: r4(v, 5) if isinstance(v, float) else v for k, v in boot_mean(dl5, bl=max(1, 26 // max(spacing, 1)), seed=BASE_SEED + 8).items()},
                  "fixed5Sources": f5src, "fixed5Consistency": f5check,
                  "fullWindowBriers": {"nWeeks": int(okm.sum()), "brierFractal": r4(bf, 5), "brierClimatology": r4(bc, 5)},
                  "coverage": (f"fixed5 is scored on alternate weeks only ({int(okf.sum())} of the {int(okm.sum())} T3 weeks): both source "
                               "files were thinned to every 2 weeks (study8_common.thin(every=2)) with the same parity, and the second "
                               f"file adds {f5check.get('nDatesOnlyInSecondFile', 0)} dates to the first (identical values on "
                               f"{f5check.get('nCommonDates', 0)} common dates), so the merge reads out8 only; the common-week fractal "
                               "and climatology Briers above differ from the full-window ones (fullWindowBriers)"),
                  "selection": "walk-forward fits with a 26-week label lag, but the signal set was selected post hoc over refits "
                               "through 2026 (round 8 note: 'a post-hoc comparator, not a pre-registered one'), so fixed5's Brier is an "
                               "optimistic benchmark"}
        # placebos
        plc = {}
        allimp = []
        allzero = []
        for fk in FAM_KEYS[:4]:
            rs = [r for r in t3_res if r.get("series") == sn and r.get("fam") == fk]
            imps = []
            for r in rs:
                if not r.get("ok"):
                    continue
                pp = np.asarray(r["p"], float)
                m2 = okm & np.isfinite(pp)
                if m2.sum() < 3:
                    continue
                imps.append(brier(cv[m2], yv[m2]) - brier(pp[m2], yv[m2]))
                allzero.append(bool(np.max(pp[m2]) == 0.0))
            imps = np.array(imps, float)
            allimp += list(imps)
            plc[fk] = {"label": FAM_LABEL[fk], "n": len(rs), "nValid": int(len(imps)), "p95": r4(np.quantile(imps, 0.95), 5) if len(imps) else None,
                       "median": r4(np.median(imps), 5) if len(imps) else None, "values": [r4(v, 5) for v in imps.tolist()]}
        allimp = np.array(allimp, float)
        imp = bc - bf
        p95_pool = float(np.quantile(allimp, 0.95)) if len(allimp) else float("nan")
        above_each = {fk: (plc[fk]["p95"] is not None and imp > plc[fk]["p95"]) for fk in plc}
        t3pass = bool(imp > 0 and bb.get("q05", -1) > 0 and len(allimp) > 0 and imp > p95_pool)
        ybar = float(np.mean(yv[okm]))
        h_lab = np.asarray(fr["prim"]["h"][:nlab], float)
        pl_ = p_lab[okm]
        t3diag[sn] = {"constantForecasts": {"brierAlwaysZero": r4(brier(np.zeros(okm.sum()), yv[okm]), 5),
                                            "brierPeriodBaseRateOracle": r4(ybar * (1 - ybar), 5),
                                            "improvementOfAlwaysZeroOverClimatology": r4(bc - brier(np.zeros(okm.sum()), yv[okm]), 5),
                                            "note": ("the T3 window's fall rate is below the expanding climatology's, so p = 0 beats the "
                                                     "climatology; placebo parents whose families never sit just before a waterfall score that"
                                                     if bc - brier(np.zeros(okm.sum()), yv[okm]) > 0 else
                                                     "p = 0 does not beat the climatology in this window")},
                      "pShape": {"shareOfWeeksPEqualsZeroOrOne": r4(float(np.mean((pl_ == 0) | (pl_ == 1))), 4),
                                 "shareOfWeeksPIsOne": r4(float(np.mean(pl_ == 1)), 4),
                                 "shareOfWeeksHAtLeastOne": r4(float(np.mean(h_lab[okm] >= 1)), 4),
                                 "agreementPIsOneWithHAtLeastOne": r4(float(np.mean((pl_ == 1) == (h_lab[okm] >= 1))), 4),
                                 "note": ("p(t) = 0 every week: no parent week satisfies the 15-in-16 rule after the placed weeks"
                                          if len(pl_) and float(np.max(pl_)) == 0.0 else
                                          "the 15-in-16 flag runs for months (see readout.<series>.waterfallCalendar), so a placed week "
                                          "inside it has the next rule week one week later; p(t) = 1 exactly when h(t) >= 1 (local clock "
                                          f"<= 26) on {100 * float(np.mean((pl_ == 1) == (h_lab[okm] >= 1))):.0f}% of the weeks"
                                          + (", so p(t) is close to that indicator" if float(np.mean((pl_ == 1) == (h_lab[okm] >= 1))) >= 0.9
                                             else ""))},
                      "fallWeeksMeanP": r4(float(np.mean(pl_[yv[okm] == 1])) if (yv[okm] == 1).any() else None, 4),
                      "nonFallWeeksMeanP": r4(float(np.mean(pl_[yv[okm] == 0])) if (yv[okm] == 0).any() else None, 4)}
        # more labelled T3 diagnostics: episodes, constant and trailing forecasts, placebo ties, block length and seed, AUC
        yy, cc, dd_ = yv[okm], cv[okm], dl[okm]
        runs_ = []
        k_ = 0
        while k_ < len(yy):
            if yy[k_] == 1:
                s0 = k_
                while k_ + 1 < len(yy) and yy[k_ + 1] == 1:
                    k_ += 1
                runs_.append((s0, k_))
            k_ += 1
        merged_ = []
        for s0, e0 in runs_:
            if merged_ and s0 - merged_[-1][1] < LABEL_H:
                merged_[-1] = (merged_[-1][0], e0)
            else:
                merged_.append((s0, e0))
        b_zero = brier(np.zeros(len(yy)), yy)
        c4v = pd.Series(clim4, index=tvd).reindex(dd_).values
        ok4 = np.isfinite(c4v)
        dz = (cc - yy) ** 2 - (0.0 - yy) ** 2
        dbase = (cc - yy) ** 2 - (ybar - yy) ** 2
        grid = []
        for bl_ in (26, 52, 78):
            for sd_k in range(5):
                q_f = boot_mean(dloss, bl=bl_, seed=BASE_SEED + 7 + sd_k).get("q05")
                q_z = boot_mean(dz, bl=bl_, seed=BASE_SEED + 7 + sd_k).get("q05")
                grid.append({"blockWeeks": bl_, "seed": BASE_SEED + 7 + sd_k, "q05Fractal": r4(q_f, 5), "q05AlwaysZero": r4(q_z, 5)})
        az = np.array(allzero, bool)
        z_imp = bc - b_zero
        above_z = float(np.mean(allimp > z_imp + 1e-12)) if len(allimp) else None
        tie_z = float(np.mean(np.abs(allimp - z_imp) <= 1e-12)) if len(allimp) else None
        lv_ = S["pct"][tlab][okm]
        q05z26 = boot_mean(dz, bl=26, seed=BASE_SEED + 7).get("q05")
        auc_ = auc_score(pl_, yy)
        t3diag[sn].update({
            "status": "labelled diagnostics beside the plan's T3",
            "episodes": {"nPositiveWeeks": int(yy.sum()), "positiveRuns": [{"from": ds(dd_[s0]), "to": ds(dd_[e0]), "weeks": int(e0 - s0 + 1)} for s0, e0 in runs_],
                         "nRuns": len(runs_), "nEpisodesMergedUnder26Weeks": len(merged_),
                         "note": "the 26-week labels overlap, so positive weeks come in runs; the score rests on this many episodes"},
            "referenceForecasts": {"alwaysZero": {"brier": r4(b_zero, 5), "improvementOverClimatology": r4(z_imp, 5), "q05Block26": r4(q05z26, 5)},
                                   "periodBaseRateOracle": {"rate": r4(ybar, 4), "brier": r4(ybar * (1 - ybar), 5),
                                                            "improvementOverClimatology": r4(bc - ybar * (1 - ybar), 5),
                                                            "q05Block26": r4(boot_mean(dbase, bl=26, seed=BASE_SEED + 7).get("q05"), 5)},
                                   "trailing4yClimatology": {"nWeeks": int(ok4.sum()), "meanP": r4(float(np.mean(c4v[ok4])), 4) if ok4.any() else None,
                                                             "brier": r4(brier(c4v[ok4], yy[ok4]), 5) if ok4.any() else None,
                                                             "improvementOverClimatology": r4(brier(cc[ok4], yy[ok4]) - brier(c4v[ok4], yy[ok4]), 5) if ok4.any() else None,
                                                             "rule": f"mean of fall5_26w over the {TRAIL_CLIM_WEEKS} labelled weeks known at t"},
                                   "expandingClimatologyMeanP": r4(float(np.mean(cc)), 4)},
            "placeboTies": {"nPlacebos": int(len(allimp)), "shareWithPIdenticallyZero": r4(float(az.mean()), 4) if len(az) else None,
                            "shareTyingAlwaysZero": r4(tie_z, 4), "shareStrictlyAboveAlwaysZero": r4(above_z, 4),
                            "note": "a placebo parent whose family is never placed within h(t) of a waterfall start has p(t) = 0 and scores the "
                                    "always-zero improvement exactly; when most do, the placebo p95 is the always-zero bar"},
            "blockLengthAndSeed": grid,
            "aucOfP": r4(auc_, 4),
            "pAndLevel": {"meanLevelWhenPBelowHalf": r4(float(np.mean(lv_[pl_ < 0.5])), 2) if (pl_ < 0.5).any() else None,
                          "meanLevelWhenPAtLeastHalf": r4(float(np.mean(lv_[pl_ >= 0.5])), 2) if (pl_ >= 0.5).any() else None,
                          "minLevelWhenPIsZero": r4(float(np.min(lv_[pl_ == 0])), 2) if (pl_ == 0).any() else None,
                          "corrPLevel": r4(float(np.corrcoef(pl_, lv_)[0, 1]), 3) if np.std(pl_) > 0 and np.std(lv_) > 0 else None,
                          "levelSeries": f"{sn} weekly close"},
            "constantLowForecastNote": (f"in this window the expanding climatology averages {np.mean(cc):.3f} against a fall rate of {ybar:.3f}, so a "
                                        f"constant forecast of 0 improves on it by {z_imp:+.4f}; its block-bootstrap q05 is {q05z26:+.4f} at 26 "
                                        f"weeks with the module's seed and positive in {sum(1 for g_ in grid if (g_['q05AlwaysZero'] or 0) > 0)} "
                                        f"of {len(grid)} (block length, seed) cells (blockLengthAndSeed), and the period base rate beats the "
                                        f"climatology by {bc - ybar * (1 - ybar):+.4f}: constant low forecasts meet or nearly meet the "
                                        "climatology criterion here, so the placebo p95 is the bar that decides"
                                        if z_imp > 0 else "a constant forecast of 0 does not beat the climatology in this window")})
        if auc_ is not None and auc_ < 0.5:
            t3diag[sn]["aucNote"] = f"AUC {auc_:.3f} < 0.5: p(t) ranks the fall weeks below the non-fall weeks (anti-predictive)"
        t3out[sn] = {"weeks": [ds(dl[0]), ds(dl[-1])] if nlab else None, "nWeeks": int(okm.sum()), "baseRate": r4(np.mean(yv[okm]), 4),
                     "brierFractal": r4(bf, 5), "brierClimatology": r4(bc, 5), "improvementOverClimatology": r4(imp, 5),
                     "boot": {k: r4(v, 5) if isinstance(v, float) else v for k, v in bb.items()},
                     "fixed5": fx, "placebo": {"families": plc, "pooledP95": r4(p95_pool, 5), "nPooled": int(len(allimp)),
                                               "aboveEachFamilyP95": above_each},
                     "meanP": r4(np.nanmean(p_lab), 4), "pass": t3pass,
                     "rule": "Brier better than the expanding climatology with 26-week block-bootstrap q05 > 0 AND above the p95 of the "
                             f"placebo improvements ({a.wf_placebos} placebo parents per family (a)-(d), pooled; the plan's full run uses 40)",
                     "note": t3diag[sn]["constantLowForecastNote"], "diagnostics": t3diag[sn]}
        say(f"T3 {sn}: Brier fractal {bf:.4f} clim {bc:.4f} improvement {imp:+.4f} (q05 {bb.get('q05')}) placebo p95 {p95_pool:+.4f} "
            f"fixed5 {fx.get('brierFixed5')} -> pass {t3pass}")
        if sn == "TV":
            fo = np.array([[d[j].toordinal() if j >= 0 else np.nan for j in fr["place"][:, ti]] for ti in range(len(tl))], float)
            for ti, t in enumerate(tl):
                v = fo[ti]
                v = v[np.isfinite(v)]
                q = qdates(v) if len(v) else [None] * 3
                jp_t = int(fr["prim"]["jstar"][ti])
                y_t = yser.get(d[t], np.nan)
                wfp_rows.append({"date": ds(d[t]), "btcd": r4(S["pct"][t], 2), "primary": ds(d[jp_t]) if jp_t >= 0 else None,
                                 "p10": ord_to_date(q[0]), "p50": ord_to_date(q[1]), "p90": ord_to_date(q[2]),
                                 "localClock": r4(fr["prim"]["clock"][ti], 3), "h": r4(fr["prim"]["h"][ti], 2), "p": r4(p_all[ti], 4),
                                 "nPlaced": int(fr["nplaced"][ti]), "y": (None if not np.isfinite(y_t) else int(y_t)),
                                 "clim": r4(cser.get(d[t], np.nan), 4), "fixed5": r4(f5.get(ds(d[t]), np.nan), 4)})
    diagnostics["t3"] = t3diag
    # ---------------------------------------------------------------- labelled diagnostics: a series' family at today only
    def family_today(Sx):
        dd_ = Sx["dates"]
        Ax, Vx, _ = rule_anchors(dd_, Sx["pct"])
        Tx = len(dd_) - 1
        Px = (Ax["P0"], Ax["P1"], Ax["P2"], Ax["P3"])
        Cx = (Ax["C0"], Ax["C1"], Ax["C2"], Ax["C3"])
        c3f = int(np.searchsorted(dd_, pd.Timestamp(C3P_WINDOW[1]), side="right"))
        mem_x, prim_x = build_members(Px, Cx, Vx["P3'"], Vx["C2'"], Vx["C3'"], None, a.fast, real=True, c3p_from=c3f)
        pl_x, _, pt_x = walk_family({"x": Sx["x"], "pct": Sx["pct"]}, Sx["x"], mem_x, [Tx], primary_idx=prim_x)
        o_x = np.array([dd_[j].toordinal() if j >= 0 else np.nan for j in pl_x[:, 0]], float)
        ok_x = np.isfinite(o_x)
        q_x = qdates(o_x[ok_x])
        m_x = float(np.quantile(o_x[ok_x], 0.5, method="nearest")) if ok_x.any() else np.nan
        sh_x = float(np.mean(np.abs(o_x[ok_x] - m_x) <= 28)) if ok_x.any() else None
        shp_x = np.array([m["map"] == "shape" for m in mem_x]) & ok_x
        jpx = int(pl_x[prim_x, 0])
        end_x = Ax["C0"] - 1
        _, nxt_x = wf_next(Sx["pct"], Ax["P0"], end_x)
        wsx = int(nxt_x[jpx - Ax["P0"]]) if jpx >= 0 else -1
        f_after = int(nxt_x[Ax["P3"] - Ax["P0"]])
        segx = Sx["pct"][Ax["P0"]:Ax["C0"]]
        chx = Sx["pct"][Ax["C0"]:]
        fall16 = max(float(segx[k] - segx[k + 1:k + 1 + WF_WEEKS].min()) for k in range(len(segx) - 1))
        nw = None
        if wsx >= 0:
            hi = min(wsx + WF_WEEKS, end_x)
            lw = wsx + 1 + int(np.argmin(Sx["pct"][wsx + 1:hi + 1]))
            nw = {"start": ds(dd_[wsx]), "startLevel": r4(Sx["pct"][wsx], 2), "low": ds(dd_[lw]), "lowLevel": r4(Sx["pct"][lw], 2),
                  "parentWeeksToStart": int(wsx - jpx)}
        anch = {k: {"date": ds(dd_[Ax[k]]), "level": r4(Sx["pct"][Ax[k]], 2)} for k in ANCH}
        anch.update({k: {"date": ds(dd_[Vx[k]]), "level": r4(Sx["pct"][Vx[k]], 2)} for k in Vx})
        return {"anchors": anch, "todayLevel": r4(Sx["pct"][-1], 2),
                "parentRangePct": [r4(segx.min(), 2), r4(segx.max(), 2)], "childRangePct": [r4(chx.min(), 2), r4(chx.max(), 2)],
                "largestParentFallWithin16WeeksPts": r4(fall16, 2), "firstRuleWeekAfterP3": ds(dd_[f_after]) if f_after >= 0 else None,
                "primaryPlacedWeek": ds(dd_[jpx]) if jpx >= 0 else None, "nextWaterfall": nw,
                "family": {"n": len(mem_x), "nPlaced": int(ok_x.sum()), "p10": ord_to_date(q_x[0]), "p50": ord_to_date(q_x[1]),
                           "p90": ord_to_date(q_x[2]), "T1share": r4(sh_x, 4),
                           "T1verdict": ("robust" if sh_x >= 0.8 else "fragile") if sh_x is not None else None,
                           "shapeMembersP50": ord_to_date(qdates(o_x[shp_x], (0.5,))[0]) if shp_x.any() else None}}

    # TVc chained forward (labelled diagnostic; the plan's TVc is back-anchored, see series.TVc.construction)
    try:
        ft = family_today(make_series("TVcForward", wlogit=wk(L_fwd)))
        diagnostics["tvcForwardChained"] = {
            "status": "labelled diagnostic: TVc chained forward from TradingView's first day (2014-04-01) on the aligned step list; "
                      "the first build chained forward on CMC's raw labels; the plan's TVc (main results) is back-anchored",
            "logitOffsetVsTVAfterLastStep": r4(fwd_info["forwardChainOffsetLogit"], 4),
            "firstBuildOffsetRawLabels": r4(raw_info["forwardChainOffsetLogit"], 4),
            **ft,
            "why": (f"forward chaining puts TVc at {ft['parentRangePct'][0]}-{ft['parentRangePct'][1]} % in the parent and "
                    f"{ft['childRangePct'][0]}-{ft['childRangePct'][1]} % in the child (today {ft['todayLevel']} %); the parent's largest "
                    f"fall within 16 weeks is {ft['largestParentFallWithin16WeeksPts']} points, "
                    + ("so the 15-in-16 rule finds no waterfall in its parent: no read-out, p(t) = 0, and the shape members' open-part "
                       "normalisation runs to the parent end. The first build's TVc T1 'fragile' and p(t) = 0 were artefacts of this "
                       "chaining, not of the data; affine placements do not depend on it (a constant logit shift goes into the intercept)"
                       if ft["firstRuleWeekAfterP3"] is None else "and the rule still fires"))}
    except Exception as ex:  # diagnostics never block the results
        diagnostics["tvcForwardChained"] = {"error": f"{type(ex).__name__}: {ex}"}

    # CMC on a Sunday close (labelled diagnostic; the plan's CMC is the canonical file as built)
    try:
        fc = family_today(make_series("CMCsunday", wpct=wk(align_cmc_to_tv(raw["BTCD_CMC"]))))
        canon = {k: ds(S_all["CMC"]["dates"][A_all["CMC"][k]]) for k in ANCH}
        canon.update({k: ds(S_all["CMC"]["dates"][Vr_all["CMC"][k]]) for k in Vr_all["CMC"]})
        diagnostics["cmcSundayClose"] = {
            "status": "labelled diagnostic: CMC's labels moved back one day, so its W-SUN weekly close is the snapshot at Monday 00:02 "
                      "UTC (Sunday's close, as TradingView's); the plan's CMC rerun uses the canonical file as built (Saturday's close)",
            **fc,
            "canonicalAnchors": canon,
            "anchorsDifferingFromCanonical": [k for k in canon if fc["anchors"][k]["date"] != canon[k]],
            "canonicalPrimaryPlacedWeek": placement["primary"]["CMC"]["placedWeek"], "canonicalFamilyP50": placement["family"]["CMC"]["p50"]}
    except Exception as ex:  # diagnostics never block the results
        diagnostics["cmcSundayClose"] = {"error": f"{type(ex).__name__}: {ex}"}
    dif_ = diagnostics["cmcSundayClose"].get("anchorsDifferingFromCanonical")
    if dif_ is not None:
        series_out["CMC"]["source"] += (f"; on a Sunday close the anchors {dif_} move" if dif_ else
                                        "; a Sunday close moves no anchor")
    ftc_ = diagnostics["tvcForwardChained"]
    series_out["TVc"]["construction"]["note"] += (
        (f": parent {ftc_['parentRangePct'][0]}-{ftc_['parentRangePct'][1]} %, child {ftc_['childRangePct'][0]}-"
         f"{ftc_['childRangePct'][1]} %; "
         + ("the 15-in-16 rule finds no waterfall in its parent" if ftc_["firstRuleWeekAfterP3"] is None
            else "the 15-in-16 rule still fires in its parent")
         if "error" not in ftc_ else "") + " (diagnostics.tvcForwardChained)")

    # ---------------------------------------------------------------- base-rate diagnostic (labelled, not a verdict input)
    S, A = S_all["TV"], A_all["TV"]
    T = T_all["TV"]
    d = S["dates"]
    C = (A["C0"], A["C1"], A["C2"], A["C3"])
    Pp = (A["P0"], A["P1"], A["P2"], A["P3"])
    par = {"x": S["x"], "pct": S["pct"]}
    real_place = jp_tv
    real_cls = coarse_class(real_place, ep0)

    def near_wf(j, k=4):
        nx = nxt_tv[j - A["P0"]]
        return bool(nx >= 0 and nx - j <= k)
    base = {}
    for kind in ("walk", "block"):
        pl = np.array([j for j in syn_prim[kind] if j >= 0], np.int64)
        nearv = np.array([near_wf(j) for j in pl], bool)
        o = np.array([d[j].toordinal() for j in pl], float)
        q = qdates(o)
        vc = pd.Series([ds(d[j]) for j in pl], dtype=object).value_counts().head(5)
        cls = np.array([coarse_class(j, ep0) for j in pl], dtype=object)
        top_ = ep0["top"] if ep0 else -10
        base[kind] = {"n": int(len(pl)), "sharePlateau": r4(float(np.mean(cls == "plateau")), 4) if len(pl) else None,
                      "shareInsideDecline": r4(float(np.mean(cls == "decline")), 4) if len(pl) else None,
                      "shareLater": r4(float(np.mean(cls == "later")), 4) if len(pl) else None,
                      "shareAtTopOrWeekAfter": r4(float(np.mean((pl == top_) | (pl == top_ + 1))), 4) if len(pl) else None,
                      "shareWithin4WeeksBeforeNextWaterfall": r4(nearv.mean() if len(pl) else np.nan, 4),
                      "placedP10": ord_to_date(q[0]), "placedP50": ord_to_date(q[1]), "placedP90": ord_to_date(q[2]),
                      "mostCommonPlacedWeeks": {k: int(v) for k, v in vc.items()},
                      "shareSameWeekAsReal": r4(float(np.mean(pl == real_place)) if len(pl) else np.nan, 4)}
    cap_floor = A["P3"] + int(math.ceil((T - A["C3"] + 1) / PRIMARY_CAP)) - 1
    reach = np.arange(max(cap_floor, A["P3"] + 1), end_tv + 1)
    ucls = np.array([coarse_class(j, ep0) for j in reach], dtype=object)
    open_weeks = np.arange(A["P3"] + 1, end_tv + 1)
    crit_open = np.array([near_wf(j) for j in open_weeks], bool)
    uniform = {"nReachableWeeks": int(len(reach)), "reachableFrom": ds(d[reach[0]]) if len(reach) else None,
               "sharePlateau": r4(float(np.mean(ucls == "plateau")), 4), "shareInsideDecline": r4(float(np.mean(ucls == "decline")), 4),
               "shareLater": r4(float(np.mean(ucls == "later")), 4),
               "shareWithin4WeeksBeforeNextWaterfall": r4(float(np.mean([near_wf(j) for j in reach])), 4)}
    bpl, bde = base["block"]["sharePlateau"], base["block"]["shareInsideDecline"]
    wpl, wde = base["walk"]["sharePlateau"], base["walk"]["shareInsideDecline"]
    diagnostics["placementBaseRate"] = {
        "status": "labelled diagnostic beside the plan, not a verdict input",
        "design": f"{n_syn} logit random walks matched to the child's post-C3 weekly increment sd ({sd_inc:.4f}), starting at C3's level, "
                  f"{n_open} weeks, and {n_syn} 8-week block bootstraps of the child's own post-C3 increments; each child = the real "
                  "C0..C3 plus the synthetic open part, placed with the primary setting (TV parent, rule anchors, affine, cap 32); the "
                  "same children feed placement.T1.nullCalibration",
        "classes": {"plateau": f"before the first decline week ({ds(d[ep0['firstDecline']]) if ep0 and ep0['firstDecline'] is not None else None})",
                    "decline": f"the first decline week through the episode low ({ds(d[ep0['low']]) if ep0 else None})",
                    "later": "after the episode low", "rule": "readout.TV.waterfallCalendar.episodeRule"},
        "realPlacement": ds(d[real_place]) if real_place >= 0 else None, "realClass": real_cls,
        "realWithin4WeeksBeforeNextWaterfall": near_wf(real_place) if real_place >= 0 else None,
        "walks": base["walk"], "blockBootstraps": base["block"], "uniformOverReachableWeeks": uniform,
        "within4WeeksCriterion": {"nPlaceableWeeksTrue": int(crit_open.sum()), "nPlaceableWeeks": int(len(open_weeks)),
                                  "note": (f"the 15-in-16 flag runs for months, so 'within 4 parent weeks before the next waterfall' holds on "
                                           f"{int(crit_open.sum())} of the {len(open_weeks)} placeable weeks, from the plateau into the decline; "
                                           f"synthetic children meet it in {100 * (base['block']['shareWithin4WeeksBeforeNextWaterfall'] or 0):.0f}% "
                                           f"(block) and {100 * (base['walk']['shareWithin4WeeksBeforeNextWaterfall'] or 0):.0f}% (walk), so it "
                                           "carries little information (kept for continuity; the class shares above replace it)")},
        "capFloor": {"week": ds(d[cap_floor]), "rule": f"with {T - A['C3'] + 1} child weeks C3..today and at most {PRIMARY_CAP} child weeks on one "
                                                       f"parent week, the open-end placement cannot come earlier than P3 + {cap_floor - A['P3']} weeks"},
        "verdictOnMethod": (f"block bootstraps of the child's own increments land on the plateau in {100 * bpl:.0f}% and inside the decline in "
                            f"{100 * bde:.0f}%; matched walks {100 * wpl:.0f}% / {100 * wde:.0f}%; a uniform placement over the reachable weeks "
                            f"{100 * uniform['sharePlateau']:.0f}% / {100 * uniform['shareInsideDecline']:.0f}%. The real placement ({real_cls}) "
                            + ("is the typical outcome for children with the child's own increments: it reflects the child's level against the "
                               "mapped parent (placement.levelLookup), not evidence that the child follows the parent's shape"
                               if real_cls == "plateau" and bpl >= 0.5 else "is not the typical outcome for synthetic children")
                            if bpl is not None and wpl is not None else None)}
    say(f"base rate: plateau / decline shares, blocks {bpl} / {bde}, walks {wpl} / {wde}, uniform {uniform['sharePlateau']} / "
        f"{uniform['shareInsideDecline']} (real: {real_cls})")

    # ---------------------------------------------------------------- more diagnostics
    zz, piv = waterfalls(S["pct"][A["P0"]:A["C0"]])
    diagnostics["zigzagWaterfallsOnTVParent"] = {"rule": "study.py waterfalls(): zigzag 6-point reversals, falls >= 15 points, start when 15% of the depth is done",
                                                 "waterfalls": [{"start": ds(d[A["P0"] + s]), "trough": ds(d[A["P0"] + e]),
                                                                 "from": r4(S["pct"][A["P0"] + s], 2), "to": r4(S["pct"][A["P0"] + e], 2)} for s, e in zz]}
    i_top_c = int(d.get_loc(pd.Timestamp("2025-06-22")))
    i_top_p = int(d.get_loc(pd.Timestamp("2017-02-26")))
    diagnostics["clockToMatchTops"] = {"note": "the child's 2025-06-22 top matched to the parent's 2017-02-26 top since (P3, C3)",
                                       "childWeeksPerParentWeek": r4((i_top_c - A["C3"]) / (i_top_p - A["P3"]), 2)}
    shp = [i for i, m in enumerate(members_all["TV"]) if m["map"] == "shape" and m["aset"] == "primary" and m["cap"] == PRIMARY_CAP]
    if shp:
        j_ = int(fam_res["TV"]["place"][shp[0], -1])
        inf_ = fam_res["TV"]["info"][shp[0]]
        diagnostics["shapeVariantPrimary"] = {"placedWeek": ds(d[j_]) if j_ >= 0 else None,
                                              "openParentNormWindow": (f"({ds(d[A['P3']])}, {ds(d[inf_['normWeff']])}]" if inf_.get("feasible") else None),
                                              "ruleWaterfallStartAfterP3": ds(d[inf_["normW"]]) if inf_.get("feasible") else None,
                                              "note": "the parent's open part is z-scored over (P3, start of the parent's 2017 waterfall], the start by "
                                                      f"the 15-in-16 rule (at least {SHAPE_MIN_NORM} weeks); the plan wrote (P3, {SHAPE_LITERAL_END}] "
                                                      "expecting the rule's start there, but the rule fires earlier (see diagnostics.shapeLiteralWindow)"}
    # the plan's literal shape window (P3, 2017-03-05] on TV (labelled diagnostic)
    try:
        lit = int(d.get_loc(pd.Timestamp(SHAPE_LITERAL_END)))
        memT_ = members_all["TV"]
        ix_s = [i for i, m in enumerate(memT_) if m["map"] == "shape"]
        pl_lit, _, _ = walk_family(par, S["x"], [dict(memT_[i], normEndAbs=lit) for i in ix_s], [T])
        pl_mix = frT["place"][:, -1].copy()
        pl_mix[ix_s] = pl_lit[:, 0]
        o_m = np.array([d[j].toordinal() if j >= 0 else np.nan for j in pl_mix], float)
        ok_m = np.isfinite(o_m)
        q_m = qdates(o_m[ok_m])
        med_m = float(np.quantile(o_m[ok_m], 0.5, method="nearest"))
        sh_m = float(np.mean(np.abs(o_m[ok_m] - med_m) <= 28))
        diagnostics["shapeLiteralWindow"] = {
            "status": "labelled diagnostic: the TV family's shape members with the parent's open part z-scored over the plan's literal "
                      f"window (P3, {SHAPE_LITERAL_END}] instead of (P3, first rule week]",
            "window": f"({ds(d[A['P3']])}, {SHAPE_LITERAL_END}]",
            "asBuiltWindow": diagnostics.get("shapeVariantPrimary", {}).get("openParentNormWindow"),
            "shapeMembersPlacementsIdentical": bool(np.array_equal(pl_lit[:, 0], frT["place"][ix_s, -1])),
            "nShapeMembersPlacedDifferently": int(np.sum(pl_lit[:, 0] != frT["place"][ix_s, -1])),
            "membersPlacedDifferently": [{"member": memT_[i]["label"],
                                          "asBuilt": ds(d[frT["place"][i, -1]]) if frT["place"][i, -1] >= 0 else None,
                                          "literalWindow": ds(d[pl_lit[k, 0]]) if pl_lit[k, 0] >= 0 else None}
                                         for k, i in enumerate(ix_s) if pl_lit[k, 0] != frT["place"][i, -1]],
            "shapePrimaryByCap": {str(memT_[i]["cap"]): (ds(d[pl_lit[k, 0]]) if pl_lit[k, 0] >= 0 else None)
                                  for k, i in enumerate(ix_s) if memT_[i]["aset"] == "primary"},
            "shapePrimaryByCapAsBuilt": {str(memT_[i]["cap"]): (ds(d[frT["place"][i, -1]]) if frT["place"][i, -1] >= 0 else None)
                                         for i in ix_s if memT_[i]["aset"] == "primary"},
            "familyWithLiteralWindow": {"p10": ord_to_date(q_m[0]), "p50": ord_to_date(q_m[1]), "p90": ord_to_date(q_m[2]),
                                        "T1share": r4(sh_m, 4), "T1verdict": "robust" if sh_m >= 0.8 else "fragile"}}
    except Exception as ex:  # diagnostics never block the results
        diagnostics["shapeLiteralWindow"] = {"error": f"{type(ex).__name__}: {ex}"}
    snw = {}
    for sn in SERIES:
        ix = [i for i, m in enumerate(members_all[sn]) if m["map"] == "shape" and m["aset"] == "primary" and m["cap"] == PRIMARY_CAP]
        if not ix or not fam_res[sn]["info"][ix[0]].get("feasible"):
            snw[sn] = None
            continue
        inf_ = fam_res[sn]["info"][ix[0]]
        dd_ = S_all[sn]["dates"]
        j_ = int(fam_res[sn]["place"][ix[0], -1])
        snw[sn] = {"openParentNormWindow": f"({ds(dd_[A_all[sn]['P3']])}, {ds(dd_[inf_['normWeff']])}]",
                   "ruleWaterfallStartAfterP3": ds(dd_[inf_["normW"]]) if inf_.get("normFound") else None,
                   "fallback": None if inf_.get("normFound") else "no rule week after P3 inside the parent: the window runs to the parent end",
                   "shapePrimaryPlacedWeek": ds(dd_[j_]) if j_ >= 0 else None}
    diagnostics["shapeNormWindowBySeries"] = snw
    diagnostics["lambdaFixedPoint"] = {sn: {"primaryLambda": r4(fam_res[sn]["prim"]["lam"], 6), "converged": bool(fam_res[sn]["prim"]["conv"]),
                                            "membersNotConverged": int(sum(1 for i in fam_res[sn]["info"] if i.get("feasible") and not i.get("conv")))}
                                       for sn in SERIES}
    diagnostics["familyRuntimeSec"] = {sn: r4(fam_res[sn]["sec"], 1) for sn in SERIES}
    t3sec = [r["sec"] for r in t3_res if "sec" in r]
    diagnostics["t3PlaceboJobSec"] = {"n": len(t3sec), "mean": r4(np.mean(t3sec), 2) if t3sec else None}
    diagnostics["otherSeriesPrimaryToday"] = {sn: placement["primary"][sn]["placedWeek"] for sn in SERIES}

    # ---------------------------------------------------------------- leakage checks
    leak = {}
    fr = fam_res["TV"]
    tl = tlist_all["TV"]
    infoT = [dict(i, nxt=n) for i, n in zip(fr["info"], fr["nxt"])]
    rng2 = np.random.default_rng(3)
    samp = sorted(set(rng2.integers(0, len(tl), size=4).tolist() + [0]))
    k_act = int(np.searchsorted(tl, c3p_from["TV"]))  # first T3 week at which the C3' members are placed
    fam_samp = sorted(set(samp + [k for k in (k_act - 1, k_act) if 0 <= k < len(tl)]))
    checks = []
    prim_m = members_all["TV"][prim_all["TV"]]
    shp_m = members_all["TV"][shp[0]] if shp else None
    for ti in samp:
        t = int(tl[ti])
        ytr = S["x"][:t + 1].copy()
        pl1, _, pt1 = walk_family(par, ytr, [prim_m], [t], primary_idx=0)
        row = {"t": ds(d[t]), "primaryFull": int(fr["place"][prim_all["TV"], ti]), "primaryTruncated": int(pl1[0, 0]),
               "clockFull": r4(fr["prim"]["clock"][ti], 4), "clockTruncated": r4(pt1["clock"][0], 4)}
        if shp_m is not None:
            pl2, _, _ = walk_family(par, ytr, [shp_m], [t])
            row.update(shapeFull=int(fr["place"][shp[0], ti]), shapeTruncated=int(pl2[0, 0]))
        row["identical"] = bool(row["primaryFull"] == row["primaryTruncated"] and row.get("shapeFull") == row.get("shapeTruncated")
                                and (row["clockFull"] == row["clockTruncated"]))
        checks.append(row)

    def same_num(u, v):
        return bool((not np.isfinite(u) and not np.isfinite(v)) or (np.isfinite(u) and np.isfinite(v) and abs(u - v) < 1e-12))
    fam_checks = []
    for ti in fam_samp:  # the whole TV family with the child cut at t: p(t), h(t) and every placement (what T3 scores)
        t = int(tl[ti])
        ytr = S["x"][:t + 1].copy()
        plF, infF, ptF = walk_family(par, ytr, members_all["TV"], [t], primary_idx=prim_all["TV"])
        pF, nF = family_prob(plF, infF, ptF["h"])
        same_pl = bool(np.array_equal(plF[:, 0], fr["place"][:, ti]))
        same_h = same_num(float(ptF["h"][0]), float(fr["prim"]["h"][ti]))
        same_p = same_num(float(pF[0]), float(fr["p"][ti]))
        fam_checks.append({"t": ds(d[t]), "pFull": r4(fr["p"][ti], 6), "pTruncated": r4(pF[0], 6), "hFull": r4(fr["prim"]["h"][ti], 3),
                           "hTruncated": r4(ptF["h"][0], 3), "nPlacedTruncated": int(nF[0]), "allPlacementsIdentical": same_pl,
                           "identical": bool(same_pl and same_h and same_p)})
    plc_check = None
    try:  # one placebo walk-forward with the child after a cut replaced by noise: p must not change up to the cut
        # the TV placebo whose p(t) varies most (so a change after the cut can show), first in source order on ties
        cand_ = [(float(np.nanstd(np.asarray(r["p"], float))), k) for k, (fk_, (key_, _, _, _)) in enumerate(t3src["TV"])
                 for r in t3_res if r.get("series") == "TV" and r.get("key") == key_ and r.get("ok")]
        k_pick = max(cand_, key=lambda z: (z[0], -z[1]))[1] if cand_ else 0
        fk0, (key0, x0, w00, w10) = t3src["TV"][k_pick]
        r_pool = next(r for r in t3_res if r.get("series") == "TV" and r.get("key") == key0)
        tlab_tv = tlist_lab["TV"]
        kcut = len(tlab_tv) // 2
        tcut = int(tlab_tv[kcut])
        noisy = S["x"].copy()
        noisy[tcut + 1:] = S["x"][tcut] + np.cumsum(np.random.default_rng(BASE_SEED + 77).normal(0.0, 3 * sd_inc, len(noisy) - tcut - 1))
        r_noisy = _job_t3("TV", fk0, key0, x0, w00, w10, child_y=noisy)
        if r_pool.get("ok") and r_noisy.get("ok"):
            pa_, pb_ = np.asarray(r_pool["p"], float), np.asarray(r_noisy["p"], float)
            upto = all(same_num(float(u), float(v)) for u, v in zip(pa_[:kcut + 1], pb_[:kcut + 1]))
            after = any(not same_num(float(u), float(v)) for u, v in zip(pa_[kcut + 1:], pb_[kcut + 1:]))
            plc_check = {"placebo": key0, "family": FAM_LABEL[fk0], "cut": ds(d[tcut]), "pIdenticalUpToCut": bool(upto),
                         "pChangesAfterCut": bool(after), "identical": bool(upto)}
        else:
            plc_check = {"placebo": key0, "note": "placebo anchor search found no feasible set", "identical": True}
    except Exception as ex:  # a self-test never blocks the results
        plc_check = {"error": f"{type(ex).__name__}: {ex}", "identical": False}
    leak["truncationTest"] = {"rows": checks, "familyRows": fam_checks, "placeboNoiseTest": plc_check,
                              "allIdentical": bool(all(r["identical"] for r in checks) and all(r["identical"] for r in fam_checks)
                                                   and (plc_check or {}).get("identical", False)),
                              "what": "rows: the primary and shape-primary members' placement and the local clock at t, full forward pass vs "
                                      "a run on the child cut at t; familyRows: the whole TV family cut at t (every placement, h(t) and p(t), "
                                      "including the weeks either side of the C3' members' entry); placeboNoiseTest: one placebo walk-forward "
                                      "rerun with the child after a cut replaced by noise, p(t) compared up to the cut"}
    clim_ok = True
    for t in range(len(tvd)):
        s = t - LABEL_H
        if s >= 0 and np.isfinite(clim[t]):
            clim_ok &= bool(abs(clim[t] - np.nanmean(ylab[:s + 1])) < 1e-12)
    leak["climatology"] = {"pointInTime": clim_ok, "rule": "expanding mean of TV fall5_26w over weeks s <= t - 26 (labels known at t), from 2014-04"}
    # C3' timing: the closed-window rule against placing the C3' members from C3' + 1 (the first build)
    c3t = {"window": f"{C3P_WINDOW[0]}..{C3P_WINDOW[1]}", "c3PrimeWeek": ds(d[Vr_all["TV"]["C3'"]]),
           "membersPlacedFrom": ds(d[c3p_from["TV"]]) if c3p_from["TV"] < len(d) else None,
           "t3OverlapWeeks": [ds(d[tl[0]]), ds(d[c3p_from["TV"] - 1])] if c3p_from["TV"] > tl[0] else None,
           "nT3OverlapWeeks": int(max(0, c3p_from["TV"] - tl[0]))}
    try:
        ix_c3 = [i for i, m in enumerate(members_all["TV"]) if m["aset"] == "C3'"]
        pl_c3, inf_c3, _ = walk_family(par, S["x"], [dict(members_all["TV"][i], activeFrom=-1) for i in ix_c3], tl)
        place_alt = fr["place"].copy()
        info_alt = list(infoT)
        for k, i in enumerate(ix_c3):
            place_alt[i] = pl_c3[k]
            info_alt[i] = inf_c3[k]
        p_alt, _ = family_prob(place_alt, info_alt, fr["prim"]["h"])
        nl = len(tlist_lab["TV"])
        yv_ = yser.reindex(d[tlist_lab["TV"]]).values
        ok_ = np.isfinite(fr["p"][:nl]) & np.isfinite(p_alt[:nl]) & np.isfinite(yv_)
        c3t.update({"nMembers": len(ix_c3), "brierClosedWindowRule": r4(brier(fr["p"][:nl][ok_], yv_[ok_]), 5),
                    "brierIfPlacedFromC3PrimePlus1": r4(brier(p_alt[:nl][ok_], yv_[ok_]), 5),
                    "weeksWherePDiffers": [{"t": ds(d[tl[k]]), "pClosedWindow": r4(fr["p"][k], 4), "pFromC3PrimePlus1": r4(p_alt[k], 4)}
                                           for k in range(len(tl)) if not same_num(float(fr["p"][k]), float(p_alt[k]))]})
    except Exception as ex:  # diagnostics never block the results
        c3t["error"] = f"{type(ex).__name__}: {ex}"
    leak["c3PrimeTiming"] = c3t
    leak["anchors"] = ("hindsight by design: the anchors (and C2', P3', the jitters) are fixed from the full history; every primary anchor "
                       "window closes before T3 starts (C3's on 2021-06-30; T3 starts at C3 + 26 weeks). C3' (min weekly close in "
                       f"{C3P_WINDOW[0]}..{C3P_WINDOW[1]}) is the only anchor whose window overlaps T3 ({c3t['nT3OverlapWeeks']} weeks): "
                       f"its members are placed only from {c3t['membersPlacedFrom']}, once the window has closed, in the real families "
                       "and in every placebo walk-forward (measured effect in leakage.c3PrimeTiming)")
    leak["parentEnd"] = {"maxParentEndTV": ds(d[max(m["end"] for m in members_all["TV"])]),
                         "rule": "every real member's parent ends at or before the primary C0 - 1 week (2017-12-03 on TV): a C0 jitter's "
                                 "parent ends at min(its own C0 - 1, the primary C0 - 1), so no parent contains a child week"}
    leak["openPart"] = ("at child week t only child data up to t enters the open part, the local clock (52 child weeks back along the "
                        "path ending at t) and the shape variant's child normalisation (C3, t]; the anchored part uses child weeks <= C3 < t")
    leak["fixed5"] = {"sources": f5src, "note": "fixed5 probabilities read from the out-of-sample files only; compared on common weeks",
                      "selection": "walk-forward fits with a 26-week label lag, but the signal set was selected post hoc over refits "
                                   "through 2026 (round 8 note), so fixed5's Brier is an optimistic benchmark; it is a reported comparator, "
                                   "not in the T3 pass rule"}
    leak["t2Search"] = "the T2 anchor search scores only the anchored part (child C0..C3); the open part never enters the search"

    # ---------------------------------------------------------------- verdicts
    verdicts = {"placement": placement["T1"]["verdict"], "shape": "supported" if t2out["TV"]["pass"] else "not supported",
                "forecast": "supported" if t3out["TV"]["pass"] else "not supported",
                "placementTodayBySeries": {sn: placement["primary"][sn]["placedWeek"] for sn in SERIES},
                "familyP50BySeries": {sn: placement["family"][sn]["p50"] for sn in SERIES},
                "shapeFamilyPercentiles": {fk: t2out["TV"]["families"][fk].get("realPercentile") for fk in FAM_KEYS},
                "forecastBrier": {"fractal": t3out["TV"]["brierFractal"], "climatology": t3out["TV"]["brierClimatology"],
                                  "fixed5CommonWeeks": t3out["TV"]["fixed5"].get("brierFixed5"),
                                  "fractalCommonWeeks": t3out["TV"]["fixed5"].get("brierFractal")},
                "reruns": {sn: {"T1": placement["T1byRerun"][sn]["verdict"], "T2pass": t2out[sn]["pass"], "T3pass": t3out[sn]["pass"]} for sn in ("TVc", "CMC")},
                "verdictSeries": "TV", "basis": "T1 -> placement, T2 -> shape, T3 -> forecast; TVc and CMC are reported beside and never rescue a TV fail"}
    ncal = placement["T1"]["nullCalibration"]["byNull"]
    verdicts["placementDiagnostics"] = {
        "status": "labelled diagnostics beside the plan's T1 verdict; the verdict above is the plan's, unchanged",
        "verdictCountsPlacedMembersOnly": True,
        "shareAllMembers": placement["T1"]["diagnostics"]["shareCountingInfeasibleAsMisses"],
        "shareAllMembersReading": f"{placement['T1']['diagnostics']['verdictCountingInfeasibleAsMisses']} under the plain reading (infeasible "
                                  "members counted as misses)",
        "nullPassShare": {"blockBootstrap": ncal["block"].get("passShare"), "matchedWalk": ncal["walk"].get("passShare")},
        "realSharePercentileAmongNull": {"blockBootstrap": ncal["block"].get("realSharePercentile"),
                                         "matchedWalk": ncal["walk"].get("realSharePercentile")},
        "placedWeekClass": readout["TV"].get("waterfallCalendar", {}).get("placedWeekClass"),
        "reading": placement["T1"]["nullCalibration"].get("reading"),
        "mechanism": placement["levelLookup"].get("reading")}
    verdicts["forecastDiagnostics"] = {"status": "labelled diagnostics beside the plan's T3 verdict",
                                       "aucOfP": t3out["TV"]["diagnostics"].get("aucOfP"),
                                       "nFallEpisodes": t3out["TV"]["diagnostics"]["episodes"]["nEpisodesMergedUnder26Weeks"],
                                       "alwaysZeroImprovementOverClimatology": t3out["TV"]["diagnostics"]["referenceForecasts"]["alwaysZero"]["improvementOverClimatology"],
                                       "note": t3out["TV"]["note"]}

    tests = {"T0": {"indexSteps": len(steps), "anchorsNearSteps": {sn: [r["anchor"] for r in near[sn] if r["nearStep"]] for sn in SERIES}},
             "T1": placement["T1"], "T2": t2out, "T3": t3out}
    # ---------------------------------------------------------------- charts and output
    files = []
    try:
        files = charts(a.out, S_all, A_all, Vr_all, steps, fam_res, readout, t2out, wfp_rows, ylab, f5)
    except Exception as ex:  # charts never block the results
        notes.append(f"chart error: {type(ex).__name__}: {ex}")
        say(f"chart error: {ex}")
    for sn in SERIES:  # trim: keep placebo values for the chart only in TV (all series keep summaries)
        if sn != "TV":
            for fk in FAM_KEYS:
                t2out[sn]["families"][fk].pop("values", None)
    try:
        plan_sha = hashlib.sha256(open(PLAN_FILE, "rb").read()).hexdigest()
    except Exception:
        plan_sha = None
    end_utc, end_est = utc_est(dt.datetime.now(dt.timezone.utc))
    ncb = placement["T1"]["nullCalibration"]["byNull"]
    notes += [
        "Anchors are the plan's rules on each series' weekly closes; P0/C0 use the 8 weeks before P1/C1; ties go to the earliest week.",
        "TVc compares TradingView's day d with CoinMarketCap's change over the same market day: CMC's row dated d is its 00:02 UTC "
        "snapshot (the close of TradingView's bar d-1), so its labels move back one day before the step rule (indexSteps.alignment). "
        f"TVc is back-anchored: TVc = TV on and after the last step day ({tvc_info['lastStepDay']}); the forward chain from 2014-04-01 is TVc "
        f"+ {tvc_info['forwardChainOffsetLogit']:.3f} logit and is a labelled diagnostic (diagnostics.tvcForwardChained), as is the first "
        f"build's step list on CMC's raw labels ({len(steps_raw)} days; diagnostics.indexStepsRawLabels).",
        (f"On the forward chain the TVc family reads T1 {ftc_['family']['T1verdict']} ({ftc_['family']['T1share']}) and the 15-in-16 rule "
         "finds no waterfall in its parent, so the first build's TVc 'fragile' and p(t) = 0 were a chaining artefact, not a property of "
         "the data (diagnostics.tvcForwardChained)"
         if "error" not in ftc_ and ftc_.get("family", {}).get("T1verdict") == "fragile" and ftc_.get("firstRuleWeekAfterP3") is None else
         "The forward-chained TVc is diagnostics.tvcForwardChained."),
        "CMC (the plan's canonical file, as built) closes its W-SUN week on Saturday (its Sunday 00:02 UTC snapshot); the Sunday-close "
        "version is diagnostics.cmcSundayClose.",
        "DTW cells: child week i matched to parent week j; moves child+1 / parent+1 / both; at most `cap` child weeks on one parent week; "
        "a parent-only step adds the penalty lambda; the path is forced through the four anchor cells (diagonal moves that would skip a "
        "corner are forbidden); lambda = median squared residual of the anchored part's path computed with that lambda (fixed point).",
        "The open end may place today anywhere in (P3, parent end]; the parent end is C0 - 1 week (2017-12-03 on TV); a C0 jitter's parent "
        "ends at min(its own C0 - 1, the primary C0 - 1), so no parent contains a child week.",
        "Family members with no feasible path (a cap too small for a segment) are reported and left out of the quantiles; T1's verdict "
        "counts placed members only, and the share counting them as misses is shown beside it (verdicts.placementDiagnostics).",
        (f"T1 under the null: {100 * ncb['block']['passShare']:.0f}% of block-bootstrap children and "
         f"{100 * ncb['walk']['passShare']:.0f}% of matched-walk children pass it (placement.T1.nullCalibration), so a robust T1 is "
         + ("the expected outcome under the null" if min(ncb["block"]["passShare"], ncb["walk"]["passShare"]) >= 0.5 else
            "common under the null" if max(ncb["block"]["passShare"], ncb["walk"]["passShare"]) >= 0.2 else "uncommon under the null")
         + "; the placement tracks the child's level against the mapped parent (placement.levelLookup, placement.positiveControls)."
         if ncb["block"].get("passShare") is not None and ncb["walk"].get("passShare") is not None else
         "T1 null calibration unavailable."),
        "T2 search: P1 among the 3 deepest local minima in the window's first 30 weeks, P0 = max of the 8 weeks before P1 (inside the "
        "window), P2 among the 3 highest local maxima within 30 weeks after P1, P3 = min of the 4 weeks after P2; lowest anchored cost wins.",
        "T2 surrogates (a)-(c) are built on the series' weekly logit 2014-04..parent end and cut at the parent's calendar positions; (b) is "
        "study.py block_shuffle (8-week blocks of increments, permuted); (d) every weekly start 2014-04..2016-04; (e) every window of the "
        "parent's length that ends by the parent end (no overlap with the child), spread evenly to the placebo count.",
        "T3: p(t) = share of the placed TV family members whose placed week is within h(t) = 26 / local clock(t) parent weeks before "
        "their next waterfall start (the first later week with a 15-point fall inside 16 weeks); members whose C3 is after t are not placed, "
        f"and the C3' members (window {C3P_WINDOW[0]}..{C3P_WINDOW[1]}) are placed only once the window has closed, in the real families "
        "and in every placebo walk-forward (leakage.c3PrimeTiming).",
        "T3 placebo walk-forwards search their anchors once (anchored part, child C0..C3) and then run the same family and walk-forward.",
        f"T3 pass needs the improvement strictly above the pooled placebo p95 ({4 * a.wf_placebos} parents, (a)-(d)); a placebo whose p(t) is 0 every "
        "week scores the always-zero improvement, so a real p(t) = 0 ties that p95 and does not pass.",
        "The shape variant z-scores the parent's open part over (P3, W], W = the first week after P3 from which the parent falls 15 "
        "points within 16 weeks (the plan's waterfall rule; at least 4 weeks after P3; the parent end when no week qualifies). This departs "
        f"from the plan's literal (P3, {SHAPE_LITERAL_END}] on TV: the plan named that date as the expected start of the parent's 2017 "
        "waterfall, but the rule fires weeks before the top, so the window as built is shorter; the rule is kept because it applies to every "
        "series and placebo parent, and the literal window's result is diagnostics.shapeLiteralWindow.",
        "The 15-in-16 flag runs for months on the TV parent, so 'the next waterfall start' is one week after any placement inside that run, "
        "including placements inside the decline; readout.<series>.waterfallCalendar classifies the placed week (plateau / decline / later).",
        f"Run {run_utc} / {run_est}; finished {end_utc} / {end_est}.",
    ]
    out = {
        "plan": {"file": "research/btcd_fractal/ROUND14_PLAN.md", "sha256": plan_sha, "preRegistered": "2026-11-02 20:36 UTC / 3:36 PM EST",
                 "module": "research/btcd_fractal/study14_july2016.py", "fast": bool(a.fast), "placebos": a.placebos, "wfPlacebos": a.wf_placebos,
                 "jitterOffsets": list(jitter_offsets(a.fast)), "familySizePerSeries": len(members_all["TV"]), "numba": HAVE_NUMBA},
        "runUTC": run_utc, "runEST": run_est,
        "dataLastDailyBar": ds(last_day), "todayWeek": ds(lastw),
        "series": series_out, "indexSteps": index_steps, "placement": placement, "readout": readout, "tests": tests,
        "walkForwardPath": wfp_rows, "verdicts": verdicts, "diagnostics": diagnostics, "leakage": leak,
        "multipleComparisons": {"tests": ["T1 placement robustness", "T2 shape evidence", "T3 forecast"], "verdictSeries": "TV",
                                "t2FamiliesNeeded": "4 of 5 (a)-(e), plus (f) worse than the real parent",
                                "reruns": "TVc and CMC are reported beside TV and never rescue a TV fail",
                                "crossRound": "round 14 in a sequence of studies on the same TradingView BTC.D history: rounds 1-7 and 11 tested "
                                              "fractal alignments of 2016-17 onto 2018-now, rounds 8-10, 12 and 13 other forecasters and patterns; "
                                              "Steven revised this mapping after seeing round 11's chart",
                                "forkingPaths": ["the T1 denominator (placed members for the verdict; all members in placement.T1.diagnostics)",
                                                 "the TVc construction (CMC alignment and chain anchor; indexSteps, diagnostics.tvcForwardChained)",
                                                 "how the waterfall start is read (the 15-in-16 rule fires weeks before the top; "
                                                 "readout.<series>.waterfallCalendar)",
                                                 "the shape variant's open-part normalisation window (diagnostics.shapeLiteralWindow)"],
                                "nTestResultsReported": "9 (3 series x 3 tests), plus labelled diagnostics",
                                "note": "three tests on one verdict series; no correction beyond the pre-registered thresholds. "
                                        + ("Neither evidence test (T2 shape, T3 forecast) passes, so no correction would change those verdicts; "
                                           "T1 is a robustness reading, not a test against chance (placement.T1.nullCalibration). "
                                           if not (t2out["TV"]["pass"] or t3out["TV"]["pass"]) else
                                           "An evidence test passes: read it against the cross-round multiplicity below. ")
                                        + "A future pass would need a correction across rounds and across the choices in forkingPaths"},
        "charts": [os.path.basename(f) for f in files],
        "runtimeSeconds": round(time.time() - t_start, 1),
        "notes": notes,
    }
    with open(os.path.join(a.out, "results.json"), "w") as fh:
        json.dump(clean(out), fh, indent=1, allow_nan=False)
    say(f"verdicts: placement {verdicts['placement']}, shape {verdicts['shape']}, forecast {verdicts['forecast']}; "
        f"today (TV primary) -> parent week {placement['primary']['TV']['placedWeek']}; runtime {time.time() - t_start:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
