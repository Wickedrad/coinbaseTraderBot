#!/usr/bin/env python3
"""HO-1 held-out score for a benched-jobs run (project standard, registry README, Nov 5).
Usage: benched_ho1.py <results dir> <regime v1 labels.csv[.gz] or ''> <out.json>
Settings are chosen on H-DEV (Apr 18-Jul 31 2026) and scored once on H-HOLD (Aug 1-Nov 4 2026), in 6 consecutive
16-day folds. Every arm is scored PAIRED against the baseline (the run's control): $/h of (arm - baseline).
  folds:    folds won (paired gain > 0) and the worst fold's paired $/h.
  terciles: the regime v1 RV tercile (LOW/MID/HIGH) of each trade's coin at the top of its close hour; a tercile's $/h is
            its paired P&L over its bot-hours (coin-hours labelled with it / coins labelled that hour), covered at >= 100 h.
  placebo:  the arm's paired H-HOLD $/h beats the random market-skip placebo's (skip37, else the first skip*/placebo* arm).
Prints the table and writes {arm: heldout block + dev/hold $/h} for the registry rows. Aggregates only (public repo)."""
import collections, csv, glob, gzip, json, os, sys
from datetime import date, datetime, timedelta, timezone

src, labels_path, out = sys.argv[1], sys.argv[2], sys.argv[3]
DEV = ('2026-04-18', '2026-07-31')
HOLD0 = date(2026, 8, 1)
FOLDS = [[(HOLD0 + timedelta(days=16 * k + i)).isoformat() for i in range(16)] for k in range(6)]
HOLD = [d for f in FOLDS for d in f]

res = {}
for f in sorted(glob.glob(os.path.join(src, '*.json'))):
    try: r = json.load(open(f))
    except Exception: continue
    if isinstance(r, dict) and r.get('byDay') is not None:
        res[r.get('name') or os.path.basename(f)[:-5]] = r
if 'baseline' not in res: sys.exit('no baseline')
base = res['baseline']
replay_version = int(os.environ.get('TJ_REPLAY_VERSION', '0') or 0)
days_seen = sorted({d for r in res.values() for d in r['byDay']})
hold_days = [d for d in HOLD if days_seen and days_seen[0] <= d <= days_seen[-1]]
dev_days = [d for d in days_seen if DEV[0] <= d <= DEV[1]]

def paired(r, days):
    return sum(r['byDay'].get(d, 0.0) - base['byDay'].get(d, 0.0) for d in days) / (24 * len(days)) if days else float('nan')

# Regime v1 labels at the top of each hour: (coin, 'YYYY-MM-DDTHH') -> LOW/MID/HIGH.
lab = {}
if labels_path and os.path.exists(labels_path):
    op = gzip.open if labels_path.endswith('.gz') else open
    with op(labels_path, 'rt') as fh:
        rd = csv.DictReader(fh)
        for row in rd:
            t = (row.get('t') or row.get('ts') or row.get('time') or '').strip()
            if not t: continue
            if t.replace('.', '').isdigit():
                x = float(t); x = x / 1000 if x > 1e12 else x
                dt = datetime.fromtimestamp(x, tz=timezone.utc)
            else:
                try: dt = datetime.fromisoformat(t.replace('Z', '+00:00'))
                except Exception: continue
            if dt.minute != 0: continue
            k = dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H')
            if not (HOLD[0] <= k[:10] <= HOLD[-1]): continue
            terc = (row.get('tercile') or '').strip().upper()
            if terc in ('LOW', 'MID', 'HIGH'): lab[((row.get('asset') or '').upper(), k)] = terc
coins_at = collections.Counter(k for (_, k) in lab)
terc_hours = collections.Counter()
for (c, k), t in lab.items(): terc_hours[t] += 1 / coins_at[k]

