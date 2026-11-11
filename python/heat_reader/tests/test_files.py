"""What the reader leaves on disk: the calls file (shape against the TypeScript contract, written atomically) and the
daily replay log with its 14 days."""
import json
import os

import pytest

from conftest import FIXTURES, T0, FakeBinance, assert_contract, bot_parse, contract, pack_row, reader_for, settings, walk, write_packs
from heat_reader import DAY, MIN
from heat_reader import reader as rd
from heat_reader.config import status_path
from heat_reader.pack import Tables, call_row, pair_call


def test_contract_field_names():
    c = contract()
    assert c['HeatCallsFile'] == ({'v', 'source', 'run', 'packSha', 'writtenAt', 'coins'}, set())
    assert c['HeatCoinCalls'] == ({'asOf', 'tableSha', 'ok', 'calls'}, {'why'})
    assert c['HeatCallRow'][0] == {'key', 'kind', 'tf', 'h', 'dir', 'rank', 'of', 'heat', 'share', 'odds', 'barClose'}
    assert c['HeatCallRow'][1] == {'aliases', 'trig', 'hold', 'dip', 'move'}
    # the two mapping functions write every required field and nothing the contract does not know
    pack = json.load(open(os.path.join(FIXTURES, 'traded_pack.json')))
    for r in pack['rows']:
        row = call_row(r, pack['top'], T0)
        assert c['HeatCallRow'][0] <= set(row) <= c['HeatCallRow'][0] | c['HeatCallRow'][1]
        assert 'trig' not in row                                   # a single refines nothing
    t = Tables(FIXTURES, ['BTC', 'ETH', 'SOL', 'XRP'], clock=True)
    t.refresh()
    pairs = [p for x in t.coins.values() for p in x.pairs]
    assert len(pairs) == 38                                       # 33 pairs and triples, 5 clock rows above the twin
    for p in pairs:
        row = pair_call(p, p['rank'], t.top, T0)
        assert c['HeatCallRow'][0] <= set(row) <= c['HeatCallRow'][0] | c['HeatCallRow'][1]
        assert row['trig'] == p['when'] and row['kind'] in ('pair', 'triple')


def test_a_file_with_no_coin_readable_still_fits_the_contract(tmp_path):
    """No oracle code at the given path: every coin is written not ok with the reason, in the bot's shape."""
    pack = write_packs(tmp_path / 'packs', [pack_row('BTC', '1m:RSI7=very low')], {'BTC': 'sha-xxxxxxxx'},
                       meta={'BTC': {'edges': {'1m:RSI7': [1, 2, 3, 4]}, 'price_step': 0.01, 'table_sha256': 'sha-xxxxxxxx'}})
    s = settings(tmp_path, pack, tmp_path / 'no-oracle-here', assets='BTC,ETH,DOGE')
    fake = FakeBinance({'BTC': walk(10, T0 + 9 * MIN)}, now=T0 + 10 * MIN + 3000)
    r = reader_for(s, fake)
    obj = r.pass_once()
    assert_contract(obj)
    on_disk = json.load(open(s.calls_file))
    assert on_disk == obj and list(obj['coins']) == ['BTC', 'ETH']                     # DOGE was refused, never written
    assert obj['run'] == '43030435253' and len(obj['packSha']) == 64 and obj['writtenAt'] == T0 + 10 * MIN + 3000
    assert obj['coins']['BTC'] == {'asOf': T0 + 10 * MIN, 'tableSha': 'sha-xxxxxxxx', 'ok': False, 'calls': [],
                                   'why': f'no oracle/heat_live.py under {tmp_path / "no-oracle-here"} (HEAT_ORACLE_PATH)'}
    assert obj['coins']['ETH']['why'] == 'traded_pack.json has no rows for this coin' and obj['coins']['ETH']['tableSha'] == ''
    assert fake.klines() == []                                                          # nothing was asked of Binance for a coin that cannot be read
    status = json.load(open(os.path.join(s.reader_dir, 'status.json')))
    assert status['counts']['passes'] == 1 and status['counts']['goodPasses'] == 0 and status['coins']['BTC']['ok'] is False
    side = json.load(open(status_path(s.calls_file)))                                   # the sidecar says the same, with the row counts
    assert side['coins']['BTC']['ok'] is False and side['coins']['BTC']['why'] == obj['coins']['BTC']['why'] and side['coins']['BTC']['fired'] == {}
    assert side['coins']['BTC']['rows'] == {'wanted': {'single': 1, 'pair': 0, 'triple': 0, 'clock': 0}, 'skipped': {}}
    assert side['coins']['ETH']['rows'] == {'wanted': {'single': 0, 'pair': 0, 'triple': 0, 'clock': 0}, 'skipped': {}}
    got = bot_parse(open(s.calls_file).read())
    if got is not None:                                                                 # the bot's own reader takes the file
        assert 'error' not in got and got['run'] == '43030435253'
        assert got['coins']['BTC']['ok'] is False and got['coins']['BTC']['why'] == obj['coins']['BTC']['why']       # nothing in it is "malformed"
        assert got['coins']['ETH']['why'] == 'traded_pack.json has no rows for this coin' and got['coins']['ETH']['asOf'] == T0 + 10 * MIN


