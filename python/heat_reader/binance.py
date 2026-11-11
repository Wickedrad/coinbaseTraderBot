"""Binance spot 1-minute bars over the public market data address (no key, no account).

The heat tables were built on Binance spot minutes, so the live readings use the same source. A kline row is
[openTime, open, high, low, close, volume, closeTime, quoteVolume, trades, takerBuyBase, ...]; the reader keeps
ts (the minute's open in ms), o, h, l, c, v and tb (taker buy base volume, which one reading needs).

Only CLOSED minutes are used: a kline counts once its closeTime is before Binance's own clock. The reader's clock is
compared with Binance's once (GET /time) and the difference is carried, the same way research/heatmap_live/captureCli.ts
does it. The HTTP call is a plain function handed in, so tests answer with canned responses.
"""
import http.client
import json
import math
import time
import urllib.error
import urllib.request

import numpy as np

from heat_reader import MIN

COLS = ('ts', 'o', 'h', 'l', 'c', 'v', 'tb')
PAGE = 1000                    # Binance's largest kline page
CLOCK_MARGIN_MS = 500          # a minute counts as closed this long after its close on Binance's clock
BLIND_MARGIN_MS = 2000         # the margin while Binance's clock could not be read (the server's own clock is used)
CLOCK_EVERY_MS = 15 * MIN      # how often the clock difference is measured again


class FetchError(Exception):
    """Binance could not be read (network, HTTP status, an answer that is not kline rows)."""


class RateLimited(FetchError):
    """HTTP 429 or 418: Binance asks the caller to wait."""

    def __init__(self, message: str, retry_after: float):
        super().__init__(message)
        self.retry_after = retry_after


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect is an error: the reader only ever talks to the address it was given."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def http_get(url: str, timeout: float) -> tuple:
    """(status, headers, body) of a GET. An HTTP error status is returned, not raised; a network failure raises
    FetchError. Headers are a plain dict with lower-case names."""
    req = urllib.request.Request(url, headers={'Accept': 'application/json', 'User-Agent': 'heat-reader'})
    try:
        with _OPENER.open(req, timeout=timeout) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read()
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in (e.headers.items() if e.headers else [])}, b''
    # http.client.HTTPException (IncompleteRead, BadStatusLine, RemoteDisconnected) is not an OSError: a body cut off
    # mid-read would otherwise escape and cost the whole pass instead of marking one fetch failed.
    except (urllib.error.URLError, OSError, ValueError, http.client.HTTPException) as e:
        raise FetchError(f'network: {getattr(e, "reason", e)}'[:160]) from None


def parse_klines(data, closed_before_ms: float) -> np.ndarray:
    """Kline rows as an (n, 7) float array in COLS order, closed minutes only, in time order.

    A row is kept when its open time is a whole minute, its closeTime is before closed_before_ms and every number in
    it parses. A row that does not parse is left out: the engine then sees that minute as a gap, which is what a
    broken row is. Rows that go back in time (Binance never sends them) are left out too."""
    if not isinstance(data, list):
        raise FetchError('the kline answer is not a list')
    out, last = [], -math.inf
    for k in data:
        try:
            ts, close_time = int(k[0]), int(k[6])
            vals = [float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5]), float(k[9])]
        except (TypeError, ValueError, IndexError):
            continue
        if ts % MIN or ts <= last or not close_time < closed_before_ms or not all(math.isfinite(x) for x in vals):
            continue
        out.append([float(ts)] + vals)
        last = ts
    return np.asarray(out, dtype=np.float64).reshape(len(out), len(COLS))


class Binance:
    """The minute source. `get`, `now_ms` and `sleep` are handed in so tests need no network and no waiting."""

    def __init__(self, api: str, get=http_get, now_ms=None, sleep=time.sleep, timeout: float = 10.0, retries: int = 2, pace: float = 0.05):
        self.api = api.rstrip('/')
        self._get = get
        self._now = now_ms or (lambda: time.time() * 1000.0)
        self._sleep = sleep
        self.timeout = timeout
        self.retries = retries
        self.pace = pace                  # pause between pages of a long download
        self.offset_ms = None             # Binance's clock minus this machine's; None until measured
        self._clock_at = None
        self.requests = 0

    # ---- clock ----
    def sync_clock(self, force: bool = False) -> bool:
        """Measure the clock difference when it is due. A failure keeps the last measured value."""
        local = self._now()
        if not force and self._clock_at is not None and local - self._clock_at < CLOCK_EVERY_MS:
            return True
        try:
            t0 = self._now()
            data = self._json(f'{self.api}/time', tries=1)
            t1 = self._now()
            self.offset_ms = float(data['serverTime']) - (t0 + t1) / 2.0
            self._clock_at = t1
            return True
        except (FetchError, KeyError, TypeError, ValueError):
            return False

    def server_now(self) -> float:
        """Binance's clock in ms, as well as it is known."""
        return self._now() + (self.offset_ms or 0.0)

    def closed_before(self) -> float:
        """A kline whose closeTime is before this is final."""
        return self.server_now() - (CLOCK_MARGIN_MS if self.offset_ms is not None else BLIND_MARGIN_MS)

    def last_close(self) -> int:
        """Close time (ms) of the last minute that counts as closed now."""
        return int(self.closed_before() // MIN) * MIN

    # ---- requests ----
    def _json(self, url: str, tries: int = None):
        tries = self.retries + 1 if tries is None else tries
        err = None
        for i in range(tries):
            if i:
                self._sleep(0.5 * 3 ** (i - 1))                       # 0.5 s, then 1.5 s
            self.requests += 1
            try:
                status, headers, body = self._get(url, self.timeout)
            except FetchError as e:
                err = e
                continue
            if status in (429, 418):
                try:
                    wait = float(headers.get('retry-after', ''))
                except (TypeError, ValueError):
                    wait = 2.0
                raise RateLimited(f'HTTP {status} from Binance', max(1.0, wait))
            if status != 200:
                err = FetchError(f'HTTP {status} from Binance')
                continue
            try:
                return json.loads(body)
            except ValueError:
                err = FetchError('the answer from Binance is not JSON')
        raise err

    def minutes(self, coin: str, start_ms: int, until_ms: int = None):
        """Yield pages of closed minutes of `coin` from start_ms on (rows as parse_klines gives them), oldest first,
        up to the newest closed minute, or up to until_ms (exclusive) when given. A page is handed out as soon as it
        arrives, so the caller can save progress during a long download."""
        cur = int(start_ms)
        while until_ms is None or cur < until_ms:
            url = f'{self.api}/klines?symbol={coin}USDT&interval=1m&limit={PAGE}&startTime={cur}'
            if until_ms is not None:
                url += f'&endTime={int(until_ms) - 1}'
            data = self._json(url)
            rows = parse_klines(data, self.closed_before())
            rows = rows[rows[:, 0] >= cur]
            if until_ms is not None:
                rows = rows[rows[:, 0] < until_ms]
            if len(rows):
                yield rows
            if len(data) < PAGE:                                       # a short page: this was the newest data
                return
            try:
                nxt = int(data[-1][0]) + MIN
            except (TypeError, ValueError, IndexError):
                raise FetchError('the last kline row has no open time') from None
            if nxt <= cur:                                             # no progress: stop instead of asking forever
                return
            cur = nxt
            if self.pace:
                self._sleep(self.pace)
