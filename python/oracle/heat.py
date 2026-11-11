"""OR-HM1 heat map on coin price, Amendments 1 and 2 (python/oracle/prereg/OR-HM1.md).

  python3 -m oracle.heat coin   --asset BTC --csv 1m.csv --dom research/btcd_fractal/data --out out/BTC [--twin 1]
  python3 -m oracle.heat league --inputs out --out out/league

Per coin: every TA-Lib signal (python/oracle/heat_vocab.py) on 1m / 5m / 15m / 1h bars, known at the bar's close; entry
at the NEXT minute's open; the move to 5 / 15 / 30 / 60 minutes after the decision. Outputs (aggregates only):
  curve    a reading's value in deciles (state at every bar close)            -> the strip / linear heat map
  single   the bar where a reading ENTERS a zone, flips sign or a pattern fires (an event)
  pair     a trigger event split by the zone of a second reading (relationship curve), with the LIFT over the
           trigger's other events
  triple   a hot pair cell split by a third reading
`--twin N` runs the same pipeline on a no-signal twin of the coin (every minute's move keeps its size and loses its
direction: random sign flips), the chance yardstick for every count in the league.
Never loads a bar at or after HEAT_END (2026-01-01; a file that holds a later minute is refused). NEVER DOGE.
"""
import argparse
import gzip
import hashlib
import json
import math
import os
import time
import zlib

import numpy as np
import pandas as pd

from oracle.common import DAY, DEV_END, MIN, ms

HORIZONS = [1, 5, 15, 30, 60]   # Amendment 3: 1 minute added (does the direction hold for a minute after entry)
HMAX = max(HORIZONS)
TFS = [1, 5, 15, 60]
TOUCH = [10, 25, 50]
HEAT_END = ms('2026-01-01')  # Amendment 2: the heat tables read no minute at or after this (2026 stays unread; well before DEV_END)
assert HEAT_END <= DEV_END
SPLITS = {'A': (ms('2020-01-01'), ms('2025-01-01')), 'B': (ms('2025-01-01'), HEAT_END)}
SEEDS = 8                   # day shifts for the time-of-day control of a single
N_TRIG_PER_TF = 40          # trigger events per timeframe taken into the pair stage (by |t| on A)
N_TRIG_CTX = 10
N_REL_TOP = 60              # hot pair cells taken into the triple stage
MAX_PER_TRIGGER = 3
N_REL_CTX = 500             # relationships whose other levels are also written (for the viewer's curves)
N_REL_WRITE = 150_000       # hot relationships written per coin (the strongest by lift t on A; the count of all is in meta)
MIN_EVENTS = 30
MIN_DAYS_A = 30
MIN_DAYS_B = 20
HOT_P = 0.0027              # two-sided p of abs t = 3 under a normal: the hot bar on A (t distribution, days - 1 df)
REP_P = 0.0228              # one-sided p of t = 2 under a normal: the lift bar on A and the replication bar on B
ROW_CHUNK = 200_000
ZONE_Q = [0.02, 0.10, 0.90, 0.98]
ZONES = ['very low', 'low', 'mid', 'high', 'very high']
CURVE_Q = [0.01, 0.025, 0.05, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 0.95, 0.975, 0.99]   # 16 cells, fine in the tails
NEUTRAL = {'none', 'mid'}   # levels that are not events
STALE = 100                 # bars of a timeframe after a data gap whose readings are not used
STALE_LONG = (14, 500)      # after a gap run longer than 14 bars: 500 bars (the longest normalisation window)
TICK_DEAD = 1.5             # a move of up to one price step is flat for the odds (bid-ask bounce on a coarse tick)
DOM_Z = [-1.5, -0.5, 0.5, 1.5]
DOM_LV = ['strong down', 'down', 'flat', 'up', 'strong up']
SQ2PI = math.sqrt(2 / math.pi)


