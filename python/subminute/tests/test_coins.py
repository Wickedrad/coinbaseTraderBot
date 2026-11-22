import unittest

import numpy as np

from subminute import coins as CN
from subminute import inventory as INV
from subminute import maker as MK


def acc_of(rules, good, net_good, net_other, days=6, fills=80):
    return {r: {d: np.array([100, fills, fills * (net_good if r == good else net_other), 0.0, 100 * (0.05 if r == good else 0.0), 50.0]) for d in range(days)} for r in rules}


class CoinsTest(unittest.TestCase):
    def test_day_splits_hold_out_four(self):
        s = CN.day_splits(6, 2)
        self.assertEqual(len(s), 15)
        for b, c in s:
            self.assertEqual(len(c), 2)
            self.assertEqual(b | c, set(range(6)))
            self.assertFalse(b & c)

    def test_combine_adds_coins_day_by_day(self):
        r = MK.rules()[0]
        a = {r: {0: np.array([1.0, 1, 0.1, 0, 0, 0])}}
        b = {r: {0: np.array([2.0, 2, 0.2, 0, 0, 0]), 1: np.array([1.0, 1, 0.3, 0, 0, 0])}}
        c = CN.combine([a, b])
        self.assertAlmostEqual(c[r][0][0], 3.0)
        self.assertAlmostEqual(c[r][1][2], 0.3)
        self.assertAlmostEqual(a[r][0][0], 1.0)                 # the inputs are not changed

    def test_a_pick_that_wins_everywhere_travels(self):
        rl = [r for r in MK.rules() if r[4] == 'opt'][:20]
        good = rl[0]
        pick = acc_of(rl, good, 0.04, -0.02)
        judge = acc_of(rl, good, 0.03, -0.02)
        t = CN.transfer(pick, judge, CN.day_splits(6, 2), 'opt')
        self.assertEqual(t['splits_used'], 15)
        self.assertAlmostEqual(t['pick_on_judged_c']['mean'], 3.0)
        self.assertAlmostEqual(t['pick_on_picking_c'], 4.0)
        self.assertGreater(t['pick_minus_all_rules_c']['mean'], 0)

    def test_a_pick_that_does_not_travel_is_seen(self):
        rl = [r for r in MK.rules() if r[4] == 'opt'][:20]
        good = rl[0]
        pick = acc_of(rl, good, 0.04, -0.02)
        judge = acc_of(rl, good, -0.05, -0.01)                  # the market it never saw punishes exactly that rule
        t = CN.transfer(pick, judge, [(set(range(6)), set(range(6)))], 'opt')
        self.assertEqual(t['splits_used'], 1)
        self.assertAlmostEqual(t['pick_on_judged_c']['mean'], -5.0)
        self.assertLess(t['pick_minus_all_rules_c']['mean'], 0)

    def test_floor_is_the_mean_of_all_rules(self):
        rl = [r for r in MK.rules() if r[4] == 'pess'][:10]
        acc = acc_of(rl, rl[0], 0.10, -0.01)
        f = CN.floor(acc, set(range(6)), 'pess')
        self.assertEqual(f['rules'], 10)
        self.assertAlmostEqual(f['net_per_fill_c'], (10.0 + 9 * -1.0) / 10)
        self.assertEqual(f['rules_above_zero'], 1)

    def test_hourly_settings_apply_and_are_put_back(self):
        from subminute import hourly as HR
        from subminute import lag as LG
        before = (LG.WIN, MK.WIN, LG.RANGES, LG.INFO_HI, MK.PLACE, MK.CANCEL, len(MK.rules()))
        old = HR.configure()
        try:
            self.assertEqual((LG.WIN, MK.WIN, LG.INFO_HI), (3600, 3600, 3540))
            self.assertEqual(MK.rules()[0][2], (60, 600))
            self.assertEqual(len(MK.rules()), 360)
        finally:
            HR.restore(old)
        self.assertEqual((LG.WIN, MK.WIN, LG.RANGES, LG.INFO_HI, MK.PLACE, MK.CANCEL, len(MK.rules())), before)

    def test_inventory_counts_series(self):
        lines = [b'{"t":1,"k":"market","ticker":"KXETHD-26NOV2210-T3000","series":"KXETHD","openTime":0,"closeTime":3600000}\n',
                 b'{"t":2,"k":"book","ticker":"KXETHD-26NOV2210-T3000","bids":[],"asks":[]}\n',
                 b'{"t":3,"k":"book","ticker":"KXETHD-26NOV2210-T3100","bids":[],"asks":[]}\n',
                 b'{"t":4,"k":"trade","ticker":"KXBTC15M-26NOV2210-00","price":0.5,"count":1,"takerSide":"yes"}\n',
                 b'{"t":5,"k":"spot","asset":"ETH","value":1}\n']
        r = INV.inventory(lines)
        self.assertEqual(r['kinds']['book'], 2)
        self.assertEqual(r['series']['KXETHD']['distinct_markets'], 2)
        self.assertEqual(r['series']['KXETHD']['minutes_open_to_close']['median'], 60.0)
        self.assertEqual(r['series']['KXBTC15M']['lines_by_kind'], {'trade': 1})
        self.assertNotIn('spot', {k for v in r['series'].values() for k in v['lines_by_kind']})


if __name__ == '__main__':
    unittest.main()
