"""Prompt builders, the winner control, the canary and the usage log, on synthetic data.
Run: PYTHONPATH=python python3 -m unittest discover -s python/lossreview/tests
"""
import copy
import datetime
import hashlib
import json
import os
import subprocess
import sys
import unittest
from unittest import mock

from lossreview import forms, prompts, schema, triage


def hyp(**kw):
    h = {'id': 'late-cheap-skip', 'loss_class': 'WRONG_SIDE', 'lever': 'skip', 'feature': 'frac_elapsed_at_entry', 'op': 'gt',
         'thresholds': [0.5, 0.6, 0.7], 'neighbor_features': ['entry_px'],
         'mechanism': 'Late entries leave too little time for a cheap side to recover.', 'cites': ['entry_px']}
    h.update(kw)
    return h


def rows_with(feature, values):
    return [{feature: v} for v in values]


def section(text, start, end=None):
    """The part of a rendered prompt after the line `start` (and before `end`)."""
    i = text.index(start)
    j = text.index(end, i) if end else len(text)
    return text[i:j]


class TemplateTests(unittest.TestCase):
    def test_one_template_and_model_per_step(self):
        self.assertEqual(set(prompts.TEMPLATES), {'tag', 'hypothesize', 'adversary', 'audit'})
        self.assertEqual(set(prompts.MODEL_FOR), set(prompts.TEMPLATES))
        self.assertEqual(prompts.MODEL_FOR, {'tag': 'claude-haiku-5-5', 'hypothesize': 'claude-sonnet-5-5',
                                             'adversary': 'claude-sonnet-5-5', 'audit': 'claude-opus-5-5'})

    def test_every_template_says_propose_only_and_json_only(self):
        for step, text in prompts.TEMPLATES.items():
            self.assertIn('PROPOSE', text, step)
            self.assertIn('code', text.lower(), step)
            self.assertIn('JSON only', text, step)
            self.assertNotIn('<<', text, step)

    def test_hypothesis_template_carries_every_closed_list(self):
        t = prompts.TEMPLATES['hypothesize']
        for word in (*forms.LEVERS, *forms.OPS, *forms.HYPOTHESIS_CLASSES, 'EX_ANTE', 'OUTCOME', 'curve', 'thresholds',
                     'neighbor_features', 'mechanism', 'cites', '240', '12'):
            self.assertIn(word, t, word)
        for col in forms.FEATURE_COLUMNS:
            self.assertIn(col, t, col)
        for col in forms.OUTCOME_COLUMNS:
            self.assertIn(col, t, col)
        for lv in ('dial', 'maker', 'strike', 'exit', 'skip'):
            self.assertIn(forms.LEVER_HELP[lv], t)
        self.assertIn('blind control', t)
        for c in forms.IDENTIFIER_COLUMNS:       # identifiers are not offered as features
            self.assertNotIn(c + ',', t.split('EX_ANTE columns you may use:')[1].split('OUTCOME columns')[0])

    def test_the_template_example_is_a_valid_hypothesis(self):
        reply = forms.parse_json(prompts.TEMPLATES['hypothesize'])
        self.assertIsInstance(reply['hypotheses'], list)
        for h in reply['hypotheses']:
            self.assertEqual(forms.validate_hypothesis(h)[:2], (True, []), h)

    def test_adversary_template_carries_the_vocabulary_and_a_valid_example(self):
        t = prompts.TEMPLATES['adversary']
        for word in (*forms.VERDICTS, *forms.ADVERSARY_REASONS, 'aggregates', '300', 'lift', 'winners'):
            self.assertIn(word, t, word)
        self.assertEqual(forms.validate_adversary(forms.parse_json(t)), (True, []))

    def test_tag_template_carries_every_tag_and_a_valid_example(self):
        t = prompts.TEMPLATES['tag']
        for tag, cols in forms.TAGS.items():
            self.assertIn(tag, t)
            for c in cols:
                self.assertIn(c, t)
        for item in forms.parse_json(t)['trips']:
            self.assertTrue(forms.validate_tags(item['tags'])[0])

    def test_templates_do_not_show_the_outcome_block_to_the_tagger(self):
        self.assertIn('EX_ANTE block', prompts.TEMPLATES['tag'])
        self.assertNotIn('OUTCOME', prompts.TEMPLATES['tag'])

    def test_prompt_hash_is_the_sha256_of_the_template(self):
        for step, text in prompts.TEMPLATES.items():
            h = prompts.prompt_hash(step)
            self.assertEqual(h, hashlib.sha256(text.encode('utf-8')).hexdigest())
            self.assertRegex(h, r'^[0-9a-f]{64}$')
        self.assertEqual(len({prompts.prompt_hash(s) for s in prompts.TEMPLATES}), len(prompts.TEMPLATES))

    def test_prompt_hash_is_stable_across_processes(self):
        env = dict(os.environ, PYTHONHASHSEED='12345', PYTHONPATH=os.pathsep.join(p for p in sys.path if p))
        out = subprocess.run([sys.executable, '-c', 'from lossreview import prompts; print(prompts.prompt_hash("hypothesize"))'],
                             env=env, capture_output=True, text=True, check=True).stdout.strip()
        self.assertEqual(out, prompts.prompt_hash('hypothesize'))

    def test_prompt_hash_unknown_step(self):
        with self.assertRaises(ValueError):
            prompts.prompt_hash('summarise')


