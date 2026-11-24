"""OFFLINE helper (run by hand in the cloud session, never in CI): build exits.csv from the trips table and the
plan sale events printed in the public diagnose log. Stdlib only.

  python3 -I build_exits.py --trips trips-joined.csv --log diag.log --out exits.csv

Ratchet exits come from the plan_ratchet_sell events (time = the event's own `at`, count and bids = the event's), each
confirmed against exactly one ratchet trip of the trips table. other_sale exits have no event: time = the trip's closed
time (whole seconds, UTC, year 2026). No entry price, no profit and no strike is written."""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone

COLUMNS = ['n', 'ticker', 'side', 'exit_event', 't0_ms', 't0_src', 'count', 'ref_bid', 'limit_px']
DETAIL_RE = re.compile(r'DETAIL plan (\{.*\})\s*$')


def parse_plan_sales(text):
    out = []
    for line in text.splitlines():
        m = DETAIL_RE.search(line)
        if not m:
            continue
        try:
            e = json.loads(m.group(1))
        except ValueError:
            continue
        if e.get('event') == 'plan_ratchet_sell':
            out.append(e)
    return out


def closed_ms(s, year=2026):
    return int(datetime.strptime(f'{year} {s}', '%Y %m-%d %H:%M:%S').replace(tzinfo=timezone.utc).timestamp() * 1000)


def num(x):
    return '' if x is None or x == '' else ('%.6f' % float(x)).rstrip('0').rstrip('.')


def build(trips, events):
    rows, stats = [], {'ratchet_trips': 0, 'matched': 0, 'no_event': 0, 'ambiguous': 0, 'bid_mismatch': 0, 'unused_events': 0, 'other_sale': 0}
    used = set()
    for tr in trips:
        if tr['exit_event'] == 'plan_ratchet_sell':
            stats['ratchet_trips'] += 1
            c = closed_ms(tr['closed_utc']) / 1000.0
            cand = [i for i, e in enumerate(events) if i not in used and e['ticker'] == tr['ticker'] and e['side'] == tr['side']
                    and -1.0 < c - e['at'] / 1000.0 < 3.0]
            if not cand:
                stats['no_event'] += 1
                continue
            if len(cand) > 1:
                stats['ambiguous'] += 1
                cand.sort(key=lambda i: abs(c - events[i]['at'] / 1000.0))
            e = events[cand[0]]
            used.add(cand[0])
            stats['matched'] += 1
            if tr.get('exit_bid') not in (None, '') and abs(float(tr['exit_bid']) - float(e['bid'])) > 1e-9:
                stats['bid_mismatch'] += 1
            rows.append([e['ticker'], e['side'], 'plan_ratchet_sell', int(e['at']), 'plan_at', num(e['count']), num(e['bid']), num(e.get('limit'))])
        elif tr['exit_event'] == 'other_sale':
            stats['other_sale'] += 1
            rows.append([tr['ticker'], tr['side'], 'other_sale', closed_ms(tr['closed_utc']), 'closed_utc', num(tr['count']), '', ''])
    stats['unused_events'] = len(events) - len(used)
    rows.sort(key=lambda r: (r[3], r[0]))
    return [[i + 1] + r for i, r in enumerate(rows)], stats


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--trips', required=True)
    ap.add_argument('--log', required=True)
    ap.add_argument('--out', required=True)
    a = ap.parse_args(argv)
    with open(a.trips, newline='', encoding='utf-8') as fh:
        trips = list(csv.DictReader(fh))
    with open(a.log, encoding='utf-8', errors='replace') as fh:
        events = parse_plan_sales(fh.read())
    rows, stats = build(trips, events)
    with open(a.out, 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        w.writerow(COLUMNS)
        w.writerows(rows)
    print(json.dumps({'rows': len(rows), 'events_in_log': len(events), **stats}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
