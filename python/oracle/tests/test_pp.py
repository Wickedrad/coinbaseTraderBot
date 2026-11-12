"""Tests for oracle/pp.py (SPEC 2b, prereg OR-H1 Price Prediction exits): hand-computed take-profit / ride / cut cases
with the exact bot/fees.ts fees, the spot join (t_end == t_k), the entry-window bounds, the side price band, the hourly
mid band, DOGE refused, and no day file dated 2026-11-05 or later opened. Synthetic fixtures only (oracle/fixtures_pp.py).

    cd python && python3 -m pytest -q oracle/tests/test_pp.py
"""
from __future__ import annotations

import builtins
import math
import os

import numpy as np
import pytest
from scipy.special import ndtr

import allpairs.data as apdata
from allpairs.fees import taker_fee
from oracle import pp
from oracle.common import MIN, Part, ms
from oracle.fixtures_pp import quotes_market, spot_path, write_markets, write_spot_part

T0 = ms('2026-05-01')
H = 60 * MIN


def flat(lo, hi, q):
    return {k: q for k in range(lo, hi + 1)}


def m15(name, o, quotes, result, strike=60_000.0):
    return quotes_market(f'KXBTC15M-{name}', 'KXBTC15M', o, 15, strike, result, quotes)


def m60(name, close, quotes, result, strike=60_000.0):
    o = close - H
    return quotes_market(f'KXBTCD-{name}-T{strike:.2f}', 'KXBTCD', o, 60, strike, result, quotes, listed_ms=close - 2 * H)


# 15-minute markets (window open o, decision k at o + k min, last decision minute 14, no take-profit at j = 14).
A = {**{1: (0.38, 0.40), 2: (0.45, 0.47), 3: (0.53, 0.55)}, **flat(4, 14, (0.54, 0.56))}          # take-profit at j = 4
B = {1: (0.38, 0.40), **flat(2, 13, (0.40, 0.42)), 14: (0.45, 0.47)}                                # YES rides and loses; NO is cut
C = {1: (0.38, 0.40), **flat(2, 12, (0.40, 0.42)), 13: (0.45, 0.47), 14: (0.60, 0.62)}              # +$5 only at j = 14 (last 10%)
D = {1: (0.38, 0.40), **flat(2, 12, (0.40, 0.42)), 13: (0.54, 0.56), 14: (0.54, 0.56)}              # take-profit at j = 13
E = {1: (0.38, 0.40), **flat(2, 13, (0.40, 0.42))}                                                  # no book at j = 14: settles
I = flat(1, 14, (0.85, 0.97))                                                                       # mid 0.91: NO tradable (15m)
J = {1: (0.08, 0.10), 2: (0.10, 0.11), 3: (0.05, 0.09), 4: (0.91, 0.93), 5: (0.89, 0.90)}          # side price band edges
MK15 = [('A', A, 'yes'), ('B', B, 'no'), ('C', C, 'no'), ('D', D, 'no'), ('E', E, 'yes'), ('I', I, 'no'), ('J', J, 'no')]
O15 = {name: T0 + i * 15 * MIN for i, (name, _, _) in enumerate(MK15)}

# Hourly ladder markets (window = the last 60 minutes, decisions k = 5..50, no take-profit at j >= 54).
F = {5: (0.38, 0.40), **flat(6, 52, (0.40, 0.42)), 53: (0.54, 0.56), **flat(54, 59, (0.40, 0.42))}  # take-profit at j = 53
G = {5: (0.38, 0.40), **flat(6, 53, (0.40, 0.42)), 54: (0.54, 0.56), **flat(55, 59, (0.40, 0.42))}  # +$5 only at j = 54: cut at 59
HB = {**flat(5, 20, (0.85, 0.97)), **flat(21, 59, (0.40, 0.42))}                                   # YES mid 0.91 until k = 20
C60 = {'F': T0 + 3 * H, 'F2': T0 + 3 * H, 'G': T0 + 4 * H, 'HB': T0 + 5 * H}
DROPPED_SPOT = O15['A'] + 5 * MIN          # the spot minute ending at (A, k=5) is missing from the spot part


