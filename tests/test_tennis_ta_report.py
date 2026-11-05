#!/usr/bin/env python3
"""research/tennis_ta_report.py end to end on a synthetic shard set (contract C4): two shards x two sub-slices, a measuring
stick, F1 / F2 / coin arms and a family B export.

Run: python3 -m pytest -q tests/test_tennis_ta_report.py, or python3 tests/test_tennis_ta_report.py (no pytest needed).
Temp files go under $TENNIS_TA_TEST_TMP when set (else the system temp dir)."""
import gzip
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


def units_table():
    """17 Monday 05:00 UTC weeks from 2025-03-03; the 6th is sealed (out of the pool, its neighbours embargo 24 h)."""
    t0 = ms('2025-03-03T05:00:00')
    out = []
    for i in range(17):
        s = t0 + i * 7 * DAY
        out.append({'id': f'W-{day_of(s)}', 'start': s, 'end': s + 7 * DAY, 'startDay': day_of(s), 'sealed': i == 5})
    return out


def episode(m, start, ph, px, pnl, br=0):
    return [m, 0, start + 600_000, 'underdog', px, 10, ph, 3, 'tp', 300, round(pnl, 6), br]


def build(root, families_b=True, seed=7):
    """Write units.json and the shard directory; returns (units path, shard dir, plan path)."""
    rng = np.random.default_rng(seed)
    table = units_table()
    upath = os.path.join(root, 'units.json')
    with open(upath, 'w') as fh:
        json.dump(table, fh)
    pool_units = [u for u in table if not u['sealed']]
    slices = [[pool_units[i] for i in idx] for idx in ([0, 1, 2, 3], [4, 5, 6, 7], [8, 9, 10, 11], [12, 13, 14, 15])]
    plan_slices = {(0, 0): slices[0], (0, 1): slices[1], (1, 0): slices[2], (1, 1): slices[3]}
    sdir = os.path.join(root, 'shards')
    os.makedirs(sdir, exist_ok=True)
    spans_all = R.pool_spans_from_table(table, ['disc'], {u['id'] for u in pool_units})
    runs_def = [
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
    ]
    phases = ['pre', 'e20', 'p1', 'p2', 'p3']
    ev = 0
    plan = {'stage': '1', 'pool': 'disc', 'requestSha': 'req-sha', 'unitsSha': 'units-sha', 'simVersion': 'tennis-ta-sim/2', 'familyB': families_b,
            'plan': [{'k': 0}, {'k': 1}], 'subPlans': [[None, None], [None, None]], 'expected': [], 'units': [u['id'] for u in pool_units],
            'poolSpans': spans_all}
    breach_done = False
    for (k, j), us in sorted(plan_slices.items()):
        matches = []
        for u in us:
            for d in range(7):
                for q in range(3):
                    start = u['start'] + d * DAY + (2 + 5 * q) * HOUR
                    matches.append({'event': f'KXEV-{ev}', 'series': 'KXATPMATCH' if ev % 2 == 0 else 'KXWTAMATCH', 'day': day_of(start),
                                    'start': start, 'startPublished': ev % 17 != 3, 'close': start + int(2.5 * HOUR),
                                    'tickers': [f'KXEV-{ev}-A', f'KXEV-{ev}-B'], 'trades': 0 if ev % 41 == 5 else 40,
                                    'unresolved': False, 'resultA': 1, 'pool': 'disc', 'unit': u['id']})
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
                eps.append(episode(mi, m['start'], ph, px, v, br))
                pnl.append(round(v, 6))
            run = {'id': rid, 'overrides': ov, 'fill': fill, 'stratum': 'H', 'days': [], 'pnl': pnl, 'episodes': eps}
            if plc:
                run['placebo'] = plc
            if stick:
                run['stick'] = True
            runs.append(run)
        last = us[-1]
        frm, to = us[0]['startDay'], day_of(R.day_ms(day_of(last['end'])) + DAY)
        meta = {'simVersion': 'tennis-ta-sim/2', 'stage': '1', 'pool': 'disc', 'run': '4242', 'k': k, 'j': j, 'shards': 2, 'subShards': 2,
                'from': frm, 'to': to, 'units': [u['id'] for u in us], 'dataVersion': 'atp:abc wta:def',
                'coverage': {'span': [frm, to], 'series': {s: {'first': '2025-03-01', 'last': '2025-07-01', 'files': 120, 'spanDays': 30,
                                                               'withFile': 30, 'withTrades': 30, 'missing': []} for s in ('KXATPMATCH', 'KXWTAMATCH')},
                             'matches': len(matches), 'noPublishedStart': sum(1 for m in matches if not m['startPublished']), 'noPublishedStartEvents': []},
                'requestSha': 'req-sha', 'families': ['A', 'B'] if families_b else ['A'], 'sha': 'deadbeefcafe', 'unitsSha': 'units-sha',
                'stratum': 'H', 'evidence': 'history, synthetic depth', 'episodeCols': COLS, 'sticks': ['A|s1|prod|settlehold|F1'],
                'poolSpans': [s for s in spans_all if s['unit'] in {u['id'] for u in us}]}
        out = {'meta': meta, 'matchList': matches, 'runs': runs}
        if families_b:
            out['familyB'] = family_b(us, matches, rng, first=(k, j) == (0, 0))
        name = f'a-s1-{k}-{j}.json.gz'
        with gzip.open(os.path.join(sdir, name), 'wt') as fh:
            json.dump(out, fh)
        plan['expected'].append(name)
        plan['subPlans'][k][j] = {'k': j, 'from': frm, 'to': to, 'units': [u['id'] for u in us]}
    ppath = os.path.join(root, 'plan.json')
    with open(ppath, 'w') as fh:
        json.dump(plan, fh)
    return upath, sdir, ppath


