"""Tests of the exit-policy, entry-decision and diagnostics options (exit.policy, entry.decision, val_exit_quality, diag)."""
from __future__ import annotations

import json
import os
import tempfile
import unittest

import numpy as np

from allpairs.data import market_to_rows
from allpairs.matrix import Costs
from allpairs.policy import entry_rows, maker_attempts
from allpairs.run import ARMS, DEFAULTS, config_hash, fair_edge_value, merge
from allpairs.run import main as run_main
from allpairs.snell import S_, T_, Book, ExitConfig, build_positions, solve_exits

HYP = os.path.join(os.path.dirname(os.path.abspath(__import__('allpairs').__file__)), 'hypotheses')


def rw_book(seed, W=300, N=15, costs=None):
    rng = np.random.default_rng(seed)
    mids = np.clip(0.5 + np.cumsum(rng.normal(0, 0.05, (W, N)), axis=1), 0.03, 0.97)
    bid = np.round(mids - 0.01, 2); ask = np.round(mids + 0.01, 2)
    settle = (rng.random(W) < mids[:, -1]).astype(float)
    st = lambda y, n: np.stack([y, n], axis=1)
    book = Book.build(st(bid, 1 - ask), st(ask, 1 - bid), st(bid, 1 - ask), st(bid, 1 - ask), st(ask, 1 - bid), st(ask, 1 - bid),
                      st(settle, 1 - settle), costs or Costs())
    X = rng.normal(size=(W, 2, N, 3)).astype(np.float32)
    return book, X


class ExitPolicyNaive(unittest.TestCase):
    def test_naive_policy_is_the_naive_baseline(self):
        """exit.policy 'naive': labels equal the naive hold-then-forced value exactly, no exit model is fitted, the
        hindsight bound and the naive baseline are the learned run's, and only forced last-minute taker sales happen."""
        book, X = rw_book(3)
        pos = build_positions(book, Costs(), maker_entries=True)
        lgb = dict(n_estimators=10, num_leaves=7, min_child_samples=20)
        learned = solve_exits(book, X, pos, Costs(), ExitConfig(rows_per_fit=20_000, lgb_params=lgb))
        naive = solve_exits(book, X, pos, Costs(), ExitConfig(rows_per_fit=20_000, lgb_params=lgb, policy='naive'))
        np.testing.assert_array_equal(naive.value0, naive.naive0)
        np.testing.assert_array_equal(naive.naive0, learned.naive0)
        np.testing.assert_array_equal(naive.oracle0, learned.oracle0)
        self.assertEqual(naive.models, {})
        self.assertTrue(np.all(np.isin(naive.exit_kind, [T_, S_])))
        self.assertTrue(np.all((naive.exit_kind == S_) | (naive.exit_k == book.n - 1)))
        # The validation/test call path (models from a training solve, here {}) gives the same labels.
        applied = solve_exits(book, X, pos, Costs(), ExitConfig(policy='naive'), models={})
        np.testing.assert_array_equal(applied.value0, naive.value0)
        # end_rule 'allow' changes nothing for the naive rule (it never chooses at the last minute).
        allow = solve_exits(book, X, pos, Costs(), ExitConfig(policy='naive', end_rule='allow'))
        np.testing.assert_array_equal(allow.value0, naive.value0)

    def test_policy_values(self):
        self.assertEqual(ExitConfig().policy, 'learned')
        book, X = rw_book(4, W=20)
        pos = build_positions(book, Costs(), maker_entries=False)
        with self.assertRaises(ValueError):
            solve_exits(book, X, pos, Costs(), ExitConfig(policy='nave'))


