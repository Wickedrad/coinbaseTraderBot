"""The traded pack, the metas and the join: which pack rows fire, and what a fired row looks like to the bot."""
import hashlib
import json
import os

import pytest

from conftest import PACKAGE, pack_row, write_meta, write_pack
from heat_reader import config
from heat_reader.engine import join
from heat_reader.pack import Tables, base_of, call_row, load_meta, tf_minutes

FIRST_PACK = os.path.join(PACKAGE, 'fixtures', 'traded_pack.first.json')
ZONE_LEVELS = {'very low', 'low (falling in)', 'low (recovering)', 'high (rising in)', 'high (cooling)', 'very high'}
TS = 1_794_027_600_000


def tables(tmp_path, rows, coins=('BTC',), sha=None, meta_sha=None, edges=None, **kw):
    sha = sha or {c: 'sha-xxxxxxxx' for c in coins}
    pack = write_pack(tmp_path / 'pack.json', rows, sha, **kw)
    for c in coins:
        keys = {k for r in rows if r['coin'] == c for k in [r['key']] + r['aliases']}
        e = {base_of(k): [-2.0, -1.0, 1.0, 2.0] for k in keys} if edges is None else edges
        write_meta(tmp_path / 'meta', c, {'edges': e, 'price_step': 0.01, 'table_sha256': (meta_sha or sha).get(c)})
    t = Tables(pack, str(tmp_path / 'meta'), list(coins))
    assert t.refresh()
    return t


def res(events, closed=(1,), no_reading=(), bars=None, levels=None, gap_last=False, ts=TS):
    """What engine.read() hands the join: active_keys' answer plus the grid facts."""
    closed = list(closed)
    return {'ts': ts, 'closed': closed, 'events': sorted(events), 'no_reading': list(no_reading), 'gap_last': gap_last,
            'bars': bars or {1: 5000, 5: 3600, 15: 3600, 60: 3600},
            'levels': {f'{k}m:RSI14': 'mid' for k in closed} if levels is None else levels, 'minutes': 5000}


def test_timeframes_in_minutes():
    assert [tf_minutes(x) for x in ('1m', '5m', '15m', '60m', '1h')] == [1, 5, 15, 60, 60]
    for bad in ('', 'm', '0m', '1d', None, 5):
        with pytest.raises(ValueError):
            tf_minutes(bad)


def test_a_pack_row_becomes_the_bots_row():
    pack = json.load(open(FIRST_PACK))
    row = next(r for r in pack['rows'] if r['coin'] == 'BTC' and r['h'] == 15 and r['rank_coin'] == 12)
    assert row['key'] == '1m:CMO14=high (rising in)' and row['share_B'] == 53.312 and row['odds_B'] == 3.2534
    got = call_row(row, pack['top'], TS)
    assert got == {'key': '1m:CMO14=high (rising in)', 'kind': 'single', 'aliases': ['1m:RSI14=high (rising in)'], 'tf': 1, 'h': 15,
                   'dir': -1, 'rank': 12, 'of': 40, 'heat': 94.102, 'share': 0.53312, 'odds': 3.2534, 'hold': 8.1777, 'dip': -6.2447,
                   'move': 0.3139, 'barClose': TS}
    # every row of the first pack maps, on its own timeframe, with a share that is a fraction
    for r in pack['rows']:
        c = call_row(r, pack['top'], TS)
        assert 0 < c['share'] < 1 and c['tf'] in (1, 5, 15) and c['key'].startswith(f"{c['tf']}m:") and c['dir'] in (1, -1) and c['of'] == 40
    assert call_row(pack_row('BTC', '60m:ADX14=very high', h=60, tf='60m'), 40, TS)['tf'] == 60
    assert 'hold' not in call_row(pack_row('BTC', '1m:RSI14=very low', hold_B=None), 40, TS)


@pytest.mark.parametrize('field,value', [('dir', 0), ('dir', True), ('share_B', 120.0), ('share_B', float('nan')), ('odds_B', None),
                                         ('oheat_B', 'hot'), ('rank_coin', 0), ('h', 0), ('h', 7.5), ('tf', '5m'), ('tf', '1d'),
                                         ('aliases', 'x'), ('key', ''), ('dip_B', float('inf'))])
def test_a_row_the_bot_must_not_trade_from_is_refused(field, value):
    row = pack_row('BTC', '1m:RSI14=very low')
    assert call_row(row, 40, TS)['key'] == '1m:RSI14=very low'
    row[field] = value
    with pytest.raises(ValueError):
        call_row(row, 40, TS)


