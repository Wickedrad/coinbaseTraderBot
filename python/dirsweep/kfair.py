"""Does the spot price tell more than Kalshi's own quote? (Steven, Nov 21 2026: recorded days only.)

A 15-minute window pays YES if the coin ends above the strike set at the open. At minute k the coin is at S, the strike is K and 15 - k minutes remain, so a
plain digital-option model says

    P(YES) = Phi( ln(S / K) / (sigma x sqrt(15 - k)) ),   sigma = the coin's own 1-minute volatility over the trailing 120 minutes.

Nothing in it is fitted. Two questions, both on recorded windows and both scored with the real quotes, settlements and taker fees:

  1. information  fit a logistic on the first part of the history, settle ~ logit(quote mid) + logit(model), and compare log-loss with the quote alone on the
                  later part. If the model adds nothing, the quote already holds what the spot says.
  2. trading      buy the side whose model edge over its ask is at least `edge` at the first minute of a range of minutes that qualifies; net dollars per
                  contract after fees, by period, with a day-cluster interval.
"""
import math

import numpy as np

from allpairs import fees as KF
from dirsweep import grid as G

STAKE = 10.0
Z95 = 1.959963984540054
VOL_MIN = 120
_erf = np.frompyfunc(math.erf, 1, 1)


def phi(z: np.ndarray) -> np.ndarray:
    z = np.asarray(z, float)
    out = np.full(z.shape, np.nan)
    ok = np.isfinite(z)
    out[ok] = 0.5 * (1.0 + _erf(z[ok] / math.sqrt(2.0)).astype(float))
    return out


def model(m: dict, w, coin_idx: int) -> tuple:
    """Rows of the windows of one coin and their model P(YES) at k = 1..n-1 (column 0 and unusable minutes NaN)."""
    js = np.flatnonzero(w.asset == coin_idx)
    n = w.n
    pm = np.full((len(js), n), np.nan)
    o = np.asarray(m['o'], float)
    lr = np.zeros(len(o))
    lr[:-1] = np.log(o[1:] / o[:-1])                       # return of minute i: its open to the next open
    cs = np.concatenate([[0.0], np.cumsum(lr * lr)])
    gcs = np.concatenate([[0], np.cumsum(np.asarray(m['gap']).astype(np.int64))])
    e0 = (w.open_ms[js] - m['t0']) // G.MIN
    for k in range(1, n):
        e = e0 + k
        ok = (e - VOL_MIN >= 0) & (e + 1 <= len(o) - 1) & (e0 >= 0)
        ee = np.where(ok, e, VOL_MIN)
        sig = np.sqrt((cs[ee] - cs[ee - VOL_MIN]) / VOL_MIN)
        ok &= (sig > 0) & ((gcs[ee + 1] - gcs[ee - VOL_MIN]) == 0)      # no gap minute in the volatility window or this minute
        S = o[np.where(ok, e, 0)]
        with np.errstate(divide='ignore', invalid='ignore'):
            z = np.log(S / w.strike[js]) / (sig * math.sqrt(n - k))
        pm[:, k] = np.where(ok, phi(z), np.nan)
    return js, pm


def _logit(p):
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def fit_logistic(X: np.ndarray, y: np.ndarray, iters: int = 30, ridge: float = 1e-6) -> np.ndarray:
    A = np.column_stack([np.ones(len(X)), X])
    b = np.zeros(A.shape[1])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-A @ b))
        g = A.T @ (y - p) - ridge * b
        H = (A * (p * (1 - p))[:, None]).T @ A + ridge * np.eye(len(b))
        step = np.linalg.solve(H, g)
        b = b + step
        if np.abs(step).max() < 1e-9:
            break
    return b


def logloss(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean())


def information(w, pm_by_row: np.ndarray, split_ms: int, kmin: int, kmax: int) -> dict:
    """Quote alone against quote + model on the later part, for windows and minutes k in [kmin, kmax], one row per window and minute."""
    mid = 0.5 * (w.bid + w.ask)
    rows = []
    for k in range(kmin, kmax + 1):
        ok = np.isfinite(pm_by_row[:, k]) & np.isfinite(mid[:, k]) & (w.ask[:, k] > w.bid[:, k])
        j = np.flatnonzero(ok)
        rows.append((j, np.full(len(j), k)))
    j = np.concatenate([r[0] for r in rows])
    k = np.concatenate([r[1] for r in rows])
    if len(j) < 200:
        return {'n': int(len(j))}
    y = w.settle[j]
    xq, xm = _logit(mid[j, k]), _logit(pm_by_row[j, k])
    tr = w.open_ms[j] < split_ms
    te = ~tr
    if tr.sum() < 100 or te.sum() < 100:
        return {'n': int(len(j)), 'train': int(tr.sum()), 'test': int(te.sum())}
    b1 = fit_logistic(xq[tr, None], y[tr])
    b2 = fit_logistic(np.column_stack([xq[tr], xm[tr]]), y[tr])
    p_quote = 1 / (1 + np.exp(-(b1[0] + b1[1] * xq[te])))
    p_both = 1 / (1 + np.exp(-(b2[0] + b2[1] * xq[te] + b2[2] * xm[te])))
    return {'n': int(len(j)), 'train': int(tr.sum()), 'test': int(te.sum()), 'k': [kmin, kmax],
            'logloss_mid_raw': logloss(mid[j, k][te], y[te]), 'logloss_model_raw': logloss(pm_by_row[j, k][te], y[te]),
            'logloss_quote_fit': logloss(p_quote, y[te]), 'logloss_quote_and_model': logloss(p_both, y[te]),
            'coef_quote_only': [float(x) for x in b1], 'coef_both': [float(x) for x in b2]}


