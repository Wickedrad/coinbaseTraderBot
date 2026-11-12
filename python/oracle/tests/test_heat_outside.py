"""OR-XD lite (python/oracle/heat_outside.py, python/oracle/prereg/OR-XD.md): the CVDP formulas against brute force, causality
of every league reading (cut the future), the OI known-time rule, the liquidation-map model on planted cases, the twin
rule, split-A-only zone edges, the file refusals and an end-to-end run of the engine with heat.league on its output.
All data here is synthetic."""
import json
import os
import time

import numpy as np
import pandas as pd
import pytest

from oracle import heat, heat_outside as xd
from oracle.common import DAY, MIN, ms

pytest.importorskip('talib')


# ------------------------------------------------------------------------------------------------ synthetic data
def synth_frames(start: int, days: int, seed: int = 0, level: float = 3000.0):
    """Spot and perp 1-minute frames (ts,o,h,l,c,v,tb) and 5-minute OI (ts,oi,oi_usd) on a plain random walk."""
    rng = np.random.default_rng(seed)
    n = days * 1440
    ts = start + np.arange(n, dtype=np.int64) * MIN
    c = np.round(level * np.exp(np.cumsum(rng.normal(0, 6e-4, n))), 2)
    o = np.r_[c[0], c[:-1]]
    h = np.ceil(np.maximum(o, c) * (1 + np.abs(rng.normal(0, 2e-4, n))) * 100) / 100
    l = np.floor(np.minimum(o, c) * (1 - np.abs(rng.normal(0, 2e-4, n))) * 100) / 100
    vol = rng.uniform(50, 150, n) * np.exp(rng.normal(0, 0.3, n))
    spot = pd.DataFrame({'ts': ts, 'o': o, 'h': h, 'l': l, 'c': c, 'v': vol, 'tb': vol * rng.uniform(0.3, 0.7, n)})
    k = 1 + 4e-4 * np.sin(np.arange(n) / 700) + rng.normal(0, 5e-5, n)
    vp = vol * rng.uniform(2, 4, n)
    perp = pd.DataFrame({'ts': ts, 'o': np.round(o * k, 2), 'h': np.ceil(h * k * 100) / 100, 'l': np.floor(l * k * 100) / 100,
                         'c': np.round(c * k, 2), 'v': vp, 'tb': vp * rng.uniform(0.3, 0.7, n)})
    m5 = n // 5
    contracts = 1e9 / level * np.exp(np.cumsum(rng.normal(2e-4, 3e-3, m5)))
    # oi_usd = contracts x the perp open at ts (the implied price follows the perp, as in Binance's metrics file)
    oi = pd.DataFrame({'ts': start + np.arange(m5, dtype=np.int64) * 5 * MIN, 'oi': contracts, 'oi_usd': contracts * perp['o'].to_numpy()[::5][:m5]})
    return spot, perp, oi


def write(d, spot, perp, oi, tag=''):
    paths = {}
    for nm, df in (('spot', spot), ('perp', perp), ('oi', oi)):
        p = os.path.join(str(d), f'{nm}{tag}.csv')
        df.to_csv(p, index=False)
        paths[nm] = p
    return paths


def inputs(d, spot, perp, oi, tag=''):
    """(sp, pp, oi) as the runner builds them."""
    p = write(d, spot, perp, oi, tag)
    sp = heat.load_minutes(p['spot'], end=int(spot['ts'].iloc[-1]) + MIN)
    pp = xd.perp_on_grid(sp, pd.read_csv(p['perp']))
    return sp, pp, xd.clean_oi(pd.read_csv(p['oi']), pp)[0]


def noise_after(spot, perp, oi, t0, t, seed=99):
    """The same frames with every input after minute row t (its close is known) replaced by random noise: prices jump by
    up to a few % per row around the old level, volumes and taker volumes are redrawn, OI snapshots whose known time is
    after the close of row t are redrawn."""
    rng = np.random.default_rng(seed)
    close_t = t0 + (t + 1) * MIN
    out = []
    for df in (spot, perp):
        d = df.copy()
        m = (d['ts'] > t0 + t * MIN).to_numpy()
        k = int(m.sum())
        c = d['c'].to_numpy().copy()
        c[m] = c[m] * np.exp(rng.normal(0, 0.03, k))
        o = np.r_[c[0], c[:-1]]
        d['c'] = c
        d['o'] = np.where(m, o, d['o'])
        d['h'] = np.where(m, np.maximum(d['o'], c) * (1 + np.abs(rng.normal(0, 3e-3, len(d)))), d['h'])
        d['l'] = np.where(m, np.minimum(d['o'], c) * (1 - np.abs(rng.normal(0, 3e-3, len(d)))), d['l'])
        v = rng.uniform(1, 500, len(d))
        d['v'] = np.where(m, v, d['v'])
        d['tb'] = np.where(m, v * rng.uniform(0, 1, len(d)), d['tb'])
        out.append(d)
    q = oi.copy()
    m = (q['ts'] + xd.KNOWN > close_t).to_numpy()
    q.loc[m, 'oi'] = 1e9 / 3000 * np.exp(rng.normal(0, 0.5, int(m.sum())))
    q.loc[m, 'oi_usd'] = q.loc[m, 'oi'] * 3000
    return out[0], out[1], q


START = ms('2024-11-01')
DAYS = 40
# On random-walk test data a bucket of 0.1% rarely reaches the frozen 2% of OI, so the tests that need clusters on synthetic
# data lower the share (the planted tests below use the frozen constant).
TEST_SHARE = 0.006


@pytest.fixture
def lowshare(monkeypatch):
    monkeypatch.setattr(xd, 'CLUSTER_SHARE', TEST_SHARE)
    monkeypatch.setattr(xd, 'MIN_A_DAYS', 10)               # the module-scoped fixture's A is 25 days


