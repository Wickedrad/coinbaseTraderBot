"""Loading the real history: Kalshi's 1-minute contract candles and Binance 1-minute spot bars.

Kalshi (Drive raw/history/kalshi/<SERIES>/<close day>.jsonl, written by research/history/kalshiHistory.ts): one settled
market per line with its 1-minute candles {ts (candle END, ms), bidO/H/L/C, askO/H/L/C, last, volume, oi} in dollars.
Binance (Drive raw/history/binance-1m/<ASSET>/1m.csv): `ts,o,h,l,c,v`, ts = bar OPEN in ms.

A window of N minutes has decision times t_k = open + 60 s x k for k = 0..N-1 (k = 0 is the open). The quote at t_k is
candle k's close (candle 1's open for k = 0); a minute with no candle keeps the last quote (the book did not change)
and is counted as carried. What happens between t_k and t_{k+1} (the maker fill check) is candle k+1's high and low.
DOGE is dropped here whatever the caller asks for (Steven, 2026-11-05).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

import numpy as np

from . import EXCLUDED_ASSETS

MIN = 60_000


def allowed_assets(assets) -> list[str]:
    out = []
    for a in assets:
        a = str(a).strip().upper()
        if a and a not in EXCLUDED_ASSETS and a not in out:
            out.append(a)
    return out


def _f(v) -> float:
    if v is None:
        return np.nan
    try:
        x = float(v)
    except (TypeError, ValueError):
        return np.nan
    return x


_PRICE_KEYS = ('bidO', 'bidH', 'bidL', 'bidC', 'askO', 'askH', 'askL', 'askC', 'last')


def repair_legacy_cents(candles: list) -> bool:
    """research/history/kalshiHistory.ts repairLegacyCents, per market: a market from the /historical endpoint whose
    dollar prices were divided by 100 once more has EVERY price under a cent; it is scaled back. A market with some
    prices under a cent among normal ones keeps them (Kalshi quotes tenths of a cent in the tails). True if repaired."""
    vals = [c.get(k) for c in candles for k in _PRICE_KEYS if isinstance(c.get(k), (int, float)) and c.get(k) > 0]
    if not vals or max(vals) >= 0.01:
        return False
    for c in candles:
        for k in _PRICE_KEYS:
            v = c.get(k)
            if isinstance(v, (int, float)) and 0 < v < 0.01:
                c[k] = round(v * 1e6) / 1e4
    return True


@dataclass
class Windows:
    """N-minute contract windows with YES-side quotes at the decision times (NaN = no quote)."""
    n: int
    asset: np.ndarray          # (W,) asset index into `assets`
    assets: list[str]
    open_ms: np.ndarray        # (W,) int64
    strike: np.ndarray         # (W,)
    settle: np.ndarray         # (W,) 1.0 = YES won, 0.0 = NO won
    bid: np.ndarray            # (W, N) YES bid at t_k
    ask: np.ndarray            # (W, N) YES ask at t_k
    nbid_lo: np.ndarray        # (W, N) lowest YES bid in (t_k, t_k+1]
    nbid_hi: np.ndarray
    nask_lo: np.ndarray
    nask_hi: np.ndarray
    kvol: np.ndarray           # (W, N) contracts traded in the minute ending at t_k
    real_frac: np.ndarray      # (W,) share of decision minutes with a real (not carried) quote
    synthetic: np.ndarray      # (W,) bool: quotes priced by the synthetic pricer
    tickers: list[str] = field(default_factory=list)
    crossed: np.ndarray | None = None   # (W,) decision minutes whose recorded quote was crossed or locked

    def __len__(self) -> int:
        return len(self.open_ms)

    def subset(self, idx) -> 'Windows':
        idx = np.asarray(idx)
        g = lambda a: a[idx]
        return Windows(self.n, g(self.asset), self.assets, g(self.open_ms), g(self.strike), g(self.settle), g(self.bid), g(self.ask),
                       g(self.nbid_lo), g(self.nbid_hi), g(self.nask_lo), g(self.nask_hi), g(self.kvol), g(self.real_frac),
                       g(self.synthetic), [self.tickers[i] for i in np.atleast_1d(idx)] if self.tickers else [],
                       g(self.crossed) if self.crossed is not None else None)

    @property
    def day(self) -> np.ndarray:
        """UTC day index (days since 1970) of each window's open."""
        return (self.open_ms // 86_400_000).astype(np.int64)

    @staticmethod
    def concat(parts: list['Windows']) -> 'Windows':
        parts = [p for p in parts if len(p)]
        if not parts:
            raise ValueError('no windows')
        a0 = parts[0]
        c = lambda name: np.concatenate([getattr(p, name) for p in parts])
        return Windows(a0.n, c('asset'), a0.assets, c('open_ms'), c('strike'), c('settle'), c('bid'), c('ask'), c('nbid_lo'), c('nbid_hi'),
                       c('nask_lo'), c('nask_hi'), c('kvol'), c('real_frac'), c('synthetic'), sum((p.tickers for p in parts), []),
                       c('crossed') if all(p.crossed is not None for p in parts) else None)


def _side_hl(cd: dict, side: str):
    """A candle's (low, high) for one side, or NaNs when they contradict its own open and close (a high under the
    close, a low over it) or leave (0, 1): Kalshi's historical-tier candles carry such fields, and a fill must not be
    inferred from them."""
    lo, hi = _f(cd.get(f'{side}L')), _f(cd.get(f'{side}H'))
    o_, c_ = _f(cd.get(f'{side}O')), _f(cd.get(f'{side}C'))
    ok = np.isfinite(lo) and np.isfinite(hi) and 0 < lo <= hi + 1e-9 and hi < 1
    for v in (o_, c_):
        if ok and np.isfinite(v):
            ok = lo - 1e-9 <= v <= hi + 1e-9
    return (lo, hi) if ok else (np.nan, np.nan)


def _book(b: float, a: float) -> bool:
    """A two-sided book: 0 < bid < ask < 1."""
    return bool(np.isfinite(b) and np.isfinite(a) and 0 < b < a - 1e-9 and a < 1)


def _volume(cd: dict) -> float:
    try:
        return float(cd.get('volume') or 0.0)
    except (TypeError, ValueError):
        return 0.0


def market_to_rows(m: dict, n: int, max_stale: int = 0):
    """One stored market -> (bid, ask, nbid_lo, nbid_hi, nask_lo, nask_hi, kvol, real_frac, window open, n_crossed) or
    None. The window is the market's last N minutes (a market listed earlier than its period is cut to the period).

    A decision quote is candle k's close (k >= 1) and must be a two-sided book, 0 < bid < ask < 1, at that minute;
    anything else is no quote (NaN, both sides). Kalshi's historical-tier candles (markets settled before the API's
    historical cutoff, Apr - early Sep 2026 here) store an empty ask, $1.00 'no offers', as $0.01 (the history parser
    divides legacy values >= 1 by 100), so a one-sided minute reads as a 1c YES ask with no bid, and with a bid it is
    crossed (~4% of their minutes, counted in n_crossed). Neither is a book anyone could trade.
    k = 0 would be candle 1's open, the listing instant: an empty book in the live tier (asks at 99c+), a placeholder
    one in the historical tier (a 1c YES ask that settled YES 49% of the time, diag run 42049460236). No quote.
    A minute without a candle has no quote unless max_stale > 0 (a carried quote beside current spot features would be
    a free option). real_frac is the share of decision minutes 1..N-1 that have a candle.
    Maker fills for an order resting at minute k come from candle k+1, which proves a fill only when it traded (volume
    > 0), its close is a two-sided book and its highs/lows agree with its own open and close; otherwise no fill."""
    o, c = m.get('openTime'), m.get('closeTime')
    if not isinstance(o, (int, float)) or not isinstance(c, (int, float)) or int(c - o) < n * MIN:
        return None
    o = int(c) - n * MIN
    res = m.get('result')
    if res not in ('yes', 'no'):
        return None
    cand = {}
    repair_legacy_cents(m.get('candles') or [])
    for cd in m.get('candles') or []:
        ts = cd.get('ts')
        if not isinstance(ts, (int, float)):
            continue
        idx = int(round((ts - o) / MIN))
        if 1 <= idx <= n:
            cand[idx] = cd
    if not cand:
        return None
    bid = np.full(n, np.nan); ask = np.full(n, np.nan)
    blo = np.full(n, np.nan); bhi = np.full(n, np.nan); alo = np.full(n, np.nan); ahi = np.full(n, np.nan)
    kvol = np.zeros(n)
    real = 0
    n_crossed = 0
    age = max_stale + 1
    for k in range(1, n):
        ck = cand.get(k)
        if ck is not None:
            real += 1
            kvol[k] = _volume(ck)
            b_, a_ = _f(ck.get('bidC')), _f(ck.get('askC'))
            if np.isfinite(b_) and np.isfinite(a_) and b_ > 0 and b_ >= a_ - 1e-9:
                n_crossed += 1
            if _book(b_, a_):
                bid[k], ask[k] = b_, a_
                age = 0
            else:
                age = max_stale + 1
        else:
            age += 1
            if age <= max_stale:
                bid[k], ask[k] = bid[k - 1], ask[k - 1]
    for k in range(n):
        nk = cand.get(k + 1)
        if nk is None or _volume(nk) <= 0 or not _book(_f(nk.get('bidC')), _f(nk.get('askC'))):
            continue   # no trade, or no book at its close: no maker fill is inferred
        blo[k], bhi[k] = _side_hl(nk, 'bid')
        alo[k], ahi[k] = _side_hl(nk, 'ask')
    return bid, ask, blo, bhi, alo, ahi, kvol, real / max(1, n - 1), o, n_crossed


def load_kalshi(history_dir: str, assets, n: int = 15, series_fmt: str = 'KX{asset}15M', from_ms: int | None = None,
                to_ms: int | None = None, log=print) -> Windows:
    assets = allowed_assets(assets)
    rows = {k: [] for k in ('asset', 'open', 'strike', 'settle', 'bid', 'ask', 'blo', 'bhi', 'alo', 'ahi', 'kvol', 'real', 'ticker', 'crossed')}
    for ai, a in enumerate(assets):
        d = os.path.join(history_dir, 'kalshi', series_fmt.format(asset=a))
        if not os.path.isdir(d):
            log(f'kalshi: no {d}')
            continue
        kept = skipped = longer = crossed_w = 0
        for fn in sorted(os.listdir(d)):
            if not fn.endswith('.jsonl'):
                continue
            with open(os.path.join(d, fn), encoding='utf8') as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        m = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if (from_ms is not None and m.get('openTime', 0) < from_ms) or (to_ms is not None and m.get('openTime', 0) >= to_ms):
                        continue
                    r = market_to_rows(m, n)
                    strike = _f_strike(m.get('strike'))
                    if r is None or not np.isfinite(strike):
                        skipped += 1
                        continue
                    bid, ask, blo, bhi, alo, ahi, kvol, real, o_eff, n_crossed = r
                    if int(m['closeTime'] - m['openTime']) != n * MIN:
                        longer += 1
                    rows['asset'].append(ai); rows['open'].append(o_eff); rows['strike'].append(strike)
                    rows['settle'].append(1.0 if m['result'] == 'yes' else 0.0)
                    for k_, v in (('bid', bid), ('ask', ask), ('blo', blo), ('bhi', bhi), ('alo', alo), ('ahi', ahi), ('kvol', kvol)):
                        rows[k_].append(v)
                    rows['real'].append(real); rows['ticker'].append(str(m.get('ticker', ''))); rows['crossed'].append(n_crossed)
                    crossed_w += n_crossed > 0
                    kept += 1
        log(f'kalshi: {a}: {kept} windows ({longer} listed before their period, cut to the last {n} min; {crossed_w} with crossed quotes), {skipped} skipped (void, too short, no candles or no strike)')
    if not rows['open']:
        raise SystemExit('no Kalshi windows loaded')
    W = len(rows['open'])
    arr = lambda k: np.array(rows[k], dtype=np.float64).reshape(W, n)
    order = np.argsort(np.array(rows['open']), kind='stable')
    w = Windows(n, np.array(rows['asset'], dtype=np.int16), assets, np.array(rows['open'], dtype=np.int64), np.array(rows['strike']),
                np.array(rows['settle']), arr('bid'), arr('ask'), arr('blo'), arr('bhi'), arr('alo'), arr('ahi'), arr('kvol'),
                np.array(rows['real']), np.zeros(W, dtype=bool), rows['ticker'], np.array(rows['crossed'], dtype=np.int16))
    return w.subset(order)


def _f_strike(v) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return np.nan
    return x if x > 0 else np.nan


@dataclass
class Spot:
    """A dense 1-minute grid of one asset's Binance bars (gaps forward-filled). Bar m opens at t0 + 60 s x m."""
    t0: int
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    v: np.ndarray
    filled: np.ndarray  # bool: the bar was missing and forward-filled

    def bar_closing_at(self, t_ms) -> np.ndarray:
        """Index of the bar that closes at t (opened at t - 60 s): the newest bar fully known at t. -1 if before the grid."""
        m = (np.asarray(t_ms, dtype=np.int64) - self.t0) // MIN - 1
        return np.where((m >= 0) & (m < len(self.c)), m, -1)


def load_spot(history_dir: str, asset: str, from_ms: int, to_ms: int) -> Spot:
    if asset.upper() in EXCLUDED_ASSETS:
        raise ValueError(f'{asset} is excluded')
    f = os.path.join(history_dir, 'binance-1m', asset.upper(), '1m.csv')
    try:
        import pandas as pd  # fast path
        df = pd.read_csv(f)
        a = df[['ts', 'o', 'h', 'l', 'c', 'v']].to_numpy(dtype=np.float64)
    except ImportError:
        a = np.loadtxt(f, delimiter=',', skiprows=1, usecols=range(6))
    a = a[(a[:, 0] >= from_ms) & (a[:, 0] < to_ms)]
    if not len(a):
        raise SystemExit(f'no Binance 1m bars for {asset} in range')
    ts = a[:, 0].astype(np.int64)
    t0 = int(ts[0] - ts[0] % MIN)
    idx = (ts - t0) // MIN
    M = int(idx[-1]) + 1
    out = np.full((M, 5), np.nan)
    out[idx] = a[:, 1:6]
    filled = np.isnan(out[:, 3])
    # Forward-fill the gaps with a flat bar at the last close and no volume.
    last = np.maximum.accumulate(np.where(~filled, np.arange(M), 0))
    c = out[last, 3]
    o_ = np.where(filled, c, out[:, 0]); h = np.where(filled, c, out[:, 1]); l = np.where(filled, c, out[:, 2]); v = np.where(filled, 0.0, out[:, 4])
    return Spot(t0, o_, h, l, c, v, filled)
