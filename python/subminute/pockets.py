"""More pockets like the NO-favourite resting buy, searched on recorded days only (Steven, Nov 22 2026: "look for more like this").

A resting buy at the best bid of its side, no maker fee on Kalshi's crypto 15-minute series, held to settlement. Three recorded blocks, none used for two jobs:

  build   Kalshi's own 15-minute candles, Apr 13 to Jul 31 2026 (BTC, ETH): rules are scored here and the ones that look positive are kept
  check   the same candles, Aug 1 to Oct 31: the kept rules are judged here (day-cluster intervals, dollars an hour at a $10 stake)
  clean   the bot's own full-depth recordings, Nov 11 to 20 (1-second grids, BTC ETH SOL XRP): the best of the checked rules are replayed with the queue-aware
          simulation of maker.py; SOL and XRP were never in the build or the check

A rule is (side, price bucket of the order, placement minutes, cancel minute) in a slice (coin, six-hour block of the UTC day or all of it). The order is placed at the
first decision minute k of the placement range whose book is two-sided and whose side-price is in the bucket (candle k's close, as allpairs/data.py reads it).
Its fill is read off the candles k+1 .. cancel: a YES buy at p is filled when the lowest YES ask of such a candle is at or under p ('touch') or strictly under it
('thru'); a NO buy at p (a YES sell at 1 - p) when the highest YES bid reaches 1 - p ('touch') or goes strictly over it ('thru'). A candle counts only if it traded,
its close is a two-sided book and its highs and lows agree with its own open and close (market_to_rows). 'thru' is the conservative reading and picks the rules.
"""
import argparse
import datetime as dt
import glob
import json
import math
import os

import numpy as np

STAKE = 10.0
Z95 = 1.959963984540054
BUCKETS = tuple((round(0.1 * i, 2), round(0.1 * i + 0.1, 2)) for i in range(1, 9)) + ((0.9, 0.97),)
PLACE = ((1, 3), (3, 6), (6, 9), (9, 12))
CANCEL = (10, 14)
SIDES = ('yes', 'no')
COIN_SLICES = ('BTC', 'ETH', 'ALL')
HOUR_SLICES = (0, 1, 2, 3, 'ALL')                    # six-hour blocks of the UTC day
COLS = 8                                              # orders, fills touch (count, net per contract, dollars), fills thru (same), net per contract if every order filled
MIN_BUILD_FILLS = 300
MIN_CHECK_FILLS = 150


def rules() -> list:
    return [(sd, bk, pl, cn) for sd in SIDES for bk in BUCKETS for pl in PLACE for cn in CANCEL]


def _day(s: str) -> int:
    return (dt.date.fromisoformat(s) - dt.date(1970, 1, 1)).days


def orders(w, side: str, lo: float, hi: float, a: int, b: int):
    """(rows, minute, price): the first decision minute in [a, b) whose book is two-sided and whose side-price is in [lo, hi), per window that has one."""
    p = w.bid if side == 'yes' else 1.0 - w.ask
    with np.errstate(invalid='ignore'):
        ok = np.isfinite(w.bid) & np.isfinite(w.ask) & (p >= lo - 1e-9) & (p < hi - 1e-9)
    ok_r = ok[:, a:b]
    has = ok_r.any(1)
    rows = np.flatnonzero(has)
    k = a + ok_r[rows].argmax(1)
    return rows, k, np.round(p[rows, k], 4)


def fills(w, side: str, rows, k, p, cancel: int, strict: bool):
    """Per order: was it filled by the candles k+1 .. cancel."""
    n = w.bid.shape[1]
    inr = (np.arange(n)[None, :] >= k[:, None]) & (np.arange(n)[None, :] <= cancel - 1)
    if side == 'yes':
        ext, ref = w.nask_lo[rows], p
        with np.errstate(invalid='ignore'):
            hit = ext < ref[:, None] - 1e-9 if strict else ext <= ref[:, None] + 1e-9
    else:
        ext, ref = w.nbid_hi[rows], np.round(1.0 - p, 4)
        with np.errstate(invalid='ignore'):
            hit = ext > ref[:, None] + 1e-9 if strict else ext >= ref[:, None] - 1e-9
    return (hit & inr & np.isfinite(ext)).any(1)


