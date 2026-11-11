"""The minute cache on disk: append, reload, a torn tail, a corrupt file, trimming, and no second download."""
import os

import numpy as np
import pytest

from conftest import FakeBinance, FetchError, T0, walk
from heat_reader import MIN
from heat_reader import cache as mc
from heat_reader.binance import Binance


def source(fake):
    b = Binance('https://data-api.binance.vision/api/v3', get=fake, now_ms=fake.clock, sleep=lambda s: None, pace=0)
    b.sync_clock()
    return b


def test_append_and_reload(tmp_path):
    rows = walk(50, T0 + 49 * MIN)
    c = mc.MinuteCache(str(tmp_path / 'm' / 'BTC.min'))
    assert c.load().shape == (0, 7) and c.asked_from is None and c.last_close() == 0
    c.rewrite(rows[:30], T0)
    c.append(rows[30:42])
    c.append(rows[42:])
    again = mc.MinuteCache(c.path)
    got = again.load()
    assert np.array_equal(got, rows) and again.asked_from == T0 and not again.repaired     # every value comes back bit for bit
    assert again.last_close() == T0 + 50 * MIN
    assert os.path.getsize(c.path) == mc.HEADER + 50 * mc.REC
    assert not [f for f in os.listdir(tmp_path / 'm') if '.tmp.' in f]                   # the rewrite left no temporary file


def test_a_torn_last_record_is_cut_off(tmp_path):
    rows = walk(20, T0 + 19 * MIN)
    c = mc.MinuteCache(str(tmp_path / 'BTC.min'))
    c.rewrite(rows, T0)
    with open(c.path, 'ab') as f:
        f.write(b'\x01' * 23)                           # the process died inside an append
    got = c.load()
    assert c.repaired and np.array_equal(got, rows)
    assert os.path.getsize(c.path) == mc.HEADER + 20 * mc.REC
    c.append(walk(1, T0 + 20 * MIN))                    # and the next append lands on a record boundary
    assert len(mc.MinuteCache(c.path).load()) == 21


@pytest.mark.parametrize('damage', ['magic', 'order', 'short', 'not-minutes', 'header'])
def test_a_corrupt_cache_is_rebuilt(tmp_path, damage):
    data = {'BTC': walk(300, T0 + 299 * MIN)}
    fake = FakeBinance(data, now=T0 + 300 * MIN + 3000)
    c = mc.MinuteCache(str(tmp_path / 'BTC.min'))
    rows, facts = mc.update(c, source(fake), 'BTC', T0 + 100 * MIN)
    assert len(rows) == 200 and facts['fetched'] == 260 and not facts['rebuilt']          # it starts an hour before the window
    raw = bytearray(open(c.path, 'rb').read())
    if damage == 'magic':
        raw[:4] = b'JUNK'
    elif damage == 'order':
        raw[mc.HEADER:mc.HEADER + 8], raw[mc.HEADER + mc.REC:mc.HEADER + mc.REC + 8] = raw[mc.HEADER + mc.REC:mc.HEADER + mc.REC + 8], raw[mc.HEADER:mc.HEADER + 8]
    elif damage == 'short':
        raw = raw[:7]
    elif damage == 'not-minutes':
        raw[mc.HEADER:mc.HEADER + 8] = np.array([T0 + 40 * MIN + 17.0]).tobytes()
    else:
        raw[8:16] = b'\x00' * 8
    open(c.path, 'wb').write(bytes(raw))
    with pytest.raises(mc.CorruptCache):
        mc.MinuteCache(c.path).load()
    fake.urls.clear()
    rows, facts = mc.update(c, source(fake), 'BTC', T0 + 100 * MIN)
    assert 'corrupt cache' in facts['rebuilt'] and facts['fetched'] == 260
    assert np.array_equal(rows[:, 0], data['BTC'][100:, 0]) and np.allclose(rows, data['BTC'][100:], atol=1e-8, rtol=0)
    assert np.array_equal(mc.MinuteCache(c.path).load()[:, 0], data['BTC'][40:, 0])