@pytest.fixture(scope='module')
def built(tmp_path_factory):
    root = tmp_path_factory.mktemp('pp')
    hist, parts = str(root / 'history'), str(root / 'parts')
    write_markets(hist, 'KXBTC15M', [m15(n, O15[n], q, r) for n, q, r in MK15])
    write_markets(hist, 'KXBTCD', [m60('26MAY0103', C60['F'], F, 'no'), m60('26MAY0103', C60['F2'], F, 'yes', strike=60_250.0),
                                   m60('26MAY0104', C60['G'], G, 'no'), m60('26MAY0105', C60['HB'], HB, 'no')])
    t_end, close = spot_path(T0 - 86_400_000, 2 * 1440, seed=3)
    keep = t_end != DROPPED_SPOT
    spot = write_spot_part(parts, 'BTC', t_end[keep], close[keep])
    logs: list = []
    p15 = Part(pp.build(15, hist, spot, 'BTC', parts, code_sha='test', log=logs.append))
    p60 = Part(pp.build(60, hist, spot, 'BTC', parts, code_sha='test', log=logs.append))
    return {'hist': hist, 'parts': parts, 'spot': spot, 'p15': p15, 'p60': p60, 'logs': logs, 'sp': Part(spot)}


def row(part, t):
    i = np.nonzero(part['t'] == t)[0]
    assert len(i) == 1, (t, i)
    return int(i[0])


def rows_at(part, t):
    return np.nonzero(part['t'] == t)[0]


def val(part, name, i):
    return float(part[name][i])


# ---------- hand-computed exits ----------

def test_fee_literals_used_below():
    """The fees the hand computations use (bot/fees.ts: 0.07 C P (1-P), up to the cent)."""
    for C, p, fee in ((50, 0.40, 0.84), (50, 0.45, 0.87), (50, 0.53, 0.88), (50, 0.54, 0.87), (50, 0.60, 0.84),
                      (32, 0.62, 0.53), (32, 0.53, 0.56), (42, 0.47, 0.74), (42, 0.54, 0.74), (48, 0.41, 0.82),
                      (48, 0.54, 0.84), (25, 0.40, 0.42), (25, 0.54, 0.44)):
        assert float(taker_fee(C, p)) == pytest.approx(fee, abs=1e-12), (C, p)


def test_take_profit(built):
    """A, YES at k=1: ask 0.40, C = 50, cost 50 x 0.40 + 0.84 = 20.84. Bid 0.53 at j=3 nets 26.50 - 0.88 - 20.84 = 4.78
    (< $5); bid 0.54 at j=4 nets 27.00 - 0.87 - 20.84 = 5.29: take-profit at j=4, hold 3 minutes."""
    p = built['p15']
    i = row(p, O15['A'] + MIN)
    assert p['ok_Y15'][i] == 1
    assert val(p, 'trade_Y15', i) == pytest.approx(5.29, abs=1e-6)
    assert p['hit_Y15'][i] == 1 and p['hold_Y15'][i] == 3
    assert val(p, 'best_Y15', i) == pytest.approx(50 - 20.84, abs=1e-6)           # settlement (YES won) beats every sale


def test_take_profit_allowed_until_tau_over_10pct(built):
    """15m: j = 13 is 120 s before close (> 90 s): a take-profit is allowed there. D: 0.54 at j = 13 -> +5.29, hold 12."""
    p = built['p15']
    i = row(p, O15['D'] + MIN)
    assert val(p, 'trade_Y15', i) == pytest.approx(5.29, abs=1e-6)
    assert p['hit_Y15'][i] == 1 and p['hold_Y15'][i] == 12


def test_ride_in_profit_then_lose(built):
    """B, YES at k=1: no sale reaches $5; at j = 14 the bid 0.45 nets 22.50 - 0.87 - 20.84 = +0.79 > 0, so it rides; it
    settles NO: -20.84, no hit, held to the close (14 minutes). best = the j=14 sale, +0.79."""
    p = built['p15']
    i = row(p, O15['B'] + MIN)
    assert val(p, 'trade_Y15', i) == pytest.approx(-20.84, abs=1e-6)
    assert p['hit_Y15'][i] == 0 and p['hold_Y15'][i] == 14
    assert val(p, 'best_Y15', i) == pytest.approx(0.79, abs=1e-6)


