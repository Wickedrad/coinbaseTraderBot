"""OR-HM2 part 1: the exhaustive pair scan, the fixed triples, the re-measure and the series outputs
(python/oracle/prereg/OR-HM2.md; build plan sections 2 and 4). It changes no line of oracle.heat and no stored table.

  python3 -m oracle.heat_hm2 coin   --asset BTC --csv <1m.csv> --others ETH=<csv>,SOL=<csv>,XRP=<csv> --perp <csv> --fund <csv>
                                    --oi <csv> --cal <csv> --dom <dir> --main-meta <COIN[-twinN]/meta.json> --other-metas <dir>
                                    --out <dir> [--twin N] [--part i/S] [--procs 4] [--hm1-packs a.json,b.json] [--hm1-pairs <csv.gz>]
                                    [--shards <dir>] [--found <json>]
  python3 -m oracle.heat_hm2 finish (the same inputs) --parts <dir>,<dir>,...   the triples and the re-measure after a --part split
  python3 -m oracle.heat_hm2 bench  (the same inputs) [--pairs 3000]            ms per pair, peak RSS, projected minutes and shard size
  python3 -m oracle.heat_hm2 league / parity                                     (oracle.heat_hm2_league)

What one series job (one coin or one no-signal twin) does:
  entries   A: every 7th valid row of 2020-2024 (row % 7 == 0); B: every valid minute of 2025. The decision is the row's
            close, the entry the next minute's open.
  labels    1, 5, 15, 30, 60 minutes: the engine's (oracle.heat.labels on the engine's Grid, HMAX 60). 240 minutes:
            oracle.heat_long's int16 label function with the horizon 240 alone, on its own Grid (its A rows end 240 minutes
            before 2025, so no A label reads a 2025 price); an entry counts at 240 only when it is a valid row of that grid.
  pairs     every pair of readings with a different base. Each entry's two states give a cell. Counting is exact: one
            count bincount and four packed weighted bincounts per pair over the key (cell, day); the reading with fewer
            entries off its neutral level leads and only those entries are counted (its neutral cells are the other
            reading's own per-day totals minus the counted cells: whole numbers, so identical to a full count).
  per cell  (split, horizon): n, days, share up / down, odds = 50 x (mean sign - base mean sign) with its day-clustered t
            (heat._clu's algebra), share right and over base, minutes held and over base, windows per day (B), the
            interaction iota (log-linear [ab][ay][by] by iterative proportional fitting), iota_add (additive on the
            mean-sign scale, by backfitting), iota_robust (the one nearer zero when they agree in sign, else 0), iota_naive,
            odds_fit, lift_min (over each part) with its t, and the columns beside them (parts' own odds and t on A,
            parts_hot, part_tmax, assoc, families, learner_path, seen_in_league).
  marks     columns only: no pass bar removes a cell. The sample floor (30 entries on 30 days of A, 30 on 20 days of B)
            is the engine's, and the cells under it are counted.
  triples   (a) the 120 confluence pair cells with the largest |iota_robust| / SE on A at 15, 60 or 240 minutes (n_A >=
            2,000, at most 3 per reading: chosen on A only), each as an in/out flag crossed with every reading; (b) the
            learner's three-reading leaf paths (oracle.heat_hm2_learn), their 2x2x2 table and iota3.
  outputs   summary counts (mergeable across --part jobs), the top-1,000 candidate heaps per (kind, horizon, measure),
            the re-measured rows (heat.csv.gz in the tables' format: kinds xstate, xonset, xtriple, single, baseline),
            the near-copy Jaccard table, and on the real coins the cell shards (streamed to a directory the workflow
            uploads; a twin keeps only the small files).
Coin minutes 2020-01-01 to 2025-12-31 only (the loaders refuse a later minute). A MAP on coin price, not a Kalshi-price
result. NEVER DOGE.
"""
import argparse
import contextlib
import gzip
import hashlib
import json
import math
import os
import re
import resource
import time

import numba as nb
import numpy as np
import pandas as pd

from oracle import heat, heat_long

# ------------------------------------------------------------------------------------------------ constants (OR-HM2)
A_STRIDE = 7                    # A entries: every 7th valid row (7 shares no factor with 5, 15, 30 or 60)
H_SCAN = [1, 5, 15, 30, 60, 240]
H_MAIN = [1, 5, 15, 30, 60]     # the engine's horizons (its Grid, HMAX 60)
PACK_H = [15, 60, 240]
MERGE_AGREE = 0.995
N_TRIPLE_CELLS = 120
TRIPLE_MIN_A = 2000
PER_READING = 3
TOP = {'oheat': 40, 'iheat': 40, 'lheat': 20}
N_CANDIDATES = 200              # re-measured per (kind, horizon, measure)
CAND_POOL = 1000                # kept in candidates.csv.gz per (kind, horizon, measure) (the league may need rows past 200)
TRIPLE_POOL = 2000              # A-ranked pair cells kept for the triple choice (plus each reading's best 3)
IPF_ITERS = 30
LEARN_H = [1, 5, 15, 60, 240]
LGB_PARAMS = {'objective': 'regression', 'num_leaves': 8, 'max_depth': 3, 'learning_rate': 0.05, 'min_data_in_leaf': 3000, 'lambda_l2': 10.0,
              'feature_fraction': 0.5, 'bagging_fraction': 0.5, 'bagging_freq': 1, 'max_bin': 15, 'max_cat_threshold': 8, 'cat_smooth': 50,
              'min_data_per_group': 3000, 'deterministic': True, 'force_row_wise': True, 'num_threads': 4, 'verbose': -1}
LGB_ROUNDS = 300
LGB_SEED = 20261111             # + H
NEAR_COPY = 0.8                 # B-entry Jaccard at which two rows are one event under two names (the league collapses them)
JACC_WRITE = 0.5                # candidate pairs at or above this Jaccard are written (near_copies.csv.gz)
BATCH = 400                     # pairs per worker job (one shard file each)
MEASURES = ('oheat', 'iheat', 'lheat')
B12, B17 = 12, 17               # bits of a packed count / hold sum
M12, M17 = (1 << B12) - 1, (1 << B17) - 1
T_BINS = [1.0, 2.0, 3.0, 4.0]   # A |t| bins of the persistence curve: 0-1, 1-2, 2-3, 3-4, >= 4
PT_BINS = [2.0, 3.0]            # part_tmax strata: under 2, 2-3, 3 and over
PROV = ['none', 'stored', 'pack']
EVENT_SUFFIX = re.compile(r' \((falling in|recovering|rising in|cooling)\)$')
FAMILY_PREFIX = [('POS:', 'position'), ('X:', 'cross-coin'), ('X.', 'cross-coin'), ('VOL:', 'volatility'), ('FLOW:', 'flow'), ('PERP:', 'perp'),
                 ('OI:', 'open interest'), ('DMKT:', 'daily markets'), ('IDX:', 'btcdom'), ('CB:', 'coinbase'), ('BOOK:', 'book'), ('MACRO:', 'macro'),
                 ('GBM.', 'model'), ('ZS:', 'zone side'), ('BASE:', 'baseline')]
CLOCK = {'UTC1h', 'NY30m', 'Weekday'}

# per cell, split and horizon (the order of the last axis of the stats arrays); SHARD_STATS go to the shards as float16
STATS = ['odds', 't', 'se', 'deff', 'p_up', 'p_dn', 'hold_up', 'hold_dn', 'wd', 'iota', 'iota_add', 'iota_robust', 't_iota', 't_iota_add',
         't_robust', 'iota_naive', 'odds_fit', 'lift_min', 't_lift', 'rest_n']
SI = {k: i for i, k in enumerate(STATS)}
SHARD_STATS = ['odds', 't', 'p_up', 'p_dn', 'hold_up', 'hold_dn', 'wd', 'iota', 'iota_add', 'iota_robust', 't_iota', 'iota_naive', 'odds_fit',
               'lift_min', 't_lift', 'deff']


def _refuse_doge(*xs):
    for x in xs:
        if x and 'DOGE' in str(x).upper():
            raise SystemExit('NEVER DOGE')


def _rss_mb() -> float:
    """Peak resident memory of this process and of its finished workers, in MB."""
    a = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    b = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    return round(max(a, b) / 1024.0, 1)


def _imap(fn, items, procs: int):
    """heat._pmap with results streamed back as they finish (the parent merges them one by one: a list of every
    batch's summary would not fit). Workers are forked, so they read the context in heat._W."""
    if procs <= 1 or len(items) < 2:
        for x in items:
            yield fn(x)
        return
    import multiprocessing as mp
    with mp.get_context('fork').Pool(procs) as pool:
        yield from pool.imap_unordered(fn, items, chunksize=1)


# ------------------------------------------------------------------------------------------------------------- grids
@contextlib.contextmanager
def h240():
    """oracle.heat with the 240-minute horizon alone (as heat_long.long_horizons does for 240 and 1440): HORIZONS = [240],
    HMAX = 240, labels = heat_long.labels (int16 holds). Restored in finally."""
    saved = (heat.HORIZONS, heat.HMAX, heat.labels)
    heat.HORIZONS, heat.HMAX, heat.labels = [240], 240, heat_long.labels
    try:
        yield
    finally:
        heat.HORIZONS, heat.HMAX, heat.labels = saved


class _NoCurves:
    """The grid as build_readings sees it, with the decile-curve cells switched off (the scan does not use the curve
    rows; the zone edges come from the same split-A bars, so they are the engine's)."""

    def __init__(self, g):
        self._g = g

    def pre(self, E, s):
        return {}

    def cells(self, s, pre, codes, L, *a, **k):
        return {'n': np.zeros(L, np.int64)}

    def __getattr__(self, k):
        return getattr(self._g, k)


def family_of(R: dict) -> str:
    """The data family of a reading: its own 'family', else the name prefix, else the vocabulary's type (osc, atr, dist,
    pct, cum, z, regime, vol), pattern, context (dominance, UTC4h), clock or state (two-state and categorical)."""
    if R.get('family'):
        return str(R['family'])
    nm = R['name']
    for p, f in FAMILY_PREFIX:
        if nm.startswith(p):
            return f
    if nm in CLOCK:
        return 'clock'
    if R.get('every'):
        return 'pattern'
    if R.get('ctx'):
        return 'context'
    return str(R.get('type') or 'state')


# --------------------------------------------------------------------------------------------------- the series base
class Ctx:
    """What every stage of one series reads (the fork workers inherit it through heat._W).

      asset, label, twin, real    the coin, its label, twin number (0 = the coin) and whether it writes cell shards
      m, lab, g                   minutes, the engine's labels and Grid (HMAX 60)
      lab240, g240                the 240-minute labels and Grid (read them under h240())
      readings, names, fam        the readings after the copy merge (engine dicts), their names and families
      byname                      name (aliases included) -> reading index
      aliases                     kept name -> merged names
      rows, split, day, v240      the entries: minute row, 0 = A / 1 = B, day on the entry axis (0 = A's first day),
                                  valid at 240
      C                           uint8 [entries, readings], Fortran order: read_state + 1 (0 = NA)
      W                           float64 [4, entries]: the packed weights (pack_weights)
      T, toff                     reading totals: packed per-(level, day) sums of every reading (reading_totals)
      L, skip, work, nonneu       levels per reading, the code of the neutral level the shortcut skips (0: none), entries
                                  off it, and per code whether it is a known non-neutral level
      base                        per split: mean sign, share up / down per horizon, the per-day base influence, holds
      parts                       each reading's own state odds, t and n per split, horizon and level (part_effects)
    """


def _base_info(g, g240, dayref: int, ND: int) -> dict:
    """Per split: the base of the odds (every valid row of the split, as in the engine) on the entry day axis."""
    out = {}
    for si, s in enumerate(('A', 'B')):
        sp, sp4 = g.sp[s], g240.sp[s]
        lo = sp.d0 - dayref
        b = {'lo': lo, 'hi': lo + sp.ND, 'bms': np.zeros(6), 'bpu': np.zeros(6), 'bpd': np.zeros(6), 'beta': np.zeros((6, sp.ND)), 'N': np.zeros(6),
             'ndays': np.zeros(6), 'hold_up': float(sp.base.get('hold_up', np.nan) if sp.N else np.nan),
             'hold_dn': float(sp.base.get('hold_dn', np.nan) if sp.N else np.nan)}
        for hi_, H in enumerate(H_SCAN):
            q, gg = (sp4, 240) if H == 240 else (sp, H)
            if not q.N:
                b['bms'][hi_] = b['bpu'][hi_] = b['bpd'][hi_] = np.nan
                continue
            st = q.base[gg]
            b['bms'][hi_], b['bpu'][hi_], b['bpd'][hi_] = st['msign'], st['p_up'], st['p_dn']
            off = q.d0 - sp.d0                                  # the 240 grid's split starts on the same row
            bd = q.bd_s[gg]
            b['beta'][hi_, off:off + len(bd)] = bd / q.N        # zero on days the 240 grid does not reach (no entry there)
            b['N'][hi_] = q.N
            b['ndays'][hi_] = q.ndays
        out[si] = b
    return out


def entry_rows(g, g240) -> dict:
    """rows (A: every A_STRIDE-th valid row of A; B: every valid row of B), split (0 / 1), day (the Grid's day of the row
    on one axis for both splits, 0 = A's first day), v240 (the row is a valid row of g240's split)."""
    rA = g.sp['A'].rows
    rA = rA[rA % A_STRIDE == 0]
    rB = g.sp['B'].rows
    rows = np.r_[rA, rB].astype(np.int64)
    split = np.r_[np.zeros(len(rA), np.int8), np.ones(len(rB), np.int8)]
    dayref = int(g.sp['A'].d0)
    day = (g.day[rows] - dayref).astype(np.int64)
    ok240 = np.zeros(g.n, bool)
    for s in ('A', 'B'):
        ok240[g240.sp[s].rows] = True
    return {'rows': rows, 'split': split, 'day': day, 'dayref': dayref, 'v240': ok240[rows]}


def code_matrix(readings: list, rows: np.ndarray) -> np.ndarray:
    """uint8 [entries, readings] in Fortran order (one reading's column is contiguous): heat.read_state + 1, 0 = NA."""
    C = np.empty((len(rows), len(readings)), np.uint8, order='F')
    for j, R in enumerate(readings):
        if len(R['levels']) > 254:
            raise SystemExit(f'{R["name"]}: more than 254 levels')
        C[:, j] = (heat.read_state(R, rows).astype(np.int16) + 1).astype(np.uint8)
    return C


def merge_aliases(readings: list, entriesA: np.ndarray, codes: np.ndarray = None, log=print) -> tuple:
    """Readings whose codes agree on at least MERGE_AGREE of the A entries where both are known (and at least one is
    off its neutral level: two rare patterns are not copies because both are 'none' on most minutes) become one
    reading, the first by name order keeping the row and the others listed as its aliases. Only readings with the same
    level list can agree. A twin applies the rule to its own codes."""
    names = [R['name'] for R in readings]
    X = codes if codes is not None else code_matrix(readings, entriesA)
    order = sorted(range(len(readings)), key=lambda i: names[i])
    groups = {}
    for i in order:
        groups.setdefault(tuple(readings[i]['levels']), []).append(i)
    rng = np.random.default_rng(20261111)
    samp = np.sort(rng.choice(len(X), min(len(X), 4000), replace=False)) if len(X) else np.zeros(0, np.int64)
    dropped, aliases = set(), {}
    for lv, idx in groups.items():
        if len(idx) < 2:
            continue
        neu = np.r_[False, [x in heat.NEUTRAL for x in lv]]            # by code (0 = NA)
        sub = X[samp][:, idx].astype(np.int16)
        for p, i in enumerate(idx):
            if i in dropped or p == len(idx) - 1:
                continue
            a, b = sub[:, p:p + 1], sub[:, p + 1:]
            use = (a > 0) & (b > 0) & ~(neu[a] & neu[b])
            m = use.sum(0)
            with np.errstate(invalid='ignore', divide='ignore'):
                agree = ((a == b) & use).sum(0) / m
            for q in np.flatnonzero((agree >= 0.98) | (m < 30)):           # a sample prefilter; the full A entries decide
                j = idx[p + 1 + q]
                if j in dropped:
                    continue
                ca, cb = X[:, i].astype(np.int16), X[:, j].astype(np.int16)
                u = (ca > 0) & (cb > 0) & ~(neu[ca] & neu[cb])
                k = int(u.sum())
                if k >= 30 and float(((ca == cb) & u).sum()) / k >= MERGE_AGREE:
                    dropped.add(j)
                    aliases.setdefault(names[i], []).append(names[j])
    keep = [R for i, R in enumerate(readings) if i not in dropped]
    for R in keep:
        if R['name'] in aliases:
            R['aliases'] = sorted(aliases[R['name']])
    if aliases:
        log(f'  merged {len(dropped)} readings into {len(aliases)} (codes agree on >= {MERGE_AGREE:.1%} of A entries)')
    return keep, aliases


