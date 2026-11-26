import unittest

import numpy as np

from allpairs import data as KD
from subminute import pockets as PK

DAY = 20_400                       # a UTC day number (days since 1970)


def windows(bid=0.55, ask=0.57, alo=None, bhi=None, settle=1.0, hour=2):
    n = 15
    nan = np.full((1, n), np.nan)
    b, a = np.full((1, n), bid), np.full((1, n), ask)
    b[0, 0] = a[0, 0] = np.nan                                  # no book at k = 0
    nbl, nbh, nal, nah = nan.copy(), nan.copy(), nan.copy(), nan.copy()
    for k, v in (alo or {}).items():
        nal[0, k] = v
    for k, v in (bhi or {}).items():
        nbh[0, k] = v
    return KD.Windows(n, np.zeros(1, np.int16), ['BTC'], np.array([(DAY * 24 + hour) * 3_600_000], np.int64), np.array([100.0]), np.array([settle]), b, a, nbl, nbh, nal, nah,
                      np.zeros((1, n)), np.ones(1), np.zeros(1, bool), ['KXBTC15M-X'], np.zeros(1, np.int16))


class PocketsTest(unittest.TestCase):
    def test_yes_order_and_its_two_fill_readings(self):
        w = windows(alo={3: 0.55})                              # the lowest ask of candle 4 touches our bid
        rows, k, p = PK.orders(w, 'yes', 0.5, 0.6, 1, 3)
        self.assertEqual((rows.tolist(), k.tolist(), p.tolist()), ([0], [1], [0.55]))
        self.assertTrue(PK.fills(w, 'yes', rows, k, p, 10, False)[0])             # touch
        self.assertFalse(PK.fills(w, 'yes', rows, k, p, 10, True)[0])             # not strictly through
        w2 = windows(alo={3: 0.54})
        self.assertTrue(PK.fills(w2, 'yes', rows, k, p, 10, True)[0])
        self.assertFalse(PK.fills(w2, 'yes', rows, k, p, 3, True)[0])             # cancelled before candle 4 closes (candles up to minute 3 only)

    def test_no_order_is_a_yes_sell_at_the_ask(self):
        w = windows(bhi={5: 0.57})
        rows, k, p = PK.orders(w, 'no', 0.4, 0.5, 1, 3)
        self.assertEqual(p.tolist(), [0.43])
        self.assertTrue(PK.fills(w, 'no', rows, k, p, 10, False)[0])
        self.assertFalse(PK.fills(w, 'no', rows, k, p, 10, True)[0])
        self.assertTrue(PK.fills(windows(bhi={5: 0.58}), 'no', rows, k, p, 10, True)[0])

    def test_no_fill_without_a_candle_and_no_order_outside_the_bucket(self):
        w = windows()
        rows, k, p = PK.orders(w, 'yes', 0.5, 0.6, 1, 3)
        self.assertFalse(PK.fills(w, 'yes', rows, k, p, 14, False)[0])
        self.assertEqual(len(PK.orders(w, 'yes', 0.6, 0.7, 1, 3)[0]), 0)

    def test_scan_sums_dollars_per_day_and_slices(self):
        w = windows(alo={3: 0.54}, settle=1.0, hour=14)
        acc = PK.scan(w, DAY, 1)
        cell = (('yes', (0.5, 0.6), (1, 3), 10), 'BTC', 2)                        # hour 14 is the third six-hour block
        A = acc[cell]
        self.assertEqual(A.shape, (1, PK.COLS))
        self.assertEqual(A[0, 0], 1.0)
        self.assertEqual(A[0, 4], 1.0)                                            # filled under 'thru'
        self.assertAlmostEqual(A[0, 5], 0.45)                                     # settles YES: 1 - 0.55, no maker fee
        self.assertAlmostEqual(A[0, 6], 0.45 * 18)                                # floor(10 / 0.55) = 18 contracts
        self.assertIn((cell[0], 'ALL', 'ALL'), acc)
        self.assertNotIn((cell[0], 'BTC', 0), acc)                                # nothing in the first block

    def test_ratio_and_per_hour(self):
        A = np.zeros((4, PK.COLS))
        A[:, 4] = [10, 10, 0, 10]
        A[:, 5] = [1.0, -0.2, 0.0, 0.5]
        m, se, D, nd, pos = PK.ratio(A, 5, 4, np.ones(4, bool))
        self.assertAlmostEqual(m, 1.3 / 30)
        self.assertEqual((D, nd, pos), (30.0, 3, 2))
        A[:, 6] = [24.0, 0.0, 0.0, 24.0]
        mph, se_ph = PK.per_hour(A, 6, np.ones(4, bool), np.ones(4, bool))
        self.assertAlmostEqual(mph, 0.5)


if __name__ == '__main__':
    unittest.main()
