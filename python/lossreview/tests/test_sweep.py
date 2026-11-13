import random
import unittest

from lossreview import registry, rules, shadow, sweep

DAY0 = 1_790_000_000.0   # an arbitrary UTC day start; closed_t of a trip is DAY0 + 86400 * k + seconds


def make_rows(seed, days=8, per_day=60, plant=0.0, feature='frac_elapsed_at_entry', cut=0.3):
    """Synthetic trips: pnl is noise (sd $3); trips with `feature` under `cut` get `plant` dollars added (negative = they lose)."""
    rnd = random.Random(seed)
    rows = []
    for d in range(days):
        for i in range(per_day):
            x = rnd.random()
            px = rnd.choice([0.2, 0.4, 0.6, 0.8])
            pnl = rnd.gauss(-0.2, 3.0) + (plant if x < cut else 0.0)
            rows.append({'closed_t': DAY0 + 86400 * d + 3600 + i * 60, 'entry_px': px, feature: x, 'pnl': pnl, 'ticker': 'T%d-%d' % (d, i)})
    return rows


def hyp(**kw):
    h = {'id': 'early-entry', 'loss_class': 'WRONG_SIDE', 'lever': 'skip', 'feature': 'frac_elapsed_at_entry', 'op': 'lt',
         'thresholds': [0.1, 0.2, 0.3, 0.4], 'neighbor_features': [], 'mechanism': 'x', 'cites': []}
    h.update(kw)
    return h


def day_str(k):
    return sweep.day_of({'closed_t': DAY0 + 86400 * k})


class SweepTests(unittest.TestCase):
    def test_a_planted_effect_is_found_and_flags_enough_trips(self):
        rows = make_rows(1, days=6, per_day=350, plant=-4.0, cut=0.12)       # a lane's day: ~350 trips; 12% of them flagged
        res = sweep.sweep(hyp(thresholds=[0.04, 0.08, 0.12]), rows, generating_days=[])
        best = res['best']
        self.assertEqual(best['verdict'], 'candidate')
        self.assertGreater(best['pooled']['mean'], 0)
        self.assertGreaterEqual(best['flagged'], sweep.MIN_FLAGGED)

    def test_pure_noise_is_not_called_a_candidate(self):
        false = 0
        for seed in range(60):
            res = sweep.sweep(hyp(), make_rows(100 + seed, days=8, per_day=60), generating_days=[])
            false += sum(1 for s in res['scored'] if s['verdict'] == 'candidate')
        self.assertLessEqual(false, 3)       # Bonferroni over 4 thresholds at alpha .05: a handful in 240 tests at most

    def test_generating_days_are_never_scored(self):
        rows = make_rows(2, days=10, per_day=80, plant=-2.5)
        gen = [day_str(k) for k in range(6)]
        sc = sweep.scoring_rows(rows, gen)
        self.assertEqual({sweep.day_of(r) for r in sc}, {day_str(k) for k in range(6, 10)})
        res = sweep.sweep(hyp(), rows, generating_days=gen)
        for s in res['scored']:
            self.assertTrue(all(d['day'] > max(gen) for d in s['days']))

    def test_too_few_days_or_flags_is_not_a_verdict(self):
        res = sweep.sweep(hyp(), make_rows(3, days=3, per_day=80, plant=-3), generating_days=[])
        self.assertTrue(all(s['verdict'] == 'insufficient_days' for s in res['scored']))
        res = sweep.sweep(hyp(thresholds=[0.01]), make_rows(4, days=8, per_day=40, plant=-3), generating_days=[])
        self.assertTrue(all(s['verdict'] == 'insufficient_flags' for s in res['scored']))

    def test_the_floor_blocks_a_rule_that_skips_too_much(self):
        rows = make_rows(5, days=8, per_day=80, plant=-3.0, cut=0.5)
        res = sweep.sweep(hyp(thresholds=[0.5]), rows, generating_days=[])
        self.assertEqual(res['scored'][0]['verdict'], 'floor')          # flags half the trips: far past 15%

    def test_a_dial_rule_is_scored_against_a_matched_multiplier(self):
        rows = make_rows(6, days=6, per_day=350, plant=-4.0, cut=0.12)
        res = sweep.sweep(hyp(lever='dial', thresholds=[0.12]), rows, generating_days=[])
        s = res['scored'][0]
        self.assertEqual(s['rule']['multiplier'], sweep.DIAL_MULTIPLIER)
        self.assertEqual(s['retention'], 1.0)                            # a dial keeps every trip
        self.assertEqual(s['verdict'], 'candidate')

    def test_levers_the_file_cannot_price_get_a_replay_request(self):
        res = sweep.sweep(hyp(lever='maker'), make_rows(7), generating_days=['2026-11-12'])
        self.assertEqual(res['scored'], [])
        self.assertEqual(res['replay']['lever'], 'maker')
        self.assertEqual(res['replay']['score_days_after'], '2026-11-12')

    def test_neighbor_features_add_candidates_and_count_toward_the_correction(self):
        rows = make_rows(8)
        for r in rows:
            r['spot_vs_strike_bps_pre'] = random.Random(r['ticker']).uniform(-20, 20)
        res = sweep.sweep(hyp(neighbor_features=['spot_vs_strike_bps_pre']), rows, generating_days=[])
        self.assertEqual(res['k'], 4 + 3)
        self.assertTrue(all(s['k'] == 7 for s in res['scored']))

    def test_gain_is_first_order_and_signed(self):
        r = {'pnl': -4.0}
        self.assertEqual(rules.gain({'lever': 'skip'}, r), 4.0)
        self.assertAlmostEqual(rules.gain({'lever': 'dial', 'multiplier': 0.25}, r), 3.0)
        self.assertEqual(rules.gain({'lever': 'maker'}, r), 0.0)


