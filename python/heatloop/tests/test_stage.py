import contextlib
import dataclasses
import gzip
import io
import json
import os
import tempfile
import unittest
from unittest import mock

import numpy as np

from heatloop import calls as C
from heatloop import eventset as ES
from heatloop import guards, optimize, stage
from heatloop.tests import test_evaluate as TE
from heatloop.tests.test_universe import HEAD, line

DAYS = 181
KEYS = ['1m:AAA=up', '1m:BBB=down', '5m:CCC=up', '15m:DDD=up']


def league(path):
    lines = []
    for coin in ('BTC', 'ETH'):
        for i, (k, d) in enumerate(zip(KEYS, (1, -1, 1, 1))):
            lines.append(line(coin, k, dir_=d, nA=1000 + i, nB=500 + i, sA=54.0 + i * 0.1, sB=53.0 + i * 0.1, oheat=100 - i))
    with gzip.open(path, 'wt') as f:
        f.write(HEAD + ''.join(lines))


def run(argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        stage.main(argv)
    return [json.loads(x.split(' ', 2)[2]) for x in out.getvalue().splitlines() if x.startswith('HEATLOOP')], out.getvalue()


class Glue(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.league = os.path.join(cls.tmp, 'league.csv.gz')
        league(cls.league)
        rng = np.random.default_rng(3)
        cls.dev = os.path.join(cls.tmp, 'dev')
        os.makedirs(cls.dev)
        for coin in ('BTC', 'ETH'):
            ES.save(TE.make_set(coin, rng, False, per_day=8, days=DAYS), os.path.join(cls.dev, f'dev-{coin}-t0.npz'))
            for tw in (1, 2, 3):
                es = TE.make_set(coin, rng, False, per_day=8, days=DAYS)
                es.twin = tw
                ES.save(es, os.path.join(cls.dev, f'dev-{coin}-t{tw}.npz'))

    def setUp(self):
        p = mock.patch.object(stage, 'LEAGUE_SHA', stage.universe.sha256(self.league))
        p.start()
        self.addCleanup(p.stop)

    def test_round0_prints_the_baseline_and_the_gate(self):
        recs, text = run(['round0', '--dev', self.dev, '--league', self.league])
        r = recs[0]
        self.assertEqual(r['spec']['top_n'], 10)
        self.assertEqual(len(r['checks']), 10)
        self.assertIn('BTC', r['per_day'])
        self.assertEqual(len(r['twin_gate']['twins']['rows']), 6)
        self.assertLess(abs(r['hit'] - 0.5), 0.1)
        self.assertNotIn('Traceback', text)

    def test_a_wrong_league_file_is_refused(self):
        with mock.patch.object(stage, 'LEAGUE_SHA', 'x'):
            with self.assertRaises(SystemExit):
                run(['round0', '--dev', self.dev, '--league', self.league])

    def test_dev_writes_every_trial_and_one_line_per_round(self):
        out = os.path.join(self.tmp, 'devout')
        with mock.patch.object(optimize, 'PLAN', optimize.PLAN[:1] + optimize.PLAN[2:3]):
            recs, _ = run(['dev', '--dev', self.dev, '--league', self.league, '--out', out])
        rounds = [r for r in recs if 'round' in r and 'best' in r]
        self.assertEqual(len(rounds), 2)
        with open(os.path.join(out, 'trials.jsonl')) as f:
            n = sum(1 for _ in f)
        self.assertEqual(n, 4 + 7)
        self.assertEqual(recs[-1]['trials'], 11)

    def test_inspect_and_timing_read_the_dev_rounds_only(self):
        out = os.path.join(self.tmp, 'devout2')
        with mock.patch.object(optimize, 'PLAN', optimize.PLAN[:1] + optimize.PLAN[2:3]):
            run(['dev', '--dev', self.dev, '--league', self.league, '--out', out])
        rounds = os.path.join(out, 'rounds.json')
        recs, text = run(['inspect', '--dev', self.dev, '--league', self.league, '--rounds', rounds])
        self.assertEqual(len(recs), 2)
        self.assertEqual(len(recs[0]['checks']), 10)
        recs, text = run(['timing', '--dev', self.dev, '--league', self.league, '--rounds', rounds])
        self.assertEqual(sorted(recs[0]), ['BTC', 'ETH'])
        self.assertLess(abs(recs[0]['BTC']['fade15'] - 0.5), 0.05)
        self.assertEqual(len(recs), 3)
        self.assertEqual(recs[1]['same_side']['n'] + recs[1]['other_side']['n'] + recs[1]['no_past_move']['n'], recs[1]['decided'])
        self.assertNotIn('Traceback', text)

    def test_val_needs_the_flag_and_prints_the_bits_only(self):
        spec = os.path.join(self.tmp, 'spec.json')
        with open(spec, 'w') as f:
            json.dump(optimize.ROUND0.as_dict(), f)
        val = os.path.join(self.tmp, 'val')
        os.makedirs(val)
        rng = np.random.default_rng(4)
        for coin in ('BTC', 'ETH'):
            for tw in (0, 1, 2, 3):
                es = TE.make_set(coin, rng, False, per_day=8, days=123, t0=guards.VAL_START)
                es.twin, es.scope = tw, 'val'
                ES.save(es, os.path.join(val, f'val-{coin}-t{tw}.npz'))
        priv = os.path.join(self.tmp, 'private')
        args = ['val', '--spec', spec, '--val', val, '--league', self.league, '--private', priv, '--round', '1']
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop('HEATLOOP_VAL', None)
            with self.assertRaises(SystemExit):
                run(args)
        with mock.patch.dict(os.environ, {'HEATLOOP_VAL': '1'}):
            recs, text = run(args)
        self.assertEqual(set(recs[0]), {'round', 'hash', 'gate_ok', 'bit', 'core_bit'})   # nothing else reaches the log
        self.assertIn(recs[0]['bit'], (0, 1))
        self.assertIn(recs[0]['core_bit'], (0, 1))
        self.assertLessEqual(recs[0]['bit'], recs[0]['core_bit'] or 1)
        with open(os.path.join(priv, 'val-look-round1.json')) as f:
            table = json.load(f)
        self.assertEqual(len(table['checks']), 10)

    def test_dev_family_h2_runs_its_own_plan_from_its_own_start(self):
        out = os.path.join(self.tmp, 'devout-h2')
        with mock.patch.object(optimize, 'PLAN_H2', optimize.PLAN_H2[1:2]):
            recs, _ = run(['dev', '--dev', self.dev, '--league', self.league, '--out', out, '--family', 'h2'])
        start = [r for r in recs if r.get('start') and 'family' in r]
        self.assertEqual(start[0]['start']['spec']['side'], 'fade')
        done = recs[-1]
        self.assertEqual((done['family'], done['trials'], done['budget']), ('h2', 5, 602))
        with open(os.path.join(out, 'trials.jsonl')) as f:
            specs = [json.loads(x)['spec'] for x in f]
        self.assertEqual({sp.get('side', 'heat') for sp in specs}, {'heat', 'fade'})

    def test_qualifying_rounds_are_improved_eligible_core8_distinct_in_order_and_at_most_three(self):
        def rd(n, h, improved=True, eligible=True, passed=(1,) * 8 + (0, 0)):
            return dict(round=n, improved=improved, best=dict(hash=h, eligible=eligible, passed=list(passed), spec={}))
        rounds = [rd(1, 'a'), rd(2, 'b', improved=False), rd(3, 'c', passed=(1,) * 7 + (0, 1, 1)), rd(4, 'd', eligible=False),
                  rd(5, 'a'), rd(6, 'e', passed=(1,) * 10), rd(7, 'f'), rd(8, 'g')]
        self.assertEqual([r['round'] for r in stage.qualifying(rounds)], [1, 6, 7])
        self.assertEqual([r['round'] for r in stage.qualifying(rounds, 2)], [1, 6])
        self.assertEqual(stage.qualifying([rd(1, 'a', passed=(1,) * 6 + (0, 0, 1, 1))]), [])

    def make_val(self, name):
        val = os.path.join(self.tmp, name)
        os.makedirs(val)
        rng = np.random.default_rng(4)
        for coin in ('BTC', 'ETH'):
            for tw in (0, 1, 2, 3):
                es = TE.make_set(coin, rng, False, per_day=8, days=123, t0=guards.VAL_START)
                es.twin, es.scope = tw, 'val'
                ES.save(es, os.path.join(val, f'val-{coin}-t{tw}.npz'))
        return val

    def rounds_file(self, name, specs):
        path = os.path.join(self.tmp, name)
        rounds = [dict(round=n, group='x', improved=True, best=dict(hash=C.spec_hash(sp), eligible=True, passed=[1] * 8 + [0, 0], spec=sp.as_dict()))
                  for n, sp in specs]
        with open(path, 'w') as f:
            json.dump(rounds, f)
        return path

    def test_looks_need_the_flag_and_print_bits_only(self):
        val = self.make_val('val-looks')
        fade = dataclasses.replace(optimize.ROUND0_H2, tfs=('1m',), top_n=2, min_share_A=0.0, min_share_B=0.0)
        rounds = self.rounds_file('rounds-a.json', [(2, fade), (4, dataclasses.replace(fade, fade_k=5))])
        priv = os.path.join(self.tmp, 'private-looks')
        args = ['looks', '--rounds', rounds, '--val', val, '--league', self.league, '--private', priv]
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop('HEATLOOP_VAL', None)
            with self.assertRaises(SystemExit):
                run(args)
        self.assertFalse(os.path.exists(priv))
        with mock.patch.dict(os.environ, {'HEATLOOP_VAL': '1'}):
            recs, text = run(args)
        self.assertEqual(recs[0]['candidates'], [dict(round=2, hash=C.spec_hash(fade)[:12]), dict(round=4, hash=C.spec_hash(dataclasses.replace(fade, fade_k=5))[:12])])
        looks = [r for r in recs if 'bit' in r]
        self.assertEqual([set(r) for r in looks], [{'round', 'hash', 'gate_ok', 'bit', 'core_bit'}] * 2)
        self.assertEqual(recs[-1], dict(taken=2, stopped='looks used up'))
        self.assertNotIn('checks', text)
        for n in (2, 4):
            with open(os.path.join(priv, f'val-look-round{n}.json')) as f:
                self.assertEqual(len(json.load(f)['checks']), 10)

    def test_looks_stop_at_the_first_bit_and_at_a_gate_failure_without_using_a_look(self):
        val = self.make_val('val-looks2')
        fade = dataclasses.replace(optimize.ROUND0_H2, tfs=('1m',), top_n=2, min_share_A=0.0, min_share_B=0.0)
        rounds = self.rounds_file('rounds-b.json', [(1, fade), (3, dataclasses.replace(fade, fade_k=5)), (5, dataclasses.replace(fade, fade_k=1))])
        args = ['looks', '--rounds', rounds, '--val', val, '--league', self.league, '--private', os.path.join(self.tmp, 'private-looks2')]
        seq = [dict(round=1, hash='x', gate_ok=True, bit=0, core_bit=0), dict(round=3, hash='y', gate_ok=True, bit=0, core_bit=1)]
        with mock.patch.dict(os.environ, {'HEATLOOP_VAL': '1'}), mock.patch.object(stage, 'look', side_effect=seq) as m:
            recs, _ = run(args)
        self.assertEqual(m.call_count, 2)                                              # round 5 is never looked at
        self.assertEqual(recs[-1], dict(taken=2, stopped='a bit is 1'))
        bad = [dict(round=1, hash='x', gate_ok=False, bit=0, core_bit=0)]
        with mock.patch.dict(os.environ, {'HEATLOOP_VAL': '1'}), mock.patch.object(stage, 'look', side_effect=bad) as m:
            recs, _ = run(args)
        self.assertEqual(m.call_count, 1)
        self.assertEqual(recs[-1], dict(taken=0, stopped='gate failed (no look used)'))

    def test_looks_refuse_a_rounds_file_whose_spec_does_not_hash_to_its_recorded_hash(self):
        fade = dataclasses.replace(optimize.ROUND0_H2, tfs=('1m',), top_n=2, min_share_A=0.0, min_share_B=0.0)
        path = self.rounds_file('rounds-stale.json', [(2, fade)])
        with open(path) as f:
            rounds = json.load(f)
        rounds[0]['best']['spec']['top_n'] = 3                                                # the spec was edited after its hash was recorded
        with open(path, 'w') as f:
            json.dump(rounds, f)
        with mock.patch.dict(os.environ, {'HEATLOOP_VAL': '1'}), mock.patch.object(stage, 'look') as m:
            with self.assertRaises(SystemExit):
                run(['looks', '--rounds', path, '--val', os.path.join(self.tmp, 'nowhere'), '--league', self.league,
                     '--private', os.path.join(self.tmp, 'p4')])
        m.assert_not_called()

    def test_no_qualifying_round_means_no_look_and_no_val_file_is_read(self):
        path = os.path.join(self.tmp, 'rounds-none.json')
        with open(path, 'w') as f:
            json.dump([dict(round=1, improved=False, best=dict(hash='a', eligible=True, passed=[1] * 10, spec={}))], f)
        empty = os.path.join(self.tmp, 'no-val-here')                                    # a missing directory would fail if it were read
        with mock.patch.dict(os.environ, {'HEATLOOP_VAL': '1'}):
            recs, _ = run(['looks', '--rounds', path, '--val', empty, '--league', self.league, '--private', os.path.join(self.tmp, 'p3')])
        self.assertEqual(recs[-1], dict(taken=0, stopped='no round qualifies on DEV'))

    def test_a_dev_set_filed_as_val_is_refused(self):
        d = os.path.join(self.tmp, 'mixed')
        os.makedirs(d)
        ES.save(TE.make_set('BTC', np.random.default_rng(1), False, per_day=2, days=3), os.path.join(d, 'val-BTC-t0.npz'))   # scope dev inside
        with self.assertRaises(SystemExit):
            stage.read_sets(d, 'val')

    def test_cut_points_cover_fold_edges_and_stay_inside_dev(self):
        lo, hi = guards.DEV
        pts = stage.cut_points(lo, hi)
        self.assertGreaterEqual(len(pts), 12)
        self.assertTrue(all(lo <= p < hi for p in pts))
        for d in ('2026-01-01', '2026-02-28', '2026-03-01', '2026-04-30', '2026-05-01', '2026-06-30'):
            self.assertTrue(any(guards.ms(d) <= p < guards.ms(d) + 86_400_000 for p in pts), d)

    def test_spec_round_trips_through_json(self):
        s = optimize.g4(optimize.ROUND0)[10]
        self.assertEqual(stage.spec_from(json.loads(json.dumps(s.as_dict()))), s)


if __name__ == '__main__':
    unittest.main()