@pytest.fixture(scope='module')
def base(tmp_path_factory):
    d = tmp_path_factory.mktemp('xd')
    spot, perp, oi = synth_frames(START, DAYS, seed=5)
    sp, pp, o = inputs(d, spot, perp, oi)
    a_hi = 25 * 1440
    mp = pytest.MonkeyPatch()
    mp.setattr(xd, 'CLUSTER_SHARE', TEST_SHARE)
    mp.setattr(xd, 'MIN_A_DAYS', 10)
    try:
        res = xd.xd_readings(sp, pp, o, a_hi, keep=True)
    finally:
        mp.undo()
    return {'dir': d, 'frames': (spot, perp, oi), 'sp': sp, 'pp': pp, 'oi': o, 'a_hi': a_hi, 'res': res}


# ------------------------------------------------------------------------------------------------ (a) the formulas
def _arrays(n, seed=1):
    rng = np.random.default_rng(seed)
    t0 = START
    mk = lambda lvl: {'t0': t0, 'n': n, 'gap': np.zeros(n, bool), 'c': lvl * np.exp(np.cumsum(rng.normal(0, 1e-3, n))),
                      'v': rng.uniform(1, 3, n), 'tick': np.zeros(n)}
    sp, pp = mk(100.0), mk(101.0)
    for x in (sp, pp):
        x['tb'] = x['v'] * rng.uniform(0.2, 0.8, n)
        x['o'] = x['h'] = x['l'] = x['c']
    return sp, pp


def test_cvdp_formulas_by_hand():
    sp, pp = _arrays(3200)
    oi = pd.DataFrame({'ts': [START, START + 5 * MIN], 'oi': [1e4, 1.01e4], 'oi_usd': [1e6, 1.01e6]})
    X = xd.xd_values(sp, pp, oi)['values']
    # a tiny hand case: constant volume 2, perp taker buy 1.5 (net share +0.5), spot taker buy 0.5 (net share -0.5)
    s2, p2 = _arrays(40)
    s2['v'][:], p2['v'][:], s2['tb'][:], p2['tb'][:] = 2.0, 2.0, 0.5, 1.5
    V = xd.xd_values(s2, p2, oi)['values']
    assert np.isnan(V['CVDP:Div15'][13])                             # fewer than 15 minutes
    np.testing.assert_allclose(V['CVDP:Div15'][14:], 1.0)            # 0.5 - (-0.5)
    np.testing.assert_allclose(V['CVDP:15'][14:], 0.5)
    np.testing.assert_allclose(V['REF:FlowTB15'][14:], 0.25)
    # brute force on random data, rows with a full history
    for i in (1500, 2222, 3199):
        w = slice(i - 14, i + 1)
        ns = lambda x: (2 * x['tb'][w] - x['v'][w]).sum() / x['v'][w].sum()
        assert abs(X['CVDP:Div15'][i] - (ns(pp) - ns(sp))) < 1e-12
        assert abs(X['CVDP:15'][i] - ns(pp)) < 1e-12
        assert abs(X['REF:FlowTB15'][i] - sp['tb'][w].sum() / sp['v'][w].sum()) < 1e-12
        flow = 2 * pp['tb'] - pp['v']
        net60 = np.array([flow[j - 59:j + 1].sum() for j in range(i - 1440, i)])        # rolling-60 net at i-1440 .. i-1
        z = flow[i - 59:i + 1].sum() / net60.std(ddof=1)
        r60 = np.log(pp['c'][i] / pp['c'][i - 60]) * 1e4
        want = z if (np.sign(z) != np.sign(r60) and abs(r60) > 0) else 0.0
        assert abs(X['CVDP:PxDiv60'][i] - want) < 1e-9, i
    # the three branches are all seen: taker buying while price fell (+), selling while it rose (-), agreement (0)
    x = X['CVDP:PxDiv60']
    assert (x > 0).any() and (x < 0).any() and (x == 0).any()


def test_pxdiv60_dead_band_and_sign():
    sp, pp = _arrays(1600, seed=3)
    pp['c'][:] = 100.0                                               # flat price: |r60| = 0 is not above any band
    pp['o'] = pp['h'] = pp['l'] = pp['c']
    oi = pd.DataFrame({'ts': [START, START + 5 * MIN], 'oi': [1e4, 1.01e4], 'oi_usd': [1e6, 1.01e6]})
    x = xd.xd_values(sp, pp, oi)['values']['CVDP:PxDiv60']
    assert (x[~np.isnan(x)] == 0).all() and np.isfinite(x[1600 - 1])
    sp['tick'][:] = 1e9                                              # a huge price step: every 60-minute move is inside the band
    pp['c'] = 100 * np.exp(np.cumsum(np.full(1600, -5e-3)))          # price falls fast
    pp['o'] = pp['h'] = pp['l'] = pp['c']
    pp['tb'] = pp['v'] * 0.9                                          # taker buying
    pp['tb'][:300] = pp['v'][:300] * 0.1
    x = xd.xd_values(sp, pp, oi)['values']['CVDP:PxDiv60']
    assert (x[~np.isnan(x)] == 0).all()
    sp['tick'][:] = 0.0                                              # now the move counts: buying while falling = positive
    x = xd.xd_values(sp, pp, oi)['values']['CVDP:PxDiv60']
    assert x[1599] > 0


def test_gap_makes_every_reading_nan_for_its_window(base, lowshare):
    spot, perp, oi = base['frames']
    perp = perp.drop(index=[30000, 30001])                          # two missing perp minutes
    sp, pp, o = inputs(base['dir'], spot, perp, oi, 'gap')
    res = xd.xd_readings(sp, pp, o, base['a_hi'], edges=base['res']['edges'], keep=True)
    v = res['values']
    assert pp['gap'][30000] and pp['gap'][30001] and pp['gap'].sum() == 2
    for nm, W in (('CVDP:Div15', 15), ('CVDP:15', 15), ('REF:FlowTB15', 15), ('CVDP:PxDiv60', 60), ('LIQMAP:DistAbove', 60), ('LIQMAP:DistBelow', 60), ('LIQMAP:Skew', 60)):
        assert np.isnan(v[nm][30000:30002 + W + heat.STALE - 1]).all(), nm
        assert np.isfinite(v[nm][30002 + W + heat.STALE + 5:30002 + W + heat.STALE + 3000]).any() or nm.startswith('LIQMAP'), nm


