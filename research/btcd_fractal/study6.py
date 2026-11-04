#!/usr/bin/env python3
"""Round 6: the same fractal walk on USDT.D, TOTAL3 and ETH/BTC, then the four together (Steven, 2026-11-01 23:56 UTC).

Same steps as BTC.D rounds 1-3, per series:
  1. parent = the 2016-17 cycle, child = 2018 to now; open-end time warp with the dynamic level map; 4 settings
     (fixed / local level map x shape weight 1 / 3);
  2. walk-forward track: where the warp placed "now" at every past date; skill at 13/26/52 weeks against no-change;
  3. placebo-parent adversary (IAAFT, block shuffle, matched random walk), each placebo searching the same 4 settings;
  4. stage dilation along the final warp.
Each series is put on one scale so the warp's thresholds (6-point reversals, 15-point waterfalls) mean the same:
  BTC.D logit, USDT.D log, TOTAL3 and ETH/BTC minus log (inverted, so the alt-season move is a fall in all four),
  then scaled so the parent window spans 60 points like BTC.D's. Errors are reported in those points and in native
  units. TOTAL3 exists only from Jul 2017, so its parent is the last rally + final waterfall (Jul 2017 - Mar 2018)
  and its child starts Apr 2018.
Then the four together:
  5. each series' path through the 26 weeks before and after each BTC.D waterfall start (Nov 2016, Dec 2017, Jan 2021)
     and the medium falls;
  6. lead/lag: does a series' 4-week change lead BTC.D's, at 0-26 weeks, against a circular-shift null;
  7. fractal confluence: at each past date, how many of the four warps stood within 8 parent weeks of one of their
     parent's waterfalls; precision of that count against the falls that followed.
"""
import argparse
import itertools
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from study import block_shuffle, iaaft, load, matched_walk, waterfalls, weekly  # noqa: E402
from study2 import evaluate2  # noqa: E402
from study3 import laws, stage_table, stages_of  # noqa: E402
import study4  # noqa: E402

SERIES = {
    # name: (transform, parent from, parent to, child from, native unit, sign note)
    "BTC.D": ("logit", "2016-01-01", "2018-03-01", "2018-01-01", "pct points", "fall = alt season"),
    "USDT.D": ("log", "2016-01-01", "2018-03-01", "2018-01-01", "% of itself", "log scale; sign reported as is"),
    "TOTAL3": ("neglog", "2017-07-14", "2018-03-01", "2018-04-01", "% of itself", "inverted: a fall here = TOTAL3 rising"),
    "ETHBTC": ("neglog", "2016-07-01", "2018-03-01", "2018-01-01", "% of itself", "inverted: a fall here = ETH/BTC rising"),
}


def transform(x, how):
    x = np.asarray(x, dtype=float)
    if how == "logit":
        p = np.clip(x / 100.0, 0.005, 0.995)
        return np.log(p / (1 - p))
    if how == "log":
        return np.log(np.clip(x, 1e-6, None))
    if how == "neglog":
        return -np.log(np.clip(x, 1e-9, None))
    return x


def native_move(points, how, scale, level=None):
    """A move of `points` on the common scale, in native units (pct points for logit at `level`, % of itself for log)."""
    u = points / scale
    if how == "logit":
        p = np.clip((level or 50.0) / 100.0, 0.005, 0.995)
        l0 = np.log(p / (1 - p))
        return 100 * (1 / (1 + np.exp(-(l0 + u))) - p)
    return 100 * (np.exp(abs(u)) - 1) * np.sign(u) * (1 if how == "log" else -1)


WF_MIN = 12.0  # waterfall threshold on the common scale (BTC.D's Dec 2017 fall is 14.7 points in scaled logit)
_G = {}


def _init(G):
    _G.update(G)


def _job(args):
    name, cfg = args
    r = evaluate2(_G["childs"][name], _G["parents"][name], cfg)
    r["series"] = name
    return r


def _placebo(args):
    name, kind, par, cfgs = args
    ch = _G["childs"][name]
    best_s, best_ic = 9e9, -9.0
    for c in cfgs:
        r = evaluate2(ch, par, c, step=8, want=False)
        best_s = min(best_s, r["score"])
        best_ic = max(best_ic, r["skill"].get("h26", {}).get("ic") or -9.0)
    return {"series": name, "kind": kind, "bestScore": best_s, "bestIc": best_ic}


