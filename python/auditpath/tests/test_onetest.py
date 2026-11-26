import io
import json
import os
import tempfile
import unittest

from auditpath import onetest as T
from lossreview.fees import taker_fee

CLOSE = 3600          # a 15-minute contract closing at second 3600 (the entry window is 2760 to 3300)
T0 = 2760


def cd(end, bl, bc, ah, ac):
    """A normalized candle: end, YES bid low, YES bid close, YES ask high, YES ask close (dollars)."""
    return (end, bl, bc, ah, ac)


def book(*cs):
    return T.index(list(cs))


def entry(side='yes', t0=T0, close=CLOSE, kind='15m', i='C1', coin='BTC'):
    return {'id': i, 'coin': coin, 'kind': kind, 'close_ts': close, 'side': side, 't0': t0}


# the worked scenario: YES bid .40 / ask .44 at T0 (YES costs 44c, C = 22, level 49c; NO costs 60c, C = 16, level 65c)
SCENE = book(cd(2760, .39, .40, .45, .44),
             cd(2820, .50, .50, .62, .54),
             cd(2880, .70, .70, .75, .75))


class LevelAndFee(unittest.TestCase):
    def test_contracts(self):
        self.assertEqual([T.contracts(p) for p in (10, 44, 50, 60, 90)], [100, 22, 20, 16, 11])
        self.assertEqual(T.contracts(99), 10)

    def test_fee_is_the_shared_one(self):
        for c, p in ((20, 50), (22, 44), (16, 60), (11, 90), (100, 10), (1, 99)):
            self.assertEqual(T.fee_c(c, p), round(taker_fee(c, p / 100.0) * 100))
        self.assertEqual(T.fee_c(20, 50), 35)      # 0.07 x 20 x .25 = 0.35
        self.assertEqual(T.fee_c(22, 44), 38)      # .07 x 22 x .44 x .56 = .3794 rounds up to 38c
        self.assertEqual(T.fee_c(11, 90), 7)       # 0.0693 rounds up to 7c

    def test_level_hand_worked(self):
        # p = 50c, C = 20: need 20 x 50 + 35 + 20 = 1055; b = 54 gives 1080 - 35 = 1045 (short), b = 55 gives 1100 - 35 = 1065
        self.assertEqual(T.level_c(20, 50), 55)
        # p = 44c, C = 22: need 968 + 38 + 22 = 1028; b = 48 gives 1056 - 39 = 1017, b = 49 gives 1078 - 39 = 1039
        self.assertEqual(T.level_c(22, 44), 49)
        # p = 60c, C = 16: need 960 + 27 + 16 = 1003; b = 64 gives 1024 - 26 = 998, b = 65 gives 1040 - 26 = 1014
        self.assertEqual(T.level_c(16, 60), 65)
        # p = 90c, C = 11: need 990 + 7 + 11 = 1008; b = 92 gives 1012 - 6 = 1006, b = 93 gives 1023 - 6 = 1017
        self.assertEqual(T.level_c(11, 90), 93)
        # p = 10c, C = 100: need 1000 + 63 + 100 = 1163; b = 12 gives 1200 - 74 = 1126, b = 13 gives 1300 - 80 = 1220
        self.assertEqual(T.level_c(100, 10), 13)

    def test_no_price_reaches_the_level(self):
        self.assertIsNone(T.level_c(1, 99))        # 99c - 1c fee is 98c, the need is 99 + 1 + 1 = 101c


