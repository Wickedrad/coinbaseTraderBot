import os
import tempfile
import unittest

import numpy as np
import pandas as pd

from dirsweep import final as FIN
from dirsweep import grid as G
from dirsweep import hist as H
from dirsweep import replay as R
from dirsweep import topup as T
from dirsweep.tests.util import make_grid

FZ_WEEKS = 2
FIRST, LAST = '2026-11-23', '2026-12-06'                 # Monday to Sunday, two whole weeks
GRID_FIRST, GRID_LAST = '2026-11-21', '2026-12-07'       # two warm-up days, the day after


def write_csv(m: dict, path: str, cut: int = 0) -> None:
    n = m['n'] - cut
    ts = m['t0'] + np.arange(n) * G.MIN
    pd.DataFrame({'ts': ts, 'o': m['o'][:n], 'h': m['h'][:n], 'l': m['l'][:n], 'c': m['c'][:n], 'v': m['v'][:n], 'tb': m['tb'][:n]}).to_csv(path, index=False)


class WindowTest(unittest.TestCase):
    def test_whole_iso_weeks_only(self):
        w = FIN.window({'first_day': FIRST, 'last_day': LAST, 'weeks': 2})
        self.assertEqual((w['days'], w['weeks'], w['hi'] - w['lo']), (14, 2, 14))
        self.assertEqual((w['grid_first'], w['grid_last']), (GRID_FIRST, GRID_LAST))
        self.assertEqual(w['lo'], FIN.day_index('2026-11-23'))
        self.assertEqual(FIN.day_index('2020-01-01'), 0)
        for bad in ({'first_day': '2026-11-24', 'last_day': '2026-12-07', 'weeks': 2}, {'first_day': FIRST, 'last_day': '2026-12-05', 'weeks': 2},
                    {'first_day': FIRST, 'last_day': LAST, 'weeks': 3}):
            with self.assertRaises(ValueError):
                FIN.window(bad)

    def test_pass_test(self):
        ok = {'decided': 900, 'hit': 0.55, 'lb975': 0.52, 'by_coin': {'BTC': {'hit': 0.55}, 'ETH': {'hit': 0.54}}}
        self.assertTrue(FIN.verdict(ok)['pass'])
        for k, v in (('decided', 799), ('hit', 0.5299), ('lb975', 0.50)):
            self.assertFalse(FIN.verdict(dict(ok, **{k: v}))['pass'], k)
        self.assertFalse(FIN.verdict(dict(ok, by_coin={'BTC': {'hit': 0.55}, 'ETH': {'hit': 0.5099}}))['pass'])
        self.assertFalse(FIN.verdict(dict(ok, decided=0, hit=None, lb975=None))['pass'])


class ScoreTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.t0 = T.day_start_ms(GRID_FIRST)
        days = 17
        cls.m = {c: make_grid(days, seed=s, reversal=0.6, t0=cls.t0) for c, s in (('BTC', 21), ('ETH', 22))}
        cls.tmp = tempfile.TemporaryDirectory()
        cls.csv = {}
        for c, m in cls.m.items():
            cls.csv[c] = os.path.join(cls.tmp.name, f'{c}.csv')
            write_csv(m, cls.csv[c])
        cls.win = FIN.window({'first_day': FIRST, 'last_day': LAST, 'weeks': FZ_WEEKS})
        cls.fz = {'rule': {'rid': 2 * G.cell(5, 1, 0, 0, 0)}, 'control': {'rid': 2 * G.cell(5, 0, 0, 0, 0)}, 'expected_decided': 1000.0}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def grids(self):
        return {c: FIN.load_final(p, self.win) for c, p in self.csv.items()}

    def test_load_covers_warmup_final_and_next_day(self):
        for m in self.grids().values():
            self.assertEqual((m['t0'], m['n']), (self.t0, 17 * 1440))

    def test_a_file_that_ends_early_is_refused(self):
        p = os.path.join(self.tmp.name, 'short.csv')
        write_csv(self.m['BTC'], p, cut=600)
        with self.assertRaises(AssertionError):
            FIN.load_final(p, self.win)

    def test_plumbing_may_not_reach_the_end_of_the_search_days(self):
        with self.assertRaises(AssertionError):
            FIN.load_final(self.csv['BTC'], self.win, plumbing=True)

    def test_score_matches_a_direct_replay_and_ignores_the_warm_up_days(self):
        res = FIN.score(self.grids(), self.fz, self.win)
        rp = {c: R.Replayer(m, G.STEP[c], nd=self.win['hi']) for c, m in self.grids().items()}
        dec = sum(rp[c].replay(self.fz['rule']['rid'], self.win['lo'], self.win['hi'])['decided'].sum() for c in rp)
        right = sum(rp[c].replay(self.fz['rule']['rid'], self.win['lo'], self.win['hi'])['right'].sum() for c in rp)
        self.assertEqual(res['rule']['decided'], int(dec))
        self.assertAlmostEqual(res['rule']['hit'], right / dec)
        self.assertEqual(len(res['rule']['by_week']), FZ_WEEKS)
        self.assertEqual(set(res['rule']['by_coin']), {'BTC', 'ETH'})
        self.assertEqual(res['gap_minutes'], {'BTC': 0, 'ETH': 0})
        self.assertIn('control', res)
        self.assertGreater(res['rule']['hit'], 0.5)                       # the planted reversal is there to be found
        wide = FIN.score(self.grids(), self.fz, dict(self.win, lo=self.win['lo'] - 2))
        self.assertGreater(wide['rule']['decided'], res['rule']['decided'])     # days before `lo` count only when asked for


