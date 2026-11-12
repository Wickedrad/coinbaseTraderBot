"""OR-HM2 Part 4: structural chart patterns in the weighted curves (python/oracle/prereg/OR-HM2-part4.md; build plan
/mnt/project-files/direction-research/oracle-hm2/OR-HM2-part4-build.md). It changes no line of heat.py, heat_vocab.py,
heat_live.py, heat_xdata.py or heat_hm2.py.

  python3 -m oracle.heat_patterns coin  (heat_hm2's inputs) --out <dir> [--twin N] [--procs 4]   route B: HM2's base, then stage()
  python3 -m oracle.heat_patterns bench (heat_hm2's inputs) --out <dir> [--pairs 5000]           minutes per stage, instances, RSS
  python3 -m oracle.heat_patterns readings --csv <1m.csv> --out <dir> [--twin N]                  the readings, catalogue and meta only

Route A: heat_hm2.run_series calls stage(ctx, os.path.join(out, 'patterns'), procs, log) after HM2's meta.json is written,
only where HM2's re-measure ran (S = 1 or the finish job), never in a --part job.

What one series gets (a coin or a no-signal twin; the twin's own bars):
  swing points  the confirmed-pivot ATR zigzag on 5 / 15 / 60 / 240-minute bars (heat.resample of the engine's tick-unit
                bars) at r = 2, 4, 8 ATR (12 frames z2 / z4 / z8). A pivot exists from its CONFIRMATION bar; the running
                extreme of the current leg is the provisional pivot. ATR = the plain mean of the true ranges of the 100
                bars before the bar, summed in a fixed order (exact on tick units).
  patterns      the 26 of the design (HS ... ROUNDTOP) plus STRUCT and BOS / CHoCH, tracked bar by bar: forming, formed,
                break up / down (textbook and wrong-way), retest, failure, target, half target; near misses (one check
                failed) are kept in the catalogue only. Each break carries p_rw = d_inv / (d_inv + d_tgt), the random
                walk's chance of the target before the invalidation, and tbi (minute closes, both barriers).
  kernel        LMW's ten patterns and Savin's HS / IHS on rolling 72-bar windows (Rink's intraday form: extrema end at
                bar 60, formed at the window's last bar) on 15 / 60 / 240 minutes (frame K): the causal check frame.
  readings      engine dicts (family 'chart'): {k}m:CHART.{frame}.{P} (events, 'every'), .{P}.state, .STRUCT, .BOS, .ANY,
                .BIAS and the nine parameters .p.<name>; -1 where stale and in the first 250 bars. 885 per series; the
                54 compact ones (compact()) go to the pair scan.
  stage         singles (kind chart / chart_held), shape_lift, parameter curves, anatomy, losers, the chart pair scan on
                HM2's kernel, re-measure, the catalogue, meta (schema oracle-heat-chart-1).
  live          levels_at(window, live_meta): the same code on the last 3,000 bars of each timeframe.
Coin minutes 2020-01-01 to 2025-12-31 only (heat.load_minutes refuses a later minute). NEVER DOGE.
"""
import argparse
import gzip
import hashlib
import json
import math
import os
import time

import numba as nb
import numpy as np
import pandas as pd

from oracle import heat
from oracle.common import MIN

# ------------------------------------------------------------------------------------------- constants (the design)
PAT_TFS = [5, 15, 60, 240]
Z_R = [2, 4, 8]
K_TFS = [15, 60, 240]
ATR_N = 100
WARM_BARS = 250
LEG_MIN_BARS = 2
L_MAX = {r: 20 * r * r for r in Z_R}               # 80, 320, 1280 bars
EXPIRE_LO, EXPIRE_HI = 10.0, 100.0                 # EXPIRE = min(100, max(10, span / 2)) from the formed bar
POST_LO, POST_HI = 20.0, 100.0                     # POST = min(100, max(20, span)) from the break
STATE_N = 20
PRE_MAX = 500
RETEST_BARS, RETEST_TOL = 20, 0.25
CONT_SHARE = 2                                     # k - 2 shared pivots (sets two pivots apart) = cont
# HS (Savin R6 / R7, Bulkowski, round 12)
HS_SH_LO, HS_SH_HI, HS_HEAD, HS_SDIFF, HS_NLRISE, HS_RATIO = 0.25, 0.7, 0.2, 0.5, 0.5, 3.0
# double and triple tops
DT_TOL, DT_SEP = 0.2, 8.0
TRI_PEAKS, TRI_VALLEYS, TRI_RATIO = 0.2, 0.4, 3.0
# lines (triangles, wedges, rectangle, broadening)
LN_TOUCH, LN_FLAT, LN_TILT, LN_CONV = 0.15, 0.15, 0.3, 0.15
# flags and pennants
FLAG_MIN, FLAG_FORMED, FLAG_MAX = 3, 5, 20
FLAG_POLE_R, FLAG_POLE_SPEED, FLAG_RETRACE = 2.0, 0.5, 0.5
FLAG_TILT_LO, FLAG_TILT_HI, FLAG_PAR, FLAG_TIGHT, PEN_SLOPE = -0.5, 0.1, 0.25, 0.5, 0.5
# cup and handle, rounding
CUP_RIM, CUP_MIN, CUP_R2, CUP_HANDLE = 0.2, 20.0, 0.6, 0.5
ROUND_R2, ROUND_MID, ROUND_MIN, ROUND_DEPTH = 0.8, 0.6, 20.0, 2.0
# ABCD and harmonics
ABCD_BC_LO, ABCD_BC_HI, ABCD_CD_LO, ABCD_CD_HI, ABCD_T_LO, ABCD_T_HI = 0.382, 0.886, 0.9, 1.1, 0.5, 2.0
HARM_TOL = 0.03
HARM_NAMES = ['gartley', 'bat', 'butterfly', 'crab']
HARM_B = np.array([[0.618 - HARM_TOL, 0.618 + HARM_TOL], [0.382 - HARM_TOL, 0.5 + HARM_TOL],
                   [0.786 - HARM_TOL, 0.786 + HARM_TOL], [0.382 - HARM_TOL, 0.618 + HARM_TOL]])
HARM_D = np.array([[0.786 - HARM_TOL, 0.786 + HARM_TOL], [0.886 - HARM_TOL, 0.886 + HARM_TOL],
                   [1.27 - HARM_TOL, 1.618 + HARM_TOL], [1.618 - HARM_TOL, 1.618 + HARM_TOL]])
# kernel frames (LMW, Savin-Weller-Zvingelis, Rink)
K_WIN, K_LAST, K_LAG = 72, 59, 12                  # window of 72 bars, last extremum at bar 60 (index 59), formed 12 bars later
K_GRID = np.geomspace(0.5, 20.0, 20)
K_FACTOR, K_SWZ = 0.3, 1.0
LMW_TOL, LMW_RECT, K_DTOP_SEP = 0.015, 0.0075, 10
SWZ_SH, SWZ_TR, SWZ_HEAD, SWZ_SPACING = 0.04, 0.04, 0.03, 1.2
K_REPEAT, K_REPEAT_TOL = 12, 2
K_CHUNK = 20_000
# levels
EV_LEVELS = ['none', 'formed', 'break up', 'break down', 'retest', 'failure', 'target']
ST_LEVELS = ['none', 'forming', 'formed', 'broken up', 'broken down', 'broken both', 'target reached', 'failed']
STRUCT_LEVELS = ['up', 'down', 'expanding', 'contracting']
BOS_LEVELS = ['none', 'BOS up', 'BOS down', 'CHoCH up', 'CHoCH down']
BIAS_LEVELS = ['none', 'up 1', 'up 2+', 'down 1', 'down 2+', 'mixed']
PARAMS = ['height', 'span', 'sym', 'slope', 'pre', 'bvol', 'bdist', 'tdist', 'age']
PARAM_Q = PARAMS[:7]
Q_LEVELS = ['q1', 'q2', 'q3', 'q4', 'q5']
TDIST_LEVELS, TDIST_EDGES = ['past target', '0-1', '1-2', '2-4', 'over 4'], [1.0, 2.0, 4.0]
AGE_LEVELS, AGE_EDGES = ['0', '1-2', '3-5', '6-10', '11-20'], [0, 2, 5, 10]
EV_PRIO = {2: 0, 3: 0, 5: 1, 6: 2, 4: 3, 1: 4}     # break > failure > target > retest > formed (lower first)
PATTERNS = ['HS', 'IHS', 'DTOP', 'DBOT', 'TRITOP', 'TRIBOT', 'ASCTRI', 'DESCTRI', 'SYMTRI', 'RISWEDGE', 'FALWEDGE', 'RECT',
            'BROADTOP', 'BROADBOT', 'CUP', 'INVCUP', 'ABCD.BULL', 'ABCD.BEAR', 'HARM.BULL', 'HARM.BEAR', 'BULLFLAG', 'BEARFLAG',
            'BULLPEN', 'BEARPEN', 'ROUNDBOT', 'ROUNDTOP']
TEXTBOOK = {'HS': -1, 'IHS': 1, 'DTOP': -1, 'DBOT': 1, 'TRITOP': -1, 'TRIBOT': 1, 'ASCTRI': 1, 'DESCTRI': -1, 'SYMTRI': 0,
            'RISWEDGE': -1, 'FALWEDGE': 1, 'RECT': 0, 'BROADTOP': -1, 'BROADBOT': 1, 'CUP': 1, 'INVCUP': -1, 'ABCD.BULL': 1,
            'ABCD.BEAR': -1, 'HARM.BULL': 1, 'HARM.BEAR': -1, 'BULLFLAG': 1, 'BEARFLAG': -1, 'BULLPEN': 1, 'BEARPEN': -1,
            'ROUNDBOT': 1, 'ROUNDTOP': -1}
KPATTERNS = ['LMW.HS', 'LMW.IHS', 'LMW.BTOP', 'LMW.BBOT', 'LMW.TTOP', 'LMW.TBOT', 'LMW.RTOP', 'LMW.RBOT', 'LMW.DTOP', 'LMW.DBOT',
             'LMW.HS.SWZ', 'LMW.IHS.SWZ']
KTEXTBOOK = {'LMW.HS': -1, 'LMW.IHS': 1, 'LMW.BTOP': -1, 'LMW.BBOT': 1, 'LMW.TTOP': -1, 'LMW.TBOT': 1, 'LMW.RTOP': -1, 'LMW.RBOT': 1,
             'LMW.DTOP': -1, 'LMW.DBOT': 1, 'LMW.HS.SWZ': -1, 'LMW.IHS.SWZ': 1}

# template ids. Pivot templates are written in the TOP orientation (the last pivot is a peak, the textbook break is a
# close below the trigger); the bottom is the same template on the mirrored bars (prices negated, highs and lows swapped).
T_HS, T_TRI, T_DT, T_CUP, T_ABCD, T_HARM0, T_LINE0 = 0, 1, 2, 3, 4, 5, 9
N_TPL = 16                                          # 0-15 pivot templates (HARM 5-8 = the variants, LINES 9-15 = the classes)
T_FLAG, T_PEN, T_ROUND = 16, 17, 18
T_K0 = 100                                          # kernel classes 100-111
TPL_K = np.array([5, 5, 3, 4, 4, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5], np.int64)
LINE_CLASSES = ['ASCTRI', 'DESCTRI', 'SYMTRI', 'RISWEDGE', 'FALWEDGE', 'RECT', 'BROAD']
TPL_NAME = {T_HS: ('HS', 'IHS'), T_TRI: ('TRITOP', 'TRIBOT'), T_DT: ('DTOP', 'DBOT'), T_CUP: ('INVCUP', 'CUP'),
            T_ABCD: ('ABCD.BEAR', 'ABCD.BULL'), T_FLAG: ('BULLFLAG', 'BEARFLAG'), T_PEN: ('BULLPEN', 'BEARPEN'),
            T_ROUND: ('ROUNDBOT', 'ROUNDTOP')}
for _v in range(4):
    TPL_NAME[T_HARM0 + _v] = ('HARM.BEAR', 'HARM.BULL')
for _c, (_a, _b) in enumerate([('ASCTRI', 'DESCTRI'), ('DESCTRI', 'ASCTRI'), ('SYMTRI', 'SYMTRI'), ('RISWEDGE', 'FALWEDGE'),
                               ('FALWEDGE', 'RISWEDGE'), ('RECT', 'RECT'), ('BROADTOP', 'BROADBOT')]):
    TPL_NAME[T_LINE0 + _c] = (_a, _b)
CHECKS = {T_HS: ['shoulders_above_neckline', 'shoulder_mean', 'head_over_shoulders', 'shoulder_diff', 'neckline_rise', 'span_ratio',
                 'duration', 'size'],
          T_TRI: ['peak_range', 'valley_diff', 'spacing', 'duration', 'size'],
          T_DT: ['peak_diff', 'separation', 'duration', 'size'],
          T_CUP: ['rim_diff', 'cup_length', 'bottom_position', 'cup_fit', 'handle_depth', 'handle_half', 'handle_length', 'duration', 'size'],
          T_ABCD: ['bc', 'cd', 'time', 'duration', 'size']}
for _v in range(4):
    CHECKS[T_HARM0 + _v] = ['b', 'c', 'd', 'duration', 'size']
for _c in range(7):
    CHECKS[T_LINE0 + _c] = ['touch', 'band', 'converge', 'duration', 'size']
WHY = ['alive', 'stopped', 'overrun', 'lmax', 'expired', 'post', 'stale', 'failure', 'never', 'apex']
W_ALIVE, W_STOP, W_OVERRUN, W_LMAX, W_EXPIRE, W_POST, W_STALE, W_FAIL, W_NEVER, W_APEX = range(10)

# instance record columns (int I, float F)
(I_TID, I_J0, I_K, I_START, I_END, I_WHY, I_NEAR, I_FID, I_FORMED, I_BRK, I_DIR, I_RETEST, I_FAIL, I_TGT, I_HALF, I_LASTB,
 I_LASTC, I_CTRIG, I_BACK, I_FB, I_FT, I_BARE, I_RINK, I_VAR) = range(24)
NI = 24
(F_LASTP, F_MARGIN, F_DNV, F_DNS, F_UPV, F_UPS, F_LREF, F_HDN, F_HUP, F_FOVD, F_FOVU, F_APEX, F_EXP, F_POST, F_TRIG, F_TSLOPE,
 F_FAILV, F_TGTV, F_HALFV, F_PRW, F_CB, F_UPTB, F_DNTB, F_FP,
 F_HGT_E, F_SPAN_E, F_SYM_E, F_SLOPE_E, F_HGT_F, F_SPAN_F, F_SYM_F, F_SLOPE_F, F_HGT_B, F_SPAN_B, F_SYM_B, F_SLOPE_B,
 F_PRE_E, F_PRE_F, F_PRE_B, F_BVOL, F_BDIST, F_A_E, F_A_F, F_A_B) = range(44)
NF = 44
MOM = {'E': (F_HGT_E, F_SPAN_E, F_SYM_E, F_SLOPE_E, F_PRE_E, F_A_E), 'F': (F_HGT_F, F_SPAN_F, F_SYM_F, F_SLOPE_F, F_PRE_F, F_A_F),
       'B': (F_HGT_B, F_SPAN_B, F_SYM_B, F_SLOPE_B, F_PRE_B, F_A_B)}


def _refuse_doge(*xs):
    for x in xs:
        if x and 'DOGE' in str(x).upper():
            raise SystemExit('NEVER DOGE')


def _log_none(*a, **k):
    pass


# ------------------------------------------------------------------------------------------------------- bars, ATR
@nb.njit(cache=True)
def atr_prior(h, l, c, stale, n=ATR_N):
    """S(t): the SUM of the true ranges of the n bars before bar t, as a direct n-term sum in a fixed order (never a
    difference of cumulative sums, so a window and the full run add the same numbers; on tick units every term is a
    whole number and the sum is exact). NaN before bar n + 1 and on stale bars. a(t) = S(t) / n."""
    nb_ = len(c)
    tr = np.empty(nb_)
    if nb_ > 0:
        tr[0] = h[0] - l[0]
    for j in range(1, nb_):
        tr[j] = max(h[j], c[j - 1]) - min(l[j], c[j - 1])
    S = np.full(nb_, np.nan)
    for t in range(n + 1, nb_):
        if stale[t]:
            continue
        s = 0.0
        for j in range(t - n, t):
            s += tr[j]
        S[t] = s
    return S


def _stale_mask(gb: np.ndarray) -> np.ndarray:
    """The engine's rule (heat.build_readings): a bar holding a forward-filled minute and the STALE bars after it, and
    STALE_LONG[1] bars after a gap run longer than STALE_LONG[0] bars."""
    stale = pd.Series(gb.astype(np.float32)).rolling(heat.STALE + 1, min_periods=1).max().to_numpy() > 0
    run = pd.Series(gb.astype(np.int64)).groupby(np.cumsum(~gb)).cumsum().to_numpy()
    stale |= pd.Series((run > heat.STALE_LONG[0]).astype(np.float32)).rolling(heat.STALE_LONG[1] + 1, min_periods=1).max().to_numpy() > 0
    return stale


def units(m: dict, a_hi: int = None, step=None) -> dict:
    """The engine's tick-unit minutes: heat.tick_units(m, a_hi) (grid and step from split A's rows) when no step is
    given, else the stored step (heat_live._units: the live reader's rule)."""
    if step is None:
        return heat.tick_units(m, a_hi)
    from oracle import heat_live
    out = dict(m)
    out.update(heat_live._units({x: m[x] for x in ('o', 'h', 'l', 'c')}, step))
    st = float(step) if step else None
    on = lambda a, u: bool(np.abs(a / u - np.round(a / u)).max() <= 1e-4)
    for _ in range(6 if st else 0):                     # the unit heat_live._units settled on (a finer grid: / 10^j)
        if all(on(m[x], st) for x in ('o', 'h', 'l', 'c')):
            break
        st /= 10.0
    out['step'] = st
    return out


def frame_bars(mu: dict, k: int, s: int = 0, e: int = None) -> dict:
    """Bars s .. e-1 of timeframe k (UTC-midnight aligned, heat.resample) of tick-unit minutes mu, the engine's stale
    mask from the gaps of the bars from s - heat_live.STALE_BACK on, S (atr_prior), and each bar's minute row."""
    from oracle import heat_live
    nb_all = mu['n'] // k
    e = nb_all if e is None else min(int(e), nb_all)
    s = max(0, int(s))
    sub = {x: (None if mu.get(x) is None else mu[x][s * k:e * k]) for x in ('o', 'h', 'l', 'c', 'v', 'tb')}
    sub['n'] = (e - s) * k
    b = heat.resample(sub, k)
    g0 = max(0, s - heat_live.STALE_BACK)
    gb = mu['gap'][g0 * k:e * k].reshape(e - g0, k).any(1)
    stale = _stale_mask(gb)[s - g0:]
    h, l, c = (np.ascontiguousarray(b[x], np.float64) for x in ('h', 'l', 'c'))
    fb = {'k': int(k), 's': s, 'e': e, 'nb': e - s, 'o': np.asarray(b['o'], np.float64), 'h': h, 'l': l, 'c': c,
          'v': np.ascontiguousarray(b['v'], np.float64), 'stale': stale, 'step': mu.get('step'), 't0': mu['t0']}
    fb['S'] = atr_prior(h, l, c, stale)
    fb['row'] = (s + np.arange(e - s, dtype=np.int64)) * k + k - 1
    return fb


# ------------------------------------------------------------------------------------------------------------ zigzag
@nb.njit(cache=True)
def _zigzag(h, l, c, S, stale, r):
    """The confirmed-pivot zigzag (study12_hs._zigzag on highs and lows, threshold r x ATR). A peak is CONFIRMED at the
    first bar t whose close is at least r x a(t) below the running high: 100 (high - c) >= r S(t) (whole numbers on tick
    units). After a pivot at extreme bar e is confirmed at t, the new leg's running extreme starts from the bars e+1 .. t
    (c[t] when e = t): a trough is never placed at the low of the bar that made the peak. One pivot per bar at most.
    Starts undecided at the first bar with S known; a stale bar resets it (a new segment). Returns the pivots (extreme
    bar, price, type +1 peak / -1 trough, confirmation bar) and per bar: leg direction, running-extreme bar and price,
    pivots confirmed so far and the first pivot index of the bar's segment."""
    n = len(c)
    pb = np.empty(n, np.int64)
    pp = np.empty(n)
    pt = np.empty(n, np.int8)
    pc = np.empty(n, np.int64)
    d_bar = np.zeros(n, np.int8)
    xb_bar = np.full(n, -1, np.int64)
    xp_bar = np.full(n, np.nan)
    np_bar = np.zeros(n, np.int64)
    seg0 = np.zeros(n, np.int64)
    m = 0
    d = 0
    act = False
    hiB, loB = -1, -1
    hiP, loP = 0.0, 0.0
    s0 = 0
    for t in range(n):
        if stale[t] or not (S[t] == S[t]):
            act = False
            d = 0
            s0 = m
            np_bar[t] = m
            seg0[t] = s0
            continue
        thr = r * S[t]
        if not act:
            act = True
            d = 0
            hiB, hiP, loB, loP = t, h[t], t, l[t]
            s0 = m
        else:
            if d >= 0 and h[t] > hiP:
                hiB, hiP = t, h[t]
            if d <= 0 and l[t] < loP:
                loB, loP = t, l[t]
        if d == 0:
            if 100.0 * (c[t] - loP) >= thr:
                pb[m], pp[m], pt[m], pc[m] = loB, loP, -1, t
                m += 1
                d = 1
                if loB == t:
                    hiB, hiP = t, c[t]
                else:
                    hiB, hiP = loB + 1, h[loB + 1]
                    for j in range(loB + 2, t + 1):
                        if h[j] > hiP:
                            hiB, hiP = j, h[j]
            elif 100.0 * (hiP - c[t]) >= thr:
                pb[m], pp[m], pt[m], pc[m] = hiB, hiP, 1, t
                m += 1
                d = -1
                if hiB == t:
                    loB, loP = t, c[t]
                else:
                    loB, loP = hiB + 1, l[hiB + 1]
                    for j in range(hiB + 2, t + 1):
                        if l[j] < loP:
                            loB, loP = j, l[j]
        elif d == 1:
            if 100.0 * (hiP - c[t]) >= thr:
                pb[m], pp[m], pt[m], pc[m] = hiB, hiP, 1, t
                m += 1
                d = -1
                if hiB == t:
                    loB, loP = t, c[t]
                else:
                    loB, loP = hiB + 1, l[hiB + 1]
                    for j in range(hiB + 2, t + 1):
                        if l[j] < loP:
                            loB, loP = j, l[j]
        else:
            if 100.0 * (c[t] - loP) >= thr:
                pb[m], pp[m], pt[m], pc[m] = loB, loP, -1, t
                m += 1
                d = 1
                if loB == t:
                    hiB, hiP = t, c[t]
                else:
                    hiB, hiP = loB + 1, h[loB + 1]
                    for j in range(loB + 2, t + 1):
                        if h[j] > hiP:
                            hiB, hiP = j, h[j]
        d_bar[t] = d
        if d == 1:
            xb_bar[t], xp_bar[t] = hiB, hiP
        elif d == -1:
            xb_bar[t], xp_bar[t] = loB, loP
        np_bar[t] = m
        seg0[t] = s0
    return pb[:m].copy(), pp[:m].copy(), pt[:m].copy(), pc[:m].copy(), d_bar, xb_bar, xp_bar, np_bar, seg0


def zigzag(fb: dict, r: float) -> dict:
    pb, pp, pt, pc, d, xb, xp, npb, seg0 = _zigzag(fb['h'], fb['l'], fb['c'], fb['S'], fb['stale'], float(r))
    return {'r': r, 'pb': pb, 'pp': pp, 'pt': pt, 'pc': pc, 'd': d, 'xb': xb, 'xp': xp, 'npb': npb, 'seg0': seg0}


