#!/usr/bin/env python3
"""Paper pool audit (read-only): where did the Kalshi paper account's cash come from?
Usage: pool_audit.py <data dir>
Inputs (all copied to the runner, never published; this prints aggregates only):
  <data>/state/*.json, epochs.jsonl     the bot's small state files (paper_exchange, training, vault, ...)
  <data>/drive-paper/<day>/...          the nightly Drive snapshots of paper_exchange.json (cash, funded, refilled)
  <data>/audit/audit-*.jsonl[.gz]       the audit log (fills, settlements, training refills, recon balance reads)
  <data>/facts/*.txt                    bot.env keys, journal restarts, deploy log, crontab (text)
Sections: 1 settings and restarts, 2 current state, 3 daily snapshots (funded / refilled / earned),
          4 refills and top-ups in the audit log, 5 ledger replay against the balance reads, 6 per-day P&L."""
import collections, glob, gzip, json, os, re, sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

data = sys.argv[1] if len(sys.argv) > 1 else 'data'
NY = ZoneInfo('America/New_York')


def iso(s):
    try: return datetime.fromisoformat(str(s).replace('Z', '+00:00')).timestamp()
    except Exception: return None


def T(ts):
    if ts is None: return '?'
    d = datetime.fromtimestamp(ts, timezone.utc); e = d.astimezone(NY)
    return f"{d:%b %d %H:%M} UTC ({e:%b %d %I:%M %p} {e.tzname()})"


def jload(p):
    try:
        with open(p) as fh: return json.load(fh)
    except Exception:
        return None


def hdr(t): print(f"\n=== {t}")


def usd(x): return f"${x:,.2f}" if x >= 0 else f"-${-x:,.2f}"


def text(p, n=None):
    try:
        with open(p, errors='replace') as fh: lines = fh.read().splitlines()
        return lines if n is None else lines[-n:]
    except Exception:
        return []


# ---------------------------------------------------------------- 1. settings and restarts
hdr('1. settings, restarts, deploys (facts copied off the server)')
st = jload(f'{data}/facts/status.json')
if st:
    print('-- /api/status now (selected fields):')
    print('   ' + json.dumps({k: st.get(k) for k in ('mode', 'uptimeSec', 'balance', 'bankroll', 'dailyPnl', 'dailyLossLimit')}))
    print('   vault ' + json.dumps(st.get('vault'))[:700])
    print('   kalshiAccount ' + json.dumps(st.get('kalshiAccount'))[:500])
    print('   perps ' + json.dumps(st.get('perps'))[:700])
for f in ('env.txt', 'corrupt.txt', 'cron.txt'):
    ls = text(f'{data}/facts/{f}')
    print(f"-- {f} ({len(ls)} lines)")
    for l in ls[:60]: print('   ' + l[:240])
jr = text(f'{data}/facts/journal.txt')
starts = collections.Counter(); stops = collections.Counter(); bad = []
for l in jr:
    m = re.match(r'^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2}:\d{2})\S*\s', l)
    if not m: continue
    if 'Started ' in l: starts[m.group(1)] += 1
    if re.search(r'Main process exited|Failed with result|oom|Killed|killed', l): bad.append(l[:200])
print(f"-- journal: service 'Started' lines per day (UTC offset as the server prints it): {dict(sorted(starts.items()))}")
print(f"-- journal: abnormal exits / kills: {len(bad)}")
for l in bad[-25:]: print('   ' + l)
dl = text(f'{data}/facts/deploys.log')
print(f"-- deploys.log: {len(dl)} lines; last 30:")
for l in dl[-30:]: print('   ' + l[:220])

# ---------------------------------------------------------------- 2. current state
hdr('2. state on the server now')
pe = jload(f'{data}/state/paper_exchange.json')


def pe_summary(pe):
    pos = {t: q for t, q in (pe.get('positions') or {}).items() if abs(q) > 1e-9}
    basis = sum((pe.get('basis') or {}).get(t, {}).get('yesCost', 0) + (pe.get('basis') or {}).get(t, {}).get('noCost', 0) for t in pos)
    return dict(balance=pe.get('balance'), funded=pe.get('funded'), refilled=pe.get('refilled', 0), npos=len(pos), basis=basis,
                nfills=len(pe.get('fills') or []), fills_from=(pe.get('fills') or [{}])[0].get('ts'))


