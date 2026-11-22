"""Round 5a (Nov 22 2026, recorded days only): is the hourly ladder ever arbitrageable inside itself?

KXBTCD / KXETHD / KXSOLD / KXXRPD sell "at or above K at the top of the hour": the YES price of strike K_i must never sit below the YES price of a higher strike K_j.
When a lower strike's best ask is below a higher strike's best bid (bid_j > ask_i, i < j), buying YES_i and NO_j (one of them always pays, both pay when
K_i <= S < K_j) costs 1 - (bid_j - ask_i) and returns at least 1: a locked gain before fees. Both legs are takers: the exact taker fee of allpairs.fees (0.07 C P (1 - P),
rounded up, then onto the cent grid).

Questions, per coin, on the 1-second hourly grids of the recorded full-depth days (aggregates only, nothing is ordered):
  1. how often is the ladder crossed at all (seconds, share of the seconds with two strikes quoted), and by how many cents?
  2. what is left after the two taker fees at the contracts the quotes show (and a $10 stake)?
  3. does it survive one second of latency (trade at the quotes of the second after the crossing is first seen), and the last minute before the close?
  4. dollars an hour if every episode were taken once, with a day-cluster interval.
A book of a market that has not changed keeps its last state, so a crossing is a real resting-quote state, not a stale print; the one-second latency arm is the
guard against a crossing that is only the two books being updated a few milliseconds apart.
"""
import argparse
import datetime as dt
import glob
import json
import math
import os

import numpy as np

from allpairs import fees as KF

STAKE = 10.0
BUCKETS = (('lt60', 0, 60), ('60_600', 60, 600), ('ge600', 600, 3601))      # seconds before the close
GAP_BINS = (0.0, 0.01, 0.02, 0.03, 0.05, 0.10, 1.01)                         # crossing size in dollars per contract


def _runs(mask):
    """Start indices of the runs of True in a 1-d bool array."""
    m = np.asarray(mask, bool)
    return np.flatnonzero(m & ~np.concatenate(([False], m[:-1])))


def scan_hour(bid, ask, bsz, asz, stake: float = STAKE) -> dict:
    """One hour of one coin's ladder: rows are the strikes in ascending order, columns the seconds. Returns arrays and counts for the crossed pairs.

    best_gap[s]   largest bid_j - ask_i over pairs i < j with both quotes standing (>= 1 contract), NaN where no pair has two quotes
    pair          (i, j) of that best pair per second
    net[s]        dollars of the best crossed pair at that second's quotes after both taker fees, for `n[s]` contracts (stake-capped, size-capped); NaN if not crossed
    """
    m, W = bid.shape
    okb = np.isfinite(bid) & (bsz >= 1)
    oka = np.isfinite(ask) & (asz >= 1)
    best = np.full(W, -np.inf)
    bi = np.zeros(W, np.int16)
    bj = np.zeros(W, np.int16)
    for i in range(m - 1):
        for j in range(i + 1, m):
            both = oka[i] & okb[j]
            gap = np.where(both, bid[j] - ask[i], -np.inf)
            better = gap > best
            best = np.where(better, gap, best)
            bi = np.where(better, i, bi)
            bj = np.where(better, j, bj)
    two = np.isfinite(best)
    crossed = two & (best > 1e-9)
    ar = np.arange(W)
    pa, pb = ask[bi, ar], bid[bj, ar]
    size = np.where(two, np.minimum(asz[bi, ar], bsz[bj, ar]), 0.0)
    cost = np.where(two, pa + (1.0 - pb), np.nan)
    with np.errstate(invalid='ignore', divide='ignore'):
        n = np.where(crossed, np.maximum(np.minimum(size, np.floor(stake / cost)), 1.0), 0.0)
    fee = np.where(crossed, KF.taker_fee(n, np.where(crossed, pa, 0.5)) + KF.taker_fee(n, np.where(crossed, 1.0 - pb, 0.5)), 0.0)
    net = np.where(crossed, n * best - fee, np.nan)
    return {'best_gap': np.where(two, best, np.nan), 'two': two, 'crossed': crossed, 'size': size, 'n': n, 'fee': fee, 'net': net, 'pair': (bi, bj)}


