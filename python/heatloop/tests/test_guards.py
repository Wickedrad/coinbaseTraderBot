import os
import unittest
from unittest import mock

from heatloop import guards as g


class Scope(unittest.TestCase):
    def test_heat_end_is_the_tables_cut(self):
        from oracle import heat   # the loop's cut equals the engine's, so no table ever saw a 2026 minute
        self.assertEqual(g.HEAT_END, heat.HEAT_END)

    def test_dev_is_the_first_half_of_2026(self):
        self.assertEqual(g.scope_range('dev'), (g.ms('2026-01-01'), g.ms('2026-07-01')))

    def test_dev_window_inside_passes_and_outside_raises_not_clips(self):
        lo, hi = g.ms('2026-02-01'), g.ms('2026-03-01')
        self.assertEqual(g.window(lo, hi, 'dev'), (lo, hi))
        with self.assertRaises(g.OutOfScope):
            g.window(lo, g.ms('2026-07-01') + g.MIN, 'dev')            # one minute into VAL
        with self.assertRaises(g.OutOfScope):
            g.window(g.ms('2025-12-31'), hi, 'dev')                    # before DEV
        with self.assertRaises(g.OutOfScope):
            g.window(hi, lo, 'dev')                                    # empty

    def test_dev_never_loads_a_val_minute_as_history(self):
        self.assertEqual(g.history_limit('dev'), g.ms('2026-07-01'))

    def test_val_needs_its_end_and_the_flag(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop('HEATLOOP_VAL', None)
            with self.assertRaises(g.OutOfScope):
                g.scope_range('val')                                   # no end set
            with self.assertRaises(g.OutOfScope):
                g.scope_range('val', val_end=g.ms('2026-11-01'))       # no flag
        with mock.patch.dict(os.environ, {'HEATLOOP_VAL': '1'}):
            self.assertEqual(g.scope_range('val', val_end=g.ms('2026-11-01')), (g.ms('2026-07-01'), g.ms('2026-11-01')))
            with self.assertRaises(g.OutOfScope):
                g.window(g.ms('2026-07-01'), g.ms('2026-11-02'), 'val', val_end=g.ms('2026-11-01'))

    def test_final_needs_a_verified_freeze(self):
        with self.assertRaises(g.OutOfScope):
            g.scope_range('final')
        self.assertEqual(g.scope_range('final', final=(5, 9)), (5, 9))

    def test_unknown_scope_raises(self):
        with self.assertRaises(g.OutOfScope):
            g.scope_range('test')


if __name__ == '__main__':
    unittest.main()