class FreezeDataTest(unittest.TestCase):
    def test_freeze_data_shape_and_sizing(self):
        nd = 20
        blocks = [(2 * i, 2 * i + 2) for i in range(10)]
        periods = {'A': (0, 10), 'B': (10, 15), 'C': (15, 20)}
        grids = {'BTC': make_grid(nd, seed=11, reversal=0.5), 'ETH': make_grid(nd, seed=12, reversal=0.5)}
        arrs = {c: H.cell_arrays(m, 0.01, 15, nd=nd, day_off=0) for c, m in grids.items()}
        pooled = H.add(arrs['BTC'], arrs['ETH'])
        coins = {c: (a['ndec'], a['cf']) for c, a in arrs.items()}
        rp = {c: R.Replayer(m, 0.01, nd=nd, day_off=0) for c, m in grids.items()}
        nact = G.n_active(np.arange(G.N_CELLS))
        bench = [ik * G.PER_K for ik in range(len(G.K))]
        out = FIN.freeze_data(3, pooled['ndec'], pooled['cf'], blocks, nact, bench, coins, rp, periods)
        self.assertEqual(out['floor'], 3)
        self.assertIsInstance(out['rule']['rid'], int)
        self.assertEqual(out['rule']['describe'], G.describe(out['rule']['rid']))
        self.assertGreaterEqual(out['calls_per_day'], 3)
        self.assertIn('control', out)
        c = out['control']['describe']
        self.assertEqual((c['z'], c['a'], c['r'], c['phase']), (0.0, None, 0.0, 'all'))      # always on: no filter
        if out['weeks']:
            self.assertAlmostEqual(out['expected_decided'], out['lockout']['decided_per_day_C'] * 7 * out['weeks'])


if __name__ == '__main__':
    unittest.main()


class FreezeFileTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        for p in list(FIN.STRICT_FILES) + list(FIN.ADVISORY_FILES) + ['python/dirsweep/a.py', 'python/dirsweep/tests/t.py']:
            full = os.path.join(self.root, p)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, 'w') as f:
                f.write(p)
        self.data = {'floor': 60, 'rule': {'rid': 42, 'describe': {'k': 30}}, 'control': {'rid': 7, 'describe': {'k': 60}, 'in_sample': {}}, 'weeks': 4,
                     'expected_decided': 1300.0, 'in_sample': {'hit': 0.55}, 'lockout': {'weeks': 4}}
        self.choose = {'candidate': {'floor': 60, 'rid': 42, 'excess_per_day': 2.4}, 'floors': [{'floor': 30, 'qualifies': True}, {'floor': 60, 'qualifies': True},
                                                                                              {'floor': 20, 'qualifies': False}]}

    def tearDown(self):
        self.tmp.cleanup()

    def test_assemble_dates_deadline_and_hashes(self):
        fz = FIN.assemble(self.data, self.choose, '2026-11-23', self.root, '2026-11-20T12:00:00Z')
        self.assertEqual((fz['first_day'], fz['last_day'], fz['weeks']), ('2026-11-23', '2026-12-20', 4))
        self.assertEqual(fz['freeze_deadline_utc'], '2026-11-21T00:00:00Z')
        self.assertEqual(fz['frontier']['qualifying_floors'], [30, 60])
        self.assertIn('python/dirsweep/a.py', fz['hashes'])
        self.assertIn('python/dirsweep/tests/t.py', fz['hashes'])
        self.assertEqual(len(fz['advisory_hashes']), 2)
        self.assertEqual(FIN.window(fz)['weeks'], 4)

    def test_assemble_refuses_bad_inputs(self):
        for choose in ({'candidate': None, 'floors': []}, {'candidate': {'floor': 40, 'rid': 42, 'excess_per_day': 1}, 'floors': []},
                       {'candidate': {'floor': 60, 'rid': 41, 'excess_per_day': 1}, 'floors': []}):
            with self.assertRaises(ValueError):
                FIN.assemble(self.data, choose, '2026-11-23', self.root, 'x')
        with self.assertRaises(ValueError):
            FIN.assemble(self.data, self.choose, '2026-11-24', self.root, 'x')                  # not a Monday
        with self.assertRaises(ValueError):
            FIN.assemble(dict(self.data, weeks=None), self.choose, '2026-11-23', self.root, 'x')

    def test_verify_catches_any_change_to_a_strict_file_and_only_reports_advisory(self):
        fz = FIN.assemble(self.data, self.choose, '2026-11-23', self.root, 'x')
        self.assertTrue(FIN.verify(fz, self.root)['ok'])
        with open(os.path.join(self.root, 'python/oracle/heat_live.py'), 'a') as f:
            f.write('#')
        res = FIN.verify(fz, self.root)
        self.assertTrue(res['ok'])
        self.assertEqual(res['advisory_changed'], ['python/oracle/heat_live.py'])
        with open(os.path.join(self.root, 'python/dirsweep/a.py'), 'a') as f:
            f.write('#')
        self.assertEqual(FIN.verify(fz, self.root)['mismatch'], ['python/dirsweep/a.py'])
        with open(os.path.join(self.root, 'python/dirsweep/new.py'), 'w') as f:
            f.write('x')
        self.assertIn('python/dirsweep/new.py', FIN.verify(fz, self.root)['mismatch'])          # a file added after the freeze is a change too
