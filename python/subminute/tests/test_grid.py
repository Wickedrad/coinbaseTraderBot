import json
import unittest

import numpy as np

from subminute import grid as G

DAY0 = 1_700_006_400_000          # a UTC midnight (Nov 15 2023 00:00:00 UTC)
OPEN = DAY0 + 3600_000
CLOSE = OPEN + 900_000


def L(t, k, **kw):
    return (json.dumps({'t': t, 'k': k, **kw}, separators=(',', ':')) + '\n').encode()     # the bot writes compact JSON.stringify lines


class GridTest(unittest.TestCase):
    def lines(self):
        yield L(OPEN - 5000, 'market', ticker='KXBTC15M-X', series='KXBTC15M', asset='BTC', openTime=OPEN - 600_000, closeTime=CLOSE, strike=100000.0)
        yield L(OPEN - 5000, 'market', ticker='KXFOO-1', series='KXFOO', asset='BTC', openTime=0, closeTime=CLOSE, strike=1.0)
        yield L(OPEN + 1000, 'book', ticker='KXBTC15M-X', bids=[{'price': 0.48, 'size': 10}, {'price': 0.47, 'size': 5}], asks=[{'price': 0.52, 'size': 7}], ts=OPEN + 1000)
        yield L(OPEN + 3500, 'delta', ticker='KXBTC15M-X', side='bid', price=0.49, delta=4, ts=OPEN + 3500)
        yield L(OPEN + 3600, 'trade', ticker='KXBTC15M-X', price=0.52, count=3, takerSide='yes', ts=OPEN + 3000)
        yield L(OPEN + 6000, 'delta', ticker='KXBTC15M-X', side='bid', price=0.49, delta=-4, ts=OPEN + 6000)
        yield L(OPEN + 6000, 'delta', ticker='KXBTC15M-X', side='ask', price=0.52, delta=-7, ts=OPEN + 6000)
        yield L(OPEN + 2000, 'index', asset='BTC', value=100010.5, ts=OPEN + 1900, src='x')
        yield L(OPEN + 2400, 'index', asset='BTC', value=100011.5, ts=OPEN + 2300, src='x')
        yield b'{"t":1,"k":"spot_book","asset":"BTC"}\n'
        yield L(OPEN + 2100, 'spot', asset='BTC', value=100020.0, ts=OPEN + 2000)
        yield L(OPEN + 2300, 'perp', ticker='KXBTCPERP', asset='BTC', ts=OPEN + 2290, bid=10.0001, ask=10.0003, last=10.0002, contractSize=0.0001)
        yield L(CLOSE + 1, 'lifecycle', ticker='KXBTC15M-X', event='metadata_updated', ts=CLOSE + 1)
        yield L(CLOSE + 1201, 'lifecycle', ticker='KXBTC15M-X', event='determined', result='yes', ts=CLOSE + 1201)
        yield L(CLOSE + 2000, 'lifecycle', ticker='KXBTC15M-X', event='settled', ts=CLOSE + 2000)

    def test_reduce(self):
        o = G.reduce_day(self.lines(), DAY0, assets=('BTC', 'ETH'))
        b = o['BTC']
        self.assertEqual(b['tickers'], ['KXBTC15M-X'])
        self.assertEqual(b['result'].tolist(), [1.0])
        bid, ask = b['bid'][0], b['ask'][0]
        self.assertTrue(np.isnan(bid[0]))                               # nothing before the first snapshot
        self.assertAlmostEqual(bid[1], 0.48); self.assertAlmostEqual(ask[1], 0.52)
        self.assertAlmostEqual(bid[2], 0.48)                            # a second without events keeps the book
        self.assertAlmostEqual(bid[3], 0.49); self.assertEqual(b['bsz'][0][3], 4.0)
        self.assertAlmostEqual(bid[6], 0.48)                            # the 0.49 level is gone again
        self.assertTrue(np.isnan(ask[6]))                               # the only ask is gone
        self.assertEqual(b['ty'][0][3], 3.0)
        s = (OPEN + 2000 - DAY0) // 1000
        self.assertAlmostEqual(b['idx'][s], 100011.5)                   # the last of two updates in that second
        self.assertEqual(b['idx_n'][s], 2)
        self.assertAlmostEqual(b['idx_lag_ms'][s], 100.0)
        self.assertEqual(len(o['ETH']['tickers']), 0)
        self.assertEqual(o['counts']['index'], 2)
        self.assertEqual(b['tr_w'].tolist(), [0]); self.assertEqual(b['tr_ms'].tolist(), [3600]); self.assertEqual(b['tr_side'].tolist(), [1])
        self.assertAlmostEqual(float(b['tr_p'][0]), 0.52, places=5); self.assertAlmostEqual(float(b['tr_c'][0]), 3.0)
        self.assertAlmostEqual(b['spot'][s], 100020.0)
        self.assertEqual(b['spot_n'][s], 1)
        self.assertAlmostEqual(b['spot_lag_ms'][s], 100.0)
        self.assertAlmostEqual(b['perp_mid'][s], 100002.0, places=3)       # 10.0002 per contract of 0.0001 coin
        self.assertAlmostEqual(b['perp_last'][s], 100002.0, places=3)

    def test_hourly_ladder_is_read_with_its_own_window(self):
        close = OPEN + 3600_000
        def lines():
            yield L(OPEN + 1000, 'delta', ticker='KXETHD-26NOV1720-T3000', side='bid', price=0.30, delta=9, ts=OPEN)          # before the market line was seen: not kept
            yield L(OPEN + 40_000, 'market', ticker='KXETHD-26NOV1720-T3000', series='KXETHD', asset='ETH', openTime=OPEN, closeTime=close, strike=3000.0, kind='greater')
            yield L(OPEN + 40_000, 'market', ticker='KXETHD-26NOV1721-T3000', series='KXETHD', asset='ETH', openTime=OPEN - 86_400_000, closeTime=close + 3600_000, strike=3000.0)
            yield L(OPEN + 50_000, 'book', ticker='KXETHD-26NOV1720-T3000', bids=[{'price': 0.40, 'size': 10}], asks=[{'price': 0.44, 'size': 6}], ts=OPEN + 50_000)
            yield L(OPEN + 50_000, 'book', ticker='KXETHD-26NOV1719-T2000', bids=[{'price': 0.90, 'size': 10}], asks=[{'price': 0.95, 'size': 6}], ts=OPEN + 50_000)   # a market nobody registered
            yield L(OPEN + 1800_000, 'trade', ticker='KXETHD-26NOV1720-T3000', price=0.44, count=2, takerSide='yes', ts=OPEN + 1800_000)
            yield L(OPEN + 2400_000, 'delta', ticker='KXETHD-26NOV1720-T3000', side='bid', price=0.41, delta=5, ts=OPEN + 2400_000)
            yield L(close + 900, 'lifecycle', ticker='KXETHD-26NOV1720-T3000', event='determined', result='no', ts=close + 900)
            yield L(OPEN + 2000, 'index', asset='ETH', value=3001.0, ts=OPEN + 1900, src='x')
        o = G.reduce_day(lines(), DAY0, assets=('BTC', 'ETH'), **G.HOURLY)
        e = o['ETH']
        self.assertEqual(e['tickers'], ['KXETHD-26NOV1720-T3000'])
        self.assertEqual(e['bid'].shape, (1, 3600))
        self.assertEqual(e['result'][0], 0.0)
        s = (OPEN + 50_000 - (close - 3600_000)) // 1000
        self.assertAlmostEqual(e['bid'][0, s], 0.40)
        self.assertAlmostEqual(e['ask'][0, s], 0.44)
        self.assertAlmostEqual(e['bid'][0, 2400], 0.41)
        self.assertTrue(np.isnan(e['bid'][0, 10]))                                   # nothing known 10 seconds in
        self.assertEqual(len(e['tr_p']), 1)
        self.assertEqual(int(e['tr_ms'][0]), 1800_000)
        self.assertEqual(o['BTC']['bid'].shape, (0, 3600))

    def test_book_as_the_window_opens(self):
        def lines():
            yield L(OPEN - 9000, 'market', ticker='KXETH15M-Y', series='KXETH15M', asset='ETH', openTime=OPEN - 600_000, closeTime=CLOSE, strike=3000.0)
            yield L(OPEN - 3000, 'book', ticker='KXETH15M-Y', bids=[{'price': 0.30, 'size': 2}], asks=[{'price': 0.35, 'size': 9}])
            yield L(OPEN - 2000, 'delta', ticker='KXETH15M-Y', side='ask', price=0.34, delta=5)
            yield L(OPEN + 4000, 'delta', ticker='KXETH15M-Y', side='bid', price=0.31, delta=1)
            yield L(OPEN + 5000, 'book', ticker='KXKXX-Z', bids=[], asks=[])                       # another market: ignored
            yield L(OPEN - 1000, 'book', ticker='KXETH15M-LATER', bids=[{'price': 0.5, 'size': 1}], asks=[])   # no market line: ignored
        o = G.reduce_day(lines(), DAY0, assets=('BTC', 'ETH'))
        e = o['ETH']
        self.assertEqual(e['tickers'], ['KXETH15M-Y'])
        self.assertAlmostEqual(e['bid'][0][0], 0.30); self.assertAlmostEqual(e['ask'][0][0], 0.34)       # from the first second
        self.assertEqual(e['asz'][0][0], 5.0)
        self.assertAlmostEqual(e['bid'][0][3], 0.30); self.assertAlmostEqual(e['bid'][0][4], 0.31)
        self.assertTrue(np.isnan(e['result'][0]))

    def test_kind_of(self):
        self.assertEqual(G.kind_of(b'{"t":1,"k":"delta","x":2}'), b'delta')
        self.assertIsNone(G.kind_of(b'garbage'))


if __name__ == '__main__':
    unittest.main()
