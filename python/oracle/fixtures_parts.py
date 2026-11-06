"""Synthetic oracle parts (python/oracle/SPEC.md section 1 format) for the miner / sim tests and the miner's timing
benchmark. Nothing here is real data: every value is drawn from a seeded numpy generator.

make_part(root, ct, scope, ...) writes <root>/<ct>-<scope>/ with oracle.common.write_part:
- rows: decisions on the contract type's grid (perp: every 5 minutes; pp15: k = 1..10 of 15-minute windows; tennis: every
  minute of two-market events) for `hours_per_day` hours of every day from the start of discovery A to the end of HO-1
  (Nov 4, nothing later); the hours rotate by day so every hour bucket occurs. HO-1 rows are written as the builders
  write them (the tests overwrite them to prove the miner never reads them).
- features: n_state state features fs00.. (-1 / 0 / +1 w.p. .3 / .4 / .3), n_bucket bucket features fb00.. (4 levels, 3%
  NA), fb_rare (level 3 at 0.5%, under the 1% support), the strata context (perp ctx:hour4 and ctx:rv; Kalshi k_tau or
  the tennis phase) and, for pp15 / tennis, a side-relative pair k_price@Y / k_price@N listed in meta.side_features.
- labels per side s and horizon h: hit ~ Bernoulli(p), trade $ = 5..5.5 on a hit, else a loser ~ N(mu, 1.2) capped at
  4.9; p depends on the stratum (so the matched base matters). NaN trade where not ok (3% of rows).
  mode 'planted': base p 0.15, mu -1 (EV about -0.1 $); the PLANTED setup (fs03 = +1 and fb01 = 2, about 7% of rows) on
  side L (perp) / Y (Kalshi) lifts p to 0.45 at every horizon and on every split: a setup that truly works (EV about
  +1.8 $, hit uplift about +0.3). The other side has no edge.
  mode 'null': features independent of the labels and EV exactly 0 in every stratum (no edge anywhere).
- groups: perp = UTC day index; pp15 = the 15-minute window; tennis = the event (2 markets, mkt.npy, close.npy).

    cd python && python3 -m oracle.fixtures_parts --out <dir> --ct perp --scopes BTC,ETH --mode planted
    cd python && python3 -m oracle.fixtures_parts --out <dir> --ct perp --scopes BTC --hours 24 --n-state 320 --n-bucket 10
        (the miner benchmark: every 5-minute decision 2020-01-01 .. 2026-11-04, ~526k discovery-A rows x 333 features)
"""
from __future__ import annotations

import argparse
import os

import numpy as np

from .common import DAY, HOLD_TO, HORIZONS, MIN, SIDES, SIZE, SIZE2, SPLITS, STEP_MIN, key, write_part

HOUR = 60 * MIN
PLANTED_ITEMS = [{'f': 'fb01', 'v': 2}, {'f': 'fs03', 'v': 1}]
P_BASE, P_PLANTED, MU_LOSER = 0.15, 0.45, -1.0


def planted_setup(ct: str, h: int, scope: str = 'ALL') -> dict:
    """The setup the 'planted' fixture plants (SPEC 3 setup JSON fields that fire_mask needs)."""
    return {'ct': ct, 'scope': scope, 'side': SIDES[ct][0], 'h': int(h), 'items': [dict(x) for x in PLANTED_ITEMS]}


