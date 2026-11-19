"""Event sets: everything a trial needs from the engine, built once per coin, scope and twin and cached, so the optimizer and the
twin gate never run the engine again.

An EventSet is one coin's grid plus every firing of the universe's event keys:
  coin, twin (0 = the real coin, 1..3 = the no-signal twins), scope ('dev' | 'val'), t0 (ms of grid row 0), n (grid rows),
  lo_row (the scope's first row), o (open prices, float64, one per row), step (the table's price step),
  keys (event key names), rows (entry rows, sorted), kidx (index into keys, aligned with rows).

The grid is loaded from WARMUP_START to the scope's end and no further (events.read_bars), so a DEV set holds no minute of VAL. Events
are kept from lo_row - PAD (the TA windows and the lockout look back a little); calls before lo_row are never scored.
"""
import json

import numpy as np

from heatloop import events, guards

MIN = 60_000
PAD = 120


class EventSet:
    def __init__(self, coin, twin, scope, t0, n, lo_row, o, step, keys, rows, kidx):
        self.coin, self.twin, self.scope = coin, int(twin), scope
        self.t0, self.n, self.lo_row, self.step = int(t0), int(n), int(lo_row), step
        self.o = np.asarray(o, float)
        self.keys = list(keys)
        self.rows = np.asarray(rows, np.int64)
        self.kidx = np.asarray(kidx, np.int32)
        self._pos = {k: i for i, k in enumerate(self.keys)}
        self._by = None

    def _index(self):
        if self._by is None:
            order = np.lexsort((self.rows, self.kidx))
            r, k = self.rows[order], self.kidx[order]
            cut = np.searchsorted(k, np.arange(len(self.keys) + 1))
            self._by = {self.keys[i]: r[cut[i]:cut[i + 1]] for i in range(len(self.keys))}
        return self._by

    def events_for(self, keys) -> list:
        """[(entry_row, key)] of the wanted keys, in row order."""
        by = self._index()
        parts = [(by[k], k) for k in set(keys) if k in by and len(by[k])]
        if not parts:
            return []
        rows = np.concatenate([p[0] for p in parts])
        names = np.concatenate([np.full(len(p[0]), j, np.int32) for j, p in enumerate(parts)])
        o = np.lexsort((names, rows))
        labels = [p[1] for p in parts]
        return [(int(r), labels[j]) for r, j in zip(rows[o], names[o])]

    def counts(self) -> dict:
        return {k: int(len(v)) for k, v in self._index().items()}


def build(coin: str, csv: str, meta: dict, keys, scope: str, twin: int = 0, val_end=None, engine=None, make_twin=None) -> EventSet:
    """Load the grid for `coin` up to the scope's end, optionally replace it by the no-signal twin, and read every event of `keys`."""
    if coin not in ('BTC', 'ETH', 'SOL', 'XRP'):
        raise ValueError(f'coin {coin!r} is not allowed (never DOGE)')
    lo_ms, hi_ms = guards.scope_range(scope, val_end)
    m = events.load_grid(csv, guards.WARMUP_START, hi_ms, engine)
    if m['t0'] != guards.WARMUP_START:
        raise ValueError(f'the grid starts at {m["t0"]}, not at the warm-up start {guards.WARMUP_START}')
    if twin:
        if make_twin is None:
            from oracle import heat
            make_twin = heat.make_twin
        m = make_twin(m, int(twin))
    lo_row = int((lo_ms - m['t0']) // MIN)
    ev = events.event_rows(m, meta, keys, max(0, lo_row - PAD), m['n'], engine)
    names = sorted(set(k for _, k in ev))
    pos = {k: i for i, k in enumerate(names)}
    rows = np.array([r for r, _ in ev], np.int64)
    kidx = np.array([pos[k] for _, k in ev], np.int32)
    return EventSet(coin, twin, scope, m['t0'], m['n'], lo_row, m['o'], meta.get('price_step'), names, rows, kidx)


def save(es: EventSet, path: str) -> None:
    np.savez_compressed(path, o=es.o, rows=es.rows, kidx=es.kidx,
                        head=np.array(json.dumps(dict(coin=es.coin, twin=es.twin, scope=es.scope, t0=es.t0, n=es.n, lo_row=es.lo_row,
                                                      step=es.step, keys=es.keys))))


def load(path: str) -> EventSet:
    z = np.load(path, allow_pickle=False)
    h = json.loads(str(z['head']))
    return EventSet(h['coin'], h['twin'], h['scope'], h['t0'], h['n'], h['lo_row'], z['o'], h['step'], h['keys'], z['rows'], z['kidx'])
