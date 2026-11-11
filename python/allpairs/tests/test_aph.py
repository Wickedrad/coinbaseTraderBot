"""The AP-H1b / AP-H2 follow-up (prereg/): fill-rule arms, the 24-hour lead shift, trade readouts, the P2b skill
statistics and the readout's decisions."""
import json
import os
import tempfile
import unittest

import numpy as np

from allpairs import aph, skill
from allpairs.data import MIN, Spot
from allpairs.features import cross_at
from allpairs.run import ARMS, DEFAULTS, LIVE_TIER_DAY, _arr, _num, arm_config, config_hash, fill_readouts, window_inputs


class Arms(unittest.TestCase):
    def test_strict_arms_change_only_the_fill_rule(self):
        self.assertEqual(ARMS['strict']['costs'], {'strict_maker': True})
        self.assertEqual(ARMS['tight_strict']['costs'], {'max_spread': 0.10, 'strict_maker': True})
        for arm in ('strict', 'tight_strict'):
            c = arm_config({}, arm, 'ho1')
            self.assertEqual(c['placebo']['shuffles'], DEFAULTS['placebo']['shuffles'])
            self.assertEqual(c['costs']['maker_mult'], DEFAULTS['costs']['maker_mult'])   # fees unchanged
            self.assertEqual(c['costs']['slip'], DEFAULTS['costs']['slip'])
        self.assertNotEqual(config_hash(arm_config({}, 'tight_strict')), config_hash(arm_config({}, 'tight')))

    def test_lead_shift24_differs_from_lead_btc_only_by_the_shift(self):
        here = os.path.join(os.path.dirname(__file__), '..', 'hypotheses')
        a = json.load(open(os.path.join(here, 'lead_btc.json')))
        b = json.load(open(os.path.join(here, 'lead_shift24.json')))
        self.assertEqual(b.pop('cross_shift_min'), 1440)
        for d in (a, b):
            d.pop('name'), d.pop('notes')
        self.assertEqual(a, b)


class Shift(unittest.TestCase):
    def test_cross_feature_comes_from_the_same_minute_a_day_earlier(self):
        from allpairs.data import Windows
        t0 = 1_767_225_600_000
        n_bars = 3 * 1440
        c = 100 * np.exp(np.cumsum(np.random.default_rng(1).normal(0, 1e-3, n_bars)))
        sp = Spot(t0=t0, o=c, h=c, l=c, c=c, v=np.ones(n_bars), filled=np.zeros(n_bars, bool))
        feats = {'r1': np.concatenate([[np.nan], np.diff(np.log(c))])}
        W, N = 2, 15
        z = np.zeros((W, N))
        w = Windows(N, np.zeros(W, int), ['BTC'], np.array([t0 + 2 * 86_400_000, t0 + 2 * 86_400_000 + 15 * MIN]), np.ones(W), np.ones(W),
                    z, z, z, z, z, z, z, np.ones(W), np.zeros(W, bool))
        now = cross_at(w, sp, feats, 'BTC', names=('r1',))['lead_BTC_r1']
        ago = cross_at(w, sp, feats, 'BTC', names=('r1',), shift_ms=1440 * MIN)['lead_BTC_r1']
        m_now = sp.bar_closing_at(w.open_ms[:, None] + MIN * np.arange(N)[None, :])
        np.testing.assert_allclose(now, feats['r1'][m_now].astype(np.float32))
        np.testing.assert_allclose(ago, feats['r1'][m_now - 1440].astype(np.float32))


