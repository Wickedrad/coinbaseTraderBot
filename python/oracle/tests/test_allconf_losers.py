"""ho1.py --all-confirmed (OR-AMEND-1) and losers.py (the loser study) on synthetic fixture parts (oracle/fixtures_parts.py).
research/registry.py is read from origin/claude/project-thread-79ntof (skipped when the checkout does not have it)."""
from __future__ import annotations

import hashlib
import json
import os
import shutil

import numpy as np
import pytest

from oracle import ho1, losers
from oracle.common import DEV_END, HOLD_FROM, HOLD_TO, MIN, SPLITS, Part
from oracle.fixtures_parts import PLANTED_ITEMS, make_parts
from oracle.mine import PartB, PartCell, load_dev, main as mine_main, setup_id
from oracle.sim import bhy_adjust
from oracle.tests.test_ho1 import registry, run_ho1, write_frozen, write_labels  # noqa: F401  (registry is a fixture)

MINE_ARGS = ['--quiet', '--top', '5', '--beam', '30', '--shortlist', '100', '--draws', '500', '--max-frozen', '3']


@pytest.fixture(scope='module')
def mined(tmp_path_factory):
    """Planted perp parts (BTC, ETH), mined: confirm.jsonl and frozen.json; plus a zero-setup frozen file of the same parts."""
    root = str(tmp_path_factory.mktemp('ac_parts'))
    paths = make_parts(root, 'perp', ('BTC', 'ETH'), 'planted', seed=1)
    w = str(tmp_path_factory.mktemp('ac'))
    labels = write_labels(os.path.join(w, 'labels.csv.gz'), ['BTC', 'ETH'])
    out = os.path.join(w, 'mine')
    mine_main(['--ct', 'perp', '--parts', root, '--out', out] + MINE_ARGS)
    fp = json.load(open(os.path.join(out, 'frozen.json')))['params']           # the same statistics parameters as the miner's
    zero, _ = write_frozen(os.path.join(w, 'zero'), 'perp', [], paths, {k_: fp[k_] for k_ in ('seeds', 'block', 'draws', 'q', 'seed')})
    return {'root': root, 'paths': paths, 'labels': labels, 'mine': out, 'confirm': os.path.join(out, 'confirm.jsonl'),
            'frozen': os.path.join(out, 'frozen.json'), 'zero': zero, 'w': w}


@pytest.fixture(scope='module')
def allconf(mined, registry):
    out = os.path.join(mined['w'], 'ho1all')
    res = run_ho1(mined['zero'], mined['root'], mined['labels'], out, registry, '--all-confirmed', '--confirm', mined['confirm'])
    return {'res': res, 'out': out}


def confirm_rows(path):
    return [json.loads(line) for line in open(path) if line.strip()]


# ---------------------------------------------------------------- ho1 --all-confirmed

def test_all_confirmed_scores_every_confirmed_setup_with_zero_frozen(mined, allconf):
    conf = confirm_rows(mined['confirm'])
    s = allconf['res']['summary']
    assert s['n_frozen'] == 0 and s['mode'] == 'all-confirmed' and s['book'] is None
    assert [x['id'] for x in s['setups']] == [c['id'] for c in conf]
    assert s['m_all'] == len(conf) == s['counts']['scored'] == s['counts']['confirmed']
    planted = setup_id('perp', 'ALL', 'L', 15, PLANTED_ITEMS)
    by = {x['id']: x for x in s['setups']}
    assert planted in by and by[planted]['verdict']['rules_pass'], by[planted]['verdict']['why']
    # BHY at m = every confirmed setup of the type
    adj = bhy_adjust([x['ho1']['p'] for x in s['setups']])
    assert np.allclose([x['verdict']['p_bhy_all'] for x in s['setups']], adj)
    assert s['counts']['rules_pass'] == sum(x['verdict']['rules_pass'] for x in s['setups'])
    assert s['counts']['bhy_pass'] == sum(x['verdict']['rules_pass'] and x['verdict']['p_bhy_all'] <= 0.10 for x in s['setups'])


def test_all_confirmed_rows_are_flagged_candidates_without_a_book(mined, allconf, registry):
    reg, _, _ = ho1.load_registry(registry)
    rows = [json.loads(line) for line in open(os.path.join(allconf['out'], 'rows.jsonl'))]
    n = len(confirm_rows(mined['confirm']))
    assert len(rows) == 1 + 2 * n                                       # control + candidate and placebo per setup, no book
    assert not any(r['arm'] in ('book', 'book:placebo') for r in rows)
    for r in rows:
        assert not reg.validate(r)[0]
        assert r['family'] == 'oracle-perp-allconf-v1'
        assert 'all-confirmed' in r['flags'] and ho1.DEV_FLAG in r['flags']
    cands = [r for r in rows if r['role'] == 'candidate']
    assert len(cands) == n and all(r['env']['ORACLE_MODE'] == 'all-confirmed' for r in cands)
    assert all('not a pre-registered pass' in r['verdict'] for r in cands)


