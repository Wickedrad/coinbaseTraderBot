"""Runner reachability and field-shape probe for the heat-map live capture.
Public endpoints only; prints statuses, key names and a few public quote values."""
import json, time, urllib.request, urllib.error

def get(url, timeout=15):
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "research-probe"})
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            return r.status, body, time.time() - t
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:200], time.time() - t
    except Exception as e:  # noqa
        return -1, str(e).encode()[:200], time.time() - t

out = []
def line(s):
    out.append(s); print(s)

now = int(time.time())
for name, url in [
    ("binance data-api klines", "https://data-api.binance.vision/api/v3/klines?symbol=BTCUSDT&interval=1m&limit=3"),
    ("binance api klines", "https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1m&limit=3"),
    ("binance data-api 1000 old klines", f"https://data-api.binance.vision/api/v3/klines?symbol=SOLUSDT&interval=1m&limit=1000&startTime={(now - 40 * 86400) * 1000}"),
    ("coinbase exchange candles", "https://api.exchange.coinbase.com/products/BTC-USD/candles?granularity=60"),
]:
    s, b, dt = get(url)
    extra = ""
    if s == 200:
        try:
            j = json.loads(b); extra = f"rows={len(j)} first={str(j[0])[:90]} last_open={j[-1][0]}"
        except Exception as e:  # noqa
            extra = f"parse error {e}"
    else:
        extra = b.decode(errors="replace")[:120]
    line(f"- {name}: HTTP {s} in {dt:.2f}s {extra}")

for base in ["https://external-api.kalshi.com/trade-api/v2", "https://api.elections.kalshi.com/trade-api/v2"]:
    line(f"\n**{base}**")
    for series, horizon in [("KXBTC15M", 20 * 60), ("KXBTCD", 65 * 60), ("KXSOL15M", 20 * 60), ("KXXRPD", 65 * 60)]:
        url = f"{base}/markets?series_ticker={series}&status=open&limit=100&min_close_ts={now}&max_close_ts={now + horizon}"
        s, b, dt = get(url)
        if s != 200:
            line(f"- {series} listing: HTTP {s} {b.decode(errors='replace')[:120]}"); continue
        j = json.loads(b); ms = j.get("markets", [])
        line(f"- {series} listing: HTTP 200 in {dt:.2f}s, {len(ms)} markets, cursor={'yes' if j.get('cursor') else 'no'}")
        if not ms: continue
        m = ms[0]
        if series == "KXBTC15M": line(f"  - keys: {sorted(m.keys())}")
        pick = {k: m.get(k) for k in ["ticker", "event_ticker", "open_time", "close_time", "strike_type", "floor_strike", "cap_strike", "yes_bid_dollars", "yes_ask_dollars", "no_bid_dollars", "no_ask_dollars", "yes_bid", "yes_ask", "status", "yes_sub_title", "tick_size", "price_level_structure"] if k in m}
        line(f"  - first: {json.dumps(pick)[:500]}")
        if series.endswith("D"):
            strikes = sorted((x.get("floor_strike"), x.get("yes_bid_dollars"), x.get("yes_ask_dollars")) for x in ms if x.get("floor_strike") is not None)
            mid = [t for t in strikes if t[1] and t[2] and 0.1 < (float(t[1]) + float(t[2])) / 2 < 0.9]
            line(f"  - strikes with yes mid in 0.1-0.9: {len(mid)} of {len(strikes)}; closes: {sorted(set(x.get('close_time') for x in ms))[:4]}")
        t0 = time.time(); codes = []
        for i in range(12):
            s2, b2, _ = get(f"{base}/markets/{ms[i % len(ms)]['ticker']}/orderbook?depth=5")
            codes.append(s2)
        line(f"  - 12 orderbook reads back to back: {time.time() - t0:.2f}s, statuses {sorted(set(codes))}")
        if series == "KXBTC15M" and s2 == 200:
            ob = json.loads(b2); line(f"  - orderbook shape: {json.dumps(ob)[:400]}")
    s, b, dt = get(f"{base}/series/KXBTC15M")
    if s == 200:
        sj = json.loads(b).get("series", {}); line(f"- series KXBTC15M: fee_type={sj.get('fee_type')} fee_multiplier={sj.get('fee_multiplier')} frequency={sj.get('frequency')}")
open("probe_summary.md", "w").write("\n".join(out) + "\n")
