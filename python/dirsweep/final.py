"""The FINAL of AMENDMENT-3.md section 6: the frozen rule, scored once on the whole ISO weeks nobody has read, with the 15-minute lockout per coin.

  freeze_data(...)     the rule the chooser picked, recomputed on the search days, with its always-on control, its lockout rate and the size of the FINAL
  window(fz)           first and last FINAL day, as day numbers of the sweep (day 0 = 2020-01-01) and as dates
  load_final(...)      one coin's minute grid: two warm-up days, the FINAL days and the day after them (read only so that the last rows have their 60 minutes ahead)
  score(...)           the numbers and the pass test of PREREG-3.md section 8 as AMENDMENT-3.md changes it
"""
import datetime as dt

import numpy as np

from dirsweep import floors as FL
from dirsweep import frames as FR
from dirsweep import grid as G
from dirsweep import infer as I
from dirsweep import nested as N
from dirsweep import replay as R
from dirsweep import topup as T

WARM_DAYS = 2
PASS = {'decided_min': 800, 'hit_min': 0.530, 'lb975_above': 0.500, 'coin_hit_min': 0.510}      # PREREG-3.md section 8, unchanged by AMENDMENT-3.md


def day_index(day: str) -> int:
    """Day number of an ISO date in the sweep's own count (2020-01-01 is day 0)."""
    return T.day_start_ms(day) // G.DAY - G.DAY0


def window(fz: dict) -> dict:
    first, last = fz['first_day'], fz['last_day']
    a, b = dt.date.fromisoformat(first), dt.date.fromisoformat(last)
    n = (b - a).days + 1
    if a.weekday() != 0 or b.weekday() != 6 or n % 7 or n // 7 != int(fz['weeks']):
        raise ValueError('the FINAL is whole ISO weeks (Monday to Sunday) and as many as the freeze says')
    return {'first_day': first, 'last_day': last, 'days': n, 'weeks': n // 7, 'lo': day_index(first), 'hi': day_index(last) + 1,
            'grid_first': (a - dt.timedelta(days=WARM_DAYS)).isoformat(), 'grid_last': (b + dt.timedelta(days=1)).isoformat()}


def window_days(first: str, last: str) -> dict:
    """Any run of recorded days (no weekday rule; Steven, Nov 21: only recorded days, nothing waits for the future). The same grid as the FINAL's: two warm-up
    days before, the day after the last day for the look-ahead filter."""
    a, b = dt.date.fromisoformat(first), dt.date.fromisoformat(last)
    if b < a:
        raise ValueError('last day before first day')
    n = (b - a).days + 1
    return {'first_day': first, 'last_day': last, 'days': n, 'weeks': round(n / 7, 2), 'lo': day_index(first), 'hi': day_index(last) + 1,
            'grid_first': (a - dt.timedelta(days=WARM_DAYS)).isoformat(), 'grid_last': (b + dt.timedelta(days=1)).isoformat()}


def load_final(csv: str, win: dict, plumbing: bool = False) -> dict:
    """The coin's grid from `grid_first` to the end of `grid_last`. In a real FINAL nothing is read from before the warm-up days or after the day that follows
    the last FINAL day; a plumbing run on search days may not reach 2026-11-01."""
    lo_ms = T.day_start_ms(win['grid_first'])
    end_ms = T.day_start_ms(win['grid_last']) + G.DAY
    if plumbing and end_ms > G.SEARCH_END:
        raise AssertionError('a plumbing run may not read a minute at or after the end of the search days')
    df = FR.read_bars(csv, lo_ms, end_ms)
    if int(df['ts'].max()) < end_ms - G.MIN:
        raise AssertionError(f"the minute file ends early: last minute {int(df['ts'].max())}, needed {end_ms - G.MIN}")
    m = FR.grid(df, end_ms=end_ms)
    if m['t0'] != lo_ms or m['n'] != (end_ms - lo_ms) // G.MIN:
        raise AssertionError('the grid does not cover the warm-up days, the FINAL days and the day after')
    return m


def _per_day(replayers: dict, rid: int, lo: int, hi: int) -> dict:
    per = {c: rp.replay(rid, lo, hi) for c, rp in replayers.items()}
    return {'per': per, 'decided': sum(o['decided'] for o in per.values()), 'right': sum(o['right'] for o in per.values()),
            'calls': sum(o['calls'] for o in per.values())}


def _hit(n: np.ndarray, r: np.ndarray) -> dict:
    if not n.sum():
        return {'N': 0, 'right': 0, 'hit': None, 'se': None, 'lb975': None}
    return I.pooled_hit(n, r)


