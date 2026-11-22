#!/usr/bin/env python3
"""Round 17 M1: the stretch table on the settled anchors. Run: python3 m1_landmarks.py"""
import json
import numpy as np, pandas as pd
import common as c

d, dl, dls = c.btcd(), c.lbtcd(), c.lbtcd(True)
w = c.weekly(dl)
out = {"through": str(c.THROUGH.date()), "parentWeekly": {str(k.date()): round(float(c.inv_logit(v)), 2) for k, v in w["2016-06-12":"2017-03-26"].items()}, "readings": {}}
at = lambda s, t: float(s.asof(pd.Timestamp(t)))
for top in c.C_TOPS:
    rows = []
    for cons in (0, 1, 2):
        C = c.child_anchors(top, cons)
        for i in range(5):
            if cons != 1 and i < 3:
                continue
            pw, cw = (c.P[i + 1] - c.P[i]).days / 7, (C[i + 1] - C[i]).days / 7
            mp, mc = at(dl, c.P[i + 1]) - at(dl, c.P[i]), at(dl, C[i + 1]) - at(dl, C[i])
            rv = lambda s, a, b: float((s[a:b].diff().dropna().iloc[1:] ** 2).sum())
            rvw = lambda a, b: float((w[a:b].diff().dropna() ** 2).sum())
            r = {"stretch": c.SEG[i], "consEnd": str(c.C_CONS_END[cons].date()), "parent": [str(c.P[i].date()), str(c.P[i + 1].date())], "child": [str(C[i].date()), str(C[i + 1].date())],
                 "parentWeeks": round(pw, 1), "childWeeks": round(cw, 1), "pace": round(cw / pw, 1),
                 "parentBTCD": [round(at(d, c.P[i]), 2), round(at(d, c.P[i + 1]), 2)], "childBTCD": [round(at(d, C[i]), 2), round(at(d, C[i + 1]), 2)],
                 "moveLogitParent": round(mp, 3), "moveLogitChild": round(mc, 3), "magnification": round(mc / mp, 2),
                 "rvDailyParent": round(rv(dl, c.P[i], c.P[i + 1]), 4), "rvDailyParentStepsOut": round(rv(dls, c.P[i], c.P[i + 1]), 4), "rvDailyChild": round(rv(dl, C[i], C[i + 1]), 4),
                 "rvWeeklyParent": round(rvw(c.P[i], c.P[i + 1]), 4), "rvWeeklyChild": round(rvw(C[i], C[i + 1]), 4)}
            r["rvRatioDaily"] = round(r["rvDailyChild"] / r["rvDailyParent"], 1)
            r["rvRatioDailyStepsOut"] = round(r["rvDailyChild"] / r["rvDailyParentStepsOut"], 1)
            r["volPerDayParentStepsOut"] = round(float(np.sqrt(r["rvDailyParentStepsOut"] / (pw * 7))), 4)
            r["volPerDayChild"] = round(float(np.sqrt(r["rvDailyChild"] / (cw * 7))), 4)
            rows.append(r)
    out["readings"][top] = rows
    print("== top =", top)
    for r in rows:
        print({k: r[k] for k in ("stretch", "consEnd", "parentWeeks", "childWeeks", "pace", "parentBTCD", "childBTCD", "magnification", "rvRatioDaily", "rvRatioDailyStepsOut", "volPerDayParentStepsOut", "volPerDayChild")})
print("parent weekly closes:", out["parentWeekly"])
(c.HERE / "m1_landmarks.json").write_text(json.dumps(out, indent=1))
