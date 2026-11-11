"""The feature vector X_t at each decision time, from information known at t only.

Spot features come from the Binance bar that CLOSES at t (opened at t - 60 s) and earlier bars: returns, realized
volatility, RSI, Bollinger width and %b, MACD velocity, an OU residual (price against its 60-minute EMA in volatility
units), volume z-score and range. Contract features come from the Kalshi quote at t: the side's bid/ask/mid/spread,
the strike distance in volatility units, a zero-drift digital fair value and its gap to the market, recent mid
changes, minutes to expiry and traded volume. Directional features are flipped for the NO side so one model serves
both sides (the side flag stays in).

Extra features are expressions over these names (the hypothesis loop's constrained action space): + - * / ** and
abs, log1p, sqrt, tanh, sign, min, max of named features and numbers only, evaluated with NumPy; nothing else parses.
"""
from __future__ import annotations

import ast
import math

import numpy as np

from .data import MIN, Spot, Windows

SQRT2 = math.sqrt(2.0)


def _ncdf(x):
    from scipy.special import ndtr
    return ndtr(x)


def _rolling_sum(x: np.ndarray, n: int) -> np.ndarray:
    cs = np.concatenate([[0.0], np.cumsum(np.nan_to_num(x))])
    out = cs[n:] - cs[:-n]
    return np.concatenate([np.full(n - 1, np.nan), out])


def _rolling_mean(x, n):
    return _rolling_sum(x, n) / n


def _rolling_std(x, n):
    m = _rolling_mean(x, n)
    m2 = _rolling_mean(x * x, n)
    return np.sqrt(np.maximum(m2 - m * m, 0.0))


def _ema(x: np.ndarray, alpha: float) -> np.ndarray:
    from scipy.signal import lfilter
    x = np.asarray(x, dtype=np.float64)
    y, _ = lfilter([alpha], [1.0, alpha - 1.0], x, zi=[x[0] * (1 - alpha)])
    return y


def spot_features(sp: Spot) -> dict[str, np.ndarray]:
    c = sp.c
    lc = np.log(c)
    lr = np.concatenate([[0.0], np.diff(lc)])
    f: dict[str, np.ndarray] = {}
    for n in (1, 3, 5, 15, 60):
        f[f'r{n}'] = np.concatenate([np.full(n, np.nan), lc[n:] - lc[:-n]])
    f['rv15'] = _rolling_std(lr, 15)
    f['rv60'] = _rolling_std(lr, 60)
    f['rv_ratio'] = f['rv15'] / np.maximum(f['rv60'], 1e-7)
    up = np.maximum(np.diff(c, prepend=c[0]), 0.0)
    dn = np.maximum(-np.diff(c, prepend=c[0]), 0.0)
    au, ad = _ema(up, 1 / 14), _ema(dn, 1 / 14)
    f['rsi14'] = 100.0 - 100.0 / (1.0 + au / np.maximum(ad, 1e-12))
    m20, s20 = _rolling_mean(c, 20), _rolling_std(c, 20)
    f['bbw20'] = 4 * s20 / m20
    f['bbp20'] = (c - (m20 - 2 * s20)) / np.maximum(4 * s20, 1e-12)
    f['macd'] = (_ema(c, 2 / 13) - _ema(c, 2 / 27)) / c
    e60 = _ema(c, 2 / 61)
    f['ou60'] = np.clip((c - e60) / (c * np.maximum(f['rv60'], 1e-6) * math.sqrt(60)), -10, 10)
    v = sp.v
    f['volz60'] = (v - _rolling_mean(v, 60)) / np.maximum(_rolling_std(v, 60), 1e-9)
    f['atr15'] = _rolling_mean((sp.h - sp.l) / c, 15)
    return {k: x.astype(np.float32) for k, x in f.items()}