def test_cut_at_final_minute_no_side(built):
    """B, NO at k=1: NO ask = 1 - 0.38 = 0.62, C = floor(20/0.62) = 32, cost 19.84 + 0.53 = 20.37. At j = 14 the NO bid is
    1 - 0.47 = 0.53: 16.96 - 0.56 - 20.37 = -3.97 <= 0, so it is sold there (hold 13), although NO then settled in the
    money: best = settlement 32 - 20.37 = 11.63 ('no hold to settlement unless in profit')."""
    p = built['p15']
    i = row(p, O15['B'] + MIN)
    assert p['ok_N15'][i] == 1
    assert val(p, 'trade_N15', i) == pytest.approx(-3.97, abs=1e-6)
    assert p['hit_N15'][i] == 0 and p['hold_N15'][i] == 13
    assert val(p, 'best_N15', i) == pytest.approx(11.63, abs=1e-6)


def test_no_take_profit_in_last_10pct(built):
    """C, YES at k=1: only j = 14 (60 s before close, inside the last 90 s) nets >= $5 (30.00 - 0.84 - 20.84 = 8.32): no
    take-profit there; in profit at the final minute it rides and settles NO: -20.84. best still counts that sale."""
    p = built['p15']
    i = row(p, O15['C'] + MIN)
    assert val(p, 'trade_Y15', i) == pytest.approx(-20.84, abs=1e-6)
    assert p['hit_Y15'][i] == 0 and p['hold_Y15'][i] == 14
    assert val(p, 'best_Y15', i) == pytest.approx(8.32, abs=1e-6)


def test_ride_settles_win_and_no_book_at_final_minute(built):
    """A, YES at k=2: ask 0.47, C = 42, cost 19.74 + 0.74 = 20.48; the bid tops out at 0.54 (22.68 - 0.74 - 20.48 = +1.46,
    < $5), in profit at j = 14 -> rides, YES wins: 42 - 20.48 = 21.52, hit (>= $5 at settlement), hold 13.
    E, YES at k=1: no two-sided book at j = 14, nothing to sell into: it settles (YES won): 50 - 20.84 = 29.16."""
    p = built['p15']
    i = row(p, O15['A'] + 2 * MIN)
    assert val(p, 'trade_Y15', i) == pytest.approx(21.52, abs=1e-6)
    assert p['hit_Y15'][i] == 1 and p['hold_Y15'][i] == 13
    i = row(p, O15['E'] + MIN)
    assert val(p, 'trade_Y15', i) == pytest.approx(29.16, abs=1e-6)
    assert p['hit_Y15'][i] == 1 and p['hold_Y15'][i] == 14


def test_size2_latency_and_cost_stress(built):
    """A, YES at k=1.
    size 2 ($10): C = 25, cost 10.00 + 0.42 = 10.42; best sale 13.50 - 0.44 - 10.42 = 2.64 < $5, rides, wins 25 - 10.42 = 14.58.
    latency: the same trade entered at k=2 (ask 0.47): 21.52 (as the k=2 row).
    cost +1c: entry 0.41, C = 48, cost 19.68 + 0.82 = 20.50; best sale 25.92 - 0.84 - 20.50 = 4.58 < $5, rides: 48 - 20.50 = 27.50."""
    p = built['p15']
    i = row(p, O15['A'] + MIN)
    assert val(p, 'trade2_Y15', i) == pytest.approx(14.58, abs=1e-6) and p['hit2_Y15'][i] == 1
    assert val(p, 'tradeLat_Y15', i) == pytest.approx(21.52, abs=1e-6)
    assert val(p, 'tradeCost_Y15', i) == pytest.approx(27.50, abs=1e-6)


def test_latency_equals_next_row_trade(built):
    """tradeLat at k equals trade at k + 1 wherever both rows are tradable and the band holds at k + 1."""
    p = built['p15']
    t, g = p['t'], p['group']
    for s in 'YN':
        ok, tr, lat = p[f'ok_{s}15'], p[f'trade_{s}15'], p[f'tradeLat_{s}15']
        nxt = {(int(g[i]), int(t[i])): i for i in range(p.n)}
        n = 0
        for i in range(p.n):
            j = nxt.get((int(g[i]), int(t[i]) + MIN))
            if j is not None and ok[i] and ok[j]:
                assert lat[i] == pytest.approx(tr[j], abs=1e-5)
                n += 1
        assert n > 0


