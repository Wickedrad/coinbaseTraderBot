"""Tests for oracle/tennis.py (SPEC 2c; prereg OR-H1 tennis decisions, exits, features, strata): the fixture tarball round
trip (tar and extracted directory give the same part), hand-computed take-profit / ride / time-exit cases with the exact
bot/fees.ts fees, the 5-minute quote carry and the spread / band gates, TA and tape features that use no future minute,
the start-era filter and the unread day files, the DEV_END leakage guard, and the two markets of an event sharing a
group. Synthetic fixtures only (oracle/fixtures_tennis.py).

    cd python && python3 -m pytest -q oracle/tests/test_tennis.py
"""
from __future__ import annotations

import builtins
import os

import numpy as np
import pytest

from oracle import tennis
from oracle.common import DEV_END, MIN, Part, ms
from oracle.fixtures_tennis import flat, mirror, random_match, scripted_market, tape_line, write_history, write_tarball

SER = 'KXATPMATCH'
S1, S2, S3 = ms('2026-05-04T12:00'), ms('2026-05-05T12:00'), ms('2026-05-06T12:00')
S12 = ms('2026-07-31T23:00')         # straddles DEV_END
S13 = ms('2026-05-07T14:00')         # random match (perturbation test)
EDGES = [3.0, 5.0, 20.0]             # k_trades5 cut points given to every build (a fitted cut would move with the tape)

# E1, take-profit: YES 0.20/0.21 until minute 10, then 0.25/0.26, 0.30/0.31 and 0.35/0.36 from minute 13 (A wins).
QA1 = {**flat(-60, 10, (0.20, 0.21)), 11: (0.25, 0.26), 12: (0.30, 0.31), **flat(13, 200, (0.35, 0.36))}
# E2, ride: 0.60/0.61, a climb to 0.65/0.66 at minute 98 (the last two-sided quote), then one-sided; closes at 100.5.
QA2 = {**flat(-60, 90, (0.60, 0.61)), **flat(91, 95, (0.62, 0.63)), **flat(96, 97, (0.64, 0.65)), 98: (0.65, 0.66),
       99: (0.99, None), 100: (0.99, None)}
# E3, time exits: flat 0.40/0.41; no candle at 20-22 (carried) and 40-46 (carried to 44, NA at 45-46); 4c spread at 60.
QA3 = {**flat(-60, 19, (0.40, 0.41)), **flat(23, 39, (0.40, 0.41)), **flat(47, 59, (0.40, 0.41)), 60: (0.40, 0.44),
       **flat(61, 150, (0.40, 0.41))}
QF = flat(-60, 100, (0.40, 0.41))


def pair(ev, start, close, qa, result_a, **kw):
    a = scripted_market(f'{ev}-AAA', SER, ev, start, close, qa, result_a, **kw)
    b = scripted_market(f'{ev}-BBB', SER, ev, start, close, mirror(qa), 'no' if result_a == 'yes' else 'yes', **kw)
    return [a, b]


def scenario():
    mk, tp = [], []
    mk += pair('KXATPMATCH-E1', S1, S1 + 200 * MIN + 30_000, QA1, 'yes')
    # E1 market A's tape: a YES taker 30 and a NO taker 10 in minute 9, a YES taker 100 stamped exactly at t(10).
    tp.append(tape_line('KXATPMATCH-E1-AAA', [(S1 + 9 * MIN + 10_000, 0.21, 30, 1), (S1 + 9 * MIN + 40_000, 0.20, 10, 0),
                                              (S1 + 10 * MIN, 0.21, 100, 1)]))
    mk += pair('KXATPMATCH-E2', S2, S2 + 100 * MIN + 30_000, QA2, 'yes')
    mk += pair('KXATPMATCH-E3', S3, S3 + 150 * MIN + 30_000, QA3, 'no')
    # Start-era filter.
    s4, s5 = ms('2026-04-27T04:59'), ms('2026-04-27T05:00')
    mk += pair('KXATPMATCH-E4', s4, s4 + 100 * MIN, QF, 'yes')                       # starts a minute before the era
    mk += pair('KXATPMATCH-E5', s5, s5 + 100 * MIN, QF, 'yes')                       # starts at the era's first instant
    mk += pair('KXATPMATCH-E6', S1 + 3600_000, S1 + 3600_000 + 100 * MIN, QF, 'yes', no_start=True)   # no start time
    s7 = ms('2026-11-04T22:00')
    mk += pair('KXATPMATCH-E7', s7, ms('2026-11-05T00:00'), QF, 'yes')              # closes at the cutoff (11-05 file)
    tp.append(tape_line('KXATPMATCH-E7-AAA', [(s7 + 5 * MIN, 0.41, 10, 1)]))
    s8 = ms('2026-11-04T20:00')
    mk += pair('KXATPMATCH-E8', s8, ms('2026-11-04T23:30'), QF, 'no')               # HO-1, last day
    s9 = ms('2026-04-20T12:00')
    mk += pair('KXATPMATCH-E9', s9, s9 + 100 * MIN, QF, 'yes')                      # old era (04-20 file, never read)
    tp.append(tape_line('KXATPMATCH-E9-AAA', [(s9 + 5 * MIN, 0.41, 10, 1)]))
    v = pair('KXATPMATCH-E10', S2 + 3 * 3600_000, S2 + 3 * 3600_000 + 100 * MIN, QF, 'yes')
    for m in v:
        m['result'] = ''                                                           # voided
    mk += v
    mk += pair('KXATPMATCH-E11', S3 + 3 * 3600_000, S3 + 3 * 3600_000 + 100 * MIN, QF, 'yes')[:1]   # one-legged event
    mk += pair('KXATPMATCH-E12', S12, S12 + 100 * MIN + 30_000, QF, 'yes')         # straddles DEV_END
    rm, rt = random_match(SER, 'KXATPMATCH-E13', S13, 150, np.random.default_rng(5))
    mk += rm; tp += rt
    return mk, tp


