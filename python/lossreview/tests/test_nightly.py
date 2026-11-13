import json
import os
import tempfile
import time
import unittest

from lossreview import fees, nightly
from lossreview.tests import test_builder as tb


def line(t, kind, data, seq):
    return json.dumps({'seq': seq, 'ts': time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(t)) + '.%03dZ' % int((t % 1) * 1000), 'kind': kind, 'data': data}, separators=(',', ':'))


class NightlyTests(unittest.TestCase):
    def test_a_day_end_to_end_without_the_network(self):
        ef, xf = fees.taker_fee(20, 0.50), fees.taker_fee(20, 0.62)
        pnl = round(20 * 0.12 - ef - xf, 6)
        recs = [tb.heat_entry(0), tb.fill(1, 'bid', 0.50, 20), tb.plan_event(300, 'plan_ratchet_sell', 0.62),
                tb.fill(302, 'ask', 0.62, 20, coid='c2'), tb.closed(310, 'yes', pnl),
                # noise kinds the reader must skip
                (tb.T0 + 5, 'tick', {'x': 1}, 0)]
        with tempfile.TemporaryDirectory() as d:
            ad, od = os.path.join(d, 'audit'), os.path.join(d, 'out')
            os.makedirs(ad)
            with open(os.path.join(ad, 'audit-2026-11-12.jsonl'), 'w') as fh:
                for i, (t, k, data, _s) in enumerate(sorted(recs, key=lambda r: r[0])):
                    fh.write(line(t, k, data, i) + '\n')
            rows, s = nightly.run('2026-11-12', ad, od, net=False)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['class'], 'WIN')
            self.assertEqual(s['trips'], 1)
            self.assertEqual(s['defect_sales'], 0)
            for f in ('trips-2026-11-12.jsonl', 'agg-2026-11-12.json', 'report-2026-11-12.md'):
                self.assertTrue(os.path.exists(os.path.join(od, f)), f)
            # the aggregate files carry no ticker
            for f in ('agg-2026-11-12.json', 'report-2026-11-12.md'):
                self.assertNotIn('KXBTC', open(os.path.join(od, f)).read(), f)
            # the per-trade file does
            self.assertIn('KXBTC', open(os.path.join(od, 'trips-2026-11-12.jsonl')).read())

    def test_trips_closed_on_another_day_are_left_out(self):
        recs = [tb.heat_entry(0), tb.fill(1, 'bid', 0.50, 20), tb.fill(100, 'ask', 0.55, 20, coid='c2'), tb.closed(110, 'yes', 0.5)]
        with tempfile.TemporaryDirectory() as d:
            ad = os.path.join(d, 'audit')
            os.makedirs(ad)
            with open(os.path.join(ad, 'audit-2026-11-12.jsonl'), 'w') as fh:
                for i, (t, k, data, _s) in enumerate(sorted(recs, key=lambda r: r[0])):
                    fh.write(line(t, k, data, i) + '\n')
            rows, s = nightly.run('2026-11-13', ad, os.path.join(d, 'out'), net=False)
            self.assertEqual(rows, [])


if __name__ == '__main__':
    unittest.main()