if pe:
    s = pe_summary(pe)
    print(f"paper_exchange.json: cash(balance, holds included) {usd(s['balance'])} | funded {s['funded']} | refilled {s['refilled']} | open positions {s['npos']} costing {usd(s['basis'])} | fills kept {s['nfills']}")
    print(f"   cash + open-position cost = {usd(s['balance'] + s['basis'])}; minus funded + refilled ({usd((s['funded'] or 0) + s['refilled'])}) = {usd(s['balance'] + s['basis'] - (s['funded'] or 0) - s['refilled'])}  <- what the account earned since its books began (fees on open entries already paid)")
else:
    print('paper_exchange.json not readable')
tr = jload(f'{data}/state/training.json')
if tr:
    k = tr.get('kalshi') or {}
    print(f"training.json kalshi epoch: {json.dumps({x: k.get(x) for x in ('epoch', 'startTs', 'startEquity', 'peak', 'trough', 'fills', 'refills', 'refilled', 'pool')})}")
    if k.get('startTs'): print(f"   epoch began {T(k['startTs']/1000)}")
ep = [json.loads(l) for l in text(f'{data}/state/epochs.jsonl') if l.strip()]
print(f"epochs.jsonl: {len(ep)} capital-exhaustion records (kalshi {sum(1 for e in ep if e.get('book')=='kalshi')}, perps {sum(1 for e in ep if e.get('book')=='perps')})")
for e in ep:
    print(f"   {e.get('book')} epoch {e.get('epoch')}: {T(e.get('startTs',0)/1000)} -> {T(e.get('endTs',0)/1000)} ({e.get('hours')} h) start {e.get('startEquity')} peak {e.get('peak')} trough {e.get('trough')} end {e.get('endEquity')} REFILL {e.get('refill')} fills {e.get('fills')}")
kref = sum(e.get('refill', 0) for e in ep if e.get('book') == 'kalshi')
print(f"   Kalshi refills in epochs.jsonl total {usd(kref)}")
vt = jload(f'{data}/state/vault.json')
if vt:
    ev = vt.get('events') or []
    print(f"vault.json: vault {usd(vt.get('vault', 0))} | pocket {usd(sum(p.get('amount', 0) for p in vt.get('pocket') or []))} | withdrawnTotal {vt.get('withdrawnTotal')} | realized {json.dumps(vt.get('realized'))}")
    kinds = collections.defaultdict(lambda: [0, 0.0])
    for e in ev: kinds[e.get('kind')][0] += 1; kinds[e.get('kind')][1] += e.get('amount', 0)
    print(f"   events kept {len(ev)} (newest 500): " + ', '.join(f"{k}:{v[0]} ${v[1]:.2f}" for k, v in sorted(kinds.items(), key=lambda x: str(x[0]))))
    led = [e for e in ev if e.get('kind') == 'ledger']
    print(f"   ledger restarts (one per refill): {len(led)}; first {T(led[0]['ts']/1000) if led else '-'}, last {T(led[-1]['ts']/1000) if led else '-'}")
    for e in led[-12:]: print(f"      {T(e['ts']/1000)}: {str(e.get('note'))[:170]}")
    if ev: print(f"   oldest event kept {T(ev[0]['ts']/1000)}; newest {T(ev[-1]['ts']/1000)}")
bm = jload(f'{data}/state/balance_monitor.json')
if bm: print(f"balance_monitor.json: {json.dumps(bm)[:300]}")
eg = jload(f'{data}/state/equity_guard.json')
if eg: print(f"equity_guard.json (head): {json.dumps({k: v for k, v in eg.items() if not isinstance(v, (list, dict))})[:400]}")

# ---------------------------------------------------------------- 3. daily snapshots
hdr('3. nightly Drive snapshots of paper_exchange.json (funded / refilled never go down unless the books were replaced)')
snaps = []
for p in sorted(glob.glob(f'{data}/drive-paper/*/paper_exchange.json')):
    j = jload(p)
    if not j: continue
    s = pe_summary(j)
    snaps.append((os.path.getmtime(p), os.path.basename(os.path.dirname(p)), s))
