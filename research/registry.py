#!/usr/bin/env python3
"""Trial registry: every replay/sweep arm any thread runs, in one place, so a gain is judged against how many tries it
took (institutional-methods proposal, Nov 5).

Layout on Drive (gdrive:kalshi-bot-archive/registry/):
  shards/<thread>/<run>.jsonl   one row per trial, written by the thread that ran it (append-only, never edited)
  merged/trials.jsonl           every valid row, deduplicated by trial_id (the daily merge writes it)
  merged/report.json|.md        per family: N_raw, K_eff, PBO, BHY-adjusted p, DSR per candidate, flags

A row (SCHEMA below; `python3 research/registry.py schema` prints it):
  required  trial_id, thread, family, arm, role, code_sha, data.source, data.days, by_day
  role      control | candidate | placebo | loo (leave-one-module-out) | neighbour
  by_day    {"YYYY-MM-DD": $ realized after fees} for the arm, phase/seed-averaged, DOGE excluded unless data.doge says so
  control   trial_id of the paired control (same days, same code); candidates are scored as by_day - control.by_day
  flags     free strings; the validator adds its own (see validate()).

Commands:
  schema                         print the JSON schema
  validate FILE...               check rows; exit 1 on an invalid row
  merge SHARD_DIR OUT_DIR        merge every shard, score each family, write merged/ files
  cellsweep SRC_DIR SHA THREAD   turn a cell-sweep Drive folder (d<dd>-<tag>.json.gz) into registry rows on stdout
  foreign FILE THREAD FAMILY     wrap another thread's own ledger (one JSON object a line) into registry rows
  ho1 SHARD                      fill each paired row's HO-1 heldout block (folds, terciles, placebo) -> stdout
  selftest                       run the built-in checks

Statistics (no scipy; tests in selftest):
  K_eff  participation ratio of the eigenvalues of the trials' daily-P&L correlation matrix, (sum l)^2 / sum l^2: the
         number of effectively independent trials (a cheap stand-in for ONC clustering, same role in the DSR).
  PBO    CSCV (Bailey et al. 2015) over S contiguous day blocks (S=6 default; fewer days -> S = largest even <= days).
  DSR    deflated Sharpe probability of a candidate's daily paired gain, SR0 from K_eff trials (Bailey & Lopez de Prado).
  BHY    Benjamini-Yekutieli step-up over the family's one-sided paired-t p-values (alpha 0.10).
"""
from __future__ import annotations

import gzip
import hashlib
import json
import math
import os
import re
import sys
from collections import defaultdict
from statistics import NormalDist

N01 = NormalDist()
CONTRACT_TYPES = ('price_prediction', 'perpetual', 'tennis')
# Steven 21:59 UTC Nov 5: track $/h per contract type, adding up the best validated module results that combine.
MODULE_OF = [(r'^(MARKET_ANCHOR|NO_LONGSHOT)', 'anchor'), (r'^TA_VETO', 'ta-veto'), (r'^FV_ENTRY_GATE|^ENTRY_WINDOW', 'entry-gate'),
             (r'^GATED_STAKE', 'sizing'), (r'^DYN_EDGE', 'scaling'), (r'^ACCURACY_GATE', 'accuracy-gate'),
             (r'^MODEL_SKILL', 'model-skill'), (r'^TENNIS_', 'tennis-ta'), (r'^PERP_', 'perp'), (r'^PACER', 'pacer'),
             (r'^(LOSER|TP_|TAKE_PROFIT|EXIT)', 'exits'), (r'^STRATEGY_EXCLUDE', 'series-filter'), (r'^TRAINING', 'training')]
ROLES = ('control', 'candidate', 'placebo', 'loo', 'neighbour')
SOURCES = ('recorded', 'history', 'paper', 'live')
DOGE = re.compile(r'^KXDOGE', re.I)
# Settings whose inputs come from the order book, which history replays synthesize (size 100, no depth): OFI, depth and the
# TA veto's confirmation count. Trade-tape signals (tennis taker flow, momentum, opponent) are real on history days.
# Simulators whose $ level disagrees with the replay (sizing lab, run 42071866371: 1.66x fills, window corr +0.14).
RANK_ONLY = {'cross_study'}
BOOK_FLOW = re.compile(r'OFI|DEPTH|^TA_VETO_CONF$', re.I)

