#!/usr/bin/env python3
"""Round 17 M2: anchor-free alignment of a long weekly series (child) to a short daily series (parent).

Hidden Markov alignment in the style of Lin, Khider, Lisiecki and Lawrence 2014 (doi 10.1002/2014PA002713):
  hidden state each child week = (position s on the parent's daily grid, speed level k)
  speed level: sticky random walk over log-spaced speeds (parent days per child week), switch probability q
  advance per child week ~ Poisson(speed), position never moves back; the last parent day absorbs
  observation: child value ~ (1 - EPS) Normal(a + b * parent value at s, sd) + EPS * flat, b > 0;
  the amplitude b is profiled over a fixed grid (free b lets the fit sit on a few parent weeks and blow up their noise);
  the offset a and the spread sd are fitted by EM at each b
The start is pinned to the parent's first day; the end is free, or (end_min) must have reached a given parent day.
"""
import numpy as np
from scipy import sparse
from scipy.stats import poisson

SPEEDS = np.exp(np.linspace(np.log(0.05), np.log(10.0), 16))   # parent days per child week; pace = 7 / speed
DMAX = 45
EPS = 0.05


class Model:
    def __init__(self, S, q=0.05, speeds=SPEEDS, dmax=DMAX):
        self.S, self.K, self.speeds, self.q = S, len(speeds), speeds, q
        blocks = []
        for v in speeds:
            pm = poisson.pmf(np.arange(dmax + 1), v); pm[-1] += 1.0 - pm.sum()
            keep = np.where(pm > 1e-13)[0]
            rows = np.repeat(np.arange(S), len(keep)); cols = np.minimum(rows + np.tile(keep, S), S - 1)
            blocks.append(sparse.coo_matrix((np.tile(pm[keep], S), (rows, cols)), shape=(S, S)).tocsr())
        self.Mb = sparse.block_diag(blocks, format="csr")       # (k, s) -> (k, s'), row-stochastic
        self.Mf = self.Mb.T.tocsr()
        T = np.zeros((self.K, self.K))
        for k in range(self.K):
            T[k, k] = 1 - q
            for n in (k - 1, k + 1):
                T[k, n if 0 <= n < self.K else k] += q / 2
        self.T = T

    def step_f(self, al):                 # al: S x K -> predicted S x K
        return (self.Mf @ (al @ self.T).T.ravel()).reshape(self.K, self.S).T

    def step_b(self, v):                  # v: S x K -> S x K
        return (self.Mb @ v.T.ravel()).reshape(self.K, self.S).T @ self.T.T


def emis(y, x, a, b, sd, flat):
    z = (y[:, None] - (a + b * x[None, :])) / sd
    n = (1 - EPS) * np.exp(-0.5 * z * z) / (sd * np.sqrt(2 * np.pi))
    return n + EPS * flat, n


def forward(m, E, upto=None):
    J = E.shape[0] if upto is None else upto
    al = np.zeros((J, m.S, m.K)); c = np.zeros(J)
    al[0, 0, :] = E[0, 0] / m.K
    c[0] = al[0].sum(); al[0] /= c[0]
    for j in range(1, J):
        al[j] = m.step_f(al[j - 1]) * E[j][:, None]
        c[j] = al[j].sum(); al[j] /= c[j]
    return al, c


def smooth(m, E, end_min=None):
    """Posterior over (position, speed) each week. end_min: the last week must sit at parent day >= end_min."""
    al, c = forward(m, E)
    J = len(c)
    ll = float(np.log(c).sum())
    be = np.ones((m.S, m.K))
    if end_min is not None:
        be[:end_min, :] = 0.0
        ll += float(np.log(max((al[-1] * be).sum(), 1e-300)))
    g = np.zeros_like(al); g[-1] = al[-1] * be; g[-1] /= max(g[-1].sum(), 1e-300)
    for j in range(J - 1, 0, -1):
        be = m.step_b(E[j][:, None] * be); be /= max(be.max(), 1e-300)
        g[j - 1] = al[j - 1] * be
        g[j - 1] /= max(g[j - 1].sum(), 1e-300)
    return g, ll, al


def fit_b(y, x, b, m, iters=8, end_min=None, keep=False):
    """Fixed amplitude b; EM over the offset a and the spread sd. Returns the fit at this b."""
    y, x = np.asarray(y, float), np.asarray(x, float)
    flat = 1.0 / max(y.max() - y.min(), 1e-9)
    xr = x if end_min is None else x[:end_min + 15]
    a = float(np.median(y)) - b * float(np.median(xr)); sd = 0.3 * y.std()
    for it in range(iters + 1):
        E, N = emis(y, x, a, b, sd, flat)
        g, ll, al = smooth(m, E, end_min)
        if it == iters:
            break
        W = g.sum(axis=2) * (N / E)
        tot = W.sum()
        a = float((W * (y[:, None] - b * x[None, :])).sum() / tot)
        sd = max(float(np.sqrt((W * (y[:, None] - a - b * x[None, :]) ** 2).sum() / tot)), 0.02 * y.std() + 1e-9)
    W = g.sum(axis=2)
    base = -0.5 * len(y) * (np.log(2 * np.pi * y.var()) + 1)
    r = {"b": b, "a": a, "sd": sd, "loglik": ll, "gainPerWeek": (ll - base) / len(y), "W": W, "logSpeed": g.sum(axis=1) @ np.log(m.speeds),
         "inlier": float((W * (N / E)).sum() / len(y))}
    if keep:
        r["filtered"] = al.sum(axis=2)
    return r


B_GRID = (1.0, 1.5, 2.0, 2.3, 2.6, 3.0, 3.5, 4.5)


def profile(y, x, m, end_min=None, grid=B_GRID, keep=False):
    """The fit at every amplitude on the grid; returns (best by log-likelihood, all)."""
    fits = [fit_b(y, x, b, m, end_min=end_min, keep=keep) for b in grid]
    return max(fits, key=lambda r: r["loglik"]), fits


def first_passage(W):
    """F[j, s] = P(position at week j >= s) = P(the map has reached parent day s by week j)."""
    return W[:, ::-1].cumsum(axis=1)[:, ::-1]


def passage_weeks(W, s, qs=(0.1, 0.5, 0.9)):
    F = first_passage(W)[:, s]
    return [int(np.searchsorted(F, q)) if F[-1] >= q else None for q in qs]
