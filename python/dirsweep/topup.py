"""FINAL data (AMENDMENT-3.md section 6): Binance public daily 1-minute files for BTCUSDT and ETHUSDT, turned into the same minute file the sweep read
(`ts, o, h, l, c, v, tb`: the minute's open time in ms, open, high, low, close, base volume, taker-buy base volume).

A daily file is a zip of one csv with kline rows [openTime, open, high, low, close, volume, closeTime, quoteVolume, trades, takerBuyBase, takerBuyQuote,
ignore]. From 2025-01-01 the exchange writes the time in microseconds; both units are read here. The HTTP call is a plain function handed in, so tests
answer with canned bytes.
"""
import datetime as dt
import io
import time
import urllib.error
import urllib.request
import zipfile

import numpy as np
import pandas as pd

URL = 'https://data.binance.vision/data/spot/daily/klines/{sym}/1m/{sym}-1m-{day}.zip'
SYMBOL = {'BTC': 'BTCUSDT', 'ETH': 'ETHUSDT'}
COLS = ('ts', 'o', 'h', 'l', 'c', 'v', 'tb')
DAY_MS = 86_400_000
MIN_MS = 60_000


class TopupError(Exception):
    """A daily file could not be read or does not look like a day of 1-minute klines."""


def days(first: str, last: str) -> list:
    """['YYYY-MM-DD', ...] from `first` to `last`, both included."""
    a, b = dt.date.fromisoformat(first), dt.date.fromisoformat(last)
    if b < a:
        raise ValueError('last day before first day')
    return [(a + dt.timedelta(days=i)).isoformat() for i in range((b - a).days + 1)]


def day_start_ms(day: str) -> int:
    return int(dt.datetime.fromisoformat(day).replace(tzinfo=dt.timezone.utc).timestamp() * 1000)


def parse_zip(blob: bytes, day: str) -> pd.DataFrame:
    """One day's rows as a frame with COLS, ts in ms, time-ordered, every row inside `day` and on a whole minute. A header line, if present, is skipped."""
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            names = z.namelist()
            if len(names) != 1:
                raise TopupError(f'{day}: {len(names)} files in the zip')
            raw = pd.read_csv(z.open(names[0]), header=None, dtype=str)
    except (zipfile.BadZipFile, pd.errors.ParserError, pd.errors.EmptyDataError) as e:
        raise TopupError(f'{day}: unreadable zip ({type(e).__name__})') from None
    if raw.shape[1] < 10:
        raise TopupError(f'{day}: {raw.shape[1]} columns, expected 12')
    num = raw.apply(pd.to_numeric, errors='coerce')
    num = num[num[0].notna()]                                                 # a header row has no number in the first column
    ts = num[0].to_numpy(float)
    ts = np.where(ts > 1e14, ts // 1000, ts)                                  # microseconds -> ms
    out = pd.DataFrame({'ts': ts.astype(np.int64), 'o': num[1].to_numpy(float), 'h': num[2].to_numpy(float), 'l': num[3].to_numpy(float),
                        'c': num[4].to_numpy(float), 'v': num[5].to_numpy(float), 'tb': num[9].to_numpy(float)})
    lo = day_start_ms(day)
    if out.empty:
        raise TopupError(f'{day}: no rows')
    if (out['ts'] % MIN_MS).any():
        raise TopupError(f'{day}: a row is not on a whole minute')
    if (out['ts'] < lo).any() or (out['ts'] >= lo + DAY_MS).any():
        raise TopupError(f'{day}: a row lies outside the day')
    if not out['ts'].is_monotonic_increasing or out['ts'].duplicated().any():
        raise TopupError(f'{day}: rows are not strictly time-ordered')
    return out


def http_get(url: str, timeout: float = 60.0) -> tuple:
    """(status, body); an HTTP error status is returned, a network failure raises TopupError."""
    req = urllib.request.Request(url, headers={'User-Agent': 'dirsweep-topup'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b''
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise TopupError(f'network: {getattr(e, "reason", e)}'[:160]) from None


def fetch_day(coin: str, day: str, get=http_get, tries: int = 4, pause: float = 5.0) -> pd.DataFrame:
    """One coin-day, parsed. A 404 (not published yet, or no such day) raises; other failures are retried."""
    url = URL.format(sym=SYMBOL[coin], day=day)
    last = None
    for i in range(tries):
        try:
            status, body = get(url)
        except TopupError as e:
            status, body, last = None, b'', str(e)
        if status == 200:
            return parse_zip(body, day)
        if status == 404:
            raise TopupError(f'{coin} {day}: not published (404)')
        last = last or f'HTTP {status}'
        time.sleep(pause * (i + 1))
    raise TopupError(f'{coin} {day}: {last}')


def fetch_range(coin: str, first: str, last: str, get=http_get, **kw) -> pd.DataFrame:
    """The days first..last of one coin as one frame, with a report of rows per day in `attrs['rows_per_day']`."""
    parts, rows = [], {}
    for d in days(first, last):
        df = fetch_day(coin, d, get, **kw)
        rows[d] = int(len(df))
        parts.append(df)
    out = pd.concat(parts, ignore_index=True)
    out.attrs['rows_per_day'] = rows
    return out


def write_csv(df: pd.DataFrame, path: str) -> None:
    """The sweep's own minute-file layout: header `ts,o,h,l,c,v,tb`, ts in ms, repr-exact numbers."""
    df[list(COLS)].to_csv(path, index=False)


def compare(a: pd.DataFrame, b: pd.DataFrame) -> dict:
    """a (the daily file) against b (the sweep's file) on one day: minutes only in one of them and the largest relative difference of each column."""
    m = a.merge(b, on='ts', how='outer', suffixes=('_a', '_b'), indicator=True)
    both = m[m['_merge'] == 'both']
    out = {'rows_a': int(len(a)), 'rows_b': int(len(b)), 'only_a': int((m['_merge'] == 'left_only').sum()), 'only_b': int((m['_merge'] == 'right_only').sum()),
           'both': int(len(both))}
    for c in COLS[1:]:
        x, y = both[f'{c}_a'].to_numpy(float), both[f'{c}_b'].to_numpy(float)
        den = np.maximum(np.abs(y), 1e-12)
        out[f'max_rel_{c}'] = float(np.max(np.abs(x - y) / den)) if len(x) else None
    return out
