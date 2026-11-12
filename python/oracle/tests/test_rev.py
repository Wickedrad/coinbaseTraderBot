"""Tests for the OR-H2 reversal variant (python/oracle/prereg/OR-H2.md): contract type 'perp-rev' through common / mine / ho1 on
the synthetic parts of oracle/fixtures_parts.py (one part per coin x target M, horizons read from the part's meta, pooled
scope per target). Nothing here is real data.

    cd python && python3 -m pytest -q oracle/tests/test_rev.py
"""
import json
import os

import numpy as np
import pytest

from oracle import ho1
from oracle.common import (DEV_END, MIN, SPLITS, Part, dev_rows, group_of, is_pooled, list_parts, pooled_name, split_of)
from oracle.fixtures_parts import PLANTED_ITEMS, make_part
from oracle.mine import freeze_scopes, main as mine_main, scope_names, load_dev
from oracle.tests.test_ho1 import NULL_ITEMS, registry, run_ho1, write_frozen, write_labels  # noqa: F401  (registry is a fixture)

FAST = ['--top', '5', '--beam', '30', '--shortlist', '100', '--draws', '400', '--quiet']


def build(root, mode='planted', seed=1):
    """BTC and ETH at M = 60 (horizons 5/15/60) and BTC at M = 100 (15/60)."""
    return [make_part(root, 'perp-rev', 'BTC-m60', mode, seed, hours=2, target_bps=60),
            make_part(root, 'perp-rev', 'ETH-m60', mode, seed + 1, hours=2, target_bps=60),
            make_part(root, 'perp-rev', 'BTC-m100', mode, seed + 2, hours=2, target_bps=100)]


@pytest.fixture(scope='module')
def planted(tmp_path_factory):
    root = str(tmp_path_factory.mktemp('rev_parts'))
    paths = build(root)
    out = str(tmp_path_factory.mktemp('rev_out'))
    res = mine_main(['--ct', 'perp-rev', '--parts', root, '--out', out, *FAST])
    return root, paths, out, res


def test_parts_listing_keeps_perp_and_perp_rev_apart(tmp_path):
    root = str(tmp_path)
    make_part(root, 'perp', 'BTC', 'planted', 1, hours=1)
    build(root)
    assert [os.path.basename(p) for p in list_parts(root, 'perp')] == ['perp-BTC']
    assert [os.path.basename(p) for p in list_parts(root, 'perp-rev')] == ['perp-rev-BTC-m100', 'perp-rev-BTC-m60', 'perp-rev-ETH-m60']
    with pytest.raises(ValueError):
        make_part(root, 'perp-rev', 'DOGE-m60', 'planted', 1, hours=1)


def test_groups_pooled_names_and_splits():
    assert group_of({'target_bps': 60}) == 'm60' and group_of({'target_bps': 17.5}) == 'm17p5' and group_of({}) is None
    assert pooled_name(None) == 'ALL' and pooled_name('m60') == 'ALL-m60'
    assert is_pooled('ALL') and is_pooled('ALL-m170') and not is_pooled('BTC-m60') and not is_pooled('ALLY')
    assert SPLITS['perp-rev'] == SPLITS['perp']                          # the perpetual A / B split
    # split_of works for any horizon: a 5-minute window ending exactly at DEV_END belongs to B, one minute later to nobody
    t = np.array([DEV_END - 5 * MIN, DEV_END - 4 * MIN, SPLITS['perp']['A'][1] - 5 * MIN, SPLITS['perp']['A'][1] - 4 * MIN], dtype=np.int64)
    assert list(split_of(t, 5, 'perp-rev')) == list(split_of(t, 5, 'perp')) == ['B', '', 'A', '']     # the A / B edge works the same way
    assert list(split_of(t[:2], 90, 'perp-rev')) == ['', '']
    assert list(dev_rows(t, 5)) == [True, False, True, True] and bool(dev_rows(t[:1], 240)[0]) is False


