"""OR-HM2 part 1, the scan (python/oracle/heat_hm2.py; build plan sections 2 and 4): exact counting (the neutral-level
shortcut against a naive count, the packed fields against a direct count, the statistics against the engine's g.cells
and heat._clu), the two interaction scales and iota_robust, the chance scale on pure noise, a planted pure interaction,
planted main effects with no joint term, the cut at 2025 for every A label (240 minutes included), the --part merge and
the series files. Synthetic minutes, SPLITS patched to 120 days (A 90, B 30), procs 1 unless noted."""
import json
import os

import numpy as np
import pandas as pd
import pytest

from oracle import heat
from oracle import heat_hm2 as hm
from oracle.common import DAY, MIN

DAYS, A_DAYS = 120, 90


@pytest.fixture
def splits(monkeypatch):
    start = heat.HEAT_END - DAYS * DAY
    monkeypatch.setattr(heat, 'SPLITS', {'A': (start, start + A_DAYS * DAY), 'B': (start + A_DAYS * DAY, heat.HEAT_END)})
    return start


def _csv(path, start, days=DAYS, seed=0, drift=None):
    """A random walk of 1-minute bars (open = the previous close). drift(i) -> per-minute log drift added to minute i."""
    rng = np.random.default_rng(seed)
    n = days * 1440
    r = rng.normal(0, 8e-4, n)
    if drift is not None:
        r = r + drift
    c = 100 * np.exp(np.cumsum(r))
    o = np.r_[100, c[:-1]]
    w = np.abs(rng.normal(0, 3e-4, n))
    v = rng.uniform(1, 2, n)
    pd.DataFrame({'ts': start + np.arange(n) * MIN, 'o': o, 'h': np.maximum(o, c) * (1 + w), 'l': np.minimum(o, c) * (1 - w), 'c': c, 'v': v,
                  'tb': v * rng.uniform(0.3, 0.7, n)}).to_csv(path, index=False)


def _zone(name, x, k, a_bars, typ='osc'):
    xa = x[:a_bars]
    e = np.quantile(xa[np.isfinite(xa)], heat.ZONE_Q)
    return {'name': name, 'k': k, 'codes': heat.bucket(x, e), 'levels': heat.ZONES, 'base': name, 'zones': True, 'type': typ}


def _path_readings(m, g):
    """Causal readings of the coin's own path on 1- and 15-minute bars: zones of 3/10/30-bar returns and of a volatility
    ratio, and the sign of the 5-bar return (no neutral level). On a random walk none of them knows the next move."""
    c = np.log(m['c'])
    out = []
    for k in (1, 15):
        nb = m['n'] // k
        cb = c[k - 1::k][:nb]
        a_bars = g.sp['A'].hi // k
        for L in (3, 10, 30):
            out.append(_zone(f'{k}m:R{L}', np.r_[np.full(L, np.nan), cb[L:] - cb[:-L]], k, a_bars))
        r1 = pd.Series(np.r_[np.nan, np.diff(cb)])
        out.append(_zone(f'{k}m:VR', (r1.rolling(60).std() / r1.rolling(240).std()).to_numpy(), k, a_bars, 'regime'))
        x = np.r_[np.full(5, np.nan), cb[5:] - cb[:-5]]
        out.append({'name': f'{k}m:R5 sign', 'k': k, 'codes': np.where(np.isfinite(x), (x > 0).astype(np.int8), -1).astype(np.int8),
                    'levels': ['below 0', 'above 0'], 'base': f'{k}m:R5', 'type': 'osc'})
    return out


def _ctx(path, readings_fn, twin=0, real=None, labs=None):
    m = heat.load_minutes(str(path))
    if twin:
        m = heat.make_twin(m, twin)
    lab = heat.labels(m) if labs is None else labs[0]
    g = heat.Grid(m, lab)
    kw = {}
    if labs is not None and labs[1] is not None:
        with hm.h240():
            kw = {'lab240': labs[1], 'g240': heat.Grid(m, labs[1])}
    return hm.make_ctx(m, readings_fn(m, g), 'X', twin, real=real, lab=lab, g=g, log=lambda *a: None, **kw)


def _scan(ctx, tmp_path=None, procs=1):
    summ = {'pair': hm.SummaryCounts(ctx.families), 'triple': hm.SummaryCounts(ctx.families)}
    cands = hm.Candidates()
    w = hm.ShardWriter(str(tmp_path / f'shards{ctx.twin}') if tmp_path is not None else '', ctx.real and tmp_path is not None)
    st = hm.scan_pairs(ctx, procs, w, summ, cands, log=None)
    return summ, cands.frame(), st, w


def _shards(d) -> dict:
    fs = sorted(f for f in os.listdir(d) if f.startswith('cells_'))
    z = [np.load(os.path.join(d, f)) for f in fs]
    out = {k: np.concatenate([x[k] for x in z]) for k in ('ia', 'ib', 'la', 'lb', 'n', 'days', 'stats', 'rest_n')}
    out['names'] = list(z[0]['stat_names'])
    return out


