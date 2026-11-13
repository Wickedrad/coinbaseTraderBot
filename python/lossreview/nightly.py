"""One day's trip file from the audit log: build the trips, join the public candles, run the code triage, write the day's
private files and print aggregates only.

    PYTHONPATH=python python3 -m lossreview.nightly --day 2026-11-12 --audit-dir DIR --out DIR [--no-net]

--audit-dir holds audit-<day>*.jsonl[.gz] for the day before, the day and the day after (the day before carries entries
of trips that close after midnight UTC, the day after the settlement of markets that close just after it). --out gets
trips-<day>.jsonl (PER-TRADE DATA: private Drive or the runner only, never a commit, an artifact or a log) and
report-<day>.md plus agg-<day>.json (aggregates: safe to print).
"""
import argparse
import calendar
import datetime
import json
import os
import sys
import time

from . import audit, builder, ledger, outcomes, paths, triage
from .cli import render


def day_bounds(day):
    t0 = calendar.timegm(time.strptime(day, '%Y-%m-%d'))
    return t0, t0 + 86400


def neighbours(day):
    d = datetime.date.fromisoformat(day)
    return [(d + datetime.timedelta(days=k)).isoformat() for k in (-1, 0, 1)]


def run(day, audit_dir, out_dir, net=True):
    """-> (rows, summary dict). rows are the day's trips (closed in the UTC day) with outcomes joined and classes added."""
    t0, t1 = day_bounds(day)
    files = [os.path.join(audit_dir, f) for f in sorted(os.listdir(audit_dir)) if any(f.startswith('audit-%s' % d) for d in neighbours(day))]
    recs, bad = audit.read_files(files, since=t0 - 86400, until=t1 + 7200)
    trips, skipped = builder.build(recs)
    trips = [t for t in trips if t0 <= t['closed_t'] < t1]
    cache = os.path.join(out_dir, 'cache')
    os.makedirs(cache, exist_ok=True)
    rows = []
    spot = {}
    for t in trips:
        if net:
            market, candles = paths.market_and_candles(t['ticker'], cache)
            coin = t['coin']
            if coin and coin not in spot:
                spot[coin] = paths.spot_minutes(coin, t0 - 3 * 3600, t1 + 7200, cache)
            t = outcomes.join(t, market, candles, spot.get(coin, []))
        c = triage.classify(t)
        t = dict(t, **{'class': c['primary'], 'tags': c['tags'], 'gross': c.get('gross'), 'fee_share': c.get('fee_share')})
        rows.append(t)
    cl = [triage.classify(r) for r in rows]
    summ = ledger.summarize(rows, cl) if rows else {}
    summ['day'] = day
    summ['files'] = len(files)
    summ['bad_lines'] = bad
    summ['closes_skipped'] = skipped
    summ['fidelity_flagged'] = sum(1 for r in rows if r.get('fidelity_flag'))
    summ['defect_sales'] = sum(1 for r in rows if r.get('defect_sale'))
    summ['defect_dollars'] = round(sum(r.get('defect_dollars') or 0 for r in rows), 2)
    summ['candles_joined'] = sum(1 for r in rows if r.get('best_bid_held') is not None)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, 'trips-%s.jsonl' % day), 'w', encoding='utf-8') as fh:
        for r in rows:
            fh.write(json.dumps(r, separators=(',', ':'), default=str) + '\n')
    agg = {k: v for k, v in summ.items() if k not in ('by_price', 'by_exit', 'by_coin', 'by_kind')}
    with open(os.path.join(out_dir, 'agg-%s.json' % day), 'w', encoding='utf-8') as fh:
        json.dump(agg, fh, indent=1, default=str)
    if rows:
        md = render(summ, ledger.check_stake(rows), ledger.check_no_price(rows))
        with open(os.path.join(out_dir, 'report-%s.md' % day), 'w', encoding='utf-8') as fh:
            fh.write(md)
    return rows, summ


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--day', required=True)
    ap.add_argument('--audit-dir', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--no-net', action='store_true', help='skip the public candle fetch (outcome columns stay empty)')
    a = ap.parse_args(argv)
    rows, s = run(a.day, a.audit_dir, a.out, net=not a.no_net)
    # aggregates only: no ticker, no per-trade row
    keys = ('day', 'files', 'bad_lines', 'closes_skipped', 'trips', 'losers', 'fidelity_flagged', 'defect_sales', 'defect_dollars', 'candles_joined', 'net', 'fees', 'gross', 'loser_dollars')
    print('LOSSREVIEW %s' % json.dumps({k: s.get(k) for k in keys}, default=str))
    for c in s.get('classes', []):
        print('LOSSREVIEW class %s trips %d dollars %.2f' % (c['class'], c['trips'], c['dollars']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
