"""Synthetic books only: nothing here reads a capture file."""
import csv
import gzip
import json
import os
import re
import tempfile
import unittest

from allpairs.fees import maker_fee, taker_fee
from exitfill import HORIZONS_S, PRIMARY, UNIT
from exitfill import guard, report
from exitfill.book import Capture, Grid, HeldGrid, Sample, TickerSeries, close_ms, held_book, kind_of, u
from exitfill import build_exits
from exitfill.events import COLUMNS, Exit, load_exits
from exitfill.rules import evaluate, ioc_floor, make_ctx, place, usable, walk_ioc
from exitfill.run import build_rows, coverage, main as run_main

BASE = guard.iso_ms('2026-11-12T00:00:00Z')
T = BASE + 3600000
TICKER = 'KXBTC15M-26NOV112000-00'
BANDS = [{'start': 0.0, 'end': 0.1, 'step': 0.001}, {'start': 0.1, 'end': 0.9, 'step': 0.01}, {'start': 0.9, 'end': 1.0, 'step': 0.001}]


def S(t, k, yb, ya, x=TICKER):
    return Sample(t, k, x, tuple((u(p), float(z)) for p, z in yb), tuple((u(p), float(z)) for p, z in ya))


def mirror(s):
    """The same held-side book seen from the NO side: YES asks are 1 - NO bids."""
    return Sample(s.t, s.k, s.x, tuple((UNIT - p, z) for p, z in s.ya), tuple((UNIT - p, z) for p, z in s.yb))


def scenario(close=T + 600000, extra=()):
    ss = [
        S(T - 9000, T - 8800, [(0.50, 20), (0.49, 40)], [(0.53, 15), (0.54, 30)]),
        S(T + 5000, T + 5200, [(0.50, 20)], [(0.53, 15)]),
        S(T + 15000, T + 15200, [(0.52, 12)], [(0.53, 15)]),
        S(T + 25000, T + 25200, [(0.53, 30), (0.52, 12)], [(0.54, 30)]),
        S(T + 35000, T + 35200, [(0.50, 10)], [(0.52, 5)]),
        S(T + 55000, T + 55200, [(0.51, 40), (0.50, 10)], [(0.53, 20)]),
        S(T + 75000, T + 75200, [(0.51, 40)], [(0.53, 20)]),
        S(T + 95000, T + 95200, [(0.51, 40)], [(0.53, 20)]),
        S(T + 115000, T + 115200, [(0.51, 40)], [(0.53, 20)]),
    ] + list(extra)
    return ss, close


def capture(samples, close, side='yes', kind='15m'):
    ts = TickerSeries(samples if side == 'yes' else samples)
    return Capture({TICKER: ts}, {TICKER: {'ticker': TICKER, 'closeTime': close, 'priceRanges': BANDS, 'kind': kind, 'at': 1}}, {'books_files': 1})


def ex(side='yes', n=10, ref=None, event='plan_ratchet_sell'):
    return Exit(1, TICKER, side, event, T, 'plan_at', float(n), ref, None)


class Guard(unittest.TestCase):
    def req(self, **kw):
        r = {'artifacts': 'heat-shadow-43051376882-9,heat-shadow-43138942198-1', 'from': '2026-11-11T22:55:00Z', 'to': '2026-11-12T13:00:00Z', 'readlog': '10ag', 'run': '1'}
        r.update(kw)
        return r

    def test_ok(self):
        out = guard.check_request(self.req())
        self.assertEqual(len(out['artifacts']), 2)

    def test_floor(self):
        with self.assertRaises(guard.FloorViolation):
            guard.check_request(self.req(**{'from': '2026-11-10T03:43:00Z'}))

    def test_needs_readlog_and_run(self):
        for k in ('readlog', 'run'):
            r = self.req()
            del r[k]
            with self.assertRaises(guard.FloorViolation):
                guard.check_request(r)

    def test_bad_artifact_and_doge_and_long_window(self):
        with self.assertRaises(guard.FloorViolation):
            guard.check_request(self.req(artifacts='heat-shadow-1-1,../etc'))
        with self.assertRaises(guard.FloorViolation):
            guard.check_request(self.req(artifacts='heat-shadow-1-1', readlog='10ag', note='KXDOGE15M'))
        with self.assertRaises(guard.FloorViolation):
            guard.check_request(self.req(to='2026-11-15T13:00:00Z'))

    def test_exit_floor_and_doge(self):
        with self.assertRaises(guard.FloorViolation):
            guard.check_ts(guard.FLOOR_MS - 1)
        with self.assertRaises(guard.FloorViolation):
            guard.check_ticker('KXDOGE15M-26NOV112000-00')