def score_rule(replayers: dict, rid: int, lo: int, hi: int) -> dict:
    t = _per_day(replayers, rid, lo, hi)
    pooled = _hit(t['decided'], t['right'])
    by_coin = {c: _hit(o['decided'], o['right']) for c, o in t['per'].items()}
    weeks = [_hit(t['decided'][a:a + 7], t['right'][a:a + 7])['hit'] for a in range(0, hi - lo, 7)]
    return {'rid': int(rid), 'rule': G.describe(int(rid)), 'decided': int(t['decided'].sum()), 'calls': int(t['calls'].sum()), 'hit': pooled['hit'], 'se': pooled['se'],
            'lb975': pooled['lb975'], 'by_coin': {c: {'N': h['N'], 'hit': h['hit']} for c, h in by_coin.items()}, 'by_week': weeks,
            'decided_per_day': float(t['decided'].sum() / (hi - lo))}


def verdict(res: dict) -> dict:
    """The pass test: at least 800 decided calls, hit >= 53.0%, day-cluster 97.5% lower bound > 50%, BTC and ETH each >= 51.0%."""
    c = {'decided': res['decided'] >= PASS['decided_min'],
         'hit': res['hit'] is not None and res['hit'] >= PASS['hit_min'],
         'lb975': res['lb975'] is not None and res['lb975'] > PASS['lb975_above'],
         'coins': bool(res['by_coin']) and all(v['hit'] is not None and v['hit'] >= PASS['coin_hit_min'] for v in res['by_coin'].values())}
    c['pass'] = all(c.values())
    return c


def score(grids: dict, fz: dict, win: dict) -> dict:
    """The rule and its control on the FINAL days. The control is reported, not judged."""
    replayers = {c: R.Replayer(m, G.STEP[c], nd=win['hi']) for c, m in grids.items()}
    rule = score_rule(replayers, fz['rule']['rid'], win['lo'], win['hi'])
    out = {'first_day': win['first_day'], 'last_day': win['last_day'], 'weeks': win['weeks'], 'rule': rule, 'checks': verdict(rule),
           'expected_decided': fz.get('expected_decided'), 'gap_minutes': {}}
    for c, m in grids.items():
        off = m['t0'] // G.DAY - G.DAY0
        out['gap_minutes'][c] = int(np.asarray(m['gap'])[(win['lo'] - off) * 1440:(win['hi'] - off) * 1440].sum())
    if fz.get('control'):
        out['control'] = score_rule(replayers, fz['control']['rid'], win['lo'], win['hi'])
    return out


def freeze_data(floor: int, ndec, cf, blocks: list, nact: np.ndarray, bench_cells, coins: dict, replayers: dict, periods: dict) -> dict:
    """The chooser's rule at `floor` and the always-on rule that is the E5 benchmark of that floor, both from all 14 blocks of the search days, with their
    numbers (sweep and lockout) and the size of the FINAL."""
    fr = N.freeze(ndec, cf, blocks, nact, coins=coins, min_per_day=floor)
    if fr.get('rid') is None:
        raise ValueError(f'no eligible rule at floor {floor}')
    st = I.window_stats(ndec, cf, 0, ndec.shape[1])
    sc = N.rule_scores(st, floor)
    brid, _ = N.pick(sc, nact, N.bench_allowed(ndec.shape[0], bench_cells))
    out = {'floor': int(floor), 'rule': {'rid': int(fr['rid']), 'describe': fr['rule']}, 'in_sample': fr['all'], 'calls_per_day': fr['calls_per_day'],
           'by_coin': fr.get('by_coin'), 'lockout': FL.frozen_replay(replayers, fr['rid'], blocks, periods)}
    lk = out['lockout']
    out['weeks'] = lk['weeks']
    out['expected_decided'] = None if not lk['weeks'] else float(lk['decided_per_day_C'] * 7 * lk['weeks'])
    if brid is not None:
        n, r = N.side_counts(ndec, cf, brid, 0, ndec.shape[1])
        out['control'] = {'rid': int(brid), 'describe': G.describe(int(brid)), 'in_sample': I.pooled_hit(n, r), 'calls_per_day': float(n.sum() / ndec.shape[1]),
                          'lockout': FL.frozen_replay(replayers, brid, blocks, periods)}
    return out


STRICT_FILES = ('research/heat_direction/PREREG.md', 'research/heat_direction/AMENDMENT-1.md', 'research/heat_direction/PREREG-3.md',
                'research/heat_direction/AMENDMENT-3.md', 'research/heat_direction/dsfloor/choose.json')
WORKFLOW = '.github/workflows/heat-direction.yml'
WORKFLOW_JOBS = ('dsfinal', 'dsstamp')                                                   # the jobs that carry the guards of the FINAL
STRICT_GLOBS = ('python/dirsweep/*.py', 'python/dirsweep/tests/*.py')
ADVISORY_FILES = ('python/heatloop/events.py', 'python/oracle/heat_live.py')          # the data path the sweep also uses; a change is reported, not fatal


def _sha(path: str) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def hashes(root: str) -> tuple:
    """(strict, advisory): sha256 of every file the FINAL is tied to, keyed by path relative to the repository root."""
    import glob
    import os
    strict = {p: _sha(os.path.join(root, p)) for p in STRICT_FILES}
    for g in STRICT_GLOBS:
        for p in sorted(glob.glob(os.path.join(root, g))):
            if '__pycache__' not in p:
                strict[os.path.relpath(p, root)] = _sha(p)
    for job in WORKFLOW_JOBS:
        strict[f'{WORKFLOW}#{job}'] = job_block_sha(os.path.join(root, WORKFLOW), job)
    adv = {p: _sha(os.path.join(root, p)) for p in ADVISORY_FILES}
    return strict, adv


