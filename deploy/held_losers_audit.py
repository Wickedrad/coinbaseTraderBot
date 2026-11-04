#!/usr/bin/env python3
"""Held-to-settlement audit (read-only; daily health check ask, Nov 4): what paper's positions that rode to settlement
looked like on the way, and what a take-profit would have done with them.
Usage: held_losers_audit.py <audit dir> [from ISO] [to ISO]
For every market paper still held at settlement, the close-now P&L along the bot's decision records (cash so far + the
position closed at the touch, taker fee in): its best (MFE), its worst (MAE), the time left at the best, and the result.
Then rules that close a held market the first time the close-now P&L reaches +X cents a contract, with and without the
take-profit's fair-value confirm (the coin's fair value of the side at most the net bid + m), against riding: the
losers saved and the winners given up, by series, entry price band, side and market state.
Prints aggregates only (public repository)."""
import collections, glob, json, math, os, sys
from datetime import datetime

src = sys.argv[1] if len(sys.argv) > 1 else 'data/audit'
t_from = sys.argv[2] if len(sys.argv) > 2 else ''
t_to = sys.argv[3] if len(sys.argv) > 3 else ''

def ts_of(iso):
    try: return datetime.fromisoformat(iso.replace('Z', '+00:00')).timestamp()
    except Exception: return None
lo, hi = (ts_of(t_from) if t_from else -1e18), (ts_of(t_to) if t_to else 1e18)

def taker_fee(n, p):
    return math.ceil(0.07 * n * p * (1 - p) * 100 - 1e-9) / 100 if n > 0 else 0.0

fills, decs, settles = collections.defaultdict(list), collections.defaultdict(list), {}
want = ('"kind":"fill"', '"kind":"settlement"', '"kind":"decision"', '"kind": "fill"', '"kind": "settlement"', '"kind": "decision"')
files = sorted(glob.glob(os.path.join(src, 'audit-*.jsonl'))) + sorted(glob.glob(os.path.join(src, 'audit-*.jsonl.gz')))
import gzip
for f in files:
    op = gzip.open if f.endswith('.gz') else open
    with op(f, 'rb') as fh:
        for raw in fh:
            line = raw.decode('utf8', 'replace')
            if not any(w in line[:200] for w in want): continue
            try: r = json.loads(line)
            except Exception: continue
            k, d, ts = r.get('kind'), r.get('data') or {}, ts_of(r.get('ts', ''))
            if ts is None: continue
            if k == 'fill':
                fl = d.get('fill') or {}
                if fl.get('ticker'): fills[fl['ticker']].append((ts, fl.get('side'), fl.get('count') or 0, fl.get('price') or 0, d.get('fee') or 0))
            elif k == 'decision':
                if d.get('ticker') and d.get('bid') is not None and d.get('ask') is not None:
                    ms = d.get('mstate') or {}
                    decs[d['ticker']].append((ts, d['bid'], d['ask'], d.get('fv'), d.get('tauSec'), ms.get('rv1h'), ms.get('volRatio')))
            elif k == 'settlement':
                if lo <= ts <= hi and d.get('ticker'): settles[d['ticker']] = (ts, d.get('result'), d.get('realized') or 0)

def series(t):
    return '15m' if '15M' in t.upper() else ('1h' if any(x in t.upper() for x in ('KXBTCD', 'KXETHD', 'KXSOLD', 'KXXRPD', 'KXDOGED', '1H')) else t.split('-')[0])

def band(p):
    return 'lt30' if p < 0.30 else ('30-50' if p < 0.50 else ('50-70' if p < 0.70 else '70+'))

def vol_key(rv, vr):
    b = f"vol{2 ** round(math.log2(rv * 1e4)):g}bp" if rv and rv > 0 else 'vol?'
    return f"{b}|{'?' if vr is None else ('rising' if vr > 1 else 'calming')}"

