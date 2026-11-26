import unittest

import numpy as np

from allpairs import data as KD
from dirsweep import grid as G
from dirsweep import kinfo as KI
from dirsweep.tests.util import make_grid

try:
    import lightgbm  # noqa: F401
    HAVE_LGB = True
except Exception:
    HAVE_LGB = False

ND = 6


def two_coin_windows(grids, bid=0.49, ask=0.51, informed=False):
    """Windows of BTC and ETH on the same quarter hours. informed=True: the quote is a flat 50/50 but the window settles as the coin did, so the grids hold
    everything the quote lacks."""
    parts = []
    for ci, c in enumerate(('BTC', 'ETH')):
        m = grids[c]
        nw = m['n'] // 15
        opens = m['t0'] + np.arange(nw, dtype=np.int64) * 15 * G.MIN
        e0 = (opens - m['t0']) // G.MIN
        o = np.asarray(m['o'], float)
        settle = np.where(e0 + 15 < len(o), (o[np.minimum(e0 + 15, len(o) - 1)] > o[e0]).astype(float), 0.0)
        if not informed:
            settle = (np.random.default_rng(ci).random(nw) < 0.5).astype(float)
        full = lambda v: np.full((nw, 15), v)
        parts.append(KD.Windows(15, np.full(nw, ci, np.int16), ['BTC', 'ETH'], opens, o[e0], settle, full(bid), full(ask), full(np.nan), full(np.nan),
                                full(np.nan), full(np.nan), np.zeros((nw, 15)), np.ones(nw), np.zeros(nw, bool), [], np.zeros(nw, np.int16)))
    return KD.Windows.concat(parts)


class InfoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.grids = {'BTC': make_grid(ND, seed=11), 'ETH': make_grid(ND, seed=12)}

    def test_rows_have_one_feature_per_name_and_only_known_minutes(self):
        w = two_coin_windows(self.grids)
        R = KI.rows(self.grids, w, (1, 5, 10))
        self.assertEqual(R['X'].shape[1], len(KI.NAMES))
        self.assertTrue(np.isfinite(R['X']).all())
        self.assertEqual(sorted(set(R['k'].tolist())), [1, 5, 10])
        self.assertEqual(len(R['j']), len(R['y']))
        self.assertTrue((R['bid'] < R['ask']).all())

    def test_price_atlas_counts_each_window_once_per_cell(self):
        w = two_coin_windows(self.grids)
        a = KI.price_atlas(w, {'all': (0, 10 ** 15)}, ranges=((1, 4),), edges=(0.02, 0.50, 0.98))
        n = sum(v.get('all', {}).get('trades', 0) for key, v in a.items() if key.startswith('k1-4_yes'))
        self.assertGreater(n, 0)
        self.assertLessEqual(n, len(w))
        no_cell = a['k1-4_no_0.02-0.50'].get('all', {'trades': 0})                          # 1 - bid = 0.51: not in this bucket, so none
        self.assertEqual(no_cell['trades'], 0)

    @unittest.skipUnless(HAVE_LGB, 'lightgbm is not installed here')
    def test_the_residual_model_finds_information_the_quote_lacks_and_none_when_there_is_none(self):
        for informed, expect_gain in ((True, True), (False, False)):
            w = two_coin_windows(self.grids, informed=informed)
            R = KI.rows(self.grids, w, (3, 6, 9, 12))
            split = int(np.median(w.open_ms))
            fit = KI.fit(R, w, split)
            res = KI.judge(R, w, fit['p'], {'check': (split, 10 ** 15)})
            c = res['check']
            gain = c['logloss_quote'] - c['logloss_quote_plus_residual']
            if expect_gain:
                self.assertGreater(gain, 0.05)                           # a flat quote against a grid that knows the outcome
            else:
                self.assertLess(abs(gain), 0.01)                          # nothing to find


if __name__ == '__main__':
    unittest.main()