# ---------------------------------------------------------------------------------------------------------------- data
def load_minutes(path: str, start: int = SPLITS['A'][0], end: int = HEAT_END, strict: bool = True) -> dict:
    """Complete 1-minute grid from the first UTC midnight on or after the data start (>= start) to end (exclusive,
    never past HEAT_END). A missing minute or a row with an empty price is a gap: forward-filled, volume 0.
    strict: a file that holds any minute at or after HEAT_END is refused (the workflow cuts the file before this
    process sees it); strict=False only drops those rows."""
    end = min(int(end), HEAT_END)
    df = pd.read_csv(path)
    late = int((df['ts'] >= HEAT_END).sum())
    if late and strict:
        raise SystemExit(f'{path}: {late:,} rows at or after {pd.Timestamp(HEAT_END, unit="ms")}: the heat tables stop there; cut the file first')
    df = df[(df['ts'] >= start) & (df['ts'] < end)]
    px = df[['o', 'h', 'l', 'c']].to_numpy(float)
    with np.errstate(invalid='ignore'):
        bad = ~np.isfinite(px).all(1) | ~np.isfinite(df['v'].to_numpy(float)) | (px <= 0).any(1) | (px[:, 1] < px.max(1)) | (px[:, 2] > px.min(1))
    df = df[~bad].drop_duplicates('ts').sort_values('ts')         # a broken row becomes a gap
    if df.empty:
        raise SystemExit(f'{path}: no rows in range')
    t0 = int(-(-int(df['ts'].iloc[0]) // DAY) * DAY)
    df = df[df['ts'] >= t0]
    n = int((end - t0) // MIN)
    n -= n % 1440
    pos = ((df['ts'].to_numpy() - t0) // MIN).astype(np.int64)
    keep = pos < n
    pos, df = pos[keep], df[keep]
    gap = np.ones(n, bool)
    gap[pos] = False
    c = np.full(n, np.nan)
    c[pos] = df['c'].to_numpy(float)
    c = pd.Series(c).ffill().bfill().to_numpy()
    o, h, l = c.copy(), c.copy(), c.copy()
    o[pos], h[pos], l[pos] = df['o'].to_numpy(float), df['h'].to_numpy(float), df['l'].to_numpy(float)
    v = np.zeros(n)
    v[pos] = df['v'].fillna(0).to_numpy(float)
    tb = None
    if 'tb' in df.columns:
        tb = np.zeros(n)
        tb[pos] = df['tb'].fillna(0).to_numpy(float)
    return {'t0': t0, 'n': n, 'o': o, 'h': h, 'l': l, 'c': c, 'v': v, 'tb': tb, 'gap': gap, 'tick': tick_bps(c, gap), 'bad_rows': int(bad.sum())}


def tick_bps(c: np.ndarray, gap: np.ndarray) -> np.ndarray:
    """The coin's price step at each minute in bps of price: the smallest non-zero close-to-close change of the last
    day. A measured effect below one step is rounding, not a move anyone can trade."""
    d = np.abs(np.diff(c, prepend=c[0]))
    d[(d <= 0) | gap] = np.nan
    step = pd.Series(d).rolling(1440, min_periods=1).min().ffill().bfill().fillna(0).to_numpy()
    return (step / c * 1e4).astype(np.float32)


def tick_units(m: dict, a_end: int = None) -> dict:
    """The bars in whole price steps when the coin trades on a tick grid (every reading is scale-free), so ties inside
    TA-Lib are exact and do not depend on float rounding. The step, and whether there is a grid at all, come from the
    rows before a_end (split A) only, so no later row can change a build-years reading; later rows on a finer grid
    refine the unit by powers of ten (the build-years values stay whole). A series that is not on a grid is returned
    as is. out['step'] is the unit."""
    n = m['n'] if a_end is None else max(3, min(int(a_end), m['n']))
    u = np.unique(m['c'][:n][~m['gap'][:n]])
    if len(u) < 3:
        return m
    step = 10.0 ** np.floor(np.log10(np.diff(u).min()) + 1e-6)
    if u.max() / step >= 2.0 ** 50:                 # a smallest gap of float-noise size is not a grid
        return m
    on = lambda a, st: bool(np.abs(a / st - np.round(a / st)).max() <= 1e-4)
    if not all(on(m[x][:n], step) for x in ('o', 'h', 'l', 'c')):
        return m
    for _ in range(6):
        if all(on(m[x], step) for x in ('o', 'h', 'l', 'c')):
            break
        step /= 10.0
    out = dict(m)
    for x in ('o', 'h', 'l', 'c'):
        out[x] = np.round(m[x] / step)
    out['step'] = float(step)
    return out


def make_twin(m: dict, seed: int) -> dict:
    """The coin with every minute's direction replaced by a coin flip: each bar keeps its size, range, volume and place
    in time (so volatility clustering, the daily cycle and fat tails are the real ones) but the path has no memory."""
    rng = np.random.default_rng([20261111, int(seed)])
    n, c = m['n'], m['c']
    prev = np.r_[c[0], c[:-1]]
    s = rng.choice(np.array([-1.0, 1.0]), n)
    s[0] = 1.0
    rc, ro, rh, rl = (np.log(m[x] / prev) for x in ('c', 'o', 'h', 'l'))
    c2 = np.exp(np.log(c[0]) + np.cumsum(s * rc))
    p2 = np.r_[c2[0], c2[:-1]]
    out = dict(m)
    sig = lambda x: np.round(x * 10.0 ** (11 - np.floor(np.log10(x)))) / 10.0 ** (11 - np.floor(np.log10(x)))
    out['c'] = sig(c2)                              # 12 significant digits: a move up and back lands on the same price
    out['o'] = sig(p2 * np.exp(s * ro))             # exactly (as on the coin), not a few float bits away
    out['h'] = np.maximum(sig(p2 * np.exp(np.where(s > 0, rh, -rl))), np.maximum(out['o'], out['c']))
    out['l'] = np.minimum(sig(p2 * np.exp(np.where(s > 0, rl, -rh))), np.minimum(out['o'], out['c']))
    if m['tb'] is not None:
        out['tb'] = np.where(s > 0, m['tb'], m['v'] - m['tb'])
    return out


def resample(m: dict, k: int) -> dict:
    if k == 1:
        return {x: m[x] for x in ('o', 'h', 'l', 'c', 'v', 'tb')}
    nb = m['n'] // k
    r = lambda a: a[:nb * k].reshape(nb, k)
    return {'o': r(m['o'])[:, 0].copy(), 'h': r(m['h']).max(1), 'l': r(m['l']).min(1), 'c': r(m['c'])[:, -1].copy(),
            'v': r(m['v']).sum(1), 'tb': None if m['tb'] is None else r(m['tb']).sum(1)}


def bucket(x: np.ndarray, edges) -> np.ndarray:
    """Cell of x between the edges; a value exactly on an edge belongs to the OUTER cell on both sides (so the two
    extremes are treated alike); not finite -> -1."""
    x = np.asarray(x, float)
    e = np.asarray(edges, float)
    mid = (e[0] + e[-1]) / 2
    with np.errstate(invalid='ignore'):
        out = np.where(x < mid, np.digitize(x, e, right=True), np.digitize(x, e)).astype(np.int8)
    out[~np.isfinite(x)] = -1
    return out


def context_readings(m: dict, dom_dir: str) -> list:
    """Context STATES. BTC.D / USDT.D: the change of the last COMPLETED UTC day and of the last 5, each divided by the
    series' own daily volatility over the 60 days before it (five levels), and the two 1-day directions together
    (four quadrants); bar i = day i, readable only from day i's close on. The UTC 4-hour block (k = 240)."""
    nd = m['n'] // 1440
    days = m['t0'] + np.arange(nd) * DAY
    R, up = [], {}
    for sym in ('BTC.D', 'USDT.D'):
        f = os.path.join(dom_dir, f'{sym}_1d.csv')
        if not os.path.exists(f):
            continue
        d = pd.read_csv(f)[['ts', 'c']].drop_duplicates('ts').set_index('ts')['c']
        d.index = (d.index // DAY) * DAY
        d = d.groupby(level=0).last()
        d = d[d.index < HEAT_END]
        d = d.reindex(np.arange(int(d.index.min()), int(d.index.max()) + DAY, DAY))
        r1 = d / d.shift(1) - 1
        sd = r1.rolling(60, min_periods=40).std().shift(1)          # the days before the scored day only
        z = {'1d': r1 / sd, '5d': (d / d.shift(5) - 1) / (sd * math.sqrt(5))}
        for nm in ('1d', '5d'):
            R.append({'name': f'{sym} {nm}', 'k': 1440, 'codes': bucket(z[nm].reindex(days).to_numpy(float), DOM_Z), 'levels': DOM_LV,
                      'ctx': True, 'state': True, 'base': f'{sym} {nm}'})
        up[sym] = r1.reindex(days).to_numpy(float)
    if len(up) == 2:
        a, b = up['BTC.D'], up['USDT.D']
        R.append({'name': 'Dom 1d', 'k': 1440, 'codes': np.where(np.isfinite(a) & np.isfinite(b), (a > 0) * 2 + (b > 0), -1).astype(np.int8),
                  'levels': ['BTC.D down, USDT.D down', 'BTC.D down, USDT.D up', 'BTC.D up, USDT.D down', 'BTC.D up, USDT.D up'],
                  'ctx': True, 'state': True, 'base': 'Dom 1d'})
    nb = m['n'] // 240
    R.append({'name': 'UTC4h', 'k': 240, 'codes': ((np.arange(nb) + 1) % 6).astype(np.int8),
              'levels': [f'{4 * i:02d}-{4 * i + 4:02d}' for i in range(6)], 'ctx': True, 'state': True, 'base': 'UTC4h'})
    return R


# -------------------------------------------------------------------------------------------------------------- labels
def labels(m: dict, chunk: int = 200_000) -> dict:
    """Per minute row m (decision at its close, entry e = the next minute's open): the move from e to the close H minutes
    after the decision (bps), the best high / worst low on the way, the dip before the best high and the pop before the
    worst low, the minutes price HOLDS above / below the entry (holdU / holdD: consecutive minute closes from the first
    one that stay beyond the entry by more than the dead band; 0 = the first close is not on that side, 60 = the whole
    hour), the same move entered one minute later (retL, a bid-ask bounce check), the first minute (1..60, 0 =
    never) price touches e +X and e -X, the bounce (e vs the signal bar's close), the direction sg (the sign of the move,
    0 when it is within one price step: TICK_DEAD) and a validity mask (no gap at the row or within the next 60 minutes)."""
    from numpy.lib.stride_tricks import sliding_window_view
    n, o, c, h, l, gap = m['n'], m['o'], m['c'], m['h'], m['l'], m['gap']
    e = np.r_[o[1:], np.nan]
    c1 = np.r_[c[1:], np.nan]
    out = {'gap1': ((e / c - 1) * 1e4).astype(np.float32)}
    hp = np.r_[h[1:], np.full(HMAX + 1, np.nan)]
    lp = np.r_[l[1:], np.full(HMAX + 1, np.nan)]
    Wh, Wl = sliding_window_view(hp, HMAX), sliding_window_view(lp, HMAX)       # row m: bars m+1 .. m+60
    Wc = sliding_window_view(np.r_[c[1:], np.full(HMAX + 1, np.nan)], HMAX)     # the closes of the same bars
    dead_a = np.broadcast_to(np.asarray(TICK_DEAD * m['tick'] if 'tick' in m else 0.0, np.float64), (n,))
    out['holdU'], out['holdD'] = np.zeros(n, np.int8), np.zeros(n, np.int8)
    for H in HORIZONS:
        fut = np.r_[c[H:], np.full(H, np.nan)]
        out[f'ret{H}'] = ((fut / e - 1) * 1e4).astype(np.float32)
        out[f'retL{H}'] = ((fut / c1 - 1) * 1e4).astype(np.float32)
        for nm in ('up', 'dn', 'dipU', 'dipD'):
            out[f'{nm}{H}'] = np.full(n, np.nan, np.float32)
    for X in TOUCH:
        out[f'tu{X}'], out[f'td{X}'] = np.zeros(n, np.int8), np.zeros(n, np.int8)
    for s in range(0, n, chunk):
        t = min(n, s + chunk)
        ee = e[s:t]
        wh, wl = Wh[s:t], Wl[s:t]
        ar = np.arange(t - s)
        with np.errstate(invalid='ignore'):
            for H in HORIZONS:
                a, b = wh[:, :H], wl[:, :H]
                am = np.where(np.isnan(a), -np.inf, a).argmax(1)
                bm = np.where(np.isnan(b), np.inf, b).argmin(1)
                out[f'up{H}'][s:t] = (a[ar, am] / ee - 1) * 1e4
                out[f'dn{H}'][s:t] = (b[ar, bm] / ee - 1) * 1e4
                out[f'dipU{H}'][s:t] = (np.minimum.accumulate(b, 1)[ar, am] / ee - 1) * 1e4
                out[f'dipD{H}'][s:t] = (np.maximum.accumulate(a, 1)[ar, bm] / ee - 1) * 1e4
            rc = (Wc[s:t] / ee[:, None] - 1) * 1e4
            dd = dead_a[s:t][:, None]
            ab, be = rc > dd, rc < -dd
            out['holdU'][s:t] = np.where(ab.all(1), HMAX, ab.argmin(1))
            out['holdD'][s:t] = np.where(be.all(1), HMAX, be.argmin(1))
            del rc, ab, be
            for X in TOUCH:
                for W, up, arr in ((wh, True, out[f'tu{X}']), (wl, False, out[f'td{X}'])):
                    hit = (W >= ee[:, None] * (1 + X / 1e4)) if up else (W <= ee[:, None] * (1 - X / 1e4))
                    arr[s:t] = np.where(hit.any(1), hit.argmax(1) + 1, 0)
    dead = TICK_DEAD * m['tick'] if 'tick' in m else 0.0
    with np.errstate(invalid='ignore'):
        for H in HORIZONS:
            r = out[f'ret{H}']
            out[f'sg{H}'] = np.where(np.isfinite(r) & (np.abs(r) > dead), np.sign(r), 0).astype(np.int8)
    out['tick'] = m['tick'] if 'tick' in m else np.zeros(n, np.float32)
    g = pd.Series(gap.astype(np.int16)[::-1]).rolling(HMAX + 1, min_periods=1).sum().to_numpy()[::-1]
    valid = (g == 0)
    valid[max(0, n - HMAX - 1):] = False
    out['valid'] = valid
    return out


# ----------------------------------------------------------------------------------------------------------- the stats
def _clu(x: np.ndarray, dr: np.ndarray, ND: int, bd: np.ndarray, N: int):
    """Mean of x over the events and its day-clustered standard error. x is already centred on the base mean; the
    variance uses each day's influence on (event mean - base mean): the events' own part minus the base's part (bd =
    per-day sums of the centred values over ALL valid minutes, N of them), so a level that fires on most minutes is not
    charged for noise it shares with the base. Also the EFFECTIVE number of days, (sum psi^2)^2 / sum psi^4: when a few
    very volatile days carry most of the variance the t has that many degrees of freedom, not the count of days."""
    n = len(x)
    S = np.bincount(dr, x, minlength=ND)
    cnt = np.bincount(dr, minlength=ND)
    mu = S.sum() / n
    psi = (S - mu * cnt) / n - bd / N
    G = int(np.count_nonzero(cnt))
    q2, q4 = float((psi ** 2).sum()), float((psi ** 4).sum())
    var = q2 * G / (G - 1) if G > 1 else float('nan')
    se = math.sqrt(var) if var == var and var > 0 else float('nan')
    deff = min(float(G), q2 * q2 / q4) if q4 > 0 else float(G)      # the effective number of days behind the variance
    return float(mu), se, G, deff


def _t(mu, se):
    return float(mu / se) if se == se and se > 0 else 0.0


_TC = {}


def tcrit(days, p: float) -> np.ndarray:
    """The t a level needs for a one-sided p when its events fall on `days` days (t distribution, days - 1 df)."""
    if p not in _TC:
        from scipy.stats import t as tdist
        _TC[p] = tdist.isf(p, np.maximum(np.arange(4000) - 1, 1))
    d = np.nan_to_num(np.asarray(days, float), nan=0.0)
    return _TC[p][np.clip(d, 0, 3999).astype(np.int64)]


def _trim():
    """Hand freed memory back to the system (large arrays of a finished stage)."""
    try:
        import ctypes
        ctypes.CDLL('libc.so.6').malloc_trim(0)
    except Exception:
        pass


class Rows:
    """Row dicts gathered in chunks (a list of a few million dicts is too heavy)."""

    def __init__(self):
        self.buf, self.frames, self.n = [], [], 0

    def __iadd__(self, rows):
        self.buf += rows
        self.n += len(rows)
        if len(self.buf) >= ROW_CHUNK:
            self.frames.append(pd.DataFrame(self.buf))
            self.buf = []
        return self

    def frame(self) -> pd.DataFrame:
        if self.buf:
            self.frames.append(pd.DataFrame(self.buf))
            self.buf = []
        return pd.concat(self.frames, ignore_index=True) if self.frames else pd.DataFrame()


class Split:
    pass


class Grid:
    def __init__(self, m: dict, lab: dict):
        self.t0, self.n, self.lab = m['t0'], m['n'], lab
        self.day = (np.arange(m['n']) // 1440).astype(np.int64)        # UTC day of the row's bar (grid starts at midnight)
        self.day[1439::1440] += 1                                      # a 23:59 bar's decision is the next day's 00:00
        self.sp = {}
        for s, (a, b) in SPLITS.items():
            sp = Split()
            lo = max(0, int(np.ceil((a - self.t0) / MIN)) - 1)
            hi = max(lo, min(int((b - HMAX * MIN - self.t0) // MIN), self.n))
            sp.lo, sp.hi = lo, hi
            sp.rows = np.arange(lo, hi)[lab['valid'][lo:hi]]
            sp.N = len(sp.rows)
            sp.d0 = int(self.day[lo]) if hi > lo else 0
            sp.ND = int(self.day[hi - 1] - sp.d0 + 1) if hi > lo else 1
            sp.ndays = max(1.0, (hi - lo) / 1440)
            self.sp[s] = sp
            sp.base, sp.bd_e, sp.bd_s = {}, {}, {}
            if sp.N == 0:
                continue
            full = self.full(sp.rows, s, base=True)
            dr = self.day[sp.rows] - sp.d0
            for H in HORIZONS:
                sp.base[H] = full[H]
                sp.bd_e[H] = np.bincount(dr, lab[f'ret{H}'][sp.rows].astype(np.float64) - full[H]['mean'], minlength=sp.ND)
                sp.bd_s[H] = np.bincount(dr, lab[f'sg{H}'][sp.rows].astype(np.float64) - full[H]['msign'], minlength=sp.ND)
            sp.base['gap1'] = full['gap1']
            sp.base['hold_up'], sp.base['hold_dn'] = full['hold_up'], full['hold_dn']
            sp.base['n'], sp.base['per_day'] = full['n'], full['per_day']

    def in_split(self, idx: np.ndarray, s: str) -> np.ndarray:
        sp = self.sp[s]
        idx = idx[(idx >= sp.lo) & (idx < sp.hi)]
        return idx[self.lab['valid'][idx]]

    def full(self, idx: np.ndarray, s: str, base: bool = False) -> dict:
        """Every statistic of the events idx (rows of split s, valid)."""
        sp, lab = self.sp[s], self.lab
        n = int(len(idx))
        out = {'n': n}
        if n == 0:
            return out
        dr = self.day[idx] - sp.d0
        out['per_day'] = n / sp.ndays
        out['days'] = int(len(np.unique(dr)))
        out['gap1'] = float(lab['gap1'][idx].mean())
        out['tick'] = float(np.median(lab['tick'][idx]))
        out['hold_up'], out['hold_dn'] = float(lab['holdU'][idx].mean()), float(lab['holdD'][idx].mean())
        touch = {X: (lab[f'tu{X}'][idx], lab[f'td{X}'][idx]) for X in TOUCH}
        for H in HORIZONS:
            r = lab[f'ret{H}'][idx].astype(np.float64)
            sg = lab[f'sg{H}'][idx].astype(np.float64)
            st = {'mean': float(r.mean()), 'msign': float(sg.mean()), 'p_up': float((sg > 0).mean()), 'p_dn': float((sg < 0).mean()),
                  'median': float(np.median(r)), 'best_up': float(lab[f'up{H}'][idx].mean()), 'best_dn': float(lab[f'dn{H}'][idx].mean()),
                  'dip_up': float(lab[f'dipU{H}'][idx].mean()), 'dip_dn': float(lab[f'dipD{H}'][idx].mean()),
                  'retL': float(lab[f'retL{H}'][idx].mean()), 'mabs': float(np.abs(r).mean()),
                  'wd': len(np.unique((idx + 1) // H)) / sp.ndays}
            for X in TOUCH:
                tu, td = touch[X]
                hu, hd = (tu > 0) & (tu <= H), (td > 0) & (td <= H)
                wu, wd = float((hu & (~hd | (tu < td))).mean()), float((hd & (~hu | (td < tu))).mean())
                tie = float((hu & hd & (tu == td)).mean())
                st[f'win_up{X}'], st[f'win_dn{X}'] = wu, wd
                st[f'net_up{X}'], st[f'net_dn{X}'] = wu - wd - tie, wd - wu - tie
            if not base:
                b = sp.base[H]
                mu, se, _, de = _clu(r - b['mean'], dr, sp.ND, sp.bd_e[H], sp.N)
                ms_, ses, _, dp = _clu(sg - b['msign'], dr, sp.ND, sp.bd_s[H], sp.N)
                st.update(excess=mu, se=se, t=_t(mu, se), edge_p=ms_ / 2, t_p=_t(ms_, ses), deff=de, deff_p=dp, excessL=st['retL'] - b['retL'],
                          size=st['mabs'] / b['mabs'] if b['mabs'] > 0 else float('nan'))
                for X in TOUCH:
                    st[f'bx_up{X}'] = X * (st[f'net_up{X}'] - b[f'net_up{X}'])
                    st[f'bx_dn{X}'] = X * (st[f'net_dn{X}'] - b[f'net_dn{X}'])
            out[H] = st
        if not base:
            out['gap1'] -= sp.base['gap1']
        return out

    def quick(self, idx: np.ndarray, s: str) -> dict:
        """{H: (excess, edge_p)} only (for the time-of-day shifts)."""
        sp, lab = self.sp[s], self.lab
        return {H: (float(lab[f'ret{H}'][idx].mean()) - sp.base[H]['mean'],
                    (float(lab[f'sg{H}'][idx].mean()) - sp.base[H]['msign']) / 2) for H in HORIZONS}

    def pre(self, E: np.ndarray, s: str) -> dict:
        """Centred per-event arrays of the events E (rows of split s, valid), for cells()."""
        sp, lab = self.sp[s], self.lab
        return {'dr': self.day[E] - sp.d0, 'rows': E, 'tick': lab['tick'][E].astype(np.float64),
                'e': {H: lab[f'ret{H}'][E].astype(np.float64) - sp.base[H]['mean'] for H in HORIZONS},
                's': {H: lab[f'sg{H}'][E].astype(np.float64) - sp.base[H]['msign'] for H in HORIZONS},
                'L': {H: lab[f'retL{H}'][E].astype(np.float64) - sp.base[H]['retL'] for H in HORIZONS},
                'dU': {H: lab[f'dipU{H}'][E] for H in HORIZONS}, 'dD': {H: lab[f'dipD{H}'][E] for H in HORIZONS},
                'sg': {H: lab[f'sg{H}'][E] for H in HORIZONS}, 'hU': lab['holdU'][E], 'hD': lab['holdD'][E]}

    def cells(self, s: str, pre: dict, codes: np.ndarray, L: int, lift: bool, late: bool = True, win: bool = True, cb: dict = None) -> dict:
        """The events of `pre` split by `codes` (0..L-1, -1 = NA): per level and horizon the excess move and the odds
        edge against the base with day-clustered t, and (lift) the same against the OTHER levels' events. cb: the
        splitting reading's own effect per level over ALL minutes ({(H, track): centred mean}); then also lift2 = the
        cell against that (a cell must add to BOTH its parents: the trigger and the condition). late: also
        the move entered one minute later and the usual wrong-way dip; win: also the distinct H-minute clock windows per day that hold an event."""
        sp = self.sp[s]
        ND = sp.ND
        key = np.where(codes < 0, L, codes).astype(np.int64) * ND + pre['dr']
        size = (L + 1) * ND
        C = np.bincount(key, minlength=size).reshape(L + 1, ND)[:L].astype(np.float64)
        cnt = C.sum(1)
        G = (C > 0).sum(1)
        Call = C.sum(0)
        rest = cnt.sum() - cnt
        out = {'n': cnt.astype(np.int64), 'days': G, 'rest_n': rest.astype(np.int64)}
        lvc = np.where(codes < 0, L, codes)
        with np.errstate(all='ignore'):
            out['tick'] = np.bincount(lvc, pre['tick'], minlength=L + 1)[:L] / cnt
            fac = np.where(G > 1, G / np.maximum(G - 1, 1), np.nan)
            cn = cnt[:, None]
            for H in HORIZONS:
                for tr, x, bd in (('e', pre['e'][H], sp.bd_e[H]), ('s', pre['s'][H], sp.bd_s[H])):
                    S = np.bincount(key, x, minlength=size).reshape(L + 1, ND)[:L]
                    mu = S.sum(1) / cnt
                    own = (S - mu[:, None] * C) / cn
                    psi = own - bd[None, :] / sp.N
                    q2 = (psi ** 2).sum(1)
                    q4 = ((psi ** 2) ** 2).sum(1)
                    se = np.sqrt(q2 * fac)
                    deff = np.minimum(np.where(q4 > 0, q2 * q2 / q4, G), G)
                    sc = 1.0 if tr == 'e' else 0.5
                    out[(H, tr)] = mu * sc
                    out[(H, tr + '_se')] = se * sc
                    out[(H, tr + '_t')] = np.where(se > 0, mu / se, 0.0)
                    if lift:
                        Sall = S.sum(0)
                        mur = (Sall.sum() - S.sum(1)) / rest
                        oth = ((Sall[None, :] - S) - mur[:, None] * (Call[None, :] - C)) / rest[:, None]
                        psi = own - oth
                        l2 = (psi ** 2).sum(1)
                        l4 = ((psi ** 2) ** 2).sum(1)
                        sel = np.sqrt(l2 * fac)
                        deff = np.minimum(deff, np.where(l4 > 0, l2 * l2 / l4, G))
                        out[(H, tr + '_lift')] = (mu - mur) * sc
                        out[(H, tr + '_tlift')] = np.where(sel > 0, (mu - mur) / sel, 0.0)
                    out[(H, tr + '_deff')] = deff
                    if cb is not None:
                        out[(H, tr + '_lift2')] = (mu - cb[(H, tr)]) * sc
                        out[(H, tr + '_tlift2')] = np.where(se > 0, (mu - cb[(H, tr)]) / se, 0.0)
                if late:
                    out[(H, 'L')] = np.bincount(lvc, pre['L'][H], minlength=L + 1)[:L] / cnt
                    out[(H, 'dU')] = np.bincount(lvc, pre['dU'][H], minlength=L + 1)[:L] / cnt     # the usual dip before the best high
                    out[(H, 'dD')] = np.bincount(lvc, pre['dD'][H], minlength=L + 1)[:L] / cnt     # the usual pop before the worst low
                    out[(H, 'pu')] = np.bincount(lvc, pre['sg'][H] > 0, minlength=L + 1)[:L] / cnt     # share of events that went up
                    out[(H, 'pd')] = np.bincount(lvc, pre['sg'][H] < 0, minlength=L + 1)[:L] / cnt     # ... down (flat: neither)
                    if win:
                        nw = self.n // H + 2
                        u = np.unique(lvc * nw + (pre['rows'] + 1) // H)
                        out[(H, 'wd')] = np.bincount(u // nw, minlength=L + 1)[:L] / sp.ndays
            if late:
                out['hU'] = np.bincount(lvc, pre['hU'], minlength=L + 1)[:L] / cnt        # minutes the price holds above the entry
                out['hD'] = np.bincount(lvc, pre['hD'], minlength=L + 1)[:L] / cnt        # ... below it
        return out


def read_state(R: dict, idx: np.ndarray) -> np.ndarray:
    """Code of reading R known at minute rows idx (the last bar of R's timeframe closed at or before the row's close)."""
    k, codes = R['k'], R['codes']
    bi = (idx + 1) // k - 1
    out = np.full(len(idx), -1, np.int8)
    ok = (bi >= 0) & (bi < len(codes))
    out[ok] = codes[bi[ok]]
    return out


def level_events(R: dict, lv: int, side: int = 0) -> np.ndarray:
    """Rows (bar closes) where level lv STARTS to hold after a known, different level (side +1: entered from a lower
    level, -1: from a higher one). A candlestick pattern ('every'): each bar it fires. A context state ('state'): every
    15-minute close while it holds (a dominance or clock state is a condition of the whole day, not a moment)."""
    codes = R['codes']
    if R.get('state'):
        rows = np.arange(14, len(codes) * R['k'], 15)
        return rows[read_state(R, rows) == lv]
    on = codes == lv
    if R.get('every'):
        bi = np.nonzero(on)[0]
    else:
        prev = np.r_[np.int8(-1), codes[:-1]]
        st = on & (prev != lv) & (prev >= 0)
        if side > 0:
            st &= prev < lv
        elif side < 0:
            st &= prev > lv
        bi = np.nonzero(st)[0]
    return bi * R['k'] + R['k'] - 1


def event_levels(R: dict) -> list:
    """(level index, side, label) of every event a reading defines. The inner zones of a value reading are entered from
    two sides, which are opposite setups: falling in / recovering (low), rising in / cooling (high)."""
    if R.get('zones'):
        return [(0, 0, 'very low'), (1, -1, 'low (falling in)'), (1, 1, 'low (recovering)'),
                (3, 1, 'high (rising in)'), (3, -1, 'high (cooling)'), (4, 0, 'very high')]
    return [(i, 0, lv) for i, lv in enumerate(R['levels']) if lv not in NEUTRAL]


def shift_events(idx: np.ndarray, g: Grid, s: str, rng) -> np.ndarray:
    """The events moved by a whole random number of days (>= 30), circular over the split's whole days: same count,
    same clock time, same clustering, other days."""
    sp = g.sp[s]
    D = (sp.hi - sp.lo) // 1440
    if D < 61:
        return idx
    sh = int(rng.integers(30, D - 30)) * 1440
    idx = idx[idx < sp.lo + D * 1440]
    return sp.lo + (idx - sp.lo + sh) % (D * 1440)


# ------------------------------------------------------------------------------------------------------------ readings
def build_readings(m: dict, g: Grid, dom: str, log=print):
    """All readings (bar-level int8 codes) and the curve rows. Zone and curve edges come from split A's bars only. A bar
    that holds a forward-filled minute, and the STALE bars after it (500 after a long outage), carry no reading."""
    from oracle.heat_vocab import sign_codes, vocabulary
    spA = g.sp['A']
    readings, curves, edges, missing = [], Rows(), {}, []
    mu = tick_units(m, spA.hi)
    for k in TFS:
        b = resample(mu, k)
        V, C, miss = vocabulary(b)
        missing = sorted(set(missing) | set(miss))
        nb = len(b['c'])
        gb = m['gap'][:nb * k].reshape(nb, k).any(1)
        stale = pd.Series(gb.astype(np.float32)).rolling(STALE + 1, min_periods=1).max().to_numpy() > 0
        run = pd.Series(gb.astype(np.int64)).groupby(np.cumsum(~gb)).cumsum().to_numpy()         # length of the gap run ending here
        stale |= pd.Series((run > STALE_LONG[0]).astype(np.float32)).rolling(STALE_LONG[1] + 1, min_periods=1).max().to_numpy() > 0
        bar_rows = np.arange(nb) * k + k - 1
        inA = (bar_rows >= spA.lo) & (bar_rows < spA.hi)
        pre = {}
        for s in SPLITS:
            rows = g.in_split(bar_rows, s)
            pre[s] = (rows, g.pre(rows, s) if len(rows) else None)
        n_val = len(V)
        for vi in range(n_val):
            name, typ, zero, x = V[vi]
            V[vi] = None
            x[stale] = np.nan
            xa = x[inA]
            xa = xa[np.isfinite(xa)]
            if len(xa) < 1000:
                continue
            full = f'{k}m:{name}'
            zq = np.quantile(xa, ZONE_Q)
            if zq[1] < zq[2]:                           # (an atom on an outer edge only empties that inner zone)
                edges[full] = [float(q) for q in zq]
                readings.append({'name': full, 'k': k, 'codes': bucket(x, zq), 'levels': ZONES, 'base': full, 'type': typ, 'zones': True})
            if zero:
                readings.append({'name': full + ' sign', 'k': k, 'codes': sign_codes(x), 'levels': ['below 0', 'above 0'], 'base': full, 'type': typ})
            dq = np.unique(np.quantile(xa, CURVE_Q))
            if len(dq) >= 3:
                dcodes = np.digitize(x, dq).astype(np.int8)
                dcodes[~np.isfinite(x)] = -1
                lo_hi = [(None if i == 0 else float(dq[i - 1]), None if i == len(dq) else float(dq[i])) for i in range(len(dq) + 1)]
                for s in SPLITS:
                    rows, p = pre[s]
                    if p is None:
                        continue
                    cs = g.cells(s, p, dcodes[(rows + 1) // k - 1].astype(np.int64), len(dq) + 1, lift=False, win=False)
                    curves += cell_rows('curve', full, s, g, cs, [f'c{i:02d}' for i in range(len(dq) + 1)],
                                        extra=lambda i: {'series': full, 'bin': i, 'lo': lo_hi[i][0], 'hi': lo_hi[i][1]})
        for name, codes, levels, every in C:
            full = f'{k}m:{name}'
            codes[stale] = -1
            readings.append({'name': full, 'k': k, 'codes': codes, 'levels': levels, 'base': full, 'every': every, 'cond': not every})
        log(f'  {k}m: {n_val} value series, {len(C)} two-state / pattern readings; {int(stale.sum()):,} of {nb:,} bars stale after gaps')
        del pre, V, C, b
        _trim()
    readings += context_readings(m, dom)
    return readings, curves, edges, missing, mu.get('step')


def cell_rows(kind: str, key: str, s: str, g: Grid, cs: dict, levels: list, extra=None, only=None, min_n: int = 1) -> list:
    sp = g.sp[s]
    rows = []
    for i, lv in enumerate(levels):
        if lv in NEUTRAL and kind != 'curve':
            continue
        if only is not None and i not in only:
            continue
        n = int(cs['n'][i])
        if n < min_n:
            continue
        head = {'kind': kind, 'key': f'{key}={lv}' if kind != 'curve' else f'{key}#{lv}', 'split': s}      # strings: once per level
        ex = extra(i) if extra is not None else {}
        for H in HORIZONS:
            row = {**head, 'h': H, 'n': n, 'per_day': n / sp.ndays, 'days': int(cs['days'][i]), 'excess': float(cs[(H, 'e')][i]),
                   'se': float(cs[(H, 'e_se')][i]), 't': float(cs[(H, 'e_t')][i]), 'edge_p': float(cs[(H, 's')][i]), 't_p': float(cs[(H, 's_t')][i]),
                   'excessL': float(cs[(H, 'L')][i]), 'tick': float(cs['tick'][i]), 'deff': float(cs[(H, 'e_deff')][i]), 'deff_p': float(cs[(H, 's_deff')][i])}
            if (H, 'dU') in cs:
                row['dip_up'], row['dip_dn'] = float(cs[(H, 'dU')][i]), float(cs[(H, 'dD')][i])
                row['p_up'], row['p_dn'] = float(cs[(H, 'pu')][i]), float(cs[(H, 'pd')][i])
            if (H, 'wd') in cs:
                row['wd'] = float(cs[(H, 'wd')][i])
            if 'hU' in cs:
                row['hold_up'], row['hold_dn'] = float(cs['hU'][i]), float(cs['hD'][i])
            if (H, 'e_lift') in cs:
                row.update(lift=float(cs[(H, 'e_lift')][i]), t_lift=float(cs[(H, 'e_tlift')][i]), liftp=float(cs[(H, 's_lift')][i]),
                           t_liftp=float(cs[(H, 's_tlift')][i]), rest_n=int(cs['rest_n'][i]))
            if (H, 'e_lift2') in cs:
                row.update(lift2=float(cs[(H, 'e_lift2')][i]), t_lift2=float(cs[(H, 'e_tlift2')][i]), liftp2=float(cs[(H, 's_lift2')][i]),
                           t_liftp2=float(cs[(H, 's_tlift2')][i]))
            row.update(ex)
            rows.append(row)
    return rows


def pack(cs: dict):
    """A cells dict as one float32 block (keys, array): a hundred thousand of them must fit in memory."""
    keys = list(cs.keys())
    return keys, np.stack([np.asarray(cs[k], np.float64) for k in keys]).astype(np.float32)


def unpack(pk) -> dict:
    return {k: pk[1][i] for i, k in enumerate(pk[0])}


FULL_COLS = ['mean', 'excess', 'se', 't', 'edge_p', 't_p', 'deff', 'deff_p', 'p_up', 'p_dn', 'median', 'best_up', 'best_dn', 'dip_up', 'dip_dn', 'excessL', 'wd', 'size'] + \
            [f'{a}{X}' for X in TOUCH for a in ('bx_up', 'bx_dn', 'win_up', 'win_dn')]


def full_rows(kind: str, key: str, st_by_split: dict, tod=None) -> list:
    rows = []
    for s, st in st_by_split.items():
        if st.get('n', 0) == 0:
            continue
        for H in HORIZONS:
            row = {'kind': kind, 'key': key, 'split': s, 'h': H, 'n': st['n'], 'per_day': st['per_day'], 'days': st['days'], 'gap1': st['gap1'],
                   'tick': st['tick'], 'hold_up': st['hold_up'], 'hold_dn': st['hold_dn']}
            row.update({k: st[H][k] for k in FULL_COLS})
            if tod and (s, H) in tod:
                row['tod_excess'], row['tod_edge_p'] = tod[(s, H)]
            rows.append(row)
    return rows


def hot_cells(cs: dict, need_lift: bool) -> np.ndarray:
    """Bool (L, n_H): the cell is hot on this split in either track (move or odds), its move is at least one price step
    of the coin, and (lift) it adds to BOTH its parents: it beats the trigger's other events and, when the cells carry
    lift2, the condition level's own effect, and its lift over the trigger is itself at least one price step."""
    ok = (cs['n'] >= MIN_EVENTS) & (cs['days'] >= MIN_DAYS_A)
    if need_lift:
        ok &= cs['rest_n'] >= MIN_EVENTS
    out = []
    for H in HORIZONS:
        h = np.zeros(len(ok), bool)
        big = np.abs(cs[(H, 'e')]) >= cs['tick']
        if need_lift:
            big &= np.abs(cs[(H, 'e_lift')]) >= cs['tick']
        for tr in ('e', 's'):
            de = cs[(H, tr + '_deff')]
            x = np.abs(cs[(H, tr + '_t')]) >= tcrit(de, HOT_P / 2)
            if need_lift:
                d, c_lift = np.sign(cs[(H, tr)]), tcrit(de, REP_P)
                x &= cs[(H, tr + '_tlift')] * d >= c_lift
                if (H, tr + '_tlift2') in cs:
                    x &= cs[(H, tr + '_tlift2')] * d >= c_lift
            h |= x
        out.append(h & ok & big)
    return np.array(out).T


_W = {}             # the grid, readings and conditions the pair / triple workers read (inherited by fork)


def _pmap(fn, items, procs: int) -> list:
    if procs <= 1 or len(items) < 2:
        return [fn(x) for x in items]
    import multiprocessing as mp
    with mp.get_context('fork').Pool(procs) as pool:
        return pool.map(fn, items, chunksize=1)


def _events_of(x):
    g = _W['g']
    ev = level_events(_W['readings'][x[1]], x[2], x[4])
    E = {s: g.in_split(ev, s) for s in SPLITS}
    return E, {s: g.pre(E[s], s) if len(E[s]) else None for s in SPLITS}


def _cond_base_job(ci):
    """The own effect of reading ci as a state: per split and level, the centred mean move and sign over ALL valid
    minutes while the level holds (what a pair cell with this condition must beat)."""
    g, R = _W['g'], _W['readings'][ci]
    L = len(R['levels'])
    out = {}
    for s in SPLITS:
        sp, o = g.sp[s], {}
        if sp.N:
            codes = read_state(R, sp.rows).astype(np.int64)
            ok = codes >= 0
            cd = codes[ok]
            cnt = np.bincount(cd, minlength=L)[:L].astype(np.float64)
            with np.errstate(all='ignore'):
                for k, x in _W['xs'][s].items():
                    o[k] = np.bincount(cd, x[ok], minlength=L)[:L] / cnt
        out[s] = o
    return ci, out


def _split_cells(E, P, R, ci=None):
    """One conditioning reading over the events E: cells on A (screen), the hot mask and the count of tested cells."""
    g = _W['g']
    L = len(R['levels'])
    cb = _W.get('cbase', {}).get(ci)
    cbA, cbB = (cb['A'] or None, cb['B'] or None) if cb else (None, None)
    codes = read_state(R, E['A']).astype(np.int64)
    cA = g.cells('A', P['A'], codes, L, lift=True, late=False, cb=cbA)
    ok = (cA['n'] >= MIN_EVENTS) & (cA['days'] >= MIN_DAYS_A) & (cA['rest_n'] >= MIN_EVENTS)
    ok &= np.array([lv not in NEUTRAL for lv in R['levels']])
    hot = hot_cells(cA, True) & ok[:, None]
    n_t = int(ok.sum()) * len(HORIZONS)
    if not hot.any():
        return n_t, None, None, hot
    cA = g.cells('A', P['A'], codes, L, lift=True, cb=cbA)
    cB = g.cells('B', P['B'], read_state(R, E['B']).astype(np.int64), L, lift=True, cb=cbB) if P['B'] is not None else None
    return n_t, cA, cB, hot


def _pair_job(job):
    """One trigger against every conditioning reading (or the context states only): (cell-horizons tested,
    [(score, x, cond index, cells A, cells B, hot)])."""
    x, ctx_only = job
    readings = _W['readings']
    E, P = _events_of(x)
    R0 = readings[x[1]]
    tested, rels = 0, []
    if P['A'] is None:
        return tested, rels
    for ci, R in _W['ctx' if ctx_only else 'conds']:
        if R['base'] == R0['base']:
            continue
        n_t, cA, cB, hot = _split_cells(E, P, R, ci)
        tested += n_t
        if cA is None:
            continue
        best = 0.0
        for hi, H in enumerate(HORIZONS):
            for tr in ('e', 's'):
                d = np.sign(cA[(H, tr)])
                z = cA[(H, tr + '_tlift')] * d
                if (H, tr + '_tlift2') in cA:
                    z = np.minimum(z, cA[(H, tr + '_tlift2')] * d)          # the weaker of its two lifts
                best = max(best, float(np.nanmax(np.where(hot[:, hi], z, 0.0))))
        rels.append((best, x, ci, pack(cA), None if cB is None else pack(cB), hot))
    return tested, rels


def _triple_job(job):
    """One hot pair cell against every third reading: (cell-horizons tested, relationships with a hot cell, rows)."""
    x, c1, lv1 = job
    g, readings = _W['g'], _W['readings']
    E, _ = _events_of(x)
    R0, R1 = readings[x[1]], readings[c1]
    E1 = {s: E[s][read_state(R1, E[s]) == lv1] for s in SPLITS}
    tested, n_hot, rows = 0, 0, []
    if len(E1['A']) < 2 * MIN_EVENTS:
        return tested, n_hot, rows
    P1 = {s: g.pre(E1[s], s) if len(E1[s]) else None for s in SPLITS}
    key1 = f'{x[3]} | {R1["name"]}={R1["levels"][lv1]}'
    for ci, R in _W['conds']:
        if R['base'] in (R0['base'], R1['base']):
            continue
        n_t, cA, cB, hot = _split_cells(E1, P1, R, ci)
        tested += n_t
        if cA is None:
            continue
        only = set(np.nonzero(hot.any(1))[0].tolist())
        ex = lambda i, R=R: {'trig': key1, 'cond': R['name'], 'lv': R['levels'][i]}
        key = f'{key1} | {R["name"]}'
        rows += cell_rows('triple', key, 'A', g, cA, R['levels'], extra=ex, only=only)
        if cB is not None:
            rows += cell_rows('triple', key, 'B', g, cB, R['levels'], extra=ex, only=only)
        n_hot += 1
    return tested, n_hot, rows


def run_coin(asset: str, csv: str, dom: str, out: str, end: int = HEAT_END, twin: int = 0, procs: int = 0, log=print) -> dict:
    if 'DOGE' in asset.upper():
        raise SystemExit('NEVER DOGE')
    import talib
    os.makedirs(out, exist_ok=True)
    procs = procs or min(4, os.cpu_count() or 1)
    t_start = time.time()
    el = lambda: f'{time.time() - t_start:.0f}s'
    m = load_minutes(csv, end=end)
    label = asset
    if twin:
        m = make_twin(m, twin)
        label = f'{asset}~twin{twin}'
    log(f'{label}: {m["n"]:,} minutes from {pd.Timestamp(m["t0"], unit="ms")}; gaps {int(m["gap"].sum()):,}')
    from oracle.heat_vocab import EXCLUDED
    gp = np.diff(np.r_[0, m['gap'].astype(np.int8), 0])
    runs = np.nonzero(gp == -1)[0] - np.nonzero(gp == 1)[0]
    gap_runs, longest_gap = int(len(runs)), int(runs.max()) if len(runs) else 0
    open_same = float(np.mean(m['o'][1:] == m['c'][:-1]))
    log(f'{label}: {gap_runs} gap runs, longest {longest_gap} minutes; {m.get("bad_rows", 0)} broken rows dropped; '
        f'the open equals the previous close on {100 * open_same:.1f}% of minutes')
    lab = labels(m)
    g = Grid(m, lab)
    log(f'{label}: labels done ({el()}); split rows ' + str({s: (g.sp[s].lo, g.sp[s].hi, g.sp[s].N) for s in SPLITS})
        + '; median price step (bps) ' + str({s: round(float(np.median(lab['tick'][g.sp[s].rows])), 3) if g.sp[s].N else None for s in SPLITS}))
    if g.sp['A'].N == 0:
        raise SystemExit(f'{label}: split A has no valid minute')
    for s in SPLITS:
        if g.sp[s].N and g.sp[s].N < 0.9 * (g.sp[s].hi - g.sp[s].lo):
            raise SystemExit(f'{label}: split {s} has only {g.sp[s].N:,} valid minutes of {g.sp[s].hi - g.sp[s].lo:,}: a truncated or broken CSV')
    readings, rows, edges, missing, mu_step = build_readings(m, g, dom, log)
    if missing:
        raise SystemExit(f'{label}: TA-Lib functions missing from this install: {missing}')
    n_curve = rows.n // (len(HORIZONS) * len(SPLITS))
    log(f'{label}: {len(readings)} readings, {n_curve} curve bins ({el()})')

    # ---------------------------------------------------------------------------------------------------- singles
    singles = []            # (score on A, reading index, level, key, side)
    for ri, R in enumerate(readings):
        for lv, side, lname in event_levels(R):
            ev = level_events(R, lv, side)
            key = f'{R["name"]}={lname}'
            st, tod = {}, {}
            for s in SPLITS:
                idx = g.in_split(ev, s)
                st[s] = g.full(idx, s)
                if st[s]['n'] >= MIN_EVENTS:
                    rng = np.random.default_rng([20261111, zlib.crc32(f'{key}|{s}'.encode())])
                    acc = []
                    for _ in range(SEEDS):
                        sh = g.in_split(shift_events(idx, g, s, rng), s)
                        if len(sh) >= MIN_EVENTS:
                            acc.append(g.quick(sh, s))
                    for H in HORIZONS:
                        if acc:
                            tod[(s, H)] = (float(np.mean([a[H][0] for a in acc])), float(np.mean([a[H][1] for a in acc])))
            rows += full_rows('single', key, st, tod)
            a = st['A']
            if a.get('n', 0) >= MIN_EVENTS and a['days'] >= MIN_DAYS_A:
                # the trigger score counts a horizon only when its move is at least one price step (below that it is rounding)
                singles.append((max((max(abs(a[H]['t']), abs(a[H]['t_p'])) if abs(a[H]['excess']) >= a['tick'] else 0.0) for H in HORIZONS),
                                ri, lv, key, side))
    log(f'{label}: singles done ({el()}); {len(singles)} event levels with >= {MIN_EVENTS} events on >= {MIN_DAYS_A} days of A')

    # ------------------------------------------------------------------------------------- pairs: trigger x condition
    singles.sort(key=lambda x: (-x[0], x[3]))
    trig = []
    for k in TFS:
        trig += [x for x in singles if x[0] > 0 and readings[x[1]]['k'] == k and not readings[x[1]].get('ctx')][:N_TRIG_PER_TF]
    trig += [x for x in singles if x[0] > 0 and readings[x[1]].get('ctx')][:N_TRIG_CTX]
    tset = {x[3] for x in trig}
    conds = [(ci, R) for ci, R in enumerate(readings) if R.get('cond', True)]
    # every trigger against every reading; every OTHER event level against the context states (dominance, clock)
    jobs = [(x, False) for x in trig] + [(x, True) for x in singles if x[3] not in tset]
    tested = {'pair': 0, 'triple': 0}
    xs = {}
    for s in SPLITS:
        sp, xs[s] = g.sp[s], {}
        for H in HORIZONS:
            if sp.N:
                xs[s][(H, 'e')] = (lab[f'ret{H}'][sp.rows] - np.float32(sp.base[H]['mean'])).astype(np.float32)
                xs[s][(H, 's')] = (lab[f'sg{H}'][sp.rows] - np.float32(sp.base[H]['msign'])).astype(np.float32)
    _W.update(g=g, readings=readings, conds=conds, ctx=[(ci, R) for ci, R in conds if R.get('ctx')], xs=xs)
    _W['cbase'] = dict(_pmap(_cond_base_job, [ci for ci, _ in conds], procs))
    del xs
    _W.pop('xs')
    _trim()
    log(f'{label}: own effect of {len(conds)} conditions done ({el()})')
    rels = []           # (score, trigger tuple, cond index, cells A, cells B, hot mask)
    for n_t, r in _pmap(_pair_job, jobs, procs):
        tested['pair'] += n_t
        rels += r
    n_rels = len(rels)
    log(f'{label}: pairs done ({el()}); {len(trig)} triggers x {len(conds)} conditions, {len(jobs) - len(trig)} more event levels x '
        f'{len(_W["ctx"])} context states, {tested["pair"]:,} cell-horizons tested, {n_rels:,} relationships with a hot cell')
    rels.sort(key=lambda r: (-r[0], r[1][3], r[2]))
    n_hot_cells = int(sum(int(r[5].sum()) for r in rels))
    if len(rels) > N_REL_WRITE:
        log(f'{label}: writing the {N_REL_WRITE:,} strongest of {len(rels):,} hot relationships (by lift t on A)')
        del rels[N_REL_WRITE:]
    for rank, (score, x, ci, cA, cB, hot) in enumerate(rels):
        cA, cB = unpack(cA), None if cB is None else unpack(cB)
        R = readings[ci]
        only = None if rank < N_REL_CTX else set(np.nonzero(hot.any(1))[0].tolist())
        ex = lambda i, x=x, R=R: {'trig': x[3], 'cond': R['name'], 'lv': R['levels'][i]}
        key = f'{x[3]} | {R["name"]}'
        rows += cell_rows('pair', key, 'A', g, cA, R['levels'], extra=ex, only=only)
        if cB is not None:
            rows += cell_rows('pair', key, 'B', g, cB, R['levels'], extra=ex, only=only)

    # ------------------------------------------------------------------------ triples: hot pair cell x third reading
    picked, per_trig = [], {}
    for score, x, ci, cA, cB, hot in rels:
        for lv in np.nonzero(hot.any(1))[0]:
            if per_trig.get(x[3], 0) >= MAX_PER_TRIGGER or len(picked) >= N_REL_TOP:
                break
            picked.append((x, ci, int(lv)))
            per_trig[x[3]] = per_trig.get(x[3], 0) + 1
    del rels
    n_tri = 0
    for n_t, n_hot, r in _pmap(_triple_job, picked, procs):
        tested['triple'] += n_t
        n_tri += n_hot
        rows += r
    log(f'{label}: triples done ({el()}); {len(picked)} pair cells, {tested["triple"]:,} cell-horizons tested, {n_tri:,} with a hot cell')
    _W.clear()

    df = rows.frame()
    df.insert(0, 'coin', label)
    df.to_csv(os.path.join(out, 'heat.csv.gz'), index=False, compression='gzip', float_format='%.6g')
    sha = hashlib.sha256()                                  # of the table's text (not of the gzip container)
    with gzip.open(os.path.join(out, 'heat.csv.gz'), 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            sha.update(chunk)
    base = {s: {'n': g.sp[s].base.get('n', 0), 'per_day': g.sp[s].base.get('per_day', 0),
                'hold_up': g.sp[s].base.get('hold_up'), 'hold_dn': g.sp[s].base.get('hold_dn'),
                **{str(H): g.sp[s].base[H] for H in HORIZONS if H in g.sp[s].base}} for s in SPLITS}
    meta = {'schema': 'oracle-heat-2', 'asset': asset, 'label': label, 'twin': int(twin), 'minutes': m['n'], 'gaps': int(m['gap'].sum()),
            'from': str(pd.Timestamp(m['t0'], unit='ms')), 'end': str(pd.Timestamp(min(end, HEAT_END), unit='ms')), 'heat_end': str(pd.Timestamp(HEAT_END, unit='ms')),
            'splits': {s: [str(pd.Timestamp(a, unit='ms')), str(pd.Timestamp(b, unit='ms'))] for s, (a, b) in SPLITS.items()},
            'readings': len(readings), 'curve_bins': n_curve, 'event_levels': len(singles), 'triggers': len(trig), 'conditions': len(conds),
            'tested': tested, 'relationships_hot': n_rels, 'relationships_written': min(n_rels, N_REL_WRITE), 'pair_hot_cells_A': n_hot_cells,
            'rows': len(df), 'talib': talib.__version__,
            'ta_lib_c': talib.__ta_version__.decode() if isinstance(talib.__ta_version__, bytes) else str(talib.__ta_version__), 'missing': missing,
            'excluded': EXCLUDED, 'bad_rows': m.get('bad_rows', 0), 'gap_runs': gap_runs, 'longest_gap': longest_gap, 'open_is_prev_close': open_same,
            'tick_bps': {s: float(np.median(lab['tick'][g.sp[s].rows])) if g.sp[s].N else None for s in SPLITS},
            'price_step': mu_step, 'table_sha256': sha.hexdigest(), 'edges': edges, 'base': base, 'seconds': round(time.time() - t_start)}
    with open(os.path.join(out, 'meta.json'), 'w') as f:
        json.dump(meta, f, indent=1)
    return meta


# -------------------------------------------------------------------------------------------------------------- league
TRACKS = {'move': ('excess', 't', 'lift', 't_lift', 'lift2', 't_lift2', 'deff'), 'odds': ('edge_p', 't_p', 'liftp', 't_liftp', 'liftp2', 't_liftp2', 'deff_p')}
OPTIONAL = ['lift', 't_lift', 'liftp', 't_liftp', 'lift2', 't_lift2', 'liftp2', 't_liftp2', 'deff', 'deff_p', 'rest_n', 'tod_excess', 'tod_edge_p', 'trig', 'cond', 'lv', 'series', 'bin', 'lo', 'hi', 'gap1',
            'best_up', 'best_dn', 'dip_up', 'dip_dn', 'bx_up25', 'bx_dn25', 'p_up', 'p_dn', 'median', 'tick', 'wd', 'size', 'hold_up', 'hold_dn']
VIEW = ['coin', 'kind', 'key', 'h', 'hs', 'dir', 'passes', 'q', 'n_A', 'days_A', 'per_day_A', 'move_A', 'odds_A', 't_A', 'n_B', 'days_B', 'per_day_B', 'wd_B',
        'move_B', 'odds_B', 'share_B', 'share_over_B', 'hold_B', 'hold_over_B', 't_B', 'heat_B', 'chance_heat', 'oheat_B', 'late_B', 'tod_B', 'lift_A', 't_lift_A', 'lift_B', 't_lift_B', 'lift2_B', 't_lift2_B',
        'bx25_B', 'best_B', 'dip_B', 'size_B', 'gap1_B', 'tick_B', 'trig', 'cond', 'lv']
TABLES = {'move_heat': ('move', 'heat_B', 0.0, 'by heat on B (windows per day x move, bps per day)'),
          'move_edge': ('move', 'move_B', 0.2, 'by move per event on B (bps; at least 0.2 windows per day)'),
          'odds_edge': ('odds', 'odds_B', 0.2, 'by odds edge per event on B (points of probability toward the direction; at least 0.2 windows per day)'),
          'odds_heat': ('odds', 'oheat_B', 0.0, 'by odds heat on B (windows per day x odds points)')}
FEE_POINTS = 2.75           # break-even odds shift at a 50c contract: taker fee 0.07 x 0.5 x 0.5 = 1.75c plus a 1c half spread


def _join(df: pd.DataFrame) -> pd.DataFrame:
    """One coin's rows: split A beside split B, one row per (kind, key, horizon)."""
    for c in OPTIONAL:
        if c not in df.columns:
            df[c] = np.nan
    KEY = ['kind', 'key', 'h']
    A = df[df.split == 'A'].drop(columns='split').set_index(KEY)
    B = df[df.split == 'B'].drop(columns=['split', 'coin', 'trig', 'cond', 'lv', 'series', 'bin', 'lo', 'hi']).set_index(KEY)
    return A.join(B, lsuffix='_A', rsuffix='_B', how='left').reset_index().copy()      # one block: columns are added after


def _judge(j: pd.DataFrame) -> pd.DataFrame:
    """Per track: hot on A (t distribution with the effective days; a move of at least one price step; a pair or triple
    must also beat BOTH its parents: its trigger's other events, by at least one price step, and the condition level's
    own effect), the one-sided p of B in A's direction (a pair or triple: the largest of its own p and its two lifts'
    p, so it must replicate as an ADDITION to both parents), and whether it replicates."""
    from scipy.stats import t as tdist
    combo = j.kind.isin(['pair', 'triple'])
    okA = (j.n_A >= MIN_EVENTS) & (j.days_A >= MIN_DAYS_A) & (~combo | (j.rest_n_A >= MIN_EVENTS))
    okB = (j.n_B >= MIN_EVENTS) & (j.days_B >= MIN_DAYS_B) & (~combo | (j.rest_n_B >= MIN_EVENTS))
    tickA = j.tick_A.fillna(0)
    bigA = (j.excess_A.abs() >= tickA) & (~combo | (j.lift_A.abs() >= tickA))    # at least one price step of the coin:
    bigB = j.excess_B.abs() >= j.tick_B.fillna(0)                                # less is rounding (bounce on a coarse tick)
    j['okA'] = okA
    for tr, (val, tc, lf, tl, lf2, tl2, de) in TRACKS.items():
        dA, dB = j[de + '_A'].fillna(j.days_A), j[de + '_B'].fillna(j.days_B)    # effective days (older tables: the day count)
        cH, cL = tcrit(dA, HOT_P / 2), tcrit(dA, REP_P)
        dfB = (np.floor(dB) - 1).clip(lower=1).fillna(1)
        d = np.sign(j[val + '_A']).fillna(0)
        two = bool(j[tl2 + '_A'].notna().any())             # the table carries the second lift (the condition's own effect)
        add = j[tl + '_A'] * d >= cL
        if two:
            add &= j[tl2 + '_A'] * d >= cL
        hot = okA & bigA & (j[tc + '_A'].abs() >= cH) & (~combo | add)
        sf = lambda t: np.where(okB & t.notna(), tdist.sf(t.fillna(0), dfB), 1.0)
        p, pl = sf(j[tc + '_B'] * d), sf(j[tl + '_B'] * d)
        if two:
            pl = np.maximum(pl, sf(j[tl2 + '_B'] * d))
        p = np.where(combo, np.maximum(p, pl), p)
        j[f'd_{tr}'], j[f'hot_{tr}'], j[f'p_{tr}'] = d.astype(np.int8), hot, p
        j[f'rep_{tr}'] = hot & okB & bigB & (p <= REP_P)
    return j


def _view(H: pd.DataFrame, tr: str) -> pd.DataFrame:
    """The hot rows of one track with every number signed in A's direction for that track."""
    val, tc, lf, tl, lf2, tl2, _ = TRACKS[tr]
    H = H[H[f'hot_{tr}']]
    d = H[f'd_{tr}'].astype(float)
    sc = 1.0 if tr == 'move' else 100.0
    v = H[['coin', 'kind', 'key', 'h', 'twin', 'tw', 'trig', 'cond', 'lv', 'n_A', 'days_A', 'per_day_A', 'n_B', 'days_B', 'per_day_B']].copy()
    v['dir'] = d.astype(int)
    v['move_A'], v['odds_A'], v['t_A'] = H.excess_A * d, H.edge_p_A * d * 100, H[tc + '_A'] * d
    v['move_B'], v['odds_B'], v['t_B'] = H.excess_B * d, H.edge_p_B * d * 100, H[tc + '_B'] * d
    v['wd_B'] = H.wd_B.fillna(H.per_day_B)                # distinct clock windows per day that hold an event (no overlap)
    v['heat_B'], v['oheat_B'] = v.wd_B * v.move_B, v.wd_B * v.odds_B
    with np.errstate(all='ignore'):
        se = H.se_B if tr == 'move' else (H.edge_p_B / H.t_p_B).abs() * 100
    v['chance_heat'] = v.wd_B * se * SQ2PI                # the size of heat this level shows by chance on B
    v['late_B'] = H.excessL_B * d                         # the same move entered one minute later
    v['tod_B'] = (H.tod_excess_B if tr == 'move' else H.tod_edge_p_B * 100) * d
    for s in 'AB':
        v[f'lift_{s}'], v[f't_lift_{s}'] = H[f'{lf}_{s}'] * d * sc, H[f'{tl}_{s}'] * d                 # over the trigger's other events
        v[f'lift2_{s}'], v[f't_lift2_{s}'] = H[f'{lf2}_{s}'] * d * sc, H[f'{tl2}_{s}'] * d            # over the condition's own effect
    v['share_B'] = np.where(d > 0, H.p_up_B, H.p_dn_B) * 100                    # share of events that went the reading's way
    v['share_over_B'] = v.share_B - np.where(d > 0, H.bp_up_B, H.bp_dn_B) * 100  # ... in points over all minutes of the check period
    v['hold_B'] = np.where(d > 0, H.hold_up_B, H.hold_dn_B)                      # minutes the price holds on the reading's side of the entry
    v['hold_over_B'] = v.hold_B - np.where(d > 0, H.bh_up_B, H.bh_dn_B)          # ... over all minutes of the check period
    v['bx25_B'] = np.where(d > 0, H.bx_up25_B, H.bx_dn25_B)
    v['best_B'] = np.where(d > 0, H.best_up_B, -H.best_dn_B)
    v['dip_B'] = np.where(d > 0, H.dip_up_B, -H.dip_dn_B)
    v['gap1_B'], v['size_B'], v['tick_B'] = H.gap1_B * d, H.size_B, H.tick_B
    v['rep'], v['p'], v['q'], v['passes'] = H[f'rep_{tr}'], H[f'p_{tr}'], H[f'q_{tr}'], H[f'bhy_{tr}']
    return v


DIR_MIN_WD = 0.2            # windows per day a level needs to enter the share-right ranking (once in five days)
DIR_COLS = ['coin', 'kind', 'key', 'h', 'hs', 'dir', 'passes', 'rep', 'hot', 'n_A', 'n_B', 'days_B', 'wd_B', 'share_A', 'share_B', 'share_over_B', 'odds_A', 'odds_B',
            't_A', 't_B', 'oheat_B', 'move_B', 'hold_B', 'hold_over_B', 'best_B', 'dip_B', 'tick_B']


def _direction(j: pd.DataFrame) -> pd.DataFrame:
    """Amendment 3: EVERY event level with a sample on both periods (30 events on 30 / 20 days), nothing cut by a
    significance bar. The direction is the one split A's odds showed; every B number is signed in that direction, so a
    level with no information scores about zero. Share right: events where price is beyond the entry by more than 1.5
    price steps in that direction at the horizon. Hold: minutes price stays on that side of the entry from the first
    close. Heat: distinct windows per day x the odds points (how often x how sure)."""
    x = j[(j.kind == 'single') & j.okA & (j.n_B >= MIN_EVENTS) & (j.days_B >= MIN_DAYS_B) & (j.d_odds != 0)]
    d = x.d_odds.astype(float)
    up = (d > 0).to_numpy()
    v = x[['coin', 'kind', 'key', 'h', 'twin', 'tw', 'n_A', 'n_B', 'days_B', 'tick_B']].copy()
    v['hs'] = x.h.astype(int).astype(str)
    v['dir'] = d.astype(int)
    v['wd_B'] = x.wd_B.fillna(x.per_day_B)
    v['share_A'], v['share_B'] = np.where(up, x.p_up_A, x.p_dn_A) * 100, np.where(up, x.p_up_B, x.p_dn_B) * 100
    v['share_over_B'] = v.share_B - np.where(up, x.bp_up_B, x.bp_dn_B) * 100
    v['odds_A'], v['odds_B'] = x.edge_p_A * d * 100, x.edge_p_B * d * 100
    v['t_A'], v['t_B'] = x.t_p_A * d, x.t_p_B * d
    v['oheat_B'] = v.wd_B * v.odds_B
    v['move_B'] = x.excess_B * d
    v['hold_B'] = np.where(up, x.hold_up_B, x.hold_dn_B)
    v['hold_over_B'] = v.hold_B - np.where(up, x.bh_up_B, x.bh_dn_B)
    v['best_B'], v['dip_B'] = np.where(up, x.best_up_B, -x.best_dn_B), np.where(up, x.dip_up_B, -x.dip_dn_B)
    v['hot'], v['rep'] = x.hot_odds.to_numpy(), x.rep_odds.to_numpy()
    return v


def _ta_league(j: pd.DataFrame) -> pd.DataFrame:
    """One row per reading and horizon: the heat of the reading as a whole, built on A and read on B.
    Curve heat (value readings): act in every non-overlapping H-minute window (at most once per bar of the reading's
    timeframe) in the direction the reading's current cell showed on A; bps per day. On B the same A directions are
    scored, so a reading with no information scores about zero and its t is close to standard normal (sd 1.0 to 1.4:
    cells that share days are added as if independent). A cell whose move is under one price step of the coin ON A
    counts as zero (below a step the "move" is rounding); on B a cell needs the replication sample (30 events on 20
    days) and is NOT filtered by the size of its B move (that would select on the number being tested).
    Event heat: the same over the reading's event levels (entering a zone, a flip, a pattern), in distinct windows."""
    parts = []
    c = j[(j.kind == 'curve') & (j.n_A >= MIN_EVENTS)]
    if len(c):
        k = ['series', 'h']
        wA, wB = c.n_A / c.groupby(k).n_A.transform('sum'), c.n_B / c.groupby(k).n_B.transform('sum')
        per = 1440.0 / np.maximum(c.h, c.series.str.extract(r'^(\d+)m:')[0].astype(float))      # decisions only at the reading's bar closes
        okA = c.excess_A.abs() >= c.tick_A.fillna(0)              # a cell whose move is under one price step counts as zero
        ok = okA & (c.n_B >= MIN_EVENTS) & (c.days_B >= MIN_DAYS_B)
        c = c.assign(reading=c.series, cells=1, nok=ok.astype(float), curve_heat_A=(wA * c.excess_A.abs() * per).where(okA, 0.0),
                     curve_heat_B=(wB * c.excess_B * np.sign(c.excess_A) * per).where(ok, 0.0),
                     v=((wB * c.se_B * per) ** 2).where(ok, 0.0), curve_odds_A=(wA * c.edge_p_A.abs() * 100).where(okA, 0.0),
                     curve_odds_B=(wB * c.edge_p_B * np.sign(c.edge_p_A) * 100).where(ok, 0.0))
        g = c.groupby(['reading', 'h'])[['cells', 'nok', 'curve_heat_A', 'curve_heat_B', 'v', 'curve_odds_A', 'curve_odds_B']].sum(min_count=1)
        g[['curve_heat_B', 'curve_odds_B']] = g[['curve_heat_B', 'curve_odds_B']].where(g.nok > 0)        # no cell with a B sample: no B number
        g['curve_t_B'] = (g.curve_heat_B / np.sqrt(g.v)).where(g.v > 0)
        parts.append(g.drop(columns=['v', 'nok']))
    e = j[(j.kind == 'single') & j.okA]
    if len(e):
        wdA, wdB = e.wd_A.fillna(e.per_day_A), e.wd_B.fillna(e.per_day_B)
        okA = e.excess_A.abs() >= e.tick_A.fillna(0)
        ok = okA & (e.n_B >= MIN_EVENTS) & (e.days_B >= MIN_DAYS_B)
        e = e.assign(reading=e.key.str.split('=').str[0].str.replace(' sign$', '', regex=True), levels=1, nok=ok.astype(float),
                     ev_heat_A=(wdA * e.excess_A.abs()).where(okA, 0.0),
                     ev_heat_B=(wdB * e.excess_B * np.sign(e.excess_A)).where(ok, 0.0), v=((wdB * e.se_B) ** 2).where(ok, 0.0))
        g = e.groupby(['reading', 'h'])[['levels', 'nok', 'ev_heat_A', 'ev_heat_B', 'v']].sum(min_count=1)
        g['ev_heat_B'] = g.ev_heat_B.where(g.nok > 0)
        g['ev_t_B'] = (g.ev_heat_B / np.sqrt(g.v)).where(g.v > 0)
        parts.append(g.drop(columns=['v', 'nok']))
    if not parts:
        return pd.DataFrame()
    return pd.concat(parts, axis=1).reset_index()


def _ta_best(ta: pd.DataFrame, a: str) -> pd.DataFrame:
    """Each reading at the horizon where its heat on A (column a) is largest: the choice uses A only."""
    x = ta.dropna(subset=[a])
    return x.loc[x.groupby(['coin', 'reading'])[a].idxmax()]


def _r(x, p=2):
    """Rounded list for JSON (NaN -> None)."""
    return [None if not np.isfinite(v) else (int(v) if p == 0 else round(float(v), p)) for v in np.asarray(x, float)]


def _viewer_coin(j: pd.DataFrame, n_rel: int = 60) -> dict:
    """One coin's compact viewer data: decile curves, event strips and the strongest relationships."""
    out = {'curves': {}, 'events': [], 'relations': []}
    c = j[j.kind == 'curve'].sort_values(['series', 'bin', 'h'])
    for series, x in c.groupby('series', sort=False):
        nb = x.bin.nunique()
        if len(x) != nb * len(HORIZONS):
            continue
        f = lambda col, p=1, sc=1.0: [_r(r, p) for r in (x[col].to_numpy(float) * sc).reshape(nb, len(HORIZONS)).T]
        out['curves'][series] = {'lo': _r(x.lo.to_numpy(float).reshape(nb, -1)[:, 0], 3), 'n': _r(x.n_A.to_numpy(float).reshape(nb, -1)[:, 0], 0),
                                 'nB': _r(x.n_B.to_numpy(float).reshape(nb, -1)[:, 0], 0),
                                 'mA': f('excess_A'), 'mB': f('excess_B'), 'oA': f('edge_p_A', 1, 100), 'oB': f('edge_p_B', 1, 100),
                                 'tA': f('t_A', 0), 'tB': f('t_B', 0), 'pA': f('t_p_A', 0), 'pB': f('t_p_B', 0)}
        fb = lambda m: [[int(v) for v in r] for r in np.asarray(m, bool).reshape(nb, len(HORIZONS)).T]
        up = (x.excess_A >= 0).to_numpy()
        fd = lambda u, dn: [_r(r, 1) for r in np.where(up, x[u].to_numpy(float), -x[dn].to_numpy(float)).reshape(nb, len(HORIZONS)).T]
        out['curves'][series].update(kA=fb(x.excess_A.abs() >= x.tick_A.fillna(0)), kB=fb(x.excess_B.abs() >= x.tick_B.fillna(0)),   # 1: at least one price step
                                     dA=fd('dip_up_A', 'dip_dn_A'), dB=fd('dip_up_B', 'dip_dn_B'))            # the usual dip against A's direction
    e = j[(j.kind == 'single') & j.okA].sort_values(['key', 'h'])
    for key, x in e.groupby('key', sort=False):
        if len(x) != len(HORIZONS):
            continue
        fl = (x.hot_move * 1 + x.rep_move * 2 + x.hot_odds * 4 + x.rep_odds * 8).tolist()
        out['events'].append([key, _r(x.wd_A, 2), _r(x.wd_B, 2), _r(x.excess_A, 1), _r(x.t_A, 0), _r(x.excess_B, 1), _r(x.t_B, 0),
                              _r(x.edge_p_A * 100, 1), _r(x.t_p_A, 0), _r(x.edge_p_B * 100, 1), _r(x.t_p_B, 0), fl])
    r = j[j.kind.isin(['pair', 'triple'])]
    if len(r):
        r = r.assign(rel=r.trig.astype(str) + ' | ' + r.cond.astype(str),
                     sc=np.where(r.rep_move | r.rep_odds,
                                 np.maximum(np.minimum(r.t_lift_B * r.d_move, (r.t_lift2_B * r.d_move).fillna(np.inf)).where(r.rep_move, 0),
                                            np.minimum(r.t_liftp_B * r.d_odds, (r.t_liftp2_B * r.d_odds).fillna(np.inf)).where(r.rep_odds, 0)), 0.0))
        best = r.groupby(['kind', 'rel']).sc.max().sort_values(ascending=False)
        best = best[best > 0]
        keep = list(best.groupby(level=0).head(n_rel).index)
        for kind, rel in keep:
            x = r[(r.kind == kind) & (r.rel == rel)].sort_values(['lv', 'h'])
            cells = []
            for lv, y in x.groupby('lv', sort=False):
                y = y.set_index('h').reindex(HORIZONS)
                cells.append({'lv': lv, 'nA': _r(y.n_A, 0)[0], 'nB': _r(y.n_B, 0)[0], 'mA': _r(y.excess_A, 1), 'mB': _r(y.excess_B, 1), 'lA': _r(y.lift_A, 1), 'lB': _r(y.lift_B, 1),
                              'tlA': _r(y.t_lift_A, 1), 'tlB': _r(y.t_lift_B, 1), 'oA': _r(y.edge_p_A * 100, 1), 'oB': _r(y.edge_p_B * 100, 1),
                              'loA': _r(y.liftp_A * 100, 1), 'loB': _r(y.liftp_B * 100, 1), 'tpA': _r(y.t_liftp_A, 1), 'tpB': _r(y.t_liftp_B, 1),
                              'l2A': _r(y.lift2_A, 1), 'l2B': _r(y.lift2_B, 1), 'lo2A': _r(y.liftp2_A * 100, 1), 'lo2B': _r(y.liftp2_B * 100, 1),
                              'fl': (y.hot_move.fillna(False) * 1 + y.rep_move.fillna(False) * 2 + y.hot_odds.fillna(False) * 4 + y.rep_odds.fillna(False) * 8).astype(int).tolist()})
            out['relations'].append({'kind': kind, 'trig': x.trig.iloc[0], 'cond': x.cond.iloc[0], 'cells': cells})
    return out


def league(inputs: str, out: str, top: int = 40) -> dict:
    from scipy.stats import spearmanr
    from oracle.sim import bhy_adjust
    os.makedirs(out, exist_ok=True)
    dirs = [d for d in sorted(os.listdir(inputs)) if os.path.exists(os.path.join(inputs, d, 'heat.csv.gz'))]
    if not dirs:
        raise SystemExit('no coin outputs')
    for f in ('strips.csv.gz', 'curves.csv.gz', 'relations.csv.gz'):
        if os.path.exists(os.path.join(out, f)):
            os.remove(os.path.join(out, f))
    metas, hots, counts, tt, viewer, tas, pads, sets, dirs_ = {}, [], {}, {}, {}, [], {}, {}, []
    s_cols = ['coin', 'key', 'h', 'n_A', 'days_A', 'deff_A', 'per_day_A', 'wd_A', 'wd_B', 'tick_A', 'tick_B', 'excess_A', 't_A', 'edge_p_A', 't_p_A', 'tod_excess_A', 'excessL_A', 'gap1_A', 'p_up_A', 'p_dn_A',
              'median_A', 'best_up_A', 'best_dn_A', 'dip_up_A', 'dip_dn_A', 'bx_up25_A', 'bx_dn25_A', 'hold_up_A', 'hold_dn_A', 'n_B', 'days_B', 'per_day_B', 'excess_B', 'se_B', 't_B',
              'edge_p_B', 't_p_B', 'p_up_B', 'p_dn_B', 'hold_up_B', 'hold_dn_B', 'tod_excess_B', 'excessL_B', 'best_up_B', 'best_dn_B', 'dip_up_B', 'dip_dn_B', 'bx_up25_B', 'bx_dn25_B',
              'hot_move', 'rep_move', 'p_move', 'hot_odds', 'rep_odds', 'p_odds']
    c_cols = ['coin', 'series', 'bin', 'lo', 'hi', 'h', 'n_A', 'days_A', 'excess_A', 't_A', 'edge_p_A', 't_p_A', 'tick_A', 'p_up_A', 'p_dn_A', 'dip_up_A', 'dip_dn_A',
              'hold_up_A', 'hold_dn_A', 'n_B', 'days_B', 'excess_B', 't_B', 'edge_p_B', 't_p_B', 'tick_B', 'p_up_B', 'p_dn_B', 'dip_up_B', 'dip_dn_B', 'hold_up_B', 'hold_dn_B', 'hot_move', 'rep_move', 'hot_odds', 'rep_odds']
    r_cols = ['coin', 'kind', 'trig', 'cond', 'lv', 'h', 'n_A', 'days_A', 'excess_A', 't_A', 'lift_A', 't_lift_A', 'lift2_A', 't_lift2_A', 'edge_p_A', 't_p_A',
              'liftp_A', 't_liftp_A', 'liftp2_A', 't_liftp2_A', 'tick_A', 'p_up_A', 'p_dn_A', 'dip_up_A', 'dip_dn_A',
              'n_B', 'days_B', 'excess_B', 't_B', 'lift_B', 't_lift_B', 'lift2_B', 't_lift2_B', 'edge_p_B', 't_p_B', 'liftp_B', 't_liftp_B', 'liftp2_B', 't_liftp2_B',
              'tick_B', 'p_up_B', 'p_dn_B', 'dip_up_B', 'dip_dn_B', 'hold_up_B', 'hold_dn_B',
              'hot_move', 'rep_move', 'p_move', 'hot_odds', 'rep_odds', 'p_odds']

    def put(df, cols, name):
        f = os.path.join(out, name)
        df[[c for c in cols if c in df.columns]].to_csv(f, index=False, compression='gzip', float_format='%.5g', mode='a', header=not os.path.exists(f))

    n_rows = 0
    for d in dirs:
        mt = json.load(open(os.path.join(inputs, d, 'meta.json')))
        label, twi = mt['label'], int(mt['twin'])           # twi 0: the coin; n > 0: its n-th no-signal twin (set n across the coins)
        tw = twi > 0
        metas[label] = mt
        sets.setdefault(twi, []).append(mt['asset'])
        df = pd.read_csv(os.path.join(inputs, d, 'heat.csv.gz'), low_memory=False)
        n_rows += len(df)
        j = _judge(_join(df))
        del df
        j['twin'], j['tw'] = tw, twi
        bB = mt.get('base', {}).get('B', {})
        j['bp_up_B'] = j.h.map(lambda H: bB.get(str(int(H)), {}).get('p_up', np.nan))
        j['bp_dn_B'] = j.h.map(lambda H: bB.get(str(int(H)), {}).get('p_dn', np.nan))
        j['bh_up_B'], j['bh_dn_B'] = bB.get('hold_up') or np.nan, bB.get('hold_dn') or np.nan      # base: minutes held on each side
        for kind in ('single', 'curve', 'pair', 'triple'):
            x = j[j.kind == kind]
            c = counts.setdefault((twi, kind), {'tested': 0, 'move': [0, 0], 'odds': [0, 0]})
            c['tested'] += int(mt['tested'][kind]) if kind in ('pair', 'triple') else int(x.okA.sum())
            for tr in TRACKS:
                c[tr][0] += int(x[f'hot_{tr}'].sum())
                c[tr][1] += int(x[f'rep_{tr}'].sum())
            if kind in ('single', 'curve'):             # rank agreement of A and B over rows whose A move is at least one price step
                z = x[x.okA & (x.n_B >= MIN_EVENTS) & (x.excess_A.abs() >= x.tick_A.fillna(0))][['t_A', 't_B', 't_p_A', 't_p_B']].dropna()
                tt.setdefault((tw, kind), []).append(z)
            if kind == 'pair' and mt.get('relationships_written', 0) < mt.get('relationships_hot', 0):
                # the weakest hot relationships were not written: they stay in the BHY family as p = 1
                pads[(twi, kind)] = pads.get((twi, kind), 0) + max(0, int(mt.get('pair_hot_cells_A', 0)) - int((x.hot_move | x.hot_odds).sum()))
        put(j[j.kind == 'single'], s_cols, 'strips.csv.gz')
        put(j[j.kind == 'curve'], c_cols, 'curves.csv.gz')
        put(j[j.kind.isin(['pair', 'triple'])], r_cols, 'relations.csv.gz')
        ta = _ta_league(j)
        if len(ta):
            tas.append(ta.assign(coin=label, twin=tw))
        if not tw:
            viewer[label] = _viewer_coin(j)
            if len(ta):
                viewer[label]['ta'] = {r: {c: _r(x.set_index('h').reindex(HORIZONS)[c], 1) for c in ('curve_heat_A', 'curve_heat_B', 'curve_t_B', 'curve_odds_B',
                                                                                                'ev_heat_A', 'ev_heat_B', 'ev_t_B') if c in x.columns}
                                       for r, x in ta.groupby('reading')}
        hots.append(j[(j.hot_move | j.hot_odds) & (j.kind != 'curve')])
        dirs_.append(_direction(j))
        del j
    H = pd.concat(hots, ignore_index=True)
    for tr in TRACKS:                                           # BHY inside each family: the coins or one twin set x kind x track
        H[f'q_{tr}'] = np.nan
        for (twi, kind), idx in H[H[f'hot_{tr}']].groupby(['tw', 'kind']).groups.items():
            pv, k = H.loc[idx, f'p_{tr}'].to_numpy(), pads.get((twi, kind), 0)
            H.loc[idx, f'q_{tr}'] = bhy_adjust(np.r_[pv, np.ones(k)])[:len(pv)] if k else bhy_adjust(pv)
        H[f'bhy_{tr}'] = H[f'rep_{tr}'] & (H[f'q_{tr}'] <= 0.10)
    views = {tr: _view(H, tr) for tr in TRACKS}

    coins = sorted(k for k, v in metas.items() if not v['twin'])
    twins = sorted(k for k, v in metas.items() if v['twin'])
    summary = {'schema': 'oracle-heat-league-2', 'coins': coins, 'twins': twins, 'rows': int(n_rows), 'by_kind': {},
               'twin_sets': {str(k): sorted(v) for k, v in sorted(sets.items()) if k > 0}, 'bhy_padding': {f'{k[0]}:{k[1]}': v for k, v in pads.items() if v}}
    KINDS = ('single', 'curve', 'pair', 'triple')

    def one(twi, kind):
        c = counts.get((twi, kind))
        if c is None:
            return None
        sm = {'tested': c['tested']}
        for tr in TRACKS:
            hot, rep = c[tr]
            v = views[tr]
            sm[tr] = {'hot': hot, 'replicate': rep, 'share': round(rep / hot, 4) if hot else None,
                      'bhy': int((v.passes & (v.tw == twi) & (v.kind == kind)).sum()) if kind != 'curve' else None}
        return sm

    def rank_agreement(sm, tw, kind):
        z = pd.concat(tt.get((tw, kind), []) or [pd.DataFrame()])
        if len(z) > 10:
            sm['spearman_t_A_B'] = round(float(spearmanr(z.t_A, z.t_B).correlation), 3)
            sm['spearman_tp_A_B'] = round(float(spearmanr(z.t_p_A, z.t_p_B).correlation), 3)

    for kind in KINDS:
        sm = one(0, kind)
        if sm is not None:
            rank_agreement(sm, False, kind)
            summary['by_kind'][kind] = sm
    tsets = [k for k in sorted(sets) if k > 0]
    num = lambda x: int(x) if float(x).is_integer() else round(float(x), 1)
    for kind in KINDS:                          # the twins: the median over the twin sets (each set = one twin of every coin) and the range
        per = [x for x in (one(t, kind) for t in tsets) if x is not None]
        if not per:
            continue
        sm = {'tested': num(np.median([x['tested'] for x in per])), 'sets': len(per)}
        for tr in TRACKS:
            sm[tr] = {'range': {}}
            for f in ('hot', 'replicate', 'share', 'bhy'):
                vals = [x[tr][f] for x in per]
                if any(v is None for v in vals):
                    sm[tr][f] = None
                    continue
                sm[tr][f] = round(float(np.median(vals)), 4) if f == 'share' else num(np.median(vals))
                if f != 'share':
                    sm[tr]['range'][f] = [int(min(vals)), int(max(vals))]
        rank_agreement(sm, True, kind)
        summary['by_kind']['twin:' + kind] = sm

    def table(tr, metric, min_pd, twin=False):
        v = views[tr]
        x = v[v.rep & (v.twin == twin) & (v.wd_B >= min_pd)].sort_values(['passes', metric], ascending=[False, False])
        if len(x):
            x = x.assign(hs=x.groupby(['coin', 'kind', 'key']).h.transform(lambda z: '/'.join(str(int(i)) for i in sorted(z))))
        else:
            x = x.assign(hs='')
        return x.drop_duplicates(['coin', 'kind', 'key'])[VIEW]

    tabs = {nm: table(tr, metric, min_pd) for nm, (tr, metric, min_pd, _) in TABLES.items()}
    summary['twin_best'] = {}
    for nm, (tr, metric, min_pd, _) in TABLES.items():
        x = table(tr, metric, min_pd, twin=True)
        summary['twin_best'][nm] = None if x.empty else round(float(x[metric].max()), 3)
    D = pd.concat(dirs_, ignore_index=True)
    ps = views['odds'][['coin', 'key', 'h', 'passes']].drop_duplicates(['coin', 'key', 'h'])
    D = D.merge(ps, on=['coin', 'key', 'h'], how='left')
    D['passes'] = D.passes.fillna(False).astype(bool)
    summary['direction'] = {}
    for Hh in HORIZONS:                                         # does A's direction carry to B: every level, the coins beside the twins
        for tw, nm in ((False, 'real'), (True, 'twin')):
            x = D[(D.h == Hh) & (D.twin == tw)]
            if len(x):
                summary['direction'].setdefault(str(Hh), {})[nm] = {
                    'levels': int(len(x)), 'kept_direction_on_B': round(float((x.odds_B > 0).mean()), 4), 't_B_2_or_more': round(float((x.t_B >= 2).mean()), 4),
                    'median_odds_B': round(float(x.odds_B.median()), 3), 'p99_odds_heat_B': round(float(x.oheat_B.quantile(0.99)), 3),
                    'max_odds_heat_B': round(float(x.oheat_B.max()), 3), 'median_hold_over_B': round(float(x.hold_over_B.median()), 3)}
                y = x[x.wd_B >= DIR_MIN_WD].share_over_B.dropna()
                if len(y):                                      # the share-right scale among levels that fire at least once in five days
                    summary['direction'][str(Hh)][nm].update(p99_share_over_B=round(float(y.quantile(0.99)), 2), max_share_over_B=round(float(y.max()), 2))
    DR = D[~D.twin].sort_values('oheat_B', ascending=False)
    DR[DIR_COLS].to_csv(os.path.join(out, 'direction_all.csv.gz'), index=False, compression='gzip', float_format='%.5g')      # every level
    DR[DIR_COLS].head(5000).to_csv(os.path.join(out, 'league_direction.csv.gz'), index=False, compression='gzip', float_format='%.5g')
    # per horizon the 60 hottest levels and the 60 with the largest share right over base (the csv has every level)
    dir_top = pd.concat([DR.groupby('h', sort=True).head(60),
                         DR[DR.wd_B >= DIR_MIN_WD].sort_values('share_over_B', ascending=False).groupby('h', sort=True).head(60)]
                        ).drop_duplicates(['coin', 'key', 'h']).sort_values('oheat_B', ascending=False)[DIR_COLS]
    summary['twin_best']['direction'] = None if not D.twin.any() else round(float(D[D.twin].oheat_B.max()), 3)
    pd.concat([views[tr].assign(track=tr) for tr in TRACKS])[lambda x: ~x.twin].drop(columns='twin').to_csv(
        os.path.join(out, 'hot.csv.gz'), index=False, compression='gzip', float_format='%.6g')
    for nm, tdf in tabs.items():
        tdf.head(5000).to_csv(os.path.join(out, f'league_{nm}.csv.gz'), index=False, compression='gzip', float_format='%.6g')
    summary['metas'] = {k: {x: v.get(x) for x in ('from', 'end', 'minutes', 'gaps', 'gap_runs', 'longest_gap', 'bad_rows', 'open_is_prev_close', 'tick_bps',
                                                  'readings', 'curve_bins', 'event_levels', 'triggers', 'conditions', 'tested', 'relationships_hot',
                                                  'relationships_written', 'pair_hot_cells_A', 'rows', 'heat_end', 'price_step', 'table_sha256',
                                                  'seconds', 'talib', 'ta_lib_c', 'missing', 'excluded')} for k, v in metas.items()}
    # every TA by heat: all readings, cold ones too, each at its best horizon on A, read on B; the twins give the chance level
    TA = pd.concat(tas, ignore_index=True) if tas else pd.DataFrame()
    summary['ta'], ta_top = {}, {}
    if len(TA):
        TA.to_csv(os.path.join(out, 'league_ta.csv.gz'), index=False, compression='gzip', float_format='%.5g')
        for what, a, b, t in (('curve', 'curve_heat_A', 'curve_heat_B', 'curve_t_B'), ('events', 'ev_heat_A', 'ev_heat_B', 'ev_t_B')):
            if a not in TA.columns:
                continue
            best = _ta_best(TA, a).dropna(subset=[b])
            for tw in (False, True):
                x = best[best.twin == tw]
                if len(x):
                    summary['ta'][('twin:' if tw else '') + what] = {
                        'readings': int(len(x)), 'positive_on_B': round(float((x[b] > 0).mean()), 4), 't_B_2_or_more': round(float((x[t] >= 2).mean()), 4),
                        't_B_3_or_more': round(float((x[t] >= 3).mean()), 4), 'median_heat_B': round(float(x[b].median()), 3),
                        'p95_heat_B': round(float(x[b].quantile(0.95)), 3), 'max_heat_B': round(float(x[b].max()), 3)}
            ta_top[what] = best[~best.twin].sort_values(b, ascending=False)
        summary['top_ta'] = {what: json.loads(x.head(top).drop(columns='twin').to_json(orient='records', double_precision=3)) for what, x in ta_top.items()}
    summary['top'] = {nm: json.loads(tdf.head(top).to_json(orient='records', double_precision=4)) for nm, tdf in tabs.items()}
    with open(os.path.join(out, 'summary.json'), 'w') as f:
        json.dump(summary, f, indent=1, allow_nan=False)
    with open(os.path.join(out, 'league.md'), 'w') as f:
        f.write(league_md(summary, tabs, top, ta_top, dir_top))
    import gzip
    vw = {'schema': 'oracle-heat-viewer-1', 'coins': coins, 'twins': twins, 'horizons': HORIZONS, 'by_kind': summary['by_kind'], 'twin_best': summary['twin_best'],
          'league': {'direction': json.loads(dir_top.to_json(orient='records', double_precision=3)),
                     **{nm: json.loads(tdf.head(300).to_json(orient='records', double_precision=3)) for nm, tdf in tabs.items()}},
          'direction': summary['direction'],
          'ta': summary.get('ta', {}), 'fee_points': FEE_POINTS, 'metas': summary['metas'],
          'edges': {k: {a: [round(float(q), 4) for q in e] for a, e in metas[k].get('edges', {}).items()} for k in coins}, 'coin': viewer}
    with gzip.open(os.path.join(out, 'viewer.json.gz'), 'wt') as f:
        json.dump(vw, f, separators=(',', ':'), allow_nan=False)
    return summary


def league_md(summary: dict, tabs: dict, top: int, ta_top: dict = None, dir_top: pd.DataFrame = None) -> str:
    exp = ['BTC', 'ETH', 'SOL', 'XRP']
    md = ['# OR-HM1 heat map: league (coin price, discovery only)', '',
          f"Coins: {', '.join(summary['coins']) or 'none'}. No-signal twins: {', '.join(summary['twins']) or 'none'}.",
          'Build A 2020-01-01..2025-01-01, check B 2025-01-01..2026-01-01 (no minute of 2026 is read). Entry at the next minute\'s open. A map, not a validated rule.']
    if sorted(summary['coins']) != exp:
        md.append(f'**WARNING: expected {", ".join(exp)}; this league is partial.**')
    ts = summary.get('twin_sets', {})
    if not ts:
        md.append('**WARNING: no twin was run; there is no chance yardstick beside the counts.**')
    elif any(sorted(v) != sorted(summary['coins']) for v in ts.values()):
        md.append('**WARNING: the twin sets do not cover the same coins: ' + '; '.join(f'set {k}: {", ".join(v)}' for k, v in ts.items()) + '.**')
    md += ['', '## Hot spots against chance', '',
           'Hot: on A the level differs from the base rate (two-sided p <= 0.0027, the t = 3 bar; a pair or triple must also beat its parent\'s other '
           'events, one-sided p <= 0.023). Replicates: B agrees in the same direction (one-sided p <= 0.023; a pair or triple also on its lift). '
           'BHY: survives the multiple-testing correction at q 0.10 inside its kind. The twin rows are the same pipeline on the coins with the '
           'direction of every minute replaced by a coin flip: what chance alone produces. With several twin sets the twin row is the median '
           'and, in brackets, the lowest and highest set: twin counts are clumpy (readings overlap), so only a count well above the highest '
           'set, a higher replicate share and the BHY column are evidence.', '',
           '| set | kind | tested on A | hot (move) | replicate | share | BHY | hot (odds) | replicate | share | BHY |',
           '|---|---|---|---|---|---|---|---|---|---|---|']
    nn = lambda x: '' if x is None else x
    def cnt(x, f):
        v, r = x.get(f), (x.get('range') or {}).get(f)
        if v is None:
            return ''
        return f'{v:,}' + (f' ({r[0]:,} to {r[1]:,})' if r and r[0] != r[1] else '')
    for k, sm in summary['by_kind'].items():
        a, b = sm['move'], sm['odds']
        who = f"twin (median of {sm['sets']})" if k.startswith('twin:') and sm.get('sets', 1) > 1 else 'twin' if k.startswith('twin:') else 'real'
        md.append(f"| {who} | {k.replace('twin:', '')} | {sm['tested']:,} | {cnt(a, 'hot')} | {cnt(a, 'replicate')} | {nn(a['share'])} | {cnt(a, 'bhy')} | "
                  f"{cnt(b, 'hot')} | {cnt(b, 'replicate')} | {nn(b['share'])} | {cnt(b, 'bhy')} |")
    if summary.get('bhy_padding'):
        md += ['', 'Not every hot relationship was written (the weakest by lift were left out); they are counted in the BHY family as failures: '
               + ', '.join(f'{k} {v:,}' for k, v in summary['bhy_padding'].items()) + '.']
    tb = summary.get('twin_best', {})
    md += ['', 'Best replicating twin row over all twin sets (what the top of each list looks like by chance; the yardstick for the lists below): ' +
           ', '.join(f"{nm} {tb.get(nm)}" for nm in TABLES) + '.', '']

    def f(x, p=1, plus=False):
        if x is None or (isinstance(x, float) and not np.isfinite(x)):
            return ''
        return f'{x:+.{p}f}' if plus else f'{x:.{p}f}'
    if dir_top is not None and len(dir_top):
        md += ['## Direction: every event level, nothing cut (Amendment 3)', '',
               'The question: can direction be detected, and does it hold for at least a minute. Every event level with a sample on both periods '
               '(30 events) is listed in direction_all.csv.gz (the 5,000 hottest in league_direction.csv.gz); no significance bar removes a row. The direction is the one the build years showed; the '
               'check-year numbers are signed in it, so a level with no information scores about zero. Kept direction: the share of levels whose odds on '
               'the check year point the same way (a coin flip gives about 0.5). The twin row is the same count on the no-signal twins.', '',
               '| minutes | set | levels | kept direction on B | t B >= 2 | median odds B pts | 99th pct odds heat B | max odds heat B | median hold over base, min |',
               '|---|---|---|---|---|---|---|---|---|']
        for Hh, v in summary.get('direction', {}).items():
            for nm in ('real', 'twin'):
                if nm in v:
                    w = v[nm]
                    md.append(f"| {Hh} | {nm} | {w['levels']:,} | {w['kept_direction_on_B']} | {w['t_B_2_or_more']} | {w['median_odds_B']} | {w['p99_odds_heat_B']} | "
                              f"{w['max_odds_heat_B']} | {w['median_hold_over_B']} |")
        md += ['', 'Share right: events where price is beyond the entry (by more than 1.5 price steps) in the direction at that minute. Hold: minutes price stays '
               'on that side of the entry from the first close; over base: against all minutes. Best move and usual dip: inside the window, bps. '
               'Heat: windows per day x odds points. The marks (hot on A, replicates, BHY) are information only.', '']
        for Hh in sorted(dir_top.h.unique()):
            x = dir_top[dir_top.h == Hh].head(12)
            md += [f'Top {len(x)} at {int(Hh)} minute{"s" if Hh != 1 else ""} by heat on B:', '',
                   '| coin | event | dir | windows/day B | share right A % | share right B % | over base pts | odds B pts | t B | heat B | hold B min | over base | best move bps | usual dip bps | marks |',
                   '|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|']
            for r in x.itertuples():
                marks = ', '.join(nm for nm, on in (('hot', r.hot), ('replicates', r.rep), ('BHY', r.passes)) if on) or 'none'
                md.append(f"| {r.coin} | {str(r.key).replace('|', '/')} | {'up' if r.dir > 0 else 'down'} | {f(r.wd_B, 2)} | {f(r.share_A, 1)} | {f(r.share_B, 1)} | "
                          f"{f(r.share_over_B, 1, True)} | {f(r.odds_B, 1, True)} | {f(r.t_B, 1, True)} | {f(r.oheat_B, 1)} | {f(r.hold_B, 1)} | {f(r.hold_over_B, 1, True)} | "
                          f"{f(r.best_B, 1, True)} | {f(r.dip_B, 1, True)} | {marks} |")
            md.append('')
            y = dir_top[(dir_top.h == Hh) & (dir_top.wd_B >= DIR_MIN_WD)].sort_values('share_over_B', ascending=False).head(8)
            sc = summary.get('direction', {}).get(str(int(Hh)), {}).get('twin', {})
            md += [f'Top {len(y)} at {int(Hh)} minute{"s" if Hh != 1 else ""} by share right over base on B (at least {DIR_MIN_WD} windows per day; '
                   f'the best twin level reaches {sc.get("max_share_over_B", "n/a")} points, the 99th percentile {sc.get("p99_share_over_B", "n/a")}):', '',
                   '| coin | event | dir | windows/day B | events B | share right B % | over base pts | t B | hold B min | over base | usual dip bps | marks |', '|---|---|---|---|---|---|---|---|---|---|---|---|']
            for r in y.itertuples():
                marks = ', '.join(nm for nm, on in (('hot', r.hot), ('replicates', r.rep), ('BHY', r.passes)) if on) or 'none'
                md.append(f"| {r.coin} | {str(r.key).replace('|', '/')} | {'up' if r.dir > 0 else 'down'} | {f(r.wd_B, 2)} | {int(r.n_B):,} | {f(r.share_B, 1)} | {f(r.share_over_B, 1, True)} | "
                          f"{f(r.t_B, 1, True)} | {f(r.hold_B, 1)} | {f(r.hold_over_B, 1, True)} | {f(r.dip_B, 1, True)} | {marks} |")
            md.append('')
    if ta_top:
        md += ['## Every TA by heat', '',
               'Each reading as a whole (all readings are in league_ta.csv.gz, cold ones too). Curve heat: act in every non-overlapping window in the '
               'direction the reading\'s current value showed on A; bps per day. Event heat: the same over its events (entering a zone, a flip, a pattern). '
               'The horizon is the one with the most heat on A; the B columns score A\'s directions on B, so a reading with no information scores about zero.', '',
               '| set | what | readings | positive on B | t B >= 2 | t B >= 3 | median heat B | 95th pct heat B | max heat B |', '|---|---|---|---|---|---|---|---|---|']
        for k, v in summary['ta'].items():
            md.append(f"| {'twin' if k.startswith('twin:') else 'real'} | {k.replace('twin:', '')} | {v['readings']:,} | {v['positive_on_B']} | {v['t_B_2_or_more']} | "
                      f"{v['t_B_3_or_more']} | {v['median_heat_B']} | {v['p95_heat_B']} | {v['max_heat_B']} |")
        for what, (a, b, t) in (('curve', ('curve_heat_A', 'curve_heat_B', 'curve_t_B')), ('events', ('ev_heat_A', 'ev_heat_B', 'ev_t_B'))):
            if what not in ta_top:
                continue
            md += ['', f'Top {min(top, len(ta_top[what]))} readings by {what} heat on B:', '', '| coin | reading | minutes | heat A | heat B | t B |', '|---|---|---|---|---|---|']
            for r in ta_top[what].head(top).itertuples():
                md.append(f"| {r.coin} | {r.reading} | {r.h} | {f(getattr(r, a), 1)} | {f(getattr(r, b), 1, True)} | {f(getattr(r, t), 1, True)} |")
        md.append('')
    for nm, (tr, metric, min_pd, title) in TABLES.items():
        tdf = tabs[nm]
        md += [f'## Top {min(top, len(tdf))} replicating {title}', '',
               f'{int(tdf.passes.sum()):,} of {len(tdf):,} replicating readings pass BHY; they are listed first. All numbers are in the direction found on A. '
               f'For scale: an odds edge has to beat about {FEE_POINTS} points to cover the fee and spread of a 50c contract held to settlement. '
               'Odds: half the shift in P(up) - P(down), in points; it equals the shift in the chance of an up close when no outcome is flat (on a '
               'coarse-step coin many 5-minute outcomes are flat, so the fee scale is loose there). '
               'Share right: the share of events where price went the reading\'s way by more than 1.5 price steps; over base: against all minutes of the check period. '
               'Usual dip: the average move against the direction before the best point inside the window. Coin price only: Kalshi fees enter at the next stage.', '',
               '| coin | kind | reading(s) | minutes | dir | BHY | windows/day B | move B bps | odds B pts | share right B % | over base pts | hold B min | usual dip bps | t B | heat B | 1-min-late move | time-of-day part | lift B over trigger | lift B over condition | q |',
               '|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|']
        for r in tdf.head(top).itertuples():
            md.append(f"| {r.coin} | {r.kind} | {str(r.key).replace('|', '/')} | {r.hs} | {'up' if r.dir > 0 else 'down'} | {'yes' if r.passes else 'no'} | {f(r.wd_B, 2)} | "
                      f"{f(r.move_B, 1, True)} | {f(r.odds_B, 1, True)} | {f(r.share_B, 1)} | {f(r.share_over_B, 1, True)} | {f(r.hold_B, 1)} | {f(r.dip_B, 1, True)} | {f(r.t_B, 1, True)} | {f(r.heat_B if tr == 'move' else r.oheat_B, 1)} | "
                      f"{f(r.late_B, 1, True)} | {f(r.tod_B, 1, True)} | {f(r.lift_B, 1, True)} | {f(r.lift2_B, 1, True)} | {f(r.q, 3)} |")
        md.append('')
    md += ['## Tables', '', 'One table per series; the hash is the sha256 of the table text (heat.csv.gz, unzipped). No minute at or after the cut-off is read.', '',
           '| series | from | cut-off (exclusive) | minutes | gap minutes | price unit | table sha256 |', '|---|---|---|---|---|---|---|']
    for k in sorted(summary.get('metas', {})):
        v = summary['metas'][k]
        md.append(f"| {k} | {str(v.get('from'))[:10]} | {str(v.get('end'))[:10]} | {v.get('minutes') or 0:,} | {v.get('gaps') or 0:,} | {v.get('price_step') or 'not on a grid'} | {v.get('table_sha256')} |")
    return '\n'.join(md) + '\n'


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest='cmd', required=True)
    a = sp.add_parser('coin')
    a.add_argument('--asset', required=True)
    a.add_argument('--csv', required=True)
    a.add_argument('--dom', required=True)
    a.add_argument('--out', required=True)
    a.add_argument('--twin', type=int, default=0)
    a.add_argument('--procs', type=int, default=0)
    b = sp.add_parser('league')
    b.add_argument('--inputs', required=True)
    b.add_argument('--out', required=True)
    x = ap.parse_args()
    if x.cmd == 'coin':
        mt = run_coin(x.asset, x.csv, x.dom, x.out, twin=x.twin, procs=x.procs)
        print(json.dumps({k: v for k, v in mt.items() if k not in ('base', 'edges')}, indent=1))
    else:
        s = league(x.inputs, x.out)
        print(json.dumps(s['by_kind'], indent=1))


if __name__ == '__main__':
    main()
