import math
import unittest

import numpy as np

from dirsweep import grid as G
from dirsweep import kfair as KF
from dirsweep.tests.test_kscore import windows
from dirsweep.tests.util import make_grid


class FairTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = make_grid(5, seed=3)
        cls.w = windows(cls.m)
        cls.w.strike[:] = np.asarray(cls.m['o'], float)[(cls.w.open_ms - cls.m['t0']) // G.MIN]     # strike = the coin at the window open

    def test_phi(self):
        self.assertAlmostEqual(float(KF.phi(np.array([0.0]))[0]), 0.5)
        self.assertAlmostEqual(float(KF.phi(np.array([1.959963984540054]))[0]), 0.975, places=6)
        self.assertTrue(np.isnan(KF.phi(np.array([np.nan]))[0]))

    def test_model_moves_with_spot_against_strike(self):
        js, pm = KF.model(self.m, self.w, 0)
        self.assertEqual(len(js), len(self.w))
        self.assertTrue(np.isnan(pm[:, 0]).all())
        o = np.asarray(self.m['o'], float)
        e0 = (self.w.open_ms[js] - self.m['t0']) // G.MIN
        ok = np.isfinite(pm[:, 10])
        self.assertGreater(ok.sum(), 100)
        above = o[e0 + 10] > self.w.strike[js]
        self.assertTrue((pm[ok & above, 10] > 0.5).all() and (pm[ok & ~above, 10] < 0.5).all())

    def test_logistic_recovers_a_planted_law(self):
        rng = np.random.default_rng(1)
        x = rng.standard_normal((20000, 2))
        y = (rng.random(20000) < 1 / (1 + np.exp(-(0.3 + 1.2 * x[:, 0] - 0.5 * x[:, 1])))).astype(float)
        b = KF.fit_logistic(x, y)
        self.assertTrue(np.allclose(b, [0.3, 1.2, -0.5], atol=0.08))

    def test_no_trade_when_the_edge_is_out_of_reach_and_trades_are_priced(self):
        full, per = KF.model_all({'BTC': self.m}, self.w)
        js, pm = per['BTC']
        self.assertEqual(len(KF.trade(self.w, pm, 5, 9, 0.99)['net']), 0)
        t = KF.trade(self.w, pm, 5, 9, 0.02)
        self.assertGreater(len(t['net']), 10)
        self.assertTrue(((t['p'] > 0) & (t['p'] < 1)).all())
        self.assertTrue((t['net'] < 1 - t['p']).all() and (t['net'] > -t['p'] - 0.05).all())       # a win pays 1, a loss costs the price; the fee is a few cents
        res = KF.run({'BTC': self.m}, self.w, int(self.w.open_ms[len(self.w) // 2]), {'all': (0, 10 ** 15)}, ranges=((5, 9),), edges=(0.05,))
        self.assertIn('k5-9_edge0.05', res['trading'])
        self.assertIn('k5-9', res['information'])


if __name__ == '__main__':
    unittest.main()
