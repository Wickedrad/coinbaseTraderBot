"""HO-1 scorer of the oracle-setups study: python/oracle/SPEC.md section 4; prereg python/oracle/prereg/OR-H1.md sections
"HO-1 (once per frozen file)" and "Adversary" (reported beside every result).

    cd python && python3 -m oracle.ho1 --frozen frozen.json --parts <dir> --labels <regime labels.csv.gz> --out out/ho1 \
        --run <id> --code-sha <sha> [--registry ../research/registry.py] [--sha256 HEX|FILE] [--confirm confirm.jsonl] \
        [--prior-setups N] [--flag TEXT ...] [--quiet]

Nothing is re-selected: the frozen file fixes the setups, their scopes, sides, horizons and ranks, and the statistics
parameters (placebo seeds, bootstrap block / draws, BHY q, seed) come from its params.

1. Integrity. frozen.json is read as bytes and its SHA-256 checked against frozen.sha256 beside it (sha256sum format), or
   against --sha256 (the hash or a file holding it). A mismatch, or nothing to check against, is refused before any part
   is opened. The parts are the frozen file's own (same directory names, row counts and builder code sha); DOGE refused.
2. Rows. Per part only rows with t in [HOLD_FROM, HOLD_TO) are read (binary search on the sorted t: nothing at or after
   2026-11-05 is touched). A (side, h) decision is scored when sim.split_rows puts it in 'H' (decision + horizon, and the
   tennis contract close, inside Aug 1 - Nov 4) and it is tradable (ok, stratum >= 0, finite trade $): the row rule of
   the miner's stage 2 (oracle/mine.py PartCell / PartB), on split H instead of B.
3. Per frozen setup, traded exactly as confirmation traded it (HoldCell duck-types mine.PartB: mine.adversary runs on it
   unchanged, and test_ho1 runs mine.confirm on it and checks its numbers equal ours): sim.fire_mask, sim.trade_sim with
   sim.busy_key (one position at a time per asset; tennis per event), the part's primary-exit trade $ and hold; by_day
   over all 96 days (sim.daily_vec over sim.day_labels, the body of sim.daily_usd: 0.0 on days without trades); the
   matched random-entry placebo
   (sim.PlaceboPool: same stratum and UTC day, else same stratum and split; 8 seeds averaged; booked on the trade's day;
   sim.matched_placebo is the same draw); hit rate vs the matched base (HO-1 stratum means of the hit flag); p_ev / p_up /
   p = max (sim.stationary_bootstrap_test); by_tercile {LOW, MID, HIGH: {pnl, hours}} from ONE labeling of the HO-1
   hours, the regime v1 labels (--labels) of the scope's assets (allpairs.ho1.hour_terciles: an hour's label is the
   rounded mean of its minute labels over those assets): a trade's P&L goes to the label of the hour holding its decision
   instant, a tercile's hours are the hours with that label (Strata; review fix of Nov 6, P&L used to follow each row's
   own rv.npy tercile while the hours were the pooled labels'). Tennis (no RV regime): the
   tours are the strata, as research/tennis_ta_report.py does (origin/claude/project-thread-7817be): by_tercile
   {ATP|WTA: {pnl, hours}}, hours = the tour's live-match hours in the hold (start to close, clipped to the hold).
4. One book per frozen file (the contract type's ranked rulebook): every frozen setup; at each decision the best-ranked
   (frozen rank) setup that fires and is tradable there is the candidate, rows at one instant are taken in rank order;
   perps one $300 position at a time across ALL coins, Price Prediction one per asset (so one per market), tennis one per
   event. Same placebo, by_day, by_tercile and tests.
5. Registry rows (research/registry.py of origin/claude/project-thread-79ntof, loaded from --registry): thread
   'oracle-setups', family 'oracle-<ct>-v1'; one control (arm 'flat', $0 every day), one candidate per setup and the book,
   one placebo per candidate (placebo_for = its arm); contract_type perpetual | price_prediction | tennis; data.source
   'history', metric 'usd', engine 'oracle' (so ho1_pass's Kalshi replay_version gate, meant for the TS replay, does not
   apply: this engine reads the parts, not the replay); trial_id = make_id (ported, checked equal to registry.make_id);
   heldout filled by registry.ho1_fill; every row passes registry.validate or nothing is written (exit 1).
6. Verdict per setup and for the book = registry.ho1_pass(heldout) AND BHY at q within the family (m = the frozen
   setups of the type, plus --prior-setups of earlier openings of the family at p = 1; the book's p is NOT in the
   setups' family: the book is adjusted on its own row at m + 1) AND beats its placebo AND HO-1 hit rate above the
   matched base. BHY at m = every stage-2 setup (the frozen file's m_confirmed, or the line count of --confirm) is
   reported beside it (untested setups count as p = 1). --flag adds a flag to every row (a logged re-opening).
   Our own 16-day fold $ are reported beside the registry's (its ho1_fill counts Nov 4 twice in fold 6; a verdict-relevant
   difference is written to the notes).
Outputs (--out): rows.jsonl (the registry shard), ho1.json, ho1.md (aggregates only, public repo), validated.json (the
passing setups ranked by HO-1 $/h: the rulebook's input). NEVER DOGE.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import time
import types
import zlib
from datetime import datetime, timezone

import numpy as np

from allpairs.ho1 import hour_terciles
from .common import CTS, DAY, FOLD_EDGES, HOLD_FROM, HOLD_TO, HORIZONS, MIN, SIDES, SIZE, Part, fold_of, key, list_parts
from .mine import adversary as mine_adversary
from .mine import clean, code_sha as git_code_sha
from .sim import (ArrayPart, PlaceboPool, bhy, bhy_adjust, busy_key, daily_vec, day_labels, fire_mask, resolve,
                  shift_index, split_rows, stationary_bootstrap_test, trade_sim)

THREAD = 'oracle-setups'
FROZEN_SCHEMA = 'oracle-frozen-1'
POOLED = 'ALL'
CONTRACT_TYPE = {'perp': 'perpetual', 'pp15': 'price_prediction', 'pp60': 'price_prediction', 'tennis': 'tennis'}
HOLD_SPAN = (HOLD_FROM, HOLD_TO)
HOLD_DAYS = day_labels(HOLD_SPAN)                       # 2026-08-01 .. 2026-11-04
assert len(HOLD_DAYS) == 96 and HOLD_DAYS[0] == '2026-08-01' and HOLD_DAYS[-1] == '2026-11-04'
HOLD_HOURS = 24.0 * len(HOLD_DAYS)                      # the registry's $/h denominator (24 h a day)
FOLD_DAYS = [int((b - a) // DAY) for a, b in zip(FOLD_EDGES[:-1], FOLD_EDGES[1:])]     # 6 x 16
TERCILES = ('LOW', 'MID', 'HIGH')
TOURS = ('ATP', 'WTA')
MIN_STRATUM_HOURS = 100                                 # registry HO-1: a tercile counts with >= 100 h
HEX64 = re.compile(r'[0-9a-f]{64}')
# The primary exit each setup was scored with (prereg "Decision times, entries, labels, exits"): the rulebook hook must
# run exactly this exit, or the HO-1 $ is not what live would realise (prereg "Known limits").
EXITS = {
    'perp': 'taker entry at the next perp minute open (+12 bps + half spread), $300 notional; resting maker take-profit at '
            'the price netting +$5 after costs (maker 5 bps, 2 bps funding buffer; fills on a 1 bp trade-through); else a '
            'taker exit at the close of minute i+H; no stop',
    'pp15': 'taker buy of the side (YES at the ask, NO at 1 - bid), C = min(floor(20 / ask), 250), fee 0.07 C P (1 - P) '
            'rounded up to the cent; sell at the bid at the first minute netting >= $5 outside the last 10% of the window; '
            'else at the final candle ride to settlement if in profit at the bid, else sell at that bid',
    'tennis': 'taker entry at the side ask at a candle minute, C = min(floor(10 / ask), 100); take-profit at the bid when '
              'net >= $5 within H; else sell at the bid at minute k+H; if the market closes inside the horizon, hold to '
              'settlement (deviation from the OR-H1 text "ride only if in profit at the last candle, else sell at that '
              'bid", which is not causal: the last candle of a match is known only after it ended)',
}
EXITS['pp60'] = EXITS['pp15']
# Reported under "Known limits" in ho1.md (prereg "Known limits" plus what the review of Nov 6 found).
KNOWN_LIMITS = {
    'all': ['live exits (pacer, take-profit floors) would pre-empt a +$5 take-profit unless the setup\'s tagged exit '
            'bypasses them: the rulebook hook must run exactly the exit scored here (validated.json "exit")'],
    'perp': ['fills are on Binance USD-M, not Kalshi\'s perp book (15-minute tracking error ~21 bps on SOL / XRP)'],
    'pp15': ['prereg vs live: without a take-profit, a position not in profit at the final candle (60 s before the close) '
             'is sold at that bid; the live bot cannot exit then (relaxed cadence, STRATEGY_NO_EXIT_BEFORE_CLOSE_SEC 60) '
             'and the position settles. The "live exit (settle)" column scores that variant (tradeSettle; never selected '
             'on)', 'Kalshi history has top-of-book only'],
    'tennis': ['tennis books are candle-level; a market that closes inside the horizon settles (the OR-H1 sale at the '
               'last candle was not causal and was dropped before any opening)'],
}
KNOWN_LIMITS['pp60'] = KNOWN_LIMITS['pp15']
# Module families a setup's items read (registry `modules`), from the builders' feature names / descriptions.
ANALYZER = ('ta:', 'book:', 'conf:', 'conv:')
TALIB = ('cdl_', 'tl_', 'ta_')


def log_to(quiet: bool):
    t0 = time.time()
    return (lambda msg: None) if quiet else (lambda msg: print(f'[{time.time() - t0:7.1f}s] {msg}', flush=True))


# ---------------------------------------------------------------- registry plumbing

def make_id(thread, family, arm, code_sha, days, seed=None, phases=None, env=None) -> str:
    """research/registry.py make_id, ported (every row is checked against the loaded registry's own)."""
    k = json.dumps([thread, family, arm, code_sha, sorted(days), seed, sorted(phases or []), env or {}], sort_keys=True)
    return hashlib.sha1(k.encode()).hexdigest()[:16]


def load_registry(path: str | None = None):
    """(module, path, sha256) of research/registry.py: --registry, else ../research/registry.py (from python/), else the
    repo's research/registry.py. It lives on origin/claude/project-thread-79ntof; refused when none is found."""
    here = os.path.dirname(os.path.abspath(__file__))
    cands = [path] if path else [os.path.join('..', 'research', 'registry.py'), os.path.join(here, '..', '..', 'research', 'registry.py')]
    for p in cands:
        if p and os.path.isfile(p):
            spec = importlib.util.spec_from_file_location('oracle_ho1_registry', p)
            reg = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(reg)
            missing = [n for n in ('validate', 'ho1_fill', 'ho1_pass', 'make_id', 'contract_type_of', 'CONTRACT_TYPES', 'paired_p', 'bhy')
                       if not hasattr(reg, n)]
            if missing:
                raise SystemExit(f'{p}: not the registry (missing {missing})')
            with open(p, 'rb') as f:
                sha = hashlib.sha256(f.read()).hexdigest()
            return reg, os.path.abspath(p), sha
    raise SystemExit('research/registry.py not found: pass --registry (it is on origin/claude/project-thread-79ntof: '
                     'git show origin/claude/project-thread-79ntof:research/registry.py > registry.py)')


# ---------------------------------------------------------------- the frozen file

def load_frozen(path: str, sha256: str | None = None) -> tuple:
    """(frozen doc, sha256 hex). Refuses a file whose SHA-256 does not equal frozen.sha256 beside it (or --sha256)."""
    with open(path, 'rb') as f:
        body = f.read()
    got = hashlib.sha256(body).hexdigest()
    if sha256 and HEX64.fullmatch(sha256.strip().lower()):
        want, src = sha256.strip().lower(), '--sha256'
    else:
        src = sha256 or os.path.join(os.path.dirname(os.path.abspath(path)), 'frozen.sha256')
        if not os.path.isfile(src):
            raise SystemExit(f'{path}: no {os.path.basename(src)} to check its SHA-256 against (and no --sha256): refused; '
                             'HO-1 scores only the frozen file whose hash was logged')
        with open(src) as f:
            m = HEX64.search(f.read().lower())
        if not m:
            raise SystemExit(f'{src}: no SHA-256 in it: refused')
        want = m.group(0)
    if got != want:
        raise SystemExit(f'frozen.json sha256 {got[:16]}.. does not match {want[:16]}.. ({src}): refused, nothing scored')
    doc = json.loads(body)
    if not isinstance(doc, dict) or doc.get('schema') != FROZEN_SCHEMA or doc.get('ct') not in CTS:
        raise SystemExit(f'{path}: not an {FROZEN_SCHEMA} file of a known contract type')
    for s in doc.get('setups') or []:
        if 'DOGE' in str(s.get('scope', '')).upper() or s.get('ct') not in (None, doc['ct']):
            raise SystemExit(f'frozen setup {s.get("id")}: scope / ct refused')
        if s.get('side') not in SIDES[doc['ct']] or int(s.get('h', -1)) not in HORIZONS[doc['ct']] or not s.get('items'):
            raise SystemExit(f'frozen setup {s.get("id")}: bad side / horizon / items')
    return doc, got


# ---------------------------------------------------------------- hold rows

class HoldPart:
    """One part's rows with t in [HOLD_FROM, HOLD_TO) as an in-memory sim.ArrayPart (rows at or after HOLD_TO are never
    read: the cut is a binary search on the memory-mapped, sorted t)."""

    def __init__(self, path: str, ct: str, index: int):
        part = Part(path)
        if part.ct != ct:
            raise SystemExit(f'{path}: ct {part.ct!r} != {ct!r}')
        if 'DOGE' in str(part.scope).upper() or any('DOGE' in str(a).upper() for a in part.meta.get('assets', [])):
            raise SystemExit('DOGE part refused')
        meta = part.meta
        self.sides = list(meta.get('sides') or SIDES[ct])
        self.hs = [int(h) for h in (meta.get('horizons') or HORIZONS[ct])]
        tm = part['t']
        lo = int(np.searchsorted(tm, HOLD_FROM, side='left'))
        hi = int(np.searchsorted(tm, HOLD_TO, side='left'))
        t = np.array(tm[lo:hi], dtype=np.int64)
        if len(t) > 1 and np.any(np.diff(t) < 0):
            raise SystemExit(f'{path}: t is not sorted')
        arrays = {'t': t}
        need = ['group', 'asset', 'X'] + [f'stratum_{s}' for s in self.sides]
        need += [key(nm, s, h) for s in self.sides for h in self.hs for nm in ('ok', 'hit', 'trade', 'hold')]
        opt = ['rv', 'mkt', 'close', 'tmin', 'event'] + [key(nm, s, h) for s in self.sides for h in self.hs
                                                         for nm in ('tradeLat', 'tradeCost', 'tradeSettle')]
        for nm in need + opt:
            if part.has(nm):
                arrays[nm] = np.array(part[nm][lo:hi])
            elif nm in need:
                raise SystemExit(f'{path}: missing {nm}.npy')
        if arrays['X'].ndim != 2 or arrays['X'].shape[1] != len(part.features):
            raise SystemExit(f'{path}: X shape {arrays["X"].shape} vs {len(part.features)} features')
        self.dir = os.path.basename(os.path.normpath(path))
        self.scope = part.scope
        self.assets = [str(a) for a in (meta.get('assets') or [part.scope])]
        self.index = index
        self.rows_total = part.n
        self.hold_rows = hi - lo
        self.code_sha = meta.get('code_sha')
        self.v = ArrayPart(dict(meta, part_dir=self.dir, rows_total=part.n, hold_rows=hi - lo), arrays, path)
        self._cells: dict = {}
        self._shift = None

    def cell(self, side: str, h: int) -> 'HoldCell':
        k_ = (side, int(h))
        if k_ not in self._cells:
            if side not in self.sides or int(h) not in self.hs:
                raise SystemExit(f'{self.dir}: no side {side} / horizon {h}')
            self._cells[k_] = HoldCell(self, side, int(h))
        return self._cells[k_]

    def shift(self):
        if self._shift is None:
            self._shift = shift_index(self.v)
        return self._shift

    def tour_hours(self) -> float:
        """Tennis: live-match hours of this part's events inside the hold (published start to close, clipped)."""
        v = self.v
        if not len(v['t']):
            return 0.0
        g = np.asarray(v['group'], dtype=np.int64)
        t = np.asarray(v['t'], dtype=np.int64)
        start = t - np.asarray(v['tmin'], dtype=np.int64) * MIN if v.has('tmin') else t
        end = np.asarray(v['close'], dtype=np.int64) if v.has('close') else t + MIN
        u, inv = np.unique(g, return_inverse=True)
        s = np.full(len(u), np.iinfo(np.int64).max)
        e = np.full(len(u), np.iinfo(np.int64).min)
        np.minimum.at(s, inv, start)
        np.maximum.at(e, inv, end)
        live = np.clip(np.minimum(e, HOLD_TO) - np.maximum(s, HOLD_FROM), 0, None)
        return float(live.sum() / 3_600_000)


class HoldCell:
    """A part's HO-1 rows for one (side, h) and what trading, the placebo and the matched base need. It has the
    attributes of oracle/mine.py PartB (v, B, t, trade, hit, hold, st, busy, pool, pc.mhB, shift(), trade_on()), so the
    miner's confirm / adversary run on it unchanged: B = the HO-1 rows here."""

    def __init__(self, hp: HoldPart, side: str, h: int):
        v = hp.v
        self.hp, self.v, self.side, self.h = hp, v, side, h
        self.t = v['t']
        self.trade = v[key('trade', side, h)].astype(np.float64)
        self.hold = v[key('hold', side, h)].astype(np.float64)
        self.hit = v[key('hit', side, h)].astype(np.float64)
        self.st = v[f'stratum_{side}'].astype(np.int64)
        ok = (v[key('ok', side, h)] == 1) & (self.st >= 0) & np.isfinite(self.trade)
        self.B = np.flatnonzero(ok & (split_rows(v, h) == 'H'))
        S = int(self.st.max()) + 1 if len(self.st) and self.st.max() >= 0 else 1
        sH = self.st[self.B]
        cnt = np.bincount(sH, minlength=S).astype(np.float64)
        self.base = np.bincount(sH, self.hit[self.B], S) / np.maximum(cnt, 1)     # matched base: HO-1 stratum hit means
        self.pc = types.SimpleNamespace(mhB=self.base)
        self.busy = busy_key(v)
        self._pool = None

    @property
    def pool(self) -> PlaceboPool:
        if self._pool is None:
            self._pool = PlaceboPool(self.v, self.side, self.h)
        return self._pool

    def shift(self):
        return self.hp.shift()

    def trade_on(self, fire_all, trade=None) -> np.ndarray:
        """Taken HO-1 rows when the setup fires per fire_all (over every hold row), skip while busy (sim.trade_sim)."""
        B = self.B
        tr = self.trade if trade is None else trade
        rel = trade_sim(self.t[B], self.hold[B], tr[B], np.asarray(fire_all)[B], self.busy[B])
        return B[rel]

    def fire(self, setup: dict) -> np.ndarray:
        """Bool over every hold row: the setup's items hold (evaluated on the HO-1 rows only)."""
        out = np.zeros(len(self.t), dtype=bool)
        out[self.B] = fire_mask(self.v, setup, self.B)
        return out


# ---------------------------------------------------------------- strata hours (by_tercile denominators)

class Strata:
    """by_tercile strata. Perps and Price Prediction: one labeling of the HO-1 hours per set of assets, from the regime v1
    labels (allpairs.ho1.hour_terciles: an hour's label is the rounded mean of its minute labels over the assets, cached);
    a trade's P&L goes to the label of the hour holding its decision instant and a tercile's hours are the hours with that
    label, so numerator and denominator describe the same hours (review fix, Nov 6: P&L used to go by each trade's own
    rv.npy tercile while the hours were the pooled labels'). Tennis: the tours' live-match hours."""

    def __init__(self, ct: str, labels: str | None, hps: list):
        self.ct, self.labels, self.hps = ct, labels, hps
        self._cache: dict = {}
        if ct != 'tennis' and not (labels and os.path.isfile(labels)):
            raise SystemExit(f'{ct}: --labels (regime v1 labels.csv[.gz]) is required for the RV terciles')

    def keys(self) -> tuple:
        return TOURS if self.ct == 'tennis' else TERCILES

    def _hourly(self, hps: list) -> np.ndarray:
        """int8 per HO-1 hour (Aug 1 00:00 .. Nov 4 23:00): 0 LOW / 1 MID / 2 HIGH, -1 = no label, for the assets of hps."""
        assets = tuple(sorted({a for hp in hps for a in hp.assets}))
        if assets not in self._cache:
            d0 = HOLD_FROM // DAY
            lab = hour_terciles(self.labels, list(assets), d0, HOLD_TO // DAY - 1)
            arr = np.full(len(HOLD_DAYS) * 24, -1, dtype=np.int8)
            for (d, hr), v in lab.items():
                i = (int(d) - d0) * 24 + int(hr)
                if 0 <= i < len(arr):
                    arr[i] = TERCILES.index(v)
            self._cache[assets] = arr
        return self._cache[assets]

    def label(self, hps: list, t) -> np.ndarray:
        """Tercile code (0..2, -1 = none) of the HO-1 hour holding each decision instant t, for the assets of hps."""
        arr = self._hourly(hps)
        i = (np.asarray(t, dtype=np.int64) - HOLD_FROM) // 3_600_000
        ok = (i >= 0) & (i < len(arr))
        return np.where(ok, arr[np.clip(i, 0, len(arr) - 1)], -1).astype(np.int64)

    def hours(self, hps: list) -> dict:
        if self.ct == 'tennis':
            out = {}
            for hp in hps:
                out[hp.scope] = out.get(hp.scope, 0.0) + hp.tour_hours()
            return out
        arr = self._hourly(hps)
        return {k: float(np.count_nonzero(arr == j)) for j, k in enumerate(TERCILES)}


# ---------------------------------------------------------------- trading

def setup_legs(setup: dict, hps: list) -> list:
    """[(cell, taken rows)] of one frozen setup over its scope's parts: one position at a time per asset (event)."""
    legs = []
    for hp in hps:
        c = hp.cell(setup['side'], int(setup['h']))
        legs.append((c, c.trade_on(c.fire(setup))))
    return legs


def book_legs(setups: list, hps: list, ct: str) -> tuple:
    """The contract type's book: [(cell, taken rows)] plus the taken trades in time order (t, hold, part, busy key, setup id).
    At each decision row the best-ranked frozen setup that fires there and is tradable is its candidate; rows at one
    instant go in rank order; one position at a time per key: perps all coins (one $300 position is the whole book),
    Price Prediction the asset (one part = one asset, so also one per market), tennis the event."""
    ranked = sorted(setups, key=lambda s: int(s['rank']))
    T, R, HO, TR, K, P, J, ROW = [], [], [], [], [], [], [], []
    for p, hp in enumerate(hps):
        n = len(hp.v['t'])
        best = np.full(n, -1, dtype=np.int64)
        for j, s in enumerate(ranked):
            if s['scope'] not in (POOLED, hp.scope):
                continue
            f = hp.cell(s['side'], int(s['h'])).fire(s)
            best[f & (best < 0)] = j
        rows = np.flatnonzero(best >= 0)
        for j in np.unique(best[rows]):
            sel = rows[best[rows] == j]
            c = hp.cell(ranked[j]['side'], int(ranked[j]['h']))
            T.append(c.t[sel]); HO.append(c.hold[sel]); TR.append(c.trade[sel])
            R.append(np.full(len(sel), int(ranked[j]['rank']))); P.append(np.full(len(sel), p)); J.append(np.full(len(sel), j))
            ROW.append(sel)
            if ct == 'perp':
                K.append(np.zeros(len(sel), dtype=np.int64))
            elif ct == 'tennis':
                K.append(p * (1 << 40) + np.asarray(hp.v['group'], dtype=np.int64)[sel])
            else:
                K.append(np.full(len(sel), p, dtype=np.int64))
    if not T:
        return [], {'t': np.zeros(0, np.int64), 'hold': np.zeros(0), 'part': np.zeros(0, np.int64), 'key': np.zeros(0, np.int64),
                    'setup': [], 'candidates': 0}
    cat = lambda xs, dt=None: np.concatenate(xs).astype(dt) if dt else np.concatenate(xs)
    t, rk, hold, tr, k_, pp, jj, row = cat(T, np.int64), cat(R), cat(HO), cat(TR), cat(K, np.int64), cat(P), cat(J), cat(ROW)
    order = np.lexsort((rk, t))
    rel = trade_sim(t[order], hold[order], tr[order], np.ones(len(order), dtype=bool), k_[order])
    taken = order[rel]
    legs = {}
    for i in taken:
        s = ranked[jj[i]]
        legs.setdefault((int(pp[i]), s['side'], int(s['h'])), []).append(int(row[i]))
    out = [(hps[p].cell(sd, h), np.asarray(sorted(rs), dtype=np.int64)) for (p, sd, h), rs in sorted(legs.items())]
    detail = {'t': t[taken], 'hold': hold[taken], 'part': pp[taken], 'key': k_[taken], 'setup': [ranked[jj[i]]['id'] for i in taken],
              'candidates': int(len(order))}
    return out, detail


def evaluate(legs: list, params: dict, seed: int, strata: Strata, hps: list) -> dict:
    """HO-1 statistics of a set of taken trades: daily $ over the 96 days, the matched placebo (8 seeds, same day),
    hit rate vs matched base, by_tercile (or tours), folds, bootstrap tests (the confirmation's, on the hold)."""
    nd = len(HOLD_DAYS)
    daily, plac = np.zeros(nd), np.zeros(nd)
    keys_ = strata.keys()
    pnl = {k_: 0.0 for k_ in keys_}
    ppl = {k_: 0.0 for k_ in keys_}
    by_cell, pl_cell, trades_cell = {}, {}, {}
    folds = np.zeros(6)
    trades, hits, base = 0, 0.0, 0.0
    info = {'same_day': 0, 'fallback': 0, 'unmatched': 0}
    markets = set()
    for c, rows in legs:
        if not len(rows):
            continue
        t, usd = c.t[rows], c.trade[rows]
        pv, inf = c.pool.draw(rows, int(params['seeds']), seed)
        daily += daily_vec(t, usd, HOLD_SPAN)
        plac += daily_vec(t, pv, HOLD_SPAN)
        for k_ in info:
            info[k_] += inf[k_]
        trades += len(rows)
        hits += float(c.hit[rows].sum())
        base += float(c.base[c.st[rows]].sum())
        sc = c.hp.scope
        by_cell[sc] = by_cell.get(sc, 0.0) + float(usd.sum())
        pl_cell[sc] = pl_cell.get(sc, 0.0) + float(pv.sum())
        trades_cell[sc] = trades_cell.get(sc, 0) + len(rows)
        if strata.ct == 'tennis':
            pnl[sc] = pnl.get(sc, 0.0) + float(usd.sum())
            ppl[sc] = ppl.get(sc, 0.0) + float(pv.sum())
        else:
            rv = strata.label(hps, t)              # the same hour labels whose counts are the tercile hours
            for k, name in enumerate(TERCILES):
                pnl[name] += float(usd[rv == k].sum())
                ppl[name] += float(pv[rv == k].sum())
        f = fold_of(t)
        folds += np.bincount(f[f >= 0], usd[f >= 0], 6)
        markets |= {(sc, int(g)) for g in np.unique(np.asarray(c.v['group'])[rows])}
    hours = strata.hours(hps)
    if strata.ct == 'tennis':
        keys_ = tuple(hp.scope for hp in hps)
    terc = {k_: {'pnl': round(pnl.get(k_, 0.0), 6), 'hours': round(hours.get(k_, 0.0), 3)} for k_ in keys_}
    pterc = {k_: {'pnl': round(ppl.get(k_, 0.0), 6), 'hours': round(hours.get(k_, 0.0), 3)} for k_ in keys_}
    ev = stationary_bootstrap_test(daily, params['block'], int(params['draws']), seed)
    up = stationary_bootstrap_test(daily - plac, params['block'], int(params['draws']), seed + 1)
    return {'trades': trades, 'active_days': int(np.count_nonzero(daily)), 'usd_total': float(daily.sum()),
            'usd_day': float(daily.mean()), 'usd_per_hour': float(daily.sum() / HOLD_HOURS),
            'placebo_usd_total': float(plac.sum()), 'placebo_usd_day': float(plac.mean()),
            'beats_placebo': bool(daily.sum() > plac.sum()),
            'hit': hits / trades if trades else None, 'base_hit': base / trades if trades else None,
            'p_ev': ev['p'], 'p_up': up['p'], 'p': max(ev['p'], up['p']), 'p_ev_emp': ev['p_emp'], 'p_up_emp': up['p_emp'],
            'placebo': info, 'markets': len(markets), 'by_cell': by_cell, 'placebo_by_cell': pl_cell, 'trades_by_cell': trades_cell,
            'by_tercile': terc, 'placebo_by_tercile': pterc,
            'fold_usd': [float(x) for x in folds], 'fold_per_hour': [float(x / (24 * d)) for x, d in zip(folds, FOLD_DAYS)],
            'folds_won': int(np.sum(folds > 0)),
            '_daily': daily, '_placebo_daily': plac}


# ---------------------------------------------------------------- modules and rows

def feature_info(hps: list, side: str, f: str) -> tuple:
    """(column name, desc) of mined feature f for side `side` in the first part that has it."""
    for hp in hps:
        j = resolve(hp.v, side, f)
        if j >= 0:
            ft = hp.v.meta['features'][j]
            return ft.get('name', f), str(ft.get('desc', ''))
    return f, ''


def module_of(name: str, desc: str) -> str:
    """Module family of a feature (registry `modules`): contract-state, ta-primitives, ta-analyzer, ta-lib or context."""
    base = name.split('@')[0]
    if base.startswith('k_'):
        return 'contract-state'
    if desc.startswith('buildPrims'):
        return 'ta-primitives'
    if base.startswith(ANALYZER) or base == 'ta_net' or base == 'ctx:char':
        return 'ta-analyzer'
    if base.startswith(TALIB) or base == 'ctx:ht_mode' or 'TA-Lib' in desc:
        return 'ta-lib'
    if base.startswith('ctx:'):
        return 'context'
    return 'other-features'


def setup_modules(setup: dict, hps: list) -> list:
    return sorted({module_of(*feature_info(hps, setup['side'], str(i['f']))) for i in setup['items']})


def items_str(items) -> str:
    return ' & '.join(f'{i["f"]}={int(i["v"])}' for i in items)


def setup_env(s: dict, ct: str, sha: str) -> dict:
    return {'ORACLE_SETUP': s['id'], 'ORACLE_SCOPE': s['scope'], 'ORACLE_SIDE': s['side'], 'ORACLE_H_MIN': str(int(s['h'])),
            'ORACLE_ITEMS': items_str(s['items']), 'ORACLE_SIZE_USD': f'{SIZE[ct]:g}', 'ORACLE_EXIT': 'primary',
            'ORACLE_FROZEN_RANK': str(int(s['rank'])), 'ORACLE_FROZEN_SHA256': sha[:16]}


def build_rows(reg, ct, fam, sha, code_sha, run, results, book, control_terc, hps) -> tuple:
    """(rows, control row): the control, a candidate per setup and the book, a placebo per candidate; by_day on all 96
    days. Sets trial_id / placebo_trial_id on each result."""
    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    ctype = CONTRACT_TYPE[ct]
    ref = f'https://github.com/Wickedrad/coinbaseTraderBot/actions/runs/{run}' if re.fullmatch(r'[0-9]+', str(run)) else str(run)
    data = {'source': 'history', 'days': list(HOLD_DAYS), 'doge': False, 'metric': 'usd', 'engine': 'oracle'}
    common = {'v': 1, 'ts': now, 'thread': THREAD, 'family': fam, 'code_sha': code_sha, 'seed': None, 'contract_type': ctype,
              'hours': HOLD_HOURS, 'base': f'oracle-setups@{code_sha}', 'ref': ref, 'flags': [f'frozen-sha256:{sha[:16]}'],
              'code_epoch': 'oracle-setups OR-H1 HO-1 (python/oracle/ho1.py on the oracle parts; no TS replay)'}

    def row(arm, role, env, by_day, terc, extra):
        r = dict(common, arm=arm, role=role, env=env, data=dict(data, days=list(HOLD_DAYS)), flags=list(common['flags']),
                 by_day={d: round(float(x), 6) for d, x in zip(HOLD_DAYS, by_day)}, by_tercile=terc, **extra)
        r['trial_id'] = make_id(THREAD, fam, arm, code_sha, HOLD_DAYS, None, None, env)
        if r['trial_id'] != reg.make_id(THREAD, fam, arm, code_sha, list(HOLD_DAYS), None, None, env):
            raise SystemExit('make_id differs from research/registry.py make_id')
        return r

    ctl = row('flat', 'control', {}, np.zeros(len(HOLD_DAYS)), control_terc,
              {'modules': ['oracle-setups'], 'fills': 0, 'verdict': 'control: flat (no trading, $0 every HO-1 day)',
               'raw': {'run': str(run), 'ct': ct, 'frozen_sha256': sha, 'parts': [hp.dir for hp in hps]}})
    rows = [ctl]
    cands = [(r['setup'], r, r['setup']['id']) for r in results] + ([(None, book, 'book')] if book else [])
    for s, res, arm in cands:
        ev = res['eval']
        if s is not None:
            env = setup_env(s, ct, sha)
            mods = ['oracle-setups'] + res['modules']
            raw = {'run': str(run), 'ct': ct, 'frozen_sha256': sha, 'setup': {k_: s[k_] for k_ in ('id', 'scope', 'side', 'h', 'items', 'rank')}}
        else:
            env = {'ORACLE_BOOK': 'all frozen setups, best frozen rank first', 'ORACLE_SETUPS': ','.join(x['setup']['id'] for x in results),
                   'ORACLE_POSITIONS': {'perp': 'one $300 position at a time across all coins', 'tennis': 'one position per event at a time'}
                   .get(ct, 'one position per market and per asset at a time'), 'ORACLE_EXIT': 'primary',
                   'ORACLE_FROZEN_SHA256': sha[:16]}
            mods = ['oracle-setups'] + sorted({m for x in results for m in x['modules']})
            raw = {'run': str(run), 'ct': ct, 'frozen_sha256': sha, 'book_of': len(results)}
        stats = {k_: ev[k_] for k_ in ('trades', 'usd_total', 'usd_per_hour', 'hit', 'base_hit', 'p_ev', 'p_up', 'p',
                                       'placebo_usd_total', 'placebo', 'fold_usd')}
        c = row(arm, 'candidate', env, ev['_daily'], ev['by_tercile'],
                {'control': ctl['trial_id'], 'modules': mods, 'fills': ev['trades'], 'by_cell': ev['by_cell'],
                 'raw': dict(raw, ho1=stats)})
        if ct != 'perp':
            c['markets'] = ev['markets']
        penv = dict(env, ORACLE_PLACEBO='matched random entry: same stratum and UTC day, '
                                        f'{res.get("seeds", 8)} seeds averaged, booked on the trade day')
        p = row(f'{arm}:placebo', 'placebo', penv, ev['_placebo_daily'], ev['placebo_by_tercile'],
                {'control': ctl['trial_id'], 'placebo_for': arm, 'modules': mods, 'fills': ev['trades'],
                 'by_cell': ev['placebo_by_cell'], 'verdict': f'placebo of {arm}',
                 'raw': dict(raw, placebo=ev['placebo'])})
        rows += [c, p]
        res['trial_id'], res['placebo_trial_id'] = c['trial_id'], p['trial_id']
    ids = [r['trial_id'] for r in rows]
    if len(set(ids)) != len(ids):
        raise SystemExit('duplicate trial_id')
    return rows, ctl


# ---------------------------------------------------------------- outputs

def fmt(x, f='+.2f'):
    return 'n/a' if x is None else format(x, f)


def report_md(doc) -> str:
    ct = doc['ct']
    L = [f'# Oracle setups HO-1: {ct} ({doc["family"]})', '',
         'Prereg python/oracle/prereg/OR-H1.md "HO-1"; SPEC 4. Scored once on Aug 1 - Nov 4 2026 (96 days, 2,304 h); '
         'aggregates only.', '',
         f'Frozen file sha256 `{doc["frozen_sha256"]}` ({doc["n_setups"]} setups); parts '
         + ', '.join(f'{p["dir"]} ({p["hold_rows"]} hold rows)' for p in doc['parts']) + '.',
         f'Registry rows {doc["n_rows"]} (thread {THREAD}, research/registry.py sha256 {doc["registry_sha256"][:16]}); '
         f'BHY q {doc["params"]["q"]} at m = {doc["m_family"]} (the frozen setups of the family) and m = {doc["m_all"]} '
         '(every stage-2 setup); the book is adjusted on its own row at m + 1 and is not in the setups\' family.', '',
         f'**Passing setups: {sum(1 for s in doc["setups"] if s["verdict"]["pass"])} of {doc["n_setups"]}**'
         + (f'; book {"PASS" if doc["book"]["verdict"]["pass"] else "fail"}.' if doc.get('book') else '.'), '',
         '| rank | arm | scope | side h | items | trades | $ total | $/h | placebo $ | hit vs base | folds won (registry) '
         '| worst fold $/h | strata won / covered | p | p BHY family | p BHY all | verdict |',
         '|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|']
    for s in doc['setups'] + ([doc['book']] if doc.get('book') else []):
        e, h, v = s['ho1'], s['heldout'], s['verdict']
        L.append(f'| {s.get("rank", "-")} | {s["arm"]} | {s.get("scope", "all")} | {s.get("side", "")} {s.get("h", "")} | '
                 f'{items_str(s["items"]) if s.get("items") else "book"} | {e["trades"]} | {e["usd_total"]:+.2f} | '
                 f'{e["usd_per_hour"]:+.4f} | {e["placebo_usd_total"]:+.2f} | {fmt(e["hit"], ".3f")} vs {fmt(e["base_hit"], ".3f")} | '
                 f'{h.get("folds_won")}/{h.get("folds")} | {fmt(h.get("worst_fold_per_hour"), "+.3f")} | '
                 f'{h.get("terciles_won", 0)}/{h.get("terciles_covered", 0)} | {e["p"]:.2g} | {v["p_bhy"]:.2g} | {v["p_bhy_all"]:.2g} | '
                 f'{"PASS" if v["pass"] else "fail: " + "; ".join(v["why"])} |')
    L += ['', '## Strata (by_tercile pnl $ / hours) and adversary ($/day on the hold)', '',
          '| arm | ' + ' | '.join(doc['strata_keys']) + ' | stale | early | +1 latency | cost stress | live exit (settle) |',
          '|---|' + '---|' * (len(doc['strata_keys']) + 5)]
    for s in doc['setups']:
        bt, ad = s['ho1']['by_tercile'], s.get('adversary') or {}
        g = lambda n_: fmt((ad.get(n_) or {}).get('usd_day'), '+.3f')
        L.append(f'| {s["arm"]} | ' + ' | '.join(f'{bt[k]["pnl"]:+.2f} / {bt[k]["hours"]:.0f} h' if k in bt else '-' for k in doc['strata_keys'])
                 + f' | {g("stale")} | {g("early")} | {g("lat")} | {g("cost")} | {g("settle")} |')
    if doc.get('book'):
        b = doc['book']
        L += ['', f'Book: {b["ho1"]["trades"]} trades taken of {b["candidates"]} candidate decisions; positions: {b["positions"]}.']
    if doc.get('notes'):
        L += ['', '## Notes', ''] + [f'- {n}' for n in doc['notes']]
    L += ['', '## Known limits', ''] + [f'- {n}' for n in KNOWN_LIMITS['all'] + KNOWN_LIMITS.get(ct, [])]
    L.append('')
    return '\n'.join(L)


def write_json(path: str, obj) -> None:
    with open(path, 'w') as f:
        json.dump(clean(obj), f, indent=1, sort_keys=True, allow_nan=False)


# ---------------------------------------------------------------- driver

def resolve_parts(doc: dict, root: str, ct: str) -> list:
    """The frozen file's own parts under root (same dir, row count and builder code sha), in its order."""
    paths = {os.path.basename(p): p for p in list_parts(root, ct)}
    listed = doc.get('parts') or [{'dir': d} for d in sorted(paths)]
    out = []
    for i, e in enumerate(listed):
        if e['dir'] not in paths:
            raise SystemExit(f'part {e["dir"]} of the frozen file is not under {root}: refused')
        hp = HoldPart(paths[e['dir']], ct, i)
        if e.get('rows_total') is not None and int(e['rows_total']) != hp.rows_total:
            raise SystemExit(f'{e["dir"]}: {hp.rows_total} rows, the frozen file says {e["rows_total"]}: not the mined part')
        if e.get('code_sha') is not None and e['code_sha'] != hp.code_sha:
            raise SystemExit(f'{e["dir"]}: builder code_sha {hp.code_sha} != frozen {e["code_sha"]}: not the mined part')
        if e.get('scope') is not None and e['scope'] != hp.scope:
            raise SystemExit(f'{e["dir"]}: scope {hp.scope} != frozen {e["scope"]}')
        out.append(hp)
    return out


def run(a) -> dict:
    log = log_to(a.quiet)
    doc, sha = load_frozen(a.frozen, a.sha256)          # refused here, before any part is opened, on a hash mismatch
    reg, reg_path, reg_sha = load_registry(a.registry)
    ct = doc['ct']
    fam = f'oracle-{ct}-v1'
    if CONTRACT_TYPE[ct] not in reg.CONTRACT_TYPES:
        raise SystemExit(f'contract type {CONTRACT_TYPE[ct]} not in the registry')
    params = {'seeds': 8, 'block': 5.0, 'draws': 2000, 'q': 0.10, 'seed': 7}
    params.update({k_: doc.get('params', {})[k_] for k_ in params if k_ in doc.get('params', {})})
    code_sha = a.code_sha or git_code_sha()
    setups = sorted(doc.get('setups') or [], key=lambda s: int(s['rank']))
    log(f'{ct}: frozen sha256 {sha} verified; {len(setups)} frozen setups; registry {reg_path}')
    hps = resolve_parts(doc, a.parts, ct)
    by_scope = {hp.scope: hp for hp in hps}
    notes = []
    extra = sorted(set(os.path.basename(p) for p in list_parts(a.parts, ct)) - {hp.dir for hp in hps})
    if extra:
        notes.append(f'parts under --parts not in the frozen file, not used: {", ".join(extra)}')
    log('parts: ' + ', '.join(f'{hp.dir} {hp.hold_rows} hold rows' for hp in hps))
    strata = Strata(ct, a.labels, hps)
    scope_parts = lambda s: hps if s['scope'] == POOLED else [by_scope[s['scope']]] if s['scope'] in by_scope else None

    # --- every frozen setup, traded as confirmation traded it
    results = []
    for s in setups:
        sp = scope_parts(s)
        if not sp:
            raise SystemExit(f'setup {s["id"]}: no part for scope {s["scope"]}')
        seed = (zlib.crc32(s['id'].encode()) ^ int(params['seed'])) & 0x7FFFFFFF
        legs = setup_legs(s, sp)
        ev = evaluate(legs, params, seed, strata, sp)
        cells = [hp.cell(s['side'], int(s['h'])) for hp in sp]
        adv = mine_adversary(s, cells, HOLD_SPAN, None)
        results.append({'setup': s, 'eval': ev, 'adversary': adv, 'modules': setup_modules(s, sp), 'seed': seed,
                        'seeds': int(params['seeds'])})
        log(f'  {s["id"]}: {ev["trades"]} trades, ${ev["usd_total"]:+.2f} ({ev["usd_per_hour"]:+.4f}/h), placebo '
            f'${ev["placebo_usd_total"]:+.2f}, hit {fmt(ev["hit"], ".3f")} vs {fmt(ev["base_hit"], ".3f")}, p {ev["p"]:.2g}')

    # --- the book
    book = None
    if setups:
        legs, detail = book_legs(setups, hps, ct)
        bseed = (zlib.crc32(f'{ct}-book'.encode()) ^ int(params['seed'])) & 0x7FFFFFFF
        ev = evaluate(legs, params, bseed, strata, hps)
        book = {'eval': ev, 'detail': detail, 'seed': bseed, 'seeds': int(params['seeds'])}
        log(f'  book: {ev["trades"]} trades of {detail["candidates"]} candidate decisions, ${ev["usd_total"]:+.2f}, '
            f'placebo ${ev["placebo_usd_total"]:+.2f}, p {ev["p"]:.2g}')

    # --- registry rows, HO-1 blocks (registry ho1_fill), verdicts
    ctl_hours = strata.hours(hps)
    order = [hp.scope for hp in hps] if ct == 'tennis' else list(TERCILES)
    control_terc = {k_: {'pnl': 0.0, 'hours': ctl_hours.get(k_, 0.0)} for k_ in order}
    rows, ctl = build_rows(reg, ct, fam, sha, code_sha, a.run, results, book, control_terc, hps)
    reg.ho1_fill(rows)
    byid = {r['trial_id']: r for r in rows}
    cand = results + ([book] if book else [])
    # BHY within the family: m = the frozen setups of the type (prereg "HO-1"), plus the frozen setups of any earlier
    # opening of the same family (--prior-setups, counted as p = 1: their p values are another run's). The book is not
    # one of the family's hypotheses (it trades a subset of the setups' trades): it is adjusted on its own row, at
    # m_family + 1 (review fix, Nov 6: the book's p used to sit inside the setups' family and could lift a setup).
    q = float(params['q'])
    prior = max(0, int(getattr(a, 'prior_setups', 0) or 0))
    ps_set = [c['eval']['p'] for c in results] + [1.0] * prior
    m_family = len(ps_set)
    book_bhy = lambda ps, pb: float(bhy_adjust(list(ps) + [pb])[-1])
    adj = [float(x) for x in bhy_adjust(ps_set)[:len(results)]] + ([book_bhy(ps_set, book['eval']['p'])] if book else [])
    rej = [x <= q for x in adj]
    m_conf = doc.get('m_confirmed')
    if a.confirm:
        with open(a.confirm) as f:
            n_conf = sum(1 for line in f if line.strip())
        if m_conf is not None and n_conf != m_conf:
            notes.append(f'--confirm has {n_conf} setups, the frozen file says m_confirmed {m_conf}: used {n_conf}')
        m_conf = n_conf
    m_conf = max(int(m_conf or 0), len(results))
    ps_all = ps_set + [1.0] * (m_conf - len(results))
    adj_all = [float(x) for x in bhy_adjust(ps_all)[:len(results)]] + ([book_bhy(ps_all, book['eval']['p'])] if book else [])
    p_reg = [reg.paired_p(list(c['eval']['_daily'])) for c in cand]
    preg_set = p_reg[:len(results)] + [1.0] * prior
    adj_reg = [x[0] for x in reg.bhy(preg_set, q)[:len(results)]] + ([reg.bhy(preg_set + [p_reg[-1]], q)[-1][0]] if book else [])
    if prior:
        notes.append(f'family BHY m = {len(results)} setups of this frozen file + {prior} frozen setups of earlier openings '
                     f'of {fam} (counted as p = 1)')
    for i, c in enumerate(cand):
        r = byid[c['trial_id']]
        ok, why = reg.ho1_pass(r['heldout'], reg.contract_type_of(r), r['data'].get('engine'))
        e = c['eval']
        hit_ok = e['hit'] is not None and e['hit'] > e['base_hit']
        reasons = ([f'HO-1: {why}'] if not ok else []) + ([] if rej[i] else [f'BHY p {adj[i]:.3g} > {params["q"]}'])
        reasons += ([] if e['beats_placebo'] or 'placebo' in why else ['does not beat its placebo'])
        reasons += ([] if hit_ok else ['hit rate not above the matched base'])
        c['heldout'] = r['heldout']
        c['verdict'] = {'pass': bool(ok and rej[i] and e['beats_placebo'] and hit_ok), 'ho1_pass': bool(ok), 'ho1_why': why,
                        'bhy_pass': bool(rej[i]), 'p_bhy': float(adj[i]), 'p_bhy_all': float(adj_all[i]),
                        'bhy_pass_all': bool(adj_all[i] <= float(params['q'])), 'beats_placebo': e['beats_placebo'],
                        'hit_above_base': bool(hit_ok), 'p_paired_t': p_reg[i], 'p_bhy_paired_t': adj_reg[i], 'why': reasons}
        v = c['verdict']
        r['verdict'] = (('HO-1 PASS' if v['pass'] else 'HO-1 fail: ' + '; '.join(reasons))
                        + f' (${e["usd_per_hour"]:+.4f}/h, p {e["p"]:.2g}, p BHY {adj[i]:.2g} at m {m_family + (i >= len(results))}, '
                        f'{adj_all[i]:.2g} at m {len(ps_all) + (i >= len(results))})')
        r['raw']['verdict'] = {k_: v[k_] for k_ in ('pass', 'ho1_pass', 'bhy_pass', 'p_bhy', 'p_bhy_all', 'beats_placebo', 'hit_above_base')}
        # registry fold 6 counts Nov 4 twice (ho1_fill: folds[-1] += [d1]); our own 16-day folds beside it
        if (e['folds_won'] >= 4) != ((r['heldout'].get('folds_won') or 0) >= 4):
            notes.append(f'{r["arm"]}: registry folds won {r["heldout"].get("folds_won")} vs {e["folds_won"]} on 16-day folds '
                         '(ho1_fill counts Nov 4 twice in fold 6)')

    # --- validate every row with the registry; refuse to write an invalid shard
    bad = []
    for r in rows:
        err, fl = reg.validate(r)
        if err:
            bad.append(f'{r["arm"]}: {"; ".join(err)}')
        r['flags'] = sorted(set((r.get('flags') or []) + fl + list(getattr(a, 'flag', None) or [])))
    if bad:
        raise SystemExit('invalid registry rows (nothing written):\n  ' + '\n  '.join(bad))
    blocking = sorted({f for r in rows for f in r['flags'] if f.startswith(('G0:', 'G1:', 'G1b:', 'G1c:', 'G2:', 'LOCKBOX:', 'DEV:', 'HO1:'))})
    if blocking:
        notes.append(f'validator flags on rows: {", ".join(blocking)}')
    if ct == 'tennis':
        single = [s['id'] for s in setups if s['scope'] != POOLED]
        notes.append('tennis strata are the tours (research/tennis_ta_report.py convention; no RV regime for matches); the '
                     'miner freezes tennis setups from the pooled scope only, since a single-tour setup has one stratum and '
                     'cannot meet "2 strata won"' + (f'; this frozen file still holds {len(single)} single-tour setup(s), '
                                                     'which cannot pass' if single else ''))
    for d in doc.get('deviations') or []:
        notes.append(f'deviation from the OR-H1 text (decided before the opening): {d}')

    # --- outputs
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, 'rows.jsonl'), 'w') as f:
        for r in rows:
            f.write(json.dumps(clean(r), sort_keys=True, allow_nan=False) + '\n')
    pub = lambda e: {k_: v for k_, v in e.items() if not k_.startswith('_')}
    out_setups = []
    for c in results:
        s = c['setup']
        out_setups.append({'arm': s['id'], 'id': s['id'], 'rank': int(s['rank']), 'scope': s['scope'], 'side': s['side'],
                           'h': int(s['h']), 'items': s['items'], 'modules': c['modules'], 'trial_id': c['trial_id'],
                           'placebo_trial_id': c['placebo_trial_id'], 'ho1': pub(c['eval']), 'heldout': c['heldout'],
                           'verdict': c['verdict'], 'adversary': c['adversary'], 'dev_B': (s.get('dev') or {}).get('B')})
    out_book = None
    if book:
        bt = book['detail']
        out_book = {'arm': 'book', 'trial_id': book['trial_id'], 'placebo_trial_id': book['placebo_trial_id'],
                    'ho1': pub(book['eval']), 'heldout': book['heldout'], 'verdict': book['verdict'],
                    'candidates': bt['candidates'], 'setups_used': {i: bt['setup'].count(i) for i in sorted(set(bt['setup']))},
                    'positions': {'perp': 'one $300 position at a time across all coins',
                                  'tennis': 'one position per event at a time'}.get(ct, 'one position per asset (and market) at a time')}
    summary = {'schema': 'oracle-ho1-1', 'ct': ct, 'family': fam, 'thread': THREAD, 'contract_type': CONTRACT_TYPE[ct],
               'frozen_sha256': sha, 'run': str(a.run), 'code_sha': code_sha, 'registry_sha256': reg_sha,
               'prereg': 'python/oracle/prereg/OR-H1.md', 'params': params,
               'hold': {'from': HOLD_DAYS[0], 'to': HOLD_DAYS[-1], 'days': len(HOLD_DAYS), 'hours': HOLD_HOURS},
               'parts': [{'dir': hp.dir, 'scope': hp.scope, 'rows_total': hp.rows_total, 'hold_rows': hp.hold_rows} for hp in hps],
               'strata_keys': list(control_terc), 'strata_hours': {k_: v['hours'] for k_, v in control_terc.items()},
               'n_setups': len(results), 'n_rows': len(rows), 'm_family': m_family, 'm_all': len(ps_all), 'prior_setups': prior,
               'book_bhy': 'the book is adjusted on its own row at m + 1 (setups + the book); setups at m',
               'control_trial_id': ctl['trial_id'], 'setups': out_setups, 'book': out_book, 'notes': notes}
    write_json(os.path.join(a.out, 'ho1.json'), summary)
    passing = sorted([s for s in out_setups if s['verdict']['pass']], key=lambda s: -s['ho1']['usd_per_hour'])
    validated = {'schema': 'oracle-validated-1', 'ct': ct, 'family': fam, 'contract_type': CONTRACT_TYPE[ct], 'frozen_sha256': sha,
                 'run': str(a.run), 'code_sha': code_sha, 'ranked_by': 'HO-1 $/h (usd_total / 2304 h)', 'size_usd': SIZE[ct],
                 'exit': EXITS[ct],
                 'setups': [{'rank_ho1': i + 1, 'id': s['id'], 'ct': ct, 'scope': s['scope'], 'side': s['side'], 'h': s['h'],
                             'items': s['items'], 'frozen_rank': s['rank'], 'trial_id': s['trial_id'],
                             'usd_per_hour': s['ho1']['usd_per_hour'], 'usd_day': s['ho1']['usd_day'], 'trades': s['ho1']['trades'],
                             'hit': s['ho1']['hit'], 'base_hit': s['ho1']['base_hit'], 'p': s['ho1']['p'],
                             'p_bhy': s['verdict']['p_bhy'], 'p_bhy_all': s['verdict']['p_bhy_all'], 'heldout': s['heldout']}
                            for i, s in enumerate(passing)],
                 'book': None if not out_book else {'pass': out_book['verdict']['pass'], 'usd_per_hour': out_book['ho1']['usd_per_hour'],
                                                    'trial_id': out_book['trial_id'], 'positions': out_book['positions']}}
    write_json(os.path.join(a.out, 'validated.json'), validated)
    with open(os.path.join(a.out, 'ho1.md'), 'w') as f:
        f.write(report_md(summary))
    log(f'{len(passing)} of {len(results)} frozen setups pass HO-1' + (f'; book {"PASS" if out_book["verdict"]["pass"] else "fail"}' if out_book else '')
        + f'; {len(rows)} registry rows validated -> {a.out}/rows.jsonl')
    return {'summary': summary, 'rows': rows, 'validated': validated, 'results': results, 'book': book}


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description='Oracle setups HO-1 scorer (SPEC 4): score a frozen file once on Aug 1 - Nov 4 2026.')
    ap.add_argument('--frozen', required=True, help="the miner's frozen.json")
    ap.add_argument('--parts', required=True, help='parts root holding the frozen file\'s <ct>-<scope>/ directories')
    ap.add_argument('--labels', default=None, help='regime v1 labels.csv[.gz] (required for perp / Price Prediction)')
    ap.add_argument('--out', required=True)
    ap.add_argument('--run', default='local', help='run id (registry ref / raw)')
    ap.add_argument('--code-sha', default=None)
    ap.add_argument('--registry', default=None, help='research/registry.py (origin/claude/project-thread-79ntof)')
    ap.add_argument('--sha256', default=None, help='expected frozen.json SHA-256 (hex) or a file holding it; default frozen.sha256 beside it')
    ap.add_argument('--confirm', default=None, help="the miner's confirm.jsonl (BHY at m = every stage-2 setup)")
    ap.add_argument('--prior-setups', type=int, default=0,
                    help='frozen setups of earlier HO-1 openings of the same family (a logged re-opening): added to the '
                         'family BHY m as p = 1')
    ap.add_argument('--flag', action='append', default=[], help='a flag added to every registry row (repeatable), e.g. '
                                                                'ho1-reopen:<earlier runs>')
    ap.add_argument('--quiet', action='store_true')
    return ap


def main(argv=None) -> dict:
    return run(parser().parse_args(argv))


if __name__ == '__main__':
    main()