if pe:
    snaps.append((os.path.getmtime(f'{data}/state/paper_exchange.json'), 'server now', pe_summary(pe)))
snaps.sort(key=lambda x: x[0])
prev = None
print(f"{'snapshot time':46} {'cash':>9} {'open cost':>9} {'equity':>9} {'funded':>7} {'refilled':>8} {'earned*':>9}  note")
for ts, day, s in snaps:
    eq = (s['balance'] or 0) + s['basis']; net = eq - (s['funded'] or 0) - s['refilled']
    note = ''
    if prev:
        if (s['funded'] or 0) < (prev['funded'] or 0) - 1e-6 or s['refilled'] < prev['refilled'] - 1e-6: note += ' <-- funded/refilled WENT DOWN (books replaced?)'
        if s['refilled'] > prev['refilled'] + 1e-6: note += f" refilled +{s['refilled']-prev['refilled']:.2f}"
        if (s['funded'] or 0) > (prev['funded'] or 0) + 1e-6: note += f" funded +{(s['funded'] or 0)-(prev['funded'] or 0):.2f}"
    print(f"{T(ts):46} {s['balance']:9.2f} {s['basis']:9.2f} {eq:9.2f} {s['funded'] or 0:7.0f} {s['refilled']:8.2f} {net:9.2f} {note}")
    prev = s
print('   *earned = cash + open-position cost - funded - refilled (the account against every dollar ever put in)')

# ---------------------------------------------------------------- 4/5. audit log
hdr('4. audit log: refills, top-ups, restarts, rebases')
WANT = {b'fill', b'settlement', b'training', b'vault', b'recon_ok', b'recon_break', b'recon_adopt', b'recon_repair', b'startup', b'shutdown', b'kill_engaged', b'kill_reset'}
def fkey(f):
    m = re.match(r'audit-(\d{4}-\d{2}-\d{2})(?:\.(\d+))?\.jsonl', os.path.basename(f))
    return (m.group(1), int(m.group(2) or 0)) if m else (os.path.basename(f), 0)


files = sorted(glob.glob(f'{data}/audit/audit-*.jsonl*'), key=fkey)
print(f"audit files: {len(files)}; first {os.path.basename(files[0]) if files else '-'}; last {os.path.basename(files[-1]) if files else '-'}")
ev = []   # (ts, kind, dict)
nlines = 0
for f in files:
    op = gzip.open if f.endswith('.gz') else open
    try:
        with op(f, 'rb') as fh:
            for line in fh:
                nlines += 1
                i = line.find(b'"kind":"', 0, 200)
                if i < 0: continue
                j = line.find(b'"', i + 8)
                kind = line[i + 8:j]
                if kind not in WANT: continue
                try: r = json.loads(line)
                except Exception: continue
                ts = iso(r.get('ts'))
                if ts is None: continue
                d = r.get('data') or {}
                k = kind.decode()
                if k == 'startup':
                    cfgd = d.get('config') or {}
                    d = dict(pid=d.get('pid'), mode=cfgd.get('mode'), bankroll=[(kk, vv) for kk, vv in cfgd.items() if re.search(r'bankroll|pool', kk, re.I) and isinstance(vv, (int, float))])
                ev.append((ts, k, d))
    except Exception as e:
        print(f"   could not read {f}: {e}")
print(f"lines read {nlines:,}; kept {len(ev):,} events of the kinds above")
ev.sort(key=lambda x: x[0])
cnt = collections.Counter(k for _, k, _ in ev)
print('event counts:', dict(cnt))
if ev: print(f"window {T(ev[0][0])} -> {T(ev[-1][0])}")

starts_ev = [(t, d) for t, k, d in ev if k == 'startup']
stops_ev = [(t, d) for t, k, d in ev if k == 'shutdown']
print(f"\nbot starts in the audit window: {len(starts_ev)}; clean shutdown records: {len(stops_ev)}")
byday = collections.Counter(datetime.fromtimestamp(t, timezone.utc).strftime('%m-%d') for t, _ in starts_ev)
print('   starts per UTC day:', dict(sorted(byday.items())))
for t, d in starts_ev[-20:]: print(f"   start {T(t)} pid {d.get('pid')} mode {d.get('mode')} pool setting {d.get('bankroll')}")
pools = sorted({tuple(map(tuple, d.get('bankroll') or [])) for _, d in starts_ev})
print('   distinct bankroll settings seen at startups:', pools[:10])

