"""OR-XD readings inside OR-HM2 (heat_outside.hm2_outside_readings; heat_hm2 --outside; python/oracle/prereg/OR-XD.md).

(a) the hook, fed through HM2's loaders, gives the standalone study's codes, edges and values on identical synthetic data, with empty-tb
perp rows (broken bars: prices carried forward), duplicate OI stamps (clean_oi picks among the raw rows) and, on a twin, the pre-registered
OR-XD twin (twin spot x the real perp / spot ratio); (b) cut the future: replace everything after minute t, no code at a row <= t changes
(fixed edges, as the other HM2 cut tests); (c) a twin: the HM2 joint-flipped perp is ignored, the OI stays real, the guards read the real
perp, the model is driven by contracts, the twin follows its real coin's skips; (d) the skip behaviour (tb, oi_usd, the two input guards,
MIN_A_DAYS, fixed edges, a duck-typed Zoner that only has zone and skipped); (e) the flag off changes nothing (the hook is never called, the
plumbing with a stubbed hook leaves every file, the decompressed tables included, equal to the default run, no research-only key, no
--outside on the other commands); (f) an end-to-end smoke of the HM2 coin path with --outside on the synthetic world of
test_heat_hm2_xdata (part job and twin job through the command line): the five readings reach meta and the scan input, an input the hook
refuses stops the job; (g) the pack and live meta of the league leave research-only readings out (also as an alias of a kept row), Part 4's
chart pairs never pair one; (h) the workflow tag [hm2-outside] (plan step, Drive folder, league commit location). All data is synthetic."""
import argparse
import json
import os
import shutil
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from oracle import heat, heat_outside as xo
from oracle.common import DAY, MIN, ms

pytest.importorskip('talib')
xd = pytest.importorskip('oracle.heat_xdata')
hm = pytest.importorskip('oracle.heat_hm2')

T0 = ms('2024-11-01')
PYROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))      # .../python
ROOT = os.path.dirname(PYROOT)
FIVE = ['CVDP:Div15', 'CVDP:PxDiv60', 'LIQMAP:DistAbove', 'LIQMAP:DistBelow', 'LIQMAP:Skew']
quiet = lambda *a, **k: None


# ------------------------------------------------------------------------------------------------ synthetic data
def _frames(seed, days=8, dup=True):
    """Spot, perp (ts,o,h,l,c,v,tb) and OI (ts,oi,oi_usd) frames on a fat-tailed random walk: gaps in the spot and the perp, OI before
    the grid, off-grid OI stamps, OI holes and (dup) duplicate OI rows (as test_heat_outside_lookahead)."""
    rng = np.random.default_rng(seed)
    n = days * 1440
    ts = T0 + np.arange(n, dtype=np.int64) * MIN
    c = 3000 * np.exp(np.cumsum(rng.standard_t(3, n) * 6e-4))
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 3e-4, n)))
    l = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 3e-4, n)))
    v = rng.uniform(10, 200, n)
    spot = pd.DataFrame(dict(ts=ts, o=o, h=h, l=l, c=c, v=v, tb=v * rng.uniform(0.2, 0.8, n)))
    k = 1 + rng.normal(0, 2e-4, n)
    vp = v * rng.uniform(2, 4, n)
    perp = pd.DataFrame(dict(ts=ts, o=o * k, h=h * k * 1.0003, l=l * k * 0.9997, c=c * k, v=vp, tb=vp * rng.uniform(0.2, 0.8, n)))
    for _ in range(10):
        a = int(rng.integers(100, n - 100))
        spot = spot[~spot.ts.between(ts[a], ts[a + int(rng.integers(1, 20))])]
        a = int(rng.integers(100, n - 100))
        perp = perp[~perp.ts.between(ts[a], ts[a + int(rng.integers(1, 20))])]
    K = n // 5
    oits = T0 - 15 * MIN + np.arange(K, dtype=np.int64) * 5 * MIN
    usd = 1e9 * np.exp(np.cumsum(rng.normal(3e-4, 4e-3, K)))
    oi = pd.DataFrame(dict(ts=oits, oi=usd / 3000, oi_usd=usd))
    offg = rng.random(K) < 0.05
    oi.loc[offg, 'ts'] = oi.loc[offg, 'ts'] + rng.integers(1, 9000, int(offg.sum()))
    for _ in range(8):
        a = int(rng.integers(10, K - 10))
        oi = oi.drop(index=range(a, a + int(rng.integers(1, 8))), errors='ignore')
    if dup:
        oi = pd.concat([oi, oi.sample(20, random_state=seed).assign(oi_usd=lambda d: d.oi_usd * 1.1)])
    oi = oi.sort_values('ts', kind='stable')
    if not dup:
        oi = oi.drop_duplicates('ts', keep='first')
    return n, spot.reset_index(drop=True), perp.reset_index(drop=True), oi.reset_index(drop=True)


