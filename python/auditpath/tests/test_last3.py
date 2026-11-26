import contextlib
import io
import json
import math
import os
import tempfile
import unittest
from unittest import mock

import numpy as np

from auditpath import last3 as L
from lossreview.fees import taker_fee

DAY = '2026-11-11'
OPEN_S = 1000


def idx_wave(base=100.0):
    """A one-second index that alternates by one: every one-second change is +1 or -1, so sigma is about 1 and all seconds are valid."""
    t = np.arange(L.DAY)
    return base + (t % 2).astype(float)


def block(ask=0.40, bid=0.38, asz=None, bsz=None, strike=99.0, result=1.0, day=DAY, open_s=OPEN_S, idx=None, coin=0, nw=1):
    """One coin's block with nw identical windows. The sizes alternate by one each second so that the book never counts as stale unless asked."""
    t = np.arange(L.WIN)
    asz = (100.0 + t % 2) if asz is None else asz
    bsz = (100.0 + t % 2) if bsz is None else bsz

    def mat(x):
        x = np.asarray(x, float)
        return np.tile(x if x.ndim else np.full(L.WIN, float(x)), (nw, 1))
    dms = L.day_ms_of(day)
    return {'coin': coin, 'day': day, 'open_ms': np.array([dms + (open_s + 900 * i) * 1000 for i in range(nw)], np.int64),
            'open_s': np.array([open_s + 900 * i for i in range(nw)], np.int64), 'strike': np.full(nw, strike), 'result': np.full(nw, result),
            'bid': mat(bid), 'ask': mat(ask), 'bsz': mat(bsz), 'asz': mat(asz), 'idx': idx_wave() if idx is None else idx}


def write_grid(path, day, windows=4, result=1.0, strike=99.0):
    """A grid file in the layout of subminute.grid.save: every coin has `windows` windows."""
    dms = L.day_ms_of(day)
    z = {}
    t = np.arange(L.WIN)
    for c in L.COINS:
        z[f'{c}__open_ms'] = np.array([dms + (OPEN_S + 900 * i) * 1000 for i in range(windows)], np.int64)
        z[f'{c}__strike'] = np.full(windows, strike)
        z[f'{c}__result'] = np.full(windows, result)
        for k, v in (('bid', 0.38), ('ask', 0.40), ('bsz', 100.0), ('asz', 100.0)):
            z[f'{c}__{k}'] = np.tile(v + (t % 2) * (0.0 if k in ('bid', 'ask') else 1.0), (windows, 1))
        z[f'{c}__idx'] = idx_wave(100.0)
    np.savez_compressed(path, **z)


