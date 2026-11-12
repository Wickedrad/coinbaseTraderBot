#!/usr/bin/env python3
"""Heat lane round trips, plan exits (loser cut, ratchet, end rule) and re-entries after a loss, from the bot's audit log.

Read-only. Server diagnostics uploads this file and runs it on the server:

    python3 heat_trips.py DATA_DIR [HOURS] [--journal FILE]

It reads DATA_DIR/audit/audit-*.jsonl (one JSON record a line: seq, ts, kind, data) for the last HOURS (default 24), and
FILE when given: the bot's "[heat] round trip closed" log lines (journalctl), which carry each round trip's own result.
Without them the audit's "closed" record gives it: its pnl since the record carries the book's total as bookPnl (Nov 12);
before that the total was written over pnl, and a trip's result is the change in that total (unknown when two trips close
in one pass). It prints:
  - every heat round trip closed (sold or settled) with its result, and the totals;
  - every plan sale and call-off (loser cut, ratchet, end rule) with the entry price, the bid and the net;
  - re-entries after a loss: by contract window (a 15-minute contract, or an hourly window with all of its strikes), the
    losses and the entries sent after the first one;
  - the reasons heat calls were not entered, the re-entry rules' first.
"""
import calendar
import collections
import glob
import json
import os
import re
import sys
import time

KINDS = ('"kind":"heat"', '"kind":"plan"')
RE_RULES = (
    'since its first loss',
    'HEAT_REENTRY_LOSS_STOP',
    'a re-entry after a loss needs',
    're-entry needs a call made after',
    'before re-entries were counted',
    'loser cut (',
)


def window_of(ticker):
    """A 15-minute contract is its own window; an hourly ladder's strikes (-T<strike>, -B<bracket>) share theirs."""
    return re.sub(r'-[TB][0-9.]+$', '', ticker)


def iso_s(ts):
    """An audit time ('2026-11-12T01:40:45.854Z', UTC) in seconds since the epoch, milliseconds kept."""
    ms = int(ts[20:23]) if len(ts) >= 23 and ts[20:23].isdigit() else 0
    return calendar.timegm(time.strptime(ts[:19], '%Y-%m-%dT%H:%M:%S')) + ms / 1000.0


def hhmm(t):
    return time.strftime('%m-%d %H:%M:%S', time.gmtime(t)) + 'Z'


def money(x):
    return ('+' if x > 0 else '-' if x < 0 else ' ') + '$%.2f' % abs(x)


JOURNAL = re.compile(r'(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z)\s+INFO\s+\[heat\] round trip closed (\S+) (yes|no) pnl (-?[\d.]+) \((sold|settled)\)')


def trips_from_journal(path, since):
    out = []
    with open(path, 'r', encoding='utf-8', errors='replace') as fh:
        for line in fh:
            m = JOURNAL.search(line)
            if not m:
                continue
            t = iso_s(m.group(1))
            if t >= since:
                out.append((t, {'ticker': m.group(2), 'side': m.group(3), 'pnl': float(m.group(4)), 'settled': m.group(5) == 'settled'}))
    return out


def trips_from_audit(closed, prev=None):
    """The audit's closed records: a trip's result is the change in the book's running total since the pass before
    (prev: the total at the last close before the window, when the files read hold one)."""
    out = []
    passes = collections.OrderedDict()
    for t, d in closed:
        passes.setdefault((t, d.get('trips')), []).append(d)
    for (t, _), ds in passes.items():
        if 'bookPnl' in ds[0]:
            # A record with the book's total apart: pnl is the trip's own.
            out.extend((t, d) for d in ds)
            prev = float(ds[0].get('bookPnl') or 0)
            continue
        book = float(ds[0].get('pnl') or 0)
        delta = None if prev is None else round(book - prev, 6)
        for d in ds:
            out.append((t, dict(d, pnl=delta if len(ds) == 1 else None)))
        prev = book
    return out


