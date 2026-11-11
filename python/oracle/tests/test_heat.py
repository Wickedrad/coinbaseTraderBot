"""OR-HM1 heat map, Amendment 1 (python/oracle/heat.py, heat_vocab.py): labels against brute force, causality of every
reading, the event rules, the statistics on pure noise and a planted signal end to end with its no-signal twin."""
import gzip
import json
import os

import numpy as np
import pandas as pd
import pytest

from oracle import heat
from oracle.common import DAY, MIN, ms

pytest.importorskip('talib')
from oracle import heat_vocab  # noqa: E402


def _csv(path, start, days, seed=0, plant=None):
    rng = np.random.default_rng(seed)
    n = days * 1440
    ts = start + np.arange(n) * MIN
    r = rng.normal(0, 8e-4, n)
    if plant is not None:
        r = plant(ts, r)
    c = 100 * np.exp(np.cumsum(r))
    o = np.r_[100, c[:-1]]
    w = np.abs(rng.normal(0, 3e-4, n))
    h = np.maximum(o, c) * (1 + w)
    l = np.minimum(o, c) * (1 - w)
    v = rng.uniform(1, 2, n)
    tb = v * rng.uniform(0.3, 0.7, n)
    pd.DataFrame({'ts': ts, 'o': o, 'h': h, 'l': l, 'c': c, 'v': v, 'tb': tb}).to_csv(path, index=False)


def test_labels_match_brute_force(tmp_path):
    f = tmp_path / 'x.csv'
    start = ms('2024-12-01')
    _csv(f, start, 2, seed=3)
    m = heat.load_minutes(str(f), end=start + 2 * DAY)
    lab = heat.labels(m)
    o, h, l, c = m['o'], m['h'], m['l'], m['c']
    rng = np.random.default_rng(1)
    for r in rng.integers(0, m['n'] - 62, 60):
        e = o[r + 1]                                    # entry: the next minute's open
        for H in heat.HORIZONS:
            assert abs(lab[f'ret{H}'][r] - (c[r + H] / e - 1) * 1e4) < 2e-2
            assert abs(lab[f'retL{H}'][r] - (c[r + H] / c[r + 1] - 1) * 1e4) < 2e-2
            hi, lo = h[r + 1:r + H + 1], l[r + 1:r + H + 1]
            assert abs(lab[f'up{H}'][r] - (hi.max() / e - 1) * 1e4) < 2e-2
            assert abs(lab[f'dn{H}'][r] - (lo.min() / e - 1) * 1e4) < 2e-2
            assert abs(lab[f'dipU{H}'][r] - (lo[:hi.argmax() + 1].min() / e - 1) * 1e4) < 2e-2
            assert abs(lab[f'dipD{H}'][r] - (hi[:lo.argmin() + 1].max() / e - 1) * 1e4) < 2e-2
        for X in heat.TOUCH:
            up = np.nonzero(h[r + 1:r + 61] >= e * (1 + X / 1e4))[0]
            dn = np.nonzero(l[r + 1:r + 61] <= e * (1 - X / 1e4))[0]
            assert lab[f'tu{X}'][r] == (up[0] + 1 if len(up) else 0)
            assert lab[f'td{X}'][r] == (dn[0] + 1 if len(dn) else 0)
    assert not lab['valid'][m['n'] - 61:].any() and lab['valid'][m['n'] - 62]


def test_gap_invalidates_window_and_bad_rows_become_gaps(tmp_path):
    f = tmp_path / 'x.csv'
    start = ms('2024-12-01')
    n = 2 * 1440
    c = np.full(n, 100.0)
    df = pd.DataFrame({'ts': start + np.arange(n) * MIN, 'o': c, 'h': c, 'l': c, 'c': c, 'v': 1.0})
    df = df.drop(index=500)
    df.loc[700, 'c'] = 0.0                              # a zero price
    df.loc[900, 'h'] = np.nan                           # a blank high
    df.to_csv(f, index=False)
    m = heat.load_minutes(str(f), end=start + n * MIN)
    lab = heat.labels(m)
    assert m['gap'][500] and m['gap'][700] and m['gap'][900] and m['bad_rows'] == 2
    assert not lab['valid'][500] and not lab['valid'][440] and lab['valid'][439] and lab['valid'][501]
    assert np.isfinite(m['c']).all() and (m['c'] > 0).all()


