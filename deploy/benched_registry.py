#!/usr/bin/env python3
"""Trial registry rows for a benched-jobs run (the meta plan thread's registry, research/registry.py on its branch).
Usage: benched_registry.py <results dir> <run id> <code sha> <registry.py> <out.jsonl> [labels.csv[.gz]]
One row per arm and family from research/out/benched-jobs/<arm>.json (byDay: $ after fees, DOGE dropped from the replayed
days). Roles, families and placebo_for come from the run's arms (env TJ_ARMS_JSON, research/benchedJobs.ts ARMS); the
baseline is each family's control. With regime v1 labels, by_tercile ({LOW|MID|HIGH: {pnl, hours}} over H-HOLD) is
filled from each arm's byAssetHour, so `registry.py ho1` can score HO-1. Aggregates only (public repository)."""
import collections, csv, glob, gzip, importlib.util, json, os, sys
from datetime import datetime, timezone

src, run, sha, reg_py, out = sys.argv[1:6]
labels_path = sys.argv[6] if len(sys.argv) > 6 else ''
spec = importlib.util.spec_from_file_location('registry', reg_py)
reg = importlib.util.module_from_spec(spec); spec.loader.exec_module(reg)
thread = os.environ.get('TJ_THREAD') or 'benched'
replay_version = int(os.environ.get('TJ_REPLAY_VERSION') or 0) or None
H_HOLD = getattr(reg, 'H_HOLD', ('2026-08-01', '2026-11-04'))

arms = {a['name']: a for a in json.loads(os.environ.get('TJ_ARMS_JSON') or '[]')}
res = {}
for f in sorted(glob.glob(os.path.join(src, '*.json'))):
    try: r = json.load(open(f))
    except Exception: continue
    if isinstance(r, dict) and r.get('byDay') is not None:
        res[r.get('name') or os.path.basename(f)[:-5]] = r
if 'baseline' not in res:
    sys.exit('no baseline result')
days = sorted({d for r in res.values() for d in r['byDay']})

# Regime v1 labels at the top of each hour of H-HOLD: (coin, 'YYYY-MM-DDTHH') -> LOW/MID/HIGH.
lab = {}
if labels_path and os.path.exists(labels_path):
    op = gzip.open if labels_path.endswith('.gz') else open
    with op(labels_path, 'rt') as fh:
        for row in csv.DictReader(fh):
            t = (row.get('t') or row.get('ts') or row.get('time') or '').strip()
            if not t: continue
            try:
                if t.replace('.', '').isdigit():
                    x = float(t); dt = datetime.fromtimestamp(x / 1000 if x > 1e12 else x, tz=timezone.utc)
                else:
                    dt = datetime.fromisoformat(t.replace('Z', '+00:00')).astimezone(timezone.utc)
            except Exception:
                continue
            if dt.minute != 0: continue
            k = dt.strftime('%Y-%m-%dT%H')
            if not (H_HOLD[0] <= k[:10] <= H_HOLD[1]): continue
            terc = (row.get('tercile') or '').strip().upper()
            if terc in ('LOW', 'MID', 'HIGH'): lab[((row.get('asset') or '').upper(), k)] = terc
coins_at = collections.Counter(k for (_, k) in lab)
terc_hours = collections.Counter()
for (c, k), t in lab.items(): terc_hours[t] += 1 / coins_at[k]

def by_tercile(r):
    if not lab or not r.get('byAssetHour'): return None
    pnl = collections.Counter()
    for key, v in r['byAssetHour'].items():
        coin, hour = key.split('|', 1)
        t = lab.get((coin, hour))
        if t: pnl[t] += v
    return {t: {'pnl': round(pnl[t], 4), 'hours': round(terc_hours[t], 1)} for t in ('LOW', 'MID', 'HIGH')}

def meta(arm):
    a = arms.get(arm) or {}
    if arm == 'baseline': return 'control', None, None
    role = a.get('role') or ('placebo' if arm.startswith(('skip', 'placebo')) else 'neighbour')
    return role, a.get('family') or 'benched', a.get('placeboFor')

fams = sorted({meta(a)[1] for a in res if a != 'baseline'} - {None}) or ['benched']
ids = {fam: reg.make_id(thread, fam, 'baseline', sha, days, None, None, {}) for fam in fams}
now = datetime.now(timezone.utc).isoformat(timespec='seconds')
rows = []
for arm, r in sorted(res.items()):
    role, fam, pfor = meta(arm)
    for fam in (fams if arm == 'baseline' else [fam]):
        env = (arms.get(arm) or {}).get('env') or {}
        tid = ids[fam] if arm == 'baseline' else reg.make_id(thread, fam, arm, sha, days, None, None, env)
        data = {'source': 'history', 'days': days, 'doge': False, 'benches': 'own', 'books': 'synthetic', 'engine': 'replay',
                'copy': os.environ.get('TJ_REPLAY_DRIVE', 'gdrive:kalshi-bot-archive/simulated') + ' + models/benched-server-pin'}
        if replay_version: data['replay_version'] = replay_version
        row = {'v': 1, 'trial_id': tid, 'ts': now, 'thread': thread, 'family': fam, 'arm': arm, 'role': role, 'env': env,
               'code_sha': sha, 'data': data, 'by_day': {d: round(float(r['byDay'].get(d, 0.0)), 4) for d in days},
               'hours': 24.0 * len(days), 'ref': f'https://github.com/Wickedrad/coinbaseTraderBot/actions/runs/{run}'}
        bt = by_tercile(r)
        if bt: row['by_tercile'] = bt
        if arm != 'baseline': row['control'] = ids[fam]
        if pfor: row['placebo_for'] = pfor
        if isinstance(r.get('trades'), int): row['fills'] = r['trades']
        rows.append(row)

bad = 0
with open(out, 'w') as fh:
    for row in rows:
        err, fl = reg.validate(row)
        if err:
            bad += 1; print(f"invalid {row['arm']}: {err}", file=sys.stderr); continue
        if fl: row['flags'] = sorted(set(row.get('flags', []) + fl))
        fh.write(json.dumps(row) + '\n')
print(f"registry: {len(rows) - bad} row(s) for run {run} -> {out}" + (f", {bad} invalid" if bad else '') + (f"; terciles from {len(lab)} coin-hours" if lab else '; no tercile labels'))
