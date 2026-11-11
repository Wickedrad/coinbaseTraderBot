"""The packs, live_meta.json and the join: which rows are published, which fire, and what a fired row looks like to
the bot. The fixtures are trimmed copies of the oracle run's own files (the main packs as at fd88805, the perp packs and
live_meta.json of 52edf4c): real field names, real schemas."""
import hashlib
import json
import os
import shutil

import pytest

from conftest import FIXTURES, pack_row, pair_row, perp_pair, perp_row, write_packs
from heat_reader import config
from heat_reader.engine import join
from heat_reader.pack import (CLOCK_SCHEMA, PAIR_SCHEMA, SKIP_DOMINANCE, SKIP_HASH, SKIP_PARITY, SKIP_PERP_EDGES, SKIP_PERP_H, SKIP_PERP_RUN, SKIP_RANK,
                              SKIP_RUN, SKIP_TWIN, Tables, base_of, call_row, check_pair, effective_rank, indicator_of, key_tf, load_meta, pair_call,
                              parity_off, row_names, tf_minutes)

ZONE_EVENTS = {'very low', 'low (falling in)', 'low (recovering)', 'high (rising in)', 'high (cooling)', 'very high'}
ZONE_STATES = {'very low', 'low', 'mid', 'high', 'very high'}
TS = 1_794_027_600_000
COINS = ['BTC', 'ETH', 'SOL', 'XRP']


def fixture(name):
    return json.load(open(os.path.join(FIXTURES, name)))


def tables(tmp_path, rows, coins=('BTC',), sha=None, meta_sha=None, edges=None, pairs=(), clock=None, perp=None, perp_pairs=(), perp_head=None, **kw):
    """Packs in a folder with a live_meta.json whose edges cover every reading the rows name (or `edges`). perp: rows
    of perp_pack.json (and perp_pairs of perp_pair_pack.json), loaded with the perp packs on."""
    sha = sha or {c: 'sha-xxxxxxxx' for c in coins}
    meta = {}
    for c in coins:
        e = edges
        if e is None:
            names = {k for r in rows + list(perp or []) if r['coin'] == c for k in [r['key']] + r['aliases']}
            names |= {x for p in list(pairs) + list(clock or []) + list(perp_pairs) if p['coin'] == c
                      for x in [p['when']] + [f'{a}=x' for a, _ in p['conds']]}
            e = {base_of(k): [-2.0, -1.0, 1.0, 2.0] for k in names if key_tf(k)}
        meta[c] = {'edges': e, 'price_step': 0.01, 'table_sha256': (meta_sha or sha).get(c), 'no_edges': []}
    folder = write_packs(tmp_path / 'packs', rows, sha, pairs=pairs, meta=meta, clock=clock, perp=perp, perp_pairs=perp_pairs, perp_head=perp_head)
    t = Tables(folder, list(coins), perp=perp is not None, **kw)
    assert t.refresh()
    return t


def res(events, closed=(1,), no_reading=(), bars=None, levels=None, gap_last=False, ts=TS, states=None, tfs=(1, 5, 15)):
    """What engine.read() hands the join: active_keys' answer plus the grid facts."""
    closed = list(closed)
    return {'ts': ts, 'closed': closed, 'events': sorted(events), 'no_reading': list(no_reading), 'gap_last': gap_last,
            'bars': bars or {1: 5000, 5: 3600, 15: 3600, 60: 3600}, 'tfs': list(tfs), 'states': states or {},
            'levels': {f'{k}m:RSI14': 'mid' for k in closed} if levels is None else levels, 'minutes': 5000}


def test_timeframes_in_minutes():
    assert [tf_minutes(x) for x in ('1m', '5m', '15m', '60m', '1h')] == [1, 5, 15, 60, 60]
    for bad in ('', 'm', '0m', '1d', None, 5):
        with pytest.raises(ValueError):
            tf_minutes(bad)
    assert [key_tf(x) for x in ('1m:RSI7=low', '60m:ADX14', '15m:SI sign', 'UTC4h=12-16', 'BTC.D 1d', 'Weekday')] == [1, 60, 15, None, None, None]


def test_a_pack_row_becomes_the_bots_row():
    pack = fixture('traded_pack.json')
    row = next(r for r in pack['rows'] if r['coin'] == 'BTC' and r['h'] == 15 and r['rank_coin'] == 12)
    assert row['key'] == '1m:CMO14=high (rising in)' and row['share_B'] == 53.312 and row['odds_B'] == 3.2534
    got = call_row(row, pack['top'], TS)
    assert got == {'key': '1m:CMO14=high (rising in)', 'kind': 'single', 'aliases': ['1m:RSI14=high (rising in)'], 'tf': 1, 'h': 15,
                   'dir': -1, 'rank': 12, 'of': 40, 'heat': 94.102, 'share': 0.53312, 'odds': 3.2534, 'hold': 8.1777, 'dip': -6.2447,
                   'move': 0.3139, 'barClose': TS}
    for r in pack['rows']:                       # every row of the trimmed real pack maps, on its own timeframe
        c = call_row(r, pack['top'], TS)
        assert 0 < c['share'] < 1 and c['tf'] in (1, 5, 15, 60) and c['key'].startswith(f"{c['tf']}m:") and c['dir'] in (1, -1) and c['of'] == 40
    assert 'hold' not in call_row(pack_row('BTC', '1m:RSI14=very low', hold_B=None), 40, TS)


def test_a_pair_row_becomes_the_bots_row():
    pairs = fixture('pair_pack.json')
    row = next(r for r in pairs['rows'] if r['key'] == '1m:AROONdn14=very high | 1m:AD sign=below 0')
    p = check_pair(row, 40, PAIR_SCHEMA)
    assert p['kind'] == 'pair' and p['when'] == '1m:AROONdn14=very high' and p['conds'] == [('1m:AD sign', 'below 0')] and p['tf'] == 1
    assert pair_call(p, 1, 40, TS) == {'key': '1m:AROONdn14=very high | 1m:AD sign=below 0', 'kind': 'pair', 'aliases': [], 'trig': '1m:AROONdn14=very high',
                                      'tf': 1, 'h': 15, 'dir': 1, 'rank': 1, 'of': 40, 'heat': 128.5824, 'share': 0.52406, 'odds': 2.5439,
                                      'hold': 8.2894, 'dip': -6.5716, 'move': 0.6781, 'barClose': TS}
    tri = check_pair(next(r for r in pairs['rows'] if r['kind'] == 'triple' and r['coin'] == 'BTC'), 40, PAIR_SCHEMA)
    assert tri['conds'] == [('5m:ERIbull13 sign', 'above 0'), ('1m:PVT sign', 'above 0')] and tri['when'] == '1m:RSI2=high (rising in)'
    # a context trigger has no bars of its own: it fires at 15-minute closes, so its rows are on 15
    ctx = check_pair(next(r for r in pairs['rows'] if r['when'] == 'UTC4h=12-16'), 40, PAIR_SCHEMA)
    assert ctx['tf'] == 15 and pair_call(ctx, 7, 40, TS)['trig'] == 'UTC4h=12-16'
    # pair aliases are other pair keys of the same event: carried as they are
    al = next(r for r in pairs['rows'] if r['coin'] == 'BTC' and r['aliases'])
    assert pair_call(check_pair(al, 40, PAIR_SCHEMA), 5, 40, TS)['aliases'] == ['1m:RSI14=high (rising in) | 1m:SWAK_2PHP20 sign=above 0']


