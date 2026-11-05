"""Registry rows of all-pairs runs: dollars per out-of-sample day, roles and pairing."""
from __future__ import annotations

import json
import os
import tempfile
import unittest

from allpairs.registry_rows import by_day, make_id, rows_for_run

D0 = 20623   # 2026-06-19


def result(name, arm, per_hour_by_day, folds_days, cfg=None, kind='real15', gaps=False):
    hourly, folds = [], []
    for fi, days in enumerate(folds_days):
        for d in days:
            hourly += [per_hour_by_day[d]] + [0.0] * 23
        f = dict(fold=fi, test=[days[0], days[-1]], n_hours=24 * len(days))
        if gaps:
            f['test_days'] = days
        folds.append(f)
    return dict(arm=arm, kind=kind, name=name, config_hash=f'h-{name}', config=dict(cfg or {}, name=name), folds=folds,
                hourly_pnl=hourly, oos=dict(per_hour=0.1, per_hour_ci95=[-1, 1], trades=5, hours=len(hourly)))


def write_run(root, configs):
    for name, arms, passed in configs:
        d = os.path.join(root, name)
        os.makedirs(d, exist_ok=True)
        for r in arms:
            json.dump(r, open(os.path.join(d, f'{r["arm"]}.json'), 'w'))
        json.dump(dict(passed=passed, checks=dict(target=passed, complete=True)), open(os.path.join(d, 'gate.json'), 'w'))


class Registry(unittest.TestCase):
    def test_by_day_from_hourly_folds(self):
        pnl = {D0 + k: float(k) - 1.5 for k in range(6)}
        r = result('x', 'base', pnl, [[D0, D0 + 1, D0 + 2], [D0 + 3, D0 + 4, D0 + 5]])
        bd = by_day(r)
        self.assertEqual(sorted(bd)[0], '2026-06-19')
        self.assertEqual(len(bd), 6)
        self.assertAlmostEqual(sum(bd.values()), sum(pnl.values()))
        # A gap in the history: test_days names the days the hours belong to.
        g = result('x', 'base', pnl, [[D0, D0 + 2, D0 + 5]], gaps=True)
        self.assertEqual(sorted(by_day(g)), ['2026-06-19', '2026-06-21', '2026-06-24'])
        # Without test_days a gap cannot be placed: refuse rather than shift days.
        bad = result('x', 'base', pnl, [[D0, D0 + 2, D0 + 5]])
        with self.assertRaises(ValueError):
            by_day(bad)

    def test_roles_pairing_and_ids(self):
        days = [[D0, D0 + 1], [D0 + 2, D0 + 3]]
        pnl = {D0 + k: 1.0 for k in range(4)}
        root = tempfile.mkdtemp()
        write_run(root, [
            ('base_ctrl', [result('base_ctrl', a, pnl, days) for a in ('base', 'stress', 'tight')], False),
            ('exit_naive', [result('exit_naive', a, pnl, days, cfg=dict(max_crossed=0)) for a in ('base', 'stress', 'tight')]
             + [result('exit_naive', 'synth15', pnl, days, kind='synth15')], False),
        ])
        rows = rows_for_run(root, '42088067536', 'abc123', 'https://run')
        by = {r['arm']: r for r in rows}
        self.assertEqual(sorted(by), ['base_ctrl', 'base_ctrl:stress', 'base_ctrl:tight', 'exit_naive', 'exit_naive:stress', 'exit_naive:tight'])
        self.assertEqual(by['base_ctrl']['role'], 'control')
        self.assertEqual(by['exit_naive']['role'], 'candidate')
        self.assertEqual(by['exit_naive']['control'], by['base_ctrl']['trial_id'])
        self.assertEqual(by['exit_naive:tight']['role'], 'neighbour')
        self.assertEqual(by['exit_naive:tight']['control'], by['exit_naive']['trial_id'])
        self.assertNotIn('control', by['base_ctrl'])
        days_iso = ['2026-06-19', '2026-06-20', '2026-06-21', '2026-06-22']
        self.assertEqual(by['exit_naive']['trial_id'], make_id('all-pairs', 'all-pairs-policy', 'exit_naive', 'abc123', days_iso))
        self.assertEqual((by['exit_naive']['pyes_kept'], by['exit_naive']['pyes_all']), (0.423, 0.498))
        self.assertFalse(by['exit_naive']['data']['doge'])
        self.assertTrue(by['exit_naive']['verdict'].startswith('fails the gate'))

    def test_control_from_an_earlier_run(self):
        days = [[D0, D0 + 1]]
        pnl = {D0: 1.0, D0 + 1: -2.0}
        a, b = tempfile.mkdtemp(), tempfile.mkdtemp()
        write_run(a, [('base', [result('base', 'base', pnl, days)], False)])
        prior = rows_for_run(a, '42054088258', 'sha-a')
        write_run(b, [('lead_btc', [result('lead_btc', 'base', pnl, days)], False)])
        rows = rows_for_run(b, '42065715159', 'sha-b', prior=prior)
        self.assertEqual(rows[0]['control'], prior[0]['trial_id'])
        # A control on other days is not a pair.
        write_run(b, [('lead_btc', [result('lead_btc', 'base', {D0: 1.0, D0 + 1: 1.0, D0 + 2: 0.0}, [[D0, D0 + 1, D0 + 2]])], False)])
        rows = rows_for_run(b, '42065715159', 'sha-b', prior=prior)
        self.assertNotIn('control', rows[0])


if __name__ == '__main__':
    unittest.main()