# Spot features that change sign (or mirror) for the NO side.
_FLIP = {'r1', 'r3', 'r5', 'r15', 'r60', 'macd', 'ou60'}
_MIRROR100 = {'rsi14'}
_MIRROR1 = {'bbp20'}
SPOT_NAMES = ['r1', 'r3', 'r5', 'r15', 'r60', 'rv15', 'rv60', 'rv_ratio', 'rsi14', 'bbw20', 'bbp20', 'macd', 'ou60', 'volz60', 'atr15']
CONTRACT_NAMES = ['side', 'tau_min', 'tau_frac', 'hour_sin', 'hour_cos', 'dow', 'zdist', 'fair', 'bid', 'ask', 'mid', 'spread',
                  'gap', 'edge_ask', 'edge_bid', 'dmid1', 'dmid3', 'kvol']
BASE_NAMES = SPOT_NAMES + CONTRACT_NAMES


def side_quotes(w: Windows):
    """(bid, ask, nbid_lo, nbid_hi, nask_lo, nask_hi, settle) per side: arrays (W, 2, N) and settle (W, 2).
    NO's bid is 1 - YES ask, its ask 1 - YES bid (highs and lows swap)."""
    st = lambda y, n: np.stack([y, n], axis=1)
    bid = st(w.bid, 1 - w.ask)
    ask = st(w.ask, 1 - w.bid)
    nbl = st(w.nbid_lo, 1 - w.nask_hi)
    nbh = st(w.nbid_hi, 1 - w.nask_lo)
    nal = st(w.nask_lo, 1 - w.nbid_hi)
    nah = st(w.nask_hi, 1 - w.nbid_lo)
    settle = np.stack([w.settle, 1 - w.settle], axis=1)
    return bid, ask, nbl, nbh, nal, nah, settle


def spot_at(w: Windows, spots: dict[int, Spot], feats: dict[int, dict[str, np.ndarray]]):
    """Spot close and features at every decision time: S (W, N) and {name: (W, N)}."""
    W, N = len(w), w.n
    t = w.open_ms[:, None] + MIN * np.arange(N)[None, :]
    S = np.full((W, N), np.nan)
    F = {k: np.full((W, N), np.nan, dtype=np.float32) for k in SPOT_NAMES}
    for ai in np.unique(w.asset):
        sel = w.asset == ai
        sp = spots.get(int(ai))
        if sp is None:
            continue
        m = sp.bar_closing_at(t[sel])
        ok = m >= 0
        mm = np.where(ok, m, 0)
        S[sel] = np.where(ok, sp.c[mm], np.nan)
        for k in SPOT_NAMES:
            F[k][sel] = np.where(ok, feats[int(ai)][k][mm], np.nan)
    return S, F


def cross_at(w: Windows, spot: Spot, feats: dict[str, np.ndarray], label: str, names=('r1', 'r3', 'r5'),
             shift_ms: int = 0) -> dict[str, np.ndarray]:
    """Another asset's spot returns at every decision time of every window ({f'lead_{label}_{name}': (W, N)}): the bar
    that closed at t_k, as for the window's own asset (no lookahead). For a lead-lag hypothesis: does a BTC move reach
    the other assets' Kalshi quotes a minute late? shift_ms > 0 takes the bar that closed at t_k - shift_ms instead (a
    placebo: lead_shift24 uses the same minute a day earlier)."""
    t = w.open_ms[:, None] + MIN * np.arange(w.n)[None, :] - int(shift_ms)
    m = spot.bar_closing_at(t)
    ok = m >= 0
    mm = np.where(ok, m, 0)
    return {f'lead_{label}_{n}': np.where(ok, feats[n][mm], np.nan).astype(np.float32) for n in names}


