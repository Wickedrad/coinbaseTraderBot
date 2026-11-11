"""heat_live: the live reader gives the engine's levels and events (python/oracle/heat_live.py)."""
import numpy as np
import pandas as pd

import json
import pytest

from oracle import heat, heat_live, heat_parity
from oracle.common import DAY, MIN, ms


def _csv(path, start, days, seed=0, grid=0.01):
    rng = np.random.default_rng(seed)
    n = days * 1440
    ts = start + np.arange(n) * MIN
    c = np.round(100 * np.exp(np.cumsum(rng.standard_t(4, n) * 5e-4)) / grid) * grid
    o = np.r_[100.0, c[:-1]]
    w = np.abs(rng.normal(0, 3e-4, n))
    h = np.round(np.maximum(o, c) * (1 + w) / grid + 0.5) * grid
    l = np.round(np.minimum(o, c) * (1 - w) / grid - 0.5) * grid
    v = rng.uniform(1, 2, n)
    df = pd.DataFrame({'ts': ts, 'o': o, 'h': h, 'l': l, 'c': c, 'v': v, 'tb': v * rng.uniform(0.3, 0.7, n)})
    df = df.drop(index=range(40_000, 40_003)).drop(index=range(90_000, 90_030))      # a short gap and a long outage
    df.to_csv(path, index=False)
    return df


def test_live_reader_matches_engine(tmp_path):
    p = str(tmp_path / 'X.csv')
    start = ms('2024-10-01')
    df = _csv(p, start, 120)
    m = heat.load_minutes(p, end=start + 120 * DAY)
    g = heat.Grid(m, heat.labels(m))
    readings, _, edges, missing, step = heat.build_readings(m, g, str(tmp_path), log=lambda *a: None)
    assert not missing and step and abs(step - 0.01) < 1e-12 and len(edges) > 400
    eng = {R['name']: R for R in readings}
    spA = g.sp['A']

    # 1. the same function on the whole grid reproduces the engine: its own edges, then every reading's codes
    n_cmp = 0
    for k in heat.TFS:
        R, used, s = heat_live.tf_codes(m, k, edges=None, step=step, window=None, a_rows=(spA.lo, spA.hi))
        assert s == 0
        for name, e in used.items():
            assert np.array_equal(np.asarray(e), np.asarray(edges[name])), name
        for r in R:
            assert np.array_equal(r['codes'], eng[r['name']]['codes']), r['name']
            n_cmp += 1
        R2, _, _ = heat_live.tf_codes(m, k, edges=edges, step=step, window=None)          # ... and with the stored edges
        assert all(np.array_equal(r['codes'], eng[r['name']]['codes']) for r in R2) and len(R2) == len(R)
    assert n_cmp == sum(1 for R in readings if not R.get('ctx'))

    # 2. a window ending at a minute gives the keys the engine fires at that minute
    meta = {'edges': edges, 'price_step': step}
    by_row = {}
    lo, hi = m['n'] - 3 * 1440, m['n']
    for R in readings:
        for row, key in heat_live.events_at(R, lo, hi):
            by_row.setdefault(row, set()).add(key)
    rows = sorted({hi - 1, hi - 61, hi - 1 - 240, hi - 1 - 720} | {hi - 1 - 15 * i for i in range(1, 12)} | {hi - 1 - 5 * i for i in range(1, 8)}
                  | {hi - 2 - 7 * i for i in range(12)})
    same = tot = 0
    diff = []
    for row in rows:
        end = m['t0'] + (row + 1) * MIN
        w = df[(df.ts < end) & (df.ts >= end - 60 * DAY)]
        a = heat_live.active_keys(heat_live.grid(w), meta)
        assert a['ts'] == end and 1 in a['closed'] and ((row + 1) % 60 != 0 or a['closed'] == [1, 5, 15, 60])
        want, got = by_row.get(row, set()), set(a['events'])
        tot += len(want | got)
        same += len(want & got)
        diff += sorted(want ^ got)
    assert tot > 300 and same / tot >= 0.985, (same, tot, diff[:20])
    one = sorted(by_row[hi - 1])[:3]                                 # the `want` filter keeps only the asked keys
    w = df[df.ts >= m['t0'] + hi * MIN - 60 * DAY]
    assert heat_live.active_keys(heat_live.grid(w), meta, want=set(one))['events'] == one


def test_context_and_gap_rules():
    # UTC4h is the block of the entry minute; the state fires on 15-minute closes only
    n = 3 * 1440 + 8 * 60
    ts = ms('2025-03-01') + np.arange(n) * MIN
    c = 100 + np.cumsum(np.random.default_rng(1).normal(0, 0.01, n))
    df = pd.DataFrame({'ts': ts, 'o': c, 'h': c + 0.01, 'l': c - 0.01, 'c': c, 'v': 1.0})
    a = heat_live.active_keys(heat_live.grid(df), {'edges': {}}, tfs=[1440])
    assert a['events'] == ['UTC4h=08-12'] and a['closed'] == []
    assert heat_live.active_keys(heat_live.grid(df.iloc[:-1]), {'edges': {}}, tfs=[1440])['events'] == []
    # dominance: the last completed day's change against the 60 days before it
    d = pd.Series(50 + np.cumsum(np.r_[np.random.default_rng(2).normal(0, 0.1, 80), 2.0]), index=ms('2025-03-03') - DAY * np.arange(81)[::-1] - DAY)
    lv = heat_live.dominance_levels({'BTC.D': d, 'USDT.D': d}, ms('2025-03-03') + 5 * MIN)
    assert lv['BTC.D 1d'] == 'strong up' and lv['Dom 1d'] == 'BTC.D up, USDT.D up'
    # a forward-filled minute in the last bar: that timeframe has no reading now
    g = heat_live.grid(df.drop(index=[n - 3]))
    assert g['gap'][n - 3] and heat_live.active_keys(g, {'edges': {}}, tfs=[5])['no_reading'] == [5]


