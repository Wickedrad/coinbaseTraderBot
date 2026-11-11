"""OR-H3: a loser cut (and entry filters) for Price Prediction entries. Pre-registration python/oracle/prereg/OR-H3.md.

    cd python && python3 -m oracle.cut labels --kind 15|60 --history <dir with kalshi/KX<A>15M or KX<A>D> \
        --part <parts>/pp15-<A> --out <cut labels root> [--code-sha <sha>]
    cd python && python3 -m oracle.cut search --parts <parts root> --cut-labels <cut labels root> --out <dir> [--code-sha <sha>]
    cd python && python3 -m oracle.cut ho1 --frozen <dir>/frozen-cut.json [--sha256 HEX|FILE] --ct pp15|pp60 \
        --parts <parts root> --cut-labels <cut labels root> --regime <regime v1 labels.csv.gz> --registry research/registry.py \
        --out <dir> --run <id> [--code-sha <sha>] [--lockbox lockbox_candidates.json]

Route (task step 1): a SIDECAR, not a rebuild of the pp parts. `labels` reloads the windows a pp part was built from
(oracle.pp.load_windows: the same load_kalshi call, filters and order), maps every part row to its window, recomputes the
OR-H1 primary exit for every row and side and REFUSES unless it equals the part's own trade_<s><h> on every mapped row
(the row identity check; a part group whose window index moved, e.g. a history file that gained markets since the part
was built, is matched by open time and by those labels). It then writes <out>/<ct>-<A>/, aligned row for row with the
part: win.npy (row -> window), t.npy (the part's t: the search and HO-1 refuse a sidecar whose rows are not
the part's), and per side s, horizon h and cut level L: tradeCut_<s><h>_<L> (float32 net $),
holdCut_<s><h>_<L> (uint8 minutes to the exit, settlement = to the close), cutMin_<s><h>_<L> (int8 decision minute of the
cut sale, -1 = not cut) and tradeCutSettle_<s><h>_<L> (float32: every exit that is neither a take-profit nor a cut
settles); <out>/<ct>-<A>/windows/ holds the referenced windows' side bid / ask paths and settlement (for the HO-1
placebo's random-minute exits and the +1 minute / +1c variants). Spot features, strata and every other label stay in the
existing part; nothing is rebuilt. The search never opens windows/ (it holds HO-1 paths).

The exit (OR-H3 "Arms"). Entry at decision minute k at the side's ask (OR-H1 sizes and fees). For j = k+1 .. while
tau_j > 60 s (j <= n - 2): a take-profit (OR-H1: net >= $5 at the bid, tau_j > 10% of the window) first; else sell at the
side's bid at the first j where bid_j <= entry ask - D (absolute D in 0.03 / 0.05 / 0.08 / 0.10 / 0.15 / 0.20) or bid_j <=
entry ask x (1 - r) (relative r in 15 / 25 / 40 %); level 'none' is the OR-H1 primary exit. Otherwise the OR-H1 end rule at
the final decision minute n - 1 (ride if in profit at its bid, else sell there; no book there: settles); the settle
variant settles instead. Prices on the 4-decimal grid as oracle.pp.simulate.

Filters (on the entry's own side, before entry): F1 skips k_price 0-1 (side ask < 0.30), F2 skips k_dmid3 = -1, F3
skips k_z in {0, 1}; all 8 subsets. NOTE: k_z levels 0-1 are side-relative z < -0.75 (the side is well out of the money;
pp.py Z_EDGES); the prereg's gloss "(spot within about one sigma of the strike)" describes levels 2-4 instead. The levels
{0, 1} as written are implemented (they are the loser study's over-represented states).

Entries (OR-H3 "Arms"): every tradable OR-H1 decision (ok_<s><h>, stratum >= 0), both sides, one position at a time per
asset and window (one part = one asset; the window = the part's event: the 15-minute market, or the hourly event across
its strikes), the first tradable decision at or after the previous exit (sim.trade_sim, the OR-H1 convention). Decisions
at one instant (the two sides; for hourly, the strikes) are taken in a fixed pseudo-random order (a hash of the decision
minute, market and side with params.order_seed), the same for every arm and the control: matched random entries.

Search (OR-H3 "Splits and selection"), discovery rows only (oracle.mine.load_dev: t + h <= DEV_END; the sidecar is
sliced to the same prefix; windows/ is never read): 80 arms per type (10 levels x 8 filter sets; 'none' with no filter is
the control). On A: $/day = pooled daily $ over every A day (zeros included); top 5 per type. On B, each kept arm:
stationary bootstrap of daily $ (block 5, 2,000 draws), p_ev (mean > 0) and p_up (arm - control > 0), p = max; BHY q 0.10
over the 10 kept arms of both types. The best BHY survivor per type by B $/day freezes; none = that type is falsified at
discovery. Every arm's A and B numbers go to report-cut.md / search.json (B is descriptive for arms not kept). Writes
frozen-cut.json (canonical JSON) + frozen-cut.sha256.

HO-1 (OR-H3 "HO-1"), once per type, rows t in [HOLD_FROM, HOLD_TO) only: the frozen arm vs the control (same entries, no
cut, no filter: the registry control row) and the matched placebo (params.seeds seeds averaged): every unit the arm would
cut is exited instead at k + d, d drawn from the arm's HO-1 cut offsets (cut minute - k) in the same stratum (stratum_<s>;
the type's pooled offsets when the stratum has none), the TP check kept before it; the filter set is replaced by skipping,
in each (stratum, UTC day) cell, as many tradable decisions as the filters skip there, drawn uniformly in the cell.
Registry rows (thread oracle-setups, family oracle-<ct>-cut-v1, roles control / candidate / placebo, by_day on all 96 days,
by_tercile from the regime v1 hour labels as oracle.ho1), validated with research/registry.py; ho1_fill; verdict =
registry ho1_pass (>= 90 days, folds, terciles vs the control, beats the placebo) AND net $ > 0 (the hypothesis: "net
positive ... and beats the same entries without the cut"). Descriptive (never selected on): the settle variant, +1 minute
entry latency, +1c entry cost (cut threshold from the price paid), and the frozen cut on the OR-AMEND-1 lockbox
candidates' HO-1 trades (their own entries, the OR-H1 one-position-per-asset trading). Writes rows.jsonl, ho1-cut.json,
ho1-cut.md (aggregates only). NEVER DOGE; nothing at or after 2026-11-05 is read; never compared to paper.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import types
import zlib
from datetime import datetime, timezone
from itertools import combinations

import numpy as np

from allpairs.features import side_quotes
from allpairs.fees import contracts_for_stake, taker_fee

from .common import (DAY, DEV_END, HOLD_FROM, HOLD_TO, HORIZONS, MAX_CONTRACTS, MIN, SIDES, SIZE, SPLITS, TARGET_USD, Part, fold_of,
                     key, list_parts, write_part)
from .mine import canonical, clean, code_sha as git_code_sha, load_dev
from .pp import KINDS, simulate, tp_zone
from .sim import (bhy_adjust, busy_key, daily_vec, day_labels, fire_mask, resolve, split_rows, stationary_bootstrap_test,
                  trade_sim)

CUT_TYPES = ('pp15', 'pp60')
KIND_OF = {'pp15': 15, 'pp60': 60}
# (name, kind, D): absolute D in $ per contract, relative D as a share of the entry ask; 'none' = the OR-H1 primary exit.
LEVELS = [('a03', 'abs', 0.03), ('a05', 'abs', 0.05), ('a08', 'abs', 0.08), ('a10', 'abs', 0.10), ('a15', 'abs', 0.15),
          ('a20', 'abs', 0.20), ('r15', 'rel', 0.15), ('r25', 'rel', 0.25), ('r40', 'rel', 0.40), ('none', None, None)]
LEVEL = {n_: (k_, d_) for n_, k_, d_ in LEVELS}
LEVEL_NAMES = [x[0] for x in LEVELS]
FILTERS = ('F1', 'F2', 'F3')
FILTER_SETS = [tuple(c) for r in range(4) for c in combinations(FILTERS, r)]          # (), F1, F2, F3, F1F2, ... (8)
FILTER_DESC = {'F1': 'skip k_price 0-1 (side ask < 0.30)', 'F2': 'skip k_dmid3 = -1 (side mid fell >= 1c over 3 min)',
               'F3': 'skip k_z in {0, 1} (side-relative z < -0.75)'}
CUT_LAST_SEC = 60                    # the live bot cannot exit in the last 60 s: a cut needs tau_j > 60 s
PARAMS = {'top': 5, 'q': 0.10, 'm': 10, 'block': 5.0, 'draws': 2000, 'seeds': 8, 'seed': 7, 'order_seed': 11}
LABELS_KIND = 'oracle-cut-labels-1'
FROZEN_SCHEMA = 'oracle-cut-frozen-1'
THREAD = 'oracle-setups'
PREREG = 'python/oracle/prereg/OR-H3.md'
HEX64 = re.compile(r'[0-9a-f]{64}')
UNMATCHED_MAX = 0.005                # refuse a sidecar when more than 0.5% of a part's rows find no window


def log_to(quiet: bool):
    import time
    t0 = time.time()
    return (lambda msg: None) if quiet else (lambda msg: print(f'[{time.time() - t0:7.1f}s] {msg}', flush=True))


def arm_id(ct: str, level: str, fset) -> str:
    return f'{ct}:cut-{level}:' + ('+'.join(fset) if fset else 'nofilter')


def level_desc(level: str) -> str:
    k_, d_ = LEVEL[level]
    if k_ is None:
        return 'none (OR-H1 primary exit)'
    return f'bid <= entry ask - {d_:.2f}' if k_ == 'abs' else f'bid <= entry ask x (1 - {d_:.2f})'


# ---------------------------------------------------------------- the exit

class Paths:
    """Positions entered at minute k0 (per row) at price px on side paths `bid` (M, n): what every exit variant needs."""

    def __init__(self, bid, settle, k0, px, stake: float, n: int, max_c: int = 250, target: float = TARGET_USD):
        bid = np.asarray(bid, dtype=np.float64)
        M, N = bid.shape
        assert N == n, (N, n)
        self.M, self.n, self.target = M, n, target
        self.k0 = np.broadcast_to(np.asarray(k0, dtype=np.int64), (M,)).copy()
        px = np.asarray(px, dtype=np.float64)
        self.live = np.isfinite(px) & (px > 0) & (px < 1)
        pxs = np.round(np.where(self.live, px, 0.5), 4)          # the 4-decimal grid (pp.simulate)
        C = np.where(self.live, np.minimum(contracts_for_stake(stake, pxs), max_c), 0.0)
        cost = C * pxs + taker_fee(C, pxs)
        j = np.arange(N)[None, :]
        can = np.isfinite(bid) & (bid > 0) & (bid < 1) & (j > self.k0[:, None])
        bs = np.round(np.where(can, bid, 0.5), 4)
        self.net = np.where(can, np.round(C[:, None] * bs - taker_fee(C[:, None], bs) - cost[:, None], 6), np.nan)
        self.can, self.bs, self.pxs, self.C = can, bs, pxs, C
        self.tp = can & tp_zone(n)[None, :] & (self.net >= target)
        tau_ok = (n - np.arange(N)) * 60 > CUT_LAST_SEC            # tau_j = (n - j) minutes > 60 s
        self.win = can & tau_ok[None, :]
        self.settle_net = np.round(C * np.asarray(settle, dtype=np.float64) - cost, 6)

    def cut_mask(self, level: str) -> np.ndarray:
        k_, d_ = LEVEL[level]
        if k_ is None:
            return np.zeros_like(self.win)
        thr = np.round(self.pxs - d_ if k_ == 'abs' else self.pxs * (1.0 - d_), 4)
        return self.win & (self.bs <= thr[:, None] + 1e-9)

    def forced_mask(self, exit_at) -> np.ndarray:
        """A sale at the first minute >= exit_at (per row) with a bid inside the cut window (the placebo's random exit)."""
        e = np.asarray(exit_at, dtype=np.int64)[:, None]
        f = self.win & (np.arange(self.n)[None, :] >= e)
        out = np.zeros_like(f)
        has = f.any(axis=1)
        out[np.nonzero(has)[0], np.argmax(f, axis=1)[has]] = True
        return out

    def exit(self, cut: np.ndarray) -> dict:
        """trade (net $), hold (minutes), cut_min (minute of the cut sale, -1), trade_settle, kind (0 tp, 1 cut, 2 end sale,
        3 ride / settle) under: take-profit first, else the first `cut` minute, else the OR-H1 end rule."""
        M, n = self.M, self.n
        ev = self.tp | cut
        has = ev.any(axis=1)
        je = np.argmax(ev, axis=1)
        rows = np.arange(M)
        is_tp = has & self.tp[rows, je]
        is_cut = has & ~is_tp
        net_e = self.net[rows, je]
        net_last = self.net[:, n - 1]
        ride = ~has & (~np.isfinite(net_last) | (net_last > 0))
        trade = np.where(has, net_e, np.where(ride, self.settle_net, net_last))
        hold = np.where(has, je - self.k0, np.where(ride, n - self.k0, n - 1 - self.k0))
        kind = np.where(is_tp, 0, np.where(is_cut, 1, np.where(ride, 3, 2)))
        live = self.live
        return {'trade': np.where(live, trade, np.nan), 'hold': np.where(live, hold, 0).astype(np.int64),
                'cut_min': np.where(live & is_cut, je, -1).astype(np.int64),
                'trade_settle': np.where(live, np.where(has, net_e, self.settle_net), np.nan), 'kind': np.where(live, kind, -1)}


def simulate_cut(bid, settle, k0, px, stake: float, n: int, level: str = 'none', exit_at=None, max_c: int = 250,
                 target: float = TARGET_USD) -> dict:
    """The OR-H3 exit for M positions (k0 scalar or per row). level: a LEVELS name; exit_at (per row): the placebo's forced
    sale minute instead of a cut level (level must then be 'none'). With level 'none' and no exit_at this is exactly
    oracle.pp.simulate's primary exit (trade, hold) and its trade_settle."""
    p = Paths(bid, settle, k0, px, stake, n, max_c, target)
    if exit_at is not None:
        if level != 'none':
            raise ValueError('exit_at replaces the cut level')
        return p.exit(p.forced_mask(exit_at))
    return p.exit(p.cut_mask(level))


# ---------------------------------------------------------------- labels (the sidecar)

def _label_pairs(bid, ask, settle, win, side, kmin, n, stake, max_c, levels, chunk=40_000):
    """Exit labels for (window, side, k) triples, every level: {level: dict of arrays}."""
    M = len(win)
    out = {lv: {'trade': np.full(M, np.nan), 'hold': np.zeros(M, np.int64), 'cut_min': np.full(M, -1, np.int64),
                'trade_settle': np.full(M, np.nan)} for lv in levels}
    for c0 in range(0, M, chunk):
        c1 = min(M, c0 + chunk)
        w_, s_, k_ = win[c0:c1], side[c0:c1], kmin[c0:c1]
        p = Paths(bid[w_, s_, :], settle[w_, s_], k_, ask[w_, s_, k_], stake, n, max_c)
        for lv in levels:
            r = p.exit(p.cut_mask(lv))
            for f in out[lv]:
                out[lv][f][c0:c1] = r[f]
    return out


def map_rows(part: Part, w, bid, ask, settle, n: int, stake: float, max_c: int, log=print) -> tuple:
    """(win (R,) int64: the window of each part row, -1 = unmatched; info). A row maps to window part.group when that
    window opens at t - kmin and its recomputed primary trade equals the part's trade on every tradable side; a group that
    fails is matched by open time among all loaded windows, by the same labels (exactly one window must fit all its rows)."""
    sides = part.meta['sides']
    h = int(part.meta['horizons'][0])
    t = np.asarray(part['t'], dtype=np.int64)
    g = np.asarray(part['group'], dtype=np.int64)
    kmin = np.asarray(part['kmin'], dtype=np.int64)
    R = len(t)
    open_r = t - kmin * MIN
    ok = [np.asarray(part[key('ok', s, h)]) == 1 for s in sides]
    tr = [np.asarray(part[key('trade', s, h)], dtype=np.float64) for s in sides]
    W = len(w.open_ms)

    def fits(rows, wins):
        """Bool per (row, window) pair: the recomputed primary trade equals the part's on each tradable side."""
        good = np.ones(len(rows), dtype=bool)
        for si in range(len(sides)):
            m = ok[si][rows]
            if not m.any():
                continue
            idx = np.nonzero(m)[0]
            lab = _label_pairs(bid, ask, settle, wins[idx], np.full(len(idx), si), kmin[rows[idx]], n, stake, max_c, ['none'])['none']
            want = tr[si][rows[idx]]
            same = np.isfinite(lab['trade']) & np.isfinite(want) & (np.abs(lab['trade'] - want) <= 1e-3)
            good[idx] &= same
        return good

    win = np.full(R, -1, dtype=np.int64)
    direct = (g >= 0) & (g < W)
    direct[direct] &= w.open_ms[g[direct]] == open_r[direct]
    rows = np.nonzero(direct)[0]
    good = fits(rows, g[rows]) if len(rows) else np.zeros(0, dtype=bool)
    win[rows[good]] = g[rows[good]]
    bad_groups = np.unique(g[win < 0])
    win[np.isin(g, bad_groups)] = -1                         # a group maps whole or not at all
    info = {'rows': int(R), 'direct': int((win >= 0).sum()), 'groups_rematched': 0, 'groups_unmatched': 0, 'rows_unmatched': 0}
    if len(bad_groups):
        log(f'  {len(bad_groups)} group(s) not at their window index: matching by open time and labels')
        ow = np.asarray(w.open_ms, dtype=np.int64)
        order = np.argsort(ow, kind='stable')
        ows = ow[order]
        brows = np.nonzero(np.isin(g, bad_groups))[0]
        lo = np.searchsorted(ows, open_r[brows], 'left')
        hi = np.searchsorted(ows, open_r[brows], 'right')
        cnt = hi - lo
        pr = np.repeat(brows, cnt)
        off = np.arange(int(cnt.sum())) - np.repeat(np.cumsum(cnt) - cnt, cnt)
        pc = order[np.repeat(lo, cnt) + off] if len(pr) else np.zeros(0, np.int64)
        ok_pair = np.zeros(len(pr), dtype=bool)
        for c0 in range(0, len(pr), 200_000):
            ok_pair[c0:c0 + 200_000] = fits(pr[c0:c0 + 200_000], pc[c0:c0 + 200_000])
        # a window fits a group when every row of the group fits it; it must be the group's only fitting window and
        # not already the window of a directly matched group or of another re-matched group
        gk, rows_per_group = np.unique(g[brows], return_counts=True)
        need = dict(zip(gk.tolist(), rows_per_group.tolist()))
        comb = g[pr[ok_pair]] * np.int64(W + 1) + pc[ok_pair]
        u, c_ = np.unique(comb, return_counts=True)
        ug, uw = u // (W + 1), u % (W + 1)
        full = np.array([c_[i] == need[int(ug[i])] for i in range(len(u))], dtype=bool) if len(u) else np.zeros(0, dtype=bool)
        fg, fw = ug[full], uw[full]
        gs, gc = np.unique(fg, return_counts=True)
        single = set(gs[gc == 1].tolist())
        used = set(np.unique(win[win >= 0]).tolist())
        pick = [(int(a_), int(b_)) for a_, b_ in zip(fg, fw) if int(a_) in single and int(b_) not in used]
        wc: dict = {}
        for gg, wi in pick:
            wc.setdefault(wi, []).append(gg)
        for wi, gs_ in wc.items():
            if len(gs_) == 1:
                win[g == gs_[0]] = wi
                info['groups_rematched'] += 1
        info['groups_unmatched'] = int(len(np.unique(g[win < 0])))
    info['rows_unmatched'] = int((win < 0).sum())
    return win, info


def build_labels(kind: int, history: str, part_dir: str, out_root: str, code_sha: str | None = None, log=print) -> str:
    """The sidecar of one pp part (module docstring): <out_root>/<part dir>/ + windows/."""
    from .pp import load_windows
    kind = int(kind)
    cfg = KINDS[kind]
    ct, n = cfg['ct'], cfg['n']
    part = Part(part_dir)
    if part.ct != ct:
        raise SystemExit(f'{part_dir}: ct {part.ct!r} != {ct!r}')
    asset = str(part.scope)
    if 'DOGE' in asset.upper() or 'DOGE' in os.path.basename(os.path.normpath(part_dir)).upper():
        raise SystemExit('DOGE refused (never DOGE)')
    stake, max_c = SIZE[ct], MAX_CONTRACTS[ct]
    w = load_windows(kind, history, asset, log)
    bid, ask, _, _, _, _, settle = side_quotes(w)
    win, info = map_rows(part, w, bid, ask, settle, n, stake, max_c, log)
    R = len(win)
    log(f'{ct}-{asset}: {R} part rows; {info["direct"]} at their window index, {info["groups_rematched"]} group(s) re-matched, '
        f'{info["rows_unmatched"]} row(s) unmatched')
    if info['rows_unmatched'] > UNMATCHED_MAX * R:
        raise SystemExit(f'{info["rows_unmatched"]} of {R} rows match no window (> {UNMATCHED_MAX:.1%}): the history is not '
                         'the one the part was built from: refused')
    return write_sidecar(part, part_dir, out_root, np.asarray(w.open_ms, dtype=np.int64), bid, ask, settle, win, info, n,
                         code_sha, log)


def write_sidecar(part: Part, part_dir: str, out_root: str, open_ms, bid, ask, settle, win, info: dict, n: int,
                  code_sha: str | None = None, log=print) -> str:
    """Label every mapped row of the part at every level, check level none against the part, write the sidecar."""
    ct, asset = part.ct, str(part.scope)
    h = int(part.meta['horizons'][0])
    sides = part.meta['sides']
    stake, max_c = SIZE[ct], MAX_CONTRACTS[ct]
    R = part.n
    win = np.asarray(win, dtype=np.int64)
    kmin = np.asarray(part['kmin'], dtype=np.int64)
    used = np.unique(win[win >= 0])
    remap = np.full(len(open_ms), -1, dtype=np.int64)
    remap[used] = np.arange(len(used))
    arrays = {'win': np.where(win >= 0, remap[np.maximum(win, 0)], -1).astype(np.int32),
              't': np.asarray(part['t'], dtype=np.int64)}           # the part's own t: checked row for row at load time
    mism = 0
    for si, s in enumerate(sides):
        okm = (np.asarray(part[key('ok', s, h)]) == 1) & (win >= 0)
        rows = np.nonzero(okm)[0]
        lab = _label_pairs(bid, ask, settle, win[rows], np.full(len(rows), si), kmin[rows], n, stake, max_c, LEVEL_NAMES)
        # The row identity check: level none is the OR-H1 primary exit; it must equal the part's labels.
        want_t = np.asarray(part[key('trade', s, h)], dtype=np.float64)[rows]
        want_h = np.asarray(part[key('hold', s, h)], dtype=np.int64)[rows]
        bad = ~(np.abs(lab['none']['trade'] - want_t) <= 1e-3) | (lab['none']['hold'] != want_h)
        if part.has(key('tradeSettle', s, h)):
            ws = np.asarray(part[key('tradeSettle', s, h)], dtype=np.float64)[rows]
            bad |= ~(np.abs(lab['none']['trade_settle'] - ws) <= 1e-3)
        mism += int(bad.sum())
        for lv in LEVEL_NAMES:
            a = lab[lv]
            tr = np.full(R, np.nan, dtype=np.float32); tr[rows] = a['trade']
            ho = np.zeros(R, dtype=np.uint8); ho[rows] = np.clip(a['hold'], 0, 255)
            cm = np.full(R, -1, dtype=np.int8); cm[rows] = a['cut_min']
            ts = np.full(R, np.nan, dtype=np.float32); ts[rows] = a['trade_settle']
            arrays[f'tradeCut_{s}{h}_{lv}'] = tr
            arrays[f'holdCut_{s}{h}_{lv}'] = ho
            arrays[f'cutMin_{s}{h}_{lv}'] = cm
            arrays[f'tradeCutSettle_{s}{h}_{lv}'] = ts
    if mism:
        raise SystemExit(f'{mism} mapped row-side(s) whose recomputed OR-H1 exit differs from the part\'s: refused')
    dig = hashlib.sha256()
    for nm in sorted(arrays):
        dig.update(nm.encode()); dig.update(np.ascontiguousarray(arrays[nm]).tobytes())
    meta = {'kind': LABELS_KIND, 'ct': ct, 'scope': asset, 'assets': [asset], 'sides': sides, 'horizons': [h],
            'levels': [{'name': a, 'kind': b, 'D': c, 'desc': level_desc(a)} for a, b, c in LEVELS],
            'cut_last_sec': CUT_LAST_SEC, 'size_usd': stake, 'max_contracts': max_c, 'window_min': n,
            'base': {'dir': os.path.basename(os.path.normpath(part_dir)), 'n': part.n, 'code_sha': part.meta.get('code_sha')},
            'code_sha': code_sha or git_code_sha(), 'match': info, 'labels_sha256': dig.hexdigest(),
            'notes': 'OR-H3 cut labels aligned row for row with the base part (python/oracle/cut.py). level none = the OR-H1 '
                     'primary exit, checked equal to the part\'s trade / hold / tradeSettle on every row. win.npy indexes '
                     'windows/ (-1 = no window: every label NaN).'}
    path = os.path.join(out_root, os.path.basename(os.path.normpath(part_dir)))
    write_part(path, meta, arrays)
    wsel = used
    write_part(os.path.join(path, 'windows'),
               {'kind': LABELS_KIND + '-windows', 'ct': ct, 'scope': asset, 'window_min': n,
                'notes': 'side bid / ask paths (W, 2, n), side 0 = YES, 1 = NO (allpairs side_quotes), settle (W, 2)'},
               {'open_ms': np.asarray(open_ms, dtype=np.int64)[wsel], 'bid': bid[wsel].astype(np.float64),
                'ask': ask[wsel].astype(np.float64), 'settle': settle[wsel].astype(np.float64)})
    log(f'{ct}-{asset}: wrote {len(arrays)} arrays x {R} rows and {len(wsel)} windows to {path}')
    return path


# ---------------------------------------------------------------- units: (row, side) decisions of one part and split

def _mix64(x: np.ndarray) -> np.ndarray:
    """splitmix64 finaliser (uint64, wraps)."""
    x = np.asarray(x, dtype=np.uint64)
    with np.errstate(over='ignore'):
        x = (x ^ (x >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
        x = (x ^ (x >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
        return x ^ (x >> np.uint64(31))


def order_key(t, group, side, seed: int) -> np.ndarray:
    """Fixed pseudo-random priority of a decision unit among those at the same instant (same for every arm)."""
    with np.errstate(over='ignore'):
        x = (np.asarray(t, dtype=np.int64) // MIN).astype(np.uint64) * np.uint64(0x9E3779B97F4A7C15)
        x = x ^ _mix64(np.asarray(group, dtype=np.int64).astype(np.uint64) * np.uint64(2) + np.asarray(side, dtype=np.uint64))
        x = x ^ np.uint64(int(seed) & 0xFFFFFFFF)
    return _mix64(x)


def sidecar_path(cut_root: str, part_dir: str) -> str:
    return os.path.join(cut_root, os.path.basename(os.path.normpath(part_dir)))


def check_sidecar(sc: Part, part: Part) -> None:
    b = sc.meta.get('base') or {}
    if sc.meta.get('kind') != LABELS_KIND:
        raise SystemExit(f'{sc.path}: not an OR-H3 cut-label sidecar')
    if b.get('dir') != os.path.basename(os.path.normpath(part.path)) or int(b.get('n', -1)) != part.n or b.get('code_sha') != part.meta.get('code_sha'):
        raise SystemExit(f'{sc.path}: built for {b}, not for {os.path.basename(part.path)} (n {part.n}, code {part.meta.get("code_sha")}): refused')
    if sc.n != part.n:
        raise SystemExit(f'{sc.path}: {sc.n} rows != the part\'s {part.n}')


def check_rows(sc: Part, t, lo: int, hi: int) -> None:
    """Row identity at load time: the sidecar's copy of the part's t equals the loaded rows' t on [lo, hi)."""
    if not sc.has('t'):
        raise SystemExit(f'{sc.path}: no t.npy (sidecar of an older format): refused')
    if not np.array_equal(np.asarray(sc['t'][lo:hi], dtype=np.int64), np.asarray(t, dtype=np.int64)):
        raise SystemExit(f'{sc.path}: rows {lo}..{hi} are not the part\'s rows (t differs): refused')


class Cell:
    """The tradable (row, side) units of one part in one split, in trading order (t, then the fixed random priority),
    with every level's labels. v: the part's rows (ArrayPart / Part view), lab: the sidecar arrays for the same rows."""

    def __init__(self, v, lab: dict, split: str, index: int, order_seed: int, windows=None, win=None):
        self.v, self.index = v, index
        meta = v.meta
        sides = list(meta['sides'])
        h = int(meta['horizons'][0])
        self.h, self.sides = h, sides
        self.scope = str(meta['scope'])
        self.assets = [str(a) for a in (meta.get('assets') or [self.scope])]
        t = np.asarray(v['t'], dtype=np.int64)
        R = len(t)
        sp = split_rows(v, h)
        group = np.asarray(v['group'], dtype=np.int64)
        event = np.asarray(v['event'], dtype=np.int64) if v.has('event') else group
        rows_l, side_l = [], []
        for si, s in enumerate(sides):
            okm = (np.asarray(v[key('ok', s, h)]) == 1) & (np.asarray(v[f'stratum_{s}']) >= 0) & (sp == split)
            okm &= np.isfinite(np.asarray(lab[f'tradeCut_{s}{h}_none'], dtype=np.float64))
            r = np.nonzero(okm)[0]
            rows_l.append(r); side_l.append(np.full(len(r), si, dtype=np.int64))
        rows = np.concatenate(rows_l) if rows_l else np.zeros(0, np.int64)
        side = np.concatenate(side_l) if side_l else np.zeros(0, np.int64)
        prio = order_key(t[rows], group[rows], side, order_seed)
        o = np.lexsort((prio, t[rows]))
        self.rows, self.side = rows[o], side[o]
        U = len(self.rows)
        self.U = U
        self.t = t[self.rows]
        self.event = event[self.rows]
        self.kmin = np.asarray(v['kmin'], dtype=np.int64)[self.rows] if v.has('kmin') else np.zeros(U, np.int64)
        self.day = self.t // DAY
        self.stratum = np.empty(U, dtype=np.int64)
        X = v['X']
        self.skip = {f: np.zeros(U, dtype=bool) for f in FILTERS}
        for si, s in enumerate(sides):
            m = self.side == si
            r = self.rows[m]
            self.stratum[m] = np.asarray(v[f'stratum_{s}'], dtype=np.int64)[r]
            cols = {nm: resolve(v, s, nm) for nm in ('k_price', 'k_dmid3', 'k_z')}
            if min(cols.values()) < 0:
                raise SystemExit(f'{v.path}: no side-relative k_price / k_dmid3 / k_z columns for side {s}')
            xp, xd, xz = (np.asarray(X[r, cols[c]]) for c in ('k_price', 'k_dmid3', 'k_z'))
            self.skip['F1'][m] = (xp == 0) | (xp == 1)
            self.skip['F2'][m] = xd == -1
            self.skip['F3'][m] = (xz == 0) | (xz == 1)
        self.trade, self.hold, self.cutmin, self.tsettle = {}, {}, {}, {}
        for lv in LEVEL_NAMES:
            tr, ho, cm, ts = (np.empty(U), np.empty(U), np.empty(U, np.int64), np.empty(U))
            for si, s in enumerate(sides):
                m = self.side == si
                r = self.rows[m]
                tr[m] = np.asarray(lab[f'tradeCut_{s}{h}_{lv}'], dtype=np.float64)[r]
                ho[m] = np.asarray(lab[f'holdCut_{s}{h}_{lv}'], dtype=np.float64)[r]
                cm[m] = np.asarray(lab[f'cutMin_{s}{h}_{lv}'], dtype=np.int64)[r]
                ts[m] = np.asarray(lab[f'tradeCutSettle_{s}{h}_{lv}'], dtype=np.float64)[r]
            self.trade[lv], self.hold[lv], self.cutmin[lv], self.tsettle[lv] = tr, ho, cm, ts
        self.windows = windows
        self.win = None if win is None else np.asarray(win, dtype=np.int64)[self.rows]

    def filtered(self, fset) -> np.ndarray:
        m = np.zeros(self.U, dtype=bool)
        for f in fset:
            m |= self.skip[f]
        return m

    def take(self, level: str, fset=(), drop=None, trade=None, hold=None) -> np.ndarray:
        """Unit indexes taken by the arm: candidates pass the filters (and `drop`), finite trade; one position at a time
        per event (sim.trade_sim on the trading order)."""
        tr = self.trade[level] if trade is None else trade
        ho = self.hold[level] if hold is None else hold
        cand = ~self.filtered(fset) & np.isfinite(tr)
        if drop is not None:
            cand &= ~drop
        return trade_sim(self.t, ho, tr, cand, self.event)

    def paths(self, idx: np.ndarray, k_shift: int = 0, cost: float = 0.0) -> Paths:
        """Paths of units idx from windows/ (HO-1 only): entry at kmin + k_shift at the ask (+ cost)."""
        if self.windows is None:
            raise RuntimeError('no windows loaded (discovery never reads them)')
        W = self.windows
        wi, si = self.win[idx], self.side[idx]
        if np.any(wi < 0):
            raise SystemExit('a unit without a window')
        k0 = self.kmin[idx] + k_shift
        n = W['bid'].shape[2]
        kk = np.minimum(k0, n - 1)
        px = np.where(k0 <= n - 1, W['ask'][wi, si, kk], np.nan) + cost
        ct = self.v.meta['ct']
        return Paths(W['bid'][wi, si, :], W['settle'][wi, si], k0, px, SIZE[ct], n, MAX_CONTRACTS[ct])


def load_cells_dev(ct: str, parts_root: str, cut_root: str, split: str, order_seed: int, log=print) -> list:
    """Discovery cells (split A or B) of every part of a type: dev rows only (mine.load_dev; the sidecar sliced to the same
    prefix and asserted); windows/ is not opened."""
    cells = []
    paths = list_parts(parts_root, ct)
    if not paths:
        raise SystemExit(f'no {ct} parts under {parts_root}')
    for i, p in enumerate(paths):
        v = load_dev(p, ct)
        part = Part(p)
        sc = Part(sidecar_path(cut_root, p))
        check_sidecar(sc, part)
        cut = int(v.meta['dev_rows'])
        h = int(v.meta['horizons'][0])
        if cut and int(np.asarray(v['t'])[-1]) + h * MIN > DEV_END:
            raise AssertionError('a row past DEV_END reached the search')
        check_rows(sc, v['t'], 0, cut)
        lab = {}
        for s in v.meta['sides']:
            for lv in LEVEL_NAMES:
                for nm in ('tradeCut', 'holdCut', 'cutMin', 'tradeCutSettle'):
                    a = f'{nm}_{s}{h}_{lv}'
                    lab[a] = np.array(sc[a][:cut])
        cells.append(Cell(v, lab, split, i, order_seed))
    log(f'{ct} {split}: ' + ', '.join(f'{c.scope} {c.U} units' for c in cells))
    return cells


# ---------------------------------------------------------------- arms

def arm_daily(cells: list, level: str, fset, span) -> tuple:
    """(pooled daily $ over span, trades, cut trades)."""
    d0, d1 = int(span[0] // DAY), int(-(-int(span[1]) // DAY))
    daily = np.zeros(d1 - d0)
    trades = cuts = 0
    for c in cells:
        tk = c.take(level, fset)
        daily += daily_vec(c.t[tk], c.trade[level][tk], span)
        trades += len(tk)
        cuts += int((c.cutmin[level][tk] >= 0).sum())
    return daily, trades, cuts


def search(parts_root: str, cut_root: str, out: str, code_sha: str | None = None, types_=CUT_TYPES, params=None, log=print) -> dict:
    P = dict(PARAMS, **(params or {}))
    code_sha = code_sha or git_code_sha()
    res = {'schema': 'oracle-cut-search-1', 'prereg': PREREG, 'prereg_sha256': prereg_sha(), 'params': P, 'code_sha': code_sha,
           'types': {}}
    kept_all = []
    parts_meta = {}
    for ct in types_:
        A = load_cells_dev(ct, parts_root, cut_root, 'A', P['order_seed'], log)
        B = load_cells_dev(ct, parts_root, cut_root, 'B', P['order_seed'], log)
        spA, spB = SPLITS[ct]['A'], SPLITS[ct]['B']
        ctlA, _, _ = arm_daily(A, 'none', (), spA)
        ctlB, ctl_trB, _ = arm_daily(B, 'none', (), spB)
        arms = []
        for lv in LEVEL_NAMES:
            for fs in FILTER_SETS:
                dA, nA, cA = arm_daily(A, lv, fs, spA)
                dB, nB, cB = arm_daily(B, lv, fs, spB)
                arms.append({'id': arm_id(ct, lv, fs), 'ct': ct, 'level': lv, 'filters': list(fs),
                             'A': {'days': len(dA), 'trades': nA, 'cut_trades': cA, 'usd_total': float(dA.sum()), 'usd_day': float(dA.mean())},
                             'B': {'days': len(dB), 'trades': nB, 'cut_trades': cB, 'usd_total': float(dB.sum()), 'usd_day': float(dB.mean()),
                                   'vs_control_usd_day': float((dB - ctlB).mean())},
                             '_dB': dB})
        ranked = sorted(arms, key=lambda a: (-a['A']['usd_day'], a['id']))
        for r, a in enumerate(ranked, 1):
            a['rank_A'] = r
        kept = ranked[:int(P['top'])]
        for a in kept:
            seed = (zlib.crc32(a['id'].encode()) ^ int(P['seed'])) & 0x7FFFFFFF
            ev = stationary_bootstrap_test(a['_dB'], P['block'], int(P['draws']), seed)
            up = stationary_bootstrap_test(a['_dB'] - ctlB, P['block'], int(P['draws']), seed + 1)
            a['kept'] = True
            a['B'].update({'p_ev': ev['p'], 'p_up': up['p'], 'p': max(ev['p'], up['p']), 'p_ev_emp': ev['p_emp'], 'p_up_emp': up['p_emp']})
            kept_all.append(a)
        parts_meta[ct] = [{'dir': c.v.meta['part_dir'], 'scope': c.scope, 'rows_total': int(c.v.meta['rows_total']),
                           'code_sha': c.v.meta.get('code_sha'), 'labels_sha256': Part(sidecar_path(cut_root, c.v.path)).meta['labels_sha256']}
                          for c in A]
        res['types'][ct] = {'arms': arms, 'control': {'A_usd_day': float(ctlA.mean()), 'B_usd_day': float(ctlB.mean()), 'B_trades': ctl_trB},
                            'A_days': len(ctlA), 'B_days': len(ctlB), 'parts': parts_meta[ct]}
        log(f'{ct}: control A ${ctlA.mean():+.3f}/day, B ${ctlB.mean():+.3f}/day; best A arm {ranked[0]["id"]} ${ranked[0]["A"]["usd_day"]:+.3f}/day')
    m = max(int(P['m']), len(kept_all))
    adj = bhy_adjust([a['B']['p'] for a in kept_all] + [1.0] * (m - len(kept_all)))[:len(kept_all)]
    for a, x in zip(kept_all, adj):
        a['B']['p_bhy'] = float(x)
        a['survivor'] = bool(x <= float(P['q']) and a['B']['usd_day'] > 0)
    frozen = {}
    for ct in types_:
        surv = sorted([a for a in kept_all if a['ct'] == ct and a['survivor']], key=lambda a: (-a['B']['usd_day'], a['id']))
        frozen[ct] = None if not surv else {k_: surv[0][k_] for k_ in ('id', 'ct', 'level', 'filters', 'rank_A', 'A', 'B')}
        if frozen[ct]:
            frozen[ct]['level_desc'] = level_desc(frozen[ct]['level'])
            frozen[ct]['filters_desc'] = [FILTER_DESC[f] for f in frozen[ct]['filters']]
    for ct in types_:
        for a in res['types'][ct]['arms']:
            a.pop('_dB', None)
            a['frozen'] = bool(frozen[ct] and frozen[ct]['id'] == a['id'])
    doc = {'schema': FROZEN_SCHEMA, 'prereg': PREREG, 'prereg_sha256': res['prereg_sha256'], 'code_sha': code_sha, 'params': P,
           'm': m, 'types': {ct: {'frozen': frozen[ct], 'falsified_at_discovery': frozen[ct] is None,
                                  'kept': [{k_: a[k_] for k_ in ('id', 'level', 'filters', 'rank_A', 'A', 'B', 'survivor')} for a in kept_all if a['ct'] == ct],
                                  'parts': parts_meta[ct]} for ct in types_},
           'split': {ct: {'A': [day_labels(SPLITS[ct]['A'])[0], day_labels(SPLITS[ct]['A'])[-1]],
                          'B': [day_labels(SPLITS[ct]['B'])[0], day_labels(SPLITS[ct]['B'])[-1]]} for ct in types_}}
    os.makedirs(out, exist_ok=True)
    body = canonical(doc)
    with open(os.path.join(out, 'frozen-cut.json'), 'wb') as f:
        f.write(body)
    sha = hashlib.sha256(body).hexdigest()
    with open(os.path.join(out, 'frozen-cut.sha256'), 'w') as f:
        f.write(f'{sha}  frozen-cut.json\n')
    res['frozen_sha256'] = sha
    res['frozen'] = frozen
    res['m'] = m
    with open(os.path.join(out, 'search.json'), 'w') as f:
        json.dump(clean(res), f, indent=1, sort_keys=True, allow_nan=False)
    with open(os.path.join(out, 'report-cut.md'), 'w') as f:
        f.write(search_md(res))
    log('frozen: ' + ', '.join(f'{ct} {frozen[ct]["id"] if frozen[ct] else "none (falsified at discovery)"}' for ct in types_)
        + f'; frozen-cut.json sha256 {sha}')
    return res


def prereg_sha() -> str | None:
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'prereg', 'OR-H3.md')
    if not os.path.isfile(p):
        return None
    with open(p, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


def fmtp(x) -> str:
    return '-' if x is None else f'{x:.2g}'


def search_md(res: dict) -> str:
    P = res['params']
    L = ['# OR-H3 loser cut: arm search (discovery A choose, B confirm)', '',
         f'Prereg {PREREG} (sha256 `{(res.get("prereg_sha256") or "?")[:16]}`). Code {str(res["code_sha"])[:7]}. Aggregates of '
         'discovery rows only (decision and horizon before 2026-08-01). 80 arms per type = 10 cut levels x 8 filter sets; '
         f'ranked on A by pooled $/day (zeros included); top {P["top"]} per type confirmed on B (stationary bootstrap, block '
         f'{P["block"]:g} days, {P["draws"]} draws; p = max(p_ev, p_up vs control)); BHY q {P["q"]} at m = {res["m"]}. '
         'B numbers of arms not kept are descriptive only.', '',
         'Cut levels: ' + '; '.join(f'{n_} = {level_desc(n_)}' for n_ in LEVEL_NAMES) + '. A cut sells at the side\'s bid only '
         'while tau > 60 s; a take-profit check comes first.', 'Filters: ' + '; '.join(f'{k_} {v}' for k_, v in FILTER_DESC.items()) + '.', '',
         f'frozen-cut.json sha256 `{res.get("frozen_sha256", "?")}`.', '']
    for ct, T in res['types'].items():
        fz = res['frozen'].get(ct)
        L += [f'## {ct}', '', f'Control (no cut, no filter): A ${T["control"]["A_usd_day"]:+.3f}/day over {T["A_days"]} days, '
              f'B ${T["control"]["B_usd_day"]:+.3f}/day over {T["B_days"]} days ({T["control"]["B_trades"]} trades). Parts: '
              + ', '.join(p['dir'] for p in T['parts']) + '.', '',
              f'**Frozen: {fz["id"]}** (B ${fz["B"]["usd_day"]:+.3f}/day, p {fmtp(fz["B"]["p"])}, p BHY {fmtp(fz["B"]["p_bhy"])})' if fz
              else '**Frozen: none: no kept arm survives BHY on B; OR-H3 is falsified at discovery for this type (nothing opens).**', '',
              '| A rank | arm | cut | filters | A trades | A cut | A $/day | B trades | B $/day | B - control $/day | p_ev | p_up | p BHY | survivor |',
              '|---|---|---|---|---|---|---|---|---|---|---|---|---|---|']
        for a in sorted(T['arms'], key=lambda a: a['rank_A']):
            b = a['B']
            L.append(f'| {a["rank_A"]} | {a["id"]}{" (frozen)" if a.get("frozen") else ""} | {a["level"]} | {"+".join(a["filters"]) or "-"} | '
                     f'{a["A"]["trades"]} | {a["A"]["cut_trades"]} | {a["A"]["usd_day"]:+.3f} | {b["trades"]} | {b["usd_day"]:+.3f} | '
                     f'{b["vs_control_usd_day"]:+.3f} | {fmtp(b.get("p_ev"))} | {fmtp(b.get("p_up"))} | {fmtp(b.get("p_bhy"))} | '
                     f'{("yes" if a.get("survivor") else "no") if a.get("kept") else "not kept"} |')
        L.append('')
    L += ['## Notes', '',
          '- Entries: every tradable decision of both sides, one position at a time per asset and window (event), the first '
          'tradable decision at or after the previous exit; decisions at one instant in a fixed pseudo-random order (the same '
          'for every arm): matched random entries.',
          '- F3 is k_z in {0, 1} as the prereg writes it: side-relative z < -0.75 (the side well out of the money); the '
          'prereg\'s gloss "spot within about one sigma of the strike" would be k_z 2-4.',
          '- Kalshi history is top-of-book, 1-minute candles: a cut fills at the candle\'s bid. Never compared to paper. NEVER DOGE.', '']
    return '\n'.join(L)


# ---------------------------------------------------------------- HO-1

def load_frozen_cut(path: str, sha256: str | None = None) -> tuple:
    with open(path, 'rb') as f:
        body = f.read()
    got = hashlib.sha256(body).hexdigest()
    if sha256 and HEX64.fullmatch(sha256.strip().lower()):
        want, src = sha256.strip().lower(), '--sha256'
    else:
        src = sha256 or os.path.join(os.path.dirname(os.path.abspath(path)), 'frozen-cut.sha256')
        if not os.path.isfile(src):
            raise SystemExit(f'{path}: no {os.path.basename(src)} to check its SHA-256 against: refused')
        m = HEX64.search(open(src).read().lower())
        if not m:
            raise SystemExit(f'{src}: no SHA-256 in it: refused')
        want = m.group(0)
    if got != want:
        raise SystemExit(f'frozen-cut.json sha256 {got[:16]}.. does not match {want[:16]}.. ({src}): refused, nothing scored')
    doc = json.loads(body)
    if not isinstance(doc, dict) or doc.get('schema') != FROZEN_SCHEMA:
        raise SystemExit(f'{path}: not an {FROZEN_SCHEMA} file')
    return doc, got


def load_cells_hold(ct: str, parts_root: str, cut_root: str, frozen_parts: list, order_seed: int, log=print) -> list:
    """HO-1 cells: rows t in [HOLD_FROM, HOLD_TO) only (binary search on the sorted t), the frozen file's own parts and
    sidecars (dir, rows, builder code sha, labels sha256), with windows/ for the placebo and the variants."""
    from .sim import ArrayPart
    have = {os.path.basename(p): p for p in list_parts(parts_root, ct)}
    cells = []
    for i, e in enumerate(frozen_parts):
        if e['dir'] not in have:
            raise SystemExit(f'part {e["dir"]} of the frozen file is not under {parts_root}: refused')
        p = have[e['dir']]
        part = Part(p)
        if part.n != int(e['rows_total']) or part.meta.get('code_sha') != e.get('code_sha'):
            raise SystemExit(f'{e["dir"]}: not the part the search read (rows / builder code): refused')
        sc = Part(sidecar_path(cut_root, p))
        check_sidecar(sc, part)
        if sc.meta.get('labels_sha256') != e.get('labels_sha256'):
            raise SystemExit(f'{e["dir"]}: cut labels sha256 differs from the searched ones: refused')
        tm = part['t']
        lo, hi = int(np.searchsorted(tm, HOLD_FROM, 'left')), int(np.searchsorted(tm, HOLD_TO, 'left'))
        t = np.array(tm[lo:hi], dtype=np.int64)
        check_rows(sc, t, lo, hi)
        sides = part.meta['sides']
        h = int(part.meta['horizons'][0])
        arrays = {'t': t}
        names = ['group', 'asset', 'X', 'event', 'kmin'] + [f'stratum_{s}' for s in sides]
        names += [key(nm, s, h) for s in sides for nm in ('ok', 'trade', 'hold', 'hit')]
        for nm in names:
            if part.has(nm):
                arrays[nm] = np.array(part[nm][lo:hi])
        v = ArrayPart(dict(part.meta, part_dir=e['dir'], rows_total=part.n), arrays, p)
        lab = {nm: np.array(sc[f'{nm}'][lo:hi]) for nm in [f'{a}_{s}{h}_{lv}' for a in ('tradeCut', 'holdCut', 'cutMin', 'tradeCutSettle')
                                                            for s in sides for lv in LEVEL_NAMES]}
        win = np.array(sc['win'][lo:hi], dtype=np.int64)
        wp = Part(os.path.join(sc.path, 'windows'))
        windows = {k_: np.asarray(wp[k_]) for k_ in ('bid', 'ask', 'settle')}
        c = Cell(v, lab, 'H', i, order_seed, windows, win)
        c.lab, c.lo, c.hi = lab, lo, hi
        cells.append(c)
    log(f'{ct} HO-1: ' + ', '.join(f'{c.scope} {c.U} units' for c in cells))
    return cells


def draw_cells(c: Cell, fset, cand0, rng) -> np.ndarray:
    """The placebo's filter replacement: per (stratum, UTC day) cell, as many candidates dropped at random as the filters
    drop there."""
    fm = c.filtered(fset) & cand0
    drop = np.zeros(c.U, dtype=bool)
    if not fm.any():
        return drop
    cid = c.stratum * 100_000 + c.day
    idx = np.nonzero(cand0)[0]
    k_ = rng.random(len(idx))
    o = np.lexsort((k_, cid[idx]))
    si = idx[o]
    cs = cid[si]
    start = np.r_[0, np.nonzero(np.diff(cs))[0] + 1]
    first = np.repeat(start, np.diff(np.r_[start, len(cs)]))
    rank = np.arange(len(si)) - first
    u, inv = np.unique(cid[fm], return_counts=True)
    need = dict(zip(u.tolist(), inv.tolist()))
    want = np.array([need.get(int(x), 0) for x in cs], dtype=np.int64)
    drop[si[rank < want]] = True
    return drop


def placebo_trades(cells: list, level: str, fset, taken: list, seeds: int, seed: int) -> tuple:
    """The OR-H3 placebo's trades per seed: ([(t, usd)] over seeds x cells, info averaged per seed). Every unit the arm
    would cut exits instead at k + d, d drawn from the arm's taken cut offsets (cut minute - k) in the unit's stratum
    (pooled over the type's parts; the type's pooled offsets when the stratum has none; every cut-labelled candidate's
    offsets when the arm took no cut trade); the filters are replaced by draw_cells. Take-profit first, as the arm."""
    po_s, po_d = [], []
    for c, tk in zip(cells, taken):
        m = c.cutmin[level][tk] >= 0
        po_s.append(c.stratum[tk][m]); po_d.append((c.cutmin[level][tk] - c.kmin[tk])[m])
    ps, pdd = np.concatenate(po_s), np.concatenate(po_d)
    pooled_from = 'taken'
    if not len(ps):
        pooled_from = 'candidates'
        for c in cells:
            m = (c.cutmin[level] >= 0) & np.isfinite(c.trade[level])
            ps = np.r_[ps, c.stratum[m]]; pdd = np.r_[pdd, (c.cutmin[level] - c.kmin)[m]]
    o = np.argsort(ps, kind='stable')
    ps, pdd = ps[o].astype(np.int64), pdd[o].astype(np.int64)
    info = {'cut_offsets': int(len(ps)), 'offsets_from': pooled_from, 'forced_exits': 0, 'forced_same_stratum': 0,
            'dropped': 0, 'trades': 0}
    out = []
    for s in range(int(seeds)):
        rng = np.random.default_rng([int(seed) & 0xFFFFFFFF, s])
        for c in cells:
            tr0 = c.trade[level]
            cand0 = np.isfinite(tr0)
            drop = draw_cells(c, fset, cand0, rng)
            trp, hop = tr0.copy(), c.hold[level].copy()
            cu = np.nonzero((c.cutmin[level] >= 0) & cand0 & ~drop)[0]
            if len(cu) and len(ps):
                lo, hi = np.searchsorted(ps, c.stratum[cu], 'left'), np.searchsorted(ps, c.stratum[cu], 'right')
                u = rng.random(len(cu))
                same = hi > lo
                pick = np.where(same, lo + (u * (hi - lo)).astype(np.int64), (u * len(ps)).astype(np.int64))
                d = pdd[np.minimum(pick, len(ps) - 1)]
                pth = c.paths(cu)
                r = pth.exit(pth.forced_mask(c.kmin[cu] + d))
                trp[cu], hop[cu] = r['trade'], r['hold']
                info['forced_exits'] += len(cu); info['forced_same_stratum'] += int(same.sum())
            tk = c.take(level, (), drop=drop, trade=trp, hold=hop)
            out.append((c.t[tk], trp[tk]))
            info['dropped'] += int(drop.sum()); info['trades'] += len(tk)
    for k_ in ('forced_exits', 'forced_same_stratum', 'dropped', 'trades'):
        info[k_] = info[k_] / max(1, int(seeds))
    return out, info


def variant_trade(c: Cell, level: str, name: str) -> tuple:
    """(per unit $, per unit hold in minutes from the decision) of a descriptive variant: settle (non-TP, non-cut exits
    settle at the close), lat (+1 minute entry), cost (+1c)."""
    if name == 'settle':
        ride = np.isfinite(c.tsettle[level]) & (c.tsettle[level] != c.trade[level])
        return c.tsettle[level], np.where(ride, c.v.meta['window_min'] - c.kmin, c.hold[level])
    idx = np.nonzero(np.isfinite(c.trade['none']))[0]
    out, hold = np.full(c.U, np.nan), np.array(c.hold[level], dtype=np.float64)
    if not len(idx):
        return out, hold
    shift = 1 if name == 'lat' else 0
    pth = c.paths(idx, k_shift=shift) if name == 'lat' else c.paths(idx, cost=0.01)
    r = pth.exit(pth.cut_mask(level))
    out[idx] = r['trade']
    hold[idx] = r['hold'] + shift
    return out, hold


def run_ho1(a) -> dict:
    from .ho1 import HOLD_DAYS, HOLD_HOURS, HOLD_SPAN, TERCILES, Strata, load_registry, make_id
    log = log_to(a.quiet)
    doc, sha = load_frozen_cut(a.frozen, a.sha256)
    ct = a.ct
    if ct not in CUT_TYPES or ct not in doc['types']:
        raise SystemExit(f'{ct}: not a type of the frozen file')
    T = doc['types'][ct]
    fz = T.get('frozen')
    if not fz:
        raise SystemExit(f'{ct}: nothing frozen (OR-H3 falsified at discovery for {ct}): nothing opens')
    reg, reg_path, reg_sha = load_registry(a.registry)
    P = dict(PARAMS, **doc.get('params', {}))
    code_sha = a.code_sha or git_code_sha()
    fam = f'oracle-{ct}-cut-v1'
    level, fset = fz['level'], tuple(fz['filters'])
    log(f'{ct}: frozen-cut.json sha256 {sha} verified; frozen arm {fz["id"]}; registry {reg_path}')
    cells = load_cells_hold(ct, a.parts, a.cut_labels, T['parts'], int(P['order_seed']), log)
    hps = [types.SimpleNamespace(assets=c.assets, scope=c.scope) for c in cells]
    strata = Strata(ct, a.regime, hps)
    span = HOLD_SPAN
    nd = len(HOLD_DAYS)

    def book(level_, fset_, trade_of=None):
        daily, terc, folds = np.zeros(nd), {k_: 0.0 for k_ in TERCILES}, np.zeros(6)
        taken, trades, cuts, hits = [], 0, 0, 0
        for c in cells:
            tk = c.take(level_, fset_)
            taken.append(tk)
            usd = c.trade[level_][tk]
            if trade_of is not None:
                alt, alt_hold = trade_of(c)
                tk2 = c.take(level_, fset_, trade=alt, hold=alt_hold)
                usd, tk = alt[tk2], tk2
            t = c.t[tk]
            daily += daily_vec(t, usd, span)
            rv = strata.label(hps, t)
            for j, nm in enumerate(TERCILES):
                terc[nm] += float(usd[rv == j].sum())
            f = fold_of(t)
            folds += np.bincount(f[f >= 0], usd[f >= 0], 6)
            trades += len(tk)
            cuts += int((c.cutmin[level_][tk] >= 0).sum())
            hits += int((usd > 0).sum())
        return {'daily': daily, 'terc': terc, 'folds': folds, 'taken': taken, 'trades': trades, 'cut_trades': cuts,
                'win_share': hits / trades if trades else None}

    arm = book(level, fset)
    ctl = book('none', ())
    pseed = (zlib.crc32(f'{fz["id"]}:placebo'.encode()) ^ int(P['seed'])) & 0x7FFFFFFF
    ptr, pinfo = placebo_trades(cells, level, fset, arm['taken'], int(P['seeds']), pseed)
    ns = max(1, int(P['seeds']))
    pdaily = np.zeros(nd)
    pterc = {k_: 0.0 for k_ in TERCILES}
    for t_, u_ in ptr:
        pdaily += daily_vec(t_, u_, span) / ns
        rv = strata.label(hps, t_)
        for j, nm in enumerate(TERCILES):
            pterc[nm] += float(u_[rv == j].sum()) / ns
    hours = strata.hours(hps)
    tercs = lambda d: {k_: {'pnl': round(d[k_], 6), 'hours': round(hours.get(k_, 0.0), 3)} for k_ in TERCILES}
    aseed = (zlib.crc32(fz['id'].encode()) ^ int(P['seed'])) & 0x7FFFFFFF
    ev = stationary_bootstrap_test(arm['daily'], P['block'], int(P['draws']), aseed)
    up = stationary_bootstrap_test(arm['daily'] - ctl['daily'], P['block'], int(P['draws']), aseed + 1)
    variants = {}
    for nm in ('settle', 'lat', 'cost'):
        b = book(level, fset, trade_of=lambda c, nm=nm: variant_trade(c, level, nm))
        variants[nm] = {'usd_day': float(b['daily'].mean()), 'usd_total': float(b['daily'].sum()), 'trades': b['trades']}
    cb = book('none', (), trade_of=lambda c: variant_trade(c, 'none', 'settle'))
    variants['control_settle'] = {'usd_day': float(cb['daily'].mean()), 'usd_total': float(cb['daily'].sum()), 'trades': cb['trades']}

    # --- registry rows
    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    ref = f'https://github.com/Wickedrad/coinbaseTraderBot/actions/runs/{a.run}' if re.fullmatch(r'[0-9]+', str(a.run)) else str(a.run)
    data = {'source': 'history', 'days': list(HOLD_DAYS), 'doge': False, 'metric': 'usd', 'engine': 'oracle'}
    common = {'v': 1, 'ts': now, 'thread': THREAD, 'family': fam, 'code_sha': code_sha, 'seed': None, 'contract_type': 'price_prediction',
              'hours': HOLD_HOURS, 'base': f'oracle-setups@{code_sha}', 'ref': ref, 'flags': [f'frozen-cut-sha256:{sha[:16]}', 'OR-H3'],
              'code_epoch': 'oracle-setups OR-H3 loser-cut HO-1 (python/oracle/cut.py ho1 on the oracle parts + cut labels; no TS replay)',
              'modules': ['oracle-setups', 'exit-cut'] + (['contract-state'] if fset else [])}
    base_env = {'ORACLE_SIZE_USD': f'{SIZE[ct]:g}', 'ORACLE_ENTRIES': 'every tradable decision, both sides, one position per asset and window, matched random order',
                'ORACLE_FROZEN_SHA256': sha[:16]}

    def row(arm_name, role, env, daily, terc, extra):
        r = dict(common, arm=arm_name, role=role, env=env, data=dict(data, days=list(HOLD_DAYS)), flags=list(common['flags']),
                 by_day={d: round(float(x), 6) for d, x in zip(HOLD_DAYS, daily)}, by_tercile=terc, **extra)
        r['trial_id'] = make_id(THREAD, fam, arm_name, code_sha, HOLD_DAYS, None, None, env)
        if r['trial_id'] != reg.make_id(THREAD, fam, arm_name, code_sha, list(HOLD_DAYS), None, None, env):
            raise SystemExit('make_id differs from research/registry.py make_id')
        return r

    raw = {'run': str(a.run), 'ct': ct, 'frozen_cut_sha256': sha, 'parts': [c.v.meta['part_dir'] for c in cells]}
    ctl_row = row('control', 'control', dict(base_env, ORACLE_CUT='none', ORACLE_FILTERS='none', ORACLE_EXIT='OR-H1 primary'),
                  ctl['daily'], tercs(ctl['terc']), {'fills': ctl['trades'], 'verdict': 'control: the same entries, no cut, no filter',
                                                     'raw': dict(raw, ho1={'trades': ctl['trades'], 'usd_total': float(ctl['daily'].sum())})})
    env = dict(base_env, ORACLE_CUT=f'{level}: {level_desc(level)} while tau > 60 s, take-profit first',
               ORACLE_FILTERS=','.join(fset) or 'none', ORACLE_EXIT='OR-H3 cut, then the OR-H1 end rule', ORACLE_ARM=fz['id'])
    cand = row(fz['id'], 'candidate', env, arm['daily'], tercs(arm['terc']),
               {'control': ctl_row['trial_id'], 'fills': arm['trades'],
                'raw': dict(raw, ho1={'trades': arm['trades'], 'cut_trades': arm['cut_trades'], 'usd_total': float(arm['daily'].sum()),
                                      'p_ev': ev['p'], 'p_up': up['p'], 'placebo_usd_total': float(pdaily.sum())})})
    penv = dict(env, ORACLE_PLACEBO=f'cut trades exited at a random minute from the arm\'s cut-minute distribution in the same stratum; '
                                    f'filters replaced by skipping the same count at random within stratum and day; {P["seeds"]} seeds averaged')
    plac = row(f'{fz["id"]}:placebo', 'placebo', penv, pdaily, tercs(pterc),
               {'control': ctl_row['trial_id'], 'placebo_for': fz['id'], 'fills': arm['trades'], 'verdict': f'placebo of {fz["id"]}',
                'raw': dict(raw, placebo=pinfo)})
    rows = [ctl_row, cand, plac]
    reg.ho1_fill(rows)
    ok, why = reg.ho1_pass(cand['heldout'], reg.contract_type_of(cand), cand['data'].get('engine'))
    net_pos = bool(arm['daily'].sum() > 0)
    reasons = ([f'HO-1: {why}'] if not ok else []) + ([] if net_pos else ['not net positive on HO-1'])
    verdict = {'pass': bool(ok and net_pos), 'ho1_pass': bool(ok), 'ho1_why': why, 'net_positive': net_pos,
               'beats_placebo': bool(arm['daily'].sum() > pdaily.sum()), 'beats_control': bool(arm['daily'].sum() > ctl['daily'].sum()),
               'p_ev': ev['p'], 'p_up': up['p'], 'why': reasons}
    cand['verdict'] = ('OR-H3 HO-1 PASS' if verdict['pass'] else 'OR-H3 HO-1 fail: ' + '; '.join(reasons)) + \
        f' (${arm["daily"].sum() / HOLD_HOURS:+.4f}/h vs control ${ctl["daily"].sum() / HOLD_HOURS:+.4f}/h)'
    cand['raw']['verdict'] = {k_: verdict[k_] for k_ in ('pass', 'ho1_pass', 'net_positive', 'beats_placebo', 'beats_control')}
    bad = []
    for r in rows:
        err, fl = reg.validate(r)
        if err:
            bad.append(f'{r["arm"]}: {"; ".join(err)}')
        r['flags'] = sorted(set((r.get('flags') or []) + fl))
    if bad:
        raise SystemExit('invalid registry rows (nothing written):\n  ' + '\n  '.join(bad))

    lockbox = lockbox_cut(a.lockbox, ct, cells, level, span, log) if a.lockbox else None
    fold_ctl = ctl['folds']
    summary = {'schema': 'oracle-cut-ho1-1', 'ct': ct, 'family': fam, 'thread': THREAD, 'prereg': PREREG, 'frozen_cut_sha256': sha,
               'arm': fz['id'], 'level': level, 'level_desc': level_desc(level), 'filters': list(fset), 'run': str(a.run),
               'code_sha': code_sha, 'registry_sha256': reg_sha, 'params': P,
               'hold': {'from': HOLD_DAYS[0], 'to': HOLD_DAYS[-1], 'days': nd, 'hours': HOLD_HOURS},
               'parts': [{'dir': c.v.meta['part_dir'], 'hold_units': c.U} for c in cells],
               'arm_ho1': {'trades': arm['trades'], 'cut_trades': arm['cut_trades'], 'win_share': arm['win_share'],
                           'usd_total': float(arm['daily'].sum()), 'usd_day': float(arm['daily'].mean()), 'usd_per_hour': float(arm['daily'].sum() / HOLD_HOURS),
                           'fold_usd': arm['folds'].tolist(), 'by_tercile': tercs(arm['terc'])},
               'control_ho1': {'trades': ctl['trades'], 'win_share': ctl['win_share'], 'usd_total': float(ctl['daily'].sum()),
                               'usd_day': float(ctl['daily'].mean()), 'usd_per_hour': float(ctl['daily'].sum() / HOLD_HOURS),
                               'fold_usd': fold_ctl.tolist(), 'by_tercile': tercs(ctl['terc'])},
               'placebo_ho1': {'usd_total': float(pdaily.sum()), 'usd_day': float(pdaily.mean()), 'info': pinfo, 'by_tercile': tercs(pterc)},
               'folds_won_vs_control': int(np.sum(arm['folds'] > fold_ctl)), 'heldout': cand['heldout'], 'verdict': verdict,
               'variants': variants, 'lockbox_candidates': lockbox,
               'trial_ids': {'control': ctl_row['trial_id'], 'candidate': cand['trial_id'], 'placebo': plac['trial_id']}}
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, 'rows.jsonl'), 'w') as f:
        for r in rows:
            f.write(json.dumps(clean(r), sort_keys=True, allow_nan=False) + '\n')
    with open(os.path.join(a.out, 'ho1-cut.json'), 'w') as f:
        json.dump(clean(summary), f, indent=1, sort_keys=True, allow_nan=False)
    with open(os.path.join(a.out, 'ho1-cut.md'), 'w') as f:
        f.write(ho1_md(summary))
    log(f'{ct} {fz["id"]}: HO-1 ${summary["arm_ho1"]["usd_total"]:+.2f} vs control ${summary["control_ho1"]["usd_total"]:+.2f}, '
        f'placebo ${summary["placebo_ho1"]["usd_total"]:+.2f}: {"PASS" if verdict["pass"] else "fail"}')
    return {'summary': summary, 'rows': rows}


def lockbox_cut(path: str, ct: str, cells: list, level: str, span, log=print) -> dict:
    """Descriptive: the frozen cut on the OR-AMEND-1 lockbox candidates' HO-1 trades. Each candidate setup trades its own
    entries (sim.fire_mask on its side's HO-1 rows, OR-H1 one position per asset: sim.busy_key) once with the OR-H1 primary
    exit (the part's trade / hold) and once with the frozen cut (the sidecar's tradeCut / holdCut at the frozen level).
    Never selected on."""
    from .common import is_pooled
    with open(path) as f:
        doc = json.load(f)
    if doc.get('ct') not in (None, ct):
        raise SystemExit(f'{path}: lockbox candidates of {doc.get("ct")}, not {ct}')
    out = []
    for s in doc.get('setups') or []:
        if 'DOGE' in str(s.get('scope', '')).upper():
            raise SystemExit('DOGE refused')
        h, side = int(s['h']), s['side']
        tot = {'primary': np.zeros(int(-(-span[1] // DAY) - span[0] // DAY)), 'cut': None}
        tot['cut'] = np.zeros_like(tot['primary'])
        n_tr = {'primary': 0, 'cut': 0}
        cut_n = 0
        for c in cells:
            if not (s['scope'] == c.scope or is_pooled(s['scope'])) or h != c.h:
                continue
            v = c.v
            tr = np.asarray(v[key('trade', side, h)], dtype=np.float64)
            st = np.asarray(v[f'stratum_{side}'], dtype=np.int64)
            B = np.nonzero((np.asarray(v[key('ok', side, h)]) == 1) & (st >= 0) & np.isfinite(tr) & (split_rows(v, h) == 'H'))[0]
            if not len(B):
                continue
            fire = fire_mask(v, s, B)
            t = np.asarray(v['t'], dtype=np.int64)[B]
            busy = busy_key(v)[B]
            for nm, trade, hold in (('primary', tr[B], np.asarray(v[key('hold', side, h)], dtype=np.float64)[B]),
                                    ('cut', np.asarray(c.lab[f'tradeCut_{side}{h}_{level}'], dtype=np.float64)[B],
                                     np.asarray(c.lab[f'holdCut_{side}{h}_{level}'], dtype=np.float64)[B])):
                rel = trade_sim(t, hold, trade, fire, busy)
                tot[nm] += daily_vec(t[rel], trade[rel], span)
                n_tr[nm] += len(rel)
                if nm == 'cut':
                    cut_n += int((np.asarray(c.lab[f'cutMin_{side}{h}_{level}'])[B][rel] >= 0).sum())
        out.append({'id': s.get('id'), 'rank_lockbox': s.get('rank_lockbox'), 'scope': s['scope'], 'side': side, 'h': h,
                    'items': s.get('items'), 'primary': {'trades': n_tr['primary'], 'usd_day': float(tot['primary'].mean()),
                                                         'usd_total': float(tot['primary'].sum())},
                    'cut': {'trades': n_tr['cut'], 'cut_trades': cut_n, 'usd_day': float(tot['cut'].mean()), 'usd_total': float(tot['cut'].sum())}})
    log(f'lockbox candidates ({path}): {len(out)} scored with the frozen cut (descriptive)')
    return {'source': os.path.basename(path), 'rule_sha256': doc.get('rule_sha256'), 'n': len(out), 'setups': out,
            'sum_primary_usd_day': float(sum(x['primary']['usd_day'] for x in out)),
            'sum_cut_usd_day': float(sum(x['cut']['usd_day'] for x in out))}


def ho1_md(S: dict) -> str:
    a, c, p, v = S['arm_ho1'], S['control_ho1'], S['placebo_ho1'], S['verdict']
    h = S['heldout']
    L = [f'# OR-H3 loser cut HO-1: {S["ct"]} ({S["family"]})', '',
         f'Prereg {PREREG} "HO-1". Scored once on Aug 1 - Nov 4 2026 (96 days, 2,304 h); aggregates only. frozen-cut.json '
         f'sha256 `{S["frozen_cut_sha256"]}`. Never compared to paper. NEVER DOGE.', '',
         f'Frozen arm **{S["arm"]}**: cut {S["level_desc"]} (tau > 60 s, take-profit first), filters '
         f'{", ".join(S["filters"]) or "none"}.', '',
         f'**Verdict: {"PASS" if v["pass"] else "fail"}**' + ('' if v['pass'] else ': ' + '; '.join(v['why'])), '',
         '| row | trades | $ total | $/day | $/h | win share | folds $ (16-day) |', '|---|---|---|---|---|---|---|',
         f'| arm | {a["trades"]} ({a["cut_trades"]} cut) | {a["usd_total"]:+.2f} | {a["usd_day"]:+.3f} | {a["usd_per_hour"]:+.4f} | '
         f'{fmtp(a["win_share"])} | ' + ' / '.join(f'{x:+.1f}' for x in a['fold_usd']) + ' |',
         f'| control (no cut, no filter) | {c["trades"]} | {c["usd_total"]:+.2f} | {c["usd_day"]:+.3f} | {c["usd_per_hour"]:+.4f} | '
         f'{fmtp(c["win_share"])} | ' + ' / '.join(f'{x:+.1f}' for x in c['fold_usd']) + ' |',
         f'| placebo ({S["params"]["seeds"]} seeds) | {p["info"]["trades"]:.0f} | {p["usd_total"]:+.2f} | {p["usd_day"]:+.3f} | '
         f'{p["usd_total"] / S["hold"]["hours"]:+.4f} | - | - |', '',
         f'Registry ho1_pass (vs the control row): {h.get("days")} days, folds won {h.get("folds_won")}/{h.get("folds")}, worst fold '
         f'{fmtp(h.get("worst_fold_per_hour"))} $/h, terciles won {h.get("terciles_won")}/{h.get("terciles_covered")}, worst tercile '
         f'{fmtp(h.get("worst_tercile_per_hour"))} $/h, beats placebo {h.get("beats_placebo")} -> {"pass" if v["ho1_pass"] else "fail: " + v["ho1_why"]}. '
         f'Net positive: {v["net_positive"]}. p_ev {fmtp(v["p_ev"])}, p_up vs control {fmtp(v["p_up"])} (reported, not gating).', '',
         '| tercile | arm $ | control $ | placebo $ | hours |', '|---|---|---|---|---|']
    for k_ in a['by_tercile']:
        L.append(f'| {k_} | {a["by_tercile"][k_]["pnl"]:+.2f} | {c["by_tercile"][k_]["pnl"]:+.2f} | {p["by_tercile"][k_]["pnl"]:+.2f} | '
                 f'{a["by_tercile"][k_]["hours"]:.0f} |')
    vv = S['variants']
    L += ['', '## Descriptive (never selected on)', '', '| variant | trades | $/day | $ total |', '|---|---|---|---|']
    for nm, lab in (('settle', 'arm, settle at close (no final-candle sale)'), ('control_settle', 'control, settle at close'),
                    ('lat', 'arm, +1 minute entry latency'), ('cost', 'arm, +1c entry cost')):
        L.append(f'| {lab} | {vv[nm]["trades"]} | {vv[nm]["usd_day"]:+.3f} | {vv[nm]["usd_total"]:+.2f} |')
    lb = S.get('lockbox_candidates')
    if lb:
        L += ['', f'### The frozen cut on the {lb["n"]} OR-AMEND-1 lockbox candidates of {S["ct"]} (their HO-1 trades)', '',
              '| # | setup | scope | side h | primary trades | primary $/day | cut trades (cut) | cut $/day |', '|---|---|---|---|---|---|---|---|']
        for x in lb['setups']:
            L.append(f'| {x.get("rank_lockbox") or "-"} | {x["id"]} | {x["scope"]} | {x["side"]} {x["h"]} | {x["primary"]["trades"]} | '
                     f'{x["primary"]["usd_day"]:+.3f} | {x["cut"]["trades"]} ({x["cut"]["cut_trades"]}) | {x["cut"]["usd_day"]:+.3f} |')
        L.append(f'| | sum | | | | {lb["sum_primary_usd_day"]:+.3f} | | {lb["sum_cut_usd_day"]:+.3f} |')
    pi = p['info']
    L += ['', '## Notes', '',
          f'- Placebo: per seed {pi["forced_exits"]:.0f} would-be cut trades exited at a random offset ({pi["forced_same_stratum"]:.0f} from '
          f'the same stratum; {pi["cut_offsets"]} offsets from the arm\'s {pi["offsets_from"]} cut trades), {pi["dropped"]:.0f} decisions '
          'skipped at random within stratum and day in place of the filters.',
          '- Kalshi history is top-of-book, 1-minute candles: a cut fills at the candle\'s bid. The live exit must be a tagged '
          'exit that pacing / take-profit floors cannot pre-empt (OR-H3 "Known limits").', '']
    return '\n'.join(L)


# ---------------------------------------------------------------- CLI

def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description='OR-H3 loser cut (python/oracle/prereg/OR-H3.md): labels, arm search, HO-1.')
    sub = ap.add_subparsers(dest='cmd', required=True)
    lb = sub.add_parser('labels', help='cut labels (sidecar) of one pp part, recomputed from the Kalshi history')
    lb.add_argument('--kind', type=int, required=True, choices=(15, 60))
    lb.add_argument('--history', required=True)
    lb.add_argument('--part', required=True)
    lb.add_argument('--out', required=True)
    lb.add_argument('--code-sha', default=None)
    lb.add_argument('--quiet', action='store_true')
    se = sub.add_parser('search', help='the 80-arm search per type on discovery A / B; writes frozen-cut.json')
    se.add_argument('--parts', required=True)
    se.add_argument('--cut-labels', required=True)
    se.add_argument('--out', required=True)
    se.add_argument('--types', default=','.join(CUT_TYPES))
    se.add_argument('--code-sha', default=None)
    se.add_argument('--quiet', action='store_true')
    ho = sub.add_parser('ho1', help='score the frozen arm of one type once on HO-1')
    ho.add_argument('--frozen', required=True)
    ho.add_argument('--sha256', default=None)
    ho.add_argument('--ct', required=True, choices=CUT_TYPES)
    ho.add_argument('--parts', required=True)
    ho.add_argument('--cut-labels', required=True)
    ho.add_argument('--regime', required=True, help='regime v1 labels.csv[.gz] (RV terciles)')
    ho.add_argument('--registry', default=None)
    ho.add_argument('--out', required=True)
    ho.add_argument('--run', default='local')
    ho.add_argument('--code-sha', default=None)
    ho.add_argument('--lockbox', default=None, help='lockbox_candidates.json of the OR-AMEND-1 all-confirmed trial (descriptive)')
    ho.add_argument('--quiet', action='store_true')
    return ap


def main(argv=None):
    a = parser().parse_args(argv)
    if a.cmd == 'labels':
        return build_labels(a.kind, a.history, a.part, a.out, a.code_sha, log_to(a.quiet))
    if a.cmd == 'search':
        tps = tuple(x.strip() for x in a.types.split(',') if x.strip())
        if not tps or any(x not in CUT_TYPES for x in tps):
            raise SystemExit(f'--types: {CUT_TYPES}')
        return search(a.parts, a.cut_labels, a.out, a.code_sha, tps, None, log_to(a.quiet))
    return run_ho1(a)


if __name__ == '__main__':
    main()
