"""Steven, Nov 22 2026 (8:04 AM EST / 13:04 UTC): "if edge is found on some days/trades but not others investigate the difference and then see if they still perform on the
same types of days or trades, if they do save them as only for that specific type."

Recorded days only, paper only, nothing is ordered. The trades are already typed by pockets.py (side, price bucket, placement minutes, cancel minute, coin, six-hour block). This
types the DAYS. Each UTC day gets labels known before it opens (from the calendar and the previous day's own quotes), cut at the terciles of the build days only:

  wkend    Saturday or Sunday against a weekday
  psurp    the previous day's mean |settle - first-minutes mid| (how wrong the early quotes were): low / mid / high
  pvolu    the previous day's contracts traded per window, against the mean of the 14 days before it (volume drifts over months; fixed cut points left whole levels empty in later blocks)
  ptrend   the previous day's share of windows that settled YES
  pspread  the previous day's mean YES spread at the first minutes, against the mean of the 14 days before it

A rule (side, price bucket, placement minutes, cancel minute, coin) on one day type is kept ("typed") only if all of this holds, in three time blocks used once each:

  build   (first half of the days)  the day-cluster lower bound above zero, at least 300 fills
  check   (next quarter)            the day-cluster lower bound above zero, at least 150 fills, and better than the same rule on the other days of the block by 0.25c or more
  clean   (last quarter)            a positive mean over at least 100 fills, and better than the same rule on the other days of the block by 0.25c or more

The placebo is the same search run on the day labels slid by a random number of days (the label sequence keeps its streaks and its frequencies, loses its dates): how many
typed rules appear by chance. A typed rule is only taken as real if the real count beats those. Aggregates only; the typed rules are written to typed_rules.json with their type.
"""
import argparse
import json
import math
import os

import numpy as np

from subminute import fampockets as FP
from subminute import pockets as PK

Z = PK.Z95
FEATURES = ('wkend', 'psurp', 'pvolu', 'ptrend', 'pspread')
LEVELS = {'wkend': ('weekday', 'weekend'), 'psurp': ('low', 'mid', 'high'), 'pvolu': ('low', 'mid', 'high'), 'ptrend': ('low', 'mid', 'high'), 'pspread': ('low', 'mid', 'high')}
MIN_DIFF = 0.0025                                    # a quarter of a cent per contract


def day_table(w, day0: int, nd: int) -> dict:
    """Per UTC day (index = day - day0): the mean |settle - mid| of the first minutes, contracts per window, the YES share, the spread. NaN where the day is not recorded."""
    day = (np.asarray(w.day) - day0).astype(int)
    bid, ask = np.asarray(w.bid, float), np.asarray(w.ask, float)
    with np.errstate(all='ignore'):
        mid0 = np.nanmean(((bid + ask) / 2.0)[:, 1:4], axis=1)
        spr = np.nanmean((ask - bid)[:, 1:4], axis=1)
    settle = np.asarray(w.settle, float)

    def dmean(x):
        ok = np.isfinite(x)
        s, c = np.bincount(day[ok], weights=x[ok], minlength=nd), np.bincount(day[ok], minlength=nd)
        return np.where(c > 0, s / np.maximum(c, 1), np.nan)
    return {'surp': dmean(np.abs(settle - mid0)), 'vol': dmean(np.asarray(w.kvol, float).sum(1)), 'yes': dmean(settle), 'spr': dmean(spr)}


def labels(w, day0: int, nd: int, build: np.ndarray) -> tuple:
    """({feature: int level per day, -1 = unknown}, {feature: cut points from the build days}). The previous day's value is used for every feature except wkend."""
    t = day_table(w, day0, nd)
    dn = np.arange(nd) + day0
    out, cuts = {}, {}
    out['wkend'] = (((dn + 3) % 7) >= 5).astype(int)           # 1970-01-01 was a Thursday
    cuts['wkend'] = [5]
    for f, key, rel in (('psurp', 'surp', False), ('pvolu', 'vol', True), ('ptrend', 'yes', False), ('pspread', 'spr', True)):
        x = t[key]
        prev = np.concatenate([[np.nan], x[:-1]])
        if rel:                                                  # volume and spread drift over months: the previous day against the mean of the 14 days before it
            base = np.full(nd, np.nan)
            for d in range(nd):
                seg = x[max(0, d - 15):max(0, d - 1)]
                seg = seg[np.isfinite(seg)]
                if len(seg) >= 5:
                    base[d] = seg.mean()
            with np.errstate(all='ignore'):
                prev = np.where(base > 0, prev / base, np.nan)
        ok = build & np.isfinite(prev)
        if ok.sum() < 6:
            continue
        q = np.quantile(prev[ok], [1 / 3, 2 / 3])
        lv = np.where(np.isfinite(prev), (prev > q[0]).astype(int) + (prev > q[1]).astype(int), -1)
        out[f], cuts[f] = lv, [float(q[0]), float(q[1])]
    return out, cuts


