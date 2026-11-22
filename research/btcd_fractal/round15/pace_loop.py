"""Round 15 loop 2: the 8.3:1 pace read off the re-run round 14 study.
Usage: python3 -I pace_loop.py <study14 results.json> <old round14 results.json> <out_json>"""
import json
import sys
from datetime import date, timedelta

new = json.load(open(sys.argv[1]))
old = json.load(open(sys.argv[2]))
OUT = sys.argv[3]

D = lambda s: date.fromisoformat(s)
START = D("2017-03-12")  # the parent's next waterfall start after the Mar 5 placement (round 14 rule)
STEADY = 174 / 21        # C1 2018-01-14 -> C3 2021-05-16 over P1 2016-07-24 -> P3 2016-12-18

res = {"dataLastDailyBar": new.get("dataLastDailyBar"), "todayWeek": new.get("todayWeek")}
ro = new["readout"]["TV"]
res["readoutTV"] = {"placedWeek": ro["placedWeek"], "today": ro["today"], "todayLevel": ro["todayLevel"],
                    "nextWaterfall": {k: ro["nextWaterfall"][k] for k in ("start", "low", "parentWeeksToStart", "parentWeeksToLow")},
                    "clocks": {k: {kk: v.get(kk) for kk in ("childWeeksPerParentWeek", "startDate", "lowDate")} for k, v in ro["clocks"].items()}}
ro_old = old["readout"]["TV"]
res["readoutTV_round14"] = {"placedWeek": ro_old["placedWeek"], "today": ro_old["today"],
                            "steadyStart": ro_old["clocks"]["steady2018to2021"]["startDate"]}

# segment clocks from the TV anchors
A = {"P0": "2016-06-19", "P1": "2016-07-24", "P2": "2016-11-20", "P3": "2016-12-18",
     "C0": "2017-12-10", "C1": "2018-01-14", "C2": "2019-09-08", "C2b": "2021-01-03", "C3": "2021-05-16"}
wk = lambda a, b: (D(A[b]) - D(A[a])).days / 7
seg = []
for (pa, pb), (ca, cb), name in [(("P0", "P1"), ("C0", "C1"), "waterfall: top to bottom"),
                                 (("P1", "P2"), ("C1", "C2"), "rise from the bottom to the hump"),
                                 (("P2", "P3"), ("C2", "C3"), "hump to the fall's end (C2 = Sep 2019)"),
                                 (("P2", "P3"), ("C2b", "C3"), "the fall itself (C2' = Jan 3 2021 top)"),
                                 (("P1", "P3"), ("C1", "C3"), "steady 2018-21 (the 8.3:1 clock)")]:
    p, c = wk(pa, pb), wk(ca, cb)
    seg.append({"segment": name, "parent": f"{A[pa]} -> {A[pb]}", "parentWeeks": round(p, 1), "child": f"{A[ca]} -> {A[cb]}",
                "childWeeks": round(c, 1), "childWeeksPerParentWeek": round(c / p, 2)})
tw = D(ro["today"])
pw = D(ro["placedWeek"])
p_open, c_open = (pw - D(A["P3"])).days / 7, (tw - D(A["C3"])).days / 7
seg.append({"segment": "since 2021 (open part)", "parent": f"{A['P3']} -> {ro['placedWeek']}", "parentWeeks": round(p_open, 1),
            "child": f"{A['C3']} -> {ro['today']}", "childWeeks": round(c_open, 1), "childWeeksPerParentWeek": round(c_open / p_open, 2)})
res["segmentClocks"] = seg

# the parent's 2017 path laid out on the child calendar at 8.3:1, starting from today <-> placed week
events = [("2017-03-12", "the parent's drop starts"), ("2017-03-26", "TV 90.3 / CMC 67.4, ETH/BTC 0.052 (x3.4 from Mar 5)"),
          ("2017-05-21", "the rule's low (TV 65.5)"), ("2017-06-18", "TV 2017 trough area"), ("2017-08-27", "the low before the parent's end")]
lay = []
for d_, what in events:
    pwks = (D(d_) - pw).days / 7
    for name, ratio in (("1:1 (the 2016/2018 waterfall's own clock)", 1.0), ("4.75:1 (the 2021 fall's clock)", 4.75), ("8.3:1 (steady 2018-21)", STEADY)):
        lay.append({"parentDate": d_, "event": what, "clock": name, "childDate": str(tw + timedelta(days=round(7 * pwks * ratio)))})
res["parentPathOnChildCalendar"] = {"anchor": f"today {ro['today']} <-> parent {ro['placedWeek']}", "rows": lay}

# the 8.3:1 start date implied each week by the walk-forward placement: does it roll forward?
roll = []
for w in new["walkForwardPath"]:
    if not w.get("primary"):
        continue
    pp = D(w["primary"])
    if pp > D("2017-03-05"):
        continue
    gap = (START - pp).days / 7
    roll.append({"week": w["date"], "placed": w["primary"], "parentWeeksToStart": round(gap, 1),
                 "impliedStart83": str(D(w["date"]) + timedelta(days=round(7 * gap * STEADY)))})
res["rollingImpliedStart"] = {"rule": "each week's primary placement, start = week + 8.3 x parent weeks to 2017-03-12",
                              "weeks": len(roll),
                              "alreadyPassed": sum(1 for x in roll if D(x["impliedStart83"]) < tw),
                              "sample": roll[::13] + roll[-6:]}
ALT = [D(x) for x in ("2017-12-10", "2018-04-01", "2019-09-08", "2021-01-03", "2021-06-27", "2025-06-22")]  # alt-led legs, usdt_loops.py
done = [x for x in roll if D(x["impliedStart83"]) < tw]
hit = [x for x in done if any(abs((D(x["impliedStart83"]) - a).days) <= 28 for a in ALT)]
lo, hi = D(roll[0]["week"]) if roll else tw, tw
days = [lo + timedelta(days=k) for k in range((hi - lo).days)]
base = sum(1 for d_ in days if any(abs((d_ - a).days) <= 28 for a in ALT)) / max(1, len(days))
res["rollingImpliedStart"]["hitTest"] = {"rule": "a passed implied date is a hit when an alt-led BTC.D leg (7+ pts) started within 4 weeks of it",
                                         "passed": len(done), "hits": len(hit), "hitShare": round(len(hit) / max(1, len(done)), 3),
                                         "randomDateShare": round(base, 3), "hitWeeks": [x["week"] for x in hit]}
json.dump(res, open(OUT, "w"), indent=1)
print(res["rollingImpliedStart"]["hitTest"])
print(json.dumps({k: res[k] for k in ("dataLastDailyBar", "todayWeek", "readoutTV", "readoutTV_round14")}, indent=1))
for s in seg:
    print(s)
print(res["rollingImpliedStart"]["weeks"], "weeks,", res["rollingImpliedStart"]["alreadyPassed"], "implied dates already passed")
for x in res["rollingImpliedStart"]["sample"]:
    print(x)
for x in lay:
    print(x)
