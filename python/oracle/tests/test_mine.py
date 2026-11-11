"""Tests for oracle/mine.py (SPEC 3; prereg OR-H1 "Mining", "Confirmation (discovery B) and freeze", "Adversary") on the
synthetic parts of oracle/fixtures_parts.py. Nothing here is real data.

    cd python && python3 -m pytest -q oracle/tests/test_mine.py
"""
import gzip
import hashlib
import json
import os

import numpy as np
import pytest

from oracle.common import DEV_END, MIN, Part, dev_rows, key, ms, write_part
from oracle.fixtures_parts import PLANTED_ITEMS, make_part, make_parts, planted_setup
from oracle.mine import (PartCell, _exact_stats, assert_dev, load_dev, main, pass_pairs, scope_rows)
from oracle.sim import fire_mask, split_rows


def run_mine(parts, out, *extra):
    return main(['--ct', parts['ct'], '--parts', parts['root'], '--out', out, '--quiet', *extra])


@pytest.fixture(scope='module')
def planted(tmp_path_factory):
    root = str(tmp_path_factory.mktemp('planted'))
    make_parts(root, 'perp', ('BTC', 'ETH'), 'planted', seed=1)
    out = str(tmp_path_factory.mktemp('planted_out'))
    res = run_mine({'ct': 'perp', 'root': root}, out)
    return root, out, res


def same_items(s, items):
    return sorted((i['f'], int(i['v'])) for i in s['items']) == sorted((i['f'], int(i['v'])) for i in items)


def test_planted_setup_found_in_stage1_and_survives_stage2(planted):
    root, out, res = planted
    for scope in ('BTC', 'ETH', 'ALL'):
        for h in (15, 60):
            cell = [s for s in res['stage1'] if s['scope'] == scope and s['side'] == 'L' and s['h'] == h]
            assert len(cell) == 40
            top = min(cell, key=lambda s: s['rank'])
            assert same_items(top, PLANTED_ITEMS), (scope, h, top['items'])
            A = top['dev']['A']
            assert A['n'] >= 300 and A['ev'] > 0 and A['hit_uplift'] > 0.2
            c = next(c for c in res['confirmed'] if c['id'] == top['id'])
            assert c['survivor'] and c['bhy_pass'] and c['dev']['B']['p'] < 1e-6
            assert c['dev']['B']['hit'] > c['dev']['B']['base_hit'] + 0.15
            assert c['dev']['B']['usd_day'] > c['dev']['B']['placebo_usd_day']
    fz = res['frozen']['setups']
    for scope in ('BTC', 'ETH', 'ALL'):
        mine = [s for s in fz if s['scope'] == scope]
        assert 1 <= len(mine) <= 10
        assert any(same_items(s, PLANTED_ITEMS) for s in mine)
    assert [s['rank'] for s in fz] == list(range(1, len(fz) + 1))
    # the frozen file is the canonical JSON its sha256 names
    body = open(os.path.join(out, 'frozen.json'), 'rb').read()
    assert open(os.path.join(out, 'frozen.sha256')).read().split()[0] == hashlib.sha256(body).hexdigest() == res['sha256']
    assert json.loads(body)['setups'][0]['items']
    for name in ('stage1.jsonl.gz', 'confirm.jsonl', 'report.md', 'base_rates.json', 'lift/ALL-L15.csv', 'lift/BTC-S60.csv',
                 'instances/BTC-L15.csv.gz', 'instances/ETH-S60.csv.gz'):
        assert os.path.exists(os.path.join(out, name)), name
    with gzip.open(os.path.join(out, 'stage1.jsonl.gz'), 'rt') as f:
        assert sum(1 for _ in f) == len(res['stage1'])
    # every frozen setup carries its adversary on B; the cost stress costs money
    s0 = fz[0]
    ad = s0['adversary']
    assert ad['cost']['usd_day'] < ad['base']['usd_day'] and ad['base']['usd_day'] == pytest.approx(s0['dev']['B']['usd_day'])
    # N_raw counts singles + different-feature pairs + distinct triples of every cell
    assert res['n_raw'] == sum(s['N_raw']['total'] for s in res['summaries'].values())
    s = res['summaries']['BTC-L15']
    I = s['N_raw']['singles']
    assert s['N_raw']['pairs'] < I * (I - 1) // 2 and s['N_raw']['triples'] > 0


