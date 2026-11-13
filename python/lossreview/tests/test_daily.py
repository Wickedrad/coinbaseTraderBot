"""The daily loop end to end on synthetic days: mechanical stages are the real code, the model steps are canned replies."""
import calendar
import json
import os
import random
import tempfile
import time
import unittest

from lossreview import daily, forms, registry, rules

D0 = calendar.timegm(time.strptime('2026-11-01', '%Y-%m-%d'))


def day_name(k):
    return time.strftime('%Y-%m-%d', time.gmtime(D0 + 86400 * k))


def day_rows(k, plant, seed=0, n=350, cut=0.12):
    rnd = random.Random(seed * 1000 + k)
    rows = []
    for i in range(n):
        x = ((i * 37) % 350) / 350.0 + rnd.random() / 10000.0     # an even grid: the same share of trips falls under any cut every day
        pnl = rnd.gauss(-0.2, 3.0) + (plant if x < cut else 0.0)
        t = D0 + 86400 * k + 600 + i * 60
        rows.append({'ticker': 'KXBTC15M-T%d-%d' % (k, i), 'entry_t': t - 400, 'closed_t': t, 'entry_px': rnd.choice([0.2, 0.4, 0.6, 0.8]),
                     'frac_elapsed_at_entry': x, 'pnl': pnl, 'class': 'WRONG_SIDE' if pnl < 0 else 'WIN', 'fidelity_flag': False,
                     'coin': 'BTC', 'kind': '15m', 'side': 'yes', 'count': 20, 'stake': 10.0})
    return rows


def write_days(w, ks, plant, seed=0):
    os.makedirs(os.path.join(w, 'days'), exist_ok=True)
    for k in ks:
        with open(os.path.join(w, 'days', 'trips-%s.jsonl' % day_name(k)), 'w') as fh:
            for r in day_rows(k, plant, seed):
                fh.write(json.dumps(r) + '\n')


HYP = {'id': 'early-entry-skip', 'loss_class': 'WRONG_SIDE', 'lever': 'skip', 'feature': 'frac_elapsed_at_entry', 'op': 'lt',
       'thresholds': [0.04, 0.08, 0.12], 'neighbor_features': [], 'mechanism': 'Entries in the first minutes of a window have not seen the move yet.',
       'cites': ['entry_px']}


def respond(path, obj):
    with open(path, 'w') as fh:
        fh.write('```json\n' + json.dumps(obj) + '\n```')


