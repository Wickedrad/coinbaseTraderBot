"""Run: PYTHONPATH=python python3 -m unittest discover -s python/lossreview/tests

LOSSREVIEW_TRIPS=<trips-joined.csv> adds the regression on the Nov 12 file (the file is per-trade data and is not in the repo).
"""
import csv
import os
import unittest

from lossreview import fees, ledger, schema, triage


def row(**kw):
    """A heat trip row with the columns the triage reads; override per test."""
    r = {'ticker': 'KXBTC15M-T', 'kind': '15m', 'coin': 'BTC', 'side': 'yes', 'pnl': '-2.00', 'settled': 'False',
         'plan_price': '0.50', 'entry_px': '0.50', 'count': '20', 'stake': '10.0', 'exit_event': 'plan_loser_cut_sell',
         'side_settles_win': 'False', 'best_bid_held': '0.52', 'call_kind': 'single', 'frac_elapsed_at_entry': '0.2',
         'entry_utc': '11-12 01:00:00', 'closed_utc': '11-12 01:10:00'}
    r.update(kw)
    return r


def pnl_sold(count, e, x):
    return fees_net(count, e, x)


def fees_net(count, e, x):
    return fees.net_if_sold(count, e, fees.taker_fee(count, e), x)


class FeeTests(unittest.TestCase):
    def test_taker_fee_rounds_up_to_the_cent(self):
        self.assertAlmostEqual(fees.taker_fee(58, 0.17), 0.58)  # 0.5729
        self.assertAlmostEqual(fees.taker_fee(10, 0.50), 0.18)  # 0.175
        self.assertAlmostEqual(fees.taker_fee(1, 0.50), 0.02)   # 0.0175

    def test_no_fee_at_the_edges(self):
        self.assertEqual(fees.taker_fee(10, 0.0), 0.0)
        self.assertEqual(fees.taker_fee(10, 1.0), 0.0)
        self.assertEqual(fees.taker_fee(0, 0.5), 0.0)

    def test_implied_exit_recovers_a_sale(self):
        count, e = 13, 0.76
        ef = fees.taker_fee(count, e)
        pnl = fees.net_if_sold(count, e, ef, 0.62)
        x, xf, res = fees.implied_exit(count, e, ef, pnl, False, False)
        self.assertAlmostEqual(x, 0.62)
        self.assertAlmostEqual(res, 0.0)
        self.assertAlmostEqual(xf, fees.taker_fee(count, 0.62))

    def test_settlement_has_no_exit_fee(self):
        count, e = 58, 0.17
        ef = fees.taker_fee(count, e)
        pnl = count * (0 - e) - ef
        x, xf, res = fees.implied_exit(count, e, ef, pnl, True, False)
        self.assertEqual((x, xf), (0.0, 0.0))
        self.assertAlmostEqual(res, 0.0)


class ClassTests(unittest.TestCase):
    def cls(self, **kw):
        return triage.classify(row(**kw))['primary']

    def test_a_winner_is_a_win(self):
        self.assertEqual(self.cls(pnl='1.5', side_settles_win='True'), 'WIN')

    def test_fee_only(self):
        # sold 1c above entry: gross +20c, fees take it below zero
        count, e, x = 20, 0.50, 0.51
        pnl = fees_net(count, e, x)
        self.assertLess(pnl, 0)
        self.assertEqual(self.cls(pnl=str(round(pnl, 2)), side_settles_win='True', exit_event='plan_ratchet_sell'), 'FEE_ONLY')

    def test_cut_then_won_and_sold_then_won(self):
        pnl = str(round(fees_net(20, 0.50, 0.40), 2))
        self.assertEqual(self.cls(pnl=pnl, side_settles_win='True', exit_event='plan_loser_cut_sell'), 'CUT_THEN_WON')
        self.assertEqual(self.cls(pnl=pnl, side_settles_win='True', exit_event='plan_ratchet_sell'), 'SOLD_THEN_WON')

    def test_right_then_reversed_needs_a_bid_that_clears_both_fees(self):
        pnl = str(round(fees_net(20, 0.50, 0.40), 2))
        self.assertEqual(self.cls(pnl=pnl, best_bid_held='0.62'), 'RIGHT_THEN_REVERSED')
        self.assertEqual(self.cls(pnl=pnl, best_bid_held='0.52'), 'WRONG_SIDE')

    def test_sampled_bids_stand_in_for_a_missing_best_bid(self):
        pnl = str(round(fees_net(20, 0.50, 0.40), 2))
        r = triage.classify(row(pnl=pnl, best_bid_held='', bid_2m='0.60'))
        self.assertEqual(r['primary'], 'RIGHT_THEN_REVERSED')
        r = triage.classify(row(pnl=pnl, best_bid_held='', bid_2m='0.45'))
        self.assertEqual(r['primary'], 'WRONG_SIDE')
        self.assertIn('reach_unproven', r['tags'])
        r = triage.classify(row(pnl=pnl, best_bid_held=''))
        self.assertEqual(r['primary'], 'UNKNOWN_DATA')

    def test_flags_and_other_lanes(self):
        self.assertEqual(self.cls(fidelity_flag='true'), 'FIDELITY')
        self.assertEqual(self.cls(lane='old_pricer'), 'OTHER_LANE')

    def test_a_settled_winner_cannot_lose(self):
        self.assertEqual(self.cls(settled='True', side_settles_win='True', exit_event='settled', pnl='-0.50'), 'UNEXPLAINED')

    def test_missing_outcome_is_unknown_data(self):
        pnl = str(round(fees_net(20, 0.50, 0.40), 2))
        self.assertEqual(self.cls(pnl=pnl, side_settles_win=''), 'UNKNOWN_DATA')

    def test_loser_dollars_go_to_one_class_only(self):
        rows = [row(pnl=str(round(fees_net(20, 0.50, 0.40), 2)), best_bid_held=b, side_settles_win=w)
                for b in ('0.62', '0.52') for w in ('True', 'False')]
        cl = [triage.classify(r) for r in rows]
        t = ledger.summarize(rows, cl)
        self.assertAlmostEqual(sum(c['dollars'] for c in t['classes']), t['loser_dollars'])
        self.assertEqual(sum(c['trips'] for c in t['classes']), t['losers'])


