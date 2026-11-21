import pandas as pd, numpy as np, json
from math import comb
print('binom P(X>=4|14,.179)=',round(sum(comb(14,k)*.179**k*.821**(14-k) for k in range(4,15)),3))
T=pd.Timestamp; W=lambda a,b:(T(b)-T(a)).days/7
print('P1-P3',W('2016-07-24','2016-12-18'),'C1-C3',W('2018-01-14','2021-05-16'),'ratio',W('2018-01-14','2021-05-16')/W('2016-07-24','2016-12-18'))
print('P0-P1',W('2016-06-19','2016-07-24'),'C0-C1',W('2017-12-10','2018-01-14'))
print('C3->now',W('2021-05-16','2026-11-15'),'P3->0305',W('2016-12-18','2017-03-05'),W('2021-05-16','2026-11-15')/W('2016-12-18','2017-03-05'))
print('P2-P3',W('2016-11-20','2016-12-18'),'C2-C3',W('2019-09-08','2021-05-16'), 'P1-P2',W('2016-07-24','2016-11-20'),'C1-C2',W('2018-01-14','2019-09-08'))
w=pd.DataFrame(json.load(open('/home/user/coinbaseTraderBot/research/btcd_fractal/out14/july2016/results.json'))['walkForwardPath'])
w['date']=pd.to_datetime(w.date); w['primary']=pd.to_datetime(w.primary)
print(w.primary.isna().sum(), w.date.min(), w.date.max(), len(w))
m=w[w.date>='2023-03-01']; print('since Mar2023 placements', m.primary.value_counts().to_dict())
print('first week with primary not in set after', w[~w.primary.isin([T('2017-02-26'),T('2017-03-05')])].date.max())
print(w.primary.value_counts().sort_index().to_dict())
ALT=[T(x) for x in ['2017-12-10','2018-04-01','2019-09-08','2021-01-03','2021-06-27','2025-06-22']]
r=174/21
for rate in [r]:
    v=w[w.primary<=T('2017-03-05')].copy()
    v['impl']=v.date+pd.to_timedelta(rate*W('2017-01-01','2017-01-01')+rate*((T('2017-03-12')-v.primary).dt.days/7)*7,unit='D')
    p=v[v.impl<=T('2026-11-01')]
    hit=p.impl.apply(lambda d:any(abs((d-a).days)<=28 for a in ALT))
    print('n implied',len(v),'passed',len(p),'hits',hit.sum(),round(hit.mean(),4),'span',p.impl.min().date(),p.impl.max().date())
    print(p[hit][['date','primary','impl']].to_string())
    for s0,s1 in [(p.impl.min(),T('2026-11-01')),(p.impl.min(),p.impl.max()),(v.date.min(),T('2026-11-01'))]:
        days=pd.date_range(s0,s1)
        print(' base',s0.date(),s1.date(),round(np.mean([any(abs((d-a).days)<=28 for a in ALT) for d in days]),4))
    print('implied dates future:',v[v.impl>T('2026-11-01')].impl.dt.date.unique()[:10], v.impl.max())
