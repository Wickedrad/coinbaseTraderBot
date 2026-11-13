"""Join a trip to its market's candles and the coin's spot: the strike and the clean pre-entry spot (known at the call),
the entry minute's bid and the bids after (known later), and the outcome block (the bid path while held and after the exit,
the market's result).

Candle rows are Kalshi's 1-minute candlesticks (end_period_ts, yes_bid / yes_ask OHLC in cents and *_dollars) and
Coinbase's [start, low, high, open, close, volume]. A candle's minute is (end - 60, end]. Nothing here is known earlier
than its tag in schema.py says: spot_pre_* uses only candles closed before the entry.
"""


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _px(side_dict, key):
    """A candle price in dollars: the *_dollars field when present, else cents / 100."""
    if not isinstance(side_dict, dict):
        return None
    v = _f(side_dict.get(key + '_dollars'))
    if v is not None:
        return v
    v = _f(side_dict.get(key))
    return None if v is None else v / 100.0


def side_bid(candle, side, which):
    """The held side's bid in a candle: 'high' = best, 'low' = worst, 'close'. A NO bid is 1 minus the YES ask."""
    if side == 'yes':
        return _px(candle.get('yes_bid'), which)
    inv = {'high': 'low', 'low': 'high', 'close': 'close'}[which]
    v = _px(candle.get('yes_ask'), inv)
    return None if v is None else round(1 - v, 6)


def _end(c):
    return c.get('end_period_ts') or 0


def bid_at(candles, side, t, which='close'):
    """The side bid of the last candle that ends at or before t (None before the first candle)."""
    last = None
    for c in candles:
        if _end(c) <= t:
            last = c
        else:
            break
    return None if last is None else side_bid(last, side, which)


def held_range(candles, side, t0, t1):
    """(best, worst) side bid over the candles that lie wholly inside [t0, t1]; (None, None) when none does (a hold under a
    minute, or no candle). A candle that straddles the entry or the exit would count a price from before the entry or after the
    exit as one the trip could have sold at."""
    hi = lo = None
    for c in candles:
        e = _end(c)
        if e - 60 < t0 or e > t1:
            continue
        h, l = side_bid(c, side, 'high'), side_bid(c, side, 'low')
        if h is not None and (hi is None or h > hi):
            hi = h
        if l is not None and (lo is None or l < lo):
            lo = l
    return hi, lo


def spot_before(spot, t):
    """(close, age_s) of the last Coinbase minute closed at or before t: rows [start, low, high, open, close, volume]."""
    best = None
    for r in spot:
        if r[0] + 60 <= t:
            best = r
    return (None, None) if best is None else (_f(best[4]), round(t - (best[0] + 60), 1))


def spot_after(spot, t):
    """Close of the Coinbase minute that contains t (a leak at the entry: it ends after the order)."""
    for r in spot:
        if r[0] <= t < r[0] + 60:
            return _f(r[4])
    return None


def join(trip, market, candles, spot):
    """The trip dict with the market and path columns added (a copy). Columns that cannot be built stay None."""
    out = dict(trip)
    side, e0, e1 = trip['side'], trip.get('order_t', trip['entry_t']), trip['closed_t']   # e0: the order cannot be later than its first fill
    candles = sorted(candles, key=_end)
    strike = _f((market or {}).get('floor_strike'))
    if strike is None:
        strike = _f((market or {}).get('cap_strike'))
    out['strike'] = strike
    res = (market or {}).get('result')
    if res in ('yes', 'no'):
        out['result'] = res
        out['side_settles_win'] = (res == side)
        out['won'] = bool(trip.get('pnl') is not None and trip['pnl'] > 0)
    sp, age = spot_before(spot, e0)
    out['spot_pre_entry'], out['spot_pre_age_s'] = sp, age
    out['spot_vs_strike_bps_pre'] = round((sp - strike) / strike * 1e4, 2) if sp is not None and strike else None
    out['spot_entry'] = spot_after(spot, e0)
    out['spot_vs_strike_bps'] = round((out['spot_entry'] - strike) / strike * 1e4, 2) if out['spot_entry'] is not None and strike else None
    out['bid_entry_min'] = None
    for c in candles:
        if _end(c) >= e0:
            out['bid_entry_min'] = side_bid(c, side, 'close')
            break
    for name, dt in (('bid_1m', 60), ('bid_2m', 120), ('bid_5m', 300)):
        out[name] = bid_at(candles, side, e0 + dt)
    best, worst = held_range(candles, side, e0, e1)
    out['best_bid_held'], out['worst_bid_held'] = best, worst
    out['win_len_s'] = trip.get('win_len_s')
    return out