def test_a_restart_downloads_only_the_new_minutes(tmp_path):
    data = {'BTC': walk(2600, T0 + 2599 * MIN)}
    fake = FakeBinance(data, now=T0 + 2500 * MIN + 3000)
    path = str(tmp_path / 'BTC.min')
    rows, facts = mc.update(mc.MinuteCache(path), source(fake), 'BTC', T0 + 60 * MIN)
    assert facts['fetched'] == 2500 and len(fake.klines()) == 3 and rows[0, 0] == T0 + 60 * MIN and rows[-1, 0] == T0 + 2499 * MIN
    # a new process, two minutes later: one request, two new rows, the file two records longer
    fake.urls.clear()
    fake.now += 2 * MIN
    size = os.path.getsize(path)
    rows, facts = mc.update(mc.MinuteCache(path), source(fake), 'BTC', T0 + 62 * MIN)
    assert facts['fetched'] == 2 and len(fake.klines()) == 1 and f'startTime={T0 + 2500 * MIN}' in fake.klines()[0]
    assert os.path.getsize(path) == size + 2 * mc.REC and not facts['rebuilt']
    assert rows[0, 0] == T0 + 62 * MIN and rows[-1, 0] == T0 + 2501 * MIN
    # nothing new: the answer holds only the open minute, nothing is appended
    rows, facts = mc.update(mc.MinuteCache(path), source(fake), 'BTC', T0 + 62 * MIN)
    assert facts['fetched'] == 0 and os.path.getsize(path) == size + 2 * mc.REC


def test_old_minutes_are_dropped_and_a_longer_window_starts_again(tmp_path):
    data = {'BTC': walk(4000, T0 + 3999 * MIN)}
    fake = FakeBinance(data, now=T0 + 2000 * MIN + 3000)
    path = str(tmp_path / 'BTC.min')
    mc.update(mc.MinuteCache(path), source(fake), 'BTC', T0 + 60 * MIN)
    assert len(mc.MinuteCache(path).load()) == 2000
    # the window has moved on by less than a day of minutes: the file keeps its old rows
    fake.now += 1000 * MIN
    rows, facts = mc.update(mc.MinuteCache(path), source(fake), 'BTC', T0 + 1060 * MIN)
    assert len(rows) == 1940 and len(mc.MinuteCache(path).load()) == 3000 and not facts['rebuilt']
    # more than a day of minutes are now older than the window: the file is rewritten without them
    fake.now += 600 * MIN
    rows, facts = mc.update(mc.MinuteCache(path), source(fake), 'BTC', T0 + 1660 * MIN)
    c = mc.MinuteCache(path)
    assert len(rows) == 1940 and c.load()[0, 0] == T0 + 1600 * MIN and c.asked_from == T0 + 1600 * MIN and not facts['rebuilt']
    # a clock corrected backwards by a minute is inside the slack: no new download
    fake.urls.clear()
    rows, facts = mc.update(mc.MinuteCache(path), source(fake), 'BTC', T0 + 1659 * MIN)
    assert not facts['rebuilt'] and len(fake.klines()) == 1 and facts['fetched'] == 0
    # a window that reaches further back than the cache was ever asked for: started again from there
    rows, facts = mc.update(mc.MinuteCache(path), source(fake), 'BTC', T0 + 500 * MIN)
    assert 'does not reach back' in facts['rebuilt'] and rows[0, 0] == T0 + 500 * MIN and rows[-1, 0] == T0 + 3599 * MIN
    # a cache that ends before the window starts (the reader was off for longer than the window) is started again too
    fake.now = T0 + 3990 * MIN + 3000
    mc.MinuteCache(path).rewrite(data['BTC'][:100], T0)
    rows, facts = mc.update(mc.MinuteCache(path), source(fake), 'BTC', T0 + 3000 * MIN)
    assert 'ends before' in facts['rebuilt'] and rows[0, 0] == T0 + 3000 * MIN and rows[-1, 0] == T0 + 3989 * MIN


def test_a_failed_download_keeps_what_it_has(tmp_path):
    data = {'BTC': walk(2500, T0 + 2499 * MIN)}
    fake = FakeBinance(data, now=T0 + 2500 * MIN + 3000)
    path = str(tmp_path / 'BTC.min')
    b = source(fake)
    calls = {'n': 0}
    real = fake.__call__

    def flaky(url, timeout):
        calls['n'] += '/klines' in url
        if calls['n'] >= 2 and '/klines' in url:        # the first page arrives, every later request fails
            raise FetchError('network: down')
        return real(url, timeout)
    b._get = flaky
    rows, facts = mc.update(mc.MinuteCache(path), b, 'BTC', T0 + 60 * MIN)
    assert isinstance(facts['error'], FetchError) and facts['fetched'] == 1000 and rows[-1, 0] == T0 + 999 * MIN
    assert len(mc.MinuteCache(path).load()) == 1000                         # the page that arrived is on disk
    b._get = fake
    fake.urls.clear()
    rows, facts = mc.update(mc.MinuteCache(path), b, 'BTC', T0 + 60 * MIN)
    assert facts['error'] is None and facts['fetched'] == 1500 and f'startTime={T0 + 1000 * MIN}' in fake.klines()[0]
    assert np.array_equal(rows[:, 0], data['BTC'][60:, 0])