def family_b(us, matches, rng, first):
    def cell(cid, group, edge, sd, per_unit, placebo_edge, breaches=0):
        c = {'id': cid, 'group': group, 'n': 0, 'sum': 0.0, 'sumSq': 0.0, 'sum3': 0.0, 'sum4': 0.0, 'breaches': breaches, 'gross': 0.0,
             'fees': 0.0, 'stressSum': 0.0, 'units': {}, 'days': {}}
        for u in us:
            days = sorted({m['day'] for m in matches if m['unit'] == u['id']})
            xs = edge + rng.normal(0, sd, per_unit)
            ps = placebo_edge + rng.normal(0, sd, per_unit)
            c['units'][u['id']] = [per_unit, float(xs.sum()), per_unit, float(ps.sum())]
            for q, x in enumerate(xs):
                d = days[q % len(days)]
                cur = c['days'].setdefault(d, [0, 0.0])
                cur[0] += 1
                cur[1] += float(x)
            c['n'] += per_unit
            c['sum'] += float(xs.sum())
            c['sumSq'] += float((xs ** 2).sum())
            c['sum3'] += float((xs ** 3).sum())
            c['sum4'] += float((xs ** 4).sum())
            c['gross'] += float(xs.sum()) + 0.1 * per_unit
            c['fees'] += 0.1 * per_unit
            c['stressSum'] += float(xs.sum()) - 0.05 * per_unit
        return c
    g = 'B|RSI14L|1m|exitExt|follow'
    cells = [cell(B_POS, g, 0.3, 0.2, 10, -0.1), cell(B_POS_CTX, g, 0.3, 0.2, 3, -0.1), cell(B_NULL, 'B|MACD|5m|zero|fade', 0.0, 0.5, 6, 0.0),
             cell(B_BREACH, 'B|ROC10L|1m|zero|follow', 0.3, 0.2, 10, -0.1, breaches=1 if first else 0)]
    return {'stratum': 'H', 'designSize': 40, 'diagnostics': {'matches': len(matches), 'noTape': 1, 'entries': sum(c['n'] for c in cells)}, 'cells': cells}