def test_all_confirmed_numbers_equal_the_frozen_mode(mined, allconf, registry, tmp_path):
    """A setup that is both frozen and confirmed gets the same HO-1 numbers in both modes (same trading, seed, placebo)."""
    fr = run_ho1(mined['frozen'], mined['root'], mined['labels'], str(tmp_path / 'fz'), registry, '--confirm', mined['confirm'])
    a = {x['id']: x for x in allconf['res']['summary']['setups']}
    common = [x for x in fr['summary']['setups'] if x['id'] in a]
    assert common
    for x in common:
        y = a[x['id']]
        for k_ in ('trades', 'usd_total', 'placebo_usd_total', 'p', 'hit', 'base_hit', 'folds_won', 'fold_usd', 'by_tercile'):
            assert x['ho1'][k_] == y['ho1'][k_], (x['id'], k_)
        assert x['heldout'] == y['heldout']
        assert x['verdict']['ho1_pass'] == y['verdict']['ho1_pass']


def test_lockbox_candidates_are_the_rule(mined, allconf):
    s = allconf['res']['summary']
    lb = json.load(open(os.path.join(allconf['out'], 'lockbox_candidates.json')))
    want = sorted([x for x in s['setups'] if x['verdict']['rules_pass']], key=lambda x: (-x['ho1']['usd_per_hour'], x['id']))[:10]
    assert [x['id'] for x in lb['setups']] == [x['id'] for x in want]
    assert [x['rank_lockbox'] for x in lb['setups']] == list(range(1, len(want) + 1))
    assert lb['n_rules_pass'] == s['counts']['rules_pass']
    assert lb['lockbox']['from'] == '2026-11-06T05:00Z' and lb['lockbox']['to'] == '2026-11-13T05:00Z'
    assert lb['lockbox']['days_won_min'] == 4 and lb['lockbox']['days'] == 7
    assert lb['rule'].endswith('OR-AMEND-1.md') and lb['rule_sha256'] == hashlib.sha256(
        open(os.path.join(os.path.dirname(ho1.__file__), 'prereg', 'OR-AMEND-1.md'), 'rb').read()).hexdigest()
    # top 10 at most even when more pass
    sel = ho1.lockbox_select([{'id': f's{i}', 'verdict': {'rules_pass': True}, 'ho1': {'usd_per_hour': float(i)}} for i in range(14)]
                             + [{'id': 'x', 'verdict': {'rules_pass': False}, 'ho1': {'usd_per_hour': 99.0}}])
    assert [x['id'] for x in sel] == [f's{i}' for i in range(13, 3, -1)]


def test_all_confirmed_report_is_aggregates(allconf):
    md = open(os.path.join(allconf['out'], 'ho1-all.md')).read()
    assert 'Descriptive trial' in md and 'not a pre-registered' in md and 'Lockbox L1 candidates' in md
    assert 'Top ' in md and 'HO-1 $/day over the scored setups' in md
    s = allconf['res']['summary']
    assert len(s['top']) == min(20, len(s['setups']))
    assert [x['ho1']['usd_day'] for x in s['top']] == sorted([x['ho1']['usd_day'] for x in s['setups']], reverse=True)[:len(s['top'])]
    for line in md.splitlines():                                         # no per-decision timestamps in the public report
        assert '2026-08-1' not in line or 'Aug' in line or 'lockbox' in line.lower()


def test_all_confirmed_keeps_the_frozen_sha_check_and_needs_confirm(mined, registry, tmp_path):
    d = tmp_path / 'z'
    shutil.copytree(os.path.dirname(mined['zero']), d)
    with open(d / 'frozen.json', 'ab') as f:
        f.write(b' ')
    with pytest.raises(SystemExit, match='does not match'):
        run_ho1(str(d / 'frozen.json'), mined['root'], mined['labels'], str(tmp_path / 'o'), registry, '--all-confirmed',
                '--confirm', mined['confirm'])
    with pytest.raises(SystemExit, match='--confirm'):
        run_ho1(mined['zero'], mined['root'], mined['labels'], str(tmp_path / 'o2'), registry, '--all-confirmed')


