"""Held-out standard HO-1: fold layout, the registry's held-out block (folds, RV terciles, placebo) and its rows."""
from __future__ import annotations

import csv
import datetime as dt
import gzip
import json
import os
import tempfile
import unittest

import numpy as np

from allpairs.ho1 import block, hour_terciles, run, verdict
from allpairs.registry_rows import rows_for_run
from allpairs.validate import ho1_folds


def dn(iso):
    return (dt.date.fromisoformat(iso) - dt.date(1970, 1, 1)).days


def write_labels(path, rows):
    with gzip.open(path, 'wt', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['ts_iso', 'asset', 'rv60', 'q33', 'q67', 'tercile', 'z60', 'trend'])
        for r in rows:
            w.writerow(r)


def ho1_result(per_fold, fold_days, rand95=-1.0, shuffled=(-0.5, -0.2), arm='base', name='cfg', hour_pnl=None):
    """A combined arm result: fold k's hours all carry per_fold[k] $ (or hour_pnl(day, hour))."""
    hourly, folds = [], []
    for k, days in enumerate(fold_days):
        for d in days:
            hourly += [hour_pnl(d, h) if hour_pnl else per_fold[k] for h in range(24)]
        folds.append(dict(fold=k, test=[days[0], days[-1]], test_days=list(days), n_hours=24 * len(days)))
    ph = float(np.mean(hourly))
    return dict(arm=arm, kind='real15', name=name, protocol='ho1', ho1_span=['2026-04-18', '2026-08-01', '2026-11-04'],
                config_hash=f'h-{name}', config=dict(name=name), traded_assets=['BTC', 'ETH'], folds=folds, hourly_pnl=hourly,
                oos=dict(per_hour=ph, per_hour_ci95=[-1, 1], trades=10, hours=len(hourly)),
                placebo=dict(random_per_hour_p95=rand95, shuffled_per_hour=list(shuffled)))