class OneSide(unittest.TestCase):
    def test_yes_and_no_cost_and_side_bid_low(self):
        y = T.score_side(SCENE, 'yes', T0, CLOSE, '15m', 'yes')
        n = T.score_side(SCENE, 'no', T0, CLOSE, '15m', 'yes')
        self.assertEqual((y['p_c'], y['C'], y['level_c']), (44, 22, 49))
        self.assertEqual((n['p_c'], n['C'], n['level_c']), (60, 16, 65))
        c = SCENE[2820]
        self.assertAlmostEqual(T.side_bid_low(c, 'yes'), .50)
        self.assertAlmostEqual(T.side_bid_low(c, 'no'), .38)     # 1 - YES ask high .62
        self.assertAlmostEqual(T.side_bid_close(c, 'no'), .46)   # 1 - YES ask close .54

    def test_window_on_the_first_candle_after_t0(self):
        y = T.score_side(SCENE, 'yes', T0, CLOSE, '15m', 'yes')
        self.assertTrue(y['window'])
        self.assertEqual(y['minutes'], 1.0)      # the candle ending at T0 + 60 s counts: it starts at T0
        n = T.score_side(SCENE, 'no', T0, CLOSE, '15m', 'yes')
        self.assertFalse(n['window'])             # NO side bid low is .38 then .25, never 65c

    def test_no_window_from_before_t0(self):
        b = book(cd(2700, .90, .90, .95, .95), cd(2760, .39, .40, .45, .44), cd(2820, .45, .46, .50, .50))
        y = T.score_side(b, 'yes', T0, CLOSE, '15m', None)
        self.assertTrue(y['scored'])
        self.assertFalse(y['window'])             # the 90c candle ends at T0 - 60 and the candle ending at T0 does not count either
        b2 = book(cd(2760, .90, .40, .95, .44), cd(2820, .45, .46, .50, .50))
        self.assertFalse(T.score_side(b2, 'yes', T0, CLOSE, '15m', None)['window'])

    def test_deadline_15m_and_hourly(self):
        pre = cd(2760, .39, .40, .45, .44)
        ok = book(pre, cd(3480, .60, .60, .65, .65))      # ends 2 minutes before the close
        late = book(pre, cd(3540, .60, .60, .65, .65))    # ends 1 minute before: too late
        self.assertTrue(T.score_side(ok, 'yes', T0, CLOSE, '15m', None)['window'])
        self.assertFalse(T.score_side(late, 'yes', T0, CLOSE, '15m', None)['window'])
        h0, hc = 3900, 7200
        pre = cd(h0, .39, .40, .45, .44)
        ok = book(pre, cd(6840, .60, .60, .65, .65))      # 6 minutes before the close
        late = book(pre, cd(6900, .60, .60, .65, .65))
        self.assertTrue(T.score_side(ok, 'yes', h0, hc, 'hourly', None)['window'])
        self.assertFalse(T.score_side(late, 'yes', h0, hc, 'hourly', None)['window'])

    def test_not_scored_reasons(self):
        self.assertEqual(T.score_side(None, 'yes', T0, CLOSE, '15m', None)['reason'], 'no candles')
        self.assertEqual(T.score_side(book(cd(2820, .4, .4, .5, .5)), 'yes', T0, CLOSE, '15m', None)['reason'], 'no candle at T0')
        for c, why in ((cd(2760, .5, .55, .6, .55), 'not two-sided'),     # bid = ask
                       (cd(2760, .0, .0, .6, .01), 'not two-sided'),       # an ask of 1c on an empty book
                       (cd(2760, .5, None, .6, .56), 'not two-sided'),
                       (cd(2760, .9, .95, .99, 1.0), 'not two-sided'),     # ask of $1.00
                       (cd(2760, .1, .09, .1, .08), 'not two-sided')):     # bid above ask is crossed
            self.assertEqual(T.score_side(book(c), 'yes', T0, CLOSE, '15m', None)['reason'], why)
        # the band: YES at 92c is out; YES at 90c is in; NO at 9c is out and NO at 10c is in
        self.assertEqual(T.score_side(book(cd(2760, .9, .9, .95, .92)), 'yes', T0, CLOSE, '15m', None)['reason'], 'price out of band')
        self.assertTrue(T.score_side(book(cd(2760, .8, .88, .95, .90)), 'yes', T0, CLOSE, '15m', None)['scored'])
        self.assertEqual(T.score_side(book(cd(2760, .9, .91, .95, .93)), 'no', T0, CLOSE, '15m', None)['reason'], 'price out of band')
        self.assertTrue(T.score_side(book(cd(2760, .8, .90, .95, .93)), 'no', T0, CLOSE, '15m', None)['scored'])

    def test_money_at_plus_one_minute_and_settlement(self):
        y = T.score_side(SCENE, 'yes', T0, CLOSE, '15m', 'yes')
        # sold at the YES bid close .50 after 1 minute: 22 x 50 - fee(22, .50) 39 - (22 x 44 + 38) = 55c over 22 contracts
        self.assertAlmostEqual(y['sold_c'], 55 / 22.0)
        self.assertAlmostEqual(y['held_c'], (2200 - 1006) / 22.0)
        yn = T.score_side(SCENE, 'yes', T0, CLOSE, '15m', 'no')
        self.assertAlmostEqual(yn['held_c'], -1006 / 22.0)
        n = T.score_side(SCENE, 'no', T0, CLOSE, '15m', 'yes')
        # NO sold at 1 - YES ask close .54 = 46c: 16 x 46 - fee(16, .46) 28 - (16 x 60 + 27) = -279c over 16
        self.assertAlmostEqual(n['sold_c'], -279 / 16.0)
        self.assertAlmostEqual(n['held_c'], -987 / 16.0)
        self.assertIsNone(T.score_side(SCENE, 'yes', T0, CLOSE, '15m', None)['held_c'])
        self.assertIsNone(T.score_side(book(cd(2760, .39, .40, .45, .44)), 'yes', T0, CLOSE, '15m', 'yes')['sold_c'])

    def test_missing_minute_between_t0_and_deadline(self):
        # candles at 2820 and 2880 only: the minutes 2940 to 3480 are missing
        self.assertTrue(T.score_side(SCENE, 'yes', T0, CLOSE, '15m', None)['gap'])
        full = [cd(2760, .39, .40, .45, .44)] + [cd(e, .3, .4, .5, .5) for e in range(2820, 3481, 60)]
        self.assertFalse(T.score_side(book(*full), 'yes', T0, CLOSE, '15m', None)['gap'])

    def test_own_fill_price_and_size(self):
        # the lane's own fill: no quote, no band; 44c and 22 contracts give the same level 49c; candles after the fill only
        it = T.score_side(SCENE, 'yes', 2820, CLOSE, '15m', None, price=.44, count=22)
        self.assertEqual((it['p_c'], it['C'], it['level_c']), (44, 22, 49))
        self.assertTrue(it['window'])          # the 2880 candle (bid low .70)
        self.assertEqual(it['minutes'], 1.0)
        self.assertEqual(T.score_side(SCENE, 'yes', 2820, CLOSE, '15m', None, price=.44, count=0)['reason'], 'no fill price or size')


