#!/usr/bin/env python3
"""Round 17 data: daily USD prices for single coins from the Coin Metrics community API (free, no key).

The TradingView history in data/ has no single alt coins. This writes <COIN>USD_1d.csv (same csv shape as fetch.py)
for the coins that existed through the parent fractal (2016-17), so matched days can be read on them.
Runs on the GitHub runner (the cloud session container cannot reach the host):
  python3 research/btcd_fractal/round17/fetch_coins.py --out research/btcd_fractal/data
"""
import argparse, sys, time
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fetch_caps import CM, get, write_csv  # noqa: E402

COINS = {"xrp": "XRPUSD", "xlm": "XLMUSD", "doge": "DOGEUSD", "ltc": "LTCUSD", "eth": "ETHUSD"}


def price(asset, start="2013-01-01"):
    url, params, vals = f"{CM}/timeseries/asset-metrics", {"assets": asset, "metrics": "PriceUSD", "frequency": "1d", "start_time": start, "page_size": 10000}, {}
    while url:
        r = get(url, params); params = None
        if r is None or r.status_code != 200:
            return None
        j = r.json()
        for row in j.get("data", []):
            v = row.get("PriceUSD")
            if v not in (None, ""):
                vals[pd.Timestamp(row["time"][:10])] = float(v)
        url = j.get("next_page_url")
        if url:
            time.sleep(0.7)
    return pd.Series(vals).sort_index() if vals else None


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", required=True); a = ap.parse_args()
    ok = 0
    for asset, name in COINS.items():
        s = price(asset)
        if s is None or not len(s):
            print(f"{name}: no data"); continue
        write_csv(Path(a.out) / f"{name}_1d.csv", s); ok += 1
        print(f"{name}: {len(s)} days {s.index[0].date()}..{s.index[-1].date()} last {s.iloc[-1]:.6g}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
