"""Held-out standard HO-1 evidence of an all-pairs run: the registry's `heldout` block for every gated arm.

    python -m allpairs.ho1 --results <run results dir> --labels <regime v1 labels.csv[.gz]>

For each config folder under <run results dir> whose arms were scored with --protocol ho1, writes heldout.json:
{arm: block}. The block is the registry's HO-1 history tier (research/registry.py HO1, README of the registry):
  days                    held-out days with data (H-HOLD Aug 1-Nov 4 2026: 96)
  folds, folds_won        the 6 consecutive 16-day folds; a fold is won when its $/h is above 0 (an all-pairs policy
                          is judged against not trading at all)
  worst_fold_per_hour     the worst fold's $/h
  terciles_*              $/h by regime v1 RV tercile of the hour: a tercile is covered with at least 100 hours, won
                          when covered and above 0; the worst covered tercile's $/h
  beats_placebo           the arm's $/h is above its random-entry placebo's 95th percentile and above every
                          shuffled-label refit (the gate's two placebo checks; under HO-1 every gated arm has its
                          own refits, run.arm_config); no refits counts as not beaten
Every quantity is the arm's own $ against not trading: the registry pairs each HO-1 row with a no-trade control
($0 every held-out day, registry_rows), so its paired gain is the same series.
The hour's tercile: regime v1 labels are per asset and minute; each minute label of the traded assets in the UTC hour
counts LOW 0, MID 1, HIGH 2 (NA left out) and the hour takes the rounded mean (below 0.5 LOW, below 1.5 MID, else
HIGH); an hour with no label is not in any tercile. The P&L of an hour is the policy's P&L booked to that hour (the
hour its window opened), as in hourly_pnl.
replay_version is left out: the all-pairs engine reads Kalshi's own 15-minute candles directly (no TypeScript replay,
whose REPLAY_VERSION 8 fixed ladder-strike quotes; the 15-minute series have one market per window).
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import glob
import gzip
import json
import os

import numpy as np

GATED = ('base', 'stress', 'tight', 'strict', 'tight_strict')
TERCILES = ('LOW', 'MID', 'HIGH')
MIN_TERCILE_HOURS = 100
CODE = {'LOW': 0, 'MID': 1, 'HIGH': 2}


def _day(iso: str) -> int:
    return (dt.date.fromisoformat(iso[:10]) - dt.date(1970, 1, 1)).days


def hour_terciles(labels_path: str, assets: list, day_lo: int, day_hi: int) -> dict:
    """{(day number, hour): 'LOW'|'MID'|'HIGH'} for day_lo..day_hi (inclusive) from regime v1 minute labels."""
    want = set(assets)
    s, n = {}, {}
    opener = gzip.open if labels_path.endswith('.gz') else open
    with opener(labels_path, 'rt', newline='') as fh:
        for row in csv.DictReader(fh):
            t = CODE.get(row.get('tercile', ''))
            if t is None or row.get('asset') not in want:
                continue
            ts = row['ts_iso']
            d = _day(ts)
            if d < day_lo or d > day_hi:
                continue
            k = (d, int(ts[11:13]))
            s[k] = s.get(k, 0) + t
            n[k] = n.get(k, 0) + 1
    return {k: TERCILES[0 if m < 0.5 else 1 if m < 1.5 else 2] for k in s for m in (s[k] / n[k],)}


def hour_keys(result: dict) -> list:
    """(day number, hour) of every entry of hourly_pnl, from the folds' test days (24 hours each, in order)."""
    keys = []
    for f in result.get('folds', []):
        days = f.get('test_days') or list(range(int(f['test'][0]), int(f['test'][1]) + 1))
        if len(days) * 24 != int(f['n_hours']):
            raise ValueError(f'fold {f.get("fold")}: {len(days)} test days but {f["n_hours"]} hours')
        keys += [(int(d), h) for d in days for h in range(24)]
    if len(keys) != len(result.get('hourly_pnl') or []):
        raise ValueError(f'{len(result.get("hourly_pnl") or [])} hourly values for {len(keys)} test hours')
    return keys


