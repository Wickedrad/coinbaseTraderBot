"""Code triage of one trip: economics (gross, fees, fee share) for every trip, and an ordered class for every loser.

Dollars go to the primary class only; tags are secondary and never carry dollars. Classes (first match wins):
  FIDELITY          the record is flagged (kalshiCheck mismatch, restart double count): kept out of every sweep
  OTHER_LANE        not a heat trip (old pricer, perps, tennis): own lists later
  FEE_ONLY          gross before fees was at or above zero; the fees made it a loss
  CUT_THEN_WON      a loser cut sold it and the side bought then settled as the winner
  SOLD_THEN_WON     any other sale (ratchet, pacer, end rule) of a side that then settled as the winner
  RIGHT_THEN_REVERSED  the side lost at settlement but a profitable exit was reachable on the way (proxy: best bid held)
  WRONG_SIDE        the side lost at settlement and no profitable exit was reachable
  UNEXPLAINED       a loss none of the above explains (should stay empty; each one is read by hand)
  UNKNOWN_DATA      the columns needed to decide are missing
LUCK_WITHIN_NOISE (the call had a positive ex-ante expected value) is deferred: it needs the call ledger's ex-ante
estimate. WRONG_SIDE and the *_THEN_WON classes are hindsight labels (outcome block), never features.
"""
from .fees import taker_fee, net_if_sold, implied_exit

LOSER_CLASSES = ('FIDELITY', 'OTHER_LANE', 'FEE_ONLY', 'CUT_THEN_WON', 'SOLD_THEN_WON', 'RIGHT_THEN_REVERSED',
                 'WRONG_SIDE', 'UNEXPLAINED', 'UNKNOWN_DATA')
CUT_EVENTS = ('plan_loser_cut_sell', 'loser_cut')   # the audit's event name (study files) and the builder's exit rule name
MIN_EDGE = 0.01  # a profitable exit must clear both fees by at least 1c a contract (the one test's margin)


def num(row, key):
    v = row.get(key)
    if v is None or v == '':
        return None
    try:
        return float(v)
    except ValueError:
        return None


def flag(row, key):
    v = str(row.get(key, '')).strip().lower()
    return True if v in ('true', '1', 'yes') else False if v in ('false', '0', 'no') else None


def economics(row):
    """Gross, fees and fee share of one trip from its own P&L: the exit price is the one that explains the P&L."""
    # Builder rows: what filled (count_filled, entry_fill_px) when there is one, else the plan's count and price.
    count = num(row, 'count_filled') if num(row, 'count_filled') is not None else num(row, 'count')
    e = num(row, 'entry_fill_px') if num(row, 'entry_fill_px') is not None else num(row, 'entry_px')
    pnl = num(row, 'pnl')
    if count is None or e is None or pnl is None:
        return None
    count = int(count)
    # Rows from the builder carry the actual fills' fees and exit price: no inference needed.
    afee, xfee, xpx = num(row, 'entry_fee'), num(row, 'exit_fee'), num(row, 'exit_px')
    if afee is not None and xfee is not None and xpx is not None:
        fees = afee + xfee
        cost = count * e
        return {'count': count, 'entry_px': e, 'exit_px': xpx, 'entry_fee': afee, 'exit_fee': xfee, 'fees': fees,
                'gross': pnl + fees, 'cost': cost, 'fee_share': fees / cost if cost > 0 else None, 'residual': 0.0, 'actual': True}
    ef = taker_fee(count, e)
    settled = flag(row, 'settled') is True
    sw = flag(row, 'side_settles_win')
    x, xf, res = implied_exit(count, e, ef, pnl, settled, sw is True)
    cost = count * e
    fees = ef + xf
    return {'count': count, 'entry_px': e, 'exit_px': x, 'entry_fee': ef, 'exit_fee': xf, 'fees': fees,
            'gross': pnl + fees, 'cost': cost, 'fee_share': fees / cost if cost > 0 else None, 'residual': res}


def reachable(row, eco):
    """(reachable, proven): was a profitable exit reachable, i.e. did the highest bid on record clear both fees by 1c a
    contract. The record is best_bid_held plus the bids sampled at entry, +1, +2 and +5 minutes. proven is False when
    best_bid_held is missing: a "not reachable" then holds only for the sampled bids. (None, False): no bid on record.
    A proxy for the one test's one-minute window (best_bid_held is a one-minute extreme)."""
    if eco is None:
        return None, False
    held = num(row, 'best_bid_held')
    hold = num(row, 'hold_s')
    # a sampled bid counts only when its moment fell inside the hold (bid_Nm is the bid N minutes after the order)
    sampled = [num(row, 'bid_entry_min')] + [num(row, k) for k, secs in (('bid_1m', 60), ('bid_2m', 120), ('bid_5m', 300)) if hold is None or hold >= secs]
    bids = [b for b in [held] + sampled if b is not None]
    if not bids:
        return None, False
    ok = net_if_sold(eco['count'], eco['entry_px'], eco['entry_fee'], min(max(bids), 0.99)) >= MIN_EDGE * eco['count']
    return ok, held is not None


def tags(row, eco):
    t = []
    if eco is None:
        return t
    if eco['entry_px'] < 0.25:
        t.append('cheap')
    if eco['count'] >= 60:
        t.append('big_count')
    fe = num(row, 'frac_elapsed_at_entry')
    if fe is not None and fe > 0.5:
        t.append('late_entry')
    if row.get('kind') == 'hourly':
        t.append('hourly')
    if row.get('side') == 'no':
        t.append('no_side')
    if row.get('call_kind') == 'pair':
        t.append('pair_call')
    return t


def classify(row):
    """-> dict(primary, tags, economics...) for one trip row; primary is 'WIN' for a trip that did not lose."""
    eco = economics(row)
    out = {'primary': 'UNKNOWN_DATA', 'tags': tags(row, eco)}
    if eco is None:
        return out
    out.update(eco)
    xb = num(row, 'exit_bid')
    if xb is not None and not eco.get('actual') and flag(row, 'settled') is not True and abs(eco['exit_px'] - xb) > 0.03:
        out['tags'].append('exit_mismatch')  # the P&L implies another exit than the decision bid: a partial sale or re-entry in the same market; gross and fees are approximate
    if eco['residual'] > 1.0 and not eco.get('actual'):
        out['tags'].append('unreconciled')  # one exit price does not explain the P&L (partial sales?): fees are approximate
    if eco['entry_px'] <= 0:
        return out
    pnl = num(row, 'pnl')
    if pnl >= 0:
        out['primary'] = 'WIN'
        return out
    if flag(row, 'fidelity_flag') is True:
        out['primary'] = 'FIDELITY'
    elif row.get('lane') not in (None, '', 'heat'):
        out['primary'] = 'OTHER_LANE'
    elif eco['gross'] >= 0:
        out['primary'] = 'FEE_ONLY'
    else:
        sw = flag(row, 'side_settles_win')
        settled = flag(row, 'settled') is True
        if sw is True and not settled:
            out['primary'] = 'CUT_THEN_WON' if row.get('exit_event') in CUT_EVENTS else 'SOLD_THEN_WON'
        elif sw is False:
            r, proven = reachable(row, eco)
            out['primary'] = 'UNKNOWN_DATA' if r is None else 'RIGHT_THEN_REVERSED' if r else 'WRONG_SIDE'
            if r is False and not proven:
                out['tags'].append('reach_unproven')
        elif sw is True:
            out['primary'] = 'UNEXPLAINED'  # a settled winner cannot lose money
        else:
            out['primary'] = 'UNKNOWN_DATA'
    return out
