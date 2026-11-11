"""Binance minutes: kline rows to the reader's rows and the engine's frame, the closed-minute rule, paging, limits."""
import json

import numpy as np
import pytest

from conftest import FakeBinance, FetchError, T0, kline, walk
from heat_reader import MIN
from heat_reader.binance import COLS, Binance, RateLimited, parse_klines
from heat_reader.engine import frame


def source(fake, **kw):
    return Binance('https://data-api.binance.vision/api/v3', get=fake, now_ms=fake.clock, sleep=lambda s: None, pace=0, **kw)


def test_kline_rows_become_the_columns_the_engine_takes():
    rows = walk(5, T0 + 4 * MIN)
    raw = [kline(r) for r in rows]
    got = parse_klines(raw, closed_before_ms=T0 + 10 * MIN)
    assert got.shape == (5, 7) and COLS == ('ts', 'o', 'h', 'l', 'c', 'v', 'tb')
    assert np.array_equal(got[:, 0], rows[:, 0])
    assert np.allclose(got[:, 1:], rows[:, 1:], rtol=0, atol=1e-8)
    assert got[0, 6] == pytest.approx(float(raw[0][9]))            # tb is the taker buy BASE volume (field 9), not the quote volume
    df = frame(got)
    assert list(df.columns) == ['ts', 'o', 'h', 'l', 'c', 'v', 'tb']
    assert str(df['ts'].dtype) == 'int64' and all(str(df[c].dtype) == 'float64' for c in 'ohlcv') and str(df['tb'].dtype) == 'float64'
    assert df['ts'].tolist() == [T0 + i * MIN for i in range(5)]


def test_only_closed_minutes_are_kept():
    rows = walk(3, T0 + 2 * MIN)
    raw = [kline(r) for r in rows]
    # Binance's clock is 30 s into the third minute: its kline is in the answer but still open
    assert parse_klines(raw, closed_before_ms=T0 + 2 * MIN + 30_000)[:, 0].tolist() == [T0, T0 + MIN]
    # a minute counts only once its closeTime (open + 59,999 ms) is BEFORE the clock
    assert len(parse_klines(raw, closed_before_ms=T0 + 3 * MIN - 1)) == 2
    assert len(parse_klines(raw, closed_before_ms=T0 + 3 * MIN)) == 3


def test_broken_rows_are_left_out_not_guessed():
    rows = walk(6, T0 + 5 * MIN)
    raw = [kline(r) for r in rows]
    raw[1][4] = 'not a number'            # close does not parse
    raw[2] = raw[2][:5]                   # a short row
    raw[3][0] = raw[3][0] + 1             # not a whole minute
    raw[4][2] = 'NaN'                     # not finite
    got = parse_klines(raw + [raw[0]], closed_before_ms=T0 + 60 * MIN)      # and a row that goes back in time
    assert got[:, 0].tolist() == [T0, T0 + 5 * MIN]
    with pytest.raises(FetchError):
        parse_klines({'code': -1121, 'msg': 'Invalid symbol.'}, T0)
    assert parse_klines([], T0).shape == (0, 7)


def test_clock_offset_decides_which_minute_is_closed():
    data = {'BTC': walk(10, T0 + 9 * MIN)}
    # Binance's clock: 2 s after the minute T0+5 closed. This machine's clock runs 40 s behind it.
    fake = FakeBinance(data, now=T0 + 6 * MIN + 2000, skew_ms=40_000)
    b = source(fake)
    assert b.offset_ms is None and b.last_close() == T0 + 5 * MIN         # blind: the local clock, with a wider margin
    assert b.sync_clock() and b.offset_ms == pytest.approx(40_000)
    assert b.last_close() == T0 + 6 * MIN
    pages = list(b.minutes('BTC', T0))
    got = np.concatenate(pages)
    assert got[-1, 0] == T0 + 5 * MIN                                     # the open minute T0+6 was served and dropped
    assert json.loads(fake(fake.klines()[-1], 1)[2])[-1][0] == T0 + 6 * MIN
    # a failed clock request keeps the last measured offset
    fake.fail.append(FetchError('network: down'))
    assert not b.sync_clock(force=True) and b.offset_ms == pytest.approx(40_000)


def test_paging_asks_only_for_what_is_missing():
    data = {'ETH': walk(2500, T0 + 2499 * MIN)}
    fake = FakeBinance(data, now=T0 + 2500 * MIN + 3000)
    b = source(fake)
    b.sync_clock()
    pages = list(b.minutes('ETH', T0))
    assert [len(p) for p in pages] == [1000, 1000, 500]
    urls = fake.klines()
    assert len(urls) == 3 and all('symbol=ETHUSDT&interval=1m&limit=1000' in u for u in urls)
    assert [int(u.split('startTime=')[1]) for u in urls] == [T0, T0 + 1000 * MIN, T0 + 2000 * MIN]
    assert np.array_equal(np.concatenate(pages)[:, 0], data['ETH'][:, 0])
    # an end bound (the parity replay): nothing at or after it, and no request once the range is done
    fake.urls.clear()
    part = np.concatenate(list(b.minutes('ETH', T0 + 100 * MIN, until_ms=T0 + 1300 * MIN)))
    assert part[0, 0] == T0 + 100 * MIN and part[-1, 0] == T0 + 1299 * MIN and len(part) == 1200
    assert f'endTime={T0 + 1300 * MIN - 1}' in fake.klines()[0]
    assert list(b.minutes('ETH', T0 + 1300 * MIN, until_ms=T0 + 1300 * MIN)) == []


def test_rate_limit_and_errors():
    data = {'SOL': walk(20, T0 + 19 * MIN)}
    fake = FakeBinance(data, now=T0 + 20 * MIN + 3000)
    b = source(fake)
    fake.fail.append((429, {'retry-after': '7'}))
    with pytest.raises(RateLimited) as e:
        list(b.minutes('SOL', T0))
    assert e.value.retry_after == 7.0 and len(fake.klines()) == 1          # a rate limit is not retried at once
    fake.fail.append((418, {}))
    with pytest.raises(RateLimited) as e:
        list(b.minutes('SOL', T0))
    assert e.value.retry_after >= 1.0
    # one network failure and one bad status are retried and the third try answers
    fake.urls.clear()
    fake.fail += [FetchError('network: reset'), (502, {})]
    assert len(np.concatenate(list(b.minutes('SOL', T0)))) == 20 and len(fake.klines()) == 3
    # three failures in a row give up with the last reason
    fake.fail += [(500, {}), (500, {}), (503, {})]
    with pytest.raises(FetchError, match='HTTP 503'):
        list(b.minutes('SOL', T0))
    # an unknown coin (HTTP 400) is an error, not an empty answer
    with pytest.raises(FetchError):
        list(b.minutes('NOPE', T0))


def test_http_get_turns_a_cut_off_body_into_fetch_error(monkeypatch):
    import http.client
    import pytest
    from heat_reader import binance

    class Cut:
        def open(self, req, timeout=None):
            raise http.client.IncompleteRead(b'{"serverTi')

    monkeypatch.setattr(binance, '_OPENER', Cut())
    with pytest.raises(binance.FetchError):
        binance.http_get('https://example.invalid/api/v3/time', 5)
