"""Tests for oracle/cut.py (prereg python/oracle/prereg/OR-H3.md: the Price Prediction loser cut) on the synthetic parts and
cut-label sidecars of oracle/fixtures_cut.py and a synthetic regime-label file. Nothing here is real data.

    cd python && python3 -m pytest -q oracle/tests/test_cut.py

research/registry.py is read from origin/claude/project-thread-79ntof (the HO-1 tests skip when the checkout lacks it).
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import types

import numpy as np
import pytest

from allpairs.fees import contracts_for_stake, taker_fee
from oracle import cut
from oracle.common import DAY, DEV_END, HOLD_FROM, HOLD_TO, MIN, Part, write_part
from oracle.fixtures_cut import make, make_part
from oracle.mine import canonical
from oracle.pp import KINDS, simulate
from oracle.sim import ArrayPart, bhy_adjust, resolve, trade_sim
from oracle.tests.test_ho1 import registry, write_labels  # noqa: F401  (registry is a fixture)

N15 = 15
QUIET = lambda m: None  # noqa: E731


# ---------------------------------------------------------------- fixtures

@pytest.fixture(scope='module')
def planted(tmp_path_factory):
    """Momentum paths (a falling side keeps falling): the pp15 cut has something to find. Searched once."""
    root = str(tmp_path_factory.mktemp('cut_planted'))
    fx = make(root)
    out = os.path.join(root, 'search')
    res = cut.search(fx['parts'], fx['cut'], out, 'c0ffee1', log=QUIET)
    return dict(fx, root=root, out=out, res=res, frozen=os.path.join(out, 'frozen-cut.json'))


@pytest.fixture(scope='module')
def null(tmp_path_factory):
    """Martingale paths (no momentum): nothing to find."""
    root = str(tmp_path_factory.mktemp('cut_null'))
    parts, cr = os.path.join(root, 'parts'), os.path.join(root, 'cut')
    for i, (ct, a, k) in enumerate((('pp15', 'BTC', 1), ('pp15', 'ETH', 1), ('pp60', 'BTC', 2))):
        make_part(parts, cr, ct, a, per_day=6 if ct == 'pp15' else 3, seed=5 + i, momentum=0.0, strikes=k)
    out = os.path.join(root, 'search')
    res = cut.search(parts, cr, out, 'c0ffee1', log=QUIET)
    return {'parts': parts, 'cut': cr, 'out': out, 'res': res, 'frozen': os.path.join(out, 'frozen-cut.json'), 'root': root}


@pytest.fixture(scope='module')
def regime(planted):
    return write_labels(os.path.join(planted['root'], 'labels.csv.gz'), ['BTC', 'ETH'])


def run_ho1(fx, frozen, out, registry, labels, ct='pp15', *extra):
    return cut.main(['ho1', '--frozen', frozen, '--ct', ct, '--parts', fx['parts'], '--cut-labels', fx['cut'], '--regime', labels,
                     '--registry', registry, '--out', out, '--run', '4242', '--code-sha', 'c0ffee1', '--quiet'] + list(extra))


@pytest.fixture(scope='module')
def ho(planted, regime, registry):
    out = os.path.join(planted['root'], 'ho1-pp15')
    res = run_ho1(planted, planted['frozen'], out, registry, regime)
    return {'res': res, 'out': out}


def resign(doc, d):
    """Write doc as frozen-cut.json (canonical) plus a matching frozen-cut.sha256 into d."""
    os.makedirs(d, exist_ok=True)
    body = canonical(doc)
    with open(os.path.join(d, 'frozen-cut.json'), 'wb') as f:
        f.write(body)
    with open(os.path.join(d, 'frozen-cut.sha256'), 'w') as f:
        f.write(hashlib.sha256(body).hexdigest() + '  frozen-cut.json\n')
    return os.path.join(d, 'frozen-cut.json')


# ---------------------------------------------------------------- the exit, by hand

def flat(v=0.49, n=N15, **at):
    b = np.full(n, v)
    for k_, x in at.items():
        b[int(k_[1:])] = x
    return b


def net(px, b, stake=20.0):
    C = float(contracts_for_stake(stake, px))
    return round(C * b - float(taker_fee(C, b)) - (C * px + float(taker_fee(C, px))), 6)


def one(bid, settle=0.0, k0=2, px=0.50, level='none', exit_at=None):
    r = cut.simulate_cut(np.asarray(bid)[None, :], np.array([settle]), k0, np.array([px]), 20.0, len(bid), level,
                         None if exit_at is None else np.array([exit_at]))
    return {k_: (v[0].item() if hasattr(v[0], 'item') else v[0]) for k_, v in r.items()}


def test_hand_numbers_anchor():
    assert float(contracts_for_stake(20.0, 0.50)) == 40.0
    assert net(0.50, 0.50) == pytest.approx(-1.40)              # 0.70 taker fee each leg on 40 contracts at 50c
    assert net(0.50, 0.68) >= 5.0 > net(0.50, 0.64)            # the $5 take-profit bid


def test_take_profit_runs_before_the_cut():
    # TP at 4 (0.68), a cut-level drop at 6: the take-profit exits first
    r = one(flat(j4=0.68, j6=0.30), level='a05')
    assert (r['kind'], r['hold'], r['cut_min']) == (0, 2, -1) and r['trade'] == pytest.approx(net(0.5, 0.68))
    # a drop first (4), TP later (6): the cut exits at 4
    r = one(flat(j4=0.44, j6=0.68), level='a05')
    assert (r['kind'], r['hold'], r['cut_min']) == (1, 2, 4) and r['trade'] == pytest.approx(net(0.5, 0.44))
    # with no cut, the same path takes profit at 6
    r = one(flat(j4=0.44, j6=0.68), level='none')
    assert (r['kind'], r['cut_min']) == (0, -1) and r['hold'] == 4
    # TP inside the last 10% of the window (j = 14 of 15) is no TP; no cut at 14 either (tau = 60 s): ride the profit
    r = one(flat(j14=0.68), settle=1.0, level='a05')
    assert r['kind'] == 3 and r['hold'] == N15 - 2 and r['trade'] == pytest.approx(round(40 * 1.0 - (20 + 0.7), 6))


def test_cut_fires_only_while_tau_above_60s():
    # j = n - 2 (tau 120 s): cut
    r = one(flat(j13=0.30), level='a05')
    assert (r['kind'], r['cut_min'], r['hold']) == (1, 13, 11)
    # j = n - 1 (tau 60 s): no cut; the OR-H1 end rule sells there at the bid (net < 0)
    r = one(flat(j14=0.30), level='a05')
    assert (r['kind'], r['cut_min'], r['hold']) == (2, -1, 12) and r['trade'] == pytest.approx(net(0.5, 0.30))
    # never at or before the entry minute
    r = one(flat(j1=0.10, j2=0.10), level='a05')
    assert r['kind'] == 2 and r['cut_min'] == -1
    # no book at a minute: no cut there, the next minute with a bid
    r = one(flat(j5=np.nan, j6=0.40), level='a05')
    assert r['cut_min'] == 6
    # hourly: the cut window ends at j = 58
    b = np.full(60, 0.49)
    b[58] = 0.30
    assert one(b, level='a05')['cut_min'] == 58
    b[58], b[59] = 0.49, 0.30
    assert one(b, level='a05')['cut_min'] == -1


def test_absolute_and_relative_levels():
    bid = flat(j3=0.48, j4=0.42, j5=0.39, j6=0.29)            # then 0.49 again
    want = {'a03': 4, 'a05': 4, 'a08': 4, 'a10': 5, 'a15': 6, 'a20': 6, 'r15': 4, 'r25': 6, 'r40': 6, 'none': -1}
    got = {lv: one(bid, level=lv)['cut_min'] for lv in cut.LEVEL_NAMES}
    assert got == want                                         # a08: 0.42 <= 0.50 - 0.08 (inclusive)
    # relative scales with the entry ask: at 20c, r25 cuts at <= 0.15 and r15 at <= 0.17; a03 at <= 0.17, a05 at <= 0.15
    bid = flat(0.19, j3=0.17, j6=0.15)
    got = {lv: one(bid, px=0.20, level=lv)['cut_min'] for lv in ('a03', 'a05', 'a10', 'r15', 'r25', 'r40')}
    assert got == {'a03': 3, 'a05': 6, 'a10': -1, 'r15': 3, 'r25': 6, 'r40': -1}
    assert [x[0] for x in cut.LEVELS] == cut.LEVEL_NAMES and len(cut.LEVELS) == 10 and len(cut.FILTER_SETS) == 8


def test_none_is_the_pp_primary_exit():
    rng = np.random.default_rng(4)
    for n in (15, 60):
        M = 3000
        bid = np.clip(np.round(0.5 + np.cumsum(rng.normal(0, 0.04, (M, n)), axis=1), 2), 0.01, 0.99)
        bid[rng.random((M, n)) < 0.05] = np.nan
        settle = (rng.random(M) < 0.5).astype(float)
        for k0 in (1, 5, n - 4):
            px = np.round(rng.uniform(0.1, 0.9, M), 2)
            px[:5] = np.nan
            a = cut.simulate_cut(bid, settle, k0, px, 20.0, n, 'none')
            b = simulate(bid, settle, k0, px, 20.0, n)
            np.testing.assert_array_equal(a['trade'], b['trade'])
            np.testing.assert_array_equal(a['hold'], b['hold'])
            np.testing.assert_array_equal(a['trade_settle'], b['trade_settle'])
            assert (a['cut_min'] == -1).all()
            # any cut level only changes rows it cuts
            c = cut.simulate_cut(bid, settle, k0, px, 20.0, n, 'a05')
            same = c['cut_min'] < 0
            np.testing.assert_array_equal(c['trade'][same], b['trade'][same])
            assert (c['cut_min'][~same] > k0).all() and (c['cut_min'][~same] <= n - 2).all()


def test_settle_variant():
    # cut and TP exits are kept; an end-of-window sale settles instead; a ride settles anyway
    r = one(flat(j4=0.44), settle=1.0, level='a05')
    assert r['trade_settle'] == pytest.approx(net(0.5, 0.44))
    r = one(flat(j4=0.68), settle=0.0, level='a05')
    assert r['trade_settle'] == pytest.approx(net(0.5, 0.68))
    r = one(flat(), settle=1.0, level='a05')
    assert r['kind'] == 2 and r['trade'] == pytest.approx(net(0.5, 0.49)) and r['trade_settle'] == pytest.approx(19.30)
    r = one(flat(), settle=0.0, level='none')
    assert r['trade_settle'] == pytest.approx(-20.70)


def test_forced_exit_for_the_placebo():
    r = one(flat(), exit_at=5)
    assert (r['kind'], r['cut_min'], r['hold']) == (1, 5, 3) and r['trade'] == pytest.approx(net(0.5, 0.49))
    assert one(flat(j5=np.nan), exit_at=5)['cut_min'] == 6           # first minute with a bid at or after
    assert one(flat(j4=0.68), exit_at=8)['kind'] == 0                # the take-profit is still checked first
    assert one(flat(), exit_at=14)['kind'] == 2                      # past the cut window: the end rule
    with pytest.raises(ValueError):
        one(flat(), level='a05', exit_at=5)


# ---------------------------------------------------------------- the sidecar

def windows_of(sc_path):
    W = Part(os.path.join(sc_path, 'windows'), mmap=False)
    return types.SimpleNamespace(open_ms=np.asarray(W['open_ms'])), np.asarray(W['bid']), np.asarray(W['ask']), np.asarray(W['settle'])


def as_view(part, group):
    arr = {nm: np.asarray(part[nm]) for nm in ['t', 'kmin'] + [f'{x}_{s}{part.meta["horizons"][0]}' for x in ('ok', 'trade') for s in part.meta['sides']]}
    arr['group'] = np.asarray(group, dtype=np.int64)
    return ArrayPart(part.meta, arr)


@pytest.mark.parametrize('i', [0, 2])
def test_map_rows_direct_and_rematched(planted, i):
    p = planted['paths'][i]
    part, sc = Part(p), Part(cut.sidecar_path(planted['cut'], p))
    w, bid, ask, settle = windows_of(sc.path)
    win = np.asarray(sc['win'], dtype=np.int64)
    assert (win >= 0).all()
    ct = part.ct
    n = KINDS[cut.KIND_OF[ct]]['n']
    got, info = cut.map_rows(as_view(part, win), w, bid, ask, settle, n, 20.0, 250, QUIET)
    np.testing.assert_array_equal(got, win)
    assert info['groups_rematched'] == 0 and info['rows_unmatched'] == 0
    # the history's windows in another order (e.g. markets added since the part was built): matched by open time + labels
    rng = np.random.default_rng(1)
    perm = rng.permutation(len(w.open_ms))
    inv = np.argsort(perm)
    w2 = types.SimpleNamespace(open_ms=w.open_ms[perm])
    got, info = cut.map_rows(as_view(part, win), w2, bid[perm], ask[perm], settle[perm], n, 20.0, 250, QUIET)
    assert info['groups_rematched'] > 0
    ok = got >= 0
    assert ok.mean() > 0.99                                      # hourly strikes share an open time: the labels decide
    np.testing.assert_array_equal(got[ok], inv[win[ok]])
    # a window missing from the history: its rows map nowhere
    keep = np.r_[0:5, 6:len(w.open_ms)]
    w3 = types.SimpleNamespace(open_ms=w.open_ms[keep])
    got, info = cut.map_rows(as_view(part, win), w3, bid[keep], ask[keep], settle[keep], n, 20.0, 250, QUIET)
    assert (got[win == 5] == -1).all() and info['rows_unmatched'] == int((win == 5).sum()) > 0


def test_sidecar_refuses_rows_that_do_not_match(planted, tmp_path):
    p = planted['paths'][0]
    part, sc = Part(p), Part(cut.sidecar_path(planted['cut'], p))
    w, bid, ask, settle = windows_of(sc.path)
    win = np.asarray(sc['win'], dtype=np.int64)
    # rebuilt from the same windows: the same labels, byte for byte
    path = cut.write_sidecar(part, p, str(tmp_path / 'ok'), w.open_ms, bid, ask, settle, win, {}, N15, 'fixture', QUIET)
    assert Part(path).meta['labels_sha256'] == sc.meta['labels_sha256']
    # a settlement flipped / a window's bids shifted / rows pointed at the wrong window: refused
    s2 = settle.copy(); s2[:, :] = 1 - s2
    with pytest.raises(SystemExit, match='differs from the part'):
        cut.write_sidecar(part, p, str(tmp_path / 'x1'), w.open_ms, bid, ask, s2, win, {}, N15, 'fixture', QUIET)
    with pytest.raises(SystemExit, match='differs from the part'):
        cut.write_sidecar(part, p, str(tmp_path / 'x2'), w.open_ms, bid + 0.03, ask, settle, win, {}, N15, 'fixture', QUIET)
    with pytest.raises(SystemExit, match='differs from the part'):
        cut.write_sidecar(part, p, str(tmp_path / 'x3'), w.open_ms, bid, ask, settle, np.roll(win, 7), {}, N15, 'fixture', QUIET)


def test_build_labels_end_to_end_and_unmatched_refusal(planted, tmp_path, monkeypatch):
    """build_labels with the history loader stubbed by the sidecar's own windows: the same sidecar; > 0.5% of rows without
    a window is refused; DOGE is refused."""
    import oracle.pp as pp
    p = planted['paths'][0]
    sc = Part(cut.sidecar_path(planted['cut'], p))
    w, bid, ask, settle = windows_of(sc.path)
    win = np.asarray(sc['win'], dtype=np.int64)
    root = tmp_path / 'parts'
    shutil.copytree(p, root / os.path.basename(p))
    # the part's group indexes the loaded windows (here: the sidecar's)
    P = Part(str(root / os.path.basename(p)), mmap=False)
    np.save(os.path.join(P.path, 'group.npy'), win)
    state = {'drop': None}

    def fake_load(kind, history, asset, log=print):
        assert kind == 15 and asset == 'BTC'
        keep = np.arange(len(w.open_ms)) if state['drop'] is None else np.setdiff1d(np.arange(len(w.open_ms)), state['drop'])
        return types.SimpleNamespace(open_ms=w.open_ms[keep], _keep=keep)

    monkeypatch.setattr(pp, 'load_windows', fake_load)
    monkeypatch.setattr(cut, 'side_quotes', lambda ww: (bid[ww._keep], ask[ww._keep], None, None, None, None, settle[ww._keep]))
    out = cut.build_labels(15, 'unused', P.path, str(tmp_path / 'cut'), 'fixture', QUIET)
    new = Part(out)
    assert new.meta['labels_sha256'] == sc.meta['labels_sha256'] and new.meta['match']['rows_unmatched'] == 0
    state['drop'] = np.arange(0, len(w.open_ms), 50)            # 2% of the windows gone
    with pytest.raises(SystemExit, match='match no window'):
        cut.build_labels(15, 'unused', P.path, str(tmp_path / 'cut2'), 'fixture', QUIET)
    with pytest.raises(SystemExit, match='ct'):
        cut.build_labels(60, 'unused', P.path, str(tmp_path / 'cut3'), 'fixture', QUIET)
    doge = tmp_path / 'pp15-DOGE'
    shutil.copytree(P.path, doge)
    m = json.load(open(doge / 'meta.json')); m['scope'] = 'DOGE'; m['assets'] = ['DOGE']
    json.dump(m, open(doge / 'meta.json', 'w'))
    with pytest.raises(SystemExit, match='DOGE'):
        cut.build_labels(15, 'unused', str(doge), str(tmp_path / 'cut4'), 'fixture', QUIET)


def test_search_refuses_a_sidecar_of_other_rows(planted, tmp_path):
    parts, cr = tmp_path / 'parts', tmp_path / 'cut'
    shutil.copytree(planted['parts'], parts)
    shutil.copytree(planted['cut'], cr)
    sp = cr / 'pp15-ETH'
    t = np.load(sp / 't.npy')
    t[100] += MIN
    np.save(sp / 't.npy', t)
    with pytest.raises(SystemExit, match='not the part'):
        cut.search(str(parts), str(cr), str(tmp_path / 'o1'), 'x', ('pp15',), None, QUIET)
    shutil.rmtree(cr)
    shutil.copytree(planted['cut'], cr)
    m = json.load(open(sp / 'meta.json')); m['base']['code_sha'] = 'other'
    json.dump(m, open(sp / 'meta.json', 'w'))
    with pytest.raises(SystemExit, match='built for'):
        cut.search(str(parts), str(cr), str(tmp_path / 'o2'), 'x', ('pp15',), None, QUIET)
    m['base']['code_sha'] = 'fixture'; m['base']['dir'] = 'pp15-BTC'
    json.dump(m, open(sp / 'meta.json', 'w'))
    with pytest.raises(SystemExit, match='built for'):
        cut.search(str(parts), str(cr), str(tmp_path / 'o3'), 'x', ('pp15',), None, QUIET)
    shutil.rmtree(sp)
    with pytest.raises(FileNotFoundError):
        cut.search(str(parts), str(cr), str(tmp_path / 'o4'), 'x', ('pp15',), None, QUIET)


# ---------------------------------------------------------------- filters and entries

@pytest.fixture(scope='module')
def cells_a(planted):
    return {ct: cut.load_cells_dev(ct, planted['parts'], planted['cut'], 'A', cut.PARAMS['order_seed'], QUIET) for ct in cut.CUT_TYPES}


def test_filters_are_side_relative(planted, cells_a):
    for ct in cut.CUT_TYPES:
        for c in cells_a[ct]:
            sc = Part(cut.sidecar_path(planted['cut'], c.v.path))
            W = Part(os.path.join(sc.path, 'windows'))          # the test may look: the search never does
            wi = np.asarray(sc['win'])[c.rows]
            ask = np.asarray(W['ask'])[wi, c.side, c.kmin]
            assert c.skip['F1'].any() and (~c.skip['F1']).any()
            np.testing.assert_array_equal(c.skip['F1'], ask < 0.30 - 1e-9)        # the entry side's own ask
            X = np.asarray(c.v['X'])
            for si, s in enumerate(c.sides):
                m = c.side == si
                r = c.rows[m]
                other = c.sides[1 - si]
                col = lambda nm, sd: X[r, resolve(c.v, sd, nm)]  # noqa: E731
                np.testing.assert_array_equal(c.skip['F2'][m], col('k_dmid3', s) == -1)
                np.testing.assert_array_equal(c.skip['F3'][m], np.isin(col('k_z', s), [0, 1]))
                assert not np.array_equal(c.skip['F1'][m], np.isin(col('k_price', other), [0, 1]))
                assert not np.array_equal(c.skip['F3'][m], np.isin(col('k_z', other), [0, 1]))
            # a filter set skips the union of its filters
            np.testing.assert_array_equal(c.filtered(('F1', 'F3')), c.skip['F1'] | c.skip['F3'])
            assert not c.filtered(()).any()


def ref_take(c, level, fset):
    """Reference trading: walk the units in the cell's order; one position per event; free again at t + hold minutes."""
    busy = {}
    out = []
    cand = ~c.filtered(fset) & np.isfinite(c.trade[level])
    for i in range(c.U):
        if not cand[i]:
            continue
        e = int(c.event[i])
        if c.t[i] >= busy.get(e, -1):
            out.append(i)
            busy[e] = int(c.t[i]) + max(1, int(c.hold[level][i])) * MIN
    return np.array(out, dtype=np.int64)