class TripViewTests(unittest.TestCase):
    def setUp(self):
        self.row = prompts.canary_trip()

    def test_blocks_split_by_availability(self):
        v = prompts.trip_view(self.row)
        self.assertEqual(set(v), {'ex_ante', 'outcome'})
        self.assertEqual(v['ex_ante']['entry_px'], 0.31)
        self.assertEqual(v['ex_ante']['coin'], 'ETH')
        self.assertEqual(v['outcome']['pnl'], -6.8)
        self.assertTrue(all(schema.ex_ante(c) for c in v['ex_ante']))
        self.assertFalse(any(schema.ex_ante(c) for c in v['outcome']))

    def test_no_outcome_column_in_the_ex_ante_block(self):
        row = {c: 1.0 for c in schema.COLUMNS}
        v = prompts.trip_view(row)
        self.assertFalse(set(v['ex_ante']) & set(forms.OUTCOME_COLUMNS))
        # legs is shown only as a summary, and only when it is a list
        self.assertEqual(set(v['ex_ante']) | set(v['outcome']), set(schema.COLUMNS) - prompts.PRIVATE_KEYS - {'legs'})

    def test_identifiers_and_times_are_never_shown(self):
        v = prompts.trip_view(self.row)
        shown = json.dumps(v)
        self.assertNotIn('CANARY-0', shown)
        for k in prompts.PRIVATE_KEYS:
            self.assertNotIn(k, v['ex_ante'])
            self.assertNotIn(k, v['outcome'])
        self.assertIn('ticker', prompts.PRIVATE_KEYS)
        self.assertIn('entry_utc', prompts.PRIVATE_KEYS)
        self.assertIn('closed_utc', prompts.PRIVATE_KEYS)

    def test_none_and_empty_values_are_dropped(self):
        v = prompts.trip_view({'coin': 'BTC', 'kind': None, 'side': '', 'pnl': None, 'exit_event': '  ', 'count': 0, 'won': False})
        self.assertEqual(v, {'ex_ante': {'coin': 'BTC', 'count': 0}, 'outcome': {'won': False}})

    def test_floats_are_rounded_to_four_places(self):
        v = prompts.trip_view({'entry_px': 0.123456789, 'pnl': -1.23456789, 'count': 12, 'spot_pre_entry': float('nan'),
                               'stake': float('inf')})
        self.assertEqual(v['ex_ante'], {'entry_px': 0.1235, 'count': 12})
        self.assertEqual(v['outcome'], {'pnl': -1.2346})

    def test_legs_are_summarised_in_the_outcome_block_only(self):
        v = prompts.trip_view(self.row)
        self.assertNotIn('legs', v['ex_ante'])
        self.assertEqual(v['outcome']['legs'], [{'rule': 'loser_cut', 'px': 0.12, 'count': 32.0, 'below_breakeven': True}])

    def test_many_legs_and_odd_legs(self):
        legs = [{'rule': 'ratchet', 'px': 0.5555555, 'count': 10, 'below_breakeven': False, 'fee': 0.1, 't': 5.0, 'taker': True},
                {'rule': 'end_rule', 'px': 0.2, 'count': 22.0, 'below_breakeven': True}, 'junk', None]
        v = prompts.trip_view({'legs': legs, 'coin': 'BTC'})
        self.assertEqual(v['outcome']['legs'], [{'rule': 'ratchet', 'px': 0.5556, 'count': 10, 'below_breakeven': False},
                                                {'rule': 'end_rule', 'px': 0.2, 'count': 22.0, 'below_breakeven': True}])
        self.assertEqual(prompts.trip_view({'legs': []})['outcome'], {'legs': []})      # held to the end: no legs, and that is shown
        self.assertEqual(prompts.trip_view({'legs': None})['outcome'], {})
        self.assertEqual(prompts.trip_view({'legs': ''})['outcome'], {})
        self.assertEqual(prompts.trip_view({'legs': 5})['outcome'], {})

    def test_legs_from_a_csv_cell_as_json_text(self):
        cell = json.dumps([{'rule': 'loser_cut', 'px': 0.1, 'count': 3, 'below_breakeven': True}])
        self.assertEqual(prompts.trip_view({'legs': cell})['outcome']['legs'],
                         [{'rule': 'loser_cut', 'px': 0.1, 'count': 3, 'below_breakeven': True}])

    def test_csv_style_rows(self):
        v = prompts.trip_view({'ticker': 'KXBTC15M-26NOV121015-15', 'kind': '15m', 'entry_px': '0.50', 'pnl': '-2.00', 'best_bid_held': ''})
        self.assertEqual(v, {'ex_ante': {'kind': '15m', 'entry_px': '0.50'}, 'outcome': {'pnl': '-2.00'}})

    def test_the_row_is_not_modified(self):
        before = copy.deepcopy(self.row)
        prompts.trip_view(self.row)
        self.assertEqual(self.row, before)

    def test_unknown_columns_go_to_the_outcome_block(self):
        v = prompts.trip_view({'mystery': 3})
        self.assertEqual(v, {'ex_ante': {}, 'outcome': {'mystery': 3}})

    def test_the_view_is_json_serialisable(self):
        json.dumps(prompts.trip_view(dict(self.row, odd=datetime.date(2026, 11, 12))))


