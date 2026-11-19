"""Readings to event rows (the only module that talks to the oracle engine; it needs TA-Lib, so it runs on the runner).

  load_grid(csv, lo_ms, hi_ms)                the 1-minute grid for [lo_ms, hi_ms), a minute never read past hi_ms
  bases_by_tf(keys)                           the reading names to compute, per bar size
  event_rows(m, meta, keys, lo_row, hi_row)   [(entry_row, key)]: every event of those keys whose entry row is in [lo_row, hi_row)

An event on a k-minute bar b is known when the bar closes, at the end of minute row (b+1)*k - 1; the entry is the open of the next
minute, row (b+1)*k. Readings are computed over the whole grid (window None) from the warm-up start, with the tables' own zone edges
(meta['edges']): no 2026 minute is in an edge. `engine` is injectable so the mapping is tested without TA-Lib.
"""
import os

import pandas as pd

TFS = (1, 5, 15, 60)
BAR_NAMES = {'1m': 1, '5m': 5, '15m': 15, '60m': 60}


def load_grid(csv: str, lo_ms: int, hi_ms: int, engine=None) -> dict:
    cols = pd.read_csv(csv, nrows=0).columns
    use = [c for c in ('ts', 'o', 'h', 'l', 'c', 'v', 'tb') if c in cols]
    df = pd.read_csv(csv, usecols=use)
    df = df[(df['ts'] >= lo_ms) & (df['ts'] < hi_ms)]
    if engine is None:
        from oracle import heat_live as engine
    return engine.grid(df, end_ms=hi_ms)


def bases_by_tf(keys) -> dict:
    """{bar minutes: {reading name}} for the event keys; a ' sign' reading also needs its base (as heat_live.active_keys)."""
    out = {}
    for key in keys:
        base = key.rsplit('=', 1)[0]
        tf = base.split(':', 1)[0]
        k = BAR_NAMES.get(tf)
        if k is None:
            continue
        s = out.setdefault(k, set())
        s.add(base)
        if base.endswith(' sign'):
            s.add(base[:-5])
    return out


def event_rows(m: dict, meta: dict, keys, lo_row: int, hi_row: int, engine=None) -> list:
    if engine is None:
        from oracle import heat_live as engine
    want = set(keys)
    out = []
    for k, bases in sorted(bases_by_tf(want).items()):
        if m['n'] // k < 2:
            continue
        readings, _, first = engine.tf_codes(m, k, meta.get('edges', {}), meta.get('price_step'), window=None, want_bases=bases)
        nb = m['n'] // k
        for r in readings:
            for bar, key in engine.events_at(r, 0, nb - first):
                if key not in want:
                    continue
                entry = (first + bar + 1) * k
                if lo_row <= entry < hi_row and entry < m['n']:
                    out.append((int(entry), key))
        del readings
    out.sort()
    return out
