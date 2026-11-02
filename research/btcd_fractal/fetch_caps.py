#!/usr/bin/env python3
"""Rebuild BTC dominance for 2013-2018 from per-coin market caps (Steven, 2026-11-02 17:09 UTC, doc comment: "the parent
fractal of 2016-2017 is a bit wrong, it should be measured from the bottom of the 'waterfall' event in 2016").

TradingView's CRYPTOCAP:BTC.D (the study's series) runs 95-99% through 2016: its early coin coverage is thin, so the
ETH-driven 2016 fall never shows there. Two independent rebuilds, both fetched here (the cloud container cannot reach
either host; this runs on the GitHub runner):
  A. per-coin: Coin Metrics community API (free, no key), CapMrktCurUSD daily for every asset the catalog had before
     mid-2018; dominance = BTC cap / sum of the caps with data that day. The coverage report sits beside it.
  B. canonical: CoinMarketCap's global-metrics history (the dominance chart people look at), btcDominance daily, via
     the website's own data API (unofficial; may refuse non-browser clients, in which case only A is written).
Outputs in --out (same csv shape as fetch.py, so study.py's load() reads them):
  BTCD_CAP_1d.csv      rebuild A         BTCD_CMC_1d.csv  rebuild B (when it answered)
  BTCD_SPLICED_1d.csv  the study series: rebuild (B when present, else A) before the splice week, TradingView BTC.D after
  caps_report.json     coverage, the 2016 waterfall (peak, trough, dates) in each rebuild, the gap against TradingView
                       by year, the splice week chosen, the suggested parent start (the 2016 trough week)
"""
import argparse
import calendar
import json
import os
import sys
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests

CM = "https://community-api.coinmetrics.io/v4"
CMC = "https://api.coinmarketcap.com/data-api/v3/global-metrics/quotes/historical"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
      "Accept": "application/json, text/plain, */*", "Origin": "https://coinmarketcap.com", "Referer": "https://coinmarketcap.com/charts/"}
# the 2015-2018 large caps, used when the catalog call fails
FALLBACK_ASSETS = ["btc", "eth", "xrp", "ltc", "dash", "xmr", "etc", "doge", "xem", "maid", "steem", "lsk", "rep", "waves", "fct", "nxt",
                   "xlm", "bts", "zec", "bch", "ada", "miota", "iota", "neo", "eos", "usdt", "trx", "xvg", "qtum", "omg", "bnb", "btg", "icx",
                   "ppt", "strat", "ardr", "sc", "dcr", "pivx", "gnt", "ven", "vet", "xlm", "bcn", "dgb", "sys", "gno", "bat", "zrx", "snt",
                   "salt", "kmd", "ark", "mona", "ltc", "nano", "xrb", "lrc", "knc", "mco", "pay", "wtc", "hsr", "bnt", "cvc", "powr", "zen",
                   "rdd", "doge", "game", "emc2", "vtc", "nav", "ubq", "part", "xzc", "firo", "grs", "via", "blk", "ppc", "nmc", "ftc", "nvc"]


def ms(d):
    return calendar.timegm(pd.Timestamp(d).to_pydatetime().timetuple()) * 1000


def write_csv(path, s):
    rows = [f"{ms(t)},{v},{v},{v},{v},0" for t, v in s.items()]
    with open(path, "w") as f:
        f.write("ts,o,h,l,c,v\n" + "\n".join(rows) + "\n")


def get(url, params=None, headers=None, tries=4, timeout=60):
    last = None
    for i in range(tries):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=timeout)
            if r.status_code == 429:
                time.sleep(6 + 4 * i)
                continue
            return r
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 + 3 * i)
    print(f"  {url}: {type(last).__name__ if last else 'no answer'}")
    return None


# ------------------------------------------------------------------------------------------------ A. Coin Metrics
def cm_catalog(before="2018-07-01"):
    """Assets whose CapMrktCurUSD history starts before `before` (community catalog); None when the call fails."""
    r = get(f"{CM}/catalog-v2/asset-metrics", {"metrics": "CapMrktCurUSD", "page_size": 10000})
    if r is None or r.status_code != 200:
        print(f"  catalog: {r.status_code if r is not None else 'n/a'}")
        return None
    out = []
    for row in r.json().get("data", []):
        for m in row.get("metrics", []):
            if m.get("metric") != "CapMrktCurUSD":
                continue
            for fq in m.get("frequencies", []):
                if fq.get("frequency") == "1d" and fq.get("min_time", "9999") < before:
                    out.append((row["asset"], fq["min_time"][:10]))
    return out


def cm_series(asset, start="2013-01-01"):
    url = f"{CM}/timeseries/asset-metrics"
    params = {"assets": asset, "metrics": "CapMrktCurUSD", "frequency": "1d", "start_time": start, "page_size": 10000}
    vals = {}
    while url:
        r = get(url, params)
        params = None
        if r is None:
            return None
        if r.status_code != 200:
            return None
        j = r.json()
        for row in j.get("data", []):
            v = row.get("CapMrktCurUSD")
            if v not in (None, ""):
                vals[pd.Timestamp(row["time"][:10])] = float(v)
        url = j.get("next_page_url")
        if url:
            time.sleep(0.7)
    return pd.Series(vals).sort_index() if vals else None


