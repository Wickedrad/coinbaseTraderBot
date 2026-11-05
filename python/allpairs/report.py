"""The Diagnostic Summary Card and the gate: combines the arms of one run, the trial ledger and the champion.

    python -m allpairs.report --results out/ --ledger drive/trials.jsonl --champion drive/champion.json --card card.md

A candidate (the base arm of its configuration) replaces the champion only if ALL hold:
  0. every walk-forward fold of the base and stress arms was scored, and random entries lose money (the data canary);
  1. out-of-sample $/h >= the $4.50/h target, and the 95% block-bootstrap interval of the hourly mean is above 0;
  2. deflated Sharpe >= 0.95, deflated by every configuration scored before it (the ledger's base rows, one per run);
  3. it beats its placebos: above every shuffled-label refit and the 95th percentile of random entries;
  4. it stays profitable in the stress arm (a cent worse on every taker leg, the maker fee charged, strict maker fills);
  5. it beats the champion's out-of-sample $/h.
Synthetic arms (synth15, synth1h) are reported, never gated. A failing candidate is not benched: the card lists what
lost (regime clusters, exits against hindsight) for the next hypothesis.
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os

import numpy as np

from .validate import dsr

TARGET = 4.5
PRIOR_SR_VAR = 0.05 ** 2   # until the ledger holds 3+ Sharpes: the spread of hourly Sharpes between configurations


def _day(d: int) -> str:
    return (dt.date(1970, 1, 1) + dt.timedelta(days=int(d))).isoformat()


def _now_both() -> str:
    now = dt.datetime.now(dt.timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        et = now.astimezone(ZoneInfo('America/New_York'))
        label = et.tzname() or 'ET'
    except Exception:
        et, label = now - dt.timedelta(hours=5), 'EST'
    return f'{et.strftime("%-I:%M %p")} {label} ({now.strftime("%Y-%m-%d %H:%M")} UTC)'


def load_results(d: str) -> dict:
    out = {}
    for f in sorted(glob.glob(os.path.join(d, '**', '*.json'), recursive=True)):
        try:
            r = json.load(open(f))
        except Exception:
            continue
        if isinstance(r, dict) and 'arm' in r and 'oos' in r:
            out[r['arm']] = r
    return out


def prior_trials(ledger: list, run: str = '', config_hash: str = '', test=None, sr=None) -> list:
    """The configurations scored out of sample before this one: base-arm rows only (the stress arm is the same
    configuration under worse costs, not another trial), one per scoring (rows with the same configuration, test span
    and Sharpe are one scoring however many report reruns wrote them), the candidate's own scoring left out. The hurdle
    grid is not counted: the hurdle is chosen on inner validation days, never on the out-of-sample result."""
    def content(t):
        return (str(t.get('config_hash', '')), tuple(t.get('test') or ()), round(float(t['sr_hourly']), 9))
    me = (str(config_hash), tuple(test or ()), round(float(sr), 9)) if sr is not None else None
    seen = {}
    for t in ledger:
        if t.get('arm', 'base') != 'base' or t.get('sr_hourly') is None:
            continue
        if (run and (str(t.get('run', '')), str(t.get('config_hash', ''))) == (str(run), str(config_hash))) or content(t) == me:
            continue
        seen[content(t)] = t
    return list(seen.values())


def gate(arms: dict, ledger: list, champion: dict | None, run: str = '') -> dict:
    base = arms.get('base')
    if not base:
        return dict(passed=False, reasons=['no base arm'])
    hourly = np.array(base['hourly_pnl'], dtype=np.float64)
    folds = base.get('folds', [])
    span = [folds[0]['test'][0], folds[-1]['test'][1]] if folds else None
    prior = prior_trials(ledger, run, base.get('config_hash', ''), span, base['oos'].get('sr_hourly'))
    srs = [float(t['sr_hourly']) for t in prior]
    sr_var = float(np.var(srs, ddof=1)) if len(srs) >= 3 else PRIOR_SR_VAR
    n_trials = len(prior) + 1
    d = dsr(hourly, max(n_trials, 1), sr_var)
    o = base['oos']
    pl = arms.get('placebo', {}).get('placebo') or base.get('placebo') or {}
    shuffled = pl.get('shuffled_per_hour') or []
    rand95 = pl.get('random_per_hour_p95')
    stress = arms.get('stress', {}).get('oos', {}).get('per_hour')
    folds = base.get('folds', [])
    suspect = [f for f in folds if (f.get('random_placebo_median') or 0) > 0]
    missing = {name: dict(parts_missing=r.get('parts_missing') or [], folds=len(r.get('folds', [])), folds_expected=r.get('folds_expected'))
               for name, r in arms.items()
               if r.get('parts_missing') or (r.get('folds_expected') is not None and len(r.get('folds', [])) < r['folds_expected'])}
    checks = {
        # Every fold of the gated arms scored: a missing part would score a cherry-picked subset of the history.
        'complete': not any(k in missing for k in ('base', 'stress')),
        # Canary: random entries must lose money after fees and spread; a fold where they win has broken data.
        'random_entries_lose': not suspect and (pl.get('random_per_hour_median') is None or pl['random_per_hour_median'] <= 0),
        'target': o['per_hour'] >= TARGET,
        'ci_above_zero': o['per_hour_ci95'][0] > 0,
        'dsr': d['dsr'] >= 0.95,
        'beats_shuffled': bool(shuffled) and o['per_hour'] > max(shuffled),
        'beats_random_p95': rand95 is not None and o['per_hour'] > rand95,
        'stress_profitable': stress is not None and stress > 0,
        'beats_champion': champion is None or o['per_hour'] > float(champion.get('per_hour', -1e9)),
    }
    return dict(passed=all(checks.values()), checks=checks, dsr=d, n_trials=n_trials, sr_var=sr_var, incomplete=missing,
                suspect_folds=[[f['test'][0], f['test'][1], f.get('random_placebo_median')] for f in suspect])


def card(arms: dict, g: dict, champion: dict | None, run_url: str = '') -> str:
    base = arms.get('base', {})
    o = base.get('oos', {})
    L = []
    folds = base.get('folds', [])
    span = f'{_day(folds[0]["test"][0])} to {_day(folds[-1]["test"][1])}' if folds else '?'
    L.append(f'## All-pairs payoff matrix: {base.get("name", "?")} ({base.get("config_hash", "?")})')
    if base.get('config', {}).get('notes'):
        L.append(f'Hypothesis: {base["config"]["notes"]}')
    L.append(f'Generated {_now_both()}{f" | [run]({run_url})" if run_url else ""}. Assets {", ".join(base.get("assets", []))} (DOGE excluded). '
             f'Out-of-sample days {span} ({o.get("days", 0)} days, {len(folds)} purged walk-forward folds).')
    L.append('')
    verdict = 'PASSES the gate: new champion' if g.get('passed') else 'does not pass the gate yet (champion unchanged)'
    L.append(f'**Out of sample: {o.get("per_hour", 0):+.2f} $/h against the $4.50/h target**, {o.get("trades", 0)} trades, 95% CI '
             f'[{o.get("per_hour_ci95", [0, 0])[0]:+.2f}, {o.get("per_hour_ci95", [0, 0])[1]:+.2f}] $/h, losing days {o.get("losing_days", 0)}/{o.get("days", 0)}. '
             f'Verdict: {verdict}.')
    L.append('')
    L.append('| Arm | $/h OOS | Trades | CI95 | Note |')
    L.append('|---|---|---|---|---|')
    notes = {'base': 'real 15m Kalshi quotes', 'stress': '+1c every taker leg, maker fee, strict maker fills', 'placebo': 'same + shuffled-label refits',
             'synth15': 'real windows, synthetic quotes (pricer fidelity)', 'synth1h': 'synthetic hourly (not gated)'}
    for name in ('base', 'stress', 'placebo', 'synth15', 'synth1h'):
        r = arms.get(name)
        if not r:
            continue
        ro = r['oos']
        extra = ''
        if name == 'placebo' and r.get('placebo', {}).get('shuffled_per_hour') is not None:
            extra = f'; shuffled {r["placebo"]["shuffled_per_hour"]}'
        if r.get('fidelity') and name == 'synth15':
            f = r['fidelity']
            extra = f'; mid corr {f.get("mid_corr")}, MAE {f.get("mid_mae")}, spread real {f.get("spread_real")} vs {f.get("spread_synth")}'
        L.append(f'| {name} | {ro["per_hour"]:+.2f} | {ro["trades"]} | [{ro["per_hour_ci95"][0]:+.2f}, {ro["per_hour_ci95"][1]:+.2f}] | {notes[name]}{extra} |')
    pl = base.get('placebo', {})
    L.append('')
    L.append(f'Random entries at the same rate (exits by the policy): median {pl.get("random_per_hour_median")} $/h, 95th pct {pl.get("random_per_hour_p95")} $/h.')
    eq = base.get('exit_quality_per_position', {})
    if eq:
        L.append(f'Exit policy per possible taker position: learned {eq.get("policy")} $, naive hold-then-forced {eq.get("naive")} $, '
                 f'perfect hindsight {eq.get("oracle")} $ (hindsight is an upper bound, never a label).')
    if g.get('checks'):
        d = g['dsr']
        L.append('')
        L.append(f'Gate: ' + ', '.join(f'{k} {"✓" if v else "✗"}' for k, v in g['checks'].items()) +
                 f'. Deflated Sharpe {d["dsr"]} (hourly SR {d["sr"]} vs {d["sr0"]} expected max of {d["n_trials"]} trials).')
    if g.get('incomplete'):
        L.append('**INCOMPLETE**: ' + '; '.join(f'{k} has {v["folds"]}/{v["folds_expected"]} folds'
                                                 + (f', parts missing {v["parts_missing"]}' if v['parts_missing'] else '')
                                                 for k, v in g['incomplete'].items()) + '.')
    if g.get('suspect_folds'):
        L.append(f'**DATA SUSPECT**: random entries made money in {len(g["suspect_folds"])} fold(s) ' +
                 ', '.join(f'{_day(a)}..{_day(b)} ({m:+.2f} $/h)' for a, b, m in g['suspect_folds']) + ': those results are not evidence.')
    if champion:
        L.append(f'Champion: {champion.get("name")} ({champion.get("config_hash")}) at {champion.get("per_hour")} $/h.')
    for title, key in (('By asset', 'by_asset'), ('By entry mode', 'by_mode'), ('By side', 'by_side')):
        v = base.get(key) or {}
        if v:
            L.append(f'{title}: ' + '; '.join(f'{k} {x["per_hour"]:+.2f} $/h ({x["n"]})' for k, x in v.items()) + '.')
    bm = base.get('by_entry_minute') or {}
    if bm:
        L.append('By entry minute: ' + ', '.join(f'{k}: {x["per_hour"]:+.2f}' for k, x in sorted(bm.items(), key=lambda kv: int(kv[0]))) + ' $/h.')
    L.append('')
    L.append('Top losing regime clusters (volatility | entry time | side and price):')
    for c in base.get('losing_clusters', []):
        L.append(f'- {c["cluster"]}: {c["n"]} trades, {c["total"]:+.2f} $ total, {c["avg"]:+.3f} $ each')
    L.append('Top winning clusters: ' + '; '.join(f'{c["cluster"]} {c["total"]:+.2f} $ ({c["n"]})' for c in base.get('winning_clusters', [])))
    if base.get('shap_entry'):
        L.append('')
        L.append('Entry model, mean |SHAP| ($): ' + ', '.join(f'{n} {v}' for n, v in base['shap_entry']))
    if base.get('shap_exit_hold'):
        L.append('Exit hold-value model (mid-window), mean |SHAP|: ' + ', '.join(f'{n} {v}' for n, v in base['shap_exit_hold']))
    L.append('')
    L.append('Fold detail: ' + '; '.join(f'{_day(f["test"][0])}..{_day(f["test"][1])} hurdle {f["hurdle"] if f["hurdle"] < 1e8 else "off"} '
                                       f'{f["oos"]["per_hour"]:+.2f} $/h' for f in folds))
    return '\n'.join(L)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--results', required=True)
    ap.add_argument('--ledger', required=True, help='trials.jsonl (read and appended)')
    ap.add_argument('--champion', required=True, help='champion.json (read, replaced when the gate passes)')
    ap.add_argument('--card', required=True)
    ap.add_argument('--run-url', default='')
    ap.add_argument('--run-id', default='', help='the run that scored the parts (not a report-only rerun)')
    a = ap.parse_args(argv)
    arms = load_results(a.results)
    ledger = []
    if os.path.exists(a.ledger):
        for line in open(a.ledger):
            try:
                ledger.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    champion = json.load(open(a.champion)) if os.path.exists(a.champion) else None
    g = gate(arms, ledger, champion, a.run_id)
    text = card(arms, g, champion, a.run_url)
    with open(a.card, 'w') as fh:
        fh.write(text + '\n')
    print(text)
    base = arms.get('base')
    if base:
        now = dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%MZ')
        have = {(str(t.get('run', '')), t.get('arm'), t.get('config_hash')) for t in ledger}
        with open(a.ledger, 'a') as fh:
            for name, r in arms.items():
                # A report-only rerun of the same run's parts does not score anything new: no second ledger row.
                if name in ('base', 'stress') and (str(a.run_id), name, r.get('config_hash')) not in have:
                    fh.write(json.dumps(dict(at=now, run=a.run_id, arm=name, name=r.get('name'), config_hash=r.get('config_hash'), per_hour=r['oos']['per_hour'],
                                             sr_hourly=r['oos'].get('sr_hourly'), trials=r.get('trials_this_arm', 1),
                                             test=[r['folds'][0]['test'][0], r['folds'][-1]['test'][1]] if r.get('folds') else None)) + '\n')
        if g.get('passed'):
            with open(a.champion, 'w') as fh:
                json.dump(dict(name=base.get('name'), config_hash=base.get('config_hash'), per_hour=base['oos']['per_hour'], run=a.run_id,
                               at=now, config=base.get('config')), fh, indent=1)
    with open(os.path.join(os.path.dirname(os.path.abspath(a.card)), 'gate.json'), 'w') as fh:
        json.dump(g, fh, default=str)


if __name__ == '__main__':
    main()