def read(data_dir, hours, now):
    since = now - hours * 3600
    files = sorted(glob.glob(os.path.join(data_dir, 'audit', 'audit-*.jsonl')))
    # A file last written before the window holds nothing in it.
    files = [f for f in files if os.path.getmtime(f) >= since]
    out, before = [], None
    for f in files:
        with open(f, 'r', encoding='utf-8', errors='replace') as fh:
            for line in fh:
                if KINDS[0] not in line and KINDS[1] not in line:
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                t = iso_s(r.get('ts') or '1970-01-01T00:00:00')
                d = r.get('data') or {}
                if t >= since:
                    out.append((t, r.get('kind'), d))
                elif r.get('kind') == 'heat' and d.get('event') == 'closed' and (before is None or t >= before[0]):
                    before = (t, d)
    out.sort(key=lambda x: x[0])
    prev = None if before is None else float(before[1].get('bookPnl', before[1].get('pnl')) or 0)
    return out, files, since, prev


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    args = sys.argv[1:]
    journal = None
    if '--journal' in args:
        i = args.index('--journal')
        journal = args[i + 1] if i + 1 < len(args) else None
        args = args[:i] + args[i + 2:]
    data_dir = os.path.expanduser(args[0])
    hours = float(args[1]) if len(args) > 1 else 24.0
    now = time.time()
    recs, files, since, prev_book = read(data_dir, hours, now)
    print('from %s to %s (%d audit file(s), %d heat and plan records)' % (hhmm(since), hhmm(now), len(files), len(recs)))

    audit_closed = [(t, d) for t, k, d in recs if k == 'heat' and d.get('event') == 'closed']
    if journal and os.path.exists(journal):
        closed = trips_from_journal(journal, since)
        print('round trip results from the bot log (%d lines)' % len(closed))
    else:
        closed = trips_from_audit(audit_closed, prev_book)
        print('round trip results from the audit (the change in the book total; "?" = two trips closed in one pass)')
    pnl_of = lambda d: float(d.get('pnl') or 0)
    sales = [(t, d) for t, k, d in recs if k == 'plan' and str(d.get('event', '')).endswith(('_sell', '_cancel')) and d.get('event') != 'plan_ratchet_retry']
    entries = [(t, d) for t, k, d in recs if k == 'heat' and isinstance(d.get('plan'), dict)]
    skips = [(t, d) for t, k, d in recs if k == 'heat' and 'skip' in d and 'event' not in d]

    # Round trips.
    pnl = sum(pnl_of(d) for _, d in closed)
    wins = sum(1 for _, d in closed if pnl_of(d) > 0)
    settled = [(t, d) for t, d in closed if d.get('settled')]
    settled_loss = [(t, d) for t, d in settled if pnl_of(d) < 0]
    print('\nround trips closed: %d, %d won, net %s | sold %d (%s) | settled %d (%s), %d of them at a loss (%s)' % (
        len(closed), wins, money(pnl),
        len(closed) - len(settled), money(sum(pnl_of(d) for _, d in closed if not d.get('settled'))),
        len(settled), money(sum(pnl_of(d) for _, d in settled)),
        len(settled_loss), money(sum(pnl_of(d) for _, d in settled_loss))) +
          ('' if all(d.get('pnl') is not None for _, d in closed) else ' | %d result(s) unknown, counted as $0' % sum(1 for _, d in closed if d.get('pnl') is None)))
    for t, d in closed:
        print('  %s %-28s %-3s %8s %-8s %s' % (hhmm(t), d.get('ticker'), d.get('side'), '?' if d.get('pnl') is None else money(pnl_of(d)),
                                             'settled' if d.get('settled') else 'sold', str(d.get('ruleId') or '')[:60]))

    # Plan sales and call-offs.
    by = collections.Counter(d.get('event') for _, d in sales)
    print('\nplan sales and call-offs: %s' % (', '.join('%s %d' % (k, v) for k, v in sorted(by.items())) or 'none'))
    for t, d in sales:
        entry = d.get('entry')
        print('  %s %-22s %-28s %-3s entry %-5s bid %-5s count %-4s net %8s limit %-5s %s' % (
            hhmm(t), str(d.get('event', '')).replace('plan_', ''), d.get('ticker'), d.get('side'),
            '%.2f' % entry if isinstance(entry, (int, float)) else '-', d.get('bid'), d.get('count'),
            money(float(d.get('net') or 0)) if d.get('net') is not None else '-', d.get('limit'), 'sent' if d.get('sent') else ''))

    # Re-entries after a loss, by window.
    first_loss = {}
    losses = collections.defaultdict(list)
    for t, d in closed:
        if pnl_of(d) < 0:
            w = window_of(str(d.get('ticker')))
            first_loss.setdefault(w, t)
            losses[w].append((t, d))
    re_by = collections.defaultdict(list)
    for t, d in entries:
        p = d['plan']
        w = window_of(str(p.get('ticker')))
        if w in first_loss and t > first_loss[w]:
            re_by[w].append((t, d))
    print('\nwindows left at a loss: %d | re-entries sent after a loss: %d in %d window(s)' % (
        len(losses), sum(1 for v in re_by.values() for _, d in v if str(d.get('entry', '')).startswith('sent')), len(re_by)))
    for w in sorted(losses, key=lambda x: first_loss[x]):
        ls = losses[w]
        print('  %-26s losses %d (%s), first %s' % (w, len(ls), money(sum(pnl_of(d) for _, d in ls)), hhmm(first_loss[w])))
        for t, d in re_by.get(w, []):
            p = d['plan']
            print('     re-entry %s %-28s %-3s at %s x%s ($%s) call %s %s -> %s' % (
                hhmm(t), p.get('ticker'), p.get('side'), p.get('price'), p.get('count'), p.get('stakeUsd'),
                d.get('dir'), str(d.get('key') or '')[:40], str(d.get('entry') or '')[:60]))

    # Why calls were not entered: the re-entry rules and the cut's spread guard first, then the rest.
    reasons = collections.Counter()
    for _, d in skips:
        s = str(d.get('skip') or '')
        tag = next((r for r in RE_RULES if r in s), None)
        reasons[('re-entry: ' if tag else '') + re.sub(r'\d+(\.\d+)?', '#', s)[:110]] += 1
    print('\ncalls not entered: %d' % len(skips))
    for k, v in sorted(reasons.items(), key=lambda kv: (not kv[0].startswith('re-entry: '), -kv[1]))[:14]:
        print('  %5d  %s' % (v, k))
    return 0


if __name__ == '__main__':
    sys.exit(main())