@pytest.fixture(scope='module')
def built(tmp_path_factory):
    root = tmp_path_factory.mktemp('tennis')
    mk, tp = scenario()
    sdir = write_history(str(root / 'hist'), SER, mk, tp)
    tar = write_tarball(sdir, str(root / f'{SER}.tar.gz'))
    logs: list = []
    pt = Part(tennis.build(tar, 'ATP', str(root / 'parts_tar'), code_sha='test', log=logs.append, trade_edges=EDGES))
    pd_ = Part(tennis.build(str(root / 'hist'), 'ATP', str(root / 'parts_dir'), code_sha='test', log=logs.append, trade_edges=EDGES))
    return {'root': root, 'tar': tar, 'hist': str(root / 'hist'), 'p': pt, 'pd': pd_, 'logs': logs, 'mk': mk, 'tp': tp}


def mkt_of(p, ticker):
    return p.meta['tickers'].index(ticker)


def row(p, ticker, t):
    i = np.nonzero((p['mkt'] == mkt_of(p, ticker)) & (p['t'] == t))[0]
    assert len(i) == 1, (ticker, t, i)
    return int(i[0])


def has_row(p, ticker, t):
    return bool(((p['mkt'] == mkt_of(p, ticker)) & (p['t'] == t)).any())


def val(p, name, i):
    return float(p[name][i])


def col(p, name):
    return p.meta['features'].index(next(f for f in p.meta['features'] if f['name'] == name))


# ---------- format and round trip ----------

