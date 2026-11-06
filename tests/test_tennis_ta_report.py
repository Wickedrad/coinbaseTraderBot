#!/usr/bin/env python3
"""research/tennis_ta_report.py end to end on synthetic shard sets (contract C4): two shards x two sub-slices, measuring
sticks, F1 / F2 / coin arms, 'nostart', 'old', 'embargo' and 'hold' rows beside the pool's (C9), and a family B export;
an H-DEV choice run (pool disc), an H0 stress run (pool old) and an H-HOLD scoring run of a frozen list (pool hold, stage
hold, C10); the registry v1 rows (C7 / C11) are checked with the project's research/registry.py (make_id, validate,
ho1_fill, ho1_pass).

Run: python3 -m pytest -q tests/test_tennis_ta_report.py, or python3 tests/test_tennis_ta_report.py (no pytest needed).
research/registry.py is another thread's code: $TENNIS_TA_REGISTRY_PY when set, else research/registry.py in this tree,
else origin/main's, else the registry thread's branch (claude/project-thread-79ntof), as the workflow fetches it.
Temp files go under $TENNIS_TA_TEST_TMP when set (else the system temp dir)."""
import gzip
import importlib.util
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..'))
SCRIPT = os.path.join(REPO, 'research', 'tennis_ta_report.py')
sys.path.insert(0, os.path.join(REPO, 'research'))
import tennis_ta_report as R  # noqa: E402

DAY = 86_400_000
HOUR = 3_600_000
BOOT = 199
SHA = 'c0ffee' * 6 + 'beef'  # 40 hex: the --sha the rows carry
ERA = {'historyFrom': '2025-06-18T00:00:00.000Z', 'startEraFrom': '2026-04-27T05:00:00.000Z', 'devTo': '2026-07-31T00:00:00.000Z',
       'holdFrom': '2026-08-01T00:00:00.000Z', 'cutoff': '2026-11-05T02:00:00.000Z'}
H_HOLD = ('2026-08-01', '2026-11-04')
PROD = {'TENNIS_CONF_MOMENTUM_CENTS': 0.01, 'TENNIS_CONF_FLOW': 0.2, 'TENNIS_CONF_OPPONENT_CENTS': 0.01, 'TENNIS_CONF_WINDOW_SEC': 60,
        'TENNIS_TRAIL_RATCHET': False}
BREACH = dict(PROD, TENNIS_CONF_MOMENTUM_CENTS=0.02)
NULL = dict(PROD, TENNIS_CONF_MOMENTUM_CENTS=0.005, TENNIS_CONF_FLOW=0.05, TENNIS_CONF_OPPONENT_CENTS=0.005, TENNIS_CONF_WINDOW_SEC=120)
COLS = ['m', 'k', 't', 'leg', 'px', 'n', 'ph', 'sig', 'x', 'hold', 'pnl', 'br']
B_POS = 'B|RSI14L|1m|exitExt|follow|all|tp30sl30'
B_POS_CTX = 'B|RSI14L|1m|exitExt|follow|p15-35:mid:trend|tp30sl30'
B_NULL = 'B|MACD|5m|zero|fade|all|t2m'
B_BREACH = 'B|ROC10L|1m|zero|follow|all|t10m'


def tmpdir():
    base = os.environ.get('TENNIS_TA_TEST_TMP')
    if base:
        os.makedirs(base, exist_ok=True)
    return tempfile.mkdtemp(prefix='tennis-ta-report-', dir=base)


def ms(iso):
    return int(datetime.fromisoformat(iso + '+00:00').timestamp() * 1000)


def day_of(t):
    return datetime.fromtimestamp(t / 1000, timezone.utc).strftime('%Y-%m-%d')


_REG = {}


def registry_path():
    """The project's research/registry.py (see the module docstring for the search order)."""
    if 'path' in _REG:
        return _REG['path']
    p = os.environ.get('TENNIS_TA_REGISTRY_PY')
    if not p and os.path.exists(os.path.join(REPO, 'research', 'registry.py')):
        p = os.path.join(REPO, 'research', 'registry.py')
    if not p:
        for ref in ('origin/main', 'origin/claude/project-thread-79ntof'):
            r = subprocess.run(['git', '-C', REPO, 'show', f'{ref}:research/registry.py'], capture_output=True, text=True)
            if r.returncode == 0 and 'def make_id' in r.stdout:
                p = os.path.join(tmpdir(), 'registry.py')
                with open(p, 'w') as fh:
                    fh.write(r.stdout)
                break
    if not p or not os.path.exists(p):
        raise RuntimeError('research/registry.py not found (set TENNIS_TA_REGISTRY_PY to the registry thread\'s file)')
    _REG['path'] = p
    return p


def replay_version_in_code():
    """REPLAY_VERSION as research/history/historyReplay.ts (the replay the sweep builds history days with) sets it."""
    import re
    with open(os.path.join(REPO, 'research', 'history', 'historyReplay.ts')) as fh:
        found = re.findall(r'^export const REPLAY_VERSION = (\d+);', fh.read(), re.M)
    assert len(found) == 1, found
    return int(found[0])


def registry_module():
    if 'mod' not in _REG:
        spec = importlib.util.spec_from_file_location('registry_under_test', registry_path())
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _REG['mod'] = mod
    return _REG['mod']


def iso_ms(iso):
    return int(datetime.fromisoformat(iso.replace('Z', '+00:00')).timestamp() * 1000)


HISTORY_FROM, START_ERA, DEV_TO, HOLD_FROM, CUTOFF = (iso_ms(ERA[k]) for k in ('historyFrom', 'startEraFrom', 'devTo', 'holdFrom', 'cutoff'))


def registry_fold(day):
    """The HO-1 fold of a UTC day as research/registry.py ho1_fill cuts H-HOLD (span = its days, edge i = first day +
    round(i * span / 6) days, the last fold to H-HOLD's last day); None outside H-HOLD. Written from the registry's text,
    independently of the report."""
    from datetime import date, timedelta
    d0, d1 = date.fromisoformat(H_HOLD[0]), date.fromisoformat(H_HOLD[1])
    span = (d1 - d0).days + 1
    edges = [d0 + timedelta(days=round(i * span / 6)) for i in range(7)]
    for i in range(6):
        if edges[i].isoformat() <= day < edges[i + 1].isoformat():
            return i + 1
    return 6 if day == d1.isoformat() else None


def all_hold_days():
    from datetime import date, timedelta
    d0, d1 = date.fromisoformat(H_HOLD[0]), date.fromisoformat(H_HOLD[1])
    return [(d0 + timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)]


def units_table(t0_iso='2026-04-27T05:00:00', n=28):
    """n Monday 05:00 UTC weeks from t0 (default: the start era's first week to the week of the cutoff, Nov 2). The 6th
    old-era week carries a legacy `sealed` flag, which C9 ignores (it is swept as pool old like the rest)."""
    t0 = ms(t0_iso)
    out = []
    for i in range(n):
        s = t0 + i * 7 * DAY
        out.append({'id': f'W-{day_of(s)}', 'start': s, 'end': s + 7 * DAY, 'startDay': day_of(s), 'sealed': i == 5 and s < START_ERA})
    return out


def run_units(table, pool):
    """The units a run of the pool sweeps (C9, by the fixture's own rule): disc = start-era weeks starting before DEV_TO,
    hold = weeks ending after HOLD_FROM and starting before the cutoff, old = unsealed weeks before the start era."""
    if pool == 'disc':
        return [u for u in table if START_ERA <= u['start'] < DEV_TO]
    if pool == 'hold':
        return [u for u in table if u['end'] > HOLD_FROM and u['start'] < CUTOFF]
    return [u for u in table if u['start'] < START_ERA and u['end'] > HISTORY_FROM]


def c9_pool(start, close, published, unit_start):
    """A match's pool as the sweep labels it (C9, in this order)."""
    if start < HISTORY_FROM or start >= CUTOFF or close >= CUTOFF:
        return 'out'
    if unit_start < START_ERA:
        return 'old'
    if not published:
        return 'nostart'
    if close < DEV_TO:
        return 'disc'
    if start < HOLD_FROM:
        return 'embargo'
    return 'hold'


def episode(m, start, ph, px, pnl, br=0, k=0):
    return [m, k, start + 600_000, 'underdog', px, 10, ph, 3, 'tp', 300, round(pnl, 6), br]


def pool_label(pool, ev, start, close, published, unit_start):
    """A row's pool: the C9 label; in a disc run a few disc rows are labelled 'old' too (no disc run has them, the filter
    must still drop them)."""
    p = c9_pool(start, close, published, unit_start)
    return 'old' if pool == 'disc' and p == 'disc' and ev % 29 == 11 else p


# A hold run's frozen list (C10): the production-default F1 control, two candidates with their coin placebo and F2
# neighbour, and a measuring stick. WIN beats production by 0.5 $ a match (passes HO-1), LOSE trails it.
WIN = dict(PROD, TENNIS_FAV_MIN=0.65)
LOSE = dict(PROD, TENNIS_TP_PCT=0.2)
CTRL = 'A|s1|m0.01|f0.2|o0.01|w60'
HOLD_RUNS = [
    (CTRL + '|F1', PROD, 'F1', None, False, 0.0),
    (CTRL + '|F2', PROD, 'F2', None, False, -0.02),
    (CTRL + '|coin', PROD, 'F1', 'coin', False, -0.05),
    ('A|s2|fm0.65|F1', WIN, 'F1', None, False, 0.5),
    ('A|s2|fm0.65|F2', WIN, 'F2', None, False, 0.4),
    ('A|s2|fm0.65|coin', WIN, 'F1', 'coin', False, -0.05),
    ('A|s2|tp0.2|F1', LOSE, 'F1', None, False, -0.3),
    ('A|s2|tp0.2|F2', LOSE, 'F2', None, False, -0.35),
    ('A|s2|tp0.2|coin', LOSE, 'F1', 'coin', False, -0.05),
    ('A|s2|prod|settlehold|F1', dict(PROD, TENNIS_END_LOSER_CUT=False), 'F1', None, True, 2.0),
]
STAGE_RUNS = [
    ('A|s1|m0.01|f0.2|o0.01|w60|F1', PROD, 'F1', None, False, 0.5),
    ('A|s1|m0.01|f0.2|o0.01|w60|F2', PROD, 'F2', None, False, 0.4),
    ('A|s1|m0.01|f0.2|o0.01|w60|coin', PROD, 'F1', 'coin', False, -0.05),
    ('A|s1|m0.02|f0.2|o0.01|w60|F1', BREACH, 'F1', None, False, 0.5),
    ('A|s1|m0.02|f0.2|o0.01|w60|F2', BREACH, 'F2', None, False, 0.4),
    ('A|s1|m0.02|f0.2|o0.01|w60|coin', BREACH, 'F1', 'coin', False, -0.05),
    ('A|s1|m0.005|f0.05|o0.005|w120|F1', NULL, 'F1', None, False, 0.0),
    ('A|s1|m0.005|f0.05|o0.005|w120|F2', NULL, 'F2', None, False, -0.02),
    ('A|s1|m0.005|f0.05|o0.005|w120|coin', NULL, 'F1', 'coin', False, 0.0),
    ('A|s1|prod|settlehold|F1', dict(PROD, TENNIS_END_LOSER_CUT=False), 'F1', None, True, 2.0),
    ('A|s1|prod|nopacer|F1', dict(PROD, HARNESS_PACER='off'), 'F1', None, True, 0.3),
]
LATE = ms('2026-11-05T00:30:00')  # a hold-pool match on the UTC day after H-HOLD, before the cutoff
DISC_UNITS = 14  # the start-era weeks Apr 27 to Jul 27 (the last one straddles DEV_TO and HOLD_FROM)


