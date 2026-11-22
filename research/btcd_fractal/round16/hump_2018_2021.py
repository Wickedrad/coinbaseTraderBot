#!/usr/bin/env python3
"""Round 16, second correction (Nov 21, 2026, 9:45 PM EST / Nov 22, 02:45 UTC).

Steven: the grey box on the parent (low Dec 18 2016, high Dec 25, low Jan 15 2017) is right, but its
match in the child is the whole hump from the bottom of the 2017-18 waterfall (Jan 14 2018) to the
2021 fall (low May 16 2021), not only the 2020-21 part. The top is still today.
Run: python3 hump_2018_2021.py [draws]
"""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
DRAWS = int(sys.argv.pop(1)) if len(sys.argv) > 1 else 1000
import structure_map as m

HERE = Path(__file__).resolve().parent
S = m.all_series()
TODAY = S["BTC"].index[-1]
T = str(TODAY.date())
CH = ("BTC.D", "BTC", "alts (index steps out)", "ETH/BTC")
ix = pd.DatetimeIndex
# the hump as Steven gives it: low, high, low; the fall into it and the rise out of it on either side
HP = ix(["2016-11-20", "2016-12-18", "2016-12-25", "2017-01-15", "2017-02-26"])
HC = ix(["2017-12-10", "2018-01-14", "2019-09-08", "2021-05-16", T])
NAMES = ["fall into the hump's low", "hump, up", "hump, down", "rise to the top"]
# the same with the start of the fall marked (parent Jan 4 2017 = last high before the fall; child Jan 3 2021)
HP4, HC4 = ix(sorted(set(HP) | {pd.Timestamp("2017-01-04")})), ix(sorted(set(HC) | {pd.Timestamp("2021-01-03")}))
# carried back one structure (not Steven's words): parent's 2016 waterfall against the child's 2017
BP, BC = ix(["2016-06-19", "2016-07-24"]).append(HP), ix(["2017-02-26", "2017-08-27"]).append(HC)
OLDP = ix(["2016-06-19", "2016-07-24", "2016-11-20", "2016-12-18", "2016-12-25", "2017-01-15", "2017-02-26"])
OLDC = ix(["2017-12-10", "2018-01-14", "2019-09-08", "2020-09-13", "2021-01-03", "2021-05-16", T])
SETS = {"hump = Jan 2018 to May 2021 (low, high, low)": (HP, HC),
        "the same, with the start of the 2021 fall marked": (HP4, HC4),
        "the same, carried back to the parent's waterfall": (BP, BC),
        "first addendum (hump = Sep 2020 to May 2021), same parent window": (OLDP[2:], OLDC[2:])}
base = pd.Timestamp("2010-01-01")
d = S["BTC.D"]
v = lambda s, t: float(s.asof(pd.Timestamp(t)))
lg = lambda a, b: float(np.log(b / a))
def tmap(dates, A, B):
    return base + pd.to_timedelta(np.round(np.interp(m.day(dates), m.day(A), m.day(B))), unit="D")
out = {"dataThrough": T, "anchors": {"parent": [str(x.date()) for x in HP], "child": [str(x.date()) for x in HC]}}

print("== A. stretches ==")
def table(A, B, names):
    rows = []
    for i in range(len(A) - 1):
        pw, cw = (A[i + 1] - A[i]).days / 7, (B[i + 1] - B[i]).days / 7
        r = {"stretch": names[i], "parentWeeks": round(pw, 1), "childWeeks": round(cw, 1), "pace": round(cw / pw, 1),
             "BTC.D": [round(v(d, A[i]), 2), round(v(d, A[i + 1]), 2), round(v(d, B[i]), 2), round(v(d, B[i + 1]), 2)],
             "BTC.D magnification": round(lg(v(d, B[i]), v(d, B[i + 1])) / lg(v(d, A[i]), v(d, A[i + 1])), 1)}
        for n in CH[1:]:
            if S[n].asof(A[i]) == S[n].asof(A[i]):
                r[n] = [round(v(S[n], A[i + 1]) / v(S[n], A[i]), 3), round(v(S[n], B[i + 1]) / v(S[n], B[i]), 3)]
        rows.append(r); print(r)
    return rows
out["stretches"] = table(HP, HC, NAMES)
print("-- carried back one structure")
out["carriedBack"] = table(BP[:3], BC[:3], ["waterfall (child: Feb to Aug 2017)", "rise to the first hump (child: Aug to Dec 2017)"])
hp, hc = (HP[3] - HP[1]).days / 7, (HC[3] - HC[1]).days / 7
hi = pd.Timestamp("2025-06-22")
pace = {"hump": round(hc / hp, 1), "riseToToday": round((TODAY - HC[3]).days / 7 / 6, 1), "riseToJun2025High": round((hi - HC[3]).days / 7 / 6, 1),
        "childWeeksPerParentDay": round(hc / hp / 7, 1),
        "parentTopOnHumpPace": str((HC[3] + pd.Timedelta(weeks=6 * hc / hp)).date())}
