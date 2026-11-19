"""From firing event keys to scored calls (PREREG.md sections 2 and 6). No engine here: `events` come from heatloop.events (the
oracle readings, runner only), so this module is pure numpy and is tested without TA-Lib.

  Spec               one frozen call rule (admission, combiner, lockout), hashed with `spec_hash`
  admit(rows, spec)  the pack rows a spec lets through, in rank order, one coin at a time
  decide(...)        events -> calls: at most one per coin per `lockout` minutes, decided from the events of that minute only
  outcomes(...)      calls -> rubric.Calls: the 15 minute move, the one-minute-late move and the naive-rule signs

An event row is (entry_row, key): the reading is known at its bar's close and the entry is the open of the next minute
(entry_row, a grid row), so a call at entry_row uses only bars that closed at or before entry_row - 1.
"""
import bisect
import dataclasses
import hashlib
import json
import re

import numpy as np

from heatloop import rubric

MIN = 60_000


def family(key: str) -> str:
    """'5m:RSI14=very high' -> 'RSI': the indicator without its bars, level and trailing parameters (RSI7 and RSI14 are one family)."""
    ind = key.rsplit('=', 1)[0].split(':', 1)[-1].removesuffix(' sign')
    return re.sub(r'[\d/.]+$', '', ind) or ind


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
    ta_confirm: str = 'none'          # 'none' | 'precedes' (label calls) | 'follows' (the call waits for a confirmer)
    ta_conf_k: int = 15               # minutes: precedes looks back k, follows waits j
    ta_inv_k: int = 0                 # 0 = no invalidation; else an opposing pool event within the last k minutes drops the call
    ta_pool: int = 20                 # the TA pool: the best-ranked rows of the universe across all bars

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


def decide(events: list, admitted: list, spec: Spec, pool: list = None) -> dict:
    """events: [(entry_row, key)] for one coin (base and pool keys). Returns
    {'calls': [(e, side, key, confirmed)], 'inv': [(e, side, key)], 'unconf': [(e, side, key)]}, each in time order.
    calls: one per coin per `lockout` minutes, decided from the events up to its own entry row. inv: the calls the TA layer
    dropped, scored as if made (their own lockout). unconf: the base calls a `follows` confirmation never confirmed in time
    plus the ones it did, scored as if made at their own minute (their own lockout); the made calls are the confirmed set."""
    if spec.combiner not in ('hottest', 'vote'):
        raise ValueError(f'unknown combiner {spec.combiner!r}')
    if spec.ta_confirm not in ('none', 'precedes', 'follows'):
        raise ValueError(f'unknown ta_confirm {spec.ta_confirm!r}')
    idx = key_index(admitted)
    pidx = key_index(pool or [])
    by_row, pool_ev = {}, []
    for row, key in events:
        r = idx.get(key)
        if r is not None:
            by_row.setdefault(int(row), {})[r['key']] = r
        q = pidx.get(key)
        if q is not None:
            pool_ev.append((int(row), int(q['dir']), family(q['key'])))
    pool_ev.sort()
    rows_p = [x[0] for x in pool_ev]
    def pool_in(lo, hi):
        """pool events with entry row in [lo, hi]."""
        return pool_ev[bisect.bisect_left(rows_p, lo):bisect.bisect_right(rows_p, hi)]

    calls, inv, unconf = [], [], []
    nxt = nxt_inv = nxt_unc = -1
    for row in sorted(by_row):
        e = row + spec.lag
        firing = sorted(by_row[row].values(), key=lambda r: (int(r['rank_coin']), r['key']))
        if spec.combiner == 'hottest':
            side, key = int(firing[0]['dir']), firing[0]['key']
        else:
            top = firing[:spec.vote_k]
            sm = sum(int(r['dir']) for r in top)
            if abs(sm) < spec.margin or sm == 0:
                continue
            side, key = (1 if sm > 0 else -1), top[0]['key']
        fam = family(key)
        if spec.ta_inv_k:
            if any(sd != side and f != fam for _, sd, f in pool_in(row - spec.ta_inv_k, row)):
                if e >= nxt_inv:                         # dropped: scored as if made, one per lockout window
                    inv.append((e, side, key))
                    nxt_inv = e + spec.lockout
                continue
        if spec.ta_confirm == 'follows':
            if e >= nxt_unc:                             # the base call, scored as if made
                unconf.append((e, side, key))
                nxt_unc = e + spec.lockout
            hit = [r2 for r2, sd, f in pool_in(row + 1, row + spec.ta_conf_k) if sd == side and f != fam]
            if hit and hit[0] + spec.lag >= nxt:
                e2 = hit[0] + spec.lag
                calls.append((e2, side, key, True))
                nxt = e2 + spec.lockout
            continue
        if e < nxt:
            continue
        conf = None
        if spec.ta_confirm == 'precedes':
            conf = any(sd == side and f != fam for _, sd, f in pool_in(row - spec.ta_conf_k, row))
        calls.append((e, side, key, conf))
        nxt = e + spec.lockout
    return {'calls': calls, 'inv': inv, 'unconf': unconf}


def _arrays(coin: str, items: list, o: np.ndarray, step: float, horizon: int, t0: int, n: int) -> dict:
    keep = [c for c in items if 60 <= c[0] and c[0] + 1 + horizon < n]
    e = np.array([c[0] for c in keep], np.int64)
    side = np.array([c[1] for c in keep], int)
    move = (o[e + horizon] - o[e]) / step if len(e) else np.array([])
    late = (o[e + 1 + horizon] - o[e + 1]) / step if len(e) else np.array([])
    past = {k: (np.sign(np.round((o[e] - o[e - k]) / step)).astype(int) if len(e) else np.array([], int)) for k in rubric.NAIVE_KS}
    conf = None if not keep or keep[0][3:] == () or keep[0][3] is None else np.array([bool(c[3]) for c in keep])
    return dict(ts=t0 + e * MIN, coin=np.array([coin] * len(e)), side=side, move=move, move_late=late, past=past, conf=conf,
                key=[c[2] for c in keep])


def outcomes(coin: str, calls: list, o: np.ndarray, step: float, horizon: int = 15, t0: int = 0, rows_hi: int = None) -> dict:
    """The arrays of rubric.Calls for one coin (calls: [(e, side, key[, confirmed])]). o = the grid's open prices (row i = minute
    t0 + i*MIN); rows_hi = the first row the scope may not use (a call whose late outcome would reach it is dropped, never clipped)."""
    n = len(o) if rows_hi is None else min(len(o), rows_hi)
    return _arrays(coin, [c if len(c) == 4 else c + (None,) for c in calls], o, step, horizon, t0, n)


def to_calls(parts: list) -> rubric.Calls:
    """Join the per-coin outcome dicts into one rubric.Calls (time order). conf stays None unless every part has it."""
    parts = [p for p in parts if len(p['ts'])]
    if not parts:
        z = np.array([])
        return rubric.Calls(z.astype(np.int64), z.astype(str), z.astype(int), z, z, {k: z.astype(int) for k in rubric.NAIVE_KS}, None)
    cat = lambda f: np.concatenate([p[f] for p in parts])
    ts = cat('ts')
    o = np.argsort(ts, kind='stable')
    past = {k: np.concatenate([p['past'][k] for p in parts])[o] for k in rubric.NAIVE_KS}
    conf = np.concatenate([p['conf'] for p in parts])[o] if all(p['conf'] is not None for p in parts) else None
    return rubric.Calls(ts[o], cat('coin')[o], cat('side')[o], cat('move')[o], cat('move_late')[o], past, conf)