def _stat(A, m, min_fills):
    r = PK.ratio(A, 5, 4, m)
    if r is None or r[2] < min_fills:
        return None
    mean, se, D, nd, pos = r
    return {'mean': mean, 'lo': None if se is None else mean - Z * se, 'fills': D, 'days': nd}


def evaluate(acc: dict, cells: list, lab: dict, blocks: dict, min_build: int, min_check: int, min_clean: int, tests: list = None) -> list:
    """Typed rules under the labels `lab`: [(cell, feature, level, build, check, clean, check_other, clean_other)]."""
    found = []
    for f, L in lab.items():
        for lv in range(len(LEVELS[f])):
            on = (L == lv)
            mb = blocks['build'] & on
            if mb.sum() < 5:
                continue
            for cell in cells:
                A = acc[cell]
                b = _stat(A, mb, min_build)
                if tests is not None:
                    tests.append(1)
                if b is None or b['lo'] is None or b['lo'] <= 0:
                    continue
                k = _stat(A, blocks['check'] & on, min_check)
                if k is None or k['lo'] is None or k['lo'] <= 0:
                    continue
                c = _stat(A, blocks['clean'] & on, min_clean)
                if c is None or c['mean'] <= 0:
                    continue
                ko = _stat(A, blocks['check'] & ~on & (L >= 0), 1)
                co = _stat(A, blocks['clean'] & ~on & (L >= 0), 1)
                if ko is None or co is None or k['mean'] - ko['mean'] < MIN_DIFF or c['mean'] - co['mean'] < MIN_DIFF:
                    continue
                found.append((cell, f, lv, b, k, c, ko, co))
    return found


def pooled(acc: dict, cells: list, nd: int) -> np.ndarray:
    P = np.zeros((nd, PK.COLS))
    for cell in cells:
        P += acc[cell]
    return P


def level_table(P: np.ndarray, lab: dict, blocks: dict) -> dict:
    """The mean rule (every rule of the scope pooled, fills weighted): net c per fill by day type in each block, with its day-cluster interval."""
    out = {}
    for f, L in lab.items():
        for lv, name in enumerate(LEVELS[f]):
            row = {}
            for bn, bm in blocks.items():
                s = _stat(P, bm & (L == lv), 1)
                row[bn] = None if s is None else {'net_c': PK.c(s['mean']), 'lo_c': None if s['lo'] is None else PK.c(s['lo']), 'fills': int(s['fills']), 'days': s['days']}
            out[f'{f}:{name}'] = row
    return out


def _c(s):
    return None if s is None else {'net_c': PK.c(s['mean']), 'lo_c': None if s['lo'] is None else PK.c(s['lo']), 'fills': int(s['fills']), 'days': s['days']}


