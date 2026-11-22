#!/usr/bin/env python3
"""Round 17 M2 nulls: is the child explained by the warped parent better than look-alikes are?

Same pipeline for the real pair and every null: full-traverse fit, amplitude profiled over the fixed grid, statistic =
log-likelihood gain per week over a flat fit (best of the grid).
  child-side (parent held fixed): (S1) amplitude-adjusted phase-randomised copies of the child's levels (same values, same
    spectrum, shape scrambled); (S2) the child's weekly changes resampled in blocks (mean 13 weeks) and added up.
  parent-side (child held fixed): placebo parents = same-length windows of every log value ratio series that ends before
    the child starts, scanned over start dates and both orientations, each rescaled to the true parent's range;
    and the rank of the true window among all same-length BTC.D windows before Dec 10 2017.
Run: python3 m2_null.py [draws per surrogate kind, default 200]   (about 35 minutes on 4 cores)
"""
import json, os, sys, time
from multiprocessing import Pool
import numpy as np, pandas as pd
import common as c, hmm, m2_align as m2

N = int(sys.argv[1]) if len(sys.argv) > 1 else 200
PAR, CH = m2.series()
X, Y = PAR.values, CH.values
REF = PAR.index.get_loc(c.P[-1])
END_MIN = REF - m2.TOL
MODEL = None


def stat(args):
    global MODEL
    y, x = args
    if MODEL is None:
        MODEL = hmm.Model(len(X))
    best, fits = hmm.profile(y, x, MODEL, end_min=END_MIN)
    return [best["gainPerWeek"], best["b"], best["inlier"]]


def iaaft(y, rng, iters=60):
    amp = np.abs(np.fft.rfft(y)); srt = np.sort(y)
    s = rng.permutation(y)
    for _ in range(iters):
        ph = np.angle(np.fft.rfft(s))
        s = np.fft.irfft(amp * np.exp(1j * ph), n=len(y))
        s = srt[np.argsort(np.argsort(s))]
    return s


def block(y, rng, mean=13):
    d = np.diff(y); n = len(d); out = np.empty(n); i = rng.integers(n)
    for t in range(n):
        if rng.random() < 1 / mean:
            i = rng.integers(n)
        out[t] = d[i % n]; i += 1
    return np.concatenate([[y[0]], y[0] + np.cumsum(out)])


def rescale(x):
    """A placebo window put on the true parent's scale (same range up to the top, same starting value)."""
    r = x[:REF + 1]; k = (X[:REF + 1].max() - X[:REF + 1].min()) / max(r.max() - r.min(), 1e-9)
    return X[0] + (x - x[0]) * k


def sources():
    btc = c.load("BTCUSD"); out = {}
    lb = c.lbtcd(); out["BTC.D before the parent"] = lb[:c.P[0] - pd.Timedelta(days=1)]
    o = c.load("OTHERS.D"); out["OTHERS.D before the parent"] = pd.Series(c.logit(o.values), index=o.index)[:c.P[0] - pd.Timedelta(days=1)]
    for n in ("LTC", "XRP", "DOGE", "XLM", "ETH"):
        p = c.load(f"{n}USD"); r = np.log(p / btc.reindex(p.index).ffill()).dropna()
        out[f"{n}/BTC before the child"] = r[:pd.Timestamp("2017-12-09")]
    return out


if __name__ == "__main__":
    t0 = time.time(); rng = np.random.default_rng(1700); L = len(X)
    jobs, tags = [(Y, X)], [("real", "")]
    for i in range(N):
        jobs.append((iaaft(Y, rng), X)); tags.append(("S1 phase-randomised child", str(i)))
    for i in range(N):
        jobs.append((block(Y, rng), X)); tags.append(("S2 block-resampled child", str(i)))
    for name, s in sources().items():
        v = s.values
        for st in range(0, len(v) - L + 1, 28):
            w = v[st:st + L]
            for sign in (1, -1):
                jobs.append((Y, rescale(sign * w))); tags.append(("placebo parent: " + name, f"{s.index[st].date()} {'+' if sign > 0 else '-'}"))
    lb = c.lbtcd()[:pd.Timestamp("2017-12-09")]; v = lb.values
    for st in range(lb.index.get_loc(c.P[0]) % 14, len(v) - L + 1, 14):          # every 14 days, on a grid that holds the true start
        jobs.append((Y, rescale(v[st:st + L]))); tags.append(("BTC.D window scan", str(lb.index[st].date())))
    step = int(os.environ.get("R17_STEP", "1"))                                  # smoke test: keep every step-th null
    keep = [0] + [i for i in range(1, len(jobs)) if i % step == 0 or tags[i] == ("BTC.D window scan", str(c.P[0].date()))]
    jobs, tags = [jobs[i] for i in keep], [tags[i] for i in keep]
    print(len(jobs), "fits on", os.cpu_count(), "cores", flush=True)
    with Pool(os.cpu_count()) as pool:
        res = pool.map(stat, jobs, chunksize=4)
    real = res[0][0]
    out = {"through": str(c.THROUGH.date()), "draws": N, "real": {"gainPerWeek": round(real, 4), "b": res[0][1], "inlier": round(res[0][2], 3)}, "nulls": {}, "minutes": round((time.time() - t0) / 60, 1)}
    groups = {}
    for (g, lab), r in zip(tags[1:], res[1:]):
        groups.setdefault(g, []).append((lab, r[0], r[1]))
    for g, rows in groups.items():
        v = np.array([r[1] for r in rows])
        o = {"n": len(v), "median": round(float(np.median(v)), 4), "p90": round(float(np.quantile(v, 0.9)), 4), "max": round(float(v.max()), 4),
             "shareAsGoodAsReal": round(float((v >= real).mean()), 4)}
        if g.startswith("placebo") or g.startswith("BTC.D window"):
            top = sorted(rows, key=lambda r: -r[1])[:3]
            o["best3"] = [[r[0], round(r[1], 4), r[2]] for r in top]
        if g.startswith("BTC.D window"):
            order = sorted(rows, key=lambda r: -r[1]); o["rankOfTrueWindow"] = 1 + [r[0] for r in order].index(str(c.P[0].date())) if str(c.P[0].date()) in [r[0] for r in order] else None
            o["windows"] = [[r[0], round(r[1], 4)] for r in rows]
        out["nulls"][g] = o
        print(g, {k: o[k] for k in o if k != "windows"}, flush=True)
    pl = [max(r[1] for r in rows) for g, rows in groups.items() if g.startswith("placebo")]
    out["bestOfScanPerPlaceboSource"] = {"values": [round(x, 4) for x in pl], "sourcesAsGoodAsReal": int(sum(x >= real for x in pl)), "of": len(pl)}
    print("real", out["real"], "best-of-scan", out["bestOfScanPerPlaceboSource"], "minutes", out["minutes"])
    (c.HERE / "m2_null.json").write_text(json.dumps(out, indent=1))