class TagPromptTests(unittest.TestCase):
    def rows(self, n):
        return [dict(prompts.canary_trip(), ticker='KXETHD-26NOV1210-T%d' % i, entry_px=0.2 + i / 100) for i in range(n)]

    def test_starts_with_the_template_and_shows_each_row_by_index(self):
        p = prompts.build_tag_prompt(self.rows(3))
        self.assertTrue(p.startswith(prompts.TEMPLATES['tag']))
        lines = [json.loads(line) for line in section(p, 'TRIPS').splitlines()[1:] if line.strip()]
        self.assertEqual([l['i'] for l in lines], [0, 1, 2])
        self.assertEqual([l['ex_ante']['entry_px'] for l in lines], [0.2, 0.21, 0.22])

    def test_no_ticker_no_time_and_no_outcome_block(self):
        p = prompts.build_tag_prompt(self.rows(2))
        shown = section(p, 'TRIPS')
        for bad in ('KXETHD', 'CANARY', 'ticker', 'entry_utc', 'closed_utc', '"outcome"', 'best_bid_held', 'pnl', 'legs'):
            self.assertNotIn(bad, shown, bad)

    def test_row_limits(self):
        self.assertIsInstance(prompts.build_tag_prompt(self.rows(25)), str)
        with self.assertRaises(ValueError):
            prompts.build_tag_prompt(self.rows(26))
        with self.assertRaises(ValueError):
            prompts.build_tag_prompt([])

    def test_accepts_any_iterable(self):
        self.assertIn('"i":1', prompts.build_tag_prompt(iter(self.rows(2))))

    def test_a_ticker_in_a_free_text_field_is_refused(self):
        row = dict(prompts.canary_trip(), era='KXBTC15M-26NOV121015-15')
        with self.assertRaises(ValueError):
            prompts.build_tag_prompt([row])


class HypothesisPromptTests(unittest.TestCase):
    def rows(self, n):
        return [dict(prompts.canary_trip(), ticker='KXETHD-26NOV1210-T%d' % i) for i in range(n)]

    def build(self, **kw):
        args = dict(loss_class='WRONG_SIDE', rows=self.rows(2), aggregates={'n_losers': 40, 'by_coin': {'BTC': 25, 'ETH': 15}},
                    registered=['late-skip: skip when late'])
        args.update(kw)
        return prompts.build_hypothesis_prompt(args['loss_class'], args['rows'], args['aggregates'], args['registered'])

    def test_contents(self):
        p = self.build()
        self.assertTrue(p.startswith(prompts.TEMPLATES['hypothesize'].rstrip()))
        self.assertIn('LOSS CLASS: WRONG_SIDE', p)
        self.assertIn(prompts.CLASS_HELP['WRONG_SIDE'], p)
        self.assertIn('"n_losers":40', p)
        self.assertIn('- late-skip: skip when late', p)
        self.assertEqual(p.count('\nTRIP '), 2)

    def test_each_trip_has_separate_ex_ante_and_outcome_blocks(self):
        p = self.build(rows=self.rows(1))
        trip = section(p, 'TRIP 0')
        ex = json.loads(section(trip, 'EX_ANTE: ', '\nOUTCOME').split('EX_ANTE: ', 1)[1])
        out = json.loads(trip.split('OUTCOME: ', 1)[1])
        self.assertIn('entry_px', ex)
        self.assertNotIn('pnl', ex)
        self.assertIn('pnl', out)
        self.assertNotIn('entry_px', out)
        self.assertIsInstance(out['legs'], list)

    def test_no_ticker_or_time_is_rendered(self):
        p = self.build()
        for bad in ('KXETHD', 'CANARY-0', '11-12 15:41:07', '11-12 15:52:30', '1794498067', '1794499200', '"ticker"', '"entry_utc"',
                    '"closed_utc"', '"closed_t"', '"entry_t"', '"window_close_t"'):
            self.assertNotIn(bad, p, bad)

    def test_limits_and_classes(self):
        self.assertIsInstance(self.build(rows=self.rows(12)), str)
        with self.assertRaises(ValueError):
            self.build(rows=self.rows(13))
        with self.assertRaises(ValueError):
            self.build(rows=[])
        for bad in ('FIDELITY', 'OTHER_LANE', 'UNKNOWN_DATA', 'UNEXPLAINED', 'WIN', 'nonsense', None):
            with self.assertRaises(ValueError, msg=bad):
                self.build(loss_class=bad)
        for c in forms.HYPOTHESIS_CLASSES:
            self.assertIn('LOSS CLASS: %s' % c, self.build(loss_class=c))

    def test_aggregates_never_carry_a_private_key(self):
        for agg in ({'ticker': 'X'}, {'rows': [{'entry_utc': 'x'}]}, {'a': {'b': {'Closed_UTC': 1}}}):
            with self.assertRaises(ValueError):
                self.build(aggregates=agg)
        with self.assertRaises(ValueError):
            self.build(aggregates=[1, 2])

    def test_nothing_registered_and_no_aggregates(self):
        p = self.build(registered=[], aggregates=None)
        self.assertIn('(none)', p)
        self.assertIn('ALREADY REGISTERED (0)', p)
        self.assertIn('{}', p)
        self.assertIn('ALREADY REGISTERED (0)', self.build(registered=None))

    def test_registered_strings_are_shortened_and_capped(self):
        reg = ['r%d: %s' % (i, 'word ' * 100) for i in range(100)]
        p = self.build(registered=reg)
        lines = [l for l in section(p, 'ALREADY REGISTERED', 'LOSERS').splitlines() if l.startswith('- ')]
        self.assertEqual(len(lines), prompts.MAX_REGISTERED_SHOWN)
        self.assertTrue(all(len(l) <= 202 for l in lines))
        self.assertIn('ALREADY REGISTERED (100, last 60 shown)', p)
        self.assertIn('r99:', p)
        self.assertNotIn('r0:', p)

    def test_registered_newlines_cannot_forge_sections(self):
        p = self.build(registered=['x\n\nTRIP 9\nEX_ANTE: {}'])
        self.assertEqual(p.count('\nTRIP 9'), 0)