def _gap_hist(gaps):
    """Seconds by the size of the best crossing, cents per contract: (0, 1], (1, 2], (2, 3], (3, 5], (5, 10], (10, 100]."""
    edges = (1e-9,) + tuple(x + 1e-9 for x in GAP_BINS[1:])
    names = [f'{int(round(lo * 100))}_{int(round(hi * 100))}c' for lo, hi in zip(GAP_BINS[:-1], GAP_BINS[1:])]
    return {nm: int(((gaps > lo) & (gaps <= hi)).sum()) for nm, lo, hi in zip(names, edges[:-1], edges[1:])}


def day_stats(z, coin: str, day_ms: int, stake: float = STAKE) -> dict:
    """One recorded day of one coin: the counts above, pooled over its hourly ladders."""
    tickers = z[f'{coin}__tickers']
    strike = np.asarray(z[f'{coin}__strike'], float)
    open_ms = np.asarray(z[f'{coin}__open_ms'], np.int64)
    bid, ask = np.asarray(z[f'{coin}__bid'], float), np.asarray(z[f'{coin}__ask'], float)
    bsz, asz = np.asarray(z[f'{coin}__bsz'], float), np.asarray(z[f'{coin}__asz'], float)
    W = bid.shape[1]
    tot = {'hours': 0, 'ladder_hours_ge2': 0, 'two_secs': 0, 'same_market_crossed_secs': 0, 'crossed_secs': 0, 'crossed_gross': 0.0, 'crossed_sizes': [],
           'net_pos_secs': 0, 'episodes': 0, 'episode_net': 0.0, 'episode_net_lat1': 0.0, 'episodes_pos_lat1': 0, 'gaps': [], 'by_bucket': {b[0]: {'two': 0, 'crossed': 0, 'net_pos': 0} for b in BUCKETS},
           'best_net': 0.0, 'persist_secs': 0}
    for o in np.unique(open_ms):
        rows = np.flatnonzero(open_ms == o)
        rows = rows[np.isfinite(strike[rows])]
        if len(rows) < 2:
            tot['hours'] += 1
            continue
        rows = rows[np.argsort(strike[rows], kind='stable')]
        # two markets with the same strike are one market recorded twice: keep the first
        _, first = np.unique(strike[rows], return_index=True)
        rows = rows[np.sort(first)]
        if len(rows) < 2:
            tot['hours'] += 1
            continue
        b, a, bs, as_ = bid[rows], ask[rows], bsz[rows], asz[rows]
        tot['hours'] += 1
        tot['ladder_hours_ge2'] += 1
        tot['same_market_crossed_secs'] += int((np.isfinite(b) & np.isfinite(a) & (b >= a - 1e-9) & (bs >= 1) & (as_ >= 1)).sum())
        r = scan_hour(b, a, bs, as_, stake)
        tot['two_secs'] += int(r['two'].sum())
        cr = r['crossed']
        tot['crossed_secs'] += int(cr.sum())
        if cr.any():
            tot['gaps'].extend(r['best_gap'][cr].tolist())
            tot['crossed_sizes'].extend(r['size'][cr].tolist())
            tot['crossed_gross'] += float((r['n'][cr] * r['best_gap'][cr]).sum())
        pos = cr & (r['net'] > 0)
        tot['net_pos_secs'] += int(pos.sum())
        left = np.arange(W)[::-1]            # seconds before the close of the window of 3,600 s
        for name, lo, hi in BUCKETS:
            sel = (left >= lo) & (left < hi)
            tot['by_bucket'][name]['two'] += int((r['two'] & sel).sum())
            tot['by_bucket'][name]['crossed'] += int((cr & sel).sum())
            tot['by_bucket'][name]['net_pos'] += int((pos & sel).sum())
        # episodes: runs of crossed seconds; take each once at its first second (no latency) or at the quotes one second later (latency 1, the same pair or any)
        for s in _runs(cr):
            tot['episodes'] += 1
            tot['episode_net'] += float(r['net'][s])
            s1 = s + 1
            if s1 < W and cr[s1]:
                tot['persist_secs'] += 1
                tot['episode_net_lat1'] += float(r['net'][s1])
                tot['episodes_pos_lat1'] += int(r['net'][s1] > 0)
    return tot


