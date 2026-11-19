"""The spot-gap stage: the two model probabilities, the spot lookups, the Brier and gap tables, and the failures it must not hide."""
import collections
import contextlib
import io
import math
import os
import tempfile
import unittest
from unittest import mock

from lossreview import daily, marketbase, paths, spotgap
from lossreview.tests.test_marketbase import NOW, Fake, candles_for, market

DAY = '2026-11-18'
PREV = '2026-11-17'
COINS = ('BTC', 'ETH', 'SOL', 'XRP')


def spot_rows(price, day=DAY, days=1, skip=None):
    """Coinbase-shaped 1-minute rows [start, low, high, open, close, volume] covering the stage's whole read of DAYS days ending DAY."""
    t0, t1, _ = marketbase.day_bounds(day, days)
    a = (t0 - marketbase.WINDOW - spotgap.VOL_WINDOW - 120) // 60 * 60 - 60
    rows = []
    for s in range(a, t1 + 300, 60):
        if skip and skip(s):
            continue
        c = price(s)
        rows.append([s, c, c, c, c, 1.0])
    return rows


def wiggle(s, amp=0.0002):
    """+-amp alternating 1-minute log returns: sigma is amp."""
    return 1 + amp * ((s // 60) % 2)


def saw(base):
    """Flat at BASE, up to the wiggle: far above a strike of 100 when BASE is 100.2, but not moving since any window opened."""
    return lambda s: base * wiggle(s)


def UP(s):
    """100.2 and rising 0.03 a minute through each UTC day: above the strike of 100 and up since every window opened."""
    return (100.2 + 0.03 * ((s // 60) % 1440)) * wiggle(s)


def DOWN(s):
    """99.8 and falling 0.02 a minute through each UTC day: below the strike and down since every window opened."""
    return (99.8 - 0.02 * ((s // 60) % 1440)) * wiggle(s)


def FALLING_ABOVE(s):
    """Far above the strike (130 against 100) and falling 0.02 a minute through each UTC day."""
    return (130.0 - 0.02 * ((s // 60) % 1440)) * wiggle(s)


def mk(series, day, k, result, strike=100.0, strike_type='greater_or_equal'):
    m = market(series, day, k, result)
    if strike is not None:
        m['floor_strike'] = strike
    if strike_type is not None:
        m['strike_type'] = strike_type
    return m


def run(fake, rows, days=1, day=DAY, check_coverage=False, now=NOW):
    """Run the stage on the fake Kalshi and a Coinbase spot (a price function, rows for every coin, or {coin: rows})."""
    if callable(rows):
        rows = spot_rows(rows, day, days)
    spots = rows if isinstance(rows, dict) else {c: rows for c in COINS}
    with mock.patch.object(paths, 'get', fake.get), mock.patch.object(marketbase.time, 'sleep', lambda s: None), \
            mock.patch.object(paths, 'spot_minutes', lambda coin, a, b, cache: spots[coin]):
        return spotgap.report('/unused', day, days, now=now, check_coverage=check_coverage, cache='/unused')


def lenient():
    """Read the counts of a run that lost rows: the loss check off."""
    return mock.patch.object(spotgap, 'MAX_LOST_SHARE', 1.0)


QUOTE = (0.48, 0.52)


class Model(unittest.TestCase):
    def test_phi_and_model_p(self):
        self.assertAlmostEqual(spotgap.phi(0.0), 0.5)
        self.assertAlmostEqual(spotgap.model_p(100.0, 100.0, 0.001, 5), 0.5)
        up, down = spotgap.model_p(100.1, 100.0, 0.001, 5), spotgap.model_p(99.9, 100.0, 0.001, 5)
        self.assertGreater(up, 0.5)
        self.assertLess(down, 0.5)
        self.assertAlmostEqual(up + down, 1.0, places=3)
        self.assertGreater(spotgap.model_p(100.1, 100.0, 0.001, 4), spotgap.model_p(100.1, 100.0, 0.001, 12))
        self.assertAlmostEqual(spotgap.model_p(100.1, 100.0, 0.001, 4), spotgap.phi(math.log(1.001) / (0.001 * 2)), places=9)

    def test_model_p_is_none_when_an_input_is_missing_or_unusable(self):
        for args in ((None, 100.0, 0.001, 5), (100.0, None, 0.001, 5), (100.0, 100.0, None, 5), (100.0, 100.0, 0.0, 5),
                     (100.0, 100.0, 0.001, 0), (100.0, 0.0, 0.001, 5), (0.0, 100.0, 0.001, 5)):
            self.assertIsNone(spotgap.model_p(*args))

    def test_last_closed_is_the_minute_that_closed_by_the_time(self):
        sp = spotgap.Spot([[0, 1, 1, 1, 10.0, 1], [60, 1, 1, 1, 11.0, 1], [120, 1, 1, 1, 12.0, 1]])
        self.assertEqual(sp.last_closed(120), (11.0, 0))        # the minute that started at 60 closes at 120
        self.assertEqual(sp.last_closed(119), (10.0, 59))
        self.assertEqual(sp.last_closed(1000), (12.0, 820))
        self.assertEqual(sp.last_closed(59), (None, None))
        self.assertEqual(sp.count_between(0, 120), 2)
        self.assertEqual(sp.count_between(60, 1000), 2)

    def test_sigma_is_the_root_mean_square_return_and_a_gap_counts_as_its_minutes(self):
        r = 0.001
        rows = [[60 * k, 1, 1, 1, 100.0 * math.exp(r * k), 1] for k in range(60)]
        sp = spotgap.Spot(rows)
        with mock.patch.object(spotgap, 'MIN_RETURNS', 10):
            self.assertAlmostEqual(sp.sigma(60 * 60), r, places=9)
            self.assertIsNone(spotgap.Spot(rows[:5]).sigma(60 * 60))         # under the floor of returns
            # drop minutes 20-22: the return across the gap is 4r over 4 minutes, so it counts as 4r / 2 = 2r
            gapped = [x for x in rows if not 20 <= x[0] // 60 <= 22]
            sg = spotgap.Spot(gapped).sigma(60 * 60)
            n = len(gapped) - 1
            self.assertAlmostEqual(sg, math.sqrt(((n - 1) * r * r + (4 * r / 2) ** 2) / n), places=9)

    def test_sigma_uses_only_the_hour_before_and_none_after(self):
        old = [[60 * k, 1, 1, 1, 100.0 * (1 + 0.5 * (k % 2)), 1] for k in range(100)]          # wild, but more than an hour old
        calm = [[6000 + 60 * k, 1, 1, 1, 100.0 + 0.001 * k, 1] for k in range(60)]
        after = [[6000 + 60 * (60 + k), 1, 1, 1, 100.0 * (1 + 0.5 * (k % 2)), 1] for k in range(40)]   # after t: must not count
        t = 6000 + 60 * 60
        with mock.patch.object(spotgap, 'MIN_RETURNS', 10):
            s = spotgap.Spot(old + calm + after).sigma(t)
        self.assertLess(s, 1e-4)

    def test_a_tie_on_a_day_is_not_a_day_a_model_was_better(self):
        sc = spotgap.Score()
        for _ in range(spotgap.DAY_ROWS):
            sc.add('d', 0.5, 0.5, 0.5, True)
        self.assertEqual((sc.out()['model_better_days'], sc.out()['model_open_better_days']), ('0/1', '0/1'))
        for _ in range(spotgap.DAY_ROWS):
            sc.add('e', 0.9, 0.9, 0.5, True)
        self.assertEqual((sc.out()['model_better_days'], sc.out()['model_open_better_days']), ('1/2', '1/2'))
        for _ in range(spotgap.DAY_ROWS - 1):
            sc.add('f', 0.9, 0.9, 0.5, True)                         # one row short of the floor: not a day
        self.assertEqual(sc.out()['model_better_days'], '1/2')

    def test_gap_buckets_and_labels(self):
        self.assertEqual(spotgap.gap_bucket(-0.2), '<-0.10')
        self.assertEqual(spotgap.gap_bucket(-0.10), '-0.10..-0.05')
        self.assertEqual(spotgap.gap_bucket(-0.01), '-0.05..+0.00')
        self.assertEqual(spotgap.gap_bucket(0.0), '+0.00..+0.05')
        self.assertEqual(spotgap.gap_bucket(0.0499), '+0.00..+0.05')
        self.assertEqual(spotgap.gap_bucket(0.05), '+0.05..+0.10')
        self.assertEqual(spotgap.gap_bucket(0.10), '>=+0.10')
        self.assertEqual(spotgap.labels(420, 0.049, 'KXBTC15M'), ['all', 'gap:+0.00..+0.05'])
        self.assertEqual(spotgap.labels(420, 0.05, 'KXETH15M'),
                         ['all', 'gap:+0.05..+0.10', 'gap>=+0.05', 'gap>=+0.05|offset:420s', 'gap>=+0.05|coin:ETH'])
        self.assertIn('gap>=+0.10', spotgap.labels(180, 0.12, 'KXBTC15M'))

    def test_each_quote_is_modelled_from_the_strike_and_from_the_open_with_the_minutes_left_in_its_window(self):
        m = mk('KXBTC15M', DAY, 0, 'yes')
        close = paths.iso_epoch(m['close_time'])
        sp = spotgap.Spot(spot_rows(UP))
        rows = spotgap.rows_of(m, candles_for(close, 0.48, 0.52), sp, collections.Counter())
        self.assertEqual([r['off'] for r in rows], [180, 420, 660])
        open_px = sp.last_closed(close - marketbase.WINDOW)[0]
        for r, left in zip(rows, (12.0, 8.0, 4.0)):
            t = close - marketbase.WINDOW + r['off']
            px = sp.last_closed(t)[0]
            self.assertAlmostEqual(r['p'], spotgap.model_p(px, 100.0, sp.sigma(t), left), places=12)
            self.assertAlmostEqual(r['p_open'], spotgap.model_p(px, open_px, sp.sigma(t), left), places=12)
        self.assertLess(rows[0]['p_open'], rows[2]['p_open'])      # the same move since the open is worth more with less time left
        self.assertNotAlmostEqual(rows[0]['p'], rows[0]['p_open'], places=3)

    def test_a_stale_spot_minute_lengthens_the_horizon_by_its_age(self):
        m = mk('KXBTC15M', DAY, 0, 'yes')
        close = paths.iso_epoch(m['close_time'])
        t = close - marketbase.WINDOW + 420
        sp = spotgap.Spot([r for r in spot_rows(UP) if r[0] != t - 60])        # the minute that closed at t is missing
        px, age = sp.last_closed(t)
        self.assertEqual(age, 60)
        m['floor_strike'] = px * 0.9997                                          # 3 bps under the spot: p is not close to one
        rows = spotgap.rows_of(m, candles_for(close, 0.48, 0.52), sp, collections.Counter())
        self.assertAlmostEqual(rows[1]['p'], spotgap.model_p(px, m['floor_strike'], sp.sigma(t), 9.0), places=12)
        self.assertNotAlmostEqual(rows[1]['p'], spotgap.model_p(px, m['floor_strike'], sp.sigma(t), 8.0), places=3)

    def test_a_stale_spot_at_the_open_leaves_no_row(self):
        m = mk('KXBTC15M', DAY, 0, 'yes')
        close = paths.iso_epoch(m['close_time'])
        o = close - marketbase.WINDOW
        sp = spotgap.Spot([r for r in spot_rows(UP) if r[0] not in (o - 60, o - 120)])      # the last minute closed by the open is 120 s old
        counts = collections.Counter()
        self.assertEqual(spotgap.rows_of(m, candles_for(close, 0.48, 0.52), sp, counts), [])
        self.assertEqual(counts['no_open_spot'], 3)


class Stage(unittest.TestCase):
    def test_a_spot_above_the_strike_and_up_since_the_open_makes_yes_cheap_and_the_gap_cell_wins(self):
        ms = [mk('KXBTC15M', DAY, k, 'yes') for k in range(10)]
        rep = run(Fake(ms, quote=QUOTE), UP)
        yes = rep['cells']['yes']
        self.assertEqual(rep['markets']['KXBTC15M'], 10)
        self.assertEqual((yes['all']['n'], yes['all']['markets']), (30, 10))
        c = yes['gap>=+0.05']
        self.assertEqual((c['n'], c['markets'], c['win_pct'], c['cost_c'], c['edge_c']), (30, 10, 100.0, 52.0, 48.0))
        self.assertEqual((c['edge_days'], c['rows_by_day']), ('1/1', {DAY: 30}))
        self.assertEqual(yes['gap>=+0.05|coin:BTC']['n'], 30)
        self.assertEqual(yes['gap>=+0.05|offset:180s']['n'], 10)
        self.assertEqual(yes['gap>=+0.10']['n'], 30)
        no = rep['cells']['no']                    # NO costs one minus the bid, .52, and loses
        self.assertNotIn('gap>=+0.05', no)
        self.assertEqual((no['gap:<-0.10']['n'], no['gap:<-0.10']['win_pct'], no['gap:<-0.10']['cost_c'], no['gap:<-0.10']['edge_c']), (30, 0.0, 52.0, -52.0))

    def test_a_side_is_cheap_only_when_both_models_say_so(self):
        # far above the strike (model says YES, p about 1) but falling since the window opened (model_open well under a half): neither side is cheap
        rep = run(Fake([mk('KXBTC15M', DAY, k, 'yes') for k in range(10)], quote=QUOTE), FALLING_ABOVE)
        self.assertNotIn('gap>=+0.05', rep['cells']['yes'])
        self.assertNotIn('gap>=+0.05', rep['cells']['no'])
        self.assertEqual(rep['cells']['yes']['all']['n'], 30)

    def test_the_gap_takes_the_less_favourable_probability_of_each_side(self):
        row = {'bid': 0.48, 'ask': 0.52}
        for p, po in ((1.0, 0.5), (0.5, 1.0)):                 # one model says YES hard, the other is on the fence
            yes, no = spotgap.gaps(dict(row, p=p, p_open=po))
            self.assertAlmostEqual(yes, 0.5 - 0.52)
            self.assertAlmostEqual(no, 0.48 - 1.0)
        yes, no = spotgap.gaps(dict(row, p=0.9, p_open=0.8))      # both say YES: the lower one counts
        self.assertAlmostEqual(yes, 0.8 - 0.52)
        self.assertAlmostEqual(no, 0.48 - 0.9)
        yes, no = spotgap.gaps(dict(row, p=0.1, p_open=0.2))      # both say NO: the higher p (worse for NO) counts
        self.assertAlmostEqual(yes, 0.1 - 0.52)
        self.assertAlmostEqual(no, 0.48 - 0.2)

    def test_the_gap_of_each_side_is_taken_against_its_own_price(self):
        # spot below the strike and falling: NO (bid .48, cost .52) has gap bid - max(p), about +0.48; YES about -0.5
        rep = run(Fake([mk('KXBTC15M', DAY, k, 'no') for k in range(10)], quote=QUOTE), DOWN)
        c = rep['cells']['no']['gap>=+0.05']
        self.assertEqual((c['n'], c['win_pct'], c['cost_c'], c['edge_c']), (30, 100.0, 52.0, 48.0))
        self.assertNotIn('gap>=+0.05', rep['cells']['yes'])

    def test_brier_scores_the_two_models_against_the_mid(self):
        right = run(Fake([mk('KXBTC15M', DAY, k, 'yes') for k in range(10)], quote=QUOTE), UP)['brier']
        self.assertEqual(right['all']['n'], 30)
        self.assertAlmostEqual(right['all']['mid'], 0.25, places=4)
        self.assertLess(right['all']['model'], 0.001)
        self.assertLess(right['all']['model_open'], 0.25)
        self.assertLess(right['all']['diff'], -0.2)
        self.assertLess(right['all']['diff_open'], 0)
        self.assertEqual((right['all']['model_better_days'], right['all']['model_open_better_days']), ('1/1', '1/1'))
        self.assertEqual(right['offset:420s']['n'], 10)
        wrong = run(Fake([mk('KXBTC15M', DAY, k, 'no') for k in range(10)], quote=QUOTE), UP)['brier']
        self.assertGreater(wrong['all']['diff'], 0.7)
        self.assertEqual((wrong['all']['model_better_days'], wrong['all']['model_open_better_days']), ('0/1', '0/1'))

    def test_brier_counts_by_day_the_days_the_model_was_better(self):
        ms = [mk('KXBTC15M', PREV, k, 'yes') for k in range(8)] + [mk('KXBTC15M', DAY, k, 'no') for k in range(8)]
        rep = run(Fake(ms, quote=QUOTE), UP, days=2)
        self.assertEqual(rep['brier']['all']['model_better_days'], '1/2')

    def test_a_day_with_under_day_rows_is_not_counted_in_brier_or_in_the_cells(self):
        ms = [mk('KXBTC15M', DAY, 0, 'yes')] + [mk('KXBTC15M', PREV, k, 'no') for k in range(8)]     # 3 rows on DAY, 24 the day before
        rep = run(Fake(ms, quote=QUOTE), UP, days=2)
        self.assertEqual(rep['brier']['all']['model_better_days'], '0/1')
        few = run(Fake([mk('KXBTC15M', DAY, k, 'yes') for k in range(4)], quote=QUOTE), UP)['cells']['yes']['gap>=+0.05']     # 12 rows
        self.assertEqual((few['n'], few['edge_days'], few['net_days'], few['rows_by_day']), (12, '0/0', '0/0', {DAY: 12}))

    def test_a_one_sided_quote_makes_a_row_for_its_buyable_side_only_and_no_mid(self):
        rep = run(Fake([mk('KXBTC15M', DAY, k, 'yes') for k in range(10)], quote=(0.0, 0.52)), UP)      # bid 0.00: empty
        self.assertEqual(rep['cells']['yes']['all']['n'], 30)
        self.assertNotIn('no', rep['cells'])
        self.assertEqual(rep['brier'], {})
        self.assertEqual(rep['counts']['BTC']['empty_bid'], 30)
        self.assertEqual(rep['rows']['BTC'], {'attempted': 30, 'used': 30})

    def test_calibration_bins_and_floor(self):
        rep = run(Fake([mk('KXBTC15M', DAY, k, 'yes') for k in range(10)], quote=QUOTE), UP)
        cal = rep['calibration']
        self.assertEqual(cal['model']['0.9-1.0']['n'], 30)
        self.assertEqual(cal['model']['0.9-1.0']['yes_pct'], 100.0)
        self.assertGreater(cal['model']['0.9-1.0']['forecast_pct'], 99.0)
        self.assertTrue(0 < sum(b['n'] for b in cal['model_open'].values()) <= 30)      # bins under the floor are left out
        self.assertEqual(cal['mid']['0.5-0.6'], {'n': 30, 'forecast_pct': 50.0, 'yes_pct': 100.0})
        small = run(Fake([mk('KXBTC15M', DAY, k, 'yes') for k in range(2)], quote=QUOTE), UP)       # 6 rows
        self.assertEqual((small['calibration'], small['cells'], small['brier']['all']['n']), ({}, {}, 6))
        self.assertGreater(small['cells_under_floor'], 0)

    def test_markets_that_cannot_be_modelled_are_counted_per_coin_and_stop_the_run(self):
        ms = [mk('KXBTC15M', DAY, 0, 'yes', strike=None), mk('KXBTC15M', DAY, 1, 'yes', strike_type='less'), mk('KXBTC15M', DAY, 2, 'yes'),
              mk('KXBTC15M', DAY, 3, '', strike=100.0)]
        with self.assertRaises(RuntimeError) as cm:
            run(Fake(ms, quote=QUOTE), UP)
        self.assertIn('BTC lost 6 of 9', str(cm.exception))
        with lenient():
            rep = run(Fake(ms, quote=QUOTE), UP)
        c = rep['counts']['BTC']
        self.assertEqual((c['no_strike'], c['odd_strike'], c['no_result'], c['strike_type:greater_or_equal']), (1, 1, 1, 2))
        self.assertEqual(rep['rows']['BTC'], {'attempted': 9, 'used': 3})
        self.assertEqual(rep['markets']['KXBTC15M'], 4)
        self.assertEqual(rep['brier']['all']['n'], 3)                     # only market 2 made rows

    def test_a_lost_row_is_attributed_to_its_own_coin(self):
        ms = [mk('KXBTC15M', DAY, k, 'yes') for k in range(10)] + [mk('KXXRP15M', DAY, k, 'yes') for k in range(10)]
        spots = {c: spot_rows(UP) for c in COINS}
        spots['XRP'] = spot_rows(lambda s: 0.5)                               # constant: no sigma, so no row
        with self.assertRaises(RuntimeError) as cm:
            run(Fake(ms, quote=QUOTE), spots)
        self.assertIn('XRP lost 30 of 30', str(cm.exception))
        with lenient():
            rep = run(Fake(ms, quote=QUOTE), spots)
        self.assertEqual(rep['counts']['XRP']['no_vol'], 30)
        self.assertNotIn('no_vol', rep['counts']['BTC'])
        self.assertEqual((rep['rows']['BTC'], rep['rows']['XRP']), ({'attempted': 30, 'used': 30}, {'attempted': 30, 'used': 0}))

    def test_a_crossed_quote_is_counted_but_is_not_a_lost_row(self):
        rep = run(Fake([mk('KXBTC15M', DAY, k, 'yes') for k in range(4)], quote=(0.60, 0.40)), UP)
        self.assertEqual(rep['counts']['BTC']['crossed'], 12)
        self.assertEqual(rep['rows']['BTC'], {'attempted': 12, 'used': 0})

    def test_a_stretch_with_no_spot_minutes_is_counted_as_no_spot(self):
        ms = [mk('KXBTC15M', DAY, k, 'yes') for k in range(4)]
        t0 = marketbase.day_bounds(DAY, 1)[0]
        gone = spot_rows(UP, skip=lambda s: t0 + 11 * 3600 + 1800 <= s < t0 + 13 * 3600)     # no minutes from 11:30 to 13:00
        with lenient():
            self.assertEqual(run(Fake(ms, quote=QUOTE), gone)['counts']['BTC']['no_spot'], 12)

    def test_a_spot_minute_older_than_the_limit_is_not_used(self):
        ms = [mk('KXBTC15M', DAY, k, 'yes') for k in range(4)]
        # only every third minute present: the last closed minute is 0, 60 or 120 s old, one quote of each market of each age
        rows = spot_rows(UP, skip=lambda s: (s // 60) % 3 != 0)
        with mock.patch.object(spotgap, 'MIN_DAY_SPOT_SHARE', 0.3), mock.patch.object(spotgap, 'MIN_RETURNS', 10), lenient():
            rep = run(Fake(ms, quote=QUOTE), rows)
        self.assertEqual(rep['counts']['BTC']['no_spot'], 4)

    def test_basis_is_coinbase_at_the_open_against_the_strike(self):
        ms = [mk('KXBTC15M', DAY, k, 'yes') for k in range(4)] + [mk('KXETH15M', DAY, k, 'yes', strike=50.0) for k in range(4)]
        spots = {c: spot_rows(lambda s: 100.2) for c in COINS}            # constant spot: sigma is zero, so no model row, but a basis
        spots['ETH'] = spot_rows(lambda s: 50.0)
        with lenient():
            rep = run(Fake(ms, quote=QUOTE), spots)
        self.assertEqual((rep['counts']['BTC']['no_vol'], rep['counts']['ETH']['no_vol']), (12, 12))
        self.assertEqual(rep['basis_bps']['BTC'], {'n': 4, 'median': round(1e4 * math.log(100.2 / 100.0), 2), 'sd': 0.0})
        self.assertEqual(rep['basis_bps']['ETH'], {'n': 4, 'median': 0.0, 'sd': 0.0})
        self.assertNotIn('SOL', rep['basis_bps'])

    def test_series_use_their_own_coins_spot(self):
        ms = [mk('KXBTC15M', DAY, k, 'yes') for k in range(10)] + [mk('KXETH15M', DAY, k, 'no') for k in range(10)]
        spots = {c: spot_rows(UP) for c in COINS}
        spots['ETH'] = spot_rows(DOWN)                                   # ETH below its strike and falling: NO is the model's side
        rep = run(Fake(ms, quote=QUOTE), spots)
        self.assertEqual(rep['cells']['yes']['gap>=+0.05']['markets'], 10)
        self.assertEqual(rep['cells']['no']['gap>=+0.05']['markets'], 10)
        self.assertEqual(rep['cells']['yes']['gap>=+0.05']['win_pct'], 100.0)
        self.assertEqual(rep['cells']['no']['gap>=+0.05']['win_pct'], 100.0)
        self.assertEqual(rep['cells']['yes']['gap>=+0.05|coin:BTC']['n'], 30)
        self.assertEqual(rep['cells']['no']['gap>=+0.05|coin:ETH']['n'], 30)
        self.assertNotIn('gap>=+0.05|coin:ETH', rep['cells']['yes'])

    def test_check_rows_ignores_crossed_quotes_and_stops_on_other_losses(self):
        ok = {'rows': {'BTC': {'attempted': 100, 'used': 90}}, 'counts': {'BTC': {'crossed': 10}}}
        spotgap.check_rows(ok)
        bad = {'rows': {'BTC': {'attempted': 100, 'used': 90}}, 'counts': {'BTC': {'crossed': 4, 'no_spot': 6}}}
        with self.assertRaises(RuntimeError):
            spotgap.check_rows(bad)
        spotgap.check_rows({'rows': {'BTC': {'attempted': 100, 'used': 95}}, 'counts': {'BTC': {'no_spot': 5}}})       # exactly the share: kept


class Loading(unittest.TestCase):
    def test_a_coin_with_no_spot_stops_the_run(self):
        spots = {c: spot_rows(UP) for c in COINS}
        spots['SOL'] = []
        with self.assertRaises(RuntimeError) as cm:
            run(Fake([mk('KXBTC15M', DAY, k, 'yes') for k in range(4)]), spots)
        self.assertIn('SOL', str(cm.exception))
        self.assertIn('could not be fetched', str(cm.exception))

    def test_a_coin_with_holes_in_a_full_day_stops_the_run(self):
        spots = {c: spot_rows(UP) for c in COINS}
        spots['XRP'] = spot_rows(UP, skip=lambda s: (s // 60) % 3 != 0)       # a third of the minutes
        with self.assertRaises(RuntimeError) as cm:
            run(Fake([mk('KXBTC15M', DAY, k, 'yes') for k in range(4)]), spots)
        self.assertIn('XRP', str(cm.exception))
        self.assertIn('holes', str(cm.exception))

    def test_one_whole_missing_day_of_one_coin_stops_the_run_even_when_the_total_looks_fine(self):
        t0, t1, labs = marketbase.day_bounds(DAY, 7)
        spots = {c: spot_rows(UP, days=7) for c in COINS}
        spots['ETH'] = spot_rows(UP, days=7, skip=lambda s: t0 + 2 * 86400 <= s < t0 + 3 * 86400)      # 14% of the minutes, one day
        with self.assertRaises(RuntimeError) as cm:
            run(Fake([mk('KXBTC15M', DAY, k, 'yes') for k in range(4)]), spots, days=7)
        self.assertIn('ETH', str(cm.exception))
        self.assertIn(labs[2], str(cm.exception))

    def test_a_day_that_has_not_ended_is_not_checked_for_spot(self):
        t0, t1, _ = marketbase.day_bounds(DAY, 2)
        spots = {c: spot_rows(UP, days=2, skip=lambda s: s >= t0 + 86400 + 3600) for c in COINS}   # the second day has an hour of minutes
        rep = run(Fake([mk('KXBTC15M', PREV, k, 'yes') for k in range(8)]), spots, days=2, now=t0 + 86400 + 7200)
        self.assertEqual(rep['partial_days'], [DAY])

    def test_the_stage_asks_for_the_hour_before_the_first_window_and_a_little_after_the_last(self):
        seen = []

        def spot_minutes(coin, a, b, cache):
            seen.append((coin, a, b))
            return spot_rows(UP)
        fake = Fake([mk('KXBTC15M', DAY, k, 'yes') for k in range(4)])
        with mock.patch.object(paths, 'get', fake.get), mock.patch.object(marketbase.time, 'sleep', lambda s: None), \
                mock.patch.object(paths, 'spot_minutes', spot_minutes):
            spotgap.report('/unused', DAY, 1, now=NOW, check_coverage=False, cache='/unused')
        t0, t1, _ = marketbase.day_bounds(DAY, 1)
        self.assertEqual([c for c, _, _ in seen], list(COINS))
        self.assertLessEqual(seen[0][1], t0 - marketbase.WINDOW - spotgap.VOL_WINDOW)
        self.assertGreaterEqual(seen[0][2], t1)


class Wiring(unittest.TestCase):
    def test_the_stage_runs_from_daily_and_prints_a_lossloop_line(self):
        ms = [mk(s, DAY, k, 'yes') for s in marketbase.SERIES for k in range(10)]
        fake = Fake(ms, quote=QUOTE)
        buf = io.StringIO()
        with tempfile.TemporaryDirectory() as w, mock.patch.object(paths, 'get', fake.get), \
                mock.patch.object(marketbase.time, 'sleep', lambda s: None), \
                mock.patch.object(paths, 'spot_minutes', lambda coin, a, b, cache: spot_rows(UP, days=1)), \
                mock.patch.object(marketbase, 'EXPECTED_PER_DAY', 1), contextlib.redirect_stdout(buf):
            rc = daily.main(['spotgap', DAY, '--w', w, '--days', '1'])
        self.assertEqual(rc or 0, 0)
        self.assertIn('LOSSLOOP spotgap {', buf.getvalue())

    def test_the_script_treats_the_stage_as_read_only(self):
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, '..', '..', '..', '.github', 'scripts', 'loss_review_stages.sh')) as fh:
            text = fh.read()
        line = next(l for l in text.splitlines() if l.startswith('READONLY='))
        self.assertIn(' spotgap ', line)
        self.assertIn('|spotgap|', text)


if __name__ == '__main__':
    unittest.main()
