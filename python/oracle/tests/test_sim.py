"""Tests for oracle/sim.py (the shared simulation / statistics of the miner and the HO-1 scorer; prereg OR-H1 "Mining",
"Confirmation (discovery B) and freeze"). Synthetic data only.

    cd python && python3 -m pytest -q oracle/tests/test_sim.py
"""
import importlib.util
import os
import subprocess

import numpy as np
import pytest

from oracle.common import DAY, MIN, ms, split_of
from oracle.sim import (ArrayPart, PlaceboPool, bhy, bhy_adjust, busy_key, daily_usd, daily_vec, fire_mask, items_of,
                        jaccard, matched_placebo, shift_index, side_columns, split_rows, stationary_bootstrap_p,
                        stationary_bootstrap_test, trade_sim)

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))


def kalshi_meta(side_features=None):
    feats = [{'name': 'a', 'kind': 'state', 'levels': [-1, 0, 1], 'desc': ''},
             {'name': 'b', 'kind': 'bucket', 'levels': [0, 1, 2], 'desc': ''},
             {'name': 'k_price@Y', 'kind': 'bucket', 'levels': [0, 1], 'desc': '', 'side': 'Y', 'base': 'k_price'},
             {'name': 'k_price@N', 'kind': 'bucket', 'levels': [0, 1], 'desc': '', 'side': 'N', 'base': 'k_price'},
             {'name': 'only_y@Y', 'kind': 'state', 'levels': [-1, 0, 1], 'desc': ''}]
    return {'ct': 'pp15', 'scope': 'BTC', 'features': feats,
            'side_features': side_features if side_features is not None else {'Y': [2, 4], 'N': [3]}}


# ---------------------------------------------------------------- items and firing

def test_items_state_bucket_and_side_features():
    meta = kalshi_meta()
    part = ArrayPart(meta, {'t': np.zeros(1, np.int64), 'X': np.zeros((1, 5), np.int8)})
    y = items_of(part, 'Y')
    n = items_of(part, 'N')
    assert [(i.f, i.v) for i in y] == [('a', 1), ('a', -1), ('b', 0), ('b', 1), ('b', 2), ('k_price', 0), ('k_price', 1),
                                      ('only_y', 1), ('only_y', -1)]
    assert [(i.f, i.v, i.col) for i in n if i.f == 'k_price'] == [('k_price', 0, 3), ('k_price', 1, 3)]
    assert not any(i.f == 'only_y' for i in n)            # listed for Y only -> never an item of N
    assert all(i.v != 0 for i in y if i.f in ('a', 'only_y'))  # the neutral state is never an item
    # side_features given by column name works the same
    meta2 = kalshi_meta({'Y': ['k_price@Y', 'only_y@Y'], 'N': ['k_price@N']})
    assert side_columns(meta2, 'Y') == side_columns(meta, 'Y')
    # no side_features: every column applies to every side under its own name
    meta3 = {**meta, 'side_features': None}
    assert set(side_columns(meta3, 'N')) == {'a', 'b', 'k_price@Y', 'k_price@N', 'only_y@Y'}


def test_fire_mask_rows_and_pooled_resolution():
    rng = np.random.default_rng(0)
    X = rng.integers(-1, 2, (50, 5)).astype(np.int8)
    p1 = ArrayPart(kalshi_meta(), {'t': np.arange(50, dtype=np.int64), 'X': X})
    setup = {'side': 'N', 'items': [{'f': 'k_price', 'v': 1}, {'f': 'a', 'v': -1}]}
    want = (X[:, 3] == 1) & (X[:, 0] == -1)
    assert (fire_mask(p1, setup) == want).all()
    idx = np.array([3, 7, 9, 40])
    assert (fire_mask(p1, setup, idx) == want[idx]).all()
    m = np.zeros(50, bool)
    m[idx] = True
    assert (fire_mask(p1, setup, m) == want[idx]).all()
    # another part with the columns in another order: the setup resolves by name
    meta = kalshi_meta()
    perm = [4, 3, 2, 1, 0]
    meta2 = {**meta, 'features': [meta['features'][j] for j in perm], 'side_features': {'Y': [2, 0], 'N': [1]}}
    p2 = ArrayPart(meta2, {'t': np.arange(50, dtype=np.int64), 'X': X[:, perm]})
    assert (fire_mask(p2, setup) == want).all()
    # a part without the feature never fires
    meta3 = {**meta, 'features': meta['features'][:2], 'side_features': {}}
    p3 = ArrayPart(meta3, {'t': np.arange(50, dtype=np.int64), 'X': X[:, :2]})
    assert not fire_mask(p3, setup).any()
    # Y side reads k_price@Y, not k_price@N
    sy = {'side': 'Y', 'items': [{'f': 'k_price', 'v': 1}]}
    assert (fire_mask(p1, sy) == (X[:, 2] == 1)).all()


