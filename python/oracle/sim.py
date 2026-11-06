"""Shared simulation and statistics for the oracle-setups study: imported by the miner (oracle/mine.py) and the HO-1
scorer (oracle/ho1.py), so both stages trade, match and test a setup the same way.

Implements these pieces of the pre-registration python/oracle/prereg/OR-H1.md:
- "Mining": items (feature states) and setups (conjunctions of up to 3 items from different features): items_of,
  side_columns, fire_mask; the Jaccard overlap of firing sets (jaccard).
- "Confirmation (discovery B) and freeze" / "HO-1": the exact trade (one position at a time per asset, skip while busy:
  trade_sim, busy_key), by-day $ with 0.0 on every day of the span (daily_usd, daily_vec), the matched random-entry
  placebo (same stratum and UTC day, fallback same stratum and split, 8 seeds averaged: PlaceboPool, matched_placebo),
  the stationary bootstrap of daily $ (mean block 5 days, 2,000 draws: stationary_bootstrap_p) and BHY at q = 0.10 (bhy).
- "Splits": split_rows = common.split_of plus the Kalshi rule that the contract's close must be inside the split too
  (parts that carry close.npy, i.e. tennis).
Parts follow python/oracle/SPEC.md section 1: oracle.common.Part (memory-mapped directory) or ArrayPart (in-memory rows).

Conventions. An item is Item(f, v, col): f = the feature name as mined (a side-relative column '<name>@<side>' listed in
meta.side_features is mined as '<name>', the builders' convention), v = the state (+1 / -1) or bucket level, col = its X
column in that part. A setup is a dict {side, items: [{f, v}], ...} (the SPEC 3 setup JSON); fire_mask resolves f per part
and side, so one pooled setup fires on every part that has the feature.
"""
from __future__ import annotations

import math
from typing import NamedTuple

import numba as nb
import numpy as np
from scipy.stats import t as student_t

from .common import DAY, HOLD_TO, SPLITS, iso_day, key, split_of

SPLIT_CODE = {'': 0, 'A': 1, 'B': 2, 'H': 3}


# ---------------------------------------------------------------- parts held in memory

class ArrayPart:
    """A Part-like view over in-memory arrays (same interface as oracle.common.Part: part['name'], has, meta, n,
    features, ct, scope). The miner wraps its dev-only rows in one so nothing after DEV_END is reachable."""

    def __init__(self, meta: dict, arrays: dict, path: str | None = None):
        self.meta = meta
        self.arrays = arrays
        self.path = path

    def __getitem__(self, name: str) -> np.ndarray:
        return self.arrays[name]

    def has(self, name: str) -> bool:
        return name in self.arrays

    @property
    def n(self) -> int:
        return int(len(self.arrays['t']))

    @property
    def features(self) -> list:
        return self.meta['features']

    @property
    def ct(self) -> str:
        return self.meta['ct']

    @property
    def scope(self) -> str:
        return self.meta['scope']


# ---------------------------------------------------------------- items and firing

class Item(NamedTuple):
    f: str     # mined feature name (side suffix stripped for a side-relative column)
    v: int     # +1 / -1 for a state feature, the level for a bucket feature
    col: int   # X column in this part


def side_columns(meta: dict, side: str) -> dict:
    """{mined feature name: X column} for side `side`. A column listed in meta.side_features under some side applies to
    the listed sides only (and is named without its '@<side>' suffix, or by its 'base' key); an unlisted column applies to
    every side. side_features entries may be column indexes or column names."""
    feats = meta['features']
    names = [f['name'] for f in feats]
    sf = meta.get('side_features') or {}
    idx = lambda c: int(c) if not isinstance(c, str) else names.index(c)
    listed = {s: {idx(c) for c in cols} for s, cols in sf.items()}
    any_listed = set().union(*listed.values()) if listed else set()
    mine = listed.get(side, set())
    out: dict = {}
    for j, f in enumerate(feats):
        if j in any_listed and j not in mine:
            continue
        name = f['name']
        if j in mine:
            suf = '@' + side
            name = f.get('base') or (name[:-len(suf)] if name.endswith(suf) else name)
        if name in out:
            raise ValueError(f'side {side}: two X columns map to the feature name {name!r}')
        out[name] = j
    return out


