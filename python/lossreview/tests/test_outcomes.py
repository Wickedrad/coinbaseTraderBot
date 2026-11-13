import unittest

from lossreview import outcomes as oc

E0 = 1_000_000 + 30           # entry 30 s into a minute
TRIP = {'side': 'yes', 'entry_t': E0, 'closed_t': E0 + 400, 'pnl': -1.0}


def candle(end, bid_lo, bid_hi, ask_lo, ask_hi):
    return {'end_period_ts': end, 'yes_bid': {'low_dollars': str(bid_lo), 'high_dollars': str(bid_hi), 'close_dollars': str(bid_hi)},
            'yes_ask': {'low_dollars': str(ask_lo), 'high_dollars': str(ask_hi), 'close_dollars': str(ask_lo)}}


CANDLES = [candle(1_000_000 + 60 * i, 0.40 + 0.01 * i, 0.42 + 0.01 * i, 0.44 + 0.01 * i, 0.46 + 0.01 * i) for i in range(1, 9)]
SPOT = [[1_000_000 - 120 + 60 * i, 99.0, 101.0, 100.0, 100.0 + i, 1.0] for i in range(0, 12)]


class OutcomeTests(unittest.TestCase):
    def test_no_side_bid_is_one_minus_the_yes_ask(self):
        c = candle(60, 0.40, 0.42, 0.44, 0.46)
        self.assertAlmostEqual(oc.side_bid(c, 'no', 'high'), 0.56)  # best NO bid: lowest YES ask
        self.assertAlmostEqual(oc.side_bid(c, 'no', 'low'), 0.54)
        self.assertAlmostEqual(oc.side_bid(c, 'yes', 'high'), 0.42)

    def test_cents_fall_back_when_no_dollar_field(self):
        c = {'end_period_ts': 60, 'yes_bid': {'high': 42, 'low': 40, 'close': 41}}
        self.assertAlmostEqual(oc.side_bid(c, 'yes', 'high'), 0.42)

    def test_join_columns(self):
        r = oc.join(TRIP, {'floor_strike': '100.0', 'result': 'no'}, CANDLES, SPOT)
        self.assertEqual(r['result'], 'no')
        self.assertFalse(r['side_settles_win'])
        self.assertIsNotNone(r['best_bid_held'])
        self.assertGreaterEqual(r['best_bid_held'], r['worst_bid_held'])
        self.assertIsNotNone(r['bid_1m'])

    def test_spot_pre_entry_uses_only_closed_minutes_and_ignores_later_rows(self):
        full = oc.join(TRIP, {'floor_strike': 100.0}, CANDLES, SPOT)
        early = [x for x in SPOT if x[0] + 60 <= E0]          # the log cut at the call
        cut = oc.join(TRIP, {'floor_strike': 100.0}, CANDLES, early)
        for k in ('spot_pre_entry', 'spot_pre_age_s', 'spot_vs_strike_bps_pre'):
            self.assertEqual(full[k], cut[k], k)
        self.assertNotEqual(full['spot_entry'], full['spot_pre_entry'])   # the entry minute's close is the leak, kept apart
        self.assertTrue(0 <= full['spot_pre_age_s'] <= 60)

    def test_no_market_leaves_columns_empty(self):
        r = oc.join(TRIP, None, [], [])
        self.assertIsNone(r['strike'])
        self.assertIsNone(r['best_bid_held'])


if __name__ == '__main__':
    unittest.main()
