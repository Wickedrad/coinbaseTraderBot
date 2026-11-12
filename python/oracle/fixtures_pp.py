"""Synthetic fixtures for the Price Prediction part builder (oracle/pp.py, SPEC 2b) and its tests. Nothing here is real data.

- Kalshi markets in the kalshiHistory.ts day-file format (`<history>/kalshi/<SERIES>/<UTC close day>.jsonl`, one settled
  market per line, 1-minute candles with ts = candle END, prices in dollars), so allpairs.data.load_kalshi reads them:
  15-minute "up" contracts (KX<A>15M, strike = spot at the open) and hourly greater-than ladders (KX<A>D, the 4 strikes
  nearest spot at close - 60 min, listed 2 h before the close, candles for the last 70 minutes, as the backfill writes).
- A spot part `parts/spot-<A>/` in the SPEC 1 / 2a format (t_end, X, close, rv60, rv, meta.json), written with
  oracle.common.write_part. Its 3 features are synthetic: sx_ret1 (state: sign of the 1-minute return), sx_mod7 (bucket:
  minute number of t_end mod 7, which pins the join minute in tests) and sx_hour4 (bucket: UTC hour of t_end // 4).

    cd python && python3 -m oracle.fixtures_pp --out /tmp/ppfix --asset BTC --start 2026-05-01 --days 1
    cd python && python3 -m oracle.fixtures_pp --out /tmp/e2e --asset BTC --start 2026-04-13 --days 206 --spot parts/spot-BTC
      (end-to-end: day files only, priced on the exporter's spot part; see make_aligned)
"""
from __future__ import annotations

import argparse
import json
import math
import os
from datetime import datetime, timezone

import numpy as np
from scipy.special import ndtr

from .common import MIN, ms, write_part

HOUR = 60 * MIN


def day_of(t_ms: int) -> str:
    return datetime.fromtimestamp(t_ms / 1000, tz=timezone.utc).strftime('%Y-%m-%d')


# ---------- spot ----------

def spot_path(start_ms: int, minutes: int, seed: int = 1, p0: float = 60_000.0, sig: float = 0.0008):
    """A 1-minute random walk: (t_end (M,) int64 = end of each minute, close (M,) float64)."""
    rng = np.random.default_rng(seed)
    t_end = start_ms + MIN * np.arange(1, minutes + 1, dtype=np.int64)
    close = p0 * np.exp(np.cumsum(rng.normal(0.0, sig, minutes)))
    return t_end, close


def rv60_of(close: np.ndarray) -> np.ndarray:
    """sqrt(sum r^2) over the last 60 one-minute log returns ending at each minute (NaN before 60 returns exist)."""
    r2 = np.concatenate([[np.nan], np.diff(np.log(close)) ** 2])
    cs = np.concatenate([[0.0], np.cumsum(np.nan_to_num(r2))])
    out = np.full(len(close), np.nan)
    if len(close) > 60:
        out[60:] = np.sqrt(cs[61:] - cs[1:-60])
    return out.astype(np.float32)


SPOT_FEATURES = [
    {'name': 'sx_ret1', 'kind': 'state', 'levels': [-1, 0, 1], 'desc': 'fixture: sign of the 1-minute spot return'},
    {'name': 'sx_mod7', 'kind': 'bucket', 'levels': list(range(7)), 'desc': 'fixture: (t_end // 60000) % 7'},
    {'name': 'sx_hour4', 'kind': 'bucket', 'levels': list(range(6)), 'desc': 'fixture: UTC hour of t_end // 4'},
]


