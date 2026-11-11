#!/usr/bin/env python3
"""research/tennis_ta_report.py end to end on synthetic shard sets (contract C4): two shards x two sub-slices, measuring
sticks, F1 / F2 / coin arms, 'nostart', 'old', 'embargo' and 'hold' rows beside the pool's (C9), and a family B export;
an H-DEV choice run (pool disc), an H0 stress run (pool old) and an H-HOLD scoring run of a frozen list (pool hold, stage
hold, C10); the registry v1 rows (C7 / C11) are checked with the project's research/registry.py (make_id, validate,
ho1_fill, ho1_pass). The one test (Amendment 4): shard sets with the window arms and the C12 'window' block give the
league (league.md / .csv / .json, hold-batch-candidate.json), the read of a batch at stage hold (hold-league.md / .json,
the rows' one-test heldout block) and gap_stats against the hand-computed fixture of tests/tennisTaWindow.test.ts.

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
# The fixture runs carry their own era (meta.era wins over the module defaults); it starts a week after the pinned
# START_ERA_FROM (Apr 20) so the synthetic unit table needs no Apr 20 week.
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
    assert R.unit_pools(u('2025-06-16T05:00:00Z')) == {'old'} and R.unit_pools(u('2026-04-13T05:00:00Z')) == {'old'}
    assert R.unit_pools(u('2025-08-11T05:00:00Z', sealed=True)) == {'old'}  # the legacy seal is ignored (C9)
    # The start era seals nothing; its pools are per match, so a week can hold several.
    assert R.unit_pools(u('2026-04-20T05:00:00Z')) == {'disc'} and R.unit_pools(u('2026-05-04T05:00:00Z', sealed=True)) == {'disc'}
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
        # No batch: the retired frozen-list design (C10); --hold-batch keeps a checkout's research/tennis-ta/hold-batch.json out of it.
        r = run_report(units, shards, out, '--plan', plan, '--hold-batch', os.path.join(root, 'no-batch.json'), pool='hold')
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
        # The block's replay version is the data's (data.replay_version: the shard meta's replayVersion, which the sweep sets from
        # the code's REPLAY_VERSION), never a literal: main bumped historyReplay.ts to 9 after this test pinned 8.
        assert hb['standard'] == 'HO-1' and hb['tier'] == 'history' and hb['days'] == 96 and hb['folds'] == 6 \
            and hb['replay_version'] == replay_version_in_code() == r['data']['replay_version'], r['arm']
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
    if '--hold-batch' not in extra:
        extra = (*extra, '--hold-batch', os.path.join(root, 'no-batch.json'))
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
    r = run_report(units, shards, out, '--plan', plan, '--hold-batch', os.path.join(root, 'no-batch.json'), pool='hold', boot=49)
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


# ---------------------------------------------------------------------------------------------------------------------
# The one test (Amendment 4): the 'window' block (contract C12), gap_stats, the league, the batch, the read and the rows

W_RATES = {  # config -> (underdog window rate, fav window rate, random rate); the coin placebo runs at the random rate
    'A|s1|m0.01|f0.2|o0.01|w60': (0.75, 0.55, 0.25),
    'A|s1|m0.02|f0.2|o0.01|w60': (0.35, 0.30, 0.25),
    'A|s1|m0.005|f0.05|o0.005|w120': (0.25, 0.25, 0.25),
    'A|s1|prod|settlehold': (0.50, 0.50, 0.25),
}
BW_RATES = {'RSI14L|1m|follow': (0.6, 0.25), 'MACD|5m|fade': (0.25, 0.25)}  # family B reading|bar|dir -> (window rate, random rate)
HIST_N = {k: len(v) + 1 for k, v in R.HIST_EDGES.items()}


def window_arm_runs(configs, n_matches, coin=True):
    """The |window (and |coinwindow) runs of configs [(id, overrides, stick)]: window: true, fill F1, no P&L, no episodes."""
    runs = []
    for cid, ov, stick in configs:
        base = {'overrides': ov, 'fill': 'F1', 'stratum': 'H', 'days': [], 'pnl': [0.0] * n_matches, 'episodes': [], 'window': True}
        runs.append(dict(base, id=f'{cid}|window', **({'stick': True} if stick else {})))
        if coin and not stick:
            runs.append(dict(base, id=f'{cid}|coinwindow', placebo='coin'))
    return runs


def window_row(rid, leg, matches, rate, random, rng, phase_of, twins_of=None):
    """One C12 row: an instance in 4 of 5 matches with a tape, 3 twins an instance (twins_of(i) of them when given: a coin
    side with no eligible minute draws none, Amendment 4 item 5, so tn_i falls short of 3 n_i), windows at `rate`, twin
    windows at `random`; the histograms hold the windows (tWin, lenWin) and the instances (dip, held), the phases split the
    counts."""
    n, w, tn, tw = [], [], [], []
    hist = {k: [0] * HIST_N[k] for k in R.HIST_EDGES}
    by_phase = {ph: [0, 0] for ph in R.PHASES}
    for i, m in enumerate(matches):
        has = m['trades'] > 0 and (i + {'underdog': 0, 'fav': 1}.get(leg, 2)) % 5 != 2
        ni = 1 if has else 0
        wi = int(rng.random() < rate) if has else 0
        k = twins_of(i) if twins_of else 3
        tni = k * ni
        twi = int(rng.binomial(k, random)) if has else 0
        n.append(ni)
        w.append(wi)
        tn.append(tni)
        tw.append(twi)
        if has:
            ph = phase_of(i)
            by_phase[ph][0] += ni
            by_phase[ph][1] += wi
            hist['dip'][3] += 1  # (-0.03, -0.02]
            hist['held'][2 if wi else 0] += 1
            if wi:
                hist['tWin'][3] += 1  # [3, 5) minutes
                hist['lenWin'][2] += 1  # [2, 3)
    sn, sw = sum(n), sum(w)
    return {'id': rid, 'leg': leg, 'n': n, 'w': w, 'tn': tn, 'tw': tw, 'hist': hist, 'byPhase': by_phase, 'endNoWin': sn - sw,
            'asks': [sn, round(0.35 * sn, 6)]}


def with_window(shards, configs, seed=11, batch=None, family_b=True, rates=W_RATES, coin=True, short=()):
    """Rewrite a built shard set with the window arms' runs and the C12 'window' block (and familyBWindow): one row per
    window arm and leg (the coin placebo arms too unless coin is False: the read runs none); the batch (meta.batch /
    batchHash / leagueRun) on a hold run. The fav leg of a config in `short` draws 2 twins on every third instance (item 5:
    a coin side with no eligible minute draws no twin), so its pooled rates' difference is not the item 6 gap."""
    rng = np.random.default_rng(seed)
    for f in sorted(os.listdir(shards)):
        p = os.path.join(shards, f)
        with gzip.open(p, 'rt') as fh:
            d = json.load(fh)
        ml = d['matchList']
        d['runs'] += window_arm_runs(configs, len(ml), coin)
        events = [{'event': m['event'], 'series': m['series'], 'tour': 'WTA' if 'WTA' in m['series'] else 'ATP', 'unit': m['unit'], 'day': m['day'],
                   'start': m['start'], 'close': m['close'], 'endRule': m['close'] - 30 * 60_000} for m in ml]
        rows = []
        phase_of = lambda i: R.PHASES[i % 5]  # noqa: E731
        for cid, _ov, stick in configs:
            ru, rf, rr = rates[cid]
            for leg, rate in (('underdog', ru), ('fav', rf)):
                twins_of = (lambda i: 2 if i % 3 == 0 else 3) if (cid in short and leg == 'fav') else None
                rows.append(window_row(f'{cid}|window', leg, ml, rate, rr, rng, phase_of, twins_of))
                if coin and not stick:
                    rows.append(window_row(f'{cid}|coinwindow', leg, ml, rr, rr, rng, phase_of))
        d['window'] = {'version': 'tennis-ta-window/1', 'settleFrac': 0.30, 'orderUsd': 10, 'twins': 3, 'seed': 20261105, 'events': events, 'rows': rows}
        if family_b and 'B' in d['meta']['families']:
            brows = [window_row(bid, None, ml, r_, rr_, rng, phase_of) for bid, (r_, rr_) in sorted(BW_RATES.items())]
            for b in brows:
                b.pop('leg')
            d['familyBWindow'] = {'version': 'tennis-ta-window/1', 'rows': brows}
        d['meta']['windowVersion'] = 'tennis-ta-window/1'
        if batch is not None:
            d['meta'].update(batch=batch, batchHash='ab' * 32, leagueRun='777')
        with gzip.open(p, 'wt') as fh:
            json.dump(d, fh)