class Controls(unittest.TestCase):
    def test_minute_boundaries(self):
        self.assertEqual(T.entry_minutes(3600, '15m'), list(range(2760, 3301, 60)))
        h = T.entry_minutes(7200, 'hourly')
        self.assertEqual((h[0], h[-1], len(h)), (7200 - 3300, 7200 - 600, 46))

    def test_three_controls_on_one_entry(self):
        b = T.score_entry(entry('yes'), SCENE, 'yes')
        self.assertTrue(b['called']['window'])
        self.assertFalse(b['opp']['window'])
        self.assertEqual(b['opp']['p_c'], 60)
        scored = [i for i in b['mins'] if i['scored']]
        # boundaries with a candle: 2760 (window), 2820 (YES 54c, window on the 70c candle), 2880 (YES 75c, no later candle)
        self.assertEqual([i['window'] for i in scored], [True, True, False])
        self.assertEqual(sum(1 for i in b['mins'] if i['reason'] == 'no candle at T0'), 7)
        a = T.analyse([b], T.week_fn_from(0), hours=24)['secondary']
        self.assertAlmostEqual(a['G_random_side']['gap'], 0.5)             # 1 - (1 + 0) / 2
        self.assertAlmostEqual(a['G_random_side']['control'], 0.5)
        self.assertAlmostEqual(a['same_side_random_minute']['control'], 2 / 3, places=3)
        self.assertAlmostEqual(a['same_side_random_minute']['gap'], 1 / 3, places=3)
        # the usual side of this one-entry count is YES, the called side: the control equals the called entry
        self.assertEqual(a['usual_side']['gap'], 0.0)

    def test_usual_side_is_the_most_called(self):
        bs = [T.score_entry(entry('yes', i='A'), SCENE, 'yes'), T.score_entry(entry('yes', i='B'), SCENE, 'yes'),
              T.score_entry(entry('no', i='C'), SCENE, 'yes')]
        self.assertEqual(T.usual_sides(bs), {('BTC', '15m'): 'yes'})
        a = T.core_stats(bs, T.usual_sides(bs))
        # the NO call (no window) against always YES (window): gap -1 on that entry, 0 on the other two
        self.assertAlmostEqual(a['usual_side']['gap'], -1 / 3, places=3)

    def test_money_rows(self):
        b = T.score_entry(entry('yes'), SCENE, 'yes')
        m = T.money([b], 24)
        self.assertAlmostEqual(m['called']['sold_1m']['cents_per_contract'], 2.5)
        self.assertAlmostEqual(m['opposite']['sold_1m']['cents_per_contract'], -17.4375, places=3)
        self.assertAlmostEqual(m['random_side']['sold_1m']['cents_per_contract'], (2.5 - 17.4375) / 2, places=3)
        # dollars an hour = 2.5c x 22 contracts x 1 entry / 24 hours
        self.assertAlmostEqual(m['called']['sold_1m']['dollars_per_hour'], 0.025 * 22 / 24, places=2)


