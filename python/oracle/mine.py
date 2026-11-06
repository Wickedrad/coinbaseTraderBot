"""Miner for the oracle-setups study: python/oracle/SPEC.md section 3; prereg python/oracle/prereg/OR-H1.md sections
"Mining (discovery A only)", "Confirmation (discovery B) and freeze" and "Adversary".

    cd python && python3 -m oracle.mine --ct perp --parts <dir> --out out/perp [--top 40] [--beam 500]

Rows. Parts of one contract type (oracle.common.list_parts; DOGE refused). load_dev reads ONLY rows whose horizon ends
by DEV_END: a binary search on the sorted t finds the prefix of rows with t + min(h) <= DEV_END, every array is sliced to
that prefix (the memory-mapped HO-1 rows are never paged in) and the prefix is asserted; each (side, h) then keeps rows
with dev_rows(t, h), ok, stratum >= 0, a finite trade $ and split A (stage 1) or B (stage 2) by sim.split_rows.

Stage 1 (split A), per (scope = each part, and ALL = the parts pooled) x horizon x side:
- items = feature states (sim.items_of) with support >= 1% of the scope's A decisions; strata means are per part
  (per asset) over all its A decisions; residuals r = outcome - stratum mean for the trade $ and the hit flag, so
  uplift(S) = mean over S of r exactly (the residual trick).
- singles and ALL pairs of items from different features from one float32 one-hot item matrix Z (rows x items), built
  in row chunks and never stored whole: counts = Z'Z and sums = Z'(w * Z) for w = residual trade, residual hit, trade,
  residual trade squared (accumulated in float64). The pooled scope sums the per-part matrices.
- triples from the best `--beam` pairs per scope (beam: Z'(w * pairmask) for every pair mask), deduplicated as sets.
- N_raw = every conjunction evaluated (singles + different-feature pairs + distinct triples), per scope cell.
- keep S if n >= 300, mean trade $ > 0, hit uplift > 0; rank by the trade-$ uplift t with a deflated n: perps n x step / h
  (5 / h); Kalshi and tennis the distinct groups (contracts / matches) in S, computed exactly for a shortlist of the
  `--shortlist` best by the undeflated t; exact float64 statistics for the shortlist from bit-packed firing sets; greedy
  Jaccard > 0.5 dedupe against better kept setups; top `--top` per (scope, h, side).
Stage 2 (split B), each kept setup traded exactly (sim.trade_sim: one position at a time per asset, skip while busy; the
primary-exit trade $ and hold from the part), $ per day over every B day (zeros included), p_ev = stationary bootstrap p
of mean daily $ > 0, p_up = the same on daily $ minus the matched random-entry placebo's daily $ (sim.PlaceboPool, 8
seeds), p = max(p_ev, p_up), hit rate vs the matched base (B stratum means). BHY at q = 0.10 over every stage-2 setup of
the contract type. Survivors (BHY pass, hit > matched base, $/day > 0) freeze, at most 10 per scope ranked by B $/day
(tennis: the pooled scope only, freeze_scopes), into frozen.json (canonical JSON, with the deviations it carries) +
frozen.sha256. Adversary on B for each survivor: features one decision staler (the previous row of the same contract),
one decision early (the next row: a lookahead check, should jump), tradeLat, tradeCost, and tradeSettle where present
(Price Prediction's live-executable exit, a sensitivity).
Outputs (--out): stage1.jsonl.gz, confirm.jsonl, frozen.json, frozen.sha256, report.md (aggregates only),
lift/<scope>-<s><h>.csv, instances/<part scope>-<s><h>.csv.gz (every discovery A/B decision with hit = 1 and its feature
states; the pooled scope's instances are the union of its parts'), base_rates.json.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import os
import resource
import subprocess
import sys
import time
import zlib

import numba as nb
import numpy as np

from .common import DEV_END, HORIZONS, MIN, SIDES, SPLITS, STEP_MIN, Part, dev_rows, iso_day, key, list_parts
from .sim import (ArrayPart, PlaceboPool, bhy_adjust, busy_key, daily_vec, fire_mask, items_of, shift_index, side_columns,
                  split_rows, span_days, stationary_bootstrap_test, trade_sim)

POOLED = 'ALL'
LABELS = ('ok', 'hit', 'trade', 'hold', 'best', 'tradeLat', 'tradeCost', 'tradeSettle')
REQUIRED = ('ok', 'hit', 'trade', 'hold')
OPTIONAL = ('rv', 'hour', 'mkt', 'close', 'event', 'kmin', 'tmin')
if sys.byteorder != 'little':                               # the bit-packed firing sets assume it
    raise RuntimeError('oracle.mine needs a little-endian machine')


# ---------------------------------------------------------------- the DEV_END guard

def assert_dev(t, h: int) -> None:
    """Refuse any row whose horizon ends after DEV_END (prereg "Splits": mining / confirmation never load such a row)."""
    t = np.asarray(t, dtype=np.int64)
    if len(t) and not dev_rows(t, h).all():
        raise AssertionError(f'a row with t + {h} min > DEV_END reached the miner')


def load_dev(path: str, ct: str | None = None) -> ArrayPart:
    """The part's dev rows only (t + min(horizons) <= DEV_END), as an in-memory ArrayPart. t must be sorted (SPEC 1); the
    cut is found by binary search on the memory-mapped t, so HO-1 rows are never read."""
    part = Part(path)
    if ct is not None and part.ct != ct:
        raise ValueError(f'{path}: ct {part.ct!r} != {ct!r}')
    if 'DOGE' in str(part.scope).upper() or any('DOGE' in str(a).upper() for a in part.meta.get('assets', [])):
        raise ValueError('DOGE part refused')
    sides = part.meta.get('sides') or SIDES[part.ct]
    hs = [int(h) for h in (part.meta.get('horizons') or HORIZONS[part.ct])]
    hmin = min(hs)
    tm = part['t']
    cut = int(np.searchsorted(tm, DEV_END - hmin * MIN, side='right'))
    t = np.array(tm[:cut], dtype=np.int64)
    if cut > 1 and np.any(np.diff(t) < 0):
        raise ValueError(f'{path}: t is not sorted')
    assert_dev(t, hmin)
    arrays = {'t': t}
    names = ['group', 'asset', 'X'] + [f'stratum_{s}' for s in sides]
    names += [key(nm, s, h) for s in sides for h in hs for nm in LABELS]
    names += list(OPTIONAL)
    for nm in names:
        base = nm.split('_')[0]
        if part.has(nm):
            arrays[nm] = np.array(part[nm][:cut])
        elif nm in ('group', 'asset', 'X') or nm.startswith('stratum_') or base in REQUIRED:
            raise ValueError(f'{path}: missing {nm}.npy')
    X = arrays['X']
    if X.ndim != 2 or X.shape[1] != len(part.features):
        raise ValueError(f'{path}: X shape {X.shape} vs {len(part.features)} features')
    meta = dict(part.meta)
    meta.update({'sides': sides, 'horizons': hs, 'dev_rows': cut, 'rows_total': part.n, 'part_dir': os.path.basename(path)})
    return ArrayPart(meta, arrays, path)


# ---------------------------------------------------------------- numba kernels

@nb.njit(parallel=True, cache=False)
def _value_sums(X, rows, cols, nbins, W, nchunk):
    """Per (column k, value v + 1): sums of W's columns over rows (W[:, 0] = 1 gives the count)."""
    n = len(rows)
    F = len(cols)
    Q = W.shape[1]
    acc = np.zeros((nchunk, F, nbins, Q))
    for c in nb.prange(nchunk):
        lo = c * n // nchunk
        hi = (c + 1) * n // nchunk
        for r in range(lo, hi):
            row = rows[r]
            for k in range(F):
                v = X[row, cols[k]] + 1
                for q in range(Q):
                    acc[c, k, v, q] += W[r, q]
    return acc