def test_load_dev_reads_the_parts_own_horizons(planted):
    root, paths, out, res = planted
    v = load_dev(paths[2], 'perp-rev')                                   # BTC-m100: no 5-minute labels
    assert v.meta['horizons'] == [15, 60] and not v.has('trade_L5') and v.has('trade_L15') and v.has('notional')
    assert np.all(np.asarray(v['t']) + 15 * MIN <= DEV_END)
    v = load_dev(paths[0], 'perp-rev')
    assert v.meta['horizons'] == [5, 15, 60] and v.has('trade_S5')
    with pytest.raises(ValueError):
        load_dev(paths[0], 'perp')


def test_scopes_cells_pooling_and_bhy_m(planted):
    root, paths, out, res = planted
    scopes = {s['scope'] for s in res['stage1']}
    assert scopes == {'BTC-m60', 'ETH-m60', 'ALL-m60', 'BTC-m100'}      # a pooled scope per target; M = 100 has one part; no 'ALL'
    cells = {(s['scope'], s['h']) for s in res['stage1']}
    assert ('BTC-m60', 5) in cells and ('ALL-m60', 5) in cells and ('BTC-m100', 5) not in cells and ('BTC-m100', 15) in cells
    # BHY m = every confirmed setup of the type, over all targets and horizons
    c = res['confirmed']
    assert len(c) == len(res['stage1']) and res['frozen']['m_confirmed'] == len(c)
    assert sum(1 for x in c if x['bhy_pass']) >= 1
    views = [load_dev(p, 'perp-rev') for p in list_parts(root, 'perp-rev')]
    assert scope_names(views) == ['BTC-m100', 'BTC-m60', 'ETH-m60', 'ALL-m60']                # the pooled scope of M = 60 last
    assert res['frozen']['freeze_scopes'] == ['BTC-m100', 'BTC-m60', 'ETH-m60', 'ALL-m60']
    assert res['frozen']['prereg'].endswith('OR-H2.md')
    assert freeze_scopes('perp', ['BTC', 'ETH']) == ['BTC', 'ETH', 'ALL']       # the OR-H1 rule is unchanged
    # the pooled scope sums the parts of its own target only
    a_pooled = next(s for s in res['stage1'] if s['scope'] == 'ALL-m60' and s['side'] == 'L' and s['h'] == 15 and s['rank'] == 1)
    a_parts = [next(s for s in res['stage1'] if s['scope'] == sc and s['side'] == 'L' and s['h'] == 15 and s['id'].split('-')[-1] == a_pooled['id'].split('-')[-1])
               for sc in ('BTC-m60', 'ETH-m60')]
    assert a_pooled['dev']['A']['n'] == sum(x['dev']['A']['n'] for x in a_parts)


def test_planted_setup_found_and_confirmed_with_cell_metrics(planted):
    root, paths, out, res = planted
    same = lambda s: sorted((i['f'], int(i['v'])) for i in s['items']) == sorted((i['f'], int(i['v'])) for i in PLANTED_ITEMS)
    for scope, hs in (('BTC-m60', (5, 15, 60)), ('ALL-m60', (5, 15, 60)), ('BTC-m100', (15, 60))):
        for h in hs:
            top = min((s for s in res['stage1'] if s['scope'] == scope and s['side'] == 'L' and s['h'] == h), key=lambda s: s['rank'])
            assert same(top), (scope, h, top['items'])
            c = next(x for x in res['confirmed'] if x['id'] == top['id'])
            B = c['dev']['B']
            assert c['survivor'] and c['bhy_pass'] and B['hit'] > B['base_hit'] + 0.15
            # reported per cell: trades/day, precision vs base, net bps, gross edge over matched random in bps, projected $/day
            notional = 300.0                                                  # min(300, 5 / (M / 1e4)) for M = 60 and 100
            assert B['notional_usd'] == notional
            assert B['trades_day'] == pytest.approx(B['trades'] / B['days'])
            assert B['net_bps'] == pytest.approx(B['usd_total'] / B['trades'] / notional * 1e4, rel=1e-9)
            assert B['edge_bps'] == pytest.approx(B['net_bps'] - B['placebo_bps']) and B['edge_bps'] > 0
            assert B['precision_lift'] == pytest.approx(B['hit'] - B['base_hit']) and B['usd_day'] > B['placebo_usd_day']
    md = open(os.path.join(out, 'report.md')).read()
    assert '## Reversal cells (OR-H2' in md and '| BTC-m60 L5 |' in md and '| ALL-m60 L15 |' in md and '| BTC-m100 L60 |' in md
    assert 'trades/day' in md and 'edge bps' in md and 'N_raw' in md
    assert os.path.exists(os.path.join(out, 'instances', 'BTC-m60-L5.csv.gz')) and os.path.exists(os.path.join(out, 'lift', 'ALL-m60-S60.csv'))


