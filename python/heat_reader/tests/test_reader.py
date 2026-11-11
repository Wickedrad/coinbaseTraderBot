"""One pass end to end with the REAL oracle engine on synthetic minutes, and the loop's rules.

The minutes are a random walk on a price step, several days long, served as canned Binance answers. The coin's meta
is made by the engine itself (the zone edges of that walk), so the real path runs: fetch, cache, frame, grid,
active_keys, join, the calls file. What must fire is asked of the engine directly, without the reader in between.
These tests skip themselves when TA-Lib or the oracle code is not available.
"""
import json
import os

import numpy as np
import pytest

from conftest import FetchError, assert_contract, bot_parse, pack_row, reader_for, settings, write_meta, write_pack
from heat_reader import MIN
from heat_reader import cache as mc
from heat_reader import reader as rd
from heat_reader.pack import base_of


def build(world, tmp_path, coins=('BTC', 'ETH'), end=None, eth_sha=None):
    """A pack whose rows are picked from what the engine fires at `end` (and some that do not fire), the metas in
    both layouts, and the expected calls per coin."""
    end = world.end if end is None else end
    rows, want = [], {}
    for c in coins:
        ev = world.events(c, end)
        assert ev['ts'] == end and ev['closed'] == [1, 5] and ev['no_reading'] == []
        one = sorted(k for k in ev['events'] if k.startswith('1m:'))
        five = sorted(k for k in ev['events'] if k.startswith('5m:'))
        assert len(one) >= 4 and len(five) >= 1, (c, ev['events'])
        fired = set(ev['events'])
        quiet = sorted(f'{b}=very low' for b in world.meta[c]['edges'] if b.startswith('1m:') and f'{b}=very low' not in fired
                       and f'{b}=very high' not in fired)
        sha = f'sha-{c}'
        rows += [pack_row(c, one[0], h=15, rank=1, sha=sha), pack_row(c, one[1], h=15, rank=2, direction=-1, sha=sha),
                 pack_row(c, one[0], h=60, rank=5, sha=sha),
                 pack_row(c, five[0], h=15, rank=3, tf='5m', sha=sha),
                 pack_row(c, quiet[0], h=15, rank=4, aliases=[one[2]], sha=sha),            # fires through its alias only
                 pack_row(c, quiet[1], h=15, rank=6, sha=sha),                              # does not fire
                 pack_row(c, quiet[2].replace('very low', 'very high'), h=60, rank=2, sha=sha),   # does not fire
                 pack_row(c, one[3], h=15, rank=7, live_parity=False, sha=sha)]             # fires in the engine, marked off in the pack
        want[c] = [(15, 1, one[0]), (15, 2, one[1]), (15, 3, five[0]), (15, 4, quiet[0]), (60, 5, one[0])]
    pack = write_pack(tmp_path / 'tables' / 'traded_pack.json', rows, {c: f'sha-{c}' for c in coins})
    write_meta(tmp_path / 'tables', 'BTC', world.meta['BTC'])                               # BTC: its own meta.json
    slim = {c: dict(world.meta[c], table_sha256=eth_sha or world.meta[c]['table_sha256']) for c in coins if c != 'BTC'}
    json.dump(slim, open(tmp_path / 'tables' / 'live_meta.json', 'w'))                      # the others: one live_meta.json
    return pack, want