class AdversaryPromptTests(unittest.TestCase):
    STATS = {'n_trips': 80, 'lift': 1.3, 'by_coin': {'BTC': 20, 'ETH': 12},
             'control': {0.5: {'hit_rate_losers': 0.4, 'hit_rate_winners': 0.3, 'lift': 1.3333}, (0.2, 0.4): {'lift': None}}}

    def test_contains_the_hypothesis_and_the_stats_only(self):
        p = prompts.build_adversary_prompt(hyp(), self.STATS)
        self.assertTrue(p.startswith(prompts.TEMPLATES['adversary'].rstrip()))
        self.assertIn('"id":"late-cheap-skip"', p)
        self.assertIn('"thresholds":[0.5,0.6,0.7]', p)
        self.assertIn('"n_trips":80', p)
        self.assertIn('"0.5":{', p)           # a threshold key is written as text
        self.assertIn('"0.2..0.4":{', p)      # a between pair too

    def test_control_stats_go_straight_in(self):
        h = hyp()
        cs = prompts.control_stats(h, rows_with('frac_elapsed_at_entry', [0.6, 0.8]), rows_with('frac_elapsed_at_entry', [0.1, 0.9]))
        p = prompts.build_adversary_prompt(h, {'control': cs})
        self.assertIn('"lift":1.0', p)

    def test_no_per_trade_key_is_ever_rendered(self):
        p = prompts.build_adversary_prompt(hyp(), self.STATS)
        for bad in ('ticker', 'entry_utc', 'closed_utc', 'CANARY'):
            self.assertNotIn('"%s"' % bad, p)
        self.assertNotIn('KX', p)

    def test_private_keys_in_stats_are_refused_at_any_depth(self):
        for stats in ({'ticker': 'A'}, {'a': [{'b': {'entry_utc': 1}}]}, {'Closed_Utc': 1}, {'x': ({'ticker': 1},)}):
            with self.assertRaises(ValueError):
                prompts.build_adversary_prompt(hyp(), stats)

    def test_a_ticker_value_is_refused(self):
        with self.assertRaises(ValueError):
            prompts.build_adversary_prompt(hyp(), {'worst_market': 'KXBTC15M-26NOV121015-15'})
        with self.assertRaises(ValueError):
            prompts.build_adversary_prompt(hyp(mechanism='Like KXETHD-26NOV1210 did.'), {})

    def test_only_the_form_fields_of_the_hypothesis_are_rendered(self):
        p = prompts.build_adversary_prompt(dict(hyp(), status='candidate', ticker='CANARY-0', entry_utc='x'), self.STATS)
        self.assertNotIn('candidate', p)
        self.assertNotIn('CANARY-0', p)
        self.assertNotIn('entry_utc', p)

    def test_input_types(self):
        for hh, ss in ((None, {}), (hyp(), None), ([], {}), (hyp(), [])):
            with self.assertRaises(ValueError):
                prompts.build_adversary_prompt(hh, ss)

    def test_nan_in_stats_is_written_as_null(self):
        p = prompts.build_adversary_prompt(hyp(), {'lift': float('nan'), 'p': float('inf')})
        self.assertIn('"lift":null', p)
        self.assertNotIn('NaN', p)
        self.assertNotIn('Infinity', p)


class AuditPromptTests(unittest.TestCase):
    def test_builds_from_aggregates(self):
        p = prompts.build_audit_prompt({'hypotheses': 7, 'tokens': {'tag': 1200}}, ['a: one', 'b: two'])
        self.assertTrue(p.startswith(prompts.TEMPLATES['audit'].rstrip()))
        self.assertIn('"hypotheses":7', p)
        self.assertIn('- b: two', p)

    def test_private_keys_are_refused(self):
        with self.assertRaises(ValueError):
            prompts.build_audit_prompt({'rows': [{'ticker': 'x'}]}, [])
        with self.assertRaises(ValueError):
            prompts.build_audit_prompt([], [])


