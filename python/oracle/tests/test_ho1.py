"""Tests for oracle/ho1.py (SPEC 4; prereg OR-H1 "HO-1 (once per frozen file)") on the synthetic parts of
oracle/fixtures_parts.py and a synthetic regime-label file. Nothing here is real data.

    cd python && python3 -m pytest -q oracle/tests/test_ho1.py

research/registry.py (the scorer validates and fills its rows with it) is read from origin/claude/project-thread-79ntof
with `git show`; the tests that need it skip when that branch is not in the checkout.
"""
import gzip
import hashlib
import json
import os
import shutil
import subprocess
import sys
import types

import numpy as np
import pytest

from oracle import ho1
from oracle.common import HOLD_FROM, HOLD_TO, MIN, SIDES, Part, write_part
from oracle.fixtures_parts import PLANTED_ITEMS, make_parts
from oracle.mine import canonical, confirm, main as mine_main, setup_id
from oracle.sim import matched_placebo

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
DAYS96 = [d for d in ho1.HOLD_DAYS]
NULL_ITEMS = [[{'f': 'fb03', 'v': 0}, {'f': 'fs05', 'v': 1}], [{'f': 'fs07', 'v': -1}], [{'f': 'fs09', 'v': 1}, {'f': 'fs10', 'v': -1}],
              [{'f': 'fb04', 'v': 1}]]


# ---------------------------------------------------------------- helpers

@pytest.fixture(scope='session')
def registry(tmp_path_factory):
    try:
        src = subprocess.run(['git', 'show', 'origin/claude/project-thread-79ntof:research/registry.py'], cwd=REPO,
                             capture_output=True, text=True, timeout=30)
    except Exception:
        src = None
    if src is None or src.returncode != 0 or 'def ho1_fill' not in src.stdout:
        pytest.skip('research/registry.py (origin/claude/project-thread-79ntof) not available in this checkout')
    p = tmp_path_factory.mktemp('registry') / 'registry.py'
    p.write_text(src.stdout)
    return str(p)


def write_labels(path, assets, seed=3):
    """Synthetic regime v1 labels (one minute label per HO-1 hour per asset; hour_terciles averages what is there)."""
    rng = np.random.default_rng(seed)
    with gzip.open(path, 'wt') as f:
        f.write('ts_iso,asset,rv60,q33,q67,tercile,z60,trend\n')
        for a in assets:
            for hh in range(96 * 24):
                t = HOLD_FROM + hh * 3_600_000
                iso = np.datetime_as_string(np.datetime64(t, 'ms'), unit='s') + 'Z'
                f.write(f'{iso},{a},,,,{("LOW", "MID", "HIGH")[rng.integers(0, 3)]},,\n')
    return path


def write_frozen(out, ct, setups, part_paths, params=None):
    """A frozen.json in the miner's canonical format (mine.canonical) plus frozen.sha256; ranks in list order."""
    os.makedirs(out, exist_ok=True)
    fz = []
    for r, s in enumerate(setups, 1):
        d = {'ct': ct, 'scope': s['scope'], 'side': s['side'], 'h': int(s['h']), 'items': s['items'], 'k': len(s['items']),
             'dev': {}, 'p_bhy': None, 'rank_scope': None, 'adversary': None, 'rank': r, 'rank_A': r}
        d['id'] = setup_id(ct, s['scope'], s['side'], int(s['h']), s['items'])
        fz.append(d)
    parts = []
    for p in part_paths:
        P = Part(p)
        parts.append({'dir': os.path.basename(p), 'scope': P.scope, 'code_sha': P.meta.get('code_sha'), 'rows_total': P.n, 'dev_rows': None})
    doc = {'schema': 'oracle-frozen-1', 'ct': ct, 'prereg': 'python/oracle/prereg/OR-H1.md', 'code_sha': 'test', 'parts': parts,
           'params': dict({'seeds': 8, 'block': 5.0, 'draws': 2000, 'q': 0.10, 'seed': 7}, **(params or {})),
           'N_raw': 1000, 'm_confirmed': 40, 'bhy_q': 0.10, 'setups': fz}
    body = canonical(doc)
    with open(os.path.join(out, 'frozen.json'), 'wb') as f:
        f.write(body)
    with open(os.path.join(out, 'frozen.sha256'), 'w') as f:
        f.write(f'{hashlib.sha256(body).hexdigest()}  frozen.json\n')
    return os.path.join(out, 'frozen.json'), doc


