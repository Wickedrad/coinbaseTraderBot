import pandas as pd, numpy as np
P='/home/user/coinbaseTraderBot/research/btcd_fractal/data/'
def ld(n):
    d=pd.read_csv(P+n+'_1d.csv'); d.index=pd.to_datetime(d.ts,unit='ms'); return d
def wk(d): return d.c.resample('W-SUN').last()
b,u,c=[wk(ld(n)) for n in ['BTC.D','USDT.D','USDC.D']]
S=(u.iloc[-1]+c.iloc[-1])/100; ex=b.iloc[-1]/(1-S)
for t in [9.28,10,11]:
    k=t/u.iloc[-1]; print(t, round(ex*(1-S*k),3))
# alt: USDC fixed
for t in [9.28,10,11]:
    print('usdc fixed',t, round(ex*(1-(t+c.iloc[-1])/100),3))
bu,eb,t2=[wk(ld(n)) for n in ['BTCUSD','ETHBTC','TOTAL2']]
for a,z in [('2017-03-05','2017-03-26'),('2026-11-01','2026-11-22')]:
    print(a,z,'BTC',bu[a],bu[z],round(bu[z]/bu[a]-1,3),'ETHBTC',eb[a],eb[z],round(eb[z]/eb[a]-1,3),'T2',t2[a]/1e9,t2[z]/1e9,round(t2[z]/t2[a]-1,3),'BTCD',b[a],b[z])
print(pd.DataFrame(dict(btc=bu,eb=eb,t2=t2/1e9,btcd=b))['2017-02-19':'2017-04-09'])
st=wk(ld('STABLES')); print('STABLES $B', (st/1e9)['2026-09-27':].round(1))