class MatchesTests(unittest.TestCase):
    def test_lt_and_gt_are_strict(self):
        h = hyp(op='lt')
        self.assertTrue(prompts.matches(h, {'frac_elapsed_at_entry': 0.4}, 0.5))
        self.assertFalse(prompts.matches(h, {'frac_elapsed_at_entry': 0.5}, 0.5))
        self.assertFalse(prompts.matches(h, {'frac_elapsed_at_entry': 0.6}, 0.5))
        h = hyp(op='gt')
        self.assertTrue(prompts.matches(h, {'frac_elapsed_at_entry': 0.6}, 0.5))
        self.assertFalse(prompts.matches(h, {'frac_elapsed_at_entry': 0.5}, 0.5))
        self.assertFalse(prompts.matches(h, {'frac_elapsed_at_entry': 0.4}, 0.5))

    def test_between_is_inclusive(self):
        h = hyp(op='between', thresholds=[0.2, 0.4])
        for v, want in ((0.1, False), (0.2, True), (0.3, True), (0.4, True), (0.41, False)):
            self.assertIs(prompts.matches(h, {'frac_elapsed_at_entry': v}, [0.2, 0.4]), want, v)
        self.assertTrue(prompts.matches(h, {'frac_elapsed_at_entry': 0.3}, (0.2, 0.4)))

    def test_eq_on_text_ignores_case_and_space(self):
        h = hyp(feature='coin', op='eq', thresholds=['BTC'])
        self.assertTrue(prompts.matches(h, {'coin': 'btc'}, 'BTC'))
        self.assertTrue(prompts.matches(h, {'coin': ' BTC '}, ' btc'))
        self.assertFalse(prompts.matches(h, {'coin': 'ETH'}, 'BTC'))

    def test_eq_on_booleans(self):
        h = hyp(feature='lane', op='eq', thresholds=[True])
        for v in (True, 'True', 'true', 1, '1', 'yes'):
            self.assertTrue(prompts.matches(h, {'lane': v}, True), v)
        for v in (False, 'False', 0, '0', 'no'):
            self.assertFalse(prompts.matches(h, {'lane': v}, True), v)
            self.assertTrue(prompts.matches(h, {'lane': v}, False), v)
        self.assertIsNone(prompts.matches(h, {'lane': 'maybe'}, True))
        self.assertIsNone(prompts.matches(h, {'lane': 7}, True))

    def test_eq_with_a_string_against_a_boolean_or_number_cell(self):
        h = hyp(feature='lane', op='eq')
        self.assertTrue(prompts.matches(h, {'lane': True}, 'true'))
        self.assertTrue(prompts.matches(h, {'lane': 15.0}, '15'))
        self.assertTrue(prompts.matches(h, {'lane': 15}, '15'))
        self.assertFalse(prompts.matches(h, {'lane': 15.5}, '15'))

    def test_numbers_from_csv_strings(self):
        h = hyp(op='gt')
        self.assertTrue(prompts.matches(h, {'frac_elapsed_at_entry': '0.6'}, 0.5))
        self.assertTrue(prompts.matches(h, {'frac_elapsed_at_entry': ' 0.6 '}, '0.5'))
        self.assertTrue(prompts.matches(h, {'frac_elapsed_at_entry': 1}, 0))

    def test_missing_or_unusable_values_are_none(self):
        h = hyp(op='gt')
        for v in (None, '', '  ', 'abc', 'True', float('nan'), float('inf'), True, [0.9], {'a': 1}):
            self.assertIsNone(prompts.matches(h, {'frac_elapsed_at_entry': v}, 0.5), repr(v))
        self.assertIsNone(prompts.matches(h, {}, 0.5))
        self.assertIsNone(prompts.matches(h, {'other': 1}, 0.5))
        self.assertIsNone(prompts.matches(hyp(feature='coin', op='eq'), {'coin': ''}, 'BTC'))
        self.assertIsNone(prompts.matches(hyp(feature='coin', op='eq'), {}, 'BTC'))

    def test_malformed_thresholds_are_none(self):
        h = hyp(op='gt')
        row = {'frac_elapsed_at_entry': 0.6}
        for t in (None, 'abc', True, [0.5], {'a': 1}, float('nan')):
            self.assertIsNone(prompts.matches(h, row, t), repr(t))
        hb = hyp(op='between')
        for t in (None, 0.5, [0.2], [0.2, 0.4, 0.6], ['a', 0.4], [None, 0.4], 'ab'):
            self.assertIsNone(prompts.matches(hb, row, t), repr(t))
        he = hyp(feature='coin', op='eq')
        for t in (None, 5, 1.5, ['BTC']):
            self.assertIsNone(prompts.matches(he, {'coin': 'BTC'}, t), repr(t))

    def test_unknown_op_or_broken_hypothesis_never_raises(self):
        row = {'frac_elapsed_at_entry': 0.6}
        self.assertIsNone(prompts.matches(hyp(op='ge'), row, 0.5))
        self.assertIsNone(prompts.matches(hyp(op=['gt']), row, 0.5))
        self.assertIsNone(prompts.matches({}, row, 0.5))
        self.assertIsNone(prompts.matches(None, row, 0.5))
        self.assertIsNone(prompts.matches(hyp(feature=['x']), row, 0.5))
        self.assertIsNone(prompts.matches(hyp(), None, 0.5))
        self.assertIsNone(prompts.matches(hyp(), 'row', 0.5))

    def test_no_eval(self):
        h = hyp(op='gt')
        self.assertIsNone(prompts.matches(h, {'frac_elapsed_at_entry': '__import__("os").getcwd()'}, 0.5))
        self.assertIsNone(prompts.matches(h, {'frac_elapsed_at_entry': 1}, '__import__("os").getcwd()'))
        self.assertIsNone(prompts.matches(h, {'frac_elapsed_at_entry': '1+1'}, 0))