def test_entries_one_position_and_the_same_order_for_every_arm(cells_a):
    for ct in cut.CUT_TYPES:
        for c in cells_a[ct]:
            # the trading order: t, then the fixed pseudo-random priority (independent of the arm)
            prio = cut.order_key(c.t, np.asarray(c.v['group'])[c.rows], c.side, cut.PARAMS['order_seed'])
            same_t = c.t[1:] == c.t[:-1]
            assert (np.diff(c.t) >= 0).all() and (prio[1:][same_t] >= prio[:-1][same_t]).all()
            firsts = {}
            for lv, fs in (('none', ()), ('a05', ()), ('r25', ()), ('a10', ('F2',)), ('none', ('F1', 'F2', 'F3'))):
                tk = c.take(lv, fs)
                np.testing.assert_array_equal(tk, ref_take(c, lv, fs))
                # one position at a time per window: the next entry of an event comes at or after the previous exit
                for e in np.unique(c.event[tk]):
                    k_ = tk[c.event[tk] == e]
                    assert (c.t[k_[1:]] >= c.t[k_[:-1]] + np.maximum(1, c.hold[lv][k_[:-1]]) * MIN).all()
                if not fs:
                    firsts[lv] = {int(c.event[i]): int(i) for i in tk[::-1]}            # first entry of each event
            # every unfiltered arm opens each window with the same unit (same entries until the exits differ)
            assert firsts['none'] == firsts['a05'] == firsts['r25']
            # the two sides at one instant: neither always first
            first_units = np.array(sorted(firsts['none'].values()))
            both = np.array([i + 1 < c.U and c.t[i + 1] == c.t[i] and c.event[i + 1] == c.event[i] for i in first_units])
            share_y = np.mean(c.side[first_units[both]] == 0)
            assert 0.3 < share_y < 0.7, share_y


