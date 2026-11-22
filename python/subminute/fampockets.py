"""Round 5b (Nov 22 2026, recorded days only): do resting buys earn on Kalshi's other 15-minute families (oil, metals, gas, FX, rates, alt coins)?

The survey (series_survey.py) found 15-minute series outside the BTC/ETH/SOL/XRP four that pay no maker fee (not in feeScheduleSnapshot nonStandard) and trade:
WTI, silver, natural gas, Brent, platinum, EURUSD, USDJPY, GBPUSD, AUDUSD, two Treasury yields, NEAR, HYPE, Zcash. This reads their public 1-minute candles (Drive
raw/oracle-history/kalshi/KX<A>15M, fetched by the famcandles stage) with pockets.py, unchanged: a resting buy at the best bid of its side, placed in minutes 1-12, cancelled
at 10 or 14, held to settlement, a fill read off the next candles ('thru' = strictly through the order, the conservative reading), no maker fee.

Three recorded blocks of the days that were fetched, in time order, none used for two jobs:

  build   the first half of the days: the rules (side, price bucket, placement minutes, cancel minute, asset, six-hour block) are scored here
  check   the next quarter: rules whose build 95% lower bound (day-cluster) is above zero are judged here
  clean   the last quarter: what the check blocks kept is read here, once

A pass needs the day-cluster lower bound above zero on the check block with at least 150 fills and a positive point estimate on the build and clean blocks. The no-signal twin
is the same table read on the other side at the same price (side flipped), and the mean over every rule (all of them are blind to anything but price and minute).
Nothing is ordered; aggregates only.
"""
import argparse
import json
import os

import numpy as np

from subminute import pockets as PK


def _blocks(w, build_frac: float, clean_frac: float):
    days = np.unique(w.day)
    if len(days) < 8:
        raise ValueError(f'only {len(days)} day(s) of candles')
    split = int(days[int(len(days) * build_frac)])
    clean = int(days[int(len(days) * (1.0 - clean_frac))])
    return split, clean


def _masks(acc_have, split: int, clean: int, day0: int, nd: int):
    dn = np.arange(nd) + day0
    have = acc_have
    return {'build': have & (dn < split), 'check': have & (dn >= split) & (dn < clean), 'clean': have & (dn >= clean)}, have


def _row(sd, bk, pl, st):
    b, k, c = st['build']['thru'], st['check']['thru'], st['clean']['thru']
    return [sd, bk[0], pl[0], b['net_c'], b['fills'], k['net_c'], k['lo_c'], k['hi_c'], k['fills'], st['check']['gross_if_all_filled_c'], c['net_c'], c['lo_c'], c['hi_c'], c['fills']]


def digest(rows, min_fills: int = 150) -> dict:
    """One scope's map in a few numbers: rows are [side, bucket lo, place from, build net, build fills, check net, check lo, check hi, check fills, check gross, clean net, clean lo, clean hi, clean fills]."""
    def wmean(sel, vi, fi):
        d = [(r[vi], r[fi]) for r in sel if r[vi] is not None and r[fi]]
        n = sum(f for _, f in d)
        return None if n == 0 else round(sum(v * f for v, f in d) / n, 3)
    out = {'rows': len(rows)}
    for sd in PK.SIDES:
        sel = [r for r in rows if r[0] == sd]
        out[sd] = {'build_net_c': wmean(sel, 3, 4), 'check_net_c': wmean(sel, 5, 8), 'clean_net_c': wmean(sel, 10, 13), 'check_fills': int(sum(r[8] for r in sel)), 'clean_fills': int(sum(r[13] for r in sel))}
    ok = [r for r in rows if r[8] >= min_fills and r[13] >= min_fills]
    out['rows_with_fills'] = len(ok)
    out['check_positive'] = sum(1 for r in ok if r[5] is not None and r[5] > 0)
    out['check_lo_above_zero'] = [r for r in ok if r[6] is not None and r[6] > 0]
    out['clean_lo_above_zero'] = [r for r in ok if r[11] is not None and r[11] > 0]
    out['positive_in_all_three_blocks'] = [r for r in ok if r[3] is not None and r[3] > 0 and r[5] is not None and r[5] > 0 and r[10] is not None and r[10] > 0]
    out['best_check'] = sorted(ok, key=lambda r: -(r[5] if r[5] is not None else -99))[:3]
    out['best_clean'] = sorted(ok, key=lambda r: -(r[10] if r[10] is not None else -99))[:3]
    return out


