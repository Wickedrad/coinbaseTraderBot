#!/usr/bin/env python3
"""Tennis TA rulebook trial: the report job (pre-registration /mnt/project-files/tennis-ta/preregistration.md, Amendment 1).

Reads the shard outputs of research/tennisTaSweep.ts run (gzip JSON), keeps one pool's universe (every owned match of the
pool with a tape: a match the config did not trade counts 0), and scores every cell = config x arm x series x phase x
price bucket of the entry (an "all" level on each axis). Realized net after fees is the only score.

  bootstrap   stationary bootstrap over the time-ordered tournament-week units (A2: blocks are whole units, mean block
              length --block units, B = --boot), every CI and p-value; mean per match = sum / matches of the resample
  screen      BH at q = 0.10 over every F1 cell (first screen only), then the section 6 conditions: >= 100 entries on >= 30
              match-days, mean > 0, >= 60% of months with 10+ entries positive, the F2 arm net positive, zero breaches
  placebo     per-unit paired difference against the config's coin-flip arm, same bootstrap
  ONC         N_eff = clusters of the per-match P&L correlation (distance sqrt((1 - rho) / 2)) over the F1 cells with
              >= --onc-min entries (k-means base clustering scored by silhouette t, one refinement pass)
  SPA/StepM   Hansen SPA (consistent) and Romano-Wolf StepM over the ONC medoids + each cluster's best cell + production
  DSR         deflated Sharpe at N_eff on per-match Sharpe with the per-match skew and kurtosis
  PBO         CSCV over the months for the stage's config selection (the 'all' cells)
  losers      loser tables (series, phase, leg, signal combination, price bucket, exit) for production and the top configs
  registry    one row per scored cell (N_raw) in the meta plan's schema, for registry/tennis-ta-<run>.jsonl

Usage: tennis_ta_report.py --shards DIR --pool disc --run RUN_ID --out DIR [--boot 2000] [--block 1] [--seed 20261105]
"""
import argparse
import gzip
import hashlib
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta

import numpy as np

PHASES = ['pre', 'e20', 'p1', 'p2', 'p3']
BUCKETS = ['8-15', '15-25', '75-85', '85-92', 'other']
EULER = 0.5772156649015329


def bucket_of(px):
    if 0.08 - 1e-9 <= px < 0.15 - 1e-9:
        return '8-15'
    if 0.15 - 1e-9 <= px <= 0.25 + 1e-9:
        return '15-25'
    if 0.75 - 1e-9 <= px < 0.85 - 1e-9:
        return '75-85'
    if 0.85 - 1e-9 <= px <= 0.92 + 1e-9:
        return '85-92'
    return 'other'


def tour(series):
    return {'KXATPMATCH': 'ATP', 'KXWTAMATCH': 'WTA'}.get(series, series)


def eastern(ts_ms):
    """America/New_York without tzdata: EDT from the second Sunday of March 07:00 UTC to the first Sunday of November 06:00 UTC."""
    t = datetime.fromtimestamp(ts_ms / 1000, timezone.utc)
    y = t.year
    mar = datetime(y, 3, 8, 7, tzinfo=timezone.utc)
    mar += timedelta(days=(6 - mar.weekday()) % 7)
    nov = datetime(y, 11, 1, 6, tzinfo=timezone.utc)
    nov += timedelta(days=(6 - nov.weekday()) % 7)
    dst = mar <= t < nov
    return (t - timedelta(hours=4 if dst else 5)), ('EDT' if dst else 'EST')


def norm_ppf(p):
    from scipy.stats import norm
    return float(norm.ppf(p))


def norm_cdf(x):
    from scipy.stats import norm
    return float(norm.cdf(x))


# ---------------------------------------------------------------------------------------------------------------------
# Loading