def build(root, families_b=True, seed=7, pool='disc', stage='1', t0='2026-04-27T05:00:00', b_day_placebo=False, n_units=None,
          replay_meta=True, meta_extra=None, runs_def=None):
    """Write units.json and the shard directory; returns (units path, shard dir, plan path). pool 'old' (stratum H0)
    takes units before the start era (t0 then must be one) and stage 2; pool 'hold' stage 'hold' and the frozen list
    HOLD_RUNS. The plan's poolSpans are the swept units whole (the report cuts them to the pool's window)."""
    rng = np.random.default_rng(seed)
    table = units_table(t0, n_units or (28 if iso_ms(t0 + 'Z') >= START_ERA else 17))
    upath = os.path.join(root, 'units.json')
    with open(upath, 'w') as fh:
        json.dump(table, fh)
    pool_units = run_units(table, pool)
    cuts = np.array_split(np.arange(len(pool_units)), 4)
    plan_slices = {(k, j): [pool_units[i] for i in cuts[2 * k + j]] for k in (0, 1) for j in (0, 1)}
    sdir = os.path.join(root, 'shards')
    os.makedirs(sdir, exist_ok=True)
    spans_all = [{'unit': u['id'], 'start': u['start'], 'end': u['end'], 'intervals': [[u['start'], u['end']]], 'hours': 168.0} for u in pool_units]
    if runs_def is None:
        runs_def = HOLD_RUNS if pool == 'hold' else STAGE_RUNS
    phases = ['pre', 'e20', 'p1', 'p2', 'p3']
    ev = 0
    plan = {'stage': stage, 'pool': pool, 'requestSha': 'req-sha', 'unitsSha': 'units-sha', 'simVersion': 'tennis-ta-sim/3', 'familyB': families_b,
            'plan': [{'k': 0}, {'k': 1}], 'subPlans': [[None, None], [None, None]], 'expected': [], 'units': [u['id'] for u in pool_units],
            'poolSpans': spans_all, 'era': ERA}
    breach_done = False
    for (k, j), us in sorted(plan_slices.items()):
        matches = []
        for u in us:
            starts = [u['start'] + d * DAY + (2 + 5 * q) * HOUR for d in range(7) for q in range(3)]
            if u['start'] < LATE < u['end']:
                starts.append(LATE)
            for start in sorted(starts):
                published = iso_ms(t0 + 'Z') >= START_ERA and ev % 17 != 3
                close = start + (int(1.25 * HOUR) if start == LATE else int(2.5 * HOUR))
                lab = pool_label(pool, ev, start, close, published, u['start'])
                fold = registry_fold(day_of(start)) if lab == 'hold' else None
                matches.append({'event': f'KXEV-{ev}', 'series': 'KXATPMATCH' if ev % 2 == 0 else 'KXWTAMATCH', 'day': day_of(start),
                                'start': start, 'startPublished': published, 'close': close,
                                'tickers': [f'KXEV-{ev}-A', f'KXEV-{ev}-B'], 'trades': 0 if ev % 41 == 5 else 40,
                                'unresolved': False, 'resultA': 1, 'pool': lab, 'unit': u['id'], 'fold': fold})
                ev += 1
        runs = []
        for rid, ov, fill, plc, stick, edge in runs_def:
            pnl, eps = [], []
            for mi, m in enumerate(matches):
                if m['trades'] == 0:
                    pnl.append(0.0)
                    continue
                v = edge + rng.normal(0, 0.2 if edge else 0.5)
                ph = phases[mi % 5]
                px = 0.8 if mi % 2 == 0 else 0.2
                br = 0
                if rid == 'A|s1|m0.02|f0.2|o0.01|w60|F1' and not breach_done and ph == 'p3':
                    br, breach_done = 1, True
                eps.append(episode(mi, m['start'], ph, px, v, br, k=mi % 2 if rid.endswith('|F2') else 0))
                if rid == 'A|s1|m0.02|f0.2|o0.01|w60|F2' and mi % 7 == 0:  # a second position on the same market (one market)
                    eps.append(episode(mi, m['start'] + 60_000, ph, px, 0.0, 0, k=mi % 2))
                pnl.append(round(v, 6))
            run = {'id': rid, 'overrides': ov, 'fill': fill, 'stratum': 'H', 'days': [], 'pnl': pnl, 'episodes': eps}
            if plc:
                run['placebo'] = plc
            if stick:
                run['stick'] = True
            runs.append(run)
        last = us[-1]
        frm, to = us[0]['startDay'], day_of(R.day_ms(day_of(last['end'])) + DAY)
        meta = {'simVersion': 'tennis-ta-sim/3', 'stage': stage, 'pool': pool, 'run': '4242', 'k': k, 'j': j, 'shards': 2, 'subShards': 2,
                'from': frm, 'to': to, 'units': [u['id'] for u in us], 'dataVersion': 'atp:abc wta:def',
                'coverage': {'span': [frm, to], 'series': {s: {'first': day_of(table[0]['start'] - 2 * DAY), 'last': day_of(table[-1]['end'] + DAY),
                                                               'files': 120, 'spanDays': 30, 'withFile': 30, 'withTrades': 30, 'missing': []}
                                                           for s in ('KXATPMATCH', 'KXWTAMATCH')},
                             'matches': len(matches), 'noPublishedStart': sum(1 for m in matches if not m['startPublished']), 'noPublishedStartEvents': []},
                'requestSha': 'req-sha', 'families': ['A', 'B'] if families_b else ['A'], 'sha': SHA, 'unitsSha': 'units-sha',
                'stratum': 'H', 'stratumLabel': 'H0' if pool == 'old' else 'H', 'era': ERA, 'evidence': 'history, synthetic depth',
                'episodeCols': COLS, 'sticks': [r[0] for r in runs_def if r[4]],
                'poolSpans': [s for s in spans_all if s['unit'] in {u['id'] for u in us}]}
        if replay_meta:
            meta['replayVersion'] = replay_version_in_code()
        meta.update(meta_extra or {})
        out = {'meta': meta, 'matchList': matches, 'runs': runs}
        if families_b:
            scored = [m for m in matches if m['pool'] == pool and (pool != 'hold' or H_HOLD[0] <= m['day'] <= H_HOLD[1])]
            out['familyB'] = family_b(us, scored, rng, first=(k, j) == (0, 0), day_placebo=b_day_placebo)
        name = f'a-s{stage}-{k}-{j}.json.gz'
        with gzip.open(os.path.join(sdir, name), 'wt') as fh:
            json.dump(out, fh)
        plan['expected'].append(name)
        plan['subPlans'][k][j] = {'k': j, 'from': frm, 'to': to, 'units': [u['id'] for u in us]}
    ppath = os.path.join(root, 'plan.json')
    with open(ppath, 'w') as fh:
        json.dump(plan, fh)
    return upath, sdir, ppath


def family_b(us, matches, rng, first, day_placebo=False):
    """A family B export over the slice; its day sums fall on the days of the run pool's matches only (`matches`)."""
    def cell(cid, group, edge, sd, per_unit, placebo_edge, breaches=0):
        c = {'id': cid, 'group': group, 'n': 0, 'sum': 0.0, 'sumSq': 0.0, 'sum3': 0.0, 'sum4': 0.0, 'breaches': breaches, 'gross': 0.0,
             'fees': 0.0, 'stressSum': 0.0, 'units': {}, 'days': {}}
        for u in us:
            days = sorted({m['day'] for m in matches if m['unit'] == u['id']})
            if not days:
                continue
            xs = edge + rng.normal(0, sd, per_unit)
            ps = placebo_edge + rng.normal(0, sd, per_unit)
            c['units'][u['id']] = [per_unit, float(xs.sum()), per_unit, float(ps.sum())]
            for q, x in enumerate(xs):
                d = days[q % len(days)]
                cur = c['days'].setdefault(d, [0, 0.0, 0, 0.0] if day_placebo else [0, 0.0])
                cur[0] += 1
                cur[1] += float(x)
                if day_placebo:  # [entries, net, placebo entries, placebo net]: per-day placebo sums
                    cur[2] += 1
                    cur[3] += float(ps[q])
            c['n'] += per_unit
            c['sum'] += float(xs.sum())
            c['sumSq'] += float((xs ** 2).sum())
            c['sum3'] += float((xs ** 3).sum())
            c['sum4'] += float((xs ** 4).sum())
            c['gross'] += float(xs.sum()) + 0.1 * per_unit
            c['fees'] += 0.1 * per_unit
            c['stressSum'] += float(xs.sum()) - 0.05 * per_unit
        if day_placebo:  # the current export also counts the markets entered (FamilyBCell.markets / placeboMarkets)
            c['markets'] = c['n'] // 2
            c['placeboMarkets'] = c['n'] // 3
        return c
    g = 'B|RSI14L|1m|exitExt|follow'
    cells = [cell(B_POS, g, 0.3, 0.2, 10, -0.1), cell(B_POS_CTX, g, 0.3, 0.2, 3, -0.1), cell(B_NULL, 'B|MACD|5m|zero|fade', 0.0, 0.5, 6, 0.0),
             cell(B_BREACH, 'B|ROC10L|1m|zero|follow', 0.3, 0.2, 10, -0.1, breaches=1 if first else 0)]
    return {'stratum': 'H', 'designSize': 40, 'diagnostics': {'matches': len(matches), 'noTape': 1, 'entries': sum(c['n'] for c in cells)}, 'cells': cells}


def run_report(units, shards, out, *extra, pool='disc', registry=True, boot=BOOT):
    reg = ['--registry-py', registry_path(), '--sha', SHA] if registry else []
    return subprocess.run([sys.executable, SCRIPT, '--shards', shards, '--pool', pool, '--run', '4242', '--out', out, '--units', units,
                           '--boot', str(boot), *reg, *extra], capture_output=True, text=True, timeout=600)


def strict_json(text):
    def bad(x):
        raise ValueError(f'non-JSON constant {x}')
    return json.loads(text, parse_constant=bad)


ROWS_FILE = 'registry-v1-4242.jsonl'


def read_registry(out):
    with open(os.path.join(out, ROWS_FILE)) as fh:
        return [strict_json(line) for line in fh if line.strip()]


def read_matches(shards):
    ml = []
    for f in sorted(os.listdir(shards)):
        with gzip.open(os.path.join(shards, f), 'rt') as fh:
            ml += json.load(fh)['matchList']
    return ml


_E2E = {}


def e2e():
    """One full run shared by the end-to-end checks."""
    if not _E2E:
        root = tmpdir()
        units, shards, plan = build(root)
        out = os.path.join(root, 'out')
        r = run_report(units, shards, out, '--plan', plan)
        assert r.returncode == 0, r.stderr[-3000:] + r.stdout[-2000:]
        with gzip.open(os.path.join(out, 'cells.json.gz'), 'rt') as fh:
            cells = strict_json(fh.read())
        with open(os.path.join(out, 'summary.json')) as fh:
            summary = strict_json(fh.read())
        with open(os.path.join(out, 'report.md')) as fh:
            report = fh.read()
        _E2E.update(root=root, out=out, cells=cells, summary=summary, report=report, registry=read_registry(out), shards=shards,
                    matches=read_matches(shards))
    return _E2E


def test_end_to_end_outputs_are_valid_json_and_p_is_never_zero():
    e = e2e()
    floor = 1 / (BOOT + 1)
    assert e['cells'], 'no cells'
    assert min(c['p'] for c in e['cells']) >= floor - 1e-15
    assert all(c.get('p_placebo') is None or c['p_placebo'] >= floor - 1e-15 for c in e['cells'])
    assert all(r['raw']['p_boot'] >= floor - 1e-15 for r in e['registry'] if r['raw'].get('p_boot') is not None)
    assert e['summary']['spa']['p_consistent'] >= floor - 1e-15
    with gzip.open(os.path.join(e['out'], 'cells-b.json.gz'), 'rt') as fh:
        strict_json(fh.read())
    with open(os.path.join(e['out'], 'losers.json')) as fh:
        strict_json(fh.read())


PROD_F1 = 'A|s1|m0.01|f0.2|o0.01|w60|F1'


def test_registry_rows_validate_with_the_registry_module():
    e = e2e()
    reg = registry_module()
    rows = e['registry']
    assert rows
    for r in rows:
        err, _ = reg.validate(r)
        assert err == [], (r['arm'], err)
    # The registry's own command line, as the workflow runs it (python3 -I registry.py validate FILE).
    v = subprocess.run([sys.executable, '-I', registry_path(), 'validate', os.path.join(e['out'], ROWS_FILE)], capture_output=True, text=True, timeout=120)
    assert v.returncode == 0 and 'INVALID' not in v.stdout, v.stdout[-2000:]
    # The per-cell interim file and the trials.jsonl ledger are gone.
    assert not os.path.exists(os.path.join(e['out'], 'registry-tennis-ta-4242.jsonl.gz'))
    assert not any('trials' in f for f in os.listdir(e['out']))


def test_registry_ids_are_make_id_consistent_and_unique():
    reg = registry_module()
    rows = e2e()['registry']
    ids = [r['trial_id'] for r in rows]
    assert len(ids) == len(set(ids))
    for r in rows:
        assert r['trial_id'] == reg.make_id(r['thread'], r['family'], r['arm'], r['code_sha'], r['data']['days'], r['seed'], [], r['env']), r['arm']
        assert r['thread'] == 'tennis-ta' and r['code_sha'] == SHA and r['v'] == 1
        assert r['code_epoch'] == f'tennis-ta-sim/3; REPLAY_VERSION={replay_version_in_code()}; main with #290-#292; #279 and #287 merged in'
        assert r['data'] == {'source': 'history', 'books': 'synthetic', 'days': r['data']['days'], 'doge': False, 'copy': 'atp:abc wta:def',
                             'engine': 'replay', 'replay_version': replay_version_in_code()}
        assert r['flags'] == ['dev-choice'] and r['ref'] == 'gdrive:kalshi-bot-archive/models/tennis-ta/runs/4242'
        # C11: the base bot and its non-main defaults (every spec runs the ratchet off on history)
        assert r['base'] == 'tennis-ta@' + SHA and r['base_defaults'] == {'TENNIS_TRAIL_RATCHET': False}, (r['arm'], r.get('base_defaults'))
        assert r['seed'] == (20261105 if r['role'] == 'placebo' else None)
    # Family A: one row per spec (config x arm), arm = the spec id, env = its overrides.
    a = {r['arm']: r for r in rows if r['family'] == 'tennis-ta-A'}
    assert len(a) == 11 and a[PROD_F1]['env'] == PROD