def run_ho1(frozen, root, labels, out, registry, *extra):
    argv = ['--frozen', frozen, '--parts', root, '--out', out, '--run', '4242', '--code-sha', 'c0ffee1', '--registry', registry, '--quiet']
    if labels:
        argv += ['--labels', labels]
    return ho1.main(argv + list(extra))


def by_arm(res):
    out = {s['arm']: s for s in res['summary']['setups']}
    if res['summary']['book']:
        out['book'] = res['summary']['book']
    return out


def setups_spec(ct, extra_null=True):
    side = SIDES[ct][0]
    other = SIDES[ct][1]
    s = [{'scope': 'ALL', 'side': side, 'h': 15 if ct != 'pp60' else 60, 'items': PLANTED_ITEMS}]
    if extra_null:
        s += [{'scope': 'ALL', 'side': side, 'h': 15, 'items': NULL_ITEMS[0]},
              {'scope': 'BTC' if ct != 'tennis' else 'ATP', 'side': other, 'h': 15, 'items': NULL_ITEMS[1]},
              {'scope': 'ETH' if ct != 'tennis' else 'WTA', 'side': side, 'h': 15, 'items': NULL_ITEMS[2]},
              {'scope': 'ALL', 'side': other, 'h': 15, 'items': NULL_ITEMS[3]}]
    return s


@pytest.fixture(scope='module')
def perp(tmp_path_factory, registry):
    root = str(tmp_path_factory.mktemp('perp_parts'))
    paths = make_parts(root, 'perp', ('BTC', 'ETH'), 'planted', seed=1)
    w = str(tmp_path_factory.mktemp('perp_ho1'))
    labels = write_labels(os.path.join(w, 'labels.csv.gz'), ['BTC', 'ETH'])
    spec = [{'scope': 'ALL', 'side': 'L', 'h': 15, 'items': PLANTED_ITEMS}, {'scope': 'BTC', 'side': 'L', 'h': 60, 'items': PLANTED_ITEMS}]
    spec += [{'scope': 'ALL', 'side': 'L', 'h': 15, 'items': NULL_ITEMS[0]}, {'scope': 'BTC', 'side': 'S', 'h': 60, 'items': NULL_ITEMS[1]},
             {'scope': 'ETH', 'side': 'L', 'h': 15, 'items': NULL_ITEMS[2]}, {'scope': 'ALL', 'side': 'S', 'h': 15, 'items': NULL_ITEMS[3]}]
    frozen, doc = write_frozen(os.path.join(w, 'mine'), 'perp', spec, paths)
    out = os.path.join(w, 'out')
    res = run_ho1(frozen, root, labels, out, registry)
    return {'root': root, 'paths': paths, 'labels': labels, 'frozen': frozen, 'doc': doc, 'out': out, 'res': res, 'w': w}


# ---------------------------------------------------------------- the planted setup passes, the null ones fail