def run_report(units, shards, out, *extra):
    return subprocess.run([sys.executable, SCRIPT, '--shards', shards, '--pool', 'disc', '--run', '4242', '--out', out, '--units', units,
                           '--boot', str(BOOT), *extra], capture_output=True, text=True, timeout=600)


def strict_json(text):
    def bad(x):
        raise ValueError(f'non-JSON constant {x}')
    return json.loads(text, parse_constant=bad)


def read_registry(out):
    with gzip.open(os.path.join(out, 'registry-tennis-ta-4242.jsonl.gz'), 'rt') as fh:
        return [strict_json(line) for line in fh if line.strip()]


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
        _E2E.update(root=root, out=out, cells=cells, summary=summary, report=report, registry=read_registry(out))
    return _E2E


def test_end_to_end_outputs_are_valid_json_and_p_is_never_zero():
    e = e2e()
    floor = 1 / (BOOT + 1)
    assert e['cells'], 'no cells'
    assert min(c['p'] for c in e['cells']) >= floor - 1e-15
    assert all(c.get('p_placebo') is None or c['p_placebo'] >= floor - 1e-15 for c in e['cells'])
    assert all(r['p_boot'] >= floor - 1e-15 for r in e['registry'])
    assert e['summary']['spa']['p_consistent'] >= floor - 1e-15
    with gzip.open(os.path.join(e['out'], 'cells-b.json.gz'), 'rt') as fh:
        strict_json(fh.read())
    with open(os.path.join(e['out'], 'losers.json')) as fh:
        strict_json(fh.read())


def test_registry_ids_unique_and_carry_the_arm():
    reg = e2e()['registry']
    ids = [r['cell'] for r in reg]
    assert len(ids) == len(set(ids))
    by = {r['cell']: r for r in reg}
    a_rows = [r for r in reg if r['family'] == 'A']
    for r in a_rows:
        arm_tag = r['cell'].split('|')[-4]
        assert arm_tag in ('F1', 'F2', 'coin') or r['arm'] == 'stick', r['cell']
        if r['arm'] in ('F1', 'F2', 'coin'):
            assert arm_tag == r['arm']
    partnered = [r for r in a_rows if r['arm'] == 'F1' and r['placebo_partner']]
    assert partnered
    for r in partnered:
        p = by[r['placebo_partner']]
        assert p['arm'] == 'coin' and p['config'] == r['config'] and p['cell'] != r['cell']
        assert p['cell'].split('|')[-3:] == r['cell'].split('|')[-3:]
    assert len({r['config_hash'] for r in a_rows if r['config'] == 'A|s1|m0.01|f0.2|o0.01|w60'}) == 3


def test_stick_is_reported_but_never_screened():
    e = e2e()
    sticks = [c for c in e['cells'] if c['arm'] == 'stick']
    assert sticks and all('bh' not in c and not c.get('flag') for c in sticks)
    assert e['summary']['f1_cells'] == sum(1 for c in e['cells'] if c['arm'] == 'F1')
    assert e['summary']['bh_floor']['A_m'] == e['summary']['f1_cells']
    assert not any('settlehold' in x for x in e['summary']['flagged'])
    assert 'settlehold' not in json.dumps(e['summary']['spa'])
    assert all(r['verdict'] == 'stick' and r['bh'] is None for r in e['registry'] if r['family'] == 'A' and r['arm'] == 'stick')
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
    rows = [r for r in e['registry'] if r['family'] == 'B']
    assert {r['cell'] for r in rows} == {B_POS, B_POS_CTX, B_NULL, B_BREACH}
    assert all(r['cell'].startswith('B|') and not r['cell'].startswith('B|B|') for r in rows)
    fb = e['summary']['family_b']
    assert fb['design_size'] == 40 and fb['bh_m'] == 40 and e['summary']['n_raw']['B'] == 4
    with gzip.open(os.path.join(e['out'], 'cells-b.json.gz'), 'rt') as fh:
        cb = {c['id']: c for c in strict_json(fh.read())}
    pos = cb[B_POS]
    assert pos['n'] == 160 and pos['units'] == 16 and pos['placebo_units'] == 16
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
    # Pool hours: 16 pool weeks, minus the embargo days next to the sealed week, clipped to the data span (Mar 1 to Jul 1).
    assert abs(s['pool_hours_unclipped'] - (16 * 7 - 2) * 24) < 1e-6
    assert s['pool_no_published_start'] > 0
    assert all(c['usd_per_live_hour'] is not None for c in e['cells'] if c['tour'] == 'all')
    assert s['pbo'] is not None and s['folds'] == ['2025-03', '2025-04', '2025-05', '2025-06']
    assert s['onc']['best_k'] and s['onc']['k_cap'] is None and s['onc']['warnings'] == [] and 'universe' in s['v_sr_source']
    assert 'Knob sensitivity (section 5 rule' in rep and 'A2 (the 729-config factorial): does not run' in rep


