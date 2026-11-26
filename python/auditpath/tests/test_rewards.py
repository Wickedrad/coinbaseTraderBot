import json
import os
import tempfile
import unittest

from auditpath import rewards as R


def prog(market, typ='liquidity', reward_cc=50000, hours=24, target='500.00', series=None, disc=9000):
    return {'id': market, 'market_id': 'm', 'market_ticker': market, 'incentive_type': typ, 'incentive_description': 'x',
            'start_date': '2026-11-25T00:00:00Z', 'end_date': f'2026-11-{25 + hours // 24:02d}T{hours % 24:02d}:00:00Z',
            'period_reward': reward_cc, 'paid_out': False, 'series_ticker': series or '', 'discount_factor_bps': disc,
            'target_size_fp': target}


class RewardsTest(unittest.TestCase):
    def test_coin_and_kind(self):
        self.assertEqual(R.coin_of('KXBTC15M'), 'BTC')
        self.assertEqual(R.coin_of('KXXRPD'), 'XRP')
        self.assertIsNone(R.coin_of('KXDOGE15M'))
        self.assertIsNone(R.coin_of('KXHIGHNY'))
        self.assertEqual(R.kind_of('KXETH15M'), '15-minute')
        self.assertEqual(R.kind_of('KXSOLD'), 'hourly ladder')
        self.assertEqual(R.kind_of('KXBTCMAXY'), 'other crypto')

    def test_series_falls_back_to_the_market_ticker(self):
        self.assertEqual(R.series_of({'market_ticker': 'KXBTC15M-26NOV252145-45'}), 'KXBTC15M')
        self.assertEqual(R.series_of({'series_ticker': 'KXETHD', 'market_ticker': 'zzz'}), 'KXETHD')

    def test_program_row_units(self):
        r = R.program_row(prog('KXBTC15M-A', reward_cc=50000, hours=24))
        self.assertAlmostEqual(r['reward'], 5.0)          # 50,000 centi-cents = $5.00
        self.assertAlmostEqual(r['hours'], 24.0)
        self.assertAlmostEqual(r['per_day'], 5.0)
        self.assertEqual(r['target'], 500.0)

    def test_ceiling_share_and_minimum_payout(self):
        rows = [R.program_row(prog('KXBTC15M-A', reward_cc=50000, target='500.00')),      # $5: 200/500 = $2.00, paid
                R.program_row(prog('KXBTC15M-B', reward_cc=20000, target='500.00')),      # $2: 200/500 = $0.80, under $1: nothing
                R.program_row(prog('KXBTC15M-C', reward_cc=30000, target='100.00')),      # $3: share capped at 1 = $3.00
                R.program_row(prog('KXBTC15M-D', typ='volume', reward_cc=990000))]       # not a liquidity program
        self.assertAlmostEqual(R.ceiling(rows, 200), 5.0)
        self.assertAlmostEqual(R.ceiling(rows, 50), 1.5)   # A: $0.50 no; B: no; C: 50/100 * 3 = $1.50

    def test_verdict_closed_without_crypto_rows(self):
        self.assertTrue(R.verdict({'liq_15m_hourly': 0}, {'liq_15m_hourly': 0}, 200).startswith('CLOSED: no crypto'))
        v = R.verdict({'liq_15m_hourly': 3, 'smallest_target': 1000.0}, {}, 200)
        self.assertTrue(v.startswith('CLOSED: the smallest target size'))
        self.assertTrue(R.verdict({'liq_15m_hourly': 3, 'smallest_target': 150.0}, {}, 200).startswith('NOT CLOSED'))

    def test_main_from_file(self):
        d = {'programs': [prog('KXBTC15M-A'), prog('KXHIGHNY-A', reward_cc=900000), prog('KXDOGE15M-A')], 'upcoming': [],
             'schedules': [{'series_ticker': 'KXETH15M', 'incentive_type': 'liquidity', 'reward': 10000, 'window_days': 0,
                            'target_size_fp': '300.00', 'discount_factor_bps': 9000, 'all_markets': True, 'ends': None, 'description': 'd'}]}
        with tempfile.TemporaryDirectory() as t:
            f, o = os.path.join(t, 'in.json'), os.path.join(t, 'out.json')
            json.dump(d, open(f, 'w'))
            self.assertEqual(R.main(['--from-file', f, '--out', o]), 0)
            out = json.load(open(o))
            self.assertEqual(out['active']['crypto_n'], 1)             # DOGE and weather are not counted
            self.assertEqual(out['active']['liq_15m_hourly'], 1)
            self.assertEqual(out['active']['crypto_schedules'], 1)


if __name__ == '__main__':
    unittest.main()
