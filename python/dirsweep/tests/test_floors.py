import unittest

import numpy as np

from dirsweep import floors as FL
from dirsweep import grid as G
from dirsweep import hist as H
from dirsweep import replay as R
from dirsweep.tests.util import make_grid

ND = 20
BLOCKS = [(2 * i, 2 * i + 2) for i in range(10)]
PERIODS = {'A': (0, 10), 'B': (10, 15), 'C': (15, 20)}


class WeeksTest(unittest.TestCase):
    def test_whole_weeks_capped(self):
        self.assertEqual(FL.weeks_needed(100.0), 2)           # 1000 / 700 -> 2
        self.assertEqual(FL.weeks_needed(20.0), 8)            # 1000 / 140 = 7.14 -> 8, at the cap
        self.assertEqual(FL.weeks_needed(18.0), 8)            # 1000 / 126 = 7.94 -> 8
        self.assertIsNone(FL.weeks_needed(17.0))              # 1000 / 119 = 8.4 -> 9: over the cap
        self.assertIsNone(FL.weeks_needed(10.0))              # 15 weeks: over the cap
        self.assertIsNone(FL.weeks_needed(0.0))
        self.assertIsNone(FL.weeks_needed(None))


class FloorsRunTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.grids = {'BTC': make_grid(ND, seed=11, reversal=0.5), 'ETH': make_grid(ND, seed=12, reversal=0.5)}
        cls.arrs = {c: H.cell_arrays(m, 0.01, 15, nd=ND, day_off=0) for c, m in cls.grids.items()}
        pooled = H.add(cls.arrs['BTC'], cls.arrs['ETH'])
        cls.ndec, cls.cf = pooled['ndec'], pooled['cf']
        cls.coins = {c: (a['ndec'], a['cf']) for c, a in cls.arrs.items()}
        cls.rp = {c: R.Replayer(m, 0.01, nd=ND, day_off=0) for c, m in cls.grids.items()}
        cls.nact = G.n_active(np.arange(G.N_CELLS))
        cls.bench = [ik * G.PER_K for ik in range(len(G.K))]

    def run_floor(self, floor):
        return FL.run_floor(floor, self.ndec, self.cf, BLOCKS, self.nact, self.bench, self.coins, self.rp, PERIODS)

    def test_floor_is_respected_and_lockout_never_adds_calls(self):
        for floor in (3, 20):
            res = self.run_floor(floor)
            self.assertEqual(res['floor'], floor)
            fr = res['frozen']
            if fr.get('rid') is None:
                continue
            self.assertGreaterEqual(fr['calls_per_day'], floor)          # eligibility: at least `floor` decided calls a day in the window
            for f in res['folds']:
                if f.get('rule') is not None:
                    self.assertGreaterEqual(f['calls_per_day'] or 0.0, 0.0)
            fl = res['frozen_lockout']
            self.assertLessEqual(fl['decided_per_day'], fr['calls_per_day'] + 1e-9)
            self.assertIn('E9', res['verdict'])
            ln = res['lockout_nested']
            if ln:
                self.assertAlmostEqual(ln['excess_per_day'], ln['decided_per_day'] * (ln['pooled']['hit'] - 0.5), places=9)
                self.assertLessEqual(ln['pooled']['N'], res['nested']['N'])

    def test_a_higher_floor_cannot_choose_a_rarer_rule(self):
        lo, hi = self.run_floor(3), self.run_floor(40)
        if lo['frozen'].get('rid') is not None and hi['frozen'].get('rid') is not None:
            self.assertGreaterEqual(hi['frozen']['calls_per_day'], 40)

    def test_lockout_replay_of_a_fold_rule_matches_manual_sum(self):
        res = self.run_floor(3)
        folds = [f for f in res['folds'] if f.get('rule')]
        self.assertTrue(folds)
        rid = res['frozen']['rid']
        by = FL.frozen_replay(self.rp, rid, BLOCKS, PERIODS)
        tot = {k: sum(self.rp[c].replay(rid, 0, ND)[k] for c in self.rp) for k in ('calls', 'decided', 'right')}
        self.assertAlmostEqual(by['decided_per_day'], tot['decided'].sum() / ND)
        self.assertAlmostEqual(by['hit'], tot['right'].sum() / tot['decided'].sum())
        self.assertAlmostEqual(by['decided_per_day_C'], tot['decided'][15:20].sum() / 5)


def _row(floor, nested_hit, E, excess, weeks, rid=1):
    v = {k: True for k in ('E1', 'E2', 'E3', 'E4', 'E5', 'E6', 'E8', 'E9')}
    v.update(E)
    return {'floor': floor, 'nested_hit': nested_hit, 'verdict': v, 'lockout_nested': {'excess_per_day': excess},
            'frozen': {'rid': rid, 'rule': {'k': floor}}, 'frozen_lockout': {'weeks': weeks}}


class ChooseTest(unittest.TestCase):
    def results(self, rows0, twin_hit=0.50):
        twin = {'floors': [{'floor': r['floor'], 'nested_hit': twin_hit} for r in rows0]}
        return {0: {'floors': rows0}, 1: twin, 2: twin, 3: twin}

    def test_largest_excess_among_qualifying_wins_ties_to_lower_floor(self):
        rows = [_row(3, .56, {}, 5.0, 4), _row(6, .56, {}, 9.0, 3), _row(10, .55, {}, 9.0, 2), _row(15, .55, {}, 20.0, None), _row(20, .55, {'E4': False}, 30.0, 2)]
        out = FL.choose(self.results(rows))
        self.assertEqual(out['candidate']['floor'], 6)              # 15 has no weeks, 20 fails E4, 10 ties 6 on excess -> the lower floor
        self.assertEqual([r['qualifies'] for r in out['floors']], [True, True, True, False, False])

    def test_a_twin_outside_the_band_blocks_every_floor(self):
        rows = [_row(3, .56, {}, 5.0, 4), _row(6, .56, {}, 9.0, 3)]
        res = self.results(rows)
        res[2] = {'floors': [{'floor': 3, 'nested_hit': 0.52}, {'floor': 6, 'nested_hit': 0.50}]}
        out = FL.choose(res)
        self.assertEqual([r['qualifies'] for r in out['floors']], [False, True])
        self.assertEqual(out['candidate']['floor'], 6)

    def test_no_qualifying_floor_gives_no_candidate(self):
        out = FL.choose(self.results([_row(3, .56, {'E8': False}, 5.0, 4)]))
        self.assertIsNone(out['candidate'])

    def test_missing_twins_do_not_qualify(self):
        res = {0: {'floors': [_row(3, .56, {}, 5.0, 4)]}}
        self.assertIsNone(FL.choose(res)['candidate'])


if __name__ == '__main__':
    unittest.main()
