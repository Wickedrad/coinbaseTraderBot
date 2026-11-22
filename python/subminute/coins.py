"""Round 4a (Nov 22 2026, recorded days only): the two round-2 questions asked coin by coin, with SOL and XRP on their own.

Rounds 2 and 3 pooled BTC, ETH, SOL and XRP. Here every coin gets its own answer on the same ten recorded full-depth days (Nov 11 to 20):
  1. Is the book late by seconds? The information R^2 and the 2,260 follow/flip trade cells, per coin (the thin SOL and XRP books are the likelier place for a lag).
  2. Do resting buys (the 360 maker rules of maker.py) earn? Per coin: the mean of all rules with no selection, the rule picked on the build days against the check
     days, and what the orders would have earned had every one filled (the premium before fill selection).
  3. Does a pick travel to a market it never saw? Pick on three coins, judge on the fourth (every way of holding out 4 of the 10 days at the same time, so the pick
     sees neither the coin nor the days), and BTC+ETH against SOL+XRP both ways. Days are shared across coins, so a coin that is held out is a different market but
     the same weather; read it as a check on the market, not on the days.
Nothing is ordered. Only aggregates are printed.
"""
import argparse
import datetime as dt
import glob
import itertools
import json
import os
from collections import Counter

import numpy as np

from subminute import lag as LG
from subminute import maker as MK

COINS = ('BTC', 'ETH', 'SOL', 'XRP')
MIN_PICK_FILLS = MK.MIN_BUILD_FILLS
MIN_JUDGE_FILLS = 30
KEYS = ('side', 'bucket', 'place', 'cancel', 'queue', 'guard')


def load(grids_dir: str, coins=COINS):
    """(day names, [{coin: maker.prep}]) for every grid-DAY.npz, oldest first. The maker prep carries every key the lag code reads."""
    names, preps = [], []
    for p in sorted(glob.glob(os.path.join(grids_dir, 'grid-*.npz'))):
        day = os.path.basename(p)[5:15]
        day_ms = int(dt.datetime.strptime(day, '%Y-%m-%d').replace(tzinfo=dt.timezone.utc).timestamp() * 1000)
        z = np.load(p, allow_pickle=False)
        have = {k.split('__')[0] for k in z.files}
        if any(f'{c}__tr_w' not in z.files for c in coins if c in have):
            raise SystemExit(f'{p} has no trades: run the grid reducer again')
        names.append(day)
        preps.append({c: MK.prep(z, c, day_ms) for c in coins if c in have})
    return names, preps


