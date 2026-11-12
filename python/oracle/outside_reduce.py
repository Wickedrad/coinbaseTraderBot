"""OR-XD fetch round: the pure reduction functions (no network, no disk layout).

Design: /mnt/project-files/outside-data/OR-XD-design.md sections 2.1-2.3, 4.1. Everything here takes arrays or frames and
returns frames, so the unit tests can feed tiny synthetic files. All times are UTC milliseconds after unit normalisation.
(Times in comments: EST = UTC - 5 h; e.g. 2026-11-12 13:43 UTC is 8:43 AM EST.)

  * aggTrades block -> per-minute frame (counts, USD, 24 notional edges, 1-second sweep counts), merge of partial minutes
  * unit detection (microseconds above 1e14) and header detection (first field not numeric)
  * Binance metrics create_time convention (issue 491): ceil to the 5-minute grid, two independent tests, S = true snapshot
    instant, duplicate resolution at a convention switch
  * premiumIndexKlines stamp test
  * bookDepth reshape with the one-spacing shift

NEVER DOGE: nothing here knows a symbol.
"""
from __future__ import annotations

import io
import math
from typing import Iterable

import numpy as np
import pandas as pd

MIN_MS = 60_000
FIVE_MIN_MS = 300_000
US_THRESHOLD = 1e14          # a timestamp above this is microseconds (13-digit ms is ~1.7e12, 16-digit us is ~1.7e15)

# --- aggTrades layout --------------------------------------------------------------------------------------------------
N_EDGES = 24
EDGES = np.array([1000.0 * 20000.0 ** (k / 23.0) for k in range(N_EDGES)])      # USD 1,000 ... 20,000,000
SWEEP_THRESHOLDS = (('250k', 250_000.0), ('500k', 500_000.0), ('1m', 1_000_000.0), ('2m', 2_000_000.0))
AGG_SPOT_COLS = ['agg_trade_id', 'price', 'quantity', 'first_trade_id', 'last_trade_id', 'transact_time', 'is_buyer_maker',
                 'is_best_match']
AGG_UM_COLS = AGG_SPOT_COLS[:7]

BASE_COLS = ['n_buy', 'n_sell', 'usd_buy', 'usd_sell']
EDGE_COLS = ([f'nb_ge_{k}' for k in range(N_EDGES)] + [f'ns_ge_{k}' for k in range(N_EDGES)]
             + [f'ub_ge_{k}' for k in range(N_EDGES)] + [f'us_ge_{k}' for k in range(N_EDGES)])
SWEEP_COLS = [f'sw_{s}_{name}' for name, _ in SWEEP_THRESHOLDS for s in ('b', 's')]
# contract order: ts, base, edges (nb, ns, ub, us), sweeps (b/s per threshold)
AGG_COLUMNS = ['ts'] + BASE_COLS + EDGE_COLS + SWEEP_COLS
USD_COLS = ['usd_buy', 'usd_sell'] + [c for c in EDGE_COLS if c.startswith(('ub_', 'us_'))]
INT_COLS = [c for c in AGG_COLUMNS if c != 'ts' and c not in USD_COLS]


def agg_dtypes() -> dict:
    d = {'ts': np.int64}
    for c in INT_COLS:
        d[c] = np.int32
    for c in USD_COLS:
        d[c] = np.float64
    return d


def empty_agg_frame() -> pd.DataFrame:
    return pd.DataFrame({c: np.array([], dtype=t) for c, t in agg_dtypes().items()})[AGG_COLUMNS]


# --- units and headers -------------------------------------------------------------------------------------------------
def detect_unit(ts_max: float) -> str:
    """'us' when the largest timestamp of a file/block is above 1e14, else 'ms'."""
    return 'us' if float(ts_max) > US_THRESHOLD else 'ms'


def to_ms(ts, unit: str | None = None) -> np.ndarray:
    a = np.asarray(ts, dtype=np.int64)
    if a.size == 0:
        return a
    u = unit or detect_unit(a.max())
    return a // 1000 if u == 'us' else a