@pytest.mark.parametrize('field,value', [('dir', 0), ('dir', True), ('share_B', 120.0), ('share_B', float('nan')), ('odds_B', None),
                                         ('oheat_B', 'hot'), ('rank_coin', 0), ('h', 0), ('h', 7.5), ('tf', '5m'), ('tf', '1d'),
                                         ('aliases', 'x'), ('key', ''), ('dip_B', float('inf'))])
def test_a_row_the_bot_must_not_trade_from_is_refused(field, value):
    row = pack_row('BTC', '1m:RSI14=very low')
    assert call_row(row, 40, TS)['key'] == '1m:RSI14=very low'
    row[field] = value
    with pytest.raises(ValueError):
        call_row(row, 40, TS)


@pytest.mark.parametrize('field,value', [('kind', 'quad'), ('conds', []), ('conds', [['1m:AD sign']]), ('conds', [['1m:AD sign', 'below 0'], ['5m:X', 'up']]),
                                         ('when', ''), ('when', 'no level'), ('key', None), ('dir', 2), ('share_B', 101), ('odds_B', 'x'), ('h', -15)])
def test_a_pair_row_the_bot_must_not_trade_from_is_refused(tmp_path, field, value):
    row = pair_row('BTC', '1m:RSI7=very low', [('1m:AD sign', 'below 0')])
    assert check_pair(row, 40, PAIR_SCHEMA)['kind'] == 'pair'
    row[field] = value
    with pytest.raises(ValueError):
        check_pair(row, 40, PAIR_SCHEMA)
    # in the packs, such a row refuses its coin (it may be the pair that should replace a single), not the others
    t = tables(tmp_path, [pack_row('BTC', '1m:RSI7=very low'), pack_row('ETH', '1m:RSI7=very low')], coins=('BTC', 'ETH'), pairs=[row], edges={})
    assert t.coins['BTC'].problem.startswith('pair_pack.json row 1 of this coin') and t.coins['ETH'].problem is None
    with pytest.raises(ValueError, match='clock'):
        check_pair(pair_row('BTC', '1m:RSI7=very low', [('1m:AD sign', 'below 0')]), 40, CLOCK_SCHEMA)


def test_the_real_packs_load_per_coin():
    t = Tables(FIXTURES, COINS)
    assert t.refresh()
    assert t.problem is None and t.top == 40 and t.run == '43030435253'
    assert t.pack_sha == hashlib.sha256(open(os.path.join(FIXTURES, 'traded_pack.json'), 'rb').read()).hexdigest()
    assert sorted(t.files) == ['live_meta.json', 'pair_pack.json', 'traded_pack.json']          # no clock pack unless asked for
    assert t.files['pair_pack.json']['schema'] == 'oracle-heat-pairs-1' and t.files['live_meta.json']['coins'] == 4
    for x in t.coins.values():
        x.check_edges(ZONE_EVENTS, ZONE_STATES)
    assert {c: x.problem for c, x in t.coins.items()} == dict.fromkeys(COINS)
    assert {c: x.counts() for c, x in t.coins.items()} == {
        'BTC': {'wanted': {'single': 16, 'pair': 8, 'triple': 1, 'clock': 0}, 'skipped': {SKIP_DOMINANCE: 1, SKIP_PARITY: 1, SKIP_RANK: 2}},
        'ETH': {'wanted': {'single': 12, 'pair': 8, 'triple': 1, 'clock': 0}, 'skipped': {SKIP_DOMINANCE: 1, SKIP_PARITY: 1, SKIP_RANK: 2}},
        'SOL': {'wanted': {'single': 12, 'pair': 7, 'triple': 0, 'clock': 0}, 'skipped': {SKIP_DOMINANCE: 1, SKIP_PARITY: 4, SKIP_RANK: 2}},
        'XRP': {'wanted': {'single': 12, 'pair': 7, 'triple': 1, 'clock': 0}, 'skipped': {SKIP_DOMINANCE: 1, SKIP_PARITY: 1, SKIP_RANK: 2}}}
    btc, sol = t.coins['BTC'], t.coins['SOL']
    assert all(r['rank_coin'] <= 40 for r in btc.rows) and not any(r['tf'] == '60m' for r in btc.rows)   # the share-only rows stay out
    assert '1m:RSI14=high (rising in)' in btc.want and '1m:CMO14=high (rising in)' in btc.want           # an alias is asked for too
    assert '1m:RSI2=high (rising in)' in btc.want                                                         # a pair's trigger is asked for
    assert btc.tfs == [1, 5, 15, 60] and btc.long_states == {'60m:CTI20 sign'} and t.coins['XRP'].long_states == set()
    assert 'UTC4h=12-16' in sol.want and '60m:HT_TRENDMODE' in sol.states and not any('PVI' in k for k in sol.want)   # PVI: live_parity false
    assert btc.table_sha == fixture('traded_pack.json')['table_sha256']['BTC'] == btc.meta['table_sha256']
    need = {base_of(k) for k in btc.want | btc.states if key_tf(k)}
    assert set(btc.meta['edges']) == need & set(fixture('live_meta.json')['BTC']['edges'])               # only the readings the rows need
    # dominance rows never reach the join; neither do rows the parity check marked
    assert not any(p['row']['dominance'] for x in t.coins.values() for p in x.pairs)
    assert not any(p['row']['live_parity'] is False for x in t.coins.values() for p in x.pairs)


def test_effective_rank_on_the_single_ladder():
    assert effective_rank(130.0, [123.75, 115.0, 110.0]) == 1 and effective_rank(112.0, [123.75, 115.0, 110.0]) == 3
    assert effective_rank(115.0, [123.75, 115.0, 110.0]) == 2                     # a tie is not hotter
    assert effective_rank(1.0, [50.0] * 40) == 41 and effective_rank(5.0, []) == 1
    t = Tables(FIXTURES, ['BTC'])
    t.refresh()
    ranks = {(p['h'], p['key']): p['rank'] for p in t.coins['BTC'].pairs}
    # BTC 15 in the trimmed pack: singles at 123.75, 115.85, 110.38, 108.78 ... a pair hotter than all is 1
    assert ranks[(15, '1m:AROONdn14=very high | 1m:AD sign=below 0')] == 1
    assert ranks[(15, '1m:RSI2=high (rising in) | 5m:ERIbull13 sign=above 0 | 1m:PVT sign=above 0')] == 4      # 109.90: three hotter
    assert ranks[(15, '1m:RSI2=high (rising in) | 15m:SWAK_HP20 sign=above 0')] == 5                          # 102.51: four hotter
    assert ranks[(60, '1m:AROONup14=very high | 60m:CTI20 sign=above 0')] == 1                                # the 60 ladder is its own
    # HEAT_READER_MAX_RANK hides singles, not the ladder: the pairs keep their places
    t3 = Tables(FIXTURES, ['BTC'], max_rank=3)
    t3.refresh()
    assert {(p['h'], p['key']): p['rank'] for p in t3.coins['BTC'].pairs} == ranks
    assert sorted(r['rank_coin'] for r in t3.coins['BTC'].rows) == [1, 1, 2, 2, 3, 3]
    assert t3.coins['BTC'].counts()['skipped'][SKIP_RANK] == 12