class ShiftedExtras(unittest.TestCase):
    def test_lead_shift24_features_are_lead_btc_features_a_day_earlier(self):
        """Every lead feature of lead_shift24 (the cross columns and the lag extras built from them) equals lead_btc's on
        the same windows moved 24 hours back; lag_btc_1 stays exactly 0 on BTC windows."""
        import dataclasses
        from allpairs.data import Windows
        from allpairs.features import spot_features
        here = os.path.join(os.path.dirname(__file__), '..', 'hypotheses')
        lead = merge_cfg(json.load(open(os.path.join(here, 'lead_btc.json'))))
        shift = merge_cfg(json.load(open(os.path.join(here, 'lead_shift24.json'))))
        t0, n_bars = 1_767_225_600_000, 4 * 1440
        rng = np.random.default_rng(4)
        z = rng.normal(0, 1e-3, (2, n_bars))
        spots = {}
        for ai, mix in ((0, z[0]), (1, 0.8 * z[0] + 0.6 * z[1])):
            c = 100 * (ai + 1) * np.exp(np.cumsum(mix))
            spots[ai] = Spot(t0=t0, o=c, h=c, l=c, c=c, v=np.ones(n_bars), filled=np.zeros(n_bars, bool))
        sfeats = {ai: spot_features(sp) for ai, sp in spots.items()}
        W, N = 8, 15
        opens = t0 + 2 * 86_400_000 + 15 * MIN * np.arange(W)
        q = np.full((W, N), 0.5)
        w = Windows(N, np.arange(W) % 2, ['BTC', 'ETH'], opens, np.full(W, 150.0), np.ones(W), q - 0.02, q + 0.02,
                    q, q, q, q, np.ones((W, N)), np.ones(W), np.zeros(W, bool))
        w_ago = dataclasses.replace(w, open_ms=opens - 86_400_000)
        _, _, Xs, ns = window_inputs(w, spots, sfeats, ['BTC', 'ETH'], shift)
        _, _, Xa, na = window_inputs(w_ago, spots, sfeats, ['BTC', 'ETH'], lead)
        _, _, Xn, _ = window_inputs(w, spots, sfeats, ['BTC', 'ETH'], lead)
        self.assertEqual(ns, na)
        lead_cols = [j for j, n_ in enumerate(ns) if n_.startswith('lead_') or n_.startswith('lag_')]
        self.assertEqual(len(lead_cols), 8)
        np.testing.assert_array_equal(Xs[..., lead_cols], Xa[..., lead_cols])
        own = [j for j, n_ in enumerate(ns) if j not in lead_cols]
        np.testing.assert_array_equal(Xs[..., own], Xn[..., own])          # everything else is the window's own
        j = ns.index('lag_btc_1')
        btc = w.asset == 0
        self.assertTrue(np.all(Xs[btc][..., j][np.isfinite(Xs[btc][..., j])] == 0))
        self.assertFalse(np.array_equal(Xs[..., lead_cols], Xn[..., lead_cols]))


def merge_cfg(file_cfg):
    return arm_config(file_cfg, 'base')


class TradeLog(unittest.TestCase):
    def test_nan_round_trips_as_null(self):
        v = [_num(x) for x in [0.123456789, float('nan'), 3]]
        self.assertEqual(v, [0.12346, None, 3])
        back = _arr(json.loads(json.dumps(v)))
        self.assertTrue(np.isnan(back[1]))
        self.assertEqual(_arr([1, 2]).dtype.kind, 'i')     # integer columns stay integers

    def test_fill_readouts(self):
        tr = dict(spread=np.array([0.02, 0.07, 0.2, 0.01]), day=np.array([LIVE_TIER_DAY - 1, LIVE_TIER_DAY, LIVE_TIER_DAY, 1]),
                  side=np.array([0, 1, 0, 1]), paid=np.array([0.2, 0.8, 0.5, 0.9]), mode=np.array([1, 1, 0, 1]),
                  strict=np.array([1, 0, -1, 1]), mk1=np.array([0.01, -0.02, 0.0, 0.03]),
                  mk60=np.array([0.02, np.nan, 0.01, 0.0]), mk300=np.array([np.nan, np.nan, 0.05, 0.01]))
        pnl = np.array([1.0, -2.0, 0.5, 3.0])
        r = fill_readouts(tr, pnl, 10)
        self.assertEqual(r['by_spread']['<=5c'], dict(n=2, per_hour=0.4, avg=2.0))
        self.assertEqual(r['by_spread']['5-10c']['n'], 1)
        self.assertEqual(r['by_spread']['>10c']['n'], 1)
        self.assertEqual(r['by_tier']['historical']['n'], 2)
        self.assertEqual(r['by_side_price']['YES <25c']['n'], 1)
        self.assertEqual(r['by_side_price']['NO >75c']['n'], 2)
        self.assertEqual(r['markout']['maker']['n'], 3)
        self.assertAlmostEqual(r['markout']['maker']['mk60'], 0.01)
        self.assertEqual(r['markout']['maker']['n_mk60'], 2)
        self.assertAlmostEqual(r['strict_fill_share'], 2 / 3, places=4)
        self.assertEqual(fill_readouts({'spread': np.zeros(1)}, np.ones(1), 1), {})   # older parts: no readouts


class Skill(unittest.TestCase):
    def test_isotonic(self):
        x = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
        y = np.array([0.0, 1.0, 0.0, 1.0, 1.0])
        kx, ky = skill.isotonic_fit(x, y)
        np.testing.assert_allclose(ky, [0.0, 0.5, 0.5, 1.0, 1.0])
        self.assertTrue(np.all(np.diff(skill.isotonic_apply((kx, ky), np.linspace(0, 1, 50))) >= 0))

    def test_newey_west_ratio(self):
        e = np.array([1.0, -1.0, 2.0, 0.0])
        n = np.ones(4)
        est, se = skill.newey_west_ratio(e, n, lag=0)
        self.assertAlmostEqual(est, 0.5)
        self.assertAlmostEqual(se, np.sqrt(np.sum((e - 0.5) ** 2)) / 4)

    def test_compare(self):
        rng = np.random.default_rng(0)
        y = (rng.random(20_000) < 0.5).astype(float)
        day = np.repeat(np.arange(100), 200)
        ref = np.full(len(y), 0.5)
        same = compare_same = skill.compare(y, ref, ref, ref, day)
        self.assertEqual(same['dbss'], 0.0)
        self.assertTrue(compare_same['tost_equivalent'])
        better = np.clip(0.5 + 0.3 * (y - 0.5) + rng.normal(0, 0.05, len(y)), 0.01, 0.99)
        r = skill.compare(y, ref, better, ref, day)
        self.assertGreater(r['dbss'], 0.05)
        self.assertTrue(r['verdict'].startswith('falsifier'))