def window_arrays(shards, pool, rid, leg, day_lo=None, day_hi=None):
    """The merged per-event arrays of a window row over the pool's matches (the test's own merge, from the files)."""
    n, w, tn, tw, ev = [], [], [], [], []
    for f in sorted(os.listdir(shards)):
        with gzip.open(os.path.join(shards, f), 'rt') as fh:
            d = json.load(fh)
        row = next(r for r in d['window']['rows'] + (d.get('familyBWindow') or {}).get('rows', []) if r['id'] == rid and r.get('leg') == leg)
        for i, m in enumerate(d['matchList']):
            if m['pool'] != pool or (day_lo and not (day_lo <= m['day'] <= day_hi)):
                continue
            n.append(row['n'][i])
            w.append(row['w'][i])
            tn.append(row['tn'][i])
            tw.append(row['tw'][i])
            ev.append(d['window']['events'][i])
    return n, w, tn, tw, ev


STAGE_WINDOW = [('A|s1|m0.01|f0.2|o0.01|w60', PROD, False), ('A|s1|m0.02|f0.2|o0.01|w60', BREACH, False),
                ('A|s1|m0.005|f0.05|o0.005|w120', NULL, False), ('A|s1|prod|settlehold', dict(PROD, TENNIS_END_LOSER_CUT=False), True)]
_LEAGUE = {}


def league():
    """One disc run with the window arms and the C12 block beside STAGE_RUNS: the league of Amendment 4."""
    if not _LEAGUE:
        root = tmpdir()
        units, shards, plan = build(root)
        with_window(shards, STAGE_WINDOW)
        out = os.path.join(root, 'out')
        r = run_report(units, shards, out, '--plan', plan)
        assert r.returncode == 0, r.stderr[-3000:] + r.stdout[-2000:]
        with open(os.path.join(out, 'summary.json')) as fh:
            summary = strict_json(fh.read())
        with open(os.path.join(out, 'league.json')) as fh:
            lg = strict_json(fh.read())
        with open(os.path.join(out, 'league.md')) as fh:
            md = fh.read()
        with open(os.path.join(out, 'report.md')) as fh:
            report = fh.read()
        with open(os.path.join(out, 'hold-batch-candidate.json')) as fh:
            cand = strict_json(fh.read())
        _LEAGUE.update(root=root, out=out, shards=shards, summary=summary, league=lg, md=md, report=report, cand=cand, rows=read_registry(out),
                       matches=read_matches(shards))
    return _LEAGUE


def test_gap_stats_agrees_with_the_ts_fixture():
    # tests/tennisTaWindow.test.ts: match 1 n 2 w 2 tn 6 tw 2 (d 2/3), match 2 1/0/3/1 (d -1/3), match 3 1/1/3/0 (d 1):
    # gap 0.5, SE sqrt(38) / 24, z 1.9467 < 2.
    g = R.gap_stats([2, 1, 1], [2, 0, 1], [6, 3, 3], [2, 1, 0])
    assert (g['n'], g['w'], g['tn'], g['tw'], g['matches'], g['clustered']) == (4, 3, 12, 3, 3, 3)
    for got, want in ((g['rate'], 0.75), (g['random'], 0.25), (g['gap'], 0.5), (g['se'], math.sqrt(38) / 24), (g['z'], 0.5 / (math.sqrt(38) / 24))):
        assert abs(got - want) <= 1e-12, (got, want)
    assert g['pass'] is False
    # A pass: d = [5/6, 1, 1/3], weights 2: gap 13/18, SE sqrt(78) / 54, z 4.42.
    g = R.gap_stats([2, 2, 2], [2, 2, 1], [6, 6, 6], [1, 0, 1])
    assert abs(g['gap'] - 13 / 18) <= 1e-12 and abs(g['se'] - math.sqrt(78) / 54) <= 1e-12 and g['pass'] and 4.4 < g['z'] < 4.43
    # SE 0 (one contributing match, or identical d_i): the chance wobble cannot be measured, so no z and no pass whatever the
    # gap, exactly as the core's gapStats (Amendment 4a item 2; the registry refuses se 0 too); a match with instances but no
    # twin is pooled into the rates, not into the cluster gap; nothing at all; twins without instances; unequal lengths pad with 0.
    se0 = 'SE 0: the per-match differences do not vary (one contributing match, or identical ones), so the chance wobble cannot be measured'
    s = R.gap_stats([1, 0], [1, 0], [3, 0], [0, 0])
    assert (s['n'], s['w'], s['tn'], s['tw'], s['rate'], s['random'], s['gap'], s['se'], s['z'], s['pass']) == (1, 1, 3, 0, 1, 0, 1, 0, None, False)
    assert R.no_z_why(s) == se0
    s = R.gap_stats([1, 1, 1], [1, 1, 1], [3, 3, 3], [0, 0, 0])
    assert s['z'] is None and not s['pass'] and s['clustered'] == 3
    s = R.gap_stats([1, 1, 1], [0, 0, 0], [3, 3, 3], [3, 3, 3])
    assert (s['gap'], s['se'], s['z'], s['pass']) == (-1, 0, None, False)
    s = R.gap_stats([1, 2], [1, 1], [3, 6], [3, 3])
    assert (s['gap'], s['se'], s['z'], s['pass']) == (0, 0, None, False) and R.no_z_why(s) == se0
    s = R.gap_stats([1, 1], [1, 0], [3, 0], [0, 0])
    assert (s['n'], s['w'], s['tn'], s['tw'], s['rate'], s['random'], s['gap'], s['se'], s['z']) == (2, 1, 3, 0, 0.5, 0, 1, 0, None)
    assert R.no_z_why(R.gap_stats([1, 0], [1, 0], [0, 3], [0, 0])) == 'no contributing match (no match with both an instance and a twin)'
    # pass <=> gap >= 2 x SE wherever there is a z (the written rule), over a spread of fixtures.
    for args in (([2, 1, 1], [2, 0, 1], [6, 3, 3], [2, 1, 0]), ([2, 2, 2], [2, 2, 1], [6, 6, 6], [1, 0, 1]), ([3, 1], [1, 1], [9, 3], [2, 0])):
        s = R.gap_stats(*args)
        assert s['z'] is not None and s['pass'] == (s['gap'] >= 2 * s['se']), args
    s = R.gap_stats([], [], [], [])
    assert (s['n'], s['z'], s['pass']) == (0, None, False) and all(math.isnan(s[k]) for k in ('rate', 'gap', 'se'))
    s = R.gap_stats([0, 0], [0, 0], [3, 3], [1, 0])
    assert (s['n'], s['tn'], s['tw'], s['z'], s['pass']) == (0, 6, 1, None, False)
    s = R.gap_stats([2, 1, 1], [2, 0, 1], [6, 3, 3, 0], [2, 1])
    assert abs(s['gap'] - 0.5) <= 1e-12 and abs(s['se'] - math.sqrt(38) / 24) <= 1e-12
    # Every instance with its 3 twins and every match with a twin: the weighted rates are the pooled ones, nothing short.
    g = R.gap_stats([2, 1, 1], [2, 0, 1], [6, 3, 3], [2, 1, 0])
    assert (g['twins_short'], g['events_short']) == (0, 0) and abs(g['rate_weighted'] - g['rate']) <= 1e-12 and abs(g['random_weighted'] - g['random']) <= 1e-12
    # Twins short (item 5: a coin side with no eligible minute draws none): match 2 drew 4 of its 6. The item 6 gap is
    # (3 (2/3 - 3/9) + 2 (1/2 - 2/4) + 1 (1 - 0)) / 6 = 1/3 = rate_weighted 4/6 - random_weighted (3/3 + 2/2 + 0) / 6; the pooled
    # difference 4/6 - 5/16 = 0.3542 is another number.
    g = R.gap_stats([3, 2, 1], [2, 1, 1], [9, 4, 3], [3, 2, 0])
    assert (g['twins_short'], g['events_short'], g['clustered']) == (2, 1, 3)
    assert abs(g['gap'] - 1 / 3) <= 1e-12 and abs(g['rate_weighted'] - 4 / 6) <= 1e-12 and abs(g['random_weighted'] - 1 / 3) <= 1e-12
    assert abs(g['gap'] - (g['rate_weighted'] - g['random_weighted'])) <= 1e-12 and abs((g['rate'] - g['random']) - (4 / 6 - 5 / 16)) <= 1e-12
    assert abs((g['rate'] - g['random']) - g['gap']) > 0.02
    # A match with instances but no twin: all its twins short, pooled into the rates, not into the weighted ones.
    s = R.gap_stats([1, 1], [1, 0], [3, 0], [0, 0])
    assert (s['twins_short'], s['events_short'], s['rate_weighted'], s['random_weighted']) == (3, 1, 1.0, 0.0)
    s = R.gap_stats([1, 1], [1, 0], [0, 0], [0, 0])
    assert (s['twins_short'], s['events_short']) == (6, 2) and math.isnan(s['rate_weighted']) and math.isnan(s['random_weighted'])
    # The twins an instance are the block's (C12 twins): at 2 an instance nothing here is short.
    assert R.gap_stats([2], [1], [4], [1], twins=2)['twins_short'] == 0