def test_registry_roles_and_controls_link():
    rows = e2e()['registry']
    a = {r['arm']: r for r in rows if r['family'] == 'tennis-ta-A'}
    prod = a[PROD_F1]
    assert prod['role'] == 'control' and 'control' not in prod
    for arm, r in a.items():
        cfg, tag = arm.rsplit('|', 1)
        if arm == PROD_F1:
            continue
        if 'prod|' in arm:  # measuring sticks
            assert r['role'] == 'control' and 'control' not in r, arm
        elif tag == 'F1':
            assert r['role'] == 'candidate' and r['control'] == prod['trial_id'], arm
        elif tag == 'F2':
            assert r['role'] == 'neighbour' and r['control'] == a[cfg + '|F1']['trial_id'], arm
        elif tag == 'coin':
            assert r['role'] == 'placebo' and r['control'] == a[cfg + '|F1']['trial_id'], arm
            assert r['placebo_for'] == cfg + '|F1', arm
        else:
            raise AssertionError(arm)
    assert a['A|s1|m0.01|f0.2|o0.01|w60|coin']['control'] == prod['trial_id']
    assert a['A|s1|m0.02|f0.2|o0.01|w60|F1']['verdict'].startswith('no: ') and 'config breaches=0' in a['A|s1|m0.02|f0.2|o0.01|w60|F1']['verdict']
    assert prod['verdict'] == 'flag'
    s = e2e()['summary']['registry']
    assert s['control'] == prod['trial_id'] and s['control_arm'] == PROD_F1 and s['written']
    assert s['roles'] == {'control': 3, 'candidate': 2 + 3, 'neighbour': 3, 'placebo': 3}, s['roles']


def test_registry_contract_type_and_modules():
    rows = e2e()['registry']
    assert all(r['contract_type'] == 'tennis' for r in rows)
    mods = {r['arm']: r['modules'] for r in rows}
    assert mods['A|s1|prod|settlehold|F1'] == ['exits'] and mods['A|s1|prod|nopacer|F1'] == ['pacer']
    assert all(m == ['tennis-ta'] for arm, m in mods.items() if 'prod|' not in arm)
    reg = registry_module()
    assert all(reg.contract_type_of(r) == 'tennis' and reg.modules_of(r) == r['modules'] for r in rows)


def test_family_a_modules_follow_the_overrides_for_sticks_and_hypotheses_alike():
    """A loser-stop candidate changes the exits module just as the loser-stop stick does, so the contract-type ledger
    (disjoint module sets) cannot add it on top of an exits result for the same change."""
    reg = registry_module()
    stop = dict(PROD, HARNESS_LOSER_STOP=0.5)
    both = dict(PROD, HARNESS_LOSER_STOP=0.5, TENNIS_CONF_FLOW=0.4)
    flow = dict(PROD, TENNIS_CONF_FLOW=0.4)
    days = ['2026-05-01', '2026-05-02']

    def run(rid, ov, arm, production=False):
        return {'id': rid, 'config': rid.rsplit('|', 1)[0], 'arm': arm, 'overrides': ov, 'production': production,
                'by_day': {days[0]: 1.0}, 'fills': 1, 'markets': 1, 'verdict': 'x', 'raw': {}}
    a_runs = [run('A|s2|prod|F1', PROD, 'F1', True), run('A|s2|prod|stop50|F1', stop, 'stick'), run('A|s2|stop50|F1', stop, 'F1'),
              run('A|s2|stop50|F2', stop, 'F2'), run('A|s2|stop50|coin', stop, 'coin'), run('A|s2|stop50f04|F1', both, 'F1'),
              run('A|s2|f04|F1', flow, 'F1'), run('A|s2|prod|bank|F1', dict(PROD, HARNESS_BANKROLL=400), 'stick'),
              run('A|s2|prod|fees125|F1', dict(PROD, HARNESS_FEE_MULT=1.25), 'stick'),
              run('A|s2|prod|settlehold|F1', dict(PROD, TENNIS_END_LOSER_CUT=False), 'stick')]
    rows, problems, _ = R.registry_rows(reg.make_id, SHA, days, 48.0, {'source': 'history', 'days': days}, [], 'ref', 'epoch', 'ts',
                                        a_runs, [])
    assert problems == []
    mods = {r['arm']: r['modules'] for r in rows}
    assert mods['A|s2|prod|stop50|F1'] == mods['A|s2|stop50|F1'] == mods['A|s2|stop50|F2'] == mods['A|s2|stop50|coin'] == ['exits']
    assert mods['A|s2|stop50f04|F1'] == ['exits', 'tennis-ta'] and mods['A|s2|f04|F1'] == ['tennis-ta']
    assert mods['A|s2|prod|F1'] == ['tennis-ta'] and mods['A|s2|prod|bank|F1'] == ['sizing'] and mods['A|s2|prod|fees125|F1'] == ['tennis-ta']
    assert mods['A|s2|prod|settlehold|F1'] == ['exits']
    assert all(reg.modules_of(r) == r['modules'] for r in rows)
    # On R production keeps the ratchet on, so the ratchet off there is a tennis-ta change too; on H it is production's.
    assert R.spec_modules(stop, 'H') == ['exits'] and R.spec_modules(stop, 'R') == ['exits', 'tennis-ta']
    assert R.spec_modules(dict(PROD, HARNESS_PACER='off')) == ['pacer'] and R.stick_modules is R.spec_modules


def test_code_epoch_carries_the_replay_version_of_the_code():
    v = replay_version_in_code()
    assert R.replay_version() == v
    assert R.code_epoch('tennis-ta-sim/3', v) == f'tennis-ta-sim/3; REPLAY_VERSION={v}; main with #290-#292; #279 and #287 merged in'
    s = e2e()['summary']['registry']
    # The sweep records the version in the shard metas (meta.replayVersion); it must agree with the code.
    assert s['replay_version'] == v and s['replay_version_source'].startswith('the shard metas (meta.replayVersion)')
    assert os.path.join('research', 'history', 'historyReplay.ts') in s['replay_version_source']
    assert all(r['code_epoch'] == R.code_epoch('tennis-ta-sim/3', v) and r['data']['replay_version'] == v for r in e2e()['registry'])
    # Without it (the H0 fixture's metas carry none), the file's.
    assert h0()['summary']['registry']['replay_version_source'] == os.path.join('research', 'history', 'historyReplay.ts')
    assert all(r['data']['replay_version'] == v for r in h0()['rows'])
    assert R.replay_version_of({'replayVersion': v})[0] == v and R.replay_version_of({})[:2] == (v, os.path.join('research', 'history', 'historyReplay.ts'))
    assert 'is not a whole number' in R.replay_version_of({'replayVersion': True})[2]
    assert f'sets {v}' in R.replay_version_of({'replayVersion': v - 1})[2]
    # A moved replay version moves the epoch; an unreadable one gives None (the report then writes nothing).
    root = tmpdir()
    fake = os.path.join(root, 'historyReplay.ts')
    with open(fake, 'w') as fh:
        fh.write('// x\nexport const REPLAY_VERSION = 9;\nconst y = 1;\n')
    assert R.replay_version(fake) == 9 and 'REPLAY_VERSION=9;' in R.code_epoch('tennis-ta-sim/3', 9)
    assert R.replay_version(os.path.join(root, 'missing.ts')) is None


def test_dev_rows_are_dev_choice_and_read_no_hold_day():
    """C11: an H-DEV run is a dev-choice run: flags ['dev-choice'], no by_day day from H-HOLD on, so the registry shows
    DEV:choice-only and never G0:dev-choice-reads-hold (the family would be blocked)."""
    reg = registry_module()
    e = e2e()
    rows = e['registry']
    assert all(max(r['by_day']) < '2026-08-01' and max(r['data']['days']) < '2026-08-01' for r in rows)
    for r in rows:
        err, fl = reg.validate(r)
        assert err == [] and 'DEV:choice-only' in fl and 'G0:dev-choice-reads-hold' not in fl, (r['arm'], fl)
        assert 'heldout' not in r and 'by_tercile' not in r
    v = subprocess.run([sys.executable, '-I', registry_path(), 'validate', os.path.join(e['out'], ROWS_FILE)], capture_output=True, text=True, timeout=120)
    assert v.returncode == 0 and 'DEV:choice-only' in v.stdout and 'dev-choice-reads-hold' not in v.stdout
    assert e['summary']['registry']['validator_flags'].get('DEV:choice-only') == len(rows)
    # The fixture's straddling week (Jul 27) holds embargo and hold matches: owned, counted, never scored.
    ml = e['matches']
    assert any(m['pool'] == 'hold' for m in ml) and any(m['pool'] == 'embargo' for m in ml)
    assert not any(m['pool'] == 'disc' and m['close'] >= DEV_TO for m in ml)
    assert 'none in H-HOLD' in e['report'] and 'H-DEV, up to DEV_TO' in e['report']
    # H0 rows are dev-side too (a stress test of stage 2 finalists).
    assert all(x['flags'] == ['dev-choice', 'H0-stress'] for x in h0()['rows'])


def test_a_dev_choice_run_that_would_read_hold_is_refused():
    """A disc-labelled match on an H-HOLD day (a sweep that mislabels) would give dev-choice rows an H-HOLD day: refused."""
    def mutate(s, p):
        f = os.path.join(s, 'a-s1-1-1.json.gz')
        with gzip.open(f, 'rt') as fh:
            d = json.load(fh)
        for m in d['matchList']:
            if m['pool'] == 'hold':
                m['pool'], m['fold'] = 'disc', None
        with gzip.open(f, 'wt') as fh:
            json.dump(d, fh)
    err = _refused(mutate)
    assert 'dev-choice' in err and 'H-HOLD' in err and 'nothing is written' in err


def test_a_stratum_label_that_disagrees_with_the_pool_is_refused():
    def mutate(s, p):
        f = os.path.join(s, 'a-s1-0-1.json.gz')
        with gzip.open(f, 'rt') as fh:
            d = json.load(fh)
        d['meta']['stratumLabel'] = 'H0'
        with gzip.open(f, 'wt') as fh:
            json.dump(d, fh)
    err = _refused(mutate)
    assert 'the shards say stratum H0' in err and 'registry family' in err


def test_registry_by_day_is_one_day_set_over_the_pool():
    e = e2e()
    rows = e['registry']
    pool_days = sorted({m['day'] for m in e['matches'] if m['pool'] == 'disc'})
    for r in rows:
        assert sorted(r['by_day']) == pool_days == r['data']['days'], r['arm']
    # A pool day without a trade is 0 (no-tape matches only, or no entry by the arm), and the days add up to the net.
    a = {r['arm']: r for r in rows if r['family'] == 'tennis-ta-A'}
    cells = {c['cell']: c for c in e['cells']}
    for arm, r in a.items():
        c = cells[f'{arm}|all|all|all']
        assert abs(sum(r['by_day'].values()) - c['net']) < 1e-4, arm
        assert r['fills'] == c['entries'] and r['raw']['net'] == round(c['net'], 6)
    # markets = distinct (match, market) pairs traded in the pool: one episode a match here, on market A or (F2) either.
    assert a[PROD_F1]['markets'] == a[PROD_F1]['fills'] == a['A|s1|m0.01|f0.2|o0.01|w60|F2']['markets'] > 0
    two = a['A|s1|m0.02|f0.2|o0.01|w60|F2']
    assert two['fills'] > two['markets'] == a[PROD_F1]['markets']


def test_registry_hours_are_the_usd_per_hour_denominator():
    e = e2e()
    s = e['summary']
    assert s['pool_hours'] > 0
    for r in e['registry']:
        assert r['hours'] == s['pool_hours'], r['arm']
        if r['family'] == 'tennis-ta-A':
            assert abs(r['raw']['usd_per_hour'] * r['hours'] - r['raw']['net']) < 1e-6, r['arm']
    assert s['registry']['hours'] == s['pool_hours']


