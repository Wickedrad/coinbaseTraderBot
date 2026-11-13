"""One test per finding of the builder review: each fails on the code before the fix. Synthetic data only."""
import gzip
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout

from lossreview import audit, builder, fees, nightly, outcomes as oc, triage
from lossreview.tests import test_builder as tb
from lossreview.tests.test_builder import T0, TK, closed, fill, heat_entry, plan_event, rec


def dict_no_book(r):
    del r[2]['bookPnl']
    return r


def one(recs):
    trips, skipped = builder.build(sorted(recs, key=lambda r: r[0]))
    assert (len(trips), skipped) == (1, 0), (len(trips), skipped)
    return trips[0]


class BuilderFixTests(unittest.TestCase):
    def test_a_plan_event_written_just_after_its_fill_still_names_the_rule(self):
        # the engine logs the plan event right after it sends the sale; a paper fill lands inside that call
        ef, xf = fees.taker_fee(20, 0.50), fees.taker_fee(20, 0.62)
        pnl = round(20 * 0.12 - ef - xf, 6)
        r = one([heat_entry(0), fill(1, 'bid', 0.50, 20), fill(300, 'ask', 0.62, 20, coid='c2'),
                 plan_event(300.002, 'plan_ratchet_sell', 0.62), closed(310, 'yes', pnl)])
        self.assertEqual(r['legs'][0]['rule'], 'ratchet')
        self.assertEqual(r['exit_event'], 'ratchet')

    def test_a_loser_cut_that_fills_minutes_after_it_was_decided_is_still_a_loser_cut(self):
        # decided at t=100, no bid, retried every 10 s as plan_ratchet_retry, filled at t=300 under the round-trip cost
        ef, xf = fees.taker_fee(20, 0.50), fees.taker_fee(20, 0.30)
        pnl = round(20 * (0.30 - 0.50) - ef - xf, 6)
        since = int((T0 + 100) * 1000)
        recs = [heat_entry(0), fill(1, 'bid', 0.50, 20),
                rec(100, 'plan', {'event': 'plan_loser_cut_sell', 'ticker': TK, 'side': 'yes', 'count': 20, 'bid': 0.3, 'net': -4.0, 'sent': True, 'since': since, 'at': since})]
        recs += [rec(100 + 10 * k, 'plan', {'event': 'plan_ratchet_retry', 'ticker': TK, 'side': 'yes', 'count': 20, 'bid': 0.3, 'net': -4.0, 'since': since}) for k in range(1, 20)]
        recs += [fill(299, 'ask', 0.30, 20, coid='c2'), closed(310, 'yes', pnl)]
        r = one(recs)
        self.assertEqual(r['legs'][0]['rule'], 'loser_cut')
        self.assertTrue(r['legs'][0]['below_breakeven'])
        self.assertFalse(r['defect_sale'])           # a permitted cut, not a defect for the exit owner
        self.assertEqual(r['exit_event'], 'loser_cut')

    def test_a_retry_whose_origin_is_unknown_falls_back_to_the_sale_under_way_or_other(self):
        recs = [heat_entry(0), fill(1, 'bid', 0.50, 20),
                rec(250, 'plan', {'event': 'plan_ratchet_retry', 'ticker': TK, 'side': 'yes', 'count': 20, 'bid': 0.3, 'net': -4.0, 'since': 123}),
                fill(251, 'ask', 0.30, 20, coid='c2'), closed(260, 'yes', -4.0)]
        self.assertEqual(one(recs)['legs'][0]['rule'], 'other')       # nothing to say which rule: the defect flag stays on

    def test_a_plan_event_long_after_the_fill_is_not_borrowed(self):
        r = one([heat_entry(0), fill(1, 'bid', 0.50, 20), fill(300, 'ask', 0.62, 20, coid='c2'),
                 plan_event(330, 'plan_ratchet_sell', 0.62), closed(340, 'yes', 0.5)])
        self.assertEqual(r['legs'][0]['rule'], 'other')

    def test_loser_cut_that_settles_a_winner_is_cut_then_won(self):
        ef, xf = fees.taker_fee(30, 0.33), fees.taker_fee(30, 0.25)
        pnl = round(30 * (0.25 - 0.33) - ef - xf, 6)
        r = one([heat_entry(0, 'no', 0.67, 30), fill(1, 'ask', 0.67, 30), plan_event(200, 'plan_loser_cut_sell', 0.25),
                 fill(201, 'bid', 0.75, 30, coid='c2'), closed(210, 'no', pnl), rec(900, 'settlement', {'ticker': TK, 'result': 'no'})])
        self.assertEqual(r['exit_event'], 'loser_cut')
        self.assertTrue(r['side_settles_win'])
        self.assertEqual(triage.classify(r)['primary'], 'CUT_THEN_WON')

    def test_a_loser_cut_event_named_loser_cut_counts_as_a_cut(self):
        self.assertIn('loser_cut', triage.CUT_EVENTS)
        self.assertIn('plan_loser_cut_sell', triage.CUT_EVENTS)

    def test_a_remainder_with_no_result_is_unresolved_then_finished_from_the_public_result(self):
        # 20 bought, 8 sold by the ratchet, 12 held to the end and no settlement record in the files read
        ef, xf = fees.taker_fee(20, 0.50), fees.taker_fee(8, 0.62)
        pnl = round(8 * 0.62 + 12 * 1.0 - 20 * 0.50 - ef - xf, 6)
        r = one([heat_entry(0), fill(1, 'bid', 0.50, 20), plan_event(300, 'plan_ratchet_sell', 0.62),
                 fill(302, 'ask', 0.62, 8, coid='c2'), closed(900, 'yes', pnl, settled=True)])
        self.assertTrue(r['unresolved'])
        self.assertTrue(r['fidelity_flag'])        # not trusted until the result is known
        self.assertIsNone(r['pnl_fills'])
        self.assertEqual(r['exit_event'], 'settled')
        done = builder.resolve_payout(dict(r, side_settles_win=True))
        self.assertFalse(done['unresolved'])
        self.assertAlmostEqual(done['pnl_fills'], pnl, places=4)
        self.assertFalse(done['fidelity_flag'])
        lost = builder.resolve_payout(dict(r, side_settles_win=False))
        self.assertAlmostEqual(lost['pnl_fills'], round(8 * 0.62 - 20 * 0.50 - ef - xf, 6), places=4)

    def test_resolve_payout_leaves_a_resolved_row_alone(self):
        ef, xf = fees.taker_fee(20, 0.50), fees.taker_fee(20, 0.62)
        pnl = round(20 * 0.12 - ef - xf, 6)
        r = one([heat_entry(0), fill(1, 'bid', 0.50, 20), plan_event(300, 'plan_ratchet_sell', 0.62), fill(302, 'ask', 0.62, 20, coid='c2'),
                 closed(310, 'yes', pnl)])
        self.assertIs(builder.resolve_payout(r), r)

    def test_a_partial_sale_then_settlement_ends_as_settled(self):
        ef, xf = fees.taker_fee(20, 0.50), fees.taker_fee(8, 0.62)
        pnl = round(8 * 0.62 + 12 * 1.0 - 20 * 0.50 - ef - xf, 6)
        r = one([heat_entry(0), fill(1, 'bid', 0.50, 20), plan_event(300, 'plan_ratchet_sell', 0.62), fill(302, 'ask', 0.62, 8, coid='c2'),
                 rec(900, 'settlement', {'ticker': TK, 'result': 'yes'}), closed(901, 'yes', pnl, settled=True)])
        self.assertEqual(r['exit_event'], 'settled')
        self.assertAlmostEqual(r['held_to_end'], 12)
        self.assertFalse(r['unresolved'])

    def test_order_t_is_never_after_the_first_entry_fill(self):
        # the fill is stamped 2 s before the entry record (a paper fill inside the order call)
        r = one([heat_entry(2), fill(0, 'bid', 0.50, 20), fill(100, 'ask', 0.55, 20, coid='c2'), closed(110, 'yes', 0.5)])
        self.assertLessEqual(r['order_t'], r['entry_t'])
        self.assertAlmostEqual(r['order_t'], T0, delta=0.01)

    def test_fills_that_are_not_the_trips_own_flag_a_trip_that_has_no_logged_pnl(self):
        def nobook(pnl):
            r = closed(310, 'yes', pnl)
            del r[2]['bookPnl']          # an old closed record: the P&L it carries is not the trip's own
            return r
        # clean: bought the plan's 20, sold 20, no logged P&L: the fills explain it, nothing to flag
        ef, xf = fees.taker_fee(20, 0.50), fees.taker_fee(20, 0.62)
        clean = one([heat_entry(0), fill(1, 'bid', 0.50, 20), fill(300, 'ask', 0.62, 20, coid='c2'), nobook(0.0)])
        self.assertEqual((clean['pnl_source'], clean['fidelity_flag']), ('fills', False))
        # a resting quote of another order filled in the same market: 30 bought against a plan of 20
        over = one([heat_entry(0), fill(1, 'bid', 0.50, 20), fill(2, 'bid', 0.40, 10, taker=False, coid='c9'), fill(300, 'ask', 0.62, 20, coid='c2'), nobook(0.0)])
        self.assertEqual((over['count_filled'], over['count_plan']), (30, 20))
        self.assertTrue(over['fidelity_flag'])
        # more sold than this trip bought: a sale of another position
        more = one([heat_entry(0), fill(1, 'bid', 0.50, 20), fill(299, 'ask', 0.40, 9, coid='c8'), fill(300, 'ask', 0.62, 20, coid='c2'), nobook(0.0)])
        self.assertTrue(more['fidelity_flag'])
        # with the bot's own logged P&L the reconciliation gap decides, as before: the same fills with a matching logged P&L stay clean
        logged = one([heat_entry(0), fill(1, 'bid', 0.50, 20), fill(300, 'ask', 0.62, 20, coid='c2'), closed(310, 'yes', round(20 * 0.12 - ef - xf, 6))])
        self.assertEqual((logged['pnl_source'], logged['fidelity_flag']), ('logged', False))

    def test_a_foreign_fill_flag_survives_resolving_the_payout(self):
        r = one([heat_entry(0), fill(1, 'bid', 0.50, 20), fill(2, 'bid', 0.40, 10, taker=False, coid='c9'), fill(300, 'ask', 0.62, 20, coid='c2'),
                 dict_no_book(closed(310, 'yes', 0.0))])
        r = dict(r, unresolved=True, side_settles_win=True, held_to_end=10.0, pnl_source='fills')
        self.assertTrue(builder.resolve_payout(r)['fidelity_flag'])

    def test_an_earlier_trip_of_the_same_market_does_not_lend_its_fills(self):
        # two trips in one market: the second one's window starts after the first one's close
        e1 = [heat_entry(0), fill(1, 'bid', 0.50, 20), fill(100, 'ask', 0.55, 20, coid='c2'), closed(110, 'yes', 0.5)]
        e2 = [heat_entry(120), fill(121, 'bid', 0.40, 10, coid='c3'), fill(200, 'ask', 0.45, 10, coid='c4'), closed(210, 'yes', 0.2)]
        trips, skipped = builder.build(sorted(e1 + e2, key=lambda r: r[0]))
        self.assertEqual(len(trips), 2)
        self.assertEqual([t['count_filled'] for t in trips], [20, 10])


