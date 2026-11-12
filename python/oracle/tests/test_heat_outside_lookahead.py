"""Adversarial look-ahead / twin checks of python/oracle/heat_outside.py (reviewer's tests, synthetic data only).

test_truncate_the_future_random passes: removing every perp row after t and every OI row known after close(t), and
replacing the spot future by noise, leaves every value series (league and references, real and twin) bit-identical on
rows <= t, with spot and perp gaps, OI gaps over 15 minutes, off-grid OI stamps, duplicate OI rows and OI before the grid.

The three former xfail(strict) tests (OI known time, twin coupling to the real price, perp stamp shift) now pass: the fixes are
the ts + 10 minute OI clock with grid-ceiled stamps, a model driven by contracts, and check_alignment."""
import numpy as np
import pandas as pd
import pytest

from oracle import heat, heat_outside as xd
from oracle.common import MIN, ms

T0 = ms('2024-11-01')


def _frames(seed, days=8):
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
    oi = pd.concat([oi, oi.sample(20, random_state=seed).assign(oi_usd=lambda d: d.oi_usd * 1.1)])
    return n, spot, perp, oi.sort_values('ts', kind='stable').reset_index(drop=True)


def _grid(df, n):
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


def _values(n, spdf, ppdf, oidf, twin=None):
    sp = _grid(spdf, n)
    pp = xd.perp_on_grid(sp, ppdf)
    if twin:
        tw = heat.make_twin(sp, twin)
        pp = xd.twin_perp(pp, sp, tw, xd.twin_signs(n, twin))
        sp = tw
    X = xd.xd_values(sp, pp, xd.clean_oi(oidf)[0])
    out = {}
    for nm in xd.LEAGUE + xd.REFS:
        x = np.array(X['values'][nm])
        x[xd.stale_for(nm, X['gap'])] = np.nan
        out[nm] = x
    out['dist_up_bps'], out['dist_dn_bps'] = X['dist_bps']['up'], X['dist_bps']['dn']
    return out


@pytest.mark.parametrize('seed,twin', [(0, None), (1, 3)])
def test_truncate_the_future_random(seed, twin, monkeypatch):
    monkeypatch.setattr(xd, 'CLUSTER_SHARE', 0.004)
    n, spot, perp, oi = _frames(seed)
    full = _values(n, spot, perp, oi, twin)
    assert np.isfinite(full['LIQMAP:DistAbove']).mean() > 0.3
    rng = np.random.default_rng(seed + 100)
    Tk = np.sort(xd.clean_oi(oi)[0].ts.to_numpy() + xd.KNOWN)
    cand = [int(x) for x in rng.integers(3000, n - 10, 6)]
    for T in Tk[rng.integers(0, len(Tk), 4)]:
        r = int(-(-(int(T) - T0) // MIN)) - 1                          # close(r) >= T_k
        cand += [r - 1, r]
    for t in cand:
        s2 = spot.copy()
        m = (s2.ts > T0 + t * MIN).to_numpy()
        s2.loc[m, 'c'] = s2.loc[m, 'c'] * np.exp(rng.normal(0, 0.05, m.sum()))
        s2.loc[m, 'o'] = s2.loc[m, 'c']
        s2.loc[m, 'h'] = s2.loc[m, 'c'] * 1.01
        s2.loc[m, 'l'] = s2.loc[m, 'c'] * 0.99
        s2.loc[m, 'v'] = rng.uniform(0, 1e4, m.sum())
        s2.loc[m, 'tb'] = s2.loc[m, 'v'] * rng.random(m.sum())
        cut = _values(n, s2, perp[perp.ts <= T0 + t * MIN], oi[-(-oi.ts // xd.SNAP) * xd.SNAP + xd.KNOWN <= T0 + (t + 1) * MIN], twin)
        for nm in full:
            a, b = full[nm][:t + 1], cut[nm][:t + 1]
            assert ((np.isnan(a) & np.isnan(b)) | (a == b)).all(), (nm, t)


def test_twin_liqmap_adds_do_not_follow_the_real_price():
    rng = np.random.default_rng(4)
    n = 6 * 1440
    c = 3000 * np.exp(np.cumsum(rng.normal(0, 7e-4, n)))
    o = np.r_[c[0], c[:-1]]
    v = rng.uniform(10, 200, n)
    sp = {'t0': T0, 'n': n, 'o': o, 'h': np.maximum(o, c) * 1.0002, 'l': np.minimum(o, c) * 0.9998, 'c': c, 'v': v,
          'tb': v * rng.uniform(0.3, 0.7, n), 'gap': np.zeros(n, bool)}
    pp = dict(sp, first=0)
    K = n // 5
    ts = T0 + np.arange(K, dtype=np.int64) * 5 * MIN
    S = np.minimum((ts - T0) // MIN, n - 1)
    oi = pd.DataFrame({'ts': ts, 'oi': 1e5, 'oi_usd': 1e5 * o[S]})              # the number of contracts never changes
    seed = 5
    tw = heat.make_twin(sp, seed)
    pt = xd.twin_perp(pp, sp, tw, xd.twin_signs(n, seed))
    adds = []
    xd.LiqModel(pt, oi, hook=lambda k, m: adds.append(m.stats['steps_add'])).run()
    a = np.diff(np.r_[0, adds])[1:].astype(bool)
    real_up = (o[S[1:]] > o[S[:-1]])[:len(a)]
    # no contract was opened, so nothing should be added; at the very least the adds must not equal the REAL up-moves
    assert a.sum() == 0 or (a != real_up).mean() > 0.3


def test_perp_file_shifted_by_one_minute_is_refused():
    rng = np.random.default_rng(1)
    n = 3 * 1440
    c = 3000 * np.exp(np.cumsum(rng.normal(0, 7e-4, n)))
    o = np.r_[c[0], c[:-1]]
    sp = {'t0': T0, 'n': n, 'c': c, 'o': o, 'h': np.maximum(o, c), 'l': np.minimum(o, c), 'gap': np.zeros(n, bool)}
    perp = pd.DataFrame({'ts': T0 - MIN + np.arange(n, dtype=np.int64) * MIN, 'o': o, 'h': np.maximum(o, c), 'l': np.minimum(o, c),
                         'c': c, 'v': 1.0, 'tb': 0.5})
    with pytest.raises(SystemExit):
        xd.check_alignment(sp, xd.perp_on_grid(sp, perp))


def test_oi_known_time_follows_the_design_clock_for_new_files():
    rng = np.random.default_rng(2)
    n = 2 * 1440
    c = np.full(n, 100.0)
    pp = {'t0': T0, 'n': n, 'o': c, 'h': c + 0.01, 'l': c - 0.01, 'c': c, 'v': np.ones(n), 'tb': np.full(n, 0.5), 'gap': np.zeros(n, bool)}
    K = n // 5
    usd = np.full(K, 1000.0)
    usd[100:] = 2000.0
    oi = pd.DataFrame({'ts': T0 + np.arange(K, dtype=np.int64) * 5 * MIN, 'oi': usd / 100.0, 'oi_usd': usd})
    m = xd.LiqModel(pp, oi).run()
    ts = int(oi.ts[100])
    row_at_ts_plus_5 = (ts + 5 * MIN - T0) // MIN - 1
    # under the new convention row ts is the snapshot at ts + 5 min, known at ts + 10 min: no reading of it before then
    assert np.isnan(m.dist_dn[row_at_ts_plus_5])
