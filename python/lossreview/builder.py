"""Trip builder: heat round trips from the bot's own audit records (call, order, fills, plan sales, settlement).

One trip per `heat` record of event 'closed'. Everything about the trip is rebuilt from the records:
  - the call and the lane's plan (ex-ante block: call and order columns, from the `heat` record that sent the entry);
  - the fills of the market between the entry and the close (taker or maker, actual fees, actual prices), in the book's
    YES terms: a 'bid' fill adds YES contracts and an 'ask' fill removes them, so a NO trip enters on asks;
  - the sale legs (one per sell order), each tagged with the plan rule that sent it (ratchet, loser cut, end rule, other)
    and whether it cleared the entry cost plus both fees (the break-even floor, Steven Nov 12);
  - the result at settlement for what was still held.

Prices in the trip are side terms (a NO buy pays 1 minus the YES-terms price). Per-trade rows leave this module only
into private files; reports print aggregates.

Every ex-ante column is computed by `exante()` from records at or before the entry, so the truncate-at-call test can
rebuild it from the log cut at that moment and compare.
"""
import collections
import datetime
import re

from .audit import iso_s, utc
from .fees import taker_fee

EXIT_RULES = {'plan_ratchet_sell': 'ratchet', 'plan_loser_cut_sell': 'loser_cut', 'plan_end_rule_sell': 'end_rule'}
# Sales that may land under the round-trip cost: the loser cut (by design) and the end-of-window exit.
ALLOWED_BELOW = ('loser_cut', 'end_rule')
SALE_MATCH_S = 180.0      # a plan sale event precedes the fill of its order by seconds; the event within this is its rule
SALE_AFTER_S = 5.0        # ... or follows it by a few milliseconds (the event is written after the send returns)
ENTRY_SLACK_S = 30.0      # fills of the market counted from this long before the entry record (clock skew), never before the last close
EXIT_SLACK_S = 10.0       # ... and until this long after the close record
RECON_TOL = 0.10          # a trip whose fills explain its logged P&L within this is reconciled
WINDOW_S = {'15m': 900, 'hourly': 3600}
MONTHS = {m: i + 1 for i, m in enumerate('JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC'.split())}
TICKER = re.compile(r'^KX([A-Z]+?)(15M|D)-(\d\d)([A-Z]{3})(\d\d)(\d\d)(\d\d)?')


def parse_ticker(ticker):
    """(coin, kind, close epoch seconds) of a heat ticker, or (None, None, None). Close time is Kalshi's (US Eastern)."""
    m = TICKER.match(ticker or '')
    if not m:
        return None, None, None
    coin, suffix, yy, mon, dd, hh, mm = m.groups()
    kind = '15m' if suffix == '15M' else 'hourly'
    if mon not in MONTHS:
        return coin, kind, None
    try:
        from zoneinfo import ZoneInfo
        local = datetime.datetime(2000 + int(yy), MONTHS[mon], int(dd), int(hh), int(mm or 0), tzinfo=ZoneInfo('America/New_York'))
    except Exception:  # noqa: BLE001 - an odd ticker or no tz database: the window is then unknown
        return coin, kind, None
    return coin, kind, local.timestamp()


def side_price(side, yes_price):
    """The price of the side bought for a YES-terms price."""
    return yes_price if side == 'yes' else round(1 - yes_price, 6)


def index(records):
    """Group the audit records by what the builder joins on."""
    ix = {'entries': collections.defaultdict(list), 'closed': [], 'fills': collections.defaultdict(list),
          'orders': {}, 'plan': collections.defaultdict(list), 'settle': {}}
    for t, k, d, _seq in records:
        if k == 'heat':
            if d.get('event') == 'closed' and d.get('ticker'):
                ix['closed'].append((t, d))
            elif isinstance(d.get('plan'), dict) and d['plan'].get('ticker'):
                ix['entries'][d['plan']['ticker']].append((t, d))
        elif k == 'fill':
            fl = d.get('fill') or {}
            tk = fl.get('ticker')
            if tk:
                ix['fills'][tk].append((t, d))
        elif k == 'order_new':
            if d.get('clientOrderId'):
                ix['orders'][d['clientOrderId']] = (t, d)
        elif k == 'plan':
            if d.get('ticker'):
                ix['plan'][d['ticker']].append((t, d))
        elif k == 'settlement':
            if d.get('ticker'):
                ix['settle'][d['ticker']] = (t, d)
    return ix


