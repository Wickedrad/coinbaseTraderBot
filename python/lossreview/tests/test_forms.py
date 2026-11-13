"""Closed vocabularies and validators of the review layer, on synthetic data. Run: PYTHONPATH=python python3 -m unittest discover -s python/lossreview/tests"""
import unittest

from lossreview import forms, schema, triage


def hyp(**kw):
    """A clean hypothesis; override or add fields per test (a value of None removes the key)."""
    h = {'id': 'late-cheap-skip', 'loss_class': 'WRONG_SIDE', 'lever': 'skip', 'feature': 'frac_elapsed_at_entry', 'op': 'gt',
         'thresholds': [0.5, 0.6, 0.7], 'neighbor_features': ['entry_px'],
         'mechanism': 'Late entries leave too little time for a cheap side to recover.', 'cites': ['entry_px', 'left_at_entry_s']}
    h.update(kw)
    return {k: v for k, v in h.items() if v is not None}


def adv(**kw):
    a = {'hypothesis_id': 'late-cheap-skip', 'verdict': 'refuted', 'reasons': ['fee_artifact'], 'note': 'The fee schedule explains it.'}
    a.update(kw)
    return {k: v for k, v in a.items() if v is not None}


class VocabularyTests(unittest.TestCase):
    def test_levers_and_their_priority(self):
        self.assertEqual(set(forms.LEVERS), {'dial', 'maker', 'strike', 'exit', 'skip'})
        o = forms.LEVER_ORDER
        self.assertEqual(set(o), set(forms.LEVERS))
        self.assertLess(o['dial'], o['maker'])
        self.assertEqual(o['maker'], o['strike'])
        self.assertLess(o['strike'], o['exit'])
        self.assertLess(o['exit'], o['skip'])
        self.assertEqual(set(forms.LEVER_HELP), set(forms.LEVERS))

    def test_ops_verdicts_and_reasons(self):
        self.assertEqual(set(forms.OPS), {'lt', 'gt', 'between', 'eq'})
        self.assertEqual(set(forms.VERDICTS), {'survives', 'refuted', 'unclear'})
        self.assertEqual(set(forms.ADVERSARY_REASONS), {'confounded_by_price', 'confounded_by_coin', 'clustered_in_time', 'too_few_trips',
                                                        'winner_control_matches', 'hindsight_feature', 'overlaps_curve', 'fee_artifact', 'other'})

    def test_hypotheses_explain_only_reviewable_loser_classes(self):
        self.assertEqual(set(forms.HYPOTHESIS_CLASSES), {'FEE_ONLY', 'CUT_THEN_WON', 'SOLD_THEN_WON', 'RIGHT_THEN_REVERSED', 'WRONG_SIDE'})
        self.assertTrue(set(forms.HYPOTHESIS_CLASSES) <= set(triage.LOSER_CLASSES))

    def test_feature_and_outcome_columns_partition_the_registry(self):
        feats, outs = set(forms.FEATURE_COLUMNS), set(forms.OUTCOME_COLUMNS)
        self.assertFalse(feats & outs)
        self.assertTrue(all(schema.ex_ante(c) for c in feats))
        self.assertFalse(any(schema.ex_ante(c) for c in outs))
        self.assertEqual(feats | outs | forms.IDENTIFIER_COLUMNS, set(schema.COLUMNS))
        self.assertTrue(schema.CURVE_COLUMNS <= feats)
        for c in ('pnl', 'won', 'exit_event', 'best_bid_held', 'bid_2m', 'spot_entry', 'result', 'side_settles_win', 'legs', 'fees'):
            self.assertIn(c, outs)