def _res(arm, ph, trades, hourly, folds, h=None, **kw):
    return dict(arm=arm, oos=dict(per_hour=ph, trades=trades, pnl=round(ph * len(hourly), 2)), hourly_pnl=hourly, protocol='ho1',
                folds=[dict(oos=dict(per_hour=f)) for f in folds], config_hash=h or 'x', **kw)


class Readout(unittest.TestCase):
    def test_bhy(self):
        adj = aph.bhy([0.01, 0.04, 0.03, 0.5])
        c = 1 + 1 / 2 + 1 / 3 + 1 / 4
        self.assertAlmostEqual(adj[0], min(1, 0.01 * 4 * c), places=4)
        self.assertAlmostEqual(adj[3], 1.0)
        self.assertLessEqual(adj[2], adj[1])

    def test_daily_p(self):
        self.assertEqual(aph.daily_p([0.0] * 96 * 24), 1.0)
        self.assertLess(aph.daily_p(list(np.random.default_rng(2).normal(0.5, 1, 96 * 24))), 0.01)

    def test_ap_h2_decisions(self):
        def run_with(ts, folds):
            return {'maker_only': dict(arms={'tight': _res('tight', 0.53, 433, [0.53] * 48, [1] * 6),
                                             'tight_strict': _res('tight_strict', ts, 300, [ts] * 48, folds)}, heldout={})}
        self.assertTrue(aph.ap_h2(run_with(0.0, [0] * 6))['verdict'].startswith('supported'))
        self.assertTrue(aph.ap_h2(run_with(0.2, [1] * 6))['verdict'].startswith('supported'))     # share 62%
        self.assertTrue(aph.ap_h2(run_with(0.4, [1, 1, 1, 1, -1, -1]))['verdict'].startswith('falsified'))
        self.assertTrue(aph.ap_h2(run_with(0.4, [1, 1, 1, -1, -1, -1]))['verdict'].startswith('inconclusive'))

    def test_reproduction_and_p3(self):
        a = _res('base', 0.1, 5, [0.1] * 48, [0.1] * 6, h='h')
        same, why = aph.reproduces(a, json.loads(json.dumps(a)))
        self.assertTrue(same, why)
        b = dict(a, hourly_pnl=[0.1] * 47 + [0.2])
        self.assertFalse(aph.reproduces(b, a)[0])
        ref = {'lead_btc': dict(arms={'base': _res('base', 0.0, 0, [0.0] * 96, [0] * 6)}, heldout={}),
               'base': dict(arms={'base': _res('base', 0.0, 0, [0.0] * 96, [0] * 6)}, heldout={})}
        new = {'lead_shift24': dict(arms={'base': _res('base', -0.2, 9, [-0.2] * 96, [0] * 6)}, heldout={})}
        h1 = aph.ap_h1b(new, ref, None)
        self.assertEqual(h1['G_base'], 0.0)
        self.assertTrue(h1['P1'].startswith('moot'))
        self.assertAlmostEqual(h1['P3']['P'], 0.2)
        self.assertTrue(h1['P3']['verdict'].startswith('holds'))

    def test_readout_files(self):
        with tempfile.TemporaryDirectory() as d:
            for root, runs in (('new', {'maker_only': {'base': 0.1, 'tight': 0.53, 'tight_strict': 0.1}}),
                               ('ref', {'maker_only': {'base': 0.1, 'tight': 0.53}})):
                for cfg, arms in runs.items():
                    os.makedirs(os.path.join(d, root, cfg))
                    for arm, ph in arms.items():
                        json.dump(_res(arm, ph, 10, [ph] * 48, [ph] * 6, h='h'), open(os.path.join(d, root, cfg, f'{arm}.json'), 'w'))
            res = aph.run(os.path.join(d, 'new'), os.path.join(d, 'ref'), '1', None, os.path.join(d, 'out'))
            self.assertFalse(res['void'])
            self.assertTrue(res['ap_h2']['verdict'].startswith('supported'))
            self.assertEqual(len(res['bhy']), 2)
            self.assertIn('AP-H2', open(os.path.join(d, 'out', 'aph.md')).read())


if __name__ == '__main__':
    unittest.main()
