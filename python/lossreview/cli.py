"""Run the code triage and the fee ledger on a trip file.

    PYTHONPATH=python python3 -m lossreview.cli TRIPS.csv --out DIR

Writes DIR/triage.csv (one row per trip: class, tags, gross, fees; PER-TRADE DATA, keep it out of the public repo:
private Drive or the project folder only) and DIR/report.md (aggregates only), and prints the aggregates.
"""
import argparse
import csv
import os
import sys

from . import ledger, triage


def money(x):
    return ('-' if x < 0 else '') + '$%.2f' % abs(x)


def pct(x):
    return '-' if x is None else '%.1f%%' % (100 * x)


def render(t, stake_bad, no_bad):
    L = []
    L.append('# Loss review: code triage and fee ledger')
    L.append('')
    L.append('%d trips over %.1f h: net %s (%s/h), fees %s (%s/h; %s on losers, %s on winners), gross before fees %s (%s/h), %.1f trips/h.' % (
        t['trips'], t['hours'] or 0, money(t['net']), money(t.get('net_per_h', 0)), money(t['fees']), money(t.get('fees_per_h', 0)),
        money(t['fees_losers']), money(t['fees_winners']), money(t['gross']), money(t.get('gross_per_h', 0)), t.get('trips_per_h', 0)))
    L.append('Entry fees %s, exit fees %s. Largest residual when explaining a P&L by one exit price: %s.' % (
        money(t['entry_fees']), money(t['exit_fees']), money(t['max_residual'])))
    L.append('')
    L.append('## Losers by primary class (dollars go to one class only)')
    L.append('')
    L.append('| Class | Trips | Dollars |')
    L.append('| --- | --- | --- |')
    for c in sorted(t['classes'], key=lambda c: c['dollars']):
        L.append('| %s | %d | %s |' % (c['class'], c['trips'], money(c['dollars'])))
    L.append('| all losers | %d | %s |' % (t['losers'], money(t['loser_dollars'])))
    for title, key in (('price bucket (side price paid)', 'by_price'), ('exit event', 'by_exit'), ('coin', 'by_coin'), ('contract kind', 'by_kind')):
        L.append('')
        L.append('## Fees on every trip, by ' + title)
        L.append('')
        L.append('| Group | Trips | Staked | Fees | Fee share of stake | Gross per contract | Net per contract |')
        L.append('| --- | --- | --- | --- | --- | --- | --- |')
        for r in t[key]:
            L.append('| %s | %d | %s | %s | %s | %s | %s |' % (
                r['group'], r['trips'], money(r['cost']), money(r['fees']), pct(r['fee_share']),
                '-' if r['gross_per_contract'] is None else '%.1fc' % (100 * r['gross_per_contract']),
                '-' if r['net_per_contract'] is None else '%.1fc' % (100 * r['net_per_contract'])))
    L.append('')
    L.append('## Input checks')
    L.append('')
    L.append('- count x price paid does not explain the stake on %d trips; a NO buy not priced at 1 minus the YES-terms price on %d.' % (len(stake_bad), len(no_bad)))
    L.append('')
    return '\n'.join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('trips')
    ap.add_argument('--out', default='.')
    a = ap.parse_args(argv)
    with open(a.trips, newline='', encoding='utf-8') as fh:
        rows = list(csv.DictReader(fh))
    cl = [triage.classify(r) for r in rows]
    t = ledger.summarize(rows, cl)
    stake_bad, no_bad = ledger.check_stake(rows), ledger.check_no_price(rows)
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, 'triage.csv'), 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        w.writerow(['ticker', 'entry_utc', 'pnl', 'class', 'tags', 'gross', 'entry_fee', 'exit_fee', 'fees', 'fee_share', 'cost', 'exit_px', 'residual'])
        for r, c in zip(rows, cl):
            w.writerow([r.get('ticker'), r.get('entry_utc'), r.get('pnl'), c['primary'], ' '.join(c['tags'])] +
                       ['' if c.get(k) is None else round(c[k], 4) for k in ('gross', 'entry_fee', 'exit_fee', 'fees', 'fee_share', 'cost', 'exit_px', 'residual')])
    md = render(t, stake_bad, no_bad)
    with open(os.path.join(a.out, 'report.md'), 'w', encoding='utf-8') as fh:
        fh.write(md)
    print(md)
    return 0


if __name__ == '__main__':
    sys.exit(main())