def test_null_fixture_has_no_survivors(tmp_path):
    root = str(tmp_path / 'p')
    build(root, 'null', seed=21)
    res = mine_main(['--ct', 'perp-rev', '--parts', root, '--out', str(tmp_path / 'o'), *FAST])
    assert len(res['confirmed']) > 0
    assert sum(1 for c in res['confirmed'] if c['survivor']) == 0 and res['frozen']['setups'] == []


def test_ho1_scores_perp_rev_with_per_target_pooled_scopes(tmp_path, registry):
    root = str(tmp_path / 'p')
    paths = build(root)
    labels = write_labels(str(tmp_path / 'labels.csv.gz'), ['BTC', 'ETH'])
    spec = [{'scope': 'ALL-m60', 'side': 'L', 'h': 15, 'items': PLANTED_ITEMS}, {'scope': 'BTC-m100', 'side': 'L', 'h': 60, 'items': PLANTED_ITEMS},
            {'scope': 'ALL-m60', 'side': 'L', 'h': 5, 'items': NULL_ITEMS[0]}, {'scope': 'ETH-m60', 'side': 'S', 'h': 60, 'items': NULL_ITEMS[1]}]
    frozen, doc = write_frozen(str(tmp_path / 'mine'), 'perp-rev', spec, paths)
    res = run_ho1(frozen, root, labels, str(tmp_path / 'out'), registry)
    S = res['summary']
    assert S['family'] == 'oracle-perp-rev-v1' and S['contract_type'] == 'perpetual' and S['prereg'].endswith('OR-H2.md')
    assert {r['family'] for r in res['rows']} == {'oracle-perp-rev-v1'}
    arms = {s['arm']: s for s in S['setups']}
    pooled = next(s for s in S['setups'] if s['scope'] == 'ALL-m60' and s['h'] == 15 and s['items'] == PLANTED_ITEMS)
    # ALL-m60 trades BTC-m60 and ETH-m60 only, never the M = 100 part
    assert set(pooled['ho1']['by_cell']) == {'BTC-m60', 'ETH-m60'}
    one = next(s for s in S['setups'] if s['scope'] == 'BTC-m100')
    assert set(one['ho1']['by_cell']) == {'BTC-m100'} and one['h'] == 60
    assert pooled['verdict']['pass'], pooled['verdict']['why']
    assert pooled['ho1']['hit'] > pooled['ho1']['base_hit']
    null5 = next(s for s in S['setups'] if s['h'] == 5)
    assert not null5['verdict']['pass']
    assert S['book'] is not None and 'across all coins' in S['book']['positions']
    # one position at a time across all coins and targets: no two taken book trades overlap
    legs, detail = ho1.book_legs(sorted(doc['setups'], key=lambda s: s['rank']), ho1.resolve_parts(doc, root, 'perp-rev'), 'perp-rev')
    t, hold = detail['t'], detail['hold']
    assert len(t) > 0 and np.all(t[1:] >= t[:-1] + np.maximum(hold[:-1], 1) * MIN)
    rows = [json.loads(line) for line in open(str(tmp_path / 'out' / 'rows.jsonl'))]
    assert any(r.get('env', {}).get('ORACLE_TARGET_BPS') == '60' for r in rows)
    assert os.path.exists(str(tmp_path / 'out' / 'ho1.md')) and 'OR-H2' in open(str(tmp_path / 'out' / 'ho1.md')).read()
