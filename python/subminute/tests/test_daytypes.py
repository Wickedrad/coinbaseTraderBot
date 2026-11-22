import json
import os
import tempfile
import unittest

import numpy as np

from subminute import daytypes as DT
from subminute import fampockets as FP
from subminute import pockets as PK
from subminute.tests.test_fampockets import DAY0, MIN, candle, market, write


def write_weekend(dirname, asset='AAA', days=56, per_day=10, yes_on_weekend=True):
    """A YES buy at 55c wins every weekend window and loses every weekday window; the book trades through the order every minute."""
    d = os.path.join(dirname, 'kalshi', f'KX{asset}15M')
    os.makedirs(d, exist_ok=True)
    for day in range(DAY0, DAY0 + days):
        weekend = ((day + 3) % 7) >= 5
        res = 'yes' if (weekend == yes_on_weekend) else 'no'
        with open(os.path.join(d, f'{np.datetime64("1970-01-01") + np.timedelta64(day, "D")}.jsonl'), 'w') as fh:
            for i in range(per_day):
                fh.write(json.dumps(market(asset, day, i, res, lo_ask=0.54)) + '\n')


def write_daily(dirname, ticker='KXHIGHAAA', days=16, per_day=3):
    """Daily brackets: a 40-hour market, candles for the last 720 minutes only (as the fetcher keeps them)."""
    d = os.path.join(dirname, 'kalshi', ticker)
    os.makedirs(d, exist_ok=True)
    rng = np.random.default_rng(3)
    for day in range(DAY0, DAY0 + days):
        with open(os.path.join(d, f'{np.datetime64("1970-01-01") + np.timedelta64(day, "D")}.jsonl'), 'w') as fh:
            for i in range(per_day):
                close = (day * 24 * 60 + 60 * (i + 1)) * MIN
                cs = [candle(close - 720 * MIN + k * MIN, 0.55, 0.57, 0.54) for k in range(1, 721)]
                fh.write(json.dumps({'ticker': f'{ticker}-{day}-{i}', 'series': ticker, 'openTime': close - 40 * 60 * MIN, 'closeTime': close, 'strike': 70.0,
                                     'result': 'yes' if rng.random() < 0.5 else 'no', 'candles': cs}) + '\n')


class DayTypesTest(unittest.TestCase):
    def test_daily_windows_keep_the_last_twelve_hours(self):
        with tempfile.TemporaryDirectory() as t:
            write_daily(t)
            r = FP.run(t, '{asset}', ['KXHIGHAAA'], os.path.join(t, 'out'), log=lambda *x: None, kind='daily')
            self.assertEqual(r['assets']['KXHIGHAAA']['windows'], 16 * 3)
            row = [x for x in r['maps']['ALL'] if x[0] == 'yes' and x[1] == 0.5 and x[2] == 1][0]
            self.assertGreater(row[4], 0)                                                       # the order placed in the first two hours fills
            self.assertEqual(PK.CANCEL, (10, 14))                                                # the settings are put back


    def setUp(self):
        self.old = (PK.MIN_BUILD_FILLS, PK.MIN_CHECK_FILLS)

    def tearDown(self):
        PK.MIN_BUILD_FILLS, PK.MIN_CHECK_FILLS = self.old

    def test_weekend_only_edge_is_found_and_saved_with_its_type(self):
        with tempfile.TemporaryDirectory() as t:
            write_weekend(t)
            w = DT.load(t, 'm15', ['AAA'], log=lambda *x: None)
            r = DT.run(w, os.path.join(t, 'out'), shifts=20, min_build=10, min_check=5, min_clean=5, log=lambda *x: None)
            self.assertGreater(r['typed_found'], 0)
            tr = [x for x in r['typed_rules'] if x['type']['feature'] == 'wkend']
            self.assertTrue(tr)
            self.assertTrue(all(x['type']['level'] == 'weekend' and x['rule']['side'] == 'yes' for x in tr))
            self.assertTrue(all(x['check_other_days']['net_c'] < 0 < x['check']['net_c'] for x in tr))            # worse on the other days
            self.assertTrue(os.path.exists(os.path.join(t, 'out', 'typed_rules.json')))

    def test_an_edge_that_does_not_depend_on_the_day_is_not_typed(self):
        with tempfile.TemporaryDirectory() as t:
            write_weekend(t, yes_on_weekend=True)
            for f in os.listdir(os.path.join(t, 'kalshi', 'KXAAA15M')):                                              # every window settles YES: no day type matters
                p = os.path.join(t, 'kalshi', 'KXAAA15M', f)
                rows = [json.loads(x) for x in open(p)]
                for m in rows:
                    m['result'] = 'yes'
                open(p, 'w').write('\n'.join(json.dumps(m) for m in rows) + '\n')
            w = DT.load(t, 'm15', ['AAA'], log=lambda *x: None)
            r = DT.run(w, os.path.join(t, 'out'), shifts=5, min_build=10, min_check=5, min_clean=5, log=lambda *x: None)
            self.assertEqual(r['typed_found'], 0)

    def test_labels_use_the_previous_day_and_the_build_days_only(self):
        with tempfile.TemporaryDirectory() as t:
            write(t, ['AAA'], 30)
            w = DT.load(t, 'm15', ['AAA'], log=lambda *x: None)
            day0, nd = int(w.day.min()), int(w.day.max() - w.day.min() + 1)
            build = np.zeros(nd, bool)
            build[:15] = True
            lab, cuts = DT.labels(w, day0, nd, build)
            self.assertEqual(set(lab['wkend']), {0, 1})
            self.assertEqual(lab['pvolu'][0], -1)                                                                     # no previous day for the first one
            self.assertTrue(all(len(v) == nd for v in lab.values()))

    def test_too_few_days_is_an_error(self):
        with tempfile.TemporaryDirectory() as t:
            write(t, ['AAA'], 8)
            w = DT.load(t, 'm15', ['AAA'], log=lambda *x: None)
            with self.assertRaises(ValueError):
                DT.run(w, os.path.join(t, 'out'), shifts=1, log=lambda *x: None)


if __name__ == '__main__':
    unittest.main()
