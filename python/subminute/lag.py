"""Is Kalshi's 15-minute book late by seconds? (Steven, Nov 21 2026: recorded days only.)

grid.py keeps, per window and second, the best YES bid and ask, and per coin and second the last index value the bot received. Two questions on those grids,
each judged on days that were not used to choose anything (the build days pick, the check days judge; both are already recorded):

  information  after the index has moved by z volatility units over the last L seconds, does the quote's mid move the same way over the next H seconds
               (entry delayed by d seconds, so a quote that is already gone is not counted)? Slope per price bucket fitted on the build days; R^2 against zero on
               the check days.
  trading      the first second in a range where |z| >= thr: buy the side the index points to at the ask `d` seconds later, then either sell it H seconds after that
               at the bid (both legs pay the taker fee) or hold it to settlement (entry fee only). Net dollars per contract; day-cluster interval; the same
               trigger with the side flipped is the control (it shows what the spread and the fees cost on its own).

Nothing here orders anything. Output is aggregates only.
"""
import argparse
import glob
import json
import math
import os

import numpy as np

from allpairs import fees as KF

STAKE = 10.0
Z95 = 1.959963984540054
WIN, DAY = 900, 86400
WARM = 1800                                    # a window needs 30 minutes of index before it opens
VOLW = 900
LS = (1, 2, 3, 5, 10, 20, 30)
ZS = (1.5, 2.0, 3.0)
HS = (2, 5, 10, 30)
RANGES = ((60, 300), (300, 600), (600, 840))      # the book of a window is only known from about 40 seconds in
SOURCES = ('idx', 'spot', 'perp_mid')              # Kalshi's settlement index, the fast spot feed, the perpetual's mid
DELAYS = (1, 2, 3)
PMIN, PMAX = 0.05, 0.95
BUCKETS = (0.10, 0.30, 0.45, 0.55, 0.70, 0.90)
MIN_BUILD_TRADES = 300


def ffill(x: np.ndarray) -> np.ndarray:
    i = np.maximum.accumulate(np.where(np.isfinite(x), np.arange(len(x)), -1))
    return np.where(i >= 0, x[np.maximum(i, 0)], np.nan)


def prep(z, coin: str, day_ms: int):
    """Per-window arrays of one coin on one day (windows that open at least 30 minutes into the day), or None. z[(source, L)] = the source's move over the
    last L seconds in units of its own trailing volatility."""
    open_s = (z[f'{coin}__open_ms'] - day_ms) // 1000
    keep = (open_s >= WARM) & (open_s + WIN < DAY)
    if not keep.any():
        return None
    G = open_s[keep][:, None] + np.arange(WIN)[None, :]
    zs = {}
    for src in SOURCES:
        if f'{coin}__{src}' not in z:
            continue
        ix = ffill(np.asarray(z[f'{coin}__{src}'], float))
        with np.errstate(divide='ignore', invalid='ignore'):
            lx = np.log(ix)
        r10 = np.zeros(DAY)
        r10[10:] = lx[10:] - lx[:-10]
        r10 = np.nan_to_num(r10)
        cs = np.concatenate([[0.0], np.cumsum(r10 * r10)])
        sig = np.sqrt((cs[G + 1] - cs[G + 1 - VOLW]) / (VOLW * 10.0))     # per-second volatility from the trailing 15 minutes of 10-second returns
        with np.errstate(divide='ignore', invalid='ignore'):
            for L in LS:
                v = (lx[G] - lx[G - L]) / (sig * math.sqrt(L))
                v[~np.isfinite(v)] = np.nan
                zs[(src, L)] = np.clip(v, -8, 8)
    bid, ask = np.asarray(z[f'{coin}__bid'], float)[keep], np.asarray(z[f'{coin}__ask'], float)[keep]
    return {'z': zs, 'bid': bid, 'ask': ask, 'mid': 0.5 * (bid + ask), 'result': np.asarray(z[f'{coin}__result'], float)[keep]}


def trades(pr: dict, src: str, L: int, thr: float, lo: int, hi: int, H: int, d: int) -> dict:
    """Per variant ('follow', 'flip'): (rows, net if sold H seconds later, net if held to settlement, entry price) for the first trigger of each window."""
    z = pr['z'][(src, L)][:, lo:hi]
    with np.errstate(invalid='ignore'):
        hit = np.abs(z) >= thr
    anyhit = hit.any(1)
    if not anyhit.any():
        return {}
    first = hit.argmax(1)
    rows = np.flatnonzero(anyhit)
    s0 = lo + first[rows]
    sgn = np.sign(z[rows, first[rows]])
    se, sx = s0 + d, s0 + d + H
    a_e, b_e = pr['ask'][rows, se], pr['bid'][rows, se]
    a_x, b_x = pr['ask'][rows, sx], pr['bid'][rows, sx]
    res = pr['result'][rows]
    ok = np.isfinite(a_e) & np.isfinite(b_e) & (b_e > 0) & (b_e < a_e) & (a_e < 1)
    out = {}
    for name, side in (('follow', sgn), ('flip', -sgn)):
        up = side > 0
        p_in = np.where(up, a_e, 1 - b_e)
        p_out = np.nan_to_num(np.where(up, b_x, 1 - a_x), nan=0.0)         # a side nobody bids for cannot be sold: it is worth nothing here
        win = np.where(up, res, 1 - res)
        m = ok & (p_in >= PMIN) & (p_in <= PMAX)
        if not m.any():
            continue
        p, po = p_in[m], p_out[m]
        cnt = np.maximum(np.floor(STAKE / p), 1.0)
        fee_in = KF.taker_fee(cnt, p) / cnt
        fee_out = KF.taker_fee(cnt, po) / cnt
        hold = win[m] - p - fee_in
        out[name] = (rows[m], po - p - fee_in - fee_out, hold, p)
    return out