tr_ev = [(t, d) for t, k, d in ev if k == 'training']
trc = collections.Counter(d.get('event') for _, d in tr_ev)
print('\ntraining events:', dict(trc))
refills = []   # (ts, amount, kind)
for t, d in tr_ev:
    e = d.get('event')
    if e == 'capital_exhaustion' and d.get('book') == 'kalshi':
        refills.append((t, float(d.get('refill') or 0), 'refill after exhaustion'))
        print(f"   REFILL  {T(t)}: +{d.get('refill')} (epoch {d.get('epoch')}, ran {d.get('hours')} h, ended with equity {d.get('endEquity')}, fills {d.get('fills')})")
    elif e == 'pool_raised' and d.get('book') == 'kalshi':
        refills.append((t, float(d.get('topUp') or 0), 'pool raised'))
        print(f"   POOL    {T(t)}: raised {d.get('from')} -> {d.get('to')}, topUp +{d.get('topUp')} (bankroll {d.get('bankroll')}, equity {d.get('equity')})")
    elif e in ('kill_released', 'break_even_raised'):
        pass
print(f"   total Kalshi refills + top-ups in the audit window: {usd(sum(a for _, a, _ in refills))} in {len(refills)} events")
rb = [(t, d) for t, k, d in ev if k == 'vault' and d.get('event') == 'paper_rebase']
print(f"\nvault 'paper_rebase' events (an unexplained balance move that the books re-anchored to): {len(rb)}")
for t, d in rb[:30]: print(f"   {T(t)}: deposit {d.get('deposit')} withdrawal {d.get('withdrawal')} balance {d.get('balance')}")
print(f"recon breaks {cnt.get('recon_break', 0)}, repairs {cnt.get('recon_repair', 0)}, adopts {cnt.get('recon_adopt', 0)}, kill engaged {cnt.get('kill_engaged', 0)}, kill reset {cnt.get('kill_reset', 0)}")

# ---------------------------------------------------------------- 5. replay
hdr('5. ledger replay: every fill and settlement in the audit log against the cash reads')
import bisect
_st = sorted((t, d.get('mode')) for t, d in starts_ev)
_stt = [t for t, _ in _st]
def mode_at(ts):
    i = bisect.bisect_right(_stt, ts) - 1
    return _st[i][1] if i >= 0 else None
skipped = collections.Counter()
vault_lv = []                   # (ts, vault level after a win event)
vevents = collections.defaultdict(lambda: [0, 0.0])
pos = {}
cum = 0.0                       # cumulative trading cash flow (fills net of fees + settlement payouts)
fees_cum = 0.0
flow_pts = []                   # (ts, cum, refills cumulative)
obs = []                        # (ts, resid, balance, trigger)
rc = 0.0
ri = 0
refills.sort()
daily = collections.defaultdict(lambda: dict(fills=0, taker=0, fees=0.0, flow=0.0, settles=0, realized=0.0, wins=0))
orphan = 0
refill_marks = []
for ts, k, d in ev:
    while ri < len(refills) and refills[ri][0] <= ts:
        rc += refills[ri][1]; ri += 1
    day = datetime.fromtimestamp(ts, timezone.utc).strftime('%Y-%m-%d')
    if k in ('fill', 'settlement', 'recon_ok') and mode_at(ts) not in ('paper', None):
        skipped[(k, mode_at(ts))] += 1
        continue
    if k == 'vault':
        vevents[d.get('event')][0] += 1
        try: vevents[d.get('event')][1] += float(d.get('amount') or 0)
        except Exception: pass
        stt = d.get('status') or {}
        if isinstance(stt, dict) and stt.get('vault') is not None: vault_lv.append((ts, float(stt['vault'])))
        continue
    if k == 'training' and d.get('event') == 'capital_exhaustion' and d.get('book') == 'kalshi':
        refill_marks.append((ts, cum, d))
    if k == 'fill':
        fl = d.get('fill') or {}
        t = fl.get('ticker'); n = float(fl.get('count') or 0); price = float(fl.get('price') or 0); side = fl.get('side')
        fee = float(d.get('fee') or fl.get('fee') or 0)
        after = d.get('position')
        if after is not None: p0 = (after - n) if side == 'bid' else (after + n)
        else: p0 = pos.get(t, 0.0)
        if side == 'bid':
            closing = min(n, max(0.0, -p0)); flow = closing * (1 - price) - (n - closing) * price
        else:
            closing = min(n, max(0.0, p0)); flow = closing * price - (n - closing) * (1 - price)
        flow -= fee
        pos[t] = after if after is not None else (p0 + n if side == 'bid' else p0 - n)
        cum += flow; fees_cum += fee
        dd = daily[day]; dd['fills'] += 1; dd['taker'] += 1 if fl.get('isTaker') else 0; dd['fees'] += fee; dd['flow'] += flow
        if d.get('orphan'): orphan += 1
    elif k == 'settlement':
        t = d.get('ticker'); res = d.get('result'); p = pos.pop(t, 0.0)
        pay = p if (p > 0 and res == 'yes') else (-p if (p < 0 and res == 'no') else 0.0)
        cum += pay
        dd = daily[day]; dd['flow'] += pay; dd['settles'] += 1; dd['realized'] += float(d.get('realized') or 0); dd['wins'] += 1 if (d.get('realized') or 0) > 0 else 0
    elif k == 'recon_ok' and d.get('balance') is not None:
        obs.append((ts, float(d['balance']) - cum - rc, float(d['balance']), d.get('trigger')))
