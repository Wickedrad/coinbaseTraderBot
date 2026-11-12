"""OR-HM2 extra data and new readings (python/oracle/heat_xdata.py): no lookahead (perturb the future, the codes up to
the cut stay the same, for each input alone and all together), the stamp rules (funding calc_time + 1 minute, open
interest create_time + 5 minutes, daily stamp + 24 hours, 13-digit milliseconds, HEAT_END, DOGE), the joint coin flip
(equal to heat.make_twin on the job coin, the same flips on every path, the real levels unchanged), zone edges and norm
tables from A only, the stale rule, the macro windows in ET with daylight saving, the entry-minute states, the other
coins' direct engine readings against heat_live.tf_codes, the inventory, the copies merge, ZS states and the live
levels. Synthetic minutes; SPLITS patched to 65 days ending at HEAT_END (A 50, B 15)."""
import os

import numpy as np
import pandas as pd
import pytest

from oracle import heat
from oracle.common import DAY, MIN, ms

pytest.importorskip('talib')
from oracle import heat_clock, heat_live, heat_xdata as X  # noqa: E402

HOUR = 60 * MIN
E = heat.HEAT_END
DAYS = 65
START = E - DAYS * DAY
SPL = {'A': (START, E - 15 * DAY), 'B': (E - 15 * DAY, E)}
CAL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'calendars', 'macro_calendar_2020_2025.csv')
DNAMES = ['ETH.D', 'DXY', 'SPX']
COINSPEC = {'BTC': (1.0, 100.0, 0.01, 0), 'ETH': (0.8, 50.0, 0.01, 0), 'SOL': (1.2, 20.0, 0.001, 10), 'XRP': (1.0, 0.5, 0.0001, 0)}


def _bars(rng, r, p0, grid):
    n = len(r)
    c = np.round(p0 * np.exp(np.cumsum(r)) / grid) * grid
    o = np.r_[c[0], c[:-1]]
    w = np.abs(rng.normal(0, 2e-4, n))
    h = np.round(np.maximum(o, c) * (1 + w) / grid + 0.5) * grid
    l = np.round(np.minimum(o, c) * (1 - w) / grid - 0.5) * grid
    v = rng.uniform(1, 2, n)
    return {'o': o, 'h': h, 'l': l, 'c': c, 'v': v, 'tb': v * rng.uniform(0.3, 0.7, n)}


def _world(d, seed=0):
    """Four coins (SOL-like starting 10 days later), BTC's perp, funding, open interest, Coinbase minutes, BTCDOM hours,
    book snapshots and three daily series (stamped 00:00, 23:00 and 14:30 UTC, running past HEAT_END)."""
    rng = np.random.default_rng(seed)
    n = DAYS * 1440
    ts = START + np.arange(n, dtype=np.int64) * MIN
    f = rng.standard_t(4, n) * 4e-4
    P = {}
    for coin, (b, p0, grid, late) in COINSPEC.items():
        bars = _bars(rng, b * f + rng.normal(0, 2e-4, n), p0, grid)
        df = pd.DataFrame({'ts': ts, **bars})
        df = df[df.ts >= START + late * DAY]
        if coin == 'BTC':
            df = df.drop(index=list(range(30_000, 30_004)) + list(range(60_000, 60_031)))      # a short gap and a long outage
        if coin == 'ETH':
            df = df.drop(index=[45_000])
        df.to_csv(d / f'{coin}.csv', index=False)
        P[coin] = str(d / f'{coin}.csv')
        if coin == 'BTC':
            spot = df.set_index('ts')['c']
    # the perp: spot x (1 + a slowly moving basis), from day 2
    bas = 5 + np.cumsum(rng.normal(0, 0.05, n)) * 0 + pd.Series(rng.normal(0, 1, n)).ewm(alpha=1 / 240).mean().to_numpy() * 40
    sp = spot.reindex(ts).ffill().bfill().to_numpy()
    pc = np.round(sp * (1 + bas / 1e4) / 0.01) * 0.01
    po = np.r_[pc[0], pc[:-1]]
    pv = rng.uniform(5, 9, n)
    perp = pd.DataFrame({'ts': ts, 'o': po, 'h': np.maximum(po, pc) + 0.01, 'l': np.minimum(po, pc) - 0.01, 'c': pc, 'v': pv, 'tb': pv * rng.uniform(0.3, 0.7, n)})
    perp = perp[perp.ts >= START + 2 * DAY].drop(index=range(50_000, 50_010))
    perp.to_csv(d / 'perp.csv', index=False)
    P['perp'] = str(d / 'perp.csv')
    # funding every 8 hours: the mean basis of the 8 hours BEFORE the stamp (settlement convention), earlier ones random
    T = np.arange(START - 40 * DAY, E, 8 * HOUR, dtype=np.int64)
    bs = pd.Series(bas, index=ts)
    rate = []
    for t in T:
        w = bs[(bs.index >= t - 8 * HOUR) & (bs.index < t)]
        rate.append((w.mean() if len(w) > 400 else rng.normal(5, 2)) / 1e4 * 0.3 + rng.normal(0, 2e-6))
    pd.DataFrame({'ts': T, 'rate': rate}).to_csv(d / 'funding.csv', index=False)
    P['funding'] = str(d / 'funding.csv')
    # open interest every 5 minutes
    To = np.arange(START - DAY, E, 5 * MIN, dtype=np.int64)
    oi = 1000 * np.exp(np.cumsum(rng.normal(0, 2e-3, len(To))))
    odf = pd.DataFrame({'ts': To, 'oi': oi, 'oi_usd': oi * 100})
    odf = odf.drop(index=range(9000, 9004))                                                  # a 25-minute hole
    odf.to_csv(d / 'oi.csv', index=False)
    P['oi'] = str(d / 'oi.csv')
    # Coinbase minutes from day 5: spot x a small premium
    cp = np.round(sp * (1 + pd.Series(rng.normal(0, 1, n)).ewm(alpha=0.05).mean().to_numpy() * 3 / 1e4) / 0.01) * 0.01
    co = np.r_[cp[0], cp[:-1]]
    cb = pd.DataFrame({'ts': ts, 'o': co, 'h': np.maximum(co, cp) + 0.01, 'l': np.minimum(co, cp) - 0.01, 'c': cp, 'v': rng.uniform(1, 2, n)})
    cb[cb.ts >= START + 5 * DAY].to_csv(d / 'cb.csv', index=False)
    P['cb'] = str(d / 'cb.csv')
    # BTCDOM hours
    Th = np.arange(START - 60 * DAY, E, HOUR, dtype=np.int64)
    hc = 500 * np.exp(np.cumsum(rng.normal(0, 3e-3, len(Th))))
    pd.DataFrame({'ts': Th, 'o': hc, 'h': hc * 1.001, 'l': hc * 0.999, 'c': hc, 'v': 1.0}).drop(index=[100]).to_csv(d / 'btcdom.csv', index=False)
    P['btcdom'] = str(d / 'btcdom.csv')
    # book snapshots every 2 minutes from day 3, a 20-minute hole
    Tb = np.arange(START + 3 * DAY, E, 2 * MIN, dtype=np.int64)
    bk = pd.DataFrame({'ts': Tb, 'bid_depth_1pct': rng.uniform(10, 20, len(Tb)), 'ask_depth_1pct': rng.uniform(10, 20, len(Tb))})
    bk.drop(index=range(5000, 5010)).to_csv(d / 'book.csv', index=False)
    P['book'] = str(d / 'book.csv')
    # daily series, past HEAT_END (the loader drops what is known at or after it)
    dd = d / 'dom'
    dd.mkdir(exist_ok=True)
    days = np.arange(START - 200 * DAY, E + 30 * DAY, DAY, dtype=np.int64)
    for nm, off, wk in (('ETH.D', 0, False), ('DXY', 23 * HOUR, True), ('SPX', 14 * HOUR + 30 * MIN, True)):
        t = days + off
        if wk:
            t = t[((t // DAY + 3) % 7) < 5]
        c = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, len(t))))
        pd.DataFrame({'ts': t, 'o': c, 'h': c, 'l': c, 'c': c, 'v': 0}).to_csv(dd / f'{nm}_1d.csv', index=False)
    P['dom'] = str(dd)
    return P