@nb.njit(cache=True)
def _structure(c, stale, S, pp, pt, npb, seg0):
    """STRUCT (from the last two confirmed peaks and troughs of the segment: up / down / expanding / contracting, -1
    until two of each) and BOS (the first close above the last confirmed peak or below the last confirmed trough, each
    pivot broken once: CHoCH when against an up / down STRUCT, BOS otherwise)."""
    n = len(c)
    st = np.full(n, -1, np.int8)
    bos = np.full(n, -1, np.int8)
    p1 = p2 = t1 = t2 = 0.0
    nP = nT = 0
    lastP = lastT = -1
    brP = brT = False
    seen = 0
    cur = -1
    for t in range(n):
        if stale[t] or not (S[t] == S[t]):
            cur = -1
            continue
        if seg0[t] != cur:
            cur = seg0[t]
            seen = cur
            nP = nT = 0
            lastP = lastT = -1
        while seen < npb[t]:
            j = seen
            if pt[j] > 0:
                p1, p2 = p2, pp[j]
                nP += 1
                lastP = j
                brP = False
            else:
                t1, t2 = t2, pp[j]
                nT += 1
                lastT = j
                brT = False
            seen += 1
        s = -1
        if nP >= 2 and nT >= 2:
            hh = p2 > p1
            hl = t2 > t1
            if hh and hl:
                s = 0
            elif (not hh) and (not hl):
                s = 1
            elif hh:
                s = 2
            else:
                s = 3
        st[t] = s
        ev = 0
        if lastP >= 0 and not brP and c[t] > pp[lastP]:
            brP = True
            ev = 3 if s == 1 else 1
        elif lastT >= 0 and not brT and c[t] < pp[lastT]:
            brT = True
            ev = 4 if s == 0 else 2
        bos[t] = ev
    return st, bos


def structure(fb: dict, zz: dict) -> tuple:
    return _structure(fb['c'], fb['stale'], fb['S'], zz['pp'], zz['pt'], zz['npb'], zz['seg0'])


# ------------------------------------------------------------------------------------------------ pivot templates
@nb.njit(cache=True)
def _lsq3(x0, y0, x1, y1, x2, y2):
    """Least-squares line through three points: (intercept at x = 0, slope)."""
    mx = (x0 + x1 + x2) / 3.0
    my = (y0 + y1 + y2) / 3.0
    sxx = (x0 - mx) ** 2 + (x1 - mx) ** 2 + (x2 - mx) ** 2
    sxy = (x0 - mx) * (y0 - my) + (x1 - mx) * (y1 - my) + (x2 - mx) * (y2 - my)
    b = sxy / sxx if sxx > 0 else 0.0
    return my - b * mx, b


@nb.njit(cache=True)
def _band(cl, su, sl):
    """The line class's band as a margin (<= 0 inside). su, sl: each line's rise over the span / H0. Strict bounds get a
    tiny epsilon so that the seven bands never overlap."""
    E = 1e-12
    if cl == 0:                                    # ascending: flat top, rising lows
        return max(abs(su) - LN_FLAT, LN_TILT - sl)
    if cl == 1:                                    # descending: flat bottom, falling highs
        return max(abs(sl) - LN_FLAT, su + LN_TILT)
    if cl == 2:                                    # symmetrical
        return max(su + LN_CONV + E, LN_CONV - sl + E)
    if cl == 3:                                    # rising wedge
        return max(LN_CONV - su + E, su + LN_CONV - sl)
    if cl == 4:                                    # falling wedge
        return max(sl + LN_CONV + E, su - sl + LN_CONV)
    if cl == 5:                                    # rectangle
        return max(abs(su) - LN_FLAT, abs(sl) - LN_FLAT)
    return max(LN_CONV - su + E, sl + LN_CONV + E)  # broadening


@nb.njit(cache=True)
def _lines(P, B):
    """E1..E5 with E1 a peak: the upper line by least squares through E1, E3, E5, the lower through E2, E4. Returns
    (au, bu, al, bl, H0, su, sl, H5) with lines y = a + b x."""
    au, bu = _lsq3(B[0], P[0], B[2], P[2], B[4], P[4])
    bl = (P[3] - P[1]) / (B[3] - B[1])
    al = P[1] - bl * B[1]
    H0 = (au + bu * B[0]) - (al + bl * B[0])
    span = B[4] - B[0]
    su = bu * span / H0 if H0 > 0 else 0.0
    sl = bl * span / H0 if H0 > 0 else 0.0
    H5 = (au + bu * B[4]) - (al + bl * B[4])
    return au, bu, al, bl, H0, su, sl, H5


@nb.njit(cache=True)
def _nearest_class(P, B):
    au, bu, al, bl, H0, su, sl, H5 = _lines(P, B)
    best, bm = 0, 1e300
    for cl in range(7):
        mg = _band(cl, su, sl)
        if mg < bm:
            best, bm = cl, mg
    return best


@nb.njit(cache=True)
def _count(m, nm):
    """Checks failed (margin > 0), the first failed check and its margin."""
    nf = 0
    fid = -1
    mg = 0.0
    for j in range(nm):
        if m[j] > 0 or not (m[j] == m[j]):
            if fid < 0:
                fid = j
                mg = m[j]
            nf += 1
    return nf, fid, mg


@nb.njit(cache=True)
def _check(tid, P, B, k, a, r, lmax, ex, m):
    """Every check of template tid on pivots P (prices) at bars B (top orientation), with a = the bar's ATR. Margins in
    units of the pattern's height (or of the ratio bounded), > 0 = failed. Returns (checks failed (99 = no shape:
    height <= 0), first failed check, its margin, the pattern's height in price)."""
    dur = B[k - 1] - B[0]
    mdur = max(LEG_MIN_BARS * (k - 1) - dur, dur - lmax) / lmax
    if tid == T_HS:
        s = (P[3] - P[1]) / (B[3] - B[1])
        h = P[2] - (P[1] + s * (B[2] - B[1]))
        if not h > 0:
            return 99, -1, 1.0, h
        sh1 = P[0] - (P[1] + s * (B[0] - B[1]))
        sh2 = P[4] - (P[1] + s * (B[4] - B[1]))
        m[0] = -min(sh1, sh2) / h + 1e-12
        msh = 0.5 * (sh1 + sh2) / h
        m[1] = max(HS_SH_LO - msh, msh - HS_SH_HI)
        m[2] = HS_HEAD - (P[2] - max(P[0], P[4])) / h
        m[3] = abs(P[0] - P[4]) / h - HS_SDIFF
        m[4] = abs(s * (B[4] - B[0])) / h - HS_NLRISE
        ratio = (B[4] - B[2]) / max(B[2] - B[0], 1e-9)
        m[5] = max(1.0 / HS_RATIO - ratio, ratio - HS_RATIO)
        m[6] = mdur
        m[7] = (r * a - h) / h
        nf, fid, mg = _count(m, 8)
        return nf, fid, mg, h
    if tid == T_TRI:
        d = (P[0] + P[2] + P[4]) / 3.0 - 0.5 * (P[1] + P[3])
        if not d > 0:
            return 99, -1, 1.0, d
        m[0] = (max(P[0], max(P[2], P[4])) - min(P[0], min(P[2], P[4]))) / d - TRI_PEAKS
        m[1] = abs(P[1] - P[3]) / d - TRI_VALLEYS
        ratio = (B[4] - B[2]) / max(B[2] - B[0], 1e-9)
        m[2] = max(1.0 / TRI_RATIO - ratio, ratio - TRI_RATIO)
        m[3] = mdur
        m[4] = (r * a - d) / d
        nf, fid, mg = _count(m, 5)
        return nf, fid, mg, d
    if tid == T_DT:
        d = 0.5 * (P[0] + P[2]) - P[1]
        if not d > 0:
            return 99, -1, 1.0, d
        m[0] = abs(P[0] - P[2]) / d - DT_TOL
        m[1] = (DT_SEP - (B[2] - B[0])) / DT_SEP
        m[2] = mdur
        m[3] = (r * a - d) / d
        nf, fid, mg = _count(m, 4)
        return nf, fid, mg, d
    if tid == T_CUP:                               # top orientation = the inverted cup: R1 trough, B peak, R2 trough, HL peak
        D = P[1] - max(P[0], P[2])
        if not D > 0:
            return 99, -1, 1.0, D
        W = B[2] - B[0]
        m[0] = abs(P[0] - P[2]) / D - CUP_RIM
        m[1] = (CUP_MIN - W) / CUP_MIN
        m[2] = abs((B[1] - B[0]) / max(W, 1e-9) - 0.5) - 0.25
        m[3] = CUP_R2 - ex
        m[4] = (P[3] - P[2]) / D - CUP_HANDLE
        m[5] = (P[3] - (P[1] - 0.5 * D)) / D
        m[6] = ((B[3] - B[2]) - 0.5 * W) / max(W, 1e-9)
        m[7] = mdur
        m[8] = (r * a - D) / D
        nf, fid, mg = _count(m, 9)
        return nf, fid, mg, D
    if tid == T_ABCD:                              # top orientation = bearish: A trough, B peak, C trough, D peak
        AB = P[1] - P[0]
        if not AB > 0:
            return 99, -1, 1.0, AB
        bc = (P[1] - P[2]) / AB
        cd = (P[3] - P[2]) / AB
        tr = (B[3] - B[2]) / max(B[1] - B[0], 1e-9)
        m[0] = max(ABCD_BC_LO - bc, bc - ABCD_BC_HI)
        m[1] = max(ABCD_CD_LO - cd, cd - ABCD_CD_HI)
        m[2] = max(ABCD_T_LO - tr, tr - ABCD_T_HI)
        m[3] = mdur
        m[4] = (r * a - AB) / AB
        nf, fid, mg = _count(m, 5)
        return nf, fid, mg, AB
    if tid < T_LINE0:                              # harmonics, bearish: X peak, A trough, B peak, C trough, D peak
        v = tid - T_HARM0
        XA = P[0] - P[1]
        if not XA > 0 or not P[2] > P[1]:
            return 99, -1, 1.0, XA
        b = (P[2] - P[1]) / XA
        c = (P[2] - P[3]) / (P[2] - P[1])
        d = (P[4] - P[1]) / XA
        m[0] = max(HARM_B[v, 0] - b, b - HARM_B[v, 1])
        m[1] = max(ABCD_BC_LO - c, c - ABCD_BC_HI)
        m[2] = max(HARM_D[v, 0] - d, d - (HARM_D[v, 1] + HARM_TOL))
        m[3] = mdur
        m[4] = (r * a - XA) / XA
        nf, fid, mg = _count(m, 5)
        return nf, fid, mg, XA
    cl = tid - T_LINE0                             # lines, E1 a peak
    au, bu, al, bl, H0, su, sl, H5 = _lines(P, B)
    if not H0 > 0:
        return 99, -1, 1.0, H0
    tch = max(abs(P[0] - (au + bu * B[0])), max(abs(P[2] - (au + bu * B[2])), abs(P[4] - (au + bu * B[4]))))
    m[0] = tch / H0 - LN_TOUCH
    m[1] = _band(cl, su, sl)
    m[2] = -H5 / H0 + 1e-12                         # the lines do not meet before E5 (converging ones meet after it)
    m[3] = mdur
    m[4] = (r * a - H0) / H0
    nf, fid, mg = _count(m, 5)
    return nf, fid, mg, H0


@nb.njit(cache=True)
def _dn_level(tid, P, B, t):
    """The textbook trigger at bar t (top orientation: a close below it is the textbook break): (level, slope per bar,
    1 if a close triggers it). ABCD and the harmonics break when the zigzag confirms D in the PRZ: their level is the
    PRZ's near edge (used as the failure level of a wrong-way break) and is not a close trigger."""
    if tid == T_HS:
        s = (P[3] - P[1]) / (B[3] - B[1])
        if s > 0:
            return P[1] + s * (t - B[1]), s, 1
        return P[3], 0.0, 1
    if tid == T_TRI:
        return min(P[1], P[3]), 0.0, 1
    if tid == T_DT:
        return P[1], 0.0, 1
    if tid == T_CUP:
        return P[2], 0.0, 1
    if tid == T_ABCD:
        return P[2] + ABCD_CD_LO * (P[1] - P[0]), 0.0, 0
    if tid < T_LINE0:
        return P[1] + HARM_D[tid - T_HARM0, 0] * (P[0] - P[1]), 0.0, 0
    bl = (P[3] - P[1]) / (B[3] - B[1])
    return P[1] + bl * (t - B[1]), bl, 1


@nb.njit(cache=True)
def _up_conf(tid, P, B, t):
    """The invalidation once the last pivot is confirmed (a close above it is the wrong-way break): (level, slope)."""
    if tid == T_HS:
        return P[4], 0.0
    if tid == T_TRI:
        return max(P[0], max(P[2], P[4])), 0.0
    if tid == T_DT:
        return max(P[0], P[2]), 0.0
    if tid == T_CUP or tid == T_ABCD:
        return P[3], 0.0
    if tid < T_LINE0:
        return P[4], 0.0
    au, bu = _lsq3(B[0], P[0], B[2], P[2], B[4], P[4])
    return au + bu * t, bu


@nb.njit(cache=True)
def _heights(tid, P, B, F, i):
    """The measured moves after a break (HDN below the trigger, HUP above the invalidation) and the failure levels that
    are not the opposite level (FOVD after a textbook break, FOVU after a wrong-way one; NaN = the opposite level)."""
    F[i, F_FOVD] = np.nan
    F[i, F_FOVU] = np.nan
    if tid == T_HS:
        s = (P[3] - P[1]) / (B[3] - B[1])
        hd = P[2] - (P[1] + s * (B[2] - B[1]))
        hu = hd
    elif tid == T_TRI:
        hd = (P[0] + P[2] + P[4]) / 3.0 - 0.5 * (P[1] + P[3])
        hu = hd
    elif tid == T_DT:
        hd = 0.5 * (P[0] + P[2]) - P[1]
        hu = hd
    elif tid == T_CUP:
        hd = P[1] - max(P[0], P[2])
        hu = hd
        F[i, F_FOVD] = P[3]                        # after the break: beyond the handle (HL)
    elif tid == T_ABCD:
        hd = 0.618 * (P[3] - P[2])                 # D - 0.618 (D - C)
        hu = hd
        F[i, F_FOVD] = P[3]
    elif tid < T_LINE0:
        hd = 0.618 * (P[4] - P[1])                 # D - 0.618 (D - A)
        hu = hd
        F[i, F_FOVD] = P[4]
    else:
        au, bu, al, bl, H0, su, sl, H5 = _lines(P, B)
        hd = H5 if tid == T_LINE0 + 6 else H0      # broadening: the height at E5
        hu = hd
    F[i, F_HDN] = hd
    F[i, F_HUP] = hu


@nb.njit(cache=True)
def _sym(tid, P, B, hgt):
    """sym, 0 to 1 (the design's Readings, 5)."""
    if tid == T_HS:
        ratio = (B[4] - B[2]) / max(B[2] - B[0], 1e-9)
        return 0.5 * (max(0.0, 1.0 - abs(P[0] - P[4]) / (HS_SDIFF * hgt)) + max(0.0, 1.0 - abs(math.log(max(ratio, 1e-9))) / math.log(HS_RATIO)))
    if tid == T_TRI:
        return max(0.0, 1.0 - (max(P[0], max(P[2], P[4])) - min(P[0], min(P[2], P[4]))) / (TRI_PEAKS * hgt))
    if tid == T_DT:
        return max(0.0, 1.0 - abs(P[0] - P[2]) / (DT_TOL * hgt))
    if tid == T_CUP:
        W = max(B[2] - B[0], 1e-9)
        return 0.5 * (max(0.0, 1.0 - abs(P[0] - P[2]) / (CUP_RIM * hgt)) + max(0.0, 1.0 - abs((B[1] - B[0]) / W - 0.5) / 0.25))
    if tid == T_ABCD:
        return max(0.0, 1.0 - abs(math.log(max((B[3] - B[2]) / max(B[1] - B[0], 1e-9), 1e-9))) / math.log(2.0))
    if tid < T_LINE0:
        return max(0.0, 1.0 - abs(math.log(max((B[4] - B[3]) / max(B[2] - B[1], 1e-9), 1e-9))) / math.log(2.0))
    lo, hi = 1e300, 0.0
    for j in range(4):
        x = B[j + 1] - B[j]
        lo = min(lo, x)
        hi = max(hi, x)
    return lo / hi if hi > 0 else np.nan


@nb.njit(cache=True)
def _bound(tid, P, B, k, a, r, lmax, ex, t, plo, m, Q, Bq):
    """The farthest price the last pivot may reach at bar t with every check still passing (the invalidation while it
    is provisional): bisection upward from plo. NaN when plo itself does not pass at bar t."""
    for j in range(k):
        Q[j] = P[j]
        Bq[j] = B[j]
    Bq[k - 1] = t
    Q[k - 1] = plo
    nf, fid, mg, h = _check(tid, Q, Bq, k, a, r, lmax, ex, m)
    if nf != 0:
        return np.nan
    lo_p, hi_p = P[0], P[0]
    for j in range(k):
        lo_p = min(lo_p, P[j])
        hi_p = max(hi_p, P[j])
    step = max(hi_p - lo_p, abs(h), 1e-9)
    hi = plo + step
    found = False
    for _ in range(40):
        Q[k - 1] = hi
        nf, fid, mg, h2 = _check(tid, Q, Bq, k, a, r, lmax, ex, m)
        if nf != 0:
            found = True
            break
        hi = plo + 2.0 * (hi - plo)
    if not found:
        return hi
    lo = plo
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        Q[k - 1] = mid
        nf, fid, mg, h2 = _check(tid, Q, Bq, k, a, r, lmax, ex, m)
        if nf == 0:
            lo = mid
        else:
            hi = mid
    return lo


@nb.njit(cache=True)
def _quadfit(C, b0, b1, ref):
    """Least-squares quadratic of the closes b0 .. b1 (x = bar - b0, y = close - ref): (curvature, R^2, vertex x)."""
    n = 0.0
    sx = sx2 = sx3 = sx4 = sy = sxy = sx2y = syy = 0.0
    for b in range(b0, b1 + 1):
        x = float(b - b0)
        y = C[b] - ref
        x2 = x * x
        n += 1.0
        sx += x
        sx2 += x2
        sx3 += x2 * x
        sx4 += x2 * x2
        sy += y
        sxy += x * y
        sx2y += x2 * y
        syy += y * y
    return _quadsolve(n, sx, sx2, sx3, sx4, sy, sxy, sx2y, syy)


@nb.njit(cache=True)
def _quadsolve(n, sx, sx2, sx3, sx4, sy, sxy, sx2y, syy):
    det = n * (sx2 * sx4 - sx3 * sx3) - sx * (sx * sx4 - sx3 * sx2) + sx2 * (sx * sx3 - sx2 * sx2)
    if n < 3 or det == 0:
        return 0.0, 0.0, np.nan
    d0 = sy * (sx2 * sx4 - sx3 * sx3) - sx * (sxy * sx4 - sx3 * sx2y) + sx2 * (sxy * sx3 - sx2 * sx2y)
    d1 = n * (sxy * sx4 - sx2y * sx3) - sy * (sx * sx4 - sx3 * sx2) + sx2 * (sx * sx2y - sxy * sx2)
    d2 = n * (sx2 * sx2y - sx3 * sxy) - sx * (sx * sx2y - sxy * sx2) + sy * (sx * sx3 - sx2 * sx2)
    c0, c1, c2 = d0 / det, d1 / det, d2 / det
    sst = syy - sy * sy / n
    sse = syy - (c0 * sy + c1 * sxy + c2 * sx2y)
    r2 = 1.0 - sse / sst if sst > 0 else 0.0
    vx = -c1 / (2.0 * c2) if c2 != 0 else np.nan
    return c2, r2, vx


@nb.njit(cache=True)
def _cupfit(C, b0, b1, ref):
    """The cup's closes as a quadratic: R^2 when the curvature has the cup's sign (top orientation: an inverted U,
    curvature < 0), else -1."""
    c2, r2, vx = _quadfit(C, b0, b1, ref)
    return r2 if c2 < 0 else -1.0


# ------------------------------------------------------------------------------------------------------- the tracker
@nb.njit(cache=True)
def _new(I, F, i, tid, j0, k, t, P, B, ft):
    I[i, I_TID] = tid
    I[i, I_J0] = j0
    I[i, I_K] = k
    I[i, I_START] = t
    I[i, I_END] = -1
    I[i, I_WHY] = W_ALIVE
    I[i, I_NEAR] = 0
    I[i, I_BACK] = 0
    I[i, I_FB] = int(B[0])
    I[i, I_FT] = ft
    I[i, I_RINK] = 0
    I[i, I_CTRIG] = 1
    F[i, F_FP] = P[0]


@nb.njit(cache=True)
def _end(I, i, t, why):
    I[i, I_END] = t
    I[i, I_WHY] = why


@nb.njit(cache=True)
def _moment(F, i, w, hgt, span, sym, slope, a):
    """Record the instance's measurements as known at a moment: w 0 = its last forming bar, 1 = formed, 2 = break."""
    b = F_HGT_E + 4 * w
    F[i, b] = hgt
    F[i, b + 1] = span
    F[i, b + 2] = sym
    F[i, b + 3] = slope
    F[i, F_A_E + w] = a


@nb.njit(cache=True)
def _set_wait(I, F, i, tid, P, B, k, t):
    """The formed instance's two levels from bar t on (lines: value at t and slope), EXPIRE and the apex."""
    dn, ds, ct = _dn_level(tid, P, B, t)
    up, us = _up_conf(tid, P, B, t)
    F[i, F_DNV] = dn
    F[i, F_DNS] = ds
    F[i, F_UPV] = up
    F[i, F_UPS] = us
    F[i, F_LREF] = t
    I[i, I_CTRIG] = ct
    span = B[k - 1] - B[0]
    F[i, F_EXP] = min(EXPIRE_HI, max(EXPIRE_LO, span / 2.0))
    if tid >= T_LINE0 and tid <= T_LINE0 + 4:
        au, bu, al, bl, H0, su, sl, H5 = _lines(P, B)
        if bl > bu:
            F[i, F_APEX] = B[0] + H0 / (bl - bu)


@nb.njit(cache=True)
def _set_break(I, F, i, t, dirn, up, us, dn, ds, C, a):
    """The break at bar t (dirn -1: a close below the trigger, +1 above the invalidation): the broken level becomes the
    retest line, the opposite level (or the template's own) is frozen as the failure level, the measured move gives the
    target and half target, and p_rw = d_inv / (d_inv + d_tgt) from the break close. SPAN_B must be set."""
    I[i, I_BRK] = t
    I[i, I_DIR] = dirn
    F[i, F_UPTB] = up
    F[i, F_DNTB] = dn
    if dirn < 0:
        trig, ts = dn, ds
        tg, hf = dn - F[i, F_HDN], dn - 0.5 * F[i, F_HDN]
        fv = F[i, F_FOVD] if F[i, F_FOVD] == F[i, F_FOVD] else up
    else:
        trig, ts = up, us
        tg, hf = up + F[i, F_HUP], up + 0.5 * F[i, F_HUP]
        fv = F[i, F_FOVU] if F[i, F_FOVU] == F[i, F_FOVU] else dn
    F[i, F_TRIG] = trig
    F[i, F_TSLOPE] = ts
    F[i, F_TGTV] = tg
    F[i, F_HALFV] = hf
    F[i, F_FAILV] = fv
    cb = C[t]
    F[i, F_CB] = cb
    di = (fv - cb) * (-dirn)
    dt = (tg - cb) * dirn
    if not (di == di) or not (dt == dt):
        p = np.nan
    elif dt <= 0:
        p = 1.0
    elif di <= 0:
        p = 0.0
    elif di == np.inf:
        p = 1.0
    else:
        p = di / (di + dt)
    F[i, F_PRW] = p
    F[i, F_BDIST] = (cb - trig) * dirn / a if a > 0 else np.nan
    F[i, F_POST] = min(POST_HI, max(POST_LO, F[i, F_SPAN_B]))


