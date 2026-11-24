"""The AP-H1b and AP-H2 readout of a follow-up run (prereg/AP-H1b.md with Amendment 1, prereg/AP-H2.md).

    python -m allpairs.aph --results <this run's results> --ref <run 42127527423's results> --ref-run 42127527423
                           [--skill skill.json] --out <dir>

It reads the combined arm results (<config>/<arm>.json with heldout.json, after allpairs.ho1) of the follow-up run and
of the reference run, and writes aph.md (appended to the card) and aph.json. Its steps:
- Reproduction check: maker_only base and tight must equal the reference run exactly ($/h, trades, fold $/h, hourly
  P&L). If they don't, every quantity below is VOID.
- AP-H2: T, T_s, the artefact share, the folds kept, D with its block-bootstrap CI, the decision and the mechanism
  readouts.
- AP-H1b: G_base, P (P3) and P2b (from the skill job). P2a is read elsewhere (the SNN thread's H-B job).
- Multiple testing: the BHY-adjusted p of every arm of the reference run (one-sided, mean daily P&L > 0,
  Newey-West t).
"""
from __future__ import annotations

import argparse
import json
import math
import os

import numpy as np

from .ho1 import verdict as ho1_verdict

NOISE = 0.92          # $/h, AP-H1b's noise unit (2x noise, institutional diagnosis)
NW_LAG = 3


def load(results_dir: str) -> dict:
    """{config: {'arms': {arm: result}, 'heldout': {arm: block}}} from a combined results directory."""
    out = {}
    if not results_dir or not os.path.isdir(results_dir):
        return out
    for cfg in sorted(os.listdir(results_dir)):
        d = os.path.join(results_dir, cfg)
        if not os.path.isdir(d):
            continue
        arms = {}
        for f in sorted(os.listdir(d)):
            if f.endswith('.json') and f not in ('heldout.json', 'gate.json'):
                try:
                    r = json.load(open(os.path.join(d, f)))
                except (OSError, ValueError):
                    continue
                if isinstance(r, dict) and r.get('arm') == f[:-5] and 'oos' in r:
                    arms[r['arm']] = r
        ho = os.path.join(d, 'heldout.json')
        out[cfg] = dict(arms=arms, heldout=json.load(open(ho)) if os.path.exists(ho) else {})
    return out


def arm(runs: dict, cfg: str, name: str):
    return (runs.get(cfg) or {}).get('arms', {}).get(name)


def block_of(runs: dict, cfg: str, name: str):
    return (runs.get(cfg) or {}).get('heldout', {}).get(name)


def fold_ph(r: dict) -> list:
    return [round(float(f['oos']['per_hour']), 4) for f in r.get('folds', [])]


def reproduces(new: dict, ref: dict) -> tuple:
    """(same, differences) of two results of one arm: $/h, trades, fold $/h, hourly P&L."""
    if not new or not ref:
        return False, ['missing in ' + ('this run' if not new else 'the reference run')]
    why = []
    for k in ('per_hour', 'trades', 'pnl'):
        if new['oos'].get(k) != ref['oos'].get(k):
            why.append(f'{k} {new["oos"].get(k)} vs {ref["oos"].get(k)}')
    if fold_ph(new) != fold_ph(ref):
        why.append(f'fold $/h {fold_ph(new)} vs {fold_ph(ref)}')
    if new.get('hourly_pnl') != ref.get('hourly_pnl'):
        why.append('hourly P&L differs')
    if new.get('config_hash') != ref.get('config_hash'):
        why.append(f'config hash {new.get("config_hash")} vs {ref.get("config_hash")}')
    return not why, why


