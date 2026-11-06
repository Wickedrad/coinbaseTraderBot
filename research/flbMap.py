#!/usr/bin/env python3
"""H-A part 1 / cheap-NO Stage A: the favourite-longshot bias (FLB) map of Kalshi crypto price-prediction markets, fitted
on H-DEV only (Apr 18 - Jul 31 2026). Spec: /mnt/project-files/market-anchor/stageA-flb-spec.md (v1, 00:05 UTC Nov 6),
hypothesis H-A SHARED-SKILL-FLB in /mnt/project-files/institutional-methods/failure-diagnoses.md. Fill-free.

Input:  <kalshi dir>/<SERIES>/<YYYY-MM-DD>.jsonl[.gz]  (research/history/kalshiHistory.ts: one settled market a line,
        1-minute candles in dollars)  and optionally the regime v1 labels CSV (research/regime.py).
Output: <out>/flb-map.json (the frozen map: per kind and per kind x RV tercile, for p = mid and p = ask:
        a, beta, beta 95% CI, n; favourite and longshot net excess in cents with CI), <out>/flb-report.md.

Sample unit: one row per market per time-to-close bucket (bot/strategy/accuracyGate.ts ACCURACY_BUCKETS): the first
eligible minute in the bucket. Eligible: bid and ask present, bid < ask (crossed minutes dropped), not a no-bid 1c ask,
spread <= 10c (dropped share reported, G1b). Markets without a yes/no result are dropped. DOGE never read.
Fit: logit q = a + beta * logit p by weighted Newton; CIs by a market-clustered bootstrap (multinomial market weights).
FLB means beta > 1. Net excess of a buy at ask A on either side: y_side - A - fee(A), with the shared fee
(bot/fees.ts takerFee, 10 contracts, 0.01 balance grid) per contract; favourites A >= 0.70, longshots A <= 0.30.
Falsified (spec): beta's CI includes 1, or the favourite net excess <= 0.

  python3 research/flbMap.py fit KALSHI_DIR OUT_DIR [--labels labels.csv.gz] [--from 2026-04-18] [--to 2026-07-31] [--boot 1000]
  python3 research/flbMap.py selftest
"""
from __future__ import annotations

import csv
import gzip
import json
import math
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone

import numpy as np

BUCKETS = {'updown15m': [(600, 840), (450, 600), (300, 450), (90, 300)],
           'hourly': [(2400, 3300), (1500, 2400), (600, 1500), (90, 600)]}
H_DEV = ('2026-04-18', '2026-07-31')
ASSET = [('KXBTC', 'BTC'), ('KXETH', 'ETH'), ('KXSOL', 'SOL'), ('KXXRP', 'XRP')]
FAV, LS = 0.70, 0.30


def taker_fee(price, count=10, rate=0.07, precision=0.01):
    """Per-contract mirror of bot/fees.ts takerFee (ceil to 6 dp, then onto the balance grid), for `count` contracts."""
    if not (0 < price < 1):
        return 0.0
    model = rate * count * price * (1 - price) * 1e6
    trade = math.ceil(round(model * 1e3) / 1e3)
    notional = round(count * price * 1e6)
    grid = round(precision * 1e6)
    charged = math.ceil((notional + trade) / grid) * grid
    return (charged - notional) / 1e6 / count


def kind_of(series, m):
    s = series.upper()
    if s.endswith('15M'):
        return 'updown15m'
    st = (m.get('strikeType') or '').lower()
    if st in ('between', 'range') or (m.get('cap') is not None and m.get('strike') is not None):
        return 'range'
    return 'threshold'


def asset_of(series):
    for p, a in ASSET:
        if series.upper().startswith(p):
            return a
    return None