def items_of(part, side: str) -> list:
    """Every candidate item of side `side` (prereg "Mining": a state feature gives (f, +1) and (f, -1), a bucket feature
    gives (f, level) for each level >= 0; 0 / NA states and the -1 bucket are never items). Support is filtered by the
    caller. Order: X column order."""
    feats = part.meta['features']
    out = []
    for name, j in side_columns(part.meta, side).items():
        f = feats[j]
        if f['kind'] == 'state':
            out += [Item(name, 1, j), Item(name, -1, j)]
        elif f['kind'] == 'bucket':
            out += [Item(name, int(lv), j) for lv in f['levels'] if int(lv) >= 0]
        else:
            raise ValueError(f'feature {f["name"]}: unknown kind {f["kind"]!r}')
    return out


def _item_fv(it) -> tuple:
    if isinstance(it, dict):
        return str(it['f']), int(it['v'])
    return str(it[0]), int(it[1])


def resolve(part, side: str, f: str) -> int:
    """X column of mined feature f for side `side` in this part, -1 if the part has no such feature. A full column name
    (e.g. 'k_price@Y') is accepted too."""
    cols = side_columns(part.meta, side)
    if f in cols:
        return cols[f]
    names = [x['name'] for x in part.meta['features']]
    if f in names and names.index(f) in cols.values():
        return names.index(f)
    return -1


def _rows_index(rows, n: int) -> np.ndarray | None:
    if rows is None:
        return None
    r = np.asarray(rows)
    if r.dtype == bool:
        if len(r) != n:
            raise ValueError('boolean rows mask has the wrong length')
        return np.flatnonzero(r)
    return r.astype(np.int64, copy=False)


def fire_mask(part, setup: dict, rows=None) -> np.ndarray:
    """Bool per row: every item of the setup holds (X[row, col(f)] == v) for setup['side']. rows: None (every row of the
    part, result length part.n), an index array (result aligned with it) or a bool mask (result over the selected rows).
    A setup whose feature the part lacks never fires there. Feature condition only: tradability (ok) and the label are the
    caller's (trade_sim skips rows whose trade $ is NaN)."""
    X = part['X']
    n = X.shape[0]
    idx = _rows_index(rows, n)
    m = n if idx is None else len(idx)
    out = np.ones(m, dtype=bool)
    side = setup['side']
    for it in setup['items']:
        f, v = _item_fv(it)
        j = resolve(part, side, f)
        if j < 0:
            return np.zeros(m, dtype=bool)
        col = X[:, j] if idx is None else X[idx, j]
        out &= np.asarray(col) == v
    return out


# ---------------------------------------------------------------- splits and position keys

def split_rows(part, h: int) -> np.ndarray:
    """Per row 'A' / 'B' / 'H' / '': common.split_of (decision and horizon inside the split) and, when the part has
    close.npy (the contract's close time), the close inside the split as well (prereg "Splits", Kalshi rule)."""
    ct = part.meta['ct']
    s = split_of(part['t'], h, ct)
    if part.has('close'):
        close = np.asarray(part['close'], dtype=np.int64)
        for name, (_, b) in SPLITS[ct].items():
            s[(s == name) & (close > b)] = ''
        s[(s == 'H') & (close > HOLD_TO)] = ''
    return s


def split_codes(s: np.ndarray) -> np.ndarray:
    """'' / 'A' / 'B' / 'H' -> 0 / 1 / 2 / 3 (int64)."""
    out = np.zeros(len(s), dtype=np.int64)
    for name, c in SPLIT_CODE.items():
        if c:
            out[s == name] = c
    return out


def busy_key(part, rows=None) -> np.ndarray:
    """The 'asset' a position occupies (one position at a time per key): asset.npy for perps and Price Prediction (one
    coin per part), the event (group.npy, the match) for tennis, whose asset.npy is the tour (one tennis position per
    tour at a time would be no tennis bot)."""
    a = part['group'] if part.meta['ct'] == 'tennis' else part['asset']
    a = np.asarray(a, dtype=np.int64)
    idx = _rows_index(rows, len(a))
    return a if idx is None else a[idx]


def shift_index(part) -> tuple:
    """(prev, next): for each row the previous / next decision row of the same contract (mkt.npy if present, else
    group.npy; perps: the same UTC day), -1 at the ends. Used by the staler / earlier feature adversaries."""
    k = np.asarray(part['mkt'] if part.has('mkt') else part['group'], dtype=np.int64)
    n = len(k)
    order = np.argsort(k, kind='stable')           # rows are t-sorted, so each key's rows stay in time order
    same = k[order[1:]] == k[order[:-1]]
    prev = np.full(n, -1, dtype=np.int64)
    nxt = np.full(n, -1, dtype=np.int64)
    prev[order[1:][same]] = order[:-1][same]
    nxt[order[:-1][same]] = order[1:][same]
    return prev, nxt


