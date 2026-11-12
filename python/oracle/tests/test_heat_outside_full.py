"""OR-XD full (Amendment 3 in python/oracle/prereg/OR-XD.md; python/oracle/heat_outside.py: full_values, full_readings, AggStore, the
hm2_outside_readings keywords): the new readings from the DATA CONTRACT files (metrics, premium + funding, spot / perp aggTrade
reducers, bookDepth) against brute force, causality of every new reading (cut the future, with the exact boundary), the known-time
rules (metrics S + 5 min, premium stamp delay, F from earlier days only), the twin rule (Net15 / Sweep swap, Count60 / LS / PREM / BOOKP
do not), the refusal of 2026 rows, skips with reasons, the frozen lite readings unchanged. All data here is synthetic."""
import hashlib
import json
import os

import numpy as np
import pandas as pd
import pytest

from oracle import heat, heat_outside as xd
from oracle.common import DAY, MIN, ms

T0 = ms('2024-11-01')
DAYS = 60
N = DAYS * 1440
A_HI = 48 * 1440
CLOSE = lambda t: T0 + (t + 1) * MIN                      # the close of row t (the decision time)
NEW = xd.FULL_LEAGUE
LS = [x for x in NEW if x.startswith('LS:')]
PREM = ['PREM:PredFund', 'PREM:PredMinusLast']


@pytest.fixture(autouse=True, scope='module')
def _small_a():
    mp = pytest.MonkeyPatch()
    mp.setattr(xd, 'WHALE_Q', 0.01)                        # 30 trades a minute here, not thousands: a 1% tail gives the 15-minute windows some prints
    mp.setattr(xd, 'MIN_A_DAYS', 5)
    yield
    mp.undo()                                              # (the synthetic A is 48 days, with only the last ~13 inside every rolling history)


# ------------------------------------------------------------------------------------------------ synthetic contract files
def make_sp(seed=0):
    rng = np.random.default_rng(seed)
    gap = np.zeros(N, bool)
    for a in (5000, 30000, 61000):
        gap[a:a + int(rng.integers(2, 12))] = True
    c = 3000 * np.exp(np.cumsum(rng.normal(0, 6e-4, N)))
    o = np.r_[c[0], c[:-1]]
    v = rng.uniform(50, 150, N)
    return {'t0': T0, 'n': N, 'gap': gap, 'c': c, 'o': o, 'h': np.maximum(o, c) * 1.0002, 'l': np.minimum(o, c) * 0.9998, 'v': v,
            'tb': v * rng.uniform(0.3, 0.7, N), 'tick': np.full(N, 1.0)}


def make_metrics(seed=1, lo=-3 * DAY, drop=0.03):
    rng = np.random.default_rng(seed)
    S = np.arange(T0 + lo, T0 + N * MIN, 5 * MIN, dtype=np.int64)
    K = len(S)

    def walk(sd, base):
        return base * np.exp(np.cumsum(rng.normal(0, sd, K)) * 0.2 + rng.normal(0, sd, K))

    df = pd.DataFrame({'S': S, 'stamp': S, 'conv': 'new', 'sum_open_interest': 1e5 * np.exp(rng.normal(0, 0.01, K)),
                       'sum_open_interest_value': 3e8, 'count_toptrader_long_short_ratio': walk(0.01, 1.2),
                       'sum_toptrader_long_short_ratio': walk(0.012, 1.1), 'count_long_short_ratio': walk(0.01, 1.5),
                       'sum_taker_long_short_vol_ratio': 1.0, 'file': 'x'})
    keep = rng.random(K) > drop
    keep[20000:20030] = False                                # a 2.5 hour hole
    return df[keep].reset_index(drop=True)


def make_premium(seed=2, drop=0.01):
    rng = np.random.default_rng(seed)
    ts = np.arange(T0 - DAY, T0 + N * MIN, MIN, dtype=np.int64)
    prem = 1.2e-3 * np.sin(np.arange(len(ts)) / 900) + rng.normal(0, 3e-5, len(ts))      # excursions beyond the +-0.05% band of F
    df = pd.DataFrame({'ts': ts, 'o': prem, 'h': prem, 'l': prem, 'c': prem})
    return df[rng.random(len(ts)) > drop].reset_index(drop=True)


def make_funding(seed=3, hours=4, jitter=3):
    rng = np.random.default_rng(seed)
    Ts = np.arange(T0 - 20 * DAY, T0 + N * MIN, hours * 60 * MIN, dtype=np.int64)
    rate = np.clip(1e-4 + np.cumsum(rng.normal(0, 2e-5, len(Ts))) * 0.3 + rng.normal(0, 3e-5, len(Ts)), -7e-4, 7e-4)
    return pd.DataFrame({'calc_time': Ts + jitter, 'funding_interval_hours': hours, 'last_funding_rate': rate})


def make_book(seed=4):
    rng = np.random.default_rng(seed)
    ts = np.arange(T0 + 3 * DAY, T0 + N * MIN, 30_000, dtype=np.int64)
    return pd.DataFrame({'ts': ts, 'bid_1pct': rng.uniform(1e6, 3e6, len(ts)), 'ask_1pct': rng.uniform(1e6, 3e6, len(ts))})


def make_agg(seed=5, rate=30):
    """Per-minute reducer rows for DAYS days, from random trades (heavy-tailed sizes): the columns of the contract."""
    rng = np.random.default_rng(seed)
    nt = rng.poisson(rate, N)
    mi = np.repeat(np.arange(N), nt)
    buy = rng.random(len(mi)) < 0.5
    usd = np.exp(rng.normal(np.log(800), 1.5, len(mi)))
    cols = {'ts': T0 + np.arange(N, dtype=np.int64) * MIN}
    bc = lambda m, w=None: np.bincount(mi[m], weights=None if w is None else w[m], minlength=N)
    cols['n_buy'], cols['n_sell'] = bc(buy).astype(np.int32), bc(~buy).astype(np.int32)
    cols['usd_buy'], cols['usd_sell'] = bc(buy, usd), bc(~buy, usd)
    for k, e in enumerate(xd.WHALE_EDGES):
        g = usd >= e
        cols[f'nb_ge_{k}'], cols[f'ns_ge_{k}'] = bc(g & buy).astype(np.int32), bc(g & ~buy).astype(np.int32)
        cols[f'ub_ge_{k}'], cols[f'us_ge_{k}'] = bc(g & buy, usd), bc(g & ~buy, usd)
    for side in ('b', 's'):                                   # nested thresholds: a $1M second is also a $500k and a $250k second
        prev = (rng.random(N) < 0.02).astype(np.int32)
        for tag in ('250k', '500k', '1m', '2m'):
            cols[f'sw_{side}_{tag}'] = prev * rng.integers(1, 3, N).astype(np.int32)
            prev = prev * (rng.random(N) < 0.5).astype(np.int32)
    df = pd.DataFrame(cols)
    return df[(df.n_buy + df.n_sell) > 0].reset_index(drop=True)


def write_agg(directory, df, cut_after_row=None):
    """The frame as <YYYY-MM>.parquet month files (rows after minute row `cut_after_row` dropped when given)."""
    import pyarrow as pa
    import pyarrow.parquet as pq
    os.makedirs(directory, exist_ok=True)
    if cut_after_row is not None:
        df = df[df.ts <= T0 + cut_after_row * MIN]
    mon = pd.to_datetime(df.ts, unit='ms').dt.strftime('%Y-%m')
    for mo, part in df.groupby(mon):
        pq.write_table(pa.Table.from_pandas(part.reset_index(drop=True), preserve_index=False), os.path.join(directory, f'{mo}.parquet'))
    return directory


@pytest.fixture(scope='module')
def world(tmp_path_factory):
    d = tmp_path_factory.mktemp('xdfull')
    w = {'dir': d, 'sp': make_sp(), 'met': make_metrics(), 'prem': make_premium(), 'fund': make_funding(), 'book': make_book(),
         'agg_s': make_agg(5), 'agg_p': make_agg(6, rate=40)}
    w['dir_s'], w['dir_p'] = write_agg(str(d / 'agg_spot'), w['agg_s']), write_agg(str(d / 'agg_perp'), w['agg_p'])
    w['pp'] = {'gap': w['sp']['gap'] | (np.arange(N) % 9999 == 0)}
    return w


