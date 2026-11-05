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
        make(cls.dir, days=3, assets=('BTC', 'DOGE'))

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

    def test_side_quotes(self):
        w = load_kalshi(self.dir, ['BTC'], log=lambda m: None)
        b, a, nbl, nbh, nal, nah, st = side_quotes(w)
        np.testing.assert_allclose(b[:, 1], 1 - w.ask)
        np.testing.assert_allclose(nah[:, 1], 1 - w.nbid_lo)
        np.testing.assert_allclose(st[:, 0] + st[:, 1], 1.0)


if __name__ == '__main__':
    unittest.main()