# ---------------------------------------------------------------- the exact trade

@nb.njit(cache=False)
def _trade_sim_nb(t, hold, cand, g, ng, order):
    busy = np.full(ng, np.iinfo(np.int64).min, dtype=np.int64)
    out = np.empty(len(order), dtype=np.int64)
    k = 0
    for i in order:
        if not cand[i]:
            continue
        gi = g[i]
        if t[i] >= busy[gi]:
            out[k] = i
            k += 1
            busy[gi] = t[i] + hold[i] * 60000
    return out[:k]


def trade_sim(t, hold_min, trade_usd, fire, groups=None) -> np.ndarray:
    """Indexes of the trades taken, in time order: walk the rows by t; a row is entered when it fires, its trade $ is
    finite (the side was tradable) and its key (groups: e.g. busy_key; None = one position at a time over all rows) is
    free; it then holds the key for hold_min minutes, so the next entry on that key needs t >= t_prev + hold minutes
    (skip while busy). A hold of 0 counts as 1 minute (no two entries at one instant)."""
    t = np.asarray(t, dtype=np.int64)
    n = len(t)
    cand = np.asarray(fire, dtype=bool) & np.isfinite(np.asarray(trade_usd, dtype=np.float64))
    hold = np.maximum(np.nan_to_num(np.asarray(hold_min, dtype=np.float64), nan=1.0), 1.0).astype(np.int64)
    if groups is None:
        g = np.zeros(n, dtype=np.int64)
        ng = 1
    else:
        u, g = np.unique(np.asarray(groups), return_inverse=True)
        g = g.astype(np.int64)
        ng = max(1, len(u))
    if n == 0:
        return np.zeros(0, dtype=np.int64)
    order = np.argsort(t, kind='stable').astype(np.int64)
    return _trade_sim_nb(t, hold, cand, g, ng, order)


# ---------------------------------------------------------------- by-day $

