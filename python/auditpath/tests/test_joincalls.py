import calendar
import gzip
import json
import os
import tempfile
import unittest
from unittest import mock

from auditpath import joincalls as J
from auditpath import onetest


def ts(text):
    return calendar.timegm(__import__('time').strptime(text, '%Y-%m-%d %H:%M'))


def candle(end_s, bid, ask):
    """A history candle: ts = the candle END in milliseconds, prices in dollars (flat inside the minute)."""
    return {'ts': end_s * 1000, 'bidO': bid, 'bidH': bid, 'bidL': bid, 'bidC': bid, 'askO': ask, 'askH': ask, 'askL': ask, 'askC': ask,
            'last': None, 'volume': 1, 'oi': 1}


def market(ticker, close_s, result, candles, strike=None, event=None):
    m = {'ticker': ticker, 'series': ticker.split('-')[0], 'openTime': (close_s - 3600) * 1000, 'closeTime': close_s * 1000,
         'strike': strike, 'result': result, 'candles': candles}
    if event:
        m['event'] = event
    return m


def call_row(asset, h, t0, d=1, skip=None):
    return {'asset': asset, 'h': h, 't0': t0, 'dir': d, 'key': 'k', 'kind': 'single', 'rank': 1, 'of': 1, 'fired': 1, 'against': 0,
            'tf': 15, 'heat': 1.0, 'share': 0.5, 'odds': 2.0, 'trig': None, 'single_key': None, 'single_dir': None, 'skip': skip}


def write_shard(folder, name, rows):
    os.makedirs(folder, exist_ok=True)
    with gzip.open(os.path.join(folder, name), 'wt', encoding='utf8') as fh:
        for r in rows:
            fh.write(json.dumps(r) + '\n')


def write_day(root, series, day, markets):
    d = os.path.join(root, series)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, day + '.jsonl'), 'w', encoding='utf8') as fh:
        for m in markets:
            fh.write(json.dumps(m) + '\n')


def mk_calls(spec):
    """A Calls object from {(coin, h): [(t0, dir)]}."""
    series = {(a, h): J.Series([]) for a in J.COINS for h in J.HORIZONS}
    for k, v in spec.items():
        series[k] = J.Series(list(v))
    return J.Calls(series, 'x', {})


D1, D2 = '2026-08-31', '2026-09-01'
T_A = ts('2026-08-31 12:00')     # a call in August
T_B = ts('2026-09-01 12:00')     # a call in September


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        r = self.tmp.name
        self.calls, self.m15, self.hourly = (os.path.join(r, x) for x in ('calls', 'm15', 'hourly'))

    def shard(self, rows, name='calls-BTC-a.jsonl.gz'):
        write_shard(self.calls, name, rows)

    def filler(self):
        """A skipped row per coin and day so that coverage holds without changing the kept rows."""
        return [call_row(a, 15, ts(d + ' 00:00'), 1, 'pair_against_single') for a in J.COINS for d in (D1, D2)]

    def run_join(self, **kw):
        lines = []
        res = J.run(self.calls, self.m15, self.hourly, D1, D2, log=lines.append, **kw)
        return res, lines


class ContractPick(unittest.TestCase):
    def pick(self, close_offset):
        t0 = T_A
        j = J.Joiner(mk_calls({('BTC', 15): [(t0, 1)]}))
        j.m15_market('BTC', market('KXBTC15M-X', t0 + close_offset, 'yes', [candle(t0, 0.48, 0.52)]))
        return len(j.bundles)

    def test_the_edges_of_300_to_840_seconds(self):
        self.assertEqual(self.pick(299), 0)
        self.assertEqual(self.pick(300), 1)
        self.assertEqual(self.pick(840), 1)
        self.assertEqual(self.pick(841), 0)

    def test_the_next_contract_of_the_series_is_not_taken(self):
        t0 = T_A
        j = J.Joiner(mk_calls({('BTC', 15): [(t0, 1)]}))
        j.m15_market('BTC', market('KXBTC15M-A', t0 + 300, 'yes', [candle(t0, 0.48, 0.52)]))
        j.m15_market('BTC', market('KXBTC15M-B', t0 + 300 + 900, 'yes', [candle(t0, 0.48, 0.52)]))
        self.assertEqual([b['id'] for b in j.bundles], ['KXBTC15M-A'])

    def test_a_duplicate_ticker_is_taken_once(self):
        t0 = T_A
        j = J.Joiner(mk_calls({('BTC', 15): [(t0, 1)]}))
        m = market('KXBTC15M-A', t0 + 400, 'yes', [candle(t0, 0.48, 0.52)])
        j.m15_market('BTC', m)
        j.m15_market('BTC', m)
        self.assertEqual(len(j.bundles), 1)
        self.assertEqual(j.stats['duplicate_ticker_skipped'], 1)