def test_hourly_tp_boundary(built):
    """Hourly (60 min, last 10% = 6 min): F, YES at k=5, bid 0.54 at j = 53 (tau 7 min) -> take-profit +5.29, hold 48.
    G: 0.54 only at j = 54 (tau 6 min, not > 6): no take-profit; at j = 59 the bid 0.40 nets 20.00 - 0.84 - 20.84 = -1.68
    -> sold there, hold 54; best = the j=54 sale, +5.29."""
    p = built['p60']
    oF = C60['F'] - H
    i = [k for k in rows_at(p, oF + 5 * MIN)]
    gF = min(int(p['group'][k]) for k in i)              # F was written before F2 (same open): lower market index
    iF = [k for k in i if p['group'][k] == gF][0]
    assert val(p, 'trade_Y60', iF) == pytest.approx(5.29, abs=1e-6)
    assert p['hit_Y60'][iF] == 1 and p['hold_Y60'][iF] == 48
    iG = row(p, C60['G'] - H + 5 * MIN)
    assert val(p, 'trade_Y60', iG) == pytest.approx(-1.68, abs=1e-6)
    assert p['hit_Y60'][iG] == 0 and p['hold_Y60'][iG] == 54
    assert val(p, 'best_Y60', iG) == pytest.approx(5.29, abs=1e-6)


def test_simulate_unit():
    """simulate() on one hand-made path (YES at k=1, ask 0.40): TP at the first j with net >= $5 outside the last 10%."""
    n = 15
    bid = np.full((3, n), np.nan)
    bid[0, 2:] = 0.54                     # TP at j=2
    bid[1, 2:14] = 0.40                   # final 0.40: -1.68, sold
    bid[1, 14] = 0.40
    bid[2, 2:] = 0.45                     # final 0.45: +0.79, rides
    r = pp.simulate(bid, np.array([0.0, 1.0, 1.0]), 1, np.array([0.40, 0.40, 0.40]), 20.0, n)
    assert np.allclose(r['trade'], [5.29, -1.68, 29.16])
    assert r['hit'].tolist() == [True, False, True]
    assert r['hold'].tolist() == [1, 13, 14]
    assert r['C'].tolist() == [50, 50, 50]
    assert pp.tp_zone(15).nonzero()[0].max() == 13 and pp.tp_zone(60).nonzero()[0].max() == 53
    # tradeSettle (sensitivity): no sale at the final candle; the position cut at 0.40 settles instead (YES won: 50 -
    # 20.84 = 29.16), the take-profit and the ride are unchanged
    assert np.allclose(r['trade_settle'], [5.29, 29.16, 29.16])


def test_no_side_float_price_is_sized_on_the_cent_grid():
    """Review fix (Nov 6): a NO ask is 1 - YES bid in float (1 - 0.84 = 0.16000000000000003). The prereg C =
    min(floor(20 / ask), 250) is 125 at 16c; an unrounded floor gave 124. Same at the +1c cost-stress price 0.15 + 0.01."""
    no_ask = 1 - 0.84
    assert no_ask != 0.16 and math.floor(20 / no_ask) == 124          # the float trap itself
    n = 15
    bid = np.full((2, n), np.nan)
    bid[:, 2:] = 1 - 0.99                                              # NO bid 1c to the end: a loser cut at j = 14
    r = pp.simulate(bid, np.zeros(2), 1, np.array([no_ask, 0.15 + 0.01]), 20.0, n)
    assert r['C'].tolist() == [125, 125]
    fee = float(taker_fee(125, 0.16))                                  # 0.07 x 125 x 0.16 x 0.84 = 1.176 -> 1.18
    sell = round(125 * 0.01 - float(taker_fee(125, 0.01)), 6)          # 1.25 - 0.09
    assert r['trade'][0] == pytest.approx(sell - (20.0 + fee), abs=1e-9)


# ---------- windows, bands, join ----------

