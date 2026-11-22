#!/usr/bin/env python3
"""Round 16: what was in place when each alt-led BTC.D fall began, and the same readings today.

Asked Nov 21, 2026, 11:11 PM EST / Nov 22, 04:11 UTC: timing of the waterfall. No clock is used here;
the script only lists BTC, USDT.D and ETH/BTC around the four alt-led falls on record (weekly closes).
Run: python3 waterfall_starts.py [data_dir]
"""
import json, sys
from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent / "data"
def load(n):
    d = pd.read_csv(DATA / f"{n}_1d.csv"); d.index = pd.to_datetime(d.ts, unit="ms"); return d.c
bd, eb, ut, uc, btc = (load(n) for n in ("BTC.D", "ETHBTC", "USDT.D", "USDC.D", "BTCUSD"))
W = lambda s: s.resample("W-SUN").last()
wbd, web, wut, wbtc = W(bd), W(eb), W(ut), W(btc)
FALLS = {"parent 2017": ("2017-02-26", "2017-05-21"), "child 2017-18": ("2017-12-10", "2018-01-14"),
         "child 2021": ("2021-01-03", "2021-05-16"), "child 2025": ("2025-06-22", "2025-09-14")}
out = {"dataThrough": str(bd.index[-1].date()), "falls": [], "now": {}}
for name, (t, e) in FALLS.items():
    t, e = pd.Timestamp(t), pd.Timestamp(e)
    pre = web[t - pd.Timedelta(weeks=52):t].dropna(); lo = pre.idxmin()
    seg = wbd[t:e]; r4 = (seg / seg.shift(4) - 1).dropna()
    pu = wut[t - pd.Timedelta(weeks=78):t]; hi = pu.idxmax()
    row = {"fall": name, "btcdHigh": [str(t.date()), round(float(wbd[t]), 2)], "btcdLow": [str(e.date()), round(float(wbd[e]), 2)], "weeks": (e - t).days // 7,
           "btc13wBeforePct": round(float(wbtc[t] / wbtc[t - pd.Timedelta(weeks=13)] - 1) * 100), "btcThroughFall": round(float(wbtc[e] / wbtc[t]), 2),
           "ethbtc52wLow": str(lo.date()), "ethbtcLowWeeksBefore": (t - lo).days // 7, "ethbtcAboveLowAtHigh": round(float(web[t] / pre.min()), 2),
           "ethbtcThroughFall": round(float(web[e] / web[t]), 2),
           "usdtd78wHigh": [str(hi.date()), round(float(pu.max()), 2)], "usdtdAtBtcdHigh": round(float(wut[t]), 2), "usdtdAtBtcdLow": round(float(wut[e]), 2),
           "sharpest4wDropEndsWeeksAfterHigh": (r4.idxmin() - t).days // 7, "sharpest4wDropPct": round(float(r4.min()) * 100)}
    out["falls"].append(row); print(row)
ex = bd / (1 - (ut + uc) / 100)
out["now"] = {"btc": round(float(btc.iloc[-1])), "btc4wPct": round(float(btc.iloc[-1] / btc.iloc[-29] - 1) * 100, 1), "btc13wPct": round(float(btc.iloc[-1] / btc.iloc[-92] - 1) * 100, 1),
              "btc52wLow": [str(btc[-365:].idxmin().date()), round(float(btc[-365:].min()))],
              "usdtd": round(float(ut.iloc[-1]), 2), "usdtd4wAgo": round(float(ut.iloc[-29]), 2), "usdtd13wAgo": round(float(ut.iloc[-92]), 2),
              "ethbtc": round(float(eb.iloc[-1]), 4), "ethbtc52wLow": [str(eb[-365:].idxmin().date()), round(float(eb[-365:].min()), 4)],
              "ethbtcAboveLow": round(float(eb.iloc[-1] / eb[-365:].min()), 2), "ethbtc13wPct": round(float(eb.iloc[-1] / eb.iloc[-92] - 1) * 100, 1),
              "btcd": round(float(bd.iloc[-1]), 2), "btcdExStables": round(float(ex.iloc[-1]), 2), "btcdExStables13wAgo": round(float(ex.iloc[-92]), 2)}
print("now", out["now"])
print("parent after its top, weekly BTC.D / ETH/BTC:", [(str(i.date()), round(float(wbd[i]), 1), round(float(web[i]), 4)) for i in wbd["2017-02-26":"2017-03-26"].index])
(HERE / "waterfall_starts.json").write_text(json.dumps(out, indent=1))
