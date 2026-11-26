import os
import tempfile
import unittest

import numpy as np

from heatloop import events as E


class FakeEngine:
    """tf_codes returns one reading per wanted base; events_at gives fixed (bar, key) pairs so the row mapping is checked."""
    def __init__(self, ev):
        self.ev, self.calls = ev, []

    def grid(self, df, end_ms=None):
        return {'n': len(df), 't0': int(df['ts'].iloc[0]), 'rows': len(df), 'end': end_ms}

    def tf_codes(self, m, k, edges, step, window=None, want_bases=None):
        self.calls.append((k, sorted(want_bases), window))
        return [{'name': b} for b in sorted(want_bases)], {}, 0

    def events_at(self, r, lo, hi):
        return [(b, key) for b, key in self.ev.get(r['name'], []) if lo <= b < hi]


class Mapping(unittest.TestCase):
    def test_bases_per_bar_size_and_sign_readings(self):
        got = E.bases_by_tf(['5m:RSI14=low', '5m:RSI14=high', '1m:PVI sign=above 0', '60m:ADX=high', '9m:X=y'])
        self.assertEqual(got, {5: {'5m:RSI14'}, 1: {'1m:PVI sign', '1m:PVI'}, 60: {'60m:ADX'}})

    def test_entry_row_is_the_next_minute_after_the_bar_closes(self):
        eng = FakeEngine({'5m:RSI14': [(0, '5m:RSI14=low'), (3, '5m:RSI14=low'), (3, '5m:RSI14=other')]})
        m = {'n': 100}
        got = E.event_rows(m, {'edges': {}, 'price_step': 0.01}, ['5m:RSI14=low'], 0, 100, engine=eng)
        self.assertEqual(got, [(5, '5m:RSI14=low'), (20, '5m:RSI14=low')])       # bar 0 closes at minute 4: entry minute 5; bar 3 -> 20
        self.assertEqual(eng.calls[0][2], None)                                  # the whole grid, no window

    def test_rows_outside_the_range_or_the_grid_are_dropped(self):
        eng = FakeEngine({'1m:A': [(0, '1m:A=x'), (49, '1m:A=x'), (98, '1m:A=x'), (99, '1m:A=x')]})
        got = E.event_rows({'n': 100}, {}, ['1m:A=x'], 50, 100, engine=eng)
        self.assertEqual(got, [(50, '1m:A=x'), (99, '1m:A=x')])                 # bar 49 -> 50 and bar 98 -> 99 are in; bar 99 -> 100 is past the grid; bar 0 is before the range
        self.assertEqual(E.event_rows({'n': 100}, {}, ['1m:A=x'], 0, 50, engine=eng), [(1, '1m:A=x')])

    def test_grid_stops_at_the_scope_end(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, '1m.csv')
            with open(p, 'w') as f:
                f.write('ts,o,h,l,c,v\n')
                for t in range(10):
                    f.write(f'{t * 60000},1,2,0.5,1.5,3\n')
            eng = FakeEngine({})
            g = E.load_grid(p, 120000, 360000, engine=eng)
            self.assertEqual((g['rows'], g['end']), (4, 360000))                 # minutes 2..5 only: nothing at or after the end, nothing before the start

    def test_the_reader_stops_before_a_chunk_that_starts_at_the_end(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, '1m.csv')
            with open(p, 'w') as f:
                f.write('ts,o,h,l,c,v\n')
                for t in range(10):
                    f.write(f'{t * 60000},1,2,0.5,1.5,3\n')
                f.write('not a number,x,x,x,x,x\n')                             # a later chunk that would break the parse if it were read
            df = E.read_bars(p, 60000, 240000, chunk=3)
            self.assertEqual(df['ts'].tolist(), [60000, 120000, 180000])
            self.assertLess(int(df['ts'].max()), 240000)

    def test_an_unordered_file_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, '1m.csv')
            with open(p, 'w') as f:
                f.write('ts,o,h,l,c,v\n')
                for t in (0, 1, 2, 5, 3, 4):
                    f.write(f'{t * 60000},1,2,0.5,1.5,3\n')
            with self.assertRaises(ValueError):
                E.read_bars(p, 0, 10 * 60000, chunk=3)


if __name__ == '__main__':
    unittest.main()
