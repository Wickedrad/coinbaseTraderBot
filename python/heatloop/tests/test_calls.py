import unittest

import numpy as np

from heatloop import calls as C
from heatloop import rubric as R


def row(key, coin='BTC', rank=1, dir_=1, h=15, tf='5m', sA=53.0, sB=53.0, nB=1000, aliases=()):
    return dict(key=key, coin=coin, rank_coin=rank, dir=dir_, h=h, tf=tf, share_A=sA, share_B=sB, n_B=nB, aliases=list(aliases))


ROWS = [
    row('5m:RSI14=very high', rank=1, dir_=-1, aliases=['5m:CMO14=very high']),
    row('1m:ZSCORE20=very low', rank=2, dir_=1),
    row('15m:EMA9=above', rank=3, dir_=1, tf='15m'),
    row('5m:ADX=high', rank=4, dir_=1, sA=51.0),
    row('5m:ETHONLY=x', coin='ETH', rank=1, dir_=1),
    row('5m:H60=x', rank=1, dir_=1, h=60),
]


class Admit(unittest.TestCase):
    def test_filters_coin_horizon_bars_and_shares_then_ranks(self):
        sp = C.Spec(tfs=('1m', '5m'), top_n=10)
        got = [r['key'] for r in C.admit(ROWS, sp, 'BTC')]
        self.assertEqual(got, ['5m:RSI14=very high', '1m:ZSCORE20=very low', '5m:ADX=high'])
        self.assertEqual([r['key'] for r in C.admit(ROWS, sp, 'ETH')], ['5m:ETHONLY=x'])
        self.assertEqual([r['key'] for r in C.admit(ROWS, C.Spec(min_share_A=52.0), 'BTC')][-1], '1m:ZSCORE20=very low')
        self.assertEqual(len(C.admit(ROWS, C.Spec(top_n=2), 'BTC')), 2)
        self.assertEqual(len(C.admit(ROWS, C.Spec(min_n_B=5000), 'BTC')), 0)
        self.assertEqual([r['key'] for r in C.admit(ROWS, C.Spec(horizon=60), 'BTC')], ['5m:H60=x'])

    def test_aliases_map_to_their_row(self):
        idx = C.key_index(C.admit(ROWS, C.Spec(), 'BTC'))
        self.assertIs(idx['5m:CMO14=very high'], idx['5m:RSI14=very high'])


class Decide(unittest.TestCase):
    def setUp(self):
        self.adm = C.admit(ROWS, C.Spec(), 'BTC')

    def test_hottest_wins_and_unknown_keys_are_ignored(self):
        ev = [(100, '1m:ZSCORE20=very low'), (100, '5m:RSI14=very high'), (100, '9m:NOPE=x')]
        self.assertEqual(C.decide(ev, self.adm, C.Spec())['calls'], [(100, -1, '5m:RSI14=very high', None)])

    def test_an_alias_event_counts_as_its_row(self):
        self.assertEqual(C.decide([(50, '5m:CMO14=very high')], self.adm, C.Spec())['calls'][0][1:3], (-1, '5m:RSI14=very high'))

    def test_lockout_is_fifteen_minutes_from_the_call(self):
        ev = [(100, '1m:ZSCORE20=very low'), (114, '1m:ZSCORE20=very low'), (115, '1m:ZSCORE20=very low')]
        self.assertEqual([c[0] for c in C.decide(ev, self.adm, C.Spec())['calls']], [100, 115])

    def test_lag_moves_the_entry_and_the_lockout(self):
        ev = [(100, '1m:ZSCORE20=very low'), (110, '1m:ZSCORE20=very low')]
        self.assertEqual([c[0] for c in C.decide(ev, self.adm, C.Spec(lag=2))['calls']], [102])
        ev = [(100, '1m:ZSCORE20=very low'), (114, '1m:ZSCORE20=very low')]          # 114 + 2 = 116 is inside the lockout that ends at 117
        self.assertEqual([c[0] for c in C.decide(ev, self.adm, C.Spec(lag=2))['calls']], [102])

    def test_vote_needs_the_margin_and_a_side(self):
        ev = [(10, '1m:ZSCORE20=very low'), (10, '5m:ADX=high'), (10, '5m:RSI14=very high')]       # +1 +1 -1
        self.assertEqual(C.decide(ev, self.adm, C.Spec(combiner='vote', vote_k=3, margin=1))['calls'][0][1], 1)
        self.assertEqual(C.decide(ev, self.adm, C.Spec(combiner='vote', vote_k=3, margin=2))['calls'], [])
        self.assertEqual(C.decide(ev[:1] + ev[2:], self.adm, C.Spec(combiner='vote', vote_k=3, margin=1))['calls'], [])   # +1 -1 ties

    def test_unknown_combiner_raises(self):
        with self.assertRaises(ValueError):
            C.decide([], self.adm, C.Spec(combiner='avg'))

    def test_a_call_never_depends_on_later_events(self):
        rng = np.random.default_rng(3)
        keys = [r['key'] for r in self.adm]
        ev = sorted((int(rng.integers(0, 3000)), keys[int(rng.integers(0, len(keys)))]) for _ in range(400))
        full = C.decide(ev, self.adm, C.Spec())['calls']
        for cut in (500, 1500, 2500):
            part = C.decide([e for e in ev if e[0] <= cut], self.adm, C.Spec())['calls']
            self.assertEqual(part, [c for c in full if c[0] <= cut])

    def test_spec_hash_changes_with_any_field(self):
        base = C.spec_hash(C.Spec())
        self.assertEqual(base, C.spec_hash(C.Spec()))
        for kw in ({'top_n': 9}, {'tfs': ('5m',)}, {'lag': 1}, {'combiner': 'vote'}, {'lockout': 20}, {'min_share_A': 51.0}):
            self.assertNotEqual(base, C.spec_hash(C.Spec(**kw)), kw)