def inputs_of(w, delay=0, **over):
    inp = dict(metrics=w['met'], premium=w['prem'], premium_stamp={'fits': 'next' if delay else 'same', 'resolved': True, 'extra_delay_minutes': int(bool(delay))}, funding=w['fund'],
               agg_spot=w['dir_s'], agg_perp=w['dir_p'], book=w['book'])
    inp.update(over)
    return inp


@pytest.fixture(scope='module')
def full(world):
    return xd.full_values(world['sp'], world['pp'], **inputs_of(world))


def same(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    return bool((((np.isnan(a) & np.isnan(b)) | (a == b))).all())


# ------------------------------------------------------------------------------------------------ (a) all families produce values
def test_every_new_reading_has_values(full):
    assert full['skipped'] == {}
    for nm in NEW + xd.FULL_REFS:
        v = full['values'][nm]
        assert len(v) == N and np.isfinite(v[:A_HI]).sum() > 1000, nm
    inf = full['info']
    assert inf['metrics']['known_rule'].startswith('S + 5 min') and inf['book']['median_spacing_ms'] == 30_000
    assert set(inf['prem']['reconstruction_error_by_year']) == {'2024'} and inf['prem']['interval_hours_seen'] == {'4': inf['prem']['interval_hours_seen']['4']}
    assert inf['whale_spot']['f_days_with_value'] > 20 and 0 < inf['whale_spot']['realised_share_of_trades_at_f']['median'] < 2 * xd.WHALE_Q


# ------------------------------------------------------------------------------------------------ (b) formulas against brute force
def test_ls_matches_brute_force_and_the_known_time_is_s_plus_5_min(world, full):
    met = xd.prep_metrics(world['met'])
    s = met.set_index('S')
    Sall = np.arange(int(met.S.iloc[0]), int(met.S.iloc[-1]) + 1, 5 * MIN, dtype=np.int64)
    for col, nm in (('count_long_short_ratio', 'LS:Global z'), ('sum_toptrader_long_short_ratio', 'LS:TopPos z'),
                    ('count_toptrader_long_short_ratio', 'LS:TopAcc z')):
        x = np.log(s[col].reindex(Sall))
        for r in (3000, 20123, 40000, 55555):
            close = CLOSE(r)
            Sk = (close - xd.LS_KNOWN) // (5 * MIN) * (5 * MIN)             # the latest snapshot known at the close
            got = full['values'][nm][r]
            for q in range(3):                                              # carried at most 10 minutes
                Sq = Sk - q * 5 * MIN
                if close - (Sq + xd.LS_KNOWN) > xd.CARRY:
                    break
                w = x.loc[Sq - 288 * 5 * MIN:Sq - 5 * MIN].dropna()           # [S - 24 h, S): the row itself is not in its window
                if np.isfinite(x.loc[Sq]) and len(w) >= 231:
                    assert got == pytest.approx((x.loc[Sq] - w.mean()) / w.std(ddof=1), rel=1e-9, abs=1e-9), (nm, r)
                    break
    # the change: needs the snapshot exactly 60 minutes before, / sd of the 60-minute changes of the previous 24 h
    x = np.log(s['sum_toptrader_long_short_ratio'].reindex(Sall))
    d = x - x.shift(12)
    r = 40000
    Sk = (CLOSE(r) - xd.LS_KNOWN) // (5 * MIN) * (5 * MIN)
    i = int((Sk - Sall[0]) // (5 * MIN))
    w = d.iloc[i - 288:i].dropna()
    if np.isfinite(d.iloc[i]) and len(w) >= 231:
        assert full['values']['LS:TopPosChg60'][r] == pytest.approx(d.iloc[i] / w.std(ddof=1), rel=1e-9)
    # the first row that sees the snapshot S is the one whose close is S + 5 min
    j = int(np.flatnonzero(Sall == Sk)[0])
    assert (CLOSE(r) - (Sk + xd.LS_KNOWN)) == 0 or CLOSE(r) > Sk + xd.LS_KNOWN


def test_prem_matches_brute_force(world, full):
    prem = world['prem'].set_index('ts')['c']
    fund = xd.prep_funding(world['fund'])
    Ts, rate = fund.Ts.to_numpy(), fund.rate.to_numpy()
    n_out = 0
    rows = [20000, 40001, 40240, 50000, 24001, 24005, 24060, 24241, 24245]       # (+1 / +5 minutes after a 4 h settlement: calc_time is 3 ms past the minute)
    ch = np.diff(rate)
    for r in rows:
        o = T0 + r * MIN
        k = int(np.searchsorted(Ts, o, side='right') - 1)
        n_ = (o - Ts[k]) // MIN + 1
        bars = [(p, prem.get(Ts[k] + (p - 1) * MIN, np.nan)) for p in range(1, n_ + 1)]
        ok = [(p, v) for p, v in bars if np.isfinite(v)]
        if len(ok) < np.ceil(0.8 * n_ - 1e-9) or not np.isfinite(prem.get(o, np.nan)):
            assert np.isnan(full['values']['PREM:PredFund'][r])
            continue
        P = sum(p * v for p, v in ok) / sum(p for p, _ in ok)
        I = 1e-4 * 4 / 8
        F = P + min(max(I - P, -5e-4), 5e-4)
        assert full['values']['PREM:PredFund'][r] == pytest.approx(F, rel=1e-12, abs=1e-15)
        n_out += abs(I - P) > 5e-4
        sd = np.std(ch[k - 90:k], ddof=1)                                  # the 90 changes ending at settlement k
        assert full['values']['PREM:PredMinusLast'][r] == pytest.approx((F - rate[k]) / sd, rel=1e-9)
    assert n_out >= 3                                                      # the clamp is really exercised, not vacuous
    v = full['values']['PREM:PredFund']
    assert len(np.unique(v[np.isfinite(v)])) > 1000                       # F is not a constant I (in-band rows equal I only when P is in band)


def test_premium_delay_reads_the_fetch_jobs_stamp_schema():
    """The exact dict outside_reduce.premium_stamp_test writes to premium_stamp.json (resolved or not) is understood."""
    from oracle import outside_reduce as red
    rng = np.random.default_rng(3)
    ts = np.arange(T0, T0 + 3000 * MIN, MIN, dtype=np.int64)
    x = np.cumsum(rng.normal(0, 1e-4, len(ts) + 1))
    idx = pd.DataFrame({'ts': ts, 'c': np.full(len(ts), 100.0)})
    perp = pd.DataFrame({'ts': ts, 'c': 100.0 * (1 + x[:-1])})
    for fit, shift in (('same', 0), ('next', 1)):
        prem = pd.DataFrame({'ts': ts, 'c': x[shift:len(ts) + shift] + rng.normal(0, 1e-6, len(ts))})
        st = red.premium_stamp_test(prem, perp, idx)
        assert st['fits'] == fit and st['resolved'] is True
        assert xd.premium_delay(st) == (1 if fit == 'next' else 0)
    flat = pd.DataFrame({'ts': ts[:50], 'c': 0.0})
    st = red.premium_stamp_test(flat, perp.iloc[:50], idx.iloc[:50])
    assert st['resolved'] is False
    with pytest.raises(xd._Skip):
        xd.premium_delay(st)
    with pytest.raises(xd._Skip):
        xd.premium_delay({'fits': 'unresolved'})
    assert xd.premium_delay({'fits': 'next', 'resolved': True, 'extra_delay_minutes': 1}) == 1
    assert xd.premium_delay({'fits': 'same', 'resolved': True, 'extra_delay_minutes': 0}) == 0


def test_prem_weights_inside_the_segment_when_calc_time_is_off_the_minute(world):
    """calc_time a few ms past the minute: the bar at Ts_k belongs to the previous interval and enters this one with weight 1."""
    fund = world['fund']
    assert (fund.calc_time % MIN != 0).all()
    f, _, _ = xd.prem_series(xd.prep_premium(world['prem']), xd.prep_funding(fund), T0, N)
    prem = world['prem'].set_index('ts')['c']
    Ts = xd.prep_funding(fund).Ts.to_numpy()
    for r in (24001, 24002, 24005, 24241):
        o = T0 + r * MIN
        k = int(np.searchsorted(Ts, o, side='right') - 1)
        bars = [(p, prem.get(Ts[k] + (p - 1) * MIN, np.nan)) for p in range(1, (o - Ts[k]) // MIN + 2)]
        ok = [(p, v) for p, v in bars if np.isfinite(v)]
        if np.isnan(f[r]):
            continue
        P = sum(p * v for p, v in ok) / sum(p for p, _ in ok)
        assert f[r] == pytest.approx(min(max(1e-4 * 4 / 8, P - 5e-4), P + 5e-4), rel=1e-12, abs=1e-15)


def test_in_band_prem_fund_equals_the_interest_rate_exactly(world, full):
    v = full['values']['PREM:PredFund']
    v = v[np.isfinite(v)]
    assert (v == 1e-4 * 4 / 8).any()
    assert set(np.unique(v[np.abs(v - 5e-5) < 1e-9])) == {5e-5}            # no I +- ulp values


def test_ls_is_na_for_a_whole_window_after_a_gap_of_more_than_an_hour(world):
    met = world['met']
    t = T0 + 20 * DAY
    hole = met[(met.S >= t) & (met.S < t + 3 * 3600_000)].index
    cut = met.drop(hole)
    sp = {'t0': T0, 'n': N, 'gap': np.zeros(N, bool)}
    v = xd.full_values(sp, None, metrics=cut)['values']['LS:Global z']
    ref = xd.full_values(sp, None, metrics=met)['values']['LS:Global z']
    r0 = (t + 3 * 3600_000 - T0) // MIN
    after = slice(int(r0) + 10, int(r0) + 24 * 60 - 20)
    assert np.isnan(v[after]).all() and np.isfinite(ref[after]).any()
    assert np.isfinite(v[int(r0) + 24 * 60 + 60: int(r0) + 24 * 60 + 600]).any()


def test_prem_minus_last_is_na_when_the_sd_window_spans_a_missing_stretch(world):
    fund = world['fund'].copy()
    n_ = len(fund)
    drop = fund.index[(fund.calc_time > T0 - 10 * DAY) & (fund.calc_time < T0 + 8 * DAY)]            # three days of 4 h settlements gone
    sp = {'t0': T0, 'n': N, 'gap': np.zeros(N, bool)}
    a = xd.full_values(sp, None, premium=world['prem'], funding=fund.drop(drop), premium_stamp={'fits': 'same'})['values']['PREM:PredMinusLast']
    b = xd.full_values(sp, None, premium=world['prem'], funding=fund, premium_stamp={'fits': 'same'})['values']['PREM:PredMinusLast']
    k = int((T0 + 12 * DAY - T0) // MIN)
    assert np.isnan(a[k]) and np.isfinite(b[k])


def test_agg_days_without_trades_are_holes_not_quiet_days(world, tmp_path):
    df = world['agg_s']
    D0 = 30
    hole = (df.ts >= T0 + D0 * DAY) & (df.ts < T0 + (D0 + 2) * DAY)
    d = write_agg(str(tmp_path / 'hole'), df[~hole])
    v = xd.full_values(world['sp'], None, agg_spot=d)['values']
    ref = xd.full_values(world['sp'], None, agg_spot=world['dir_s'])['values']
    rows = slice(D0 * 1440, (D0 + 2) * 1440)
    for nm in ('WHALE:Net15', 'WHALE:Count60', 'WHALE:Sweep'):
        assert np.isnan(v[nm][D0 * 1440 + 60:(D0 + 2) * 1440]).all(), nm            # (the first rows still read windows that end before the hole)
    assert np.isfinite(ref['WHALE:Count60'][rows]).any()
    # Count60 stays NA for the 7 days after the hole; F (all of Net15's rows) for the 30 days after
    assert np.isnan(v['WHALE:Count60'][(D0 + 2) * 1440 + 60:(D0 + 9) * 1440 - 1]).all()
    st = xd.AggStore(d, T0, N)
    kstar = xd.whale_edges_by_day(st)[0]
    assert (kstar[D0 + 2:D0 + 32] == -1).all()


def test_prem_reconstruction_error_is_reported_for_both_regimes(full):
    rec = full['info']['prem']['reconstruction_error_by_year']['2024']
    assert rec['n'] > 100 and rec['median_abs_old'] >= 0 and rec['p99_abs_old'] >= rec['median_abs_old']
    assert 'median_abs_new_8_over_N' in rec and full['info']['prem']['interval_column_mismatch'] == 0


def test_whale_f_net15_count60_sweep_match_brute_force(world, full):
    df = world['agg_s'].set_index('ts').reindex(T0 + np.arange(N, dtype=np.int64) * MIN).fillna(0.0)
    store = xd.AggStore(world['dir_s'], T0, N)
    kstar, real, _ = xd.whale_edges_by_day(store)
    cnt = lambda k: (df[f'nb_ge_{k}'] + df[f'ns_ge_{k}']).to_numpy()
    tot = (df.n_buy + df.n_sell).to_numpy()
    for D in (31, 40, 55):
        a, b = (D - 30) * 1440, D * 1440
        share = np.array([cnt(k)[a:b].sum() / tot[a:b].sum() for k in range(24)])
        assert kstar[D] == np.flatnonzero(share <= xd.WHALE_Q)[0]
    assert (kstar[:30] == -1).all()
    D = 45
    k = int(kstar[D])
    net = (df[f'ub_ge_{k}'] - df[f'us_ge_{k}']).to_numpy()
    usd = (df.usd_buy + df.usd_sell).to_numpy()
    for r in (D * 1440 + 100, D * 1440 + 900):
        assert full['values']['WHALE:Net15'][r] == pytest.approx(net[r - 14:r + 1].sum() / usd[r - 14:r + 1].sum(), rel=1e-9)
        x60 = lambda rr: cnt(k)[rr - 59:rr + 1].sum()
        base = np.array([x60(r - 1440 * j) for j in range(1, 8)])
        assert full['values']['WHALE:Count60'][r] == pytest.approx((x60(r) - np.median(base)) / max(base.std(ddof=1), 1.0), rel=1e-9)
    sb, ss = df['sw_b_1m'].to_numpy() > 0, df['sw_s_1m'].to_numpy() > 0
    for r in range(D * 1440, D * 1440 + 3000):
        wb, ws = sb[r - 4:r + 1], ss[r - 4:r + 1]
        lb = np.flatnonzero(wb)
        ls_ = np.flatnonzero(ws)
        exp = 0.0
        if len(lb) and (not len(ls_) or lb[-1] > ls_[-1]):
            exp = 1.0
        elif len(ls_) and (not len(lb) or ls_[-1] > lb[-1]):
            exp = -1.0
        assert full['values']['WHALE:Sweep'][r] == exp, r


def test_bookp_known_at_its_stamp_and_carried_10_minutes(world, full):
    bk = world['book']
    imb = ((bk.bid_1pct - bk.ask_1pct) / (bk.bid_1pct + bk.ask_1pct)).to_numpy()
    ts = bk.ts.to_numpy()
    r = 12345
    j = np.searchsorted(ts, CLOSE(r), side='right') - 1
    assert full['values']['BOOKP:Imb1'][r] == imb[j]
    assert np.isnan(full['values']['BOOKP:Imb1'][:3 * 1440 - 1]).all()          # the file starts 3 days in
    # exactly at the close counts; one millisecond later does not; a stamp older than 10 minutes is not carried
    b2 = pd.DataFrame({'ts': [CLOSE(r), CLOSE(r + 5) + 1], 'bid_1pct': [3.0, 1.0], 'ask_1pct': [1.0, 3.0]})
    v = xd.book_imbalance(b2, T0, N)
    assert v[r] == 0.5 and v[r + 5] == 0.5 and v[r + 6] == -0.5 and np.isnan(v[r - 1])
    v1 = xd.book_imbalance(b2.iloc[:1], T0, N)
    assert v1[r + 10] == 0.5 and np.isnan(v1[r + 11])


# ------------------------------------------------------------------------------------------------ (c) cut the future
def noise_metrics(met, t, rng):
    """Every snapshot whose known time (S + 5 min) is after the close of row t replaced by noise."""
    m = met.copy()
    late = (m.S + xd.LS_KNOWN > CLOSE(t)).to_numpy()
    for c in ('count_long_short_ratio', 'sum_toptrader_long_short_ratio', 'count_toptrader_long_short_ratio'):
        m.loc[late, c] = np.exp(rng.normal(0, 1, int(late.sum())))
    return m


CUT_ROWS = [3000, 40001, 52000]


def _snap_known_rows(met):
    """Rows t where a snapshot is known exactly at the close (t = (S + 5 min - T0) / 1 min - 1) and the row before."""
    S = xd.prep_metrics(met).S.to_numpy()
    out = []
    for q in (7000, 30000, 47000):
        Sk = int(S[np.searchsorted(S, T0 + q * MIN)])
        t = (Sk + xd.LS_KNOWN - T0) // MIN - 1
        out += [t - 1, t]
    return out


@pytest.mark.parametrize('t_kind', ['random', 'boundary'])
def test_cut_the_future_ls(world, full, t_kind):
    rng = np.random.default_rng(7)
    rows = CUT_ROWS if t_kind == 'random' else _snap_known_rows(world['met'])
    for t in rows:
        cut = xd.full_values(world['sp'], world['pp'], metrics=noise_metrics(world['met'], t, rng))
        for nm in LS:
            assert same(full['values'][nm][:t + 1], cut['values'][nm][:t + 1]), (nm, t)
    # the removed variant: rows known after the close are simply absent
    t = rows[1]
    met = world['met']
    cut = xd.full_values(world['sp'], world['pp'], metrics=met[met.S + xd.LS_KNOWN <= CLOSE(t)])
    for nm in LS:
        assert same(full['values'][nm][:t + 1], cut['values'][nm][:t + 1]), (nm, t)


def test_ls_snapshot_stamped_one_ms_after_its_known_time_does_not_change_the_row(world):
    """A snapshot with S + 5 min = close(t) is used at row t; stamped 1 ms later (S + 1 ms: ceiled to the next grid slot, known 5
    minutes later) it is not: the row equals the one computed with the snapshot absent."""
    met = xd.prep_metrics(world['met']).reset_index(drop=True)
    k = int(np.searchsorted(met.S.to_numpy(), T0 + 30000 * MIN))
    t = (int(met.S[k]) + xd.LS_KNOWN - T0) // MIN - 1
    assert CLOSE(t) == met.S[k] + xd.LS_KNOWN
    base = xd.full_values(world['sp'], None, metrics=met)['values']
    late = met.copy()
    late.loc[k, 'S'] = met.S[k] + 1
    gone = met.drop(index=k)
    a = xd.full_values(world['sp'], None, metrics=late)['values']
    b = xd.full_values(world['sp'], None, metrics=gone)['values']
    for nm in LS:
        assert same(a[nm][:t + 1], b[nm][:t + 1]), nm
    assert any(not same(base[nm][t:t + 1], b[nm][t:t + 1]) for nm in LS)       # not vacuous: with the snapshot known at the close, row t does change


@pytest.mark.parametrize('delay', [0, 1])
def test_cut_the_future_prem_and_the_stamp_delay(world, delay):
    w = world
    ref = xd.full_values(w['sp'], None, premium=w['prem'], premium_stamp={'fits': 'next' if delay else 'same', 'resolved': True, 'extra_delay_minutes': int(bool(delay))}, funding=w['fund'])['values']
    rng = np.random.default_rng(8)
    for t in CUT_ROWS + [40240 - 1, 40240]:
        p2 = w['prem'].copy()
        late = (p2.ts > T0 + (t - delay) * MIN).to_numpy()                      # bars opening after the last bar known at the close
        p2.loc[late, 'c'] = rng.normal(0, 1e-2, int(late.sum()))
        f2 = w['fund'][w['fund'].calc_time + MIN <= CLOSE(t)]
        cut = xd.full_values(w['sp'], None, premium=p2, premium_stamp={'fits': 'next' if delay else 'same', 'resolved': True, 'extra_delay_minutes': int(bool(delay))}, funding=f2)['values']
        for nm in PREM:
            assert same(ref[nm][:t + 1], cut[nm][:t + 1]), (nm, t, delay)
    # exact boundary: the bar that opens AT the close of row t is unknown at t; with delay 1 the bar that closes at t is unknown too
    t = 40001
    for ts, who in ((CLOSE(t), 'open at the close'), (T0 + t * MIN, 'closes at the close')):
        p2 = w['prem'].copy()
        p2.loc[p2.ts == ts, 'c'] = 0.5
        cut = xd.full_values(w['sp'], None, premium=p2, premium_stamp={'fits': 'next' if delay else 'same', 'resolved': True, 'extra_delay_minutes': int(bool(delay))}, funding=w['fund'])['values']
        changed = not same(ref['PREM:PredFund'][t:t + 1], cut['PREM:PredFund'][t:t + 1])
        assert changed == (who == 'closes at the close' and delay == 0), (who, delay)


def test_premium_stamp_next_is_one_minute_later(world):
    w = world
    a = xd.full_values(w['sp'], None, premium=w['prem'], premium_stamp={'fit': 'same'}, funding=w['fund'])['values']
    b = xd.full_values(w['sp'], None, premium=w['prem'], premium_stamp={'fit': 'next'}, funding=w['fund'])['values']
    for nm in PREM:
        assert same(b[nm][1:], a[nm][:-1]) and np.isnan(b[nm][0])
    assert xd.premium_delay({'delay_minutes': 1}) == 1 and xd.premium_delay({'best': 'Next minute'}) == 1 and xd.premium_delay({'winner': 'same'}) == 0
    for bad in ({}, {'fit': 'maybe'}, {'resolved': False, 'fit': 'same'}):
        with pytest.raises(xd._Skip):
            xd.premium_delay(bad)


def test_settlement_is_known_at_calc_time_plus_one_minute(world):
    """A settlement with calc_time = the open of row t is known at the close of row t (calc_time + 1 min) and sets the rate of row t;
    with calc_time one millisecond later (the same minute Ts) it is not used before row t + 1. Rows before t are the same either way."""
    w = world
    k = 300
    f = w['fund'].copy()
    Ts = int(xd.prep_funding(f).Ts[k])
    t = (Ts - T0) // MIN
    prem = make_premium(drop=0.0)
    ref = {}
    for tag, calc in (('at', Ts), ('late', Ts + 1)):
        f2 = f.copy()
        f2.loc[f2.index[k], 'calc_time'] = calc
        f2.loc[f2.index[k], 'last_funding_rate'] = 0.0004                          # the new rate (the others are around 1e-4)
        ref[tag] = xd.full_values(w['sp'], None, premium=prem, premium_stamp={'fit': 'same'}, funding=f2)['values']['PREM:PredMinusLast']
    assert same(ref['at'][:t], ref['late'][:t]) and np.allclose(ref['at'][t + 1:t + 400], ref['late'][t + 1:t + 400], rtol=1e-9, equal_nan=True)
    assert np.isfinite(ref['at'][t]) and np.isfinite(ref['late'][t]) and ref['at'][t] != ref['late'][t]


@pytest.mark.parametrize('market', ['spot', 'perp'])
def test_cut_the_future_whale(world, market, tmp_path):
    w = world
    key = 'agg_spot' if market == 'spot' else 'agg_perp'
    df = w['agg_s'] if market == 'spot' else w['agg_p']
    names = [f'{"WHALE" if market == "spot" else "WHALEP"}:{x}' for x in ('Net15', 'Count60', 'Sweep')]
    inp = {key: w['dir_s'] if market == 'spot' else w['dir_p']}
    full_ = xd.full_values(w['sp'], w['pp'], **inp)['values']
    rng = np.random.default_rng(9)
    for t in (45 * 1440 + 100, 52 * 1440 + 777, 52 * 1440):
        # (1) the rows after minute t removed; (2) the minute that opens at the close of t (known only at its own close) replaced by noise
        cutdir = write_agg(str(tmp_path / f'{market}{t}'), df, cut_after_row=t)
        cut = xd.full_values(w['sp'], w['pp'], **{key: cutdir})['values']
        d2 = df.copy()
        m = (d2.ts == T0 + (t + 1) * MIN).to_numpy()
        for c in d2.columns:
            if c != 'ts':
                d2.loc[m, c] = d2.loc[m, c] * 50 + 7
        cut2 = xd.full_values(w['sp'], w['pp'], **{key: write_agg(str(tmp_path / f'{market}{t}b'), d2)})['values']
        for nm in names + ([] if market == 'perp' else ['REF:Sweep500']):
            assert same(full_[nm][:t + 1], cut[nm][:t + 1]), (nm, t)
            assert same(full_[nm][:t + 1], cut2[nm][:t + 1]), (nm, t, 'boundary')
    assert not same(full_[names[0]], cut[names[0]])                                 # the future does differ: the cut is not vacuous


def test_whale_f_uses_only_earlier_days(world, tmp_path):
    """F of day D is read from the 30 days before D: changing day D's own trades (a thousand large prints) leaves F of days <= D alone
    and may change F of later days."""
    df = world['agg_s'].copy()
    D = 40
    m = ((df.ts >= T0 + D * DAY) & (df.ts < T0 + (D + 1) * DAY)).to_numpy()
    for k in range(24):
        for c in ('nb', 'ns'):
            df.loc[m, f'{c}_ge_{k}'] = (df.loc[m, 'n_buy'] if c == 'nb' else df.loc[m, 'n_sell'])
    k0 = xd.whale_edges_by_day(xd.AggStore(world['dir_s'], T0, N))[0]
    k1 = xd.whale_edges_by_day(xd.AggStore(write_agg(str(tmp_path / 'dd'), df), T0, N))[0]
    assert (k0[:D + 1] == k1[:D + 1]).all()
    assert k1[D + 1] != k0[D + 1]


# ------------------------------------------------------------------------------------------------ (d) the twin rule
def test_twin_swaps_net15_and_sweep_but_not_the_level_readings(world, full):
    w = world
    s = xd.twin_signs(N, 3)
    tw = xd.full_values(w['sp'], w['pp'], signs=s, **inputs_of(w))
    for nm in ['LS:Global z', 'LS:TopPos z', 'LS:TopPosChg60', 'LS:TopAcc z', 'PREM:PredFund', 'PREM:PredMinusLast', 'BOOKP:Imb1',
               'WHALE:Count60', 'WHALEP:Count60']:
        assert same(full['values'][nm], tw['values'][nm]), nm                       # real level: identical on a twin
    for nm in ['WHALE:Net15', 'WHALE:Sweep', 'WHALEP:Net15', 'WHALEP:Sweep', 'REF:Sweep500']:
        assert not same(full['values'][nm], tw['values'][nm]), nm                   # direction: changes
    # every minute flipped: the direction readings change sign exactly, the counts do not
    allf = xd.full_values(w['sp'], w['pp'], signs=-np.ones(N), agg_spot=w['dir_s'], agg_perp=w['dir_p'])['values']
    for nm in ('WHALE:Net15', 'WHALE:Sweep', 'WHALEP:Net15', 'WHALEP:Sweep', 'REF:Sweep500', 'REFP:Sweep500'):
        a, b = full['values'][nm], allf[nm]
        assert same(np.where(np.isfinite(a), -a, np.nan), b), nm
    assert same(full['values']['WHALE:Count60'], allf['WHALE:Count60'])
    # a mixed twin: the sweep state is that of the swapped minutes
    sb, ss = w['agg_s'].set_index('ts').reindex(T0 + np.arange(N, dtype=np.int64) * MIN).fillna(0)[['sw_b_1m', 'sw_s_1m']].to_numpy().T
    st, _ = xd.sweep_state(np.where(s > 0, sb, ss), np.where(s > 0, ss, sb), np.ones(N, bool))
    assert same(st, tw['values']['WHALE:Sweep'])


def test_a_twin_follows_the_real_coins_skips_and_readings_carry_the_family(world):
    w = world
    R = xd.full_readings(w['sp'], w['pp'], A_HI, **inputs_of(w))
    assert [r['name'] for r in R['readings']] == NEW and R['skipped'] == []
    for r in R['readings']:
        assert r['family'] == xd.FULL_FAMILY[r['name']] and r['cond'] and r['k'] == 1
        assert (r.get('zones') is True) == (r['name'] not in xd.FULL_STATE)
        assert r['levels'] == (xd.SWEEP_LEVELS if r['name'] in xd.FULL_STATE else heat.ZONES)
    Rt = xd.full_readings(w['sp'], w['pp'], A_HI, skip=('LS:TopAcc z', 'WHALE:Sweep'), signs=xd.twin_signs(N, 2), **inputs_of(w))
    assert {'LS:TopAcc z', 'WHALE:Sweep'} <= set(Rt['skipped']) and 'LS:TopAcc z' not in Rt['edges']
    assert 'inherited' not in json.dumps(Rt['reasons']) and 'twins' in Rt['reasons']['WHALE:Sweep']


def test_zone_edges_come_from_a_rows_only_and_fixed_edges_reproduce_the_codes(world):
    w = world
    R = xd.full_readings(w['sp'], w['pp'], A_HI, keep=True, **inputs_of(w))
    for name in ('LS:Global z', 'PREM:PredFund', 'WHALE:Net15', 'BOOKP:Imb1'):
        x = R['values'][name]
        xa = x[:A_HI][np.isfinite(x[:A_HI])]
        assert np.allclose(R['edges'][name], np.quantile(xa, heat.ZONE_Q))
    # B rows replaced: edges unchanged
    sp2 = dict(w['sp'])
    met2 = w['met'].copy()
    late = met2.S >= T0 + A_HI * MIN
    met2.loc[late, 'count_long_short_ratio'] = 50.0
    R2 = xd.full_readings(sp2, w['pp'], A_HI, **inputs_of(w, metrics=met2))
    assert np.allclose(R2['edges']['LS:Global z'], R['edges']['LS:Global z'])
    # fixed edges (parity / hook): the same codes, no A rows looked at
    Rf = xd.full_readings(w['sp'], w['pp'], 0, edges=R['edges'], **inputs_of(w))
    for a, b in zip(R['readings'], Rf['readings']):
        assert a['name'] == b['name'] and np.array_equal(a['codes'], b['codes'])
    assert xd.full_readings(w['sp'], w['pp'], A_HI, edges={}, **inputs_of(w))['readings'] == []


def test_stale_rule_follows_the_engines_gap_rule(world):
    w = world
    R = xd.full_readings(w['sp'], w['pp'], A_HI, keep=True, **inputs_of(w))
    g = w['sp']['gap']
    r0 = int(np.flatnonzero(g)[0])
    for nm in NEW:
        assert np.isnan(R['values'][nm][r0]) and np.isnan(R['values'][nm][r0 + 50]), nm          # inside the 100 stale rows after a gap
    assert np.isnan(R['values']['WHALEP:Net15'][np.flatnonzero(w['pp']['gap'] & ~g)[0]])         # the perp readings also respect the perp's gaps


def test_near_duplicates_and_direction_coupling_cover_the_new_readings(world):
    w = world
    R = xd.full_readings(w['sp'], w['pp'], A_HI, keep=True, **inputs_of(w))
    nd = xd.full_near_duplicates(R['values'], A_HI, {'CVDP:15': np.random.default_rng(0).normal(size=N)})
    assert 'WHALE:Net15 ~ WHALEP:Net15' in nd and 'CVDP:15 ~ WHALE:Net15' in nd and 'LS:Global z ~ LS:TopPos z' in nd
    assert 'WHALE:Sweep ~ REF:Sweep500' in nd and nd['WHALE:Sweep ~ REF:Sweep500']['spearman'] > 0.5
    assert not any(k.startswith('CVDP:15 ~ CVDP') for k in nd)
    dc = xd.full_direction_coupling(R['values'], w['sp']['c'], R['gap'], A_HI)
    assert set(dc) == set(NEW) | set(xd.FULL_REFS) and set(dc['LS:Global z']) == {'5', '15', '60'}


# ------------------------------------------------------------------------------------------------ (e) refusals and skips
def test_rows_at_or_after_heat_end_are_refused(world, tmp_path):
    end = heat.HEAT_END
    met = xd.prep_metrics(world['met']).iloc[:50].copy()
    met.loc[met.index[-1], 'S'] = end
    with pytest.raises(SystemExit, match='cut the file'):
        xd.prep_metrics(met)
    with pytest.raises(SystemExit):
        xd.prep_premium(pd.DataFrame({'ts': [end - MIN, end], 'c': [0.0, 0.0]}))
    with pytest.raises(SystemExit):
        xd.prep_funding(pd.DataFrame({'calc_time': [end], 'last_funding_rate': [1e-4]}))
    with pytest.raises(SystemExit):
        xd.prep_book(pd.DataFrame({'ts': [end], 'bid_1pct': [1.0], 'ask_1pct': [1.0]}))
    with pytest.raises(SystemExit):
        xd.full_values(world['sp'], None, metrics=met)                          # full_values refuses, it does not skip
    # a stamp in seconds is refused as in the lite loaders
    with pytest.raises(SystemExit, match='13 digits'):
        xd.prep_premium(pd.DataFrame({'ts': [1_700_000_000], 'c': [0.0]}))
    # aggTrade reducers: a month file at or after 2026-01 and a late row in an earlier month
    d = tmp_path / 'agg'
    write_agg(str(d), world['agg_s'])
    late = world['agg_s'].iloc[:5].copy()
    late['ts'] = ms('2026-01-01') + np.arange(5) * MIN
    import pyarrow as pa
    import pyarrow.parquet as pq
    pq.write_table(pa.Table.from_pandas(late, preserve_index=False), str(d / '2026-01.parquet'))
    with pytest.raises(SystemExit, match='at or after'):
        xd.AggStore(str(d), T0, N)
    os.remove(d / '2026-01.parquet')
    bad = world['agg_s'].iloc[:5].copy()
    bad['ts'] = ms('2026-01-01') + np.arange(5) * MIN
    pq.write_table(pa.Table.from_pandas(bad, preserve_index=False), str(d / '2024-11.parquet'))
    with pytest.raises(SystemExit, match='at or after'):
        xd.AggStore(str(d), T0, N).col('n_buy')
    with pytest.raises(SystemExit, match='at or after'):
        xd.full_values(world['sp'], None, agg_spot=str(d))
    # the csv loaders (run_coin_outside): a late row in the file is refused
    p = tmp_path / 'metrics.csv.gz'
    met.to_csv(p, index=False)
    with pytest.raises(SystemExit):
        xd.load_full_inputs(metrics=str(p))


def test_doge_is_refused(tmp_path):
    for kw in ({'metrics': 'x/DOGEUSDT/metrics.csv.gz'}, {'agg_spot_dir': 'raw/DOGE/agg_spot'}, {'book': 'DOGE/b.csv'}):
        with pytest.raises(SystemExit, match='NEVER DOGE'):
            xd.load_full_inputs(**kw)
    with pytest.raises(SystemExit, match='NEVER DOGE'):
        xd.AggStore(str(tmp_path / 'DOGE'), T0, N)
    with pytest.raises(SystemExit, match='NEVER DOGE'):
        xd.cut_dir(str(tmp_path / 'DOGEUSDT'))


def test_missing_inputs_skip_with_a_reason(world):
    w = world
    none = xd.full_values(w['sp'], None)
    assert set(none['skipped']) == set(NEW) and none['values'] == {}
    assert all(v.startswith('no ') for v in none['skipped'].values())
    only = xd.full_values(w['sp'], None, metrics=w['met'])
    assert set(only['values']) == set(LS) and set(only['skipped']) == set(NEW) - set(LS)
    nostamp = xd.full_values(w['sp'], None, premium=w['prem'], funding=w['fund'])
    assert 'premium_stamp' in nostamp['skipped']['PREM:PredFund'] and not (set(PREM) & set(nostamp['values']))
    nofund = xd.full_values(w['sp'], None, premium=w['prem'], premium_stamp={'fit': 'same'})
    assert 'funding' in nofund['skipped']['PREM:PredMinusLast']
    unresolved = xd.full_values(w['sp'], None, premium=w['prem'], premium_stamp={'resolved': False}, funding=w['fund'])
    assert 'did not resolve' in unresolved['skipped']['PREM:PredFund']
    noagg = xd.full_values(w['sp'], None, agg_spot=w['dir_s'])
    assert set(noagg['skipped']) >= {'WHALEP:Net15', 'WHALEP:Count60', 'WHALEP:Sweep'} and 'WHALE:Net15' in noagg['values']
    assert 'agg_perp' in noagg['skipped']['WHALEP:Sweep']
    # a metrics file without the ratio columns is not guessed
    with pytest.raises(SystemExit, match='lacks column'):
        xd.full_values(w['sp'], None, metrics=w['met'].drop(columns='count_long_short_ratio'))
    # an empty agg directory and a missing directory
    os.makedirs(str(w['dir'] / 'empty'), exist_ok=True)
    assert 'no <YYYY-MM>.parquet' in xd.full_values(w['sp'], None, agg_spot=str(w['dir'] / 'empty'))['skipped']['WHALE:Net15']
    assert 'no directory' in xd.full_values(w['sp'], None, agg_spot=str(w['dir'] / 'nowhere'))['skipped']['WHALE:Net15']


def test_a_reading_with_too_few_values_on_a_is_skipped_with_the_zone_rule(world):
    w = world
    R = xd.full_readings(w['sp'], w['pp'], 1000, **inputs_of(w))                      # A of 1,000 rows: BOOKP has none, the rest are short
    assert 'BOOKP:Imb1' in R['skipped'] and 'fewer than' in R['reasons']['BOOKP:Imb1']
    few = make_agg(11)
    few[[c for c in few.columns if c.startswith('sw_')]] = 0                           # no sweep at all on A
    R = xd.full_readings(w['sp'], w['pp'], A_HI, agg_spot=write_agg(str(w['dir'] / 'nosweep'), few))
    assert 'WHALE:Sweep' in R['skipped'] and 'sweep rows on A' in R['reasons']['WHALE:Sweep'] and 'WHALE:Net15' not in R['skipped']


def test_aggstore_microsecond_stamps_are_converted(world, tmp_path):
    df = world['agg_s'].iloc[:2000].copy()
    df['ts'] = df.ts * 1000
    s = xd.AggStore(write_agg(str(tmp_path / 'us'), df.assign(ts=df.ts // 1000)), T0, N)         # (writer cuts by ms; rewrite below)
    import pyarrow as pa
    import pyarrow.parquet as pq
    pq.write_table(pa.Table.from_pandas(df, preserve_index=False), str(tmp_path / 'us' / '2024-11.parquet'))
    s = xd.AggStore(str(tmp_path / 'us'), T0, N)
    ref = xd.AggStore(write_agg(str(tmp_path / 'ms'), world['agg_s'].iloc[:2000]), T0, N)
    assert same(s.col('n_buy'), ref.col('n_buy')) and s.us_files == 1


def test_cut_dir_drops_2026(world, tmp_path):
    d = tmp_path / 'BTC'
    os.makedirs(d)
    met = xd.prep_metrics(world['met']).iloc[-10:].copy()
    met['S'] = heat.HEAT_END - 5 * 5 * MIN + np.arange(10) * 5 * MIN
    met.to_csv(d / 'metrics.csv.gz', index=False, compression='gzip')
    a = world['agg_s'].iloc[:50].copy()
    write_agg(str(d / 'agg_spot'), a)
    import pyarrow as pa
    import pyarrow.parquet as pq
    b = a.copy()
    b['ts'] = ms('2026-01-05') + np.arange(len(b)) * MIN
    pq.write_table(pa.Table.from_pandas(b, preserve_index=False), str(d / 'agg_spot' / '2026-01.parquet'))
    out = xd.cut_dir(str(d), log=lambda *_: None)
    assert out['metrics.csv.gz'] == 5 and out['agg_spot/2026-01.parquet'] == -1
    assert not os.path.exists(d / 'agg_spot' / '2026-01.parquet')
    assert pd.read_csv(d / 'metrics.csv.gz').S.max() < heat.HEAT_END
    assert xd.cut_dir(str(d), log=lambda *_: None) == {'metrics.csv.gz': 0}
    xd.prep_metrics(pd.read_csv(d / 'metrics.csv.gz'))                                   # now loads


# ------------------------------------------------------------------------------------------------ (f) the lite readings are frozen
def _digest(x):
    x = np.round(np.nan_to_num(np.asarray(x, float), nan=-9.87654321e9), 9)
    return hashlib.sha256(x.tobytes()).hexdigest()[:16]


def test_the_frozen_lite_readings_and_constants_are_unchanged(monkeypatch):
    monkeypatch.setattr(xd, 'CLUSTER_SHARE', 0.006)           # (the planted-cluster share of the lite tests; the frozen 2% is asserted below)
    from oracle.tests.test_heat_outside import synth_frames, inputs, START
    import tempfile
    spot, perp, oi = synth_frames(START, 12, seed=5)
    with tempfile.TemporaryDirectory() as d:
        sp, pp, o = inputs(d, spot, perp, oi)
    X = xd.xd_values(sp, pp, o)
    got = {}
    for nm in xd.LEAGUE + xd.REFS:
        x = np.array(X['values'][nm])
        x[xd.stale_for(nm, X['gap'])] = np.nan
        got[nm] = _digest(x)
    assert got == FROZEN_DIGEST, got
    monkeypatch.undo()
    assert xd.LEAGUE == ['CVDP:Div15', 'CVDP:PxDiv60', 'LIQMAP:DistAbove', 'LIQMAP:DistBelow', 'LIQMAP:Skew'] and xd.REFS == ['CVDP:15', 'REF:FlowTB15']
    c = xd.CONSTANTS
    assert c['leverage'] == [10, 25, 50, 100] and c['weights'] == [0.4, 0.3, 0.2, 0.1] and c['maintenance_margin'] == 0.005
    assert c['bucket_ratio'] == 1.001 and c['cluster_share_of_oi'] == 0.02 and c['expire_days'] == 30 and c['skew_band'] == 0.02
    assert (c['snapshot_ms'], c['known_ms'], c['carry_ms'], c['snapshot_gap_max_ms']) == (300000, 600000, 600000, 900000)
    assert (c['min_a_values'], c['presence'], c['sd_window'], c['skew_eps_share_of_oi']) == (1000, 0.8, 1440, 0.001)
    assert xd.FAMILY == {'CVDP:Div15': 'CVDP', 'CVDP:PxDiv60': 'CVDP', 'LIQMAP:DistAbove': 'LIQMAP', 'LIQMAP:DistBelow': 'LIQMAP', 'LIQMAP:Skew': 'LIQMAP'}
    assert set(c) == {'leverage', 'weights', 'maintenance_margin', 'bucket_ratio', 'cluster_share_of_oi', 'expire_days', 'skew_band', 'skew_eps_share_of_oi',
                      'snapshot_ms', 'known_ms', 'carry_ms', 'min_a_days', 'snapshot_gap_max_ms', 'presence', 'sd_window', 'zone_q', 'min_a_values',
                      'renorm_below'}       # the lite constants dict does not grow; the new ones are FULL_CONSTANTS


# sha256 (first 16 hex) of each lite series after the stale rule, rounded to 9 decimals, on synth_frames(START, 12, seed=5) at cluster share
# 0.006, taken from the code as it was BEFORE Amendment 3 (the lite functions have not been edited since)
FROZEN_DIGEST = {'CVDP:Div15': '65e1a6440af0497b', 'CVDP:PxDiv60': '207029f3e0e42170', 'LIQMAP:DistAbove': 'd2a312618fe6e14b',
                 'LIQMAP:DistBelow': '68e84ad30b63dac1', 'LIQMAP:Skew': 'ee5728153667b5f1', 'CVDP:15': '29839bbfeff3375c',
                 'REF:FlowTB15': '34e81bef0307c7a5'}


# ------------------------------------------------------------------------------------------------ (g) the OR-HM2 adapter
class MiniZ:
    """A duck-typed Zoner: zone(name, x, stale=, family=) and z.skipped; state() only when asked for."""

    def __init__(self, a_hi, with_state=True):
        self.a_hi, self.skipped, self.calls = a_hi, [], []
        if with_state:
            self.state = self._state

    def zone(self, name, x, stale=None, family='', k=1):
        x = np.array(x, float)
        if stale is not None:
            x[np.asarray(stale, bool)] = np.nan
        R, _ = xd.zone(name, x, self.a_hi, family)
        self.calls.append((name, family))
        if R is None:
            self.skipped.append(name)
        return R

    def _state(self, name, x, levels, stale=None, family=''):
        x = np.array(x, float)
        if stale is not None:
            x[np.asarray(stale, bool)] = np.nan
        R, why = xd.state_reading(name, x, self.a_hi, family)
        self.calls.append((name, family))
        if R is None:
            self.skipped.append(name)
        return R


def _hm2_inputs(w):
    c = w['sp']['c']
    pg = {'t0': T0, 'n': N, 'gap': w['sp']['gap'].copy(), 'first': 0, 'o': c, 'h': c * 1.0003, 'l': c * 0.9997, 'c': c,
          'v': np.full(N, 3.0), 'tb': np.full(N, 1.4)}
    return pg


def test_the_hm2_adapter_returns_the_new_readings_and_keeps_its_old_call(world):
    w = world
    m = dict(w['sp'])
    z = MiniZ(A_HI)
    info = {}
    R = xd.hm2_outside_readings(m, None, None, A_HI, z, lambda *a: None, info, **{k: v for k, v in inputs_of(w).items()})
    names = [r['name'] for r in R]
    assert names == NEW and all(r['research_only'] for r in R) and set(z.skipped) == set(xd.LEAGUE)        # (the lite five: no perp given)
    assert {c[1] for c in z.calls} == {'ls', 'prem', 'whale', 'whalep', 'bookp'}
    assert set(info['full']) >= {'near_duplicates', 'direction_coupling', 'reading_share', 'input', 'constants'}
    assert 'perp' in info['refused'] and all(info['skipped'][n].startswith('refused') for n in xd.LEAGUE)          # (no perp given: the lite five are skipped, as before)
    # the same codes as the standalone function (zones from A)
    S = xd.full_readings(m, w['pp'], A_HI, **inputs_of(w))
    codes = {r['name']: r['codes'] for r in S['readings']}
    pr = xd.hm2_outside_readings(m, _hm2_inputs(w) | {'gap': w['pp']['gap']}, None, A_HI, MiniZ(A_HI), lambda *a: None, None, **inputs_of(w))
    for r in pr:
        if r['name'] in codes:
            assert np.array_equal(r['codes'], codes[r['name']]), r['name']
    # no new inputs: the hook is the old one
    z0 = MiniZ(A_HI)
    assert xd.hm2_outside_readings(m, None, None, A_HI, z0, lambda *a: None) == [] and len(z0.skipped) == 5
    # a Zoner without a state method skips the three-state readings with a reason
    z1, i1 = MiniZ(A_HI, with_state=False), {}
    R1 = xd.hm2_outside_readings(m, None, None, A_HI, z1, lambda *a: None, i1, **inputs_of(w))
    assert 'WHALE:Sweep' not in [r['name'] for r in R1] and 'state method' in i1['skipped']['WHALE:Sweep']
    # a twin: needs its seed; swaps Net15 / Sweep only
    with pytest.raises(ValueError):
        xd.hm2_outside_readings(m, None, None, A_HI, MiniZ(A_HI), lambda *a: None, None, twin=True, **inputs_of(w))
    # a row at or after HEAT_END is refused with a reason, not a crash
    iL = {}
    bad = w['book'].copy()
    bad.loc[bad.index[-1], 'ts'] = heat.HEAT_END
    xd.hm2_outside_readings(m, None, None, A_HI, MiniZ(A_HI), lambda *a: None, iL, **inputs_of(w, book=bad))
    assert 'full' in iL['refused'] and 'cut the file' in iL['refused']['full']


# ------------------------------------------------------------------------------------------------ (h) end to end
@pytest.fixture(scope='module')
def e2e(tmp_path_factory):
    from oracle.tests.test_heat_outside import synth_frames, write
    import pyarrow as pa
    import pyarrow.parquet as pq
    d = tmp_path_factory.mktemp('e2e')
    start = ms('2024-10-01')
    days = int((ms('2026-01-01') - start) // DAY)
    spot, perp, oi = synth_frames(start, days, seed=12, level=60000.0)
    p = write(d, spot, perp, oi)
    n = days * 1440
    rng = np.random.default_rng(1)
    X = d / 'xd'
    os.makedirs(X)
    S = np.arange(start - DAY, start + n * MIN, 5 * MIN, dtype=np.int64)
    K = len(S)
    pd.DataFrame({'S': S, 'stamp': S, 'conv': 'new', 'count_long_short_ratio': np.exp(rng.normal(0.4, 0.1, K)),
                  'sum_toptrader_long_short_ratio': np.exp(rng.normal(0.1, 0.1, K)),
                  'count_toptrader_long_short_ratio': np.exp(rng.normal(0.2, 0.1, K))}).to_csv(X / 'metrics.csv.gz', index=False)
    ts = np.arange(start, start + n * MIN, MIN, dtype=np.int64)
    pm = 1.2e-3 * np.sin(np.arange(n) / 900) + rng.normal(0, 3e-5, n)
    pd.DataFrame({'ts': ts, 'o': pm, 'h': pm, 'l': pm, 'c': pm}).to_csv(X / 'premium_1m.csv.gz', index=False)
    json.dump({'fits': 'same', 'resolved': True, 'extra_delay_minutes': 0}, open(X / 'premium_stamp.json', 'w'))       # the fetch job's schema
    Ts = np.arange(start - 20 * DAY, start + n * MIN, 8 * 60 * MIN, dtype=np.int64)
    pd.DataFrame({'calc_time': Ts + 2, 'funding_interval_hours': 8, 'last_funding_rate': 1e-4 + rng.normal(0, 2e-5, len(Ts))}).to_csv(X / 'funding.csv.gz', index=False)
    bs = np.arange(start + 3 * DAY, start + n * MIN, 60_000, dtype=np.int64)
    pd.DataFrame({'ts': bs, 'bid_1pct': rng.uniform(1e6, 3e6, len(bs)), 'ask_1pct': rng.uniform(1e6, 3e6, len(bs))}).to_csv(X / 'bookdepth_1pct.csv.gz', index=False)
    # a light reducer: only the columns the readings read, on the whole grid, a few trades a minute
    nt = rng.poisson(6, n)
    mi = np.repeat(np.arange(n), nt)
    buy = rng.random(len(mi)) < 0.5
    usd = np.exp(rng.normal(np.log(800), 1.5, len(mi)))
    bc = lambda m, w=None: np.bincount(mi[m], weights=None if w is None else w[m], minlength=n)
    cols = {'ts': ts, 'n_buy': bc(buy).astype(np.int32), 'n_sell': bc(~buy).astype(np.int32), 'usd_buy': bc(buy, usd), 'usd_sell': bc(~buy, usd)}
    for k, e in enumerate(xd.WHALE_EDGES):
        g = usd >= e
        cols[f'nb_ge_{k}'], cols[f'ns_ge_{k}'] = bc(g & buy).astype(np.int32), bc(g & ~buy).astype(np.int32)
        cols[f'ub_ge_{k}'], cols[f'us_ge_{k}'] = bc(g & buy, usd), bc(g & ~buy, usd)
    for tag, pr in (('250k', 0.02), ('500k', 0.01), ('1m', 0.005), ('2m', 0.002)):
        cols[f'sw_b_{tag}'], cols[f'sw_s_{tag}'] = [(rng.random(n) < pr).astype(np.int32) for _ in range(2)]
    df = pd.DataFrame(cols)
    df = df[(df.n_buy + df.n_sell) > 0]
    write_agg(str(X / 'agg_spot'), df)
    write_agg(str(X / 'agg_perp'), df.assign(n_buy=df.n_buy * 2))
    mp = pytest.MonkeyPatch()
    mp.setattr(xd, 'CLUSTER_SHARE', 0.006)
    logs = []
    mt = xd.run_coin_outside('BTC', p['spot'], p['perp'], p['oi'], str(d / 'out'), procs=1, log=logs.append, metrics=str(X / 'metrics.csv.gz'),
                             premium=str(X / 'premium_1m.csv.gz'), premium_stamp=str(X / 'premium_stamp.json'), funding=str(X / 'funding.csv.gz'),
                             agg_spot_dir=str(X / 'agg_spot'), agg_perp_dir=str(X / 'agg_perp'), book=str(X / 'bookdepth_1pct.csv.gz'),
                             mark=str(X / 'nonexistent.csv.gz'))
    mp.undo()
    return {'dir': d, 'meta': mt, 'logs': logs}


def test_run_coin_outside_with_the_full_inputs(e2e):
    mt = e2e['meta']
    assert mt['study'] == 'OR-XD lite + full'
    xf = mt['xd_full']
    assert set(xf['readings']) <= set(NEW) and len(xf['readings']) >= 10, xf['skipped_reasons']
    assert xf['files']['mark'].startswith('not found') and xf['files']['metrics'].endswith('metrics.csv.gz')
    assert xf['perp_lag_applied'] is False and set(xf['direction_coupling']) <= set(NEW) | set(xd.FULL_REFS)
    assert mt['readings'] == 5 + len(xf['readings']) and mt['conditions'] == mt['readings']
    assert set(mt['edges']) >= set(xf['readings'])
    meta = json.load(open(e2e['dir'] / 'out' / 'meta.json'))
    assert meta['xd_full']['readings'] == xf['readings']
    df = pd.read_csv(e2e['dir'] / 'out' / 'heat.csv.gz', low_memory=False)
    keys = set(df.key.astype(str))
    assert any(k.startswith('LS:Global z=') for k in keys) and any(k.startswith('PREM:PredFund=') for k in keys)
    assert any(k.startswith('CVDP:Div15=') for k in keys)                    # the lite readings are still there
    # new x lite and new x new pairs
    assert (df.kind == 'pair').any()
    pk = df[df.kind == 'pair'].key.astype(str)
    assert pk.str.contains('CVDP:|LIQMAP:').any() and pk.str.contains('WHALE|LS:|PREM:|BOOKP:').any()        # all readings enter the pair scan
    assert (pk.str.contains('CVDP:') & pk.str.contains('WHALE|LS:|BOOKP:')).any()                          # ... including lite x new
    assert heat.build_readings.__module__ == 'oracle.heat' and heat.make_twin.__module__ == 'oracle.heat'


def test_cli_accepts_the_new_flags(tmp_path):
    with pytest.raises(SystemExit):
        xd.main(['coin', '--asset', 'DOGE', '--spot', 'a', '--perp', 'b', '--oi', 'c', '--out', str(tmp_path), '--metrics', 'm.csv.gz',
                 '--premium', 'p', '--premium-stamp', 's.json', '--mark', 'k', '--funding', 'f', '--agg-spot-dir', 'x', '--agg-perp-dir', 'y',
                 '--book', 'b.csv.gz'])
    with pytest.raises(SystemExit):
        xd.main(['coin', '--asset', 'BTC', '--spot', 'a', '--perp', 'b', '--oi', 'c', '--out', str(tmp_path), '--xd-dir', 'raw/DOGE/x'])
    assert xd.main(['cut', '--dir', str(tmp_path)]) is None
