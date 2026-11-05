"""Unit tests: python -m unittest discover -s python/allpairs/tests -t python"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest

import numpy as np

from allpairs import EXCLUDED_ASSETS
from allpairs.data import allowed_assets, load_kalshi, load_spot
from allpairs.fake import make
from allpairs.features import safe_eval, side_quotes, spot_at, spot_features, window_features
from allpairs.fees import contracts_for_stake, maker_fee, taker_fee
from allpairs.matrix import Costs, all_pairs, compute_all_pairs_pnl_matrix, maker_fills
from allpairs.policy import simulate
from allpairs.snell import H_, S_, T_, Book, ExitConfig, build_positions, solve_exits
from allpairs.validate import dsr, expected_max_sr, psr, walk_forward

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))


class Fees(unittest.TestCase):
    def test_published_table(self):
        """bot/fees.ts's formula reproduces Kalshi's General Trading Fees Table (1 and 100 contracts)."""
        snap = json.load(open(os.path.join(ROOT, 'bot', 'kalshi', 'feeScheduleSnapshot.json')))
        for r in snap['table']:
            self.assertAlmostEqual(float(taker_fee(1, r['price'])), r['fee1'], places=9, msg=r)
            self.assertAlmostEqual(float(taker_fee(100, r['price'])), r['fee100'], places=9, msg=r)

    def test_rounding_and_maker(self):
        # 0.07 x 10 x 0.5 x 0.5 = 0.175 -> 0.18; maker multiplier 0 pays nothing; maker 1 at 0.0175 -> 0.04375 -> 0.05
        self.assertAlmostEqual(float(taker_fee(10, 0.5)), 0.18)
        self.assertEqual(float(maker_fee(10, 0.5)), 0.0)
        self.assertAlmostEqual(float(maker_fee(10, 0.5, multiplier=1)), 0.05)
        # Direct members' centicent grid.
        self.assertAlmostEqual(float(taker_fee(10, 0.5, precision=0.0001)), 0.175)
        self.assertEqual(float(taker_fee(0, 0.5)), 0.0)
        self.assertEqual(float(taker_fee(5, 1.0)), 0.0)

    def test_parity_with_bot_fees_ts(self):
        """Same numbers as bot/fees.ts itself (run by Node with type stripping) on a grid of counts, prices, grids and
        multipliers: one fee rule for the bot, paper, replay and this engine."""
        import shutil, subprocess
        node = shutil.which('node')
        if not node:
            self.skipTest('node not installed')
        counts = [1, 2, 3, 7, 10, 13, 29, 30, 37, 100, 150, 1500, 12.5]
        prices = [0.001, 0.005, 0.01, 0.02, 0.05, 0.1, 0.123, 0.25, 0.33, 0.4999, 0.5, 0.51, 0.77, 0.9, 0.95, 0.99, 0.999]
        cases = [(c, p, prec, tm, mm) for c in counts for p in prices for prec in (0.01, 0.0001) for tm, mm in ((1, 0), (1, 1), (1.25, 1))]
        js = ("import('./bot/fees.ts').then(f => { const cs = JSON.parse(process.argv[1]); console.log(JSON.stringify(cs.map(([c, p, prec, tm, mm]) => "
              "[f.takerFee(c, p, {takerMultiplier: tm, makerMultiplier: mm, balancePrecision: prec}), f.makerFee(c, p, {takerMultiplier: tm, makerMultiplier: mm, balancePrecision: prec})]))) })")
        r = subprocess.run([node, '--experimental-strip-types', '--no-warnings', '-e', js, json.dumps(cases)], cwd=ROOT, capture_output=True, text=True, timeout=60)
        if r.returncode != 0 and 'strip-types' in r.stderr:
            self.skipTest('node too old for --experimental-strip-types')
        self.assertEqual(r.returncode, 0, r.stderr[-500:])
        want = json.loads(r.stdout.strip().splitlines()[-1])
        for (c, p, prec, tm, mm), (wt, wm) in zip(cases, want):
            self.assertAlmostEqual(float(taker_fee(c, p, tm, prec)), wt, places=9, msg=(c, p, prec, tm))
            self.assertAlmostEqual(float(maker_fee(c, p, mm, prec)), wm, places=9, msg=(c, p, prec, mm))

    def test_contracts(self):
        self.assertEqual(list(contracts_for_stake(15, np.array([0.5, 0.99, 0.01, np.nan]))), [30, 15, 1500, 0])


class Matrix(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(3)
        self.N = 15
        mid = np.clip(0.5 + np.cumsum(rng.normal(0, 0.05, self.N)), 0.03, 0.97)
        self.bid = np.round(mid - 0.01, 2)
        self.ask = np.round(mid + 0.01, 2)

    def test_brute_force(self):
        """Every TT cell equals the hand computation; j <= i is NaN; column N is settlement with no exit fee."""
        c = Costs(stake=15)
        P = compute_all_pairs_pnl_matrix(self.ask, self.bid, 1.0, c)['TT']
        N = self.N
        for i in range(N):
            C = np.floor(15 / self.ask[i])
            fin = float(taker_fee(C, self.ask[i]))
            for j in range(N + 1):
                if j <= i:
                    self.assertTrue(np.isnan(P[i, j]))
                    continue
                if j == N:
                    want = C * (1.0 - self.ask[i]) - fin
                else:
                    want = C * (self.bid[j] - self.ask[i]) - fin - float(taker_fee(C, self.bid[j]))
                self.assertAlmostEqual(P[i, j], want, places=9, msg=(i, j))

    def test_maker_fill_rule(self):
        """A resting buy fills only when the ask reaches it (a bid moving away is no evidence)."""
        bid = np.array([0.50]); ask = np.array([0.52])
        fb, _ = maker_fills(bid, ask, nbl=np.array([0.40]), nbh=np.array([0.50]), nal=np.array([0.51]), nah=np.array([0.52]), strict=False)
        self.assertFalse(fb[0])   # the bid fell (cancellations) but no seller came to 50c
        fb, _ = maker_fills(bid, ask, nbl=np.array([0.49]), nbh=np.array([0.50]), nal=np.array([0.50]), nah=np.array([0.52]), strict=False)
        self.assertTrue(fb[0])
        fb, _ = maker_fills(bid, ask, nbl=np.array([0.49]), nbh=np.array([0.50]), nal=np.array([0.50]), nah=np.array([0.52]), strict=True)
        self.assertFalse(fb[0])   # strict needs a cent through
        _, fs = maker_fills(bid, ask, nbl=np.array([0.5]), nbh=np.array([0.52]), nal=np.array([0.52]), nah=np.array([0.53]), strict=False)
        self.assertTrue(fs[0])

    def test_no_side_is_mirror(self):
        w_bid = self.bid[None, :]; w_ask = self.ask[None, :]
        st = lambda y, n: np.stack([y, n], axis=1)
        b, a = st(w_bid, 1 - w_ask), st(w_ask, 1 - w_bid)
        P = all_pairs(b, a, b, b, a, a, np.array([[1.0, 0.0]]), Costs())['TT']
        Pno = compute_all_pairs_pnl_matrix(1 - self.bid, 1 - self.ask, 0.0, Costs())['TT']
        np.testing.assert_allclose(P[0, 1], Pno, equal_nan=True)


def tiny_book(bids, asks, settle, nal=None, nbh=None):
    b = np.array(bids, dtype=float)[None, None, :]
    a = np.array(asks, dtype=float)[None, None, :]
    nal = b * 0 + 2 if nal is None else np.array(nal, dtype=float)[None, None, :]
    nbh = b * 0 - 1 if nbh is None else np.array(nbh, dtype=float)[None, None, :]
    return Book.build(b, a, b, nbh, nal, a, np.array([[settle]], dtype=float), Costs())


class Snell(unittest.TestCase):
    def test_settlement_rule_and_labels(self):
        """Not in profit at the last decision -> sold at the bid, never settled; labels equal the matrix cell of the
        exit the policy took; hindsight >= policy."""
        rng = np.random.default_rng(1)
        W, N = 400, 15
        mids = np.clip(0.5 + np.cumsum(rng.normal(0, 0.06, (W, N)), axis=1), 0.03, 0.97)
        bid = np.round(mids - 0.01, 2); ask = np.round(mids + 0.01, 2)
        settle = (rng.random(W) < mids[:, -1]).astype(float)
        st = lambda y, n: np.stack([y, n], axis=1)
        b, a = st(bid, 1 - ask), st(ask, 1 - bid)
        book = Book.build(b, a, b, b, a, a, st(settle, 1 - settle), Costs())
        X = np.concatenate([b[..., None], a[..., None]], axis=-1).astype(np.float32)
        pos = build_positions(book, Costs(), maker_entries=False)
        cfg = ExitConfig(rows_per_fit=50_000, maker_exits=False, lgb_params=dict(n_estimators=20, learning_rate=0.1, num_leaves=7, min_child_samples=20))
        r = solve_exits(book, X, pos, Costs(), cfg, groups=(np.arange(W) % 2))
        pnl = r.pnl(pos)
        P = all_pairs(b, a, b, b, a, a, st(settle, 1 - settle), Costs())['TT']
        cell = P[pos.w, pos.s, pos.i, r.exit_k]
        np.testing.assert_allclose(pnl, cell, atol=1e-9)
        # Settled only when in profit at the last decision (bot rule: then it must ride).
        settled = r.exit_kind == S_
        last_bid = book.bid[pos.w, pos.s, N - 1]
        from allpairs.matrix import exit_taker
        aT = exit_taker(last_bid, pos.C, Costs())
        self.assertTrue(np.all(~settled | (aT - pos.cost > 0) | ~np.isfinite(aT)))
        self.assertTrue(np.all(r.exit_k[~settled] > pos.i[~settled]))
        self.assertTrue(np.all(r.oracle0 >= r.value0 - 1e-9))
        # 'bot' rule: in profit at the last decision -> rides (never a taker sale at N-1).
        rode = (aT - pos.cost > 0) & np.isfinite(aT)
        self.assertFalse(np.any((r.exit_k == N - 1) & rode))

    def test_models_reused_out_of_sample(self):
        rng = np.random.default_rng(2)
        W, N = 300, 15
        mids = np.clip(0.5 + np.cumsum(rng.normal(0, 0.05, (W, N)), axis=1), 0.03, 0.97)
        bid = np.round(mids - 0.01, 2); ask = np.round(mids + 0.01, 2)
        settle = (rng.random(W) < mids[:, -1]).astype(float)
        st = lambda y, n: np.stack([y, n], axis=1)
        book = Book.build(st(bid, 1 - ask), st(ask, 1 - bid), st(bid, 1 - ask), st(bid, 1 - ask), st(ask, 1 - bid), st(ask, 1 - bid), st(settle, 1 - settle), Costs())
        X = rng.normal(size=(W, 2, N, 3)).astype(np.float32)
        pos = build_positions(book, Costs(), maker_entries=True)
        cfg = ExitConfig(rows_per_fit=20_000, lgb_params=dict(n_estimators=10, num_leaves=7, min_child_samples=20))
        r = solve_exits(book, X, pos, Costs(), cfg)
        r2 = solve_exits(book, X, pos, Costs(), cfg, models=r.models)
        self.assertEqual(len(r2.value0), len(pos))
        self.assertTrue(np.all(np.isfinite(r2.value0)))


class Policy(unittest.TestCase):
    def test_one_position_per_window_and_maker_retry(self):
        rows = dict(w=np.array([0, 0, 0, 1, 1]), i=np.array([0, 0, 1, 0, 2]), y=np.array([5.0, 1.0, 2.0, -1.0, 3.0]),
                    filled=np.array([False, True, True, True, True]))
        pred = np.array([9.0, 3.0, 1.0, 0.5, 2.0])
        ch = simulate(rows, pred, 0.9)
        # Window 0: the best at minute 0 is an unfilled maker attempt -> no position, minute 1's row (pred 1.0) opens.
        # Window 1: minute 0 is under the hurdle, minute 2 opens.
        self.assertEqual(sorted(ch.tolist()), [2, 4])


class Placebo(unittest.TestCase):
    def test_random_entries_follow_maker_retry(self):
        from allpairs.policy import random_entry_placebo
        # One window: minute 0 only has an unfilled maker attempt; minute 1 a filled taker row worth 1.
        rows = dict(w=np.array([0, 0]), i=np.array([0, 1]), y=np.array([0.0, 1.0]), filled=np.array([False, True]))
        out = random_entry_placebo(rows, 1.0, np.random.default_rng(0), draws=40, n_windows=1)
        np.testing.assert_allclose(out, 1.0)        # an unfilled draw moves on to the later minute, as simulate() does
        rows = dict(w=np.array([0, 0]), i=np.array([0, 1]), y=np.array([1.0, 0.0]), filled=np.array([True, False]))
        out = random_entry_placebo(rows, 1.0, np.random.default_rng(1), draws=200, n_windows=1)
        self.assertTrue(0.3 < out.mean() < 0.7)     # half the draws post the last-minute maker bid and get nothing
        W = 20                                      # with spare windows, an unfilled one is replaced: the model's count
        rows = dict(w=np.repeat(np.arange(W), 2), i=np.tile([0, 1], W), y=np.tile([1.0, 0.0], W), filled=np.tile([True, False], W))
        out = random_entry_placebo(rows, 5 / W, np.random.default_rng(2), draws=50, n_windows=W)
        np.testing.assert_allclose(out, 5.0)


class Bounds(unittest.TestCase):
    def test_bot_side_price_band_and_contract_cap(self):
        from allpairs.matrix import entry_legs
        bid = np.array([0.04, 0.20, 0.50]); ask = np.array([0.05, 0.22, 0.52]); fb = np.ones(3, dtype=bool)
        c = Costs(min_side_price=0.10, max_contracts=50)
        cost_T, C_T, cost_M, C_M, ok_T, ok_M = entry_legs(bid, ask, fb, c)
        self.assertEqual(ok_T.tolist(), [False, True, True])             # a 5c side is a longshot the bot refuses
        self.assertEqual(ok_M.tolist(), [False, True, True])
        self.assertEqual(C_T[1], 50)                                      # floor(15 / 0.22) = 68, capped at 50
        free = entry_legs(bid, ask, fb, Costs())
        self.assertTrue(free[4][0] and free[1][0] == 300)                 # the engine alone has no band


class Gate(unittest.TestCase):
    def _arm(self, name, per_hour=6.0, folds=4, expected=4, missing=()):
        rng = np.random.default_rng(3)
        h = rng.normal(per_hour, 2.0, 24 * 14 * folds)
        return dict(arm=name, config_hash='abc', oos=dict(per_hour=per_hour, per_hour_ci95=[per_hour - 1, per_hour + 1], trades=100),
                    hourly_pnl=h.tolist(), folds=[dict(test=[0, 1])] * folds, folds_expected=expected, parts_missing=list(missing),
                    placebo=dict(random_per_hour_median=-1.0, random_per_hour_p95=0.5, shuffled_per_hour=[0.1, 0.2, 0.0]))

    def test_incomplete_run_fails(self):
        from allpairs.report import gate
        g = gate({'base': self._arm('base'), 'stress': self._arm('stress', 1.0), 'tight': self._arm('tight', 1.0)}, [], None, 'r1')
        self.assertTrue(g['checks']['complete'])
        # An arm the gate needs that never ran is incomplete (it is not mistaken for an arm that ran and lost).
        g = gate({'base': self._arm('base'), 'stress': self._arm('stress', 1.0)}, [], None, 'r1')
        self.assertFalse(g['checks']['complete'])
        self.assertEqual(g['incomplete']['tight']['parts_missing'], ['not run'])
        g = gate({'base': self._arm('base', folds=3, missing=[2]), 'stress': self._arm('stress', 1.0), 'tight': self._arm('tight', 1.0)}, [], None, 'r1')
        self.assertFalse(g['checks']['complete'])
        self.assertFalse(g['passed'])

    def test_trials_counted_once(self):
        from allpairs.report import prior_trials
        ledger = [dict(run='r0', arm='base', config_hash='x', sr_hourly=0.1), dict(run='r0', arm='stress', config_hash='x', sr_hourly=0.0),
                  dict(run='r0', arm='base', config_hash='x', sr_hourly=0.1), dict(run='r1', arm='base', config_hash='abc', sr_hourly=0.3)]
        p = prior_trials(ledger, 'r1', 'abc')
        self.assertEqual(len(p), 1)                 # r0's base once; its stress row and r1 (the candidate itself) left out
        ledger += [dict(run='r9', arm='base', config_hash='abc', sr_hourly=0.3, test=[1, 2]),   # an old report-only copy of r1
                   dict(run='r1', arm='base', config_hash='abc', sr_hourly=0.3, test=[1, 2])]
        p = prior_trials(ledger, 'r1', 'abc', [1, 2], 0.3)
        self.assertEqual([t['run'] for t in p], ['r0'])


class Validation(unittest.TestCase):
    def test_walk_forward_purged(self):
        days = np.arange(100, 300)
        f = walk_forward(days, 90, 14, 1)
        self.assertGreater(len(f), 5)
        for tr, te in f:
            self.assertGreaterEqual(te.min() - tr.max(), 2)   # one embargo day in between
            self.assertEqual(len(tr), 90)
        tests = np.concatenate([te for _, te in f])
        self.assertEqual(len(tests), len(np.unique(tests)))

    def test_dsr(self):
        rng = np.random.default_rng(0)
        r = rng.normal(0.1, 1.0, 2000)
        self.assertGreater(psr(r), 0.99)
        self.assertLess(dsr(r, 1000, 0.01)['dsr'], dsr(r, 2, 0.01)['dsr'])
        self.assertGreater(expected_max_sr(100, 0.01), expected_max_sr(10, 0.01))
        self.assertAlmostEqual(psr(rng.normal(0, 1, 5000)), 0.5, delta=0.45)


class Features(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp()
        make(cls.dir, days=3, assets=('BTC', 'DOGE', 'ETH'))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def test_doge_excluded(self):
        self.assertIn('DOGE', EXCLUDED_ASSETS)
        self.assertEqual(allowed_assets(['btc', 'DOGE', 'eth']), ['BTC', 'ETH'])
        w = load_kalshi(self.dir, ['BTC', 'DOGE'], log=lambda m: None)
        self.assertEqual(w.assets, ['BTC'])
        with self.assertRaises(ValueError):
            load_spot(self.dir, 'DOGE', 0, 2 ** 62)

    def test_no_lookahead(self):
        """Changing every spot bar after a decision time does not change that decision's features."""
        w = load_kalshi(self.dir, ['BTC'], log=lambda m: None)
        sp = load_spot(self.dir, 'BTC', int(w.open_ms.min()) - 2 * 86_400_000, int(w.open_ms.max()) + 86_400_000)
        S, F = spot_at(w, {0: sp}, {0: spot_features(sp)})
        X, names = window_features(w, S, F)
        j, k = 50, 7
        t = int(w.open_ms[j]) + 60_000 * k
        m = sp.bar_closing_at(np.array([t]))[0]
        sp2 = load_spot(self.dir, 'BTC', int(w.open_ms.min()) - 2 * 86_400_000, int(w.open_ms.max()) + 86_400_000)
        for arr in (sp2.o, sp2.h, sp2.l, sp2.c, sp2.v):
            arr[m + 1:] *= 1.37
        S2, F2 = spot_at(w, {0: sp2}, {0: spot_features(sp2)})
        X2, _ = window_features(w, S2, F2)
        spot_cols = [names.index(n) for n in ('r1', 'r15', 'rv60', 'rsi14', 'bbw20', 'macd', 'ou60', 'zdist', 'fair')]
        np.testing.assert_allclose(X[j, :, k, spot_cols], X2[j, :, k, spot_cols], rtol=1e-6, atol=1e-6)
        self.assertFalse(np.allclose(X[j, 0, k + 1, names.index('r1')], X2[j, 0, k + 1, names.index('r1')]))

    def test_cross_asset_features(self):
        """Another asset's returns at a decision time: no lookahead, signed by side, usable in expressions."""
        from allpairs.features import cross_at
        w = load_kalshi(self.dir, ['BTC'], log=lambda m: None)
        lo, hi = int(w.open_ms.min()) - 2 * 86_400_000, int(w.open_ms.max()) + 86_400_000
        sp, eth = load_spot(self.dir, 'BTC', lo, hi), load_spot(self.dir, 'ETH', lo, hi)
        S, F = spot_at(w, {0: sp}, {0: spot_features(sp)})
        cr = cross_at(w, eth, spot_features(eth), 'ETH')
        X, names = window_features(w, S, F, [dict(name='lag', expr='lead_ETH_r1 - r1')], cr)
        j, k = 50, 7
        c = names.index('lead_ETH_r1')
        self.assertAlmostEqual(float(X[j, 0, k, c]), -float(X[j, 1, k, c]), places=6)
        self.assertAlmostEqual(float(X[j, 0, k, names.index('lag')]), float(X[j, 0, k, c] - X[j, 0, k, names.index('r1')]), places=5)
        t = int(w.open_ms[j]) + 60_000 * k
        m = eth.bar_closing_at(np.array([t]))[0]
        for arr in (eth.o, eth.h, eth.l, eth.c, eth.v):
            arr[m + 1:] *= 1.37
        cr2 = cross_at(w, eth, spot_features(eth), 'ETH')
        self.assertAlmostEqual(float(cr['lead_ETH_r3'][j, k]), float(cr2['lead_ETH_r3'][j, k]), places=6)

    def test_safe_eval(self):
        env = {'a': np.array([1.0, 2.0]), 'b': np.array([2.0, 0.0])}
        np.testing.assert_allclose(safe_eval('a * b + abs(-a)', env), [3.0, 2.0])
        self.assertTrue(np.isnan(safe_eval('a / b', env)[1]))
        for bad in ('__import__("os")', 'a.__class__', '[x for x in a]', 'open("f")', 'c + 1'):
            with self.assertRaises((ValueError, SyntaxError)):
                safe_eval(bad, env)

    def test_legacy_cents(self):
        from allpairs.data import repair_legacy_cents
        legacy = [dict(bidC=0.0048, askC=0.0052), dict(bidC=0.0049, askC=0.0051)]
        self.assertTrue(repair_legacy_cents(legacy))
        self.assertAlmostEqual(legacy[0]['bidC'], 0.48)
        tails = [dict(bidC=0.005, askC=0.012), dict(bidC=0.003, askC=0.011)]
        self.assertFalse(repair_legacy_cents(tails))
        self.assertAlmostEqual(tails[0]['bidC'], 0.005)

    def test_crossed_minutes_dropped(self):
        from allpairs.data import market_to_rows
        o = 1_767_225_600_000
        cs = [dict(ts=o + 60_000 * c, bidO=0.4, bidH=0.45, bidL=0.4, bidC=0.42, askO=0.44, askH=0.47, askL=0.43, askC=0.45) for c in range(1, 16)]
        cs[4]['bidC'], cs[4]['askC'] = 0.60, 0.05   # candle 5 closes crossed
        r = market_to_rows(dict(openTime=o, closeTime=o + 900_000, result='yes', candles=cs), 15)
        bid, ask, blo, bhi, alo, ahi, kvol, real, o_eff, n_crossed = r
        self.assertEqual(n_crossed, 1)
        self.assertTrue(np.isnan(bid[5]) and np.isnan(ask[5]))          # decision minute 5 = candle 5 close
        self.assertTrue(np.isnan(alo[4]))                                 # no maker fill proven by a crossed minute
        self.assertAlmostEqual(bid[4], 0.42)

    def test_stale_quotes_and_bad_candle_fields(self):
        from allpairs.data import market_to_rows
        o = 1_767_225_600_000
        cs = [dict(ts=o + 60_000 * c, bidO=0.4, bidH=0.45, bidL=0.4, bidC=0.42, askO=0.44, askH=0.47, askL=0.43, askC=0.45, volume=10)
              for c in range(1, 16) if not 3 <= c <= 8]
        cs[0]['askH'] = 0.01                                              # candle 1: high under its own close
        r = market_to_rows(dict(openTime=o, closeTime=o + 900_000, result='yes', candles=cs), 15, max_stale=3)
        bid, ask, blo, bhi, alo, ahi = r[:6]
        self.assertTrue(np.isnan(alo[0]) and np.isnan(ahi[0]))           # fills at minute 0 come from candle 1
        self.assertAlmostEqual(bid[5], 0.42)                              # candles 3..5 missing: carried 3 minutes
        self.assertTrue(np.isnan(bid[6]) and np.isnan(ask[8]))            # then no quote
        self.assertAlmostEqual(bid[9], 0.42)
        self.assertAlmostEqual(alo[1], 0.43)                              # candle 2 proves fills for minute 1
        r0 = market_to_rows(dict(openTime=o, closeTime=o + 900_000, result='yes', candles=cs), 15)
        self.assertTrue(np.isnan(r0[0][3]) and np.isnan(r0[0][0]))       # default: no carried quote, none at the listing

    def test_one_sided_and_untraded_minutes(self):
        from allpairs.data import market_to_rows
        o = 1_767_225_600_000
        cs = [dict(ts=o + 60_000 * c, bidO=0.4, bidH=0.45, bidL=0.4, bidC=0.42, askO=0.44, askH=0.47, askL=0.43, askC=0.45, volume=5)
              for c in range(1, 16)]
        cs[3].update(bidO=0, bidH=0, bidL=0, bidC=0, askO=0.01, askH=0.01, askL=0.01, askC=0.01)  # candle 4: historical 'no ask' as 1c, no bid
        cs[6]['volume'] = 0                                                                   # candle 7: nothing traded
        bid, ask, blo, bhi, alo, ahi = market_to_rows(dict(openTime=o, closeTime=o + 900_000, result='yes', candles=cs), 15)[:6]
        self.assertTrue(np.isnan(ask[4]) and np.isnan(bid[4]))           # one-sided: no quote on either side
        self.assertTrue(np.isnan(alo[3]))                                 # and it proves no fill for minute 3
        self.assertTrue(np.isnan(alo[6]) and np.isnan(bhi[6]))            # an untraded next minute proves no fill
        self.assertAlmostEqual(alo[5], 0.43)

    def test_side_quotes(self):
        w = load_kalshi(self.dir, ['BTC'], log=lambda m: None)
        b, a, nbl, nbh, nal, nah, st = side_quotes(w)
        np.testing.assert_allclose(b[:, 1], 1 - w.ask)
        np.testing.assert_allclose(nah[:, 1], 1 - w.nbid_lo)
        np.testing.assert_allclose(st[:, 0] + st[:, 1], 1.0)


if __name__ == '__main__':
    unittest.main()