class ControlStatsTests(unittest.TestCase):
    F = 'frac_elapsed_at_entry'

    def test_rates_and_lift_per_threshold(self):
        losers = rows_with(self.F, [0.9, 0.8, 0.7, 0.6, 0.55, 0.3, 0.2, 0.1])
        winners = rows_with(self.F, [0.9, 0.4, 0.3, 0.2])
        s = prompts.control_stats(hyp(thresholds=[0.5, 0.75]), losers, winners)
        self.assertEqual(set(s), {0.5, 0.75})
        a = s[0.5]
        self.assertEqual((a['n_losers'], a['n_winners'], a['n_losers_hit'], a['n_winners_hit']), (8, 4, 5, 1))
        self.assertEqual(a['hit_rate_losers'], 0.625)
        self.assertEqual(a['hit_rate_winners'], 0.25)
        self.assertEqual(a['lift'], 2.5)
        b = s[0.75]
        self.assertEqual((b['n_losers_hit'], b['n_winners_hit']), (2, 1))
        self.assertEqual(b['hit_rate_losers'], 0.25)
        self.assertEqual(b['lift'], 1.0)

    def test_every_documented_key_is_present(self):
        s = prompts.control_stats(hyp(thresholds=[0.5]), rows_with(self.F, [0.9]), rows_with(self.F, [0.1]))
        for k in ('n_losers_hit', 'n_winners_hit', 'hit_rate_losers', 'hit_rate_winners', 'lift'):
            self.assertIn(k, s[0.5])

    def test_a_rule_that_hits_winners_as_often_explains_nothing(self):
        both = rows_with(self.F, [0.9, 0.1, 0.9, 0.1])
        self.assertEqual(prompts.control_stats(hyp(thresholds=[0.5]), both, both)[0.5]['lift'], 1.0)

    def test_lift_is_undefined_without_a_winner_rate(self):
        s = prompts.control_stats(hyp(thresholds=[0.5]), rows_with(self.F, [0.9, 0.8]), rows_with(self.F, [0.1, 0.2]))
        self.assertEqual(s[0.5]['n_winners_hit'], 0)
        self.assertEqual(s[0.5]['hit_rate_winners'], 0.0)
        self.assertIsNone(s[0.5]['lift'])

    def test_rows_without_the_feature_are_left_out(self):
        losers = [{self.F: 0.9}, {}, {self.F: ''}, {self.F: None}, {self.F: 'junk'}]
        winners = [{self.F: 0.1}, {'other': 1}]
        a = prompts.control_stats(hyp(thresholds=[0.5]), losers, winners)[0.5]
        self.assertEqual((a['n_losers'], a['n_winners']), (1, 1))
        self.assertEqual(a['hit_rate_losers'], 1.0)

    def test_empty_samples_have_no_rates(self):
        a = prompts.control_stats(hyp(thresholds=[0.5]), [], [])[0.5]
        self.assertEqual((a['n_losers'], a['n_winners'], a['n_losers_hit'], a['n_winners_hit']), (0, 0, 0, 0))
        self.assertIsNone(a['hit_rate_losers'])
        self.assertIsNone(a['hit_rate_winners'])
        self.assertIsNone(a['lift'])
        b = prompts.control_stats(hyp(thresholds=[0.5]), rows_with(self.F, [0.9]), [])[0.5]
        self.assertEqual(b['hit_rate_losers'], 1.0)
        self.assertIsNone(b['lift'])

    def test_between_has_one_key_the_pair(self):
        s = prompts.control_stats(hyp(op='between', thresholds=[0.2, 0.4]), rows_with(self.F, [0.1, 0.2, 0.3, 0.5]),
                                  rows_with(self.F, [0.3, 0.9]))
        self.assertEqual(list(s), [(0.2, 0.4)])
        self.assertEqual((s[(0.2, 0.4)]['n_losers_hit'], s[(0.2, 0.4)]['n_winners_hit']), (2, 1))
        self.assertEqual(s[(0.2, 0.4)]['lift'], 1.0)

    def test_eq_thresholds(self):
        h = hyp(feature='coin', op='eq', thresholds=['BTC', 'ETH'])
        s = prompts.control_stats(h, rows_with('coin', ['BTC', 'BTC', 'ETH', 'SOL']), rows_with('coin', ['ETH', 'SOL']))
        self.assertEqual(s['BTC']['n_losers_hit'], 2)
        self.assertEqual(s['ETH']['n_winners_hit'], 1)
        self.assertIsNone(s['BTC']['lift'])
        self.assertEqual(s['ETH']['lift'], 0.5)

    def test_malformed_hypothesis_gives_an_empty_result(self):
        for bad in (None, {}, {'op': 'gt'}, {'thresholds': [1]}, {'op': 'gt', 'thresholds': 5}):
            self.assertEqual(prompts.control_stats(bad, [{}], [{}]), {}, bad)
        self.assertEqual(prompts.control_stats(hyp(thresholds=[[1], 0.5]), [{self.F: 0.9}], [])[0.5]['n_losers_hit'], 1)

    def test_the_result_serialises_for_the_adversary_prompt(self):
        s = prompts.control_stats(hyp(op='between', thresholds=[0.2, 0.4]), rows_with(self.F, [0.3]), rows_with(self.F, [0.3]))
        self.assertIn('"0.2..0.4"', prompts.build_adversary_prompt(hyp(), {'control': s}))