class Outcomes(unittest.TestCase):
    def test_moves_late_moves_and_past_signs(self):
        o = np.arange(0.0, 2000.0) * 0.5              # a straight ramp: 0.5 per minute, step 0.01 -> 50 steps a minute
        calls = [(200, 1, 'k'), (1990, 1, 'k'), (30, 1, 'k')]
        out = C.outcomes('BTC', calls, o, 0.01, horizon=15, t0=0)
        self.assertEqual(out['ts'].tolist(), [200 * 60_000])                       # e=30 has no 60 minutes of past; e=1990 reaches past the end
        self.assertAlmostEqual(out['move'][0], 15 * 50)
        self.assertAlmostEqual(out['move_late'][0], 15 * 50)
        self.assertEqual({k: v.tolist() for k, v in out['past'].items()}, {1: [1], 5: [1], 15: [1], 60: [1]})

    def test_rows_hi_drops_calls_that_would_read_past_the_scope(self):
        o = np.arange(0.0, 2000.0)
        out = C.outcomes('ETH', [(500, 1, 'k'), (900, -1, 'k')], o, 1.0, horizon=15, rows_hi=700)
        self.assertEqual(out['ts'].tolist(), [500 * 60_000])

    def test_to_calls_joins_coins_in_time_order(self):
        o = np.cumsum(np.random.default_rng(1).normal(size=3000))
        a = C.outcomes('BTC', [(300, 1, 'k'), (900, -1, 'k')], o, 0.01)
        b = C.outcomes('ETH', [(600, 1, 'k')], o, 0.01)
        c = C.to_calls([a, b])
        self.assertEqual(c.ts.tolist(), [300 * 60_000, 600 * 60_000, 900 * 60_000])
        self.assertEqual(c.coin.tolist(), ['BTC', 'ETH', 'BTC'])
        self.assertIsInstance(c, R.Calls)
        self.assertEqual(len(C.to_calls([C.outcomes('BTC', [], o, 0.01)])), 0)


POOL = [
    row('5m:RSI14=low', rank=10, dir_=1, tf='5m'),                    # confirms UP, another family
    row('5m:MACDh5/35/5=down', rank=11, dir_=-1, tf='5m'),            # opposes UP, another family
    row('5m:ZSCORE50=low', rank=12, dir_=-1, tf='5m'),                # opposes UP but the SAME family as the base row
    row('5m:ZSCORE50=high', rank=13, dir_=1, tf='5m'),                # agrees with UP but the SAME family: not independent
]
BASE = [row('1m:ZSCORE20=very low', rank=1, dir_=1)]
UP, DOWN_OTHER, DOWN_SAME, UP_SAME = '5m:RSI14=low', '5m:MACDh5/35/5=down', '5m:ZSCORE50=low', '5m:ZSCORE50=high'