def fake(i, close, side='yes', called=1, opp=0, coin='BTC', kind='15m', t0=0, minutes=(1,)):
    """A bundle built straight from window flags (1 / 0 / None = not scored)."""
    def it(w):
        if w is None:
            return {'scored': False, 'reason': 'no candle at T0', 'window': None}
        return {'scored': True, 'reason': None, 'window': bool(w), 'level_c': 50, 'p_c': 50, 'C': 20, 'minutes': 1.0, 'gap': False,
                'sold_c': 1.0, 'held_c': 1.0}
    return {'id': i, 'coin': coin, 'kind': kind, 'close_ts': close, 'side': side, 't0': t0,
            'called': it(called), 'opp': it(opp), 'mins': [it(w) for w in minutes]}


class Counting(unittest.TestCase):
    def test_first_scored_entry_per_contract(self):
        bs = [T.score_entry(entry(t0=2700, i='K'), SCENE, 'yes'),       # no candle at 2700: not scored
              T.score_entry(entry(t0=2820, i='K'), SCENE, 'yes'),       # scored
              T.score_entry(entry(t0=2760, i='K'), SCENE, 'yes'),       # scored and earlier: the first
              T.score_entry(entry(t0=2760, i='L'), None, None)]         # no candles at all
        self.assertFalse(bs[0]['called']['scored'])
        p = T.primary_count(bs)
        self.assertEqual(len(p), 1)
        self.assertEqual(p[0]['t0'], 2760)
        a = T.analyse(bs, T.week_fn_from(0), hours=24)
        self.assertEqual((a['primary']['n_entries'], a['secondary']['n_entries']), (1, 4))
        self.assertEqual(a['contracts'], 2)
        self.assertEqual(a['secondary']['not_scored']['called']['not_scored'], {'no candle at T0': 1, 'no candles': 1})

    def test_bootstrap_is_deterministic_and_clustered(self):
        pairs = [(s, float(s % 3 == 0)) for s in range(40) for _ in range(2)]
        a, b = T.slot_boot(pairs), T.slot_boot(pairs)
        self.assertEqual(a, b)
        self.assertAlmostEqual(a[0], 14 / 40.0)      # slots 0, 3, ..., 39 are 14 of 40
        self.assertGreater(a[1], 0)
        self.assertEqual(T.slot_boot([(1, .5), (2, .5), (3, .5)])[1], 0.0)
        self.assertEqual(T.slot_boot([(1, 1.0)]), (1.0, None))
        # entries of one slot move together: the error is larger than with each entry its own slot
        solo = [(k, v) for k, (_, v) in enumerate(pairs)]
        self.assertGreater(a[1], T.slot_boot(solo)[1] * 0.999)

    def test_direction_found_needs_two_standard_errors_on_the_primary(self):
        bs = [fake('c%d' % k, 1000 + 900 * k, side='yes', called=1, opp=0, minutes=(1, 1)) for k in range(30)]
        a = T.analyse(bs, T.week_fn_from(10 ** 12), hours=24)
        self.assertEqual(a['primary']['G_random_side']['gap'], 0.5)
        self.assertEqual(a['verdict']['verdict'], 'direction found')
        self.assertEqual(a['verdict']['G_sign_primary'], 'above random by any amount')

    def test_timing_not_direction(self):
        # called always wins, the opposite side wins as often (G = 0), but the other minutes of the contract lose
        bs = [fake('c%d' % k, 1000 + 900 * k, called=1, opp=1, minutes=(0, 0)) for k in range(30)]
        a = T.analyse(bs, T.week_fn_from(10 ** 12), hours=24)
        self.assertEqual(a['primary']['G_random_side']['gap'], 0.0)
        self.assertEqual(a['verdict']['verdict'], 'timing, not direction')
        self.assertEqual(a['verdict']['G_sign_primary'], 'not above random by any amount')

    def test_mixed_when_counts_disagree(self):
        # the first entry of each contract wins alone; the later ones (secondary only) lose to the opposite side
        bs = []
        for k in range(30):
            bs.append(fake('c%d' % k, 1000 + 900 * k, called=1, opp=0, t0=0))
            for j in range(1, 6):
                bs.append(fake('c%d' % k, 1000 + 900 * k, called=0, opp=1, t0=j))
        a = T.analyse(bs, T.week_fn_from(10 ** 12), hours=24)
        self.assertEqual(a['verdict']['primary'], 'direction found')
        self.assertEqual(a['verdict']['secondary'], 'direction not found')
        self.assertEqual(a['verdict']['verdict'], 'mixed')

    def test_mixed_when_timing_meets_not_found(self):
        # primary: called wins, opposite wins too (G = 0) but the other minutes lose, so timing; the later entries
        # (secondary only) make the other minutes win too, so direction not found. The two words differ: mixed.
        bs = []
        for k in range(30):
            bs.append(fake('c%d' % k, 1000 + 900 * k, called=1, opp=1, t0=0, minutes=(0, 0)))
            for j in range(1, 6):
                bs.append(fake('c%d' % k, 1000 + 900 * k, called=0, opp=0, t0=j, minutes=(1, 1)))
        a = T.analyse(bs, T.week_fn_from(10 ** 12), hours=24)
        self.assertEqual(a['verdict']['primary'], 'timing, not direction')
        self.assertEqual(a['verdict']['secondary'], 'direction not found')
        self.assertEqual(a['verdict']['verdict'], 'mixed')

    def test_small_cells_are_withheld_and_splits_keyed_by_week(self):
        bs = [fake('c%d' % k, 1000 + 900 * k, t0=k * 100) for k in range(12)]
        a = T.analyse(bs, T.week_fn_from(600), hours=24)['secondary']['splits']
        self.assertEqual(set(a['week']), {'week1', 'week2'})
        self.assertEqual(a['week']['week1']['n_called_scored'], 6)
        self.assertIn('withheld', a['week']['week1'])
        self.assertEqual(a['side']['yes']['n_called_scored'], 12)
        self.assertNotIn('withheld', a['side']['yes'])


