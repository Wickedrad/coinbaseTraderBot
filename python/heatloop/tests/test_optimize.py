import dataclasses
import unittest

import numpy as np

from heatloop import calls as C
from heatloop import guards
from heatloop import optimize as O
from heatloop.tests import test_evaluate as TE


def fake(total, lb, spec=None, eligible=True):
    spec = spec or O.ROUND0
    checks = [dict(passed=False, value=None) for _ in range(10)]
    checks[1]['value'] = lb
    return dict(total=total, checks=checks, eligible=eligible, spec=spec, hash=C.spec_hash(spec), hit_rate=0.5)


class Grid(unittest.TestCase):
    def test_trial_budget_is_the_frozen_604(self):
        self.assertEqual(sum(len(s(O.ROUND0)) for _, sw in O.PLAN for s in sw), 604)
        self.assertEqual(O.BUDGET, 604)
        sizes = [sum(len(s(O.ROUND0)) for s in sw) for _, sw in O.PLAN]
        self.assertEqual(sizes, [4, 240, 7, 55, 3, 295])

    def test_grid_values_are_exactly_the_amendment(self):
        g2 = O.g2(O.ROUND0)
        self.assertEqual({s.top_n for s in g2}, {5, 10, 20, 40, 80})
        self.assertEqual({s.min_share_A for s in g2}, {0, 52, 53, 54})
        self.assertEqual({s.min_n_B for s in g2}, {0, 5000, 10000})
        self.assertEqual({(s.combiner, s.vote_k, s.margin) for s in O.g3(O.ROUND0)},
                         {('hottest', 3, 1)} | {('vote', k, m) for k in (2, 3, 5) for m in (1, 2)})
        g4 = O.g4(O.ROUND0)
        self.assertEqual(len(g4), 55)
        self.assertEqual({(s.ta_confirm, s.ta_conf_k) for s in g4 if s.ta_confirm != 'none'},
                         {(m, k) for m in ('precedes', 'follows') for k in (5, 15, 30)})
        self.assertEqual({s.ta_inv_k for s in g4}, {0, 5, 15, 30})
        self.assertEqual({s.ta_pool for s in g4 if s.ta_confirm != 'none' or s.ta_inv_k}, {20, 40})
        self.assertEqual({s.lag for s in O.g5(O.ROUND0)}, {0, 1, 2})
        self.assertEqual({s.tfs for s in O.g1(O.ROUND0)}, {('1m',), ('5m',), ('1m', '5m'), O.ALL_TFS})

    def test_a_group_changes_only_its_own_fields(self):
        b = dataclasses.replace(O.ROUND0, top_n=40, lag=2, tfs=('5m',))
        for s in O.g4(b):
            self.assertEqual((s.top_n, s.lag, s.tfs), (40, 2, ('5m',)))
        for s in O.g2(b):
            self.assertEqual((s.lag, s.tfs, s.ta_confirm), (2, ('5m',), 'none'))

    def test_the_round_zero_spec_is_the_lanes_current_settings(self):
        s = O.ROUND0
        self.assertEqual((s.coins, s.horizon, s.tfs, s.top_n, s.combiner, s.lockout, s.lag, s.ta_confirm, s.ta_inv_k),
                         (('BTC', 'ETH'), 15, O.ALL_TFS, 10, 'hottest', 15, 0, 'none', 0))
        self.assertEqual(O.nondefault(s), 0)
        self.assertEqual(O.nondefault(dataclasses.replace(s, top_n=20, lag=1)), 2)


class Selection(unittest.TestCase):
    def test_more_checks_then_larger_lower_bound_then_simpler_then_hash(self):
        a, b = fake(6, 0.51), fake(7, 0.49)
        self.assertLess(O.key(b), O.key(a))
        c, d = fake(7, 0.52), fake(7, 0.49)
        self.assertLess(O.key(c), O.key(d))
        simple = fake(7, 0.5, O.ROUND0)
        complex_ = fake(7, 0.5, dataclasses.replace(O.ROUND0, top_n=20, lag=1))
        self.assertLess(O.key(simple), O.key(complex_))
        s1 = dataclasses.replace(O.ROUND0, top_n=20)
        s2 = dataclasses.replace(O.ROUND0, top_n=40)
        x, y = fake(7, 0.5, s1), fake(7, 0.5, s2)
        self.assertEqual(O.key(x) < O.key(y), C.spec_hash(s1) < C.spec_hash(s2))

    def test_an_ineligible_trial_never_wins(self):
        self.assertLess(O.key(fake(1, 0.4)), O.key(fake(9, 0.6, eligible=False)))

    def test_improves_means_strictly_more_checks_or_a_larger_bound(self):
        self.assertTrue(O.better(fake(5, 0.5), fake(4, 0.6)))
        self.assertTrue(O.better(fake(5, 0.52), fake(5, 0.51)))
        self.assertFalse(O.better(fake(5, 0.51), fake(5, 0.51)))
        self.assertFalse(O.better(fake(4, 0.6), fake(5, 0.5)))
        self.assertFalse(O.better(fake(9, 0.6, eligible=False), fake(1, 0.4)))
        self.assertTrue(O.better(fake(1, 0.4), fake(9, 0.6, eligible=False)))


class Descent(unittest.TestCase):
    def test_rounds_run_on_synthetic_events_and_never_get_worse(self):
        rng = np.random.default_rng(9)
        rows = TE.universe('BTC') + TE.universe('ETH')
        sets = {c: TE.make_set(c, rng, True, per_day=14, days=60) for c in ('BTC', 'ETH')}
        lo, hi = guards.DEV[0], guards.DEV[0] + 60 * 86_400_000
        seen = []
        out = O.descend(sets, rows, lo, hi, blocks=2, log=seen.append, rounds={1, 3, 5}, stall=False)
        self.assertEqual([r['round'] for r in out], [1, 3, 5])
        self.assertEqual(len(seen), 4 + 7 + 3)
        totals = [r['best']['total'] for r in out]
        self.assertEqual(totals, sorted(totals))
        for r in out:
            self.assertGreaterEqual(r['best']['total'], r['start']['total'])
        self.assertTrue(all('hash' in t and 'spec' in t for t in seen))

    def test_two_quiet_rounds_in_a_row_stop_the_loop(self):
        rng = np.random.default_rng(10)
        rows = TE.universe('BTC') + TE.universe('ETH')
        sets = {c: TE.make_set(c, rng, False, per_day=14, days=60) for c in ('BTC', 'ETH')}
        lo, hi = guards.DEV[0], guards.DEV[0] + 60 * 86_400_000
        out = O.descend(sets, rows, lo, hi, blocks=2, rounds={1, 3, 5})
        self.assertEqual([r['round'] for r in out], [1, 3])
        self.assertTrue(out[-1].get('stalled'))


if __name__ == '__main__':
    unittest.main()