def exante(entry_t, d, ticker, closed=None, order_close_ms=None):
    """The ex-ante block of a trip from the `heat` record that sent the entry (time entry_t) and the ticker alone.

    Uses nothing recorded after entry_t. `closed` is only read for the lane's own labels (asset, kind), which the ticker
    also gives; order_close_ms is the window close when an order of the entry carries it.
    """
    plan = d.get('plan') or {}
    side = plan.get('side')
    coin, kind, close_t = parse_ticker(ticker)
    if order_close_ms:
        close_t = order_close_ms / 1000.0
    kind = (closed or {}).get('kind') or kind
    coin = d.get('asset') or (closed or {}).get('asset') or coin
    win = WINDOW_S.get(kind)
    plan_price = plan.get('price')
    row = {
        'ticker': ticker, 'kind': kind, 'coin': coin, 'side': side, 'h': d.get('h'),
        'call_key': d.get('key'), 'call_kind': d.get('kind'), 'dir': d.get('dir'), 'rank': d.get('rank'), 'of': d.get('of'),
        'heat': d.get('heat'), 'fired': d.get('fired'), 'against': d.get('against'), 'context': d.get('context'),
        'weight': plan.get('weight'), 'slot': plan.get('slot'),
        'plan_price': plan_price, 'entry_px_plan': side_price(side, plan_price) if plan_price is not None and side else None,
        'entry_px': side_price(side, plan_price) if plan_price is not None and side else None,
        'count_plan': plan.get('count'), 'stake_plan': plan.get('stakeUsd'),
        # entry_px, count and stake are the PLAN's values (known when the order went out); what filled is in entry_fill_px,
        # count_filled and stake_filled (known later) so a hypothesis can never lean on the fill.
        'count': plan.get('count'), 'stake': plan.get('stakeUsd'),
        'entry_utc': utc(entry_t),
        'call_age_s': round(entry_t - d['barClose'] / 1000.0, 1) if isinstance(d.get('barClose'), (int, float)) else None,
    }
    if close_t is not None and win:
        row['left_at_entry_s'] = round(close_t - entry_t, 1)
        row['frac_elapsed_at_entry'] = round(1 - (close_t - entry_t) / win, 4)
        row['window_close_t'] = close_t
    return row


def _fill_rows(fills_t, side, t0, t1, orders):
    """Fills of one market in [t0, t1] as dicts in side terms: dir 'in' (entry) or 'out' (sale)."""
    out, seen = [], set()
    for t, d in fills_t:
        fl = d.get('fill') or {}
        tid = fl.get('tradeId')
        if tid is not None:
            if tid in seen:
                out.append({'dup': True, 't': t, 'dir': 'dup', 'px': 0.0, 'count': 0.0, 'fee': 0.0, 'fee_est': False, 'taker': False, 'coid': None, 'orphan': False})
                continue
            seen.add(tid)
        ft = fl.get('ts')
        ft = ft / 1000.0 if isinstance(ft, (int, float)) and ft > 1e11 else t
        if ft < t0 or ft > t1:
            continue
        book = fl.get('side')
        if book not in ('bid', 'ask'):
            continue
        yes_in = (book == 'bid')
        entering = yes_in == (side == 'yes')
        yp = float(fl.get('price') or 0)
        cnt = float(fl.get('count') or 0)
        if cnt <= 0:
            continue
        px = side_price(side, yp)
        fee = d.get('fee')
        est = bool(d.get('feeEstimated'))
        if not isinstance(fee, (int, float)):
            fee, est = taker_fee(int(round(cnt)), px) if fl.get('isTaker') else 0.0, True
        out.append({'t': ft, 'dir': 'in' if entering else 'out', 'px': px, 'count': cnt, 'fee': float(fee), 'fee_est': est,
                    'taker': bool(fl.get('isTaker')), 'coid': d.get('clientOrderId'), 'orphan': bool(d.get('orphan'))})
    return out