def test_a_missing_pack_is_said_in_the_file(tmp_path):
    s = settings(tmp_path, tmp_path / 'nope', tmp_path / 'no-oracle', assets='BTC')
    obj = reader_for(s, FakeBinance({}, now=T0 + 3000)).pass_once()
    assert_contract(obj)
    assert obj['run'] == 'unknown' and obj['packSha'] == '' and obj['coins']['BTC']['why'] == f'traded_pack.json cannot be read in {tmp_path / "nope"} (FileNotFoundError)'
    side = json.load(open(status_path(s.calls_file)))
    assert side['problem'] == obj['coins']['BTC']['why'] and side['packs'] == {}


def test_the_calls_file_is_replaced_whole(tmp_path, monkeypatch):
    path = str(tmp_path / 'd' / 'heat_calls.json')
    rd.write_atomic(path, '{"old":1}\n')
    seen = {}
    real = os.replace

    def spy(src, dst):
        # at the moment of the swap the new text is complete in a file of the SAME folder and the old file is whole
        seen['src_dir'], seen['new'], seen['old'] = os.path.dirname(src), open(src).read(), open(dst).read()
        real(src, dst)
    monkeypatch.setattr(os, 'replace', spy)
    rd.write_atomic(path, '{"new":2}\n')
    assert seen == {'src_dir': os.path.dirname(path), 'new': '{"new":2}\n', 'old': '{"old":1}\n'}
    assert open(path).read() == '{"new":2}\n' and os.listdir(tmp_path / 'd') == ['heat_calls.json']
    # a write that fails halfway leaves the old file and no temporary file behind
    monkeypatch.setattr(os, 'fsync', lambda fd: (_ for _ in ()).throw(OSError('disk full')))
    with pytest.raises(OSError):
        rd.write_atomic(path, '{"half":')
    assert open(path).read() == '{"new":2}\n' and os.listdir(tmp_path / 'd') == ['heat_calls.json']


def test_daily_log_and_its_14_days(tmp_path):
    calls = str(tmp_path / 'heat_calls.json')
    day0 = T0 + 20 * DAY
    for d in range(20):                                             # twenty days of logs, some days with two lines
        for line in range(1 + d % 2):
            rd.append_daily(calls, json.dumps({'d': d, 'n': line}), T0 + d * DAY + line * MIN)
    assert rd.daily_path(calls, T0) == str(tmp_path / 'heat_calls-2026-11-07.jsonl')
    assert open(rd.daily_path(calls, T0 + DAY)).read() == '{"d": 1, "n": 0}\n{"d": 1, "n": 1}\n'
    for name in ('heat_calls.json', 'heat_calls-notes.jsonl', 'heat_calls-2026-11-07.jsonl.bak', 'other-2026-11-07.jsonl', 'heat_calls-2026-11-08.jsonl.gz'):
        open(tmp_path / name, 'w').write('x')
    gone = rd.prune_daily(calls, day0 - DAY + 5 * MIN)              # "now" is on the 20th log day (index 19)
    left = sorted(os.listdir(tmp_path))
    logs = [n for n in left if rd.DAILY.match(n)]
    assert len(logs) == 14 and logs[0] == 'heat_calls-2026-11-13.jsonl' and logs[-1] == 'heat_calls-2026-11-26.jsonl'
    assert len(gone) == 7 and any(g.endswith('heat_calls-2026-11-08.jsonl.gz') for g in gone)          # a compressed old day goes too
    # files that are not the daily log are never touched
    assert {'heat_calls.json', 'heat_calls-notes.jsonl', 'heat_calls-2026-11-07.jsonl.bak', 'other-2026-11-07.jsonl'} <= set(left)
    assert rd.prune_daily(calls, day0 - DAY + 5 * MIN) == []


def test_the_reader_appends_each_file_and_rotates_at_the_day_change(tmp_path):
    s = settings(tmp_path, tmp_path / 'nope', tmp_path / 'no-oracle', assets='BTC')
    d = os.path.dirname(s.calls_file)
    os.makedirs(d)
    for i in range(1, 30):                                          # logs of the 29 days before
        open(os.path.join(d, f'heat_calls-{rd.day_of(T0 - i * DAY)}.jsonl'), 'w').write('{}\n')
    fake = FakeBinance({}, now=T0 + 23 * 60 * MIN + 58 * MIN + 3000)
    r = reader_for(s, fake)
    a = r.pass_once()
    fake.now += MIN
    b = r.pass_once()
    today = os.path.join(d, 'heat_calls-2026-11-07.jsonl')
    assert [json.loads(x) for x in open(today).read().splitlines()] == [a, b]             # the same object as in the calls file, one per line
    assert json.load(open(s.calls_file)) == b
    assert len([n for n in os.listdir(d) if rd.DAILY.match(n)]) == 14                     # today and the 13 days before
    fake.now += MIN                                                                       # 00:00:03 the next day
    c = r.pass_once()
    assert [json.loads(x) for x in open(os.path.join(d, 'heat_calls-2026-11-08.jsonl')).read().splitlines()] == [c]
    names = sorted(n for n in os.listdir(d) if rd.DAILY.match(n))
    assert len(names) == 14 and names[0] == 'heat_calls-2026-10-26.jsonl' and names[-1] == 'heat_calls-2026-11-08.jsonl'
