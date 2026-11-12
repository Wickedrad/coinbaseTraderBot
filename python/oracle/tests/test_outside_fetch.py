"""OR-XD fetch round (python/oracle/outside_reduce.py, outside_fetch.py): synthetic data only, network monkeypatched.
Fake zips are built in tmp: aggTrades spot without header (ms), spot 2025-style microseconds, um with header; metrics old,
new, ambiguous and off-grid days; a duplicate stamp across two files at the switch; premium next-minute fit; bookDepth
reshape and its spacing shift; resume skipping; the amb rule."""
import gzip
import hashlib
import io
import json
import os
import zipfile

import numpy as np
import pandas as pd
import pytest

from oracle import outside_fetch as fx, outside_reduce as red

MIN = 60_000
T0 = 1_709_337_600_000      # 2024-03-02 00:00:00 UTC (2024-03-01 19:00 EST)


def zbytes(name: str, text: str) -> bytes:
    b = io.BytesIO()
    with zipfile.ZipFile(b, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr(name, text)
    return b.getvalue()


# ------------------------------------------------------------------------------------------------------ aggTrades
def make_trades(seed=1, n=3000, minutes=10, start=T0 + 7 * MIN):
    rng = np.random.default_rng(seed)
    ts = np.sort(start + rng.integers(0, minutes * MIN, n))
    price = np.round(rng.uniform(40000, 41000, n), 2)
    notional = np.exp(rng.normal(8, 2.2, n))
    qty = np.round(notional / price, 6)
    maker = rng.random(n) < 0.5
    # planted bursts inside single calendar seconds: five 120k buys (600k) and three 400k sells (1.2M)
    s = start + 3 * MIN + 17_000
    extra_t, extra_p, extra_q, extra_m = [], [], [], []
    for i in range(5):
        extra_t.append(s + i * 100); extra_p.append(40000.0); extra_q.append(3.0); extra_m.append(False)
    s2 = start + 5 * MIN + 59_000
    for i in range(3):
        extra_t.append(s2 + i * 100); extra_p.append(40000.0); extra_q.append(10.0); extra_m.append(True)
    ts = np.r_[ts, extra_t].astype(np.int64)
    price = np.r_[price, extra_p]
    qty = np.r_[qty, extra_q]
    maker = np.r_[maker, extra_m]
    o = np.argsort(ts, kind='stable')
    return ts[o], price[o], qty[o], maker[o]


def brute(ts, price, qty, maker):
    out = {}
    secs = {}
    for t, p, q, m in zip(ts, price, qty, maker):
        mn = int(t // MIN * MIN)
        d = out.setdefault(mn, {'n_buy': 0, 'n_sell': 0, 'usd_buy': 0.0, 'usd_sell': 0.0})
        nt = float(p) * float(q)
        side = 's' if m else 'b'
        d['n_' + ('sell' if m else 'buy')] += 1
        d['usd_' + ('sell' if m else 'buy')] += nt
        for k in range(24):
            if nt >= red.EDGES[k]:
                d[f'n{side}_ge_{k}'] = d.get(f'n{side}_ge_{k}', 0) + 1
                d[f'u{side}_ge_{k}'] = d.get(f'u{side}_ge_{k}', 0.0) + nt
        secs[(mn, int(t // 1000), side)] = secs.get((mn, int(t // 1000), side), 0.0) + nt
    for (mn, sec, side), v in secs.items():
        for name, thr in red.SWEEP_THRESHOLDS:
            if v >= thr:
                out[mn][f'sw_{side}_{name}'] = out[mn].get(f'sw_{side}_{name}', 0) + 1
    return out


def check_frame(df, ref):
    assert list(df.columns) == red.AGG_COLUMNS
    for c, t in red.agg_dtypes().items():
        assert df[c].dtype == t, c
    assert list(df['ts']) == sorted(ref)
    for _, row in df.iterrows():
        d = ref[int(row['ts'])]
        for c in red.AGG_COLUMNS[1:]:
            exp = d.get(c, 0)
            if c in red.USD_COLS:
                assert row[c] == pytest.approx(exp, rel=1e-9, abs=1e-6), (c, row['ts'])
            else:
                assert row[c] == exp, (c, row['ts'])


def csv_spot(ts, price, qty, maker, unit_mult=1):
    return ''.join(f'{i},{float(p)!r},{float(q)!r},{i},{i},{int(t) * unit_mult},{"True" if m else "False"},True\n'
                   for i, (t, p, q, m) in enumerate(zip(ts, price, qty, maker), 100))


def csv_um(ts, price, qty, maker, header=True):
    h = 'agg_trade_id,price,quantity,first_trade_id,last_trade_id,transact_time,is_buyer_maker\n' if header else ''
    return h + ''.join(f'{i},{float(p)!r},{float(q)!r},{i},{i},{int(t)},{"true" if m else "false"}\n'
                       for i, (t, p, q, m) in enumerate(zip(ts, price, qty, maker), 100))


def test_edges_and_columns():
    assert red.EDGES[0] == 1000.0 and red.EDGES[23] == pytest.approx(20_000_000.0)
    assert len(red.AGG_COLUMNS) == 1 + 4 + 96 + 8
    assert red.AGG_COLUMNS[5] == 'nb_ge_0' and red.AGG_COLUMNS[5 + 24] == 'ns_ge_0' and red.AGG_COLUMNS[-1] == 'sw_s_2m'


def test_unit_and_header_detection():
    assert red.detect_unit(1.7e12) == 'ms' and red.detect_unit(1.7e15) == 'us'
    assert list(red.to_ms([1_735_689_600_123_456])) == [1_735_689_600_123]
    assert list(red.to_ms([1_709_337_600_000])) == [1_709_337_600_000]
    assert red.has_header(b'agg_trade_id,price') and not red.has_header(b'100,40000.1,2')
    assert not red.has_header(b'2020-09-01 00:05:00,BTCUSDT') and red.has_header(b'create_time,symbol')


def test_reduce_arrays_against_brute_force():
    t = make_trades()
    df = red.reduce_arrays(*t)
    check_frame(df, brute(*t))
    # the planted bursts: five 120k buys in one second = 600k (>=250k, >=500k, not 1m), three 400k sells = 1.2M (>=1m, <2m)
    assert df['sw_b_500k'].sum() >= 1 and df['sw_s_1m'].sum() >= 1
    r = df.set_index('ts')
    m3 = T0 + 7 * MIN + 3 * MIN
    assert r.loc[m3, 'sw_b_250k'] >= 1 and r.loc[m3, 'sw_b_500k'] >= 1


def test_edge_counting_exact_boundaries():
    # notional exactly E_k counts for k (>=), just below does not; side from is_buyer_maker (false = buy)
    ts = np.array([T0, T0, T0, T0], dtype=np.int64)
    price = np.array([1000.0, 999.99, 20_000_000.0, 5000.0])
    qty = np.array([1.0, 1.0, 1.0, 1.0])
    maker = np.array([False, False, True, True])
    r = red.reduce_arrays(ts, price, qty, maker).iloc[0]
    assert r['n_buy'] == 2 and r['n_sell'] == 2
    assert r['nb_ge_0'] == 1 and r['nb_ge_1'] == 0          # 1000 counts, 999.99 does not
    assert r['ns_ge_0'] == 2 and r['ns_ge_23'] == 1          # 5000 and 20M >= 1000; only 20M >= E_23
    assert r['us_ge_23'] == pytest.approx(20_000_000.0)
    assert r['usd_buy'] == pytest.approx(1999.99)


def test_streaming_blocks_merge_partial_minutes_and_seconds():
    t = make_trades(seed=3)
    ref = red.reduce_arrays(*t)
    for cut in (7, 333, 1500):
        rd = red.AggReducer()
        idx = np.arange(len(t[0]))
        for chunk in np.array_split(idx, max(2, len(idx) // cut)):
            rd.feed(t[0][chunk], t[1][chunk], t[2][chunk], t[3][chunk])
        got = rd.finish()
        pd.testing.assert_frame_equal(got, ref, check_exact=False, rtol=1e-9)
    assert rd.rows == len(t[0]) and rd.unit == 'ms'


def test_merge_frames_adds_columns():
    t = make_trades(seed=4)
    h = len(t[0]) // 2
    a, b = red.reduce_arrays(*[x[:h] for x in t]), red.reduce_arrays(*[x[h:] for x in t])
    m = red.merge_frames([a, b])
    assert m['n_buy'].sum() == (~t[3]).sum() and m['ts'].is_monotonic_increasing and not m['ts'].duplicated().any()


def test_unit_change_inside_one_file_is_refused():
    rd = red.AggReducer()
    rd.feed([T0, T0 + 1], [1.0, 1.0], [1.0, 1.0], [False, True])
    with pytest.raises(ValueError):
        rd.feed([T0 * 1000 + 5], [1.0], [1.0], [False])


@pytest.mark.parametrize('kind', ['spot_ms', 'spot_us', 'um_header', 'um_noheader'])
def test_read_agg_zip_variants(tmp_path, kind):
    t = make_trades(seed=5, n=2500)
    if kind == 'spot_ms':
        text = csv_spot(*t)
    elif kind == 'spot_us':
        text = csv_spot(*t, unit_mult=1000)
    elif kind == 'um_header':
        text = csv_um(*t, header=True)
    else:
        text = csv_um(*t, header=False)
    p = tmp_path / 'f.zip'
    p.write_bytes(zbytes('x.csv', text))
    rd = fx.read_agg_zip(str(p), block_size=4096)
    assert rd.unit == ('us' if kind == 'spot_us' else 'ms')
    assert rd.rows == len(t[0])
    check_frame(rd.finish(), brute(*t))


# ------------------------------------------------------------------------------------------------------ klines
def synth_market(days=4, seed=0):
    rng = np.random.default_rng(seed)
    n = days * 1440
    ts = T0 - 1440 * MIN + np.arange(n, dtype=np.int64) * MIN            # starts 2024-03-01
    px = 60000 * np.exp(np.cumsum(rng.normal(0, 4e-4, n)))
    v = rng.uniform(50, 150, n)
    tb = v * rng.uniform(0.2, 0.8, n)
    um = pd.DataFrame({'ts': ts, 'o': px, 'h': px, 'l': px, 'c': px, 'v': v, 'tb': tb})
    mark = pd.DataFrame({'ts': ts, 'o': px * (1 + 1e-5), 'h': px, 'l': px, 'c': px})
    return um, mark


def metrics_day(um, mark, day_start, conv, rng, start_off=0, n=288):
    """Rows for one daily file under a convention; returns the CSV text."""
    ug, mg = red.make_um_grid(um), red.make_mark_grid(mark)
    T = day_start + start_off + np.arange(n, dtype=np.int64) * 5 * MIN
    if conv == 'old':
        b, s, px = ug.window_sum(T - 5 * MIN, 5, 'buy'), ug.window_sum(T - 5 * MIN, 5, 'sell'), mg.at(T, 'o')
    elif conv == 'new':
        b, s, px = ug.window_sum(T, 5, 'buy'), ug.window_sum(T, 5, 'sell'), mg.at(T + 5 * MIN, 'o')
    else:   # taker ratio unrelated to price flow, implied price from neither instant (half way)
        b, s, px = rng.uniform(1, 2, n), rng.uniform(1, 2, n), mg.at(T + 2 * 5 * MIN // 4 // MIN * MIN, 'o') * 1.002
    oi = np.full(n, 1000.0)
    lines = ['create_time,symbol,sum_open_interest,sum_open_interest_value,count_toptrader_long_short_ratio,'
             'sum_toptrader_long_short_ratio,count_long_short_ratio,sum_taker_long_short_vol_ratio']
    for i in range(n):
        st = pd.Timestamp(int(T[i]), unit='ms').strftime('%Y-%m-%d %H:%M:%S')
        lines.append(f'{st},BTCUSDT,{oi[i]},{float(oi[i] * px[i])!r},1.1,1.2,1.3,{float(b[i] / s[i])!r}')
    return '\n'.join(lines) + '\n'


def test_metrics_convention_old_new_amb_and_offgrid():
    um, mark = synth_market()
    rng = np.random.default_rng(1)
    ug, mg = red.make_um_grid(um), red.make_mark_grid(mark)
    d1, d2, d3 = T0, T0 + 1440 * MIN, T0 + 2 * 1440 * MIN
    old = red.read_metrics_csv(metrics_day(um, mark, d1, 'old', rng).encode())
    new = red.read_metrics_csv(metrics_day(um, mark, d2, 'new', rng).encode())
    amb = red.read_metrics_csv(metrics_day(um, mark, d3, 'amb', rng).encode())
    lo, ln, la = red.label_day(old, ug, mg), red.label_day(new, ug, mg), red.label_day(amb, ug, mg)
    assert lo['conv'] == 'old' and lo['a'] == 'old' and lo['b'] == 'old'
    assert ln['conv'] == 'new' and ln['a'] == 'new' and ln['b'] == 'new'
    assert la['conv'] == 'amb'
    # a day where the two tests disagree is ambiguous: flow from the new window, price from the old instant
    mixed = new.copy()
    mixed['sum_open_interest_value'] = 1000.0 * mg.at(mixed['stamp'].to_numpy(), 'o')
    assert red.label_day(mixed, ug, mg)['conv'] == 'amb'
    assert (red.snapshot_instant(old['stamp'].to_numpy(), 'old') == old['stamp'].to_numpy()).all()
    assert (red.snapshot_instant(new['stamp'].to_numpy(), 'new') == new['stamp'].to_numpy() + 5 * MIN).all()
    assert (red.snapshot_instant(new['stamp'].to_numpy(), 'amb') == new['stamp'].to_numpy() + 5 * MIN).all()


def test_single_test_decides_when_the_other_has_no_data():
    """Real archive: the taker ratio column is empty on every file 2021-12-31..2022-05-08 (test a cannot run) and some
    days lack mark bars (test b cannot run). The test that ran decides alone, with a stricter margin."""
    um, mark = synth_market()
    rng = np.random.default_rng(3)
    ug, mg = red.make_um_grid(um), red.make_mark_grid(mark)
    old = red.read_metrics_csv(metrics_day(um, mark, T0, 'old', rng).encode())
    new = red.read_metrics_csv(metrics_day(um, mark, T0 + 1440 * MIN, 'new', rng).encode())
    for day, conv in ((old, 'old'), (new, 'new')):
        no_taker = day.assign(sum_taker_long_short_vol_ratio=np.nan)
        lab = red.label_day(no_taker, ug, mg)
        assert lab['conv'] == conv and lab['single_test'] == 'b' and lab['a'] == 'amb'
        no_mark = red.make_mark_grid(mark[(mark['ts'] < day['stamp'].min() - 10 * MIN) | (mark['ts'] > day['stamp'].max() + 10 * MIN)])
        lab = red.label_day(day, ug, no_mark)
        assert lab['conv'] == conv and lab['single_test'] == 'a' and lab['b'] == 'amb'
        both = red.label_day(no_taker, ug, no_mark)
        assert both['conv'] == 'amb' and both['single_test'] is None
    # a single test that is not decisive enough stays ambiguous
    amb = red.read_metrics_csv(metrics_day(um, mark, T0 + 2 * 1440 * MIN, 'amb', rng).encode())
    assert red.label_day(amb.assign(sum_taker_long_short_vol_ratio=np.nan), ug, mg)['conv'] == 'amb'
    # both ran and agree: no single test recorded
    assert red.label_day(old, ug, mg)['single_test'] is None


def test_off_grid_stamp_is_ceiled():
    base = pd.Timestamp('2024-03-02 02:35:02', tz='UTC')
    ms = int(base.value // 10**6)
    assert int(red.ceil_5m([ms])[0]) == int(pd.Timestamp('2024-03-02 02:40:00', tz='UTC').value // 10**6)
    on = int(pd.Timestamp('2024-03-02 02:35:00', tz='UTC').value // 10**6)
    assert int(red.ceil_5m([on])[0]) == on
    raw = (b'create_time,symbol,sum_open_interest,sum_open_interest_value,count_toptrader_long_short_ratio,'
           b'sum_toptrader_long_short_ratio,count_long_short_ratio,sum_taker_long_short_vol_ratio\n'
           b'2024-03-02 02:35:02,BTCUSDT,1,2,3,4,5,6\n')
    df = red.read_metrics_csv(raw)
    assert int(df['stamp_raw'][0]) == ms and int(df['stamp'][0]) == ms + 298_000
    assert list(df.columns) == ['stamp_raw', 'stamp'] + red.METRIC_COLS


def test_duplicate_s_across_two_files_keeps_row_closest_to_mark():
    um, mark = synth_market()
    mg = red.make_mark_grid(mark)
    T = T0 + 600 * MIN
    px = float(mg.at(np.array([T + 5 * MIN]), 'o')[0])

    def day(stamp, oi_value):
        return pd.DataFrame({'stamp': [stamp], **{c: [1.0] for c in red.METRIC_COLS}, }).assign(sum_open_interest_value=oi_value)

    # old file row at T+5m (S = T+5m) and new file row at T (S = T+5m): the new one matches the mark price at S
    good_new = day(T, 1.0 * px)
    bad_old = day(T + 5 * MIN, 1.0 * px * 1.01)
    t = red.build_metrics_table([('A-2024-03-01.zip', bad_old, 'old'), ('A-2024-03-02.zip', good_new, 'new')], mg)
    assert len(t) == 1 and t['file'][0] == 'A-2024-03-02.zip' and t['conv'][0] == 'new' and int(t['S'][0]) == T + 5 * MIN
    # and the reverse way round: the old row is the one that fits
    good_old = day(T + 5 * MIN, 1.0 * px)
    bad_new = day(T, 1.0 * px * 0.99)
    t = red.build_metrics_table([('A-2024-03-01.zip', good_old, 'old'), ('A-2024-03-02.zip', bad_new, 'new')], mg)
    assert len(t) == 1 and t['file'][0] == 'A-2024-03-01.zip'
    assert list(t.columns) == ['S', 'stamp', 'conv'] + red.METRIC_COLS + ['file']


def test_amb_report_years():
    labels = {f'BTCUSDT-metrics-2021-01-{d:02d}.zip': {'conv': 'old'} for d in range(1, 11)}
    labels['BTCUSDT-metrics-2021-01-11.zip'] = {'conv': 'amb'}
    labels['BTCUSDT-metrics-2025-05-01.zip'] = {'conv': 'new'}
    labels['BTCUSDT-metrics-2026-05-01.zip'] = {'conv': 'amb'}
    r = red.amb_report(labels)
    assert r['A']['days'] == 11 and r['A']['amb'] == 1 and r['B']['days'] == 1 and r['B']['amb'] == 0
    assert r['2026']['amb'] == 1 and r['A']['old'] == 10


# ------------------------------------------------------------------------------------------------------ premium
def synth_premium(shift, n=3000, seed=2):
    rng = np.random.default_rng(seed)
    ts = T0 + np.arange(n, dtype=np.int64) * MIN
    index = 3000 * np.exp(np.cumsum(rng.normal(0, 3e-4, n)))
    x = np.cumsum(rng.normal(0, 4e-4, n)) * 0.2 + rng.normal(0, 3e-4, n)       # (perp - index)/index
    perp = index * (1 + x)
    prem_vals = np.roll(x, -shift) if shift else x                              # premium bar t shows minute t+shift
    perp_df = pd.DataFrame({'ts': ts, 'c': perp})
    idx_df = pd.DataFrame({'ts': ts, 'c': index})
    prem_df = pd.DataFrame({'ts': ts, 'c': prem_vals + rng.normal(0, 1e-5, n)})
    return prem_df, perp_df, idx_df


def test_premium_stamp_same_and_next_fit():
    st = red.premium_stamp_test(*synth_premium(0))
    assert st['resolved'] and st['fits'] == 'same' and st['extra_delay_minutes'] == 0
    st = red.premium_stamp_test(*synth_premium(1))
    assert st['resolved'] and st['fits'] == 'next' and st['extra_delay_minutes'] == 1 and st['corr_next'] > st['corr_same']


def test_premium_stamp_unresolved_on_noise():
    p, q, i = synth_premium(0)
    p['c'] = np.random.default_rng(9).normal(0, 1e-3, len(p))
    st = red.premium_stamp_test(p, q, i)
    assert not st['resolved'] and st['fits'] == 'unresolved'


# ------------------------------------------------------------------------------------------------------ bookDepth
def book_csv(start_s, n=6, spacing_s=30, jitter=False):
    rows = ['timestamp,percentage,depth,notional']
    for i in range(n):
        s = start_s + i * spacing_s + (1 if (jitter and i == 2) else 0)
        st = pd.Timestamp(int(s), unit='s').strftime('%Y-%m-%d %H:%M:%S')
        for pct in (-5, -4, -3, -2, -1, 1, 2, 3, 4, 5):
            rows.append(f'{st},{pct},{abs(pct) * 10},{(abs(pct) * 1000 + i) * (1 if pct < 0 else 2)}')
    return ('\n'.join(rows) + '\n').encode()


def test_bookdepth_reshape_and_spacing_shift():
    s0 = int(pd.Timestamp('2023-01-01 00:00:08', tz='UTC').timestamp())
    df, sp = red.bookdepth_reshape(book_csv(s0))
    assert sp == 30_000
    assert list(df.columns) == ['ts', 'bid_1pct', 'ask_1pct'] and len(df) == 6
    assert df['ts'].iloc[0] == s0 * 1000 + 30_000          # shifted LATER by one spacing, never early
    assert df['bid_1pct'].iloc[0] == 1000 and df['ask_1pct'].iloc[0] == 2000 and df['bid_1pct'].iloc[3] == 1003
    assert df['ts'].dtype == np.int64
    df2, sp2 = red.bookdepth_reshape(book_csv(s0, jitter=True))
    assert sp2 == 30_000 and (df2['ts'] > (np.array([s0 + i * 30 for i in range(6)]) * 1000)).all()


# ------------------------------------------------------------------------------------------------------ fake archive
class FakeArchive:
    def __init__(self):
        self.files = {}
        self.fetched = []

    def add(self, key, data):
        self.files[key] = data

    def list_prefix(self, prefix):
        return [{'key': k, 'size': len(v), 'etag': hashlib.md5(v).hexdigest(), 'last_modified': '2026-03-18T12:30:27.000Z'}
                for k, v in sorted(self.files.items()) if k.startswith(prefix)]

    def fetch_zip(self, key, size, dest):
        self.fetched.append(key)
        with open(dest, 'wb') as f:
            f.write(self.files[key])
        return hashlib.sha256(self.files[key]).hexdigest()


def kl_text(df, cols, header=False):
    lines = []
    for r in df.itertuples(index=False):
        d = r._asdict()
        vals = [int(d['ts']), d['o'], d['h'], d['l'], d['c']]
        if 'v' in cols:
            vals += [d['v'], int(d['ts']) + 59999, 1, 10, d['tb'], 1, 0]
        else:
            vals += [0, int(d['ts']) + 59999, 0, 0, 0, 0, 0]
        lines.append(','.join(repr(x) if isinstance(x, float) else str(x) for x in vals))
    h = 'open_time,open,high,low,close,volume,close_time,quote_volume,count,taker_buy_volume,taker_buy_quote_volume,ignore\n'
    return (h if header else '') + '\n'.join(lines) + '\n'


def build_archive(fake_days=(('2024-03-02', 'old'), ('2024-03-03', 'old'), ('2024-03-04', 'new')), amb_day=None):
    um, mark = synth_market(days=5, seed=0)       # 2024-03-01 .. 2024-03-05
    rng = np.random.default_rng(1)
    pr, perp, idx = synth_premium(0, n=len(um), seed=2)
    perp = um.copy()
    idx = um[['ts']].copy()
    x = pr['c'].to_numpy()
    idx['c'] = um['c'].to_numpy() / (1 + x)           # so (perp - index)/index == x
    pr = pr.assign(ts=um['ts'].to_numpy())
    idx['o'] = idx['h'] = idx['l'] = idx['c']
    pr['o'] = pr['h'] = pr['l'] = pr['c']
    a = FakeArchive()
    S = 'BTCUSDT'
    a.add(f'data/futures/um/monthly/klines/{S}/1m/{S}-1m-2024-03.zip', zbytes('k.csv', kl_text(um, ('v',), header=True)))
    a.add(f'data/futures/um/monthly/markPriceKlines/{S}/1m/{S}-1m-2024-03.zip', zbytes('k.csv', kl_text(mark, ())))
    a.add(f'data/futures/um/monthly/indexPriceKlines/{S}/1m/{S}-1m-2024-03.zip', zbytes('k.csv', kl_text(idx, ())))
    a.add(f'data/futures/um/monthly/premiumIndexKlines/{S}/1m/{S}-1m-2024-03.zip', zbytes('k.csv', kl_text(pr, ())))
    # a current-month style daily-only file set for premium in another month must also be used
    a.add(f'data/futures/um/monthly/fundingRate/{S}/{S}-fundingRate-2024-03.zip',
          zbytes('f.csv', 'calc_time,funding_interval_hours,last_funding_rate\n1709366400000,8,0.0001\n1709395200000,8,0.00011\n'))
    for day, conv in fake_days:
        ds = int(pd.Timestamp(day, tz='UTC').value // 10**6)
        c = 'amb' if day == amb_day else conv
        a.add(f'data/futures/um/daily/metrics/{S}/{S}-metrics-{day}.zip', zbytes('m.csv', metrics_day(um, mark, ds, c, rng)))
    for day in ('2022-12-31', '2023-01-01'):
        s0 = int(pd.Timestamp(day + ' 00:00:08', tz='UTC').timestamp())
        a.add(f'data/futures/um/daily/bookDepth/{S}/{S}-bookDepth-{day}.zip', zbytes('b.csv', book_csv(s0).decode()))
    return a, um


@pytest.fixture
def patched(monkeypatch):
    def install(a):
        monkeypatch.setattr(fx, 'list_prefix', a.list_prefix)
        monkeypatch.setattr(fx, 'fetch_zip', a.fetch_zip)
        return a
    return install


def read_gz(path):
    return pd.read_csv(path)


def test_small_end_to_end_contract_files(tmp_path, patched):
    a, um = build_archive()
    patched(a)
    out = tmp_path / 'BTC'
    # A days are all 2024, so the three synthetic days are fine only if none is ambiguous
    rep = fx.small('BTC', str(out))
    for f in ('metrics.csv.gz', 'premium_1m.csv.gz', 'mark_1m.csv.gz', 'index_1m.csv.gz', 'um_1m.csv.gz', 'funding.csv.gz',
              'bookdepth_1pct.csv.gz', 'premium_stamp.json', 'manifest.json'):
        assert (out / f).exists(), f
    m = read_gz(out / 'metrics.csv.gz')
    assert list(m.columns) == ['S', 'stamp', 'conv'] + red.METRIC_COLS + ['file']
    assert m['S'].is_monotonic_increasing and not m['S'].duplicated().any()
    assert set(m['conv']) == {'old', 'new'} and (m.loc[m.conv == 'new', 'S'] - m.loc[m.conv == 'new', 'stamp'] == 5 * MIN).all()
    assert (m.loc[m.conv == 'old', 'S'] == m.loc[m.conv == 'old', 'stamp']).all()
    u = read_gz(out / 'um_1m.csv.gz')
    assert list(u.columns) == ['ts', 'o', 'h', 'l', 'c', 'v', 'tb'] and len(u) == len(um)
    assert list(read_gz(out / 'premium_1m.csv.gz').columns) == ['ts', 'o', 'h', 'l', 'c']
    f = read_gz(out / 'funding.csv.gz')
    assert list(f.columns) == ['calc_time', 'funding_interval_hours', 'last_funding_rate'] and len(f) == 2
    b = read_gz(out / 'bookdepth_1pct.csv.gz')
    assert list(b.columns) == ['ts', 'bid_1pct', 'ask_1pct'] and len(b) == 6          # 2022-12-31 is before 2023-01-01
    st = json.load(open(out / 'premium_stamp.json'))
    assert st['resolved'] and st['fits'] == 'same'
    man = json.load(open(out / 'manifest.json'))
    keys = {e['key'] for e in man['entries']}
    assert not any('2022-12-31' in k for k in keys) and any('metrics-2024-03-04' in k for k in keys)
    e0 = man['entries'][0]
    assert {'key', 'bytes', 'etag', 'last_modified', 'sha256', 'downloaded_at', 'rows'} <= set(e0) and len(e0['sha256']) == 64
    assert man['datasets']['bookdepth_1pct']['spacing_ms_median'] == 30_000
    assert man['datasets']['metrics']['first'] == int(m['S'].iloc[0])
    assert rep['metrics']['A']['days'] == 3 and rep['metrics']['A']['amb'] == 0
    # no zip was kept: only contract files are in the folder
    assert not [p for p in os.listdir(out) if p.endswith('.zip')]


def test_small_fails_loudly_on_ambiguous_days(tmp_path, patched):
    a, _ = build_archive(amb_day='2024-03-03')
    patched(a)
    with pytest.raises(SystemExit) as ei:
        fx.small('BTC', str(tmp_path / 'BTC'))
    assert 'ambiguous' in str(ei.value)
    assert (tmp_path / 'BTC' / 'metrics.csv.gz').exists()         # written first so the files can be inspected


def test_small_btcdom_only_idx1h(tmp_path, patched):
    a = FakeArchive()
    rows = '\n'.join(f'{1_709_337_600_000 + i * 3_600_000},1,2,0.5,1.5,10,0,0,0,0,0,0' for i in range(5)) + '\n'
    a.add('data/futures/um/monthly/klines/BTCDOMUSDT/1h/BTCDOMUSDT-1h-2024-03.zip', zbytes('k.csv', rows))
    patched(a)
    out = tmp_path / 'BTCDOM'
    fx.small('BTCDOM', str(out))
    assert sorted(os.listdir(out)) == ['idx1h.csv.gz', 'manifest.json']
    d = read_gz(out / 'idx1h.csv.gz')
    assert list(d.columns) == ['ts', 'o', 'h', 'l', 'c', 'v'] and len(d) == 5


def test_never_doge_and_unknown_assets():
    for bad in ('DOGE', 'doge', 'DOGEUSDT', 'ADA'):
        with pytest.raises(SystemExit):
            fx.symbol_of(bad)
    assert fx.symbol_of('xrp') == 'XRPUSDT'


# ------------------------------------------------------------------------------------------------------ agg driver
def agg_archive():
    a = FakeArchive()
    S = 'BTCUSDT'
    t1 = make_trades(seed=11, n=800, start=T0)
    t2 = make_trades(seed=12, n=800, start=T0 + 40 * 86_400_000)             # 2024-04-11
    t3 = make_trades(seed=13, n=800, start=T0 + 41 * 86_400_000)             # 2024-04-12
    a.add(f'data/spot/monthly/aggTrades/{S}/{S}-aggTrades-2024-03.zip', zbytes('a.csv', csv_spot(*t1)))
    a.add(f'data/spot/daily/aggTrades/{S}/{S}-aggTrades-2024-04-11.zip', zbytes('a.csv', csv_spot(*t2)))
    a.add(f'data/spot/daily/aggTrades/{S}/{S}-aggTrades-2024-04-12.zip', zbytes('a.csv', csv_spot(*t3)))
    return a, (t1, t2, t3)


def test_agg_months_daily_fallback_put_and_resume(tmp_path, patched):
    a, (t1, t2, t3) = agg_archive()
    patched(a)
    drive = tmp_path / 'drive'
    drive.mkdir()
    put = f'cp "$OUTSIDE_FILE" {drive}/ && echo "$OUTSIDE_REL" >> {tmp_path}/put.log'
    out = tmp_path / 'out'
    done = fx.agg('BTC', 'spot', 2024, str(out), None, put, None)
    assert done == ['2024-03', '2024-04']                              # 01, 02 and 05..12 have no file: skipped
    assert sorted(os.listdir(drive)) == ['2024-03.parquet', '2024-04.parquet']
    assert not list((out / 'agg_spot').glob('*.parquet'))              # local copies deleted after upload
    assert open(tmp_path / 'put.log').read().split() == ['agg_spot/2024-03.parquet', 'agg_spot/2024-04.parquet']
    m = pd.read_parquet(drive / '2024-03.parquet')
    check_frame(m, brute(*t1))
    apr = pd.read_parquet(drive / '2024-04.parquet')                    # two daily zips merged into one month
    assert apr['n_buy'].sum() + apr['n_sell'].sum() == 1616
    import pyarrow.parquet as pq
    meta = json.loads(pq.read_schema(drive / '2024-03.parquet').metadata[b'outside_source'])
    assert meta['market'] == 'spot' and meta['unit'] == 'ms' and meta['files'][0]['rows'] == len(t1[0]) and len(meta['files'][0]['sha256']) == 64
    # resume: a file list from rclone lsf -R skips the month that is already there
    skip = tmp_path / 'skip.txt'
    skip.write_text('agg_spot/2024-03.parquet\nagg_perp/2024-04.parquet\n')
    a.fetched.clear()
    done = fx.agg('BTC', 'spot', 2024, str(out), None, None, str(skip))
    assert done == ['2024-04'] and all('2024-04' in k for k in a.fetched)       # perp's file does not skip spot
    a.fetched.clear()
    assert fx.agg('BTC', 'spot', 2024, str(out), ['03'], None, str(skip)) == [] and a.fetched == []


def test_agg_monthly_file_missing_a_day_is_filled_from_its_daily_file(tmp_path, patched):
    """Seen on the real archive: BTCUSDT perp monthly 2022-08/09/11 zips miss whole days that the daily zips hold."""
    a = FakeArchive()
    S = 'BTCUSDT'
    t1 = make_trades(seed=21, n=600, start=T0)                               # 2024-03-02, in the monthly zip
    t4 = make_trades(seed=24, n=500, start=T0 + 3 * 86_400_000)              # 2024-03-05, only in its daily zip
    a.add(f'data/futures/um/monthly/aggTrades/{S}/{S}-aggTrades-2024-03.zip', zbytes('a.csv', csv_um(*t1)))
    a.add(f'data/futures/um/daily/aggTrades/{S}/{S}-aggTrades-2024-03-02.zip', zbytes('a.csv', csv_um(*t1)))
    a.add(f'data/futures/um/daily/aggTrades/{S}/{S}-aggTrades-2024-03-05.zip', zbytes('a.csv', csv_um(*t4, header=False)))
    patched(a)
    drive = tmp_path / 'drive'
    drive.mkdir()
    done = fx.agg('BTC', 'perp', 2024, str(tmp_path / 'out'), ['03'], f'cp "$OUTSIDE_FILE" {drive}/', None)
    assert done == ['2024-03']
    m = pd.read_parquet(drive / '2024-03.parquet')
    ref = brute(*t1)
    ref.update(brute(*t4))
    check_frame(m, ref)                                                       # both days, exactly
    import pyarrow.parquet as pq
    meta = json.loads(pq.read_schema(drive / '2024-03.parquet').metadata[b'outside_source'])
    fills = {f['day']: f for f in meta['gap_fill']}
    assert fills['2024-03-05']['used'] and fills['2024-03-05']['monthly_minutes'] == 0
    assert not fills['2024-03-02']['used'] and fills['2024-03-02']['daily_minutes'] == fills['2024-03-02']['monthly_minutes']
    assert meta['trades'] == len(t1[0]) + len(t4[0])                         # the unused daily copy is not counted twice
    assert sum(1 for f in meta['files'] if f.get('gap_fill_day')) == 2


def test_agg_daily_only_month_is_rebuilt_despite_drive_copy(tmp_path, patched):
    a, _ = agg_archive()
    patched(a)
    skip = tmp_path / 'skip.txt'
    skip.write_text('agg_spot/2024-03.parquet\nagg_spot/2024-04.parquet\n')
    done = fx.agg('BTC', 'spot', 2024, str(tmp_path / 'out'), None, None, str(skip))
    assert done == ['2024-04']                                          # 03 (monthly zip) skipped, 04 (daily only) rebuilt


def test_agg_spot_2025_microseconds_end_to_end(tmp_path, patched):
    a = FakeArchive()
    S = 'ETHUSDT'
    t = make_trades(seed=21, n=600, start=T0 + 365 * 86_400_000)
    a.add(f'data/spot/monthly/aggTrades/{S}/{S}-aggTrades-2025-03.zip', zbytes('a.csv', csv_spot(*t, unit_mult=1000)))
    patched(a)
    drive = tmp_path / 'd'
    drive.mkdir()
    fx.agg('ETH', 'spot', 2025, str(tmp_path / 'o'), ['03'], f'cp "$OUTSIDE_FILE" {drive}/', None)
    df = pd.read_parquet(drive / '2025-03.parquet')
    check_frame(df, brute(*t))
    assert df['ts'].iloc[0] < 2e12            # milliseconds, not microseconds


def test_agg_put_failure_is_loud(tmp_path, patched):
    a, _ = agg_archive()
    patched(a)
    with pytest.raises(RuntimeError):
        fx.agg('BTC', 'spot', 2024, str(tmp_path / 'o'), ['03'], 'exit 7', None)


def test_agg_refuses_btcdom_and_doge(tmp_path):
    with pytest.raises(SystemExit):
        fx.agg('BTCDOM', 'spot', 2024, str(tmp_path))
    with pytest.raises(SystemExit):
        fx.agg('DOGE', 'perp', 2024, str(tmp_path))


def test_plan_months_prefers_monthly():
    mo = [{'key': 'x/A-aggTrades-2024-03.zip'}]
    da = [{'key': 'x/A-aggTrades-2024-03-05.zip'}, {'key': 'x/A-aggTrades-2024-04-01.zip'}]
    p = fx.plan_months(mo, da)
    assert [fx.date_of(e['key']) for e in p] == ['2024-03', '2024-04-01']


def test_preflight_aggregates_only(tmp_path, patched):
    a, _ = build_archive()
    a2, _ = agg_archive()
    a.files.update(a2.files)
    patched(a)
    out = tmp_path / 'pf' / 'preflight.json'
    res = fx.preflight(str(out))
    j = json.load(open(out))
    assert j['assets']['BTC']['metrics_daily']['files'] == 3 and j['assets']['BTC']['metrics_daily']['first'] == '2024-03-02'
    assert j['assets']['BTC']['aggTrades']['spot']['per_year']['2024']['files'] == 3
    assert j['assets']['BTC']['aggTrades']['perp']['summary']['files'] == 0
    assert set(j['assets']) == {'BTC', 'ETH', 'SOL', 'XRP', 'BTCDOM'}
    txt = out.read_text()
    assert 'DOGE' not in txt and '"o"' not in txt


def test_zip_with_a_duplicate_member_under_an_internal_path(tmp_path):
    """Real archive: spot aggTrades 2021-12 zips hold the CSV twice (root and fsx-data/collector_data/...)."""
    ts, price, qty, maker = make_trades(seed=31, n=300)
    text = csv_spot(ts, price, qty, maker)
    p = tmp_path / 'f.zip'
    with zipfile.ZipFile(p, 'w') as z:
        z.writestr('XRPUSDT-aggTrades-2021-12.csv', text)
        z.writestr('fsx-data/collector_data/data/spot/monthly/aggTrades/XRPUSDT/XRPUSDT-aggTrades-2021-12.csv', text)
    check_frame(fx.read_agg_zip(str(p)).finish(), brute(ts, price, qty, maker))
    q = tmp_path / 'g.zip'
    with zipfile.ZipFile(q, 'w') as z:
        z.writestr('a.csv', text)
        z.writestr('b.csv', text + '1,1,1,1,1,1,True,True\n')
    with pytest.raises(RuntimeError):
        fx.read_agg_zip(str(q))
