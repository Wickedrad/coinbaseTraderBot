import unittest

import numpy as np

from dirsweep import features as F
from dirsweep import grid as G
from dirsweep.tests.util import make_grid


def naive_row(m, k, e):
    """One row's reading, straight from the definitions of PREREG-3.md section 3 (no cumulative sums)."""
    o, v, tb, gap = (np.asarray(m[x]) for x in ('o', 'v', 'tb', 'gap'))
    if e < G.MIN_ROW or gap[e - 60:e + 1].any() or gap[e - 1440:e].sum() > 72:
        return None
    M = o[e] - o[e - k]
    if M == 0:
        return None
    ms = np.array([o[j] - o[j - k] for j in range(e - 1440, e)])
    sigma = np.sqrt((ms ** 2).mean())
    vk = v[e - k:e].sum()
    meanv = v[e - 1440:e].mean()
    if sigma <= 0 or vk <= 0 or meanv <= 0:
        return None
    z = abs(M) / sigma
    a = np.sign(M) * (2 * tb[e - k:e].sum() - vk) / vk
    r = vk / (k * meanv)
    return (int(np.sign(M)), sum(z >= t for t in G.TZ), sum(a >= t for t in G.TA), sum(r >= t for t in G.TR), (e % 60) % 15)


class FeatureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = make_grid(6, seed=3, gap_days=(), level=100.0)
        cls.m['gap'][1500:1520] = True                      # a gap inside the window
        cls.m['v'][1500:1520] = 0
        cls.m['tb'][1500:1520] = 0

    def test_codes_equal_the_definition_row_by_row(self):
        rng = np.random.default_rng(5)
        rows = rng.integers(G.MIN_ROW - 5, self.m['n'], 120)
        for k in (1, 5, 15, 60):
            c = F.codes(self.m, k)
            for e in rows:
                want = naive_row(self.m, k, int(e))
                if want is None:
                    self.assertFalse(c['ok'][e], (k, e))
                else:
                    self.assertTrue(c['ok'][e], (k, e))
                    got = (int(c['sgn'][e]), int(c['zc'][e]), int(c['ac'][e]), int(c['rc'][e]), int(c['mq'][e]))
                    self.assertEqual(got, want, (k, e))

    def test_a_gap_blocks_the_next_hour_of_calls(self):
        c = F.codes(self.m, 5)
        self.assertFalse(c['ok'][1500:1500 + 61].any())
        self.assertTrue(c['ok'][1500 + 61:1500 + 200].any())

    def test_cut_test_passes_and_catches_a_one_bar_leak(self):
        res = F.cut_test(self.m, ks=(1, 15), cuts=6)
        self.assertTrue(res['ok'], res)
        self.assertGreater(res['rows_compared'], 10000)

        def leak(m, k, full):
            full = dict(full)
            full['sgn'] = np.roll(full['sgn'], -1)           # row e now carries row e+1's sign
            return full
        bad = F.cut_test(self.m, ks=(1, 15), cuts=6, lookahead=leak)
        self.assertFalse(bad['ok'])
        self.assertGreater(bad['mismatches'], 0)

    def test_a_later_bar_never_changes_an_earlier_reading(self):
        m2 = {x: (np.array(self.m[x]) if hasattr(self.m[x], '__len__') else self.m[x]) for x in self.m}
        cut = 5000
        for x in ('o', 'h', 'l', 'c', 'v', 'tb'):
            m2[x][cut:] = m2[x][cut:] * 1.7 + 3                # change everything from the cut on
        a, b = F.codes(self.m, 10), F.codes(m2, 10)
        for x in ('ok', 'sgn', 'zc', 'ac', 'rc', 'mq'):
            self.assertTrue((a[x][:cut] == b[x][:cut]).all(), x)


if __name__ == '__main__':
    unittest.main()
