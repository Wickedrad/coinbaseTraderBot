import os
import tempfile
import unittest

import numpy as np

from heatloop import calls as C
from heatloop import eventset as ES
from heatloop import evaluate as EV
from heatloop import guards

MIN = 60_000
DAYS = 40


def universe(coin):
    base = dict(coin=coin, h=15, aliases=[], share_A=55.0, share_B=55.0, n_A=9000, n_B=4000)
    return [dict(base, key='1m:AAA=up', tf='1m', dir=1, rank_coin=1),
            dict(base, key='1m:BBB=down', tf='1m', dir=-1, rank_coin=2),
            dict(base, key='5m:CCC=up', tf='5m', dir=1, rank_coin=3, aliases=['5m:CCC2=up']),
            dict(base, key='15m:DDD=up', tf='15m', dir=1, rank_coin=4)]


def make_set(coin, rng, foresight, per_day=6, days=DAYS, t0=guards.DEV[0]):
    n = days * 1440
    steps = rng.choice([-1.0, 1.0], n) * rng.integers(1, 4, n)
    o = 100.0 + np.cumsum(steps) * 0.01
    o = np.maximum(o, 1.0)
    rows, keys = [], []
    for d in range(days):
        for r in np.sort(rng.choice(np.arange(d * 1440 + 100, d * 1440 + 1300), per_day, replace=False)):
            up = o[r + 15] > o[r] if r + 15 < n else True
            if foresight:
                keys.append('1m:AAA=up' if up else '1m:BBB=down')
            else:
                keys.append('1m:AAA=up' if rng.random() < 0.5 else '1m:BBB=down')
            rows.append(int(r))
    names = sorted(set(keys))
    return ES.EventSet(coin, 0, 'dev', t0, n, 0, o, 0.01, names, rows, [names.index(k) for k in keys])