class Book(unittest.TestCase):
    def test_no_side_mirror(self):
        s = S(0, 0, [(0.50, 20), (0.49, 40)], [(0.53, 15), (0.54, 30)])
        no = held_book(s, 'no')
        self.assertEqual(no.bids, ((4700, 15.0), (4600, 30.0)))     # NO bid = 1 - YES ask, high to low
        self.assertEqual(no.asks, ((5000, 20.0), (5100, 40.0)))
        self.assertEqual(held_book(s, 'yes').bids[0], (5000, 20.0))

    def test_grid_steps(self):
        g = Grid.from_market({'priceRanges': BANDS})
        self.assertEqual((g.step_above(5000), g.step_below(5000)), (100, 100))
        self.assertEqual((g.step_above(900), g.step_below(1000)), (10, 10))
        self.assertEqual((g.step_above(9500), g.step_below(9500)), (10, 10))
        hg = HeldGrid(g, 'no')
        self.assertEqual((hg.up(9500), hg.down(9500)), (10, 10))       # NO 0.95 is YES 0.05, fine ticks
        self.assertEqual(Grid.from_market({'tickSize': 0.01}).step_above(5000), 100)

    def test_close_and_kind(self):
        self.assertEqual(close_ms('KXBTC15M-26NOV111815-15'), guard.iso_ms('2026-11-11T23:15:00Z'))
        self.assertEqual(close_ms('KXBTCD-26NOV1118-T75000'), guard.iso_ms('2026-11-11T23:00:00Z'))
        self.assertIsNone(close_ms('KXBTC15M-26JUL111815-15'))      # summer offset not guessed
        self.assertEqual((kind_of('KXBTC15M-26NOV111815-15'), kind_of('KXBTCD-26NOV1118-T75000')), ('15m', 'hourly'))

    def test_no_lookahead_in_lookups(self):
        ts = TickerSeries([S(100, 200, [(0.5, 1)], []), S(300, 900, [(0.5, 1)], []), S(400, 450, [(0.5, 1)], [])])
        self.assertEqual(ts.last_k_at_or_before(500), 2)
        self.assertEqual(ts.last_k_at_or_before(300), 0)              # the sample requested at 300 ended at 900: not known yet
        self.assertEqual([x.t for x in ts.evidence(350, 1000)], [400])
        self.assertEqual(ts.last_k_at_or_before(50), -1)


class Walk(unittest.TestCase):
    def test_per_level_fees(self):
        w = walk_ioc(((5000, 5.0), (4900, 5.0), (4000, 99.0)), 10, 4900)
        self.assertAlmostEqual(w.proceeds, 5 * 0.50 + 5 * 0.49)
        self.assertAlmostEqual(w.fee, float(taker_fee(5, 0.50)) + float(taker_fee(5, 0.49)))
        self.assertEqual(w.short, 0.0)

    def test_floor_stops_and_shortfall_is_zero_proceeds(self):
        w = walk_ioc(((5000, 4.0), (4800, 50.0)), 10, 4900)
        self.assertAlmostEqual(w.sold, 4.0)
        self.assertAlmostEqual(w.short, 6.0)
        self.assertAlmostEqual(w.proceeds, 2.0)

    def test_floor_two_ticks(self):
        hg = HeldGrid(Grid.from_market({'priceRanges': BANDS}), 'yes')
        self.assertEqual(ioc_floor(5000, hg), 4800)