SCHEMA = {
    '$schema': 'https://json-schema.org/draft/2020-12/schema',
    'title': 'registry trial row v1',
    'type': 'object',
    'required': ['trial_id', 'thread', 'family', 'arm', 'role', 'code_sha', 'data', 'by_day'],
    'properties': {
        'v': {'const': 1},
        'trial_id': {'type': 'string', 'description': 'sha1 of thread|family|arm|code_sha|days|seed|phase|env (make_id)'},
        'ts': {'type': 'string', 'description': 'UTC ISO time the row was written'},
        'thread': {'type': 'string', 'description': 'owning thread, short name (meta, losses, ta, sizing, all-pairs ...)'},
        'family': {'type': 'string', 'description': 'hypothesis family: every arm tried for one question (multiple-testing unit)'},
        'arm': {'type': 'string'},
        'role': {'enum': list(ROLES)},
        'control': {'type': 'string', 'description': 'trial_id of the paired control'},
        'env': {'type': 'object', 'description': 'flag -> value overrides vs the code default'},
        'code_sha': {'type': 'string'},
        'code_epoch': {'type': 'string', 'description': 'e.g. REPLAY_VERSION=7, pacer-fix=#290'},
        'seed': {'type': ['integer', 'null']},
        'phases': {'type': 'array', 'items': {'type': 'integer'}},
        'data': {'type': 'object', 'required': ['source', 'days'], 'properties': {
            'source': {'enum': list(SOURCES)},
            'days': {'type': 'array', 'items': {'type': 'string'}},
            'doge': {'type': 'boolean', 'description': 'true when DOGE series are in by_day (default false)'},
            'benches': {'enum': ['own', 'paper']},
            'copy': {'type': 'string', 'description': 'Drive copy / reuse_run the replay read'},
            'books': {'enum': ['recorded', 'synthetic']},
            'engine': {'type': 'string', 'description': 'simulator: replay (TS backtester, default) | cross_study (sizing lab) | ...'},
        }},
        'by_day': {'type': 'object', 'additionalProperties': {'type': 'number'}},
        'by_cell': {'type': 'object', 'description': 'optional: cell -> $ over the days'},
        'hours': {'type': 'number'},
        'fills': {'type': 'integer'},
        'markets': {'type': 'integer'},
        'noise_sd_day': {'type': 'number', 'description': 'SD of a day\'s control-vs-twin difference (phase/seed noise)'},
        'wide_spread_share': {'type': 'number', 'description': 'share of |P&L| from contracts quoted wider than 10c'},
        'pyes_kept': {'type': 'number'}, 'pyes_all': {'type': 'number'},
        'flags': {'type': 'array', 'items': {'type': 'string'}},
        'verdict': {'type': 'string'},
        'ref': {'type': 'string', 'description': 'run URL, comment or Drive path behind the row'},
        'raw': {'type': 'object', 'description': 'foreign ledger row kept verbatim'},
        'by_tercile': {'type': 'object', 'description': 'HO-1 history tier: {"LOW"|"MID"|"HIGH": {"pnl": $, "hours": h}} over H-HOLD, regime v1 labels'},
        'placebo_for': {'type': 'string', 'description': 'on a placebo row: the arm it mimics (HO-1 beats_placebo)'},
        'contract_type': {'enum': list(CONTRACT_TYPES), 'description': 'inferred from thread/env when absent (contract_type_of)'},
        'modules': {'type': 'array', 'items': {'type': 'string'}, 'description': 'bot modules the arm changes; inferred from env when absent'},
        'held_out': {'type': 'boolean', 'description': 'legacy: by_day is out of sample (not enough for the ledger without heldout)'},
        'heldout': {'type': 'object', 'description': 'held-out standard HO-1 evidence (see HO1 below and the README)', 'properties': {
            'standard': {'const': 'HO-1'}, 'tier': {'enum': ['history', 'recorded']},
            'days': {'type': 'number'}, 'folds': {'type': 'integer'}, 'folds_won': {'type': 'integer'},
            'worst_fold_per_hour': {'type': 'number'}, 'terciles_covered': {'type': 'integer'},
            'terciles_won': {'type': 'integer'}, 'worst_tercile_per_hour': {'type': 'number'},
            'beats_placebo': {'type': 'boolean'}, 'replay_version': {'type': 'integer'}}},
    },
}


def make_id(thread, family, arm, code_sha, days, seed=None, phases=None, env=None) -> str:
    key = json.dumps([thread, family, arm, code_sha, sorted(days), seed, sorted(phases or []), env or {}], sort_keys=True)
    return hashlib.sha1(key.encode()).hexdigest()[:16]


def validate(r: dict) -> tuple[list[str], list[str]]:
    """(errors, validator flags). Errors make the row invalid; flags mark evidence that cannot carry a verdict."""
    err, fl = [], []
    for k in SCHEMA['required']:
        if k not in r:
            err.append(f'missing {k}')
    if err:
        return err, fl
    if r['role'] not in ROLES:
        err.append(f'role {r["role"]!r}')
    d = r['data']
    if d.get('source') not in SOURCES:
        err.append(f'data.source {d.get("source")!r}')
    bd = r['by_day']
    if not isinstance(bd, dict) or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in bd.values()):
        err.append('by_day must be a {day: finite $} map')
    elif not bd:
        fl.append('G2:no-daily-pnl')  # kept in the trial count (N_raw), left out of PBO/DSR/BHY
    # Validator rules (meta thread, Nov 5):
    if d.get('doge'):
        fl.append('G0:doge-included')  # Steven 13:26 UTC Nov 5: no DOGE in scoring for now
    if d.get('benches') == 'paper':
        fl.append('G0:paper-benches')  # Steven 13:51 UTC Nov 5: paper has no say in training
    if d.get('source') == 'history' and d.get('books') == 'synthetic' and any(BOOK_FLOW.search(k) for k in (r.get('env') or {})):
        fl.append('G1:synthetic-book-flow')  # order-flow inputs are fake on history books (TA thread, Nov 5)
    if d.get('engine') in RANK_ONLY:
        fl.append('G1:rank-only-level')  # level ($/h) not valid; compare only variants on the same entries
    if 'dev-choice' in (r.get('flags') or []):
        if any(x >= H_HOLD[0] for x in (r.get('by_day') or {})):
            fl.append('G0:dev-choice-reads-hold')  # an H-DEV choice run must not carry H-HOLD days
        fl.append('DEV:choice-only')  # counted in N_raw, never scored as held out
    w = r.get('wide_spread_share')
    if isinstance(w, (int, float)) and w > 0.5:
        fl.append('G1b:wide-spread-pnl')  # SNN thread: history "mid" of a 1c/99c book is not a price
    pk, pa = r.get('pyes_kept'), r.get('pyes_all')
    if isinstance(pk, (int, float)) and isinstance(pa, (int, float)) and abs(pk - pa) > 0.02:
        fl.append('G1c:pyes-selection-bias')  # all-pairs: dropping crossed windows biases toward NO
    if r['role'] == 'candidate' and not r.get('control'):
        fl.append('G2:unpaired')
    if any(re.match(r'^2026-11-(0[6-9]|1[0-2])$|^2026-11-13$', x) for x in d.get('days', [])) and 'lockbox-L1' not in (r.get('flags') or []):
        fl.append('LOCKBOX:L1-days-read-early')  # lockbox L1 Nov 6 05:00 - Nov 13 05:00 UTC, opened once
    return err, fl