def lag_coin(preps: list, build: set, check: set, coin: str) -> dict:
    pl = [(i, ps[coin]) for i, ps in enumerate(preps) if ps.get(coin) is not None]
    if not pl:
        return {'windows': 0}
    info = LG.information(pl, build, check, 1)
    back = LG.information(pl, build, check, 1, back=True)
    r2 = sorted(((v['r2_check_1e4'], k) for k, v in info.items() if v['r2_check_1e4'] is not None), reverse=True)
    judged = LG.judge(LG.sweep(pl), build, check, top=1)
    out = {'windows': int(sum(len(pr['bid']) for _, pr in pl)), 'days': len(pl),
           'information_r2_check_1e4': {'best': r2[:3], 'median': None if not r2 else r2[len(r2) // 2][0], 'cells': len(r2)},
           'alignment_r2_1e4': {k: v['r2_check_1e4'] for k, v in back.items() if k in ('idx_L1', 'idx_L5', 'idx_L30', 'spot_L5', 'perp_mid_L5')}}
    for label in ('sold', 'held'):
        j = judged[label]
        b = j['best_on_build'][0] if j['best_on_build'] else None
        out[label] = {'all_cells_check': j['all_cells_check'],
                      'best_on_build': None if b is None else {'cell': b['cell'], 'follow_build': b['follow']['build'], 'follow_check': b['follow']['check'],
                                                               'flip_check': b['flip']['check']}}
    return out


def maker_acc(preps: list, coins, rl: list) -> dict:
    """{coin: {rule: {day index: [orders, fills, net, net under the stress fee, net if all filled, price]}}}."""
    acc = {c: {r: {} for r in rl} for c in coins}
    for di, ps in enumerate(preps):
        for c in coins:
            pr = ps.get(c)
            if pr is None:
                continue
            for r, v in MK.run_day(pr, rl).items():
                t = acc[c][r].setdefault(di, np.zeros(6))
                t += v
            pr.pop('_lv', None)                                   # the per-window level caches are only worth keeping while one day's rules run
    return acc


def combine(accs: list) -> dict:
    out = {}
    for a in accs:
        for r, days in a.items():
            for d, v in days.items():
                t = out.setdefault(r, {}).setdefault(d, np.zeros(6))
                t += v
    return out


def floor(acc: dict, sel: set, queue: str, min_fills: int = 100) -> dict:
    """No selection at all: the mean over every rule with enough fills, of the net per filled contract and of the net had every order filled."""
    net, gross = [], []
    for r, days in acc.items():
        if r[4] != queue:
            continue
        m, _, f, _, _ = MK._ratio(days, 2, 1, sel)
        mo, _, o, _, _ = MK._ratio(days, 4, 0, sel)
        if m is not None and f >= min_fills and mo is not None:
            net.append(m)
            gross.append(mo)
    if not net:
        return {'rules': 0}
    return {'rules': len(net), 'net_per_fill_c': MK._c(float(np.mean(net))), 'if_all_filled_c': MK._c(float(np.mean(gross))), 'rules_above_zero': int(sum(1 for m in net if m > 0))}


def day_splits(n: int, k: int = 4) -> list:
    return [(set(range(n)) - set(h), set(h)) for h in itertools.combinations(range(n), k)]


def transfer(acc_pick: dict, acc_judge: dict, splits: list, queue: str, min_pick: int = MIN_PICK_FILLS, min_judge: int = MIN_JUDGE_FILLS) -> dict:
    """For every (build days, judged days) split: pick the rule with the best net per fill on `acc_pick` over the build days (at least min_pick fills), then read it on
    `acc_judge` over the judged days; compared with the mean of all rules on the same judged days (those with at least min_judge fills)."""
    rq = [r for r in acc_pick if r[4] == queue]
    picks, got, bld, base = [], [], [], []
    for build, check in splits:
        best = None
        for r in rq:
            m, _, f, _, _ = MK._ratio(acc_pick[r], 2, 1, build)
            if m is not None and f >= min_pick and (best is None or m > best[0]):
                best = (m, r)
        if best is None:
            continue
        mc, _, fc, _, _ = MK._ratio(acc_judge.get(best[1], {}), 2, 1, check)
        allc = [x[0] for x in (MK._ratio(acc_judge.get(r, {}), 2, 1, check) for r in rq) if x[0] is not None and x[2] >= min_judge]
        if mc is None or fc < min_judge or not allc:
            continue
        picks.append(best[1]); got.append(mc); bld.append(best[0]); base.append(float(np.mean(allc)))
    out = {'splits_total': len(splits), 'splits_used': len(got)}
    if not got:
        return out
    g, b, a = np.array(got), np.array(bld), np.array(base)
    out.update({'pick_on_picking_c': MK._c(float(b.mean())),
                'pick_on_judged_c': {'mean': MK._c(float(g.mean())), 'median': MK._c(float(np.median(g))), 'p10': MK._c(float(np.quantile(g, 0.1))),
                                     'p90': MK._c(float(np.quantile(g, 0.9))), 'share_positive': round(float((g > 0).mean()), 3)},
                'all_rules_on_judged_c': MK._c(float(a.mean())),
                'pick_minus_all_rules_c': {'mean': MK._c(float((g - a).mean())), 'share_positive': round(float((g > a).mean()), 3)},
                'most_picked': [{'rule': dict(zip(KEYS, r)), 'splits': n} for r, n in Counter(picks).most_common(2)]})
    return out


def digest(r: dict) -> dict:
    """The few numbers worth reading from a full result, per coin and per transfer (the full tables are in coins.json)."""
    out = {'days': len(r['days']), 'build_days': r['build_days'], 'check_days': r['check_days'], 'lag': {}, 'maker': {}, 'transfer': {}}
    for c, v in r['lag'].items():
        if not v.get('windows'):
            out['lag'][c] = {'windows': 0}
            continue
        d = {'windows': v['windows'], 'r2_check_1e4_best': v['information_r2_check_1e4']['best'][:1], 'r2_check_1e4_median': v['information_r2_check_1e4']['median'],
             'alignment_r2_1e4': v['alignment_r2_1e4']}
        for label in ('sold', 'held'):
            a = v[label]['all_cells_check']
            b = v[label]['best_on_build']
            d[label] = {'cells': a['cells'], 'follow_mean_c': a['follow_mean_c'], 'flip_mean_c': a['flip_mean_c'], 'follow_positive': a['follow_positive'],
                        'best_build_c': None if b is None else b['follow_build']['net_c'], 'best_check_c': None if b is None else b['follow_check']['net_c'],
                        'best_check_ci': None if b is None else [b['follow_check']['lo_c'], b['follow_check']['hi_c']], 'best_cell': None if b is None else b['cell']}
        out['lag'][c] = d
    for c, v in r['maker'].items():
        out['maker'][c] = {}
        for q, m in v.items():
            b = m['best_on_build'][0] if m['best_on_build'] else None
            out['maker'][c][q] = {'no_selection_all_days': m['all_days_no_selection'], 'no_selection_check': m['check_days_no_selection'],
                                  'best_build_c': None if b is None else b['build']['net_per_fill_c'], 'best_check_c': None if b is None else b['check']['net_per_fill_c'],
                                  'best_check_ci': None if b is None else [b['check']['lo_c'], b['check']['hi_c']], 'best_fills_check': None if b is None else b['check']['fills'],
                                  'best_rule': None if b is None else b['rule']}
    for q, t in r['transfer'].items():
        out['transfer'][q] = {k: {'used': v['splits_used'], 'pick_judged_c': v.get('pick_on_judged_c', {}).get('mean'), 'share_positive': v.get('pick_on_judged_c', {}).get('share_positive'),
                                  'all_rules_c': v.get('all_rules_on_judged_c'), 'pick_picking_c': v.get('pick_on_picking_c')} for k, v in t.items()}
    return out


def run(grids_dir: str, build_last: str, out_dir: str, coins=COINS) -> dict:
    names, preps = load(grids_dir, coins)
    n = len(names)
    build = {i for i, d in enumerate(names) if d <= build_last}
    check = {i for i, d in enumerate(names) if d > build_last}
    allset = set(range(n))
    res = {'days': names, 'build_days': len(build), 'check_days': len(check), 'lag': {}, 'maker': {}, 'transfer': {}}
    for c in coins:
        res['lag'][c] = lag_coin(preps, build, check, c)
    rl = MK.rules()
    acc = maker_acc(preps, coins, rl)
    for c in coins:
        j = MK.judge(acc[c], build, check, top=2)
        res['maker'][c] = {q: {'all_days_no_selection': floor(acc[c], allset, q), 'check_days_no_selection': floor(acc[c], check, q),
                               'rules_with_build_fills': j[q]['rules_with_build_fills'], 'best_on_build': j[q]['best_on_build'],
                               'all_rules_check': j[q]['all_rules_check']} for q in MK.QUEUE}
    ds = day_splits(n)
    for q in MK.QUEUE:
        t = {}
        for h in coins:
            others = combine([acc[c] for c in coins if c != h])
            t[f'leave_out_{h}'] = transfer(others, acc[h], ds, q)
        big, small = combine([acc[c] for c in ('BTC', 'ETH') if c in acc]), combine([acc[c] for c in ('SOL', 'XRP') if c in acc])
        t['BTC+ETH_to_SOL+XRP_all_days'] = transfer(big, small, [(allset, allset)], q)
        t['SOL+XRP_to_BTC+ETH_all_days'] = transfer(small, big, [(allset, allset)], q, min_pick=100)
        t['BTC+ETH_to_SOL+XRP_held_out_days'] = transfer(big, small, ds, q)
        res['transfer'][q] = t
    os.makedirs(out_dir, exist_ok=True)
    json.dump(res, open(os.path.join(out_dir, 'coins.json'), 'w'), indent=1, sort_keys=True, default=float)
    return res


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--grids', required=True)
    ap.add_argument('--build-last', required=True)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    r = run(a.grids, a.build_last, a.out)
    print('HEATLOOP mdcoin-digest ' + json.dumps(digest(r), sort_keys=True, default=float)[:14000], flush=True)
