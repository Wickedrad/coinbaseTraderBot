import pandas as pd, numpy as np
P='/home/user/coinbaseTraderBot/research/btcd_fractal/data/'
def ld(n):
    d=pd.read_csv(P+n+'_1d.csv'); d.index=pd.to_datetime(d.ts,unit='ms'); return d
def wk(d): return d.c.resample('W-SUN').last()
b=wk(ld('BTC.D')); cm=wk(ld('BTCD_CMC'))
x=pd.DataFrame(dict(tv=b,cmc=cm))
print(x.loc[['2016-06-12','2016-06-19','2016-06-26','2016-07-24','2016-11-20','2016-12-18','2017-12-10','2018-01-14','2019-09-08','2021-05-16']].round(2))
print(b['2016-06-01':'2017-01-15'].round(2).to_string())
# BTC.D zero/odd daily jumps
d=ld('BTC.D').c; j=d.diff().abs(); print(j['2017':].nlargest(5))
u=ld('USDT.D').c; print(u.diff().abs()['2017':].nlargest(4))