class SchemaTests(unittest.TestCase):
    def test_outcome_columns_cannot_be_features(self):
        for col in ('pnl', 'won', 'exit_event', 'best_bid_held', 'side_settles_win', 'bid_2m', 'spot_entry',
                    'spot_vs_strike_bps', 'spot_bps_5m_for_side', 'result'):
            self.assertFalse(schema.validate_feature(col)[0], col)

    def test_clean_columns_pass_and_curve_columns_are_flagged(self):
        self.assertEqual(schema.validate_feature('spot_vs_strike_bps_pre'), (True, 'ok'))
        self.assertEqual(schema.validate_feature('entry_px'), (True, 'ok'))
        self.assertEqual(schema.validate_feature('rank'), (True, 'curve edit'))
        self.assertFalse(schema.validate_feature('not_a_column')[0])

    def test_curve_columns_are_registered(self):
        self.assertTrue(schema.CURVE_COLUMNS <= set(schema.COLUMNS))

    def test_blocks_split_by_availability(self):
        a, o = schema.blocks({'rank': 3, 'pnl': -1, 'spot_pre_entry': 1.0, 'bid_5m': 0.4})
        self.assertEqual(sorted(a), ['rank', 'spot_pre_entry'])
        self.assertEqual(sorted(o), ['bid_5m', 'pnl'])


class InputCheckTests(unittest.TestCase):
    def test_a_yes_price_on_a_no_buy_is_caught(self):
        good = row(side='no', plan_price='0.67', entry_px='0.33', count='30', stake='10.0', ticker='A')
        bad = row(side='no', plan_price='0.67', entry_px='0.67', count='14', stake='10.0', ticker='B')
        self.assertEqual(ledger.check_no_price([good, bad]), ['B'])

    def test_stake_must_be_explained_by_count_times_price(self):
        ok = row(count='20', entry_px='0.50', stake='10.0', ticker='A')
        off = row(count='20', entry_px='0.33', stake='10.0', ticker='B')  # a NO buy priced as if YES would differ
        self.assertEqual(ledger.check_stake([ok, off]), ['B'])


@unittest.skipUnless(os.environ.get('LOSSREVIEW_TRIPS'), 'set LOSSREVIEW_TRIPS to the Nov 12 trips-joined.csv')
class Nov12Regression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.environ['LOSSREVIEW_TRIPS'], newline='', encoding='utf-8') as fh:
            cls.rows = list(csv.DictReader(fh))
        cls.cl = [triage.classify(r) for r in cls.rows]
        cls.t = ledger.summarize(cls.rows, cls.cl)

    def test_totals_match_the_corrected_loser_study(self):
        t = self.t
        self.assertEqual(t['trips'], 203)
        self.assertAlmostEqual(t['net'], -235.58, places=2)
        self.assertAlmostEqual(t['entry_fees'], 108.48, places=2)   # the study's entry fees
        self.assertAlmostEqual(t['fees'], 209.6, delta=1.0)          # fees $209 on every trip
        self.assertAlmostEqual(t['gross'], -26.0, delta=1.0)         # about -$26 before fees
        self.assertEqual(t['losers'], 99)
        self.assertAlmostEqual(t['loser_dollars'], -437.24, places=2)

    def test_fee_only_losers(self):
        c = {x['class']: x for x in self.t['classes']}
        self.assertEqual(c['FEE_ONLY']['trips'], 13)
        self.assertAlmostEqual(c['FEE_ONLY']['dollars'], -6.79, places=2)

    def test_inputs_are_clean(self):
        self.assertEqual(ledger.check_stake(self.rows), [])
        self.assertEqual(ledger.check_no_price(self.rows), [])


if __name__ == '__main__':
    unittest.main()