def span_days(span) -> tuple:
    """[from, to) ms -> (first UTC day index, last day index + 1)."""
    return int(span[0] // DAY), int(-(-int(span[1]) // DAY))


def daily_vec(t, usd, span) -> np.ndarray:
    """$ per UTC day of the decision time, one entry for every day of span [from, to) (0.0 on days without trades)."""
    d0, d1 = span_days(span)
    t = np.asarray(t, dtype=np.int64)
    usd = np.asarray(usd, dtype=np.float64)
    d = t // DAY - d0
    if len(d) and (d.min() < 0 or d.max() >= d1 - d0):
        raise ValueError('a trade falls outside the daily span')
    return np.bincount(d, weights=usd, minlength=d1 - d0).astype(np.float64)


def day_labels(span) -> list:
    d0, d1 = span_days(span)
    return [iso_day(d * DAY) for d in range(d0, d1)]


def daily_usd(t, trade_usd, taken, span) -> dict:
    """{'YYYY-MM-DD': $} over every day of span [from, to) ms (0.0 where nothing was taken); taken = row indexes into t /
    trade_usd (None = every row)."""
    t = np.asarray(t, dtype=np.int64)
    usd = np.asarray(trade_usd, dtype=np.float64)
    if taken is not None:
        taken = np.asarray(taken, dtype=np.int64)
        t, usd = t[taken], usd[taken]
    v = daily_vec(t, usd, span)
    return {d: float(x) for d, x in zip(day_labels(span), v)}


# ---------------------------------------------------------------- matched random-entry placebo

class PlaceboPool:
    """Random ok decisions to replace taken trades with (prereg "Confirmation": each trade replaced by a random decision
    from the same stratum and day). Pool = rows with ok_{s}{h} = 1, stratum_{s} >= 0 and a finite trade $ (restricted to
    `rows` if given). A taken row draws uniformly from the pool rows of its (stratum, split, UTC day); if there are none,
    from its (stratum, split); if still none it is unmatched (placebo $ 0, counted)."""

    def __init__(self, part, side: str, h: int, rows=None):
        t = np.asarray(part['t'], dtype=np.int64)
        st = np.asarray(part[f'stratum_{side}'], dtype=np.int64)
        tr = np.asarray(part[key('trade', side, h)], dtype=np.float64)
        ok = np.asarray(part[key('ok', side, h)]) == 1
        sp = split_codes(split_rows(part, h))
        pool = ok & (st >= 0) & np.isfinite(tr)
        if rows is not None:
            m = np.zeros(len(t), dtype=bool)
            m[_rows_index(rows, len(t))] = True
            pool &= m
        self.t, self.st, self.sp, self.trade = t, st, sp, tr
        idx = np.flatnonzero(pool)
        self.k1 = self._k1(st[idx], sp[idx], t[idx] // DAY)
        o1 = np.argsort(self.k1, kind='stable')
        self.k1, self.i1 = self.k1[o1], idx[o1]
        self.k2 = st[idx] * 4 + sp[idx]
        o2 = np.argsort(self.k2, kind='stable')
        self.k2, self.i2 = self.k2[o2], idx[o2]
        self.n_pool = len(idx)

    @staticmethod
    def _k1(st, sp, day):
        return (st * 4 + sp) * 1_000_000 + day

    def draw(self, taken, seeds: int = 8, seed: int = 0) -> tuple:
        """(placebo $ per taken row averaged over `seeds` draws, info {n, same_day, fallback, unmatched})."""
        taken = np.asarray(taken, dtype=np.int64)
        n = len(taken)
        if n == 0:
            return np.zeros(0), {'n': 0, 'same_day': 0, 'fallback': 0, 'unmatched': 0}
        st, sp = self.st[taken], self.sp[taken]
        k1 = self._k1(st, sp, self.t[taken] // DAY)
        lo1, hi1 = np.searchsorted(self.k1, k1, 'left'), np.searchsorted(self.k1, k1, 'right')
        k2 = st * 4 + sp
        lo2, hi2 = np.searchsorted(self.k2, k2, 'left'), np.searchsorted(self.k2, k2, 'right')
        day_ok = hi1 > lo1
        fb_ok = ~day_ok & (hi2 > lo2)
        acc = np.zeros(n)
        for s in range(seeds):
            u = np.random.default_rng([int(seed) & 0xFFFFFFFF, s]).random(n)
            pick = np.full(n, -1, dtype=np.int64)
            pick[day_ok] = self.i1[lo1[day_ok] + (u[day_ok] * (hi1[day_ok] - lo1[day_ok])).astype(np.int64)]
            pick[fb_ok] = self.i2[lo2[fb_ok] + (u[fb_ok] * (hi2[fb_ok] - lo2[fb_ok])).astype(np.int64)]
            v = np.zeros(n)
            m = pick >= 0
            v[m] = self.trade[pick[m]]
            acc += v
        info = {'n': n, 'same_day': int(day_ok.sum()), 'fallback': int(fb_ok.sum()), 'unmatched': int(n - day_ok.sum() - fb_ok.sum())}
        return acc / max(1, seeds), info


def matched_placebo(part, side: str, h: int, taken_rows, seeds: int = 8, seed: int = 0, span=None, rows=None) -> dict:
    """Daily $ {'YYYY-MM-DD': $} of the matched random-entry placebo: every taken trade replaced by a random ok decision of
    the same stratum and UTC day (fallback: same stratum and split), averaged over `seeds` seeds, booked on the taken
    trade's day (so the placebo is paired day by day with the setup). span [from, to) ms (default: the taken trades'
    days); rows restricts the pool (e.g. the HO-1 rows)."""
    taken_rows = np.asarray(taken_rows, dtype=np.int64)
    pool = PlaceboPool(part, side, h, rows)
    vals, _ = pool.draw(taken_rows, seeds, seed)
    t = np.asarray(part['t'], dtype=np.int64)[taken_rows]
    if span is None:
        span = (int(t.min() // DAY * DAY), int((t.max() // DAY + 1) * DAY)) if len(t) else (0, 0)
    return daily_usd(t, vals, None, span)


# ---------------------------------------------------------------- stationary bootstrap and BHY

@nb.njit(cache=False)
def _sb_means(x, p, draws, seed):
    """Politis-Romano stationary bootstrap means: blocks start uniformly, lengths geometric with mean 1/p, circular."""
    np.random.seed(seed)
    n = len(x)
    out = np.empty(draws)
    for d in range(draws):
        s = 0.0
        i = np.random.randint(0, n)
        for _ in range(n):
            s += x[i]
            if np.random.random() < p:
                i = np.random.randint(0, n)
            else:
                i += 1
                if i == n:
                    i = 0
        out[d] = s / n
    return out


def stationary_bootstrap_test(x, mean_block: float = 5.0, draws: int = 2000, seed: int = 0) -> dict:
    """One-sided test of mean(x) > 0 on a daily series by the stationary bootstrap (mean block `mean_block` days,
    `draws` resamples). p_emp = share of resampled means <= 0; p_t = the Student-t tail with n - 1 degrees of freedom of
    mean / se, se = the bootstrap SD of the mean; p = max(p_emp, p_t). The parametric tail gives p below 1 / draws
    (which BHY over hundreds of setups needs); taking the max keeps p at least the empirical bootstrap p.
    A normal tail (ndtr) was used before the review of Nov 6: on short daily series (tennis B 39 days, Price Prediction
    B 47) it understated the tail 3-5x at the stage-2 BHY thresholds; the t tail is close to nominal there (the reviewers'
    Monte Carlo of confirm(): P(p <= 1e-4) 0.00010 at 39 days). 'p_norm' is kept as an alias of p_t for readers."""
    x = np.asarray(x, dtype=np.float64)
    n = len(x)
    mean = float(x.mean()) if n else 0.0
    if n < 2 or not np.any(x != 0) or not np.isfinite(x).all():
        return {'mean': mean, 'se': float('nan'), 'p_emp': 1.0, 'p_t': 1.0, 'p_norm': 1.0, 'p': 1.0, 'n': n}
    means = _sb_means(x, 1.0 / max(1.0, float(mean_block)), int(draws), int(seed) & 0x7FFFFFFF)
    p_emp = float(np.mean(means <= 0.0))
    se = float(np.std(means, ddof=1))
    if se > 0:
        p_t = float(student_t.sf(mean / se, df=n - 1))
    else:
        p_t = 0.0 if mean > 0 else 1.0
    return {'mean': mean, 'se': se, 'p_emp': p_emp, 'p_t': p_t, 'p_norm': p_t, 'p': max(p_emp, p_t), 'n': n}


def stationary_bootstrap_p(x, mean_block: float = 5.0, draws: int = 2000, seed: int = 0) -> float:
    """p of stationary_bootstrap_test (one-sided, mean > 0)."""
    return stationary_bootstrap_test(x, mean_block, draws, seed)['p']


def bhy_adjust(ps) -> np.ndarray:
    """Benjamini-Hochberg-Yekutieli adjusted p values in the input order (valid under any dependence; a NaN p counts as
    1). Same as research/registry.py bhy (origin/claude/project-thread-79ntof) and allpairs.aph.bhy (unrounded)."""
    p = np.asarray(ps, dtype=np.float64).copy()
    m = len(p)
    if m == 0:
        return np.zeros(0)
    p[~np.isfinite(p)] = 1.0
    c = float(np.sum(1.0 / np.arange(1, m + 1)))
    order = np.argsort(p, kind='stable')
    scaled = p[order] * m * c / np.arange(1, m + 1)
    adj_sorted = np.minimum(1.0, np.minimum.accumulate(scaled[::-1])[::-1])
    adj = np.empty(m)
    adj[order] = adj_sorted
    return adj


def bhy(ps, q: float = 0.10) -> np.ndarray:
    """Bool mask: rejected by BHY at level q (adjusted p <= q)."""
    return bhy_adjust(ps) <= q


def jaccard(a, b) -> float:
    """|a & b| / |a | b| of two firing sets: bool masks of equal length, or arrays of row indexes. 0.0 if both empty."""
    a, b = np.asarray(a), np.asarray(b)
    if a.dtype == bool and b.dtype == bool:
        inter = int(np.count_nonzero(a & b))
        union = int(np.count_nonzero(a | b))
    else:
        inter = len(np.intersect1d(a, b))
        union = len(np.union1d(a, b))
    return inter / union if union else 0.0


def tstat(mean: float, var: float, n_eff: float) -> float:
    """mean / sqrt(var / n_eff) (inf-safe: 0 when there is nothing)."""
    if not (n_eff > 0) or not math.isfinite(mean):
        return 0.0
    return mean / math.sqrt(max(var, 1e-12) / n_eff)