class StrikePick(unittest.TestCase):
    def item(self, strike, bid, ask, t0=T_A):
        return (strike, 'KXBTCD-X-T%d' % strike, 'yes', onetest.index(onetest.norm_hist_candles([candle(t0, bid, ask)])))

    def test_nearest_fifty_cents_on_the_yes_mid(self):
        items = [self.item(60000, 0.40, 0.44), self.item(61000, 0.47, 0.51), self.item(62000, 0.58, 0.62)]   # mids 42, 49, 60
        it, n2, _ = J.pick_strike(items, T_A)
        self.assertEqual((it[0], n2), (61000, 3))

    def test_one_sided_strikes_are_not_taken_however_near(self):
        items = [self.item(60000, 0.0, 0.50), self.item(61000, 0.50, 1.0), self.item(62000, 0.50, 0.50), self.item(63000, 0.30, 0.34)]
        it, n2, _ = J.pick_strike(items, T_A)
        self.assertEqual((it[0], n2), (63000, 1))

    def test_a_tie_goes_to_the_lower_strike(self):
        items = [self.item(62000, 0.53, 0.57), self.item(60000, 0.43, 0.47), self.item(61000, 0.20, 0.24)]   # mids 55, 45, 22
        it, _, dist = J.pick_strike(items, T_A)
        self.assertEqual((it[0], dist), (60000, 10))

    def test_no_strike_when_nothing_is_two_sided_at_t0(self):
        items = [self.item(60000, 0.40, 0.44, t0=T_A + 60)]            # its candle ends a minute after T0
        self.assertEqual(J.pick_strike(items, T_A), (None, 0, None))


class CallsTable(Base):
    def test_skip_rows_are_dropped_and_do_not_change_the_hash(self):
        kept = [call_row('BTC', 15, T_A), call_row('ETH', 60, T_B, -1), call_row('BTC', 60, T_B)]
        self.shard(kept + self.filler())
        c1 = J.load_calls(self.calls, J.day_number(D1), J.day_number(D2))
        self.assertEqual(c1.info['rows_kept'], 3)
        self.assertEqual(c1.info['rows_skipped'], 4)
        # The same kept rows in another shard split and order, with one more skipped row, give the same hash.
        other = tempfile.TemporaryDirectory()
        self.addCleanup(other.cleanup)
        extra = [call_row('ETH', 15, T_A, 1, 'pair_against_single')]
        write_shard(other.name, 'calls-1.jsonl.gz', list(reversed(kept[1:])) + self.filler() + extra)
        write_shard(other.name, 'calls-2.jsonl.gz', kept[:1])
        c2 = J.load_calls(other.name, J.day_number(D1), J.day_number(D2))
        self.assertEqual(c2.info['rows_skipped'], 5)
        self.assertEqual(c2.digest, c1.digest)

    def test_a_changed_kept_row_changes_the_hash(self):
        self.shard([call_row('BTC', 15, T_A)] + self.filler())
        a = J.load_calls(self.calls, J.day_number(D1), J.day_number(D2)).digest
        self.shard([call_row('BTC', 15, T_A, -1)] + self.filler())
        b = J.load_calls(self.calls, J.day_number(D1), J.day_number(D2)).digest
        self.assertNotEqual(a, b)

    def test_only_h15_and_h60_of_btc_and_eth_are_kept(self):
        rows = [call_row('SOL', 15, T_A), call_row('BTC', 30, T_A), call_row('BTC', 15, T_A)]
        self.shard(rows + self.filler())
        c = J.load_calls(self.calls, J.day_number(D1), J.day_number(D2))
        self.assertEqual((c.info['rows_kept'], c.info['rows_ignored_other_coin_or_h']), (1, 2))

    def test_duplicate_asset_h_t0_is_refused(self):
        self.shard([call_row('BTC', 15, T_A), call_row('BTC', 15, T_A, -1)] + self.filler())
        with self.assertRaises(J.JoinError) as cm:
            J.load_calls(self.calls, J.day_number(D1), J.day_number(D2))
        self.assertIn('duplicate', str(cm.exception))

    def test_a_skip_row_beside_a_kept_row_is_not_a_duplicate(self):
        self.shard([call_row('BTC', 15, T_A), call_row('BTC', 15, T_A, -1, 'pair_against_single')] + self.filler())
        self.assertEqual(J.load_calls(self.calls, J.day_number(D1), J.day_number(D2)).info['rows_kept'], 1)

    def test_a_day_without_rows_for_a_coin_is_refused(self):
        self.shard([call_row('BTC', 15, T_A), call_row('BTC', 15, T_B), call_row('ETH', 15, T_A)])
        with self.assertRaises(J.JoinError) as cm:
            J.load_calls(self.calls, J.day_number(D1), J.day_number(D2))
        self.assertIn('cover', str(cm.exception))

    def test_rows_outside_the_range_or_in_milliseconds_are_refused(self):
        for bad in (ts('2026-09-02 00:00'), T_A * 1000, T_A + 7):
            self.shard([call_row('BTC', 15, bad)] + self.filler())
            with self.assertRaises(J.JoinError):
                J.load_calls(self.calls, J.day_number(D1), J.day_number(D2))

    def test_no_shard_is_refused(self):
        os.makedirs(self.calls)
        with self.assertRaises(J.JoinError):
            J.load_calls(self.calls, 1, 2)


