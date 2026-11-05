#!/usr/bin/env python3
"""regime v1: per-asset market regime labels for every minute, frozen spec at
/mnt/project-files/registry/regime-v1-spec.md (meta thread, 15:45 UTC Nov 5). The TypeScript mirror
(bot/model/regimeV1.ts, market-anchor thread) must match this file on the fixture it writes.

Label at minute t (bar open time) uses only bars that closed by t, i.e. bars opened at t-1 min and earlier:
  RV60     sqrt(sum of squared 1-minute log returns over the last 60 closed minutes), not annualized;
           NA when fewer than 50 of those 60 returns exist (gaps)
  q33/q67  33.33 / 66.67 percentiles (linear interpolation, numpy default) of every minute RV60 of that asset in the
           30 days ending at the previous 00:00 UTC; recomputed once per UTC day; NA when fewer than 7 distinct days
           of RV60 lie in that window
  tercile  LOW (RV60 < q33) | MID (q33 <= RV60 < q67) | HIGH (RV60 >= q67) | NA
  z60      ln(close[t-1] / close[t-61]) / RV60; trend FLAT (|z60| < 1) | TREND (1-2) | STRONG (> 2)
  v1.1     series type MATCH (tennis): frac_left = 1 - MatchTracker.progress, RV/z60 NA (bot side, not computed here)

Input: <dir>/<ASSET>/1m.csv with rows ts,o,h,l,c[,v...] (ts = bar open, ms or s), the Drive raw/history/binance-1m
layout. Output CSV: ts_iso,asset,rv60,q33,q67,tercile,z60,trend.

  python3 research/regime.py label DIR OUT.csv [--assets BTC,ETH,SOL,XRP] [--from YYYY-MM-DD] [--to YYYY-MM-DD]
  python3 research/regime.py selftest
"""
from __future__ import annotations

import bisect
import csv
import math
import os
import sys
from collections import deque
from datetime import datetime, timezone

VERSION = 'regime-v1.1'
MIN = 60_000
DAY = 86_400_000
LOOKBACK_DAYS = 30
MIN_DAYS = 7
MIN_RETURNS = 50


def read_closes(path):
    """{bar open ms: close}"""
    out = {}
    with open(path) as fh:
        for line in fh:
            if not line or line.startswith('ts'):
                continue
            f = line.split(',')
            try:
                ts, c = float(f[0]), float(f[4])
            except (ValueError, IndexError):
                continue
            if ts <= 0 or c <= 0:
                continue
            ts = int(ts if ts > 1e11 else ts * 1000)
            out[ts - ts % MIN] = c
    return out


def percentile(sorted_x, q):
    """numpy.percentile(x, q) with the default linear interpolation; sorted_x ascending."""
    n = len(sorted_x)
    if n == 0:
        return float('nan')
    pos = (n - 1) * q / 100.0
    lo = math.floor(pos)
    hi = min(lo + 1, n - 1)
    return sorted_x[lo] + (sorted_x[hi] - sorted_x[lo]) * (pos - lo)


def rv_series(closes):
    """{t: (rv60, z60)} for every minute t that has a closed bar at t-1 min."""
    ts = sorted(closes)
    out = {}
    win = deque()  # (bar open ms of the later bar, squared return) over bars opened in [t-60min, t-1min]
    ss = 0.0
    prev_t, prev_c = None, None
    for t1 in ts:  # t1 = open of the bar that just closed; label minute t = t1 + 1 min
        c = closes[t1]
        if prev_t is not None and t1 - prev_t == MIN:
            r2 = math.log(c / prev_c) ** 2
            win.append((t1, r2))
            ss += r2
        prev_t, prev_c = t1, c
        t = t1 + MIN
        while win and win[0][0] < t - 60 * MIN:
            ss -= win.popleft()[1]
        if len(win) < MIN_RETURNS:
            out[t] = (float('nan'), float('nan'))
            continue
        rv = math.sqrt(max(ss, 0.0))
        c0 = closes.get(t1 - 60 * MIN)  # close of the bar 61 minutes before t
        z = math.log(c / c0) / rv if (c0 and rv > 0) else float('nan')
        out[t] = (rv, z)
    return out


