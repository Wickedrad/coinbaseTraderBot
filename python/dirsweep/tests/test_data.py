import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

import numpy as np
import pandas as pd

from dirsweep import data
from dirsweep import grid as G
from dirsweep import stage as S


def write_csv(path, first_day, days, beyond_value=None):
    t = G.ms(first_day) + np.arange(days * 1440) * G.MIN
    px = 100 + np.cumsum(np.random.default_rng(0).standard_normal(len(t))) * 0.01
    df = pd.DataFrame({'ts': t, 'o': px, 'h': px + 0.02, 'l': px - 0.02, 'c': px, 'v': 5.0, 'tb': 2.5})
    if beyond_value is not None:
        df.loc[df['ts'] >= G.ms('2020-01-08'), ['o', 'h', 'l', 'c']] = beyond_value
    df.to_csv(path, index=False)


class DataTest(unittest.TestCase):
    def test_no_minute_at_or_after_the_search_end_is_loaded(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, '1m.csv')
            write_csv(p, '2020-01-01', 12, beyond_value=1e9)
            with mock.patch.object(G, 'SEARCH_START', G.ms('2020-01-04')), mock.patch.object(G, 'SEARCH_END', G.ms('2020-01-08')):
                m = data.load(p)
            self.assertEqual(m['t0'], G.ms('2020-01-02'))                       # two warm-up days before the search start
            self.assertEqual(m['t0'] + m['n'] * G.MIN, G.ms('2020-01-08'))
            self.assertLess(float(np.max(m['o'])), 1e6)
            self.assertEqual(int(m['gap'].sum()), 0)
            self.assertIsNotNone(m['tb'])

    def test_guard_refuses_a_grid_that_runs_past_the_end(self):
        m = {'t0': G.SEARCH_END - 1000 * G.MIN - (G.SEARCH_END - 1000 * G.MIN) % G.DAY, 'n': 10 ** 7}
        with self.assertRaises(AssertionError):
            data.guard(m)

    def test_a_twin_keeps_the_calendar_and_flips_directions(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, '1m.csv')
            write_csv(p, '2020-01-01', 12)
            with mock.patch.object(G, 'SEARCH_START', G.ms('2020-01-04')), mock.patch.object(G, 'SEARCH_END', G.ms('2020-01-08')):
                real, tw = data.load(p), data.load(p, twin=1)
            self.assertEqual((real['t0'], real['n']), (tw['t0'], tw['n']))
            self.assertFalse(np.allclose(real['o'], tw['o']))
            self.assertTrue(np.allclose(real['v'], tw['v']))


class StageTest(unittest.TestCase):
    def test_emit_prints_one_aggregate_line_with_nulls_for_nan(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            S.emit('s1', {'x': float('nan'), 'y': np.float32(0.5), 'z': np.int64(3), 'w': [np.nan, 1.0]})
        line = buf.getvalue().strip()
        self.assertTrue(line.startswith('HEATLOOP ds {'))
        obj = json.loads(line[len('HEATLOOP ds '):])
        self.assertEqual(obj, {'part': 's1', 'x': None, 'y': 0.5, 'z': 3, 'w': [None, 1.0]})
        self.assertEqual(buf.getvalue().count('\n'), 1)


if __name__ == '__main__':
    unittest.main()


class RenderTest(unittest.TestCase):
    def test_league_and_matrix_render_without_error(self):
        from dirsweep import hist as H
        from dirsweep import oracle as O
        from dirsweep.tests.util import make_grid
        m = make_grid(8, seed=2, reversal=0.1)
        arr = H.cell_arrays(m, 0.01, 15, nd=8, day_off=0)
        periods = {'A': (0, 5), 'B': (5, 7), 'C': (7, 8)}
        lg = O.league(arr, 15, periods)
        lines = O.render_league(lg)
        self.assertTrue(lines[0].startswith('### h = 15'))
        self.assertGreaterEqual(len([x for x in lines if x.startswith('| ') and 'fade' in x or 'follow' in x]), 20)
        mx = O.matrix(arr, periods, 15)
        md = O.render_matrix(mx)
        self.assertGreater(len(md), 100)
        self.assertTrue(any('fade hit %' in x for x in md))
