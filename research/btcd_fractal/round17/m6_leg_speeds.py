#!/usr/bin/env python3
"""Round 17 M6 (description): how fast each leg of BTC.D ran, in logit per week, parent and child.

logit BTC.D = log(BTC value / value of everything else), so -0.25 logit in a week means BTC lost 22% against
everything else that week. Legs are the settled structures plus the three actual waterfall events (the only
waterfalls, by Steven's rule), the 2021 fall and the Jun-Sep 2025 drop (listed apart, not as waterfalls).
Run: python3 m6_leg_speeds.py
"""
import json
import numpy as np, pandas as pd
import common as c

d = c.btcd(); dl = c.lbtcd(); dls = c.lbtcd(True); w = c.weekly(dl); ws = c.weekly(dls)
tot = c.load("TOTAL")
LEGS = [  # kind, era, name, start, end (weekly closes)
    ("waterfall", "parent", "July 2016 waterfall", "2016-06-19", "2016-07-24"),
    ("waterfall", "parent", "2017 waterfall after the parent's top", "2017-02-26", "2017-05-21"),
    ("waterfall", "child", "2017-18 waterfall", "2017-12-10", "2018-01-14"),
    ("other fall", "parent", "mid-structure fall (index step Dec 16 2016)", "2016-11-20", "2016-12-18"),
    ("other fall", "child", "2021 fall (mid-structure), whole stretch from the Sep 2019 high", "2019-09-08", "2021-05-16"),
    ("other fall", "child", "2021 fall, sharp part from the Jan 3 2021 high", "2021-01-03", "2021-05-16"),
    ("other fall", "child", "Jun-Sep 2025 drop (inside the top)", "2025-06-22", "2025-09-14"),
    ("rise", "parent", "rise after the July 2016 waterfall", "2016-07-24", "2016-11-20"),
    ("rise", "parent", "rise to the top", "2017-01-15", "2017-02-26"),
    ("rise", "child", "rise after the 2017-18 waterfall", "2018-01-14", "2019-09-08"),
    ("rise", "child", "rise to the Jun 22 2025 high", "2022-12-11", "2025-06-22"),
]
rows = []
for kind, era, name, a, b in LEGS:
    a, b = pd.Timestamp(a), pd.Timestamp(b)
    seg, segs = w[a:b], ws[a:b]
    wk = (b - a).days / 7
    ch = seg.diff().dropna()
    r = {"kind": kind, "era": era, "leg": name, "from": str(a.date()), "to": str(b.date()), "weeks": round(wk, 1),
         "btcd": [round(float(d.asof(a)), 2), round(float(d.asof(b)), 2)], "moveLogit": round(float(seg.iloc[-1] - seg.iloc[0]), 3),
         "moveLogitStepsOut": round(float(segs.iloc[-1] - segs.iloc[0]), 3),
         "speedLogitPerWeek": round(float((seg.iloc[-1] - seg.iloc[0]) / wk), 4), "speedStepsOut": round(float((segs.iloc[-1] - segs.iloc[0]) / wk), 4),
         "fastest4WeeksLogit": round(float((seg.diff(4)).min() if kind != "rise" else (seg.diff(4)).max()), 3) if len(seg) > 4 else None,
         "biggestWeekLogit": round(float(ch.min() if kind != "rise" else ch.max()), 3),
         "btcVsRestMultiple": round(float(np.exp(seg.iloc[-1] - seg.iloc[0])), 3),
         "marketValueAtStartBn": round(float(tot.asof(a)) / 1e9, 1)}
    rows.append(r); print({k: r[k] for k in ("kind", "era", "leg", "weeks", "btcd", "moveLogit", "moveLogitStepsOut", "speedLogitPerWeek", "speedStepsOut", "fastest4WeeksLogit", "biggestWeekLogit", "marketValueAtStartBn")})