print("pace", pace); out["pace"] = pace

print("\n== B. inside the hump (parent daily closes, child weekly closes) ==")
pp = d.loc["2016-12-16":"2017-01-15"]; cw_ = d.loc["2018-01-14":"2021-05-16"].resample("W-SUN").last()
P = {"low": pp.loc[:"2016-12-20"].idxmin(), "high": pp.idxmax(), "fallStart": pd.Timestamp("2017-01-04"), "end": pp.loc["2017-01-05":].idxmin()}
P["sag"] = pp.loc[P["high"]:P["fallStart"]].idxmin()
C = {"low": pd.Timestamp("2018-01-14"), "high": cw_.idxmax(), "fallStart": pd.Timestamp("2021-01-03"), "end": pd.Timestamp("2021-05-16")}
C["sag"] = cw_.loc[C["high"]:C["fallStart"]].idxmin()
shape = {}
for lab, X in (("parent", P), ("child", C)):
    tot = (X["end"] - X["low"]).days; rise = lg(v(d, X["low"]), v(d, X["high"]))
    shape[lab] = {"dates": {k: str(t.date()) for k, t in X.items()}, "levels": {k: round(v(d, t), 2) for k, t in X.items()},
                  "timeShare": {"up": round((X["high"] - X["low"]).days / tot, 2), "topZone": round((X["fallStart"] - X["high"]).days / tot, 2), "down": round((X["end"] - X["fallStart"]).days / tot, 2)},
                  "sagShareOfRise": round(lg(v(d, X["sag"]), v(d, X["high"])) / rise, 2),
                  "bounceShareOfSag": round(lg(v(d, X["sag"]), v(d, X["fallStart"])) / lg(v(d, X["sag"]), v(d, X["high"])), 2),
                  "fallShareOfRise": round(lg(v(d, X["end"]), v(d, X["high"])) / rise, 2)}
    print(lab, shape[lab])
out["humpShape"] = shape

print("\n== C. the top against the hump's high ==")
ptop, phump = float(d.loc["2017-01-15":"2017-03-05"].max()), float(pp.max())
ctop, chump, clow, plow = float(d.loc["2021-05-16":TODAY].resample("W-SUN").last().max()), float(cw_.max()), v(d, "2021-05-16"), float(pp.loc["2017-01-05":].min())
top = {"parent": {"humpHigh": round(phump, 2), "low": round(plow, 2), "top": round(ptop, 2), "topDate": str(d.loc["2017-01-15":"2017-03-05"].idxmax().date()), "shareOfFallRegained": round(lg(plow, ptop) / lg(plow, phump), 2)},
       "child": {"humpHigh": round(chump, 2), "low": round(clow, 2), "top": round(ctop, 2), "shareOfFallRegained": round(lg(clow, ctop) / lg(clow, chump), 2),
                 "today": round(v(d, TODAY), 2), "todayShare": round(lg(clow, v(d, TODAY)) / lg(clow, chump), 2)}}
print(top); out["topVsHump"] = top

print("\n== D. which anchor set do the charts follow? (trend removed / weekly changes; share of nearby clocks as good) ==")
rng = np.random.default_rng(162)
def score(n, A, B, mode):
    grid = pd.date_range(A[0], A[-1], freq="D"); xg = m.day(grid)
    p = np.log(S[n].reindex(grid).ffill().values); q = np.log(S[n].reindex(tmap(grid, A, B)).values)
    ok = np.isfinite(p) & np.isfinite(q)
    if mode == "weekly changes":
        i = np.where(ok)[0][::7]; return float(np.corrcoef(np.diff(p[i]), np.diff(q[i]))[0, 1])
    det = lambda x: x[ok] - np.polyval(np.polyfit(xg[ok], x[ok], 1), xg[ok])
    return float(np.corrcoef(det(p), det(q))[0, 1])
out["follows"] = {}
for lab, (A, B) in SETS.items():
    b0, b1 = m.day([B[0]])[0], m.day([B[-1]])[0]
    near = []
    while len(near) < DRAWS:
        mid = m.day(B[1:-1]) + rng.uniform(-365, 365, len(B) - 2)
        if b0 + 7 < mid[0] and mid[-1] < b1 - 7 and np.all(np.diff(mid) > 0):
            near.append(ix([B[0]]).append(base + pd.to_timedelta(np.round(mid), unit="D")).append(ix([B[-1]])))
    out["follows"][lab] = {}
    for n in CH:
        r = {}
        for mode in ("detrended", "weekly changes"):
            obs = score(n, A, B, mode); nul = np.array([score(n, A, x, mode) for x in near])
            r[mode] = [round(obs, 3), round(float(np.nanmean(nul >= obs)), 3)]
        out["follows"][lab][n] = r
    print(lab, out["follows"][lab])
(HERE / "hump_2018_2021.json").write_text(json.dumps(out, indent=1))