def scan(w, day0: int, nd: int) -> dict:
    """{(rule, coin slice, hour slice): array (nd, COLS)} summed per UTC day."""
    day = (w.day - day0).astype(int)
    coin = w.asset.astype(int)
    hb = (((w.open_ms // 3_600_000) % 24) // 6).astype(int)
    names = [str(a) for a in w.assets]
    acc = {}
    for rule in rules():
        side, (lo, hi), (a, b), cancel = rule
        rows, k, p = orders(w, side, lo, hi, a, b)
        if len(rows) == 0:
            continue
        ft, fh = fills(w, side, rows, k, p, cancel, False), fills(w, side, rows, k, p, cancel, True)
        win = w.settle[rows] if side == 'yes' else 1.0 - w.settle[rows]
        net = win - p
        n = np.maximum(np.floor(STAKE / p + 1e-9), 1.0)
        dol = net * n
        vals = np.stack([np.ones(len(rows)), ft, ft * net, ft * dol, fh, fh * net, fh * dol, net], axis=1)
        d, cn, h = day[rows], coin[rows], hb[rows]
        for cs in COIN_SLICES:
            mc = np.ones(len(rows), bool) if cs == 'ALL' else (cn == names.index(cs) if cs in names else np.zeros(len(rows), bool))
            for hs in HOUR_SLICES:
                sel = mc if hs == 'ALL' else mc & (h == hs)
                if not sel.any():
                    continue
                acc[(rule, cs, hs)] = np.stack([np.bincount(d[sel], weights=vals[sel, j], minlength=nd) for j in range(COLS)], axis=1)
    return acc


def ratio(A: np.ndarray, ni: int, di: int, sel: np.ndarray):
    """(mean of A[:, ni] per unit of A[:, di], its day-cluster standard error, total units, days, days above zero) over the days in `sel` that have units."""
    ds = np.flatnonzero(sel & (A[:, di] > 0))
    D = float(A[ds, di].sum())
    if D == 0:
        return None
    mean = float(A[ds, ni].sum()) / D
    pos = int((A[ds, ni] > 0).sum())
    if len(ds) < 2:
        return mean, None, D, len(ds), pos
    res = A[ds, ni] - mean * A[ds, di]
    return mean, math.sqrt(float((res * res).sum()) * len(ds) / (len(ds) - 1)) / D, D, len(ds), pos


def per_hour(A: np.ndarray, col: int, sel: np.ndarray, have: np.ndarray):
    """Dollars an hour (mean, standard error) over the recorded days of the block, days without an order counting as zero."""
    ds = np.flatnonzero(sel & have)
    if len(ds) < 2:
        return None, None
    x = A[ds, col] / 24.0
    return float(x.mean()), float(x.std(ddof=1) / math.sqrt(len(ds)))


def c(x):
    return None if x is None else round(100.0 * x, 3)


def r3(x):
    return None if x is None else round(float(x), 3)


def cell_stats(A, sel, have) -> dict:
    out = {}
    for tag, (ni, di, dol) in (('thru', (5, 4, 6)), ('touch', (2, 1, 3))):
        m, se, f, nd, pos = ratio(A, ni, di, sel) or (None, None, 0, 0, 0)
        ph, phse = per_hour(A, dol, sel, have)
        out[tag] = {'fills': int(f), 'net_c': c(m), 'lo_c': None if m is None or se is None else c(m - Z95 * se), 'hi_c': None if m is None or se is None else c(m + Z95 * se),
                    'pos_days': pos, 'days': nd, 'dollars_per_hour': r3(ph), 'dph_se': r3(phse)}
    o = float(A[sel, 0].sum())
    out['orders'] = int(o)
    out['gross_if_all_filled_c'] = None if o == 0 else c(float(A[sel, 7].sum()) / o)
    out['fill_rate_thru'] = None if o == 0 else r3(float(A[sel, 4].sum()) / o)
    return out


def cell_name(cell) -> dict:
    (side, bk, pl, cn), cs, hs = cell
    return {'side': side, 'bucket': list(bk), 'place_min': list(pl), 'cancel_min': cn, 'coin': cs, 'hours_utc': 'all' if hs == 'ALL' else f'{6 * hs:02d}-{6 * hs + 6:02d}'}


def search(w, split_day: int, clean_day: int, top: int = 30) -> dict:
    day_nums = np.unique(w.day)
    day0, nd = int(day_nums.min()), int(day_nums.max() - day_nums.min() + 1)
    acc = scan(w, day0, nd)
    dn = np.arange(nd) + day0
    have = np.zeros(nd, bool)
    have[(day_nums - day0).astype(int)] = True
    build, check = have & (dn < split_day), have & (dn >= split_day) & (dn < clean_day)
    rows = []
    for cell, A in acc.items():
        b = ratio(A, 5, 4, build)
        if b is None or b[2] < MIN_BUILD_FILLS or b[1] is None:
            continue
        ck = ratio(A, 5, 4, check)
        rows.append((cell, b, ck))
    kept = [(cell, b, ck) for cell, b, ck in rows if b[0] - Z95 * b[1] > 0]
    kept.sort(key=lambda t: -(t[1][0] - Z95 * t[1][1]))
    ck_means = [ck[0] for _, _, ck in rows if ck is not None and ck[2] >= MIN_CHECK_FILLS]
    ck_kept = [ck[0] for _, _, ck in kept if ck is not None and ck[2] >= MIN_CHECK_FILLS]
    summary = {'blocks': {'build_days': int(build.sum()), 'check_days': int(check.sum())}, 'cells_with_build_fills': len(rows), 'cells_build_lower_bound_positive': len(kept),
               'check_mean_net_per_fill_c_all_cells': c(float(np.mean(ck_means))) if ck_means else None,
               'check_mean_net_per_fill_c_kept_cells': c(float(np.mean(ck_kept))) if ck_kept else None,
               'kept_cells_with_check_fills': len(ck_kept), 'kept_cells_check_positive': int(sum(1 for x in ck_kept if x > 0))}
    top_rows = []
    for cell, b, ck in kept[:top]:
        A = acc[cell]
        top_rows.append({'cell': cell_name(cell), 'build': cell_stats(A, build, have), 'check': cell_stats(A, check, have)})
    surv = []
    for cell, b, ck in kept:
        if ck is not None and ck[2] >= MIN_CHECK_FILLS and ck[0] > 0:
            surv.append((ck[0], cell))
    surv.sort(key=lambda t: -t[0])
    return {'summary': summary, 'top_by_build': top_rows, 'survivors': [cell for _, cell in surv], 'acc': acc, 'have': have, 'build': build, 'check': check}


def exact_clean(grids_dir: str, cells: list, assets=('BTC', 'ETH', 'SOL', 'XRP')) -> list:
    """The queue-aware replay of maker.py on the full-depth days for each cell (coin slice and hour block respected)."""
    from subminute import maker as MK
    paths = sorted(glob.glob(os.path.join(grids_dir, 'grid-*.npz')))
    preps = {}
    for di, p in enumerate(paths):
        day = os.path.basename(p)[5:15]
        day_ms = int(dt.datetime.strptime(day, '%Y-%m-%d').replace(tzinfo=dt.timezone.utc).timestamp() * 1000)
        z = np.load(p, allow_pickle=False)
        have = {k.split('__')[0] for k in z.files}
        for coin in assets:
            if coin in have:
                pr = MK.prep(z, coin, day_ms)
                if pr is not None:
                    pr['_lv'] = {}                                    # the per-window trade indexes are shared by every cell
                    preps[(coin, di)] = pr
    out = []
    for cell in cells:
        (side, (lo, hi), (a, b), cancel), cs, hs = cell
        res = {'cell': cell_name(cell)}
        groups = {'BTC': ['BTC'], 'ETH': ['ETH'], 'ALL': ['BTC', 'ETH']}[cs]
        for gname, coins in (('seen_coins', groups), ('new_coins_sol_xrp', ['SOL', 'XRP'] if cs == 'ALL' else [])):
            if not coins:
                continue
            for q in ('opt', 'pess'):
                days = {}
                for (coin, di), pr in preps.items():
                    if coin not in coins:
                        continue
                    pr = dict(pr)
                    pr['wmask'] = None if hs == 'ALL' else (pr['open_s'] // 3600) // 6 == hs
                    v = MK.simulate(pr, (side, (lo, hi), (60 * a, 60 * b), 60 * cancel, q, None))
                    days.setdefault(di, np.zeros(6))
                    days[di] += v
                sel = set(days)
                m, se, f, nd, pos = MK._ratio(days, 2, 1, sel)
                mo, _, o, _, _ = MK._ratio(days, 4, 0, sel)
                ps = (sum(days[d][5] for d in days) / f) if f else None
                dph = None if not f or not ps else float(sum(days[d][2] for d in days)) * STAKE / ps / (len(days) * 24.0)
                res[f'{gname}_{q}'] = {'fills': int(f), 'orders': int(o), 'net_c': MK._c(m), 'lo_c': None if m is None or se is None else MK._c(m - Z95 * se),
                                       'hi_c': None if m is None or se is None else MK._c(m + Z95 * se), 'pos_days': pos, 'days': nd,
                                       'gross_if_all_filled_c': MK._c(mo), 'dollars_per_hour': r3(dph)}
        out.append(res)
    return out


def run(k15: str, grids: str, out_dir: str, first: str, last: str, split: str, clean: str, top: int = 30, n_clean: int = 30, assets=('BTC', 'ETH')) -> dict:
    from allpairs import data as KD
    lo_ms, hi_ms = _day(first) * 86_400_000, (_day(last) + 1) * 86_400_000
    w = KD.load_kalshi(k15, list(assets), from_ms=lo_ms, to_ms=hi_ms)
    res = search(w, _day(split), _day(clean), top)
    surv = res.pop('survivors')
    for k in ('acc', 'have', 'build', 'check'):
        res.pop(k)
    res['survivor_count'] = len(surv)
    res['clean'] = exact_clean(grids, surv[:n_clean]) if grids and os.path.isdir(grids) and surv else []
    os.makedirs(out_dir, exist_ok=True)
    json.dump(res, open(os.path.join(out_dir, 'pockets.json'), 'w'), indent=1, sort_keys=True, default=float)
    return res


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--k15', required=True)
    ap.add_argument('--grids', default='')
    ap.add_argument('--out', required=True)
    ap.add_argument('--first', default='2026-04-13')
    ap.add_argument('--last', default='2026-11-03')
    ap.add_argument('--split', default='2026-08-01')
    ap.add_argument('--clean', default='2026-11-01')
    ap.add_argument('--top', type=int, default=30)
    ap.add_argument('--n-clean', type=int, default=30)
    a = ap.parse_args()
    r = run(a.k15, a.grids, a.out, a.first, a.last, a.split, a.clean, a.top, a.n_clean)
    print('HEATLOOP mdpocket-summary ' + json.dumps({k: v for k, v in r.items() if k not in ('top_by_build', 'clean')}, sort_keys=True, default=float), flush=True)
    print('HEATLOOP mdpocket-top ' + json.dumps(r['top_by_build'][:12], sort_keys=True, default=float)[:14000], flush=True)
    for i in range(0, len(r['clean']), 8):
        print(f'HEATLOOP mdpocket-clean{i // 8} ' + json.dumps(r['clean'][i:i + 8], sort_keys=True, default=float)[:14000], flush=True)