def rebuild_from_caps(out, report):
    cat = cm_catalog()
    if cat is None:
        assets = list(dict.fromkeys(FALLBACK_ASSETS))
        report["coinmetrics"] = {"catalog": "failed; fallback list", "requested": len(assets)}
    else:
        assets = [a for a, _ in sorted(cat, key=lambda x: x[1])]
        report["coinmetrics"] = {"catalog": "ok", "requested": len(assets), "firstDates": dict(cat)}
    if "btc" not in assets:
        assets.insert(0, "btc")
    caps = {}
    for i, a in enumerate(assets):
        s = cm_series(a)
        if s is not None and len(s) > 30:
            caps[a] = s
        time.sleep(0.7)
        if (i + 1) % 25 == 0:
            print(f"  coinmetrics {i + 1}/{len(assets)} assets, {len(caps)} with data")
    if "btc" not in caps:
        print("coinmetrics: no BTC cap; rebuild A skipped")
        report["coinmetrics"]["status"] = "no btc"
        return None
    df = pd.DataFrame(caps).sort_index()
    df = df[df.index >= pd.Timestamp("2013-04-28")]
    tot = df.sum(axis=1, skipna=True)
    dom = (100.0 * df["btc"] / tot).dropna()
    n = df.notna().sum(axis=1)
    report["coinmetrics"].update({"status": "ok", "assetsWithData": sorted(caps), "coverageCount": {str(d.date()): int(n.loc[d]) for d in
                                  [pd.Timestamp(x) for x in ("2015-01-01", "2016-01-01", "2016-07-01", "2017-01-01", "2017-07-01", "2018-01-01", "2018-07-01")] if d in n.index},
                                  "topShareByYear": {}})
    # what share of the summed cap the top-10 non-BTC assets carry per year (a thin tail cannot move dominance much)
    for y in range(2015, 2019):
        sub = df[df.index.year == y]
        if len(sub):
            m = sub.mean().drop("btc").sort_values(ascending=False)
            report["coinmetrics"]["topShareByYear"][str(y)] = {"top10": [k for k in m.index[:10]], "top10ShareOfAlts": float(m.iloc[:10].sum() / max(m.sum(), 1e-9))}
    write_csv(os.path.join(out, "BTCD_CAP_1d.csv"), dom)
    print(f"BTCD_CAP: {len(dom)} days {dom.index[0].date()}..{dom.index[-1].date()}, {len(caps)} assets")
    return dom


# ------------------------------------------------------------------------------------------------ B. CoinMarketCap
def _walk(o, found, ts=None):
    if isinstance(o, dict):
        t = o.get("timestamp", ts)
        if "btcDominance" in o and t is not None:
            try:
                found.append((t, float(o["btcDominance"])))
            except (TypeError, ValueError):
                pass
        for v in o.values():
            _walk(v, found, t)
    elif isinstance(o, list):
        for v in o:
            _walk(v, found, ts)


def rebuild_from_cmc(out, report):
    found = []
    raw_saved = False
    y0, y1 = 2013, datetime.now(timezone.utc).year
    for y in range(y0, y1 + 1):
        t0 = int(pd.Timestamp(f"{y}-01-01").timestamp())
        t1 = int(pd.Timestamp(f"{y + 1}-01-01").timestamp())
        r = get(CMC, {"format": "chart_crypto_details", "interval": "1d", "timeStart": t0, "timeEnd": t1}, headers=UA, tries=2, timeout=40)
        if r is None or r.status_code != 200:
            report["cmc"] = {"status": f"http {r.status_code if r is not None else 'n/a'} at {y}"}
            print(f"cmc: {report['cmc']['status']}")
            if r is not None and not raw_saved:
                with open(os.path.join(out, "cmc_raw_error.txt"), "w") as f:
                    f.write(r.text[:4000])
                raw_saved = True
            if y > y0 and found:
                break
            return None
        try:
            j = r.json()
        except ValueError:
            report["cmc"] = {"status": "not json"}
            return None
        if not raw_saved:
            with open(os.path.join(out, "cmc_raw_sample.json"), "w") as f:
                f.write(json.dumps(j)[:20000])
            raw_saved = True
        _walk(j, found)
        time.sleep(1.5)
    if not found:
        report["cmc"] = {"status": "no btcDominance field found; see cmc_raw_sample.json"}
        return None
    vals = {}
    for t, v in found:
        try:
            ts = pd.Timestamp(t) if not isinstance(t, (int, float)) else pd.Timestamp(float(t), unit="s" if float(t) < 1e11 else "ms")
        except (TypeError, ValueError):
            continue
        vals[ts.tz_localize(None).normalize() if ts.tzinfo else ts.normalize()] = v
    dom = pd.Series(vals).sort_index()
    dom = dom[(dom > 0) & (dom <= 100)]
    report["cmc"] = {"status": "ok", "days": int(len(dom)), "first": str(dom.index[0].date()), "last": str(dom.index[-1].date())}
    write_csv(os.path.join(out, "BTCD_CMC_1d.csv"), dom)
    print(f"BTCD_CMC: {len(dom)} days {dom.index[0].date()}..{dom.index[-1].date()}")
    return dom