def test_planted_setup_passes_and_null_setups_fail(perp):
    arms = by_arm(perp['res'])
    ids = [s['id'] for s in perp['doc']['setups']]
    planted, nulls = ids[:2], ids[2:]
    for i in planted:
        s = arms[i]
        v = s['verdict']
        assert v['pass'], (i, v['why'])
        assert v['ho1_pass'] and v['bhy_pass'] and v['beats_placebo'] and v['hit_above_base']
        assert s['ho1']['hit'] > s['ho1']['base_hit'] + 0.15
        assert s['heldout']['days'] == 96 and s['heldout']['folds'] == 6 and s['heldout']['folds_won'] >= 4
        assert s['heldout']['terciles_covered'] >= 2 and s['heldout']['terciles_won'] >= 2
    for i in nulls:
        assert not arms[i]['verdict']['pass'], (i, arms[i]['ho1'])
        assert not arms[i]['verdict']['bhy_pass']
    # validated.json: exactly the passing setups, ranked by HO-1 $/h
    val = json.load(open(os.path.join(perp['out'], 'validated.json')))
    assert sorted(s['id'] for s in val['setups']) == sorted(planted)
    ph = [s['usd_per_hour'] for s in val['setups']]
    assert ph == sorted(ph, reverse=True) and val['setups'][0]['rank_ho1'] == 1
    assert val['exit'] == ho1.EXITS['perp'] and val['size_usd'] == 300.0
    # BHY at m = every stage-2 setup is reported and never smaller than the family's
    for s in arms.values():
        assert s['verdict']['p_bhy_all'] >= s['verdict']['p_bhy'] - 1e-12
    # m = the frozen setups only (the book is adjusted on its own row, review fix of Nov 6)
    assert perp['res']['summary']['m_family'] == len(ids) and perp['res']['summary']['m_all'] == 40


def test_bhy_family_is_the_setups_and_the_book_is_adjusted_alone(perp):
    """Review fix (Nov 6): the prereg family is the frozen setups (m = their count); the book trades a subset of their
    trades and is not one of the family's hypotheses, so its p must not shift the setups' ranks. The book is adjusted on
    its own row at m + 1."""
    from oracle.sim import bhy_adjust
    res = perp['res']
    arms = by_arm(res)
    ps = [r['eval']['p'] for r in res['results']]
    adj = bhy_adjust(ps)
    for r, a in zip(res['results'], adj):
        assert arms[r['setup']['id']]['verdict']['p_bhy'] == pytest.approx(float(a), abs=0)
    pb = res['book']['eval']['p']
    assert arms['book']['verdict']['p_bhy'] == pytest.approx(float(bhy_adjust(ps + [pb])[-1]), abs=0)
    ps_all = ps + [1.0] * (40 - len(ps))
    for r, a in zip(res['results'], bhy_adjust(ps_all)):
        assert arms[r['setup']['id']]['verdict']['p_bhy_all'] == pytest.approx(float(a), abs=0)
    # the reviewers' case: a book with a tiny p would have turned a setup at the edge into a pass
    edge = [0.002] + [0.5] * 23
    assert bhy_adjust(edge)[0] > 0.10 and bhy_adjust(edge + [1e-6])[0] < 0.10


def test_prior_openings_raise_the_family_m_and_flag_rows(perp, tmp_path, registry):
    """A logged re-opening of the family (--prior-setups, --flag): the earlier frozen setups join the family m as p = 1
    and every row carries the flag."""
    from oracle.sim import bhy_adjust
    res = run_ho1(perp['frozen'], perp['root'], perp['labels'], str(tmp_path / 'o'), registry, '--prior-setups', '7',
                  '--flag', 'ho1-reopen:111')
    ps = [r['eval']['p'] for r in res['results']]
    assert res['summary']['m_family'] == len(ps) + 7 and res['summary']['prior_setups'] == 7
    a = by_arm(res)
    for r, x in zip(res['results'], bhy_adjust(ps + [1.0] * 7)):
        assert a[r['setup']['id']]['verdict']['p_bhy'] == pytest.approx(float(x), abs=0)
    rows = [json.loads(line) for line in open(tmp_path / 'o' / 'rows.jsonl')]
    assert all('ho1-reopen:111' in r['flags'] for r in rows)


