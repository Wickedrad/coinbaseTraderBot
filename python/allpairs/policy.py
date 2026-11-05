"""Entry labels, the entry model and the trading simulation that scores a policy in dollars per hour.

The entry label of (window, side, minute i, mode) is the realized P&L of entering there and then FOLLOWING THE EXIT
POLICY (snell.py), never the best exit in hindsight: max over j labels minutes as good because one later minute
spiked, and the entry model would learn to buy noise the exit logic can never time. A maker entry that did not fill
is labelled 0 (no position).

The simulation walks each window minute by minute: the first minute whose best predicted (side, mode) clears the
hurdle opens the position (one per window); a maker attempt that does not fill leaves the window open for later
minutes. $/h is total P&L over the hours of the test span (every asset's windows together).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .snell import Positions


@dataclass
class EntryConfig:
    hurdles: tuple = (0.0, 0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 1e9)   # dollars per position to clear (1e9 = no trading)
    rows_per_fit: int = 1_500_000
    seed: int = 11
    lgb_params: dict = field(default_factory=lambda: dict(n_estimators=300, learning_rate=0.03, num_leaves=31, min_child_samples=400,
                                                          subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=5.0))


def entry_rows(X: np.ndarray, pos: Positions, pnl: np.ndarray, attempts: tuple | None = None):
    """Rows of the entry dataset. Taker rows are the taker positions; maker rows are every maker ATTEMPT (filled or not:
    `attempts` = (w, s, i) of every posted maker entry), labelled with the filled position's P&L or 0."""
    tk = pos.mode == 0
    w, s, i, y = pos.w[tk], pos.s[tk], pos.i[tk], pnl[tk]
    mode = np.zeros(len(w), dtype=np.int8)
    filled = np.ones(len(w), dtype=bool)
    if attempts is not None:
        aw, as_, ai = attempts
        key = lambda W_, S_, I_: (W_.astype(np.int64) * 2 + S_) * 256 + I_
        mk = pos.mode == 1
        filled_pnl = dict(zip(key(pos.w[mk], pos.s[mk], pos.i[mk]).tolist(), pnl[mk].tolist()))
        ak = key(aw, as_, ai).tolist()
        ay = np.array([filled_pnl.get(k_, 0.0) for k_ in ak])
        af = np.array([k_ in filled_pnl for k_ in ak], dtype=bool)
        filled = np.concatenate([filled, af])
        w = np.concatenate([w, aw]); s = np.concatenate([s, as_]); i = np.concatenate([i, ai]); y = np.concatenate([y, ay])
        mode = np.concatenate([mode, np.ones(len(aw), dtype=np.int8)])
    feats = np.concatenate([X[w, s, i, :], mode[:, None].astype(np.float32)], axis=1)
    return dict(w=w.astype(np.int32), s=s.astype(np.int8), i=i.astype(np.int16), mode=mode, X=feats, y=y, filled=filled)


def maker_attempts(book_bid: np.ndarray, n_entry: int):
    """Every (w, s, i) where a maker entry could be posted (a bid to join), i < n_entry."""
    ok = np.isfinite(book_bid[..., :n_entry]) & (book_bid[..., :n_entry] > 0)
    return np.nonzero(ok)


def fit_entry(rows: dict, cfg: EntryConfig, shuffle_rng: np.random.Generator | None = None, day_of_w: np.ndarray | None = None):
    """LightGBM regressor of the label on the entry features. With shuffle_rng the labels are permuted across rows
    (within each mode) first: the placebo that keeps every label's distribution and destroys what the features say."""
    from .gbm import fit_gbm
    X, y = rows['X'], rows['y'].copy()
    if shuffle_rng is not None:
        for m in (0, 1):
            sel = np.nonzero(rows['mode'] == m)[0]
            y[sel] = y[shuffle_rng.permutation(sel)]
    rng = np.random.default_rng(cfg.seed)
    if len(y) > cfg.rows_per_fit:
        sel = rng.choice(len(y), cfg.rows_per_fit, replace=False)
        X, y = X[sel], y[sel]
    return fit_gbm(X, y, cfg.lgb_params, cfg.seed)


def simulate(rows: dict, pred: np.ndarray, hurdle: float, entry_minutes: np.ndarray | None = None):
    """One position per window: the earliest minute whose best (side, mode) prediction clears the hurdle; a maker
    attempt that does not fill (label exactly 0 with mode 1 and no filled position) lets the window go on.
    Returns the chosen row indices (filled positions only)."""
    ok = pred > hurdle
    if entry_minutes is not None:
        ok &= np.isin(rows['i'], entry_minutes)
    idx = np.nonzero(ok)[0]
    if not len(idx):
        return idx
    # Order by window, minute, then best prediction first.
    order = np.lexsort((-pred[idx], rows['i'][idx], rows['w'][idx]))
    idx = idx[order]
    w = rows['w'][idx]
    i = rows['i'][idx]
    filled = rows.get('filled')
    if filled is None:
        filled = np.ones(len(rows['y']), dtype=bool)
    chosen = []
    cur_w = -1
    done = False
    last_i = -1
    for j, (ww, ii) in enumerate(zip(w.tolist(), i.tolist())):
        if ww != cur_w:
            cur_w, done, last_i = ww, False, -1
        if done or ii == last_i:
            continue   # one decision per minute: the best prediction of that minute
        last_i = ii
        r = idx[j]
        if filled[r]:
            chosen.append(r)
            done = True
    return np.array(chosen, dtype=np.int64)


def pnl_stats(pnl: np.ndarray, hours: float, hour_of_trade: np.ndarray | None = None, n_hours: int | None = None) -> dict:
    tot = float(np.sum(pnl)) if len(pnl) else 0.0
    out = dict(trades=int(len(pnl)), pnl=round(tot, 2), per_hour=round(tot / hours, 3) if hours else 0.0,
               avg=round(float(np.mean(pnl)), 3) if len(pnl) else 0.0, win=round(float(np.mean(pnl > 0)), 3) if len(pnl) else 0.0)
    if hour_of_trade is not None and n_hours:
        series = np.bincount(hour_of_trade, weights=pnl, minlength=n_hours)[:n_hours]
        sd = float(np.std(series, ddof=1)) if n_hours > 1 else 0.0
        out['sr_hourly'] = round(float(np.mean(series)) / sd, 4) if sd > 0 else 0.0
    return out


def random_entry_placebo(rows: dict, n_trades_per_window: float, rng, draws: int = 50, n_windows: int | None = None):
    """Random entries at the model's trade rate: per draw, the same number of positions spread over random windows,
    each at a random minute/side/mode among that window's filled rows. Returns per-draw total P&L."""
    filled = rows.get('filled', np.ones(len(rows['y']), dtype=bool))
    cand = np.nonzero(filled)[0]
    cand = cand[np.argsort(rows['w'][cand], kind='stable')]
    if not len(cand):
        return np.zeros(draws)
    ws = rows['w'][cand]
    uniq, start = np.unique(ws, return_index=True)
    ends = np.append(start[1:], len(ws))
    nw = len(uniq)
    k = int(round(n_trades_per_window * (n_windows or nw)))
    k = min(k, nw)
    out = np.zeros(draws)
    for d in range(draws):
        pick = rng.choice(nw, k, replace=False)
        j = start[pick] + (rng.random(k) * (ends[pick] - start[pick])).astype(np.int64)
        out[d] = rows['y'][cand[j]].sum()
    return out