# ------------------------------------------------------------------------------------ (b) cut the future, every reading
@pytest.mark.parametrize('t', [30000, 40000 + 3, 50000 + 4])
def test_cut_the_future(base, t, lowshare):
    spot, perp, oi = base['frames']
    # the rows around t: t is just before a snapshot's known time when (t + 2) % 5 == 0 (close(t) + 1 minute = T_k)
    sp0, pp0, o0 = base['sp'], base['pp'], base['oi']
    edges = base['res']['edges']
    ref = base['res']['values']
    assert set(edges) == set(xd.LEAGUE)
    s2, p2, q2 = noise_after(spot, perp, oi, sp0['t0'], t)
    sp, pp, o = inputs(base['dir'], s2, p2, q2, f'cut{t}')
    assert not np.allclose(pp['c'][t + 5:t + 500], pp0['c'][t + 5:t + 500])             # the future really is different
    res = xd.xd_readings(sp, pp, o, base['a_hi'], edges=edges, keep=True)
    codes0 = {r['name']: r['codes'] for r in base['res']['readings']}
    for r in res['readings']:
        np.testing.assert_array_equal(r['codes'][:t + 1], codes0[r['name']][:t + 1], err_msg=r['name'])
        assert r['edges'] == edges[r['name']]
    for nm in xd.LEAGUE + xd.REFS:
        np.testing.assert_allclose(res['values'][nm][:t + 1], ref[nm][:t + 1], rtol=1e-9, atol=1e-12, equal_nan=True, err_msg=nm)
    assert len(res['readings']) == 5
    # and the readings do see data up to row t: some of the five reading codes are known at the cut
    assert any((r['codes'][t - 3:t + 1] >= 0).any() for r in res['readings'])


def test_cut_just_before_and_at_a_snapshot_known_time(base, lowshare):
    """t with close(t) one minute before / exactly at T_k: the snapshot is not / is part of the state for row t."""
    spot, perp, oi = base['frames']
    sp0 = base['sp']
    k = 4000
    Tk = int(oi['ts'].iloc[k]) + xd.KNOWN
    t_at = (Tk - sp0['t0']) // MIN - 1                                # close(t_at) = T_k
    assert sp0['t0'] + (t_at + 1) * MIN == Tk
    for t in (t_at - 1, t_at):
        s2, p2, q2 = noise_after(spot, perp, oi, sp0['t0'], t, seed=7 + t)
        sp, pp, o = inputs(base['dir'], s2, p2, q2, f'edge{t}')
        res = xd.xd_readings(sp, pp, o, base['a_hi'], edges=base['res']['edges'], keep=True)
        for nm in xd.LEAGUE:
            np.testing.assert_allclose(res['values'][nm][:t + 1], base['res']['values'][nm][:t + 1], rtol=1e-9, atol=1e-12, equal_nan=True, err_msg=f'{nm} {t}')


# --------------------------------------------------------------------------------------------- (c) OI known time
def test_oi_snapshot_is_used_only_from_its_known_time(base):
    sp, pp, o = base['sp'], base['pp'], base['oi']
    t0 = int(sp['t0'])
    k = 3000
    Tk = int(o['ts'].iloc[k]) + xd.KNOWN
    i_at = (Tk - t0) // MIN - 1                                       # close(i_at) == T_k: the first row that may read snapshot k
    assert t0 + (i_at + 1) * MIN == Tk
    o2 = o.copy()
    o2.loc[k, 'oi'] = o2.loc[k, 'oi'] * 1.5                           # a big jump of this one snapshot
    a = xd.LiqModel(pp, o).run()
    b = xd.LiqModel(pp, o2).run()
    same = lambda x, y: np.allclose(x, y, equal_nan=True, rtol=0, atol=0)
    for nm in ('dist_up', 'dist_dn', 'skew'):
        assert same(getattr(a, nm)[:i_at], getattr(b, nm)[:i_at]), nm        # nothing before its known time moves
    assert not same(a.skew[i_at:i_at + 5], b.skew[i_at:i_at + 5])            # at T_k it does
    # a snapshot whose ts + 5 min is one minute after the close of row i does not move row i
    i = i_at + 7
    k2 = k + 2                                                         # T = T_k + 10 min -> close(i_at + 10)
    assert int(o['ts'].iloc[k2]) + xd.KNOWN > t0 + (i + 1) * MIN
    o3 = o.copy()
    o3.loc[k2, 'oi'] = o3.loc[k2, 'oi'] * 0.5
    c = xd.LiqModel(pp, o3).run()
    assert same(a.skew[:i_at + 10], c.skew[:i_at + 10]) and same(a.dist_up[:i_at + 10], c.dist_up[:i_at + 10])
    # a state is carried for 10 minutes at most: with no snapshot for an hour the rows after 10 minutes are NaN
    assert xd.CARRY == 10 * MIN
    o4 = o.drop(index=range(3100, 3112)).reset_index(drop=True)       # a gap of 1 h 5 min after snapshot 3099
    d = xd.LiqModel(pp, o4).run()
    T = int(o['ts'].iloc[3099]) + xd.KNOWN
    r_last = (T + xd.CARRY - t0) // MIN - 1
    assert np.isfinite(d.skew[r_last]) and np.isnan(d.skew[r_last + 1]) and np.isnan(d.skew[r_last + 30])


