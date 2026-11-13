"""Screening: what a model reply may carry into a public workflow input."""
import io
import json
import unittest
from unittest import mock

from lossreview import screen

H = {'id': 'early-entry-skip', 'loss_class': 'WRONG_SIDE', 'lever': 'skip', 'feature': 'frac_elapsed_at_entry', 'op': 'lt',
     'thresholds': [0.04, 0.08, 0.12], 'neighbor_features': [], 'mechanism': 'Entries in the first minutes have not seen the move yet.', 'cites': ['entry_px']}
ADV = {'hypothesis_id': 'early-entry-skip', 'verdict': 'survives', 'reasons': [], 'note': 'Plausible.'}


def run_cli(name, text):
    out, err = io.StringIO(), io.StringIO()
    with mock.patch('sys.stdin', io.StringIO(text)), mock.patch('sys.stdout', out), mock.patch('sys.stderr', err):
        rc = screen.main([name])
    return rc, out.getvalue(), err.getvalue()


class ScreenTests(unittest.TestCase):
    def test_a_screened_reply_is_a_fixed_point(self):
        cases = [('tag-00', [{'i': 0, 'tags': ['late_entry']}, {'i': 3, 'tags': []}]),
                 ('hyp-WRONG_SIDE', [H]),
                 ('adv-early-entry-skip', ADV)]
        for name, reply in cases:
            once = screen.screen_reply(name, reply)
            self.assertEqual(screen.screen_reply(name, once), once, name)
            self.assertEqual(once, reply, name)             # these were already clean

    def test_tags_keep_only_index_and_closed_tags(self):
        out = screen.screen_tags({'trips': [{'i': 1, 'tags': ['late_entry'], 'why': 'lost $6.80 at 15:41'}, {'i': 2, 'tags': ['not_a_tag']},
                                            {'i': 99, 'tags': []}, {'i': True, 'tags': []}, 'junk', {'i': 4, 'tags': 'late_entry'}]})
        self.assertEqual(out, [{'i': 1, 'tags': ['late_entry']}])

    def test_free_text_loses_its_figures(self):
        h = dict(H, mechanism='The 3 losers lost $2.10, 1.80 and 3.30 (45%) after entry above 0.93 at 15:41:07')
        out = screen.screen_hyp([h])[0]
        self.assertFalse(any(c in out['mechanism'] for c in '0123456789$%'))
        self.assertTrue(out['mechanism'].startswith('The losers lost'))
        self.assertEqual(screen.screen_hyp([dict(H, mechanism='1.5 2 3')])[0]['mechanism'], 'not stated')
        a = screen.screen_adv(dict(ADV, note='the 6.80 dollar loss on 15:41:07 trip'))
        self.assertFalse(any(c in a['note'] for c in '0123456789'))

    def test_thresholds_are_coarse_and_eq_values_are_words(self):
        h = dict(H, feature='spot_pre_entry', thresholds=[3224.8, 3224.9, 3199.123, 12])
        out = screen.screen_hyp([h])[0]
        self.assertEqual(out['thresholds'], [3220, 3200, 12])        # 3224.8 and 3224.9 collapse to one value; an exact level never leaves
        e = dict(H, feature='kind', op='eq', thresholds=['15m', 'hourly', 'KXBTC15M-26NOV121015-15', 'a' * 30, 'ab12cd34ef56'])
        self.assertEqual(screen.screen_hyp([e])[0]['thresholds'], ['15m', 'hourly'])
        self.assertEqual(screen.screen_hyp([dict(e, thresholds=['KXBTC15M-26NOV121015-15'])]), [])

    def test_a_hypothesis_the_validator_refuses_is_dropped_and_the_rest_kept(self):
        bad = dict(H, id='x')                                          # too short
        worse = dict(H, id='another-one', feature='pnl')               # an outcome column
        out = screen.screen_hyp({'hypotheses': [bad, H, worse, 'junk']})
        self.assertEqual([h['id'] for h in out], ['early-entry-skip'])
        self.assertEqual(len(screen.screen_hyp([dict(H, id='h%02d' % i) for i in range(10)])), screen.MAX_HYP_ITEMS)
        extra = dict(H, prose='anything', mechanism='ok')
        self.assertNotIn('prose', screen.screen_hyp([extra])[0])

    def test_an_adversary_reply_keeps_its_four_fields_only(self):
        a = screen.screen_adv(dict(ADV, extra='x', verdict='refuted', reasons=['winner_control_matches']))
        self.assertEqual(sorted(a), ['hypothesis_id', 'note', 'reasons', 'verdict'])
        self.assertIsNone(screen.screen_adv(dict(ADV, verdict='maybe')))
        self.assertIsNone(screen.screen_adv([ADV]))

    def test_nothing_usable_raises(self):
        for name, reply in (('tag-00', []), ('tag-00', 'text'), ('hyp-WRONG_SIDE', [{'id': 'x'}]), ('adv-abc', {}), ('other-1', [])):
            with self.assertRaises(ValueError, msg=(name, reply)):
                screen.screen_reply(name, reply)

    def test_the_command_line_tolerates_prose_and_prints_only_json(self):
        text = 'Here is my answer:\n```json\n' + json.dumps([dict(H, thresholds=[3224.8])]) + '\n```\nHope it helps $5.'
        rc, out, err = run_cli('hyp-WRONG_SIDE', text)
        self.assertEqual((rc, err), (0, ''))
        self.assertEqual(json.loads(out)[0]['thresholds'], [3220])
        self.assertNotIn('Hope', out)
        self.assertEqual(run_cli('hyp-WRONG_SIDE', 'no json at all')[0], 1)
        self.assertEqual(run_cli('tag-00', '[]')[0], 1)
        self.assertEqual(screen.main([]), 2)


if __name__ == '__main__':
    unittest.main()