# ---------------------------------------------------------------- statistics

def _mean(x):
    return sum(x) / len(x) if x else float('nan')


def _sd(x):
    if len(x) < 2:
        return float('nan')
    m = _mean(x)
    return math.sqrt(sum((v - m) ** 2 for v in x) / (len(x) - 1))


def _betacf(a, b, x):
    qab, qap, qam = a + b, a + 1, a - 1
    c, d = 1.0, 1 - qab * x / qap
    d = 1 / (d if abs(d) > 1e-300 else 1e-300)
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1 + aa * d; d = 1 / (d if abs(d) > 1e-300 else 1e-300)
        c = 1 + aa / c if abs(c) > 1e-300 else 1e300
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1 + aa * d; d = 1 / (d if abs(d) > 1e-300 else 1e-300)
        c = 1 + aa / c if abs(c) > 1e-300 else 1e300
        de = d * c
        h *= de
        if abs(de - 1) < 1e-12:
            break
    return h


def _ibeta(a, b, x):
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lb = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1 - x)
    if x < (a + 1) / (a + b + 2):
        return math.exp(lb) * _betacf(a, b, x) / a
    return 1 - math.exp(lb) * _betacf(b, a, 1 - x) / b


def t_sf(t, df):
    """P(T > t) for Student t with df degrees of freedom."""
    x = df / (df + t * t)
    p = 0.5 * _ibeta(df / 2, 0.5, x)
    return p if t > 0 else 1 - p


def paired_p(gains):
    """One-sided paired t p-value that the mean daily gain is > 0."""
    n = len(gains)
    s = _sd(gains)
    if n < 2 or not s > 0:
        return float('nan')
    return t_sf(_mean(gains) / (s / math.sqrt(n)), n - 1)


def bhy(ps, alpha=0.10):
    """Benjamini-Yekutieli step-up: list of (adjusted p, rejected)."""
    m = len(ps)
    if not m:
        return []
    cm = sum(1 / i for i in range(1, m + 1))
    order = sorted(range(m), key=lambda i: ps[i] if math.isfinite(ps[i]) else 2)
    adj = [1.0] * m
    run = 1.0
    for rank in range(m, 0, -1):
        i = order[rank - 1]
        p = ps[i] if math.isfinite(ps[i]) else 1.0
        run = min(run, p * m * cm / rank)
        adj[i] = min(1.0, run)
    return [(a, a <= alpha) for a in adj]


def _jacobi_eig(a):
    n = len(a)
    a = [row[:] for row in a]
    for _ in range(100):
        off = sum(a[i][j] ** 2 for i in range(n) for j in range(n) if i != j)
        if off < 1e-18:
            break
        for p in range(n):
            for q in range(p + 1, n):
                if abs(a[p][q]) < 1e-15:
                    continue
                th = (a[q][q] - a[p][p]) / (2 * a[p][q])
                t = (1 if th >= 0 else -1) / (abs(th) + math.sqrt(th * th + 1))
                c = 1 / math.sqrt(t * t + 1); s = t * c
                for k in range(n):
                    akp, akq = a[k][p], a[k][q]
                    a[k][p], a[k][q] = c * akp - s * akq, s * akp + c * akq
                for k in range(n):
                    apk, aqk = a[p][k], a[q][k]
                    a[p][k], a[q][k] = c * apk - s * aqk, s * apk + c * aqk
    return [a[i][i] for i in range(n)]


def k_eff(series):
    """Participation ratio of the correlation eigenvalues of the trials' daily series (each a list over the same days)."""
    s = [x for x in series if len(x) >= 2 and _sd(x) > 0]
    n = len(s)
    if n <= 1:
        return float(n)
    z = []
    for x in s:
        m, sd = _mean(x), _sd(x)
        z.append([(v - m) / sd for v in x])
    T = len(z[0])
    c = [[sum(z[i][t] * z[j][t] for t in range(T)) / (T - 1) for j in range(n)] for i in range(n)]
    lam = [max(0.0, v) for v in _jacobi_eig(c)]
    return sum(lam) ** 2 / sum(v * v for v in lam) if sum(lam) > 0 else 1.0


def dsr(gains, n_trials, var_sr=None):
    """Deflated Sharpe probability of a daily gain series given n_trials effective trials."""
    T = len(gains)
    sd = _sd(gains)
    if T < 3 or not sd > 0:
        return float('nan'), float('nan'), float('nan')
    m = _mean(gains)
    sr = m / sd
    sk = sum(((g - m) / sd) ** 3 for g in gains) / T
    ku = sum(((g - m) / sd) ** 4 for g in gains) / T
    n = max(1.0, n_trials)
    if var_sr is None:
        var_sr = 1.0 / (T - 1)  # SR estimation variance under the null when no cross-trial SR spread is given
    g = 0.5772156649
    sr0 = 0.0 if n <= 1 else math.sqrt(var_sr) * ((1 - g) * N01.inv_cdf(1 - 1 / n) + g * N01.inv_cdf(1 - 1 / (n * math.e)))
    den = 1 - sk * sr + (ku - 1) / 4 * sr * sr
    if den <= 0:
        return sr, sr0, float('nan')
    return sr, sr0, N01.cdf((sr - sr0) * math.sqrt(T - 1) / math.sqrt(den))


