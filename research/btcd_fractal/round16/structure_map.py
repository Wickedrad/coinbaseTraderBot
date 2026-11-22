#!/usr/bin/env python3
"""Round 16: lay the BTC.D structure dates onto BTC, alts and ETH/BTC in both eras.

Steven's matched BTC.D structures (round 14 anchors plus the tops) give a
piecewise-linear time map from the parent (2016-17) to the child (2017-now).
This script (1) measures every other chart between the same structure dates,
(2) finds each chart's biggest fall and rise inside every matched stretch and
where in the stretch they sit, (3) scores how well the child's charts follow
the parent's on the mapped clock against random clocks, and (4) lists the
order of events after the top.  Run: python3 structure_map.py [data_dir]
"""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).resolve().parent
DATA = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent / "data"
P = pd.to_datetime(["2016-06-19", "2016-07-24", "2016-11-20", "2016-12-18", "2017-02-26"])
C = pd.to_datetime(["2017-12-10", "2018-01-14", "2019-09-08", "2021-05-16", "2025-06-22"])
NAMES = ["waterfall start", "waterfall low", "hump", "mid-structure fall low", "top"]
SEG = ["waterfall", "rise to the hump", "mid-structure fall", "plateau to the top"]
STEP_DAYS = pd.to_datetime(["2016-10-09", "2016-12-16", "2017-04-02", "2017-05-07", "2017-05-09", "2017-07-14"])


def load(n):
    d = pd.read_csv(DATA / f"{n}_1d.csv")
    d["ts"] = pd.to_datetime(d["ts"], unit="ms")
    return d.set_index("ts")["c"].astype(float)


def all_series():
    btcd, btc, tot, t2, eth = load("BTC.D"), load("BTCUSD"), load("TOTAL"), load("TOTAL2"), load("ETHBTC")
    idx = pd.date_range(tot.index[0], tot.index[-1], freq="D")
    f = lambda s: s.reindex(idx).ffill()
    st = (f(load("USDT.D")).fillna(0) + f(load("USDC.D")).fillna(0)) / 100
    alts = f(t2) - f(tot) * st            # alts without USDT and USDC
    r = np.log(alts).diff()
    r[r.index.isin(STEP_DAYS)] = 0.0        # TradingView index steps taken out
    alts_ns = np.exp(r.fillna(0).cumsum())
    return {"BTC.D": f(btcd), "BTC": f(btc), "alts": alts, "alts (index steps out)": alts_ns,
            "ETH/BTC": f(eth), "whole market": f(tot)}


def day(t):
    return np.asarray((pd.DatetimeIndex(np.atleast_1d(t)) - pd.Timestamp("2010-01-01")).days, float)


def to_child(pd_dates, c=C, pace_after=None):
    x, xp, fp = day(pd_dates), day(P), day(c)
    y = np.interp(x, xp, fp)
    s = pace_after if pace_after else (fp[-1] - fp[-2]) / (xp[-1] - xp[-2])
    y = np.where(x > xp[-1], fp[-1] + (x - xp[-1]) * s, y)
    return pd.Timestamp("2010-01-01") + pd.to_timedelta(np.round(y), unit="D")


def to_parent(c_dates, pace_after=None):
    x, xp, fp = day(c_dates), day(C), day(P)
    y = np.interp(x, xp, fp)
    s = pace_after if pace_after else (xp[-1] - xp[-2]) / (fp[-1] - fp[-2])
    y = np.where(x > xp[-1], fp[-1] + (x - xp[-1]) / s, y)
    return pd.Timestamp("2010-01-01") + pd.to_timedelta(np.round(y), unit="D")


def swings(s):
    """biggest fall (peak, trough) and biggest rise (trough, peak) on daily closes"""
    s = s.dropna()
    dd = s / s.cummax() - 1
    t = dd.idxmin(); p = s.loc[:t].idxmax()
    ru = s / s.cummin() - 1
    k = ru.idxmax(); b = s.loc[:k].idxmin()
    return {"fall": (p, t, float(dd.min())), "rise": (b, k, float(ru.max()))}


def frac(t, a, b):
    return float((t - a).days / (b - a).days)


