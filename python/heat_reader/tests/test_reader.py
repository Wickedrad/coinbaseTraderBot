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

from conftest import T0, FetchError, World, assert_contract, bot_parse, pack_row, pair_row, perp_pair, perp_row, reader_for, settings, write_packs
from heat_reader import MIN
from heat_reader import cache as mc
from heat_reader import reader as rd
from heat_reader.config import status_path
from heat_reader.pack import SKIP_DOMINANCE, SKIP_PARITY, SKIP_RANK, base_of, indicator_of


def held_states(world, coin: str, end: int, tfs=(1, 5)) -> dict:
    """Readings of these timeframes that hold a level at end (the engine's own answer, asked directly): sign and
    condition readings, so no zone edges are needed."""
    m = world.grid(coin, end)
    names = set()
    for k in tfs:
        R, _, _ = world.engine.live.tf_codes(m, k, world.meta[coin]['edges'], world.meta[coin]['price_step'], world.window)
        names |= {r['name'] for r in R if not r.get('zones')}
    got = world.events(coin, end, states=names)['states']
    return {k: v for k, v in sorted(got.items()) if v is not None}


def build(world, tmp_path, coins=('BTC', 'ETH'), end=None, eth_sha=None, pairs=False, perp=False):
    """A pack folder whose rows are picked from what the engine fires at `end` (and some that do not fire),
    live_meta.json with the engine's own edges, and the expected calls per coin as (h, rank, kind, key).
    pairs: also a pair pack with rows whose conditions hold at `end`, rows whose conditions do not, a dominance row
    and a row the parity check marked. perp: also the perp packs (top 30) with h240 and h1440 singles and pairs, a
    share-only row, and a row on the indicator the traded pack marks live_parity false."""
    end = world.end if end is None else end
    rows, prs, want, per, pprs = [], [], {}, [], []
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
                 pack_row(c, one[3], h=15, rank=7, live_parity=False, sha=sha),             # fires in the engine, marked off in the pack
                 pack_row(c, quiet[3], h=15, rank=41, sha=sha)]                             # a share-only row: never asked for
        want[c] = [(15, 1, 'single', one[0]), (15, 2, 'single', one[1]), (15, 3, 'single', five[0]), (15, 4, 'single', quiet[0]),
                   (60, 5, 'single', one[0])]
        if pairs:
            st = held_states(world, c, end)
            (a, la), (b, lb) = [(k, v) for k, v in st.items() if k.startswith('1m:')][0], [(k, v) for k, v in st.items() if k.startswith('5m:')][0]
            other = next(x for x in ('below 0', 'above 0', 'above', 'below') if x != la)
            prs += [pair_row(c, one[0], [(a, la)], oheat=150.0, sha=sha),                     # holds, hotter than every single: rank 1
                    pair_row(c, one[0], [(a, other)], oheat=160.0, sha=sha),                  # its condition does not hold
                    pair_row(c, one[1], [(b, lb), (a, la)], oheat=94.5, direction=1, sha=sha),     # a triple that holds: 4 singles hotter
                    pair_row(c, quiet[0], [(b, lb)], oheat=80.0, sha=sha),                    # its trigger fires through the single's alias
                    pair_row(c, quiet[1], [(a, la)], oheat=90.0, sha=sha),                    # its trigger does not fire
                    pair_row(c, one[0], [(a, la)], oheat=300.0, dominance=True, sha=sha),     # never: no dominance feed
                    pair_row(c, one[0], [(b, lb)], oheat=300.0, live_parity=False, sha=sha)]  # never: the parity check marked it
            want[c] += [(15, 1, 'pair', f'{one[0]} | {a}={la}'), (15, 7, 'pair', f'{quiet[0]} | {b}={lb}'),
                        (15, 5, 'triple', f'{one[1]} | {b}={lb} | {a}={la}')]
        if perp:
            off = indicator_of(one[3])                                                    # its h15 row above is marked live_parity false
            pk = [k for k in one if indicator_of(k) != off]
            st = [(k, v) for k, v in held_states(world, c, end).items() if indicator_of(k) != off]
            (a, la), (b, lb) = [x for x in st if x[0].startswith('1m:')][0], [x for x in st if x[0].startswith('5m:')][0]
            other = next(x for x in ('below 0', 'above 0', 'above', 'below') if x != la)
            assert len(pk) >= 3, (c, one)
            psha = f'long-sha-{c}'
            per += [perp_row(c, pk[0], h=240, rank=1, sha=psha), perp_row(c, five[0], h=240, rank=2, tf='5m', sha=psha),
                    perp_row(c, quiet[4], h=240, rank=3, sha=psha),                       # does not fire
                    perp_row(c, one[3], h=240, rank=4, sha=psha),                         # fires, on the indicator the traded pack marks
                    perp_row(c, pk[1], h=1440, rank=2, sha=psha),
                    perp_row(c, pk[2], h=240, rank=41, sha=psha)]                         # a share-only row: never asked for
            pprs += [perp_pair(c, pk[0], [(a, la)], oheat=98.5, sha=psha),                # holds: rank 2 on the 240 ladder (99 is hotter)
                     perp_pair(c, pk[0], [(a, other)], oheat=120.0, sha=psha),            # its condition does not hold
                     perp_pair(c, pk[1], [(b, lb)], h=1440, oheat=99.0, sha=psha)]        # holds: rank 1 on the 1440 ladder
            want[c] += [(240, 1, 'single', pk[0]), (240, 2, 'single', five[0]), (240, 2, 'pair', f'{pk[0]} | {a}={la}'),
                        (1440, 1, 'pair', f'{pk[1]} | {b}={lb}'), (1440, 2, 'single', pk[1])]
        want[c].sort(key=lambda x: (x[0], x[1], ('single', 'pair', 'triple').index(x[2]), x[3]))
    meta = {c: dict(world.meta[c], table_sha256=(eth_sha if c != 'BTC' and eth_sha else world.meta[c]['table_sha256'])) for c in coins}
    folder = write_packs(tmp_path / 'packs', rows, {c: f'sha-{c}' for c in coins}, pairs=prs, meta=meta,
                         perp=per if perp else None, perp_pairs=pprs, perp_head={'top': 30})
    return folder, want