def test_one_pass_end_to_end(world, oracle_path, tmp_path):
    pack, want = build(world, tmp_path)
    s = settings(tmp_path, pack, tmp_path / 'tables', oracle_path, window=world.window)
    fake = world.fake()
    r = reader_for(s, fake)
    obj = r.pass_once()

    assert_contract(obj)
    assert json.load(open(s.calls_file)) == obj and open(s.calls_file).read().endswith('}\n')
    assert obj['source'] == 'oracle-heat' and obj['run'] == '43030435253' and obj['writtenAt'] == world.end + 3000
    assert list(obj['coins']) == ['BTC', 'ETH']
    for c in ('BTC', 'ETH'):
        coin = obj['coins'][c]
        assert coin['ok'] is True and 'why' not in coin and coin['tableSha'] == f'sha-{c}'
        assert coin['asOf'] == world.end                                    # the close of the last closed minute
        assert [(x['h'], x['rank'], x['key']) for x in coin['calls']] == want[c]
        assert all(x['barClose'] == world.end for x in coin['calls'])       # every fired row: the bar that closed now
        five = next(x for x in coin['calls'] if x['rank'] == 3)
        assert five['tf'] == 5 and five['share'] == 0.5325 and five['odds'] == 3.25 and five['heat'] == 94.5 and five['of'] == 40
        assert next(x for x in coin['calls'] if x['rank'] == 2)['dir'] == -1
        alias = next(x for x in coin['calls'] if x['rank'] == 4)
        assert alias['aliases'] and alias['aliases'][0] in world.events(c, world.end)['events'] and alias['key'] not in world.events(c, world.end)['events']
        # the cache holds the minutes Binance served, bit for bit, up to the last closed one and not the open one
        cached = mc.MinuteCache(os.path.join(s.reader_dir, 'minutes', f'{c}.min')).load()
        src = world.data[c]
        assert cached[-1, 0] == world.end - MIN and np.array_equal(cached, src[(src[:, 0] >= cached[0, 0]) & (src[:, 0] < world.end)])
        need = r.engine.need_minutes(world.window, [1, 5])
        assert need == (world.window + r.engine.stale_back + 2) * 5 + 1440 and len(cached) == need + 60
    status = json.load(open(os.path.join(s.reader_dir, 'status.json')))
    assert status['counts'] == {'passes': 1, 'goodPasses': 1, 'networkErrors': 0, 'engineErrors': 0, 'passErrors': 0, 'cacheRebuilds': 0, 'rateLimits': 0}
    assert status['coins']['BTC']['fired'] == 5 and status['coins']['BTC']['keys'] == sorted({k for _, _, k in want['BTC']})
    assert status['coins']['BTC']['closed'] == [1, 5] and status['coins']['BTC']['minutes'] >= world.window * 5
    got = bot_parse(open(s.calls_file).read())
    if got is not None:                                                     # the bot's own reader takes the file as it is
        assert got == {'run': '43030435253', 'coins': {c: {'ok': True, 'calls': 5, 'asOf': world.end} for c in ('BTC', 'ETH')}}


def test_the_next_minute_and_a_restart_ask_for_one_minute_only(world, oracle_path, tmp_path):
    pack, _ = build(world, tmp_path)
    s = settings(tmp_path, pack, tmp_path / 'tables', oracle_path, window=world.window)
    fake = world.fake()
    r = reader_for(s, fake)
    r.pass_once()
    first = len(fake.klines())
    assert first == 2 * 8                                                    # the whole window once: 8 pages a coin
    size = os.path.getsize(os.path.join(s.reader_dir, 'minutes', 'BTC.min'))
    for step, reader in ((1, r), (2, reader_for(s, fake)), (3, reader_for(s, fake))):      # the same process, then two restarts
        fake.urls.clear()
        fake.now += MIN
        obj = reader.pass_once()
        end = world.end + step * MIN
        assert [u.split('symbol=')[1].split('&')[0] for u in fake.klines()] == ['BTCUSDT', 'ETHUSDT']
        assert all(f'startTime={end - MIN}' in u for u in fake.klines())
        for c in ('BTC', 'ETH'):
            direct = world.events(c, end)
            coin = obj['coins'][c]
            assert coin['ok'] and coin['asOf'] == end == direct['ts']
            fired = set(direct['events'])
            table = reader.tables.coins[c]
            expect = sorted({x['key'] for x in table.rows if x.get('live_parity') is not False
                             and (x['key'] in fired or any(a in fired for a in x['aliases']))})
            assert sorted({x['key'] for x in coin['calls']}) == expect      # the reader fires exactly what the engine fires
            assert all(x['tf'] == 1 for x in coin['calls'])                  # no 5-minute bar closes at these minutes
        assert os.path.getsize(os.path.join(s.reader_dir, 'minutes', 'BTC.min')) == size + step * mc.REC