def test_order_key_is_fixed_and_seeded():
    t = np.arange(1000, dtype=np.int64) * MIN
    g = np.arange(1000) % 7
    s = np.arange(1000) % 2
    a, b = cut.order_key(t, g, s, 11), cut.order_key(t, g, s, 11)
    np.testing.assert_array_equal(a, b)
    assert not np.array_equal(a, cut.order_key(t, g, s, 12))
    assert not np.array_equal(a, cut.order_key(t, g, 1 - s, 11))


# ---------------------------------------------------------------- the search

def test_planted_cut_is_found_and_frozen(planted):
    res = planted['res']
    fz = res['frozen']['pp15']
    assert fz is not None and fz['level'] != 'none'
    T = res['types']['pp15']
    arm = next(a for a in T['arms'] if a['id'] == fz['id'])
    assert arm['kept'] and arm['survivor'] and arm['frozen'] and arm['rank_A'] <= 5
    assert arm['B']['usd_day'] > 0 and arm['B']['vs_control_usd_day'] > 0 and arm['B']['p_bhy'] <= 0.10
    assert len(T['arms']) == 80 and len({a['id'] for a in T['arms']}) == 80
    assert sum(1 for a in T['arms'] if a.get('kept')) == 5
    # the best survivor by B $/day
    surv = [a for a in T['arms'] if a.get('survivor')]
    assert fz['B']['usd_day'] == max(a['B']['usd_day'] for a in surv)
    # A ranks by pooled A $/day
    r = sorted(T['arms'], key=lambda a: a['rank_A'])
    assert all(r[i]['A']['usd_day'] >= r[i + 1]['A']['usd_day'] for i in range(79))
    doc = json.loads(open(planted['frozen'], 'rb').read())
    assert doc['types']['pp15']['frozen']['id'] == fz['id'] and not doc['types']['pp15']['falsified_at_discovery']
    assert open(os.path.join(planted['out'], 'frozen-cut.sha256')).read().split()[0] == hashlib.sha256(open(planted['frozen'], 'rb').read()).hexdigest()
    assert 'NEVER DOGE' in open(os.path.join(planted['out'], 'report-cut.md')).read()