def _rows(ct: str, hours: int, rng, start_ms: int | None = None, end_ms: int = HOLD_TO) -> dict:
    """Decision rows of a part: t (sorted), group, and ct-specific extras."""
    d0 = int((start_ms if start_ms is not None else SPLITS[ct]['A'][0]) // DAY)
    d1 = int(end_ms // DAY)
    days = np.arange(d0, d1, dtype=np.int64)
    if ct == 'perp':
        per = hours * 60 // 5
        off = (days[:, None] * 5 % 24) * 60 + 5 * np.arange(per)[None, :]
        t = days[:, None] * DAY + (off % 1440) * MIN
        t = np.sort(t, axis=1).ravel()
        return {'t': t, 'group': t // DAY}
    if ct == 'pp15':
        wins = hours * 4
        off = (days[:, None] * 5 % 24) * 60 + 15 * np.arange(wins)[None, :]
        opens = np.sort(days[:, None] * DAY + (off % 1440) * MIN, axis=1).ravel()
        k = np.tile(np.arange(1, 11), len(opens))
        t = np.repeat(opens, 10) + k * MIN
        return {'t': t, 'group': np.repeat(np.arange(len(opens)), 10), 'kmin': k.astype(np.uint8)}
    if ct == 'tennis':
        L = 90                                                  # decisions per market: 30 min pre-start + 60 live
        ev_per_day = max(1, hours // 2)
        starts = np.sort((days[:, None] * DAY + (((days[:, None] * 5 % 24) + 2 * np.arange(ev_per_day)[None, :]) % 24) * HOUR
                          + 30 * MIN).ravel())
        E = len(starts)
        tm = np.arange(-30, L - 30)                             # minutes from the start
        t = (starts[:, None, None] + tm[None, :, None] * MIN + np.zeros((1, 1, 2), dtype=np.int64)).ravel()
        ev = np.repeat(np.arange(E), L * 2)
        mkt = (ev * 2 + np.tile([0, 1], E * L)).astype(np.int32)
        close = np.repeat(starts + (L - 30) * MIN + rng.integers(1, 40, E) * MIN, L * 2)
        tmin = np.tile(np.repeat(tm, 2), E).astype(np.int16)
        o = np.lexsort((mkt, t))
        out = {'t': t[o], 'group': ev[o], 'mkt': mkt[o], 'close': close[o], 'tmin': tmin[o]}
        keep = (out['t'] < out['close']) & (out['close'] <= end_ms)
        return {k_: v[keep] for k_, v in out.items()}
    raise ValueError(f'fixture ct {ct!r}')


def make_part(root: str, ct: str = 'perp', scope: str = 'BTC', mode: str = 'planted', seed: int = 1, hours: int = 2,
              n_state: int = 12, n_bucket: int = 6, start_ms: int | None = None) -> str:
    """Write one synthetic part <root>/<ct>-<scope>/ and return its path (see the module docstring)."""
    if 'DOGE' in scope.upper():
        raise ValueError('never DOGE')
    if mode not in ('planted', 'null'):
        raise ValueError('mode is planted or null')
    rng = np.random.default_rng(seed)
    R = _rows(ct, hours, rng, start_ms)
    t = R['t'].astype(np.int64)
    n = len(t)
    hour = ((t // HOUR) % 24).astype(np.int8)
    feats, cols = [], []

    def add(name, kind, levels, col, desc, **kw):
        feats.append({'name': name, 'kind': kind, 'levels': list(levels), 'desc': desc, **kw})
        cols.append(np.asarray(col, dtype=np.int8))

    for i in range(n_state):
        add(f'fs{i:02d}', 'state', [-1, 0, 1], rng.choice(np.array([-1, 0, 1], dtype=np.int8), n, p=[0.3, 0.4, 0.3]),
            'fixture: random state')
    for i in range(n_bucket):
        b = rng.integers(0, 4, n).astype(np.int8)
        b[rng.random(n) < 0.03] = -1
        add(f'fb{i:02d}', 'bucket', range(4), b, 'fixture: random 4-level bucket, 3% NA')
    rare = np.where(rng.random(n) < 0.005, 3, rng.integers(0, 3, n)).astype(np.int8)
    add('fb_rare', 'bucket', range(4), rare, 'fixture: level 3 at 0.5% (under the 1% support)')

    blk = t // (2 * HOUR) if ct == 'perp' else R['group']                      # RV tercile constant over a block
    rv_blk = np.random.default_rng(seed + 1000).integers(0, 3, int(blk.max()) + 1)
    rv = rv_blk[blk].astype(np.int8) if ct != 'tennis' else np.full(n, -1, dtype=np.int8)
    side_features = None
    strata = {}
    if ct == 'perp':
        h4 = (hour // 4).astype(np.int8)
        add('ctx:hour4', 'bucket', range(6), h4, 'UTC hour / 4')
        add('ctx:rv', 'bucket', range(3), rv, 'RV tercile')
        for s in SIDES[ct]:
            strata[s] = (h4.astype(np.int16) * 3 + rv).astype(np.int16)
        lift = lambda s: 0.04 * (rv == 2) - 0.03 * (rv == 0) + 0.01 * (h4 % 2)
    elif ct == 'pp15':
        tau = ((R['kmin'].astype(np.int16) - 1) * 3 // 10).astype(np.int8)
        add('k_tau', 'bucket', range(3), tau, 'thirds of the entry window')
        pb = np.repeat(rng.integers(0, 8, int(R['group'].max()) + 1), 1)[R['group']].astype(np.int8)
        add('k_price@Y', 'bucket', range(8), pb, "the side's ask bucket", side='Y', base='k_price')
        add('k_price@N', 'bucket', range(8), 7 - pb, "the side's ask bucket", side='N', base='k_price')
        F0 = len(feats)
        side_features = {'Y': [F0 - 2], 'N': [F0 - 1]}
        for s, b in (('Y', pb), ('N', 7 - pb)):
            strata[s] = ((b.astype(np.int16) * 3 + tau) * 4 + rv).astype(np.int16)
        lift = lambda s: 0.02 * ((pb if s == 'Y' else 7 - pb) - 3.5) / 3.5 + 0.02 * (rv == 2)
    else:
        phase = np.where(R['tmin'] < 0, 0, np.where(R['tmin'] < 60, 1, 2)).astype(np.int8)
        add('k_since', 'bucket', range(3), phase, 'match phase')
        pb = rng.integers(0, 10, int(R['mkt'].max()) + 1)[R['mkt']].astype(np.int8)
        add('k_price@Y', 'bucket', range(10), pb, "the side's ask bucket", side='Y', base='k_price')
        add('k_price@N', 'bucket', range(10), 9 - pb, "the side's ask bucket", side='N', base='k_price')
        F0 = len(feats)
        side_features = {'Y': [F0 - 2], 'N': [F0 - 1]}
        for s, b in (('Y', pb), ('N', 9 - pb)):
            strata[s] = (b.astype(np.int16) * 3 + phase).astype(np.int16)
        lift = lambda s: 0.02 * ((pb if s == 'Y' else 9 - pb) - 4.5) / 4.5 + 0.02 * (phase == 1)

    X = np.stack(cols, axis=1)
    names = [f['name'] for f in feats]
    planted = (X[:, names.index('fs03')] == 1) & (X[:, names.index('fb01')] == 2)
    arrays = {'t': t, 'group': R['group'].astype(np.int64), 'asset': np.zeros(n, dtype=np.int8), 'X': X, 'rv': rv,
              'hour': hour}
    for extra in ('mkt', 'close', 'tmin', 'kmin'):
        if extra in R:
            arrays[extra] = R[extra]
    size, size2 = SIZE[ct], SIZE2[ct]
    for s in SIDES[ct]:
        arrays[f'stratum_{s}'] = strata[s]
        p_row = np.clip((P_BASE if mode == 'planted' else 1 / 6) + lift(s), 0.02, 0.9)
        if mode == 'planted' and s == SIDES[ct][0]:
            p_row = np.where(planted, P_PLANTED, p_row)
        for h in HORIZONS[ct]:
            ok = (rng.random(n) < 0.97) & (strata[s] >= 0)
            hit = (rng.random(n) < p_row) & ok
            win = 5.0 + 0.5 * rng.random(n)
            mu = MU_LOSER if mode == 'planted' else -p_row * 5.25 / (1 - p_row)       # null: EV 0 in every stratum
            lose = np.minimum(rng.normal(mu, 1.2, n), 4.9)
            trade = np.where(hit, win, lose)
            trade[~ok] = np.nan
            if ct == 'pp15':
                rem = 15 - R['kmin'].astype(np.int64)
                hold = np.where(hit, 1 + (rng.random(n) * rem).astype(np.int64), rem)
            else:
                hold = np.where(hit, rng.integers(1, h + 1, n), h)
            best = np.where(ok, np.maximum(trade, trade + np.abs(rng.normal(0, 1.5, n))), np.nan)
            arrays[key('ok', s, h)] = ok.astype(np.uint8)
            arrays[key('hit', s, h)] = hit.astype(np.uint8)
            arrays[key('trade', s, h)] = trade.astype(np.float32)
            arrays[key('best', s, h)] = best.astype(np.float32)
            arrays[key('hold', s, h)] = hold.astype(np.uint16)
            arrays[key('hit2', s, h)] = hit.astype(np.uint8)
            arrays[key('trade2', s, h)] = (trade * size2 / size).astype(np.float32)
            arrays[key('tradeLat', s, h)] = (trade + rng.normal(0, 0.3, n)).astype(np.float32)
            arrays[key('tradeCost', s, h)] = (trade - 0.15).astype(np.float32)
            if ct == 'perp':
                arrays[key('bestbps', s, h)] = (best / size * 1e4).astype(np.float32)
    meta = {'ct': ct, 'scope': scope, 'assets': [scope], 'sides': SIDES[ct], 'horizons': HORIZONS[ct], 'size_usd': size,
            'size2_usd': size2, 'step_min': STEP_MIN[ct], 'code_sha': 'fixture', 'features': feats,
            'strata_desc': 'fixture strata (perp hour4 x 3 + rv; pp15 (price x 3 + tau) x 4 + rv; tennis price x 3 + phase)',
            'notes': f'SYNTHETIC fixture part (oracle/fixtures_parts.py), mode {mode}, seed {seed}: not real data',
            'fixture': {'mode': mode, 'seed': seed, 'planted': PLANTED_ITEMS if mode == 'planted' else None,
                        'planted_side': SIDES[ct][0] if mode == 'planted' else None}}
    if side_features:
        meta['side_features'] = side_features
    path = os.path.join(root, f'{ct}-{scope}')
    write_part(path, meta, arrays)
    return path


def make_parts(root: str, ct: str = 'perp', scopes=('BTC', 'ETH'), mode: str = 'planted', seed: int = 1, **kw) -> list:
    """One part per scope (seeds seed, seed + 1, ...); returns their paths."""
    return [make_part(root, ct, sc, mode, seed + i, **kw) for i, sc in enumerate(scopes)]


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description='Write synthetic oracle parts (fixtures, not real data).')
    ap.add_argument('--out', required=True)
    ap.add_argument('--ct', default='perp', choices=('perp', 'pp15', 'tennis'))
    ap.add_argument('--scopes', default='BTC,ETH')
    ap.add_argument('--mode', default='planted', choices=('planted', 'null'))
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--hours', type=int, default=2, help='decision hours per day (24 = every decision)')
    ap.add_argument('--n-state', type=int, default=12)
    ap.add_argument('--n-bucket', type=int, default=6)
    a = ap.parse_args(argv)
    for p in make_parts(a.out, a.ct, [s for s in a.scopes.split(',') if s], a.mode, a.seed, hours=a.hours,
                        n_state=a.n_state, n_bucket=a.n_bucket):
        print(p)


if __name__ == '__main__':
    main()