class TagTests(unittest.TestCase):
    def test_about_twenty_tags(self):
        self.assertGreaterEqual(len(forms.TAGS), 18)
        for t in ('late_entry', 'cheap_side', 'hourly_far_strike', 'pair_call', 'no_side', 'big_count', 'stale_call',
                  'early_window_entry', 'fee_heavy_small_edge'):
            self.assertIn(t, forms.TAGS)

    def test_every_tag_is_measured_by_ex_ante_columns_that_exist(self):
        for tag, cols in forms.TAGS.items():
            self.assertTrue(cols, tag)
            for c in cols:
                self.assertIn(c, schema.COLUMNS, '%s: %s' % (tag, c))
                self.assertTrue(schema.ex_ante(c), '%s: %s is not ex-ante' % (tag, c))

    def test_every_tag_has_a_description(self):
        self.assertEqual(set(forms.TAG_HELP), set(forms.TAGS))
        self.assertTrue(all(forms.TAG_HELP.values()))

    def test_valid_tags(self):
        self.assertEqual(forms.validate_tags(['late_entry', 'no_side']), (True, []))
        self.assertEqual(forms.validate_tags([]), (True, []))
        self.assertEqual(forms.validate_tags(('big_count',)), (True, []))
        self.assertTrue(forms.validate_tags(list(forms.TAGS))[0])

    def test_unknown_duplicate_and_malformed_tags(self):
        ok, errs = forms.validate_tags(['late_entry', 'made_up'])
        self.assertFalse(ok)
        self.assertIn('made_up', errs[0])
        ok, errs = forms.validate_tags(['late_entry', 'late_entry'])
        self.assertFalse(ok)
        self.assertIn('duplicate', errs[0])
        self.assertFalse(forms.validate_tags('late_entry')[0])
        self.assertFalse(forms.validate_tags(None)[0])
        self.assertFalse(forms.validate_tags([3])[0])
        self.assertFalse(forms.validate_tags([['late_entry']])[0])   # unhashable item: an error, not an exception
        self.assertFalse(forms.validate_tags(['Late_Entry'])[0])


