#!/usr/bin/env python3
"""Pool audit zoom (read-only): minute by minute around a refill.
Usage: pool_zoom.py <data dir> <from ISO UTC> <to ISO UTC> [more from/to pairs...]
Prints, for each window: every training / vault / startup / shutdown / kill event (short), then a 1-minute table of the
cash read (recon_ok balance = cash - resting holds), fills and trading cash flow in that minute, and settlements."""
import collections, glob, gzip, json, os, re, sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

data = sys.argv[1]
NY = ZoneInfo('America/New_York')


def iso(s):
    try: return datetime.fromisoformat(str(s).replace('Z', '+00:00')).timestamp()
    except Exception: return None


def T(ts):
    d = datetime.fromtimestamp(ts, timezone.utc); e = d.astimezone(NY)
    return f"{d:%b %d %H:%M:%S} UTC ({e:%I:%M:%S %p} {e.tzname()})"


def Tm(ts):
    d = datetime.fromtimestamp(ts, timezone.utc); e = d.astimezone(NY)
    return f"{d:%H:%M} UTC ({e:%I:%M %p} {e.tzname()})"


wins = []
a = sys.argv[2:]
for i in range(0, len(a) - 1, 2):
    w0 = iso(a[i] + ('Z' if not a[i].endswith('Z') and '+' not in a[i] else '')); w1 = iso(a[i + 1] + ('Z' if not a[i + 1].endswith('Z') and '+' not in a[i + 1] else ''))
    wins.append((w0, w1))
WANT = (b'fill', b'settlement', b'training', b'vault', b'recon_ok', b'startup', b'shutdown', b'kill_engaged', b'kill_reset', b'recon_break')


def fkey(f):
    m = re.match(r'audit-(\d{4}-\d{2}-\d{2})(?:\.(\d+))?\.jsonl', os.path.basename(f))
    return (m.group(1), int(m.group(2) or 0)) if m else (os.path.basename(f), 0)


files = sorted(glob.glob(f'{data}/audit/audit-*.jsonl*'), key=fkey)
days = {datetime.fromtimestamp(t, timezone.utc).strftime('%Y-%m-%d') for w in wins for t in (w[0], w[1])}
for w0, w1 in wins:
    print(f"\n===== window {T(w0)} -> {T(w1)}")
    evs = []
    for f in files:
        m = re.match(r'audit-(\d{4}-\d{2}-\d{2})', os.path.basename(f))
        if not m or m.group(1) not in days: continue
        op = gzip.open if f.endswith('.gz') else open
        with op(f, 'rb') as fh:
            for line in fh:
                i = line.find(b'"kind":"', 0, 200)
                if i < 0: continue
                j = line.find(b'"', i + 8)
                kind = line[i + 8:j]
                if kind not in WANT: continue
                k = line.find(b'"ts":"', 0, 80)
                ts = iso(line[k + 6:line.find(b'"', k + 6)].decode()) if k >= 0 else None
                if ts is None or ts < w0 or ts > w1: continue
                try: r = json.loads(line)
                except Exception: continue
                evs.append((ts, kind.decode(), r.get('data') or {}))
    evs.sort(key=lambda x: x[0])
    print(f"{len(evs)} events in the window: {dict(collections.Counter(k for _, k, _ in evs))}")
    print('-- events (training / vault / start / stop / kill / recon_break):')
    for ts, k, d in evs:
        if k in ('training', 'startup', 'shutdown', 'kill_engaged', 'kill_reset', 'recon_break') or (k == 'vault' and d.get('event') != 'win'):
            if k == 'startup': d = dict(pid=d.get('pid'), mode=(d.get('config') or {}).get('mode'))
            print(f"   {T(ts)} {k}: {json.dumps(d)[:420]}")
    print('-- wins that moved the vault (vault level after each win, first and every change):')
    last = None
    for ts, k, d in evs:
        if k == 'vault' and d.get('event') == 'win':
            v = (d.get('status') or {}).get('vault')
            if v != last: print(f"   {T(ts)} win realized {d.get('realized')} vault {v} quota {(d.get('status') or {}).get('quotaFilled')} realized-total {((d.get('status') or {}).get('realized') or {}).get('total')}"); last = v
    print('-- per minute: cash read (last), fills, trading flow, settlements, realized')
    pos = {}
    per = collections.OrderedDict()
    for ts, k, d in evs:
        mnt = int(ts // 60)
        row = per.setdefault(mnt, dict(bal=None, n=0, flow=0.0, st=0, rz=0.0, tr=None))
        if k == 'recon_ok' and d.get('balance') is not None: row['bal'] = float(d['balance']); row['tr'] = d.get('trigger')
        elif k == 'fill':
            fl = d.get('fill') or {}
            t = fl.get('ticker'); n = float(fl.get('count') or 0); price = float(fl.get('price') or 0); side = fl.get('side'); fee = float(d.get('fee') or 0)
            after = d.get('position')
            p0 = ((after - n) if side == 'bid' else (after + n)) if after is not None else pos.get(t, 0.0)
            if side == 'bid':
                closing = min(n, max(0.0, -p0)); flow = closing * (1 - price) - (n - closing) * price
            else:
                closing = min(n, max(0.0, p0)); flow = closing * price - (n - closing) * (1 - price)
            row['flow'] += flow - fee; row['n'] += 1
            pos[t] = after if after is not None else (p0 + n if side == 'bid' else p0 - n)
        elif k == 'settlement':
            p = pos.pop(d.get('ticker'), 0.0); res = d.get('result')
            row['flow'] += p if (p > 0 and res == 'yes') else (-p if (p < 0 and res == 'no') else 0.0)
            row['st'] += 1; row['rz'] += float(d.get('realized') or 0)
    print(f"   {'minute':36} {'cash read':>9} {'fills':>5} {'flow':>8} {'settled':>7} {'realized':>9}")
    for mnt, r in per.items():
        print(f"   {Tm(mnt * 60):36} {('%.2f' % r['bal']) if r['bal'] is not None else '-':>9} {r['n']:5d} {r['flow']:8.2f} {r['st']:7d} {r['rz']:9.2f}")