@nb.njit(parallel=True, cache=False)
def _exact_stats(B, sets, Wr, gid, ngroups):
    """For each setup (row of up to 3 item indexes, -1 = none): count and sums of Wr's columns over the rows where all
    its items' bits are set in B (U x bytes, little-endian bit order), and the number of distinct gid among them."""
    K = sets.shape[0]
    nbytes = B.shape[1]
    Q = Wr.shape[1]
    out = np.zeros((K, Q + 1))
    grp = np.zeros(K, dtype=np.int64)
    for k in nb.prange(K):
        a = sets[k, 0]
        b = sets[k, 1]
        c = sets[k, 2]
        seen = np.zeros(max(ngroups, 1), dtype=np.bool_)
        acc = np.zeros(Q)
        cnt = 0
        g = 0
        for j in range(nbytes):
            m = np.int64(B[a, j])
            if b >= 0:
                m = m & np.int64(B[b, j])
            if c >= 0:
                m = m & np.int64(B[c, j])
            if m == 0:
                continue
            for bit in range(8):
                if (m >> bit) & 1:
                    r = j * 8 + bit
                    cnt += 1
                    for q in range(Q):
                        acc[q] += Wr[r, q]
                    if ngroups > 0:
                        gg = gid[r]
                        if not seen[gg]:
                            seen[gg] = True
                            g += 1
        out[k, 0] = cnt
        for q in range(Q):
            out[k, q + 1] = acc[q]
        grp[k] = g
    return out, grp


_M1 = np.uint64(0x5555555555555555)
_M2 = np.uint64(0x3333333333333333)
_M4 = np.uint64(0x0F0F0F0F0F0F0F0F)
_H01 = np.uint64(0x0101010101010101)


@nb.njit(inline='always', cache=False)
def _popcnt(x):
    x = x - ((x >> np.uint64(1)) & _M1)
    x = (x & _M2) + ((x >> np.uint64(2)) & _M2)
    x = (x + (x >> np.uint64(4))) & _M4
    return (x * _H01) >> np.uint64(56)


@nb.njit(cache=False)
def _dedupe(Wd, sets, sizes, top, thr):
    """Greedy Jaccard dedupe in rank order: keep a setup unless its firing set overlaps an already kept (better) one by
    Jaccard > thr; stop at `top` kept. Returns the kept positions."""
    K = sets.shape[0]
    nw = Wd.shape[1]
    kept = np.zeros((top, nw), dtype=np.uint64)
    ksz = np.zeros(top)
    kidx = np.empty(top, dtype=np.int64)
    nk = 0
    m = np.empty(nw, dtype=np.uint64)
    for k in range(K):
        a = sets[k, 0]
        b = sets[k, 1]
        c = sets[k, 2]
        for w in range(nw):
            x = Wd[a, w]
            if b >= 0:
                x = x & Wd[b, w]
            if c >= 0:
                x = x & Wd[c, w]
            m[w] = x
        sz = sizes[k]
        dup = False
        for j in range(nk):
            lo = min(sz, ksz[j])
            hi = max(sz, ksz[j])
            if lo <= thr * hi:                      # Jaccard <= min / max <= thr: cannot be a duplicate
                continue
            inter = np.uint64(0)
            for w in range(nw):
                inter += _popcnt(m[w] & kept[j, w])
            fi = float(inter)
            if fi > thr * (sz + ksz[j] - fi):
                dup = True
                break
        if not dup:
            for w in range(nw):
                kept[nk, w] = m[w]
            ksz[nk] = sz
            kidx[nk] = k
            nk += 1
            if nk == top:
                break
    return kidx[:nk]


# ---------------------------------------------------------------- small helpers

class Log:
    def __init__(self, quiet: bool = False):
        self.t0 = time.time()
        self.quiet = quiet

    def __call__(self, msg: str) -> None:
        if not self.quiet:
            print(f'[{time.time() - self.t0:8.1f}s rss {peak_gb():5.2f} GB] {msg}', flush=True)


def peak_gb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 ** 2      # Linux: KB


def clean(x):
    """JSON-safe: numpy scalars -> python, NaN / inf -> None."""
    if isinstance(x, dict):
        return {str(k): clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [clean(v) for v in x]
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating, float)):
        x = float(x)
        return x if math.isfinite(x) else None
    if isinstance(x, np.bool_):
        return bool(x)
    return x


def canonical(obj) -> bytes:
    return json.dumps(clean(obj), sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def setup_id(ct: str, scope: str, side: str, h: int, items: list) -> str:
    body = json.dumps([[i['f'], int(i['v'])] for i in items], separators=(',', ':'))
    return f'{ct}-{scope}-{side}{h}-{hashlib.sha1(body.encode()).hexdigest()[:10]}'


def freeze_scopes(ct: str, scopes: list) -> list:
    """Scopes whose survivors may freeze: every part's scope and the pooled one (when there are several parts); tennis
    the pooled scope only (see run(); a deviation from "at most 10 per (type, scope)", decided before any opening)."""
    pooled = [POOLED] if len(scopes) > 1 else []
    return pooled if ct == 'tennis' else list(scopes) + pooled


def deviations(ct: str, views: list) -> list:
    """Departures from the OR-H1 text that this frozen file carries: the parts' own (meta.deviations) and the miner's."""
    out = sorted({str(d) for v in views for d in (v.meta.get('deviations') or [])})
    if ct == 'tennis':
        out.append('tennis freeze: survivors freeze from the pooled ATP+WTA scope only (single-tour setups have one HO-1 '
                   'stratum, the tour, and cannot pass "2 strata won")')
    return out


def code_sha() -> str:
    try:
        return subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=os.path.dirname(os.path.abspath(__file__)), capture_output=True,
                              text=True, timeout=10).stdout.strip() or 'unknown'
    except Exception:
        return 'unknown'


