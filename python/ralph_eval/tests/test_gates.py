import unittest
from datetime import date, timedelta

from ralph_eval.gates import (ALPHA, FDR_Q, InvalidEvidence, bh_pass,
                              direction_gate, execution_gate, mde,
                              one_sided_gap, stage1_paper_gate,
                              t_critical, t_survival)

D0 = date(2026, 11, 15)
DAYS = [(D0 + timedelta(days=i)).isoformat() for i in range(12)]


def arm(**overrides):
    x = {'id': 'J10-dial-a', 'design': 'paired', 'gaps': [45.0 + (i % 3) for i in range(12)],
         'full_book_days': DAYS, 'frozen': True, 'count_in_ledger': True,
         'measured_sd': 100.0, 'conservative_ceiling': 200.0,
         'baseline_decisions': 100, 'arm_decisions': 90, 'placebo_gap': 0.1}
    x.update(overrides)
    return x


class GateTests(unittest.TestCase):
    def test_t_exact_and_mde_matches_proposal(self):
        self.assertAlmostEqual(t_survival(1.363430318, 11), .1, places=7)
        self.assertAlmostEqual(t_critical(.1, 11), 1.363430318, places=7)
        self.assertTrue(61 < mde(100, design='paired') < 66)
        self.assertTrue(125 < mde(100, design='alternating') < 132)

    def test_bh_counts_all_candidates(self):
        self.assertEqual(bh_pass([0.001, 0.09, 0.2, 0.001]), [True, False, False, True])
        self.assertEqual(bh_pass([]), [])

    def test_direction_cannot_pass_without_split_pin_and_signature(self):
        rows = [{'day': d, 'full_book': True, 'source_mode': 'forward',
                 'n': 100, 'called_windows': 65, 'opposite_windows': 25} for d in DAYS]
        r = direction_gate(rows, signed=True, negative_splits_rule_pinned=False)
        self.assertEqual(r['status'], 'blocked')
        self.assertEqual(r['positive_days'], 12)
        self.assertEqual(direction_gate(rows[:11], signed=True, negative_splits_rule_pinned=True)['status'], 'underpowered')
        rows[0]['source_mode'] = 'historical_shadow'
        self.assertEqual(direction_gate(rows, signed=True, negative_splits_rule_pinned=True)['status'], 'blocked')

    def test_direction_under_9_days_iterates(self):
        rows = [{'day': d, 'full_book': True, 'source_mode': 'forward',
                 'n': 100, 'called_windows': 70 if i < 8 else 20,
                 'opposite_windows': 20 if i < 8 else 70} for i, d in enumerate(DAYS)]
        self.assertEqual(direction_gate(rows, signed=True, negative_splits_rule_pinned=True)['status'], 'iterate')

    def test_execution_no_direction_no_arm(self):
        self.assertEqual(execution_gate([arm()], direction_signed=False, look_day=12,
                                        embargo_verified=True, trial_count=1)['status'], 'blocked')
        self.assertEqual(execution_gate([arm()], direction_signed=True, look_day=12,
                                        embargo_verified=True, trial_count=0)['status'], 'blocked')

    def test_execution_only_12day_binding_and_harm_checks(self):
        good = execution_gate([arm()], direction_signed=True, look_day=12,
                              embargo_verified=True, trial_count=1)
        self.assertEqual(good['arms'][0]['status'], 'conditional')
        harm = execution_gate([arm(gaps=[-80.0, -70.0, -75.0, -85.0],
                                   full_book_days=DAYS[:4])],
                              direction_signed=True, look_day=4,
                              embargo_verified=True, trial_count=1)
        self.assertEqual(harm['arms'][0]['status'], 'harm_stop')

    def test_underpowered_and_fewer_trades(self):
        u = execution_gate([arm(conservative_ceiling=20)], direction_signed=True,
                           look_day=12, embargo_verified=True, trial_count=1)
        self.assertEqual(u['arms'][0]['status'], 'underpowered')
        v = execution_gate([arm(arm_decisions=80)], direction_signed=True,
                           look_day=12, embargo_verified=True, trial_count=1)
        self.assertEqual(v['arms'][0]['status'], 'iterate')

    def test_alternating_is_not_paired(self):
        a = arm(design='alternating', gaps=[], arm_day_net=[100, 105, 102, 107, 108, 104],
                control_day_net=[-50, -55, -52, -57, -53, -54])
        r = execution_gate([a], direction_signed=True, look_day=12,
                           embargo_verified=True, trial_count=1)
        self.assertEqual(r['arms'][0]['status'], 'conditional')

    def test_stage1_requires_200_no_refills_and_net_positive(self):
        days = [{'day': d, 'full_book': True, 'autorefills': 0,
                 'initial_pool': 200, 'pool_exhausted': False,
                 'baseline_decisions': 100, 'arm_decisions': 90, 'reconciled_net': 1}
                for d in DAYS]
        self.assertEqual(stage1_paper_gate(days, signed_direction=True, fresh_config=True)['status'], 'conditional')
        days[0]['autorefills'] = 1
        self.assertEqual(stage1_paper_gate(days, signed_direction=True, fresh_config=True)['status'], 'blocked')
        days[0]['autorefills'] = 0
        days[2]['reconciled_net'] = -100
        self.assertEqual(stage1_paper_gate(days, signed_direction=True, fresh_config=True)['status'], 'iterate')

    def test_nonfinite_rejected(self):
        with self.assertRaises(InvalidEvidence):
            one_sided_gap([float('nan'), 1, 2, 3])


if __name__ == '__main__':
    unittest.main()