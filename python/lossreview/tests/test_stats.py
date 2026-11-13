import random
import unittest

from lossreview import stats


class StatsTests(unittest.TestCase):
    def test_t_tail_known_values(self):
        self.assertAlmostEqual(stats.t_sf(0.0, 5), 0.5, places=9)
        self.assertAlmostEqual(stats.t_sf(1.0, 1), 0.25, places=9)            # Cauchy
        self.assertAlmostEqual(stats.t_sf(2.776445, 4), 0.025, places=5)
        self.assertAlmostEqual(stats.t_sf(2.015048, 5), 0.05, places=5)
        self.assertAlmostEqual(stats.t_sf(-2.015048, 5), 0.95, places=5)
        self.assertAlmostEqual(stats.t_sf(1.96, 100000), 0.025, places=3)     # the normal in the limit
        self.assertEqual(stats.t_sf(float('inf'), 3), 0.0)

    def test_bh(self):
        p = [0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205, 0.212, 0.216]
        self.assertEqual(stats.bh(p, q=0.05), [0, 1])
        # untested trials count as p = 1 and make the cut harder
        self.assertEqual(stats.bh([0.004], q=0.05), [0])
        self.assertEqual(stats.bh([0.004], q=0.05, total=200), [])

    def test_placebo_moments_match_a_monte_carlo_draw(self):
        rnd = random.Random(3)
        g = {'a': [rnd.gauss(-0.2, 1.0) for _ in range(40)], 'b': [rnd.gauss(0.1, 2.0) for _ in range(25)]}
        n = {'a': 7, 'b': 5}
        mean, var = stats.placebo_moments(n, g)
        sums = [sum(rnd.sample(g['a'], 7)) + sum(rnd.sample(g['b'], 5)) for _ in range(40000)]
        m = sum(sums) / len(sums)
        v = sum((x - m) ** 2 for x in sums) / (len(sums) - 1)
        self.assertAlmostEqual(mean, m, delta=0.05)
        self.assertAlmostEqual(var, v, delta=0.6)

    def test_placebo_moments_draw_everything_when_n_exceeds_the_stratum(self):
        mean, var = stats.placebo_moments({'a': 10}, {'a': [1.0, 2.0, 3.0]})
        self.assertAlmostEqual(mean, 6.0)
        self.assertAlmostEqual(var, 0.0)

    def test_pooled_gap(self):
        r = stats.pooled_gap([1.0, 2.0, 3.0, 2.0, 2.0])
        self.assertEqual(r['days'], 5)
        self.assertAlmostEqual(r['mean'], 2.0)
        self.assertLess(r['p'], 0.01)
        self.assertIsNone(stats.pooled_gap([1.0])['p'])
        flat = stats.pooled_gap([0.5, 0.5, 0.5])
        self.assertEqual(flat['p'], 0.0)   # no spread and a positive mean: infinite t


if __name__ == '__main__':
    unittest.main()
