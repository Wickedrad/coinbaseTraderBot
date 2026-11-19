import datetime as dt
import os
import unittest

import numpy as np

from heatloop import rubric as R

LO = int(dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
HI = int(dt.datetime(2026, 11, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
DAYS = (HI - LO) // R.DAY


def synth(rng, p_unc=0.5, p_conf=0.5, p_inv=0.5, per=4.0, edge_by_coin=None, late=True):
    """Calls from Jul 1 to Oct 31: per coin per day ~Poisson(per); hit with p, a move of 2..9 steps."""
    rows = []
    for coin in ('BTC', 'ETH'):
        for d in range(DAYS):
            for _ in range(rng.poisson(per)):
                rows.append((LO + d * R.DAY + int(rng.integers(0, R.DAY)), coin))
    ts = np.array([r[0] for r in rows], np.int64)
    coin = np.array([r[1] for r in rows])
    n = len(ts)
    conf = rng.random(n) < 0.35
    p = np.where(conf, p_conf, p_unc)
    hit = rng.random(n) < p
    side = np.where(rng.random(n) < 0.5, 1, -1)
    mag = rng.integers(2, 10, size=n).astype(float)
    move = np.where(hit, side, -side) * mag
    move_late = np.where(rng.random(n) < 0.93, move, np.where(rng.random(n) < p - 0.01, side, -side) * mag)
    past = {k: rng.choice([-1, 0, 1], size=n) for k in R.NAIVE_KS}
    calls = R.Calls(ts, coin, side, move, move_late if late else None, past, conf)
    ni = int(0.25 * n)
    its = LO + rng.integers(0, DAYS, size=ni) * R.DAY
    iside = np.where(rng.random(ni) < 0.5, 1, -1)
    ihit = rng.random(ni) < p_inv
    imove = np.where(ihit, iside, -iside) * rng.integers(2, 10, size=ni).astype(float)
    inv = R.Calls(its, np.array(['BTC'] * ni), iside, imove)
    return calls, inv


class Basics(unittest.TestCase):
    def test_right_wrong_flat(self):
        dec, hit = R.right(np.array([1, 1, -1, -1, 1]), np.array([2.0, -2.0, -2.0, 2.0, 1.4]))
        self.assertEqual(dec.tolist(), [True, True, True, True, False])
        self.assertEqual(hit.tolist(), [True, False, True, False, False])

    def test_iso_week_is_monday_start(self):
        mon = int(dt.date(2026, 7, 6).toordinal() - 719163)       # a Monday
        days = np.arange(mon, mon + 7)
        self.assertEqual(set(R.iso_week(days).tolist()), {mon})
        self.assertEqual(int(R.iso_week(np.array([mon - 1]))[0]), mon - 7)

    def test_month_id_changes_at_the_first(self):
        d = int(dt.date(2026, 7, 31).toordinal() - 719163)
        a, b = R.month_id(np.array([d, d + 1]))
        self.assertEqual(b - a, 1)

    def test_cluster_se_is_larger_when_a_day_carries_all_the_wins(self):
        h = np.array([1, 1, 1, 1, 0, 0, 0, 0], float)
        spread = R.cluster_se(h, np.array([0, 1, 2, 3, 0, 1, 2, 3]))
        lumped = R.cluster_se(h, np.array([0, 0, 0, 0, 1, 1, 1, 1]))
        self.assertGreater(lumped, spread)

    def test_bootstrap_is_deterministic(self):
        rng = np.random.default_rng(1)
        h = rng.random(500) < 0.56
        day = rng.integers(0, 60, 500)
        self.assertEqual(R.boot_lower(h, day), R.boot_lower(h, day))
        self.assertNotEqual(R.boot_lower(h, day), R.boot_lower(h, day, seed=1))

    def test_thresholds_match_the_preregistration(self):
        with open(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'research', 'heat_direction', 'PREREG.md')) as f:
            doc = f.read()
        for s in ('>= 55.0%', '> 50.0%', '>= 2.0 points', '>= 53.0%', '>= 65%', '>= 52.0%', '>= 3.0 points', '<= 50.0%',
                  'seed 20261119', '2,000 resamples', '1.5 steps', 'fewer than 20 decided calls', '800 decided calls'):
            self.assertIn(s, doc, s)
        self.assertEqual((R.T['level'], R.T['naive_gap'], R.T['coin'], R.T['week_share'], R.T['side'], R.T['late'], R.T['ta_lift']),
                         (0.55, 0.02, 0.53, 0.65, 0.52, 0.53, 0.03))
        self.assertEqual((R.SEED, R.BOOT, R.FLAT_STEPS, R.FLOORS['pooled'], R.FLOORS['week_calls']), (20261119, 2000, 1.5, 800, 20))


class Scoring(unittest.TestCase):
    def run_one(self, seed, **kw):
        rng = np.random.default_rng(seed)
        calls, inv = synth(rng, **kw)
        return R.score(calls, inv, LO, HI, 'month')

    def test_no_edge_does_not_pass_and_has_ten_checks(self):
        r = self.run_one(1)
        self.assertEqual(len(r['checks']), 10)
        self.assertFalse(r['passed'])
        self.assertLessEqual(r['total'], 3)

    def test_a_real_edge_with_helpful_ta_passes(self):
        r = self.run_one(2, p_unc=0.56, p_conf=0.66, p_inv=0.42)
        self.assertTrue(r['passed'], [(c['name'], c['passed'], c['value']) for c in r['checks']])
        self.assertGreaterEqual(r['total'], 9)

    def test_edge_without_ta_help_does_not_pass(self):
        # a real edge that TA does not improve: the core 8 pass, and the two TA checks pass only by chance
        core, ta9, ta10, passed = [], [], [], []
        for seed in range(30, 50):
            r = self.run_one(seed, p_unc=0.60, p_conf=0.60, p_inv=0.60)
            core.append(r['core8'] == 8)
            ta9.append(r['checks'][8]['passed'])
            ta10.append(r['checks'][9]['passed'])
            passed.append(r['passed'])
        self.assertGreaterEqual(np.mean(core), 0.8)
        self.assertLessEqual(np.mean(ta9), 0.3)
        self.assertEqual(sum(ta10), 0)                      # invalidated calls hit 60%: never <= 50%
        self.assertLessEqual(np.mean(passed), 0.3)          # 9 only when check 9 is lucky; the simulation says about 1 in 10

    def test_no_ta_layer_scores_zero_on_checks_nine_and_ten(self):
        rng = np.random.default_rng(4)
        calls, _ = synth(rng, p_unc=0.6, p_conf=0.6)
        calls.conf = None
        r = R.score(calls, None, LO, HI, 'month')
        self.assertFalse(r['checks'][8]['passed'] or r['checks'][9]['passed'])
        self.assertLessEqual(r['total'], 8)

    def test_required_checks_gate_the_pass(self):
        # all ten pass; then make the best naive rule as good as the candidate: check 3 fails, the other nine pass, the
        # total is 9 and it is still not a pass because check 3 is required
        rng = np.random.default_rng(2)
        calls, inv = synth(rng, p_unc=0.57, p_conf=0.72, p_inv=0.40)
        self.assertEqual(R.score(calls, inv, LO, HI, 'month')['total'], 10)
        calls.past[15] = np.sign(calls.move).astype(int)
        r = R.score(calls, inv, LO, HI, 'month')
        self.assertFalse(r['checks'][2]['passed'])
        self.assertEqual(r['total'], 9)
        self.assertFalse(r['gate'])
        self.assertFalse(r['passed'])

    def test_a_three_point_lift_inside_the_noise_does_not_confirm(self):
        # 200 confirmed calls hit 56%, 600 unconfirmed hit 52%: the lift is 4 points but its 90% cluster bound is below zero
        n_conf, n_unc = 200, 600
        n = n_conf + n_unc
        conf = np.array([True] * n_conf + [False] * n_unc)
        hit = np.zeros(n, bool)
        hit[:n_conf][:112] = True
        hit[n_conf:][:312] = True
        order = np.random.default_rng(0).permutation(n)               # spread over the days
        conf, hit = conf[order], hit[order]
        ts = LO + (np.arange(n) % 100) * R.DAY + 3600_000
        calls = R.Calls(ts, np.where(np.arange(n) % 2 == 0, 'BTC', 'ETH'), np.ones(n, int), np.where(hit, 5.0, -5.0),
                        np.where(hit, 5.0, -5.0), {k: np.zeros(n, int) for k in R.NAIVE_KS}, conf)
        c9 = R.score(calls, None, LO, HI, 'month')['checks'][8]
        self.assertGreaterEqual(c9['value'], 0.03)
        self.assertTrue(c9['floor_ok'])
        self.assertFalse(c9['passed'])

    def test_too_few_calls_scores_zero_never_a_default_pass(self):
        rng = np.random.default_rng(6)
        calls, inv = synth(rng, p_unc=0.7, p_conf=0.7, per=0.4)        # about 100 calls
        r = R.score(calls, inv, LO, HI, 'month')
        self.assertLess(r['n_decided'], 800)
        self.assertEqual(r['total'], 0)

    def test_a_quiet_week_counts_as_failed_not_dropped(self):
        rng = np.random.default_rng(7)
        calls, inv = synth(rng, p_unc=0.62, p_conf=0.62, p_inv=0.62)
        base = R.score(calls, inv, LO, HI, 'month')['checks'][4]
        self.assertTrue(base['passed'], base)
        # silence 40% of the weeks: the surviving weeks are all winners, yet the check must fail
        wk = R.iso_week(calls.day)
        weeks = sorted(set(wk.tolist()))
        quiet = set(weeks[:: 2][: int(0.6 * len(weeks))])
        keep = ~np.isin(wk, list(quiet))
        r = R.score(calls.pick(keep), inv, LO, HI, 'month')['checks'][4]
        self.assertFalse(r['passed'], r)

    def test_a_thin_block_fails_the_blocks_check(self):
        rng = np.random.default_rng(8)
        calls, inv = synth(rng, p_unc=0.62, p_conf=0.62)
        m = R.month_id(calls.day)
        last = m.max()
        drop = (m == last) & (rng.random(len(m)) < 0.97)               # October nearly silent
        r = R.score(calls.pick(~drop), inv, LO, HI, 'month')['checks'][5]
        self.assertFalse(r['passed'])
        self.assertFalse(r['floor_ok'])

    def test_both_coins_needs_each_coin(self):
        rng = np.random.default_rng(9)
        calls, inv = synth(rng, p_unc=0.60, p_conf=0.60)
        eth = calls.coin == 'ETH'
        move = np.where(eth, -calls.move, calls.move)                  # ETH always wrong
        calls = R.Calls(calls.ts, calls.coin, calls.side, move, calls.move_late, calls.past, calls.conf)
        r = R.score(calls, inv, LO, HI, 'month')['checks'][3]
        self.assertFalse(r['passed'])

    def test_the_best_naive_rule_is_the_bar(self):
        rng = np.random.default_rng(10)
        calls, inv = synth(rng, p_unc=0.60, p_conf=0.60)
        # make "fade the last 15 minute move" as good as the candidate: it then ties it and check 3 fails
        calls.past[15] = np.where(calls.move > 0, -1, 1) * -1          # follow15 would be right on every call
        calls.past[15] = np.sign(calls.move).astype(int)
        r = R.score(calls, inv, LO, HI, 'month')
        self.assertFalse(r['checks'][2]['passed'])
        self.assertEqual(r['checks'][2]['best_rule'], 'follow15')

    def test_a_given_base_replaces_the_same_call_comparison(self):
        """PREREG-2.md section 3 item 1: with side = fade check 3 compares with the naive rules at every minute, not on the calls."""
        rng = np.random.default_rng(10)
        calls, inv = synth(rng, p_unc=0.60, p_conf=0.60)
        calls.past[15] = np.sign(calls.move).astype(int)               # on the calls follow15 is always right: the old bar is unreachable
        self.assertFalse(R.score(calls, inv, LO, HI, 'month')['checks'][2]['passed'])
        base = {'up': 0.51, 'down': 0.49, 'follow15': 0.50, 'fade15': 0.525}
        r = R.score(calls, inv, LO, HI, 'month', base=base)
        c3 = r['checks'][2]
        self.assertEqual(c3['best_rule'], 'fade15')
        self.assertAlmostEqual(c3['value'], r['hit_rate'] - 0.525, places=9)
        self.assertTrue(c3['passed'])
        self.assertEqual(r['naive_base'], base)
        self.assertIn('follow15', r['naive'])                           # the same-call rates are still reported
        tight = R.score(calls, inv, LO, HI, 'month', base=dict(base, fade15=r['hit_rate'] - 0.019))
        self.assertFalse(tight['checks'][2]['passed'])                  # a gap under 2.0 points fails
        edge = R.score(calls, inv, LO, HI, 'month', base=dict(base, fade15=r['hit_rate'] - 0.0201))
        self.assertTrue(edge['checks'][2]['passed'])

    def test_a_base_with_no_rate_for_a_rule_ignores_that_rule(self):
        rng = np.random.default_rng(10)
        calls, inv = synth(rng, p_unc=0.60, p_conf=0.60)
        r = R.score(calls, inv, LO, HI, 'month', base={'up': float('nan'), 'fade15': 0.52})
        self.assertEqual(r['checks'][2]['best_rule'], 'fade15')

    def test_flat_calls_are_excluded_and_counted(self):
        rng = np.random.default_rng(11)
        calls, inv = synth(rng, p_unc=0.6, p_conf=0.6)
        calls.move = np.where(rng.random(len(calls)) < 0.2, 0.5, calls.move)
        r = R.score(calls, inv, LO, HI, 'month')
        self.assertGreater(r['flat_share'], 0.15)
        self.assertTrue(r['voided'])

    def test_follows_mode_compares_the_made_calls_with_the_lapsed_ones(self):
        rng = np.random.default_rng(13)
        calls, inv = synth(rng, p_unc=0.62, p_conf=0.62)
        calls.conf = None                                                # follows: no flags, the made calls are the confirmed set
        un, _ = synth(np.random.default_rng(14), p_unc=0.50, p_conf=0.50, per=3.0)
        un.conf = None
        r = R.score(calls, inv, LO, HI, 'month', unconf=un)['checks'][8]
        self.assertTrue(r['passed'], r)                                  # 62% confirmed vs 50% lapsed
        un2, _ = synth(np.random.default_rng(15), p_unc=0.62, p_conf=0.62, per=3.0)
        un2.conf = None
        self.assertFalse(R.score(calls, inv, LO, HI, 'month', unconf=un2)['checks'][8]['passed'])
        self.assertFalse(R.score(calls, inv, LO, HI, 'month')['checks'][8]['passed'])     # neither flags nor lapsed calls: 0

    def test_final_blocks_are_equal_fourths(self):
        rng = np.random.default_rng(12)
        calls, inv = synth(rng, p_unc=0.6, p_conf=0.6)
        r = R.score(calls, inv, LO, HI, 4)['checks'][5]
        self.assertEqual(len(r['value']), 4)

    def test_dev_folds_are_pairs_of_calendar_months(self):
        lo = int(dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
        hi = int(dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
        rng = np.random.default_rng(31)
        n = 2400
        ts = lo + np.sort(rng.integers(0, hi - lo, size=n))
        side = np.where(rng.random(n) < 0.5, 1, -1)
        move = side * 3.0
        # the last day of February hits, the first day of March misses: they sit in different folds only if the folds are Jan-Feb | Mar-Apr
        feb_end = int(dt.datetime(2026, 3, 1, tzinfo=dt.timezone.utc).timestamp() * 1000)
        move = np.where((ts >= feb_end) & (ts < feb_end + 2 * R.DAY * 30), -move, move)       # Mar-Apr all wrong
        calls = R.Calls(ts, np.where(np.arange(n) % 2 == 0, 'BTC', 'ETH'), side, move, move, {k: np.ones(n, int) for k in R.NAIVE_KS}, None)
        r = R.score(calls, None, lo, hi, 'bimonth')['checks'][5]
        self.assertEqual(len(r['value']), 3)
        self.assertLess(r['value'][1], 0.05)                       # Mar-Apr is the second fold
        self.assertGreater(r['value'][0], 0.95)
        self.assertGreater(r['value'][2], 0.5)


if __name__ == '__main__':
    unittest.main()
