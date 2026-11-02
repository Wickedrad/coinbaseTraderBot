#!/usr/bin/env python3
"""Append one line per run to forecast_log.csv from the committed results (round-10 refresh; no fitting, no network).

  python3 research/btcd_fractal/log_reading.py --root research/btcd_fractal --log research/btcd_fractal/forecast_log.csv
"""
import argparse
import csv
import datetime as dt
import json
import os
import zoneinfo

COLS = ["asOf", "runUTC", "runEST", "btcd", "btcd_exstable", "m2_yoy", "btc_dd_ath", "ethbtc_fromhi52w", "usdtd_vsma30w", "btcusd_ret13w",
        "p_fixed5", "p_m2only", "p_m2eth", "p_strat", "p_stack", "spread_inSupport_lo", "spread_inSupport_hi", "readinessOn",
        "btcRallyNeededToReadiness", "fresh", "falsifier_i", "falsifier_ii", "falsifier_iii"]


def load(path):
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def g(d, *keys, default=None):
    for k in keys:
        if not isinstance(d, dict) or k not in d:
            return default
        d = d[k]
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--log", required=True)
    a = ap.parse_args()
    h = load(os.path.join(a.root, "out8", "honest", "results.json"))
    f = load(os.path.join(a.root, "out8", "forecast", "results.json"))
    c = load(os.path.join(a.root, "out9", "checks", "results.json"))
    now = dt.datetime.now(dt.timezone.utc)
    est = now.astimezone(zoneinfo.ZoneInfo("America/New_York"))
    inp = g(h, "today", "inputs", default={}) or {}
    comp = g(h, "today", "comparators", default={}) or {}
    spread = g(h, "today", "headline", "spread", default=[None, None]) or [None, None]
    fz = g(c, "questionB", "falsifiers", default={}) or {}

    def status(key):
        v = fz.get(key)
        return v.get("status") if isinstance(v, dict) else v

    row = {"asOf": g(h, "today", "asOf"), "runUTC": now.strftime("%Y-%m-%d %H:%M"), "runEST": est.strftime("%Y-%m-%d %H:%M %Z"),
           "btcd": g(h, "today", "btcd"), "btcd_exstable": g(h, "today", "btcd_exstable"),
           "m2_yoy": inp.get("m2_yoy"), "btc_dd_ath": inp.get("btc_dd_ath"), "ethbtc_fromhi52w": inp.get("ethbtc_fromhi52w"),
           "usdtd_vsma30w": inp.get("usdtd_vsma30w"), "btcusd_ret13w": inp.get("btcusd_ret13w"),
           "p_fixed5": comp.get("fixed5:fall5_26w"), "p_m2only": comp.get("m2only:fall5_26w"), "p_m2eth": comp.get("m2eth:fall5_26w"),
           "p_strat": comp.get("strat:fall5_26w"), "p_stack": g(f, "today", "onset", "stack_fall5_26w"),
           "spread_inSupport_lo": spread[0], "spread_inSupport_hi": spread[1], "readinessOn": g(h, "today", "readinessOn"),
           "btcRallyNeededToReadiness": g(c, "today", "readinessGate", "btcRallyNeededToWithin5pctOfATH"), "fresh": g(h, "today", "fresh"),
           "falsifier_i": status("i_higherHighAbove65.7"), "falsifier_ii": status("ii_engineImminentSinceFeb2023"),
           "falsifier_iii": status("iii_nextFallWhileEngineFit<0.8")}
    new = not os.path.exists(a.log)
    with open(a.log, "a", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        if new:
            w.writeheader()
        w.writerow(row)
    print(f"logged {row['asOf']}: BTC.D {row['btcd']} fixed5 {row['p_fixed5']} m2only {row['p_m2only']} m2eth {row['p_m2eth']} spread {spread} readiness {row['readinessOn']} ({row['runEST']} / {row['runUTC']} UTC)")


if __name__ == "__main__":
    main()
