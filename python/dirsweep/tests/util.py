"""Synthetic minute grids for the tests: volatility clusters, volume, taker flow, optional planted reversal."""
import numpy as np

from dirsweep import grid as G


def make_grid(days: int, seed: int = 1, reversal: float = 0.0, gap_days=(), level: float = 100.0, t0: int = None) -> dict:
    """`reversal` > 0 plants a mean reversion: after a 15-minute noise sum of at least 2 sigma the next 15 minutes drift back by reversal x that sum."""
    n = days * 1440
    rng = np.random.default_rng(seed)
    vol = np.repeat(np.exp(0.4 * rng.standard_normal(days)), 1440) * 4e-4
    eps = rng.standard_normal(n) * vol
    r = eps.copy()
    if reversal:
        cs = np.concatenate([[0.0], np.cumsum(eps)])
        s15 = np.zeros(n)
        s15[15:] = cs[15:n] - cs[:n - 15]                                  # noise sum of minutes e-15..e-1, known at e
        sig = vol * np.sqrt(15)
        sig_shift = np.concatenate([sig[:1], sig[:-1]])
        trig = np.where(np.abs(s15) >= 2.0 * sig_shift, s15, 0.0)
        r = r - reversal / 15.0 * trig
    c = level * np.exp(np.cumsum(r))
    o = np.concatenate([[c[0]], c[:-1]])
    wick = np.abs(rng.standard_normal(n)) * vol * 0.3
    h = np.maximum(o, c) * (1 + wick)
    l = np.minimum(o, c) * (1 - wick)
    v = np.exp(rng.standard_normal(n) * 0.5) * 10.0 * np.repeat(np.exp(0.3 * rng.standard_normal(days)), 1440)
    sign = np.sign(r)
    tb = np.clip(v * (0.5 + 0.12 * sign + 0.08 * rng.standard_normal(n)), 0, v)
    gap = np.zeros(n, bool)
    for d in gap_days:
        gap[d * 1440:(d + 1) * 1440] = True
        v[d * 1440:(d + 1) * 1440] = 0
        tb[d * 1440:(d + 1) * 1440] = 0
    return {'t0': G.SEARCH_START if t0 is None else t0, 'n': n, 'o': o, 'h': h, 'l': l, 'c': c, 'v': v, 'tb': tb, 'gap': gap}