def load(shard_dir):
    files = sorted(f for f in os.listdir(shard_dir) if f.endswith('.json.gz'))
    if not files:
        sys.exit(f'no shard files in {shard_dir}')
    matches, runs, metas = [], {}, []
    for f in files:
        with gzip.open(os.path.join(shard_dir, f), 'rt') as fh:
            d = json.load(fh)
        metas.append(d['meta'])
        cols = d['meta']['episodeCols']
        off = len(matches)
        matches.extend(d['matchList'])
        for r in d['runs']:
            acc = runs.setdefault(r['id'], {'id': r['id'], 'overrides': r['overrides'], 'fill': r['fill'], 'placebo': r.get('placebo'), 'pnl': [], 'eps': [], 'days': []})
            if len(r['pnl']) != len(d['matchList']):
                sys.exit(f"{f}: {r['id']} has {len(r['pnl'])} match values for {len(d['matchList'])} matches")
            acc['pnl'].extend(r['pnl'])
            acc['days'].extend(r['days'])
            for e in r['episodes']:
                row = dict(zip(cols, e))
                row['m'] += off
                acc['eps'].append(row)
    return matches, runs, metas


# ---------------------------------------------------------------------------------------------------------------------
# Bootstrap over units

def stationary_weights(n_units, B, block, rng):
    """B x n_units counts: the stationary bootstrap (Politis-Romano) on the unit sequence, mean block length `block` units."""
    W = np.zeros((B, n_units), dtype=np.float64)
    p = 1.0 / max(block, 1.0)
    for b in range(B):
        i, filled = rng.integers(n_units), 0
        while filled < n_units:
            W[b, i] += 1
            filled += 1
            i = rng.integers(n_units) if rng.random() < p else (i + 1) % n_units
    return W


def bh(p, q):
    p = np.asarray(p)
    m = len(p)
    order = np.argsort(p)
    thresh = q * (np.arange(1, m + 1) / m)
    passed = p[order] <= thresh
    k = np.max(np.nonzero(passed)[0]) + 1 if passed.any() else 0
    rej = np.zeros(m, dtype=bool)
    rej[order[:k]] = True
    return rej


# ---------------------------------------------------------------------------------------------------------------------
# ONC (Lopez de Prado): base k-means clustering on the correlation-distance matrix scored by silhouette t, one refinement

