"""Data-quality report of the stored Kalshi 15-minute candles, by month (aggregates only; Kalshi data is public).

    python -m allpairs.diag --history data/history --assets BTC,ETH,SOL,XRP

Per month: markets, share of candle prices under a cent by field, markets whose prices are ALL under a cent (the legacy
cents bug) or MIXED (some fields under a cent among normal ones), crossed quotes (bid > ask), median spread, and the
market's calibration: mean YES mid at minute 7 against the share settled YES. A few mixed examples are printed.
"""
from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict

import numpy as np

from .data import allowed_assets

KEYS = ('bidO', 'bidH', 'bidL', 'bidC', 'askO', 'askH', 'askL', 'askC', 'last')


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--history', default='data/history')
    ap.add_argument('--assets', default='BTC,ETH,SOL,XRP')
    a = ap.parse_args(argv)
    st = defaultdict(lambda: defaultdict(float))
    examples = []
    wk = defaultdict(lambda: [0, 0])
    crossed_ex = []
    for asset in allowed_assets(a.assets.split(',')):
        d = os.path.join(a.history, 'kalshi', f'KX{asset}15M')
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith('.jsonl'):
                continue
            month = fn[:7]
            week = __import__('datetime').date.fromisoformat(fn[:10]).isocalendar()[1]
            for line in open(os.path.join(d, fn)):
                try:
                    m = json.loads(line)
                except json.JSONDecodeError:
                    continue
                cs = m.get('candles') or []
                if not cs:
                    continue
                s = st[month]
                s['markets'] += 1
                vals = []
                sub = defaultdict(int)
                cnt = defaultdict(int)
                for c in cs:
                    for k in KEYS:
                        v = c.get(k)
                        if isinstance(v, (int, float)) and v > 0:
                            vals.append(v)
                            cnt[k] += 1
                            if v < 0.01:
                                sub[k] += 1
                    b, x = c.get('bidC'), c.get('askC')
                    if isinstance(b, (int, float)) and isinstance(x, (int, float)):
                        s['quotes'] += 1
                        wk[(fn[:4], week)][0] += 1
                        if b > x:
                            s['crossed'] += 1
                            wk[(fn[:4], week)][1] += 1
                            if len(crossed_ex) < 8 and len(crossed_ex) < 2 * (1 + len({e[0] for e in crossed_ex})):
                                crossed_ex.append((fn[:7], m.get('ticker'), {k: c.get(k) for k in KEYS}))
                        s['spread_sum'] += x - b
                        if x - b > 0.5:
                            s['wide'] += 1
                for k in KEYS:
                    s[f'n_{k}'] += cnt[k]
                    s[f'sub_{k}'] += sub[k]
                if vals:
                    if max(vals) < 0.01:
                        s['all_sub'] += 1
                    elif min(vals) < 0.01:
                        s['mixed'] += 1
                        if len(examples) < 6 and month < '2026-09':
                            examples.append(dict(ticker=m.get('ticker'), result=m.get('result'), candles=[{k: c.get(k) for k in ('ts', 'bidC', 'askC', 'bidL', 'askH', 'last')} for c in cs[:4]]))
                c7 = next((c for c in cs if isinstance(c.get('ts'), (int, float)) and int(round((c['ts'] - (m['closeTime'] - 900_000)) / 60_000)) == 7), None)
                if c7 and isinstance(c7.get('bidC'), (int, float)) and isinstance(c7.get('askC'), (int, float)) and m.get('result') in ('yes', 'no'):
                    s['cal_n'] += 1
                    s['cal_mid'] += (c7['bidC'] + c7['askC']) / 2
                    s['cal_yes'] += m['result'] == 'yes'
                    s['ask7_lt5'] += c7['askC'] < 0.05
                s['dur_ne_15'] += int((m.get('closeTime', 0) - m.get('openTime', 0)) != 900_000)
    print('month    mkts  all<1c mixed  crossed  wide>50c  spread  mid@7 yes%  ask7<5c  | share of prices <1c by field')
    for month in sorted(st):
        s = st[month]
        q = max(1, s['quotes'])
        fields = ' '.join(f'{k}:{s[f"sub_{k}"] / max(1, s[f"n_{k}"]):.3f}' for k in KEYS)
        print(f'{month}  {int(s["markets"]):5d}  {int(s["all_sub"]):5d}  {int(s["mixed"]):5d}  {s["crossed"] / q:.4f}  {s["wide"] / q:.4f}  '
              f'{s["spread_sum"] / q:.4f}  {s["cal_mid"] / max(1, s["cal_n"]):.3f} {s["cal_yes"] / max(1, s["cal_n"]):.3f}  {s["ask7_lt5"] / max(1, s["cal_n"]):.3f}  | {fields}  len!=15m:{int(s["dur_ne_15"])}')
    print('crossed share by ISO week: ' + ', '.join(f'{y}-W{w:02d} {c / max(1, n):.4f}' for (y, w), (n, c) in sorted(wk.items())))
    for e in crossed_ex:
        print('crossed', json.dumps(e)[:400])
    for e in examples[:2]:
        print('example', json.dumps(e)[:400])
    calibration(a.history, allowed_assets(a.assets.split(',')))