def direct_cell_stats(path, side, h, items):
    """Independent recomputation from the raw part directory: n, mean trade, residual-trade uplift, hit, base hit."""
    p = Part(path)
    t = np.asarray(p['t'])
    keep = dev_rows(t, h)
    idx = np.flatnonzero(keep)
    tr = np.asarray(p[key('trade', side, h)])[idx].astype(float)
    hit = np.asarray(p[key('hit', side, h)])[idx].astype(float)
    st = np.asarray(p[f'stratum_{side}'])[idx].astype(int)
    ok = np.asarray(p[key('ok', side, h)])[idx] == 1
    from oracle.common import split_of
    A = ok & (st >= 0) & np.isfinite(tr) & (split_of(t[idx], h, p.ct) == 'A')
    names = [f['name'] for f in p.features]
    X = np.asarray(p['X'])[idx]
    S = A.copy()
    for it in items:
        S &= X[:, names.index(it['f'])] == it['v']
    mt = {s: tr[A & (st == s)].mean() for s in np.unique(st[A])}
    mh = {s: hit[A & (st == s)].mean() for s in np.unique(st[A])}
    base_t = np.array([mt[s] for s in st[S]])
    base_h = np.array([mh[s] for s in st[S]])
    return {'n': int(S.sum()), 'ev': tr[S].mean(), 'uplift': (tr[S] - base_t).mean(), 'hit': hit[S].mean(),
            'base_hit': base_h.mean(), 'hit_uplift': (hit[S] - base_h).mean()}


def test_residual_trick_equals_direct(planted):
    root, out, res = planted
    path = os.path.join(root, 'perp-BTC')
    # the stage-1 record of the planted setup equals a direct computation from the raw part
    s = next(s for s in res['stage1'] if s['scope'] == 'BTC' and s['side'] == 'L' and s['h'] == 60 and s['rank'] == 1)
    d = direct_cell_stats(path, 'L', 60, s['items'])
    A = s['dev']['A']
    assert A['n'] == d['n']
    for k in ('ev', 'uplift', 'hit', 'base_hit', 'hit_uplift'):
        assert A[k] == pytest.approx(d[k], abs=1e-9), k
    # the matrix products: every pair's Z'(w Z) / Z'Z equals the direct residual mean (float32 products, f64 sums)
    v = load_dev(path, 'perp')
    pc = PartCell(v, 'L', 15)
    items = pc.items
    colU = np.array([it.col for it in items], dtype=np.int64)
    valU = np.array([it.v for it in items], dtype=np.int8)
    P, packed = pass_pairs(pc, colU, valU, 4096)
    X = v['X'][pc.A]
    rng = np.random.default_rng(0)
    for _ in range(40):
        a, b = rng.choice(len(items), 2, replace=False)
        S = (X[:, colU[a]] == valU[a]) & (X[:, colU[b]] == valU[b])
        n = int(S.sum())
        assert P[0, a, b] == n
        if n:
            assert P[1, a, b] / n == pytest.approx(pc.rt[S].mean(), abs=1e-4)
            assert P[2, a, b] / n == pytest.approx(pc.rh[S].mean(), abs=1e-5)
            assert P[3, a, b] / n == pytest.approx(pc.trade[S].mean(), abs=1e-4)
            assert P[4, a, b] == pytest.approx((pc.rt[S] ** 2).sum(), rel=1e-4)
    # and the bit-packed exact path agrees with the direct masks (counts, sums, distinct groups)
    sets = np.array([[0, 5, -1], [1, 7, 12], [3, -1, -1]], dtype=np.int64)
    B, Wr, gid, ng = scope_rows([pc], [0], [packed])
    ex, grp = _exact_stats(B, sets, Wr, gid, ng)
    for k, (a, b, c) in enumerate(sets):
        S = np.ones(pc.nA, bool)
        for u in (a, b, c):
            if u >= 0:
                S &= X[:, colU[u]] == valU[u]
        assert ex[k, 0] == S.sum()
        assert ex[k, 1] == pytest.approx(pc.rt[S].sum(), abs=1e-6)
        assert ex[k, 5] == pytest.approx(pc.hit[S].sum())
        assert grp[k] == len(np.unique(pc.gid[S]))