class RulesRegistryShadowTests(unittest.TestCase):
    def rule(self, **kw):
        r = {'id': 'r1', 'lever': 'skip', 'feature': 'frac_elapsed_at_entry', 'op': 'lt', 'threshold': 0.3}
        r.update(kw)
        return r

    def test_validate_rule(self):
        self.assertTrue(rules.validate_rule(self.rule())[0])
        self.assertFalse(rules.validate_rule(self.rule(feature='pnl'))[0])                  # an outcome column
        self.assertFalse(rules.validate_rule(self.rule(lever='dial'))[0])                    # a dial needs its multiplier
        self.assertTrue(rules.validate_rule(self.rule(lever='dial', multiplier=0.5))[0])
        self.assertFalse(rules.validate_rule(self.rule(lever='dial', multiplier=1.5))[0])    # a dial only shrinks
        self.assertFalse(rules.validate_rule(self.rule(also=[{'feature': 'entry_px', 'op': 'lt', 'threshold': 1}] * 3))[0])
        self.assertTrue(rules.curve_edit(self.rule(feature='rank')))

    def test_hit_needs_every_test_and_a_missing_value_is_never_flagged(self):
        r = self.rule(also=[{'feature': 'entry_px', 'op': 'gt', 'threshold': 0.5}])
        self.assertTrue(rules.hit(r, {'frac_elapsed_at_entry': 0.1, 'entry_px': 0.6}))
        self.assertFalse(rules.hit(r, {'frac_elapsed_at_entry': 0.1, 'entry_px': 0.4}))
        self.assertFalse(rules.hit(r, {'frac_elapsed_at_entry': None, 'entry_px': 0.6}))
        self.assertFalse(rules.hit(r, {'entry_px': 0.6}))
        self.assertTrue(rules.hit(self.rule(op='between', threshold=[0.1, 0.2]), {'frac_elapsed_at_entry': 0.15}))
        self.assertTrue(rules.hit(self.rule(feature='no_side', op='eq', threshold=True), {'no_side': 'True'}))

    def test_hash_changes_with_anything_that_changes_the_rule(self):
        a = rules.rule_hash(self.rule())
        self.assertEqual(a, rules.rule_hash(self.rule()))
        self.assertNotEqual(a, rules.rule_hash(self.rule(threshold=0.31)))
        self.assertNotEqual(a, rules.rule_hash(self.rule(lever='dial', multiplier=0.5)))

    def test_registry_counts_trials_and_enforces_the_moves(self):
        reg = registry.Registry()
        self.assertEqual(reg.trials, registry.PRIOR_TRIALS)
        reg.register(self.rule(), '2026-11-13', ['2026-11-12'], trials=4)
        self.assertEqual(reg.trials, registry.PRIOR_TRIALS + 4)
        with self.assertRaises(registry.RegistryError):
            reg.register(self.rule(), '2026-11-13', [])                  # a second registration of an id
        with self.assertRaises(registry.RegistryError):
            reg.move('r1', 'shadow')                                     # proposed -> shadow skips the sweep
        reg.move('r1', 'swept')
        reg.move('r1', 'shadow')
        reg.move('r1', 'proposal')
        with self.assertRaises(registry.RegistryError):
            reg.move('r1', 'proposed')

    def test_a_hypothesis_needs_a_frozen_rule_before_shadow(self):
        reg = registry.Registry()
        h = hyp(id='hyp-a')
        reg.register(h, '2026-11-13', ['2026-11-12'], trials=4, kind='hypothesis')
        reg.move('hyp-a', 'swept')
        with self.assertRaises(registry.RegistryError):
            reg.move('hyp-a', 'shadow')
        reg.freeze('hyp-a', self.rule(id='hyp-a@0.1', threshold=0.1), '2026-11-13')
        reg.move('hyp-a', 'shadow')
        self.assertEqual(reg.state['hyp-a']['frozen_hash'], rules.rule_hash(self.rule(id='hyp-a@0.1', threshold=0.1)))

    def test_a_curve_edit_waits_for_the_owner(self):
        reg = registry.Registry()
        reg.register(self.rule(id='c1', feature='rank'), '2026-11-13', [])
        reg.move('c1', 'swept')
        with self.assertRaises(registry.RegistryError):
            reg.move('c1', 'shadow')
        reg.owner_ok('c1')
        reg.move('c1', 'shadow')

    def test_registry_replays_from_its_file(self):
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'registry.jsonl')
            a = registry.Registry(p)
            a.register(self.rule(), '2026-11-13', ['2026-11-12'], trials=3)
            a.move('r1', 'swept')
            b = registry.Registry(p)
            self.assertEqual(b.state['r1']['status'], 'swept')
            self.assertEqual(b.trials, a.trials)

    def test_shadow_refuses_a_changed_rule_and_pools_days(self):
        rule = self.rule()
        h = rules.rule_hash(rule)
        with self.assertRaises(shadow.ShadowError):
            shadow.shadow_day(self.rule(threshold=0.4), h, [])
        rows = make_rows(9, days=8, per_day=120, plant=-2.5)
        results = []
        for d in range(8):
            day_rows = [r for r in rows if sweep.day_of(r) == day_str(d)]
            results.append(shadow.shadow_day(rule, h, day_rows))
        v = shadow.shadow_verdict(results)
        self.assertEqual(v['status'], 'ready')
        self.assertEqual(shadow.shadow_verdict(results[:2])['status'], 'collecting')
        # re-running a day replaces it, not doubles it
        self.assertEqual(shadow.shadow_verdict(results + results[:2])['days'], 8)

    def test_a_faded_rule_is_called_faded(self):
        rule = self.rule()
        h = rules.rule_hash(rule)
        rows = make_rows(10, days=8, per_day=120, plant=+2.5)   # the flagged trips now do better: the rule hurts
        results = [shadow.shadow_day(rule, h, [r for r in rows if sweep.day_of(r) == day_str(d)]) for d in range(8)]
        self.assertEqual(shadow.shadow_verdict(results)['status'], 'faded')

    def test_the_floor_holds_back_rules_that_skip_too_much_together(self):
        rows = make_rows(11, days=1, per_day=200)
        a = self.rule(id='a', threshold=0.1)        # ~10% of trips
        b = self.rule(id='b', threshold=0.12)       # overlaps a almost entirely
        c = self.rule(id='c', feature='entry_px', op='lt', threshold=0.5)   # half the trips
        kept, held, retention = shadow.ruleset_floor([a, b, c], rows)
        self.assertIn('a', kept)
        self.assertIn('c', held)
        self.assertGreaterEqual(retention, 0.85)


if __name__ == '__main__':
    unittest.main()