class ArmConfig(unittest.TestCase):
    def test_every_gated_arm_has_its_placebos_under_ho1(self):
        from allpairs.run import DEFAULTS, arm_config, config_hash
        for arm in ('stress', 'tight'):
            self.assertEqual(arm_config({}, arm)['placebo']['shuffles'], 0)          # walk-forward: unchanged
            c = arm_config({}, arm, 'ho1')
            self.assertEqual(c['placebo']['shuffles'], DEFAULTS['placebo']['shuffles'])
            self.assertEqual(config_hash(c), config_hash(arm_config({}, arm)))      # placebo is not in the hash
        self.assertEqual(DEFAULTS['placebo']['shuffles'], 3)                          # DEFAULTS not mutated
        # A real stress arm then carries shuffled refits, and beats_placebo is judged on them.
        d0 = dn('2026-08-01')
        fd = [list(range(d0 + 16 * k, d0 + 16 * (k + 1))) for k in range(6)]
        terc = {(d, h): ('LOW', 'MID', 'HIGH')[h // 8] for days in fd for d in days for h in range(24)}
        none = ho1_result([1.0] * 6, fd, arm='stress', rand95=-0.1, shuffled=())
        none['placebo']['shuffled_per_hour'] = None
        self.assertFalse(block(none, terc)['beats_placebo'])        # no refits: not shown as beaten
        self.assertTrue(block(ho1_result([1.0] * 6, fd, arm='stress', rand95=-0.1, shuffled=(-0.3, 0.1, -0.2)), terc)['beats_placebo'])


class Folds(unittest.TestCase):
    def test_project_layout(self):
        """Apr 18..Nov 5 history: one training span Apr 18..Jul 29 (2-day purge before Aug 1) in every fold, and six
        consecutive 16-day held-out folds Aug 1..Nov 4; Nov 5 is not held out."""
        days = np.arange(dn('2026-04-18'), dn('2026-11-05') + 1)
        f = ho1_folds(days)
        self.assertEqual(len(f), 6)
        tr0 = f[0][0]
        self.assertEqual((int(tr0[0]), int(tr0[-1])), (dn('2026-04-18'), dn('2026-07-29')))
        for tr, te in f:
            self.assertTrue(np.array_equal(tr, tr0))
            self.assertEqual(len(te), 16)
        self.assertEqual(int(f[0][1][0]), dn('2026-08-01'))
        self.assertEqual(int(f[-1][1][-1]), dn('2026-11-04'))
        tested = np.concatenate([te for _, te in f])
        self.assertEqual(len(np.unique(tested)), 96)
        self.assertLess(int(tr0.max()), int(tested.min()) - 1)

    def test_gaps_and_spans(self):
        days = np.array([dn('2026-04-20'), dn('2026-05-01'), dn('2026-08-03'), dn('2026-09-30')])
        f = ho1_folds(days)
        self.assertEqual([len(te) for _, te in f], [1, 1])       # folds without a data day are left out
        with self.assertRaises(ValueError):
            ho1_folds(days, '2026-08-01', '2026-04-18', '2026-11-04')
        self.assertEqual(ho1_folds(np.array([dn('2026-09-01')])), [])   # no training day: no fold


class HeldOutBlock(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        d0 = dn('2026-08-01')
        self.fold_days = [list(range(d0 + 16 * k, d0 + 16 * (k + 1))) for k in range(6)]

    def test_hour_tercile_is_the_rounded_mean_of_the_traded_assets(self):
        p = os.path.join(self.d, 'l.csv.gz')
        rows = []
        for m in range(60):
            rows.append([f'2026-08-01T00:{m:02d}:00Z', 'BTC', '', '', '', 'HIGH', '', ''])
            rows.append([f'2026-08-01T00:{m:02d}:00Z', 'ETH', '', '', '', 'LOW', '', ''])    # mean 1.0 -> MID
            rows.append([f'2026-08-01T01:{m:02d}:00Z', 'BTC', '', '', '', 'HIGH', '', ''])
            rows.append([f'2026-08-01T01:{m:02d}:00Z', 'ETH', '', '', '', 'NA', '', ''])     # NA left out -> HIGH
            rows.append([f'2026-08-01T01:{m:02d}:00Z', 'DOGE', '', '', '', 'LOW', '', ''])   # not traded: ignored
            rows.append([f'2026-08-01T02:{m:02d}:00Z', 'BTC', '', '', '', 'LOW' if m < 31 else 'MID', '', ''])  # 29/60 -> LOW
        rows.append(['2026-07-31T23:00:00Z', 'BTC', '', '', '', 'HIGH', '', ''])                   # outside the span
        write_labels(p, rows)
        t = hour_terciles(p, ['BTC', 'ETH'], dn('2026-08-01'), dn('2026-08-01'))
        d = dn('2026-08-01')
        self.assertEqual(t, {(d, 0): 'MID', (d, 1): 'HIGH', (d, 2): 'LOW'})

    def test_block_folds_terciles_and_placebo(self):
        # Hours 0-7 LOW, 8-15 MID, 16-23 HIGH on every held-out day; the policy makes +1 $ in LOW and MID hours, loses
        # 0.2 $ in HIGH hours, and loses everything in fold 2.
        terc = {(d, h): ('LOW', 'MID', 'HIGH')[h // 8] for days in self.fold_days for d in days for h in range(24)}
        bad = set(self.fold_days[2])
        pnl = lambda d, h: -2.0 if d in bad else (1.0 if h < 16 else -0.2)
        r = ho1_result(None, self.fold_days, hour_pnl=pnl)
        b = block(r, terc)
        self.assertEqual((b['standard'], b['tier'], b['days'], b['folds'], b['folds_won']), ('HO-1', 'history', 96, 6, 5))
        self.assertAlmostEqual(b['worst_fold_per_hour'], -2.0)
        self.assertEqual((b['terciles_covered'], b['terciles_won']), (3, 2))
        self.assertAlmostEqual(b['by_tercile']['HIGH']['per_hour'], (-0.2 * 5 * 16 * 8 - 2.0 * 16 * 8) / (96 * 8), places=4)
        self.assertTrue(b['beats_placebo'])
        self.assertNotIn('replay_version', b)
        ok, why = verdict(b)
        self.assertFalse(ok)
        self.assertTrue(any('worst fold' in w for w in why))
        # Placebo: must beat the random 95th percentile AND every shuffled refit.
        self.assertFalse(block(ho1_result(None, self.fold_days, hour_pnl=pnl, shuffled=(0.0, 5.0)), terc)['beats_placebo'])
        self.assertFalse(block(ho1_result(None, self.fold_days, hour_pnl=pnl, rand95=9.0), terc)['beats_placebo'])
        # Fewer than 100 hours in a tercile: not covered.
        few = {k: v for k, v in terc.items() if not (v == 'LOW' and k[0] > self.fold_days[0][11])}
        bf = block(r, few)
        self.assertEqual(bf['by_tercile']['LOW']['hours'], 12 * 8)
        self.assertEqual(bf['terciles_covered'], 2)
        self.assertGreater(bf['unlabelled_hours'], 0)

    def test_passing_block_and_hour_count_mismatch(self):
        terc = {(d, h): ('LOW', 'MID', 'HIGH')[h // 8] for days in self.fold_days for d in days for h in range(24)}
        b = block(ho1_result([0.3, 0.2, -0.1, 0.4, 0.5, 0.1], self.fold_days), terc)
        self.assertEqual(verdict(b), (True, []))
        r = ho1_result([0.3] * 6, self.fold_days)
        r['hourly_pnl'] = r['hourly_pnl'][:-1]
        with self.assertRaises(ValueError):
            block(r, terc)

    def test_run_writes_heldout_and_registry_rows_carry_it(self):
        root = os.path.join(self.d, 'results')
        terc_rows = []
        for days in self.fold_days:
            for d in days:
                day = (dt.date(1970, 1, 1) + dt.timedelta(days=d)).isoformat()
                for h in range(24):
                    terc_rows.append([f'{day}T{h:02d}:00:00Z', 'BTC', '', '', '', ('LOW', 'MID', 'HIGH')[h // 8], '', ''])
        lp = os.path.join(self.d, 'labels.csv.gz')
        write_labels(lp, terc_rows)
        for name, per in (('base', [-0.1] * 6), ('lead', [0.3, 0.2, -0.1, 0.4, 0.5, 0.1])):
            os.makedirs(os.path.join(root, name))
            for arm in ('base', 'stress', 'tight'):
                json.dump(ho1_result(per, self.fold_days, arm=arm, name=name), open(os.path.join(root, name, f'{arm}.json'), 'w'))
            json.dump(dict(passed=False, checks=dict(target=False)), open(os.path.join(root, name, 'gate.json'), 'w'))
        # A walk-forward config next to them gets no block.
        os.makedirs(os.path.join(root, 'walk'))
        w = ho1_result([1.0] * 6, self.fold_days, name='walk')
        w['protocol'] = 'walk'
        json.dump(w, open(os.path.join(root, 'walk', 'base.json'), 'w'))
        done = run(root, lp)
        self.assertEqual(sorted(done), ['base', 'lead'])
        self.assertTrue(verdict(done['lead']['base'])[0])
        self.assertFalse(os.path.exists(os.path.join(root, 'walk', 'heldout.json')))
        rows = rows_for_run(root, '42200000000', 'sha', 'https://run')
        by = {r['arm']: r for r in rows}
        self.assertEqual(by['lead']['heldout']['folds_won'], 5)
        self.assertEqual(by['lead:tight']['heldout']['standard'], 'HO-1')
        self.assertNotIn('heldout', by['walk'])
        # HO-1: every config is a candidate against one no-trade control ($0 on each held-out day), the benchmark of
        # the block, so the registry's paired gain is the arm's own P&L.
        z = by['no_trade']
        self.assertEqual((z['role'], len(z['by_day']), sum(z['by_day'].values())), ('control', 96, 0.0))
        self.assertEqual(sorted(z['by_day']), by['lead']['data']['days'])
        self.assertEqual((by['base']['role'], by['lead']['role'], by['lead:stress']['role']), ('candidate', 'candidate', 'neighbour'))
        for arm in ('base', 'lead', 'lead:stress', 'base:tight'):
            self.assertEqual(by[arm]['control'], z['trial_id'])
        self.assertEqual(sum(1 for r in rows if r['arm'] == 'no_trade'), 1)
        self.assertEqual(by['lead']['data']['engine'], 'allpairs')
        self.assertEqual((by['lead']['contract_type'], by['lead']['modules']), ('price_prediction', ['entry-gate', 'exits']))
        self.assertEqual(len(by['lead']['by_day']), 96)


if __name__ == '__main__':
    unittest.main()