def test_dev_mask_refuses_hold_rows(tmp_path):
    path = make_part(str(tmp_path), 'perp', 'BTC', 'planted', seed=3)
    p = Part(path)
    t = np.asarray(p['t'])
    assert (t >= DEV_END).any()                       # the part does hold HO-1 rows ...
    v = load_dev(path, 'perp')
    assert v.n == int(dev_rows(t, 15).sum())          # ... and the miner's view stops at DEV_END - 15 min
    assert (v['t'] + 15 * MIN <= DEV_END).all()
    for name, a in v.arrays.items():
        assert len(a) == v.n, name
    pc = PartCell(v, 'L', 60)
    assert (v['t'][pc.B] + 60 * MIN <= DEV_END).all()
    with pytest.raises(AssertionError):
        assert_dev(np.array([DEV_END - 10 * MIN]), 15)
    # a part whose t is not sorted (an HO-1 row early) is refused rather than leaked
    bad = str(tmp_path / 'bad')
    os.makedirs(bad)
    arrays = {n_[:-4]: np.load(os.path.join(path, n_)) for n_ in os.listdir(path) if n_.endswith('.npy')}
    meta = json.load(open(os.path.join(path, 'meta.json')))
    tt = arrays['t'].copy()
    tt[5] = DEV_END + 3 * 60 * MIN
    arrays['t'] = tt
    write_part(os.path.join(bad, 'perp-BTC'), meta, arrays)
    with pytest.raises((AssertionError, ValueError)):
        load_dev(os.path.join(bad, 'perp-BTC'), 'perp')


def test_hold_rows_never_influence_the_result(tmp_path):
    """Run the miner, overwrite every row with t + min(h) > DEV_END (labels and features) with garbage, run again:
    every output is identical."""
    root = str(tmp_path / 'parts')
    path = make_part(root, 'perp', 'BTC', 'planted', seed=4)
    args = ('--top', '8', '--draws', '300', '--beam', '50')
    r1 = run_mine({'ct': 'perp', 'root': root}, str(tmp_path / 'o1'), *args)
    t = np.load(os.path.join(path, 't.npy'))
    late = t + 15 * MIN > DEV_END
    assert late.sum() > 1000
    rng = np.random.default_rng(9)
    for fn in os.listdir(path):
        if not fn.endswith('.npy') or fn == 't.npy':
            continue
        a = np.load(os.path.join(path, fn))
        if a.dtype.kind == 'f':
            a[late] = 1e6
        elif fn == 'X.npy':
            a[late] = rng.integers(-1, 2, a[late].shape)
        elif fn.startswith(('hit', 'ok')):
            a[late] = 1
        np.save(os.path.join(path, fn), a)
    r2 = run_mine({'ct': 'perp', 'root': root}, str(tmp_path / 'o2'), *args)
    assert r1['sha256'] == r2['sha256']
    assert json.dumps(r1['confirmed'], default=str) == json.dumps(r2['confirmed'], default=str)


@pytest.mark.parametrize('seed', [11, 23, 37])
def test_null_parts_pass_nothing(tmp_path, seed):
    root = str(tmp_path / 'parts')
    make_parts(root, 'perp', ('BTC',), 'null', seed=seed)
    res = run_mine({'ct': 'perp', 'root': root}, str(tmp_path / 'out'), '--draws', '1000')
    surv = [c for c in res['confirmed'] if c['survivor']]
    assert len(res['confirmed']) == 160
    assert len(surv) <= 1, [(c['id'], c['dev']['B']['p']) for c in surv]
    ps = np.array([c['dev']['B']['p'] for c in res['confirmed']])
    assert np.median(ps) > 0.2                               # stage-2 p values of null setups are not small


