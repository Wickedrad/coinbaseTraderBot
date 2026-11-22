"""Round 15 loops 3 and 4: USDT.D state, its mechanical pull on TradingView BTC.D, and USDT.D around past BTC.D drops.
Usage: python3 -I usdt_loops.py <data_dir> <out_json>"""
import json
import sys

import numpy as np
import pandas as pd

D = sys.argv[1]
OUT = sys.argv[2]


def ld(n):
    s = pd.read_csv(f"{D}/{n}_1d.csv")
    s["d"] = pd.to_datetime(s.ts, unit="ms").dt.normalize()
    s = s.drop_duplicates("d", keep="last").set_index("d")
    return s


def r(x, k=2):
    return None if x is None or (isinstance(x, float) and not np.isfinite(x)) else round(float(x), k)


raw = {n: ld(n) for n in ["BTC.D", "USDT.D", "USDC.D", "TOTAL", "BTCUSD", "ETHBTC", "OTHERS.D"]}
last_day = raw["BTC.D"].index[-1]
res = {"dataLastDailyBar": str(last_day.date())}

# weekly closes, weeks ending Sunday; a week whose last bar is not its Sunday is partial
def wk(n, col="c"):
    s = raw[n][col]
    w = s.resample("W-SUN").last()
    return w

partial = last_day.weekday() != 6
W = pd.DataFrame({n: wk(n) for n in raw})
Wh = pd.DataFrame({n: raw[n]["h"].resample("W-SUN").max() for n in ["USDT.D"]})
if partial:
    res["partialWeek"] = {"week": str(W.index[-1].date()), "barsSoFar": int((raw["BTC.D"].index > W.index[-2]).sum())}
Wc = W.iloc[:-1] if partial else W  # complete weeks only

# ---------------- loop 3: USDT.D state
u = raw["USDT.D"]
uc = u["c"]
uw = Wc["USDT.D"]
ath_d = uc.idxmax()
ath_w = uw.idxmax()
y26 = uc[uc.index >= "2026-01-01"]
y26w = uw[uw.index >= "2026-01-01"]
lows_since_jun = uw[uw.index >= "2026-06-28"]
retest = lows_since_jun.idxmin()
after = uw[uw.index >= retest]
streak = 0
for a, b in zip(after.values[:-1][::-1], after.values[1:][::-1]):
    if b > a:
        streak += 1
    else:
        break
res["usdt"] = {
    "lastDailyClose": {"date": str(uc.index[-1].date()), "level": r(uc.iloc[-1], 3)},
    "lastDailyHigh": r(u["h"].iloc[-1], 3),
    "lastCompleteWeek": {"week": str(uw.index[-1].date()), "close": r(uw.iloc[-1], 3)},
    "partialWeekSoFar": r(W["USDT.D"].iloc[-1], 3) if partial else None,
    "athDailyClose": {"date": str(ath_d.date()), "level": r(uc.max(), 3)},
    "athDailyHigh": {"date": str(u["h"].idxmax().date()), "level": r(u["h"].max(), 3)},
    "athWeeklyClose": {"week": str(ath_w.date()), "level": r(uw.max(), 3)},
    "high2026DailyClose": {"date": str(y26.idxmax().date()), "level": r(y26.max(), 3)},
    "high2026WeeklyClose": {"week": str(y26w.idxmax().date()), "level": r(y26w.max(), 3)},
    "retestLowSinceJun28": {"week": str(retest.date()), "level": r(uw[retest], 3)},
    "higherWeeklyClosesInARow": streak,
    "pctToAthDailyClose": r(100 * (uc.max() / uc.iloc[-1] - 1), 1),
    "round12Levels": {"head": 3.82, "flatNeckline": 5.86, "measuredTarget": round(5.86 + (5.86 - 3.82), 2),
                      "note": "round 12 (Nov 2): inverse head 2024-12-08 3.82, flat neckline 5.86, high 9.14 week 2026-06-28, retest low 6.32 week 2026-10-04; fails below 5.86, next leg above 9.14"},
}

