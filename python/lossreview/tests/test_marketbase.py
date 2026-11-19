"""The market-wide calibration stage: the quote rows, the edge arithmetic, the day counts, and the failures it must not hide."""
import datetime
import os
import unittest
from unittest import mock

from lossreview import marketbase, paths


def iso(t):
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def epoch(day, hh=12, mm=0):
    return int(datetime.datetime.strptime('%s %02d:%02d' % (day, hh, mm), '%Y-%m-%d %H:%M').replace(tzinfo=datetime.timezone.utc).timestamp())


def candles_for(close, bid, ask):
    """One 1-minute candle per minute of the window and a little after (dollars). BID and ASK are numbers (one constant quote)
    or functions of the candle's number k (its end is close - 900 + 60 k), so a test can tell which minute a quote was read at."""
    b = bid if callable(bid) else (lambda k: bid)
    a = ask if callable(ask) else (lambda k: ask)
    return [{'end_period_ts': close - 900 + 60 * k, 'yes_bid': {'close_dollars': '%.2f' % b(k)}, 'yes_ask': {'close_dollars': '%.2f' % a(k)}}
            for k in range(0, 17)]


class Fake:
    """The two public endpoints: a markets list (paged by a cursor) and one candlestick request per market."""

    def __init__(self, markets, quote=(0.38, 0.42), page=1000, fail_candles=False):
        self.markets, self.quote, self.page, self.fail_candles = markets, quote, page, fail_candles
        self.calls = []

    def get(self, url, tries=4):
        self.calls.append(url)
        if '/candlesticks' in url:
            if self.fail_candles:
                return {'error': 'HTTP 500'}
            ticker = url.split('/markets/')[1].split('/')[0]
            m = next(m for m in self.markets if m['ticker'] == ticker)
            return {'candlesticks': candles_for(paths.iso_epoch(m['close_time']), *self.quote)}
        series = url.split('series_ticker=')[1].split('&')[0]
        rows = [m for m in self.markets if m['ticker'].startswith(series + '-')]
        start = int(url.split('cursor=')[1]) if 'cursor=' in url else 0
        chunk = rows[start:start + self.page]
        more = start + self.page < len(rows)
        return {'markets': chunk, 'cursor': str(start + self.page) if more else ''}


def market(series, day, k, result, hh=12, mm=None):
    close = epoch(day, hh, 15 * (k % 4) if mm is None else mm)
    return {'ticker': '%s-%s-%d' % (series, day, k), 'close_time': iso(close), 'result': result}


NOW = epoch('2030-01-01')


def run(fake, day='2026-11-18', days=7, check_coverage=False, now=NOW):
    with mock.patch.object(paths, 'get', fake.get), mock.patch.object(marketbase.time, 'sleep', lambda s: None):
        return marketbase.report('/unused', day, days, now=now, check_coverage=check_coverage)


