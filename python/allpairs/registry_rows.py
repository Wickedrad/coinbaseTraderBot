"""Trial-registry rows (the meta plan's registry v1, research/registry.py on branch claude/project-thread-79ntof) for
all-pairs runs: one row per hypothesis config x gated arm (base, stress, tight), with dollars per out-of-sample day.

    python -m allpairs.registry_rows --results <run dir> --run-id <id> --code-sha <sha> --out <shard.jsonl>
        [--prior <dir of earlier all-pairs shards>] [--run-url URL]

<run dir> holds the run's combined results as the report job keeps them on Drive (models/all-pairs/runs/<run>/):
one folder per hypothesis config with <arm>.json and gate.json, or (older runs) the arm files at the top.

Roles: the run's base configuration (config named base or base_ctrl) is the control; every other config's base arm
is a candidate paired with a control on the same out-of-sample days (CONTROLS below, else the in-run control); the
stress and tight arms are neighbours (the same configuration under worse costs / without wide books) paired with
the config's own base arm. Synthetic arms are not trials and get no row.
HO-1 runs (--protocol ho1, rows with a heldout block): every config's base arm is a candidate and every arm is paired
with a no-trade control row ($0 on each held-out day), the benchmark the HO-1 block is judged against.
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import hashlib
import json
import os

THREAD = 'all-pairs'
FAMILY = 'all-pairs-policy'     # every configuration asks one question: does a learned entry/exit policy beat $0?
GATED = ('base', 'stress', 'tight')
# Runs without their own base configuration: (control run, control config). Same out-of-sample days as the run.
CONTROLS = {
    '42060065859': ('42054088258', 'base'),          # taker_only, early_entries, exit_allow vs base (4a628f9)
    '42065715159': ('42054088258', 'base'),          # lead_btc
    '42088667467': ('42088067536', 'base_ctrl'),     # keep_crossed vs base re-scored on the same engine
}
# A later run with no base of its own pairs with the current base: keep_crossed IS the base since b3c8581
# (max_crossed 99 default, same config hash da11163cef).
DEFAULT_CONTROL = ('42088667467', 'keep_crossed')
# Measured P(settle YES) of the historical tier (diag run 42088067536): training pool with crossed windows dropped vs
# all windows. Used for runs that predate the per-fold measurement.
PYES_DROPPED = (0.423, 0.498)
PYES_KEPT = (0.498, 0.498)


def make_id(thread, family, arm, code_sha, days, seed=None, phases=None, env=None) -> str:
    """Identical to research/registry.py make_id (the workflow checks both agree before uploading)."""
    key = json.dumps([thread, family, arm, code_sha, sorted(days), seed, sorted(phases or []), env or {}], sort_keys=True)
    return hashlib.sha1(key.encode()).hexdigest()[:16]


def _iso(day: int) -> str:
    return (dt.date(1970, 1, 1) + dt.timedelta(days=int(day))).isoformat()


def by_day(result: dict) -> dict:
    """{YYYY-MM-DD: $} over every out-of-sample day (0 where the policy sat out), from the hourly P&L the folds were
    scored on. A fold's test days are its test_days (newer runs) or its contiguous test span (checked against its
    hour count); anything else raises."""
    hourly = result.get('hourly_pnl') or []
    out, pos = {}, 0
    for f in result.get('folds', []):
        n = int(f['n_hours'])
        days = f.get('test_days') or list(range(int(f['test'][0]), int(f['test'][1]) + 1))
        if len(days) * 24 != n:
            raise ValueError(f'fold {f.get("fold")}: {len(days)} test days but {n} hours')
        seg = hourly[pos:pos + n]
        if len(seg) != n:
            raise ValueError(f'fold {f.get("fold")}: hourly series too short')
        pos += n
        for j, d in enumerate(days):
            out[_iso(d)] = round(float(sum(seg[24 * j:24 * (j + 1)])), 2)
    if pos != len(hourly):
        raise ValueError(f'{len(hourly) - pos} hours not in any fold')
    return out


def load_run(run_dir: str) -> dict:
    """{config name: {'arms': {arm: result}, 'gate': gate dict or None}} from a run's kept results."""
    groups = {}
    for f in sorted(glob.glob(os.path.join(run_dir, '**', '*.json'), recursive=True)):
        try:
            r = json.load(open(f))
        except Exception:
            continue
        if not isinstance(r, dict) or 'arm' not in r or 'oos' not in r:
            continue
        g = groups.setdefault(os.path.dirname(f), {'arms': {}, 'gate': None, 'heldout': None})
        g['arms'][r['arm']] = r
    out = {}
    for d, g in groups.items():
        for key, fn in (('gate', 'gate.json'), ('heldout', 'heldout.json')):
            gp = os.path.join(d, fn)
            if os.path.exists(gp):
                try:
                    g[key] = json.load(open(gp))
                except Exception:
                    pass
        base = g['arms'].get('base') or next(iter(g['arms'].values()))
        out[base.get('name') or os.path.basename(d) or 'base'] = g
    return out