class OddsTest(unittest.TestCase):
    def test_pair_sum_by_hand(self):
        self.assertEqual(L.pair_min_sum([1, 2]), 5.0)                      # (1,1)=1 (1,2)=1 (2,1)=1 (2,2)=2
        self.assertEqual(L.pair_min_sum([1]), 1.0)
        self.assertEqual(L.pair_min_sum(range(1, 61)), 60 * 61 * 121 / 6)  # s = 839: the closed form n(n+1)(2n+1)/6

    def test_pair_sum_against_brute_force(self):
        d = [10, 11, 12, 13]
        brute = sum(min(a, b) for a in d for b in d)
        self.assertEqual(L.pair_min_sum(d), brute)

    def test_variance_factor_before_and_inside_the_final_minute(self):
        self.assertAlmostEqual(L.variance_factor(897), 5 / 3600)
        self.assertAlmostEqual(L.variance_factor(898), 1 / 3600)
        self.assertEqual(L.variance_factor(899), 0.0)
        self.assertAlmostEqual(L.variance_factor(839), 73810 / 3600)
        d = list(range(840 - 800, 900 - 800))                               # s = 800: the seconds 840..899 are 40..99 away
        self.assertAlmostEqual(L.variance_factor(800), sum(min(a, b) for a in d for b in d) / 3600)

    def test_variance_matches_a_simulation(self):
        rng = np.random.default_rng(7)
        for s in (780, 860, 890):
            steps = rng.standard_normal((100000, 899 - s))
            path = np.cumsum(steps, axis=1)                                 # path[:, k] is the walk k + 1 seconds after s
            fut = [j for j in range(max(840, s + 1), 900)]
            avg = path[:, [j - s - 1 for j in fut]].sum(1) / 60.0
            self.assertAlmostEqual(float(avg.var()) / L.variance_factor(s), 1.0, delta=0.03)

    def test_all_sixty_seconds_known(self):
        self.assertEqual(L.p_yes(60 * 100.0, 100.0, 899, 1.0, 100.0), 1.0)
        self.assertEqual(L.p_yes(60 * 100.0, 100.0, 899, 1.0, 100.5), 0.0)

    def test_symmetric_case_is_one_half(self):
        self.assertAlmostEqual(L.p_yes(0.0, 100.0, 800, 2.0, 100.0), 0.5)
        self.assertAlmostEqual(L.p_yes(58 * 100.0, 100.0, 897, 2.0, 100.0), 0.5)

    def test_one_standard_deviation_by_hand(self):
        sd = 1.0 * math.sqrt(5 / 3600)
        self.assertAlmostEqual(L.p_yes(58 * 100.0, 100.0, 897, 1.0, 100.0 + sd), 0.15865525, places=6)
        self.assertAlmostEqual(L.p_yes(58 * 100.0, 100.0, 897, 1.0, 100.0 - sd), 0.84134475, places=6)

    def test_vectorised_odds_equal_the_scalar_formula_and_use_nothing_later(self):
        b = block(strike=100.4)
        od = L.window_odds(b)
        self.assertTrue(od['ok'].all())
        raw = b['idx']
        for s in (720, 800, 839, 840, 870, 897):
            j = s - L.S_LO
            t = OPEN_S + s
            ch = raw[t - 599:t + 1] - raw[t - 600:t]
            known = float(raw[OPEN_S + 840:OPEN_S + s + 1].sum()) if s >= 840 else 0.0
            want = L.p_yes(known, raw[t], s, float(np.std(ch, ddof=1)), 100.4)
            self.assertAlmostEqual(float(od['prob'][0, j]), want, places=9)
        later = raw.copy()
        later[OPEN_S + 850:] += 50.0                                        # a change after second 849 must not move the odds at 849 or earlier
        od2 = L.window_odds(block(strike=100.4, idx=later))
        self.assertTrue(np.allclose(od['prob'][0, :850 - L.S_LO], od2['prob'][0, :850 - L.S_LO]))

    def test_sigma_needs_300_valid_seconds(self):
        raw = idx_wave()
        raw[OPEN_S + 100:OPEN_S + 300] = np.nan                            # 600 seconds before second 720 hold only about 400 valid changes
        od = L.window_odds(block(idx=raw))
        self.assertTrue(od["ok"][0, 0])
        raw2 = idx_wave()
        raw2[OPEN_S + 130:OPEN_S + 700] = np.nan                           # almost nothing valid before second 720
        od2 = L.window_odds(block(idx=raw2))
        self.assertFalse(od2['ok'][0, 0])

    def test_no_strike_or_no_result_means_no_odds(self):
        self.assertFalse(L.window_odds(block(strike=np.nan))['ok'].any())
        self.assertFalse(L.window_odds(block(result=np.nan))['ok'].any())