class AuditReadTests(unittest.TestCase):
    def test_the_same_day_present_plain_and_gzipped_is_counted_once(self):
        lines = [json.dumps({'seq': i, 'ts': '2026-11-12T15:05:0%d.000Z' % i, 'kind': 'fill', 'data': {'n': i}}, separators=(',', ':')) for i in range(3)]
        with tempfile.TemporaryDirectory() as d:
            a, b = os.path.join(d, 'audit-2026-11-12.jsonl'), os.path.join(d, 'audit-2026-11-12.jsonl.gz')
            with open(a, 'w') as fh:
                fh.write('\n'.join(lines) + '\n')
            with gzip.open(b, 'wt') as fh:
                fh.write('\n'.join(lines) + '\n')
            recs, bad = audit.read_files([a, b])
            self.assertEqual((len(recs), bad), (3, 0))

    def test_nightly_ignores_a_partial_file(self):
        with tempfile.TemporaryDirectory() as d:
            ad = os.path.join(d, 'audit')
            os.makedirs(ad)
            with open(os.path.join(ad, 'audit-2026-11-12.jsonl.partial'), 'w') as fh:
                fh.write('{"truncated"\n')
            with self.assertRaises(SystemExit):
                nightly.run('2026-11-12', ad, os.path.join(d, 'out'), net=False)


