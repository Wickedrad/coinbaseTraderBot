"""OR-HM2 Part 3, the drill (python/oracle/heat_hm2_drill.py; build plan OR-HM2-part3-build.md): no lookahead (every A
number, the A choice and the own instance features are blind to 2025: replacing every 2025 minute leaves them identical
bit for bit; the live own levels equal the history's), pure noise shows nothing beyond its coin-flip twin through the
identical pipeline, a planted separator is found with the right curve (a threshold at the planted percentile), the
right depth-2 split inside its gate and the planted loser level, and is gone on the twin. Also: the profit proxy on
hand-built paths, the packed counts against the direct per-cluster form, the 200-bin codes against the zone codes, the
unit list, the league's files and the gate rows' merge. Synthetic minutes, SPLITS patched, procs 1."""
import contextlib
import gzip
import hashlib
import json
import os

import numpy as np
import pandas as pd
import pytest

from oracle import heat
from oracle import heat_hm2 as hm
from oracle import heat_hm2_drill as dr
from oracle import heat_hm2_league as hl
from oracle.common import DAY, MIN

A_DAYS, B_DAYS = 84, 28                    # 12 weeks of A, 4 of B
NOOP = lambda *a, **k: None


# ------------------------------------------------------------------------------------------------------- fixtures
@pytest.fixture(scope='module')
def splits():
    mp = pytest.MonkeyPatch()
    start = heat.HEAT_END - (A_DAYS + B_DAYS) * DAY
    mp.setattr(heat, 'SPLITS', {'A': (start, start + A_DAYS * DAY), 'B': (start + A_DAYS * DAY, heat.HEAT_END)})
    yield start
    mp.undo()


def _walk(n, seed):
    rng = np.random.default_rng(seed)
    return rng.normal(0, 8e-4, n), np.abs(rng.normal(0, 3e-4, n)), rng.uniform(1, 2, n), rng.uniform(0.3, 0.7, n)


def _write(path, start, r, w, v, f):
    """1-minute bars from log returns r (open = the previous close)."""
    n = len(r)
    c = 100 * np.exp(np.cumsum(r))
    o = np.r_[100, c[:-1]]
    pd.DataFrame({'ts': start + np.arange(n) * MIN, 'o': o, 'h': np.maximum(o, c) * (1 + w), 'l': np.minimum(o, c) * (1 - w), 'c': c, 'v': v,
                  'tb': v * f}).to_csv(path, index=False)
    return heat.load_minutes(str(path))


def _zone(name, x, k, a_bars, **kw):
    xa = x[:a_bars]
    e = np.quantile(xa[np.isfinite(xa)], heat.ZONE_Q)
    return dict({'name': name, 'k': k, 'codes': heat.bucket(x, e), 'levels': list(heat.ZONES), 'base': name, 'zones': True, 'type': 'osc',
                 'edges': [float(q) for q in e]}, **kw)


def _price_readings(m, g):
    """Causal readings of the coin's own path (zones of 3- and 10-bar returns at 1 and 15 minutes, the sign of the
    5-bar return): engine-like names, so they are HM1 event levels too."""
    c = np.log(m['c'])
    out, raw = [], {}
    for k in (1, 15):
        nb = m['n'] // k
        cb = c[k - 1::k][:nb]
        a_bars = g.sp['A'].hi // k
        for L in (3, 10):
            x = np.r_[np.full(L, np.nan), cb[L:] - cb[:-L]]
            out.append(_zone(f'{k}m:R{L}', x, k, a_bars))
            raw[f'{k}m:R{L}'] = (x, k)
        x = np.r_[np.full(5, np.nan), cb[5:] - cb[:-5]]
        out.append({'name': f'{k}m:R5 sign', 'k': k, 'codes': np.where(np.isfinite(x), (x > 0).astype(np.int8), -1).astype(np.int8),
                    'levels': ['below 0', 'above 0'], 'base': f'{k}m:R5', 'type': 'osc'})
    return out, raw


def _ctx(m, R, raw, twin=0):
    lab = heat.labels(m)
    g = heat.Grid(m, lab)
    with hm.h240():
        lab240 = heat.labels(m)
        g240 = heat.Grid(m, lab240)
    return dr.make_drill_ctx(m, R, raw=raw, asset='X', twin=twin, lab=lab, g=g, lab240=lab240, g240=g240, log=NOOP)


def _units(units: list, pack=None) -> dict:
    us = []
    for i, (kind, key, tier, extra) in enumerate(units):
        u = dr._unit('X', kind, key, tier, 'test', **extra)
        u['order'] = i
        us.append(u)
    return {'schema': dr.SCHEMA_UNITS, 'coins': {'X': us}, 'sha256': 'test', 'hm2_nongate_sha256': hl.non_gate_sha(pack) if pack else None,
            'hm2_tier2_sha256': hl.tier2_sha(pack) if pack else None}


def _read(out, suffix):
    fr = [pd.read_csv(os.path.join(out, f)) for f in sorted(os.listdir(out)) if f.endswith(suffix) and os.path.getsize(os.path.join(out, f)) > 30]
    fr = [x for x in fr if len(x)]
    return pd.concat(fr, ignore_index=True) if fr else pd.DataFrame()


def _drill(out):
    d = {}
    for f in sorted(os.listdir(out)):
        if f.endswith('_drill.json.gz'):
            with gzip.open(os.path.join(out, f), 'rt') as fh:
                d.update(json.load(fh))
    return d


# ---------------------------------------------------------------------------------------------- the planted series
PLANT_UNIT = '1m:RSI14=very low'


