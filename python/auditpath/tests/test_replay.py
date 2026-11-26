import contextlib
import gzip
import io
import json
import os
import random
import shutil
import tempfile
import unittest
from collections import Counter

import numpy as np

from auditpath import replay as R

T0 = R.parse_day('2026-08-01')


def bars(n, start_ms, seed=1, gap_at=()):
    """n synthetic one-minute bars (a random walk) opening at start_ms, as the (n, 7) array of the reader's minute cache."""
    rng = np.random.default_rng(seed)
    c = 60000 * np.exp(np.cumsum(rng.normal(0, 0.0007, n)))
    o = np.concatenate(([c[0]], c[:-1]))
    h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.0003, n)))
    lo = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.0003, n)))
    v = rng.uniform(1, 50, n)
    arr = np.column_stack([start_ms + np.arange(n) * R.MIN_MS, o, h, lo, c, v, v * rng.uniform(0.3, 0.7, n)])
    return np.delete(arr, list(gap_at), axis=0) if gap_at else arr


def row(key, rank, heat=10.0, d=1, kind='single', h=15, trig=None, aliases=None, bar_close=0, tf=15):
    r = {'key': key, 'kind': kind, 'aliases': aliases or [], 'tf': tf, 'h': h, 'dir': d, 'rank': rank, 'of': 40, 'heat': heat,
         'share': 0.5, 'odds': 1.0, 'barClose': bar_close}
    if trig is not None:
        r['trig'] = trig
    return r


def file_of(coins, written):
    return {'v': 1, 'source': 'oracle-heat', 'run': 'r', 'packSha': 'x', 'writtenAt': written, 'coins': coins}


class FakeTables:
    run, pack_sha, top = 'r', 'x', 40

    def __init__(self, coin):
        self.coins = {coin: object()}


def node_cwd():
    """A folder `node --import tsx` works from: AUDITPATH_NODE_CWD, or the repository when npm ci has run."""
    for d in (os.environ.get('AUDITPATH_NODE_CWD'), R.REPO_DIR):
        if d and os.path.isdir(os.path.join(d, 'node_modules', 'tsx')) and shutil.which('node'):
            return d
    return None


class ShardTest(unittest.TestCase):
    def test_parse_day(self):
        self.assertEqual(R.parse_day('1970-01-02'), 86_400_000)
        with self.assertRaises(R.ReplayError):
            R.parse_day('2026-8-1')

    def test_closes_cover_whole_days_both_ends(self):
        c = R.closes_for(T0, T0 + R.DAY_MS)
        self.assertEqual(len(c), 2 * 1440)
        self.assertEqual(c[0], T0)
        self.assertEqual(c[-1], T0 + 2 * R.DAY_MS - R.MIN_MS)       # 23:59 of the last day
        self.assertEqual(R.closes_for(T0, T0, limit=600)[-1], T0 + 599 * R.MIN_MS)

    def test_blocks_cover_the_period_exactly_once(self):
        end = R.parse_day('2026-11-04')
        seen, day = [], T0
        while day <= end:
            last = min(day + 13 * R.DAY_MS, end)
            seen += R.closes_for(day, last)
            day = last + R.DAY_MS
        self.assertEqual(len(seen), len(set(seen)))
        self.assertEqual(len(seen), 96 * 1440)
        self.assertEqual(seen, R.closes_for(T0, end))

    def test_shard_must_start_on_the_hour(self):
        with self.assertRaises(R.ReplayError):
            R.closes_for(T0 + 30 * R.MIN_MS, T0 + R.DAY_MS)
        with self.assertRaises(R.ReplayError):
            R.closes_for(T0 + R.DAY_MS, T0)

    def test_load_bars_filters_sorts_and_drops_duplicates(self):
        b = bars(10, T0)
        lines = ['ts,o,h,l,c,v,tb'] + [','.join(repr(float(x)) if i else str(int(x)) for i, x in enumerate(r)) for r in b[[3, 1, 2, 2, 5, 9, 0]]]
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, '1m.csv')
            with open(p, 'w') as f:
                f.write('\n'.join(lines) + '\n')
            got = R.load_bars(p, T0 + R.MIN_MS, T0 + 9 * R.MIN_MS)
        self.assertEqual(list(got[:, 0]), [T0 + k * R.MIN_MS for k in (1, 2, 3, 5)])