class CanaryTests(unittest.TestCase):
    def test_the_canary_trip(self):
        t = prompts.canary_trip()
        self.assertEqual(t['ticker'], 'CANARY-0')
        self.assertTrue(set(t) <= set(schema.COLUMNS))
        # every ex-ante column is present (a new one added to the schema must be added to the canary too)
        self.assertEqual(set(forms.FEATURE_COLUMNS) - set(t), set())
        self.assertLess(t['pnl'], 0)
        self.assertIn(triage.classify(t)['primary'], forms.HYPOTHESIS_CLASSES)
        self.assertEqual(prompts.canary_trip(), t)
        self.assertIsNot(prompts.canary_trip(), t)

    def test_the_canary_trip_is_internally_consistent(self):
        t = prompts.canary_trip()
        self.assertAlmostEqual(t['entry_px'], 1 - t['plan_price'], places=6)       # a NO buy
        d = t['stake'] - t['count'] * t['entry_px']
        self.assertTrue(-1e-9 <= d < t['entry_px'])
        self.assertAlmostEqual(t['pnl'], t['pnl_fills'])
        self.assertAlmostEqual(t['fees'], t['entry_fee'] + t['exit_fee'])
        self.assertAlmostEqual(t['frac_elapsed_at_entry'], 1 - t['left_at_entry_s'] / 3600, places=3)

    def test_mutating_one_canary_trip_does_not_touch_the_next(self):
        t = prompts.canary_trip()
        t['legs'].append('x')
        t['pnl'] = 5
        self.assertEqual(len(prompts.canary_trip()['legs']), 1)
        self.assertEqual(prompts.canary_trip()['pnl'], -6.8)

    def test_canary_hypotheses_cover_the_required_cases(self):
        cases = {h['id']: (h, ok) for h, ok in prompts.canary_hypotheses()}
        self.assertEqual(len(cases), len(prompts.canary_hypotheses()))     # distinct ids
        self.assertTrue(any(ok for _, ok in cases.values()))
        self.assertTrue(any(not ok for _, ok in cases.values()))
        clean, ok = cases['canary-clean']
        self.assertTrue(ok)
        self.assertIn('best_bid_held', cases['canary-cites-outcome'][0]['cites'])
        self.assertFalse(cases['canary-cites-outcome'][1])
        self.assertEqual(cases['canary-curve-rank'][0]['feature'], 'rank')
        self.assertTrue(cases['canary-curve-rank'][1])
        self.assertEqual(len(cases['canary-13-thresholds'][0]['thresholds']), 13)
        self.assertFalse(cases['canary-13-thresholds'][1])
        self.assertNotIn(cases['canary-unknown-column'][0]['feature'], schema.COLUMNS)
        self.assertFalse(cases['canary-unknown-column'][1])

    def test_canary_expectations_match_the_validator(self):
        for h, should_pass in prompts.canary_hypotheses():
            ok, errors, flags = forms.validate_hypothesis(h)
            self.assertEqual(ok, should_pass, '%s %s' % (h['id'], errors))
        ok, errors, flags = forms.validate_hypothesis(dict(next(h for h, _ in prompts.canary_hypotheses() if h['id'] == 'canary-curve-rank')))
        self.assertEqual((ok, flags), (True, ['curve_edit']))

    def test_canary_hypotheses_are_fresh_copies(self):
        a = prompts.canary_hypotheses()
        a[0][0]['thresholds'].append(9)
        a[0][0]['cites'].append('pnl')
        b = prompts.canary_hypotheses()
        self.assertEqual(b[0][0]['thresholds'], [0.5, 0.6, 0.7])
        self.assertNotIn('pnl', b[0][0]['cites'])

    def test_run_canary_passes_on_the_real_validators(self):
        self.assertEqual(prompts.run_canary(), (True, []))

    def test_run_canary_notices_a_validator_that_lets_everything_through(self):
        with mock.patch.object(forms, 'validate_hypothesis', lambda h: (True, [], [])):
            ok, failures = prompts.run_canary()
        self.assertFalse(ok)
        self.assertTrue(any('canary-cites-outcome' in f for f in failures))
        self.assertTrue(any('canary-13-thresholds' in f for f in failures))
        self.assertTrue(any('canary-curve-rank' in f for f in failures))

    def test_run_canary_notices_a_validator_that_refuses_everything(self):
        with mock.patch.object(forms, 'validate_hypothesis', lambda h: (False, ['no'], [])):
            ok, failures = prompts.run_canary()
        self.assertFalse(ok)
        self.assertTrue(any('canary-clean' in f for f in failures))

    def test_run_canary_notices_a_lost_curve_flag(self):
        real = forms.validate_hypothesis
        with mock.patch.object(forms, 'validate_hypothesis', lambda h: (lambda r: (r[0], r[1], []))(real(h))):
            ok, failures = prompts.run_canary()
        self.assertFalse(ok)
        self.assertTrue(any('flags' in f for f in failures))

    def test_run_canary_notices_a_wrong_reason(self):
        real = forms.validate_hypothesis
        with mock.patch.object(forms, 'validate_hypothesis', lambda h: (lambda r: (r[0], ['something else'] if r[1] else [], r[2]))(real(h))):
            ok, failures = prompts.run_canary()
        self.assertFalse(ok)
        self.assertTrue(any('another reason' in f for f in failures))

    def test_run_canary_notices_a_trip_view_that_leaks(self):
        real = prompts.trip_view
        with mock.patch.object(prompts, 'trip_view', lambda row: dict(real(row), ex_ante=dict(real(row)['ex_ante'], pnl=-6.8))):
            ok, failures = prompts.run_canary()
        self.assertFalse(ok)
        self.assertTrue(any('trip_view' in f for f in failures))


class UsageRecordTests(unittest.TestCase):
    def rec(self, **kw):
        a = dict(step='tag', model='claude-haiku-5-5', prompt_hash_='abc', tokens_in=1000, tokens_out=200, items=25, day='2026-11-13')
        a.update(kw)
        return prompts.usage_record(a['step'], a['model'], a['prompt_hash_'], a['tokens_in'], a['tokens_out'], a['items'], a['day'])

    def test_fields(self):
        self.assertEqual(self.rec(), {'day': '2026-11-13', 'step': 'tag', 'model': 'claude-haiku-5-5', 'prompt_hash': 'abc',
                                      'tokens_in': 1000, 'tokens_out': 200, 'items': 25})

    def test_a_real_prompt_hash_and_model(self):
        r = self.rec(step='audit', model=prompts.MODEL_FOR['audit'], prompt_hash_=prompts.prompt_hash('audit'))
        self.assertEqual(r['prompt_hash'], prompts.prompt_hash('audit'))
        self.assertEqual(r['model'], 'claude-opus-5-5')

    def test_day_as_a_date_or_datetime(self):
        self.assertEqual(self.rec(day=datetime.date(2026, 11, 13))['day'], '2026-11-13')
        self.assertEqual(self.rec(day=datetime.datetime(2026, 11, 13, 23, 59))['day'], '2026-11-13')

    def test_the_record_is_json_serialisable(self):
        self.assertEqual(json.loads(json.dumps(self.rec())), self.rec())

    def test_bad_inputs(self):
        with self.assertRaises(ValueError):
            self.rec(step='summarise')
        with self.assertRaises(ValueError):
            self.rec(day='13/11/2026')
        for field in ('tokens_in', 'tokens_out', 'items'):
            for bad in (-1, 1.5, '10', None, True):
                with self.assertRaises(ValueError, msg='%s=%r' % (field, bad)):
                    self.rec(**{field: bad})
        self.assertEqual(self.rec(tokens_in=0, tokens_out=0, items=0)['items'], 0)