def test_all_confirmed_with_an_empty_confirm_file(mined, registry, tmp_path):
    p = tmp_path / 'confirm.jsonl'
    p.write_text('')
    res = run_ho1(mined['zero'], mined['root'], mined['labels'], str(tmp_path / 'o'), registry, '--all-confirmed', '--confirm', str(p))
    assert res['summary']['counts']['scored'] == 0 and res['lockbox']['setups'] == []
    rows = [json.loads(line) for line in open(tmp_path / 'o' / 'rows.jsonl')]
    assert [r['role'] for r in rows] == ['control']


# ---------------------------------------------------------------- losers.py

@pytest.fixture(scope='module')
def lost(mined):
    out = os.path.join(mined['w'], 'losers')
    doc = losers.main(['--ct', 'perp', '--parts', mined['root'], '--confirm', mined['confirm'], '--out', out, '--quiet', '--ho1'])
    return {'doc': doc, 'out': out}


def test_losers_trades_are_the_confirmation_trades(mined, lost):
    """Per setup the B trades are exactly mine.PartB.trade_on's (the confirm step), and the HO-1 trades ho1.HoldCell's."""
    conf = confirm_rows(mined['confirm'])
    per = {s['id']: s for s in lost['doc']['splits']['B']['setups']}
    perH = {s['id']: s for s in lost['doc']['splits']['H']['setups']}
    views = {Part(p).scope: load_dev(p, 'perp') for p in mined['paths']}
    hps = {Part(p).scope: ho1.HoldPart(p, 'perp', i) for i, p in enumerate(mined['paths'])}
    for c in conf[:8]:
        scopes = list(views) if c['scope'] == 'ALL' else [c['scope']]
        nB = nH = 0
        usdB = 0.0
        for sc in scopes:
            pb = PartB(PartCell(views[sc], c['side'], int(c['h'])))
            fire = np.zeros(pb.v.n, dtype=bool)
            from oracle.sim import fire_mask
            fire[pb.B] = fire_mask(pb.v, c, pb.B)
            rows = pb.trade_on(fire)
            nB += len(rows)
            usdB += float(pb.trade[rows].sum())
            hc = hps[sc].cell(c['side'], int(c['h']))
            nH += len(hc.trade_on(hc.fire(c)))
        assert per[c['id']]['trades'] == nB == c['dev']['B']['trades'], c['id']
        assert abs(per[c['id']]['usd_total'] - usdB) < 1e-6
        assert abs(per[c['id']]['usd_total'] - c['dev']['B']['usd_total']) < 1e-4
        assert perH[c['id']]['trades'] == nH


def test_losers_b_rows_never_reach_the_hold(mined, tmp_path):
    """Without --ho1 nothing at or after DEV_END is read: poisoning those rows changes nothing."""
    root = tmp_path / 'parts'
    shutil.copytree(mined['root'], root)
    for d in os.listdir(root):
        p = root / d
        t = np.load(p / 't.npy')
        late = t >= DEV_END - 15 * MIN
        for f in os.listdir(p):
            if f.startswith(('trade_', 'best_', 'hit_', 'hold_')):
                a = np.load(p / f)
                a[late] = (np.nan if a.dtype.kind == 'f' else 0)
                np.save(p / f, a)
    a = losers.main(['--ct', 'perp', '--parts', mined['root'], '--confirm', mined['confirm'], '--out', str(tmp_path / 'a'), '--quiet'])
    b = losers.main(['--ct', 'perp', '--parts', str(root), '--confirm', mined['confirm'], '--out', str(tmp_path / 'b'), '--quiet'])
    assert 'H' not in a['splits']
    assert json.dumps(a['splits']['B']['setups'], sort_keys=True) == json.dumps(b['splits']['B']['setups'], sort_keys=True)
    v = losers.load_B(mined['paths'][0], 'perp')
    assert v['t'].min() >= SPLITS['perp']['B'][0] and v['t'].max() + 15 * MIN <= DEV_END


def test_losers_statistics(mined, lost):
    r = lost['doc']['splits']['B']
    assert r['trades'] == r['losers'] + r['winners'] > 0
    assert sum(r['loser_exits'].values()) == r['losers'] and r['loser_exits']['take-profit'] == 0
    # perp (no stop): a loser exits at the horizon
    assert r['loser_exits']['time'] == r['losers'] and r['loser_exits']['stop'] == 0
    b = r['loser_best_share']
    assert 1 >= b['gt0'] >= b['ge1'] >= b['ge_half_target'] >= b['ge_target'] >= 0
    assert len(r['lift']) <= 15 and all(x['losers'] + x['winners'] >= 30 for x in r['lift'])
    assert [x['lift'] for x in r['lift']] == sorted([x['lift'] for x in r['lift']], reverse=True)
    names = {x['feature'] for x in lost['doc']['splits']['B']['setups'][0]['lift']} | {x['feature'] for x in r['lift']}
    assert names
    fx = r['fix']
    assert [x['level_frac'] for x in fx] == [0.25, 0.5, 0.75]
    for x in fx:
        assert x['usd_upper_bound'] == pytest.approx(x['usd_actual'] + x['usd_change'])
        assert x['usd_recovered_on_losers'] >= 0 and x['losers_rescued'] <= x['losers']
    assert fx[0]['losers_rescued'] >= fx[1]['losers_rescued'] >= fx[2]['losers_rescued']
    md = open(os.path.join(lost['out'], 'losers.md')).read()
    assert '## Discovery B' in md and '## HO-1' in md and 'What would fix it' in md and 'upper bound' in md
    assert json.load(open(os.path.join(lost['out'], 'losers.json')))['schema'] == 'oracle-losers-1'