def pbo(matrix, S=6):
    """CSCV probability of backtest overfitting. matrix: trial -> list of daily $ over the same days."""
    from itertools import combinations
    names = list(matrix)
    if len(names) < 2:
        return float('nan'), 0
    T = len(matrix[names[0]])
    S = min(S, T - T % 2)
    if S < 2:
        return float('nan'), 0
    bounds = [round(i * T / S) for i in range(S + 1)]
    blocks = [list(range(bounds[i], bounds[i + 1])) for i in range(S)]
    logits = []
    for ins in combinations(range(S), S // 2):
        I = [d for b in ins for d in blocks[b]]
        O = [d for b in range(S) if b not in ins for d in blocks[b]]
        best = max(names, key=lambda n: sum(matrix[n][d] for d in I))
        oos = sorted(names, key=lambda n: sum(matrix[n][d] for d in O))
        rank = oos.index(best) + 1
        w = rank / (len(names) + 1)
        logits.append(math.log(w / (1 - w)))
    return sum(1 for l in logits if l <= 0) / len(logits), len(logits)


# ---------------------------------------------------------------- merge

def read_rows(paths):
    for p in paths:
        op = gzip.open if p.endswith('.gz') else open
        with op(p, 'rt') as fh:
            for i, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    yield p, i, json.loads(line)
                except json.JSONDecodeError as e:
                    yield p, i, {'_bad': str(e)}


def merge(shard_dir, out_dir, S=6):
    paths = sorted(os.path.join(dp, f) for dp, _, fs in os.walk(shard_dir) for f in fs if re.search(r'\.jsonl(\.gz)?$', f))
    rows, bad = {}, []
    for p, i, r in read_rows(paths):
        if '_bad' in r:
            bad.append(f'{p}:{i}: {r["_bad"]}')
            continue
        err, fl = validate(r)
        if err:
            bad.append(f'{p}:{i}: {"; ".join(err)}')
            continue
        r['flags'] = sorted(set((r.get('flags') or []) + fl))
        rows[r['trial_id']] = r  # later shards win on a re-run of the same trial
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, 'trials.jsonl'), 'w') as fh:
        for r in rows.values():
            fh.write(json.dumps(r, sort_keys=True) + '\n')
    fams = defaultdict(list)
    for r in rows.values():
        fams[(r['thread'], r['family'])].append(r)
    rep = {'n_rows': len(rows), 'n_bad': len(bad), 'bad': bad[:200], 'families': []}
    for (th, fam), rs in sorted(fams.items()):
        scored = [r for r in rs if r['by_day']]
        days = sorted(set.intersection(*[set(r['by_day']) for r in scored])) if scored else []
        rs_all, rs = rs, scored
        mat = {r['trial_id']: [r['by_day'][d] for d in days] for r in rs}
        ke = k_eff(list(mat.values())) if len(days) >= 3 else float(len(rs))
        p_bo, splits = pbo({r['trial_id']: mat[r['trial_id']] for r in rs if r['role'] != 'placebo'}, S) if len(days) >= 2 else (float('nan'), 0)
        cands = []
        byid = {r['trial_id']: r for r in rs}
        for r in rs:
            if r['role'] not in ('candidate', 'loo', 'neighbour') or r.get('control') not in byid:
                continue
            c = byid[r['control']]
            cd = [d for d in sorted(r['by_day']) if d in c['by_day']]
            g = [r['by_day'][d] - c['by_day'][d] for d in cd]
            sr, sr0, prob = dsr(g, ke)
            noise = r.get('noise_sd_day')
            cands.append({'trial_id': r['trial_id'], 'arm': r['arm'], 'role': r['role'], 'days': len(cd),
                          'gain': sum(g), 'gain_per_day': _mean(g), 'p': paired_p(g), 'sr': sr, 'sr0': sr0, 'dsr': prob,
                          'above_2noise': (None if noise is None else sum(g) > 2 * noise * math.sqrt(len(cd))),
                          'flags': r['flags'], 'contract_type': contract_type_of(r), 'modules': modules_of(r),
                          'held_out': bool(r.get('held_out')), 'ho1': ho1_pass(r.get('heldout'), contract_type_of(r)), 'hours_per_day': (r.get('hours') or 24 * len(cd)) / max(1, len(cd))})
        for c, (adj, rej) in zip(cands, bhy([c['p'] for c in cands])):
            c['p_bhy'], c['bhy_pass'] = adj, rej
        rep['families'].append({'thread': th, 'family': fam, 'n_raw': len(rs_all), 'k_eff': ke, 'days': len(days),
                                'pbo': p_bo, 'pbo_splits': splits, 'candidates': cands,
                                'flagged': sum(1 for r in rs_all if r['flags'])})
    with open(os.path.join(out_dir, 'report.json'), 'w') as fh:
        json.dump(rep, fh, indent=1, default=lambda x: None)
    L = [f'# Trial registry: {len(rows)} trials, {len(rep["families"])} families, {len(bad)} invalid rows', '']
    for f in rep['families']:
        L.append(f'## {f["thread"]} / {f["family"]}: N_raw {f["n_raw"]}, K_eff {f["k_eff"]:.1f}, {f["days"]} common days, '
                 f'PBO {f["pbo"]:.2f} ({f["pbo_splits"]} splits), {f["flagged"]} flagged')
        if f['candidates']:
            L.append('| arm | role | days | gain $ | p | p BHY | DSR | >2 noise | flags |')
            L.append('|---|---|---|---|---|---|---|---|---|')
            for c in sorted(f['candidates'], key=lambda c: -c['gain']):
                L.append(f'| {c["arm"]} | {c["role"]} | {c["days"]} | {c["gain"]:+.2f} | {c["p"]:.3f} | {c["p_bhy"]:.3f}'
                         f'{" ✓" if c["bhy_pass"] else ""} | {c["dsr"]:.2f} | {c["above_2noise"]} | {" ".join(c["flags"])} |')
        L.append('')
    with open(os.path.join(out_dir, 'report.md'), 'w') as fh:
        fh.write('\n'.join(L).replace('nan', 'n/a') + '\n')
    with open(os.path.join(out_dir, 'contract-ledger.md'), 'w') as fh:
        fh.write(contract_ledger(rep))
    return rep