def test_the_first_pack_loads_per_coin(tmp_path):
    pack = json.load(open(FIRST_PACK))
    for c in ('BTC', 'ETH', 'SOL', 'XRP'):
        keys = {k for r in pack['rows'] if r['coin'] == c for k in [r['key']] + r['aliases']}
        write_meta(tmp_path, c, {'edges': {base_of(k): [0.0, 1.0, 2.0, 3.0] for k in keys}, 'price_step': 0.01, 'table_sha256': pack['table_sha256'][c]})
    t = Tables(FIRST_PACK, str(tmp_path), ['BTC', 'ETH', 'SOL', 'XRP'])
    t.refresh()
    assert t.problem is None and t.top == 40 and t.run == '43030435253'
    assert t.pack_sha == hashlib.sha256(open(FIRST_PACK, 'rb').read()).hexdigest()
    assert {c: x.problem for c, x in t.coins.items()} == dict.fromkeys(['BTC', 'ETH', 'SOL', 'XRP'])
    assert sum(len(x.rows) for x in t.coins.values()) == 302
    assert t.coins['BTC'].tfs == [1, 5, 15] and t.coins['ETH'].tfs == [1, 5]
    btc = t.coins['BTC']
    assert '1m:RSI14=high (rising in)' in btc.want and '1m:CMO14=high (rising in)' in btc.want          # an alias is asked for too
    assert btc.table_sha == pack['table_sha256']['BTC'] and btc.meta['table_sha256'] == btc.table_sha
    assert set(btc.meta['edges']) == {base_of(k) for k in btc.want}                                    # only the readings the rows need
    for x in t.coins.values():
        x.check_edges(ZONE_LEVELS)
        assert x.problem is None


def test_key_and_alias_fire_once(tmp_path):
    rows = [pack_row('BTC', '1m:CMO14=high (rising in)', h=15, rank=3, aliases=['1m:RSI14=high (rising in)'], direction=-1),
            pack_row('BTC', '1m:CMO14=high (rising in)', h=60, rank=7, aliases=['1m:RSI14=high (rising in)'], direction=-1),
            pack_row('BTC', '1m:WILLR14=very low', h=15, rank=1),
            pack_row('BTC', '1m:STOCHK5=very high', h=15, rank=2)]
    t = tables(tmp_path, rows).coins['BTC']
    # only the alias name is among the events: the row fires once, under its own key
    calls, problem, notes = join(t, 40, res({'1m:RSI14=high (rising in)', '1m:WILLR14=very low', '1m:OTHER=very low'}), 3000)
    assert problem is None and notes == []
    assert [(c['h'], c['rank'], c['key']) for c in calls] == [(15, 1, '1m:WILLR14=very low'), (15, 3, '1m:CMO14=high (rising in)'),
                                                             (60, 7, '1m:CMO14=high (rising in)')]
    assert all(c['barClose'] == TS and c['kind'] == 'single' for c in calls)
    assert calls[1]['aliases'] == ['1m:RSI14=high (rising in)'] and calls[1]['dir'] == -1
    # key and alias both among the events: still one row per horizon
    calls, _, _ = join(t, 40, res({'1m:RSI14=high (rising in)', '1m:CMO14=high (rising in)'}), 3000)
    assert [(c['h'], c['key']) for c in calls] == [(15, '1m:CMO14=high (rising in)'), (60, '1m:CMO14=high (rising in)')]
    assert join(t, 40, res(set()), 3000) == ([], None, [])


def test_a_stale_timeframe_cannot_fire(tmp_path):
    rows = [pack_row('BTC', '1m:RSI7=very low', rank=1), pack_row('BTC', '5m:RSI7=very low', rank=2, tf='5m'),
            pack_row('BTC', '15m:RSI2=very low', rank=3, tf='15m')]
    t = tables(tmp_path, rows).coins['BTC']
    ev = {'1m:RSI7=very low', '5m:RSI7=very low', '15m:RSI2=very low'}
    assert [c['key'] for c in join(t, 40, res(ev, closed=(1, 5, 15)), 3000)[0]] == ['1m:RSI7=very low', '5m:RSI7=very low', '15m:RSI2=very low']
    # the engine says the last 5-minute bar holds a missing minute: its row cannot fire, the others can, and the coin says why
    calls, problem, notes = join(t, 40, res(ev, closed=(1, 5, 15), no_reading=(5,)), 3000)
    assert problem is None and [c['key'] for c in calls] == ['1m:RSI7=very low', '15m:RSI2=very low']
    assert notes == ['a minute is missing inside the last 5-minute bar']
    # a bar that did not close at this minute cannot fire, whatever the events say
    assert [c['key'] for c in join(t, 40, res(ev, closed=(1,)), 3000)[0]] == ['1m:RSI7=very low']
    # too few 15-minute bars for the window: that timeframe is out
    calls, problem, notes = join(t, 40, res(ev, closed=(1, 5, 15), bars={1: 9000, 5: 3600, 15: 2999}), 3000)
    assert [c['tf'] for c in calls] == [1, 5] and notes == ['only 2999 of 3000 15-minute bars are loaded']
    # no 5-minute reading holds a level (the engine uses none for 100 bars after a gap)
    calls, problem, notes = join(t, 40, res(ev, closed=(1, 5), levels={'1m:RSI7': 'very low'}), 3000)
    assert [c['tf'] for c in calls] == [1] and 'no 5-minute reading holds a level' in notes[0]


