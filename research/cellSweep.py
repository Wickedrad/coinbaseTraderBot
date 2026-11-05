#!/usr/bin/env python3
"""Cell sweep scorer (meta plan thread, 2026-11-05).

Each arm of a cell-sweep batch replays the whole bot with ONE global setting changed. Every replay's per-market P&L
(replay.byTicker in the replay check's output) is split into cells: series x contract kind (B = range bucket,
T = threshold). So each (cell, setting) pair is scored from the same replays.

Adversaries, all out of sample:
  * walk-forward, leave one day out: a cell's setting is picked on the other days and scored on the held-out day;
  * noise floor: the control replayed at another tick phase (P500) gives each cell's day-to-day path noise;
  * placebos (PSH anchor shuffle, NLM longshot mirror) are never pickable, and are reported beside what they mimic;
  * stability: the setting must win the pick in most folds.
A cell is a SOLID candidate when its held-out gain over the control beats 2 noise SDs, is positive on most held-out
days, and its pick is stable. Placebo arms and the noise twin are not candidates.

Usage: cellSweep.py <dir with dDD-ARM.json.gz files> <out.md> [--control C0] [--noise P500]
"""
import gzip
import json
import math
import os
import re
import sys
from collections import defaultdict

PLACEBOS = {'P500', 'PSH', 'NLM', 'WP500', 'WPSH', 'WNLM'}
HOURS_PER_DAY = 24.0


def cell_of(ticker: str) -> str:
    parts = ticker.split('-')
    series = parts[0]
    kind = parts[-1][:1] if len(parts) > 2 and parts[-1][:1] in 'BT' else 'U'  # U = 15-minute up/down
    return f'{series} {kind}'


def load(d: str):
    """Arms tagged <arm>p<phase> (one replay per tick phase) are averaged over their phases: the path noise of one
    replay (a tick phase moved $500+ a week in batch 2) shrinks with the number of phases."""
    raw = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(float))))  # arm -> phase -> day -> cell
    rawc = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(int))))
    days = set()
    for f in sorted(os.listdir(d)):
        m = re.match(r'^d(\d\d)-([A-Za-z0-9]+)\.json(\.gz)?$', f)
        if not m:
            continue
        op = gzip.open if f.endswith('.gz') else open
        with op(os.path.join(d, f), 'rt') as fh:
            res = json.load(fh)
        day, tag = m.group(1), m.group(2)
        pm = re.match(r'^(.+?)p(\d+)$', tag)
        arm, ph = (pm.group(1), int(pm.group(2))) if pm else (tag, -1)
        days.add(day)
        bt = (res.get('replay') or {}).get('byTicker') or {}
        raw[arm][ph][day]  # mark the run, even with no settled markets
        for t, v in bt.items():
            raw[arm][ph][day][cell_of(t)] += float(v)
            rawc[arm][ph][day][cell_of(t)] += 1
    pnl = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))  # arm -> day -> cell -> $ (phase mean)
    cnt = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    for arm, phs in raw.items():
        for day in days:
            have = [ph for ph in phs if day in phs[ph]]
            if not have or len(have) < len(phs):
                continue  # a day is complete only with every phase the arm ran
            pnl[arm][day]
            for ph in have:
                for c, v in phs[ph][day].items():
                    pnl[arm][day][c] += v / len(have)
                for c, v in rawc[arm][ph][day].items():
                    cnt[arm][day][c] += v / len(have)
    return pnl, cnt, sorted(days), sorted(raw), raw


