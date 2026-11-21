import pandas as pd, numpy as np
P='/home/user/coinbaseTraderBot/research/btcd_fractal/data/'
def ld(n):
    d=pd.read_csv(P+n+'_1d.csv'); d.index=pd.to_datetime(d.ts,unit='ms'); return d
def wk(d): return d.c.resample('W-SUN').last().dropna()
u=ld('USDT.D'); print(u.tail(1)[['h','c']])
print('max close',u.c.idxmax(),u.c.max(),' max high',u.h.idxmax(),u.h.max())
print(u.c.nlargest(5)); print(u.h.nlargest(5))
uw=wk(u); print('max wk', uw.idxmax(), uw.max()); print(uw.nlargest(4))
print(uw['2026-09-20':])
# check duplicates/gaps
for n in ['BTC.D','USDT.D','USDC.D','BTCUSD','ETHBTC','TOTAL2']:
    d=ld(n); dd=d.index.to_series().diff().dt.days
    print(n,'dups',d.index.duplicated().sum(),'gaps>1 since2017',(dd['2017':]>1).sum(), 'max gap', dd['2017':].max(), 'last',d.index[-1])