class NoLookAheadTest(unittest.TestCase):
    def run_stub(self, rows, closes):
        seen = []

        def read(table, rws, t, window, long):
            seen.append((t, float(rws[-1, 0]), float(rws[:, 0].max()), float(rws[-1, 4])))
            return {'ok': True, 'calls': [row(f'k{int(rws[-1, 4])}', 1, bar_close=t)]}, {}

        out = {}
        R.read_minutes(read, rows, closes, 'BTC', FakeTables('BTC'), 3000, object(), Counter(),
                       lambda t, f: out.__setitem__(t, json.dumps(f, sort_keys=True)))
        return seen, out

    def test_reader_sees_only_bars_before_the_close(self):
        rows = bars(300, T0 - 100 * R.MIN_MS)
        closes = R.closes_for(T0, T0)[:60]
        seen, _ = self.run_stub(rows, closes)
        self.assertEqual(len(seen), 60)
        for t, last, mx, _c in seen:
            self.assertEqual(last, t - R.MIN_MS)       # the newest bar is the one that just closed
            self.assertLess(mx, t)                     # and nothing opened at or after the close is visible

    def test_changing_bars_after_a_close_leaves_that_close_unchanged(self):
        a = bars(300, T0 - 100 * R.MIN_MS)
        cut = T0 + 30 * R.MIN_MS
        b = a.copy()
        b[b[:, 0] >= cut, 1:] *= 1.37                  # every bar that opened at or after the cut is altered
        closes = R.closes_for(T0, T0)[:60]
        _, out_a = self.run_stub(a, closes)
        _, out_b = self.run_stub(b, closes)
        before = [t for t in closes if t <= cut]
        self.assertTrue(before)
        for t in before:
            self.assertEqual(out_a[t], out_b[t])       # the close at the cut reads bars up to cut - 1 minute only
        for t in closes:
            if t > cut:
                self.assertNotEqual(out_a[t], out_b[t])

    def test_a_close_without_its_bar_is_not_read(self):
        rows = bars(300, T0 - 100 * R.MIN_MS, gap_at=[100 + 5])     # the bar that opened at T0 + 5 min is missing
        closes = R.closes_for(T0, T0)[:10]
        stats = Counter()
        got = []
        R.read_minutes(lambda *a: ({'ok': True, 'calls': [row('k', 1)]}, {}), rows, closes, 'BTC', FakeTables('BTC'), 3000, object(), stats,
                       lambda t, f: got.append(t))
        self.assertEqual(stats['minutes_missing_bar'], 1)
        self.assertNotIn(T0 + 6 * R.MIN_MS, got)       # the close at 00:06 would read the missing 00:05 bar
        self.assertIn(T0 + 5 * R.MIN_MS, got)

    def test_not_ok_and_other_horizons_make_no_file(self):
        rows = bars(300, T0 - 100 * R.MIN_MS)
        stats, got = Counter(), []
        replies = iter([({'ok': False, 'why': 'gap', 'calls': []}, {}),
                        ({'ok': True, 'calls': [row('a', 1, h=240), row('b', 1, h=1440)]}, {}),
                        ({'ok': True, 'calls': [row('c', 1, h=15), row('d', 1, h=240)]}, {})])
        R.read_minutes(lambda *a: next(replies), rows, R.closes_for(T0, T0)[:3], 'BTC', FakeTables('BTC'), 3000, object(), stats,
                       lambda t, f: got.append(f))
        self.assertEqual((stats['minutes_not_ok'], stats['minutes_read']), (1, 2))
        self.assertEqual(len(got), 1)
        self.assertEqual([c['key'] for c in got[0]['coins']['BTC']['calls']], ['c'])
        self.assertEqual(got[0]['writtenAt'], T0 + 2 * R.MIN_MS + R.WRITE_LAG_MS)