def test_kalshi_side_features_and_group_deflation(tmp_path):
    root = str(tmp_path / 'parts')
    make_parts(root, 'pp15', ('BTC', 'ETH'), 'planted', seed=5, hours=8)
    res = run_mine({'ct': 'pp15', 'root': root}, str(tmp_path / 'out'), '--top', '20', '--draws', '1000')
    for scope in ('BTC', 'ETH', 'ALL'):
        cell = [s for s in res['stage1'] if s['scope'] == scope and s['side'] == 'Y' and s['h'] == 15]
        top = min(cell, key=lambda s: s['rank'])
        assert same_items(top, PLANTED_ITEMS), (scope, top['items'])
        A = top['dev']['A']
        assert A['n_eff'] == A['groups'] and A['groups'] < A['n']           # n deflated to distinct windows (contracts)
        c = next(c for c in res['confirmed'] if c['id'] == top['id'])
        assert c['survivor']
    # side-relative k_price is one mined feature per side (suffix stripped), read from that side's own column
    lift_n = open(os.path.join(str(tmp_path / 'out'), 'lift', 'BTC-N15.csv')).read()
    assert '\nk_price,' in lift_n and 'k_price@' not in lift_n
    v = load_dev(os.path.join(root, 'pp15-BTC'), 'pp15')
    names = [f['name'] for f in v.features]
    for side in ('Y', 'N'):
        f = fire_mask(v, {'side': side, 'items': [{'f': 'k_price', 'v': 3}]})
        assert (f == (v['X'][:, names.index(f'k_price@{side}')] == 3)).all()


def test_tennis_close_rule_and_event_busy(tmp_path):
    root = str(tmp_path / 'parts')
    path = make_part(root, 'tennis', 'ATP', 'planted', seed=6, hours=12)
    res = run_mine({'ct': 'tennis', 'root': root}, str(tmp_path / 'out'), '--draws', '500', '--beam', '100')
    v = load_dev(path, 'tennis')
    s = split_rows(v, 15)
    assert ((s == 'A') <= (v['close'] <= ms('2026-06-22'))).all()             # A rows' markets close inside A
    cell = [x for x in res['stage1'] if x['side'] == 'Y' and x['h'] == 15]
    top = min(cell, key=lambda x: x['rank'])
    # n_eff = distinct events saturates (every event has ~180 rows), so t ranks by mean / sd and lucky triple subsets of
    # the planted pair can outrank it: the top contains the planted items, and the pair itself is kept and survives
    want = {(i['f'], i['v']) for i in PLANTED_ITEMS}
    assert want <= {(i['f'], i['v']) for i in top['items']}
    assert top['dev']['A']['groups'] == top['dev']['A']['n_eff'] < 400
    pair = next(x for x in cell if same_items(x, PLANTED_ITEMS))
    assert next(c for c in res['confirmed'] if c['id'] == pair['id'])['survivor']
    assert planted_setup('tennis', 15)['side'] == 'Y'
    # one tour only: its survivors are not frozen (the HO-1 strata are the tours: one stratum can never pass)
    assert res['frozen']['setups'] == [] and res['frozen']['freeze_scopes'] == []
    assert any('pooled ATP+WTA scope only' in d for d in res['frozen']['deviations'])


def test_tennis_freezes_from_the_pooled_scope_only(tmp_path):
    """Review fix (Nov 6): a single-tour tennis setup has one HO-1 stratum (prereg 'tennis: tour'), so registry ho1_pass
    ('2 strata won') fails it whatever its P&L; only pooled ATP+WTA survivors freeze. Other contract types are unchanged."""
    from oracle.mine import freeze_scopes
    assert freeze_scopes('tennis', ['ATP', 'WTA']) == ['ALL'] and freeze_scopes('tennis', ['ATP']) == []
    assert freeze_scopes('perp', ['BTC', 'ETH']) == ['BTC', 'ETH', 'ALL'] and freeze_scopes('pp15', ['BTC']) == ['BTC']
    root = str(tmp_path / 'parts')
    make_part(root, 'tennis', 'ATP', 'planted', seed=6, hours=12)
    make_part(root, 'tennis', 'WTA', 'planted', seed=7, hours=12)
    res = run_mine({'ct': 'tennis', 'root': root}, str(tmp_path / 'out'), '--draws', '500', '--beam', '100')
    assert any(c['survivor'] and c['scope'] != 'ALL' for c in res['confirmed'])       # single-tour survivors exist ...
    fz = res['frozen']['setups']
    assert fz and {s['scope'] for s in fz} == {'ALL'}                                 # ... but only pooled ones freeze
    assert res['frozen']['freeze_scopes'] == ['ALL']
