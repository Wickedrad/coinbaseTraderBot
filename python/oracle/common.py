"""Shared constants and the part-directory format for the oracle-setups study.

Design and pass rules: python/oracle/prereg/OR-H1.md. Interfaces: python/oracle/SPEC.md.
A part is one directory of plain .npy arrays plus meta.json, one row per decision (see SPEC.md section 1).
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import numpy as np

MIN = 60_000
DAY = 86_400_000
SCHEMA = 'oracle-part-1'
TARGET_USD = 5.0
ASSETS = ['BTC', 'ETH', 'SOL', 'XRP']          # never DOGE
CTS = ['perp', 'pp15', 'pp60', 'tennis', 'perp-rev']


def ms(iso: str) -> int:
    """'2026-08-01' or '2026-04-27T05:00' (UTC) -> epoch ms."""
    s = iso if 'T' in iso else iso + 'T00:00'
    return int(datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp() * 1000)


def iso_day(t_ms: int) -> str:
    return datetime.fromtimestamp(t_ms / 1000, tz=timezone.utc).strftime('%Y-%m-%d')


DEV_END = ms('2026-08-01')
HOLD_FROM = ms('2026-08-01')
HOLD_TO = ms('2026-11-05')          # exclusive: Nov 4 is the last HO-1 day
LOCKBOX_FROM = ms('2026-11-06T05:00')
FOLD_EDGES = [ms(d) for d in ('2026-08-01', '2026-08-17', '2026-09-02', '2026-09-18', '2026-10-04', '2026-10-20', '2026-11-05')]

# Half-open [from, to) by decision time; a row also needs its horizon to end inside the split (see split_of).
SPLITS = {
    'perp': {'A': (ms('2020-01-01'), ms('2025-01-01')), 'B': (ms('2025-01-01'), DEV_END)},
    'pp15': {'A': (ms('2026-04-18'), ms('2026-06-15')), 'B': (ms('2026-06-15'), DEV_END)},
    'pp60': {'A': (ms('2026-04-18'), ms('2026-06-15')), 'B': (ms('2026-06-15'), DEV_END)},
    'tennis': {'A': (ms('2026-04-27T05:00'), ms('2026-06-22')), 'B': (ms('2026-06-22'), ms('2026-07-31'))},
}
SPLITS['perp-rev'] = dict(SPLITS['perp'])          # OR-H2: the same perpetual A / B discovery split
SIZE = {'perp': 300.0, 'pp15': 20.0, 'pp60': 20.0, 'tennis': 10.0, 'perp-rev': 300.0}      # perp-rev: the cap; each part sizes min(300, 5 / (M / 1e4))
SIZE2 = {'perp': 1000.0, 'pp15': 10.0, 'pp60': 10.0, 'tennis': 20.0, 'perp-rev': 1000.0}
MAX_CONTRACTS = {'pp15': 250, 'pp60': 250, 'tennis': 100}
SIDES = {'perp': ['L', 'S'], 'pp15': ['Y', 'N'], 'pp60': ['Y', 'N'], 'tennis': ['Y', 'N'], 'perp-rev': ['L', 'S']}
HORIZONS = {'perp': [15, 60], 'pp15': [15], 'pp60': [60], 'tennis': [15, 60], 'perp-rev': [5, 15, 60]}   # perp-rev: the part's meta.horizons rules
STEP_MIN = {'perp': 5, 'pp15': 1, 'pp60': 1, 'tennis': 1, 'perp-rev': 5}
POOLED = 'ALL'


def is_perp(ct: str) -> bool:
    """Perpetual contract types: the OR-H1 perp and the OR-H2 reversal variant (5-minute decisions, per-coin parts)."""
    return ct in ('perp', 'perp-rev')


def group_of(meta: dict):
    """The pooling group of a part: 'm<M>' for a reversal part of target M bps (its pooled scope is 'ALL-m<M>': parts of
    different targets have different labels and are never pooled together), None for every other part (pooled scope 'ALL')."""
    tb = meta.get('target_bps')
    if tb is None:
        return None
    return 'm' + (str(int(tb)) if float(tb) == int(tb) else str(tb).replace('.', 'p'))


def pooled_name(group) -> str:
    return POOLED if group is None else f'{POOLED}-{group}'


def is_pooled(scope: str) -> bool:
    return scope == POOLED or scope.startswith(POOLED + '-')


def split_of(t: np.ndarray, h: int, ct: str) -> np.ndarray:
    """Per row: 'A' / 'B' (discovery), 'H' (HO-1 hold) or '' (outside, embargo). A row belongs to a split only if its
    decision and its whole horizon (t + h minutes) fall inside it."""
    t = np.asarray(t, dtype=np.int64)
    end = t + h * MIN
    out = np.full(t.shape, '', dtype='<U1')
    for name, (a, b) in SPLITS[ct].items():
        out[(t >= a) & (end <= b)] = name
    out[(t >= HOLD_FROM) & (end <= HOLD_TO)] = 'H'
    return out


def dev_rows(t: np.ndarray, h: int) -> np.ndarray:
    """Rows a mining / confirmation step may read: the whole horizon ends before DEV_END."""
    t = np.asarray(t, dtype=np.int64)
    return t + h * MIN <= DEV_END


def fold_of(t: np.ndarray) -> np.ndarray:
    """HO-1 fold 0..5 of a decision time, -1 outside the hold."""
    t = np.asarray(t, dtype=np.int64)
    f = np.searchsorted(np.asarray(FOLD_EDGES), t, side='right') - 1
    f[(t < FOLD_EDGES[0]) | (t >= FOLD_EDGES[-1])] = -1
    return f


def key(name: str, side: str, h: int) -> str:
    """Array name for a side/horizon label, e.g. key('trade', 'L', 60) -> 'trade_L60'."""
    return f'{name}_{side}{h}'


def write_part(path: str, meta: dict, arrays: dict) -> None:
    """Write a part directory: every array as <name>.npy plus meta.json (schema, n, features...)."""
    os.makedirs(path, exist_ok=True)
    n = None
    for name, a in arrays.items():
        a = np.ascontiguousarray(a)
        if n is None:
            n = a.shape[0]
        if a.shape[0] != n:
            raise ValueError(f'{name}: {a.shape[0]} rows, expected {n}')
        np.save(os.path.join(path, name + '.npy'), a, allow_pickle=False)
    meta = dict(meta)
    meta['schema'] = SCHEMA
    meta['n'] = int(n or 0)
    if 'X' in arrays and 'features' in meta and arrays['X'].ndim == 2 and arrays['X'].shape[1] != len(meta['features']):
        raise ValueError('X columns != len(meta.features)')
    with open(os.path.join(path, 'meta.json'), 'w') as f:
        json.dump(meta, f, indent=1)


class Part:
    """A loaded part; arrays are memory-mapped and loaded on first access (part['trade_L60'])."""

    def __init__(self, path: str, mmap: bool = True):
        self.path = path
        with open(os.path.join(path, 'meta.json')) as f:
            self.meta = json.load(f)
        if self.meta.get('schema') != SCHEMA:
            raise ValueError(f'{path}: schema {self.meta.get("schema")!r} != {SCHEMA}')
        self._mmap = 'r' if mmap else None
        self._cache: dict = {}

    def __getitem__(self, name: str) -> np.ndarray:
        if name not in self._cache:
            self._cache[name] = np.load(os.path.join(self.path, name + '.npy'), mmap_mode=self._mmap, allow_pickle=False)
        return self._cache[name]

    def has(self, name: str) -> bool:
        return os.path.exists(os.path.join(self.path, name + '.npy'))

    @property
    def n(self) -> int:
        return int(self.meta['n'])

    @property
    def features(self) -> list:
        return self.meta['features']

    @property
    def ct(self) -> str:
        return self.meta['ct']

    @property
    def scope(self) -> str:
        return self.meta['scope']


def list_parts(root: str, ct: str) -> list:
    """Part directories of one contract type under root (perp-BTC, pp15-ETH, tennis-ATP ...), sorted; DOGE refused."""
    out = []
    longer = [c + '-' for c in CTS if c != ct and c.startswith(ct + '-')]       # 'perp' must not take 'perp-rev-*'
    for d in sorted(os.listdir(root)):
        if d.startswith(ct + '-') and not any(d.startswith(x) for x in longer) and os.path.exists(os.path.join(root, d, 'meta.json')):
            if 'DOGE' in d.upper():
                raise ValueError('DOGE part refused')
            out.append(os.path.join(root, d))
    return out
