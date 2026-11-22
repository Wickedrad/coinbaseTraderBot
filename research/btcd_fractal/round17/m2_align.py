#!/usr/bin/env python3
"""Round 17 M2: the anchor-free time map on BTC.D against the settled anchors. Run: python3 m2_align.py"""
import json, sys, time
import numpy as np, pandas as pd
import common as c, hmm

P_END = pd.Timestamp("2017-04-09")          # six weeks past the parent's top, so the map may run past it
TOL = 14                                     # "full traverse": the last child week sits within 14 days of the parent's top, or past it


def series(scale="logit", steps_out=False, p_end=P_END):
    d = c.lbtcd(steps_out) if scale == "logit" else np.log(c.btcd())
    par = d[c.P[0]:p_end]
    ch = c.weekly(d)[pd.Timestamp("2017-12-10"):]
    return par, ch


def describe(par, ch, r):
    wk = ch.index
    f = lambda j: str(wk[j].date()) if j is not None and j < len(wk) else None
    out = {"b": r["b"], "a": round(r["a"], 3), "sd": round(r["sd"], 4), "loglik": round(r["loglik"], 1), "gainPerWeek": round(r["gainPerWeek"], 3), "inlierShare": round(r["inlier"], 3), "anchors": []}
    med = []
    for t in c.P:
        lo, m_, hi = hmm.passage_weeks(r["W"], par.index.get_loc(t))
        out["anchors"].append({"parent": str(t.date()), "child10": f(lo), "child50": f(m_), "child90": f(hi)}); med.append(m_)
    out["paceByStretch"] = [round((med[i + 1] - med[i]) / ((c.P[i + 1] - c.P[i]).days / 7), 1) if med[i + 1] is not None and med[i] is not None else None for i in range(5)]
    F = hmm.first_passage(r["W"]); s_top = par.index.get_loc(c.P[-1])
    out["pastTopToday"] = round(float(F[-1, min(s_top + 1, len(par) - 1)]), 3)
    q = np.cumsum(r["W"][-1]); pick = lambda p: str(par.index[min(int(np.searchsorted(q, p)), len(par) - 1)].date())
    out["todayOnParent"] = [pick(0.1), pick(0.5), pick(0.9)]
    return out


if __name__ == "__main__":
    res = {"grid": list(hmm.B_GRID), "runs": {}}
    runs = (("primary: logit, steps in, 6 weeks past the top", {}, 0.05), ("q 0.02", {}, 0.02), ("q 0.10", {}, 0.10), ("log scale", {"scale": "log"}, 0.05), ("index steps out", {"steps_out": True}, 0.05),
            ("3 weeks past the top", {"p_end": pd.Timestamp("2017-03-19")}, 0.05), ("12 weeks past the top", {"p_end": pd.Timestamp("2017-05-21")}, 0.05))
    for name, kw, q in runs:
        par, ch = series(**kw)
        m = hmm.Model(len(par), q); end_min = par.index.get_loc(c.P[-1]) - TOL
        grid = hmm.B_GRID if kw.get("scale") != "log" else tuple(10 * b for b in hmm.B_GRID)
        t0 = time.time(); out = {}
        for tag, em in (("endFree", None), ("fullTraverse", end_min)):
            best, fits = hmm.profile(ch.values, par.values, m, end_min=em, grid=grid, keep=name.startswith("primary"))
            out[tag] = {"best": describe(par, ch, best), "byB": [describe(par, ch, r) for r in fits]}
            if name.startswith("primary"):
                np.savez_compressed(c.HERE / f"m2_primary_{tag}.npz", W=best["W"], filtered=best["filtered"], logSpeed=best["logSpeed"], weeks=ch.index.values.astype("datetime64[D]").astype(str), days=par.index.values.astype("datetime64[D]").astype(str))
        out["seconds"] = round(time.time() - t0, 1); res["runs"][name] = out
        for tag in ("endFree", "fullTraverse"):
            print(f"== {name} | {tag}")
            for d in out[tag]["byB"]:
                print("  b", d["b"], "ll", d["loglik"], "inl", d["inlierShare"], "sd", d["sd"], "anchors", [x["child50"] for x in d["anchors"][1:]], "pace", d["paceByStretch"], "today", d["todayOnParent"], "pastTop", d["pastTopToday"])
    (c.HERE / "m2_align.json").write_text(json.dumps(res, indent=1))