def _grid(df, n):
    """The engine's minute dict of a frame (what heat.load_minutes gives): a gap is forward-filled with zero volume."""
    pos = ((df.ts.to_numpy() - T0) // MIN).astype(int)
    gap = np.ones(n, bool)
    gap[pos] = False
    cc = np.full(n, np.nan)
    cc[pos] = df.c
    cc = pd.Series(cc).ffill().bfill().to_numpy()
    m = {'t0': T0, 'n': n, 'gap': gap, 'c': cc}
    for x in 'ohl':
        a = cc.copy()
        a[pos] = df[x]
        m[x] = a
    for x in ('v', 'tb'):
        a = np.zeros(n)
        a[pos] = df[x]
        m[x] = a
    m['tick'] = heat.tick_bps(cc, gap)
    return m


def _side(n, spot, perp, oi, twin=0):
    """(m, perp, oi, real) as OR-HM2 holds them: the minutes (heat.make_twin on a twin), the perp on the grid (xd.on_grid; joint-flipped
    with the spot on a twin), the OI frame with HM2's own 'known' column (ts + 5 minutes) and the real minutes and perp."""
    m_real = _grid(spot, n)
    pg = xd.on_grid(m_real, perp)
    real = {'m': m_real, 'perp': pg}
    f = oi.assign(known=oi['ts'] + 5 * MIN)
    if twin:
        return heat.make_twin(m_real, twin), xd.joint_flip(twin, T0, n)(pg), f, real
    return m_real, pg, f, real


def _write(d, spot, perp, oi):
    out = {}
    for nm, df in (('spot', spot), ('perp', perp), ('oi', oi)):
        out[nm] = os.path.join(str(d), f'{nm}.csv')
        df.to_csv(out[nm], index=False)
    return out


def _hook(m, perp, oi, a_hi, real=None, edges=None, **kw):
    z = xd.Zoner(a_hi, edges=edges, keep_values=True)
    info = kw.pop('info', None)
    R = xo.hm2_outside_readings(m, perp, oi, a_hi, z, quiet, info, real=real, **kw)
    return z, R


def _same(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    return a.shape == b.shape and bool(((np.isnan(a) & np.isnan(b)) | (a == b)).all())


@pytest.fixture
def lowshare(monkeypatch):
    """The frozen 2% cluster share rarely holds on a random walk (OR-XD, Amendment 1): the tests that need LIQMAP values lower it; the 30 days of A
    become 3."""
    monkeypatch.setattr(xo, 'CLUSTER_SHARE', 0.004)
    monkeypatch.setattr(xo, 'MIN_A_DAYS', 3)


# ------------------------------------------------------------------------------------------ (a) the same as the study
def _study_inputs(tmp_path, seed=0, days=10, dup=False, empty_tb=0, twin=0):
    """The files of one synthetic coin and the two ways to read them: heat_outside's own (perp_on_grid, clean_oi on the file's rows, xd_readings;
    on a twin run_coin_outside's twin rule) and HM2's (load_inputs, load_extra for the empty-tb count, the RAW OI rows, the hook). empty_tb:
    rows of the perp file whose tb cell is emptied (random ones, two at the very start, a run of three)."""
    n, spot, perp, oi = _frames(seed, days=days, dup=dup)
    if empty_tb:
        rng = np.random.default_rng(seed + 50)
        idx = list(rng.choice(np.arange(300, len(perp) - 300), empty_tb - 5, replace=False)) + [0, 1, 4000, 4001, 4002]
        perp.loc[perp.index[idx], 'tb'] = np.nan
    p = _write(tmp_path, spot, perp, oi)
    sp = heat.load_minutes(p['spot'], end=T0 + n * MIN)
    a_hi = 6 * 1440
    pg = xo.perp_on_grid(sp, pd.read_csv(p['perp']))
    oi_df = xo.clean_oi(pd.read_csv(p['oi']), pg)[0]
    m, skip, pp = sp, set(), pg
    if twin:
        m = heat.make_twin(sp, twin)
        skip = set(xo.xd_readings(sp, pg, oi_df, a_hi)['skipped'])
        pp = xo.twin_perp(pg, sp, m, xo.twin_signs(n, twin))
    ref = xo.xd_readings(m, pp, oi_df, a_hi, keep=True, skip=skip)
    kw = xd.load_inputs('BTC', sp, twin, {}, p['perp'], None, p['oi'], None, {}, log=quiet)['kwargs']
    info = {}
    z, R = _hook(m, kw['perp'], xo.read_checked(p['oi'], ('ts', 'oi'), 'OI'), a_hi, kw['real'], info=info, perp_frame=xd.load_extra(p['perp'], 'perp1m'),
                 seed=twin or None)
    return ref, z, R, info, p


@pytest.mark.parametrize('dup,empty_tb,twin', [(False, 0, 0), (True, 13, 0), (True, 13, 3)])
def test_hook_equals_the_standalone_study(tmp_path, lowshare, dup, empty_tb, twin):
    """HM2's loaders (load_extra, on_grid) and the hook against heat_outside's own (perp_on_grid, clean_oi, xd_readings): the same names in
    the same order, the same codes, edges and levels, the same stale-masked values; only the family spelling and the research flag differ.
    The cases that used to differ: perp rows with an EMPTY tb cell (the standalone run forward-fills the bar's prices, chained over
    consecutive rows and at the file's start; the model reads h / l / c on every row), duplicate OI stamps (clean_oi must see the raw rows
    to pick the one closest to the perp) and a twin (the OR-XD twin rule, not HM2's joint flip, with its real coin's skips)."""
    ref, z, R, info, p = _study_inputs(tmp_path, dup=dup, empty_tb=empty_tb, twin=twin)
    assert [r['name'] for r in ref['readings']] == FIVE, ref['skipped']
    assert [r['name'] for r in R] == FIVE and info['readings'] == FIVE and info['skipped'] == {} and info['refused'] == {}
    for a, b in zip(ref['readings'], R):
        assert a['levels'] == b['levels'] and a['edges'] == b['edges'] and np.array_equal(a['codes'], b['codes']), a['name']
        assert b['family'] == a['family'].lower() and b['family'] in ('cvdp', 'liqmap') and b['research_only'] is True and 'research_only' not in a
    assert z.edges == ref['edges']
    for nm in FIVE:
        assert _same(z.values[nm], ref['values'][nm]), nm
    assert info['edges'] == {r['name']: r['edges'] for r in R} and info['constants'] == xo.CONSTANTS
    xi = info['xd_input']
    assert xi['perp_spot_alignment']['checked'] and xi['oi_clock']['checked'] and xi['perp_missing_tb'] == empty_tb and xi['twin'] is bool(twin)
    assert xi['twin_seed'] == (twin or None) and (xi['twin_rule'] is not None) is bool(twin)
    if dup:
        assert xi['oi_duplicates_dropped'] > 20 and xi['oi_frame_rows'] == len(pd.read_csv(p['oi']))           # the raw rows, not load_extra's first-per-stamp frame
    assert info['model']['snapshots'] > 1000 and info['near_duplicates'] is not None
    assert set(info['reading_share']) == set(FIVE + xo.REFS) and set(info['direction_coupling']) == set(FIVE)


def test_the_hm2_flavour_of_the_inputs_would_have_differed(tmp_path, lowshare):
    """The two parity breaks the cases above close, shown on the same data: the OI frame heat_xdata.load_extra returns (first row per stamp)
    and a perp whose empty-tb bars keep their own prices both move LIQMAP values away from the standalone study."""
    ref, z, R, info, p = _study_inputs(tmp_path, dup=True, empty_tb=13)
    sp = heat.load_minutes(p['spot'], end=T0 + 10 * 1440 * MIN)
    kw = xd.load_inputs('BTC', sp, 0, {}, p['perp'], None, p['oi'], None, {}, log=quiet)['kwargs']
    a_hi = 6 * 1440
    z2, _ = _hook(sp, kw['perp'], kw['oi'], a_hi, kw['real'])                       # load_extra's frame: ts deduplicated first-in-file
    assert any(not _same(z2.values[nm], ref['values'][nm]) for nm in FIVE[2:])
    z3, _ = _hook(sp, kw['perp'], xo.read_checked(p['oi'], ('ts', 'oi'), 'OI'), a_hi, kw['real'])                  # no perp_frame: an empty tb is read as 0 on a live bar
    assert any(not _same(z3.values[nm], ref['values'][nm]) for nm in FIVE)


def test_the_known_column_of_the_frame_is_ignored(lowshare):
    """HM2's open-interest frame carries known = ts + 5 minutes; the OR-XD clock (ceil to 5 minutes, + 10 minutes) is the hook's own."""
    n, spot, perp, oi = _frames(2, days=8)
    m, pp, f, real = _side(n, spot, perp, oi)
    a_hi = 5 * 1440
    z1, R1 = _hook(m, pp, f, a_hi, real)
    z2, R2 = _hook(m, pp, f.assign(known=0), a_hi, real)
    z3, R3 = _hook(m, pp, f.assign(known=f['ts'] + 99 * MIN), a_hi, real)
    assert len(R1) == 5
    for a, b, c in zip(R1, R2, R3):
        assert np.array_equal(a['codes'], b['codes']) and np.array_equal(a['codes'], c['codes'])


def test_a_duck_typed_zoner_needs_only_zone_and_skipped(lowshare):
    """The hook reads nothing but z.zone(name, x, stale=, family=) and z.skipped (a_hi / fixed only when the Zoner has them)."""
    n, spot, perp, oi = _frames(2, days=8)
    m, pp, f, real = _side(n, spot, perp, oi)
    a_hi = 5 * 1440

    class MiniZ:
        def __init__(self):
            self.skipped, self.calls = [], []

        def zone(self, name, x, stale=None, family='', k=1):
            x = np.array(x, float)
            if stale is not None:
                x[np.asarray(stale, bool)] = np.nan
            R, e = xo.zone(name, x, a_hi, family)
            self.calls.append((name, family))
            if R is None:
                self.skipped.append(name)
            return R

    z = MiniZ()
    R = xo.hm2_outside_readings(m, pp, f, a_hi, z, quiet, None, real=real)
    assert [r['name'] for r in R] == FIVE and [c[0] for c in z.calls] == FIVE
    assert [c[1] for c in z.calls] == ['cvdp', 'cvdp', 'liqmap', 'liqmap', 'liqmap'] and z.skipped == []


def test_heat_outside_does_not_import_heat_xdata():
    """The module works without OR-HM2: importing heat_outside (and defining the hook) pulls in neither heat_xdata nor heat_hm2."""
    code = 'import sys; import oracle.heat_outside as x; assert hasattr(x, "hm2_outside_readings"); assert "oracle.heat_xdata" not in sys.modules and "oracle.heat_hm2" not in sys.modules'
    r = subprocess.run([sys.executable, '-c', code], cwd=PYROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-500:]


# ------------------------------------------------------------------------------------------------ (b) cut the future
def _noise_spot(spot, t, rng):
    s2 = spot.copy()
    m = (s2.ts > T0 + t * MIN).to_numpy()
    s2.loc[m, 'c'] = s2.loc[m, 'c'] * np.exp(rng.normal(0, 0.05, m.sum()))
    s2.loc[m, 'o'] = s2.loc[m, 'c']
    s2.loc[m, 'h'] = s2.loc[m, 'c'] * 1.01
    s2.loc[m, 'l'] = s2.loc[m, 'c'] * 0.99
    s2.loc[m, 'v'] = rng.uniform(0, 1e4, m.sum())
    s2.loc[m, 'tb'] = s2.loc[m, 'v'] * rng.random(m.sum())
    return s2


@pytest.mark.parametrize('seed,twin', [(0, 0), (1, 3)])
def test_cut_the_future_through_the_hook(seed, twin, lowshare):
    """Everything after minute t replaced (the spot by noise, the perp rows removed, the OI rows not yet known by the OR-XD clock removed): the
    codes and the stale-masked values of every reading are bit-identical on rows <= t (a fortiori on rows < t - 1 day), with the zone edges
    fixed as in the other HM2 cut tests, at random rows and at and one row before a snapshot's known time; real coin and twin."""
    n, spot, perp, oi = _frames(seed)
    a_hi = 5 * 1440
    m, pp, f, real = _side(n, spot, perp, oi, twin)
    zf, Rf = _hook(m, pp, f, a_hi, real, seed=twin or None)
    assert len(Rf) == 5
    rng = np.random.default_rng(seed + 100)
    Tk = np.sort(xo.clean_oi(oi)[0].ts.to_numpy() + xo.KNOWN)
    cand = [int(x) for x in rng.integers(3000, n - 10, 5)]
    for T in Tk[rng.integers(0, len(Tk), 3)]:
        r = int(-(-(int(T) - T0) // MIN)) - 1
        cand += [r - 1, r]
    for t in cand:
        close_t = T0 + (t + 1) * MIN
        oi_cut = oi[-(-oi.ts // xo.SNAP) * xo.SNAP + xo.KNOWN <= close_t]
        m2, pp2, f2, real2 = _side(n, _noise_spot(spot, t, rng), perp[perp.ts <= T0 + t * MIN], oi_cut, twin)
        zc, Rc = _hook(m2, pp2, f2, a_hi, real2, edges=zf.edges, seed=twin or None)
        assert [r['name'] for r in Rc] == FIVE
        for a, b in zip(Rf, Rc):
            assert np.array_equal(a['codes'][:t + 1], b['codes'][:t + 1]), (a['name'], t)
        for nm in FIVE:
            assert _same(zf.values[nm][:t + 1], zc.values[nm][:t + 1]), (nm, t)


# ----------------------------------------------------------------------------------------------------- (c) the twin
def test_the_twin_is_the_preregistered_one_not_the_joint_flip(lowshare, monkeypatch):
    """OR-XD (Twins): the perp path of a twin is the twin SPOT o / h / l / c times the REAL perp / spot close ratio (the real basis is kept) and
    its taker-buy volume is flipped with the spot's signs. HM2's joint flip (xd.joint_flip: the perp's own path flipped, tb swapped where s < 0)
    agrees only for a constant basis, so the hook builds the pre-registered path from the REAL perp and the seed and ignores the flipped
    perp it is handed: any perp argument gives the same readings, the twin's log-basis has the real coin's size (the flipped one's random-walks
    away), tb is the standalone twin's bit for bit, and the signs are heat.make_twin's own."""
    n, spot, perp, oi = _frames(2, days=10, dup=False)
    seed, a_hi = 3, 6 * 1440
    m, flipped, f, real = _side(n, spot, perp, oi, seed)
    s = xo.twin_signs(n, seed)
    assert np.array_equal(xd.joint_flip(seed, T0, n).signs(T0, n), s)
    seen = []
    orig = xo.xd_values
    monkeypatch.setattr(xo, 'xd_values', lambda sp, pp, o, *a, **k: seen.append((sp, pp)) or orig(sp, pp, o, *a, **k))
    z1, R1 = _hook(m, flipped, f, a_hi, real, seed=seed)
    garbage = dict(flipped, c=np.full(n, 7.0), o=np.full(n, 7.0), h=np.full(n, 7.0), l=np.full(n, 7.0), tb=np.zeros(n))
    z2, R2 = _hook(m, garbage, f, a_hi, real, seed=seed)
    z3, R3 = _hook(m, None, f, a_hi, real, seed=seed)
    assert len(R1) == 5
    for a, b, c in zip(R1, R2, R3):
        assert np.array_equal(a['codes'], b['codes']) and np.array_equal(a['codes'], c['codes']) and a['edges'] == b['edges'] == c['edges']
    pp = next(pp for sp, pp in seen if sp is m)                              # the path the model and the readings ran on
    pg = xo.perp_on_grid(real['m'], perp)
    assert np.array_equal(pp['tb'], np.where(s > 0, pg['tb'], pg['v'] - pg['tb']))
    ratio = pg['c'] / real['m']['c']
    ok = ~pg['gap'] & np.isfinite(ratio)
    np.testing.assert_allclose(pp['c'][ok], (m['c'] * ratio)[ok], rtol=1e-12)
    basis = lambda perp_c, spot_c: np.nanstd(np.log(np.asarray(perp_c, float) / np.asarray(spot_c, float))[ok])
    assert basis(pp['c'], m['c']) < 3 * basis(pg['c'], real['m']['c'])                       # the real basis is kept
    assert basis(flipped['c'], m['c']) > 10 * basis(pg['c'], real['m']['c'])                 # HM2's flip lets it random-walk
    ref = xo.xd_readings(m, xo.twin_perp(pg, real['m'], m, s), xo.clean_oi(oi, pg)[0], a_hi, keep=True, skip=set(xo.xd_readings(real['m'], pg, xo.clean_oi(oi, pg)[0], a_hi)['skipped']))
    assert [r['name'] for r in ref['readings']] == [r['name'] for r in R1]
    for nm in [r['name'] for r in R1]:
        assert _same(z1.values[nm], ref['values'][nm]), nm


def test_a_twin_needs_its_seed_and_the_real_inputs(lowshare):
    n, spot, perp, oi = _frames(2, days=8)
    m, pp, f, real = _side(n, spot, perp, oi, 2)
    with pytest.raises(ValueError, match='seed'):
        _hook(m, pp, f, 5 * 1440, real, twin=True)
    with pytest.raises(ValueError, match='real'):
        _hook(m, pp, f, 5 * 1440, None, seed=2)
    m0, pp0, f0, real0 = _side(n, spot, perp, oi)
    z, R = _hook(m0, pp0, f0, 5 * 1440, real0)                               # no seed, not a twin: the perp given is the real one
    assert len(R) == 5


def test_twin_guards_read_the_real_perp_and_the_model_runs_on_contracts(lowshare, monkeypatch):
    """On a twin the alignment guard, the OI clock guard and the OI row pick get the REAL spot and perp (the flipped perp would fail them);
    OI stays real, and a constant number of contracts adds nothing although oi_usd follows the real price (the model is driven by
    contracts, not USD, so a twin's adds do not inherit the real price move)."""
    n = 6 * 1440
    rng = np.random.default_rng(4)
    ts = T0 + np.arange(n, dtype=np.int64) * MIN
    c = 3000 * np.exp(np.cumsum(rng.normal(0, 7e-4, n)))
    o = np.r_[c[0], c[:-1]]
    v = rng.uniform(10, 200, n)
    spot = pd.DataFrame(dict(ts=ts, o=o, h=np.maximum(o, c) * 1.0002, l=np.minimum(o, c) * 0.9998, c=c, v=v, tb=v * rng.uniform(0.3, 0.7, n)))
    perp = spot.assign(v=v * 3, tb=v * 3 * rng.uniform(0.3, 0.7, n))
    K = n // 5
    ots = T0 + np.arange(K, dtype=np.int64) * 5 * MIN
    oi = pd.DataFrame({'ts': ots, 'oi': 1e5, 'oi_usd': 1e5 * o[(ots - T0) // MIN]})            # never a new contract
    m, pp, f, real = _side(n, spot, perp, oi, twin=5)
    seen = {}
    orig_a, orig_o = xo.check_alignment, xo.check_oi_clock
    monkeypatch.setattr(xo, 'check_alignment', lambda sp, p: seen.setdefault('align', (sp, p)) and orig_a(sp, p))
    monkeypatch.setattr(xo, 'check_oi_clock', lambda o_, p: seen.setdefault('clock', p) and orig_o(o_, p))
    info = {}
    z, R = _hook(m, pp, f, 4 * 1440, real, info=info, seed=5)
    assert info['refused'] == {} and info['twin'] is True
    assert seen['align'][0] is real['m'] and seen['align'][0] is not m
    real_c = np.asarray(real['perp']['c'], float)
    np.testing.assert_array_equal(seen['align'][1]['c'], real_c)
    np.testing.assert_array_equal(seen['clock']['c'], real_c)
    assert not np.allclose(np.asarray(pp['c'], float), real_c)                                  # the flipped perp is another path
    assert info['model']['steps_add'] == 0 and info['model']['snapshots'] > 1000


def test_a_twin_follows_the_skips_of_its_real_coin(lowshare, monkeypatch):
    """OR-XD twin rule: a reading skipped for the real coin is skipped for its twins (the same families in the league); the real coin's run is
    recomputed on the real minutes and the real perp. Not applied with fixed edges (live / parity)."""
    n, spot, perp, oi = _frames(2, days=8)
    a_hi = 5 * 1440
    m, pp, f, real = _side(n, spot, perp, oi, twin=1)
    called = []

    def fake(sp, p, o, a, **k):
        called.append((sp, p))
        return {'skipped': ['CVDP:Div15', 'LIQMAP:Skew']}
    monkeypatch.setattr(xo, 'xd_readings', fake)
    info = {}
    z, R = _hook(m, pp, f, a_hi, real, info=info, seed=1)
    assert [r['name'] for r in R] == ['CVDP:PxDiv60', 'LIQMAP:DistAbove', 'LIQMAP:DistBelow'] and len(called) == 1
    assert called[0][0] is real['m'] and set(info['skipped']) == {'CVDP:Div15', 'LIQMAP:Skew'} and 'twin rule' in info['skipped']['CVDP:Div15']
    assert z.skipped == ['CVDP:Div15', 'LIQMAP:Skew']
    called.clear()
    full = {r['name']: r['edges'] for r in R}
    z2, R2 = _hook(m, pp, f, a_hi, real, edges=full, seed=1)
    assert not called and [r['name'] for r in R2] == list(full)                                  # fixed edges: no real run, only the names with an edge


# ------------------------------------------------------------------------------------------------------ (d) skipping
@pytest.fixture
def small():
    n, spot, perp, oi = _frames(3, days=6, dup=False)
    return {'n': n, 'spot': spot, 'perp': perp, 'oi': oi, 'a_hi': 4 * 1440, 'side': _side(n, spot, perp, oi)}


def _all_skipped(z, R, info, key, word):
    assert R == [] and sorted(info['skipped']) == sorted(FIVE) and sorted(z.skipped) == sorted(FIVE) and info['readings'] == []
    assert word in info['refused'][key] and all(word in why for why in info['skipped'].values())


def test_no_tb_column_skips_all_five(small, lowshare):
    m, pp, f, real = small['side']
    info = {}
    z, R = _hook(m, dict(pp, tb=None), f, small['a_hi'], real, info=info)
    _all_skipped(z, R, info, 'perp', 'taker-buy')
    info = {}
    z, R = _hook(m, dict(pp, tb=np.zeros(small['n'])), f, small['a_hi'], real, info=info)           # an empty tb column that on_grid turned into zeros
    _all_skipped(z, R, info, 'perp', 'zero on every bar')
    info = {}
    z, R = _hook(m, None, f, small['a_hi'], real, info=info)
    _all_skipped(z, R, info, 'perp', 'no perp')


def test_empty_tb_rows_are_gaps_and_a_file_full_of_them_is_refused(small, lowshare):
    m, pp, f, real = small['side']
    perp = small['perp']
    many = perp.copy()
    many.loc[many.index[::50], 'tb'] = np.nan                                          # 2% of the rows
    info = {}
    z, R = _hook(m, xd.on_grid(m, many), f, small['a_hi'], real, info=info, perp_frame=many)
    _all_skipped(z, R, info, 'perp', 'empty tb')
    few = perp.copy()
    rows = [500, 3000, 6000]
    few.loc[few.index[rows], 'tb'] = np.nan
    pgf = xd.on_grid(m, few)
    info = {}
    z, R = _hook(m, pgf, f, small['a_hi'], {'m': m, 'perp': pgf}, info=info, perp_frame=few)
    assert [r['name'] for r in R] == FIVE and info['xd_input']['perp_missing_tb'] == 3
    gone = [(int(t) - T0) // MIN for t in few.ts.to_numpy()[few.tb.isna().to_numpy()]]
    assert len(gone) == 3 and all(np.isnan(z.values['CVDP:Div15'][g]) for g in gone)          # a gap minute carries no reading
    ref = xo.xd_readings(m, xo.perp_on_grid(m, few), xo.clean_oi(small['oi'], xo.perp_on_grid(m, few))[0], small['a_hi'], keep=True)
    for nm in ('CVDP:Div15', 'CVDP:PxDiv60'):                                     # the CVDP readings do not read a gap minute's price: the same as the standalone run
        assert _same(z.values[nm], ref['values'][nm]), nm


def test_oi_usd_missing_skips_only_the_liqmap_readings(small, lowshare):
    m, pp, f, real = small['side']
    ref = xo.xd_readings(m, xo.perp_on_grid(m, small['perp']), xo.clean_oi(small['oi'], xo.perp_on_grid(m, small['perp']))[0], small['a_hi'])
    for oi_, why in ((f.drop(columns='oi_usd'), 'oi_usd is missing'), (None, 'no open-interest frame'), (f.iloc[:0], 'no usable OI row')):
        info = {}
        z, R = _hook(m, pp, oi_, small['a_hi'], real, info=info)
        assert [r['name'] for r in R] == ['CVDP:Div15', 'CVDP:PxDiv60'] and 'oi' in info['refused'] and why in info['refused']['oi']
        assert sorted(info['skipped']) == sorted(FIVE[2:]) and all(why in w for w in info['skipped'].values()) and sorted(z.skipped) == sorted(FIVE[2:])
        for a, b in zip(ref['readings'][:2], R):
            assert np.array_equal(a['codes'], b['codes']), a['name']                  # CVDP does not read the OI


def test_the_alignment_guard_skips_all_five_for_a_shifted_perp(small, lowshare):
    m, pp, f, real = small['side']
    pg = xd.on_grid(m, small['perp'].assign(ts=small['perp'].ts - MIN))               # stamped one minute early: a minute of look-ahead
    info = {}
    z, R = _hook(m, pg, f, small['a_hi'], {'m': m, 'perp': pg}, info=info)
    _all_skipped(z, R, info, 'perp', 'not on the spot clock')


def test_the_oi_clock_guard_skips_only_the_liqmap_readings(small, lowshare):
    m, pp, f, real = small['side']
    po = pd.Series(small['perp'].o.to_numpy(), index=small['perp'].ts)
    early = f.assign(oi_usd=f.oi * po.reindex(f.ts + 15 * MIN).to_numpy())             # the implied price belongs to ts + 15 minutes: stamps too early
    info = {}
    z, R = _hook(m, pp, early, small['a_hi'], real, info=info)
    assert [r['name'] for r in R] == ['CVDP:Div15', 'CVDP:PxDiv60'] and 'OI clock guard' in info['refused']['oi']
    assert sorted(info['skipped']) == sorted(FIVE[2:])


def test_thirty_distinct_days_of_a_are_enforced(small, monkeypatch):
    """z.zone enforces MIN_A values and the empty inner zones; MIN_A_DAYS (heat_outside.zone's rule) the hook enforces itself, with the
    frozen 30 days: 4 days of A give no reading although a plain Zoner would zone the CVDP series."""
    monkeypatch.setattr(xo, 'CLUSTER_SHARE', 0.004)
    m, pp, f, real = small['side']
    info = {}
    z, R = _hook(m, pp, f, small['a_hi'], real, info=info)
    assert R == [] and sorted(info['skipped']) == sorted(FIVE) and all(w.startswith(('values on', 'fewer than')) for w in info['skipped'].values())
    assert info['skipped']['CVDP:Div15'] == 'values on 4 distinct days of A, fewer than 30'
    X = xo.xd_values(m, xo._hm2_perp(pp, 'perp'), pd.DataFrame({'ts': np.zeros(0, np.int64), 'oi': np.zeros(0), 'oi_usd': np.zeros(0)}))
    assert xd.Zoner(small['a_hi']).zone('CVDP:Div15', X['values']['CVDP:Div15'], xo.stale_for('CVDP:Div15', X['gap']), family='cvdp') is not None
    monkeypatch.setattr(xo, 'MIN_A_DAYS', 3)                          # the days are counted per reading: three of them are enough for all five here
    z, R = _hook(m, pp, f, small['a_hi'], real)
    assert [r['name'] for r in R] == FIVE


def test_fixed_edges_register_only_the_names_that_have_one(small, lowshare):
    m, pp, f, real = small['side']
    z0, R0 = _hook(m, pp, f, small['a_hi'], real)
    keep = {k: v for k, v in z0.edges.items() if k in ('CVDP:Div15', 'LIQMAP:Skew')}
    info = {}
    z, R = _hook(m, pp, f, small['a_hi'], real, edges=keep, info=info)
    assert [r['name'] for r in R] == ['CVDP:Div15', 'LIQMAP:Skew'] and info['skipped']['CVDP:PxDiv60'] == 'no stored edge'
    assert np.array_equal(R[0]['codes'], R0[0]['codes']) and 'stored edges' in info['xd_input']['edges_from']


# --------------------------------------------------------------------------------------------- (e), (f) the HM2 path
@pytest.fixture(scope='module')
def world(tmp_path_factory):
    """The synthetic world of test_heat_hm2_xdata (four coins, BTC's perp / funding / OI, Coinbase, BTCDOM, book, daily markets; SPLITS patched
    to 65 days: A 50, B 15) with the 13 daily series the real run reads, and the frozen LIQMAP cluster share lowered so that all five readings
    exist on random OI. Yields the paths and two contexts of heat_hm2.base: the default one and the --outside one."""
    xt = pytest.importorskip('oracle.tests.test_heat_hm2_xdata')
    old = heat.SPLITS
    heat.SPLITS = xt.SPL
    mp = pytest.MonkeyPatch()
    try:
        d = tmp_path_factory.mktemp('hm2outside')
        P = xt._world(d)
        for nm in xd.DMKT_NAMES:
            f = os.path.join(P['dom'], f'{nm}_1d.csv')
            if not os.path.exists(f):
                shutil.copy(os.path.join(P['dom'], 'ETH.D_1d.csv'), f)
        mp.setattr(xo, 'CLUSTER_SHARE', 0.001)
        others = {o: P[o] for o in xd.COINS if o != 'BTC'}
        found = {'btcdom': P['btcdom'], 'cb': P['cb'], 'book': P['book']}
        kw = dict(other_csvs=others, perp_csv=P['perp'], fund_csv=P['funding'], oi_csv=P['oi'], cal_csv=xt.CAL, dom=P['dom'], found=found, log=quiet)
        mp2 = pytest.MonkeyPatch()
        try:                                                    # the flag off never calls the hook (a call would fail the fixture)
            mp2.setattr(xo, 'hm2_outside_readings', lambda *a, **k: (_ for _ in ()).throw(AssertionError('the OR-XD hook ran without --outside')))
            off = hm.base('BTC', P['BTC'], **kw)

            def nothing(m, perp, oi, a_hi, z, log=print, info=None, **k):          # the plumbing alone: --outside with a hook that adds no reading
                info.update(readings=[], skipped={}, refused={}, twin=False)
                return []
            mp2.setattr(xo, 'hm2_outside_readings', nothing)
            stub = hm.base('BTC', P['BTC'], outside=True, **kw)
        finally:
            mp2.undo()
        on = hm.base('BTC', P['BTC'], outside=True, **kw)
        cli = ['--asset', 'BTC', '--csv', P['BTC'], '--others', ','.join(f'{k}={v}' for k, v in others.items()), '--perp', P['perp'], '--fund', P['funding'],
               '--oi', P['oi'], '--cal', xt.CAL, '--dom', P['dom'], '--found', json.dumps(found), '--procs', '1', '--no-learn']
        yield {'P': P, 'kw': kw, 'off': off, 'on': on, 'stub': stub, 'cli': cli, 'dir': d, 'xt': xt}
    finally:
        mp.undo()
        heat.SPLITS = old


TIMINGS = ('seconds', 'seconds_total', 'worker_seconds', 'wall_seconds', 'peak_rss_mb', 'shards')


def _meta_bytes(path, drop=()):
    """meta.json without the timings and the output paths, wherever they sit (the rest is deterministic), and without the top-level keys in `drop`."""
    def strip(o):
        if isinstance(o, dict):
            return {k: strip(v) for k, v in o.items() if k not in TIMINGS and not k.endswith('_seconds')}
        return [strip(v) for v in o] if isinstance(o, list) else o
    mt = strip(json.load(open(path)))
    for k in drop:
        mt.pop(k, None)
    return json.dumps(mt, sort_keys=True)


def _content(path):
    """A series file's bytes, a .gz decompressed (the gzip header carries a time stamp)."""
    import gzip
    return (gzip.open(path, 'rb') if path.endswith('.gz') else open(path, 'rb')).read()


def _light(monkeypatch, ctx_pairs=True):
    """The scan reduced to what the smoke test is about: the triple stage off, the pair stage over the pairs that hold a research-only reading."""
    monkeypatch.setattr(hm, 'scan_triples', lambda *a, **k: {})
    if ctx_pairs:
        orig = hm.pair_list

        def only_outside(ctx, part=(0, 1), max_pairs=None, seed=0):
            pl = orig(ctx, part, None, seed)
            ro = [i for i, R in enumerate(ctx.readings) if R.get('research_only')]
            pl = pl[np.isin(pl[:, 1], ro) | np.isin(pl[:, 2], ro)]
            return pl[:240]
        monkeypatch.setattr(hm, 'pair_list', only_outside)


def test_flag_off_changes_nothing(world, monkeypatch, tmp_path):
    """Without --outside: no research-only key anywhere (readings, meta, ctx), nothing of the five in the context, and with it on every
    other reading keeps its place, name, levels, aliases, family and codes bit for bit (so the pair scan of a flag-off run is the one it
    always was); the shared parser helper gives the other commands no such key, only heat_hm2's coin, finish and bench take the flag."""
    off, on = world['off'], world['on']
    assert not hasattr(off, 'outside') and not any(R.get('research_only') for R in off.readings)
    assert not any(n.startswith(('CVDP:', 'LIQMAP:')) for n in off.names) and 'cvdp' not in off.families and 'liqmap' not in off.families
    new = [i for i, R in enumerate(on.readings) if R.get('research_only')]
    old = [i for i in range(len(on.readings)) if i not in new]
    assert [on.readings[i]['name'] for i in new] == FIVE and new == list(range(len(on.readings) - 5, len(on.readings)))
    assert [on.readings[i]['name'] for i in old] == off.names and [on.fam[i] for i in old] == off.fam
    assert [on.readings[i].get('aliases') for i in old] == [R.get('aliases') for R in off.readings] and [on.L[i] for i in old] == off.L
    assert np.array_equal(on.C[:, old], off.C) and np.array_equal(on.rows, off.rows) and np.array_equal(on.W, off.W)
    assert on.xdata == off.xdata                                               # edges_new, norms and missing: the five are not in them
    # the series files. The flag off is the default: the hook never ran for `off` (the fixture would have failed). `stub` is --outside with a
    # hook that adds no reading, so the plumbing (the flag, the context's outside block, the meta writer) is all that differs: every table, decompressed,
    # and every other file is byte-identical to the default run, and meta.json differs by its 'outside' block alone. (The original code's
    # output was compared by hand in the review of this change: the same files, byte for byte, for BTC and twin 1.)
    _light(monkeypatch, ctx_pairs=False)
    outs = []
    for i, ctx in enumerate((off, world['stub'])):
        out = str(tmp_path / f'off{i}')
        hm.run_series('BTC', world['P']['BTC'], out, ctx=ctx, learn=False, procs=1, max_pairs=120, log=quiet)
        outs.append(out)
    assert _meta_bytes(os.path.join(outs[0], 'meta.json')) == _meta_bytes(os.path.join(outs[1], 'meta.json'), drop=('outside',))
    txt = open(os.path.join(outs[0], 'meta.json')).read()
    assert 'research_only' not in txt and '"outside"' not in txt and 'CVDP' not in txt and 'LIQMAP' not in txt
    assert '"outside"' in open(os.path.join(outs[1], 'meta.json')).read()
    same = [f for f in sorted(os.listdir(outs[0])) if f != 'meta.json' and os.path.isfile(os.path.join(outs[0], f)) and f.endswith(('.json', '.csv', '.gz'))]
    assert {'summary_counts.json', 'candidates.csv.gz'} <= set(same) and set(os.listdir(outs[0])) == set(os.listdir(outs[1])), (same, os.listdir(outs[1]))
    for f in same:
        assert _content(os.path.join(outs[0], f)) == _content(os.path.join(outs[1], f)), f
    # the command line
    ap = argparse.ArgumentParser()
    hm._inputs(ap)
    a = ap.parse_args(['--asset', 'BTC', '--csv', 'x.csv'])
    assert 'outside' not in hm._kw(a) and not hasattr(a, 'outside')
    assert hm._kw(ap.parse_args(['--asset', 'BTC', '--csv', 'x.csv']))['xdata'] is True
    hm._outside_arg(ap)
    assert 'outside' not in hm._kw(ap.parse_args(['--asset', 'BTC', '--csv', 'x.csv'])) and hm._kw(ap.parse_args(['--asset', 'BTC', '--csv', 'x.csv', '--outside']))['outside'] is True
    help_of = lambda mod, cmd: _help(mod, cmd)
    for cmd in ('coin', 'finish', 'bench'):
        assert '--outside' in help_of(hm, cmd)
    pat = pytest.importorskip('oracle.heat_patterns')
    dr = pytest.importorskip('oracle.heat_hm2_drill')
    for mod in (pat, dr):
        assert '--outside' not in help_of(mod, 'coin')


def _help(mod, cmd):
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), pytest.raises(SystemExit):
        mod.main([cmd, '--help'])
    return buf.getvalue()


def test_outside_with_no_xdata_is_refused_and_a_name_clash_stops_the_job(world, monkeypatch):
    kw = dict(world['kw'])
    with pytest.raises(SystemExit, match='no-xdata'):
        hm.base('BTC', world['P']['BTC'], xdata=False, outside=True, **kw)
    monkeypatch.setattr(heat, 'build_readings', lambda m, g, dom, log=print: ([], heat.Rows(), {}, [], 0.01))
    orig = hm._extra_readings

    def clash(*a, **k):
        res = orig(*a, **k)
        ob = k['outside'] if 'outside' in k else a[-1]
        ob['readings'] = ob['readings'] + [dict(ob['readings'][0], name=res[0][0]['name'])]
        return res
    monkeypatch.setattr(hm, '_extra_readings', clash)
    with pytest.raises(SystemExit, match='collide'):
        hm.base('BTC', world['P']['BTC'], outside=True, **kw)


def test_the_five_readings_reach_meta_and_the_scan(world, monkeypatch, tmp_path):
    """--outside on the synthetic HM2 world: the five readings are in the context after the copy merge (families cvdp and liqmap, unique
    names, a code matrix with known levels), in the pair list and the pair scan, in meta.json's readings (flagged research_only) with
    their zone edges and measures in the 'outside' block (not in edges_new, which the live meta reads), in the summary strata and
    the family list; and the learner's feature set sees them as a new family, not as TA."""
    on = world['on']
    names = [R['name'] for R in on.readings]
    assert len(set(names)) == len(names) and set(FIVE) <= set(names)
    ix = [on.byname[n] for n in FIVE]
    assert {on.fam[i] for i in ix} == {'cvdp', 'liqmap'} and {'cvdp', 'liqmap'} <= set(on.families)
    for i in ix:
        c = on.C[:, i]
        assert (c > 0).mean() > 0.5 and len(np.unique(c[c > 0])) >= 3 and on.readings[i]['research_only'] and on.readings[i]['zones']
    pl = hm.pair_list(on)
    assert np.isin(pl[:, 1:3], ix).any(axis=1).sum() > 4 * (len(on.readings) - 10) and set(map(tuple, pl[:, 1:3].tolist())) >= {(min(ix[0], ix[1]), max(ix[0], ix[1]))} | set()
    _light(monkeypatch)
    out = str(tmp_path / 'on')
    mt = hm.run_series('BTC', world['P']['BTC'], out, ctx=on, learn=False, procs=1, log=quiet)
    meta = json.load(open(os.path.join(out, 'meta.json')))
    assert mt['pairs']['pairs'] == 240 and meta['pairs']['pairs'] == 240
    ro = [r for r in meta['readings'] if r.get('research_only')]
    assert [r['name'] for r in ro] == FIVE and {r['family'] for r in ro} == {'cvdp', 'liqmap'} and all(r['levels'] == heat.ZONES for r in ro)
    assert not any(r.get('research_only') for r in meta['readings'] if r['name'] not in FIVE)
    ob = meta['outside']
    assert ob['research_only'] is True and ob['readings'] == FIVE and ob['skipped'] == {} and ob['refused'] == {} and ob['twin'] is False
    assert set(ob['edges']) == set(FIVE) and all(len(e) == 4 for e in ob['edges'].values())
    assert not set(FIVE) & set(meta['edges_new']) and not set(FIVE) & set(meta['norms'])
    assert {'cvdp', 'liqmap'} <= set(meta['families'])
    assert ob['constants']['cluster_share_of_oi'] == 0.02 and ob['constants']['leverage'] == [10, 25, 50, 100] and 'research only' in ob['live']
    assert ob['model']['snapshots'] > 1000 and ob['near_duplicates'] and ob['direction_coupling'] and ob['reading_share']
    sj = json.load(open(os.path.join(out, 'summary_counts.json')))
    assert {'fam:cvdp|cvdp', 'fam:cvdp|liqmap', 'fam:liqmap|liqmap'} <= set(sj['pair']['strata'])
    c, st = np.array(sj['pair']['c']), sj['pair']['strata']
    mine = [k for k, x in enumerate(st) if x.startswith('fam:') and ('cvdp' in x or 'liqmap' in x)]
    cols = [sj['pair']['counts'].index(k) for k in ('cells', 'under_floor')]
    assert c[:, mine][:, :, cols].sum() > 0                                                  # pair cells of the two new families were scanned and counted
    from oracle import heat_hm2_learn as hl
    fs = hl.feature_set(on, 'ALL')
    f5 = [F for F in fs['feats'] if F['name'] in FIVE]
    assert len(f5) == 5 and {F['family'] for F in f5} == {'cvdp', 'liqmap'} and {F['group'] for F in f5} == {'cvdp', 'liqmap'}
    assert not any(hl.is_ta(F['R']) for F in f5) and not [F for F in hl.feature_set(on, 'TA')['feats'] if F['name'].endswith(tuple(FIVE))]
    assert {'ZS:' + n for n in FIVE} <= set(fs['names'])


def test_part_job_and_twin_job_through_the_command_line(world, monkeypatch, tmp_path, capsys):
    """The workflow's command: `coin ... --outside` as a --part 0/2 job and as twin 1: every job of a series builds the same five readings with
    the same edges (the part job's meta equals the single job's), the twin's five are zoned on its own A rows with the real coin's skips."""
    on = world['on']
    _light(monkeypatch)
    monkeypatch.setattr(hm, '_learner', lambda *a, **k: (_ for _ in ()).throw(AssertionError('no learner')))
    ref = str(tmp_path / 'single')
    hm.run_series('BTC', world['P']['BTC'], ref, ctx=on, learn=False, procs=1, log=quiet)
    part = str(tmp_path / 'part0')
    hm.main(['coin', *world['cli'], '--outside', '--part', '0/2', '--out', part])
    capsys.readouterr()
    m_ref, m_part = json.load(open(os.path.join(ref, 'meta.json'))), json.load(open(os.path.join(part, 'meta.json')))
    assert m_part['part'] == [0, 2] and m_part['outside']['readings'] == FIVE and m_part['outside']['edges'] == m_ref['outside']['edges']
    assert [r['name'] for r in m_part['readings']] == [r['name'] for r in m_ref['readings']] and m_part['readings'] == m_ref['readings']
    assert m_part['edges_new'] == m_ref['edges_new'] and m_part['families'] == m_ref['families']
    twin = str(tmp_path / 'twin1')
    hm.main(['coin', *world['cli'], '--outside', '--twin', '1', '--out', twin])
    capsys.readouterr()
    m_tw = json.load(open(os.path.join(twin, 'meta.json')))
    assert m_tw['twin'] == 1 and m_tw['outside']['twin'] is True and m_tw['outside']['readings'] == FIVE and m_tw['outside']['skipped'] == {}
    assert m_tw['outside']['edges'] != m_ref['outside']['edges']                                   # its own A rows, its own flipped path
    assert [r['name'] for r in m_tw['readings'] if r.get('research_only')] == FIVE
    off = str(tmp_path / 'part0_off')
    hm.main(['coin', *world['cli'], '--part', '0/2', '--out', off])
    capsys.readouterr()
    assert 'outside' not in json.load(open(os.path.join(off, 'meta.json')))


def test_the_hook_gets_the_raw_oi_rows_and_the_twin_seed(world, monkeypatch, tmp_path):
    """heat_hm2._extra_readings hands the hook the RAW open-interest rows (every duplicate of a stamp: clean_oi picks) and, on a twin, the seed and
    the real perp; HM2's own readings keep load_extra's deduplicated frame."""
    P = world['P']
    raw = pd.read_csv(P['oi'])
    dup = pd.concat([raw, raw.sample(30, random_state=1).assign(oi_usd=lambda d: d.oi_usd * 1.1)]).sort_values('ts', kind='stable')
    f = str(tmp_path / 'oi_dup.csv')
    dup.to_csv(f, index=False)
    got = []

    def spy(m, perp, oi, a_hi, z, log=print, info=None, **k):
        got.append({'oi': oi, 'seed': k.get('seed'), 'real': k.get('real'), 'perp': perp, 'perp_frame': k.get('perp_frame')})
        info.update(readings=[], skipped={}, refused={}, twin=bool(k.get('seed')))
        return []
    monkeypatch.setattr(xo, 'hm2_outside_readings', spy)
    kw = dict(world['kw'], oi_csv=f)
    hm.base('BTC', P['BTC'], outside=True, **kw)
    hm.base('BTC', P['BTC'], outside=True, twin=2, **kw)
    real, tw = got
    assert len(real['oi']) == len(dup) and len(xd.load_extra(f, 'oi')) < len(dup) and real['seed'] is None
    assert len(tw['oi']) == len(dup) and tw['seed'] == 2
    assert tw['real']['perp'] is not tw['perp'] and tw['real']['m']['n'] == real['real']['m']['n']          # the real perp rides along for the twin rule
    assert real['perp_frame'] is not None and 'tb' in real['perp_frame'].columns


def test_an_input_the_hook_refuses_stops_the_job(world, tmp_path):
    """--outside asks for the five readings, so a refused input (no tb column; no oi_usd) stops the job with the reason instead of finishing green
    with no or three readings; the same files without --outside run (the flag off never looks)."""
    P = world['P']
    no_tb = str(tmp_path / 'perp_no_tb.csv')
    pd.read_csv(P['perp']).drop(columns='tb').to_csv(no_tb, index=False)
    with pytest.raises(SystemExit, match='refused an input.*taker-buy'):
        hm.base('BTC', P['BTC'], outside=True, **dict(world['kw'], perp_csv=no_tb))
    no_usd = str(tmp_path / 'oi_no_usd.csv')
    pd.read_csv(P['oi']).drop(columns='oi_usd').to_csv(no_usd, index=False)
    with pytest.raises(SystemExit, match='refused an input.*oi_usd is missing'):
        hm.base('BTC', P['BTC'], outside=True, **dict(world['kw'], oi_csv=no_usd))


# ------------------------------------------------------------------------------------------------- (g) pack and live
def _lists_frame(rows):
    cols = {'twin': 0, 'h': 15, 'coin': 'BTC', 'kind': 'pair', 'slice': 'all', 'measure': 'oheat', 'dir': 1, 'hot_A': False, 'rep_B': False, 'q': 0.5,
            'bhy': False, 'remeasured': True, 'learner_path': False, 'seen_in_league': 'none', 'families': 'cvdp|osc', 'rank': 1, 'list': 'all:oheat',
            'source': 'x', 'parts_hot': 0, 'iota_with_call': False, 'd_iota': 0, 'aliases': []}
    return pd.DataFrame([{**cols, **r} for r in rows])


def _metas(ro=True):
    rd = [{'name': 'CVDP:Div15', 'family': 'cvdp', 'k': 1, 'levels': heat.ZONES, 'aliases': [], **({'research_only': True} if ro else {})},
          {'name': '15m:RSI14', 'family': 'osc', 'k': 15, 'levels': heat.ZONES, 'aliases': []},
          {'name': 'LIQMAP:Skew', 'family': 'liqmap', 'k': 1, 'levels': heat.ZONES, 'aliases': ['X:alias'], **({'research_only': True} if ro else {})}]
    tree = lambda used: {'file': 'trees/x.json', 'sha256': 'abc', 'used': used}
    return {'BTC': {'asset': 'BTC', 'twin': 0, 'table_sha256': 'sha', 'readings': rd, 'price_step': 0.01,
                    'learner': {'trees': {'ALL_h15': tree(['ZS:LIQMAP:Skew', '15m:RSI14']), 'TA_h15': tree(['15m:RSI14', 'ZS:15m:RSI14'])}}}}


def test_the_pack_and_the_live_meta_leave_research_only_readings_out():
    """No pack row for a bot may hold a reading that has no live computation: a pair row with an OR-XD reading in its conds (or merged into
    it as an alias) and the GBM zone rows of a model whose trees use one are left out of hm2_pack.json (counted in `research_only`), its
    tree is not listed under `models`, and hm2_live_meta.json names none of them. With no flagged reading the pack has no such key."""
    from oracle import heat_hm2_league as L
    cj = lambda *c: json.dumps([[n, [lv]] for n, lv in c])
    lists = _lists_frame([
        {'key': 'CVDP:Div15=very low & 15m:RSI14=low', 'conds': cj(('CVDP:Div15', 'very low'), ('15m:RSI14', 'low'))},
        {'key': 'X:alias=high & 15m:RSI14=low', 'conds': cj(('X:alias', 'high'), ('15m:RSI14', 'low')), 'measure': 'iheat', 'list': 'all:iheat'},
        {'key': '15m:RSI14=low & 1m:R3=high', 'conds': cj(('15m:RSI14', 'low'), ('1m:R3', 'high')),
         'aliases': ['CVDP:Div15=very low & 1m:R3=high', '15m:RSI14=low & X:alias=high', '15m:RSI14=low & 1m:R3=very high']},
        {'key': 'LIQMAP:Skew=very low & 1m:R3=high', 'conds': cj(('LIQMAP:Skew', 'very low'), ('1m:R3', 'high')), 'measure': 'lheat', 'list': 'all:lheat'}])
    mrow = lambda mdl: {'twin': 0, 'h': 15, 'coin': 'BTC', 'asset': 'BTC', 'model': mdl, 'key': f'GBM.{mdl}15=very high', 'conds': cj((f'GBM.{mdl}15', 'very high')), 'dir': 1}
    model = pd.DataFrame([mrow('ALL'), mrow('TA')])
    summary = {'chance': {}, 'model': {}, 'warnings': [], 'stamp': 'test'}
    pk = L.build_pack(lists, summary, _metas(), model)
    keys = [r['key'] for r in pk['rows']]
    assert keys == ['15m:RSI14=low & 1m:R3=high', 'GBM.TA15=very high'], keys
    assert pk['research_only']['rows_left_out'] == 3 and pk['research_only']['models_left_out'] == ['BTC:ALL:15']
    assert pk['research_only']['readings'] == ['CVDP:Div15', 'LIQMAP:Skew', 'X:alias']
    assert 'no live computation' in pk['research_only']['why']
    assert pk['rows'][0]['aliases'] == ['15m:RSI14=low & 1m:R3=very high']              # the alias strings that name a research-only reading (or its alias) are dropped
    assert set(pk['models']['BTC']) == {'TA'} and L.pack_summary(pk)['research_only_rows_left_out'] == 3
    lm = L.live_meta(pk, _metas(), {}, None)
    txt = json.dumps(lm)
    assert 'CVDP' not in txt and 'LIQMAP' not in txt and 'X:alias' not in txt
    assert lm['coins']['BTC']['readings'] == ['15m:RSI14', '1m:R3', 'GBM.TA15'] and 'CVDP:Div15' not in lm['coins']['BTC']['no_edges']
    # defence in depth: a pack that does carry such an alias or reading (an older pack, a hand edit) still gives a live meta without it
    dirty = {'rows': [{'coin': 'BTC', 'kind': 'pair', 'readings': ['15m:RSI14', '1m:R3', 'LIQMAP:Skew'],
                       'aliases': ['CVDP:Div15=very low & 1m:R3=high', '15m:RSI14=low & X:alias=high']}]}
    lm2 = L.live_meta(dirty, _metas(), {}, None)
    assert lm2['coins']['BTC']['readings'] == ['15m:RSI14', '1m:R3'] and 'CVDP' not in json.dumps(lm2) and 'LIQMAP' not in json.dumps(lm2)
    clean = L.build_pack(lists, summary, _metas(ro=False), model)
    assert 'research_only' not in clean and len(clean['rows']) == 6 and set(clean['models']['BTC']) == {'ALL', 'TA'}
    assert 'research_only_rows_left_out' not in L.pack_summary(clean)


def test_a_research_only_reading_is_never_live_ready():
    """Defence in depth for a pack that does hold such a row: the readings' families need feeds the bot does not have (perp taker flow, open-interest
    history), the parity never checks them, and heat_xdata.levels_at returns no level for them."""
    from oracle import heat_hm2_league as L
    assert L.needed_feeds(['CVDP:Div15']) == {'spot', 'perp taker flow'} and L.needed_feeds(['LIQMAP:Skew', '15m:RSI14']) == {'spot', 'open interest history'}
    row = {'coin': 'BTC', 'kind': 'pair', 'readings': ['CVDP:Div15', '15m:RSI14'], 'live_ready': False}
    par = {'table_sha256': 'sha', 'readings': {}, 'engine': {'15m:RSI14': {'agreement': 1.0}}, 'gbm': {}}
    pk = L.set_live_ready({'table_sha256': {'BTC': 'sha'}, 'rows': [row]}, {'BTC': par}, feeds=('spot', 'other coins', 'binance perp', 'dominance'))
    r = pk['rows'][0]
    assert r['live_ready'] is False and any('CVDP:Div15: not checked' in w for w in r['live_ready_why']) and any('no perp taker flow feed' in w for w in r['live_ready_why'])
    assert hm.family_of({'name': 'CVDP:Div15'}) == 'cvdp' and hm.family_of({'name': 'LIQMAP:Skew'}) == 'liqmap'
    assert hm.research_only_names(_metas()['BTC']) == {'CVDP:Div15', 'LIQMAP:Skew', 'X:alias'} and hm.research_only_names(_metas(ro=False)['BTC']) == set()
    win = _grid(_frames(3, days=4)[1], 4 * 1440)
    out = xd.levels_at(win, {'edges': {}, 'norms': {}}, names=FIVE)
    assert out == {n: None for n in FIVE}


def test_part_4_chart_pairs_never_pair_a_research_only_reading():
    """heat_patterns.chart_pairs pairs each chart reading with every HM2 reading, but not with a research-only one (a --outside series runs Part 4 on
    the same context): the pair list is the plain one with those rows taken out, and with none flagged it is exactly what it always was."""
    from types import SimpleNamespace
    pat = pytest.importorskip('oracle.heat_patterns')
    hm_readings = [{'name': f'r{i}', 'base': f'b{i}'} for i in range(6)]
    comp = [{'name': 'c0', 'base': 'chart0'}, {'name': 'c1', 'base': 'chart1'}]
    plain = SimpleNamespace(n0=6, readings=hm_readings + comp)
    flagged = SimpleNamespace(n0=6, readings=[dict(R, research_only=True) if i in (2, 5) else R for i, R in enumerate(hm_readings)] + comp)
    a, b = pat.chart_pairs(plain), pat.chart_pairs(flagged)
    assert len(a) == 2 * 6 + 1 and len(b) == 2 * 4 + 1
    assert not (set(b[:, 1]) | set(b[:, 2])) & {2, 5} and set(map(tuple, b[:, 1:].tolist())) == {(i, c) for i in (0, 1, 3, 4) for c in (6, 7)} | {(6, 7)}
    assert set(map(tuple, a[:, 1:].tolist())) == {(i, c) for i in range(6) for c in (6, 7)} | {(6, 7)}


# ----------------------------------------------------------------------------------------------- (h) the workflow tag
WF = os.path.join(ROOT, '.github', 'workflows', 'oracle-hm2.yml')


def _plan(msg, tmp_path):
    yaml = pytest.importorskip('yaml')
    if not os.path.exists(WF) or not shutil.which('jq') or not shutil.which('bash'):
        pytest.skip('the workflow, bash or jq is not here')
    wf = yaml.safe_load(open(WF))
    step = next(s for s in wf['jobs']['test']['steps'] if s.get('id') == 'plan')
    (tmp_path / 'bin').mkdir(exist_ok=True)
    gh = tmp_path / 'bin' / 'gh'
    gh.write_text('#!/bin/sh\nexit 0\n')
    gh.chmod(0o755)
    outf = tmp_path / 'out.txt'
    outf.write_text('')
    wfenv = {k: str(v) for k, v in {**(wf.get('env') or {}), **(wf['jobs']['test'].get('env') or {}), **(step.get('env') or {})}.items() if '${{' not in str(v)}
    env = {**os.environ, **wfenv, 'MSG': msg, 'GH_TOKEN': 'x', 'GITHUB_OUTPUT': str(outf), 'GITHUB_RUN_ID': '1', 'GITHUB_REPOSITORY': 'o/r',
           'PATH': f'{tmp_path / "bin"}:{os.environ["PATH"]}'}
    r = subprocess.run(['bash', '-c', step['run']], cwd=ROOT, env=env, capture_output=True, text=True)
    out = dict(l.split('=', 1) for l in outf.read_text().splitlines() if '=' in l)
    return r, out, wf


def test_the_workflow_tag_adds_outside_and_nothing_else(tmp_path):
    base_msg = 'x [heat-hm2:43030435253] [heat-hm2-parts:3]'
    r0, o0, wf = _plan(base_msg, tmp_path)
    assert r0.returncode == 0, r0.stderr[-800:]
    r1, o1, _ = _plan(base_msg + ' [hm2-outside]', tmp_path)
    assert r1.returncode == 0, r1.stderr[-800:]
    assert o0['outside'] == 'false' and o1['outside'] == 'true'
    # the job graph, the matrices and the defaults are the same; the Drive folder of an outside study is its own (never a plain run's)
    assert {k: v for k, v in o0.items() if k not in ('outside', 'drive')} == {k: v for k, v in o1.items() if k not in ('outside', 'drive')}
    assert o0['drive'] == 'models/oracle-heat/runs/43030435253/hm2' and o1['drive'] == 'models/oracle-heat/runs/43030435253/hm2-outside'
    assert o1['study'] == 'true' and o1['parts'] == '3' and 'outside true' in r1.stdout
    r2, o2, _ = _plan('no tag at all', tmp_path)
    assert r2.returncode == 0 and o2['outside'] == 'false' and o2['minutes'] == 'false'
    r3, o3, _ = _plan('[hm2-outside] alone', tmp_path)
    assert o3['outside'] == 'true' and o3['minutes'] == 'false' and 'acts only with' in r3.stdout + r3.stderr
    r4, o4, _ = _plan('[heat-hm2-league:43030435253] [hm2-outside]', tmp_path)                    # a league-only push of an outside study reads its folder
    assert r4.returncode == 0 and o4['league'] == 'true' and o4['drive'].endswith('/hm2-outside') and 'acts only with' not in r4.stdout + r4.stderr
    for tag in ('[heat-hm2-parity:43030435253]', '[heat-hm2-drill:43030435253]', '[heat-hm2-drill-bench:43030435253]', '[heat-hm2-drill-league:43030435253]',
                '[heat-hm2-drill-parity:43030435253]'):
        r5, _, _ = _plan(f'{tag} [hm2-outside]', tmp_path)
        assert r5.returncode != 0 and 'not combined' in r5.stdout + r5.stderr, tag
    jobs = wf['jobs']
    for j in ('bench', 'series', 'finish'):
        assert jobs[j]['env']['OUTSIDE'] == '${{ needs.test.outputs.outside }}'
        text = '\n'.join(s.get('run', '') for s in jobs[j]['steps'])
        assert 'X+=(--outside)' in text and '$OUTSIDE" = true' in text
    assert len([j for j in jobs]) == 14 and jobs['series']['strategy']['max-parallel'] == 9
    assert all('OUTSIDE' not in (jobs[j].get('env') or {}) for j in jobs if j not in ('bench', 'series', 'finish', 'league'))
    assert 'oracle/tests/test_heat_outside_hm2*.py' in '\n'.join(s.get('run', '') for s in jobs['test']['steps'])
    p4 = next(s for s in jobs['bench']['steps'] if 'Part 4 bench' in s.get('name', ''))
    assert '--outside' not in p4['run']                                          # chart pairs never pair a research-only reading, so the sizing is the same
    paths = wf[True]['push']['paths'] if True in wf else wf['on']['push']['paths']
    assert 'python/oracle/heat_outside.py' in paths and 'python/oracle/tests/test_heat_outside_hm2*.py' in paths
    pip = next(s for s in jobs['test']['steps'] if 'pip install' in s.get('run', ''))['run']
    assert 'pyyaml' in pip                                                       # this test reads the plan step with it


def _commit_step(tmp_path, name, outside_meta, env_outside):
    """Runs the league job's commit step on a fake checkout (git stubbed): returns the tree afterwards."""
    yaml = pytest.importorskip('yaml')
    if not shutil.which('jq') or not shutil.which('bash'):
        pytest.skip('bash or jq is not here')
    wf = yaml.safe_load(open(WF))
    step = next(s for s in wf['jobs']['league']['steps'] if s.get('name', '').startswith('Commit the small league files'))
    d = tmp_path / name
    for sub in ('bin', 'data/hm2/BTC', 'data/hm2/BTC-twin1', 'out/league', 'out/logs', 'research/oracle_heat/latest', 'research/oracle_heat/hm2'):
        (d / sub).mkdir(parents=True)
    for f in ('BTC', 'BTC-twin1'):
        (d / 'data/hm2' / f / 'meta.json').write_text(json.dumps({'label': f, **({'outside': {'research_only': True}} if outside_meta else {})}))
    for f in ('hm2_pack.json', 'hm2_live_meta.json'):
        (d / 'out/league' / f).write_text(json.dumps({'new': True}))
        (d / 'research/oracle_heat/latest' / f).write_text(json.dumps({'plain': True}))
    (d / 'out/league/league.md').write_text('league')
    git = d / 'bin' / 'git'
    git.write_text('#!/bin/sh\necho "$@" >> "$GITLOG"\n[ "$1" != diff ] || exit 1\nexit 0\n')              # `git diff --cached --quiet` fails: something is staged
    git.chmod(0o755)
    env = {**os.environ, 'RUN': '77', 'BR': 'b', 'PATTERNS': 'false', 'OUTSIDE': 'true' if env_outside else 'false', 'GITHUB_SHA': 'abc', 'GITHUB_RUN_ID': '9',
           'GITLOG': str(d / 'git.log'), 'PATH': f'{d / "bin"}:{os.environ["PATH"]}'}
    r = subprocess.run(['bash', '-c', step['run']], cwd=d, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-800:] + r.stdout[-800:]
    return d, r


def test_the_league_commit_keeps_an_outside_study_away_from_the_plain_handoff(tmp_path):
    """Found from the DATA, so a league-only push without the tag is caught as well: a series meta.json with an `outside` block moves the whole
    commit under research/oracle_heat/hm2/outside/ and leaves latest/ (what the bot and the drill read) as it was; a plain study commits as before."""
    plain = lambda d, f: json.loads((d / 'research/oracle_heat/latest' / f).read_text())
    d, r = _commit_step(tmp_path, 'plain', outside_meta=False, env_outside=False)
    assert plain(d, 'hm2_pack.json') == {'new': True} and (d / 'research/oracle_heat/hm2/league.md').exists()
    assert not (d / 'research/oracle_heat/hm2/outside').exists() and 'an --outside study' not in r.stdout
    commit = [l for l in (d / 'git.log').read_text().splitlines() if l.startswith('commit')]
    assert len(commit) == 1 and 'league, lessons and hm2_pack.json of run 77' in commit[0]
    for name, meta, env in (('data_only', True, False), ('tag_only', False, True), ('both', True, True)):
        d, r = _commit_step(tmp_path, name, outside_meta=meta, env_outside=env)
        assert plain(d, 'hm2_pack.json') == {'plain': True} and plain(d, 'hm2_live_meta.json') == {'plain': True}, name
        o = d / 'research/oracle_heat/hm2/outside'
        assert json.loads((o / 'hm2_pack.json').read_text()) == {'new': True} and json.loads((o / 'hm2_live_meta.json').read_text()) == {'new': True}, name
        assert (o / 'league.md').exists() and (o / 'RUN').exists() and not (d / 'research/oracle_heat/hm2/league.md').exists(), name
        assert 'an --outside study' in r.stdout
        commit = [l for l in (d / 'git.log').read_text().splitlines() if l.startswith('commit')]
        assert len(commit) == 1 and '--outside study (research only, not latest/)' in commit[0], commit
        adds = [l for l in (d / 'git.log').read_text().splitlines() if l.startswith('add')]
        assert adds and all('latest' not in l or 'outside' in l for l in adds), adds
