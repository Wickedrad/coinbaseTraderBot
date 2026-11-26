import os
import tempfile
import unittest

import numpy as np

from subminute import daytypes as DT
from subminute import fresh as FR
from subminute.tests.test_daytypes import write_weekend
from subminute.tests.test_fampockets import DAY0


def d(n):
    return str(np.datetime64('1970-01-01') + np.timedelta64(DAY0 + n, 'D'))


BLOCKS = {'build': (d(0), d(27)), 'check': (d(28), d(41)), 'clean': (d(42), d(55)), 'fresh': (d(56), d(83))}


class FreshTest(unittest.TestCase):
    def read(self, yes_on_weekend):
        t = tempfile.mkdtemp()
        write_weekend(t, days=84, yes_on_weekend=yes_on_weekend)
        w = DT.load(t, 'm15', ['AAA'], log=lambda *x: None)
        return FR.read(w, BLOCKS, ('yes', '0.5', '1'), 'wkend', 'weekend', perms=300)

    def test_a_weekend_edge_that_keeps_going_is_supported_on_the_fresh_days(self):
        r = self.read(True)
        self.assertEqual({x['scope'] for x in r['rows']}, {'AAA', 'ALL'})
        x = [x for x in r['rows'] if x['scope'] == 'ALL'][0]
        for b in ('build', 'check', 'clean', 'fresh'):
            self.assertGreater(x[b]['net_c'], 0)                           # the rule wins on the typed days in every block, the fresh one too
            self.assertLess(x[b + '_other']['net_c'], 0)
        self.assertEqual(FR.verdict(x, min_fills=5)['verdict'], 'supported')
        self.assertLess(x['fresh_permutation_p'], 0.05)                    # a random pick of the same number of days does not do as well
        self.assertEqual(r['blocks']['fresh'][2], 28)

    def test_an_edge_that_stops_is_contradicted(self):
        r = self.read(False)                                               # the weekend rule loses on every weekend
        x = [x for x in r['rows'] if x['scope'] == 'ALL'][0]
        self.assertLess(x['fresh']['net_c'], 0)
        self.assertEqual(FR.verdict(x, min_fills=5)['verdict'], 'contradicted')

    def test_too_few_fills_is_too_thin(self):
        r = self.read(True)
        x = [x for x in r['rows'] if x['scope'] == 'ALL'][0]
        self.assertEqual(FR.verdict(x, min_fills=10 ** 9)['verdict'], 'too thin')

    def test_the_cut_points_come_from_the_build_block_only(self):
        r = self.read(True)
        self.assertEqual(r['cuts_from_build'], {'wkend': [5]})


if __name__ == '__main__':
    unittest.main()