class HypothesisTests(unittest.TestCase):
    def check(self, h):
        return forms.validate_hypothesis(h)

    def assertRejected(self, h, fragment):
        ok, errors, _ = self.check(h)
        self.assertFalse(ok, h)
        self.assertTrue(any(fragment in e for e in errors), '%r not in %r' % (fragment, errors))

    def test_a_clean_hypothesis_passes_without_flags(self):
        self.assertEqual(self.check(hyp()), (True, [], []))

    def test_neighbors_and_cites_are_optional(self):
        self.assertEqual(self.check(hyp(neighbor_features=None, cites=None)), (True, [], []))
        self.assertEqual(self.check(hyp(neighbor_features=[], cites=[])), (True, [], []))

    def test_not_an_object(self):
        for bad in (None, [], 'text', 3):
            ok, errors, flags = self.check(bad)
            self.assertFalse(ok)
            self.assertEqual(flags, [])
            self.assertTrue(errors)

    def test_missing_and_unknown_keys(self):
        for k in forms.REQUIRED_KEYS:
            self.assertRejected(hyp(**{k: None}), "missing key '%s'" % k)
        self.assertRejected(hyp(confidence=0.9), "unknown key 'confidence'")
        self.assertRejected(hyp(**{'thresholds_extra': [1]}), 'unknown key')

    def test_all_problems_are_reported_together(self):
        ok, errors, _ = self.check(hyp(lever='nope', op='nope', feature='pnl'))
        self.assertFalse(ok)
        self.assertGreaterEqual(len(errors), 3)

    def test_id_pattern(self):
        for good in ('abc', 'a-b_c9', 'x' * 40, '007'):
            self.assertTrue(self.check(hyp(id=good))[0], good)
        for bad in ('ab', 'x' * 41, 'Late-Skip', 'late skip', 'late.skip', 'abc\n', '', None, 7, ['abc']):
            self.assertFalse(self.check(dict(hyp(), id=bad))[0], repr(bad))

    def test_loss_class(self):
        for c in forms.HYPOTHESIS_CLASSES:
            self.assertTrue(self.check(hyp(loss_class=c))[0], c)
        for c in ('FIDELITY', 'OTHER_LANE', 'UNKNOWN_DATA', 'UNEXPLAINED'):
            self.assertRejected(hyp(loss_class=c), 'not reviewed')
        for c in ('WIN', 'wrong_side', '', None, ['WRONG_SIDE']):
            self.assertFalse(self.check(dict(hyp(), loss_class=c))[0], repr(c))

    def test_one_lever_from_the_closed_set(self):
        for lv in forms.LEVERS:
            self.assertTrue(self.check(hyp(lever=lv))[0], lv)
        self.assertRejected(hyp(lever='raise_stake'), 'lever')
        self.assertRejected(hyp(lever=['dial', 'skip']), 'lever')
        self.assertRejected(hyp(lever='dial,skip'), 'lever')
        self.assertRejected(hyp(lever=''), 'lever')
        self.assertRejected(dict(hyp(), lever=5), 'lever')

    def test_op_from_the_closed_set(self):
        self.assertRejected(hyp(op='ge'), 'op must be')
        self.assertRejected(hyp(op=['lt']), 'op must be')

    # features -------------------------------------------------------------------------------------------------------
    def test_every_outcome_column_is_refused_as_feature_neighbor_and_cite(self):
        for col in forms.OUTCOME_COLUMNS:
            self.assertFalse(self.check(hyp(feature=col, op='lt', thresholds=[1]))[0], col)
            self.assertFalse(self.check(hyp(neighbor_features=[col]))[0], col)
            self.assertFalse(self.check(hyp(cites=[col]))[0], col)

    def test_outcome_error_names_when_the_column_is_known(self):
        self.assertRejected(hyp(feature='best_bid_held', op='gt', thresholds=[0.5]), 'known only at close')
        self.assertRejected(hyp(cites=['spot_entry']), 'plus60s')

    def test_unknown_columns(self):
        self.assertRejected(hyp(feature='moon_phase'), 'unknown column')
        self.assertRejected(hyp(neighbor_features=['moon_phase']), 'unknown column')
        self.assertRejected(hyp(cites=['moon_phase']), 'unknown column')

    def test_columns_must_be_strings(self):
        for bad in (['entry_px'], 7, None, {'a': 1}):
            ok, errors, _ = self.check(dict(hyp(), feature=bad))
            self.assertFalse(ok)
            ok, errors, _ = self.check(dict(hyp(), cites=[bad]))
            self.assertFalse(ok)
            ok, errors, _ = self.check(dict(hyp(), neighbor_features=[bad]))
            self.assertFalse(ok)

    def test_ex_ante_columns_pass(self):
        for col in ('entry_px', 'spot_vs_strike_bps_pre', 'call_age_s', 'frac_elapsed_at_entry', 'count', 'stake', 'plan_price'):
            self.assertEqual(self.check(hyp(feature=col, neighbor_features=[]))[0], True, col)

    def test_identifiers_are_not_features(self):
        for col in sorted(forms.IDENTIFIER_COLUMNS):
            self.assertRejected(hyp(feature=col, op='eq', thresholds=['x']), 'identifier')
            self.assertRejected(hyp(cites=[col]), 'identifier')
            self.assertRejected(hyp(neighbor_features=[col]), 'identifier')

    def test_labels_take_eq_only(self):
        self.assertEqual(self.check(hyp(feature='coin', op='eq', thresholds=['BTC', 'ETH'], neighbor_features=[]))[0], True)
        self.assertRejected(hyp(feature='kind', op='gt', thresholds=[1]), 'is a label')
        self.assertRejected(hyp(feature='side', op='between', thresholds=[0, 1]), 'is a label')

    # curve columns --------------------------------------------------------------------------------------------------
    def test_a_curve_column_is_flagged_not_refused(self):
        for col in sorted(schema.CURVE_COLUMNS):
            op, thr = ('eq', ['x']) if col in forms.CATEGORICAL_COLUMNS else ('gt', [1])
            ok, errors, flags = self.check(hyp(feature=col, op=op, thresholds=thr, neighbor_features=[]))
            self.assertTrue(ok, '%s %s' % (col, errors))
            self.assertEqual(flags, ['curve_edit'], col)

    def test_curve_neighbor_or_cite_is_flagged_too(self):
        self.assertEqual(self.check(hyp(neighbor_features=['rank'])), (True, [], ['curve_edit']))
        self.assertEqual(self.check(hyp(cites=['heat'])), (True, [], ['curve_edit']))
        self.assertEqual(self.check(hyp(neighbor_features=['entry_px', 'weight'], cites=['of'])), (True, [], ['curve_edit']))

    def test_flag_is_reported_once_and_also_when_the_hypothesis_is_otherwise_bad(self):
        ok, errors, flags = self.check(hyp(feature='rank', neighbor_features=['heat'], cites=['weight'], lever='nope'))
        self.assertFalse(ok)
        self.assertEqual(flags, ['curve_edit'])

    def test_no_flag_for_non_curve_columns(self):
        self.assertEqual(self.check(hyp(feature='entry_px', neighbor_features=['stake', 'count'], cites=['call_age_s']))[2], [])

    # neighbors ------------------------------------------------------------------------------------------------------
    def test_at_most_two_neighbors(self):
        self.assertTrue(self.check(hyp(neighbor_features=['entry_px', 'stake']))[0])
        self.assertRejected(hyp(neighbor_features=['entry_px', 'stake', 'count']), 'at most 2')

    def test_neighbor_differs_from_feature_and_from_each_other(self):
        self.assertRejected(hyp(neighbor_features=['frac_elapsed_at_entry']), 'repeats the feature')
        self.assertRejected(hyp(neighbor_features=['entry_px', 'entry_px']), 'listed twice')
        self.assertRejected(hyp(neighbor_features='entry_px'), 'must be a list')

    def test_cites_must_be_a_list(self):
        self.assertRejected(hyp(cites='entry_px'), 'must be a list')
        self.assertRejected(dict(hyp(), cites=None), 'must be a list')
        self.assertRejected(dict(hyp(), neighbor_features=None), 'must be a list')

    # thresholds -----------------------------------------------------------------------------------------------------
    def test_threshold_count_bounds(self):
        self.assertTrue(self.check(hyp(thresholds=[0.5]))[0])
        self.assertTrue(self.check(hyp(thresholds=[i / 100 for i in range(12)]))[0])
        self.assertRejected(hyp(thresholds=[i / 100 for i in range(13)]), '13 items')
        self.assertRejected(hyp(thresholds=[]), '0 items')
        self.assertRejected(hyp(thresholds=0.5), 'thresholds must be a list')
        self.assertRejected(hyp(thresholds='0.5'), 'thresholds must be a list')

    def test_numeric_ops_need_finite_numbers(self):
        for op in ('lt', 'gt'):
            self.assertTrue(self.check(hyp(op=op, thresholds=[1, 2.5, -3]))[0])
            self.assertRejected(hyp(op=op, thresholds=['0.5']), 'finite numbers')
            self.assertRejected(hyp(op=op, thresholds=[True]), 'finite numbers')
            self.assertRejected(hyp(op=op, thresholds=[None]), 'finite numbers')
            self.assertRejected(hyp(op=op, thresholds=[float('nan')]), 'finite numbers')
            self.assertRejected(hyp(op=op, thresholds=[float('inf')]), 'finite numbers')

    def test_between_needs_exactly_two_ordered_numbers(self):
        self.assertTrue(self.check(hyp(op='between', thresholds=[0.2, 0.4]))[0])
        self.assertRejected(hyp(op='between', thresholds=[0.2, 0.4, 0.6]), 'exactly 2')
        self.assertRejected(hyp(op='between', thresholds=[0.2]), 'exactly 2')
        self.assertRejected(hyp(op='between', thresholds=[0.4, 0.2]), 'lo < hi')
        self.assertRejected(hyp(op='between', thresholds=[0.4, 0.4]), 'lo < hi')
        self.assertRejected(hyp(op='between', thresholds=['a', 'b']), 'finite numbers')

    def test_eq_takes_strings_or_booleans(self):
        self.assertTrue(self.check(hyp(feature='coin', op='eq', thresholds=['BTC'], neighbor_features=[]))[0])
        self.assertTrue(self.check(hyp(feature='coin', op='eq', thresholds=[True, False], neighbor_features=[]))[0])
        for bad in ([5], [None], [''], ['  '], ['x' * 41], [['a']], [1.5]):
            self.assertFalse(self.check(hyp(feature='coin', op='eq', thresholds=bad, neighbor_features=[]))[0], bad)

    def test_repeated_thresholds(self):
        self.assertRejected(hyp(thresholds=[0.5, 0.5]), 'repeat')
        self.assertRejected(hyp(thresholds=[1, 1.0]), 'repeat')
        self.assertRejected(hyp(feature='coin', op='eq', thresholds=['BTC', 'btc'], neighbor_features=[]), 'repeat')

    def test_a_bad_op_does_not_hide_the_threshold_count(self):
        ok, errors, _ = self.check(hyp(op='nope', thresholds=list(range(13))))
        self.assertFalse(ok)
        self.assertTrue(any('13 items' in e for e in errors))

    # mechanism ------------------------------------------------------------------------------------------------------
    def test_mechanism_length(self):
        self.assertTrue(self.check(hyp(mechanism='x' * 240))[0])
        self.assertRejected(hyp(mechanism='x' * 241), '241 characters')

    def test_mechanism_must_be_text(self):
        for bad in ('', '   ', None, 5, ['a']):
            self.assertFalse(self.check(dict(hyp(), mechanism=bad))[0], repr(bad))

    def test_mechanism_naming_an_outcome_column_is_a_leak(self):
        for text in ('The pnl was poor.', 'best_bid_held fell.', 'Look at BID_2M.', 'result: lost', 'it won', 'high fees',
                     '(exit_event) says cut', 'spot_entry moved', 'pnl.', 'a-pnl-b'):
            self.assertRejected(hyp(mechanism=text), 'hindsight leak')

    def test_leak_check_is_per_whole_word(self):
        for text in ('The fee per dollar is high near 50c.', 'Results vary by hour.', 'Winners and losers differ.',
                     'The pnl_like thing', 'Stake sizing is big.', 'pnlx is not a column', 'bid_2mx'):
            ok, errors, _ = self.check(hyp(mechanism=text))
            self.assertFalse(any('hindsight' in e for e in errors), '%s: %s' % (text, errors))

    def test_leak_error_names_the_columns(self):
        ok, errors, _ = self.check(hyp(mechanism='pnl and best_bid_held'))
        self.assertIn("['best_bid_held', 'pnl']", ' '.join(errors))

    def test_outcome_words_helper(self):
        self.assertEqual(forms.outcome_words('Pnl then fees; entry_px fine'), ['fees', 'pnl'])
        self.assertEqual(forms.outcome_words(''), [])
        self.assertEqual(forms.outcome_words(None), [])

    def test_mechanism_must_not_carry_a_ticker(self):
        self.assertRejected(hyp(mechanism='Like KXBTC15M-26NOV121015-15 did.'), 'carries a ticker')
        self.assertRejected(hyp(mechanism='see kxethd-26nov1210'), 'carries a ticker')

    def test_a_hypothesis_is_not_modified(self):
        h = hyp()
        snapshot = {k: (list(v) if isinstance(v, list) else v) for k, v in h.items()}
        self.check(h)
        self.assertEqual(h, snapshot)


