#!/usr/bin/env python3
"""Round 16 addendum: the same map on Steven's anchors (Nov 21, 2026, 9:20 PM EST / Nov 22, 02:20 UTC).

Steven: the grey box on the parent (the small hump right after the December 2016 step:
low Dec 18, high Dec 25, low Jan 15, 2017) is the mid hump, the match for the child's 2020-21
hump (low Sep 13, 2020, high Jan 3, 2021, low May 16, 2021). The dilation is dynamic, and the
parent's top (Feb 26, 2017) is closer to today than to Jun 22, 2025.
Run: python3 steven_anchors.py [draws]
"""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
DRAWS = int(sys.argv.pop(1)) if len(sys.argv) > 1 else 1000
import structure_map as m

HERE = Path(__file__).resolve().parent
S = m.all_series()
TODAY = S["BTC"].index[-1]
CH = ("BTC.D", "BTC", "alts (index steps out)", "ETH/BTC")
PS = pd.DatetimeIndex(["2016-06-19", "2016-07-24", "2016-11-20", "2016-12-18", "2016-12-25", "2017-01-15", "2017-02-26"])
CS = pd.DatetimeIndex(["2017-12-10", "2018-01-14", "2019-09-08", "2020-09-13", "2021-01-03", "2021-05-16", str(TODAY.date())])
NAMES = ["waterfall", "rise to the first hump", "first hump to the step low", "mid hump, up", "mid hump, down (the 2021 fall)", "rise to the top"]
SETS = {"round 16 (hump Sep 2019, fall low May 2021, top Jun 22 2025)": (m.P, m.C),
        "Steven (mid hump = 2020-21 hump, top = today)": (PS, CS),
        "Steven's mid hump, top kept at Jun 22 2025": (PS, CS[:-1].append(pd.DatetimeIndex(["2025-06-22"])))}
base = pd.Timestamp("2010-01-01")
fr = lambda t, a, b: round((t - a).days / (b - a).days, 3)
def tmap(dates, A, B):
    return base + pd.to_timedelta(np.round(np.interp(m.day(dates), m.day(A), m.day(B))), unit="D")
out = {"dataThrough": str(TODAY.date()), "anchors": {"parent": [str(d.date()) for d in PS], "child": [str(d.date()) for d in CS]}}

print("== A. stretches on Steven's anchors ==")
rows = []
d = S["BTC.D"]
for i in range(len(PS) - 1):
    pw, cw = (PS[i + 1] - PS[i]).days / 7, (CS[i + 1] - CS[i]).days / 7
    rp, rc = float(d.asof(PS[i + 1]) / d.asof(PS[i])), float(d.asof(CS[i + 1]) / d.asof(CS[i]))
    r = {"stretch": NAMES[i], "parentWeeks": round(pw, 1), "childWeeks": round(cw, 1), "pace": round(cw / pw, 1),
         "BTC.D": [round(float(d.asof(PS[i])), 2), round(float(d.asof(PS[i + 1])), 2), round(float(d.asof(CS[i])), 2), round(float(d.asof(CS[i + 1])), 2)],
         "BTC.D magnification": round(float(np.log(rc) / np.log(rp)), 1)}
    for n in CH[1:]:
        if S[n].asof(PS[i]) == S[n].asof(PS[i]):
            r[n] = [round(float(S[n].asof(PS[i + 1]) / S[n].asof(PS[i])), 3), round(float(S[n].asof(CS[i + 1]) / S[n].asof(CS[i])), 3)]
    rows.append(r); print(r)
hi = pd.Timestamp("2025-06-22")
print("rise to the child's BTC.D high instead of today: magnification", round(float(np.log(d.asof(hi) / d.asof(CS[5])) / np.log(d.asof(PS[6]) / d.asof(PS[5]))), 1))
out["stretches"] = rows

print("\n== B. inside the last stretch (parent Jan 15 to Feb 26 2017, child May 16 2021 to today) ==")
feats = []
for n in CH:
    a, b = m.swings(S[n].loc[PS[5]:PS[6]]), m.swings(S[n].loc[CS[5]:CS[6]])
    for k in ("fall", "rise"):
        (p0, p1, pv), (c0, c1, cv) = a[k], b[k]
        row = {"chart": n, "kind": k, "parent": [str(p0.date()), str(p1.date()), round(pv * 100, 1), fr(p0, PS[5], PS[6]), fr(p1, PS[5], PS[6])],
               "child": [str(c0.date()), str(c1.date()), round(cv * 100, 1), fr(c0, CS[5], CS[6]), fr(c1, CS[5], CS[6])]}
        feats.append(row); print(row)
out["lastStretch"] = feats

