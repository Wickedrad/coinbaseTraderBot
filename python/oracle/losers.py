"""Loser study of the oracle-setups study (Steven, 2026-11-06 14:03 UTC: "figure out why losers are losing"; recorded in
python/oracle/prereg/OR-AMEND-1.md). Descriptive only: nothing here selects, freezes or re-ranks a setup.

    cd python && python3 -m oracle.losers --ct perp --parts <dir> --confirm confirm.jsonl --out out/losers [--ho1] \
        [--min-support 30] [--top 15] [--quiet]

For every setup of the miner's confirm.jsonl, its trades are the confirmation step's own (oracle/mine.py PartB.trade_on:
sim.fire_mask, sim.trade_sim with sim.busy_key, one position at a time per asset / event, the part's primary-exit trade $
and hold), on
- discovery B rows: the rows of split B (sim.split_rows) whose whole horizon ends before DEV_END (common.dev_rows), read
  from the part with a binary search on the sorted t (rows from the start of B to DEV_END - min(h) only: nothing from the
  hold is read), and,
- only with --ho1, HO-1 rows (ho1.HoldPart: t in [HOLD_FROM, HOLD_TO), split H), reported separately. Use --ho1 only once
  HO-1 has been opened for every confirmed setup of the type (the workflow runs it inside the all-confirmed HO-1 job).
Each trade is a winner (trade $ > 0) or a loser (trade $ <= 0). Per contract type and per setup:
- loser share, mean loser $, mean winner $, total $;
- how losers exit: take-profit (never a loser), stop (perp-rev: no take-profit and an exit before the horizon), settlement
  (tennis: the market closed inside the horizon; Price Prediction: the ride to settlement), time (perp / perp-rev: the
  taker exit at the horizon; Price Prediction: the sale at the final candle; tennis: the sale at minute k+H);
- the share of losers whose best_ (the hindsight best net $ at a tradable price within h) was > $0, >= $1, >= half the
  target and >= the target: an UPPER BOUND on what an earlier / smaller take-profit could have saved (best_ ignores path
  order: the best price may come after the stop, or after the take-profit level would have been missed);
- hold minutes (losers vs winners);
- feature states (sim.items_of: state +-1, bucket levels >= 0), the RV tercile (rv.npy) and the 4-hour UTC hour bucket
  over-represented among losers vs winners: lift = (losers in the state / losers) / (winners in the state / winners), with
  +0.5 / +1 smoothing, only states with >= --min-support trades, the --top highest, with counts.
Pooled "what would fix it" table per contract type: a take-profit at 25 / 50 / 75 % of the target, scored with best_ as
an upper bound (a trade whose best_ reached the level exits there; others keep their $). Pooled tables add the trades of
every setup: one decision traded by several setups counts once per setup.
Outputs (--out): losers.md (aggregates only, public repo) and losers.json. NEVER DOGE.
"""
from __future__ import annotations

import argparse
import json
import os
import time

import numpy as np

from .common import (DEV_END, HORIZONS, MIN, SIDES, SPLITS, TARGET_USD, Part, dev_rows, group_of, is_pooled, key, list_parts,
                     pooled_name)
from .mine import assert_dev, clean
from .sim import ArrayPart, busy_key, fire_mask, items_of, split_rows, trade_sim

EXITS = ('take-profit', 'stop', 'settlement', 'time')
FIX_LEVELS = (0.25, 0.5, 0.75)
BEST_LEVELS = ('gt0', 'ge1', 'ge_half_target', 'ge_target')
TIME_DESC = {'perp': 'taker exit at the horizon', 'perp-rev': 'taker exit at the horizon', 'pp15': 'sale at the final candle bid',
             'pp60': 'sale at the final candle bid', 'tennis': 'sale at the bid at minute k+H'}
RV_NAMES = ('LOW', 'MID', 'HIGH')


def log_to(quiet: bool):
    t0 = time.time()
    return (lambda msg: None) if quiet else (lambda msg: print(f'[{time.time() - t0:7.1f}s] {msg}', flush=True))


# ---------------------------------------------------------------- rows

