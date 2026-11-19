"""The anatomy stage: aggregates only, small cells withheld, the hold counterfactual and the day counts."""
import contextlib
import io
import json
import os
import tempfile
import unittest

from lossreview import anatomy, daily


def trip(i, pnl=-1.0, px=0.4, win=False, side='yes', fees=0.5, **over):
    r = {'ticker': 'KXBTC15M-SECRET-%d' % i, 'entry_t': 1700000000 + i, 'pnl': pnl, 'fees': fees, 'entry_fee': fees / 2, 'entry_fill_px': px,
         'count_filled': 10, 'stake_filled': 10 * px, 'side_settles_win': win, 'side': side, 'exit_event': 'loser_cut', 'entry_taker': True,
         'kind': '15m', 'coin': 'BTC', 'hold_s': 100, 'call_age_s': 10, 'fidelity_flag': False}
    r.update(over)
    return r


def write(w, day, rows):
    os.makedirs(os.path.join(w, 'days'), exist_ok=True)
    with open(os.path.join(w, 'days', 'trips-%s.jsonl' % day), 'w') as fh:
        for r in rows:
            fh.write(json.dumps(r) + '\n')


class Anatomy(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.w = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_hold_counterfactual_and_edge(self):
        # 10 contracts at 0.40, entry fee 0.25: a winner held = 10*0.6 - 0.25 = 5.75, a loser held = -10*0.4 - 0.25 = -4.25
        rows = [trip(i, win=(i < 16), fees=0.5) for i in range(40)]
        write(self.w, '2026-11-14', rows)
        c = anatomy.report(self.w)['all']
        self.assertEqual(c['n'], 40)
        self.assertEqual(c['hold'], anatomy._d(16 * 5.75 - 24 * 4.25))     # -10
        self.assertEqual(c['net_h'], -40)
        self.assertEqual(c['win_pct'], 40.0)
        self.assertEqual(c['px_c'], 40.0)
        self.assertEqual(c['edge_c'], 0.0)
        self.assertEqual(c['pre'], -20)            # net -40 plus fees 20
        self.assertEqual(c['fee_pct'], 12.5)       # fees 20 on stake 160

    def test_unresolved_trips_stay_out_of_edge_and_hold_but_not_out_of_net(self):
        rows = [trip(i, win=None) for i in range(10)]
        write(self.w, '2026-11-14', rows)
        c = anatomy.report(self.w)['all']
        self.assertEqual(c['n'], 10)
        self.assertNotIn('win_pct', c)
        self.assertNotIn('hold', c)

    def test_cells_under_the_floor_are_withheld_and_only_counted(self):
        rows = [trip(i, px=0.5) for i in range(15)] + [trip(100 + i, px=0.7) for i in range(12)] + [trip(200 + i, px=0.1) for i in range(9)]
        write(self.w, '2026-11-14', rows)
        rep = anatomy.report(self.w)
        self.assertEqual(sorted(rep['cuts']['px']), ['0.5-0.65'])      # 9 unprinted trips would be subtracted out: the 12-trip cell goes too
        self.assertEqual(rep['suppressed_trips']['px'], 21)
        self.assertEqual(rep['all']['n'], 36)

    def test_nothing_left_unprinted_but_all_or_at_least_the_floor(self):
        import random
        rnd = random.Random(7)
        for k in range(30):
            rows = []
            for i in range(rnd.randint(15, 140)):
                rows.append(trip(k * 1000 + i, pnl=rnd.gauss(-0.3, 2), px=rnd.choice([0.1, 0.3, 0.45, 0.6, 0.75, 0.9]), side=rnd.choice(['yes', 'no']),
                                 exit_event=rnd.choice(['ratchet', 'loser_cut', 'end_rule', 'settled', None]), coin=rnd.choice(['BTC', 'ETH', 'SOL', 'XRP', 'DOGE']),
                                 entry_taker=rnd.choice([True, False, None]), hold_s=rnd.choice([5, 60, 200, 600, 1200, None]), win=rnd.choice([True, False, None])))
            write(self.w, '2026-11-%02d' % (k % 28 + 1), rows)
            rep = anatomy.report(self.w)
            for name, cells in rep['cuts'].items():
                left = rep['all']['n'] - sum(c['n'] for c in cells.values())
                self.assertTrue(left == 0 or left >= anatomy.MIN_CELL, (name, left))
                self.assertEqual(left, rep['suppressed_trips'][name], name)
            self.assertEqual(rep['trips'], sum(d['n'] for d in rep['per_day']))

    def test_neg_days_counts_only_days_with_enough_trips(self):
        write(self.w, '2026-11-12', [trip(i, pnl=-1) for i in range(10)])
        write(self.w, '2026-11-13', [trip(i, pnl=+1) for i in range(10)])
        write(self.w, '2026-11-14', [trip(i, pnl=-5) for i in range(anatomy.DAY_MIN - 1)] + [trip(50 + i, pnl=1, side='no') for i in range(10)])
        rep = anatomy.report(self.w)
        self.assertEqual(rep['cuts']['side']['yes']['neg_days'], '1/2')      # day 3 had only 2 yes trips: not counted
        self.assertEqual(rep['days_used'], 3)

    def test_flagged_and_unscored_trips_stay_out(self):
        rows = [trip(i) for i in range(10)] + [trip(20, fidelity_flag=True), trip(21, pnl=None)]
        write(self.w, '2026-11-14', rows)
        self.assertEqual(anatomy.report(self.w)['all']['n'], 10)

    def test_buckets(self):
        self.assertEqual(anatomy._bucket(0.2, anatomy.PX_EDGES), '0.2-0.35')
        self.assertEqual(anatomy._bucket(0.19, anatomy.PX_EDGES), '<0.2')
        self.assertEqual(anatomy._bucket(0.8, anatomy.PX_EDGES), '>=0.8')
        self.assertEqual(anatomy._bucket(None, anatomy.PX_EDGES), 'unknown')
        self.assertEqual(anatomy._bucket(45, anatomy.HOLD_EDGES, 's'), '30-120s')

    def test_stage_prints_one_aggregate_line_and_no_per_trade_field(self):
        write(self.w, '2026-11-14', [trip(i) for i in range(12)])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = daily.main(['anatomy', '--w', self.w])
        self.assertEqual(rc, 0)
        out = buf.getvalue()
        self.assertEqual(out.count('\n'), 1)
        self.assertTrue(out.startswith('LOSSLOOP anatomy {'))
        for leak in ('SECRET', 'KXBTC15M', 'entry_t', 'ticker', '1700000'):
            self.assertNotIn(leak, out)
        self.assertEqual(json.loads(out[len('LOSSLOOP anatomy '):])['all']['n'], 12)

    def test_resolved_groups_need_the_floor_on_their_own_count(self):
        # 11 unresolved ratchet trips and ONE resolved: the cell has 12 trips but the resolved group must not print
        rows = [trip(i, win=None, exit_event='ratchet') for i in range(11)] + [trip(50, win=False, exit_event='ratchet', pnl=-2.13, px=0.37)]
        rows += [trip(100 + i, win=bool(i % 2), exit_event='settled') for i in range(12)]
        write(self.w, '2026-11-14', rows)
        cell = anatomy.report(self.w)['cuts']['exit']['ratchet']
        self.assertEqual(cell['n'], 12)
        for k in ('n_res', 'win_pct', 'px_c', 'edge_c', 'n_hold', 'hold', 'net_h'):
            self.assertNotIn(k, cell)

    def test_the_unresolved_rest_must_be_empty_or_at_the_floor(self):
        rest_one = [trip(i, win=bool(i % 2)) for i in range(12)] + [trip(50, win=None, pnl=3.41)]
        write(self.w, '2026-11-14', rest_one)
        cell = anatomy.report(self.w)['all']
        self.assertEqual(cell['n'], 13)
        self.assertNotIn('hold', cell)             # net minus net_h would be that one trade
        self.assertIn('win_pct', cell)             # a price and a win share need no such guard
        write(self.w, '2026-11-14', [trip(i, win=bool(i % 2)) for i in range(12)] + [trip(50 + i, win=None) for i in range(10)])
        self.assertIn('hold', anatomy.report(self.w)['all'])
        write(self.w, '2026-11-14', [trip(i, win=bool(i % 2)) for i in range(12)])
        self.assertIn('hold', anatomy.report(self.w)['all'])

    def test_a_short_day_is_left_out_of_everything(self):
        for k in range(5):
            write(self.w, '2026-11-%02d' % (10 + k), [trip(100 * k + i, pnl=-1 - k) for i in range(12)])
        before = anatomy.report(self.w)
        write(self.w, '2026-11-15', [trip(900, pnl=3.41, fees=0.4)])
        after = anatomy.report(self.w)
        self.assertEqual(after['days_short'], 1)
        after['days_short'] = 0
        self.assertEqual(before, after)            # the one-trip day changes no printed number

    def test_every_dollar_sum_is_on_the_grid(self):
        import random
        rnd = random.Random(3)
        for k in range(4):
            write(self.w, '2026-11-%02d' % (10 + k), [trip(1000 * k + i, pnl=round(rnd.gauss(-0.4, 2.2), 2), fees=round(rnd.uniform(0.2, 0.9), 2),
                                                           win=rnd.choice([True, False, None]), px=rnd.choice([0.2, 0.5, 0.7])) for i in range(60)])
        rep = anatomy.report(self.w)
        cells = [rep['all']] + list(rep['per_day']) + [c for cut in rep['cuts'].values() for c in cut.values()]
        seen = 0
        for c in cells:
            for k in ('net', 'fees', 'pre', 'hold', 'net_h'):
                if k in c:
                    seen += 1
                    self.assertEqual(c[k] % anatomy.GRID, 0, (k, c[k]))
        self.assertGreater(seen, 40)

    def test_edge_days_and_hold_days_count_the_days_with_a_positive_edge_and_hold(self):
        # 10 contracts at 0.40 (entry fee 0.25): a held winner is +5.75, a held loser -4.25
        for day, wins in (('2026-11-12', 6), ('2026-11-13', 6), ('2026-11-14', 2), ('2026-11-15', 4)):
            write(self.w, day, [trip(int(day[-2:]) * 100 + i, win=(i < wins)) for i in range(10)])
        # a day at px 0.5 with no fee: 5 of 10 ties the price (edge 0) and holds to exactly 0, neither is positive
        write(self.w, '2026-11-16', [trip(1600 + i, px=0.5, fees=0.0, win=(i < 5)) for i in range(10)])
        c = anatomy.report(self.w)['all']
        # 6 and 6 of 10 beat 40c; 2 of 10 does not; 4 of 10 ties the price; the px 0.5 day ties
        self.assertEqual(c['edge_days'], '2/5')
        # held: +17.5, +17.5, -22.5, -2.5, 0.0
        self.assertEqual(c['hold_days'], '2/5')

    def test_the_day_counts_leave_out_the_days_a_cell_has_under_day_min_trips(self):
        # the 'no' cell: 2 trips (a winning pair, left out), exactly 3 (all win, counts), 5 (all lose)
        for day, n_no, wins in (('2026-11-12', 2, 2), ('2026-11-13', 3, 3), ('2026-11-14', 5, 0)):
            rows = [trip(int(day[-2:]) * 100 + i, side='no', win=(i < wins)) for i in range(n_no)]
            rows += [trip(int(day[-2:]) * 100 + 50 + i, side='yes') for i in range(10 - n_no)]
            write(self.w, day, rows)
        no = anatomy.report(self.w)['cuts']['side']['no']
        self.assertEqual(no['n'], 10)
        self.assertEqual(no['edge_days'], '1/2')
        self.assertEqual(no['hold_days'], '1/2')

    def test_edge_days_count_resolved_trips_and_hold_days_wait_for_the_hold_group(self):
        # the 'no' cell: day A has 4 trips but only 2 resolved (a winning pair), B 5 winners, C 5 losers; 2 trips never resolved
        for day, rows_no in (('2026-11-12', [None, None, True, True]), ('2026-11-13', [True] * 5), ('2026-11-14', [False] * 5)):
            rows = [trip(int(day[-2:]) * 100 + i, side='no', win=w) for i, w in enumerate(rows_no)]
            rows += [trip(int(day[-2:]) * 100 + 50 + i, side='yes') for i in range(10 - len(rows_no))]
            write(self.w, day, rows)
        no = anatomy.report(self.w)['cuts']['side']['no']
        self.assertEqual(no['n'], 14)
        self.assertEqual(no['n_res'], 12)
        self.assertEqual(no['edge_days'], '1/2')                  # day A has 2 resolved trips, under DAY_MIN
        self.assertNotIn('hold', no)                              # the 2 unresolved trips are a handful: the hold group is withheld
        self.assertNotIn('hold_days', no)

    def test_the_day_counts_follow_the_group_they_belong_to(self):
        write(self.w, '2026-11-12', [trip(i, win=None) for i in range(10)])
        c = anatomy.report(self.w)['all']
        self.assertNotIn('edge_days', c)
        self.assertNotIn('hold_days', c)

    def test_empty_folder_gives_an_empty_report(self):
        write(self.w, '2026-11-09', [])
        rep = anatomy.report(self.w)
        self.assertEqual(rep['trips'], 0)
        self.assertEqual(rep['all'], {})


if __name__ == '__main__':
    unittest.main()
