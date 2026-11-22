#!/usr/bin/env python3
"""Round 17 M4: does any clock order the pace of the five matched stretches?

Each law says log(pace of a stretch) = alpha + beta * z, with z known the week before the child's stretch starts
(nothing from inside the stretch is used). Scored by leave-one-stretch-out error of log pace. One family-wide exact
permutation test (the five paces dealt out in all 120 orders, best law of the family each time) and a set of random
trending clocks say how easy it is to "explain" five rising numbers. Run: python3 m4_laws.py
"""
import itertools, json, warnings
import numpy as np, pandas as pd
import common as c

warnings.simplefilter("ignore")
dl = c.lbtcd(); btc = np.log(c.load("BTCUSD")); tot = c.load("TOTAL")
TRAIL = 26


def tvar(s, t, weeks=TRAIL):
    seg = s[t - pd.Timedelta(weeks=weeks + 1):t - pd.Timedelta(weeks=1)].dropna()
    return float((seg.diff().dropna() ** 2).mean())


def dc_rate(s, t, theta=0.05, weeks=TRAIL):
    """Directional changes of size theta (logit) per week over the trailing window: the intrinsic-time clock rate."""
    seg = s[t - pd.Timedelta(weeks=weeks + 1):t - pd.Timedelta(weeks=1)].dropna().values
    hi = lo = seg[0]; mode = 0; n = 0
    for v in seg[1:]:
        if mode == 0:
            hi, lo = max(hi, v), min(lo, v)
            if hi - v >= theta: mode, lo, n = -1, v, n + 1
            elif v - lo >= theta: mode, hi, n = 1, v, n + 1
        elif mode == 1:
            if v > hi: hi = v
            elif hi - v >= theta: mode, lo, n = -1, v, n + 1
        else:
            if v < lo: lo = v
            elif v - lo >= theta: mode, hi, n = 1, v, n + 1
    return (n + 0.5) / weeks


def covariates(C):
    z = {"L1 position along the parent (weeks)": [(c.P[i] - c.P[0]).days / 7 for i in range(5)],
         "L2 own volatility (BTC.D, trailing 26 weeks)": [-np.log(tvar(dl, C[i])) for i in range(5)],
         "L3 BTC price volatility (trailing 26 weeks)": [-np.log(tvar(btc, C[i])) for i in range(5)],
         "L4 market size (total value at the start)": [np.log(float(tot.asof(C[i]))) for i in range(5)],
         "L5 directional changes per week (BTC.D, 0.05 logit)": [-np.log(dc_rate(dl, C[i])) for i in range(5)]}
    for n in ("SPX", "DXY", "EURUSD"):
        s = np.log(c.load(n)); z[f"placebo clock: {n} volatility"] = [-np.log(tvar(s, C[i])) for i in range(5)]
    return {k: np.array(v, float) for k, v in z.items()}


def loo(z, y):
    e = []
    for i in range(len(y)):
        k = np.arange(len(y)) != i
        if z is None:
            pred = y[k].mean()
        else:
            b, a = np.polyfit(z[k], y[k], 1); pred = a + b * z[i]
        e.append(pred - y[i])
    return float(np.sqrt(np.mean(np.square(e)))), [round(float(x), 2) for x in e]


def spearman(a, b):
    r = lambda v: pd.Series(v).rank().values
    return float(np.corrcoef(r(a), r(b))[0, 1])


out = {"through": str(c.THROUGH.date()), "trailWeeks": TRAIL, "readings": {}}
rng = np.random.default_rng(174)
for top in c.C_TOPS:
    C = c.child_anchors(top, 1)
    y = np.log([(C[i + 1] - C[i]).days / (c.P[i + 1] - c.P[i]).days for i in range(5)])
    Z = covariates(C)
    rows = {"L0 constant pace": {"looRmse": round(loo(None, y)[0], 3), "looErrors": loo(None, y)[1]}}
    for k, z in Z.items():
        r, e = loo(z, y); b, a = np.polyfit(z, y, 1)
        rows[k] = {"looRmse": round(r, 3), "looErrors": e, "slope": round(float(b), 2), "rank correlation": round(spearman(z, y), 2), "z": [round(float(v), 2) for v in z]}
    laws = [k for k in Z if k.startswith("L")]
    best = min(laws, key=lambda k: rows[k]["looRmse"]); obs = rows[best]["looRmse"]
    perm_best, per_law = [], {k: 0 for k in laws}
    perms = list(itertools.permutations(range(5)))
    for p in perms:
        yp = y[list(p)]; sc = {k: loo(Z[k], yp)[0] for k in laws}
        perm_best.append(min(sc.values()))
        for k in laws:
            per_law[k] += sc[k] <= rows[k]["looRmse"] + 1e-12
    for k in laws:
        rows[k]["permutation p (this law alone)"] = round(per_law[k] / len(perms), 3)
    # random trending clocks: a random walk over the five stretches, as many as you like
    rw = [loo(np.cumsum(rng.normal(0.5, 1.0, 5)), y)[0] for _ in range(2000)]
    out["readings"][top] = {"pace": [round(float(np.exp(v)), 1) for v in y], "laws": rows, "bestLaw": best, "bestLooRmse": obs,
                            "familyPermutationP": round(float(np.mean(np.array(perm_best) <= obs + 1e-12)), 3),
                            "randomTrendingClocksAsGood": round(float(np.mean(np.array(rw) <= obs)), 3),
                            "errorMeaning": "looRmse is in log units: 0.69 means a factor of 2, 1.1 a factor of 3"}
    print("== top =", top, "pace", out["readings"][top]["pace"])
    for k, r in rows.items():
        print(f"  {k[:52]:52s} loo {r['looRmse']:>6} rank {r.get('rank correlation', '')!s:>6} slope {r.get('slope', '')!s:>6} p {r.get('permutation p (this law alone)', '')!s:>6} errs {r['looErrors']}")
    print("  best", best, obs, "family p", out["readings"][top]["familyPermutationP"], "random trending clocks as good", out["readings"][top]["randomTrendingClocksAsGood"])
    print("  child trailing BTC.D vol/day", [round(float(np.sqrt(tvar(dl, C[i]))), 4) for i in range(5)], "BTC", [round(float(np.sqrt(tvar(btc, C[i]))), 4) for i in range(5)], "cap $bn", [round(float(tot.asof(C[i])) / 1e9) for i in range(5)])
# what the volatility clock reads today (description, not a forecast)
now = c.THROUGH
out["today"] = {"btcdVolPerDay26w": round(float(np.sqrt(tvar(dl, now + pd.Timedelta(weeks=1)))), 4), "btcVolPerDay26w": round(float(np.sqrt(tvar(btc, now + pd.Timedelta(weeks=1)))), 4),
                "dcPerWeek": round(dc_rate(dl, now + pd.Timedelta(weeks=1)), 2), "totalBn": round(float(tot.asof(now)) / 1e9)}
print("today", out["today"])
(c.HERE / "m4_laws.json").write_text(json.dumps(out, indent=1))