def called(coin: dict) -> list:
    return [(x['h'], x['rank'], x['kind'], x['key']) for x in coin['calls']]


def test_one_pass_end_to_end(world, oracle_path, tmp_path):
    pack, want = build(world, tmp_path)
    s = settings(tmp_path, pack, oracle_path, window=world.window)
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
        assert called(coin) == want[c]
        assert all(x['barClose'] == world.end for x in coin['calls'])       # every fired row: the bar that closed now
        five = next(x for x in coin['calls'] if x['rank'] == 3)
        assert five['tf'] == 5 and five['share'] == 0.5325 and five['odds'] == 3.25 and five['heat'] == 97.0 and five['of'] == 40
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
    assert status['coins']['BTC']['fired'] == 5 and status['coins']['BTC']['keys'] == sorted({k for _, _, _, k in want['BTC']})
    assert status['coins']['BTC']['rows'] == {'wanted': {'single': 7, 'pair': 0, 'triple': 0, 'clock': 0},
                                              'skipped': {SKIP_PARITY: 1, 'rank beyond HEAT_READER_MAX_RANK': 1}}
    side = json.load(open(status_path(s.calls_file)))                       # the sidecar the bot's status reads
    assert side['v'] == 1 and side['writtenAt'] == obj['writtenAt'] and side['maxRank'] == 40 and side['clockPack'] is False
    assert sorted(side['packs']) == ['live_meta.json', 'pair_pack.json', 'traded_pack.json'] and side['packSha'] == obj['packSha']
    assert side['coins']['BTC'] == {'ok': True, 'fired': {'single': 5}, 'rows': status['coins']['BTC']['rows']}
    # HEAT_PERP_PACKS is on by default and this folder has no perp packs: the sidecar says so, the h15 and h60 rows are as above
    assert side['perpPacks'] is True and side['perpProblem'] == f'perp_pack.json cannot be read in {pack} (FileNotFoundError)'
    assert status['coins']['BTC']['closed'] == [1, 5] and status['coins']['BTC']['minutes'] >= world.window * 5
    got = bot_parse(open(s.calls_file).read())
    if got is not None:                                                     # the bot's own reader takes the file as it is
        assert got == {'run': '43030435253', 'coins': {c: {'ok': True, 'calls': 5, 'asOf': world.end} for c in ('BTC', 'ETH')}}