@pytest.fixture(scope='module')
def world(tmp_path_factory):
    old = heat.SPLITS
    heat.SPLITS = SPL
    try:
        d = tmp_path_factory.mktemp('hm2x')
        P = _world(d)
        yield P
    finally:
        heat.SPLITS = old


@pytest.fixture
def splits():
    old = heat.SPLITS
    heat.SPLITS = SPL
    yield
    heat.SPLITS = old


def _inputs(P, asset='BTC', twin=0, cal=True):
    m_real = heat.load_minutes(P[asset])
    li = X.load_inputs(asset, m_real, twin, {o: P[o] for o in X.COINS if o != asset}, P['perp'], P['funding'], P['oi'], CAL if cal else None,
                       {'btcdom': P['btcdom'], 'cb': P['cb'], 'book': P['book']}, log=lambda *a: None)
    m = heat.make_twin(m_real, twin) if twin else m_real
    return m, m_real, li['kwargs'], li['flip']


def _run(m, kw, edges=None, norms=None, other_metas=None, P=None, info=None):
    a_hi = X.split_rows(m['t0'], m['n'])[1]
    return X.extra_readings(m, a_hi, other_metas=other_metas, dom_dir=P['dom'], daily_names=DNAMES, edges=edges, norms=norms,
                            info=info, log=lambda *a: None, **kw)


def _codes_upto(R, t):
    return heat.read_state(R, np.arange(t + 1))