H_HOLD = ('2026-08-01', '2026-11-04')


def ho1_fill(rows):
    """Fill the HO-1 `heldout` block of every paired row from by_day (and by_tercile) against its control, so every thread
    computes folds the same way. History tier: H-HOLD days in 6 consecutive folds; recorded tier: one fold per day."""
    from datetime import date, timedelta
    byid = {r['trial_id']: r for r in rows}
    plac = {(r['family'], r.get('placebo_for')): r for r in rows if r['role'] == 'placebo' and r.get('placebo_for')}
    for r in rows:
        c = byid.get(r.get('control'))
        if r['role'] == 'control' or not c or 'dev-choice' in (r.get('flags') or []):
            continue
        tier = 'history' if r['data']['source'] == 'history' else 'recorded'
        d0, d1 = (date.fromisoformat(H_HOLD[0]), date.fromisoformat(H_HOLD[1])) if tier == 'history' else (None, None)
        days = sorted(d for d in r['by_day'] if d in c['by_day'] and (tier == 'recorded' or H_HOLD[0] <= d <= H_HOLD[1]))
        hpd = 24.0
        if tier == 'history':
            span = (d1 - d0).days + 1
            edges = [d0 + timedelta(days=round(i * span / 6)) for i in range(7)]
            folds = [[d for d in days if edges[i].isoformat() <= d < edges[i + 1].isoformat()] for i in range(6)]
            folds[-1] += [d for d in days if d == d1.isoformat()]
        else:
            folds = [[d] for d in days]
        fg = [sum(r['by_day'][d] - c['by_day'][d] for d in f) / (hpd * len(f)) for f in folds if f]
        h = {'standard': 'HO-1', 'tier': tier, 'days': len(days), 'folds': len(fg), 'folds_won': sum(1 for g in fg if g > 0),
             'worst_fold_per_hour': min(fg) if fg else None}
        rt, ct = r.get('by_tercile') or {}, c.get('by_tercile') or {}
        if tier == 'history' and rt and ct:
            tg = {k: (rt[k]['pnl'] - ct[k]['pnl']) / rt[k]['hours'] for k in rt if k in ct and (rt[k].get('hours') or 0) >= 100}
            h.update(terciles_covered=len(tg), terciles_won=sum(1 for g in tg.values() if g > 0),
                     worst_tercile_per_hour=min(tg.values()) if tg else None)
        p = plac.get((r['family'], r['arm']))
        if p:
            gain = sum(r['by_day'][d] - c['by_day'][d] for d in days)
            pg = sum(p['by_day'].get(d, 0.0) - c['by_day'][d] for d in days)
            h['beats_placebo'] = gain > pg
        rv = (r.get('data') or {}).get('replay_version')
        if rv is not None:
            h['replay_version'] = rv
        r['heldout'] = h
    return rows


def contract_type_of(r):
    if r.get('contract_type') in CONTRACT_TYPES:
        return r['contract_type']
    if 'tennis' in r['thread'] or any(k.startswith('TENNIS_') for k in (r.get('env') or {})):
        return 'tennis'
    if 'perp' in r['thread'] or any(k.startswith('PERP_') for k in (r.get('env') or {})):
        return 'perpetual'
    return 'price_prediction'


def modules_of(r):
    if r.get('modules'):
        return sorted(set(r['modules']))
    m = {mod for k in (r.get('env') or {}) for pat, mod in MODULE_OF if re.match(pat, k)}
    return sorted(m) or ['other']


# Held-out standard HO-1 (Steven 22:07 UTC Nov 5: held-out must be a large chunk of time, not a few days).
#   history tier : choose on H-DEV Apr 18-Jul 31 2026 only; score on H-HOLD Aug 1-Nov 4 2026 (96 days, crash of Oct 29
#                  included) in 6 consecutive folds of 16 days. Needs >= 90 held-out days, folds won >= 4/6, worst fold
#                  >= -$0.50/h, >= 2 of 3 RV terciles covered (regime v1, >= 100 h each) and won, none below -$0.50/h,
#                  and the gain beats its placebo.
#   recorded tier: every fixed-code recorded day (>= 14 days, Oct 21 on), leave-one-day-out walk-forward (>= 14 folds),
#                  >= 2 tick phases or K=8 seeds; folds won >= 60%, worst day >= -$1.00/h, beats placebo.
#   The ledger counts a result when its history tier passes and its recorded tier is not negative, or (a mechanism the
#   history books cannot simulate: depth, order flow) when its recorded tier passes. Lockboxes L1/L2 stay separate.
HO1 = {'history': {'days': 90, 'folds': 6, 'win_share': 4 / 6, 'worst_fold': -0.50, 'terciles': 2, 'worst_tercile': -0.50},
       'recorded': {'days': 14, 'folds': 14, 'win_share': 0.60, 'worst_fold': -1.00, 'terciles': 0, 'worst_tercile': None}}
REPLAY_VERSION_MIN = 8  # results from before #286 are re-run on REPLAY_VERSION 8


