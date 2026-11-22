import os
import tempfile
import unittest

import numpy as np

from subminute import ladder_arb as LA

W = 3600


def book(m):
    return {k: np.full((m, W), np.nan) for k in ('bid', 'ask')}, {k: np.zeros((m, W)) for k in ('bsz', 'asz')}


class LadderArb(unittest.TestCase):
    def test_no_cross_when_monotone(self):
        q, s = book(3)
        for i, (b, a) in enumerate(((0.70, 0.72), (0.50, 0.52), (0.30, 0.32))):
            q['bid'][i], q['ask'][i], s['bsz'][i], s['asz'][i] = b, a, 20, 20
        r = LA.scan_hour(q['bid'], q['ask'], s['bsz'], s['asz'])
        self.assertTrue(r['two'].all())
        self.assertEqual(int(r['crossed'].sum()), 0)

    def test_planted_cross_and_fees(self):
        q, s = book(2)
        q['bid'][0], q['ask'][0], s['bsz'][0], s['asz'][0] = 0.40, 0.50, 20, 20          # lower strike: ask 0.50
        q['bid'][1], q['ask'][1], s['bsz'][1], s['asz'][1] = 0.60, 0.65, 20, 20          # higher strike: bid 0.60 > 0.50
        q['bid'][1, 100:110] = 0.45                                                        # crossed for 100 s, then no longer
        r = LA.scan_hour(q['bid'], q['ask'], s['bsz'], s['asz'])
        self.assertEqual(int(r['crossed'][:100].sum()), 100)
        self.assertEqual(int(r['crossed'][110:].sum()), 3490)
        self.assertAlmostEqual(float(r['best_gap'][0]), 0.10, places=9)
        n = r['n'][0]
        self.assertEqual(n, 11.0)                       # floor($10 / 0.90) pairs, 20 contracts shown
        self.assertGreater(r['fee'][0], 0.0)
        self.assertAlmostEqual(float(r['net'][0]), float(n * 0.10 - r['fee'][0]), places=9)

    def test_small_gap_dies_on_fees(self):
        q, s = book(2)
        q['bid'][0], q['ask'][0], s['bsz'][0], s['asz'][0] = 0.40, 0.50, 50, 50
        q['bid'][1], q['ask'][1], s['bsz'][1], s['asz'][1] = 0.51, 0.55, 50, 50           # one cent crossing
        r = LA.scan_hour(q['bid'], q['ask'], s['bsz'], s['asz'])
        self.assertTrue(r['crossed'].all())
        self.assertTrue((r['net'] < 0).all())

    def test_size_below_one_contract_is_no_quote(self):
        q, s = book(2)
        q['bid'][0], q['ask'][0], s['bsz'][0], s['asz'][0] = 0.40, 0.50, 0.5, 0.5
        q['bid'][1], q['ask'][1], s['bsz'][1], s['asz'][1] = 0.60, 0.65, 20, 20
        r = LA.scan_hour(q['bid'], q['ask'], s['bsz'], s['asz'])
        self.assertEqual(int(r['two'].sum()), 0)

    def test_day_stats_and_run(self):
        m = 3
        ticks = np.array([f'T{i}' for i in range(m)])
        strike = np.array([100.0, 110.0, 120.0])
        open_ms = np.zeros(m, np.int64) + 3_600_000
        q, s = book(m)
        for i, (b, a) in enumerate(((0.70, 0.72), (0.50, 0.52), (0.30, 0.32))):
            q['bid'][i], q['ask'][i], s['bsz'][i], s['asz'][i] = b, a, 20, 20
        q['bid'][2, 200:203], q['ask'][2, 200:203] = 0.80, 0.85                              # K=120 bid above K=100 ask for 3 seconds
        with tempfile.TemporaryDirectory() as d:
            np.savez_compressed(os.path.join(d, 'grid-2026-11-11.npz'), **{'BTC__tickers': ticks, 'BTC__strike': strike, 'BTC__open_ms': open_ms,
                                                                           'BTC__bid': q['bid'], 'BTC__ask': q['ask'], 'BTC__bsz': s['bsz'], 'BTC__asz': s['asz']})
            out = os.path.join(d, 'out')
            r = LA.run(d, out, coins=('BTC',))
            e = r['coins']['BTC']
            self.assertEqual(e['crossed_seconds'], 3)
            self.assertEqual(e['episodes'], 1)
            self.assertEqual(e['same_market_crossed_seconds'], 0)
            self.assertEqual(e['episodes_with_a_next_second'], 1)
            self.assertTrue(os.path.exists(os.path.join(out, 'ladder_arb.json')))


if __name__ == '__main__':
    unittest.main()
