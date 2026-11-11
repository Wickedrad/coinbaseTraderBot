"""The reader's pass and loop: minutes in, the calls file out.

One pass, one coin at a time (so only one coin's minutes are in memory): bring the minute cache up to date, ask the
engine what fires at the last closed minute, join with the packs. Then the whole HeatCallsFile is written atomically
to HEAT_CALLS_FILE and the same object is appended as one line to the day's heat_calls-YYYY-MM-DD.jsonl beside it.
Per coin, the rows the reader asks for and the rows it leaves out (by reason) go to the status sidecar beside the
calls file (config.status_path: heat_calls.status.json), which the bot's status can show.

The 60-minute readings a pair conditions on need the long window (3,000 hourly bars, about 150 days of minutes), but
their level changes only when an hourly bar closes. So the long window is read once an hour per coin (or after a
restart) and the levels are kept until the next hourly close; every other minute reads only the window the 1-, 5-
and 15-minute readings need. The minute cache on disk always holds the long window, so the hourly read downloads
nothing extra.

A coin the reader cannot vouch for is written with ok false, a plain reason and no calls; the bot then opens nothing
on it. A network or engine error never ends the loop: it is counted, the coin is marked not ok, and after a network
error the reader waits before asking Binance again. Only ten minutes without one good pass end the process (exit 1),
so systemd starts it fresh.
"""
import ctypes
import datetime
import gc
import glob
import json
import math
import os
import re
import signal
import threading
import time

import numpy as np

from heat_reader import MIN
from heat_reader import cache as minute_cache
from heat_reader.binance import Binance, FetchError, RateLimited
from heat_reader.config import LOG_DAYS, Settings, is_doge, status_path
from heat_reader.engine import Engine, EngineError, fired_triggers, frame, join
from heat_reader.pack import LONG_TF, SOURCE, Tables

HOUR = 60 * MIN
WAKE_AFTER_MS = 3000           # the loop wakes this long after a minute closes
GIVE_UP_SEC = 600              # no good pass for this long: exit so systemd restarts the reader
LATE_TRIES = 3                 # extra looks for the last minute when Binance has not published it yet
DAILY = re.compile(r'^heat_calls-(\d{4}-\d{2}-\d{2})\.jsonl(\.gz)?$')


def write_atomic(path: str, text: str) -> None:
    """Write beside the file, then rename over it: a reader of the file sees the old or the new one, never half."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    tmp = f'{path}.tmp.{os.getpid()}'
    try:
        with open(tmp, 'w', encoding='utf-8') as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def day_of(ms: float) -> str:
    return datetime.datetime.fromtimestamp(ms / 1000.0, tz=datetime.timezone.utc).strftime('%Y-%m-%d')


def daily_path(calls_file: str, written_at: float) -> str:
    return os.path.join(os.path.dirname(calls_file), f'heat_calls-{day_of(written_at)}.jsonl')


def append_daily(calls_file: str, line: str, written_at: float) -> str:
    """One line per written file, in a file per UTC day beside the calls file (what a replay reads)."""
    path = daily_path(calls_file, written_at)
    with open(path, 'a', encoding='utf-8') as f:
        f.write(line + '\n')
    return path


def prune_daily(calls_file: str, written_at: float, keep_days: int = LOG_DAYS) -> list:
    """Remove daily logs older than the newest keep_days days. Only files with the log's own name are touched."""
    oldest = day_of(written_at - (keep_days - 1) * 86_400_000)
    gone = []
    for p in glob.glob(os.path.join(os.path.dirname(calls_file), 'heat_calls-*.jsonl*')):
        m = DAILY.match(os.path.basename(p))
        if m and m.group(1) < oldest:
            try:
                os.unlink(p)
                gone.append(p)
            except OSError:
                pass
    return sorted(gone)


try:
    _LIBC = ctypes.CDLL('libc.so.6')
except OSError:                    # not glibc: nothing to trim
    _LIBC = None


def _trim() -> None:
    """Hand freed memory back to the system after a coin (glibc keeps it otherwise), so the idle reader stays small."""
    gc.collect()
    try:
        if _LIBC is not None:
            _LIBC.malloc_trim(0)
    except AttributeError:
        pass


def _rss_mb() -> dict:
    """The process's memory now and at its highest, in MB (Linux; empty elsewhere)."""
    out = {}
    try:
        with open('/proc/self/status') as f:
            for line in f:
                if line.startswith(('VmRSS:', 'VmHWM:')):
                    out['rssMb' if line.startswith('VmRSS') else 'peakRssMb'] = round(int(line.split()[1]) / 1024.0, 1)
    except (OSError, ValueError, IndexError):
        pass
    return out


