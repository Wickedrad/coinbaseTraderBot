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

SEALED = ('2026-11-06', '2026-11-13')   # lockbox L1 (Nov 6 05:00 - Nov 13 05:00 UTC) as whole UTC day files
KEYS = ('bidO', 'bidH', 'bidL', 'bidC', 'askO', 'askH', 'askL', 'askC', 'last')


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--history', default='data/history')
    ap.add_argument('--assets', default='BTC,ETH,SOL,XRP')
    ap.add_argument('--only', default='all', choices=('all', 'tier'), help="'tier': only the tier report and the keep_crossed gate")
    a = ap.parse_args(argv)
    if a.only == 'tier':
        tier_report(a.history, allowed_assets(a.assets.split(',')))
        return
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
            if SEALED[0] <= fn[:10] <= SEALED[1]:
                continue      # the sealed lockbox week is never read (its file names are close days, UTC)
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
    """Are the quotes the study trades on honest? Built exactly as the study builds them (market_to_rows, both sides).
    1. Calibration by data tier, minute group (0 = candle 1's open, 1-13, 14) and ask bucket: mean ask vs share won.
    2. Mean $ of one $15 position by tier and entry minute, four round trips: taker in at the ask, out at the next
       minute's bid (TT1); taker in, held to settlement (TS); maker in at the bid when the study's fill rule fills it,
       out at the next minute's bid (MT1); taker in, maker out at the next minute's ask when filled (TM1).
       Honest quotes lose a little on every one; a minute or tier that makes money has prices nobody could trade.
    3. The largest one-minute winners of the historical tier, with their raw candles."""
    from .data import market_to_rows
    from .fees import contracts_for_stake, maker_fee, taker_fee
    edges = [0, 0.03, 0.1, 0.35, 0.65, 0.9, 0.97, 1.0]
    cal = defaultdict(lambda: np.zeros(3))      # (tier, minutes, bucket) -> n, sum price, sum won
    rt = defaultdict(lambda: np.zeros(8))       # (tier, minute) -> n and sum $ for TT1, TS, MT1, TM1
    top = []
    keys = ('ts', 'bidO', 'bidH', 'bidL', 'bidC', 'askO', 'askH', 'askL', 'askC', 'last', 'volume')
    for asset in assets:
        d = os.path.join(history, 'kalshi', f'KX{asset}15M')
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith('.jsonl'):
                continue
            if SEALED[0] <= fn[:10] <= SEALED[1]:
                continue
            tier = 'live' if fn[:10] >= live_from else 'hist'
            for line in open(os.path.join(d, fn)):
                try:
                    m = json.loads(line)
                except json.JSONDecodeError:
                    continue
                raw = [dict(c) for c in (m.get('candles') or [])]
                r = market_to_rows(m, 15)
                if r is None:
                    continue
                bid, ask, blo, bhi, alo, ahi = r[:6]
                yes = float(m.get('result') == 'yes')
                with np.errstate(invalid='ignore'):
                    for side, b_, a_, al_, bh_, won in (('YES', bid, ask, alo, bhi, yes), ('NO', 1 - ask, 1 - bid, 1 - bhi, 1 - alo, 1 - yes)):
                        for k in range(15):
                            px = a_[k]
                            if np.isfinite(px) and 0 < px < 1:
                                grp = 'm0' if k == 0 else ('m14' if k == 14 else 'm1-13')
                                cal[(tier, grp, int(np.searchsorted(edges, px, side='right') - 1))] += (1, px, won)
                        n = 14
                        A, B, An, Bn = a_[:n], b_[:n], a_[1:n + 1], b_[1:n + 1]
                        okA = np.isfinite(A) & (A > 0) & (A < 1)
                        C = np.where(okA, contracts_for_stake(15.0, np.where(okA, A, 0.5)), 0)
                        cost = np.where(okA, C * A + taker_fee(C, np.where(okA, A, 0.5)), np.nan)
                        okBn = np.isfinite(Bn) & (Bn > 0)
                        tt1 = np.where(okA & okBn, C * np.where(okBn, Bn, 0) - taker_fee(C, np.where(okBn, Bn, 0.5)) - cost, np.nan)
                        ts = np.where(okA, C * won - cost, np.nan)
                        okB = np.isfinite(B) & (B > 0) & (B < 1) & np.isfinite(al_[:n]) & (al_[:n] <= B + 1e-9)
                        Cm = np.where(okB, contracts_for_stake(15.0, np.where(okB, B, 0.5)), 0)
                        mt1 = np.where(okB & okBn, Cm * np.where(okBn, Bn, 0) - taker_fee(Cm, np.where(okBn, Bn, 0.5)) - Cm * np.where(okB, B, 0), np.nan)
                        okM = okA & np.isfinite(An) & (An < 1) & np.isfinite(bh_[1:n + 1]) & (bh_[1:n + 1] >= An - 1e-9)
                        tm1 = np.where(okM, C * np.where(okM, An, 0) - maker_fee(C, np.where(okM, An, 0.5)) - cost, np.nan)
                        for k in range(n):
                            v = rt[(tier, k)]
                            for j, x in enumerate((tt1[k], ts[k], mt1[k], tm1[k])):
                                if np.isfinite(x):
                                    v[2 * j] += 1
                                    v[2 * j + 1] += x
                            if tier == 'hist':
                                best = max((x, nm) for x, nm in ((tt1[k], 'TT1'), (mt1[k], 'MT1'), (tm1[k], 'TM1')) if np.isfinite(x)) if any(
                                    np.isfinite(x) for x in (tt1[k], mt1[k], tm1[k])) else None
                                if best and best[0] > 50 and (len(top) < 8 or best[0] > top[-1][0]):
                                    o = m['closeTime'] - 900_000
                                    cs = [{kk: c.get(kk) for kk in keys} | {'min': round((c['ts'] - o) / 60_000)} for c in raw
                                          if isinstance(c.get('ts'), (int, float)) and -1 <= (c['ts'] - o) / 60_000 - k <= 2]
                                    top.append((round(float(best[0]), 1), best[1], m.get('ticker'), side, k, m.get('result'), cs))
                                    top.sort(key=lambda t: -t[0])
                                    del top[8:]
    print(f'calibration by tier (hist = before {live_from}), minutes, ask bucket: n avg_ask won_share')
    for (tier, grp, b), (n, sp, won) in sorted(cal.items()):
        print(f'{tier} {grp} {edges[b]:.2f}-{edges[b + 1]:.2f} {int(n)} {sp / n:.4f} {won / n:.4f}')
    print('mean $ per $15 position by tier and entry minute: TT1 (n) | TS | MT1 (n) | TM1 (n)')
    for (tier, k), v in sorted(rt.items()):
        f = lambda j: f'{v[2 * j + 1] / max(1, v[2 * j]):+.3f} ({int(v[2 * j])})'
        print(f'{tier} min {k:2d}: {f(0)} | {f(1)} | {f(2)} | {f(3)}')
    for t in top:
        print('big one-minute winner', json.dumps(t)[:690])