def t_of(n, srt, sq, n_eff):
    """Vectorised trade-$ uplift t: mean residual / sqrt(var / n_eff)."""
    n = np.asarray(n, dtype=np.float64)
    with np.errstate(divide='ignore', invalid='ignore'):
        mean = srt / n
        var = np.maximum((sq - n * mean * mean) / np.maximum(n - 1, 1), 1e-12)
        t = mean / np.sqrt(var / np.maximum(n_eff, 1e-12))
    return np.where(n > 1, t, 0.0)


# ---------------------------------------------------------------- per (part, side, h) rows

class PartCell:
    """One part's rows for one (side, h): discovery A arrays (residuals vs per-part A strata means) and B indexes."""

    def __init__(self, v: ArrayPart, side: str, h: int):
        self.v, self.side, self.h = v, side, h
        t = v['t']
        split = split_rows(v, h)
        tr = v[key('trade', side, h)].astype(np.float64)
        st = v[f'stratum_{side}'].astype(np.int64)
        ok = (v[key('ok', side, h)] == 1) & (st >= 0) & np.isfinite(tr) & dev_rows(t, h)
        self.A = np.flatnonzero(ok & (split == 'A'))
        self.B = np.flatnonzero(ok & (split == 'B'))
        assert_dev(t[self.A], h)
        assert_dev(t[self.B], h)
        hit = v[key('hit', side, h)].astype(np.float64)
        S = int(st.max()) + 1 if len(st) and st.max() >= 0 else 1
        a = self.A
        self.trade, self.hit, self.st = tr[a], hit[a], st[a]
        cnt = np.bincount(self.st, minlength=S).astype(np.float64)
        self.mt = np.bincount(self.st, self.trade, S) / np.maximum(cnt, 1)
        self.mh = np.bincount(self.st, self.hit, S) / np.maximum(cnt, 1)
        self.cntA = cnt
        self.rt = self.trade - self.mt[self.st]
        self.rh = self.hit - self.mh[self.st]
        b = self.B
        cb = np.bincount(st[b], minlength=S).astype(np.float64)
        self.cntB = cb
        self.mtB = np.bincount(st[b], tr[b], S) / np.maximum(cb, 1)
        self.mhB = np.bincount(st[b], hit[b], S) / np.maximum(cb, 1)
        self.nA = len(a)
        _, gid = np.unique(v['group'][a], return_inverse=True)
        self.gid = gid.astype(np.int64)
        self.ngroups = int(gid.max()) + 1 if len(gid) else 0
        self.items = items_of(v, side)
        self.cols = np.array(sorted({it.col for it in self.items}), dtype=np.int64)
        self.sums = None          # {(f, v): [n, srt, srh, strade, srt2, shit]}

    def value_sums(self) -> dict:
        """Single-item sufficient statistics for every candidate item (one numba pass over the A rows)."""
        if self.sums is not None:
            return self.sums
        X = self.v['X']
        feats = self.v.meta['features']
        nb_ = 3
        for j in self.cols:
            lv = feats[j]['levels']
            nb_ = max(nb_, int(max(lv)) + 2)
        if self.nA:
            xs = X[self.A][:, self.cols]
            if xs.size and (xs.min() < -1 or xs.max() > nb_ - 2):
                raise ValueError(f'{self.v.path}: X values outside the declared levels')
        W = np.stack([np.ones(self.nA), self.rt, self.rh, self.trade, self.rt * self.rt, self.hit], axis=1)
        nchunk = max(1, min(64, nb.get_num_threads() * 4, self.nA // 1000 + 1))
        acc = _value_sums(X, self.A.astype(np.int64), self.cols, nb_, W, nchunk).sum(axis=0) if self.nA else \
            np.zeros((len(self.cols), nb_, 6))
        pos = {int(c): k for k, c in enumerate(self.cols)}
        self.sums = {(it.f, it.v): acc[pos[it.col], it.v + 1].copy() for it in self.items}
        return self.sums


# ---------------------------------------------------------------- stage 1

def z_chunks(pc: PartCell, colU, valU, chunk: int):
    """(row offset, bool Z chunk) over the cell's A rows: Z[r, u] = item u holds on row r (False where the part lacks
    the feature)."""
    X = pc.v['X']
    present = colU >= 0
    cs = np.where(present, colU, 0)
    for c0 in range(0, pc.nA, chunk):
        r = pc.A[c0:c0 + chunk]
        yield c0, (X[r][:, cs] == valU[None, :]) & present[None, :]


def pass_pairs(pc: PartCell, colU, valU, chunk: int):
    """Counts and weighted sums of every item pair (5, U, U) float64, and the bit-packed item firing sets (U, bytes)."""
    U = len(colU)
    P = np.zeros((5, U, U))
    nbytes = -(-pc.nA // 64) * 8
    packed = np.zeros((U, nbytes), dtype=np.uint8)
    w = np.stack([pc.rt, pc.rh, pc.trade, pc.rt * pc.rt], axis=1).astype(np.float32)
    for c0, Zb in z_chunks(pc, colU, valU, chunk):
        Z = Zb.astype(np.float32)
        wc = w[c0:c0 + len(Z)]
        P[0] += Z.T @ Z
        for q in range(4):
            P[q + 1] += Z.T @ (Z * wc[:, q:q + 1])
        pb = np.packbits(Zb, axis=0, bitorder='little').T
        packed[:, c0 // 8:c0 // 8 + pb.shape[1]] = pb
    return P, packed


def pass_triples(pc: PartCell, colU, valU, pairs, chunk: int):
    """Counts and weighted sums of (item c) x (pair k) (5, U, K): the beam Z'(w * pairmask)."""
    U, K = len(colU), len(pairs)
    P3 = np.zeros((5, U, K))
    if K == 0:
        return P3
    pa, pb = pairs[:, 0], pairs[:, 1]
    w = np.stack([pc.rt, pc.rh, pc.trade, pc.rt * pc.rt], axis=1).astype(np.float32)
    for c0, Zb in z_chunks(pc, colU, valU, chunk):
        Z = Zb.astype(np.float32)
        M = Z[:, pa] * Z[:, pb]
        wc = w[c0:c0 + len(Z)]
        P3[0] += Z.T @ M
        for q in range(4):
            P3[q + 1] += Z.T @ (M * wc[:, q:q + 1])
    return P3


class ScopeCell:
    """One (scope, side, h): its parts, items (U indexes), candidate conjunctions and results."""

    def __init__(self, name: str, parts: list):
        self.name, self.parts = name, parts
        self.sidx = None
        self.cands = None
        self.beam = np.zeros((0, 2), dtype=np.int64)
        self.n_raw = {'singles': 0, 'pairs': 0, 'triples': 0}
        self.kept = []


def score_prelim(st, ct, step, h, min_n):
    """(valid, preliminary t) from stats rows [n, srt, srh, strade, srt2]."""
    n = np.rint(st[0])
    with np.errstate(divide='ignore', invalid='ignore'):
        valid = (n >= min_n) & (st[3] / n > 0) & (st[2] / n > 0)
    fac = step / h if ct == 'perp' else 1.0
    return valid, t_of(n, st[1], st[4], n * fac)


def mine_cell(views, scopes, ct, side, h, a, log):
    """Stage 1 for one (side, h) over every scope. Returns (setups, cell summaries, lift tables, part cells)."""
    t0 = time.time()
    pcs = [PartCell(v, side, h) for v in views]
    nA = [pc.nA for pc in pcs]
    log(f'cell {side}{h}: A rows {nA}, B rows {[len(pc.B) for pc in pcs]}')
    sums = [pc.value_sums() for pc in pcs]
    # item universe: supported (>= support x A decisions) in some part scope or in the pooled scope
    keys, fname = [], {}
    for pc in pcs:
        for it in pc.items:
            if (it.f, it.v) not in fname:
                fname[(it.f, it.v)] = it.f
                keys.append((it.f, it.v))
    nk = lambda s, k_: float(s[k_][0]) if k_ in s else 0.0
    sup_scope = {}
    for sc in scopes:
        tot = sum(nA[p] for p in sc.parts)
        sup_scope[sc.name] = [k_ for k_ in keys if tot > 0 and sum(nk(sums[p], k_) for p in sc.parts) >= a.support * tot]
    in_any = set().union(*[set(v) for v in sup_scope.values()]) if sup_scope else set()
    U_keys = [k_ for k_ in keys if k_ in in_any]
    U = len(U_keys)
    uidx = {k_: i for i, k_ in enumerate(U_keys)}
    feat_names = sorted({k_[0] for k_ in U_keys})
    fid = np.array([feat_names.index(k_[0]) for k_ in U_keys], dtype=np.int64)
    valU = np.array([k_[1] for k_ in U_keys], dtype=np.int8)
    colUs = []
    for pc in pcs:
        cmap = {(it.f, it.v): it.col for it in pc.items}
        colUs.append(np.array([cmap.get(k_, -1) for k_ in U_keys], dtype=np.int64))
    for sc in scopes:
        sc.sidx = np.array(sorted(uidx[k_] for k_ in sup_scope[sc.name]), dtype=np.int64)
    log(f'cell {side}{h}: {len(keys)} candidate items, universe {U}, supported per scope '
        f'{ {sc.name: len(sc.sidx) for sc in scopes} }')

    # pass 1: pair matrices per part (pooled = their sum) and bit-packed firing sets
    Pp, packs = [], []
    for p, pc in enumerate(pcs):
        tp = time.time()
        P, pk = pass_pairs(pc, colUs[p], valU, a.chunk)
        Pp.append(P)
        packs.append(pk)
        log(f'  pass 1 {pc.v.scope}: {pc.nA} rows x {U} items in {time.time() - tp:.1f}s')
    step = float(views[0].meta.get('step_min') or STEP_MIN[ct])
    for sc in scopes:
        P = Pp[sc.parts[0]] if len(sc.parts) == 1 else np.sum([Pp[p] for p in sc.parts], axis=0)
        s = sc.sidx
        single = np.stack([s, -np.ones_like(s), -np.ones_like(s)], 1)
        st1 = P[:, s, s]
        iu, ju = np.triu_indices(len(s), 1)
        pa, pb = s[iu], s[ju]
        df = fid[pa] != fid[pb]
        pa, pb = pa[df], pb[df]
        st2 = P[:, pa, pb]
        sc.n_raw['singles'], sc.n_raw['pairs'] = int(len(s)), int(len(pa))
        valid2, t2 = score_prelim(st2, ct, step, h, a.min_n)
        order = np.argsort(-np.where(valid2, t2, -np.inf), kind='stable')
        order = order[valid2[order]][:a.beam]
        sc.beam = np.stack([pa[order], pb[order]], 1).astype(np.int64)
        sc.cands = [(single, st1), (np.stack([pa, pb, -np.ones_like(pa)], 1), st2)]
    del Pp

    # pass 2: triples from each scope's beam (per part: the union of the beams of the scopes it belongs to)
    for p, pc in enumerate(pcs):
        mine = [sc for sc in scopes if p in sc.parts and len(sc.beam)]
        if not mine:
            continue
        allp = np.concatenate([sc.beam for sc in mine])
        code = allp[:, 0] * U + allp[:, 1]
        ucode, inv = np.unique(code, return_inverse=True)
        upairs = np.stack([ucode // U, ucode % U], 1)
        tp = time.time()
        P3 = pass_triples(pc, colUs[p], valU, upairs, a.chunk)
        off = 0
        for sc in mine:
            cols = inv[off:off + len(sc.beam)]
            off += len(sc.beam)
            part3 = P3[:, :, cols]
            sc._p3 = part3 if getattr(sc, '_p3', None) is None else sc._p3 + part3
        log(f'  pass 2 {pc.v.scope}: {len(upairs)} beam pairs in {time.time() - tp:.1f}s')
    for sc in scopes:
        P3 = getattr(sc, '_p3', None)
        sc._p3 = None
        if P3 is None or not len(sc.beam):
            continue
        C = sc.sidx
        ba, bb = sc.beam[:, 0], sc.beam[:, 1]
        ok3 = (fid[C][None, :] != fid[ba][:, None]) & (fid[C][None, :] != fid[bb][:, None])
        kk, cc = np.nonzero(ok3)
        tri = np.sort(np.stack([ba[kk], bb[kk], C[cc]], 1), axis=1)
        code = (tri[:, 0] * U + tri[:, 1]) * U + tri[:, 2]
        _, first = np.unique(code, return_index=True)
        st3 = P3[:, C[cc[first]], kk[first]]
        sc.cands.append((tri[first], st3))
        sc.n_raw['triples'] = int(len(first))

    # shortlist, exact statistics, deflated t, Jaccard dedupe, top
    setups, summaries = [], {}
    kalshi = ct != 'perp'
    for sc in scopes:
        sets = np.concatenate([c[0] for c in sc.cands]).astype(np.int64)
        stats = np.concatenate([c[1] for c in sc.cands], axis=1)
        valid, tpre = score_prelim(stats, ct, step, h, a.min_n)
        order = np.argsort(-np.where(valid, tpre, -np.inf), kind='stable')
        short = order[valid[order]][:a.shortlist]
        B, Wr, gid, ng = scope_rows(pcs, sc.parts, packs)
        ex, grp = _exact_stats(B, sets[short], Wr, gid, ng if kalshi else 0) if len(short) else \
            (np.zeros((0, 6)), np.zeros(0, dtype=np.int64))
        n = ex[:, 0]
        n_eff = grp.astype(np.float64) if kalshi else n * step / h
        t = t_of(n, ex[:, 1], ex[:, 4], n_eff)
        with np.errstate(divide='ignore', invalid='ignore'):
            good = (n >= a.min_n) & (ex[:, 3] / n > 0) & (ex[:, 2] / n > 0)
        o = np.argsort(-np.where(good, t, -np.inf), kind='stable')
        o = o[good[o]]
        keep = _dedupe(B.view(np.uint64), sets[short][o], n[o], a.top, a.jaccard) if len(o) else np.zeros(0, np.int64)
        for rank, j in enumerate(o[keep], 1):
            items = sorted([{'f': U_keys[u][0], 'v': int(U_keys[u][1])} for u in sets[short][j] if u >= 0],
                           key=lambda d: (d['f'], d['v']))
            nn = float(n[j])
            A = {'n': int(nn), 'hit': ex[j, 5] / nn, 'base_hit': (ex[j, 5] - ex[j, 2]) / nn, 'ev': ex[j, 3] / nn,
                 'uplift': ex[j, 1] / nn, 'hit_uplift': ex[j, 2] / nn, 't': float(t[j]), 'n_eff': float(n_eff[j]),
                 'sd': math.sqrt(max((ex[j, 4] - nn * (ex[j, 1] / nn) ** 2) / max(nn - 1, 1), 0.0)),
                 'shortlist_rank': int(np.flatnonzero(o == j)[0]) + 1}
            if kalshi:
                A['groups'] = int(grp[j])
            setups.append({'id': setup_id(ct, sc.name, side, h, items), 'ct': ct, 'scope': sc.name, 'side': side,
                           'h': int(h), 'items': items, 'k': len(items), 'rank': rank, 'dev': {'A': A}})
        tot = sum(sc.n_raw.values())
        summaries[f'{sc.name}-{side}{h}'] = {
            'scope': sc.name, 'side': side, 'h': h, 'rows_A': int(sum(nA[p] for p in sc.parts)),
            'items_candidate': len({(it.f, it.v) for p in sc.parts for it in pcs[p].items}),
            'items_supported': int(len(sc.sidx)), 'N_raw': {**sc.n_raw, 'total': tot}, 'valid': int(valid.sum()),
            'shortlist': int(len(short)), 'kept': int(len(keep))}
        log(f'  scope {sc.name} {side}{h}: N_raw {tot} (items {sc.n_raw["singles"]}, pairs {sc.n_raw["pairs"]}, '
            f'triples {sc.n_raw["triples"]}), valid {int(valid.sum())}, kept {len(keep)}')
        sc.cands = None
        del B, Wr, gid
    lifts = {sc.name: lift_table(pcs, sc.parts, sup_scope[sc.name], ct, step, h) for sc in scopes}
    log(f'cell {side}{h} done in {time.time() - t0:.1f}s')
    return setups, summaries, lifts, pcs


def scope_rows(pcs, parts, packs):
    """A scope's bit-packed firing sets (U x bytes, parts side by side) and row weights [rt, rh, trade, rt^2, hit]
    padded to the packed length, with group ids made distinct across parts."""
    if len(parts) == 1:
        p = parts[0]
        pc, B = pcs[p], packs[p]
        L = B.shape[1] * 8
        Wr = np.zeros((L, 5))
        Wr[:pc.nA] = np.stack([pc.rt, pc.rh, pc.trade, pc.rt * pc.rt, pc.hit], 1)
        gid = np.zeros(L, dtype=np.int64)
        gid[:pc.nA] = pc.gid
        return np.ascontiguousarray(B), Wr, gid, pc.ngroups
    Bs, Ws, gs, off = [], [], [], 0
    for p in parts:
        pc, B = pcs[p], packs[p]
        L = B.shape[1] * 8
        W = np.zeros((L, 5))
        W[:pc.nA] = np.stack([pc.rt, pc.rh, pc.trade, pc.rt * pc.rt, pc.hit], 1)
        g = np.zeros(L, dtype=np.int64)
        g[:pc.nA] = pc.gid + off
        off += pc.ngroups
        Bs.append(B)
        Ws.append(W)
        gs.append(g)
    return np.ascontiguousarray(np.concatenate(Bs, axis=1)), np.concatenate(Ws), np.concatenate(gs), off


def lift_table(pcs, parts, supported, ct, step, h) -> list:
    """Single-item lift rows for a scope (every candidate item seen in its A rows)."""
    acc = {}
    for p in parts:
        for k_, s in pcs[p].value_sums().items():
            acc[k_] = acc.get(k_, 0) + s
    tot = sum(pcs[p].nA for p in parts)
    sup = set(supported)
    rows = []
    for (f, v), s in acc.items():
        n = float(s[0])
        if n <= 0:
            continue
        fac = step / h if ct == 'perp' else 1.0
        t = float(t_of(np.array([n]), np.array([s[1]]), np.array([s[4]]), np.array([n * fac]))[0])
        rows.append({'f': f, 'v': int(v), 'n': int(n), 'support': n / tot, 'hit': s[5] / n, 'base_hit': (s[5] - s[2]) / n,
                     'hit_uplift': s[2] / n, 'ev': s[3] / n, 'uplift': s[1] / n,
                     't' if ct == 'perp' else 't_undeflated': t, 'supported': (f, v) in sup})
    rows.sort(key=lambda r: -r['uplift'])
    return rows


# ---------------------------------------------------------------- stage 2

class PartB:
    """One part's B rows for one (side, h), with what trading, the placebo and the matched base need."""

    def __init__(self, pc: PartCell):
        v, side, h = pc.v, pc.side, pc.h
        self.v, self.pc = v, pc
        self.B = pc.B
        self.t = v['t']
        self.trade = v[key('trade', side, h)].astype(np.float64)
        self.hit = v[key('hit', side, h)].astype(np.float64)
        self.hold = v[key('hold', side, h)].astype(np.float64)
        self.st = v[f'stratum_{side}'].astype(np.int64)
        self.busy = busy_key(v)
        self.pool = PlaceboPool(v, side, h)
        self._shift = None

    def shift(self):
        if self._shift is None:
            self._shift = shift_index(self.v)
        return self._shift

    def trade_on(self, fire_all, trade=None):
        """Taken B rows (part row indexes) when the setup fires per `fire_all` (over every dev row)."""
        B = self.B
        tr = self.trade if trade is None else trade
        rel = trade_sim(self.t[B], self.hold[B], tr[B], fire_all[B], self.busy[B])
        return B[rel]


def confirm(setup, pbs, span, a, seed):
    """Stage 2 statistics of one setup over its scope's parts (pbs)."""
    nd = span_days(span)[1] - span_days(span)[0]
    daily, plac = np.zeros(nd), np.zeros(nd)
    trades, hits, base = 0, 0.0, 0.0
    info = {'same_day': 0, 'fallback': 0, 'unmatched': 0}
    for pb in pbs:
        fire = np.zeros(pb.v.n, dtype=bool)
        fire[pb.B] = fire_mask(pb.v, setup, pb.B)
        rows = pb.trade_on(fire)
        if not len(rows):
            continue
        daily += daily_vec(pb.t[rows], pb.trade[rows], span)
        pv, inf = pb.pool.draw(rows, a.seeds, seed)
        for k_ in info:
            info[k_] += inf[k_]
        plac += daily_vec(pb.t[rows], pv, span)
        trades += len(rows)
        hits += float(pb.hit[rows].sum())
        base += float(pb.pc.mhB[pb.st[rows]].sum())
    ev = stationary_bootstrap_test(daily, a.block, a.draws, seed)
    up = stationary_bootstrap_test(daily - plac, a.block, a.draws, seed + 1)
    return {'trades': trades, 'days': nd, 'active_days': int(np.count_nonzero(daily)), 'usd_day': float(daily.mean()),
            'usd_total': float(daily.sum()), 'placebo_usd_day': float(plac.mean()),
            'hit': hits / trades if trades else None, 'base_hit': base / trades if trades else None,
            'p_ev': ev['p'], 'p_up': up['p'], 'p': max(ev['p'], up['p']), 'p_ev_emp': ev['p_emp'], 'p_up_emp': up['p_emp'],
            'placebo': info}


def adversary(setup, pbs, span, a):
    """B $/day of the survivor under the prereg adversaries (features staler / early by one decision of the same
    contract, +1 decision entry latency, cost stress), plus 'settle' where the part has tradeSettle (Price Prediction:
    the live-executable exit that settles instead of selling at the final candle; sensitivity only, None elsewhere)."""
    nd = span_days(span)[1] - span_days(span)[0]
    out = {}
    fires = [fire_mask(pb.v, setup) for pb in pbs]          # over every dev row, so a shifted row may come from A
    for name in ('base', 'stale', 'early', 'lat', 'cost', 'settle'):
        daily = np.zeros(nd)
        trades = 0
        missing = False
        for pb, f in zip(pbs, fires):
            trade = None
            if name in ('stale', 'early'):
                prev, nxt = pb.shift()
                src = prev if name == 'stale' else nxt
                g = np.zeros_like(f)
                g[src >= 0] = f[src[src >= 0]]
                f = g
            elif name in ('lat', 'cost', 'settle'):
                arr = key({'lat': 'tradeLat', 'cost': 'tradeCost', 'settle': 'tradeSettle'}[name], setup['side'], setup['h'])
                if not pb.v.has(arr):
                    missing = True
                    continue
                trade = pb.v[arr].astype(np.float64)
            rows = pb.trade_on(f, trade)
            tr = pb.trade if trade is None else trade
            daily += daily_vec(pb.t[rows], tr[rows], span)
            trades += len(rows)
        out[name] = None if missing else {'usd_day': float(daily.mean()), 'trades': trades}
    b, e = out['base'], out['early']
    out['early_jump'] = bool(e['usd_day'] > b['usd_day']) if b and e else None
    out['stale_holds'] = bool(out['stale']['usd_day'] > 0) if out['stale'] else None
    return out


# ---------------------------------------------------------------- outputs

def write_csv(path: str, rows: list, cols: list, gz: bool = False) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    op = gzip.open if gz else open
    with op(path, 'wt') as f:
        f.write(','.join(cols) + '\n')
        for r in rows:
            f.write(','.join('' if r.get(c) is None else (f'{r[c]:.6g}' if isinstance(r[c], float) else str(r[c])) for c in cols)
                    + '\n')


_LUT = np.array([f'{v},'.encode() for v in range(-1, 128)], dtype='S4')       # X value v at index v + 1
_LUT_END = np.array([f'{v}\n'.encode() for v in range(-1, 128)], dtype='S4')


def write_instances(path: str, pc: PartCell, chunk: int = 20000) -> int:
    """Every discovery (A and B) decision of this part / side / h with hit = 1, with its feature states (gzip CSV; the
    int8 feature block is formatted by table lookup, not per cell)."""
    v, side, h = pc.v, pc.side, pc.h
    rows = np.concatenate([pc.A, pc.B])
    rows = np.sort(rows[v[key('hit', side, h)][rows] == 1])
    cols = side_columns(v.meta, side)
    cidx = list(cols.values())
    split = split_rows(v, h)
    best = v[key('best', side, h)] if v.has(key('best', side, h)) else None
    t, grp, st = v['t'], v['group'], v[f'stratum_{side}']
    tr, hd = v[key('trade', side, h)], v[key('hold', side, h)]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    head = ['t', 'day', 'split', 'group', 'stratum', 'trade', 'best', 'hold'] + list(cols.keys())
    with gzip.open(path, 'wb', compresslevel=5) as f:
        f.write((','.join(head) + '\n').encode())
        for c0 in range(0, len(rows), chunk):
            r = rows[c0:c0 + chunk]
            pre = [f'{int(t[i])},{iso_day(int(t[i]))},{split[i]},{int(grp[i])},{int(st[i])},{float(tr[i]):.4f},'
                   f'{"" if best is None else format(float(best[i]), ".4f")},{int(hd[i])}' for i in r]
            if not cidx:
                f.write(''.join(p_ + '\n' for p_ in pre).encode())
                continue
            Xi = v['X'][r][:, cidx].astype(np.int16) + 1
            if Xi.min() < 0 or Xi.max() > 128:
                raise ValueError('X value outside int8 states / levels')
            A = _LUT[Xi]
            A[:, -1] = _LUT_END[Xi[:, -1]]
            lines = np.ascontiguousarray(A).view(f'S{4 * len(cidx)}').ravel()
            f.write(b''.join(p_.encode() + b',' + ln.replace(b'\x00', b'') for p_, ln in zip(pre, lines)))
    return int(len(rows))


def base_rates(pc: PartCell) -> dict:
    out = {}
    for name, cnt, mt, mh in (('A', pc.cntA, pc.mt, pc.mh), ('B', pc.cntB, pc.mtB, pc.mhB)):
        n = float(cnt.sum())
        out[name] = {'rows': int(n), 'hit': float((mh * cnt).sum() / n) if n else None,
                     'ev': float((mt * cnt).sum() / n) if n else None,
                     'strata': {str(s): {'n': int(cnt[s]), 'hit': float(mh[s]), 'ev': float(mt[s])}
                                for s in range(len(cnt)) if cnt[s] > 0}}
    return out


def report_md(ct, a, summaries, confirmed, frozen, timing, n_raw) -> str:
    L = [f'# Oracle miner: {ct}', '', 'Prereg python/oracle/prereg/OR-H1.md; SPEC 3. Aggregates only (no rows).', '',
         f'Parameters: top {a.top}, beam {a.beam}, shortlist {a.shortlist}, min n {a.min_n}, support {a.support}, '
         f'Jaccard {a.jaccard}, bootstrap block {a.block} days x {a.draws} draws, placebo seeds {a.seeds}, BHY q {a.q}.', '',
         f'N_raw (every conjunction evaluated, all cells): **{n_raw}**. Stage-2 setups (BHY m): **{len(confirmed)}**. '
         f'BHY passes: **{sum(1 for c in confirmed if c["bhy_pass"])}**. Survivors: '
         f'**{sum(1 for c in confirmed if c["survivor"])}**. Frozen: **{len(frozen)}**.', '',
         '## Stage 1 cells', '', '| cell | A rows | items | N_raw | valid | kept |', '|---|---|---|---|---|---|']
    for k_, s in summaries.items():
        L.append(f'| {k_} | {s["rows_A"]} | {s["items_supported"]} | {s["N_raw"]["total"]} | {s["valid"]} | {s["kept"]} |')
    L += ['', '## Stage 2 by cell', '', '| cell | setups | B $/day best | min p | BHY pass | survivors |', '|---|---|---|---|---|---|']
    by = {}
    for c in confirmed:
        by.setdefault(f'{c["scope"]}-{c["side"]}{c["h"]}', []).append(c)
    for k_, cs in by.items():
        L.append(f'| {k_} | {len(cs)} | {max(c["dev"]["B"]["usd_day"] for c in cs):+.3f} | '
                 f'{min(c["dev"]["B"]["p"] for c in cs):.2g} | {sum(c["bhy_pass"] for c in cs)} | {sum(c["survivor"] for c in cs)} |')
    L += ['', '## Frozen setups', '']
    if frozen:
        L += ['| rank | id | items | A n / EV / uplift / t | B trades / $ per day / hit vs base / p / p_bhy | adversary $/day '
              'stale / early / lat / cost |', '|---|---|---|---|---|---|']
        for s in frozen:
            A, B, ad = s['dev']['A'], s['dev']['B'], s.get('adversary') or {}
            g = lambda n_: f'{ad[n_]["usd_day"]:+.3f}' if ad.get(n_) else 'n/a'
            items = ' & '.join(f'{i["f"]}={i["v"]}' for i in s['items'])
            L.append(f'| {s["rank"]} | {s["id"]} | {items} | {A["n"]} / {A["ev"]:+.3f} / {A["uplift"]:+.3f} / {A["t"]:.1f} | '
                     f'{B["trades"]} / {B["usd_day"]:+.3f} / {B["hit"]:.3f} vs {B["base_hit"]:.3f} / {B["p"]:.2g} / '
                     f'{s["p_bhy"]:.2g} | {g("stale")} / {g("early")} / {g("lat")} / {g("cost")} |')
    else:
        L.append('None: no setup of this contract type passed BHY at q = 0.10 with hit rate above the matched base.')
    L += ['', '## Timing', '', '| step | seconds |', '|---|---|'] + [f'| {k_} | {v:.1f} |' for k_, v in timing.items()]
    L += ['', f'Peak RSS {peak_gb():.2f} GB.', '']
    return '\n'.join(L)


# ---------------------------------------------------------------- driver

def run(a) -> dict:
    log = Log(a.quiet)
    ct = a.ct
    timing = {}
    t0 = time.time()
    paths = list_parts(a.parts, ct)
    if not paths:
        raise SystemExit(f'no {ct}-* parts under {a.parts}')
    views = [load_dev(p, ct) for p in paths]
    names = [v.scope for v in views]
    if len(set(names)) != len(names) or POOLED in names:
        raise ValueError(f'scope names must be distinct and not {POOLED!r}: {names}')
    log(f'{ct}: {len(views)} parts {names}; dev rows {[v.meta["dev_rows"] for v in views]} of '
        f'{[v.meta["rows_total"] for v in views]} (rows with t + h > DEV_END are never read)')
    timing['load'] = time.time() - t0
    os.makedirs(a.out, exist_ok=True)
    sides, hs = views[0].meta['sides'], views[0].meta['horizons']

    stage1, summaries, cells = [], {}, {}
    brates = {'ct': ct, 'cells': {}, 'parts': {}}
    t1 = time.time()
    for h in hs:
        for side in sides:
            scopes = [ScopeCell(v.scope, [i]) for i, v in enumerate(views)]
            if len(views) > 1:
                scopes.append(ScopeCell(POOLED, list(range(len(views)))))
            setups, summ, lifts, pcs = mine_cell(views, scopes, ct, side, h, a, log)
            stage1 += setups
            summaries.update(summ)
            cells[(side, h)] = (scopes, pcs)
            for sc, rows in lifts.items():
                write_csv(os.path.join(a.out, 'lift', f'{sc}-{side}{h}.csv'), rows,
                          ['f', 'v', 'n', 'support', 'hit', 'base_hit', 'hit_uplift', 'ev', 'uplift',
                           't' if ct == 'perp' else 't_undeflated', 'supported'])
            for pc in pcs:
                n_inst = write_instances(os.path.join(a.out, 'instances', f'{pc.v.scope}-{side}{h}.csv.gz'), pc)
                brates['parts'][f'{pc.v.scope}-{side}{h}'] = {**base_rates(pc), 'instances': n_inst}
            for k_, s in summ.items():
                brates['cells'][k_] = s
    timing['stage1'] = time.time() - t1
    n_raw = int(sum(s['N_raw']['total'] for s in summaries.values()))
    with gzip.open(os.path.join(a.out, 'stage1.jsonl.gz'), 'wt') as f:
        for s in stage1:
            f.write(json.dumps(clean(s)) + '\n')
    log(f'stage 1: {len(stage1)} setups kept, N_raw {n_raw}')

    # stage 2
    t2 = time.time()
    spanB = SPLITS[ct]['B']
    pbs = {}
    for (side, h), (scopes, pcs) in cells.items():
        pbs[(side, h)] = [PartB(pc) for pc in pcs]
    scope_parts = {(sc.name, side, h): sc.parts for (side, h), (scopes, _) in cells.items() for sc in scopes}
    confirmed = []
    for i, s in enumerate(stage1):
        seed = (zlib.crc32(s['id'].encode()) ^ a.seed) & 0x7FFFFFFF
        parts = scope_parts[(s['scope'], s['side'], s['h'])]
        s = dict(s)
        s['dev'] = dict(s['dev'])
        s['dev']['B'] = confirm(s, [pbs[(s['side'], s['h'])][p] for p in parts], spanB, a, seed)
        confirmed.append(s)
        if (i + 1) % 100 == 0:
            log(f'  stage 2: {i + 1}/{len(stage1)}')
    adj = bhy_adjust([c['dev']['B']['p'] for c in confirmed])
    for c, pa in zip(confirmed, adj):
        B = c['dev']['B']
        c['p_bhy'] = float(pa)
        c['bhy_pass'] = bool(pa <= a.q)
        c['survivor'] = bool(c['bhy_pass'] and B['trades'] > 0 and B['usd_day'] > 0 and B['hit'] is not None
                             and B['hit'] > B['base_hit'])
    timing['stage2'] = time.time() - t2
    log(f'stage 2: {len(confirmed)} setups, BHY passes {sum(c["bhy_pass"] for c in confirmed)}, survivors '
        f'{sum(c["survivor"] for c in confirmed)}')

    # freeze: at most max_frozen per scope by B $/day, adversary beside each. Tennis freezes from the pooled scope only:
    # its HO-1 strata are the tours (prereg "HO-1": "tennis: tour"), so a single-tour setup has one stratum and can never
    # meet registry ho1_pass's "2 strata won"; freezing it would spend a slot and raise the HO-1 BHY m for nothing.
    t3 = time.time()
    frozen = []
    for sc_name in freeze_scopes(ct, [v.scope for v in views]):
        surv = sorted([c for c in confirmed if c['survivor'] and c['scope'] == sc_name], key=lambda c: -c['dev']['B']['usd_day'])
        for r, c in enumerate(surv[:a.max_frozen], 1):
            c['frozen'] = True
            c['rank_scope'] = r
            frozen.append(c)
    for c in confirmed:
        c.setdefault('frozen', False)
        if c['survivor']:
            parts = scope_parts[(c['scope'], c['side'], c['h'])]
            c['adversary'] = adversary(c, [pbs[(c['side'], c['h'])][p] for p in parts], spanB, a)
    frozen.sort(key=lambda c: -c['dev']['B']['usd_day'])
    fz = []
    for r, c in enumerate(frozen, 1):
        d = {k_: c[k_] for k_ in ('id', 'ct', 'scope', 'side', 'h', 'items', 'k', 'dev', 'p_bhy', 'rank_scope', 'adversary')}
        d['rank'] = r
        d['rank_A'] = c['rank']
        fz.append(d)
    timing['freeze'] = time.time() - t3
    with open(os.path.join(a.out, 'confirm.jsonl'), 'w') as f:
        for c in confirmed:
            f.write(json.dumps(clean(c)) + '\n')
    doc = {'schema': 'oracle-frozen-1', 'ct': ct, 'prereg': 'python/oracle/prereg/OR-H1.md', 'code_sha': a.code_sha or code_sha(),
           'parts': [{'dir': v.meta['part_dir'], 'scope': v.scope, 'code_sha': v.meta.get('code_sha'),
                      'rows_total': v.meta['rows_total'], 'dev_rows': v.meta['dev_rows']} for v in views],
           'params': {k_: getattr(a, k_) for k_ in ('top', 'beam', 'shortlist', 'min_n', 'support', 'jaccard', 'block',
                                                    'draws', 'seeds', 'q', 'max_frozen', 'seed')},
           'N_raw': n_raw, 'm_confirmed': len(confirmed), 'bhy_q': a.q,
           'freeze_scopes': freeze_scopes(ct, [v.scope for v in views]),
           'deviations': deviations(ct, views), 'setups': fz}
    body = canonical(doc)
    with open(os.path.join(a.out, 'frozen.json'), 'wb') as f:
        f.write(body)
    sha = hashlib.sha256(body).hexdigest()
    with open(os.path.join(a.out, 'frozen.sha256'), 'w') as f:
        f.write(f'{sha}  frozen.json\n')
    timing['total'] = time.time() - t0
    brates['run'] = {'N_raw': n_raw, 'stage1_setups': len(stage1), 'confirmed': len(confirmed),
                     'bhy_pass': sum(c['bhy_pass'] for c in confirmed), 'survivors': sum(c['survivor'] for c in confirmed),
                     'frozen': len(fz), 'frozen_sha256': sha, 'timing_s': timing, 'peak_rss_gb': peak_gb()}
    with open(os.path.join(a.out, 'base_rates.json'), 'w') as f:
        json.dump(clean(brates), f, indent=1)
    with open(os.path.join(a.out, 'report.md'), 'w') as f:
        f.write(report_md(ct, a, summaries, confirmed, fz, timing, n_raw))
    log(f'frozen {len(fz)} setups, sha256 {sha}; outputs in {a.out}; total {timing["total"]:.1f}s, peak RSS {peak_gb():.2f} GB')
    return {'stage1': stage1, 'confirmed': confirmed, 'frozen': doc, 'sha256': sha, 'summaries': summaries, 'n_raw': n_raw}


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description='Oracle setups miner (SPEC 3): stage 1 on discovery A, stage 2 on B, freeze.')
    ap.add_argument('--ct', required=True, choices=('perp', 'pp15', 'pp60', 'tennis'))
    ap.add_argument('--parts', required=True, help='parts root holding <ct>-<scope>/ directories')
    ap.add_argument('--out', required=True)
    ap.add_argument('--top', type=int, default=40, help='setups kept per (scope, h, side)')
    ap.add_argument('--beam', type=int, default=500, help='best pairs grown into triples')
    ap.add_argument('--shortlist', type=int, default=2000, help='candidates given exact statistics, deflated t and dedupe')
    ap.add_argument('--min-n', type=int, default=300)
    ap.add_argument('--support', type=float, default=0.01)
    ap.add_argument('--jaccard', type=float, default=0.5)
    ap.add_argument('--block', type=float, default=5.0, help='stationary bootstrap mean block (days)')
    ap.add_argument('--draws', type=int, default=2000)
    ap.add_argument('--seeds', type=int, default=8, help='placebo seeds')
    ap.add_argument('--q', type=float, default=0.10, help='BHY level')
    ap.add_argument('--max-frozen', type=int, default=10, help='frozen setups per scope')
    ap.add_argument('--seed', type=int, default=7)
    ap.add_argument('--chunk', type=int, default=32768, help='rows per matrix-product chunk (multiple of 64)')
    ap.add_argument('--code-sha', default=None)
    ap.add_argument('--quiet', action='store_true')
    return ap


def main(argv=None) -> dict:
    a = parser().parse_args(argv)
    if a.chunk % 64:
        raise SystemExit('--chunk must be a multiple of 64')
    return run(a)


if __name__ == '__main__':
    main()
