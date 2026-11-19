"""Kalshi taker fee, a port of bot/fees.ts feeDollars (whole contracts, whole-cent prices, non-direct member).

model fee = 0.07 * C * P * (1 - P), rounded up to $0.000001, then the balance (C * P + fee) is rounded up to the
cent grid; with whole-cent prices that is "round the fee up to the next cent". Settlement has no fee.
Prices here are the price of the side bought or sold (a NO buy pays 1 minus the YES-terms price).
"""
import math

TAKER_RATE = 0.07


def taker_fee(count, price, rate=TAKER_RATE, precision=0.01):
    """Net fee in dollars for one fill of `count` contracts at side price `price`."""
    if not (count > 0) or not (0 < price < 1):
        return 0.0
    model = rate * count * price * (1 - price) * 1e6
    trade = math.ceil(round(model * 1e3) / 1e3)
    notional = round(count * price * 1e6)
    grid = round(precision * 1e6)
    charged = math.ceil((notional + trade) / grid) * grid
    return (charged - notional) / 1e6


def net_if_sold(count, entry_px, entry_fee, exit_px):
    """P&L after both fees of buying `count` at entry_px and selling them at exit_px (taker)."""
    return count * (exit_px - entry_px) - entry_fee - taker_fee(count, exit_px)


def implied_exit(count, entry_px, entry_fee, pnl, settled, side_won):
    """The exit price that explains a trip's P&L, and how far off the best one is.

    Settled trips exit at 1 (side won) or 0 with no exit fee. Sold trips: scan whole-cent exit prices and take the one
    whose net P&L is nearest `pnl` (the trip's own P&L is the book's change in cash less fees, so it already holds
    the exit fee). Returns (exit_px, exit_fee, residual_dollars); residual is |predicted - pnl|.
    """
    if settled:
        x = 1.0 if side_won else 0.0
        return x, 0.0, abs(count * (x - entry_px) - entry_fee - pnl)
    best = None
    for cents in range(1, 100):
        x = cents / 100.0
        res = abs(net_if_sold(count, entry_px, entry_fee, x) - pnl)
        if best is None or res < best[2] - 1e-9:
            best = (x, taker_fee(count, x), res)
    return best