def test_never_loads_past_heat_end(tmp_path):
    """Amendment 2: the tables stop at HEAT_END (2026-01-01). A file holding a later minute is refused; the lenient
    mode drops those rows; nothing can widen the window."""
    assert heat.HEAT_END == ms('2026-01-01') and heat.HEAT_END <= heat.DEV_END and heat.SPLITS['B'][1] == heat.HEAT_END
    f = tmp_path / 'x.csv'
    start = heat.HEAT_END - 2 * DAY
    _csv(f, start, 4)
    with pytest.raises(SystemExit):
        heat.load_minutes(str(f), start=start, end=start + 4 * DAY)
    m = heat.load_minutes(str(f), start=start, end=2 ** 62, strict=False)
    assert m['t0'] + m['n'] * MIN == heat.HEAT_END
    ok = tmp_path / 'ok.csv'
    df = pd.read_csv(f)
    df[df.ts < heat.HEAT_END].to_csv(ok, index=False)
    m2 = heat.load_minutes(str(ok), start=start, end=start + 4 * DAY)
    assert m2['n'] == m['n'] and np.array_equal(m2['c'], m['c'])


def test_read_state_and_events_are_causal():
    R = {'k': 15, 'codes': np.array([3, 4, 5], np.int8)}
    # rows 0..13 are inside bar 0 (not closed): unknown; row 14 is bar 0's close; rows 15..28 still see bar 0
    s = heat.read_state(R, np.arange(45))
    assert (s[:14] == -1).all() and (s[14:29] == 3).all() and s[29] == 4 and s[44] == 5
    # a level starts an event only after a KNOWN, different level; the row is the bar's close
    R = {'k': 15, 'codes': np.array([-1, 1, 1, 0, 1, -1, 1], np.int8)}
    assert list(heat.level_events(R, 1)) == [74]
    assert list(heat.level_events({**R, 'every': True}, 1)) == [29, 44, 74, 104]
    # sides: level 1 entered from below (0 -> 1) or from above (2 -> 1)
    R = {'k': 1, 'codes': np.array([0, 1, 2, 1, 0, 1], np.int8)}
    assert list(heat.level_events(R, 1, 1)) == [1, 5] and list(heat.level_events(R, 1, -1)) == [3]
    names = [x[2] for x in heat.event_levels({'zones': True, 'levels': heat.ZONES})]
    assert names == ['very low', 'low (falling in)', 'low (recovering)', 'high (rising in)', 'high (cooling)', 'very high']
    assert [x[2] for x in heat.event_levels({'levels': ['none', 'bull', 'bear']})] == ['bull', 'bear']


def test_bucket_and_sign_treat_both_sides_alike():
    assert list(heat.bucket(np.array([-2, -1, 0, 1, 2, np.nan, np.inf]), [-1, 1])) == [0, 0, 1, 2, 2, -1, -1]
    assert list(heat_vocab.sign_codes(np.array([1, 0, 1, -1, 0, -1, np.nan, 2]))) == [1, 1, 1, 0, 0, 0, -1, 1]
    a, b = np.array([1.0, 2.0, 2.0, 3.0, 2.0]), np.array([2.0, 2.0, 2.0 + 1e-13, 2.0, 2.0])
    assert list(heat_vocab._state(a, b)) == [0, 0, 0, 1, 1]            # ties keep the last side: no cross from float noise


def test_context_states_known_after_close(tmp_path):
    start = ms('2024-12-01')
    nd = 100
    m = {'t0': start + 90 * DAY, 'n': 10 * 1440}
    d = tmp_path / 'dom'
    d.mkdir()
    rng = np.random.default_rng(0)
    for sym, sd in (('BTC.D', 0.005), ('USDT.D', 0.03)):
        cl = 50 * np.exp(np.cumsum(rng.normal(0, sd, nd)))
        cl[95] = cl[94] * (1 + 6 * sd)                  # day 95 (grid day 5): a strong rise
        cl[96:] = cl[95]
        pd.DataFrame({'ts': [start + i * DAY for i in range(nd)], 'o': cl, 'h': cl, 'l': cl, 'c': cl, 'v': 1}).to_csv(d / f'{sym}_1d.csv', index=False)
    R = {x['name']: x for x in heat.context_readings(m, str(d))}
    r = R['BTC.D 1d']
    assert r['levels'] == heat.DOM_LV and r['state']
    # readable only from day 5's last minute (its close) on, never during day 5
    s = heat.read_state(r, np.array([5 * 1440 + 100, 6 * 1440 - 2, 6 * 1440 - 1, 6 * 1440 + 100]))
    assert s[0] != 4 and s[1] != 4 and s[2] == 4 and s[3] == 4
    assert heat.read_state(R['Dom 1d'], np.array([6 * 1440 + 5]))[0] == 3            # both rose
    assert list(heat.read_state(R['UTC4h'], np.array([0, 239, 240, 479]))) == [-1, 1, 1, 2]
    ev = heat.level_events(r, 4)                         # a state: every 15-minute close while it holds
    ev = ev[ev >= 5 * 1440]
    assert len(ev) == 96 and ev.min() == 6 * 1440 - 1 and (np.diff(ev) == 15).all()