# ---------------------------------------------------------------------------------------- (d) the planted LIQMAP model
def planted(n_days=40, k_big=100, extra=None, c_fn=None):
    t0 = ms('2024-06-01')
    n = n_days * 1440
    c = np.full(n, 100.0)
    h, l = np.full(n, 100.01), np.full(n, 99.99)
    if c_fn:
        c_fn(c, h, l)
    pp = {'t0': t0, 'n': n, 'o': c.copy(), 'h': h, 'l': l, 'c': c, 'v': np.ones(n), 'tb': np.full(n, 0.5), 'gap': np.zeros(n, bool), 'first': 0}
    K = n // 5
    usd = np.full(K, 1000.0)
    usd[k_big:] = 2000.0
    if extra:
        extra(usd)
    oi = pd.DataFrame({'ts': t0 + np.arange(K, dtype=np.int64) * 5 * MIN, 'oi': usd / 100.0, 'oi_usd': usd})     # the price stays 100
    return pp, oi


def bprice(p):
    return float(np.exp(np.floor(np.log(p) / xd.LNB + 0.5) * xd.LNB))


def test_planted_one_big_increase_makes_the_right_buckets():
    pp, oi = planted()
    seen = {}

    def hook(k, m):
        if k == 100:
            seen['long'] = m.long.copy() * m.S
            seen['short'] = m.short.copy() * m.S
            seen['S'] = m.S
    m = xd.LiqModel(pp, oi, hook=hook).run()
    for i, (L, w) in enumerate(zip(xd.LEVERAGE, xd.WEIGHTS)):
        lb = m.bidx(100 * (1 - 1 / L + xd.MAINT))
        sb = m.bidx(100 * (1 + 1 / L - xd.MAINT))
        assert abs(seen['long'][lb] - 1000 * 0.5 * w) < 1e-9, L
        assert abs(seen['short'][sb] - 1000 * 0.5 * w) < 1e-9, L
        assert abs(m.bp[lb] - bprice(100 * (1 - 1 / L + xd.MAINT))) < 1e-9
    assert abs(seen['long'].sum() - 500) < 1e-9 and abs(seen['short'].sum() - 500) < 1e-9
    # before the jump there is no cluster, after it the nearest long cluster below 100 is the 100x tier at 99.5
    r_before = (int(oi['ts'].iloc[100]) + xd.KNOWN - pp['t0']) // MIN - 3
    r_at = (int(oi['ts'].iloc[100]) + xd.KNOWN - pp['t0']) // MIN - 1
    assert np.isnan(m.dist_dn[r_before]) and np.isnan(m.dist_up[r_before])
    for r in (r_at, r_at + 7):
        assert abs(m.dist_dn[r] - (100 - bprice(99.5)) / 100 * 1e4) < 1e-6
        assert abs(m.dist_up[r] - (bprice(100.5) - 100) / 100 * 1e4) < 1e-6
    # the skew: short notional in (P, 1.02P] = tiers at 100.5 and 101.5 (50 + 100), long in [0.98P, P) = 99.5 and 98.5 (50 + 100)
    e = 0.001 * 2000
    assert abs(m.skew[r_at] - np.log((150 + e) / (150 + e))) < 1e-9


def test_planted_cluster_disappears_after_price_trades_through_it():
    t_dip, t_spike = 100 * 5 + 30, 100 * 5 + 60                        # rows (minutes after the jump snapshot)

    def shape(c, h, l):
        l[t_dip] = 98.9                                               # a low through the 99.5 bucket, not the 98.5 one
        h[t_spike] = 100.6                                            # a high through the 100.5 bucket, not the 101.5 one
    pp, oi = planted(c_fn=shape)
    m = xd.LiqModel(pp, oi).run()
    r_before = t_dip - 3
    assert abs(m.dist_dn[r_before] - (100 - bprice(99.5)) / 100 * 1e4) < 1e-6
    r_after = t_dip + 20
    assert abs(m.dist_dn[r_after] - (100 - bprice(98.5)) / 100 * 1e4) < 1e-6          # the 99.5 cluster is gone
    assert abs(m.dist_up[t_dip + 10] - (bprice(100.5) - 100) / 100 * 1e4) < 1e-6   # (the high is still ahead)
    assert abs(m.dist_up[t_spike + 20] - (bprice(101.5) - 100) / 100 * 1e4) < 1e-6    # the 100.5 cluster is gone
    assert abs(m.dist_dn[t_spike + 20] - (100 - bprice(98.5)) / 100 * 1e4) < 1e-6     # and stays gone: it is not re-created by old OI
    # a bucket that was zeroed and is filled again by a later addition is a new generation: the later one is not wiped by the old expiry


def test_planted_expiry_after_thirty_days_with_generations():
    k_big = 100

    def shape(c, h, l):
        l[100 * 5 + 30] = 98.9                                         # zero the 99.5 bucket (a new generation)
    pp, oi = planted(n_days=36, k_big=k_big, c_fn=shape)
    tot = {}

    def hook(k, m):
        tot[k] = (float((m.long * m.S).sum()), float((m.short * m.S).sum()), m.S)
    m = xd.LiqModel(pp, oi, hook=hook).run()
    k30 = k_big + 8640
    assert tot[k30 - 1][0] > 340 and tot[k30 - 1][1] > 490                                 # one step before the 30 days: 450 long (99.5 gone), 500 short
    assert abs(tot[k30 - 1][0] - 450) < 1e-9
    assert tot[k30][0] == 0.0 and tot[k30][1] == 0.0                                      # at 30 days the addition is subtracted (clamped at 0)
    assert tot[k30 + 50][0] == 0.0
    r = (int(oi['ts'].iloc[k30 + 3]) + xd.KNOWN - pp['t0']) // MIN
    assert np.isnan(m.dist_dn[r]) and np.isnan(m.dist_up[r])
    assert m.stats['expired_rows'] == 1


