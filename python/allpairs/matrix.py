"""The upper-triangular all-pairs payoff matrix P[i, j]: enter at minute i, exit at minute j > i (or settle at j = N).

Each cell is the position's net P&L in dollars for a stake-sized order (C whole contracts, the bot's order band),
with Kalshi's real fee on every fill (fees.py, the exact port of bot/fees.ts): a taker entry pays the ask plus the
taker fee, a taker exit gets the bid minus the taker fee, settlement pays $1 or $0 with no fee. Maker legs rest at
the bid (entry) or the ask (exit) and fill only when the next minute's candle shows the book traded through that
price (fill rules below); their fee is the maker fee (multiplier 0 for the crypto series, 1 in the stress arm).

Maker fill from 1-minute candles. The recorded book never held our order, so a quote moving away from our price is no
evidence (the makers ahead of us may simply have cancelled, and we would still be resting). Only the OTHER side
reaching our price is: a buy resting at bid b fills in (t_k, t_k+1] when the next minute's lowest ask is <= b (a
seller offered at our price or below; with our bid there, that order would have traded with it), a sell resting at
ask a when the next minute's highest bid is >= a. `strict` asks for a cent more (the other side crossed THROUGH our
price), which also covers a queue of other orders ahead of ours at the same price.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .fees import contracts_for_stake, maker_fee, taker_fee

TICK = 0.01
EPS = 1e-9


@dataclass
class Costs:
    stake: float = 15.0          # dollars per order (the middle of the $10-$20 band)
    slip: float = 0.0            # extra dollars per contract paid on every taker leg (stress: 0.01)
    taker_mult: float = 1.0
    maker_mult: float = 0.0      # crypto series pay no maker fee; stress charges 1 (0.0175 x P(1-P))
    strict_maker: bool = False   # maker fills need the price traded through by a tick
    precision: float = 0.01      # the account's balance grid: 0.01 through an FCM (the bot's default), 0.0001 direct


def maker_fills(bid, ask, nbl, nbh, nal, nah, strict: bool):
    """(fill_buy, fill_sell) for orders resting at the side's bid / ask at t_k, filled in (t_k, t_k+1]."""
    with np.errstate(invalid='ignore'):
        through = TICK if strict else 0.0
        fb = nal <= bid - through + EPS
        fs = nbh >= ask + through - EPS
    fb &= np.isfinite(bid)
    fs &= np.isfinite(ask)
    return fb, fs


def entry_legs(bid, ask, fill_buy, c: Costs):
    """Per-contract entry cost (fee in) and contract count for taker (at the ask) and maker (at the bid) entries.
    Returns (cost_T, C_T, cost_M, C_M, ok_T, ok_M); maker entries are ok only where they filled."""
    pa = ask + c.slip
    ok_T = np.isfinite(ask) & (pa < 1)
    C_T = contracts_for_stake(c.stake, np.where(ok_T, pa, np.nan))
    cost_T = np.where(ok_T, pa + taker_fee(C_T, np.where(ok_T, pa, 0.5), c.taker_mult, c.precision) / np.maximum(C_T, 1), np.nan)
    ok_M = np.isfinite(bid) & (bid > 0) & fill_buy
    C_M = contracts_for_stake(c.stake, np.where(ok_M, bid, np.nan))
    cost_M = np.where(ok_M, bid + maker_fee(C_M, np.where(ok_M, bid, 0.5), c.maker_mult, c.precision) / np.maximum(C_M, 1), np.nan)
    return cost_T, C_T, cost_M, C_M, ok_T, ok_M


def exit_taker(bid, C, c: Costs):
    """Per-contract proceeds of a taker sale at the bid for a C-contract position (NaN where there is no bid)."""
    pb = bid - c.slip
    ok = np.isfinite(pb) & (pb > 0)
    Cs = np.where(ok, C, 0)
    fee = taker_fee(Cs, np.where(ok, pb, 0.5), c.taker_mult, c.precision) / np.maximum(C, 1)
    return np.where(ok, pb - fee, np.nan)


def exit_maker(ask, C, c: Costs):
    """Per-contract proceeds of a maker sale resting at the ask (valid only where it fills)."""
    ok = np.isfinite(ask) & (ask < 1)
    Cs = np.where(ok, C, 0)
    fee = maker_fee(Cs, np.where(ok, ask, 0.5), c.maker_mult, c.precision) / np.maximum(C, 1)
    return np.where(ok, ask - fee, np.nan)


def compute_all_pairs_pnl_matrix(ask_prices: np.ndarray, bid_prices: np.ndarray, settlement: float, costs: Costs | None = None,
                                 next_bid_lo=None, next_bid_hi=None, next_ask_lo=None, next_ask_hi=None) -> dict[str, np.ndarray]:
    """Steven's blueprint for one window, with the real fees: net P&L in dollars of entering at minute i and exiting
    at minute j > i, column N = holding to settlement. Returns {'TT': taker in / taker out, 'MT': maker in / taker
    out, 'TM': taker in / maker out, 'MM'} as (N, N + 1) arrays, NaN where the pair is impossible (j <= i, no quote,
    a maker leg that did not fill). Column N is the same settlement payoff for every exit kind."""
    c = costs or Costs()
    a = np.asarray(ask_prices, dtype=np.float64)[None, None, :]
    b = np.asarray(bid_prices, dtype=np.float64)[None, None, :]
    s = np.array([[float(settlement)]])
    nx = lambda v, d: d if v is None else np.asarray(v, dtype=np.float64)[None, None, :]
    P = all_pairs(b, a, nx(next_bid_lo, b), nx(next_bid_hi, b), nx(next_ask_lo, a), nx(next_ask_hi, a), s, c)
    return {k: v[0, 0] for k, v in P.items()}


def all_pairs(bid, ask, nbl, nbh, nal, nah, settle, c: Costs) -> dict[str, np.ndarray]:
    """Batched matrices for side arrays (W, S, N) and settle (W, S): {'TT','MT','TM','MM'} -> (W, S, N, N + 1)."""
    W, S, N = bid.shape
    fb, fs = maker_fills(bid, ask, nbl, nbh, nal, nah, c.strict_maker)
    cost_T, C_T, cost_M, C_M, ok_T, ok_M = entry_legs(bid, ask, fb, c)
    j = np.arange(N + 1)
    upper = j[None, :] > np.arange(N)[:, None]                       # (N, N+1): j > i
    out = {}
    for ein, cost, C in (('T', cost_T, C_T), ('M', cost_M, C_M)):
        Ci = C[..., :, None]                                          # (W,S,N,1)
        bj = np.broadcast_to(bid[..., None, :], (W, S, N, N))
        aj = np.broadcast_to(ask[..., None, :], (W, S, N, N))
        Cb = np.broadcast_to(Ci, (W, S, N, N))
        xt = exit_taker(bj, Cb, c)
        xm = np.where(np.broadcast_to(fs[..., None, :], (W, S, N, N)), exit_maker(aj, Cb, c), np.nan)
        for eout, x in (('T', xt), ('M', xm)):
            per = np.concatenate([x, np.broadcast_to(settle[..., None, None], (W, S, N, 1))], axis=-1)  # (W,S,N,N+1)
            P = Ci * (per - cost[..., :, None])
            out[ein + eout] = np.where(upper, P, np.nan)
    return out
