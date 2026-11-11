"""OR-HM1 heat map (python/oracle/heat.py): causality, labels, events, a planted signal end to end."""
import json
import os

import numpy as np
import pandas as pd
import pytest

from oracle import heat
from oracle.common import DAY, MIN, ms

pytest.importorskip('talib')


def _csv(path, start, days, seed=0, plant=None):
    rng = np.random.default_rng(seed)
    n = days * 1440
    ts = start + np.arange(n) * MIN
    r = rng.normal(0, 8e-4, n)
    if plant is not None:
        r = plant(ts, r)
    c = 100 * np.exp(np.cumsum(r))
    o = np.r_[100, c[:-1]]
    h = np.maximum(o, c) * (1 + 2e-4)
    l = np.minimum(o, c) * (1 - 2e-4)
    v = rng.uniform(1, 2, n)
    tb = v * rng.uniform(0.3, 0.7, n)
    pd.DataFrame({'ts': ts, 'o': o, 'h': h, 'l': l, 'c': c, 'v': v, 'tb': tb}).to_csv(path, index=False)


def test_labels_and_touch(tmp_path):
    f = tmp_path / 'x.csv'
    start = ms('2024-12-01')
    n = 3 * 1440
    c = np.full(n, 100.0)
    c[1001:] = 100.3                     # +30 bps from row 1001 on
    df = pd.DataFrame({'ts': start + np.arange(n) * MIN, 'o': c, 'h': c, 'l': c, 'c': c, 'v': 1.0})
    df.to_csv(f, index=False)
    m = heat.load_minutes(str(f), end=start + n * MIN)
    lab = heat.labels(m)
    assert abs(lab['ret5'][1000] - 30) < 1e-3 and abs(lab['ret5'][995] - 0) < 1e-6
    assert abs(lab['ret5'][996] - 30) < 1e-3          # row 996 + 5 = 1001
    assert lab['tu25'][1000] == 1 and lab['td25'][1000] == 0 and lab['tu50'][1000] == 0
    assert lab['tu10'][941] == 60 and lab['tu10'][940] == 0
    assert abs(lab['up15'][990] - 30) < 1e-3 and lab['dn15'][990] == 0


def test_gap_invalidates_window(tmp_path):
    f = tmp_path / 'x.csv'
    start = ms('2024-12-01')
    n = 2 * 1440
    keep = np.ones(n, bool)
    keep[500] = False
    c = np.full(n, 100.0)
    df = pd.DataFrame({'ts': start + np.arange(n) * MIN, 'o': c, 'h': c, 'l': c, 'c': c, 'v': 1.0})[keep]
    df.to_csv(f, index=False)
    m = heat.load_minutes(str(f), end=start + n * MIN)
    lab = heat.labels(m)
    assert m['gap'][500] and not lab['valid'][500] and not lab['valid'][440] and lab['valid'][439] and lab['valid'][501]


def test_read_state_is_causal():
    R = {'k': 15, 'codes': np.array([3, 4, 5], np.int8)}
    # rows 0..13 are inside bar 0 (not closed): unknown; row 14 is bar 0's close; rows 15..28 still see bar 0
    s = heat.read_state(R, np.arange(45))
    assert (s[:14] == -1).all() and (s[14:29] == 3).all() and s[29] == 4 and s[44] == 5
    ev = heat.level_events({'k': 15, 'codes': np.array([0, 1, 1, 0, 1], np.int8)}, 1)
    assert list(ev) == [29, 74]


def test_context_dominance_known_after_close(tmp_path):
    start = ms('2024-12-01')
    m = {'t0': start, 'n': 5 * 1440}
    d = tmp_path / 'dom'
    d.mkdir()
    closes = [10, 10, 10.2, 10.2, 9.9]
    pd.DataFrame({'ts': [start + i * DAY for i in range(5)], 'o': closes, 'h': closes, 'l': closes, 'c': closes, 'v': 1}).to_csv(d / 'BTC.D_1d.csv', index=False)
    R = {x[0]: {'k': x[1], 'codes': x[2]} for x in heat.context_readings(m, str(d))}
    r = R['BTC.D 1d']
    # day 2 rose 2%: code 'up' (2) is readable only from day 2's last row (its close) on, never during day 2
    s = heat.read_state(r, np.array([2 * 1440 + 100, 3 * 1440 - 1, 3 * 1440 + 100]))
    assert list(s) == [1, 2, 2]
    blk = R['UTC4h']
    assert list(heat.read_state(blk, np.array([0, 239, 240, 479]))) == [-1, 1, 1, 2]


def test_planted_signal_end_to_end(tmp_path):
    """In UTC hours 8-11 the coin drifts up: the hour context must light up on A and replicate on B. The chance shift is by
    whole days, so it KEEPS time of day: a pure time-of-day effect scores about the same chance heat (by design)."""
    start = ms('2024-10-01')

    def plant(ts, r):
        hr = (ts // 3_600_000) % 24
        r = r.copy()
        r[(hr >= 8) & (hr < 12)] += 4e-4
        return r
    f = tmp_path / 'BTC.csv'
    _csv(f, start, 150, plant=plant)
    out = tmp_path / 'out'
    old = heat.TFS, heat.N_CAND, heat.N_PAIR_TOP, heat.SEEDS
    heat.TFS, heat.N_CAND, heat.N_PAIR_TOP, heat.SEEDS = [60], 10, 3, 2
    try:
        meta = heat.run_coin('BTC', str(f), str(tmp_path / 'nodom'), str(out / 'BTC'), end=start + 150 * DAY, log=lambda *_: None)
        s = heat.league(str(out), str(tmp_path / 'league'))
    finally:
        heat.TFS, heat.N_CAND, heat.N_PAIR_TOP, heat.SEEDS = old
    df = pd.read_csv(out / 'BTC' / 'heat.csv.gz')
    x = df[(df.key == 'UTC4h=08-12') & (df.h == 60)].set_index('split')
    assert x.loc['A', 'dir'] == 1 and x.loc['A', 't'] > 3 and x.loc['B', 't'] > 2
    assert x.loc['A', 'chance_heat'] > 0.5 * x.loc['A', 'heat']
    assert {'single', 'pair'} <= set(df.kind)
    assert meta['readings'] > 100 and s['by_kind']['single']['replicate_B'] >= 1
    assert os.path.exists(tmp_path / 'league' / 'league.md')
    json.load(open(tmp_path / 'league' / 'summary.json'))


def test_never_doge(tmp_path):
    with pytest.raises(SystemExit):
        heat.run_coin('DOGE', 'x', 'y', str(tmp_path))