def test_without_one_minute_readings_the_coin_is_not_ok(tmp_path):
    t = tables(tmp_path, [pack_row('BTC', '1m:RSI7=very low'), pack_row('BTC', '5m:RSI7=very low', tf='5m', rank=2)]).coins['BTC']
    ev = {'1m:RSI7=very low', '5m:RSI7=very low'}
    for r, text in ((res(ev, closed=(1, 5), no_reading=(1,)), 'a minute is missing inside the last 1-minute bar'),
                    (res(ev, closed=(1, 5), gap_last=True), 'the last closed minute is missing or broken'),
                    (res(ev, closed=(1, 5), bars={1: 2000, 5: 400}), 'only 2000 of 3000 1-minute bars are loaded'),
                    (res(ev, closed=(1, 5), levels={'5m:RSI7': 'mid'}), 'no 1-minute reading holds a level')):
        calls, problem, notes = join(t, 40, r, 3000)
        assert calls == [] and text in problem


def test_rows_the_parity_check_marked_do_not_fire(tmp_path):
    rows = [pack_row('SOL', '1m:PVI=high (rising in)', rank=6, live_parity=False), pack_row('SOL', '1m:RSI7=very low', rank=9, live_parity=True)]
    t = tables(tmp_path, rows, coins=('SOL',)).coins['SOL']
    calls, problem, _ = join(t, 40, res({'1m:PVI=high (rising in)', '1m:RSI7=very low'}), 3000)
    assert problem is None and [c['key'] for c in calls] == ['1m:RSI7=very low']


def test_table_hash_mismatch_refuses_the_coin(tmp_path):
    rows = [pack_row('BTC', '1m:RSI7=very low', sha='aaa'), pack_row('ETH', '1m:RSI7=very low', sha='bbb')]
    t = tables(tmp_path, rows, coins=('BTC', 'ETH'), sha={'BTC': 'aaa', 'ETH': 'bbb'}, meta_sha={'BTC': 'aaa', 'ETH': 'ccc'})
    assert t.problem is None and t.coins['BTC'].problem is None and t.coins['BTC'].meta is not None
    assert 'table hash differs' in t.coins['ETH'].problem and t.coins['ETH'].meta is None and t.coins['ETH'].table_sha == 'bbb'
    # a row that carries another table's hash than its coin's
    t = tables(tmp_path / 'b', [pack_row('BTC', '1m:RSI7=very low', sha='zzz')], sha={'BTC': 'aaa'})
    assert 'table hash' in t.coins['BTC'].problem
    # the pack names no hash for the coin: nothing to compare with
    t = tables(tmp_path / 'c', [pack_row('BTC', '1m:RSI7=very low')], sha={'ETH': 'x'})
    assert 'no table hash' in t.coins['BTC'].problem and t.coins['BTC'].table_sha == ''


def test_metas_in_both_layouts(tmp_path):
    slim = {'BTC': {'price_step': 0.01, 'table_sha256': 'aaa', 'edges': {'1m:RSI7': [1, 2, 3, 4]}, 'no_edges': []}}
    os.makedirs(tmp_path / 'live')
    json.dump(slim, open(tmp_path / 'live' / 'live_meta.json', 'w'))
    assert load_meta(str(tmp_path / 'live'), 'BTC')['table_sha256'] == 'aaa'                 # one file keyed by coin
    assert load_meta(str(tmp_path / 'live' / 'live_meta.json'), 'BTC')['edges'] == {'1m:RSI7': [1, 2, 3, 4]}   # the file named directly
    with pytest.raises(ValueError, match='no meta.json for ETH'):
        load_meta(str(tmp_path / 'live'), 'ETH')
    write_meta(tmp_path / 'live', 'BTC', {'edges': {}, 'price_step': 0.5, 'table_sha256': 'own'})
    assert load_meta(str(tmp_path / 'live'), 'BTC')['table_sha256'] == 'own'                 # the coin's own meta.json comes first
    write_meta(tmp_path / 'bad', 'BTC', {'price_step': 0.5})
    with pytest.raises(ValueError, match='no zone edges'):
        load_meta(str(tmp_path / 'bad'), 'BTC')
    open(tmp_path / 'bad' / 'BTC' / 'meta.json', 'w').write('{not json')
    with pytest.raises(ValueError, match='cannot be read'):
        load_meta(str(tmp_path / 'bad'), 'BTC')
    pack = write_pack(tmp_path / 'p.json', [pack_row('BTC', '1m:RSI7=very low', sha='aaa')], {'BTC': 'aaa'})
    os.unlink(tmp_path / 'live' / 'BTC' / 'meta.json')
    t = Tables(pack, str(tmp_path / 'live'), ['BTC', 'XRP'])
    t.refresh()
    assert t.coins['BTC'].problem is None and t.coins['BTC'].meta['edges'] == {'1m:RSI7': [1, 2, 3, 4]}
    assert t.coins['XRP'].problem == 'the traded pack has no rows for this coin'


