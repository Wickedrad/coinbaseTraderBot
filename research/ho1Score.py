#!/usr/bin/env python3
"""HO-1 scoring for the market-anchor history lab (registry README, 22:30 UTC Nov 5).

Reads the lab's per-variant results (<name>.json with byDay and byHour, $ after fees, no DOGE) and the regime v1
labels, then for each candidate scores H-HOLD (Aug 1-Nov 4, 6 folds of 16 days) against its paired control and placebo:
  fold won        candidate - control > 0 in that fold
  worst fold      the worst paired diff (candidate - control) $/h over the folds, as registry.py ho1 (own $/h printed too)
  terciles        each hour labelled by the majority regime v1 tercile over all assets' minutes in it; a tercile is
                  covered with >= 100 h; won when candidate - control > 0 over its hours; worst tercile = worst paired diff $/h
  beats placebo   candidate - placebo > 0 over H-HOLD
H-DEV (Apr 18-Jul 31) is printed for reference only: these arms' settings were fixed before the run (none were tuned).
Writes one registry row per arm (append-only shard, with by_tercile and placebo_for so `registry.py ho1` recomputes the
same HO-1 block) and prints a text report.

  python3 research/ho1Score.py --results DIR --labels labels.csv.gz --pairs cand:control:placebo,... \
      --code-sha SHA --out shard.jsonl [--env-json variants.json]
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

DEV = ('2026-04-18', '2026-07-31')
HOLD = ('2026-08-01', '2026-11-04')
FOLDS = 6
FOLD_DAYS = 16
THREAD = 'market-anchor'
FAMILY = 'anchor-ho1'


def days_between(a, b):
    d, e = date.fromisoformat(a), date.fromisoformat(b)
    out = []
    while d <= e:
        out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def make_id(thread, family, arm, code_sha, days, seed=None, phases=None, env=None):
    key = json.dumps([thread, family, arm, code_sha, sorted(days), seed, sorted(phases or []), env or {}], sort_keys=True)
    return hashlib.sha1(key.encode()).hexdigest()[:16]


def hour_terciles(path):
    votes = defaultdict(Counter)
    op = gzip.open if path.endswith('.gz') else open
    with op(path, 'rt') as fh:
        for line in fh:
            f = line.rstrip('\n').split(',')
            if len(f) < 6 or f[5] not in ('LOW', 'MID', 'HIGH'):
                continue
            votes[f[0][:13]][f[5]] += 1
    return {h: c.most_common(1)[0][0] for h, c in votes.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--results', required=True)
    ap.add_argument('--labels', required=True)
    ap.add_argument('--pairs', required=True)
    ap.add_argument('--code-sha', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--env-json', default='')
    ap.add_argument('--replay-version', type=int, default=8)
    a = ap.parse_args()

    res = {}
    for f in sorted(os.listdir(a.results)):
        if f.endswith('.json'):
            j = json.load(open(os.path.join(a.results, f)))
            if j.get('ok', True):
                res[j['name']] = j
    envs = json.load(open(a.env_json)) if a.env_json else {}
    terc = hour_terciles(a.labels)
    hold_days = days_between(*HOLD)
    dev_days = days_between(*DEV)
    have = sorted({d for r in res.values() for d in r.get('byDay', {})})
    hold_days = [d for d in hold_days if d in have] or hold_days
    folds = [hold_days[i * FOLD_DAYS:(i + 1) * FOLD_DAYS] for i in range(FOLDS)]
    pnl = lambda r, ds: sum(r.get('byDay', {}).get(d, 0.0) for d in ds)
    print(f'HO-1 (history tier): H-HOLD {hold_days[0]}..{hold_days[-1]} ({len(hold_days)} days with data), '
          f'{FOLDS} folds of {FOLD_DAYS} d; H-DEV {DEV[0]}..{DEV[1]} for reference; arms {", ".join(sorted(res))}')
    print(f'regime v1 hour labels: {len(terc)} hours (majority tercile over BTC/ETH/SOL/XRP minutes)')
    for name in sorted(res):
        r = res[name]
        print(f'  {name:9s} H-DEV {pnl(r, dev_days):+9.2f}  H-HOLD {pnl(r, hold_days):+9.2f}  trades {r.get("trades", 0)}  fills {r.get("fills", 0)}')

    def by_tercile(r):
        out = {}
        for d in hold_days:
            for hh in range(24):
                k = f'{d}T{hh:02d}'
                t = terc.get(k)
                if t:
                    e = out.setdefault(t, {'pnl': 0.0, 'hours': 0})
                    e['pnl'] += r.get('byHour', {}).get(k, 0.0)
                    e['hours'] += 1
        return {t: {'pnl': round(v['pnl'], 4), 'hours': v['hours']} for t, v in out.items()}

    rows, ids = [], {}
    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    all_days = sorted(have)

    def row(name, role, control=None, heldout=None, verdict=None, placebo_for=None):
        r = res[name]
        env = envs.get(name, {})
        tid = make_id(THREAD, FAMILY, name, a.code_sha, all_days, env=env)
        ids[name] = tid
        out = {'v': 1, 'trial_id': tid, 'ts': now, 'thread': THREAD, 'family': FAMILY, 'arm': name, 'role': role,
               'env': env, 'code_sha': a.code_sha, 'code_epoch': f'REPLAY_VERSION={a.replay_version}', 'base': f'anchor@{a.code_sha[:7]}',
               'data': {'source': 'history', 'days': all_days, 'doge': False, 'benches': 'own', 'books': 'synthetic', 'replay_version': a.replay_version},
               'by_tercile': by_tercile(r),
               # Every replayed day, $0 where the arm made no trade: registry.py ho1 pairs days present in both rows, so a missing
               # zero day would drop out of the held-out score (42137452467: off20 counted on 41 of 94 days).
               'by_day': {d: round(r.get('byDay', {}).get(d, 0.0), 4) for d in all_days},
               'hours': len(all_days) * 24, 'fills': r.get('fills', 0), 'contract_type': 'Price Prediction', 'modules': ['anchor']}
        if control:
            out['control'] = control
        if heldout:
            out['heldout'] = heldout
        if verdict:
            out['verdict'] = verdict
        if placebo_for:
            out['placebo_for'] = placebo_for
        return out

    pairs = [p.split(':') for p in a.pairs.split(',') if p]
    controls = {c for _, c, _ in pairs}
    for c in sorted(controls):
        if c in res:
            rows.append(row(c, 'control'))
    for cand, ctl, plc in pairs:
        if cand not in res or ctl not in res:
            print(f'{cand}: missing results ({cand} or {ctl}), skipped')
            continue
        R, C, P = res[cand], res[ctl], res.get(plc)
        fold_lines, won, worst_own, worst_diff = [], 0, float('inf'), float('inf')
        for i, f in enumerate(folds):
            if not f:
                continue
            h = len(f) * 24
            own, diff = pnl(R, f) / h, (pnl(R, f) - pnl(C, f)) / h
            won += diff > 0
            worst_own, worst_diff = min(worst_own, own), min(worst_diff, diff)
            fold_lines.append(f'f{i + 1} {f[0][5:]}..{f[-1][5:]} own {own:+.2f}/h diff {diff:+.2f}/h')
        hold_set = set(hold_days)
        th = defaultdict(lambda: [0, 0.0, 0.0])  # hours, cand, control
        for d in hold_days:
            for hh in range(24):
                k = f'{d}T{hh:02d}'
                t = terc.get(k)
                if not t:
                    continue
                th[t][0] += 1
                th[t][1] += R.get('byHour', {}).get(k, 0.0)
                th[t][2] += C.get('byHour', {}).get(k, 0.0)
        cov = {t: v for t, v in th.items() if v[0] >= 100}
        t_won = sum(1 for v in cov.values() if v[1] - v[2] > 0)
        worst_t = min(((v[1] - v[2]) / v[0] for v in cov.values()), default=float('nan'))
        beats = P is not None and pnl(R, hold_days) - pnl(P, hold_days) > 0
        passed = (len(hold_days) >= 90 and won >= 4 and worst_diff >= -0.5 and len(cov) >= 2 and t_won >= 2
                  and worst_t >= -0.5 and beats and a.replay_version >= 8)
        ho = {'standard': 'HO-1', 'tier': 'history', 'days': len(hold_days), 'folds': len(fold_lines), 'folds_won': won,
              'worst_fold_per_hour': round(worst_diff, 4), 'terciles_covered': len(cov), 'terciles_won': t_won,
              'worst_tercile_per_hour': round(worst_t, 4), 'beats_placebo': bool(beats), 'replay_version': a.replay_version}
        rows.append(row(cand, 'candidate', ids.get(ctl), ho, 'pass' if passed else 'fail'))
        if P is not None:
            rows.append(row(plc, 'placebo', ids.get(ctl), placebo_for=cand))
        print(f'\n{cand} vs {ctl} (placebo {plc}): HO-1 {"PASS" if passed else "FAIL"}')
        print(f'  H-HOLD {pnl(R, hold_days):+.2f} vs control {pnl(C, hold_days):+.2f} vs placebo {pnl(P, hold_days) if P else float("nan"):+.2f}; '
              f'folds won {won}/{len(fold_lines)}, worst fold own {worst_own:+.2f}/h, worst diff {worst_diff:+.2f}/h')
        print('  ' + ' | '.join(fold_lines))
        f5 = [d for f in folds[:5] for d in f]
        won5 = sum(1 for f in folds[:5] if f and pnl(R, f) - pnl(C, f) > 0)
        print(f'  without fold 6 (Oct 20-Nov 4, where the anchor settings were tuned): won {won5}/5, '
              f'diff {(pnl(R, f5) - pnl(C, f5)) / max(1, 24 * len(f5)):+.3f}/h, vs placebo {((pnl(R, f5) - pnl(P, f5)) / max(1, 24 * len(f5))) if P else float("nan"):+.3f}/h')
        print('  terciles: ' + ', '.join(f'{t} {v[0]} h cand {v[1] / v[0]:+.2f}/h ctl {v[2] / v[0]:+.2f}/h' for t, v in sorted(th.items())))
    seen, uniq = set(), []
    for r in rows:
        if r['trial_id'] not in seen:
            seen.add(r['trial_id'])
            uniq.append(r)
    with open(a.out, 'w') as fh:
        for r in uniq:
            fh.write(json.dumps(r) + '\n')
    print(f'\nregistry shard: {len(uniq)} rows -> {a.out}')


if __name__ == '__main__':
    main()