# ---------------------------------------------------------------- trade_sim

def test_trade_sim_skip_while_busy():
    t = np.arange(12, dtype=np.int64) * 5 * MIN           # a decision every 5 minutes
    fire = np.ones(12, bool)
    trade = np.ones(12)
    taken = trade_sim(t, np.full(12, 15), trade, fire)
    assert taken.tolist() == [0, 3, 6, 9]                  # next entry only at t >= t_prev + 15 min
    taken = trade_sim(t, np.full(12, 14), trade, fire)
    assert taken.tolist() == [0, 3, 6, 9]                  # 14 min: the +10 min row is still busy, +15 is free
    taken = trade_sim(t, np.full(12, 16), trade, fire)
    assert taken.tolist() == [0, 4, 8]
    # a row whose trade is NaN (not tradable) is not entered and does not block
    tr = trade.copy()
    tr[0] = np.nan
    assert trade_sim(t, np.full(12, 15), tr, fire).tolist() == [1, 4, 7, 10]
    # hold varies per position
    hold = np.array([5, 30, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5])
    assert trade_sim(t, hold, trade, fire).tolist() == [0, 1, 7, 8, 9, 10, 11]
    # per-key busy: two assets interleaved at the same instants are independent
    t2 = np.repeat(t, 2)
    g = np.tile([0, 1], 12)
    taken = trade_sim(t2, np.full(24, 15), np.ones(24), np.ones(24, bool), g)
    assert taken.tolist() == [0, 1, 6, 7, 12, 13, 18, 19]
    # one key: the second asset's simultaneous decision is skipped
    assert trade_sim(t2, np.full(24, 15), np.ones(24), np.ones(24, bool)).tolist() == [0, 6, 12, 18]
    # hold 0 counts as 1 minute: never two entries at one instant
    assert trade_sim(t2, np.zeros(24), np.ones(24), np.ones(24, bool)).tolist() == list(range(0, 24, 2))
    # unsorted input is walked in time order
    o = np.random.default_rng(1).permutation(12)
    taken = trade_sim(t[o], np.full(12, 15), trade[o], fire[o])
    assert sorted(o[taken].tolist()) == [0, 3, 6, 9]
    assert len(trade_sim(t, np.full(12, 15), trade, np.zeros(12, bool))) == 0


def test_daily_usd_every_day_present():
    span = (ms('2025-01-01'), ms('2025-01-08'))
    t = np.array([ms('2025-01-02') + 5 * MIN, ms('2025-01-02') + 9 * MIN, ms('2025-01-05')], dtype=np.int64)
    usd = np.array([1.0, 2.0, -0.5])
    d = daily_usd(t, usd, None, span)
    assert list(d) == ['2025-01-01', '2025-01-02', '2025-01-03', '2025-01-04', '2025-01-05', '2025-01-06', '2025-01-07']
    assert d['2025-01-02'] == 3.0 and d['2025-01-05'] == -0.5 and d['2025-01-01'] == 0.0
    assert daily_usd(t, usd, np.array([2]), span)['2025-01-02'] == 0.0
    assert daily_vec(t, usd, span).sum() == 2.5
    with pytest.raises(ValueError):
        daily_vec(np.array([ms('2025-01-09')]), np.array([1.0]), span)


# ---------------------------------------------------------------- matched placebo