def tier_report(history: str, assets: list[str], live_from: str = '2026-09-12', gate_to: str = '2026-06-17'):
    """Historical vs live tier (no P&L, no model): quote coverage, spread, volume, maker-fill rate, crossed windows and the
    settle rate of the windows the training filter drops (max_crossed 0). Then the keep_crossed gate, fixed before any
    run (workflow wf_7de383f8-2f4, Nov 5): on windows opening before gate_to (Apr 18 - Jun 16, never scored out of sample),
    the dropped windows' P(settle YES) exceeds the kept windows' by >= 5 points AND the training pool's P(YES) is >= 1
    point below all windows'. Outcome rates only. The sealed lockbox (Nov 6-13) is never read."""
    import datetime as dt
    from .data import load_kalshi
    from .features import side_quotes
    from .matrix import maker_fills
    day = lambda s: (dt.date.fromisoformat(s) - dt.date(1970, 1, 1)).days
    ms = lambda s: day(s) * 86_400_000
    sealed = set(range(day('2026-11-06'), day('2026-11-13') + 1))
    w = load_kalshi(history, assets, n=15, to_ms=ms('2026-11-06'), log=lambda *_: None, skip_days=sealed)
    if not len(w):
        print('tier report: no windows')
        return
    live = w.open_ms >= ms(live_from)
    bid, ask, nbl, nbh, nal, nah, settle = side_quotes(w)
    fb, fs = maker_fills(bid, ask, nbl, nbh, nal, nah, False)
    book = np.isfinite(w.bid) & np.isfinite(w.ask)
    bad = w.crossed > 0
    lowcov = w.real_frac < 0.8
    q = lambda x, p: float(np.nanpercentile(x, p)) if np.isfinite(x).any() else float('nan')
    rate = lambda m: float(w.settle[m].mean()) if m.any() else float('nan')
    print('\n== Tier report (historical tier before %s, live tier from it; lockbox never read)' % live_from)
    for name, sel in (('historical', ~live), ('live', live)):
        if not sel.any():
            print(f'{name}: no windows')
            continue
        sp = (w.ask - w.bid)[sel][:, 1:]
        kv = w.kvol[sel][:, 1:]
        has = book[sel][:, :-1]
        print(f'{name}: {int(sel.sum())} windows, P(settle YES) {rate(sel):.3f}; two-sided book share minutes 1-14 '
              f'{np.round(book[sel][:, 1:].mean(axis=0), 2).tolist()}')
        print(f'  spread p10/p50/p90 {q(sp, 10):.3f}/{q(sp, 50):.3f}/{q(sp, 90):.3f}; volume/min p50/p90 {q(kv, 50):.0f}/{q(kv, 90):.0f}; '
              f'zero-volume minutes {np.mean(kv == 0):.3f}')
        print(f'  maker fill rate given a book: YES buy {fb[sel][:, 0, :-1][has].mean():.3f}, NO buy {fb[sel][:, 1, :-1][has].mean():.3f}, '
              f'YES sell {fs[sel][:, 0, :-1][has].mean():.3f}, NO sell {fs[sel][:, 1, :-1][has].mean():.3f}')
        print(f'  windows with crossed minutes (dropped from training): {bad[sel].mean():.3f}, P(YES) dropped {rate(sel & bad):.3f} '
              f'vs kept {rate(sel & ~bad):.3f}; coverage < 0.8: {lowcov[sel].mean():.3f}; training pool P(YES) '
              f'{rate(sel & ~bad & ~lowcov):.3f} vs all {rate(sel):.3f}')
    g = w.open_ms < ms(gate_to)
    d_drop, d_kept = rate(g & bad), rate(g & ~bad)
    d_pool, d_all = rate(g & ~bad & ~lowcov), rate(g)
    ok = (d_drop - d_kept >= 0.05) and (d_all - d_pool >= 0.01)
    print(f'GATE keep_crossed (windows before {gate_to}: {int(g.sum())}, {int((g & bad).sum())} dropped): P(YES) dropped {d_drop:.4f} vs kept '
          f'{d_kept:.4f} (needs +0.05), training pool {d_pool:.4f} vs all {d_all:.4f} (needs -0.01): {"PASS" if ok else "FAIL"}')


if __name__ == '__main__':
    main()