def cell_key(src, L, thr, rng, H, d):
    return (src, L, thr, rng, H, d)


def sweep(preps: list) -> dict:
    """preps: [(day index, prep dict)]. Returns {cell: {variant: {day: [n, sum net_sold, n_hold, sum net_hold, sum price]}}}."""
    acc = {}
    for di, pr in preps:
        for src in {k[0] for k in pr['z']}:
            for L in LS:
                for thr in ZS:
                    for rng in RANGES:
                        for H in HS:
                            for d in DELAYS:
                                for name, (rows, nx, nh, p) in trades(pr, src, L, thr, rng[0], rng[1], H, d).items():
                                    c = acc.setdefault(cell_key(src, L, thr, rng, H, d), {}).setdefault(name, {}).setdefault(di, [0, 0.0, 0, 0.0, 0.0])
                                    fin = np.isfinite(nh)
                                    c[0] += len(nx); c[1] += float(nx.sum()); c[2] += int(fin.sum()); c[3] += float(nh[fin].sum()); c[4] += float(p.sum())
    return acc


def pooled(days: dict, which: int, days_sel: set) -> tuple:
    """Mean, standard error (day clusters), trades, days, positive days of the per-trade net over the selected days; which 0 = sold, 1 = held."""
    n_i, s_i = (0, 1) if which == 0 else (2, 3)
    ds = [d for d in days if d in days_sel and days[d][n_i] > 0]
    N = sum(days[d][n_i] for d in ds)
    if N == 0:
        return None, None, 0, 0, 0
    S = sum(days[d][s_i] for d in ds)
    mean = S / N
    pos = sum(1 for d in ds if days[d][s_i] > 0)
    if len(ds) < 2:
        return mean, None, N, len(ds), pos
    res = np.array([days[d][s_i] - mean * days[d][n_i] for d in ds])
    return mean, math.sqrt(float((res * res).sum()) * len(ds) / (len(ds) - 1)) / N, N, len(ds), pos


def _c(x):
    return None if x is None else round(100 * x, 3)


def describe(cell: dict, which: int, build: set, check: set) -> dict:
    out = {}
    for name in ('follow', 'flip'):
        days = cell.get(name, {})
        o = {}
        for tag, sel in (('build', build), ('check', check)):
            m, se, n, nd, pos = pooled(days, which, sel)
            o[tag] = {'n': n, 'net_c': _c(m), 'lo_c': None if m is None or se is None else _c(m - Z95 * se),
                      'hi_c': None if m is None or se is None else _c(m + Z95 * se), 'days': nd, 'pos_days': pos}
        out[name] = o
    return out


def judge(acc: dict, build: set, check: set, top: int = 6) -> dict:
    res = {}
    for which, label in ((0, 'sold'), (1, 'held')):
        rows = []
        for key, cell in acc.items():
            m, se, n, nd, pos = pooled(cell.get('follow', {}), which, build)
            if m is not None and n >= MIN_BUILD_TRADES:
                rows.append((m, key))
        rows.sort(key=lambda x: -x[0])
        chosen = [{'cell': dict(zip(('src', 'L', 'thr', 'range', 'H', 'delay'), k)), **describe(acc[k], which, build, check)} for _, k in rows[:top]]
        # the cost floor: every cell's follow and flip on the check days, no selection at all
        fm, flm, pos_f = [], [], 0
        for key, cell in acc.items():
            m1 = pooled(cell.get('follow', {}), which, check)
            m2 = pooled(cell.get('flip', {}), which, check)
            if m1[0] is not None and m2[0] is not None and m1[2] >= 100:
                fm.append(m1[0]); flm.append(m2[0]); pos_f += m1[0] > 0
        res[label] = {'cells_with_build_trades': len(rows), 'best_on_build': chosen,
                      'all_cells_check': {'cells': len(fm), 'follow_mean_c': _c(float(np.mean(fm))) if fm else None,
                                          'flip_mean_c': _c(float(np.mean(flm))) if flm else None, 'follow_positive': int(pos_f)}}
    return res


