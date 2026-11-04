#!/usr/bin/env python3
"""Adversary for the daily health check (read-only): tries to break the last day's paper P&L.
Usage: adversary_report.py <data dir> [hours=24] [lag file]
  - luck: the day's realized P&L against 0 +/- the hourly SD of the last days x sqrt(hours)
  - settlement truth: the bot's settlements against the Kalshi check's verdicts (audit 'kalshi_check' events)
  - fill realism: P&L and contracts from maker quote fills (simulated by the paper exchange) vs taker fills
  - stale quotes: fills within 60 s after a data-lag / feed-drop warning (lag file: one ISO time per line)
  - concentration: the day without its 3 best markets
  - why: where the day's P&L came from (series, asset, entry route, exits, entry price band, EST hour block)
Runs on a GitHub runner from files copied off the server; prints aggregates only."""
import collections, glob, json, math, os, sys, time
from datetime import datetime, timezone

data = sys.argv[1] if len(sys.argv) > 1 else 'data'
hours = float(sys.argv[2]) if len(sys.argv) > 2 else 24.0
lag_file = sys.argv[3] if len(sys.argv) > 3 else ''

def t_of(iso):
    try: return datetime.fromisoformat(iso.replace('Z', '+00:00')).timestamp()
    except Exception: return None

now = time.time()
day_from = now - hours * 3600
fills, settles, orders, checks = [], [], {}, collections.Counter()
want = ('"kind":"fill"', '"kind":"settlement"', '"kind":"order_new"', '"kind":"kalshi_check')
for f in sorted(glob.glob(os.path.join(data, 'audit', 'audit-*.jsonl'))):
    with open(f, 'rb') as fh:
        for raw in fh:
            line = raw.decode('utf8', 'replace')
            if not any(w in line[:200] for w in want): continue
            try: r = json.loads(line)
            except Exception: continue
            k, d, ts = r.get('kind'), r.get('data') or {}, t_of(r.get('ts', ''))
            if ts is None: continue
            if k == 'fill':
                fl = d.get('fill') or {}
                fills.append({'ts': ts, 'ticker': fl.get('ticker', ''), 'count': fl.get('count') or 0, 'price': fl.get('price') or 0,
                              'taker': bool(fl.get('isTaker')), 'fee': d.get('fee') or 0, 'coid': d.get('clientOrderId'),
                              'side': fl.get('side') or fl.get('action') or ''})
            elif k == 'settlement':
                settles.append({'ts': ts, 'ticker': d.get('ticker', ''), 'realized': d.get('realized') or 0})
            elif k == 'order_new':
                orders[d.get('clientOrderId')] = d.get('purpose') or '?'
            elif str(k).startswith('kalshi_check') and ts >= day_from:
                checks[f"{k}:{d.get('event') or d.get('type') or ''}"] += 1

day = [s for s in settles if s['ts'] >= day_from]
total = sum(s['realized'] for s in day)
print(f"== adversary: last {hours:g} h to {time.strftime('%Y-%m-%d %H:%M', time.gmtime(now))} UTC | settled markets {len(day)} | realized ${total:.2f}")

