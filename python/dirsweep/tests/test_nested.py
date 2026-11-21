import unittest

import numpy as np

from dirsweep import grid as G
from dirsweep import infer as I
from dirsweep import nested as N

NB, BD = 14, 30                                   # 14 blocks of 30 days
BLOCKS = [(i * BD, (i + 1) * BD) for i in range(NB)]
ND = NB * BD
NC = 60
NACT = np.zeros(NC, int)
NACT[10:] = 1
NACT[30:] = 2
BENCH = [0, 1, 2]


def arrays(seed=1, planted=None, p_planted=0.58, rate=30):
    rng = np.random.default_rng(seed)
    n = rng.poisson(rate, size=(NC, ND)).astype(np.int32)
    p = np.full(NC, 0.5)
    if planted is not None:
        p[planted] = p_planted
    c = rng.binomial(n, p[:, None]).astype(np.int32)
    return n, c


class NestedTest(unittest.TestCase):
    def run_it(self, n, c):
        return N.run_nested(n, c, BLOCKS, NACT, BENCH)

    def test_a_planted_rule_is_found_and_scored_out_of_sample(self):
        n, c = arrays(1, planted=37)
        out = self.run_it(n, c)
        self.assertEqual({f['rid'] for f in out['folds']}, {74})
        self.assertGreater(out['pooled']['hit'], 0.56)
        self.assertEqual(len(out['folds']), 10)

    def test_a_follow_rule_is_found_as_the_follow_side(self):
        n, c = arrays(2)
        c = c.copy()
        c[20] = n[20] - np.random.default_rng(3).binomial(n[20], 0.6).astype(np.int32)       # fade right 40% -> follow right 60%
        out = self.run_it(n, c)
        self.assertEqual({f['rid'] for f in out['folds']}, {41})

    def test_nothing_planted_gives_a_hit_near_half(self):
        hits = []
        for seed in range(5):
            n, c = arrays(100 + seed)
            out = self.run_it(n, c)
            hits.append(out['pooled']['hit'])
        self.assertTrue(all(0.485 < h < 0.515 for h in hits), hits)

    def test_the_choice_never_sees_the_purged_day_or_the_test_block(self):
        n, c = arrays(4)
        base = self.run_it(n, c)
        n2, c2 = n.copy(), c.copy()
        for f in base['folds']:
            lo, hi = f['test_days']
            n2[55, lo - 1:hi], c2[55, lo - 1:hi] = 400, 400            # a perfect decoy from the purged day on: must not change that fold's pick
        alt = self.run_it(n2, c2)
        for a, b in zip(base['folds'], alt['folds']):
            if b['block'] == 4:
                self.assertEqual(a['rid'], b['rid'])
        # the decoy on the purged day alone (no test-block days) cannot change fold 4
        n3, c3 = n.copy(), c.copy()
        lo4 = BLOCKS[4][0]
        n3[55, lo4 - 1], c3[55, lo4 - 1] = 10_000, 10_000
        alt3 = self.run_it(n3, c3)
        self.assertEqual(base['folds'][0]['rid'], alt3['folds'][0]['rid'])
        self.assertEqual(base['folds'][0]['train_days'], [0, lo4 - 1])

    def test_tie_goes_to_fewer_active_filters_then_rule_id(self):
        n = np.full((NC, ND), 20, np.int32)
        c = np.full((NC, ND), 12, np.int32)                           # every cell identical: 60% fade
        out = self.run_it(n, c)
        self.assertTrue(all(f['rid'] == 0 for f in out['folds']))
        sc = np.full((NC, 2), 0.1)
        sc[5, 0] = sc[40, 0] = sc[12, 1] = 0.2
        rid, _ = N.pick(sc, NACT)
        self.assertEqual(rid, 10)                                       # cell 5 (0 filters), fade
        sc[5, 0] = 0.1
        rid, _ = N.pick(sc, NACT)
        self.assertEqual(rid, 25)                                       # cell 12 follow (1 filter) beats cell 40 fade (2 filters)

    def test_a_rule_below_three_calls_a_day_is_not_eligible(self):
        n, c = arrays(5, planted=7, rate=2)
        st = I.window_stats(n, c, 0, 100)
        self.assertTrue(np.isinf(N.rule_scores(st)).all())

    def test_the_freeze_uses_every_block_and_reports_the_blocks(self):
        n, c = arrays(6, planted=33)
        fr = N.freeze(n, c, BLOCKS, NACT, coins={'X': (n, c)})
        self.assertEqual(fr['rid'], 66)
        self.assertEqual(len(fr['by_block']), 14)
        self.assertGreater(fr['calls_per_day'], 20)
        self.assertEqual(len(fr['top']), 10)

    def test_the_benchmark_is_an_unfiltered_cell(self):
        n, c = arrays(7, planted=33)
        out = self.run_it(n, c)
        self.assertTrue(all(f['bench_rid'] // 2 in BENCH for f in out['folds']))
        self.assertIn('bench_pooled', out)


class InferTest(unittest.TestCase):
    def test_cluster_se_matches_the_ratio_formula(self):
        rng = np.random.default_rng(1)
        n = rng.integers(5, 30, size=(1, 80)).astype(float)
        r = rng.binomial(n.astype(int), 0.55).astype(float)
        N_, C_, p, se = I.ratio_se(n, r)
        res = r[0] - (r.sum() / n.sum()) * n[0]
        want = np.sqrt(80 / 79 * (res ** 2).sum()) / n.sum()
        self.assertAlmostEqual(float(se[0]), want, places=12)

    def test_reality_check_rejects_a_real_edge_and_not_noise(self):
        n, c = arrays(8)
        noise = I.reality_check(n, c, n_boot=300)
        self.assertGreater(noise['p'], 0.05)
        n, c = arrays(8, planted=12, p_planted=0.54)
        real = I.reality_check(n, c, n_boot=300)
        self.assertLess(real['p'], 0.05)
        self.assertEqual(real['cell'], 12)

    def test_stationary_bootstrap_blocks(self):
        idx = I.stationary_indices(np.random.default_rng(2), 50, 400, 5.0)
        self.assertEqual(idx.shape, (50, 400))
        self.assertTrue(((idx >= 0) & (idx < 400)).all())
        steps = (np.diff(idx, axis=1) % 400 == 1)
        self.assertAlmostEqual(float(steps.mean()), 0.8, delta=0.03)       # a block continues with probability 1 - 1/5

    def test_paired_bootstrap(self):
        n, c = arrays(9, planted=3, p_planted=0.56)
        a = I.paired_bootstrap(n[3], c[3], n[4], c[4], n_boot=400)
        self.assertGreater(a['diff'], 0.03)
        self.assertGreater(a['lb90'], 0.0)
        b = I.paired_bootstrap(n[4], c[4], n[5], c[5], n_boot=400)
        self.assertLess(abs(b['diff']), 0.03)

    def test_pbo_low_for_a_stable_edge_and_about_half_for_noise(self):
        n, c = arrays(10)
        noise = I.pbo(n, c, BLOCKS)
        self.assertEqual(noise['splits'], 3432)
        self.assertTrue(0.25 < noise['pbo'] < 0.75, noise)
        n, c = arrays(10, planted=9, p_planted=0.56)
        edge = I.pbo(n, c, BLOCKS)
        self.assertLess(edge['pbo'], 0.1, edge)


class VerdictTest(unittest.TestCase):
    def test_thresholds(self):
        n, c = arrays(1, planted=37, p_planted=0.60)
        nested = N.run_nested(n, c, BLOCKS, NACT, BENCH)
        fr = N.freeze(n, c, BLOCKS, NACT)
        v = N.verdict(nested, fr, {'p': 0.01}, {'pbo': 0.1}, {'diff': 0.05, 'lb90': 0.01})
        self.assertTrue(v['E1'] and v['E2'] and v['E3'] and v['E4'] and v['E5'] and v['E6'] and v['E8'])
        v = N.verdict(nested, fr, {'p': 0.2}, {'pbo': 0.5}, {'diff': 0.005, 'lb90': 0.01})
        self.assertFalse(v['E4'] or v['E5'] or v['E6'] or v['all_but_E7'])


if __name__ == '__main__':
    unittest.main()