class ConfigKeys(unittest.TestCase):
    OPTIONAL = {('exit', 'policy'): ('learned', 'naive'), ('entry', 'decision'): ('model', 'fair_edge'),
                ('entry', 'taker_entries'): (True, False)}

    def test_new_keys_do_not_rehash_existing_configs(self):
        """exit.policy / entry.decision are read with .get, never DEFAULTS keys: base keeps its hash (pinned at HEAD)."""
        self.assertNotIn('policy', DEFAULTS['exit'])
        self.assertNotIn('decision', DEFAULTS['entry'])
        self.assertNotIn('taker_entries', DEFAULTS['entry'])
        h = lambda f: config_hash(merge(merge(DEFAULTS, json.load(open(os.path.join(HYP, f)))), ARMS['base']))
        # max_crossed 99 became the default after keep_crossed (Nov 5): base is now the same trial as keep_crossed.
        self.assertEqual(h('base.json'), 'da11163cef')
        self.assertEqual(h('keep_crossed.json'), h('base.json'))

    def test_hypothesis_keys_exist(self):
        """Every key a hypothesis file sets is a DEFAULTS key or a known optional key with a valid value (a typo would
        silently score the base configuration under a new hash: a wasted ledger trial)."""
        def walk(d, ref, path=()):
            for k, v in d.items():
                p = path + (k,)
                if p in self.OPTIONAL:
                    self.assertIn(v, self.OPTIONAL[p], msg=str(p))
                    continue
                if p in (('name',), ('notes',)):
                    continue
                self.assertIn(k, ref, msg=str(p))
                if isinstance(v, dict) and isinstance(ref[k], dict):
                    walk(v, ref[k], p)
        for f in sorted(os.listdir(HYP)):
            if f.endswith('.json'):
                walk(json.load(open(os.path.join(HYP, f))), DEFAULTS)

    def test_unknown_decision_stops_before_loading(self):
        d = tempfile.mkdtemp()
        cfg = os.path.join(d, 'c.json')
        json.dump({'name': 'x', 'entry': {'decision': 'fair'}}, open(cfg, 'w'))
        with self.assertRaisesRegex(SystemExit, 'entry.decision'):
            run_main(['--history', d, '--config', cfg, '--out', os.path.join(d, 'o.json')])


class Diagnostics(unittest.TestCase):
    def test_labels_align_with_a_one_column_feature_slice(self):
        """run.py re-labels the test rows under the naive exit with entry_rows(Xte[..., :1], ...): the rows must be the
        same rows in the same order as the full-feature call."""
        book, X = rw_book(5)
        pos = build_positions(book, Costs(), maker_entries=True)
        rng = np.random.default_rng(0)
        pa, pb = rng.normal(size=len(pos)), rng.normal(size=len(pos))
        att = maker_attempts(book.bid, book.n - 1)
        ra, rb = entry_rows(X, pos, pa, att), entry_rows(X[..., :1], pos, pb, att)
        for k in ('w', 's', 'i', 'mode', 'filled'):
            np.testing.assert_array_equal(ra[k], rb[k])
        tk = pos.mode == 0
        np.testing.assert_array_equal(rb['y'][:int(tk.sum())], pb[tk])
        self.assertEqual(rb['X'].shape[1], 2)


class FairEdge(unittest.TestCase):
    def test_value_is_contracts_times_fair_minus_entry_cost(self):
        """fair_edge_value = C x (fair - per-contract taker cost) of the matching taker position (same sizing, band,
        cap, slip and fee as matrix.entry_legs), in the base and the stress costs; maker rows are never chosen."""
        for costs in (Costs(min_side_price=0.10, max_contracts=250),
                      Costs(slip=0.01, taker_mult=1.25, maker_mult=1.0, strict_maker=True, min_side_price=0.10, max_contracts=250)):
            book, _ = rw_book(6, costs=costs)
            W, _, N = book.bid.shape
            fair = np.random.default_rng(1).random((W, 2, N)).astype(np.float32)
            pos = build_positions(book, costs, maker_entries=True)
            rows = entry_rows(fair[..., None], pos, np.zeros(len(pos)), maker_attempts(book.bid, N - 1))
            fe = fair_edge_value(rows, book, ['fair'], costs)
            tk = pos.mode == 0
            want = pos.C[tk] * (fair[pos.w[tk], pos.s[tk], pos.i[tk]].astype(np.float64) - pos.cost[tk])
            np.testing.assert_allclose(fe[rows['mode'] == 0], want, rtol=0, atol=1e-9)
            self.assertTrue(np.all(np.isneginf(fe[rows['mode'] == 1])))