def main() -> None:
    args = sys.argv[1:]
    src, out = args[0], args[1]
    control = args[args.index('--control') + 1] if '--control' in args else 'C0'
    noise = args[args.index('--noise') + 1] if '--noise' in args else 'P500'
    pnl, cnt, days, arms, raw = load(src)
    MIN_MARKETS = 10  # a cell needs at least this many settled markets (picked arm, all days) to be SOLID
    full = [a for a in arms if all(day in pnl[a] for day in days)]
    missing = sorted(set(arms) - set(full))
    if control not in full:
        sys.exit(f'control {control} is missing days; arms complete: {full}')
    cells = sorted({c for a in full for day in days for c in pnl[a][day]})
    pick_arms = [a for a in full if a not in PLACEBOS]

    def tot(a, c, ds):
        return sum(pnl[a][d].get(c, 0.0) for d in ds)

    lines = []
    w = lines.append
    w(f'# Cell sweep: {len(full)} complete arms x {len(days)} days (Oct {days[0]}-{days[-1]}), {len(cells)} cells')
    if missing:
        w(f'Arms missing days (left out): {", ".join(missing)}')
    w('')
    # Whole-bot totals per arm (all cells) and without DOGE hourly ranges.
    w('## Arms, whole bot ($ over the days; no-DOGE-hourly second)')
    w('| arm | total | no DOGE hourly | $/h | vs control |')
    w('|---|---|---|---|---|')
    ctl_tot = sum(tot(control, c, days) for c in cells)
    for a in sorted(full, key=lambda a: -sum(tot(a, c, days) for c in cells)):
        t = sum(tot(a, c, days) for c in cells)
        nd = sum(tot(a, c, days) for c in cells if not c.startswith('KXDOGE '))
        w(f'| {a}{" (placebo)" if a in PLACEBOS else ""} | {t:+.2f} | {nd:+.2f} | {t / (HOURS_PER_DAY * len(days)):+.2f} | {t - ctl_tot:+.2f} |')
    w('')

    # Noise floor per cell: SD over days of (noise twin - control).
    def noise_sd(c):
        # Phase-averaged control: two of its phases differ by sigma*sqrt(2) a day; an arm-minus-control difference of
        # n-phase means has sigma*sqrt(2/n), so SD(phase A - phase B) / sqrt(n).
        phs = sorted(p for p in raw.get(control, {}) if p >= 0)
        if len(phs) >= 2:
            a, b = raw[control][phs[0]], raw[control][phs[1]]
            xs = [a[d].get(c, 0.0) - b[d].get(c, 0.0) for d in days if d in a and d in b]
            if len(xs) >= 2:
                mu = sum(xs) / len(xs)
                return math.sqrt(sum((x - mu) ** 2 for x in xs) / (len(xs) - 1)) / math.sqrt(len(phs))
        if noise not in full:
            return None
        xs = [pnl[noise][d].get(c, 0.0) - pnl[control][d].get(c, 0.0) for d in days]
        mu = sum(xs) / len(xs)
        return math.sqrt(sum((x - mu) ** 2 for x in xs) / max(1, len(xs) - 1))

    # Walk-forward, leave one day out.
    rows = []
    map_oos = 0.0
    ctl_oos = 0.0
    for c in cells:
        picks, gains, oos = [], [], 0.0
        for d in days:
            train = [x for x in days if x != d]
            best = max(pick_arms, key=lambda a: (tot(a, c, train), a == control))
            picks.append(best)
            g = pnl[best][d].get(c, 0.0) - pnl[control][d].get(c, 0.0)
            gains.append(g)
            oos += pnl[best][d].get(c, 0.0)
        top = max(set(picks), key=picks.count)
        stab = picks.count(top) / len(picks)
        gain = sum(gains)
        pos = sum(1 for g in gains if g > 0)
        sd = noise_sd(c)
        floor = 2 * sd * math.sqrt(len(days)) if sd is not None else None
        nmk = round(sum(cnt[top][d].get(c, 0) for d in days))
        solid = nmk >= MIN_MARKETS and top != control and gain > 0 and (floor is None or gain > floor) and pos >= math.ceil(len(days) / 2) and stab >= 5 / 7
        ctl = tot(control, c, days)
        map_oos += oos
        ctl_oos += ctl
        rows.append((c, top, stab, gain, pos, floor, solid, ctl, tot(top, c, days), nmk, round(sum(cnt[control][d].get(c, 0) for d in days))))
    w('## Cell map, walk-forward (pick on the other days, score the held-out day)')
    w(f'Cell-map total held out: {map_oos:+.2f} vs control {ctl_oos:+.2f} ({(map_oos - ctl_oos):+.2f}; '
      f'{map_oos / (HOURS_PER_DAY * len(days)):+.2f}/h vs {ctl_oos / (HOURS_PER_DAY * len(days)):+.2f}/h). '
      'Cells are scored apart, so this ignores shared bankroll and pacer effects: a whole-bot replay confirms it.')
    w('')
    w('| cell | picked | folds won | held-out gain vs control | days ahead | noise floor (2 SD) | control $ (markets) | picked $ (markets) | verdict |')
    w('|---|---|---|---|---|---|---|---|---|')
    for r in sorted(rows, key=lambda r: -r[3]):
        c, top, stab, gain, pos, floor, solid, ctl, pt, nmk, nctl = r
        verdict = 'SOLID' if solid else ('keep control' if top == control else ('too few markets' if nmk < MIN_MARKETS else 'not proven'))
        w(f'| {c} | {top} | {stab:.0%} | {gain:+.2f} | {pos}/{len(days)} | {"-" if floor is None else f"{floor:.2f}"} | {ctl:+.2f} ({nctl}) | {pt:+.2f} ({nmk}) | {verdict} |')
    w('')
    # Placebo check: each real arm beside its placebo, per cell where it won.
    w('## Placebos beside what they mimic (all days, all cells)')
    for real, plc in (('C0', 'PSH'), ('NL04', 'NLM'), ('C0', 'P500'), ('W0', 'WPSH'), ('WNL04', 'WNLM'), ('W0', 'WP500')):
        if real in full and plc in full:
            a = sum(tot(real, c, days) for c in cells); b = sum(tot(plc, c, days) for c in cells)
            w(f'- {real} {a:+.2f} vs {plc} {b:+.2f}')
    for base, noanc, psh in (('C0', 'NOANC', 'PSH'), ('W0', 'WNOANC', 'WPSH')):
        if all(x in full for x in (base, noanc, psh)):
            a = sum(tot(base, c, days) - tot(noanc, c, days) for c in cells)
            b = sum(tot(psh, c, days) - tot(noanc, c, days) for c in cells)
            w(f'- anchor gain over no anchor on {base}: real {a:+.2f}, shuffled placebo {b:+.2f}')
    w('')
    solid = [r for r in rows if r[6]]
    w(f'## Solid candidates: {len(solid)}')
    for r in sorted(solid, key=lambda r: -r[3]):
        w(f'- {r[0]}: {r[1]} (held-out {r[3]:+.2f} over control, {r[4]}/{len(days)} days, picked in {r[2]:.0%} of folds)')
    with open(out, 'w') as fh:
        fh.write('\n'.join(lines) + '\n')
    with open(os.path.splitext(out)[0] + '.json', 'w') as fh:
        json.dump({'days': days, 'arms': full, 'cells': {r[0]: {'pick': r[1], 'stability': r[2], 'gain': r[3], 'daysAhead': r[4], 'floor': r[5], 'solid': r[6]} for r in rows}}, fh, indent=1)
    print('\n'.join(lines[:40]))


if __name__ == '__main__':
    main()