def calibration(history: str, assets: list[str], live_from: str = '2026-09-12'):
    """Are the decision quotes (as the study builds them, after its cuts) honest? Per data tier and YES-ask bucket at
    minutes 1-13: the mean ask and the share settled YES. Buying at an honest ask loses a little on average; a bucket
    whose YES share is far above its ask holds prices nobody could have traded. A few such cases are printed whole."""
    from .data import market_to_rows
    edges = [0, 0.03, 0.06, 0.1, 0.2, 0.35, 0.5, 0.65, 0.8, 0.9, 0.94, 0.97, 1.0]
    acc = defaultdict(lambda: np.zeros(4))      # (tier, side, bucket) -> n, sum price, sum won, sum spread
    bad = []
    for asset in assets:
        d = os.path.join(history, 'kalshi', f'KX{asset}15M')
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith('.jsonl'):
                continue
            tier = 'live' if fn[:10] >= live_from else 'hist'
            for line in open(os.path.join(d, fn)):
                try:
                    m = json.loads(line)
                except json.JSONDecodeError:
                    continue
                raw = json.loads(line).get('candles') or []
                r = market_to_rows(m, 15)
                if r is None:
                    continue
                bid, ask = r[0], r[1]
                yes = m.get('result') == 'yes'
                for k in range(1, 14):
                    for side, px, won, sp in (('YES', ask[k], yes, ask[k] - bid[k]), ('NO', 1 - bid[k], not yes, ask[k] - bid[k])):
                        if not np.isfinite(px):
                            continue
                        b = int(np.searchsorted(edges, px, side='right') - 1)
                        acc[(tier, side, b)] += (1, px, won, sp if np.isfinite(sp) else 0)
                        if won and px <= 0.03 and len(bad) < 10 and len([x for x in bad if x[0] == tier]) < 5:
                            o = m['closeTime'] - 900_000
                            cs = [c for c in raw if isinstance(c.get('ts'), (int, float)) and abs((c['ts'] - o) / 60_000 - k) <= 2]
                            bad.append((tier, m.get('ticker'), side, k, round(float(px), 4), m.get('result'),
                                        [{kk: c.get(kk) for kk in ('ts', 'bidO', 'bidH', 'bidL', 'bidC', 'askO', 'askH', 'askL', 'askC', 'last', 'volume')} for c in cs]))
    print(f'calibration of decision quotes, minutes 1-13 (hist = before {live_from}, live = from it): tier side bucket n avg_price won_share avg_spread')
    for (tier, side, b), (n, sp, won, spr) in sorted(acc.items()):
        print(f'{tier} {side} {edges[b]:.2f}-{edges[b + 1]:.2f} {int(n)} {sp / n:.4f} {won / n:.4f} {spr / n:.4f}')
    for x in bad:
        print('cheap winner', json.dumps(x)[:690])


if __name__ == '__main__':
    main()