def test_by_tercile_pnl_and_hours_use_one_labeling(perp, tmp_path, registry):
    """Review fix (Nov 6): by_tercile P&L and hours come from the same hour labels (regime v1 labels of the scope's
    assets). BTC is HIGH and ETH LOW in every hour: a BTC-scope setup books HIGH (2304 h), an ETH-scope one LOW, and an
    ALL-scope one MID (the rounded mean of HIGH and LOW), with all 2304 h in MID: no tercile has P&L without hours."""
    w = tmp_path / 'lab'
    os.makedirs(w)
    path = str(w / 'labels.csv.gz')
    with gzip.open(path, 'wt') as f:
        f.write('ts_iso,asset,rv60,q33,q67,tercile,z60,trend\n')
        for a, lab in (('BTC', 'HIGH'), ('ETH', 'LOW')):
            for hh in range(96 * 24):
                iso = np.datetime_as_string(np.datetime64(HOLD_FROM + hh * 3_600_000, 'ms'), unit='s') + 'Z'
                f.write(f'{iso},{a},,,,{lab},,\n')
    res = run_ho1(perp['frozen'], perp['root'], path, str(tmp_path / 'o'), registry)
    want = {'BTC': 'HIGH', 'ETH': 'LOW', 'ALL': 'MID'}
    for s in res['summary']['setups']:
        bt, tot = s['ho1']['by_tercile'], s['ho1']['usd_total']
        k = want[s['scope']]
        assert bt[k]['hours'] == 2304.0 and bt[k]['pnl'] == pytest.approx(tot, abs=1e-4), (s['scope'], bt)
        for o in set(bt) - {k}:
            assert bt[o]['hours'] == 0.0 and bt[o]['pnl'] == 0.0, (s['scope'], bt)
    bt = res['summary']['book']['ho1']['by_tercile']
    assert bt['MID']['hours'] == 2304.0 and bt['LOW']['pnl'] == bt['HIGH']['pnl'] == 0.0
    # with the random fixture labels, P&L per tercile = the trades whose decision hour carries that pooled label
    from allpairs.ho1 import hour_terciles
    lab = hour_terciles(perp['labels'], ['BTC', 'ETH'], HOLD_FROM // 86_400_000, HOLD_TO // 86_400_000 - 1)
    r = next(x for x in perp['res']['results'] if x['setup']['scope'] == 'ALL')
    got = {k_: 0.0 for k_ in ('LOW', 'MID', 'HIGH')}
    for c, rows in ho1.setup_legs(r['setup'], ho1.resolve_parts(perp['doc'], perp['root'], 'perp')):
        for t, usd in zip(c.t[rows], c.trade[rows]):
            got[lab[(int(t) // 86_400_000, int(t) // 3_600_000 % 24)]] += float(usd)
    for k_, v in got.items():
        assert r['eval']['by_tercile'][k_]['pnl'] == pytest.approx(v, abs=1e-4)


def test_null_fixture_nothing_passes(tmp_path, registry):
    root = str(tmp_path / 'parts')
    paths = make_parts(root, 'perp', ('BTC', 'ETH'), 'null', seed=11)
    labels = write_labels(str(tmp_path / 'labels.csv.gz'), ['BTC', 'ETH'])
    spec = [{'scope': 'ALL', 'side': 'L', 'h': 15, 'items': PLANTED_ITEMS}] + [
        {'scope': sc, 'side': sd, 'h': h, 'items': it} for sc, sd, h, it in
        (('ALL', 'S', 60, NULL_ITEMS[0]), ('BTC', 'L', 15, NULL_ITEMS[1]), ('ETH', 'S', 15, NULL_ITEMS[2]), ('ALL', 'L', 60, NULL_ITEMS[3]))]
    frozen, _ = write_frozen(str(tmp_path / 'mine'), 'perp', spec, paths)
    res = run_ho1(frozen, root, labels, str(tmp_path / 'out'), registry)
    arms = by_arm(res)
    assert not any(s['verdict']['pass'] for s in arms.values()), {k: s['verdict']['why'] for k, s in arms.items()}
    assert json.load(open(tmp_path / 'out' / 'validated.json'))['setups'] == []


# ---------------------------------------------------------------- registry rows

def test_rows_validate_with_registry(perp, registry):
    reg, _, _ = ho1.load_registry(registry)
    rows = [json.loads(line) for line in open(os.path.join(perp['out'], 'rows.jsonl'))]
    n = len(perp['doc']['setups'])
    roles = [r['role'] for r in rows]
    assert roles.count('control') == 1 and roles.count('candidate') == n + 1 and roles.count('placebo') == n + 1
    ctl = next(r for r in rows if r['role'] == 'control')
    cands = {r['arm']: r for r in rows if r['role'] == 'candidate'}
    assert ctl['arm'] == 'flat' and set(ctl['by_day'].values()) == {0.0}
    assert set(cands) == {s['id'] for s in perp['doc']['setups']} | {'book'}
    for r in rows:
        err, fl = reg.validate(r)
        assert not err, (r['arm'], err)
        assert not [f for f in fl if f.startswith(('G0:', 'G1:', 'G2:', 'LOCKBOX:'))], (r['arm'], fl)
        assert r['thread'] == 'oracle-setups' and r['family'] == 'oracle-perp-v1' and r['contract_type'] == 'perpetual'
        assert r['data']['source'] == 'history' and r['data']['metric'] == 'usd' and r['data']['engine'] == 'oracle'
        assert r['data']['days'] == DAYS96 and r['code_sha'] == 'c0ffee1' and r['base'] == 'oracle-setups@c0ffee1'
        assert r['modules'][0] == 'oracle-setups' and r['hours'] == 2304.0
        assert r['trial_id'] == reg.make_id(r['thread'], r['family'], r['arm'], r['code_sha'], r['data']['days'], None, None, r['env'])
        if r['role'] != 'control':
            assert r['control'] == ctl['trial_id']
            assert set(r['by_tercile']) == {'LOW', 'MID', 'HIGH'}
    for r in rows:
        if r['role'] == 'placebo':
            assert r['placebo_for'] in cands and r['arm'] == r['placebo_for'] + ':placebo'
    # the heldout blocks are the registry's own ho1_fill, and the verdicts its ho1_pass
    fresh = reg.ho1_fill([{k: v for k, v in r.items() if k != 'heldout'} for r in rows])
    arms = by_arm(perp['res'])
    for r in fresh:
        if r['role'] == 'candidate':
            assert r['heldout'] == cands[r['arm']]['heldout']
            ok, _ = reg.ho1_pass(r['heldout'], reg.contract_type_of(r), r['data']['engine'])
            assert ok == arms[r['arm']]['verdict']['ho1_pass']
    # the registry CLI accepts the shard (the workflow runs exactly this)
    cli = subprocess.run([sys.executable, '-I', registry, 'validate', os.path.join(perp['out'], 'rows.jsonl')], capture_output=True, text=True)
    assert cli.returncode == 0, cli.stdout + cli.stderr


def test_by_day_has_exactly_the_96_hold_days(perp):
    rows = [json.loads(line) for line in open(os.path.join(perp['out'], 'rows.jsonl'))]
    assert DAYS96[0] == '2026-08-01' and DAYS96[-1] == '2026-11-04' and len(DAYS96) == 96
    for r in rows:
        assert sorted(r['by_day']) == DAYS96, r['arm']
        assert all(np.isfinite(v) for v in r['by_day'].values())
    arms = by_arm(perp['res'])
    for r in rows:
        if r['role'] == 'candidate':
            e = arms[r['arm']]['ho1']
            assert abs(sum(r['by_day'].values()) - e['usd_total']) < 1e-3
            assert abs(sum(r['by_tercile'][k]['pnl'] for k in r['by_tercile']) - e['usd_total']) < 1e-3   # rv known on every row
            assert sum(1 for v in r['by_day'].values() if v != 0) == e['active_days']


def test_outputs_are_aggregates_and_parse(perp):
    for f in ('ho1.json', 'validated.json'):
        json.load(open(os.path.join(perp['out'], f)))
    md = open(os.path.join(perp['out'], 'ho1.md')).read()
    assert 'oracle-perp-v1' in md and perp['res']['summary']['frozen_sha256'] in md
    assert sorted(os.listdir(perp['out'])) == ['ho1.json', 'ho1.md', 'rows.jsonl', 'validated.json']   # one .jsonl: the shard


# ---------------------------------------------------------------- the book

def test_book_never_holds_two_perp_positions(perp):
    detail = perp['res']['book']['detail']
    t, hold, part = detail['t'], detail['hold'], detail['part']
    assert len(t) > 50 and set(part.tolist()) == {0, 1}                      # both coins traded
    assert np.all(np.diff(t) > 0)
    assert np.all(t[1:] >= t[:-1] + np.maximum(hold[:-1], 1).astype(np.int64) * MIN), 'two perp positions at once'
    assert detail['candidates'] > len(t)                                     # the one-position rule bound
    # the same setups traded one position per coin would overlap across coins
    res = perp['res']
    per_coin = [r for r in res['results'] if r['setup']['scope'] == 'ALL' and r['setup']['side'] == 'L' and r['setup']['items'] == PLANTED_ITEMS]
    assert per_coin and per_coin[0]['eval']['trades'] > 0
    b = by_arm(res)['book']
    assert b['positions'] == 'one $300 position at a time across all coins'
    assert b['ho1']['trades'] == len(t) and sum(b['setups_used'].values()) == len(t)
    ranked = [s['id'] for s in perp['doc']['setups']]
    assert ranked[0] in b['setups_used']                                      # the best-ranked setup is taken first


# ---------------------------------------------------------------- integrity

def test_refuses_a_frozen_file_whose_sha256_does_not_match(perp, tmp_path, registry):
    d = tmp_path / 'bad'
    shutil.copytree(os.path.dirname(perp['frozen']), d)
    body = (d / 'frozen.json').read_bytes()
    (d / 'frozen.json').write_bytes(body.replace(b'"rank":1', b'"rank":9', 1))         # one edited byte
    with pytest.raises(SystemExit, match='does not match'):
        run_ho1(str(d / 'frozen.json'), perp['root'], perp['labels'], str(tmp_path / 'o1'), registry)
    assert not os.path.exists(tmp_path / 'o1')
    with pytest.raises(SystemExit, match='does not match'):                             # a wrong --sha256
        run_ho1(perp['frozen'], perp['root'], perp['labels'], str(tmp_path / 'o2'), registry, '--sha256', '0' * 64)
    (d / 'frozen.json').write_bytes(body)
    os.remove(d / 'frozen.sha256')
    with pytest.raises(SystemExit, match='refused'):                                   # nothing to check against
        run_ho1(str(d / 'frozen.json'), perp['root'], perp['labels'], str(tmp_path / 'o3'), registry)
    good = hashlib.sha256(body).hexdigest()                                             # the opened hash, passed in
    res = run_ho1(str(d / 'frozen.json'), perp['root'], perp['labels'], str(tmp_path / 'o4'), registry, '--sha256', good)
    assert res['summary']['frozen_sha256'] == good


def test_refuses_parts_that_are_not_the_mined_ones(perp, tmp_path, registry):
    d = tmp_path / 'f'
    doc = json.loads(open(perp['frozen'], 'rb').read())
    doc['parts'][0]['rows_total'] += 1
    os.makedirs(d)
    body = canonical(doc)
    (d / 'frozen.json').write_bytes(body)
    (d / 'frozen.sha256').write_text(hashlib.sha256(body).hexdigest() + '  frozen.json\n')
    with pytest.raises(SystemExit, match='not the mined part'):
        run_ho1(str(d / 'frozen.json'), perp['root'], perp['labels'], str(tmp_path / 'o'), registry)


def test_rows_after_the_hold_are_never_read(perp, tmp_path, registry):
    """A part with garbage rows at and after 2026-11-05 scores exactly like the clean part."""
    root = tmp_path / 'parts'
    shutil.copytree(perp['root'], root)
    p = root / 'perp-BTC'
    P = Part(str(p), mmap=False)
    names = [f[:-4] for f in os.listdir(p) if f.endswith('.npy')]
    arr = {nm: np.array(P[nm]) for nm in names}
    k = 500
    late = {'t': HOLD_TO + np.arange(k, dtype=np.int64) * 5 * MIN}
    for nm, a in arr.items():
        if nm == 't':
            continue
        g = np.full((k,) + a.shape[1:], 1 if a.dtype.kind in 'iu' else np.float32(1e6), dtype=a.dtype)
        late[nm] = g
    write_part(str(p), {k_: v for k_, v in P.meta.items() if k_ not in ('schema', 'n')},
               {nm: np.concatenate([arr[nm], late[nm]]) for nm in names})
    doc = json.loads(open(perp['frozen'], 'rb').read())
    doc['parts'][0]['rows_total'] += k
    d = tmp_path / 'f'
    os.makedirs(d)
    body = canonical(doc)
    (d / 'frozen.json').write_bytes(body)
    (d / 'frozen.sha256').write_text(hashlib.sha256(body).hexdigest() + '  frozen.json\n')
    res = run_ho1(str(d / 'frozen.json'), str(root), perp['labels'], str(tmp_path / 'o'), registry)
    a, b = by_arm(res), by_arm(perp['res'])
    for arm in b:
        assert a[arm]['ho1']['usd_total'] == b[arm]['ho1']['usd_total'] and a[arm]['ho1']['trades'] == b[arm]['ho1']['trades']
    assert res['summary']['parts'][0]['hold_rows'] == perp['res']['summary']['parts'][0]['hold_rows']


# ---------------------------------------------------------------- HO-1 trades exactly as confirmation did

def test_same_trading_as_confirmation_and_sim_placebo(perp):
    res = perp['res']
    hps = ho1.resolve_parts(perp['doc'], perp['root'], 'perp')
    params = types.SimpleNamespace(seeds=8, block=5.0, draws=2000)
    for r in res['results']:
        s = r['setup']
        sp = hps if s['scope'] == 'ALL' else [hp for hp in hps if hp.scope == s['scope']]
        cells = [hp.cell(s['side'], int(s['h'])) for hp in sp]
        c = confirm(s, cells, ho1.HOLD_SPAN, params, r['seed'])          # the miner's stage-2 function, on the hold rows
        e = r['eval']
        assert c['trades'] == e['trades'] and c['days'] == 96
        assert c['usd_day'] == pytest.approx(e['usd_day'], abs=1e-12) and c['placebo_usd_day'] == pytest.approx(e['placebo_usd_day'], abs=1e-12)
        assert (c['p_ev'], c['p_up'], c['hit'], c['base_hit']) == (e['p_ev'], e['p_up'], e['hit'], e['base_hit'])
        if len(sp) == 1:
            rows = ho1.setup_legs(s, sp)[0][1]
            mp = matched_placebo(cells[0].v, s['side'], int(s['h']), rows, 8, r['seed'], span=ho1.HOLD_SPAN)
            assert list(mp) == DAYS96 and np.allclose(list(mp.values()), e['_placebo_daily'])
        assert np.all(cells[0].t[cells[0].B] >= HOLD_FROM)
        assert np.all(cells[0].t[cells[0].B] + int(s['h']) * MIN <= HOLD_TO)


# ---------------------------------------------------------------- the miner's own output, end to end

def test_end_to_end_with_the_miner(perp, tmp_path, registry):
    out = str(tmp_path / 'mine')
    mine_main(['--ct', 'perp', '--parts', perp['root'], '--out', out, '--quiet', '--top', '5', '--beam', '30', '--shortlist', '100',
               '--draws', '500', '--max-frozen', '3'])
    res = run_ho1(os.path.join(out, 'frozen.json'), perp['root'], perp['labels'], str(tmp_path / 'ho1'), registry,
                  '--confirm', os.path.join(out, 'confirm.jsonl'))
    arms = by_arm(res)
    planted = setup_id('perp', 'ALL', 'L', 15, PLANTED_ITEMS)
    assert planted in arms and arms[planted]['verdict']['pass'], arms.get(planted, {}).get('verdict')
    assert res['summary']['params']['draws'] == 500                      # the frozen file's parameters, not defaults
    n_conf = sum(1 for _ in open(os.path.join(out, 'confirm.jsonl')))
    assert res['summary']['m_all'] == n_conf


# ---------------------------------------------------------------- Price Prediction and tennis

def test_pp15_book_one_position_per_asset(tmp_path, registry):
    root = str(tmp_path / 'parts')
    paths = make_parts(root, 'pp15', ('BTC', 'ETH'), 'planted', seed=2)
    labels = write_labels(str(tmp_path / 'labels.csv.gz'), ['BTC', 'ETH'])
    frozen, doc = write_frozen(str(tmp_path / 'mine'), 'pp15', setups_spec('pp15'), paths)
    res = run_ho1(frozen, root, labels, str(tmp_path / 'out'), registry)
    reg, _, _ = ho1.load_registry(registry)
    rows = [json.loads(line) for line in open(tmp_path / 'out' / 'rows.jsonl')]
    for r in rows:
        assert not reg.validate(r)[0] and r['contract_type'] == 'price_prediction' and r['family'] == 'oracle-pp15-v1'
    arms = by_arm(res)
    planted = doc['setups'][0]['id']
    assert arms[planted]['verdict']['pass'], arms[planted]['verdict']['why']
    assert 'replay version' not in arms[planted]['verdict']['ho1_why']          # engine 'oracle': no TS replay gate
    d = res['book']['detail']
    assert len(d['t']) > 20
    for p in (0, 1):
        tp, hp_ = d['t'][d['part'] == p], d['hold'][d['part'] == p]
        assert np.all(tp[1:] >= tp[:-1] + np.maximum(hp_[:-1], 1).astype(np.int64) * MIN), 'two positions on one asset'
    # across assets the book may overlap (one per asset, not one in all)
    assert arms['book']['positions'].startswith('one position per asset')


def test_tennis_tours_are_the_strata_and_book_per_event(tmp_path, registry):
    root = str(tmp_path / 'parts')
    paths = make_parts(root, 'tennis', ('ATP', 'WTA'), 'planted', seed=4)
    frozen, doc = write_frozen(str(tmp_path / 'mine'), 'tennis', setups_spec('tennis'), paths)
    res = run_ho1(frozen, root, None, str(tmp_path / 'out'), registry)          # tennis needs no regime labels
    reg, _, _ = ho1.load_registry(registry)
    rows = [json.loads(line) for line in open(tmp_path / 'out' / 'rows.jsonl')]
    for r in rows:
        assert not reg.validate(r)[0] and r['contract_type'] == 'tennis'
    ctl = next(r for r in rows if r['role'] == 'control')
    assert set(ctl['by_tercile']) == {'ATP', 'WTA'} and all(v['hours'] > 100 for v in ctl['by_tercile'].values())
    cand = {r['arm']: r for r in rows if r['role'] == 'candidate'}
    by_scope = {s['id']: s['scope'] for s in doc['setups']}
    for arm, r in cand.items():
        want = {'ATP', 'WTA'} if arm == 'book' or by_scope[arm] == 'ALL' else {by_scope[arm]}
        assert set(r['by_tercile']) == want, arm
    planted = doc['setups'][0]['id']
    assert by_arm(res)[planted]['verdict']['pass'], by_arm(res)[planted]['verdict']['why']
    # one position per event: the busy key is the event (part, group), and per key the trades never overlap
    d = res['book']['detail']
    assert by_arm(res)['book']['ho1']['trades'] == len(d['t']) > 10
    assert np.all(d['key'] >> 40 == d['part'])
    for k_ in np.unique(d['key']):
        m = d['key'] == k_
        tk, hk = d['t'][m], d['hold'][m]
        assert np.all(tk[1:] >= tk[:-1] + np.maximum(hk[:-1], 1).astype(np.int64) * MIN), 'two positions in one event'
    assert len(np.unique(d['key'])) > 10