def test_the_clock_pack_only_when_asked_and_only_above_the_twin(tmp_path):
    t = Tables(FIXTURES, COINS, clock=True)
    t.refresh()
    assert t.problem is None and t.files['clock_pack.json']['schema'] == 'oracle-heat-clock-pack-1'
    assert {c: (x.counts()['wanted']['clock'], x.counts()['skipped'].get(SKIP_TWIN)) for c, x in t.coins.items()} == \
        {'BTC': (2, 2), 'ETH': (2, 2), 'SOL': (1, 2), 'XRP': (0, 2)}
    clock = [p for p in t.coins['BTC'].pairs if p['conds'][0][0] == 'Weekday']
    assert [(p['key'], p['rank'], p['tf']) for p in clock] == [('1m:STOCHK5=low (falling in) | Weekday=Wed', 9, 1),
                                                              ('1m:C-CKSPmid=low (falling in) | Weekday=Wed', 9, 1)]
    assert 'Weekday' in t.coins['BTC'].states and pair_call(clock[0], 9, 40, TS)['kind'] == 'pair'
    # off (the default): the file is not even read, so a missing one is no problem
    os.makedirs(tmp_path / 'p')
    for name in ('traded_pack.json', 'pair_pack.json', 'live_meta.json'):
        open(tmp_path / 'p' / name, 'w').write(open(os.path.join(FIXTURES, name)).read())
    off = Tables(str(tmp_path / 'p'), COINS)
    off.refresh()
    assert off.problem is None and 'Weekday' not in off.coins['BTC'].states
    on = Tables(str(tmp_path / 'p'), COINS, clock=True)
    on.refresh()
    assert on.problem == f'clock_pack.json cannot be read in {tmp_path / "p"} (FileNotFoundError)' and on.coins == {}
    # a clock pack of another run, or rows of another clock table, are not published
    cp = fixture('clock_pack.json')
    json.dump(dict(cp, stamp=cp['stamp'].replace('43030435253', '555000111')), open(tmp_path / 'p' / 'clock_pack.json', 'w'))
    assert on.refresh() and on.coins['BTC'].counts()['skipped'][SKIP_RUN] == 4 and on.coins['BTC'].counts()['wanted']['clock'] == 0
    cp['rows'][0]['table_sha256'] = 'f' * 64
    json.dump(cp, open(tmp_path / 'p' / 'clock_pack.json', 'w'))
    assert on.refresh() and on.coins['BTC'].counts()['skipped'][SKIP_HASH] == 1 and on.coins['BTC'].counts()['wanted']['clock'] == 1


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


def test_the_pair_fire_rule(tmp_path):
    """when fires now AND every condition holds its level at its own last closed bar; a triple needs both."""
    single = pack_row('BTC', '1m:RSI7=very low', rank=2, aliases=['1m:CMO7=very low'])
    pairs = [pair_row('BTC', '1m:RSI7=very low', [('5m:MOM10 sign', 'above 0')], oheat=120.0),
             pair_row('BTC', '1m:RSI7=very low', [('60m:ADX14', 'high'), ('15m:Ichimoku', 'above cloud')], oheat=90.0, direction=-1),
             pair_row('BTC', '5m:WILLR14=very high', [('1m:AD sign', 'below 0')], oheat=99.0),                 # its trigger is no single
             pair_row('BTC', 'UTC4h=12-16', [('1m:AD sign', 'below 0')], oheat=40.0),
             pair_row('BTC', '1m:RSI7=very low', [('1m:AD sign', 'below 0')], oheat=200.0, dominance=True),
             pair_row('BTC', '1m:RSI7=very low', [('BTC.D 1d', 'up')], oheat=200.0)]                              # dominance by name
    rows = [single, pack_row('BTC', '1m:X=very high', rank=1)]
    t = tables(tmp_path, rows, pairs=pairs).coins['BTC']
    assert t.counts()['skipped'] == {SKIP_DOMINANCE: 2} and t.counts()['wanted'] == {'single': 2, 'pair': 3, 'triple': 1, 'clock': 0}
    assert [p['rank'] for p in t.pairs] == [1, 3, 1, 3]              # singles at 99 and 98: 120 beats both, 90 neither, 99 ties (not hotter)
    held = {'5m:MOM10 sign': 'above 0', '60m:ADX14': 'high', '15m:Ichimoku': 'above cloud', '1m:AD sign': 'below 0'}
    r = res({'1m:CMO7=very low'}, closed=(1,), states=held)                            # the trigger fires through its alias
    calls, problem, _ = join(t, 40, r, 3000)
    assert problem is None
    assert [(c['kind'], c['rank'], c['key']) for c in calls] == [
        ('pair', 1, '1m:RSI7=very low | 5m:MOM10 sign=above 0'), ('single', 2, '1m:RSI7=very low'),
        ('triple', 3, '1m:RSI7=very low | 60m:ADX14=high | 15m:Ichimoku=above cloud')]
    assert all(c['trig'] == '1m:RSI7=very low' for c in calls if c['kind'] != 'single') and calls[2]['dir'] == -1
    # one condition of the triple does not hold, or has no reading: only the pair is left
    for st in (dict(held, **{'15m:Ichimoku': 'below cloud'}), dict(held, **{'60m:ADX14': None}), {k: v for k, v in held.items() if k != '60m:ADX14'}):
        got = [c['kind'] for c in join(t, 40, res({'1m:RSI7=very low'}, states=st), 3000)[0]]
        assert got == ['pair', 'single']
    # a condition on a timeframe with fewer bars than the window is not trusted
    got = join(t, 40, res({'1m:RSI7=very low'}, states=held, bars={1: 5000, 5: 2000, 15: 3600, 60: 3600}), 3000)
    assert [c['kind'] for c in got[0]] == ['single', 'triple'] and got[2] == ['only 2000 of 3000 5-minute bars are loaded']
    # the trigger fires but the conditions do not hold: the single alone
    assert [c['kind'] for c in join(t, 40, res({'1m:RSI7=very low'}, states={}), 3000)[0]] == ['single']
    # a 5-minute trigger needs its bar to close now; a context trigger fires whenever the engine sends it (15-minute closes)
    assert [c['key'] for c in join(t, 40, res({'5m:WILLR14=very high'}, closed=(1,), states=held), 3000)[0]] == []
    assert [c['trig'] for c in join(t, 40, res({'5m:WILLR14=very high'}, closed=(1, 5), states=held), 3000)[0]] == ['5m:WILLR14=very high']
    ctx = join(t, 40, res({'UTC4h=12-16'}, closed=(1, 5, 15), states=held), 3000)[0]
    assert [(c['key'], c['tf'], c['rank']) for c in ctx] == [('UTC4h=12-16 | 1m:AD sign=below 0', 15, 3)]


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


