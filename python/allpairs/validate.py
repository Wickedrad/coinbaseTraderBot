"""Purged walk-forward splits, the probabilistic and deflated Sharpe ratios, and block-bootstrap intervals.

Walk-forward: train on `train_days` consecutive days, skip `embargo_days` (the purge: no training window's label or
feature lookback reaches into the test span; windows are 15-60 minutes and features look back at most 60 minutes, so
one day is ample), test on the next `test_days`, step forward by `test_days`. The test spans never overlap and every
model is refitted per fold from its own training days only.

Deflated Sharpe (Bailey and Lopez de Prado, 2014): the probability that the true Sharpe exceeds the best Sharpe that
`n_trials` unskilled tries would show by luck, given the trials' Sharpe variance, the returns' skew and kurtosis and
the number of observations. Every configuration this project has scored is a trial (trial ledger on Drive).
"""
from __future__ import annotations

import math

import numpy as np

EULER_GAMMA = 0.5772156649015329


def walk_forward(days: np.ndarray, train_days: int, test_days: int, embargo_days: int = 1, rolling: bool = True):
    """Folds over the sorted unique `days` (day numbers): list of (train_days array, test_days array)."""
    u = np.unique(days)
    if not len(u):
        return []
    d0, d1 = int(u[0]), int(u[-1])
    folds = []
    start = d0
    while True:
        tr_lo = start if rolling else d0
        tr_hi = start + train_days            # exclusive
        te_lo = tr_hi + embargo_days
        te_hi = te_lo + test_days
        if te_lo > d1:
            break
        tr = u[(u >= tr_lo) & (u < tr_hi)]
        te = u[(u >= te_lo) & (u < te_hi)]
        if len(tr) >= max(1, train_days // 2) and len(te):
            folds.append((tr, te))
        start += test_days
    return folds


def inner_split(train: np.ndarray, inner_days: int, embargo_days: int = 1):
    """(fit days, validation days) inside a training span: the last `inner_days` validate, after an embargo."""
    u = np.unique(train)
    if len(u) <= inner_days + embargo_days + 5:
        return u, u[:0]
    return u[: len(u) - inner_days - embargo_days], u[len(u) - inner_days:]


def _norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _norm_ppf(p: float) -> float:
    from scipy.special import ndtri
    return float(ndtri(p))


def moments(r: np.ndarray):
    r = np.asarray(r, dtype=np.float64)
    n = len(r)
    sd = r.std(ddof=1) if n > 1 else 0.0
    if n < 3 or sd == 0:
        return 0.0, 0.0, 3.0
    z = (r - r.mean()) / r.std(ddof=0)
    return float(r.mean() / sd), float(np.mean(z ** 3)), float(np.mean(z ** 4))


def psr(r: np.ndarray, sr_benchmark: float = 0.0) -> float:
    """Probabilistic Sharpe ratio of per-period returns r against a benchmark Sharpe (same period)."""
    sr, skew, kurt = moments(r)
    n = len(r)
    if n < 3:
        return 0.0
    den = 1 - skew * sr + (kurt - 1) / 4 * sr * sr
    if den <= 0:
        return 0.0
    return _norm_cdf((sr - sr_benchmark) * math.sqrt(n - 1) / math.sqrt(den))


def expected_max_sr(n_trials: int, sr_var: float) -> float:
    """Expected maximum Sharpe of n_trials unskilled strategies whose Sharpes have variance sr_var."""
    if n_trials <= 1 or sr_var <= 0:
        return 0.0
    a = _norm_ppf(1 - 1 / n_trials)
    b = _norm_ppf(1 - 1 / (n_trials * math.e))
    return math.sqrt(sr_var) * ((1 - EULER_GAMMA) * a + EULER_GAMMA * b)


def dsr(r: np.ndarray, n_trials: int, sr_var: float) -> dict:
    sr0 = expected_max_sr(n_trials, sr_var)
    sr, skew, kurt = moments(r)
    return dict(dsr=round(psr(r, sr0), 4), sr=round(sr, 5), sr0=round(sr0, 5), n_trials=int(n_trials), sr_var=sr_var,
                skew=round(skew, 3), kurt=round(kurt, 3), n=int(len(r)))


def block_bootstrap_mean(x: np.ndarray, block: int = 24, draws: int = 2000, seed: int = 3):
    """95% interval of the mean of a series by a moving-block bootstrap (blocks of `block` periods)."""
    x = np.asarray(x, dtype=np.float64)
    n = len(x)
    if n < 2:
        return (float('nan'), float('nan'))
    rng = np.random.default_rng(seed)
    b = max(1, min(block, n))
    nb = int(math.ceil(n / b))
    starts = rng.integers(0, n - b + 1, size=(draws, nb))
    idx = (starts[:, :, None] + np.arange(b)[None, None, :]).reshape(draws, -1)[:, :n]
    means = x[idx].mean(axis=1)
    return (float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5)))