def test_the_last_minute_missing_or_a_gap_makes_the_coin_not_ok(world, oracle_path, tmp_path):
    pack, want = build(world, tmp_path)
    s = settings(tmp_path, pack, tmp_path / 'tables', oracle_path, window=world.window)
    fake = world.fake()
    btc = world.data['BTC']
    fake.data = dict(world.data, BTC=btc[btc[:, 0] != world.end - MIN])       # Binance has not published BTC's last minute
    r = reader_for(s, fake)
    obj = r.pass_once()
    assert_contract(obj)
    assert obj['coins']['BTC'] == {'asOf': world.end - MIN, 'tableSha': 'sha-BTC', 'ok': False, 'calls': [],
                                   'why': 'the minute that closed at 05:00 UTC is not in the Binance answer yet'}
    assert obj['coins']['ETH']['ok'] and len(obj['coins']['ETH']['calls']) == 5
    assert len([u for u in fake.klines() if 'BTCUSDT' in u]) == 8 + rd.LATE_TRIES   # it looked again, three times
    # a minute later Binance has the new minute but the one before stays missing: a gap, so the engine has no
    # 1-minute reading (it uses none for 100 bars after a missing minute) and the reader does not vouch for the coin
    fake.now += MIN
    obj = r.pass_once()
    assert obj['coins']['BTC']['ok'] is False and obj['coins']['BTC']['calls'] == [] and obj['coins']['BTC']['asOf'] == world.end + MIN
    assert 'no 1-minute reading holds a level' in obj['coins']['BTC']['why']
    assert obj['coins']['ETH']['ok']
    assert r.counts['goodPasses'] == 2 and r.counts['networkErrors'] == 0


def test_a_network_error_marks_the_coin_and_backs_off(world, oracle_path, tmp_path):
    pack, _ = build(world, tmp_path)
    s = settings(tmp_path, pack, tmp_path / 'tables', oracle_path, window=world.window)
    fake = world.fake()
    r = reader_for(s, fake)
    assert all(c['ok'] for c in r.pass_once()['coins'].values())
    fake.now += MIN
    fake.urls.clear()
    fake.fail += [FetchError('network: timed out')] * 3                      # the request and its two retries
    obj = r.pass_once()
    assert_contract(obj)
    assert obj['coins']['BTC'] == {'asOf': world.end, 'tableSha': 'sha-BTC', 'ok': False, 'calls': [], 'why': 'Binance fetch failed: network: timed out'}
    assert obj['coins']['ETH']['why'] == 'Binance is not asked for another 5 s after a failed request' and obj['coins']['ETH']['asOf'] == world.end
    assert len(fake.klines()) == 3 and r.counts['networkErrors'] == 1 and r.counts['goodPasses'] == 1
    fake.now += MIN                                                          # the next minute: the wait is over, both coins read again
    obj = r.pass_once()
    assert all(c['ok'] and c['asOf'] == world.end + 2 * MIN for c in obj['coins'].values()) and r.net_fails == 0
    # a rate limit waits as long as Binance asks: the next pass asks nothing, the one after reads again
    fake.now += MIN
    fake.fail.append((429, {'retry-after': '90'}))
    obj = r.pass_once()
    assert obj['coins']['BTC']['why'] == 'Binance fetch failed: HTTP 429 from Binance' and r.counts['rateLimits'] == 1
    fake.now += MIN
    fake.urls.clear()
    obj = r.pass_once()
    assert not any(c['ok'] for c in obj['coins'].values()) and fake.klines() == []
    assert 'Binance is not asked for another 30 s' in obj['coins']['BTC']['why']
    fake.now += MIN
    assert all(c['ok'] for c in r.pass_once()['coins'].values())