def test_missing_zone_edges_refuse_the_coin(tmp_path):
    rows = [pack_row('BTC', '1m:RSI7=very low'), pack_row('BTC', '1m:KVO>sig=below', rank=2), pack_row('BTC', '1m:MOM10 sign=above 0', rank=3)]
    t = tables(tmp_path, rows, edges={'1m:RSI7': [1, 2, 3, 4]}).coins['BTC']
    t.check_edges(ZONE_LEVELS)
    assert t.problem is None                                # two-state and sign readings need no zone edges
    t = tables(tmp_path / 'b', rows + [pack_row('BTC', '5m:CCI20=high (cooling)', tf='5m', rank=4)], edges={'1m:RSI7': [1, 2, 3, 4]}).coins['BTC']
    t.check_edges(ZONE_LEVELS)
    assert t.problem == 'meta.json has no zone edges for 1 pack row(s), first 5m:CCI20=high (cooling)'


def test_never_doge(tmp_path):
    assert config.parse_assets('btc, DOGE ,eth,doge-usd,DOGEUSDT,BTC') == (['BTC', 'ETH'], ['DOGE', 'DOGE-USD', 'DOGEUSDT'])
    with pytest.raises(config.ConfigError):
        config.parse_assets('DOGE')
    with pytest.raises(config.ConfigError):
        config.parse_assets('BTC,../etc')
    s = config.load(['--assets', 'DOGE,SOL'], env={})
    assert s.assets == ['SOL'] and s.refused == ['DOGE']
    assert config.load([], env={}).assets == ['BTC', 'ETH', 'SOL', 'XRP']
    # DOGE rows in a pack and a DOGE meta on disk are never loaded, even if a caller hands the name in
    rows = [pack_row('DOGE', '1m:RSI7=very low'), pack_row('BTC', '1m:RSI7=very low')]
    pack = write_pack(tmp_path / 'p.json', rows, {'BTC': 'sha-xxxxxxxx', 'DOGE': 'sha-xxxxxxxx'})
    for c in ('BTC', 'DOGE'):
        write_meta(tmp_path, c, {'edges': {'1m:RSI7': [1, 2, 3, 4]}, 'price_step': 0.01, 'table_sha256': 'sha-xxxxxxxx'})
    t = Tables(pack, str(tmp_path), ['BTC', 'DOGE'])
    t.refresh()
    assert list(t.coins) == ['BTC']


def test_tables_reload_when_a_file_changes(tmp_path):
    t = tables(tmp_path, [pack_row('BTC', '1m:RSI7=very low')])
    assert not t.refresh() and len(t.coins['BTC'].rows) == 1 and t.run == '43030435253'
    sha1 = t.pack_sha
    write_pack(tmp_path / 'pack.json', [pack_row('BTC', '1m:RSI7=very low'), pack_row('BTC', '1m:RSI7=very high', rank=2)], {'BTC': 'sha-xxxxxxxx'},
               stamp='tables of run 555000111; pack job 43057668061 at commit c6db27c')
    assert t.refresh() and len(t.coins['BTC'].rows) == 2 and t.pack_sha != sha1 and t.run == '555000111'
    os.unlink(tmp_path / 'pack.json')
    assert t.refresh() and 'cannot be read' in t.problem and t.coins == {} and t.pack_sha == ''
    open(tmp_path / 'pack.json', 'w').write('{"schema": "something-else", "rows": []}')
    assert t.refresh() and 'not of schema oracle-heat-pack-1' in t.problem
    assert Tables(str(tmp_path / 'pack.json'), str(tmp_path / 'meta'), ['BTC'], run='777').run == '777'      # HEAT_RUN wins
