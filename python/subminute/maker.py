"""Can a resting buy order (a maker, no fee on Kalshi's crypto 15-minute series) earn more than the adverse selection costs it? (Steven, Nov 21 2026: recorded days only.)

On the 1-second grids of grid.py (best bid and ask with their sizes, every taker trade with its price and side, the settlement index, the determined result):
a buy order is placed at the best bid of its side (YES bid, or NO bid = 1 - best YES ask) in a price bucket, at the first second of a placement range where that
bucket holds (and, optionally, where the index has not just moved against it), and rests to the cancel second, which is also earlier when the index then moves
against it. It is filled when taker volume at its price has used up the visible queue ahead of it plus its own size, or when a taker trade goes through its
price (the level was cleared). Two queue assumptions bracket what cancellations ahead of us would do: `pess` the whole visible size at the level sits ahead of us and
only trades shorten it; `opt` we are first in line. A fill is held to settlement (no exit, the settlement pays 0 or 1). Maker fee 0 (the crypto 15M series are
not in Kalshi's non-standard fee table: allpairs/fees.py); the stress arm charges the full 0.0175 rate anyway.

What it reports, per rule and day, summed and judged like lag.py (build days pick the rule, check days judge it): orders, fills, net dollars per filled contract,
and what the same orders would have earned unfilled (a gap between the two is adverse selection).
"""
import argparse
import datetime as dt
import glob
import itertools
import json
import math
import os
from collections import Counter

import numpy as np

from allpairs import fees as KF
from subminute import lag as LG

STAKE = 10.0
Z95 = 1.959963984540054
WIN, DAY = 900, 86400
BUCKETS = ((0.50, 0.60), (0.60, 0.70), (0.70, 0.80), (0.80, 0.90), (0.90, 0.97))
PLACE = ((60, 180), (180, 420), (420, 720))
CANCEL = (600, 840, 900)
QUEUE = ('pess', 'opt')
GUARDS = (None, (10, 1.0))                       # (source seconds L, volatility units): not placed, and cancelled, when the index moves this far against the order
SIDES = ('yes', 'no')
MIN_BUILD_FILLS = 200


def prep(z, coin: str, day_ms: int):
    """lag.prep arrays plus the sizes and the trades of the same windows (those that open at least 30 minutes into the day)."""
    base = LG.prep(z, coin, day_ms)
    if base is None:
        return None
    open_s = (z[f'{coin}__open_ms'] - day_ms) // 1000
    keep = (open_s >= LG.WARM) & (open_s + WIN < DAY)
    rows = np.flatnonzero(keep)
    base['bsz'] = np.asarray(z[f'{coin}__bsz'], float)[keep]
    base['asz'] = np.asarray(z[f'{coin}__asz'], float)[keep]
    tw, tms, tp, tc, ts = (np.asarray(z[f'{coin}__{k}']) for k in ('tr_w', 'tr_ms', 'tr_p', 'tr_c', 'tr_side'))
    remap = np.full(len(keep), -1, np.int64)
    remap[rows] = np.arange(len(rows))
    w = remap[tw]
    ok = w >= 0
    order = np.argsort(w[ok], kind='stable')
    w, tms, tp, tc, ts = w[ok][order], tms[ok][order], tp[ok][order].astype(float), tc[ok][order].astype(float), ts[ok][order]
    cut = np.searchsorted(w, np.arange(len(rows) + 1))
    base['trades'] = [(tms[cut[i]:cut[i + 1]], tp[cut[i]:cut[i + 1]], tc[cut[i]:cut[i + 1]], ts[cut[i]:cut[i + 1]]) for i in range(len(rows))]
    return base