class Place(unittest.TestCase):
    def setUp(self):
        self.hg = HeldGrid(Grid.from_market({'priceRanges': BANDS}), 'yes')

    def test_variants(self):
        hb = held_book(S(0, 0, [(0.50, 20)], [(0.53, 15)]), 'yes')
        self.assertEqual((place('JOIN_ASK', hb, self.hg, None).q, place('JOIN_ASK', hb, self.hg, None).queue), (5300, 15.0))
        self.assertEqual(place('INSIDE', hb, self.hg, None).q, 5200)
        self.assertEqual(place('BID_PLUS_1C', hb, self.hg, None).q, 5100)

    def test_not_available(self):
        tight = held_book(S(0, 0, [(0.52, 20)], [(0.53, 15)]), 'yes')
        self.assertIsNone(place('INSIDE', tight, self.hg, None))
        self.assertIsNone(place('BID_PLUS_1C', tight, self.hg, None))
        self.assertIsNotNone(place('JOIN_ASK', tight, self.hg, None))
        self.assertIsNone(place('JOIN_ASK', held_book(S(0, 0, [(0.5, 1)], []), 'yes'), self.hg, None))

    def test_would_have_been_a_taker(self):
        hb = held_book(S(0, 0, [(0.50, 20)], [(0.53, 15)]), 'yes')
        self.assertIsNone(place('INSIDE', hb, self.hg, 5200))     # the bot saw a 0.52 bid: our 0.52 sell would have crossed
        self.assertIsNotNone(place('INSIDE', hb, self.hg, 5100))