def test_pairs_end_to_end(world, oracle_path, tmp_path):
    """Pairs and triples with the real engine: a row fires when its trigger fires and its conditions hold at their
    own last closed bar (asked of the engine directly to build the pack); the bot's reader takes the rows."""
    pack, want = build(world, tmp_path, pairs=True)
    s = settings(tmp_path, pack, oracle_path, window=world.window)
    r = reader_for(s, world.fake())
    obj = r.pass_once()
    assert_contract(obj)
    for c in ('BTC', 'ETH'):
        coin = obj['coins'][c]
        assert coin["ok"] and called(coin) == want[c]
        pair = next(x for x in coin['calls'] if x['kind'] == 'pair' and x['rank'] == 1)
        single = next(x for x in coin['calls'] if x['kind'] == 'single' and x['rank'] == 1)
        assert pair['trig'] == single['key'] and pair['tf'] == 1 and pair['of'] == 40 and pair['heat'] == 150.0 and pair['share'] == 0.545
        assert pair['barClose'] == world.end and pair['odds'] == 4.5 and pair['hold'] == 8.3 and pair['dip'] == -6.5 and pair['move'] == 0.7
        tri = next(x for x in coin['calls'] if x['kind'] == 'triple')
        assert tri['dir'] == 1 and tri['trig'] == next(x for x in coin['calls'] if x['rank'] == 2 and x['kind'] == 'single')['key']
    status = json.load(open(os.path.join(s.reader_dir, 'status.json')))
    assert status['coins']['BTC']['rows'] == {'wanted': {'single': 7, 'pair': 4, 'triple': 1, 'clock': 0},
                                              'skipped': {SKIP_DOMINANCE: 1, SKIP_PARITY: 2, 'rank beyond HEAT_READER_MAX_RANK': 1}}
    assert status['coins']['BTC']['firedBy'] == {'single': 5, 'pair': 2, 'triple': 1} and status['coins']['BTC']['long'] is None
    side = json.load(open(status_path(s.calls_file)))
    assert side['coins']['ETH']['fired'] == {'single': 5, 'pair': 2, 'triple': 1} and side['coins']['ETH']['rows'] == status['coins']['ETH']['rows']
    parsed = bot_parse(open(s.calls_file).read())
    if parsed is not None:                                                  # the bot's own reader takes pairs and triples as they are
        assert parsed['coins']['BTC'] == {'ok': True, 'calls': 8, 'asOf': world.end}


def test_perp_rows_end_to_end(world, oracle_path, tmp_path):
    """The perp packs with the real engine: h240 and h1440 rows published beside h15 and h60, with of = the perp pack's
    top (30 here), a pair on 240 that fires when its condition holds at its last closed bar, and a row on the indicator
    the traded pack marks live_parity false left out although it fires. HEAT_PERP_PACKS=false gives h15 and h60 only."""
    pack, want = build(world, tmp_path, pairs=True, perp=True)
    s = settings(tmp_path, pack, oracle_path, window=world.window)
    obj = reader_for(s, world.fake()).pass_once()
    assert_contract(obj)
    for c in ('BTC', 'ETH'):
        coin = obj['coins'][c]
        assert coin['ok'] and 'why' not in coin and called(coin) == want[c]
        assert {x['h'] for x in coin['calls']} == {15, 60, 240, 1440} and all(x['of'] == (30 if x['h'] > 60 else 40) for x in coin['calls'])
        pair = next(x for x in coin['calls'] if x['h'] == 240 and x['kind'] == 'pair')
        assert pair['trig'] == next(x for x in coin['calls'] if x['h'] == 240 and x['rank'] == 1)['key'] and pair['heat'] == 98.5 and pair['tf'] == 1
        assert all(x['barClose'] == world.end for x in coin['calls'])
    side = json.load(open(status_path(s.calls_file)))
    assert side['perpPacks'] is True and 'perpProblem' not in side
    assert sorted(side['packs']) == ['live_meta.json', 'pair_pack.json', 'perp_pack.json', 'perp_pair_pack.json', 'traded_pack.json']
    assert side['coins']['BTC']['rows']['perp'] == {'wanted': {'single': 4, 'pair': 3, 'triple': 0}, 'skipped': {SKIP_PARITY: 1, SKIP_RANK: 1}}
    assert side['coins']['BTC']['rows']['wanted'] == {'single': 7, 'pair': 4, 'triple': 1, 'clock': 0}
    assert side['coins']['BTC']['fired'] == {'single': 8, 'pair': 4, 'triple': 1}
    parsed = bot_parse(open(s.calls_file).read())
    if parsed is not None:                                                  # the bot's own reader takes the h240 and h1440 rows
        assert parsed['coins']['BTC'] == {'ok': True, 'calls': 13, 'asOf': world.end}
    off = settings(tmp_path / 'off', pack, oracle_path, window=world.window, perp_packs='false')
    obj = reader_for(off, world.fake()).pass_once()
    for c in ('BTC', 'ETH'):
        assert called(obj['coins'][c]) == [x for x in want[c] if x[0] in (15, 60)]
    side = json.load(open(status_path(off.calls_file)))
    assert side['perpPacks'] is False and 'perpProblem' not in side and 'perp' not in side['coins']['BTC']['rows']
    assert sorted(side['packs']) == ['live_meta.json', 'pair_pack.json', 'traded_pack.json']