class Levels:
    """The taker trades of one window, indexed for fill questions about one side: volume at an exact price over time, and the first trade through a price."""
    def __init__(self, ms, p, c, side, want_side: int):
        m = side == want_side
        self.ms, self.p, self.c = ms[m], np.round(p[m], 3), c[m]
        self._level, self._through = {}, {}

    def level(self, price: float):
        k = round(price, 3)
        if k not in self._level:
            m = self.p == k
            self._level[k] = (self.ms[m], np.cumsum(self.c[m]))
        return self._level[k]

    def through(self, price: float, below: bool):
        k = (round(price, 3), below)
        if k not in self._through:
            m = self.p < round(price, 3) - 1e-9 if below else self.p > round(price, 3) + 1e-9
            self._through[k] = self.ms[m]
        return self._through[k]


def fill_time(lv: Levels, price: float, below: bool, t0: int, tc: int, queue: float, size: float):
    """Millisecond of the fill (None if not filled before tc): enough volume at the price after t0, or any trade through it."""
    out = None
    ms, cum = lv.level(price)
    if len(ms):
        i0 = np.searchsorted(ms, t0, side='right')
        base = cum[i0 - 1] if i0 > 0 else 0.0
        j = np.searchsorted(cum, base + queue + size - 1e-9, side='left')
        if j < len(ms):
            out = int(ms[j])
    th = lv.through(price, below)
    if len(th):
        k = np.searchsorted(th, t0, side='right')
        if k < len(th):
            out = int(th[k]) if out is None else min(out, int(th[k]))
    return out if out is not None and out <= tc else None


def simulate(pr: dict, rule: tuple) -> np.ndarray:
    """One day of one coin under one rule: [orders, fills, sum net per filled contract, same under the stress fee, sum net per contract over all orders if each had
    filled, sum price of fills]."""
    side, (lo, hi), (a, b), cancel, queue, guard = rule
    W = len(pr['bid'])
    if side == 'yes':
        price = pr['bid']
        size_arr = pr['bsz']
        sgn = 1.0
    else:
        price = 1.0 - pr['ask']
        size_arr = pr['asz']
        sgn = -1.0
    ok = np.isfinite(price) & (price >= lo) & (price < hi) & (pr['bid'] < pr['ask'])
    if queue == 'pess':
        ok &= size_arr > 0
    if guard is not None:
        zg = pr['z'].get(('idx', guard[0]))
        if zg is None:
            return np.zeros(6)
        with np.errstate(invalid='ignore'):
            ok &= ~(sgn * zg <= -guard[1])                       # NaN passes: no information is no reason to stay away
    ok_r = ok[:, a:b]
    has = ok_r.any(1)
    out = np.zeros(6)
    for w in np.flatnonzero(has):
        s0 = a + int(ok_r[w].argmax())
        p = float(price[w, s0])
        res = pr['result'][w]
        if not np.isfinite(res):
            continue
        win = res if side == 'yes' else 1.0 - res
        n = max(math.floor(STAKE / p), 1)
        tc = cancel * 1000
        if guard is not None:
            adverse = np.flatnonzero(sgn * pr['z'][('idx', guard[0])][w, s0 + 1:cancel] <= -guard[1])
            if len(adverse):
                tc = min(tc, (s0 + 1 + int(adverse[0])) * 1000)
        want = -1 if side == 'yes' else 1
        cache = pr.setdefault('_lv', {})
        if (w, want) not in cache:
            ms, tp, tcnt, ts = pr['trades'][w]
            cache[(w, want)] = Levels(ms, tp, tcnt, ts, want)
        lv = cache[(w, want)]
        if side == 'yes':
            ft = fill_time(lv, p, True, (s0 + 1) * 1000, tc, 0.0 if queue == 'opt' else float(size_arr[w, s0]), n)
        else:
            ft = fill_time(lv, round(1.0 - p, 3), False, (s0 + 1) * 1000, tc, 0.0 if queue == 'opt' else float(size_arr[w, s0]), n)
        out[0] += 1
        out[4] += win - p
        if ft is not None:
            fee = float(KF.maker_fee(n, p, multiplier=1.0)) / n               # the stress arm: the full rate (the real maker fee on these series is 0)
            out[1] += 1; out[2] += win - p; out[3] += win - p - fee; out[5] += p
    return out