class OutcomeFixTests(unittest.TestCase):
    def test_held_range_counts_only_candles_wholly_inside_the_hold(self):
        def c(end, hi, lo):
            return {'end_period_ts': end, 'yes_bid': {'high_dollars': str(hi), 'low_dollars': str(lo), 'close_dollars': str(hi)},
                    'yes_ask': {'high_dollars': str(hi + .02), 'low_dollars': str(lo + .02), 'close_dollars': str(hi + .02)}}
        candles = [c(60, 0.95, 0.40), c(120, 0.50, 0.45), c(180, 0.55, 0.50), c(240, 0.99, 0.10)]
        # entry at t=70, closed at t=200: the 60 s candle (before) and the 240 s candle (after) are outside; 120 starts at 60 < 70 so
        # it is outside too (it straddles the entry); only the 180 candle is wholly inside
        self.assertEqual(oc.held_range(candles, 'yes', 70, 200), (0.55, 0.50))
        self.assertEqual(oc.held_range(candles, 'yes', 70, 100), (None, None))      # a hold under a minute: nothing proven

    def test_a_sample_after_the_hold_is_not_a_reachable_bid(self):
        # a 90 s hold: bid_2m and bid_5m are moments after the trip ended and cannot show a reachable bid
        base = {'entry_px': 0.50, 'count': 20, 'stake': 10.0, 'entry_fill_px': 0.50, 'count_filled': 20, 'entry_fee': 0.18,
                'exit_fee': 0.2, 'exit_px': 0.40, 'pnl': -2.4, 'hold_s': 90.0, 'bid_entry_min': 0.48, 'bid_1m': 0.48, 'bid_2m': 0.97, 'bid_5m': 0.97,
                'best_bid_held': None, 'side': 'yes', 'actual': True}
        eco = triage.economics(dict(base))
        ok, proven = triage.reachable(dict(base), eco)
        self.assertFalse(ok)
        self.assertFalse(proven)
        short = dict(base, hold_s=20.0, bid_entry_min=0.97, bid_1m=0.97)     # a 20 s hold: the entry minute closed after the trip did
        self.assertFalse(triage.reachable(short, triage.economics(dict(short)))[0])
        long_hold = dict(base, hold_s=400.0)
        ok2, _ = triage.reachable(long_hold, triage.economics(dict(long_hold)))
        self.assertTrue(ok2)


