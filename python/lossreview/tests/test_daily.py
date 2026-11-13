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
        x = rnd.random()
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
        w, _ = self.run_loop(plant=-4.0)
        reg = registry.Registry(os.path.join(w, 'registry.jsonl'))
        self.assertEqual(reg.trials, registry.PRIOR_TRIALS + 3)
        r = daily.run_sweep(w, day_name(5))                        # days 1..5 are scoring days (day 0 generated it)
        self.assertEqual(r['candidates'] >= 1 and r['to_shadow'], 1)
        reg = registry.Registry(os.path.join(w, 'registry.jsonl'))
        st = reg.state['early-entry-skip']
        self.assertEqual(st['status'], 'shadow')
        self.assertEqual(st['frozen_day'], day_name(5))
        # shadow never counts the freeze day or earlier
        self.assertEqual(daily.run_shadow(w, day_name(5))['ready_for_pr'], [])
        self.assertEqual(len(registry.Registry(os.path.join(w, 'registry.jsonl')).state['early-entry-skip']['shadow']), 0)
        ready = []
        for k in range(6, 13):
            ready += daily.run_shadow(w, day_name(k))['ready_for_pr']
        self.assertEqual(ready, ['early-entry-skip'])
        self.assertEqual(registry.Registry(os.path.join(w, 'registry.jsonl')).state['early-entry-skip']['status'], 'proposal')

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
        write_days(w, range(0, 9), -4.0)
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


if __name__ == '__main__':
    unittest.main()
