import pandas as pd, numpy as np
P='/home/user/coinbaseTraderBot/research/btcd_fractal/data/'
def ld(n):
    d=pd.read_csv(P+n+'_1d.csv'); d.index=pd.to_datetime(d.ts,unit='ms'); return d
def wk(d): return d.c.resample('W-SUN').last()
b,u,c=[wk(ld(n)) for n in ['BTC.D','USDT.D','USDC.D']]
S=(u+c)/100; ex=b/(1-S)
df=pd.DataFrame(dict(btcd=b,usdt=u,usdc=c,S=S*100,ex=ex))
print(df['2026-09-27':].round(3))
for a in ['2026-10-04','2026-11-01']:
    print(a,'dBTCD',round(b.iloc[-1]-b[a],3),'dEx',round(ex.iloc[-1]-ex[a],3),'dS',round((S.iloc[-1]-S[a])*100,3))
# ex-stables using STABLES series if available
st=ld('STABLES'); tot=ld('TOTAL'); print(st.tail(2)[['c']], tot.tail(2)[['c']])
sw=wk(st); tw=wk(tot)
S2=sw/tw; ex2=b/(1-S2)
print(pd.DataFrame(dict(S2=S2*100,ex2=ex2, S=S*100))['2026-09-27':].round(3))
# BTC mcap from BTC.D*TOTAL; non-stable= TOTAL*(1-S)
btcm=b/100*tw; print('BTC mcap B', (btcm/1e9)['2026-10-25':].round(1)); print('BTCUSD wk',wk(ld('BTCUSD'))['2026-10-25':])
# CMC check
cm=ld('BTCD_CMC'); print(cm.tail(3).c, 'BTCD_CMC wk', wk(cm)['2026-09-27':])