def _refused(mutate, *extra):
    root = tmpdir()
    units, shards, plan = build(root)
    mutate(shards, plan)
    out = os.path.join(root, 'out')
    r = run_report(units, shards, out, *extra)
    assert r.returncode != 0, r.stdout[-2000:]
    assert not os.path.exists(os.path.join(out, 'registry-tennis-ta-4242.jsonl.gz'))
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


def test_pool_list_membership():
    root = tmpdir()
    units, shards, _ = build(root, families_b=False)
    out = os.path.join(root, 'out')
    r = subprocess.run([sys.executable, SCRIPT, '--shards', shards, '--pool', 'check,disc', '--out', out, '--units', units, '--boot', '99'],
                       capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stderr[-2000:]
    with open(os.path.join(out, 'summary.json')) as fh:
        s = strict_json(fh.read())
    assert s['pools'] == ['check', 'disc'] and s['matches'] > 300 and s['family_b'] is None
    r2 = subprocess.run([sys.executable, SCRIPT, '--shards', shards, '--pool', 'dis', '--out', os.path.join(root, 'out2'), '--units', units,
                         '--boot', '99'], capture_output=True, text=True, timeout=600)
    assert r2.returncode != 0 and not os.path.exists(os.path.join(root, 'out2'))


def test_set_check_finds_a_skipped_pool_unit_but_not_a_sealed_one():
    table = units_table()
    pool = [u for u in table if not u['sealed']]

    def info(k, j, us, events):
        last = us[-1]
        meta = {'run': '1', 'stage': '1', 'pool': 'disc', 'simVersion': 'tennis-ta-sim/2', 'dataVersion': 'v', 'families': ['A'], 'shards': 1,
                'subShards': 2, 'k': k, 'j': j, 'from': us[0]['startDay'], 'to': day_of(R.day_ms(day_of(last['end'])) + DAY), 'units': [u['id'] for u in us]}
        return {'file': f'a-s1-{k}-{j}.json.gz', 'meta': meta, 'events': events, 'run_ids': ('x',), 'has_b': False, 'b_design': None,
                'b_stratum': None, 'row_units': {us[0]['id']}, 'b_units': set(), 'problems': []}
    # Pool units 4 and 5 sit on either side of the sealed week: adjacent in the pool, so the set is sound.
    ok = R.check_shard_set([info(0, 0, pool[:5], ['e1']), info(0, 1, pool[5:8], ['e2'])], table)
    assert ok == [], ok
    gap = R.check_shard_set([info(0, 0, pool[:5], ['e1']), info(0, 1, pool[6:8], ['e2'])], table)
    assert any('no shard file swept them' in x and pool[5]['id'] in x for x in gap), gap
    dup = R.check_shard_set([info(0, 0, pool[:5], ['e1']), info(0, 1, pool[5:8], ['e1'])], table)
    assert any('appear twice' in x for x in dup), dup


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