def test_an_engine_error_marks_the_coin_and_the_pass_goes_on(world, oracle_path, tmp_path, monkeypatch):
    pack, _ = build(world, tmp_path)
    s = settings(tmp_path, pack, tmp_path / 'tables', oracle_path, window=world.window)
    r = reader_for(s, world.fake())
    r._load_engine()
    real = r.engine.live.active_keys

    def broken(m, meta, **kw):
        if meta['table_sha256'] == 'sha-BTC':
            raise FloatingPointError('boom')
        return real(m, meta, **kw)
    monkeypatch.setattr(r.engine.live, 'active_keys', broken)
    obj = r.pass_once()
    assert_contract(obj)
    assert obj['coins']['BTC'] == {'asOf': world.end, 'tableSha': 'sha-BTC', 'ok': False, 'calls': [], 'why': 'engine error: FloatingPointError: boom'}
    assert obj['coins']['ETH']['ok'] and r.counts['engineErrors'] == 1 and r.counts['goodPasses'] == 1


def test_a_meta_of_another_table_refuses_the_coin(world, oracle_path, tmp_path):
    pack, want = build(world, tmp_path, eth_sha='sha-of-another-run')
    s = settings(tmp_path, pack, tmp_path / 'tables', oracle_path, window=world.window)
    fake = world.fake()
    obj = reader_for(s, fake).pass_once()
    assert_contract(obj)
    assert obj['coins']['ETH']['ok'] is False and obj['coins']['ETH']['calls'] == [] and obj['coins']['ETH']['tableSha'] == 'sha-ETH'
    assert obj['coins']['ETH']['why'] == 'table hash differs: the pack is of table sha-ETH, the meta of table sha-of-anoth'
    assert not [u for u in fake.klines() if 'ETHUSDT' in u]                  # no minute is fetched for a refused coin
    assert [(x['h'], x['rank'], x['key']) for x in obj['coins']['BTC']['calls']] == want['BTC']


def test_a_short_window_is_not_vouched_for(world, oracle_path, tmp_path):
    """Binance holds less history than the window needs: a timeframe with too few bars cannot fire, and without
    enough 1-minute bars the coin is not ok."""
    pack, want = build(world, tmp_path)
    s = settings(tmp_path, pack, tmp_path / 'tables', oracle_path, window=world.window, assets='BTC')
    fake = world.fake()
    fake.data = {'BTC': world.data['BTC'][-(2 * 1440 + 30):]}               # two days: 1,740 minutes after the midnight, 348 five-minute bars
    obj = reader_for(s, fake).pass_once()
    assert obj['coins']['BTC']['ok'] is True and obj['coins']['BTC']['why'] == 'only 348 of 600 5-minute bars are loaded'
    assert [x['tf'] for x in obj['coins']['BTC']['calls']] == [1, 1, 1, 1]     # the 5-minute row is out, the 1-minute rows fire
    fake.data = {'BTC': world.data['BTC'][-(400 + 30):]}                    # 400 minutes: 300 after the midnight
    s2 = settings(tmp_path / 'b', pack, tmp_path / 'tables', oracle_path, window=world.window, assets='BTC')
    obj = reader_for(s2, fake).pass_once()
    assert obj['coins']['BTC'] == {'asOf': world.end, 'tableSha': 'sha-BTC', 'ok': False, 'calls': [], 'why': 'only 300 of 600 1-minute bars are loaded'}


def test_the_engine_names_and_window(engine):
    assert engine.zone_levels == {'very low', 'low (falling in)', 'low (recovering)', 'high (rising in)', 'high (cooling)', 'very high'}
    assert engine.stale_back == engine.live.STALE_BACK == 616
    assert engine.need_minutes(3000, [1, 5, 15]) == (3000 + 616 + 2) * 15 + 1440
    assert engine.need_minutes(3000, [1, 60]) == (3000 + 616 + 2) * 60 + 1440
    assert base_of('5m:MOM10 sign=above 0') == '5m:MOM10' and base_of('1m:RSI14=low (falling in)') == '1m:RSI14'


class Clock:
    """Stands in for time.monotonic and the stop event's wait, on the fake Binance clock."""

    def __init__(self, fake, stop_after=None):
        self.fake, self.waits, self.stop_after = fake, [], stop_after

    def monotonic(self):
        return self.fake.now / 1000.0

    def is_set(self):
        return self.stop_after is not None and len(self.waits) >= self.stop_after

    def set(self):
        self.stop_after = 0

    def wait(self, sec):
        self.waits.append(round(sec, 3))
        self.fake.now += sec * 1000.0


