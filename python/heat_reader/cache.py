"""The per-coin minute cache on disk: an append-only binary file, so a restart does not download the window again.

File: 16 bytes of header (8 bytes magic, then the time in ms the cache was asked to start from, a little-endian
int64), then one record per minute: seven little-endian float64 in binance.COLS order (ts, o, h, l, c, v, tb).
New minutes are appended. Once a day's worth of minutes has fallen out of the window the file is rewritten without
them (written beside the file, then renamed over it, so a crash leaves the old or the new file, never half of one).

A file that does not read back as whole, time-ordered minutes is corrupt: it is removed and the window is downloaded
again. A torn last record (the process died inside an append) is cut off and the rest is kept.
"""
import os
import struct

import numpy as np

from heat_reader import MIN
from heat_reader.binance import COLS, FetchError

MAGIC = b'HEATMIN1'
HEADER = len(MAGIC) + 8
SLACK_MS = 60 * MIN            # a new cache starts this much before the window, so a clock corrected backwards by a
                               # minute does not make it look too short and start the download again
WIDTH = len(COLS)
REC = WIDTH * 8
DTYPE = np.dtype('<f8')


class CorruptCache(Exception):
    """The file cannot be trusted. The caller removes it and downloads the window again."""


def empty() -> np.ndarray:
    return np.empty((0, WIDTH), dtype=np.float64)


class MinuteCache:
    def __init__(self, path: str):
        self.path = path
        self.asked_from = None      # the start the cache was built for; None = no file
        self.repaired = False       # a torn last record was cut off on the last load

    def load(self) -> np.ndarray:
        """All cached minutes as an (n, 7) array, oldest first. No file: an empty array and asked_from None.
        Raises CorruptCache when the file is not a cache this code wrote."""
        self.asked_from, self.repaired = None, False
        try:
            size = os.path.getsize(self.path)
        except FileNotFoundError:
            return empty()
        if size < HEADER:
            raise CorruptCache('shorter than its header')
        with open(self.path, 'rb') as f:
            head = f.read(HEADER)
            if head[:len(MAGIC)] != MAGIC:
                raise CorruptCache('not a minute cache (wrong first bytes)')
            asked = struct.unpack('<q', head[len(MAGIC):])[0]
            body = size - HEADER
            if body % REC:                                    # died inside an append: keep the whole records
                body -= body % REC
                self.repaired = True
            rows = np.fromfile(f, dtype=DTYPE, count=body // 8).reshape(-1, WIDTH).astype(np.float64, copy=False)
        if len(rows) * REC != body:
            raise CorruptCache('shorter than its size says')
        ts = rows[:, 0]
        if len(ts) and (not np.isfinite(ts).all() or (ts % MIN != 0).any() or (np.diff(ts) <= 0).any() or ts[0] < 1e11 or ts[-1] >= 1e14):
            raise CorruptCache('minutes out of order or not whole minutes')
        if not 0 < asked < 1e14:
            raise CorruptCache('no start time in the header')
        if self.repaired:
            os.truncate(self.path, HEADER + body)
        self.asked_from = int(asked)
        return rows

    def rewrite(self, rows: np.ndarray, asked_from: int) -> None:
        """Replace the file with these minutes (atomic: a new file beside it, renamed over it)."""
        os.makedirs(os.path.dirname(self.path) or '.', exist_ok=True)
        tmp = f'{self.path}.tmp.{os.getpid()}'
        try:
            with open(tmp, 'wb') as f:
                f.write(MAGIC + struct.pack('<q', int(asked_from)))
                f.write(np.ascontiguousarray(rows, dtype=DTYPE).tobytes())
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        self.asked_from = int(asked_from)

    def append(self, rows: np.ndarray) -> None:
        """Add minutes after the ones in the file. The caller hands in only minutes newer than the last one."""
        if not len(rows):
            return
        with open(self.path, 'ab') as f:
            f.write(np.ascontiguousarray(rows, dtype=DTYPE).tobytes())
            f.flush()
            os.fsync(f.fileno())

    def last_close(self) -> int:
        """Close time (ms) of the newest whole minute in the file, read from its last record; 0 when there is none."""
        try:
            size = os.path.getsize(self.path)
            n = (size - HEADER) // REC
            if n < 1:
                return 0
            with open(self.path, 'rb') as f:
                f.seek(HEADER + (n - 1) * REC)
                ts = struct.unpack('<d', f.read(8))[0]
            return int(ts) + MIN if 1e11 <= ts < 1e14 else 0
        except (OSError, struct.error, ValueError):
            return 0

    def remove(self) -> None:
        try:
            os.unlink(self.path)
        except FileNotFoundError:
            pass
        self.asked_from = None


def update(cache: MinuteCache, source, coin: str, start_ms: int, until_ms: int = None, keep_extra: int = 1440) -> tuple:
    """Bring the coin's cache up to date and return (rows from start_ms on, facts).

    start_ms: the oldest minute the engine needs now. A cache that was never asked to go back that far (a longer
    window, a pack that now uses a larger timeframe) is started again; one that is corrupt is removed and started
    again. Minutes older than start_ms are dropped from the file once more than keep_extra of them have piled up.
    Each downloaded page is appended at once, so a download that fails halfway keeps what it has and the next pass
    goes on from there. A failed download does not raise: facts['error'] holds the FetchError and the rows are the
    ones the cache has."""
    facts = {'rebuilt': '', 'fetched': 0, 'repaired': False, 'error': None}
    try:
        rows = cache.load()
        facts['repaired'] = cache.repaired
    except CorruptCache as e:
        cache.remove()
        rows = empty()
        facts['rebuilt'] = f'corrupt cache ({e})'
    if cache.asked_from is None or cache.asked_from > start_ms or (len(rows) and rows[-1, 0] < start_ms - MIN):
        if cache.asked_from is not None:
            facts['rebuilt'] = 'the cache does not reach back far enough' if cache.asked_from > start_ms else 'the cache ends before the window starts'
        rows = empty()
        cache.rewrite(rows, start_ms - SLACK_MS)                # the header remembers how far back this cache was asked to go
    lo = start_ms - SLACK_MS
    first = int(np.searchsorted(rows[:, 0], lo)) if len(rows) else 0
    if first > keep_extra:                                    # a day of minutes fell out of the window: drop them
        rows = rows[first:]
        cache.rewrite(rows, lo)
    nxt = int(rows[-1, 0]) + MIN if len(rows) else int(lo)
    pages = [rows]
    try:
        for page in source.minutes(coin, nxt, until_ms):
            page = page[page[:, 0] >= nxt]
            if not len(page):
                continue
            cache.append(page)
            pages.append(page)
            facts['fetched'] += len(page)
            nxt = int(page[-1, 0]) + MIN
    except FetchError as e:
        facts['error'] = e
    if len(pages) > 1:
        rows = np.concatenate(pages)
    return rows[int(np.searchsorted(rows[:, 0], start_ms)):], facts