class NightlyOutputTests(unittest.TestCase):
    def day(self, recs, name='audit-2026-11-12.jsonl'):
        d = tempfile.mkdtemp()
        ad = os.path.join(d, 'audit')
        os.makedirs(ad)
        with open(os.path.join(ad, name), 'w') as fh:
            for i, (t, k, data, _s) in enumerate(sorted(recs, key=lambda r: r[0])):
                from lossreview.tests.test_nightly import line
                fh.write(line(t, k, data, i) + '\n')
        return d, ad

    def test_the_printed_summary_hides_dollars_for_a_cell_under_five_trips(self):
        ef, xf = fees.taker_fee(20, 0.50), fees.taker_fee(20, 0.62)
        pnl = round(20 * 0.12 - ef - xf, 6)
        d, ad = self.day([heat_entry(0), fill(1, 'bid', 0.50, 20), plan_event(300, 'plan_ratchet_sell', 0.62), fill(302, 'ask', 0.62, 20, coid='c2'), closed(310, 'yes', pnl)])
        buf = io.StringIO()
        with redirect_stdout(buf):
            nightly.main(['--day', '2026-11-12', '--audit-dir', ad, '--out', os.path.join(d, 'out'), '--no-net'])
        out = buf.getvalue()
        self.assertIn('LOSSREVIEW', out)
        self.assertNotIn('KXBTC', out)
        self.assertNotRegex(out, r'"(net|fees|gross|loser_dollars)"')   # one trip: a dollar figure is that trade
        self.assertNotRegex(out, r'class \w+ trips \d+ dollars')

    def run_day(self, recs):
        d, ad = self.day(recs)
        buf = io.StringIO()
        with redirect_stdout(buf):
            nightly.main(['--day', '2026-11-12', '--audit-dir', ad, '--out', os.path.join(d, 'out'), '--no-net'])
        return buf.getvalue()

    def six_trips(self, n_winners, losers):
        """n_winners ratchet winners and `losers`: list of (price, count) cut trips; each trip in its own 20-minute slot."""
        recs = []
        n = 0
        for _ in range(n_winners):
            off = 1000 * n
            n += 1
            ef, xf = fees.taker_fee(20, 0.50), fees.taker_fee(20, 0.62)
            recs += [heat_entry(off), fill(off + 1, 'bid', 0.50, 20, coid='w%d' % n), plan_event(off + 300, 'plan_ratchet_sell', 0.62),
                     fill(off + 302, 'ask', 0.62, 20, coid='x%d' % n), closed(off + 310, 'yes', round(20 * 0.12 - ef - xf, 6))]
        return recs, n

    def test_no_printed_dollar_figure_is_one_trade_or_differences_down_to_one(self):
        # 5 winners and ONE trade sold under break-even by the ratchet (a defect): the day has 6 trips, a cell of 1 loser
        recs, n = self.six_trips(5, [])
        off = 1000 * n
        ef, xf = fees.taker_fee(20, 0.50), fees.taker_fee(20, 0.51)
        recs += [heat_entry(off), fill(off + 1, 'bid', 0.50, 20, coid='lz'), plan_event(off + 100, 'plan_ratchet_sell', 0.51),
                 fill(off + 101, 'ask', 0.51, 20, coid='lx'), closed(off + 110, 'yes', round(20 * 0.01 - ef - xf, 6))]
        out = self.run_day(recs)
        self.assertNotRegex(out, r'"(loser_dollars|defect_dollars)"')          # 1 loser, 1 defect sale: neither is printed
        lone = round(20 * 0.01 - ef - xf, 2)
        self.assertNotIn(str(lone), out)
        self.assertIn('"net"', out)                                            # the six-trip total is a cell of six
        self.assertNotRegex(out, r'class \w+ trips \d+ dollars')               # a small class is in the day: counts only, so net cannot be differenced

    def fee_only(self, k):
        off = 1000 * (20 + k)
        ef, xf = fees.taker_fee(20, 0.50), fees.taker_fee(20, 0.51)
        return [heat_entry(off), fill(off + 1, 'bid', 0.50, 20, coid='fz%d' % k), plan_event(off + 100, 'plan_ratchet_sell', 0.51),
                fill(off + 101, 'ask', 0.51, 20, coid='fx%d' % k), closed(off + 110, 'yes', round(20 * 0.01 - ef - xf, 6))]

    def test_class_dollars_are_printed_only_when_no_cell_is_small_and_the_winners_are_not_one(self):
        recs, _ = self.six_trips(5, [])
        for k in range(5):
            recs += self.fee_only(k)
        out = self.run_day(recs)                                  # 5 FEE_ONLY losers and 5 winners: every cell is five
        self.assertRegex(out, r'class FEE_ONLY trips 5 dollars')
        recs, _ = self.six_trips(1, [])                           # 5 losers and ONE winner: net minus the class dollars would be that trade
        for k in range(5):
            recs += self.fee_only(k)
        out = self.run_day(recs)
        self.assertRegex(out, r'class FEE_ONLY trips 5')
        self.assertNotRegex(out, r'class FEE_ONLY trips 5 dollars')

    def test_a_failed_public_join_for_most_trips_exits_three_and_is_counted(self):
        from lossreview import paths
        ef, xf = fees.taker_fee(20, 0.50), fees.taker_fee(20, 0.62)
        d, ad = self.day([heat_entry(0), fill(1, 'bid', 0.50, 20), plan_event(300, 'plan_ratchet_sell', 0.62), fill(302, 'ask', 0.62, 20, coid='c2'),
                          closed(310, 'yes', round(20 * 0.12 - ef - xf, 6))])
        keep = paths._get
        paths._get = lambda url, tries: {'error': 'HTTP 403'}        # the public endpoints refuse the runner
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = nightly.main(['--day', '2026-11-12', '--audit-dir', ad, '--out', os.path.join(d, 'out')])
        finally:
            paths._get = keep
        self.assertEqual(rc, 3)
        self.assertIn('"fetch_errors"', buf.getvalue())

    def test_a_quiet_day_still_writes_its_files(self):
        # records exist (a plan event of another market) but no heat trip closed
        d, ad = self.day([plan_event(10, 'plan_ratchet_sell', 0.6)])
        rows, s = nightly.run('2026-11-12', ad, os.path.join(d, 'out'), net=False)
        self.assertEqual(rows, [])
        for f in ('trips-2026-11-12.jsonl', 'agg-2026-11-12.json', 'report-2026-11-12.md'):
            self.assertTrue(os.path.exists(os.path.join(d, 'out', f)), f)


if __name__ == '__main__':
    unittest.main()