def test_rows_the_parity_check_marked_are_never_published(tmp_path):
    rows = [pack_row('SOL', '1m:PVI=high (rising in)', rank=6, live_parity=False), pack_row('SOL', '1m:RSI7=very low', rank=9, live_parity=True),
            pack_row('SOL', '1m:RSI2=very low', rank=10)]
    pairs = [pair_row('SOL', '1m:RSI7=very low', [('5m:PVI sign', 'below 0')], live_parity=False)]
    t = tables(tmp_path, rows, coins=('SOL',), pairs=pairs).coins['SOL']
    assert t.counts()['skipped'] == {SKIP_PARITY: 2} and '1m:PVI=high (rising in)' not in t.want and '5m:PVI sign' not in t.states
    calls, problem, _ = join(t, 40, res({'1m:PVI=high (rising in)', '1m:RSI7=very low'}, states={'5m:PVI sign': 'below 0'}), 3000)
    assert problem is None and [c['key'] for c in calls] == ['1m:RSI7=very low']


def test_table_hash_mismatch_refuses_the_coin(tmp_path):
    rows = [pack_row('BTC', '1m:RSI7=very low', sha='aaa'), pack_row('ETH', '1m:RSI7=very low', sha='bbb')]
    t = tables(tmp_path, rows, coins=('BTC', 'ETH'), sha={'BTC': 'aaa', 'ETH': 'bbb'}, meta_sha={'BTC': 'aaa', 'ETH': 'ccc'})
    assert t.problem is None and t.coins['BTC'].problem is None and t.coins['BTC'].meta is not None
    assert t.coins['ETH'].problem == 'table hash differs: the pack is of table bbb, live_meta.json of table ccc'
    assert t.coins['ETH'].meta is None and t.coins['ETH'].table_sha == 'bbb'
    # a row that carries another table's hash than its coin's
    t = tables(tmp_path / 'b', [pack_row('BTC', '1m:RSI7=very low', sha='zzz')], sha={'BTC': 'aaa'})
    assert 'table hash' in t.coins['BTC'].problem
    # the pack names no hash for the coin: nothing to compare with
    t = tables(tmp_path / 'c', [pack_row('BTC', '1m:RSI7=very low')], sha={'ETH': 'x'})
    assert 'no table hash' in t.coins['BTC'].problem and t.coins['BTC'].table_sha == ''
    # a pair row of another table than the traded pack's is left out and counted; the coin's singles stay
    pairs = [pair_row('BTC', '1m:RSI7=very low', [('1m:AD sign', 'below 0')], sha='aaa'), pair_row('BTC', '1m:RSI7=very low', [('1m:OBV sign', 'below 0')], sha='old')]
    t = tables(tmp_path / 'd', [pack_row('BTC', '1m:RSI7=very low', sha='aaa')], sha={'BTC': 'aaa'}, pairs=pairs)
    assert t.coins['BTC'].problem is None and t.coins['BTC'].counts() == {'wanted': {'single': 1, 'pair': 1, 'triple': 0, 'clock': 0}, 'skipped': {SKIP_HASH: 1}}


def test_live_meta(tmp_path):
    slim = {'BTC': {'price_step': 0.01, 'table_sha256': 'aaa', 'edges': {'1m:RSI7': [1, 2, 3, 4]}, 'no_edges': []}}
    assert load_meta(slim, 'BTC')['table_sha256'] == 'aaa'
    with pytest.raises(ValueError, match='live_meta.json has no entry for ETH'):
        load_meta(slim, 'ETH')
    with pytest.raises(ValueError, match='no zone edges'):
        load_meta({'BTC': {'price_step': 0.5}}, 'BTC')
    folder = write_packs(tmp_path / 'p', [pack_row('BTC', '1m:RSI7=very low', sha='aaa'), pack_row('XRP', '1m:RSI7=very low', sha='x')],
                         {'BTC': 'aaa', 'XRP': 'x'}, meta=slim)
    t = Tables(folder, ['BTC', 'XRP', 'SOL'])
    t.refresh()
    assert t.coins['BTC'].problem is None and t.coins['BTC'].meta['edges'] == {'1m:RSI7': [1, 2, 3, 4]}
    assert t.coins['XRP'].problem == 'live_meta.json has no entry for XRP' and t.coins['SOL'].problem == 'traded_pack.json has no rows for this coin'
    open(os.path.join(folder, 'live_meta.json'), 'w').write('{not json')
    assert t.refresh() and t.problem == 'live_meta.json is not JSON' and t.coins == {}


def test_missing_zone_edges_refuse_the_coin(tmp_path):
    rows = [pack_row('BTC', '1m:RSI7=very low'), pack_row('BTC', '1m:KVO>sig=below', rank=2), pack_row('BTC', '1m:MOM10 sign=above 0', rank=3)]
    t = tables(tmp_path, rows, edges={'1m:RSI7': [1, 2, 3, 4]}).coins['BTC']
    t.check_edges(ZONE_EVENTS, ZONE_STATES)
    assert t.problem is None                                # two-state and sign readings need no zone edges
    t = tables(tmp_path / 'b', rows + [pack_row('BTC', '5m:CCI20=high (cooling)', tf='5m', rank=4)], edges={'1m:RSI7': [1, 2, 3, 4]}).coins['BTC']
    t.check_edges(ZONE_EVENTS, ZONE_STATES)
    assert t.problem == 'live_meta.json has no zone edges for 1 row(s), first 5m:CCI20=high (cooling)'
    # a pair's zone condition needs edges too ('high' is a zone level); a level of a reading the meta lists as having
    # no edges is a condition reading's own level and needs none
    pairs = [pair_row('BTC', '1m:RSI7=very low', [('60m:ADX14', 'high')]), pair_row('BTC', '1m:RSI7=very low', [('15m:Ichimoku', 'above cloud')])]
    t = tables(tmp_path / 'c', rows, pairs=pairs, edges={'1m:RSI7': [1, 2, 3, 4]}).coins['BTC']
    t.check_edges(ZONE_EVENTS, ZONE_STATES)
    assert t.problem == 'live_meta.json has no zone edges for 1 row(s), first 60m:ADX14=high'
    t.problem, t.meta['no_edges'] = None, ['60m:ADX14']
    t.check_edges(ZONE_EVENTS, ZONE_STATES)
    assert t.problem is None