def load_days(grids_dir: str):
    paths = sorted(glob.glob(os.path.join(grids_dir, 'grid-*.npz'))) or sorted(glob.glob(os.path.join(grids_dir, 'hgrid-*.npz')))
    for p in paths:
        base = os.path.basename(p)
        day = base.split('-', 1)[1][:10]
        yield day, int(dt.datetime.strptime(day, '%Y-%m-%d').replace(tzinfo=dt.timezone.utc).timestamp() * 1000), np.load(p, allow_pickle=False)


def _ci(xs):
    xs = np.asarray([x for x in xs if x is not None and np.isfinite(x)], float)
    if len(xs) < 2:
        return None
    m = float(xs.mean())
    se = float(xs.std(ddof=1) / math.sqrt(len(xs)))
    return {'mean': m, 'lo': m - 1.96 * se, 'hi': m + 1.96 * se, 'days': int(len(xs))}


def run(grids_dir: str, out_dir: str, coins=('BTC', 'ETH', 'SOL', 'XRP'), stake: float = STAKE) -> dict:
    per = {c: {} for c in coins}
    for day, day_ms, z in load_days(grids_dir):
        have = {k.split('__')[0] for k in z.files}
        for c in coins:
            if c in have:
                per[c][day] = day_stats(z, c, day_ms, stake)
    res = {'stake': stake, 'coins': {}}
    for c in coins:
        days = per[c]
        if not days:
            continue
        tot = lambda k: sum(d[k] for d in days.values())
        gaps = np.array([g for d in days.values() for g in d['gaps']], float)
        sizes = np.array([g for d in days.values() for g in d['crossed_sizes']], float)
        hours_rec = 24.0 * len(days)
        entry = {'days': sorted(days), 'hours_with_a_ladder': tot('hours'), 'ladders_with_two_strikes': tot('ladder_hours_ge2'), 'two_quote_seconds': tot('two_secs'),
                 'same_market_crossed_seconds': tot('same_market_crossed_secs'), 'crossed_seconds': tot('crossed_secs'),
                 'crossed_share_of_two_quote_seconds': (tot('crossed_secs') / tot('two_secs')) if tot('two_secs') else None,
                 'gap_hist_seconds': _gap_hist(gaps) if len(gaps) else {}, 'gap_median_c': float(np.median(gaps) * 100) if len(gaps) else None,
                 'gap_max_c': float(gaps.max() * 100) if len(gaps) else None, 'size_median_contracts': float(np.median(sizes)) if len(sizes) else None,
                 'gross_locked_dollars': tot('crossed_gross'), 'seconds_net_positive_after_taker_fees': tot('net_pos_secs'),
                 'episodes': tot('episodes'), 'episodes_with_a_next_second': tot('persist_secs'), 'episodes_positive_after_one_second': tot('episodes_pos_lat1'),
                 'by_close_bucket': {b[0]: {k: sum(d['by_bucket'][b[0]][k] for d in days.values()) for k in ('two', 'crossed', 'net_pos')} for b in BUCKETS},
                 'episode_net_dollars_no_latency': tot('episode_net'), 'episode_net_dollars_one_second_latency': tot('episode_net_lat1'),
                 'dollars_per_hour_no_latency': tot('episode_net') / hours_rec, 'dollars_per_hour_one_second_latency': tot('episode_net_lat1') / hours_rec,
                 'day_net_no_latency': _ci([d['episode_net'] for d in days.values()]), 'day_net_one_second_latency': _ci([d['episode_net_lat1'] for d in days.values()]),
                 'by_day_crossed_seconds': {k: d['crossed_secs'] for k, d in sorted(days.items())}}
        res['coins'][c] = entry
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, 'ladder_arb.json'), 'w') as f:
        json.dump(res, f, indent=1, sort_keys=True, default=float)
    return res


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--grids', required=True, help='the hourly grid-DAY.npz files (grid.py --hourly)')
    ap.add_argument('--out', required=True)
    ap.add_argument('--stake', type=float, default=STAKE)
    a = ap.parse_args()
    r = run(a.grids, a.out, stake=a.stake)
    print('HEATLOOP ladarb-digest ' + json.dumps(r, sort_keys=True, default=float)[:24000], flush=True)