def run(hist: str, series_fmt: str, assets, out_dir: str, build_frac: float = 0.5, clean_frac: float = 0.25, top: int = 10, log=print) -> dict:
    from allpairs import data as KD
    assets = [a for a in assets if a]
    w = KD.load_kalshi(hist, assets, n=15, series_fmt=series_fmt, log=log)
    if len(w.day) == 0:
        raise ValueError('no windows')
    split, clean = _blocks(w, build_frac, clean_frac)
    old = PK.COIN_SLICES
    PK.COIN_SLICES = tuple(a for a in (str(x) for x in w.assets)) + ('ALL',)
    try:
        res = PK.search(w, split, clean, top)
    finally:
        PK.COIN_SLICES = old
    acc, have_ = res.pop('acc'), res.pop('have')
    res.pop('build'), res.pop('check')
    surv = res.pop('survivors')
    day0 = int(np.unique(w.day).min())
    nd = int(np.unique(w.day).max() - day0 + 1)
    masks, have = _masks(have_, split, clean, day0, nd)
    names = [str(a) for a in w.assets]
    asset_of = np.asarray(w.asset).astype(int)
    per_asset = {}
    for i, a in enumerate(names):
        sel = asset_of == i
        per_asset[a] = {'windows': int(sel.sum()), 'days': int(len(np.unique(np.asarray(w.day)[sel]))), 'avg_contracts_per_window': round(float(np.asarray(w.kvol)[sel].sum(1).mean()), 1) if sel.any() else 0.0}
    date = lambda d: (np.datetime64('1970-01-01') + np.timedelta64(int(d), 'D')).astype(str)
    maps, passes = {}, []
    for scope in names + ['ALL']:
        rows = []
        for sd in PK.SIDES:
            for bk in PK.BUCKETS:
                for pl in PK.PLACE:
                    A = acc.get(((sd, bk, pl, max(PK.CANCEL)), scope, 'ALL'))
                    if A is None:
                        continue
                    st = {k: PK.cell_stats(A, m, have) for k, m in masks.items()}
                    rows.append(_row(sd, bk, pl, st))
        maps[scope] = rows
    ranked = []
    for cell in surv:                       # build lower bound above zero and a positive, well-filled check mean (search())
        A = acc[cell]
        st = {k: PK.cell_stats(A, m, have) for k, m in masks.items()}
        k, c = st['check']['thru'], st['clean']['thru']
        ok = k['lo_c'] is not None and k['lo_c'] > 0 and k['fills'] >= PK.MIN_CHECK_FILLS and c['net_c'] is not None and c['net_c'] > 0 and st['build']['thru']['net_c'] > 0
        ranked.append((k['net_c'] or -9, {'cell': PK.cell_name(cell), 'build': st['build']['thru'], 'check': k, 'clean': c, 'pass': bool(ok), 'orders_check': st['check']['orders'], 'gross_check_c': st['check']['gross_if_all_filled_c']}))
        if ok:
            passes.append(ranked[-1][1])
    ranked.sort(key=lambda t: -t[0])
    rules_total = len(PK.rules()) * len(PK.COIN_SLICES) * len(PK.HOUR_SLICES)
    out = {'series_fmt': series_fmt, 'assets': per_asset, 'blocks': {'build': [date(np.unique(w.day).min()), date(split - 1)], 'check': [date(split), date(clean - 1)], 'clean': [date(clean), date(np.unique(w.day).max())]},
           'summary': res['summary'], 'survivor_count': len(surv), 'passes': passes[:top], 'pass_count': len(passes), 'top_survivors': [r for _, r in ranked[:top]], 'rule_slots': rules_total, 'maps': maps}
    os.makedirs(out_dir, exist_ok=True)
    json.dump(out, open(os.path.join(out_dir, 'fampockets.json'), 'w'), indent=1, sort_keys=True, default=float)
    return out


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--hist', required=True, help='a directory holding kalshi/KX<A>15M/DAY.jsonl')
    ap.add_argument('--series-fmt', default='KX{asset}15M')
    ap.add_argument('--assets', required=True, help='comma-separated, e.g. WTI,SILVER,NATGAS')
    ap.add_argument('--out', required=True)
    ap.add_argument('--top', type=int, default=10)
    ap.add_argument('--maps', action='store_true', help='print every scope\'s whole map (long); the digest is always printed')
    a = ap.parse_args()
    r = run(a.hist, a.series_fmt, [x.strip().upper() for x in a.assets.split(',')], a.out, top=a.top, log=lambda *x: None)
    print('HEATLOOP famp-summary ' + json.dumps({k: v for k, v in r.items() if k not in ('maps', 'top_survivors', 'passes')}, sort_keys=True, default=float), flush=True)
    print('HEATLOOP famp-cols [side, bucket lo, place from minute, build net c, build fills, check net c, check lo, check hi, check fills, check gross if all filled c, clean net c, clean lo, clean hi, clean fills]', flush=True)
    for scope, rows in r['maps'].items():
        print(f'HEATLOOP famp-digest {scope} ' + json.dumps(digest(rows), sort_keys=True, default=float), flush=True)
        if a.maps:
            print(f'HEATLOOP famp-map {scope} ' + json.dumps(rows, default=float), flush=True)
    print('HEATLOOP famp-top ' + json.dumps(r['top_survivors'][:6], sort_keys=True, default=float)[:12000], flush=True)