def test_null_fixture_freezes_nothing(null):
    res = null['res']
    assert res['frozen'] == {'pp15': None, 'pp60': None}
    doc = json.loads(open(null['frozen'], 'rb').read())
    assert all(doc['types'][ct]['falsified_at_discovery'] for ct in cut.CUT_TYPES)
    assert 'falsified at discovery' in open(os.path.join(null['out'], 'report-cut.md')).read()


def test_bhy_over_the_ten_kept_arms(planted, tmp_path):
    res = planted['res']
    kept = [a for ct in cut.CUT_TYPES for a in res['types'][ct]['arms'] if a.get('kept')]
    kept.sort(key=lambda a: (cut.CUT_TYPES.index(a['ct']), a['rank_A']))
    assert res['m'] == 10 and len(kept) == 10
    np.testing.assert_allclose([a['B']['p_bhy'] for a in kept], bhy_adjust([a['B']['p'] for a in kept]))
    for a in kept:
        assert a['B']['p'] == max(a['B']['p_ev'], a['B']['p_up'])
    # one type searched alone still adjusts at m = 10 (its 5 kept arms plus 5 of p = 1)
    one_ = cut.search(planted['parts'], planted['cut'], str(tmp_path / 'one'), 'c0ffee1', ('pp15',), None, QUIET)
    k5 = sorted([a for a in one_['types']['pp15']['arms'] if a.get('kept')], key=lambda a: a['rank_A'])
    assert one_['m'] == 10
    np.testing.assert_allclose([a['B']['p_bhy'] for a in k5], bhy_adjust([a['B']['p'] for a in k5] + [1.0] * 5)[:5])