def test_twin_keeps_size_and_loses_direction(tmp_path):
    f = tmp_path / 'x.csv'
    start = ms('2024-12-01')
    _csv(f, start, 3, seed=5)
    m = heat.load_minutes(str(f), end=start + 3 * DAY)
    t = heat.make_twin(m, 1)
    r, rt = np.diff(np.log(m['c'])), np.diff(np.log(t['c']))
    assert np.allclose(np.abs(r), np.abs(rt)) and 0.4 < np.mean(np.sign(r) == np.sign(rt)) < 0.6
    assert np.allclose(np.log(t['h'] / t['l']), np.log(m['h'] / m['l']))
    assert (t['h'] >= np.maximum(t['o'], t['c']) - 1e-9).all() and (t['l'] <= np.minimum(t['o'], t['c']) + 1e-9).all()
    assert t['tick'] is m['tick'] and t['gap'] is m['gap']
    assert not np.allclose(heat.make_twin(m, 2)['c'], t['c'])


def test_tick_size_and_tick_units(tmp_path):
    f = tmp_path / 'x.csv'
    start = ms('2024-12-01')
    rng = np.random.default_rng(2)
    n = 2 * 1440
    c = np.round(0.2 * np.exp(np.cumsum(rng.normal(0, 5e-4, n))), 4)
    o = np.r_[c[0], c[:-1]]
    pd.DataFrame({'ts': start + np.arange(n) * MIN, 'o': o, 'h': np.maximum(o, c), 'l': np.minimum(o, c), 'c': c, 'v': 1.0}).to_csv(f, index=False)
    m = heat.load_minutes(str(f), end=start + n * MIN)
    assert abs(float(np.median(m['tick'])) - 1e-4 / 0.2 * 1e4) < 0.6          # about 5 bps a step
    u = heat.tick_units(m)
    assert np.array_equal(u['c'], np.round(m['c'] * 1e4)) and u['c'].dtype == float
    m2 = dict(m)
    for x in ('o', 'h', 'l', 'c'):
        m2[x] = m[x] * 1000
    assert np.array_equal(heat.tick_units(m2)['c'], u['c'])                   # the unit of price does not matter
    assert abs(u['step'] - 1e-4) < 1e-12
    off = dict(m)
    off['c'] = m['c'] * np.exp(rng.normal(0, 1e-6, n))
    assert heat.tick_units(off) is off
    # the unit comes from the build rows only: an off-grid or finer price AFTER them cannot change a build-years value
    late = dict(m)
    late['h'] = m['h'].copy()
    late['h'][n - 5] += 0.3e-4
    ul = heat.tick_units(late, n - 100)
    assert np.array_equal(ul['c'][:n - 100] * (ul['step'] / u['step']), u['c'][:n - 100]) and ul['step'] <= u['step']
    assert (ul['c'][:n - 100] == np.round(ul['c'][:n - 100])).all()
    # a twin of a coin on a grid: an up-and-back move lands on exactly the same price, and it is not rescaled by float noise
    tw = heat.make_twin(m, 1)
    assert (tw['h'] >= np.maximum(tw['o'], tw['c'])).all() and (tw['l'] <= np.minimum(tw['o'], tw['c'])).all()
    ut = heat.tick_units(tw)
    assert ut is tw or float(np.abs(ut['c']).max()) < 2.0 ** 50
    lab = heat.labels(m)                                                      # a move of one step is flat for the odds
    one = np.abs(lab['ret5']) <= 1.2 * m['tick']
    assert one.any() and (lab['sg5'][one] == 0).all()


