"""Exit policy by backward induction (Snell envelope, Longstaff-Schwartz), and the realistic labels it produces.

A position (window w, side s, entry minute i, entry mode taker/maker) is first free to exit at k0 = i + 1. Working
backward from expiry, at each decision minute k = N-1 .. 1 every open position has up to three actions:
    T  sell now at the bid (taker): known value a_T(k)
    M  rest a sell at the ask (maker): a_M(k) if the next minute fills it, else the position carries on
    H  hold to k + 1
The value of carrying on is not known at k, so it is ESTIMATED from what is known at k (the market features X_k, the
side, minutes left, the unrealized P&L and the entry cost) by a regression of the realized value-to-go under the
policy already fixed for later minutes (LightGBM, cross-fitted: a model never scores the days it was fitted on).
The action with the highest value (a_T exact, M and H estimated) is taken, and the realized value-to-go becomes the
target one step earlier. The perfect-hindsight envelope (the max of the realized values: what "max over j" gives) is
computed beside it as an upper bound for the report only; it never labels anything.

Steven's settlement rule (Oct 29, every contract type): never hold to settlement unless less than 10% of the window
is left AND the position is in profit after fees. So at the last decision a position that is not in profit is sold
(taker; a resting maker sale could miss and settle). end_rule='bot' mirrors the bot's implementation
(STRATEGY_NO_EXIT_BEFORE_CLOSE_FRAC: in the last 10% a position in profit after fees rides to settlement, no sale);
end_rule='allow' lets the policy choose between selling and riding there.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .matrix import Costs, entry_legs, exit_maker, exit_taker, maker_fills

T_, M_, H_, S_ = 0, 1, 2, 3   # exit kinds: taker sale, maker sale, (hold), settled


@dataclass
class Book:
    """Side-transformed quotes and maker fills of a set of windows: arrays (W, 2, N); settle (W, 2)."""
    bid: np.ndarray
    ask: np.ndarray
    fill_buy: np.ndarray
    fill_sell: np.ndarray
    settle: np.ndarray

    @property
    def n(self) -> int:
        return self.bid.shape[2]

    @staticmethod
    def build(bid, ask, nbl, nbh, nal, nah, settle, costs: Costs) -> 'Book':
        fb, fs = maker_fills(bid, ask, nbl, nbh, nal, nah, costs.strict_maker)
        return Book(bid, ask, fb, fs, settle)


@dataclass
class Positions:
    w: np.ndarray       # window index
    s: np.ndarray       # side 0 YES / 1 NO
    i: np.ndarray       # entry minute
    mode: np.ndarray    # 0 taker / 1 maker entry
    C: np.ndarray       # contracts
    cost: np.ndarray    # per-contract cost, entry fee in

    def __len__(self) -> int:
        return len(self.w)

    @property
    def k0(self) -> np.ndarray:
        return self.i + 1


def build_positions(book: Book, costs: Costs, maker_entries: bool = True, entry_minutes: np.ndarray | None = None) -> Positions:
    """Every possible position: each window x side x entry minute (0..N-2) x entry mode that can fill."""
    W, S, N = book.bid.shape
    cost_T, C_T, cost_M, C_M, ok_T, ok_M = entry_legs(book.bid, book.ask, book.fill_buy, costs)
    allowed = np.zeros(N, dtype=bool)
    allowed[: N - 1] = True
    if entry_minutes is not None:
        allowed &= np.isin(np.arange(N), entry_minutes)
    parts = []
    for mode, ok, C, cost in ((0, ok_T, C_T, cost_T), (1, ok_M, C_M, cost_M)):
        if mode == 1 and not maker_entries:
            continue
        m = ok & allowed[None, None, :]
        w, s, i = np.nonzero(m)
        parts.append((w, s, i, np.full(len(w), mode, dtype=np.int8), C[w, s, i], cost[w, s, i]))
    cat = lambda j, dt: np.concatenate([p[j] for p in parts]).astype(dt)
    return Positions(cat(0, np.int32), cat(1, np.int8), cat(2, np.int16), cat(3, np.int8), cat(4, np.float64), cat(5, np.float64))


@dataclass
class ExitConfig:
    end_rule: str = 'bot'         # 'bot' | 'allow'
    end_frac: float = 0.10
    maker_exits: bool = True
    rows_per_fit: int = 200_000
    seed: int = 7
    lgb_params: dict = field(default_factory=lambda: dict(n_estimators=150, learning_rate=0.05, num_leaves=31, min_child_samples=200,
                                                          subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=1.0))


@dataclass
class ExitResult:
    value0: np.ndarray        # per-contract value at the first decision (gross of entry cost)
    exit_k: np.ndarray        # minute the position was sold or settled (N = settled)
    exit_kind: np.ndarray     # T_ / M_ / S_
    oracle0: np.ndarray       # perfect-hindsight per-contract value (report only)
    naive0: np.ndarray        # hold, sold only when the settlement rule forces it
    models: dict              # k -> (hold models, maker models) for reuse on other windows

    def pnl(self, pos: Positions, which: str = 'policy') -> np.ndarray:
        v = {'policy': self.value0, 'oracle': self.oracle0, 'naive': self.naive0}[which]
        return pos.C * (v - pos.cost)


class _Mean:
    def __init__(self, y):
        self.m = float(np.mean(y)) if len(y) else 0.0

    def predict(self, X):
        return np.full(len(X), self.m)


def _fit(X, y, cfg: ExitConfig, rng):
    if len(y) < 500:
        return _Mean(y)
    if len(y) > cfg.rows_per_fit:
        sel = rng.choice(len(y), cfg.rows_per_fit, replace=False)
        X, y = X[sel], y[sel]
    from .gbm import fit_gbm
    return fit_gbm(X, y, cfg.lgb_params, cfg.seed)


def _predict(models, X, chunk=500_000):
    if not len(X):
        return np.zeros(0)
    out = np.zeros(len(X))
    for m in models:
        for a in range(0, len(X), chunk):
            out[a:a + chunk] += m.predict(X[a:a + chunk])
    return out / len(models)


def state_features(X: np.ndarray, pos: Positions, idx: np.ndarray, k: int, aT: np.ndarray) -> np.ndarray:
    """Regression inputs at minute k for positions idx: market features, unrealized P&L, cost, minutes held, mode."""
    base = X[pos.w[idx], pos.s[idx], k, :]
    u = np.where(np.isfinite(aT), aT - pos.cost[idx], np.nan)
    extra = np.stack([u, pos.cost[idx], (k - pos.i[idx]).astype(np.float64), pos.mode[idx].astype(np.float64)], axis=1)
    return np.concatenate([base, extra.astype(np.float32)], axis=1)


STATE_EXTRA = ['unreal', 'entry_cost', 'held_min', 'entry_maker']


def solve_exits(book: Book, X: np.ndarray, pos: Positions, costs: Costs, cfg: ExitConfig, groups: np.ndarray | None = None,
                models: dict | None = None, log=None) -> ExitResult:
    """Backward induction over k = N-1 .. 1. With `models` (from a training set) the policy is applied as fitted;
    otherwise it is fitted here with 2-fold cross-fitting over `groups` (per window, 0/1), each half's decisions made by
    the model fitted on the other half. The returned models are both halves' (averaged when applied elsewhere)."""
    N = book.n
    P = len(pos)
    rng = np.random.default_rng(cfg.seed)
    Y = book.settle[pos.w, pos.s].astype(np.float64)          # realized value-to-go, per contract
    Yo = Y.copy()                                              # perfect hindsight
    Yn = Y.copy()                                              # naive
    exit_k = np.full(P, N, dtype=np.int16)
    exit_kind = np.full(P, S_, dtype=np.int8)
    value0 = np.full(P, np.nan); oracle0 = np.full(P, np.nan); naive0 = np.full(P, np.nan)
    fit_here = models is None
    out_models: dict = {} if fit_here else models
    g = None
    if fit_here:
        g = (groups[pos.w] if groups is not None else (pos.w % 2)).astype(np.int8)
    k0 = pos.k0
    for k in range(N - 1, 0, -1):
        alive = np.nonzero(k0 <= k)[0]
        if not len(alive):
            continue
        w, s = pos.w[alive], pos.s[alive]
        C, cost = pos.C[alive], pos.cost[alive]
        aT = exit_taker(book.bid[w, s, k], C, costs)
        aM = exit_maker(book.ask[w, s, k], C, costs) if cfg.maker_exits else np.full(len(alive), np.nan)
        fill = book.fill_sell[w, s, k]
        has_T = np.isfinite(aT)
        has_M = np.isfinite(aM)
        in_profit = has_T & (aT - cost > 0)
        last10 = (N - k) / N <= cfg.end_frac + 1e-9
        final = k == N - 1
        allow_T = has_T.copy(); allow_M = has_M.copy(); allow_H = np.ones(len(alive), dtype=bool)
        if cfg.end_rule == 'bot' and last10:
            ride = in_profit
            allow_T &= ~ride; allow_M &= ~ride
        if final:
            # Not in profit: never left to settle (a maker sale could miss), sold at the bid if there is one.
            forced = ~in_profit & has_T
            allow_H &= ~forced; allow_M &= ~forced
        Yk1 = Y[alive]
        rM = np.where(fill, aM, Yk1)
        Z = state_features(X, pos, alive, k, aT)
        if fit_here:
            hold_m, mk_m = [], []
            pred_H = np.zeros(len(alive)); pred_M = np.zeros(len(alive))
            for half in (0, 1):
                tr = g[alive] == half
                te = ~tr
                mh = _fit(Z[tr], Yk1[tr], cfg, rng)
                trm = tr & has_M
                mm = _fit(Z[trm], rM[trm], cfg, rng) if cfg.maker_exits else _Mean([])
                hold_m.append(mh); mk_m.append(mm)
                pred_H[te] = mh.predict(Z[te]) if te.any() else 0
                pred_M[te] = mm.predict(Z[te]) if te.any() else 0
            out_models[k] = (hold_m, mk_m)
        else:
            hold_m, mk_m = out_models[k]
            pred_H = _predict(hold_m, Z)
            pred_M = _predict(mk_m, Z) if cfg.maker_exits else np.zeros(len(alive))
        vals = np.stack([np.where(allow_T, aT, -np.inf), np.where(allow_M, pred_M, -np.inf), np.where(allow_H, pred_H, -np.inf)], axis=1)
        act = np.argmax(vals, axis=1)
        none = ~np.isfinite(vals.max(axis=1))   # nothing allowed (no bid, not in profit, final): settles
        act[none] = H_
        newY = Yk1.copy()
        tsel = act == T_
        newY[tsel] = aT[tsel]
        msel = (act == M_) & fill
        newY[msel] = aM[msel]
        Y[alive] = newY
        ek = exit_k[alive]; ekind = exit_kind[alive]
        ek[tsel] = k; ekind[tsel] = T_
        ek[msel] = k; ekind[msel] = M_
        exit_k[alive] = ek; exit_kind[alive] = ekind
        # Perfect hindsight: the best realized value among the allowed actions.
        yo = Yo[alive]
        cand = np.stack([np.where(allow_T, aT, -np.inf), np.where(allow_M & fill, aM, -np.inf), np.where(allow_H | (allow_M & ~fill), yo, -np.inf)], axis=1)
        best = cand.max(axis=1)
        Yo[alive] = np.where(np.isfinite(best), best, yo)
        # Naive: hold; sell only when forced (final minute, not in profit).
        yn = Yn[alive]
        if final:
            yn = np.where(~allow_H & has_T, aT, yn)
        Yn[alive] = yn
        born = alive[k0[alive] == k]
        value0[born] = Y[born]; oracle0[born] = Yo[born]; naive0[born] = Yn[born]
        if log:
            log(f'  k={k}: {len(alive)} open, taker {tsel.mean():.3f} maker {msel.mean():.3f} posted {(act == M_).mean():.3f}')
    return ExitResult(value0, exit_k, exit_kind, oracle0, naive0, out_models)