@pytest.fixture(scope='session')
def hour_world(engine):
    """55 days of BTC minutes ending 2 minutes before an hourly close, 10 more minutes served as time moves on: enough
    for a 300-bar window of 60-minute bars, and for zone edges on them (the engine wants 1,000 values)."""
    return World(engine, coins=('BTC',), days=55, window=300, tfs=(1, 5, 60), end_ms=T0 + 5 * 60 * MIN - 2 * MIN, extra=10)


def test_hourly_states_are_read_once_an_hour_and_kept(hour_world, oracle_path, tmp_path, monkeypatch):
    """A pair conditioned on a 60-minute reading needs the long window, but its level changes only on the hour: the
    reader reads the 60-minute timeframe at its first pass and at each hourly close, keeps the levels in between, and
    hands the engine only the short window the other minutes. What it holds is what the engine says on the whole
    window at every minute."""
    w = hour_world
    end = w.end
    m = w.grid('BTC', end)
    R, _, _ = w.engine.live.tf_codes(m, 60, w.meta['BTC']['edges'], w.meta['BTC']['price_step'], w.window)
    # 60-minute readings that hold a level now: zone levels (they need the meta's edges) and sign or condition ones
    zones = sorted(r['name'] for r in R if r.get('zones') and r['codes'][-1] >= 0)[:3]
    others = sorted(r['name'] for r in R if not r.get('zones') and r['codes'][-1] >= 0)[:3]
    long_names = zones + others
    assert len(zones) == 3 and len(others) == 3
    direct = w.events('BTC', end, states=long_names)['states']
    # every 1-minute event key of the next minutes as a single, so pairs on them can fire at each step
    keys = sorted({k for t in range(end, end + 6 * MIN, MIN) for k in w.events('BTC', t)['events'] if k.startswith('1m:')})
    rows = [pack_row('BTC', k, rank=i + 1, sha='sha-BTC') for i, k in enumerate(keys[:40])]
    prs = [pair_row('BTC', k, [(n, lv)], oheat=200.0 - i, sha='sha-BTC') for i, k in enumerate(keys[:40]) for n in long_names
           for lv in {direct[n], 'below 0', 'above 0'}]
    folder = write_packs(tmp_path / 'packs', rows, {'BTC': 'sha-BTC'}, pairs=prs, meta={'BTC': w.meta['BTC']})
    s = settings(tmp_path, folder, oracle_path, window=w.window, assets='BTC')
    fake = w.fake()
    r = reader_for(s, fake)
    r.tables.refresh()
    r._load_engine()
    table = r.tables.coins['BTC']
    assert table.problem is None and table.tfs == [1, 60] and table.long_states == set(long_names)
    seen = []
    real = r.engine.read

    def spy(minutes, end_ms, table, window, tfs, states):
        seen.append((end_ms, list(tfs), len(minutes), sorted(st for st in states if st.startswith('60m:'))))
        return real(minutes, end_ms, table, window, tfs, states)
    monkeypatch.setattr(r.engine, 'read', spy)
    short_need = r.engine.need_minutes(w.window, [1])
    fired = held_back = 0
    kept = []
    for step in range(6):                                                   # 04:58, 04:59, 05:00 (an hourly close), 05:01 ...
        t = end + step * MIN
        fake.now = t + 3000
        obj = r.pass_once()
        coin = obj['coins']['BTC']
        assert coin['ok'], coin
        full = w.events('BTC', t, tfs=[1, 5, 60], states=long_names)
        assert r.long['BTC'].states == full['states']                       # the kept levels are the whole-window ones
        assert r.long['BTC'].bar == t // rd.HOUR * rd.HOUR
        kept.append(dict(r.long['BTC'].states))
        fired1 = {k for k in full['events'] if k.startswith('1m:')}
        expect = sorted(p['key'] for p in prs if (p['when'] in fired1 and full['states'][p['conds'][0][0]] == p['conds'][0][1]))
        assert sorted(x['key'] for x in coin['calls'] if x['kind'] == 'pair') == expect
        fired += len(expect)
        held_back += sum(1 for p in prs if p['when'] in fired1) - len(expect)
    assert fired >= 20 and held_back >= 20                                  # the 60-minute conditions decided, both ways
    assert kept[0] == kept[1] != kept[2] == kept[3]                         # a level changed with the hourly bar, and was picked up
    # the long window was handed to the engine twice: the first pass (a fresh start) and the hourly close at 05:00
    longs = [(e, n) for e, tfs, n, st in seen if 60 in tfs]
    assert [e for e, _ in longs] == [end, end + 2 * MIN] and all(n >= r.engine.need_minutes(w.window, [1, 60]) - 1440 for _, n in longs)
    assert all(tfs == [1] and n <= short_need and st == [] for e, tfs, n, st in seen if e not in (end, end + 2 * MIN))
    status = json.load(open(os.path.join(s.reader_dir, 'status.json')))
    assert status['coins']['BTC']['long'] == 'kept'