def test_vocabulary_has_no_lookahead():
    """Every reading at bar i depends only on bars <= i: cut the future off and the past must not change."""
    rng = np.random.default_rng(7)
    n = 2600
    r = rng.standard_t(4, n) * 6e-4
    c = 100 * np.exp(np.cumsum(r))
    o = np.r_[100, c[:-1]] * np.exp(rng.normal(0, 1e-4, n))
    w = np.abs(rng.normal(0, 4e-4, n))
    b = {'o': o, 'h': np.maximum(o, c) * (1 + w), 'l': np.minimum(o, c) * (1 - w), 'c': c, 'v': rng.uniform(1, 3, n), 'tb': None}
    b['tb'] = b['v'] * rng.uniform(0.3, 0.7, n)
    V, C, missing = heat_vocab.vocabulary(b)
    cut = n - 400
    V2, C2, _ = heat_vocab.vocabulary({k: v[:cut] for k, v in b.items()})
    assert len(V) > 120 and len(C) > 70 and not missing
    bad = [a[0] for a, z in zip(V, V2) if not np.allclose(a[3][:cut], z[3], rtol=2e-3, atol=2e-3, equal_nan=True)]
    bad += [a[0] for a, z in zip(C, C2) if not np.array_equal(a[1][:cut], z[1])]
    assert bad == [], bad
    assert all(np.isnan(a[3][:heat_vocab.WARM]).all() for a in V) and all((a[1][:heat_vocab.WARM] == -1).all() for a in C)


def test_t_is_calibrated_on_noise(tmp_path):
    """A level that holds on half of all minutes and a rare one: on pure noise t stays inside chance, and the windows
    per day never exceed what fits in a day."""
    f = tmp_path / 'x.csv'
    start = ms('2024-06-01')
    _csv(f, start, 150, seed=11)
    m = heat.load_minutes(str(f), start=start, end=start + 150 * DAY)
    g = heat.Grid(m, heat.labels(m))
    rng = np.random.default_rng(3)
    rows = g.sp['A'].rows
    ts = []
    for share in (0.5, 0.5, 0.5, 0.5, 0.05, 0.05, 0.002, 0.002):
        st = g.full(rows[rng.random(len(rows)) < share], 'A')
        ts += [st[H]['t'] for H in heat.HORIZONS] + [st[H]['t_p'] for H in heat.HORIZONS]
        assert all(st[H]['wd'] <= 1440 / H + 1e-9 for H in heat.HORIZONS)
    ts = np.array(ts)
    assert np.abs(ts).max() < 4.0 and 0.5 < ts.std() < 1.6