class Evaluate(unittest.TestCase):
    def run_h(self, h, side='yes', n=10, ref=None, extra=(), close=None):
        ss, c = scenario(extra=extra)
        if side == 'no':
            ss = [mirror(x) for x in ss]
        cap = capture(ss, close or c, side)
        ctx, why = make_ctx(ex(side, n, ref), cap)
        self.assertIsNone(why)
        return ctx, evaluate(ctx, h)

    def test_golden_inside_strict_30(self):
        ctx, r = self.run_h(30)
        a, i = r[('INSIDE', 'strict')], r['ioc']
        self.assertAlmostEqual(i.net0, 10 * 0.50 - float(taker_fee(10, 0.50)))
        self.assertAlmostEqual(a.proceeds, 5.2)
        self.assertAlmostEqual(a.fee0, 0.0)
        self.assertAlmostEqual(a.fee1, float(maker_fee(10, 0.52, 1.0)))
        self.assertAlmostEqual(a.net0 - i.net0, 0.2 + float(taker_fee(10, 0.50)))
        self.assertEqual((a.delay_ms, a.bracket_ms, a.rest_filled, a.short), (25200, 10200, 10.0, 0.0))
        self.assertFalse(a.pre_cross)

    def test_wait_placebo_30(self):
        ctx, r = self.run_h(30)
        self.assertAlmostEqual(r['wait'].proceeds, 5.3)
        self.assertAlmostEqual(r['wait'].fee0, float(taker_fee(10, 0.53)))

    def test_strict_versus_touch_and_ambiguous(self):
        ctx, r = self.run_h(30)
        js, jt = r[('JOIN_ASK', 'strict')], r[('JOIN_ASK', 'touch')]
        self.assertEqual(js.rest_filled, 0.0)          # bid reached 0.53 but not 0.54
        self.assertTrue(js.ambiguous)                  # the 0.53 ask level disappeared
        self.assertEqual(jt.rest_filled, 10.0)
        self.assertEqual(jt.q_u, 5300)
        self.assertEqual(jt.queue, 15.0)

    def test_bid_plus_one_cent_is_earlier(self):
        ctx, r = self.run_h(30)
        b = r[('BID_PLUS_1C', 'strict')]
        self.assertEqual((b.q_u, b.delay_ms), (5100, 15200))

    def test_fallback_when_unfilled_60(self):
        ctx, r = self.run_h(60)
        js = r[('JOIN_ASK', 'strict')]
        self.assertEqual(js.rest_filled, 0.0)
        self.assertAlmostEqual(js.proceeds, 10 * 0.51)        # fallback book at k <= te is the 55.2 s sample, bid 0.51

    def test_partial_fill_remainder_to_fallback(self):
        ctx, r = self.run_h(30, n=50)
        a = r[('INSIDE', 'strict')]
        self.assertEqual(a.rest_filled, 30.0)                  # only 30 displayed at or above q + 1 tick
        self.assertAlmostEqual(a.proceeds, 30 * 0.52 + 20 * 0.53)   # the other 20 go to the fallback IOC on the 25 s book
        self.assertAlmostEqual(a.fee0, float(taker_fee(20, 0.53)))
        self.assertEqual(a.short, 0.0)

    def test_shortfall_valued_at_zero(self):
        ctx, r = self.run_h(60, n=300)
        for arm in (r['ioc'], r['wait']):
            self.assertGreater(arm.short, 0.0)
        self.assertLess(r['ioc'].proceeds, 300 * 0.50)

    def test_first_sample_cross_is_priced_as_taker(self):
        ss, c = scenario()
        ss[1] = S(T + 5000, T + 5200, [(0.53, 20)], [(0.54, 15)])     # already crossed in the very first evidence sample
        cap = capture(ss, c)
        ctx, _ = make_ctx(ex(), cap)
        r = evaluate(ctx, 30)
        a = r[('INSIDE', 'strict')]
        self.assertTrue(a.pre_cross)
        self.assertAlmostEqual(a.fee0, float(taker_fee(10, 0.52)))

    def test_no_side_gives_identical_numbers(self):
        _, ry = self.run_h(60)
        _, rn = self.run_h(60, side='no')
        for key in ry:
            a, b = ry[key], rn[key]
            if a is None:
                self.assertIsNone(b)
                continue
            for f in ('proceeds', 'fee0', 'fee1', 'short', 'rest_filled', 'delay_ms', 'q_u'):
                self.assertAlmostEqual(getattr(a, f) or 0, getattr(b, f) or 0, msg=f'{key} {f}')

    def test_straddling_sample_is_not_the_placement_book(self):
        ss, c = scenario(extra=[S(T - 100, T + 500, [(0.60, 99)], [(0.62, 99)])])
        ctx, _ = make_ctx(ex(), capture(ss, c))
        self.assertEqual(ctx.s0.yb[0][0], 5000)                # the 0.60 book ended after the decision: not usable

    def test_sample_before_placement_is_not_evidence(self):
        ss, c = scenario(extra=[S(T + 600, T + 900, [(0.60, 99)], [(0.62, 99)])])   # requested before t0 + 1 s slack
        ctx, _ = make_ctx(ex(), capture(ss, c))
        r = evaluate(ctx, 30)
        self.assertEqual(r[('INSIDE', 'strict')].delay_ms, 25200)

    def test_usable_rules(self):
        ctx, _ = self.run_h(60)
        self.assertIsNone(usable(ctx, 60))
        ctx2, _ = self.run_h(60, close=T + 61000 + 4000)
        self.assertEqual(usable(ctx2, 60), 'near_close')
        ss, c = scenario()
        holed = [x for x in ss if x.t not in (T + 25000, T + 35000)]
        ctx3, _ = make_ctx(ex(), capture(holed, c))
        self.assertEqual(usable(ctx3, 60), 'gap')
        stale = [x for x in ss if x.t != T - 9000]
        stale.append(S(T - 40000, T - 39800, [(0.5, 9)], [(0.53, 9)]))
        ctx4, _ = make_ctx(ex(), capture(stale, c))
        self.assertEqual(usable(ctx4, 60), 'gap')

    def test_no_bid_at_decision(self):
        ss, c = scenario()
        ss[0] = S(T - 9000, T - 8800, [], [(0.53, 15)])
        ctx, why = make_ctx(ex(), capture(ss, c))
        self.assertEqual(why, 'no_bid')


