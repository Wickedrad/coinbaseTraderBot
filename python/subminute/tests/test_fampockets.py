import json
import os
import tempfile
import unittest

import numpy as np

from subminute import fampockets as FP

DAY0 = 20_400                                # a UTC day number (days since 1970)
MIN = 60_000


def candle(ts, bid, ask, lo_ask, vol=5):
    return {'ts': ts, 'bidO': bid, 'bidH': bid, 'bidL': bid, 'bidC': bid, 'askO': ask, 'askH': ask, 'askL': lo_ask, 'askC': ask, 'volume': vol}


def market(asset, day, i, result, bid=0.55, ask=0.57, lo_ask=0.55):
    close = (day * 24 * 60 + 60 * (i + 1)) * MIN
    o = close - 15 * MIN
    cs = [candle(o + k * MIN, bid, ask, lo_ask) for k in range(1, 16)]
    return {'ticker': f'KX{asset}15M-{day}-{i}', 'series': f'KX{asset}15M', 'openTime': o, 'closeTime': close, 'strike': 100.0, 'result': result, 'candles': cs}


def write(dirname, assets, days, per_day=6, fill=True):
    rng = np.random.default_rng(1)
    for a in assets:
        d = os.path.join(dirname, 'kalshi', f'KX{a}15M')
        os.makedirs(d, exist_ok=True)
        for day in range(DAY0, DAY0 + days):
            with open(os.path.join(d, f'{np.datetime64("1970-01-01") + np.timedelta64(day, "D")}.jsonl'), 'w') as fh:
                for i in range(per_day):
                    fh.write(json.dumps(market(a, day, i, 'yes' if rng.random() < 0.5 else 'no', lo_ask=0.54 if fill else 0.57)) + '\n')


class FamPocketsTest(unittest.TestCase):
    def test_blocks_maps_and_the_frozen_split(self):
        with tempfile.TemporaryDirectory() as t:
            write(t, ['AAA', 'BBB'], 16)
            r = FP.run(t, 'KX{asset}15M', ['AAA', 'BBB'], os.path.join(t, 'out'), log=lambda *x: None)
            self.assertEqual(set(r['assets']), {'AAA', 'BBB'})
            self.assertEqual(r['assets']['AAA']['windows'], 16 * 6)
            b = r['blocks']
            self.assertLess(b['build'][1], b['check'][0])
            self.assertLess(b['check'][1], b['clean'][0])
            self.assertEqual(b['build'][0], str(np.datetime64('1970-01-01') + np.timedelta64(DAY0, 'D')))   # the first day file is the first build day
            self.assertEqual(set(r['maps']), {'AAA', 'BBB', 'ALL'})
            row = [x for x in r['maps']['ALL'] if x[0] == 'yes' and x[1] == 0.5 and x[2] == 1][0]
            self.assertEqual(len(row), 14)
            self.assertGreater(row[4], 0)                                                     # build fills: the 54c ask goes through a 55c bid
            self.assertTrue(os.path.exists(os.path.join(t, 'out', 'fampockets.json')))

    def test_no_fill_when_the_ask_never_goes_through(self):
        with tempfile.TemporaryDirectory() as t:
            write(t, ['AAA'], 16, fill=False)
            r = FP.run(t, 'KX{asset}15M', ['AAA'], os.path.join(t, 'out'), log=lambda *x: None)
            for row in r['maps']['ALL']:
                if row[1] == 0.5 and row[0] == 'yes':
                    self.assertEqual(row[4], 0)
            self.assertEqual(r['pass_count'], 0)

    def test_too_few_days_is_an_error(self):
        with tempfile.TemporaryDirectory() as t:
            write(t, ['AAA'], 5)
            with self.assertRaises(ValueError):
                FP.run(t, 'KX{asset}15M', ['AAA'], os.path.join(t, 'out'), log=lambda *x: None)


if __name__ == '__main__':
    unittest.main()