def bootstrap_ci(x: np.ndarray, levels=(0.90, 0.95), block: int = 24, draws: int = 2000, seed: int = 3) -> dict:
    """Moving-block bootstrap intervals of the mean (validate.block_bootstrap_mean's draws; several levels)."""
    x = np.asarray(x, dtype=np.float64)
    n = len(x)
    if n < 2:
        return {lv: (float('nan'), float('nan')) for lv in levels}
    rng = np.random.default_rng(seed)
    b = max(1, min(block, n))
    nb = int(math.ceil(n / b))
    starts = rng.integers(0, n - b + 1, size=(draws, nb))
    idx = (starts[:, :, None] + np.arange(b)[None, None, :]).reshape(draws, -1)[:, :n]
    means = x[idx].mean(axis=1)
    return {lv: (float(np.percentile(means, 50 * (1 - lv))), float(np.percentile(means, 100 - 50 * (1 - lv)))) for lv in levels}


def _ncdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def daily_p(hourly: list, lag: int = NW_LAG) -> float:
    """One-sided p of mean daily P&L > 0 from a Newey-West t (Bartlett, `lag` days). No trades or no variance: 1."""
    h = np.asarray(hourly or [], dtype=np.float64)
    d = h[: (len(h) // 24) * 24].reshape(-1, 24).sum(axis=1)
    n = len(d)
    if n < 3 or not np.any(d != 0):
        return 1.0
    u = d - d.mean()
    s = float(np.dot(u, u)) / n
    for l_ in range(1, min(lag, n - 1) + 1):
        s += 2 * (1 - l_ / (lag + 1)) * float(np.dot(u[l_:], u[:-l_])) / n
    if s <= 0:
        return 1.0
    t = float(d.mean()) / math.sqrt(s / n)
    return 1 - _ncdf(t)


def bhy(p: list) -> list:
    """Benjamini-Hochberg-Yekutieli adjusted p values (any dependence), in the input order."""
    p = np.asarray(p, dtype=np.float64)
    m = len(p)
    if not m:
        return []
    c = float(np.sum(1.0 / np.arange(1, m + 1)))
    order = np.argsort(p)
    adj = np.empty(m)
    run_min = 1.0
    for rank in range(m, 0, -1):
        i = order[rank - 1]
        run_min = min(run_min, p[i] * m * c / rank)
        adj[i] = min(1.0, run_min)
    return [round(float(x), 4) for x in adj]


def ap_h2(new: dict) -> dict:
    """AP-H2's decision from this run's maker_only tight and tight_strict (prereg/AP-H2.md)."""
    t, ts = arm(new, 'maker_only', 'tight'), arm(new, 'maker_only', 'tight_strict')
    if not t or not ts:
        return dict(verdict='not scored: maker_only tight or tight_strict missing')
    T, Ts = float(t['oos']['per_hour']), float(ts['oos']['per_hour'])
    fts = fold_ph(ts)
    kept = sum(x > 0 for x in fts)
    share = (T - Ts) / T if T > 0 else None
    if T <= 0:
        v = 'moot: T is not above 0 in this run'
    elif Ts <= 0 or (share is not None and share >= 0.5):
        v = 'supported: the gain is the candle-touch fill' + (' (T_s <= 0)' if Ts <= 0 else f' (artefact share {share:.0%})')
    elif Ts > 0.5 * T and kept >= 4:
        v = f'falsified: tight_strict keeps {Ts / T:.0%} of the gain and is above 0 in {kept}/6 folds'
    else:
        v = f'inconclusive: tight_strict keeps {Ts / T:.0%} of the gain, above 0 in {kept}/6 folds'
    d = np.asarray(t.get('hourly_pnl') or [], dtype=np.float64)
    e = np.asarray(ts.get('hourly_pnl') or [], dtype=np.float64)
    ci = bootstrap_ci(d - e)[0.95] if len(d) == len(e) and len(d) else (float('nan'), float('nan'))
    bt = block_of(new, 'maker_only', 'tight_strict')
    ho = ho1_verdict(bt) if bt else (None, ['no HO-1 block'])
    mt = (t.get('by_mode') or {}).get('maker', {}).get('n', 0)
    ms = (ts.get('by_mode') or {}).get('maker', {}).get('n', 0)
    return dict(T=T, T_s=Ts, artefact_share=round(share, 4) if share is not None else None, folds_kept=kept, fold_per_hour_strict=fts,
                D=round(T - Ts, 4), D_ci95=[round(ci[0], 4), round(ci[1], 4)], verdict=v,
                tight_strict_ho1=dict(passes=ho[0], why=ho[1]),
                fill_ratio_arms=round(ms / mt, 4) if mt else None,
                strict_fill_share_tight=t.get('strict_fill_share'),
                markout=dict(tight=t.get('markout'), tight_strict=ts.get('markout')),
                markout_mid=dict(tight=t.get('markout_mid'), tight_strict=ts.get('markout_mid')),
                concentration=dict(tight=t.get('concentration'), tight_strict=ts.get('concentration')),
                by_side_price=dict(tight=t.get('by_side_price'), tight_strict=ts.get('by_side_price')),
                by_spread=dict(tight=t.get('by_spread'), tight_strict=ts.get('by_spread')),
                by_tier=dict(tight=t.get('by_tier'), tight_strict=ts.get('by_tier')))


def ap_h1b(new: dict, ref: dict, skill: dict | None) -> dict:
    lb, kc = arm(ref, 'lead_btc', 'base'), arm(ref, 'base', 'base')
    g = round(float(lb['oos']['per_hour']) - float(kc['oos']['per_hour']), 4) if lb and kc else None
    out = dict(G_base=g, P1='moot: G_base <= 0 (no gain to explain)' if g is not None and g <= 0 else 'see the pre-registration')
    sh = arm(new, 'lead_shift24', 'base')
    if lb and sh:
        a = np.asarray(lb.get('hourly_pnl') or [], dtype=np.float64)
        b = np.asarray(sh.get('hourly_pnl') or [], dtype=np.float64)
        if len(a) == len(b) and len(a):
            P = float(a.mean() - b.mean())
            ci = bootstrap_ci(a - b)
            lo90, hi90 = ci[0.90]
            lo95, hi95 = ci[0.95]
            if P > NOISE and lo95 > 0:
                v = 'falsifier: P > $0.92/h with its 95% CI above 0'
            elif lo90 > -NOISE and hi90 < NOISE:
                v = 'holds: P within +/-$0.92/h (90% CI inside the band)'
            else:
                v = 'undecided: the 90% CI leaves the +/-$0.92/h band'
            out['P3'] = dict(P=round(P, 4), ci90=[round(lo90, 4), round(hi90, 4)], ci95=[round(lo95, 4), round(hi95, 4)],
                             lead_shift24_per_hour=sh['oos']['per_hour'], lead_shift24_trades=sh['oos']['trades'], verdict=v)
        else:
            out['P3'] = dict(verdict=f'not scored: hour grids differ ({len(a)} vs {len(b)})')
    else:
        out['P3'] = dict(verdict='not scored: lead_btc (reference) or lead_shift24 base missing')
    out['P2b'] = skill.get('tight') | {'verdict': skill.get('p2b')} if skill and skill.get('tight') else dict(verdict='not scored: no skill result')
    out['P2a'] = 'read from the SNN thread\'s H-B mid-response job (not this run)'
    return out


def multiple_testing(ref: dict) -> list:
    rows = []
    for cfg, g in sorted(ref.items()):
        for name, r in sorted(g['arms'].items()):
            if r.get('protocol') != 'ho1':
                continue
            b = g['heldout'].get(name)
            rows.append(dict(config=cfg, arm=name, per_hour=r['oos']['per_hour'], trades=r['oos']['trades'],
                             ho1_pass=bool(b and ho1_verdict(b)[0]), p=round(daily_p(r.get('hourly_pnl')), 4)))
    for row, a in zip(rows, bhy([r_['p'] for r_ in rows])):
        row['p_bhy'] = a
    return rows


def card(res: dict) -> str:
    L = [f'## AP-H1b and AP-H2 follow-up (reference run {res["ref_run"]})', '']
    rp = res['reproduction']
    L.append('Reproduction of the reference run: ' + '; '.join(f'maker_only {k} {"exact" if v["same"] else "DIFFERS: " + ", ".join(v["why"])}'
                                                              for k, v in rp.items()) + '.')
    if res['void']:
        L.append('**VOID**: the reproduction check failed, so no quantity below is evidence (prereg/AP-H2.md).')
    h2 = res['ap_h2']
    L.append('')
    if 'T' in h2:
        L.append(f'**AP-H2** (maker_only, 10c cap): T {h2["T"]:+.2f} $/h, T_s (strict fills) {h2["T_s"]:+.2f} $/h, artefact share '
                 f'{h2["artefact_share"] if h2["artefact_share"] is None else format(h2["artefact_share"], ".0%")}, tight_strict above 0 in '
                 f'{h2["folds_kept"]}/6 folds {h2["fold_per_hour_strict"]}, D {h2["D"]:+.2f} $/h CI95 {h2["D_ci95"]}. '
                 f'Verdict: {h2["verdict"]}. tight_strict HO-1: {"PASS" if h2["tight_strict_ho1"]["passes"] else "fails"}'
                 + ('' if h2['tight_strict_ho1']['passes'] else f' ({"; ".join(h2["tight_strict_ho1"]["why"])})') + '.')
        L.append(f'Fill-count ratio, strict over touch: {h2["fill_ratio_arms"]} (maker fills of tight_strict / tight); share of tight\'s '
                 f'maker entries the strict rule also fills {h2["strict_fill_share_tight"]}. Markouts per fill ($ per contract): '
                 f'{json.dumps(h2["markout"])}.')
        L.append(f'By side and price paid ($/h, trades): {json.dumps(h2["by_side_price"])}.')
        L.append(f'Mid-to-mid markouts from the fill ($ per contract; edge_at_fill = mid at the fill minus price paid): '
                 f'{json.dumps(h2["markout_mid"])}. Concentration: {json.dumps(h2["concentration"])}.')
    else:
        L.append(f'**AP-H2**: {h2["verdict"]}.')
    h1 = res['ap_h1b']
    L.append('')
    L.append(f'**AP-H1b**: G_base {h1["G_base"]} $/h, so P1 is {h1["P1"]}. P3 (lead_btc minus lead_shift24): {json.dumps(h1["P3"])}. '
             f'P2b (settlement skill on tight books): {json.dumps(h1["P2b"])}. P2a: {h1["P2a"]}.')
    L.append('')
    L.append(f'Multiple testing over the {len(res["bhy"])} HO-1 arms of run {res["ref_run"]} (one-sided p of mean daily P&L > 0, '
             'Newey-West lag 3; BHY-adjusted): ' + '; '.join(f'{r["config"]}:{r["arm"]} {r["per_hour"]:+.2f} p {r["p"]} BHY {r["p_bhy"]}'
                                                           + (' (HO-1 pass)' if r['ho1_pass'] else '') for r in res['bhy']) + '.')
    return '\n'.join(L) + '\n'


def run(results: str, ref_dir: str, ref_run: str, skill_path: str | None, out_dir: str) -> dict:
    new, ref = load(results), load(ref_dir)
    skill = json.load(open(skill_path)) if skill_path and os.path.exists(skill_path) else None
    rp = {}
    for name in ('base', 'tight'):
        same, why = reproduces(arm(new, 'maker_only', name), arm(ref, 'maker_only', name))
        rp[name] = dict(same=same, why=why)
    res = dict(ref_run=ref_run, reproduction=rp, void=not all(v['same'] for v in rp.values()),
               ap_h2=ap_h2(new), ap_h1b=ap_h1b(new, ref, skill), bhy=multiple_testing(ref))
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, 'aph.json'), 'w') as fh:
        json.dump(res, fh, indent=1)
    md = card(res)
    with open(os.path.join(out_dir, 'aph.md'), 'w') as fh:
        fh.write(md)
    print(md)
    return res


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--results', required=True)
    ap.add_argument('--ref', required=True)
    ap.add_argument('--ref-run', required=True)
    ap.add_argument('--skill', default=None)
    ap.add_argument('--out', required=True)
    a = ap.parse_args(argv)
    run(a.results, a.ref, a.ref_run, a.skill, a.out)


if __name__ == '__main__':
    main()
