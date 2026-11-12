"""Aggregates over classified trips: the fee-per-stake ledger (every trip, winners too) and class dollars (losers)."""
import collections
import datetime

BUCKETS = ((0.0, 0.25, 'under 25c'), (0.25, 0.5, '25c to 50c'), (0.5, 0.75, '50c to 75c'), (0.75, 1.01, '75c and over'))


def bucket(px):
    for lo, hi, name in BUCKETS:
        if lo <= px < hi:
            return name
    return 'other'


def _ts(s):
    """'11-12 01:40:45' (UTC, 2026) -> datetime."""
    return datetime.datetime.strptime('2026-' + s, '%Y-%m-%d %H:%M:%S')


def span_hours(rows):
    try:
        a = min(_ts(r['entry_utc']) for r in rows if r.get('entry_utc'))
        b = max(_ts(r['closed_utc']) for r in rows if r.get('closed_utc'))
        return max((b - a).total_seconds() / 3600.0, 1e-9)
    except (ValueError, KeyError):
        return None


def group(items, keyfn):
    out = collections.OrderedDict()
    for it in items:
        out.setdefault(keyfn(it), []).append(it)
    return out


def summarize(rows, classified):
    """rows: input dicts; classified: matching classify() dicts. Returns a plain dict of aggregates."""
    pairs = [(r, c) for r, c in zip(rows, classified) if 'fees' in c]
    pnl = [float(r['pnl']) for r, _ in pairs]
    hours = span_hours([r for r, _ in pairs])
    t = {'trips': len(pairs), 'net': sum(pnl), 'fees': sum(c['fees'] for _, c in pairs),
         'entry_fees': sum(c['entry_fee'] for _, c in pairs), 'exit_fees': sum(c['exit_fee'] for _, c in pairs),
         'gross': sum(c['gross'] for _, c in pairs), 'hours': hours,
         'max_residual': max((c['residual'] for _, c in pairs), default=0.0)}
    if hours:
        t.update({k + '_per_h': t[k] / hours for k in ('net', 'fees', 'gross', 'trips')})
    losers = [(r, c) for r, c in pairs if c['primary'] != 'WIN']
    winners = [(r, c) for r, c in pairs if c['primary'] == 'WIN']
    t['fees_losers'] = sum(c['fees'] for _, c in losers)
    t['fees_winners'] = sum(c['fees'] for _, c in winners)
    t['losers'] = len(losers)
    t['loser_dollars'] = sum(float(r['pnl']) for r, _ in losers)

    def fee_rows(groups):
        out = []
        for k, v in groups.items():
            cost = sum(c['cost'] for _, c in v)
            contracts = sum(c['count'] for _, c in v)
            out.append({'group': k, 'trips': len(v), 'cost': cost, 'fees': sum(c['fees'] for _, c in v),
                        'fee_share': (sum(c['fees'] for _, c in v) / cost) if cost else None,
                        'gross_per_contract': sum(c['gross'] for _, c in v) / contracts if contracts else None,
                        'net_per_contract': sum(float(r['pnl']) for r, _ in v) / contracts if contracts else None})
        return out

    order = [b[2] for b in BUCKETS]
    t['by_price'] = sorted(fee_rows(group(pairs, lambda p: bucket(p[1]['entry_px']))), key=lambda r: order.index(r['group']) if r['group'] in order else 99)
    t['by_exit'] = fee_rows(group(pairs, lambda p: p[0].get('exit_event') or 'none'))
    t['by_coin'] = fee_rows(group(pairs, lambda p: p[0].get('coin') or '?'))
    t['by_kind'] = fee_rows(group(pairs, lambda p: p[0].get('kind') or '?'))
    cls = group(losers, lambda p: p[1]['primary'])
    t['classes'] = [{'class': k, 'trips': len(v), 'dollars': sum(float(r['pnl']) for r, _ in v)} for k, v in cls.items()]
    return t


def check_stake(rows, tol=0.0):
    """Rows where count * entry_px does not explain stake (the check that catches a YES price used for a NO buy):
    stake - count*px must lie in [0, px), since the count is the whole number of contracts the stake buys."""
    bad = []
    for r in rows:
        try:
            count, px, stake = float(r['count']), float(r['entry_px']), float(r['stake'])
        except (KeyError, ValueError):
            continue
        d = stake - count * px
        if d < -tol - 1e-9 or d >= px + tol:
            bad.append(r.get('ticker'))
    return bad


def check_no_price(rows):
    """NO buys whose side price is not 1 minus the YES-terms plan price."""
    bad = []
    for r in rows:
        if r.get('side') != 'no':
            continue
        try:
            if abs(float(r['entry_px']) - (1 - float(r['plan_price']))) > 0.015:
                bad.append(r.get('ticker'))
        except (KeyError, ValueError):
            continue
    return bad