@nb.njit(cache=True)
def _alive_step(I, F, i, t, H, Lo, C, S):
    """One bar of a formed (waiting for a break) or broken instance. Returns True when the instance ends."""
    a = S[t] / 100.0
    if I[i, I_BRK] < 0:
        tf = I[i, I_FORMED]
        if t <= tf:
            return False
        if t - tf > F[i, F_EXP]:
            _end(I, i, t, W_EXPIRE)
            return True
        if F[i, F_APEX] == F[i, F_APEX] and t >= F[i, F_APEX]:
            _end(I, i, t, W_APEX)
            return True
        dt = t - F[i, F_LREF]
        dn = F[i, F_DNV] + F[i, F_DNS] * dt
        up = F[i, F_UPV] + F[i, F_UPS] * dt
        dirn = 0
        if I[i, I_CTRIG] == 1 and C[t] < dn:
            dirn = -1
        elif C[t] > up:
            dirn = 1
        if dirn != 0:
            hg = F[i, F_HGT_F]
            F[i, F_HGT_B] = hg
            F[i, F_SPAN_B] = F[i, F_SPAN_F]
            F[i, F_SYM_B] = F[i, F_SYM_F]
            ls = F[i, F_DNS] if dirn < 0 else F[i, F_UPS]
            F[i, F_SLOPE_B] = ls * F[i, F_SPAN_F] / hg if hg > 0 else np.nan
            F[i, F_A_B] = a
            _set_break(I, F, i, t, dirn, up, F[i, F_UPS], dn, F[i, F_DNS], C, a)
        return False
    tb = I[i, I_BRK]
    if t <= tb:
        return False
    if t - tb > F[i, F_POST]:
        _end(I, i, t, W_POST)
        return True
    dirn = I[i, I_DIR]
    line = F[i, F_TRIG] + F[i, F_TSLOPE] * (t - tb)
    if dirn < 0:
        if C[t] > F[i, F_FAILV]:
            I[i, I_FAIL] = t
            _end(I, i, t, W_FAIL)
            return True
        if I[i, I_TGT] < 0 and Lo[t] <= F[i, F_TGTV]:
            I[i, I_TGT] = t
        if I[i, I_HALF] < 0 and Lo[t] <= F[i, F_HALFV]:
            I[i, I_HALF] = t
        if I[i, I_RETEST] < 0 and I[i, I_BACK] < 1 and t - tb <= RETEST_BARS:
            if C[t] >= line:
                I[i, I_BACK] = 1
            elif H[t] >= line - RETEST_TOL * a:
                I[i, I_RETEST] = t
    else:
        if C[t] < F[i, F_FAILV]:
            I[i, I_FAIL] = t
            _end(I, i, t, W_FAIL)
            return True
        if I[i, I_TGT] < 0 and H[t] >= F[i, F_TGTV]:
            I[i, I_TGT] = t
        if I[i, I_HALF] < 0 and H[t] >= F[i, F_HALFV]:
            I[i, I_HALF] = t
        if I[i, I_RETEST] < 0 and I[i, I_BACK] < 1 and t - tb <= RETEST_BARS:
            if C[t] <= line:
                I[i, I_BACK] = 1
            elif Lo[t] <= line + RETEST_TOL * a:
                I[i, I_RETEST] = t
    return False


@nb.njit(cache=True)
def _track(H, Lo, C, S, stale, pb, pp, pt, pc, npb, seg0, d_o, xb, xp, r, lmax, tpls):
    """The pivot templates tpls bar by bar on one orientation's bars and zigzag (prices already mirrored for the
    bottoms). At each bar the candidate of a template is its k - 1 last confirmed pivots plus the running extreme of the
    current (rising) leg; it is tracked from the bar its checks first pass ("forming"); it ends for good when they stop
    passing (an overrun of the farthest admissible price fires the wrong-way break only on a close beyond it); "formed"
    when the last pivot is confirmed before any break; the textbook break is the first close below the trigger at or
    after the forming start (the last pivot as it stands); precedence HS > TRITOP > DTOP on the same last pivot, bar by
    bar. A candidate that never passed and fails exactly one check at its confirmation is a near miss (catalogue only)."""
    nb_ = len(C)
    npv = len(pb)
    ntp = len(tpls)
    cap = ntp * (npv + 2) + 8
    I = np.full((cap, NI), -1, np.int64)
    F = np.full((cap, NF), np.nan)
    ni = 0
    s_j0 = np.full(ntp, -1, np.int64)
    s_st = np.zeros(ntp, np.int64)
    s_i = np.full(ntp, -1, np.int64)
    s_ex = np.zeros(ntp)
    s_P = np.zeros((ntp, 5))
    s_B = np.zeros((ntp, 5))
    alive = np.empty(cap, np.int64)
    nal = 0
    P = np.zeros(5)
    Bv = np.zeros(5)
    Q = np.zeros(5)
    Bq = np.zeros(5)
    m = np.zeros(12)
    raw = np.zeros(N_TPL, np.bool_)
    for t in range(nb_):
        if stale[t] or not (S[t] == S[t]):
            for q in range(nal):
                _end(I, alive[q], t, W_STALE)
            nal = 0
            for s in range(ntp):
                if s_st[s] == 1:
                    _end(I, s_i[s], t, W_STALE)
                s_j0[s] = -1
                s_st[s] = 0
                s_i[s] = -1
            continue
        a = S[t] / 100.0
        q = 0
        while q < nal:
            if _alive_step(I, F, alive[q], t, H, Lo, C, S):
                nal -= 1
                alive[q] = alive[nal]
            else:
                q += 1
        jn = npb[t]
        conf_now = jn > 0 and pc[jn - 1] == t and pt[jn - 1] > 0
        for tt in range(N_TPL):
            raw[tt] = False
        for s in range(ntp):
            tid = tpls[s]
            k = TPL_K[tid]
            if conf_now:
                j0 = jn - k
                confirmed = True
            elif d_o[t] == 1:
                j0 = jn - k + 1
                confirmed = False
            else:
                continue
            if j0 < 0 or j0 < seg0[t]:
                continue
            if j0 != s_j0[s]:
                s_j0[s] = j0
                s_st[s] = 0
                s_i[s] = -1
                if tid == T_CUP:
                    s_ex[s] = _cupfit(C, pb[j0], pb[j0 + 2], pp[j0])
            for u in range(k - 1):
                P[u] = pp[j0 + u]
                Bv[u] = pb[j0 + u]
            if confirmed:
                P[k - 1] = pp[jn - 1]
                Bv[k - 1] = pb[jn - 1]
            else:
                P[k - 1] = xp[t]
                Bv[k - 1] = xb[t]
            nf, fid, mg, hgt = _check(tid, P, Bv, k, a, r, lmax, s_ex[s], m)
            raw[tid] = nf == 0
            excl = (tid == T_TRI and raw[T_HS]) or (tid == T_DT and raw[T_TRI])
            ok = nf == 0 and not excl
            if s_st[s] == 2:                                            # (its checks still count for precedence above)
                continue
            if s_st[s] == 0:
                if (not confirmed) and t - Bv[0] > lmax:
                    s_st[s] = 2
                    continue
                if ok:
                    i = ni
                    ni += 1
                    _new(I, F, i, tid, j0, k, t, P, Bv, pt[j0])
                    s_st[s] = 1
                    s_i[s] = i
                    if tid >= T_ABCD and tid < T_LINE0:           # ABCD / harmonics: formed when D first enters the PRZ
                        I[i, I_FORMED] = t
                        _moment(F, i, 1, hgt, Bv[k - 1] - Bv[0], _sym(tid, P, Bv, hgt), 0.0, a)
                elif confirmed:
                    if nf == 1 and not excl and (tid < T_LINE0 or tid - T_LINE0 == _nearest_class(P, Bv)):
                        i = ni
                        ni += 1
                        _new(I, F, i, tid, j0, k, t, P, Bv, pt[j0])
                        I[i, I_NEAR] = 1
                        I[i, I_FID] = fid
                        F[i, F_MARGIN] = mg
                        I[i, I_FORMED] = t
                        I[i, I_LASTB] = int(Bv[k - 1])
                        I[i, I_LASTC] = t
                        F[i, F_LASTP] = P[k - 1]
                        _heights(tid, P, Bv, F, i)
                        _set_wait(I, F, i, tid, P, Bv, k, t)
                        sp = Bv[k - 1] - Bv[0]
                        _moment(F, i, 1, hgt, sp, _sym(tid, P, Bv, hgt), F[i, F_DNS] * sp / hgt if hgt > 0 else np.nan, a)
                        alive[nal] = i
                        nal += 1
                    s_st[s] = 2
                    continue
                else:
                    continue
            i = s_i[s]
            if not ok:
                if Bv[k - 1] == t and P[k - 1] > s_P[s, k - 1] and I[i, I_START] < t:
                    bd = _bound(tid, s_P[s], s_B[s], k, a, r, lmax, s_ex[s], t, s_P[s, k - 1], m, Q, Bq)
                    if bd == bd and P[k - 1] > bd:
                        if C[t] > bd:                                   # overrun with a close beyond: the wrong-way break
                            for u in range(k):
                                Q[u] = s_P[s, u]
                                Bq[u] = s_B[s, u]
                            dn, ds, ct = _dn_level(tid, Q, Bq, t)
                            _heights(tid, Q, Bq, F, i)
                            hg = F[i, F_HGT_E]
                            sp = Bq[k - 1] - Bq[0]
                            _moment(F, i, 2, hg, sp, _sym(tid, Q, Bq, hg), 0.0, a)
                            _set_break(I, F, i, t, 1, bd, 0.0, dn, ds, C, a)
                            alive[nal] = i
                            nal += 1
                            s_st[s] = 2
                            continue
                        _end(I, i, t, W_OVERRUN)
                        s_st[s] = 2
                        continue
                _end(I, i, t, W_STOP)
                s_st[s] = 2
                continue
            if (not confirmed) and t - Bv[0] > lmax:
                _end(I, i, t, W_LMAX)
                s_st[s] = 2
                continue
            for u in range(k):
                s_P[s, u] = P[u]
                s_B[s, u] = Bv[u]
            sp = Bv[k - 1] - Bv[0]
            sy = _sym(tid, P, Bv, hgt)
            dn, ds, ct = _dn_level(tid, P, Bv, t)
            I[i, I_BARE] = t
            _moment(F, i, 0, hgt, sp, sy, ds * sp / hgt, a)
            I[i, I_LASTB] = int(Bv[k - 1])
            F[i, F_LASTP] = P[k - 1]
            I[i, I_LASTC] = t if confirmed else -1
            if ct == 1 and C[t] < dn:                                   # the textbook break (last pivot as it stands)
                if confirmed:
                    up, us = _up_conf(tid, P, Bv, t)
                else:
                    up = _bound(tid, P, Bv, k, a, r, lmax, s_ex[s], t, P[k - 1], m, Q, Bq)
                    us = 0.0
                _heights(tid, P, Bv, F, i)
                _moment(F, i, 2, hgt, sp, sy, ds * sp / hgt, a)
                _set_break(I, F, i, t, -1, up, us, dn, ds, C, a)
                alive[nal] = i
                nal += 1
                s_st[s] = 2
                continue
            if confirmed:
                _heights(tid, P, Bv, F, i)
                if tid >= T_ABCD and tid < T_LINE0:                   # ABCD / harmonics: D confirmed inside the PRZ
                    _moment(F, i, 2, hgt, sp, sy, 0.0, a)
                    _set_break(I, F, i, t, -1, P[k - 1], 0.0, P[k - 1], 0.0, C, a)
                else:
                    I[i, I_FORMED] = t
                    _set_wait(I, F, i, tid, P, Bv, k, t)
                    _moment(F, i, 1, hgt, sp, sy, ds * sp / hgt, a)
                alive[nal] = i
                nal += 1
                s_st[s] = 2
                continue
    return I[:ni].copy(), F[:ni].copy()


@nb.njit(cache=True)
def _pre_bvol(I, F, H, Lo, V):
    """pre at each moment (the move into the first pivot from the far extreme of the min(2 x span, PRE_MAX) bars before
    it, / a) and bvol (the break bar's volume / the pattern's mean bar volume from its first pivot)."""
    n = I.shape[0]
    for i in range(n):
        fb = I[i, I_FB]
        if fb < 0:
            continue
        for w in range(3):
            span = F[i, F_SPAN_E + 4 * w]
            a = F[i, F_A_E + w]
            if not (span == span) or not (a == a) or a <= 0:
                continue
            L = int(min(2.0 * span, PRE_MAX))
            j0 = max(0, fb - L)
            if j0 >= fb:
                continue
            if I[i, I_FT] > 0:
                ext = Lo[j0]
                for j in range(j0 + 1, fb):
                    ext = min(ext, Lo[j])
                F[i, F_PRE_E + w] = (F[i, F_FP] - ext) / a
            else:
                ext = H[j0]
                for j in range(j0 + 1, fb):
                    ext = max(ext, H[j])
                F[i, F_PRE_E + w] = (ext - F[i, F_FP]) / a
        tb = I[i, I_BRK]
        if tb > fb:
            sv = 0.0
            for j in range(fb, tb):
                sv += V[j]
            mv = sv / (tb - fb)
            F[i, F_BVOL] = V[tb] / mv if mv > 0 else np.nan