def test_never_doge(tmp_path):
    assert config.parse_assets('btc, DOGE ,eth,doge-usd,DOGEUSDT,BTC') == (['BTC', 'ETH'], ['DOGE', 'DOGE-USD', 'DOGEUSDT'])
    with pytest.raises(config.ConfigError):
        config.parse_assets('DOGE')
    with pytest.raises(config.ConfigError):
        config.parse_assets('BTC,../etc')
    s = config.load(['--assets', 'DOGE,SOL'], env={})
    assert s.assets == ['SOL'] and s.refused == ['DOGE']
    assert config.load([], env={}).assets == ['BTC', 'ETH', 'SOL', 'XRP']
    # DOGE rows in a pack and a DOGE meta are never loaded, even if a caller hands the name in
    rows = [pack_row('DOGE', '1m:RSI7=very low'), pack_row('BTC', '1m:RSI7=very low')]
    t = tables(tmp_path, rows, coins=('BTC', 'DOGE'))
    assert list(t.coins) == ['BTC']
    # nor DOGE rows of the perp packs; and the perp fixtures hold none
    t = tables(tmp_path / 'perp', rows, coins=('BTC', 'DOGE'), perp=[perp_row('DOGE', '1m:MFI14=very low'), perp_row('BTC', '1m:MFI14=very low')],
               perp_pairs=[perp_pair('DOGE', '1m:MFI14=very low', [('1m:AD sign', 'below 0')])])
    assert list(t.coins) == ['BTC'] and [r['coin'] for r in t.coins['BTC'].perp_rows] == ['BTC'] and t.coins['BTC'].perp_pairs == []
    for name in ('perp_pack.json', 'perp_pair_pack.json'):
        pk = fixture(name)
        assert {r['coin'] for r in pk['rows']} == set(COINS) and not any('DOGE' in c.upper() for c in pk['table_sha256'])


def test_settings():
    s = config.load([], env={})
    assert s.pack_dir == os.path.join(config.REPO_DIR, 'research', 'oracle_heat', 'latest') and s.oracle_path == config.PYTHON_DIR
    assert s.max_rank == 40 and s.clock_pack is False and s.perp_packs is True
    s = config.load(['--max-rank', '10'], env={'HEAT_CLOCK_PACK': 'true', 'HEAT_PACK_DIR': '/x/packs', 'HEAT_READER_MAX_RANK': '25', 'HEAT_PERP_PACKS': 'false'})
    assert s.max_rank == 10 and s.clock_pack is True and s.pack_dir == '/x/packs' and s.perp_packs is False
    assert config.load(['--perp-packs', 'on'], env={'HEAT_PERP_PACKS': 'off'}).perp_packs is True          # the flag wins
    for env, text in (({'HEAT_READER_MAX_RANK': '0'}, 'is below 1'), ({'HEAT_READER_MAX_RANK': 'all'}, 'not a whole number'),
                      ({'HEAT_CLOCK_PACK': 'maybe'}, 'neither true nor false'), ({'HEAT_PERP_PACKS': 'entry'}, 'HEAT_PERP_PACKS')):
        with pytest.raises(config.ConfigError, match=text):
            config.load([], env=env)
    assert config.status_path('/d/heat_calls.json') == '/d/heat_calls.status.json' and config.status_path('/d/calls') == '/d/calls.status.json'


def test_tables_reload_when_a_file_changes(tmp_path):
    t = tables(tmp_path, [pack_row('BTC', '1m:RSI7=very low')])
    assert not t.refresh() and len(t.coins['BTC'].rows) == 1 and t.run == '43030435253'
    sha1 = t.pack_sha
    folder = t.pack_dir
    write_packs(folder, [pack_row('BTC', '1m:RSI7=very low'), pack_row('BTC', '1m:RSI7=very high', rank=2)], {'BTC': 'sha-xxxxxxxx'},
                stamp='tables of run 555000111; pack job 43057668061 at commit c6db27c')
    assert t.refresh() and len(t.coins['BTC'].rows) == 2 and t.pack_sha != sha1 and t.run == '555000111'
    # a new pair pack alone is a change too
    write_packs(folder, [pack_row('BTC', '1m:RSI7=very low')], {'BTC': 'sha-xxxxxxxx'}, pairs=[pair_row('BTC', '1m:RSI7=very low', [('1m:AD sign', 'below 0')])])
    assert t.refresh() and len(t.coins['BTC'].pairs) == 1
    os.unlink(os.path.join(folder, 'traded_pack.json'))
    assert t.refresh() and 'traded_pack.json cannot be read' in t.problem and t.coins == {} and t.pack_sha == ''
    open(os.path.join(folder, 'traded_pack.json'), 'w').write('{"schema": "something-else", "rows": []}')
    assert t.refresh() and t.problem == 'traded_pack.json is not of schema oracle-heat-pack-1'
    write_packs(folder, [pack_row('BTC', '1m:RSI7=very low')], {'BTC': 'sha-xxxxxxxx'})
    open(os.path.join(folder, 'pair_pack.json'), 'w').write('{"schema": "oracle-heat-pack-1", "rows": []}')
    assert t.refresh() and t.problem == 'pair_pack.json is not of schema oracle-heat-pairs-1'          # no pairs, no coin: they change the bet
    assert Tables(folder, ['BTC'], run='777').run == '777'      # HEAT_RUN wins


PERP_FILES = ['live_meta.json', 'pair_pack.json', 'perp_pack.json', 'perp_pair_pack.json', 'traded_pack.json']