class Family(unittest.TestCase):
    def test_parameters_are_stripped_and_different_indicators_stay_different(self):
        f = C.family
        self.assertEqual(f('5m:RSI7=low'), f('1m:RSI14=very high'))
        self.assertEqual(f('1m:C-EMA9=above'), f('15m:C-EMA21=below'))
        self.assertEqual(f('5m:MACDh5/35/5=down'), 'MACDh')
        self.assertEqual(f('1m:PERCENTB20/2=very high'), 'PERCENTB')
        self.assertEqual(f('1m:PVI sign=above 0'), 'PVI')
        self.assertNotEqual(f('1m:AROONup14=very high'), f('1m:AROONdn14=very high'))


class TaLayer(unittest.TestCase):
    def run_ta(self, ev, **kw):
        return C.decide(ev, BASE, C.Spec(**kw), pool=POOL)

    def test_precedes_labels_calls_and_never_drops_them(self):
        ev = [(100, '1m:ZSCORE20=very low'), (95, UP)]
        self.assertEqual(self.run_ta(ev, ta_confirm='precedes', ta_conf_k=15)['calls'][0][3], True)
        ev = [(100, '1m:ZSCORE20=very low'), (80, UP)]                                   # 20 minutes back: outside k=15
        r = self.run_ta(ev, ta_confirm='precedes', ta_conf_k=15)['calls']
        self.assertEqual((len(r), r[0][3]), (1, False))
        ev = [(100, '1m:ZSCORE20=very low'), (101, UP)]                                  # a confirmer AFTER the call cannot label it
        self.assertEqual(self.run_ta(ev, ta_confirm='precedes', ta_conf_k=15)['calls'][0][3], False)
        ev = [(100, '1m:ZSCORE20=very low'), (100, UP)]                                  # the same minute is known at the call
        self.assertEqual(self.run_ta(ev, ta_confirm='precedes', ta_conf_k=15)['calls'][0][3], True)
        ev = [(100, '1m:ZSCORE20=very low'), (95, UP_SAME)]                              # the same family does not confirm itself
        self.assertEqual(self.run_ta(ev, ta_confirm='precedes', ta_conf_k=15)['calls'][0][3], False)
        ev = [(100, '1m:ZSCORE20=very low'), (95, DOWN_OTHER)]                           # an opposing reading is not a confirmer
        self.assertEqual(self.run_ta(ev, ta_confirm='precedes', ta_conf_k=15)['calls'][0][3], False)

    def test_invalidation_uses_only_what_is_known_at_the_call(self):
        base = (100, '1m:ZSCORE20=very low')
        r = self.run_ta([base, (95, DOWN_OTHER)], ta_inv_k=10)
        self.assertEqual((r['calls'], r['inv']), ([], [(100, 1, '1m:ZSCORE20=very low')]))
        r = self.run_ta([base, (85, DOWN_OTHER)], ta_inv_k=10)                           # too old
        self.assertEqual((len(r['calls']), r['inv']), (1, []))
        r = self.run_ta([base, (105, DOWN_OTHER)], ta_inv_k=10)                          # later than the call: no effect, ever
        self.assertEqual((len(r['calls']), r['inv']), (1, []))
        r = self.run_ta([base, (95, DOWN_SAME)], ta_inv_k=10)                            # same family: no effect
        self.assertEqual((len(r['calls']), r['inv']), (1, []))
        r = self.run_ta([base, (95, UP)], ta_inv_k=10)                                   # agreeing reading: no effect
        self.assertEqual((len(r['calls']), r['inv']), (1, []))

    def test_invalidated_calls_obey_their_own_lockout_and_do_not_start_the_made_lockout(self):
        ev = [(100, '1m:ZSCORE20=very low'), (96, DOWN_OTHER), (110, '1m:ZSCORE20=very low'), (140, '1m:ZSCORE20=very low')]
        r = self.run_ta(ev, ta_inv_k=15)
        self.assertEqual([c[0] for c in r['inv']], [100])                                # 110 is inside the invalidated window
        self.assertEqual([c[0] for c in r['calls']], [140])                              # 110 saw the 96 reading (14 back) and was dropped too

    def test_a_dropped_call_does_not_block_the_next_made_call(self):
        ev = [(100, '1m:ZSCORE20=very low'), (96, DOWN_OTHER), (106, '1m:ZSCORE20=very low')]
        r = self.run_ta(ev, ta_inv_k=5)                                                  # 100 is dropped; 106 sees no opposing reading
        self.assertEqual(([c[0] for c in r['calls']], [c[0] for c in r['inv']]), ([106], [100]))

    def test_follows_waits_for_the_confirmer_and_scores_the_lapsed_calls(self):
        ev = [(100, '1m:ZSCORE20=very low'), (106, UP)]
        r = self.run_ta(ev, ta_confirm='follows', ta_conf_k=10)
        self.assertEqual(r['calls'], [(106, 1, '1m:ZSCORE20=very low', True)])
        self.assertEqual([c[0] for c in r['unconf']], [100])
        r = self.run_ta([(100, '1m:ZSCORE20=very low'), (111, UP)], ta_confirm='follows', ta_conf_k=10)
        self.assertEqual((r['calls'], [c[0] for c in r['unconf']]), ([], [100]))        # too late: the base call lapses
        r = self.run_ta([(100, '1m:ZSCORE20=very low'), (95, UP)], ta_confirm='follows', ta_conf_k=10)
        self.assertEqual(r['calls'], [])                                                 # a confirmer BEFORE the base is "precedes", not follows
        r = self.run_ta([(100, '1m:ZSCORE20=very low'), (106, DOWN_OTHER)], ta_confirm='follows', ta_conf_k=10)
        self.assertEqual(r['calls'], [])                                                 # opposing reading is no confirmation

    def test_follows_with_lag_moves_both_entries(self):
        r = self.run_ta([(100, '1m:ZSCORE20=very low'), (106, UP)], ta_confirm='follows', ta_conf_k=10, lag=1)
        self.assertEqual(([c[0] for c in r['calls']], [c[0] for c in r['unconf']]), ([107], [101]))

    def test_nothing_is_decided_from_later_events_with_the_ta_layer_on(self):
        rng = np.random.default_rng(5)
        keys = ['1m:ZSCORE20=very low', UP, DOWN_OTHER, DOWN_SAME]
        ev = sorted((int(rng.integers(0, 3000)), keys[int(rng.integers(0, 4))]) for _ in range(500))
        for kw in ({'ta_confirm': 'precedes', 'ta_inv_k': 10}, {'ta_confirm': 'follows', 'ta_conf_k': 10, 'ta_inv_k': 5}, {'ta_inv_k': 15, 'lag': 2}):
            full = self.run_ta(ev, **kw)
            for cut in (600, 1700, 2600):
                part = self.run_ta([e for e in ev if e[0] <= cut], **kw)
                for name in ('calls', 'inv', 'unconf'):
                    self.assertEqual(part[name], [c for c in full[name] if c[0] <= cut], (kw, cut, name))

    def test_unknown_confirm_mode_raises(self):
        with self.assertRaises(ValueError):
            self.run_ta([], ta_confirm='later')

    def test_confirm_flags_reach_the_rubric_arrays(self):
        o = np.cumsum(np.random.default_rng(2).normal(size=3000))
        a = C.outcomes('BTC', [(300, 1, 'k', True), (900, -1, 'k', False)], o, 0.01)
        self.assertEqual(a['conf'].tolist(), [True, False])
        self.assertIsNone(C.outcomes('BTC', [(300, 1, 'k')], o, 0.01)['conf'])
        b = C.outcomes('ETH', [(600, 1, 'k')], o, 0.01)
        self.assertIsNone(C.to_calls([a, b]).conf)                                       # one part without flags: no split
        self.assertEqual(C.to_calls([a, C.outcomes('ETH', [(600, 1, 'k', True)], o, 0.01)]).conf.tolist(), [True, True, False])


if __name__ == '__main__':
    unittest.main()