def test_planted_scale_on_oi_decrease_and_renormalisation():
    def extra(usd):
        usd[110:] = 1500.0                                              # -500 from 2000: every stored notional x 0.75
        usd[120:] = 1500.0 * 0.5 ** np.minimum(np.arange(len(usd) - 120), 21)    # then halving 21 times: S passes below 1e-6
        usd[120 + 21:] = usd[120 + 21]
    pp, oi = planted(extra=extra)
    tot = {}

    def hook(k, m):
        tot[k] = (float((m.long * m.S).sum()), float((m.short * m.S).sum()), m.S)
    m = xd.LiqModel(pp, oi, hook=hook).run()
    assert abs(tot[109][0] - 500) < 1e-9
    assert abs(tot[110][0] - 375) < 1e-9 and abs(tot[110][1] - 375) < 1e-9 and abs(tot[110][2] - 0.75) < 1e-15
    # step 120 is the first halving (usd[120] = 1500, same as before: d = 0); halvings are steps 121 .. 141
    for j in range(1, 22):
        want = 375 * 0.5 ** j
        assert abs(tot[120 + j][0] - want) < 1e-9 * max(1.0, 375) and abs(tot[120 + j][1] - want) < 1e-9 * 375
    assert m.stats['renorms'] >= 1
    assert tot[141][2] > 1e-9 and tot[141][2] <= 1.0
    assert min(v[2] for k, v in tot.items() if k >= 110) >= 0.5 ** 20 * 0.75 * 0.99


def test_planted_oi_gap_sets_baseline_only():
    pp, oi = planted(k_big=10)
    oi = oi.drop(index=range(50, 53)).reset_index(drop=True)            # 20 minutes between snapshots 49 and 53 -> row 50
    oi.loc[50:, 'oi'] = 60.0                                            # +40 contracts (4000 USD) across the gap: must not be added
    m = xd.LiqModel(pp, oi).run()
    assert m.stats['steps_skipped_gap'] == 1
    assert m.stats['steps_add'] == 1                                    # only the first jump at snapshot 10


def test_planted_traded_through_inside_the_block_is_gone_at_that_row():
    """A low through the 99.5 long-liq bucket inside the 5-minute block that reads the snapshot removes it from that row on
    (not only at the next snapshot), and so does a high through the 100.5 short-liq bucket."""
    def shape(c, h, l):
        l[511] = 98.9
        h[512] = 100.6
    pp, oi = planted(c_fn=shape)
    m = xd.LiqModel(pp, oi).run()
    assert (int(oi['ts'].iloc[100]) + xd.KNOWN - pp['t0']) // MIN - 1 == 509          # the first row of the block
    assert abs(m.dist_dn[510] - (100 - bprice(99.5)) / 100 * 1e4) < 1e-6
    assert abs(m.dist_dn[511] - (100 - bprice(98.5)) / 100 * 1e4) < 1e-6
    assert abs(m.dist_up[511] - (bprice(100.5) - 100) / 100 * 1e4) < 1e-6
    assert abs(m.dist_up[512] - (bprice(101.5) - 100) / 100 * 1e4) < 1e-6


def test_planted_oi_in_contracts_ignores_the_price_move_and_the_usd_column():
    """Only the number of contracts moves the model: a price that doubles with constant contracts adds nothing."""
    def shape(c, h, l):
        c[:] = np.linspace(100, 200, len(c))
        h[:] = c * 1.0001
        l[:] = c * 0.9999
    pp, oi = planted(c_fn=shape, k_big=10 ** 6)
    oi['oi'] = 10.0
    oi['oi_usd'] = 10.0 * np.linspace(100, 200, len(oi))                      # the USD column does rise
    m = xd.LiqModel(pp, oi).run()
    assert m.stats['steps_add'] == 0 and m.stats['steps_scale'] == 0
    oi.loc[500:, 'oi'] = 12.0
    m = xd.LiqModel(pp, oi).run()
    assert m.stats['steps_add'] == 1


def test_oi_clock_is_ts_plus_ten_minutes_and_off_grid_stamps_are_ceiled():
    assert xd.KNOWN == 10 * MIN and xd.SNAP == 5 * MIN
    pp, oi = planted(k_big=100)
    ts = int(oi['ts'].iloc[100])
    m = xd.LiqModel(pp, oi).run()
    row_ts_plus_5 = (ts + 5 * MIN - pp['t0']) // MIN - 1               # the close at ts + 5 min: the snapshot instant, not yet known
    row_ts_plus_10 = (ts + 10 * MIN - pp['t0']) // MIN - 1
    assert np.isnan(m.dist_dn[row_ts_plus_5]) and np.isfinite(m.dist_dn[row_ts_plus_10])
    # a stamp 2 seconds after the grid counts as the NEXT grid stamp: usable one 5-minute step later than the exact one
    o2 = oi.copy()
    o2.loc[100, 'ts'] = ts + 2000
    o2 = o2.drop(index=101).reset_index(drop=True)                      # (so that the ceiled stamp is not a duplicate)
    c2, info = xd.clean_oi(o2)
    assert int(c2['ts'].iloc[100]) == ts + 5 * MIN and info['oi_off_grid_rows'] == 1
    m2 = xd.LiqModel(pp, c2).run()
    assert np.isnan(m2.dist_dn[row_ts_plus_10]) and np.isfinite(m2.dist_dn[row_ts_plus_10 + 5])


def test_clean_oi_duplicates_keep_the_row_whose_implied_price_matches_the_perp():
    pp, oi = planted()
    ts = int(oi['ts'].iloc[50])
    bad = pd.DataFrame({'ts': [ts + 3000], 'oi': [99.0], 'oi_usd': [99.0 * 250.0]})                     # same grid stamp after the ceil, price 250
    good = pd.DataFrame({'ts': [ts + 4000], 'oi': [88.0], 'oi_usd': [88.0 * 100.0]})
    df = pd.concat([oi.drop(index=50), bad, good]).sort_values('ts')
    c, info = xd.clean_oi(df, pp)
    # the two off-grid rows collide on ts + 5 min with the exact row of the next snapshot: the one with price 250 is dropped
    assert info['oi_duplicates_dropped'] == 2 and info['oi_off_grid_rows'] == 2
    assert len(c) == len(c.drop_duplicates('ts')) and (c['oi_usd'] / c['oi']).between(99, 101).all()
    c2, _ = xd.clean_oi(df)                                                 # no perp: the last row of the file
    assert len(c2) == len(c)


