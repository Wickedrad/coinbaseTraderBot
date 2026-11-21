"""Does ANY spot feature add to Kalshi's own quote? (Steven, Nov 21 2026: recorded days only.)

The quote at decision minute k already prices the coin's move so far (kfair.py: a model of spot against strike adds nothing to it). This module asks the
general question: take everything the 1-minute grids know at that minute (the coin's own returns over 1 to 60 minutes in volatility units, taker-flow
imbalance, volume, the other coin's returns, time of day) and let a boosted model learn only the RESIDUAL of the quote (the quote's logit is the starting
score), fitted on the build days, early-stopped on the last quarter of them, and judged on the check days and the clean days:

  log-loss of the quote alone   against   log-loss of quote + learned residual.

If the residual does not lower the log-loss on days it never saw, nothing the grids hold is worth more than the quote and no price-direction rule can pay
after fees. If it does, the same residual is traded against the ask and scored in net cents per contract. Also here: the realized win rate by price bucket
(favourites and longshots) with the taker fee, no model at all.
"""
import math

import numpy as np

from allpairs import fees as KF
from dirsweep import grid as G
from dirsweep import kfair as KFAIR

STAKE = 10.0
Z95 = 1.959963984540054
RETS = (1, 3, 5, 15, 30, 60)
NAMES = (['k', 'logit_mid', 'spread', 'z_since_open'] + [f'ret{n}' for n in RETS] + ['ti15', 'ti30', 'volz30'] +
         ['o_ret1', 'o_ret5', 'o_ret15', 'o_z_since_open', 'hour_sin', 'hour_cos'])


def _cum(x):
    return np.concatenate([[0.0], np.cumsum(x, dtype=np.float64)])


class Series:
    """Cumulative sums of one coin's grid, shared by every feature."""
    def __init__(self, m: dict):
        self.m = m
        self.o = np.asarray(m['o'], float)
        lr = np.zeros(len(self.o))
        lr[:-1] = np.log(self.o[1:] / self.o[:-1])
        self.cs = _cum(lr * lr)
        self.v = _cum(np.asarray(m['v'], float))
        self.tb = _cum(np.asarray(m['tb'], float))
        self.gcs = np.concatenate([[0], np.cumsum(np.asarray(m['gap']).astype(np.int64))])
        self.n = len(self.o)

    def sigma(self, e):
        return np.sqrt((self.cs[e] - self.cs[e - KFAIR.VOL_MIN]) / KFAIR.VOL_MIN)

    def ret(self, e, n):
        return np.log(self.o[e] / self.o[e - n]) / (self.sigma(e) * math.sqrt(n))

    def ti(self, e, n):
        v = self.v[e] - self.v[e - n]
        with np.errstate(divide='ignore', invalid='ignore'):
            return (self.tb[e] - self.tb[e - n]) / v - 0.5

    def volz(self, e, n=30):
        mean = (self.v[e] - self.v[e - 1440]) / 1440
        with np.errstate(divide='ignore', invalid='ignore'):
            return np.log((self.v[e] - self.v[e - n]) / (n * mean))


