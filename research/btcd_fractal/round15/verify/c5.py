import pandas as pd, numpy as np, sys
P='/home/user/coinbaseTraderBot/research/btcd_fractal/data/'
def ld(n):
    d=pd.read_csv(P+n+'_1d.csv'); d.index=pd.to_datetime(d.ts,unit='ms'); return d
def wk(d): return d.c.resample('W-SUN').last()
def zigzag(s, thr, log=False):
    x=np.log(s.values) if log else s.values; idx=s.index
    piv=[]; trend=0; hi=lo=0
    for i in range(1,len(x)):
        if trend>=0 and x[i]>x[hi]: hi=i
        if trend<=0 and x[i]<x[lo]: lo=i
        if trend==0:
            if x[hi]-x[lo]>=thr:
                if hi>lo: piv.append(('L',lo)); trend=1; lo=i
                else: piv.append(('H',hi)); trend=-1; hi=i
        elif trend==1:
            if x[hi]-x[i]>=thr: piv.append(('H',hi)); trend=-1; lo=i
        else:
            if x[i]-x[lo]>=thr: piv.append(('L',lo)); trend=1; hi=i
    last=('H',hi) if trend==1 else ('L',lo)
    return [(k,idx[i],s.values[i]) for k,i in piv], (last[0],idx[last[1]],s.values[last[1]])
b=wk(ld('BTC.D')).dropna(); eb=wk(ld('ETHBTC')); bu=wk(ld('BTCUSD'))
b=b[b.index<='2026-11-15']  # complete weeks
def legs(rev,mn,verbose=False):
    piv,last=zigzag(b,rev)
    pts=piv+[last]
    out=[]
    for (k1,d1,v1),(k2,d2,v2) in zip(pts,pts[1:]):
        if k1=='H' and v1-v2>=mn and d1>=pd.Timestamp('2017-12-01'):
            er=eb[d2]/eb[d1]-1; br=bu[d2]/bu[d1]-1
            alt= er>=0.20 and br>-0.15
            out.append((d1.date(),d2.date(),round(v1,2),round(v2,2),round(er,3),round(br,3),'ALT' if alt else 'crash' if br<=-0.15 else 'other'))
    if verbose:
        for o in out: print(o)
        print('last unconfirmed',last)
    return out
L=legs(5,7,True)
print()
for rev in [4,5,6]:
    for mn in [6,7,8]:
        o=legs(rev,mn); print(rev,mn,len(o),[(str(x[0]),x[6]) for x in o])