def _cluster(x: np.ndarray, day: np.ndarray) -> tuple:
    N = len(x)
    if N == 0:
        return None, None, 0
    mean = x.mean()
    ds = np.unique(day)
    if len(ds) < 2:
        return float(mean), None, len(ds)
    s = np.array([x[day == d].sum() for d in ds])
    n = np.array([(day == d).sum() for d in ds], float)
    res = s - mean * n
    return float(mean), float(np.sqrt((res * res).sum() * len(ds) / (len(ds) - 1)) / N), len(ds)


def trade(w, pm: np.ndarray, kmin: int, kmax: int, edge: float) -> dict:
    """One trade per window: the first minute k in [kmin, kmax] where the model's edge over the ask of its better side is at least `edge`. Returns per trade
    arrays: window row, minute, side (+1 YES), price, win, net dollars per contract."""
    W = len(pm)
    jj, kk, sd, pr, win = [], [], [], [], []
    for j in range(W):
        for k in range(kmin, kmax + 1):
            p = pm[j, k]
            b, a = w.bid[j, k], w.ask[j, k]
            if not (np.isfinite(p) and np.isfinite(b) and np.isfinite(a)) or not 0 < b < a < 1:
                continue
            ey, en = p - a, b - p                              # edge of buying YES at the ask, of buying NO at 1 - bid
            if max(ey, en) >= edge:
                up = ey >= en
                jj.append(j); kk.append(k); sd.append(1 if up else -1); pr.append(a if up else 1 - b)
                win.append(float(w.settle[j] == (1.0 if up else 0.0)))
                break
    pr, win = np.array(pr), np.array(win)
    if not len(pr):
        return {'j': np.array([], int), 'k': np.array([], int), 'side': np.array([], int), 'p': pr, 'win': win, 'net': np.array([])}
    cnt = np.maximum(np.floor(STAKE / pr), 1.0)
    fee = KF.taker_fee(cnt, pr) / cnt
    return {'j': np.array(jj), 'k': np.array(kk), 'side': np.array(sd), 'p': pr, 'win': win, 'net': win - pr - fee}


def summarize(day: np.ndarray, t: dict) -> dict:
    n = len(t['net'])
    out = {'trades': int(n)}
    if not n:
        return out
    mean, se, nd = _cluster(t['net'], day)
    out.update({'hit': float(t['win'].mean()), 'price': float(t['p'].mean()), 'net_c': round(100 * mean, 3), 'days': nd,
                'net_lo_c': None if se is None else round(100 * (mean - Z95 * se), 3),
                'net_hi_c': None if se is None else round(100 * (mean + Z95 * se), 3)})
    return out


def sweep(w, pms: dict, periods: dict, ranges, edges) -> dict:
    """Net cents per contract for every (minute range, edge) cell, by period (name -> (start ms, end ms)), both coins pooled."""
    out = {}
    for (kmin, kmax) in ranges:
        for edge in edges:
            cell = {}
            allj, allt = [], []
            for c, (js, pm) in pms.items():
                t = trade(w, pm, kmin, kmax, edge)
                allj.append(js[t['j']] if len(t['j']) else np.array([], int))
                allt.append(t)
            jall = np.concatenate(allj)
            tall = {k: np.concatenate([t[k] for t in allt]) for k in ('side', 'p', 'win', 'net')}
            day = (w.open_ms[jall] // G.DAY).astype(np.int64) if len(jall) else np.array([], np.int64)
            for name, (a, b) in periods.items():
                sel = (w.open_ms[jall] >= a) & (w.open_ms[jall] < b) if len(jall) else np.array([], bool)
                cell[name] = summarize(day[sel], {k: v[sel] for k, v in tall.items()})
            out[f'k{kmin}-{kmax}_edge{edge:.2f}'] = cell
    return out


def model_all(grids: dict, w) -> tuple:
    """The model's P(YES) for every window of every coin: the (W, n) matrix and the per-coin (rows, matrix) pairs."""
    full = np.full((len(w), w.n), np.nan)
    per = {}
    for i, c in enumerate(w.assets):
        if c not in grids:
            continue
        js, pm = model(grids[c], w, i)
        full[js] = pm
        per[c] = (js, pm)
    return full, per


def run(grids: dict, w, split_ms: int, periods: dict, ranges=((1, 4), (5, 9), (10, 13)), edges=(0.03, 0.06, 0.10)) -> dict:
    full, per = model_all(grids, w)
    res = {'windows': int(len(w)), 'modelled_cells': int(np.isfinite(full).sum()), 'information': {}, 'trading': sweep(w, per, periods, ranges, edges)}
    for (a, b) in ranges:
        res['information'][f'k{a}-{b}'] = information(w, full, split_ms, a, b)
    return res