def _planted(tmp, start, twin=0):
    """Instances of '1m:RSI14=very low' every 16-20 minutes (so the 15-minute windows never overlap). FLOW:TB15 (iid
    uniform, a value reading of its own family) plants the call's 15-minute direction: right with p 0.70 at or over
    its 70th percentile; at or over its 90th, 0.88 when POS:Phase is 'late' and 0.61 otherwise (the depth-2 split);
    under its 70th, VOL:Jump5 'down' (5% of minutes) makes the call wrong 75% of the time (the loser level). The twin is
    heat.make_twin of the planted minutes: the same readings, the outcomes' link gone."""
    n = (A_DAYS + B_DAYS) * 1440
    rng = np.random.default_rng(7)
    inst = np.cumsum(rng.integers(16, 21, n // 16))
    inst = inst[(inst >= 100) & (inst < n - 300)]
    rsi = np.full(n, 2, np.int8)
    rsi[inst] = 0
    flow = rng.uniform(0, 1, n)
    phase = ((np.arange(n) % 15) // 5).astype(np.int8)
    u = rng.uniform(0, 1, n)
    jump = np.where(u < 0.05, 0, np.where(u > 0.525, 2, 1)).astype(np.int8)
    r, w, v, f = _walk(n, 21)
    for i in inst:
        x = flow[i]
        if x >= 0.9:
            p = 0.88 if phase[i] == 2 else 0.61
        elif x >= 0.7:
            p = 0.70
        elif jump[i] == 0:
            p = 0.25
        else:
            continue
        want = 1.0 if rng.uniform() < p else -1.0
        s = r[i + 1:i + 16].sum()
        if s * want < 0:
            r[i + 1:i + 16] *= -1
    m = _write(os.path.join(tmp, 'p.csv'), start, r, w, v, f)
    if twin:
        m = heat.make_twin(m, twin)
    g = heat.Grid(m, heat.labels(m))
    R, raw = _price_readings(m, g)
    R += [{'name': '1m:RSI14', 'k': 1, 'codes': rsi, 'levels': list(heat.ZONES), 'base': '1m:RSI14', 'zones': True, 'type': 'osc'},
          _zone('FLOW:TB15', flow, 1, g.sp['A'].hi, family='flow'),
          {'name': 'POS:Phase', 'k': 1, 'codes': phase, 'levels': ['early', 'middle', 'late'], 'base': 'POS:Phase', 'ctx': True, 'family': 'position'},
          {'name': 'VOL:Jump5', 'k': 1, 'codes': jump, 'levels': ['down', 'none', 'up'], 'base': 'VOL:Jump5', 'family': 'vol'}]
    raw['FLOW:TB15'] = (flow, 1)
    return _ctx(m, R, raw, twin), inst


@pytest.fixture(scope='module')
def planted(splits, tmp_path_factory):
    tmp = str(tmp_path_factory.mktemp('planted'))
    U = _units([('level', PLANT_UNIT, 1, {}), ('level', '1m:R3=very high', 3, {})])
    res = {}
    for twin in (0, 1):
        ctx, inst = _planted(tmp, splits, twin)
        out = os.path.join(tmp, f'twin{twin}')
        meta = dr.run_series('X', '', out, U, twin=twin, procs=1, ctx=ctx, log=NOOP)
        res[twin] = {'ctx': ctx, 'out': out, 'meta': meta, 'inst': inst, 'T': _read(out, '_top.csv.gz'), 'D2': _read(out, '_depth2.csv.gz'),
                     'drill': _drill(out), 'U': _read(out, '_units.csv.gz'), 'L': _read(out, '_losers.csv.gz')}
    return res


# -------------------------------------------------------------------------------------------- the noise series
def _noise(tmp, start, seed=11, twin=0, b_seed=None):
    n = (A_DAYS + B_DAYS) * 1440
    r, w, v, f = _walk(n, seed)
    if b_seed is not None:                                   # every 2025 minute replaced by another walk
        b0 = A_DAYS * 1440
        r2, w2, v2, f2 = _walk(n, b_seed)
        r[b0:], w[b0:], v[b0:], f[b0:] = r2[b0:], w2[b0:], v2[b0:], f2[b0:]
    m = _write(os.path.join(tmp, f'n{seed}_{b_seed}.csv'), start, r, w, v, f)
    if twin:
        m = heat.make_twin(m, twin)
    g = heat.Grid(m, heat.labels(m))
    R, raw = _price_readings(m, g)
    q = ((m['t0'] // MIN + np.arange(m['n'])) % 15 // 5).astype(np.int8)
    R.append({'name': 'POS:Phase', 'k': 1, 'codes': q, 'levels': ['early', 'middle', 'late'], 'base': 'POS:Phase', 'ctx': True, 'family': 'position'})
    return _ctx(m, R, raw, twin)


NOISE_UNITS = [('level', '1m:R3=very high', 1, {}), ('level', '1m:R10=low (falling in)', 1, {}),
               ('cell', '1m:R3=very low|15m:R10', 2, {'when': '1m:R3=very low', 'conds': [['15m:R10', ['high', 'very high']]]}),
               ('hm2', '15m:R3=low&1m:R5 sign', 2, {'conds': [['15m:R3', ['low']], ['1m:R5 sign', ['above 0']]], 'extra': {'hm2_kind': 'pair'}}),
               ('level', '15m:R3=very high', 3, {})]
PACK = {'schema': 'test', 'rows': [{'coin': 'X', 'kind': 'pair', 'key': 'a & b', 'h': 15, 'odds': 1.5},
                                   {'coin': 'X', 'kind': 'gate', 'key': 'old gate row', 'h': 15}]}


@pytest.fixture(scope='module')
def noise(splits, tmp_path_factory):
    tmp = str(tmp_path_factory.mktemp('noise'))
    U = _units(NOISE_UNITS, PACK)
    up = os.path.join(tmp, 'units.json')
    dr._dump(U, up)
    res = {'units': up, 'dir': os.path.join(tmp, 'series'), 'tmp': tmp}
    for twin in (0, 1):
        ctx = _noise(tmp, splits, twin=twin)
        out = os.path.join(res['dir'], f'X{"~twin" + str(twin) if twin else ""}')
        dr.run_series('X', '', out, U, twin=twin, procs=1, ctx=ctx, log=NOOP)
        res[twin] = {'ctx': ctx, 'out': out, 'T': _read(out, '_top.csv.gz')}
    return res


# ------------------------------------------------------------------------------------------------ the profit proxy
def _bars(n, i, closes_bps, base=100.0, lows=None, opens=None):
    """Flat bars at `base` with the closes after row i set in bps of the entry (o[i + 1] = base); h / l from o and c
    unless lows / opens are given ({j: bps})."""
    c = np.full(n, base)
    for j, b in enumerate(closes_bps, 1):
        c[i + j] = base * (1 + b / 1e4)
    c[i + len(closes_bps) + 1:] = c[i + len(closes_bps)]
    o = np.r_[base, c[:-1]]
    for j, b in (opens or {}).items():
        o[i + j] = base * (1 + b / 1e4)
    h, l = np.maximum(o, c), np.minimum(o, c)
    for j, b in (lows or {}).items():
        l[i + j] = base * (1 + b / 1e4)
    return o, h, l, c


def test_profit_proxy_paths():
    """1-60: cost = 4.5 / 40 x sigma x sqrt(tau); the FIRST close at or beyond +F (take) or -C (cut) ends the trade,
    else the close at H; pi = exit - cost (bps), pi_c = clip(exit x 40 / (sigma sqrt tau), +-50) - 4.5 (cents); two price
    steps at least; no sigma: no proxy. 240: no take, the stop max(50, 2 x ATR) on the minute's adverse extreme, filled
    at the stop or at an open beyond it; 25 bps."""
    n, i, s = 400, 5, 10.0
    cost = 4.5 / 40 * s * np.sqrt(10)
    fac = 40 / (s * np.sqrt(10))
    P = lambda cl, H=15, d=1, **kw: dr.proxy_path(*_bars(n, i, cl), i, H, d, **{'sigma': s, **kw})
    r = P([3, 8, -20])                                                  # take at the second close (8 >= F = 7.1)
    assert (r['kind'], r['j']) == (1, 2) and r['pi'] == pytest.approx(8 - cost, abs=1e-9) and r['pi_c'] == pytest.approx(8 * fac - 4.5, abs=1e-9)
    r = P([-3, 5, -7.5, 30])                                            # cut at the third
    assert (r['kind'], r['j']) == (2, 3) and r['pi'] == pytest.approx(-7.5 - cost, abs=1e-9)
    r = P([-8, 20])                                                     # the first event ends it
    assert (r['kind'], r['j']) == (2, 1)
    r = P([3, -4, 5, 4])                                                # time: the close at H
    assert (r['kind'], r['j']) == (3, 15) and r['pi'] == pytest.approx(4 - cost, abs=1e-9)
    r = P([200])                                                        # gross cents clipped at +50
    assert r['pi_c'] == pytest.approx(50 - 4.5) and r['pi'] == pytest.approx(200 - cost, abs=1e-9)
    r = P([-200])
    assert r['pi_c'] == pytest.approx(-50 - 4.5)
    r = P([-8], d=-1)                                                   # the down call takes on the way down
    assert (r['kind'], r['j']) == (1, 1) and r['pi'] == pytest.approx(8 - cost, abs=1e-9)
    r = P([8, -20], tick=5.0)                                           # F = 2 steps = 10 bps: 8 is not a take
    assert (r['kind'], r['j']) == (2, 2)
    r = P([3, 8], H=60)                                                 # tau 30 at 60 minutes
    c60 = 4.5 / 40 * s * np.sqrt(30)
    assert r['kind'] == 3 and r['pi'] == pytest.approx(8 - c60, abs=1e-9)
    assert np.isnan(P([8], sigma=np.nan)['pi'])
    # 240: stop 60 bps (2 x ATR 30) on the low of the 10th minute, filled at the stop
    o, h, l, c = _bars(n, i, [-10] * 20, lows={10: -61})
    r = dr.proxy_path(o, h, l, c, i, 240, 1, atr=30.0)
    assert (r['kind'], r['j']) == (2, 10) and r['pi'] == pytest.approx(-60 - 25, abs=1e-9) and np.isnan(r['pi_c'])
    o, h, l, c = _bars(n, i, [-10] * 20, opens={12: -80}, lows={12: -80})        # opens beyond the stop: filled at the open
    r = dr.proxy_path(o, h, l, c, i, 240, 1, atr=10.0)                        # stop max(50, 20) = 50
    assert (r['kind'], r['j']) == (2, 12) and r['pi'] == pytest.approx(-80 - 25, abs=1e-6)
    o, h, l, c = _bars(n, i, [30] * 240)
    r = dr.proxy_path(o, h, l, c, i, 240, 1, atr=10.0)                        # never stopped, no take: the close at 240
    assert (r['kind'], r['j']) == (3, 240) and r['pi'] == pytest.approx(30 - 25, abs=1e-6)
    r = dr.proxy_path(o, h, l, c, i, 240, -1, atr=10.0)                       # the down call: 30 against, under its stop
    assert (r['kind'], r['j']) == (3, 240) and r['pi'] == pytest.approx(-30 - 25, abs=1e-6)
    o, h, l, c = _bars(n, i, [60] * 240)
    r = dr.proxy_path(o, h, l, c, i, 240, -1, atr=10.0)                       # stopped by the first minute's high
    assert (r['kind'], r['j']) == (2, 1) and r['pi'] == pytest.approx(-50 - 25, abs=1e-6)
    assert np.isnan(dr.proxy_path(o, h, l, c, i, 240, 1)['pi'])               # no ATR yet: no proxy


# ------------------------------------------------------------------------------------- packed against direct
def _fake_insts(seed=5, U=3):
    rng = np.random.default_rng(seed)
    insts, Vs = [], []
    for _ in range(U):
        N = int(rng.integers(500, 900))
        dA, dB = int(rng.integers(25, 45)), int(rng.integers(10, 20))
        x = dr.Inst()
        x.split = np.sort((rng.uniform(size=N) < 0.3).astype(np.int8))
        raw = np.where(x.split == 0, rng.integers(0, dA, N), dA + rng.integers(0, dB, N))
        x.day_u, x.day = np.unique(raw, return_inverse=True)
        x.day = x.day.astype(np.int64)
        x.G, x.sd = len(x.day_u), int((x.day_u < dA).sum())
        wk = np.where(x.day_u < dA, x.day_u // 7, 10 ** 6 + (x.day_u - dA) // 7)
        _, x.dweek = np.unique(wk, return_inverse=True)
        x.rows = np.arange(N)
        x.d = np.ones(6, np.int8)
        x.unit, x.bases, x.own = {'id': 'u', 'tier': 1}, set(), {}
        V = {'ok': np.ones((6, N), bool), 'pok': np.ones((6, N), bool)}
        V['ok'][5] = rng.uniform(size=N) < 0.8
        V['pok'][:5] = rng.uniform(size=N) < 0.9
        V['pok'][5] = V['ok'][5] & (rng.uniform(size=N) < 0.9)
        V['y'] = np.where(V['ok'], rng.integers(-1, 2, (6, N)), 0).astype(np.int8)
        V['move'] = np.where(V['ok'], rng.normal(0, 30, (6, N)), np.nan).astype(np.float32)
        V['prof'] = np.where(V['pok'], np.r_[rng.uniform(-54.5, 45.5, (5, N)), rng.normal(-25, 40, (1, N))], np.nan).astype(np.float32)
        V['kind'] = np.where(V['pok'], rng.integers(1, 4, (6, N)), 0).astype(np.int8)
        x.W, _ = dr.pack_weights(x, V)
        insts.append(x)
        Vs.append(V)
    return insts, Vs


def test_packed_counts_equal_direct():
    """The 12 packed bincounts and the kernel give, per unit, level and split, the counts, days, rest days and weeks,
    right / wrong, take / cut, and for each of the 18 lifts the level's mean, the rest's mean and the day- and
    week-clustered standard errors of the lift exactly as the direct per-cluster form on the same (quantised) values."""
    insts, Vs = _fake_insts()
    L = 4
    rng = np.random.default_rng(9)
    codes = [np.where(rng.uniform(size=len(x.rows)) < 0.1, -1, rng.choice(L, len(x.rows), p=[0.1, 0.2, 0.3, 0.4])) for x in insts]
    o = dr.level_cells(insts, np.concatenate(codes), L)
    checked = 0
    for u, (x, V, cd) in enumerate(zip(insts, Vs, codes)):
        for s in (0, 1):
            days = np.arange(0, x.sd) if s == 0 else np.arange(x.sd, x.G)
            insp = (x.split == s) & (cd >= 0)
            dl = x.day - days[0]
            for hi in range(6):
                for tr in range(3):
                    li = hi * 3 + tr
                    if tr < 2:
                        cnt = V['ok'][hi] if hi == 5 else np.ones(len(x.rows), bool)
                        val = V['y'][hi].astype(float) if tr == 0 else np.rint(np.clip(np.nan_to_num(V['move'][hi].astype(float)), -4000, 4000) / 0.5) * 0.5
                    else:
                        cnt = V['pok'][5] if hi == 5 else V['pok'][2]
                        pf = np.nan_to_num(V['prof'][hi].astype(float))
                        val = np.rint(np.clip(pf, -54.5, 45.5) / 0.05) * 0.05 if hi < 5 else np.rint(np.clip(pf, -4000, 4000) / 0.5) * 0.5
                    m = insp & cnt
                    Vd = np.zeros((L, len(days)))
                    Cd = np.zeros((L, len(days)))
                    np.add.at(Vd, (cd[m], dl[m]), np.where(m, val, 0)[m])
                    np.add.at(Cd, (cd[m], dl[m]), 1)
                    for cl, key in ((np.arange(len(days)), 'sed'), (x.dweek[days] - x.dweek[days[0]], 'sew')):
                        ref = dr.cells_direct(Vd, Cd, cl)
                        for lv in range(L):
                            if not np.isfinite(ref['mu'][lv]):
                                continue
                            assert o['mu'][u, lv, s, li] == pytest.approx(ref['mu'][lv], rel=1e-9, abs=1e-9)
                            assert o['mur'][u, lv, s, li] == pytest.approx(ref['mur'][lv], rel=1e-9, abs=1e-9)
                            if np.isfinite(ref['se'][lv]):
                                assert o[key][u, lv, s, li] == pytest.approx(ref['se'][lv], rel=1e-7, abs=1e-12)
                                checked += 1
            for lv in range(L):
                mm = insp & (cd == lv)
                assert o['cnt'][u, lv, s, 0] == mm.sum() and o['days'][u, lv, s, 0] == len(np.unique(x.day[mm]))
                assert o['weeks'][u, lv, s, 0] == len(np.unique(x.dweek[x.day[mm]]))
                rest = insp & (cd != lv)
                assert o['rdays'][u, lv, s, 0] == len(np.unique(x.day[rest]))
                assert o['cnt'][u, lv, s, 3] == (mm & V['pok'][5]).sum()
                for hi in range(6):
                    assert o['rw'][u, lv, s, hi, 0] == (mm & (V['y'][hi] > 0)).sum() and o['rw'][u, lv, s, hi, 1] == (mm & (V['y'][hi] < 0)).sum()
                for k, hi in enumerate((2, 4, 5)):
                    assert o['tc'][u, lv, s, k, 0] == (mm & V['pok'][hi] & (V['kind'][hi] == 1)).sum()
                    assert o['tc'][u, lv, s, k, 1] == (mm & V['pok'][hi] & (V['kind'][hi] == 2)).sum()
    assert checked > 500
    # a full day of 1,440 instances at the clip values packs and unpacks exactly (no field overflows)
    x = dr.Inst()
    x.rows, x.split = np.arange(1440), np.zeros(1440, np.int8)
    x.day_u, x.day, x.G, x.sd, x.dweek = np.array([0]), np.zeros(1440, np.int64), 1, 1, np.zeros(1, np.int64)
    V = {'ok': np.ones((6, 1440), bool), 'pok': np.ones((6, 1440), bool), 'y': np.ones((6, 1440), np.int8), 'kind': np.ones((6, 1440), np.int8),
         'move': np.full((6, 1440), 9000.0, np.float32), 'prof': np.r_[np.full((5, 1440), 99.0), np.full((1, 1440), 9000.0)].astype(np.float32)}
    x.W, clipped = dr.pack_weights(x, V)
    o1 = dr.level_cells([x], np.zeros(1440, np.int64), 1)
    assert clipped == 6 * 1440 + 1440 and o1['cnt'][0, 0, 0].tolist() == [1440] * 4 and o1['rw'][0, 0, 0, :, 0].tolist() == [1440] * 6
    assert o1['mu'][0, 0, 0, 1] == 4000.0 and o1['mu'][0, 0, 0, 2] == pytest.approx(45.5) and o1['mu'][0, 0, 0, 17] == 4000.0
    assert o1['tc'][0, 0, 0, :, 0].tolist() == [1440] * 3
    # z_adj: the weaker |t| ranks; Bonferroni over the levels with a sample
    z, t, G, wk = dr.z_adj(np.array([5.0, -4.0]), np.array([100, 100]), np.array([3.0, -6.0]), np.array([12, 12]), 3)
    assert list(t) == [3.0, -4.0] and list(wk) == [True, False] and list(G) == [12, 100] and z[0] < z[1] < 4.0
    # the lists: GBM and OWN:Agree are in-sample, never in the main list
    assert dr.Param('GBM.TA15', heat.ZONES, 'model').list == 'insample' and dr.Param('OWN:Agree@60', dr.AGREE_LV, 'own', own=True).list == 'insample'
    assert dr.Param('1m:RSI14', heat.ZONES, 'osc').list == 'main' and dr.Param('OWN:Last@15', dr.LAST_LV, 'own', own=True).list == 'main'


def test_pct_codes_match_zones():
    """The 200-bin code of a value series, bucketed at bins 4, 20, 180, 196, is the zone code heat.bucket gives on every
    bar, ties on an edge included (the outer cell on both sides), NA where the value is not finite."""
    rng = np.random.default_rng(4)
    n = 20_000
    for x in (rng.integers(0, 60, n).astype(float), rng.normal(0, 1, n).round(2), rng.standard_t(3, n)):
        x[rng.uniform(size=n) < 0.02] = np.nan
        a = np.arange(n) < 14_000
        e = np.quantile(x[a][np.isfinite(x[a])], heat.ZONE_Q)
        code, E = dr.pct_code(x, a, e)
        assert np.array_equal(dr.zone_of_pct(code), heat.bucket(x, e))
        assert np.all((code == dr.PCT_NA) == ~np.isfinite(x)) and len(E) == 199 and np.all(np.diff(E) >= 0)
        assert dr.pct_code(x[:900], np.ones(900, bool))[0] is None                 # under 1,000 A values: no code
    # an HM2 value reading made through heat_xdata's Zoner is coded at once while heat_hm2.base runs (capture_raw)
    from oracle import heat_xdata as xd
    orig, store = xd.zone, {}
    with dr.capture_raw(store):
        zr = xd.Zoner(a_hi=7000)
        R1 = zr.zone('FLOW:T1', rng.normal(0, 1, 5000).round(1), family='flow', k=1)
        R5 = zr.zone('FLOW:T5', rng.standard_t(4, 2000), stale=np.arange(2000) % 50 == 0, family='flow', k=5)
        zr.zone_codes('X.O:RSI14', np.zeros(100, np.int8), [1, 2, 3, 4], 'other')
    assert xd.zone is orig and set(store) == {'FLOW:T1', 'FLOW:T5'} and store['FLOW:T5'][1] == 5
    for R in (R1, R5):
        assert np.array_equal(dr.zone_of_pct(store[R['name']][0]), R['codes'])
    assert np.all(store['FLOW:T5'][0][::50] == dr.PCT_NA)


# ---------------------------------------------------------------------------------------------- the planted separator
def _row(T, unit, h, track, mode, lst='main', rank=1):
    x = T[(T['unit'] == unit) & (T['h'] == h) & (T['track'] == track) & (T['mode'] == mode) & (T['list'] == lst) & (T['rank'] == rank)]
    assert len(x) == 1
    return x.iloc[0]


def test_planted_separator(planted):
    """Chosen on A, the planted reading is the call's top-1 take separator at 15 minutes (its 'high' zone), kept on B;
    its finer curve is a threshold at the planted 70th percentile; inside its gate the depth-2 split is the planted
    phase; the loser profile names the planted loser level; the twin (the same readings, the coin's directions flipped
    at random) finds none of it."""
    uid = f'X|level|{PLANT_UNIT}'
    T, T1 = planted[0]['T'], planted[1]['T']
    r = _row(T, uid, 15, 'right', 'take')
    assert (r['param'], r['level_label']) == ('FLOW:TB15', 'high') and r['family'] == 'flow'
    assert r['z'] > 2.5 and r['lift_A_mode'] > 8 and r['n_A'] >= 400 and r['kept'] and r['lift_B_mode'] > 8 and not r['thin']
    assert r['dir'] == 1 and r['drill'] == 'A' and r['gated_odds_B'] > r['call_odds_B']
    assert r['specific_A'] > 0.6 * r['lift_A_mode'] and r['specific_B'] > 0.6 * r['lift_B_mode']    # its own all-minutes effect is near 0
    sk = T[(T['unit'] == uid) & (T['h'] == 15) & (T['track'] == 'right') & (T['mode'] == 'skip') & (T['list'] == 'main') & (T['rank'] <= 3)]
    assert 'VOL:Jump5=down' in set(sk['param'] + '=' + sk['level_label'])
    # the curve: deciles of the 200-bin code over the call's A instances; the step at the 70th percentile
    c = [c for c in planted[0]['drill'][uid]['curves'] if c['param'] == 'FLOW:TB15' and c['h'] == 15]
    assert len(c) == 1 and c[0]['kind'] == 'value' and c[0]['drill'] == 'A' and c[0]['shape'] == 'threshold'
    lo = np.r_[0, np.ceil(c[0]['edges'])]
    odds = np.asarray(c[0]['A']['odds'])
    up, dn = odds[lo >= 140], odds[lo < 135]
    assert len(up) == 3 and up.min() > 12 and np.abs(dn).max() < 8
    assert np.asarray(c[0]['B']['odds'])[lo >= 140].mean() > 12 and c[0]['zones'][-1] == [3, 4]
    # depth 2 inside the take gate: the planted phase
    D2 = planted[0]['D2']
    p = D2[(D2['unit'] == uid) & (D2['origin_h'] == 15) & (D2['origin_track'] == 'right') & D2['path'].astype(bool)]
    assert len(p) == 1
    p = p.iloc[0]
    assert (p['p1'], p['l1'], p['param'], p['level_label']) == ('FLOW:TB15', 'high', 'POS:Phase', 'late')
    assert p['lift_A'] > 15 and p['z'] > 3 and p['path_over_call_B'] > 10
    assert not (D2['param'] == 'FLOW:TB15').any() or (D2[D2['param'] == 'FLOW:TB15']['p1'] != 'FLOW:TB15').all()    # never the gate's own base
    # the loser profile
    lp = planted[0]['drill'][uid]['losers']['15']
    top = {(w['param'], w['level']) for w in lp['wrong_levels'][:2]}
    assert ('VOL:Jump5', 'down') in top
    w = [w for w in lp['wrong_levels'] if (w['param'], w['level']) == ('VOL:Jump5', 'down')][0]
    assert w['ratio_A'] > 1.8 and w['ratio_B'] > 1.5 and w['kept'] and 'times as common' in lp['words']
    assert sum(sum(v.values()) for v in lp['table_A'].values()) > 5000
    # the twin: the same unit keys and parameters through the identical pipeline, nothing planted left
    assert planted[1]['meta']['param_names'] == planted[0]['meta']['param_names'] and planted[1]['meta']['block_units'] == planted[0]['meta']['block_units']
    assert planted[1]['meta']['label'] == 'X~twin1' and not planted[1]['meta']['real'] and not os.path.isdir(os.path.join(planted[1]['out'], 'shards'))
    r1 = _row(T1, uid, 15, 'right', 'take')
    assert r1['z'] < r['z'] - 0.5 and r1['lift_B_mode'] < r['lift_B_mode'] / 2
    f1 = T1[(T1['unit'] == uid) & (T1['param'] == 'FLOW:TB15') & (T1['list'] == 'main')]
    assert (f1['z'] < 2.5).all()
    p1 = planted[1]['D2']
    p1 = p1[(p1['unit'] == uid) & p1['path'].astype(bool) & (p1['p1'] == 'FLOW:TB15') & (p1['param'] == 'POS:Phase')]
    assert len(p1) == 0 or (p1['z'] < 3).all()
    assert np.abs(_row(T1, uid, 15, 'right', 'skip')['lift_B_mode']) < 8


def test_series_files(planted):
    """The block files and meta: the twin table has the real table's columns; every listed row carries its B
    re-measure; the summary counts hold every ranked parameter; shards (real coins only) hold every parameter."""
    T, mt = planted[0]['T'], planted[0]['meta']
    assert mt['schema'] == dr.SCHEMA_SERIES and mt['blocks_missing'] == [] and mt['units']['run'] == 2 and mt['pct']['checked'] >= 5
    assert mt['part_effects_check_max_abs_odds'] < 1e-6
    assert list(planted[1]['T'].columns) == list(T.columns)
    assert set(T['list']) == {'main'} or set(T['list']) <= {'main', 'insample'}
    assert (T.groupby(['unit', 'h', 'track', 'mode', 'list'])['rank'].max() <= dr.TOP_B).all()
    assert T['gheat_B'].notna().mean() > 0.9 and T['wd_B'].notna().all() and set(T['drill'].fillna('')) <= {'A', 'B', ''}
    assert ((T['drill'] == 'A') == ((T['rank'] <= dr.TOP_FULL) & (T['list'] == 'main'))).all()
    own_main = T[T['param'].str.startswith('OWN:Agree')]
    assert (own_main['list'] == 'insample').all()
    sh = [f for f in os.listdir(os.path.join(planted[0]['out'], 'shards'))]
    z = np.load(os.path.join(planted[0]['out'], 'shards', sh[0]))
    assert z['rec'].shape[1:] == (2, 18, 2, len(dr.ShardWriter.FIELDS)) and len(z['pid']) == z['rec'].shape[0]
    sm = dr.SummaryCounts.from_json(json.load(open(os.path.join(planted[0]['out'], 'b00000_summary.json'))))
    f = sm.frame()
    assert f['ranked'].sum() >= len(T[T['rank'] == 1]) and (f['kept'] <= f['ranked']).all()
    U = planted[0]['U']
    assert set(U['h']) == set(dr.H_ALL) and len(U) == 12 and (U['n_A'] > 0).all()


# --------------------------------------------------------------------------------------------------- no lookahead
A_COLS = ['uix', 'h', 'track', 'mode', 'list', 'rank', 'pid', 'param', 'level', 'z', 'lift_A', 't_A', 't_day_A', 't_week_A', 'G_day_A', 'G_week_A',
          'n_A', 'days_A', 'weeks_A', 'rest_n_A', 'rest_days_A', 'mean_A', 'mean_rest_A', 'right_A', 'wrong_A', 'week_weaker_A', 'Ls', 'take_A',
          'cut_A', 'specific_A']


def test_no_lookahead(splits, tmp_path, monkeypatch):
    """Every 2025 minute replaced by another walk (the readings rebuilt causally from the new minutes): the A instances
    (capped by the seeded sample), the A directions, every own instance feature and packed weight of an A instance, the
    profit proxy, sigma and ATR at every A row, and every A column of every ranked list (the A choice) and of the loser
    lists stay identical bit for bit; the B columns change."""
    monkeypatch.setattr(dr, 'A_CAP', 400)
    c1 = _noise(str(tmp_path), splits)
    c2 = _noise(str(tmp_path), splits, b_seed=99)
    b0 = A_DAYS * 1440
    assert np.array_equal(c1.m['c'][:b0], c2.m['c'][:b0]) and not np.array_equal(c1.m['c'][b0:], c2.m['c'][b0:])
    rA = c1.g.sp['A'].rows
    assert np.array_equal(rA, c2.g.sp['A'].rows) and rA.max() + 60 < b0
    r4 = c1.g240.sp['A'].rows                                      # the 240 grid's A rows end 240 minutes before 2025
    assert np.array_equal(r4, c2.g240.sp['A'].rows) and r4.max() + 240 < b0
    for k in ('pi', 'pi_c', 'kind', 'j'):
        n_h = c1.pt[k].shape[0]
        assert np.array_equal(c1.pt[k][:5][..., rA], c2.pt[k][:5][..., rA], equal_nan=k.startswith('pi'))
        if n_h == 6:
            assert np.array_equal(c1.pt[k][5][..., r4], c2.pt[k][5][..., r4], equal_nan=k.startswith('pi'))
    for k in ('sigma', 'atr'):
        assert np.array_equal(c1.pt[k][:b0], c2.pt[k][:b0], equal_nan=True)
    res = []
    for ctx in (c1, c2):
        kept, unknown = dr.prepare_units(ctx, _units(NOISE_UNITS)['coins']['X'])
        assert not unknown and len(kept) == len(NOISE_UNITS)
        insts = [dr._make_inst(ctx, u) for u in kept]
        so = dr.scan(ctx, insts, ctx.params, dr.SummaryCounts())
        res.append((insts, so, dr.rank_lists(so, insts, ctx.params)))
    (i1, s1, T1), (i2, s2, T2) = res
    assert any(x.capped for x in i1)
    for x, y in zip(i1, i2):
        a, b = x.split == 0, y.split == 0
        assert np.array_equal(x.rows[a], y.rows[b]) and np.array_equal(x.d, y.d) and np.array_equal(x.W[:, a], y.W[:, b])
        assert x.own.keys() == y.own.keys() and all(np.array_equal(x.own[k][a], y.own[k][b]) for k in x.own)
        assert x.own_edges == y.own_edges
    assert len(T1) == len(T2) > 100
    pd.testing.assert_frame_equal(T1[A_COLS].reset_index(drop=True), T2[A_COLS].reset_index(drop=True), check_exact=True)
    assert not np.allclose(T1['lift_B'], T2['lift_B'], equal_nan=True)
    for t in ('los', 'lct'):
        a, b = getattr(s1, t), getattr(s2, t)
        assert np.array_equal(a.z, b.z) and np.array_equal(a.p, b.p)
        assert np.array_equal(a.r[..., [dr.LI['ratio_A'], dr.LI['t_A'], dr.LI['n_A']]], b.r[..., [dr.LI['ratio_A'], dr.LI['t_A'], dr.LI['n_A']]], equal_nan=True)


def test_live_own_levels(noise):
    """The live reader's own levels (own_levels_at: a window of minutes that ends at the decision close, the call's
    fires in it) equal the history's codes at every instance of the last days: Since, Order, Last@H, BarBody, Step
    exactly, BarRange and BarVol (Wilder's ATR started inside the window) on 98% or more."""
    ctx = noise[0]['ctx']
    for key in ('1m:R3=very high', '15m:R3=very high'):
        u = dr._unit('X', 'level', key, 1, 'test')
        u['rows'] = dr.unit_rows(ctx, u)
        x = dr._make_inst(ctx, u)
        hist = dr.own_history_levels(ctx, x)
        meta = {'k': x.k, 'dir': x.d.tolist(), 'own_edges': x.own_edges}
        sel = np.flatnonzero(x.rows >= ctx.m['n'] - (3 if x.k == 1 else 20) * 1440)
        W = max(3000, 300 * x.k)
        agree, tot = {}, {}
        for j in sel:
            i = int(x.rows[j])
            a = i - W + 1
            win = {kk: np.asarray(ctx.m[kk])[a:i + 1] for kk in ('o', 'h', 'l', 'c', 'v', 'gap')}
            live = dr.own_levels_at(u['rows'][(u['rows'] >= a) & (u['rows'] <= i)] - a, win, meta)
            for nm, lv in live.items():
                tot[nm] = tot.get(nm, 0) + 1
                agree[nm] = agree.get(nm, 0) + (lv == hist[nm][j])
        assert len(sel) > 15 and {'OWN:Since', 'OWN:Order', 'OWN:Last@15', 'OWN:Last@240', 'OWN:BarBody', 'OWN:BarRange', 'OWN:Step'} <= set(tot)
        for nm in tot:
            share = agree[nm] / tot[nm]
            assert share >= (0.98 if nm in ('OWN:BarRange', 'OWN:BarVol') else 1.0), (key, nm, share)


# ------------------------------------------------------------------------------------------------------ pure noise
def test_pure_noise_nothing_beyond_twins(noise):
    """A random walk and its coin-flip twin through the identical pipeline: the A-chosen top-1 separators keep their
    sign on B about half the time on both, t_B >= 2 is rare on both (a large B t only where the B sample is thin, as
    marked), and the real series' counts sit beside the twin's."""
    st = {}
    for tw in (0, 1):
        T = noise[tw]['T']
        t1 = T[(T['rank'] == 1) & (T['list'] == 'main')]
        assert len(t1) >= 150
        st[tw] = {'kept': t1['kept'].mean(), 'tb2': t1['tb2'].mean(), 'big': ((t1['t_B_mode'].abs() >= 3.5) & ~t1['thin']).mean(), 'zmax': t1['z'].max(),
                  'sd': np.nanstd(t1['t_day_B'] * np.where(t1['mode'] == 'take', 1, -1))}
    for tw in (0, 1):
        assert 0.3 <= st[tw]['kept'] <= 0.7 and st[tw]['tb2'] <= 0.12 and st[tw]['big'] <= 0.01 and 0.6 <= st[tw]['sd'] <= 1.6, (tw, st)
    assert abs(st[0]['kept'] - st[1]['kept']) <= 0.2 and abs(st[0]['tb2'] - st[1]['tb2']) <= 0.1 and st[0]['zmax'] <= st[1]['zmax'] + 1.5, st


# ------------------------------------------------------------------------------------------- the league and the pack
def test_league_files_and_gate_merge(noise, tmp_path):
    """The league over a coin and its twin: every file; the chance table real against the twins; the gate rows in
    their own file (kinds gate / gate2, the pack horizons, at most PER_CALL rows per call and PACK_LISTS per list; the
    calls the bot loads in the take / skip lists, the others in their own list); merged into hm2_pack.json with every
    non-gate row byte-identical and the earlier gate rows replaced; --merge-only re-applies them to a rewritten pack; a
    pack whose non-gate rows changed since the units were built stops the league."""
    tmp = str(tmp_path)
    pk, lm, hd = os.path.join(tmp, 'hm2_pack.json'), os.path.join(tmp, 'hm2_live_meta.json'), os.path.join(tmp, 'hm2')
    os.makedirs(hd)
    dr._dump(PACK, pk)
    dr._dump({'schema': 'test'}, lm)
    with open(os.path.join(hd, 'league.md'), 'w') as f:
        f.write('# HM2 league\n')
    out = os.path.join(tmp, 'league')
    S = dr.league(noise['dir'], noise['units'], out, stamp='test', hm2_pack=pk, hm2_live_meta=lm, hm2_league=hd, log=NOOP)
    for f in ('league.md', 'cards.md', 'summary.json', 'cards.json.gz', 'gate_rows.json', 'gates_all.csv.gz', 'profiles_pack.json.gz'):
        assert os.path.getsize(os.path.join(out, f)) > 0, f
    assert S['schema'] == dr.SCHEMA_LEAGUE and set(S['series']) == {'X', 'X~twin1'} and not any(v['missing'] for v in S['coverage'].values())
    ch = S['chance']['15|right|take|main']['pooled']
    assert ch['real']['units'] == len(NOISE_UNITS) and ch['twins']['kept']['sets'] == 1
    assert '15|right|take' in S['persistence'] and S['cards'] > 0 and S['columns'] > 0
    G = json.load(open(os.path.join(out, 'gate_rows.json')))
    rows = G['rows']
    assert rows and G['part3']['schema'] == dr.SCHEMA_GATES and G['part3']['list_rule'] == dr.PACK_LISTS
    df = pd.DataFrame(rows)
    assert set(df['kind']) <= set(dr.GATE_KINDS) and set(df['h']) <= set(dr.PACK_H) and set(df['coin']) == {'X'}
    g1 = df[df['kind'] == 'gate']
    unit = g1['when'].map(lambda w: w['unit'])
    assert (g1.groupby([g1['h'], g1['list'], unit]).size() <= dr.PER_CALL).all()
    assert (g1.groupby(['h', 'list']).size() <= g1.groupby(['h', 'list'])['list'].first().map(dr.PACK_LISTS)).all()
    assert (g1[g1['list'] != 'other_units']['tier'] <= 2).all() and (g1[g1['list'] == 'other_units']['tier'] > 2).all()
    assert all(len(c) == 1 and isinstance(c[0][1], list) for c in g1['conds']) and not g1['live_ready'].any()
    assert set(g1['profit_unit']) <= {'pi_c', 'pi_bps'} and ((g1['h'] == 240) == (g1['profit_unit'] == 'pi_bps')).all()
    # (review fixes) the twins' max mark per list (same tier filter); depth-2 paths ranked by their own gate heat
    assert set(g1['twin_mark']) <= {'max', ''} and (g1['twin_mark'] == 'max').any() and g1['above_twin_p99'].isna().all()
    g2 = df[df['kind'] == 'gate2']
    for _, y in g2.groupby('h'):
        gh = y['gheat_B'].astype(float).to_numpy()
        assert (np.diff(gh[np.isfinite(gh)]) <= 1e-12).all()
    assert G['part3']['hm2_tier2_sha256'] == hl.tier2_sha(PACK)
    P = json.load(open(pk))
    keep = [r for r in PACK['rows'] if r['kind'] not in dr.GATE_KINDS]
    assert [r for r in P['rows'] if r['kind'] not in dr.GATE_KINDS] == keep and 'old gate row' not in {r['key'] for r in P['rows']}
    assert len([r for r in P['rows'] if r['kind'] in dr.GATE_KINDS]) == len(rows) and P['part3']['schema'] == dr.SCHEMA_GATES
    assert hl.non_gate_sha(P) == hl.non_gate_sha(PACK)
    assert 'part3' in json.load(open(lm)) and 'Part 3' in open(os.path.join(hd, 'league.md')).read()
    # gate_rows.json carries the live meta's part3 block too; the pack names the live meta it goes with
    assert G['live'] == json.load(open(lm))['part3'] and G['live']['coins'].get('X')
    assert P['live_meta_sha256'] == hashlib.sha256(open(lm, 'rb').read()).hexdigest()
    # the HM2 league rewrites the pack and the live meta: --merge-only puts the gate rows and the part3 block back
    dr._dump({'schema': 'test', 'rows': keep}, pk)
    dr._dump({'schema': 'test'}, lm)
    dr.main(['league', '--out', out, '--hm2-pack', pk, '--hm2-live-meta', lm, '--merge-only', os.path.join(out, 'gate_rows.json')])
    P2 = json.load(open(pk))
    assert [r for r in P2['rows'] if r['kind'] not in dr.GATE_KINDS] == keep and len(P2['rows']) == len(keep) + len(rows)
    assert json.load(open(lm))['part3'] == G['live'] and P2['live_meta_sha256'] == hashlib.sha256(open(lm, 'rb').read()).hexdigest()
    # a parity run (live_ready only) leaves tier 2 alone: the league runs
    dr._dump({'schema': 'test', 'rows': [dict(r, live_ready=True, live_ready_why=[]) for r in keep]}, pk)
    dr.league(noise['dir'], noise['units'], os.path.join(tmp, 'league-lr'), hm2_pack=pk, log=NOOP)
    # a changed non-gate row: tier 2 would be stale
    dr._dump({'schema': 'test', 'rows': [dict(keep[0], odds=9.9)]}, pk)
    with pytest.raises(SystemExit, match='changed since drill-units'):
        dr.league(noise['dir'], noise['units'], out, hm2_pack=pk, log=NOOP)
    # no drill series at all (every drill job failed): the league stops and the pack's gate rows stay
    dr._dump(P, pk)
    empty = os.path.join(tmp, 'no-series')
    os.makedirs(empty)
    with pytest.raises(SystemExit, match='no drill series outputs'):
        dr.league(empty, noise['units'], os.path.join(tmp, 'league-empty'), hm2_pack=pk, log=NOOP)
    assert json.load(open(pk)) == P


def test_build_units(tmp_path):
    """The unit list: tier 1 the HM1 packs' calls (singles as levels, cells with their `when` and conds, perp pairs at
    240 only), tier 2 the HM2 pack's non-gate rows, tier 3 every other HM1 level by its A numbers at 15 minutes (never a
    B number); a key listed twice runs once with every source; twins' rows are not units; the sha is stable; the twin
    fallback's subset is fixed; DOGE is refused."""
    tmp = str(tmp_path)
    d = pd.DataFrame([{'coin': c, 'kind': 'single', 'key': k, 'h': h, 'dir': 1, 'n_A': nA, 'n_B': 10 if c == 'BTC' else 1, 'odds_A': oA}
                      for c in ('BTC', 'BTC~twin1') for k, nA, oA in (('1m:A=very high', 100, 1.0), ('1m:B=low', 50, 4.0), ('5m:C=high', 300, 1.0),
                                                                          ('1m:D=very low', 10, 0.5))
                      for h in (15, 60)])
    d.loc[(d['key'] == '5m:C=high') & (d['h'] == 60), 'n_B'] = 999                 # a B number never moves the order
    dp = os.path.join(tmp, 'direction_all.csv.gz')
    d.to_csv(dp, index=False)
    pdir = os.path.join(tmp, 'packs')
    os.makedirs(pdir)
    dr._dump({'rows': [{'coin': 'BTC', 'h': 15, 'key': '1m:A=very high', 'aliases': ['1m:A2=very high']}]}, os.path.join(pdir, 'traded_pack.json'))
    dr._dump({'rows': [{'coin': 'BTC', 'h': 15, 'kind': 'pair', 'key': '1m:B=low | 1m:E sign=above 0', 'when': '1m:B=low',
                        'conds': [['1m:E sign', 'above 0']], 'aliases': []},
                       {'coin': 'ETH', 'h': 15, 'kind': 'pair', 'key': 'x | y=z', 'when': 'x', 'conds': [['y', 'z']]}]}, os.path.join(pdir, 'pair_pack.json'))
    dr._dump({'rows': [{'coin': 'BTC', 'h': 60, 'kind': 'pair', 'key': 'p60 | q=r', 'when': '1m:A=very high', 'conds': [['q', 'r']]},
                       {'coin': 'BTC', 'h': 240, 'kind': 'triple', 'key': 'p240 | q=r | s=t', 'when': '1m:A=very high', 'conds': [['q', 'r'], ['s', 't']]}]},
             os.path.join(pdir, 'perp_pair_pack.json'))
    pack = {'rows': [{'coin': 'BTC', 'kind': 'pair', 'key': 'F=x & G=y', 'conds': [['F', ['x']], ['G', ['y']]]},
                     {'coin': 'BTC', 'kind': 'model', 'key': 'GBM.TA15=very high'}, {'coin': 'BTC', 'kind': 'gate', 'key': 'g'}]}
    U = dr.build_units(dp, '', pdir, pack, coins=['BTC'], chart=False)
    us = U['coins']['BTC']
    assert U['schema'] == dr.SCHEMA_UNITS and U['hm2_nongate_sha256'] == hl.non_gate_sha(pack) and not U['chart']['loaded']
    assert [u['tier'] for u in us] == sorted(u['tier'] for u in us) and [u['order'] for u in us] == list(range(len(us)))
    ids = [u['id'] for u in us]
    assert ids[:3] == ['BTC|level|1m:A=very high', 'BTC|cell|1m:B=low | 1m:E sign=above 0', 'BTC|cell|p240 | q=r | s=t']
    assert ids[3:5] == ['BTC|hm2|F=x & G=y', 'BTC|model|GBM.TA15=very high'] and not any('|g' == i[-2:] for i in ids)
    assert ids[5:] == ['BTC|level|5m:C=high', 'BTC|level|1m:B=low', 'BTC|level|1m:D=very low']        # n_A x odds_A at 15: 300, 200, 5
    a = us[0]
    assert a['source'] == ['direction_all', 'traded_pack.json'] and a['aliases'] == ['1m:A2=very high'] and a['league']['60']['n_B'] == 10
    assert us[1]['conds'] == [['1m:E sign', ['above 0']]] and us[3]['conds'] == [['F', ['x']], ['G', ['y']]]
    assert dr.build_units(dp, '', pdir, pack, coins=['BTC'], chart=False)['sha256'] == U['sha256']
    q = dr.quarter_subset(us)
    assert q == dr.quarter_subset(us) and {u['id'] for u in us if u['tier'] < 3} <= q and len(q) == 5 + 1
    with pytest.raises(SystemExit, match='DOGE'):
        dr.build_units(dp, '', pdir, pack, coins=['BTC', 'DOGE'])


def test_parts_blocks_and_workers(noise, tmp_path, monkeypatch):
    """--part splits the unit list into disjoint parts that cover it; small blocks run in fork workers and as --blocks
    reruns into one out dir give the same tables and summary counts as one block in one process; a twin on the fixed
    quarter runs the tier 1 and 2 units and the seeded quarter of tier 3."""
    ctx = noise[0]['ctx']
    monkeypatch.setattr(dr, 'BLOCK_UNIT_DAYS', 120)
    kept, _ = dr.prepare_units(ctx, _units(NOISE_UNITS)['coins']['X'])
    parts = [sum(dr.plan_blocks(ctx, kept, (i, 2)), []) for i in (0, 1)]
    assert sorted(parts[0] + parts[1]) == list(range(len(kept))) and parts[0] and parts[1]
    assert dr._parse_blocks('0-2,5') == [0, 1, 2, 5] and dr._parse_blocks('') is None
    out = str(tmp_path / 'X')
    U = _units(NOISE_UNITS, PACK)
    m1 = dr.run_series('X', '', out, U, procs=2, ctx=ctx, blocks=[1, 2], log=NOOP)
    assert m1['blocks_total'] == len(NOISE_UNITS) and m1['blocks_missing'] == [0, 3, 4]
    m2 = dr.run_series('X', '', out, U, procs=1, ctx=ctx, blocks=[0, 3, 4], log=NOOP)
    assert m2['blocks_missing'] == [] and len(m2['blocks_done']) == len(NOISE_UNITS)
    key = ['unit', 'h', 'track', 'mode', 'list', 'rank']
    a = _read(out, '_top.csv.gz').sort_values(key).reset_index(drop=True)
    b = noise[0]['T'].sort_values(key).reset_index(drop=True)
    cols = key + ['param', 'level', 'z', 'lift_A', 'lift_B', 't_B', 'gheat_B', 'specific_B', 'deff_day_A', 'alias_of']
    pd.testing.assert_frame_equal(a[cols], b[cols])
    s1 = dr.SummaryCounts()
    for f in os.listdir(out):
        if f.endswith('_summary.json'):
            s1.merge(dr.SummaryCounts.from_json(json.load(open(os.path.join(out, f)))))
    s0 = dr.SummaryCounts.from_json(json.load(open(os.path.join(noise[0]['out'], 'b00000_summary.json'))))
    assert s1.c == s0.c
    mq = dr.run_series('X', '', str(tmp_path / 'tq'), U, twin=1, twin_units='quarter', procs=1, ctx=noise[1]['ctx'], log=NOOP)
    q = dr.quarter_subset(U['coins']['X'])
    assert mq['twin_units'] == 'quarter' and mq['units']['listed'] == len(q) and mq['block_units'] and set(sum(mq['block_units'], [])) <= q


# ----------------------------------------------------------------------------------- the CLI on the engine's readings
def test_cli_on_engine_readings(tmp_path, monkeypatch):
    """The command line on a short synthetic coin (on a 0.01 price grid) with the engine's own readings
    (heat_hm2.base, --no-xdata): units from a direction table, an HM1 pair pack and an HM2 pack; coin (the engine's
    value series rebuilt into 200-bin codes that bucket back to every zone reading's codes), the bench on the twin, and
    the live parity of the own conditions of a gate row."""
    A, B = 40, 15
    start = heat.HEAT_END - (A + B) * DAY
    monkeypatch.setattr(heat, 'SPLITS', {'A': (start, start + A * DAY), 'B': (start + A * DAY, heat.HEAT_END)})
    tmp = str(tmp_path)
    r, w, v, f = _walk((A + B) * 1440, 3)
    c = np.round(30000 * np.exp(np.cumsum(r)), 2)
    o = np.r_[c[0], c[:-1]]
    csv = os.path.join(tmp, 'btc.csv')
    pd.DataFrame({'ts': start + np.arange(len(c)) * MIN, 'o': o, 'h': np.maximum(o, c) + 0.01 * np.round(w * 1e4), 'l': np.minimum(o, c) - 0.01 * np.round(w * 1e4),
                  'c': c, 'v': v, 'tb': v * f}).to_csv(csv, index=False)
    keys = ['1m:RSI14=very low', '5m:RSI14=very high', '15m:RSI14=low (falling in)', '1m:CCI14=very high']
    dp = os.path.join(tmp, 'direction_all.csv')
    pd.DataFrame([{'coin': 'BTC', 'kind': 'single', 'key': k, 'h': 15, 'dir': 1, 'n_A': 100 - i, 'n_B': 10, 'odds_A': 1.0} for i, k in enumerate(keys)]).to_csv(dp, index=False)
    pdir = os.path.join(tmp, 'packs')
    os.makedirs(pdir)
    dr._dump({'rows': [{'coin': 'BTC', 'h': 15, 'kind': 'pair', 'key': '1m:RSI14=very low | 15m:AO sign=above 0', 'when': '1m:RSI14=very low',
                        'conds': [['15m:AO sign', 'above 0']], 'aliases': []}]}, os.path.join(pdir, 'pair_pack.json'))
    hp = os.path.join(tmp, 'hm2_pack.json')
    dr._dump({'rows': [{'coin': 'BTC', 'kind': 'pair', 'key': '15m:AO sign=above 0 & 1m:CCI14 sign=below 0',
                        'conds': [['15m:AO sign', ['above 0']], ['1m:CCI14 sign', ['below 0']]]}]}, hp)
    up = os.path.join(tmp, 'units.json')
    dr.main(['units', '--direction', dp, '--packs', pdir, '--hm2-pack', hp, '--out', up])
    U = json.load(open(up))
    assert [u['tier'] for u in U['coins']['BTC']] == [1, 2, 3, 3, 3, 3] and U['coins']['ETH'] == []
    out = os.path.join(tmp, 'BTC')
    dr.main(['coin', '--asset', 'BTC', '--csv', csv, '--no-xdata', '--units', up, '--out', out, '--procs', '1', '--no-chart'])
    mt = json.load(open(os.path.join(out, 'meta.json')))
    assert mt['units']['run'] == 6 and not mt['units']['unknown'] and mt['blocks_missing'] == [] and mt['pct']['checked'] > 300
    assert mt['league_check']['checked'] == 4 and mt['params'] > 500 and mt['part_effects_check_max_abs_odds'] < 1e-6
    assert mt['chart'] == {'loaded': False, 'why': 'off (--no-chart)'}
    T = _read(out, '_top.csv.gz')
    ids = {u['id'] for u in U['coins']['BTC']}
    assert set(_read(out, '_units.csv.gz')['unit']) == ids and {'BTC|level|1m:RSI14=very low', 'BTC|level|1m:CCI14=very high'} <= set(T['unit']) <= ids
    assert T[T['unit'] == 'BTC|level|1m:RSI14=very low']['param'].map(lambda p: p.split(':')[1].split(' ')[0] != 'RSI14' if p.startswith('1m:') else True).all()
    d = _drill(out)['BTC|level|1m:RSI14=very low']
    assert 'OWN:Depth' in d['own_edges'] and d['k'] == 1
    bo = os.path.join(tmp, 'bench')                                       # the bench on the twin: the twin path of the CLI
    dr.main(['bench', '--asset', 'BTC', '--csv', csv, '--no-xdata', '--units', up, '--out', bo, '--procs', '1', '--n-units', '3', '--twin', '1',
             '--no-chart'])
    bj = json.load(open(os.path.join(bo, 'bench.json')))
    assert bj['units_run'] == 3 and bj['ms_per_instance_param'] > 0 and bj['projected_minutes']['1'] >= bj['projected_minutes']['3']
    assert bj['workers'] == {'1': 1, '2': 1, '3': 1}                       # --procs 1: one worker whatever the blocks
    assert bj['unit_days'] > 0 and bj['instances_total'] >= bj['instances'] and bj['units_total'] >= bj['units_run']
    assert bj['projected_minutes']['1'] == pytest.approx(bj['base_minutes'] + bj['worker_minutes'], abs=0.11) and bj['parts_needed'] >= 1
    assert bj['units_unknown'] == 0 and bj['units_unknown_eg'] == []                # (W6) the whole unit set's unknown keys
    m1 = json.load(open(os.path.join(bo, 'meta.json')))
    assert m1['label'] == 'BTC~twin1' and not m1['real'] and m1['league_check'] is None and not os.path.isdir(os.path.join(bo, 'shards'))
    own = lambda names: [p for p in names if p.startswith('OWN:')]
    assert own(m1['param_names']) == own(mt['param_names']) and abs(m1['params'] - mt['params']) <= 0.1 * mt['params']   # HM2's copy merge runs per series
    gp = os.path.join(tmp, 'gate_rows.json')
    dr._dump({'rows': [{'coin': 'BTC', 'h': 15, 'kind': 'gate', 'key': 'k', 'when': {'unit': 'BTC|level|1m:RSI14=very low'},
                        'conds': [['OWN:Since', ['4-10']], ['OWN:Last@15', ['right']], ['OWN:BarBody', ['0.2 to 0.6']], ['OWN:Order', ['1']]]}]}, gp)
    po = os.path.join(tmp, 'parity')
    dr.main(['parity', '--asset', 'BTC', '--csv', csv, '--no-xdata', '--units', up, '--gates', gp, '--out', po, '--days', '5'])
    pj = json.load(open(os.path.join(po, 'parity.json')))
    assert pj['rows'][0]['minutes'] > 50 and pj['rows'][0]['parity'] == 1.0


def test_gbm_readings(noise, tmp_path, monkeypatch):
    """The GBM readings come from Part 2's gbm_codes.npz (the grid's t0 and n must match), are k = 1 zone readings of
    the in-sample list, and a model unit fires at their zone onsets."""
    ctx = noise[0]['ctx']
    rng = np.random.default_rng(2)
    a = np.repeat(rng.integers(0, 5, ctx.m['n'] // 30 + 1), 30)[:ctx.m['n']].astype(np.int8)
    a[:500] = -1
    b = np.roll(a, 7)
    np.savez_compressed(tmp_path / 'gbm_codes.npz', t0=np.int64(ctx.m['t0']), n=np.int64(ctx.m['n']), **{'GBM.TA15': a, 'GBM.ALL15': b})
    G = dr.load_gbm(ctx, str(tmp_path))
    assert [R['name'] for R in G] == ['GBM.ALL15', 'GBM.TA15'] and np.array_equal(G[1]['codes'], a) and G[1]['k'] == 1
    assert all(dr.Param(R['name'], R['levels'], 'model', R['k'], R['codes'], R=R).list == 'insample' for R in G)
    monkeypatch.setattr(ctx, 'gbm_byname', {R['name']: R for R in G})
    rows = dr.unit_rows(ctx, dr._unit('X', 'model', 'GBM.TA15=very high', 2, 'test'))
    assert np.array_equal(rows, heat.level_events(G[1], 4, 0)) and len(rows) > 100
    np.savez_compressed(tmp_path / 'gbm_codes.npz', t0=np.int64(ctx.m['t0']), n=np.int64(ctx.m['n'] + 1), **{'GBM.TA15': a})
    with pytest.raises(SystemExit, match='another grid'):
        dr.load_gbm(ctx, str(tmp_path))


def test_chart_own_columns():
    """(Part 4's review) A chart unit's own shape columns come from the catalogue joined by (frame, pattern, event
    row): another pattern's instance on the same bar (a collision) and the same frame name on another timeframe never
    leak in; the quintiles are the pattern's own A instances'; tdist and age have fixed levels; a row with no catalogue
    entry is NA."""
    rng = np.random.default_rng(8)
    ev = np.arange(100, 100 + 15 * 200, 15)
    hs = rng.uniform(1, 2, len(ev))
    cat = pd.concat([pd.DataFrame({'frame': '60m:z4', 'pattern': 'HS', 'event_row': ev, 'instance': np.arange(len(ev)), 'height': hs,
                                   'tdist': np.resize([-1, 0.5, 1.5, 3, 5], len(ev)), 'age': np.resize([0, 2, 5, 10, 20, 25], len(ev))}),
                     pd.DataFrame({'frame': '60m:z4', 'pattern': 'DT', 'event_row': ev, 'instance': 10_000 + np.arange(len(ev)), 'height': hs + 50,
                                   'tdist': 9.0, 'age': 0}),
                     pd.DataFrame({'frame': 'z4', 'tf': '15m', 'pattern': 'HS', 'event_row': ev + 1, 'instance': 20_000 + np.arange(len(ev)), 'height': -5.0,
                                   'tdist': 9.0, 'age': 0})], ignore_index=True)
    rows = np.r_[ev, 7]
    rowsA = ev[:150]
    out = dr.chart_own(cat, '60m', 'z4', 'HS', rows, rowsA)
    e = np.quantile(hs[:150], [0.2, 0.4, 0.6, 0.8])
    assert np.array_equal(out['OWN:chart.height'][0][:-1], np.searchsorted(e, hs, 'right')) and out['OWN:chart.height'][1] == pytest.approx(list(e))
    assert out['OWN:chart.height'][0][-1] == -1 and np.bincount(out['OWN:chart.height'][0][:150]).tolist() == [30] * 5
    assert out['OWN:chart.tdist'][0][:5].tolist() == [0, 1, 2, 3, 4] and out['OWN:chart.age'][0][:6].tolist() == [0, 1, 2, 3, 4, 4]
    assert dr._chart_parts('60m:CHART.z4.HS=break up') == ('60m', 'z4', 'HS') and dr._chart_parts('15m:CHART.K.LMW.HS=formed') == ('15m', 'K', 'LMW.HS')
    assert dr._chart_parts('60m:CHART.z4.HS.state=formed') is None and dr._chart_parts('60m:CHART.z4.p.height=q1') is None


def test_twin_marks_same_units():
    """(review fix) Under the twin fallback the twins' max is over the seeded subset's twin rows, only the real rows of
    that subset are marked against it, and the real coin's other units carry the twins' p99 mark instead; without the
    fallback every real row is marked against the max over all twin rows."""
    real = pd.DataFrame({'gheat_B': [5.0, 3.0, 0.5, 9.0], 'subset': [True, True, False, False]})
    tw = pd.DataFrame({'gheat_B': np.r_[np.linspace(0, 4, 100), 8.0], 'subset': np.r_[np.ones(100, bool), False]})
    am, ap, mk = dr.twin_marks(real, tw, same_units=True)
    assert list(mk) == ['max', 'max', 'p99', 'p99'] and list(am) == [True, False, None, None]
    assert list(ap) == [None, None, False, True]
    am, ap, mk = dr.twin_marks(real, tw, same_units=False)
    assert list(mk) == ['max'] * 4 and list(am) == [False, False, False, True] and all(x is None for x in ap)
    assert list(dr.twin_marks(real, tw.iloc[:0])[2]) == [''] * 4


def test_ta_cards_counts():
    """A TA card line: each unit once (its first row), kept with t_B >= 2 on any of its rows, the median B lift and the
    levels of the first rows; the twins' share per seed; a line the twins alone have; rows below the top 5 or off the
    main list left out; the shape from the real series' curves only, a tie to the first name."""
    def r(twin, unit, h, kept, tb2, lift, lv, param='p1', rank=1, lst='main'):
        return {'list': lst, 'rank': rank, 'unit_fn': 'RSI', 'track': 'right', 'mode': 'take', 'param': param, 'twin': twin, 'asset': 'X',
                'unit': unit, 'h': h, 'kept': kept, 'tb2': tb2, 'lift_B_mode': lift, 'level_label': lv}
    T = pd.DataFrame([r(0, 'u1', 15, True, True, 1.2, 'high'), r(0, 'u1', 60, False, False, 0.5, 'low'), r(0, 'u2', 15, False, True, 0.8, 'mid'),
                      r(0, 'u3', 15, True, True, 9.0, 'x', rank=6), r(0, 'u3', 15, True, True, 9.0, 'x', lst='other'),
                      r(1, 'u1', 15, True, True, 1.0, 'high'), r(1, 'u2', 15, False, False, 1.0, 'mid'), r(2, 'u1', 15, False, True, 1.0, 'high'),
                      r(1, 'u1', 15, True, True, 1.0, 'high', param='p2')])
    curves = {('X', 'u1', 'p1', 15): {'shape': 'tail'}, ('X', 'u2', 'p1', 15): {'shape': 'slope'},
              ('X~twin1', 'u1', 'p1', 15): {'shape': 'tail'}, ('X~twin1', 'u2', 'p1', 60): {'shape': 'tail'}}
    C = dr.ta_cards(T, curves)
    assert len(C) == 1 and C[0]['card'] == 'RSI' and C[0]['units_real'] == 2
    assert set(C[0]['tracks']) == {f'{t}|{m}' for t in ('right', 'profit', 'move') for m in dr.MODES}
    p1, p2 = C[0]['tracks']['right|take']
    assert (p1['param'], p1['units'], p1['kept_tb2_share'], p1['median_lift_B']) == ('p1', 2, 0.5, pytest.approx(1.0))
    assert p1['levels'] == ['high', 'mid'] and p1['unit_ids'] == ['u1', 'u2'] and p1['shape'] == 'slope'
    assert p1['twins'] == {'median': 0.25, 'min': 0.0, 'max': 0.5, 'sets': 2}
    assert (p2['param'], p2['units'], p2['kept_tb2_share'], p2['shape'], p2['twins']['sets']) == ('p2', 0, None, None, 1)


def test_league_check_and_cap(noise):
    """For singles the uncapped n_A, n_B and the direction (the sign of the A odds over the base, heat's d_odds rule;
    the 240 grid at 240) equal heat.Grid.full's on the same events, so check_league finds no difference; the A cap is
    an exact, seeded, repeatable uniform sample and leaves a unit under it untouched."""
    ctx = noise[0]['ctx']
    units, insts = [], {}
    for key in ('1m:R3=very high', '1m:R10=low (falling in)', '15m:R3=very high'):
        u = dr._unit('X', 'level', key, 3, 'test')
        R, lv, side = dr.parse_key(ctx, key)
        ev = heat.level_events(R, lv, side)
        lg = {}
        for H in dr.H_ALL:
            g = ctx.g240 if H == 240 else ctx.g
            with (hm.h240() if H == 240 else contextlib.nullcontext()):
                fa = g.full(g.in_split(ev, 'A'), 'A')
                fb = g.full(g.in_split(ev, 'B'), 'B')
            lg[str(H)] = {'dir': int(np.sign(fa[H]['edge_p'])), 'n_A': fa['n'], 'n_B': fb['n']}
        u['league'] = lg
        units.append(u)
        insts[u['id']] = dr.split_instances(ctx, u, ev)
    lc = dr.check_league(units, insts, ctx)
    assert lc['checked'] == 18 and lc['n_differ'] == 0 and lc['d_differ'] == 0, lc
    rA = np.sort(np.random.default_rng(1).choice(10 ** 6, 40_000, replace=False))
    a, b = dr._cap(rA, 'k'), dr._cap(rA, 'k')
    assert len(a) == dr.A_CAP and np.array_equal(a, b) and np.all(np.diff(a) > 0) and np.isin(a, rA).all()
    assert not np.array_equal(a, dr._cap(rA, 'other key')) and dr._cap(rA[:dr.A_CAP], 'k') is not None
    assert np.array_equal(dr._cap(rA[:dr.A_CAP], 'k'), rA[:dr.A_CAP])


def test_chart_units_through_part4(noise, monkeypatch):
    """Part 4's builder (oracle.heat_patterns.series_readings, faked here): its event readings become chart units (with
    the engine's sample floors) and parameters of the other units; a chart unit's own shape columns come from the
    catalogue at its own event rows and never split it by its own frame's readings; a failing builder leaves the drill
    running without chart readings, the reason in meta."""
    import copy
    import sys
    import types
    ctx = copy.copy(noise[0]['ctx'])
    del ctx.chart
    rng = np.random.default_rng(12)
    nb = ctx.m['n'] // 15
    codes = np.where(rng.uniform(size=nb) < 0.03, 2, 0).astype(np.int8)
    R = {'name': '15m:CHART.z4.HS', 'k': 15, 'codes': codes, 'levels': ['none', 'formed', 'break up', 'break down', 'retest', 'failure', 'target'],
         'base': '15m:CHART.z4', 'every': True, 'family': 'chart'}
    ev = np.flatnonzero(codes == 2) * 15 + 14
    cat = pd.DataFrame({'frame': '15m:z4', 'pattern': 'HS', 'event_row': ev, 'instance': np.arange(len(ev)), 'height': rng.uniform(1, 3, len(ev)),
                        'span': rng.integers(10, 60, len(ev)), 'tdist': rng.uniform(-1, 5, len(ev)), 'age': 0})
    fake = types.ModuleType('oracle.heat_patterns')
    fake.series_readings = lambda c: ([R], cat)
    monkeypatch.setitem(sys.modules, 'oracle.heat_patterns', fake)
    info = dr.chart_readings(ctx)
    assert info == {'loaded': True, 'how': 'series_readings', 'readings': 1, 'catalogue_rows': len(ev)}
    ctx.params = dr.series_params(ctx)
    names = [p.name for p in ctx.params]
    assert '15m:CHART.z4.HS' in names and 'OWN:chart.height' in names and dr.Param('x', ['a'], 'chart').list == 'main'
    us = dr.chart_units(ctx, 'X')
    assert [u['key'] for u in us] == ['15m:CHART.z4.HS=break up'] and us[0]['kind'] == 'chart' and us[0]['tier'] == 3
    u = dict(us[0], rows=dr.unit_rows(ctx, us[0]))
    assert np.array_equal(u['rows'], ev)
    x = dr._make_inst(ctx, u)
    assert x.k == 15 and x.bases == {'15m:CHART.z4'} and (x.own['OWN:chart.height'] >= 0).all() and len(x.own_edges['OWN:chart.height']) == 4
    assert (x.own['OWN:chart.age'] == 0).all() and dr._unit_fn(ctx, u) == 'chart:HS'
    o = dr.scan(ctx, [x], ctx.params)
    T = dr.rank_lists(o, [x], ctx.params)
    assert len(T) and '15m:CHART.z4.HS' not in set(T['param'])
    fake.series_readings = lambda c: (_ for _ in ()).throw(RuntimeError('boom'))
    c2 = copy.copy(noise[0]['ctx'])
    info = dr.chart_readings(c2, log=NOOP)
    assert info == {'loaded': False, 'why': 'RuntimeError: boom'} and c2.chart == [] and c2.chart_cat is None


def test_gate_live_ready(tmp_path):
    """live_ready on the gate rows (the drill-parity-commit job): own conditions from the coin's drill parity (by key and
    h, at least 99.5% of the checked minutes), the other conditions' readings from HM2's parity, a call from hm2_pack.json
    live ready there, and the feeds the readings need; every other row stays byte-identical and twins' files are
    ignored."""
    lv = {'coin': 'BTC', 'h': 15, 'kind': 'pair', 'key': 'K1', 'readings': ['15m:A', '1m:B'], 'live_ready': True}
    when = {'key': '1m:X=low', 'kind': 'level', 'unit': 'BTC|level|1m:X=low'}
    g = lambda key, conds, h=15, coin='BTC', w=when, kind='gate': {'coin': coin, 'h': h, 'kind': kind, 'key': key, 'when': w, 'conds': conds,  # noqa: E731
                                                                   'live_ready': False, 'live_ready_why': ['parity not run']}
    pack = {'rows': [lv, g('G1', [['OWN:Since', ['4-10']]]), g('G2', [['15m:RSI14', ['high']]]),
                     g('G3', [['OWN:Order', ['1']]], w={'key': 'K1', 'kind': 'hm2', 'unit': 'BTC|hm2|K1'}),
                     g('G4', [['OWN:Since', ['1']], ['PERP:Basis', ['high']]], h=60, kind='gate2', w={'key': '1m:X=low', 'unit': 'BTC|level|1m:X=low'}),
                     g('G5', [['OWN:Since', ['1']]], coin='ETH'), g('G6', [['60m:CHART.z4.HS', ['break up']]]), g('G7', [['OWN:Since', ['1']]])],
            'models': {}}
    before = hl.non_gate_sha(pack)
    par = {'BTC': {'rows': [{'key': 'G1', 'h': 15, 'minutes': 100, 'parity': 1.0}, {'key': 'G3', 'h': 15, 'minutes': 50, 'parity': 1.0},
                            {'key': 'G4', 'h': 60, 'minutes': 80, 'parity': 1.0}, {'key': 'G7', 'h': 15, 'minutes': 80, 'parity': 0.99}]}}
    hpar = {'BTC': {'readings': {'PERP:Basis': {'agreement': 1.0}}, 'engine': {'15m:RSI14': {'agreement': 0.999}}}}
    out = dr.set_gate_live_ready(pack, par, hpar)
    r = {x['key']: x for x in out['rows']}
    assert r['K1'] is lv and hl.non_gate_sha(out) == before
    assert r['G1']['live_ready'] and r['G2']['live_ready'] and r['G3']['live_ready'] and r['G1']['live_ready_why'] == []
    assert not r['G4']['live_ready'] and r['G4']['live_ready_why'] == ['no binance perp feed']
    assert r['G5']['live_ready_why'] == ['no drill parity for this coin']
    assert r['G6']['live_ready_why'] == ['60m:CHART.z4.HS: not checked']
    assert r['G7']['live_ready_why'] == ['own conditions: parity 0.9900']
    out = dr.set_gate_live_ready(pack, par, hpar, feeds=('spot', 'binance perp'))
    assert {x['key']: x for x in out['rows']}['G4']['live_ready']
    lv['live_ready'] = False                                             # the HM2 call itself must be live ready
    assert {x['key']: x for x in dr.set_gate_live_ready(pack, par, hpar)['rows']}['G3']['live_ready_why'] == ['the call is not live ready in hm2_pack.json']
    assert {x['key']: x for x in dr.set_gate_live_ready(pack, par, {})['rows']}['G2']['live_ready_why'] == ['15m:RSI14: no HM2 parity for this coin']
    # the CLI: the job's artifacts (<COIN>/parity.json) and the committed HM2 parity copies (<COIN>.json); twins ignored
    lv['live_ready'] = True
    dp, hp_ = tmp_path / 'dp', tmp_path / 'hp'
    for c, d in (('BTC', par['BTC']), ('BTC-twin1', {'rows': [{'key': 'G7', 'h': 15, 'parity': 1.0}]})):
        os.makedirs(dp / c)
        dr._dump(d, str(dp / c / 'parity.json'))
    os.makedirs(hp_)
    dr._dump(hpar['BTC'], str(hp_ / 'BTC.json'))
    pk = tmp_path / 'hm2_pack.json'
    dr._dump(pack, str(pk))
    dr.main(['live-ready', '--pack', str(pk), '--parity', str(dp), '--hm2-parity', str(hp_)])
    got = {x['key']: x for x in json.load(open(pk))['rows']}
    assert got['G1']['live_ready'] and got['G2']['live_ready'] and not got['G7']['live_ready']
    with pytest.raises(SystemExit):
        dr.main(['live-ready', '--pack', str(pk), '--parity', str(tmp_path / 'none')])


# ------------------------------------------------------------------------------- the pre-run audit (Nov 12 2026)
def _twice(x):
    return 2 * x


def _die_on_1(x):
    import time as _t
    if x == 1:
        os._exit(9)                                         # as the OOM killer: the worker is gone, no exception
    _t.sleep(0.3)
    return x


_SAFE = dr._block_safe


def _block_die_1(bid):
    if bid == 1:
        os._exit(9)
    return _SAFE(bid)


def _block_raise_2(bid):
    if bid == 2:
        raise RuntimeError('block two broke')
    return dr.__dict__['_block_job_orig'](bid)


def test_fork_map_order_and_fail_fast():
    """(W3) The drill's map gives results in item order (fork workers and serial alike) and a killed worker raises
    BrokenProcessPool at once instead of hanging; what finished before stays in `done`."""
    from concurrent.futures.process import BrokenProcessPool
    assert dr._fork_map(_twice, range(7), 3) == [2 * i for i in range(7)] == dr._fork_map(_twice, range(7), 1)
    done = []
    assert dr._fork_map(_twice, [5], 4, done=done) == [10] and done == [(5, 10)]
    done = []
    with pytest.raises(BrokenProcessPool):
        dr._fork_map(_die_on_1, [0, 1, 2, 3, 4, 5], 2, done=done)
    assert all(r == x for x, r in done) and 1 not in [x for x, _ in done]


def test_quarter_subset_ignores_chart_units():
    """(F2/C6) The twin fallback's quarter depends on the units file and on unit ids only: the same file list with 650
    or 661 chart units appended gives identical flags on every shared id; a chart unit's flag is crc32(id) % 4 == 0."""
    import zlib
    base = [dr._unit('X', 'level', f'1m:L{i}=high', 1 if i < 5 else 3, 'test') for i in range(400)]
    chart = [dr._unit('X', 'chart', f'15m:CHART.z4.P{i}=break up', 3, 'chart') for i in range(661)]
    a, b = dr.quarter_subset(base + chart[:650]), dr.quarter_subset(base + chart)
    shared = {u['id'] for u in base + chart[:650]}
    assert a & shared == b & shared and a == b - {u['id'] for u in chart[650:]}
    assert a & {u['id'] for u in base} == dr.quarter_subset(base)
    assert all((u['id'] in b) == (zlib.crc32(u['id'].encode()) % 4 == 0) for u in chart)
    assert 0 < len(b & {u['id'] for u in chart}) < len(chart) and {u['id'] for u in base[:5]} <= a


def test_failed_block_recorded_and_checks(noise, tmp_path, monkeypatch):
    """(W4, W2, C3) A block that raises is recorded as missing (its files gone), every other block is kept; meta.json
    is written before the checks and a failing league check is recorded, not raised; the slim top table holds the
    full table's rank-1 rows and the main list's top TOP_FULL, unchanged; the pack check runs on the real coin."""
    ctx = noise[0]['ctx']
    monkeypatch.setattr(dr, 'BLOCK_UNIT_DAYS', 120)
    monkeypatch.setitem(dr.__dict__, '_block_job_orig', dr._block_job)
    monkeypatch.setattr(dr, '_block_job', _block_raise_2)
    monkeypatch.setattr(dr, 'check_league', lambda *a, **k: (_ for _ in ()).throw(ValueError('league check broke')))
    units = [(k, key, t, dict(e, extra={**e.get('extra', {}), 'pack': {'15': {'dir': 1, 'onset_dir_A': 1, 'n_A': 1, 'n_B': None}}})
              if k == 'hm2' else e) for k, key, t, e in NOISE_UNITS]
    out = str(tmp_path / 'X')
    m = dr.run_series('X', '', out, _units(units, PACK), procs=2, ctx=ctx, log=NOOP)
    assert m['blocks_total'] == len(NOISE_UNITS) and m['blocks_missing'] == [2] and [f['block'] for f in m['blocks_failed']] == [2]
    assert 'block two broke' in m['blocks_failed'][0]['error'] and m['pool_error'] is None
    with pytest.raises(SystemExit, match=r'1 blocks failed: \[2\]'):         # the coin job exits non-zero after meta.json
        dr._exit_if_blocks_failed(m)
    dr._exit_if_blocks_failed({**m, 'blocks_failed': []})                     # a complete series exits 0
    assert not [f for f in os.listdir(out) if f.startswith('b00002_')] and os.path.isfile(os.path.join(out, 'b00003_top.csv.gz'))
    assert m['league_check'] == {'error': "ValueError('league check broke')"} and json.load(open(os.path.join(out, 'meta.json')))['league_check'] == m['league_check']
    assert m['pack_check']['checked'] == 1 and m['pack_check']['n_A_differ'] == 1 and m['pack_check']['n_B_differ'] == 0
    for f in sorted(os.listdir(noise[0]['out'])):
        if f.endswith('_top.csv.gz') and os.path.getsize(os.path.join(noise[0]['out'], f)) > 30:
            T = pd.read_csv(os.path.join(noise[0]['out'], f))
            T1 = pd.read_csv(os.path.join(noise[0]['out'], f.replace('_top.csv.gz', '_top1.csv.gz')))
            want = T[((T['list'] == 'main') & (T['rank'] <= dr.TOP_FULL)) | (T['rank'] == 1)].reset_index(drop=True)
            pd.testing.assert_frame_equal(T1, want)
            assert len(T1) < len(T) and set(T1['rank']) <= set(range(1, dr.TOP_FULL + 1))


def test_broken_pool_keeps_finished_blocks(noise, tmp_path, monkeypatch):
    """(W3 with W4) A killed block worker stops the series job at once, after meta.json records the blocks that
    finished; no file of an unfinished block stays."""
    monkeypatch.setattr(dr, 'BLOCK_UNIT_DAYS', 120)
    monkeypatch.setattr(dr, '_block_safe', _block_die_1)
    out = str(tmp_path / 'X')
    with pytest.raises(SystemExit, match='block pool failed'):
        dr.run_series('X', '', out, _units(NOISE_UNITS, PACK), procs=2, ctx=noise[0]['ctx'], log=NOOP)
    m = json.load(open(os.path.join(out, 'meta.json')))
    assert 'BrokenProcessPool' in m['pool_error'] and 1 in m['blocks_missing'] and m['league_check'] is None
    for b in range(m['blocks_total']):
        has = bool([f for f in os.listdir(out) if f.startswith(f'b{b:05d}_')])
        assert has == (b not in m['blocks_missing'])


def test_unknown_units_twin_tolerated(noise, tmp_path):
    """(W6) A unit key a series cannot resolve stops a real coin's job and is listed (and run around) on a twin."""
    units = [NOISE_UNITS[0], ('level', '1m:NOPE=high', 3, {})]
    U = _units(units)
    with pytest.raises(SystemExit, match='unknown unit keys'):
        dr.run_series('X', '', str(tmp_path / 'real'), U, procs=1, ctx=noise[0]['ctx'], log=NOOP)
    m = dr.run_series('X', '', str(tmp_path / 'twin'), U, twin=1, procs=1, ctx=noise[1]['ctx'], log=NOOP)
    assert m['units']['unknown_n'] == 1 and m['units']['unknown_eg'] == ['X|level|1m:NOPE=high'] and m['units']['run'] == 1
    assert [x['id'] for x in m['units']['unknown']] == ['X|level|1m:NOPE=high'] and not m['units']['strict'] and m['pack_check'] is None


def test_check_pack_toy(noise, tmp_path):
    """(C3) build_units stores each HM2 pack call's dir, onset_dir_A and onset n_A / n_B per h (merged over the h rows
    of one key); check_pack compares them with the drill's uncapped counts and direction (240 on the 240 grid)."""
    pk = {'rows': [{'coin': 'BTC', 'kind': 'pair', 'key': 'F=x & G=y', 'h': 15, 'dir': 1, 'onset_dir_A': -1, 'conds': [['F', ['x']], ['G', ['y']]],
                    'onset': {'n_A': 103148.0, 'n_B': 20622.0}},
                   {'coin': 'BTC', 'kind': 'pair', 'key': 'F=x & G=y', 'h': 60, 'dir': 1, 'onset_dir_A': 1, 'conds': [['F', ['x']], ['G', ['y']]],
                    'onset': {'n_A': 5.0, 'n_B': 6.0}},
                   {'coin': 'BTC', 'kind': 'model', 'key': 'GBM.TA15=very high', 'h': 15, 'dir': -1, 'onset': {'n_A': 7.0, 'n_B': 8.0}}]}
    dp = str(tmp_path / 'd.csv')
    pd.DataFrame([{'coin': 'BTC', 'kind': 'single', 'key': '1m:A=high', 'h': 15, 'dir': 1, 'n_A': 9, 'n_B': 3, 'odds_A': 1.0}]).to_csv(dp, index=False)
    us = {u['id']: u for u in dr.build_units(dp, '', '', pk, coins=['BTC'], chart=False)['coins']['BTC']}
    assert us['BTC|hm2|F=x & G=y']['pack'] == {'15': {'dir': 1, 'onset_dir_A': -1, 'n_A': 103148, 'n_B': 20622},
                                               '60': {'dir': 1, 'onset_dir_A': 1, 'n_A': 5, 'n_B': 6}}
    assert us['BTC|model|GBM.TA15=very high']['pack'] == {'15': {'dir': -1, 'onset_dir_A': None, 'n_A': 7, 'n_B': 8}}
    ctx = noise[0]['ctx']
    k, key, t, e = NOISE_UNITS[3]
    u = dr._unit('X', k, key, t, 'test', conds=e['conds'])
    x = dr.split_instances(ctx, u, dr.unit_rows(ctx, u))
    dr._ok240(ctx)
    nA, nB = len(x.rA_all), len(ctx.g.in_split(x.fires, 'B'))
    nA4, nB4 = int(ctx.ok240A[x.rA_all].sum()), int(ctx.ok240B[ctx.g.in_split(x.fires, 'B')].sum())
    d = lambda H: int(x.d[dr.H_ALL.index(H)])                                         # noqa: E731
    u['pack'] = {'15': {'dir': d(15), 'onset_dir_A': d(15), 'n_A': nA, 'n_B': nB}, '240': {'dir': -d(240), 'onset_dir_A': d(240), 'n_A': nA4, 'n_B': nB4},
                 '60': {'dir': d(60), 'onset_dir_A': -d(60), 'n_A': nA + 1, 'n_B': None}}
    v = dr._unit('X', 'level', '1m:R3=very high', 1, 'test', extra={'pack': {'15': {'n_A': 0}}})          # not an HM2 pack call: skipped
    pc = dr.check_pack([u, v], {u['id']: x, v['id']: x}, ctx)
    assert (pc['checked'], pc['n_A_differ'], pc['n_B_differ'], pc['onset_dir_differ'], pc['pack_dir_differ']) == (3, 1, 0, 1, 1)
    assert pc['by_h']['240'] == {'checked': 1, 'n_A_differ': 0, 'n_B_differ': 0, 'onset_dir_differ': 0, 'pack_dir_differ': 1}
    assert [(z['id'], z['h']) for z in pc['examples']] == [(u['id'], 60)] and pc['onset_dir_checked'] == 3
    assert dr.check_pack([u], lambda w: x, ctx) == pc
