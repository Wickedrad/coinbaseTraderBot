"""The hourly-ladder stage: strike selection, the two spot gaps, the clustered standard error, and the failures it must not hide."""
import collections
import contextlib
import io
import math
import os
import unittest
from unittest import mock

from lossreview import daily, ladder, marketbase, paths, spotgap
from lossreview.tests.test_marketbase import NOW, Fake, epoch, iso

DAY = '2026-11-18'
HOUR0 = epoch(DAY, 12, 0)                 # the close of the ladder events of most tests
COINS = ('BTC', 'ETH', 'SOL', 'XRP')


def lmarket(series, day, hh, k, result, strike=100.0, strike_type='greater', open_back=3600):
    close = epoch(day, hh, 0)
    m = {'ticker': '%s-%s%02d-T%d' % (series, day, hh, k), 'close_time': iso(close), 'open_time': iso(close - open_back), 'result': result}
    if strike is not None:
        m['floor_strike'] = strike
    if strike_type is not None:
        m['strike_type'] = strike_type
    return m


def candles_hour(close, quote, drop=None):
    """One 1-minute candle a minute from 10 minutes before the window to the close. QUOTE(close - end) -> (bid, ask) in dollars for the
    candle that ends that many seconds before the close, so a test can tell which minute a quote was read at."""
    out = []
    for k in range(-10, 61):
        end = close - 3600 + 60 * k
        if drop and drop(close - end):
            continue
        bid, ask = quote(close - end)
        out.append({'end_period_ts': end, 'yes_bid': {'close_dollars': '%.2f' % bid}, 'yes_ask': {'close_dollars': '%.2f' % ask}})
    return out


class LFake(Fake):
    """The two public endpoints for ladder markets: QUOTE is (bid, ask), or a function of (market, seconds before the close)."""

    def __init__(self, markets, quote=(0.48, 0.52), page=1000, fail_candles=False, drop=None):
        super().__init__(markets, quote, page, fail_candles)
        self.drop = drop

    def get(self, url, tries=4):
        if '/candlesticks' in url and not self.fail_candles:
            self.calls.append(url)
            ticker = url.split('/markets/')[1].split('/')[0]
            m = next(m for m in self.markets if m['ticker'] == ticker)
            return {'candlesticks': candles_hour(paths.iso_epoch(m['close_time']), self._q(m), self.drop)}
        return super().get(url, tries)

    def _q(self, m):
        if callable(self.quote):
            return lambda left: self.quote(m, left)
        return lambda left: self.quote


