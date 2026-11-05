"""Kalshi trading fees, an exact NumPy port of bot/fees.ts (keep the two in step).

    model fee  taker = M_taker * 0.07   * C * P * (1 - P)
               maker = M_maker * 0.0175 * C * P * (1 - P)
    trade fee  = model fee rounded UP to $0.000001
    rounding   = what brings C x P + trade fee back onto the balance grid ($0.01 non-direct members, the default)
    net fee    = trade fee + rounding.  No settlement fee.

Multipliers: taker 1; maker 0 unless the series is in the schedule's non-standard table (the crypto 15-minute and
hourly series are not, so their maker fills pay nothing: bot/kalshi/feeScheduleSnapshot.json). The stress arm charges
makers the full 0.0175 anyway (a cost is never underestimated).
"""
from __future__ import annotations

import numpy as np

TAKER_RATE = 0.07
MAKER_RATE = 0.0175


def _js_round(x):
    """JavaScript Math.round (half up) for the non-negative values used here."""
    return np.floor(np.asarray(x, dtype=np.float64) + 0.5)


def fee_dollars(rate: float, multiplier: float, count, price, precision: float = 0.01) -> np.ndarray:
    """Net fee in dollars for one fill of `count` contracts at side price `price` (broadcasts)."""
    count = np.asarray(count, dtype=np.float64)
    price = np.asarray(price, dtype=np.float64)
    count, price = np.broadcast_arrays(count, price)
    out = np.zeros(count.shape, dtype=np.float64)
    if not multiplier > 0:
        return out
    ok = (count > 0) & (price > 0) & (price < 1) & np.isfinite(price)
    if not ok.any():
        return out
    c, p = count[ok], price[ok]
    model = multiplier * rate * c * p * (1 - p) * 1e6
    trade = np.ceil(_js_round(model * 1e3) / 1e3)
    notional = _js_round(c * p * 1e6)
    grid = float(_js_round(precision * 1e6))
    charged = np.ceil((notional + trade) / grid) * grid
    out[ok] = (charged - notional) / 1e6
    return out


def taker_fee(count, price, multiplier: float = 1.0, precision: float = 0.01, rate: float = TAKER_RATE) -> np.ndarray:
    return fee_dollars(rate, multiplier, count, price, precision)


def maker_fee(count, price, multiplier: float = 0.0, precision: float = 0.01, rate: float = MAKER_RATE) -> np.ndarray:
    return fee_dollars(rate, multiplier, count, price, precision)


def contracts_for_stake(stake: float, price) -> np.ndarray:
    """Whole contracts a stake buys at `price` (at least 1 where the price is valid), as the bot's order band sizes."""
    price = np.asarray(price, dtype=np.float64)
    with np.errstate(invalid='ignore', divide='ignore'):
        n = np.floor(stake / np.where((price > 0) & (price < 1), price, np.nan))
    return np.where(np.isfinite(n), np.maximum(n, 1.0), 0.0)
