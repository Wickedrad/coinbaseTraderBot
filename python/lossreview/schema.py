"""Column registry for the trip record: which block a column belongs to and when it is known.

available_at (ordered): CALL (known when the lane rules on the call), ORDER (known when the order is sent),
P60 (known one minute after entry), CLOSE (known only when the trip is over). A hypothesis may cite only columns
known at ORDER or earlier ("ex-ante"); everything later is the outcome block, shown to a reviewer apart from the
ex-ante block and never usable as a feature. Source: the column set of bot-audit/heat-losers/trips-joined.csv.
"""
CALL, ORDER, P60, CLOSE = 0, 1, 2, 3
LEVEL_NAME = {CALL: 'call', ORDER: 'order', P60: 'plus60s', CLOSE: 'close'}

# column: (available_at, note)
COLUMNS = {
    # identifiers and bookkeeping (not features)
    'ticker': (CALL, 'id'), 'closed_utc': (CLOSE, 'bookkeeping'), 'entry_utc': (ORDER, 'bookkeeping'),
    # the call and the lane's choice
    'kind': (CALL, '15m or hourly'), 'coin': (CALL, ''), 'side': (CALL, 'side bought'), 'h': (CALL, 'curve horizon'),
    'call_key': (CALL, ''), 'call_kind': (CALL, 'single or pair'), 'dir': (CALL, ''), 'rank': (CALL, 'curve rank: a curve value'),
    'of': (CALL, 'batch size'), 'heat': (CALL, 'curve value'), 'fired': (CALL, ''), 'against': (CALL, ''),
    'context': (CALL, 'hour agrees or not'), 'call_age_s': (CALL, ''), 'weight': (CALL, 'curve weight'), 'slot': (CALL, ''),
    'era': (CALL, 'which cut schedule was in force'),
    # order terms
    'plan_price': (ORDER, 'YES terms'), 'entry_px': (ORDER, 'side price paid'), 'count': (ORDER, ''), 'stake': (ORDER, ''),
    'left_at_entry_s': (ORDER, ''), 'frac_elapsed_at_entry': (ORDER, ''), 'strike': (CALL, ''),
    # spot known before the entry minute closed (clean)
    'spot_pre_entry': (CALL, 'last closed minute'), 'spot_pre_age_s': (CALL, ''), 'spot_vs_strike_bps_pre': (CALL, 'clean'),
    # entry-minute book and spot that include the entry minute: known one minute later
    'bid_entry_min': (P60, 'bid in the entry minute'), 'spot_entry': (P60, 'LEAK: minute close, ~53 s ahead'),
    'spot_vs_strike_bps': (P60, 'LEAK: built on spot_entry'), 'spot_bps_1m_for_side': (P60, 'LEAK'),
    'spot_bps_5m_for_side': (CLOSE, 'LEAK'), 'spot_bps_15m_for_side': (CLOSE, 'LEAK'),
    'bid_1m': (P60, ''), 'bid_2m': (CLOSE, ''), 'bid_5m': (CLOSE, ''),
    # outcome block
    'pnl': (CLOSE, ''), 'won': (CLOSE, ''), 'settled': (CLOSE, ''), 'hold_s': (CLOSE, ''), 'exit_event': (CLOSE, ''),
    'exit_bid': (CLOSE, ''), 'exit_net': (CLOSE, ''), 'win_len_s': (CLOSE, ''), 'result': (CLOSE, ''),
    'side_settles_win': (CLOSE, ''), 'best_bid_held': (CLOSE, ''), 'worst_bid_held': (CLOSE, ''),
    'best_bid_after_exit': (CLOSE, ''), 'worst_bid_after_exit': (CLOSE, ''),
    # builder columns (builder.py): the call and order block known when the entry went out
    'entry_px_plan': (ORDER, 'side price the plan asked'), 'count_plan': (ORDER, ''), 'stake_plan': (ORDER, ''),
    'window_close_t': (CALL, 'epoch seconds'), 'entry_t': (ORDER, 'epoch seconds'), 'lane': (CALL, ''),
    # what the fills showed: known once the entry filled (plus 60 s) or when the trip closed
    'entry_taker': (P60, 'every entry fill was a taker'), 'entry_maker_any': (P60, 'some entry fill rested'),
    'entry_fee': (P60, 'actual fee of the entry fills'), 'exit_fee': (CLOSE, ''), 'exit_px': (CLOSE, ''), 'fees': (CLOSE, ''),
    'closed_t': (CLOSE, ''), 'pnl_fills': (CLOSE, ''), 'pnl_gap': (CLOSE, ''), 'pnl_source': (CLOSE, ''),
    'held_to_end': (CLOSE, ''), 'n_sale_legs': (CLOSE, ''), 'legs': (CLOSE, ''), 'defect_sale': (CLOSE, ''),
    'defect_dollars': (CLOSE, ''), 'fee_estimated': (CLOSE, ''), 'orphan_fill': (CLOSE, ''), 'fidelity_flag': (CLOSE, ''),
}

# Columns that carry the lane's curve values. A rule keyed on one of these is a "curve edit": it needs Steven's
# explicit word and is never promoted by the loop on its own.
CURVE_COLUMNS = frozenset({'rank', 'heat', 'weight', 'of', 'fired', 'against', 'call_key', 'call_kind', 'dir', 'h', 'slot', 'context'})


def level(col):
    return COLUMNS[col][0] if col in COLUMNS else None


def ex_ante(col):
    """True when the column is known at order time or earlier."""
    lv = level(col)
    return lv is not None and lv <= ORDER


def validate_feature(col):
    """(ok, reason) for a hypothesis that cites `col`. Unknown columns are refused, later ones too."""
    lv = level(col)
    if lv is None:
        return False, 'unknown column %r' % col
    if lv > ORDER:
        return False, '%s is known only at %s, after the order' % (col, LEVEL_NAME[lv])
    return True, 'curve edit' if col in CURVE_COLUMNS else 'ok'


def blocks(row):
    """Split a row into (ex_ante, outcome) dicts by column; unknown columns go to the outcome block."""
    a, o = {}, {}
    for k, v in row.items():
        (a if ex_ante(k) else o)[k] = v
    return a, o