# ------------------------------------------------------------------------------------------------------------ counting
def _mixed_readings(m, g):
    """Zone readings, a sign reading, a rare pattern ('none' neutral), a categorical state with no neutral level and one
    with several, and NA stretches."""
    rng = np.random.default_rng(5)
    R = _path_readings(m, g)
    n = m['n']
    pat = np.where(rng.random(n) < 0.01, rng.integers(1, 3, n), 0).astype(np.int8)
    pat[1000:3000] = -1
    R.append({'name': '1m:CDL:X', 'k': 1, 'codes': pat, 'levels': ['none', 'bull', 'bear'], 'base': '1m:CDL:X', 'every': True})
    cat = (np.arange(n // 60) % 4).astype(np.int8)
    R.append({'name': 'H4', 'k': 60, 'codes': cat, 'levels': ['a', 'b', 'c', 'd'], 'base': 'H4', 'ctx': True, 'state': True})
    run = rng.integers(0, 5, n // 5).astype(np.int8)
    run[:300] = -1
    R.append({'name': '5m:Runs', 'k': 5, 'codes': run, 'levels': ['none', '3-4 down', '5+ down', '3-4 up', '5+ up'], 'base': '5m:Runs', 'cond': True})
    return R


def test_shortcut_equals_naive_count(tmp_path, splits):
    """The neutral-level shortcut (count only the lead's off-neutral and NA entries, fill its neutral cells from the
    other reading's per-day totals) gives exactly the naive full count, for every pair; the packed fields equal a direct
    per-(cell, day) count of up / down at every horizon, the 240-minute count and the hold sums."""
    f = tmp_path / 'x.csv'
    _csv(f, splits, seed=1)
    ctx = _ctx(f, _mixed_readings)
    Rn = len(ctx.readings)
    led = 0
    for ia in range(Rn):
        for ib in range(ia + 1, Rn):
            A, B = hm._col(ctx, ia), hm._col(ctx, ib)
            P1, idx = hm.pair_kernel(ctx, A, B, True)
            P2, _ = hm.pair_kernel(ctx, A, B, False)
            assert np.array_equal(P1, P2), (ctx.names[ia], ctx.names[ib])
            led += idx is not None
            if idx is not None:
                assert len(idx) < 0.5 * len(ctx.rows) or 'CDL' in ctx.names[ia] + ctx.names[ib] or 'Runs' in ctx.names[ia] + ctx.names[ib]
    assert led > Rn                                                   # the shortcut ran on most pairs ...
    A, B = hm._col(ctx, ctx.byname['1m:R5 sign']), hm._col(ctx, ctx.byname['15m:R5 sign'])
    assert hm.pair_kernel(ctx, A, B)[1] is None                       # ... and two readings with no neutral level count in full
    # the packed fields against a direct count
    ia, ib = ctx.byname['1m:R10'], ctx.byname['5m:Runs']
    P, _ = hm.pair_kernel(ctx, hm._col(ctx, ia), hm._col(ctx, ib))
    F = hm.unpack(P)
    ca, cb, d, r = ctx.C[:, ia].astype(int), ctx.C[:, ib].astype(int), ctx.day, ctx.rows
    for k, H in enumerate(hm.H_SCAN):
        sg = np.where(ctx.v240, ctx.lab240['sg240'][r], 0) if H == 240 else ctx.lab[f'sg{H}'][r]
        for x, want in ((F['up'][k], sg > 0), (F['dn'][k], sg < 0)):
            direct = np.zeros(P.shape[1:])
            np.add.at(direct, (ca, cb, d), want)
            assert np.array_equal(x, direct), H
    direct = np.zeros(P.shape[1:])
    np.add.at(direct, (ca, cb, d), ctx.v240)
    assert np.array_equal(F['c6'][5], direct) and F['c6'][5].sum() < F['c6'][0].sum()
    for x, nm in ((F['hU'], 'holdU'), (F['hD'], 'holdD')):
        direct = np.zeros(P.shape[1:])
        np.add.at(direct, (ca, cb, d), ctx.lab[nm][r])
        assert np.array_equal(x, direct)
    # the fields never reach their bits: a day of 1,440 entries with every hold at 60
    big = {'rows': np.arange(1440), 'day': np.zeros(1440, np.int64), 'v240': np.ones(1440, bool)}
    lab = {f'sg{H}': np.ones(1440, np.int8) for H in hm.H_MAIN}
    lab.update(holdU=np.full(1440, 60, np.int8), holdD=np.full(1440, 60, np.int8))
    W = hm.pack_weights(lab, {'sg240': -np.ones(1440, np.int8)}, big)
    Fb = hm.unpack(np.r_[[1440.0], W.sum(1)].reshape(5, 1))
    assert (Fb['up'][:5] == 1440).all() and Fb['dn'][5] == 1440 and Fb['c6'][5] == 1440 and Fb['hU'] == 86400 and Fb['hD'] == 86400


def test_stats_equal_engine_cells_and_clu(tmp_path, splits):
    """A pair cell's odds and t equal the engine's g.cells on the sign track (and heat._clu) on the same entries, at 1-60
    minutes on the main grid and at 240 on the 240 grid; its lift over a's level equals g.cells' lift of b's level
    among a's entries; the numba statistics equal the numpy reference; the fused windows per day equal the bitmask and
    np.unique."""
    f = tmp_path / 'x.csv'
    _csv(f, splits, seed=2)
    ctx = _ctx(f, _path_readings)
    ia, ib = ctx.byname['1m:R10'], ctx.byname['15m:R3']
    A, B = hm._col(ctx, ia), hm._col(ctx, ib)
    P, _ = hm.pair_kernel(ctx, A, B)
    st = hm._stats(P, ctx, lift=True, oa=1, ob=1)
    ref = hm._stats_np(hm.unpack(P[:, 1:, 1:]), ctx, lift=True)
    for k in ('n', 'odds', 't', 'se', 'deff', 'p_up', 'hold_up', 'lift_a', 't_lift_a', 'lift_b', 't_lift_b', 'rest_a'):
        assert np.allclose(np.nan_to_num(st[k], nan=-9), np.nan_to_num(ref[k], nan=-9), rtol=1e-9, atol=1e-9), k
    la = 3                                                                # a = 1m:R10 high
    for si, s in enumerate('AB'):
        E = ctx.rows[(ctx.split == si) & (ctx.C[:, ia] == la + 1) & (ctx.C[:, ib] > 0)]
        codes = (heat.read_state(ctx.readings[ib], E)).astype(np.int64)
        cs = ctx.g.cells(s, ctx.g.pre(E, s), codes, 5, lift=True, late=False, win=False)
        for k, H in enumerate(hm.H_MAIN):
            for lb in range(5):
                if cs['n'][lb] < 5:
                    continue
                assert st['n'][si, k, la, lb] == cs['n'][lb]
                assert abs(st['odds'][si, k, la, lb] - 100 * cs[(H, 's')][lb]) < 1e-9
                assert abs(st['t'][si, k, la, lb] - cs[(H, 's_t')][lb]) < 1e-9
                assert abs(st['lift_a'][si, k, la, lb] - 100 * cs[(H, 's_lift')][lb]) < 1e-9
                assert abs(st['t_lift_a'][si, k, la, lb] - cs[(H, 's_tlift')][lb]) < 1e-9
        # heat._clu on the same entries, one cell
        lb = 3
        Ec = E[codes == lb]
        sp = ctx.g.sp[s]
        for k, H in enumerate(hm.H_MAIN):
            mu, se, G, deff = heat._clu(ctx.lab[f'sg{H}'][Ec] - sp.base[H]['msign'], ctx.g.day[Ec] - sp.d0, sp.ND, sp.bd_s[H], sp.N)
            assert abs(st['odds'][si, k, la, lb] - 50 * mu) < 1e-9 and abs(st['se'][si, k, la, lb] - se) < 1e-12 and st['days'][si, k, la, lb] == G
        with hm.h240():
            g4 = ctx.g240
            sp4 = g4.sp[s]
            E4 = Ec[np.isin(Ec, sp4.rows)]
            mu, se, G, _ = heat._clu(ctx.lab240['sg240'][E4] - sp4.base[240]['msign'], g4.day[E4] - sp4.d0, sp4.ND, sp4.bd_s[240], sp4.N)
        assert st['n'][si, 5, la, lb] == len(E4) < len(Ec) + 1
        assert abs(st['odds'][si, 5, la, lb] - 50 * mu) < 1e-9 and abs(st['se'][si, 5, la, lb] - se) < 1e-12
    # windows per day: fused counter == bitmask OR == np.unique
    r = hm.measure_cross(ctx, A, B)
    isB = ctx.split == 1
    for k, H in enumerate(hm.H_SCAN):
        for c in range(len(r['ka'])):
            sel = isB & (ctx.C[:, ia] == r['ka'][c] + 1) & (ctx.C[:, ib] == r['kb'][c] + 1) & (ctx.v240 if H == 240 else True)
            want = len(np.unique((ctx.rows[sel] + 1) // H)) / ctx.base[1]['ndays'][k]
            assert abs(r['st'][c, 1, k, hm.SI['wd']] - want) < 1e-12
        cells = np.full(len(ctx.rows), -1)
        for c in range(len(r['ka'])):
            cells[(ctx.C[:, ia] == r['ka'][c] + 1) & (ctx.C[:, ib] == r['kb'][c] + 1)] = c
        u = isB & (cells >= 0) & (ctx.v240 if H == 240 else True)
        wb = hm.windows_B(cells[u], ctx.rows[u], H, len(r['ka']))
        wu = hm.windows_B(cells[u], ctx.rows[u], H, 65)[:len(r['ka'])]          # > 64 cells: the np.unique path
        assert np.array_equal(wb, wu) and np.allclose(wb / ctx.base[1]['ndays'][k], r['st'][:, 1, k, hm.SI['wd']])


# ---------------------------------------------------------------------------------------------------- the two scales
def test_fits_on_planted_tables():
    """An exactly no-joint-term table gives |iota| < 1e-6; an exactly additive mean-sign table |iota_add| < 1e-6; a planted
    XOR with flat margins gives iota, iota_add and iota_robust > 0 in its 'together' cell. The numba fits equal the numpy
    ones; iota_robust is the one nearer zero when the two agree in sign, else 0."""
    rng = np.random.default_rng(0)
    La, Lb = 5, 4
    # log-linear [ab][ay][by]: log N = u_ab + v_ay + w_by
    u, v, w = rng.normal(0, 0.5, (La, Lb)), rng.normal(0, 0.4, (La, 3)), rng.normal(0, 0.4, (Lb, 3))
    N = 1000 * np.exp(u[:, :, None] + v[:, None, :] + w[None, :, :])
    F = hm.ipf(N[None])[0]
    ms = (N[..., 0] - N[..., 2]) / N.sum(-1)
    assert np.abs(50 * (ms - hm._fitted_ms(F))).max() < 1e-6
    assert np.allclose(hm._nb_ipf2(N[None], hm.IPF_MAX, hm.IPF_TOL)[0], F, rtol=1e-9)
    # additive mean sign: ms = mu + a + b, with flat share 0.2
    a, b = rng.uniform(-0.2, 0.2, La), rng.uniform(-0.2, 0.2, Lb)
    msa = 0.05 + a[:, None] + b[None, :]
    n = rng.integers(200, 2000, (La, Lb)).astype(float)
    up, dn = n * (0.8 + msa) / 2, n * (0.8 - msa) / 2
    fit = hm.additive_fit((up - dn)[None], n[None])[0]
    assert np.abs(50 * (msa - fit)).max() < 1e-6
    assert np.allclose(hm._nb_additive((up - dn)[None], n[None], hm.IPF_MAX, hm.IPF_TOL)[0], fit, atol=1e-10)
    # XOR with flat margins: (high, high) and (low, low) go up, mixed go down, every margin is flat
    p = np.array([[0.7, 0.5, 0.3], [0.5, 0.5, 0.5], [0.3, 0.5, 0.7]])
    cnt = np.array([[1000, 2000, 1000], [2000, 4000, 2000], [1000, 2000, 1000]], float)
    T = np.stack([cnt * p, np.zeros_like(cnt), cnt * (1 - p)], -1)
    ms = (T[..., 0] - T[..., 2]) / cnt
    i1 = 50 * (ms - hm._fitted_ms(hm.ipf(T[None])[0]))
    i2 = 50 * (ms - hm.additive_fit((T[..., 0] - T[..., 2])[None], cnt[None])[0])
    rob = hm.robust_iota(i1, i2)
    assert i1[2, 2] > 5 and i2[2, 2] > 5 and rob[2, 2] > 5 and i1[0, 2] < -5 and rob[0, 2] < -5
    assert np.allclose((ms * cnt).sum(0), 0) and np.allclose((ms * cnt).sum(1), 0)
    x = hm.robust_iota(np.array([2.0, -3.0, 1.0, 0.0]), np.array([1.0, -1.0, -1.0, 4.0]))
    assert list(x) == [1.0, -1.0, 0.0, 0.0]


def test_fits_settle_on_associated_readings():
    """(review fix) Two strongly associated readings (rho 0.95 and 0.99 of the joint table on its diagonal), each with a
    real call that adds on the mean-sign scale, and no joint term: the fits run until they settle, so iota_add is 0 and
    iota_robust is 0 to 1e-6 in every cell (30 rounds left up to 10 odds points of the same sign in both scales), and the
    numba fits equal the numpy ones. A multiplicative plant gives |iota| < 1e-6 the same way."""
    pr = np.array([0.02, 0.08, 0.8, 0.08, 0.02])
    eff = np.array([-0.2, -0.1, 0.0, 0.1, 0.2])
    for rho in (0.95, 0.99):
        J = rho * np.diag(pr) + (1 - rho) * np.outer(pr, pr)
        n = 1e6 * J
        ms = eff[:, None] + eff[None, :]
        up, dn = n * (0.8 + ms) / 2, n * (0.8 - ms) / 2
        N = np.stack([up, n * 0.2, dn], -1)
        ia = 50 * (ms - hm._nb_additive((up - dn)[None], n[None], hm.IPF_MAX, hm.IPF_TOL)[0])
        i1 = 50 * (ms - hm._fitted_ms(hm._nb_ipf2(N[None], hm.IPF_MAX, hm.IPF_TOL)[0]))
        assert np.abs(ia).max() < 1e-6 and np.abs(hm.robust_iota(i1, ia)).max() < 1e-6, rho
        assert np.abs(50 * (ms - hm.additive_fit((up - dn)[None], n[None])[0])).max() < 1e-6
        assert np.allclose(hm._fitted_ms(hm.ipf(N[None])[0]), hm._fitted_ms(hm._nb_ipf2(N[None], hm.IPF_MAX, hm.IPF_TOL)[0]), atol=1e-9)
        v = np.stack([2 * eff, np.zeros(5), -2 * eff], -1)                  # log N = u_ab + v_ay + v_by: no joint term
        E = np.exp(v[:, None, :] + v[None, :, :])
        M = n[..., None] * E / E.sum(-1, keepdims=True)
        msm = (M[..., 0] - M[..., 2]) / n
        assert np.abs(50 * (msm - hm._fitted_ms(hm._nb_ipf2(M[None], hm.IPF_MAX, hm.IPF_TOL)[0]))).max() < 1e-6, rho
        assert np.abs(50 * (msm - hm._fitted_ms(hm.ipf(M[None])[0]))).max() < 1e-6, rho


def test_copies_merge_and_alias_bases():
    """(review fixes) A true copy whose non-neutral entries are rare (99.7% agreement off 'none' on 1.2% of entries) is
    merged: the sample screen no longer drops it. The kept reading carries its copy's base as an alias base, and
    pair_list (and the triples' third readings) never pair it with a reading of that series."""
    N = 376_000
    rng = np.random.default_rng(25)
    a = np.where(rng.random(N) < 0.012, rng.integers(1, 3, N), 0).astype(np.int8)
    b = a.copy()
    on = np.flatnonzero(a > 0)
    b[rng.choice(on, int(round(0.003 * len(on))), replace=False)] = 0
    lv = ['none', 'bull', 'bear']
    R = [{'name': 'P1', 'k': 1, 'codes': a, 'levels': lv, 'base': 'P1'}, {'name': 'P2', 'k': 1, 'codes': b, 'levels': lv, 'base': 'P2'}]
    keep, al = hm.merge_aliases(R, np.arange(N), codes=np.stack([a + 1, b + 1], 1).astype(np.uint8), log=lambda *x: None)
    assert [r['name'] for r in keep] == ['P1'] and al == {'P1': ['P2']} and keep[0]['alias_bases'] == ['P2']
    # X zone absorbs Y zone; Y's sign reading (base Y) stays, and is never paired with X
    z = rng.integers(0, 5, N).astype(np.int8)
    sg = rng.integers(0, 2, N).astype(np.int8)
    R = [{'name': 'X', 'k': 1, 'codes': z, 'levels': list(heat.ZONES), 'base': 'X'},
         {'name': 'Y', 'k': 1, 'codes': z.copy(), 'levels': list(heat.ZONES), 'base': 'Y'},
         {'name': 'Y:sign', 'k': 1, 'codes': sg, 'levels': ['down', 'up'], 'base': 'Y'},
         {'name': 'Z', 'k': 1, 'codes': rng.integers(0, 5, N).astype(np.int8), 'levels': list(heat.ZONES), 'base': 'Z'}]
    C = np.stack([R[i]['codes'] + 1 for i in range(4)], 1).astype(np.uint8)
    keep, al = hm.merge_aliases([dict(r) for r in R], np.arange(N), codes=C, log=lambda *x: None)
    assert [r['name'] for r in keep] == ['X', 'Y:sign', 'Z'] and keep[0]['alias_bases'] == ['Y']

    class _C:
        pass
    c = _C()
    c.readings = keep
    pairs = {(keep[i]['name'], keep[j]['name']) for _, i, j in hm.pair_list(c)}
    assert pairs == {('X', 'Z'), ('Y:sign', 'Z')}


def _planted_labels(m, base_lab, base_240, codes_a, codes_b, p_up, seed):
    """Copies of the labels whose direction at every horizon is drawn afresh from p_up(a level, b level) of the states at
    the row (no flat move): the planted outcome scale holds at every horizon."""
    rng = np.random.default_rng(seed)
    lab, l240 = dict(base_lab), dict(base_240)
    p = p_up[np.clip(codes_a, 0, None), np.clip(codes_b, 0, None)]
    for H in hm.H_MAIN:
        lab[f'sg{H}'] = np.where(rng.random(m['n']) < p, 1, -1).astype(np.int8)
    l240['sg240'] = np.where(rng.random(m['n']) < p, 1, -1).astype(np.int8)
    return lab, l240


def test_planted_main_effects_no_joint_term(tmp_path, splits):
    """(review; design test 4) Two associated readings, each with a real call and no joint term: once additive on the
    probability scale, once multiplicative in the odds, at a moderate association and at a strong one (the case where a
    fit stopped early leaves a same-sign error in both scales). One plain measure then shows a scale artifact that keeps
    its sign on B (iota under the additive plant, iota_add under the multiplicative one: kept share at least 0.12 over the
    twins'), but iota_robust does not: its kept-interaction share on B is within 0.45-0.55 (a B value of exactly 0
    counts as not kept: build notes, the lower edge is 0.35), and no iheat row stands above the max of the three
    coin-flip twins (same readings, coin-flip outcomes) at its horizon."""
    f = tmp_path / 'x.csv'
    _csv(f, splits, seed=3)
    m = heat.load_minutes(str(f))
    lab = heat.labels(m)
    with hm.h240():
        lab240 = heat.labels(m)
    lv = ['l2', 'l1', 'mid', 'h1', 'h2']
    pr = np.array([0.15, 0.15, 0.4, 0.15, 0.15])
    eff = np.array([-0.22, -0.11, 0.0, 0.11, 0.22])
    shares = {}
    for same in (0.4, 0.97):
        for model in ('add', 'mult'):
            if model == 'add':
                p_up = np.clip(0.5 + eff[:, None] + eff[None, :], 0.05, 0.95)
            else:
                z = 4.5 * eff
                p_up = 1 / (1 + np.exp(-(z[:, None] + z[None, :])))
            kept = {tw: {'robust': [0, 0], 'iota': [0, 0], 'iota_add': [0, 0]} for tw in (0, 1)}
            real, twins = [], []
            for seed in range(3):
                rng = np.random.default_rng([seed, 7])
                ca = rng.choice(5, m['n'], p=pr).astype(np.int8)
                cb = np.where(rng.random(m['n']) < same, ca, rng.choice(5, m['n'], p=pr)).astype(np.int8)     # associated
                R = [{'name': 'SA', 'k': 1, 'codes': ca, 'levels': lv, 'base': 'SA', 'state': True},
                     {'name': 'SB', 'k': 1, 'codes': cb, 'levels': lv, 'base': 'SB', 'state': True}]
                for tw in (0, 1, 2, 3):
                    la, lb = _planted_labels(m, lab, lab240, ca, cb, p_up if tw == 0 else np.full((5, 5), 0.5), 100 * seed + tw)
                    ctx = _ctx(f, lambda m_, g_: R, labs=(la, lb), real=(tw == 0))
                    r = hm.measure_cross(ctx, hm._col(ctx, 0), hm._col(ctx, 1))
                    Dv = hm.derive(r)
                    (real if tw == 0 else twins).append(Dv)
                    for k, col in (('robust', 'iota_robust'), ('iota', 'iota'), ('iota_add', 'iota_add')):
                        sa, sb = np.sign(r['st'][:, 0, :, hm.SI[col]]), np.sign(r['st'][:, 1, :, hm.SI[col]])
                        use = Dv['ok'] & (sa != 0)
                        kept[min(tw, 1)][k][0] += int((use & (sa == sb)).sum())
                        kept[min(tw, 1)][k][1] += int(use.sum())
            twmax = np.max([np.max(np.where(D['ok'], D['iheat'], -np.inf), 0) for D in twins], 0)          # per horizon
            above = sum(int((D['ok'] & (D['iheat'] > twmax[None, :])).sum()) for D in real)
            share = {tw: {k: v[0] / v[1] for k, v in kk.items()} for tw, kk in kept.items()}
            shares[(same, model)] = share
            assert 0.35 <= share[0]['robust'] <= 0.55, (same, model, share)
            assert above == 0, (same, model, above)
    # the artifact the guard removes: the wrong-scale plain measure keeps its sign on B well above chance
    for same in (0.4,):
        assert shares[(same, 'add')][0]['iota'] >= shares[(same, 'add')][1]['iota'] + 0.12, shares
        assert shares[(same, 'mult')][0]['iota_add'] >= shares[(same, 'mult')][1]['iota_add'] + 0.12, shares


# --------------------------------------------------------------------------------------------------------- chance
def test_pure_noise_no_excess_over_twin(tmp_path, splits):
    """Pure noise (a random walk and readings of its own path) against its coin-flip twin (same pipeline): the kept
    direction and kept interaction (iota, iota_add, iota_robust) on B are within 0.45-0.55, the sd of t_iota on A is at
    most 1.2 on all cells and within 0.85-1.2 on the cells of near-independent multi-level readings (assoc < 0.1; see
    the build notes: the fit absorbs part of a cell's own noise, so cells of a 2-level or strongly associated reading
    run lower, on the coin and its twin alike), and at most 5% of the noise coin's iheat rows stand above the twin's
    max."""
    f = tmp_path / 'x.csv'
    _csv(f, splits, seed=11)
    real = _ctx(f, _path_readings)
    twin = _ctx(f, _path_readings, twin=1)
    sr, _, st, w = _scan(real, tmp_path)
    stw, _, _, _ = _scan(twin, tmp_path)
    assert st['pairs'] == len(real.readings) * (len(real.readings) - 1) // 2 and not os.path.exists(tmp_path / 'shards1')
    for s in (sr, stw):
        C = s['pair'].c[:, 0].sum(0)
        g = dict(zip(hm.SummaryCounts.COUNTS, C))
        assert g['cells'] > 500
        for a, b in (('dir_kept', 'dir_n'), ('iota_kept', 'iota_n'), ('iota_add_kept', 'iota_add_n')):
            assert 0.45 <= g[a] / g[b] <= 0.55, (a, g[a] / g[b])
        assert 0.45 <= g['robust_kept'] / g['robust_n'] <= 0.55                        # a B value of exactly 0 counts as not kept
    sh = _shards(tmp_path / 'shards0')                                   # the shards hold every cell with a sample
    ok = (sh['n'][:, 0] >= 30) & (sh['days'][:, 0] >= 30) & (sh['n'][:, 1] >= 30) & (sh['days'][:, 1] >= 20)
    assert ok.sum() == sum(int(sr['pair'].c[k, 0, 0]) for k in range(len(hm.H_SCAN)))
    for c in (real, twin):
        ti, ti01 = [], []
        for ia in range(len(c.readings)):
            for ib in range(ia + 1, len(c.readings)):
                r = hm.measure_cross(c, hm._col(c, ia), hm._col(c, ib))
                x = r['st'][:, 0, :, hm.SI['t_iota']][hm._sample(r['n'], r['days'])].tolist()
                ti += x
                if r['assoc'] < 0.1 and 'sign' not in c.names[ia] + c.names[ib]:
                    ti01 += x
        # all cells: at most 1.2 (no excess); the fit takes up part of a cell's own noise (leverage), most for a 2-level
        # reading or an associated pair, so the design's lower edge 0.85 holds on the near-independent multi-level cells
        assert len(ti) > 500 and 0.6 <= np.std(ti) <= 1.2, (c.twin, np.std(ti), len(ti))
        assert len(ti01) > 150 and 0.85 <= np.std(ti01) <= 1.2, (c.twin, np.std(ti01), len(ti01))
    above = cells = 0
    for k, H in enumerate(hm.H_SCAN):
        tmax = stw['pair'].top[(k, 'iheat', 'all')][0]
        above += int((sr['pair'].top[(k, 'iheat', 'all')] > tmax).sum())
        cells += int(sr['pair'].c[k, 0, 0])
    assert above <= 0.05 * cells, (above, cells)


# --------------------------------------------------------------------------------------------- a planted interaction
def test_planted_pure_interaction_found_on_B(tmp_path, splits):
    """Two 15-minute states, each flat alone, that call direction together (XOR: both high or both low -> up, one high
    and one low -> down), among noise readings: the planted cells lead the iheat list at 15 minutes with the right sign
    (iota_robust and iota_add in the planted direction on A, and on B with t >= 2), while each part alone has |t_A| < 3."""
    rng = np.random.default_rng(21)
    nb = DAYS * 96
    s1 = rng.choice(3, nb, p=[0.25, 0.5, 0.25]).astype(np.int8)
    s2 = rng.choice(3, nb, p=[0.25, 0.5, 0.25]).astype(np.int8)
    x = np.where((s1 == 1) | (s2 == 1), 0, np.where(s1 == s2, 1, -1)).astype(float)
    # bar b's state is known at its close; it drives the next bar's 15 minutes
    drift = np.repeat(np.r_[0.0, x[:-1]], 15) * 3e-4
    f = tmp_path / 'x.csv'
    _csv(f, splits, seed=4, drift=drift)
    lv = ['low', 'mid', 'high']

    def readings(m, g):
        R = _path_readings(m, g)
        R.append({'name': '15m:S1', 'k': 15, 'codes': s1[:m['n'] // 15], 'levels': lv, 'base': '15m:S1'})
        R.append({'name': '15m:S2', 'k': 15, 'codes': s2[:m['n'] // 15], 'levels': lv, 'base': '15m:S2'})
        return R
    ctx = _ctx(f, readings)
    _, cands, _, _ = _scan(ctx)
    i1, i2 = ctx.byname['15m:S1'], ctx.byname['15m:S2']
    for H in (15, 30):
        top = cands[(cands.kind == 'pair') & (cands.h == H) & (cands.measure == 'iheat')].sort_values('value', ascending=False).head(4)
        assert set(zip(top.ia, top.ib)) == {(min(i1, i2), max(i1, i2))}, top[['key', 'value']]
        for r in top.itertuples():
            want = 1 if r.la == r.lb else -1                               # levels 0 / 2: low / high
            assert r.d_iota == want and r.dir == want and np.sign(r.iota_add_A) == want
            assert r.iota_robust_B * want > 0 and r.t_robust_B * want >= 2 and r.iheat_B > 0
            assert abs(r.t_a_A) < 3 and abs(r.t_b_A) < 3                   # flat alone
            assert r.iota_with_call


# ------------------------------------------------------------------------------------------------- the 2025 cut
def test_no_A_label_reads_a_2025_price(tmp_path, splits):
    """Every A entry's label (1-60 minutes and its holds on the main grid, 240 minutes on the 240 grid) ends before the
    first minute of split B: the rows end 60 (240) minutes before it, and replacing every price from split B on leaves
    every A number unchanged (the packed weights, the totals and a pair's A statistics)."""
    f = tmp_path / 'x.csv'
    _csv(f, splits, seed=6)
    ctx = _ctx(f, _path_readings)
    b_row = (heat.SPLITS['B'][0] - ctx.m['t0']) // MIN
    A = ctx.split == 0
    assert ctx.rows[A].max() + 60 <= b_row - 1 and (ctx.rows[A] % hm.A_STRIDE == 0).all()
    assert ctx.rows[A & ctx.v240].max() + 240 <= b_row - 1 and ctx.rows[A & ~ctx.v240].max() > ctx.rows[A & ctx.v240].max()
    assert ctx.g240.sp['A'].hi == b_row - 240 and ctx.g.sp['A'].hi == b_row - 60
    df = pd.read_csv(f)
    late = df.ts >= heat.SPLITS['B'][0]
    rng = np.random.default_rng(99)
    k = rng.uniform(0.5, 2.0, int(late.sum()))
    for c in ('o', 'h', 'l', 'c'):
        df.loc[late, c] = df.loc[late, c] * k
    f2 = tmp_path / 'y.csv'
    df.to_csv(f2, index=False)
    ctx2 = _ctx(f2, lambda m, g: _path_readings(m, ctx.g))                 # the same readings' edges come from A only
    A2 = ctx2.split == 0
    assert np.array_equal(ctx.rows[A], ctx2.rows[A2]) and np.array_equal(ctx.v240[A], ctx2.v240[A2])
    assert np.array_equal(ctx.W[:, A], ctx2.W[:, A2]) and np.array_equal(ctx.C[A], ctx2.C[A2])
    dA = ctx.dsl[0]
    assert np.array_equal(ctx.T[..., dA], ctx2.T[..., dA])
    for ia, ib in ((0, 5), (2, 9), (4, 8)):
        r1 = hm.measure_cross(ctx, hm._col(ctx, ia), hm._col(ctx, ib))
        r2 = hm.measure_cross(ctx2, hm._col(ctx2, ia), hm._col(ctx2, ib))
        assert np.array_equal(r1['n'][:, 0], r2['n'][:, 0])
        keep = [hm.SI[x] for x in ('odds', 't', 'p_up', 'p_dn', 'hold_up', 'hold_dn', 'lift_min', 't_lift')]
        assert np.allclose(r1['st'][:, 0][..., keep], r2['st'][:, 0][..., keep], equal_nan=True)


def test_h240_restores_engine_and_grids(tmp_path, splits):
    """h240() switches the engine to the 240-minute horizon and heat_long's labels (no label past the series' end), and
    restores the engine afterwards, also when the block raises."""
    f = tmp_path / 'x.csv'
    _csv(f, splits, seed=8, days=DAYS)
    m = heat.load_minutes(str(f))
    before = (list(heat.HORIZONS), heat.HMAX, heat.labels)
    with hm.h240():
        assert heat.HORIZONS == [240] and heat.HMAX == 240 and heat.labels is not before[2]
        lab = heat.labels(m)
        assert lab['holdU'].dtype == np.int16 and not lab['valid'][m['n'] - 241:].any()
    assert (heat.HORIZONS, heat.HMAX, heat.labels) == before
    with pytest.raises(ValueError):
        with hm.h240():
            raise ValueError
    assert (heat.HORIZONS, heat.HMAX, heat.labels) == before


# ---------------------------------------------------------------------------------- merge, provenance, part, files
def test_merge_aliases_and_provenance(tmp_path, splits):
    """An exact copy under another name merges into the first name (its alias); two rare patterns that are 'none' on
    almost every minute do not; provenance labels a part in a pack 'pack' (an event label matches its state level),
    two readings stored together 'stored', anything else 'none'."""
    f = tmp_path / 'x.csv'
    _csv(f, splits, seed=9)
    rng = np.random.default_rng(1)

    def readings(m, g):
        R = _path_readings(m, g)
        R.append(dict(R[1], name='1m:R10copy', base='1m:R10copy'))
        n = m['n']
        for nm in ('CDL:A', 'CDL:B'):
            R.append({'name': f'1m:{nm}', 'k': 1, 'codes': np.where(rng.random(n) < 0.002, 1, 0).astype(np.int8), 'levels': ['none', 'bull', 'bear'],
                      'base': f'1m:{nm}', 'every': True})
        return R
    ctx = _ctx(f, readings)
    assert ctx.aliases == {'1m:R10': ['1m:R10copy']} and '1m:R10copy' not in ctx.names and ctx.byname['1m:R10copy'] == ctx.byname['1m:R10']
    assert '1m:CDL:A' in ctx.names and '1m:CDL:B' in ctx.names
    pk = tmp_path / 'traded_pack.json'
    json.dump({'rows': [{'key': '1m:R10copy=low (falling in)', 'aliases': []}]}, open(pk, 'w'))
    pp = tmp_path / 'pairs_X.csv.gz'
    pd.DataFrame({'trig': ['15m:R3=very high'], 'cond': ['1m:VR'], 'lv': ['mid']}).to_csv(pp, index=False)
    ctx.prov = hm.provenance(ctx, hm.load_hm1([str(pk)], str(pp)))
    a, b, c = ctx.byname['1m:R10'], ctx.byname['15m:R3'], ctx.byname['1m:VR']
    assert list(hm._prov_cells(ctx, a, b, np.array([1, 3]), np.array([0, 0]))) == [2, 0]
    assert list(hm._prov_cells(ctx, b, c, np.array([0]), np.array([4]))) == [1]


def test_candidates_keep_an_unseen_heap():
    """(review fix) Candidates keep the top k per (kind, horizon, measure) and, apart, the top k of the unseen cells
    (seen_in_league 'none'): an unseen cell ranked below the overall k-th stays in the pool; batches merge exactly in
    any order; the worker thresholds are the k-th value of each heap."""
    rng = np.random.default_rng(0)
    n = 60
    df = pd.DataFrame({'kind': 'pair', 'h': 15, 'measure': 'oheat', 'value': hm._sig6(rng.normal(size=n)), 'key': [f'k{i:02d}' for i in range(n)],
                       'seen_in_league': np.where(np.arange(n) % 3 == 0, 'none', 'pack')})
    c = hm.Candidates(k=10)
    c.add(df)
    f = c.frame()
    top_all = df.sort_values(['value', 'key'], ascending=[False, True]).head(10).key
    top_none = df[df.seen_in_league == 'none'].sort_values(['value', 'key'], ascending=[False, True]).head(10).key
    assert set(f.key) == set(top_all) | set(top_none) and len(set(top_none) - set(top_all)) > 0
    c2 = hm.Candidates(k=10)
    for part in (df.iloc[40:], df.iloc[:20], df.iloc[20:40]):
        c2.add(part)
    assert c2.frame().key.tolist() == f.key.tolist()
    th = c.kth()
    assert th[('all', 'pair', 15, 'oheat')] == df.value.sort_values(ascending=False).iloc[9]
    assert th[('none', 'pair', 15, 'oheat')] == df[df.seen_in_league == 'none'].value.sort_values(ascending=False).iloc[9]


def test_relist_measures_every_listed_row():
    """(review fix) The re-measure draws each list as the league does and measures any row it shows, until none is
    unmeasured. A chain of near copies under one reading (every A row is a near copy of the best one, which only its
    measurement shows) frees one per-reading slot per row it collapses, so drawing one round per reveal would take ~30
    rounds; the look-ahead (the rows below the list and the reading's held-back rows) settles it in a few, and the
    league's list on the final near-copy table shows only measured rows."""
    na, nf = 60, 80
    keys = [f'A=x & B{i:02d}=y' for i in range(na)] + [f'C{i:02d}=x & D{i:02d}=y' for i in range(nf)]
    conds = [json.dumps([['A', ['x']], [f'B{i:02d}', ['y']]]) for i in range(na)] + \
        [json.dumps([[f'C{i:02d}', ['x']], [f'D{i:02d}', ['y']]]) for i in range(nf)]
    pool = pd.DataFrame({'kind': 'pair', 'h': 15, 'key': keys, 'conds': conds, 'n_A': np.arange(na + nf) + 100,
                         'oheat_B': np.r_[np.linspace(100, 90, na), np.linspace(80, 10, nf)]})
    pools = {('pair', 15, 'all'): pool}
    first = hm.list_rows(pool, 'oheat', hm.TOP['oheat'])['key'].tolist()      # measured first (the n_top rows by the rule)
    groups = {('pair', 15, 'oheat', 'all'): list(first)}
    measured, calls = set(first), []

    def regroup(ks):
        calls.append(len(ks))
        measured.update(ks)

    def jac_of(kind, h):                         # what measuring shows: every measured A row is a near copy of A's best
        rows = [{'kind': kind, 'h': h, 'measure': 'oheat', 'key1': keys[0], 'key2': k, 'jaccard': 0.9}
                for k in keys[1:na] if k in measured and keys[0] in measured]
        return pd.DataFrame(rows, columns=['kind', 'h', 'measure', 'key1', 'key2', 'jaccard'])
    rounds, settled = hm.close_lists(pools, groups, measured, regroup, jac_of)
    assert settled and rounds <= 8
    L = hm.list_rows(pool, 'oheat', hm.TOP['oheat'], jac_of('pair', 15))
    assert len(L) == hm.TOP['oheat'] and set(L.key) <= measured
    assert L.key.iloc[0] == keys[0] and set(L.near.iloc[0]) == set(keys[1:na])      # the chain collapsed into one row
    assert len(measured) <= na + hm.TOP['oheat']                 # the look-ahead measured little beyond what the list shows


def test_provenance_per_coin(tmp_path):
    """(review fix) Pack levels count for their own coin only (the bot loads rows per coin); a row without a coin counts
    for every coin."""
    pk = tmp_path / 'traded_pack.json'
    json.dump({'rows': [{'coin': 'BTC', 'key': '15m:RSI14=low (falling in)'}, {'coin': 'ETH', 'key': '1m:R5=high'}, {'key': 'UTC1h=3'}]},
              open(pk, 'w'))
    b, e, a = hm.load_hm1([str(pk)], coin='BTC'), hm.load_hm1([str(pk)], coin='ETH'), hm.load_hm1([str(pk)])
    assert b['levels'] == {'15m:RSI14': {'low'}, 'UTC1h': {'3'}} and e['levels'] == {'1m:R5': {'high'}, 'UTC1h': {'3'}}
    assert set(a['levels']) == {'15m:RSI14', '1m:R5', 'UTC1h'}


def test_part_split_merges_exactly_and_series_files(tmp_path, splits):
    """--part 0/2 and 1/2 cover every pair once, and their summary counts and candidate pools merge into exactly the
    one-job result; the series job writes its files (JSON without NaN, the schema, the re-measured rows at every
    horizon, near copies, the triple cells chosen on A with at most 3 per reading)."""
    f = tmp_path / 'x.csv'
    _csv(f, splits, seed=12)
    ctx = _ctx(f, _path_readings)
    p0, p1, pall = hm.pair_list(ctx, (0, 2)), hm.pair_list(ctx, (1, 2)), hm.pair_list(ctx)
    assert len(p0) + len(p1) == len(pall) and set(map(tuple, np.r_[p0, p1].tolist())) == set(map(tuple, pall.tolist()))
    mt = hm.run_series('X', str(f), str(tmp_path / 'one'), ctx=ctx, learn=False, procs=2, log=lambda *a: None)
    for i in (0, 1):
        hm.run_series('X', str(f), str(tmp_path / f'p{i}'), ctx=ctx, learn=False, procs=1, part=(i, 2), log=lambda *a: None)
    fin = hm.run_series('X', str(f), str(tmp_path / 'fin'), ctx=ctx, learn=False, procs=1, parts_dirs=[str(tmp_path / 'p0'), str(tmp_path / 'p1')],
                        log=lambda *a: None)
    s1 = json.load(open(tmp_path / 'one' / 'summary_counts.json'))
    s2 = json.load(open(tmp_path / 'fin' / 'summary_counts.json'))
    assert s1['pair'] == s2['pair'] and s1['triple'] == s2['triple']
    c1 = pd.read_csv(tmp_path / 'one' / 'candidates.csv.gz')
    c2 = pd.read_csv(tmp_path / 'fin' / 'candidates.csv.gz')
    assert c1.shape == c2.shape and (c1.key.to_numpy() == c2.key.to_numpy()).all()
    assert mt['table_sha256'] == fin['table_sha256']
    meta = json.load(open(tmp_path / 'one' / 'meta.json'))
    assert meta['schema'] == 'oracle-heat-hm2-1' and meta['stride'] == 7 and meta['horizons'] == hm.H_SCAN and meta['real']
    tc = meta['triple_cells']
    assert tc and max(pd.Series([x[0] for x in tc] + [x[2] for x in tc]).value_counts()) <= hm.PER_READING
    h = pd.read_csv(tmp_path / 'one' / 'heat.csv.gz', low_memory=False)
    assert set(h.h) == set(hm.H_SCAN) and {'xstate', 'xonset', 'xtriple', 'baseline'} <= set(h.kind) and h.move_steps.notna().any()
    assert set(h.split) == {'A', 'B'} and (h.coin == 'X').all()
    for nm in ('summary_counts.json', 'meta.json', 'usage.json'):
        json.loads(open(tmp_path / 'one' / nm).read(), parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
    assert os.path.exists(tmp_path / 'one' / 'near_copies.csv.gz') and os.listdir(tmp_path / 'one' / 'shards')
    c = c1[(c1.kind == 'pair')]
    assert (c.n_A >= 30).all() and (c.days_B >= 20).all() and set(c.measure) == set(hm.MEASURES)
    assert np.allclose(c.oheat_B, c.wd_B * c.odds_B * c.dir)


def test_never_doge(tmp_path):
    with pytest.raises(SystemExit):
        hm.run_series('DOGE', 'x.csv', str(tmp_path))
    with pytest.raises(SystemExit):
        hm.base('BTC', '/data/DOGE/1m.csv')
