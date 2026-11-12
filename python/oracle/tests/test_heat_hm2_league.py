"""OR-HM2 section 5, the league (python/oracle/heat_hm2_league.py; build plan section 5): the league over the series
files of one coin and its three no-signal twins (the identical pipeline: heat_hm2.run_series), the lists (exact and near
copies collapsed, at most 3 rows per reading, no pass bar), the provenance-only unseen slice, the marks as columns, the
conservative BHY from the p histogram, the chance scale beside every count, the words (Eastern and UTC), the usage
cards, the pack (fire at the onset, live_ready False until parity) and its live meta, the Part 3 gate rows and the Part 4
section hooks, live_ready from parity and feeds, the parity of the live reader on windows, and DOGE refused.
Synthetic minutes: SPLITS patched to 120 days (A 90, B 30) as in test_heat_hm2_scan; a planted XOR of two 15-minute
states (each flat alone) and a fake GBM call built from the same states (the learner itself is tested elsewhere)."""
import hashlib
import json
import os
import re

import numpy as np
import pandas as pd
import pytest

from oracle import heat
from oracle import heat_hm2 as hm
from oracle import heat_hm2_league as L
from oracle.common import DAY
from oracle.tests import test_heat_hm2_scan as SC

DAYS, A_DAYS = 120, 90
LV = ['low', 'mid', 'high']


def _xor(seed=21):
    rng = np.random.default_rng(seed)
    nb = DAYS * 96
    s1 = rng.choice(3, nb, p=[0.25, 0.5, 0.25]).astype(np.int8)
    s2 = rng.choice(3, nb, p=[0.25, 0.5, 0.25]).astype(np.int8)
    x = np.where((s1 == 1) | (s2 == 1), 0, np.where(s1 == s2, 1, -1)).astype(float)
    return s1, s2, x


S1, S2, XS = _xor()