def onc(corr, rng_seed, max_k=None, n_init=3):
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_samples
    n = corr.shape[0]
    if n < 3:
        return np.zeros(n, dtype=int)
    dist = np.sqrt(np.clip((1 - corr) / 2, 0, 1))
    max_k = max_k or min(50, n // 2)
    best, best_q = np.zeros(n, dtype=int), -np.inf
    for k in range(2, max(3, max_k + 1)):
        for s in range(n_init):
            km = KMeans(n_clusters=k, n_init=1, random_state=rng_seed + 97 * k + s).fit(dist)
            sil = silhouette_samples(dist, km.labels_)
            q = sil.mean() / (sil.std() + 1e-12)
            if q > best_q:
                best_q, best = q, km.labels_.copy()
    # Refinement: clusters whose silhouette t is below the mean are re-clustered once on their own.
    sil = silhouette_samples(dist, best) if len(set(best)) > 1 else np.zeros(n)
    labels = best.copy()
    next_id = labels.max() + 1
    qs = {c: sil[best == c].mean() / (sil[best == c].std() + 1e-12) for c in set(best)}
    mean_q = np.mean(list(qs.values()))
    for c, qc in qs.items():
        idx = np.nonzero(best == c)[0]
        if qc >= mean_q or len(idx) < 6:
            continue
        sub = onc(corr[np.ix_(idx, idx)], rng_seed + 1, min(10, len(idx) // 2), 1)
        for s in set(sub):
            if s == 0:
                continue
            labels[idx[sub == s]] = next_id
            next_id += 1
    _, labels = np.unique(labels, return_inverse=True)
    return labels


# ---------------------------------------------------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--shards', required=True)
    ap.add_argument('--pool', default='disc')
    ap.add_argument('--run', default='local')
    ap.add_argument('--out', required=True)
    ap.add_argument('--boot', type=int, default=2000)
    ap.add_argument('--block', type=float, default=1.0)
    ap.add_argument('--seed', type=int, default=20261105)
    ap.add_argument('--onc-min', type=int, default=100)
    ap.add_argument('--onc-cap', type=int, default=6000)
    ap.add_argument('--alpha', type=float, default=0.10)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    rng = np.random.default_rng(a.seed)

    matches, runs, metas = load(a.shards)
    meta = metas[0]
    keep = [i for i, m in enumerate(matches) if m['pool'] == a.pool and m['trades'] > 0]
    no_tape = sum(1 for m in matches if m['pool'] == a.pool and m['trades'] == 0)
    if not keep:
        sys.exit(f'no {a.pool} matches with a tape')
    keep.sort(key=lambda i: matches[i]['start'])
    remap = {old: new for new, old in enumerate(keep)}
    M = [matches[i] for i in keep]
    N = len(M)
    units = sorted({m['unit'] for m in M}, key=lambda u: min(x['start'] for x in M if x['unit'] == u))
    uidx = {u: i for i, u in enumerate(units)}
    m_unit = np.array([uidx[m['unit']] for m in M])
    days = sorted({m['day'] for m in M})
    didx = {d: i for i, d in enumerate(days)}
    m_day = np.array([didx[m['day']] for m in M])
    months = sorted({m['day'][:7] for m in M})
    moidx = {mo: i for i, mo in enumerate(months)}
    m_month = np.array([moidx[m['day'][:7]] for m in M])
    m_tour = np.array([tour(m['series']) for m in M])
    tours = sorted(set(m_tour))
    U = len(units)
    unit_n = {t: np.bincount(m_unit[m_tour == t], minlength=U).astype(float) for t in tours}
    unit_n['all'] = np.bincount(m_unit, minlength=U).astype(float)
    n_series = {t: int((m_tour == t).sum()) for t in tours}
    n_series['all'] = N
    t_first, t_last = M[0]['start'], max(m['close'] for m in M)
    # Wall-clock hours of the pool: the pool's units clipped to the data span (sealed and embargoed time left out).
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'models', 'tennis-ta', 'state', 'units.json')) as fh:
        unit_table = {u['id']: u for u in json.load(fh)}
    pool_hours = sum(max(0, min(unit_table[u]['end'], t_last) - max(unit_table[u]['start'], t_first)) for u in units) / 3.6e6
    live_hours = sum(max(0, m['close'] - m['start']) for m in M) / 3.6e6

    W = stationary_weights(U, a.boot, a.block, rng)

    # ---- cells
    cells = []          # summary rows
    unit_sums = []      # per cell, U
    vec_store = {}      # cell index -> per-match vector (F1 cells with enough entries, for ONC / SPA)
    hourly = []
    for rid, r in runs.items():
        o = r['overrides']
        # Measuring sticks (production without the loser cut, production without the pacer) are scored and logged but are
        # not hypotheses: they never enter the screen.
        stick = o.get('HARNESS_LOSER_CUT') in (False, 'false') or o.get('HARNESS_PACER') == 'off'
        arm = 'stick' if stick else 'coin' if r.get('placebo') == 'coin' else r['fill']
        base = rid.rsplit('|', 1)[0]
        pnl_full = np.array(r['pnl'], dtype=float)
        eps = [e for e in r['eps'] if e['m'] in remap]
        e_m = np.array([remap[e['m']] for e in eps], dtype=int)
        e_pnl = np.array([e['pnl'] for e in eps], dtype=float)
        e_ph = np.array([e['ph'] for e in eps])
        e_bk = np.array([bucket_of(e['px']) for e in eps])
        e_br = np.array([e.get('br', 0) or 0 for e in eps], dtype=int)
        e_hour = np.array([eastern(e['t'] + 1000 * e['hold'])[0].hour for e in eps], dtype=int) if eps else np.zeros(0, dtype=int)
        e_tour = m_tour[e_m] if len(e_m) else np.array([])
        # Sanity: the episodes add up to the match values.
        full_kept = pnl_full[keep]
        ep_tot = np.bincount(e_m, weights=e_pnl, minlength=N) if len(e_m) else np.zeros(N)
        if np.abs(ep_tot - full_kept).max(initial=0) > 0.05:
            print(f'warning: {rid}: episodes differ from match P&L by up to {np.abs(ep_tot - full_kept).max():.3f}')
        # One tour only: its level is the 'all' level (no duplicate cells).
        for t in (tours + ['all']) if len(tours) > 1 else ['all']:
            st = np.ones(len(eps), dtype=bool) if t == 'all' else (e_tour == t)
            for ph in PHASES + ['all']:
                sp = st if ph == 'all' else st & (e_ph == ph)
                for bk in BUCKETS + ['all']:
                    mask = sp if bk == 'all' else sp & (e_bk == bk)
                    n_e = int(mask.sum())
                    if n_e == 0 and not (t == 'all' and ph == 'all' and bk == 'all'):
                        continue
                    v = np.bincount(e_m[mask], weights=e_pnl[mask], minlength=N)
                    universe = np.ones(N, dtype=bool) if t == 'all' else (m_tour == t)
                    vu = v[universe]
                    n_u = len(vu)
                    mean = vu.mean() if n_u else 0.0
                    sd = vu.std(ddof=1) if n_u > 1 else 0.0
                    z = (vu - mean) / sd if sd > 0 else np.zeros(n_u)
                    skew = float((z ** 3).mean()) if sd > 0 else 0.0
                    kurt = float((z ** 4).mean()) if sd > 0 else 3.0
                    e_days = len(set(m_day[e_m[mask]])) if n_e else 0
                    mo_n = np.bincount(m_month[e_m[mask]], minlength=len(months)) if n_e else np.zeros(len(months))
                    mo_s = np.bincount(m_month[e_m[mask]], weights=e_pnl[mask], minlength=len(months)) if n_e else np.zeros(len(months))
                    big = mo_n >= 10
                    fold_share = float((mo_s[big] > 0).mean()) if big.any() else float('nan')
                    us = np.bincount(m_unit, weights=v, minlength=U)
                    cid = f'{base}|{t}|{ph}|{bk}'
                    row = dict(cell=cid, config=base, arm=arm, run=rid, tour=t, phase=ph, bucket=bk, entries=n_e, days=e_days,
                               traded=int((vu != 0).sum()), universe=n_u, net=float(v.sum()), mean=float(mean), sd=float(sd), skew=skew,
                               kurt=kurt, breaches=int(e_br[mask].sum()), fold_share=fold_share, months_big=int(big.sum()),
                               month_means=[float(mo_s[i] / max(1, (m_month[universe] == i).sum())) for i in range(len(months))],
                               overrides=r['overrides'])
                    cells.append(row)
                    unit_sums.append(us)
                    hourly.append(np.bincount(e_hour[mask], weights=e_pnl[mask], minlength=24) if n_e else np.zeros(24))
                    if arm == 'F1' and n_e >= a.onc_min:
                        vec_store[len(cells) - 1] = v.astype(np.float32)
    US = np.array(unit_sums)
    nC = len(cells)
    print(f'{nC} cells scored over {N} matches ({no_tape} no-tape matches left out), {U} units, {len(days)} days')

    # ---- bootstrap means and p-values (vectorised over cells, per series denominator)
    den = {t: W @ unit_n[t] for t in unit_n}
    boot_mean = np.empty((a.boot, nC))
    for t in unit_n:
        idx = [i for i, c in enumerate(cells) if c['tour'] == t]
        if idx:
            boot_mean[:, idx] = (W @ US[idx].T) / den[t][:, None]
    means = np.array([c['mean'] for c in cells])
    centred = boot_mean - means[None, :]
    p_boot = (centred >= means[None, :]).mean(axis=0)
    omega = boot_mean.std(axis=0, ddof=1)
    lo, hi = np.percentile(boot_mean, [5, 95], axis=0)
    for i, c in enumerate(cells):
        c.update(p=float(p_boot[i]), ci90=[float(lo[i]), float(hi[i])], t_boot=float(means[i] / omega[i]) if omega[i] > 0 else 0.0)

    by_id = {(c['config'], c['arm'], c['tour'], c['phase'], c['bucket']): i for i, c in enumerate(cells)}
    f1 = [i for i, c in enumerate(cells) if c['arm'] == 'F1']
    rej = bh([cells[i]['p'] for i in f1], a.alpha)
    for j, i in enumerate(f1):
        c = cells[i]
        k = (c['config'], 'F2', c['tour'], c['phase'], c['bucket'])
        kc = (c['config'], 'coin', c['tour'], c['phase'], c['bucket'])
        f2 = cells[by_id[k]] if k in by_id else None
        pc = by_id.get(kc)
        c['bh'] = bool(rej[j])
        c['f2_net'] = f2['net'] if f2 else 0.0
        if pc is not None:
            d_us = US[i] - US[pc]
            d_mean = (cells[i]['net'] - cells[pc]['net']) / max(1, c['universe'])
            d_boot = (W @ d_us) / den[c['tour']]
            c['placebo_diff'] = float(d_mean)
            c['p_placebo'] = float(((d_boot - d_mean) >= d_mean).mean())
            c['placebo_partner'] = cells[pc]['cell']
        c['flag'] = bool(c['bh'] and c['entries'] >= 100 and c['days'] >= 30 and c['mean'] > 0
                         and (c['fold_share'] >= 0.6 if c['months_big'] else False) and c['f2_net'] > 0 and c['breaches'] == 0)

    # ---- ONC over F1 cells with enough entries
    onc_ids = sorted(vec_store, key=lambda i: -cells[i]['entries'])
    dropped = 0
    if len(onc_ids) > a.onc_cap:
        dropped = len(onc_ids) - a.onc_cap
        onc_ids = onc_ids[:a.onc_cap]
    n_eff, labels, medoids, best_in = 0, np.array([]), [], []
    if len(onc_ids) >= 3:
        X = np.array([vec_store[i] for i in onc_ids], dtype=np.float64)
        X = X - X.mean(axis=1, keepdims=True)
        nrm = np.linalg.norm(X, axis=1)
        nrm[nrm == 0] = 1
        corr = np.clip((X / nrm[:, None]) @ (X / nrm[:, None]).T, -1, 1)
        labels = onc(corr, a.seed)
        n_eff = int(labels.max() + 1)
        dist = np.sqrt(np.clip((1 - corr) / 2, 0, 1))
        for k in range(n_eff):
            idx = np.nonzero(labels == k)[0]
            medoids.append(onc_ids[idx[np.argmin(dist[np.ix_(idx, idx)].sum(axis=1))]])
            best_in.append(onc_ids[idx[np.argmax([cells[onc_ids[j]]['mean'] for j in idx])]])
    elif onc_ids:
        n_eff = len(onc_ids)
    n_eff = max(n_eff, 1)

    # ---- SPA (consistent) and StepM over medoids + cluster bests + production
    prod = [i for i, c in enumerate(cells) if c['arm'] == 'F1' and c['tour'] == 'all' and c['phase'] == 'all' and c['bucket'] == 'all'
            and c['overrides'].get('TENNIS_CONF_MOMENTUM_CENTS') == 0.01 and c['overrides'].get('TENNIS_CONF_FLOW') == 0.2
            and c['overrides'].get('TENNIS_CONF_OPPONENT_CENTS') == 0.01 and c['overrides'].get('TENNIS_CONF_WINDOW_SEC') == 60]
    sticks = [i for i, c in enumerate(cells) if c['arm'] == 'stick' and c['tour'] == 'all' and c['phase'] == 'all' and c['bucket'] == 'all']
    spa_set = sorted(set(medoids) | set(best_in) | set(prod) | {i for i in f1 if cells[i]['flag']})
    spa = {}
    if spa_set:
        mh = means[spa_set]
        om = np.where(omega[spa_set] > 0, omega[spa_set], np.inf)
        tk = mh / om
        T = max(0.0, float(tk.max()))
        thr = -math.sqrt(2 * math.log(max(math.log(N), 1.0001)))
        mu_c = np.where(tk <= thr, np.minimum(mh, 0), 0.0)
        Z = (boot_mean[:, spa_set] - mh[None, :] + mu_c[None, :]) / om[None, :]
        Tb = np.maximum(0, Z.max(axis=1))
        spa = {'T': T, 'p_consistent': float((Tb >= T).mean()), 'models': len(spa_set), 'best': cells[spa_set[int(np.argmax(tk))]]['cell']}
        # StepM (Romano-Wolf), one-sided, alpha
        active = list(range(len(spa_set)))
        rejected = []
        cen = (boot_mean[:, spa_set] - mh[None, :]) / om[None, :]
        while active:
            c_alpha = float(np.quantile(cen[:, active].max(axis=1), 1 - a.alpha))
            new = [k for k in active if tk[k] > c_alpha]
            if not new:
                break
            rejected += new
            active = [k for k in active if k not in new]
        spa['stepm_rejected'] = [cells[spa_set[k]]['cell'] for k in rejected]
        spa['stepm_alpha'] = a.alpha

    # ---- DSR at N_eff
    srs = np.array([cells[i]['mean'] / cells[i]['sd'] for i in onc_ids if cells[i]['sd'] > 0]) if onc_ids else np.array([])
    v_sr = float(srs.var(ddof=1)) if len(srs) > 1 else 0.0
    sr0 = math.sqrt(v_sr) * ((1 - EULER) * norm_ppf(1 - 1 / max(n_eff, 2)) + EULER * norm_ppf(1 - 1 / (max(n_eff, 2) * math.e))) if v_sr > 0 else 0.0
    for i in set(spa_set) | set(f1[:0]):
        c = cells[i]
        sr = c['mean'] / c['sd'] if c['sd'] > 0 else 0.0
        denom = 1 - c['skew'] * sr + (c['kurt'] - 1) / 4 * sr * sr
        c['sr'] = sr
        c['dsr'] = norm_cdf((sr - sr0) * math.sqrt(max(c['universe'] - 1, 1)) / math.sqrt(denom)) if denom > 0 else float('nan')

    # ---- PBO (CSCV) over the months for the stage's configs ('all' cells, F1)
    allc = [i for i in f1 if cells[i]['tour'] == 'all' and cells[i]['phase'] == 'all' and cells[i]['bucket'] == 'all']
    pbo = None
    if len(allc) >= 2 and len(months) >= 4:
        P = np.array([cells[i]['month_means'] for i in allc]).T  # months x configs
        S = len(months) - (len(months) % 2)
        P = P[:S]
        from itertools import combinations
        combos = list(combinations(range(S), S // 2))
        if len(combos) > 2000:
            combos = [combos[j] for j in rng.choice(len(combos), 2000, replace=False)]
        logits = []
        for cmb in combos:
            ins = np.zeros(S, dtype=bool)
            ins[list(cmb)] = True
            best = int(np.argmax(P[ins].mean(axis=0)))
            oos = P[~ins].mean(axis=0)
            rank = (oos < oos[best]).sum() + 0.5 * ((oos == oos[best]).sum() - 1) + 1
            w = rank / (len(allc) + 1)
            logits.append(math.log(w / (1 - w)))
        pbo = {'pbo': float(np.mean(np.array(logits) <= 0)), 'combos': len(combos), 'months': S}

    # ---- knob sensitivity (stage 1: range of mean net per match across each knob's levels, F1 'all' cells)
    sens = {}
    for knob in ['TENNIS_CONF_MOMENTUM_CENTS', 'TENNIS_CONF_FLOW', 'TENNIS_CONF_OPPONENT_CENTS', 'TENNIS_CONF_WINDOW_SEC']:
        lv = defaultdict(list)
        for i in allc:
            o = cells[i]['overrides']
            if knob in o and 'HARNESS_LOSER_CUT' not in o and 'HARNESS_PACER' not in o:
                lv[o[knob]].append(cells[i]['mean'])
        if lv:
            ms = {str(k): float(np.mean(v)) for k, v in sorted(lv.items())}
            sens[knob] = {'levels': ms, 'range': max(ms.values()) - min(ms.values())}

    # ---- loser tables: production and the five best F1 configs by mean ('all' cells)
    top_cfg = [cells[i]['run'] for i in sorted(allc, key=lambda i: -cells[i]['mean'])[:5]]
    prod_runs = [cells[i]['run'] for i in prod]
    loser_rows = []
    for rid in dict.fromkeys(prod_runs + top_cfg):
        g = defaultdict(lambda: [0, 0.0, 0])
        for e in runs[rid]['eps']:
            if e['m'] not in remap:
                continue
            key = (tour(M[remap[e['m']]]['series']), e['ph'], e['leg'], int(e['sig']), bucket_of(e['px']), e['x'])
            s = g[key]
            s[0] += 1
            s[1] += e['pnl']
            s[2] += 1 if e['pnl'] > 0 else 0
        for key, (n, net, wins) in sorted(g.items(), key=lambda kv: kv[1][1]):
            loser_rows.append(dict(run=rid, tour=key[0], phase=key[1], leg=key[2], signals=key[3], bucket=key[4], exit=key[5], n=n, net=round(net, 4), mean=round(net / n, 4), win=round(wins / n, 3)))

    # ---- registry rows (every scored cell = N_raw)
    from_d, to_d = min(m['day'] for m in M), max(m['day'] for m in M)
    e_from, z_from = eastern(M[0]['start'])
    e_to, z_to = eastern(t_last)
    n_raw = nC
    reg = []
    for i, c in enumerate(cells):
        ch = hashlib.sha1(json.dumps(c['overrides'], sort_keys=True).encode()).hexdigest()[:16]
        reg.append(dict(thread='tennis-ta', run=a.run, cell=c['cell'], arm=c['arm'], sha=meta['sha'], config_hash=ch, overrides=c['overrides'],
                        sim_version=meta['sim_version'], evidence=meta['evidence'], stage=meta['stage'], pool=a.pool,
                        days_utc=[from_d, to_d], days_eastern=[e_from.strftime('%Y-%m-%d %H:%M ') + z_from, e_to.strftime('%Y-%m-%d %H:%M ') + z_to],
                        seeds={'coin': 'hash32(spec id)', 'bootstrap': a.seed}, doge_excluded=True, entries=c['entries'], matches=c['universe'],
                        net=round(c['net'], 4), mean_per_match=round(c['mean'], 6), usd_per_hour=round(c['net'] / pool_hours, 6) if pool_hours else None,
                        hourly_eastern=[round(x, 4) for x in hourly[i]], placebo_partner=c.get('placebo_partner'), gate='stage1-screen' if meta['stage'] == '1' else f"stage{meta['stage']}",
                        verdict=('flag' if c.get('flag') else 'no') if c['arm'] == 'F1' else 'stick' if c['arm'] == 'stick' else 'arm', p_boot=c['p'], n_raw=n_raw, n_eff=n_eff))
    with gzip.open(os.path.join(a.out, f'registry-tennis-ta-{a.run}.jsonl.gz'), 'wt') as fh:
        for r in reg:
            fh.write(json.dumps(r) + '\n')

    # ---- outputs
    slim = [{k: v for k, v in c.items() if k not in ('month_means',)} for c in cells]
    with gzip.open(os.path.join(a.out, 'cells.json.gz'), 'wt') as fh:
        json.dump(slim, fh)
    with open(os.path.join(a.out, 'losers.json'), 'w') as fh:
        json.dump(loser_rows, fh)
    summary = dict(run=a.run, pool=a.pool, meta=meta, matches=N, no_tape=no_tape, units=U, days=len(days), months=months, pool_hours=pool_hours,
                   live_hours=live_hours, n_raw=n_raw, f1_cells=len(f1), bh_rejections=int(rej.sum()), flagged=[cells[i]['cell'] for i in f1 if cells[i]['flag']],
                   n_eff=n_eff, onc_cells=len(onc_ids), onc_dropped=dropped, spa=spa, sr0=sr0, v_sr=v_sr, pbo=pbo, sensitivity=sens,
                   production=[{k: cells[i].get(k) for k in ('cell', 'entries', 'net', 'mean', 'ci90', 'p', 'f2_net', 'placebo_diff', 'p_placebo', 'breaches', 'dsr')} for i in prod],
                   sticks=[{k: cells[i].get(k) for k in ('cell', 'entries', 'net', 'mean', 'ci90', 'p', 'breaches')} for i in sticks])
    with open(os.path.join(a.out, 'summary.json'), 'w') as fh:
        json.dump(summary, fh, indent=1, default=float)

    # ---- the markdown report
    def usd(x):
        return f"{'-' if x < 0 else ''}${abs(x):,.2f}"
    L = []
    L.append(f"## Tennis TA sweep, stage {meta['stage']}, pool {a.pool} (run {a.run})")
    L.append(f"Evidence: {meta['evidence']}. sha {meta['sha'][:10]}, {meta['sim_version']}. Days {from_d} to {to_d} UTC "
             f"({e_from.strftime('%b %-d %-I:%M %p')} {z_from} to {e_to.strftime('%b %-d %-I:%M %p')} {z_to}).")
    L.append(f"{N} matches with a tape ({no_tape} without one left out), {U} tournament-week units, {len(days)} match-days. "
             f"N_raw = {n_raw} cells scored ({len(f1)} F1 cells screened); N_eff = {n_eff} (ONC over {len(onc_ids)} cells with >= {a.onc_min} entries"
             f"{f', {dropped} beyond the cap left out' if dropped else ''}). Pool hours {pool_hours:,.0f}, live-match hours {live_hours:,.0f}.")
    L.append('')
    L.append('Production (momentum 1c, flow 0.2, opponent 1c, window 60 s; loser cut on, tennis-only pacer):')
    for p in summary['production']:
        L.append(f"- {p['entries']} entries, net {usd(p['net'])}, {usd(p['mean'])} a match (90% CI {usd(p['ci90'][0])} to {usd(p['ci90'][1])}), "
                 f"p = {p['p']:.3f}; F2 {usd(p['f2_net'])}; vs placebo {usd(p.get('placebo_diff') or 0)} a match (p = {p.get('p_placebo', float('nan')):.3f}); "
                 f"{usd(p['net'] / pool_hours) if pool_hours else 'n/a'}/h over 24 h; breaches {p['breaches']}")
    for p in summary['sticks']:
        L.append(f"- measuring stick {p['cell'].split('|')[3]}: {p['entries']} entries, net {usd(p['net'])}, {usd(p['mean'])} a match "
                 f"(90% CI {usd(p['ci90'][0])} to {usd(p['ci90'][1])}); breaches {p['breaches']}")
    L.append('')
    L.append(f"Screen: BH q = {a.alpha} rejects {int(rej.sum())} of {len(f1)} F1 cells; {len(summary['flagged'])} pass every discovery condition.")
    if spa:
        L.append(f"SPA (consistent) over {spa['models']} models: T = {spa['T']:.2f}, p = {spa['p_consistent']:.3f}, best {spa['best']}. "
                 f"StepM (alpha {a.alpha}) rejects {len(spa['stepm_rejected'])}.")
    if pbo:
        L.append(f"PBO (CSCV, {pbo['months']} months, {pbo['combos']} splits): {pbo['pbo']:.2f}.")
    L.append(f"DSR reference SR0 = {sr0:.4f} per match (variance of per-match Sharpe across the ONC cells {v_sr:.6f}).")
    L.append('')
    top = sorted(f1, key=lambda i: (not cells[i]['flag'], cells[i]['p'], -cells[i]['mean']))[:25]
    L.append('| cell | entries | days | net | $/match | 90% CI | p | BH | F2 net | vs placebo | folds+ | DSR |')
    L.append('|---|---|---|---|---|---|---|---|---|---|---|---|')
    for i in top:
        c = cells[i]
        L.append(f"| {c['cell'].replace('A|s1|', '')} | {c['entries']} | {c['days']} | {usd(c['net'])} | {c['mean']:.4f} | {c['ci90'][0]:.3f}..{c['ci90'][1]:.3f} | {c['p']:.3f} | "
                 f"{'yes' if c['bh'] else 'no'} | {usd(c['f2_net'])} | {c.get('placebo_diff', 0):.4f} (p {c.get('p_placebo', float('nan')):.2f}) | "
                 f"{'-' if c['fold_share'] != c['fold_share'] else format(c['fold_share'], '.0%')} | {'-' if 'dsr' not in c else format(c['dsr'], '.2f')} |")
    L.append('')
    L.append('Knob sensitivity (mean net a match by level, F1, all matches):')
    for k, s in sens.items():
        L.append(f"- {k}: " + ', '.join(f"{lv}: {v:.4f}" for lv, v in s['levels'].items()) + f" (range {s['range']:.4f})")
    L.append('')
    L.append('Biggest losers (production, F1):')
    for r_ in [x for x in loser_rows if x['run'] in prod_runs][:12]:
        sig = '+'.join(n for b, n in ((1, 'momentum'), (2, 'flow'), (4, 'depth'), (8, 'opponent')) if r_['signals'] & b) or 'none'
        L.append(f"- {r_['tour']} {r_['phase']} {r_['leg']} -> {r_['exit']}, {r_['bucket']}c, signals {sig}: {r_['n']} trades, {usd(r_['net'])} ({r_['win']:.0%} won)")
    with open(os.path.join(a.out, 'report.md'), 'w') as fh:
        fh.write('\n'.join(L) + '\n')
    print('\n'.join(L))


if __name__ == '__main__':
    main()
