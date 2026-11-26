import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from heatloop import coverage as cv
from heatloop import guards as g


def minutes(a, b, skip=()):
    return [t for t in range(g.ms(a), g.ms(b), g.MIN) if t not in set(skip)]


class Coverage(unittest.TestCase):
    def test_counts_rows_first_last_and_missing_minutes_per_month(self):
        gap = [g.ms('2025-08-10') + i * g.MIN for i in range(30)]
        ts = minutes('2025-07-01', '2025-09-01', skip=gap)
        r = cv.report(ts, 'btc')
        self.assertEqual(r['first'], '2025-07-01 00:00')
        self.assertEqual(r['last'], '2025-08-31 23:59')
        self.assertEqual(r['months']['2025-07'], [31 * 1440, 0])
        self.assertEqual(r['months']['2025-08'], [31 * 1440 - 30, 30])

    def test_last_month_is_measured_to_the_last_minute_on_file(self):
        ts = minutes('2026-11-01', '2026-11-03')
        r = cv.report(ts, 'ETH')
        self.assertEqual(r['months']['2026-11'], [2 * 1440, 0])

    def test_duplicates_and_order_do_not_matter(self):
        ts = minutes('2025-07-01', '2025-07-02')
        r = cv.report(ts[::-1] + ts[:5], 'XRP')
        self.assertEqual(r['rows'], 1440)

    def test_empty_file(self):
        self.assertEqual(cv.report([], 'BTC'), {'coin': 'BTC', 'rows': 0})

    def test_reads_only_the_ts_column(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, '1m.csv')
            with open(p, 'w') as f:
                f.write('ts,o,h,l,c,v\n')
                f.write(f"{g.ms('2025-07-01')},1,2,0.5,1.5,3\n")
            buf = io.StringIO()
            with mock.patch.object(sys, 'argv', ['coverage', '--coin', 'btc', '--csv', p]), redirect_stdout(buf):
                cv.main()
            line = buf.getvalue().strip()
            self.assertTrue(line.startswith('HEATLOOP coverage '))
            self.assertEqual(json.loads(line[len('HEATLOOP coverage '):])['coin'], 'BTC')

    def test_never_doge(self):
        with mock.patch.object(sys, 'argv', ['coverage', '--coin', 'doge', '--csv', 'x']):
            with self.assertRaises(SystemExit):
                cv.main()


if __name__ == '__main__':
    unittest.main()