def write_spot_part(parts_root: str, asset: str, t_end: np.ndarray, close: np.ndarray, rv: np.ndarray | None = None) -> str:
    """parts/spot-<A>/ in the SPEC format. rv (tercile) defaults to the rv60 terciles over the whole path (fixture only:
    the real builder's terciles are causal, regime v1)."""
    t_end = np.asarray(t_end, dtype=np.int64)
    close = np.asarray(close, dtype=np.float64)
    rv60 = rv60_of(close)
    if rv is None:
        fin = np.isfinite(rv60)
        q = np.quantile(rv60[fin], [1 / 3, 2 / 3]) if fin.any() else [0.0, 0.0]
        rv = np.where(fin, np.searchsorted(q, rv60, side='right'), -1)
    ret = np.concatenate([[0.0], np.diff(np.log(close))])
    X = np.stack([np.sign(ret), (t_end // MIN) % 7, ((t_end // HOUR) % 24) // 4], axis=1).astype(np.int8)
    path = os.path.join(parts_root, f'spot-{asset}')
    meta = {'ct': 'spot', 'scope': asset, 'assets': [asset], 'step_min': 1, 'code_sha': 'fixture', 'features': SPOT_FEATURES,
            'notes': 'synthetic spot part (oracle/fixtures_pp.py), not real data'}
    write_part(path, meta, {'t_end': t_end, 'X': X, 'close': close, 'rv60': rv60, 'rv': np.asarray(rv, dtype=np.int8)})
    return path


# ---------- Kalshi markets ----------

def candle(ts: int, bid: float, ask: float, volume: float = 10.0) -> dict:
    """One flat 1-minute candle (ts = candle END) quoting YES bid/ask in dollars."""
    return {'ts': int(ts), 'bidO': bid, 'bidH': bid, 'bidL': bid, 'bidC': bid, 'askO': ask, 'askH': ask, 'askL': ask, 'askC': ask,
            'last': round((bid + ask) / 2, 4), 'volume': float(volume), 'oi': None}


def market(ticker: str, series: str, open_ms: int, close_ms: int, strike: float, result: str, candles: list, event: str | None = None) -> dict:
    return {'ticker': ticker, 'series': series, 'event': event or ticker.rsplit('-', 1)[0], 'openTime': int(open_ms),
            'closeTime': int(close_ms), 'strike': float(strike), 'cap': None, 'strikeType': 'greater', 'result': result,
            'settlement': 1.0 if result == 'yes' else 0.0, 'volume': float(sum(c.get('volume') or 0 for c in candles)), 'candles': candles}


def quotes_market(ticker: str, series: str, open_ms: int, n: int, strike: float, result: str, quotes: dict, listed_ms: int | None = None) -> dict:
    """A market whose window is the last n minutes before open_ms + n min, with explicit quotes {k: (bid, ask[, volume])}
    at the candle ending at t_k = open + k min (k = 1..n). Minutes not in `quotes` have no candle."""
    close = open_ms + n * MIN
    cs = []
    for k in sorted(quotes):
        q = quotes[k]
        cs.append(candle(open_ms + k * MIN, q[0], q[1], q[2] if len(q) > 2 else 10.0))
    return market(ticker, series, listed_ms if listed_ms is not None else open_ms, close, strike, result, cs)


def write_markets(history_root: str, series: str, markets: list) -> str:
    """Append markets to <history>/kalshi/<series>/<UTC close day>.jsonl (the kalshiHistory.ts layout)."""
    d = os.path.join(history_root, 'kalshi', series)
    os.makedirs(d, exist_ok=True)
    by_day: dict[str, list] = {}
    for m in markets:
        by_day.setdefault(day_of(m['closeTime']), []).append(json.dumps(m))
    for day, lines in by_day.items():
        with open(os.path.join(d, f'{day}.jsonl'), 'a', encoding='utf8') as fh:
            fh.write('\n'.join(lines) + '\n')
    return d


def _quote(fair: float, half: float) -> tuple[float, float]:
    """Whole-cent YES bid/ask around a fair value, a two-sided book inside (0, 1)."""
    b = min(max(math.floor((fair - half) * 100) / 100, 0.01), 0.97)
    a = max(min(math.ceil((fair + half) * 100) / 100, 0.99), round(b + 0.01, 2))
    return round(b, 2), round(a, 2)


def _fair(S: float, K: float, sig_min: float, tau_min: float) -> float:
    return float(ndtr(math.log(S / K) / (sig_min * math.sqrt(max(tau_min, 1e-6)))))


def synth_markets(t_end: np.ndarray, close: np.ndarray, asset: str, start_ms: int, days: int, seed: int = 2,
                  sig_min: float = 0.0008) -> tuple[list, list]:
    """(15-minute markets, hourly ladder markets) for [start, start + days) on the spot path, quoted around the digital
    fair value with 1-3c half spreads; settled on the spot close at the market's close."""
    rng = np.random.default_rng(seed)
    at = {int(t): float(c) for t, c in zip(t_end.tolist(), close.tolist())}
    m15, m60 = [], []
    end = start_ms + days * 86_400_000
    for o in range(start_ms, end, 15 * MIN):
        K = at[o]
        cs = []
        for k in range(1, 16):
            b, a = _quote(_fair(at[o + k * MIN], K, sig_min, 15 - k + 0.5), 0.01 * int(rng.integers(1, 4)))
            cs.append(candle(o + k * MIN, b, a, float(rng.integers(0, 300))))
        res = 'yes' if at[o + 15 * MIN] > K else 'no'
        m15.append(market(f'KX{asset}15M-{day_of(o)}-{o // MIN}', f'KX{asset}15M', o, o + 15 * MIN, K, res, cs))
    step = round(float(close[0]) * 0.002, -1) or 10.0
    for c in range(start_ms + HOUR, end + 1, HOUR):
        o = c - HOUR
        S0 = at[o]
        ladder = (np.floor(S0 / step) + np.arange(-3, 5)) * step - 0.01
        strikes = sorted(ladder[np.argsort(np.abs(ladder - S0), kind='stable')[:4]].tolist())
        for K in strikes:
            cs = []
            for i in range(-9, 61):          # the last 70 minutes, as the hourly backfill stores them
                ts = o + i * MIN
                b, a = _quote(_fair(at[ts], K, sig_min, 60 - i + 0.5), 0.01 * int(rng.integers(1, 4)))
                cs.append(candle(ts, b, a, float(rng.integers(0, 500))))
            res = 'yes' if at[c] > K else 'no'
            tk = f'KX{asset}D-{datetime.fromtimestamp(c / 1000, tz=timezone.utc).strftime("%y%b%d%H").upper()}-T{K:.2f}'
            m60.append(market(tk, f'KX{asset}D', c - 2 * HOUR, c, K, res, cs))
    return m15, m60


def make(out: str, asset: str = 'BTC', start: str = '2026-05-01', days: int = 1, seed: int = 1) -> dict:
    """A full fixture under `out`: history/kalshi/KX<A>15M + KX<A>D and parts/spot-<A>/ (spot from 1 day before start)."""
    if asset.upper() == 'DOGE':
        raise ValueError('DOGE refused')
    s = ms(start)
    t_end, close = spot_path(s - 86_400_000, (days + 2) * 1440, seed=seed)
    hist, parts = os.path.join(out, 'history'), os.path.join(out, 'parts')
    m15, m60 = synth_markets(t_end, close, asset, s, days, seed=seed + 1)
    write_markets(hist, f'KX{asset}15M', m15)
    write_markets(hist, f'KX{asset}D', m60)
    spot = write_spot_part(parts, asset, t_end, close)
    return {'history': hist, 'parts': parts, 'spot': spot, 'n15': len(m15), 'n60': len(m60)}


def make_aligned(out: str, spot_dir: str, asset: str = 'BTC', start: str = '2026-04-13', days: int = 1, seed: int = 1) -> dict:
    """Kalshi day files only (<out>/history/kalshi/KX<A>15M + KX<A>D), priced and settled on an EXISTING spot part (the
    exporter's parts/spot-<A>/, research/oracle/oracleExport.ts) for windows opening in [start, start + days): the
    end-to-end fixture, so pp.py's spot join, z and fair read the same spot the markets were made from."""
    if 'DOGE' in asset.upper() or 'DOGE' in os.path.basename(os.path.normpath(spot_dir)).upper():
        raise ValueError('DOGE refused')
    from .common import Part
    sp = Part(spot_dir)
    t_end, close = np.asarray(sp['t_end'], dtype=np.int64), np.asarray(sp['close'], dtype=np.float64)
    rv60 = np.asarray(sp['rv60'], dtype=np.float64)
    sig = float(np.nanmedian(rv60) / math.sqrt(60.0)) if np.isfinite(rv60).any() else 0.0008
    hist = os.path.join(out, 'history')
    m15, m60 = synth_markets(t_end, close, asset, ms(start), days, seed=seed + 1, sig_min=sig)
    write_markets(hist, f'KX{asset}15M', m15)
    write_markets(hist, f'KX{asset}D', m60)
    return {'history': hist, 'spot': spot_dir, 'n15': len(m15), 'n60': len(m60), 'sig_min': sig}


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='Write a synthetic Price Prediction fixture (Kalshi day files + spot part).')
    ap.add_argument('--out', required=True)
    ap.add_argument('--asset', default='BTC')
    ap.add_argument('--start', default='2026-05-01')
    ap.add_argument('--days', type=int, default=1)
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--spot', default=None, help='price the markets on this existing spot part (no spot part is written)')
    a = ap.parse_args()
    if a.spot:
        r = make_aligned(a.out, a.spot, a.asset.upper(), a.start, a.days, a.seed)
    else:
        r = make(a.out, a.asset.upper(), a.start, a.days, a.seed)
    print(json.dumps(r))