def _garble_after(path, cut_t, cols, rng):
    """Overwrite rows with t >= cut_t of the arrays cols (in place) with garbage."""
    t = np.load(os.path.join(path, 't.npy'))
    lo = int(np.searchsorted(t, cut_t, 'left'))
    for nm in cols:
        f = os.path.join(path, nm + '.npy')
        a = np.load(f)
        if a.dtype.kind == 'f':
            a[lo:] = 1e6
        else:
            a[lo:] = rng.integers(0, 2, a[lo:].shape).astype(a.dtype)
        np.save(f, a)
    return lo


def test_search_reads_no_row_past_dev_end_and_never_windows(planted, tmp_path, monkeypatch):
    parts, cr = tmp_path / 'parts', tmp_path / 'cut'
    shutil.copytree(planted['parts'], parts)
    shutil.copytree(planted['cut'], cr)
    rng = np.random.default_rng(0)
    for p in planted['paths']:
        d = os.path.basename(p)
        h = 15 if d.startswith('pp15') else 60
        first_bad = DEV_END - h * MIN + 1                       # t + h > DEV_END
        pcols = [f[:-4] for f in os.listdir(parts / d) if f.endswith('.npy') and f not in ('t.npy',)]
        _garble_after(str(parts / d), first_bad, pcols, rng)
        scols = [f[:-4] for f in os.listdir(cr / d) if f.endswith('.npy') and f not in ('t.npy',)]
        _garble_after(str(cr / d), first_bad, scols, rng)
        shutil.rmtree(cr / d / 'windows')                       # HO-1 paths: the search must not need them
    opened = []
    real = np.load

    def spy(f, *a, **k):
        opened.append(str(f))
        return real(f, *a, **k)

    monkeypatch.setattr(np, 'load', spy)
    res = cut.search(str(parts), str(cr), str(tmp_path / 'o'), 'c0ffee1', log=QUIET)
    assert opened and not any(os.sep + 'windows' + os.sep in f for f in opened)
    for ct in cut.CUT_TYPES:
        a = {x['id']: (x['A'], x['B']) for x in res['types'][ct]['arms']}
        b = {x['id']: (x['A'], x['B']) for x in planted['res']['types'][ct]['arms']}
        assert a == b
    assert res['frozen'] == planted['res']['frozen']