def test_the_next_minute_and_a_restart_ask_for_one_minute_only(world, oracle_path, tmp_path):
    pack, _ = build(world, tmp_path)
    s = settings(tmp_path, pack, oracle_path, window=world.window)
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
    s = settings(tmp_path, pack, oracle_path, window=world.window)
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
    s = settings(tmp_path, pack, oracle_path, window=world.window)
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
    s = settings(tmp_path, pack, oracle_path, window=world.window)
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
    s = settings(tmp_path, pack, oracle_path, window=world.window)
    fake = world.fake()
    obj = reader_for(s, fake).pass_once()
    assert_contract(obj)
    assert obj['coins']['ETH']['ok'] is False and obj['coins']['ETH']['calls'] == [] and obj['coins']['ETH']['tableSha'] == 'sha-ETH'
    assert obj['coins']['ETH']['why'] == 'table hash differs: the pack is of table sha-ETH, live_meta.json of table sha-of-anoth'
    assert not [u for u in fake.klines() if 'ETHUSDT' in u]                  # no minute is fetched for a refused coin
    assert called(obj["coins"]["BTC"]) == want["BTC"]


def test_a_short_window_is_not_vouched_for(world, oracle_path, tmp_path):
    """Binance holds less history than the window needs: a timeframe with too few bars cannot fire, and without
    enough 1-minute bars the coin is not ok."""
    pack, want = build(world, tmp_path)
    s = settings(tmp_path, pack, oracle_path, window=world.window, assets='BTC')
    fake = world.fake()
    fake.data = {'BTC': world.data['BTC'][-(2 * 1440 + 30):]}               # two days: 1,740 minutes after the midnight, 348 five-minute bars
    obj = reader_for(s, fake).pass_once()
    assert obj['coins']['BTC']['ok'] is True and obj['coins']['BTC']['why'] == 'only 348 of 600 5-minute bars are loaded'
    assert [x['tf'] for x in obj['coins']['BTC']['calls']] == [1, 1, 1, 1]     # the 5-minute row is out, the 1-minute rows fire
    fake.data = {'BTC': world.data['BTC'][-(400 + 30):]}                    # 400 minutes: 300 after the midnight
    s2 = settings(tmp_path / 'b', pack, oracle_path, window=world.window, assets='BTC')
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
    s = settings(tmp_path, pack, oracle_path, window=world.window)
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
    s = settings(tmp_path, pack, tmp_path / 'no-oracle', window=world.window)
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
    s = settings(tmp_path, pack, oracle_path, window=world.window)
    fake = world.fake()
    r = reader_for(s, fake)
    clock = Clock(fake, stop_after=3)
    r.stop = clock
    monkeypatch.setattr(rd.time, 'monotonic', clock.monotonic)
    real, n = rd.write_atomic, {'n': 0}

    def flaky(path, text):
        n['n'] += 1
        if n['n'] == 4:                         # the second pass cannot write the calls file (a pass writes it, status.json, the sidecar)
            raise OSError('No space left on device')
        real(path, text)
    monkeypatch.setattr(rd, 'write_atomic', flaky)
    logged = []
    r.log = logged.append
    assert r.run() == 0
    assert r.counts['passErrors'] == 1 and r.counts['passes'] == 3 and r.counts['goodPasses'] == 2
    assert any('pass failed: OSError: No space left on device' in x for x in logged)
    assert json.load(open(s.calls_file))['coins']['BTC']['asOf'] == world.end + 2 * MIN