class Marketbase(unittest.TestCase):
    def test_edge_math_of_one_quote(self):
        # bid .38 / ask .42, every market settles NO: YES costs .42 and loses, NO costs .62 and wins
        ms = [market('KXBTC15M', '2026-11-18', k, 'no') for k in range(10)]
        rep = run(Fake(ms))
        yes, no = rep['cells']['yes']['all'], rep['cells']['no']['all']
        self.assertEqual((yes['n'], yes['markets']), (30, 10))
        self.assertEqual((yes['win_pct'], yes['cost_c'], yes['edge_c']), (0.0, 42.0, -42.0))
        self.assertEqual((no['win_pct'], no['cost_c'], no['edge_c']), (100.0, 62.0, 38.0))
        self.assertAlmostEqual(yes['fee_c'], 100 * 0.07 * 0.42 * 0.58, places=2)
        self.assertAlmostEqual(no['net_c'], 38.0 - 100 * 0.07 * 0.62 * 0.38, places=1)

    def test_day_counts_follow_the_sign_of_each_days_edge(self):
        ms = [market('KXBTC15M', '2026-11-16', k, 'yes') for k in range(4)] + [market('KXBTC15M', '2026-11-17', k, 'no') for k in range(4)] \
            + [market('KXBTC15M', '2026-11-18', k, 'no') for k in range(4)]
        yes = run(Fake(ms))['cells']['yes']['all']
        self.assertEqual(yes['edge_days'], '1/3')       # YES wins on one day only
        self.assertEqual(run(Fake(ms))['cells']['no']['all']['edge_days'], '2/3')

    def test_price_bands_and_offsets_and_series_are_cells(self):
        ms = [market('KXBTC15M', '2026-11-18', k, 'no') for k in range(5)] + [market('KXETH15M', '2026-11-18', k, 'yes') for k in range(5)]
        cells = run(Fake(ms))['cells']['yes']
        self.assertIn('band:0.35-0.5', cells)           # the ask .42
        self.assertIn('offset:420s', cells)
        self.assertIn('series:KXETH15M', cells)
        self.assertIn('mid(0.2-0.8)', cells)
        self.assertEqual(cells['series:KXETH15M']['win_pct'], 100.0)

    def test_a_cell_under_the_floor_is_not_printed(self):
        rep = run(Fake([market('KXBTC15M', '2026-11-18', k, 'no') for k in range(2)]))      # 6 rows a side
        self.assertEqual(rep['cells'], {})
        self.assertEqual(rep['markets']['KXBTC15M'], 2)

    def test_a_market_without_a_yes_or_no_result_is_left_out(self):
        ms = [market('KXBTC15M', '2026-11-18', k, 'no') for k in range(10)] + [market('KXBTC15M', '2026-11-18', 10 + k, '') for k in range(5)]
        self.assertEqual(run(Fake(ms))['cells']['yes']['all']['markets'], 10)

    def test_quote_is_the_last_candle_closed_by_the_time(self):
        cs = [{'end_period_ts': 100, 'yes_bid': {'close_dollars': '0.10'}, 'yes_ask': {'close_dollars': '0.20'}},
              {'end_period_ts': 160, 'yes_bid': {'close_dollars': '0.30'}, 'yes_ask': {'close_dollars': '0.40'}},
              {'end_period_ts': 220, 'yes_bid': {'close_dollars': '0.50'}, 'yes_ask': {'close_dollars': '0.60'}}]
        self.assertEqual(marketbase.quote_at(cs, 160), (0.30, 0.40))
        self.assertEqual(marketbase.quote_at(cs, 219), (0.30, 0.40))
        self.assertEqual(marketbase.quote_at(cs, 99), (None, None))

    def test_a_crossed_or_missing_quote_makes_no_row(self):
        m = market('KXBTC15M', '2026-11-18', 0, 'yes')
        close = paths.iso_epoch(m['close_time'])
        self.assertEqual(marketbase.rows_of(m, candles_for(close, 0.60, 0.40)), [])
        self.assertEqual(marketbase.rows_of(m, []), [])

    def test_the_markets_list_is_paged_and_the_window_is_the_seven_days(self):
        ms = [market('KXBTC15M', '2026-11-18', k, 'no', hh=1 + k % 20) for k in range(12)]
        fake = Fake(ms, page=5)
        run(fake)
        lists = [u for u in fake.calls if '/markets?' in u and 'KXBTC15M' in u]
        self.assertEqual(len(lists), 3)                  # 12 markets, 5 a page
        self.assertIn('min_close_ts=%d' % (epoch('2026-11-12', 0, 0) - 1), lists[0])       # a second wider each way: the bounds may be exclusive
        self.assertIn('max_close_ts=%d' % epoch('2026-11-19', 0, 0), lists[0])

    def test_a_failed_markets_list_stops_the_run(self):
        with mock.patch.object(paths, 'get', lambda url, tries=4: {'error': 'HTTP 503'}), mock.patch.object(marketbase.time, 'sleep', lambda s: None):
            with self.assertRaises(RuntimeError):
                marketbase.report('/unused', '2026-11-18')

    def test_failed_candle_requests_stop_the_run_instead_of_printing_a_table_of_holes(self):
        ms = [market('KXBTC15M', '2026-11-18', k, 'no') for k in range(20)]
        with self.assertRaises(RuntimeError):
            run(Fake(ms, fail_candles=True))

    def test_each_offset_reads_the_quote_of_its_own_minute(self):
        # the quote moves with the candle: bid .20 + .02 k, ask .22 + .02 k; offsets 180, 420, 660 s are the candles k = 3, 7, 11
        ms = [market('KXBTC15M', '2026-11-18', k, 'no') for k in range(10)]
        cells = run(Fake(ms, quote=(lambda k: 0.20 + 0.02 * k, lambda k: 0.22 + 0.02 * k)))['cells']
        self.assertEqual([cells['yes']['offset:%ds' % o]['cost_c'] for o in (180, 420, 660)], [28.0, 36.0, 44.0])
        self.assertEqual([cells['no']['offset:%ds' % o]['cost_c'] for o in (180, 420, 660)], [74.0, 66.0, 58.0])

    def test_a_market_belongs_to_the_day_it_closes_not_the_day_its_window_opened(self):
        ms = [market('KXBTC15M', '2026-11-18', k, 'no', hh=0, mm=0) for k in range(4)]            # close 00:00 on the 18th: window opened on the 17th
        ms += [market('KXBTC15M', '2026-11-12', 100 + k, 'no', hh=0, mm=0) for k in range(4)]     # close exactly at the start of the first day
        ms += [market('KXBTC15M', '2026-11-19', 200 + k, 'no', hh=0, mm=0) for k in range(4)]     # close exactly at the end of the range: out
        rep = run(Fake(ms))
        counts = rep['markets_per_day']['KXBTC15M']
        self.assertEqual((counts['2026-11-12'], counts['2026-11-17'], counts['2026-11-18']), (4, 0, 4))
        self.assertEqual(sum(counts.values()), 8)
        self.assertEqual(rep['markets']['KXBTC15M'], 8)

    def test_a_day_with_under_day_min_rows_in_a_cell_is_not_counted(self):
        # the offset-180 cell has one row a market: day 16 has 2 (YES wins, not counted), 17 has 3 and 18 has 6 (NO wins)
        ms = [market('KXBTC15M', '2026-11-16', k, 'yes') for k in range(2)] + [market('KXBTC15M', '2026-11-17', k, 'no') for k in range(3)] \
            + [market('KXBTC15M', '2026-11-18', k, 'no') for k in range(6)]
        cell = run(Fake(ms))['cells']['yes']['offset:180s']
        self.assertEqual(cell['n'], 11)
        self.assertEqual(cell['edge_days'], '0/2')

    def test_an_empty_side_or_a_crossed_quote_is_no_row(self):
        m = market('KXBTC15M', '2026-11-18', 0, 'no')
        close = paths.iso_epoch(m['close_time'])
        self.assertEqual({(r[0], r[1]) for r in marketbase.rows_of(m, candles_for(close, 0.0, 0.40))}, {(o, 'yes') for o in marketbase.OFFSETS})    # no bid: YES only
        self.assertEqual({(r[0], r[1]) for r in marketbase.rows_of(m, candles_for(close, 0.60, 1.0))}, {(o, 'no') for o in marketbase.OFFSETS})     # no ask: NO only
        self.assertEqual(marketbase.rows_of(m, candles_for(close, 0.0, 1.0)), [])
        self.assertEqual(marketbase.rows_of(m, candles_for(close, 0.60, 0.40)), [])

    def test_a_stale_quote_is_not_used(self):
        cs = [{'end_period_ts': 100, 'yes_bid': {'close_dollars': '0.10'}, 'yes_ask': {'close_dollars': '0.20'}}]
        self.assertEqual(marketbase.quote_at(cs, 100 + marketbase.MAX_QUOTE_AGE), (0.10, 0.20))
        self.assertEqual(marketbase.quote_at(cs, 100 + marketbase.MAX_QUOTE_AGE + 1), (None, None))

    def test_a_market_listed_on_two_pages_counts_once(self):
        ms = [market('KXBTC15M', '2026-11-18', k, 'no') for k in range(4)]
        fake = Fake(ms, page=3)
        real_get = fake.get

        def dup(url, tries=4):
            r = real_get(url, tries)
            if 'cursor=3' in url:                      # the second page repeats the last market of the first
                r['markets'] = [ms[2]] + r['markets']
            return r
        fake.get = dup
        self.assertEqual(run(fake)['markets']['KXBTC15M'], 4)

    def test_the_run_stops_when_a_series_has_no_market_or_a_full_day_is_short(self):
        full = [market(s, '2026-11-18', k, 'no') for s in marketbase.SERIES for k in range(100)]
        with self.assertRaises(RuntimeError):                                 # the other six days have none
            run(Fake(full), check_coverage=True)
        one_week = []
        for s in marketbase.SERIES:
            for d in range(12, 19):
                one_week += [dict(market(s, '2026-11-%02d' % d, k, 'no', hh=k // 4, mm=15 * (k % 4)), ticker='%s-%d-%d' % (s, d, k)) for k in range(96)]
        rep = run(Fake(one_week), check_coverage=True)                        # a full, complete week passes
        self.assertEqual(rep['partial_days'], [])
        short = [m for m in one_week if not (m['ticker'].startswith('KXSOL15M-15-') and int(m['ticker'].split('-')[-1]) >= 20)]
        with self.assertRaises(RuntimeError):                                 # a day at 20 of 96 for one series
            run(Fake(short), check_coverage=True)

    def test_a_day_that_has_not_ended_is_listed_as_partial_and_not_checked(self):
        ms = [market(s, '2026-11-18', k, 'no') for s in marketbase.SERIES for k in range(4)]
        rep = run(Fake(ms), days=1, check_coverage=True, now=epoch('2026-11-18', 13, 0))
        self.assertEqual(rep['partial_days'], ['2026-11-18'])

    def test_a_market_whose_window_is_not_900_seconds_is_counted(self):
        m = market('KXBTC15M', '2026-11-18', 0, 'no')
        m['open_time'] = iso(paths.iso_epoch(m['close_time']) - 3600)
        self.assertEqual(run(Fake([m] + [market('KXBTC15M', '2026-11-18', k, 'no') for k in range(1, 5)]))['odd_windows'], 1)

    def test_day_bounds(self):
        t0, t1, labels = marketbase.day_bounds('2026-11-18', 7)
        self.assertEqual(labels[0], '2026-11-12')
        self.assertEqual(labels[-1], '2026-11-18')
        self.assertEqual(t1 - t0, 7 * 86400)

    def test_the_script_treats_the_stage_as_read_only(self):
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, '..', '..', '..', '.github', 'scripts', 'loss_review_stages.sh')) as fh:
            text = fh.read()
        line = next(l for l in text.splitlines() if l.startswith('READONLY='))
        self.assertIn(' marketbase ', line)


if __name__ == '__main__':
    unittest.main()