def test_planted_signal_end_to_end(tmp_path):
    """Two planted effects: the coin drifts up in UTC hours 8-12 (a clock effect) and bounces for five minutes after a
    large down minute. Both must be hot on A, replicate on B and survive BHY; the clock effect must show up as the
    time-of-day part; pairs that only restate the clock effect must not pass; the no-signal twins of the same file
    (two sets: the league reports their median and range) must come out empty."""
    start = ms('2024-08-01')
    days = 240

    def plant(ts, r):
        r = r.copy()
        hr = (ts // 3_600_000) % 24
        r[(hr >= 8) & (hr < 12)] += 1.5e-4
        big = np.nonzero(r < -2.5 * 8e-4)[0]
        for k in range(1, 6):
            j = big + k
            r[j[j < len(r)]] += 3e-4
        return r
    f = tmp_path / 'BTC.csv'
    _csv(f, start, days, seed=1, plant=plant)
    out = tmp_path / 'out'
    old = heat.TFS, heat.N_TRIG_PER_TF, heat.N_TRIG_CTX, heat.N_REL_TOP, heat.SEEDS
    heat.TFS, heat.N_TRIG_PER_TF, heat.N_TRIG_CTX, heat.N_REL_TOP, heat.SEEDS = [1], 3, 2, 2, 2
    try:
        meta = heat.run_coin('BTC', str(f), str(tmp_path / 'nodom'), str(out / 'BTC'), end=start + days * DAY, procs=2, log=lambda *_: None)
        for tw in (1, 2):
            heat.run_coin('BTC', str(f), str(tmp_path / 'nodom'), str(out / f'BTC-twin{tw}'), end=start + days * DAY, twin=tw, procs=1, log=lambda *_: None)
        s = heat.league(str(out), str(tmp_path / 'league'))
    finally:
        heat.TFS, heat.N_TRIG_PER_TF, heat.N_TRIG_CTX, heat.N_REL_TOP, heat.SEEDS = old
    assert meta['readings'] > 200 and meta['schema'] == 'oracle-heat-2' and s['coins'] == ['BTC'] and s['twins'] == ['BTC~twin1', 'BTC~twin2']
    assert s['twin_sets'] == {'1': ['BTC'], '2': ['BTC']}
    assert len(meta['table_sha256']) == 64 and s['metas']['BTC']['table_sha256'] == meta['table_sha256']
    df = pd.read_csv(out / 'BTC' / 'heat.csv.gz', low_memory=False)
    assert {'single', 'curve', 'pair'} <= set(df.kind)
    dips = df[df.kind.isin(['curve', 'pair']) & (df.n >= 30)]                       # every cell stores the usual wrong-way dip
    assert dips.dip_up.notna().all() and (dips.dip_up <= 1e-9).all() and (dips.dip_dn >= -1e-9).all()
    x = df[(df.key == 'UTC4h=08-12') & (df.h == 60)].set_index('split')
    assert x.loc['A', 'excess'] > 0 and x.loc['A', 't'] > 3 and x.loc['B', 't'] > 2
    assert x.loc['A', 'tod_excess'] > 0.5 * x.loc['A', 'excess']                    # a clock effect: the day shift keeps it
    y = df[(df.key == '1m:BarBody=very low') & (df.h == 5)].set_index('split')
    assert y.loc['A', 'excess'] > 0 and y.loc['A', 't'] > 3 and y.loc['B', 't'] > 2
    assert abs(y.loc['A', 'tod_excess']) < 0.5 * y.loc['A', 'excess']               # not a clock effect
    k = s['by_kind']
    assert k['single']['move']['bhy'] >= 2 and k['single']['move']['replicate'] >= k['single']['move']['bhy']
    assert k['twin:single']['move']['bhy'] <= 1 and k['twin:single']['move']['replicate'] <= 0.2 * k['single']['move']['replicate']
    assert k['twin:single']['sets'] == 2 and len(k['twin:single']['move']['range']['hot']) == 2      # the median of two twin sets and their range
    pr = df[(df.kind == 'pair') & (df.split == 'A') & (df.n >= 30)]
    assert pr.t_lift2.notna().any() and pr.deff.notna().all() and (pr.deff <= pr.days + 1e-9).all()  # second lift and effective days are stored
    hot = pd.read_csv(tmp_path / 'league' / 'hot.csv.gz', low_memory=False)
    clock = hot[hot.kind.isin(['pair', 'triple']) & (hot.cond.astype(str) == 'UTC4h') & (hot.lv.astype(str) == '08-12')]
    assert int(clock.passes.sum()) <= 2, clock[clock.passes][['key', 'h', 'track']]                 # the clock restated by a pair does not pass
    top = pd.read_csv(tmp_path / 'league' / 'league_move_heat.csv.gz')
    assert top.passes.iloc[0] and (top.move_B[top.passes] > 0).all() and (top.heat_B[top.passes] > 0).all()
    ta = pd.read_csv(tmp_path / 'league' / 'league_ta.csv.gz')
    assert (ta[(ta.coin == 'BTC') & (ta.reading == '1m:BarBody')].curve_t_B.max() > 3)
    md = open(tmp_path / 'league' / 'league.md').read()
    assert '|t|' not in md and 'WARNING: expected BTC, ETH, SOL, XRP' in md and 'twin' in md
    json.load(open(tmp_path / 'league' / 'summary.json'))                           # valid JSON (no NaN)
    vw = json.load(gzip.open(tmp_path / 'league' / 'viewer.json.gz', 'rt'))
    assert vw['coins'] == ['BTC'] and '1m:BarBody' in vw['coin']['BTC']['curves'] and vw['coin']['BTC']['events']
    for nm in ('strips.csv.gz', 'curves.csv.gz', 'relations.csv.gz', 'hot.csv.gz'):
        assert os.path.getsize(tmp_path / 'league' / nm) > 100


def test_never_doge(tmp_path):
    with pytest.raises(SystemExit):
        heat.run_coin('DOGE', 'x', 'y', str(tmp_path))