class Evaluate(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(5)
        self.rows = universe('BTC') + universe('ETH')
        self.lo, self.hi = guards.DEV[0], guards.DEV[0] + DAYS * 86_400_000
        self.fore = {c: make_set(c, rng, True) for c in ('BTC', 'ETH')}
        self.rand = {c: make_set(c, rng, False) for c in ('BTC', 'ETH')}

    def test_foresight_events_hit_and_random_events_do_not(self):
        spec = C.Spec(tfs=('1m',), top_n=2)
        a = EV.evaluate(spec, self.fore, self.rows, self.lo, self.hi, blocks=2)
        b = EV.evaluate(spec, self.rand, self.rows, self.lo, self.hi, blocks=2)
        self.assertGreater(a['hit_rate'], 0.95)
        self.assertLess(abs(b['hit_rate'] - 0.5), 0.07)
        self.assertEqual(len(a['checks']), 10)
        self.assertGreater(a['n_decided'], 300)

    def test_calls_before_the_window_are_not_scored(self):
        spec = C.Spec(tfs=('1m',), top_n=2)
        full = EV.evaluate(spec, self.fore, self.rows, self.lo, self.hi, blocks=2)
        half = EV.evaluate(spec, self.fore, self.rows, self.lo + 20 * 86_400_000, self.hi, blocks=2)
        self.assertLess(half['n_calls'], full['n_calls'] * 0.6)
        self.assertGreater(half['n_calls'], full['n_calls'] * 0.4)

    def test_admission_limits_the_keys(self):
        one = EV.evaluate(C.Spec(tfs=('1m',), top_n=1), self.fore, self.rows, self.lo, self.hi, blocks=2)
        two = EV.evaluate(C.Spec(tfs=('1m',), top_n=2), self.fore, self.rows, self.lo, self.hi, blocks=2)
        self.assertLess(one['n_calls'], two['n_calls'])
        none = EV.evaluate(C.Spec(tfs=('15m',), top_n=1), self.fore, self.rows, self.lo, self.hi, blocks=2)
        self.assertEqual(none['n_calls'], 0)                       # the only 15m row never fires here

    def test_follows_mode_uses_the_lapsed_base_calls_as_the_comparison(self):
        spec = C.Spec(tfs=('1m',), top_n=2, ta_confirm='follows', ta_conf_k=30, ta_pool=4)
        r = EV.run(spec, self.fore, self.rows)
        self.assertIsNone(r['calls'].conf)
        self.assertIsNotNone(r['unconf'])
        precedes = EV.run(C.Spec(tfs=('1m',), top_n=2, ta_confirm='precedes', ta_pool=4), self.fore, self.rows)
        self.assertIsNotNone(precedes['calls'].conf)
        self.assertIsNone(precedes['unconf'])

    def test_random_sides_keep_the_call_times(self):
        spec = C.Spec(tfs=('1m',), top_n=2)
        res = EV.evaluate(spec, self.fore, self.rows, self.lo, self.hi, blocks=2)
        calls, inv, unc = res['_calls']
        c2, _, _ = EV.randomized(calls, inv, unc, np.random.default_rng(1))
        self.assertTrue((c2.ts == calls.ts).all())
        self.assertTrue((c2.move == calls.move).all())
        self.assertLess(abs(float((c2.side == calls.side).mean()) - 0.5), 0.12)
        sc = EV.score_calls(c2, None, None, self.lo, self.hi, blocks=2)
        self.assertLess(abs(sc['hit_rate'] - 0.5), 0.12)

    def test_event_set_round_trips_and_lists_events_in_row_order(self):
        es = self.rand['BTC']
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'x.npz')
            ES.save(es, p)
            back = ES.load(p)
        self.assertEqual((back.coin, back.t0, back.n, back.step, back.keys), (es.coin, es.t0, es.n, es.step, es.keys))
        self.assertEqual(back.events_for(es.keys), es.events_for(es.keys))
        ev = es.events_for(es.keys)
        self.assertEqual([r for r, _ in ev], sorted(r for r, _ in ev))
        self.assertEqual(len(ev), len(es.rows))
        self.assertEqual(es.events_for(['nope']), [])

    def test_eligibility_needs_calls_from_both_coins(self):
        res = dict(n_decided=900, n_dec_by_coin={'BTC': 850, 'ETH': 50})
        self.assertFalse(EV.eligible(res))
        res = dict(n_decided=900, n_dec_by_coin={'BTC': 450, 'ETH': 450})
        self.assertTrue(EV.eligible(res))


class Build(unittest.TestCase):
    def test_build_reads_only_up_to_the_scope_end_and_keeps_the_warmup_pad(self):
        class Eng:
            def grid(self, df, end_ms=None):
                n = int((end_ms - guards.WARMUP_START) // MIN)
                return {'t0': guards.WARMUP_START, 'n': n, 'o': np.arange(n, dtype=float) + 1.0, 'rows': len(df)}

            def tf_codes(self, m, k, edges, step, window=None, want_bases=None):
                return [{'name': b} for b in sorted(want_bases)], {}, 0

            def events_at(self, r, lo, hi):
                return [(b, f'{r["name"]}=x') for b in (10, 300_000, 400_000) if lo <= b < hi]
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, '1m.csv')
            with open(p, 'w') as f:
                f.write('ts,o,h,l,c,v\n')
                for t in range(0, 5):
                    f.write(f'{guards.WARMUP_START + t * MIN},1,2,0.5,1.5,3\n')
            es = ES.build('BTC', p, {'price_step': 0.01, 'edges': {}}, ['1m:AAA=x'], 'dev', engine=Eng())
        self.assertEqual(es.n, int((guards.DEV[1] - guards.WARMUP_START) // MIN))
        self.assertEqual(es.lo_row, int((guards.DEV[0] - guards.WARMUP_START) // MIN))
        self.assertTrue(all(r >= es.lo_row - ES.PAD for r in es.rows.tolist()))        # a pre-scope event outside the pad is dropped
        with self.assertRaises(ValueError):
            ES.build('DOGE', p, {}, [], 'dev', engine=Eng())


if __name__ == '__main__':
    unittest.main()