def main():
    S = all_series()
    today = S["BTC"].index[-1]
    out = {"dataThrough": str(today.date()), "anchors": {"parent": [str(d.date()) for d in P], "child": [str(d.date()) for d in C]}}

    print("== A. matched stretches: length, pace, and what each chart did (multiple) ==")
    rows = []
    for i in range(4):
        pw, cw = (P[i + 1] - P[i]).days / 7, (C[i + 1] - C[i]).days / 7
        r = {"stretch": SEG[i], "parentWeeks": round(pw, 1), "childWeeks": round(cw, 1), "pace": round(cw / pw, 1)}
        for n, s in S.items():
            if s.asof(P[i]) != s.asof(P[i]):
                continue
            r[n] = [round(float(s.asof(P[i + 1]) / s.asof(P[i])), 3), round(float(s.asof(C[i + 1]) / s.asof(C[i])), 3)]
        r["BTC.D pts"] = [round(float(S["BTC.D"].asof(P[i + 1]) - S["BTC.D"].asof(P[i])), 2), round(float(S["BTC.D"].asof(C[i + 1]) - S["BTC.D"].asof(C[i])), 2)]
        rows.append(r); print(r)
    out["stretches"] = rows

    print("\n== B. biggest fall and rise of each chart inside each matched stretch, and where in the stretch ==")
    feats = []
    for i in range(4):
        for n in ("BTC.D", "BTC", "alts (index steps out)", "ETH/BTC"):
            s = S[n]
            try:
                a, b = swings(s.loc[P[i]:P[i + 1]]), swings(s.loc[C[i]:C[i + 1]])
            except Exception:
                continue
            for k in ("fall", "rise"):
                (p0, p1, pv), (c0, c1, cv) = a[k], b[k]
                row = {"stretch": SEG[i], "chart": n, "kind": k,
                       "parent": [str(p0.date()), str(p1.date()), round(pv * 100, 1), round(frac(p0, P[i], P[i + 1]), 2), round(frac(p1, P[i], P[i + 1]), 2)],
                       "child": [str(c0.date()), str(c1.date()), round(cv * 100, 1), round(frac(c0, C[i], C[i + 1]), 2), round(frac(c1, C[i], C[i + 1]), 2)],
                       "parentEndMappedToChild": str(to_child([p1])[0].date()),
                       "weeksOff": round((c1 - to_child([p1])[0]).days / 7, 1)}
                feats.append(row); print(row)
    out["features"] = feats

    print("\n== C. does the child follow the parent on the mapped clock? (P0 to top, daily, linear trend removed) ==")
    grid = pd.date_range(P[0], P[-1], freq="D")
    xg = day(grid)
    rng = np.random.default_rng(16)

    def score(n, c, mode="detrended"):
        p = np.log(S[n].reindex(grid).ffill().values)
        cd = to_child(grid, c=c)
        q = np.log(S[n].reindex(cd).values)
        ok = np.isfinite(p) & np.isfinite(q)
        if ok.sum() < 50:
            return np.nan
        if mode == "weekly changes":
            i = np.where(ok)[0][::7]
            return float(np.corrcoef(np.diff(p[i]), np.diff(q[i]))[0, 1])
        det = lambda v: v[ok] - np.polyval(np.polyfit(xg[ok], v[ok], 1), xg[ok])
        return float(np.corrcoef(det(p), det(q))[0, 1])

    c0, c4 = day([C[0]])[0], day([C[-1]])[0]
    base = pd.Timestamp("2010-01-01")
    mk = lambda mid: pd.DatetimeIndex([C[0]]).append(base + pd.to_timedelta(np.round(mid), unit="D")).append(pd.DatetimeIndex([C[-1]]))
    rand = [mk(np.sort(rng.uniform(c0 + 7, c4 - 7, 3))) for _ in range(2000)]   # any interior clock
    near = []                                                                   # the chosen dates moved by up to a year
    while len(near) < 2000:
        mid = day(C[1:4]) + rng.uniform(-365, 365, 3)
        if c0 + 7 < mid[0] < mid[1] < mid[2] < c4 - 7:
            near.append(mk(mid))
    corr = {}
    for n in ("BTC.D", "BTC", "alts (index steps out)", "ETH/BTC", "whole market"):
        corr[n] = {}
        for mode in ("detrended", "weekly changes"):
            obs = score(n, C, mode)
            n1 = np.array([score(n, r, mode) for r in rand]); n2 = np.array([score(n, r, mode) for r in near])
            corr[n][mode] = {"mapped": round(obs, 3), "shareAnyClockAsGood": round(float(np.nanmean(n1 >= obs)), 3),
                             "shareNearbyClockAsGood": round(float(np.nanmean(n2 >= obs)), 3)}
        print(n, corr[n])
    out["followsOnMappedClock"] = corr

    print("\n== D. after the top: order of events ==")
    def after(n, t0, t1):
        return S[n].loc[t0:t1]
    ev = {}
    for era, t0, t1 in (("parent", P[-1], pd.Timestamp("2017-05-21")), ("child", C[-1], today)):
        b, d, e, a = after("BTC", t0, t1), after("BTC.D", t0, t1), after("ETH/BTC", t0, t1), after("alts (index steps out)", t0, t1)
        sw = swings(b)
        pk, tr, dep = sw["fall"]
        ev[era] = {
            "top": str(t0.date()), "through": str(t1.date()),
            "BTC at top": round(float(b.iloc[0]), 1),
            "BTC high after top": [str(b.idxmax().date()), round(float(b.max()), 1), round(float(b.max() / b.iloc[0] - 1) * 100, 1)],
            "BTC biggest fall": [str(pk.date()), str(tr.date()), round(dep * 100, 1)],
            "BTC.D low": [str(d.idxmin().date()), round(float(d.min()), 2), round(float(d.min() / d.iloc[0]), 3)],
            "ETH/BTC high": [str(e.idxmax().date()), round(float(e.max()), 4), round(float(e.max() / e.iloc[0]), 2)],
            "alts high": [str(a.idxmax().date()), round(float(a.max() / a.iloc[0]), 2)],
            "at BTC fall low": {"BTC.D x": round(float(d.asof(tr) / d.asof(pk)), 3), "ETH/BTC x": round(float(e.asof(tr) / e.asof(pk)), 2),
                                "alts x": round(float(a.asof(tr) / a.asof(pk)), 2), "BTC.D pts": round(float(d.asof(tr) - d.asof(pk)), 2)},
            "weeks top to BTC high": round((b.idxmax() - t0).days / 7, 1), "weeks top to BTC fall low": round((tr - t0).days / 7, 1),
        }
        print(era, ev[era])
    out["afterTop"] = ev
    pp = pd.to_datetime(["2017-03-03", "2017-03-10", "2017-03-24", "2017-04-02", "2017-04-30", "2017-05-21"])
    out["parentDatesOnChildClock"] = {}
    for pace in (None, 8.3, 5.1, 1.0):
        lab = "plateau pace" if pace is None else f"{pace}:1"
        out["parentDatesOnChildClock"][lab] = {str(a.date()): str(b.date()) for a, b in zip(pp, to_child(pp, pace_after=pace))}
        print(lab, out["parentDatesOnChildClock"][lab])
    cc = pd.to_datetime(["2025-09-14", "2025-10-06", str(today.date())])
    out["childDatesOnParentClock"] = {str(a.date()): str(b.date()) for a, b in zip(cc, to_parent(cc))}
    print("child dates on the parent clock at the plateau pace", out["childDatesOnParentClock"])

    print("\n== E. same test with the hump at Jan 3 2021 (C2') ==")
    C2 = C.copy().to_series().reset_index(drop=True); C2[2] = pd.Timestamp("2021-01-03"); C2 = pd.DatetimeIndex(C2)
    out["followsOnMappedClockC2prime"] = {}
    for n in ("BTC.D", "BTC", "alts (index steps out)", "ETH/BTC", "whole market"):
        obs = score(n, C2); nul = np.array([score(n, r) for r in rand])
        out["followsOnMappedClockC2prime"][n] = {"mapped": round(obs, 3), "shareAnyClockAsGood": round(float(np.nanmean(nul >= obs)), 3)}
        print(n, out["followsOnMappedClockC2prime"][n])

    print("\n== F. how much bigger the child's BTC.D moves are (log of the ratio, child / parent) ==")
    d = S["BTC.D"]; b = S["BTC"]
    mag = {}
    for i in range(4):
        mag[SEG[i]] = round(float(np.log(d.asof(C[i + 1]) / d.asof(C[i])) / np.log(d.asof(P[i + 1]) / d.asof(P[i]))), 1)
    p_hi, c_hi = pd.Timestamp(ev["parent"]["BTC biggest fall"][0]), pd.Timestamp(ev["child"]["BTC biggest fall"][0])
    mag["top to BTC's high after it"] = round(float(np.log(d.asof(c_hi) / d.asof(C[-1])) / np.log(d.asof(p_hi) / d.asof(P[-1]))), 1)
    print(mag); out["btcdMagnification"] = mag
    now_ratio = float(d.iloc[-1] / d.asof(C[-1])); lo_ratio = float(d.loc[C[-1]:].min() / d.asof(C[-1]))
    par = d.loc[P[-1]:"2017-04-01"] / d.asof(P[-1])
    place = {}
    for m_ in sorted(set(mag.values())):
        eq = float(np.exp(np.log(now_ratio) / m_))
        hit = par[par <= eq]
        place[str(m_)] = {"parentEquivalentRatio": round(eq, 4), "parentLevel": round(eq * float(d.asof(P[-1])), 2),
                          "firstParentDayAtOrBelow": str(hit.index[0].date()) if len(hit) else None}
    out["todayByScaledLevel"] = {"childRatioToTop": round(now_ratio, 4), "childLowRatioToTop": round(lo_ratio, 4), "byMagnification": place}
    print("today's BTC.D as a share of its top", round(now_ratio, 4), place)
    first_leg = {"parent Feb 26 to Apr 1 2017 (before the Apr 2 index step)": {n: round(float(S[n].asof("2017-04-01") / S[n].asof(P[-1])), 3) for n in ("BTC.D", "ETH/BTC", "alts (index steps out)", "BTC")},
                 "parent Feb 26 to Apr 2 2017 (as drawn)": {"BTC.D": round(float(d.asof("2017-04-02") / d.asof(P[-1])), 3)},
                 "parent leg start": "ETH/BTC and BTC.D break on 2017-03-10/11, 7-8 days after BTC's high",
                 "child Jun 22 to Sep 13 2025": {n: round(float(S[n].asof("2025-09-13") / S[n].asof(C[-1])), 3) for n in ("BTC.D", "ETH/BTC", "alts (index steps out)", "BTC")},
                 "child Jun 22 to Oct 6 2025": {n: round(float(S[n].asof("2025-10-06") / S[n].asof(C[-1])), 3) for n in ("BTC.D", "ETH/BTC", "alts (index steps out)", "BTC")},
                 "child Jun 22 2025 to now": {n: round(float(S[n].iloc[-1] / S[n].asof(C[-1])), 3) for n in ("BTC.D", "ETH/BTC", "alts (index steps out)", "BTC")},
                 "parent Feb 26 to Mar 3 2017": {n: round(float(S[n].asof("2017-03-03") / S[n].asof(P[-1])), 3) for n in ("BTC.D", "ETH/BTC", "alts (index steps out)", "BTC")}}
    out["firstLeg"] = first_leg
    for k, v in first_leg.items():
        print(k, v)
    # BTC price: the crash inside the plateau, and the parent's March drop scaled the same way
    pf, cf = swings(b.loc[P[3]:P[4]])["fall"][2], swings(b.loc[C[3]:C[4]])["fall"][2]
    k_ = float(np.log(1 + cf) / np.log(1 + pf))
    dip1 = float(b.loc["2017-03-03":"2017-03-10"].min() / b.asof("2017-03-03") - 1)
    full = ev["parent"]["BTC biggest fall"][2] / 100
    chi = float(b.asof(c_hi))
    out["btcScaling"] = {"plateauCrash": [round(pf * 100, 1), round(cf * 100, 1)], "logMagnification": round(k_, 2),
                         "parentFirstDipMar3to10": round(dip1 * 100, 1), "scaled": round(float(np.exp(np.log(1 + dip1) * k_) - 1) * 100, 1),
                         "parentFullMar3to24": round(full * 100, 1), "scaledFull": round(float(np.exp(np.log(1 + full) * k_) - 1) * 100, 1),
                         "scaledFullPrice": round(chi * float(np.exp(np.log(1 + full) * k_))), "childSoFarCloseLow": ev["child"]["BTC biggest fall"][2],
                         "childNow": round(float(b.iloc[-1] / chi - 1) * 100, 1)}
    print(out["btcScaling"])
    # day by day after the top on the plateau clock
    g = pd.date_range(P[-1], "2017-05-21", freq="D"); cd = to_child(g)
    tab = []
    for a_, c_ in zip(g, cd):
        r = {"parent": str(a_.date()), "child": str(c_.date()) if c_ <= today else None}
        for n in ("BTC", "BTC.D", "ETH/BTC", "alts (index steps out)"):
            r["P " + n] = round(float(S[n].asof(a_) / S[n].asof(P[-1])), 3)
            r["C " + n] = round(float(S[n].asof(c_) / S[n].asof(C[-1])), 3) if c_ <= today else None
        tab.append(r)
    out["afterTopDayByDay"] = tab
    lead = pd.Timestamp("2017-03-10")
    out["legLateWeeks"] = round((today - to_child([lead])[0]).days / 7, 1)
    print("parent leg start Mar 10 2017 on the plateau clock:", to_child([lead])[0].date(), "weeks late:", out["legLateWeeks"])
    (HERE / "structure_map.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