def ho1_pass(h, contract_type='price_prediction'):
    """(passes, why) for a row's heldout block under HO-1."""
    if not isinstance(h, dict) or h.get('standard') != 'HO-1' or h.get('tier') not in HO1:
        return False, 'no HO-1 held-out block'
    t = HO1[h['tier']]
    why = []
    if (h.get('days') or 0) < t['days']: why.append(f'{h.get("days") or 0} held-out days < {t["days"]}')
    k = h.get('folds') or 0
    if k < t['folds']: why.append(f'{k} folds < {t["folds"]}')
    elif (h.get('folds_won') or 0) / k < t['win_share'] - 1e-9: why.append(f'won {h.get("folds_won") or 0}/{k} folds')
    if (h.get('worst_fold_per_hour') if h.get('worst_fold_per_hour') is not None else -1e9) < t['worst_fold']: why.append('worst fold too deep')
    if t['terciles']:
        if (h.get('terciles_covered') or 0) < t['terciles'] or (h.get('terciles_won') or 0) < t['terciles']: why.append('fewer than 2 RV terciles won')
        if (h.get('worst_tercile_per_hour') if h.get('worst_tercile_per_hour') is not None else -1e9) < t['worst_tercile']: why.append('a tercile below -$0.50/h')
    if not h.get('beats_placebo'): why.append('does not beat its placebo')
    # REPLAY_VERSION is the Kalshi history replay's; perps run their own minute simulator on Binance bars (no version gate).
    if h['tier'] == 'history' and contract_type != 'perpetual' and (h.get('replay_version') or 0) < REPLAY_VERSION_MIN: why.append(f'replay version < {REPLAY_VERSION_MIN}')
    return not why, '; '.join(why)


BLOCKING_EXTRA = ('DEV:',)
BLOCKING = ('G0:', 'G1:', 'G1b:', 'G1c:', 'G2:', 'LOCKBOX:')


def validated(c):
    """A result that may count toward a contract type's model: clean evidence, held out, survives multiple testing and noise."""
    return (c['role'] == 'candidate' and c['ho1'][0] and c['bhy_pass'] and c['above_2noise'] is not False
            and c['gain'] > 0 and not any(f.startswith(BLOCKING + BLOCKING_EXTRA) for f in c['flags']))


def contract_ledger(rep, target=4.50):
    """Per contract type: the best validated result per module, combined greedily over disjoint module sets."""
    cs = [dict(c, thread=f['thread'], family=f['family']) for f in rep['families'] for c in f['candidates']]
    L = ['# Contract-type ledger (Steven, 21:59 UTC / 4:59 PM EST Nov 5)', '',
         'Sum of the best VALIDATED module results that combine (disjoint modules): held-out standard HO-1 (96-day history',
         'hold-out in 6 folds + 2 RV terciles, or 14+ recorded days walk-forward; see README), BHY pass, above 2x noise, no',
         'blocking flag (DOGE, paper benches, synthetic book flow, wide spreads, selection bias, unpaired, lockbox). Never paper.',
         f'A contract type at or above ${target:.2f}/h freezes as that type\'s model; new work is then judged against it.', '']
    for ct in CONTRACT_TYPES:
        mine = [c for c in cs if c['contract_type'] == ct]
        ok = sorted([c for c in mine if validated(c)], key=lambda c: -c['gain_per_day'] / c['hours_per_day'])
        used, picks = set(), []
        for c in ok:
            if not used & set(c['modules']):
                picks.append(c); used |= set(c['modules'])
        tot = sum(c['gain_per_day'] / c['hours_per_day'] for c in picks)
        state = 'MODEL (freeze)' if tot >= target else 'building'
        L.append(f'## {ct.replace("_", " ").title()}: ${tot:+.2f}/h validated of ${target:.2f}/h, {state}')
        L.append(f'{len(mine)} scored candidate(s); {len(ok)} validated.')
        if picks:
            L += ['| module(s) | thread / family | arm | $/h | days | p BHY | DSR |', '|---|---|---|---|---|---|---|']
            for c in picks:
                L.append(f'| {", ".join(c["modules"])} | {c["thread"]} / {c["family"]} | {c["arm"]} | {c["gain_per_day"] / c["hours_per_day"]:+.2f}'
                         f' | {c["days"]} | {c["p_bhy"]:.3f} | {c["dsr"]:.2f} |')
        leads = sorted([c for c in mine if not validated(c) and c['gain'] > 0], key=lambda c: -c['gain_per_day'] / c['hours_per_day'])[:8]
        if leads:
            L += ['', 'Leads not yet validated (why):', '| module(s) | thread / family | arm | $/h | why not |', '|---|---|---|---|---|']
            for c in leads:
                why = [f for f in c['flags'] if f.startswith(BLOCKING)]
                if not c['ho1'][0]: why.append('HO-1: ' + c['ho1'][1])
                if not c['bhy_pass']: why.append(f'BHY p {c["p_bhy"]:.2f}')
                if c['above_2noise'] is False: why.append('under 2x noise')
                if c['role'] != 'candidate': why.append(c['role'])
                L.append(f'| {", ".join(c["modules"])} | {c["thread"]} / {c["family"]} | {c["arm"]} | {c["gain_per_day"] / c["hours_per_day"]:+.2f} | {"; ".join(why)} |')
        L.append('')
    return '\n'.join(L).replace('nan', 'n/a') + '\n'


# ---------------------------------------------------------------- backfill adapters