def pack_weights(lab: dict, lab240: dict, E: dict) -> np.ndarray:
    """Four float64 weights per entry that pack whole-number fields (12 bits per count, 17 per hold sum):
      W1: up1, dn1, up5, dn5        W2: up15, dn15, up30, dn30        W3: up60, dn60, up240, dn240
      W4: valid at 240, holdU, holdD of the 60-minute grid (0-60 each).
    A bin of a weighted bincount over (cell, day) then holds every field's per-day sum exactly, as long as each field
    stays under its 2^bits (a day has at most 1,440 entries: 1,440 < 2^12 and 60 x 1,440 = 86,400 < 2^17) and the
    whole number under 2^53 (the top field ends at bit 46 or 48)."""
    r, v = E['rows'], E['v240']
    per_day = np.bincount(E['day']).max() if len(r) else 0
    if per_day > M12 or 60 * per_day > M17:
        raise SystemExit(f'pack_weights: {per_day} entries on one day overflow a packed field')
    f = lambda x: x.astype(np.float64)
    sg = {H: lab[f'sg{H}'][r] for H in H_MAIN}
    s240 = np.where(v, lab240['sg240'][r], 0)
    up = {H: f(sg[H] > 0) for H in H_MAIN}
    dn = {H: f(sg[H] < 0) for H in H_MAIN}
    up[240], dn[240] = f(s240 > 0), f(s240 < 0)
    W = np.empty((4, len(r)))
    for w, (h1, h2) in enumerate(((1, 5), (15, 30), (60, 240))):
        W[w] = up[h1] + dn[h1] * 2.0 ** 12 + up[h2] * 2.0 ** 24 + dn[h2] * 2.0 ** 36
    hu, hd = f(lab['holdU'][r]), f(lab['holdD'][r])
    if len(r) and (hu.max() > 60 or hd.max() > 60 or hu.min() < 0 or hd.min() < 0):
        raise SystemExit('pack_weights: a hold outside 0-60 minutes')
    W[3] = f(v) + hu * 2.0 ** 12 + hd * 2.0 ** 29
    assert np.all(W < 2.0 ** 53)
    return W


def unpack(P: np.ndarray) -> dict:
    """The fields of packed per-(cell, day) sums P (5, ...): P[0] the count of entries, P[1:] the four weights.
    Returns float64 arrays: c6 (6, ...) the count per horizon (the count of entries at 1-60, of entries valid at 240),
    up and dn (6, ...) at H_SCAN, hU and hD (hold sums of the 60-minute grid)."""
    v = P[1:].astype(np.int64)
    up = np.stack([v[0] & M12, (v[0] >> 24) & M12, v[1] & M12, (v[1] >> 24) & M12, v[2] & M12, (v[2] >> 24) & M12]).astype(np.float64)
    dn = np.stack([(v[0] >> 12) & M12, (v[0] >> 36) & M12, (v[1] >> 12) & M12, (v[1] >> 36) & M12, (v[2] >> 12) & M12,
                   (v[2] >> 36) & M12]).astype(np.float64)
    n240 = (v[3] & M12).astype(np.float64)
    c6 = np.concatenate([np.broadcast_to(P[0], (5,) + P[0].shape), n240[None]])
    return {'c6': c6, 'up': up, 'dn': dn, 'hU': ((v[3] >> 12) & M17).astype(np.float64), 'hD': ((v[3] >> 29) & M17).astype(np.float64)}


def _bins(key: np.ndarray, W: np.ndarray, size: int) -> np.ndarray:
    """One count bincount and four weighted bincounts: (5, size)."""
    P = np.empty((5, size))
    P[0] = np.bincount(key, minlength=size)
    for w in range(4):
        P[w + 1] = np.bincount(key, W[w], minlength=size)
    return P


def reading_totals(C: np.ndarray, E: dict, W: np.ndarray, ND: int, Ls: list) -> tuple:
    """Per reading, the packed per-(level, day) sums over every entry, NA as level 0: (T (5, sum(L + 1), ND), offsets).
    The neutral-level shortcut reads the other reading's totals here."""
    off = np.r_[0, np.cumsum([L + 1 for L in Ls])].astype(np.int64)
    T = np.empty((5, int(off[-1]), ND))
    for j, L in enumerate(Ls):
        key = C[:, j].astype(np.intp) * ND + E['day']
        T[:, off[j]:off[j + 1]] = _bins(key, W, (L + 1) * ND).reshape(5, L + 1, ND)
    return T, off


def _neutral_info(levels: list, codes: np.ndarray) -> tuple:
    """(skip code, work count, non-neutral by code): the skip level is the reading's most common neutral level
    ('mid' of a zone reading, 'none' of a pattern); 0 when it has none (a sign reading is counted in full)."""
    L = len(levels)
    nonneu = np.r_[False, [lv not in heat.NEUTRAL for lv in levels]]
    neu = [i + 1 for i, lv in enumerate(levels) if lv in heat.NEUTRAL]
    cnt = np.bincount(codes, minlength=L + 1)
    if not neu:
        return 0, int(len(codes)), nonneu
    s = max(neu, key=lambda c: (cnt[c], -c))
    return int(s), int(len(codes) - cnt[s]), nonneu