def label(rv, start_ms=None, end_ms=None):
    """Yields (t, rv60, q33, q67, tercile, z60, trend) for t in [start, end)."""
    ts = sorted(rv)
    vals_t = [t for t in ts if math.isfinite(rv[t][0])]
    cache = {}

    def cuts(day0):
        if day0 not in cache:
            lo = bisect.bisect_left(vals_t, day0 - LOOKBACK_DAYS * DAY)
            hi = bisect.bisect_left(vals_t, day0)
            w = vals_t[lo:hi]
            days = {t // DAY for t in w}
            if len(days) < MIN_DAYS:
                cache[day0] = (float('nan'), float('nan'))
            else:
                xs = sorted(rv[t][0] for t in w)
                cache[day0] = (percentile(xs, 100 / 3), percentile(xs, 200 / 3))
        return cache[day0]

    for t in ts:
        if start_ms is not None and t < start_ms or end_ms is not None and t >= end_ms:
            continue
        r, z = rv[t]
        q33, q67 = cuts(t - t % DAY)
        if not (math.isfinite(r) and math.isfinite(q33)):
            ter = 'NA'
        else:
            ter = 'LOW' if r < q33 else 'MID' if r < q67 else 'HIGH'
        trend = 'NA' if not math.isfinite(z) else 'FLAT' if abs(z) < 1 else 'TREND' if abs(z) <= 2 else 'STRONG'
        yield t, r, q33, q67, ter, z, trend


def iso(t):
    return datetime.fromtimestamp(t / 1000, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def day_ms(s):
    return int(datetime.strptime(s, '%Y-%m-%d').replace(tzinfo=timezone.utc).timestamp() * 1000)


def fmt(x):
    return '' if not math.isfinite(x) else f'{x:.10g}'


def run_label(src, out, assets, frm=None, to=None):
    s, e = (day_ms(frm) if frm else None), (day_ms(to) + DAY if to else None)
    n = 0
    counts = {}
    with open(out, 'w', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['ts_iso', 'asset', 'rv60', 'q33', 'q67', 'tercile', 'z60', 'trend'])
        for a in assets:
            p = os.path.join(src, a, '1m.csv')
            if not os.path.exists(p):
                print(f'{a}: no {p}, skipped', file=sys.stderr)
                continue
            for t, r, q33, q67, ter, z, tr in label(rv_series(read_closes(p)), s, e):
                w.writerow([iso(t), a, fmt(r), fmt(q33), fmt(q67), ter, fmt(z), tr])
                counts[(a, ter)] = counts.get((a, ter), 0) + 1
                n += 1
    for (a, ter), c in sorted(counts.items()):
        print(f'{a} {ter}: {c} min', file=sys.stderr)
    print(f'{VERSION}: {n} rows -> {out}', file=sys.stderr)


def selftest():
    assert abs(percentile([1, 2, 3, 4], 100 / 3) - 2.0) < 1e-12
    assert abs(percentile([1, 2, 3, 4, 10], 200 / 3) - (3 + (4 - 3) * (8 / 3 - 2))) < 1e-12
    base = day_ms('2026-10-01')
    closes = {}
    p = 100.0
    for i in range(10 * 1440):
        vol = 0.0005 if (i // 1440) % 2 == 0 else 0.002  # calm and wild days alternate
        p *= math.exp(vol * (1 if (i * 7919) % 3 == 0 else -1 if (i * 7919) % 3 == 1 else 0.5))
        closes[base + i * MIN] = p
    rv = rv_series(closes)
    t = base + 3 * 1440 * MIN + 600 * MIN
    assert math.isfinite(rv[t][0]) and math.isfinite(rv[t][1])
    gap = dict(closes)
    for k in range(20):
        gap.pop(base + (2000 + k) * MIN, None)
    assert not math.isfinite(rv_series(gap)[base + 2021 * MIN][0])  # 20-minute hole -> under 50 returns -> NA
    lab = {x[0]: x for x in label(rv)}
    assert lab[base + 5 * 1440 * MIN + 600 * MIN][4] == 'NA'  # only 5 days of history before day 6
    late = [lab[base + d * 1440 * MIN + 600 * MIN][4] for d in (8, 9)]
    assert late == ['LOW', 'HIGH'], late  # day 8 calm, day 9 wild
    print('regime selftest ok')


def main(a):
    if not a or a[0] in ('-h', '--help'):
        print(__doc__)
    elif a[0] == 'selftest':
        selftest()
    elif a[0] == 'label':
        opt = lambda k, d=None: a[a.index(k) + 1] if k in a else d
        run_label(a[1], a[2], opt('--assets', 'BTC,ETH,SOL,XRP').split(','), opt('--from'), opt('--to'))
    else:
        sys.exit(f'unknown command {a[0]}')


if __name__ == '__main__':
    main(sys.argv[1:])
