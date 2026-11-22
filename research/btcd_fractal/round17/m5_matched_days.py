#!/usr/bin/env python3
"""Round 17 M5: the matched days read on other assets and key charts.

For each matched stretch of the settled anchors: what every chart did in the parent's stretch and in the child's
(multiple = end / start), and whether the direction agrees. Then one test per chart: sampled along the BTC.D time map,
do the child's weekly changes follow the parent's better than along nearby maps (inner anchors moved up to a year)?
Charts that are near mirror images of BTC.D (alts against BTC) agree by construction and are marked.
Run: python3 m5_matched_days.py [nearby maps, default 1000]
"""
import json, sys
import numpy as np, pandas as pd
import common as c

DRAWS = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
btc = c.load("BTCUSD"); tot = c.load("TOTAL"); t2 = c.load("TOTAL2")
idx = pd.date_range("2014-01-01", c.THROUGH, freq="D")
f = lambda s: s.reindex(idx).ffill()
st = (f(c.load("USDT.D")).fillna(0) + f(c.load("USDC.D")).fillna(0)) / 100
alts = f(t2) - f(tot) * st
r = np.log(alts).diff(); r[r.index.isin(c.STEP_DAYS)] = 0.0
alts_ns = np.exp(r.fillna(0).cumsum())
S = {"BTC.D (logit)": (np.exp(f(c.lbtcd())), "the map itself"), "BTC in USD": (f(btc), "independent"), "whole market value": (f(tot), "independent"),
     "alts without stablecoins (index steps out)": (alts_ns, "independent"), "alts against BTC": (alts_ns / f(btc), "mirror of BTC.D"),
     "ETH/BTC": (f(c.load("ETHBTC")), "mirror of BTC.D"), "OTHERS.D": (f(c.load("OTHERS.D")), "mirror of BTC.D")}
for n in ("XRP", "XLM", "DOGE", "LTC"):
    p = f(c.load(f"{n}USD")); S[f"{n} in USD"] = (p, "independent"); S[f"{n}/BTC"] = (p / f(btc), "mirror of BTC.D")
for n, lab in (("DXY", "US dollar index"), ("SPX", "S&P 500"), ("US10Y", "US 10-year yield"), ("M2", "US M2")):
    S[lab] = (f(c.load(n)), "macro")
S["USDT.D"] = (f(c.load("USDT.D")), "child only (under 0.2% of the market in the parent)")
v = lambda s, t: float(s.asof(pd.Timestamp(t))) if pd.Timestamp(t) >= s.first_valid_index() else float("nan")
out = {"through": str(c.THROUGH.date()), "coverage": {k: str(s.first_valid_index().date()) for k, (s, _) in S.items()}, "stretches": {}, "anchorsLevels": {}, "followsMap": {}}

for top in c.C_TOPS:
    C = c.child_anchors(top, 1); rows = []
    for k, (s, kind) in S.items():
        if k == "USDT.D":
            continue
        pm = [v(s, c.P[i + 1]) / v(s, c.P[i]) for i in range(5)]; cm = [v(s, C[i + 1]) / v(s, C[i]) for i in range(5)]
        agree = [None if not np.isfinite(a) else bool((a > 1) == (b > 1)) for a, b in zip(pm, cm)]
        rows.append({"chart": k, "kind": kind, "parentMultiple": [None if not np.isfinite(x) else round(x, 3) for x in pm], "childMultiple": [round(x, 3) for x in cm],
                     "sameDirection": agree, "agreeCount": [int(sum(1 for a in agree if a)), int(sum(1 for a in agree if a is not None))]})
    out["stretches"][top] = rows
    print("== stretches, top =", top)
    for r_ in rows:
        print(f"  {r_['chart'][:38]:38s} {r_['kind'][:10]:10s} parent {r_['parentMultiple']} child {r_['childMultiple']} agree {r_['agreeCount']}")
C = c.child_anchors("today", 1)
for k, (s, kind) in S.items():
    out["anchorsLevels"][k] = {"parent": [None if not np.isfinite(v(s, t)) else float(f"{v(s, t):.4g}") for t in c.P], "child": [float(f"{v(s, t):.4g}") for t in C]}

# does each chart follow the BTC.D map better than nearby maps?
day = lambda t: np.asarray((pd.DatetimeIndex(np.atleast_1d(t)) - pd.Timestamp("2010-01-01")).days, float)
base = pd.Timestamp("2010-01-01"); rng = np.random.default_rng(175)
def score(s, A, B):
    g = pd.date_range(A[0], A[-1], freq="7D")
    m = base + pd.to_timedelta(np.round(np.interp(day(g), day(A), day(B))), unit="D")
    p, q = np.log(s.reindex(g).values), np.log(s.reindex(m).values)
    ok = np.isfinite(p) & np.isfinite(q)
    if ok.sum() < 12:
        return float("nan")
    dp, dq = np.diff(p[ok]), np.diff(q[ok])
    return float(np.corrcoef(dp, dq)[0, 1])
for top in c.C_TOPS:
    B = c.child_anchors(top, 1); near = []
    b0, b1 = day([B[0]])[0], day([B[-1]])[0]
    while len(near) < DRAWS:
        mid = day(B[1:-1]) + rng.uniform(-365, 365, len(B) - 2)
        if b0 + 7 < mid[0] and mid[-1] < b1 - 7 and np.all(np.diff(mid) > 0):
            near.append(pd.DatetimeIndex([B[0]]).append(base + pd.to_timedelta(np.round(mid), unit="D")).append(pd.DatetimeIndex([B[-1]])))
    res = {}
    for k, (s, kind) in S.items():
        if k == "USDT.D":
            continue
        obs = score(s, c.P, B)
        if not np.isfinite(obs):
            res[k] = None; continue
        nul = np.array([score(s, c.P, x) for x in near])
        res[k] = {"kind": kind, "matchOfWeeklyChanges": round(obs, 2), "shareOfNearbyMapsAsGood": round(float(np.nanmean(nul >= obs)), 3)}
    out["followsMap"][top] = res
    print("== follows the BTC.D map, top =", top)
    for k, r_ in res.items():
        print(f"  {k[:38]:38s}", r_)
(c.HERE / "m5_matched_days.json").write_text(json.dumps(out, indent=1))