def placebo_part():
    """3 strata x 4 days (perp split B), 20 rows per (stratum, day) except (stratum 2, day 3): trade = 100 s + day."""
    d0 = ms('2025-03-01') // DAY
    t, st = [], []
    for day in range(4):
        for s in range(3):
            if (s, day) == (2, 3):
                continue
            t += [(d0 + day) * DAY + (60 + 5 * k) * MIN for k in range(20)]
            st += [s] * 20
    t = np.array(t, dtype=np.int64)
    o = np.argsort(t, kind='stable')
    t, st = t[o], np.array(st, dtype=np.int16)[o]
    trade = (100 * st + (t // DAY - d0)).astype(np.float32)
    n = len(t)
    meta = {'ct': 'perp', 'scope': 'BTC', 'features': [], 'sides': ['L'], 'horizons': [15]}
    arrays = {'t': t, 'stratum_L': st, 'ok_L15': np.ones(n, np.uint8), 'trade_L15': trade, 'group': t // DAY,
              'asset': np.zeros(n, np.int8), 'X': np.zeros((n, 0), np.int8)}
    return ArrayPart(meta, arrays), d0


def test_matched_placebo_same_stratum_and_day():
    part, d0 = placebo_part()
    t, st = part['t'], part['stratum_L']
    taken = np.array([0, 5, 30, 61, 100, 150, 200])
    pool = PlaceboPool(part, 'L', 15)
    vals, info = pool.draw(taken, seeds=8, seed=3)
    want = 100 * st[taken] + (t[taken] // DAY - d0)
    assert np.allclose(vals, want)                          # every draw is from the same stratum and day
    assert info['same_day'] == len(taken) and info['fallback'] == 0
    v2, _ = pool.draw(taken, seeds=8, seed=3)
    assert np.array_equal(vals, v2)                         # deterministic by seed
    # remove the pool rows of (stratum 0, day 1): those trades fall back to stratum 0 on another day of the split
    ok = part['ok_L15'].copy()
    ok[(st == 0) & (t // DAY - d0 == 1)] = 0
    part.arrays['ok_L15'] = ok
    row = int(np.flatnonzero((st == 0) & (t // DAY - d0 == 1))[0])
    pool = PlaceboPool(part, 'L', 15)
    vals, info = pool.draw(np.array([row]), seeds=8, seed=1)
    assert info['fallback'] == 1
    assert vals[0] != 1.0 and 0 <= vals[0] <= 3              # stratum 0, days 0/2/3 averaged over 8 seeds
    # matched_placebo books the averaged placebo $ on the taken trade's day, every day of the span present
    span = (int((d0 - 1) * DAY), int((d0 + 5) * DAY))
    d = matched_placebo(part, 'L', 15, np.array([0, 5]), seeds=8, seed=3, span=span)
    assert len(d) == 6 and sum(d.values()) == pytest.approx(float(want[0] + want[1]))


# ---------------------------------------------------------------- bootstrap, BHY, Jaccard

def test_stationary_bootstrap():
    rng = np.random.default_rng(0)
    pos = rng.normal(1.0, 1.0, 200)
    assert stationary_bootstrap_p(pos, 5, 2000, 1) < 1e-6
    assert stationary_bootstrap_p(-pos, 5, 2000, 1) > 0.99
    assert stationary_bootstrap_p(np.zeros(100)) == 1.0
    r = stationary_bootstrap_test(pos, 5, 2000, 1)
    assert r['p'] == max(r['p_emp'], r['p_norm']) and r['p_emp'] == 0.0
    assert stationary_bootstrap_p(pos, 5, 500, 9) == stationary_bootstrap_p(pos, 5, 500, 9)
    # the SE of an autocorrelated series is larger than iid's: blocks keep the dependence
    ar = np.zeros(400)
    e = rng.normal(0, 1, 400)
    for i in range(1, 400):
        ar[i] = 0.8 * ar[i - 1] + e[i]
    se5 = stationary_bootstrap_test(ar, 5, 2000, 2)['se']
    se1 = stationary_bootstrap_test(ar, 1, 2000, 2)['se']
    assert se5 > 1.5 * se1
    # null series: p roughly uniform (calibration)
    ps = [stationary_bootstrap_p(rng.normal(0, 1, 120), 5, 400, s) for s in range(150)]
    assert 0.35 < float(np.mean(ps)) < 0.65
    assert 0.03 < float(np.mean(np.array(ps) < 0.1)) < 0.2


def test_bootstrap_p_uses_the_student_t_tail_on_short_series():
    """Review fix (Nov 6): the parametric part of p is the t tail with n - 1 df on mean / se, not the normal tail, which
    was anti-conservative on 39-47 day series below p = 5e-4 (the BHY thresholds)."""
    from scipy.special import ndtr
    from scipy.stats import t as student_t
    rng = np.random.default_rng(5)
    x = rng.normal(0.9, 1.0, 39)                         # a strong 39-day series: p far below 1 / draws
    r = stationary_bootstrap_test(x, 5, 2000, 3)
    z = r['mean'] / r['se']
    assert r['p_emp'] == 0.0 and r['p'] == r['p_t'] == r['p_norm']
    assert r['p_t'] == pytest.approx(float(student_t.sf(z, df=38)), rel=1e-12)
    assert r['p_t'] > 3 * float(ndtr(-z))                # the old normal tail understated it several times here
    assert stationary_bootstrap_test(np.r_[x, -x], 5, 500, 3)['p'] > 0.05


def bhy_reference(ps, q):
    """Textbook BY step-up: reject the k* smallest, k* = max{k : p_(k) <= k q / (m c_m)}."""
    p = np.asarray(ps, float)
    m = len(p)
    c = sum(1 / i for i in range(1, m + 1))
    o = np.argsort(p, kind='stable')
    ok = [k for k in range(1, m + 1) if p[o[k - 1]] <= k * q / (m * c)]
    out = np.zeros(m, bool)
    if ok:
        out[o[:max(ok)]] = True
    return out


def registry_bhy():
    try:
        src = subprocess.run(['git', 'show', 'origin/claude/project-thread-79ntof:research/registry.py'], cwd=REPO,
                             capture_output=True, text=True, timeout=30)
    except Exception:
        return None
    if src.returncode != 0 or 'def bhy' not in src.stdout:
        return None
    return src.stdout


def test_bhy_matches_references(tmp_path):
    rng = np.random.default_rng(5)
    cases = [[0.001, 0.01, 0.03, 0.5], list(rng.uniform(0, 1, 50)),
             list(np.concatenate([rng.uniform(0, 1e-4, 10), rng.uniform(0, 1, 90)])), [0.2], [], [np.nan, 0.001, 0.02]]
    for ps in cases:
        for q in (0.05, 0.10):
            clean = [1.0 if not np.isfinite(x) else x for x in ps]
            assert bhy(ps, q).tolist() == bhy_reference(clean, q).tolist()
    from allpairs.aph import bhy as aph_bhy
    for ps in cases[:3]:
        assert np.allclose(bhy_adjust(ps), aph_bhy(ps), atol=1e-4)
    src = registry_bhy()
    if src is None:
        pytest.skip('research/registry.py (origin/claude/project-thread-79ntof) not available in this checkout')
    path = tmp_path / 'registry_79ntof.py'
    path.write_text(src)
    spec = importlib.util.spec_from_file_location('registry_79ntof', path)
    reg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reg)
    for ps in cases:
        out = reg.bhy(list(ps), 0.10)
        assert [r for _, r in out] == bhy(ps, 0.10).tolist()
        if out:
            assert np.allclose([a for a, _ in out], bhy_adjust(ps))


def test_jaccard():
    a = np.array([1, 1, 0, 0, 1], bool)
    b = np.array([1, 0, 0, 1, 1], bool)
    assert jaccard(a, b) == pytest.approx(2 / 4)
    assert jaccard(np.array([1, 2, 3]), np.array([3, 4])) == pytest.approx(1 / 4)
    assert jaccard(np.zeros(3, bool), np.zeros(3, bool)) == 0.0


# ---------------------------------------------------------------- splits, keys, shifts

def test_split_rows_close_rule_and_busy_key():
    t = np.array([ms('2026-06-21') + 60 * MIN, ms('2026-06-21') + 120 * MIN, ms('2026-07-01')], dtype=np.int64)
    close = np.array([ms('2026-06-21') + 200 * MIN, ms('2026-06-22') + 30 * MIN, ms('2026-07-01') + 300 * MIN])
    meta = {'ct': 'tennis', 'scope': 'ATP', 'features': []}
    part = ArrayPart(meta, {'t': t, 'close': close, 'group': np.array([7, 8, 9]), 'asset': np.zeros(3, np.int8)})
    assert split_of(t, 15, 'tennis').tolist() == ['A', 'A', 'B']
    assert split_rows(part, 15).tolist() == ['A', '', 'B']   # the second market closes after the A split ends
    assert busy_key(part).tolist() == [7, 8, 9]              # tennis: one position per event
    perp = ArrayPart({'ct': 'perp', 'scope': 'BTC', 'features': []},
                     {'t': t, 'group': np.array([1, 1, 2]), 'asset': np.zeros(3, np.int8)})
    assert busy_key(perp).tolist() == [0, 0, 0]


def test_shift_index_within_contract():
    t = np.array([0, 0, 1, 1, 2, 2], dtype=np.int64) * MIN
    mkt = np.array([5, 6, 5, 6, 5, 6])
    part = ArrayPart({'ct': 'tennis', 'scope': 'ATP', 'features': []}, {'t': t, 'mkt': mkt, 'group': np.zeros(6, np.int64)})
    prev, nxt = shift_index(part)
    assert prev.tolist() == [-1, -1, 0, 1, 2, 3]
    assert nxt.tolist() == [2, 3, 4, 5, -1, -1]