def by_tercile(r):
    pnl = collections.Counter()
    for side, sign in ((r, 1), (base, -1)):
        for key, v in (side.get('byAssetHour') or {}).items():
            coin, hour = key.split('|', 1)
            t = lab.get((coin, hour))
            if t: pnl[t] += sign * v
    return {t: (pnl[t] / terc_hours[t] if terc_hours[t] else float('nan'), terc_hours[t]) for t in ('LOW', 'MID', 'HIGH')}

arms = {a['name']: a for a in json.loads(os.environ.get('TJ_ARMS_JSON') or '[]')}
pfor = {a['placeboFor']: n for n, a in arms.items() if a.get('placeboFor') and n in res}
placebo = 'skip37' if 'skip37' in res else next((a for a in res if a.startswith('skip') or a.startswith('placebo')), None)
pl_hold = paired(res[placebo], hold_days) if placebo else None
outj, lines = {}, []
lines.append(f"HO-1 held-out (history tier): choose on H-DEV {dev_days[0] if dev_days else '-'}..{dev_days[-1] if dev_days else '-'} ({len(dev_days)} d), "
             f"score on H-HOLD {hold_days[0] if hold_days else '-'}..{hold_days[-1] if hold_days else '-'} ({len(hold_days)} d) in 6 folds of 16 d; "
             f"paired vs baseline; placebo {placebo}; replay v{replay_version}; labels {'yes (' + str(len(lab)) + ' coin-hours)' if lab else 'MISSING'}")
for arm, r in sorted(res.items(), key=lambda kv: -paired(kv[1], hold_days) if kv[0] != 'baseline' else 1e9):
    if arm == 'baseline':
        continue
    fv = [paired(r, [d for d in f if d in hold_days]) for f in FOLDS if any(d in hold_days for d in f)]
    tv = by_tercile(r) if lab else {}
    cov = [t for t, (v, h) in tv.items() if h >= 100]
    won = [t for t in cov if tv[t][0] > 0]
    hold = paired(r, hold_days)
    own_pl = pfor.get(arm, placebo)
    own_hold = paired(res[own_pl], hold_days) if own_pl in res else None
    beats = (arms.get(arm, {}).get('role') != 'placebo') and arm != own_pl and own_hold is not None and hold > own_hold
    blk = {'standard': 'HO-1', 'tier': 'history', 'days': len(hold_days), 'folds': len(fv), 'folds_won': sum(1 for v in fv if v > 0),
           'worst_fold_per_hour': round(min(fv), 4) if fv else None, 'terciles_covered': len(cov), 'terciles_won': len(won),
           'worst_tercile_per_hour': round(min(tv[t][0] for t in cov), 4) if cov else None, 'beats_placebo': bool(beats),
           'replay_version': replay_version}
    ok = (blk['days'] >= 90 and blk['folds_won'] >= 4 and (blk['worst_fold_per_hour'] or -9) >= -0.5 and blk['terciles_won'] >= 2
          and (blk['worst_tercile_per_hour'] if blk['worst_tercile_per_hour'] is not None else -9) >= -0.5 and beats and replay_version >= 8)
    outj[arm] = {'heldout': {k: v for k, v in blk.items() if v is not None}, 'dev_per_hour': round(paired(r, dev_days), 4), 'hold_per_hour': round(hold, 4), 'ho1_pass': ok}
    lines.append(f"{arm:16s} {'PASS' if ok else 'fail'} | H-DEV {paired(r, dev_days):+.2f}/h | H-HOLD {hold:+.2f}/h ({own_pl} {own_hold if own_hold is not None else float('nan'):+.2f}) | folds "
                 + ' '.join(f'{v:+.2f}' for v in fv) + f" ({blk['folds_won']}/6) | terciles "
                 + ', '.join(f"{t} {tv[t][0]:+.2f} ({tv[t][1]:.0f} h)" for t in ('LOW', 'MID', 'HIGH') if t in tv))
json.dump(outj, open(out, 'w'))
print('\n'.join(lines))