def _pyes(r: dict):
    if r.get('pyes'):
        return tuple(r['pyes'])
    mc = (r.get('config') or {}).get('max_crossed', 0)
    return PYES_KEPT if mc >= 14 else PYES_DROPPED


def _verdict(gate: dict | None) -> str:
    if not gate:
        return 'no gate'
    if gate.get('passed'):
        return 'passed the gate'
    failed = [k for k, v in (gate.get('checks') or {}).items() if not v]
    return 'fails the gate: ' + ', '.join(failed)


def rows_for_run(run_dir: str, run_id: str, code_sha: str, run_url: str = '', prior: list | None = None,
                 flags: list | None = None) -> list:
    groups = load_run(run_dir)
    now = dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    rows, ids = [], {}
    for cfg, g in sorted(groups.items()):
        for arm in GATED:
            r = g['arms'].get(arm)
            if not r or r.get('kind', 'real15') != 'real15':
                continue
            bd = by_day(r)
            days = sorted(bd)
            name = cfg if arm == 'base' else f'{cfg}:{arm}'
            tid = make_id(THREAD, FAMILY, name, code_sha, days)
            ids[(cfg, arm)] = tid
            pk, pa = _pyes(r)
            ho1 = bool((g.get('heldout') or {}).get(arm))
            # Under HO-1 every config is a candidate against not trading ($0 every day: the family's question); in a
            # walk-forward run the base configuration is the control.
            role = 'neighbour' if arm != 'base' else ('control' if cfg in ('base', 'base_ctrl') and not ho1 else 'candidate')
            row = {'v': 1, 'trial_id': tid, 'ts': now, 'thread': THREAD, 'family': FAMILY, 'arm': name, 'role': role,
                   'code_sha': code_sha, 'env': {}, 'seed': None,
                   'code_epoch': 'all-pairs engine: Kalshi 15m candles read directly (no TS replay; REPLAY_VERSION n/a)',
                   # A learned entry + exit policy for the 15-minute crypto series: it replaces the entry decision and the exits.
                   'contract_type': 'price_prediction', 'modules': ['entry-gate', 'exits'], 'held_out': True,
                   'data': {'source': 'history', 'days': days, 'doge': False, 'benches': 'own', 'books': 'recorded', 'engine': 'allpairs'},
                   'by_day': bd, 'hours': r['oos'].get('hours'), 'fills': r['oos'].get('trades'),
                   'pyes_kept': pk, 'pyes_all': pa, 'flags': list(flags or []),
                   'verdict': _verdict(g['gate']) if arm == 'base' else f'{arm} arm: {r["oos"]["per_hour"]:+.2f} $/h',
                   'ref': run_url,
                   'raw': {'run': str(run_id), 'config': cfg, 'config_hash': r.get('config_hash'), 'arm': arm,
                           'per_hour': r['oos'].get('per_hour'), 'ci95': r['oos'].get('per_hour_ci95'),
                           'notes': (r.get('config') or {}).get('notes', '')[:300]}}
            if r.get('wide_spread_share') is not None:
                row['wide_spread_share'] = r['wide_spread_share']
            if (g.get('heldout') or {}).get(arm):
                row['heldout'] = g['heldout'][arm]     # HO-1 evidence (allpairs.ho1), on rows scored with --protocol ho1
                row['raw']['protocol'] = 'ho1'
            rows.append(row)
    # Pairing. Neighbours pair with their config's base arm; base-arm candidates with the run's own control, else
    # the registered control run's row (from earlier shards).
    own = next((ids[(c, 'base')] for c in ('base_ctrl', 'base') if (c, 'base') in ids), None)
    ext = None
    ctl_run, ctl_cfg = CONTROLS.get(str(run_id), DEFAULT_CONTROL)
    for p in prior or []:
        raw = p.get('raw') or {}
        if raw.get('run') == ctl_run and raw.get('config') == ctl_cfg and raw.get('arm') == 'base':
            ext = p
    # HO-1 runs: one no-trade control per held-out day set ($0 every day), the benchmark the HO-1 block is computed against
    # (folds won, worst fold, terciles: the arm's own $/h), so the registry's paired gain is the same quantity.
    zero = {}
    for row in [r for r in rows if r.get('heldout')]:
        days = row['data']['days']
        key = tuple(days)
        if key not in zero:
            zid = make_id(THREAD, FAMILY, 'no_trade', code_sha, days)
            zero[key] = zid
            rows.append({'v': 1, 'trial_id': zid, 'ts': now, 'thread': THREAD, 'family': FAMILY, 'arm': 'no_trade', 'role': 'control',
                         'code_sha': code_sha, 'env': {}, 'seed': None, 'code_epoch': row['code_epoch'],
                         'contract_type': 'price_prediction', 'modules': ['entry-gate', 'exits'], 'held_out': True,
                         'data': dict(row['data']), 'by_day': {d: 0.0 for d in days}, 'hours': 24 * len(days), 'fills': 0,
                         'flags': list(flags or []), 'verdict': 'benchmark: no trading ($0 every day)', 'ref': run_url,
                         'raw': {'run': str(run_id), 'config': 'no_trade', 'arm': 'base', 'protocol': 'ho1',
                                 'notes': 'HO-1 control of the all-pairs family: not trading'}})
        row['control'] = zero[key]
    for row in rows:
        raw = row['raw']
        if row.get('heldout') or raw.get('config') == 'no_trade':
            continue
        if raw['arm'] != 'base':
            row['control'] = ids.get((raw['config'], 'base'))
        elif row['role'] == 'candidate':
            if own:
                row['control'] = own
            elif ext and sorted(ext['by_day']) == row['data']['days']:
                row['control'] = ext['trial_id']
        if not row.get('control'):
            row.pop('control', None)
    return rows


def read_shards(d: str | None) -> list:
    out = []
    if not d or not os.path.isdir(d):
        return out
    for f in sorted(glob.glob(os.path.join(d, '**', '*.jsonl'), recursive=True)):
        for line in open(f):
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--results', required=True)
    ap.add_argument('--run-id', required=True)
    ap.add_argument('--code-sha', required=True)
    ap.add_argument('--run-url', default='')
    ap.add_argument('--prior', default='', help='directory of earlier all-pairs shards (to pair with a control run)')
    ap.add_argument('--flag', action='append', default=[], help='extra flag on every row (e.g. invalid-data)')
    ap.add_argument('--out', required=True)
    a = ap.parse_args(argv)
    rows = rows_for_run(a.results, a.run_id, a.code_sha, a.run_url, read_shards(a.prior), a.flag)
    with open(a.out, 'w') as fh:
        for r in rows:
            fh.write(json.dumps(r, sort_keys=True) + '\n')
    for r in rows:
        print(f'{r["arm"]:28s} {r["role"]:9s} days {len(r["by_day"]):3d}  ${sum(r["by_day"].values()):+9.2f}  control {r.get("control", "-")}')


if __name__ == '__main__':
    main()