print(f"fills replayed {sum(v['fills'] for v in daily.values()):,} (orphan {orphan}), settlements {sum(v['settles'] for v in daily.values()):,}, fees {usd(fees_cum)}; trading cash flow over the window {usd(cum)}; refills + top-ups {usd(rc)}")
print(f"balance reads (recon_ok): {len(obs):,}; events skipped because the bot ran in another mode (live): {dict(skipped)}")
# resid = balance read - replayed flows - refills. A constant resid (+ holds, which only lower it) = nothing unexplained.
if obs:
    env = collections.OrderedDict()
    for ts, r, b, trig in obs:
        h = int(ts // 3600)
        env[h] = max(env.get(h, -1e18), r)
    hs = sorted(env)
    base = max(env.values())
    print(f"hourly upper envelope of (balance read - replay): max {base:.2f}; this is the starting cash if holds were 0 at some moment each hour")
    print('\nlevel shifts in the envelope (|shift| >= $2, 3 h before vs 3 h after):')
    shifts = []
    for i, h in enumerate(hs):
        before = [env[x] for x in hs[max(0, i - 3):i]]
        after = [env[x] for x in hs[i:i + 3]]
        if not before or not after: continue
        sh = max(after) - max(before)
        if abs(sh) >= 2.0: shifts.append((h, sh))
    merged = []
    for h, sh in shifts:
        if merged and h - merged[-1][0] <= 2: continue
        merged.append((h, sh))
    near = [(t, k, d) for t, k, d in ev if k in ('startup', 'shutdown', 'training', 'recon_break', 'recon_adopt', 'kill_engaged') or (k == 'vault' and d.get('event') == 'paper_rebase')]
    for h, sh in merged[:80]:
        lo, hi = h * 3600 - 1800, h * 3600 + 7200
        why = [f"{k}{'/' + str(d.get('event')) if k in ('training', 'vault') else ''}@{datetime.fromtimestamp(t, timezone.utc):%H:%M}" for t, k, d in near if lo <= t <= hi][:6]
        print(f"   {T(h*3600)}: shift {sh:+.2f}   nearby: {', '.join(why) or '-'}")
    print(f"   {len(merged)} shift(s) found")
    # end to end
    ts0, r0, b0, _ = obs[0]; ts1, r1, b1, _ = obs[-1]
    print(f"\nfirst read {T(ts0)} balance {b0:.2f}; last read {T(ts1)} balance {b1:.2f}")
    print(f"replayed change over the window: trading {usd(cum)} + refills {usd(rc)} = {usd(cum + rc)}")
    # daily resid envelope to show drift
    dayenv = collections.OrderedDict()
    for ts, r, b, trig in obs:
        dkey = datetime.fromtimestamp(ts, timezone.utc).strftime('%m-%d')
        e = dayenv.setdefault(dkey, [1e18, -1e18, 0]); e[0] = min(e[0], r); e[1] = max(e[1], r); e[2] += 1
    print('per UTC day, resid (balance read - replay - refills) low / high / reads (high should stay flat):')
    for dkey, (lo_, hi_, n_) in dayenv.items(): print(f"   {dkey}: {lo_:9.2f} / {hi_:9.2f} / {n_}")
    # restart boundaries
    print('\nacross each bot restart: last envelope before vs first after (start-of-day cash lost or gained shows here):')
    obs_sorted = obs
    for t, d in starts_ev[-30:]:
        bef = [r for ts, r, _, _ in obs_sorted if t - 1800 <= ts < t]
        aft = [r for ts, r, _, _ in obs_sorted if t <= ts < t + 1800]
        if bef and aft:
            print(f"   start {T(t)}: before max {max(bef):.2f} (n={len(bef)}) / after max {max(aft):.2f} (n={len(aft)}) / jump {max(aft)-max(bef):+.2f}")

# ---------------------------------------------------------------- 6. per day
hdr('6. per UTC day from the audit log (trading cash flow = fills net of fees + settlement payouts, before any refill)')
print(f"{'day':10} {'fills':>6} {'taker':>6} {'fees':>8} {'settled':>7} {'win%':>5} {'realized(net)':>13} {'cash flow':>10}")
tot = [0, 0, 0.0, 0, 0.0, 0.0]
for day in sorted(daily):
    v = daily[day]
    print(f"{day:10} {v['fills']:6d} {v['taker']:6d} {v['fees']:8.2f} {v['settles']:7d} {(100*v['wins']/v['settles'] if v['settles'] else 0):5.0f} {v['realized']:13.2f} {v['flow']:10.2f}")
    tot[0] += v['fills']; tot[1] += v['taker']; tot[2] += v['fees']; tot[3] += v['settles']; tot[4] += v['realized']; tot[5] += v['flow']
print(f"{'total':10} {tot[0]:6d} {tot[1]:6d} {tot[2]:8.2f} {tot[3]:7d} {'':5} {tot[4]:13.2f} {tot[5]:10.2f}")
print('\nrealized(net) is the sum of the settlement events (fee-inclusive); cash flow also counts positions opened and still held at the edges.')

# ---------------------------------------------------------------- 7. refills against the vault
hdr('7. each Kalshi refill: cash the account still held, the vault, and the bankroll the refill saw')
print('bank before = pool - refill (the supervisor adds pool - tradable bankroll); tradable bankroll = cash + committed - vault, floored at 0')
print(f"{'refill time':46} {'refill':>8} {'bank before':>11} {'equity (cash)':>13} {'vault then':>10} {'equity-vault':>12} {'trading flow since last refill':>30}")
prev_cum = None
rows = []
for ts, c, d in refill_marks:
    vl = [v for t, v in vault_lv if t <= ts]
    vlevel = vl[-1] if vl else None
    pool = 200 if ts >= 1793340000 else 100
    rf = float(d.get('refill') or 0)
    flow = (c - prev_cum) if prev_cum is not None else None
    prev_cum = c
    eqv = d.get('endEquity')
    rows.append((ts, rf, eqv, vlevel))
    print(f"{T(ts):46} {rf:8.2f} {pool - rf:11.2f} {eqv if eqv is not None else float('nan'):13.2f} {vlevel if vlevel is not None else float('nan'):10.2f} {(eqv - vlevel) if (eqv is not None and vlevel is not None) else float('nan'):12.2f} {('%.2f' % flow) if flow is not None else '-':>30}")
big = [r for r in rows if r[2] is not None and r[2] >= 100]
print(f"refills made while the account still held >= $100 in cash: {len(big)} of {len(rows)}, adding {usd(sum(r[1] for r in big))} of {usd(sum(r[1] for r in rows))}")
print('\nvault audit events:', {k: (v[0], round(v[1], 2)) for k, v in sorted(vevents.items(), key=lambda x: str(x[0]))})
pe_ep = [e for e in ep if e.get('book') == 'perps']
print(f"perps paper refills in epochs.jsonl: {len(pe_ep)} totalling {usd(sum(e.get('refill', 0) for e in pe_ep))}")
