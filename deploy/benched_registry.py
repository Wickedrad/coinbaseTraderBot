#!/usr/bin/env python3
"""Trial registry rows for a benched-jobs run (meta plan thread's registry, research/registry.py on its branch).
Usage: benched_registry.py <results dir> <run id> <code sha> <registry.py> <out.jsonl>
One row per variant from research/out/benched-jobs/<variant>.json (byDay: $ after fees, DOGE already dropped from the
replayed days). Families and roles come from the arm's name: baseline is the control, skip*/placebo* are placebos, the
round's best arm is the candidate, the rest are neighbours. Aggregates only (public repository)."""
import glob, importlib.util, json, os, sys
from datetime import datetime, timezone

src, run, sha, reg_py, out = sys.argv[1:6]
spec = importlib.util.spec_from_file_location('registry', reg_py)
reg = importlib.util.module_from_spec(spec); spec.loader.exec_module(reg)

# The arm each family's question is about (candidate); everything else in the family is a neighbour.
CANDIDATES = {'tails15', 'tp_be_l3'}

def family(arm):
    if arm.startswith('tp_'):
        return 'take-profit-fv-confirm'
    return 'model-skill-tails'

def role(arm):
    if arm == 'baseline': return 'control'
    if arm.startswith('skip') or arm.startswith('placebo'): return 'placebo'
    return 'candidate' if arm in CANDIDATES else 'neighbour'

res = {}
for f in sorted(glob.glob(os.path.join(src, '*.json'))):
    r = json.load(open(f))
    if isinstance(r, dict) and r.get('byDay') is not None:
        res[r.get('name') or os.path.basename(f)[:-5]] = r
if 'baseline' not in res:
    sys.exit('no baseline result')
days = sorted({d for r in res.values() for d in r['byDay']})
try:
    env_of = json.loads(os.environ.get('TJ_VARIANT_ENVS', '{}'))
except Exception:
    env_of = {}

rows, ids = [], {}
fams = {family(a) for a in res}
for fam in sorted(fams):
    ids[fam] = reg.make_id('benched', fam, 'baseline', sha, days, None, None, {})
now = datetime.now(timezone.utc).isoformat(timespec='seconds')
for arm, r in sorted(res.items()):
    fams_for = sorted(fams) if arm == 'baseline' else [family(arm)]
    for fam in fams_for:
        env = env_of.get(arm, {})
        tid = ids[fam] if arm == 'baseline' else reg.make_id('benched', fam, arm, sha, days, None, None, env)
        row = {'v': 1, 'trial_id': tid, 'ts': now, 'thread': 'benched', 'family': fam, 'arm': arm, 'role': role(arm),
               'env': env, 'code_sha': sha,
               'data': {'source': 'history', 'days': days, 'doge': False, 'benches': 'own', 'books': 'synthetic', 'engine': 'replay',
                        'copy': 'gdrive:kalshi-bot-archive/simulated/benched-189d + models/benched-server-pin'},
               'by_day': {d: round(float(r['byDay'].get(d, 0.0)), 4) for d in days},
               'hours': 24.0 * len(days),
               'ref': f'https://github.com/Wickedrad/coinbaseTraderBot/actions/runs/{run}'}
        if arm != 'baseline':
            row['control'] = ids[fam]
        if isinstance(r.get('trades'), int):
            row['fills'] = r['trades']
        rows.append(row)

bad = 0
with open(out, 'w') as fh:
    for row in rows:
        err, fl = reg.validate(row)
        if err:
            bad += 1; print(f"invalid {row['arm']}: {err}", file=sys.stderr)
            continue
        if fl:
            row['flags'] = sorted(set(row.get('flags', []) + fl))
        fh.write(json.dumps(row) + '\n')
print(f"registry: {len(rows) - bad} row(s) for run {run} -> {out}" + (f", {bad} invalid" if bad else ''))