def not_ok(table_sha: str, why: str, as_of: int = 0) -> dict:
    return {'asOf': int(as_of), 'tableSha': table_sha, 'ok': False, 'why': str(why)[:300], 'calls': []}


class LongStates:
    """One coin's levels of the 60-minute readings at their last closed bar, and which bar that was. Valid until the
    next hourly bar closes, for the table and window they were read with."""

    def __init__(self):
        self.table, self.window, self.bar, self.states, self.note = None, None, None, {}, None

    def valid(self, table, window: int, bar: int) -> bool:
        return self.table is table and self.window == window and self.bar == bar


def read_coin(engine: Engine, table, top: int, rows: np.ndarray, end_ms: int, window: int, long: LongStates) -> tuple:
    """(HeatCoinCalls, facts) of one coin at the minute close end_ms. rows: the cached minutes, oldest first, ending
    with the minute that closed at end_ms. long: the coin's LongStates, read and updated here. The live pass and the
    parity replay both go through this function, so what the replay measures is what the server runs.

    The 60-minute timeframe is read only when its last closed bar is not the one the LongStates hold (an hourly
    close, a restart, new tables). Otherwise only the minutes the shorter timeframes need are handed to the engine,
    and the 60-minute levels come from LongStates."""
    needs_long = LONG_TF in table.tfs
    bar = int(end_ms) // HOUR * HOUR                              # close of the last closed hourly bar
    fresh = needs_long and not long.valid(table, window, bar)
    tfs = table.tfs if fresh or not needs_long else [k for k in table.tfs if k != LONG_TF]
    long_names = table.long_states
    states = table.states if fresh else table.states - long_names
    i0 = int(np.searchsorted(rows[:, 0], end_ms - engine.need_minutes(window, tfs) * MIN))
    res = engine.read(frame(rows[i0:]), end_ms, table, window, tfs, states)
    if fresh:
        bars = res['bars'].get(LONG_TF, 0)
        note = f'only {bars} of {window} {LONG_TF}-minute bars are loaded' if bars < window else None
        long.table, long.window, long.bar, long.note = table, window, bar, note
        long.states = {s: (None if note else res['states'].get(s)) for s in long_names}
    held = dict(res['states'])
    if needs_long:
        held.update(long.states)
    calls, problem, notes = join(table, top, res, window, held)
    if needs_long and long.note and not fresh:
        notes = notes + [long.note]
    kinds = {}
    for c in calls:
        kinds[c['kind']] = kinds.get(c['kind'], 0) + 1
    facts = {'minutes': res['minutes'], 'closed': res['closed'], 'noReading': res['no_reading'], 'fired': len(calls), 'firedBy': kinds,
             'keys': sorted({c['key'] for c in calls}), 'events': len(res['events']), 'long': ('read' if fresh else 'kept') if needs_long else None,
             'triggers': sorted(fired_triggers(table, res, window)) if not problem else []}
    if problem:
        return not_ok(table.table_sha, problem, res['ts']), facts
    coin = {'asOf': int(res['ts']), 'tableSha': table.table_sha, 'ok': True, 'calls': calls}
    if notes:
        coin['why'] = '; '.join(notes)[:300]
    return coin, facts