def iso_min(ms):
    return datetime.fromtimestamp(ms / 1000 - (ms / 1000) % 60, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def load_labels(path):
    lab = {}
    if not path:
        return lab
    op = gzip.open if path.endswith('.gz') else open
    with op(path, 'rt') as fh:
        r = csv.reader(fh)
        next(r, None)
        for row in r:
            if len(row) >= 6 and row[5] != 'NA':
                lab[(row[1], row[0])] = row[5]
    return lab


def rows_of(m, series, stats):
    """Decision rows of one settled market: (bucket lo, tau, bid, ask, y, minute ms)."""
    res = (m.get('result') or '').lower()
    if res not in ('yes', 'no') or m.get('error'):
        stats['no_result'] += 1
        return []
    y = 1 if res == 'yes' else 0
    close = m.get('closeTime')
    grp = 'updown15m' if series.upper().endswith('15M') else 'hourly'
    out = []
    cs = sorted((c for c in (m.get('candles') or []) if c.get('ts')), key=lambda c: c['ts'])
    for lo, hi in BUCKETS[grp]:
        for c in cs:
            tau = (close - c['ts']) / 1000  # candle end -> seconds to close
            if not (lo < tau <= hi):
                continue
            stats['minutes'] += 1
            b, a = c.get('bidC'), c.get('askC')
            if a is None or b is None:
                stats['drop_missing'] += 1; continue
            if b >= a:
                stats['drop_crossed'] += 1; continue
            if b <= 0 and a <= 0.0101:
                stats['drop_nobid_1c'] += 1; continue
            if a - b > 0.10 + 1e-9:
                stats['drop_wide'] += 1; continue
            out.append((lo, tau, b, a, y, c['ts']))
            break
    return out


def collect(kdir, d0, d1, labels):
    stats = defaultdict(int)
    rows, markets = [], {}
    for series in sorted(os.listdir(kdir)):
        if series.upper().startswith('KXDOGE') or not asset_of(series):
            continue
        sd = os.path.join(kdir, series)
        if not os.path.isdir(sd):
            continue
        for f in sorted(os.listdir(sd)):
            mm = re.match(r'^(\d{4}-\d\d-\d\d)\.jsonl(\.gz)?$', f)
            if not mm or not (d0 <= mm.group(1) <= d1):
                continue
            op = gzip.open if f.endswith('.gz') else open
            with op(os.path.join(sd, f), 'rt') as fh:
                for line in fh:
                    try:
                        m = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    stats['markets'] += 1
                    k = kind_of(series, m)
                    res = (m.get('result') or '').lower()
                    if res in ('yes', 'no'):
                        markets.setdefault(k, []).append(1 if res == 'yes' else 0)
                    for lo, tau, b, a, y, ts in rows_of(m, series, stats):
                        ter = labels.get((asset_of(series), iso_min(ts - 60_000)), 'NA')  # label of the minute the candle covers
                        rows.append({'t': m['ticker'], 'series': series.upper(), 'kind': k, 'lo': lo, 'bid': b, 'ask': a,
                                     'mid': (a + b) / 2, 'y': y, 'ter': ter})
    return rows, markets, stats


def logit(p):
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


def fit_logistic(x, y, w):
    """Weighted logistic regression y ~ a + b x by Newton; returns (a, b)."""
    a, b = 0.0, 1.0
    for _ in range(50):
        z = np.clip(a + b * x, -30, 30)
        q = 1 / (1 + np.exp(-z))
        g0, g1 = np.sum(w * (y - q)), np.sum(w * (y - q) * x)
        v = w * q * (1 - q)
        h00, h01, h11 = np.sum(v), np.sum(v * x), np.sum(v * x * x)
        det = h00 * h11 - h01 * h01
        if det <= 1e-12:
            break
        da, db = (h11 * g0 - h01 * g1) / det, (h00 * g1 - h01 * g0) / det
        a, b = a + da, b + db
        if abs(da) + abs(db) < 1e-9:
            break
    return a, b


def excess(rows, fav):
    """Per-row net excess of buying the side whose ask is in the favourite (or longshot) band, both sides."""
    v = []
    for r in rows:
        ay, an = r['ask'], 1 - r['bid']  # YES ask, NO ask
        for A, ys in ((ay, r['y']), (an, 1 - r['y'])):
            if (A >= FAV) if fav else (A <= LS):
                v.append((r['t'], ys - A - taker_fee(A)))
    return v


def summarize(rows, boot, rng):
    """beta for mid and ask, favourite / longshot net excess, with market-clustered bootstrap CIs."""
    if len(rows) < 30:
        return {'n': len(rows), 'markets': len({r['t'] for r in rows})}
    tick = [r['t'] for r in rows]
    ids = {t: i for i, t in enumerate(dict.fromkeys(tick))}
    mi = np.array([ids[t] for t in tick])
    M = len(ids)
    y = np.array([r['y'] for r in rows], float)
    out = {'n': len(rows), 'markets': M}
    for name in ('mid', 'ask'):
        x = logit(np.array([r[name] for r in rows]))
        a, b = fit_logistic(x, y, np.ones_like(y))
        bs = []
        for _ in range(boot):
            w = rng.multinomial(M, np.ones(M) / M)[mi].astype(float)
            bs.append(fit_logistic(x, y, w)[1])
        lo, hi = np.percentile(bs, [2.5, 97.5]) if bs else (float('nan'), float('nan'))
        out[name] = {'a': a, 'beta': b, 'beta_ci': [float(lo), float(hi)]}
    for nm, fav in (('fav_excess_c', True), ('ls_excess_c', False)):
        v = excess(rows, fav)
        if len(v) < 10:
            out[nm] = {'n': len(v)}
            continue
        tk = [t for t, _ in v]
        ids2 = {t: i for i, t in enumerate(dict.fromkeys(tk))}
        mi2 = np.array([ids2[t] for t in tk])
        vals = np.array([e for _, e in v])
        M2 = len(ids2)
        bs = []
        for _ in range(boot):
            w = rng.multinomial(M2, np.ones(M2) / M2)[mi2].astype(float)
            bs.append(np.sum(w * vals) / max(1e-9, np.sum(w)))
        lo, hi = np.percentile(bs, [2.5, 97.5])
        out[nm] = {'n': len(v), 'mean': float(vals.mean() * 100), 'ci': [float(lo * 100), float(hi * 100)]}
    return out


def fmt_ci(d, k='beta'):
    if not d or k not in d:
        return 'n/a'
    return f'{d[k]:.3f} [{d[k + "_ci"][0]:.3f}, {d[k + "_ci"][1]:.3f}]'


def fmt_ex(d):
    return 'n/a' if not d or 'mean' not in d else f'{d["mean"]:+.2f}c [{d["ci"][0]:+.2f}, {d["ci"][1]:+.2f}] (n {d["n"]})'


def fit(kdir, out, labels_path=None, d0=H_DEV[0], d1=H_DEV[1], boot=1000, sha='unknown'):
    if d1 > H_DEV[1] and d0 <= H_DEV[1]:
        sys.exit('refusing: H-DEV ends 2026-07-31 (HO-1); H-HOLD is never fitted on')
    rng = np.random.default_rng(20261106)
    labels = load_labels(labels_path)
    rows, markets, st = collect(kdir, d0, d1, labels)
    os.makedirs(out, exist_ok=True)
    days = sorted({r['t'] for r in rows})
    res = {'version': 'flb-map v1', 'code_sha': sha, 'h_dev': [d0, d1], 'stats': dict(st), 'kinds': {}, 'terciles': {}, 'series': {}}
    by_kind = defaultdict(list)
    for r in rows:
        by_kind[r['kind']].append(r)
    by_kind['all'] = rows
    for k, rs in sorted(by_kind.items()):
        res['kinds'][k] = summarize(rs, boot, rng)
        kept_y = [r['y'] for r in rs]
        all_y = markets.get(k, []) if k != 'all' else [v for vs in markets.values() for v in vs]
        if kept_y and all_y:
            res['kinds'][k]['pyes_kept'] = sum(kept_y) / len(kept_y)
            res['kinds'][k]['pyes_all'] = sum(all_y) / len(all_y)
        for ter in ('LOW', 'MID', 'HIGH'):
            sub = [r for r in rs if r['ter'] == ter]
            res['terciles'][f'{k}|{ter}'] = summarize(sub, max(200, boot // 5), rng)
    by_ser = defaultdict(list)
    for r in rows:
        by_ser[r['series']].append(r)
    for s_, rs in sorted(by_ser.items()):
        d = summarize(rs, max(200, boot // 5), rng)
        ex = [r for r in rs if r['ask'] >= FAV or (1 - r['bid']) >= FAV][:5]
        d['examples'] = [{'ticker': r['t'], 'ask': r['ask'], 'bid': r['bid'], 'y': r['y']} for r in ex]
        res['series'][s_] = d
    a = res['kinds'].get('all', {})
    fals = []
    if 'mid' in a and a['mid']['beta_ci'][0] <= 1 <= a['mid']['beta_ci'][1]:
        fals.append('beta (mid) CI includes 1')
    if 'mean' in a.get('fav_excess_c', {}) and a['fav_excess_c']['mean'] <= 0:
        fals.append('favourite net excess <= 0')
    res['falsified'] = fals
    with open(os.path.join(out, 'flb-map.json'), 'w') as fh:
        json.dump(res, fh, indent=1)
    tot = st['minutes'] or 1
    L = [f'# FLB map v1 (H-A part 1 / cheap-NO Stage A), H-DEV {d0} to {d1}, code {sha}', '',
         f'{st["markets"]} markets read (no DOGE), {len(rows)} decision rows. Bucket minutes dropped: crossed '
         f'{st["drop_crossed"]} ({st["drop_crossed"] / tot:.1%}), no-bid 1c ask {st["drop_nobid_1c"]}, spread > 10c '
         f'{st["drop_wide"]} ({st["drop_wide"] / tot:.1%}), missing quote {st["drop_missing"]}; no result {st["no_result"]} markets.',
         '', f'**Verdict:** {"FALSIFIED: " + "; ".join(fals) if fals else "not falsified (FLB present and favourites pay after fees)"}', '',
         '## By kind', '| kind | rows | markets | beta (mid) [95% CI] | beta (ask) [95% CI] | favourite net excess | longshot net excess | P(YES) kept / all |',
         '|---|---|---|---|---|---|---|---|']
    for k, d in res['kinds'].items():
        py = f'{d["pyes_kept"]:.3f} / {d["pyes_all"]:.3f}{" G1c" if abs(d["pyes_kept"] - d["pyes_all"]) > 0.02 else ""}' if 'pyes_kept' in d else 'n/a'
        L.append(f'| {k} | {d["n"]} | {d.get("markets", 0)} | {fmt_ci(d.get("mid"))} | {fmt_ci(d.get("ask"))} | {fmt_ex(d.get("fav_excess_c"))} | {fmt_ex(d.get("ls_excess_c"))} | {py} |')
    L += ['', '## By kind x RV tercile (regime v1)', '| kind / tercile | rows | beta (mid) | favourite net excess | longshot net excess |', '|---|---|---|---|---|']
    for k, d in res['terciles'].items():
        L.append(f'| {k} | {d["n"]} | {fmt_ci(d.get("mid"))} | {fmt_ex(d.get("fav_excess_c"))} | {fmt_ex(d.get("ls_excess_c"))} |')
    L += ['', '## Per-series audit', '| series | rows | beta (mid) | favourite net excess | examples (ticker ask/bid -> y) |', '|---|---|---|---|---|']
    for s_, d in res['series'].items():
        exs = '; '.join(f'{e["ticker"]} {e["ask"]:.2f}/{e["bid"]:.2f}->{e["y"]}' for e in d['examples'])
        L.append(f'| {s_} | {d["n"]} | {fmt_ci(d.get("mid"))} | {fmt_ex(d.get("fav_excess_c"))} | {exs} |')
    L += ['', 'Not in this job (spec items that need the bot): the selection split (b) needs the harness per-decision log; the live',
          'tier (Oct 21 on) is inside H-HOLD and is reported by H-A part 2, the one H-HOLD scoring job.']
    with open(os.path.join(out, 'flb-report.md'), 'w') as fh:
        fh.write('\n'.join(L) + '\n')
    print('\n'.join(L[:16]))


def selftest():
    assert abs(taker_fee(0.5) - 0.018) < 1e-9, taker_fee(0.5)  # 0.07*10*0.25 = $0.175 -> $0.18 on the cent grid
    rng = np.random.default_rng(1)
    p = rng.uniform(0.05, 0.95, 20000)
    x = logit(p)
    y = (rng.uniform(size=p.size) < 1 / (1 + np.exp(-(0.1 + 1.3 * x)))).astype(float)
    a, b = fit_logistic(x, y, np.ones_like(y))
    assert abs(b - 1.3) < 0.08 and abs(a - 0.1) < 0.08, (a, b)
    m = {'ticker': 'KXBTC15M-X', 'result': 'yes', 'closeTime': 900_000, 'candles': [
        {'ts': 60_000 * i, 'bidC': 0.40, 'askC': 0.40 if i == 1 else 0.44} for i in range(1, 15)]}
    st = defaultdict(int)
    rs = rows_of(m, 'KXBTC15M', st)
    assert st['drop_crossed'] == 1 and len(rs) == 4, (dict(st), rs)
    print('flbMap selftest ok')


def main(a):
    if not a or a[0] in ('-h', '--help'):
        print(__doc__)
    elif a[0] == 'selftest':
        selftest()
    elif a[0] == 'fit':
        opt = lambda k, d=None: a[a.index(k) + 1] if k in a else d
        fit(a[1], a[2], opt('--labels'), opt('--from', H_DEV[0]), opt('--to', H_DEV[1]), int(opt('--boot', '1000')), opt('--sha', 'unknown'))
    else:
        sys.exit(f'unknown command {a[0]}')


if __name__ == '__main__':
    main(sys.argv[1:])