# 1. luck: hourly realized over every full hour in the files, the day's own hours included
by_hour = collections.defaultdict(float)
for s in settles: by_hour[int(s['ts'] // 3600)] += s['realized']
if by_hour:
    lo, hi = min(by_hour), max(by_hour)
    series = [by_hour.get(h, 0.0) for h in range(lo, hi)]
    if len(series) >= 12:
        m = sum(series) / len(series)
        sd = math.sqrt(sum((x - m) ** 2 for x in series) / (len(series) - 1))
        band = sd * math.sqrt(hours)
        z = total / band if band else float('nan')
        verdict = 'beyond luck' if abs(z) >= 2 else 'not distinguishable from luck'
        print(f"luck: hourly SD ${sd:.2f} over {len(series)} h (mean ${m:.2f}/h) -> day 0 +/- ${band:.2f} per SD; z {z:+.2f}: {verdict}")
    else:
        print(f"luck: only {len(series)} hours of settlements in the files")

# 2. settlement truth
print(f"settlement truth: Kalshi check events in the window {dict(checks) or 'none in the audit (see /api/status kalshiCheck)'}")

# 3. fill realism and 4. stale quotes
lags = []
if lag_file and os.path.exists(lag_file):
    for l in open(lag_file):
        t = t_of(l.strip())
        if t: lags.append(t)
lags.sort()
def stale(ts):
    import bisect
    i = bisect.bisect_right(lags, ts) - 1
    return i >= 0 and ts - lags[i] <= 60
dfills = [x for x in fills if x['ts'] >= day_from]
agg = collections.defaultdict(lambda: [0, 0.0, 0.0])  # n, contracts, fees
for x in dfills:
    key = ('taker' if x['taker'] else 'maker (simulated queue)', orders.get(x['coid'], '?'))
    a = agg[key]; a[0] += 1; a[1] += x['count']; a[2] += x['fee']
print("fills by type and purpose (n, contracts, fees):")
for (typ, pur), (n, c, fe) in sorted(agg.items(), key=lambda kv: -kv[1][1]):
    print(f"   {typ:24s} {pur:12s} {n:5d} {c:10.1f} ${fe:.2f}")
maker_markets = collections.Counter(x['ticker'] for x in dfills if not x['taker'])
taker_markets = collections.Counter(x['ticker'] for x in dfills if x['taker'])
mk = sum(s['realized'] for s in day if maker_markets[s['ticker']] and not taker_markets[s['ticker']])
tk = sum(s['realized'] for s in day if taker_markets[s['ticker']] and not maker_markets[s['ticker']])
mixed = total - mk - tk
print(f"realized by how the market was traded: maker fills only ${mk:.2f} | taker fills only ${tk:.2f} | both ${mixed:.2f}")
st = [x for x in dfills if stale(x['ts'])]
st_m = {x['ticker'] for x in st}
print(f"stale-quote fills (within 60 s after {len(lags)} lag / feed-drop warnings): {len(st)} fills, {sum(x['count'] for x in st):.1f} contracts,"
      f" in {len(st_m)} markets realizing ${sum(s['realized'] for s in day if s['ticker'] in st_m):.2f}")

# 5. concentration
per = collections.defaultdict(float)
for s in day: per[s['ticker']] += s['realized']
top = sorted(per.items(), key=lambda kv: -kv[1])[:3]
print(f"concentration: best 3 markets ${sum(v for _, v in top):.2f} ({', '.join(f'{t} ${v:.2f}' for t, v in top)}) -> without them ${total - sum(v for _, v in top):.2f}")
worst = sorted(per.items(), key=lambda kv: kv[1])[:3]
print(f"   worst 3 markets: {', '.join(f'{t} ${v:.2f}' for t, v in worst)}")

# 6. why: attribute the day's realized P&L (per settled market) to series, asset, entry route, exits, entry price band and hour
def series_of(t): return t.split('-')[0] if t else '?'
def asset_of(t):
    for a in ('BTC', 'ETH', 'SOL', 'XRP', 'DOGE'):
        if series_of(t).startswith('KX' + a): return a
    return 'tennis' if 'ATP' in t or 'WTA' in t else 'other'
mf = collections.defaultdict(list)
for x in dfills: mf[x['ticker']].append(x)
def table(title, groups):
    print(f"why - {title} (markets, P&L, avg/market, win %):")
    for k, (n, pnl, w) in sorted(groups.items(), key=lambda kv: kv[1][1])[:12]:
        print(f"   {str(k):34s} {n:4d} ${pnl:9.2f} ${pnl / n:7.2f} {100 * w / n:4.0f}%")
def group(keyf):
    g = {}
    for s_ in day:
        k = keyf(s_)
        n, pnl, w = g.get(k, (0, 0.0, 0))
        g[k] = (n + 1, pnl + s_['realized'], w + (1 if s_['realized'] > 0 else 0))
    return g
table('by series', group(lambda s_: series_of(s_['ticker'])))
table('by asset', group(lambda s_: asset_of(s_['ticker'])))
def route(s_):
    fs = mf.get(s_['ticker'], [])
    purposes = {orders.get(x['coid'], '?') for x in fs}
    if not fs: return 'no fills in window (opened earlier)'
    tk_exit = any(x['taker'] and orders.get(x['coid']) == 'exit' for x in fs)
    tk_entry = any(x['taker'] and orders.get(x['coid']) == 'entry' for x in fs)
    return ('taker entry' if tk_entry else 'maker entry') + (' + sold early' if tk_exit else ' + held to settlement')
table('by entry route and exit', group(route))
def band(s_):
    fs = sorted(mf.get(s_['ticker'], []), key=lambda x: x['ts'])
    if not fs: return 'n/a'
    p = fs[0]['price']; p = p / 100 if p > 1.5 else p
    b = '<0.30' if p < 0.30 else '0.30-0.70' if p <= 0.70 else '>0.70'
    return f"{fs[0]['side'] or '?'} {b}"
table('by first fill side and price (dollars, YES scale)', group(band))
def est_block(s_):
    h = (time.gmtime(s_['ts']).tm_hour - 5) % 24
    return f"{h // 4 * 4:02d}-{h // 4 * 4 + 4:02d} EST"
table('by 4-hour block (EST)', group(est_block))
big = sorted(per.items(), key=lambda kv: kv[1])[:5]
print("why - 5 worst markets:", '; '.join(f"{t} ${v:.2f}" for t, v in big))

# replay check verdict, when copied
rc = os.path.join(data, 'replay-check-latest.json')
if os.path.exists(rc):
    try:
        v = json.load(open(rc))
        print("latest replay check:", json.dumps({k: v.get(k) for k in ('verdict', 'close', 'from', 'to', 'stretch', 'replay', 'paper') if k in v}, default=str)[:600])
    except Exception as e:
        print("latest replay check: unreadable", str(e)[:80])
