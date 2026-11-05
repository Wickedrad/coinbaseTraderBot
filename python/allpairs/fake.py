"""A small fake history in the Drive layout (Kalshi 15-minute candles + Binance 1-minute bars) for tests and smoke runs.

    python -m allpairs.fake --out /tmp/fakehist --days 40 --assets BTC,ETH
"""
from __future__ import annotations

import argparse
import json
import math
import os

import numpy as np

from .features import _ncdf

DAY = 86_400_000
MIN = 60_000


def make(out: str, days: int = 40, assets=('BTC', 'ETH'), seed: int = 1, start_ms: int = 1_767_225_600_000, lag: float = 0.6) -> None:
    """Spot: a random walk sampled every 15 s. Kalshi: 'up in 15 minutes' contracts quoted around a digital fair value
    that LAGS the spot by `lag` of a minute (so quotes are predictable from spot: a planted edge for smoke tests)."""
    rng = np.random.default_rng(seed)
    for ai, asset in enumerate(assets):
        n15 = (days + 1) * 24 * 60 * 4 + 8
        p0 = 100.0 * (ai + 1) * 10
        steps = rng.normal(0, 0.0004, n15)
        px = p0 * np.exp(np.cumsum(steps))
        t15 = start_ms - DAY + np.arange(n15) * 15_000   # one day of warm-up bars before the first market
        bars = px.reshape(-1, 4)
        ts = t15[::4]
        d = os.path.join(out, 'binance-1m', asset)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, '1m.csv'), 'w') as fh:
            fh.write('ts,o,h,l,c,v\n')
            for t, b in zip(ts.tolist(), bars):
                fh.write(f'{t},{b[0]:.6f},{b.max():.6f},{b.min():.6f},{b[-1]:.6f},{rng.integers(1, 50)}\n')
        sig = 0.0004 * 2  # per-minute
        kd = os.path.join(out, 'kalshi', f'KX{asset}15M')
        os.makedirs(kd, exist_ok=True)
        files: dict[str, list[str]] = {}
        for o in range(start_ms, start_ms + days * DAY, 15 * MIN):
            q0 = (o - t15[0]) // 15_000
            K = float(px[q0 - 1])
            close_px = float(px[q0 + 60 - 1])
            candles = []
            for c in range(1, 16):
                lo_q, hi_q = q0 + (c - 1) * 4, q0 + c * 4
                vals = []
                for q in range(lo_q, hi_q + 1):
                    ql = max(0, q - int(lag * 4))
                    tau = max(15 - (q - q0) / 4, 0.05)
                    f = float(_ncdf(math.log(px[ql] / K) / (sig * math.sqrt(tau))))
                    vals.append(f)
                hs = 0.01 + 0.01 * rng.integers(0, 2)
                bids = [max(0.01, math.floor((v - hs) * 100) / 100) for v in vals]
                asks = [min(0.99, max(b + 0.01, math.ceil((v + hs) * 100) / 100)) for v, b in zip(vals, bids)]
                candles.append(dict(ts=o + c * MIN, bidO=bids[0], bidH=max(bids), bidL=min(bids), bidC=bids[-1], askO=asks[0], askH=max(asks),
                                    askL=min(asks), askC=asks[-1], last=vals[-1], volume=float(rng.integers(0, 200)), oi=None))
            m = dict(ticker=f'KX{asset}15M-{o}', series=f'KX{asset}15M', openTime=o, closeTime=o + 15 * MIN, strike=K, cap=None,
                     strikeType='greater', result='yes' if close_px > K else 'no', candles=candles)
            day = __import__('datetime').datetime.utcfromtimestamp((o + 15 * MIN) / 1000).strftime('%Y-%m-%d')
            files.setdefault(day, []).append(json.dumps(m))
        for day, lines in files.items():
            with open(os.path.join(kd, f'{day}.jsonl'), 'w') as fh:
                fh.write('\n'.join(lines) + '\n')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--days', type=int, default=40)
    ap.add_argument('--assets', default='BTC,ETH')
    ap.add_argument('--lag', type=float, default=0.6)
    a = ap.parse_args()
    make(a.out, a.days, tuple(a.assets.split(',')), lag=a.lag)