def block(result: dict, terciles: dict) -> dict:
    hourly = np.asarray(result.get('hourly_pnl') or [], dtype=np.float64)
    keys = hour_keys(result)
    fold_ph, pos = [], 0
    for f in result.get('folds', []):
        n = int(f['n_hours'])
        fold_ph.append(round(float(hourly[pos:pos + n].sum()) / n, 4) if n else 0.0)
        pos += n
    by_t = {}
    for t in TERCILES:
        sel = np.array([terciles.get(k) == t for k in keys], dtype=bool)
        h = int(sel.sum())
        by_t[t] = dict(hours=h, per_hour=round(float(hourly[sel].sum()) / h, 4) if h else None)
    covered = [t for t in TERCILES if by_t[t]['hours'] >= MIN_TERCILE_HOURS]
    ph = float(result['oos']['per_hour'])
    pl = result.get('placebo') or {}
    rand95, shuffled = pl.get('random_per_hour_p95'), pl.get('shuffled_per_hour') or []
    days = sorted({k[0] for k in keys})
    out = dict(standard='HO-1', tier='history', days=len(days), folds=len(fold_ph), folds_won=sum(x > 0 for x in fold_ph),
               worst_fold_per_hour=min(fold_ph) if fold_ph else None,
               terciles_covered=len(covered), terciles_won=sum(by_t[t]['per_hour'] > 0 for t in covered),
               worst_tercile_per_hour=min(by_t[t]['per_hour'] for t in covered) if covered else None,
               beats_placebo=bool(rand95 is not None and shuffled and ph > rand95 and ph > max(shuffled)),
               # informational (not read by the registry's ho1_pass)
               fold_per_hour=fold_ph, by_tercile=by_t, per_hour=round(ph, 4), unlabelled_hours=sum(1 for k in keys if k not in terciles),
               span=result.get('ho1_span'), benchmark='no trading ($0 every hour; the no_trade control row)',
               engine='allpairs (Kalshi 15m candles; no TS replay, REPLAY_VERSION n/a)')
    return {k: v for k, v in out.items() if v is not None}


def verdict(b: dict) -> tuple:
    """(passes, reasons) with the registry's HO-1 history thresholds, replay version aside (see the module note)."""
    why = []
    if b.get('days', 0) < 90: why.append(f'{b.get("days", 0)} held-out days < 90')
    if b.get('folds', 0) < 6: why.append(f'{b.get("folds", 0)} folds < 6')
    elif b.get('folds_won', 0) < 4: why.append(f'won {b.get("folds_won", 0)}/{b["folds"]} folds')
    if b.get('worst_fold_per_hour', -1e9) < -0.50: why.append(f'worst fold {b.get("worst_fold_per_hour")} $/h')
    if b.get('terciles_covered', 0) < 2 or b.get('terciles_won', 0) < 2: why.append(f'{b.get("terciles_won", 0)} RV terciles won')
    if b.get('worst_tercile_per_hour', -1e9) < -0.50: why.append(f'worst tercile {b.get("worst_tercile_per_hour")} $/h')
    if not b.get('beats_placebo'): why.append('does not beat its placebo')
    return not why, why


def run(results_dir: str, labels_path: str) -> dict:
    """Writes heldout.json in every config folder scored under HO-1; returns {config: {arm: block}}."""
    done = {}
    folders = sorted({os.path.dirname(f) for f in glob.glob(os.path.join(results_dir, '**', '*.json'), recursive=True)})
    cache = {}
    for d in folders:
        arms = {}
        for arm in GATED:
            p = os.path.join(d, f'{arm}.json')
            if os.path.exists(p):
                r = json.load(open(p))
                if r.get('protocol') == 'ho1' and r.get('kind', 'real15') == 'real15' and r.get('folds'):
                    arms[arm] = r
        if not arms:
            continue
        blocks = {}
        for arm, r in arms.items():
            keys = hour_keys(r)
            assets = r.get('traded_assets') or r.get('assets') or []
            span = (tuple(assets), min(k[0] for k in keys), max(k[0] for k in keys))
            if span not in cache:
                cache[span] = hour_terciles(labels_path, list(span[0]), span[1], span[2])
            blocks[arm] = block(r, cache[span])
        with open(os.path.join(d, 'heldout.json'), 'w') as fh:
            json.dump(blocks, fh, indent=1)
        name = arms.get('base', next(iter(arms.values()))).get('name') or os.path.basename(d)
        done[name] = blocks
        for arm, b in blocks.items():
            ok, why = verdict(b)
            print(f'{name:16s} {arm:7s} HO-1 {"PASS" if ok else "fail"}: {b["per_hour"]:+.2f} $/h, folds won {b["folds_won"]}/{b["folds"]}, '
                  f'worst fold {b.get("worst_fold_per_hour")}, terciles {b["by_tercile"]}{"" if ok else "; " + "; ".join(why)}')
    return done


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--results', required=True)
    ap.add_argument('--labels', required=True, help='regime v1 labels.csv or labels.csv.gz')
    a = ap.parse_args(argv)
    run(a.results, a.labels)


if __name__ == '__main__':
    main()