def test_an_infinite_z_is_spelt_in_json_and_csv_and_ranks_first():
    # SE 0 with a gap (one contributing match): z = +inf as the core has it; JSON has no infinity, so league.json, hold-league.json
    # and the registry rows spell it '+inf' / '-inf' (z_json, spell_inf), the tables print it (_zf), the verdict names it, and the
    # league ranks it first (z, ties by gap), a -inf z last among the rows with a z, rows without a z after them.
    assert R.z_json(math.inf) == '+inf' and R.z_json(-math.inf) == '-inf' and R.z_json(1.5) == 1.5 and R.z_json(None) is None
    assert R.z_json(float('nan')) is None and R.z_json('+inf') == '+inf'
    row = {'z': math.inf, 'by_tour': {'ATP': {'z': -math.inf, 'gap': -0.5}, 'WTA': {'z': None}}, 'gap': 1.0, 'se': 0.0}
    out = json.loads(R.dumps(R.spell_inf(row)))
    assert out == {'z': '+inf', 'by_tour': {'ATP': {'z': '-inf', 'gap': -0.5}, 'WTA': {'z': None}}, 'gap': 1.0, 'se': 0.0}
    assert json.loads(json.dumps(R.spell_inf(row), allow_nan=False))['z'] == '+inf'
    assert R._zf({'z': math.inf}) == '+inf' and R._zf({'z': -math.inf}) == '-inf' and R._zf({'z': None}) == '-' and R._zf({'z': 2.345}) == '2.35'
    # gap_stats itself never makes an infinite z since Amendment 4a item 2 (SE 0 -> no z): one match reads 'no z' in the
    # verdict, on the league and on the read alike; the spelling above stays for any infinite z a file may still carry.
    s = dict(R.gap_stats([1, 0], [1, 0], [3, 0], [0, 0]), hot_spot='x|fav')
    v = R.one_test_verdict(s)
    assert s['z'] is None and v.startswith('one test (information, no read): ') and 'no z (SE 0' in v
    assert R.one_test_verdict(s, read=True).startswith('not found: ') and 'no z (SE 0' in R.one_test_verdict(s, read=True)
    p = R.gap_stats([2, 2, 2], [2, 2, 1], [6, 6, 6], [1, 0, 1])
    assert R.one_test_verdict(p, read=True).startswith('direction found: ') and 'gap >= 2 x SE' in R.one_test_verdict(p)
    neg = R.gap_stats([2, 1, 1], [0, 0, 1], [6, 3, 3], [3, 1, 0])
    assert neg['z'] is not None and neg['z'] < 0 and 'gap < 2 x SE' in R.one_test_verdict(neg)
    rows = [{'id': 'b', 'leg': 'fav', 'z': 2.0, 'gap': 0.2}, {'id': 'a', 'leg': 'fav', 'z': math.inf, 'gap': 1.0}, {'id': 'd', 'leg': 'fav', 'z': None, 'gap': 0.0},
            {'id': 'c', 'leg': 'fav', 'z': -math.inf, 'gap': -1.0}, {'id': 'e', 'leg': 'fav', 'z': math.inf, 'gap': 0.5}]
    assert [r['id'] for r in R.rank_league(rows)] == ['a', 'e', 'b', 'c', 'd'] and [r['rank'] for r in rows] == [1, 2, 3, 4, 5]
    csv_row = R.league_csv_row({'family': 'A', 'hot_spot': 'x', 'id': 'x|window', 'config': 'x', 'leg': 'fav', 'stick': False, 'n': 1, 'w': 1, 'tn': 3,
                                'tw': 0, 'rate': 1.0, 'random': 0.0, 'gap': 1.0, 'se': 0.0, 'z': math.inf, 'pass': True, 'matches': 1, 'clustered': 1,
                                'n_all': 1, 'mean_ask': 0.5, 'hist': {k: {'q1': None, 'median': None, 'q3': None} for k in ('tWin', 'lenWin', 'dip', 'held')},
                                'end_no_window': 0, 'end_no_window_share': 0.0, 'by_phase': {}, 'coin': None,
                                'by_tour': {t: {'n': 0, 'w': 0, 'tn': 0, 'tw': 0, 'gap': float('nan'), 'se': float('nan'), 'z': None} for t in ('ATP', 'WTA')}})
    assert csv_row['z'] == '+inf' and csv_row['ATP_gap'] == '' and csv_row['ATP_z'] == ''
    assert 'no z without an instance, a twin or a contributing match, or on SE 0' in R.ONE_TEST_RULE and 'starting at or after the entry' in R.ONE_TEST_RULE
    assert 'inf' not in R.ONE_TEST_RULE