def test_losers_lift_finds_an_over_represented_state(tmp_path):
    """A planted loser state: on a null part, make every trade with fs05 = +1 lose; it tops the pooled lift table."""
    root = str(tmp_path / 'parts')
    paths = make_parts(root, 'perp', ('BTC',), 'null', seed=5, hours=6)
    p = paths[0]
    X = np.load(os.path.join(p, 'X.npy'))
    meta = json.load(open(os.path.join(p, 'meta.json')))
    j = [f['name'] for f in meta['features']].index('fs05')
    for h in (15, 60):
        tr = np.load(os.path.join(p, f'trade_L{h}.npy'))
        tr[(X[:, j] == 1) & np.isfinite(tr)] = -2.0
        np.save(os.path.join(p, f'trade_L{h}.npy'), tr)
    conf = tmp_path / 'confirm.jsonl'
    conf.write_text(json.dumps({'id': 'x1', 'ct': 'perp', 'scope': 'BTC', 'side': 'L', 'h': 15, 'items': [{'f': 'fb00', 'v': 1}]}) + '\n')
    doc = losers.main(['--ct', 'perp', '--parts', root, '--confirm', str(conf), '--out', str(tmp_path / 'o'), '--quiet'])
    top = doc['splits']['B']['lift'][0]
    assert (top['feature'], top['value']) == ('fs05', 1) and top['winners'] == 0


def test_losers_exit_kinds():
    """perp-rev stop (exit before the horizon without a take-profit), tennis settlement (closed inside the hold), pp ride."""
    from oracle.sim import ArrayPart
    t = np.array([0, 10, 20, 30], dtype=np.int64) * MIN + HOLD_FROM
    base = {'t': t, 'hit_L15': np.array([1, 0, 0, 0], np.uint8), 'hold_L15': np.array([3, 4, 15, 15], np.uint16),
            'trade_L15': np.array([1.0, -1.0, -0.5, 0.2], np.float32)}
    v = ArrayPart({'ct': 'perp-rev', 'stop_bps': 30, 'target_bps': 60}, dict(base))
    assert [losers.EXITS[i] for i in losers.exit_kind(v, 'L', 15, np.arange(4))] == ['take-profit', 'stop', 'time', 'time']
    v = ArrayPart({'ct': 'perp'}, dict(base))
    assert [losers.EXITS[i] for i in losers.exit_kind(v, 'L', 15, np.arange(4))] == ['take-profit', 'time', 'time', 'time']
    tb = {k_.replace('L15', 'Y15'): x for k_, x in base.items()}
    tb['close'] = t + np.array([60, 4, 99, 15]) * MIN
    v = ArrayPart({'ct': 'tennis'}, tb)
    assert [losers.EXITS[i] for i in losers.exit_kind(v, 'Y', 15, np.arange(4))] == ['take-profit', 'settlement', 'time', 'settlement']
    pb = dict(tb)
    pb['kmin'] = np.array([1, 11, 1, 0], np.uint8)
    v = ArrayPart({'ct': 'pp15', 'window_min': 15}, pb)
    assert [losers.EXITS[i] for i in losers.exit_kind(v, 'Y', 15, np.arange(4))] == ['take-profit', 'settlement', 'settlement', 'settlement']
    pb['hold_Y15'] = np.array([3, 3, 13, 14], np.uint16)
    v = ArrayPart({'ct': 'pp15', 'window_min': 15}, pb)
    assert [losers.EXITS[i] for i in losers.exit_kind(v, 'Y', 15, np.arange(4))] == ['take-profit', 'time', 'time', 'time']
    # perp-rev target $ = notional x M bps
    v = ArrayPart({'ct': 'perp-rev', 'target_bps': 60, 'notional_usd': 300.0}, {'t': t, 'notional': np.full(4, 300.0, np.float32)})
    assert np.allclose(losers.target_usd(v, np.arange(4)), 1.8)
    assert HOLD_TO > HOLD_FROM