def cellsweep_rows(src, sha, thread='meta', family=None, control='C', noise_tags=('P500', 'PSH', 'NLM', 'WP500', 'WPSH', 'WNLM'),
                   placebos=('Panc', 'NLm', 'Pta', 'Psc'), month='2026-10', benches='own', batch=None):
    """Rows from a cell-sweep folder of d<dd>-<tag>.json.gz replays (tag <arm>p<phase>), DOGE series dropped."""
    family = family or f'cell-sweep-{sha[:7]}'
    per = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))  # arm -> phase -> day -> $
    for f in sorted(os.listdir(src)):
        m = re.match(r'^d(\d\d)-([A-Za-z0-9]+)\.json(\.gz)?$', f)
        if not m:
            continue
        op = gzip.open if f.endswith('.gz') else open
        with op(os.path.join(src, f), 'rt') as fh:
            res = json.load(fh)
        dd, tag = m.group(1), m.group(2)
        pm = re.match(r'^(.+?)p(\d+)$', tag)
        arm, ph = (pm.group(1), int(pm.group(2))) if pm else (tag, -1)
        mon = month if int(dd) > 15 else '2026-11'  # cell sweeps so far span Oct 2x - Nov 0x
        day = f'{mon}-{dd}'
        per[arm][ph][day] += 0.0
        for t, v in ((res.get('replay') or {}).get('byTicker') or {}).items():
            if not DOGE.match(t):
                per[arm][ph][day] += float(v)
    env_of, date_of = {}, {}
    if batch:
        with open(batch) as fh:
            for line in fh:
                f = line.split()
                if not f or f[0].startswith('#') or len(f) < 5:
                    continue
                m = re.match(r'^d(\d\d)-(.+?)(?:p\d+)?$', f[0])
                if not m:
                    continue
                date_of[m.group(1)] = f[1]
                env_of.setdefault(m.group(2), dict(x.split('=', 1) for x in f[5:] if '=' in x))
    if date_of:  # real dates from the batch file instead of the month guess
        for arm in per:
            for ph in per[arm]:
                per[arm][ph] = defaultdict(float, {date_of.get(d[-2:], d): v for d, v in per[arm][ph].items()})
    cenv = env_of.get(control, {})
    out = []
    ids = {}
    for arm, phs in per.items():
        days = sorted(set.intersection(*[set(v) for v in phs.values()]))
        by_day = {d: sum(phs[p][d] for p in phs) / len(phs) for d in days}
        role = 'control' if arm == control else 'placebo' if (arm in placebos or arm in noise_tags) else 'candidate'
        tid = make_id(thread, family, arm, sha, days, phases=sorted(phs))
        ids[arm] = tid
        out.append({'v': 1, 'trial_id': tid, 'thread': thread, 'family': family, 'arm': arm, 'role': role,
                    'code_sha': sha, 'phases': sorted(phs), 'data': {'source': 'recorded', 'days': days, 'doge': False,
                    'benches': benches, 'books': 'recorded'}, 'by_day': by_day,
                    'ref': f'gdrive:kalshi-bot-archive/simulated/cell-sweep/{sha}'})
        if arm in env_of:
            e = env_of[arm]
            diff = {k: v for k, v in e.items() if cenv.get(k) != v}
            diff.update({k: '<unset>' for k in cenv if k not in e})
            out[-1]['env'] = diff
            out[-1]['modules'] = modules_of({'env': diff})
    cph = per.get(control, {})
    ps = sorted(p for p in cph if p >= 0)
    noise = None
    if len(ps) >= 2:
        a, b = cph[ps[0]], cph[ps[1]]
        xs = [a[d] - b[d] for d in a if d in b]
        if len(xs) >= 2:
            noise = _sd(xs) / math.sqrt(len(ps))
    for r in out:
        if r['arm'] != control and control in ids:
            r['control'] = ids[control]
        if noise is not None:
            r['noise_sd_day'] = noise
    return out


def foreign_rows(path, thread, family):
    """Wrap another thread's own ledger. Keeps the row under raw; maps the fields that have an obvious meaning."""
    out = []
    for p, i, r in read_rows([path]):
        if '_bad' in r:
            continue
        bd = r.get('by_day') or r.get('byDay') or r.get('daily') or {}
        arm = str(r.get('arm') or r.get('id') or r.get('name') or r.get('trial') or f'row{i}')
        days = sorted(bd) if isinstance(bd, dict) else []
        sha = str(r.get('code_sha') or r.get('sha') or 'unknown')
        out.append({'v': 1, 'trial_id': str(r.get('trial_id') or make_id(thread, family, arm, sha, days, env=r.get('env'))),
                    'thread': thread, 'family': str(r.get('family') or family), 'arm': arm,
                    'role': r.get('role') if r.get('role') in ROLES else 'candidate', 'code_sha': sha,
                    'env': r.get('env') or {}, 'data': {'source': r.get('source') if r.get('source') in SOURCES else 'history',
                    'days': days, 'doge': bool(r.get('doge', False))}, 'by_day': bd if isinstance(bd, dict) else {},
                    'flags': ['foreign-ledger'] + ([] if bd else ['no-by-day']), 'ref': path, 'raw': r})
    return out


# ---------------------------------------------------------------- selftest / cli