def _arrays(part: Part, lo: int, hi: int, sides: list, hs: list) -> dict:
    arrays = {'t': np.array(part['t'][lo:hi], dtype=np.int64)}
    names = ['group', 'asset', 'X', 'rv', 'hour', 'close', 'kmin', 'mkt', 'event', 'notional'] + [f'stratum_{s}' for s in sides]
    names += [key(nm, s, h) for s in sides for h in hs for nm in ('ok', 'hit', 'trade', 'hold', 'best', 'tradeSettle')]
    for nm in names:
        if part.has(nm):
            arrays[nm] = np.array(part[nm][lo:hi])
        elif nm in ('group', 'asset', 'X') or nm.startswith(('stratum_', 'ok_', 'hit_', 'trade_', 'hold_')):
            raise SystemExit(f'{part.path}: missing {nm}.npy')
    return arrays


def load_B(path: str, ct: str) -> ArrayPart:
    """The part's discovery-B window only: rows with t in [start of B, DEV_END - min(h)] (binary search on the memory-mapped,
    sorted t; earlier rows are not needed, since trade_sim over B reads B rows only, and nothing at or after DEV_END is
    touched)."""
    part = Part(path)
    if part.ct != ct:
        raise SystemExit(f'{path}: ct {part.ct!r} != {ct!r}')
    if 'DOGE' in str(part.scope).upper() or any('DOGE' in str(a).upper() for a in part.meta.get('assets', [])):
        raise SystemExit('DOGE part refused')
    sides = list(part.meta.get('sides') or SIDES[ct])
    hs = [int(h) for h in (part.meta.get('horizons') or HORIZONS[ct])]
    tm = part['t']
    lo = int(np.searchsorted(tm, SPLITS[ct]['B'][0], side='left'))
    hi = int(np.searchsorted(tm, DEV_END - min(hs) * MIN, side='right'))
    arrays = _arrays(part, lo, hi, sides, hs)
    assert_dev(arrays['t'], min(hs))
    meta = dict(part.meta, sides=sides, horizons=hs, part_dir=os.path.basename(os.path.normpath(path)), rows_total=part.n)
    return ArrayPart(meta, arrays, path)


def load_H(path: str, ct: str) -> ArrayPart:
    """The part's HO-1 rows (oracle.ho1.HoldPart: t in [HOLD_FROM, HOLD_TO), nothing at or after 2026-11-05)."""
    from .ho1 import HoldPart
    hp = HoldPart(path, ct, 0)
    hp.v.meta.update({'sides': hp.sides, 'horizons': hp.hs, 'part_dir': hp.dir})
    return hp.v


class Cell:
    """One part's rows of one split ('B' or 'H') for one (side, h): the confirmation's row rule (ok, stratum >= 0, finite
    trade $, the split by sim.split_rows; on B also dev_rows) and its trade simulation."""

    def __init__(self, v: ArrayPart, side: str, h: int, split: str):
        self.v, self.side, self.h, self.split = v, side, h, split
        t = v['t']
        self.t = t
        self.trade = v[key('trade', side, h)].astype(np.float64)
        self.hold = v[key('hold', side, h)].astype(np.float64)
        self.hit = v[key('hit', side, h)].astype(bool)
        st = v[f'stratum_{side}'].astype(np.int64)
        ok = (v[key('ok', side, h)] == 1) & (st >= 0) & np.isfinite(self.trade)
        if split == 'B':
            ok &= dev_rows(t, h)
        self.B = np.flatnonzero(ok & (split_rows(v, h) == split))
        if split == 'B':
            assert_dev(t[self.B], h)
        self.busy = busy_key(v)

    def taken(self, setup: dict) -> np.ndarray:
        """Part row indexes of the trades taken (sim.trade_sim over the split's rows, skip while busy)."""
        B = self.B
        fire = fire_mask(self.v, setup, B)
        rel = trade_sim(self.t[B], self.hold[B], self.trade[B], fire, self.busy[B])
        return B[rel]