def test_one_test_block_carries_the_item_6_gap_and_the_registry_recomputes_the_same_pass():
    """Nov 11 finding: with an instance short of its 3 twins the pooled window rate - random rate is not the item 6 gap, and
    the block used to carry that pooled difference as gap beside item 6's SE and pass, so the registry's recomputed verdict
    (the one it uses) could differ from the row's. The block's rates are now item 6's weighted ones, gap their difference."""
    reg = registry_module()
    # n (1, 1, 1), tn (1, 1, 2): item 6 gap 0.5 >= 2 x SE 0.4714 (a pass); the pooled difference 1/3 (2/3 - 1/4 = 0.4167) is below it.
    g = R.gap_stats([1, 1, 1], [0, 1, 1], [1, 1, 2], [0, 0, 1])
    assert g['pass'] and abs(g['gap'] - 0.5) <= 1e-12 and (g['rate'] - g['random']) < 2 * g['se'] < g['gap']
    h = R.one_test_block(g, ['2026-08-%02d' % d for d in range(1, 11)], 8, 'x|both')
    assert abs(h['gap'] - g['gap']) <= 1e-12 and h['pass'] is True and abs(h['se'] - g['se']) <= 1e-12
    assert abs(h['gap'] - (h['window_rate'] - h['random_rate'])) <= 1e-12 and abs(h['window_rate'] - 2 / 3) <= 1e-12 and abs(h['random_rate'] - 1 / 6) <= 1e-12
    assert (h['n'], h['twins'], h['days'], h['replay_version'], h['twins_short'], h['matches'], h['clustered']) == (3, 4, 10, 8, 5, 3, 3)
    assert abs(h['window_rate_pooled'] - 2 / 3) <= 1e-12 and abs(h['random_rate_pooled'] - 1 / 4) <= 1e-12 and h['rates'].startswith('item 6')
    assert h['standard'] == 'one-test' and h['tier'] == 'history' and h['horizon'] == 'match' and h['hot_spot'] == 'x|both'
    assert reg.one_test_pass(h) == (True, '')
    # The old block (the pooled difference as gap) had the registry turn that pass into 'not found'.
    old = dict(h, window_rate=g['rate'], random_rate=g['random'], gap=g['rate'] - g['random'])
    assert not reg.one_test_pass(old)[0] and 'gap' in reg.one_test_pass(old)[1]
    # The finding's hand case: gap 1/3 against a pooled 0.3542, both a pass; the block and the registry agree on 1/3.
    g = R.gap_stats([3, 2, 1], [2, 1, 1], [9, 4, 3], [3, 2, 0])
    h = R.one_test_block(g, ['d'] * 96, 8, 'y|fav')
    assert abs(h['gap'] - 1 / 3) <= 1e-12 and abs(h['window_rate'] - 4 / 6) <= 1e-12 and abs(h['random_rate'] - 1 / 3) <= 1e-12 and reg.one_test_pass(h)[0]
    assert 'short of 3 an instance' in R.one_test_verdict(g, True) and "item 6's weighted" in R.one_test_verdict(g, True) and '+0.3542' in R.one_test_verdict(g, True)
    # Nothing short: the block's rates are the pooled ones and the verdict says nothing of twins.
    g = R.gap_stats([2, 2, 2], [2, 2, 1], [6, 6, 6], [1, 0, 1])
    h = R.one_test_block(g, ['d'], None, 'z|both')
    assert abs(h['window_rate'] - g['rate']) <= 1e-12 and abs(h['random_rate'] - g['random']) <= 1e-12 and h['twins_short'] == 0 and 'replay_version' not in h
    assert 'short of' not in R.one_test_verdict(g, True) and R.one_test_verdict(g, True).startswith('direction found: ')
    # No contributing match (no z): the pooled rates, their difference, se 0 and pass False; the registry refuses se 0 too.
    g = R.gap_stats([1, 1], [1, 0], [0, 0], [0, 0])
    h = R.one_test_block(g, ['d'], 8, 'w|underdog')
    assert (h['window_rate'], h['random_rate'], h['gap'], h['se'], h['pass'], h['twins'], h['twins_short']) == (0.5, 0.0, 0.5, 0.0, False, 0, 6)
    assert not reg.one_test_pass(h)[0] and R.one_test_verdict(g, True).startswith('not found: ') and 'no z (no twin)' in R.one_test_verdict(g, True)
    assert R.one_test_verdict(g, True).endswith('6 twin(s) short of 3 an instance over 2 match(es)')
    # Off pool old the verdict is information with no league.
    assert R.one_test_verdict(R.gap_stats([2, 2, 2], [2, 2, 1], [6, 6, 6], [1, 0, 1]), False, 'old').startswith('one test (information: pool old has no league')


def test_league_ranks_hot_spots_by_z_and_writes_the_files():
    e = league()
    s, lg = e['summary'], e['league']
    assert s['one_test']['run'] and s['one_test']['files'] == ['league.md', 'league.csv', 'league.json', 'hold-batch-candidate.json']
    assert all(os.path.exists(os.path.join(e['out'], f)) for f in s['one_test']['files'])
    A = lg['A']
    # One row per hot spot: config x leg, 'both' included, sticks included; ranked by z, ties by gap, rows without a z last.
    assert {(r['config'], r['leg']) for r in A} == {(c, leg) for c, _, _ in STAGE_WINDOW for leg in ('underdog', 'fav', 'both')}
    assert all(r['id'] == r['config'] + '|window' and r['hot_spot'] == f"{r['config']}|{r['leg']}" for r in A)
    zs = [r['z'] for r in A if r['z'] is not None]
    assert zs == sorted(zs, reverse=True) and [r['rank'] for r in A] == list(range(1, len(A) + 1))
    assert all(r['z'] is None for r in A[len(zs):])
    # The strong config leads, its underdog leg hottest; the null config has no pass.
    assert A[0]['config'] == 'A|s1|m0.01|f0.2|o0.01|w60' and A[0]['pass'] and A[0]['gap'] > 0.3
    assert not any(r['pass'] for r in A if r['config'] == 'A|s1|m0.005|f0.05|o0.005|w120')
    assert any(r['stick'] for r in A) and sum(1 for r in A if r['production']) == 3
    # Each row's one test is gap_stats over the pool's events of the file arrays (the test's own merge), to 1e-12; the 'both'
    # row is the per-event sum of the two legs.
    for r in A:
        legs = ['underdog', 'fav'] if r['leg'] == 'both' else [r['leg']]
        arrs = [window_arrays(e['shards'], 'disc', r['id'], leg) for leg in legs]
        n, w, tn, tw = ([sum(x) for x in zip(*[a[k] for a in arrs])] for k in range(4))
        g = R.gap_stats(n, w, tn, tw)
        assert (r['n'], r['w'], r['tn'], r['tw']) == (g['n'], g['w'], g['tn'], g['tw']), r['hot_spot']
        for k in ('rate', 'random', 'gap', 'se'):
            assert abs(r[k] - g[k]) <= 1e-12, (r['hot_spot'], k)
        assert (r['z'] is None) == (g['z'] is None) and (r['z'] is None or R.z_json(r['z']) == R.z_json(g['z'])
                                                          or abs(r['z'] - g['z']) <= 1e-12) and r['pass'] == g['pass']
        # By tour: the same over the tour's events; both tours add up to the row.
        ev = arrs[0][4]
        for t in ('ATP', 'WTA'):
            sel = [i for i, x in enumerate(ev) if x['tour'] == t]
            gt = R.gap_stats(*([a[i] for i in sel] for a in (n, w, tn, tw)))
            assert r['by_tour'][t]['n'] == gt['n']
            if gt['clustered']:
                assert abs(r['by_tour'][t]['gap'] - gt['gap']) <= 1e-12 and abs(r['by_tour'][t]['se'] - gt['se']) <= 1e-12
            else:
                assert r['by_tour'][t]['gap'] is None
        assert r['by_tour']['ATP']['n'] + r['by_tour']['WTA']['n'] == r['n']
        # Information columns (item 8): the binned quartiles, the phases, the end-rule share, the coin placebo, the F1 / F2 P&L.
        h = r['hist']
        assert h['tWin']['median'] == '3..5' and h['lenWin']['median'] == '2..3' and h['dip']['median'] == '-0.03..-0.02' and h['tWin']['total'] >= r['w']
        assert set(r['by_phase']) == set(PHASES_T) and sum(v['n'] for v in r['by_phase'].values()) == r['n_all'] >= r['n']
        assert r['end_no_window'] == r['n_all'] - sum(v['w'] for v in r['by_phase'].values()) and 0 <= r['end_no_window_share'] <= 1
        assert abs(r['mean_ask'] - 0.35) < 1e-6
        if r['stick']:
            assert r['coin'] is None and r['f2'] is None and r['f1']['arm'] == r['config'] + '|F1' and r['f1']['entries'] > 0
        else:
            assert r['coin']['id'] == r['config'] + '|coinwindow' and r['coin']['n'] > 0 and r['f1']['per_entry'] is not None and r['f2']['entries'] > 0
            assert abs(r['coin']['gap']) < 0.2  # the coin placebo runs at the random rate
    # Family B: its own table, no legs, no coin, no P&L columns.
    B = lg['B']
    assert [r['id'] for r in B] and all(r['leg'] is None and r['coin'] is None and r['f1'] is None for r in B)
    assert B[0]['config'] == 'RSI14L|1m|follow' and B[0]['pass']
    # league.csv: every row, one line each, with the information columns.
    with open(os.path.join(e['out'], 'league.csv')) as fh:
        lines = [x for x in fh.read().splitlines() if x]
    assert len(lines) == 1 + len(A) + len(B) and lines[0].startswith('family,rank,hot_spot,id,config,leg,stick,production,n,w,tn,tw,rate,random,gap,se,z,pass')
    assert all(c in lines[0].split(',') for c in ('t_win_median', 'dip_median', 'end_no_window_share', 'p3_rate', 'ATP_gap', 'WTA_z', 'coin_gap', 'f1_per_entry', 'f2_per_entry',
                                                   'twins_short', 'events_short', 'rate_weighted', 'random_weighted'))
    # Every instance of the fixture drew its 3 twins: nothing short, the weighted rates are the pooled ones (league.json).
    assert all(r['twins_short'] == 0 and r['events_short'] == 0 and abs(r['rate_weighted'] - r['rate']) <= 1e-12 for r in A + B if r['z'] is not None)
    # league.md: the top rows, the production legs and the stick, the rule, the batch instruction.
    md = e['md']
    assert "## The one test's league (Amendment 4)" in md and 'PASS = gap >= 2 x SE' in md and '| rank | hot spot | leg |' in md
    assert '(stick)' in md and '(production)' in md and 'Family B' in md and 'RSI14L' in md and '| twins short |' in md
    assert 'hold-batch-candidate.json' in md and 'research/tennis-ta/hold-batch.json' in md and 'calendar' in md and 'only then commits the hold request' in md
    assert 'measuring sticks are never in it' in md
    assert 'nothing in it cuts a hot spot' in md
    # report.md names the one test as the only bar and the discovery screen as information.
    rep = e['report']
    assert '### The one test (Amendment 4' in rep and 'league.md' in rep and 'Discovery screen (information' in rep and 'meet every discovery condition (information)' in rep