rows = []
for t, (sts, result, realized) in settles.items():
    fs = sorted(fills.get(t, []))
    if not fs: continue
    pos, cash, exits = 0, 0.0, 0
    for (_, side, n, p, fee) in fs:
        if side == 'bid': pos += n; cash -= p * n + fee
        else: pos -= n; cash += p * n - fee
    if abs(pos) < 1e-9: continue  # closed before settlement: not this group
    held = abs(pos); sign = 1 if pos > 0 else -1
    entry_ts = fs[0][0]
    # Entry side price per contract (fees in), from the buys of the held side.
    buys = [(n, p, fee) for (_, side, n, p, fee) in fs if (side == 'bid') == (sign > 0)]
    nb = sum(n for n, _, _ in buys) or 1
    side_entry = sum((p if sign > 0 else 1 - p) * n for n, p, _ in buys) / nb
    path = []
    for (ts, bid, ask, fv, tau, rv, vr) in decs.get(t, []):
        if ts < entry_ts or ts > sts: continue
        # Cash and position at ts (fills up to ts).
        pz, cz = 0, 0.0
        for (fts, side, n, p, fee) in fs:
            if fts > ts: break
            if side == 'bid': pz += n; cz -= p * n + fee
            else: pz -= n; cz += p * n - fee
        if abs(pz) < 1e-9: continue
        sp = bid if pz > 0 else 1 - ask  # side price we would sell at
        close = cz + (pz * bid if pz > 0 else pz * ask) - taker_fee(abs(pz), sp)
        fv_side = None if fv is None else (fv if pz > 0 else 1 - fv)
        path.append((ts, close / abs(pz), close, sp, fv_side, tau, rv, vr, abs(pz)))
    if not path: continue
    best = max(path, key=lambda x: x[1]); worst = min(path, key=lambda x: x[1])
    st0 = path[0]
    rows.append({'t': t, 'realized': realized, 'held': held, 'series': series(t), 'band': band(side_entry), 'side': 'yes' if sign > 0 else 'no',
                 'state': vol_key(st0[6], st0[7]), 'mfe': best[1], 'mfe_tau': best[5], 'mae': worst[1], 'path': path})

def rule(x, m=None, min_tau=0):
    """Close at the first record whose close-now P&L >= +x a contract (and, with m, fv of the side <= net side bid + m)."""
    out = []
    for r in rows:
        got = None
        for (ts, per, close, sp, fvs, tau, rv, vr, n) in r['path']:
            if per >= x and (tau or 0) >= min_tau and (m is None or (fvs is not None and fvs <= sp - taker_fee(n, sp) / n + m)):
                got = close; break
        out.append((r, got if got is not None else r['realized']))
    return out

los = [r for r in rows if r['realized'] < 0]; win = [r for r in rows if r['realized'] >= 0]
tot = sum(r['realized'] for r in rows)
print(f"== held to settlement {t_from or 'start'} .. {t_to or 'end'}: {len(rows)} markets (of {len(settles)} settled), ridden P&L ${tot:.2f}; losers {len(los)} ${sum(r['realized'] for r in los):.2f}, winners {len(win)} ${sum(r['realized'] for r in win):.2f}")
if los:
    ever = [r for r in los if r['mfe'] > 0]
    print(f"losers ever in profit after the exit fee: {len(ever)} of {len(los)}; best close-now per contract: median {sorted(r['mfe'] for r in los)[len(los)//2]*100:+.1f}c, "
          f"of those in profit median {sorted(r['mfe'] for r in ever)[len(ever)//2]*100 if ever else float('nan'):+.1f}c; worst before settling median {sorted(r['mae'] for r in los)[len(los)//2]*100:+.1f}c")
    taus = [r['mfe_tau'] for r in ever if r['mfe_tau'] is not None]
    if taus: print(f"  time left at their best: median {sorted(taus)[len(taus)//2]/60:.1f} min")
    for key in ('series', 'band', 'side', 'state'):
        g = collections.defaultdict(lambda: [0, 0.0, 0])
        for r in los: g[r[key]][0] += 1; g[r[key]][1] += r['realized']; g[r[key]][2] += r['mfe'] > 0
        print(f"  losers by {key}: " + ', '.join(f"{k} {v[0]} ${v[1]:.0f} ({v[2]} in profit once)" for k, v in sorted(g.items(), key=lambda kv: kv[1][1])))
print("rules on every held market (close at first +x c/contract after the exit fee; vs riding to settlement):")
for x in (0.0, 0.01, 0.02, 0.03, 0.05, 0.08):
    for m in (None, 0.02, 0.0):
        res = rule(x, m)
        pl = sum(v for _, v in res)
        saved = sum(v - r['realized'] for r, v in res if r['realized'] < 0)
        lost = sum(v - r['realized'] for r, v in res if r['realized'] >= 0)
        closed = sum(1 for r, v in res if v != r['realized'])
        print(f"  +{x*100:.0f}c{'' if m is None else f' fv<=bid+{m*100:.0f}c'}: P&L ${pl:.2f} ({pl - tot:+.2f}) | losers {saved:+.2f}, winners {lost:+.2f} | {closed} closed early")
best = max(((x, m) for x in (0.0, 0.01, 0.02, 0.03, 0.05, 0.08) for m in (None, 0.02, 0.0)), key=lambda xm: sum(v for _, v in rule(*xm)))
res = rule(*best)
for key in ('series', 'band', 'side', 'state'):
    g = collections.defaultdict(float)
    for r, v in res: g[r[key]] += v - r['realized']
    print(f"  best rule (+{best[0]*100:.0f}c{'' if best[1] is None else f' fv<=bid+{best[1]*100:.0f}c'}) vs riding by {key}: " + ', '.join(f"{k} {v:+.2f}" for k, v in sorted(g.items(), key=lambda kv: kv[1])))