class Normalizers(unittest.TestCase):
    def test_api_and_history_forms_agree(self):
        api = [
            {'end_period_ts': 2820, 'yes_bid': {'open': 40, 'high': 52, 'low': 39, 'close': 50, 'open_dollars': '0.4000',
                                                'low_dollars': '0.3900', 'close_dollars': '0.5000'},
             'yes_ask': {'open': 44, 'high': 62, 'low': 43, 'close': 54, 'high_dollars': '0.6200', 'close_dollars': '0.5400'}},
            {'end_period_ts': 2760, 'yes_bid': {'low': 39, 'close': 40}, 'yes_ask': {'high': 45, 'close': 44}},   # cents only
            {'end_period_ts': 2760, 'yes_bid': {'low': 39, 'close': 40}, 'yes_ask': {'high': 45, 'close': 44}},   # a duplicate
        ]
        hist = [
            {'ts': 2760000, 'bidL': .39, 'bidC': .40, 'askH': .45, 'askC': .44},
            {'ts': 2820000, 'bidL': .39, 'bidC': .50, 'askH': .62, 'askC': .54},
        ]
        a, h = T.norm_api_candles(api), T.norm_hist_candles(hist)
        self.assertEqual(len(a), 2)
        self.assertEqual([c[0] for c in a], [2760, 2820])
        for x, y in zip(a, h):
            for u, v in zip(x, y):
                self.assertAlmostEqual(u, v)
        # the same market scored from either form gives the same numbers
        ra = T.score_side(T.index(a), 'yes', 2760, CLOSE, '15m', 'yes')
        rh = T.score_side(T.index(h), 'yes', 2760, CLOSE, '15m', 'yes')
        self.assertEqual(ra, rh)
        rn = T.score_side(T.index(a), 'no', 2760, CLOSE, '15m', 'yes')
        self.assertEqual(rn, T.score_side(T.index(h), 'no', 2760, CLOSE, '15m', 'yes'))

    def test_history_prices_stored_in_hundredths_of_a_cent_are_scaled_back(self):
        h = T.norm_hist_candles([{'ts': 60000, 'bidL': .0039, 'bidC': .004, 'askH': .0045, 'askC': .0044}])
        self.assertAlmostEqual(h[0][2], .40)
        self.assertAlmostEqual(h[0][4], .44)

    def test_missing_prices_stay_missing(self):
        a = T.norm_api_candles([{'end_period_ts': 60, 'yes_bid': {}, 'yes_ask': {'high': 50, 'close': 49}}])
        self.assertEqual(a[0][1:3], (None, None))