# ------------------------------------------------------------------------------------------------ splice + report
def weekly(s):
    return s.resample("W-SUN").last().dropna()


def waterfall_2016(w):
    """Largest peak-to-trough fall of weekly closes between Oct 2015 and Jan 2017 (peak before trough)."""
    s = w[(w.index >= pd.Timestamp("2015-10-01")) & (w.index < pd.Timestamp("2017-01-08"))]
    if len(s) < 10:
        return None
    best = None
    v = s.values
    for i in range(len(v)):
        for j in range(i + 1, len(v)):
            d = v[i] - v[j]
            if best is None or d > best[0]:
                best = (d, i, j)
    d, i, j = best
    return {"peak": str(s.index[i].date()), "peakValue": round(float(v[i]), 2), "trough": str(s.index[j].date()),
            "troughValue": round(float(v[j]), 2), "fallPoints": round(float(d), 2), "weeks": int(j - i)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="the data dir (BTC.D_1d.csv from fetch.py must be there)")
    ap.add_argument("--splice-from", default="2018-01-01")
    ap.add_argument("--splice-to", default="2018-07-01")
    ap.add_argument("--skip-cmc", action="store_true")
    ap.add_argument("--skip-cm", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    report = {"runUTC": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}
    tv_path = os.path.join(a.out, "BTC.D_1d.csv")
    tv = None
    if os.path.exists(tv_path):
        df = pd.read_csv(tv_path)
        tv = pd.Series(df["c"].values, index=pd.DatetimeIndex(pd.to_datetime(df["ts"], unit="ms", utc=True)).tz_convert(None)).sort_index()
        tv = tv[~tv.index.duplicated()]
    cap = None if a.skip_cm else rebuild_from_caps(a.out, report)
    cmc = None if a.skip_cmc else rebuild_from_cmc(a.out, report)
    series = {"cap": cap, "cmc": cmc}
    report["waterfall2016"] = {k: waterfall_2016(weekly(v)) for k, v in series.items() if v is not None}
    if tv is not None:
        report["waterfall2016"]["tradingview"] = waterfall_2016(weekly(tv))
        gaps = {}
        for k, v in series.items():
            if v is None:
                continue
            both = pd.concat([weekly(v).rename("r"), weekly(tv).rename("tv")], axis=1).dropna()
            gaps[k] = {str(y): {"meanGap": round(float((g["r"] - g["tv"]).mean()), 2), "maxAbsGap": round(float((g["r"] - g["tv"]).abs().max()), 2), "weeks": int(len(g))}
                       for y, g in both.groupby(both.index.year)}
        report["gapVsTradingViewByYear"] = gaps
        if cmc is not None and cap is not None:
            both = pd.concat([weekly(cmc).rename("a"), weekly(cap).rename("b")], axis=1).dropna()
            report["cmcVsCapByYear"] = {str(y): round(float((g["a"] - g["b"]).mean()), 2) for y, g in both.groupby(both.index.year)}
    primary_name = "cmc" if cmc is not None else ("cap" if cap is not None else None)
    report["primary"] = primary_name
    if primary_name and tv is not None:
        prim = series[primary_name]
        wp, wt = weekly(prim), weekly(tv)
        both = pd.concat([wp.rename("r"), wt.rename("tv")], axis=1).dropna()
        cand = both[(both.index >= pd.Timestamp(a.splice_from)) & (both.index < pd.Timestamp(a.splice_to))]
        if len(cand):
            gap = (cand["r"] - cand["tv"]).abs()
            splice = gap.idxmin()
            report["splice"] = {"week": str(splice.date()), "gapAtSplice": round(float(gap.loc[splice]), 2), "rule": "weekly close nearest between the rebuild and TradingView in [splice-from, splice-to)"}
            d0 = pd.Timestamp(splice)
            spliced = pd.concat([prim[prim.index < d0], tv[tv.index >= d0]]).sort_index()
            spliced = spliced[~spliced.index.duplicated()]
            write_csv(os.path.join(a.out, "BTCD_SPLICED_1d.csv"), spliced)
            print(f"BTCD_SPLICED: {len(spliced)} days, rebuild ({primary_name}) before {splice.date()} (gap {gap.loc[splice]:.2f}), TradingView after")
        wf = report["waterfall2016"].get(primary_name)
        if wf:
            report["parentStart"] = wf["trough"]
            print(f"2016 waterfall ({primary_name}): {wf['peakValue']} on {wf['peak']} -> {wf['troughValue']} on {wf['trough']} ({wf['fallPoints']} pts in {wf['weeks']} w); parent start {wf['trough']}")
    with open(os.path.join(a.out, "caps_report.json"), "w") as f:
        json.dump(report, f, indent=1, default=str)
    print(json.dumps({k: v for k, v in report.items() if k != "coinmetrics"}, default=str)[:1500])
    return 0 if primary_name else 1


if __name__ == "__main__":
    sys.exit(main())