def test_the_loop_wakes_three_seconds_after_the_minute(world, oracle_path, tmp_path, monkeypatch):
    pack, _ = build(world, tmp_path)
    s = settings(tmp_path, pack, tmp_path / 'tables', oracle_path, window=world.window)
    fake = world.fake(now=world.end + 41_000)                                # started 41 s into a minute
    r = reader_for(s, fake)
    clock = Clock(fake, stop_after=4)
    r.stop = clock
    monkeypatch.setattr(rd.time, 'monotonic', clock.monotonic)
    assert r.run() == 0                                                      # stopped on request
    assert clock.waits == [22.0, 60.0, 60.0, 60.0]                           # then at :03 of every minute
    lines = [json.loads(x) for x in open(rd.daily_path(s.calls_file, fake.now)).read().splitlines()]
    assert [x['coins']['BTC']['asOf'] for x in lines] == [world.end + i * MIN for i in range(4)]
    assert all(x['coins']['BTC']['ok'] and x['coins']['ETH']['ok'] for x in lines) and r.counts['goodPasses'] == 4


def test_wait_rules():
    m = 1_794_027_600_000
    assert rd.wait_sec(m + 3000, m + 3400, True) == pytest.approx(59.6)       # a normal pass: the next minute plus 3 s
    assert rd.wait_sec(m + 3000, m + 3400, False) == pytest.approx(59.6)
    assert rd.wait_sec(m + 50_000, m + MIN + 1000, True) == pytest.approx(2.0)    # a minute closed during a good pass: read it at :03
    assert rd.wait_sec(m + 50_000, m + MIN + 20_000, True) == 1.0             # already late: at once, but never under a second
    assert rd.wait_sec(m + 50_000, m + MIN + 20_000, False) == pytest.approx(43.0)   # a failed pass waits for the next minute


def test_the_loop_gives_up_after_ten_minutes_without_a_good_pass(world, tmp_path, monkeypatch):
    """Nothing can be read (no oracle code at the path): the loop keeps writing not-ok files once a minute, never
    raises, and exits 1 once ten minutes have passed, so systemd starts it again."""
    pack, _ = build(world, tmp_path)
    s = settings(tmp_path, pack, tmp_path / 'tables', tmp_path / 'no-oracle', window=world.window)
    fake = world.fake()
    r = reader_for(s, fake)
    clock = Clock(fake)
    r.stop = clock
    monkeypatch.setattr(rd.time, 'monotonic', clock.monotonic)
    logged = []
    r.log = logged.append
    assert r.run() == 1
    assert r.counts['passes'] == 12 and r.counts['goodPasses'] == 0 and clock.waits == [60.0] * 11
    assert 'no good pass for 600 s' in logged[-1]
    lines = open(rd.daily_path(s.calls_file, fake.now)).read().splitlines()
    assert len(lines) == 12 and all(not json.loads(x)['coins']['BTC']['ok'] for x in lines)


def test_a_pass_that_raises_does_not_end_the_loop(world, oracle_path, tmp_path, monkeypatch):
    pack, _ = build(world, tmp_path)
    s = settings(tmp_path, pack, tmp_path / 'tables', oracle_path, window=world.window)
    fake = world.fake()
    r = reader_for(s, fake)
    clock = Clock(fake, stop_after=3)
    r.stop = clock
    monkeypatch.setattr(rd.time, 'monotonic', clock.monotonic)
    real, n = rd.write_atomic, {'n': 0}

    def flaky(path, text):
        n['n'] += 1
        if n['n'] == 3:                                                      # the second pass cannot write the calls file
            raise OSError('No space left on device')
        real(path, text)
    monkeypatch.setattr(rd, 'write_atomic', flaky)
    logged = []
    r.log = logged.append
    assert r.run() == 0
    assert r.counts['passErrors'] == 1 and r.counts['passes'] == 3 and r.counts['goodPasses'] == 2
    assert any('pass failed: OSError: No space left on device' in x for x in logged)
    assert json.load(open(s.calls_file))['coins']['BTC']['asOf'] == world.end + 2 * MIN