class BudgetTests(unittest.TestCase):
    DAY = '2026-11-13'

    def rec(self, day, tin=100, tout=50, step='tag'):
        return prompts.usage_record(step, prompts.MODEL_FOR[step], prompts.prompt_hash(step), tin, tout, 1, day)

    def test_sums_input_and_output_tokens_for_the_day(self):
        recs = [self.rec(self.DAY, 100, 50), self.rec(self.DAY, 200, 25, 'hypothesize'), self.rec('2026-11-12', 999, 999)]
        b = prompts.budget_check(recs, self.DAY, 1000)
        self.assertEqual(b['used_today'], 375)
        self.assertEqual(b['remaining_today'], 625)
        self.assertTrue(b['ok'])
        self.assertTrue(b['reason'])

    def test_four_keys_at_least(self):
        b = prompts.budget_check([], self.DAY, 10)
        for k in ('used_today', 'remaining_today', 'ok', 'reason'):
            self.assertIn(k, b)
        self.assertEqual((b['used_today'], b['remaining_today'], b['ok']), (0, 10, True))

    def test_at_and_over_the_daily_allowance(self):
        b = prompts.budget_check([self.rec(self.DAY, 100, 50)], self.DAY, 150)
        self.assertEqual((b['used_today'], b['remaining_today'], b['ok']), (150, 0, False))
        self.assertIn('daily', b['reason'])
        b = prompts.budget_check([self.rec(self.DAY, 1000, 500)], self.DAY, 150)
        self.assertEqual((b['used_today'], b['remaining_today'], b['ok']), (1500, 0, False))
        b = prompts.budget_check([self.rec(self.DAY, 100, 49)], self.DAY, 150)
        self.assertEqual((b['remaining_today'], b['ok']), (1, True))

    def test_a_zero_allowance_is_never_ok(self):
        b = prompts.budget_check([], self.DAY, 0)
        self.assertFalse(b['ok'])

    def test_other_days_do_not_count_without_a_weekly_allowance(self):
        b = prompts.budget_check([self.rec('2026-11-12', 10 ** 6, 0)], self.DAY, 1000)
        self.assertEqual((b['used_today'], b['ok'], b['remaining_week']), (0, True, None))

    def test_the_week_is_the_seven_days_ending_today(self):
        recs = [self.rec('2026-11-07', 100, 0),   # 6 days before: in the week
                self.rec('2026-11-06', 5000, 0),  # 7 days before: out
                self.rec('2026-11-10', 100, 0),
                self.rec(self.DAY, 100, 0),
                self.rec('2026-11-14', 7000, 0)]  # tomorrow: not counted
        b = prompts.budget_check(recs, self.DAY, 1000, 1000)
        self.assertEqual(b['used_today'], 100)
        self.assertEqual(b['used_week'], 300)
        self.assertEqual(b['remaining_week'], 700)
        self.assertEqual(b['remaining_today'], 700)     # the weekly allowance binds before the daily one
        self.assertTrue(b['ok'])

    def test_weekly_allowance_used_up(self):
        recs = [self.rec('2026-11-09', 600, 0), self.rec('2026-11-10', 400, 0)]
        b = prompts.budget_check(recs, self.DAY, 500, 1000)
        self.assertEqual((b['used_today'], b['remaining_today'], b['ok']), (0, 0, False))
        self.assertIn('weekly', b['reason'])

    def test_the_daily_limit_binds_when_it_is_smaller(self):
        b = prompts.budget_check([self.rec(self.DAY, 300, 0)], self.DAY, 400, 10 ** 6)
        self.assertEqual(b['remaining_today'], 100)
        self.assertTrue(b['ok'])

    def test_daily_reason_wins_when_both_are_used_up(self):
        b = prompts.budget_check([self.rec(self.DAY, 100, 0)], self.DAY, 50, 50)
        self.assertFalse(b['ok'])
        self.assertIn('daily', b['reason'])

    def test_a_date_object_for_day_and_in_records(self):
        recs = [{'day': datetime.date(2026, 11, 13), 'tokens_in': 10, 'tokens_out': 5}]
        self.assertEqual(prompts.budget_check(recs, datetime.date(2026, 11, 13), 100)['used_today'], 15)

    def test_unreadable_records_are_skipped(self):
        recs = [{}, {'day': 'x', 'tokens_in': 1, 'tokens_out': 1}, {'day': self.DAY}, {'day': self.DAY, 'tokens_in': 'a', 'tokens_out': 1},
                {'day': None, 'tokens_in': 1, 'tokens_out': 1}, self.rec(self.DAY, 7, 3)]
        self.assertEqual(prompts.budget_check(recs, self.DAY, 100)['used_today'], 10)

    def test_a_generator_of_records(self):
        self.assertEqual(prompts.budget_check((self.rec(self.DAY, 1, 1) for _ in range(3)), self.DAY, 100)['used_today'], 6)

    def test_bad_allowances_and_day(self):
        for bad in (-1, 'x', True):
            with self.assertRaises(ValueError):
                prompts.budget_check([], self.DAY, bad)
            with self.assertRaises(ValueError):
                prompts.budget_check([], self.DAY, 10, bad)
        with self.assertRaises(ValueError):
            prompts.budget_check([], 'yesterday', 10)

    def test_month_and_year_boundaries(self):
        recs = [self.rec('2026-12-30', 10, 0), self.rec('2027-01-02', 10, 0)]
        b = prompts.budget_check(recs, '2027-01-02', 100, 100)
        self.assertEqual((b['used_today'], b['used_week']), (10, 20))


if __name__ == '__main__':
    unittest.main()