def test_alignment_guard_refuses_a_shifted_perp_and_accepts_an_aligned_one():
    rng = np.random.default_rng(1)
    n = 3 * 1440
    c = 3000 * np.exp(np.cumsum(rng.normal(0, 7e-4, n)))
    o = np.r_[c[0], c[:-1]]
    sp = {'t0': START, 'n': n, 'c': c, 'o': o, 'h': np.maximum(o, c), 'l': np.minimum(o, c), 'gap': np.zeros(n, bool)}
    mk = lambda shift: pd.DataFrame({'ts': START + shift * MIN + np.arange(n, dtype=np.int64) * MIN, 'o': o, 'h': np.maximum(o, c),
                                     'l': np.minimum(o, c), 'c': c, 'v': 1.0, 'tb': 0.5})
    a = xd.check_alignment(sp, xd.perp_on_grid(sp, mk(0)))
    assert a['checked'] and a['r_0'] > 0.99 and abs(a['r_m1']) < 0.1 and abs(a['r_p1']) < 0.1
    for shift in (-1, 1):
        with pytest.raises(SystemExit, match='not on the spot clock'):
            xd.check_alignment(sp, xd.perp_on_grid(sp, mk(shift)))


def test_oi_clock_guard_refuses_stamps_earlier_than_the_model_clock():
    rng = np.random.default_rng(3)
    n = 4 * 1440
    c = 100 * np.exp(np.cumsum(rng.normal(0, 1.5e-3, n)))
    pp = {'t0': START, 'n': n, 'o': c, 'c': c, 'h': c, 'l': c, 'gap': np.zeros(n, bool)}
    ts = START + np.arange(n // 5 - 4, dtype=np.int64) * 5 * MIN
    mk = lambda off: pd.DataFrame({'ts': ts, 'oi': 1.0, 'oi_usd': c[(ts - START) // MIN + off]})
    for off in (0, 5):
        assert xd.check_oi_clock(mk(off), pp)['best_offset_min'] == off
    with pytest.raises(SystemExit, match='earlier than the model clock'):
        xd.check_oi_clock(mk(10), pp)


def test_perp_lag_shifts_every_perp_input(base, lowshare):
    sp, pp, o = base['sp'], base['pp'], base['oi']
    p1 = xd.lag_perp(pp, 1)
    assert xd.lag_perp(pp, 0) is pp
    for x in ('o', 'h', 'l', 'c', 'v', 'tb'):
        np.testing.assert_array_equal(p1[x][1:], pp[x][:-1])
    assert p1['gap'][0] and (p1['gap'][1:] == pp['gap'][:-1]).all()
    r0 = xd.xd_readings(sp, pp, o, base['a_hi'], keep=True)['values']
    r1 = xd.xd_readings(sp, p1, o, base['a_hi'], keep=True)['values']
    # CVDP:15 reads only the perp: at lag 1 it is the lag-0 series one row later
    np.testing.assert_allclose(r1['CVDP:15'][20000:30000], r0['CVDP:15'][19999:29999], equal_nan=True)
    assert not np.allclose(r1['CVDP:Div15'][20000:30000], r0['CVDP:Div15'][20000:30000], equal_nan=True)


def test_empty_tb_with_volume_is_a_gap_and_a_file_full_of_them_is_refused(tmp_path):
    spot, perp, oi = synth_frames(START, 3, seed=1)
    p = write(tmp_path, spot, perp, oi)
    sp = heat.load_minutes(p['spot'], end=int(spot['ts'].iloc[-1]) + MIN)
    perp2 = perp.copy()
    perp2.loc[100, 'tb'] = np.nan
    pg = xd.perp_on_grid(sp, perp2)
    assert pg['gap'][100] and pg['bad_rows'] == 1 and pg['gap'].sum() == 1
    assert xd.missing_tb(perp2) == 1
    perp3 = perp.copy()
    perp3.loc[perp3.index[::50], 'tb'] = np.nan                         # 2% of the rows
    q = str(tmp_path / 'perp_notb.csv')
    perp3.to_csv(q, index=False)
    with pytest.raises(SystemExit, match='empty tb'):
        xd.run_coin_outside('BTC', p['spot'], q, p['oi'], str(tmp_path / 'o'))
    spot3 = spot.copy()
    spot3.loc[spot3.index[::50], 'tb'] = np.nan
    q = str(tmp_path / 'spot_notb.csv')
    spot3.to_csv(q, index=False)
    with pytest.raises(SystemExit, match='empty tb'):
        xd.run_coin_outside('BTC', q, p['perp'], p['oi'], str(tmp_path / 'o'))


def test_pxdiv60_waits_for_its_whole_normalising_history_after_a_long_gap():
    n = 9000
    gap = np.zeros(n, bool)
    gap[5000:5180] = True                                              # a 3-hour hole
    st = xd.stale_for('CVDP:PxDiv60', gap)
    assert st[6679] and not st[6680]                                   # the hole ends at row 5,179: NA until 5,179 + 60 + 1,440 = 6,679 (the engine's rule alone: 5,179 + 560)
    assert not xd.stale_for('LIQMAP:Skew', gap)[5180 + 60 + heat.STALE_LONG[1] + 5]      # the others keep the engine's rule
    short = np.zeros(n, bool)
    short[5000:5030] = True                                            # a 30-minute hole: the engine's rule only
    assert not xd.stale_for('CVDP:PxDiv60', short)[5030 + 60 + heat.STALE_LONG[1] + 5]
    assert xd.stale_for('CVDP:Div15', gap)[5180 + 15 + 5] and not xd.stale_for('CVDP:Div15', gap)[5180 + 15 + heat.STALE_LONG[1] + 5]


def test_zone_needs_thirty_days_of_a_values(monkeypatch):
    x = np.random.default_rng(0).normal(size=40 * 1440)
    y = x.copy()
    y[10 * 1440:] = np.nan                                              # values on 10 days only (14,400 of them)
    R, e = xd.zone('x', y, 40 * 1440, 'F', t0=START)
    assert R is None
    R, e = xd.zone('x', x, 40 * 1440, 'F', t0=START)
    assert R is not None                                                # 40 days of values
    R, e = xd.zone('x', x, 20 * 1440, 'F', t0=START)
    assert R is None                                                    # A holds 20 days only


# ------------------------------------------------------------------------------------------------------ (e) the twin
def test_twin_rule_regenerates_exactly_and_readings_differ(base, lowshare):
    sp, pp, o = base['sp'], base['pp'], base['oi']
    seed = 2
    s = xd.twin_signs(sp['n'], seed)
    tw = heat.make_twin(sp, seed)
    np.testing.assert_array_equal(tw['tb'], np.where(s > 0, sp['tb'], sp['v'] - sp['tb']))      # the spot rule, with the regenerated signs
    assert s[0] == 1.0 and (s < 0).any() and (s > 0).any()
    pt = xd.twin_perp(pp, sp, tw, s)
    np.testing.assert_array_equal(pt['tb'], np.where(s > 0, pp['tb'], pp['v'] - pp['tb']))      # tb_p' = where(s > 0, tb_p, v_p - tb_p)
    np.testing.assert_allclose(pt['c'] / tw['c'], pp['c'] / sp['c'], rtol=1e-12)                # the real basis is kept
    np.testing.assert_allclose(pt['h'] / tw['h'], pp['c'] / sp['c'], rtol=1e-12)
    np.testing.assert_array_equal(pt['v'], pp['v'])
    assert not np.allclose(pt['c'], pp['c'])
    res = xd.xd_readings(tw, pt, o, base['a_hi'], keep=True)
    real = base['res']['values']
    for nm in xd.LEAGUE:
        a, b = res['values'][nm], real[nm]
        ok = np.isfinite(a) & np.isfinite(b)
        assert ok.sum() > 1000 and not np.allclose(a[ok], b[ok]), nm
    assert len(res['readings']) == 5
    # a twin follows its real coin's skips (the same families): a skipped name is never entered
    sk = xd.xd_readings(tw, pt, o, base['a_hi'], skip={'LIQMAP:DistAbove'})
    assert sk['skipped'] == ['LIQMAP:DistAbove'] and [r['name'] for r in sk['readings']] == [n for n in xd.LEAGUE if n != 'LIQMAP:DistAbove']
    # a different seed gives different signs
    assert not np.array_equal(s, xd.twin_signs(sp['n'], 3))


# ----------------------------------------------------------------------------------------------- (f) edges from A only
def test_zone_edges_come_from_split_a_rows_only(base, lowshare):
    spot, perp, oi = base['frames']
    sp0 = base['sp']
    t = base['a_hi'] - 1
    s2, p2, q2 = noise_after(spot, perp, oi, sp0['t0'], t, seed=12)
    sp, pp, o = inputs(base['dir'], s2, p2, q2, 'edgesB')
    res = xd.xd_readings(sp, pp, o, base['a_hi'])
    assert res['edges'] == base['res']['edges']
    for nm, e in res['edges'].items():
        x = base['res']['values'][nm][:base['a_hi']]
        np.testing.assert_allclose(e, np.quantile(x[np.isfinite(x)], heat.ZONE_Q), rtol=1e-12)
        assert e[0] < e[1] < e[2] < e[3] or nm == 'LIQMAP:Skew'
    for r in res['readings']:
        assert r['zones'] and r['k'] == 1 and r['levels'] == heat.ZONES and r['cond'] is True and r['type'] == 'xd'
        assert r['family'] == xd.FAMILY[r['name']] and r['base'] == r['name'] and r['codes'].dtype == np.int8
    # fewer than 1,000 values on A: no reading
    R, e = xd.zone('x', np.arange(5000.0), 900, 'F')
    assert R is None and e is None
    R, e = xd.zone('x', np.r_[np.arange(2000.0), np.full(3000, 1e6)], 2000, 'F')
    R2, e2 = xd.zone('x', np.r_[np.arange(2000.0), np.full(3000, -1e6)], 2000, 'F')
    assert e == e2 and (R['codes'][:2000] == R2['codes'][:2000]).all()


# ------------------------------------------------------------------------------------------------------ (g) refusals
def test_refusals(tmp_path):
    spot, perp, oi = synth_frames(START, 3, seed=1)
    p = write(tmp_path, spot, perp, oi)
    ok_dir = str(tmp_path / 'o')
    # a row at or after HEAT_END, in each of the three files
    late = pd.DataFrame({'ts': [heat.HEAT_END - MIN, heat.HEAT_END], 'o': 1.0, 'h': 1.0, 'l': 1.0, 'c': 1.0, 'v': 1.0, 'tb': 0.5})
    for nm, df in (('spot', spot), ('perp', perp)):
        q = str(tmp_path / f'late_{nm}.csv')
        pd.concat([df, late]).to_csv(q, index=False)
        with pytest.raises(SystemExit, match='at or after'):
            xd.run_coin_outside('BTC', q if nm == 'spot' else p['spot'], q if nm == 'perp' else p['perp'], p['oi'], ok_dir)
    q = str(tmp_path / 'late_oi.csv')
    pd.concat([oi, pd.DataFrame({'ts': [heat.HEAT_END], 'oi': 1.0, 'oi_usd': 1.0})]).to_csv(q, index=False)
    with pytest.raises(SystemExit, match='at or after'):
        xd.run_coin_outside('BTC', p['spot'], p['perp'], q, ok_dir)
    # DOGE: the asset and any path
    with pytest.raises(SystemExit, match='NEVER DOGE'):
        xd.run_coin_outside('DOGE', p['spot'], p['perp'], p['oi'], ok_dir)
    d = tmp_path / 'DOGE'
    d.mkdir()
    qq = write(d, spot, perp, oi)
    with pytest.raises(SystemExit, match='NEVER DOGE'):
        xd.run_coin_outside('BTC', qq['spot'], p['perp'], p['oi'], ok_dir)
    # seconds-stamped files (10 digits) and microsecond stamps (16 digits)
    for nm, df in (('spot', spot), ('perp', perp), ('oi', oi)):
        for div, mul in ((1000, 1), (1, 1000)):
            q = str(tmp_path / f'sec_{nm}_{div}_{mul}.csv')
            df2 = df.copy()
            df2['ts'] = df2['ts'] // div * mul
            df2.to_csv(q, index=False)
            kw = dict(p, **{nm: q})
            with pytest.raises(SystemExit, match='13 digits'):
                xd.run_coin_outside('BTC', kw['spot'], kw['perp'], kw['oi'], ok_dir)
    # a missing column
    q = str(tmp_path / 'nocol.csv')
    perp.drop(columns=['tb']).to_csv(q, index=False)
    with pytest.raises(SystemExit, match='lacks column'):
        xd.run_coin_outside('BTC', p['spot'], q, p['oi'], ok_dir)
    # the engine's own loader still refuses a late spot row on its own
    with pytest.raises(SystemExit):
        heat.load_minutes(str(tmp_path / 'late_spot.csv'))
    # the engine entry points are restored after a refusal
    assert heat.build_readings.__module__ == 'oracle.heat' and heat.make_twin.__module__ == 'oracle.heat'


# --------------------------------------------------------------------------------------------- (h) end-to-end smoke
@pytest.fixture(scope='module')
def smoke(tmp_path_factory):
    d = tmp_path_factory.mktemp('smoke')
    mp = pytest.MonkeyPatch()
    mp.setattr(xd, 'CLUSTER_SHARE', TEST_SHARE)
    start = ms('2024-10-01')
    days = (ms('2026-01-01') - start) // DAY
    spot, perp, oi = synth_frames(start, int(days), seed=11, level=60000.0)
    # one real-looking hole in each file
    spot = spot.drop(index=range(200000, 200012))
    perp = perp.drop(index=range(150000, 150003))
    oi = oi.drop(index=range(50000, 50004))
    p = write(d, spot, perp, oi)
    out = {}
    t = time.time()
    logs = []
    for tw in (0, 1):
        nm = 'BTC' if tw == 0 else 'BTC-twin1'
        out[nm] = xd.run_coin_outside('BTC', p['spot'], p['perp'], p['oi'], str(d / 'out' / nm), twin=tw, procs=1, log=logs.append)
    mp.undo()
    return {'dir': d, 'out': out, 'seconds': time.time() - t, 'logs': logs}


def test_smoke_runs_and_the_league_reads_it(smoke):
    d = smoke['dir']
    assert smoke['seconds'] < 600
    for nm in ('BTC', 'BTC-twin1'):
        mt = smoke['out'][nm]
        assert os.path.exists(d / 'out' / nm / 'heat.csv.gz') and os.path.exists(d / 'out' / nm / 'meta.json')
        assert mt['readings'] == 5 and mt['conditions'] == 5
        assert set(mt['edges']) == set(xd.LEAGUE)
        assert mt['twin'] == (0 if nm == 'BTC' else 1) and mt['label'] == ('BTC' if nm == 'BTC' else 'BTC~twin1')
        assert set(mt['near_duplicates']) and set(mt['direction_coupling']) == set(xd.LEAGUE)
        assert mt['constants']['maintenance_margin'] == 0.005 and mt['model']['steps_add'] > 0
        assert mt['skipped_readings'] == [] and mt['heat_end'].startswith('2026-01-01')
        xi = mt['xd_input']
        assert xi['perp_lag_min'] == 0 and xi['perp_spot_alignment']['r_0'] > 0.9 and xi['oi_clock']['best_offset_min'] == 0
        assert xi['spot_missing_tb'] == 0 and xi['perp_missing_tb'] == 0 and 'oi_duplicates_dropped' in xi
        assert mt['model']['bucket_share_of_oi_max'] > 0 and mt['model']['bucket_share_samples'] > 100
        sh = mt['reading_share']
        assert all(sh[n]['A'] > 0.3 for n in xd.LEAGUE), sh
    # the stored meta.json is the returned one and is valid JSON
    mt = json.load(open(d / 'out' / 'BTC' / 'meta.json'))
    assert mt['near_duplicates'] == json.loads(json.dumps(smoke['out']['BTC']['near_duplicates']))
    df = pd.read_csv(d / 'out' / 'BTC' / 'heat.csv.gz', low_memory=False)
    keys = set(df.key.astype(str))
    assert any(k.startswith('CVDP:Div15=') for k in keys) and any(k.startswith('LIQMAP:Skew=') for k in keys)
    assert (df.kind == 'single').any() and (df.kind == 'pair').any()
    # the OR-HM1 league reads the output unchanged
    s = heat.league(str(d / 'out'), str(d / 'league'))
    assert s['coins'] == ['BTC'] and s['twins'] == ['BTC~twin1']
    assert os.path.exists(d / 'league' / 'league.md') and os.path.exists(d / 'league' / 'summary.json')
    assert 'direction' in json.dumps(s).lower() or os.path.exists(d / 'league' / 'summary.json')
    # the engine's entry points are back
    assert heat.build_readings.__module__ == 'oracle.heat' and heat.make_twin.__module__ == 'oracle.heat'


def test_cli_parser(tmp_path):
    with pytest.raises(SystemExit):
        xd.main(['coin', '--asset', 'DOGE', '--spot', 'a', '--perp', 'b', '--oi', 'c', '--out', str(tmp_path)])