class Reader:
    def __init__(self, settings: Settings, source: Binance = None, now_ms=None, log=print, sleep=time.sleep):
        self.s = settings
        self.log = log
        self._now = now_ms or (lambda: time.time() * 1000.0)
        self._sleep = sleep
        self.source = source or Binance(settings.binance_api, now_ms=self._now, sleep=sleep)
        self.tables = Tables(settings.pack_dir, settings.assets, settings.run, settings.max_rank, settings.clock_pack)
        self.engine = None
        self.engine_why = None
        self.caches = {c: minute_cache.MinuteCache(os.path.join(settings.reader_dir, 'minutes', f'{c}.min')) for c in settings.assets}
        self.counts = {'passes': 0, 'goodPasses': 0, 'networkErrors': 0, 'engineErrors': 0, 'passErrors': 0, 'cacheRebuilds': 0, 'rateLimits': 0}
        self.net_fails = 0
        self.pause_until = 0.0          # this machine's clock (ms): no Binance request before it
        self.read_end = {}              # per coin: the close of the last minute the engine read
        self.long = {c: LongStates() for c in settings.assets}
        self.log_day = None
        self.stop = threading.Event()

    # ---- one coin ----
    def _load_engine(self) -> None:
        if self.engine is not None:
            return
        try:
            self.engine = Engine(self.s.oracle_path)
            self.engine_why = None
            for t in self.tables.coins.values():
                t.check_edges(self.engine.zone_levels, self.engine.zone_states)
        except EngineError as e:
            self.engine_why = str(e)

    def _network_error(self, e: FetchError) -> None:
        """Count the failure and wait longer after each one in a row: 5 s, 10 s ... at most 5 minutes; a rate limit
        waits at least as long as Binance asked."""
        self.net_fails += 1
        wait = min(5.0 * 2 ** (self.net_fails - 1), 300.0)
        if isinstance(e, RateLimited):
            self.counts['rateLimits'] += 1
            wait = max(wait, min(e.retry_after, 600.0))
        self.counts['networkErrors'] += 1
        self.pause_until = self._now() + wait * 1000.0

    def _as_of(self, coin: str) -> int:
        """asOf of a coin that is not read in this pass: the last minute the engine read for it, else the newest
        minute in its cache. A coin the reader holds no minute of gets the minute this pass ran for: the bot's
        reader takes only a real time there, and "not ok as of this minute" is what the file then says."""
        return self.read_end.get(coin) or self.caches[coin].last_close() or self.source.last_close()

    def _coin(self, coin: str) -> tuple:
        facts = {'ok': False}
        table = self.tables.coins.get(coin)
        sha = table.table_sha if table else ''
        if self.tables.problem:
            return not_ok(sha, self.tables.problem, self._as_of(coin)), facts
        if table is None or table.problem:
            return not_ok(sha, table.problem if table else 'the traded pack has no rows for this coin', self._as_of(coin)), facts
        if self.engine is None:
            return not_ok(sha, self.engine_why or 'the oracle engine is not loaded', self._as_of(coin)), facts
        wait = self.pause_until - self._now()
        if wait > 0:
            return not_ok(sha, f'Binance is not asked for another {math.ceil(wait / 1000)} s after a failed request', self._as_of(coin)), facts
        need_ms = self.engine.need_minutes(self.s.window_bars, table.tfs) * MIN
        t0 = time.monotonic()
        rows, target = None, 0
        for attempt in range(1 + LATE_TRIES):
            target = self.source.last_close()                  # the close of the last closed minute, on Binance's clock
            rows, got = minute_cache.update(self.caches[coin], self.source, coin, target - need_ms)
            facts['fetched'] = facts.get('fetched', 0) + got['fetched']
            if got['rebuilt']:
                self.counts['cacheRebuilds'] += 1
                self.log(f'heat-reader {coin}: minute cache started again ({got["rebuilt"]})')
            if got['error'] is not None:
                self._network_error(got['error'])
                last = int(rows[-1, 0]) + MIN if len(rows) else self._as_of(coin)
                return not_ok(sha, f'Binance fetch failed: {got["error"]}', last), facts
            if len(rows) and rows[-1, 0] + MIN >= target:
                break
            if attempt < LATE_TRIES:
                self._sleep(1.0)                               # the minute just closed: Binance may need a moment
        self.net_fails = 0
        facts['fetchSec'] = round(time.monotonic() - t0, 3)
        facts['cached'] = int(len(rows))
        if not len(rows) or rows[-1, 0] + MIN < target:
            last = int(rows[-1, 0]) + MIN if len(rows) else self._as_of(coin)
            return not_ok(sha, f'the minute that closed at {_hm(target)} UTC is not in the Binance answer yet', last), facts
        end_ms = int(rows[-1, 0]) + MIN
        t1 = time.monotonic()
        try:
            out, more = read_coin(self.engine, table, self.tables.top, rows, end_ms, self.s.window_bars, self.long[coin])
        except Exception as e:                                 # whatever the engine raises: this coin is not ok, the loop goes on
            self.counts['engineErrors'] += 1
            return not_ok(sha, f'engine error: {type(e).__name__}: {e}'[:200], end_ms), facts
        self.read_end[coin] = end_ms
        facts.update(more)
        facts['engineSec'] = round(time.monotonic() - t1, 3)
        facts['ok'] = out['ok']
        return out, facts

    # ---- one pass ----
    def pass_once(self) -> dict:
        t0 = time.monotonic()
        self.counts['passes'] += 1
        if self.tables.refresh() and self.engine is not None:
            for t in self.tables.coins.values():
                t.check_edges(self.engine.zone_levels, self.engine.zone_states)
        self._load_engine()
        if self._now() >= self.pause_until:
            self.source.sync_clock()
        coins, facts = {}, {}
        for coin in self.s.assets:
            if is_doge(coin):                                  # never DOGE, whatever the settings say
                continue
            c0 = time.monotonic()
            try:
                coins[coin], facts[coin] = self._coin(coin)
            except Exception as e:                             # a bug or a full disk on one coin must not take the others
                self.counts['passErrors'] += 1
                table = self.tables.coins.get(coin)
                coins[coin] = not_ok(table.table_sha if table else '', f'reader error: {type(e).__name__}: {e}'[:200],
                                     self.read_end.get(coin) or self.source.last_close())
                facts[coin] = {'ok': False}
            if not coins[coin]['ok']:
                facts[coin]['why'] = coins[coin]['why']
            facts[coin]['sec'] = round(time.monotonic() - c0, 3)
            table = self.tables.coins.get(coin)
            if table is not None:
                facts[coin]['rows'] = table.counts()
            _trim()
        written = int(self._now())
        obj = {'v': 1, 'source': SOURCE, 'run': self.tables.run, 'packSha': self.tables.pack_sha, 'writtenAt': written, 'coins': coins}
        line = json.dumps(obj, separators=(',', ':'), allow_nan=False)
        write_atomic(self.s.calls_file, line + '\n')
        append_daily(self.s.calls_file, line, written)
        if day_of(written) != self.log_day:                    # a new day (or the first pass): drop logs past 14 days
            self.log_day = day_of(written)
            prune_daily(self.s.calls_file, written)
        good = any(c['ok'] for c in coins.values())
        self.counts['goodPasses'] += good
        sec = round(time.monotonic() - t0, 3)
        status = {'at': written, 'seconds': sec, 'pid': os.getpid(), 'coins': facts, 'counts': dict(self.counts),
                  'clockOffsetMs': None if self.source.offset_ms is None else round(self.source.offset_ms), **_rss_mb()}
        try:
            write_atomic(os.path.join(self.s.reader_dir, 'status.json'), json.dumps(status, indent=1) + '\n')
            write_atomic(status_path(self.s.calls_file), json.dumps(self.sidecar(written, coins, facts), separators=(',', ':')) + '\n')
        except OSError:
            pass
        self.log('heat-reader pass ' + ' | '.join(
            f'{c} {len(v["calls"])} fired in {facts[c].get("sec", 0)} s' if v['ok'] else f'{c} NOT OK: {v["why"]}' for c, v in coins.items())
            + f' ({sec} s)')
        return obj

    def sidecar(self, written: int, coins: dict, facts: dict) -> dict:
        """The status beside the calls file, for the bot's status: per coin whether it is read, what fired this
        minute by kind, and the rows of the packs it asks for and leaves out, by reason."""
        out = {'v': 1, 'writtenAt': written, 'run': self.tables.run, 'packSha': self.tables.pack_sha, 'maxRank': self.s.max_rank,
               'clockPack': self.s.clock_pack, 'packs': self.tables.files, 'coins': {}}
        if self.tables.problem:
            out['problem'] = self.tables.problem
        for c, v in coins.items():
            f = facts.get(c, {})
            out['coins'][c] = {'ok': v['ok'], 'fired': f.get('firedBy', {}), 'rows': f.get('rows')}
            if v.get('why'):
                out['coins'][c]['why'] = v['why']
        return out

    # ---- the loop ----
    def run(self) -> int:
        """Pass after pass until told to stop. 0 = stopped on request, 1 = ten minutes without a good pass."""
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                signal.signal(sig, lambda *_: self.stop.set())
            except ValueError:                                 # not the main thread (tests)
                pass
        last_good = time.monotonic()
        while not self.stop.is_set():
            started, good = self.source.server_now(), False
            try:
                good = any(c['ok'] for c in self.pass_once()['coins'].values())
            except Exception as e:                             # the file could not be written, or a bug: count it and go on
                self.counts['passErrors'] += 1
                self.log(f'heat-reader pass failed: {type(e).__name__}: {e}'[:300])
            if good:
                last_good = time.monotonic()
            elif time.monotonic() - last_good > GIVE_UP_SEC:
                self.log(f'heat-reader: no good pass for {GIVE_UP_SEC} s, exiting so the service restarts')
                return 1
            self.stop.wait(wait_sec(started, self.source.server_now(), good))
        return 0


def wait_sec(started_ms: float, now_ms: float, good: bool) -> float:
    """Seconds to sleep after a pass, on Binance's clock: until about 3 s after the next minute closes. If a minute
    closed while a good pass ran (the first download, a slow answer), that minute is read as soon as it is 3 s old.
    A failed pass always waits for the next minute, and no wait is under a second, so the loop cannot spin."""
    cur = int(now_ms // MIN) * MIN
    due = cur + WAKE_AFTER_MS if good and cur > int(started_ms // MIN) * MIN else cur + MIN + WAKE_AFTER_MS
    return max(1.0, (due - now_ms) / 1000.0)


def _hm(ms: float) -> str:
    return datetime.datetime.fromtimestamp(ms / 1000.0, tz=datetime.timezone.utc).strftime('%H:%M')