class AdversaryTests(unittest.TestCase):
    def test_valid_verdicts(self):
        self.assertEqual(forms.validate_adversary(adv()), (True, []))
        self.assertEqual(forms.validate_adversary(adv(verdict='survives', reasons=[])), (True, []))
        self.assertTrue(forms.validate_adversary(adv(verdict='survives', reasons=['too_few_trips']))[0])
        self.assertTrue(forms.validate_adversary(adv(verdict='unclear', reasons=['other', 'clustered_in_time']))[0])
        self.assertTrue(forms.validate_adversary(adv(note=None))[0])      # the note is optional
        self.assertTrue(forms.validate_adversary(adv(note='x' * 300))[0])
        for r in forms.ADVERSARY_REASONS:
            self.assertTrue(forms.validate_adversary(adv(reasons=[r]))[0], r)

    def test_reasons_are_required_unless_it_survives(self):
        for v in ('refuted', 'unclear'):
            ok, errors = forms.validate_adversary(adv(verdict=v, reasons=[]))
            self.assertFalse(ok)
            self.assertIn('needs at least one reason', ' '.join(errors))
        self.assertFalse(forms.validate_adversary(adv(reasons=None))[0])

    def test_unknown_reason_or_verdict(self):
        self.assertFalse(forms.validate_adversary(adv(reasons=['because']))[0])
        self.assertFalse(forms.validate_adversary(adv(reasons=['fee_artifact', 'because']))[0])
        self.assertFalse(forms.validate_adversary(adv(reasons='fee_artifact'))[0])
        self.assertFalse(forms.validate_adversary(adv(reasons=['fee_artifact', 'fee_artifact']))[0])
        self.assertFalse(forms.validate_adversary(adv(reasons=[['fee_artifact']]))[0])
        for v in ('maybe', 'SURVIVES', '', None, ['survives']):
            self.assertFalse(forms.validate_adversary(dict(adv(), verdict=v))[0], repr(v))

    def test_hypothesis_id_and_extra_keys(self):
        for bad in ('x', 'Not An Id', None, 5):
            self.assertFalse(forms.validate_adversary(dict(adv(), hypothesis_id=bad))[0], repr(bad))
        self.assertFalse(forms.validate_adversary(adv(hypothesis_id=None))[0])
        ok, errors = forms.validate_adversary(adv(score=3))
        self.assertFalse(ok)
        self.assertIn("unknown key 'score'", errors[0])

    def test_note(self):
        ok, errors = forms.validate_adversary(adv(note='x' * 301))
        self.assertFalse(ok)
        self.assertIn('301 characters', ' '.join(errors))
        self.assertFalse(forms.validate_adversary(dict(adv(), note=5))[0])

    def test_not_an_object(self):
        for bad in (None, [], 'refuted'):
            self.assertFalse(forms.validate_adversary(bad)[0])


