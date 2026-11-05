"""Synthetic contract quotes for windows with no recorded Kalshi quotes (the hourly series are not on Drive).

A zero-drift digital (Black-Scholes) fair value  P(YES) = Phi( ln(S/K) / (lam * sigma_1m * sqrt(minutes left)) ),
sigma_1m the 60-minute realized volatility of 1-minute log returns, lam calibrated on REAL 15-minute Kalshi mids,
and a half-spread table learned from the real books by minutes-left share x distance from 50c. The next minute's
quote range (for maker fills) comes from the fair value at the next spot bar's high and low.

Calibration uses only days before the first test span. Synthetic windows are reported apart and never enter the
gate; their fidelity is measured by pricing real 15-minute windows synthetically and comparing (the synth15 arm).
"""
from __future__ import annotations

import numpy as np

from .data import MIN, Spot, Windows
from .features import _ncdf

TAU_BINS = np.array([0.0, 0.2, 0.4, 0.6, 0.8, 1.01])
DIST_BINS = np.array([0.0, 0.1, 0.2, 0.3, 0.4, 0.51])


def _fair(S, K, sig, tau, lam):
    with np.errstate(divide='ignore', invalid='ignore'):
        z = np.log(S / K) / (lam * np.maximum(sig, 1e-5) * np.sqrt(np.maximum(tau, 1e-3)))
    return _ncdf(np.clip(z, -12, 12))


def calibrate(w: Windows, S: np.ndarray, rv60: np.ndarray, mask: np.ndarray) -> dict:
    """Fit lam and the half-spread table on the real windows selected by `mask`."""
    N = w.n
    tau = (N - np.arange(N))[None, :].astype(np.float64)
    b, a = w.bid[mask], w.ask[mask]
    mid = (b + a) / 2
    ok = np.isfinite(mid) & np.isfinite(S[mask]) & np.isfinite(rv60[mask])
    K = w.strike[mask][:, None] * np.ones((1, N))
    Ss, sg, tt = S[mask][ok], rv60[mask][ok], (tau * np.ones((mask.sum(), 1)))[ok]
    mm, KK = mid[ok], K[ok]
    best = (np.inf, 1.0)
    for lam in np.arange(0.5, 3.01, 0.05):
        e = float(np.mean((_fair(Ss, KK, sg, tt, lam) - mm) ** 2))
        if e < best[0]:
            best = (e, float(lam))
    lam = best[1]
    fair = _fair(Ss, KK, sg, tt, lam)
    hs = ((a - b) / 2)[ok]
    tf = tt / N
    ti = np.clip(np.digitize(tf, TAU_BINS) - 1, 0, len(TAU_BINS) - 2)
    di = np.clip(np.digitize(np.abs(fair - 0.5), DIST_BINS) - 1, 0, len(DIST_BINS) - 2)
    table = np.full((len(TAU_BINS) - 1, len(DIST_BINS) - 1), np.nan)
    for x in range(table.shape[0]):
        for y in range(table.shape[1]):
            sel = (ti == x) & (di == y) & np.isfinite(hs)
            if sel.sum() >= 30:
                table[x, y] = float(np.median(hs[sel]))
    fill = float(np.nanmedian(hs)) if np.isfinite(hs).any() else 0.01
    table = np.where(np.isfinite(table), table, fill)
    return dict(lam=lam, mse=best[0], half_spread=table.tolist(), n=int(ok.sum()))


def _half_spread(params, tau_frac, fair):
    t = np.asarray(params['half_spread'])
    ti = np.clip(np.digitize(tau_frac, TAU_BINS) - 1, 0, t.shape[0] - 1)
    di = np.clip(np.digitize(np.abs(fair - 0.5), DIST_BINS) - 1, 0, t.shape[1] - 1)
    return np.maximum(t[ti, di], 0.005)


def _quote(fair, hs):
    bid = np.clip(np.floor((fair - hs) * 100 + 1e-9) / 100, 0.01, 0.98)
    ask = np.clip(np.ceil((fair + hs) * 100 - 1e-9) / 100, 0.02, 0.99)
    ask = np.maximum(ask, bid + 0.01)
    return bid, ask