def rules() -> list:
    return [(sd, bk, pl, cn, q, g) for sd in SIDES for bk in BUCKETS for pl in PLACE for cn in CANCEL for q in QUEUE for g in GUARDS]


def run_day(pr: dict, rule_list: list) -> dict:
    return {r: simulate(pr, r) for r in rule_list}


def _ratio(days: dict, ni: int, di: int, sel: set) -> tuple:
    ds = [d for d in days if d in sel and days[d][di] > 0]
    D = sum(days[d][di] for d in ds)
    if D == 0:
        return None, None, 0, 0, 0
    mean = sum(days[d][ni] for d in ds) / D
    pos = sum(1 for d in ds if days[d][ni] > 0)
    if len(ds) < 2:
        return mean, None, D, len(ds), pos
    res = np.array([days[d][ni] - mean * days[d][di] for d in ds])
    return mean, math.sqrt(float((res * res).sum()) * len(ds) / (len(ds) - 1)) / D, D, len(ds), pos


def _c(x):
    return None if x is None else round(100 * x, 3)


def describe(days: dict, build: set, check: set) -> dict:
    out = {}
    for tag, sel in (('build', build), ('check', check)):
        m, se, f, nd, pos = _ratio(days, 2, 1, sel)               # net per filled contract
        ms, _, _, _, _ = _ratio(days, 3, 1, sel)                  # same under the stress fee
        mo, _, o, _, _ = _ratio(days, 4, 0, sel)                  # what the orders would have earned if every one had filled
        fr = None if o == 0 else f / o
        out[tag] = {'orders': int(o), 'fills': int(f), 'fill_rate': None if fr is None else round(fr, 3), 'net_per_fill_c': _c(m),
                    'lo_c': None if m is None or se is None else _c(m - Z95 * se), 'hi_c': None if m is None or se is None else _c(m + Z95 * se),
                    'stress_fee_c': _c(ms), 'if_all_filled_c': _c(mo), 'days': nd, 'pos_days': pos,
                    'per_order_c': None if m is None or fr is None else _c(m * fr)}
    return out


def judge(acc: dict, build: set, check: set, top: int = 8) -> dict:
    res = {}
    for q in QUEUE:
        rows = []
        for r, days in acc.items():
            if r[4] != q:
                continue
            m, se, f, nd, pos = _ratio(days, 2, 1, build)
            if m is not None and f >= MIN_BUILD_FILLS:
                rows.append((m, r))
        rows.sort(key=lambda x: -x[0])
        chosen = [{'rule': dict(zip(('side', 'bucket', 'place', 'cancel', 'queue', 'guard'), r)), **describe(acc[r], build, check)} for _, r in rows[:top]]
        allc = [_ratio(days, 2, 1, check) for r, days in acc.items() if r[4] == q]
        good = [m for m, _, f, _, _ in allc if m is not None and f >= 100]
        res[q] = {'rules_with_build_fills': len(rows), 'best_on_build': chosen,
                  'all_rules_check': {'rules': len(good), 'mean_net_per_fill_c': _c(float(np.mean(good))) if good else None, 'positive': int(sum(1 for m in good if m > 0))}}
    return res