def window_ids(ctx) -> np.ndarray:
    """int32 (entries, horizons): the H-minute clock window (row + 1) // H of each B entry (as the engine's wd), -1 for
    A entries and, at 240, for entries that are not valid rows of the 240 grid."""
    W = np.full((len(ctx.rows), len(H_SCAN)), -1, np.int32)
    b = ctx.split == 1
    for k, H in enumerate(H_SCAN):
        ok = b & ctx.v240 if H == 240 else b
        W[ok, k] = ((ctx.rows[ok] + 1) // H).astype(np.int32)
    return W


def make_ctx(m: dict, readings: list, asset: str = 'X', twin: int = 0, real: bool = None, lab: dict = None, g=None, lab240: dict = None,
             g240=None, log=print) -> Ctx:
    """The series context from minutes and readings: grids and labels (unless given), the copy merge on A entries,
    the entries, the code matrix, the packed weights, the reading totals, the bases and each reading's own effect."""
    assert heat.HORIZONS == H_MAIN and heat.HMAX == 60, 'make_ctx runs outside h240()'
    t0 = time.time()
    if lab is None:
        lab = heat.labels(m)
    if g is None:
        g = heat.Grid(m, lab)
    if lab240 is None or g240 is None:
        with h240():
            lab240 = heat.labels(m)
            g240 = heat.Grid(m, lab240)
    if g.sp['A'].N == 0 or g.sp['B'].N == 0:
        raise SystemExit(f'{asset}: a split has no valid minute')
    E = entry_rows(g, g240)
    readings = [dict(R) for R in readings]
    nA = int((E['split'] == 0).sum())
    readings, aliases = merge_aliases(readings, E['rows'][:nA], log=log)
    x = Ctx()
    x.asset, x.twin, x.label = asset, int(twin), asset if not twin else f'{asset}~twin{twin}'
    x.real = (not twin) if real is None else bool(real)
    x.m, x.lab, x.g, x.lab240, x.g240 = m, lab, g, lab240, g240
    x.readings, x.aliases = readings, aliases
    x.names = [R['name'] for R in readings]
    x.fam = [family_of(R) for R in readings]
    x.families = sorted(set(x.fam))
    x.byname = {}
    for i, R in enumerate(readings):
        x.byname[R['name']] = i
        for a in R.get('aliases', []):
            x.byname[a] = i
    x.rows, x.split, x.day, x.v240, x.dayref = E['rows'], E['split'], E['day'], E['v240'], E['dayref']
    x.base = _base_info(g, g240, x.dayref, 0)
    x.ND = int(max(x.base[1]['hi'], x.day.max() + 1))
    x.dsl = [slice(x.base[s]['lo'], x.base[s]['hi']) for s in (0, 1)]
    x.C = code_matrix(readings, x.rows)
    x.W = pack_weights(lab, lab240, E)
    x.Wt = np.ascontiguousarray(x.W.T)                               # (entries, 4) for the numba counting
    x.L = [len(R['levels']) for R in readings]
    x.skip, x.work, x.nonneu = [], [], []
    for j in range(len(readings)):
        s, w, nn = _neutral_info(readings[j]['levels'], x.C[:, j])
        x.skip.append(s)
        x.work.append(w)
        x.nonneu.append(nn)
    x.T, x.toff = reading_totals(x.C, E, x.W, x.ND, x.L)
    x.isB = x.split == 1
    x.nA = nA
    x.win = window_ids(x)
    x.parts = part_effects(x)
    x.prov = None
    x.lp = {}
    x.flags = []
    log(f'{x.label}: {len(readings)} readings ({len(aliases)} kept names carry aliases), {nA:,} A and {len(x.rows) - nA:,} B entries, '
        f'{x.ND} entry days ({time.time() - t0:.0f}s, peak {_rss_mb()} MB)')
    return x


def part_effects(ctx) -> dict:
    """Each reading's own state odds, t and n on A and B over all entries (per split, horizon and level): the parts of
    a cell. parts_hot and part_tmax read the A numbers."""
    out = {'odds': [], 't': [], 'n': []}
    for j in range(len(ctx.L)):
        P = ctx.T[:, ctx.toff[j] + 1:ctx.toff[j + 1], None, :]       # known levels only, as (5, L, 1, ND)
        st = _stats(P, ctx, lift=False)
        out['odds'].append(st['odds'][..., 0])                       # (2, 6, L)
        out['t'].append(st['t'][..., 0])
        out['n'].append(st['n'][..., 0])
    return out


# -------------------------------------------------------------------------------------------------------- the counts
def _lead_index(ctx, j: int, codes: np.ndarray, skip: int) -> np.ndarray:
    """Entries where reading j is off its skip level (NA included); the last few are cached (pairs come in order)."""
    cache = ctx.__dict__.setdefault('_icache', {})
    if j is not None and j in cache:
        return cache[j]
    idx = np.flatnonzero(codes != skip)
    if j is not None:
        if len(cache) >= 4:
            cache.pop(next(iter(cache)))
        cache[j] = idx
    return idx


def _col(ctx, j: int) -> dict:
    """A reading as a column spec for the kernel."""
    o = ctx.toff
    return {'id': j, 'codes': ctx.C[:, j], 'L': ctx.L[j], 'skip': ctx.skip[j], 'work': ctx.work[j], 'T': ctx.T[:, o[j]:o[j + 1]],
            'nonneu': ctx.nonneu[j], 'po': ctx.parts['odds'][j], 'pt': ctx.parts['t'][j]}


def pair_kernel(ctx, A: dict, B: dict, shortcut: bool = True) -> tuple:
    """Packed per-(cell, day) sums of two columns, P (5, La + 1, Lb + 1, ND) (code 0 = NA), and the counted entries.
    The lead is the column with fewer entries off its neutral level; only those entries (and its NA) are counted, and
    its neutral cells are the other column's per-day totals minus the counted cells (whole numbers: exact). Two
    columns without a neutral level (two sign readings) are counted in full. shortcut False: the naive full count."""
    ND = ctx.ND
    lead = None
    if shortcut:
        cand = [(c['work'], k, c) for k, c in ((0, A), (1, B)) if c['skip']]
        if cand:
            lead = min(cand, key=lambda x: (x[0], x[1]))[1]
    if lead is None:
        P = np.zeros((5, A['L'] + 1, B['L'] + 1, ND))
        _nb_count_all(A['codes'], B['codes'], ctx.day, ctx.Wt, P)
        return P, None
    Ld, Ot = (A, B) if lead == 0 else (B, A)
    idx = _lead_index(ctx, Ld['id'], Ld['codes'], Ld['skip'])
    P = np.zeros((5, Ld['L'] + 1, Ot['L'] + 1, ND))
    _nb_count(Ld['codes'], Ot['codes'], ctx.day, ctx.Wt, idx, P)
    P[:, Ld['skip']] = Ot['T'] - P.sum(1)                   # the lead's neutral cells (zero before this line)
    if lead == 1:
        P = np.ascontiguousarray(P.transpose(0, 2, 1, 3))
    return P, idx


def windows_B(cell: np.ndarray, rows: np.ndarray, H: int, ncell: int) -> np.ndarray:
    """Distinct H-minute clock windows ((row + 1) // H, as the engine's wd) that hold an entry of each cell: the bitwise
    OR of 1 << cell over each window, then a count per bit. rows ascending. More than 64 cells: np.unique."""
    if len(cell) == 0:
        return np.zeros(ncell, np.int64)
    w = (rows + 1) // H
    if ncell > 64:
        nw = int(w.max()) + 1
        u = np.unique(cell.astype(np.int64) * nw + w)
        return np.bincount(u // nw, minlength=ncell)[:ncell]
    st = np.r_[0, np.flatnonzero(np.diff(w)) + 1]
    orv = np.bitwise_or.reduceat(np.left_shift(np.uint64(1), cell.astype(np.uint64)), st)
    if ncell <= 16:
        return np.array([np.count_nonzero(orv & np.uint64(1 << c)) for c in range(ncell)], np.int64)
    bits = np.unpackbits(orv.view(np.uint8).reshape(-1, 8), axis=1, bitorder='little')
    return bits.sum(0, dtype=np.int64)[:ncell]


def clu_cells(S: np.ndarray, c: np.ndarray, beta: np.ndarray) -> tuple:
    """heat._clu vectorised over cells: S and c (6, ..., D) the per-day sums of the CENTRED sign (sign - base mean sign)
    and the per-day counts of each cell over every day of the split, beta (6, D) the base's per-day influence (bd / N).
    Returns (mu, se, G, deff, own) with own = (S - mu c) / n per day (for the lifts)."""
    sh = (6,) + (1,) * (S.ndim - 2) + (S.shape[-1],)
    n = c.sum(-1)
    G = (c > 0).sum(-1)
    with np.errstate(invalid='ignore', divide='ignore'):
        mu = S.sum(-1) / n
        own = (S - mu[..., None] * c) / n[..., None]
        psi = own - beta.reshape(sh)
        p2 = psi * psi
        q2, q4 = p2.sum(-1), (p2 * p2).sum(-1)
        se = np.sqrt(q2 * np.where(G > 1, G / np.maximum(G - 1, 1), np.nan))
        deff = np.minimum(np.where(q4 > 0, q2 * q2 / q4, G), G)
    return mu, se, G, deff, own


def _stats_np(F: dict, ctx, lift: bool = True) -> dict:
    """Per split (axis 0) and horizon (axis 1) for the cells of F (unpack's fields, cells on the axes between the
    horizon and the day): n, days, p_up, p_dn, msign, odds, t, se, deff, holds; with lift (cells on two axes a, b):
    the lift over a's level with b at any other known level (lift_a) and the same with a and b swapped (lift_b), each
    with its day-clustered t (the engine's lift algebra: the cell's per-day influence minus the rest's)."""
    c6, u6, d6 = F['c6'], F['up'], F['dn']
    shp = c6.shape[1:-1]
    out = {k: np.full((2, 6) + shp, np.nan) for k in ('n', 'days', 'p_up', 'p_dn', 'ms', 'odds', 't', 'se', 'deff', 'hold_up', 'hold_dn')}
    if lift:
        for k in ('lift_a', 't_lift_a', 'rest_a', 'lift_b', 't_lift_b', 'rest_b'):
            out[k] = np.full((2, 6) + shp, np.nan)
    ex = (slice(None),) + (None,) * len(shp)
    for s in (0, 1):
        b, sl = ctx.base[s], ctx.dsl[s]
        c, u, d = c6[..., sl], u6[..., sl], d6[..., sl]
        n = c.sum(-1)
        U, D = u.sum(-1), d.sum(-1)
        S = (u - d) - b['bms'][ex + (None,)] * c
        mu, se, G, deff, own = clu_cells(S, c, b['beta'])
        with np.errstate(invalid='ignore', divide='ignore'):
            out['n'][s], out['days'][s] = n, G
            out['p_up'][s], out['p_dn'][s] = U / n, D / n
            out['ms'][s] = (U - D) / n
            out['odds'][s] = 50.0 * mu
            out['se'][s], out['deff'][s] = se, deff
            out['t'][s] = np.where(se > 0, mu / se, 0.0)
            n0 = c[0].sum(-1)
            out['hold_up'][s] = np.broadcast_to(F['hU'][..., sl].sum(-1) / n0, n.shape)
            out['hold_dn'][s] = np.broadcast_to(F['hD'][..., sl].sum(-1) / n0, n.shape)
            if lift:
                fac = np.where(G > 1, G / np.maximum(G - 1, 1), np.nan)
                for ax, nm in ((-2, 'a'), (-3, 'b')):           # rest of a's row (b other) / of b's column (a other)
                    Sr = S.sum(ax, keepdims=True) - S
                    Cr = c.sum(ax, keepdims=True) - c
                    nr = Cr.sum(-1)
                    mur = Sr.sum(-1) / nr
                    oth = (Sr - mur[..., None] * Cr) / nr[..., None]
                    l2 = ((own - oth) ** 2).sum(-1)
                    sel = np.sqrt(l2 * fac)
                    out['lift_' + nm][s] = 50.0 * (mu - mur)
                    out['t_lift_' + nm][s] = np.where(sel > 0, (mu - mur) / sel, 0.0)
                    out['rest_' + nm][s] = nr
    return out


# ------------------------------------------------------------------------------------------------ numba kernels
# The hot loops of the scan, fused so that no (horizon, cell, day) temporary is built: the packed counting, the
# day-clustered statistics with both lifts, and the two fits. clu_cells / ipf / additive_fit (numpy) are the reference
# algebra; the tests check these against them and against heat._clu.
@nb.njit(cache=True)
def _nb_count(cl, co, day, Wt, idx, P):
    """P (5, Ll + 1, Lo + 1, ND) += the count and the four packed weights of the entries idx (all entries if idx is
    empty and full is wanted: the caller passes np.arange)."""
    for t in range(idx.shape[0]):
        e = idx[t]
        a, b, d = cl[e], co[e], day[e]
        P[0, a, b, d] += 1.0
        P[1, a, b, d] += Wt[e, 0]
        P[2, a, b, d] += Wt[e, 1]
        P[3, a, b, d] += Wt[e, 2]
        P[4, a, b, d] += Wt[e, 3]


@nb.njit(cache=True)
def _nb_count_all(cl, co, day, Wt, P):
    for e in range(cl.shape[0]):
        a, b, d = cl[e], co[e], day[e]
        P[0, a, b, d] += 1.0
        P[1, a, b, d] += Wt[e, 0]
        P[2, a, b, d] += Wt[e, 1]
        P[3, a, b, d] += Wt[e, 2]
        P[4, a, b, d] += Wt[e, 3]


@nb.njit(cache=True)
def _nb_windows(ca, cb, win, start, idx, use_idx, cmap, out):
    """Windows per day on B, fused: out[k, cell] += 1 the first time a cell holds an entry in a clock window of horizon k
    (win[e, k] = (row + 1) // H of a B entry, -1 where the entry does not count: A, or not valid at 240). Rows ascend, so
    'a window not seen yet for this cell' is 'a window other than the last one counted for it': the same count as
    windows_B's bitmask OR (and np.unique), for any number of cells. start: the first B entry (in idx when use_idx)."""
    nH, nc = out.shape[0], out.shape[1]
    last = np.full((nH, nc), -1, np.int64)
    n = idx.shape[0] if use_idx else ca.shape[0]
    for t in range(start, n):
        e = idx[t] if use_idx else t
        c = cmap[ca[e], cb[e]]
        if c < 0:
            continue
        for k in range(nH):
            w = win[e, k]
            if w >= 0:                                  # (false only at 240, near a gap)
                out[k, c] += last[k, c] != w            # branch-free: a new window adds one
                last[k, c] = w


@nb.njit(cache=True)
def _nb_field(P, h, a, b, dd):
    """(count, up, down) of horizon index h from packed sums P[:, a, b, dd]."""
    if h < 5:
        cnt = P[0, a, b, dd]
    else:
        cnt = float(np.int64(P[4, a, b, dd]) & 4095)
    v = np.int64(P[1 + h // 2, a, b, dd])
    if h % 2 == 0:
        return cnt, float(v & 4095), float((v >> 12) & 4095)
    return cnt, float((v >> 24) & 4095), float((v >> 36) & 4095)


@nb.njit(cache=True)
def _nb_stats(P, oa, ob, lo, hi, bms, beta, lift, out):
    """Per horizon and cell (a, b) of P[:, oa:, ob:] over the days lo..hi of one split: out[0..14] = n, up, down, days
    with an entry, the sum of the centred sign S, q2 and q4 of psi (heat._clu: psi_d = (S_d - mu c_d) / n - beta_d), and
    with lift: l2, mean and count of the rest of a's row (b at its other levels) and of b's column, then the hold sums."""
    La, Lb = P.shape[1] - oa, P.shape[2] - ob
    D = hi - lo
    Srow, Crow = np.zeros((La, D)), np.zeros((La, D))
    Scol, Ccol = np.zeros((Lb, D)), np.zeros((Lb, D))
    for a in range(La):
        for b in range(Lb):
            hu, hd = 0.0, 0.0
            for d in range(D):
                v = np.int64(P[4, oa + a, ob + b, lo + d])
                hu += float((v >> 12) & 131071)
                hd += float((v >> 29) & 131071)
            for h in range(6):
                out[13, h, a, b], out[14, h, a, b] = hu, hd
    for h in range(6):
        Srow[:], Crow[:], Scol[:], Ccol[:] = 0.0, 0.0, 0.0, 0.0
        bm = bms[h]
        for a in range(La):
            for b in range(Lb):
                n, U, Dn, G, Ss = 0.0, 0.0, 0.0, 0.0, 0.0
                for d in range(D):
                    cnt, u, dn = _nb_field(P, h, oa + a, ob + b, lo + d)
                    if cnt > 0:
                        S = u - dn - bm * cnt
                        n += cnt
                        U += u
                        Dn += dn
                        G += 1.0
                        Ss += S
                        if lift:
                            Srow[a, d] += S
                            Crow[a, d] += cnt
                            Scol[b, d] += S
                            Ccol[b, d] += cnt
                out[0, h, a, b], out[1, h, a, b], out[2, h, a, b], out[3, h, a, b], out[4, h, a, b] = n, U, Dn, G, Ss
        nrow, srow = np.zeros(La), np.zeros(La)
        ncol, scol = np.zeros(Lb), np.zeros(Lb)
        for a in range(La):
            for b in range(Lb):
                nrow[a] += out[0, h, a, b]
                srow[a] += out[4, h, a, b]
                ncol[b] += out[0, h, a, b]
                scol[b] += out[4, h, a, b]
        for a in range(La):
            for b in range(Lb):
                n = out[0, h, a, b]
                if n <= 0:
                    continue
                mu = out[4, h, a, b] / n
                nra, nrb = nrow[a] - n, ncol[b] - n
                mra = (srow[a] - out[4, h, a, b]) / nra if nra > 0 else 0.0
                mrb = (scol[b] - out[4, h, a, b]) / nrb if nrb > 0 else 0.0
                q2, q4, la2, lb2 = 0.0, 0.0, 0.0, 0.0
                for d in range(D):
                    cnt, u, dn = _nb_field(P, h, oa + a, ob + b, lo + d)
                    S = u - dn - bm * cnt
                    own = (S - mu * cnt) / n
                    psi = own - beta[h, d]
                    p2 = psi * psi
                    q2 += p2
                    q4 += p2 * p2
                    if lift:
                        if nra > 0:
                            x = own - ((Srow[a, d] - S) - mra * (Crow[a, d] - cnt)) / nra
                            la2 += x * x
                        if nrb > 0:
                            x = own - ((Scol[b, d] - S) - mrb * (Ccol[b, d] - cnt)) / nrb
                            lb2 += x * x
                out[5, h, a, b], out[6, h, a, b] = q2, q4
                out[7, h, a, b], out[8, h, a, b], out[9, h, a, b] = la2, mra, nra
                out[10, h, a, b], out[11, h, a, b], out[12, h, a, b] = lb2, mrb, nrb


@nb.njit(cache=True)
def _nb_ipf2(N, iters):
    """ipf's default model [ab][ay][by] on tables N (T, La, Lb, Y)."""
    T, La, Lb, Y = N.shape
    F = np.ones(N.shape)
    for t in range(T):
        for _ in range(iters):
            for a in range(La):
                for b in range(Lb):
                    tg, cur = 0.0, 0.0
                    for y in range(Y):
                        tg += N[t, a, b, y]
                        cur += F[t, a, b, y]
                    r = tg / cur if cur > 0 else 0.0
                    for y in range(Y):
                        F[t, a, b, y] *= r
            for a in range(La):
                for y in range(Y):
                    tg, cur = 0.0, 0.0
                    for b in range(Lb):
                        tg += N[t, a, b, y]
                        cur += F[t, a, b, y]
                    r = tg / cur if cur > 0 else 0.0
                    for b in range(Lb):
                        F[t, a, b, y] *= r
            for b in range(Lb):
                for y in range(Y):
                    tg, cur = 0.0, 0.0
                    for a in range(La):
                        tg += N[t, a, b, y]
                        cur += F[t, a, b, y]
                    r = tg / cur if cur > 0 else 0.0
                    for a in range(La):
                        F[t, a, b, y] *= r
    return F


@nb.njit(cache=True)
def _nb_additive(S, n, iters):
    """additive_fit on tables (T, La, Lb): backfitting of mean sign = mu + alpha_a + beta_b, weights n."""
    T, La, Lb = S.shape
    out = np.zeros(S.shape)
    for t in range(T):
        W, Sy = 0.0, 0.0
        for a in range(La):
            for b in range(Lb):
                W += n[t, a, b]
                Sy += S[t, a, b]
        mu = Sy / W if W > 0 else 0.0
        al, be = np.zeros(La), np.zeros(Lb)
        for _ in range(iters):
            for a in range(La):
                num, den = 0.0, 0.0
                for b in range(Lb):
                    w = n[t, a, b]
                    if w > 0:
                        num += S[t, a, b] - w * (mu + be[b])
                        den += w
                al[a] = num / den if den > 0 else 0.0
            for b in range(Lb):
                num, den = 0.0, 0.0
                for a in range(La):
                    w = n[t, a, b]
                    if w > 0:
                        num += S[t, a, b] - w * (mu + al[a])
                        den += w
                be[b] = num / den if den > 0 else 0.0
        for a in range(La):
            for b in range(Lb):
                out[t, a, b] = mu + al[a] + be[b]
    return out


def _stats(P: np.ndarray, ctx, lift: bool = True, oa: int = 0, ob: int = 0) -> dict:
    """Per split (axis 0) and horizon (axis 1) for the cells (a, b) of packed sums P[:, oa:, ob:] (5, La, Lb, ND): n,
    days, p_up, p_dn, ms (mean sign), odds = 50 x (mean sign - base mean sign), its day-clustered se, t and effective
    days (heat._clu's algebra), the holds of the 60-minute grid; with lift: the lift over a's level with b at any other
    known level (lift_a, its t and the rest's count) and the same with a and b swapped (lift_b). _stats_np is the same
    in numpy (the reference the tests compare with)."""
    P = np.ascontiguousarray(P, dtype=np.float64)
    La, Lb = P.shape[1] - oa, P.shape[2] - ob
    keys = ['n', 'days', 'p_up', 'p_dn', 'ms', 'odds', 't', 'se', 'deff', 'hold_up', 'hold_dn']
    if lift:
        keys += ['lift_a', 't_lift_a', 'rest_a', 'lift_b', 't_lift_b', 'rest_b']
    out = {k: np.full((2, 6, La, Lb), np.nan) for k in keys}
    for s in (0, 1):
        b = ctx.base[s]
        R = np.zeros((15, 6, La, Lb))
        _nb_stats(P, oa, ob, int(b['lo']), int(b['hi']), np.ascontiguousarray(b['bms']), np.ascontiguousarray(b['beta']), bool(lift), R)
        n, U, D, G, Ss, q2, q4 = R[:7]
        with np.errstate(invalid='ignore', divide='ignore'):
            mu = Ss / n
            fac = np.where(G > 1, G / np.maximum(G - 1, 1), np.nan)
            se = np.sqrt(q2 * fac)
            out['n'][s], out['days'][s] = n, G
            out['p_up'][s], out['p_dn'][s], out['ms'][s] = U / n, D / n, (U - D) / n
            out['odds'][s], out['se'][s] = 50.0 * mu, se
            out['t'][s] = np.where(se > 0, mu / se, 0.0)
            out['deff'][s] = np.minimum(np.where(q4 > 0, q2 * q2 / q4, G), G)
            n0 = n[0]
            out['hold_up'][s], out['hold_dn'][s] = R[13] / n0, R[14] / n0
            if lift:
                for nm, (l2, mr, nr) in (('a', R[7:10]), ('b', R[10:13])):
                    sel = np.sqrt(l2 * fac)
                    ok = nr > 0
                    out['lift_' + nm][s] = np.where(ok, 50.0 * (mu - mr), np.nan)
                    out['t_lift_' + nm][s] = np.where(ok & (sel > 0), (mu - mr) / sel, np.where(ok, 0.0, np.nan))
                    out['rest_' + nm][s] = np.where(ok, nr, np.nan)
    return out


def _ratio(a, b):
    return np.divide(a, b, out=np.zeros(np.broadcast_shapes(a.shape, b.shape)), where=b > 0)


def ipf(N: np.ndarray, iters: int = IPF_ITERS, margins=None) -> np.ndarray:
    """The log-linear model fitted by iterative proportional fitting on tables N (..., table axes). margins: the
    margins the model keeps, each a tuple of table axes counted from the end. Default, for (..., La, Lb, 3):
    [ab][ay][by] = each reading shifts the outcome on its own and the two readings may go together, with no joint
    term. Starts from ones; a zero margin stays zero."""
    if margins is None:
        margins = [(-3, -2), (-3, -1), (-2, -1)]
    nd = N.ndim
    T = max(-a for mg in margins for a in mg)                   # the number of table axes
    targets = []
    for mg in margins:
        keep = {nd + a for a in mg}
        drop = tuple(a for a in range(nd - T, nd) if a not in keep)
        targets.append((drop, N.sum(drop, keepdims=True)))
    F = np.ones(N.shape)
    for _ in range(iters):
        for drop, tg in targets:
            F *= _ratio(tg, F.sum(drop, keepdims=True))
    return F


def additive_fit(S: np.ndarray, n: np.ndarray, iters: int = IPF_ITERS) -> np.ndarray:
    """(review) The mean sign as a main effect of a's level plus one of b's level, weighted least squares (weights n,
    the entries of each cell) by backfitting: tables (..., La, Lb) of sign sums S and counts n. Returns the fitted mean
    sign of every cell."""
    w = np.asarray(n, np.float64)
    y = _ratio(S, w)
    W = w.sum((-2, -1), keepdims=True)
    mu = _ratio((w * y).sum((-2, -1), keepdims=True), W)
    a = np.zeros(w.shape[:-1] + (1,))
    b = np.zeros(w.shape[:-2] + (1, w.shape[-1]))
    wa, wb = w.sum(-1, keepdims=True), w.sum(-2, keepdims=True)
    for _ in range(iters):
        a = _ratio((w * (y - mu - b)).sum(-1, keepdims=True), wa)
        b = _ratio((w * (y - mu - a)).sum(-2, keepdims=True), wb)
    return mu + a + b


def _fitted_ms(F: np.ndarray) -> np.ndarray:
    with np.errstate(invalid='ignore', divide='ignore'):
        return (F[..., 0] - F[..., 2]) / F.sum(-1)


def robust_iota(i1, i2):
    """iota_robust: the one of the two interaction measures nearer zero when they share a sign, else 0."""
    same = (np.sign(i1) == np.sign(i2)) & np.isfinite(i1) & np.isfinite(i2)
    return np.where(same, np.where(np.abs(i1) <= np.abs(i2), i1, i2), 0.0)


def _thin(lift: np.ndarray, rest: np.ndarray) -> np.ndarray:
    """A lift against fewer than MIN_EVENTS other entries is not measured (NaN): a cell that holds almost all of its
    part's entries is the part itself, and its lift against a handful is +-50 points with a meaningless t. The cell
    keeps its row; lift_min then takes the other part's lift (the pair pack's rest_n >= MIN_EVENTS, as a measure)."""
    return np.where(np.nan_to_num(rest) >= heat.MIN_EVENTS, lift, np.nan)


def cell_stats(P: np.ndarray, ctx, A: dict, B: dict) -> dict:
    """Per cell (known a level x known b level), split and horizon: the STATS arrays (2, 6, La, Lb) (wd is filled by the
    caller on B), plus n and days, and assoc (Cramér's V of the two readings on A)."""
    st = _stats(P, ctx, lift=True, oa=1, ob=1)
    La, Lb = P.shape[1] - 1, P.shape[2] - 1
    out = {k: np.full((2, 6, La, Lb), np.nan) for k in STATS}
    for k in ('odds', 't', 'se', 'deff', 'p_up', 'p_dn', 'hold_up', 'hold_dn'):
        out[k] = st[k]
    n = np.nan_to_num(st['n'])
    U, D = np.nan_to_num(st['p_up'] * n), np.nan_to_num(st['p_dn'] * n)
    N = np.stack([U, n - U - D, D], -1)                                   # (2, 6, La, Lb, 3): up, flat, down
    ms = st['ms']
    with np.errstate(invalid='ignore', divide='ignore'):
        fit = _fitted_ms(_nb_ipf2(N.reshape(12, La, Lb, 3), IPF_ITERS).reshape(N.shape))
        add = _nb_additive((U - D).reshape(12, La, Lb), n.reshape(12, La, Lb), IPF_ITERS).reshape(n.shape)
        bms = np.stack([ctx.base[s]['bms'] for s in (0, 1)])[:, :, None, None]
        out['iota'] = 50.0 * (ms - fit)
        out['iota_add'] = 50.0 * (ms - add)
        out['iota_robust'] = robust_iota(out['iota'], out['iota_add'])
        se = st['se']
        out['t_iota'] = np.where(se > 0, (ms - fit) / se, 0.0)
        out['t_iota_add'] = np.where(se > 0, (ms - add) / se, 0.0)
        out['t_robust'] = np.where(se > 0, out['iota_robust'] / (50.0 * se), 0.0)
        out['odds_fit'] = 50.0 * (fit - bms)
        out['iota_naive'] = st['odds'] - A['po'][:, :, :, None] - B['po'][:, :, None, :]
        d = np.sign(np.nan_to_num(st['odds'][0]))[None]                   # the cell's direction on A
        la, lb = _thin(st['lift_a'], st['rest_a']), _thin(st['lift_b'], st['rest_b'])
        fa, fb = np.isfinite(la), np.isfinite(lb)
        use_a = fa & (~fb | np.where(d != 0, d * la <= d * lb, np.abs(la) <= np.abs(lb)))
        out['lift_min'] = np.where(use_a, la, lb)                         # NaN when neither part has a rest
        out['t_lift'] = np.where(use_a, st['t_lift_a'], np.where(fb, st['t_lift_b'], np.nan))
        out['rest_n'] = np.where(use_a, st['rest_a'], np.where(fb, st['rest_b'], np.fmax(st['rest_a'], st['rest_b'])))
    out['n'], out['days'] = n.astype(np.int64), np.nan_to_num(st['days']).astype(np.int64)
    # Cramér's V of the two readings on A (counts of the entries where both are known)
    O = n[0, 0]
    tot = O.sum()
    r_, c_ = O.sum(1), O.sum(0)
    k = min(int((r_ > 0).sum()), int((c_ > 0).sum()))
    if tot > 0 and k > 1:
        Ex = np.outer(r_, c_) / tot
        with np.errstate(invalid='ignore', divide='ignore'):
            chi = float(np.nansum(np.where(Ex > 0, (O - Ex) ** 2 / Ex, 0.0)))
        out['assoc'] = math.sqrt(chi / (tot * (k - 1)))
    else:
        out['assoc'] = 0.0
    return out


def measure_cross(ctx, A: dict, B: dict, shortcut: bool = True) -> dict:
    """One pair (or a flag and a reading): kernel, statistics, fits, windows per day. Returns the confluence cells
    (both levels known and not neutral) that hold an entry: ka, kb (0-based levels), stats (ncell, 2, 6, K), n and
    days (ncell, 2, 6), assoc."""
    P, idx = pair_kernel(ctx, A, B, shortcut)
    conf = np.outer(A['nonneu'], B['nonneu'])                            # by code (0 = NA)
    ka, kb = np.nonzero(conf[1:, 1:])
    st = cell_stats(P, ctx, A, B)
    nn = st['n'][:, 0, ka, kb].sum(0)
    keep = nn > 0
    ka, kb = ka[keep], kb[keep]
    out = {'ka': ka, 'kb': kb, 'assoc': st['assoc']}
    S = np.stack([st[k][:, :, ka, kb] for k in STATS], -1)               # (2, 6, ncell, K)
    out['n'] = st['n'][:, :, ka, kb].transpose(2, 0, 1)
    out['days'] = st['days'][:, :, ka, kb].transpose(2, 0, 1)
    if len(ka):
        cmap = np.full((A['L'] + 1, B['L'] + 1), -1, np.int64)
        cmap[ka + 1, kb + 1] = np.arange(len(ka))
        wc = np.zeros((len(H_SCAN), len(ka)))
        if idx is None:
            _nb_windows(A['codes'], B['codes'], ctx.win, ctx.nA, ctx.rows[:0], False, cmap, wc)
        else:
            _nb_windows(A['codes'], B['codes'], ctx.win, int(np.searchsorted(idx, ctx.nA)), idx, True, cmap, wc)
        S[1, :, :, SI['wd']] = wc / ctx.base[1]['ndays'][:, None]
    out['st'] = S.transpose(2, 0, 1, 3)
    return out


# ---------------------------------------------------------------------------------------------------- the cell table
def _sample(n: np.ndarray, days: np.ndarray) -> np.ndarray:
    """(ncell, 6): the engine's sample floors on both splits (30 entries on 30 days of A, 30 on 20 days of B)."""
    return (n[:, 0] >= heat.MIN_EVENTS) & (days[:, 0] >= heat.MIN_DAYS_A) & (n[:, 1] >= heat.MIN_EVENTS) & (days[:, 1] >= heat.MIN_DAYS_B)


def derive(B: dict) -> dict:
    """Signing and heat for a block of cells (ncell, ...): d = the sign of the cell's odds on A, d_iota = the sign of
    iota_robust on A (0: the cell has no interaction direction and its iheat_B is 0), iota_with_call, the B heats
      oheat_B = wd_B x odds_B . d          iheat_B = wd_B x iota_robust_B . d_iota
      lheat_B = min(wd_B, rest_wd_B) x lift_min_B . d,   rest_wd_B = wd_B x rest_n_B / n_B (the pair pack's rule)
    and the sample mask."""
    S = B['st']
    g = lambda k, s: S[:, s, :, SI[k]]
    d = np.sign(np.nan_to_num(g('odds', 0)))
    di = np.sign(np.nan_to_num(g('iota_robust', 0)))
    wd = np.nan_to_num(g('wd', 1))
    with np.errstate(invalid='ignore', divide='ignore'):
        rest_wd = wd * np.nan_to_num(g('rest_n', 1)) / B['n'][:, 1]
        out = {'d': d, 'di': di, 'with_call': (di == d) & (di != 0), 'ok': _sample(B['n'], B['days']),
               'oheat': wd * np.nan_to_num(g('odds', 1)) * d, 'iheat': wd * np.nan_to_num(g('iota_robust', 1)) * di,
               'rest_wd': np.nan_to_num(rest_wd), 'lheat': np.minimum(wd, np.nan_to_num(rest_wd)) * np.nan_to_num(g('lift_min', 1)) * d}
    return out


class SummaryCounts:
    """Mergeable counts per horizon and stratum (exact integer sums: batches, workers and --part jobs add up).
    Strata: all; part_tmax under 2 / 2-3 / 3 and over; provenance none / stored / pack; each family pair. Per stratum:
    confluence cells with a sample and under the floor, kept direction, kept lift (cells with a lift on A), kept interaction (iota, iota_add,
    iota_robust: the B sign equals the A sign, a B value of exactly 0 counts as not kept), t_B >= 2 in the A direction
    of iota and iota_robust, iota_robust with the call, and the persistence curve (kept interaction by A |t| bin).
    For the first 7 strata also: heat histograms (signed log bins) with the exact top 1,000 values of 'all' and
    'prov:none', and log-binned histograms of the one-sided B p (odds, iota_robust, lift) for BHY."""
    COUNTS = ['cells', 'under_floor', 'dir_n', 'dir_kept', 'lift_n', 'lift_kept', 'iota_n', 'iota_kept', 'iota_add_n', 'iota_add_kept',
              'robust_n', 'robust_kept', 't_iota_B2', 't_robust_B2', 'robust_with_call']
    PKINDS = ['iota', 'iota_add', 'robust']
    HEAT_EDGES = np.r_[-np.logspace(5, -4, 181), np.logspace(-4, 5, 181)]      # |heat| 1e-4 .. 1e5, 20 bins a decade, each side
    P_EDGES = np.linspace(-12.0, 0.0, 241)                                       # log10 p, 0.05 a bin (bin 0: below 1e-12)
    TOPN = 1000

    def __init__(self, families: list):
        fp = [f'{a}|{b}' for i, a in enumerate(families) for b in families[i:]]
        self.strata = ['all', 'ptmax<2', 'ptmax2-3', 'ptmax>=3', 'prov:none', 'prov:stored', 'prov:pack'] + ['fam:' + x for x in fp]
        self.fam_index = {x: 7 + i for i, x in enumerate(fp)}
        nS, nH = len(self.strata), len(H_SCAN)
        self.c = np.zeros((nH, nS, len(self.COUNTS)), np.int64)
        self.persist = np.zeros((nH, nS, len(self.PKINDS), len(T_BINS) + 1, 2), np.int64)
        self.heat = np.zeros((nH, 7, len(MEASURES), len(self.HEAT_EDGES) + 1), np.int64)
        self.p = np.zeros((nH, 7, 3, len(self.P_EDGES) + 1), np.int64)
        self.top = {(h, m, s): np.zeros(0) for h in range(nH) for m in MEASURES for s in ('all', 'prov:none')}

    def fam_id(self, fa: str, fb: str) -> int:
        a, b = sorted((fa, fb))
        return self.fam_index.get(f'{a}|{b}', -1)

    def add(self, B: dict, Dv: dict) -> None:
        """B: a block of cells (st, n, days, prov, fam, ptmax (ncell, 6)); Dv: derive(B)."""
        from scipy.stats import t as tdist
        nS = len(self.strata)
        S = B['st']
        for hi_ in range(len(H_SCAN)):
            ok = Dv['ok'][:, hi_]
            anyn = (B['n'][:, 0, hi_] + B['n'][:, 1, hi_]) > 0
            ptb = np.digitize(np.nan_to_num(B['ptmax'][:, hi_]), PT_BINS)
            sid = np.stack([np.zeros(len(ok), np.int64), 1 + ptb, 4 + B['prov'].astype(np.int64), B['fam'].astype(np.int64)], 1)

            def cnt(mask, col):
                s = sid[mask].ravel()
                self.c[hi_, :, col] += np.bincount(s[s >= 0], minlength=nS)[:nS]
            g = lambda k, s: S[:, s, hi_, SI[k]]
            d, di = Dv['d'][:, hi_], Dv['di'][:, hi_]
            cnt(ok, 0)
            cnt(anyn & ~ok, 1)
            sgn = lambda k, s: np.sign(np.nan_to_num(g(k, s)))
            m = ok & (d != 0)
            cnt(m, 2)
            cnt(m & (sgn('odds', 1) == d), 3)
            ml = m & np.isfinite(g('lift_min', 0))                       # a lift with a rest on A (_thin)
            cnt(ml, 4)
            cnt(ml & (sgn('lift_min', 1) == d), 5)
            for kk, (k, tk) in enumerate((('iota', 't_iota'), ('iota_add', 't_iota_add'), ('iota_robust', 't_robust'))):
                sa = sgn(k, 0)
                mk = ok & (sa != 0)
                kept = mk & (sgn(k, 1) == sa)
                cnt(mk, 6 + 2 * kk)
                cnt(kept, 7 + 2 * kk)
                tb = np.digitize(np.abs(np.nan_to_num(g(tk, 0))), T_BINS)
                for col, mm in ((0, mk), (1, kept)):
                    s = sid[mm]
                    tt = np.repeat(tb[mm], 4)
                    s = s.ravel()
                    v = s >= 0
                    np.add.at(self.persist[hi_, :, kk, :, col], (s[v], tt[v]), 1)
            cnt(ok & (sgn('iota', 0) != 0) & (np.nan_to_num(g('t_iota', 1)) * sgn('iota', 0) >= 2), 12)
            cnt(ok & (di != 0) & (np.nan_to_num(g('t_robust', 1)) * di >= 2), 13)
            cnt(ok & (di != 0) & Dv['with_call'][:, hi_], 14)
            # histograms over the first 7 strata
            s7 = sid[ok][:, :3].ravel()
            for mi, me in enumerate(MEASURES):
                v = Dv[me][ok, hi_]
                b = np.searchsorted(self.HEAT_EDGES, v, side='right')
                np.add.at(self.heat[hi_, :, mi], (s7, np.repeat(b, 3)), 1)
                for nm, msk in (('all', np.ones(len(v), bool)), ('prov:none', B['prov'][ok] == 0)):
                    k = (hi_, me, nm)
                    x = np.r_[self.top[k], v[msk]]
                    self.top[k] = -np.sort(-x)[:self.TOPN] if len(x) > self.TOPN else -np.sort(-x)
            df = np.maximum(np.floor(np.nan_to_num(g('deff', 1))) - 1, 1)
            for pi, (tk, dd) in enumerate((('t', d), ('t_robust', di), ('t_lift', d))):
                t = g(tk, 1) * dd
                p = np.where((dd != 0) & np.isfinite(t), tdist.sf(np.nan_to_num(t), df), 1.0)[ok]     # no measure: p = 1
                lp = np.log10(np.maximum(p, 1e-300))
                b = np.searchsorted(self.P_EDGES, lp, side='left')
                np.add.at(self.p[hi_, :, pi], (s7, np.repeat(b, 3)), 1)

    def merge(self, o: 'SummaryCounts') -> 'SummaryCounts':
        if o.strata != self.strata:
            raise SystemExit('SummaryCounts.merge: the strata differ (another family set)')
        self.c += o.c
        self.persist += o.persist
        self.heat += o.heat
        self.p += o.p
        for k in self.top:
            x = np.r_[self.top[k], o.top[k]]
            self.top[k] = -np.sort(-x)[:self.TOPN]
        return self

    def to_json(self) -> dict:
        r6 = lambda a: [round(float(x), 6) for x in a]
        return {'horizons': H_SCAN, 'strata': self.strata, 'counts': self.COUNTS, 'persist_kinds': self.PKINDS, 't_bins': T_BINS,
                'heat_edges': r6(self.HEAT_EDGES), 'p_edges_log10': r6(self.P_EDGES), 'p_kinds': ['odds', 'iota_robust', 'lift'],
                'c': self.c.tolist(), 'persist': self.persist.tolist(), 'heat': self.heat.tolist(), 'p': self.p.tolist(),
                'top': {f'{H_SCAN[h]}|{m}|{s}': r6(v) for (h, m, s), v in self.top.items()}}

    @classmethod
    def from_json(cls, j: dict) -> 'SummaryCounts':
        fams = sorted({x for s in j['strata'] if s.startswith('fam:') for x in s[4:].split('|')})
        o = cls(fams)
        if o.strata != j['strata']:
            raise SystemExit('SummaryCounts.from_json: strata do not rebuild')
        o.c, o.persist = np.array(j['c'], np.int64), np.array(j['persist'], np.int64)
        o.heat, o.p = np.array(j['heat'], np.int64), np.array(j['p'], np.int64)
        for k, v in j['top'].items():
            h, me, s = k.split('|')
            o.top[(H_SCAN.index(int(h)), me, s)] = np.array(v, float)
        return o

    def quantile(self, h: int, measure: str, q: float, stratum: str = 'all') -> float:
        """A quantile of a heat from its histogram (bin upper edge), exact from the top values where they reach."""
        hi_, si = H_SCAN.index(h), self.strata.index(stratum)
        hist = self.heat[hi_, si, MEASURES.index(measure)]
        n = int(hist.sum())
        if n == 0:
            return float('nan')
        k = int(math.ceil((1 - q) * n))                  # the k-th largest
        top = self.top.get((hi_, measure, stratum))
        if top is not None and 0 < k <= len(top):
            return float(top[k - 1])
        cum = np.cumsum(hist[::-1])
        b = len(hist) - 1 - int(np.searchsorted(cum, k))
        e = self.HEAT_EDGES
        return float(e[min(b, len(e) - 1)])


def _sig6(x) -> np.ndarray:
    """x rounded to 6 significant digits, the precision the CSVs write ('%.6g'): each result is the double nearest a
    6-digit decimal, so it writes and reads back unchanged. Every pooled list ranks on these values (ties by key), so a
    list merged from --part files sorts exactly as the one-job list."""
    x = np.asarray(x, np.float64)
    out = x.copy()
    f = np.isfinite(x) & (x != 0) & (np.abs(x) >= 1e-15) & (np.abs(x) < 1e21)
    a = np.abs(x[f])
    e = np.floor(np.log10(a)).astype(np.int64)
    e = np.where(a >= 10.0 ** (e + 1), e + 1, np.where(a < 10.0 ** e, e - 1, e))      # log10 off by one at a power of ten
    k = 5 - e                                                            # decimals kept (negative: tens, hundreds, ...)
    up, dn = 10.0 ** np.maximum(k, 0), 10.0 ** np.maximum(-k, 0)        # exact powers of ten (|k| <= 20)
    out[f] = np.where(k >= 0, np.round(x[f] * up) / up, np.round(x[f] / dn) * dn)
    odd = np.isfinite(x) & (x != 0) & ~f
    out[odd] = [float('%.6g' % v) for v in x[odd]]
    return out


class Candidates:
    """The top CAND_POOL rows per (kind, horizon, measure) by the B heat (ties by key), merged batch by batch."""

    def __init__(self, k: int = CAND_POOL):
        self.k, self.df = k, None

    def add(self, df: pd.DataFrame) -> None:
        if df is None or not len(df):
            return
        self.df = df if self.df is None else pd.concat([self.df, df], ignore_index=True)
        self.df = (self.df.sort_values(['kind', 'h', 'measure', 'value', 'key'], ascending=[True, True, True, False, True])
                   .groupby(['kind', 'h', 'measure'], sort=False).head(self.k).reset_index(drop=True))

    def frame(self) -> pd.DataFrame:
        return pd.DataFrame() if self.df is None else self.df


class ShardWriter:
    """Streams the cells with a sample on both splits (at any horizon) to <dir>/<prefix>_NNNNN.npz, one file per batch:
    int32 n and days (cell, split, horizon), int32 rest_n, float16 SHARD_STATS, the reading and level ids, the
    provenance and the family pair. No list of all cells is held in memory. Real coins only (review): on a twin it
    writes nothing and everything else runs the same."""

    def __init__(self, out_dir: str, enabled: bool):
        self.dir, self.enabled = out_dir, bool(enabled and out_dir)
        if self.enabled:
            os.makedirs(out_dir, exist_ok=True)

    def write(self, prefix: str, bid: int, B: dict, Dv: dict) -> int:
        if not self.enabled:
            return 0
        keep = Dv['ok'].any(1)
        if not keep.any():
            return 0
        si = [SI[k] for k in SHARD_STATS]
        p = os.path.join(self.dir, f'{prefix}_{bid:05d}.npz')
        np.savez(p, kind=B['kind'][keep], obj=B['obj'][keep], ia=B['ia'][keep], la=B['la'][keep], ib=B['ib'][keep], lb=B['lb'][keep],
                 prov=B['prov'][keep], fam=B['fam'][keep], n=B['n'][keep].astype(np.int32), days=B['days'][keep].astype(np.int16),
                 rest_n=np.nan_to_num(B['st'][keep][..., SI['rest_n']]).astype(np.int32),
                 stats=B['st'][keep][..., si].astype(np.float16), stat_names=np.array(SHARD_STATS), horizons=np.array(H_SCAN))
        return os.path.getsize(p)


# ----------------------------------------------------------------------------------------------------- provenance
def load_hm1(packs=(), pairs: str = '') -> dict:
    """(review) What the bot already has, by reading names: {'levels': {reading: {state levels}}} of every part in a pack
    the bot loads (traded, pair, clock, perp, perp pair; their aliases included), and {'stored': {frozenset of two
    readings}} stored together as an HM1 relationship (the pairs file of run 43030435253). An event label maps to its
    state level ('low (falling in)' -> 'low'). direction_all is not used: it lists every level."""
    lv, stored = {}, set()

    def put(key):
        if '=' not in key:
            return
        r, level = key.rsplit('=', 1)
        lv.setdefault(r, set()).add(EVENT_SUFFIX.sub('', level))
    for p in packs or ():
        if not p or not os.path.isfile(p):
            continue
        with open(p) as f:
            pk = json.load(f)
        for row in pk.get('rows', []):
            keys = [row.get('key', '')] + list(row.get('aliases', []))
            if 'when' in row:
                keys.append(row['when'])
                keys += [f'{c}={v}' for c, v in row.get('conds', [])]
            for k in keys:
                for part in str(k).split(' | '):
                    put(part)
    if pairs and os.path.isfile(pairs):
        df = pd.read_csv(pairs, usecols=lambda c: c in ('trig', 'cond'), low_memory=False)
        for trig, cond in df.drop_duplicates().itertuples(index=False):
            rs = [x.rsplit('=', 1)[0] for x in str(trig).split(' | ')] + [str(cond)]
            for i in range(len(rs)):
                for j in range(i + 1, len(rs)):
                    if rs[i] != rs[j]:
                        stored.add(frozenset((rs[i], rs[j])))
    return {'levels': lv, 'stored': stored}


def provenance(ctx, hm1: dict) -> dict:
    """Per reading, a bool by level: the level (or an alias's) is in a pack the bot loads; and the reading pairs stored
    in HM1, by reading index. A cell is 'pack' when either part's level is in a pack, 'stored' when its two readings
    were stored together, 'none' otherwise. Labels go by names, so a twin's cells get the coin's labels."""
    inpack = []
    for R in ctx.readings:
        names = [R['name']] + list(R.get('aliases', []))
        have = set().union(*[hm1['levels'].get(n, set()) for n in names])
        inpack.append(np.array([lv in have for lv in R['levels']], bool))
    stored = set()
    if hm1['stored']:
        idx = {}
        for i, R in enumerate(ctx.readings):
            for n in [R['name']] + list(R.get('aliases', [])):
                idx.setdefault(n, set()).add(i)
        for fs in hm1['stored']:
            a, b = tuple(fs)
            for i in idx.get(a, ()):
                for j in idx.get(b, ()):
                    if i != j:
                        stored.add((min(i, j), max(i, j)))
    return {'inpack': inpack, 'stored': stored}


def _prov_cells(ctx, ia: int, ib: int, ka: np.ndarray, kb: np.ndarray, extra=()) -> np.ndarray:
    pv = ctx.prov
    if pv is None:
        return np.zeros(len(ka), np.int8)
    pk = np.zeros(len(ka), bool)
    if ia >= 0:
        pk |= pv['inpack'][ia][ka]
    if ib >= 0:
        pk |= pv['inpack'][ib][kb]
    for (r, lv) in extra:
        pk |= bool(pv['inpack'][r][lv])
    rs = [r for r in [ia, ib] + [r for r, _ in extra] if r >= 0]
    st = any((min(a, b), max(a, b)) in pv['stored'] for i, a in enumerate(rs) for b in rs[i + 1:])
    return np.where(pk, 2, 1 if st else 0).astype(np.int8)


# ---------------------------------------------------------------------------------------------------------- the scan
def pair_list(ctx, part=(0, 1), max_pairs: int = None, seed: int = 0) -> np.ndarray:
    """Every pair of readings with a different base, in a fixed order ((i, j), i < j, by reading index), as int64
    (pair index, i, j). --part i/S keeps pair index % S == i. max_pairs (the bench): a seeded random subset."""
    R = len(ctx.readings)
    bases = np.array([str(r['base']) for r in ctx.readings], object)
    ii, jj = np.triu_indices(R, 1)
    keep = bases[ii] != bases[jj]
    ii, jj = ii[keep], jj[keep]
    pid = np.arange(len(ii), dtype=np.int64)
    i, S = part
    sel = pid % S == i
    out = np.stack([pid[sel], ii[sel], jj[sel]], 1)
    if max_pairs is not None and len(out) > max_pairs:
        out = out[np.sort(np.random.default_rng([20261111, seed]).choice(len(out), max_pairs, replace=False))]
    return out


def _empty_block() -> dict:
    return {k: [] for k in ('kind', 'obj', 'ia', 'la', 'ib', 'lb', 'st', 'n', 'days', 'prov', 'fam', 'ptmax', 'phot', 'assoc', 'lp')}


def _append(Bk: dict, kind: int, obj: int, ia: int, ib: int, r: dict, prov: np.ndarray, fam: int, pts: list, lp: np.ndarray,
            la: np.ndarray = None) -> None:
    """Add the cells of one cross to a batch block. pts: the parts' own |t| on A at each cell's levels, one (6, ncell)
    array per part (part_tmax is their max, parts_hot the count at 3 or more)."""
    k = len(r['ka'])
    if not k:
        return
    Bk['kind'].append(np.full(k, kind, np.int8))
    Bk['obj'].append(np.full(k, obj, np.int64))
    Bk['ia'].append(np.full(k, ia, np.int32))
    Bk['ib'].append(np.full(k, ib, np.int32))
    Bk['la'].append((r['ka'] if la is None else la).astype(np.int16))
    Bk['lb'].append(r['kb'].astype(np.int16))
    Bk['st'].append(r['st'])
    Bk['n'].append(r['n'])
    Bk['days'].append(r['days'])
    Bk['prov'].append(prov.astype(np.int8))
    Bk['fam'].append(np.full(k, fam, np.int16))
    P = np.stack(pts)                                                     # (parts, 6, ncell)
    Bk['ptmax'].append(P.max(0).T)
    Bk['phot'].append((P >= 3).sum(0).astype(np.int8).T)
    Bk['assoc'].append(np.full(k, r['assoc']))
    Bk['lp'].append(lp)


def _close(Bk: dict) -> dict:
    if not Bk['kind']:
        return None
    return {k: np.concatenate(v) for k, v in Bk.items()}


def _lp_cells(ctx, ia: int, ib: int, ka: np.ndarray, kb: np.ndarray) -> np.ndarray:
    """learner_path: a learner rule (two readings, or two of a rule's three) holds the cell's two levels."""
    rules = ctx.lp.get((min(ia, ib), max(ia, ib)))
    out = np.zeros(len(ka), bool)
    if not rules:
        return out
    for ra, sa, rb, sb in rules:
        x, y = (ka, kb) if ra == ia else (kb, ka)
        out |= np.isin(x, list(sa)) & np.isin(y, list(sb))
    return out


def _thr():
    """The shared thresholds (fork-inherited shared memory): per (kind, horizon, measure) the CAND_POOL-th best B heat
    the parent holds so far, and the TRIPLE_POOL-th best A score. A worker returns only cells above them, which keeps the
    merge exact (the thresholds only rise) and the traffic small."""
    import multiprocessing as mp
    a = mp.RawArray('d', 2 * len(H_SCAN) * len(MEASURES) + 1)
    v = np.frombuffer(a, np.float64)
    v[:] = -np.inf
    return a


def _thr_view() -> np.ndarray:
    return np.frombuffer(heat._W['hm2_thr'], np.float64)


def _pair_batch(job):
    """One batch of pairs in a worker: every pair's confluence cells, then the batch's summary counts, candidates,
    triple-choice pool and shard."""
    bid, lo, hi = job
    ctx = heat._W['hm2']
    pairs = heat._W['hm2_pairs'][lo:hi]
    proto = heat._W['hm2_summ_proto']
    t0 = time.time()
    Bk = _empty_block()
    for pid, ia, ib in pairs:
        ia, ib = int(ia), int(ib)
        A, B = _col(ctx, ia), _col(ctx, ib)
        r = measure_cross(ctx, A, B)
        if not len(r['ka']):
            continue
        pts = [np.abs(np.nan_to_num(ctx.parts['t'][ia][0][:, r['ka']])), np.abs(np.nan_to_num(ctx.parts['t'][ib][0][:, r['kb']]))]
        _append(Bk, 0, int(pid), ia, ib, r, _prov_cells(ctx, ia, ib, r['ka'], r['kb']), proto.fam_id(ctx.fam[ia], ctx.fam[ib]), pts,
                _lp_cells(ctx, ia, ib, r['ka'], r['kb']))
    return _finish_batch(ctx, 'pair', bid, _close(Bk), len(pairs), t0)


def _finish_batch(ctx, kind: str, bid: int, Bk: dict, n_obj: int, t0: float) -> dict:
    summ = SummaryCounts(ctx.families)
    res = {'bid': bid, 'kind': kind, 'summ': summ, 'cands': None, 'pool': None, 'bytes': 0, 'n_obj': n_obj, 'cells': 0, 'sec': 0.0}
    if Bk is not None:
        Dv = derive(Bk)
        summ.add(Bk, Dv)
        res['cells'] = int(Dv['ok'].any(1).sum())
        res['bytes'] = heat._W['hm2_writer'].write('cells' if kind == 'pair' else 'triples', bid, Bk, Dv)
        res['cands'] = _candidate_rows(ctx, kind, Bk, Dv)
        if kind == 'pair':
            res['pool'] = _triple_pool(ctx, Bk)
    res['sec'] = time.time() - t0
    return res


def _key_conds(ctx, kind: int, obj: int, ia: int, la: int, ib: int, lb: int) -> tuple:
    """(key, conds) of a cell: conds [[reading, [levels]], ...]; key 'reading=level & reading=level ...' (a level set is
    joined by '|')."""
    if kind == 0:
        conds = [[ctx.names[ia], [ctx.readings[ia]['levels'][la]]], [ctx.names[ib], [ctx.readings[ib]['levels'][lb]]]]
    elif kind == 1:
        conds = ctx.flags[ia]['conds'] + [[ctx.names[ib], [ctx.readings[ib]['levels'][lb]]]]
    else:
        conds = ctx.paths[obj]['conds']
    return ' & '.join(f'{r}={"|".join(lv)}' for r, lv in conds), conds


def _families(ctx, kd: int, ia: int, ib: int, obj: int) -> str:
    if kd == 0:
        fs = [ctx.fam[ia], ctx.fam[ib]]
    elif kd == 1:
        fs = [ctx.fam[x] for x in ctx.flags[ia]['readings']] + [ctx.fam[ib]]
    else:
        fs = [ctx.fam[x] for x in ctx.paths[obj]['readings']]
    return '|'.join(sorted(fs))


def _candidate_rows(ctx, kind: str, Bk: dict, Dv: dict) -> pd.DataFrame:
    """The batch's best cells per (horizon, measure) by the B heat (at most CAND_POOL, and only above the parent's
    current threshold), as rows with both splits' numbers. Built column-wise; strings only for the selected cells."""
    ki = 0 if kind == 'pair' else 1
    thr = _thr_view() if 'hm2_thr' in heat._W else None
    C, Hh, Mm = [], [], []
    for hi_ in range(len(H_SCAN)):
        ok = Dv['ok'][:, hi_]
        for mi, me in enumerate(MEASURES):
            v = np.where(ok, _sig6(Dv[me][:, hi_]), -np.inf)                # ranked as written (_sig6)
            if thr is not None:
                v = np.where(v >= thr[(ki * len(H_SCAN) + hi_) * len(MEASURES) + mi], v, -np.inf)
            k = min(CAND_POOL, int(np.isfinite(v).sum()))
            if k == 0:
                continue
            top = np.argpartition(-v, k - 1)[:k] if k < len(v) else np.arange(len(v))
            top = top[np.isfinite(v[top])]
            C.append(top)
            Hh.append(np.full(len(top), hi_))
            Mm.append(np.full(len(top), mi))
    if not C:
        return None
    c, h, mi = np.concatenate(C), np.concatenate(Hh), np.concatenate(Mm)
    S, D = Bk['st'], Dv['d'][c, h]
    df = {'kind': kind, 'source': np.array(['pair', 'flag', 'path'])[Bk['kind'][c]], 'h': np.array(H_SCAN)[h], 'measure': np.array(MEASURES)[mi],
          'value': _sig6(np.array([Dv[me][c, h] for me in MEASURES])[mi, np.arange(len(c))])}
    uc = np.unique(c)
    kc = {int(x): _key_conds(ctx, int(Bk['kind'][x]), int(Bk['obj'][x]), int(Bk['ia'][x]), int(Bk['la'][x]), int(Bk['ib'][x]), int(Bk['lb'][x])) for x in uc}
    fm = {int(x): _families(ctx, int(Bk['kind'][x]), int(Bk['ia'][x]), int(Bk['ib'][x]), int(Bk['obj'][x])) for x in uc}
    df['key'] = [kc[int(x)][0] for x in c]
    df['conds'] = [json.dumps(kc[int(x)][1]) for x in c]
    for k in ('obj', 'ia', 'la', 'ib', 'lb', 'assoc'):
        df[k] = Bk[k][c]
    df['dir'], df['d_iota'], df['iota_with_call'] = D.astype(int), Dv['di'][c, h].astype(int), Dv['with_call'][c, h]
    for k in ('oheat', 'iheat', 'lheat'):
        df[k + '_B'] = Dv[k][c, h]
    df['rest_wd_B'] = Dv['rest_wd'][c, h]
    df['parts_hot'], df['part_tmax'] = Bk['phot'][c, h], Bk['ptmax'][c, h]
    df['seen_in_league'] = np.array(PROV)[Bk['prov'][c]]
    df['learner_path'] = Bk['lp'][c]
    df['families'] = [fm[int(x)] for x in c]
    up = D >= 0
    for si, sn in ((0, 'A'), (1, 'B')):
        b = ctx.base[si]
        df[f'n_{sn}'], df[f'days_{sn}'] = Bk['n'][c, si, h], Bk['days'][c, si, h]
        for k in STATS:
            if not (k == 'wd' and si == 0):
                df[f'{k}_{sn}'] = S[c, si, h, SI[k]]
        df[f'share_{sn}'] = 100.0 * np.where(up, S[c, si, h, SI['p_up']], S[c, si, h, SI['p_dn']])
        df[f'share_over_{sn}'] = df[f'share_{sn}'] - 100.0 * np.where(up, b['bpu'][h], b['bpd'][h])
        df[f'hold_{sn}'] = np.where(up, S[c, si, h, SI['hold_up']], S[c, si, h, SI['hold_dn']])
        df[f'hold_over_{sn}'] = df[f'hold_{sn}'] - np.where(up, b['hold_up'], b['hold_dn'])
    pa = Bk['kind'][c] == 0                                               # the parts' own A odds and t (pairs)
    ia, la, ib, lb = Bk['ia'][c], Bk['la'][c], Bk['ib'][c], Bk['lb'][c]
    po = lambda r, l, hh, w: float(ctx.parts[w][int(r)][0, int(hh), int(l)])
    for nm, (rr, ll) in (('a', (ia, la)), ('b', (ib, lb))):
        df[f'odds_{nm}_A'] = [po(r, l, hh, 'odds') if p else np.nan for r, l, hh, p in zip(rr, ll, h, pa)]
        df[f't_{nm}_A'] = [po(r, l, hh, 't') if p else np.nan for r, l, hh, p in zip(rr, ll, h, pa)]
    return pd.DataFrame(df)


def _triple_pool(ctx, Bk: dict) -> pd.DataFrame:
    """Pair cells for the triple choice, A numbers only: score = the largest |iota_robust_A| / SE_A at 15, 60 or 240
    minutes where the cell has at least TRIPLE_MIN_A A entries (confluence cells). Only cells above the parent's
    current TRIPLE_POOL-th score come back."""
    S = Bk['st']
    sc = np.zeros(len(S))
    bh = np.zeros(len(S), np.int64)
    for h in [H_SCAN.index(x) for x in PACK_H]:
        with np.errstate(invalid='ignore', divide='ignore'):
            z = np.abs(S[:, 0, h, SI['iota_robust']]) / (50.0 * S[:, 0, h, SI['se']])
        z = np.where((Bk['n'][:, 0, h] >= TRIPLE_MIN_A) & np.isfinite(z), z, 0.0)
        better = z > sc
        sc, bh = np.where(better, z, sc), np.where(better, H_SCAN[h], bh)
    sc = _sig6(sc)                                                        # ranked as written
    floor = _thr_view()[-1] if 'hm2_thr' in heat._W else -np.inf
    ok = (sc > 0) & (sc >= floor)
    if not ok.any():
        return None
    df = pd.DataFrame({'obj': Bk['obj'][ok], 'ia': Bk['ia'][ok], 'la': Bk['la'][ok], 'ib': Bk['ib'][ok], 'lb': Bk['lb'][ok], 'score': sc[ok], 'h': bh[ok],
                       'n_A': Bk['n'][ok][:, 0, 0]})
    return _trim_pool(df)


def _trim_pool(df: pd.DataFrame) -> pd.DataFrame:
    return (df.sort_values(['score', 'obj', 'la', 'lb'], ascending=[False, True, True, True]).drop_duplicates(['ia', 'la', 'ib', 'lb'])
            .head(TRIPLE_POOL).reset_index(drop=True))


def pick_triple_cells(pool: pd.DataFrame, n: int = N_TRIPLE_CELLS, per_reading: int = PER_READING) -> list:
    """The n confluence pair cells with the largest A score, at most per_reading from one reading (a compute cap chosen
    on A only, not a pass mark): [(ia, la, ib, lb, score, h)]. pool: the TRIPLE_POOL best by the score."""
    out, used = [], {}
    if pool is None or not len(pool):
        return out
    for r in pool.sort_values(['score', 'obj', 'la', 'lb'], ascending=[False, True, True, True]).itertuples():
        if used.get(r.ia, 0) >= per_reading or used.get(r.ib, 0) >= per_reading:
            continue
        out.append((int(r.ia), int(r.la), int(r.ib), int(r.lb), float(r.score), int(r.h)))
        used[r.ia] = used.get(r.ia, 0) + 1
        used[r.ib] = used.get(r.ib, 0) + 1
        if len(out) >= n:
            break
    return out


def _merge(results, summ: dict, cands: Candidates, pools: list, log, what: str, total: int) -> dict:
    """Merge workers' batch results as they arrive; raise the shared thresholds after each merge."""
    t0, n, jobs, cells, by, sec = time.time(), 0, 0, 0, 0, 0.0
    thr = _thr_view() if 'hm2_thr' in heat._W else None
    nH, nM = len(H_SCAN), len(MEASURES)
    for r in results:
        summ[r['kind']].merge(r['summ'])
        cands.add(r['cands'])
        if r['pool'] is not None:
            pools.append(r['pool'])
            if len(pools) > 20:
                pools[:] = [_trim_pool(pd.concat(pools, ignore_index=True))]
        if thr is not None:
            cf = cands.frame()
            if len(cf):
                kth = cf.groupby(['kind', 'h', 'measure']).value.agg(lambda s: s.iloc[cands.k - 1] if len(s) >= cands.k else -np.inf)
                for (kd, h, me), v in kth.items():
                    thr[((0 if kd == 'pair' else 1) * nH + H_SCAN.index(int(h))) * nM + MEASURES.index(me)] = v
            if pools and sum(len(p) for p in pools) >= TRIPLE_POOL:
                pools[:] = [_trim_pool(pd.concat(pools, ignore_index=True))]
                if len(pools[0]) >= TRIPLE_POOL:
                    thr[-1] = float(pools[0].score.iloc[TRIPLE_POOL - 1])
        n += r['n_obj']
        jobs += 1
        cells += r['cells']
        by += r['bytes']
        sec += r['sec']
        if log and total and (jobs * 10 // total) != ((jobs - 1) * 10 // total):
            log(f'  {what}: {jobs:,} of {total:,} jobs ({time.time() - t0:.0f}s, peak {_rss_mb()} MB)')
    return {'objects': n, 'cells_with_sample': cells, 'shard_bytes': by, 'worker_seconds': round(sec, 1), 'wall_seconds': round(time.time() - t0, 1)}


def _ctx_on(ctx, writer, **more):
    """Put the context where the forked workers read it (heat._W) with fresh shared thresholds."""
    heat._W.update(hm2=ctx, hm2_writer=writer, hm2_summ_proto=SummaryCounts(ctx.families), hm2_thr=_thr(), **more)


def _ctx_off():
    for k in [k for k in heat._W if k.startswith('hm2')]:
        heat._W.pop(k, None)


def scan_pairs(ctx, procs: int, writer: ShardWriter, summ: dict, cands: Candidates, max_pairs: int = None, seed: int = 0, part=(0, 1),
               pools: list = None, log=print) -> dict:
    """Every pair with a different base (pair index % S == i for --part i/S) in batches of BATCH pairs through forked
    workers with the context in heat._W. max_pairs and seed are for the bench."""
    pairs = pair_list(ctx, part, max_pairs, seed)
    jobs = [(b, lo, min(lo + BATCH, len(pairs))) for b, lo in enumerate(range(0, len(pairs), BATCH))]
    _ctx_on(ctx, writer, hm2_pairs=pairs)
    try:
        st = _merge(_imap(_pair_batch, jobs, procs), summ, cands, pools if pools is not None else [], log, 'pairs', len(jobs))
    finally:
        _ctx_off()
    st['pairs'] = int(len(pairs))
    return st


# ---------------------------------------------------------------------------------------------------------- triples
def flag_column(ctx, ia: int, la: int, ib: int, lb: int) -> dict:
    """A pair cell as an in/out flag over the entries: levels ['none', 'in'] ('none' = both known and not the cell, a
    neutral level the kernel skips), code 0 where either reading is NA. Its totals and own effect are counted here."""
    ca, cb = ctx.C[:, ia], ctx.C[:, ib]
    codes = np.where((ca == 0) | (cb == 0), 0, np.where((ca == la + 1) & (cb == lb + 1), 2, 1)).astype(np.uint8)
    T = _bins(codes.astype(np.intp) * ctx.ND + ctx.day, ctx.W, 3 * ctx.ND).reshape(5, 3, ctx.ND)
    st = {k: v[..., 0] for k, v in _stats(T[:, 1:, None, :], ctx, lift=False).items()}
    return {'id': None, 'codes': codes, 'L': 2, 'skip': 1, 'work': int((codes != 1).sum()), 'T': T, 'nonneu': np.array([False, False, True]),
            'po': st['odds'], 'pt': st['t']}


def _flag_job(fi):
    """One pair-cell flag against every third reading (with a base other than the pair's two)."""
    ctx = heat._W['hm2']
    t0 = time.time()
    ia, la, ib, lb = ctx.flags[fi]['cell']
    Fc = flag_column(ctx, ia, la, ib, lb)
    bases = {ctx.readings[ia]['base'], ctx.readings[ib]['base']}
    Bk = _empty_block()
    n = 0
    for c in range(len(ctx.readings)):
        if ctx.readings[c]['base'] in bases:
            continue
        n += 1
        r = measure_cross(ctx, Fc, _col(ctx, c))
        keep = r['ka'] == 1                                               # flag 'in' x the third reading's non-neutral levels
        if not keep.any():
            continue
        r = {**r, 'ka': r['ka'][keep], 'kb': r['kb'][keep], 'st': r['st'][keep], 'n': r['n'][keep], 'days': r['days'][keep]}
        k = len(r['kb'])
        pts = [np.repeat(np.abs(np.nan_to_num(Fc['pt'][0][:, 1:2])), k, 1), np.abs(np.nan_to_num(ctx.parts['t'][c][0][:, r['kb']]))]
        prov = _prov_cells(ctx, ia, c, np.full(k, la), r['kb'], extra=((ib, lb),))
        _append(Bk, 1, fi, fi, c, r, prov, -1, pts, np.zeros(k, bool), la=np.ones(k))
    return _finish_batch(ctx, 'triple', 100000 + fi, _close(Bk), n, t0)


def _path_table(ctx, flags: list) -> np.ndarray:
    """Packed per-(cell, day) sums of a 2x2x2 table of three in/out conditions: (5, 2, 2, 2, ND)."""
    cell = flags[0].astype(np.intp) * 4 + flags[1] * 2 + flags[2]
    return _bins(cell * ctx.ND + ctx.day, ctx.W, 8 * ctx.ND).reshape(5, 2, 2, 2, ctx.ND)


def _cond_flag(ctx, name: str, levels) -> np.ndarray:
    """In/out of one condition at every entry: the reading holds one of the levels ('NA' matches an unknown state)."""
    j = ctx.byname[name]
    lv = ctx.readings[j]['levels']
    codes = [lv.index(x) + 1 for x in levels if x != 'NA' and x in lv] + ([0] if 'NA' in levels else [])
    return np.isin(ctx.C[:, j], codes)


def measure_path(ctx, conds: list) -> dict:
    """A learner path of three readings: the statistics of all 8 cells of the 2x2x2 table, iota3 of the all-in cell
    against the model with every two-way term among the conditions and each condition's own effect on the outcome
    ([ab][ac][bc][ay][by][cy]), and lift_min of the all-in cell over each member (the cell against the entries where
    the other two hold and this one does not). Returns one confluence 'cell' in measure_cross's format."""
    P = _path_table(ctx, [_cond_flag(ctx, r, lv) for r, lv in conds])
    st = {k: v.reshape(2, 6, 2, 2, 2) for k, v in _stats(P.reshape(5, 8, 1, ctx.ND), ctx, lift=False).items()}
    n = np.nan_to_num(st['n'])
    U, D = np.nan_to_num(st['p_up'] * n), np.nan_to_num(st['p_dn'] * n)
    N = np.stack([U, n - U - D, D], -1)                                   # (2, 6, 2, 2, 2, 3)
    m2 = [(-4, -3), (-4, -2), (-3, -2), (-4, -1), (-3, -1), (-2, -1)]
    with np.errstate(invalid='ignore', divide='ignore'):
        fit = _fitted_ms(ipf(N, margins=m2))[..., 1, 1, 1]
        ms = st['ms'][..., 1, 1, 1]
        se = st['se'][..., 1, 1, 1]
        o = {k: st[k][..., 1, 1, 1] for k in ('odds', 't', 'se', 'deff', 'p_up', 'p_dn', 'hold_up', 'hold_dn')}
        o['iota'] = 50.0 * (ms - fit)
        # the additive scale for three: mean sign = mu + a + b + c (backfitting over the three axes)
        o['iota_add'] = 50.0 * (ms - _additive3(U - D, n)[..., 1, 1, 1])
        o['iota_robust'] = robust_iota(o['iota'], o['iota_add'])
        o['t_iota'] = np.where(se > 0, (ms - fit) / se, 0.0)
        o['t_iota_add'] = np.where(se > 0, o['iota_add'] / (50.0 * se), 0.0)
        o['t_robust'] = np.where(se > 0, o['iota_robust'] / (50.0 * se), 0.0)
        bms = np.stack([ctx.base[s]['bms'] for s in (0, 1)])
        o['odds_fit'] = 50.0 * (fit - bms)
        o['iota_naive'] = np.full_like(ms, np.nan)
        # lift over each member: the all-in cell against (member out, the other two in)
        d = np.sign(np.nan_to_num(o['odds'][0]))[None]
        best = None
        for other in ((0, 1, 1), (1, 0, 1), (1, 1, 0)):
            sub = np.stack([P[:, 1, 1, 1], P[(slice(None),) + other]], 1)[:, None]     # (5, 1, 2, ND): the all-in cell and the other
            ls = _stats(sub, ctx, lift=True)
            rn = ls['rest_a'][..., 0, 0]
            lf = _thin(ls['lift_a'][..., 0, 0], rn)
            tl = np.where(np.isfinite(lf), ls['t_lift_a'][..., 0, 0], np.nan)
            if best is None:
                best = [lf, tl, rn]
            else:
                use = np.isfinite(lf) & (np.where(d != 0, d * lf < d * best[0], np.abs(lf) < np.abs(best[0])) | ~np.isfinite(best[0]))
                best = [np.where(use, lf, best[0]), np.where(use, tl, best[1]), np.where(use, rn, best[2])]
        o['lift_min'], o['t_lift'], o['rest_n'] = best
        o['wd'] = np.full_like(ms, np.nan)
    allin = np.ones(len(ctx.rows), bool)
    for r, lv in conds:
        allin &= _cond_flag(ctx, r, lv)
    use = allin & ctx.isB
    for hi_, H in enumerate(H_SCAN):
        u = use & ctx.v240 if H == 240 else use
        o['wd'][1, hi_] = windows_B(np.zeros(int(u.sum()), np.int64), ctx.rows[u], H, 1)[0] / ctx.base[1]['ndays'][hi_]
    S = np.stack([o[k] for k in STATS], -1)                               # (2, 6, K)
    return {'ka': np.zeros(1, np.int64), 'kb': np.zeros(1, np.int64), 'assoc': float('nan'), 'st': S[None],
            'n': np.nan_to_num(st['n'][..., 1, 1, 1]).astype(np.int64)[None], 'days': np.nan_to_num(st['days'][..., 1, 1, 1]).astype(np.int64)[None]}


def _additive3(S: np.ndarray, n: np.ndarray, iters: int = IPF_ITERS) -> np.ndarray:
    """additive_fit over three condition axes (..., 2, 2, 2)."""
    w = np.asarray(n, np.float64)
    y = _ratio(S, w)
    ax = (-3, -2, -1)
    mu = _ratio((w * y).sum(ax, keepdims=True), w.sum(ax, keepdims=True))
    eff = [np.zeros(1), np.zeros(1), np.zeros(1)]
    for _ in range(iters):
        for k in range(3):
            rest = mu + sum(eff[j] for j in range(3) if j != k)
            other = tuple(a for a in ax if a != ax[k])
            eff[k] = _ratio((w * (y - rest)).sum(other, keepdims=True), w.sum(other, keepdims=True))
    return mu + eff[0] + eff[1] + eff[2]


def _path_job(job):
    bid, lo, hi = job
    ctx = heat._W['hm2']
    t0 = time.time()
    Bk = _empty_block()
    for p in range(lo, hi):
        path = ctx.paths[p]
        r = measure_path(ctx, path['conds'])
        rd = path['readings']
        pts = [np.array([[abs(_part_t(ctx, j, lv, h))] for h in range(len(H_SCAN))]) for j, (_, lv) in zip(rd, path['conds'])]
        prov = np.array([_path_prov(ctx, path) if ctx.prov is not None else 0], np.int8)
        _append(Bk, 2, p, p, -1, r, prov, -1, pts, np.ones(1, bool), la=np.full(1, -1))
    return _finish_batch(ctx, 'triple', 200000 + bid, _close(Bk), hi - lo, t0)


def _part_t(ctx, j: int, levels, h: int) -> float:
    """A condition's own A t when it names one level (else 0: a level set has no single part effect here)."""
    lv = [x for x in levels if x != 'NA']
    if len(lv) != 1 or lv[0] not in ctx.readings[j]['levels']:
        return 0.0
    return float(np.nan_to_num(ctx.parts['t'][j][0, h, ctx.readings[j]['levels'].index(lv[0])]))


def _path_prov(ctx, path: dict) -> int:
    pv = ctx.prov
    rd = path['readings']
    pk = any(pv['inpack'][j][ctx.readings[j]['levels'].index(x)] for j, (_, lvs) in zip(rd, path['conds']) for x in lvs
             if x in ctx.readings[j]['levels'])
    st = any((min(a, b), max(a, b)) in pv['stored'] for i, a in enumerate(rd) for b in rd[i + 1:])
    return 2 if pk else (1 if st else 0)


def scan_triples(ctx, cells: list, paths: list, procs: int, writer: ShardWriter, summ: dict, cands: Candidates, log=print) -> dict:
    """(a) each picked pair cell as an in/out flag crossed with every reading (iota: what the third reading adds inside
    the pair cell); (b) each learner path of three readings (its 2x2x2 table and iota3). Every cell of a scanned
    triple is written (shards on a real coin), counted (summary kind 'triple') and ranked (candidates kind 'triple')."""
    ctx.flags = [{'cell': (ia, la, ib, lb), 'readings': [ia, ib], 'score': sc, 'h': h,
                  'conds': [[ctx.names[ia], [ctx.readings[ia]['levels'][la]]], [ctx.names[ib], [ctx.readings[ib]['levels'][lb]]]]}
                 for ia, la, ib, lb, sc, h in cells]
    ctx.paths = []
    for p in paths or []:
        try:
            rd = [ctx.byname[r] for r, _ in p['conds']]
        except KeyError:
            continue
        if len(set(rd)) == 3:
            ctx.paths.append({**p, 'readings': rd})
    _ctx_on(ctx, writer)
    try:
        jobs = list(range(len(ctx.flags)))
        st_a = _merge(_imap(_flag_job, jobs, procs), summ, cands, [], log, 'flag triples', len(jobs))
        pj = [(b, lo, min(lo + 200, len(ctx.paths))) for b, lo in enumerate(range(0, len(ctx.paths), 200))]
        st_b = _merge(_imap(_path_job, pj, procs), summ, cands, [], log, 'learner-path triples', len(pj))
    finally:
        _ctx_off()
    return {'flags': len(ctx.flags), 'flag_crosses': st_a['objects'], 'paths': len(ctx.paths), 'flag_stats': st_a, 'path_stats': st_b}


# ----------------------------------------------------------------------------------------------- section 4: re-measure
def joint_mask(ctx, conds: list, rows: np.ndarray = None, with_known: bool = False):
    """Every condition holds one of its levels at the row (heat.read_state: the last closed bar of each reading's own
    timeframe; 'NA' in a level set matches an unknown state). with_known: also whether every reading is known."""
    rows = np.arange(ctx.m['n']) if rows is None else rows
    ok = np.ones(len(rows), bool)
    known = np.ones(len(rows), bool)
    for name, lvs in conds:
        R = ctx.extra_readings[name] if name in getattr(ctx, 'extra_readings', {}) else ctx.readings[ctx.byname[name]]
        c = heat.read_state(R, rows)
        want = [R['levels'].index(x) for x in lvs if x != 'NA']
        na = 'NA' in lvs
        ok &= np.isin(c, want) | (na & (c < 0))
        known &= (c >= 0) | na
    return (ok, known) if with_known else ok


def onset_rows(mask: np.ndarray, known: np.ndarray = None) -> np.ndarray:
    """Rows where the joint state starts to hold: mask[r] and not mask[r - 1], with every reading known at r - 1 (as
    heat.level_events needs a known, different level before an event)."""
    prev = np.r_[False, mask[:-1]]
    pk = np.r_[False, known[:-1]] if known is not None else np.r_[False, np.ones(len(mask) - 1, bool)]
    return np.flatnonzero(mask & ~prev & pk)


def _full_both(ctx, idx: np.ndarray) -> tuple:
    """g.full per split on the main grid (1-60) and on the 240 grid (under h240)."""
    g, g240 = ctx.g, ctx.g240
    st = {s: g.full(g.in_split(idx, s), s) for s in heat.SPLITS}
    with h240():
        st4 = {s: g240.full(g240.in_split(idx, s), s) for s in heat.SPLITS}
    return st, st4


def _rows_of(kind: str, key: str, form: str, st: dict, st4: dict, extra: dict) -> list:
    rows = heat.full_rows(kind, key, st)
    with h240():
        rows += heat.full_rows(kind, key, st4)
    for r in rows:
        r.update(extra, form=form)
        with np.errstate(invalid='ignore', divide='ignore'):
            r['move_steps'] = float(r['excess'] / r['tick']) if r.get('tick') else float('nan')
    return rows


def _bitset(ctx, idx: np.ndarray) -> np.ndarray:
    """The B entries (every valid B minute) of a state as a packed bit set (for the near-copy Jaccard)."""
    sp = ctx.g.sp['B']
    x = np.zeros(sp.hi - sp.lo, bool)
    r = ctx.g.in_split(idx, 'B')
    x[r - sp.lo] = True
    return np.packbits(x)


def _remeasure_job(job):
    """One candidate: its joint state on every minute (xstate / xtriple) and its onsets (xonset / xtriple onset)."""
    ci = job
    ctx = heat._W['hm2']
    c = heat._W['hm2_rm'][ci]
    conds = json.loads(c['conds'])
    mask, known = joint_mask(ctx, conds, with_known=True)
    kind = 'xtriple' if c['kind'] == 'triple' else 'xstate'
    extra = {'conds': c['conds'], 'source': c['source']}
    st_rows = np.flatnonzero(mask)
    out = _rows_of(kind, c['key'], 'state', *_full_both(ctx, st_rows), extra)
    out += _rows_of('xtriple' if c['kind'] == 'triple' else 'xonset', c['key'], 'onset', *_full_both(ctx, onset_rows(mask, known)), extra)
    return ci, out, _bitset(ctx, st_rows)


def last_candle(ctx) -> dict:
    """The bid-ask bounce baseline as a reading: the sign of the decision minute's candle (c - o), k = 1. The league
    fades it (the call is against the last candle) at matched windows per day."""
    m = ctx.m
    d = m['c'] - m['o']
    codes = np.where(d > 0, 2, np.where(d < 0, 0, 1)).astype(np.int8)
    codes[m['gap']] = -1
    return {'name': 'BASE:LastCandle', 'k': 1, 'codes': codes, 'levels': ['candle down', 'candle flat', 'candle up'], 'base': 'BASE:LastCandle',
            'family': 'baseline'}


def remeasure(ctx, cands: pd.DataFrame, gbm_readings: list = (), procs: int = 1, n_top: int = N_CANDIDATES, log=print) -> tuple:
    """The best n_top candidates per (kind, horizon, measure) measured again with g.full (g240.full at 240) on every
    minute in two forms: xstate (every minute the joint state holds) and xonset (the minute it starts to hold, a
    moment like the league's events); triples as kind xtriple with form state / onset. The GBM readings go through
    heat.event_levels / level_events ('single') and their held levels ('xstate'); the last-candle baseline as kind
    'baseline'. Adds move_steps (the move / the price step). Returns (heat.Rows, near-copy table): per (kind, horizon,
    measure) list, the B-entry Jaccard of every candidate pair at or above JACC_WRITE (the league collapses >= 0.8)."""
    rows = heat.Rows()
    if cands is None or not len(cands):
        sel = pd.DataFrame(columns=['kind', 'h', 'measure', 'key', 'conds', 'source'])
    else:
        sel = (cands.sort_values(['kind', 'h', 'measure', 'value', 'key'], ascending=[True, True, True, False, True])
               .groupby(['kind', 'h', 'measure'], sort=False).head(n_top))
    uniq = sel.drop_duplicates('key')[['key', 'kind', 'conds', 'source']].to_dict('records')
    heat._W.update(hm2=ctx, hm2_rm=uniq)
    bits, got = {}, {}
    try:
        for ci, out, b in _imap(_remeasure_job, list(range(len(uniq))), procs):
            got[ci] = out                                   # added in candidate order below: the table's hash does not depend on procs
            bits[uniq[ci]['key']] = b
        for ci in range(len(uniq)):
            rows += got.pop(ci)
    finally:
        heat._W.pop('hm2_rm', None)
        heat._W.pop('hm2', None)
    log(f'  re-measured {len(uniq):,} distinct candidates in two forms (peak {_rss_mb()} MB)')
    ctx.extra_readings = {}
    for R in list(gbm_readings or []) + [last_candle(ctx)]:
        ctx.extra_readings[R['name']] = R
        kind = 'baseline' if R['name'].startswith('BASE:') else None
        for lv, side, lname in heat.event_levels(R):
            if kind is None:
                rows += _rows_of('single', f'{R["name"]}={lname}', 'onset', *_full_both(ctx, heat.level_events(R, lv, side)), {'source': 'model'})
        for i, lname in enumerate(R['levels']):
            if lname in heat.NEUTRAL and kind is None:
                continue
            idx = np.flatnonzero(joint_mask(ctx, [[R['name'], [lname]]]))
            rows += _rows_of(kind or 'xstate', f'{R["name"]}={lname}', 'state', *_full_both(ctx, idx), {'source': kind or 'model'})
    # near copies: per list, the B-entry Jaccard of every pair of its candidates
    jac = []
    pc = np.bitwise_count if hasattr(np, 'bitwise_count') else (lambda a: np.unpackbits(a.view(np.uint8)).reshape(a.shape + (-1,)).sum(-1))
    for (kind, h, me), grp in sel.groupby(['kind', 'h', 'measure'], sort=True):
        keys = [k for k in grp.key if k in bits]
        if len(keys) < 2:
            continue
        M = np.stack([bits[k] for k in keys])
        pad = (-M.shape[1]) % 8
        M = np.pad(M, ((0, 0), (0, pad))).view(np.uint64)
        sz = pc(M).sum(1).astype(np.int64)
        for i in range(len(keys) - 1):
            inter = pc(M[i] & M[i + 1:]).sum(1).astype(np.int64)
            uni = sz[i] + sz[i + 1:] - inter
            with np.errstate(invalid='ignore', divide='ignore'):
                J = np.where(uni > 0, inter / uni, 0.0)
            for q in np.flatnonzero(J >= JACC_WRITE):
                jac.append({'kind': kind, 'h': int(h), 'measure': me, 'key1': keys[i], 'key2': keys[i + 1 + q], 'jaccard': round(float(J[q]), 4)})
    return rows, pd.DataFrame(jac, columns=['kind', 'h', 'measure', 'key1', 'key2', 'jaccard'])


def near_copy_clusters(jac: pd.DataFrame, order: list, thr: float = NEAR_COPY) -> dict:
    """Near-copy collapse for one list: walking the rows best first, a row whose B entries overlap an earlier kept row's
    by at least thr (Jaccard) becomes that row's alias. Returns {kept key: [aliases]}."""
    near = {}
    for r in jac[jac.jaccard >= thr].itertuples():
        near.setdefault(r.key1, set()).add(r.key2)
        near.setdefault(r.key2, set()).add(r.key1)
    kept, out = [], {}
    for k in order:
        host = next((x for x in kept if k in near.get(x, ())), None)
        if host is None:
            kept.append(k)
            out[k] = []
        else:
            out[host].append(k)
    return out


# ------------------------------------------------------------------------------------------------ the series job
def _load_json(p: str):
    if not p:
        return None
    with open(p) as f:
        return json.load(f)


def _other_metas(d, others: dict, twin: int, m_real: dict) -> dict:
    """{O: the main-run meta that zones O's direct readings, or None} (heat_xdata.extra_readings' other_metas): the
    file <d>/<key>/meta.json with key = heat_xdata.other_meta_key (O on a real job; O-twinN on twin N when O's grid is
    the job coin's, else None: O's edges then come from its own A bars). d: the directory of the main run's metas."""
    from oracle import heat_xdata as xd
    out = {}
    for O, mo in (others or {}).items():
        _refuse_doge(O)
        key = xd.other_meta_key(O, twin, m_real, mo)
        p = os.path.join(d, key, 'meta.json') if (d and key) else ''
        out[O] = _load_json(p) if p and os.path.isfile(p) else None
    return out


def _extra_readings(m: dict, m_real: dict, g, asset: str, twin: int, other_csvs: dict, other_metas, perp_csv: str, fund_csv: str, oi_csv: str,
                    cal_csv: str, dom: str, found: dict, log) -> tuple:
    """The new readings of OR-HM2 (heat_xdata, plan section 1): heat_xdata.load_inputs loads the other coins' minutes,
    the perp and Coinbase minutes on this grid (through the one joint coin flip on a twin; the real perp is kept for the
    basis), funding, open interest, the calendar and the inventory-found frames; heat_xdata.extra_readings builds the
    readings. other_metas: the directory of the main run's metas, or {O: meta or None} already chosen. found: the
    inventory-found source paths {'btcdom', 'cb', 'book'} (each optional). Returns (readings, edges, norms, missing)."""
    from oracle import heat_xdata as xd
    inp = xd.load_inputs(asset, m_real, twin, other_csvs or {}, perp_csv or None, fund_csv or None, oi_csv or None, cal_csv or None,
                         dict(found or {}), log=log)
    kw = inp['kwargs']
    metas = other_metas if isinstance(other_metas, dict) else _other_metas(other_metas, kw['others'], twin, m_real)
    return xd.extra_readings(m, g, kw['others'], metas, kw['perp'], kw['fund'], kw['oi'], kw['cal'], dom or None, kw['found'], kw['real'], log,
                             asset=asset)


def base(asset: str, csv: str, other_csvs: dict = None, perp_csv: str = '', fund_csv: str = '', oi_csv: str = '', cal_csv: str = '', dom: str = '',
         found: dict = None, main_meta: dict = None, twin: int = 0, other_metas=None, xdata: bool = True, log=print) -> Ctx:
    """1. Refuses DOGE. 2. heat.load_minutes (strict), then make_twin(m, seed) for a twin (the real minutes are kept for
    the basis). 3. labels and Grid (HMAX 60). 4. Under h240: the 240 labels and Grid. 5. heat.build_readings (its curve
    cells off). 6. The zone edges and price step must equal main_meta (<COIN>/meta.json for the coin, <COIN>-twinN/
    meta.json for twin N): a difference stops the job. 7. The clock readings (heat_clock) and the new readings
    (heat_xdata). 8. The copy merge, entries, code matrix and counts (make_ctx)."""
    _refuse_doge(asset, csv, perp_csv, fund_csv, oi_csv)
    from oracle import heat_clock
    t0 = time.time()
    m_real = heat.load_minutes(csv)
    m = heat.make_twin(m_real, twin) if twin else m_real
    label = asset if not twin else f'{asset}~twin{twin}'
    lab = heat.labels(m)
    g = heat.Grid(m, lab)
    with h240():
        lab240 = heat.labels(m)
        g240 = heat.Grid(m, lab240)
    log(f'{label}: {m["n"]:,} minutes from {pd.Timestamp(m["t0"], unit="ms")}; labels at 1-60 and 240 ({time.time() - t0:.0f}s)')
    readings, _, edges, missing, step = heat.build_readings(m, _NoCurves(g), dom, log)
    if missing:
        raise SystemExit(f'{label}: TA-Lib functions missing from this install: {missing}')
    if main_meta is not None:
        a, b = edges, main_meta.get('edges', {})
        diff = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
        if diff or main_meta.get('price_step') != step:
            raise SystemExit(f'{label}: zone edges differ from the main run meta on {len(diff)} readings {diff[:5]} '
                             f'(price step {step} against {main_meta.get("price_step")})')
    readings += [dict(R, family='clock') for R in heat_clock.clock_readings(m)]
    xe = {'edges': {}, 'norms': {}, 'missing': []}
    if xdata:
        xr, xedges, norms, xmiss = _extra_readings(m, m_real, g, asset, twin, other_csvs, other_metas, perp_csv, fund_csv, oi_csv, cal_csv, dom,
                                                   found, log)
        if xmiss:
            raise SystemExit(f'{label}: extra inputs missing: {xmiss}')
        have = {R['name'] for R in readings}
        readings += [R for R in xr if R['name'] not in have]
        xe = {'edges': xedges, 'norms': norms, 'missing': xmiss}
    ctx = make_ctx(m, readings, asset, twin, lab=lab, g=g, lab240=lab240, g240=g240, log=log)
    ctx.m_real, ctx.edges, ctx.price_step, ctx.xdata = m_real, edges, step, xe
    return ctx


def _learner(ctx, out: str, log) -> dict:
    """Part 2 through oracle.heat_hm2_learn (plan section 3): for each model (TA, ALL) and horizon (LEARN_H) the fit on
    the A entries, the GBM call as a reading, the leaf paths and the contributions on 20,000 seeded B minutes. The
    trees go to <out>/trees/<model>_h<H>.json. Runs before the pair scan so learner_path is a column of every cell."""
    from oracle import heat_hm2_learn as hl
    os.makedirs(os.path.join(out, 'trees'), exist_ok=True)
    res = {'gbm': [], 'paths': [], 'usage': {}, 'trees': {}, 'version': None}
    try:
        import lightgbm
        res['version'] = lightgbm.__version__
    except Exception:
        pass
    rB = ctx.g.sp['B'].rows
    sampB = np.sort(np.random.default_rng([20261111, 2]).choice(rB, min(20_000, len(rB)), replace=False))
    for model in ('TA', 'ALL'):
        XB = hl.features(ctx, model, sampB)
        for H in LEARN_H:
            booster, used, tree_json = hl.learn(ctx, model, H)
            R, _ = hl.gbm_reading(ctx, booster, model, H)
            res['gbm'].append(R)
            p = os.path.join(out, 'trees', f'{model}_h{H}.json')
            with open(p, 'w') as f:
                json.dump(tree_json, f, allow_nan=False)
            res['trees'][f'{model}_h{H}'] = {'file': os.path.relpath(p, out), 'sha256': hashlib.sha256(open(p, 'rb').read()).hexdigest(),
                                             'used': list(used)}
            res['paths'] += [dict(rule, model=model, h=H) for rule in hl.leaf_paths(tree_json)]
            res['usage'][f'{model}{H}'] = hl.contributions(booster, XB)
            log(f'  learner {model} h{H}: {len(used)} readings used ({_rss_mb()} MB)')
    return res


def _set_learner_paths(ctx, paths: list) -> None:
    """learner_path lookup: (i, j) -> [(i, levels of i, j, levels of j)] from every two readings of a rule."""
    lp = {}
    for p in paths:
        cs = [(ctx.byname.get(r), lv) for r, lv in p['conds']]
        cs = [(j, {ctx.readings[j]['levels'].index(x) for x in lv if x in ctx.readings[j]['levels']}) for j, lv in cs if j is not None]
        for a in range(len(cs)):
            for b in range(a + 1, len(cs)):
                (i, si), (j, sj) = cs[a], cs[b]
                if i != j:
                    lp.setdefault((min(i, j), max(i, j)), []).append((i, si, j, sj))
    ctx.lp = lp


def _write_csv(df: pd.DataFrame, path: str) -> str:
    """CSV.gz and the sha256 of its unzipped text (as the engine's table_sha256)."""
    df.to_csv(path, index=False, compression='gzip', float_format='%.6g')
    sha = hashlib.sha256()
    with gzip.open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            sha.update(chunk)
    return sha.hexdigest()


def run_series(asset: str, csv: str, out: str, twin: int = 0, procs: int = 0, other_csvs: dict = None, perp_csv: str = '', fund_csv: str = '',
               oi_csv: str = '', cal_csv: str = '', dom: str = '', found: dict = None, main_meta: dict = None, other_metas=None,
               hm1_packs=(), hm1_pairs: str = '', part=(0, 1), shards: str = '', learn: bool = True, xdata: bool = True, max_pairs: int = None,
               seed: int = 0, ctx: Ctx = None, parts_dirs=(), log=print) -> dict:
    """One series (a coin or a twin): base -> part effects -> learner -> scan_pairs -> triple choice and leaf paths ->
    scan_triples -> remeasure. Writes into out: summary_counts.json, candidates.csv.gz, triple_pool.csv.gz, heat.csv.gz
    (re-measured rows, with table_sha256 of the unzipped text), near_copies.csv.gz, usage.json, trees/<model>_h<H>.json,
    meta.json (schema oracle-heat-hm2-1); on a real coin the cell shards (cells_*.npz, triples_*.npz) stream to
    `shards` (default <out>/shards). With --part i/S (S > 1) only the pair scan of that part runs (summary, candidates
    and the triple-choice pool of the part); `parts_dirs` (the finish job) merges the parts' files, then runs the
    triples and the re-measure. ctx: a ready context (tests)."""
    _refuse_doge(asset, csv)
    os.makedirs(out, exist_ok=True)
    procs = procs or min(4, os.cpu_count() or 1)
    t_start, sec = time.time(), {}
    tick = lambda k, t: sec.__setitem__(k, round(time.time() - t, 1))
    t = time.time()
    if ctx is None:
        ctx = base(asset, csv, other_csvs, perp_csv, fund_csv, oi_csv, cal_csv, dom, found, main_meta, twin, other_metas, xdata, log)
    tick('base', t)
    pi, S = part
    finishing = bool(parts_dirs)
    ctx.prov = provenance(ctx, load_hm1(hm1_packs, hm1_pairs))
    writer = ShardWriter(shards or os.path.join(out, 'shards'), ctx.real)
    lr = {'gbm': [], 'paths': [], 'usage': {}, 'trees': {}, 'version': None}
    if learn and (S == 1 or finishing):
        t = time.time()
        lr = _learner(ctx, out, log)
        tick('learner', t)
    _set_learner_paths(ctx, lr['paths'])
    summ = {'pair': SummaryCounts(ctx.families), 'triple': SummaryCounts(ctx.families)}
    cands, pools = Candidates(), []
    st_pairs = {}
    if finishing:                                   # merge the parts' pair results
        for d in parts_dirs:
            with open(os.path.join(d, 'summary_counts.json')) as f:
                sj = json.load(f)
            summ['pair'].merge(SummaryCounts.from_json(sj['pair']))
            cands.add(pd.read_csv(os.path.join(d, 'candidates.csv.gz'), low_memory=False))
            if os.path.exists(os.path.join(d, 'triple_pool.csv.gz')):
                pools.append(pd.read_csv(os.path.join(d, 'triple_pool.csv.gz')))
        st_pairs = {'merged_parts': list(parts_dirs)}
    else:
        t = time.time()
        st_pairs = scan_pairs(ctx, procs, writer, summ, cands, max_pairs, seed, part, pools, log)
        tick('pairs', t)
        log(f'{ctx.label}: {st_pairs["pairs"]:,} pairs, {st_pairs["cells_with_sample"]:,} confluence cells with a sample ({sec["pairs"]}s, peak {_rss_mb()} MB)')
    pool = _trim_pool(pd.concat(pools, ignore_index=True)) if pools else pd.DataFrame(columns=['obj', 'ia', 'la', 'ib', 'lb', 'score', 'h', 'n_A'])
    st_tri, rows, jac = {}, heat.Rows(), pd.DataFrame()
    if S == 1 or finishing:
        t = time.time()
        cells = pick_triple_cells(pool)
        three = [p for p in lr['paths'] if len({r for r, _ in p['conds']}) == 3]
        st_tri = scan_triples(ctx, cells, three, procs, writer, summ, cands, log)
        tick('triples', t)
        t = time.time()
        rows, jac = remeasure(ctx, cands.frame(), lr['gbm'], procs, log=log)
        tick('remeasure', t)
    # ------------------------------------------------------------------------------------------------- the files
    cf = cands.frame()
    if len(cf) and ctx.lp:
        pass                                        # learner_path was set inside the scan
    with open(os.path.join(out, 'summary_counts.json'), 'w') as f:
        json.dump({'schema': 'oracle-heat-hm2-summary-1', 'label': ctx.label, 'twin': ctx.twin, 'part': [pi, S],
                   'pair': summ['pair'].to_json(), 'triple': summ['triple'].to_json()}, f, allow_nan=False)
    _write_csv(cf, os.path.join(out, 'candidates.csv.gz'))
    _write_csv(pool, os.path.join(out, 'triple_pool.csv.gz'))
    sha = None
    if S == 1 or finishing:
        df = rows.frame()
        if len(df):
            df.insert(0, 'coin', ctx.label)
        sha = _write_csv(df, os.path.join(out, 'heat.csv.gz'))
        _write_csv(jac, os.path.join(out, 'near_copies.csv.gz'))
    with open(os.path.join(out, 'usage.json'), 'w') as f:
        json.dump(_clean(lr['usage']) if lr['usage'] else {'learner': 'not run in this job'}, f, allow_nan=False)
    meta = {'schema': 'oracle-heat-hm2-1', 'asset': asset, 'label': ctx.label, 'twin': ctx.twin, 'real': ctx.real, 'part': [pi, S],
            'stride': A_STRIDE, 'horizons': H_SCAN, 'entries': {'A': int((ctx.split == 0).sum()), 'B': int((ctx.split == 1).sum()),
                                                                 'valid240': int(ctx.v240.sum())},
            'splits': {s: [str(pd.Timestamp(a, unit='ms')), str(pd.Timestamp(b, unit='ms'))] for s, (a, b) in heat.SPLITS.items()},
            'heat_end': str(pd.Timestamp(heat.HEAT_END, unit='ms')), 'minutes': int(ctx.m['n']), 'from': str(pd.Timestamp(ctx.m['t0'], unit='ms')),
            'base': {s: {'msign': _clean(list(ctx.base[i]['bms'])), 'p_up': _clean(list(ctx.base[i]['bpu'])), 'p_dn': _clean(list(ctx.base[i]['bpd'])),
                         'hold_up': _clean(ctx.base[i]['hold_up']), 'hold_dn': _clean(ctx.base[i]['hold_dn']), 'ndays': _clean(list(ctx.base[i]['ndays']))}
                     for i, s in enumerate(('A', 'B'))},
            'readings': [{'name': R['name'], 'family': f, 'k': int(R['k']), 'levels': list(R['levels']), 'aliases': R.get('aliases', [])}
                         for R, f in zip(ctx.readings, ctx.fam)],
            'families': ctx.families, 'aliases': ctx.aliases, 'edges_new': _clean(getattr(ctx, 'xdata', {}).get('edges', {})),
            'norms': _clean(getattr(ctx, 'xdata', {}).get('norms', {})), 'missing': getattr(ctx, 'xdata', {}).get('missing', []),
            'price_step': getattr(ctx, 'price_step', None), 'pairs': _clean(st_pairs), 'triples': _clean(st_tri),
            'triple_cells': [list(f['cell']) + [round(f['score'], 4), f['h']] for f in ctx.flags],
            'learner': {'version': lr['version'], 'trees': lr['trees'], 'paths': len(lr['paths'])},
            'shards': {'dir': writer.dir if writer.enabled else None, 'bytes': int(st_pairs.get('shard_bytes', 0))},
            'table_sha256': sha, 'seconds': sec, 'seconds_total': round(time.time() - t_start, 1), 'peak_rss_mb': _rss_mb()}
    with open(os.path.join(out, 'meta.json'), 'w') as f:
        json.dump(_clean(meta), f, indent=1, allow_nan=False)
    log(f'{ctx.label}: done in {meta["seconds_total"]}s, peak {meta["peak_rss_mb"]} MB')
    return meta


def _clean(x):
    """JSON-safe (allow_nan False): NaN / inf -> None, numpy scalars -> Python."""
    if isinstance(x, dict):
        return {str(k): _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating, float)):
        return float(x) if math.isfinite(float(x)) else None
    if isinstance(x, np.ndarray):
        return _clean(x.tolist())
    if isinstance(x, (np.bool_,)):
        return bool(x)
    return x


def bench(asset: str, csv: str, out: str, n_pairs: int = 3000, procs: int = 0, learn: bool = True, log=print, **kw) -> dict:
    """base + n_pairs random pairs + one learner fit (ALL, H = 15). Prints ms per pair, the projected minutes of a full
    series and of its pair stage, peak RSS and the projected shard size of a real series, and writes bench.json."""
    os.makedirs(out, exist_ok=True)
    procs = procs or min(4, os.cpu_count() or 1)
    t = time.time()
    ctx = base(asset, csv, log=log, **{k: v for k, v in kw.items() if k in ('other_csvs', 'perp_csv', 'fund_csv', 'oi_csv', 'cal_csv', 'dom', 'found',
                                                                              'main_meta', 'twin', 'other_metas', 'xdata')})
    t_base = time.time() - t
    total = len(pair_list(ctx))
    writer = ShardWriter(os.path.join(out, 'shards'), True)
    summ = {'pair': SummaryCounts(ctx.families), 'triple': SummaryCounts(ctx.families)}
    t = time.time()
    st = scan_pairs(ctx, procs, writer, summ, Candidates(), max_pairs=n_pairs, seed=1, log=log)
    t_pairs = time.time() - t
    ms_pair = 1000.0 * t_pairs / max(st['pairs'], 1)
    t_fit = None
    if learn:
        from oracle import heat_hm2_learn as hl
        t = time.time()
        hl.learn(ctx, 'ALL', 15)
        t_fit = time.time() - t
    n_tri = N_TRIPLE_CELLS * len(ctx.readings)
    proj_pairs = ms_pair * total / 60000.0
    proj = (t_base + (t_fit or 0) * 2 * len(LEARN_H) + ms_pair * (total + n_tri) / 1000.0) / 60.0 + 12.0      # + the plan's 12 min re-measure
    shard_b = st['shard_bytes'] / max(st['pairs'], 1) * (total + n_tri)
    res = {'schema': 'oracle-heat-hm2-bench-1', 'asset': asset, 'readings': len(ctx.readings), 'pairs_total': total, 'pairs_run': st['pairs'],
           'procs': procs, 'ms_per_pair_wall': round(ms_pair, 3), 'ms_per_pair_worker': round(1000.0 * st['worker_seconds'] / max(st['pairs'], 1), 3),
           'base_seconds': round(t_base, 1), 'learner_fit_seconds': None if t_fit is None else round(t_fit, 1),
           'projected_pair_minutes': round(proj_pairs, 1), 'projected_series_minutes': round(proj, 1),
           'parts_needed': int(math.ceil(proj / 300.0)), 'projected_shard_gb': round(shard_b / 1e9, 2), 'peak_rss_mb': _rss_mb(),
           'entries': {'A': int((ctx.split == 0).sum()), 'B': int((ctx.split == 1).sum())}}
    with open(os.path.join(out, 'bench.json'), 'w') as f:
        json.dump(res, f, indent=1, allow_nan=False)
    log(json.dumps(res, indent=1))
    return res


# --------------------------------------------------------------------------------------------------------------- CLI
def _inputs(ap):
    ap.add_argument('--asset', required=True)
    ap.add_argument('--csv', required=True)
    ap.add_argument('--others', default='')                       # ETH=<csv>,SOL=<csv>,XRP=<csv>
    ap.add_argument('--perp', default='')
    ap.add_argument('--fund', default='')
    ap.add_argument('--oi', default='')
    ap.add_argument('--cal', default='')
    ap.add_argument('--dom', default='')
    ap.add_argument('--found', default='')                        # JSON (text or a file): inventory-found paths {btcdom, cb, book}
    ap.add_argument('--main-meta', default='')                    # <COIN>/meta.json or <COIN>-twinN/meta.json of the main run
    ap.add_argument('--other-metas', default='')                  # the main run's dir of <O>[-twinN]/meta.json
    ap.add_argument('--twin', type=int, default=0)
    ap.add_argument('--procs', type=int, default=0)
    ap.add_argument('--no-xdata', action='store_true')            # the engine's readings and the clock only
    ap.add_argument('--no-learn', action='store_true')


def _kw(a) -> dict:
    others = dict(x.split('=', 1) for x in a.others.split(',') if x)
    found = {}
    if a.found:
        found = _load_json(a.found) if os.path.isfile(a.found) else json.loads(a.found)
    return {'other_csvs': others, 'perp_csv': a.perp, 'fund_csv': a.fund, 'oi_csv': a.oi, 'cal_csv': a.cal, 'dom': a.dom, 'found': found,
            'main_meta': _load_json(a.main_meta), 'twin': a.twin, 'other_metas': a.other_metas, 'xdata': not a.no_xdata}


def main(argv=None):
    ap = argparse.ArgumentParser(prog='oracle.heat_hm2')
    sub = ap.add_subparsers(dest='cmd', required=True)
    c = sub.add_parser('coin')
    _inputs(c)
    c.add_argument('--out', required=True)
    c.add_argument('--part', default='0/1')
    c.add_argument('--shards', default='')
    c.add_argument('--hm1-packs', default='')
    c.add_argument('--hm1-pairs', default='')
    fn = sub.add_parser('finish')
    _inputs(fn)
    fn.add_argument('--out', required=True)
    fn.add_argument('--parts', required=True)                     # the --part jobs' out dirs, comma-separated
    fn.add_argument('--shards', default='')
    fn.add_argument('--hm1-packs', default='')
    fn.add_argument('--hm1-pairs', default='')
    b = sub.add_parser('bench')
    _inputs(b)
    b.add_argument('--out', required=True)
    b.add_argument('--pairs', type=int, default=3000)
    lg = sub.add_parser('league')
    lg.add_argument('--inputs', required=True)
    lg.add_argument('--hm1', default='')
    lg.add_argument('--out', required=True)
    lg.add_argument('--stamp', default='')
    pr = sub.add_parser('parity')
    pr.add_argument('rest', nargs=argparse.REMAINDER)
    a = ap.parse_args(argv)
    if a.cmd in ('coin', 'finish'):
        kw = _kw(a)
        pi, S = (int(x) for x in a.part.split('/')) if a.cmd == 'coin' else (0, 1)
        if not 0 <= pi < S:
            raise SystemExit(f'--part {a.part}: want i/S with 0 <= i < S')
        mt = run_series(a.asset, a.csv, a.out, procs=a.procs, part=(pi, S), shards=a.shards, learn=not a.no_learn,
                        hm1_packs=[x for x in a.hm1_packs.split(',') if x], hm1_pairs=a.hm1_pairs,
                        parts_dirs=[x for x in a.parts.split(',') if x] if a.cmd == 'finish' else (), **kw)
        print(json.dumps({k: v for k, v in mt.items() if k not in ('readings', 'base', 'aliases', 'edges_new', 'norms')}, indent=1))
    elif a.cmd == 'bench':
        kw = _kw(a)
        bench(a.asset, a.csv, a.out, a.pairs, a.procs, learn=not a.no_learn, **kw)
    elif a.cmd == 'league':
        from oracle import heat_hm2_league
        heat_hm2_league.league(a.inputs, a.hm1, a.out, a.stamp)
    else:
        from oracle import heat_hm2_league
        heat_hm2_league.main(['parity'] + list(a.rest))


if __name__ == '__main__':
    main()