def price_windows(w: Windows, spots: dict[int, Spot], rv60_at: np.ndarray, params: dict) -> Windows:
    """The same windows (strike, settlement) with synthetic quotes in place of the real ones."""
    W, N = len(w), w.n
    t = w.open_ms[:, None] + MIN * np.arange(N)[None, :]
    S = np.full((W, N), np.nan); Hn = np.full((W, N), np.nan); Ln = np.full((W, N), np.nan)
    for ai in np.unique(w.asset):
        sel = w.asset == ai
        sp = spots[int(ai)]
        m = sp.bar_closing_at(t[sel])
        ok = m >= 0
        mm = np.where(ok, m, 0)
        nx = np.minimum(mm + 1, len(sp.c) - 1)
        S[sel] = np.where(ok, sp.c[mm], np.nan)
        Hn[sel] = np.where(ok, sp.h[nx], np.nan)
        Ln[sel] = np.where(ok, sp.l[nx], np.nan)
    tau = (N - np.arange(N))[None, :].astype(np.float64) * np.ones((W, 1))
    K = w.strike[:, None]
    lam = params['lam']
    fair = _fair(S, K, rv60_at, tau, lam)
    hs = _half_spread(params, tau / N, fair)
    bid, ask = _quote(fair, hs)
    tn = np.maximum(tau - 1, 0.05)
    fh, fl = _fair(Hn, K, rv60_at, tn, lam), _fair(Ln, K, rv60_at, tn, lam)
    bh, ah = _quote(fh, _half_spread(params, tn / N, fh))
    bl, al = _quote(fl, _half_spread(params, tn / N, fl))
    bad = ~np.isfinite(fair)
    for x in (bid, ask, bh, ah, bl, al):
        x[bad] = np.nan
    return Windows(N, w.asset, w.assets, w.open_ms, w.strike, w.settle, bid, ask, np.fmin(bl, bid), np.fmax(bh, bid), np.fmin(al, ask),
                   np.fmax(ah, ask), np.zeros((W, N)), np.zeros(W), np.ones(W, dtype=bool), list(w.tickers))


def hourly_windows(spots: dict[int, Spot], assets: list[str], from_ms: int, to_ms: int, offsets=(0.0,), n: int = 60) -> Windows:
    """Synthetic hourly 'above strike at the close' windows: strike = spot at the open x (1 + offset x sigma_1h),
    settlement = the Binance close at the hour's end above the strike (Kalshi settles on the CF index average of the
    last minute: a basis this proxy does not have). Quotes are filled in by price_windows."""
    parts = []
    for ai, sp in spots.items():
        h0 = ((max(from_ms, sp.t0 + 2 * 3_600_000) + 3_599_999) // 3_600_000) * 3_600_000
        opens = np.arange(h0, to_ms - n * MIN, 3_600_000, dtype=np.int64)
        m0 = sp.bar_closing_at(opens)
        m1 = sp.bar_closing_at(opens + n * MIN)
        ok = (m0 >= 60) & (m1 >= 0)
        opens, m0, m1 = opens[ok], m0[ok], m1[ok]
        lr = np.diff(np.log(sp.c))
        sig1h = np.array([np.std(lr[max(0, a - 60):a]) for a in m0]) * np.sqrt(60)
        for off in offsets:
            K = sp.c[m0] * (1 + off * sig1h)
            settle = (sp.c[m1] > K).astype(np.float64)
            W = len(opens)
            nanWN = np.full((W, n), np.nan)
            parts.append(Windows(n, np.full(W, ai, dtype=np.int16), assets, opens, K, settle, nanWN.copy(), nanWN.copy(), nanWN.copy(),
                                 nanWN.copy(), nanWN.copy(), nanWN.copy(), np.zeros((W, n)), np.zeros(W), np.ones(W, dtype=bool),
                                 [f'SYN-{assets[ai]}-1H-{o}-{off:+.2f}' for o in opens.tolist()]))
    w = Windows.concat(parts)
    return w.subset(np.argsort(w.open_ms, kind='stable'))