def test_nostart_and_old_rows_are_excluded_from_disc_and_counted():
    e = e2e()
    s, ml = e['summary'], e['matches']
    by = {p: sum(1 for m in ml if m['pool'] == p) for p in ('disc', 'nostart', 'old', 'embargo', 'hold')}
    assert all(by.values()), by
    assert s['excluded'] == {p: by[p] for p in ('nostart', 'old', 'embargo', 'hold')}, s['excluded']
    assert s['by_pool']['disc']['scored'] and not s['by_pool']['nostart']['scored'] and not s['by_pool']['old']['scored']
    assert s['matches'] == sum(1 for m in ml if m['pool'] == 'disc' and m['trades'] > 0)
    assert s['pool_no_published_start'] == 0 and s['owned_no_published_start'] == by['nostart']
    # Every fixture match with a tape carries one episode per run: the production row's fills are the disc ones only.
    prod = next(r for r in e['registry'] if r['arm'] == PROD_F1)
    assert prod['fills'] == s['matches']
    assert 'Matches by pool' in e['report'] and 'nostart' in e['report'] and 'Era rule (C9' in e['report']
    assert 'stratum H0' in e['report'] and '2026-04-27 05:00 UTC' in e['report'] and '2026-07-31 00:00 UTC' in e['report']


def test_registry_rows_need_the_registry_module():
    root = tmpdir()
    units, shards, _ = build(root, families_b=False)
    out = os.path.join(root, 'out')
    r = run_report(units, shards, out, registry=False, boot=49)
    assert r.returncode != 0 and 'no --registry-py' in r.stderr and not os.path.exists(out), r.stderr[-1500:]
    r2 = run_report(units, shards, out, '--no-registry', registry=False, boot=49)
    assert r2.returncode == 0, r2.stderr[-2000:]
    assert not os.path.exists(os.path.join(out, ROWS_FILE)) and 'Registry: no rows' in open(os.path.join(out, 'report.md')).read()
    bad = os.path.join(root, 'bad_registry.py')
    with open(bad, 'w') as fh:
        fh.write('def make_id(*a, **k):\n    return "same"\n\ndef validate(r):\n    return [], []\n')
    out3 = os.path.join(root, 'out3')
    r3 = subprocess.run([sys.executable, SCRIPT, '--shards', shards, '--run', '4242', '--out', out3, '--units', units, '--boot', '49',
                         '--registry-py', bad, '--sha', SHA], capture_output=True, text=True, timeout=600)
    assert r3.returncode != 0 and 'trial id(s) repeat' in r3.stderr and not os.path.exists(out3), r3.stderr[-1500:]
    strict = os.path.join(root, 'strict_registry.py')
    with open(strict, 'w') as fh:
        fh.write('import hashlib, json\ndef make_id(*a, **k):\n    return hashlib.sha1(json.dumps([a, k], sort_keys=True, default=str).encode()).hexdigest()\n\n'
                 'def validate(r):\n    return (["no thanks"] if r["role"] == "placebo" else []), []\n')
    out4 = os.path.join(root, 'out4')
    r4 = subprocess.run([sys.executable, SCRIPT, '--shards', shards, '--run', '4242', '--out', out4, '--units', units, '--boot', '49',
                         '--registry-py', strict, '--sha', SHA], capture_output=True, text=True, timeout=600)
    assert r4.returncode != 0 and 'no thanks' in r4.stderr and 'nothing is written' in r4.stderr and not os.path.exists(out4)
    out5 = os.path.join(root, 'out5')
    r5 = run_report(units, shards, out5, '--sha', 'a' * 40, boot=49)
    assert r5.returncode != 0 and 'swept at' in r5.stderr and not os.path.exists(out5)


def test_family_b_placebo_rows_when_the_export_has_day_sums():
    root = tmpdir()
    units, shards, _ = build(root, b_day_placebo=True)
    out = os.path.join(root, 'out')
    r = run_report(units, shards, out, boot=49)
    assert r.returncode == 0, r.stderr[-2000:]
    rows = read_registry(out)
    b = {x['arm']: x for x in rows if x['family'] == 'tennis-ta-B'}
    rule = 'B|RSI14L|1m|exitExt|follow|tp30sl30'
    assert b[rule]['role'] == 'candidate' and b[rule]['control'] == b[rule + '|placebo']['trial_id']
    assert b[rule + '|placebo']['role'] == 'placebo' and b[rule + '|placebo']['seed'] == 20261105 and b[rule + '|placebo']['placebo_for'] == rule
    assert b[rule + '|placebo']['fills'] == 10 * DISC_UNITS and sorted(b[rule + '|placebo']['by_day']) == b[rule]['data']['days']
    # Markets add over the shard files (each slice counts the markets of the matches it owns).
    shard_cells = []
    for f in sorted(os.listdir(shards)):
        with gzip.open(os.path.join(shards, f), 'rt') as fh:
            shard_cells += [c for c in json.load(fh)['familyB']['cells'] if c['id'] == B_POS]
    assert b[rule]['markets'] == sum(c['markets'] for c in shard_cells) > 0
    assert b[rule + '|placebo']['markets'] == sum(c['placeboMarkets'] for c in shard_cells) > 0
    assert len({tuple(sorted(x['by_day'])) for x in rows}) == 1
    reg = registry_module()
    assert all(reg.validate(x)[0] == [] for x in rows)


def test_stick_is_reported_but_never_screened():
    e = e2e()
    sticks = [c for c in e['cells'] if c['arm'] == 'stick']
    assert sticks and all('bh' not in c and not c.get('flag') for c in sticks)
    assert e['summary']['f1_cells'] == sum(1 for c in e['cells'] if c['arm'] == 'F1')
    assert e['summary']['bh_floor']['A_m'] == e['summary']['f1_cells']
    assert not any('settlehold' in x for x in e['summary']['flagged'])
    assert 'settlehold' not in json.dumps(e['summary']['spa'])
    st = [r for r in e['registry'] if 'prod|' in r['arm']]
    assert len(st) == 2 and all(r['verdict'] == 'measuring stick (not screened)' and r['raw']['bh'] is None and r['role'] == 'control' for r in st)
    assert e['summary']['sticks'] and e['summary']['sticks'][0]['entries'] > 0
    assert 'Measuring sticks' in e['report']


def test_breach_rule_is_per_config():
    e = e2e()
    cfg = 'A|s1|m0.02|f0.2|o0.01|w60'
    f1 = [c for c in e['cells'] if c['config'] == cfg and c['arm'] == 'F1']
    assert f1 and all(c['config_breaches'] == 1 for c in f1)
    # The breach sits in one p3 cell, yet no cell of the config passes, while the same edge without a breach does.
    assert not any(c['flag'] for c in f1)
    assert any(c['breaches'] == 0 and c['bh'] and 'config breaches=0' in c['gates_failed'] for c in f1)
    prod_all = [c for c in e['cells'] if c['cell'] == 'A|s1|m0.01|f0.2|o0.01|w60|F1|all|all|all']
    assert prod_all and prod_all[0]['flag'], prod_all
    assert e['summary']['breach_configs'] == [cfg]


def test_family_b_rows_and_section():
    e = e2e()
    rows = {r['arm']: r for r in e['registry'] if r['family'] == 'tennis-ta-B'}
    # One row per reading x exit, its 'all' context as the row and the other contexts in by_cell.
    assert set(rows) == {'B|RSI14L|1m|exitExt|follow|tp30sl30', 'B|MACD|5m|zero|fade|t2m', 'B|ROC10L|1m|zero|follow|t10m'}, set(rows)
    pos = rows['B|RSI14L|1m|exitExt|follow|tp30sl30']
    assert pos['raw']['cell'] == B_POS and pos['fills'] == 10 * DISC_UNITS and set(pos['by_cell']) == {'p15-35:mid:trend'}
    assert pos['verdict'] == 'flag' and rows['B|ROC10L|1m|zero|follow|t10m']['verdict'].startswith('no: ')
    # An export without per-day placebo sums (2-column day rows; research/tennisTaSignals.ts now writes 4): no placebo rows,
    # the candidates are unpaired (said in the notes). test_family_b_placebo_rows_when_the_export_has_day_sums covers 4.
    assert all(r['role'] == 'candidate' and 'control' not in r and r['env'] == {} and r['modules'] == ['tennis-ta'] for r in rows.values())
    assert any('placebo rows are not written' in x for x in e['summary']['registry']['notes'])
    fb = e['summary']['family_b']
    assert fb['design_size'] == 40 and fb['bh_m'] == 40 and e['summary']['n_raw']['B'] == 4
    with gzip.open(os.path.join(e['out'], 'cells-b.json.gz'), 'rt') as fh:
        cb = {c['id']: c for c in strict_json(fh.read())}
    pos = cb[B_POS]
    assert pos['n'] == 10 * DISC_UNITS and pos['units'] == DISC_UNITS and pos['placebo_units'] == DISC_UNITS
    assert pos['bh'] and pos['flag'] and pos['z_placebo'] > 3 and pos['p'] >= 1 / (BOOT + 1)
    assert not cb[B_BREACH]['flag'] and cb[B_BREACH]['rule_breaches'] == 1
    assert not cb[B_NULL]['flag']
    assert '### Family B' in e['report'] and 'Gates passed' in e['report']


def test_report_states_mechanics():
    e = e2e()
    rep = e['report']
    assert 'restarts only at unit edges' in rep
    assert 'atp:abc wta:def' in rep
    assert 'without a published start' in rep
    assert 'N_raw: family A' in rep and 'family B 4 cells' in rep
    s = e['summary']
    assert s['pool_hours_source'] == 'the plan'
    # Pool hours: the plan gives the 14 swept weeks whole (Apr 27 to Aug 3); H-DEV's window cuts them at DEV_TO (Jul 31
    # 00:00 UTC), so the embargo day and the hold days of the straddling week count in no disc hour.
    assert abs(s['pool_hours_unclipped'] - (DEV_TO - START_ERA) / HOUR) < 1e-6 and abs(s['pool_hours'] - 2275) < 1e-6
    assert s['owned_no_published_start'] > 0 and s['pool_no_published_start'] == 0
    assert all(c['usd_per_live_hour'] is not None for c in e['cells'] if c['tour'] == 'all')
    assert s['pbo'] is not None and s['folds'] == ['2026-05', '2026-06', '2026-07', '2026-08']
    assert s['onc']['best_k'] and s['onc']['k_cap'] is None and s['onc']['warnings'] == [] and 'universe' in s['v_sr_source']
    assert 'Knob sensitivity (section 5 rule' in rep and 'A2 (the 729-config factorial): does not run' in rep
    assert s['era_source'] == 'the shard metas' and s['stratum_label'] == 'H' and 'stratum H' in rep


def test_report_states_the_onc_k_range_and_the_ranking_scope():
    e = e2e()
    s, rep = e['summary'], e['report']
    kr = s['onc']['k_range']
    # No default cap (--onc-max-k 0): the base scan runs k = 2..n - 1 of the distinct vectors, and the report says so.
    assert kr['from'] == 2 and kr['to'] == s['onc_distinct'] - 1 == kr['n'] - 1 and kr['cap'] is None, kr
    assert f"k search range 2..{kr['to']} = n - 1 of the {kr['n']} distinct vectors (no cap)" in rep
    assert R.parse_args(['--shards', 'x', '--out', 'y']).onc_max_k == 0
    assert 'Ranking scope:' in rep and "each config's F1 all/all/all cell" in rep and 'A2 is chosen only from stage 2 on H-DISC' in rep
    assert s['sensitivity']['scope'].startswith("each config's F1 all/all/all cell")


def test_dsr_sr0_is_per_tour_universe():
    # Two cluster series: one trades ATP matches only, one every match. On the WTA universe only the second varies; on the
    # ATP universe both are taken over the ATP matches, the matches an ATP cell's own SR is over.
    rng = np.random.default_rng(5)
    N = 400
    atp = np.arange(N) % 2 == 0
    u = {'ATP': atp, 'WTA': ~atp, 'all': np.ones(N, dtype=bool)}
    x1 = np.where(atp, 0.3 + rng.normal(0, 1, N), 0.0)
    x2 = -0.1 + rng.normal(0, 1, N)
    x3 = 0.05 + rng.normal(0, 1, N)
    sr0, v, srs = R.sr0_by_universe([x1, x2, x3], u, 3)
    assert len(srs['ATP']) == 3 and len(srs['WTA']) == 2 and len(srs['all']) == 3
    want = float(np.var([x[atp].mean() / x[atp].std(ddof=1) for x in (x1, x2, x3)], ddof=1))
    assert abs(v['ATP'] - want) < 1e-12 and abs(sr0['ATP'] - R.sr0_of(want, 3)) < 1e-12
    e = e2e()
    s = e['summary']
    assert set(s['sr0']) == {'ATP', 'WTA', 'all'}
    scored = [c for c in e['cells'] if c.get('dsr') is not None]
    assert scored and all(c['sr0'] == s['sr0'][c['tour']] for c in scored)
    assert 'one per tour universe' in e['report']