def rows(grids: dict, w, ks) -> dict:
    """One row per (window, decision minute k): features known at that minute, the quote, the outcome."""
    S = {c: Series(m) for c, m in grids.items()}
    t0 = {m['t0'] for m in grids.values()}
    if len(t0) != 1 or len({s.n for s in S.values()}) != 1:
        raise ValueError('the coins need the same minute grid')
    t0 = t0.pop()
    out = {k: [] for k in ('j', 'k', 'y', 'bid', 'ask', 'X')}
    coins = list(grids)
    for ci, c in enumerate(w.assets):
        if c not in grids or len(coins) < 2:
            continue
        o_c = [x for x in coins if x != c][0]
        s, so = S[c], S[o_c]
        js = np.flatnonzero(w.asset == ci)
        e0 = (w.open_ms[js] - t0) // G.MIN
        for k in ks:
            e = e0 + k
            ok = (e - 1440 >= 0) & (e + 1 < s.n) & (e0 >= 0)
            ee = np.where(ok, e, 1440)
            bid, ask = w.bid[js, k], w.ask[js, k]
            ok &= np.isfinite(bid) & np.isfinite(ask) & (bid > 0) & (ask < 1) & (bid < ask)
            ok &= (s.gcs[ee + 1] - s.gcs[ee - 1440] == 0) & (so.gcs[ee + 1] - so.gcs[ee - 1440] == 0)
            if not ok.any():
                continue
            e, e0k, jk = ee[ok], np.where(ok, e0, 0)[ok], js[ok]
            mid = np.clip(0.5 * (bid[ok] + ask[ok]), 1e-3, 1 - 1e-3)
            hr = ((w.open_ms[jk] // G.MIN) % 1440 + k) / 1440.0 * 2 * math.pi
            cols = [np.full(len(e), float(k)), np.log(mid / (1 - mid)), ask[ok] - bid[ok],
                    np.log(s.o[e] / s.o[e0k]) / (s.sigma(e) * math.sqrt(k))]
            cols += [s.ret(e, n) for n in RETS]
            cols += [s.ti(e, 15), s.ti(e, 30), s.volz(e)]
            cols += [so.ret(e, 1), so.ret(e, 5), so.ret(e, 15), np.log(so.o[e] / so.o[e0k]) / (so.sigma(e) * math.sqrt(k)), np.sin(hr), np.cos(hr)]
            X = np.column_stack(cols)
            good = np.isfinite(X).all(1)
            out['j'].append(jk[good]); out['k'].append(np.full(good.sum(), k)); out['y'].append(w.settle[jk][good])
            out['bid'].append(bid[ok][good]); out['ask'].append(ask[ok][good]); out['X'].append(X[good])
    return {k: np.concatenate(v) for k, v in out.items()}


def fit(R: dict, w, split_ms: int, rounds: int = 600, seed: int = 7) -> dict:
    """Boosted residual of the quote's logit, fitted on build rows (last quarter of them in time for early stopping), predicted on every row."""
    import lightgbm as lgb
    t = w.open_ms[R['j']]
    build = t < split_ms
    order = np.argsort(t[build], kind='stable')
    bi = np.flatnonzero(build)[order]
    cut = int(len(bi) * 0.75)
    tr, va = bi[:cut], bi[cut:]
    base = R['X'][:, NAMES.index('logit_mid')]
    prm = {'objective': 'binary', 'learning_rate': 0.03, 'num_leaves': 15, 'min_data_in_leaf': 400, 'feature_fraction': 0.8, 'bagging_fraction': 0.8,
           'bagging_freq': 1, 'lambda_l2': 10.0, 'verbose': -1, 'seed': seed, 'num_threads': 2}
    X = R['X'][:, [i for i, nme in enumerate(NAMES) if nme != 'logit_mid']]
    dtr = lgb.Dataset(X[tr], R['y'][tr], init_score=base[tr])
    dva = lgb.Dataset(X[va], R['y'][va], init_score=base[va], reference=dtr)
    bst = lgb.train(prm, dtr, rounds, valid_sets=[dva], callbacks=[lgb.early_stopping(40, verbose=False)])
    raw = bst.predict(X, raw_score=True, num_iteration=bst.best_iteration)
    p = 1 / (1 + np.exp(-(base + raw)))
    names = [nme for nme in NAMES if nme != 'logit_mid']
    gain = bst.feature_importance('gain')
    top = sorted(zip(names, gain / max(gain.sum(), 1e-9)), key=lambda x: -x[1])[:8]
    return {'p': p, 'rounds': int(bst.best_iteration or 0), 'top_gain': [(n, round(float(g), 4)) for n, g in top]}


def judge(R: dict, w, p: np.ndarray, periods: dict, edges=(0.03, 0.06, 0.10)) -> dict:
    """Log-loss of the quote against the quote plus residual, and the residual traded against the ask, per period; plus the same by minute."""
    mid = np.clip(0.5 * (R['bid'] + R['ask']), 1e-3, 1 - 1e-3)
    t = w.open_ms[R['j']]
    res = {}
    for name, (a, b) in periods.items():
        s = (t >= a) & (t < b)
        if not s.any():
            continue
        cell = {'rows': int(s.sum()), 'logloss_quote': KFAIR.logloss(mid[s], R['y'][s]), 'logloss_quote_plus_residual': KFAIR.logloss(p[s], R['y'][s])}
        cell['by_k'] = {int(k): [round(KFAIR.logloss(mid[s & (R['k'] == k)], R['y'][s & (R['k'] == k)]), 5),
                                 round(KFAIR.logloss(p[s & (R['k'] == k)], R['y'][s & (R['k'] == k)]), 5)] for k in np.unique(R['k'][s])}
        for e in edges:
            tr = _trade(R, w, p, s, e)
            cell[f'trade_edge{e:.2f}'] = _summ(tr)
        res[name] = cell
    return res


def _trade(R, w, p, sel, edge) -> dict:
    """One trade per window: the earliest k whose predicted probability beats the ask of a side by `edge`."""
    idx = np.flatnonzero(sel)
    order = idx[np.lexsort((R['k'][idx], R['j'][idx]))]
    seen, jj, pr, win, up_l = set(), [], [], [], []
    for i in order:
        j = int(R['j'][i])
        if j in seen:
            continue
        ey, en = p[i] - R['ask'][i], R['bid'][i] - p[i]
        if max(ey, en) < edge:
            continue
        up = ey >= en
        seen.add(j)
        jj.append(j); up_l.append(up); pr.append(R['ask'][i] if up else 1 - R['bid'][i]); win.append(float(R['y'][i] == (1.0 if up else 0.0)))
    pr, win = np.array(pr), np.array(win)
    if not len(pr):
        return {'net': np.array([]), 'p': pr, 'win': win, 'day': np.array([], np.int64)}
    cnt = np.maximum(np.floor(STAKE / pr), 1.0)
    return {'net': win - pr - KF.taker_fee(cnt, pr) / cnt, 'p': pr, 'win': win, 'day': (w.open_ms[np.array(jj)] // G.DAY).astype(np.int64)}


def _summ(t) -> dict:
    n = len(t['net'])
    if not n:
        return {'trades': 0}
    mean, se, nd = KFAIR._cluster(t['net'], t['day'])
    return {'trades': int(n), 'hit': round(float(t['win'].mean()), 4), 'price': round(float(t['p'].mean()), 4), 'net_c': round(100 * mean, 3),
            'net_lo_c': None if se is None else round(100 * (mean - Z95 * se), 3), 'net_hi_c': None if se is None else round(100 * (mean + Z95 * se), 3), 'days': nd}


def price_atlas(w, periods: dict, ranges=((1, 4), (5, 9), (10, 13)), edges=(0.02, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 0.98)) -> dict:
    """No model: buy a side at its ask when the ask is in a price bucket, first qualifying minute of the range, hold to settlement, pay the taker fee."""
    out = {}
    t = w.open_ms
    for (a, b) in ranges:
        for side in ('yes', 'no'):
            for lo, hi in zip(edges[:-1], edges[1:]):
                jj, pr, win = [], [], []
                for j in range(len(w)):
                    for k in range(a, b + 1):
                        bd, ak = w.bid[j, k], w.ask[j, k]
                        if not (np.isfinite(bd) and np.isfinite(ak)) or not 0 < bd < ak < 1:
                            continue
                        p = ak if side == 'yes' else 1 - bd
                        if lo <= p < hi:
                            jj.append(j); pr.append(p); win.append(float(w.settle[j] == (1.0 if side == 'yes' else 0.0)))
                            break
                jj, pr, win = np.array(jj, int), np.array(pr), np.array(win)
                cell = {}
                for name, (t0, t1) in periods.items():
                    s = (t[jj] >= t0) & (t[jj] < t1) if len(jj) else np.array([], bool)
                    if not s.any():
                        continue
                    cnt = np.maximum(np.floor(STAKE / pr[s]), 1.0)
                    net = win[s] - pr[s] - KF.taker_fee(cnt, pr[s]) / cnt
                    cell[name] = _summ({'net': net, 'p': pr[s], 'win': win[s], 'day': (t[jj[s]] // G.DAY).astype(np.int64)})
                out[f'k{a}-{b}_{side}_{lo:.2f}-{hi:.2f}'] = cell
    return out