class TradeTest(unittest.TestCase):
    def tab(self, b, delay=1, stake=20.0):
        od = L.window_odds(b)
        return od, L.book_tables(b, od, delay, stake)

    def test_fee_and_edge_arithmetic(self):
        b = block(ask=0.40, bid=0.38, asz=np.full(L.WIN, 100.0), bsz=np.full(L.WIN, 100.0))
        b['asz'][:, ::2] = 101.0
        od, tab = self.tab(b)
        j = 5
        p = float(od['prob'][0, j])
        self.assertEqual(tab['ny'][0, j], 50)                              # floor(20 / 0.40)
        fee = taker_fee(50, 0.40)
        self.assertAlmostEqual(fee, 0.84)
        self.assertAlmostEqual(tab['edge'][0, j], max(p - 0.40 - 0.84 / 50, (1 - p) - 0.62 - taker_fee(32, 0.62) / 32))
        self.assertEqual(tab['nn'][0, j], 32)                              # NO costs 1 - 0.38 = 0.62, floor(20 / 0.62) = 32

    def test_size_limit(self):
        asz = np.full(L.WIN, 7.0)
        asz[::2] = 6.0
        b = block(ask=0.40, asz=asz)
        _, tab = self.tab(b)
        e = (L.S_LO + 1)                                                    # the book one second after s = 720 is second 721 (odd: size 7)
        self.assertEqual(tab['ny'][0, 0], int(asz[e]))
        b2 = block(ask=0.40, asz=np.full(L.WIN, 0.4))                       # less than one contract shown: that side cannot trade
        _, tab2 = self.tab(b2)
        self.assertEqual(tab2['ny'][0, 0], 0)
        self.assertEqual(tab2['ey'][0, 0], -np.inf)

    def test_one_second_delay(self):
        ask = np.full(L.WIN, 0.40)
        ask[721:] = 0.30                                                    # the ask drops at second 721
        b = block(ask=ask, bid=0.20, strike=90.0, result=1.0)               # the odds of YES are about 1: YES is bought as soon as the margin allows
        od = L.window_odds(b)
        f1 = L.fills_of(b, od, L.book_tables(b, od, 1, 20.0), 0)
        f0 = L.fills_of(b, od, L.book_tables(b, od, 0, 20.0), 0)
        self.assertEqual(int(f1['s'][0]), 720)
        self.assertAlmostEqual(float(f1['p'][0]), 0.30)                    # priced from second 721
        self.assertAlmostEqual(float(f0['p'][0]), 0.40)                    # no delay: second 720
        self.assertEqual(int(f1['n'][0]), 66)                               # floor(20 / 0.30)

    def test_net_and_payoff_by_hand(self):
        b = block(ask=0.40, strike=90.0, result=1.0)
        od = L.window_odds(b)
        f = L.fills_of(b, od, L.book_tables(b, od, 1, 20.0), 0)
        n = int(f['n'][0])
        self.assertEqual(n, 50)
        self.assertAlmostEqual(float(f['net'][0]), 50 * (1 - 0.40) - 0.84)
        b = block(ask=0.40, strike=90.0, result=0.0)                        # the same buy loses when Kalshi says NO
        od = L.window_odds(b)
        f = L.fills_of(b, od, L.book_tables(b, od, 1, 20.0), 0)
        self.assertAlmostEqual(float(f['net'][0]), -50 * 0.40 - 0.84)

    def test_buys_no_when_the_odds_favour_no(self):
        b = block(ask=0.70, bid=0.65, strike=130.0, result=0.0)           # the average is far below the strike: NO at 0.35
        od = L.window_odds(b)
        f = L.fills_of(b, od, L.book_tables(b, od, 1, 20.0), 0)
        self.assertEqual(int(f['side'][0]), -1)
        self.assertAlmostEqual(float(f['p'][0]), 0.35)
        self.assertGreater(float(f['net'][0]), 0)

    def test_margin_delays_the_first_second(self):
        ask = np.full(L.WIN, 0.99)
        ask[800:] = 0.30                                                    # no edge before second 800 (the price is too high)
        b = block(ask=ask, bid=0.20, strike=90.0)
        od = L.window_odds(b)
        tab = L.book_tables(b, od, 1, 20.0)
        self.assertEqual(int(L.fills_of(b, od, tab, 0)['s'][0]), 799)      # the book of second 800 is what is bought
        self.assertEqual(len(L.fills_of(b, od, tab, 99)['s']), 0)          # a margin of 99 cents cannot be met

    def test_one_trade_per_window(self):
        b = block(ask=0.40, strike=90.0, nw=3)
        od = L.window_odds(b)
        f = L.fills_of(b, od, L.book_tables(b, od, 1, 20.0), 0)
        self.assertEqual(len(f['s']), 3)

    def test_stale_book_is_skipped(self):
        b = block(ask=0.40, strike=90.0, asz=np.full(L.WIN, 100.0), bsz=np.full(L.WIN, 100.0))   # nothing ever changes: age counts from second 0
        od = L.window_odds(b)
        self.assertEqual(len(L.fills_of(b, od, L.book_tables(b, od, 1, 20.0), 0)['s']), 0)
        asz = np.full(L.WIN, 100.0)
        asz[795:] = 101.0                                                   # one change at second 795: fresh for the next 120 seconds
        b = block(ask=0.40, strike=90.0, asz=asz, bsz=np.full(L.WIN, 100.0))
        od = L.window_odds(b)
        f = L.fills_of(b, od, L.book_tables(b, od, 1, 20.0), 0)
        self.assertEqual(int(f['s'][0]), 794)                               # the first second whose next-second book is 795 old enough to count

    def test_one_sided_and_crossed_books_are_skipped(self):
        for kw in ({'bid': np.nan}, {'ask': np.nan}, {'bid': 0.45, 'ask': 0.40}):
            b = block(strike=90.0, **kw)
            od = L.window_odds(b)
            self.assertEqual(len(L.fills_of(b, od, L.book_tables(b, od, 1, 20.0), 0)['s']), 0, kw)

    def test_a_window_without_strike_index_or_result_is_skipped(self):
        for b in (block(strike=np.nan), block(result=np.nan), block(idx=np.full(L.DAY, np.nan))):
            od = L.window_odds(b)
            self.assertEqual(len(L.fills_of(b, od, L.book_tables(b, od, 1, 20.0), 0)['s']), 0)