# every 4-week fall of BTC.D on record, to see how rare waterfall speed is outside the three waterfalls
d4 = w.diff(4).dropna()
thr = -0.5
hits = d4[d4 <= thr]
eps = []
for t in hits.index:
    if not eps or (t - eps[-1][-1]).days > 28:
        eps.append([t])
    else:
        eps[-1].append(t)
ep = [{"weeksEnding": [str(e[0].date()), str(e[-1].date())], "worst4w": round(float(d4[e[0]:e[-1]].min()), 3)} for e in eps]
print("4-week falls of 0.5 logit or more (BTC down 39% against the rest in 4 weeks):", ep)
# how much BTC.D was already moving before each waterfall began (daily logit changes, index-step days out), against today
def tvol(t, weeks):
    seg = dls[pd.Timestamp(t) - pd.Timedelta(weeks=weeks):pd.Timestamp(t)]
    return round(float(seg.diff().dropna().std()), 4)
before = [{"waterfall": n, "start": a, "volPerDay13w": tvol(a, 13), "volPerDay26w": tvol(a, 26), "move13wLogit": round(float(ws.asof(pd.Timestamp(a)) - ws.asof(pd.Timestamp(a) - pd.Timedelta(weeks=13))), 3)}
          for k, e, n, a, b in LEGS if k == "waterfall"]
before.append({"waterfall": "today", "start": str(c.THROUGH.date()), "volPerDay13w": tvol(c.THROUGH, 13), "volPerDay26w": tvol(c.THROUGH, 26), "move13wLogit": round(float(w.iloc[-1] - w.iloc[-14]), 3)})
print("before each waterfall:", before)
now4 = round(float(d4.iloc[-1]), 3); now13 = round(float(w.diff(13).iloc[-1]), 3)
print("last 4 weeks", now4, "last 13 weeks", now13, "child weekly changes since 2023: sd", round(float(w["2023-01-01":].diff().std()), 4))
# is "volatile and rising" special to the waterfalls? The same two readings at the start of the other falls, and how common the state is
wv = dls.diff().rolling(91).std().resample("W-SUN").last(); mv = ws.diff(13)
others = [{"fall": n, "start": a, "volPerDay13w": round(float(wv.asof(pd.Timestamp(a))), 4), "move13wLogit": round(float(mv.asof(pd.Timestamp(a))), 3)}
          for n, a in (("2021 fall, from the Sep 2019 high", "2019-09-08"), ("2021 fall, sharp part", "2021-01-03"), ("Jun-Sep 2025 drop", "2025-06-22"))]
lo_v = min(b["volPerDay13w"] for b in before[:3]); lo_m = min(b["move13wLogit"] for b in before[:3])
rec = wv["2014-06-01":]; state = ((wv >= lo_v) & (mv >= lo_m))["2014-06-01":]
base = {"since": "2014-06-01", "weeks": int(len(rec)), "weeksAsVolatileAsTheQuietestWaterfallStart": int((rec >= lo_v).sum()), "lastSuchWeek": str(rec[rec >= lo_v].index[-1].date()),
        "weeksVolatileAndRising": int(state.sum()), "lastVolatileAndRisingWeek": str(state[state].index[-1].date()),
        "todayVolRankShare": round(float((rec <= rec.iloc[-1]).mean()), 3), "lowestVol": [str(rec.idxmin().date()), round(float(rec.min()), 4)],
        "medianVolByYear": {int(k): round(float(v), 4) for k, v in rec.groupby(rec.index.year).median().items()}}
print("other falls began from:", others); print("base rate:", base)
(c.HERE / "m6_leg_speeds.json").write_text(json.dumps({"through": str(c.THROUGH.date()), "legs": rows, "fourWeekFalls": {"threshold": thr, "episodes": ep}, "last4w": now4, "last13w": now13,
                                                        "beforeEachWaterfall": before, "otherFallsBeganFrom": others, "volatileStateBaseRate": base}, indent=1))