def _rule_for(t, events):
    """The plan sale event nearest to the fill time t that actually went out. The engine writes the event right after it sends
    the sale, and a paper fill lands inside that call: so the event may come a few milliseconds AFTER the fill (SALE_AFTER_S)
    or up to SALE_MATCH_S before it."""
    best = None
    for et, e in events:
        lag = t - et
        if -SALE_AFTER_S <= lag <= SALE_MATCH_S and e.get('event') in EXIT_RULES and e.get('sent') is not False:
            if best is None or abs(lag) < abs(t - best[0]):
                best = (et, e)
    return (EXIT_RULES[best[1]['event']], best[0], best[1]) if best else ('other', None, None)


def build_trip(closed_t, closed, ix):
    """One trip record (dict) from a 'closed' heat record and the index of the day's records, or None when its entry
    cannot be found."""
    tk = closed['ticker']
    side = closed.get('side')
    prev_close = max([t for t, c in ix['closed'] if c['ticker'] == tk and t < closed_t] or [0])
    entries = [(t, d) for t, d in ix['entries'].get(tk, []) if prev_close <= t <= closed_t]
    if not entries or side not in ('yes', 'no'):
        return None
    entry_t, ed = entries[-1]
    close_ms = None
    for fl in ix['fills'].get(tk, []):
        o = ix['orders'].get((fl[1] or {}).get('clientOrderId'))
        if o and o[1].get('windowCloseTs'):
            close_ms = o[1]['windowCloseTs']
            break
    row = exante(entry_t, ed, tk, closed, close_ms)
    fills = _fill_rows(ix['fills'].get(tk, []), side, max(entry_t - ENTRY_SLACK_S, prev_close + 0.001), closed_t + EXIT_SLACK_S, ix['orders'])
    dups = sum(1 for f in fills if f.get('dir') == 'dup')    # the same trade id twice in the log (a restart): counted once, flagged
    fills = [f for f in fills if f.get('dir') != 'dup']
    ins = [f for f in fills if f['dir'] == 'in']
    outs = [f for f in fills if f['dir'] == 'out']
    n_in = sum(f['count'] for f in ins)
    if n_in <= 0:
        return None
    order_t = min(entry_t, min(f['t'] for f in ins))   # the order cannot be later than its first fill: the cutoff for anything 'known at the order'
    cost = sum(f['px'] * f['count'] for f in ins)
    entry_fee = sum(f['fee'] for f in ins)
    entry_px = cost / n_in
    # sale legs: one per sell order (client order id), in time order
    legs, by_order = [], collections.OrderedDict()
    for f in sorted(outs, key=lambda x: x['t']):
        by_order.setdefault(f['coid'] or ('t%.0f' % f['t']), []).append(f)
    events = sorted(ix['plan'].get(tk, []), key=lambda x: x[0])
    for coid, fs in by_order.items():
        n = sum(f['count'] for f in fs)
        px = sum(f['px'] * f['count'] for f in fs) / n
        fee = sum(f['fee'] for f in fs)
        rule, et, ev = _rule_for(fs[0]['t'], events)
        basis = n * entry_px + entry_fee * (n / n_in)  # the entry cost of these contracts: price plus their share of the entry fee
        net_after_both = n * px - fee - basis
        legs.append({'t': round(fs[0]['t'], 1), 'rule': rule, 'px': round(px, 4), 'count': n, 'fee': round(fee, 4),
                     'taker': any(f['taker'] for f in fs), 'net_vs_cost': round(net_after_both, 4),
                     'below_breakeven': net_after_both < -1e-9, 'bid_at_event': (ev or {}).get('bid')})
    n_out = sum(f['count'] for f in outs)
    held = max(0.0, n_in - n_out)
    st = ix['settle'].get(tk)
    result = (st[1].get('result') if st else None)
    result = result if result in ('yes', 'no') else None
    settled_trip = bool(closed.get('settled'))
    side_settles_win = None if result is None else (result == side)
    payout = 0.0
    if held > 1e-9:
        payout = held * (1.0 if side_settles_win else 0.0) if side_settles_win is not None else None
    exit_fee = sum(f['fee'] for f in outs)
    revenue = sum(f['px'] * f['count'] for f in outs)
    pnl_fills = None if payout is None else round(revenue + payout - cost - entry_fee - exit_fee, 6)
    pnl_logged = closed.get('pnl')
    pnl_book = closed.get('bookPnl')
    # An old closed record carried the book's running total in pnl; a trip then has no logged result of its own.
    logged_ok = pnl_book is not None and isinstance(pnl_logged, (int, float))
    gap = None if (pnl_fills is None or not logged_ok) else round(pnl_fills - pnl_logged, 4)
    pnl = pnl_logged if logged_ok else pnl_fills
    exit_total_n = n_out + held
    exit_px = None if exit_total_n <= 0 or payout is None else (revenue + payout) / exit_total_n
    first_sale = legs[0] if legs else None
    last_leg = legs[-1] if legs else None
    exit_event = 'settled' if held > 1e-9 else (last_leg['rule'] if last_leg else 'settled' if settled_trip else None)   # what ended the trip
    defect = [l for l in legs if l['below_breakeven'] and l['rule'] not in ALLOWED_BELOW]
    row.update({
        'closed_utc': utc(closed_t), 'closed_t': closed_t, 'entry_t': entry_t, 'order_t': order_t,
        'hold_s': round(closed_t - entry_t, 1),
        'count_filled': n_in, 'entry_fill_px': round(entry_px, 6), 'stake_filled': round(cost, 4),
        'entry_fee': round(entry_fee, 4), 'exit_fee': round(exit_fee, 4), 'exit_px': None if exit_px is None else round(exit_px, 6),
        'fees': round(entry_fee + exit_fee, 4),
        'entry_taker': all(f['taker'] for f in ins), 'entry_maker_any': any(not f['taker'] for f in ins),
        'pnl': pnl, 'pnl_fills': pnl_fills, 'pnl_gap': gap, 'pnl_source': 'logged' if logged_ok else 'fills',
        'settled': settled_trip, 'held_to_end': round(held, 4), 'result': result, 'side_settles_win': side_settles_win,
        'exit_event': exit_event, 'exit_bid': None if not first_sale else first_sale.get('bid_at_event'),
        'n_sale_legs': len(legs), 'legs': legs,
        'defect_sale': bool(defect), 'defect_dollars': round(sum(l['net_vs_cost'] for l in defect), 4),
        'fee_estimated': any(f['fee_est'] for f in fills), 'orphan_fill': any(f['orphan'] for f in fills), 'dup_fills': dups,
        'sale_revenue': round(revenue, 6), 'unresolved': payout is None,
    })
    # A remainder held with no result yet leaves the P&L unproven: flagged until the result arrives (resolve_payout).
    row['fidelity_flag'] = bool(row['orphan_fill'] or dups or payout is None or (gap is not None and abs(gap) > RECON_TOL) or pnl is None)
    row['lane'] = 'heat'
    return row