class ChooseTest(unittest.TestCase):
    def row(self, m, fills, net):
        return {'margin_cents': m, 'fills': fills, 'net_dollars': net}

    def test_most_net_dollars_among_100_fills(self):
        t = [self.row(0, 300, 5.0), self.row(1, 250, 9.0), self.row(2, 99, 50.0), self.row(3, 120, 9.0), self.row(5, 100, -1.0)]
        self.assertEqual(L.pick_margin(t), 1)                              # 99 fills is under the floor; the tie at 9.0 goes to the smaller margin

    def test_fallback_is_the_most_fills(self):
        t = [self.row(0, 60, -5.0), self.row(1, 80, -9.0), self.row(2, 80, 3.0), self.row(3, 20, 40.0)]
        self.assertEqual(L.pick_margin(t), 1)                              # nobody has 100: the most fills, the smaller margin on a tie

    def run_main(self, args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
            rc = L.main(args)
        return rc, buf.getvalue()

    def test_choose_refuses_later_days_and_writes_the_freeze(self):
        with tempfile.TemporaryDirectory() as d:
            for day in ('2026-11-11', '2026-11-12', '2026-11-19'):
                write_grid(os.path.join(d, f'grid-{day}.npz'), day)
            out = os.path.join(d, 'freeze.json')
            opened = []
            real = np.load

            def spy(path, *a, **k):
                opened.append(os.path.basename(str(path)))
                return real(path, *a, **k)
            with mock.patch.object(np, 'load', spy):
                rc, text = self.run_main(['choose', '--grids', d, '--from', '2026-11-11', '--to', '2026-11-12', '--out', out])
            self.assertEqual(rc, 0, text)
            self.assertEqual(sorted(opened), ['grid-2026-11-11.npz', 'grid-2026-11-12.npz'])   # the later grid is never opened
            with open(out) as fh:
                fz = json.load(fh)
            self.assertEqual(fz['days_used'], ['2026-11-11', '2026-11-12'])
            self.assertEqual(fz['last_day'], '2026-11-12')
            self.assertEqual(set(fz['grid_sha256']), {'grid-2026-11-11.npz', 'grid-2026-11-12.npz'})
            self.assertEqual([r['margin_cents'] for r in fz['table']], list(L.MARGINS))
            self.assertIn(fz['margin_cents'], L.MARGINS)
            self.assertTrue(all(len(v) == 64 for v in fz['grid_sha256'].values()))
            self.assertIn('AUDITPATH last3 {', text)
            self.assertTrue(all(line.startswith('AUDITPATH last3 ') for line in text.strip().splitlines()))

    def test_settlement_rule_mismatch_stops_and_trades_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            write_grid(os.path.join(d, 'grid-2026-11-11.npz'), '2026-11-11', result=0.0)    # the average is above the strike but Kalshi says NO
            out = os.path.join(d, 'freeze.json')
            rc, text = self.run_main(['choose', '--grids', d, '--from', '2026-11-11', '--to', '2026-11-11', '--out', out])
            self.assertEqual(rc, 2)
            self.assertFalse(os.path.exists(out))
            self.assertNotIn('"part": "margin"', text)
            self.assertIn('97%', text)

    def test_settlement_check_counts_matches(self):
        b = block(strike=99.0, result=1.0, nw=1)
        self.assertEqual(L.settlement_check([b])['share'], 1.0)
        b = block(strike=101.0, result=1.0, nw=1)                           # the average is 100.5, under 101: the rule says NO
        self.assertEqual(L.settlement_check([b])['share'], 0.0)


class ScoreTest(unittest.TestCase):
    def freeze(self, d, margin=0, last='2026-11-18'):
        p = os.path.join(d, 'freeze.json')
        with open(p, 'w') as fh:
            json.dump({'margin_cents': margin, 'last_day': last, 'table': [], 'days_used': []}, fh)
        return p

    def test_score_refuses_days_at_or_before_the_last_choosing_day(self):
        with tempfile.TemporaryDirectory() as d:
            write_grid(os.path.join(d, 'grid-2026-11-18.npz'), '2026-11-18')
            fz = self.freeze(d)
            for frm in ('2026-11-18', '2026-11-11'):
                with self.assertRaises(L.Stop):
                    L.score(d, fz, frm, os.path.join(d, 'r.json'))

    def test_score_reads_only_scoring_days_and_the_margin_from_the_freeze(self):
        with tempfile.TemporaryDirectory() as d:
            for day in ('2026-11-18', '2026-11-19', '2026-11-20'):
                write_grid(os.path.join(d, f'grid-{day}.npz'), day)
            fz = self.freeze(d, margin=3)
            opened = []
            real = np.load

            def spy(path, *a, **k):
                opened.append(os.path.basename(str(path)))
                return real(path, *a, **k)
            with mock.patch.object(np, 'load', spy), contextlib.redirect_stdout(io.StringIO()) as buf:
                r = L.score(d, fz, '2026-11-19', os.path.join(d, 'r.json'))
            self.assertEqual(sorted(opened), ['grid-2026-11-19.npz', 'grid-2026-11-20.npz'])
            self.assertEqual(r['margin_cents'], 3)
            self.assertEqual(r['days_scored'], ['2026-11-19', '2026-11-20'])
            self.assertEqual(r['hours'], 48.0)
            self.assertTrue(r['pass_line']['preliminary'] is True)
            self.assertEqual(r['pass_line']['verdict'], 'too thin to decide')       # 8 windows a coin and day: far under 200 fills
            self.assertEqual(set(r['information']), {'book_at_s_plus_0', 'book_at_s_plus_1', 'book_at_s_plus_3'})
            self.assertTrue(all(line.startswith('AUDITPATH last3 ') for line in buf.getvalue().strip().splitlines()))
            self.assertTrue(os.path.exists(os.path.join(d, 'r.json')))

    def fills(self, k=40):
        b = block(ask=0.40, strike=90.0, nw=k)
        b['result'] = (np.arange(k) % 3 != 0).astype(float)                # two windows in three settle YES
        od = L.window_odds(b)
        return b, od, L.fills_of(b, od, L.book_tables(b, od, 1, 20.0), 0)

    def test_bootstrap_is_deterministic_and_matches_the_mean(self):
        b, od, f = self.fills()
        slots = b['open_ms'] + L.WIN * 1000
        a1 = L.slot_bootstrap(slots, f)
        a2 = L.slot_bootstrap(slots, f)
        self.assertEqual(a1, a2)
        self.assertAlmostEqual(a1['mean_cents'], 100.0 * f['net'].sum() / f['n'].sum())
        self.assertAlmostEqual(a1['hi_cents'] - a1['mean_cents'], 1.96 * a1['se_cents'], delta=0.01)
        self.assertEqual(a1['draws'], 2000)
        self.assertNotEqual(L.slot_bootstrap(slots, f, seed=1)['se_cents'], a1['se_cents'])   # a different seed draws differently (the net differs per slot)

    def test_twins_are_deterministic_and_the_favourite_is_the_dearer_side(self):
        _, _, f = self.fills()
        t1, t2 = L.twins(f), L.twins(f)
        self.assertEqual(t1, t2)
        # ask 0.40 and bid 0.38: YES costs 0.40 and NO costs 0.62, so the favourite is NO; the result is YES, so it loses
        self.assertLess(t1['favourite']['net_dollars'], 0)
        self.assertEqual(t1['favourite']['fills'], 40)
        fl = t1['coin_flip_mean_of_20_seeds']
        self.assertEqual(fl['fills'], 40.0)
        self.assertTrue(fl['net_dollars'] < f['net'].sum())

    def test_pass_line_is_evaluated_literally(self):
        st = {'lo_cents': 0.5}
        self.assertEqual(L.pass_line(st, 250, 2.0, ['2026-11-21'])['verdict'], 'pass')
        self.assertEqual(L.pass_line(st, 199, 2.0, ['2026-11-21'])['verdict'], 'too thin to decide')
        self.assertEqual(L.pass_line(st, 250, 0.99, ['2026-11-21'])['verdict'], 'no pass')
        self.assertEqual(L.pass_line({'lo_cents': -0.1}, 250, 2.0, ['2026-11-21'])['verdict'], 'no pass')
        self.assertTrue(L.pass_line(st, 250, 2.0, ['2026-11-19', '2026-11-20'])['preliminary'])
        self.assertFalse(L.pass_line(st, 250, 2.0, ['2026-11-19', '2026-11-20', '2026-11-21'])['preliminary'])

    def test_splits_add_up(self):
        _, _, f = self.fills(10)
        s = L.splits(f)
        for key in s:
            self.assertEqual(sum(v['fills'] for v in s[key].values()), 10, key)


    def test_choose_refuses_days_outside_the_choosing_range(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, 'f.json')
            for frm, to in (('2026-11-11', '2026-11-19'), ('2026-11-10', '2026-11-18')):
                with self.assertRaises(L.Stop):
                    L.choose(d, frm, to, out)
            self.assertFalse(os.path.exists(out))

    def test_edge_windows_are_counted(self):
        blk = {'open_s': np.array([-5, 0, 86400 - 900, 86400 - 899])}
        self.assertEqual(L.edge_windows([blk]), 2)

    def test_small_split_cells_print_no_net(self):
        _, _, f = self.fills(3)
        s = L.splits(f)
        for cell in s['by_day'].values():
            self.assertIsNone(cell['net_dollars'])
            self.assertEqual(cell['fills'], 3)

    def test_favourite_tie_takes_yes(self):
        f = {'py': np.array([0.55]), 'pn': np.array([0.55]), 'ny': np.array([10.0]), 'nn': np.array([10.0]),
             'fy': np.array([0.0]), 'fn': np.array([0.0]), 'res': np.array([1.0]), 'net': np.array([0.0])}
        self.assertEqual(L.twins(f)['favourite']['fills'], 1)
        self.assertGreater(L.twins(f)['favourite']['net_dollars'], 0)


if __name__ == '__main__':
    unittest.main()