# ---------------- loop 4a: mechanical pull of stablecoin share on TradingView BTC.D
S = (W["USDT.D"] + W["USDC.D"].fillna(0)) / 100.0
X = W["BTC.D"] / (1 - S)  # BTC share of the non-stable (USDT+USDC excluded) market
res["exStables"] = {"definition": "BTC.D / (1 - (USDT.D + USDC.D)/100); other stablecoins (DAI, USDe ...) are left in, so this slightly understates the stable share"}
def decomp(d0):
    i0 = W.index[W.index >= pd.Timestamp(d0)][0]
    i1 = W.index[-1]
    tv0, tv1 = W.loc[i0, "BTC.D"], W.loc[i1, "BTC.D"]
    x0, x1 = X[i0], X[i1]
    s0, s1 = S[i0], S[i1]
    # points of TV change from the stable share alone, holding X at its start value
    from_s = x0 * (1 - s1) - x0 * (1 - s0)
    return {"from": str(i0.date()), "to": str(i1.date()), "tvBtcd": [r(tv0), r(tv1)], "tvChange": r(tv1 - tv0),
            "exStables": [r(x0), r(x1)], "exStablesChange": r(x1 - x0), "stableShare": [r(100 * s0), r(100 * s1)],
            "tvPointsFromStableShareAlone": r(from_s), "tvPointsFromBtcShareOfNonStables": r((tv1 - tv0) - from_s)}
res["decompositionNote"] = "the end week is the partial week (data through dataLastDailyBar)" if partial else "complete weeks"
res["decomposition"] = [decomp(d) for d in ["2025-06-22", "2026-06-28", "2026-10-04", "2026-11-01"]]
# what-if: USDT.D rises to a level with the non-stable market falling (stables' $ cap fixed), BTC's share of non-stables fixed
u0, c0 = W["USDT.D"].iloc[-1] / 100, W["USDC.D"].iloc[-1] / 100
x_now = X.iloc[-1]
wi = []
for target in [8.5, 9.14, 9.28, 10.0, 11.0, 12.0]:
    f = (target / 100) / u0  # how much the stable share scales: non-stable cap must shrink until USDT.D reaches target
    s_new = (u0 + c0) * f
    wi.append({"usdtd": target, "stableShare": r(100 * s_new), "tvBtcdIfBtcShareOfNonStablesUnchanged": r(x_now * (1 - s_new)),
               "nonStableMarketChangePct": r(100 * ((1 - s_new) / s_new * (u0 + c0) / (1 - u0 - c0) - 1), 1)})
res["whatIf"] = {"start": {"week": str(W.index[-1].date()), "tvBtcd": r(W["BTC.D"].iloc[-1]), "exStables": r(x_now), "usdtd": r(100 * u0), "usdcd": r(100 * c0)},
                 "rows": wi, "levelsToCompare": {"round12FlatNeckline": 57.79, "smallTopNeckline": 58.58}}

# ---------------- loop 4b: BTC.D down-legs since 2018 and what USDT.D did
Wc = Wc.dropna(subset=["BTC.D", "USDT.D"])
x = Wc["BTC.D"].values
idx = Wc.index
piv = []
from itertools import pairwise
def zz(x, rev):
    p = [0]; d = 0; e = 0
    for i in range(1, len(x)):
        if d >= 0:
            if x[i] > x[e]: e = i
            elif x[e] - x[i] >= rev: p.append(e); d = -1; e = i; continue
        if d <= 0:
            if x[i] < x[e]: e = i
            elif x[i] - x[e] >= rev: p.append(e); d = 1; e = i
    p.append(e)
    return sorted(set(p))