def information(preps: list, build: set, check: set, d: int = 1, back: bool = False) -> dict:
    """Slope of the quote's later mid move (back=True: its move over the same L seconds before, the alignment check) on the source's move, per mid bucket,
    fitted on build days; R^2 against zero on check days."""
    S = np.arange(60, 840 - max(HS) - d, 5)
    out = {}
    srcs = sorted({k[0] for _, pr in preps for k in pr['z']})
    for src in srcs:
        for L in LS:
            for H in ((0,) if back else HS):
                sums = {}
                for di, pr in preps:
                    if (src, L) not in pr['z']:
                        continue
                    x = pr['z'][(src, L)][:, S]
                    if back:
                        m0 = pr['mid'][:, S]
                        y = m0 - pr['mid'][:, S - L]
                    else:
                        m0 = pr['mid'][:, S + d]
                        y = pr['mid'][:, S + d + H] - m0
                    ok = np.isfinite(x) & np.isfinite(y) & np.isfinite(m0)
                    b = np.digitize(m0, BUCKETS)
                    for k in range(1, len(BUCKETS)):
                        sel = ok & (b == k)
                        if sel.any():
                            xs, ys = x[sel], y[sel]
                            t = sums.setdefault((di, k), np.zeros(4))
                            t += [float((xs * ys).sum()), float((xs * xs).sum()), float((ys * ys).sum()), float(sel.sum())]
                beta, sse0, sse1, n_chk, nb = {}, 0.0, 0.0, 0, 0
                for k in range(1, len(BUCKETS)):
                    sxy = sum(v[0] for (di, kk), v in sums.items() if kk == k and di in build)
                    sxx = sum(v[1] for (di, kk), v in sums.items() if kk == k and di in build)
                    beta[k] = sxy / sxx if sxx > 0 else 0.0
                    nb += int(sum(v[3] for (di, kk), v in sums.items() if kk == k and di in build))
                for (di, k), v in sums.items():
                    if di in check:
                        sse0 += v[2]; sse1 += v[2] - 2 * beta[k] * v[0] + beta[k] ** 2 * v[1]; n_chk += int(v[3])
                out[f'{src}_L{L}' + ('' if back else f'_H{H}')] = {
                    'beta_by_bucket_c': [round(100 * beta[k], 4) for k in range(1, len(BUCKETS))], 'n_build': nb, 'n_check': n_chk,
                    'r2_check_1e4': None if sse0 <= 0 else round(1e4 * (1 - sse1 / sse0), 3)}
    return out


def load_days(grids_dir: str, assets=('BTC', 'ETH', 'SOL', 'XRP')) -> list:
    """[(day string, day ms, {coin: prep})] for every grid-DAY.npz, oldest first."""
    import datetime as dt
    out = []
    for p in sorted(glob.glob(os.path.join(grids_dir, 'grid-*.npz'))):
        day = os.path.basename(p)[5:15]
        day_ms = int(dt.datetime.strptime(day, '%Y-%m-%d').replace(tzinfo=dt.timezone.utc).timestamp() * 1000)
        z = np.load(p, allow_pickle=False)
        names = {k.split('__')[0] for k in z.files}
        out.append((day, day_ms, {c: prep(z, c, day_ms) for c in assets if c in names}))
    return out


def run(grids_dir: str, build_last: str, out_dir: str) -> dict:
    days = load_days(grids_dir)
    names = [d[0] for d in days]
    build = {i for i, n in enumerate(names) if n <= build_last}
    check = {i for i, n in enumerate(names) if n > build_last}
    res = {'days': names, 'build_days': len(build), 'check_days': len(check), 'coins': {}}
    preps = [(i, pr) for i, (_, _, ps) in enumerate(days) for pr in ps.values() if pr is not None]
    res['windows'] = int(sum(len(pr['bid']) for _, pr in preps))
    res['information_d1'] = information(preps, build, check, 1)
    res['alignment_back'] = information(preps, build, check, 1, back=True)
    acc = sweep(preps)
    res['trading'] = judge(acc, build, check)
    os.makedirs(out_dir, exist_ok=True)
    json.dump(res, open(os.path.join(out_dir, 'lag.json'), 'w'), indent=1, sort_keys=True, default=float)
    return res


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--grids', required=True)
    ap.add_argument('--build-last', required=True, help='last build day, YYYY-MM-DD; later days are the check days')
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    r = run(a.grids, a.build_last, a.out)
    print('HEATLOOP mdlag ' + json.dumps({'days': r['days'], 'windows': r['windows'], 'trading': r['trading']}, sort_keys=True, default=float), flush=True)
    best = sorted(((v['r2_check_1e4'], k) for k, v in r['information_d1'].items() if v['r2_check_1e4'] is not None), reverse=True)[:8]
    back = {k: v['r2_check_1e4'] for k, v in r['alignment_back'].items()}
    print('HEATLOOP mdlag-info ' + json.dumps({'top_r2_check_1e4': best, 'alignment_back_r2_1e4': back}, sort_keys=True, default=float)[:9000], flush=True)