def job_block_sha(path: str, job: str) -> str:
    """sha256 of the text of one job of the workflow file: from its `  <job>:` line to the next job (or the end of the file)."""
    import hashlib
    import re
    lines = open(path).read().split('\n')
    start = next((i for i, ln in enumerate(lines) if ln == f'  {job}:'), None)
    if start is None:
        return 'missing'
    end = next((i for i in range(start + 1, len(lines)) if re.match(r'^  [A-Za-z0-9_-]+:\s*$', lines[i])), len(lines))
    return hashlib.sha256('\n'.join(lines[start:end]).rstrip('\n').encode()).hexdigest()


def assemble(data: dict, choose: dict, first_day: str, root: str, written_utc: str) -> dict:
    """FREEZE-DS.json: the rule of AMENDMENT-3.md section 5, the control, the size and dates of the FINAL, and the hashes that tie the FINAL to this code."""
    cand = choose['candidate']
    if cand is None:
        raise ValueError('`choose` found no qualifying floor: there is nothing to freeze')
    if cand['floor'] != data['floor'] or cand['rid'] != data['rule']['rid']:
        raise ValueError('the recomputed rule is not the one `choose` named')
    weeks = data['weeks']
    if not weeks:
        raise ValueError('the chosen rule needs more than eight weeks')
    a = dt.date.fromisoformat(first_day)
    if a.weekday() != 0:
        raise ValueError('the FINAL starts on a Monday')
    last = a + dt.timedelta(days=7 * weeks - 1)
    strict, adv = hashes(root)
    return {'version': 1, 'written_utc': written_utc, 'floor': data['floor'], 'rule': data['rule'], 'control': data.get('control') and
            {'rid': data['control']['rid'], 'describe': data['control']['describe']}, 'weeks': weeks, 'first_day': first_day, 'last_day': last.isoformat(),
            'freeze_deadline_utc': (dt.datetime.fromisoformat(first_day) - dt.timedelta(days=2)).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'expected_decided': data['expected_decided'], 'in_sample': data['in_sample'], 'lockout': data['lockout'],
            'frontier': {'run_id': 44637991215, 'commit': 'a3304197df7062ced44ae6426fc615cf1121f8f4', 'excess_per_day': cand['excess_per_day'],
                         'qualifying_floors': [r['floor'] for r in choose['floors'] if r['qualifies']]},
            'scoring': {'horizon_min': 15, 'lockout_min': 15, 'flat_steps': G.FLAT, 'step': G.STEP, 'warm_days': WARM_DAYS, 'one_look': True},
            'pass': PASS, 'hashes': strict, 'advisory_hashes': adv}


def verify(fz: dict, root: str) -> dict:
    """Every strict hash must match the checked-out files (and no strict file may be missing or new); advisory differences are listed."""
    import json
    import os
    strict, adv = hashes(root)
    want = fz['hashes']
    bad = sorted(p for p in set(want) | set(strict) if want.get(p) != strict.get(p))
    with open(os.path.join(root, 'research/heat_direction/dsfloor/choose.json')) as f:
        cand = json.load(f)['candidate']
    for field, a, b in (('floor', fz.get('floor'), cand and cand['floor']), ('rule.rid', fz['rule']['rid'], cand and cand['rid']), ('weeks', fz.get('weeks'), cand and cand['weeks'])):
        if a != b:
            bad.append(f'field {field}: freeze file {a}, choose.json {b}')
    try:
        window(fz)
    except ValueError as e:
        bad.append(f'window: {e}')
    return {'ok': not bad, 'mismatch': bad, 'advisory_changed': sorted(p for p in adv if adv[p] != fz['advisory_hashes'].get(p))}


def same_as_original(csv: str, win: dict) -> dict:
    """Plumbing only (search days): the vendored loader against `heatloop.events.read_bars` + `oracle.heat_live.grid`, which the sweep itself read."""
    from heatloop import events
    from oracle import heat_live
    lo_ms = T.day_start_ms(win['grid_first'])
    end_ms = T.day_start_ms(win['grid_last']) + G.DAY
    if end_ms > G.SEARCH_END:
        raise AssertionError('a plumbing run may not read a minute at or after the end of the search days')
    a = heat_live.grid(events.read_bars(csv, lo_ms, end_ms), end_ms=end_ms)
    b = FR.grid(FR.read_bars(csv, lo_ms, end_ms), end_ms=end_ms)
    same = {k: bool(np.array_equal(np.asarray(a[k]), np.asarray(b[k]))) for k in ('o', 'h', 'l', 'c', 'v', 'tb', 'gap')}
    same['t0_n'] = (a['t0'], a['n']) == (b['t0'], b['n'])
    same['all'] = all(same.values())
    return same
