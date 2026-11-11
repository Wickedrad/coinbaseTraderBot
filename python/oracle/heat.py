"""OR-HM1 heat strips and confluence matrix on coin price (python/oracle/prereg/OR-HM1.md).

  python3 -m oracle.heat coin  --asset BTC --csv 1m.csv --dom research/btcd_fractal/data --out out/BTC
  python3 -m oracle.heat league --inputs out --out out/league

Never loads a bar at or after DEV_END. NEVER DOGE. Aggregates only in the outputs (no per-minute rows).
"""
import argparse
import gzip
import json
import math
import os
import time

import numpy as np
import pandas as pd

from oracle.common import DAY, DEV_END, MIN, ms

HORIZONS = [5, 15, 30, 60]
HMAX = max(HORIZONS)
TFS = [1, 5, 15, 60]
TOUCH = [10, 25, 50]
SPLITS = {'A': (ms('2020-01-01'), ms('2025-01-01')), 'B': (ms('2025-01-01'), DEV_END)}
SEEDS = 8
N_CAND = 120
N_PAIR_TOP = 40
MIN_EVENTS = 30
HOT_T = 3.0


# ---------------------------------------------------------------------------------------------------------------- data
def load_minutes(path: str, start: int = SPLITS['A'][0], end: int = DEV_END) -> dict:
    """Complete 1-minute grid from the first UTC midnight on or after the data start (>= start) to end (exclusive)."""
    df = pd.read_csv(path)
    df = df[(df['ts'] >= start) & (df['ts'] < end)].drop_duplicates('ts').sort_values('ts')
    if df.empty:
        raise SystemExit(f'{path}: no rows in range')
    t0 = int(-(-int(df['ts'].iloc[0]) // DAY) * DAY)
    df = df[df['ts'] >= t0]
    n = int((end - t0) // MIN)
    n -= n % 60
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
    v[pos] = df['v'].to_numpy(float)
    tb = None
    if 'tb' in df.columns:
        tb = np.zeros(n)
        tb[pos] = df['tb'].to_numpy(float)
    return {'t0': t0, 'n': n, 'o': o, 'h': h, 'l': l, 'c': c, 'v': v, 'tb': tb, 'gap': gap}


def resample(m: dict, k: int) -> dict:
    if k == 1:
        return {x: m[x] for x in ('o', 'h', 'l', 'c', 'v', 'tb')}
    nb = m['n'] // k
    r = lambda a: a[:nb * k].reshape(nb, k)
    out = {'o': r(m['o'])[:, 0].copy(), 'h': r(m['h']).max(1), 'l': r(m['l']).min(1), 'c': r(m['c'])[:, -1].copy(),
           'v': r(m['v']).sum(1), 'tb': None if m['tb'] is None else r(m['tb']).sum(1)}
    return out


# ------------------------------------------------------------------------------------------------------------ readings
def bucket(x: np.ndarray, edges) -> np.ndarray:
    out = np.digitize(x, edges).astype(np.int8)
    out[~np.isfinite(x)] = -1
    return out


def sign_code(x: np.ndarray, dead: float = 0.0) -> np.ndarray:
    return bucket(x, [-dead, dead]) if dead > 0 else bucket(x, [0.0])


def cross_code(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """0 none, 1 a crosses above b, 2 a crosses below b (at this bar)."""
    d = a - b
    prev = np.r_[np.nan, d[:-1]]
    out = np.zeros(len(d), np.int8)
    out[(prev <= 0) & (d > 0)] = 1
    out[(prev >= 0) & (d < 0)] = 2
    out[~np.isfinite(d) | ~np.isfinite(prev)] = -1
    return out


def rolling_mean(x, n):
    return pd.Series(x).rolling(n, min_periods=n).mean().to_numpy()


def rolling_std(x, n):
    return pd.Series(x).rolling(n, min_periods=n).std().to_numpy()


def bar_readings(b: dict) -> list:
    """[(name, codes int8, level names)] for one timeframe's bars. Each code is known at that bar's close."""
    import talib
    o, h, l, c, v, tb = b['o'], b['h'], b['l'], b['c'], b['v'], b['tb']
    with np.errstate(all='ignore'):
        atr = talib.ATR(h, l, c, 14)
        R = []
        add = lambda name, codes, levels: R.append((name, codes.astype(np.int8), levels))
        for p, edges, lv in [(2, [10, 90], ['<10', '10-90', '>90'])] + [
                (p, [20, 30, 70, 80], ['<20', '20-30', '30-70', '70-80', '>80']) for p in (7, 14, 21)]:
            add(f'RSI{p}', bucket(talib.RSI(c, p), edges), lv)
        k, d = talib.STOCH(h, l, c, 14, 3, 0, 3, 0)
        add('STOCH14', bucket(k, [20, 80]), ['<20', '20-80', '>80'])
        add('STOCHx', cross_code(k, d), ['none', 'K>D', 'K<D'])
        fk, _ = talib.STOCHRSI(c, 14, 14, 3, 0)
        add('STOCHRSI14', bucket(fk, [10, 90]), ['<10', '10-90', '>90'])
        add('WILLR14', bucket(talib.WILLR(h, l, c, 14), [-90, -10]), ['<-90', 'mid', '>-10'])
        add('CCI20', bucket(talib.CCI(h, l, c, 20), [-200, -100, 100, 200]), ['<-200', '-200..-100', 'mid', '100..200', '>200'])
        add('MFI14', bucket(talib.MFI(h, l, c, np.maximum(v, 1e-12), 14), [20, 80]), ['<20', '20-80', '>80'])
        adx, pdi, mdi = talib.ADX(h, l, c, 14), talib.PLUS_DI(h, l, c, 14), talib.MINUS_DI(h, l, c, 14)
        a3 = bucket(adx, [20, 40])
        adxc = np.where((a3 >= 0) & np.isfinite(pdi - mdi), a3 * 2 + (pdi > mdi), -1)
        add('ADX14xDI', adxc, ['<20 DI-', '<20 DI+', '20-40 DI-', '20-40 DI+', '>40 DI-', '>40 DI+'])
        add('AROONOSC25', bucket(talib.AROONOSC(h, l, 25), [-70, 70]), ['<-70', 'mid', '>70'])
        for fa, sl, sg in ((12, 26, 9), (5, 35, 5)):
            _, _, hist = talib.MACD(c, fa, sl, sg)
            rising = np.r_[np.nan, np.diff(hist)] > 0
            mc = np.where(np.isfinite(hist) & np.isfinite(np.r_[np.nan, hist[:-1]]), (hist > 0) * 2 + rising, -1)
            add(f'MACD{fa}/{sl}/{sg}', mc, ['<0 falling', '<0 rising', '>0 falling', '>0 rising'])
        r1 = np.r_[np.nan, np.diff(np.log(c))]
        s1 = rolling_std(r1, 1000)
        add('ROC10z', bucket((np.log(c) - np.log(np.r_[np.full(10, np.nan), c[:-10]])) / (s1 * math.sqrt(10)), [-2, -1, 1, 2]),
            ['<-2', '-2..-1', 'mid', '1..2', '>2'])
        add('CMO14', bucket(talib.CMO(c, 14), [-50, 50]), ['<-50', 'mid', '>50'])
        add('ULTOSC', bucket(talib.ULTOSC(h, l, c, 7, 14, 28), [30, 70]), ['<30', 'mid', '>70'])
        add('BOP', bucket(talib.BOP(o, h, l, c), [-0.5, 0.5]), ['<-0.5', 'mid', '>0.5'])
        add('TRIX15', sign_code(talib.TRIX(c, 15)), ['<0', '>0'])
        for dev in (2.0, 2.5):
            up, mid, lo = talib.BBANDS(c, 20, dev, dev, 0)
            pos = (c - lo) / (up - lo)
            if dev == 2.0:
                add('BB20/2', bucket(pos, [0, 0.5, 1]), ['below lower', 'lower half', 'upper half', 'above upper'])
                width = (up - lo) / mid
                add('BBwidth', bucket(width / rolling_mean(width, 100), [0.6, 1.5]), ['squeeze', 'normal', 'wide'])
            else:
                add('BB20/2.5', bucket(pos, [0, 1]), ['below lower', 'inside', 'above upper'])
        ema = {p: talib.EMA(c, p) for p in (9, 21, 50, 200)}
        for p in (9, 21, 50, 200):
            add(f'C>EMA{p}', sign_code(c - ema[p]), ['below', 'above'])
        add('EMA9x21', cross_code(ema[9], ema[21]), ['none', 'golden', 'death'])
        add('EMA50x200', cross_code(ema[50], ema[200]), ['none', 'golden', 'death'])
        add('SAR', sign_code(c - talib.SAR(h, l, 0.02, 0.2)), ['below SAR', 'above SAR'])
        add('C>KAMA30', sign_code(c - talib.KAMA(c, 30)), ['below', 'above'])
        t3 = talib.T3(c, 5, 0.7)
        add('T3slope', sign_code(np.r_[np.nan, np.diff(t3)]), ['down', 'up'])
        hi20 = pd.Series(h).shift(1).rolling(20, min_periods=20).max().to_numpy()
        lo20 = pd.Series(l).shift(1).rolling(20, min_periods=20).min().to_numpy()
        dn = np.where(np.isfinite(hi20), np.where(c > hi20, 2, np.where(c < lo20, 0, 1)), -1)
        add('Donchian20', dn, ['break low', 'inside', 'break high'])
        hs = pd.Series(h)
        ls = pd.Series(l)
        tenkan = ((hs.rolling(9).max() + ls.rolling(9).min()) / 2).to_numpy()
        kijun = ((hs.rolling(26).max() + ls.rolling(26).min()) / 2).to_numpy()
        spa = pd.Series((tenkan + kijun) / 2).shift(26).to_numpy()
        spb = (((hs.rolling(52).max() + ls.rolling(52).min()) / 2).shift(26)).to_numpy()
        top, bot = np.fmax(spa, spb), np.fmin(spa, spb)
        add('Ichimoku', np.where(np.isfinite(top), np.where(c > top, 2, np.where(c < bot, 0, 1)), -1),
            ['below cloud', 'in cloud', 'above cloud'])
        tp = (h + l + c) / 3
        vw = pd.Series(tp * v).rolling(20).sum().to_numpy() / pd.Series(v).rolling(20).sum().to_numpy()
        add('VWAP20dist', bucket((c - vw) / atr, [-1, 1]), ['<-1 ATR', 'near', '>1 ATR'])
        natr = talib.NATR(h, l, c, 14)
        add('NATRregime', bucket(natr / rolling_mean(natr, 200), [0.7, 1.3]), ['calm', 'normal', 'hot'])
        add('VolSurge', bucket(v / rolling_mean(v, 20), [0.5, 2, 4]), ['<0.5x', 'normal', '2-4x', '>4x'])
        if tb is not None:
            share = np.where(v > 0, tb / np.where(v > 0, v, 1), np.nan)
            add('TakerBuy', bucket(share, [0.4, 0.6]), ['<40% buy', 'mid', '>60% buy'])
        obv = talib.OBV(c, v)
        dp = c - np.r_[np.full(10, np.nan), c[:-10]]
        do = obv - np.r_[np.full(10, np.nan), obv[:-10]]
        add('OBVdiv10', np.where(np.isfinite(dp) & np.isfinite(do), np.where((dp < 0) & (do > 0), 1, np.where((dp > 0) & (do < 0), 2, 0)), -1),
            ['none', 'bull div', 'bear div'])
        add('ADOSC', sign_code(talib.ADOSC(h, l, c, v, 3, 10)), ['<0', '>0'])
        add('LRslope14', bucket(talib.LINEARREG_SLOPE(c, 14) / atr, [-0.1, 0.1]), ['down', 'flat', 'up'])
        add('Zscore20', bucket((c - talib.SMA(c, 20)) / talib.STDDEV(c, 20, 1), [-2, -1, 1, 2]), ['<-2', '-2..-1', 'mid', '1..2', '>2'])
        add('HTtrend', talib.HT_TRENDMODE(c).astype(float) * (np.arange(len(c)) >= 63) - (np.arange(len(c)) < 63), ['cycle', 'trend'])
        up = (c > o).astype(np.int64)
        dnb = (c < o).astype(np.int64)
        run_up = _runs(up)
        run_dn = _runs(dnb)
        add('Runs', np.select([run_dn >= 5, run_dn >= 3, run_up >= 5, run_up >= 3], [2, 1, 4, 3], 0),
            ['none', '3-4 down', '5+ down', '3-4 up', '5+ up'])
        add('BarATR', bucket((c - o) / atr, [-2, -1, 1, 2]), ['<-2', '-2..-1', 'mid', '1..2', '>2'])
        for fn in sorted(talib.get_function_groups()['Pattern Recognition']):
            x = getattr(talib, fn)(o, h, l, c)
            add(fn[3:], np.where(x > 0, 1, np.where(x < 0, 2, 0)), ['none', 'bull', 'bear'])
    return R


def _runs(x: np.ndarray) -> np.ndarray:
    """Length of the current run of ones ending at each bar."""
    cs = np.cumsum(x)
    reset = np.where(x == 0, cs, 0)
    return cs - np.maximum.accumulate(reset)


NEUTRAL = {'none'}      # levels never reported (pattern / cross absent)


def context_readings(m: dict, dom_dir: str) -> list:
    """Daily (k = 1440) BTC.D / USDT.D changes of the last COMPLETED UTC day, and the UTC 4-hour block (k = 240)."""
    nd = m['n'] // 1440
    days = m['t0'] + np.arange(nd) * DAY
    R = []
    for sym in ('BTC.D', 'USDT.D'):
        f = os.path.join(dom_dir, f'{sym}_1d.csv')
        if not os.path.exists(f):
            continue
        d = pd.read_csv(f)[['ts', 'c']].drop_duplicates('ts').set_index('ts')['c']
        d.index = (d.index // DAY) * DAY
        d = d.groupby(level=0).last()
        cl = d.reindex(days).to_numpy(float)
        prev1 = d.reindex(days - DAY).to_numpy(float)
        prev5 = d.reindex(days - 5 * DAY).to_numpy(float)
        # bar i = day i; known at day i's close, so the minute formula reads it during day i+1: no lookahead
        R.append((f'{sym} 1d', 1440, bucket(cl / prev1 - 1, [-0.005, 0.005]), ['down', 'flat', 'up']))
        R.append((f'{sym} 5d', 1440, bucket(cl / prev5 - 1, [-0.02, 0.02]), ['down', 'flat', 'up']))
    nb = m['n'] // 240
    R.append(('UTC4h', 240, ((np.arange(nb) + 1) % 6).astype(np.int8), [f'{4 * i:02d}-{4 * i + 4:02d}' for i in range(6)]))
    return R


# -------------------------------------------------------------------------------------------------------------- labels
def labels(m: dict, chunk: int = 200_000) -> dict:
    """Per minute row m (decision at its close): ret / best up / best down to each horizon (bps), the first minute
    (1..60, 0 = never) price touches +X and -X, and a validity mask (no gap at m or within the next 60 minutes)."""
    n, c, h, l, gap = m['n'], m['c'], m['h'], m['l'], m['gap']
    out = {}
    for H in HORIZONS:
        fut = np.r_[c[H:], np.full(H, np.nan)]
        out[f'ret{H}'] = ((fut / c - 1) * 1e4).astype(np.float32)
        hh = pd.Series(h[::-1]).rolling(H, min_periods=H).max().to_numpy()[::-1]
        ll = pd.Series(l[::-1]).rolling(H, min_periods=H).min().to_numpy()[::-1]
        out[f'up{H}'] = ((np.r_[hh[1:], np.nan] / c - 1) * 1e4).astype(np.float32)
        out[f'dn{H}'] = ((np.r_[ll[1:], np.nan] / c - 1) * 1e4).astype(np.float32)
    from numpy.lib.stride_tricks import sliding_window_view
    hp = np.r_[h[1:], np.full(HMAX + 1, np.nan)]
    lp = np.r_[l[1:], np.full(HMAX + 1, np.nan)]
    Wh, Wl = sliding_window_view(hp, HMAX), sliding_window_view(lp, HMAX)
    for X in TOUCH:
        tu = np.zeros(n, np.int8)
        td = np.zeros(n, np.int8)
        for s in range(0, n, chunk):
            e = min(n, s + chunk)
            cc = c[s:e, None]
            for W, sgn, arr in ((Wh, 1, tu), (Wl, -1, td)):
                hit = (W[s:e] >= cc * (1 + X / 1e4)) if sgn > 0 else (W[s:e] <= cc * (1 - X / 1e4))
                first = hit.argmax(1) + 1
                arr[s:e] = np.where(hit.any(1), first, 0)
        out[f'tu{X}'], out[f'td{X}'] = tu, td
    g = pd.Series(gap.astype(np.int16)[::-1]).rolling(HMAX + 1, min_periods=1).sum().to_numpy()[::-1]
    valid = (g == 0)
    valid[n - HMAX - 1:] = False
    out['valid'] = valid
    return out


# ----------------------------------------------------------------------------------------------------------- the stats
class Grid:
    def __init__(self, m: dict, lab: dict):
        self.t0, self.n, self.lab = m['t0'], m['n'], lab
        self.t = m['t0'] + (np.arange(m['n']) + 1) * MIN           # decision time of row m = its bar's close
        self.day = ((self.t - 1) // DAY).astype(np.int64)
        self.split_rows = {}
        for s, (a, b) in SPLITS.items():
            lo = max(0, int(np.ceil((a - self.t0) / MIN)) - 1)
            hi = int((b - HMAX * MIN - self.t0) // MIN)
            hi = max(lo, min(hi, self.n))
            self.split_rows[s] = (lo, hi)
        self.base = {s: self.stats(np.arange(*self.split_rows[s]), s, base=True) for s in SPLITS}

    def in_split(self, idx: np.ndarray, s: str) -> np.ndarray:
        lo, hi = self.split_rows[s]
        idx = idx[(idx >= lo) & (idx < hi)]
        return idx[self.lab['valid'][idx]]

    def stats(self, idx: np.ndarray, s: str, base: bool = False) -> dict:
        """Per horizon stats of the events idx (already in split s and valid when base is False)."""
        if base:
            idx = idx[self.lab['valid'][idx]]
        out = {'n': int(len(idx))}
        if len(idx) == 0:
            return out
        days = self.day[idx]
        lo, hi = self.split_rows[s]
        nd = max(1.0, (hi - lo) / 1440)
        out['per_day'] = len(idx) / nd
        out['days'] = int(len(np.unique(days)))
        for H in HORIZONS:
            r = self.lab[f'ret{H}'][idx].astype(np.float64)
            st = {'mean': float(r.mean()), 'p_up': float((r > 0).mean()),
                  'best_up': float(self.lab[f'up{H}'][idx].mean()), 'best_dn': float(self.lab[f'dn{H}'][idx].mean())}
            for X in TOUCH:
                tu, td = self.lab[f'tu{X}'][idx], self.lab[f'td{X}'][idx]
                hu, hd = (tu > 0) & (tu <= H), (td > 0) & (td <= H)
                st[f'win_up{X}'] = float((hu & (~hd | (tu < td))).mean())
                st[f'win_dn{X}'] = float((hd & (~hu | (td < tu))).mean())
            if not base:
                b = self.base[s][H]
                e = r - b['mean']
                ud, inv = np.unique(days, return_inverse=True)
                S = np.bincount(inv, e)
                cnt = np.bincount(inv)
                mu = S.sum() / cnt.sum()
                G = len(ud)
                var = ((S - mu * cnt) ** 2).sum() / cnt.sum() ** 2 * (G / (G - 1)) if G > 1 else np.nan
                st['excess'] = float(mu)
                st['t'] = float(mu / math.sqrt(var)) if var and var > 0 else 0.0
                d = 1 if mu > 0 else -1
                st['dir'] = d
                st['heat'] = float(out['per_day'] * abs(mu))
                k = 'up' if d > 0 else 'dn'
                for X in TOUCH:
                    st[f'bheat{X}'] = float(out['per_day'] * 2 * X * (st[f'win_{k}{X}'] - b[f'win_{k}{X}']))
            out[H] = st
        return out


def read_state(R: dict, idx: np.ndarray) -> np.ndarray:
    """Code of reading R known at minute rows idx (the last bar of R's timeframe closed at or before the row's close)."""
    k, codes = R['k'], R['codes']
    bi = (idx + 1) // k - 1
    out = np.full(len(idx), -1, np.int8)
    ok = (bi >= 0) & (bi < len(codes))
    out[ok] = codes[bi[ok]]
    return out


def level_events(R: dict, lv: int) -> np.ndarray:
    codes = R['codes']
    on = codes == lv
    prev = np.r_[False, on[:-1]]
    bi = np.nonzero(on & ~prev)[0]
    return bi * R['k'] + R['k'] - 1


def shift_events(idx: np.ndarray, g: Grid, s: str, rng) -> np.ndarray:
    lo, hi = g.split_rows[s]
    span = hi - lo
    if span < 61 * 1440:
        return idx
    sh = int(rng.integers(30, span // 1440 - 30)) * 1440
    return lo + (idx - lo + sh) % span


def flat_rows(coin, kind, key, parts, st_by_split, chance=None):
    rows = []
    for s, st in st_by_split.items():
        if st.get('n', 0) == 0:
            continue
        for H in HORIZONS:
            x = st[H]
            row = {'coin': coin, 'kind': kind, 'key': key, 'parts': parts, 'split': s, 'h': H, 'n': st['n'],
                   'per_day': round(st['per_day'], 4), 'days': st['days']}
            row.update({k: (round(v, 5) if isinstance(v, float) else v) for k, v in x.items()})
            if chance is not None and (s, H) in chance:
                row['chance_heat'] = round(chance[(s, H)], 4)
            rows.append(row)
    return rows


def run_coin(asset: str, csv: str, dom: str, out: str, end: int = DEV_END, log=print) -> dict:
    if asset == 'DOGE':
        raise SystemExit('NEVER DOGE')
    os.makedirs(out, exist_ok=True)
    t_start = time.time()
    m = load_minutes(csv, end=end)
    log(f'{asset}: {m["n"]:,} minutes from {pd.Timestamp(m["t0"], unit="ms")}; gaps {int(m["gap"].sum()):,}')
    lab = labels(m)
    g = Grid(m, lab)
    log(f'{asset}: labels done ({time.time() - t_start:.0f}s); split rows {g.split_rows}')
    readings = []
    for k in TFS:
        b = resample(m, k)
        for name, codes, levels in bar_readings(b):
            readings.append({'name': f'{k}m:{name}', 'k': k, 'codes': codes, 'levels': levels})
    for name, k, codes, levels in context_readings(m, dom):
        readings.append({'name': name, 'k': k, 'codes': codes, 'levels': levels, 'ctx': True})
    log(f'{asset}: {len(readings)} readings ({time.time() - t_start:.0f}s)')
    rng = np.random.default_rng(20261111)
    singles, rows, cand = [], [], []
    for ri, R in enumerate(readings):
        for lv, lname in enumerate(R['levels']):
            if lname in NEUTRAL:
                continue
            ev = level_events(R, lv)
            key = f'{R["name"]}={lname}'
            st, chance = {}, {}
            for s in SPLITS:
                idx = g.in_split(ev, s)
                st[s] = g.stats(idx, s)
                if st[s]['n'] >= MIN_EVENTS:
                    acc = {H: [] for H in HORIZONS}
                    for _ in range(SEEDS):
                        sh = g.in_split(shift_events(idx, g, s, rng), s)
                        if len(sh) < MIN_EVENTS:
                            continue
                        ps = g.stats(sh, s)
                        for H in HORIZONS:
                            acc[H].append(ps[H]['heat'])
                    for H in HORIZONS:
                        if acc[H]:
                            chance[(s, H)] = float(np.mean(acc[H]))
            rows += flat_rows(asset, 'single', key, 1, st, chance)
            sA = st['A']
            if sA.get('n', 0) >= MIN_EVENTS:
                tmax = max(abs(sA[H]['t']) for H in HORIZONS)
                singles.append((tmax, ri, lv, key, ev))
    log(f'{asset}: singles done ({time.time() - t_start:.0f}s); {len(singles)} levels with >= {MIN_EVENTS} events on A')
    singles.sort(key=lambda x: -x[0])
    cand = [x for x in singles if not readings[x[1]].get('ctx')][:N_CAND]
    ctx = [x for x in singles if readings[x[1]].get('ctx')]
    cand_all = cand + ctx

    def combo(members):
        """Events where one member's event happens while every other member's level holds."""
        evs = []
        for j, (_, ri, lv, _, ev) in enumerate(members):
            keep = np.ones(len(ev), bool)
            for jj, (_, rj, lj, _, _) in enumerate(members):
                if jj != j:
                    keep &= read_state(readings[rj], ev) == lj
            evs.append(ev[keep])
        return np.unique(np.concatenate(evs)) if evs else np.zeros(0, np.int64)

    pair_scores = []
    for i in range(len(cand)):
        for j in range(i + 1, len(cand_all)):
            a, b = cand[i], cand_all[j]
            if a[1] == b[1]:
                continue
            ev = combo([a, b])
            st = {s: g.stats(g.in_split(ev, s), s) for s in SPLITS}
            key = f'{a[3]} & {b[3]}'
            rows += flat_rows(asset, 'pair', key, 2, st)
            if st['A'].get('n', 0) >= MIN_EVENTS:
                pair_scores.append((max(st['A'][H]['heat'] * (abs(st['A'][H]['t']) >= HOT_T) for H in HORIZONS), a, b))
    log(f'{asset}: pairs done ({time.time() - t_start:.0f}s); {len(pair_scores)} pairs with >= {MIN_EVENTS} events on A')
    pair_scores.sort(key=lambda x: -x[0])
    seen = set()
    for _, a, b in pair_scores[:N_PAIR_TOP]:
        for c3 in cand_all:
            if c3[1] in (a[1], b[1]):
                continue
            fs = frozenset((a[3], b[3], c3[3]))
            if fs in seen:
                continue
            seen.add(fs)
            ev = combo([a, b, c3])
            st = {s: g.stats(g.in_split(ev, s), s) for s in SPLITS}
            if st['A'].get('n', 0) < MIN_EVENTS:
                continue
            rows += flat_rows(asset, 'triple', f'{a[3]} & {b[3]} & {c3[3]}', 3, st)
    log(f'{asset}: triples done ({time.time() - t_start:.0f}s)')
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(out, 'heat.csv.gz'), index=False, compression='gzip')
    base = {s: {str(H): g.base[s][H] for H in HORIZONS} | {'n': g.base[s]['n'], 'per_day': g.base[s]['per_day']} for s in SPLITS}
    meta = {'schema': 'oracle-heat-1', 'asset': asset, 'minutes': m['n'], 'gaps': int(m['gap'].sum()),
            'from': str(pd.Timestamp(m['t0'], unit='ms')), 'end': str(pd.Timestamp(end, unit='ms')), 'splits': {
                s: [str(pd.Timestamp(a, unit='ms')), str(pd.Timestamp(b, unit='ms'))] for s, (a, b) in SPLITS.items()},
            'readings': len(readings), 'levels_A30': len(singles), 'candidates': len(cand), 'context_levels': len(ctx),
            'rows': len(df), 'base': base, 'seconds': round(time.time() - t_start)}
    with open(os.path.join(out, 'meta.json'), 'w') as f:
        json.dump(meta, f, indent=1)
    return meta


# -------------------------------------------------------------------------------------------------------------- league
def bhy_q(p: np.ndarray) -> np.ndarray:
    from oracle.sim import bhy_adjust
    return np.asarray(bhy_adjust(p)) if len(p) else np.zeros(0)


def league(inputs: str, out: str, top: int = 60) -> dict:
    from scipy.stats import norm, spearmanr
    os.makedirs(out, exist_ok=True)
    frames, metas = [], {}
    for d in sorted(os.listdir(inputs)):
        f = os.path.join(inputs, d, 'heat.csv.gz')
        if os.path.exists(f):
            frames.append(pd.read_csv(f))
            metas[d] = json.load(open(os.path.join(inputs, d, 'meta.json')))
    df = pd.concat(frames, ignore_index=True)
    A = df[df.split == 'A'].set_index(['coin', 'kind', 'key', 'h'])
    B = df[df.split == 'B'].set_index(['coin', 'kind', 'key', 'h'])
    j = A.join(B, lsuffix='_A', rsuffix='_B', how='left')
    hot = j[(j.n_A >= MIN_EVENTS) & (j.t_A.abs() >= HOT_T)].copy()
    tB_dir = hot.t_B * np.sign(hot.excess_A)
    hot['tB_dir'] = tB_dir
    hot['p_B'] = norm.sf(tB_dir.fillna(-10))
    hot['replicates'] = (tB_dir >= 2.0)
    hot['bhy_q'] = bhy_q(hot.p_B.to_numpy())
    hot['bhy_ok'] = hot.bhy_q <= 0.10
    hot['heat_B_dir'] = hot.per_day_B * hot.excess_B * np.sign(hot.excess_A)
    summary = {'coins': sorted(metas), 'rows': int(len(df)), 'by_kind': {}}
    for kind, grp in hot.groupby(level='kind'):
        allk = j.xs(kind, level='kind')
        allk = allk[allk.n_A >= MIN_EVENTS]
        ch = j.xs(kind, level='kind')
        sm = {'tested_A': int(len(allk)), 'hot_A': int(len(grp)), 'replicate_B': int(grp.replicates.sum()),
              'replicate_share': round(float(grp.replicates.mean()), 3) if len(grp) else None,
              'bhy_survivors': int(grp.bhy_ok.sum())}
        ok = allk[['heat_A', 'heat_B']].dropna()
        if len(ok) > 10:
            sm['spearman_heat_A_B'] = round(float(spearmanr(ok.heat_A, ok.heat_B * 1).correlation), 3)
        if 'chance_heat_A' in ch:
            c2 = ch[['heat_A', 'chance_heat_A']].dropna()
            sm['median_heat_A'] = round(float(c2.heat_A.median()), 3) if len(c2) else None
            sm['median_chance_heat_A'] = round(float(c2.chance_heat_A.median()), 3) if len(c2) else None
        summary['by_kind'][kind] = sm
    hot = hot.reset_index()
    cols = ['coin', 'kind', 'key', 'h', 'dir_A', 'n_A', 'per_day_A', 'excess_A', 't_A', 'heat_A', 'n_B', 'per_day_B', 'excess_B',
            't_B', 'heat_B_dir', 'p_up_B', 'best_up_B', 'best_dn_B', 'win_up25_B', 'win_dn25_B', 'bheat25_B', 'bhy_q', 'replicates']
    cols += [c for c in ('chance_heat_A', 'chance_heat_B') if c in hot.columns]
    rep = hot[hot.replicates].sort_values('heat_B_dir', ascending=False)
    rep[cols].to_csv(os.path.join(out, 'league.csv.gz'), index=False, compression='gzip')
    hot[cols].to_csv(os.path.join(out, 'hot_A.csv.gz'), index=False, compression='gzip')
    # the strips: every single level per coin x horizon (A and B heat, chance), for the viewer
    s = j.xs('single', level='kind').reset_index()
    strip_cols = ['coin', 'key', 'h', 'n_A', 'per_day_A', 'excess_A', 't_A', 'heat_A', 'n_B', 'excess_B', 't_B', 'heat_B',
                  'p_up_A', 'best_up_A', 'best_dn_A', 'win_up25_A', 'win_dn25_A']
    strip_cols += [c for c in ('chance_heat_A',) if c in s.columns]
    s[strip_cols].round(3).to_csv(os.path.join(out, 'strips.csv.gz'), index=False, compression='gzip')
    summary['league_top'] = rep[cols].head(top).round(3).to_dict('records')
    summary['metas'] = {k: {x: v[x] for x in ('from', 'minutes', 'gaps', 'readings', 'levels_A30', 'rows', 'seconds')} for k, v in metas.items()}
    with open(os.path.join(out, 'summary.json'), 'w') as f:
        json.dump(summary, f, indent=1, default=float)
    md = ['# OR-HM1 heat map: league (coin price, discovery only)', '',
          'Build A 2020-01-01..2025-01-01, check B 2025-01-01..2026-08-01. Heat = events/day x excess move (bps/day).', '',
          '| kind | tested on A | hot on A (|t|>=3) | replicate on B (t>=2 same way) | share | BHY q<=0.10 | Spearman A/B heat | median heat A | median chance heat A |',
          '|---|---|---|---|---|---|---|---|---|']
    for kind, sm in summary['by_kind'].items():
        md.append(f"| {kind} | {sm['tested_A']} | {sm['hot_A']} | {sm['replicate_B']} | {sm['replicate_share']} | {sm['bhy_survivors']} | "
                  f"{sm.get('spearman_heat_A_B')} | {sm.get('median_heat_A')} | {sm.get('median_chance_heat_A')} |")
    md += ['', f'## Top {min(top, len(rep))} replicating hot spots by B heat', '',
           '| coin | kind | reading(s) | h | dir | ev/day B | excess B bps | t B | heat B | bracket +/-25 win B | BHY q |', '|---|---|---|---|---|---|---|---|---|---|---|']
    for r in rep.head(top).itertuples():
        w = r.win_up25_B if r.dir_A > 0 else r.win_dn25_B
        md.append(f'| {r.coin} | {r.kind} | {r.key} | {r.h} | {"up" if r.dir_A > 0 else "down"} | {r.per_day_B:.2f} | {r.excess_B:+.1f} | '
                  f'{r.t_B:+.1f} | {r.heat_B_dir:.1f} | {w:.2f} | {r.bhy_q:.3f} |')
    open(os.path.join(out, 'league.md'), 'w').write('\n'.join(md) + '\n')
    return summary


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest='cmd', required=True)
    a = sp.add_parser('coin')
    a.add_argument('--asset', required=True)
    a.add_argument('--csv', required=True)
    a.add_argument('--dom', required=True)
    a.add_argument('--out', required=True)
    b = sp.add_parser('league')
    b.add_argument('--inputs', required=True)
    b.add_argument('--out', required=True)
    x = ap.parse_args()
    if x.cmd == 'coin':
        print(json.dumps({k: v for k, v in run_coin(x.asset, x.csv, x.dom, x.out).items() if k != 'base'}, indent=1))
    else:
        s = league(x.inputs, x.out)
        print(json.dumps(s['by_kind'], indent=1))


if __name__ == '__main__':
    main()