def test_doge_parts_are_refused(planted, tmp_path):
    parts = tmp_path / 'parts'
    shutil.copytree(planted['parts'], parts)
    shutil.copytree(parts / 'pp15-ETH', parts / 'pp15-DOGE')
    with pytest.raises((ValueError, SystemExit), match='DOGE'):
        cut.search(str(parts), planted['cut'], str(tmp_path / 'o'), 'x', ('pp15',), None, QUIET)


# ---------------------------------------------------------------- HO-1

def test_ho1_end_to_end_with_the_registry(planted, ho, registry):
    from oracle import ho1
    s = ho['res']['summary']
    fz = planted['res']['frozen']['pp15']
    assert s['arm'] == fz['id'] and s['family'] == 'oracle-pp15-cut-v1' and s['frozen_cut_sha256'] == planted['res']['frozen_sha256']
    assert s['verdict']['pass'] and s['verdict']['ho1_pass'] and s['verdict']['net_positive']
    assert s['arm_ho1']['usd_total'] > s['control_ho1']['usd_total'] and s['arm_ho1']['usd_total'] > s['placebo_ho1']['usd_total']
    reg, _, _ = ho1.load_registry(registry)
    rows = [json.loads(line) for line in open(os.path.join(ho['out'], 'rows.jsonl'))]
    assert [r['role'] for r in rows] == ['control', 'candidate', 'placebo']
    for r in rows:
        assert not reg.validate(r)[0]
        assert r['family'] == 'oracle-pp15-cut-v1' and r['thread'] == 'oracle-setups' and r['contract_type'] == 'price_prediction'
        assert list(r['by_day']) == list(ho1.HOLD_DAYS) and len(r['by_day']) == 96
        assert r['data']['doge'] is False
    cand = rows[1]
    assert cand['control'] == rows[0]['trial_id'] and rows[2]['placebo_for'] == fz['id']
    ok, why = reg.ho1_pass(cand['heldout'], reg.contract_type_of(cand), cand['data'].get('engine'))
    assert ok == s['verdict']['ho1_pass']
    cli = subprocess.run([sys.executable, '-I', registry, 'validate', os.path.join(ho['out'], 'rows.jsonl')], capture_output=True, text=True)
    assert cli.returncode == 0, cli.stdout + cli.stderr
    # by_day sums are the summary totals
    assert sum(cand['by_day'].values()) == pytest.approx(s['arm_ho1']['usd_total'], abs=1e-3)
    assert sum(rows[0]['by_day'].values()) == pytest.approx(s['control_ho1']['usd_total'], abs=1e-3)
    assert sum(rows[2]['by_day'].values()) == pytest.approx(s['placebo_ho1']['usd_total'], abs=1e-3)
    for nm in ('settle', 'lat', 'cost', 'control_settle'):
        assert nm in s['variants'] and s['variants'][nm]['trades'] > 0


def test_ho1_outputs_are_aggregates_and_never_paper(ho):
    md = open(os.path.join(ho['out'], 'ho1-cut.md')).read()
    js = open(os.path.join(ho['out'], 'ho1-cut.json')).read()
    assert 'Never compared to paper' in md and 'NEVER DOGE' in md
    assert 'paper' not in js.lower() and 'doge' not in js.lower().replace('"doge": false', '')
    json.loads(js)


@pytest.fixture(scope='module')
def hold_cells(planted, ho):
    doc = json.loads(open(planted['frozen'], 'rb').read())
    return cut.load_cells_hold('pp15', planted['parts'], planted['cut'], doc['types']['pp15']['parts'], cut.PARAMS['order_seed'], QUIET)


def test_windows_reproduce_the_labels(hold_cells):
    for c in hold_cells:
        idx = np.nonzero(np.isfinite(c.trade['none']))[0]
        pth = c.paths(idx)
        for lv in cut.LEVEL_NAMES:
            r = pth.exit(pth.cut_mask(lv))
            np.testing.assert_allclose(r['trade'], c.trade[lv][idx], atol=1e-3)
            np.testing.assert_array_equal(r['cut_min'], c.cutmin[lv][idx])
        assert (c.t >= HOLD_FROM).all() and (c.t + 15 * MIN <= HOLD_TO).all()


