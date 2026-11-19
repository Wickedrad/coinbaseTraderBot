"""Trip builder on a synthetic audit day (no real data in the repo). Run: PYTHONPATH=python python3 -m unittest discover -s python/lossreview/tests"""
import unittest

from lossreview import builder, fees, triage
from lossreview.audit import iso_s

T0 = iso_s('2026-11-12T15:05:00.000Z')  # 10:05 EST, 10 minutes before the window closes
TK = 'KXBTC15M-26NOV121015-15'            # closes 10:15 EST = 15:15 UTC


def rec(dt, kind, data):
    return (T0 + dt, kind, data, 0)


def heat_entry(dt, side='yes', price=0.50, count=20):
    return rec(dt, 'heat', {'asset': 'BTC', 'h': 15, 'key': '1m:X=high | 15m:Y=low', 'kind': 'pair', 'dir': 1, 'rank': 8, 'of': 40,
                            'heat': 98.7, 'barClose': (T0 + dt - 31) * 1000, 'fired': 3, 'against': 0, 'context': 'agree',
                            'plan': {'ticker': TK, 'side': side, 'price': price, 'count': count, 'stakeUsd': 10.0, 'weight': 0.47, 'slot': 1}})


def fill(dt, book, yes_price, count, taker=True, coid='c1'):
    side_px = yes_price
    fee = fees.taker_fee(int(count), side_px if book == 'bid' else 1 - yes_price) if taker else 0.0
    return rec(dt, 'fill', {'fill': {'ticker': TK, 'side': book, 'count': count, 'price': yes_price, 'isTaker': taker, 'ts': int((T0 + dt) * 1000)},
                            'fee': fee, 'feeEstimated': False, 'clientOrderId': coid, 'orphan': False})


def plan_event(dt, name, bid=None):
    return rec(dt, 'plan', {'event': name, 'ticker': TK, 'side': 'yes', 'count': 20, 'bid': bid, 'net': -1.0, 'sent': True})


def closed(dt, side, pnl, settled=False):
    return rec(dt, 'heat', {'event': 'closed', 'ticker': TK, 'asset': 'BTC', 'kind': '15m', 'side': side, 'h': 15, 'pnl': pnl,
                            'settled': settled, 'stakeUsd': 10.0, 'trips': 5, 'wins': 2, 'bookPnl': -3.0})