PHASES_T = ['pre', 'e20', 'p1', 'p2', 'p3']


def test_batch_candidate_is_the_ten_hottest_by_z_and_never_a_stick():
    e = league()
    A = e['league']['A']
    cand = e['cand']
    with_z = [r for r in A if r['z'] is not None]
    hot = [r for r in with_z if not r['stick']]
    # The settle-hold stick's three legs have a z and rank among the ten hottest, and still are not in the batch (item 1: a
    # hot spot is a config of the gradient matrix; C4: a stick is reported, never screened or counted): the batch is the
    # hottest non-stick rows, fewer than 10 when the league has fewer.
    assert len(with_z) >= 10 and sum(1 for r in with_z[:10] if r['stick']) >= 1 and 3 <= len(hot) <= 9
    assert cand['league_run'] == '4242' and set(cand) == {'league_run', 'batch'} and len(cand['batch']) == len(hot)
    assert cand['batch'] == [{'id': r['config'], 'leg': r['leg']} for r in hot[:10]]
    assert not any(m['id'].startswith('A|s1|prod|') for m in cand['batch'])
    assert all(not any(m['id'].endswith('|' + arm) for arm in R.ARMS) and m['leg'] in ('underdog', 'fav', 'both') for m in cand['batch'])
    assert e['league']['batch_candidate'] == cand
    # batch_candidate itself: a stick in the top ten is skipped and the next row taken; at most HOLD_BATCH_MAX; no z, no place.
    rows = [dict(config=f'c{i}', leg='both', z=20 - i, gap=0.5, stick=(i == 1)) for i in range(12)] + [dict(config='nz', leg='fav', z=None, gap=0.9, stick=False)]
    assert R.batch_candidate(rows, 'run9') == {'league_run': 'run9', 'batch': [{'id': f'c{i}', 'leg': 'both'} for i in [0] + list(range(2, 11))]}
    assert R.batch_candidate([dict(config='s', leg='both', z=9.0, gap=0.5, stick=True)], '1') == {'league_run': '1', 'batch': []}


def test_hold_batch_refuses_a_stick_and_a_league_off_another_pool():
    """Item 1: a hot spot of the batch is a config of the gradient matrix, never a measuring stick (C4); item 7: the league
    the batch is read off runs on pool disc only."""
    runs = {'A|s2|x|window': {'window': True}, 'A|s2|x|F1': {}, 'A|s2|y|window': {'window': True, 'stick': True}, 'A|s2|y|F1': {}}
    wd = {'rows': {('A|s2|x|window', 'underdog'): {}, ('A|s2|x|window', 'fav'): {}, ('A|s2|y|window', 'underdog'): {}, ('A|s2|y|window', 'fav'): {}}}
    assert R.hold_batch_problems([{'id': 'A|s2|x', 'leg': 'both'}], runs, wd) == []
    assert R.hold_batch_problems([{'id': 'A|s2|x', 'leg': 'both'}], runs, wd, 'disc') == []
    # A stick by its id (stage 1 or 2, the sweep's 'A|s<n>|prod|<name>') or by its |window run's tag.
    for sid in ('A|s1|prod|settlehold', 'A|s2|prod|nopacer', 'A|s2|y'):
        p = R.hold_batch_problems([{'id': sid, 'leg': 'underdog'}], runs, wd)
        assert len(p) == 1 and 'measuring stick' in p[0] and sid in p[0] and 'item 1' in p[0], p
    # A stated league pool that is not disc.
    p = R.hold_batch_problems([{'id': 'A|s2|x', 'leg': 'both'}], runs, wd, 'old')
    assert len(p) == 1 and 'pool old league' in p[0] and 'pool disc' in p[0] and 'item 7' in p[0]
    assert R.hold_batch_problems('x', runs, wd, 'old')[0].startswith('the batch was read off')
    # hold_batch_of carries the pool the source states (the file's league_pool, the metas' / plan's leaguePool), None otherwise.
    root = tmpdir()
    bfile = os.path.join(root, 'hold-batch.json')
    with open(bfile, 'w') as fh:
        json.dump({'league_run': '777', 'batch': HOLD_BATCH, 'league_pool': 'old'}, fh)
    b = R.hold_batch_of({}, None, bfile)
    assert b['league_pool'] == 'old' and b['batch'] == HOLD_BATCH and b['league_run'] == '777' and b['source'] == bfile
    with open(bfile, 'w') as fh:
        json.dump({'league_run': '777', 'batch': HOLD_BATCH}, fh)
    assert R.hold_batch_of({}, None, bfile)['league_pool'] is None
    assert R.hold_batch_of({'batch': HOLD_BATCH, 'leagueRun': '1', 'batchHash': 'h', 'leaguePool': 'disc'}, None, bfile)['league_pool'] == 'disc'
    assert R.hold_batch_of({}, {'batch': HOLD_BATCH, 'leagueRun': '1'}, bfile)['league_pool'] is None
    # End to end: a stick in the batch, and a batch file read off a pool old league, each refuse the read before scoring.
    def fixture(batch):
        return lambda s, p: with_window(s, HOLD_WINDOW, seed=5, batch=batch, family_b=False, rates=HOLD_RATES, coin=False)
    err = _hold_refused(fixture(HOLD_BATCH + [{'id': 'A|s1|prod|settlehold', 'leg': 'both'}]), runs_def=HOLD_BATCH_RUNS)
    assert 'measuring stick' in err and 'A|s1|prod|settlehold' in err and 'no registry rows' in err
    with open(bfile, 'w') as fh:
        json.dump({'league_run': '777', 'batch': HOLD_BATCH, 'league_pool': 'old'}, fh)
    err = _hold_refused(fixture(None), '--hold-batch', bfile, runs_def=HOLD_BATCH_RUNS)
    assert 'read off a pool old league' in err and 'no registry rows' in err


