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

    def test_fade_fn_is_minus_the_sign_of_the_move_from_the_entry_open(self):
        o = np.array([100.00, 100.02, 100.05, 100.05, 100.04, 100.04])
        f = EV.fade_fn(o, 0.01, 2)
        self.assertEqual([f(e) for e in range(8)], [0, 0, -1, -1, 1, 1, 0, 0])       # e<k and e>=n give 0
        self.assertEqual(EV.fade_fn(o, 0.01, 1)(4), 1)
        self.assertEqual(EV.fade_fn(o, 0.01, 1)(1), -1)
        self.assertEqual(EV.fade_fn(o, 0.05, 2)(5), 0)                                # a 0.01 move is under half of a 0.05 step

    def test_baseline_counts_every_decided_minute_and_matches_a_brute_force_loop(self):
        spec = C.Spec(tfs=('1m',), top_n=2)
        lo, hi = self.lo + 86_400_000, self.hi - 86_400_000
        base = EV.baseline(spec, self.rand, lo, hi)
        self.assertEqual(sorted(base), sorted(['up', 'down'] + [f'{m}{k}' for m in ('follow', 'fade') for k in (1, 5, 15, 60)]))
        cnt = {}
        for coin in ('BTC', 'ETH'):
            es = self.rand[coin]
            o = es.o
            for e in range(60, es.n - 16):
                t = es.t0 + e * MIN
                if not lo <= t < hi:
                    continue
                mv = (o[e + 15] - o[e]) / 0.01
                if abs(mv) < 1.5:
                    continue
                add = lambda k, ok: cnt.setdefault(k, [0, 0]).__setitem__(slice(None), [cnt[k][0] + int(ok), cnt[k][1] + 1])
                cnt.setdefault('up', [0, 0]); cnt.setdefault('down', [0, 0])
                add('up', mv > 0); add('down', mv < 0)
                for k in (1, 5, 15, 60):
                    p = np.sign(np.round((o[e] - o[e - k]) / 0.01))
                    if p == 0:
                        continue
                    cnt.setdefault(f'follow{k}', [0, 0]); cnt.setdefault(f'fade{k}', [0, 0])
                    add(f'follow{k}', np.sign(mv) == p); add(f'fade{k}', np.sign(mv) == -p)
        for k, (h, d) in cnt.items():
            self.assertAlmostEqual(base[k], h / d, places=12, msg=k)
        self.assertGreater(cnt['fade15'][1], 3000)
        self.assertAlmostEqual(base['up'] + base['down'], 1.0, places=12)

    def test_a_fade_spec_calls_against_the_last_move_and_is_scored_against_every_minute(self):
        for k in (5, 15):
            spec = C.Spec(tfs=('1m',), top_n=2, side='fade', fade_k=k)
            res = EV.evaluate(spec, self.rand, self.rows, self.lo, self.hi, blocks=2)
            c = res['_calls'][0]
            self.assertGreater(len(c), 300)
            self.assertTrue((c.side == -c.past[k]).all())                              # every call is against the last k minute move
            self.assertTrue((c.past[k] != 0).all())
            self.assertIsNotNone(res['_base'])
            self.assertEqual(res['naive_base'], res['_base'])
            self.assertIn(res['checks'][2]['best_rule'], res['_base'])
            self.assertAlmostEqual(res['checks'][2]['value'], res['hit_rate'] - max(res['_base'].values()), places=9)
        heat = EV.evaluate(C.Spec(tfs=('1m',), top_n=2), self.rand, self.rows, self.lo, self.hi, blocks=2)
        self.assertIsNone(heat['_base'])                                               # a heat spec keeps the same-call comparison

    def test_the_twin_gate_needs_every_twin_file(self):
        from heatloop import gate
        spec = C.Spec(tfs=('1m',), top_n=2)
        twins = {(c, t): self.rand[c] for c in ('BTC', 'ETH') for t in (1, 2, 3)}
        full = gate.twin_gate(spec, twins, self.rows, self.lo, self.hi, 2)
        self.assertTrue(full['complete'])
        short = gate.twin_gate(spec, {k: v for k, v in twins.items() if k != ('ETH', 3)}, self.rows, self.lo, self.hi, 2)
        self.assertFalse(short['complete'])
        self.assertFalse(short['ok'])

    def test_the_random_side_gate_scores_a_fade_spec_against_the_same_base(self):
        from heatloop import gate
        spec = C.Spec(tfs=('1m',), top_n=2, side='fade', fade_k=15)
        res = EV.evaluate(spec, self.rand, self.rows, self.lo, self.hi, blocks=2)
        c, i, u = res['_calls']
        out = gate.random_side(c, i, u, self.lo, self.hi, 2, draws=6, base=res['_base'])
        self.assertEqual(out['draws'], 6)
        self.assertLessEqual(out['max_total'], 10)

    def test_decide_coin_is_what_run_scores_and_a_peeking_side_shows_at_a_cut_on_the_call_minute(self):
        spec = C.Spec(tfs=('1m',), top_n=2, side='fade', fade_k=5, lag=1)
        es = self.rand['BTC']
        d = EV.decide_coin(spec, es, self.rows, 'BTC')
        run = EV.run(C.Spec(tfs=('1m',), top_n=2, side='fade', fade_k=5, lag=1, coins=('BTC',)), self.rand, self.rows)['calls']
        self.assertEqual([c[0] for c in d['calls'] if 60 <= c[0] and c[0] + 16 < es.n], [(int(t) - es.t0) // MIN for t in run.ts])
        e0 = d['calls'][len(d['calls']) // 2][0]                                      # cut so that the file ends on this call's own minute
        n_cut = e0 + 1
        keep = [i for i, r in enumerate(es.rows.tolist()) if r < n_cut]
        trunc = ES.EventSet('BTC', 0, 'dev', es.t0, n_cut, es.lo_row, es.o[:n_cut], es.step, es.keys, [es.rows.tolist()[i] for i in keep],
                            [es.kidx.tolist()[i] for i in keep])
        raw = lambda dd: [(c[0], c[1]) for c in dd['calls'] if c[0] < n_cut]
        self.assertEqual(raw(EV.decide_coin(spec, trunc, self.rows, 'BTC')), raw(d))        # the registered side is the same on the cut file
        self.assertIn((e0, d['calls'][len(d['calls']) // 2][1]), raw(d))
        real = EV.fade_fn
        try:
            EV.fade_fn = lambda o, step, k: (lambda e: 0 if e + 1 >= len(o) else -int(np.sign(np.round((o[e + 1] - o[e - k]) / step))))
            peek_full, peek_cut = EV.decide_coin(spec, es, self.rows, 'BTC'), EV.decide_coin(spec, trunc, self.rows, 'BTC')
        finally:
            EV.fade_fn = real
        self.assertNotEqual(raw(peek_full), raw(peek_cut))                                  # one bar of lookahead is caught by the cut on the call minute

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

    def test_events_of_one_row_come_back_in_key_name_order_like_event_rows(self):
        es = ES.EventSet('BTC', 0, 'dev', 0, 10, 0, np.arange(10.0), 0.01, ['b', 'z', 'a'], [5, 5, 5, 3, 7], [0, 1, 2, 1, 0])
        got = es.events_for(['z', 'b', 'a', 'nope'])
        self.assertEqual(got, sorted(got))
        self.assertEqual(got, [(3, 'z'), (5, 'a'), (5, 'b'), (5, 'z'), (7, 'b')])

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