class FiringRowTest(unittest.TestCase):
    def decide(self, calls, t=T0 + 5 * R.MIN_MS):
        f = file_of({'BTC': {'asOf': t, 'tableSha': 't', 'ok': True, 'calls': calls}}, t + R.WRITE_LAG_MS)
        return R.lane_decide_py(t + R.TICK_LAG_MS, f)

    def test_rows_of_the_close_fire_and_older_ones_do_not(self):
        t = T0 + 5 * R.MIN_MS
        fresh = row('15m:A=x', 3, bar_close=t)
        old = row('15m:B=x', 1, bar_close=t - R.MIN_MS)            # one minute old: past the 45 s lag
        got = self.decide([fresh, old], t)
        self.assertEqual([d['row']['key'] for d in got['fresh']], ['15m:A=x'])
        self.assertEqual(got['fresh'][0]['fired'], 1)

    def test_top_ten_and_one_call_per_horizon(self):
        t = T0
        got = self.decide([row('a', 11, bar_close=t), row('b', 4, bar_close=t, d=-1), row('c', 2, bar_close=t, h=60),
                           row('d', 3, bar_close=t, h=240)], t)
        self.assertEqual({(d['h'], d['row']['key']) for d in got['fresh']}, {(15, 'b'), (60, 'c')})

    def test_pair_refines_its_single_and_a_conflict_is_skipped(self):
        t = T0
        single = row('s', 5, heat=9, d=1, bar_close=t)
        pair = row('s | p', 20, heat=50, d=-1, kind='pair', trig='s', bar_close=t)
        got = self.decide([single, pair], t)
        self.assertEqual(got['fresh'], [])
        self.assertEqual(got['unfit'][0]['row']['key'], 's | p')
        self.assertEqual(got['unfit'][0]['row']['rank'], 5)         # the replacement keeps the hotter rank
        self.assertTrue(got['unfit'][0]['why'].startswith('pair against single'))
        rows = R.rows_of(got, t)
        self.assertEqual(rows[0]['skip'], 'pair_against_single')
        self.assertEqual((rows[0]['single_key'], rows[0]['single_dir'], rows[0]['t0']), ('s', 1, t // 1000))
        agree = row('s | q', 20, heat=50, d=1, kind='pair', trig='s', bar_close=t)
        self.assertEqual(self.decide([single, agree], t)['fresh'][0]['row']['key'], 's | q')

    def test_alias_is_one_event(self):
        t = T0
        a = row('a', 1, d=1, aliases=['b'], bar_close=t)
        b = row('b', 2, d=-1, bar_close=t)
        got = self.decide([a, b], t)['fresh'][0]
        self.assertEqual((got['fired'], got['against']), (1, 0))


def random_case(rng, now):
    names = [f'k{i}' for i in range(7)]
    rows = []
    for i in range(rng.randint(0, 14)):
        kind = rng.choice(['single', 'single', 'pair', 'triple'])
        key = rng.choice(names) if kind == 'single' else f'{rng.choice(names)} | p{rng.randint(0, 5)}'
        r = row(key, rng.choice([1, 2, 2.5, 3, 5, 9, 10, 11, 30]), heat=rng.choice([1.0, 2.0, 2.0, 7.5]), d=rng.choice([1, -1]), kind=kind,
                h=rng.choice([15, 15, 60, 240]), aliases=rng.sample(names, rng.randint(0, 2)),
                bar_close=now - R.TICK_LAG_MS - rng.choice([0, 0, 0, 0, 40_000, 60_000]))
        if kind != 'single':
            r['trig'] = rng.choice(names + ['k_other', ''])
        rows.append(r)
    return rows


class DecideParityTest(unittest.TestCase):
    """The Python port of the lane's rule equals the original TypeScript (readHeatCalls and decideCall)."""

    def test_port_equals_the_typescript_on_generated_cases(self):
        cwd = node_cwd()
        if cwd is None:
            self.skipTest('node and tsx are not installed here (npm ci, or AUDITPATH_NODE_CWD)')
        rng = random.Random(20261125)
        lines, now0 = [], 1_790_000_000_000
        for i in range(600):
            now = now0 + i * 60_000 + R.TICK_LAG_MS
            coins = {c: {'asOf': now - R.TICK_LAG_MS, 'tableSha': 't', 'ok': rng.random() > 0.05, 'calls': random_case(rng, now)}
                     for c in ('BTC', 'ETH')}
            lines.append(json.dumps({'id': i, 'now': now, 'file': file_of(coins, now - 3000)}))
        ts_out = R.decide_ts(lines, cwd)
        py_out = R.decide_lines(lines, 'py', cwd)
        decided = 0
        for line, a, b in zip(lines, ts_out, py_out):
            self.assertEqual(a['id'], b['id'])
            now = json.loads(line)['now']
            # The lane also decides the perps' horizons (240, 1440); the port and the table keep the two contract horizons.
            ra = R.rows_of({'fresh': a['fresh'], 'unfit': a['unfit']}, now - R.TICK_LAG_MS)
            ra = [r for r in ra if r['h'] in R.HORIZONS]
            rb = R.rows_of(b, now - R.TICK_LAG_MS)
            self.assertEqual(ra, rb, line[:200])
            decided += len(ra)
        self.assertGreater(decided, 300)


class ErrorTextTest(unittest.TestCase):
    def test_lane_failure_text_is_not_echoed(self):
        secret = 'ROW{"key":"SECRET-ROW"}'
        class P:
            returncode = 1
            stderr = secret
        orig = R.subprocess.run
        R.subprocess.run = lambda *a, **k: P()
        try:
            with self.assertRaises(R.ReplayError) as cm:
                R.decide_ts(['{"id":1}'], '.')
        finally:
            R.subprocess.run = orig
        self.assertNotIn('SECRET', str(cm.exception))
        self.assertIn('exit code 1', str(cm.exception))

    def test_lane_refusal_text_is_not_echoed(self):
        with self.assertRaises(R.ReplayError) as cm:
            R.rows_of({'error': 'bad row {"key":"SECRET-ROW"}'}, 1000)
        self.assertNotIn('SECRET', str(cm.exception))


class OutputTest(unittest.TestCase):
    def test_same_rows_same_bytes_whatever_the_time(self):
        rows = [{'asset': 'BTC', 'h': 15, 't0': 1, 'dir': 1, 'key': 'k', 'skip': None}]
        with tempfile.TemporaryDirectory() as d:
            a, b = os.path.join(d, 'a.gz'), os.path.join(d, 'b.gz')
            sa = R.write_table(a, rows)
            os.utime(a, (1, 1))
            sb = R.write_table(b, rows)
            self.assertEqual(sa, sb)
            with gzip.open(b, 'rt') as f:
                self.assertEqual(json.loads(f.readline())['key'], 'k')

    def test_aggregates_count_pairs_and_skips(self):
        rows = [dict(asset='BTC', h=15, dir=1, kind='single', skip=None), dict(asset='BTC', h=15, dir=-1, kind='pair', skip=None),
                dict(asset='BTC', h=15, dir=-1, kind='triple', skip='pair_against_single'), dict(asset='BTC', h=60, dir=1, kind='pair', skip=None)]
        a = R.aggregates(rows)
        self.assertEqual((a['15']['decided'], a['15']['up'], a['15']['down'], a['15']['skipped_pair_against_single']), (2, 1, 1, 1))
        self.assertEqual(a['15']['share_pair_or_triple'], 0.5)
        self.assertEqual(a['60']['share_pair_or_triple'], 1.0)


def have_reader():
    try:
        import pandas  # noqa: F401
        import talib  # noqa: F401
        return True
    except ImportError:
        return False


@unittest.skipUnless(have_reader(), 'TA-Lib and pandas (python/heat_reader/requirements.txt) are not installed')
class RealReaderTest(unittest.TestCase):
    """The real read_coin on synthetic bars with a short window: shards and look-ahead, end to end through main()."""
    WINDOW = 300

    @classmethod
    def setUpClass(cls):
        from heat_reader.engine import Engine
        need = Engine(R.PYTHON_DIR).need_minutes(cls.WINDOW, [1, 5, 15, 60])
        cls.dir = tempfile.mkdtemp()
        cls.rows = bars(need + 60 + 300, T0 - (need + 120) * R.MIN_MS, seed=7)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def csv(self, name, rows):
        p = os.path.join(self.dir, name)
        np.savetxt(p, rows, delimiter=',', header='ts,o,h,l,c,v,tb', comments='', fmt=['%d'] + ['%.6f'] * 6)
        return p

    def run_main(self, bars_path, out, frm, to, limit):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = R.main(['calls', '--coin', 'BTC', '--bars', bars_path, '--from', frm, '--to', to, '--out', out, '--limit-minutes', str(limit),
                           '--decider', 'py', '--window', str(self.WINDOW)])
        self.assertEqual(code, 0, buf.getvalue()[:300])
        agg = json.loads(buf.getvalue().split('AUDITPATH replay ', 1)[1])
        with gzip.open(out, 'rt') as f:
            return agg, [json.loads(x) for x in f]

    def test_look_ahead_and_shards(self):
        full_csv = self.csv('full.csv', self.rows)
        agg, rows = self.run_main(full_csv, os.path.join(self.dir, 'full.gz'), '2026-08-01', '2026-08-01', 180)
        self.assertEqual(agg['minutes_read'], 180)
        self.assertGreater(len(rows), 0)
        # Bars changed from 02:00 on: the closes before 02:00 are read unchanged, so their rows are the same.
        cut = T0 + 120 * R.MIN_MS
        alt = self.rows.copy()
        alt[alt[:, 0] >= cut, 1:] *= 1.21
        agg2, rows2 = self.run_main(self.csv('alt.csv', alt), os.path.join(self.dir, 'alt.gz'), '2026-08-01', '2026-08-01', 180)
        early = lambda rs: [r for r in rs if r['t0'] * 1000 <= cut]
        self.assertEqual(early(rows), early(rows2))
        self.assertGreater(len(early(rows)), 0)
        self.assertNotEqual([r for r in rows if r['t0'] * 1000 > cut], [r for r in rows2 if r['t0'] * 1000 > cut])

    def test_a_shard_starting_at_a_later_hour_gives_the_same_rows(self):
        from heat_reader import config
        from heat_reader.engine import Engine
        from heat_reader.pack import Tables
        from heat_reader.reader import LongStates, read_coin
        s = config.load(['--window-bars', str(self.WINDOW)], env={})
        engine = Engine(s.oracle_path)
        tables = Tables(s.pack_dir, s.assets, s.run, s.max_rank, s.clock_pack, s.perp_packs)
        tables.refresh()
        for t in tables.coins.values():
            t.check_edges(engine.zone_levels, engine.zone_states)

        def files(closes):
            got = {}
            R.read_minutes(lambda tb, rws, t, w, lg: read_coin(engine, tb, tables.top, rws, t, w, lg), self.rows, closes, 'BTC', tables,
                           self.WINDOW, LongStates(), Counter(), lambda t, f: got.__setitem__(t, json.dumps(f, sort_keys=True)))
            return got

        whole = files([T0 + k * R.MIN_MS for k in range(0, 150)])
        late = files([T0 + k * R.MIN_MS for k in range(60, 150)])        # starts at 01:00, an hourly boundary
        self.assertGreater(len(late), 0)
        for t, f in late.items():
            self.assertEqual(whole[t], f)
        self.assertEqual({t for t in whole if t >= T0 + 60 * R.MIN_MS}, set(late))


if __name__ == '__main__':
    unittest.main()