class PartA(unittest.TestCase):
    def test_entry_from_trip(self):
        r = {'lane': 'heat', 'ticker': 'KXBTC15M-X', 'side': 'yes', 'kind': '15m', 'coin': 'BTC', 'order_t': 2777, 'entry_t': 2800,
             'window_close_t': 3600}
        e, why = T.entry_from_trip(r)
        self.assertEqual((e['t0'], e['close_ts'], why), (2760, 3600, None))
        r2 = dict(r, order_t=None)
        self.assertEqual(T.entry_from_trip(r2)[0]['t0'], 2760)         # entry_t 2800 rounds down to 2760
        r3 = dict(r, window_close_t=None)
        self.assertEqual(T.entry_from_trip(r3)[1], 'no close time')
        self.assertEqual(T.entry_from_trip(r3, 3600)[0]['close_ts'], 3600)
        self.assertEqual(T.entry_from_trip(dict(r, lane='maker'))[1], 'other lane')
        self.assertEqual(T.entry_from_trip(dict(r, coin='DOGE'))[1], 'coin not in the four')
        self.assertEqual(T.entry_from_trip(dict(r, side=None))[1], 'no ticker, side or time')

    def test_end_to_end_on_a_synthetic_cache(self):
        close = T.iso_epoch('2026-11-12T12:00:00')
        t0 = close - 840
        tk = 'KXBTC15M-26NOV121200-00'

        def row(end, bl, bc, ah, ac):
            return {'end_period_ts': end, 'yes_bid': {'low_dollars': '%.4f' % bl, 'close_dollars': '%.4f' % bc},
                    'yes_ask': {'high_dollars': '%.4f' % ah, 'close_dollars': '%.4f' % ac}}
        candles = [row(t0, .39, .40, .45, .44), row(t0 + 60, .50, .50, .62, .54), row(t0 + 120, .70, .70, .75, .75)]
        trip = {'lane': 'heat', 'ticker': tk, 'side': 'yes', 'kind': '15m', 'coin': 'BTC', 'order_t': t0 + 17,
                'window_close_t': close, 'entry_fill_px': .44, 'count_filled': 22, 'pnl': 0.55, 'fidelity_flag': True}
        flagged_off = dict(trip, order_t=t0 + 100, fidelity_flag=False, pnl=-0.20)     # a later entry on the same contract
        with tempfile.TemporaryDirectory() as w, tempfile.TemporaryDirectory() as cache:
            os.makedirs(os.path.join(w, 'days'))
            with open(os.path.join(w, 'days', 'trips-2026-11-12.jsonl'), 'w') as fh:
                fh.write(json.dumps(trip) + '\n' + json.dumps(flagged_off) + '\n' + json.dumps(dict(trip, lane='maker')) + '\n')
            with open(os.path.join(w, 'days', 'trips-2026-11-10.jsonl'), 'w') as fh:
                fh.write(json.dumps(trip) + '\n')                       # before --from: ignored
            with open(os.path.join(cache, 'k-%s.json' % tk), 'w') as fh:
                json.dump({'market': {'ticker': tk, 'result': 'yes', 'close_time': '2026-11-12T12:00:00Z'}, 'candles': candles}, fh)
            res = T.run_trips(w, cache, '2026-11-12', fetch=False)
            self.assertEqual(res['rows']['heat_rows'], 2)
            self.assertEqual(res['rows']['entries'], 2)
            self.assertEqual(res['contracts'], 1)
            self.assertEqual(res['primary']['n_entries'], 1)
            self.assertEqual(res['secondary']['n_entries'], 2)
            self.assertEqual(res['secondary']['n_called_scored'], 2)
            ex = res['extras_a']['secondary']
            self.assertEqual(ex['fill_test_scored'], 2)
            self.assertEqual(ex['fidelity_flagged_kept'], 1)
            self.assertEqual(ex['realized_trips'], 2)
            self.assertAlmostEqual(ex['realized_cents_per_contract'], 100 * 0.35 / 44, places=3)
            out = io.StringIO()
            T.print_blocks(res, out)
            text = out.getvalue()
            self.assertNotIn(tk, text)
            self.assertNotIn(str(t0), text)
            for line in text.splitlines():
                self.assertTrue(line.startswith('AUDITPATH onetest {'))
                self.assertLess(len(line), 3000)
                json.loads(line[len('AUDITPATH onetest '):])
            # a coin outside the four is never fetched or counted as a ticker
            with open(os.path.join(w, 'days', 'trips-2026-11-12.jsonl'), 'a') as fh:
                fh.write(json.dumps(dict(trip, ticker='KXDOGE15M-X', coin='DOGE')) + '\n')
            res1 = T.run_trips(w, cache, '2026-11-12', fetch=False)
            self.assertEqual(res1['rows']['tickers'], 1)
            self.assertEqual(res1['rows']['dropped'], {'coin not in the four': 1})
            self.assertEqual(res1['rows']['fetch_errors'], 0)
            # a ticker with no cache entry is not scored, with its reason
            os.remove(os.path.join(cache, 'k-%s.json' % tk))
            res2 = T.run_trips(w, cache, '2026-11-12', fetch=False)
            self.assertEqual(res2['secondary']['not_scored']['called']['not_scored'], {'no candles': 2})
            self.assertEqual(res2['rows']['tickers_without_candles'], 1)


class TestFractionalCounts(unittest.TestCase):
    def test_extras_a_takes_fractional_and_zero_counts(self):
        """A recorded count under one contract (0.5) must not divide by zero; a zero or missing count is left out."""
        from auditpath import onetest as ot
        item = {'scored': False, 'reason': 'no fill price or size', 'window': None}
        rows = [{'pnl': -0.25, 'count_filled': 0.5}, {'pnl': 1.0, 'count_filled': 10}, {'pnl': 2.0, 'count_filled': 0},
                {'pnl': 3.0}]
        out = ot.extras_a([({}, r, item) for r in rows])
        self.assertEqual(out['realized_trips'], 2)
        self.assertAlmostEqual(out['realized_cents_per_contract'], 100.0 * 0.75 / 10.5, places=3)
        self.assertAlmostEqual(out['realized_cents_per_contract_mean_of_trips'], (-50.0 + 10.0) / 2, places=3)


if __name__ == '__main__':
    unittest.main()