class Aggregates(unittest.TestCase):
    def test_wilson_and_bootstrap(self):
        lo, hi = report.wilson(5, 10)
        self.assertAlmostEqual(lo, 0.237, places=2)
        self.assertAlmostEqual(hi, 0.763, places=2)
        m, se = report.mean_se([1.0, 2.0, 3.0, 4.0], [1, 1, 2, 2])
        self.assertAlmostEqual(m, 2.5)
        self.assertEqual((m, se), report.mean_se([1.0, 2.0, 3.0, 4.0], [1, 1, 2, 2]))      # seeded: reproducible

    def test_card_has_no_tickers_times_or_verdict_words(self):
        ss, c = scenario()
        cap = capture(ss, c)
        exits = [ex(), Exit(2, TICKER, 'yes', 'other_sale', T + 1000, 'closed_utc', 8.0, None, None)]
        rows = build_rows(exits, cap)
        meta = {'run': '1', 'hash': 'abc', 'readlog': '10ag', 'from': '2026-11-11T22:55:00Z', 'to': '2026-11-12T13:00:00Z', 'segments': '6'}
        card = report.render_card(meta, coverage(exits, rows), rows)
        self.assertNotIn('KX', card)
        self.assertIsNone(re.search(r'\d{12,}', card))
        self.assertIsNone(re.search(r'\b(pass|passes|passed|fail|fails|failed|gate|verdict|significant)\b', card, re.I))
        self.assertIn('Declared before the first run', card)
        self.assertIn('C12', card)

    def test_coverage_counts(self):
        ss, c = scenario()
        cap = capture(ss, c)
        exits = [ex(), Exit(2, 'KXETH15M-26NOV112000-00', 'yes', 'plan_ratchet_sell', T, 'plan_at', 3.0, None, None)]
        cov = coverage(exits, build_rows(exits, cap))
        self.assertEqual(cov['exits in the list']['ratchet'], 2)
        self.assertEqual(cov['ticker found in the capture']['ratchet'], 1)
        self.assertEqual(cov['usable at 60 s']['ratchet'], 1)


class Events(unittest.TestCase):
    def write(self, rows):
        fd, path = tempfile.mkstemp(suffix='.csv')
        with os.fdopen(fd, 'w', newline='') as fh:
            w = csv.writer(fh)
            w.writerow(COLUMNS)
            w.writerows(rows)
        self.addCleanup(os.remove, path)
        return path

    def test_load_and_validate(self):
        path = self.write([[1, TICKER, 'no', 'plan_ratchet_sell', T, 'plan_at', '12', '0.35', '0.33'], [2, TICKER, 'yes', 'other_sale', T, 'closed_utc', '4.5', '', '']])
        e = load_exits(path)
        self.assertEqual((e[0].ref_bid_u, e[0].limit_u, e[1].ref_bid_u, e[0].etype, e[1].etype), (3500, 3300, None, 'ratchet', 'other_sale'))
        for bad in ([1, 'KXDOGE15M-26NOV112000-00', 'yes', 'other_sale', T, 'x', '1', '', ''],
                    [1, TICKER, 'yes', 'other_sale', guard.FLOOR_MS - 1, 'x', '1', '', ''],
                    [1, TICKER, 'maybe', 'other_sale', T, 'x', '1', '', ''],
                    [1, TICKER, 'yes', 'sell_all', T, 'x', '1', '', '']):
            with self.assertRaises((ValueError, guard.FloorViolation)):
                load_exits(self.write([bad]))

    def test_primary_is_declared(self):
        self.assertEqual(PRIMARY, ('ratchet', 'INSIDE', 60, 'strict'))
        self.assertEqual(HORIZONS_S, (30, 60, 120))


if __name__ == '__main__':
    unittest.main()