def has_header(first_line: bytes | str) -> bool:
    """A data row starts with a number (or a minus sign); a header starts with a name."""
    if isinstance(first_line, bytes):
        first_line = first_line.decode('utf-8', 'replace')
    f = first_line.strip().split(',')[0].strip().strip('"')
    if not f:
        return False
    try:
        float(f)
        return False
    except ValueError:
        pass
    # a datetime such as 2020-09-01 00:05:00 is data, not a header
    return not (f[:4].isdigit() and f[4:5] == '-')


# --- aggTrades reduction -----------------------------------------------------------------------------------------------
def reduce_arrays(ts_ms: np.ndarray, price: np.ndarray, qty: np.ndarray, buyer_maker: np.ndarray) -> pd.DataFrame:
    """One block of aggTrades (timestamps already in ms) -> per-minute frame with the contract columns.

    Aggressor buy = is_buyer_maker false. A calendar second must be wholly inside the block for its sweep flag to be
    exact; AggReducer guarantees that by carrying the last second over to the next block.
    """
    ts_ms = np.asarray(ts_ms, dtype=np.int64)
    n = ts_ms.size
    if n == 0:
        return empty_agg_frame()
    price = np.asarray(price, dtype=np.float64)
    qty = np.asarray(qty, dtype=np.float64)
    buy = ~np.asarray(buyer_maker, dtype=bool)
    notional = price * qty

    minute = ts_ms // MIN_MS
    um, mi = np.unique(minute, return_inverse=True)
    M = um.size
    side = buy.astype(np.int64)                                   # 1 = aggressor buy, 0 = aggressor sell
    c = np.searchsorted(EDGES, notional, side='right')            # number of edges <= notional, 0..24
    key = (mi.astype(np.int64) * 2 + side) * (N_EDGES + 1) + c
    size = M * 2 * (N_EDGES + 1)
    cnt = np.bincount(key, minlength=size).reshape(M, 2, N_EDGES + 1)
    usd = np.bincount(key, weights=notional, minlength=size).reshape(M, 2, N_EDGES + 1)
    # ge[k] = sum of bins c >= k+1 (notional >= E_k)
    cnt_ge = cnt[:, :, ::-1].cumsum(axis=2)[:, :, ::-1][:, :, 1:]
    usd_ge = usd[:, :, ::-1].cumsum(axis=2)[:, :, ::-1][:, :, 1:]

    out = {'ts': um.astype(np.int64) * MIN_MS,
           'n_buy': cnt[:, 1, :].sum(axis=1), 'n_sell': cnt[:, 0, :].sum(axis=1),
           'usd_buy': usd[:, 1, :].sum(axis=1), 'usd_sell': usd[:, 0, :].sum(axis=1)}
    for k in range(N_EDGES):
        out[f'nb_ge_{k}'] = cnt_ge[:, 1, k]
        out[f'ns_ge_{k}'] = cnt_ge[:, 0, k]
        out[f'ub_ge_{k}'] = usd_ge[:, 1, k]
        out[f'us_ge_{k}'] = usd_ge[:, 0, k]

    # sweeps: per CALENDAR second (floor(ts/1000)) the same-side notional sum, flagged by threshold, counted per minute
    sec = ts_ms // 1000
    us, si = np.unique(sec, return_inverse=True)
    S = us.size
    sb = np.bincount(si[buy], weights=notional[buy], minlength=S)
    ss = np.bincount(si[~buy], weights=notional[~buy], minlength=S)
    sec_minute = np.searchsorted(um, us // 60)
    for name, thr in SWEEP_THRESHOLDS:
        out[f'sw_b_{name}'] = np.bincount(sec_minute[sb >= thr], minlength=M)
        out[f'sw_s_{name}'] = np.bincount(sec_minute[ss >= thr], minlength=M)
    df = pd.DataFrame(out)[AGG_COLUMNS]
    return df.astype(agg_dtypes())


def merge_frames(frames: Iterable[pd.DataFrame]) -> pd.DataFrame:
    """Sum partial minutes across blocks (every column is additive: counts, USD and whole-second sweep counts)."""
    fr = [f for f in frames if len(f)]
    if not fr:
        return empty_agg_frame()
    df = pd.concat(fr, ignore_index=True).copy()
    df = df.groupby('ts', sort=True, as_index=False).sum().copy()
    return df[AGG_COLUMNS].astype(agg_dtypes())


class AggReducer:
    """Streaming reducer: feed blocks of raw columns, get one per-minute frame at the end. Memory is bounded by the
    number of minutes (<= 44,640 a month), not by the number of trades."""

    def __init__(self):
        self.unit: str | None = None
        self.rows = 0
        self._parts: list[pd.DataFrame] = []
        self._carry: tuple | None = None

    def _norm(self, ts):
        ts = np.asarray(ts, dtype=np.int64)
        if ts.size == 0:
            return ts
        u = detect_unit(ts.max())
        if self.unit is None:
            self.unit = u
        elif u != self.unit and (u == 'us' or ts.max() > 1e11):   # a later block jumping unit is a corrupt file
            raise ValueError(f'timestamp unit changed inside one file: {self.unit} then {u}')
        return ts // 1000 if self.unit == 'us' else ts

    def feed(self, ts, price, qty, buyer_maker) -> None:
        ts = self._norm(ts)
        if ts.size == 0:
            return
        price = np.asarray(price, dtype=np.float64)
        qty = np.asarray(qty, dtype=np.float64)
        bm = np.asarray(buyer_maker, dtype=bool)
        self.rows += ts.size
        if self._carry is not None:
            c = self._carry
            ts, price, qty, bm = (np.concatenate([c[0], ts]), np.concatenate([c[1], price]), np.concatenate([c[2], qty]),
                                  np.concatenate([c[3], bm]))
            self._carry = None
        last_sec = ts.max() // 1000
        tail = (ts // 1000) >= last_sec
        if tail.all():                                 # the whole block is one second: wait for more
            self._carry = (ts, price, qty, bm)
            return
        self._carry = (ts[tail], price[tail], qty[tail], bm[tail])
        keep = ~tail
        self._parts.append(reduce_arrays(ts[keep], price[keep], qty[keep], bm[keep]))
        if len(self._parts) >= 32:
            self._parts = [merge_frames(self._parts)]

    def finish(self) -> pd.DataFrame:
        if self._carry is not None:
            c = self._carry
            self._parts.append(reduce_arrays(*c))
            self._carry = None
        return merge_frames(self._parts)


# --- klines-like CSVs (um, premium, mark, index, 1h) -------------------------------------------------------------------
KLINE_COLS = ['ts', 'o', 'h', 'l', 'c', 'v', 'close_time', 'quote_v', 'count', 'tb', 'tbq', 'ignore']


def read_klines_csv(raw: bytes | io.BufferedIOBase, keep: list[str]) -> pd.DataFrame:
    """Kline CSV with or without header (newer years have one). Returns ts (ms) + the kept columns, sorted, deduped."""
    data = raw if isinstance(raw, (bytes, bytearray)) else raw.read()
    head = data.split(b'\n', 1)[0]
    ncols = len(head.split(b','))
    names = KLINE_COLS[:ncols]
    df = pd.read_csv(io.BytesIO(data), header=0 if has_header(head) else None, names=names, usecols=range(ncols))
    if df.empty:
        return pd.DataFrame({c: np.array([], dtype=np.int64 if c == 'ts' else np.float64) for c in keep})
    df['ts'] = to_ms(df['ts'].to_numpy())
    for c in keep:
        if c != 'ts':
            df[c] = pd.to_numeric(df[c], errors='coerce').astype(np.float64)
    df = df[keep].drop_duplicates('ts', keep='last').sort_values('ts', kind='stable').reset_index(drop=True)
    return df


def read_funding_csv(raw: bytes) -> pd.DataFrame:
    head = raw.split(b'\n', 1)[0]
    names = ['calc_time', 'funding_interval_hours', 'last_funding_rate']
    df = pd.read_csv(io.BytesIO(raw), header=0 if has_header(head) else None, names=names, usecols=range(3))
    df['calc_time'] = to_ms(df['calc_time'].to_numpy())
    df['funding_interval_hours'] = pd.to_numeric(df['funding_interval_hours'], errors='coerce').astype(np.float64)
    df['last_funding_rate'] = pd.to_numeric(df['last_funding_rate'], errors='coerce').astype(np.float64)
    return df.drop_duplicates('calc_time', keep='last').sort_values('calc_time', kind='stable').reset_index(drop=True)


# --- Binance metrics: create_time convention (binance-public-data issue 491) -------------------------------------------
METRIC_COLS = ['sum_open_interest', 'sum_open_interest_value', 'count_toptrader_long_short_ratio',
               'sum_toptrader_long_short_ratio', 'count_long_short_ratio', 'sum_taker_long_short_vol_ratio']
METRICS_FILE_COLS = ['create_time', 'symbol'] + METRIC_COLS
R_MARGIN = 0.5            # test (a): correlation of the right window minus the wrong window must reach this
GAP_RATIO = 1.5           # test (b): the wrong instant's median gap must be at least this many times the right one's
MIN_ROWS_TEST = 24


def ceil_5m(ms_arr) -> np.ndarray:
    a = np.asarray(ms_arr, dtype=np.int64)
    return -((-a) // FIVE_MIN_MS) * FIVE_MIN_MS


def parse_create_time(col: pd.Series) -> np.ndarray:
    """create_time as UTC ms; accepts '2020-09-01 00:05:00' strings and epoch numbers (ms or us)."""
    if pd.api.types.is_numeric_dtype(col):
        return to_ms(col.to_numpy())
    dt = pd.to_datetime(col, utc=True)
    return ((dt - pd.Timestamp('1970-01-01', tz='UTC')) // pd.Timedelta(milliseconds=1)).to_numpy(dtype=np.int64)


def read_metrics_csv(raw: bytes) -> pd.DataFrame:
    """One daily metrics file -> stamp_raw (ms), stamp (ceiled to the 5-minute grid) and the six numeric columns."""
    head = raw.split(b'\n', 1)[0]
    df = pd.read_csv(io.BytesIO(raw), header=0 if has_header(head) else None, names=METRICS_FILE_COLS,
                     usecols=range(len(METRICS_FILE_COLS)))
    out = pd.DataFrame({'stamp_raw': parse_create_time(df['create_time'])})
    out['stamp'] = ceil_5m(out['stamp_raw'].to_numpy())
    for c in METRIC_COLS:
        out[c] = pd.to_numeric(df[c], errors='coerce').astype(np.float64)
    return out


class MinuteGrid:
    """1-minute bars on a complete grid with O(1) window sums (NaN-safe via validity counts)."""

    def __init__(self, ts: np.ndarray, **cols: np.ndarray):
        ts = np.asarray(ts, dtype=np.int64)
        self.empty = ts.size == 0
        if self.empty:
            return
        self.t0 = int(ts.min() // MIN_MS * MIN_MS)
        n = int((ts.max() - self.t0) // MIN_MS) + 1
        idx = (ts - self.t0) // MIN_MS
        self.n = n
        self.valid = np.zeros(n, dtype=bool)
        self.valid[idx] = True
        self.col = {}
        self.cum = {}
        for k, v in cols.items():
            full = np.full(n, np.nan)
            full[idx] = np.asarray(v, dtype=np.float64)
            self.col[k] = full
            self.cum[k] = np.concatenate([[0.0], np.cumsum(np.nan_to_num(full))])
        self.cum_valid = np.concatenate([[0], np.cumsum(self.valid & ~np.isnan(next(iter(self.col.values()))))])

    def window_sum(self, start_ms: np.ndarray, minutes: int, col: str) -> np.ndarray:
        """Sum of the bars opening in [start, start + minutes); NaN unless every bar is present."""
        if self.empty:
            return np.full(len(start_ms), np.nan)
        i = (np.asarray(start_ms, dtype=np.int64) - self.t0) // MIN_MS
        j = i + minutes
        ok = (i >= 0) & (j <= self.n)
        ii = np.clip(i, 0, self.n)
        jj = np.clip(j, 0, self.n)
        s = self.cum[col][jj] - self.cum[col][ii]
        full = (self.cum_valid[jj] - self.cum_valid[ii]) == minutes
        return np.where(ok & full, s, np.nan)

    def at(self, ms_arr: np.ndarray, col: str) -> np.ndarray:
        if self.empty:
            return np.full(len(ms_arr), np.nan)
        i = (np.asarray(ms_arr, dtype=np.int64) - self.t0) // MIN_MS
        ok = (i >= 0) & (i < self.n)
        return np.where(ok, self.col[col][np.clip(i, 0, self.n - 1)], np.nan)


def make_um_grid(um: pd.DataFrame) -> MinuteGrid:
    """um 1m klines (ts, v, tb) -> grid with taker buy and sell base volume."""
    return MinuteGrid(um['ts'].to_numpy(), buy=um['tb'].to_numpy(), sell=(um['v'] - um['tb']).to_numpy())


def make_mark_grid(mark: pd.DataFrame) -> MinuteGrid:
    return MinuteGrid(mark['ts'].to_numpy(), o=mark['o'].to_numpy())


def _corr(a: np.ndarray, b: np.ndarray) -> float:
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < MIN_ROWS_TEST:
        return float('nan')
    a, b = a[m], b[m]
    if a.std() == 0 or b.std() == 0:
        return float('nan')
    return float(np.corrcoef(a, b)[0, 1])


def test_a_taker(day: pd.DataFrame, um_grid: MinuteGrid) -> dict:
    """Taker ratio against um klines taker buy/sell over [T-5m, T) (old convention) vs [T, T+5m) (new convention)."""
    T = day['stamp'].to_numpy()
    r = day['sum_taker_long_short_vol_ratio'].to_numpy()
    with np.errstate(all='ignore'):
        x = np.log(np.where(r > 0, r, np.nan))
        left = np.log(um_grid.window_sum(T - FIVE_MIN_MS, 5, 'buy') / um_grid.window_sum(T - FIVE_MIN_MS, 5, 'sell'))
        right = np.log(um_grid.window_sum(T, 5, 'buy') / um_grid.window_sum(T, 5, 'sell'))
    r_old, r_new = _corr(x, left), _corr(x, right)
    verdict = 'amb'
    if math.isfinite(r_old) and math.isfinite(r_new):
        if r_old - r_new >= R_MARGIN:
            verdict = 'old'
        elif r_new - r_old >= R_MARGIN:
            verdict = 'new'
    return {'a': verdict, 'r_left': r_old, 'r_right': r_new}


def test_b_price(day: pd.DataFrame, mark_grid: MinuteGrid) -> dict:
    """Implied price oi_value/oi against mark price at T (old) vs T+5m (new): per-day median absolute log gap."""
    T = day['stamp'].to_numpy()
    with np.errstate(all='ignore'):
        imp = day['sum_open_interest_value'].to_numpy() / day['sum_open_interest'].to_numpy()
        g_old = np.abs(np.log(imp / mark_grid.at(T, 'o')))
        g_new = np.abs(np.log(imp / mark_grid.at(T + FIVE_MIN_MS, 'o')))
    ok = np.isfinite(g_old) & np.isfinite(g_new)
    if ok.sum() < MIN_ROWS_TEST:
        return {'b': 'amb', 'gap_t': float('nan'), 'gap_t5': float('nan')}
    go, gn = float(np.median(g_old[ok])), float(np.median(g_new[ok]))
    verdict = 'amb'
    if gn >= GAP_RATIO * max(go, 1e-12):
        verdict = 'old'
    elif go >= GAP_RATIO * max(gn, 1e-12):
        verdict = 'new'
    return {'b': verdict, 'gap_t': go, 'gap_t5': gn}


def label_day(day: pd.DataFrame, um_grid: MinuteGrid, mark_grid: MinuteGrid) -> dict:
    """Both tests must agree on old or new, else 'amb' (treated as new for S)."""
    a = test_a_taker(day, um_grid)
    b = test_b_price(day, mark_grid)
    conv = a['a'] if a['a'] == b['b'] and a['a'] in ('old', 'new') else 'amb'
    return {'conv': conv, **a, **b}


def snapshot_instant(stamp: np.ndarray, conv: str) -> np.ndarray:
    """S: old file S = stamp; new file (and amb) S = stamp + 5 min. Readers use known time S + 5 min."""
    stamp = np.asarray(stamp, dtype=np.int64)
    return stamp if conv == 'old' else stamp + FIVE_MIN_MS


def build_metrics_table(days: list[tuple[str, pd.DataFrame, str]], mark_grid: MinuteGrid) -> pd.DataFrame:
    """days = [(file, parsed day frame, conv)] -> the metrics.csv.gz table sorted by S, duplicates resolved.

    Duplicate S (two files at a convention switch land on the same instant): keep the row whose implied price
    oi_value/oi is closest to the mark price at S (bar open); a tie keeps the later file (the new convention)."""
    parts = []
    for fname, df, conv in days:
        if df.empty:
            continue
        p = pd.DataFrame({'S': snapshot_instant(df['stamp'].to_numpy(), conv), 'stamp': df['stamp'].to_numpy(), 'conv': conv})
        for c in METRIC_COLS:
            p[c] = df[c].to_numpy()
        p['file'] = fname
        parts.append(p)
    if not parts:
        return pd.DataFrame(columns=['S', 'stamp', 'conv'] + METRIC_COLS + ['file'])
    t = pd.concat(parts, ignore_index=True)
    with np.errstate(all='ignore'):
        imp = t['sum_open_interest_value'].to_numpy() / t['sum_open_interest'].to_numpy()
        gap = np.abs(np.log(imp / mark_grid.at(t['S'].to_numpy(), 'o')))
    t['_gap'] = np.where(np.isfinite(gap), gap, np.inf)
    t = t.sort_values(['S', '_gap', 'file'], ascending=[True, True, False], kind='stable')
    t = t.drop_duplicates('S', keep='first').drop(columns='_gap')
    return t.sort_values('S', kind='stable').reset_index(drop=True)


def amb_report(labels: dict[str, dict]) -> dict:
    """labels: file name (...-YYYY-MM-DD.zip) -> label_day dict. A days = 2020-2024, B days = 2025 (2026 is information)."""
    def year(f: str) -> int:
        import re
        m = re.search(r'(\d{4})-\d{2}-\d{2}', f)
        return int(m.group(1)) if m else 0
    out = {}
    for name, sel in (('A', lambda y: 2020 <= y <= 2024), ('B', lambda y: y == 2025), ('2026', lambda y: y >= 2026)):
        fs = [f for f in labels if sel(year(f))]
        amb = [f for f in fs if labels[f]['conv'] == 'amb']
        out[name] = {'days': len(fs), 'amb': len(amb), 'frac': (len(amb) / len(fs)) if fs else 0.0,
                     'old': sum(labels[f]['conv'] == 'old' for f in fs), 'new': sum(labels[f]['conv'] == 'new' for f in fs)}
    return out


# --- premiumIndexKlines stamp test -------------------------------------------------------------------------------------
STAMP_MIN_CORR = 0.2
STAMP_MIN_DIFF = 0.05


def premium_stamp_test(premium: pd.DataFrame, perp: pd.DataFrame, index: pd.DataFrame) -> dict:
    """Does the premium bar opening at t describe (perp close - index close)/index close of the same minute (fit 'same'
    -> known at t + 60 s) or of the NEXT minute ('next' -> readers add one more minute of delay)?  Correlation of 1-minute
    CHANGES (levels autocorrelate too much to tell adjacent minutes apart). Resolved only if the better fit has r >=
    0.2 and beats the other by >= 0.05; the caller fails the job otherwise."""
    p = premium.set_index('ts')['c']
    x = ((perp.set_index('ts')['c'] - index.set_index('ts')['c']) / index.set_index('ts')['c']).dropna()
    ts = p.index.intersection(x.index)
    if len(ts) < 100:
        return {'fits': 'unresolved', 'resolved': False, 'n': int(len(ts)), 'corr_same': float('nan'), 'corr_next': float('nan')}
    pv = p.reindex(ts)
    dp = pv.diff()
    xs = x.reindex(ts)
    xn = x.reindex(ts + MIN_MS)
    dxs = xs.diff()
    dxn = pd.Series(xn.to_numpy(), index=ts).diff()
    # keep only consecutive minutes so a gap never creates a fake change
    consec = pd.Series(ts.to_numpy(), index=ts).diff().to_numpy() == MIN_MS
    cs = _corr(np.where(consec, dp.to_numpy(), np.nan), np.where(consec, dxs.to_numpy(), np.nan))
    cn = _corr(np.where(consec, dp.to_numpy(), np.nan), np.where(consec, dxn.to_numpy(), np.nan))
    fits, resolved = 'unresolved', False
    if math.isfinite(cs) and math.isfinite(cn):
        best, other = max(cs, cn), min(cs, cn)
        if best >= STAMP_MIN_CORR and best - other >= STAMP_MIN_DIFF:
            fits, resolved = ('same' if cs > cn else 'next'), True
    return {'fits': fits, 'resolved': resolved, 'n': int(consec.sum()), 'corr_same': cs, 'corr_next': cn,
            'extra_delay_minutes': 1 if fits == 'next' else 0, 'method': 'corr of 1-minute changes',
            'min_corr': STAMP_MIN_CORR, 'min_diff': STAMP_MIN_DIFF}


# --- bookDepth ---------------------------------------------------------------------------------------------------------
def bookdepth_reshape(raw: bytes) -> tuple[pd.DataFrame, int]:
    """One daily bookDepth file (timestamp, percentage, depth, notional) -> (ts, bid_1pct, ask_1pct) and the spacing.

    bid_1pct = notional at percentage -1, ask_1pct = at +1. ts is SHIFTED LATER by one spacing (the median gap between
    distinct stamps of this file, ms) so a reader using 'known at ts' can never see a snapshot early."""
    head = raw.split(b'\n', 1)[0]
    df = pd.read_csv(io.BytesIO(raw), header=0 if has_header(head) else None,
                     names=['timestamp', 'percentage', 'depth', 'notional'], usecols=range(4))
    if df.empty:
        return pd.DataFrame({'ts': np.array([], dtype=np.int64), 'bid_1pct': [], 'ask_1pct': []}), 0
    stamps = parse_create_time(df['timestamp'])
    df['ts'] = stamps
    df['percentage'] = pd.to_numeric(df['percentage'], errors='coerce')
    df['notional'] = pd.to_numeric(df['notional'], errors='coerce').astype(np.float64)
    uniq = np.unique(stamps)
    spacing = int(np.median(np.diff(uniq))) if uniq.size > 1 else 0
    bid = df[df['percentage'] == -1].drop_duplicates('ts', keep='last').set_index('ts')['notional']
    ask = df[df['percentage'] == 1].drop_duplicates('ts', keep='last').set_index('ts')['notional']
    out = pd.DataFrame({'bid_1pct': bid, 'ask_1pct': ask}).dropna().sort_index()
    out.insert(0, 'ts', out.index.to_numpy(dtype=np.int64) + spacing)
    return out.reset_index(drop=True), spacing