def test_entry_window_bounds(built):
    p15, p60 = built['p15'], built['p60']
    assert set(p15['kmin'].tolist()) <= set(range(1, 11)) and p15['kmin'].min() == 1 and p15['kmin'].max() == 10
    assert set(p60['kmin'].tolist()) <= set(range(5, 51)) and p60['kmin'].min() == 5 and p60['kmin'].max() == 50
    # A has quotes at k = 1..14: rows exactly at k = 1..10 except the k = 5 minute whose spot row is missing.
    ta = p15['t'][(p15['t'] > O15['A']) & (p15['t'] < O15['A'] + 15 * MIN)]
    assert sorted(((ta - O15['A']) // MIN).tolist()) == [1, 2, 3, 4, 6, 7, 8, 9, 10]
    # 840..300 s before close (15m) and 3300..600 s (hourly)
    left = (p15['t'] - O15['A']) % (15 * MIN)
    assert np.all(np.isin(15 * 60 - left[p15['t'] < O15['A'] + 15 * MIN] // 1000, np.arange(300, 841, 60)))
    tf = p60['t'][(p60['t'] > C60['G'] - H) & (p60['t'] < C60['G'])]
    assert sorted(((C60['G'] - tf) // 1000).tolist()) == list(range(600, 3301, 60))
    assert np.all(np.diff(p15['t']) >= 0) and np.all(np.diff(p60['t']) >= 0)


def test_side_price_band(built):
    """J: k=1 YES ask 0.10 (ok) / NO ask 0.92 (not); k=2 both ok (0.11 / 0.90); k=3 (0.09 / 0.95) and k=4 (0.93 / 0.09):
    no tradable side -> no row; k=5 YES ask 0.90 ok, NO ask 0.11 ok."""
    p = built['p15']
    o = O15['J']
    assert len(rows_at(p, o + 3 * MIN)) == 0 and len(rows_at(p, o + 4 * MIN)) == 0
    i1, i2, i5 = row(p, o + MIN), row(p, o + 2 * MIN), row(p, o + 5 * MIN)
    assert (p['ok_Y15'][i1], p['ok_N15'][i1]) == (1, 0)
    assert (p['ok_Y15'][i2], p['ok_N15'][i2]) == (1, 1)
    assert (p['ok_Y15'][i5], p['ok_N15'][i5]) == (1, 1)
    assert np.isnan(p['trade_N15'][i1]) and p['stratum_N'][i1] == -1 and p['hit_N15'][i1] == 0
    names = [f['name'] for f in p.features]
    assert p['X'][i1, names.index('k_price@Y')] == 0 and p['X'][i1, names.index('k_price@N')] == -1
    assert p['X'][i5, names.index('k_price@Y')] == 7 and p['X'][i5, names.index('k_price@N')] == 0


def test_hourly_mid_band(built):
    """HB quotes YES 0.85 / 0.97 (mid 0.91) at k = 5..20: NO's ask 0.15 is inside the side band, but the hourly mid band
    [0.10, 0.90] removes those decisions; the same book on a 15-minute contract (I) is a NO decision."""
    p60, p15 = built['p60'], built['p15']
    o = C60['HB'] - H
    tk = p60['t'][(p60['t'] > o) & (p60['t'] < C60['HB'])]
    assert sorted(((tk - o) // MIN).tolist()) == list(range(21, 51))
    iI = row(p15, O15['I'] + MIN)
    assert (p15['ok_Y15'][iI], p15['ok_N15'][iI]) == (0, 1)


def test_spot_join_alignment(built):
    """Spot columns, rv and z come from the spot row whose t_end equals t_k; a decision without one is dropped."""
    p, sp = built['p15'], built['sp']
    names = [f['name'] for f in p.features]
    X, t = p['X'], p['t']
    assert len(rows_at(p, DROPPED_SPOT)) == 0
    assert any(', 1 without a spot row' in s for s in built['logs'])
    assert np.array_equal(X[:, names.index('sx_mod7')], ((t // MIN) % 7).astype(np.int8))       # the minute ENDING at t
    st = sp['t_end']
    j = np.searchsorted(st, t)
    assert np.array_equal(st[j], t)
    assert np.array_equal(p['rv'], sp['rv'][j])
    assert np.array_equal(X[:, :3], sp['X'][j])
    # z and fair at (A, k=3) from the spot close / rv60 at t_end == t
    i = row(p, O15['A'] + 3 * MIN)
    js = int(np.searchsorted(st, t[i]))
    z = math.log(sp['close'][js] / 60_000.0) / (float(sp['rv60'][js]) / math.sqrt(60) * math.sqrt(15 - 3))
    assert X[i, names.index('k_z@Y')] == np.searchsorted(pp.Z_EDGES, z, side='right')
    assert X[i, names.index('k_z@N')] == np.searchsorted(pp.Z_EDGES, -z, side='right')
    gap = float(ndtr(z)) - 0.54
    assert X[i, names.index('k_fair@Y')] == np.searchsorted(pp.GAP_EDGES, gap, side='right')
    assert X[i, names.index('k_fair@N')] == np.searchsorted(pp.GAP_EDGES, -gap, side='right')


def test_contract_features_and_strata(built):
    p = built['p15']
    names = [f['name'] for f in p.features]
    X = p['X']
    i3 = row(p, O15['A'] + 3 * MIN)       # YES mid 0.54 vs 0.46 (k=2): +8c over 1 min; vs 0.39 (k=1): +15c over 3 min? no: k-3 = 0
    assert X[i3, names.index('k_dmid1@Y')] == 1 and X[i3, names.index('k_dmid1@N')] == -1
    assert X[i3, names.index('k_dmid3@Y')] == 0           # k - 3 = 0: minute 0 has no quote (NA -> 0)
    i4 = row(p, O15['A'] + 4 * MIN)       # 0.55 vs 0.39 at k=1
    assert X[i4, names.index('k_dmid3@Y')] == 1 and X[i4, names.index('k_dmid3@N')] == -1
    assert X[i4, names.index('k_spread')] == 1            # 2c
    assert X[i4, names.index('k_tau')] == 0 and X[row(p, O15['A'] + 7 * MIN), names.index('k_tau')] == 1
    assert X[row(p, O15['A'] + 8 * MIN), names.index('k_tau')] == 2
    # strata: (price bucket x 3 + tau bucket) x 4 + rv slot
    i1 = row(p, O15['A'] + MIN)
    rv = int(p['rv'][i1])
    assert p['stratum_Y'][i1] == (3 * 3 + 0) * 4 + (rv if rv >= 0 else 3)        # YES ask 0.40 -> bucket 3
    assert p['stratum_N'][i1] == (5 * 3 + 0) * 4 + (rv if rv >= 0 else 3)        # NO ask 0.62 -> bucket 5
    assert pp.vol_bucket(np.array([0.0, 5.0, 10.0, 50.0, 5000.0]), [10.0, 100.0, 1000.0]).tolist() == [0, 1, 2, 2, 4]
    assert pp.spread_bucket(np.array([0.01, 0.015, 0.02, 0.05, 0.06])).tolist() == [0, 1, 1, 2, 3]
    assert pp.price_bucket(np.array([0.09, 0.10, 0.199, 0.20, 0.30, 0.899, 0.90, 0.91])).tolist() == [-1, 0, 0, 1, 2, 7, 7, -1]


def test_meta_side_features_and_format(built):
    for p, h in ((built['p15'], 15), (built['p60'], 60)):
        m = p.meta
        assert m['schema'] == 'oracle-part-1' and m['sides'] == ['Y', 'N'] and m['horizons'] == [h]
        assert m['size_usd'] == 20.0 and m['size2_usd'] == 10.0 and m['assets'] == ['BTC'] and m['scope'] == 'BTC'
        names = [f['name'] for f in m['features']]
        for s, other in (('Y', 'N'), ('N', 'Y')):
            cols = m['side_features'][s]
            assert cols and all(names[c].endswith('@' + s) for c in cols)
            assert sorted(c for c in range(len(names)) if names[c].endswith('@' + s)) == sorted(cols)
            assert not set(cols) & set(m['side_features'][other])
        assert p['X'].dtype == np.int8 and p['X'].shape == (p.n, len(names))
        for name, dt in (('t', np.int64), ('group', np.int64), ('asset', np.int8), ('rv', np.int8), ('hour', np.int8),
                         ('stratum_Y', np.int16), (f'ok_Y{h}', np.uint8), (f'hit_N{h}', np.uint8), (f'trade_Y{h}', np.float32),
                         (f'best_N{h}', np.float32), (f'hold_Y{h}', np.uint16), (f'hit2_Y{h}', np.uint8), (f'trade2_N{h}', np.float32),
                         (f'tradeLat_Y{h}', np.float32), (f'tradeCost_N{h}', np.float32)):
            assert p[name].dtype == dt, name
        ok = p[f'ok_Y{h}'].astype(bool)
        assert np.all(np.isfinite(p[f'trade_Y{h}'][ok])) and np.all(np.isnan(p[f'trade_Y{h}'][~ok]))
        assert np.all(p[f'best_Y{h}'][ok] >= p[f'trade_Y{h}'][ok] - 1e-5)
        assert np.array_equal(p['hour'], ((p['t'] // 3_600_000) % 24).astype(np.int8))
    p60 = built['p60']
    oF = C60['F'] - H
    i = rows_at(p60, oF + 5 * MIN)
    assert len(i) == 2 and len(set(p60['group'][i].tolist())) == 2 and len(set(p60['event'][i].tolist())) == 1


# ---------- hard rules ----------

def test_doge_refused(built, tmp_path):
    with pytest.raises(ValueError, match='DOGE'):
        pp.build(15, built['hist'], built['spot'], 'DOGE', str(tmp_path))
    with pytest.raises(ValueError, match='DOGE'):
        pp.main(['--kind', '60', '--history', built['hist'], '--spot', built['spot'], '--asset', 'doge', '--out', str(tmp_path)])
    os.makedirs(tmp_path / 'spot-DOGE', exist_ok=True)
    with pytest.raises(ValueError, match='DOGE'):
        pp.build(15, built['hist'], str(tmp_path / 'spot-DOGE'), 'BTC', str(tmp_path))
    with pytest.raises(ValueError, match='XRP'):
        pp.build(60, built['hist'], built['spot'], 'XRP', str(tmp_path))
    assert not os.path.exists(tmp_path / 'pp15-DOGE') and not os.path.exists(tmp_path / 'pp60-DOGE')


def test_no_file_from_nov5_is_opened(tmp_path, monkeypatch):
    """Day files dated 2026-11-05 or later (embargo, lockbox) are never opened; a stray market closing after HOLD_TO inside
    an earlier file is dropped; a .jsonl not named by day is refused."""
    hist, parts = str(tmp_path / 'h'), str(tmp_path / 'p')
    write_markets(hist, 'KXBTC15M', [m15('A', O15['A'], A, 'yes')])
    late = [m15('L1', ms('2026-11-05T00:00'), A, 'yes'), m15('L2', ms('2026-11-07T10:00'), A, 'no')]
    write_markets(hist, 'KXBTC15M', late)
    stray = m15('S', ms('2026-11-04T23:55'), A, 'yes')
    with open(os.path.join(hist, 'kalshi', 'KXBTC15M', '2026-11-04.jsonl'), 'w') as fh:
        import json
        fh.write(json.dumps(stray) + '\n')
    t_end, close = spot_path(T0 - 86_400_000, 2 * 1440, seed=3)
    spot = write_spot_part(parts, 'BTC', t_end, close)
    opened: list = []
    real_open = builtins.open

    def spy(f, *a, **k):
        opened.append(str(f))
        return real_open(f, *a, **k)

    monkeypatch.setattr(apdata, 'open', spy, raising=False)
    logs: list = []
    p = Part(pp.build(15, hist, spot, 'BTC', parts, code_sha='test', log=logs.append))
    days = [os.path.basename(f)[:10] for f in opened if f.endswith('.jsonl')]
    assert days and all(d < '2026-11-05' for d in days), days
    assert any('dropped 1 closing after HOLD_TO' in s for s in logs)
    assert p['t'].max() < ms('2026-11-05')
    with open(os.path.join(hist, 'kalshi', 'KXBTC15M', 'extra.jsonl'), 'w') as fh:
        fh.write('\n')
    with pytest.raises(SystemExit, match='not named by UTC day'):
        pp.build(15, hist, spot, 'BTC', parts, code_sha='test', log=logs.append)


def test_make_aligned_prices_on_an_existing_spot_part(tmp_path):
    """fixtures_pp.make_aligned (the end-to-end fixture) writes day files only, priced on a spot part it did not write; pp.py
    joins every decision to that spot part and settles on its close."""
    from oracle.fixtures_pp import make_aligned
    t_end, close = spot_path(T0 - 86_400_000, 3 * 1440, seed=5)
    spot = write_spot_part(str(tmp_path / 'parts'), 'BTC', t_end, close)
    r = make_aligned(str(tmp_path / 'k'), spot, 'BTC', '2026-05-01', 1, seed=4)
    assert (r['n15'], r['n60']) == (96, 96) and not os.path.exists(tmp_path / 'k' / 'parts')
    at = dict(zip(t_end.tolist(), close.tolist()))
    logs: list = []
    p15 = Part(pp.build(15, r['history'], spot, 'BTC', str(tmp_path / 'out'), code_sha='test', log=logs.append))
    assert p15.n > 0 and any(', 0 without a spot row' in s for s in logs)
    sp = Part(spot)
    i = np.searchsorted(sp['t_end'], p15['t'])
    assert np.array_equal(sp['t_end'][i], p15['t'])
    assert all(k in at for k in p15['t'][:10].tolist())
    with pytest.raises(ValueError, match='DOGE'):
        make_aligned(str(tmp_path / 'd'), spot, 'DOGE')