class BuilderTests(unittest.TestCase):
    def one(self, recs):
        trips, skipped = builder.build(sorted(recs, key=lambda r: r[0]))
        self.assertEqual((len(trips), skipped), (1, 0))
        return trips[0]

    def test_yes_trip_sold_by_the_ratchet_clears_the_floor(self):
        ef = fees.taker_fee(20, 0.50)
        xf = fees.taker_fee(20, 0.62)
        pnl = round(20 * 0.12 - ef - xf, 6)
        r = self.one([heat_entry(0), fill(1, 'bid', 0.50, 20), plan_event(300, 'plan_ratchet_sell', 0.62),
                      fill(302, 'ask', 0.62, 20, coid='c2'), closed(310, 'yes', pnl)])
        self.assertEqual(r['exit_event'], 'ratchet')
        self.assertEqual(len(r['legs']), 1)
        self.assertFalse(r['legs'][0]['below_breakeven'])
        self.assertFalse(r['defect_sale'])
        self.assertAlmostEqual(r['pnl_fills'], pnl, places=4)
        self.assertFalse(r['fidelity_flag'])
        self.assertAlmostEqual(r['entry_fee'], ef)
        self.assertAlmostEqual(r['exit_fee'], xf)

    def test_no_trip_uses_the_no_price_and_a_loser_cut_below_cost_is_allowed(self):
        # NO bought at YES price 0.67 = 0.33 for NO; cut sells the NO at 0.25 (YES price 0.75): a bid fill
        ef = fees.taker_fee(30, 0.33)
        xf = fees.taker_fee(30, 0.25)
        pnl = round(30 * (0.25 - 0.33) - ef - xf, 6)
        r = self.one([heat_entry(0, 'no', 0.67, 30), fill(1, 'ask', 0.67, 30), plan_event(200, 'plan_loser_cut_sell', 0.25),
                      fill(201, 'bid', 0.75, 30, coid='c2'), closed(210, 'no', pnl)])
        self.assertAlmostEqual(r['entry_px'], 0.33)
        self.assertEqual(r['exit_event'], 'loser_cut')
        self.assertTrue(r['legs'][0]['below_breakeven'])
        self.assertFalse(r['defect_sale'])  # the loser cut may sell under the round-trip cost
        self.assertAlmostEqual(r['pnl_fills'], pnl, places=4)

    def test_a_ratchet_sale_under_the_floor_is_a_defect(self):
        ef = fees.taker_fee(20, 0.50)
        xf = fees.taker_fee(20, 0.51)
        pnl = round(20 * 0.01 - ef - xf, 6)
        r = self.one([heat_entry(0), fill(1, 'bid', 0.50, 20), plan_event(100, 'plan_ratchet_sell', 0.51),
                      fill(101, 'ask', 0.51, 20, coid='c2'), closed(110, 'yes', pnl)])
        self.assertTrue(r['defect_sale'])
        self.assertLess(r['defect_dollars'], 0)
        self.assertEqual(triage.classify(r)['primary'], 'FEE_ONLY')

    def test_held_to_settlement_gets_the_payout_from_the_result(self):
        ef = fees.taker_fee(30, 0.33)
        pnl = round(30 * (1 - 0.33) - ef, 6)
        r = self.one([heat_entry(0, 'no', 0.67, 30), fill(1, 'ask', 0.67, 30),
                      rec(900, 'settlement', {'ticker': TK, 'result': 'no', 'realized': pnl}), closed(901, 'no', pnl, settled=True)])
        self.assertTrue(r['side_settles_win'])
        self.assertEqual(r['exit_event'], 'settled')
        self.assertAlmostEqual(r['pnl_fills'], pnl, places=4)
        self.assertAlmostEqual(r['exit_px'], 1.0)

    def test_a_logged_pnl_the_fills_do_not_explain_is_flagged(self):
        r = self.one([heat_entry(0), fill(1, 'bid', 0.50, 20), fill(100, 'ask', 0.55, 20, coid='c2'), closed(110, 'yes', -9.0)])
        self.assertTrue(r['fidelity_flag'])
        self.assertEqual(triage.classify(dict(r, pnl=r['pnl']))['primary'], 'FIDELITY')

    def test_a_fill_logged_twice_is_counted_once_and_flagged(self):
        ef = fees.taker_fee(20, 0.50)
        xf = fees.taker_fee(20, 0.62)
        pnl = round(20 * 0.12 - ef - xf, 6)
        buy = fill(1, 'bid', 0.50, 20)
        buy[2]['fill']['tradeId'] = 't1'
        again = fill(2, 'bid', 0.50, 20)
        again[2]['fill']['tradeId'] = 't1'
        r = self.one([heat_entry(0), buy, again, plan_event(300, 'plan_ratchet_sell', 0.62), fill(302, 'ask', 0.62, 20, coid='c2'), closed(310, 'yes', pnl)])
        self.assertEqual(r['count'], 20)
        self.assertEqual(r['dup_fills'], 1)
        self.assertTrue(r['fidelity_flag'])
        self.assertAlmostEqual(r['pnl_fills'], pnl, places=4)

    def test_a_close_without_an_entry_record_is_skipped_not_invented(self):
        trips, skipped = builder.build([fill(1, 'bid', 0.50, 20), closed(110, 'yes', -1.0)])
        self.assertEqual((trips, skipped), ([], 1))

    def test_window_columns_come_from_the_ticker(self):
        r = self.one([heat_entry(0), fill(1, 'bid', 0.50, 20), fill(100, 'ask', 0.55, 20, coid='c2'), closed(110, 'yes', 0.0)])
        self.assertEqual((r['coin'], r['kind']), ('BTC', '15m'))
        self.assertAlmostEqual(r['left_at_entry_s'], 600.0, delta=0.5)
        self.assertAlmostEqual(r['frac_elapsed_at_entry'], 1 / 3.0, delta=0.001)
        self.assertAlmostEqual(r['call_age_s'], 31.0, delta=0.1)

    def test_truncate_at_call(self):
        """The ex-ante block rebuilt from the log cut at the entry equals the one from the whole day."""
        recs = sorted([heat_entry(0), fill(1, 'bid', 0.50, 20), plan_event(300, 'plan_ratchet_sell', 0.62),
                       fill(302, 'ask', 0.62, 20, coid='c2'), closed(310, 'yes', 1.0)], key=lambda r: r[0])
        full = self.one(recs)
        cut = [r for r in recs if r[0] <= T0 + 0.0]            # nothing after the entry record
        ix = builder.index(cut)
        et, ed = ix['entries'][TK][0]
        ante = builder.exante(et, ed, TK, closed={'asset': 'BTC', 'kind': '15m'})
        for k, v in ante.items():
            self.assertEqual(full[k], v, k)


if __name__ == '__main__':
    unittest.main()