legs = []
REV, MIN = 5.0, 7.0
P = zz(x, REV)
for a, b in pairwise(P):
    if x[a] - x[b] >= MIN and idx[a] >= pd.Timestamp("2017-12-01"):
        ia, ib = idx[a], idx[b]
        def ch(col, i0, i1, pct=False):
            v0, v1 = Wc.loc[i0, col], Wc.loc[i1, col]
            return r(100 * (v1 / v0 - 1), 1) if pct else r(v1 - v0, 2)
        pre = idx[max(0, a - 8)]
        u_win = Wc["USDT.D"].iloc[max(0, a - 52):a + 1]
        legs.append({
            "start": str(ia.date()), "end": str(ib.date()), "weeks": int(b - a),
            "tvBtcd": [r(x[a]), r(x[b])], "tvDrop": r(x[b] - x[a]),
            "exStablesDrop": r(X[ib] - X[ia]),
            "usdtdDuringLeg": ch("USDT.D", ia, ib), "usdtdLevel": [r(Wc.loc[ia, "USDT.D"], 2), r(Wc.loc[ib, "USDT.D"], 2)],
            "usdtd8wBeforeStart": ch("USDT.D", pre, ia),
            "usdtdAt52wHighWithin4wOfStart": bool(Wc["USDT.D"].iloc[max(0, a - 4):a + 5].max() >= u_win.max() - 1e-9),
            "btcusdDuringLegPct": ch("BTCUSD", ia, ib, True), "ethbtcDuringLegPct": ch("ETHBTC", ia, ib, True),
            "totalDuringLegPct": ch("TOTAL", ia, ib, True),
            "usdtdMinMaxInLeg": [r(Wc["USDT.D"].iloc[a:b + 1].min(), 2), r(Wc["USDT.D"].iloc[a:b + 1].max(), 2)],
            "usdtdNewHighInLeg": bool(Wc["USDT.D"].iloc[a + 1:b + 1].max() > Wc["USDT.D"].iloc[:a + 1].max()),
            "kind": ("alt-led" if (Wc.loc[ib, "ETHBTC"] / Wc.loc[ia, "ETHBTC"] - 1 >= 0.20 and Wc.loc[ib, "BTCUSD"] / Wc.loc[ia, "BTCUSD"] - 1 > -0.15)
                     else "crash-led"),
        })
res["btcdDownLegs"] = {"rule": f"zigzag on weekly TradingView BTC.D closes, reversal {REV} pts, legs with a drop of {MIN}+ pts starting Dec 2017 or later; alt-led = ETH/BTC up 20%+ over the leg and BTC/USD not down 15%+, else crash-led",
                       "legs": legs}

# ---------------- loop 4c: USDT.D weekly peaks and what BTC.D did next
uu = Wc["USDT.D"].values
UP = zz(np.log(uu), np.log(1.30))  # 30% reversals in USDT.D
peaks = []
for k, i in enumerate(UP):
    if 0 < k and i < len(uu) - 1 and uu[i] >= uu[UP[k - 1]] and idx[i] >= pd.Timestamp("2017-06-01"):
        row = {"week": str(idx[i].date()), "usdtd": r(uu[i]), "tvBtcd": r(x[i])}
        for h in (13, 26, 52):
            j = min(i + h, len(x) - 1)
            row[f"tvBtcdChange{h}w"] = r(x[j] - x[i]) if i + h < len(x) else None
            row[f"exStablesChange{h}w"] = r(X[idx[j]] - X[idx[i]]) if i + h < len(x) else None
        nxt = [l for l in legs if pd.Timestamp(l["start"]) >= idx[i] and l["kind"] == "alt-led"]
        row["nextAltLedLeg"] = ({"start": nxt[0]["start"], "weeksAfterPeak": int((pd.Timestamp(nxt[0]["start"]) - idx[i]).days // 7), "drop": nxt[0]["tvDrop"]} if nxt else None)
        peaks.append(row)
res["usdtPeaks"] = {"rule": "zigzag on log weekly USDT.D, 30% reversals; peaks from Jun 2017", "peaks": peaks}

json.dump(res, open(OUT, "w"), indent=1, default=str)
print(json.dumps({k: res[k] for k in ["dataLastDailyBar", "usdt"]}, indent=1, default=str))