def test_the_real_perp_packs():
    """perp_pack.json and perp_pair_pack.json (52edf4c, trimmed): loaded only with perp on, h240 and h1440 rows on their
    own ladders with of = the perp pack's top, and the main rows exactly as without them."""
    off, on = Tables(FIXTURES, COINS), Tables(FIXTURES, COINS, perp=True)
    assert off.refresh() and on.refresh() and on.problem is None and on.perp_problem is None and off.perp_problem is None
    assert sorted(on.files) == PERP_FILES and on.files['perp_pack.json']['schema'] == 'oracle-heat-pack-1'
    assert on.files['perp_pair_pack.json']['schema'] == 'oracle-heat-pairs-1' and on.files['perp_pack.json']['rows'] == 44
    assert not any(x.perp_rows or x.perp_pairs or 'perp' in x.counts() for x in off.coins.values())
    for x in on.coins.values():
        x.check_edges(ZONE_EVENTS, ZONE_STATES)
    assert {c: x.problem for c, x in on.coins.items()} == dict.fromkeys(COINS)
    for c in COINS:                                         # the main rows do not change with the perp packs
        a, b = off.coins[c], on.coins[c]
        assert a.rows == b.rows and [p['key'] for p in a.pairs] == [p['key'] for p in b.pairs] and a.aliases == b.aliases
        assert a.counts() == {k: v for k, v in b.counts().items() if k != 'perp'} and a.want <= b.want and a.states <= b.states
    assert {c: x.counts()['perp'] for c, x in on.coins.items()} == {
        'BTC': {'wanted': {'single': 8, 'pair': 3, 'triple': 2}, 'skipped': {SKIP_PARITY: 3, SKIP_RANK: 2}},
        'ETH': {'wanted': {'single': 9, 'pair': 4, 'triple': 2}, 'skipped': {SKIP_PARITY: 2, SKIP_RANK: 2}},
        'SOL': {'wanted': {'single': 9, 'pair': 3, 'triple': 1}, 'skipped': {SKIP_PARITY: 2, SKIP_RANK: 2}},
        'XRP': {'wanted': {'single': 7, 'pair': 2, 'triple': 2}, 'skipped': {SKIP_PARITY: 1, SKIP_RANK: 2}}}
    btc = on.coins['BTC']
    assert {r['h'] for r in btc.perp_rows} == {p['h'] for p in btc.perp_pairs} == {240, 1440} and btc.perp_top == 40
    assert all(r['rank_coin'] <= 40 for x in on.coins.values() for r in x.perp_rows)
    # no row on PVI (live_parity false in the main packs) is asked for, whether by key, trigger or condition
    assert not any(indicator_of(n) == 'PVI' for x in on.coins.values() for r in x.perp_rows + [p['row'] for p in x.perp_pairs] for n in row_names(r))
    assert not any('PVI' in k for x in on.coins.values() for k in x.want | x.states)
    # 60-minute singles at h1440: XRP, which reads no 60-minute timeframe for h15 and h60, now does
    assert off.coins['XRP'].tfs == [1, 5, 15] and on.coins['XRP'].tfs == [1, 5, 15, 60] and '60m:ERIbear13 sign=above 0' in on.coins['XRP'].want
    # a perp pair's rank is on the perp singles' ladder of its horizon (rank_coin up to the top, a parity-skipped one included)
    ranks = {(p['h'], p['key']): p['rank'] for p in btc.perp_pairs}
    assert ranks[(240, '1m:AROONup25=very high | 1m:PVO12/26 sign=above 0 | 60m:SQZMOM sign=above 0')] == 1      # 20.80 over 18.01
    assert ranks[(1440, 'UTC4h=16-20 | 15m:ADOSC sign=below 0')] == 6     # 3.70: five singles hotter, the PVI one at 4.82 among them
    assert next(p for p in btc.perp_pairs if p['when'] == 'UTC4h=16-20')['tf'] == 15                    # a context trigger: 15-minute closes
    # what fires: h15 and h60 from the main packs, h240 and h1440 from the perp packs, each row once per horizon
    ev = {'1m:MFI14=very low', '1m:AROONup25=very high', '60m:C-AVGPRICE=high (rising in)', '1m:RSI14=very low'}
    held = {'1m:PVO12/26 sign': 'above 0', '60m:SQZMOM sign': 'above 0'}
    calls, problem, notes = join(btc, 40, res(ev, closed=(1, 5, 15, 60), states=held), 3000)
    assert problem is None and notes == []
    assert [(c['h'], c['rank'], c['kind'], c['key'], c['of']) for c in calls] == [
        (15, 2, 'single', '1m:AROONup25=very high', 40), (60, 9, 'single', '1m:AROONup25=very high', 40),
        (240, 1, 'single', '1m:MFI14=very low', 40),
        (240, 1, 'triple', '1m:AROONup25=very high | 1m:PVO12/26 sign=above 0 | 60m:SQZMOM sign=above 0', 40),
        (240, 30, 'single', '1m:CMO14=very low', 40),                                                    # through its alias 1m:RSI14
        (1440, 9, 'single', '60m:C-AVGPRICE=high (rising in)', 40)]                                     # a 60-minute single at the hourly close
    assert calls[2] == {'key': '1m:MFI14=very low', 'kind': 'single', 'aliases': [], 'tf': 1, 'h': 240, 'dir': 1, 'rank': 1, 'of': 40, 'heat': 18.013,
                        'share': 0.54442, 'odds': 3.4784, 'hold': 49.514, 'dip': -25.268, 'move': 1.3351, 'barClose': TS}
    assert calls[3]['trig'] == '1m:AROONup25=very high' and calls[3]['dir'] == -1 and calls[3]['heat'] == 20.8012 and calls[3]['share'] == 0.55198
    # the 60-minute bar did not close: the h1440 single cannot fire
    assert '60m:C-AVGPRICE=high (rising in)' not in [c['key'] for c in join(btc, 40, res(ev, closed=(1, 5), states=held), 3000)[0]]


def test_missing_perp_packs_leave_the_main_rows_alone(tmp_path):
    p = tmp_path / 'p'
    os.makedirs(p)
    for name in ('traded_pack.json', 'pair_pack.json', 'live_meta.json'):
        shutil.copy(os.path.join(FIXTURES, name), p / name)
    main = Tables(FIXTURES, COINS)
    main.refresh()
    t = Tables(str(p), COINS, perp=True)
    assert t.refresh() and t.problem is None and t.perp_problem == f'perp_pack.json cannot be read in {p} (FileNotFoundError)'
    assert sorted(t.files) == ['live_meta.json', 'pair_pack.json', 'traded_pack.json']
    assert {c: x.counts() for c, x in t.coins.items()} == {c: x.counts() for c, x in main.coins.items()}
    assert all(x.perp is None and x.perp_rows == x.perp_pairs == [] and x.tfs == main.coins[c].tfs for c, x in t.coins.items())
    # the pairs refine the singles, so one file without the other is not used either
    shutil.copy(os.path.join(FIXTURES, 'perp_pack.json'), p / 'perp_pack.json')
    assert t.refresh() and t.perp_problem == f'perp_pair_pack.json cannot be read in {p} (FileNotFoundError)' and 'perp_pack.json' not in t.files
    open(p / 'perp_pair_pack.json', 'w').write('{"schema": "oracle-heat-pack-1", "rows": []}')
    assert t.refresh() and t.perp_problem == 'perp_pair_pack.json is not of schema oracle-heat-pairs-1' and t.problem is None
    shutil.copy(os.path.join(FIXTURES, 'perp_pair_pack.json'), p / 'perp_pair_pack.json')
    assert t.refresh() and t.perp_problem is None and sorted(t.files) == PERP_FILES and len(t.coins['BTC'].perp_rows) == 8
    pk = fixture('perp_pack.json')
    json.dump(dict(pk, top=0), open(p / 'perp_pack.json', 'w'))
    assert t.refresh() and t.perp_problem == 'perp_pack.json has no `top`' and all(x.problem is None and x.rows for x in t.coins.values())
    open(p / 'perp_pack.json', 'w').write('{not json')
    assert t.refresh() and t.perp_problem == 'perp_pack.json is not JSON' and t.problem is None
    # with perp off the files are not even looked at
    assert Tables(str(p), COINS).refresh() is True