@nb.njit(cache=True)
def _track_flags(H, Lo, C, S, stale, pb, pp, pt, pc, npb, seg0, d_o, xb, xp, r):
    """BULLFLAG / BULLPEN on one orientation's bars (the bear ones on the mirrored bars). Pole: the current zigzag leg
    from its confirmed trough L0 to its running (or just confirmed) high P0, at least 2 r a tall and rising 0.5 a a bar
    or more. Flag: the bars after P0 (3-20, no high above P0), retracing more than 0 and at most half the pole; lines by
    least squares of the flag bars' highs and lows, fitted on the bars before the current one (the break test) and on
    the bars up to it (the checks). Flag: both slopes in [-0.5, 0.1] x the pole's slope and within 0.25 of it of each
    other; pennant (takes precedence): upper < 0 < lower, each at most half the pole's slope; every flag bar within
    0.5 a of its line. Forming at 3-4 bars, formed at 5; a break is a close beyond a line; more than 20 bars ends it."""
    nb_ = len(C)
    cap = 2 * (nb_ // 3) + 16
    I = np.full((cap, NI), -1, np.int64)
    F = np.full((cap, NF), np.nan)
    ni = 0
    alive = np.empty(cap, np.int64)
    nal = 0
    st = np.zeros(2, np.int64)
    si = np.full(2, -1, np.int64)
    cP0 = -1
    cL0 = -1
    P0p = L0p = 0.0
    L0b = 0
    hb = np.zeros(FLAG_MAX + 2)
    lbv = np.zeros(FLAG_MAX + 2)
    fit = False
    au = bu = al = bl = 0.0
    nfl = 0
    minlow = maxhigh = 0.0
    for t in range(nb_):
        if stale[t] or not (S[t] == S[t]):
            for q in range(nal):
                _end(I, alive[q], t, W_STALE)
            nal = 0
            for s in range(2):
                if st[s] == 1:
                    _end(I, si[s], t, W_STALE)
                st[s] = 0
                si[s] = -1
            cP0 = -1
            cL0 = -1
            fit = False
            continue
        a = S[t] / 100.0
        q = 0
        while q < nal:
            if _alive_step(I, F, alive[q], t, H, Lo, C, S):
                nal -= 1
                alive[q] = alive[nal]
            else:
                q += 1
        # 1. the break of a live flag, against the lines fitted on the bars before this one
        if fit:
            x = float(t - cP0)
            U = au + bu * x
            Lw = al + bl * x
            for s in range(2):
                if st[s] != 1:
                    continue
                dirn = 1 if C[t] > U else (-1 if C[t] < Lw else 0)
                if dirn == 0:
                    continue
                i = si[s]
                pole = P0p - L0p
                F[i, F_FOVU] = minlow                       # after the up break: a close below the flag's low
                F[i, F_FOVD] = maxhigh
                F[i, F_HUP] = minlow + pole - U             # target: the flag's low + the pole
                F[i, F_HDN] = Lw - (maxhigh - pole)
                sp = float(t - L0b)
                ls = bu if dirn > 0 else bl
                _moment(F, i, 2, pole, sp, np.nan, ls * nfl / pole, a)
                _set_break(I, F, i, t, dirn, U, bu, Lw, bl, C, a)
                alive[nal] = i
                nal += 1
                st[s] = 2
        # 2. the pole at this bar
        jn = npb[t]
        nP0 = -1
        nL0 = -1
        if d_o[t] == 1 and jn - 1 >= seg0[t] and jn >= 1:
            nP0, nP0p, nL0 = xb[t], xp[t], jn - 1
        elif d_o[t] == -1 and jn - 2 >= seg0[t] and jn >= 2:
            nP0, nP0p, nL0 = pb[jn - 1], pp[jn - 1], jn - 2
        else:
            nP0p = 0.0
        if nP0 != cP0 or nL0 != cL0:
            for s in range(2):
                if st[s] == 1:
                    _end(I, si[s], t, W_OVERRUN)
                st[s] = 0
                si[s] = -1
            cP0, cL0 = nP0, nL0
            fit = False
            if cP0 < 0:
                continue
            P0p = nP0p
            L0p = pp[cL0]
            L0b = pb[cL0]
            nfl = t - cP0
            if nfl > FLAG_MAX:
                st[0] = 2
                st[1] = 2
                continue
            minlow, maxhigh = 1e300, -1e300
            for j in range(cP0 + 1, t + 1):
                hb[j - cP0] = H[j]
                lbv[j - cP0] = Lo[j]
                minlow = min(minlow, Lo[j])
                maxhigh = max(maxhigh, H[j])
        else:
            if cP0 < 0:
                continue
            nfl = t - cP0
            if nfl > FLAG_MAX:
                for s in range(2):
                    if st[s] == 1:
                        _end(I, si[s], t, W_EXPIRE)
                    st[s] = 2
                fit = False
                continue
            if nfl >= 1:
                hb[nfl] = H[t]
                lbv[nfl] = Lo[t]
                minlow = min(minlow, Lo[t])
                maxhigh = max(maxhigh, H[t])
        if st[0] == 2 and st[1] == 2:
            fit = False
            continue
        if nfl >= 1 and maxhigh > P0p:                       # a high above P0 inside the flag: no flag on this pole
            for s in range(2):
                if st[s] == 1:
                    _end(I, si[s], t, W_OVERRUN)
                st[s] = 2
            fit = False
            continue
        if nfl < 2:
            fit = False
            continue
        sx = sxx = sh = sxh = sl = sxl = 0.0
        for x in range(1, nfl + 1):
            fx = float(x)
            sx += fx
            sxx += fx * fx
            sh += hb[x]
            sxh += fx * hb[x]
            sl += lbv[x]
            sxl += fx * lbv[x]
        den = nfl * sxx - sx * sx
        bu = (nfl * sxh - sx * sh) / den
        au = (sh - bu * sx) / nfl
        bl = (nfl * sxl - sx * sl) / den
        al = (sl - bl * sx) / nfl
        fit = True
        if nfl < FLAG_MIN:
            continue
        pole = P0p - L0p
        pbars = max(float(cP0 - L0b), 1.0)
        ps = pole / pbars
        retr = P0p - minlow
        tight = 0.0
        for x in range(1, nfl + 1):
            tight = max(tight, max(abs(hb[x] - (au + bu * x)), abs(lbv[x] - (al + bl * x))))
        common = pole >= FLAG_POLE_R * r * a and ps >= FLAG_POLE_SPEED * a and retr > 0 and retr <= FLAG_RETRACE * pole and tight <= FLAG_TIGHT * a
        pen = bu < 0 and bl > 0 and -bu <= PEN_SLOPE * ps and bl <= PEN_SLOPE * ps
        flg = (bu >= FLAG_TILT_LO * ps and bu <= FLAG_TILT_HI * ps and bl >= FLAG_TILT_LO * ps and bl <= FLAG_TILT_HI * ps
               and abs(bu - bl) <= FLAG_PAR * ps)
        for s in range(2):
            ok = common and ((flg and not pen) if s == 0 else pen)
            sp = float(t - L0b)
            if st[s] == 0:
                if not ok:
                    continue
                i = ni
                ni += 1
                I[i, I_TID] = T_FLAG + s
                I[i, I_J0] = cL0
                I[i, I_K] = 2
                I[i, I_START] = t
                I[i, I_WHY] = W_ALIVE
                I[i, I_NEAR] = 0
                I[i, I_BACK] = 0
                I[i, I_FB] = L0b
                I[i, I_FT] = -1
                I[i, I_RINK] = 0
                F[i, F_FP] = L0p
                I[i, I_LASTB] = cP0
                F[i, F_LASTP] = P0p
                I[i, I_LASTC] = pc[jn - 1] if d_o[t] == -1 else -1
                st[s] = 1
                si[s] = i
            elif st[s] == 1:
                i = si[s]
                if not ok:
                    _end(I, i, t, W_STOP)
                    st[s] = 2
                    continue
            else:
                continue
            i = si[s]
            I[i, I_BARE] = t
            _moment(F, i, 0, pole, sp, np.nan, 0.5 * (bu + bl) * nfl / pole, a)
            if I[i, I_FORMED] < 0 and nfl >= FLAG_FORMED:
                I[i, I_FORMED] = t
                _moment(F, i, 1, pole, sp, np.nan, 0.5 * (bu + bl) * nfl / pole, a)
    return I[:ni].copy(), F[:ni].copy()


@nb.njit(cache=True)
def _track_round(H, Lo, C, S, stale, pb, pp, pt, pc, npb, seg0, d_o, xb, xp, r, lmax):
    """ROUNDBOT on one orientation's bars (ROUNDTOP on the mirrored bars): R1 a confirmed peak, B the low after it (the
    running low, or the trough just confirmed, with no confirmed peak since); the closes from R1 to the bar fit a
    quadratic with curvature > 0, R^2 >= 0.8, the vertex in the middle 60%, at least 20 bars, R1 - B >= 2 r a. Forming
    while B is provisional and the checks pass; formed when B is confirmed with every check passing. Break up: a close
    above R1; down: below B. Failure: back beyond the midpoint of R1 and B. Target: R1 + (R1 - B)."""
    nb_ = len(C)
    npv = len(pb)
    cap = npv + 8
    I = np.full((cap, NI), -1, np.int64)
    F = np.full((cap, NF), np.nan)
    ni = 0
    alive = np.empty(cap, np.int64)
    nal = 0
    cR1 = -1
    st = 0
    si = -1
    n = sx = sx2 = sx3 = sx4 = sy = sxy = sx2y = syy = 0.0
    R1b = 0
    R1p = 0.0
    for t in range(nb_):
        if stale[t] or not (S[t] == S[t]):
            for q in range(nal):
                _end(I, alive[q], t, W_STALE)
            nal = 0
            if st == 1:
                _end(I, si, t, W_STALE)
            cR1 = -1
            st = 0
            si = -1
            continue
        a = S[t] / 100.0
        q = 0
        while q < nal:
            if _alive_step(I, F, alive[q], t, H, Lo, C, S):
                nal -= 1
                alive[q] = alive[nal]
            else:
                q += 1
        jn = npb[t]
        conf_tr = jn > 0 and pc[jn - 1] == t and pt[jn - 1] < 0
        R1j = -1
        Bconf = False
        Bb = 0
        Bp = 0.0
        if conf_tr and jn - 2 >= seg0[t] and pt[jn - 2] > 0:
            R1j, Bb, Bp, Bconf = jn - 2, pb[jn - 1], pp[jn - 1], True
        elif d_o[t] == -1 and jn - 1 >= seg0[t] and jn >= 1 and pt[jn - 1] > 0:
            R1j, Bb, Bp = jn - 1, xb[t], xp[t]
        if R1j != cR1:
            cR1 = R1j
            st = 0
            si = -1
            if R1j < 0:
                continue
            R1b = pb[R1j]
            R1p = pp[R1j]
            if t - R1b > lmax:
                st = 2
                continue
            n = sx = sx2 = sx3 = sx4 = sy = sxy = sx2y = syy = 0.0
            for b in range(R1b, t + 1):
                x = float(b - R1b)
                y = C[b] - R1p
                n += 1.0
                sx += x
                sx2 += x * x
                sx3 += x * x * x
                sx4 += x * x * x * x
                sy += y
                sxy += x * y
                sx2y += x * x * y
                syy += y * y
        else:
            if R1j < 0:
                continue
            x = float(t - R1b)
            y = C[t] - R1p
            n += 1.0
            sx += x
            sx2 += x * x
            sx3 += x * x * x
            sx4 += x * x * x * x
            sy += y
            sxy += x * y
            sx2y += x * x * y
            syy += y * y
        if st == 2:
            continue
        span = float(t - R1b)
        if span > lmax:
            if st == 1:
                _end(I, si, t, W_LMAX)
            st = 2
            continue
        c2, r2, vx = _quadsolve(n, sx, sx2, sx3, sx4, sy, sxy, sx2y, syy)
        depth = R1p - Bp
        ok = (span >= ROUND_MIN and c2 > 0 and r2 >= ROUND_R2 and vx == vx and vx >= 0.5 * (1.0 - ROUND_MID) * span
              and vx <= 0.5 * (1.0 + ROUND_MID) * span and depth >= ROUND_DEPTH * r * a)
        if st == 0:
            if not ok:
                if Bconf:
                    st = 2
                continue
            i = ni
            ni += 1
            I[i, I_TID] = T_ROUND
            I[i, I_J0] = R1j
            I[i, I_K] = 2
            I[i, I_START] = t
            I[i, I_WHY] = W_ALIVE
            I[i, I_NEAR] = 0
            I[i, I_BACK] = 0
            I[i, I_FB] = R1b
            I[i, I_FT] = 1
            I[i, I_RINK] = 0
            I[i, I_CTRIG] = 1
            F[i, F_FP] = R1p
            st = 1
            si = i
        i = si
        if not ok:
            _end(I, i, t, W_STOP)
            st = 2
            continue
        sym = max(0.0, 1.0 - abs(vx - 0.5 * span) / (0.5 * ROUND_MID * span)) if span > 0 else np.nan
        I[i, I_BARE] = t
        I[i, I_LASTB] = Bb
        F[i, F_LASTP] = Bp
        I[i, I_LASTC] = t if Bconf else -1
        _moment(F, i, 0, depth, float(Bb - R1b), sym, 0.0, a)
        if Bconf:
            I[i, I_FORMED] = t
            _moment(F, i, 1, depth, float(Bb - R1b), sym, 0.0, a)
            F[i, F_DNV] = Bp
            F[i, F_DNS] = 0.0
            F[i, F_UPV] = R1p
            F[i, F_UPS] = 0.0
            F[i, F_LREF] = t
            F[i, F_HDN] = depth
            F[i, F_HUP] = depth
            F[i, F_FOVD] = 0.5 * (R1p + Bp)
            F[i, F_FOVU] = 0.5 * (R1p + Bp)
            F[i, F_EXP] = min(EXPIRE_HI, max(EXPIRE_LO, (Bb - R1b) / 2.0))
            alive[nal] = i
            nal += 1
            st = 2
    return I[:ni].copy(), F[:ni].copy()


# ------------------------------------------------------------------------------------------------- the kernel frames
_KM = {}


def kernel_mats() -> tuple:
    """Per grid bandwidth h (np.geomspace(0.5, 20, 20) bars): the leave-one-out Gaussian Nadaraya-Watson smoother of a
    72-bar window (zero diagonal, rows normalised), and the smoothers at 0.3 h (LMW / Rink) and 1.0 h (SWZ). Stored
    transposed ([g, j, i] = weight of bar j in output i) for the fixed-order loops."""
    if 'm' not in _KM:
        idx = np.arange(K_WIN, dtype=np.float64)
        D = idx[:, None] - idx[None, :]
        loo, sm, sw = (np.empty((len(K_GRID), K_WIN, K_WIN)) for _ in range(3))
        for g, h in enumerate(K_GRID):
            W = np.exp(-0.5 * (D / h) ** 2)
            np.fill_diagonal(W, 0.0)
            loo[g] = (W / W.sum(1, keepdims=True)).T
            W = np.exp(-0.5 * (D / (K_FACTOR * h)) ** 2)
            sm[g] = (W / W.sum(1, keepdims=True)).T
            W = np.exp(-0.5 * (D / (K_SWZ * h)) ** 2)
            sw[g] = (W / W.sum(1, keepdims=True)).T
        _KM['m'] = (np.ascontiguousarray(loo), np.ascontiguousarray(sm), np.ascontiguousarray(sw))
    return _KM['m']


@nb.njit(cache=True)
def _ksmooth(c, ends, loo, sm, sw):
    """For each window of 72 closes ending at bar ends[w] (centred on its mean): the cross-validated bandwidth index
    (leave-one-out squared error, the first minimum = the smaller bandwidth on a tie) and the two smooths. Every
    window's numbers come from the same fixed-order loops, so they do not depend on which other windows are computed."""
    m = len(ends)
    G = loo.shape[0]
    hs = np.empty(m, np.int64)
    Y = np.empty((m, K_WIN))
    Y2 = np.empty((m, K_WIN))
    x = np.empty(K_WIN)
    acc = np.empty(K_WIN)
    for w in range(m):
        t = ends[w]
        mu = 0.0
        for j in range(K_WIN):
            x[j] = c[t - K_WIN + 1 + j]
            mu += x[j]
        mu /= K_WIN
        for j in range(K_WIN):
            x[j] -= mu
        best = np.inf
        bj = 0
        for g in range(G):
            for i in range(K_WIN):
                acc[i] = 0.0
            for j in range(K_WIN):
                xj = x[j]
                for i in range(K_WIN):
                    acc[i] += loo[g, j, i] * xj
            cv = 0.0
            for i in range(K_WIN):
                d = x[i] - acc[i]
                cv += d * d
            if cv < best:
                best = cv
                bj = g
        hs[w] = bj
        for i in range(K_WIN):
            acc[i] = 0.0
        for j in range(K_WIN):
            xj = x[j]
            for i in range(K_WIN):
                acc[i] += sm[bj, j, i] * xj
        for i in range(K_WIN):
            Y[w, i] = acc[i]
            acc[i] = 0.0
        for j in range(K_WIN):
            xj = x[j]
            for i in range(K_WIN):
                acc[i] += sw[bj, j, i] * xj
        for i in range(K_WIN):
            Y2[w, i] = acc[i]
    return hs, Y, Y2


def kernel_smooth_blas(X: np.ndarray) -> tuple:
    """The same smooths as one BLAS product per bandwidth over a chunk of windows X (m, 72) (the design's vectorised
    form; the test checks it against _ksmooth and a direct per-window Nadaraya-Watson to 1e-9)."""
    loo, sm, sw = kernel_mats()
    Xc = X - X.mean(1, keepdims=True)
    cv = np.stack([((Xc - Xc @ loo[g]) ** 2).sum(1) for g in range(len(K_GRID))], 1)
    hs = cv.argmin(1)
    Y, Y2 = np.empty_like(Xc), np.empty_like(Xc)
    for g in np.unique(hs):
        sel = hs == g
        Y[sel], Y2[sel] = Xc[sel] @ sm[g], Xc[sel] @ sw[g]
    return hs, Y, Y2


@nb.njit(cache=True)
def _kext(y, H, Lo, t0, ei, et, erb, erp):
    """Extrema of one smooth y (a sign change of its slope), each mapped to the raw high (a maximum) or low (a minimum)
    within one bar. Returns their count."""
    ne = 0
    for s in range(1, K_WIN - 1):
        d0 = y[s] - y[s - 1]
        d1 = y[s + 1] - y[s]
        tp = 0
        if d0 > 0 and d1 < 0:
            tp = 1
        elif d0 < 0 and d1 > 0:
            tp = -1
        if tp == 0:
            continue
        lo, hi = max(0, s - 1), min(K_WIN - 1, s + 1)
        bb = lo
        if tp > 0:
            for j in range(lo + 1, hi + 1):
                if H[t0 + j] > H[t0 + bb]:
                    bb = j
            erp[ne] = H[t0 + bb]
        else:
            for j in range(lo + 1, hi + 1):
                if Lo[t0 + j] < Lo[t0 + bb]:
                    bb = j
            erp[ne] = Lo[t0 + bb]
        ei[ne] = t0 + s
        et[ne] = tp
        erb[ne] = t0 + bb
        ne += 1
    return ne


@nb.njit(cache=True)
def _near(a, b, tol):
    avg = 0.5 * (a + b)
    return abs(a - avg) <= tol * abs(avg) and abs(b - avg) <= tol * abs(avg)


@nb.njit(cache=True)
def _kdetect(Y, Y2, ends, H, Lo):
    """LMW's ten classes on the 0.3 x CV smooth and SWZ's HS / IHS on the 1.0 x CV smooth, for every window whose
    smooth has an extremum at bar 60 (index 59): the five extrema ending there (DTOP / DBOT: the window's first
    extremum and the highest later maximum / lowest later minimum, which must be the one at bar 60). Returns detections
    (window end, class, extremum positions, raw bars, raw prices, the valley / peak between a double top's tops)."""
    m = len(ends)
    cap = 4 * m + 16
    dt = np.empty(cap, np.int64)
    dc = np.empty(cap, np.int64)
    de = np.full((cap, 5), -1, np.int64)
    drb = np.full((cap, 5), -1, np.int64)
    drp = np.full((cap, 5), np.nan)
    dv = np.full(cap, np.nan)
    nd = 0
    ei = np.empty(K_WIN, np.int64)
    et = np.empty(K_WIN, np.int64)
    erb = np.empty(K_WIN, np.int64)
    erp = np.empty(K_WIN)
    for w in range(m):
        t = ends[w]
        t0 = t - K_WIN + 1
        for pass_ in range(2):
            y = Y[w] if pass_ == 0 else Y2[w]
            ne = _kext(y, H, Lo, t0, ei, et, erb, erp)
            q = -1
            for u in range(ne):
                if ei[u] == t0 + K_LAST:
                    q = u
            if q < 0:
                continue
            if pass_ == 0:
                # double top / bottom: the window's first extremum and the highest later max (lowest later min)
                if ne >= 2:
                    tp = et[0]
                    bu = -1
                    for u in range(1, ne):
                        if et[u] == tp and (bu < 0 or (tp > 0 and erp[u] > erp[bu]) or (tp < 0 and erp[u] < erp[bu])):
                            bu = u
                    if bu == q and _near(erp[0], erp[bu], LMW_TOL) and erb[bu] - erb[0] >= K_DTOP_SEP:
                        ext = Lo[erb[0]] if tp > 0 else H[erb[0]]
                        for j in range(erb[0] + 1, erb[bu]):
                            ext = min(ext, Lo[j]) if tp > 0 else max(ext, H[j])
                        dt[nd] = t
                        dc[nd] = 8 if tp > 0 else 9
                        de[nd, 0], de[nd, 1] = ei[0], ei[bu]
                        drb[nd, 0], drb[nd, 1] = erb[0], erb[bu]
                        drp[nd, 0], drp[nd, 1] = erp[0], erp[bu]
                        dv[nd] = ext
                        nd += 1
            if q < 4:
                continue
            E1, E2, E3, E4, E5 = erp[q - 4], erp[q - 3], erp[q - 2], erp[q - 1], erp[q]
            top = et[q - 4] > 0
            cls0 = nd
            if pass_ == 0:
                if top:
                    if E3 > E1 and E3 > E5 and _near(E1, E5, LMW_TOL) and _near(E2, E4, LMW_TOL):
                        dc[nd] = 0
                        nd += 1
                    if E1 < E3 and E3 < E5 and E2 > E4:
                        dc[nd] = 2
                        nd += 1
                    if E1 > E3 and E3 > E5 and E2 < E4:
                        dc[nd] = 4
                        nd += 1
                    av = (E1 + E3 + E5) / 3.0
                    bv = 0.5 * (E2 + E4)
                    if (abs(E1 - av) <= LMW_RECT * av and abs(E3 - av) <= LMW_RECT * av and abs(E5 - av) <= LMW_RECT * av
                            and abs(E2 - bv) <= LMW_RECT * bv and abs(E4 - bv) <= LMW_RECT * bv and min(E1, min(E3, E5)) > max(E2, E4)):
                        dc[nd] = 6
                        nd += 1
                else:
                    if E3 < E1 and E3 < E5 and _near(E1, E5, LMW_TOL) and _near(E2, E4, LMW_TOL):
                        dc[nd] = 1
                        nd += 1
                    if E1 > E3 and E3 > E5 and E2 < E4:
                        dc[nd] = 3
                        nd += 1
                    if E1 < E3 and E3 < E5 and E2 > E4:
                        dc[nd] = 5
                        nd += 1
                    av = 0.5 * (E2 + E4)
                    bv = (E1 + E3 + E5) / 3.0
                    if (abs(E2 - av) <= LMW_RECT * av and abs(E4 - av) <= LMW_RECT * av and abs(E1 - bv) <= LMW_RECT * bv
                            and abs(E3 - bv) <= LMW_RECT * bv and abs(E5 - bv) <= LMW_RECT * bv and min(E2, E4) > max(E1, max(E3, E5))):
                        dc[nd] = 7
                        nd += 1
            else:
                sp_hi, sp_sum = 0.0, 0.0
                for u in range(q - 4, q):
                    x = float(ei[u + 1] - ei[u])
                    sp_hi = max(sp_hi, x)
                    sp_sum += x
                r9 = sp_hi <= SWZ_SPACING * sp_sum / 4.0
                tm = 0.5 * (E2 + E4)
                if top and E3 > E1 and E3 > E5 and _near(E1, E5, SWZ_SH) and _near(E2, E4, SWZ_TR) and r9:
                    hd = E3 - tm
                    ms = 0.5 * ((E1 - E2) + (E5 - E4))
                    if hd > 0 and ms >= HS_SH_LO * hd and ms <= HS_SH_HI * hd and hd >= SWZ_HEAD * abs(tm):
                        dc[nd] = 10
                        nd += 1
                if (not top) and E3 < E1 and E3 < E5 and _near(E1, E5, SWZ_SH) and _near(E2, E4, SWZ_TR) and r9:
                    hd = tm - E3
                    ms = 0.5 * ((E2 - E1) + (E4 - E5))
                    if hd > 0 and ms >= HS_SH_LO * hd and ms <= HS_SH_HI * hd and hd >= SWZ_HEAD * abs(tm):
                        dc[nd] = 11
                        nd += 1
            for d in range(cls0, nd):
                dt[d] = t
                for u in range(5):
                    de[d, u] = ei[q - 4 + u]
                    drb[d, u] = erb[q - 4 + u]
                    drp[d, u] = erp[q - 4 + u]
    return dt[:nd].copy(), dc[:nd].copy(), de[:nd].copy(), drb[:nd].copy(), drp[:nd].copy(), dv[:nd].copy()


@nb.njit(cache=True)
def _kinstances(dt, dc, de, drb, drp, dv, H, Lo, C, S, stale):
    """Kernel detections -> instances: a class reported in the previous 12 bars (by any detection, reported or not, so the
    rule reads only the last 84 bars) with every extremum within 2 bars is the same instance. Formed at the window's
    last bar; a close beyond a level inside the 12-bar lag fires the break there (rink12 = 1); then the same post-break
    watch as the zigzag patterns."""
    nd = len(dt)
    cap = nd + 8
    I = np.full((cap, NI), -1, np.int64)
    F = np.full((cap, NF), np.nan)
    ni = 0
    nb_ = len(C)
    alive = np.empty(cap, np.int64)
    nal = 0
    d = 0
    for t in range(nb_):
        if stale[t] or not (S[t] == S[t]):
            for q in range(nal):
                _end(I, alive[q], t, W_STALE)
            nal = 0
            while d < nd and dt[d] <= t:
                d += 1
            continue
        a = S[t] / 100.0
        q = 0
        while q < nal:
            if _alive_step(I, F, alive[q], t, H, Lo, C, S):
                nal -= 1
                alive[q] = alive[nal]
            else:
                q += 1
        while d < nd and dt[d] == t:
            cl = dc[d]
            ne = 2 if cl >= 8 and cl <= 9 else 5
            rep = False
            e = d - 1
            while e >= 0 and dt[e] >= t - K_REPEAT:
                if dt[e] < t and dc[e] == cl:
                    same = True
                    for u in range(ne):
                        if abs(de[e, u] - de[d, u]) > K_REPEAT_TOL:
                            same = False
                    if same:
                        rep = True
                        break
                e -= 1
            if rep:
                d += 1
                continue
            i = ni
            ni += 1
            P = drp[d]
            Bb = drb[d]
            I[i, I_TID] = T_K0 + cl
            I[i, I_J0] = d
            I[i, I_K] = ne
            I[i, I_START] = t
            I[i, I_FORMED] = t
            I[i, I_WHY] = W_ALIVE
            I[i, I_NEAR] = 0
            I[i, I_BACK] = 0
            I[i, I_CTRIG] = 1
            I[i, I_FB] = Bb[0]
            I[i, I_LASTB] = Bb[ne - 1]
            I[i, I_LASTC] = t
            I[i, I_BARE] = t
            F[i, F_FP] = P[0]
            F[i, F_LASTP] = P[ne - 1]
            textb = -1 if (cl % 2 == 0) else 1
            I[i, I_FT] = 1 if (cl % 2 == 0) else -1
            if cl == 0 or cl == 10 or cl == 1 or cl == 11:
                s_ = (P[3] - P[1]) / max(Bb[3] - Bb[1], 1)          # two extrema can map to one raw bar
                nl = P[1] + s_ * (t - Bb[1])
                if cl == 0 or cl == 10:
                    hgt = P[2] - (P[1] + s_ * (Bb[2] - Bb[1]))
                    dn, ds, up, us = nl, s_, P[4], 0.0
                else:
                    hgt = (P[1] + s_ * (Bb[2] - Bb[1])) - P[2]
                    dn, ds, up, us = P[4], 0.0, nl, s_
                ratio = (Bb[4] - Bb[2]) / max(Bb[2] - Bb[0], 1.0)
                sym = 0.5 * (max(0.0, 1.0 - abs(P[0] - P[4]) / (HS_SDIFF * hgt)) + max(0.0, 1.0 - abs(math.log(max(ratio, 1e-9))) / math.log(HS_RATIO))) if hgt > 0 else np.nan
            elif cl >= 2 and cl <= 5:
                if cl % 2 == 0:                    # E1 a maximum: maxima E1 E3 E5, minima E2 E4
                    au, bu = _lsq3(Bb[0], P[0], Bb[2], P[2], Bb[4], P[4])
                    bl = (P[3] - P[1]) / max(Bb[3] - Bb[1], 1)
                    al = P[1] - bl * Bb[1]
                else:
                    al, bl = _lsq3(Bb[0], P[0], Bb[2], P[2], Bb[4], P[4])
                    bu = (P[3] - P[1]) / max(Bb[3] - Bb[1], 1)
                    au = P[1] - bu * Bb[1]
                up, us, dn, ds = au + bu * t, bu, al + bl * t, bl
                hgt = (au + bu * Bb[4]) - (al + bl * Bb[4])
                lo_, hi_ = 1e300, 0.0
                for u in range(4):
                    x = float(Bb[u + 1] - Bb[u])
                    lo_ = min(lo_, x)
                    hi_ = max(hi_, x)
                sym = lo_ / hi_ if hi_ > 0 else np.nan
            elif cl == 6 or cl == 7:
                if cl == 6:
                    up, dn = max(P[0], max(P[2], P[4])), min(P[1], P[3])
                    hgt = (P[0] + P[2] + P[4]) / 3.0 - 0.5 * (P[1] + P[3])
                else:
                    up, dn = max(P[1], P[3]), min(P[0], min(P[2], P[4]))
                    hgt = 0.5 * (P[1] + P[3]) - (P[0] + P[2] + P[4]) / 3.0
                us = ds = 0.0
                lo_, hi_ = 1e300, 0.0
                for u in range(4):
                    x = float(Bb[u + 1] - Bb[u])
                    lo_ = min(lo_, x)
                    hi_ = max(hi_, x)
                sym = lo_ / hi_ if hi_ > 0 else np.nan
            else:
                avg = 0.5 * (P[0] + P[1])
                if cl == 8:
                    up, dn = max(P[0], P[1]), dv[d]
                    hgt = avg - dv[d]
                else:
                    up, dn = dv[d], min(P[0], P[1])
                    hgt = dv[d] - avg
                us = ds = 0.0
                sym = max(0.0, 1.0 - abs(P[0] - P[1]) / (2.0 * LMW_TOL * abs(avg))) if avg != 0 else np.nan
            span = float(Bb[ne - 1] - Bb[0])
            F[i, F_DNV] = dn
            F[i, F_DNS] = ds
            F[i, F_UPV] = up
            F[i, F_UPS] = us
            F[i, F_LREF] = t
            F[i, F_HDN] = hgt
            F[i, F_HUP] = hgt
            F[i, F_FOVD] = np.nan
            F[i, F_FOVU] = np.nan
            F[i, F_EXP] = min(EXPIRE_HI, max(EXPIRE_LO, span / 2.0))
            lsl = ds if textb < 0 else us
            _moment(F, i, 0, hgt, span, sym, lsl * span / hgt if hgt > 0 else np.nan, a)
            _moment(F, i, 1, hgt, span, sym, lsl * span / hgt if hgt > 0 else np.nan, a)
            # Rink: a close beyond a level inside the 12-bar lag fires the break at the window's last bar
            dirn = 0
            for u in range(t - K_LAG + 1, t + 1):
                if u < 0:
                    continue
                if C[u] < dn + ds * (u - t):
                    dirn = -1
                    break
                if C[u] > up + us * (u - t):
                    dirn = 1
                    break
            if dirn != 0:
                I[i, I_RINK] = 1
                F[i, F_HGT_B] = hgt
                F[i, F_SPAN_B] = span
                F[i, F_SYM_B] = sym
                F[i, F_SLOPE_B] = (ds if dirn < 0 else us) * span / hgt if hgt > 0 else np.nan
                F[i, F_A_B] = a
                _set_break(I, F, i, t, dirn, up, us, dn, ds, C, a)
            else:
                I[i, I_RINK] = 0
            alive[nal] = i
            nal += 1
            d += 1
        while d < nd and dt[d] < t:
            d += 1
    return I[:ni].copy(), F[:ni].copy()


# ------------------------------------------------------------------------------------------------- instance tables
_PRICE_F = [F_LASTP, F_DNV, F_UPV, F_TRIG, F_FAILV, F_TGTV, F_HALFV, F_CB, F_UPTB, F_DNTB, F_FP, F_FOVD, F_FOVU]
_SLOPE_F = [F_DNS, F_UPS, F_TSLOPE, F_SLOPE_E, F_SLOPE_F, F_SLOPE_B]
_ICOLS = ['tid', 'j0', 'k', 'start', 'end', 'why', 'near', 'fid', 'formed', 'brk', 'dir', 'retest', 'fail', 'tgt_bar', 'half_bar', 'lastb',
          'lastc', 'ctrig', 'back', 'fb', 'ft', 'bar_e', 'rink', 'var']
_FCOLS = ['lastp', 'margin', 'dnv', 'dns', 'upv', 'ups', 'lref', 'hdn', 'hup', 'fovd', 'fovu', 'apex', 'expire', 'post', 'trig', 'trig_slope',
          'failv', 'tgtv', 'halfv', 'p_rw', 'cb', 'up_tb', 'dn_tb', 'fp', 'hgt_E', 'span_E', 'sym_E', 'slope_E', 'hgt_F', 'span_F', 'sym_F',
          'slope_F', 'hgt_B', 'span_B', 'sym_B', 'slope_B', 'pre_E', 'pre_F', 'pre_B', 'bvol', 'bdist', 'a_E', 'a_F', 'a_B']


def _orient_arrays(fb: dict, zz: dict, o: int) -> tuple:
    """The bars and the zigzag in orientation o (1 = mirrored: prices negated, highs and lows swapped)."""
    if o == 0:
        return fb['h'], fb['l'], fb['c'], zz['pp'], zz['pt'], zz['d'], zz['xp']
    return (np.ascontiguousarray(-fb['l']), np.ascontiguousarray(-fb['h']), np.ascontiguousarray(-fb['c']), -zz['pp'],
            (-zz['pt']).astype(np.int8), (-zz['d']).astype(np.int8), -zz['xp'])


def _to_frame(parts: list, kind: str) -> pd.DataFrame:
    """Instance records of one frame as a table, back in the original orientation (the mirrored parts' prices and
    slopes negated, their directions flipped) with each instance's pattern."""
    rows = []
    for o, I, F in parts:
        if not len(I):
            continue
        F = F.copy()
        I = I.copy()
        if o == 1:
            F[:, _PRICE_F] *= -1.0
            F[:, _SLOPE_F] *= -1.0
            I[:, I_DIR] = np.where(I[:, I_BRK] >= 0, -I[:, I_DIR], -1)
            I[:, I_FT] = -I[:, I_FT]
        d = pd.DataFrame(I, columns=_ICOLS)
        for j, c in enumerate(_FCOLS):
            d[c] = F[:, j]
        d['orient'] = o
        rows.append(d)
    if not rows:
        d = pd.DataFrame(columns=_ICOLS + _FCOLS + ['orient'])          # a frame with no instance: numeric columns all the same
        d = d.astype({**{c: np.float64 for c in _FCOLS}, **{c: np.int64 for c in _ICOLS + ['orient']}})
    else:
        d = pd.concat(rows, ignore_index=True)
    if kind == 'K':
        d['pattern'] = [KPATTERNS[t - T_K0] for t in d['tid']]
        d['textbook'] = [KTEXTBOOK[p] for p in d['pattern']]
        d['variant'] = ''
    else:
        d['pattern'] = [TPL_NAME[int(t)][int(o)] for t, o in zip(d['tid'], d['orient'])]
        d['textbook'] = [TEXTBOOK[p] for p in d['pattern']]
        d['variant'] = [HARM_NAMES[t - T_HARM0] if T_HARM0 <= t < T_LINE0 else '' for t in d['tid']]
    d['check'] = [CHECKS[int(t)][int(f)] if (f >= 0 and int(t) in CHECKS) else '' for t, f in zip(d['tid'], d['fid'])]
    return d


def _cont(d: pd.DataFrame) -> np.ndarray:
    """cont: the set shares k - 2 pivots with an earlier alive passing set of the same pattern (the set two pivots back,
    alive at this one's start), passing sets counted whether or not they are flagged. Pivot templates only."""
    out = np.zeros(len(d), np.int8)
    if not len(d):
        return out
    ok = (d['near'].to_numpy() == 0) & (d['tid'].to_numpy() < N_TPL)
    key = {}
    for i in np.flatnonzero(ok):
        key[(d['pattern'].iat[i], int(d['orient'].iat[i]), int(d['tid'].iat[i]), int(d['j0'].iat[i]))] = i
    st, en = d['start'].to_numpy(), d['end'].to_numpy()
    for i in np.flatnonzero(ok):
        j = key.get((d['pattern'].iat[i], int(d['orient'].iat[i]), int(d['tid'].iat[i]), int(d['j0'].iat[i]) - CONT_SHARE))
        if j is not None and st[j] <= st[i] and (en[j] < 0 or en[j] > st[i]):
            out[i] = 1
    return out


def _pivot_cols(d: pd.DataFrame, zz: dict = None, det: tuple = None) -> None:
    """piv1..piv5: extreme bar, confirmation bar and price of every pivot of the instance (the last one as it stood at
    the instance's last recorded moment)."""
    n = len(d)
    for u in range(1, 6):
        d[f'piv{u}_bar'] = np.full(n, -1, np.int64)
        d[f'piv{u}_conf'] = np.full(n, -1, np.int64)
        d[f'piv{u}_px'] = np.full(n, np.nan)
    if not n:
        return
    k = d['k'].to_numpy()
    j0 = d['j0'].to_numpy()
    sg = np.where(d['orient'].to_numpy() == 1, -1.0, 1.0)
    for u in range(5):
        has = u < k - 1
        if zz is not None:
            jj = np.where(has, j0 + u, 0)
            if len(zz['pb']):
                d.loc[has, f'piv{u + 1}_bar'] = zz['pb'][jj[has]]
                d.loc[has, f'piv{u + 1}_conf'] = zz['pc'][jj[has]]
                d.loc[has, f'piv{u + 1}_px'] = zz['pp'][jj[has]]
        elif det is not None:
            de, drb, drp = det
            jj = np.where(has, j0, 0)
            d.loc[has, f'piv{u + 1}_bar'] = drb[jj[has], u]
            d.loc[has, f'piv{u + 1}_conf'] = d['formed'].to_numpy()[has]
            d.loc[has, f'piv{u + 1}_px'] = drp[jj[has], u]
        last = k - 1 == u
        d.loc[last, f'piv{u + 1}_bar'] = d['lastb'].to_numpy()[last]
        d.loc[last, f'piv{u + 1}_conf'] = d['lastc'].to_numpy()[last]
        d.loc[last, f'piv{u + 1}_px'] = d['lastp'].to_numpy()[last]
    del sg


def detect_zz(fb: dict, r: int) -> tuple:
    """One zigzag frame: the zigzag, STRUCT and BOS codes, and every instance (pivot templates on both orientations,
    flags and pennants, rounding bottoms and tops) with near misses, as a table."""
    zz = zigzag(fb, r)
    st, bos = structure(fb, zz)
    lmax = float(L_MAX[r])
    tpls = np.arange(N_TPL, dtype=np.int64)
    parts = []
    for o in (0, 1):
        H, Lo, C, pp, pt, d, xp = _orient_arrays(fb, zz, o)
        args = (H, Lo, C, fb['S'], fb['stale'], zz['pb'], pp, pt, zz['pc'], zz['npb'], zz['seg0'], d, zz['xb'], xp)
        for I, F in (_track(*args, float(r), lmax, tpls), _track_flags(*args, float(r)), _track_round(*args, float(r), lmax)):
            _pre_bvol(I, F, H, Lo, fb['v'])
            parts.append((o, I, F))
    tab = _to_frame(parts, 'z')
    tab['cont'] = _cont(tab)
    _pivot_cols(tab, zz=zz)
    return zz, st, bos, tab


def detect_k(fb: dict) -> tuple:
    """The kernel frame on one timeframe: every window of 72 bars without a stale bar and with a known ATR."""
    nb_ = fb['nb']
    ok = ~fb['stale'] & np.isfinite(fb['S'])
    if nb_ < K_WIN:
        ends = np.zeros(0, np.int64)
    else:
        bad = pd.Series((~ok).astype(np.int8)).rolling(K_WIN, min_periods=K_WIN).max().to_numpy()
        ends = np.flatnonzero(bad == 0).astype(np.int64)
    loo, sm, sw = kernel_mats()
    dets = []
    for lo in range(0, len(ends), K_CHUNK):
        e = ends[lo:lo + K_CHUNK]
        hs, Y, Y2 = _ksmooth(fb['c'], e, loo, sm, sw)
        dets.append(_kdetect(Y, Y2, e, fb['h'], fb['l']))
    if dets:
        dt, dc, de, drb, drp, dv = (np.concatenate([x[i] for x in dets]) for i in range(6))
    else:
        dt, dc = np.zeros(0, np.int64), np.zeros(0, np.int64)
        de, drb = np.zeros((0, 5), np.int64), np.zeros((0, 5), np.int64)
        drp, dv = np.zeros((0, 5)), np.zeros(0)
    I, F = _kinstances(dt, dc, de, drb, drp, dv, fb['h'], fb['l'], fb['c'], fb['S'], fb['stale'])
    _pre_bvol(I, F, fb['h'], fb['l'], fb['v'])
    tab = _to_frame([(0, I, F)], 'K')
    tab['cont'] = np.zeros(len(tab), np.int8)
    _pivot_cols(tab, det=(de, drb, drp))
    j0 = tab['j0'].to_numpy()
    for u in range(5):                                          # the smooth's extremum bars (the repeat rule reads these)
        tab[f'ext{u + 1}'] = de[j0, u] if len(tab) else np.zeros(0, np.int64)
    return {'n_windows': int(len(ends)), 'n_detections': int(len(dt))}, tab


def frames() -> list:
    """The 12 zigzag frames and the 3 kernel frames: (timeframe, frame name, r or None)."""
    return [(k, f'z{r}', r) for k in PAT_TFS for r in Z_R] + [(k, 'K', None) for k in K_TFS]


# ------------------------------------------------------------------------------------------------------- readings
def _pick(bar, prio, start, iid):
    """Per bar the event shown: the highest priority, then the older instance (earlier start, then lower id)."""
    if not len(bar):
        return np.zeros(0, np.int64), 0
    o = np.lexsort((iid, start, prio, bar))
    b = bar[o]
    first = np.r_[True, b[1:] != b[:-1]]
    return o[first], int(len(bar) - first.sum())


def _events(T: pd.DataFrame) -> dict:
    """Every event of the instances T: bar, level (EV_LEVELS index), priority, instance start, instance row, pattern."""
    B, LV, IR = [], [], []
    ix = np.arange(len(T))
    for col, lv in (('formed', None), ('brk', None), ('retest', 4), ('fail', 5), ('tgt_bar', 6)):
        b = T[col].to_numpy()
        h = b >= 0
        if col == 'formed':
            v = np.full(h.sum(), 1)
        elif col == 'brk':
            v = np.where(T['dir'].to_numpy()[h] > 0, 2, 3)
        else:
            v = np.full(h.sum(), lv)
        B.append(b[h])
        LV.append(v)
        IR.append(ix[h])
    bar = np.concatenate(B).astype(np.int64)
    lv = np.concatenate(LV).astype(np.int64)
    ir = np.concatenate(IR).astype(np.int64)
    prio = np.array([EV_PRIO[int(x)] for x in lv], np.int64) if len(lv) else np.zeros(0, np.int64)
    return {'bar': bar, 'lv': lv, 'prio': prio, 'start': T['start'].to_numpy()[ir] if len(ir) else np.zeros(0, np.int64), 'ir': ir,
            'pat': T['pattern'].to_numpy()[ir] if len(ir) else np.zeros(0, object)}


def _intervals(T: pd.DataFrame, nb_: int) -> dict:
    """[lo, hi) bar intervals of each state of each instance (the design's state rules)."""
    st, fo, br, tg, fa, en, why = (T[c].to_numpy() for c in ('start', 'formed', 'brk', 'tgt_bar', 'fail', 'end', 'why'))
    endx = np.where(en >= 0, en, nb_)
    stale_end = np.where(why == W_STALE, en, nb_)
    big = nb_ + 10**9
    f1 = np.minimum(np.minimum(np.where(fo >= 0, fo, big), np.where(br >= 0, br, big)), endx)
    out = {'forming': (st, f1)}
    out['formed'] = (np.where(fo >= 0, fo, 0), np.where(fo >= 0, np.minimum(np.where(br >= 0, br, big), endx), 0))
    bend = np.minimum.reduce([br + STATE_N, np.where(tg >= 0, tg, big), np.where(fa >= 0, fa, big), stale_end])
    dirv = T['dir'].to_numpy()
    out['bup'] = (np.where((br >= 0) & (dirv > 0), br, 0), np.where((br >= 0) & (dirv > 0), bend, 0))
    out['bdn'] = (np.where((br >= 0) & (dirv < 0), br, 0), np.where((br >= 0) & (dirv < 0), bend, 0))
    out['target'] = (np.where(tg >= 0, tg, 0), np.where(tg >= 0, np.minimum.reduce([tg + STATE_N, np.where(fa >= 0, fa, big), stale_end]), 0))
    out['failed'] = (np.where(fa >= 0, fa, 0), np.where(fa >= 0, np.minimum(fa + STATE_N, stale_end), 0))
    return out


def _paint(lo, hi, nb_):
    """Number of intervals [lo, hi) covering each bar."""
    lo = np.clip(lo, 0, nb_)
    hi = np.clip(hi, 0, nb_)
    keep = hi > lo
    d = np.zeros(nb_ + 1, np.int64)
    np.add.at(d, lo[keep], 1)
    np.add.at(d, hi[keep], -1)
    return np.cumsum(d[:-1])


def _qcode(x, e):
    if e is None:
        return np.full(len(x), -1, np.int8)
    return heat.bucket(x, e)


def _param_values(T: pd.DataFrame, which: np.ndarray) -> dict:
    """The seven quintile parameters of instances T at moment which ('E', 'F' or 'B' per row), as float64 (a frame with
    no instance gives empty object columns)."""
    out = {}
    for nm, col in (('height', 'hgt'), ('span', 'span'), ('sym', 'sym'), ('slope', 'slope'), ('pre', 'pre')):
        v = np.full(len(T), np.nan)
        for w in 'EFB':
            s = which == w
            if s.any():
                x = T[f'{col}_{w}'].to_numpy(np.float64)[s]
                if nm == 'height':
                    x = x / T[f'a_{w}'].to_numpy(np.float64)[s]
                v[s] = x
        out[nm] = v
    b = which == 'B'
    out['bvol'] = np.where(b, T['bvol'].to_numpy(np.float64), np.nan)
    out['bdist'] = np.where(b, T['bdist'].to_numpy(np.float64), np.nan)
    return out


def _ref_moment(T: pd.DataFrame) -> tuple:
    """The instance's own value moment: its first break, else formed, else its last forming bar (and that bar)."""
    br, fo, be = (T[c].to_numpy() for c in ('brk', 'formed', 'bar_e'))
    which = np.where(br >= 0, 'B', np.where(fo >= 0, 'F', 'E'))
    bar = np.where(br >= 0, br, np.where(fo >= 0, fo, be))
    return which, bar


def _a_moment(T: pd.DataFrame, fb: dict, a_rows: tuple) -> tuple:
    """Each instance's value moment as known at split A's end: its first break if that bar closed in A, else formed if
    formed in A, else its last forming bar if the instance had ended in A; an instance still alive and unbroken at A's
    end, or one that starts after it, is not an A instance. So no price after A's end moves an A edge. Returns (which,
    bar, in A)."""
    nb_ = max(fb['nb'] - 1, 0)
    row = lambda c: np.where(T[c].to_numpy() >= 0, fb['row'][np.clip(T[c].to_numpy(), 0, nb_)], np.iinfo(np.int64).max)
    lo, hi = a_rows
    rb, rf, re_, rs, rend = row('brk'), row('formed'), row('bar_e'), row('start'), row('end')
    inb = (rb >= lo) & (rb < hi)
    inf = ~inb & (rf >= lo) & (rf < hi)
    ine = ~inb & ~inf & (rs >= lo) & (rend < hi) & (re_ >= lo) & (re_ < hi) & (T['formed'].to_numpy() < 0) & (T['brk'].to_numpy() < 0)
    which = np.where(inb, 'B', np.where(inf, 'F', 'E'))
    bar = np.where(inb, T['brk'].to_numpy(), np.where(inf, T['formed'].to_numpy(), T['bar_e'].to_numpy()))
    return which, bar, inb | inf | ine


def param_edges(tabs: dict, fbs: dict, a_rows: tuple) -> tuple:
    """Quintile edges of each parameter over split A's instances of each frame (one value per instance, pooled over the
    frame's patterns; the value at the first break, else at formed, else at the last forming bar, as known at A's end:
    _a_moment), and per pattern (for the parameter curves and Part 3). Returns ({frame key: {name: [4 edges] or None}}, {frame key: {pattern: {name: edges}}})."""
    out, byp = {}, {}
    for key, T in tabs.items():
        T = T[T['near'] == 0]
        fb = fbs[key.split(':')[0]]
        which, bar, inA = _a_moment(T, fb, a_rows)
        vals = _param_values(T, which)
        q = lambda x: [float(v) for v in np.quantile(x, [0.2, 0.4, 0.6, 0.8])] if len(x) >= 5 else None
        out[key] = {nm: q(v[inA & np.isfinite(v)]) for nm, v in vals.items()}
        pats = T['pattern'].to_numpy()
        byp[key] = {p: {nm: q(v[inA & np.isfinite(v) & (pats == p)]) for nm, v in vals.items()} for p in sorted(set(pats))}
    return out, byp


def frame_readings(fb: dict, T: pd.DataFrame, frame: str, edges: dict, st=None, bos=None) -> tuple:
    """Every reading of one frame in the engine's format, and its counts (hidden events per reading, collisions)."""
    nb_, k = fb['nb'], fb['k']
    base = f'{k}m:CHART.{frame}'
    pats = KPATTERNS if frame == 'K' else PATTERNS
    na = fb['stale'].copy()
    na[:min(WARM_BARS, nb_)] = True
    T = T[T['near'] == 0].reset_index(drop=True)
    E = _events(T)
    R, info = [], {'hidden': {}, 'collisions': 0}
    mk = lambda name, codes, levels, every, b=base: {'name': name, 'k': k, 'codes': np.where(na, -1, codes).astype(np.int8), 'levels': list(levels),
                                                    'base': b, 'family': 'chart', 'every': bool(every), 'cond': not every}
    iv = _intervals(T, nb_)
    cnt_all = {s: np.zeros(nb_, np.int64) for s in ('bup', 'bdn')}
    pat_arr = T['pattern'].to_numpy()
    for p in pats:
        sel = E['pat'] == p
        codes = np.zeros(nb_, np.int8)
        o, hid = _pick(E['bar'][sel], E['prio'][sel], E['start'][sel], E['ir'][sel])
        codes[E['bar'][sel][o]] = E['lv'][sel][o]
        R.append(mk(f'{base}.{p}', codes, EV_LEVELS, True))
        info['hidden'][f'{base}.{p}'] = hid
        ps = pat_arr == p
        c = {s: _paint(lo[ps], hi[ps], nb_) for s, (lo, hi) in iv.items()}
        for s in cnt_all:
            cnt_all[s] += c[s]
        sc = np.zeros(nb_, np.int8)
        sc[c['forming'] > 0] = 1
        sc[c['formed'] > 0] = 2
        sc[c['target'] > 0] = 6
        sc[c['failed'] > 0] = 7
        sc[c['bup'] > 0] = 3
        sc[c['bdn'] > 0] = 4
        sc[(c['bup'] > 0) & (c['bdn'] > 0)] = 5
        R.append(mk(f'{base}.{p}.state', sc, ST_LEVELS, False))
    if st is not None:
        R.append(mk(f'{base}.STRUCT', st, STRUCT_LEVELS, False))
        R.append(mk(f'{base}.BOS', np.maximum(bos, 0), BOS_LEVELS, True))
    # ANY: the breaks of the frame's patterns on the bar
    any_lv = ['none'] + [f'{p} {d}' for p in pats for d in ('up', 'down')] + ['several up', 'several down', 'conflict']
    ac = np.zeros(nb_, np.int8)
    bsel = (E['lv'] == 2) | (E['lv'] == 3)
    if bsel.any():
        bb, bl, bp = E['bar'][bsel], E['lv'][bsel], E['pat'][bsel]
        pidx = np.array([pats.index(x) for x in bp], np.int64)
        o = np.lexsort((pidx, bl, bb))
        bb, bl, pidx = bb[o], bl[o], pidx[o]
        starts = np.flatnonzero(np.r_[True, bb[1:] != bb[:-1]])
        ends = np.r_[starts[1:], len(bb)]
        for s0, s1 in zip(starts, ends):
            lvs, ps_ = bl[s0:s1], pidx[s0:s1]
            if (lvs == 2).all() or (lvs == 3).all():
                up = lvs[0] == 2
                if len(set(ps_.tolist())) == 1:
                    ac[bb[s0]] = 1 + 2 * ps_[0] + (0 if up else 1)
                else:
                    ac[bb[s0]] = len(any_lv) - (3 if up else 2)
            else:
                ac[bb[s0]] = len(any_lv) - 1
    R.append(mk(f'{base}.ANY', ac, any_lv, True))
    cu, cd = cnt_all['bup'], cnt_all['bdn']
    bias = np.where((cu > 0) & (cd > 0), 5, np.where(cu >= 2, 2, np.where(cu == 1, 1, np.where(cd >= 2, 4, np.where(cd == 1, 3, 0)))))
    R.append(mk(f'{base}.BIAS', bias, BIAS_LEVELS, False))
    # parameters: the frame's current instance (the latest event within STATE_N bars; ties as the event readings)
    o, hid = _pick(E['bar'], E['prio'], E['start'], E['ir'])
    eb = E['bar'][o]
    if len(E['bar']):
        ninst = pd.Series(E['ir']).groupby(E['bar']).nunique()
        info['collisions'] = int((ninst > 1).sum())
    shown = np.full(nb_, -1, np.int64)
    shown_lv = np.zeros(nb_, np.int64)
    shown[eb] = E['ir'][o]
    shown_lv[eb] = E['lv'][o]
    last = np.where(shown >= 0, np.arange(nb_), -1)
    last = np.maximum.accumulate(last) if nb_ else last
    t = np.arange(nb_)
    cur = (last >= 0) & (t - last < STATE_N)
    li = np.where(cur, last, 0)
    ir = np.where(cur, shown[li], -1)
    lvv = np.where(cur, shown_lv[li], 0)
    which = np.where(lvv == 1, 'F', 'B')
    vals = {nm: np.full(nb_, np.nan) for nm in PARAMS}
    hasi = ir >= 0
    if hasi.any() and len(T):
        Ti = T.iloc[ir[hasi]].reset_index(drop=True)
        pv = _param_values(Ti, which[hasi])
        for nm, v in pv.items():
            vals[nm][hasi] = v
        brk = Ti['brk'].to_numpy()
        tt = t[hasi]
        post = (brk >= 0) & (brk <= tt) & (which[hasi] == 'B')
        a = fb['S'][tt] / 100.0
        with np.errstate(invalid='ignore', divide='ignore'):
            td = (Ti['tgtv'].to_numpy() - fb['c'][tt]) * Ti['dir'].to_numpy() / a
        vals['tdist'][hasi] = np.where(post, td, np.nan)
        age = (tt - brk).astype(np.float64)
        vals['age'][hasi] = np.where(post & (age <= STATE_N), age, np.nan)
    for nm in PARAMS:
        x = vals[nm]
        if nm in PARAM_Q:
            codes, lv = _qcode(x, (edges or {}).get(nm)), Q_LEVELS
        elif nm == 'tdist':
            codes = np.where(np.isfinite(x), np.where(x < 0, 0, np.searchsorted(np.asarray(TDIST_EDGES), x, 'left') + 1), -1)
            lv = TDIST_LEVELS
        else:
            codes = np.where(np.isfinite(x), np.minimum(np.searchsorted(np.asarray(AGE_EDGES, float), x, 'left'), 4), -1)
            lv = AGE_LEVELS
        R.append(mk(f'{base}.p.{nm}', np.asarray(codes).astype(np.int8), lv, False, b=f'{base}.p.{nm}'))
    return R, info


def compact(readings: list) -> list:
    """The 54 readings of the pair scan: ANY, BIAS, STRUCT and BOS of each zigzag frame, ANY and BIAS of each kernel
    frame."""
    want = []
    for k, fr, r in frames():
        for x in (('ANY', 'BIAS', 'STRUCT', 'BOS') if fr != 'K' else ('ANY', 'BIAS')):
            want.append(f'{k}m:CHART.{fr}.{x}')
    by = {R['name']: R for R in readings}
    return [by[n] for n in want if n in by]


def _sha(codes: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(codes, np.int8).tobytes()).hexdigest()


def _a_rows(t0: int) -> tuple:
    """Minute rows of split A: [first row of 2020 (or 0), first row of 2025)."""
    a, b = heat.SPLITS['A']
    return max(0, int((a - t0) // MIN)), max(0, int((b - t0) // MIN))


def run_tf(mu: dict, k: int, s: int = 0, e: int = None, edges: dict = None, a_rows: tuple = None, want: set = None) -> dict:
    """Every frame of timeframe k on bars s .. e-1 of tick-unit minutes mu: bars, detectors and instance tables (the
    readings are built once the edges are known: run_readings)."""
    fb = frame_bars(mu, k, s, e)
    out = {'fb': fb, 'frames': {}, 'sec': {}}
    for kk, fr, r in frames():
        if kk != k or (want is not None and fr not in want):
            continue
        t = time.time()
        if r is not None:
            zz, st, bos, tab = detect_zz(fb, r)
            out['frames'][fr] = {'zz': zz, 'st': st, 'bos': bos, 'tab': tab}
        else:
            info, tab = detect_k(fb)
            out['frames'][fr] = {'tab': tab, 'info': info}
        out['sec'][fr] = round(time.time() - t, 2)
    return out


def tf_readings(run: dict, edges: dict) -> tuple:
    """The readings of every frame of one run_tf result with the given edges ({'5m:z2': {name: edges}})."""
    fb = run['fb']
    R, info = [], {}
    for fr, x in run['frames'].items():
        key = f'{fb["k"]}m:{fr}'
        rr, inf = frame_readings(fb, x['tab'], fr, (edges or {}).get(key), x.get('st'), x.get('bos'))
        R += rr
        info[key] = inf
    return R, info


def pattern_readings(m: dict, a_hi: int = None, log=print, tfs=None) -> tuple:
    """All frames of one series (minutes m: a coin or a twin; its own bars). Returns (readings, edges, inst, meta):
    inst = {'<k>m:<frame>': instance table} plus inst['_fb'] (the bars of each timeframe) and inst['_zz'] (each
    zigzag); meta: frames, constants, reading names and levels, sha256 of every reading's codes, the edges (pooled and
    per pattern), instance counts per pattern and frame (distinct, with cont, near misses), hidden events and
    collisions, the stale share per timeframe and split, and seconds per frame."""
    t_all = time.time()
    if a_hi is None:
        a_hi = max(0, min(int((heat.SPLITS['A'][1] - heat.HMAX * MIN - m['t0']) // MIN), m['n']))
    mu = units(m, a_hi)
    a_rows = _a_rows(m['t0'])
    tfs = sorted(set(PAT_TFS) | set(K_TFS)) if tfs is None else tfs
    runs, tabs, fbs, zzs, sec = {}, {}, {}, {}, {}
    for k in tfs:
        runs[k] = run_tf(mu, k)
        fbs[f'{k}m'] = runs[k]['fb']
        for fr, x in runs[k]['frames'].items():
            tabs[f'{k}m:{fr}'] = x['tab']
            if 'zz' in x:
                zzs[f'{k}m:{fr}'] = x['zz']
            sec[f'{k}m:{fr}'] = runs[k]['sec'][fr]
        log(f'  chart {k}m: {runs[k]["fb"]["nb"]:,} bars; instances ' +
            ', '.join(f'{fr} {int((x["tab"]["near"] == 0).sum()):,}' for fr, x in runs[k]['frames'].items()))
    edges, edges_p = param_edges(tabs, fbs, a_rows)
    readings, infos = [], {}
    for k in tfs:
        rr, inf = tf_readings(runs[k], edges)
        readings += rr
        infos.update(inf)
    stale = {}
    for key, fb in fbs.items():
        out = {}
        for s, (a, b) in heat.SPLITS.items():
            lo, hi = max(0, int((a - m['t0']) // MIN)), max(0, int((b - m['t0']) // MIN))
            sel = (fb['row'] >= lo) & (fb['row'] < hi)
            out[s] = float(fb['stale'][sel].mean()) if sel.any() else None
        stale[key] = out
    counts = {}
    for key, T in tabs.items():
        c = {}
        for p, g_ in T.groupby('pattern'):
            nn = g_['near'].to_numpy() == 0
            c[p] = {'instances': int(nn.sum()), 'distinct': int((nn & (g_['cont'].to_numpy() == 0)).sum()), 'near': int((~nn).sum()),
                    'breaks': int((nn & (g_['brk'].to_numpy() >= 0)).sum())}
        counts[key] = c
    meta = {'frames': [{'tf': k, 'frame': fr, 'r': r} for k, fr, r in frames() if k in tfs], 'constants': constants(),
            'readings': [{'name': R['name'], 'k': R['k'], 'levels': R['levels'], 'base': R['base'], 'every': R['every']} for R in readings],
            'sha256': {R['name']: _sha(R['codes']) for R in readings}, 'edges': edges, 'edges_by_pattern': edges_p, 'counts': counts,
            'hidden': {k: v for inf in infos.values() for k, v in inf['hidden'].items()},
            'collisions': {key: inf['collisions'] for key, inf in infos.items()}, 'stale_share': stale, 'seconds': sec,
            'price_step': mu.get('step'), 'a_rows': list(a_rows), 'seconds_total': round(time.time() - t_all, 1)}
    inst = dict(tabs)
    inst['_fb'] = fbs
    inst['_zz'] = zzs
    inst['_mu'] = {'c': mu['c'], 'h': mu['h'], 'l': mu['l'], 'n': mu['n'], 't0': mu['t0'], 'step': mu.get('step')}
    inst['_edges_p'] = edges_p
    return readings, edges, inst, meta


def constants() -> dict:
    return {'PAT_TFS': PAT_TFS, 'Z_R': Z_R, 'K_TFS': K_TFS, 'ATR_N': ATR_N, 'WARM_BARS': WARM_BARS, 'L_MAX': {str(k): v for k, v in L_MAX.items()},
            'EXPIRE': [EXPIRE_LO, EXPIRE_HI], 'POST': [POST_LO, POST_HI], 'STATE_N': STATE_N, 'PRE_MAX': PRE_MAX,
            'RETEST': [RETEST_BARS, RETEST_TOL], 'HS': [HS_SH_LO, HS_SH_HI, HS_HEAD, HS_SDIFF, HS_NLRISE, HS_RATIO],
            'DTOP': [DT_TOL, DT_SEP], 'TRITOP': [TRI_PEAKS, TRI_VALLEYS, TRI_RATIO], 'LINES': [LN_TOUCH, LN_FLAT, LN_TILT, LN_CONV],
            'FLAG': [FLAG_MIN, FLAG_FORMED, FLAG_MAX, FLAG_POLE_R, FLAG_POLE_SPEED, FLAG_RETRACE, FLAG_TILT_LO, FLAG_TILT_HI, FLAG_PAR,
                     FLAG_TIGHT, PEN_SLOPE],
            'CUP': [CUP_RIM, CUP_MIN, CUP_R2, CUP_HANDLE], 'ROUND': [ROUND_R2, ROUND_MID, ROUND_MIN, ROUND_DEPTH],
            'ABCD': [ABCD_BC_LO, ABCD_BC_HI, ABCD_CD_LO, ABCD_CD_HI, ABCD_T_LO, ABCD_T_HI], 'HARM_TOL': HARM_TOL,
            'HARM_B': HARM_B.tolist(), 'HARM_D': HARM_D.tolist(),
            'K': {'window': K_WIN, 'last': K_LAST + 1, 'lag': K_LAG, 'grid': K_GRID.tolist(), 'factor': K_FACTOR, 'swz': K_SWZ, 'lmw_tol': LMW_TOL,
                  'lmw_rect': LMW_RECT, 'dtop_sep': K_DTOP_SEP, 'swz_r': [SWZ_SH, SWZ_TR, SWZ_HEAD, SWZ_SPACING], 'repeat': [K_REPEAT, K_REPEAT_TOL]},
            'EV_LEVELS': EV_LEVELS, 'ST_LEVELS': ST_LEVELS, 'PATTERNS': PATTERNS, 'KPATTERNS': KPATTERNS, 'PARAMS': PARAMS}


# ------------------------------------------------------------------------------------------------------- the catalogue
CAT_PRIO = {'break up': 0, 'break down': 0, 'failure': 1, 'target': 2, 'retest': 3, 'formed': 4, 'half target': 5, 'near miss': 6}
CAT_H = [60, 240, 1440]
LAB_H = [1, 5, 15, 30, 60]
LAB_KEYS = ['ret', 'sg', 'up', 'dn', 'dipU', 'dipD']
LIVE_WINDOW = 3000
TZ_ET = 'America/New_York'
SLIM = ['frame', 'tf', 'fr', 'pattern', 'event', 'event_row', 'event_bar', 'inst', 'instance', 'near', 'cont', 'dir', 'textbook', 'split',
        'p_rw', 'tbi', 'retest_row', 'fail_row', 'tgt_row', 'start_row', 'why'] + PARAMS + ['sg15', 'sg60', 'sg240']


@nb.njit(cache=True)
def _first_close(C, rows, d, lvl, strict, end, out):
    """Per event i: the first minute row after rows[i] (up to end[i], exclusive) whose close is at or beyond lvl[i] in
    direction d[i] (strict: beyond), else -1. d = 0 or a NaN level: -1."""
    for i in range(len(rows)):
        out[i] = -1
        di = d[i]
        v = lvl[i]
        if di == 0 or not (v == v):
            continue
        for r in range(rows[i] + 1, end[i]):
            x = C[r]
            if di > 0:
                hit = x > v if strict else x >= v
            else:
                hit = x < v if strict else x <= v
            if hit:
                out[i] = r
                break


@nb.njit(cache=True)
def _range_after(H, Lo, rows, w, end, hi, lo):
    """The highest minute high and lowest minute low of rows[i] + 1 .. rows[i] + w; NaN when that window crosses end[i]."""
    for i in range(len(rows)):
        r0 = rows[i]
        if r0 < 0 or r0 + w >= end[i]:
            hi[i] = np.nan
            lo[i] = np.nan
            continue
        a = H[r0 + 1]
        b = Lo[r0 + 1]
        for r in range(r0 + 2, r0 + w + 1):
            if H[r] > a:
                a = H[r]
            if Lo[r] < b:
                b = Lo[r]
        hi[i] = a
        lo[i] = b


def _split_rows(t0: int, n: int) -> tuple:
    """(rowA0, rowB0, rowEnd): the minute rows where split A starts, B starts and B ends (heat.SPLITS, clipped to n)."""
    (a0, a1), (b0, b1) = heat.SPLITS['A'], heat.SPLITS['B']
    f = lambda x: int(min(max(0, (x - t0) // MIN), n))
    return f(a0), f(b0), f(min(b1, heat.HEAT_END))


def _split_end(rows: np.ndarray, t0: int, n: int) -> tuple:
    """Per row: its split (0 A, 1 B, -1 neither) and the first row after its split (= the row itself when neither)."""
    a0, b0, e = _split_rows(t0, n)
    sp = np.where((rows >= a0) & (rows < b0), 0, np.where((rows >= b0) & (rows < e), 1, -1)).astype(np.int8)
    end = np.where(sp == 0, b0, np.where(sp == 1, e, rows)).astype(np.int64)
    return sp, end


def _ms_of(rows: np.ndarray, t0: int) -> np.ndarray:
    """UTC ms of the close of minute rows (-1 for a negative row)."""
    return np.where(rows >= 0, t0 + (rows + 1) * MIN, -1).astype(np.int64)


def _fmt_times(ms: np.ndarray) -> tuple:
    t = pd.to_datetime(pd.Series(ms), unit='ms', utc=True)
    return t.dt.strftime('%Y-%m-%d %H:%M').to_numpy(object), t.dt.tz_convert(TZ_ET).dt.strftime('%Y-%m-%d %H:%M %Z').to_numpy(object)


def catalogue_frame(key: str, T: pd.DataFrame, fb: dict, mu: dict, lab: dict = None, lab240: dict = None, slim: bool = False) -> pd.DataFrame:
    """One frame's catalogue, long format: one row per event of every instance (formed, break up / down, retest,
    failure, target, half target) and one row per near miss (at its confirmation bar), sorted by pattern, event row,
    then the event the reading shows first (priority, older instance), so a join on (frame, pattern, event_row) that
    keeps the first row gets the reading's instance. Prices in the coin's price (tick units x step); parameters as known
    at the event (formed and near miss: at formed; the rest: at the break; tdist and age at the event bar); outcomes:
    the engine labels at the event row (1-60 and 240), after a break the target and half target before the
    invalidation within 60 / 240 / 1,440 minutes and tbi (minute closes, both barriers, to the split's end), best and
    worst move in ATR within 240 minutes. An outcome whose window crosses its split's end is NA."""
    k, t0, n_m = fb['k'], mu['t0'], mu['n']
    tf, fr = key.split(':')
    step = float(mu['step']) if mu.get('step') else 1.0
    T = T.reset_index(drop=True)
    nn = T['near'].to_numpy() == 0
    I, B, E = [], [], []
    for col, name in (('formed', 'formed'), ('brk', None), ('retest', 'retest'), ('fail', 'failure'), ('tgt_bar', 'target'), ('half_bar', 'half target')):
        b = T[col].to_numpy()
        idx = np.flatnonzero((b >= 0) & nn)
        I.append(idx)
        B.append(b[idx])
        E.append(np.where(T['dir'].to_numpy()[idx] > 0, 'break up', 'break down') if name is None else np.full(len(idx), name, object))
    idx = np.flatnonzero(~nn)
    I.append(idx)
    B.append(T['formed'].to_numpy()[idx])
    E.append(np.full(len(idx), 'near miss', object))
    ii = np.concatenate(I).astype(np.int64)
    bar = np.concatenate(B).astype(np.int64)
    ev = np.concatenate(E).astype(object)
    pats = T['pattern'].to_numpy()[ii] if len(ii) else np.zeros(0, object)
    prio = np.array([CAT_PRIO[x] for x in ev], np.int64)
    start = T['start'].to_numpy()[ii] if len(ii) else np.zeros(0, np.int64)
    pcode = pd.factorize(pats, sort=True)[0] if len(ii) else np.zeros(0, np.int64)
    row = fb['row'][np.clip(bar, 0, max(fb['nb'] - 1, 0))] if len(ii) else np.zeros(0, np.int64)
    o = np.lexsort((ii, start, prio, row, pcode))
    ii, bar, ev, row, pats = ii[o], bar[o], ev[o], row[o], pats[o]
    Ti = T.iloc[ii].reset_index(drop=True)
    n = len(ii)
    D = {'frame': np.full(n, key, object), 'tf': np.full(n, tf, object), 'fr': np.full(n, fr, object), 'pattern': pats,
         'variant': Ti['variant'].to_numpy(), 'textbook': Ti['textbook'].to_numpy(), 'orient': Ti['orient'].to_numpy(), 'inst': ii,
         'instance': np.array([f'{key}#{x}' for x in ii], object), 'near': Ti['near'].to_numpy(), 'check': Ti['check'].to_numpy(),
         'margin': Ti['margin'].to_numpy(), 'cont': Ti['cont'].to_numpy(), 'rink12': Ti['rink'].to_numpy() if fr == 'K' else np.full(n, -1),
         'event': ev, 'event_bar': bar, 'event_row': row}
    ems = _ms_of(row, t0)
    sp, end = _split_end(row, t0, n_m)
    D['split'] = np.where(sp == 0, 'A', np.where(sp == 1, 'B', '')).astype(object)
    D['event_ms'] = ems
    dirv = Ti['dir'].to_numpy()
    brk = Ti['brk'].to_numpy()
    rowf = lambda b: np.where(b >= 0, fb['row'][np.clip(b, 0, max(fb['nb'] - 1, 0))], -1)
    for c, nm in (('start', 'start'), ('formed', 'formed'), ('brk', 'brk'), ('end', 'end'), ('retest', 'retest'), ('fail', 'fail'), ('tgt_bar', 'tgt'),
                  ('half_bar', 'half')):
        D[f'{nm}_bar'] = Ti[c].to_numpy()
        D[f'{nm}_row'] = rowf(Ti[c].to_numpy())
    D['why'] = np.array(WHY, object)[np.clip(Ti['why'].to_numpy(), 0, len(WHY) - 1)]
    D['dir'] = np.where(brk >= 0, dirv, 0)
    a_ev = fb['S'][np.clip(bar, 0, max(fb['nb'] - 1, 0))] / 100.0 if n else np.zeros(0)
    # parameters at the event
    which = np.where(np.isin(ev, ['formed', 'near miss']), 'F', 'B')
    pv = _param_values(Ti, which) if n else {nm: np.zeros(0) for nm in PARAM_Q}
    for nm in PARAM_Q:
        D[nm] = pv[nm]
    post = (brk >= 0) & (bar >= brk) & (which == 'B')
    cev = fb['c'][np.clip(bar, 0, max(fb['nb'] - 1, 0))] if n else np.zeros(0)
    with np.errstate(invalid='ignore', divide='ignore'):
        D['tdist'] = np.where(post, (Ti['tgtv'].to_numpy() - cev) * dirv / a_ev, np.nan)
    D['age'] = np.where(post, (bar - brk).astype(np.float64), np.nan)
    hgt = np.full(n, np.nan)
    for w in 'EFB':
        s = which == w
        hgt[s] = Ti[f'hgt_{w}'].to_numpy()[s]
    D['height_steps'] = hgt if mu.get('step') else np.full(n, np.nan)
    D['atr'] = a_ev * step
    # levels (prices) and lines
    for c in ('lastp', 'trig', 'trig_slope', 'failv', 'tgtv', 'halfv', 'cb', 'up_tb', 'dn_tb', 'dnv', 'dns', 'upv', 'ups', 'fp'):
        D[c] = Ti[c].to_numpy() * step
    D['p_rw'] = Ti['p_rw'].to_numpy()
    lref = Ti['lref'].to_numpy()
    x1 = np.where(Ti['end'].to_numpy() >= 0, Ti['end'].to_numpy(), fb['nb'] - 1).astype(np.float64)
    D['lines_known_bar'] = np.where(np.isfinite(lref), lref, np.where(brk >= 0, brk, -1)).astype(np.int64)
    D['dn_x1'] = x1
    D['dn_y1'] = (Ti['dnv'].to_numpy() + Ti['dns'].to_numpy() * (x1 - lref)) * step
    D['up_y1'] = (Ti['upv'].to_numpy() + Ti['ups'].to_numpy() * (x1 - lref)) * step
    for u in range(1, 6):
        for c in ('bar', 'conf'):
            b = Ti[f'piv{u}_{c}'].to_numpy()
            D[f'piv{u}_{c}'] = b
            D[f'piv{u}_{c}_ms'] = _ms_of(rowf(b), t0)
        D[f'piv{u}_px'] = Ti[f'piv{u}_px'].to_numpy() * step
    # the engine labels at the event row
    rr = np.clip(row, 0, n_m - 1)
    if lab is not None:
        for H in LAB_H:
            bad = row + H >= end
            for kk in LAB_KEYS:
                x = lab[f'{kk}{H}'][rr].astype(np.float64)
                D[f'{kk}{H}'] = np.where(bad, np.nan, x)
        bad = row + 60 >= end
        D['holdU'] = np.where(bad, np.nan, lab['holdU'][rr].astype(np.float64))
        D['holdD'] = np.where(bad, np.nan, lab['holdD'][rr].astype(np.float64))
        D['valid'] = lab['valid'][rr] & ~bad
    if lab240 is not None:
        bad = row + 240 >= end
        for kk in LAB_KEYS:
            D[f'{kk}240'] = np.where(bad, np.nan, lab240[f'{kk}240'][rr].astype(np.float64))
        D['holdU240'] = np.where(bad, np.nan, lab240['holdU'][rr].astype(np.float64))
        D['holdD240'] = np.where(bad, np.nan, lab240['holdD'][rr].astype(np.float64))
    # barriers on minute closes after a break (failure rows: none)
    pb = post & (ev != 'failure')
    d = np.where(pb, dirv, 0).astype(np.int64)
    ft, fh, fi = (np.empty(n, np.int64) for _ in range(3))
    C = np.ascontiguousarray(mu['c'], np.float64)
    _first_close(C, row, d, Ti['tgtv'].to_numpy().astype(np.float64), False, end, ft)
    _first_close(C, row, d, Ti['halfv'].to_numpy().astype(np.float64), False, end, fh)
    _first_close(C, row, -d, Ti['failv'].to_numpy().astype(np.float64), True, end, fi)
    first = lambda x: (x >= 0) & ((fi < 0) | (x < fi))
    D['tbi'] = np.where(pb & (first(ft) | (fi >= 0)), first(ft).astype(np.float64), np.nan)
    D['tbi_row'] = np.where(pb, np.where(first(ft), ft, np.where(fi >= 0, fi, -1)), -1)
    for H in CAT_H:
        ok = pb & (row + H < end)
        D[f'tgt{H}'] = np.where(ok, (first(ft) & (ft <= row + H)).astype(np.float64), np.nan)
        D[f'half{H}'] = np.where(ok, (first(fh) & (fh <= row + H)).astype(np.float64), np.nan)
    hi, lo = np.empty(n), np.empty(n)
    _range_after(np.ascontiguousarray(mu['h'], np.float64), np.ascontiguousarray(mu['l'], np.float64), row, 240, end, hi, lo)
    de = np.where(post, dirv, np.where(np.isin(ev, ['formed', 'near miss']), Ti['textbook'].to_numpy(), 0))
    c0 = C[rr] if n else np.zeros(0)
    with np.errstate(invalid='ignore', divide='ignore'):
        D['best240_atr'] = np.where(de > 0, (hi - c0) / a_ev, np.where(de < 0, (c0 - lo) / a_ev, np.nan))
        D['worst240_atr'] = np.where(de > 0, (c0 - lo) / a_ev, np.where(de < 0, (hi - c0) / a_ev, np.nan))
    out = pd.DataFrame(D)
    if slim:
        return out[[c for c in SLIM if c in out]].copy()
    out['event_utc'], out['event_et'] = _fmt_times(ems)
    return out


def catalogue(inst: dict, lab: dict = None, lab240: dict = None, slim: bool = False, path: str = None, label: str = None) -> pd.DataFrame:
    """Every frame's catalogue (catalogue_frame), frame by frame. path: also written there as one CSV.gz (appended frame
    by frame, so the full table is never held whole); the returned table is then the slim one. Returns the table."""
    keys = [f'{k}m:{fr}' for k, fr, r in frames() if f'{k}m:{fr}' in inst]
    parts = []
    first = True
    if path:
        if os.path.exists(path):
            os.remove(path)
    for key in keys:
        fb = inst['_fb'][key.split(':')[0]]
        c = catalogue_frame(key, inst[key], fb, inst['_mu'], lab, lab240, slim=False)
        if label is not None:
            c.insert(0, 'coin', label)
        if path:
            with gzip.open(path, 'at') as f:
                c.to_csv(f, index=False, header=first, float_format='%.10g')
            first = False
        parts.append(c[[x for x in (['coin'] if label is not None else []) + SLIM if x in c]].copy() if (slim or path) else c)
    if not parts:
        return pd.DataFrame(columns=SLIM)
    return pd.concat(parts, ignore_index=True)


def series_readings(ctx, log=_log_none) -> tuple:
    """Part 3's entry (heat_hm2_drill.chart_readings): every chart reading of ctx's own minutes (a twin's bars on a
    twin) and the slim catalogue (frame '<k>m:<frame>', pattern, event, event_row, instance, the nine parameters as
    known at each event, ...), joined by Part 3 on (frame, pattern, event_row)."""
    R, edges, inst, meta = pattern_readings(ctx.m, log=log)
    cat = catalogue(inst, getattr(ctx, 'lab', None), getattr(ctx, 'lab240', None), slim=True)
    return R, cat


# ---------------------------------------------------------------------------------------------- singles and curves
def _name_info(R: dict) -> dict:
    """frame, pattern (or the reading kind: STRUCT, BOS, ANY, BIAS, p.<name>, <P>.state) and textbook direction."""
    nm = R['name']
    tf, rest = nm.split(':', 1)
    parts = rest.split('.', 2)
    fr, what = parts[1], parts[2] if len(parts) > 2 else ''
    tb = TEXTBOOK.get(what, KTEXTBOOK.get(what, 0))
    if what.endswith('.state'):
        tb = TEXTBOOK.get(what[:-6], KTEXTBOOK.get(what[:-6], 0))
    return {'frame': f'{tf}:{fr}', 'pattern': what, 'textbook': tb, 'source': 'chart'}


def _reading_rows(ctx, R: dict, held: bool = True) -> list:
    """One chart reading's single rows: every event level's onsets (kind 'chart'), every non-neutral state level held
    (kind 'chart_held', every minute it holds) and, for BOS, the union of BOS and CHoCH per direction (kind 'chart_bos',
    the baseline of shape_lift). g.full per split on the main grid and on the 240 grid."""
    from oracle import heat_hm2 as h2
    out = []
    n = int(ctx.m['n'])
    ex = _name_info(R)
    for lv, side, lname in heat.event_levels(R):
        idx = heat.level_events(R, lv, side)
        idx = idx[idx < n]
        if len(idx):
            out += h2._rows_of('chart', f'{R["name"]}={lname}', 'onset', *h2._full_both(ctx, idx), dict(ex, event=lname))
    if held and not R.get('every'):
        st = heat.read_state(R, np.arange(n))
        for i, lname in enumerate(R['levels']):
            if lname in heat.NEUTRAL:
                continue
            idx = np.flatnonzero(st == i)
            if len(idx):
                out += h2._rows_of('chart_held', f'{R["name"]}={lname}', 'state', *h2._full_both(ctx, idx), dict(ex, event=lname))
    if R['name'].endswith('.BOS'):
        for side, lvs in (('up', [1, 3]), ('down', [2, 4])):
            idx = np.flatnonzero(np.isin(R['codes'], lvs)) * R['k'] + R['k'] - 1
            idx = idx[idx < n]
            if len(idx):
                out += h2._rows_of('chart_bos', f'{R["name"]}=any {side}', 'onset', *h2._full_both(ctx, idx), dict(ex, event=f'any {side}'))
    return out


def _singles_job(j):
    W = heat._W
    return j, _reading_rows(W['chart_ctx'], W['chart_R'][j])


def _curve_job(j):
    W = heat._W
    from oracle import heat_hm2 as h2
    key, ex, idx = W['chart_pc'][j]
    return j, h2._rows_of('chart_param', key, 'onset', *h2._full_both(W['chart_ctx'], idx), ex)


def _run_jobs(fn, n_jobs: int, procs: int, **ctxw) -> list:
    """fn over range(n_jobs) through forked workers (heat._W holds ctxw), results in job order."""
    from oracle import heat_hm2 as h2
    heat._W.update(ctxw)
    got = {}
    try:
        for j, rows in h2._imap(fn, list(range(n_jobs)), procs):
            got[j] = rows
    finally:
        for k in ctxw:
            heat._W.pop(k, None)
    out = []
    for j in range(n_jobs):
        out += got.pop(j)
    return out


def shape_lift(df: pd.DataFrame) -> pd.DataFrame:
    """Each break row (kind chart, '<frame>.<P>=break up / down' of a zigzag frame) gets the same frame's BOS row of
    the same direction (kind chart_bos, the union of BOS and CHoCH): shape_lift = its odds minus the BOS row's (odds
    points, 100 x edge_p), shape_lift_excess the same on the mean move. NaN without that row (and on the kernel frames)."""
    if not len(df):
        return df
    df = df.copy()
    isb = (df['kind'] == 'chart') & df['event'].isin(['break up', 'break down']) & ~df['frame'].str.endswith(':K')
    fr = df['frame'].str.split(':')
    df['bos_key'] = np.where(isb, fr.str[0] + ':CHART.' + fr.str[1] + '.BOS=any ' + np.where(df['event'] == 'break up', 'up', 'down'), '')
    bos = df[df['kind'] == 'chart_bos'][['key', 'split', 'h', 'edge_p', 'excess']].rename(columns={'key': 'bos_key', 'edge_p': 'bos_edge_p',
                                                                                                    'excess': 'bos_excess'})
    df = df.merge(bos, on=['bos_key', 'split', 'h'], how='left')
    df['shape_lift'] = np.where(isb.to_numpy(), 100.0 * (df['edge_p'] - df['bos_edge_p']), np.nan)
    df['shape_lift_excess'] = np.where(isb.to_numpy(), df['excess'] - df['bos_excess'], np.nan)
    return df.drop(columns=['bos_edge_p', 'bos_excess'])


def singles(ctx, readings: list, procs: int = 1, log=print) -> pd.DataFrame:
    """Every chart reading's single rows (heat.full_rows' format, through heat_hm2._rows_of: per split and horizon 1-60
    and, under h240, 240), kinds chart / chart_held / chart_bos, with shape_lift."""
    rows = _run_jobs(_singles_job, len(readings), procs, chart_ctx=ctx, chart_R=readings)
    df = pd.DataFrame(rows)
    log(f'  chart singles: {len(df):,} rows from {len(readings)} readings')
    return shape_lift(df)


def param_curves(ctx, cat: pd.DataFrame, edges_p: dict, procs: int = 1, log=print) -> pd.DataFrame:
    """Per pattern, frame and break level, the break rows by quintile of each of the seven quintile parameters (that
    pattern's own A quintiles, values at the break), kind chart_param: g.full per split on both grids."""
    jobs = []
    b = cat[(cat['near'] == 0) & cat['event'].isin(['break up', 'break down'])]
    for (key, pat, evn), g in b.groupby(['frame', 'pattern', 'event'], sort=True):
        ep = edges_p.get(key, {}).get(pat, {})
        tf, fr = key.split(':')
        base = f'{tf}:CHART.{fr}.{pat}'
        rows = g['event_row'].to_numpy(np.int64)
        for nm in PARAM_Q:
            e = ep.get(nm)
            if not e:
                continue
            q = heat.bucket(g[nm].to_numpy(float), e)
            for c in range(5):
                idx = np.unique(rows[q == c])
                if len(idx):
                    jobs.append((f'{base}={evn} & {base}.p.{nm}={Q_LEVELS[c]}',
                                 {'frame': key, 'pattern': pat, 'event': evn, 'param': nm, 'q': Q_LEVELS[c], 'textbook': TEXTBOOK.get(pat, KTEXTBOOK.get(pat, 0)),
                                  'source': 'chart'}, idx))
    rows = _run_jobs(_curve_job, len(jobs), procs, chart_ctx=ctx, chart_pc=jobs)
    log(f'  chart parameter curves: {len(rows):,} rows from {len(jobs):,} quintile cells')
    return pd.DataFrame(rows)


def anatomy(inst: dict, cat: pd.DataFrame, meta: dict, days: dict) -> pd.DataFrame:
    """Per pattern, frame and split (by the instance's start row): instances (and distinct, near misses) per day, the
    share that broke up / down, failed, reached the target and the half target, expired; tbi share (decided breaks)
    minus the mean p_rw; median span and height (ATR) at the instance's own value moment; the timeframe's stale share."""
    out = []
    t0, n = inst['_mu']['t0'], inst['_mu']['n']
    brk = cat[cat['event'].isin(['break up', 'break down']) & (cat['near'] == 0)]
    for key in [f'{k}m:{fr}' for k, fr, r in frames() if f'{k}m:{fr}' in inst]:
        T = inst[key]
        fb = inst['_fb'][key.split(':')[0]]
        rows = np.where(T['start'].to_numpy() >= 0, fb['row'][np.clip(T['start'].to_numpy(), 0, max(fb['nb'] - 1, 0))], -1)
        sp, _ = _split_end(rows, t0, n)
        which, _ = _ref_moment(T)
        pv = _param_values(T, which) if len(T) else {'height': np.zeros(0), 'span': np.zeros(0)}
        bk = brk[brk['frame'] == key]
        for p in (KPATTERNS if key.endswith(':K') else PATTERNS):
            for si, s in enumerate(('A', 'B')):
                sel = (T['pattern'].to_numpy() == p) & (sp == si)
                nn = sel & (T['near'].to_numpy() == 0)
                k_ = int(nn.sum())
                d = days.get(s) or 1.0
                br, dr = T['brk'].to_numpy(), T['dir'].to_numpy()
                why = T['why'].to_numpy()
                b2 = bk[(bk['pattern'] == p) & (bk['split'] == s)]
                dec = b2['tbi'].dropna()
                sh = lambda m: float(m[nn].mean()) if k_ else None
                out.append({'frame': key, 'pattern': p, 'split': s, 'instances': k_, 'distinct': int((nn & (T['cont'].to_numpy() == 0)).sum()),
                            'near_misses': int((sel & ~(T['near'].to_numpy() == 0)).sum()), 'per_day': k_ / d,
                            'distinct_per_day': int((nn & (T['cont'].to_numpy() == 0)).sum()) / d,
                            'broke_up': sh((br >= 0) & (dr > 0)), 'broke_down': sh((br >= 0) & (dr < 0)), 'failed': sh(T['fail'].to_numpy() >= 0),
                            'target': sh(T['tgt_bar'].to_numpy() >= 0), 'half_target': sh(T['half_bar'].to_numpy() >= 0),
                            'expired': sh((br < 0) & np.isin(why, [W_EXPIRE, W_APEX])), 'breaks': int(len(b2)), 'tbi_decided': int(len(dec)),
                            'tbi_share': float(dec.mean()) if len(dec) else None, 'mean_p_rw': float(b2['p_rw'].mean()) if len(b2) else None,
                            'tbi_minus_p_rw': float(dec.mean() - b2.loc[dec.index, 'p_rw'].mean()) if len(dec) else None,
                            'median_span': float(np.nanmedian(pv['span'][nn])) if k_ and np.isfinite(pv['span'][nn]).any() else None,
                            'median_height_atr': float(np.nanmedian(pv['height'][nn])) if k_ and np.isfinite(pv['height'][nn]).any() else None,
                            'textbook': TEXTBOOK.get(p, KTEXTBOOK.get(p, 0)), 'hidden_events': meta['hidden'].get(f'{key.split(":")[0]}:CHART.{key.split(":")[1]}.{p}'),
                            'stale_share': (meta['stale_share'].get(key.split(':')[0]) or {}).get(s)})
    return pd.DataFrame(out)


def losers(cat: pd.DataFrame) -> pd.DataFrame:
    """Per pattern, frame, event level (every level) and split at 15, 60 and 240 minutes: the instances that went the
    wrong way (sign of the move against the event's direction: the break's after a break, the textbook's at formed)
    against those that went right: counts, parameter medians, mean p_rw, and how the losers ended within the horizon
    (failure, retest, target; stall = neither failure nor target)."""
    c = cat[(cat['near'] == 0) & (cat['split'] != '')]
    if not len(c):
        return pd.DataFrame()
    de = np.where(c['dir'].to_numpy() != 0, c['dir'].to_numpy(), np.where(c['event'].to_numpy() == 'formed', c['textbook'].to_numpy(), 0))
    c = c[de != 0].assign(d_ev=de[de != 0])
    keys = ['frame', 'pattern', 'event', 'split', 'side']
    out = []
    for H in (15, 60, 240):
        col = f'sg{H}'
        if col not in c:
            continue
        s = np.sign(c[col].to_numpy() * c['d_ev'].to_numpy())
        r = c['event_row'].to_numpy()
        x = {'side': np.where(s > 0, 'right', 'wrong')}
        for nm, cl in (('failure', 'fail_row'), ('retest', 'retest_row'), ('target', 'tgt_row')):
            b = c[cl].to_numpy()
            x[f'ended_{nm}'] = ((b > r) if nm != 'target' else (b >= r)) & (b <= r + H)
        x['ended_stall'] = ~x['ended_failure'] & ~x['ended_target']
        g = c.assign(**x)[s != 0]
        agg = {'n': ('p_rw', 'size'), 'mean_p_rw': ('p_rw', 'mean')}
        agg.update({f'median_{nm}': (nm, 'median') for nm in PARAMS})
        agg.update({f'ended_{nm}': (f'ended_{nm}', 'mean') for nm in ('failure', 'retest', 'target', 'stall')})
        t = g.groupby(keys, sort=True).agg(**agg).reset_index()
        t.insert(4, 'h', H)
        out.append(t)
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


# --------------------------------------------------------------------------------------------- the chart pair scan
class _Cols:
    """ctx.C's columns followed by the chart codes (a column index past HM2's reads the chart matrix): no copy."""

    def __init__(self, a, b, n0):
        self.a, self.b, self.n0 = a, b, n0

    def __getitem__(self, key):
        r, j = key
        j = int(j)
        return self.a[r, j] if j < self.n0 else self.b[r, j - self.n0]


class _Tcat:
    """ctx.T's totals followed by the chart totals, addressed by the joined offsets: no copy."""

    def __init__(self, a, b, off0):
        self.a, self.b, self.off0 = a, b, int(off0)

    def __getitem__(self, key):
        r, sl = key
        if sl.start >= self.off0:
            return self.b[r, sl.start - self.off0:sl.stop - self.off0]
        return self.a[r, sl]


class ChartView:
    """HM2's series context seen with the chart's compact readings appended (reading ids len(ctx.readings) ...): the
    HM2 kernel reads codes, totals and part effects through it; everything else (minutes, grids, entries, weights,
    bases) is ctx's own. Nothing is written to ctx: the caches and extra_readings HM2's re-measure sets land here."""

    def __init__(self, ctx, comp: list, Cc: np.ndarray, Tc: np.ndarray, toffc: np.ndarray, parts: dict, skip: list, work: list, nonneu: list):
        object.__setattr__(self, '_ctx', ctx)
        n0 = len(ctx.readings)
        self.n0 = n0
        self.readings = list(ctx.readings) + list(comp)
        self.names = list(ctx.names) + [R['name'] for R in comp]
        self.fam = list(ctx.fam) + ['chart'] * len(comp)
        self.families = sorted(set(self.fam))
        self.byname = dict(ctx.byname)
        for i, R in enumerate(comp):
            self.byname[R['name']] = n0 + i
        self.L = list(ctx.L) + [len(R['levels']) for R in comp]
        self.skip = list(ctx.skip) + list(skip)
        self.work = list(ctx.work) + list(work)
        self.nonneu = list(ctx.nonneu) + list(nonneu)
        self.toff = np.r_[ctx.toff, ctx.toff[-1] + toffc[1:]].astype(np.int64)
        self.C = _Cols(ctx.C, Cc, n0)
        self.T = _Tcat(ctx.T, Tc, ctx.toff[-1])
        self.parts = {k: list(ctx.parts[k]) + list(parts[k]) for k in ('odds', 't', 'n')}
        pv = getattr(ctx, 'prov', None)
        self.prov = None if pv is None else {'inpack': list(pv['inpack']) + [np.zeros(len(R['levels']), bool) for R in comp], 'stored': pv['stored']}
        self.lp = {}
        self.flags = []
        self.paths = []
        self.extra_readings = {}

    def __getattr__(self, k):
        return getattr(object.__getattribute__(self, '_ctx'), k)


class _PartsView:
    def __init__(self, ctx, L, T, toff):
        self._ctx, self.L, self.T, self.toff = ctx, L, T, toff

    def __getattr__(self, k):
        return getattr(self.__dict__['_ctx'], k)


def chart_view(ctx, comp: list) -> ChartView:
    """The compact readings' code matrix on ctx's entries (heat_hm2.code_matrix), their totals (reading_totals on that
    matrix with ctx's weights), neutral info and part effects, as a ChartView over ctx."""
    from oracle import heat_hm2 as h2
    comp = [dict(R, family='chart') for R in comp]
    Cc = h2.code_matrix(comp, ctx.rows)
    Lc = [len(R['levels']) for R in comp]
    Tc, toffc = h2.reading_totals(Cc, {'day': ctx.day}, ctx.W, ctx.ND, Lc)
    skip, work, nonneu = [], [], []
    for j, R in enumerate(comp):
        s, w, nn = h2._neutral_info(R['levels'], Cc[:, j])
        skip.append(s)
        work.append(w)
        nonneu.append(nn)
    parts = h2.part_effects(_PartsView(ctx, Lc, Tc, toffc))
    return ChartView(ctx, comp, Cc, Tc, toffc, parts, skip, work, nonneu)


def chart_pairs(view: ChartView, part=(0, 1), max_pairs: int = None, seed: int = 0) -> np.ndarray:
    """(pair index, ia, ib), ia < ib: each compact reading with every HM2 reading, then with the compact readings of
    the other frames (never its own frame: same base, nor a frame a copy of it stands for). --part i/S keeps index % S
    == i; max_pairs: a seeded subset."""
    from oracle import heat_hm2 as h2
    n0, nr = view.n0, len(view.readings)
    P = []
    for c in range(n0, nr):
        P.append(np.stack([np.arange(n0, dtype=np.int64), np.full(n0, c, np.int64)], 1))
    ov = h2.series_overlap(view.readings[n0:])                   # one base, or a copy's base (merge_aliases' alias_bases)
    cc = [(n0 + a, n0 + b) for a in range(nr - n0) for b in range(a + 1, nr - n0) if not ov[a, b]]
    if cc:
        P.append(np.array(cc, np.int64))
    P = np.concatenate(P) if P else np.zeros((0, 2), np.int64)
    pid = np.arange(len(P), dtype=np.int64)
    i, S = part
    sel = pid % S == i
    out = np.concatenate([pid[sel, None], P[sel]], 1)
    if max_pairs is not None and len(out) > max_pairs:
        out = out[np.sort(np.random.default_rng([20261112, seed]).choice(len(out), max_pairs, replace=False))]
    return out


def scan(view: ChartView, procs: int, writer, part=(0, 1), max_pairs: int = None, seed: int = 0, log=print) -> tuple:
    """The chart pairs through HM2's pair kernel, statistics, summary counts and candidates (heat_hm2._pair_batch in
    forked workers with the view as the context). Returns (summary counts {'pair', 'triple'}, Candidates, stats)."""
    from oracle import heat_hm2 as h2
    pairs = chart_pairs(view, part, max_pairs, seed)
    jobs = [(b, lo, min(lo + h2.BATCH, len(pairs))) for b, lo in enumerate(range(0, len(pairs), h2.BATCH))]
    summ = {'pair': h2.SummaryCounts(view.families), 'triple': h2.SummaryCounts(view.families)}
    cands = h2.Candidates()
    h2._ctx_on(view, writer, hm2_pairs=pairs)
    try:
        st = h2._merge(h2._imap(h2._pair_batch, jobs, procs), summ, cands, [], log, 'chart pairs', len(jobs))
    finally:
        h2._ctx_off()
    st['pairs'] = int(len(pairs))
    return summ, cands, st


# ------------------------------------------------------------------------------------------------------- the stage
def _read_csv(path: str) -> pd.DataFrame:
    """A table this module wrote (an empty one is written as an empty file)."""
    try:
        return pd.read_csv(path, low_memory=False)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def _examples(inst: dict, cat: pd.DataFrame, real: bool, n_per: int = 1) -> list:
    """Per pattern and frame: on a real coin one winner and one loser from split B (sign of the 60-minute move against
    the break's direction), on a twin one example; each with the frame's bars from 20 bars before the first pivot to 40
    after the break (prices in the coin's price)."""
    out = []
    step = float(inst['_mu']['step']) if inst['_mu'].get('step') else 1.0
    b = cat[(cat['near'] == 0) & cat['event'].isin(['break up', 'break down']) & (cat['split'] == 'B')]
    if 'sg60' not in b:
        return out
    for (key, p), g in b.groupby(['frame', 'pattern'], sort=True):
        fb = inst['_fb'][key.split(':')[0]]
        T = inst[key]
        s = np.sign(g['sg60'].to_numpy() * g['dir'].to_numpy())
        picks = [('winner', g[s > 0]), ('loser', g[s < 0])] if real else [('twin', g[s != 0])]
        for kind, gg in picks:
            if not len(gg):
                continue
            r = gg.iloc[0]
            i = int(r['inst'])
            first = int(T['fb'].iat[i]) if T['fb'].iat[i] >= 0 else int(r['event_bar'])
            lo, hi = max(0, first - 20), min(fb['nb'], int(r['event_bar']) + 41)
            out.append({'frame': key, 'pattern': p, 'kind': kind, 'instance': r['instance'], 'event': r['event'], 'event_row': int(r['event_row']),
                        'bar0': lo, 'bar0_ms': int(inst['_mu']['t0'] + (fb['row'][lo] + 1 - fb['k']) * MIN),
                        'o': (fb['o'][lo:hi] * step).tolist(), 'h': (fb['h'][lo:hi] * step).tolist(), 'l': (fb['l'][lo:hi] * step).tolist(),
                        'c': (fb['c'][lo:hi] * step).tolist(),
                        'pivots': [[int(T[f'piv{u}_bar'].iat[i]), float(T[f'piv{u}_px'].iat[i] * step)] for u in range(1, 6) if T[f'piv{u}_bar'].iat[i] >= 0],
                        'trig': float(T['trig'].iat[i] * step), 'trig_slope': float(T['trig_slope'].iat[i] * step), 'brk': int(T['brk'].iat[i]),
                        'target': float(T['tgtv'].iat[i] * step), 'half_target': float(T['halfv'].iat[i] * step),
                        'invalidation': float(T['failv'].iat[i] * step), 'p_rw': float(T['p_rw'].iat[i]), 'sg60': int(r['sg60'])})
    return out


def live_meta(meta: dict) -> dict:
    """What levels_at needs from a full run: the frames, constants, parameter edges and price step (schema
    oracle-heat-chart-live-1)."""
    return {'schema': 'oracle-heat-chart-live-1', 'frames': meta['frames'], 'constants': meta['constants'], 'edges': meta['edges'],
            'price_step': meta['price_step'], 'window': LIVE_WINDOW, 'readings': meta['readings']}


def stage(ctx, out: str, procs: int = 1, log=print, part=(0, 1), parts_dirs=(), shards: str = '', max_pairs: int = None) -> dict:
    """Route A's entry (heat_hm2.run_series calls it after HM2's meta.json, only where HM2's re-measure ran) and route
    B's second half: pattern_readings on ctx's own minutes, singles (with shape_lift), the catalogue (frame by frame),
    parameter curves, anatomy, losers, the chart pair scan through a ChartView, HM2's re-measure of the chart
    candidates, examples. Writes into out: meta.json (schema oracle-heat-chart-1), chart_heat.csv.gz (with its
    table_sha256), chart_summary_counts.json, chart_candidates.csv.gz, chart_near_copies.csv.gz, anatomy.csv.gz,
    losers.csv.gz, instances.csv.gz (the full catalogue), examples.json, live_meta.json, the chart cell shards (real
    coins) under <out>/shards. With part = (i, S), S > 1: only the scan of that part (summary counts and candidates);
    parts_dirs: the finish, which merges the parts' scans. Never writes to ctx (ctx.extra_readings and caches as found)."""
    from oracle import heat_hm2 as h2
    _refuse_doge(getattr(ctx, 'asset', ''), getattr(ctx, 'label', ''))
    os.makedirs(out, exist_ok=True)
    t_start, sec = time.time(), {}
    tick = lambda k, t: sec.__setitem__(k, round(time.time() - t, 1))
    keep = {k: ctx.__dict__.get(k, None) for k in ('extra_readings', '_icache')}
    procs = procs or min(4, os.cpu_count() or 1)
    pi, S = part
    t = time.time()
    R, edges, inst, pmeta = pattern_readings(ctx.m, log=log)
    comp = compact(R)
    # (review fix; design item 9) HM2's copy merge, unchanged, on the compact readings' own A entries
    comp, comp_aliases = h2.merge_aliases([dict(x) for x in comp], ctx.rows[:int((ctx.split == 0).sum())], log=log)
    tick('readings', t)
    log(f'{ctx.label}: {len(R)} chart readings, {len(comp)} compact ({sec["readings"]}s, peak {h2._rss_mb()} MB)')
    t = time.time()
    view = chart_view(ctx, comp)
    writer = h2.ShardWriter(shards or os.path.join(out, 'shards'), ctx.real)
    summ, cands = None, h2.Candidates()
    st_pairs = {}
    if parts_dirs:
        summ = {'pair': h2.SummaryCounts(view.families), 'triple': h2.SummaryCounts(view.families)}
        for d in parts_dirs:
            with open(os.path.join(d, 'chart_summary_counts.json')) as f:
                summ['pair'].merge(h2.SummaryCounts.from_json(json.load(f)['pair']))
            cands.add(_read_csv(os.path.join(d, 'chart_candidates.csv.gz')))
        st_pairs = {'merged_parts': list(parts_dirs)}
    else:
        summ, cands, st_pairs = scan(view, procs, writer, part, max_pairs, log=log)
    tick('pairs', t)
    with open(os.path.join(out, 'chart_summary_counts.json'), 'w') as f:
        json.dump({'schema': 'oracle-heat-chart-summary-1', 'label': ctx.label, 'twin': ctx.twin, 'part': [pi, S], 'pair': summ['pair'].to_json()},
                  f, allow_nan=False)
    h2._write_csv(cands.frame(), os.path.join(out, 'chart_candidates.csv.gz'))
    meta = {'schema': 'oracle-heat-chart-1', 'asset': getattr(ctx, 'asset', None), 'label': ctx.label, 'twin': ctx.twin, 'real': ctx.real,
            'part': [pi, S], 'pairs': st_pairs, 'compact': [x['name'] for x in comp], 'compact_aliases': comp_aliases}
    if S > 1 and not parts_dirs:
        meta.update(seconds=sec, seconds_total=round(time.time() - t_start, 1), peak_rss_mb=h2._rss_mb())
        with open(os.path.join(out, 'meta.json'), 'w') as f:
            json.dump(h2._clean(meta), f, indent=1, allow_nan=False)
        return meta
    t = time.time()
    rm, jac = h2.remeasure(view, cands.frame(), (), procs, log=log)
    rm = rm.frame()
    if len(rm):
        rm = rm[rm['kind'] != 'baseline'].reset_index(drop=True)          # HM2's own baseline rows: not repeated here
    tick('remeasure', t)
    t = time.time()
    sg = singles(ctx, R, procs, log)
    tick('singles', t)
    t = time.time()
    cpath = os.path.join(out, 'instances.csv.gz')
    cat = catalogue(inst, ctx.lab, ctx.lab240, path=cpath, label=ctx.label)
    tick('catalogue', t)
    log(f'  catalogue: {len(cat):,} rows ({os.path.getsize(cpath) / 1e6:.1f} MB gzip, {sec["catalogue"]}s)')
    t = time.time()
    pc = param_curves(ctx, cat, inst['_edges_p'], procs, log)
    tick('param_curves', t)
    t = time.time()
    days = {s: float(ctx.g.sp[s].ndays) for s in ('A', 'B')}
    an = anatomy(inst, cat, pmeta, days)
    lo = losers(cat)
    an.insert(0, 'coin', ctx.label)
    if len(lo):
        lo.insert(0, 'coin', ctx.label)
    h2._write_csv(an, os.path.join(out, 'anatomy.csv.gz'))
    h2._write_csv(lo, os.path.join(out, 'losers.csv.gz'))
    h2._write_csv(jac, os.path.join(out, 'chart_near_copies.csv.gz'))
    ex = _examples(inst, cat, ctx.real)
    with open(os.path.join(out, 'examples.json'), 'w') as f:
        json.dump(h2._clean({'label': ctx.label, 'examples': ex}), f, allow_nan=False)
    tick('tables', t)
    heat_df = pd.concat([x for x in (sg, pc, rm) if x is not None and len(x)], ignore_index=True) if any(len(x) for x in (sg, pc, rm)) else pd.DataFrame()
    if len(heat_df):
        heat_df.insert(0, 'coin', ctx.label)
    sha = h2._write_csv(heat_df, os.path.join(out, 'chart_heat.csv.gz'))
    lm = live_meta(pmeta)
    with open(os.path.join(out, 'live_meta.json'), 'w') as f:
        json.dump(h2._clean(lm), f, allow_nan=False)
    fam = {}
    if len(heat_df):
        ok = (heat_df['n'] >= heat.MIN_EVENTS)
        for (kd, hh, sp), g in heat_df[ok].groupby(['kind', 'h', 'split']):
            fam.setdefault(kd, {}).setdefault(str(hh), {})[sp] = int(len(g))
    meta.update({'splits': {s: [str(pd.Timestamp(a, unit='ms')), str(pd.Timestamp(b, unit='ms'))] for s, (a, b) in heat.SPLITS.items()},
                 'frames': pmeta['frames'], 'constants': pmeta['constants'], 'readings': pmeta['readings'], 'sha256': pmeta['sha256'],
                 'edges': pmeta['edges'], 'edges_by_pattern': pmeta['edges_by_pattern'], 'counts': pmeta['counts'], 'hidden': pmeta['hidden'],
                 'collisions': pmeta['collisions'], 'stale_share': pmeta['stale_share'], 'price_step': pmeta['price_step'],
                 'rows': {k: int(v) for k, v in (heat_df['kind'].value_counts().items() if len(heat_df) else [])},
                 'family_rows_with_n': fam, 'catalogue_rows': int(len(cat)), 'catalogue_bytes': int(os.path.getsize(cpath)), 'examples': len(ex),
                 'table_sha256': sha, 'seconds_frames': pmeta['seconds'], 'seconds': sec, 'seconds_total': round(time.time() - t_start, 1),
                 'peak_rss_mb': h2._rss_mb()})
    with open(os.path.join(out, 'meta.json'), 'w') as f:
        json.dump(h2._clean(meta), f, indent=1, allow_nan=False)
    for k, v in keep.items():                                   # ctx as HM2 left it (the stage writes only to the view)
        if v is None:
            ctx.__dict__.pop(k, None)
        elif ctx.__dict__.get(k) is not v:
            ctx.__dict__[k] = v
    log(f'{ctx.label}: chart stage done in {meta["seconds_total"]}s, peak {meta["peak_rss_mb"]} MB')
    return meta


def run_series(asset: str, csv: str, out: str, twin: int = 0, procs: int = 0, part=(0, 1), parts_dirs=(), shards: str = '', hm1_packs=(),
               hm1_pairs: str = '', log=print, **kw) -> dict:
    """Route B: HM2's base for the series (heat_hm2.base: the same minutes, twin, readings, entries and code matrix as
    the HM2 job), the provenance when HM1's packs are given, then stage()."""
    from oracle import heat_hm2 as h2
    _refuse_doge(asset, csv)
    ctx = h2.base(asset, csv, twin=twin, log=log, **{k: v for k, v in kw.items() if k in ('other_csvs', 'perp_csv', 'fund_csv', 'oi_csv', 'cal_csv',
                                                                                          'dom', 'found', 'main_meta', 'other_metas', 'xdata')})
    if hm1_packs or hm1_pairs:
        ctx.prov = h2.provenance(ctx, h2.load_hm1(hm1_packs, hm1_pairs))
    return stage(ctx, out, procs or min(4, os.cpu_count() or 1), log, part, parts_dirs, shards)


def bench(asset: str, csv: str, out: str, n_pairs: int = 5000, procs: int = 0, log=print, **kw) -> dict:
    """BTC: HM2's base, pattern_readings, singles, the catalogue and n_pairs random chart pairs. Prints and writes
    (bench.json) minutes per stage, instances per pattern and frame (distinct, cont, near misses), ms per pair, peak
    RSS, catalogue rows and size, the stale share per timeframe and split and the projected stage minutes."""
    from oracle import heat_hm2 as h2
    _refuse_doge(asset, csv)
    os.makedirs(out, exist_ok=True)
    procs = procs or min(4, os.cpu_count() or 1)
    sec = {}
    t = time.time()
    ctx = h2.base(asset, csv, log=log, **{k: v for k, v in kw.items() if k in ('other_csvs', 'perp_csv', 'fund_csv', 'oi_csv', 'cal_csv', 'dom', 'found',
                                                                              'main_meta', 'twin', 'other_metas', 'xdata')})
    sec['base'] = round(time.time() - t, 1)
    t = time.time()
    R, edges, inst, pmeta = pattern_readings(ctx.m, log=log)
    sec['readings'] = round(time.time() - t, 1)
    t = time.time()
    sg = singles(ctx, R, procs, log)
    sec['singles'] = round(time.time() - t, 1)
    t = time.time()
    cpath = os.path.join(out, 'instances.csv.gz')
    cat = catalogue(inst, ctx.lab, ctx.lab240, path=cpath, label=ctx.label)
    sec['catalogue'] = round(time.time() - t, 1)
    t = time.time()
    view = chart_view(ctx, compact(R))
    total = len(chart_pairs(view))
    summ, cands, st = scan(view, procs, h2.ShardWriter(os.path.join(out, 'shards'), True), max_pairs=n_pairs, seed=1, log=log)
    sec['pairs'] = round(time.time() - t, 1)
    ms_pair = 1000.0 * sec['pairs'] / max(st['pairs'], 1)
    proj = (sec['readings'] + sec['singles'] + sec['catalogue'] + ms_pair * total / 1000.0) / 60.0 + 10.0     # + curves, re-measure, writes
    res = {'schema': 'oracle-heat-chart-bench-1', 'asset': asset, 'seconds': sec, 'chart_readings': len(R), 'pairs_total': total, 'pairs_run': st['pairs'],
           'ms_per_pair_wall': round(ms_pair, 3), 'projected_pair_minutes': round(ms_pair * total / 60000.0, 1),
           'projected_stage_minutes': round(proj, 1), 'singles_rows': int(len(sg)), 'catalogue_rows': int(len(cat)),
           'catalogue_mb_gzip': round(os.path.getsize(cpath) / 1e6, 1), 'counts': pmeta['counts'], 'stale_share': pmeta['stale_share'],
           'seconds_frames': pmeta['seconds'], 'peak_rss_mb': h2._rss_mb(), 'procs': procs}
    with open(os.path.join(out, 'bench.json'), 'w') as f:
        json.dump(h2._clean(res), f, indent=1, allow_nan=False)
    log(json.dumps(h2._clean({k: v for k, v in res.items() if k != 'counts'}), indent=1))
    return res


# ---------------------------------------------------------------------------------------------------- the live window
def window_readings(m: dict, step=None, edges: dict = None, window: int = LIVE_WINDOW, tfs=None, want: set = None) -> dict:
    """The chart readings from the last `window` bars of each timeframe of minutes m (a heat_live.grid dict: UTC
    midnight aligned), with the full run's price step and parameter edges: the same detectors on bars s .. nb - 1
    (the gap mask from heat_live.STALE_BACK bars before s). Returns {k: {'s': first bar, 'nb': bars, 'readings': [...]}};
    a reading's codes[j] is bar s + j of the minutes' k-minute grid."""
    mu = units(m, step=step) if step else dict(m)
    out = {}
    for k in (tfs or sorted(set(PAT_TFS) | set(K_TFS))):
        nb_all = mu['n'] // k
        s = max(0, nb_all - int(window))
        run = run_tf(mu, k, s, nb_all, want=want)
        rr, info = tf_readings(run, edges)
        out[k] = {'s': s, 'nb': nb_all, 'readings': rr}
    return out


def levels_at(win, meta: dict, names=None, window: int = LIVE_WINDOW) -> dict:
    """{reading name: level at the last closed bar of its timeframe (None = NA)} from a window of minutes (a DataFrame
    of ts, o, h, l, c, v rows or a heat_live.grid dict) and a live meta (live_meta() or a chart meta.json)."""
    from oracle import heat_live
    m = heat_live.grid(win) if isinstance(win, pd.DataFrame) else win
    want_tf = None
    if names:
        want_tf = sorted({int(n.split('m:', 1)[0]) for n in names})
    W = window_readings(m, meta.get('price_step'), meta.get('edges'), window, tfs=want_tf)
    out = {}
    for k, x in W.items():
        for R in x['readings']:
            if names and R['name'] not in names:
                continue
            c = int(R['codes'][-1]) if len(R['codes']) else -1
            out[R['name']] = R['levels'][c] if c >= 0 else None
    return out


# ------------------------------------------------------------------------------------------------------------- league
def league(inputs: str, hm2_dir: str, out: str, stamp: str = '', top: int = 40) -> dict:
    """The chart league from every series' patterns/ files under inputs (<COIN>[-twinN]/patterns/): the chance table
    (anatomy, real against the twins' median and range), the singles lists per coin and horizon (top by B heat and by
    share over base at 0.2 windows a day or more, at most 3 rows per pattern), with marks as columns (hot on A,
    replicated on B, above the twins' max). Writes chart_all.csv.gz, chart_summary.json (oracle-heat-chart-league-1)
    and chart_league.md."""
    import glob
    from oracle import heat_hm2 as h2
    os.makedirs(out, exist_ok=True)
    metas = sorted(glob.glob(os.path.join(inputs, '*', 'patterns', 'meta.json')))
    ser = []
    for p in metas:
        with open(p) as f:
            mt = json.load(f)
        if mt.get('part', [0, 1])[1] > 1 or 'table_sha256' not in mt:
            continue
        _refuse_doge(mt.get('label'), p)
        ser.append((mt, os.path.dirname(p)))
    if not ser:
        raise SystemExit(f'{inputs}: no chart series')
    coins = sorted({m['asset'] for m, _ in ser if m.get('asset')})
    an = pd.concat([_read_csv(os.path.join(d, 'anatomy.csv.gz')).assign(asset=m['asset'], twin=m['twin']) for m, d in ser], ignore_index=True)
    rows = []
    for m, d in ser:
        x = _read_csv(os.path.join(d, 'chart_heat.csv.gz'))
        if len(x):
            rows.append(x.assign(asset=m['asset'], twin=m['twin']))
    H = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    # chance table: per coin, frame, pattern and split, the real coin against its twins
    chance = []
    for (a, fr, p, s), g in an.groupby(['asset', 'frame', 'pattern', 'split']):
        r, tw = g[g['twin'] == 0], g[g['twin'] > 0]
        if not len(r):
            continue
        r = r.iloc[0]
        row = {'coin': a, 'frame': fr, 'pattern': p, 'split': s}
        for c in ('per_day', 'distinct_per_day', 'broke_up', 'broke_down', 'failed', 'target', 'tbi_minus_p_rw', 'stale_share'):
            row[c] = r[c]
            v = tw[c].dropna()
            row[f'{c}_twin_med'], row[f'{c}_twin_lo'], row[f'{c}_twin_hi'] = (float(v.median()), float(v.min()), float(v.max())) if len(v) else (None,) * 3
        chance.append(row)
    chance = pd.DataFrame(chance)
    # singles: A and B side by side, marks as columns
    lists, allrows = {}, pd.DataFrame()
    if len(H):
        S = H[H['kind'].isin(['chart', 'chart_held', 'chart_param', 'xstate', 'xonset'])]
        key = ['asset', 'twin', 'kind', 'key', 'h']
        A = S[S['split'] == 'A'].set_index(key)
        B = S[S['split'] == 'B'].set_index(key)
        J = A[['n', 'days', 'edge_p', 't_p', 'wd', 'p_up', 'p_dn']].join(B[['n', 'days', 'edge_p', 't_p', 'wd', 'p_up', 'p_dn']], lsuffix='_A', rsuffix='_B',
                                                                           how='outer').reset_index()
        d = np.sign(J['edge_p_A'].fillna(0.0))
        J['dir'] = d
        J['odds_A'], J['odds_B'] = 100.0 * J['edge_p_A'], 100.0 * J['edge_p_B']
        J['heat_B'] = J['wd_B'] * J['odds_B'] * d
        J['share_B'] = 100.0 * np.where(d >= 0, J['p_up_B'], J['p_dn_B'])
        J['floors'] = (J['n_A'] >= heat.MIN_EVENTS) & (J['days_A'] >= heat.MIN_DAYS_A) & (J['n_B'] >= heat.MIN_EVENTS) & (J['days_B'] >= heat.MIN_DAYS_B)
        J['hot_A'] = J['t_p_A'].abs() >= 3
        J['rep_B'] = (J['t_p_B'] * d) >= 2
        tmax = J[J['twin'] > 0].groupby(['asset', 'kind', 'key', 'h'])['heat_B'].max().rename('twin_max_heat_B')
        J = J.join(tmax, on=['asset', 'kind', 'key', 'h'])
        J['above_twin_max'] = J['heat_B'] > J['twin_max_heat_B']
        allrows = J
        R0 = J[(J['twin'] == 0) & J['floors']]
        for (a, hh), g in R0.groupby(['asset', 'h']):
            g = g.assign(pat=g['key'].str.split('=').str[0])
            best = g.sort_values(['heat_B', 'key'], ascending=[False, True]).groupby('pat').head(3).head(top)
            lists[f'{a}|{hh}'] = best[['kind', 'key', 'odds_A', 'odds_B', 'share_B', 'wd_B', 'heat_B', 'twin_max_heat_B', 'above_twin_max', 'hot_A',
                                       'rep_B']].to_dict('records')
    h2._write_csv(allrows, os.path.join(out, 'chart_all.csv.gz'))
    h2._write_csv(chance, os.path.join(out, 'chart_chance.csv.gz'))
    summary = {'schema': 'oracle-heat-chart-league-1', 'stamp': stamp, 'coins': coins, 'series': [m['label'] for m, _ in ser],
               'rows': int(len(allrows)), 'lists': lists, 'hm2_dir': hm2_dir}
    with open(os.path.join(out, 'chart_summary.json'), 'w') as f:
        json.dump(h2._clean(summary), f, indent=1, allow_nan=False)
    md = [f'# Chart patterns (Part 4)', '', stamp, '', f'Series: {", ".join(summary["series"])}.', '', '## Chance table', '',
          'Instances per day on each split, the real coin against its twins (median, range).', '',
          '| coin | frame | pattern | split | per day | twins | tbi - p_rw |', '|---|---|---|---|---|---|---|']
    for r in chance.sort_values(['coin', 'frame', 'pattern', 'split']).itertuples() if len(chance) else []:
        tw = '' if r.per_day_twin_med is None or (isinstance(r.per_day_twin_med, float) and not math.isfinite(r.per_day_twin_med)) else \
            f'{r.per_day_twin_med:.3g} ({r.per_day_twin_lo:.3g}-{r.per_day_twin_hi:.3g})'
        md.append(f'| {r.coin} | {r.frame} | {r.pattern} | {r.split} | {r.per_day:.3g} | {tw} | '
                  f'{"" if r.tbi_minus_p_rw is None or not np.isfinite(r.tbi_minus_p_rw) else f"{r.tbi_minus_p_rw:+.3f}"} |')
    md += ['', '## Singles lists (B heat, at most 3 rows per pattern)', '']
    for lk, rr in sorted(lists.items()):
        a, hh = lk.split('|')
        md += [f'### {a}, {hh} minutes', '', '| key | odds A | odds B | windows/day B | heat B | twins max | marks |', '|---|---|---|---|---|---|---|']
        for r in rr:
            mk = ','.join(x for x, f in (('hot', r['hot_A']), ('rep', r['rep_B']), ('>twins', r['above_twin_max'])) if f is True)
            md.append(f'| {r["key"]} | {r["odds_A"]:.2f} | {r["odds_B"]:.2f} | {r["wd_B"]:.3g} | {r["heat_B"]:.3g} | '
                      f'{"" if r["twin_max_heat_B"] is None or not np.isfinite(r["twin_max_heat_B"]) else format(r["twin_max_heat_B"], ".3g")} | {mk} |')
        md.append('')
    with open(os.path.join(out, 'chart_league.md'), 'w') as f:
        f.write('\n'.join(md) + '\n')
    return summary


# --------------------------------------------------------------------------------------------------------------- CLI
def main(argv=None):
    from oracle import heat_hm2 as h2
    ap = argparse.ArgumentParser(prog='oracle.heat_patterns')
    sub = ap.add_subparsers(dest='cmd', required=True)
    c = sub.add_parser('coin')
    h2._inputs(c)
    c.add_argument('--out', required=True)
    c.add_argument('--part', default='0/1')
    c.add_argument('--parts', default='')                         # finish: the --part jobs' out dirs, comma-separated
    c.add_argument('--shards', default='')
    c.add_argument('--hm1-packs', default='')
    c.add_argument('--hm1-pairs', default='')
    b = sub.add_parser('bench')
    h2._inputs(b)
    b.add_argument('--out', required=True)
    b.add_argument('--pairs', type=int, default=5000)
    r = sub.add_parser('readings')
    r.add_argument('--csv', required=True)
    r.add_argument('--asset', default='')
    r.add_argument('--out', required=True)
    r.add_argument('--twin', type=int, default=0)
    lg = sub.add_parser('league')
    lg.add_argument('--inputs', required=True)
    lg.add_argument('--hm2', default='')
    lg.add_argument('--out', required=True)
    lg.add_argument('--stamp', default='')
    a = ap.parse_args(argv)
    if a.cmd in ('coin', 'bench'):
        _refuse_doge(a.asset, a.csv)
        kw = h2._kw(a)
        if a.cmd == 'coin':
            pi, S = (int(x) for x in a.part.split('/'))
            if not 0 <= pi < S:
                raise SystemExit(f'--part {a.part}: want i/S with 0 <= i < S')
            mt = run_series(a.asset, a.csv, a.out, procs=a.procs, part=(pi, S), parts_dirs=[x for x in a.parts.split(',') if x], shards=a.shards,
                            hm1_packs=[x for x in a.hm1_packs.split(',') if x], hm1_pairs=a.hm1_pairs, **kw)
            print(json.dumps({k: v for k, v in mt.items() if k in ('label', 'twin', 'part', 'pairs', 'rows', 'catalogue_rows', 'table_sha256', 'seconds',
                                                                    'seconds_total', 'peak_rss_mb')}, indent=1))
        else:
            bench(a.asset, a.csv, a.out, a.pairs, a.procs, **kw)
    elif a.cmd == 'readings':
        _refuse_doge(a.asset, a.csv)
        os.makedirs(a.out, exist_ok=True)
        m = heat.load_minutes(a.csv)
        if a.twin:
            m = heat.make_twin(m, a.twin)
        R, edges, inst, meta = pattern_readings(m)
        lab = heat.labels(m)
        from oracle import heat_hm2 as h2_
        with h2_.h240():
            lab240 = heat.labels(m)
        cat = catalogue(inst, lab, lab240, path=os.path.join(a.out, 'instances.csv.gz'), label=a.asset or None)
        meta['catalogue_rows'] = int(len(cat))
        with open(os.path.join(a.out, 'meta.json'), 'w') as f:
            json.dump(h2._clean(dict(meta, schema='oracle-heat-chart-readings-1')), f, indent=1, allow_nan=False)
        with open(os.path.join(a.out, 'live_meta.json'), 'w') as f:
            json.dump(h2._clean(live_meta(meta)), f, allow_nan=False)
        np.savez_compressed(os.path.join(a.out, 'codes.npz'), **{R_['name']: R_['codes'] for R_ in R})
    else:
        _refuse_doge(a.inputs, a.out)
        league(a.inputs, a.hm2, a.out, a.stamp)


if __name__ == '__main__':
    main()
