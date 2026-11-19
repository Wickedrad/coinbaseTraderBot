"""From firing event keys to scored calls (PREREG.md sections 2 and 6). No engine here: `events` come from heatloop.events (the
oracle readings, runner only), so this module is pure numpy and is tested without TA-Lib.

  Spec               one frozen call rule (admission, combiner, lockout), hashed with `spec_hash`
  admit(rows, spec)  the pack rows a spec lets through, in rank order, one coin at a time
  decide(...)        events -> calls: at most one per coin per `lockout` minutes, decided from the events of that minute only
  outcomes(...)      calls -> rubric.Calls: the 15 minute move, the one-minute-late move and the naive-rule signs

An event row is (entry_row, key): the reading is known at its bar's close and the entry is the open of the next minute
(entry_row, a grid row), so a call at entry_row uses only bars that closed at or before entry_row - 1.
"""
import dataclasses
import hashlib
import json

import numpy as np

from heatloop import rubric

MIN = 60_000


@dataclasses.dataclass(frozen=True)
class Spec:
    coins: tuple = ('BTC', 'ETH')
    horizon: int = 15                 # minutes, the scored time frame
    tfs: tuple = ('1m', '5m')         # reading bars a level may come from
    top_n: int = 10                   # admit the top_n pack rows per coin by rank_coin (the lane's HEAT_TOP_N)
    min_share_A: float = 0.0          # cross-year admission: build-years share right, percent
    min_share_B: float = 0.0
    min_n_B: int = 0
    combiner: str = 'hottest'         # 'hottest' = the firing admitted row with the best rank; 'vote' = sum of the firing rows' sides
    vote_k: int = 3                   # vote: the k best-ranked firing rows
    margin: int = 1                   # vote: |sum of sides| needed
    lockout: int = 15                 # minutes after a call before the coin may call again
    lag: int = 0                      # extra entry delay in minutes (the call is made at the event minute + lag)

    def as_dict(self):
        d = dataclasses.asdict(self)
        d['coins'], d['tfs'] = list(self.coins), list(self.tfs)
        return d


def spec_hash(spec: Spec) -> str:
    return hashlib.sha256(json.dumps(spec.as_dict(), sort_keys=True).encode()).hexdigest()


def admit(rows: list, spec: Spec, coin: str) -> list:
    """The pack rows of `coin` at the spec's horizon that pass its admission, best rank first. A row may be listed under aliases
    (the same event under another name); the caller maps those keys to the row."""
    out = []
    for r in rows:
        if r['coin'] != coin or int(r['h']) != spec.horizon or r['tf'] not in spec.tfs:
            continue
        if float(r['share_A']) < spec.min_share_A or float(r['share_B']) < spec.min_share_B or int(r['n_B']) < spec.min_n_B:
            continue
        out.append(r)
    out.sort(key=lambda r: (int(r['rank_coin']), r['key']))
    return out[:spec.top_n]


def key_index(admitted: list) -> dict:
    """event key -> admitted row (the row's own key and every alias)."""
    idx = {}
    for r in admitted:
        for k in [r['key']] + list(r.get('aliases') or []):
            idx.setdefault(k, r)
    return idx


def decide(events: list, admitted: list, spec: Spec) -> list:
    """events: [(entry_row, key)] for one coin. Returns [(entry_row, side, key)] with side +1 UP / -1 DOWN, in time order."""
    if spec.combiner not in ('hottest', 'vote'):
        raise ValueError(f'unknown combiner {spec.combiner!r}')
    idx = key_index(admitted)
    by_row = {}
    for row, key in events:
        r = idx.get(key)
        if r is not None:
            by_row.setdefault(int(row), {})[r['key']] = r
    calls, nxt = [], -1
    for row in sorted(by_row):
        e = row + spec.lag
        if e < nxt:
            continue
        firing = sorted(by_row[row].values(), key=lambda r: (int(r['rank_coin']), r['key']))
        if spec.combiner == 'hottest':
            side, key = int(firing[0]['dir']), firing[0]['key']
        else:
            top = firing[:spec.vote_k]
            s = sum(int(r['dir']) for r in top)
            if abs(s) < spec.margin or s == 0:
                continue
            side, key = (1 if s > 0 else -1), top[0]['key']
        calls.append((e, side, key))
        nxt = e + spec.lockout
    return calls


def outcomes(coin: str, calls: list, o: np.ndarray, step: float, horizon: int = 15, t0: int = 0, rows_hi: int = None) -> dict:
    """The arrays of rubric.Calls for one coin. o = the grid's open prices (row i = minute t0 + i*MIN); rows_hi = the first row the
    scope may not use (a call whose late outcome would reach it is dropped, never clipped)."""
    n = len(o) if rows_hi is None else min(len(o), rows_hi)
    keep = [(e, s, k) for e, s, k in calls if 60 <= e and e + 1 + horizon < n]
    e = np.array([c[0] for c in keep], np.int64)
    side = np.array([c[1] for c in keep], int)
    move = (o[e + horizon] - o[e]) / step if len(e) else np.array([])
    late = (o[e + 1 + horizon] - o[e + 1]) / step if len(e) else np.array([])
    past = {k: (np.sign(np.round((o[e] - o[e - k]) / step)).astype(int) if len(e) else np.array([], int)) for k in rubric.NAIVE_KS}
    return dict(ts=t0 + e * MIN, coin=np.array([coin] * len(e)), side=side, move=move, move_late=late, past=past,
                key=[c[2] for c in keep])


def to_calls(parts: list) -> rubric.Calls:
    """Join the per-coin outcome dicts into one rubric.Calls (time order)."""
    parts = [p for p in parts if len(p['ts'])]
    if not parts:
        z = np.array([])
        return rubric.Calls(z.astype(np.int64), z.astype(str), z.astype(int), z, z, {k: z.astype(int) for k in rubric.NAIVE_KS}, None)
    cat = lambda f: np.concatenate([p[f] for p in parts])
    ts = cat('ts')
    o = np.argsort(ts, kind='stable')
    past = {k: np.concatenate([p['past'][k] for p in parts])[o] for k in rubric.NAIVE_KS}
    return rubric.Calls(ts[o], cat('coin')[o], cat('side')[o], cat('move')[o], cat('move_late')[o], past, None)