def test_perp_rows_fire_with_their_horizon(tmp_path):
    """Synthetic perp packs with a `top` of 30: of is the perp pack's top, ranks are on each horizon's own ladder, a
    pair on 240 fires when its trigger fires and its conditions hold, and an event of a main single at h15 is a second
    row at h240 (another horizon, another bet)."""
    rows = [pack_row('BTC', '1m:RSI7=very low', h=15, rank=1), pack_row('BTC', '1m:X=very high', h=60, rank=1)]
    perp = [perp_row('BTC', '1m:RSI7=very low', rank=2, oheat_B=17.0),
            perp_row('BTC', '1m:MFI14=very low', rank=1, oheat_B=18.0, aliases=['1m:MFIX=very low']),
            perp_row('BTC', '5m:WAD=low (falling in)', rank=3, tf='5m', oheat_B=12.0),
            perp_row('BTC', '60m:C-AVGPRICE=high (rising in)', h=1440, rank=1, tf='60m', oheat_B=6.9, direction=-1),
            perp_row('BTC', '1m:Y=very low', h=1440, rank=41, oheat_B=9.0)]                              # share-only: never asked for
    pp = [perp_pair('BTC', '1m:MFI14=very low', [('60m:SQZMOM sign', 'above 0')], oheat=17.5),                 # 18.0 is hotter: rank 2
          perp_pair('BTC', '1m:MFI14=very low', [('1m:PVO12/26 sign', 'above 0'), ('60m:SQZMOM sign', 'above 0')], oheat=20.0),
          perp_pair('BTC', '1m:MFI14=very low', [('60m:SQZMOM sign', 'below 0')], oheat=30.0),                 # its condition does not hold
          perp_pair('BTC', '1m:RSI7=very low', [('5m:MOM10 sign', 'above 0')], h=1440, oheat=5.0)]             # the h1440 ladder: 6.9 hotter
    t = tables(tmp_path, rows, perp=perp, perp_pairs=pp, perp_head={'top': 30}).coins['BTC']
    assert t.counts()['perp'] == {'wanted': {'single': 4, 'pair': 3, 'triple': 1}, 'skipped': {SKIP_RANK: 1}} and t.perp_top == 30
    assert [p['rank'] for p in t.perp_pairs] == [2, 1, 1, 2] and t.tfs == [1, 5, 60] and '60m:SQZMOM sign' in t.long_states
    held = {'60m:SQZMOM sign': 'above 0', '1m:PVO12/26 sign': 'above 0', '5m:MOM10 sign': 'above 0'}
    calls, problem, _ = join(t, 40, res({'1m:MFIX=very low', '1m:RSI7=very low', '5m:WAD=low (falling in)'}, closed=(1, 5), states=held), 3000)
    assert problem is None
    assert [(c['h'], c['rank'], c['kind'], c['key'], c['of']) for c in calls] == [
        (15, 1, 'single', '1m:RSI7=very low', 40),
        (240, 1, 'single', '1m:MFI14=very low', 30),                                               # fired through its alias
        (240, 1, 'triple', '1m:MFI14=very low | 1m:PVO12/26 sign=above 0 | 60m:SQZMOM sign=above 0', 30),
        (240, 2, 'single', '1m:RSI7=very low', 30),
        (240, 2, 'pair', '1m:MFI14=very low | 60m:SQZMOM sign=above 0', 30),
        (240, 3, 'single', '5m:WAD=low (falling in)', 30),
        (1440, 2, 'pair', '1m:RSI7=very low | 5m:MOM10 sign=above 0', 30)]
    assert all(c['trig'] == c['key'].split(' | ')[0] for c in calls if c['kind'] != 'single') and all(c['barClose'] == TS for c in calls)
    # the 60-minute state turns: the pair conditioned on the other side fires instead
    calls, _, _ = join(t, 40, res({'1m:MFI14=very low'}, states={'60m:SQZMOM sign': 'below 0'}), 3000)
    assert [(c['h'], c['rank'], c['kind'], c['key']) for c in calls] == [(240, 1, 'single', '1m:MFI14=very low'),
                                                                        (240, 1, 'pair', '1m:MFI14=very low | 60m:SQZMOM sign=below 0')]
    # a 60-minute single fires at the hourly close only
    hour = res({'60m:C-AVGPRICE=high (rising in)'}, closed=(1, 5, 15, 60), states=held)
    assert [(c['h'], c['rank'], c['tf'], c['dir'], c['of']) for c in join(t, 40, hour, 3000)[0]] == [(1440, 1, 60, -1, 30)]
    assert join(t, 40, res({'60m:C-AVGPRICE=high (rising in)'}, closed=(1, 5)), 3000)[0] == []


def test_perp_rows_on_an_indicator_the_main_packs_mark_are_skipped(tmp_path):
    assert indicator_of('5m:PVI sign=above 0') == indicator_of('1m:PVI') == indicator_of('PVI') == indicator_of('60m:PVI sign') == 'PVI'
    assert indicator_of('60m:PVO12/26 sign') == 'PVO12/26' and indicator_of('UTC4h=12-16') == 'UTC4h' and indicator_of('15m:NVI=low') == 'NVI'
    # the real main packs mark PVI: the traded pack's parity section, the pair pack's list and the SOL rows marked false
    assert parity_off(fixture('traded_pack.json'), fixture('pair_pack.json')) == {'PVI'}
    assert parity_off(dict(fixture('traded_pack.json'), live_reader_parity={}), {}) == {'PVI'}                # the rows alone say it too
    assert parity_off({'rows': [pack_row('SOL', '1m:RSI7=very low')]}, {'indicators_that_differ_live': ['OBV']}) == {'OBV'}
    assert parity_off({'rows': [pack_row('SOL', '1m:RSI7=very low')]}, {}) == set()
    rows = [pack_row('SOL', '1m:PVI=high (rising in)', rank=6, live_parity=False), pack_row('SOL', '1m:RSI7=very low', rank=1)]
    perp = [perp_row('SOL', '5m:PVI=low (falling in)', rank=1, tf='5m'),                       # on PVI by its key, on another timeframe
            perp_row('SOL', '1m:CMO14=very low', rank=2, aliases=['1m:PVI=very low']),         # by an alias
            perp_row('SOL', '1m:RSI7=very low', rank=3),
            perp_row('SOL', '1m:RSI2=very low', h=1440, rank=1)]
    pp = [perp_pair('SOL', '1m:RSI7=very low', [('60m:PVI sign', 'below 0')]),                 # by a condition
          perp_pair('SOL', '1m:PVI=very low', [('15m:MDI14', 'high')], h=1440),               # by its trigger
          perp_pair('SOL', '1m:RSI7=very low', [('1m:AD sign', 'below 0')], readings=['1m:AD', '1m:RSI7', '5m:PVI']),   # by its readings
          perp_pair('SOL', '1m:CMO14=very low', [('15m:MDI14', 'high')]),                     # by its trigger's alias (join fires it on PVI)
          perp_pair('SOL', '1m:RSI7=very low', [('1m:AD sign', 'below 0'), ('15m:MDI14', 'high')])]
    t = tables(tmp_path, rows, coins=('SOL',), perp=perp, perp_pairs=pp).coins['SOL']
    assert t.counts()['perp'] == {'wanted': {'single': 2, 'pair': 0, 'triple': 1}, 'skipped': {SKIP_PARITY: 6}}
    assert not any('PVI' in k for k in t.want | t.states)
    ev = {'5m:PVI=low (falling in)', '1m:PVI=very low', '1m:RSI7=very low', '1m:RSI2=very low', '1m:PVI=high (rising in)'}
    held = {'60m:PVI sign': 'below 0', '15m:MDI14': 'high', '1m:AD sign': 'below 0'}
    calls, _, _ = join(t, 40, res(ev, closed=(1, 5), states=held), 3000)
    assert [(c['h'], c['kind'], c['key']) for c in calls] == [(15, 'single', '1m:RSI7=very low'), (240, 'single', '1m:RSI7=very low'),
                                                             (240, 'triple', '1m:RSI7=very low | 1m:AD sign=below 0 | 15m:MDI14=high'),
                                                             (1440, 'single', '1m:RSI2=very low')]
    # main packs that mark nothing: the same perp rows are published
    t = tables(tmp_path / 'b', [pack_row('SOL', '1m:RSI7=very low')], coins=('SOL',), perp=perp, perp_pairs=pp).coins['SOL']
    assert t.counts()['perp'] == {'wanted': {'single': 4, 'pair': 4, 'triple': 1}, 'skipped': {}}


