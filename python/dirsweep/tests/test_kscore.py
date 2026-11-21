import unittest

import numpy as np

from allpairs import data as KD
from allpairs import fees as KF
from dirsweep import grid as G
from dirsweep import kscore as K
from dirsweep.tests.util import make_grid

ND = 4


def windows(grid, bid=0.49, ask=0.51, settle=1.0, drop_every=0):
    nw = grid['n'] // 15
    opens = grid['t0'] + np.arange(nw, dtype=np.int64) * 15 * G.MIN
    if drop_every:
        opens = opens[np.arange(nw) % drop_every != 0]
    W = len(opens)
    full = lambda v: np.full((W, 15), v)
    return KD.Windows(15, np.zeros(W, np.int16), ['BTC'], opens, np.full(W, 100.0), np.full(W, settle), full(bid), full(ask), full(np.nan), full(np.nan),
                      full(np.nan), full(np.nan), np.zeros((W, 15)), np.ones(W), np.zeros(W, bool), [], np.zeros(W, np.int16))


class KscoreTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = make_grid(ND, seed=5, reversal=0.12)
        cls.rid = 2 * G.cell(1, 0, 0, 0, 0)                 # k = 2, no filters, any minute: a call at the first row after each lockout
        cls.hi = ND

    def test_calls_are_fifteen_minutes_apart_and_fade_the_last_move(self):
        cl = K.calls(self.m, 'BTC', self.rid, 0, self.hi)
        self.assertGreater(len(cl['t']), 50)
        self.assertTrue((np.diff(cl['t']) >= 15 * G.MIN).all())
        o = self.m['o']
        e = ((cl['t'] - self.m['t0']) // G.MIN).astype(int)
        last = o[e] - o[e - 2]
        self.assertTrue((cl['side'] == -np.sign(last)).all())
        fol = K.calls(self.m, 'BTC', self.rid + 1, 0, self.hi)
        self.assertTrue((fol['side'] == -cl['side']).all())

    def test_price_takes_the_ask_of_the_called_side_at_the_first_minute_with_a_book(self):
        w = windows(self.m)
        idx = K.index(w)
        cl = K.calls(self.m, 'BTC', self.rid, 0, self.hi)
        pr = K.price(w, idx, 'BTC', cl)
        self.assertEqual(int(pr['ok'].sum()), len(cl['t']))
        self.assertTrue(np.allclose(pr['p'], 0.51))                        # YES ask 0.51, NO ask 1 - 0.49
        up = cl['side'] > 0
        self.assertTrue((pr['win'][up] == 1).all() and (pr['win'][~up] == 0).all())      # the window settled YES
        cnt = np.floor(10 / 0.51)
        fee = float(KF.taker_fee(cnt, 0.51)) / cnt
        x = K.net(pr)
        self.assertTrue(np.allclose(x[up], 1 - 0.51 - fee) and np.allclose(x[~up], -0.51 - fee))

    def test_flipped_side_and_missing_windows_and_late_entry(self):
        w = windows(self.m, drop_every=2)
        idx = K.index(w)
        cl = K.calls(self.m, 'BTC', self.rid, 0, self.hi)
        pr = K.price(w, idx, 'BTC', cl)
        self.assertLess(int(pr['ok'].sum()), len(cl['t']))
        self.assertGreater(int(pr['ok'].sum()), 0)
        late = K.price(windows(self.m), idx, 'BTC', cl, delay=14)         # k = max(mq, 1) + 14 >= 15: never priced
        self.assertEqual(int(late['ok'].sum()), 0)
        res = K.run({'BTC': self.m}, windows(self.m), self.rid, 0, self.hi, delays=(0,), seeds=3)
        d = res['by_delay']['0']
        self.assertAlmostEqual(d['pooled']['hit'] + d['flipped']['hit'], 1.0)
        self.assertEqual(d['pooled']['priced'], d['pooled']['calls'])
        self.assertLess(d['pooled']['net_c'], 0.0 + 100 * (1 - 0.51))

    def test_a_quote_without_a_book_is_not_traded(self):
        w = windows(self.m)
        w.ask[:, :] = np.nan
        cl = K.calls(self.m, 'BTC', self.rid, 0, self.hi)
        self.assertEqual(int(K.price(w, K.index(w), 'BTC', cl)['ok'].sum()), 0)


if __name__ == '__main__':
    unittest.main()