def test_pool_old_has_no_league_and_no_batch_candidate():
    """Item 7: the league runs on H-DEV (pool disc) only. A stage 2 pool old run with a window block scores the one test as
    information (summary.json, the registry rows) and writes no league file and no hold-batch-candidate.json."""
    root = tmpdir()
    units, shards, _ = build(root, families_b=False, pool='old', stage='2', t0='2025-07-07T05:00:00', replay_meta=False)
    with_window(shards, STAGE_WINDOW, family_b=False)
    out = os.path.join(root, 'out')
    r = run_report(units, shards, out, pool='old', boot=49)
    assert r.returncode == 0, r.stderr[-3000:] + r.stdout[-2000:]
    with open(os.path.join(out, 'summary.json')) as fh:
        s = strict_json(fh.read())
    ot = s['one_test']
    assert s['pools'] == ['old'] and ot['run'] and ot['rows_a'] == 12 and ot['with_z'] >= 10 and not ot['league'] and ot['league_pool'] == 'disc'
    assert ot['files'] == [] and 'pool disc' in ot['league_reason'] and 'item 7' in ot['league_reason'] and "pool old's one test is information" in ot['league_reason']
    assert not any(os.path.exists(os.path.join(out, f)) for f in ('league.md', 'league.csv', 'league.json', 'hold-batch-candidate.json', 'hold-league.md'))
    rows = read_registry(out)
    w = [x for x in rows if '|window|' in x['arm']]
    assert len(w) == 12 and all(x['verdict'].startswith('one test (information: pool old has no league') and 'heldout' not in x for x in w)
    assert all(x['raw']['gate'].startswith('one test (information: pool old has no league') for x in w)
    assert all(registry_module().validate(x)[0] == [] for x in w)
    with open(os.path.join(out, 'report.md')) as fh:
        rep = fh.read()
    assert 'No league: the league runs on H-DEV (pool disc) only (item 7)' in rep and 'league.md' not in rep.split('### The one test (Amendment 4')[1].split('\n')[1]


def test_league_registry_rows_are_one_per_hot_spot_with_the_gap_by_day_and_tour():
    reg = registry_module()
    e = league()
    rows = e['rows']
    wrows = {r['arm']: r for r in rows if '|window|' in r['arm']}
    crows = {r['arm']: r for r in rows if '|coinwindow|' in r['arm']}
    assert len(wrows) == 4 * 3 and len(crows) == 3 * 3
    A = {(r['config'], r['leg']): r for r in e['league']['A']}
    cfg_ov = {c: ov for c, ov, _ in STAGE_WINDOW}
    for arm, r in wrows.items():
        cfg, leg = arm.split('|window|')
        lr = A[(cfg, leg)]
        err, fl = reg.validate(r)
        assert err == [] and 'DEV:choice-only' in fl and 'G1:non-dollar-metric' in fl and not any(f.startswith('G0:') for f in fl), (arm, err, fl)
        assert r['family'] == 'tennis-ta-A' and r['contract_type'] == 'tennis' and r['role'] == 'candidate' and r['leg'] == leg and r['flags'] == ['dev-choice']
        assert r['data']['metric'] == 'window_gap' and r['data']['regime_proxy'] == 'tour' and r['data']['replay_version'] == replay_version_in_code()
        assert r['modules'] == (['exits'] if 'settlehold' in cfg else ['tennis-ta']) and r['env'] == cfg_ov[cfg]
        assert r['trial_id'] == reg.make_id(r['thread'], r['family'], r['arm'], r['code_sha'], r['data']['days'], r['seed'], [], r['env'])
        assert r['seed'] is None and 'heldout' not in r and r['fills'] == lr['n'] and r['markets'] == lr['matches']
        # by_day = the gap per UTC match day over the day set (0 on a day without one); by_tercile = the gap per tour.
        assert sorted(r['by_day']) == r['data']['days']
        for d, v in lr['by_day'].items():
            assert abs(r['by_day'][d] - (v['gap'] if v['gap'] is not None else 0.0)) < 1e-6, (arm, d)
        assert set(r['by_tercile']) == {'ATP', 'WTA'}
        for t in ('ATP', 'WTA'):
            assert r['by_tercile'][t]['n'] == lr['by_tour'][t]['n'] and abs(r['by_tercile'][t]['pnl'] - (lr['by_tour'][t]['gap'] or 0.0)) < 1e-6
        assert 'gap' in r['verdict'] and 'SE' in r['verdict'] and r['verdict'].startswith('one test (league, information')
        assert r['raw']['one_test']['z'] == lr['z'] and r['raw']['gate'].startswith('league')
        if 'settlehold' in cfg:
            assert 'control' not in r
        else:
            c = crows[f'{cfg}|coinwindow|{leg}']
            assert r['control'] == c['trial_id'] and c['placebo_for'] == arm and c['role'] == 'placebo' and c['seed'] == 20261105
            assert reg.validate(c)[0] == [] and 'control' not in c and c['verdict'].startswith('coin placebo of the one test')
    # The P&L rows are as before: the window arms never become P&L cells or rows.
    assert not any(r['arm'].endswith('|window') or r['arm'].endswith('|coinwindow') for r in rows)
    assert len([r for r in rows if r['family'] == 'tennis-ta-A' and '|window|' not in r['arm'] and '|coinwindow|' not in r['arm']]) == 11
    assert e['summary']['registry']['one_test_rows'] == 21 and e['summary']['f1_cells'] == league_f1_cells(e)


def league_f1_cells(e):
    with gzip.open(os.path.join(e['out'], 'cells.json.gz'), 'rt') as fh:
        cells = strict_json(fh.read())
    assert not any('window' in c['run'] for c in cells)
    return sum(1 for c in cells if c['arm'] == 'F1')


HOLD_BATCH_RUNS = [(CTRL + '|F1', PROD, 'F1', None, False, 0.0), ('A|s2|fm0.65|F1', WIN, 'F1', None, False, 0.5), ('A|s2|tp0.2|F1', LOSE, 'F1', None, False, -0.3)]
HOLD_WINDOW = [(CTRL, PROD, False), ('A|s2|fm0.65', WIN, False), ('A|s2|tp0.2', LOSE, False)]
HOLD_RATES = {CTRL: (0.45, 0.40, 0.25), 'A|s2|fm0.65': (0.80, 0.70, 0.25), 'A|s2|tp0.2': (0.25, 0.25, 0.25)}
HOLD_BATCH = [{'id': 'A|s2|fm0.65', 'leg': 'both'}, {'id': CTRL, 'leg': 'underdog'}, {'id': 'A|s2|tp0.2', 'leg': 'fav'}]
_READ = {}


def read():
    """One stage hold run of a batch (Amendment 4 item 7): the batch configs' |window and |F1 arms, the production config in it."""
    if not _READ:
        root = tmpdir()
        units, shards, plan = build(root, pool='hold', stage='hold', families_b=False, runs_def=HOLD_BATCH_RUNS, meta_extra={'specsHash': SPECS_HASH})
        with_window(shards, HOLD_WINDOW, seed=5, batch=HOLD_BATCH, family_b=False, rates=HOLD_RATES, coin=False, short=('A|s2|tp0.2',))
        out = os.path.join(root, 'out')
        r = run_report(units, shards, out, '--plan', plan, pool='hold')
        assert r.returncode == 0, r.stderr[-3000:] + r.stdout[-2000:]
        with open(os.path.join(out, 'summary.json')) as fh:
            summary = strict_json(fh.read())
        with open(os.path.join(out, 'hold-league.json')) as fh:
            hl = strict_json(fh.read())
        with open(os.path.join(out, 'hold-league.md')) as fh:
            md = fh.read()
        with open(os.path.join(out, 'report.md')) as fh:
            report = fh.read()
        _READ.update(root=root, out=out, shards=shards, summary=summary, hl=hl, md=md, report=report, rows=read_registry(out))
    return _READ