class EndToEnd(unittest.TestCase):
    def test_files_to_card(self):
        with tempfile.TemporaryDirectory() as d:
            art = os.path.join(d, 'capture', 'heat-shadow-1-1')
            os.makedirs(art)
            ss, c = scenario()
            rows = [{'t': x.t, 'k': x.k, 'x': x.x, 'yb': [[p / UNIT, z] for p, z in x.yb], 'ya': [[p / UNIT, z] for p, z in x.ya]} for x in ss]
            rows.append(rows[0])                                                       # duplicate row: deduped
            rows.append({'t': T + 1, 'k': T + 2, 'x': 'KXDOGE15M-26NOV112000-00', 'yb': [[0.5, 1]], 'ya': [[0.6, 1]]})   # DOGE: never loaded
            rows.append({'t': BASE - 10 ** 7, 'k': BASE - 10 ** 7 + 1, 'x': TICKER, 'yb': [[0.5, 1]], 'ya': [[0.6, 1]]})  # outside the window
            with gzip.open(os.path.join(art, 'books.jsonl.gz'), 'wt') as fh:
                fh.write('\n'.join(json.dumps(r) for r in rows) + '\n')
            with gzip.open(os.path.join(art, 'markets.jsonl.gz'), 'wt') as fh:
                fh.write(json.dumps({'at': 1, 'ticker': TICKER, 'kind': '15m', 'closeTime': c, 'priceRanges': BANDS}) + '\n')
            with open(os.path.join(art, 'events.jsonl.gz'), 'w') as fh:
                fh.write('not opened\n')
            run = os.path.join(d, 'RUN')
            with open(run, 'w') as fh:
                fh.write('# test\nartifacts=heat-shadow-1-1\nfrom=2026-11-11T22:55:00Z\nto=2026-11-12T13:00:00Z\nreadlog=10ag\nrun=1\n')
            exits = os.path.join(d, 'exits.csv')
            with open(exits, 'w', newline='') as fh:
                w = csv.writer(fh)
                w.writerow(COLUMNS)
                w.writerow([1, TICKER, 'yes', 'plan_ratchet_sell', T, 'plan_at', '10', '0.50', '0.48'])
            out = os.path.join(d, 'card.md')
            self.assertEqual(run_main(['--capture', os.path.join(d, 'capture'), '--out', out, '--run', run, '--exits', exits]), 0)
            card = open(out).read()
            self.assertIn('Heat exit-fill probe', card)
            self.assertIn('| usable at 60 s | 1 | 0 |', card)


class BuildExits(unittest.TestCase):
    LOG = ('2026-11-12T12:40:12Z out: DETAIL plan {"event":"plan_ratchet_sell","ticker":"KXETH15M-26NOV111815-15","side":"no","count":30,"bid":0.35,'
           '"limit":0.33,"at":1794438375726,"since":1794438375726}\n'
           '2026-11-12T12:40:12Z out: DETAIL plan {"event":"plan_ratchet_arm","ticker":"KXETH15M-26NOV111815-15","side":"no","count":30,"bid":0.42,"at":1794438369713}\n'
           'noise line\n')

    def trips(self):
        base = {'ticker': 'KXETH15M-26NOV111815-15', 'side': 'no', 'count': '30'}
        return [dict(base, closed_utc='11-11 23:06:15', exit_event='plan_ratchet_sell', exit_bid='0.35'),
                dict(ticker='KXSOL15M-26NOV111815-15', side='yes', count='17', closed_utc='11-11 23:02:35', exit_event='other_sale', exit_bid=''),
                dict(base, closed_utc='11-11 23:07:00', exit_event='plan_loser_cut_sell', exit_bid='0.2')]

    def test_columns_match_loader(self):
        self.assertEqual(build_exits.COLUMNS, COLUMNS)

    def test_build(self):
        ev = build_exits.parse_plan_sales(self.LOG)
        self.assertEqual(len(ev), 1)                       # arms and noise are not sales
        rows, stats = build_exits.build(self.trips(), ev)
        self.assertEqual((stats['matched'], stats['other_sale'], stats['bid_mismatch'], stats['unused_events']), (1, 1, 0, 0))
        self.assertEqual([r[3] for r in rows], ['other_sale', 'plan_ratchet_sell'])        # sorted by time, loser cut left out
        self.assertEqual(rows[1][4:], [1794438375726, 'plan_at', '30', '0.35', '0.33'])
        self.assertEqual(rows[0][4:], [1794438155000, 'closed_utc', '17', '', ''])
        self.assertEqual(len(rows[0]), len(COLUMNS))
        self.assertEqual(len(set(COLUMNS) & {'entry_px', 'pnl', 'net', 'strike', 'actual_net_usd'}), 0)

    def test_unmatched_trip_is_counted(self):
        rows, stats = build_exits.build(self.trips(), [])
        self.assertEqual((stats['no_event'], len(rows)), (1, 1))