class EndToEnd(Base):
    def fixture(self):
        self.shard([call_row('BTC', 15, T_A, 1), call_row('BTC', 15, T_B, -1)] + self.filler())
        # August call: contract closes 600 s later, YES bid 48 ask 52, result yes. September call: the same book, result yes.
        write_day(self.m15, 'KXBTC15M', D1, [market('KXBTC15M-A', T_A + 600, 'yes', [candle(T_A, 0.48, 0.52)])])
        write_day(self.m15, 'KXBTC15M', D2, [market('KXBTC15M-B', T_B + 600, 'yes', [candle(T_B, 0.48, 0.52)])])

    def test_the_hash_line_comes_before_any_history_file_is_listed_or_opened(self):
        self.fixture()
        lines, events = [], []

        def log(s):
            lines.append(s)

        real_list, real_open = J.list_days, J.open_text

        def spy_list(*a, **k):
            events.append(('list', any('"sha256"' in x for x in lines)))
            return real_list(*a, **k)

        def spy_open(path):
            events.append(('open', any('"sha256"' in x for x in lines)))
            return real_open(path)
        with mock.patch.object(J, 'list_days', spy_list):
            J.run(self.calls, self.m15, self.hourly, D1, D2, log=log, opener=spy_open)
        self.assertTrue(events and all(seen for _, seen in events))
        self.assertTrue(any(k == 'open' for k, _ in events))
        self.assertTrue(lines[0].startswith('AUDITPATH join {"block":"calls","sha256":"'))
        self.assertEqual(len(lines[0].split('"sha256":"')[1].split('"')[0]), 64)

    def test_a_refused_calls_table_opens_nothing(self):
        self.shard([call_row('BTC', 15, T_A), call_row('BTC', 15, T_A)] + self.filler())
        opened = []
        with self.assertRaises(J.JoinError):
            J.run(self.calls, self.m15, self.hourly, D1, D2, log=lambda s: opened.append(s), opener=lambda p: opened.append(p))
        self.assertEqual(opened, [])

    def test_units_result_and_the_month_split(self):
        self.fixture()
        j_calls = J.load_calls(self.calls, J.day_number(D1), J.day_number(D2))
        j = J.Joiner(j_calls)
        j.run_history(self.m15, self.hourly, J.day_number(D1), J.day_number(D2))
        a, b = j.bundles
        # t0 in seconds met the candle end in milliseconds: the quote was found. YES costs the ask 52c, C = floor(1000 / 52) = 19,
        # fee 0.07 x 19 x 0.52 x 0.48 = 0.332 rounded up to 34c.
        self.assertTrue(a['called']['scored'])
        self.assertEqual((a['called']['p_c'], a['called']['C']), (52, 19))
        self.assertEqual(onetest.fee_c(19, 52), 34)
        # YES held to a settlement of yes: (19 x 100 - (19 x 52 + 34)) / 19.
        self.assertAlmostEqual(a['called']['held_c'], (1900 - 1022) / 19.0, places=6)
        # The September call is a NO at 1 - bid = 52c (the same price) and the result is yes: all of it lost.
        self.assertEqual(b['side'], 'no')
        self.assertAlmostEqual(b['called']['held_c'], -1022 / 19.0, places=6)
        res, lines = self.run_join()
        months = res['analysis']['secondary']['splits']['month']
        self.assertEqual(sorted(months), ['2026-08', '2026-09'])
        self.assertEqual(months['2026-08']['n_entries'], 1)
        self.assertNotIn('week', res['analysis']['secondary']['splits'])
        self.assertEqual(res['hours'], 48)

    def test_result_no_flows_into_the_cents_held(self):
        self.shard([call_row('BTC', 15, T_A, -1)] + self.filler())
        write_day(self.m15, 'KXBTC15M', D1, [market('KXBTC15M-A', T_A + 600, 'no', [candle(T_A, 0.48, 0.52)])])
        j = J.Joiner(J.load_calls(self.calls, J.day_number(D1), J.day_number(D2)))
        j.run_history(self.m15, self.hourly, J.day_number(D1), J.day_number(D2))
        self.assertAlmostEqual(j.bundles[0]['called']['held_c'], (1900 - 1022) / 19.0, places=6)

    def test_no_contract_and_missing_day_file_are_counted_apart(self):
        self.shard([call_row('BTC', 15, T_A), call_row('BTC', 15, ts('2026-08-31 13:00')), call_row('BTC', 15, T_B)] + self.filler())
        # The 12:00 call has its contract; the 13:00 call has none in 300 to 840 s (the file holds a contract 1000 s later);
        # the September day has no file at all.
        write_day(self.m15, 'KXBTC15M', D1, [market('KXBTC15M-A', T_A + 600, 'yes', [candle(T_A, 0.48, 0.52)]),
                                             market('KXBTC15M-Z', ts('2026-08-31 13:00') + 1000, 'yes', [])])
        res, lines = self.run_join()
        c = res['entries']['by_kind_coin']['15m BTC']
        self.assertEqual((c['calls'], c['entries'], c['no_contract'], c['no_contract_day_file_missing']), (3, 1, 2, 1))
        self.assertEqual(res['history']['BTC_15m_days_missing'], 1)

    def test_printed_lines_are_short_and_hold_no_ticker(self):
        self.fixture()
        res, lines = self.run_join()
        self.assertTrue(lines and all(x.startswith('AUDITPATH join {') for x in lines))
        self.assertTrue(all(len(x) < 3000 for x in lines), max(len(x) for x in lines))
        self.assertFalse(any('KX' in x for x in lines))
        self.assertTrue(any('"block":"verdict"' in x for x in lines))
        json.dumps(res)

    def test_books_share_by_month_and_kind(self):
        self.shard([call_row('BTC', 15, T_A, 1), call_row('BTC', 15, T_B, 1)] + self.filler())
        write_day(self.m15, 'KXBTC15M', D1, [market('KXBTC15M-A', T_A + 600, 'yes', [candle(T_A, 0.48, 0.52)])])
        write_day(self.m15, 'KXBTC15M', D2, [market('KXBTC15M-B', T_B + 600, 'yes', [candle(T_B, 0.0, 0.52)])])   # one-sided
        res, _ = self.run_join()
        self.assertEqual(res['books']['15m 2026-08']['one_sided_or_missing'], 0)
        self.assertEqual(res['books']['15m 2026-09']['one_sided_or_missing'], 1)
        self.assertEqual(res['books']['15m 2026-09']['share_one_sided_or_missing'], 1.0)