def test_hold_batch_run_scores_each_member_with_the_one_test():
    e = read()
    s, hl, md = e['summary'], e['hl'], e['md']
    assert s['one_test']['run'] and s['one_test']['files'] == ['hold-league.md', 'hold-league.json']
    assert not any(os.path.exists(os.path.join(e['out'], f)) for f in ('league.md', 'league.csv', 'league.json', 'hold-batch-candidate.json'))
    b = s['one_test']['batch']
    assert b['source'] == 'the shard metas (meta.batch)' and b['league_run'] == '777' and b['hash'] == 'ab' * 32
    mem = {(m['config'], m['leg']): m for m in b['members']}
    assert set(mem) == {(x['id'], x['leg']) for x in HOLD_BATCH} and [(m['config'], m['leg']) for m in b['members']] == [(x['id'], x['leg']) for x in HOLD_BATCH]
    win, ctrl, lose = mem[('A|s2|fm0.65', 'both')], mem[(CTRL, 'underdog')], mem[('A|s2|tp0.2', 'fav')]
    assert win['direction_found'] and win['verdict'].startswith('direction found: ') and win['gap'] >= 2 * win['se']
    assert not lose['direction_found'] and lose['verdict'].startswith('not found: ') and lose['gap'] < 2 * lose['se']
    # Each member's one test is gap_stats over the hold pool's H-HOLD matches of the file arrays, the 'both' leg per-event summed.
    for m in b['members']:
        legs = ['underdog', 'fav'] if m['leg'] == 'both' else [m['leg']]
        arrs = [window_arrays(e['shards'], 'hold', m['config'] + '|window', leg, H_HOLD[0], H_HOLD[1]) for leg in legs]
        n, w, tn, tw = ([sum(x) for x in zip(*[a[k] for a in arrs])] for k in range(4))
        g = R.gap_stats(n, w, tn, tw)
        assert (m['n'], m['w'], m['tn'], m['tw']) == (g['n'], g['w'], g['tn'], g['tw']) and abs(m['gap'] - g['gap']) <= 1e-12 and abs(m['se'] - g['se']) <= 1e-12
        assert m['pass'] == g['pass'] == (g['z'] is not None and g['gap'] >= 2 * g['se'])
    # hold-league.json: the members with the six folds, both tours and the F1 money; the other legs as information.
    hm = {(m['config'], m['leg']): m for m in hl['members']}
    assert set(hm) == set(mem) and hl['batch'] == {'source': b['source'], 'league_run': '777', 'hash': 'ab' * 32}
    for m in hm.values():
        assert sorted(m['by_fold']) == ['1', '2', '3', '4', '5', '6'] and sum(v['n'] for v in m['by_fold'].values()) == m['n']
        assert set(m['by_tour']) == {'ATP', 'WTA'} and m['by_tour']['ATP']['n'] + m['by_tour']['WTA']['n'] == m['n']
        assert m['f1_money']['arm'] == m['config'] + '|F1' and len(m['f1_money']['folds']) == 6 and m['registry']['standard'] == 'one-test'
    assert {(r['config'], r['leg']) for r in hl['other_legs']} == {(c, leg) for c, _, _ in HOLD_WINDOW for leg in ('underdog', 'fav', 'both')} - set(mem)
    # The HO-1 money table is paired against the production control (in the batch) and carries the registry's block: information.
    assert hl['ho1_money']['control'] == CTRL + '|F1' and {c['arm'] for c in hl['ho1_money']['candidates']} == {'A|s2|fm0.65|F1', 'A|s2|tp0.2|F1'}
    # hold-league.md: the result per member, the folds, the tours, the money table, nothing judged but the one test.
    assert '## The one read (Amendment 4 item 7)' in md and 'DIRECTION FOUND' in md and 'not found (gap < 2 x SE)' in md and '| twins short |' in md
    assert 'the six 16-day HO-1 folds' in md and '### Both tours (information)' in md and '### The HO-1 money table (information)' in md
    assert "The batch configs' other legs (information, not read; no registry row)" in md
    assert 'Paired against the production control' in md and '| A\\|s2\\|fm0.65\\|F1 |' in md
    rep = e['report']
    assert 'Under Amendment 4 this section is information' in rep and 'direction found' in rep and 'hold-league.md' in rep


def test_hold_batch_rows_carry_the_one_test_block_and_validate():
    reg = registry_module()
    e = read()
    rows = e['rows']
    wrows = {r['arm']: r for r in rows if '|window|' in r['arm']}
    # Rows of the read only: one per batch member (no row for the other legs, no coin placebo ran), every one valid.
    assert set(wrows) == {f"{x['id']}|window|{x['leg']}" for x in HOLD_BATCH} and not any('coinwindow' in r['arm'] for r in rows)
    hm = {(m['config'], m['leg']): m for m in e['hl']['members']}
    for arm, r in wrows.items():
        err, fl = reg.validate(r)
        # No coin placebo runs on the read (README: the batch configs' |window and |F1 arms only), so the row has no control and
        # the validator says G2:unpaired (a money flag; the registry's OT_BLOCKING leaves a direction test alone).
        assert err == [] and not any(f.startswith(('DEV:', 'G0:', 'OT:')) for f in fl) and 'G1:non-dollar-metric' in fl and 'G2:unpaired' in fl, (arm, err, fl)
        assert r['flags'] == [] and r['role'] == 'candidate' and 'control' not in r and r['data']['days'] == all_hold_days()
        h = r['heldout']
        m = hm[(r['raw']['config'], r['leg'])]
        assert h['standard'] == 'one-test' and h['tier'] == 'history' and h['days'] == 96 and h['horizon'] == 'match' and h['hot_spot'] == m['hot_spot']
        # The block's gap is the item 6 (cluster-weighted) gap the verdict was judged on, decomposed into item 6's weighted
        # rates, so the registry, which recomputes pass from window_rate - random_rate against se, judges by that number;
        # the pooled rates and the twin shortfall stand beside them.
        assert h['n'] == m['n'] and h['twins'] == m['tn'] and abs(h['gap'] - m['gap']) < 1e-12 and abs(h['se'] - m['se']) < 1e-12 and h['pass'] == m['pass']
        assert abs(h['window_rate'] - m['rate_weighted']) < 1e-12 and abs(h['random_rate'] - m['random_weighted']) < 1e-12
        assert abs(h['gap'] - (h['window_rate'] - h['random_rate'])) <= 1e-12
        assert abs(h['window_rate_pooled'] - m['rate']) < 1e-12 and abs(h['random_rate_pooled'] - m['random']) < 1e-12
        assert h['twins_short'] == m['twins_short'] and (h['matches'], h['clustered']) == (m['matches'], m['clustered']) and h['rates'].startswith('item 6')
        assert h['replay_version'] == replay_version_in_code()
        ok, why = reg.one_test_pass(h)
        assert ok == m['pass'] and ok == m['direction_found'] and 'OT:declared-pass-differs' not in fl, (arm, why, fl)
        assert r['verdict'].startswith('direction found: ' if ok else 'not found: ')
        if m['twins_short']:
            # tp0.2's fav leg drew 2 twins on every third instance (the fixture): the pooled difference is not the gap, and the
            # verdict and the md say so.
            assert abs((m['rate'] - m['random']) - m['gap']) > 1e-6 and 'short of 3 an instance' in r['verdict'] and "item 6's weighted" in r['verdict']
            assert f"| {m['tn']} | {m['tw']} | {m['twins_short']} |" in e['md']
        else:
            assert abs(h['window_rate'] - m['rate']) < 1e-12 and abs(h['random_rate'] - m['random']) < 1e-12 and 'short of' not in r['verdict']
        assert sorted(r['by_day']) == all_hold_days() and set(r['by_tercile']) == {'ATP', 'WTA'}
    assert [k for k, m in hm.items() if m['twins_short']] == [('A|s2|tp0.2', 'fav')] and hm[('A|s2|tp0.2', 'fav')]['events_short'] > 0
    # The registry's own ho1_fill leaves a one-test block as written.
    again = reg.ho1_fill([dict(r) for r in rows])
    assert {x['arm']: x['heldout'] for x in again if x['arm'] in wrows} == {arm: r['heldout'] for arm, r in wrows.items()}
    ot = e['summary']['registry']['one_test']
    assert set(ot) == set(wrows) and all(ot[arm]['pass'] == wrows[arm]['heldout']['pass'] for arm in wrows)
    # The F1 rows keep their HO-1 block as information: the registry's verdict beside the one test, cutting nothing.
    a = {r['arm']: r for r in rows if r['family'] == 'tennis-ta-A' and '|window|' not in r['arm']}
    assert set(a) == {CTRL + '|F1', 'A|s2|fm0.65|F1', 'A|s2|tp0.2|F1'} and a['A|s2|fm0.65|F1']['verdict'].startswith('HO-1 ')
    assert a[CTRL + '|F1']['role'] == 'control' and a['A|s2|fm0.65|F1']['heldout']['standard'] == 'HO-1'
    v = subprocess.run([sys.executable, '-I', registry_path(), 'validate', os.path.join(e['out'], ROWS_FILE)], capture_output=True, text=True, timeout=120)
    assert v.returncode == 0 and 'INVALID' not in v.stdout, v.stdout[-2000:]