def _readings(m, g):
    R = SC._path_readings(m, g)
    R.append({'name': '15m:S1', 'k': 15, 'codes': S1[:m['n'] // 15], 'levels': LV, 'base': '15m:S1'})
    R.append({'name': '15m:S2', 'k': 15, 'codes': S2[:m['n'] // 15], 'levels': LV, 'base': '15m:S2'})
    return R


def _fake_learner(ctx, out, log):
    """heat_hm2._learner's dict with one GBM call: a score from the planted states (the last closed 15-minute bar's XOR)
    plus noise, in five zones at A's quantiles; on a twin the same score (its moves are coin flips)."""
    from oracle import heat_hm2_learn as hl
    from oracle import heat_xdata as xd
    n = ctx.m['n']
    bar = (np.arange(n) + 1) // 15 - 1
    sig = np.where(bar >= 0, XS[np.clip(bar, 0, len(XS) - 1)], 0.0)
    score = sig + np.random.default_rng(7).normal(0, 0.3, n)
    score[ctx.m['gap']] = np.nan
    R, edges = xd.zone('GBM.ALL15', score, ctx.g.sp['A'].hi, typ='gbm', family='model')
    R.update(model='ALL', h=15, used=2)
    R['call'] = hl.call_stats(ctx, R, 15)
    usage = {'ALL15': {'rows': 1000, 'model': 'ALL', 'h': 15, 'by_function': {'S': {'mean_abs': 2.0 if ctx.real else 0.2, 'mean': 0.0}},
                       'by_level': {'15m:S1': {'low': {'n': 10, 'mean': 0.5}, 'high': {'n': 10, 'mean': -0.5}}}, 'call': R['call']}}
    trees = {'ALL_h15': {'file': 'trees/ALL_h15.json', 'sha256': 'none', 'used': ['15m:S1', '15m:S2'], 'edges': edges}}
    return {'gbm': [R], 'paths': [], 'usage': usage, 'trees': trees, 'version': 'fake'}


def _hm1(d):
    """HM1 files: a pack the bot loads holding 1m:R10 = low (an event label), a stored pair (15m:R3, 1m:VR) of BTC, the
    direction league and BTC's main meta."""
    os.makedirs(d / 'pairs', exist_ok=True)
    os.makedirs(d / 'metas' / 'BTC', exist_ok=True)
    json.dump({'rows': [{'key': '1m:R10=low (falling in)', 'aliases': []}]}, open(d / 'traded_pack.json', 'w'))
    pd.DataFrame({'trig': ['15m:R3=very high'], 'cond': ['1m:VR'], 'lv': ['mid']}).to_csv(d / 'pairs' / 'pairs_BTC.csv.gz', index=False)
    rows = []
    for coin in ('BTC', 'BTC-twin1'):
        for h in (15, 60, 240):
            for i, key in enumerate(('15m:R3=very high', '15m:R10=very low', '1m:R30=low (recovering)')):
                rows.append({'coin': coin, 'h': h, 'key': key, 'dir': 1 if i % 2 else -1, 'odds_B': 1.0 + i, 'share_B': 51.0 + i,
                             'share_over_B': 0.5 * i, 'wd_B': 2.0 * (i + 1), 'oheat_B': 2.0 * (i + 1) * (1.0 + i)})
    pd.DataFrame(rows).to_csv(d / 'direction_all.csv.gz', index=False)
    json.dump({'edges': {'15m:R3': [-0.01, -0.002, 0.002, 0.01]}, 'price_step': 0.01}, open(d / 'metas' / 'BTC' / 'meta.json', 'w'))
    return d


@pytest.fixture(scope='module')
def built(tmp_path_factory):
    """A coin (BTC, with the planted XOR) and its three twins through heat_hm2.run_series (fake learner), HM1 files and
    the league."""
    old_spl, old_learner = heat.SPLITS, hm._learner
    start = heat.HEAT_END - DAYS * DAY
    heat.SPLITS = {'A': (start, start + A_DAYS * DAY), 'B': (start + A_DAYS * DAY, heat.HEAT_END)}
    hm._learner = _fake_learner
    try:
        d = tmp_path_factory.mktemp('hm2league')
        drift = np.repeat(np.r_[0.0, XS[:-1]], 15) * 3e-4
        SC._csv(d / 'btc.csv', start, seed=4, drift=drift)
        hm1 = _hm1(d / 'hm1')
        m = heat.load_minutes(str(d / 'btc.csv'))
        for tw in (0, 1, 2, 3):
            mm = heat.make_twin(m, tw) if tw else m
            lab = heat.labels(mm)
            g = heat.Grid(mm, lab)
            ctx = hm.make_ctx(mm, _readings(mm, g), 'BTC', tw, lab=lab, g=g, log=lambda *a: None)
            hm.run_series('BTC', str(d / 'btc.csv'), str(d / 'inputs' / ('BTC' if not tw else f'BTC-twin{tw}')), ctx=ctx, procs=2,
                          hm1_packs=[str(hm1 / 'traded_pack.json')], hm1_pairs=str(hm1 / 'pairs' / 'pairs_BTC.csv.gz'), log=lambda *a: None)
        out = d / 'league'
        summ = L.league(str(d / 'inputs'), str(hm1), str(out), stamp='test', log=lambda *a: None)
        yield {'d': d, 'out': out, 'summary': summ, 'hm1': hm1, 'm': m}
    finally:
        heat.SPLITS, hm._learner = old_spl, old_learner


def _strict(path):
    txt = open(path).read()
    return json.loads(txt, parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))


# ------------------------------------------------------------------------------------------------------- the outputs
def test_league_outputs_and_pack(built):
    """Every file is written (JSON without NaN); the lists hold the coin and its twins at all six horizons; the pack
    holds the coin's rows at 15, 60 and 240 minutes, each with its conditions, direction, fire = onset, the lists it is
    in, the marks as columns, and live_ready False until parity; the model rows carry the GBM zones; the live meta names
    the GBM edges and every reading behind a row."""
    out, s = built['out'], built['summary']
    for f in ('league.md', 'usage.md', 'summary.json', 'lists.csv.gz', 'model.csv.gz', 'usage_cards.json', 'hm2_pack.json', 'hm2_live_meta.json'):
        assert os.path.exists(out / f), f
    sj, pk, lm = _strict(out / 'summary.json'), _strict(out / 'hm2_pack.json'), _strict(out / 'hm2_live_meta.json')
    assert sj['schema'] == L.SCHEMA_SUMMARY and pk['schema'] == L.SCHEMA_PACK and lm['schema'] == L.SCHEMA_LIVE
    assert s['coins'] == ['BTC'] and sorted(s['twins']) == ['BTC~twin1', 'BTC~twin2', 'BTC~twin3']
    assert any('partial' in w for w in s['warnings']) and not any('twin sets' in w for w in s['warnings'])
    lists = pd.read_csv(out / 'lists.csv.gz')
    assert set(lists.coin) == {'BTC', 'BTC~twin1', 'BTC~twin2', 'BTC~twin3'}
    assert set(lists.h) <= set(hm.H_SCAN) and {15, 60} <= set(lists.h) and set(lists.slice) == {'all', 'unseen'}
    for (c, k, h, sl, me), y in lists.groupby(['coin', 'kind', 'h', 'slice', 'measure']):
        assert len(y) <= hm.TOP[me] and list(y['rank']) == list(range(1, len(y) + 1))
        assert (np.diff(y['value'].to_numpy()) <= 1e-9).all()
        cnt = pd.Series([r for c_ in y.conds for r in L._rows_readings(c_)]).value_counts()
        assert cnt.max() <= hm.PER_READING
    # (review fix) every row a list shows was re-measured (onset and held), the unseen slice included
    assert lists['remeasured'].all() and lists['onset_n_B'].notna().all(), lists[~lists['remeasured']][['coin', 'list', 'h', 'rank']].head()
    rows = pk['rows']
    assert rows and {r['coin'] for r in rows} == {'BTC'} and {r['h'] for r in rows} <= set(hm.PACK_H)
    assert {'pair', 'model'} <= {r['kind'] for r in rows}
    for r in rows:
        assert r['fire'] == 'onset' and r['live_ready'] is False and r['live_ready_why'] == ['parity not run']
        assert r['conds'] and r['dir'] in (-1, 1) and r['call'] in ('up', 'down') and r['readings']
        assert set(r['onset']) == set(L.RM_PACK) and set(r['held']) == set(L.RM_PACK)
        if r['kind'] != 'model':
            assert r['lists'] and set(r['ranks']) == set(r['lists']) and set(r['marks']) == set(r['lists'])
            assert r['seen_in_league'] in ('none', 'stored', 'pack')
            # (review fix) the headline numbers are what the onset fire gave; the scan's held-state numbers are in `scan`
            assert all(r[k] == r['onset'][k] for k in L.HEAD_ONSET) and set(r['scan']) == set(L.HEAD_ONSET)
            assert r['onset_agrees_A'] == (r['onset']['odds_A'] > 0) and r['onset_dir_A'] in (-1, 0, 1)
    mrow = [r for r in rows if r['kind'] == 'model']
    assert {r['key'].split('=')[1] for r in mrow} <= {'very low', 'low', 'high', 'very high'} and all(r['model'] == 'ALL' for r in mrow)
    assert any(r['onset']['n_B'] for r in mrow if r['key'].endswith('very high') or r['key'].endswith('very low'))
    c = lm['coins']['BTC']
    assert c['gbm']['GBM.ALL15']['edges'] and len(c['gbm']['GBM.ALL15']['edges']) == 4
    assert {'15m:S1', '15m:S2'} <= set(c['readings'])
    assert pk['models']['BTC']['ALL']['15']['used'] == ['15m:S1', '15m:S2']
    assert pk['live_meta_sha256'] and pk['table_sha256']['BTC']
    md = open(out / 'league.md').read()
    for sec in ('## 1. Chance scale', '## 2. The unseen slice', '## 3. The model call', '## 4. Lessons', '## 5. The lists', '## 6. The pack',
                L.SECTION.format('part3'), L.SECTION.format('part4'), '## Chart patterns (Part 4)'):
        assert sec in md, sec
    assert 'EST' in md and 'UTC' in md and not re.search(r'\bnan\b', md.lower())


def test_planted_xor_tops_iheat_above_twins(built):
    """The planted XOR (each state flat alone) leads BTC's iheat list at 15 minutes, in the right direction, above the
    max of its three twins; it is unseen (provenance: neither state is in a pack or stored), so it also leads the
    unseen list; the twins' lists exist and none of their rows is marked above their own coin's twins."""
    lists = pd.read_csv(built['out'] / 'lists.csv.gz')
    for sl in ('all', 'unseen'):
        y = lists[(lists.coin == 'BTC') & (lists.kind == 'pair') & (lists.h == 15) & (lists.measure == 'iheat') & (lists.slice == sl)].sort_values('rank')
        top = y.iloc[0]
        assert set(L._cond_names(top.conds)) == {'15m:S1', '15m:S2'}, y[['key', 'value']].head()
        lv = [x[1][0] for x in json.loads(top.conds)]
        assert top.d_iota == (1 if lv[0] == lv[1] else -1)
        assert top.above_twin_max and top.value > top.twin_max > 0 and top.seen_in_league == 'none'
    tw = lists[lists.twin != 0]
    assert len(tw) and not tw.above_twin_max.any()
    ch = built['summary']['chance']['pair']['15']
    assert ch['twin_sets'] == 3 and ch['real']['above_twin_max']['all:iheat']['rows'] >= 1
    assert ch['twin']['cells']['median'] is not None and len(ch['twin']['cells']['range']) == 2


def test_unseen_is_provenance_only(built):
    """The unseen slice is the cells with seen_in_league = none (no part in a pack, the pair not stored), whatever the
    parts' own strength: a strong part (part_tmax >= 3) stays in, and the league's recomputed provenance agrees with
    the series' labels."""
    lists = pd.read_csv(built['out'] / 'lists.csv.gz')
    u = lists[lists.slice == 'unseen']
    assert len(u) and (u.seen_in_league == 'none').all()
    a = lists[(lists.slice == 'all') & (lists.coin == 'BTC')]
    assert {'pack', 'none'} <= set(a.seen_in_league)
    pc = built['summary']['provenance_check']
    assert pc['checked'] and pc['differ'] == 0
    c = pd.read_csv(built['d'] / 'inputs' / 'BTC' / 'candidates.csv.gz')
    assert (c[c.seen_in_league == 'none'].part_tmax >= 0).all()           # no significance filter: any strength may be unseen


def test_seen_in_league_names_rule(tmp_path):
    """Provenance by names: an event label in a pack matches its state level; an alias counts; two readings stored
    together are 'stored'; direction_all is never read."""
    pk = tmp_path / 'traded_pack.json'
    json.dump({'rows': [{'key': '15m:RSI14=low (falling in)', 'aliases': ['1m:X=very high']}]}, open(pk, 'w'))
    pp = tmp_path / 'pairs_BTC.csv.gz'
    pd.DataFrame({'trig': ['15m:A=very high'], 'cond': ['1m:B'], 'lv': ['mid']}).to_csv(pp, index=False)
    hp = hm.load_hm1([str(pk)], str(pp))
    got = L.seen_in_league([[['15m:RSI14', ['low']], ['1m:B', ['high']]],
                            [['15m:RSI14', ['very low']], ['1m:B', ['high']]],
                            json.dumps([['1m:Y', ['very high']], ['5m:Z', ['low']]]),
                            [['15m:A', ['low']], ['1m:B', ['high']]],
                            [['15m:Q', ['low']], ['1m:B', ['high']]]], hp, {'1m:Y': ['1m:Y', '1m:X']})
    assert got == ['pack', 'none', 'pack', 'stored', 'none']
    pd.DataFrame({'coin': ['BTC'], 'h': [15], 'key': ['15m:Q=low']}).to_csv(tmp_path / 'direction_all.csv.gz', index=False)
    assert L.seen_in_league([[['15m:Q', ['low']], ['1m:B', ['high']]]], str(tmp_path)) == ['none']


# --------------------------------------------------------------------------------------------------------- the lists
def _pool(n=10):
    rows = []
    for i in range(n):
        rows.append({'key': f'k{i}', 'kind': 'pair', 'h': 15, 'conds': json.dumps([[f'r{i % 4}', ['low']], [f'q{i}', ['high']]]),
                     'oheat_B': 100.0 - i, 'iheat_B': 50.0 - i, 'lheat_B': 10.0 - i, 'n_A': 100 + i, 'n_B': 50 + i, 'days_A': 80, 'days_B': 25,
                     'odds_A': 1.0 + i, 'odds_B': 2.0 + i, 't_A': 3.0, 't_B': 2.0, 'iota_robust_A': 1.0, 'iota_robust_B': 1.0, 'wd_B': 3.0})
    return pd.DataFrame(rows)


def test_make_list_copies_near_and_cap():
    """Exact copies (identical numbers on both periods) collapse into the better row's aliases; a near copy (B Jaccard
    >= 0.8 with a better row) too; at most per_reading rows per reading; ranks 1..n by the measure; NaN rows dropped."""
    p = _pool()
    cp = p.iloc[[0]].assign(key='k0copy', oheat_B=100.0)                # the same event under another name
    p = pd.concat([p, cp, p.iloc[[1]].assign(key='knan', oheat_B=np.nan)], ignore_index=True)
    jac = pd.DataFrame({'kind': ['pair'], 'h': [15], 'measure': ['oheat'], 'key1': ['k1'], 'key2': ['k2'], 'jaccard': [0.9]})
    x = L.make_list(p, 'oheat', 40, jac, per_reading=2)
    assert x['key'].iloc[0] == 'k0' and x['aliases'].iloc[0] == ['k0copy'] and 'k0copy' not in set(x.key)
    assert x[x.key == 'k1']['near'].iloc[0] == ['k2'] and 'k2' not in set(x.key) and 'knan' not in set(x.key)
    cnt = pd.Series([r for c in x.conds for r in L._rows_readings(c)]).value_counts()
    assert cnt.max() <= 2 and list(x['rank']) == list(range(1, len(x) + 1))
    assert len(L.make_list(p, 'oheat', 3, None)) == 3 and len(L.make_list(p.iloc[:0], 'oheat', 3)) == 0


def test_bhy_from_histogram_is_conservative():
    """BHY q from the log-binned p histogram is never below the exact BHY q of the same family, and close to it."""
    from oracle.sim import bhy_adjust
    rng = np.random.default_rng(3)
    p = np.r_[rng.uniform(0, 1, 5000), 10 ** rng.uniform(-9, -3, 60), np.ones(300)]
    e = hm.SummaryCounts.P_EDGES
    hist = np.bincount(np.searchsorted(e, np.log10(p), side='left'), minlength=len(e) + 1)
    q = L.bhy_from_hist(p, hist, e)
    ex = bhy_adjust(p)
    assert (q >= ex - 1e-12).all() and (q <= 1).all()
    small = ex < 0.1
    assert small.sum() >= 30 and np.all(q[small] <= ex[small] * 1.25 + 1e-12)
    assert (L.bhy_from_hist(p, np.zeros(len(e) + 1), e) == 1).all()


def test_marks_are_columns_never_filters():
    """add_marks adds hot_A, p_B, rep_B, q and bhy to every row and drops none."""
    x = pd.DataFrame({'dir': [1, -1, 1, 0], 't_A': [5.0, -4.0, 0.5, 9.0], 't_B': [4.0, -3.0, 0.2, 9.0], 'deff_A': [80.0] * 4, 'days_A': [80] * 4,
                      'deff_B': [25.0] * 4})
    y = L.add_marks(x, 'oheat', np.r_[np.zeros(200), [4], np.zeros(40)])
    assert len(y) == 4 and list(y.hot_A) == [True, True, False, False] and list(y.rep_B) == [True, True, False, False]
    assert y.p_B.iloc[3] == 1.0 and np.isfinite(y.q).all()


# ----------------------------------------------------------------------------------------------------- chance, words
def test_twin_scale_and_missing_twin_warning(built, tmp_path):
    """twin_scale gives the median and range of each metric over the twin sets (nested); a league without a twin set
    warns and keeps every row."""
    sc = L.twin_scale([{'a': 1, 'b': {'c': 0.5}, 'l': [1, 2]}, {'a': 3, 'b': {'c': 0.7}, 'l': [3, None]}, {'a': 2, 'b': {'c': None}, 'l': [2, 4]}])
    assert sc['a'] == {'median': 2, 'range': [1, 3]} and sc['b']['c'] == {'median': 0.6, 'range': [0.5, 0.7]}
    assert sc['l'][0]['median'] == 2 and sc['l'][1]['range'] == [2, 4]
    import shutil
    inp = tmp_path / 'inputs'
    shutil.copytree(built['d'] / 'inputs' / 'BTC', inp / 'BTC')
    shutil.copytree(built['d'] / 'inputs' / 'BTC-twin1', inp / 'BTC-twin1')
    s = L.league(str(inp), '', str(tmp_path / 'out'), log=lambda *a: None)
    assert any('twin sets [1] of [1, 2, 3]' in w for w in s['warnings'])
    a = pd.read_csv(built['out'] / 'lists.csv.gz')
    b = pd.read_csv(tmp_path / 'out' / 'lists.csv.gz')
    ka = a[a.coin == 'BTC'][['kind', 'h', 'slice', 'measure', 'key']]
    kb = b[b.coin == 'BTC'][['kind', 'h', 'slice', 'measure', 'key']]
    assert ka.reset_index(drop=True).equals(kb.reset_index(drop=True))         # the twins change marks, never rows
    assert not s['provenance_check']['checked']


def test_words_eastern_and_utc():
    """Clock levels in Eastern (EST and EDT) and UTC; a row in words with its share, windows and the twins' best."""
    assert L.level_words('UTC1h', '13') == 'the hour 13:00-14:00 UTC (8:00 AM-9:00 AM EST, 9:00 AM-10:00 AM EDT)'
    w = L.level_words('NY30m', '09:30')
    assert '9:30 AM-10:00 AM ET' in w and '14:30 UTC in winter' in w and '13:30 UTC in summer' in w
    assert 'Monday UTC (from Sunday 7:00 PM EST' in L.level_words('Weekday', 'Mon')
    assert 'last minute before :00' in L.level_words('POS:QPos', 'm14')
    assert '13:30 UTC in winter' in L.level_words('MACRO:R830', '0-14 after')
    row = {'dir': -1, 'conds': json.dumps([['15m:RSI14', ['very high']], ['X.BTC:R5z', ['very low']]]), 'share_B': 57.2, 'wd_B': 6.04,
           'measure': 'oheat'}
    s = L.in_words(row, {'share_B': 53.0, 'wd_B': 4.0})
    assert s == "15m RSI14 very high while BTC's last 5 minutes very low: down, 57% right on 2025, 6.0 windows a day (twins' best: 53%, 4.0 windows)."
    assert L.in_words(row).endswith('(no twin in this league).')


# --------------------------------------------------------------------------------------------------- the lessons
def test_usage_cards(built):
    """One card per TA function of the series' readings (cards.json.gz grid: the settings x timeframe squares with the
    strongest A horizon and B odds beside the twins); its best partner per family with iota_with_call; the kept share per
    function from the scan's tally beside the twins; the model's contribution beside the twins'."""
    cards = _strict(built['out'] / 'usage_cards.json')['cards']
    assert {'R', 'S', 'VR'} <= set(cards)
    s = cards['S']
    assert s['grid'] and all(g['best_h'] in hm.H_SCAN and g['coins'] == 1 and g['twins'] == 3 for g in s['grid'])
    assert {g['tf'] for g in s['grid']} == {'15m'} and set(s['grid'][0]['odds_B']) == {'low', 'high'}
    p15 = [p for p in s['partners'] if p['h'] == 15]
    assert p15 and max(p['iheat_B'] for p in p15) > 0 and all(isinstance(p['iota_with_call'], bool) for p in p15)
    best = max(p15, key=lambda p: p['iheat_B'])
    assert best['partner'] in ('15m:S1', '15m:S2') and best['twin_best_iheat_B']['median'] is not None
    k = s['kept']['15']
    assert k['level'] == 'function' and k['cells'] > 0 and k['twin_median'] is not None and len(k['twin_range']) == 2
    mm = s['model']['ALL15']
    assert mm['real']['BTC'] == 2.0 and mm['twin_median'] == 0.2 and mm['by_level'] == {'high': -0.5, 'low': 0.5}
    um = open(built['out'] / 'usage.md').read()
    assert '## S' in um and 'Its best partner in each data family' in um


def test_model_and_baselines(built):
    """The GBM zones beside the twins' zones; the last candle faded per horizon; the best single level of the direction
    league, also at matched windows per day."""
    ms = built['summary']['model']
    z = [x for x in ms['zones'] if x['coin'] == 'BTC' and x['h'] == 15]
    assert z and all(x['twin_odds_B']['median'] is not None for x in z)
    vh = [x for x in z if x['level'] in L.EXTREME]
    assert vh and all(x['odds_B'] > 0 for x in vh)                      # the planted call, B odds in its A direction
    b = [x for x in ms['baselines'] if x['h'] == 15]
    assert b and b[0]['last_candle_faded']['odds_B'] is not None and b[0]['best_single']['by_heat']['key'] == '1m:R30=low (recovering)'


# ------------------------------------------------------------------------------------------------- Part 3 and Part 4
def test_gate_rows_merge_and_sections(built, tmp_path):
    """Part 3's gate rows merge into the pack from their own file with every other row byte-identical (non_gate_sha);
    a non-gate row in that file stops; a second merge replaces the gate rows; live-ready leaves them as they are.
    upsert_section replaces a section between its markers; chart_section reads Part 4's league files."""
    pk = _strict(built['out'] / 'hm2_pack.json')
    sha0 = L.non_gate_sha(pk)
    g = {'rows': [{'kind': 'gate', 'coin': 'BTC', 'h': 15, 'key': 'g1', 'mode': 'block', 'live_ready': True},
                  {'kind': 'gate2', 'coin': 'BTC', 'h': 60, 'key': 'g2', 'live_ready': False}], 'part3': {'schema': 'p3'}}
    json.dump(g, open(tmp_path / 'gate_rows.json', 'w'))
    p2 = L.merge_gate_rows(pk, str(tmp_path / 'gate_rows.json'))
    assert L.non_gate_sha(p2) == sha0 == p2['non_gate_sha256'] and p2['part3'] == {'schema': 'p3'}
    assert sum(r['kind'] in L.GATE_KINDS for r in p2['rows']) == 2
    p3 = L.merge_gate_rows(p2, {'rows': g['rows'][:1]})
    assert sum(r['kind'] in L.GATE_KINDS for r in p3['rows']) == 1 and L.non_gate_sha(p3) == sha0
    with pytest.raises(SystemExit):
        L.merge_gate_rows(pk, {'rows': [{'kind': 'pair', 'key': 'x'}]})
    lr = L.set_live_ready(p2, {}, ())
    assert [r for r in lr['rows'] if r['kind'] in L.GATE_KINDS] == g['rows']
    assert '2 gate rows' in L.part3_section(p2)
    md = tmp_path / 'league.md'
    md.write_text('# x\n\n' + L.SECTION.format('part4') + '\nold\n' + L.SECTION_END.format('part4') + '\n\ntail\n')
    pat = tmp_path / 'patterns'
    pat.mkdir()
    (pat / 'chart_league.md').write_text('# Chart league\n\n## Singles\n\nrow\n')
    json.dump({'schema': 'oracle-heat-patterns-1', 'coins': ['BTC']}, open(pat / 'chart_summary.json', 'w'))
    L.upsert_section(str(md), 'part4', L.chart_section(str(pat)))
    t = md.read_text()
    assert 'old' not in t and '## Chart league' in t and '### Singles' in t and t.rstrip().endswith('tail') and t.count(L.SECTION.format('part4')) == 1
    assert t.count('Chart league') == 1 and '## Chart patterns (Part 4)' not in t        # Part 4's title is the section heading, once
    L.upsert_section(str(md), 'part3', 'P3')
    assert t in md.read_text() and md.read_text().rstrip().endswith(L.SECTION_END.format('part3'))
    assert 'has not written its league yet' in L.chart_section('')
    # a league run with --gates and --patterns puts both in (the gate rows, and Part 3's live block into the live meta)
    g['live'] = {'schema': 'oracle-heat-hm2-drill-live-1', 'coins': {'BTC': {'BTC|level|1m:X=high': {'k': 5}}}}
    json.dump(g, open(tmp_path / 'gate_rows.json', 'w'))
    s = L.league(str(built['d'] / 'inputs'), str(built['hm1']), str(tmp_path / 'out'), gates=str(tmp_path / 'gate_rows.json'), patterns=str(pat),
                 log=lambda *a: None)
    pk2 = _strict(tmp_path / 'out' / 'hm2_pack.json')
    assert s['pack']['gate_rows'] == 2 and L.non_gate_sha(pk2) == pk2['non_gate_sha256']
    lmp = tmp_path / 'out' / 'hm2_live_meta.json'
    assert _strict(lmp)['part3'] == g['live'] and pk2['live_meta_sha256'] == hashlib.sha256(lmp.read_bytes()).hexdigest()
    t2 = (tmp_path / 'out' / 'league.md').read_text()
    assert '2 gate rows are merged' in t2 and '### Singles' in t2
    # (review fix) gate rows built on another HM2 pack (their part3 block's tier-2 sha) are dropped, with their live block;
    # live_ready alone (a parity run) leaves the tier-2 sha and the gate rows alone
    assert L.tier2_sha(lr) == L.tier2_sha(pk) and L.merge_gate_rows(lr, dict(g, part3={'hm2_tier2_sha256': L.tier2_sha(pk)}))['part3'].get('stale') is None
    stale = dict(g, part3={'schema': 'p3', 'hm2_tier2_sha256': 'f' * 64})
    p4 = L.merge_gate_rows(p2, stale, log=lambda *a: None)
    assert not any(r['kind'] in L.GATE_KINDS for r in p4['rows']) and p4['part3']['stale'] and p4['part3']['gate_rows_dropped'] == 2
    assert L.non_gate_sha(p4) == sha0 and not L.gates_merged(p4)
    json.dump(stale, open(tmp_path / 'gate_rows.json', 'w'))
    s = L.league(str(built['d'] / 'inputs'), str(built['hm1']), str(tmp_path / 'out2'), gates=str(tmp_path / 'gate_rows.json'), log=lambda *a: None)
    pk3 = _strict(tmp_path / 'out2' / 'hm2_pack.json')
    assert s['pack']['gate_rows'] == 0 and pk3['part3']['stale'] and 'part3' not in _strict(tmp_path / 'out2' / 'hm2_live_meta.json')


# ------------------------------------------------------------------------------------------------------ live ready
def test_live_ready_from_parity_and_feeds(built):
    """live_ready: every reading of the row at >= 99.5% on its coin's parity and every feed the row needs; the model row
    needs the readings its trees use; a parity of another series table stops."""
    pk = _strict(built['out'] / 'hm2_pack.json')
    rows = [r for r in pk['rows'] if r['kind'] in ('pair', 'triple')]
    names = sorted({n for r in rows for n in r['readings']} | {'15m:S1', '15m:S2'})
    bad = rows[0]['readings'][0]
    par = {'schema': L.SCHEMA_PARITY, 'table_sha256': pk['table_sha256']['BTC'], 'readings': {},
           'engine': {n: {'agreement': 0.9 if n == bad else 1.0} for n in names}, 'gbm': {'GBM.ALL15': {'agreement': 1.0}}}
    pk['rows'].append(dict(rows[0], key='perp row', readings=['PERP:Basis'], conds=[['PERP:Basis', ['high']]]))
    out = L.set_live_ready(pk, {'BTC': par})
    ok = [r for r in out['rows'] if r['live_ready']]
    assert ok and all(bad not in r['readings'] for r in ok)
    nb = [r for r in out['rows'] if bad in r['readings'] and r['kind'] != 'model']
    assert nb and all(not r['live_ready'] and f'{bad}: parity 0.9000' in r['live_ready_why'] for r in nb)
    pr = [r for r in out['rows'] if r['key'] == 'perp row'][0]
    assert not pr['live_ready'] and 'no binance perp feed' in pr['live_ready_why'] and 'PERP:Basis: not checked' in pr['live_ready_why']
    mr = [r for r in out['rows'] if r['kind'] == 'model']
    assert mr and all(r['live_ready'] for r in mr)
    assert out['live_reader_parity']['live_min'] == L.LIVE_MIN
    assert not L.set_live_ready(pk, {})['rows'][0]['live_ready']
    with pytest.raises(SystemExit):
        L.set_live_ready(pk, {'BTC': dict(par, table_sha256='other')})
    assert L.needed_feeds(['X.ETH:R5z', 'MACRO:FOMC', 'BTC.D 1d', 'CB:Prem']) == {'spot', 'other coins', 'calendar 2026', 'dominance', 'coinbase minutes'}


def test_gbm_zone_window_equals_history():
    """The GBM zone at a close from reading dicts (the live way, _gbm_zone) equals the zone from the whole history
    (_gbm_history) for a hand-made tree on a zone reading and its ZS state; unknown on a gap."""
    rng = np.random.default_rng(2)
    n = 3000
    R = {'name': '15m:Q', 'k': 15, 'codes': rng.integers(0, 5, n // 15).astype(np.int8), 'levels': heat.ZONES, 'zones': True}
    leaf = lambda v: {'leaf_value': v}
    tj = {'tree_info': [{'tree_structure': {'split_feature': 0, 'decision_type': '<=', 'threshold': 0.5, 'default_left': True, 'missing_type': 'NaN',
                                            'left_child': leaf(-1.0), 'right_child': {'split_feature': 1, 'decision_type': '==', 'threshold': '1||3',
                                                                                    'default_left': False, 'missing_type': 'None',
                                                                                    'left_child': leaf(2.0), 'right_child': leaf(0.5)}}}],
          'hm2': {'features': [{'name': '15m:Q', 'k': 15, 'levels': list(heat.ZONES), 'offset': 2, 'zs_of': None, 'aliases': []},
                               {'name': 'ZS:15m:Q', 'k': 15, 'levels': ['x'] * 7, 'offset': 0, 'zs_of': '15m:Q', 'aliases': []}]}}
    edges = [-0.9, 0.0, 0.7, 1.5]
    gap = np.zeros(n, bool)
    gap[1500] = True
    rows = np.arange(100, n, 37)
    zh = L._gbm_history(tj, edges, lambda nm: R if nm == '15m:Q' else None, rows, gap)
    for r, z in zip(rows, zh):
        assert L._gbm_zone(tj, edges, lambda nm: (R, r) if nm == '15m:Q' else (None, None), gap=bool(gap[r])) == z
    assert set(zh.tolist()) - {-1} and L._gbm_zone(tj, edges, lambda nm: (None, None), gap=False) is None


def test_parity_on_windows(tmp_path, monkeypatch):
    """parity on the last day of a synthetic world: the new readings from 14-day windows agree with the history on
    almost every sampled close, and the pack's engine readings from the live reader's window agree with the whole
    grid; parity.json carries the table hash; a twin's series is refused."""
    pytest.importorskip('talib')
    from oracle.tests import test_heat_hm2_xdata as XT
    from oracle import heat_live, heat_xdata as X
    monkeypatch.setattr(heat, 'SPLITS', XT.SPL)
    P = XT._world(tmp_path)
    m = heat.load_minutes(P['BTC'])
    a_hi = X.split_rows(m['t0'], m['n'])[1]
    R15, used, _ = heat_live.tf_codes(m, 15, edges=None, window=None, a_rows=(0, a_hi), want_bases={'15m:RSI14', '15m:MOM10'})
    mm = {'edges': used, 'price_step': heat.tick_units(m, a_hi).get('step')}
    json.dump(mm, open(tmp_path / 'main_meta.json', 'w'))
    sd = tmp_path / 'series'
    sd.mkdir()
    json.dump({'schema': 'oracle-heat-hm2-1', 'label': 'BTC', 'asset': 'BTC', 'twin': 0, 'table_sha256': 'abc'}, open(sd / 'meta.json', 'w'))
    pack = {'rows': [{'coin': 'BTC', 'kind': 'pair', 'h': 15, 'readings': ['15m:RSI14', 'UTC4h'], 'key': 'a'},
                     {'coin': 'BTC', 'kind': 'pair', 'h': 15, 'readings': ['15m:MOM10 sign', 'VOL:RVclock'], 'key': 'b'}]}
    json.dump(pack, open(tmp_path / 'pack.json', 'w'))
    found = {'btcdom': P['btcdom'], 'cb': P['cb'], 'book': P['book']}
    res = L.parity('BTC', P['BTC'], str(sd), str(tmp_path / 'par'), main_meta=str(tmp_path / 'main_meta.json'),
                   other_csvs={o: P[o] for o in ('ETH', 'SOL', 'XRP')}, perp_csv=P['perp'], fund_csv=P['funding'], oi_csv=P['oi'],
                   cal_csv=XT.CAL, dom=P['dom'], found=found, pack_path=str(tmp_path / 'pack.json'), days=1, every=(331, 337), engine_every=2,
                   procs=1, log=lambda *a: None)
    pj = _strict(tmp_path / 'par' / 'parity.json')
    assert pj['schema'] == L.SCHEMA_PARITY and pj['table_sha256'] == 'abc' and res['rows_checked'] >= 6
    rd = res['readings']
    assert len(rd) > 20 and np.mean([v['agreement'] for v in rd.values()]) > 0.97
    assert {k: v['agreement'] for k, v in rd.items() if k.startswith(('POS:', 'MACRO:', 'UTC1h', 'NY30m', 'Weekday'))} and \
        all(v['agreement'] == 1.0 for k, v in rd.items() if k.startswith(('POS:', 'UTC1h', 'NY30m', 'Weekday')))
    eng = res['engine']
    assert set(eng) == {'15m:RSI14', 'UTC4h', '15m:MOM10 sign'} and all(v['agreement'] == 1.0 for v in eng.values()), eng
    json.dump({'schema': 'oracle-heat-hm2-1', 'label': 'BTC~twin1', 'asset': 'BTC', 'twin': 1}, open(sd / 'meta.json', 'w'))
    with pytest.raises(SystemExit):
        L.parity('BTC', P['BTC'], str(sd), str(tmp_path / 'par2'), log=lambda *a: None)


def test_part_only_series_and_cli(built, tmp_path, capsys):
    """A series with --part files only is merged (summary counts add up exactly, candidate pools joined) and flagged
    incomplete; the CLI's live-ready and merge-gates write the pack."""
    import shutil
    src = built['d'] / 'inputs' / 'BTC'
    for i in (0, 1):
        d = tmp_path / 'parts' / f'BTC-p{i}'
        d.mkdir(parents=True)
        for f in ('summary_counts.json', 'candidates.csv.gz'):
            shutil.copy(src / f, d / f)
        mt = json.load(open(src / 'meta.json'))
        json.dump(dict(mt, part=[i, 2]), open(d / 'meta.json', 'w'))
    found = L.find_series(str(tmp_path / 'parts'))
    s = L.load_series(found['BTC'])
    one = hm.SummaryCounts.from_json(json.load(open(src / 'summary_counts.json'))['pair'])
    assert not s.complete and any('only --part files' in n for n in s.notes)
    assert np.array_equal(s.summ['pair'].c, 2 * one.c) and len(s.cands)
    pk = tmp_path / 'pack.json'
    shutil.copy(built['out'] / 'hm2_pack.json', pk)
    par = tmp_path / 'parity' / 'BTC'
    par.mkdir(parents=True)
    rows = _strict(pk)['rows']
    names = sorted({n for r in rows for n in r['readings']})
    json.dump({'schema': L.SCHEMA_PARITY, 'engine': {n: {'agreement': 1.0} for n in names}}, open(par / 'parity.json', 'w'))
    L.main(['live-ready', '--pack', str(pk), '--parity', str(tmp_path / 'parity'), '--out', str(tmp_path / 'ready.json')])
    rd = _strict(tmp_path / 'ready.json')
    assert all(r['live_ready'] for r in rd['rows']) and rd['live_reader_parity']['coins']['BTC']
    json.dump([{'kind': 'gate', 'coin': 'BTC', 'h': 15, 'key': 'g'}], open(tmp_path / 'g.json', 'w'))
    L.main(['merge-gates', '--pack', str(tmp_path / 'ready.json'), '--gates', str(tmp_path / 'g.json')])
    assert '1 gate rows merged' in capsys.readouterr().out
    g = _strict(tmp_path / 'ready.json')
    assert g['non_gate_sha256'] == L.non_gate_sha(rd) and g['rows'][-1]['key'] == 'g'


def test_never_doge(tmp_path):
    with pytest.raises(SystemExit):
        L.parity('DOGE', 'x.csv', str(tmp_path), str(tmp_path))
    d = tmp_path / 'inputs' / 'DOGE'
    d.mkdir(parents=True)
    json.dump({'schema': 'oracle-heat-hm2-1', 'label': 'DOGE', 'asset': 'DOGE'}, open(d / 'meta.json', 'w'))
    with pytest.raises(SystemExit):
        L.league(str(tmp_path / 'inputs'), '', str(tmp_path / 'out'), log=lambda *a: None)
    assert 'DOGE' not in L.COINS
