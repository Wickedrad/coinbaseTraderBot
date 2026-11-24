"""Synthetic only; must be supplemented by TypeScript parity tests before binding grading."""
import json
import unittest
from datetime import date, timedelta
from ralph.window_core import (taker_fee, exit_level, score_entry,
                               candidate_scores, aggregate_public)
from ralph.j22_scoreboard import make_report


def quotes(hi_segments=(), gap=(), side='yes', until=810000):
    xs = []
    for t in range(0, until+1, 10000):
        if t in gap:
            continue
        elevated = any(lo <= t <= high for lo, high in hi_segments)
        if side == 'yes':
            yb, ya = (0.56, 0.58) if elevated else (0.48, 0.50)
        else:
            yb, ya = (0.42, 0.44) if elevated else (0.50, 0.52)
        xs.append({'t_ms':t,'yb':yb,'ya':ya,'ybs':30,'yas':30})
    return xs


class DirectionTests(unittest.TestCase):
    def setUp(self):
        self.market = {'ticker':'PRIVATE','kind':'15m','close_ms':900_000,'tick':0.01}

    def test_fee_is_35_cents_at_50c_20_contracts(self):
        self.assertAlmostEqual(taker_fee(20,0.5),0.35)
        self.assertAlmostEqual(taker_fee(0,0.5),0.0)

    def test_exit_level_pays_both_fees_and_one_cent_per_contract(self):
        self.assertEqual(exit_level(0.50,20,self.market),0.55)

    def test_60s_real_yes_window_passes(self):
        xs=quotes([(30_000,180_000)])
        o=score_entry(self.market,xs,[x['t_ms'] for x in xs],'yes',0)
        self.assertEqual(o.status,'scored')
        self.assertTrue(o.hit)
        self.assertTrue(o.depth_hit)

    def test_60s_real_no_window_passes(self):
        xs=quotes([(30_000,180_000)],side='no')
        o=score_entry(self.market,xs,[x['t_ms'] for x in xs],'no',0)
        self.assertEqual(o.status,'scored')
        self.assertTrue(o.hit)

    def test_short_bursts_do_not_pass(self):
        xs=quotes([(30_000,50_000),(90_000,110_000)])
        self.assertFalse(score_entry(self.market,xs,[x['t_ms'] for x in xs],'yes',0).hit)

    def test_incomplete_capture_never_becomes_a_negative(self):
        xs=quotes([(30_000,180_000)],until=730_000)
        o=score_entry(self.market,xs,[x['t_ms'] for x in xs],'yes',0)
        self.assertEqual(o.status,'incomplete')
        self.assertIsNone(o.hit)

    def test_first_quote_must_arrive_in_20s(self):
        xs=[x for x in quotes() if x['t_ms']>=30_000]
        o=score_entry(self.market,xs,[x['t_ms'] for x in xs],'yes',0)
        self.assertEqual(o.status,'no-book')

    def test_missing_grid_is_not_assumed_one_cent(self):
        self.assertIsNone(exit_level(0.5,20,{'kind':'15m','close_ms':900000}))

    def test_public_results_do_not_include_private_tickers_or_calls(self):
        rows=[{'status':'scored','day':'2026-11-13','asset':'BTC','side':'yes','kind':'15m',
               'slot_ms':i*900000,'ticker':'PRIVATE_TICKER','call_key':'SECRET',
               'called_window':True,'opposite_window':False,'to_window_ms':10_000,'dip':-0.02}
              for i in range(8)]
        pub=json.dumps(aggregate_public(rows,{}))
        self.assertNotIn('PRIVATE_TICKER',pub)
        self.assertNotIn('SECRET',pub)

    def test_12_day_scoreboard_requires_complete_days(self):
        start=date.fromisoformat('2026-11-20')
        days=[(start+timedelta(days=i)).isoformat() for i in range(12)]
        rows=[]
        for i,d in enumerate(days):
            for j in range(5):
                rows.append({'status':'scored','day':d,'asset':'BTC','kind':'15m','side':'yes',
                             'source_mode':'forward','regime':'calm','slot_ms':i*86_400_000+j*900_000,
                             'called_window':i<9,'opposite_window':i>=9})
        ok=make_report(rows,{'full_days':days},days[0])
        self.assertEqual(ok['daily_positive'],9)
        self.assertTrue(ok['positive_days_condition'])
        self.assertEqual(ok['status'],'diagnostic_only')
        under=make_report(rows,{'full_days':days[:-1]},days[0])
        self.assertIsNone(under['positive_days_condition'])
        self.assertEqual(under['status'],'underpowered_or_missing_capture')


if __name__=='__main__':
    unittest.main()