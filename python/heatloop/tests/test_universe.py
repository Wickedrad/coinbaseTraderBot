import gzip
import os
import tempfile
import unittest

from heatloop import universe as U

HEAD = 'coin,kind,key,h,hs,dir,passes,rep,hot,n_A,n_B,days_B,wd_B,share_A,share_B,share_over_B,odds_A,odds_B,t_A,t_B,oheat_B,move_B,hold_B,hold_over_B,best_B,dip_B,tick_B\n'


def line(coin, key, h=15, dir_=1, nA=1000, nB=500, sA=53.0, sB=52.0, oheat=10.0):
    return f'{coin},single,{key},{h},{h},{dir_},True,True,True,{nA},{nB},365,1.0,{sA},{sB},2.0,3.0,2.0,5.0,4.0,{oheat},0.3,8.0,1.0,5.0,-2.0,0.001\n'


class Load(unittest.TestCase):
    def write(self, lines):
        d = tempfile.mkdtemp()
        p = os.path.join(d, 'l.csv.gz')
        with gzip.open(p, 'wt') as f:
            f.write(HEAD + ''.join(lines))
        return p

    def test_filters_folds_aliases_and_ranks_by_heat(self):
        p = self.write([
            line('BTC', '5m:RSI14=very high', oheat=50), line('BTC', '5m:CMO14=very high', oheat=50),          # same numbers: one event
            line('BTC', '1m:ZSCORE20=low', nA=2000, oheat=70),
            line('BTC', '1m:SLOW=low', h=60, oheat=99),                                                         # other horizon
            line('SOL', '1m:X=low', oheat=99),                                                                  # other coin
            line('ETH', '1m:Y=low', oheat=5),
        ])
        rows = U.load(p)
        btc = [r for r in rows if r['coin'] == 'BTC']
        self.assertEqual([(r['key'], r['rank_coin']) for r in btc], [('1m:ZSCORE20=low', 1), ('5m:CMO14=very high', 2)])
        self.assertEqual(btc[1]['aliases'], ['5m:RSI14=very high'])                    # the sorted-first key names the event
        self.assertEqual([r['key'] for r in rows if r['coin'] == 'ETH'], ['1m:Y=low'])
        self.assertEqual(U.all_keys(rows, 'BTC'), ['1m:ZSCORE20=low', '5m:CMO14=very high', '5m:RSI14=very high'])
        self.assertEqual({r['tf'] for r in rows}, {'1m', '5m'})

    def test_never_doge(self):
        with self.assertRaises(SystemExit):
            U.load(self.write([line('DOGE', '1m:A=b')]))

    def test_the_real_league_file_loads_and_matches_the_amendment(self):
        here = os.path.dirname(__file__)
        p = os.path.join(here, '..', '..', '..', 'research', 'oracle_heat', 'latest', 'league_direction.csv.gz')
        self.assertEqual(U.sha256(p), '1931ecbca4a7da1e0e1f5ba38b677d8fcbe6d9381f9e92407d5046123a3d62b7')
        rows = U.load(p)
        by = {}
        for r in rows:
            by.setdefault((r['coin'], r['tf']), 0)
            by[(r['coin'], r['tf'])] += 1
        self.assertGreater(by[('ETH', '5m')], 60)                                     # the 5m rows the traded pack lacks
        self.assertGreater(by[('BTC', '1m')], 100)
        self.assertEqual({r['coin'] for r in rows}, {'BTC', 'ETH'})
        for coin in ('BTC', 'ETH'):
            rk = sorted(r['rank_coin'] for r in rows if r['coin'] == coin)
            self.assertEqual(rk, list(range(1, len(rk) + 1)))


if __name__ == '__main__':
    unittest.main()