def selftest():
    assert abs(t_sf(2.0, 10) - 0.036694) < 1e-4, t_sf(2.0, 10)
    assert abs(t_sf(-1.0, 5) - 0.818391) < 1e-4
    adj = bhy([0.001, 0.01, 0.03, 0.5])
    assert adj[0][1] and not adj[3][1]
    assert abs(k_eff([[1, 2, 3, 4], [2, 4, 6, 8.1], [1, -1, -1, 1]]) - 1.8) < 0.01  # eigenvalues ~2, ~0, 1
    m = {f't{i}': [((i * 7 + d * 13) % 11) - 5 for d in range(12)] for i in range(8)}
    p, n = pbo(m, 6)
    assert n == 20 and 0 <= p <= 1
    _, _, prob = dsr([5, 3, 4, 6, 2, 5, 4], 1)
    assert prob > 0.95
    _, _, prob2 = dsr([5, 3, 4, 6, 2, 5, 4], 200)
    assert prob2 < prob
    r = {'trial_id': 'x', 'thread': 't', 'family': 'f', 'arm': 'a', 'role': 'candidate', 'code_sha': 's',
         'data': {'source': 'recorded', 'days': ['2026-11-07'], 'doge': True}, 'by_day': {'2026-11-07': 1.0}}
    err, fl = validate(r)
    assert not err and 'G0:doge-included' in fl and 'G2:unpaired' in fl and 'LOCKBOX:L1-days-read-early' in fl, fl
    h = {**r, 'data': {'source': 'history', 'days': ['2026-10-01'], 'books': 'synthetic'}}
    assert 'G1:synthetic-book-flow' in validate({**h, 'env': {'TA_VETO_OFI': 0}})[1]
    assert 'G1:synthetic-book-flow' in validate({**h, 'env': {'TENNIS_CONF_DEPTH': 1}})[1]
    assert 'G1:synthetic-book-flow' not in validate({**h, 'env': {'TENNIS_CONF_FLOW': 1, 'TENNIS_CONF_MOMENTUM_CENTS': 2}})[1]
    ok = {'standard': 'HO-1', 'tier': 'history', 'days': 96, 'folds': 6, 'folds_won': 4, 'worst_fold_per_hour': -0.2,
          'terciles_covered': 3, 'terciles_won': 2, 'worst_tercile_per_hour': -0.1, 'beats_placebo': True, 'replay_version': 8}
    assert ho1_pass(ok)[0], ho1_pass(ok)
    assert not ho1_pass({**ok, 'days': 7})[0] and not ho1_pass({**ok, 'folds_won': 3})[0] and not ho1_pass({**ok, 'replay_version': 7})[0]
    assert not ho1_pass(None)[0]
    assert ho1_pass({**ok, 'replay_version': None}, 'perpetual')[0]
    from datetime import date, timedelta
    hd = [(date(2026, 8, 1) + timedelta(days=i)).isoformat() for i in range(96)]
    base = {'thread': 't', 'family': 'f', 'code_sha': 's', 'data': {'source': 'history', 'days': hd, 'replay_version': 8}}
    rows = [dict(base, trial_id='c', arm='C', role='control', by_day={d: 0.0 for d in hd},
                 by_tercile={k: {'pnl': 0.0, 'hours': 700} for k in ('LOW', 'MID', 'HIGH')}),
            dict(base, trial_id='x', arm='X', role='candidate', control='c', by_day={d: 30.0 for d in hd},
                 by_tercile={k: {'pnl': 900.0, 'hours': 700} for k in ('LOW', 'MID', 'HIGH')}),
            dict(base, trial_id='p', arm='P', role='placebo', placebo_for='X', control='c', by_day={d: 1.0 for d in hd})]
    hx = ho1_fill(rows)[1]['heldout']
    assert hx['days'] == 96 and hx['folds'] == 6 and hx['folds_won'] == 6 and hx['terciles_won'] == 3 and hx['beats_placebo'], hx
    assert ho1_pass(hx)[0], ho1_pass(hx)
    dv = {**r, 'flags': ['dev-choice'], 'by_day': {'2026-07-30': 1.0, '2026-08-02': 1.0}, 'control': 'c'}
    assert 'G0:dev-choice-reads-hold' in validate(dv)[1] and 'DEV:choice-only' in validate(dv)[1]
    print('registry selftest ok')


def main(a):
    if not a or a[0] in ('-h', '--help'):
        print(__doc__)
    elif a[0] == 'schema':
        print(json.dumps(SCHEMA, indent=1))
    elif a[0] == 'validate':
        badn = 0
        for p, i, r in read_rows(a[1:]):
            err, fl = validate(r) if '_bad' not in r else ([r['_bad']], [])
            if err:
                badn += 1
                print(f'{p}:{i}: INVALID {"; ".join(err)}')
            elif fl:
                print(f'{p}:{i}: flags {" ".join(fl)}')
        sys.exit(1 if badn else 0)
    elif a[0] == 'merge':
        rep = merge(a[1], a[2], int(a[a.index('--S') + 1]) if '--S' in a else 6)
        print(f'{rep["n_rows"]} trials, {len(rep["families"])} families, {rep["n_bad"]} invalid')
    elif a[0] == 'cellsweep':
        kw = {}
        if '--control' in a:
            kw['control'] = a[a.index('--control') + 1]
        if '--family' in a:
            kw['family'] = a[a.index('--family') + 1]
        if '--batch' in a:
            kw['batch'] = a[a.index('--batch') + 1]
        if '--benches' in a:
            kw['benches'] = a[a.index('--benches') + 1]
        for r in cellsweep_rows(a[1], a[2], a[3] if len(a) > 3 and not a[3].startswith('--') else 'meta', **kw):
            print(json.dumps(r, sort_keys=True))
    elif a[0] == 'foreign':
        for r in foreign_rows(a[1], a[2], a[3]):
            print(json.dumps(r, sort_keys=True))
    elif a[0] == 'ho1':
        rows = [r for _, _, r in read_rows(a[1:2]) if '_bad' not in r]
        for r in ho1_fill(rows):
            print(json.dumps(r, sort_keys=True))
    elif a[0] == 'selftest':
        selftest()
    else:
        sys.exit(f'unknown command {a[0]}')


if __name__ == '__main__':
    main(sys.argv[1:])
