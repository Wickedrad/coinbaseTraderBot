"""Run one arm of the all-pairs study end to end and write its JSON result.

    python -m allpairs.run --history data/history --config python/allpairs/hypotheses/base.json --arm base --out out/base.json

Arms (presets layered over the config file):
    base     real 15-minute Kalshi quotes, the config as written
    stress   same, with every taker leg one cent worse, the maker fee charged (0.0175) and maker fills needing a cent of
             trade-through: does the edge survive costs the history may understate?
    placebo  same as base, plus entry models refitted on permuted labels (the gain must beat what no-information
             models make on the same folds)
    synth15  real 15-minute windows priced by the synthetic pricer instead of their real quotes (the pricer's fidelity)
    synth1h  hourly windows priced synthetically (no hourly Kalshi quotes on Drive): reported apart, never gated
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import sys
import time

import numpy as np

from . import DEFAULT_ASSETS, EXCLUDED_ASSETS
from .data import MIN, Windows, allowed_assets, load_kalshi, load_spot
from .features import BASE_NAMES, side_quotes, spot_at, spot_features, window_features
from .matrix import Costs, all_pairs
from .policy import EntryConfig, entry_rows, fit_entry, maker_attempts, pnl_stats, random_entry_placebo, simulate
from .snell import STATE_EXTRA, Book, ExitConfig, build_positions, solve_exits
from .synthetic import calibrate, hourly_windows, price_windows
from .validate import block_bootstrap_mean, inner_split, psr, walk_forward

DEFAULTS = {
    'name': 'base',
    'costs': {'stake': 15.0, 'slip': 0.0, 'taker_mult': 1.0, 'maker_mult': 0.0, 'strict_maker': False},
    'exit': {'end_rule': 'bot', 'end_frac': 0.10, 'maker_exits': True, 'rows_per_fit': 200_000},
    'entry': {'hurdles': [0.0, 0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 1e9], 'maker_entries': True, 'entry_minutes': None, 'rows_per_fit': 1_000_000},
    'extra_features': [],
    'placebo': {'shuffles': 3, 'random_draws': 50},
    'walk': {'train_days': 90, 'test_days': 14, 'embargo_days': 1, 'inner_days': 14, 'rolling': True},
    'min_real_frac': 0.8,
    'hourly_offsets': [0.0],
}

ARMS = {
    'base': {},
    'stress': {'costs': {'slip': 0.01, 'maker_mult': 1.0, 'strict_maker': True}, 'placebo': {'shuffles': 0}},
    'placebo': {'placebo': {'shuffles': 3}},
    'synth15': {'kind': 'synth15', 'placebo': {'shuffles': 0}},
    'synth1h': {'kind': 'synth1h', 'exit': {'rows_per_fit': 100_000}, 'placebo': {'shuffles': 0}},
}


def merge(a: dict, b: dict) -> dict:
    out = copy.deepcopy(a)
    for k, v in b.items():
        out[k] = merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else copy.deepcopy(v)
    return out


def config_hash(cfg: dict) -> str:
    keep = {k: v for k, v in cfg.items() if k not in ('name', 'placebo', 'notes')}
    return hashlib.sha1(json.dumps(keep, sort_keys=True).encode()).hexdigest()[:10]


def log(m: str):
    print(f'[all-pairs {time.strftime("%H:%M:%S", time.gmtime())}] {m}', flush=True)


def regime_tags(trades: dict, cuts: dict) -> list[str]:
    vol = np.digitize(trades['rv60'], cuts['rv60'])
    tau = np.digitize(trades['tau_frac'], [0.34, 0.67])
    price = np.digitize(trades['price'], [0.30, 0.70])
    side = trades['side']
    names_v = ['calm', 'normal', 'volatile']
    names_t = ['late', 'mid', 'early']
    names_p = ['<30c', '30-70c', '>70c']
    return [f'{names_v[v]} | {names_t[t]} entry | {"YES" if s == 0 else "NO"} {names_p[p]}' for v, t, s, p in zip(vol, tau, side, price)]


def shap_top(model, X: np.ndarray, names: list[str], top: int = 12, rows: int = 20_000, seed: int = 5) -> list:
    if not len(X):
        return []
    rng = np.random.default_rng(seed)
    sel = rng.choice(len(X), min(rows, len(X)), replace=False)
    try:
        contrib = model.predict(X[sel], pred_contrib=True)
    except Exception:  # a mean model
        return []
    imp = np.abs(contrib[:, :-1]).mean(axis=0)
    order = np.argsort(-imp)[:top]
    return [[names[j], round(float(imp[j]), 4)] for j in order]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--history', default='data/history')
    ap.add_argument('--config', default=os.path.join(os.path.dirname(__file__), 'hypotheses', 'base.json'))
    ap.add_argument('--arm', default='base', choices=sorted(ARMS))
    ap.add_argument('--assets', default=','.join(DEFAULT_ASSETS))
    ap.add_argument('--days', type=int, default=0, help='only the most recent N days (0 = all)')
    ap.add_argument('--max-folds', type=int, default=0)
    ap.add_argument('--part', type=int, default=0, help='this job runs folds with index %% parts == part')
    ap.add_argument('--parts', type=int, default=1)
    ap.add_argument('--out', required=True)
    a = ap.parse_args(argv)
    t_start = time.time()
    with open(a.config) as fh:
        file_cfg = json.load(fh)
    cfg = merge(merge(DEFAULTS, file_cfg), ARMS[a.arm])
    kind = cfg.get('kind', 'real15')
    asked = [x.strip().upper() for x in a.assets.split(',') if x.strip()]
    assets = allowed_assets(asked)
    dropped = sorted(set(asked) - set(assets))
    if dropped:
        log(f'assets excluded by rule: {",".join(dropped)} (DOGE is not used at all)')
    costs = Costs(**cfg['costs'])
    xcfg = ExitConfig(end_rule=cfg['exit']['end_rule'], end_frac=cfg['exit']['end_frac'], maker_exits=cfg['exit']['maker_exits'],
                      rows_per_fit=cfg['exit']['rows_per_fit'])
    ecfg = EntryConfig(hurdles=tuple(cfg['entry']['hurdles']), rows_per_fit=cfg['entry']['rows_per_fit'])
    walk = cfg['walk']

    # ---- data
    real = load_kalshi(a.history, assets, n=15, log=log)
    if a.days:
        cut = real.open_ms.max() - a.days * 86_400_000
        real = real.subset(np.nonzero(real.open_ms >= cut)[0])
    lo, hi = int(real.open_ms.min()) - 2 * 86_400_000, int(real.open_ms.max()) + 2 * 86_400_000
    spots, sfeats = {}, {}
    for ai, asset in enumerate(real.assets):
        if asset in EXCLUDED_ASSETS:
            continue
        try:
            spots[ai] = load_spot(a.history, asset, lo, hi)
        except (SystemExit, OSError) as e:
            log(f'spot: {asset}: {e}')
            continue
        sfeats[ai] = spot_features(spots[ai])
    real = real.subset(np.nonzero(np.isin(real.asset, list(spots)))[0])
    log(f'real 15m windows: {len(real)} ({np.mean(real.real_frac):.2f} of minutes quoted), {len(np.unique(real.day))} days, assets {real.assets}')
    real_q = real.subset(np.nonzero(real.real_frac >= cfg['min_real_frac'])[0])
    folds_days = walk_forward(real_q.day, walk['train_days'], walk['test_days'], walk['embargo_days'], walk['rolling'])
    if a.max_folds:
        folds_days = folds_days[-a.max_folds:]
    if not folds_days:
        raise SystemExit('not enough days for one walk-forward fold')
    first_test = int(folds_days[0][1][0])
    fidelity = None
    if kind == 'real15':
        w = real_q
    else:
        Sr, Fr = spot_at(real_q, spots, sfeats)
        cal_mask = real_q.day < first_test - walk['embargo_days']
        params = calibrate(real_q, Sr, Fr['rv60'].astype(np.float64), cal_mask)
        log(f'synthetic pricer calibrated on {int(cal_mask.sum())} real windows before day {first_test}: lam {params["lam"]:.2f}, mse {params["mse"]:.4f}')
        if kind == 'synth15':
            w = price_windows(real_q, spots, Fr['rv60'].astype(np.float64), params)
            te = real_q.day >= first_test
            rm, sm = (real_q.bid + real_q.ask) / 2, (w.bid + w.ask) / 2
            ok = te[:, None] & np.isfinite(rm) & np.isfinite(sm)
            fidelity = dict(lam=params['lam'], mid_corr=round(float(np.corrcoef(rm[ok], sm[ok])[0, 1]), 4), mid_mae=round(float(np.mean(np.abs(rm[ok] - sm[ok]))), 4),
                            spread_real=round(float(np.nanmean((real_q.ask - real_q.bid)[te])), 4), spread_synth=round(float(np.nanmean((w.ask - w.bid)[te])), 4))
            log(f'synthetic vs real quotes on test days: {fidelity}')
        else:
            hw = hourly_windows(spots, real.assets, int(real_q.open_ms.min()), int(real_q.open_ms.max()), offsets=tuple(cfg['hourly_offsets']))
            _, Fh = spot_at(hw, spots, sfeats)
            w = price_windows(hw, spots, Fh['rv60'].astype(np.float64), params)
            fidelity = dict(lam=params['lam'], note='hourly windows are synthetic: strike = spot at the open, settled on the Binance close (Kalshi uses the CF index)')
            log(f'synthetic hourly windows: {len(w)}')
    N = w.n
    S, F = spot_at(w, spots, sfeats)
    X, names = window_features(w, S, F, cfg.get('extra_features'))
    state_names = names + STATE_EXTRA
    entry_names = names + ['entry_maker']
    bid, ask, nbl, nbh, nal, nah, settle = side_quotes(w)
    book_all = Book.build(bid, ask, nbl, nbh, nal, nah, settle, costs)
    days = w.day
    log(f'{len(w)} windows x 2 sides x {N} minutes, {len(names)} features, {len(folds_days)} folds; data ready in {time.time() - t_start:.0f} s')

    def sub_book(idx):
        return Book(book_all.bid[idx], book_all.ask[idx], book_all.fill_buy[idx], book_all.fill_sell[idx], book_all.settle[idx])

    entry_minutes = np.array(cfg['entry']['entry_minutes']) if cfg['entry'].get('entry_minutes') else None
    cuts = {'rv60': [float(x) for x in np.nanpercentile(F['rv60'][np.isin(days, folds_days[0][0])], [33.3, 66.7])]}
    folds = []
    shap_entry = shap_exit = []
    last_fold = len(folds_days) - 1
    for fi, (tr_days, te_days) in enumerate(folds_days):
        if fi % a.parts != a.part:
            continue
        t_f = time.time()
        rng = np.random.default_rng(17 + fi)
        tr_idx = np.nonzero(np.isin(days, tr_days))[0]
        te_idx = np.nonzero(np.isin(days, te_days))[0]
        if not len(te_idx) or not len(tr_idx):
            continue
        btr, bte = sub_book(tr_idx), sub_book(te_idx)
        Xtr, Xte = X[tr_idx], X[te_idx]
        ptr = build_positions(btr, costs, cfg['entry']['maker_entries'], entry_minutes)
        groups = (days[tr_idx] % 2).astype(np.int8)
        xr = solve_exits(btr, Xtr, ptr, costs, xcfg, groups=groups)
        pnl_tr = xr.pnl(ptr)
        att_tr = maker_attempts(btr.bid, N - 1) if cfg['entry']['maker_entries'] else None
        rows_tr = entry_rows(Xtr, ptr, pnl_tr, att_tr)
        del pnl_tr
        # Hurdle chosen on the last inner_days of the training span (purged), the entry model fitted on the rest.
        fit_d, val_d = inner_split(tr_days, walk['inner_days'], walk['embargo_days'])
        rday = days[tr_idx][rows_tr['w']]
        fsel = np.isin(rday, fit_d)
        vsel = np.isin(rday, val_d)

        def pick_hurdle(shuffle=None):
            if not vsel.any():
                return ecfg.hurdles[0], {}
            sub = {k: v[fsel] for k, v in rows_tr.items()}
            mdl = fit_entry(sub, ecfg, shuffle_rng=shuffle)
            vrows = {k: v[vsel] for k, v in rows_tr.items()}
            pv = mdl.predict(vrows['X'])
            scores = {}
            for h in ecfg.hurdles:
                ch = simulate(vrows, pv, h, entry_minutes)
                scores[h] = float(vrows['y'][ch].sum()) / (len(val_d) * 24)
            best = max(scores.items(), key=lambda kv: (kv[1], kv[0]))[0]
            return best, scores

        hurdle, val_scores = pick_hurdle()
        emodel = fit_entry(rows_tr, ecfg)
        # Out of sample: exits by the training span's models, entries by its entry model.
        pte = build_positions(bte, costs, cfg['entry']['maker_entries'], entry_minutes)
        xe = solve_exits(bte, Xte, pte, costs, xcfg, models=xr.models)
        pnl_te = xe.pnl(pte)
        att_te = maker_attempts(bte.bid, N - 1) if cfg['entry']['maker_entries'] else None
        rows_te = entry_rows(Xte, pte, pnl_te, att_te)
        pred = emodel.predict(rows_te['X'])
        chosen = simulate(rows_te, pred, hurdle, entry_minutes)
        n_hours = len(te_days) * 24
        t0 = int(te_days[0]) * 86_400_000
        wopen = w.open_ms[te_idx]
        hour_of = ((wopen[rows_te['w'][chosen]] - t0) // 3_600_000).astype(np.int64)
        y = rows_te['y'][chosen]
        series = np.bincount(np.clip(hour_of, 0, n_hours - 1), weights=y, minlength=n_hours)
        st = pnl_stats(y, n_hours)
        # Every possible taker position under the learned, naive and hindsight exits.
        tk = pte.mode == 0
        eq = {name: [float(np.nansum(v[tk])), int(np.isfinite(v[tk]).sum())]
              for name, v in (('policy', pnl_te), ('naive', xe.pnl(pte, 'naive')), ('oracle', xe.pnl(pte, 'oracle')))}
        # Placebo 1: random entries at the model's rate, exits by the policy.
        per_window = len(chosen) / max(1, len(te_idx))
        rp = random_entry_placebo(rows_te, per_window, rng, cfg['placebo']['random_draws'], len(te_idx)) / n_hours
        # Placebo 2: entry models fitted on permuted labels, same hurdle procedure.
        shuf = []
        for k_ in range(int(cfg['placebo']['shuffles'])):
            h_s, _ = pick_hurdle(shuffle=np.random.default_rng(100 + 10 * fi + k_))
            m_s = fit_entry(rows_tr, ecfg, shuffle_rng=np.random.default_rng(200 + 10 * fi + k_))
            ch_s = simulate(rows_te, m_s.predict(rows_te['X']), h_s, entry_minutes)
            shuf.append(float(rows_te['y'][ch_s].sum()) / n_hours)
        ci = chosen
        wi = rows_te['w'][ci]; si = rows_te['s'][ci]; ii = rows_te['i'][ci]
        side_price = np.where(si == 0, w.ask[te_idx][wi, ii], 1 - w.bid[te_idx][wi, ii])
        trades = dict(asset=w.asset[te_idx][wi].astype(int), side=si.astype(int), i=ii.astype(int), mode=rows_te['mode'][ci].astype(int),
                      pnl=y, rv60=F['rv60'][te_idx][wi, ii].astype(np.float64), tau_frac=(N - ii) / N, price=side_price,
                      day=days[te_idx][wi])
        folds.append(dict(fold=fi, train=[int(tr_days[0]), int(tr_days[-1])], test=[int(te_days[0]), int(te_days[-1])], hurdle=hurdle,
                          val_per_hour={str(k): round(v, 3) for k, v in val_scores.items()}, oos=st, n_hours=n_hours,
                          random_placebo=[round(float(x), 4) for x in rp], shuffled_per_hour=[round(x, 4) for x in shuf],
                          train_positions=len(ptr), test_positions=len(pte), seconds=round(time.time() - t_f),
                          hourly=[round(float(x), 4) for x in series], exit_quality=eq,
                          trades={k: [round(float(x), 5) if isinstance(x, (float, np.floating)) else int(x) for x in np.asarray(v).tolist()] for k, v in trades.items()}))
        log(f'fold {fi}: test {te_days[0]}..{te_days[-1]} hurdle {hurdle}: {st["trades"]} trades {st["per_hour"]:+.2f} $/h '
            f'(random {np.median(rp):+.2f}, shuffled {[round(x, 2) for x in shuf]}) [{time.time() - t_f:.0f} s]')
        if fi == last_fold:
            shap_entry = shap_top(emodel, rows_te['X'], entry_names)
            kmid = N // 2
            if kmid in xr.models:
                from .matrix import exit_taker
                from .snell import state_features
                alive = np.nonzero(pte.k0 <= kmid)[0][:50_000]
                aT = exit_taker(bte.bid[pte.w[alive], pte.s[alive], kmid], pte.C[alive], costs)
                Z = state_features(Xte, pte, alive, kmid, aT)
                shap_exit = shap_top(xr.models[kmid][0][0], Z, state_names, top=8)
        del xr, xe, rows_tr, rows_te, ptr, pte
    part = dict(arm=a.arm, kind=kind, name=cfg.get('name', 'base'), config_hash=config_hash(cfg), config=cfg, assets=w.assets,
                excluded_assets=sorted(EXCLUDED_ASSETS), windows=len(w), n=N, n_folds=len(folds_days), part=a.part, parts=a.parts,
                folds=folds, cuts=cuts, shap_entry=shap_entry, shap_exit_hold=shap_exit, fidelity=fidelity,
                trials_this_arm=len(ecfg.hurdles), seconds=round(time.time() - t_start))
    result = aggregate([part]) if a.parts == 1 else part
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, 'w') as fh:
        json.dump(result, fh, default=lambda o: o.tolist() if hasattr(o, 'tolist') else str(o))
    try:
        import resource
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    except Exception:
        rss = float('nan')
    log(f'{a.arm} part {a.part}/{a.parts}: {len(folds)} fold(s) written to {a.out}; {time.time() - t_start:.0f} s, peak memory {rss:.0f} MB')
    return result


def aggregate(parts: list[dict]) -> dict:
    """One arm's result from its parts (each a subset of the walk-forward folds)."""
    p0 = parts[0]
    folds = sorted([f for p in parts for f in p['folds']], key=lambda f: f['fold'])
    hourly = np.concatenate([np.array(f['hourly'], dtype=np.float64) for f in folds]) if folds else np.zeros(0)
    total_hours = len(hourly)
    tr = {k: np.concatenate([np.array(f['trades'][k]) for f in folds]) for k in folds[0]['trades']} if folds else {}
    pnl = tr.get('pnl', np.zeros(0)).astype(np.float64)
    oos = pnl_stats(pnl, total_hours)
    daily = hourly[: (len(hourly) // 24) * 24].reshape(-1, 24).sum(axis=1) if len(hourly) >= 24 else hourly
    ci_lo, ci_hi = block_bootstrap_mean(hourly, block=24)
    sr_h = float(np.mean(hourly) / np.std(hourly, ddof=1)) if len(hourly) > 1 and np.std(hourly) > 0 else 0.0
    wts = np.array([f['n_hours'] for f in folds], dtype=np.float64)
    rp = [np.array(f['random_placebo']) for f in folds]
    placebo_rand = (np.stack(rp) * wts[:, None]).sum(axis=0) / max(1, total_hours) if rp and len({len(x) for x in rp}) == 1 and len(rp[0]) else np.zeros(0)
    sh = [f['shuffled_per_hour'] for f in folds]
    shuf_tot = (np.array(sh) * wts[:, None]).sum(axis=0) / max(1, total_hours) if sh and all(len(x) for x in sh) and len({len(x) for x in sh}) == 1 else None
    clusters, by_asset, by_minute, by_mode, by_side = [], {}, {}, {}, {}
    if len(pnl):
        tags = np.array(regime_tags(tr, {'rv60': np.array(p0['cuts']['rv60'])}))
        for tag in np.unique(tags):
            sel = tags == tag
            clusters.append(dict(cluster=str(tag), n=int(sel.sum()), total=round(float(pnl[sel].sum()), 2), avg=round(float(pnl[sel].mean()), 3)))
        clusters.sort(key=lambda c: c['total'])
        for key, dst, lab in (('asset', by_asset, lambda v: p0['assets'][v]), ('i', by_minute, str), ('mode', by_mode, lambda v: ['taker', 'maker'][v]),
                              ('side', by_side, lambda v: ['YES', 'NO'][v])):
            for v in np.unique(tr[key]):
                sel = tr[key] == v
                dst[lab(int(v))] = dict(n=int(sel.sum()), per_hour=round(float(pnl[sel].sum()) / total_hours, 3), avg=round(float(pnl[sel].mean()), 3))
    eq = {}
    for name in ('policy', 'naive', 'oracle'):
        s_ = sum(f['exit_quality'][name][0] for f in folds)
        n_ = sum(f['exit_quality'][name][1] for f in folds)
        eq[name] = round(s_ / n_, 4) if n_ else None
    shap_e = next((p['shap_entry'] for p in parts if p.get('shap_entry')), [])
    shap_x = next((p['shap_exit_hold'] for p in parts if p.get('shap_exit_hold')), [])
    slim = [{k: v for k, v in f.items() if k not in ('hourly', 'trades', 'random_placebo')} | {'random_placebo_median': round(float(np.median(f['random_placebo'])), 3) if f['random_placebo'] else None}
            for f in folds]
    return dict(
        arm=p0['arm'], kind=p0['kind'], name=p0['name'], config_hash=p0['config_hash'], config=p0['config'], assets=p0['assets'],
        excluded_assets=p0['excluded_assets'], windows=p0['windows'], n=p0['n'], folds=slim, folds_expected=p0['n_folds'],
        oos=dict(oos, hours=total_hours, per_hour_ci95=[round(ci_lo, 3), round(ci_hi, 3)], sr_hourly=round(sr_h, 4), psr0=round(psr(hourly), 4),
                 days=int(len(daily)), losing_days=int(np.sum(daily < 0)), worst_day=round(float(daily.min()), 2) if len(daily) else 0.0,
                 best_day=round(float(daily.max()), 2) if len(daily) else 0.0),
        target_per_hour=4.5,
        placebo=dict(random_per_hour_median=round(float(np.median(placebo_rand)), 3) if len(placebo_rand) else None,
                     random_per_hour_p95=round(float(np.percentile(placebo_rand, 95)), 3) if len(placebo_rand) else None,
                     shuffled_per_hour=[round(float(x), 3) for x in shuf_tot] if shuf_tot is not None else None),
        exit_quality_per_position=eq, by_asset=by_asset, by_entry_minute=by_minute, by_mode=by_mode, by_side=by_side,
        losing_clusters=clusters[:3], winning_clusters=clusters[::-1][:3],
        shap_entry=shap_e, shap_exit_hold=shap_x, hourly_pnl=[round(float(x), 3) for x in hourly], fidelity=p0.get('fidelity'),
        trials_this_arm=p0['trials_this_arm'], seconds=sum(p.get('seconds', 0) for p in parts), parts=len(parts),
    )


def combine(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--parts', required=True, help='directory with the part files of one or more arms')
    ap.add_argument('--out', required=True, help='directory for one <arm>.json per arm')
    a = ap.parse_args(argv)
    import glob
    by_arm: dict[str, list] = {}
    for f in sorted(glob.glob(os.path.join(a.parts, '**', '*.json'), recursive=True)):
        try:
            r = json.load(open(f))
        except Exception:
            continue
        if isinstance(r, dict) and 'arm' in r and 'part' in r and 'folds' in r:
            by_arm.setdefault(r['arm'], []).append(r)
    os.makedirs(a.out, exist_ok=True)
    for arm, parts in by_arm.items():
        got = sorted(p['part'] for p in parts)
        res = aggregate(parts)
        res['parts_missing'] = sorted(set(range(parts[0]['parts'])) - set(got))
        with open(os.path.join(a.out, f'{arm}.json'), 'w') as fh:
            json.dump(res, fh)
        o = res['oos']
        log(f'{arm}: {len(res["folds"])}/{res["folds_expected"]} folds, OOS {o["per_hour"]:+.3f} $/h over {o["hours"]} h ({o["trades"]} trades), '
            f'CI95 {o["per_hour_ci95"]}, placebo {res["placebo"]}')


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'combine':
        combine(sys.argv[2:])
    else:
        sys.exit(0 if main() else 1)
