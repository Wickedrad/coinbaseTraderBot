import unittest

import numpy as np

from subminute import lag as LG

DAY0 = 1_700_006_400_000


def fake(jump_at=100, lag=2, n_windows=2):
    """A coin whose index jumps up 0.05% at second `jump_at` of every window and whose book follows `lag` seconds later."""
    rng = np.random.default_rng(3)
    idx = 100000.0 * np.exp(np.cumsum(rng.normal(0, 1e-5, LG.DAY)))
    opens = [3600 + 1800 * i for i in range(n_windows)]
    bid, ask = np.full((n_windows, LG.WIN), 0.49), np.full((n_windows, LG.WIN), 0.51)
    for i, o in enumerate(opens):
        idx[o + jump_at:] *= 1.0005
        bid[i, jump_at + lag:], ask[i, jump_at + lag:] = 0.59, 0.61
    return {'BTC__open_ms': DAY0 + 1000 * np.array(opens, np.int64), 'BTC__idx': idx, 'BTC__bid': bid, 'BTC__ask': ask, 'BTC__result': np.ones(n_windows)}


class LagTest(unittest.TestCase):
    def test_late_book_pays_the_follower_and_not_the_flip(self):
        pr = LG.prep(fake(), 'BTC', DAY0)
        t = LG.trades(pr, 1, 6.0, 30, 300, 10, 1)
        rows, net_sold, net_held, p = t['follow']
        self.assertEqual(len(rows), 2)
        self.assertTrue((net_sold > 0.03).all() and (net_sold < 0.08).all())      # 8c of move, about 3.5c of two taker fees
        self.assertAlmostEqual(float(p[0]), 0.51)
        self.assertAlmostEqual(float(net_held[0]), 1 - 0.51 - 0.0179, places=2)
        self.assertTrue((t['flip'][1] < -0.1).all())

    def test_a_book_that_keeps_up_pays_nothing(self):
        pr = LG.prep(fake(lag=0), 'BTC', DAY0)
        t = LG.trades(pr, 1, 6.0, 30, 300, 10, 1)             # the entry second already shows the new quote
        self.assertTrue((t['follow'][1] < 0.0).all())

    def test_sweep_judge_and_information_run(self):
        pr = LG.prep(fake(n_windows=3), 'BTC', DAY0)
        acc = LG.sweep([(0, pr), (1, pr)])
        self.assertTrue(len(acc) > 0)
        j = LG.judge(acc, {0}, {1})
        self.assertIn('sold', j)
        self.assertIn('held', j)
        inf = LG.information([(0, pr), (1, pr)], {0}, {1})
        self.assertIn('L1_H2', inf)

    def test_pooled(self):
        days = {0: [2, 0.10, 2, 0.20, 1.0], 1: [2, -0.02, 2, 0.0, 1.0], 2: [1, 0.05, 1, 0.1, 0.5]}
        m, se, n, nd, pos = LG.pooled(days, 0, {0, 1, 2})
        self.assertAlmostEqual(m, 0.13 / 5)
        self.assertEqual((n, nd, pos), (5, 3, 2))
        self.assertIsNotNone(se)
        self.assertEqual(LG.pooled(days, 0, set())[2], 0)

    def test_ffill(self):
        x = np.array([np.nan, 1.0, np.nan, np.nan, 2.0, np.nan])
        y = LG.ffill(x)
        self.assertTrue(np.isnan(y[0]))
        self.assertEqual(y.tolist()[1:], [1.0, 1.0, 1.0, 2.0, 2.0])


if __name__ == '__main__':
    unittest.main()