def test_perp_rows_the_reader_cannot_vouch_for(tmp_path):
    rows = [pack_row('BTC', '1m:RSI7=very low'), pack_row('BTC', '1m:RSI2=very low', h=60, rank=2), pack_row('ETH', '1m:RSI7=very low')]
    good = [perp_row('BTC', '1m:MFI14=very low'), perp_row('ETH', '1m:MFI14=very low')]
    pp = [perp_pair('BTC', '1m:MFI14=very low', [('60m:SQZMOM sign', 'above 0')]),
          perp_pair('BTC', '1m:MFI14=very low', [('BTC.D 1d', 'up')]),                                      # needs the dominance feed
          perp_pair('BTC', '1m:MFI14=very low', [('1m:OBV sign', 'below 0')], sha='long-old'),              # another table than perp_pack's
          perp_pair('BTC', '1m:MFI14=very low', [('1m:AD sign', 'below 0')], h=60)]                         # h60 belongs to the main packs
    t = tables(tmp_path, rows, coins=('BTC', 'ETH'), perp=good + [perp_row('BTC', '1m:WAD=very low', h=60, rank=2)], perp_pairs=pp)
    btc = t.coins['BTC']
    assert btc.counts()['perp'] == {'wanted': {'single': 1, 'pair': 1, 'triple': 0}, 'skipped': {SKIP_DOMINANCE: 1, SKIP_HASH: 1, SKIP_PERP_H: 2}}
    assert t.coins['ETH'].counts()['perp'] == {'wanted': {'single': 1, 'pair': 0, 'triple': 0}, 'skipped': {}}
    # long-table edges the oracle did not find equal to live_meta's (the file says so, or the row does): not read with them
    head = {'edges_as_main_tables': {'BTC': {'same': 600, 'n_different': 24, 'price_step_same': True},
                                     'ETH': {'same': 624, 'n_different': 0, 'price_step_same': True}}}
    t = tables(tmp_path / 'e', rows, coins=('BTC', 'ETH'), perp=good + [perp_row('ETH', '1m:WAD=very low', rank=2, edges_as_main=False)], perp_head=head)
    assert t.coins['BTC'].counts()['perp']['skipped'] == {SKIP_PERP_EDGES: 1} and t.coins['ETH'].counts()['perp'] == \
        {'wanted': {'single': 1, 'pair': 0, 'triple': 0}, 'skipped': {SKIP_PERP_EDGES: 1}}
    # perp packs of another oracle run than the traded pack's
    t = tables(tmp_path / 'r', rows, coins=('BTC', 'ETH'), perp=good, perp_pairs=pp[:1], perp_head={'stamp': 'long tables of run 555000111'})
    assert t.coins['BTC'].counts()['perp'] == {'wanted': {'single': 0, 'pair': 0, 'triple': 0}, 'skipped': {SKIP_PERP_RUN: 2}}
    # a row the bot must not trade from: that coin's perp rows are left out, never its main rows or another coin's
    t = tables(tmp_path / 'b', rows, coins=('BTC', 'ETH'), perp=[perp_row('BTC', '1m:MFI14=very low', direction=0)] + good, perp_pairs=pp)
    btc = t.coins['BTC']
    assert btc.problem is None and len(btc.rows) == 2 and btc.perp_rows == btc.perp_pairs == []
    assert btc.counts()['perp'] == {'wanted': {'single': 0, 'pair': 0, 'triple': 0}, 'skipped': {},
                                    'problem': 'perp_pack.json row 1 of this coin (1m:MFI14=very low): dir is neither 1 nor -1'}
    assert t.coins['ETH'].perp_rows and t.coins['ETH'].counts()['perp'].get('problem') is None
    t = tables(tmp_path / 'c', rows, coins=('BTC',), perp=good, perp_pairs=[perp_pair('BTC', '1m:MFI14=very low', [('1m:AD sign', 'below 0')], kind='quad')])
    assert t.coins['BTC'].counts()['perp']['problem'].startswith('perp_pair_pack.json row 1 of this coin') and t.coins['BTC'].rows
    assert t.coins['BTC'].counts()['perp']['skipped'] == {} and t.coins['BTC'].perp_rows == []
    t = tables(tmp_path / 'd', rows, coins=('BTC',), perp=good, perp_head={'table_sha256': {'ETH': 'long-x'}})
    assert t.coins['BTC'].counts()['perp']['problem'] == 'perp_pack.json has no table hash for this coin'
    t = tables(tmp_path / 'n', rows, coins=('BTC', 'ETH'), perp=good[1:])
    assert t.coins['BTC'].counts()['perp']['problem'] == 'perp_pack.json has no rows for this coin' and t.coins['ETH'].perp_rows
    # a perp row without zone edges in live_meta.json: the coin's perp rows go, h15 and h60 stay, and so does the window
    t = tables(tmp_path / 'z', rows, coins=('BTC',), perp=good, perp_pairs=pp[:1], edges={'1m:RSI7': [1, 2, 3, 4], '1m:RSI2': [1, 2, 3, 4]})
    btc = t.coins['BTC']
    assert btc.tfs == [1, 60] and '1m:MFI14=very low' in btc.want
    btc.check_edges(ZONE_EVENTS, ZONE_STATES)
    assert btc.problem is None and btc.perp_rows == btc.perp_pairs == [] and btc.tfs == [1] and btc.want == {'1m:RSI7=very low', '1m:RSI2=very low'}
    assert btc.counts()['perp']['problem'] == 'live_meta.json has no zone edges for 2 perp row(s), first 1m:MFI14=very low'
    assert btc.counts()['perp']['wanted'] == {'single': 0, 'pair': 0, 'triple': 0} and btc.states == set()
