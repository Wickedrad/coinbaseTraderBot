"""AP-H1b P2b: does lead information add settlement skill on tight books? (prereg/AP-H1b.md, Amendment 1)

    python -m allpairs.skill --history data/history --out skill.json [--assets BTC,ETH,SOL,XRP]

Two LightGBM classifiers of P(settle YES) on YES-side decision minutes (minute k >= 1 with a two-sided book). One uses
config base's features and the other lead_btc's. Both are fitted on H-DEV, which is HO-1's training span Apr 18-Jul 29
with the run's training filters, and both early-stop on its last 10 days after a 1-day embargo. An isotonic map of the
YES mid to settlement (the FLB-corrected mid) is fitted on the same rows.

Scoring is on H-HOLD (Aug 1-Nov 4) minutes whose book is 10c wide or less:
- Brier skill against the mapped mid;
- dBSS = (BS_base - BS_lead) / BS_ref, with the ratio estimator's Newey-West standard error over held-out days
  (Bartlett weights, lag 3, on daily sums);
- TOST against +/-0.002 (90% CI) and the two-sided Diebold-Mariano p from the same t.

H-HOLD is read only here, once, for scoring. The lockbox weeks are never loaded.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os

import numpy as np

from . import DEFAULT_ASSETS, EXCLUDED_ASSETS
from .data import MIN, load_kalshi, load_spot
from .features import BASE_NAMES, spot_features
from .validate import HO1_DEV_FROM, HO1_HOLD_FROM, HO1_HOLD_TO, inner_split

BAND = 0.002
NW_LAG = 3
MAX_SPREAD = 0.10
EPS = 1e-9
PARAMS = dict(objective='binary', num_leaves=31, learning_rate=0.05, min_data_in_leaf=500, feature_fraction=0.8,
              bagging_fraction=0.8, bagging_freq=1, lambda_l2=1.0, seed=7, deterministic=True, force_col_wise=True,
              verbosity=-1, num_threads=0)
MAX_ROUNDS, EARLY_STOP = 2000, 50
HERE = os.path.dirname(__file__)


def log(m: str):
    print(f'[skill {dt.datetime.now(dt.timezone.utc).strftime("%H:%M:%S")}] {m}', flush=True)


def _day(iso: str) -> int:
    return (dt.date.fromisoformat(iso) - dt.date(1970, 1, 1)).days


def isotonic_fit(x: np.ndarray, y: np.ndarray):
    """Increasing least-squares fit of y on x (pool adjacent violators over the distinct x values): (knots x, fitted y)."""
    ux, inv = np.unique(np.asarray(x, dtype=np.float64), return_inverse=True)
    wsum = np.bincount(inv).astype(np.float64)
    ysum = np.bincount(inv, weights=np.asarray(y, dtype=np.float64))
    vals, wts, cnt = [], [], []
    for v, w_ in zip(ysum / wsum, wsum):
        vals.append(v); wts.append(w_); cnt.append(1)
        while len(vals) > 1 and vals[-2] > vals[-1]:
            w2 = wts[-2] + wts[-1]
            vals[-2] = (vals[-2] * wts[-2] + vals[-1] * wts[-1]) / w2
            wts[-2] = w2
            cnt[-2] += cnt[-1]
            vals.pop(); wts.pop(); cnt.pop()
    fitted = np.repeat(vals, cnt)
    return ux, fitted


def isotonic_apply(knots, x: np.ndarray) -> np.ndarray:
    kx, ky = knots
    return np.interp(np.asarray(x, dtype=np.float64), kx, ky)


def newey_west_ratio(e: np.ndarray, n: np.ndarray, lag: int = NW_LAG) -> tuple:
    """(estimate, standard error) of sum(e) / sum(n) over the periods (in order), the variance by Newey-West with
    Bartlett weights on u_d = e_d - estimate * n_d."""
    e = np.asarray(e, dtype=np.float64)
    n = np.asarray(n, dtype=np.float64)
    tot = float(n.sum())
    if tot <= 0 or len(e) < 2:
        return float('nan'), float('nan')
    est = float(e.sum()) / tot
    u = e - est * n
    s = float(np.dot(u, u))
    for l_ in range(1, min(lag, len(u) - 1) + 1):
        s += 2 * (1 - l_ / (lag + 1)) * float(np.dot(u[l_:], u[:-l_]))
    return est, math.sqrt(max(s, 0.0)) / tot


def _ncdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def compare(y, p_base, p_lead, ref, day) -> dict:
    """Brier scores and the skill difference on the scored minutes, its day-level Newey-West error, TOST and DM."""
    y = np.asarray(y, dtype=np.float64)
    bs = lambda p: float(np.mean((np.asarray(p) - y) ** 2))
    bs_ref, bs_b, bs_l = bs(ref), bs(p_base), bs(p_lead)
    d = ((p_base - y) ** 2 - (p_lead - y) ** 2) / bs_ref
    ud, inv = np.unique(day, return_inverse=True)
    e = np.bincount(inv, weights=d)
    n = np.bincount(inv).astype(np.float64)
    est, se = newey_west_ratio(e, n)
    t = est / se if se and se > 0 else float('nan')
    p_dm = 2 * (1 - _ncdf(abs(t))) if t == t else float('nan')
    lo90, hi90 = est - 1.645 * se, est + 1.645 * se
    equiv = bool(lo90 > -BAND and hi90 < BAND)
    if est > 0 and p_dm < 0.05:
        verdict = 'falsifier: lead features add settlement skill (dBSS > 0, DM p < 0.05)'
    elif equiv:
        verdict = f'holds: dBSS within +/-{BAND} (TOST at 5%)'
    else:
        verdict = 'undecided: the 90% CI is not inside the band (underpowered or a skill loss), and no significant gain'
    return dict(rows=int(len(y)), days=int(len(ud)), bs_ref=round(bs_ref, 6), bs_base=round(bs_b, 6), bs_lead=round(bs_l, 6),
                bss_base=round(1 - bs_b / bs_ref, 5), bss_lead=round(1 - bs_l / bs_ref, 5), dbss=round(est, 6), se=round(se, 6),
                ci90=[round(lo90, 6), round(hi90, 6)], t=round(t, 3) if t == t else None, p_dm=round(p_dm, 4) if p_dm == p_dm else None,
                tost_equivalent=equiv, verdict=verdict)


def fit_classifier(X, y, fit_sel, val_sel, names):
    import lightgbm as lgb
    dtr = lgb.Dataset(X[fit_sel], label=y[fit_sel], feature_name=names, free_raw_data=True)
    dva = lgb.Dataset(X[val_sel], label=y[val_sel], reference=dtr, free_raw_data=True)
    bst = lgb.train(PARAMS, dtr, num_boost_round=MAX_ROUNDS, valid_sets=[dva],
                    callbacks=[lgb.early_stopping(EARLY_STOP, verbose=False)])
    imp = bst.feature_importance('gain')
    top = sorted(zip(names, imp.tolist()), key=lambda kv: -kv[1])[:12]
    return bst, dict(best_iteration=int(bst.best_iteration), top_gain=[[n_, round(v, 1)] for n_, v in top])


def run(history: str, assets: list, out: str, dev_from=HO1_DEV_FROM, hold_from=HO1_HOLD_FROM, hold_to=HO1_HOLD_TO,
        embargo_days: int = 2, inner_days: int = 10) -> dict:
    from .run import DEFAULTS, arm_config, window_inputs
    base_cfg = arm_config(json.load(open(os.path.join(HERE, 'hypotheses', 'base.json'))), 'base')
    lead_cfg = arm_config(json.load(open(os.path.join(HERE, 'hypotheses', 'lead_btc.json'))), 'base')
    ms = lambda x: int(dt.datetime.fromisoformat(x).replace(tzinfo=dt.timezone.utc).timestamp() * 1000)
    sealed = set()
    for lo_s, hi_s in DEFAULTS.get('exclude_utc') or []:
        sealed |= set(range(ms(lo_s) // 86_400_000, (ms(hi_s) - 1) // 86_400_000 + 1))
    real = load_kalshi(history, assets, n=15, log=log, skip_days=sealed)
    lo, hi = int(real.open_ms.min()) - 2 * 86_400_000, int(real.open_ms.max()) + 2 * 86_400_000
    spots, sfeats = {}, {}
    for ai, asset in enumerate(real.assets):
        if asset in EXCLUDED_ASSETS:
            continue
        spots[ai] = load_spot(history, asset, lo, hi)
        sfeats[ai] = spot_features(spots[ai])
    real = real.subset(np.nonzero(np.isin(real.asset, list(spots)))[0])
    keep = ~np.isin(real.day, sorted(sealed))
    for lo_s, hi_s in DEFAULTS.get('exclude_utc') or []:
        keep &= ~((real.open_ms + real.n * MIN > ms(lo_s)) & (real.open_ms < ms(hi_s)))
    w = real.subset(np.nonzero(keep)[0])
    clean = w.real_frac >= base_cfg['min_real_frac']
    if w.crossed is not None:
        clean &= ~(w.crossed > base_cfg['max_crossed'])
    d_dev, d_hold, d_end = _day(dev_from), _day(hold_from), _day(hold_to)
    day = w.day
    dev_w = (day >= d_dev) & (day < d_hold - embargo_days) & clean
    hold_w = (day >= d_hold) & (day <= d_end)
    log(f'windows: {len(w)}; H-DEV {int(dev_w.sum())} (clean), H-HOLD {int(hold_w.sum())}')
    # Features: lead_btc's set holds base's as its leading columns (window_features: BASE_NAMES, sorted cross, extras).
    _, _, X, names_lead = window_inputs(w, spots, sfeats, real.assets, lead_cfg)
    names_base = list(BASE_NAMES) + sorted(base_cfg.get('cross_assets') or []) + [e['name'] for e in base_cfg.get('extra_features') or []]
    if base_cfg.get('cross_assets'):
        raise SystemExit('config base has cross assets: its features are not a prefix of lead_btc\'s')
    nb = len(names_base)
    if names_lead[:nb] != names_base:
        raise SystemExit('lead_btc features do not start with base features')
    N = w.n
    k = np.arange(N)[None, :]
    ok = np.isfinite(w.bid) & np.isfinite(w.ask) & (k >= 1)
    wi, ki = np.nonzero(ok)
    Xr = X[wi, 0, ki, :]
    del X
    y = w.settle[wi].astype(np.float64)
    mid = (w.bid[wi, ki] + w.ask[wi, ki]) / 2
    spread = w.ask[wi, ki] - w.bid[wi, ki]
    rday = day[wi]
    dev_r, hold_r = dev_w[wi], hold_w[wi]
    fit_days, val_days = inner_split(np.unique(rday[dev_r]), inner_days, 1)
    if not len(val_days):
        raise SystemExit(f'H-DEV has too few days for {inner_days} early-stopping days')
    fit_r = dev_r & np.isin(rday, fit_days)
    val_r = dev_r & np.isin(rday, val_days)
    log(f'rows: H-DEV fit {int(fit_r.sum())}, early-stop {int(val_r.sum())}; H-HOLD {int(hold_r.sum())}')
    flb = isotonic_fit(mid[dev_r], y[dev_r])
    m_base, info_b = fit_classifier(Xr[:, :nb], y, fit_r, val_r, names_base)
    m_lead, info_l = fit_classifier(Xr, y, fit_r, val_r, names_lead)
    tight = hold_r & (spread <= MAX_SPREAD + EPS)
    res = dict(prereg='prereg/AP-H1b.md P2b (Amendment 1)', dev=[dev_from, f'purge {embargo_days} days before {hold_from}'],
               hold=[hold_from, hold_to], early_stop_days=[int(val_days[0]), int(val_days[-1])] if len(val_days) else None,
               models=dict(base=info_b, lead=info_l), flb_knots=int(len(flb[0])), lockbox='never loaded')
    for label, sel in (('tight', tight), ('all_books', hold_r),
                       ('tight_historical', tight & (rday < 20708)), ('tight_live', tight & (rday >= 20708))):
        if not sel.any():
            continue
        pb = m_base.predict(Xr[sel][:, :nb], num_iteration=m_base.best_iteration)
        pl = m_lead.predict(Xr[sel], num_iteration=m_lead.best_iteration)
        res[label] = compare(y[sel], pb, pl, isotonic_apply(flb, mid[sel]), rday[sel])
        log(f'{label}: {res[label]}')
    res['p2b'] = res.get('tight', {}).get('verdict')
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, 'w') as fh:
        json.dump(res, fh, indent=1)
    return res


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--history', default='data/history')
    ap.add_argument('--assets', default=','.join(DEFAULT_ASSETS))
    ap.add_argument('--out', required=True)
    ap.add_argument('--span', default=f'{HO1_DEV_FROM},{HO1_HOLD_FROM},{HO1_HOLD_TO}', help='dev_from,hold_from,hold_to (tests)')
    ap.add_argument('--inner-days', type=int, default=10, help='early-stopping days at the end of H-DEV (tests only)')
    a = ap.parse_args(argv)
    assets = [x.strip().upper() for x in a.assets.split(',') if x.strip() and x.strip().upper() not in EXCLUDED_ASSETS]
    dev_from, hold_from, hold_to = a.span.split(',')
    run(a.history, assets, a.out, dev_from, hold_from, hold_to, inner_days=a.inner_days)


if __name__ == '__main__':
    main()
