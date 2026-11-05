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
    sold = any(orders.get(x['coid']) == 'exit' for x in fs)  # a maker exit fill is a sale too
    tk_entry = any(x['taker'] and orders.get(x['coid']) == 'entry' for x in fs)
    return ('taker entry' if tk_entry else 'maker entry') + (' + sold early' if sold else ' + held to settlement')
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

# 7. held trace: why did the markets that rode to settlement and lost ride? For each loser (no exit fill, maker or taker), the
# best net profit after fees it ever showed at the bid while the window was open, against the bot's own take-profit floor
# (guards.takeProfit from /api/status, copied to data/takeprofit.json: the larger of floorCents and floorPct of cost), the
# time left at that moment, and the exit orders the bot sent. A loser that was above the floor is split into "the give-back
# sell condition was met and nothing sold" (a defect) and "the price gapped from above the give-back line to below the
# floor between two decisions" (the rule's documented gap case, bot/strategy/fairValueStrategy.ts).
import re
tp = {}
try: tp = json.load(open(os.path.join(data, 'takeprofit.json'))) or {}
except Exception: pass
tp_cents = float(tp.get('floorCents', 2)) / 100
tp_pct = float(tp.get('floorPct', 0.10))
tp_give = float(tp.get('giveBack', 1 / 3))
print(f"take-profit in force: floor max({tp_cents * 100:.0f}c, {tp_pct * 100:.0f}% of cost), give-back {tp_give:.3f}" + ("" if tp else " (defaults: /api/status not read)"))
TICK = 0.01
def window_sec(t): return 900 if '15M' in series_of(t) else None if asset_of(t) == 'tennis' else 3600
def exit_fee(p): return math.ceil(0.07 * p * (1 - p) * 100 - 1e-9) / 100
losers = []
for s_ in day:
    t = s_['ticker']
    fs = mf.get(t, [])
    if s_['realized'] >= 0 or not fs or asset_of(t) == 'tennis': continue
    sold = any(orders.get(x['coid']) == 'exit' for x in fs)
    if not sold: losers.append(s_)
lset = {s_['ticker'] for s_ in losers}
decs = collections.defaultdict(list)
if lset:
    rx = re.compile(r'"ticker":"(KX[^"]+)"')
    for f in sorted(glob.glob(os.path.join(data, 'audit', 'audit-*.jsonl'))):
        with open(f, 'rb') as fh:
            for raw in fh:
                line = raw.decode('utf8', 'replace')
                if '"kind":"decision"' not in line[:200]: continue
                m_ = rx.search(line)
                if not m_ or m_.group(1) not in lset: continue
                try: r = json.loads(line)
                except Exception: continue
                d = r.get('data') or {}
                ts = t_of(r.get('ts', ''))
                if ts is None or ts < day_from - 7200 or not d.get('position') or d.get('bid') is None: continue
                decs[m_.group(1)].append((ts, d['position'], d['bid'], d['ask'], d.get('tauSec') or 0, [x.get('why', '') for x in d.get('place') or [] if x.get('purpose') == 'exit']))
cats = collections.defaultdict(lambda: [0, 0.0])
rows = []
exit_orders = collections.defaultdict(int)
for s_ in losers:
    t = s_['ticker']; fs = sorted(mf[t], key=lambda x: x['ts'])
    ds = sorted(decs.get(t, []))
    buys = [x for x in fs if orders.get(x['coid']) in ('quote', 'entry', 'train', '?')]
    if not buys or not ds: cats['no decision records (opened before the window)'][0] += 1; cats['no decision records (opened before the window)'][1] += s_['realized']; continue
    side = buys[0]['side']; px = buys[0]['price']; px = px / 100 if px > 1.5 else px
    cost = (1 - px) if side == 'ask' else px
    efee = sum(x['fee'] for x in buys) / max(1e-9, sum(x['count'] for x in buys))
    floor = max(tp_cents, tp_pct * (cost + efee))
    win = window_sec(t) or 900
    best, best_tau, ever_exit_try = -9, None, False
    run_best, sell_met, gapped = None, False, False
    prev_net = None
    for ts, pos, bid, ask, tau, why in ds:
        sbid = bid if pos > 0 else 1 - ask
        net = sbid - cost - efee - exit_fee(sbid)
        if why: ever_exit_try = True
        if tau > 60 and net > best: best, best_tau = net, tau
        # replay the rule: armed once the best gain reached the floor; sells at or below max(best x (1 - give-back), floor + tick)
        if net >= floor - 1e-9 and (run_best is None or net > run_best): run_best = net
        if run_best is not None and tau > 0:
            line_ = max(run_best * (1 - tp_give), floor + TICK)
            if net >= floor - 1e-9 and net < run_best - 1e-9 and (net <= floor + TICK + 1e-9 or net <= line_ + 1e-9): sell_met = True
            elif net < floor - 1e-9 and prev_net is not None and prev_net > line_ + 1e-9: gapped = True
        prev_net = net
    in_share = best_tau is not None and best_tau <= 0.10 * win
    if best >= floor:
        k = 'above the floor: ' + ('only in the last 10% of the window' if in_share else
            'give-back sell condition met, nothing sold (defect)' if sell_met else
            'gapped from above the give-back line to below the floor' if gapped else 'armed, never fell back to the sell line before close')
    elif best > 0: k = 'in profit after fees but below the floor'
    else: k = 'never in profit after fees (no rule sells a loser)'
    cats[k][0] += 1; cats[k][1] += s_['realized']
    rows.append((s_['realized'], t, side, cost, best, best_tau, ever_exit_try, floor, k))
print(f"held trace: {len(losers)} markets lost after riding to settlement (no exit fill); why they rode (markets, P&L):")
for k, (n, v) in sorted(cats.items(), key=lambda kv: kv[1][1]):
    print(f"   {k:100s} {n:4d} ${v:9.2f}")
fmt = lambda r, t, sd, c, b, bt, et, fl: f"{t} {sd} cost {c:.2f} best net {b:+.3f} (floor {fl:.3f}) at {('%.0f' % bt) if bt is not None else '-'} s left, exit tried {et}, ${r:.2f}"
print("held trace - 8 worst: " + '; '.join(fmt(*x[:8]) for x in sorted(rows)[:8]))
print("held trace - every loser that was in profit after fees:")
for x in sorted(rows, key=lambda x: -x[4]):
    if x[4] > 0: print(f"   {fmt(*x[:8])} | {x[8]}")

# replay check verdict, when copied: with the file's time and the backtester code it names, so it can be traced
rc = os.path.join(data, 'replay-check-latest.json')
if os.path.exists(rc):
    try:
        v = json.load(open(rc))
        at = time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(os.path.getmtime(rc)))
        keep = {k: v.get(k) for k in ('close', 'checked', 'from', 'to', 'code', 'why') if k in v}
        print(f"latest replay check (file written {at}; the file records no run id or commit):", json.dumps(keep, default=str)[:500])
    except Exception as e:
        print("latest replay check: unreadable", str(e)[:80])
