import contextlib
import gzip
import io
import json
import os
import tempfile
import unittest
from unittest import mock

import numpy as np

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

    def test_val_needs_the_flag_and_prints_one_bit_only(self):
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
        self.assertEqual(set(recs[0]), {'round', 'hash', 'gate_ok', 'bit'})            # nothing else reaches the log
        self.assertIn(recs[0]['bit'], (0, 1))
        with open(os.path.join(priv, 'val-look-round1.json')) as f:
            table = json.load(f)
        self.assertEqual(len(table['checks']), 10)

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