def test_placebo_random_minute_exits_and_random_skips(planted, hold_cells):
    fz = planted['res']['frozen']['pp15']
    level, fset = fz['level'], tuple(fz['filters'])
    taken = [c.take(level, fset) for c in hold_cells]
    # no intervention (no cut, no filter): the placebo is the control exactly
    ctl = [c.take('none', ()) for c in hold_cells]
    out0, info0 = cut.placebo_trades(hold_cells, 'none', (), ctl, 2, 3)
    assert info0['forced_exits'] == 0 and info0['dropped'] == 0
    for (t_, u_), c, tk in zip(out0, hold_cells * 2, ctl * 2):
        np.testing.assert_array_equal(t_, c.t[tk])
        np.testing.assert_allclose(u_, c.trade['none'][tk])
    # the arm's placebo: every unit the arm would cut is force-exited (same count), the filters' count is skipped at random
    out, info = cut.placebo_trades(hold_cells, level, fset, taken, 1, 3)
    n_cut = sum(int(((c.cutmin[level] >= 0) & np.isfinite(c.trade[level])).sum()) for c in hold_cells)
    n_filt = sum(int((c.filtered(fset) & np.isfinite(c.trade[level])).sum()) for c in hold_cells)
    assert info['dropped'] == n_filt
    assert 0 < info['forced_exits'] <= n_cut and info['forced_same_stratum'] > 0.9 * info['forced_exits']
    assert info['offsets_from'] == 'taken' and info['cut_offsets'] == sum(int((c.cutmin[level][tk] >= 0).sum()) for c, tk in zip(hold_cells, taken))
    # different seeds, different draws; the same seed, the same draws
    a1, _ = cut.placebo_trades(hold_cells, level, fset, taken, 1, 3)
    a2, _ = cut.placebo_trades(hold_cells, level, fset, taken, 1, 4)
    assert sum(u.sum() for _, u in a1) == sum(u.sum() for _, u in out)
    assert sum(u.sum() for _, u in a2) != sum(u.sum() for _, u in out)
    # the arm's information is gone: its placebo earns less than the arm
    arm_usd = sum(c.trade[level][tk].sum() for c, tk in zip(hold_cells, taken))
    assert sum(u.sum() for _, u in out) < arm_usd


def test_draw_cells_keeps_the_count_per_stratum_and_day(hold_cells):
    c = hold_cells[0]
    cand0 = np.isfinite(c.trade['none'])
    fset = ('F1', 'F2')
    d1 = cut.draw_cells(c, fset, cand0, np.random.default_rng(1))
    d2 = cut.draw_cells(c, fset, cand0, np.random.default_rng(2))
    fm = c.filtered(fset) & cand0
    cid = c.stratum * 100_000 + c.day
    for x in np.unique(cid[cand0]):
        m = cid == x
        assert d1[m].sum() == min(fm[m].sum(), (m & cand0).sum()) == d2[m].sum()
    assert not (d1 & ~cand0).any() and not np.array_equal(d1, d2) and not np.array_equal(d1, fm)


def test_forced_exit_offsets_come_from_the_arm(hold_cells, planted, monkeypatch):
    """Every forced sale minute is k + d with d one of the arm's cut offsets (TP first, or the next minute with a bid)."""
    fz = planted['res']['frozen']['pp15']
    level, fset = fz['level'], tuple(fz['filters'])
    taken = [c.take(level, fset) for c in hold_cells]
    offs = set(np.concatenate([(c.cutmin[level][tk] - c.kmin[tk])[c.cutmin[level][tk] >= 0] for c, tk in zip(hold_cells, taken)]).tolist())
    seen = []
    real = cut.Paths.forced_mask

    def spy(self, exit_at):
        seen.append(np.asarray(exit_at) - self.k0)
        return real(self, exit_at)

    monkeypatch.setattr(cut.Paths, 'forced_mask', spy)
    cut.placebo_trades(hold_cells, level, fset, taken, 2, 3)
    d = np.concatenate(seen)
    assert len(d) and set(np.unique(d).tolist()) <= offs


def test_ho1_reads_no_row_at_or_after_hold_to(planted, ho, regime, registry, tmp_path):
    """Garbage rows from HOLD_TO on (the lockbox included) in the part and the sidecar: the same HO-1 numbers."""
    parts, cr = tmp_path / 'parts', tmp_path / 'cut'
    shutil.copytree(planted['parts'], parts)
    shutil.copytree(planted['cut'], cr)
    k = 400
    doc = json.loads(open(planted['frozen'], 'rb').read())
    for d in ('pp15-BTC', 'pp15-ETH'):
        late = HOLD_TO + np.arange(k, dtype=np.int64) * MIN
        for root in (parts / d, cr / d):
            P = Part(str(root), mmap=False)
            names = [f[:-4] for f in os.listdir(root) if f.endswith('.npy')]
            arr = {}
            for nm in names:
                a = np.array(P[nm])
                g = late if nm == 't' else np.full((k,) + a.shape[1:], 1e6 if a.dtype.kind == 'f' else 1, dtype=a.dtype)
                arr[nm] = np.concatenate([a, g])
            meta = {k_: v for k_, v in P.meta.items() if k_ not in ('schema', 'n')}
            if 'base' in meta:
                meta['base'] = dict(meta['base'], n=meta['base']['n'] + k)
            write_part(str(root), meta, arr)
        for e in doc['types']['pp15']['parts']:
            if e['dir'] == d:
                e['rows_total'] += k
    frozen = resign(doc, str(tmp_path / 'f'))
    res = cut.main(['ho1', '--frozen', frozen, '--ct', 'pp15', '--parts', str(parts), '--cut-labels', str(cr), '--regime', regime,
                    '--registry', registry, '--out', str(tmp_path / 'o'), '--run', '4242', '--code-sha', 'c0ffee1', '--quiet'])
    a, b = res['summary'], ho['res']['summary']
    for k_ in ('arm_ho1', 'control_ho1', 'placebo_ho1', 'variants'):
        assert a[k_] == b[k_]
    assert [p['hold_units'] for p in a['parts']] == [p['hold_units'] for p in b['parts']]