def window_features(w: Windows, S: np.ndarray, F: dict[str, np.ndarray], extra: list[dict] | None = None,
                    cross: dict[str, np.ndarray] | None = None):
    """X (W, 2, N, n_features) float32 and the feature names. `cross`: other assets' spot returns (cross_at), signed
    like the window's own returns (flipped for the NO side)."""
    W, N = len(w), w.n
    bid, ask, *_ = side_quotes(w)
    k = np.arange(N)[None, :]
    tau = (N - k).astype(np.float64) * np.ones((W, 1))
    sig = np.maximum(np.nan_to_num(F['rv60'], nan=1e-4), 1e-5).astype(np.float64)
    with np.errstate(divide='ignore', invalid='ignore'):
        z = np.log(S / w.strike[:, None]) / (sig * np.sqrt(tau))
    z = np.clip(z, -12, 12)
    fair = _ncdf(z)
    t = w.open_ms[:, None] + MIN * k
    hours = ((t // 3_600_000) % 24 + (t % 3_600_000) / 3_600_000.0)
    cols: dict[str, np.ndarray] = {}
    for s in (0, 1):
        sgn = 1.0 if s == 0 else -1.0
        b, a = bid[:, s], ask[:, s]
        mid = (b + a) / 2
        fs = fair if s == 0 else 1 - fair
        d1 = np.concatenate([np.zeros((W, 1)), np.diff(mid, axis=1)], axis=1)
        d3 = np.concatenate([np.zeros((W, 3)), mid[:, 3:] - mid[:, :-3]], axis=1) if N > 3 else d1
        side_cols = {
            'side': np.full((W, N), float(s)), 'tau_min': tau, 'tau_frac': tau / N,
            'hour_sin': np.sin(2 * np.pi * hours / 24), 'hour_cos': np.cos(2 * np.pi * hours / 24),
            'dow': ((t // 86_400_000 + 3) % 7).astype(np.float64),  # 0 = Monday
            'zdist': sgn * z, 'fair': fs, 'bid': b, 'ask': a, 'mid': mid, 'spread': a - b, 'gap': fs - mid,
            'edge_ask': fs - a, 'edge_bid': b - fs, 'dmid1': d1, 'dmid3': d3, 'kvol': np.log1p(w.kvol),
        }
        for name in SPOT_NAMES:
            x = F[name].astype(np.float64)
            if s == 1:
                if name in _FLIP:
                    x = -x
                elif name in _MIRROR100:
                    x = 100 - x
                elif name in _MIRROR1:
                    x = 1 - x
            side_cols[name] = x
        for name, x in sorted((cross or {}).items()):
            side_cols[name] = x.astype(np.float64) * sgn
        for name, x in side_cols.items():
            cols.setdefault(name, [None, None])[s] = x
    names = list(BASE_NAMES) + sorted(cross or {})
    X = np.empty((W, 2, N, len(names) + len(extra or [])), dtype=np.float32)
    for j, name in enumerate(names):
        X[:, 0, :, j] = cols[name][0]
        X[:, 1, :, j] = cols[name][1]
    for e in extra or []:
        env = {nm: X[..., i] for i, nm in enumerate(names)}
        X[..., len(names)] = safe_eval(e['expr'], env)
        names.append(e['name'])
    return X, names


_FUNCS = {'abs': np.abs, 'log1p': np.log1p, 'sqrt': lambda x: np.sqrt(np.abs(x)), 'tanh': np.tanh, 'sign': np.sign,
          'min': np.minimum, 'max': np.maximum}
_OPS = {ast.Add: np.add, ast.Sub: np.subtract, ast.Mult: np.multiply, ast.Div: lambda a, b: np.divide(a, np.where(b == 0, np.nan, b)),
        ast.Pow: lambda a, b: np.sign(a) * np.abs(a) ** b}


def safe_eval(expr: str, env: dict[str, np.ndarray]) -> np.ndarray:
    """Evaluate a feature expression: names from env, numbers, + - * / **, unary minus, whitelisted functions."""
    tree = ast.parse(expr, mode='eval')

    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            v = ev(node.operand)
            return -v if isinstance(node.op, ast.USub) else v
        if isinstance(node, ast.Name):
            if node.id not in env:
                raise ValueError(f'unknown feature {node.id!r}')
            return env[node.id].astype(np.float64)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return float(node.value)
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS and not node.keywords
                and 1 <= len(node.args) <= 2):
            return _FUNCS[node.func.id](*[ev(a) for a in node.args])
        raise ValueError(f'not allowed in a feature expression: {ast.dump(node)[:80]}')

    with np.errstate(all='ignore'):
        out = np.asarray(ev(tree), dtype=np.float64)
    return np.where(np.isfinite(out), out, np.nan).astype(np.float32)
