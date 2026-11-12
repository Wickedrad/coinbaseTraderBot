"""The oracle engine, as the reader uses it: python/oracle/heat_live.py, imported from HEAT_ORACLE_PATH.

The reader computes no indicator itself. A level means live what it meant in the heat tables only if the same code
places it, so every reading comes from heat_live.grid() and heat_live.active_keys(), and this file holds nothing but
the import, the frame those functions take, and the join of their answer with the packs.
"""
import importlib
import os
import sys

import numpy as np
import pandas as pd

from heat_reader.binance import COLS
from heat_reader.pack import call_row, key_tf, pair_call, tf_minutes


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
        if 'states' not in self.live.active_keys.__code__.co_varnames:
            raise EngineError('the oracle engine is too old: heat_live.active_keys takes no states (pairs need it)')
        self.stale_back = int(self.live.STALE_BACK)
        # The names of the zone events ('very low', 'low (falling in)' ...) and of the zone levels a pair condition
        # names ('low', 'high' ...): a row on one of them needs zone edges.
        self.zone_levels = {name for _, _, name in self.heat.event_levels({'zones': True, 'levels': self.heat.ZONES})}
        self.zone_states = set(self.heat.ZONES)

    def need_minutes(self, window: int, tfs: list) -> int:
        """Minutes of history the engine needs for these timeframes: the window plus the bars before it whose gaps
        still matter, on the largest timeframe, plus one day because the engine's grid starts at a UTC midnight."""
        return (int(window) + self.stale_back + 2) * max(tfs) + 1440

    def read(self, minutes: pd.DataFrame, end_ms: int, table, window: int, tfs: list, states: set) -> dict:
        """What the engine says at the minute close end_ms, on these timeframes. minutes: frame() of the cached
        minutes ending at the minute that closed then. states: the readings whose level at their own last closed bar
        is wanted (a pair's conditions). Returns active_keys' answer (ts, closed, events, no_reading, levels, states)
        plus `minutes` (the grid's length), `gap_last` (the last minute itself is a gap), `bars` (complete bars per
        timeframe) and `tfs`."""
        m = self.live.grid(minutes, end_ms=end_ms)
        out = self.live.active_keys(m, table.meta, want=table.want, tfs=list(tfs), window=int(window), levels=True, states=set(states))
        out['minutes'] = int(m['n'])
        out['gap_last'] = bool(m['gap'][-1])
        out['bars'] = {k: int(m['n'] // k) for k in tfs}
        out['tfs'] = list(tfs)
        out.setdefault('states', {})
        return out


def frame(rows: np.ndarray) -> pd.DataFrame:
    """Cached minutes as the frame heat_live.grid() takes: ts (the minute's open, ms, whole numbers), o, h, l, c, v
    and tb as floats."""
    rows = np.asarray(rows, dtype=np.float64).reshape(-1, len(COLS))
    cols = {name: rows[:, i] for i, name in enumerate(COLS)}
    cols['ts'] = rows[:, 0].astype(np.int64)
    return pd.DataFrame(cols)


KIND_ORDER = {'single': 0, 'pair': 1, 'triple': 2}


def _blind(table, res: dict, window: int) -> tuple:
    """({timeframe: why it has no reading now}, {timeframes with fewer bars than the window}) of the timeframes the
    engine read this time."""
    closed, blind, short = set(res['closed']), {}, set()
    for k in res.get('tfs') or table.tfs:
        if res['bars'].get(k, 0) < window:
            short.add(k)
            blind[k] = f'only {res["bars"].get(k, 0)} of {window} {k}-minute bars are loaded'
        elif k in res['no_reading']:
            blind[k] = f'a minute is missing inside the last {k}-minute bar'
        elif k in closed and not any(name.startswith(f'{k}m:') for name in res.get('levels', {})):
            blind[k] = f'no {k}-minute reading holds a level (the engine uses none for 100 bars after a missing minute)'
    return blind, short


def _fires(key: str, aliases, res: dict, blind: dict) -> bool:
    """An event key fires when it or one of its aliases is among the events, on a timeframe whose bar closed now and
    has a reading. A context trigger (UTC4h ...) has no bars of its own: the engine sends it at 15-minute closes."""
    k = key_tf(key)
    if k is not None and (k not in res['closed'] or k in blind):
        return False
    events = res['events']
    return key in events or any(a in events for a in (aliases or []))


def fired_triggers(table, res: dict, window: int) -> set:
    """The `when` events of the coin's pair and triple rows that fire now, whether or not the conditions hold (what
    the parity replay compares with the full engine's events). The main packs only: the replay checks h15 and h60."""
    blind, _ = _blind(table, res, window)
    return {p['when'] for p in table.pairs if _fires(p['when'], table.aliases.get(p['when']), res, blind)}


def join(table, top: int, res: dict, window: int, held: dict = None) -> tuple:
    """(calls, coin problem, notes): the rows of the packs that fire, from the engine's answer for one coin.

    A single fires when its key or one of its aliases is among the events, on a timeframe whose bar closed at this
    minute and has a reading. A timeframe has no reading when the engine says so (no_reading: a gap inside its last
    bar), when it holds fewer bars than the window, or when none of its wanted readings holds a level (after a gap the
    engine uses no reading for 100 bars). Without readings on the 1-minute bars the reader cannot vouch for the coin:
    that comes back as the coin's problem and nothing fires.

    A pair or triple fires when its `when` fires by the same rule AND every condition reading holds its level at the
    last closed bar of its own timeframe (held: reading to level or None, the engine's states with the cached
    60-minute ones). A state on a timeframe with fewer bars than the window is not trusted: it does not hold.
    barClose of every fired row is the engine's ts.

    The perp rows (h240, h1440) fire by the same rules; their `of` is the perp pack's top, and a perp pair's trigger
    fires through the aliases of the perp singles too."""
    held = res.get('states', {}) if held is None else held
    blind, short = _blind(table, res, window)
    if res.get('gap_last'):
        return [], 'the last closed minute is missing or broken in the Binance data', []
    if 1 in blind:
        return [], blind[1], []
    res = dict(res, events=set(res['events']), closed=set(res['closed']))
    calls = [call_row(r, of, res['ts']) for rows, of in ((table.rows, top), (table.perp_rows, table.perp_top))
             for r in rows if _fires(r['key'], r.get('aliases'), res, blind)]
    for pairs, aliases, of in ((table.pairs, table.aliases, top), (table.perp_pairs, table.perp_aliases, table.perp_top)):
        for p in pairs:
            if _fires(p['when'], aliases.get(p['when']), res, blind) and \
                    all(held.get(rd) == lv and key_tf(rd) not in short for rd, lv in p['conds']):
                calls.append(pair_call(p, p['rank'], of, res['ts']))
    calls.sort(key=lambda c: (c['h'], c['rank'], KIND_ORDER[c['kind']], c['key']))
    return calls, None, [blind[k] for k in sorted(blind)]
