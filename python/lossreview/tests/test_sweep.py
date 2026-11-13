import random
import unittest

from lossreview import registry, rules, shadow, sweep

EARLY = ['2000-01-01']   # a generating day long before the synthetic ones
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
        res = sweep.sweep(hyp(thresholds=[0.04, 0.08, 0.12]), rows, generating_days=EARLY)
        best = res['best']
        self.assertEqual(best['verdict'], 'candidate')
        self.assertGreater(best['pooled']['mean'], 0)
        self.assertGreaterEqual(best['flagged'], sweep.MIN_FLAGGED)

    def test_pure_noise_is_not_called_a_candidate(self):
        false = 0
        for seed in range(60):
            res = sweep.sweep(hyp(), make_rows(100 + seed, days=8, per_day=60), generating_days=EARLY)
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
        res = sweep.sweep(hyp(), make_rows(3, days=3, per_day=80, plant=-3), generating_days=EARLY)
        self.assertTrue(all(s['verdict'] == 'insufficient_days' for s in res['scored']))
        res = sweep.sweep(hyp(thresholds=[0.01]), make_rows(4, days=8, per_day=40, plant=-3), generating_days=EARLY)
        self.assertTrue(all(s['verdict'] == 'insufficient_flags' for s in res['scored']))

    def test_a_skip_candidate_over_the_floor_is_dropped_before_scoring(self):
        rows = make_rows(5, days=8, per_day=80, plant=-3.0, cut=0.5)
        res = sweep.sweep(hyp(thresholds=[0.5, 0.1]), rows, generating_days=EARLY)
        self.assertEqual(res['dropped'], 1)                               # 0.5 flags half the trips: far past 15%, no outcome read
        self.assertEqual(res['k'], 1)
        self.assertEqual([s['rule']['threshold'] for s in res['scored']], [0.1])

    def test_the_floor_still_gates_a_verdict_when_the_pooled_share_is_over(self):
        rows = make_rows(5, days=8, per_day=80, plant=-3.0, cut=0.5)
        sc = sweep.scoring_rows(rows, EARLY)
        res = sweep.score_rule({'id': 'x', 'lever': 'skip', 'feature': 'frac_elapsed_at_entry', 'op': 'lt', 'threshold': 0.5}, sc)
        self.assertEqual(sweep.verdict(res, 1)[0], 'floor')

    def test_beating_a_random_draw_is_not_enough_when_the_rule_still_loses_money_absolute(self):
        # a profitable lane (mean +1): the flagged trips earn 0.5 less than the rest, so skipping them loses money, but
        # less than skipping random trips would on average? No: skipping any trip loses +1; the flagged lose less, so the gap is
        # positive while the absolute gain is negative.
        rnd = random.Random(21)
        rows = []
        for d in range(6):
            for i in range(350):
                x = rnd.random()
                rows.append({'closed_t': DAY0 + 86400 * d + 3600 + i * 60, 'entry_px': 0.5, 'frac_elapsed_at_entry': x,
                             'pnl': rnd.gauss(1.0, 1.0) - (0.5 if x < 0.12 else 0.0)})
        res = sweep.sweep(hyp(thresholds=[0.12]), rows, generating_days=EARLY)
        s = res['scored'][0]
        self.assertGreater(s['pooled']['mean'], 0)       # beats a random skip
        self.assertLess(s['gain_sum'], 0)                # but skipping them costs money
        self.assertNotEqual(s['verdict'], 'candidate')

    def test_empty_generating_days_is_an_error_not_a_free_pass(self):
        with self.assertRaises(ValueError):
            sweep.sweep(hyp(), make_rows(1), generating_days=[])

    def test_a_look_scores_exactly_its_first_days(self):
        rows = make_rows(12, days=10, per_day=200, plant=-4.0, cut=0.12)
        res = sweep.sweep(hyp(thresholds=[0.12]), rows, generating_days=EARLY, max_days=4)
        self.assertEqual(res['days'], 4)
        self.assertEqual([d['day'] for d in res['scored'][0]['days']], sorted({sweep.day_of(r) for r in rows})[:4])

    def test_looks_are_paid_for_in_the_corrected_p(self):
        rows = make_rows(13, days=6, per_day=350, plant=-1.0, cut=0.12)
        sc = sweep.scoring_rows(rows, EARLY)
        res = sweep.score_rule({'id': 'x', 'lever': 'skip', 'feature': 'frac_elapsed_at_entry', 'op': 'lt', 'threshold': 0.12}, sc)
        _, p1 = sweep.verdict(res, 1, looks=1)
        _, p3 = sweep.verdict(res, 1, looks=3)
        self.assertAlmostEqual(p3, min(1.0, p1 * 3))

    def test_a_dial_rule_is_scored_against_a_matched_multiplier(self):
        rows = make_rows(6, days=6, per_day=350, plant=-4.0, cut=0.12)
        res = sweep.sweep(hyp(lever='dial', thresholds=[0.12]), rows, generating_days=EARLY)
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
        res = sweep.sweep(hyp(lever='dial', neighbor_features=['spot_vs_strike_bps_pre']), rows, generating_days=EARLY)
        self.assertEqual(res['k'], 4 + 3)                      # a dial has no floor: the three quartile cuts all count
        self.assertTrue(all(s['k'] == 7 for s in res['scored']))
        res = sweep.sweep(hyp(neighbor_features=['spot_vs_strike_bps_pre']), rows, generating_days=EARLY)
        cut = [s['rule']['threshold'] for s in res['scored'] if s['rule']['feature'] == 'spot_vs_strike_bps_pre']
        self.assertEqual(len(cut), 3)                          # a skip's neighbor cuts are the 5/10/15% tails: the ones that fit the floor
        self.assertTrue(all(c < -10 for c in cut))

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

    def candidate(self, rule):
        """A score event as daily.run_sweep writes it: the best candidate of the look is this rule."""
        return {'day': '2026-11-13', 'look': 0, 'best': {'rule': rule, 'verdict': 'candidate', 'p_adj': 0.001}}

    def test_registry_counts_trials_and_enforces_the_moves(self):
        reg = registry.Registry()
        self.assertEqual(reg.trials, registry.PRIOR_TRIALS)
        reg.register(self.rule(), '2026-11-13', ['2026-11-12'], trials=4)
        self.assertEqual(reg.trials, registry.PRIOR_TRIALS + 4)
        with self.assertRaises(registry.RegistryError):
            reg.register(self.rule(), '2026-11-13', ['2026-11-12'])          # a second registration of an id
        with self.assertRaises(registry.RegistryError):
            reg.register(self.rule(id='r2'), '2026-11-13', ['2026-11-12'], trials=-40)   # the counter only goes up
        with self.assertRaises(registry.RegistryError):
            reg.register(self.rule(id='r3'), '2026-11-13', [])               # no generating days: scoring would fail open
        with self.assertRaises(registry.RegistryError):
            reg.move('r1', 'shadow')                                         # proposed -> shadow skips the sweep
        with self.assertRaises(registry.RegistryError):
            reg.move('r1', 'swept')                                          # nothing scored yet
        reg.score('r1', self.candidate(self.rule()))
        reg.move('r1', 'swept')
        reg.move('r1', 'shadow')
        with self.assertRaises(registry.RegistryError):
            reg.move('r1', 'proposal')                                       # no shadow evidence yet

    def test_a_hypothesis_needs_a_frozen_rule_before_shadow_and_freezes_once(self):
        reg = registry.Registry()
        reg.register(hyp(id='hyp-a'), '2026-11-13', ['2026-11-12'], trials=4, kind='hypothesis')
        reg.score('hyp-a', self.candidate(self.rule(id='hyp-a@0.1', threshold=0.1)))
        reg.move('hyp-a', 'swept')
        with self.assertRaises(registry.RegistryError):
            reg.move('hyp-a', 'shadow')
        frozen = self.rule(id='hyp-a@0.1', threshold=0.1)
        reg.freeze('hyp-a', frozen, '2026-11-15')
        self.assertEqual(reg.state['hyp-a']['frozen_hash'], rules.rule_hash(frozen))
        with self.assertRaises(registry.RegistryError):
            reg.freeze('hyp-a', self.rule(id='hyp-a@0.2', threshold=0.2), '2026-11-15')    # a changed rule is a new trial
        reg.move('hyp-a', 'shadow')
        with self.assertRaises(registry.RegistryError):
            reg.freeze('hyp-a', self.rule(id='hyp-a@0.2', threshold=0.2), '2026-11-16')    # and not from shadow

    def test_shadow_must_name_the_frozen_rule_as_the_sweeps_candidate(self):
        reg = registry.Registry()
        reg.register(hyp(id='hyp-b'), '2026-11-13', ['2026-11-12'], trials=4, kind='hypothesis')
        reg.score('hyp-b', self.candidate(self.rule(id='hyp-b@0.1', threshold=0.1)))
        reg.move('hyp-b', 'swept')
        reg.freeze('hyp-b', self.rule(id='hyp-b@0.4', threshold=0.4), '2026-11-15')        # not the rule the sweep named
        with self.assertRaises(registry.RegistryError):
            reg.move('hyp-b', 'shadow')

    def test_a_curve_edit_waits_for_the_owner_and_the_word_is_for_that_rule_only(self):
        reg = registry.Registry()
        reg.register(self.rule(id='c1', feature='rank'), '2026-11-13', ['2026-11-12'])
        reg.score('c1', self.candidate(self.rule(id='c1', feature='rank')))
        reg.move('c1', 'swept')
        with self.assertRaises(registry.RegistryError):
            reg.move('c1', 'shadow')
        reg.owner_ok('c1')
        reg.move('c1', 'shadow')
        # an approval for one frozen rule does not carry to another hypothesis' rule on a different curve column
        reg.register(hyp(id='c2', feature='rank'), '2026-11-13', ['2026-11-12'], kind='hypothesis')
        reg.score('c2', self.candidate(self.rule(id='c2@1', feature='rank', threshold=1)))
        reg.move('c2', 'swept')
        reg.freeze('c2', self.rule(id='c2@1', feature='rank', threshold=1), '2026-11-14')
        with self.assertRaises(registry.RegistryError):
            reg.move('c2', 'shadow')
        reg.owner_ok('c2')
        reg.move('c2', 'shadow')
        self.assertNotEqual(reg.state['c1']['owner_ok_hash'], reg.state['c2']['owner_ok_hash'])

    def test_registry_replays_from_its_file(self):
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'registry.jsonl')
            a = registry.Registry(p)
            a.register(self.rule(), '2026-11-13', ['2026-11-12'], trials=3)
            a.score('r1', self.candidate(self.rule()))
            a.move('r1', 'swept')
            b = registry.Registry(p)
            self.assertEqual(b.state['r1']['status'], 'swept')
            self.assertEqual(b.trials, a.trials)

    def shadow_results(self, rule, h, plant, days=12, seed=9):
        rows = make_rows(seed, days=days, per_day=300, plant=plant, cut=0.12)
        return [shadow.shadow_day(rule, h, day_str(d), [r for r in rows if sweep.day_of(r) == day_str(d)]) for d in range(days)]

    def test_shadow_refuses_a_changed_rule(self):
        rule = self.rule(threshold=0.12)
        with self.assertRaises(shadow.ShadowError):
            shadow.shadow_day(self.rule(threshold=0.4), rules.rule_hash(rule), day_str(0), [])

    def test_shadow_is_ready_at_a_fixed_look_and_only_with_enough_unseen_days(self):
        rule = self.rule(threshold=0.12)
        h = rules.rule_hash(rule)
        res = self.shadow_results(rule, h, plant=-4.0)
        self.assertEqual(shadow.shadow_verdict(res[:4], h, None)['status'], 'collecting')
        v = shadow.shadow_verdict(res[:5], h, None)
        self.assertEqual((v['status'], v['look']), ('ready', 5))
        # re-running a day replaces it, not doubles it
        self.assertEqual(shadow.shadow_verdict(res[:5] + res[:2], h, None)['days'], 5)
        # days up to the sweep window never count
        self.assertEqual(shadow.shadow_verdict(res[:5], h, day_str(2))['days'], 2)
        # results of another rule hash never pool in
        self.assertEqual(shadow.shadow_verdict(res[:5], 'deadbeef', None)['days'], 0)

    def test_a_night_without_trips_is_not_a_day(self):
        rule = self.rule(threshold=0.12)
        h = rules.rule_hash(rule)
        empty = shadow.shadow_day(rule, h, day_str(3), [])
        self.assertEqual(empty['trips'], 0)
        self.assertEqual(shadow.shadow_verdict([empty], h, None)['days'], 0)
        # and a day's result only scores that day's trips
        rows = make_rows(4, days=2, per_day=100)
        self.assertEqual(shadow.shadow_day(rule, h, day_str(0), rows)['trips'], 100)

    def test_a_rule_that_hurts_fades_at_the_last_look_not_before(self):
        rule = self.rule(threshold=0.12)
        h = rules.rule_hash(rule)
        res = self.shadow_results(rule, h, plant=+4.0)     # the flagged trips now do better: skipping them hurts
        self.assertEqual(shadow.shadow_verdict(res[:9], h, None)['status'], 'collecting')
        self.assertEqual(shadow.shadow_verdict(res[:10], h, None)['status'], 'faded')

    def test_beating_the_placebo_is_not_ready_when_the_rule_still_loses_money(self):
        rule = self.rule(threshold=0.12)
        h = rules.rule_hash(rule)
        rnd = random.Random(33)
        results = []
        for d in range(6):
            rows = [{'closed_t': DAY0 + 86400 * d + 3600 + i * 60, 'entry_px': 0.5, 'frac_elapsed_at_entry': rnd.random(),
                     'pnl': 0.0} for i in range(350)]
            for r in rows:
                r['pnl'] = rnd.gauss(1.0, 1.0) - (0.5 if r['frac_elapsed_at_entry'] < 0.12 else 0.0)
            results.append(shadow.shadow_day(rule, h, day_str(d), rows))
        v = shadow.shadow_verdict(results[:5], h, None)
        self.assertGreater(v['gap_mean'], 0)
        self.assertLess(v['gain_sum'], 0)
        self.assertNotEqual(v['status'], 'ready')

    def test_registry_checks_shadow_results_and_proposal_needs_a_ready_verdict(self):
        rule = self.rule(id='s1', threshold=0.12)
        h = rules.rule_hash(rule)
        reg = registry.Registry()
        reg.register(rule, day_str(-1), [day_str(-2)])
        reg.score('s1', self.candidate(rule))
        reg.move('s1', 'swept')
        reg.move('s1', 'shadow')
        res = self.shadow_results(rule, h, plant=-4.0)
        with self.assertRaises(registry.RegistryError):
            reg.shadow('s1', dict(res[3], hash='other'))                       # another rule's hash
        for r in res[:4]:
            reg.shadow('s1', r)
        with self.assertRaises(registry.RegistryError):
            reg.move('s1', 'proposal')                                         # four days: still collecting
        reg.shadow('s1', res[4])
        reg.move('s1', 'proposal')

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