print("\n== C. from the child's BTC.D high (Jun 22 2025) to today, and the same share of the parent's last stretch ==")
f0 = (hi - CS[5]).days / (CS[6] - CS[5]).days
pw0 = PS[5] + pd.Timedelta(days=round(f0 * (PS[6] - PS[5]).days))
last = {"shareOfStretch": round(f0, 3), "parentWindow": [str(pw0.date()), str(PS[6].date())], "charts": {}}
print("share", round(f0, 3), "parent window from", pw0.date())
for n in CH:
    p, c = S[n].loc[pw0:PS[6]], S[n].loc[hi:TODAY]
    sp, sc = m.swings(p), m.swings(c)
    last["charts"][n] = {k: {"change": round(float(x.iloc[-1] / x.iloc[0]), 4), "low": round(float(x.min() / x.iloc[0]), 4), "high": round(float(x.max() / x.iloc[0]), 4),
                             "biggestFall": [str(sw["fall"][0].date()), str(sw["fall"][1].date()), round(sw["fall"][2] * 100, 2)],
                             "biggestRise": [str(sw["rise"][0].date()), str(sw["rise"][1].date()), round(sw["rise"][2] * 100, 2)]}
                         for k, x, sw in (("parent", p, sp), ("child", c, sc))}
    print(n, last["charts"][n])
dip = float(d.loc["2017-02-08":"2017-02-15"].min() / d.asof("2017-02-08")); push = float(d.loc["2017-02-15":"2017-02-26"].max() / d.loc["2017-02-08":"2017-02-15"].min())
cd_ = float(d.loc[hi:TODAY].min() / d.asof(hi))
last["parentFebDip"] = {"from": "2017-02-08", "low": str(d.loc["2017-02-08":"2017-02-15"].idxmin().date()), "ratio": round(dip, 4), "thenPushTo": str(d.loc["2017-02-15":"2017-02-26"].idxmax().date()), "pushRatio": round(push, 4),
                        "childDropRatio": round(cd_, 4), "magnification": round(float(np.log(cd_) / np.log(dip)), 1)}
print("parent Feb dip", last["parentFebDip"])
out["lastPart"] = last

print("\n== D. which anchor set do the charts follow? (trend removed / weekly changes; share of nearby clocks as good) ==")
rng = np.random.default_rng(16)
def score(n, A, B, mode):
    grid = pd.date_range(A[0], A[-1], freq="D"); xg = m.day(grid)
    p = np.log(S[n].reindex(grid).ffill().values); q = np.log(S[n].reindex(tmap(grid, A, B)).values)
    ok = np.isfinite(p) & np.isfinite(q)
    if mode == "weekly changes":
        i = np.where(ok)[0][::7]; return float(np.corrcoef(np.diff(p[i]), np.diff(q[i]))[0, 1])
    det = lambda v: v[ok] - np.polyval(np.polyfit(xg[ok], v[ok], 1), xg[ok])
    return float(np.corrcoef(det(p), det(q))[0, 1])
out["follows"] = {}
for lab, (A, B) in SETS.items():
    b0, b1 = m.day([B[0]])[0], m.day([B[-1]])[0]
    near = []
    while len(near) < DRAWS:
        mid = m.day(B[1:-1]) + rng.uniform(-365, 365, len(B) - 2)
        if b0 + 7 < mid[0] and mid[-1] < b1 - 7 and np.all(np.diff(mid) > 0):
            near.append(pd.DatetimeIndex([B[0]]).append(base + pd.to_timedelta(np.round(mid), unit="D")).append(pd.DatetimeIndex([B[-1]])))
    out["follows"][lab] = {}
    for n in CH:
        r = {}
        for mode in ("detrended", "weekly changes"):
            obs = score(n, A, B, mode); nul = np.array([score(n, A, x, mode) for x in near])
            r[mode] = [round(obs, 3), round(float(np.nanmean(nul >= obs)), 3)]
        out["follows"][lab][n] = r
    print(lab, out["follows"][lab])

print("\n== E. how long the alt-led BTC.D falls took ==")
falls = [("parent waterfall", "2016-06-19", "2016-07-24"), ("parent top to waterfall low", "2017-02-26", "2017-05-21"), ("parent May waterfall alone", "2017-04-30", "2017-05-21"),
         ("child waterfall", "2017-12-10", "2018-01-14"), ("child 2021 fall", "2021-01-03", "2021-05-16"), ("child 2025 drop", "2025-06-22", "2025-09-14")]
out["falls"] = []
for lab, a, b in falls:
    a, b = pd.Timestamp(a), pd.Timestamp(b)
    r = {"fall": lab, "from": str(a.date()), "to": str(b.date()), "weeks": round((b - a).days / 7, 1), "BTC.D": [round(float(d.asof(a)), 2), round(float(d.asof(b)), 2)],
         "alts x": round(float(S["alts (index steps out)"].asof(b) / S["alts (index steps out)"].asof(a)), 2),
         "ETH/BTC x": round(float(S["ETH/BTC"].asof(b) / S["ETH/BTC"].asof(a)), 2) if S["ETH/BTC"].asof(a) == S["ETH/BTC"].asof(a) else None,
         "BTC x": round(float(S["BTC"].asof(b) / S["BTC"].asof(a)), 2)}
    out["falls"].append(r); print(r)
(HERE / "steven_anchors.json").write_text(json.dumps(out, indent=1))