# ------------------------------------------------------------------------------------------------------- no lookahead
def _noise_minutes(mo, cut_ms, rng):
    """A minutes dict whose minutes opening at or after cut_ms are replaced by another random path (same grid)."""
    out = dict(mo)
    j = int(np.clip((cut_ms - mo['t0']) // MIN, 0, mo['n']))
    if j >= mo['n']:
        return out
    k = mo['n'] - j
    grid = 0.0001 if mo['c'][0] < 5 else (0.001 if mo['c'][0] < 30 else 0.01)
    p0 = mo['c'][j - 1] if j > 0 else mo['c'][0]
    b = _bars(rng, rng.normal(0, 2e-3, k), p0, grid)
    for x in ('o', 'h', 'l', 'c', 'v', 'tb'):
        if out.get(x) is not None:
            out[x] = np.r_[mo[x][:j], b[x]]
    out['gap'] = np.r_[mo['gap'][:j], rng.random(k) < 0.01]
    if 'tick' in mo:
        out['tick'] = heat.tick_bps(out['c'], out['gap'])
    return out


def _noise_grid(pg, cut_ms, rng):
    """On-grid perp / Coinbase minutes with the future replaced (NaN-led arrays kept)."""
    out = dict(pg)
    j = int(np.clip((cut_ms - pg['t0']) // MIN, 0, pg['n']))
    k = pg['n'] - j
    if k <= 0:
        return out
    p0 = np.nanmax(pg['c'][:j]) if j > 0 else 100.0
    b = _bars(rng, rng.normal(0, 3e-3, k), p0, 0.01)
    for x in ('o', 'h', 'l', 'c', 'v', 'tb'):
        if out.get(x) is not None:
            out[x] = np.r_[pg[x][:j], b[x]]
    out['gap'] = np.r_[pg['gap'][:j], rng.random(k) < 0.02]
    return out


def _noise_frame(df, kind, cut_ms, rng):
    """A load_extra frame whose rows not yet known at cut_ms are replaced by noise (the calendar: unscheduled events
    not yet known, and scheduled ones on later ET days, moved at random)."""
    df = df.copy()
    if kind == 'calendar':
        fut = np.where(df['scheduled'], df['day_lo'] > cut_ms, df['known'] > cut_ms)
        sh = rng.integers(-300, 300, int(fut.sum())) * MIN
        df.loc[fut, 'ts'] = df.loc[fut, 'ts'] + sh
        df.loc[fut, 'known'] = np.where(df.loc[fut, 'scheduled'], 0, df.loc[fut, 'ts'] + MIN)
        return df.sort_values('ts').reset_index(drop=True)
    fut = df['known'].to_numpy() > cut_ms
    k = int(fut.sum())
    for c in {'funding': ['rate'], 'oi': ['oi'], 'daily': ['c'], 'book': ['bid', 'ask'], 'idx1h': ['c']}[kind]:
        x = df[c].to_numpy(float).copy()
        x[fut] = np.abs(rng.normal(np.nanmean(x), 3 * np.nanstd(x) + 1e-9, k)) + 1e-9
        df[c] = x
    return df


def _daily_frames(P):
    return {nm: X.load_extra(os.path.join(P['dom'], f'{nm}_1d.csv'), 'daily') for nm in DNAMES}


def test_cut_future_new_readings(world):
    """Every new reading and its ZS state: the codes at rows <= t do not change when the inputs after t are noise, each
    input alone and all together, at five cut points (two in A with the edges and norm tables fixed, three in B where the
    edges come from A untouched)."""
    P = world
    m, _, kw, _ = _inputs(P)
    info = {}
    R0, e0, nm0, miss = _run(m, kw, P=P, info=info)
    assert miss == [], miss
    base = {R['name']: R for R in R0 + X.zs_readings(R0)}
    assert len(R0) > 60 and not info['not_found']
    om = {O: {'edges': {'1m:RSI14': e0[f'X.{O}:RSI14'], '1m:TakerBuy': e0[f'X.{O}:TakerBuy']}, 'price_step': heat.tick_units(kw['others'][O], X.split_rows(kw['others'][O]['t0'], kw['others'][O]['n'])[1]).get('step')}
          for O in kw['others']}
    a_hi = X.split_rows(m['t0'], m['n'])[1]
    cuts = [a_hi // 2 + 7, a_hi - 3000, a_hi + 1500, m['n'] - 6000, m['n'] - 777]
    rng = np.random.default_rng(5)
    daily0 = _daily_frames(P)
    inputs = ['own', 'BTCDOM', 'perp', 'funding', 'oi', 'cb', 'book', 'calendar'] + [f'other:{o}' for o in kw['others']] + [f'daily:{n}' for n in DNAMES]
    bad = []
    for ci, t in enumerate(cuts):
        cut_ms = m['t0'] + (t + 1) * MIN                       # the close of row t
        fixed = ci < 2
        for which in inputs + ['all']:
            if which != 'all' and ci not in (0, 2) and which not in ('own', 'perp', 'other:SOL', 'calendar'):
                continue                                      # each input alone at two cut points; all together at five
            kw2 = dict(kw, others=dict(kw['others']), found=dict(kw['found']))
            m2, daily = m, dict(daily0)
            al = which == 'all'
            if al or which == 'own':
                m2 = _noise_minutes(m, cut_ms, rng)
            for o in kw['others']:
                if al or which == f'other:{o}':
                    kw2['others'][o] = _noise_minutes(kw['others'][o], cut_ms, rng)
            if al or which == 'perp':
                kw2['perp'] = _noise_grid(kw['perp'], cut_ms, rng)
            if al or which == 'cb':
                kw2['found']['cb'] = _noise_grid(kw['found']['cb'], cut_ms, rng)
            for key, kind in (('fund', 'funding'), ('oi', 'oi'), ('cal', 'calendar')):
                if al or which == {'fund': 'funding'}.get(key, key) or (key == 'cal' and which == 'calendar'):
                    kw2[key] = _noise_frame(kw[key], kind, cut_ms, rng)
            for key, kind in (('btcdom', 'idx1h'), ('book', 'book')):
                if al or which == {'btcdom': 'BTCDOM'}.get(key, key):
                    kw2['found'][key] = _noise_frame(kw['found'][key], kind, cut_ms, rng)
            for nmd in DNAMES:
                if al or which == f'daily:{nmd}':
                    daily[nmd] = _noise_frame(daily0[nmd], 'daily', cut_ms, rng)
            kw2['real'] = {'m': m2, 'perp': kw2['perp']}
            a2 = X.split_rows(m2['t0'], m2['n'])[1]
            R2, _, _, _ = X.extra_readings(m2, a2, other_metas=om if fixed else None, dom_dir=daily, daily_names=DNAMES, edges=e0 if fixed else None,
                                           norms=nm0 if fixed else None, log=lambda *a: None, **kw2)
            got = {R['name']: R for R in R2 + X.zs_readings(R2)}
            assert set(got) == set(base), (which, set(base) ^ set(got))
            for name, R in base.items():
                if not np.array_equal(_codes_upto(R, t), _codes_upto(got[name], t)):
                    bad.append((t, which, name))
    assert not bad, bad[:20]


def test_cross_coin_code_is_the_other_coins_code_at_the_same_minute(world):
    """X.O readings are O's own at the same UTC minute: with the later-starting coin as own and as other (offset sign)."""
    P = world
    for own, other in (('BTC', 'SOL'), ('SOL', 'BTC')):
        m = heat.load_minutes(P[own])
        mo = heat.load_minutes(P[other])
        off = (mo['t0'] - m['t0']) // MIN
        assert (off > 0) == (own == 'BTC')
        # the same fixed edges on both: X.O:R5z on own's grid and O's own FLOW:Stretch5 on O's grid
        e = [-2.0, -1.0, 1.0, 2.0]
        fx = {'X.' + other + ':R5z': e, 'FLOW:Stretch5': e, f'X.{other}:RSI14': [20, 30, 70, 80], f'X.{other}:TakerBuy': [0.35, 0.4, 0.6, 0.65]}
        R = {r['name']: r for r in X.cross_readings(m, {other: mo}, None, 0, X.Zoner(0, fx))}
        Ro = {r['name']: r for r in X.flow_readings(mo, 0, X.Zoner(0, fx))}
        d = X.other_direct(mo, None, {'1m:RSI14': [20, 30, 70, 80], '1m:TakerBuy': [0.35, 0.4, 0.6, 0.65]})
        i = np.arange(m['n'])
        j = i - off
        ok = (j >= 0) & (j < mo['n'])
        assert ok.sum() > 50_000
        a, b = R[f'X.{other}:R5z']['codes'], Ro['FLOW:Stretch5']['codes']
        assert np.array_equal(a[ok], b[j[ok]]) and (a[~ok] == -1).all() and (a[ok] >= 0).mean() > 0.8
        assert np.array_equal(R[f'X.{other}:RSI14']['codes'][ok], d['1m:RSI14'][0][j[ok]])
        assert np.array_equal(R[f'X.{other}:TakerBuy']['codes'][ok], d['1m:TakerBuy'][0][j[ok]])


def test_other_coin_direct_equals_tf_codes(world):
    """X.O:RSI14 and X.O:TakerBuy are the engine's own 1-minute readings of O: heat_live.tf_codes on O's whole grid (its
    edges from O's A rows, and with stored edges and price step)."""
    P = world
    for O in ('ETH', 'SOL'):
        mo = heat.load_minutes(P[O])
        lo, hi = X.split_rows(mo['t0'], mo['n'])
        step = heat.tick_units(mo, hi).get('step')
        R, used, s = heat_live.tf_codes(mo, 1, edges=None, step=step, window=None, a_rows=(lo, hi), want_bases={'1m:RSI14', '1m:TakerBuy'})
        R = {r['name']: r for r in R}
        d = X.other_direct(mo)
        assert set(d) == {'1m:RSI14', '1m:TakerBuy'} == set(R)
        for nm, (codes, e) in d.items():
            assert np.array_equal(codes, R[nm]['codes']) and list(e) == list(used[nm]), nm
        d2 = X.other_direct(mo, {'edges': used, 'price_step': step})
        assert all(np.array_equal(d2[k][0], R[k]['codes']) for k in R)


# -------------------------------------------------------------------------------------------------------- stamp rules
def test_stamp_rules(world, tmp_path):
    P = world
    m = heat.load_minutes(P['BTC'])
    close = m['t0'] + (np.arange(m['n']) + 1) * MIN
    # funding: unknown until calc_time + 1 minute (calc_time <= the open of minute i)
    fund = X.load_extra(P['funding'], 'funding')
    f = X.fund_on_grid(m, fund)
    T = int(fund['ts'].to_numpy()[(fund['ts'] > m['t0'] + 20 * DAY).argmax()])
    i = (T - m['t0']) // MIN - 1                                  # the row whose close is T
    assert close[i] == T
    zprev, znew = f['z'][i], f['z'][i + 1]
    j = int(np.searchsorted(fund['ts'].to_numpy(), T))
    r = fund['rate'].to_numpy()
    sd = pd.Series(r).rolling(90, min_periods=90).std().shift(1).to_numpy()
    assert znew == pytest.approx(r[j] / sd[j]) and zprev == pytest.approx(r[j - 1] / sd[j - 1])
    assert f['to_next'][i] == 0 and f['to_next'][i + 1] == 8 * HOUR - MIN           # FundClock: last + the gap between the last two
    # open interest: unknown until create_time + 5 minutes, carried at most 10 minutes
    oi = X.load_extra(P['oi'], 'oi')
    L = X.oi_on_grid(m, oi)
    t1 = int(oi['ts'].to_numpy()[(oi['ts'] > m['t0'] + DAY).argmax()])
    k = (t1 + 5 * MIN - m['t0']) // MIN - 1                         # the row whose close is create_time + 5 minutes
    assert L[k] == pytest.approx(np.log(oi.loc[oi.ts == t1, 'oi'].iloc[0])) and L[k - 1] != pytest.approx(L[k])
    hole = oi['ts'].to_numpy()
    g = np.nonzero(np.diff(hole) > 5 * MIN)[0][0]                    # the 25-minute hole: carried 10 minutes, then NA
    last = hole[g] + 5 * MIN
    rows = (last - m['t0']) // MIN - 1 + np.arange(0, 16)
    assert np.isfinite(L[rows[:11]]).all() and np.isnan(L[rows[11:]]).all()
    # a daily bar stamped 23:00 UTC on day D is unknown before 23:00 UTC on day D + 1
    d = X.load_extra(os.path.join(P['dom'], 'DXY_1d.csv'), 'daily')
    s = int(d['ts'].to_numpy()[(d['ts'] > m['t0'] + 10 * DAY).argmax()])
    assert s % DAY == 23 * HOUR and int(d.loc[d.ts == s, 'known'].iloc[0]) == s + DAY
    R = X.daily_readings(m, {'DXY': d}, ['DXY'])[0]
    ii = (s + DAY - m['t0']) // MIN - 1
    zz = pd.Series(d['c'].to_numpy() / np.r_[np.nan, d['c'].to_numpy()[:-1]] - 1)
    zs = (zz / zz.rolling(60, min_periods=40).std().shift(1)).to_numpy()
    jj = int(np.searchsorted(d['ts'].to_numpy(), s))
    assert R['codes'][ii] == heat.bucket(zs[jj:jj + 1], heat.DOM_Z)[0] and R['codes'][ii - 1] == heat.bucket(zs[jj - 1:jj], heat.DOM_Z)[0]
    # 13-digit ms only; nothing at or after HEAT_END (strict); daily rows known at or after it dropped; never DOGE
    for unit in (1000, 1 / 1000):
        bad = pd.read_csv(P['funding'])
        bad['ts'] = (bad['ts'] / unit).astype(np.int64)
        bad.to_csv(tmp_path / 'f.csv', index=False)
        with pytest.raises(SystemExit):
            X.load_extra(str(tmp_path / 'f.csv'), 'funding')
    for kind, src in (('funding', P['funding']), ('oi', P['oi']), ('perp1m', P['perp'])):
        late = pd.read_csv(src)
        late.loc[len(late) - 1, 'ts'] = E
        late.to_csv(tmp_path / 'late.csv', index=False)
        with pytest.raises(SystemExit):
            X.load_extra(str(tmp_path / 'late.csv'), kind)
        assert X.load_extra(str(tmp_path / 'late.csv'), kind, strict=False)['ts'].max() < E
    cal = pd.read_csv(CAL)
    cal.loc[len(cal)] = ['2026-01-02', '08:30', '2026-01-02T13:30Z', 'NFP', 'x', True]
    cal.to_csv(tmp_path / 'cal.csv', index=False)
    with pytest.raises(SystemExit):
        X.load_extra(str(tmp_path / 'cal.csv'), 'calendar')
    dd = X.load_extra(os.path.join(P['dom'], 'ETH.D_1d.csv'), 'daily')
    assert dd.attrs['dropped_late'] >= 30 and (dd['known'] < E).all() and dd['known'].max() == E - DAY
    os.makedirs(tmp_path / 'DOGE', exist_ok=True)
    pd.read_csv(P['funding']).to_csv(tmp_path / 'DOGE' / 'funding.csv', index=False)
    with pytest.raises(SystemExit):
        X.load_extra(str(tmp_path / 'DOGE' / 'funding.csv'), 'funding')
    with pytest.raises(SystemExit):
        X.extra_readings(m, 0, asset='DOGE', log=lambda *a: None)
    # broken rows are dropped and counted
    br = pd.read_csv(P['perp']).head(100)
    br.loc[3, 'h'] = br.loc[3, 'l'] / 2
    br.loc[4, 'c'] = np.nan
    br.to_csv(tmp_path / 'br.csv', index=False)
    x = X.load_extra(str(tmp_path / 'br.csv'), 'perp1m')
    assert len(x) == 98 and x.attrs['bad_rows'] == 2
    # the stamps preflight reads a file's two ends
    sp = X.ts_span(P['funding'])
    assert sp['ms13'] and sp['first'] == fund['ts'].iloc[0] and sp['last'] == fund['ts'].iloc[-1]


def test_fetch_cut_keeps_2019_to_2026(tmp_path):
    """(review fix) The fetch script's cut drops rows before 2019-01-01 (heat_xdata.MS_LO) as well as rows at or after the
    2026 cut, so a found file whose backfill starts in 2015 (Coinbase's default) loads strictly instead of stopping every
    job of its coin; a file with no row in that range stops at the cut."""
    import shutil
    import subprocess
    if shutil.which('bash') is None or shutil.which('awk') is None:
        pytest.skip('bash and awk are needed')
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
    script = os.path.join(root, '.github', 'scripts', 'oracle-hm2-data.sh')
    f = tmp_path / 'cb.csv'
    rows = [ms('2015-01-01'), ms('2020-01-01'), ms('2020-01-01') + MIN, heat.HEAT_END]
    pd.DataFrame({'ts': rows, 'o': 1.0, 'h': 1.0, 'l': 1.0, 'c': 1.0, 'v': 1.0}).to_csv(f, index=False)
    r = subprocess.run(['bash', script, 'cut', str(f), 'found cb'], cwd=root, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    df = X.load_extra(str(f), 'cb1m')
    assert len(df) == 2 and pd.read_csv(f)['ts'].tolist() == rows[1:3]
    old = tmp_path / 'old.csv'
    pd.DataFrame({'ts': [ms('2015-01-01')], 'o': 1.0}).to_csv(old, index=False)
    r = subprocess.run(['bash', script, 'cut', str(old), 'old'], cwd=root, capture_output=True, text=True)
    assert r.returncode != 0 and 'no row from 2019-01-01' in r.stderr


def test_funding_stamp_check(world):
    """The real file's stamps are the settlement (the rate follows the 8 hours before); the same rates stamped at the
    start of their period fail the check."""
    P = world
    m = heat.load_minutes(P['BTC'])
    pg = X.on_grid(m, X.load_extra(P['perp'], 'perp1m'))
    with np.errstate(invalid='ignore'):
        bas = (pg['c'] - m['c']) / m['c'] * 1e4
    fund = X.load_extra(P['funding'], 'funding')
    a_hi = X.split_rows(m['t0'], m['n'])[1]
    ok = X.funding_stamp_check(fund, bas, a_hi, m['t0'])
    assert ok['ok'] and ok['n'] > 100 and ok['corr_before'] > ok['corr_after'] + 0.1
    early = fund.copy()
    early['ts'] = early['ts'] - 8 * HOUR
    bad = X.funding_stamp_check(early, bas, a_hi, m['t0'], stop=False)
    assert not bad['ok'] and bad['corr_after'] > bad['corr_before']
    with pytest.raises(SystemExit):
        X.funding_stamp_check(early, bas, a_hi, m['t0'])


# --------------------------------------------------------------------------------------------------------- joint flip
def test_joint_flip(world):
    """On the job coin the joint flip is heat.make_twin(m, seed) bit for bit; a coin on the same grid gets exactly its
    own make_twin of the same seed; the later-starting coin, the perp and Coinbase carry the same flip per minute; as
    the job coin, the later-starting coin's twin reaches back with a second seeded stream. The real levels (basis,
    funding, open interest, daily markets, BTCDOM, book, macro, position, clock) equal the coin's."""
    P = world
    m = heat.load_minutes(P['BTC'])
    for seed in (1, 2):
        fl = X.joint_flip(seed, m['t0'], m['n'])
        tw, mt = fl(m), heat.make_twin(m, seed)
        assert all(np.array_equal(tw[x], mt[x]) for x in ('o', 'h', 'l', 'c', 'v', 'tb', 'gap', 'tick'))
        for O in ('ETH', 'XRP'):
            mo = heat.load_minutes(P[O])
            assert mo['t0'] == m['t0']
            to = fl(mo)
            assert all(np.array_equal(to[x], heat.make_twin(mo, seed)[x]) for x in ('o', 'h', 'l', 'c', 'tb'))
        sol = heat.load_minutes(P['SOL'])
        ts = fl(sol)
        off = (sol['t0'] - m['t0']) // MIN
        s_btc = np.sign(np.diff(np.log(tw['c']))) * np.sign(np.diff(np.log(m['c'])))
        s_sol = np.sign(np.diff(np.log(ts['c']))) * np.sign(np.diff(np.log(sol['c'])))
        both = (s_btc[off:] != 0) & (s_sol != 0)
        assert both.sum() > 40_000 and (s_btc[off:][both] == s_sol[both]).all()
        pg = X.on_grid(m, X.load_extra(P['perp'], 'perp1m'))
        pt = fl(pg)
        assert np.isnan(pt['c'][:pg['first']]).all() and np.isfinite(pt['c'][pg['first']:]).all()
        s_p = np.sign(np.diff(np.log(pt['c']))) * np.sign(np.diff(np.log(pg['c'])))
        ok = np.isfinite(s_p) & (s_p != 0) & (s_btc != 0)
        assert ok.sum() > 40_000 and (s_p[ok] == s_btc[ok]).all()
        swap = (s_btc == -1)
        assert np.allclose(pt['tb'][1:][swap & np.isfinite(pg['tb'][1:])], (pg['v'] - pg['tb'])[1:][swap & np.isfinite(pg['tb'][1:])])
        # the later-starting coin as the job coin: its own twin is make_twin; BTC's earlier minutes take a second stream
        fs = X.joint_flip(seed, sol['t0'], sol['n'])
        assert np.array_equal(fs(sol)['c'], heat.make_twin(sol, seed)['c'])
        sg = fs.signs(m['t0'], m['n'])
        assert np.array_equal(sg[off:], fs.s) and fs.s[0] == 1.0                     # SOL's own minutes: make_twin's sequence
        assert np.array_equal(sg[:off], X.joint_flip(seed, sol['t0'], sol['n']).signs(m['t0'], off)) and set(np.unique(sg[:off])) == {-1.0, 1.0}
        assert not np.array_equal(sg[:off], X.joint_flip(seed + 1, sol['t0'], sol['n']).signs(m['t0'], off))
    # real levels on a twin equal the coin's
    mr, _, kw, _ = _inputs(P)
    R0 = {r['name']: r for r in _run(mr, kw, P=P)[0]}
    mt, _, kwt, _ = _inputs(P, twin=1)
    Rt = {r['name']: r for r in _run(mt, kwt, P=P)[0]}
    real = [n for n in R0 if n.split(':')[0] in ('POS', 'MACRO', 'DMKT', 'IDX', 'BOOK') or n in X.CLOCK_NAMES
            or n in ('PERP:Basis', 'PERP:BasisChg15', 'PERP:FundZ', 'PERP:FundClock', 'OI:Chg15', 'OI:Chg60')]
    assert len(real) >= 20
    for n in real:
        assert np.array_equal(R0[n]['codes'], Rt[n]['codes']), n
    moved = [n for n in R0 if n.startswith(('X.ETH:R5z', 'FLOW:Stretch5', 'PERP:Lead1', 'CB:Lead1', 'VOL:Jump1', 'OI:PxQuad60'))]
    assert len(moved) == 6 and all(not np.array_equal(R0[n]['codes'], Rt[n]['codes']) for n in moved)
    # the twin's other-coin RSI14 edges are its own (HM1's twin edges for a coin on the job coin's grid)
    assert X.other_meta_key('ETH', 1, mr, kwt['others']['ETH']) == 'ETH-twin1' and X.other_meta_key('SOL', 1, mr, kwt['others']['SOL']) is None
    assert X.other_meta_key('SOL', 0, mr, kw['others']['SOL']) == 'SOL'
    eth_t = X.joint_flip(1, mr['t0'], mr['n'])(heat.load_minutes(P['ETH']))
    lo, hi = X.split_rows(eth_t['t0'], eth_t['n'])
    _, used, _ = heat_live.tf_codes(eth_t, 1, edges=None, step=heat.tick_units(eth_t, hi).get('step'), window=None, a_rows=(lo, hi), want_bases={'1m:RSI14'})
    assert Rt['X.ETH:RSI14']['edges'] == used['1m:RSI14'] != R0['X.ETH:RSI14']['edges']


# ------------------------------------------------------------------------------------------------ edges, norms, stale
def test_zone_edges_and_norms_from_A_only(world):
    """Changing every B row (all inputs) changes no edge and no norm table; the edges are the A rows' ZONE_Q quantiles."""
    P = world
    m, _, kw, _ = _inputs(P)
    info = {'keep_values': True}
    R0, e0, n0, _ = _run(m, kw, P=P, info=info)
    a_hi = X.split_rows(m['t0'], m['n'])[1]
    x = info['values']['VOL:RV1d']
    xa = x[:a_hi][np.isfinite(x[:a_hi])]
    assert np.allclose(e0['VOL:RV1d'], np.quantile(xa, heat.ZONE_Q), rtol=0, atol=0)
    assert len(n0['VOL:RVclock']) == 168 and len(n0['VOL:Busy']) == 1440
    hw = X._hour_of_week(m['t0'] + np.arange(m['n']) * MIN)
    assert hw[0] == ((m['t0'] // DAY + 3) % 7) * 24 and set(np.unique(hw)) == set(range(168))
    rng = np.random.default_rng(9)
    cut = m['t0'] + (a_hi + 61) * MIN
    kw2 = dict(kw, others={o: _noise_minutes(v, cut, rng) for o, v in kw['others'].items()}, perp=_noise_grid(kw['perp'], cut, rng),
               found={'cb': _noise_grid(kw['found']['cb'], cut, rng), 'btcdom': _noise_frame(kw['found']['btcdom'], 'idx1h', cut, rng),
                      'book': _noise_frame(kw['found']['book'], 'book', cut, rng)},
               fund=_noise_frame(kw['fund'], 'funding', cut, rng), oi=_noise_frame(kw['oi'], 'oi', cut, rng))
    m2 = _noise_minutes(m, cut, rng)
    kw2['real'] = {'m': m2, 'perp': kw2['perp']}
    R2, e2, n2, _ = _run(m2, kw2, P=P)
    assert e2 == e0 and n2 == n0
    assert any(not np.array_equal(a['codes'], b['codes']) for a, b in zip(R0, R2))


def test_stale_rule():
    gap = np.zeros(3000, bool)
    gap[1000] = True
    s = X.stale_rows(gap, 1)
    assert not s[999] and s[1000:1101].all() and not s[1101]               # the gap and the 100 rows after it (the engine's)
    s5 = X.stale_rows(gap, 5)
    assert not s5[999] and s5[1000:1105].all() and not s5[1105]           # a window of 5 rows holds it for 4 more rows
    gap[2000:2020] = True                                                  # a long outage: 500 rows after its 15th row
    s = X.stale_rows(gap, 1)
    assert s[2014 + 500] and not s[2019 + 501] and s[2019 + 100]
    eng = pd.Series(gap.astype(np.float32)).rolling(heat.STALE + 1, min_periods=1).max().to_numpy() > 0
    run = pd.Series(gap.astype(np.int64)).groupby(np.cumsum(~gap)).cumsum().to_numpy()
    eng |= pd.Series((run > heat.STALE_LONG[0]).astype(np.float32)).rolling(heat.STALE_LONG[1] + 1, min_periods=1).max().to_numpy() > 0
    assert np.array_equal(X.stale_rows(gap, 1), eng)
    # on a reading: FLOW:TB5 is NA exactly on the windows that hold or follow the gap
    n = 3000
    m = {'t0': ms('2025-03-01'), 'n': n, 'c': 100 * np.exp(np.cumsum(np.random.default_rng(0).normal(0, 1e-3, n))), 'v': np.ones(n), 'tb': np.full(n, 0.5),
         'gap': np.zeros(n, bool)}
    m['gap'][1000] = True
    R = {r['name']: r for r in X.flow_readings(m, n, X.Zoner(n, {'FLOW:TB5': [0.1, 0.2, 0.8, 0.9]}))}
    c = R['FLOW:TB5']['codes']
    assert (c[4:1000] == 2).all() and (c[1000:1105] == -1).all() and (c[1105:] == 2).all()


# ------------------------------------------------------------------------------------------- entry-minute states, macro
def test_entry_minute_states():
    """Position and clock codes at row i are those of minute i + 1; NY30m follows daylight saving."""
    for day in ('2025-07-01', '2025-12-01'):
        t0 = ms(day)
        m = {'t0': t0, 'n': 2 * 1440}
        R = {r['name']: r for r in X.position_readings(m) + X.clock_readings(m)}
        rows = np.arange(m['n'])
        st = {nm: heat.read_state(R[nm], rows) for nm in R}
        assert [R['POS:QPos']['levels'][c] for c in st['POS:QPos'][12:16]] == ['m13', 'm14', 'm00', 'm01']
        assert R['POS:QPhase']['levels'][st['POS:QPhase'][13]] == 'm10-14' and R['POS:HourQ']['levels'][st['POS:HourQ'][14]] == 'h15-29'
        for i in np.random.default_rng(1).integers(60, m['n'] - 1, 300):
            ent = t0 + (i + 1) * MIN
            assert st['POS:QPos'][i] == (ent // MIN) % 15 and st['POS:HourQ'][i] == ((ent // MIN) % 60) // 15
            lv = heat_clock.levels_at(ent)
            for nm in X.CLOCK_NAMES:
                c = st[nm][i]
                assert c < 0 or R[nm]['levels'][c] == lv[nm], (nm, i)
        i = (ms(day + 'T13:30') - t0) // MIN - 1                           # the entry minute opens at 13:30 UTC
        assert R['NY30m']['levels'][st['NY30m'][i]] == ('09:30' if day.startswith('2025-07') else '08:30')


def _cal_frame(rows):
    """A calendar frame as load_extra gives it, from (date_et, time_et, kind, scheduled) rows."""
    out = []
    for d, t, k, s in rows:
        loc = pd.Timestamp(f'{d} {t}').tz_localize('America/New_York')
        out.append({'date_et': d, 'time_et': t, 'ts_utc': loc.tz_convert('UTC').strftime('%Y-%m-%dT%H:%MZ'), 'kind': k, 'source': 't', 'scheduled': s})
    return pd.DataFrame(out)


def test_macro_windows_et_with_daylight_saving(tmp_path):
    """8:30 AM ET is 12:30 UTC in summer and 13:30 UTC in winter; the windows are those of the entry minute; an
    unscheduled statement has no 'before' level and its day is a release day only from its own minute."""
    df = _cal_frame([('2025-10-15', '08:30', 'CPI', True), ('2025-11-05', '08:30', 'PPI', True), ('2025-11-05', '14:00', 'FOMC', True),
                     ('2025-11-07', '10:00', 'FOMC', False)])
    df.to_csv(tmp_path / 'c.csv', index=False)
    cal = X.load_extra(str(tmp_path / 'c.csv'), 'calendar')
    assert list(cal['ts']) == [ms('2025-10-15T12:30'), ms('2025-11-05T13:30'), ms('2025-11-05T19:00'), ms('2025-11-07T15:00')]
    m = {'t0': ms('2025-10-10'), 'n': 30 * 1440}
    R = {r['name']: r for r in X.macro_readings(m, cal)}

    def lv(nm, entry):                                                   # the level at the row whose entry minute opens at `entry`
        i = (entry - m['t0']) // MIN - 1
        return R[nm]['levels'][R[nm]['codes'][i]]
    for ev in (ms('2025-10-15T12:30'), ms('2025-11-05T13:30')):
        assert [lv('MACRO:R830', ev + d * MIN) for d in (-31, -30, -1, 0, 14, 15, 59, 60, 239, 240)] == \
            ['none', '30-1 before', '30-1 before', '0-14 after', '0-14 after', '15-59 after', '15-59 after', '60-239 after', '60-239 after', 'none']
    f = ms('2025-11-05T19:00')
    assert [lv('MACRO:FOMC', f + d * MIN) for d in (-30, 0, 100)] == ['30-1 before', '0-14 after', '60-239 after']
    u = ms('2025-11-07T15:00')                                           # unscheduled: known from the close of its minute
    assert [lv('MACRO:FOMC', u + d * MIN) for d in (-30, -1, 0, 1, 14, 15)] == ['none', 'none', 'none', '0-14 after', '0-14 after', '15-59 after']
    et0 = ms('2025-11-07T05:00')                                         # 00:00 EST
    assert [lv('MACRO:ReleaseDay', x) for x in (et0 + 60 * MIN, u, u + MIN, et0 + DAY - MIN, et0 + DAY)] == \
        ['none', 'none', 'release day', 'release day', 'none']
    ed = ms('2025-10-15T04:00')                                          # 00:00 EDT: a scheduled day is known in advance
    assert [lv('MACRO:ReleaseDay', x) for x in (ed - MIN, ed, ed + DAY - MIN, ed + DAY)] == ['none', 'release day', 'release day', 'none']
    # an unscheduled statement's minute not yet known: perturbing it moves nothing at or before its close
    df2 = df.copy()
    df2.loc[3, 'time_et'] = '16:00'
    df2.loc[3, 'ts_utc'] = '2025-11-07T21:00Z'
    df2.to_csv(tmp_path / 'c2.csv', index=False)
    R2 = {r['name']: r for r in X.macro_readings(m, X.load_extra(str(tmp_path / 'c2.csv'), 'calendar'))}
    i = (u - m['t0']) // MIN - 1
    assert all(np.array_equal(R[n]['codes'][:i + 1], R2[n]['codes'][:i + 1]) for n in R)
    # ET and UTC must agree: a row whose ts_utc ignores daylight saving is refused
    bad = df.copy()
    bad.loc[0, 'ts_utc'] = '2025-10-15T13:30Z'
    bad.to_csv(tmp_path / 'bad.csv', index=False)
    with pytest.raises(SystemExit):
        X.load_extra(str(tmp_path / 'bad.csv'), 'calendar')


def test_release_calendar_file():
    """The committed calendar: 262 events; every CPI, jobs and PPI row a weekday at 08:30 ET, every scheduled FOMC row
    at 14:00 ET, the three unscheduled 2020 statements at their own times."""
    cal = X.load_extra(CAL, 'calendar')
    assert len(cal) == 262 and (cal['ts'] < E).all()
    r = cal[cal.kind.isin(X.R830_KINDS)]
    loc = [pd.Timestamp(t, unit='ms', tz='UTC').tz_convert('America/New_York') for t in r['ts']]
    assert all(x.dayofweek < 5 and (x.hour, x.minute) == (8, 30) for x in loc) and len(r) == 212
    f = cal[(cal.kind == 'FOMC') & cal.scheduled]
    assert all((x.hour, x.minute) == (14, 0) for x in (pd.Timestamp(t, unit='ms', tz='UTC').tz_convert('America/New_York') for t in f['ts']))
    u = cal[~cal.scheduled]
    assert list(u['date_et'] + ' ' + u['time_et']) == ['2020-03-03 10:00', '2020-03-15 17:00', '2020-03-23 08:00'] and (u['known'] == u['ts'] + MIN).all()
    summer, winter = cal[cal.date_et == '2020-07-14'], cal[cal.date_et == '2020-01-14']
    assert pd.Timestamp(int(winter.ts.iloc[0]), unit='ms').hour == 13 and pd.Timestamp(int(summer.ts.iloc[0]), unit='ms').hour == 12


# ------------------------------------------------------------------------------------------------- inventory, merges
def test_inventory():
    dom = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), 'research', 'btcd_fractal', 'data')
    lst = {}
    for c in X.COINS:
        lst[c] = [{'Path': p, 'IsDir': False} for p in (f'binance-1m/{c}/1m.csv', f'binance-um/{c}/1m.csv', f'binance-um/{c}/1h.csv', 'binance-um/manifest.json',
                                                         f'binance-funding/{c}/funding.csv', f'binance-oi/{c}/oi.csv', 'binance-1h/ETH/1h.csv')]
    lst['BTC'] += ['binance-index/BTCDOM/1h.csv', 'coinbase/BTC/15m.csv', 'binance-1m/DOGE/1m.csv']
    lst['ETH'] += ['coinbase-1m/ETH/1m.csv']
    inv = X.inventory(lst, dom)
    assert inv['ok'], (inv['missing'], inv['unmapped'])
    assert inv['found']['btcdom'] == ['BTC/binance-index/BTCDOM/1h.csv'] and inv['found']['cb'] == {'ETH': 'ETH/coinbase-1m/ETH/1m.csv'}
    fam = {(r['coin'], r['folder']): r for r in inv['sources']}
    assert fam[('BTC', 'coinbase')]['family'] is None and fam[('BTC', 'binance-1h')]['reason'] and fam[('BTC', 'binance-um')]['used'] == ['binance-um/BTC/1m.csv']
    d = {r['file']: r for r in inv['daily']}
    assert d['DXY_1d.csv']['family'] == 'dmkt' and d['M2_1d.csv']['family'] is None and 'leak' in d['M2_1d.csv']['reason'] and d['BTC.D_1d.csv']['family'] == 'dominance'
    assert all(r['family'] or r['reason'] for r in inv['daily'])
    # a missing open-interest file and an unknown source both fail the preflight, loudly
    lst2 = {c: list(v) for c, v in lst.items()}
    lst2['SOL'] = [x for x in lst2['SOL'] if 'binance-oi' not in x['Path']]
    lst2['XRP'].append('kraken-1m/XRP/1m.csv')
    inv2 = X.inventory(lst2, dom)
    assert not inv2['ok'] and inv2['missing'] == ['raw/perp-ta-history/SOL/binance-oi/SOL/oi.csv'] and inv2['unmapped'] == ['XRP/kraken-1m']
    inv3 = X.inventory(lst, list(os.listdir(dom)) + ['NEW_1d.csv'])
    assert not inv3['ok'] and inv3['unmapped'] == ['research/btcd_fractal/data/NEW_1d.csv']
    inv4 = X.inventory(lst, [f for f in os.listdir(dom) if f != 'SPX_1d.csv'])
    assert inv4['missing'] == ['research/btcd_fractal/data/SPX_1d.csv']


def test_merge_aliases():
    """An exact copy under another name (CMO = 2 RSI - 100) merges into the first by name; a near copy does not; two
    rare patterns that are 'none' together on almost every minute are not copies."""
    rng = np.random.default_rng(0)
    n = 60_000
    x = pd.Series(rng.normal(0, 1, n)).rolling(20, min_periods=1).mean().to_numpy()
    e = np.quantile(x, heat.ZONE_Q)
    rsi = {'name': '1m:RSI14', 'k': 1, 'codes': heat.bucket(x, e), 'levels': heat.ZONES, 'base': '1m:RSI14', 'zones': True}
    cmo = {'name': '1m:CMO14', 'k': 1, 'codes': heat.bucket(2 * x - 100, 2 * e - 100), 'levels': heat.ZONES, 'base': '1m:CMO14', 'zones': True}
    y = x + rng.normal(0, 0.05, n)
    near = {'name': '1m:RSI21', 'k': 1, 'codes': heat.bucket(y, np.quantile(y, heat.ZONE_Q)), 'levels': heat.ZONES, 'base': '1m:RSI21', 'zones': True}
    p1 = np.where(rng.random(n) < 0.004, 1, 0).astype(np.int8)
    p2 = np.where(rng.random(n) < 0.004, 2, 0).astype(np.int8)
    pa = {'name': '1m:CDL:A', 'k': 1, 'codes': p1, 'levels': ['none', 'bull', 'bear'], 'base': '1m:CDL:A', 'every': True}
    pb = {'name': '1m:CDL:B', 'k': 1, 'codes': p2, 'levels': ['none', 'bull', 'bear'], 'base': '1m:CDL:B', 'every': True}
    assert ((p1 == p2).mean()) > 0.99
    kept, al = X.merge_aliases([rsi, near, pa, cmo, pb], np.arange(0, n, 7))
    assert al == {'1m:CMO14': ['1m:RSI14']}
    names = [r['name'] for r in kept]
    assert names == ['1m:RSI21', '1m:CDL:A', '1m:CMO14', '1m:CDL:B']
    k = kept[2]
    assert k['aliases'] == ['1m:RSI14'] and k['alias_bases'] == ['1m:RSI14']


def test_zs_states():
    R = {'name': '1m:X', 'k': 5, 'codes': np.array([-1, 2, 1, 0, 0, 1, 2, 3, 4, 3, 2, 1, -1, 1], np.int8), 'levels': heat.ZONES, 'base': '1m:X', 'zones': True}
    zs = X.zs_readings([R, {'name': 'c', 'k': 1, 'codes': np.zeros(3, np.int8), 'levels': ['a', 'b'], 'base': 'c'}])
    assert len(zs) == 1 and zs[0]['name'] == 'ZS:1m:X' and zs[0]['levels'] == X.ZS_LEVELS and zs[0]['k'] == 5
    c = zs[0]['codes']
    assert [X.ZS_LEVELS[i] if i >= 0 else None for i in c] == [None, 'none', 'low (falling in)', 'very low', 'none', 'low (recovering)', 'none',
                                                                   'high (rising in)', 'very high', 'high (cooling)', 'none', 'low (falling in)', None, 'none']
    for lv, side, name in heat.event_levels(R):                         # the same bars as the engine's events
        ev = heat.level_events(R, lv, side)
        assert np.array_equal((ev - 4) // 5, np.nonzero(c == X.ZS_LEVELS.index(name))[0])


# ---------------------------------------------------------------------------------------------------------------- live
def test_levels_at_matches_history(world):
    """A live window ending at a minute, with the stored edges and norm tables, gives the history's level of every new
    reading at that minute."""
    P = world
    m, _, kw, _ = _inputs(P)
    R0, e0, n0, _ = _run(m, kw, P=P)
    om = {O: {'edges': {'1m:RSI14': e0[f'X.{O}:RSI14'], '1m:TakerBuy': e0[f'X.{O}:TakerBuy']},
              'price_step': heat.tick_units(kw['others'][O], X.split_rows(kw['others'][O]['t0'], kw['others'][O]['n'])[1]).get('step')} for O in kw['others']}
    meta = {'edges': e0, 'norms': n0, 'other_metas': om}
    df = {c: pd.read_csv(P[c]) for c in X.COINS}
    daily = _daily_frames(P)
    same = tot = 0
    for row in (m['n'] - 1, m['n'] - 1 - 1440 - 437, m['n'] - 1 - 3 * 1440 - 14):
        end = m['t0'] + (row + 1) * MIN
        lo = end - 14 * DAY
        win = heat_live.grid(df['BTC'][(df['BTC'].ts >= lo) & (df['BTC'].ts < end)], end)
        assert win['t0'] + win['n'] * MIN == end
        oth = {o: heat_live.grid(df[o][(df[o].ts >= lo) & (df[o].ts < end)], end) for o in kw['others']}
        cut = lambda f: f[f['ts'] < end]
        pg = X.on_grid(win, X.load_extra(P['perp'], 'perp1m').pipe(cut))
        cb = X.on_grid(win, X.load_extra(P['cb'], 'cb1m').pipe(cut))
        got = X.levels_at(win, meta, None, others=oth, perp=pg, fund=kw['fund'], oi=kw['oi'], daily=daily,
                          found={'btcdom': kw['found']['btcdom'], 'cb': cb, 'book': kw['found']['book']}, cal=kw['cal'])
        for R in R0:
            c = int(heat.read_state(R, np.array([row]))[0])
            want = R['levels'][c] if c >= 0 else None
            tot += 1
            same += got.get(R['name']) == want
            if got.get(R['name']) != want and not R['name'].startswith(('X.', 'VOL:VoV', 'VOL:RV7d')):
                raise AssertionError((row, R['name'], want, got.get(R['name'])))
    assert same / tot > 0.99, (same, tot)