def test_parity_job_end_to_end(tmp_path, monkeypatch):
    """heat_parity on a small history: the recomputed edges are the table's, the fixture is written, the window agrees."""
    start = heat.HEAT_END - 120 * DAY
    monkeypatch.setattr(heat, 'SPLITS', {'A': (start, start + 90 * DAY), 'B': (start + 90 * DAY, heat.HEAT_END)})
    p = str(tmp_path / 'X.csv')
    _csv(p, start, 120, seed=3)
    m = heat.load_minutes(p)
    assert m['t0'] + m['n'] * MIN == heat.HEAT_END
    g = heat.Grid(m, heat.labels(m))
    _, _, edges, _, step = heat.build_readings(m, g, str(tmp_path), log=lambda *a: None)
    with open(tmp_path / 'meta.json', 'w') as f:
        json.dump({'edges': edges, 'price_step': step, 'table_sha256': 'x'}, f)
    par = heat_parity.run('X', p, str(tmp_path / 'meta.json'), str(tmp_path), str(tmp_path / 'out'), days=1, procs=1, log=lambda *a: None, max_rows=40)
    assert par['edges']['different'] == 0 and par['edges']['same_as_meta'] == len(edges) > 400
    assert par['minutes_checked'] >= 30 and par['agreement'] >= 0.985, par
    assert (tmp_path / 'out' / 'fixture.json.gz').exists() and (tmp_path / 'out' / 'parity.json').exists()


def test_pack_parity_flag_and_live_meta():
    """The traded pack: aliases collapse, the live-parity flag marks the indicator that differs on a window, and the
    slim meta carries the zone edges of every reading behind a row (aliases and sign readings included)."""
    from oracle import heat_pack
    base = dict(h=15, n_A=5000, n_B=900, days_B=300, share_A=53.0, odds_A=2.0, t_A=5.0, t_B=3.0, move_B=1.0, hold_B=9.0, hold_over_B=1.5, best_B=6.0,
                dip_B=-4.0, wd_B=3.0, tick_B=0.1)
    rows = [dict(base, coin='SOL', key='1m:RSI14=very low', dir=1, share_B=54.0, share_over_B=4.0, odds_B=4.0, oheat_B=12.0),
            dict(base, coin='SOL', key='1m:CMO14=very low', dir=1, share_B=54.0, share_over_B=4.0, odds_B=4.0, oheat_B=12.0),      # the same event
            dict(base, coin='SOL', key='1m:PVI=high (rising in)', dir=-1, share_B=53.0, share_over_B=3.0, odds_B=3.0, oheat_B=9.0),
            dict(base, coin='SOL', key='5m:MOM10 sign=above 0', dir=-1, share_B=52.0, share_over_B=2.0, odds_B=2.0, oheat_B=6.0),
            dict(base, coin='SOL', key='UTC4h=08-12', dir=1, share_B=51.0, share_over_B=1.0, odds_B=1.0, oheat_B=3.0),
            dict(base, coin='SOL~twin1', key='1m:RSI14=very low', dir=1, share_B=50.0, share_over_B=0.0, odds_B=0.0, oheat_B=0.1)]
    summary = {'metas': {'SOL': {'table_sha256': 'abc'}}, 'direction': {'15': {'twin': {'max_odds_heat_B': 5.0}}}}
    pack = heat_pack.build(pd.DataFrame(rows), summary, horizons=(15,), top=40, top_share=20, source='direction_all.csv.gz')
    assert [r['key'] for r in pack['rows']] == ['1m:CMO14=very low', '1m:PVI=high (rising in)', '5m:MOM10 sign=above 0', 'UTC4h=08-12']
    assert pack['rows'][0]['aliases'] == ['1m:RSI14=very low'] and pack['rows'][0]['rank_coin'] == 1 and pack['rows'][0]['above_twin_max']
    par = {'SOL': {'agreement': 1.0, 'readings_that_differ': [], 'table_sha256': 'abc', 'edges': {'same_as_meta': 3, 'different': 0}},
           'XRP': {'agreement': 0.99, 'readings_that_differ': [['1m:PVI', 197], ['1m:PVI sign', 125]], 'table_sha256': None, 'edges': {}}}
    heat_pack.add_parity(pack, par)
    assert pack['live_reader_parity']['indicators_that_differ'] == ['PVI']
    assert [r['live_parity'] for r in pack['rows']] == [True, False, True, True]
    meta = {'price_step': 0.01, 'table_sha256': 'abc',
            'edges': {'1m:RSI14': [1, 2, 3, 4], '1m:CMO14': [-2, -1, 1, 2], '1m:PVI': [-3, -1, 1, 3], '5m:MOM10': [-9, -4, 4, 9], '60m:ADX14': [5, 6, 7, 8]}}
    lm = heat_pack.live_meta(pack, {'SOL': meta})
    assert sorted(lm['SOL']['edges']) == ['1m:CMO14', '1m:PVI', '1m:RSI14', '5m:MOM10'] and lm['SOL']['edges']['5m:MOM10'] == [-9.0, -4.0, 4.0, 9.0]
    assert lm['SOL']['no_edges'] == ['UTC4h'] and lm['SOL']['price_step'] == 0.01
    with pytest.raises(SystemExit):
        heat_pack.live_meta(pack, {'SOL': dict(meta, table_sha256='other')})