def test_era_edges_match_the_sweep():
    """C9's edges as research/tennisTaSweep.ts exports them (DEV_TO and HOLD_FROM land with the sweep's C9 change)."""
    import re
    with open(os.path.join(REPO, 'research', 'tennisTaSweep.ts')) as fh:
        sweep = fh.read()
    for name, got in (('HISTORY_FROM', R.HISTORY_FROM), ('START_ERA_FROM', R.START_ERA_FROM), ('DEV_TO', R.DEV_TO), ('HOLD_FROM', R.HOLD_FROM),
                      ('HARD_CUTOFF', R.HARD_CUTOFF)):
        m = re.search(r"export const %s = Date\.parse\('([^']+)'\)" % name, sweep)
        assert m, f'{name} is not exported by research/tennisTaSweep.ts (C9)'
        assert R.ms_of(m.group(1)) == got, (name, m.group(1))
    assert R.HOLD_FROM == R.day_ms(R.HO1_HOLD[0]) and R.DEV_TO == R.HOLD_FROM - DAY
    u = lambda iso, **k: dict({'start': R.ms_of(iso), 'end': R.ms_of(iso) + 7 * DAY}, **k)  # noqa: E731
    assert R.unit_pools(u('2025-06-09T05:00:00Z')) == {'out'}  # ends before the history starts
    assert R.unit_pools(u('2025-06-16T05:00:00Z')) == {'old'} and R.unit_pools(u('2026-04-20T05:00:00Z')) == {'old'}
    assert R.unit_pools(u('2025-08-11T05:00:00Z', sealed=True)) == {'old'}  # the legacy seal is ignored (C9)
    # The start era seals nothing; its pools are per match, so a week can hold several.
    assert R.unit_pools(u('2026-04-27T05:00:00Z')) == {'disc'} and R.unit_pools(u('2026-05-04T05:00:00Z', sealed=True)) == {'disc'}
    assert R.unit_pools(u('2026-07-27T05:00:00Z')) == {'disc', 'embargo', 'hold'}
    assert R.unit_pools(u('2026-08-03T05:00:00Z')) == {'hold'} and R.unit_pools(u('2026-11-02T05:00:00Z')) == {'hold'}
    assert R.unit_pools(u('2026-11-09T05:00:00Z')) == {'out'}
    # A run's own edges (meta.era) win over the defaults.
    later = R.era_of(dict(ERA, startEraFrom='2026-05-04T05:00:00.000Z'))
    assert R.unit_pools(u('2026-04-27T05:00:00Z'), later) == {'old'} and later['devTo'] == R.DEV_TO
    assert 'checkFrom' not in R.era_of(dict(ERA, checkFrom='2026-09-14T05:00:00.000Z'))
    # Pool windows: disc to DEV_TO, hold from HOLD_FROM to the end of H-HOLD's last UTC day (two hours before the cutoff).
    assert R.pool_window('disc') == (R.HISTORY_FROM, R.DEV_TO)
    assert R.pool_window('hold') == (R.HOLD_FROM, R.ms_of('2026-11-05T00:00:00Z'))
    # The fallback spans start at the history start; the straddling week gives each pool its part.
    sp = R.pool_spans_from_table([u('2025-06-16T05:00:00Z', id='w0')], ['old'], {'w0'})
    assert sp and sp[0]['intervals'][0][0] == R.HISTORY_FROM
    w = [u('2026-07-27T05:00:00Z', id='w1')]
    assert R.pool_spans_from_table(w, ['disc'], {'w1'})[0]['hours'] == 3 * 24 + 19
    assert R.pool_spans_from_table(w, ['hold'], {'w1'})[0]['hours'] == 2 * 24 + 5
    assert R.clip_spans([{'unit': 'w1', 'intervals': [[w[0]['start'], w[0]['end']]]}], *R.pool_window('hold'))[0]['hours'] == 2 * 24 + 5


_H0 = {}


def h0(*extra):
    """One stage 2 pool 'old' (stratum H0) run, shared by the H0 checks (extra args: a separate run)."""
    key = tuple(extra)
    if key not in _H0:
        root = _H0.get('root') or tmpdir()
        if 'root' not in _H0:
            _H0['root'] = root
            _H0['inputs'] = build(root, families_b=False, pool='old', stage='2', t0='2025-07-07T05:00:00', replay_meta=False)
        units, shards, _ = _H0['inputs']
        out = os.path.join(root, 'out-' + str(len(_H0)))
        r = run_report(units, shards, out, *extra, pool='old', boot=49)
        assert r.returncode == 0, r.stderr[-2000:]
        with open(os.path.join(out, 'summary.json')) as fh:
            s = strict_json(fh.read())
        with gzip.open(os.path.join(out, 'cells.json.gz'), 'rt') as fh:
            cells = strict_json(fh.read())
        _H0[key] = dict(out=out, summary=s, rows=read_registry(out), cells=cells, report=open(os.path.join(out, 'report.md')).read(),
                        matches=read_matches(shards))
    return _H0[key]


def test_pool_old_is_scored_as_h0_at_stage_2():
    h = h0()
    s, rows = h['summary'], h['rows']
    assert s['pools'] == ['old'] and s['stratum_label'] == 'H0' and s['matches'] > 300 and s['excluded'] == {}
    assert rows and all(x['flags'] == ['dev-choice', 'H0-stress'] and x['data']['source'] == 'history' for x in rows)
    assert s['pool_hours'] > 0 and all(x['hours'] == s['pool_hours'] for x in rows)
    assert all(registry_module().validate(x)[0] == [] for x in rows)
    assert 'stratum H0' in h['report']


def test_h0_rows_are_their_own_family_so_the_registry_merge_keeps_the_disc_family_whole():
    """registry.py merge scores a family over the days all its rows share: H0's days never meet the start era's, so H0
    (and R) rows get families of their own and the disc family's statistics are the same with or without them."""
    reg = registry_module()
    disc, old = e2e()['registry'], h0()['rows']
    assert {r['family'] for r in disc} == {'tennis-ta-A', 'tennis-ta-B'}
    assert {r['family'] for r in old} == {'tennis-ta-A-H0'}
    assert h0()['summary']['registry']['family_a'] == 'tennis-ta-A-H0'
    assert any('tennis-ta-A-H0' in x for x in h0()['summary']['registry']['notes'])
    assert not set(disc[0]['by_day']) & set(old[0]['by_day'])
    # The H0 control is H0's own production row, and every H0 control link stays inside the H0 family.
    ids_old = {r['trial_id'] for r in old}
    assert all(r['control'] in ids_old for r in old if r.get('control'))
    assert h0()['summary']['registry']['control'] == next(r['trial_id'] for r in old if r['arm'] == PROD_F1)

    def merged(*row_sets):
        root = tmpdir()
        sd = os.path.join(root, 'shards', 'tennis-ta')
        os.makedirs(sd)
        for i, rows in enumerate(row_sets):
            with open(os.path.join(sd, f'run{i}.jsonl'), 'w') as fh:
                for r in rows:
                    fh.write(json.dumps(r) + '\n')
        rep = reg.merge(os.path.join(root, 'shards'), os.path.join(root, 'merged'))
        return {f['family']: f for f in rep['families']}
    alone, both = merged(disc), merged(disc, old)
    a, b = alone['tennis-ta-A'], both['tennis-ta-A']
    assert a['days'] == b['days'] == len(disc[0]['by_day']) > 0
    assert (a['n_raw'], a['pbo_splits'], len(a['candidates'])) == (b['n_raw'], b['pbo_splits'], len(b['candidates'])) and b['pbo_splits'] > 0
    assert abs(a['k_eff'] - b['k_eff']) < 1e-9
    hh = both['tennis-ta-A-H0']
    assert hh['days'] == len(old[0]['by_day']) > 0 and hh['n_raw'] == len(old) and hh['pbo_splits'] > 0
    assert R.reg_families('H') == ('tennis-ta-A', 'tennis-ta-B') and R.reg_families('R') == ('tennis-ta-A-R', 'tennis-ta-B-R')
    assert R.stratum_label_of('H', ['old']) == 'H0' and R.stratum_label_of('H', ['disc']) == 'H' and R.stratum_label_of('R', ['disc']) == 'R'


def test_h0_live_hours_are_refused_or_taken_from_a_start_era_median():
    """No H0 match has a published start: without --live-median-hours the $/live-hour figures are refused out loud
    (None, a warning in report.md), with it every match stands in for that many hours."""
    h = h0()
    s = h['summary']
    assert s['live_hours'] == {'ATP': None, 'WTA': None, 'all': None}
    assert 'not measured' in s['live_hours_source'] and 'live-median-hours' in s['live_hours_source']
    assert all(c['usd_per_live_hour'] is None for c in h['cells'])
    assert all(c['usd_per_hour'] is not None for c in h['cells'] if c['tour'] == 'all')
    assert '**Warning (A7):** no $/live-match-hour figure' in h['report']
    g = h0('--live-median-hours', '2.0')
    sg = g['summary']
    assert abs(sg['live_hours']['all'] - 2.0 * sg['matches']) < 1e-6 and 'Warning (A7)' not in g['report']
    assert '--live-median-hours' in sg['live_hours_source'] and 'estimated' in sg['live_hours_source']
    assert all(c['usd_per_live_hour'] is not None for c in g['cells'] if c['tour'] == 'all')
    # A start-era run's summary.json can be passed as it is (its live_median_hours, per series).
    d = e2e()['summary']
    assert set(d['live_median_hours']) == {'KXATPMATCH', 'KXWTAMATCH'} and all(v > 0 for v in d['live_median_hours'].values())
    assert R.parse_live_medians(os.path.join(e2e()['out'], 'summary.json')) == d['live_median_hours']
    assert R.parse_live_medians('KXATPMATCH=1.9,KXWTAMATCH=1.6') == {'KXATPMATCH': 1.9, 'KXWTAMATCH': 1.6}
    assert R.parse_live_medians('2') == {'*': 2.0} and R.parse_live_medians(None) == {}
    for bad in ('0', 'KXATPMATCH=-1', 'x'):
        try:
            R.parse_live_medians(bad)
            raise AssertionError(bad)
        except ValueError:
            pass


def test_live_durations_fall_back_from_series_to_pool_to_the_given_median():
    def m(series, hours, pub):
        return {'series': series, 'start': 0, 'close': int(hours * HOUR), 'startPublished': pub}
    # A series with published starts lends its median; a series with none takes the pool's; nothing is ever 0.
    M = [m('KXATPMATCH', 2.0, True), m('KXATPMATCH', 3.0, True), m('KXATPMATCH', 9.0, False), m('KXWTAMATCH', 9.0, False)]
    live, med, info = R.live_durations(M)
    assert med == {'KXATPMATCH': 2.5} and list(live) == [2.0, 3.0, 2.5, 2.5]
    assert info['estimated'] == 2 and info['by']['KXWTAMATCH']['from'].startswith("the pool's median") and 'estimated' in info['source']
    # Every start published: measured as is.
    live, _, info = R.live_durations(M[:2])
    assert list(live) == [2.0, 3.0] and info['estimated'] == 0 and info['source'].startswith('measured')
    # No published start at all: refused unless a median is given (per series or for all).
    none = [m('KXATPMATCH', 9.0, False), m('KXWTAMATCH', 9.0, False)]
    live, med, info = R.live_durations(none)
    assert live is None and med == {} and info['source'].startswith('not measured')
    live, _, _ = R.live_durations(none, {'KXATPMATCH': 1.9, 'KXWTAMATCH': 1.6})
    assert list(live) == [1.9, 1.6]
    live, _, _ = R.live_durations(none, {'KXATPMATCH': 1.9})
    assert live is None
    live, _, _ = R.live_durations(none, {'*': 1.7})
    assert list(live) == [1.7, 1.7]


def _refused(mutate, *extra):
    root = tmpdir()
    units, shards, plan = build(root)
    mutate(shards, plan)
    out = os.path.join(root, 'out')
    r = run_report(units, shards, out, *extra)
    assert r.returncode != 0, r.stdout[-2000:]
    assert not os.path.exists(os.path.join(out, ROWS_FILE))
    return r.stderr


def test_incomplete_shard_set_is_refused():
    err = _refused(lambda s, p: os.remove(os.path.join(s, 'a-s1-1-0.json.gz')))
    assert 'shard 1 sub-slice 0: missing' in err and 'no registry rows' in err


def test_duplicate_shard_is_refused():
    err = _refused(lambda s, p: shutil.copy(os.path.join(s, 'a-s1-0-1.json.gz'), os.path.join(s, 'a-s1-0-1 (copy).json.gz')))
    assert 'duplicate' in err