class ParseJsonTests(unittest.TestCase):
    def test_plain_json(self):
        self.assertEqual(forms.parse_json('{"a": 1}'), {'a': 1})
        self.assertEqual(forms.parse_json(' \n[1, 2, {"b": null}] \n'), [1, 2, {'b': None}])
        self.assertEqual(forms.parse_json('[]'), [])
        self.assertEqual(forms.parse_json('{}'), {})

    def test_code_fences(self):
        self.assertEqual(forms.parse_json('```json\n{"a": [1, 2]}\n```'), {'a': [1, 2]})
        self.assertEqual(forms.parse_json('```\n[1]\n```'), [1])
        self.assertEqual(forms.parse_json('```JSON {"a": 1} ```'), {'a': 1})

    def test_prose_around_the_value(self):
        self.assertEqual(forms.parse_json('Sure, here you go:\n```json\n{"a": 1}\n```\nHope that helps!'), {'a': 1})
        self.assertEqual(forms.parse_json('Answer: {"a": {"b": [1, 2]}} (end)'), {'a': {'b': [1, 2]}})
        self.assertEqual(forms.parse_json('Tags are [\"x\"] only'), ['x'])

    def test_the_outermost_longest_value_wins(self):
        self.assertEqual(forms.parse_json('Note [1]. Result: {"hypotheses": [{"id": "abc"}]} Bye [2]'),
                         {'hypotheses': [{'id': 'abc'}]})
        self.assertEqual(forms.parse_json('{"a": 1} {"b": 2, "c": 3}'), {'b': 2, 'c': 3})
        self.assertEqual(forms.parse_json('{"a": 1} {"b": 2}'), {'a': 1})        # a tie goes to the first

    def test_braces_in_prose_that_are_not_json(self):
        self.assertEqual(forms.parse_json('Use {curly} braces and [brackets]: {"a": 1}'), {'a': 1})
        self.assertEqual(forms.parse_json('{"a": "has } and ] inside"}'), {'a': 'has } and ] inside'})

    def test_failure_is_none(self):
        for bad in ('', '   ', 'no json here', '{"a": ', '{not json}', '[1, 2', 'null', '5', '"text"', 'true', None, 5, b'{}', [],
                    {'a': 1}):
            self.assertIsNone(forms.parse_json(bad), repr(bad))

    def test_never_raises_on_hostile_input(self):
        self.assertIsNone(forms.parse_json('[' * 200000))
        self.assertIsNone(forms.parse_json('{' * 50000 + '"a"'))
        self.assertIsNone(forms.parse_json('\x00\x01{'))
        self.assertEqual(forms.parse_json('{"k": "é中"}'), {'k': 'é中'})

    def test_validators_take_the_parsed_reply(self):
        reply = 'Here:\n```json\n{"hypotheses": [{"id": "late-cheap-skip", "loss_class": "WRONG_SIDE", "lever": "skip", ' \
                '"feature": "frac_elapsed_at_entry", "op": "gt", "thresholds": [0.5], "mechanism": "Late means little time."}]}\n```'
        parsed = forms.parse_json(reply)
        self.assertEqual(forms.validate_hypothesis(parsed['hypotheses'][0]), (True, [], []))


if __name__ == '__main__':
    unittest.main()