def crossval(acc: dict, n_days: int, k: int = 4, top: int = 5) -> dict:
    """Every way of holding out k of the n recorded days: the rule is picked on the other n-k days (best net per fill with at least MIN_BUILD_FILLS fills) and judged
    on the k held-out days; compared with the mean of all rules on those same days. Recorded days only, and the held-out days never take part in the pick."""
    res = {}
    for q in QUEUE:
        rq = [r for r in acc if r[4] == q]
        picks, chk, bld, base = [], [], [], []
        for held in itertools.combinations(range(n_days), k):
            check = set(held)
            build = set(range(n_days)) - check
            best = None
            for r in rq:
                m, _, f, _, _ = _ratio(acc[r], 2, 1, build)
                if m is not None and f >= MIN_BUILD_FILLS and (best is None or m > best[0]):
                    best = (m, r)
            if best is None:
                continue
            mc, _, fc, _, _ = _ratio(acc[best[1]], 2, 1, check)
            allc = [x[0] for x in (_ratio(acc[r], 2, 1, check) for r in rq) if x[0] is not None and x[2] >= 100]
            if mc is None or fc < 50 or not allc:
                continue
            picks.append(best[1]); chk.append(mc); bld.append(best[0]); base.append(float(np.mean(allc)))
        if not chk:
            res[q] = {'splits': 0}
            continue
        chk, bld, base = np.array(chk), np.array(bld), np.array(base)
        common = Counter(picks).most_common(top)
        rows = []
        for r, cnt in common:
            days = [None if acc[r].get(d) is None or acc[r][d][1] == 0 else _c(acc[r][d][2] / acc[r][d][1]) for d in range(n_days)]
            fills = [0 if acc[r].get(d) is None else int(acc[r][d][1]) for d in range(n_days)]
            rows.append({'rule': dict(zip(('side', 'bucket', 'place', 'cancel', 'queue', 'guard'), r)), 'picked_in_splits': cnt, 'net_per_fill_c_by_day': days, 'fills_by_day': fills})
        res[q] = {'splits': len(chk), 'held_out_days': k,
                  'pick_on_held_out_c': {'mean': _c(float(chk.mean())), 'median': _c(float(np.median(chk))), 'p10': _c(float(np.quantile(chk, 0.1))),
                                         'p90': _c(float(np.quantile(chk, 0.9))), 'share_positive': round(float((chk > 0).mean()), 3)},
                  'pick_on_picking_days_c': _c(float(bld.mean())), 'all_rules_on_held_out_c': _c(float(base.mean())),
                  'pick_minus_all_rules_c': {'mean': _c(float((chk - base).mean())), 'share_positive': round(float((chk > base).mean()), 3)},
                  'most_picked': rows}
    return res


def run(grids_dir: str, build_last: str, out_dir: str, assets=('BTC', 'ETH', 'SOL', 'XRP'), cv: bool = False) -> dict:
    rl = rules()
    acc = {r: {} for r in rl}
    names = []
    for p in sorted(glob.glob(os.path.join(grids_dir, 'grid-*.npz'))):
        day = os.path.basename(p)[5:15]
        names.append(day)
        di = len(names) - 1
        day_ms = int(dt.datetime.strptime(day, '%Y-%m-%d').replace(tzinfo=dt.timezone.utc).timestamp() * 1000)
        z = np.load(p, allow_pickle=False)
        if f'{assets[0]}__tr_w' not in z.files:
            raise SystemExit(f'{p} has no trades: run the grid reducer again')
        have = {k.split('__')[0] for k in z.files}
        for c in assets:
            if c not in have:
                continue
            pr = prep(z, c, day_ms)
            if pr is None:
                continue
            for r, v in run_day(pr, rl).items():
                t = acc[r].setdefault(di, np.zeros(6))
                t += v
    build = {i for i, n in enumerate(names) if n <= build_last}
    check = {i for i, n in enumerate(names) if n > build_last}
    res = {'days': names, 'build_days': len(build), 'check_days': len(check), 'rules': len(rl), 'maker': judge(acc, build, check)}
    if cv:
        res['crossval'] = crossval(acc, len(names))
    os.makedirs(out_dir, exist_ok=True)
    json.dump(res, open(os.path.join(out_dir, 'maker.json'), 'w'), indent=1, sort_keys=True, default=float)
    return res


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--grids', required=True)
    ap.add_argument('--build-last', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--cv', action='store_true', help='also hold out every 4 of the recorded days in turn (pick on the rest, judge on those)')
    a = ap.parse_args()
    r = run(a.grids, a.build_last, a.out, cv=a.cv)
    cvr = r.pop('crossval', None)
    print('HEATLOOP mdmaker ' + json.dumps(r, sort_keys=True, default=float)[:14000], flush=True)
    if cvr is not None:
        print('HEATLOOP mdmaker-cv ' + json.dumps(cvr, sort_keys=True, default=float)[:14000], flush=True)