def run(w, out_dir: str, assets=None, build_frac: float = 0.5, clean_frac: float = 0.25, shifts: int = 200, seed: int = 7, min_build: int = None, min_check: int = None,
        min_clean: int = 100, top: int = 12, log=print) -> dict:
    min_build = PK.MIN_BUILD_FILLS if min_build is None else min_build
    min_check = PK.MIN_CHECK_FILLS if min_check is None else min_check
    days = np.unique(w.day)
    if len(days) < 14:
        raise ValueError(f'only {len(days)} day(s) of candles')
    split, clean = int(days[int(len(days) * build_frac)]), int(days[int(len(days) * (1.0 - clean_frac))])
    names = [str(a) for a in w.assets]
    scopes = (list(assets) if assets is not None else names) + ['ALL']
    old_c, old_h = PK.COIN_SLICES, PK.HOUR_SLICES
    PK.COIN_SLICES, PK.HOUR_SLICES = tuple(scopes), ('ALL',)
    try:
        day0, nd = int(days.min()), int(days.max() - days.min() + 1)
        acc = PK.scan(w, day0, nd)
    finally:
        PK.COIN_SLICES, PK.HOUR_SLICES = old_c, old_h
    dn = np.arange(nd) + day0
    have = np.zeros(nd, bool)
    have[(days - day0).astype(int)] = True
    blocks = {'build': have & (dn < split), 'check': have & (dn >= split) & (dn < clean), 'clean': have & (dn >= clean)}
    lab, cuts = labels(w, day0, nd, blocks['build'])
    longest = max(PK.CANCEL)
    cells = [k for k in acc if k[0][3] == longest and k[2] == 'ALL']
    tests = []
    found = evaluate(acc, cells, lab, blocks, min_build, min_check, min_clean, tests)
    rng = np.random.default_rng(seed)
    counts = []
    for _ in range(shifts):
        s = int(rng.integers(8, max(9, nd - 8)))
        counts.append(len(evaluate(acc, cells, {f: np.roll(L, s) for f, L in lab.items()}, blocks, min_build, min_check, min_clean)))
    p = None if not counts else (1 + sum(1 for x in counts if x >= len(found))) / (1 + len(counts))
    date = lambda d: str(np.datetime64('1970-01-01') + np.timedelta64(int(d), 'D'))
    typed = []
    for cell, f, lv, b, k, c, ko, co in sorted(found, key=lambda t: -t[4]['lo'])[:top]:
        (side, bk, pl, cn), sc, _ = cell
        typed.append({'scope': sc, 'rule': {'side': side, 'bucket': list(bk), 'place_from_bar': pl[0], 'place_to_bar': pl[1], 'cancel_bar': cn}, 'type': {'feature': f, 'level': LEVELS[f][lv], 'cuts_from_build': cuts.get(f)},
                      'build': _c(b), 'check': _c(k), 'clean': _c(c), 'check_other_days': _c(ko), 'clean_other_days': _c(co)})
    out = {'blocks': {'build': [date(days.min()), date(split - 1)], 'check': [date(split), date(clean - 1)], 'clean': [date(clean), date(days.max())]},
           'days': {k: int(v.sum()) for k, v in blocks.items()}, 'scopes': scopes, 'rules_per_scope': len(cells) // max(1, len(scopes)), 'feature_cuts_from_build': cuts,
           'typed_tests': len(tests), 'typed_found': len(found), 'placebo_slides': len(counts), 'placebo_found_mean': None if not counts else round(float(np.mean(counts)), 2),
           'placebo_found_max': None if not counts else int(max(counts)), 'placebo_p': None if p is None else round(p, 4),
           'typed_rules': typed, 'levels_all_rules': level_table(pooled(acc, [k for k in cells if k[1] == 'ALL'], nd), lab, blocks)}
    os.makedirs(out_dir, exist_ok=True)
    json.dump(out, open(os.path.join(out_dir, 'typed_rules.json'), 'w'), indent=1, sort_keys=True, default=float)
    return out


def load(hist: str, kind: str, assets, series_fmt: str = None, log=print):
    from allpairs import data as KD
    return KD.load_kalshi(hist, assets, n=FP.KINDS[kind]['n'], series_fmt=series_fmt or FP.KINDS[kind]['fmt'], log=log)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--hist', required=True, help='a directory holding kalshi/<series>/DAY.jsonl')
    ap.add_argument('--assets', required=True, help='comma-separated, e.g. BTC,ETH or WTI,SILVER')
    ap.add_argument('--kind', default='m15', choices=sorted(FP.KINDS))
    ap.add_argument('--series-fmt', default=None)
    ap.add_argument('--out', required=True)
    ap.add_argument('--shifts', type=int, default=200)
    a = ap.parse_args()
    with FP.pk_settings(a.kind):
        w = load(a.hist, a.kind, [x.strip().upper() for x in a.assets.split(',')], a.series_fmt, log=lambda *x: None)
        r = run(w, a.out, shifts=a.shifts, log=lambda *x: None)
    print('HEATLOOP dt-summary ' + json.dumps({k: v for k, v in r.items() if k not in ('typed_rules', 'levels_all_rules')}, sort_keys=True, default=float), flush=True)
    print('HEATLOOP dt-levels (net c per fill of the mean rule, by day type, day-cluster lower bound) ' + json.dumps(r['levels_all_rules'], sort_keys=True, default=float)[:9000], flush=True)
    print('HEATLOOP dt-typed ' + json.dumps(r['typed_rules'][:6], sort_keys=True, default=float)[:9000], flush=True)