class KeepCrossed(unittest.TestCase):
    def test_crossed_count_is_at_most_n_minus_1(self):
        """max_crossed 99 keeps every window: a window counts at most N-1 = 14 crossed decision minutes, and a crossed
        minute has no quote (so keeping the window in training adds no tradeable minute)."""
        o = 1_767_225_600_000
        cands = [dict(ts=o + c * 60_000, bidO=0.5, bidH=0.5, bidL=0.5, bidC=0.5, askO=0.01, askH=0.01, askL=0.01, askC=0.01, volume=1.0)
                 for c in range(1, 16)]
        r = market_to_rows(dict(openTime=o, closeTime=o + 15 * 60_000, result='yes', candles=cands), 15)
        self.assertEqual(r[-1], 14)
        self.assertLess(r[-1], 99)
        self.assertTrue(np.all(np.isnan(r[0])) and np.all(np.isnan(r[1])))



class Spread(unittest.TestCase):
    def test_tight_arm_drops_wide_books_only(self):
        """costs.max_spread: no taker or maker entry where ask - bid exceeds it; 0 (the default) changes nothing."""
        from allpairs.matrix import entry_legs
        bid = np.array([0.40, 0.40, 0.01, np.nan])
        ask = np.array([0.45, 0.52, 0.99, 0.50])
        fb = np.ones(4, dtype=bool)
        off = entry_legs(bid, ask, fb, Costs())
        on = entry_legs(bid, ask, fb, Costs(max_spread=0.10))
        np.testing.assert_array_equal(on[4], off[4] & np.array([True, False, False, False]))
        np.testing.assert_array_equal(on[5], off[5] & np.array([True, False, False, False]))
        self.assertTrue(off[4][1] and off[5][1])          # the 12c book trades without the cap
        self.assertEqual(ARMS['tight']['costs'], {'max_spread': 0.10})
        self.assertNotIn('max_spread', DEFAULTS['costs'])  # read through Costs' default: existing hashes unchanged


class MakerOnly(unittest.TestCase):
    def test_taker_entries_off_leaves_the_maker_positions(self):
        rng = np.random.default_rng(7)
        W, N = 200, 15
        mids = np.clip(0.5 + np.cumsum(rng.normal(0, 0.05, (W, N)), axis=1), 0.15, 0.85)
        bid, ask = np.round(mids - 0.01, 2), np.round(mids + 0.01, 2)
        st = lambda y, n_: np.stack([y, n_], axis=1)
        # the next minute's ask low reaches our bid (and the bid high our ask): every resting order can fill
        book = Book.build(st(bid, 1 - ask), st(ask, 1 - bid), st(bid, 1 - ask), st(ask, 1 - bid), st(bid, 1 - ask), st(ask, 1 - bid),
                          st(sy := (rng.random(W) < 0.5).astype(float), 1 - sy), Costs())
        both = build_positions(book, Costs(), maker_entries=True)
        self.assertTrue(np.any(both.mode == 0) and np.any(both.mode == 1))
        mk = build_positions(book, Costs(), maker_entries=True, taker_entries=False)
        self.assertTrue(len(mk) > 0 and np.all(mk.mode == 1))
        sel = both.mode == 1
        for k in ('w', 's', 'i', 'C', 'cost'):
            np.testing.assert_array_equal(getattr(mk, k), getattr(both, k)[sel])


class Lockbox(unittest.TestCase):
    def test_sealed_days_are_never_read(self):
        """load_kalshi(skip_days=...) neither opens a sealed day's file nor keeps a market opening on a sealed day."""
        from allpairs.data import load_kalshi
        from allpairs.fake import make
        d = tempfile.mkdtemp()
        make(d, days=3, assets=('BTC',))
        quiet = lambda *_: None
        full = load_kalshi(d, ['BTC'], log=quiet)
        day0 = int(full.day.min())
        f = os.path.join(d, 'kalshi', 'KXBTC15M', '2026-01-02.jsonl')
        self.assertTrue(os.path.exists(f))
        os.chmod(f, 0)           # a sealed file that is opened would raise PermissionError (unless running as root)
        try:
            sk = load_kalshi(d, ['BTC'], log=quiet, skip_days={day0 + 1})
        finally:
            os.chmod(f, 0o644)
        self.assertGreater(len(sk), 0)
        self.assertFalse(np.any(sk.day == day0 + 1))
        # A day file can hold the market that opened in the last minutes of the day before (named by its close): skipping
        # the sealed file loses at most that one market, never adds one.
        self.assertIn(int(np.sum(full.day != day0 + 1)) - len(sk), (0, 1))


if __name__ == '__main__':
    unittest.main()
