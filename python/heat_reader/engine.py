"""The oracle engine, as the reader uses it: python/oracle/heat_live.py, imported from HEAT_ORACLE_PATH.

The reader computes no indicator itself. A level means live what it meant in the heat tables only if the same code
places it, so every reading comes from heat_live.grid() and heat_live.active_keys(), and this file holds nothing but
the import, the frame those functions take, and the join of their answer with the traded pack.
"""
import importlib
import os
import sys

import numpy as np
import pandas as pd

from heat_reader.binance import COLS
from heat_reader.pack import call_row, tf_minutes


class EngineError(Exception):
    """The oracle package cannot be loaded (wrong HEAT_ORACLE_PATH, TA-Lib missing)."""


class Engine:
    def __init__(self, oracle_path: str):
        if not os.path.isfile(os.path.join(oracle_path, 'oracle', 'heat_live.py')):
            raise EngineError(f'no oracle/heat_live.py under {oracle_path} (HEAT_ORACLE_PATH)')
        if oracle_path not in sys.path:
            sys.path.insert(0, oracle_path)
        try:
            importlib.import_module('talib')
            self.heat = importlib.import_module('oracle.heat')
            self.live = importlib.import_module('oracle.heat_live')
        except Exception as e:                       # ImportError, or anything the oracle modules raise while loading
            raise EngineError(f'the oracle engine does not load: {type(e).__name__}: {e}'[:200]) from None
        self.stale_back = int(self.live.STALE_BACK)
        # The names of the zone events ('very low', 'low (falling in)' ...): a pack row on one of them needs zone edges.
        self.zone_levels = {name for _, _, name in self.heat.event_levels({'zones': True, 'levels': self.heat.ZONES})}

    def need_minutes(self, window: int, tfs: list) -> int:
        """Minutes of history the engine needs for these timeframes: the window plus the bars before it whose gaps
        still matter, on the largest timeframe, plus one day because the engine's grid starts at a UTC midnight."""
        return (int(window) + self.stale_back + 2) * max(tfs) + 1440

    def read(self, minutes: pd.DataFrame, end_ms: int, table, window: int) -> dict:
        """What the engine says at the minute close end_ms. minutes: frame() of the cached minutes ending at the
        minute that closed then. Returns active_keys' answer (ts, closed, events, no_reading, levels) plus `minutes`
        (the grid's length), `gap_last` (the last minute itself is a gap) and `bars` (complete bars per timeframe)."""
        m = self.live.grid(minutes, end_ms=end_ms)
        out = self.live.active_keys(m, table.meta, want=table.want, tfs=table.tfs, window=int(window), levels=True)
        out['minutes'] = int(m['n'])
        out['gap_last'] = bool(m['gap'][-1])
        out['bars'] = {k: int(m['n'] // k) for k in table.tfs}
        return out


def frame(rows: np.ndarray) -> pd.DataFrame:
    """Cached minutes as the frame heat_live.grid() takes: ts (the minute's open, ms, whole numbers), o, h, l, c, v
    and tb as floats."""
    rows = np.asarray(rows, dtype=np.float64).reshape(-1, len(COLS))
    cols = {name: rows[:, i] for i, name in enumerate(COLS)}
    cols['ts'] = rows[:, 0].astype(np.int64)
    return pd.DataFrame(cols)


def join(table, top: int, res: dict, window: int) -> tuple:
    """(calls, coin problem, notes): the pack rows that fire, from the engine's answer for one coin.

    A row fires when its key or one of its aliases is among the events, on a timeframe whose bar closed at this minute
    and has a reading. A timeframe has no reading when the engine says so (no_reading: a gap inside its last bar),
    when it holds fewer bars than the window, or when none of its wanted readings holds a level (after a gap the
    engine uses no reading for 100 bars). Without readings on the 1-minute bars the reader cannot vouch for the coin:
    that comes back as the coin's problem and nothing fires. Rows the oracle's parity check marked as not
    reproducible on a window (live_parity false) never fire. barClose of every fired row is the engine's ts."""
    events, closed = set(res['events']), set(res['closed'])
    blind = {}
    for k in table.tfs:
        if res['bars'].get(k, 0) < window:
            blind[k] = f'only {res["bars"].get(k, 0)} of {window} {k}-minute bars are loaded'
        elif k in res['no_reading']:
            blind[k] = f'a minute is missing inside the last {k}-minute bar'
        elif k in closed and not any(name.startswith(f'{k}m:') for name in res.get('levels', {})):
            blind[k] = f'no {k}-minute reading holds a level (the engine uses none for 100 bars after a missing minute)'
    if res.get('gap_last'):
        return [], 'the last closed minute is missing or broken in the Binance data', []
    if 1 in blind:
        return [], blind[1], []
    calls = []
    for row in table.rows:
        k = tf_minutes(row['tf'])
        if k not in closed or k in blind or row.get('live_parity') is False:
            continue
        if row['key'] in events or any(a in events for a in (row.get('aliases') or [])):
            calls.append(call_row(row, top, res['ts']))
    calls.sort(key=lambda c: (c['h'], c['rank'], c['key']))
    return calls, None, [blind[k] for k in sorted(blind)]

