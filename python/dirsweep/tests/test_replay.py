import unittest

import numpy as np

from dirsweep import grid as G
from dirsweep import hist as H
from dirsweep import replay as R
from dirsweep.tests.util import make_grid

ND = 6


class ReplayTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = make_grid(ND, seed=5, reversal=0.12)
        cls.arr = H.cell_arrays(cls.m, 0.01, 15, nd=ND, day_off=0)

    def test_lockout_keeps_the_first_row_of_a_burst(self):
        keep = R.lockout(np.array([0, 5, 14, 15, 16, 40, 41, 55]), 15)
        self.assertEqual(keep.tolist(), [0, 15, 40, 55])
        self.assertTrue((np.diff(keep) >= 15).all())
        self.assertEqual(R.lockout(np.array([], dtype=int), 15).tolist(), [])

    def test_replay_without_lockout_equals_the_sweep_histogram(self):
        picks = [(5, 0, 0, 0, 0), (5, 4, 0, 0, 0), (2, 3, 2, 3, 4), (1, 5, 3, 2, 1), (7, 2, 1, 0, 3)]
        for p in picks:
            cell = G.cell(*p)
            for side in (0, 1):
                out = R.replay(self.m, 0.01, 2 * cell + side, 0, ND, minutes=1, nd=ND)
                self.assertTrue((out['calls'] == self.arr['ncall'][cell]).all(), (p, side))
                self.assertTrue((out['decided'] == self.arr['ndec'][cell]).all(), (p, side))
                want = self.arr['cf'][cell] if side == 0 else self.arr['ndec'][cell] - self.arr['cf'][cell]
                self.assertTrue((out['right'] == want).all(), (p, side))

    def test_lockout_only_removes_calls_and_calls_are_fifteen_minutes_apart(self):
        rid = 2 * G.cell(1, 0, 0, 0, 0)                      # k=2, no filters: a call almost every minute
        free = R.replay(self.m, 0.01, rid, 0, ND, minutes=1, nd=ND)
        locked = R.replay(self.m, 0.01, rid, 0, ND, minutes=15, nd=ND)
        self.assertTrue((locked['calls'] <= free['calls']).all())
        self.assertLess(locked['calls'].sum(), free['calls'].sum() / 5)
        rows, _, _ = R.rule_rows(self.m, rid, nd=ND)
        self.assertTrue((np.diff(R.lockout(rows, 15)) >= 15).all())

    def test_window_selects_days(self):
        rid = 2 * G.cell(5, 0, 0, 0, 0)
        whole = R.replay(self.m, 0.01, rid, 0, ND, nd=ND)
        part = R.replay(self.m, 0.01, rid, 2, 4, nd=ND)
        self.assertTrue((part['calls'] == whole['calls'][2:4]).all())


if __name__ == '__main__':
    unittest.main()