def test_hold_batch_without_the_production_config_has_no_paired_money_table():
    root = tmpdir()
    runs_def = [x for x in HOLD_BATCH_RUNS if not x[0].startswith(CTRL)]
    units, shards, plan = build(root, pool='hold', stage='hold', families_b=False, runs_def=runs_def, meta_extra={'specsHash': SPECS_HASH})
    with_window(shards, [x for x in HOLD_WINDOW if x[0] != CTRL], seed=5, batch=[x for x in HOLD_BATCH if x['id'] != CTRL], family_b=False, rates=HOLD_RATES, coin=False)
    out = os.path.join(root, 'out')
    r = run_report(units, shards, out, '--plan', plan, pool='hold', boot=49)
    assert r.returncode == 0, r.stderr[-3000:]
    with open(os.path.join(out, 'hold-league.md')) as fh:
        md = fh.read()
    with open(os.path.join(out, 'report.md')) as fh:
        rep = fh.read()
    assert 'No production control in the batch' in md and 'DIRECTION FOUND' in md and "each F1 arm's own net by fold" in md
    assert 'no production control among the run' in rep
    rows = read_registry(out)
    assert {r['arm'] for r in rows if '|window|' in r['arm']} == {'A|s2|fm0.65|window|both', 'A|s2|tp0.2|window|fav'}
    assert all(r['verdict'].startswith('HO-1: no held-out block') for r in rows if r['arm'].endswith('|F1'))


def test_hold_batch_is_refused_without_its_window_arms_or_block():
    # A batch member whose |window arm did not run.
    def no_window(shards, plan):
        for f in os.listdir(shards):
            p = os.path.join(shards, f)
            with gzip.open(p, 'rt') as fh:
                d = json.load(fh)
            d['runs'] = [x for x in d['runs'] if x['id'] != 'A|s2|tp0.2|window']
            d['window']['rows'] = [x for x in d['window']['rows'] if x['id'] != 'A|s2|tp0.2|window']
            with gzip.open(p, 'wt') as fh:
                json.dump(d, fh)
    def batch_fixture(shards, plan, batch=HOLD_BATCH):
        with_window(shards, HOLD_WINDOW, seed=5, batch=batch, family_b=False, rates=HOLD_RATES, coin=False)
    err = _hold_refused(lambda s, p: (batch_fixture(s, p), no_window(s, p)), runs_def=HOLD_BATCH_RUNS)
    assert 'hold batch' in err and 'A|s2|tp0.2|window' in err and 'no registry rows' in err
    # A batch (from the file) but shards without the window block.
    root = tmpdir()
    bfile = os.path.join(root, 'hold-batch.json')
    with open(bfile, 'w') as fh:
        json.dump({'league_run': '777', 'batch': HOLD_BATCH}, fh)
    err = _hold_refused(None, '--hold-batch', bfile, runs_def=HOLD_BATCH_RUNS)
    assert 'no window block' in err and bfile in err
    # A batch member with an arm, a leg that is not one, a member twice, eleven members.
    bad = [dict(HOLD_BATCH[0], id='A|s2|fm0.65|F1'), dict(HOLD_BATCH[1], leg='underdogs'), HOLD_BATCH[2], HOLD_BATCH[2]] + [{'id': CTRL, 'leg': 'both'}] * 7
    err = _hold_refused(lambda s, p: batch_fixture(s, p, bad), runs_def=HOLD_BATCH_RUNS)
    assert 'ends with an arm' in err and 'underdogs' in err and 'listed twice' in err and 'at most 10' in err
    # The window block in some files and not in others, and a window arm without the block.
    def drop_block(shards, plan):
        f = sorted(os.listdir(shards))[0]
        p = os.path.join(shards, f)
        with gzip.open(p, 'rt') as fh:
            d = json.load(fh)
        del d['window']
        with gzip.open(p, 'wt') as fh:
            json.dump(d, fh)
    err = _hold_refused(lambda s, p: (batch_fixture(s, p), drop_block(s, p)), runs_def=HOLD_BATCH_RUNS)
    assert 'but no window block' in err


def test_window_arms_are_checked_like_the_other_arms():
    def run(rid, ov, fill='F1', placebo=None, stick=False, window=False):
        return rid, {'id': rid, 'overrides': ov, 'fill': fill, 'placebo': placebo, 'stick': stick, 'offsetMs': None, 'window': window}
    good = dict([run(CTRL + '|F1', PROD), run(CTRL + '|coin', PROD, 'F1', 'coin'), run(CTRL + '|window', PROD, window=True),
                 run(CTRL + '|coinwindow', PROD, 'F1', 'coin', window=True), run('A|s1|prod|settlehold|window', dict(PROD, TENNIS_END_LOSER_CUT=False), stick=True, window=True)])
    assert R.check_runs([good, good]) == []
    # A window arm is never a twin of its F1 arm; its id must say |window (|coinwindow for its coin placebo).
    assert any('names arm F1' in x and 'window arm' in x for x in R.check_runs([dict([run('A|s2|x|F1', WIN, window=True)])]))
    assert any('names arm window' in x for x in R.check_runs([dict([run('A|s2|x|window', WIN, 'F1', 'coin', window=True)])]))
    assert any('must end in its arm' in x and '|window' in x for x in R.check_runs([dict([run('A|s2|x', WIN, window=True)])]))
    other = dict(good)
    other[CTRL + '|window'] = dict(other[CTRL + '|window'], window=False)
    assert any('window flag differ' in x for x in R.check_runs([good, other]))
    assert R.window_arm_of('A|s1|x|window') == ('A|s1|x', 'window') and R.window_arm_of('A|s1|x|coinwindow') == ('A|s1|x', 'coinwindow')
    assert R.window_arm_of('A|s1|x|F1') is None and R.window_arm_of('window') is None


def test_hist_bins_and_quantiles():
    assert R.hist_bins([1, 2, 5]) == ['<1', '1..2', '2..5', '>=5'] and R.hist_bins([0, -0.01, -0.2]) == ['>0', '-0.01..0', '-0.2..-0.01', '<=-0.2']
    assert R.hist_quantile([1, 2, 5], [0, 0, 0, 0], 0.5) is None
    assert R.hist_quantile([1, 2, 5], [1, 2, 1, 0], 0.5) == '1..2' and R.hist_quantile([1, 2, 5], [1, 2, 1, 0], 0.25) == '<1'
    # The 3rd of 4 binned values (q 0.75) is still in '1..2'; the 4th (q 1) is in '2..5'.
    assert R.hist_quantile([1, 2, 5], [1, 2, 1, 0], 0.75) == '1..2' and R.hist_quantile([1, 2, 5], [1, 2, 1, 0], 1.0) == '2..5'
    assert R.hist_quantile([1, 2, 5], [0, 0, 0, 3], 0.5) == '>=5'
    s = R.hist_summary('tWin', [0] * 3 + [4] + [0] * 6)
    assert s['median'] == s['q1'] == s['q3'] == '3..5' and s['total'] == 4 and len(s['bins']) == 10


def test_a_run_without_the_window_block_has_no_league_and_says_so():
    e = e2e()
    ot = e['summary']['one_test']
    assert not ot['run'] and 'no window block' in ot['reason'] and ot['files'] == []
    assert not os.path.exists(os.path.join(e['out'], 'league.md')) and '- not run: the shards carry no window block' in e['report']
    assert e['summary']['registry']['one_test_rows'] == 0


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