def spearman(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 20:
        return None
    return float(pd.Series(a[m]).rank().corr(pd.Series(b[m]).rank()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--placebos", type=int, default=30, help="per kind per series")
    ap.add_argument("--nulls", type=int, default=400)
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 2)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    t0 = time.time()
    rng = np.random.default_rng(6)
    raw = {n: weekly(load(a.data, n)) for n in SERIES}
    parents, childs, pidx, cidx, scale, meta = {}, {}, {}, {}, {}, {}
    for n, (how, pf, pt, cf, unit, note) in SERIES.items():
        w = raw[n]
        y = pd.Series(transform(w.values, how), index=w.index)
        par = y[(y.index >= pd.Timestamp(pf)) & (y.index < pd.Timestamp(pt))]
        s = 60.0 / max(par.max() - par.min(), 1e-9)
        scale[n] = s
        parents[n], pidx[n] = (par.values * s), par.index
        ch = y[y.index >= pd.Timestamp(cf)]
        childs[n], cidx[n] = (ch.values * s), ch.index
        wf, _ = waterfalls(parents[n], minfall=WF_MIN)
        meta[n] = {"transform": how, "parent": f"{pf}..{pt}", "child_from": cf, "unit": unit, "note": note, "scale": round(s, 3),
                   "parentWaterfalls": [[str(pidx[n][s_].date()), str(pidx[n][e].date())] for s_, e in wf],
                   "nativeNow": round(float(w.iloc[-1]), 4)}
        print(f"{n}: parent {pf}..{pt} ({len(par)} w), child from {cf} ({len(ch)} w), scale {s:.3f}, waterfalls {meta[n]['parentWaterfalls']}")

    base = {"maxstep": 2, "cap": 16, "j0": 0.15, "shapew": 8, "wfweeks": 13, "res": "W", "space": "raw", "bmin": 0.1, "bmax": 5.0}
    cfgs = [dict(base, dynmap=dm, bw=bw, wshape=wsh) for (dm, bw), wsh in itertools.product([(0, 0), (2, 104)], [1.0, 3.0])]
    G = {"childs": childs, "parents": parents}
    jobs = [(n, c) for n in SERIES for c in cfgs]
    with ProcessPoolExecutor(a.workers, initializer=_init, initargs=(G,)) as ex:
        res = list(ex.map(_job, jobs))
    print(f"{len(res)} fits in {time.time() - t0:.0f}s")
    pjobs = []
    for n in SERIES:
        par = parents[n]
        for _ in range(a.placebos):
            pjobs.append((n, "iaaft", iaaft(par, rng), cfgs))
            pjobs.append((n, "block8", block_shuffle(par, rng), cfgs))
            pjobs.append((n, "walk", matched_walk(par, rng), cfgs))
    with ProcessPoolExecutor(a.workers, initializer=_init, initargs=(G,)) as ex:
        adv = list(ex.map(_placebo, pjobs))
    print(f"{len(adv)} placebos in {time.time() - t0:.0f}s")

    out = {"series": {}, "meta": meta}
    tracks = {}
    for n, (how, pf, pt, cf, unit, note) in SERIES.items():
        rs = [r for r in res if r["series"] == n]
        best = min(rs, key=lambda r: r["score"])
        bi = max(rs, key=lambda r: r["skill"].get("h26", {}).get("ic") or -9)
        px = pidx[n]
        wf, _ = waterfalls(parents[n])
        prog = lambda j: round(j / max(len(px) - 1, 1), 3)  # noqa: E731
        # walk-forward track of the best setting: parent date matched at each past child date
        tr = [(cidx[n][p["t"]], px[min(p["j"], len(px) - 1)]) for p in best["pts"]]
        tracks[n] = tr
        # stage dilation along the final warp
        path = np.array(best["path"])
        st = stages_of(parents[n])
        rows = stage_table(childs[n], parents[n], path, st)
        stages = []
        for r_ in rows:
            stages.append({"kind": r_["kind"], "parent": f"{px[r_['from']].date()}..{px[min(r_['to'], len(px) - 1)].date()}", "parentWeeks": r_["parentWeeks"],
                           "child": (f"{cidx[n][r_['i0']].date()}..{cidx[n][r_['i1']].date()}" if r_["i0"] is not None else None),
                           "childWeeks": r_["childWeeks"], "dil": None if r_["dil"] is None else round(r_["dil"], 1),
                           "ampRatio": None if r_["ampRatio"] is None else round(r_["ampRatio"], 2), "complete": r_["complete"]})
        pl = [x for x in adv if x["series"] == n]
        advs = {}
        for kind in ("iaaft", "block8", "walk"):
            v = [x for x in pl if x["kind"] == kind]
            advs[kind] = {"n": len(v), "pScore": round(float(np.mean([x["bestScore"] <= best["score"] for x in v])), 3),
                          "pIc26": round(float(np.mean([x["bestIc"] >= (bi["skill"].get("h26", {}).get("ic") or -9) for x in v])), 3),
                          "medianScore": round(float(np.median([x["bestScore"] for x in v])), 3)}
        # all settings' placement of now
        nows = sorted(str(px[min(r["jend"], len(px) - 1)].date()) for r in rs)
        # how stable has the placement been over the last 3 years of the track
        last3 = [d for t, d in tr if t >= cidx[n][-1] - pd.Timedelta(weeks=156)]
        out["series"][n] = {
            "best": {"cfg": f"dyn{best['cfg']['dynmap']} wsh{best['cfg']['wshape']}", "now": str(px[min(best["jend"], len(px) - 1)].date()),
                     "progress": prog(best["jend"]), "score": round(best["score"], 3), "r": round(best["fit"]["r"], 3),
                     "dilOverall": round(best["fit"]["dil"], 2), "dilRecent": round(best["fit"]["rdil"], 2),
                     "skill": {k: {kk: (round(vv, 3) if isinstance(vv, float) else vv) for kk, vv in v.items()} for k, v in best["skill"].items()}},
            "bestIc26": {"cfg": f"dyn{bi['cfg']['dynmap']} wsh{bi['cfg']['wshape']}", "ic26": round(bi["skill"].get("h26", {}).get("ic") or -9, 3),
                         "hit26": bi["skill"].get("h26", {}).get("hit")},
            "nowAcrossSettings": nows,
            "trackLast3y": {"first": str(min(last3).date()) if last3 else None, "last": str(max(last3).date()) if last3 else None,
                            "distinctParentWeeks": len(set(last3))},
            "adversary": advs, "stages": stages, "laws": {k: (round(v, 3) if isinstance(v, float) else v) for k, v in laws(rows).items() if not isinstance(v, dict)},
            "projection26w": {"points": round(float(best["proj"][25] - childs[n][-1]), 2) if best.get("proj") else None,
                              "native": round(float(native_move(best["proj"][25] - childs[n][-1], how, scale[n], raw[n].iloc[-1])), 2) if best.get("proj") else None},
        }
        print(f"{n}: now {out['series'][n]['best']['now']} (settings {nows}), score {best['score']:.2f}, ic26 {out['series'][n]['bestIc26']['ic26']}, "
              f"adversary {json.dumps(advs)}, dil {best['fit']['dil']:.1f}/{best['fit']['rdil']:.1f}, last 3y track {out['series'][n]['trackLast3y']}")
        for s_ in stages:
            print("   ", s_)

    # ---- the four together
    F, b, _ = study4.features(a.data)
    b16 = b[b.index >= pd.Timestamp("2016-01-01")]
    big = study4.events(b16, 10.0)
    med = study4.events(b16, 5.0)
    L = {n: np.log(raw[n]) * 100 for n in SERIES if n != "BTC.D"}
    L["BTC.D"] = raw["BTC.D"]  # points
    idx = raw["BTC.D"].index
    L = {n: s.reindex(idx).ffill() for n, s in L.items()}
    offs = [-26, -13, -8, -4, 0, 4, 8, 13, 26]

    def paths(evs):
        o = {}
        for n, s in L.items():
            rows = []
            for e in evs:
                t = pd.Timestamp(e["peak"])
                i = idx.get_indexer([t])[0]
                if i < 26 or i + 26 >= len(idx):
                    continue
                if not np.isfinite(s.iloc[i]):
                    continue
                rows.append([float(s.iloc[i + k] - s.iloc[i]) for k in offs])
            o[n] = {"n": len(rows), "median": [round(float(np.nanmedian(c)), 1) if np.isfinite(c).any() else None for c in zip(*rows)] if rows else None,
                    "perEvent": [[(round(v, 1) if np.isfinite(v) else None) for v in r] for r in rows]}
        return o
    out["prePost"] = {"offsetsWeeks": offs, "unit": "BTC.D pct points; others % of themselves (100 x log change)", "big": paths(big), "medium": paths(med),
                      "bigEvents": [str(pd.Timestamp(e["peak"]).date()) for e in big], "mediumEvents": [str(pd.Timestamp(e["peak"]).date()) for e in med]}
    print("paths around the big BTC.D waterfall starts (median change from the start week):")
    for n, v in out["prePost"]["big"].items():
        print(f"   {n:7s} {v['median']}")

    # lead/lag: 4-week change of series X at t against BTC.D's 4-week change at t+lag
    db = L["BTC.D"].diff(4)
    ll = {}
    for n in ("USDT.D", "TOTAL3", "ETHBTC"):
        dx = L[n].diff(4)
        cors = [spearman(dx.values[: len(dx) - lag] if lag else dx.values, db.values[lag:] if lag else db.values) or 0 for lag in range(0, 27)]
        best_lag = int(np.argmax(np.abs(cors)))
        nul = []
        for _ in range(a.nulls):
            k = int(rng.integers(52, len(dx) - 52))
            dxs = np.roll(dx.values, k)
            nul.append(max(abs(spearman(dxs[: len(dxs) - lag] if lag else dxs, db.values[lag:] if lag else db.values) or 0) for lag in range(0, 27, 2)))
        ll[n] = {"corrByLag": [round(c, 3) for c in cors], "bestLag": best_lag, "bestCorr": round(cors[best_lag], 3),
                 "lag0": round(cors[0], 3), "pShift": round(float((np.array(nul) >= abs(cors[best_lag])).mean()), 3)}
        print(f"lead/lag {n}: lag0 {ll[n]['lag0']}, best lag {best_lag} w corr {ll[n]['bestCorr']}, p {ll[n]['pShift']}")
    out["leadLag"] = ll

    # fractal confluence: count of warps within 8 parent weeks before (or inside) a parent waterfall, by date
    door = {}
    for n in SERIES:
        px = pidx[n]
        wf, _ = waterfalls(parents[n], minfall=WF_MIN)
        flags = {}
        for t, d in tracks[n]:
            j = px.get_indexer([d])[0]
            near = any(s_ - 8 <= j <= e for s_, e in wf)
            flags[t] = near
        door[n] = pd.Series(flags)
    C = pd.DataFrame(door).reindex(idx).ffill().fillna(False)
    cnt = C.sum(axis=1)
    fut = pd.concat([b.reindex(idx).shift(-k) for k in range(1, 27)], axis=1).min(axis=1) - b.reindex(idx)
    away = pd.Series(True, index=idx)
    for e in big:
        t = pd.Timestamp(e["peak"])
        away &= ~((idx > t - pd.Timedelta(weeks=12)) & (idx <= t + pd.Timedelta(weeks=26)))
    conf = {"countNow": int(cnt.iloc[-1]), "byEvent": {}, "precision": {}}
    for e in big + [m for m in med if m not in big]:
        t = pd.Timestamp(e["peak"])
        if t in cnt.index:
            conf["byEvent"][str(t.date())] = {"count": int(cnt.loc[t]), "which": [n for n in SERIES if C.loc[t, n]]}
    valid = cnt.index >= pd.Timestamp("2019-01-01")
    for k in range(0, 5):
        m = (cnt >= k) & fut.notna() & valid
        ma = m & away
        conf["precision"][f">={k}"] = {"weeks": int(m.sum()), "fall5in26w": round(float((fut[m] <= -5).mean()), 2) if m.sum() else None,
                                       "weeksAwayFromEvents": int(ma.sum()), "fall5in26wAway": round(float((fut[ma] <= -5).mean()), 2) if ma.sum() else None}
    conf["seriesNow"] = {n: bool(C.iloc[-1][n]) for n in SERIES}
    out["confluence"] = conf
    print("confluence:", json.dumps(conf))
    # series for the doc chart
    out["confluenceSeries"] = [{"t": str(t.date()), "count": int(v)} for t, v in cnt[valid].items()][::2]
    out["doorstep"] = {str(t.date()): {n: bool(C.loc[t, n]) for n in SERIES} for t in C.index}  # point-in-time flags for round 7
    with open(os.path.join(a.out, "results6.json"), "w") as fh:
        json.dump(out, fh, indent=1, default=str)
    charts(a.out, raw, tracks, pidx, cnt[valid], big)
    print(f"done in {time.time() - t0:.0f}s")


def charts(out, raw, tracks, pidx, cnt, big):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return
    fig, ax = plt.subplots(len(tracks) + 1, 1, figsize=(11, 11), sharex=True)
    for k, (n, tr) in enumerate(tracks.items()):
        t = [x for x, _ in tr]
        d = [y for _, y in tr]
        ax[k].plot(t, d, color="#3b6fb6", lw=1)
        ax[k].set_ylabel(f"{n}\nparent week matched")
        for e in big:
            ax[k].axvline(pd.Timestamp(e["peak"]), color="#c0504d", lw=0.8, ls="--")
    ax[-1].step(cnt.index, cnt.values, color="#4f8a3c", lw=1.2, where="post")
    ax[-1].set_ylabel("warps at a\nwaterfall doorstep")
    for e in big:
        ax[-1].axvline(pd.Timestamp(e["peak"]), color="#c0504d", lw=0.8, ls="--")
    ax[0].set_title("Where each fractal walk placed 'now' at every past date (dashed: BTC.D waterfall starts)")
    fig.tight_layout()
    fig.savefig(os.path.join(out, "8_four_walks.png"), dpi=110)


if __name__ == "__main__":
    main()