def build(records):
    """All trips closed in `records` (list from audit.read_files), time order. Also returns a count of closes skipped."""
    ix = index(records)
    trips, skipped = [], 0
    for t, c in sorted(ix['closed'], key=lambda x: x[0]):
        r = build_trip(t, c, ix)
        if r is None:
            skipped += 1
        else:
            trips.append(r)
    return trips, skipped


def resolve_payout(row):
    """Finish a trip whose remainder was held to settlement but whose result was not in the audit log (the market settled after
    the files read): once side_settles_win is known from the market's public record, compute the payout, the P&L from the fills
    and the reconciliation, and clear the unresolved flag. Returns a new row."""
    if not row.get('unresolved') or row.get('side_settles_win') is None:
        return row
    held = float(row.get('held_to_end') or 0.0)
    payout = held * (1.0 if row['side_settles_win'] else 0.0)
    cost = float(row['count_filled']) * float(row['entry_fill_px'])
    pnl_fills = round(float(row['sale_revenue']) + payout - cost - float(row['entry_fee']) - float(row['exit_fee']), 6)
    out = dict(row, unresolved=False, pnl_fills=pnl_fills)
    logged = row.get('pnl') if row.get('pnl_source') == 'logged' else None
    gap = None if logged is None else round(pnl_fills - logged, 4)
    out['pnl_gap'] = gap
    n_total = float(row['count_filled'])
    out['exit_px'] = round((float(row['sale_revenue']) + payout) / n_total, 6) if n_total > 0 else None
    if row.get('pnl_source') != 'logged':
        out['pnl'] = pnl_fills
    out['fidelity_flag'] = bool(row.get('orphan_fill') or row.get('dup_fills') or (gap is not None and abs(gap) > RECON_TOL))
    return out