def test_ho1_refuses_a_bad_sha_and_nothing_frozen(planted, null, regime, registry, tmp_path):
    d = tmp_path / 'f'
    shutil.copytree(planted['out'], d)
    body = (d / 'frozen-cut.json').read_bytes()
    (d / 'frozen-cut.json').write_bytes(body.replace(b'"m":10', b'"m":11'))
    with pytest.raises(SystemExit, match='does not match'):
        run_ho1(planted, str(d / 'frozen-cut.json'), str(tmp_path / 'o1'), registry, regime)
    with pytest.raises(SystemExit, match='does not match'):
        run_ho1(planted, planted['frozen'], str(tmp_path / 'o2'), registry, regime, 'pp15', '--sha256', '0' * 64)
    (d / 'frozen-cut.sha256').unlink()
    with pytest.raises(SystemExit, match='no frozen-cut.sha256'):
        run_ho1(planted, str(d / 'frozen-cut.json'), str(tmp_path / 'o3'), registry, regime)
    good = planted['res']['frozen_sha256']
    assert run_ho1(planted, planted['frozen'], str(tmp_path / 'o4'), registry, regime, 'pp15', '--sha256', good)['summary']['frozen_cut_sha256'] == good
    # pp60 froze nothing in the planted search; nothing froze in the null search
    assert planted['res']['frozen']['pp60'] is None
    with pytest.raises(SystemExit, match='nothing frozen'):
        run_ho1(planted, planted['frozen'], str(tmp_path / 'o5'), registry, regime, 'pp60')
    with pytest.raises(SystemExit, match='nothing frozen'):
        run_ho1(null, null['frozen'], str(tmp_path / 'o6'), registry, regime, 'pp15')
    assert not os.path.exists(tmp_path / 'o5') and not os.path.exists(tmp_path / 'o6')


def test_ho1_refuses_labels_other_than_the_searched(planted, regime, registry, tmp_path):
    cr = tmp_path / 'cut'
    shutil.copytree(planted['cut'], cr)
    m = json.load(open(cr / 'pp15-BTC' / 'meta.json'))
    m['labels_sha256'] = '0' * 64
    json.dump(m, open(cr / 'pp15-BTC' / 'meta.json', 'w'))
    fx = dict(planted, cut=str(cr))
    with pytest.raises(SystemExit, match='labels sha256'):
        run_ho1(fx, planted['frozen'], str(tmp_path / 'o'), registry, regime)


def test_lockbox_candidates_descriptive(planted, ho, hold_cells, regime, registry, tmp_path):
    from oracle.sim import busy_key, fire_mask, split_rows
    lb = {'schema': 'oracle-lockbox-candidates-1', 'ct': 'pp15', 'rule_sha256': 'x',
          'setups': [{'rank_lockbox': 1, 'id': 'pp15:ALL:Y15:k_dmid3=1', 'scope': 'ALL', 'side': 'Y', 'h': 15, 'items': [{'f': 'k_dmid3', 'v': 1}]},
                     {'rank_lockbox': 2, 'id': 'pp15:ETH:N15:k_z=5', 'scope': 'ETH', 'side': 'N', 'h': 15, 'items': [{'f': 'k_z', 'v': 5}]}]}
    p = tmp_path / 'lockbox_candidates.json'
    p.write_text(json.dumps(lb))
    res = run_ho1(planted, planted['frozen'], str(tmp_path / 'o'), registry, regime, 'pp15', '--lockbox', str(p))
    L = res['summary']['lockbox_candidates']
    assert L['n'] == 2 and [x['id'] for x in L['setups']] == [s['id'] for s in lb['setups']]
    # the primary numbers are the OR-H1 trading of the setup on the part's own HO-1 labels
    s = lb['setups'][0]
    tot, n = 0.0, 0
    for c in hold_cells:
        v = c.v
        tr = np.asarray(v['trade_Y15'], dtype=np.float64)
        B = np.nonzero((np.asarray(v['ok_Y15']) == 1) & (np.asarray(v['stratum_Y']) >= 0) & np.isfinite(tr) & (split_rows(v, 15) == 'H'))[0]
        rel = trade_sim(np.asarray(v['t'])[B], np.asarray(v['hold_Y15'], dtype=np.float64)[B], tr[B], fire_mask(v, s, B), busy_key(v)[B])
        tot += tr[B][rel].sum(); n += len(rel)
    x = L['setups'][0]
    assert x['primary']['trades'] == n and x['primary']['usd_total'] == pytest.approx(tot, abs=1e-6)
    assert x['cut']['trades'] > 0 and x['cut']['cut_trades'] > 0
    assert 'lockbox candidates' in open(tmp_path / 'o' / 'ho1-cut.md').read()
    # the verdict and rows do not depend on it
    assert res['summary']['verdict'] == ho['res']['summary']['verdict']
    bad = dict(lb, setups=[dict(lb['setups'][0], scope='DOGE')])
    p.write_text(json.dumps(bad))
    with pytest.raises(SystemExit, match='DOGE'):
        run_ho1(planted, planted['frozen'], str(tmp_path / 'o2'), registry, regime, 'pp15', '--lockbox', str(p))
    p.write_text(json.dumps(dict(lb, ct='pp60')))
    with pytest.raises(SystemExit, match='lockbox candidates of pp60'):
        run_ho1(planted, planted['frozen'], str(tmp_path / 'o3'), registry, regime, 'pp15', '--lockbox', str(p))


def test_constants_match_the_prereg():
    P = cut.PARAMS
    assert (P['top'], P['q'], P['m'], P['block'], P['draws'], P['seeds']) == (5, 0.10, 10, 5.0, 2000, 8)
    assert cut.CUT_LAST_SEC == 60
    absd = sorted(d for _, k_, d in cut.LEVELS if k_ == 'abs')
    reld = sorted(d for _, k_, d in cut.LEVELS if k_ == 'rel')
    assert absd == [0.03, 0.05, 0.08, 0.10, 0.15, 0.20] and reld == [0.15, 0.25, 0.40]
    assert cut.prereg_sha() == hashlib.sha256(open(os.path.join(os.path.dirname(cut.__file__), 'prereg', 'OR-H3.md'), 'rb').read()).hexdigest()
    assert DAY == 86_400_000
