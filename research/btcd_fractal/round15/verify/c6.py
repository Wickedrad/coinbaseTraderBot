import pandas as pd, numpy as np
exec(open('/tmp/claude-0/-home-user/03e07a4e-fd19-58ad-b23f-24bf5a3dc172/scratchpad/r15/verify/c5.py').read().split('L=legs(5,7,True)')[0])
u=wk(ld('USDT.D')).dropna(); u=u[u.index<='2026-11-15']
ALT=[pd.Timestamp(x[0]) for x in legs(5,7) if x[6]=='ALT']
def run(thr,label,start='2017-07-01'):
    piv,last=zigzag(u,thr,log=True)
    pts=piv+[last]
    pk=[d for k,d,v in pts if k=='H' and d>=pd.Timestamp(start)]
    before=[d for d in pk if d<pd.Timestamp('2026-06-28')]
    hits=[]
    for d in before:
        w=[(a,(a-d).days//7) for a in ALT if 0<=(a-d).days<=91]
        if w: hits.append((str(d.date()),str(w[0][0].date()),w[0][1]))
    print(label,'peaks',len(pk),'before 2026-06-28',len(before),'has 2026-06-28', pd.Timestamp('2026-06-28') in pk)
    print('  peaks',[str(d.date()) for d in before])
    print('  hits',len(hits),hits)
    return before
for p in [0.2,0.3,0.4]:
    run(np.log(1+p),f'log(1+{p})')
    run(-np.log(1-p),f'-log(1-{p})')
# base rate: fraction of weeks in span followed within 13 wks by an ALT start
wks=u['2017-07-01':'2026-06-21'].index
f=np.mean([any(0<=(a-d).days<=91 for a in ALT) for d in wks]); print('base rate any week',round(f,3), len(wks))