def test_data_version_mismatch_is_refused():
    def mutate(s, p):
        f = os.path.join(s, 'a-s1-1-1.json.gz')
        with gzip.open(f, 'rt') as fh:
            d = json.load(fh)
        d['meta']['dataVersion'] = 'atp:zzz wta:def'
        with gzip.open(f, 'wt') as fh:
            json.dump(d, fh)
    err = _refused(mutate)
    assert 'dataVersion differs' in err


def _rewrite_runs(shards, fn):
    for f in os.listdir(shards):
        p = os.path.join(shards, f)
        with gzip.open(p, 'rt') as fh:
            d = json.load(fh)
        for r in d['runs']:
            fn(r)
        with gzip.open(p, 'wt') as fh:
            json.dump(d, fh)


def test_unlinked_or_stress_runs_are_refused():
    def no_suffix(r):
        if r['id'] == 'A|s1|m0.005|f0.05|o0.005|w120|F2':
            r['id'] = 'A|s1|m0.005|f0.05|o0.005|w120'
    err = _refused(lambda s, p: _rewrite_runs(s, no_suffix))
    assert 'must end in its arm' in err and 'no registry rows' in err

    def stress(r):
        if r['id'] == 'A|s1|m0.005|f0.05|o0.005|w120|F1':
            r['overrides'] = dict(r['overrides'], HARNESS_LATENCY_MS=2000)
    err = _refused(lambda s, p: _rewrite_runs(s, stress))
    assert 'HARNESS_LATENCY_MS' in err


def test_plan_mismatch_is_refused():
    def mutate(s, p):
        with open(p) as fh:
            plan = json.load(fh)
        plan['expected'].append('a-s1-2-0.json.gz')
        with open(p, 'w') as fh:
            json.dump(plan, fh)
    root = tmpdir()
    units, shards, plan = build(root)
    mutate(shards, plan)
    out = os.path.join(root, 'out')
    r = run_report(units, shards, out, '--plan', plan)
    assert r.returncode != 0 and 'planned but missing' in r.stderr
    assert not os.path.exists(out)


def test_pool_requests_that_cannot_be_scored_are_refused():
    root = tmpdir()
    units, shards, _ = build(root, families_b=False)
    for pool, why in (('check', 'unknown pool'), ('disc,hold', 'one pool per run'), ('disc,old', 'one pool per run'),
                      ('nostart', 'never scored'), ('embargo', 'never scored'), ('sealed', 'unknown pool'), ('dis', 'unknown pool'),
                      ('old', 'stage 2 finalists only'), ('hold', "only by stage 'hold'")):
        out = os.path.join(root, 'out-' + pool.replace(',', '-'))
        r = run_report(units, shards, out, pool=pool, boot=49)
        assert r.returncode != 0 and why in r.stderr and not os.path.exists(out), (pool, r.stderr[-800:])
    # Pool 'old' at stage 2 still has to be the shards' pool.
    root2 = tmpdir()
    units2, shards2, _ = build(root2, families_b=False, stage='2')
    out = os.path.join(root2, 'out')
    r = run_report(units2, shards2, out, pool='old', boot=49)
    assert r.returncode != 0 and 'swept for pool disc' in r.stderr and not os.path.exists(out)


def test_set_check_finds_a_skipped_pool_unit_but_not_a_sealed_one():
    def info(k, j, us, events, pool='disc'):
        last = us[-1]
        meta = {'run': '1', 'stage': '1', 'pool': pool, 'simVersion': 'tennis-ta-sim/3', 'dataVersion': 'v', 'families': ['A'], 'shards': 1,
                'subShards': 2, 'k': k, 'j': j, 'from': us[0]['startDay'], 'to': day_of(R.day_ms(day_of(last['end'])) + DAY), 'units': [u['id'] for u in us]}
        return {'file': f'a-s1-{k}-{j}.json.gz', 'meta': meta, 'events': events, 'run_ids': ('x',), 'has_b': False, 'b_design': None,
                'b_stratum': None, 'row_units': {us[0]['id']}, 'b_units': set(), 'problems': []}
    # The start era (C9): no sealed week, so every week between two swept disc weeks must be swept.
    table = units_table()
    disc = run_units(table, 'disc')
    assert R.check_shard_set([info(0, 0, disc[:5], ['e1']), info(0, 1, disc[5:8], ['e2'])], table) == []
    gap = R.check_shard_set([info(0, 0, disc[:5], ['e1']), info(0, 1, disc[6:8], ['e2'])], table)
    assert any('no shard file swept them' in x and disc[5]['id'] in x for x in gap), gap
    dup = R.check_shard_set([info(0, 0, disc[:5], ['e1']), info(0, 1, disc[5:8], ['e1'])], table)
    assert any('appear twice' in x for x in dup), dup
    # The old era: the unit table's legacy seal is ignored (C9), so a sealed week between two swept old weeks is a gap too.
    old_t = units_table('2025-07-07T05:00:00', 17)
    assert old_t[5]['sealed']
    gap = R.check_shard_set([info(0, 0, old_t[:5], ['e1'], 'old'), info(0, 1, old_t[6:8], ['e2'], 'old')], old_t)
    assert any('no shard file swept them' in x and old_t[5]['id'] in x for x in gap), gap
    assert R.check_shard_set([info(0, 0, old_t[:6], ['e1'], 'old'), info(0, 1, old_t[6:8], ['e2'], 'old')], old_t) == []


def test_family_b_design_is_taken_over_the_union_of_tours():
    # SignalStudy.designSize() = base x (1 + phases x 5 buckets x tours seen): a slice with no match states 38*2*5 = 380,
    # an ATP-only slice 38*2*21*5 = 7980, a WTA-only one the same; the set's design counts both tours (38*2*41*5).
    ph = ['pre', 'first20', 't1', 't2']

    def info(f, size, tours, phases=ph):
        return {'file': f, 'has_b': True, 'b_design': size, 'b_tours': tours, 'b_phases': phases}
    size, p = R.design_b([info('a', 380, []), info('b', 7980, ['KXATPMATCH']), info('c', 7980, ['KXWTAMATCH'])])
    assert p == [] and size == 38 * 2 * 41 * 5, (size, p)
    assert R.design_b([info('a', 380, []), info('b', 7980, ['KXATPMATCH'])]) == (7980, [])
    # A different series count or phase set is a different design: refused.
    assert R.design_b([info('a', 7980, ['KXATPMATCH']), info('b', 39 * 2 * 21 * 5, ['KXATPMATCH'])])[1]
    assert R.design_b([info('a', 7980, ['KXATPMATCH']), info('b', 38 * 2 * 26 * 5, ['KXATPMATCH'], ph + ['t3'])])[1]
    # Without the tour list (older exports) the sizes must agree exactly.
    old = [{'file': 'a', 'has_b': True, 'b_design': 40}, {'file': 'b', 'has_b': True, 'b_design': 41}]
    assert R.design_b(old)[1] and R.design_b(old[:1]) == (40, [])


def test_boot_p_is_never_zero_and_bh_floor():
    assert R.boot_p(0, 2000) == 1 / 2001
    p = R.boot_p(np.zeros(8748), 2000)
    assert (p > 0).all()
    # Under a uniform null at the floor, BH over 8,748 cells rejects nothing unless 44 or more cells sit at the floor.
    assert not R.bh(np.concatenate([np.full(43, 1 / 2001), np.ones(8748 - 43)]), 0.10).any()
    assert R.bh(np.concatenate([np.full(44, 1 / 2001), np.ones(8748 - 44)]), 0.10).sum() == 44


def test_onc_does_not_inflate_block_clusters():
    rng = np.random.default_rng(3)
    T = 2000
    for K, size in ((5, 20), (8, 15)):
        f = rng.normal(size=(K, T))
        X = np.repeat(f, size, axis=0) * 2 + rng.normal(size=(K * size, T))
        corr = np.corrcoef(X)
        labels = R.onc(corr, 11, max_k=20, n_init=2)
        assert labels.max() + 1 == K, (K, labels.max() + 1)


def test_onc_scans_past_a_cap_and_warns_when_one_binds():
    # Above --onc-max-k the silhouette quality is degenerate at small k, so a cap under the true count collapses N_eff;
    # the default scans to n - 1 and recovers the blocks, and a binding cap is visible in the diagnostics.
    rng = np.random.default_rng(3)
    K, size = 24, 5
    f = rng.normal(size=(K, 600))
    corr = np.corrcoef(np.repeat(f, size, axis=0) * 2 + rng.normal(size=(K * size, 600)))
    d = {}
    assert R.onc(corr, 11, None, n_init=2, diag=d).max() + 1 == K
    assert d['k_hi'] == K * size - 1 and d['k_cap'] is None and not d['cap_binding'] and not d['q_rising_at_cap']
    d2 = {}
    capped = R.onc(corr, 11, 12, n_init=2, diag=d2)
    assert capped.max() + 1 < K and d2['k_hi'] == 12 and (d2['cap_binding'] or d2['q_rising_at_cap']), d2
    assert R._k_grid(5) == [2, 3, 4, 5] and R._k_grid(100)[-1] == 100
    g = R._k_grid(5000)
    assert g[:39] == list(range(2, 41)) and all(b / a <= 1.1 + 1e-9 or b - a == 1 for a, b in zip(g[39:], g[40:]))


def test_run_checks_link_arms_and_keep_stress_arms_out():
    def run(rid, ov, fill='F1', placebo=None, stick=False):
        return rid, {'id': rid, 'overrides': ov, 'fill': fill, 'placebo': placebo, 'stick': stick, 'offsetMs': None}
    good = dict([run('A|s1|m0.01|f0.2|o0.01|w60|F1', PROD), run('A|s1|m0.01|f0.2|o0.01|w60|F2', PROD, 'F2'),
                 run('A|s1|m0.01|f0.2|o0.01|w60|coin', PROD, 'F1', 'coin'), run('A|s1|m0.02|f0.2|o0.01|w60|coin', BREACH, 'F1', 'coin'),
                 run('A|s1|m0.02|f0.2|o0.01|w60|F1', BREACH), run('A|s1|prod|settlehold|F1', dict(PROD, TENNIS_END_LOSER_CUT=False), stick=True),
                 run('A|s1|prod|nopacer|F1', dict(PROD, HARNESS_PACER='off'), stick=True)])
    assert R.check_runs([good, good]) == []

    def problems(*extra):
        return R.check_runs([dict(good, **dict(extra))])
    assert any('must end in its arm' in x for x in problems(run('A|s2|favmin0.65', dict(PROD, TENNIS_FAV_MIN=0.65))))
    assert any('names arm F2' in x for x in problems(run('A|s2|tp0.2|F2', dict(PROD, TENNIS_TP_PCT=0.2), 'F1')))
    assert any('different overrides' in x for x in problems(run('A|s1|m0.01|f0.2|o0.01|w60|F0', dict(PROD, TENNIS_FAV_MIN=0.65), 'F0')))
    assert any('HARNESS_FEE_MULT' in x and 'stick: true' in x for x in problems(run('A|s2|fee|F1', dict(PROD, HARNESS_FEE_MULT=1.25))))
    assert problems(run('A|s2|fee|F1', dict(PROD, HARNESS_FEE_MULT=1.25), stick=True)) == []
    assert problems(run('A|s2|lstop|F1', dict(PROD, HARNESS_LOSER_STOP=0.3))) == []  # the loser stop is a section 5 knob
    # A second production-valued arm (a clock-offset noise arm, or the same config written with defaults) is refused.
    assert any('noise-floor' in x for x in problems(run('A|s2|prod|off1s|F1', dict(PROD))))
    assert any('noise-floor' in x for x in problems(run('A|s2|prodx|F1', dict(PROD, TENNIS_FAV_MIN=0.75))))
    assert problems(run('A|s2|prod|off1s|F1', dict(PROD), stick=True)) == []
    other = dict(good)
    other['A|s1|m0.02|f0.2|o0.01|w60|F1'] = dict(other['A|s1|m0.02|f0.2|o0.01|w60|F1'], fill='F2')
    assert any('differ across the shard files' in x for x in R.check_runs([good, other]))


def test_production_is_identified_by_value():
    assert R.is_production(PROD) and R.is_production({'TENNIS_TRAIL_RATCHET': 'false', 'TENNIS_CONF_FLOW': '0.2'})
    assert not R.is_production(dict(PROD, TENNIS_FAV_MIN=0.65))  # a gate variant at production's thresholds
    assert not R.is_production(dict(PROD, TENNIS_END_LOSER_CUT=False)) and not R.is_production({})  # H runs the ratchet off
    assert R.is_production({}, 'R') and not R.is_production(PROD, 'R')
    assert R.is_production(dict(PROD, TENNIS_TRAIL='1', HARNESS_LOSER_STOP=0))
    s = e2e()['summary']
    assert s['production_config'] == 'A|s1|m0.01|f0.2|o0.01|w60' and len(s['production']) == 1
    assert s['sticks'] and all(x['vs_production'] is not None for x in s['sticks'])


