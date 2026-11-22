#!/usr/bin/env python3
"""Round 17 M3: run the fractal forward in real time, weekly.

Every 13 weeks from January 2019 the alignment is refitted on the child's weekly closes up to that week only
(offset, spread and amplitude all from data to that week; end free, because "we are at the top" is hindsight) and
the position on the parent at that week is read from the forward filter. A second pass holds the amplitude at 2.3
(a value only hindsight supplies) to show what the map would have said with the scale known.
No forecast is scored here: earlier rounds found no forecast skill and the plan labels this run in-sample as far
as the choice of parent goes. Run: python3 m3_forward.py
"""
import json
from multiprocessing import Pool
import numpy as np, pandas as pd
import common as c, hmm, m2_align as ma

par, ch = ma.series()
M = hmm.Model(len(par), 0.05)
MARKS = {"end of the July 2016 waterfall": c.P[1], "the high before the mid-structure fall": c.P[2], "start of the grey box": c.P[3],
         "end of the grey box": c.P[4], "the parent's top (weekly close)": c.P[5]}


def read(r):
    q = np.cumsum(r["filtered"][-1]); q /= q[-1]
    pick = lambda p: str(par.index[min(int(np.searchsorted(q, p)), len(par) - 1)].date())
    return {"b": r["b"], "gainPerWeek": round(r["gainPerWeek"], 3), "parentDay": [pick(0.1), pick(0.5), pick(0.9)]}


def one(j):
    y = ch.values[:j + 1]
    best, _ = hmm.profile(y, par.values, M, keep=True)
    fixed = hmm.fit_b(y, par.values, 2.3, M, keep=True)
    return {"week": str(ch.index[j].date()), "amplitudeFree": read(best), "amplitude2.3": read(fixed)}


if __name__ == "__main__":
    j0 = ch.index.get_loc(pd.Timestamp("2019-01-06"))
    js = sorted(set(list(range(j0, len(ch), 13)) + [len(ch) - 1]))
    with Pool(4) as p:
        rows = p.map(one, js)
    first = {}
    for tag in ("amplitudeFree", "amplitude2.3"):
        first[tag] = {}
        for name, t in MARKS.items():
            hit = [r["week"] for r in rows if pd.Timestamp(r[tag]["parentDay"][1]) >= t - pd.Timedelta(days=3)]
            stay = None
            for i, r in enumerate(rows):   # first quarter after which the reading never drops back before the mark
                if all(pd.Timestamp(x[tag]["parentDay"][1]) >= t - pd.Timedelta(days=3) for x in rows[i:]):
                    stay = r["week"]; break
            first[tag][name] = {"firstReached": hit[0] if hit else None, "reachedForGood": stay}
    for r in rows:
        print(r["week"], "| free b", r["amplitudeFree"]["b"], r["amplitudeFree"]["parentDay"], "| b 2.3", r["amplitude2.3"]["parentDay"])
    print(json.dumps(first, indent=1))
    (c.HERE / "m3_forward.json").write_text(json.dumps({"through": str(c.THROUGH.date()), "everyWeeks": 13, "rows": rows, "firstReached": first}, indent=1))
