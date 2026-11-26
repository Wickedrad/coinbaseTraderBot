import io
import unittest
import zipfile

import numpy as np
import pandas as pd

from dirsweep import topup as T

DAY = '2026-11-23'


def zip_of(rows, header=False) -> bytes:
    lines = ['open_time,open,high,low,close,volume,close_time,quote_volume,count,taker_buy_volume,taker_buy_quote_volume,ignore'] if header else []
    lines += [','.join(str(x) for x in r) for r in rows]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr('BTCUSDT-1m-2026-11-23.csv', '\n'.join(lines) + '\n')
    return buf.getvalue()


def kline(ts, o=100.0, h=101.0, l=99.0, c=100.5, v=3.0, tb=1.25, unit=1):
    return [ts * unit, o, h, l, c, v, (ts + 59_999) * unit, v * c, 7, tb, tb * c, 0]


class ParseTest(unittest.TestCase):
    def setUp(self):
        self.t0 = T.day_start_ms(DAY)

    def test_milliseconds_and_microseconds_give_the_same_frame(self):
        rows = [(self.t0 + i * 60_000) for i in range(5)]
        a = T.parse_zip(zip_of([kline(t, c=100 + i) for i, t in enumerate(rows)]), DAY)
        b = T.parse_zip(zip_of([kline(t, c=100 + i, unit=1000) for i, t in enumerate(rows)]), DAY)
        pd.testing.assert_frame_equal(a, b)
        self.assertEqual(list(a.columns), list(T.COLS))
        self.assertEqual(a['ts'].tolist(), rows)
        self.assertEqual(a['tb'].iloc[0], 1.25)                         # column 9 = taker-buy base volume
        self.assertEqual(a['v'].iloc[0], 3.0)

    def test_header_line_is_skipped(self):
        df = T.parse_zip(zip_of([kline(self.t0), kline(self.t0 + 60_000)], header=True), DAY)
        self.assertEqual(len(df), 2)

    def test_rejects_rows_off_the_day_off_the_minute_out_of_order_or_short(self):
        with self.assertRaises(T.TopupError):
            T.parse_zip(zip_of([kline(self.t0 - 60_000)]), DAY)
        with self.assertRaises(T.TopupError):
            T.parse_zip(zip_of([kline(self.t0 + 1_000)]), DAY)
        with self.assertRaises(T.TopupError):
            T.parse_zip(zip_of([kline(self.t0 + 60_000), kline(self.t0)]), DAY)
        with self.assertRaises(T.TopupError):
            T.parse_zip(zip_of([kline(self.t0), kline(self.t0)]), DAY)
        with self.assertRaises(T.TopupError):
            T.parse_zip(b'not a zip', DAY)
        with self.assertRaises(T.TopupError):
            T.parse_zip(zip_of([[1, 2, 3]]), DAY)

    def test_days_and_ms(self):
        self.assertEqual(T.days('2026-11-23', '2026-11-25'), ['2026-11-23', '2026-11-24', '2026-11-25'])
        self.assertEqual(T.day_start_ms('1970-01-02'), 86_400_000)
        with self.assertRaises(ValueError):
            T.days('2026-11-25', '2026-11-23')


class FetchTest(unittest.TestCase):
    def test_retries_then_succeeds_and_404_raises(self):
        t0 = T.day_start_ms(DAY)
        blob = zip_of([kline(t0)])
        seen = []

        def flaky(url):
            seen.append(url)
            return (500, b'') if len(seen) < 3 else (200, blob)

        df = T.fetch_day('BTC', DAY, flaky, tries=4, pause=0.0)
        self.assertEqual(len(df), 1)
        self.assertIn('BTCUSDT-1m-2026-11-23.zip', seen[0])
        with self.assertRaises(T.TopupError):
            T.fetch_day('ETH', DAY, lambda u: (404, b''), tries=2, pause=0.0)
        with self.assertRaises(T.TopupError):
            T.fetch_day('ETH', DAY, lambda u: (500, b''), tries=2, pause=0.0)

    def test_range_reports_rows_per_day_and_csv_roundtrip(self):
        def get(url):
            day = url.rsplit('-1m-', 1)[1][:10]
            t0 = T.day_start_ms(day)
            return 200, zip_of([kline(t0 + i * 60_000) for i in range(3)])

        df = T.fetch_range('BTC', '2026-11-23', '2026-11-24', get)
        self.assertEqual(df.attrs['rows_per_day'], {'2026-11-23': 3, '2026-11-24': 3})
        self.assertEqual(len(df), 6)

    def test_compare_finds_differences(self):
        t0 = T.day_start_ms(DAY)
        a = T.parse_zip(zip_of([kline(t0), kline(t0 + 60_000)]), DAY)
        b = a.iloc[:1].copy()
        c = T.compare(a, b)
        self.assertEqual((c['only_a'], c['only_b'], c['both']), (1, 0, 1))
        self.assertEqual(c['max_rel_c'], 0.0)
        b2 = a.copy()
        b2.loc[0, 'c'] = 100.6
        self.assertGreater(T.compare(a, b2)['max_rel_c'], 5e-4)


if __name__ == '__main__':
    unittest.main()