def test_sensitivity_is_by_value_against_the_baseline():
    # Stage-2-shaped: every config writes all four thresholds (as stage 1 does), the centre is not production, a level of
    # TP_PCT comes as a string, one config restates a default, plus a pair, a stress arm and an R-only knob.
    c = dict(PROD, TENNIS_CONF_MOMENTUM_CENTS=0.02, TENNIS_CONF_FLOW=0.4)
    rows = {'A|s2|c': (c, 0.10), 'A|s2|c-f0.2': (dict(c, TENNIS_CONF_FLOW=0.2), 0.05),
            'A|s2|c-fm0.65': (dict(c, TENNIS_FAV_MIN=0.65), 0.30), 'A|s2|c-fm0.85': (dict(c, TENNIS_FAV_MIN=0.85), 0.12),
            'A|s2|c-tp0.2': (dict(c, TENNIS_TP_PCT='0.2'), 0.25), 'A|s2|c-hunt600': (dict(c, TENNIS_FAV_MAX=0.92, TENNIS_HUNT_MAX_SEC=600), 0.25),
            'A|s2|c-pair': (dict(c, TENNIS_CONF_FLOW=0.2, TENNIS_FAV_MIN=0.65), 0.9), 'A|s2|c-fee': (dict(c, HARNESS_FEE_MULT=1.25), -1.0),
            'A|s2|c-depth': (dict(c, TENNIS_CONF_DEPTH=0.4), 2.0)}
    s = R.knob_sensitivity(rows, 'A|s2|c', '2', ['disc'], 'H')
    # TP_PCT and HUNT_MAX_SEC tie at 0.15: the section 5 order puts takeProfitPct first.
    assert s['ranking'] == ['TENNIS_FAV_MIN', 'TENNIS_TP_PCT', 'TENNIS_HUNT_MAX_SEC', 'TENNIS_CONF_FLOW'], s['ranking']
    fm = s['knobs']['TENNIS_FAV_MIN']
    assert fm['levels'] == {'0.65': 0.30, '0.75': 0.10, '0.85': 0.12} and fm['baseline_level'] == '0.75' and abs(fm['range'] - 0.2) < 1e-12
    assert s['knobs']['TENNIS_CONF_DEPTH']['r_only'] and 'TENNIS_CONF_DEPTH' not in s['ranking']
    assert s['not_knobs'] == {'A|s2|c-fee': ['HARNESS_FEE_MULT']} and s['multi_knob'] == 1
    assert not s['a2_runs'] and 'fewer than six' in s['a2_reason']
    # Key presence would see all four thresholds in every config; by value only FLOW moves.
    assert 'TENNIS_CONF_MOMENTUM_CENTS' not in s['knobs']
    assert 'no F1 run' in R.knob_sensitivity(rows, 'A|s2|nope', '2', ['disc'], 'H')['a2_reason']


def test_a2_runs_only_when_stage_2_ranks_six_knobs_on_h_disc():
    base = dict(PROD)
    knobs = [('TENNIS_FAV_MIN', 0.65, 0.4), ('TENNIS_TP_PCT', 0.2, 0.3), ('TENNIS_MAX_SPREAD', 0.05, 0.3), ('TENNIS_HUNT_MIN_SIGNALS', 3, 0.25),
             ('TENNIS_UNDERDOG_MAX', 0.35, 0.2), ('HARNESS_LOSER_STOP', 0.3, 0.1), ('TENNIS_END_ENTRY_MARGIN', 0.1, 0.05)]
    rows = {'A|s2|prod': (base, 0.0)}
    rows.update({f'A|s2|{k}': (dict(base, **{k: v}), m) for k, v, m in knobs})
    s = R.knob_sensitivity(rows, 'A|s2|prod', '2', ['disc'], 'H')
    # TP_PCT and MAX_SPREAD tie at 0.3: takeProfitPct is listed before maxSpread.
    assert s['a2_runs'] and s['top6'] == ['TENNIS_FAV_MIN', 'TENNIS_TP_PCT', 'TENNIS_MAX_SPREAD', 'TENNIS_HUNT_MIN_SIGNALS',
                                          'TENNIS_UNDERDOG_MAX', 'HARNESS_LOSER_STOP'], s['top6']
    assert not R.knob_sensitivity(rows, 'A|s2|prod', '2', ['disc', 'check'], 'H')['a2_runs']
    assert not R.knob_sensitivity(rows, 'A|s2|prod', '2', ['disc'], 'R')['a2_runs']
    assert not R.knob_sensitivity(rows, 'A|s2|prod', '1', ['disc'], 'H')['a2_runs']
    e = e2e()['summary']['sensitivity']
    assert e['baseline'] == 'A|s1|m0.01|f0.2|o0.01|w60' and e['ranking'] == ['TENNIS_CONF_MOMENTUM_CENTS'] and not e['a2_runs']


def test_explicit_baseline():
    root = tmpdir()
    units, shards, _ = build(root, families_b=False)
    out = os.path.join(root, 'out')
    r = run_report(units, shards, out, '--baseline', 'A|s1|m0.02|f0.2|o0.01|w60')
    assert r.returncode == 0, r.stderr[-2000:]
    with open(os.path.join(out, 'summary.json')) as fh:
        sv = strict_json(fh.read())['sensitivity']
    assert sv['baseline'] == 'A|s1|m0.02|f0.2|o0.01|w60' and sv['baseline_source'] == '--baseline'
    assert sv['knobs']['TENNIS_CONF_MOMENTUM_CENTS']['baseline_level'] == '0.02'
    out2 = os.path.join(root, 'out2')
    r2 = run_report(units, shards, out2, '--baseline', 'A|s2|nope')
    assert r2.returncode != 0 and 'no F1 config' in r2.stderr and not os.path.exists(out2)


_HOLD = {}
SPECS_HASH = 'f' * 64


def hold():
    """One H-HOLD scoring run of the frozen list HOLD_RUNS (pool hold, stage hold, family B with per-day placebo sums)."""
    if not _HOLD:
        root = tmpdir()
        units, shards, plan = build(root, pool='hold', stage='hold', b_day_placebo=True, meta_extra={'specsHash': SPECS_HASH})
        out = os.path.join(root, 'out')
        r = run_report(units, shards, out, '--plan', plan, pool='hold')
        assert r.returncode == 0, r.stderr[-3000:] + r.stdout[-2000:]
        with open(os.path.join(out, 'summary.json')) as fh:
            summary = strict_json(fh.read())
        with open(os.path.join(out, 'report.md')) as fh:
            report = fh.read()
        _HOLD.update(root=root, out=out, summary=summary, report=report, rows=read_registry(out), shards=shards, units=units, plan=plan,
                     matches=read_matches(shards), stderr=r.stderr)
    return _HOLD


def test_hold_rows_validate_and_carry_the_ho1_block():
    reg = registry_module()
    h = hold()
    rows = h['rows']
    assert rows and {r['family'] for r in rows} == {'tennis-ta-A', 'tennis-ta-B'}
    for r in rows:
        err, fl = reg.validate(r)
        assert err == [] and not any(f.startswith(('DEV:', 'G0:', 'G2:')) for f in fl), (r['arm'], err, fl)
        assert r['flags'] == [] and 'dev-choice' not in r['flags']
    v = subprocess.run([sys.executable, '-I', registry_path(), 'validate', os.path.join(h['out'], ROWS_FILE)], capture_output=True, text=True, timeout=120)
    assert v.returncode == 0 and 'INVALID' not in v.stdout and 'DEV:' not in v.stdout, v.stdout[-2000:]
    a = {r['arm']: r for r in rows if r['family'] == 'tennis-ta-A'}
    ctrl = a[CTRL + '|F1']
    assert ctrl['role'] == 'control' and 'heldout' not in ctrl and ctrl['verdict'].startswith('HO-1 control')
    # Every paired row (a control link: candidates, neighbours, coin placebos, family B candidates) has the registry's HO-1
    # block; a control and a family B placebo row (the B candidate's control) have none.
    for r in rows:
        if not r.get('control'):
            assert 'heldout' not in r and (r['role'] == 'control' or r['family'] == 'tennis-ta-B'), r['arm']
            continue
        hb = r['heldout']
        assert hb['standard'] == 'HO-1' and hb['tier'] == 'history' and hb['days'] == 96 and hb['folds'] == 6 and hb['replay_version'] == 8, r['arm']
    win, lose = a['A|s2|fm0.65|F1'], a['A|s2|tp0.2|F1']
    assert win['role'] == lose['role'] == 'candidate' and win['control'] == lose['control'] == ctrl['trial_id']
    assert reg.ho1_pass(win['heldout'], 'tennis', 'replay')[0] and win['verdict'] == 'HO-1 pass', win['heldout']
    ok, why = reg.ho1_pass(lose['heldout'], 'tennis', 'replay')
    assert not ok and lose['verdict'] == f'HO-1 fail: {why}'
    assert win['heldout']['beats_placebo'] is True and win['heldout']['terciles_covered'] == 2 and win['heldout']['terciles_won'] == 2
    assert win['heldout']['folds_won'] == 6 and lose['heldout']['folds_won'] == 0
    # The rows as a fresh ho1_fill over the file would fill them (the block is the registry's, not the report's).
    again = reg.ho1_fill([{k: v for k, v in r.items() if k != 'heldout'} for r in rows])
    assert {r['arm']: r.get('heldout') for r in again} == {r['arm']: r.get('heldout') for r in rows}
    s = h['summary']['registry']
    assert s['ho1']['A|s2|fm0.65|F1']['pass'] and not s['ho1']['A|s2|tp0.2|F1']['pass']


def test_hold_rows_carry_placebo_for_terciles_base_and_replay_version():
    h = hold()
    rows = h['rows']
    a = {r['arm']: r for r in rows if r['family'] == 'tennis-ta-A'}
    for arm, r in a.items():
        assert r['base'] == 'tennis-ta@' + SHA and r['base_defaults'] == {'TENNIS_TRAIL_RATCHET': False}, arm
        assert r['data']['replay_version'] == replay_version_in_code() and r['data']['engine'] == 'replay'
        assert set(r['by_tercile']) == {'ATP', 'WTA'} and all(set(x) == {'pnl', 'hours'} and x['hours'] >= 100 for x in r['by_tercile'].values())
        # Every hold match is ATP or WTA: the tours add up to the row's by_day total.
        assert abs(sum(x['pnl'] for x in r['by_tercile'].values()) - sum(r['by_day'].values())) < 1e-4, arm
        if arm.endswith('|coin'):
            assert r['role'] == 'placebo' and r['placebo_for'] == arm.rsplit('|', 1)[0] + '|F1' and r['seed'] == 20261105
        else:
            assert 'placebo_for' not in r
    # The tour hours are the live-match hours of that tour's scored hold matches (close minus the published start).
    ml = [m for m in h['matches'] if m['pool'] == 'hold' and m['day'] <= H_HOLD[1] and m['trades'] > 0]
    for t, series in (('ATP', 'KXATPMATCH'), ('WTA', 'KXWTAMATCH')):
        want = sum(m['close'] - m['start'] for m in ml if m['series'] == series) / HOUR
        assert abs(a[CTRL + '|F1']['by_tercile'][t]['hours'] - want) < 1e-6, t
    b = {r['arm']: r for r in rows if r['family'] == 'tennis-ta-B'}
    rule = 'B|RSI14L|1m|exitExt|follow|tp30sl30'
    assert b[rule + '|placebo']['placebo_for'] == rule and b[rule]['control'] == b[rule + '|placebo']['trial_id']
    assert 'by_tercile' not in b[rule] and b[rule]['base'] == 'tennis-ta@' + SHA


def test_hold_by_day_is_every_hold_day_and_hours_are_h_hold():
    h = hold()
    days = all_hold_days()
    assert len(days) == 96
    for r in h['rows']:
        assert sorted(r['by_day']) == r['data']['days'] == days, r['arm']
    # Zero on a day without a trade: the fixture's no-tape match days still count, and the sums match the cells.
    s = h['summary']
    assert s['registry']['days'] == 96 and s['h_hold'] == list(H_HOLD)
    # The plan gives the swept weeks whole (Jul 27 to Nov 9); H-HOLD's window keeps Aug 1 00:00 to Nov 5 00:00 UTC.
    assert abs(s['pool_hours'] - 96 * 24) < 1e-6 and all(r['hours'] == s['pool_hours'] for r in h['rows'])
    # The match starting on Nov 5 UTC before the cutoff is pool hold but no H-HOLD match: left out and counted.
    late = [m for m in h['matches'] if m['day'] > H_HOLD[1] and m['pool'] == 'hold']
    assert len(late) == 1 and late[0]['fold'] is None and s['hold']['matches_after_hold'] == 1
    assert s['matches'] == sum(1 for m in h['matches'] if m['pool'] == 'hold' and m['day'] <= H_HOLD[1] and m['trades'] > 0)
    assert "after H-HOLD's last day" in h['report']
    assert s['excluded'] == {p: sum(1 for m in h['matches'] if m['pool'] == p) for p in ('nostart', 'disc', 'embargo', 'out')}, s['excluded']