def target_usd(v: ArrayPart, rows: np.ndarray) -> np.ndarray:
    """The take-profit target in $ per trade: $5 (OR-H1), or for a reversal part M net bps at its notional."""
    tb = v.meta.get('target_bps')
    if tb is None:
        return np.full(len(rows), TARGET_USD)
    notional = (np.asarray(v['notional'], dtype=np.float64)[rows] if v.has('notional')
                else np.full(len(rows), float(v.meta.get('notional_usd') or v.meta.get('size_usd'))))
    return notional * float(tb) / 1e4


def exit_kind(v: ArrayPart, side: str, h: int, rows: np.ndarray) -> np.ndarray:
    """Per trade an index into EXITS (see the module docstring; inferred from hit, hold, close / kmin / tradeSettle)."""
    ct = v.meta['ct']
    hit = v[key('hit', side, h)][rows].astype(bool)
    hold = v[key('hold', side, h)][rows].astype(np.int64)
    t = v['t'][rows].astype(np.int64)
    out = np.full(len(rows), EXITS.index('time'), dtype=np.int64)
    settle = np.zeros(len(rows), dtype=bool)
    if ct in ('pp15', 'pp60'):
        if v.has('kmin') and v.meta.get('window_min'):
            settle = v['kmin'][rows].astype(np.int64) + hold >= int(v.meta['window_min'])
        elif v.has(key('tradeSettle', side, h)):
            ts = v[key('tradeSettle', side, h)][rows].astype(np.float64)
            settle = np.isclose(ts, v[key('trade', side, h)][rows].astype(np.float64), atol=1e-6)
    elif v.has('close'):
        settle = t + hold * MIN >= v['close'][rows].astype(np.int64)
    out[settle] = EXITS.index('settlement')
    if v.meta.get('stop_bps') is not None:                    # perp-rev: a stop exits before the horizon
        out[~settle & (hold < h)] = EXITS.index('stop')
    out[hit] = EXITS.index('take-profit')
    return out


# ---------------------------------------------------------------- accumulation

