import unittest

import numpy as np

from dirsweep import grid as G


class GridTest(unittest.TestCase):
    def test_sizes_are_the_preregistered_ones(self):
        self.assertEqual(G.N_RULES, 40320)
        self.assertEqual(G.N_CELLS, 20160)
        self.assertEqual(G.PER_K, 2520)
        self.assertEqual(G.ND, 2496)
        self.assertEqual((G.NZ, G.NA, G.NR, G.NP), (9, 8, 7, 5))

    def test_blocks_cover_the_search_days_exactly_once(self):
        b = G.block_days()
        self.assertEqual(len(b), 14)
        self.assertEqual(b[0][0], 0)
        self.assertEqual(b[-1][1], G.ND)
        for (a, c), (a2, _) in zip(b[:-1], b[1:]):
            self.assertEqual(c, a2)
            self.assertGreater(c, a)
        # the 14th block is 2026-07-01 .. 2026-10-31
        self.assertEqual(b[13][0], (G.ms('2026-07-01') - G.SEARCH_START) // G.DAY)
        self.assertEqual(b[12], ((G.ms('2026-01-01') - G.SEARCH_START) // G.DAY, (G.ms('2026-07-01') - G.SEARCH_START) // G.DAY))

    def test_periods(self):
        p = G.period_days()
        self.assertEqual(p['A'], (0, 1827))
        self.assertEqual(p['B'], (1827, 2192))
        self.assertEqual(p['C'], (2192, G.ND))

    def test_cell_roundtrip_and_describe(self):
        for c in (0, 1, 2519, 2520, 20159, 12345):
            self.assertEqual(G.cell(*G.unpack(c)), c)
        d = G.describe(2 * G.cell(5, 6, 3, 4, 2) + 1)
        self.assertEqual((d['side'], d['k'], d['z'], d['a'], d['r'], d['phase']), ('follow', 15, 2.0, 0.1, 1.5, 'q01'))
        d0 = G.describe(0)
        self.assertEqual((d0['side'], d0['k'], d0['z'], d0['a'], d0['r'], d0['phase']), ('fade', 1, 0.0, None, 0.0, 'all'))

    def test_every_rule_is_distinct(self):
        seen = {tuple(sorted(G.describe(r).items(), key=str)) for r in range(0, G.N_RULES, 7)}
        self.assertEqual(len(seen), len(range(0, G.N_RULES, 7)))

    def test_active_filters(self):
        self.assertEqual(int(G.n_active(0)[0]), 0)
        self.assertEqual(int(G.n_active(G.cell(0, 1, 0, 0, 0))[0]), 1)
        self.assertEqual(int(G.n_active(G.cell(3, 8, 7, 6, 4))[0]), 4)


if __name__ == '__main__':
    unittest.main()