class DailyLoopTests(unittest.TestCase):
    def run_loop(self, plant):
        w = tempfile.mkdtemp()
        write_days(w, range(0, 13), plant)
        g = day_name(0)
        out = daily.prepare_tags(w, g)
        self.assertGreater(out['reviewable'], 20)
        wd = daily.workdir(w, g)
        index = json.load(open(os.path.join(wd, 'tag-index.json')))
        for name, ids in index.items():
            respond(os.path.join(wd, name + '.response.json'), [{'i': int(i), 'tags': ['late_entry']} for i in ids])
        self.assertEqual(daily.apply_tags(w, g)['rejected'], 0)
        self.assertEqual(daily.prepare_hyp(w, g)['classes'], ['WRONG_SIDE'])
        respond(os.path.join(wd, 'hyp-WRONG_SIDE.response.json'), [HYP])
        self.assertEqual(daily.apply_hyp(w, g)['valid'], 1)
        self.assertTrue(os.path.exists(os.path.join(wd, 'adv-early-entry-skip.prompt.txt')))
        respond(os.path.join(wd, 'adv-early-entry-skip.response.json'),
                {'hypothesis_id': 'early-entry-skip', 'verdict': 'survives', 'reasons': [], 'note': 'winner control does not match'})
        self.assertEqual(daily.apply_adv(w, g)['registered_open'], 1)
        return w, wd

    def test_a_real_effect_goes_through_sweep_then_shadow_to_ready(self):
        w, _ = self.run_loop(plant=-8.0)
        reg = registry.Registry(os.path.join(w, 'registry.jsonl'))
        self.assertEqual(reg.trials, registry.PRIOR_TRIALS + 3)
        r = daily.run_sweep(w, day_name(5))                        # days 1..5 are scoring days (day 0 generated it)
        self.assertEqual(r['candidates'] >= 1 and r['to_shadow'], 1)
        reg = registry.Registry(os.path.join(w, 'registry.jsonl'))
        st = reg.state['early-entry-skip']
        self.assertEqual(st['status'], 'shadow')
        self.assertEqual(st['frozen_day'], day_name(4))             # the first look scored exactly the first 4 scoring days (1..4)
        # shadow counts only days after the window: night 5 is the first, and it catches up on nothing earlier
        self.assertEqual(daily.run_shadow(w, day_name(5))['ready_for_pr'], [])
        seen = registry.Registry(os.path.join(w, 'registry.jsonl')).state['early-entry-skip']['shadow']
        self.assertEqual([r['day'] for r in seen], [day_name(5)])
        ready = []
        for k in range(6, 13):
            ready += daily.run_shadow(w, day_name(k))['ready_for_pr']
        self.assertEqual(ready, ['early-entry-skip'])
        self.assertEqual(registry.Registry(os.path.join(w, 'registry.jsonl')).state['early-entry-skip']['status'], 'proposal')
        # a rerun of a finished night changes nothing
        self.assertEqual(daily.run_shadow(w, day_name(12))['ready_for_pr'], [])

    def test_noise_never_reaches_shadow(self):
        w, _ = self.run_loop(plant=0.0)
        r = daily.run_sweep(w, day_name(8))
        self.assertEqual(r['to_shadow'], 0)
        st = registry.Registry(os.path.join(w, 'registry.jsonl')).state['early-entry-skip']
        self.assertEqual(st['status'], 'swept')
        self.assertTrue(daily.status(w)['by_status']['swept'] == 1)

    def test_a_refuted_hypothesis_is_registered_as_a_trial_and_retired(self):
        w = tempfile.mkdtemp()
        write_days(w, range(0, 3), -4.0)
        g = day_name(0)
        wd = daily.workdir(w, g)
        daily.prepare_tags(w, g)
        daily.apply_hyp(w, g)       # nothing answered yet: no hypotheses
        json.dump([HYP], open(os.path.join(wd, 'hypotheses.json'), 'w'))
        respond(os.path.join(wd, 'adv-early-entry-skip.response.json'),
                {'hypothesis_id': 'early-entry-skip', 'verdict': 'refuted', 'reasons': ['hindsight_feature'], 'note': 'x'})
        out = daily.apply_adv(w, g)
        self.assertEqual(out['registered_refuted'], 1)
        reg = registry.Registry(os.path.join(w, 'registry.jsonl'))
        self.assertEqual(reg.state['early-entry-skip']['status'], 'retired')
        self.assertEqual(reg.trials, registry.PRIOR_TRIALS + 3)      # a refuted hypothesis still counts

    def test_invalid_model_output_never_reaches_the_registry(self):
        w = tempfile.mkdtemp()
        write_days(w, range(0, 2), -4.0)
        g = day_name(0)
        wd = daily.workdir(w, g)
        daily.prepare_tags(w, g)
        daily.prepare_hyp(w, g)
        bad = dict(HYP, id='leaky-one', feature='best_bid_held')           # an outcome column
        respond(os.path.join(wd, 'hyp-WRONG_SIDE.response.json'), [bad, 'not an object'])
        out = daily.apply_hyp(w, g)
        self.assertEqual((out['valid'], out['rejected']), (0, 2))
        self.assertEqual(daily.apply_adv(w, g), {'registered_open': 0, 'registered_refuted': 0})

    def test_a_curve_hypothesis_is_swept_but_waits_for_the_owner(self):
        w = tempfile.mkdtemp()
        write_days(w, range(0, 9), -8.0)
        for k in range(9):          # put the planted effect on the curve column instead
            p = os.path.join(w, 'days', 'trips-%s.jsonl' % day_name(k))
            rows = [json.loads(l) for l in open(p)]
            for r in rows:
                r['rank'] = r['frac_elapsed_at_entry'] * 40
            open(p, 'w').write(''.join(json.dumps(r) + '\n' for r in rows))
        g = day_name(0)
        wd = daily.workdir(w, g)
        daily.prepare_tags(w, g)
        daily.prepare_hyp(w, g)
        h = dict(HYP, id='rank-skip', feature='rank', thresholds=[1.6, 3.2, 4.8])
        respond(os.path.join(wd, 'hyp-WRONG_SIDE.response.json'), [h])
        self.assertEqual(daily.apply_hyp(w, g)['curve_edits'], 1)
        respond(os.path.join(wd, 'adv-rank-skip.response.json'), {'hypothesis_id': 'rank-skip', 'verdict': 'unclear', 'reasons': ['other'], 'note': 'x'})
        daily.apply_adv(w, g)
        r = daily.run_sweep(w, day_name(8))
        reg = registry.Registry(os.path.join(w, 'registry.jsonl'))
        self.assertEqual(reg.state['rank-skip']['status'], 'swept')       # frozen, but no shadow without the owner
        self.assertTrue(reg.state['rank-skip'].get('frozen'))
        self.assertEqual(r['to_shadow'], 0)
        self.assertEqual(daily.status(w)['curve_edits_waiting'], ['rank-skip'])
        reg.owner_ok('rank-skip')
        reg.move('rank-skip', 'shadow')

    def test_a_reply_cannot_flood_collide_or_repeat_what_is_registered(self):
        w = tempfile.mkdtemp()
        write_days(w, range(0, 3), -1.0)
        g = day_name(0)
        wd = daily.workdir(w, g)
        daily.prepare_tags(w, g)
        daily.prepare_hyp(w, g)

        def h(i, feature, op, thresholds=(0.3,)):
            return dict(HYP, id=i, feature=feature, op=op, thresholds=list(thresholds))
        reply = [h('idea-a1', 'frac_elapsed_at_entry', 'lt'), h('idea-a1', 'entry_px', 'lt'),          # a second use of an id
                 h('idea-a2', 'frac_elapsed_at_entry', 'lt', (0.5,)),                              # the same idea under a new id
                 h('idea-a3', 'frac_elapsed_at_entry', 'gt'), h('idea-a4', 'entry_px', 'gt'), h('idea-a5', 'count', 'gt', (10,)), h('idea-a6', 'stake', 'gt', (5,))]
        respond(os.path.join(wd, 'hyp-WRONG_SIDE.response.json'), reply)
        out = daily.apply_hyp(w, g)
        self.assertEqual(out['valid'], daily.HYP_PER_CLASS)            # three a class, never more
        self.assertEqual(out['rejected'], len(reply) - daily.HYP_PER_CLASS)
        ids = [x['id'] for x in json.load(open(os.path.join(wd, 'hypotheses.json')))]
        self.assertEqual(ids, ['idea-a1', 'idea-a3', 'idea-a4'])                      # in reply order: the id twice and the repeated idea are out
        for i in ids:
            respond(os.path.join(wd, 'adv-%s.response.json' % i), {'hypothesis_id': i, 'verdict': 'refuted', 'reasons': ['other'], 'note': 'x'})
        self.assertEqual(daily.apply_adv(w, g)['registered_refuted'], 3)
        # a later day: the same ids and the same ideas (refuted ones included) are not run again
        g2 = day_name(1)
        wd2 = daily.workdir(w, g2)
        daily.prepare_tags(w, g2)
        daily.prepare_hyp(w, g2)
        respond(os.path.join(wd2, 'hyp-WRONG_SIDE.response.json'), [h('idea-a1', 'count', 'lt', (5,)), h('idea-b1', 'entry_px', 'gt', (0.9,)), h('idea-b2', 'count', 'gt', (10,))])
        out2 = daily.apply_hyp(w, g2)
        self.assertEqual((out2['valid'], out2['rejected']), (1, 2))    # only b2 is new

    def test_the_whole_day_is_capped(self):
        w = tempfile.mkdtemp()
        write_days(w, range(0, 3), -1.0)
        g = day_name(0)
        wd = daily.workdir(w, g)
        daily.prepare_tags(w, g)
        daily.prepare_hyp(w, g)
        respond(os.path.join(wd, 'hyp-WRONG_SIDE.response.json'), [dict(HYP, id='wide-%d' % i, feature=f, op=o, thresholds=[t]) for i, (f, o, t) in enumerate(
            [('frac_elapsed_at_entry', 'lt', 0.3), ('frac_elapsed_at_entry', 'gt', 0.3), ('entry_px', 'lt', 0.5)])])
        daily.HYP_PER_DAY, keep = 2, daily.HYP_PER_DAY
        try:
            self.assertEqual(daily.apply_hyp(w, g)['valid'], 2)
        finally:
            daily.HYP_PER_DAY = keep

    def test_trips_the_builder_could_not_vouch_for_never_reach_the_sweep(self):
        w, _ = self.run_loop(plant=-8.0)
        for k in range(1, 13):          # the whole planted effect sits in trips flagged as FIDELITY
            p = os.path.join(w, 'days', 'trips-%s.jsonl' % day_name(k))
            with open(p) as fh:
                rows = [json.loads(l) for l in fh]
            for r in rows:
                if r['frac_elapsed_at_entry'] < 0.12:
                    r['fidelity_flag'] = True
            with open(p, 'w') as fh:
                fh.write(''.join(json.dumps(r) + '\n' for r in rows))
        r = daily.run_sweep(w, day_name(5))
        self.assertEqual((r['looked'], r['to_shadow']), (1, 0))
        # and a row with no P&L at all is not scored either
        p = os.path.join(w, 'days', 'trips-%s.jsonl' % day_name(2))
        with open(p) as fh:
            rows = [json.loads(l) for l in fh]
        rows[0]['pnl'] = None
        with open(p, 'w') as fh:
            fh.write(''.join(json.dumps(r) + '\n' for r in rows))
        self.assertEqual(len(daily.load_days(w, scoring=True)[day_name(2)]), len(rows) - 1 - sum(1 for r in rows[1:] if r['fidelity_flag']))
        self.assertEqual(len(daily.load_days(w)[day_name(2)]), len(rows))

    def test_two_skip_rules_that_each_fit_the_floor_are_not_both_promoted_when_together_they_do_not(self):
        w = tempfile.mkdtemp()
        os.makedirs(os.path.join(w, 'days'))
        for k in range(0, 13):
            rnd = random.Random(k)
            with open(os.path.join(w, 'days', 'trips-%s.jsonl' % day_name(k)), 'w') as fh:
                for i in range(350):
                    xa = ((i * 37) % 350) / 350.0
                    xb = (((i * 53) % 350) / 350.0) * 900.0                # a second, independent grid: seconds left in the window
                    pnl = rnd.gauss(-0.2, 3.0) + (-8.0 if xa < 0.10 else 0.0) + (-8.0 if xb < 108.0 else 0.0)
                    t = D0 + 86400 * k + 600 + i * 60
                    fh.write(json.dumps({'ticker': 'KXBTC15M-T%d-%d' % (k, i), 'entry_t': t - 400, 'closed_t': t, 'entry_px': 0.5,
                                         'frac_elapsed_at_entry': xa, 'left_at_entry_s': xb, 'pnl': pnl, 'class': 'WRONG_SIDE' if pnl < 0 else 'WIN',
                                         'fidelity_flag': False, 'coin': 'BTC', 'kind': '15m', 'side': 'yes', 'count': 20, 'stake': 10.0}) + '\n')
        g = day_name(0)
        wd = daily.workdir(w, g)
        daily.prepare_tags(w, g)
        daily.prepare_hyp(w, g)
        ha = dict(HYP, id='rule-ha', feature='frac_elapsed_at_entry', thresholds=[0.05, 0.075, 0.10])
        hb = dict(HYP, id='rule-hb', feature='left_at_entry_s', thresholds=[54, 81, 108])
        respond(os.path.join(wd, 'hyp-WRONG_SIDE.response.json'), [ha, hb])
        self.assertEqual(daily.apply_hyp(w, g)['valid'], 2)
        for i in ('rule-ha', 'rule-hb'):
            respond(os.path.join(wd, 'adv-%s.response.json' % i), {'hypothesis_id': i, 'verdict': 'survives', 'reasons': [], 'note': 'x'})
        daily.apply_adv(w, g)
        self.assertEqual(daily.run_sweep(w, day_name(5))['to_shadow'], 2)
        ready, held = [], []
        for k in range(5, 13):
            out = daily.run_shadow(w, day_name(k))
            ready += out['ready_for_pr']
            held = out['held_by_floor']
        reg = registry.Registry(os.path.join(w, 'registry.jsonl'))
        self.assertEqual(len(ready), 1)                                  # one of the two goes to a promotion PR ...
        self.assertEqual(len(held), 1)                                   # ... the other waits in shadow: together they flag over 15%
        self.assertEqual(sorted(s['status'] for r, s in reg.state.items() if r in ('rule-ha', 'rule-hb')), ['proposal', 'shadow'])
        self.assertNotEqual(ready[0], held[0])

    def test_usage_is_logged_and_checked_against_the_allowance(self):
        w = tempfile.mkdtemp()
        out = daily.usage(w, '2026-11-13', 'tag', 40_000, 10_000, 25)
        self.assertEqual(out['used_today'], 50_000)
        self.assertTrue(out['ok'])
        out = daily.usage(w, '2026-11-13', 'hypothesize', 300_000, 260_000, 3)
        self.assertEqual((out['used_today'], out['ok']), (610_000, False))     # over the 600k a day: the routine skips the model steps
        with open(os.path.join(w, 'usage.jsonl'), 'a') as fh:
            fh.write('\n{"torn"\n[1]\n')                                       # a blank, a torn and a non-object line
        self.assertEqual(daily.status(w)['tokens_logged'], 610_000)           # status still reads it
        self.assertEqual(daily.budget(w, '2026-11-13')['used_today'], 610_000)
        with self.assertRaises(ValueError):
            daily.usage(w, '2026-11-13', 'no-such-step', 1, 1, 1)
        self.assertEqual(daily.main(['usage', '2026-11-14', '--w', w, '--step', 'audit', '--tokens-in', '5', '--tokens-out', '5', '--items', '1']), 0)

    def test_pending_lists_days_with_a_trip_file_until_they_are_marked_done(self):
        w = tempfile.mkdtemp()
        write_days(w, range(0, 3), -1.0)
        days = [day_name(k) for k in range(3)]
        self.assertEqual(daily.pending(w)['days'], days)           # oldest first
        daily.mark_done(w, days[0])
        self.assertEqual(daily.pending(w)['days'], days[1:])
        with self.assertRaises(SystemExit):                          # no file for that day: nothing to mark
            daily.mark_done(w, '2030-01-01')
        self.assertEqual(daily.main(['pending', '--w', w]), 0)

    def test_window_keeps_dollars_out_of_the_log_and_cuts_by_closing_time(self):
        w = tempfile.mkdtemp()
        write_days(w, [1], -1.0)
        day = day_name(1)
        everything = daily.window(w, day)
        self.assertEqual(everything['trips'], 350)
        self.assertNotIn('net', json.dumps(everything))                       # the log line has a count, never a dollar figure
        part = daily.window(w, day, '00:10:00', '01:10:00')                   # trips close at +600 s and then once a minute
        self.assertEqual(part['trips'], 60)
        saved = json.load(open(os.path.join(w, 'work', day, part['file'])))
        self.assertEqual((saved['trips'], saved['since'], saved['until']), (60, '00:10:00', '01:10:00'))
        self.assertIn('net', saved)                                           # the dollars are in the private file
        self.assertEqual(daily.window(w, day, '23:59', '24:00')['trips'], 0)
        for bad in ('1:2:3:4', 'ab:cd', '25:00:01'):
            with self.assertRaises(SystemExit):
                daily.window(w, day, '00:00', bad)
        with self.assertRaises(SystemExit):
            daily.window(w, '2030-01-01')
        self.assertEqual(daily.main(['window', day, '--w', w, '--until', '02:00']), 0)

    def test_public_lines_hold_back_a_figure_that_is_one_trade(self):
        from lossreview import nightly
        small = nightly.public_lines({'day': 'd', 'trips': 4, 'losers': 1, 'net': -3.0, 'fees': 1.0, 'gross': -2.0,
                                      'classes': [{'class': 'WRONG_SIDE', 'trips': 1, 'dollars': -3.0}]})
        self.assertNotIn('net', small[0])
        self.assertTrue(any('under 5 trips' in l for l in small))
        big = nightly.public_lines({'day': 'd', 'trips': 40, 'losers': 20, 'net': -30.0, 'fees': 10.0, 'gross': -20.0,
                                    'classes': [{'class': 'WRONG_SIDE', 'trips': 20, 'dollars': -50.0}]})
        self.assertIn('"net": -30.0', big[0])
        self.assertIn('dollars -50.00', big[1])

    def test_responses_are_saved_only_for_prompts_that_exist(self):
        w = tempfile.mkdtemp()
        write_days(w, [1], -1.0)
        day = day_name(1)
        daily.prepare_tags(w, day)
        wd = daily.workdir(w, day)
        names = sorted(f[:-len('.prompt.txt')] for f in os.listdir(wd) if f.endswith('.prompt.txt'))
        self.assertTrue(names)
        out = daily.save_responses(w, day, json.dumps({names[0]: [{'i': 0, 'tags': ['late_entry']}]}))
        self.assertEqual(out['saved'], [names[0]])
        self.assertEqual(json.load(open(os.path.join(wd, names[0] + '.response.json'))), [{'i': 0, 'tags': ['late_entry']}])
        daily.save_responses(w, day, {names[0]: '```json\n[]\n```'})                      # the model's text is kept as it came
        self.assertEqual(open(os.path.join(wd, names[0] + '.response.json')).read(), '```json\n[]\n```')
        for bad in ('', 'not json', '[1]', json.dumps({'../evil': 1}), json.dumps({'tag-99': []}), json.dumps({'hyp-WRONG_SIDE': {}}),
                    json.dumps({'adv-x': 1}), 'x' * 70_000):
            with self.assertRaises(SystemExit, msg=bad[:30]):
                daily.save_responses(w, day, bad)
        os.environ['LR_RESPONSES'] = json.dumps({names[0]: []})
        try:
            self.assertEqual(daily.main(['responses', day, '--w', w]), 0)
        finally:
            del os.environ['LR_RESPONSES']


if __name__ == '__main__':
    unittest.main()