class Acc:
    """Per setup (or pooled): the taken trades' $ / best / hold / exit / target and the loser / winner counts per state."""

    def __init__(self):
        self.cols = {k_: [] for k_ in ('trade', 'best', 'hold', 'exit', 'target')}
        self.states: dict = {}          # (feature, value) -> [losers, winners]

    def add(self, v: ArrayPart, side: str, h: int, rows: np.ndarray) -> None:
        if not len(rows):
            return
        tr = v[key('trade', side, h)][rows].astype(np.float64)
        bk = key('best', side, h)
        best = v[bk][rows].astype(np.float64) if v.has(bk) else np.full(len(rows), np.nan)
        self.cols['trade'].append(tr)
        self.cols['best'].append(best)
        self.cols['hold'].append(v[key('hold', side, h)][rows].astype(np.float64))
        self.cols['exit'].append(exit_kind(v, side, h, rows))
        self.cols['target'].append(target_usd(v, rows))
        lose = tr <= 0
        X = np.asarray(v['X'])[rows]
        items = items_of(v, side)
        if items:
            cols = np.array(sorted({it.col for it in items}), dtype=np.int64)
            pos = {int(c): i for i, c in enumerate(cols)}
            Xs = X[:, cols]
            vals = sorted({it.v for it in items})
            cnt = {}
            for val in vals:
                eq = Xs == val
                cnt[val] = (eq[lose].sum(axis=0), eq[~lose].sum(axis=0))
            for it in items:
                nl, nw = cnt[it.v][0][pos[it.col]], cnt[it.v][1][pos[it.col]]
                self._bump((it.f, int(it.v)), int(nl), int(nw))
        if v.has('rv'):
            rv = np.asarray(v['rv'])[rows].astype(np.int64)
            for j, nm in enumerate(RV_NAMES):
                self._bump(('RV tercile', nm), int(np.sum((rv == j) & lose)), int(np.sum((rv == j) & ~lose)))
        hr = (np.asarray(v['hour'])[rows].astype(np.int64) if v.has('hour') else (v['t'][rows] // 3_600_000) % 24) // 4
        for b in range(6):
            self._bump(('hour bucket UTC', f'{4 * b:02d}-{4 * b + 4:02d}h'), int(np.sum((hr == b) & lose)), int(np.sum((hr == b) & ~lose)))

    def _bump(self, k_, nl: int, nw: int) -> None:
        if nl or nw:
            c = self.states.setdefault(k_, [0, 0])
            c[0] += nl
            c[1] += nw

    def merge(self, other: 'Acc') -> None:
        for k_ in self.cols:
            self.cols[k_] += other.cols[k_]
        for k_, (nl, nw) in other.states.items():
            self._bump(k_, nl, nw)

    def arrays(self) -> dict:
        return {k_: (np.concatenate(v) if v else np.zeros(0)) for k_, v in self.cols.items()}


def lift_table(states: dict, n_lose: int, n_win: int, min_support: int, top: int) -> list:
    """States over-represented among losers vs winners (see the module docstring)."""
    if not n_lose or not n_win:
        return []
    out = []
    for (f, val), (nl, nw) in states.items():
        if nl + nw < min_support:
            continue
        sl, sw = nl / n_lose, nw / n_win
        lift = ((nl + 0.5) / (n_lose + 1)) / ((nw + 0.5) / (n_win + 1))
        out.append({'feature': f, 'value': val, 'losers': nl, 'winners': nw, 'share_losers': sl, 'share_winners': sw,
                    'loser_rate': nl / (nl + nw), 'lift': lift})
    out.sort(key=lambda r: (-r['lift'], -(r['losers'] + r['winners']), str(r['feature']), str(r['value'])))
    return out[:top]


def summarize(acc: Acc, min_support: int, top: int) -> dict:
    a = acc.arrays()
    tr, best, hold, ex, tg = a['trade'], a['best'], a['hold'], a['exit'].astype(np.int64), a['target']
    n = len(tr)
    lose = tr <= 0
    nl, nw = int(lose.sum()), int((~lose).sum())
    mean = lambda x: float(np.mean(x)) if len(x) else None
    med = lambda x: float(np.median(x)) if len(x) else None
    bl, tl = best[lose], tg[lose]
    fin = np.isfinite(bl)
    best_share = {'gt0': bl > 0, 'ge1': bl >= 1, 'ge_half_target': bl >= 0.5 * tl, 'ge_target': bl >= tl}
    out = {'trades': n, 'winners': nw, 'losers': nl, 'loser_share': nl / n if n else None,
           'usd_total': float(tr.sum()), 'loser_usd_total': float(tr[lose].sum()), 'winner_usd_total': float(tr[~lose].sum()),
           'mean_loser_usd': mean(tr[lose]), 'mean_winner_usd': mean(tr[~lose]),
           'loser_exits': {e: int(np.sum(ex[lose] == i)) for i, e in enumerate(EXITS)},
           'winner_exits': {e: int(np.sum(ex[~lose] == i)) for i, e in enumerate(EXITS)},
           'losers_with_best': int(fin.sum()),
           'loser_best_share': {k_: (float(np.sum(m & fin)) / int(fin.sum()) if fin.any() else None) for k_, m in best_share.items()},
           'mean_loser_best_usd': mean(bl[fin]),
           'hold_min': {'losers_mean': mean(hold[lose]), 'losers_median': med(hold[lose]), 'winners_mean': mean(hold[~lose]),
                        'winners_median': med(hold[~lose])},
           'target_usd_mean': mean(tg),
           'lift': lift_table(acc.states, nl, nw, min_support, top)}
    return out


def fix_table(acc: Acc) -> list:
    """Upper bound of a take-profit at 25 / 50 / 75 % of the target: a trade whose best_ reached the level exits there."""
    a = acc.arrays()
    tr, best, tg = a['trade'], a['best'], a['target']
    fin = np.isfinite(best)
    lose = tr <= 0
    out = []
    for frac in FIX_LEVELS:
        lvl = frac * tg
        reach = fin & (best >= lvl)
        new = np.where(reach, lvl, tr)
        d = new - tr
        out.append({'level_frac': frac, 'level_usd_mean': float(lvl.mean()) if len(lvl) else None, 'trades': int(len(tr)),
                    'losers_rescued': int(np.sum(reach & lose)), 'losers': int(lose.sum()),
                    'usd_recovered_on_losers': float(d[lose].sum()), 'usd_change_on_winners': float(d[~lose].sum()),
                    'winners_capped': int(np.sum(reach & ~lose & (tr > lvl))),
                    'usd_actual': float(tr.sum()), 'usd_upper_bound': float(new.sum()), 'usd_change': float(d.sum()),
                    'usd_per_trade_actual': float(tr.mean()) if len(tr) else None,
                    'usd_per_trade_upper_bound': float(new.mean()) if len(new) else None})
    return out


# ---------------------------------------------------------------- driver

def load_confirm(path: str, ct: str) -> list:
    out = []
    with open(path) as f:
        for line in f:
            if not line.strip():
                continue
            s = json.loads(line)
            if 'DOGE' in str(s.get('scope', '')).upper():
                raise SystemExit('DOGE setup refused')
            if s.get('ct') not in (None, ct) or s.get('side') not in SIDES[ct] or int(s.get('h', -1)) not in HORIZONS[ct]:
                raise SystemExit(f'setup {s.get("id")}: ct / side / horizon refused')
            out.append(s)
    return out


def scope_has(scope: str, v: ArrayPart) -> bool:
    return scope == v.scope or (is_pooled(scope) and scope == pooled_name(group_of(v.meta)))


def study(paths: list, ct: str, setups: list, split: str, min_support: int, top: int, log) -> dict:
    """Per setup accumulators over the parts, one part in memory at a time."""
    accs = {s['id']: Acc() for s in setups}
    rows_read = {}
    for p in paths:
        v = load_B(p, ct) if split == 'B' else load_H(p, ct)
        rows_read[v.meta['part_dir']] = int(v.n)
        cells = {}
        for s in setups:
            if not scope_has(s['scope'], v) or int(s['h']) not in v.meta['horizons']:
                continue
            k_ = (s['side'], int(s['h']))
            if k_ not in cells:
                cells[k_] = Cell(v, s['side'], int(s['h']), split)
            c = cells[k_]
            accs[s['id']].add(v, s['side'], int(s['h']), c.taken(s))
        log(f'  {split} {v.meta["part_dir"]}: {v.n} rows, {len(cells)} cells')
        del v, cells
    per = []
    pooled = Acc()
    for s in setups:
        a = accs[s['id']]
        pooled.merge(a)
        sm = summarize(a, min_support, top)
        sm.update({'id': s['id'], 'scope': s['scope'], 'side': s['side'], 'h': int(s['h']), 'items': s['items'],
                   'frozen': bool(s.get('frozen')), 'survivor': bool(s.get('survivor')), 'fix': fix_table(a)})
        per.append(sm)
    out = summarize(pooled, min_support, top)
    out.update({'setups_scored': len(setups), 'setups_traded': sum(1 for s in per if s['trades']), 'fix': fix_table(pooled),
                'rows_read': rows_read, 'setups': per})
    return out


def items_str(items) -> str:
    return ' & '.join(f'{i["f"]}={int(i["v"])}' for i in items)


def pct(x) -> str:
    return '-' if x is None else f'{100 * x:.1f}%'


def money(x, f='+.2f') -> str:
    return '-' if x is None else format(x, f)


def esc(x) -> str:
    return str(x).replace('|', '\\|')


def split_md(ct: str, name: str, r: dict, n_setups_md: int) -> list:
    L = [f'## {name}', '',
         f'{r["setups_scored"]} confirmed setups, {r["setups_traded"]} with trades; {r["trades"]} trades (summed over setups), '
         f'{r["losers"]} losers ({pct(r["loser_share"])}), total {money(r["usd_total"])} $ (losers {money(r["loser_usd_total"])}, '
         f'winners {money(r["winner_usd_total"])}).', '',
         '| | losers | winners |', '|---|---|---|',
         f'| trades | {r["losers"]} | {r["winners"]} |',
         f'| mean $ | {money(r["mean_loser_usd"], "+.3f")} | {money(r["mean_winner_usd"], "+.3f")} |',
         f'| hold minutes mean / median | {money(r["hold_min"]["losers_mean"], ".1f")} / {money(r["hold_min"]["losers_median"], ".0f")} '
         f'| {money(r["hold_min"]["winners_mean"], ".1f")} / {money(r["hold_min"]["winners_median"], ".0f")} |']
    for e in EXITS:
        L.append(f'| exit: {e}{" (" + TIME_DESC[ct] + ")" if e == "time" else ""} | {r["loser_exits"][e]} | {r["winner_exits"][e]} |')
    b = r['loser_best_share']
    L += ['', f'Losers whose best_ within h (hindsight best net $ at a tradable price; mean {money(r["mean_loser_best_usd"], "+.3f")}; '
          f'target mean ${money(r["target_usd_mean"], ".2f")}): > $0 {pct(b["gt0"])}, >= $1 {pct(b["ge1"])}, >= half the target '
          f'{pct(b["ge_half_target"])}, >= the target {pct(b["ge_target"])}. An upper bound on what an earlier or smaller '
          'take-profit could have saved: best_ ignores path order (the best price may come after the stop or the exit).', '',
          f'### States over-represented among losers vs winners (min support {r.get("min_support", 30)}, top {len(r["lift"])})', '',
          '| feature | value | losers | winners | share of losers | share of winners | loser rate | lift |',
          '|---|---|---|---|---|---|---|---|']
    L += [f'| {esc(x["feature"])} | {esc(x["value"])} | {x["losers"]} | {x["winners"]} | {pct(x["share_losers"])} | '
          f'{pct(x["share_winners"])} | {pct(x["loser_rate"])} | {x["lift"]:.2f} |' for x in r['lift']]
    L += ['', '### What would fix it: take-profit at a fraction of the target (upper bound from best_)', '',
          '| take-profit | losers rescued | $ recovered on losers | $ change on winners (capped) | $ actual | $ upper bound | $/trade actual -> bound |',
          '|---|---|---|---|---|---|---|']
    L += [f'| {int(100 * x["level_frac"])}% (~${money(x["level_usd_mean"], ".2f")}) | {x["losers_rescued"]}/{x["losers"]} | '
          f'{money(x["usd_recovered_on_losers"])} | {money(x["usd_change_on_winners"])} ({x["winners_capped"]}) | {money(x["usd_actual"])} | '
          f'{money(x["usd_upper_bound"])} | {money(x["usd_per_trade_actual"], "+.3f")} -> {money(x["usd_per_trade_upper_bound"], "+.3f")} |'
          for x in r['fix']]
    worst = sorted([s for s in r['setups'] if s['trades']], key=lambda s: (s['usd_total'], s['id']))[:n_setups_md]
    L += ['', f'### Per setup: the {len(worst)} with the lowest total $ (every setup in losers.json)', '',
          '| setup | scope | side h | items | trades | loser share | mean loser $ | loser exits (stop / settle / time) | '
          'best_ > 0 / >= $1 / >= T/2 / >= T | hold L / W | top loser state (lift, L/W) |',
          '|---|---|---|---|---|---|---|---|---|---|---|']
    for s in worst:
        b, le, lf = s['loser_best_share'], s['loser_exits'], (s['lift'][0] if s['lift'] else None)
        L.append(f'| {s["id"]} | {esc(s["scope"])} | {s["side"]} {s["h"]} | {esc(items_str(s["items"]))} | '
                 f'{s["trades"]} | {pct(s["loser_share"])} | {money(s["mean_loser_usd"], "+.3f")} | {le["stop"]} / {le["settlement"]} / {le["time"]} | '
                 f'{pct(b["gt0"])} / {pct(b["ge1"])} / {pct(b["ge_half_target"])} / {pct(b["ge_target"])} | '
                 f'{money(s["hold_min"]["losers_mean"], ".0f")} / {money(s["hold_min"]["winners_mean"], ".0f")} | '
                 + (f'{esc(lf["feature"])}={esc(lf["value"])} ({lf["lift"]:.2f}, {lf["losers"]}/{lf["winners"]})' if lf else '-') + ' |')
    L.append('')
    return L


def report_md(doc: dict) -> str:
    ct = doc['ct']
    L = [f'# Oracle setups loser study: {ct}', '',
         'Descriptive (Steven, 2026-11-06 14:03 UTC; python/oracle/prereg/OR-AMEND-1.md): why do losing trades lose. Every '
         'confirmed setup (confirm.jsonl) traded exactly as the confirmation step trades it (one position at a time per '
         'asset / event, primary exit). Winners: trade $ > 0; losers: trade $ <= 0. Aggregates only.', '',
         f'Splits: discovery B (whole horizon before {doc["dev_end"]})' + ('; HO-1 (Aug 1 - Nov 4 2026) reported separately.' if 'H' in doc['splits'] else '; HO-1 not read.'), '']
    names = {'B': 'Discovery B', 'H': 'HO-1 (Aug 1 - Nov 4 2026)'}
    for sp, r in doc['splits'].items():
        L += split_md(ct, names[sp], r, doc['setups_in_md'])
    L += ['## Notes', '',
          '- Pooled tables add every setup\'s trades: a decision traded by several setups counts once per setup.',
          '- best_ is the hindsight best net $ within h at a tradable price; the "what would fix it" bound assumes the level '
          'fills whenever best_ reached it (path order vs the stop ignored) and keeps the same trades (an earlier exit could '
          'free the position for other trades; not modelled).',
          '- Exit kinds are inferred from the part labels: take-profit = hit; perp-rev stop = no take-profit and an exit before '
          'the horizon (a stop in the last minute counts as time); settlement = the market closed inside the hold (tennis) or '
          'the ride to settlement (Price Prediction).', '']
    return '\n'.join(L)


def run(a) -> dict:
    log = log_to(a.quiet)
    ct = a.ct
    paths = list_parts(a.parts, ct)
    if not paths:
        raise SystemExit(f'no {ct}-* parts under {a.parts}')
    setups = load_confirm(a.confirm, ct)
    log(f'{ct}: {len(setups)} confirmed setups, {len(paths)} parts')
    splits = {'B': study(paths, ct, setups, 'B', a.min_support, a.top, log)}
    if a.ho1:
        log('HO-1 rows (--ho1)')
        splits['H'] = study(paths, ct, setups, 'H', a.min_support, a.top, log)
    for r in splits.values():
        r['min_support'] = a.min_support
    doc = {'schema': 'oracle-losers-1', 'ct': ct, 'dev_end': '2026-08-01T00:00Z', 'min_support': a.min_support, 'top': a.top,
           'setups_in_md': a.setups_md, 'exits': list(EXITS), 'time_exit': TIME_DESC.get(ct), 'fix_levels': list(FIX_LEVELS),
           'splits': splits}
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, 'losers.json'), 'w') as f:
        json.dump(clean(doc), f, indent=1, sort_keys=True, allow_nan=False)
    with open(os.path.join(a.out, 'losers.md'), 'w') as f:
        f.write(report_md(doc))
    for sp, r in splits.items():
        log(f'{sp}: {r["trades"]} trades, loser share {pct(r["loser_share"])}, mean loser {money(r["mean_loser_usd"], "+.3f")} $')
    return doc


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description='Oracle setups loser study: why the confirmed setups\' losing trades lose.')
    ap.add_argument('--ct', required=True, choices=('perp', 'pp15', 'pp60', 'tennis', 'perp-rev'))
    ap.add_argument('--parts', required=True, help='parts root holding <ct>-<scope>/ directories')
    ap.add_argument('--confirm', required=True, help="the miner's confirm.jsonl")
    ap.add_argument('--out', required=True)
    ap.add_argument('--ho1', action='store_true', help='also study HO-1 rows (reported separately); only once HO-1 is opened '
                                                       'for every confirmed setup of the type')
    ap.add_argument('--min-support', type=int, default=30)
    ap.add_argument('--top', type=int, default=15)
    ap.add_argument('--setups-md', type=int, default=25, help='setups listed per split in losers.md (all in losers.json)')
    ap.add_argument('--quiet', action='store_true')
    return ap


def main(argv=None) -> dict:
    return run(parser().parse_args(argv))


if __name__ == '__main__':
    main()