class Hourly(Base):
    def ladder(self, close, rows):
        """rows = [(strike, bid, ask, result)] at the minute T_A."""
        return [market('KXBTCD-EV-T%d' % s, close, r, [candle(T_A, b, a)], strike=float(s), event='KXBTCD-EV') for s, b, a, r in rows]

    def test_the_hourly_entry_takes_the_strike_nearest_fifty_cents(self):
        self.shard([call_row('BTC', 60, T_A, 1)] + self.filler())
        write_day(self.hourly, 'KXBTCD', D1, self.ladder(T_A + 1800, [(60000, 0.40, 0.44, 'no'), (61000, 0.47, 0.51, 'yes'), (62000, 0.80, 0.84, 'yes')]))
        res, lines = self.run_join()
        a = res['hourly_availability']
        self.assertTrue(a['available'])
        self.assertEqual((a['calls_60m'], a['calls_with_a_strike_mid_10c_to_90c'], a['strikes_per_event_median']), (1, 1, 3))
        self.assertEqual(res['entries']['by_kind_coin']['hourly BTC']['entries'], 1)
        # The 61000 strike (YES mid 49c) was chosen: its ask is 51c, so the YES cost is 51c and the result yes pays.
        j = J.Joiner(J.load_calls(self.calls, J.day_number(D1), J.day_number(D2)))
        j.run_history(self.m15, self.hourly, J.day_number(D1), J.day_number(D2))
        b = j.bundles[0]
        self.assertEqual((b['id'], b['kind'], b['called']['p_c']), ('KXBTCD-EV-T61000', 'hourly', 51))
        self.assertEqual(res['analysis']['secondary']['splits']['kind']['hourly']['n_entries'], 1)

    def test_event_close_edges_600_to_3300_seconds(self):
        for off, want in ((599, 0), (600, 1), (3300, 1), (3301, 0)):
            j = J.Joiner(mk_calls({('BTC', 60): [(T_A, 1)]}))
            items = [(61000.0, 'KXBTCD-EV-T61000', 'yes', onetest.index(onetest.norm_hist_candles([candle(T_A, 0.47, 0.51)])))]
            j.hourly_group('BTC', T_A + off, items)
            self.assertEqual(len(j.bundles), want, off)

    def test_no_strike_is_counted_when_the_event_has_no_two_sided_quote(self):
        self.shard([call_row('BTC', 60, T_A, 1)] + self.filler())
        write_day(self.hourly, 'KXBTCD', D1, self.ladder(T_A + 1800, [(60000, 0.0, 0.05, 'no'), (61000, 0.50, 1.0, 'yes')]))
        res, _ = self.run_join()
        c = res['entries']['by_kind_coin']['hourly BTC']
        self.assertEqual((c['calls'], c.get('entries', 0), c['no_strike'], c.get('no_contract', 0)), (1, 0, 1, 0))

    def test_a_ladder_far_from_the_money_is_not_available_and_is_left_out(self):
        self.shard([call_row('BTC', 60, T_A, 1), call_row('BTC', 15, T_B, 1)] + self.filler())
        write_day(self.hourly, 'KXBTCD', D1, self.ladder(T_A + 1800, [(60000, 0.02, 0.04, 'no'), (61000, 0.96, 0.98, 'yes')]))
        write_day(self.m15, 'KXBTC15M', D2, [market('KXBTC15M-B', T_B + 600, 'yes', [candle(T_B, 0.48, 0.52)])])
        res, lines = self.run_join()
        self.assertFalse(res['hourly_availability']['available'])
        self.assertFalse(res['hourly_in_analysis'])
        self.assertEqual(res['entries_analysed'], 1)
        self.assertEqual(list(res['analysis']['secondary']['splits']['kind']), ['15m'])
        self.assertTrue(any('"status":"not available"' in x for x in lines))
        self.assertTrue(any('"block":"hourly_availability"' in x for x in lines))

    def test_unavailable_hourly_keeps_its_own_analysis_in_out_only_and_books_cover_it(self):
        self.shard([call_row('BTC', 60, T_A, 1), call_row('BTC', 15, T_B, 1)] + self.filler())
        write_day(self.hourly, 'KXBTCD', D1, self.ladder(T_A + 1800, [(60000, 0.02, 0.04, 'no'), (61000, 0.96, 0.98, 'yes')]))
        write_day(self.m15, 'KXBTC15M', D2, [market('KXBTC15M-B', T_B + 600, 'yes', [candle(T_B, 0.48, 0.52)])])
        res, lines = self.run_join()
        self.assertEqual(res['hourly_only_analysis_not_printed']['secondary']['splits']['kind'].keys(), {'hourly'})
        self.assertFalse(any('hourly_only' in x for x in lines))
        self.assertIn('hourly 2026-08', res['books'])
        self.assertIn('15m 2026-09', res['books'])


class HoursAndEmit(Base):
    def test_hours_are_days_with_an_entry_times_24_and_both_counts_are_printed(self):
        self.shard([call_row('BTC', 15, T_A, 1)] + self.filler())
        write_day(self.m15, 'KXBTC15M', D1, [market('KXBTC15M-A', T_A + 600, 'yes', [candle(T_A, 0.48, 0.52)])])
        res, lines = self.run_join()
        self.assertEqual((res['calendar_days'], res['days_with_an_entry'], res['hours']), (2, 1, 24))
        self.assertEqual(res['analysis']['hours'], 24)
        self.assertTrue(any('"block":"days"' in x and '"calendar_days":2' in x and '"days_with_an_entry":1' in x for x in lines))

    def test_a_block_that_cannot_be_split_is_refused(self):
        with self.assertRaises(J.JoinError):
            J.emit(lambda s: None, 'big', {'k': 'x' * 3000})
        out = []
        J.emit(out.append, 'ok', {'a': 'x' * 2000, 'b': 'y' * 2000})
        self.assertEqual(len(out), 2)
        self.assertTrue(all(len(x) < 3000 for x in out))


if __name__ == '__main__':
    unittest.main()