def test_hold_folds_equal_the_registry_edges():
    reg = registry_module()
    h = hold()
    assert tuple(reg.H_HOLD) == H_HOLD
    edges = R.ho1_fold_edges(tuple(reg.H_HOLD))
    days = all_hold_days()
    # The report's folds are the registry's: each day's fold by the registry's own formula, and 16 days each.
    assert [R.ho1_fold_of(d, edges) for d in days] == [registry_fold(d) for d in days]
    assert [sum(1 for d in days if registry_fold(d) == k) for k in range(1, 7)] == [16] * 6
    # ... and as ho1_fill itself cuts them: a gain of -1 on one report fold's days only gives the registry a fold of exactly
    # -1 $/day, for every fold (so each registry fold lies inside one report fold, and the two partitions are the same).
    base = {'thread': 't', 'family': 'f', 'code_sha': 's', 'data': {'source': 'history', 'days': days, 'replay_version': 8}}
    for k in range(1, 7):
        rows = [dict(base, trial_id='c', arm='C', role='control', by_day={d: 0.0 for d in days}),
                dict(base, trial_id='x', arm='X', role='candidate', control='c',
                     by_day={d: (-1.0 if R.ho1_fold_of(d, edges) == k else 0.0) for d in days})]
        hb = reg.ho1_fill(rows)[1]['heldout']
        assert abs(hb['worst_fold_per_hour'] + 1 / 24) < 1e-12 and hb['folds_won'] == 0, (k, hb)
    # The summary, the report and every fixture match say the same folds.
    s = h['summary']
    assert [(f['from'], f['to']) for f in s['ho1_folds']] == edges and s['folds'] == ['1', '2', '3', '4', '5', '6']
    assert [f['days'] for f in s['hold']['folds']] == [16] * 6
    assert all(m['fold'] == registry_fold(m['day']) for m in h['matches'] if m['pool'] == 'hold')
    assert 'HO-1 folds of H-HOLD' in h['report'] and '6: 2026-10-20 to 2026-11-04' in h['report']
    # The matchList check: a hold match's fold must be the registry's, any other row's null; a row without the key (an older
    # sweep) and a hold match after H-HOLD's last day (no H-HOLD match, left out) are not read.
    fp = R.fold_problems
    assert fp([{'pool': 'hold', 'day': '2026-08-16', 'fold': 1}, {'pool': 'hold', 'day': '2026-08-17', 'fold': 2}], edges) == []
    assert fp([{'pool': 'hold', 'day': '2026-08-16', 'fold': 2}], edges) and fp([{'pool': 'disc', 'day': '2026-07-01', 'fold': 1}], edges)
    assert fp([{'pool': 'hold', 'day': '2026-08-16', 'fold': True}], edges) and fp([{'pool': 'hold', 'day': '2026-08-16', 'fold': None}], edges)
    assert fp([{'pool': 'hold', 'day': '2026-11-05', 'fold': 6}, {'pool': 'hold', 'day': '2026-08-01'}], edges) == []


def test_hold_report_scores_each_candidate_once():
    h = hold()
    s, rep = h['summary'], h['report']
    assert '### H-HOLD score (HO-1, once per frozen spec list)' in rep and SPECS_HASH in rep
    hs = s['hold']
    assert hs['specs_sha'] == SPECS_HASH and hs['spec_ids'] == sorted(r[0] for r in HOLD_RUNS) and hs['control'] == CTRL + '|F1'
    c = {x['arm']: x for x in hs['candidates']}
    assert set(c) == {'A|s2|fm0.65|F1', 'A|s2|tp0.2|F1'}
    win, lose = c['A|s2|fm0.65|F1'], c['A|s2|tp0.2|F1']
    assert len(win['folds']) == 6 and all(f['gain_per_hour'] > 0 for f in win['folds']) and win['folds_won'] == 6
    assert lose['folds_won'] == 0 and lose['worst_fold_per_hour'] < 0
    assert all(win['tours'][t]['gain_per_live_hour'] > 0 for t in ('ATP', 'WTA'))
    assert win['placebo']['beats'] and win['placebo']['arm'] == 'A|s2|fm0.65|coin' and win['placebo']['p'] is not None
    assert win['neighbour']['arm'] == 'A|s2|fm0.65|F2' and win['neighbour']['gain'] > 0
    # The report's fold figures add up to the paired by_day gain of the rows.
    rows = {r['arm']: r for r in h['rows']}
    g = {d: rows['A|s2|fm0.65|F1']['by_day'][d] - rows[CTRL + '|F1']['by_day'][d] for d in all_hold_days()}
    assert abs(sum(f['gain'] for f in win['folds']) - sum(g.values())) < 1e-4 and abs(win['gain'] - sum(g.values())) < 1e-4
    assert win['ho1']['pass'] and not lose['ho1']['pass'] and win['ho1']['heldout'] == rows['A|s2|fm0.65|F1']['heldout']
    assert '| A\\|s2\\|fm0.65\\|F1 |' in rep and 'ho1_pass PASS' in rep and 'ho1_pass FAIL' in rep
    # registry.py ho1_fill counts H-HOLD's last day twice in fold 6: where that moves its worst fold, the report says so.
    for x in (win, lose):
        f6 = x['folds'][-1]
        assert 'gain_per_hour_registry' in f6
        if abs(min([f['gain_per_hour'] for f in x['folds'][:-1]] + [f6['gain_per_hour_registry']]) - x['ho1']['heldout']['worst_fold_per_hour']) < 1e-9 \
                and abs(x['worst_fold_per_hour'] - x['ho1']['heldout']['worst_fold_per_hour']) > 1e-9:
            assert any('counts H-HOLD' in d for d in x['registry_differs']), x['registry_differs']
    assert 'descriptive on H-HOLD' in rep and 'Era rule (C9' in rep


def _hold_refused(mutate=None, *extra, registry=None, **build_kw):
    root = tmpdir()
    units, shards, plan = build(root, pool='hold', stage='hold', families_b=False, **build_kw)
    if mutate:
        mutate(shards, plan)
    out = os.path.join(root, 'out')
    reg = ['--registry-py', registry or registry_path(), '--sha', SHA]
    r = subprocess.run([sys.executable, SCRIPT, '--shards', shards, '--pool', 'hold', '--run', '4242', '--out', out, '--units', units,
                        '--boot', '49', *reg, *extra], capture_output=True, text=True, timeout=600)
    assert r.returncode != 0, r.stdout[-2000:]
    assert not os.path.exists(out)
    return r.stderr


def _rewrite_matches(shards, fn):
    for f in os.listdir(shards):
        p = os.path.join(shards, f)
        with gzip.open(p, 'rt') as fh:
            d = json.load(fh)
        for m in d['matchList']:
            fn(m)
        with gzip.open(p, 'wt') as fh:
            json.dump(d, fh)


def test_hold_runs_refuse_wrong_folds_lists_and_registries():
    # A fold that is not the registry's (the sweep cut its edges another way).
    def shift(m):
        if m['pool'] == 'hold' and m['day'] == '2026-08-16':
            m['fold'] = 2
    err = _hold_refused(lambda s, p: _rewrite_matches(s, shift))
    assert "disagree with the registry's HO-1 fold edges" in err and '2026-08-16' in err
    # The plan's holdFolds must be the registry's too.
    def plan_folds(s, p):
        with open(p) as fh:
            pl = json.load(fh)
        pl['holdFolds'] = [{'fold': i + 1, 'from': a_, 'to': b_} for i, (a_, b_) in enumerate(R.ho1_fold_edges(('2026-08-01', '2026-11-05')))]
        with open(p, 'w') as fh:
            json.dump(pl, fh)
    root = tmpdir()
    units, shards, plan = build(root, pool='hold', stage='hold', families_b=False)
    plan_folds(shards, plan)
    out = os.path.join(root, 'out')
    r = run_report(units, shards, out, '--plan', plan, pool='hold', boot=49)
    assert r.returncode != 0 and "holdFolds" in r.stderr and not os.path.exists(out), r.stderr[-1000:]
    # A frozen list without a candidate's coin placebo, or without the production control.
    no_coin = [x for x in HOLD_RUNS if x[0] != 'A|s2|tp0.2|coin']
    err = _hold_refused(runs_def=no_coin)
    assert 'frozen hold list' in err and 'A|s2|tp0.2|F1' in err and 'coin' in err
    no_ctrl = [x for x in HOLD_RUNS if not x[0].startswith(CTRL)]
    assert 'production-default F1 control' in _hold_refused(runs_def=no_ctrl)
    # A registry module without ho1_fill / ho1_pass cannot give the heldout block.
    root = tmpdir()
    old_reg = os.path.join(root, 'registry_v0.py')
    with open(registry_path()) as fh:
        src = fh.read()
    with open(old_reg, 'w') as fh:
        fh.write(src.replace('def ho1_fill(', 'def _no_ho1_fill('))
    assert 'ho1_fill' in _hold_refused(registry=old_reg)
    # A replay version in the metas that is not the code's.
    assert 'REPLAY_VERSION' in _hold_refused(meta_extra={'replayVersion': replay_version_in_code() - 1})
    # Pool hold needs stage hold, and stage hold scores pool hold only.
    root = tmpdir()
    units, shards, _ = build(root, pool='hold', stage='2', families_b=False)
    out = os.path.join(root, 'out')
    r = run_report(units, shards, out, pool='hold', boot=49)
    assert r.returncode != 0 and "only by stage 'hold'" in r.stderr and not os.path.exists(out)
    assert 'scores pool' in R.pool_refusal(['disc'], 'hold') and R.pool_refusal(['hold'], 'hold') is None


def test_shared_base_defaults():
    assert R.shared_base_defaults([PROD, WIN, LOSE, dict(PROD, TENNIS_END_LOSER_CUT=False)]) == {'TENNIS_TRAIL_RATCHET': False}
    # by value: a key every spec writes at production's default is no base default; a shared non-default one is
    assert R.shared_base_defaults([dict(PROD, TENNIS_FAV_MIN='0.65'), dict(PROD, TENNIS_FAV_MIN=0.65, TENNIS_TP_PCT=0.2)]) == \
        {'TENNIS_FAV_MIN': '0.65', 'TENNIS_TRAIL_RATCHET': False}
    assert R.shared_base_defaults([{'TENNIS_TRAIL_RATCHET': 'false'}, {}]) == {} and R.shared_base_defaults([]) == {}
    assert R.shared_base_defaults([{}]) == {}


def test_knob_defaults_match_production():
    # The defaults the report compares overrides against must be production's (bot/config.ts) and the sim's harness rules.
    import re
    with open(os.path.join(REPO, 'bot', 'config.ts')) as fh:
        cfg = fh.read()
    with open(os.path.join(REPO, 'research', 'tennisTaSweep.ts')) as fh:
        sweep = fh.read()
    for key, want in R.KNOB_DEFAULTS.items():
        if key.startswith('HARNESS_'):
            m = re.search(r"h\('%s', ([^)]+)\)" % key, sweep)
            assert m, f'{key}: no default in tennisTaSweep.ts'
            got = m.group(1).strip().strip("'")
        else:
            m = re.search(r"(?:num|bool)\(env, '%s', ([^,)]+)" % key, cfg)
            assert m, f'{key}: not read by bot/config.ts'
            got = m.group(1).strip()
        assert R.knob_val(key, got) == R.knob_val(key, want), (key, got, want)


def test_unit_folds_never_split_a_unit():
    t = R.ms_of('2025-08-25T05:00:00Z')  # Monday; the week's last day is Sunday Aug 31
    assert R.unit_fold({'start': t, 'end': t + 7 * DAY}) == '2025-08'
    t2 = R.ms_of('2025-03-31T05:00:00Z')  # six of its seven days are in April
    assert R.unit_fold({'start': t2, 'end': t2 + 7 * DAY}) == '2025-04'


def test_clean_makes_json_strict():
    s = R.dumps({'a': float('nan'), 'b': [float('inf'), np.float32(1.5), np.int64(2)], 'c': np.bool_(True)})
    assert strict_json(s) == {'a': None, 'b': [None, 1.5, 2], 'c': True}


if __name__ == '__main__':
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith('test_') and callable(v)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f'ok   {name}')
        except Exception as ex:  # noqa: BLE001
            failed += 1
            print(f'FAIL {name}: {type(ex).__name__}: {ex}')
    print(f'{len(tests) - failed} passed, {failed} failed')
    sys.exit(1 if failed else 0)