def wiggle(s, amp=0.0002):
    return 1 + amp * ((s // 60) % 2)


def flat(base):
    return lambda s: base * wiggle(s)


def ramp(base, per_min, start=None):
    """BASE rising PER_MIN a minute from START (default the start of the hour)."""
    a = HOUR0 - 3600 if start is None else start
    return lambda s: (base + per_min * max(0, s - a) / 60.0) * wiggle(s)


def bumpy(base=100.0, up=0.0015):
    """Flat at BASE except for a rise of UP (a fraction) over minutes 20 to 25 of every hour, held to minute 50 and given back by minute 55."""
    def price(s):
        m = (s % 3600) / 60.0
        f = (m - 20) / 5 if 20 <= m < 25 else 1 if 25 <= m < 50 else 1 - (m - 50) / 5 if 50 <= m < 55 else 0
        return base * (1 + up * f) * wiggle(s)
    return price


def spot_rows(price, day=DAY, days=1):
    t0, t1, _ = marketbase.day_bounds(day, days)
    a = (t0 - ladder.WINDOW - spotgap.VOL_WINDOW - ladder.BACK - 120) // 60 * 60 - 60
    rows = []
    for s in range(a, t1 + 300, 60):
        c = price(s)
        rows.append([s, c, c, c, c, 1.0])
    return rows


CACHES = []


def run(fake, price=None, days=1, day=DAY, check_coverage=False, now=NOW, rows=None, floor=1):
    """Run the stage on the fake Kalshi and a Coinbase spot. The printing floor (MIN_CELL rows) is lowered to FLOOR so a small world fills cells."""
    spots = rows if isinstance(rows, dict) else {c: (rows or spot_rows(price or flat(100.2), day, days)) for c in COINS}
    with mock.patch.object(paths, 'get', fake.get), mock.patch.object(marketbase.time, 'sleep', lambda s: None), \
            mock.patch.object(ladder.time, 'sleep', lambda s: None), mock.patch.object(ladder, 'MIN_CELL', floor), \
            mock.patch.object(paths, 'spot_minutes', lambda coin, a, b, cache: CACHES.append(cache) or spots[coin]):
        return ladder.report('/unused', day, days, now=now, check_coverage=check_coverage, cache='/unused')


def event(series, hh, results, strikes, day=DAY):
    return [lmarket(series, day, hh, i, r, s) for i, (r, s) in enumerate(zip(results, strikes))]


class Selection(unittest.TestCase):
    def sel(self, listed, px=100.2, counts=None):
        sp = spotgap.Spot(spot_rows(flat(px)))
        c = counts if counts is not None else collections.Counter()
        return [(m['ticker'], k) for m, k in ladder.select(listed, sp, c)], c

    def test_the_nearest_strikes_by_log_distance_are_kept(self):
        strikes = [90.0, 95.0, 99.0, 100.0, 101.0, 102.0, 104.0, 110.0]
        listed = event('KXBTCD', 12, ['yes'] * 8, strikes)
        got, _ = self.sel(listed, px=100.2)
        self.assertEqual(sorted(k for _t, k in got), [99.0, 100.0, 101.0, 102.0])   # 99 (1.2%) is nearer than 102 (1.8%) and 104 (3.8%)

    def test_distance_is_in_log_terms(self):
        # spot 100: 99 and 101 are the same distance in dollars, but 101 is nearer in log terms (ln 100/101 < ln 100/99)
        listed = event('KXBTCD', 12, ['yes'] * 3, [99.0, 101.0, 108.0])
        sp = spotgap.Spot([[s, 100.0, 100.0, 100.0, 100.0, 1.0] for s in range(HOUR0 - 3 * 3600, HOUR0 + 600, 60)])
        with mock.patch.object(ladder, 'NEAREST', 1):
            got = [k for _m, k in ladder.select(listed, sp, collections.Counter())]
        self.assertEqual(got, [101.0])

    def test_ties_go_to_the_lower_ticker_whatever_the_listing_order(self):
        listed = event('KXBTCD', 12, ['yes'] * 6, [100.0] * 6)
        got, _ = self.sel(list(reversed(listed)))
        self.assertEqual([t for t, _k in got], [listed[i]['ticker'] for i in range(4)])

    def test_a_stale_spot_at_the_first_offset_drops_the_event(self):
        listed = event('KXBTCD', 12, ['yes'] * 5, [98.0, 99.0, 100.0, 101.0, 102.0])
        first = HOUR0 - 3600 + ladder.OFFSETS[0]
        sp = spotgap.Spot([r for r in spot_rows(flat(100.2)) if r[0] <= first - 60 - 2 * 60])      # the last minute closed 2 minutes before
        c = collections.Counter()
        self.assertEqual(ladder.select(listed, sp, c), [])
        self.assertEqual(c['event_no_spot'], 1)

    def test_each_event_keeps_its_own_nearest(self):
        a = event('KXBTCD', 12, ['yes'] * 5, [98.0, 99.0, 100.0, 101.0, 130.0])
        b = event('KXBTCD', 13, ['yes'] * 5, [70.0, 99.5, 100.5, 101.5, 102.5])
        got, _ = self.sel(a + b)
        self.assertEqual(len(got), 8)
        self.assertNotIn(130.0, [k for _t, k in got])
        self.assertNotIn(70.0, [k for _t, k in got])

    def test_the_choice_uses_the_spot_at_the_first_offset_only(self):
        listed = event('KXBTCD', 12, ['yes'] * 6, [98.0, 99.0, 100.0, 101.0, 102.0, 103.0])
        sp = spotgap.Spot(spot_rows(lambda s: (100.2 if s <= HOUR0 - 3600 + ladder.OFFSETS[0] else 140.0) * wiggle(s)))
        got = [k for _m, k in ladder.select(listed, sp, collections.Counter())]
        self.assertEqual(sorted(got), [99.0, 100.0, 101.0, 102.0])

    def test_what_cannot_be_used_is_counted(self):
        listed = (event('KXBTCD', 12, ['yes', 'no', 'yes', 'no'], [99.0, 100.0, 101.0, 102.0])
                  + [lmarket('KXBTCD', DAY, 12, 8, None), lmarket('KXBTCD', DAY, 12, 9, 'yes', strike=None),
                     lmarket('KXBTCD', DAY, 12, 10, 'yes', strike_type='between'), lmarket('KXBTCD', DAY, 12, 11, 'yes', strike=-5.0)])
        got, c = self.sel(listed)
        self.assertEqual(len(got), 4)
        self.assertEqual((c['no_result'], c['no_strike'], c['odd_strike']), (1, 2, 1))
        self.assertEqual((c['strike_type:greater'], c['strike_type:between']), (6, 1))

    def test_an_event_without_spot_is_dropped_and_counted(self):
        listed = event('KXBTCD', 12, ['yes'] * 5, [98.0, 99.0, 100.0, 101.0, 102.0])
        sp = spotgap.Spot([])
        c = collections.Counter()
        self.assertEqual(ladder.select(listed, sp, c), [])
        self.assertEqual(c['event_no_spot'], 1)


class Rows(unittest.TestCase):
    def world(self, quote, price=None):
        m = lmarket('KXBTCD', DAY, 12, 0, 'yes', 100.0)
        cs = candles_hour(HOUR0, quote)
        return m, cs, spotgap.Spot(spot_rows(price or flat(100.2)))

    def test_rows_are_read_at_the_offsets_with_the_quote_and_the_model(self):
        m, cs, sp = self.world(lambda left: (0.48, 0.52))
        counts = collections.Counter()
        rows = ladder.rows_of(m, 100.0, cs, sp, counts)
        self.assertEqual([r['off'] for r in rows], list(ladder.OFFSETS))
        r = rows[0]
        t = HOUR0 - 3600 + 600
        px, age = sp.last_closed(t)
        want = spotgap.model_p(px, 100.0, sp.sigma(t), (HOUR0 - t + age) / 60.0)
        self.assertAlmostEqual(r['p'], want)
        self.assertEqual((r['bid'], r['ask'], r['yes']), (0.48, 0.52, True))
        self.assertAlmostEqual(r['mid0'], 0.50)
        t0 = t - ladder.BACK
        px0, age0 = sp.last_closed(t0)
        self.assertAlmostEqual(r['p0'], spotgap.model_p(px0, 100.0, sp.sigma(t), (HOUR0 - t0 + age0) / 60.0))
        self.assertEqual(counts['no_prev'], 0)

    def test_the_quote_is_the_one_of_the_offset_not_a_later_one(self):
        m, cs, sp = self.world(lambda left: (0.30, 0.34) if left > 3600 - 700 else (0.60, 0.64))
        rows = ladder.rows_of(m, 100.0, cs, sp, collections.Counter())
        self.assertEqual((rows[0]['bid'], rows[0]['ask']), (0.30, 0.34))
        self.assertEqual((rows[1]['bid'], rows[1]['ask']), (0.60, 0.64))
        self.assertEqual(rows[0]['mid0'], 0.32)

    def test_a_stale_or_missing_quote_makes_no_row_and_is_counted(self):
        m, cs, sp = self.world(lambda left: (0.48, 0.52))
        stale = [c for c in cs if not (HOUR0 - 3600 + 600 - 400 < c['end_period_ts'] <= HOUR0 - 3600 + 600)]
        counts = collections.Counter()
        rows = ladder.rows_of(m, 100.0, stale, sp, counts)
        self.assertEqual([r['off'] for r in rows], [1500, 2400])
        self.assertEqual(counts['no_quote'], 1)

    def test_a_quote_a_few_minutes_old_is_used_up_to_the_ladders_age_limit(self):
        m, cs, sp = self.world(lambda left: (0.48, 0.52))
        t = HOUR0 - 3600 + 600
        old = [c for c in cs if not (t - 150 < c['end_period_ts'] <= t)]           # the last candle ended 180 s before the offset
        counts = collections.Counter()
        rows = ladder.rows_of(m, 100.0, old, sp, counts)
        self.assertEqual([r['off'] for r in rows], [600, 1500, 2400])
        self.assertEqual([r['age'] for r in rows], [180, 0, 0])
        self.assertEqual(counts['no_quote'], 0)
        older = [c for c in cs if not (t - 210 < c['end_period_ts'] <= t)]         # 240 s: too old
        self.assertEqual([r['off'] for r in ladder.rows_of(m, 100.0, older, sp, collections.Counter())], [1500, 2400])

    def test_a_stale_spot_makes_no_row(self):
        m, cs, _ = self.world(lambda left: (0.48, 0.52))
        sp = spotgap.Spot([r for r in spot_rows(flat(100.2)) if r[0] < HOUR0 - 3600 + 400])
        counts = collections.Counter()
        self.assertEqual(ladder.rows_of(m, 100.0, cs, sp, counts), [])
        self.assertEqual(counts['no_spot'], 3)

    def test_minutes_left_run_from_the_spot_minute_used(self):
        m, cs, _ = self.world(lambda left: (0.48, 0.52))
        t = HOUR0 - 3600 + 600
        sp = spotgap.Spot([r for r in spot_rows(flat(100.2)) if r[0] != t - 60])         # the minute that closes at t is missing: age 60
        rows = ladder.rows_of(m, 100.0, cs, sp, collections.Counter())
        px, age = sp.last_closed(t)
        self.assertEqual(age, 60)
        self.assertAlmostEqual(rows[0]['p'], spotgap.model_p(px, 100.0, sp.sigma(t), (HOUR0 - t + 60) / 60.0))

    def test_the_earlier_probability_uses_the_volatility_of_the_later_quote(self):
        m, cs, _ = self.world(lambda left: (0.48, 0.52))
        t = HOUR0 - 3600 + 600
        sp = spotgap.Spot(spot_rows(lambda s: 100.2 * (1 + 0.004 * (t - 240 <= s < t - 180)) * wiggle(s)))      # a spike between the two quotes
        self.assertNotAlmostEqual(sp.sigma(t), sp.sigma(t - ladder.BACK), places=5)
        r = ladder.rows_of(m, 100.0, cs, sp, collections.Counter())[0]
        px0, age0 = sp.last_closed(t - ladder.BACK)
        self.assertAlmostEqual(r['p0'], spotgap.model_p(px0, 100.0, sp.sigma(t), (HOUR0 - (t - ladder.BACK) + age0) / 60.0))

    def test_a_stale_spot_at_the_earlier_quote_leaves_no_adjustment(self):
        m, cs, _ = self.world(lambda left: (0.48, 0.52))
        t0 = HOUR0 - 3600 + 600 - ladder.BACK
        sp = spotgap.Spot([r for r in spot_rows(flat(100.2)) if not (t0 - 210 < r[0] <= t0 - 60)])        # the last minute closed 150 s earlier
        counts = collections.Counter()
        rows = ladder.rows_of(m, 100.0, cs, sp, counts)
        self.assertEqual(len(rows), 3)
        self.assertIsNone(rows[0]['p0'])
        self.assertIsNone(rows[0]['mid0'])
        self.assertEqual(counts['no_prev'], 1)

    def test_a_crossed_quote_is_not_a_row(self):
        m, cs, sp = self.world(lambda left: (0.60, 0.50))
        counts = collections.Counter()
        self.assertEqual(ladder.rows_of(m, 100.0, cs, sp, counts), [])
        self.assertEqual(counts['crossed'], 3)

    def test_without_the_earlier_quote_the_row_stays_but_has_no_adjustment(self):
        m, cs, sp = self.world(lambda left: (0.48, 0.52))
        first = HOUR0 - 3600 + 600
        cs = [c for c in cs if not (first - ladder.BACK - 200 < c['end_period_ts'] <= first - ladder.BACK + 10)]
        counts = collections.Counter()
        rows = ladder.rows_of(m, 100.0, cs, sp, counts)
        self.assertEqual(len(rows), 3)
        self.assertIsNone(rows[0]['p0'])
        self.assertIsNone(rows[0]['mid0'])
        self.assertIsNotNone(rows[1]['p0'])
        self.assertEqual(counts['no_prev'], 1)
        self.assertNotIn('adj', ladder.gaps(rows[0]))

    def test_an_empty_side_still_gives_a_row_for_the_other_side(self):
        m, cs, sp = self.world(lambda left: (0.0, 0.52))
        counts = collections.Counter()
        rows = ladder.rows_of(m, 100.0, cs, sp, counts)
        self.assertEqual(len(rows), 3)
        self.assertEqual(counts['empty_bid'], 3)
        self.assertIsNone(rows[0]['p0'])                 # an empty bid is no earlier two-sided quote

    def test_no_spot_and_no_volatility_are_counted(self):
        m, cs, _ = self.world(lambda left: (0.48, 0.52))
        counts = collections.Counter()
        self.assertEqual(ladder.rows_of(m, 100.0, cs, spotgap.Spot([]), counts), [])
        self.assertEqual(counts['no_spot'], 3)
        few = spotgap.Spot([r for r in spot_rows(flat(100.2)) if r[0] > HOUR0 - 3600 + 300 - 600 * 3])
        counts = collections.Counter()
        with mock.patch.object(spotgap, 'MIN_RETURNS', 10 ** 6):
            self.assertEqual(ladder.rows_of(m, 100.0, cs, few, counts), [])
        self.assertEqual(counts['no_vol'], 3)


class QuoteAge(unittest.TestCase):
    def test_age_is_seconds_since_the_last_candle_at_or_before_t(self):
        cs = [{'end_period_ts': 100}, {'end_period_ts': 160}, {'end_period_ts': 220}]
        self.assertEqual(ladder.quote_age(cs, 160), 0)
        self.assertEqual(ladder.quote_age(cs, 200), 40)
        self.assertEqual(ladder.quote_age(cs, 1000), 780)
        self.assertIsNone(ladder.quote_age(cs, 99))
        self.assertIsNone(ladder.quote_age([], 99))

    def test_a_quote_is_fresh_up_to_the_limit(self):
        self.assertTrue(ladder.is_fresh({'age': 0}))
        self.assertTrue(ladder.is_fresh({'age': ladder.FRESH}))
        self.assertFalse(ladder.is_fresh({'age': ladder.FRESH + 1}))
        self.assertFalse(ladder.is_fresh({'age': None}))


class Gaps(unittest.TestCase):
    def test_the_level_gap_is_model_minus_price_and_adjustment_adds_the_model_move(self):
        r = {'off': 600, 'bid': 0.40, 'ask': 0.44, 'p': 0.60, 'mid0': 0.50, 'p0': 0.52, 'yes': True}
        g = ladder.gaps(r)
        self.assertAlmostEqual(g['lvl'][0], 0.60 - 0.44)
        self.assertAlmostEqual(g['lvl'][1], 0.40 - 0.60)
        q = 0.50 + 0.60 - 0.52
        self.assertAlmostEqual(ladder.forecast(r), q)
        self.assertAlmostEqual(g['adj'][0], q - 0.44)
        self.assertAlmostEqual(g['adj'][1], 0.40 - q)

    def test_the_forecast_stays_inside_zero_and_one(self):
        self.assertEqual(ladder.forecast({'p': 0.9, 'mid0': 0.95, 'p0': 0.1}), 1.0)
        self.assertEqual(ladder.forecast({'p': 0.1, 'mid0': 0.05, 'p0': 0.9}), 0.0)
        self.assertIsNone(ladder.forecast({'p': 0.5, 'mid0': None, 'p0': None}))

    def test_gap_labels_name_the_primary_cells_and_their_cuts(self):
        labs = ladder.gap_labels('adj', 1500, 0.07, 'KXETHD')
        for want in ('adj:+0.05..+0.10', 'adj>=+0.05', 'adj>=+0.05|offset:1500s', 'adj>=+0.05|coin:ETH'):
            self.assertIn(want, labs)
        self.assertNotIn('adj>=+0.10', labs)
        self.assertIn('adj>=+0.10', ladder.gap_labels('adj', 600, 0.12, 'KXBTCD'))
        self.assertEqual(ladder.gap_labels('lvl', 600, -0.2, 'KXBTCD'), ['lvl:<-0.10'])
        self.assertIn('adj>=+0.05', ladder.gap_labels('adj', 600, ladder.PRIMARY, 'KXBTCD'))          # the edge itself is in the cell
        self.assertNotIn('adj>=+0.10', ladder.gap_labels('adj', 600, 2 * ladder.PRIMARY - 1e-9, 'KXBTCD'))
        self.assertIn('adj>=+0.10', ladder.gap_labels('adj', 600, 2 * ladder.PRIMARY, 'KXBTCD'))
        self.assertIn('adj>=+0.05|quote:fresh', ladder.gap_labels('adj', 600, 0.07, 'KXBTCD', True))
        self.assertIn('adj>=+0.05|quote:old', ladder.gap_labels('adj', 600, 0.07, 'KXBTCD', False))
        self.assertNotIn('adj>=+0.05|quote:fresh', ladder.gap_labels('adj', 600, 0.07, 'KXBTCD', False))
        self.assertFalse([l for l in ladder.gap_labels('adj', 600, 0.07, 'KXBTCD') if 'quote:' in l])
        self.assertFalse([l for l in ladder.gap_labels('adj', 600, 0.01, 'KXBTCD', True) if 'quote:' in l])      # only the pre-set cells are cut


class ClusterCell(unittest.TestCase):
    def test_the_standard_error_clusters_rows_by_hour(self):
        c = ladder.Cell()
        # hour A: two rows that both win at .50 (edge +.5 each); hour B: two rows that both lose (edge -.5 each); hour C: one row at 0
        for h, won, n in ((1, True, 2), (2, False, 2)):
            for _ in range(n):
                c.add('2026-11-18', 0.5, won, 'T', h)
        c.add('2026-11-18', 0.5, True, 'T', 3)
        c.add('2026-11-18', 0.5, False, 'T', 3)
        o = c.out()
        self.assertEqual((o['n'], o['hours']), (6, 3))
        # cluster sums: +1.0, -1.0, 0.0 over n = 6, so mean 0; var = sum(S^2) / n^2 * G/(G-1) = 2 / 36 * 1.5
        self.assertAlmostEqual(o['se_c'], round(100 * math.sqrt(2 / 36.0 * 1.5), 1))

    def test_the_standard_error_uses_edge_net_of_price_and_the_mean_edge(self):
        c = ladder.Cell()
        # hour A: two winners at .5 (+1.0); hour B: one winner at .75 (+.25); hour C: one loser at .5 (-.5): n = 4, mean = .75 / 4
        c.add('d', 0.5, True, 'T', 1)
        c.add('d', 0.5, True, 'T', 1)
        c.add('d', 0.75, True, 'T', 2)
        c.add('d', 0.5, False, 'T', 3)
        mean = 0.75 / 4
        resid = [1.0 - mean * 2, 0.25 - mean, -0.5 - mean]
        want = math.sqrt(sum(r * r for r in resid) / 16 * 3 / 2)
        self.assertAlmostEqual(c.out()['se_c'], round(100 * want, 1))

    def test_a_single_hour_has_no_standard_error(self):
        c = ladder.Cell()
        for _ in range(12):
            c.add('2026-11-18', 0.5, True, 'T', 7)
        self.assertIsNone(c.out()['se_c'])

    def test_one_hour_of_rows_is_noisier_than_the_same_rows_over_independent_hours(self):
        same, apart = ladder.Cell(), ladder.Cell()
        for i in range(40):
            won = i < 20
            same.add('2026-11-18', 0.5, won, 'T', i // 20)       # the winners are all in hour 0, the losers in hour 1
            apart.add('2026-11-18', 0.5, won, 'T', i)             # the same rows, each its own hour
        self.assertGreater(same.out()['se_c'], apart.out()['se_c'])

    def test_days_need_day_rows_and_rows_by_day_is_printed(self):
        c = ladder.Cell()
        for i in range(25):
            c.add('2026-11-17', 0.4, True, 'T', i)
        for i in range(5):
            c.add('2026-11-18', 0.4, False, 'T', 100 + i)
        o = c.out()
        self.assertEqual(o['edge_days'], '1/1')
        self.assertEqual(o['rows_by_day'], {'2026-11-17': 25, '2026-11-18': 5})


class Stage(unittest.TestCase):
    def fake(self, series='KXBTCD', n=6, quote=(0.48, 0.52), result='no', hours=(12,), day=DAY):
        ms = []
        for hh in hours:
            ms += event(series, hh, [result] * n, [97.0, 98.0, 99.0, 100.0, 101.0, 102.0, 103.0, 104.0][:n], day)
        return LFake(ms, quote)

    def test_edge_math_and_the_number_of_markets_read(self):
        fk = self.fake(n=6, result='no')
        rep = run(fk)
        yes, no = rep['cells']['yes']['all'], rep['cells']['no']['all']
        self.assertEqual((yes['n'], yes['markets']), (12, 4))                 # 4 kept strikes, 3 quotes each
        self.assertEqual((yes['win_pct'], yes['cost_c'], yes['edge_c']), (0.0, 52.0, -52.0))
        self.assertEqual((no['win_pct'], no['cost_c'], no['edge_c']), (100.0, 52.0, 48.0))
        self.assertAlmostEqual(no['fee_c'], 100 * 0.07 * 0.52 * 0.48, places=2)
        self.assertEqual(rep['markets'], {'KXBTCD': 4})
        self.assertEqual(sum(1 for u in fk.calls if '/candlesticks' in u), 4)     # one request per kept market, none for the rest
        self.assertEqual(rep['candle_requests'], 4)
        self.assertEqual(yes['hours'], 1)
        self.assertIsNone(yes['se_c'])

    def test_a_series_with_no_markets_is_skipped_not_an_error(self):
        rep = run(self.fake(series='KXETHD'))
        self.assertEqual(list(rep['markets']), ['KXETHD'])
        self.assertEqual(rep['survey']['KXBTCD']['markets'], 0)

    def test_the_survey_describes_the_ladder(self):
        ms = event('KXBTCD', 12, ['no'] * 6, [97.0, 98.0, 99.0, 100.0, 101.0, 102.0]) + event('KXBTCD', 13, ['no'] * 4, [97.0, 98.0, 99.0, 100.0])
        rep = run(LFake(ms))
        s = rep['survey']['KXBTCD']
        self.assertEqual((s['markets'], s['events'], s['kept_markets']), (10, 2, 8))
        self.assertEqual(s['strikes_per_event'], {'min': 4, 'median': 5.0, 'max': 6})
        self.assertEqual(s['strike_types'], {'greater': 10})
        self.assertEqual(s['minutes_open'], {'min': 60.0, 'median': 60.0, 'max': 60.0})
        self.assertIn('floor_strike', s['fields'])
        self.assertEqual(rep['candles_per_kept_market']['median'], 71)
        self.assertEqual(rep['events_per_day']['KXBTCD'], {DAY: 2})

    def test_the_level_gap_cell_holds_the_rows_where_spot_says_the_side_is_cheap(self):
        # spot 100.2 over strikes 99 to 102: far above the lowest strikes; the quote is a coin flip, so YES is cheap there
        rep = run(self.fake(n=6, result='yes'))
        cell = rep['cells']['yes'].get('lvl>=+0.05')
        self.assertEqual((cell['n'], cell['markets'], cell['win_pct'], cell['cost_c']), (6, 2, 100.0, 52.0))      # strikes 99 and 100, three quotes each
        self.assertIn('lvl>=+0.05|offset:600s', rep['cells']['yes'])
        self.assertIn('lvl>=+0.05|coin:BTC', rep['cells']['yes'])
        no = rep['cells']['no']['lvl>=+0.05']                                                    # strikes 101 and 102: spot says NO is cheap
        self.assertEqual((no['n'], no['markets'], no['win_pct'], no['cost_c']), (6, 2, 0.0, 52.0))
        self.assertEqual(no['n'], rep['cells']['no']['lvl>=+0.05|quote:fresh']['n'])                  # every quote here is fresh, on both sides
        self.assertEqual(cell['n'], rep['cells']['yes']['lvl>=+0.05|quote:fresh']['n'])
        self.assertNotIn('lvl>=+0.05|quote:old', rep['cells']['no'])

    def test_a_quote_that_lags_a_spot_rise_fills_the_adjustment_cell(self):
        # the spot is flat at 100 until minute 20 of the hour, rises 0.15% by minute 25 and holds; the quote is frozen at 47 / 51
        rep = run(self.bumpy_fake(quote=(0.47, 0.51)), bumpy())
        yes = rep['cells']['yes']
        cell = yes['adj>=+0.05']
        self.assertEqual(cell['win_pct'], 100.0)
        self.assertNotIn('adj>=+0.05|offset:600s', yes)                       # spot had not moved before the first quote
        self.assertEqual(yes['adj>=+0.05|offset:1500s']['n'], 20)           # 5 hours x 4 strikes, read right after the rise
        self.assertLess(yes['adj>=+0.05|offset:2400s']['n'], 10)            # only the model's time decay is left there
        self.assertEqual(cell['hours'], 5)
        self.assertNotIn('adj>=+0.05', rep['cells'].get('no', {}))

    def test_every_cell_is_also_cut_by_the_age_of_the_quote(self):
        # the first quote of every market is two minutes old (its last two candles are missing); the others are fresh
        fk = LFake(self.bumpy_markets(), (0.47, 0.51), drop=lambda left: 3000 <= left <= 3060)
        rep = run(fk, bumpy())
        for side in ('yes', 'no'):
            self.assertEqual((rep['cells'][side]['quote:fresh']['n'], rep['cells'][side]['quote:old']['n']), (40, 20))
        yes = rep['cells']['yes']
        self.assertEqual(yes['adj>=+0.05|quote:fresh']['n'], yes['adj>=+0.05|offset:1500s']['n'] + yes['adj>=+0.05|offset:2400s']['n'])
        self.assertNotIn('adj>=+0.05|quote:old', yes)                                         # the old quotes are all before the rise
        self.assertEqual(yes['lvl>=+0.05|quote:old']['n'] + yes['lvl>=+0.05|quote:fresh']['n'], yes['lvl>=+0.05']['n'])

    def test_a_quote_that_moves_with_spot_leaves_the_adjustment_cell_empty(self):
        price = bumpy()
        sp = spotgap.Spot(spot_rows(price))

        def quote(m, left):
            # the market's mid is the model's own probability at the candle's time: it moved exactly as far as spot did
            close = paths.iso_epoch(m['close_time'])
            t = close - left
            px, age = sp.last_closed(t)
            p = spotgap.model_p(px, m['floor_strike'], sp.sigma(t), (left + age) / 60.0) if px else 0.5
            p = 0.5 if p is None else min(0.97, max(0.03, p))
            return (round(p - 0.02, 2), round(p + 0.02, 2))

        rep = run(LFake(self.bumpy_markets(), quote), price)
        for side in ('yes', 'no'):
            self.assertNotIn('adj>=+0.05', rep['cells'].get(side, {}))

    def bumpy_markets(self):
        ms = []
        for hh in (9, 10, 11, 12, 13):
            ms += event('KXBTCD', hh, ['yes'] * 6, [99.8, 99.9, 100.0, 100.1, 100.2, 100.3])
        return ms

    def bumpy_fake(self, quote):
        return LFake(self.bumpy_markets(), quote)

    def test_brier_and_calibration_match_a_direct_computation(self):
        fk, price = self.bumpy_fake((0.47, 0.51)), bumpy()
        rep = run(fk, price)
        sp = spotgap.Spot(spot_rows(price))
        qs, ps = [], []
        for m, k in ladder.select(fk.markets, sp, collections.Counter()):
            cs = candles_hour(paths.iso_epoch(m['close_time']), lambda left: (0.47, 0.51))
            for r in ladder.rows_of(m, k, cs, sp, collections.Counter()):
                if ladder.forecast(r) is not None:
                    qs.append(ladder.forecast(r))
                    ps.append(r['p'])
        b = rep['brier']['all']
        self.assertEqual(b['n'], len(qs))
        self.assertEqual(b['adj'], round(sum((q - 1) ** 2 for q in qs) / len(qs), 4))
        self.assertEqual(b['model'], round(sum((p - 1) ** 2 for p in ps) / len(ps), 4))
        self.assertNotEqual(b['adj'], b['model'])
        for name, xs in (('adj', qs), ('model', ps)):
            cal = rep['calibration'][name]
            self.assertEqual(sum(v['n'] for v in cal.values()), len(xs))
            self.assertAlmostEqual(sum(v['n'] * v['forecast_pct'] / 100.0 for v in cal.values()) / len(xs), sum(xs) / len(xs), delta=0.003)

    def test_rows_without_the_earlier_quote_stay_in_the_cells_and_out_of_the_scores(self):
        # the quote five minutes before the first offset is missing on every market: its rows have no adjustment gap
        fk = LFake(self.bumpy_markets(), (0.47, 0.51), drop=lambda left: 3300 <= left <= 3500)
        rep = run(fk, bumpy())
        self.assertEqual(rep['cells']['yes']['all']['n'], 60)
        self.assertEqual(rep['brier']['all']['n'], 40)                                        # the 1500 s and 2400 s rows of 20 markets
        self.assertNotIn('offset:600s', rep['brier'])
        self.assertEqual(rep['counts']['BTC']['no_prev'], 20)

    def test_cells_under_the_printing_floor_are_withheld_and_counted(self):
        rep = run(self.fake(n=6, result='yes'), floor=10)
        self.assertIn('all', rep['cells']['yes'])                                             # 12 rows
        self.assertNotIn('lvl>=+0.05', rep['cells']['yes'])                                   # 6 rows
        self.assertGreater(rep['cells_under_floor'], 0)

    def test_candles_are_asked_for_the_hour_and_the_minutes_before_it(self):
        fk = self.fake(n=5, result='no')
        run(fk)
        urls = [u for u in fk.calls if '/candlesticks' in u]
        self.assertTrue(urls)
        self.assertIn('/series/KXBTCD/markets/', urls[0])
        self.assertIn('start_ts=%d&end_ts=%d&period_interval=1' % (HOUR0 - 3600 - ladder.BACK - 60, HOUR0 + 60), urls[0])

    def test_markets_closing_outside_the_days_are_not_read(self):
        ms = event('KXBTCD', 12, ['no'] * 5, [98.0, 99.0, 100.0, 101.0, 102.0])
        ms += event('KXBTCD', 12, ['no'] * 5, [98.0, 99.0, 100.0, 101.0, 102.0], '2026-11-19') + event('KXBTCD', 12, ['no'] * 5, [98.0, 99.0, 100.0, 101.0, 102.0], '2026-11-17')
        rep = run(LFake(ms), days=1)
        self.assertEqual((rep['survey']['KXBTCD']['markets'], rep['survey']['KXBTCD']['events']), (5, 1))
        self.assertEqual(rep['markets'], {'KXBTCD': 4})

    def test_the_spot_minutes_are_cached_in_a_folder(self):
        CACHES.clear()
        run(self.fake(n=5, result='no'))
        self.assertTrue(CACHES)
        self.assertTrue(all(c for c in CACHES))

    def test_a_small_loss_of_rows_to_missing_spot_is_kept_and_counted(self):
        # ten events, and no spot for four minutes before the 25-minute quote of one of them: 4 of 120 rows lost, under the 5% limit
        ms = []
        for hh in range(2, 12):
            ms += event('KXBTCD', hh, ['yes'] * 5, [98.0, 99.0, 100.0, 101.0, 102.0])
        t = epoch(DAY, 5, 0) - 3600 + 1500
        rows = [r for r in spot_rows(flat(100.2)) if not (t - 240 <= r[0] <= t - 60)]
        rep = run(LFake(ms), rows={c: rows for c in COINS})
        self.assertEqual(rep['counts']['BTC']['no_spot'], 4)
        self.assertEqual(rep['rows']['BTC'], {'attempted': 120, 'used': 116})

    def test_a_hole_in_a_day_that_has_not_ended_is_not_checked(self):
        rows = [r for r in spot_rows(flat(100.2)) if r[0] < epoch(DAY, 15, 0)]
        fk = self.fake(n=5, result='no')
        run(fk, rows={c: rows for c in COINS}, now=epoch(DAY, 14, 0))
        with self.assertRaisesRegex(RuntimeError, 'minutes for BTC'):
            run(fk, rows={c: rows for c in COINS})

    def test_brier_and_calibration_cover_the_three_forecasts(self):
        rep = run(self.fake(n=6, result='yes'), ramp(100.0, 0.02))
        b = rep['brier']['all']
        self.assertEqual(sorted(b), ['adj', 'adj_better_days', 'diff_adj', 'diff_model', 'mid', 'model', 'model_better_days', 'n'])
        self.assertEqual(b['n'], 12)
        self.assertEqual(sorted(rep['calibration']), ['adj', 'mid', 'model'])
        self.assertIn('offset:600s', rep['brier'])
        self.assertAlmostEqual(b['mid'], 0.25, places=2)                           # a 50% mid against YES every time

    def test_a_week_of_events_reports_hours_and_a_standard_error(self):
        days = ['2026-11-%02d' % d for d in range(12, 19)]
        ms = []
        for d in days:
            for hh in (10, 11, 12):
                ms += event('KXBTCD', hh, ['yes' if (hh + int(d[-2:])) % 2 else 'no'] * 5, [98.0, 99.0, 100.0, 101.0, 102.0], d)
        rep = run(LFake(ms), days=7)
        c = rep['cells']['yes']['all']
        self.assertEqual(c['hours'], 21)
        self.assertIsNotNone(c['se_c'])
        self.assertEqual(rep['days'], days)
        self.assertEqual(rep['events_per_day']['KXBTCD'], {d: 3 for d in days})
        self.assertEqual(c['rows_by_day'], {d: 36 for d in days})              # 3 events x 4 strikes x 3 quotes


class Failures(unittest.TestCase):
    def test_no_ladder_market_at_all_stops_with_the_survey(self):
        with self.assertRaisesRegex(RuntimeError, 'no settled ladder market.*survey'):
            run(LFake([]))

    def test_a_failed_markets_list_stops_the_run(self):
        class Bad(LFake):
            def get(self, url, tries=4):
                return {'error': 'HTTP 500'}
        with self.assertRaisesRegex(RuntimeError, 'markets list'):
            run(Bad(event('KXBTCD', 12, ['yes'] * 5, [98.0, 99.0, 100.0, 101.0, 102.0])))

    def test_too_many_failed_candle_requests_stop_the_run(self):
        ms = []
        for hh in range(0, 12):
            ms += event('KXBTCD', hh, ['yes'] * 5, [98.0, 99.0, 100.0, 101.0, 102.0])
        with self.assertRaisesRegex(RuntimeError, 'candle requests failed'):
            run(LFake(ms, fail_candles=True))

    def test_a_thin_full_day_stops_the_run_and_a_partial_day_does_not(self):
        fk = LFake(event('KXBTCD', 12, ['yes'] * 5, [98.0, 99.0, 100.0, 101.0, 102.0]))
        with self.assertRaisesRegex(RuntimeError, 'only 1 settled KXBTCD events'):
            run(fk, check_coverage=True)
        run(fk, check_coverage=True, now=epoch(DAY, 18, 0))        # the day has not ended: not checked

    def test_a_full_day_passes_the_coverage_check(self):
        ms = []
        for hh in range(0, 24):
            ms += event('KXBTCD', hh, ['yes'] * 5, [98.0, 99.0, 100.0, 101.0, 102.0])
        rep = run(LFake(ms), check_coverage=True)
        self.assertEqual(rep['events_per_day']['KXBTCD'], {DAY: 24})

    def test_more_kept_markets_than_the_cap_stop_before_any_candle_request(self):
        fk = LFake(event('KXBTCD', 12, ['yes'] * 6, [98.0, 99.0, 100.0, 101.0, 102.0, 103.0]))
        with mock.patch.object(ladder, 'MAX_CHOSEN', 3):
            with self.assertRaisesRegex(RuntimeError, 'too many candle requests'):
                run(fk)
        self.assertFalse([u for u in fk.calls if '/candlesticks' in u])

    def test_a_coin_with_holes_in_its_spot_stops_the_run(self):
        rows = [r for r in spot_rows(flat(100.2)) if (r[0] // 60) % 2 == 0]
        with self.assertRaisesRegex(RuntimeError, 'minutes for BTC'):
            run(LFake(event('KXBTCD', 12, ['yes'] * 5, [98.0, 99.0, 100.0, 101.0, 102.0])), rows={c: rows for c in COINS})

    def test_a_coin_whose_spot_cannot_be_fetched_stops_the_run(self):
        with self.assertRaisesRegex(RuntimeError, 'could not be fetched'):
            run(LFake(event('KXBTCD', 12, ['yes'] * 5, [98.0, 99.0, 100.0, 101.0, 102.0])), rows={c: [] for c in COINS})

    def test_rows_lost_to_missing_spot_stop_the_run_but_missing_quotes_do_not(self):
        out = {'rows': {'BTC': {'attempted': 100, 'used': 50}}, 'counts': {'BTC': {'no_quote': 50}}}
        ladder.check_rows(out)
        out['counts']['BTC'] = {'no_spot': 6}
        with self.assertRaisesRegex(RuntimeError, 'BTC lost 6 of 100'):
            ladder.check_rows(out)
        out['counts']['BTC'] = {'no_vol': 6}
        with self.assertRaisesRegex(RuntimeError, 'BTC lost 6 of 100'):
            ladder.check_rows(out)
        out['counts']['BTC'] = {'no_spot': 3, 'no_vol': 2}
        ladder.check_rows(out)


class Wiring(unittest.TestCase):
    def test_the_stage_is_known_to_daily_and_the_runner_script_and_is_read_only(self):
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        sh = open(os.path.join(root, '.github', 'scripts', 'loss_review_stages.sh')).read()
        yml = open(os.path.join(root, '.github', 'workflows', 'loss-review-stages.yml')).read()
        self.assertIn(' ladder ', [l for l in sh.splitlines() if l.startswith('READONLY=')][0])
        self.assertIn('|ladder|', sh)
        self.assertIn('ladder', yml)
        buf = io.StringIO()
        with mock.patch.object(ladder, 'report', lambda w, day, days=7, **k: {'stage': 'ladder', 'day': day, 'days': days}), \
                contextlib.redirect_stdout(buf):
            with mock.patch('sys.argv', ['daily', 'ladder', '2026-11-18', '--w', '/unused']):
                try:
                    daily.main()
                except SystemExit:
                    pass
        self.assertIn('LOSSLOOP ladder', buf.getvalue())
        self.assertIn('"days": 7', buf.getvalue())          # no --days: the seven days every market stage reads by default


if __name__ == '__main__':
    unittest.main()
