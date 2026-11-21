import unittest

import numpy as np

from subminute import maker as MK


def window(trades, bid=0.70, ask=0.72, bsz=10.0, asz=6.0, result=1.0):
    """One window: a constant book and a list of trades (ms, price, count, side)."""
    a = np.array(trades, float).reshape(-1, 4)
    return {'bid': np.full((1, 900), bid), 'ask': np.full((1, 900), ask), 'bsz': np.full((1, 900), bsz), 'asz': np.full((1, 900), asz),
            'result': np.array([result]), 'z': {}, 'trades': [(a[:, 0].astype(np.int64), a[:, 1], a[:, 2], a[:, 3].astype(np.int8))]}


YES = ('yes', (0.6, 0.8), (60, 180), 900, 'pess', None)


class MakerTest(unittest.TestCase):
    def test_a_trade_through_the_price_fills_us(self):
        pr = window([(101500, 0.70, 5, -1), (120000, 0.70, 8, -1), (200000, 0.69, 1, -1)])
        o = MK.simulate(pr, YES)
        self.assertEqual(o[0], 1)
        self.assertEqual(o[1], 1)                               # 13 at the price is not enough behind 10 + 14, but the .69 trade means our level was cleared
        self.assertAlmostEqual(o[2], 0.30)                      # settles yes: 1 - 0.70, no maker fee
        self.assertLess(o[3], o[2])                             # the stress fee takes something

    def test_the_queue_assumption_matters(self):
        pr = window([(110000, 0.70, 20, -1)])
        self.assertEqual(MK.simulate(pr, YES)[1], 0)            # 20 < 10 ahead + 14 of ours
        self.assertEqual(MK.simulate(pr, ('yes', (0.6, 0.8), (60, 180), 900, 'opt', None))[1], 1)   # first in line: 20 >= 14

    def test_cancel_before_the_trade_and_no_trades_before_placement(self):
        pr = window([(300000, 0.69, 1, -1)])
        self.assertEqual(MK.simulate(pr, ('yes', (0.6, 0.8), (60, 180), 240, 'pess', None))[1], 0)    # cancelled at 240 s
        pr2 = window([(50000, 0.69, 1, -1)])
        self.assertEqual(MK.simulate(pr2, YES)[1], 0)           # it happened before the order was there

    def test_no_side_mirrors_it(self):
        # NO bid = 1 - ask = 0.28; taker buys of YES at 0.72 use its level up, a buy above 0.72 clears it
        pr = window([(130000, 0.73, 1, 1)], bid=0.26, ask=0.72, asz=4.0, result=0.0)
        o = MK.simulate(pr, ('no', (0.2, 0.4), (60, 180), 900, 'pess', None))
        self.assertEqual((o[0], o[1]), (1, 1))
        self.assertAlmostEqual(o[2], 1 - 0.28)                  # NO wins when YES settles 0

    def test_judge_runs(self):
        acc = {r: {0: np.array([10, 5, 0.5, 0.4, 0.8, 3.0]), 1: np.array([10, 4, -0.2, -0.3, 0.1, 2.4])} for r in MK.rules()[:40]}
        j = MK.judge(acc, {0}, {1})
        self.assertIn('pess', j)
        self.assertEqual(len(MK.rules()), 360)


if __name__ == '__main__':
    unittest.main()
