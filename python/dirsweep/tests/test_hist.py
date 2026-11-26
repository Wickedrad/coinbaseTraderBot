import unittest

import numpy as np

from dirsweep import features as F
from dirsweep import grid as G
from dirsweep import hist as H
from dirsweep.tests.util import make_grid

ND = 6


def brute(m, step, h, ik, iz, ia, ir, ip, nd=ND):
    """The cell's per-day counts straight from the readings of one lookback."""
    k = G.K[ik]
    c = F.codes(m, k)
    n = m['n']
    o = np.asarray(m['o'])
    gap = np.asarray(m['gap'])
    out = {x: np.zeros(nd) for x in ('ncall', 'ndec', 'cf', 'sbps')}
    for e in range(n - h):
        if not c['ok'][e] or e + 60 >= n or gap[e + 1:e + 61].any():
            continue
        if c['zc'][e] < iz or c['ac'][e] < ia or c['rc'][e] < ir or (e % 60) % 15 not in G.PHASES[ip]:
            continue
        d = e // 1440
        if d >= nd:
            continue
        mv = (o[e + h] - o[e]) / step
        sg = int(c['sgn'][e])
        out['ncall'][d] += 1
        out['sbps'][d] += -sg * (o[e + h] - o[e]) / o[e] * 1e4
        if abs(mv) >= G.FLAT:
            out['ndec'][d] += 1
            if np.sign(mv) == -sg:
                out['cf'][d] += 1
    return out


class HistTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = make_grid(ND, seed=11, level=100.0)
        cls.m['gap'][3 * 1440 + 100:3 * 1440 + 130] = True
        cls.m['v'][3 * 1440 + 100:3 * 1440 + 130] = 0
        cls.m['tb'][3 * 1440 + 100:3 * 1440 + 130] = 0
        cls.arr = {h: H.cell_arrays(cls.m, 0.01, h, nd=ND, day_off=0) for h in (5, 15, 60)}

    def test_cells_equal_the_row_by_row_count(self):
        rng = np.random.default_rng(7)
        picks = [(0, 0, 0, 0, 0), (5, 0, 0, 0, 0), (5, 4, 0, 0, 0), (5, 6, 3, 0, 1), (2, 3, 2, 3, 4), (7, 8, 7, 6, 4), (1, 0, 5, 2, 2), (4, 2, 1, 1, 3)]
        picks += [(int(rng.integers(0, 8)), int(rng.integers(0, 9)), int(rng.integers(0, 8)), int(rng.integers(0, 7)), int(rng.integers(0, 5))) for _ in range(6)]
        for h in (5, 15, 60):
            for p in picks:
                want = brute(self.m, 0.01, h, *p)
                c = G.cell(*p)
                for x in ('ncall', 'ndec', 'cf'):
                    self.assertTrue((self.arr[h][x][c] == want[x]).all(), (h, p, x, self.arr[h][x][c], want[x]))
                self.assertTrue(np.allclose(self.arr[h]['sbps'][c], want['sbps'], atol=1e-3), (h, p))

    def test_fade_and_follow_right_counts_add_to_the_decided_count(self):
        a = self.arr[15]
        self.assertTrue((a['cf'] <= a['ndec']).all())
        self.assertTrue((a['ndec'] <= a['ncall']).all())

    def test_a_looser_filter_never_has_fewer_calls(self):
        a = self.arr[15]
        base = G.cell(5, 0, 0, 0, 0)
        for iz in range(1, G.NZ):
            self.assertTrue((a['ncall'][G.cell(5, iz, 0, 0, 0)] <= a['ncall'][G.cell(5, iz - 1, 0, 0, 0)]).all())
        self.assertTrue((a['ncall'][G.cell(5, 0, 0, 0, 1)] <= a['ncall'][base]).all())          # phase q0 within phase all

    def test_phase_sets_partition_correctly(self):
        a = self.arr[15]
        q0, q01, q014 = (a['ncall'][G.cell(5, 0, 0, 0, i)].sum() for i in (1, 2, 3))
        self.assertGreater(q01, q0)
        self.assertGreater(q014, q01)

    def test_nothing_is_counted_outside_the_window(self):
        m = make_grid(ND, seed=11, level=100.0)
        a = H.cell_arrays(m, 0.01, 15, nd=3, day_off=0)
        self.assertEqual(a['ncall'].shape, (G.N_CELLS, 3))
        full = self.arr[15]['ncall'][:, :3]
        self.assertTrue((a['ncall'] == full).all())


if __name__ == '__main__':
    unittest.main()