def test_round_trip_tar_and_dir(built):
    p, q = built['p'], built['pd']
    assert p.meta == q.meta
    names = sorted(f[:-4] for f in os.listdir(p.path) if f.endswith('.npy'))
    assert names == sorted(f[:-4] for f in os.listdir(q.path) if f.endswith('.npy'))
    for n in names:
        np.testing.assert_array_equal(p[n], q[n], err_msg=n)
    m = p.meta
    assert m['schema'] == 'oracle-part-1' and m['ct'] == 'tennis' and m['scope'] == 'ATP' and m['assets'] == ['ATP']
    assert m['sides'] == ['Y', 'N'] and m['horizons'] == [15, 60] and m['size_usd'] == 10.0 and m['size2_usd'] == 20.0
    assert m['n'] == len(p['t']) > 0 and np.all(np.diff(p['t']) >= 0)
    assert p['X'].shape == (m['n'], len(m['features'])) and p['X'].dtype == np.int8
    for n, dt in (('t', np.int64), ('group', np.int64), ('asset', np.int8), ('rv', np.int8), ('hour', np.int8),
                  ('stratum_Y', np.int16), ('ok_Y15', np.uint8), ('hit_N60', np.uint8), ('trade_Y60', np.float32),
                  ('best_N15', np.float32), ('hold_Y15', np.uint16), ('hit2_Y15', np.uint8), ('trade2_N60', np.float32),
                  ('tradeLat_Y15', np.float32), ('tradeCost_N60', np.float32)):
        assert p[n].dtype == dt, n
        assert p[n].shape[0] == m['n'], n
    assert np.all(p['rv'] == -1) and np.all(p['asset'] == 0)
    assert np.all(p['hour'] == (p['t'] // 3_600_000) % 24)


def test_side_features_and_strata(built):
    p = built['p']
    m = p.meta
    sf = m['side_features']
    assert set(sf) == {'Y', 'N'} and not set(sf['Y']) & set(sf['N'])
    for s in 'YN':
        for j in sf[s]:
            f = m['features'][j]
            assert f['name'].endswith('@' + s) and f['side'] == s and f['base'] == f['name'][:-2]
    bases = lambda s: sorted(m['features'][j]['base'] for j in sf[s])
    assert bases('Y') == bases('N')
    both = {f['name'] for j, f in enumerate(m['features']) if j not in sf['Y'] + sf['N']}
    assert both == {'k_since', 'k_spread', 'k_trades5', 'ctx:hour4', 'ctx:weekend'}
    X = p['X']
    for j, f in enumerate(m['features']):
        allowed = set(f['levels']) | ({-1} if f['kind'] == 'bucket' else set())
        assert set(np.unique(X[:, j]).tolist()) <= allowed, f['name']
    for s in 'YN':
        st = p[f'stratum_{s}']
        okany = (p[f'ok_{s}15'] | p[f'ok_{s}60']).astype(bool)
        assert np.all((st >= 0) & (st < 30) | (st == -1))
        assert np.all(st[okany] >= 0)
        for h in (15, 60):
            ok = p[f'ok_{s}{h}'].astype(bool)
            assert np.all(np.isfinite(p[f'trade_{s}{h}'][ok])) and np.all(np.isnan(p[f'trade_{s}{h}'][~ok]))
            assert np.all(p[f'hit_{s}{h}'][~ok] == 0)
            assert np.all(p[f'best_{s}{h}'][ok] >= p[f'trade_{s}{h}'][ok] - 1e-5)


# ---------- hand-computed exits (allpairs.fees = bot/fees.ts) ----------

def test_take_profit(built):
    """E1 minute 10, YES ask 0.21: C = 47, cost = 9.87 + fee 0.55 = 10.42. Bid 0.35 at minute 13 nets 16.45 - 0.75 -
    10.42 = 5.28 >= $5: take-profit, hold 3. NO side: ask 0.80, C = 12, cost 9.74; it never reaches $5 and exits at the
    NO bid 0.64 at k + h: 7.68 - 0.20 - 9.74 = -2.26; its best is the first minute (NO bid 0.74: -1.03)."""
    p = built['p']
    i = row(p, 'KXATPMATCH-E1-AAA', S1 + 10 * MIN)
    for h in (15, 60):
        assert val(p, f'trade_Y{h}', i) == pytest.approx(5.28, abs=1e-6)
        assert val(p, f'best_Y{h}', i) == pytest.approx(5.28, abs=1e-6)
        assert p[f'hit_Y{h}'][i] == 1 and p[f'hold_Y{h}'][i] == 3 and p[f'ok_Y{h}'][i] == 1
        assert val(p, f'trade_N{h}', i) == pytest.approx(-2.26, abs=1e-6)
        assert p[f'hit_N{h}'][i] == 0 and p[f'hold_N{h}'][i] == h
    assert val(p, 'best_N15', i) == pytest.approx(-1.03, abs=1e-6)
    # $20: C = 95, cost 19.95 + 1.11 = 21.06; bid 0.30 at minute 12 nets 28.50 - 1.40 - 21.06 = 6.04.
    assert val(p, 'trade2_Y15', i) == pytest.approx(6.04, abs=1e-6) and p['hit2_Y15'][i] == 1
    # +1c: entry 0.22, C = 45, cost 9.90 + 0.55 = 10.45; bid 0.35 nets 15.75 - 0.72 - 10.45 = 4.58 < 5: time exit.
    assert val(p, 'tradeCost_Y15', i) == pytest.approx(4.58, abs=1e-6)
    assert val(p, 'tradeCost_Y60', i) == pytest.approx(4.58, abs=1e-6)
    # Latency: entry at minute 11's ask 0.26, C = 38, cost 9.88 + 0.52 = 10.40; bid 0.35 nets 13.30 - 0.61 - 10.40 = 2.29.
    assert val(p, 'tradeLat_Y15', i) == pytest.approx(2.29, abs=1e-6)
    # The other market's NO is the same trade (B is A's mirror).
    j = row(p, 'KXATPMATCH-E1-BBB', S1 + 10 * MIN)
    assert val(p, 'trade_N15', j) == pytest.approx(5.28, abs=1e-6) and p['hold_N15'][j] == 3
    # Minute 9 + 1 = 10 latency equals the trade decided at minute 10 (same ask, same exit rule).
    k = row(p, 'KXATPMATCH-E1-AAA', S1 + 9 * MIN)
    assert val(p, 'tradeLat_Y60', k) == pytest.approx(val(p, 'trade_Y60', i), abs=1e-6)


def test_close_inside_the_horizon_settles(built):
    """E2 minute 90 (closes at 100.5, inside both horizons): without a take-profit the position settles (causal; the
    OR-H1 'sell at the last candle unless in profit' used the knowledge that the candle was the last). YES ask 0.61:
    C = 16, cost 10.03, settles YES: 16 - 10.03 = 5.97 >= $5 (hit), hold ceil(10.5) = 11. NO ask 0.40: C = 25, cost
    10.42, settles NO = 0: -10.42 (before the review fix it was sold at its last quote, NO bid 0.34: -2.32), hold 11."""
    p = built['p']
    i = row(p, 'KXATPMATCH-E2-AAA', S2 + 90 * MIN)
    for h in (15, 60):
        assert val(p, f'trade_Y{h}', i) == pytest.approx(5.97, abs=1e-6)
        assert p[f'hit_Y{h}'][i] == 1 and p[f'hold_Y{h}'][i] == 11
        assert val(p, f'best_Y{h}', i) == pytest.approx(5.97, abs=1e-6)
        assert val(p, f'trade_N{h}', i) == pytest.approx(-10.42, abs=1e-6)
        assert p[f'hit_N{h}'][i] == 0 and p[f'hold_N{h}'][i] == 11
        assert val(p, f'best_N{h}', i) == pytest.approx(-1.58, abs=1e-6)    # NO bid 0.37: 9.25 - 0.41 - 10.42
    assert not has_row(p, 'KXATPMATCH-E2-AAA', S2 + 99 * MIN)               # one-sided book: no decision
    j = row(p, 'KXATPMATCH-E2-BBB', S2 + 90 * MIN)                          # B's NO = A's YES: settles and wins too
    assert val(p, 'trade_N15', j) == pytest.approx(5.97, abs=1e-6)
    assert val(p, 'trade_Y15', j) == pytest.approx(-10.42, abs=1e-6)


def test_exit_is_causal_close_unknown_in_advance():
    """Review regression (Nov 6): two side-bid paths identical through minute 5, entry at ask 0.30 at k = 0, h = 15. In A
    the match ends at 5:30 (market closes); in B it goes on. Whatever happens after minute 5 must not change what the
    position does at minute 5: it is held in both (A then settles; B exits at k + h). Before the fix, A was SOLD at minute
    5 (the 'last quote') because the close was known to follow."""
    t0 = ms('2026-05-04T12:00')
    path = [0.30, 0.29, 0.28, 0.27, 0.26, 0.25]
    a = tennis.simulate(np.array(path), t0, t0 + 5 * MIN + 30_000, 0.0, np.array([0]), np.array([0.30]), 10.0, 15)
    b = tennis.simulate(np.array(path + [0.25] * 30), t0, t0 + 35 * MIN + 30_000, 0.0, np.array([0]), np.array([0.30]), 10.0, 15)
    C = 33                                                              # floor(10 / 0.30)
    cost = C * 0.30 + float(tennis.taker_fee(C, 0.30))
    assert a['trade'][0] == pytest.approx(round(-cost, 6)) and a['hold'][0] == 6 and not a['hit'][0]   # settles (lost)
    assert b['hold'][0] == 15                                           # held past minute 5 in B too
    assert a['read_end'][0] == t0 + 5 * MIN + 30_000


def test_time_exits_carry_and_gates(built):
    """E3 minute 0: YES ask 0.41, C = 24, cost 10.25; the bid stays 0.40: 9.60 - 0.41 - 10.25 = -1.06 at k + 15 and at
    k + 60. NO ask 0.60, C = 16, cost 9.87: NO bid 0.59 at k + 15 nets -0.71; at k + 60 the book is 0.40/0.44 (NO bid
    0.56): -1.19. Minute 30 + 15 = 45 has no quote: the time exit takes the first later bid (minute 47), hold 17."""
    p = built['p']
    tk = 'KXATPMATCH-E3-AAA'
    i = row(p, tk, S3)
    assert val(p, 'trade_Y15', i) == pytest.approx(-1.06, abs=1e-6) and p['hold_Y15'][i] == 15
    assert val(p, 'trade_Y60', i) == pytest.approx(-1.06, abs=1e-6) and p['hold_Y60'][i] == 60
    assert val(p, 'trade_N15', i) == pytest.approx(-0.71, abs=1e-6)
    assert val(p, 'trade_N60', i) == pytest.approx(-1.19, abs=1e-6) and p['hold_N60'][i] == 60
    assert val(p, 'best_N60', i) == pytest.approx(-0.71, abs=1e-6)
    j = row(p, tk, S3 + 30 * MIN)
    assert val(p, 'trade_Y15', j) == pytest.approx(-1.06, abs=1e-6) and p['hold_Y15'][j] == 17
    assert val(p, 'trade_N15', j) == pytest.approx(-0.71, abs=1e-6) and p['hold_N15'][j] == 17
    # Carry: no candle at 20-22 and 40-44 -> carried quotes value exits but are never entered on (review fix, Nov 6:
    # decisions at candle minutes only); 45-46 NA. 60: spread 4c > 3c, no decision (its bid still serves exits).
    for off in (20, 22, 40, 44, 45, 46, 60):
        assert not has_row(p, tk, S3 + off * MIN), off
    assert has_row(p, tk, S3 + 19 * MIN) and has_row(p, tk, S3 + 23 * MIN) and has_row(p, tk, S3 + 47 * MIN)
    assert np.all(p['stale'] == 0)
    # The minute-19 entry's 15-minute time exit (minute 34) is unchanged by the carried minutes before it.
    assert val(p, 'trade_Y15', row(p, tk, S3 + 19 * MIN)) == pytest.approx(-1.06, abs=1e-6)
    # Decisions start 30 minutes before the start.
    assert has_row(p, tk, S3 - 30 * MIN) and not has_row(p, tk, S3 - 31 * MIN)
    assert p['tmin'][row(p, tk, S3 - 30 * MIN)] == -30
    assert p['X'][row(p, tk, S3 - 30 * MIN), col(p, 'k_since')] == 0
    assert p['X'][row(p, tk, S3 + 29 * MIN), col(p, 'k_since')] == 1
    assert p['X'][row(p, tk, S3 + 130 * MIN), col(p, 'k_since')] == 4


def test_price_band_and_strata(built):
    """The side ask must lie in [0.05, 0.95]; stratum = price bucket x 3 + phase."""
    p = built['p']
    i = row(p, 'KXATPMATCH-E1-AAA', S1 + 10 * MIN)           # Y ask 0.21 (bucket 2), N ask 0.80 (bucket 8), minute 10 live
    assert p['X'][i, col(p, 'k_price@Y')] == 2 and p['X'][i, col(p, 'k_price@N')] == 8
    assert p['stratum_Y'][i] == 2 * 3 + 1 and p['stratum_N'][i] == 8 * 3 + 1
    j = row(p, 'KXATPMATCH-E1-AAA', S1 - 10 * MIN)
    assert p['stratum_Y'][j] == 2 * 3 + 0                     # pre-match
    k = row(p, 'KXATPMATCH-E3-AAA', S3 + 70 * MIN)
    assert p['stratum_Y'][k] == 4 * 3 + 2                     # ask 0.41, live after 60 minutes
    assert p['X'][i, col(p, 'k_band@Y')] == 1 and p['X'][i, col(p, 'k_band@N')] == 2    # mids 0.205 / 0.795
    # The E2 one-sided tail: YES 0.99 bid with no ask is no book; and a 0.96 ask would be out of band (checked directly).
    assert tennis.price_bucket(np.array([0.04, 0.05, 0.0999, 0.10, 0.95, 0.96])).tolist() == [-1, 0, 0, 1, 9, -1]


# ---------- features ----------

def test_features_at_hand_rows(built):
    p = built['p']
    X = p['X']
    i = row(p, 'KXATPMATCH-E1-AAA', S1 + 13 * MIN)           # after the climb 0.205 -> 0.355 (B falls 0.795 -> 0.645)
    assert X[i, col(p, 'ta_rsi14@Y')] == 1 and X[i, col(p, 'ta_rsi14@N')] == -1
    assert X[i, col(p, 'k_dmid1@Y')] == 1 and X[i, col(p, 'k_dmid3@N')] == -1
    assert X[i, col(p, 'k_other5@Y')] == -1 and X[i, col(p, 'k_other5@N')] == 1
    j = row(p, 'KXATPMATCH-E1-AAA', S1 + 5 * MIN)            # inside the flat stretch: flat masks, no change
    for n in ('ta_rsi14', 'ta_stoch', 'ta_willr14', 'ta_cci14', 'ta_bb', 'ta_macdh', 'ta_slope14', 'ta_mom10', 'ta_adx14', 'k_dmid1'):
        assert X[j, col(p, f'{n}@Y')] == 0 and X[j, col(p, f'{n}@N')] == 0, n
    # Tape: minute 9 has a YES taker 30 and a NO taker 10; the YES 100 stamped at t(10) belongs to the next window.
    k = row(p, 'KXATPMATCH-E1-AAA', S1 + 10 * MIN)
    assert X[k, col(p, 'k_flow5@Y')] == 3 and X[k, col(p, 'k_flow5@N')] == 1           # +0.5 / -0.5
    assert X[k, col(p, 'k_trades5')] == 1                                                # 2 trades: (0, 2]
    m = row(p, 'KXATPMATCH-E1-AAA', S1 + 11 * MIN)
    assert X[m, col(p, 'k_flow5@Y')] == 4 and X[m, col(p, 'k_flow5@N')] == 0           # (130 - 10) / 140
    assert X[m, col(p, 'k_trades5')] == 2
    n_ = row(p, 'KXATPMATCH-E1-AAA', S1 + 30 * MIN)
    assert X[n_, col(p, 'k_flow5@Y')] == -1 and X[n_, col(p, 'k_trades5')] == 0         # no trades
    assert X[k, col(p, 'k_spread')] == 0
    assert X[k, col(p, 'ctx:hour4')] == 3 and X[k, col(p, 'ctx:weekend')] == 0          # Monday 12:10 UTC
    w = row(p, 'KXATPMATCH-E8-AAA', ms('2026-11-04T21:00'))
    assert X[w, col(p, 'ctx:weekend')] == 0
    assert tennis.weekend(np.array([ms('2026-05-09T12:00'), ms('2026-05-10T23:59'), ms('2026-05-11T00:00')])).tolist() == [1, 1, 0]


def test_ta_states_mirror():
    """The N columns read the NO mid (100 - YES mid): every TA state flips sign (up to threshold ties)."""
    rng = np.random.default_rng(3)
    m = 50 + np.cumsum(rng.choice([-1.0, -0.5, 0.0, 0.5, 1.0], 600))
    m[[100, 101, 350]] = np.nan
    a, b = tennis.ta_states(m), tennis.ta_states(100 - m)
    for n in tennis.TA_NAMES:
        agree = np.mean(a[n] == -b[n])
        assert agree > 0.99, (n, agree)
        assert np.all(a[n][[100, 101, 350]] == 0)
        assert np.all(a[n][:9] == 0)                         # warm-up: no reading before 10 minutes


def test_no_future_minute(built, tmp_path):
    """Perturb every candle after t_k and every print at or after t_k of market A of a random match: the feature rows of
    both markets at t <= t_k are unchanged (labels may change)."""
    mk, tp = scenario()
    ev = 'KXATPMATCH-E13'
    tk = S13 + 40 * MIN
    rng = np.random.default_rng(11)
    for m in mk:
        if m['ticker'] == f'{ev}-AAA':
            for c in m['candles']:
                if c['ts'] > tk:
                    b = round(float(rng.uniform(0.05, 0.9)), 2)
                    for f in 'OHLC':
                        c[f'bid{f}'], c[f'ask{f}'] = b, round(b + 0.01, 2)
    for t_ in tp:
        if t_['ticker'] == f'{ev}-AAA':
            t_['trades'] = [x if x[0] < tk else [x[0], x[1], float(rng.integers(1, 500)), int(rng.integers(0, 2))] for x in t_['trades']]
            t_['trades'].append([tk, 0.5, 999.0, 1])
    write_history(str(tmp_path / 'hist'), SER, mk, tp)
    q = Part(tennis.build(str(tmp_path / 'hist'), 'ATP', str(tmp_path / 'parts'), code_sha='test', log=lambda s: None, trade_edges=EDGES))
    p = built['p']
    assert p.meta['tickers'] == q.meta['tickers']
    changed_labels = 0
    for side in ('AAA', 'BBB'):
        mi = mkt_of(p, f'{ev}-{side}')
        a = np.nonzero((p['mkt'] == mi) & (p['t'] <= tk))[0]
        b = np.nonzero((q['mkt'] == mi) & (q['t'] <= tk))[0]
        assert len(a) > 30 and np.array_equal(p['t'][a], q['t'][b])
        np.testing.assert_array_equal(p['X'][a], q['X'][b])
        for n in ('stratum_Y', 'stratum_N', 'stale', 'tmin', 'group'):
            np.testing.assert_array_equal(p[n][a], q[n][b], err_msg=n)
        changed_labels += int(np.sum(~np.isclose(p['trade_Y60'][a], q['trade_Y60'][b], equal_nan=True)))
    assert changed_labels > 0                                  # the perturbation did reach the labels


# ---------- era, files, guard, groups ----------

def test_era_filter_and_unread_files(built, tmp_path, monkeypatch):
    p = built['p']
    tickers = set(p.meta['tickers'])
    for ev in ('E4', 'E6', 'E7', 'E9', 'E10'):
        assert not any(t.startswith(f'KXATPMATCH-{ev}-') for t in tickers), ev
    for ev in ('E1', 'E2', 'E3', 'E5', 'E8', 'E11', 'E12', 'E13'):
        assert any(t.startswith(f'KXATPMATCH-{ev}-') for t in tickers), ev
    c = p.meta['counts']
    assert c['no_start'] == 2 and c['pre_era'] == 2 and c['unsettled'] == 2 and c['one_legged_events'] == 1
    t = p['t']
    assert t.max() < ms('2026-11-05') and p['close'].max() < ms('2026-11-05')
    e5 = row(p, 'KXATPMATCH-E5-AAA', ms('2026-04-27T04:30'))   # decisions from 30 min before the era's first start
    assert p['tmin'][e5] == -30
    # Files dated 2026-11-05 or later, or before 2026-04-27, are never opened (directory mode).
    opened = []
    real_open = builtins.open

    def spy(f, *a, **k):
        opened.append(str(f))
        return real_open(f, *a, **k)
    monkeypatch.setattr(builtins, 'open', spy)
    tennis.build(built['hist'], 'ATP', str(tmp_path / 'p2'), code_sha='test', log=lambda s: None, trade_edges=EDGES)
    monkeypatch.setattr(builtins, 'open', real_open)
    days = [os.path.basename(f)[:10] for f in opened if f.endswith('.jsonl')]
    assert days and all('2026-04-27' <= d < '2026-11-05' for d in days), days
    assert os.path.exists(os.path.join(built['hist'], SER, '2026-11-05.jsonl'))
    assert os.path.exists(os.path.join(built['hist'], SER, 'trades', '2026-04-20.jsonl'))
    # Tarball mode: the same members are left unread.
    stats: dict = {}
    for _ in tennis.iter_lines(built['tar'], SER, stats):
        pass
    assert all('2026-04-27' <= os.path.basename(n)[:10] < '2026-11-05' for n in stats['read'])
    assert stats['skipped'] == 4                               # 04-20 and 11-05, markets and trades


def test_dev_end_guard(built):
    """E12 starts Jul 31 23:00 and closes Aug 1 00:40:30. A decision before DEV_END whose window reaches past it is not
    ok; a decision at or after DEV_END is scored on its own."""
    p = built['p']
    tk = 'KXATPMATCH-E12-AAA'
    a = row(p, tk, S12 + 30 * MIN)        # 23:30: h=15 ends 23:45 (ok), h=60 ends 00:30 (guarded)
    assert p['ok_Y15'][a] == 1 and p['ok_Y60'][a] == 0 and np.isnan(p['trade_Y60'][a]) and p['stratum_Y'][a] >= 0
    b = row(p, tk, S12 + 50 * MIN)        # 23:50: both horizons end after DEV_END
    assert p['ok_Y15'][b] == 0 and p['ok_N15'][b] == 0
    c = row(p, tk, S12 + 70 * MIN)        # 00:10, an HO-1-side row
    assert p['t'][c] >= DEV_END and p['ok_Y15'][c] == 1 and p['ok_Y60'][c] == 1
    d = row(p, tk, S12 + 44 * MIN)        # 23:44: the 15-minute latency entry at 23:45 would read 00:00 + 0 .. 00:00
    assert p['ok_Y15'][d] == 1 and np.isfinite(p['tradeLat_Y15'][d])
    e = row(p, tk, S12 + 45 * MIN)        # 23:45: h=15 ends exactly at DEV_END (ok); its latency entry reads past it
    assert p['ok_Y15'][e] == 1 and np.isnan(p['tradeLat_Y15'][e])
    assert p.meta['counts']['dev_guard_not_ok']['ok_Y60'] > 0


def test_groups(built):
    p = built['p']
    g = p['group']
    ga = set(g[p['mkt'] == mkt_of(p, 'KXATPMATCH-E1-AAA')].tolist())
    gb = set(g[p['mkt'] == mkt_of(p, 'KXATPMATCH-E1-BBB')].tolist())
    gc = set(g[p['mkt'] == mkt_of(p, 'KXATPMATCH-E2-AAA')].tolist())
    assert len(ga) == 1 and ga == gb and not ga & gc
    assert p.meta['events'][ga.pop()] == 'KXATPMATCH-E1'
    # One market per (row's market) group and two markets per two-market event.
    per = {}
    for mi, gi in zip(p['mkt'].tolist(), g.tolist()):
        per.setdefault(gi, set()).add(mi)
    assert all(1 <= len(v) <= 2 for v in per.values())
    one = mkt_of(p, 'KXATPMATCH-E11-AAA')
    rows = p['mkt'] == one
    assert np.all(p['X'][rows, col(p, 'k_other5@Y')] == 0)    # no second market


def test_tour_refusals(tmp_path):
    with pytest.raises(ValueError):
        tennis.check_tour('DOGE')
    with pytest.raises(ValueError):
        tennis.check_tour('ITF')
    assert tennis.check_tour('wta') == 'WTA' and tennis.SERIES['WTA'] == 'KXWTAMATCH'


def test_simulate_unit():
    """simulate() on a hand series: TP, time exit, the close-inside ride, and invalid entries."""
    bid = np.array([0.20, 0.25, 0.30, 0.35, 0.35, np.nan, 0.35])
    t0 = ms('2026-05-04T12:00')
    close = t0 + 6 * MIN + 30_000                  # L = 7
    r = tennis.simulate(bid, t0, close, 1.0, np.array([0, 0, 6]), np.array([0.21, np.nan, 0.36]), 10.0, 15)
    assert r['trade'][0] == pytest.approx(5.28) and r['hit'][0] and r['hold'][0] == 3
    assert np.isnan(r['trade'][1]) and not r['hit'][1]
    # Entered at the last minute (no quote after it): rides to settlement, C = 27, cost 9.72 + 0.44 = 10.16 -> 16.84.
    assert r['trade'][2] == pytest.approx(16.84, abs=1e-6) and r['hold'][2] == 1 and r['hit'][2]
    # A grid that does not reach the close is refused.
    with pytest.raises(ValueError):
        tennis.simulate(bid, t0, t0 + 120 * MIN, 0.0, np.array([0]), np.array([0.26]), 10.0, 2)
    # h = 2 on a long market: no take-profit, time exit at k + 2 (bid 0.30): C = 38, cost 10.40, 11.40 - 0.56 - 10.40.
    bid2 = np.r_[bid, np.full(113, 0.35)]
    r2 = tennis.simulate(bid2, t0, t0 + 120 * MIN, 0.0, np.array([0]), np.array([0.26]), 10.0, 2)
    assert r2['hold'][0] == 2 and r2['trade'][0] == pytest.approx(0.44, abs=1e-6) and not r2['hit'][0]
    # The close inside the horizon with a loss at the last quote (minute 6): it settles (causal), it is not sold there.
    r3 = tennis.simulate(bid, t0, close, 0.0, np.array([4]), np.array([0.40]), 10.0, 15)
    # C = 25, cost 10.42; settles 0: -10.42, hold ceil(2.5) = 3 (the last quote would have netted -2.07).
    assert r3['trade'][0] == pytest.approx(-10.42, abs=1e-6) and r3['hold'][0] == 3
    assert r3['read_end'][0] == close


def test_minute_series_unit():
    """The first stored candle is dropped; a quiet minute carries the last quote at most 5 minutes; a candle without a
    two-sided book (one-sided, crossed, or the historical tier's 1c empty ask) is NA and breaks the carry; legacy-cent
    markets are repaired; the grid stops before the close."""
    from oracle.fixtures_tennis import candle
    t = ms('2026-05-04T12:00')
    cs = [candle(t, 0.10, 0.12), candle(t + MIN, 0.40, 0.41)] + [candle(t + (2 + i) * MIN, 0.40, 0.42) for i in range(2)]
    cs += [candle(t + 11 * MIN, 0.50, 0.51), candle(t + 12 * MIN, 0.55, None), candle(t + 13 * MIN, 0.60, 0.01),
           candle(t + 14 * MIN, 0.60, 0.61), candle(t + 20 * MIN, 0.70, 0.71)]
    m = {'closeTime': t + 15 * MIN + 30_000, 'candles': cs}
    t0, bid, ask, stale = tennis.minute_series(m)
    assert t0 == t + MIN and len(bid) == 15                   # minutes 1 .. 15 (15 + 30 s is the close; 20 is after it)
    assert bid[0] == 0.40 and ask[0] == 0.41 and ask[2] == 0.42 and stale[2] == 0     # minutes 1 .. 3 have candles
    assert [stale[i] for i in range(3, 8)] == [1, 2, 3, 4, 5] and np.all(bid[3:8] == 0.40)   # minutes 4 .. 8 carried
    assert np.isnan(bid[8]) and np.isnan(bid[9]) and bid[10] == 0.50   # minutes 9, 10: over 5 minutes stale; 11 fresh
    assert np.isnan(bid[11]) and np.isnan(bid[12])            # one-sided; crossed (1c empty ask)
    assert bid[13] == 0.60 and stale[13] == 0
    assert bid[14] == 0.60 and stale[14] == 1                 # minute 15 carried; the close at 15:30 ends the grid
    leg = {'closeTime': t + 5 * MIN, 'candles': [candle(t + i * MIN, 0.004, 0.0041) for i in range(5)]}
    _, lb, la, _ = tennis.minute_series(leg)
    assert lb[0] == pytest.approx(0.40) and la[0] == pytest.approx(0.41)


def test_tennis_taker_multiplier_is_one():
    """bot/kalshi/feeScheduleSnapshot.json lists both tennis series as non-standard with taker 1 (and maker 1)."""
    import json
    snap = json.load(open(os.path.join(os.path.dirname(__file__), '..', '..', '..', 'bot', 'kalshi', 'feeScheduleSnapshot.json')))
    for s in tennis.SERIES.values():
        assert snap['nonStandard'][s]['taker'] == tennis.TAKER_MULT == 1.0


def test_cli(built, tmp_path):
    tennis.main(['--tar', built['tar'], '--tour', 'ATP', '--out', str(tmp_path / 'cli'), '--code-sha', 'test'])
    q = Part(str(tmp_path / 'cli' / 'tennis-ATP'))
    assert q.n > 0 and q.meta['code_sha'] == 'test'
    tennis.main(['--hist', built['hist'], '--tour', 'ATP', '--out', str(tmp_path / 'cli2'), '--code-sha', 'test'])
    assert Part(str(tmp_path / 'cli2' / 'tennis-ATP')).n == q.n
