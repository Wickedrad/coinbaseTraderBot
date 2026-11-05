#!/usr/bin/env python3
"""Tennis TA rulebook trial: the report job (pre-registration /mnt/project-files/tennis-ta/preregistration.md, Amendments 1-3).

Both families are scored here (Amendment 3: research/tennisTaStats.ts is gone). Input: the shard files of
research/tennisTaSweep.ts run (gzip JSON, one per sub-slice, contract C4):
  { meta: { simVersion, stage, pool, run, k, j, shards, subShards, from, to, units, dataVersion, coverage, requestSha,
            families, ...bookkeeping }, matchList: [MatchInfo + pool + unit], runs: [SimRun + stick?], familyB?: FamilyBExport }

  shard set   checked before anything is scored: every (k, j) of meta.shards x meta.subShards exactly once, one run,
              stage, pool, families, sim version and data version, the slices cut at unit edges with no unit twice and
              no pool unit left out, match events unique, the same runs in every file (and, with --plan, every planned
              file and nothing else, each matching its planned slice), and the runs link to configs soundly (check_runs:
              every non-stick id ends in its arm, a config's arms share overrides, no stress or measuring key moved
              outside a measuring stick, no two non-placebo runs with the same overrides and fill). Any problem: exit
              non-zero, nothing written.
  universe    family A: every owned match of the pool(s) with a tape (a match the config did not trade counts 0). A cell
              = config x arm x tour x phase x price bucket of the entry (an "all" level on each axis); arms F1, F2, coin
              (the config's coin-flip placebo) and stick (measuring sticks: scored and logged, never screened or counted
              as hypotheses). Realized net after fees is the only score.
  bootstrap   stationary bootstrap over the time-ordered tournament-week units (A2: blocks are whole units, mean block
              length --block units, B = --boot) for every CI and p-value; p = (1 + #exceedances) / (B + 1), never 0
  screen      BH at q = --alpha over the F1 cells (family A) and, as its own family, over family B's design; then the
              section 6 conditions: >= 100 entries on >= 30 match-days, mean > 0, >= 60% of monthly folds with 10+
              entries positive, net positive under F2 (B: the stress column), zero settlement breaches for the CONFIG
              (A: any breach in any cell of any arm of the config fails every cell of it; B: the reading's exit rule)
  folds       months of each unit's last day (the Sunday before its Monday 05:00 UTC end): a unit is never split
  placebo     A: per-unit paired difference against the config's coin arm, same bootstrap; B: paired per-unit difference
              of mean net per entry (cell minus placebo, units where both have entries) with a paired z
  day t       the match-day clustered t of section 6, kept as a descriptive column (A2), vs zero and vs the placebo
  ONC         N_eff = clusters of the per-match P&L correlation (distance sqrt((1 - rho) / 2)) over the F1 cells with
              >= --onc-min entries (Lopez de Prado clusterKMeansTop: k-means base over k = 2..n - 1, every k to 40 and a
              10% geometric grid above refined around the best, scored by the silhouette t on the exact distances; the
              below-mean clusters are re-clustered and the result is kept only if the mean cluster t rises). The scan
              and a warning when a cap binds or k = 2 wins go to summary.json (onc)
  SPA/StepM   Hansen SPA (consistent) and Romano-Wolf StepM over the ONC medoids + each cluster's best cell + production
              + every flagged cell
  DSR         deflated Sharpe at N_eff on per-match Sharpe with the per-match skew and kurtosis; SR0's variance is taken
              across the N_eff cluster-mean series, each Sharpe over its members' tour universe (each cell's SR is over
              its own). Family B: per-entry Sharpe at its own trial count.
  production  the config whose overrides equal production's spec by value (H: the ratchet off), not by id
  sensitivity section 5: range of mean net per match across a knob's levels, a config counting for a knob when it differs
              from the baseline (--baseline, else meta.baseline, else production) by value in that A1 knob alone; ranked
              by range, ties by the section 5 order; A2 runs only if stage 2 on H-DISC ranks six knobs
  PBO         CSCV over the folds for the stage's config selection (the 'all' cells)
  $/h         net / pool wall-clock hours (pool units clipped to the data span, embargoed hours left out) and net /
              live-match hours (A7)
  registry    one row per scored cell (N_raw per family), ids carry the arm, for registry/tennis-ta-<run>.jsonl

Usage: tennis_ta_report.py --shards DIR --pool disc[,check] --run RUN_ID --out DIR [--plan prep/plan.json]
       [--units models/tennis-ta/state/units.json] [--boot 2000] [--block 1] [--seed 20261105] [--baseline CONFIG]
"""
import argparse
import gzip
import hashlib
import json
import math
import os
import sys
import warnings
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta

import numpy as np

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
DEFAULT_UNITS = os.path.join(REPO, 'models', 'tennis-ta', 'state', 'units.json')
PHASES = ['pre', 'e20', 'p1', 'p2', 'p3']
BUCKETS = ['8-15', '15-25', '75-85', '85-92', 'other']
ARMS = ('F0', 'F1', 'F2', 'coin')
EULER = 0.5772156649015329
DAY_MS = 86_400_000
HOUR_MS = 3_600_000
DEFAULT_EP_COLS = ['m', 'k', 't', 'leg', 'px', 'n', 'ph', 'sig', 'x', 'hold', 'pnl', 'br']
PROD_KNOBS = {'TENNIS_CONF_MOMENTUM_CENTS': 0.01, 'TENNIS_CONF_FLOW': 0.2, 'TENNIS_CONF_OPPONENT_CENTS': 0.01, 'TENNIS_CONF_WINDOW_SEC': 60}
# The section 5 A1 knobs in the order listed there (the A2 tie-break), env-style, with production's defaults (bot/config.ts
# loadConfig; tests/test_tennis_ta_report.py checks them against it). The I48 exit-floor arms are gone (Amendment 3:
# production's after-fee floor, MatchMarket.breakEven, replaced them); TENNIS_END_ENTRY_MARGIN joins the stage 2 knobs
# (Amendment 3) and sorts after the section 5 list.
A1_KNOBS = (
    ('TENNIS_CONF_WINDOW_SEC', 60), ('TENNIS_CONF_MOMENTUM_CENTS', 0.01), ('TENNIS_CONF_FLOW', 0.2), ('TENNIS_CONF_OPPONENT_CENTS', 0.01),
    ('TENNIS_ENTRY_MIN_SIGNALS_PRE', 1), ('TENNIS_ENTRY_MIN_SIGNALS_LIVE', 2), ('TENNIS_FAV_ENTRY_MIN_SIGNALS', 2), ('TENNIS_HUNT_MIN_SIGNALS', 2),
    ('TENNIS_UNDERDOG_MAX', 0.25), ('TENNIS_UNDERDOG_MIN', 0.08), ('TENNIS_TP_PCT', 0.40), ('TENNIS_TP_CENTS', 0.06), ('TENNIS_FAV_MIN', 0.75),
    ('TENNIS_FAV_MAX', 0.92), ('TENNIS_FAV_MIN_PROGRESS', 0.5), ('TENNIS_HUNT_MAX_SEC', 180), ('TENNIS_HUNT_TRAIL_TICKS', 2), ('TENNIS_TRAIL', True),
    ('TENNIS_UNDERDOG_LATE_PROGRESS', 0.35), ('TENNIS_UNDERDOG_CUT_PROGRESS', 0.6), ('TENNIS_MAX_SPREAD', 0.03), ('HARNESS_LOSER_STOP', 0),
    ('TENNIS_END_ENTRY_MARGIN', 0.05),
)
R_ONLY_KNOBS = {'TENNIS_CONF_DEPTH': 0.2}  # swept on R only, reported as a lead, never ranked or passed (section 5)
# Settings that are not hypotheses: stress adversaries (section 7) and measuring sticks. A run that moves one off its
# default must be a measuring stick (stick: true).
STICK_KEYS = {'HARNESS_FEE_MULT': 1, 'HARNESS_LATENCY_MS': 0, 'HARNESS_PACER': 'tennis', 'HARNESS_BANKROLL': 200, 'TENNIS_END_LOSER_CUT': True}
KNOB_DEFAULTS = dict(A1_KNOBS, **R_ONLY_KNOBS, **STICK_KEYS, TENNIS_TRAIL_RATCHET=True)
KNOB_ORDER = {k: i for i, (k, _) in enumerate(A1_KNOBS)}
# Production's spec per stratum: on H the ratchet is off for every spec (section 4), so that is production's point there.
PROD_SPEC = {'H': {'TENNIS_TRAIL_RATCHET': False}, 'R': {}}
STATE_RESTART = ('cross-match state (tennis-only pacer, 25% / 10% caps, coin-placebo stream, family B placebo reservoir) '
                 'restarts only at unit edges')


def ms_of(iso):
    return int(round(datetime.fromisoformat(iso.replace('Z', '+00:00')).timestamp() * 1000))


def day_ms(day):
    return ms_of(day + 'T00:00:00Z')


def day_of(ts_ms):
    return datetime.fromtimestamp(ts_ms / 1000, timezone.utc).strftime('%Y-%m-%d')


HARD_CUTOFF = ms_of('2026-11-05T02:00:00Z')
CHECK_FROM = ms_of('2026-04-01T00:00:00Z')
EMBARGO_MS = DAY_MS


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


def buckets_of(px):
    px = np.asarray(px, dtype=float)
    out = np.full(len(px), 'other', dtype='<U5')
    out[(px >= 0.08 - 1e-9) & (px < 0.15 - 1e-9)] = '8-15'
    out[(px >= 0.15 - 1e-9) & (px <= 0.25 + 1e-9)] = '15-25'
    out[(px >= 0.75 - 1e-9) & (px < 0.85 - 1e-9)] = '75-85'
    out[(px >= 0.85 - 1e-9) & (px <= 0.92 + 1e-9)] = '85-92'
    return out


def tour(series):
    return {'KXATPMATCH': 'ATP', 'KXWTAMATCH': 'WTA'}.get(series, series)


def _dst_bounds(year):
    mar = datetime(year, 3, 8, 7, tzinfo=timezone.utc)
    mar += timedelta(days=(6 - mar.weekday()) % 7)
    nov = datetime(year, 11, 1, 6, tzinfo=timezone.utc)
    nov += timedelta(days=(6 - nov.weekday()) % 7)
    return mar, nov


def eastern(ts_ms):
    """America/New_York without tzdata: EDT from the second Sunday of March 07:00 UTC to the first Sunday of November 06:00 UTC."""
    t = datetime.fromtimestamp(ts_ms / 1000, timezone.utc)
    mar, nov = _dst_bounds(t.year)
    dst = mar <= t < nov
    return (t - timedelta(hours=4 if dst else 5)), ('EDT' if dst else 'EST')


def eastern_hours(ts_ms):
    """Hour of day (America/New_York) of each ms timestamp, vectorised."""
    ts = np.asarray(ts_ms, dtype=np.float64)
    if not len(ts):
        return np.zeros(0, dtype=int)
    years = ts.astype('datetime64[ms]').astype('datetime64[Y]').astype(int) + 1970
    off = np.full(len(ts), 5.0)
    for y in np.unique(years):
        a, b = _dst_bounds(int(y))
        sel = (years == y) & (ts >= a.timestamp() * 1000) & (ts < b.timestamp() * 1000)
        off[sel] = 4.0
    return (np.floor((ts - off * HOUR_MS) / HOUR_MS) % 24).astype(int)


def fmt_eastern(ts_ms, pattern):
    t, z = eastern(ts_ms)
    return t.strftime(pattern) + ' ' + z


def norm_ppf(p):
    from scipy.stats import norm
    return float(norm.ppf(p))


def norm_cdf(x):
    from scipy.stats import norm
    return float(norm.cdf(x))


def clean(o):
    """JSON-safe: NaN and +-inf become null, numpy scalars and arrays become Python values."""
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, np.ndarray):
        return clean(o.tolist())
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, (float, np.floating)):
        f = float(o)
        return f if math.isfinite(f) else None
    return o


def dumps(o, **kw):
    return json.dumps(clean(o), allow_nan=False, **kw)


def finite(x):
    return x is not None and isinstance(x, (int, float, np.floating, np.integer)) and math.isfinite(float(x))


# ---------------------------------------------------------------------------------------------------------------------
# Overrides by value (a key that is present at its default value is no change; an absent key is the default)

def knob_val(key, v):
    """One override value, normalised for comparison: numbers by value, booleans as loadConfig parses them."""
    if isinstance(KNOB_DEFAULTS.get(key), bool) or isinstance(v, bool):
        if v is True or (isinstance(v, str) and v.strip() in ('true', '1')) or (type(v) in (int, float) and v == 1):
            return 'true'
        if v is False or (isinstance(v, str) and v.strip() in ('false', '0')) or (type(v) in (int, float) and v == 0):
            return 'false'
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return format(float(v), '.12g')
    s = str(v).strip()
    try:
        return format(float(s), '.12g')
    except ValueError:
        return s


def ov_val(overrides, key):
    """A key's effective value in a run: its override, else production's default (None when unknown and unset)."""
    if key in overrides:
        return knob_val(key, overrides[key])
    return knob_val(key, KNOB_DEFAULTS[key]) if key in KNOB_DEFAULTS else None


def diff_keys(o1, o2):
    """The keys whose effective values differ between two override sets (values, not key presence)."""
    return {k for k in set(o1) | set(o2) if ov_val(o1, k) != ov_val(o2, k)}


def is_production(overrides, stratum='H'):
    """Production's spec on this stratum, by value: every override at production's default (H: the ratchet off)."""
    return not diff_keys(overrides, PROD_SPEC.get(stratum or 'H', {}))


def canon_overrides(overrides):
    """The overrides minus the keys at production's default, as a comparable key."""
    return tuple(sorted((k, ov_val(overrides, k)) for k in overrides if k not in KNOB_DEFAULTS or ov_val(overrides, k) != knob_val(k, KNOB_DEFAULTS[k])))


def check_runs(run_lists, stratum='H'):
    """Problems with the run list that would mislink arms or score a non-hypothesis (empty = sound). run_lists: one
    {id: run} per shard file. Every non-stick run's id ends in its arm (F0, F1, F2 as its fill; coin for the coin placebo),
    the arms of one config run the same overrides, no stress / measuring key is moved off its default outside a measuring
    stick, and no two non-placebo runs share overrides and fill (they differ only in the decision-clock offset, a noise
    floor adversary, or are twins); a run is the same in every file."""
    p = []
    if not run_lists:
        return p
    ref = run_lists[0]
    for f, rl in enumerate(run_lists[1:], 1):
        for rid, r in rl.items():
            q = ref.get(rid)
            if q is not None and any(json.dumps(q.get(k), sort_keys=True) != json.dumps(r.get(k), sort_keys=True)
                                     for k in ('overrides', 'fill', 'placebo', 'stick', 'offsetMs')):
                p.append(f'run {rid}: its overrides, fill, placebo, stick or offset differ across the shard files')
    cfg_ov, twins = {}, {}
    for rid in sorted(ref):
        r = ref[rid]
        if r['stick']:
            continue
        parts = rid.rsplit('|', 1)
        want = 'coin' if r.get('placebo') == 'coin' else (r.get('fill') or 'F1')
        if len(parts) != 2 or parts[1] not in ARMS:
            p.append(f"run {rid}: a non-stick run's id must end in its arm (|F0, |F1, |F2 or |coin) so its arms link to one config "
                     f"(a measuring stick carries stick: true)")
            continue
        if parts[1] != want:
            p.append(f"run {rid}: its id names arm {parts[1]} but it runs {'the coin placebo' if want == 'coin' else 'fill ' + want}")
        ov = json.dumps(r['overrides'], sort_keys=True)
        if parts[0] in cfg_ov and cfg_ov[parts[0]][0] != ov:
            p.append(f'config {parts[0]}: its arms {cfg_ov[parts[0]][1]} and {rid} run different overrides')
        cfg_ov.setdefault(parts[0], (ov, rid))
        moved = [k for k in STICK_KEYS if k in r['overrides'] and ov_val(r['overrides'], k) != knob_val(k, STICK_KEYS[k])]
        if moved:
            p.append(f"run {rid}: moves {', '.join(moved)} (a stress adversary or measuring setting, never a hypothesis) but is not a "
                     f"measuring stick: mark it stick: true")
        if want != 'coin':
            key = (canon_overrides(r['overrides']), r.get('fill'), r.get('offsetMs') or 0)
            if key in twins:
                p.append(f'runs {twins[key]} and {rid} run the same overrides and fill: arms that differ only in the decision-clock '
                         f'offset are noise-floor adversaries (mark them stick: true); anything else is a twin')
            else:
                twins[key] = rid
    return p


def knob_sensitivity(rows, base_cfg, stage, pools, stratum):
    """The section 5 rule: a knob's sensitivity is the range of mean net per match across its levels with every other
    knob at the baseline. rows: {config: (overrides, mean per match)} of the F1 'all' cells. A config enters a knob's
    levels when it differs from the baseline, by value, in that A1 knob alone; configs moving 2+ knobs (pairwise,
    factorial) or a non-knob setting are left out. Ranked by range, ties by the section 5 order; A2 (the 729-config
    factorial) runs only if stage 2 on H-DISC ranks six knobs."""
    out = {'rule': "range of mean net per match (F1, all matches) across a knob's levels, the others at the baseline; "
                   'ties by the section 5 order', 'baseline': base_cfg, 'knobs': {}, 'ranking': [], 'multi_knob': 0, 'not_knobs': {},
           'top6': None, 'a2_runs': False}
    if base_cfg not in rows:
        out['a2_reason'] = f'no F1 run of the baseline config {base_cfg}: nothing is ranked'
        return out
    base_ov, base_mean = rows[base_cfg]
    levels, cfgs = defaultdict(lambda: defaultdict(list)), defaultdict(list)
    eligible_keys = set(KNOB_ORDER) | set(R_ONLY_KNOBS)
    for cfg, (ov, mean) in sorted(rows.items()):
        if cfg == base_cfg:
            continue
        d = diff_keys(ov, base_ov)
        if len(d) == 1 and next(iter(d)) in eligible_keys:
            k = next(iter(d))
            levels[k][ov_val(ov, k)].append(mean)
            cfgs[k].append(cfg)
        elif d and d <= eligible_keys:
            out['multi_knob'] += 1
        else:
            out['not_knobs'][cfg] = sorted(d - eligible_keys)
    for k, lv in levels.items():
        bl = ov_val(base_ov, k)
        lv[bl].append(base_mean)
        ms = {lvl: float(np.mean(v)) for lvl, v in sorted(lv.items(), key=lambda kv: _level_key(kv[0]))}
        out['knobs'][k] = {'levels': ms, 'baseline_level': bl, 'range': max(ms.values()) - min(ms.values()), 'configs': cfgs[k],
                           'order': KNOB_ORDER.get(k), 'r_only': k in R_ONLY_KNOBS}
    ranked = [k for k, v in out['knobs'].items() if not v['r_only'] and len(v['levels']) >= 2 and math.isfinite(v['range'])]
    out['ranking'] = sorted(ranked, key=lambda k: (-out['knobs'][k]['range'], KNOB_ORDER[k]))
    if str(stage) != '2':
        out['a2_reason'] = f'stage {stage}: A2 is decided on stage 2\'s ranking ({len(ranked)} knob(s) ranked here)'
    elif pools != ['disc'] or (stratum or 'H') != 'H':
        out['a2_reason'] = f'A2 is chosen from H-DISC numbers only (this report: pool {",".join(pools)}, stratum {stratum or "H"})'
    elif len(ranked) < 6:
        out['a2_reason'] = f'stage 2 ranks {len(ranked)} knob(s), fewer than six: A2 does not run'
    else:
        out.update(top6=out['ranking'][:6], a2_runs=True, a2_reason='stage 2 ranks six or more knobs on H-DISC')
    return out


def factorial_main_effects(rows, prod_ov):
    """Stage 1's threshold factorial (descriptive): mean net per match by level of each of the four thresholds, averaged
    over the configs that differ from production only in those thresholds (by value)."""
    lv = defaultdict(lambda: defaultdict(list))
    for ov, mean in rows.values():
        if diff_keys(ov, prod_ov) <= set(PROD_KNOBS):
            for k in PROD_KNOBS:
                lv[k][ov_val(ov, k)].append(mean)
    out = {}
    for k, v in lv.items():
        if len(v) >= 2:
            ms = {lvl: float(np.mean(x)) for lvl, x in sorted(v.items(), key=lambda kv: _level_key(kv[0]))}
            out[k] = {'levels': ms, 'range': max(ms.values()) - min(ms.values()), 'configs': max(len(x) for x in v.values())}
    return out


# ---------------------------------------------------------------------------------------------------------------------
# Units and pools (the same rules as research/tennisTaSweep.ts)

def unit_fold(u):
    """The fold of a unit: the month of its last day (the Sunday before its Monday 05:00 UTC end)."""
    return day_of(u['end'] - DAY_MS)[:7]


def unit_pool(u, cutoff=HARD_CUTOFF):
    if u['start'] >= cutoff:
        return 'out'
    if u.get('sealed'):
        return 'sealed'
    return 'disc' if u['start'] < CHECK_FROM else 'check'


def subtract(a, b, cuts):
    parts = [(a, b)] if a < b else []
    for c, d in cuts:
        nxt = []
        for x, y in parts:
            if d <= x or c >= y:
                nxt.append((x, y))
                continue
            if c > x:
                nxt.append((x, c))
            if d < y:
                nxt.append((d, y))
        parts = nxt
    return parts


def pool_spans_from_table(table, pools, only):
    """Fallback when neither the plan nor the shard metas carry poolSpans: each swept pool unit cut at the hard cutoff,
    minus the 24 h embargo windows of the sealed units."""
    cuts = []
    for s in table:
        if s.get('sealed'):
            cuts += [(s['start'] - EMBARGO_MS, s['start']), (s['end'], s['end'] + EMBARGO_MS)]
    out = []
    for u in table:
        if unit_pool(u) in pools and u['id'] in only:
            iv = subtract(u['start'], min(u['end'], HARD_CUTOFF), cuts)
            out.append({'unit': u['id'], 'start': u['start'], 'end': u['end'], 'intervals': [list(x) for x in iv],
                        'hours': sum(b - a for a, b in iv) / HOUR_MS})
    return out


def clipped_hours(spans, lo, hi):
    return sum(max(0, min(b, hi) - max(a, lo)) for s in spans for a, b in s['intervals']) / HOUR_MS


# ---------------------------------------------------------------------------------------------------------------------
# Reading and checking the shard set

def ep_columns(rows, cols):
    """Episode rows (lists in meta.episodeCols order) as numpy columns."""
    n = len(rows)
    if not n:
        return {'m': np.zeros(0, dtype=np.int64), 't': np.zeros(0), 'hold': np.zeros(0), 'px': np.zeros(0), 'pnl': np.zeros(0),
                'sig': np.zeros(0, dtype=np.int64), 'br': np.zeros(0, dtype=np.int64), 'ph': np.zeros(0, dtype='<U4'),
                'leg': np.zeros(0, dtype='<U4'), 'x': np.zeros(0, dtype='<U4')}
    d = dict(zip(cols, zip(*rows)))
    z = (0,) * n

    def num(c, dt):
        return np.asarray([0 if v is None else v for v in d.get(c, z)], dtype=dt)
    return {'m': num('m', np.int64), 't': num('t', np.float64), 'hold': num('hold', np.float64), 'px': num('px', np.float64),
            'pnl': num('pnl', np.float64), 'sig': num('sig', np.int64), 'br': num('br', np.int64),
            'ph': np.asarray([str(v) for v in d.get('ph', ('',) * n)]), 'leg': np.asarray([str(v) for v in d.get('leg', ('',) * n)]),
            'x': np.asarray([str(v) for v in d.get('x', ('',) * n)])}


def read_shard(path):
    """One shard file -> (info for the set check, compact data for scoring)."""
    name = os.path.basename(path)
    with gzip.open(path, 'rt') as fh:
        d = json.load(fh)
    meta, ml, runs = d.get('meta'), d.get('matchList'), d.get('runs')
    if not isinstance(meta, dict) or not isinstance(ml, list) or not isinstance(runs, list):
        raise ValueError(f'{name}: not a shard file (meta, matchList and runs expected)')
    problems = []
    n = len(ml)
    cols = meta.get('episodeCols') or DEFAULT_EP_COLS
    sticks = set(meta.get('sticks') or [])
    rd = {}
    for r in runs:
        rid = r.get('id')
        if rid in rd:
            problems.append(f'{name}: run {rid} appears twice')
            continue
        pnl = r.get('pnl') or []
        if len(pnl) != n:
            problems.append(f'{name}: run {rid} has {len(pnl)} match values for {n} matches')
        ep = ep_columns(r.get('episodes') or [], cols)
        if len(ep['m']) and (ep['m'].min() < 0 or ep['m'].max() >= n):
            problems.append(f'{name}: run {rid} has episodes outside its match list')
        rd[rid] = {'id': rid, 'overrides': r.get('overrides') or {}, 'fill': r.get('fill'), 'placebo': r.get('placebo'),
                   'stick': r.get('stick') is True or rid in sticks, 'offsetMs': r.get('offsetMs'), 'pnl': np.asarray(pnl, dtype=np.float64), 'ep': ep}
    fb = d.get('familyB')
    events = [m.get('event') for m in ml]
    b_diag = (fb.get('diagnostics') or {}) if isinstance(fb, dict) else {}
    info = {'file': name, 'meta': meta, 'events': events, 'run_ids': tuple(sorted(rd)), 'has_b': fb is not None,
            'b_design': fb.get('designSize') if isinstance(fb, dict) else None, 'b_stratum': fb.get('stratum') if isinstance(fb, dict) else None,
            'b_tours': b_diag.get('tours'), 'b_phases': (b_diag.get('settings') or {}).get('phasesInDesign'),
            'row_units': {m.get('unit') for m in ml}, 'b_units': ({u for c in fb.get('cells', []) for u in (c.get('units') or {})} if isinstance(fb, dict) else set()),
            'problems': problems}
    return info, {'matches': ml, 'runs': rd, 'familyB': fb}


CONSISTENT = ('run', 'stage', 'pool', 'simVersion', 'dataVersion', 'families', 'shards')
CONSISTENT_IF_SET = ('requestSha', 'unitsSha', 'stratum')
REQUIRED = ('run', 'stage', 'pool', 'simVersion', 'dataVersion', 'families', 'shards', 'subShards', 'k', 'j', 'from', 'to', 'units')


def _isint(x):
    return isinstance(x, int) and not isinstance(x, bool)


def design_b(infos):
    """Family B's design size (BH m) over the whole shard set -> (size, problems). A study states
    designSize = base x (1 + phases x buckets x tours it saw) (tennisTaSignals designSize()), so a slice that saw fewer
    tours, or no match at all, states a smaller design; the set's design is base x (1 + phases x buckets x the union of
    the tours the slices saw). base and phases must agree across the files. Files without the tour list must agree exactly."""
    bs = [i for i in infos if i['has_b']]
    if not bs:
        return None, []
    if any(not isinstance(i.get('b_tours'), list) or not isinstance(i.get('b_phases'), list) for i in bs):
        sizes = {str(i['b_design']) for i in bs}
        if len(sizes) > 1:
            return None, [f'familyB designSize differs across the shard files: {sorted(sizes)}']
        return bs[0]['b_design'], []
    p, parts, tours = [], set(), set()
    for i in bs:
        per = 1 + len(i['b_phases']) * len(BUCKETS) * len(i['b_tours'])
        size = i['b_design']
        if not _isint(size) or size <= 0 or size % per:
            p.append(f"{i['file']}: familyB designSize {size} is not a whole multiple of its {per} contexts")
            continue
        parts.add((size // per, len(i['b_phases'])))
        tours.update(i['b_tours'])
    if len(parts) > 1:
        p.append(f'familyB design (series x directions x exits, phases) differs across the shard files: {sorted(parts)}')
    if p:
        return None, p
    base, phases = next(iter(parts))
    return base * (1 + phases * len(BUCKETS) * len(tours)), []


def check_shard_set(infos, table, plan=None, run=None, allow_unversioned=False, dir_files=None):
    """Every problem with a shard set (empty = sound). Nothing may be scored or written unless this is empty."""
    p = []
    if not infos:
        return ['no shard file was read']
    by_id = {u['id']: u for u in table}
    metas = [i['meta'] for i in infos]
    for i in infos:
        for key in REQUIRED:
            if i['meta'].get(key) in (None, ''):
                p.append(f"{i['file']}: meta.{key} is missing")
        p.extend(i['problems'])
    for key in CONSISTENT + CONSISTENT_IF_SET:
        vals = [m.get(key) for m in metas]
        if key in CONSISTENT_IF_SET and all(v is None for v in vals):
            continue
        s = sorted({json.dumps(v, sort_keys=True) for v in vals})
        if len(s) > 1:
            p.append(f'meta.{key} differs across the shard files: {" / ".join(s)[:300]}')
    if not allow_unversioned and any(m.get('dataVersion') in (None, '', 'unversioned') for m in metas):
        p.append('a shard file has no data version (pass --allow-unversioned only for a local run)')
    if run is not None and any(str(m.get('run')) != str(run) for m in metas):
        p.append(f"the shard files are from run(s) {sorted({str(m.get('run')) for m in metas})}, not run {run}")

    # Every (k, j) of shards x subShards exactly once.
    S = metas[0].get('shards')
    if not _isint(S) or S < 1:
        p.append(f'meta.shards is {S!r}, not a positive integer')
        S = 0
    by_k = defaultdict(list)
    for i in infos:
        k, j = i['meta'].get('k'), i['meta'].get('j')
        if not _isint(k) or not _isint(j) or not (0 <= k < S):
            p.append(f"{i['file']}: (k, j) = ({k!r}, {j!r}) is outside the {S} shard(s)")
            continue
        by_k[k].append(i)
    for k in range(S):
        fs = by_k.get(k, [])
        if not fs:
            p.append(f'shard {k}: no file (all of its sub-slices are missing)')
            continue
        subs = {f['meta'].get('subShards') for f in fs}
        if len(subs) != 1 or not _isint(next(iter(subs))) or next(iter(subs)) < 1:
            p.append(f'shard {k}: meta.subShards is not one positive integer ({sorted(map(str, subs))})')
            continue
        J = next(iter(subs))
        cnt = defaultdict(list)
        for f in fs:
            cnt[f['meta'].get('j')].append(f['file'])
        for j in range(J):
            if not cnt.get(j):
                p.append(f'shard {k} sub-slice {j}: missing')
            elif len(cnt[j]) > 1:
                p.append(f'shard {k} sub-slice {j}: {len(cnt[j])} files ({", ".join(sorted(cnt[j]))}): a duplicate')
        for j in cnt:
            if not (0 <= j < J):
                p.append(f'shard {k} sub-slice {j}: outside its {J} sub-slice(s) ({", ".join(cnt[j])})')

    # Families: familyB present exactly when meta.families says so; one design and one stratum.
    for i in infos:
        fam = i['meta'].get('families') or []
        if 'B' in fam and not i['has_b']:
            p.append(f"{i['file']}: meta.families includes B but the file has no familyB")
        if 'B' not in fam and i['has_b']:
            p.append(f"{i['file']}: the file has familyB but meta.families is {fam}")
    p += design_b(infos)[1]
    if len({i['b_stratum'] for i in infos if i['has_b']}) > 1:
        p.append('familyB stratum differs across the shard files')

    # The same runs in every file.
    ref = infos[0]
    for i in infos[1:]:
        if i['run_ids'] != ref['run_ids']:
            miss, extra = set(ref['run_ids']) - set(i['run_ids']), set(i['run_ids']) - set(ref['run_ids'])
            p.append(f"{i['file']}: its runs differ from {ref['file']} ({len(miss)} missing, {len(extra)} extra)")

    # Match events unique across the set.
    seen = {}
    dups = []
    for i in infos:
        for e in i['events']:
            if e in seen:
                dups.append(f'{e} ({seen[e]}, {i["file"]})')
            else:
                seen[e] = i['file']
    if dups:
        p.append(f'{len(dups)} match event(s) appear twice: {"; ".join(dups[:5])}')

    # Units: in the table, each swept once, slices at unit edges, no pool unit skipped between the first and the last.
    unit_file = {}
    for i in sorted(infos, key=lambda x: (x['meta'].get('k') if _isint(x['meta'].get('k')) else -1, x['meta'].get('j') if _isint(x['meta'].get('j')) else -1)):
        m = i['meta']
        us = m.get('units') or []
        bad = [u for u in us if u not in by_id]
        if bad:
            p.append(f"{i['file']}: unit(s) {', '.join(bad[:5])} are not in the unit table")
            continue
        for u in us:
            if u in unit_file:
                p.append(f"unit {u}: swept by both {unit_file[u]} and {i['file']}")
            else:
                unit_file[u] = i['file']
        if us:
            starts = [by_id[u]['start'] for u in us]
            if starts != sorted(starts):
                p.append(f"{i['file']}: meta.units are not in start order")
            first, last = by_id[us[0]], by_id[us[-1]]
            if m.get('from') != first['startDay']:
                p.append(f"{i['file']}: meta.from {m.get('from')} is not its first unit's start day {first['startDay']}")
            want_to = day_of(day_ms(day_of(last['end'])) + DAY_MS)
            if m.get('to') != want_to:
                p.append(f"{i['file']}: meta.to {m.get('to')} is not the day after its last unit's end ({want_to})")
        outside = {u for u in i['row_units'] if u not in set(us)}
        if outside:
            p.append(f"{i['file']}: match rows in unit(s) outside the slice: {sorted(map(str, outside))[:5]}")
        if i['b_units'] - set(us):
            p.append(f"{i['file']}: familyB cells name unit(s) outside the slice: {sorted(i['b_units'] - set(us))[:5]}")
    pool = metas[0].get('pool')
    swept = sorted(unit_file, key=lambda u: by_id[u]['start'])
    for a_, b_ in zip(swept, swept[1:]):
        gap = [u['id'] for u in table if by_id[a_]['start'] < u['start'] < by_id[b_]['start'] and unit_pool(u) == pool]
        if gap:
            p.append(f"unit(s) {', '.join(gap[:5])} of pool {pool} lie between {a_} and {b_} but no shard file swept them")

    # Against the plan (prep/plan.json), when given.
    if plan is not None:
        expected = list(plan.get('expected') or [])
        files = set(dir_files if dir_files is not None else [i['file'] for i in infos])
        for n in expected:
            if n not in files:
                p.append(f'{n}: planned but missing')
        for n in sorted(files - set(expected)):
            p.append(f'{n}: not in the plan')
        subplans = plan.get('subPlans') or []
        want_fam = ['A', 'B'] if plan.get('familyB') else ['A']
        for i in infos:
            m = i['meta']
            k, j = m.get('k'), m.get('j')
            for key, want in (('stage', plan.get('stage')), ('pool', plan.get('pool')), ('requestSha', plan.get('requestSha')),
                              ('simVersion', plan.get('simVersion')), ('families', want_fam), ('shards', len(plan.get('plan') or []))):
                if want is not None and json.dumps(m.get(key)) != json.dumps(want):
                    p.append(f"{i['file']}: meta.{key} {json.dumps(m.get(key))}, the plan has {json.dumps(want)}")
            if plan.get('unitsSha') and m.get('unitsSha') is not None and m.get('unitsSha') != plan.get('unitsSha'):
                p.append(f"{i['file']}: meta.unitsSha differs from the plan")
            if not (_isint(k) and _isint(j) and 0 <= k < len(subplans) and 0 <= j < len(subplans[k])):
                p.append(f"{i['file']}: (k, j) = ({k}, {j}) is not a sub-slice of the plan")
                continue
            sub = subplans[k][j]
            if m.get('subShards') != len(subplans[k]):
                p.append(f"{i['file']}: meta.subShards {m.get('subShards')}, the plan has {len(subplans[k])}")
            for key in ('from', 'to', 'units'):
                if json.dumps(m.get(key)) != json.dumps(sub.get(key)):
                    p.append(f"{i['file']}: meta.{key} differs from the plan's sub-slice ({k}, {j})")
        pu = set(plan.get('units') or [])
        if pu:
            if pu - set(unit_file):
                p.append(f'{len(pu - set(unit_file))} planned unit(s) swept by no shard file: {sorted(pu - set(unit_file))[:5]}')
            if set(unit_file) - pu:
                p.append(f'unit(s) swept but not planned: {sorted(set(unit_file) - pu)[:5]}')
    return p


def merge_cells_b(exports):
    """Family B cells merged across the shards by id: moments summed, unit and day maps merged."""
    cells, order, problems = {}, [], []
    for fb in exports:
        for c in fb.get('cells') or []:
            cid = c['id']
            acc = cells.get(cid)
            if acc is None:
                acc = cells[cid] = {'id': cid, 'group': c.get('group'), 'n': 0, 'sum': 0.0, 'sumSq': 0.0, 'sum3': 0.0, 'sum4': 0.0,
                                    'breaches': 0, 'gross': 0.0, 'fees': 0.0, 'stressSum': 0.0, 'units': {}, 'days': {}}
                order.append(cid)
            elif acc['group'] != c.get('group'):
                problems.append(f"familyB cell {cid}: group {c.get('group')} in one shard, {acc['group']} in another")
            for k in ('n', 'sum', 'sumSq', 'sum3', 'sum4', 'breaches', 'gross', 'fees', 'stressSum'):
                acc[k] += c.get(k) or 0
            for u, v in (c.get('units') or {}).items():
                cur = acc['units'].setdefault(u, [0, 0.0, 0, 0.0])
                for q in range(4):
                    cur[q] += v[q] if q < len(v) and v[q] is not None else 0
            for dd, v in (c.get('days') or {}).items():
                cur = acc['days'].setdefault(dd, [0, 0.0])
                cur[0] += v[0]
                cur[1] += v[1]
    return [cells[i] for i in order], problems


def load(shard_dir, table, plan=None, run=None, allow_unversioned=False):
    """Read, check and merge the shard set. Returns (merged, infos) or exits non-zero listing every problem."""
    try:
        files = sorted(f for f in os.listdir(shard_dir) if f.endswith('.json.gz'))
    except OSError as e:
        sys.exit(f'cannot list {shard_dir}: {e}')
    if not files:
        sys.exit(f'no shard files in {shard_dir}: nothing is scored and no registry rows are written')
    infos, datas, problems = [], [], []
    for f in files:
        try:
            info, data = read_shard(os.path.join(shard_dir, f))
        except Exception as e:  # noqa: BLE001 - every unreadable file is a problem of the set
            problems.append(f'{f}: unreadable ({type(e).__name__}: {str(e)[:200]})')
            continue
        infos.append(info)
        datas.append(data)
    problems += check_shard_set(infos, table, plan, run, allow_unversioned, files)
    try:
        b_cells, b_problems = merge_cells_b([d['familyB'] for d in datas if d['familyB'] is not None])
    except (KeyError, TypeError, IndexError, AttributeError) as e:
        b_cells, b_problems = [], [f'familyB cells are malformed ({type(e).__name__}: {e})']
    problems += b_problems
    stratum = next((i['meta'].get('stratum') for i in infos if i['meta'].get('stratum')), 'H')
    problems += check_runs([d['runs'] for d in datas], stratum)
    if problems:
        for x in problems[:80]:
            print(f'shard set: {x}', file=sys.stderr)
        sys.exit(f'{len(problems)} problem(s) with the shard set in {shard_dir}: nothing is scored and no registry rows are written')
    order = sorted(range(len(infos)), key=lambda i: (infos[i]['meta']['k'], infos[i]['meta']['j']))
    matches, runs = [], {}
    for idx in order:
        d = datas[idx]
        off = len(matches)
        matches.extend(d['matches'])
        for rid, r in d['runs'].items():
            acc = runs.setdefault(rid, {'id': rid, 'overrides': r['overrides'], 'fill': r['fill'], 'placebo': r['placebo'],
                                        'stick': r['stick'], 'offsetMs': r.get('offsetMs'), 'pnl': [], 'ep': defaultdict(list)})
            acc['stick'] = acc['stick'] or r['stick']
            acc['pnl'].append(r['pnl'])
            for c, arr in r['ep'].items():
                acc['ep'][c].append(arr + off if c == 'm' else arr)
    for r in runs.values():
        r['pnl'] = np.concatenate(r['pnl']) if r['pnl'] else np.zeros(0)
        r['ep'] = {c: np.concatenate(v) for c, v in r['ep'].items()}
    fbs = [d['familyB'] for d in datas if d['familyB'] is not None]
    fam_b = None
    if fbs:
        diag = {}
        for fb in fbs:
            for k, v in (fb.get('diagnostics') or {}).items():
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    diag[k] = diag.get(k, 0) + v
                elif k == 'tours' and isinstance(v, list):
                    diag[k] = sorted(set(diag.get(k) or []) | set(v))
                elif isinstance(v, dict) and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in v.values()):
                    cur = diag.setdefault(k, {})  # counts by kind (exit kinds): summed over the shards
                    for kk, x in v.items():
                        cur[kk] = cur.get(kk, 0) + x
                else:
                    diag.setdefault(k, v)
        fam_b = {'stratum': fbs[0].get('stratum'), 'designSize': design_b(infos)[0], 'diagnostics': diag, 'cells': b_cells}
    metas = [infos[i]['meta'] for i in order]
    return {'matches': matches, 'runs': runs, 'familyB': fam_b, 'metas': metas, 'files': [infos[i]['file'] for i in order]}


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


def boot_p(count, B):
    """One-sided bootstrap p-value from the number of recentred exceedances: (c + 1) / (B + 1), never 0."""
    return (np.asarray(count, dtype=float) + 1.0) / (B + 1.0)


def boot_ratio(W, num_rows, den_rows, means, chunk=2048):
    """Resampled ratio means (sum of resampled numerators / sum of resampled denominators) per row, in chunks. Returns
    p (mean > 0, recentred, (c + 1) / (B + 1); a resample with no denominator counts as an exceedance), omega (the
    bootstrap SD) and the 90% interval."""
    B, n = W.shape[0], num_rows.shape[0]
    p, om, lo, hi = np.ones(n), np.zeros(n), np.zeros(n), np.zeros(n)
    for s in range(0, n, chunk):
        num = W @ num_rows[s:s + chunk].T
        den = W @ den_rows[s:s + chunk].T
        with np.errstate(divide='ignore', invalid='ignore'):
            bm = np.where(den > 0, num / np.where(den > 0, den, 1), np.nan)
        mu = means[s:s + chunk]
        bad = np.isnan(bm)
        cnt = ((bm - mu[None, :]) >= mu[None, :]).sum(axis=0) + bad.sum(axis=0)
        p[s:s + chunk] = boot_p(cnt, B)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', RuntimeWarning)
            if bad.any():
                om[s:s + chunk] = np.nan_to_num(np.nanstd(bm, axis=0, ddof=1))
                q = np.nanpercentile(bm, [5, 95], axis=0)
            else:
                om[s:s + chunk] = bm.std(axis=0, ddof=1)
                q = np.percentile(bm, [5, 95], axis=0)
        lo[s:s + chunk], hi[s:s + chunk] = np.nan_to_num(q[0]), np.nan_to_num(q[1])
    return p, om, lo, hi


def bh(p, q):
    p = np.asarray(p, dtype=float)
    m = len(p)
    rej = np.zeros(m, dtype=bool)
    if not m:
        return rej
    order = np.argsort(p)
    thresh = q * (np.arange(1, m + 1) / m)
    passed = p[order] <= thresh
    k = np.max(np.nonzero(passed)[0]) + 1 if passed.any() else 0
    rej[order[:k]] = True
    return rej


def bh_m(p, q, m_total):
    """BH over len(p) tested cells when the family holds m_total >= len(p) cells (the rest count as p = 1)."""
    p = np.asarray(p, dtype=float)
    extra = max(0, int(m_total) - len(p))
    return bh(np.concatenate([p, np.ones(extra)]), q)[:len(p)]


def day_t(d):
    """t of the mean of cluster sums (match-day clusters): mean(d) / (sd(d) / sqrt(D)); None when undefined."""
    d = np.asarray(d, dtype=float)
    if len(d) < 2:
        return None
    sd = d.std(ddof=1)
    return float(d.mean() / (sd / math.sqrt(len(d)))) if sd > 0 else None


def cluster_t_ratio(sums, counts):
    """Cluster-robust t of a mean per entry (sum / n) with clusters given by (sum_c, n_c), C / (C - 1) correction."""
    sums, counts = np.asarray(sums, dtype=float), np.asarray(counts, dtype=float)
    keep = counts > 0
    sums, counts = sums[keep], counts[keep]
    C, n = len(sums), counts.sum()
    if C < 2 or n <= 0:
        return None
    mean = sums.sum() / n
    v = C / (C - 1) * ((sums - counts * mean) ** 2).sum() / n ** 2
    return float(mean / math.sqrt(v)) if v > 0 else None


# ---------------------------------------------------------------------------------------------------------------------
# ONC (Lopez de Prado, clusterKMeansTop): k-means on the correlation distance scored by the silhouette t-stat; the
# clusters whose t is below the mean are re-clustered together, and the refinement is kept only if it raises the mean
# cluster t over the whole set (otherwise the base clustering stands).

def _pair_dist(X):
    sq = np.einsum('ij,ij->i', X, X)
    D2 = sq[:, None] + sq[None, :] - 2.0 * (X @ X.T)
    np.maximum(D2, 0, out=D2)
    D = np.sqrt(D2)
    np.fill_diagonal(D, 0.0)
    return D


def _cluster_ts(sil, labels):
    out = {}
    for c in np.unique(labels):
        s = sil[labels == c]
        sd = s.std()
        out[int(c)] = float(s.mean() / sd) if sd > 0 else 0.0
    return out


ONC_DENSE_K = 40     # every k up to this is scanned
ONC_K_RATIO = 1.1    # above it, a geometric grid of k (each step at most 10% wider), refined around the best
ONC_REFINE_TOP = 3   # the gaps next to the 3 best k of the grid are filled in until they are adjacent


def _k_grid(k_hi, dense=ONC_DENSE_K, ratio=ONC_K_RATIO):
    """Every k in [2, dense], then a geometric grid up to k_hi (k_hi itself included)."""
    ks = list(range(2, min(k_hi, dense) + 1))
    k = ks[-1] if ks else 2
    while k < k_hi:
        k = min(k_hi, max(k + 1, int(k * ratio + 1e-9)))
        ks.append(k)
    return ks


def _kmeans_space(X, dim, seed):
    """The rows of X for k-means: X itself (centred) when it has at most `dim` rows, so every distance is exact; else its
    top `dim` principal components (the rows' distances up to the variance left out, returned as the kept share). Only
    k-means runs in this space: every silhouette is taken on the exact distances."""
    Xc = X - X.mean(axis=0, keepdims=True)
    n = X.shape[0]
    if not dim or dim <= 0 or n <= dim:
        return Xc, 1.0
    from sklearn.utils.extmath import randomized_svd
    U, S, _ = randomized_svd(Xc, int(dim), n_iter=4, random_state=seed % (2 ** 31))
    tot = float((Xc ** 2).sum())
    return U * S, (float((S ** 2).sum()) / tot if tot > 0 else 1.0)


def _onc_base(X, D, seed, max_k, n_init, dim=256, diag=None):
    """clusterKMeansBase: the k whose best k-means split (of n_init) has the highest silhouette quality mean / sd.
    k runs over [2, k_hi] with k_hi = n - 1 (clusterKMeansTop's default; max_k > 0 lowers it): every k up to
    ONC_DENSE_K, a geometric grid above, and the gaps next to the best few grid points filled in until they are adjacent.
    The quality is degenerate at small k (near-uniform low silhouettes have a small sd) and peaks sharply at a block
    structure's true count, so a cap below the true count collapses N_eff toward 2; hence no fixed cap by default."""
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_samples
    n = X.shape[0]
    k_hi = n - 1 if not max_k or max_k <= 0 else min(int(max_k), n - 1)
    F, kept = _kmeans_space(X, dim, seed)
    seen = {}

    def scan(ks):
        for k in ks:
            if k in seen or k < 2 or k > k_hi:
                continue
            best = (-np.inf, None, None)
            for s in range(n_init):
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore')
                    lab = KMeans(n_clusters=k, n_init=1, random_state=(seed + 97 * k + s) % (2 ** 31)).fit(F).labels_
                nl = len(np.unique(lab))
                if nl < 2 or nl > n - 1:
                    continue
                sil = silhouette_samples(D, lab, metric='precomputed')
                sd = sil.std()
                q = sil.mean() / sd if sd > 0 else -np.inf
                if q > best[0]:
                    best = (q, lab.copy(), sil)
            seen[k] = best

    scan(_k_grid(k_hi))
    for _ in range(12):
        ks = sorted(seen)
        top = sorted(ks, key=lambda k: (-seen[k][0], k))[:ONC_REFINE_TOP]
        new = set()
        for k in top:
            i = ks.index(k)
            for a_, b_ in ((ks[i - 1] if i else k, k), (k, ks[i + 1] if i + 1 < len(ks) else k)):
                if b_ - a_ > 1:
                    step = -(-(b_ - a_) // 8)
                    new.update(range(a_ + step, b_, step))
        new -= set(seen)
        if not new:
            break
        scan(sorted(new))
    best_k = max(seen, key=lambda k: (seen[k][0], -k)) if seen else None
    if best_k is None or seen[best_k][1] is None:
        if diag is not None:
            diag.update(n=n, k_hi=k_hi, scanned=len(seen), best_k=None, best_q=None)
        return np.zeros(n, dtype=int), np.zeros(n)
    q, best, best_sil = seen[best_k]
    if diag is not None:
        ks = sorted(seen)
        diag.update(n=n, k_hi=k_hi, k_cap=(k_hi if k_hi < n - 1 else None), scanned=len(ks), best_k=int(best_k), best_q=float(q),
                    q_at_top=float(seen[ks[-1]][0]), q_k2=float(seen[2][0]) if 2 in seen else None,
                    kmeans_dims=int(F.shape[1]), kmeans_variance_kept=kept,
                    cap_binding=bool(best_k == k_hi and k_hi < n - 1),
                    q_rising_at_cap=bool(k_hi < n - 1 and len(ks) > 1 and seen[ks[-1]][0] > seen[ks[-2]][0]),
                    q_curve={str(k): round(float(seen[k][0]), 4) for k in ks if np.isfinite(seen[k][0])})
    _, best = np.unique(best, return_inverse=True)
    return best, best_sil


def onc(corr, seed, max_k=None, n_init=3, dim=256, diag=None):
    """Cluster labels for a correlation matrix (clusterKMeansTop with the quality check). max_k None or <= 0 scans k up
    to n - 1; diag (a dict) receives the top-level k scan and whether the refinement was kept."""
    from sklearn.metrics import silhouette_samples
    n = corr.shape[0]
    if n < 3:
        return np.zeros(n, dtype=int)
    X = np.sqrt(np.clip((1 - corr) / 2, 0, 1))
    D = _pair_dist(X)
    labels, sil = _onc_base(X, D, seed, max_k, n_init, dim, diag)
    if diag is not None:
        diag['refined'] = False
        diag['base_clusters'] = int(labels.max() + 1)
    if labels.max() == 0:
        return labels
    ts = _cluster_ts(sil, labels)
    q0 = float(np.mean(list(ts.values())))
    redo = [c for c, t in ts.items() if t < q0]
    if len(redo) <= 1:
        return labels
    idx = np.nonzero(np.isin(labels, redo))[0]
    if len(idx) < 3:
        return labels
    sub_k = None if not max_k or max_k <= 0 else min(max_k, len(idx) - 1)
    sub = onc(corr[np.ix_(idx, idx)], seed + 1, sub_k, n_init, dim)
    new = labels.copy()
    new[idx] = labels.max() + 1 + sub
    _, new = np.unique(new, return_inverse=True)
    if new.max() == 0 or new.max() >= n - 1:
        return labels
    sil_new = silhouette_samples(D, new, metric='precomputed')
    q1 = float(np.mean(list(_cluster_ts(sil_new, new).values())))
    if diag is not None:
        diag.update(refined=bool(q1 > q0), refine_q=[q0, q1], refined_clusters=int(new.max() + 1))
    return new if q1 > q0 else labels


# ---------------------------------------------------------------------------------------------------------------------

def parse_args(argv=None):
    ap = argparse.ArgumentParser(description='Tennis TA trial report: scores families A and B from a checked shard set.')
    ap.add_argument('--shards', required=True, help='directory of the shard files (gzip JSON)')
    ap.add_argument('--pool', default='disc', help='pool(s) to score, comma separated (a match is kept when its pool is in the list)')
    ap.add_argument('--run', default=None, help='run id; every shard file must carry it (default: the shards\' run)')
    ap.add_argument('--out', required=True)
    ap.add_argument('--plan', default=None, help='prep/plan.json: every planned file present exactly once, each matching its slice')
    ap.add_argument('--units', default=DEFAULT_UNITS, help='the unit table (models/tennis-ta/state/units.json)')
    ap.add_argument('--boot', type=int, default=2000)
    ap.add_argument('--block', type=float, default=1.0)
    ap.add_argument('--seed', type=int, default=20261105)
    ap.add_argument('--onc-min', type=int, default=100)
    ap.add_argument('--onc-cap', type=int, default=6000)
    ap.add_argument('--onc-max-k', type=int, default=0,
                    help='highest k the ONC base scan tries (default 0: n - 1, as clusterKMeansTop; a lower cap is reported and warned about when it binds)')
    ap.add_argument('--onc-dim', type=int, default=256,
                    help='k-means runs on the top DIM principal components of the distance rows when there are more cells (silhouettes stay exact)')
    ap.add_argument('--onc-init', type=int, default=3)
    ap.add_argument('--baseline', default=None,
                    help="the config (id without the arm, e.g. 'A|s2|center') the section 5 sensitivity is taken against "
                         "(default: the shards' meta.baseline, else the production config)")
    ap.add_argument('--alpha', type=float, default=0.10, help='BH q and StepM alpha')
    ap.add_argument('--allow-unversioned', action='store_true', help='local runs only: accept shards without a data version')
    return ap.parse_args(argv)


def usd(x):
    if not finite(x):
        return 'n/a'
    return f"{'-' if x < 0 else ''}${abs(x):,.2f}"


def md(x):
    """A markdown table cell: the ids' '|' separators escaped."""
    return str(x).replace('|', '\\|')


def f4(x, spec='.4f'):
    return format(x, spec) if finite(x) else '-'


def main(argv=None):
    a = parse_args(argv)
    pools = [p for p in a.pool.split(',') if p]
    try:
        with open(a.units) as fh:
            table = sorted(json.load(fh), key=lambda u: u['start'])
    except (OSError, ValueError) as e:
        sys.exit(f'cannot read the unit table {a.units}: {e}')
    unit_by_id = {u['id']: u for u in table}
    plan = None
    if a.plan:
        try:
            with open(a.plan) as fh:
                plan = json.load(fh)
        except (OSError, ValueError) as e:
            sys.exit(f'cannot read the plan {a.plan}: {e}')

    data = load(a.shards, table, plan, a.run, a.allow_unversioned)
    metas = data['metas']
    meta = metas[0]
    run_id = str(a.run if a.run is not None else meta.get('run'))
    stage = str(meta.get('stage'))
    stratum = str(meta.get('stratum') or 'H')
    sim_version = meta.get('simVersion') or meta.get('sim_version')
    data_version = meta.get('dataVersion')
    matches, runs, fam_b = data['matches'], data['runs'], data['familyB']
    if a.baseline and not any(not r['stick'] and r.get('placebo') != 'coin' and r.get('fill') == 'F1' and rid.rsplit('|', 1)[0] == a.baseline
                              for rid, r in runs.items()):
        sys.exit(f'--baseline {a.baseline}: no F1 config of that id in the shards (a config is a run id without its arm, e.g. A|s2|center): '
                 f'nothing is scored and no registry rows are written')
    rng = np.random.default_rng(a.seed)
    B = a.boot

    # ---- universe (family A): the pool(s)' owned matches with a tape, in start order
    in_pool = [i for i, m in enumerate(matches) if m.get('pool') in pools]
    keep = [i for i in in_pool if (matches[i].get('trades') or 0) > 0]
    no_tape = len(in_pool) - len(keep)
    if not keep:
        sys.exit(f'no {",".join(pools)} matches with a tape: nothing is scored and no registry rows are written')
    keep.sort(key=lambda i: (matches[i]['start'], matches[i].get('event', '')))
    remap = np.full(len(matches), -1, dtype=np.int64)
    remap[keep] = np.arange(len(keep))
    M = [matches[i] for i in keep]
    N = len(M)
    b_cells = fam_b['cells'] if fam_b else []
    b_units = {u for c in b_cells for u, v in c['units'].items() if v[0] or v[2]}
    units = sorted({m['unit'] for m in M} | b_units, key=lambda u: unit_by_id[u]['start'])
    uidx = {u: i for i, u in enumerate(units)}
    U = len(units)
    m_unit = np.array([uidx[m['unit']] for m in M])
    days = sorted({m['day'] for m in M})
    didx = {d: i for i, d in enumerate(days)}
    m_day = np.array([didx[m['day']] for m in M])
    folds = sorted({unit_fold(unit_by_id[u]) for u in units})
    fidx = {f: i for i, f in enumerate(folds)}
    NF = len(folds)
    u_fold = np.array([fidx[unit_fold(unit_by_id[u])] for u in units])
    m_fold = u_fold[m_unit]
    m_tour = np.array([tour(m['series']) for m in M])
    tours = sorted(set(m_tour))
    tour_levels = (tours + ['all']) if len(tours) > 1 else ['all']
    univ = {t: (np.ones(N, dtype=bool) if t == 'all' else m_tour == t) for t in tour_levels}
    unit_n = {t: np.bincount(m_unit[univ[t]], minlength=U).astype(float) for t in tour_levels}
    univ_days = {t: np.bincount(m_day[univ[t]], minlength=len(days)) > 0 for t in tour_levels}
    fold_univ_n = {t: np.bincount(m_fold[univ[t]], minlength=NF).astype(float) for t in tour_levels}

    # ---- hours: pool wall-clock hours (embargo left out, clipped to the data span) and live-match hours (A7)
    cov_series = defaultdict(lambda: {'first': None, 'last': None, 'span': set(), 'missing': set(), 'withTrades': 0})
    for mt in metas:
        cv = mt.get('coverage') or {}
        span = cv.get('span') or [mt.get('from'), mt.get('to')]
        for s, c in (cv.get('series') or {}).items():
            cs = cov_series[s]
            if c.get('first') and (cs['first'] is None or c['first'] < cs['first']):
                cs['first'] = c['first']
            if c.get('last') and (cs['last'] is None or c['last'] > cs['last']):
                cs['last'] = c['last']
            if span[0] and span[1]:
                for t_ in range(day_ms(span[0]), day_ms(span[1]), DAY_MS):
                    cs['span'].add(day_of(t_))
            cs['missing'].update(c.get('missing') or [])
            cs['withTrades'] += c.get('withTrades') or 0
    firsts = [c['first'] for c in cov_series.values() if c['first']]
    lasts = [c['last'] for c in cov_series.values() if c['last']]
    t_first, t_last = M[0]['start'], max(m['close'] for m in M)
    if firsts and lasts:
        span_lo, span_hi, span_src = day_ms(min(firsts)), day_ms(max(lasts)) + DAY_MS, 'the history\'s first to last day file'
    else:
        span_lo, span_hi, span_src = t_first, t_last, 'the first match start to the last close (no history coverage in the metas)'
    swept_units = [u for mt in metas for u in (mt.get('units') or [])]
    if plan is not None and plan.get('poolSpans'):
        spans, spans_src = plan['poolSpans'], 'the plan'
    elif all(mt.get('poolSpans') is not None for mt in metas):
        by_u = {}
        for mt in metas:
            for s in mt['poolSpans']:
                by_u[s['unit']] = s
        spans, spans_src = list(by_u.values()), 'the shard metas'
    else:
        spans, spans_src = pool_spans_from_table(table, pools, set(swept_units)), 'the unit table'
    spans = [s for s in spans if s['unit'] in unit_by_id and unit_pool(unit_by_id[s['unit']]) in pools]
    pool_hours = clipped_hours(spans, span_lo, span_hi)
    unclipped_hours = clipped_hours(spans, -1, 1 << 62)
    live_dur = np.array([max(0, m['close'] - m['start']) / HOUR_MS for m in M])
    published = np.array([m.get('startPublished', True) is not False for m in M])
    m_series = np.array([m['series'] for m in M])
    for s in set(m_series):
        sel = (m_series == s) & ~published
        ref = live_dur[(m_series == s) & published]
        if sel.any():
            live_dur[sel] = float(np.median(ref)) if len(ref) else 0.0
    live_hours = {t: float(live_dur[univ[t]].sum()) for t in tour_levels}
    no_start_pool = int((~published).sum())

    def per_hour(net, hours):
        return net / hours if hours else None

    W = stationary_weights(U, B, a.block, rng)

    # ---- family A cells
    cells = []          # summary rows
    unit_sums = []      # per cell, U
    day_sums = []       # per cell, days
    vec_store = {}      # cell index -> per-match vector (F1 cells with enough entries, for ONC / SPA)
    hourly = []
    config_br = defaultdict(lambda: defaultdict(int))
    warn = 0
    for rid in sorted(runs):
        r = runs[rid]
        last = rid.rsplit('|', 1)
        if r['stick']:
            arm = 'stick'
        elif r.get('placebo') == 'coin':
            arm = 'coin'
        else:
            arm = r['fill'] or 'F1'
        config = last[0] if len(last) == 2 and last[1] in ARMS else rid
        if r['stick']:
            config = rid
        ep = r['ep']
        km = remap[ep['m']] >= 0 if len(ep['m']) else np.zeros(0, dtype=bool)
        e_m = remap[ep['m'][km]]
        e_pnl, e_ph, e_br = ep['pnl'][km], ep['ph'][km], ep['br'][km]
        e_bk = buckets_of(ep['px'][km])
        e_hour = eastern_hours(ep['t'][km] + 1000.0 * ep['hold'][km])
        e_tour = m_tour[e_m] if len(e_m) else np.zeros(0, dtype='<U3')
        config_br[config][arm] += int((e_br > 0).sum())
        ep_tot = np.bincount(e_m, weights=e_pnl, minlength=N) if len(e_m) else np.zeros(N)
        dev = np.abs(ep_tot - r['pnl'][keep]).max(initial=0) if len(r['pnl']) == len(matches) else 0.0
        if dev > 0.05 and warn < 20:
            print(f'warning: {rid}: episodes differ from match P&L by up to {dev:.3f}')
            warn += 1
        for t in tour_levels:
            st = np.ones(len(e_m), dtype=bool) if t == 'all' else (e_tour == t)
            universe = univ[t]
            n_u = int(universe.sum())
            for ph in PHASES + ['all']:
                sp = st if ph == 'all' else st & (e_ph == ph)
                for bk in BUCKETS + ['all']:
                    mask = sp if bk == 'all' else sp & (e_bk == bk)
                    n_e = int(mask.sum())
                    if n_e == 0 and not (t == 'all' and ph == 'all' and bk == 'all'):
                        continue
                    v = np.bincount(e_m[mask], weights=e_pnl[mask], minlength=N) if n_e else np.zeros(N)
                    vu = v[universe]
                    mean = vu.mean() if n_u else 0.0
                    sd = vu.std(ddof=1) if n_u > 1 else 0.0
                    z = (vu - mean) / sd if sd > 0 else np.zeros(n_u)
                    skew = float((z ** 3).mean()) if sd > 0 else 0.0
                    kurt = float((z ** 4).mean()) if sd > 0 else 3.0
                    em = e_m[mask]
                    e_days = len(set(m_day[em].tolist())) if n_e else 0
                    fo_n = np.bincount(m_fold[em], minlength=NF) if n_e else np.zeros(NF)
                    fo_s = np.bincount(m_fold[em], weights=e_pnl[mask], minlength=NF) if n_e else np.zeros(NF)
                    big = fo_n >= 10
                    fold_share = float((fo_s[big] > 0).mean()) if big.any() else None
                    ds = np.bincount(m_day, weights=v, minlength=len(days))
                    cid = f'{rid}|{t}|{ph}|{bk}'
                    net = float(v.sum())
                    row = dict(cell=cid, config=config, arm=arm, run=rid, tour=t, phase=ph, bucket=bk, entries=n_e, days=e_days,
                               traded=int((vu != 0).sum()), universe=n_u, net=net, mean=float(mean), sd=float(sd), skew=skew,
                               kurt=kurt, breaches=int((e_br[mask] > 0).sum()), fold_share=fold_share, folds_big=int(big.sum()),
                               fold_means=(np.bincount(m_fold[universe], weights=vu, minlength=NF) / np.maximum(1, fold_univ_n[t])).tolist(),
                               t_day=day_t(ds[univ_days[t]]), usd_per_hour=per_hour(net, pool_hours), usd_per_live_hour=per_hour(net, live_hours[t]),
                               overrides=r['overrides'], fill=r['fill'], placebo=r.get('placebo'))
                    cells.append(row)
                    unit_sums.append(np.bincount(m_unit, weights=v, minlength=U))
                    day_sums.append(ds)
                    hourly.append(np.bincount(e_hour[mask], weights=e_pnl[mask], minlength=24) if n_e else np.zeros(24))
                    if arm == 'F1' and n_e >= a.onc_min:
                        vec_store[len(cells) - 1] = v.astype(np.float32)
    US = np.array(unit_sums)
    DS = np.array(day_sums)
    UN = np.array([unit_n[c['tour']] for c in cells])
    nC = len(cells)
    for c in cells:
        c['config_breaches'] = int(sum(config_br[c['config']].values()))
    print(f'family A: {nC} cells scored over {N} matches ({no_tape} no-tape matches left out), {U} units, {len(days)} days, {NF} folds')

    # ---- bootstrap means and p-values
    means = np.array([c['mean'] for c in cells])
    p_boot, omega, lo, hi = boot_ratio(W, US, UN, means)
    for i, c in enumerate(cells):
        c.update(p=float(p_boot[i]), ci90=[float(lo[i]), float(hi[i])], t_boot=float(means[i] / omega[i]) if omega[i] > 0 else 0.0)

    by_id = {(c['config'], c['arm'], c['tour'], c['phase'], c['bucket']): i for i, c in enumerate(cells)}
    f1 = [i for i, c in enumerate(cells) if c['arm'] == 'F1']
    sticks = [i for i, c in enumerate(cells) if c['arm'] == 'stick']
    rej = bh([cells[i]['p'] for i in f1], a.alpha)
    coin_configs = {c['config'] for c in cells if c['arm'] == 'coin'}
    f2_configs = {c['config'] for c in cells if c['arm'] == 'F2'}
    pairs = []
    for j, i in enumerate(f1):
        c = cells[i]
        k2 = (c['config'], 'F2', c['tour'], c['phase'], c['bucket'])
        kc = (c['config'], 'coin', c['tour'], c['phase'], c['bucket'])
        c['bh'] = bool(rej[j])
        # The F2 arm's net in the same cell (0 when the F2 run made no entry there; None when the config has no F2 run).
        c['f2_net'] = cells[by_id[k2]]['net'] if k2 in by_id else (0.0 if c['config'] in f2_configs else None)
        pc = by_id.get(kc)
        if pc is not None or c['config'] in coin_configs:
            # The coin arm's cell of the same config, tour, phase and bucket; when it made no entry there (no row), its
            # per-match P&L is 0 and the comparison is against zero.
            pairs.append((i, pc))
            c['placebo_partner'] = cells[pc]['cell'] if pc is not None else None
            c['placebo_empty'] = pc is None
            pnet = cells[pc]['net'] if pc is not None else 0.0
            c['placebo_diff'] = (c['net'] - pnet) / max(1, c['universe'])
            dd = DS[i] - DS[pc] if pc is not None else DS[i]
            c['t_day_placebo'] = day_t(dd[univ_days[c['tour']]])
    if pairs:
        pi = np.array([x for x, _ in pairs])
        d_us = np.array([US[x] - (US[y] if y is not None else 0.0) for x, y in pairs])
        d_means = np.array([cells[i]['placebo_diff'] for i in pi])
        p_pl, _, _, _ = boot_ratio(W, d_us, UN[pi], d_means)
        for k, i in enumerate(pi):
            cells[i]['p_placebo'] = float(p_pl[k])
    gates_a = Counter()
    for i in f1:
        c = cells[i]
        g = {'BH': c['bh'], 'entries>=100': c['entries'] >= 100, 'days>=30': c['days'] >= 30, 'mean>0': c['mean'] > 0,
             'folds>=60%': c['fold_share'] is not None and c['fold_share'] >= 0.6, 'F2 net>0': (c['f2_net'] or 0) > 0,
             'config breaches=0': c['config_breaches'] == 0}
        c['flag'] = bool(all(g.values()))
        c['gates_failed'] = [k for k, v in g.items() if not v]
        for k, v in g.items():
            gates_a[k] += int(v)
        gates_a['all'] += int(c['flag'])

    # ---- ONC over F1 cells with enough entries (identical per-match vectors are one trial)
    onc_ids = sorted(vec_store, key=lambda i: (-cells[i]['entries'], i))
    dropped = 0
    if len(onc_ids) > a.onc_cap:
        dropped = len(onc_ids) - a.onc_cap
        onc_ids = onc_ids[:a.onc_cap]
    n_eff, medoids, best_in, cluster_srs, n_distinct, onc_labels = 0, [], [], [], 0, {}
    onc_diag, onc_warn = {}, []
    if onc_ids:
        groups = {}
        for i in onc_ids:
            groups.setdefault(np.round(vec_store[i], 6).tobytes(), []).append(i)
        reps = [g[0] for g in groups.values()]
        n_distinct = len(reps)
        Xraw = np.array([vec_store[i] for i in reps], dtype=np.float64)
        if len(reps) >= 3:
            Xc = Xraw - Xraw.mean(axis=1, keepdims=True)
            nrm = np.linalg.norm(Xc, axis=1)
            nrm[nrm == 0] = 1
            corr = np.clip((Xc / nrm[:, None]) @ (Xc / nrm[:, None]).T, -1, 1)
            labels = onc(corr, a.seed, a.onc_max_k, a.onc_init, a.onc_dim, onc_diag)
            dist = np.sqrt(np.clip((1 - corr) / 2, 0, 1))
        else:
            labels = np.arange(len(reps))
            dist = np.zeros((len(reps), len(reps)))
        n_eff = int(labels.max() + 1)
        for k in range(n_eff):
            idx = np.nonzero(labels == k)[0]
            members = [i for r_ in idx for i in groups[np.round(vec_store[reps[r_]], 6).tobytes()]]
            for i in members:
                onc_labels[i] = k
            medoids.append(reps[idx[np.argmin(dist[np.ix_(idx, idx)].sum(axis=1))]])
            best_in.append(max(members, key=lambda i: (cells[i]['mean'], -i)))
            # The cluster-mean series' per-match Sharpe over its members' universe (the matches of their tours), the scale
            # each cell's own SR is taken on: over all N a one-tour cluster's Sharpe would shrink by about sqrt(its share).
            s_univ = np.zeros(N, dtype=bool)
            for i in members:
                s_univ |= univ[cells[i]['tour']]
            s = Xraw[idx].mean(axis=0)[s_univ]
            sd = s.std(ddof=1) if len(s) > 1 else 0.0
            if sd > 0:
                cluster_srs.append(float(s.mean() / sd))
        if onc_diag.get('cap_binding') or onc_diag.get('q_rising_at_cap'):
            onc_warn.append(f"the k scan's quality is {'best' if onc_diag.get('cap_binding') else 'still rising'} at its cap k = {onc_diag['k_hi']} "
                            f"(--onc-max-k) of {onc_diag['n']} cells: the true cluster count may be higher, so N_eff = {n_eff} may be "
                            f"too low and the DSR / SPA anti-conservative (default --onc-max-k 0 scans to n - 1)")
        if onc_diag.get('best_k') == 2 and onc_diag.get('n', 0) >= 20:
            onc_warn.append(f"the k scan picked k = 2 for {onc_diag['n']} cells (quality {onc_diag['best_q']:.2f}): the silhouette quality is "
                            f"degenerate at small k, so check the q curve in summary.json (onc.q_curve) before reading N_eff")
        for w_ in onc_warn:
            print(f'WARNING (ONC): {w_}', file=sys.stderr)
    n_eff = max(n_eff, 1)

    # ---- production: the F1 'all' cell of the config whose overrides equal production's spec by value (check_runs keeps
    # it unique: two non-placebo runs with the same overrides and fill are refused)
    allc = [i for i in f1 if cells[i]['tour'] == 'all' and cells[i]['phase'] == 'all' and cells[i]['bucket'] == 'all']
    prod = [i for i in allc if is_production(cells[i]['overrides'], stratum)]
    prod_cfg = cells[prod[0]]['config'] if len(prod) == 1 else None

    # ---- SPA (consistent) and StepM over medoids + cluster bests + production + flagged cells
    spa_set = sorted(set(medoids) | set(best_in) | set(prod) | {i for i in f1 if cells[i]['flag']})
    spa = {}
    if spa_set:
        num = W @ US[spa_set].T
        den = W @ UN[spa_set].T
        with np.errstate(divide='ignore', invalid='ignore'):
            bm = np.where(den > 0, num / np.where(den > 0, den, 1), 0.0)
        mh = means[spa_set]
        om = np.where(omega[spa_set] > 0, omega[spa_set], np.inf)
        tk = mh / om
        T = max(0.0, float(tk.max()))
        thr = -math.sqrt(2 * math.log(max(math.log(N), 1.0001)))
        mu_c = np.where(tk <= thr, np.minimum(mh, 0), 0.0)
        Z = (bm - mh[None, :] + mu_c[None, :]) / om[None, :]
        Tb = np.maximum(0, Z.max(axis=1))
        spa = {'T': T, 'p_consistent': float(boot_p((Tb >= T).sum(), B)), 'models': len(spa_set), 'best': cells[spa_set[int(np.argmax(tk))]]['cell']}
        active, rejected = list(range(len(spa_set))), []
        cen = (bm - mh[None, :]) / om[None, :]
        while active:
            c_alpha = float(np.quantile(cen[:, active].max(axis=1), 1 - a.alpha))
            new = [k for k in active if tk[k] > c_alpha]
            if not new:
                break
            rejected += new
            active = [k for k in active if k not in new]
        spa['stepm_rejected'] = [cells[spa_set[k]]['cell'] for k in rejected]
        spa['stepm_alpha'] = a.alpha

    # ---- DSR at N_eff; SR0's variance across the N_eff cluster-mean series
    v_sr = float(np.var(cluster_srs, ddof=1)) if len(cluster_srs) > 1 else 0.0

    def sr0_of(v, n_trials):
        if v <= 0:
            return 0.0
        n_t = max(n_trials, 2)
        return math.sqrt(v) * ((1 - EULER) * norm_ppf(1 - 1 / n_t) + EULER * norm_ppf(1 - 1 / (n_t * math.e)))
    sr0 = sr0_of(v_sr, n_eff)

    def dsr(sr, skew, kurt, T_, sr_0):
        den_ = 1 - skew * sr + (kurt - 1) / 4 * sr * sr
        return norm_cdf((sr - sr_0) * math.sqrt(max(T_ - 1, 1)) / math.sqrt(den_)) if den_ > 0 else None
    for i in set(spa_set) | set(prod):
        c = cells[i]
        c['sr'] = c['mean'] / c['sd'] if c['sd'] > 0 else 0.0
        c['dsr'] = dsr(c['sr'], c['skew'], c['kurt'], c['universe'], sr0)

    # ---- PBO (CSCV) over the folds for the stage's configs ('all' cells, F1)
    pbo = None
    if len(allc) >= 2 and NF >= 4:
        P = np.array([cells[i]['fold_means'] for i in allc]).T  # folds x configs
        S = NF - (NF % 2)
        dropped_fold = folds[-1] if NF % 2 else None
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
        pbo = {'pbo': float(np.mean(np.array(logits) <= 1e-12)), 'combos': len(combos), 'folds': S, 'dropped_fold': dropped_fold}

    # ---- knob sensitivity (section 5 rule, by value against an explicit baseline) and the six-knob A2 rule; stage 1's
    # threshold factorial main effects as a descriptive table
    cfg_rows = {cells[i]['config']: (cells[i]['overrides'], cells[i]['mean']) for i in allc}
    if a.baseline:
        base_cfg, base_src = a.baseline, '--baseline'
    elif meta.get('baseline'):
        base_cfg, base_src = str(meta['baseline']), 'the shard meta'
    else:
        base_cfg, base_src = prod_cfg, 'the production config'
    sens = knob_sensitivity(cfg_rows, base_cfg, stage, pools, stratum)
    sens['baseline_source'] = base_src
    if base_cfg is None:
        sens['a2_reason'] = 'no baseline: no production config in this run and none named (--baseline): nothing is ranked'
    sens_main = factorial_main_effects(cfg_rows, PROD_SPEC.get(stratum, {}))

    # ---- loser tables: production and the five best F1 configs by mean ('all' cells)
    top_cfg = [cells[i]['run'] for i in sorted(allc, key=lambda i: -cells[i]['mean'])[:5]]
    prod_runs = [cells[i]['run'] for i in prod]
    loser_rows = []
    for rid in dict.fromkeys(prod_runs + top_cfg):
        ep = runs[rid]['ep']
        g = defaultdict(lambda: [0, 0.0, 0])
        for q in range(len(ep['m'])):
            mi = remap[ep['m'][q]]
            if mi < 0:
                continue
            key = (m_tour[mi], ep['ph'][q], ep['leg'][q], int(ep['sig'][q]), bucket_of(ep['px'][q]), ep['x'][q])
            s = g[key]
            s[0] += 1
            s[1] += float(ep['pnl'][q])
            s[2] += 1 if ep['pnl'][q] > 0 else 0
        for key, (n, net, wins) in sorted(g.items(), key=lambda kv: kv[1][1]):
            loser_rows.append(dict(run=rid, tour=str(key[0]), phase=str(key[1]), leg=str(key[2]), signals=key[3], bucket=key[4], exit=str(key[5]),
                                   n=n, net=round(net, 4), mean=round(net / n, 4), win=round(wins / n, 3)))

    # ---- family B
    fb_rows, fb_sum = score_family_b(fam_b, uidx, unit_by_id, fidx, W, a.alpha, pool_hours, live_hours['all']) if fam_b else ([], None)

    # ---- registry rows (every scored cell = N_raw, per family)
    from_d, to_d = min(m['day'] for m in M), max(m['day'] for m in M)
    days_eastern = [fmt_eastern(M[0]['start'], '%Y-%m-%d %H:%M'), fmt_eastern(t_last, '%Y-%m-%d %H:%M')]
    n_raw_a, n_raw_b = nC, len(fb_rows)
    gate = 'stage1-screen' if stage == '1' else f'stage{stage}'
    common = dict(thread='tennis-ta', run=run_id, sha=meta.get('sha'), sim_version=sim_version, data_version=data_version,
                  evidence=meta.get('evidence'), stage=stage, pool=','.join(pools), days_utc=[from_d, to_d], days_eastern=days_eastern,
                  doge_excluded=True)
    reg = []
    for i, c in enumerate(cells):
        ch = hashlib.sha1(json.dumps({'overrides': c['overrides'], 'fill': c['fill'], 'placebo': c['placebo'], 'stick': c['arm'] == 'stick'},
                                     sort_keys=True).encode()).hexdigest()[:16]
        verdict = ('flag' if c.get('flag') else 'no') if c['arm'] == 'F1' else 'stick' if c['arm'] == 'stick' else 'arm'
        reg.append(dict(common, family='A', cell=c['cell'], config=c['config'], arm=c['arm'], config_hash=ch, overrides=c['overrides'],
                        seeds={'coin': 'hash32(spec id)', 'bootstrap': a.seed}, entries=c['entries'], matches=c['universe'],
                        net=round(c['net'], 4), mean_per_match=round(c['mean'], 6), usd_per_hour=c['usd_per_hour'],
                        usd_per_live_hour=c['usd_per_live_hour'], hourly_eastern=[round(x, 4) for x in hourly[i]],
                        placebo_partner=c.get('placebo_partner'), gate='measuring stick (not screened)' if c['arm'] == 'stick' else gate,
                        verdict=verdict, p_boot=c['p'], bh=c.get('bh'), t_day=c['t_day'], t_day_placebo=c.get('t_day_placebo'),
                        p_placebo=c.get('p_placebo'), breaches=c['breaches'], config_breaches=c['config_breaches'],
                        fold_share=c['fold_share'], onc_cluster=onc_labels.get(i), n_raw=n_raw_a, n_eff=n_eff))
    for r_ in fb_rows:
        reg.append(dict(common, family='B', cell=r_['reg_id'], config=r_['rule'], arm='B', config_hash=hashlib.sha1(r_['id'].encode()).hexdigest()[:16],
                        overrides={'familyB': r_['id']}, seeds={'familyB': 20261105, 'bootstrap': a.seed}, entries=r_['n'], matches=None,
                        net=round(r_['net'], 4), mean_per_entry=round(r_['mean'], 6), usd_per_hour=r_['usd_per_hour'],
                        usd_per_live_hour=r_['usd_per_live_hour'], hourly_eastern=None, placebo_partner=None, placebo_kind='in-cell circular shift',
                        gate=f'{gate}-B', verdict='flag' if r_['flag'] else 'no', p_boot=r_['p'], bh=r_['bh'], t_unit=r_['t_unit'],
                        t_day=r_['t_day'], z_placebo=r_['z_placebo'], breaches=r_['breaches'], config_breaches=r_['rule_breaches'],
                        fold_share=r_['fold_share'], n_raw=n_raw_b, n_eff=None, design_size=fb_sum['design_size']))
    ids = Counter(r['cell'] for r in reg)
    dup_ids = [k for k, v in ids.items() if v > 1]
    if dup_ids:
        sys.exit(f'{len(dup_ids)} registry id(s) repeat (e.g. {dup_ids[0]}): no registry rows are written')

    # ---- outputs (only now: everything above was checked)
    os.makedirs(a.out, exist_ok=True)
    with gzip.open(os.path.join(a.out, f'registry-tennis-ta-{run_id}.jsonl.gz'), 'wt') as fh:
        for r in reg:
            fh.write(dumps(r) + '\n')
    slim = [{k: v for k, v in c.items() if k != 'fold_means'} for c in cells]
    with gzip.open(os.path.join(a.out, 'cells.json.gz'), 'wt') as fh:
        fh.write(dumps(slim))
    if fb_rows:
        with gzip.open(os.path.join(a.out, 'cells-b.json.gz'), 'wt') as fh:
            fh.write(dumps(fb_rows))
    with open(os.path.join(a.out, 'losers.json'), 'w') as fh:
        fh.write(dumps(loser_rows))
    coverage = {s: {'first': c['first'], 'last': c['last'], 'spanDays': len(c['span']), 'missing': sorted(c['missing']),
                    'withFile': len(c['span'] - c['missing'])} for s, c in sorted(cov_series.items())}
    owned = len(matches)
    owned_no_start = sum(1 for m in matches if m.get('startPublished') is False)
    sub_counts = {}
    for mt in metas:
        sub_counts[mt['k']] = mt['subShards']
    slicing = {'shards': meta.get('shards'), 'subShards': [sub_counts[k] for k in sorted(sub_counts)], 'files': len(metas),
               'units': len(swept_units), 'slice_starts': [mt['units'][0] for mt in metas if mt.get('units')], 'statement': STATE_RESTART}
    bh_floor = {'p_min': 1 / (B + 1), 'A_m': len(f1), 'A_cells_at_floor_needed': math.ceil(len(f1) / (a.alpha * (B + 1))) if f1 else None}
    if fb_sum:
        bh_floor.update(B_m=fb_sum['design_size'], B_cells_at_floor_needed=math.ceil(fb_sum['design_size'] / (a.alpha * (B + 1))) if fb_sum['design_size'] else None)
    production = [{k: cells[i].get(k) for k in ('cell', 'entries', 'net', 'mean', 'ci90', 'p', 'f2_net', 'placebo_diff', 'p_placebo', 't_day',
                                                't_day_placebo', 'breaches', 'config_breaches', 'dsr', 'usd_per_hour', 'usd_per_live_hour')} for i in prod]
    prod_all = cells[prod[0]] if len(prod) == 1 else None
    stick_rows = []
    for i in sticks:
        c = cells[i]
        if c['tour'] == 'all' and c['phase'] == 'all' and c['bucket'] == 'all':
            row = {k: c.get(k) for k in ('cell', 'entries', 'net', 'mean', 'ci90', 'p', 'breaches', 'usd_per_hour', 'usd_per_live_hour', 't_day')}
            row['vs_production'] = (c['net'] - prod_all['net']) / max(1, N) if prod_all else None
            stick_rows.append(row)
    summary = dict(run=run_id, pools=pools, stage=stage, sim_version=sim_version, data_version=data_version, files=data['files'],
                   slicing=slicing, coverage=coverage, owned_matches=owned, owned_no_published_start=owned_no_start,
                   matches=N, no_tape=no_tape, pool_no_published_start=no_start_pool, units=U, days=len(days), folds=folds,
                   pool_hours=pool_hours, pool_hours_unclipped=unclipped_hours, pool_hours_source=spans_src, data_span=[day_of(span_lo), day_of(span_hi - 1)],
                   data_span_source=span_src, live_hours=live_hours, n_raw={'A': n_raw_a, 'B': n_raw_b}, f1_cells=len(f1),
                   stick_cells=len(sticks), bh_rejections=int(rej.sum()), gates_A=dict(gates_a), flagged=[cells[i]['cell'] for i in f1 if cells[i]['flag']],
                   n_eff=n_eff, onc_cells=len(onc_ids), onc_distinct=n_distinct, onc_dropped=dropped, spa=spa, sr0=sr0, v_sr=v_sr,
                   v_sr_source=(f'variance of per-match Sharpe across the {len(cluster_srs)} ONC cluster-mean series, each over its '
                                f'members\' tour universe (the scale of each cell\'s own SR)'), pbo=pbo,
                   onc=dict(onc_diag, warnings=onc_warn, max_k_arg=a.onc_max_k, dim=a.onc_dim, n_init=a.onc_init),
                   sensitivity=sens, sensitivity_factorial=sens_main, production=production, production_config=prod_cfg,
                   stratum=stratum, sticks=stick_rows, bh_floor=bh_floor, family_b=fb_sum,
                   config_breaches={k: dict(v) for k, v in config_br.items() if sum(v.values())},
                   breach_configs=sorted({cells[i]['config'] for i in f1 if cells[i]['config_breaches'] > 0}))
    with open(os.path.join(a.out, 'summary.json'), 'w') as fh:
        fh.write(dumps(summary, indent=1))

    L = render(a, summary, cells, f1, prod, loser_rows, prod_runs, fb_rows, meta, M, t_last, pools)
    with open(os.path.join(a.out, 'report.md'), 'w') as fh:
        fh.write('\n'.join(L) + '\n')
    print('\n'.join(L))


def score_family_b(fam_b, uidx, unit_by_id, fidx, W, alpha, pool_hours, live_hours_all):
    """Family B cells (merged FamilyBCell, C2) scored with the same unit bootstrap; its own BH family and DSR trial count."""
    cells = [c for c in fam_b['cells'] if c['n'] > 0]
    design = int(fam_b.get('designSize') or 0)
    m_total = max(design, len(cells))
    U, NF, B = W.shape[1], len(fidx), W.shape[0]
    rows = []
    if not cells:
        return rows, {'design_size': design, 'bh_m': m_total, 'cells_with_entries': 0, 'cells_total': len(fam_b['cells']), 'gates': {}, 'flagged': [],
                      'diagnostics': fam_b.get('diagnostics'), 'stratum': fam_b.get('stratum'), 'sr0': 0.0, 'v_sr': 0.0, 'bh_rejections': 0}
    SB, NB = np.zeros((len(cells), U)), np.zeros((len(cells), U))
    u_fold = {u: fidx[unit_fold(unit_by_id[u])] for u in uidx}
    for i, c in enumerate(cells):
        for u, v in c['units'].items():
            if u in uidx:
                NB[i, uidx[u]] += v[0]
                SB[i, uidx[u]] += v[1]
    means = np.array([c['sum'] / c['n'] for c in cells])
    p, omega, lo, hi = boot_ratio(W, SB, NB, means)
    rule_br = defaultdict(int)
    for c in cells:
        rule_br[_rule_of(c)] = max(rule_br[_rule_of(c)], int(c['breaches']))
    for i, c in enumerate(cells):
        n, s = c['n'], c['sum']
        mean = s / n
        var = max(0.0, c['sumSq'] / n - mean * mean)
        sd = math.sqrt(var * n / (n - 1)) if n > 1 else 0.0
        if var > 0:
            m3 = c['sum3'] / n - 3 * mean * c['sumSq'] / n + 2 * mean ** 3
            m4 = c['sum4'] / n - 4 * mean * c['sum3'] / n + 6 * mean * mean * c['sumSq'] / n - 3 * mean ** 4
            skew, kurt = m3 / var ** 1.5, m4 / var ** 2
        else:
            skew, kurt = 0.0, 3.0
        us = [(v[0], v[1], v[2], v[3]) for v in c['units'].values()]
        d = [v[1] / v[0] - v[3] / v[2] for v in us if v[0] > 0 and v[2] > 0]
        z_pl = None
        if len(d) >= 2:
            sdd = float(np.std(d, ddof=1))
            z_pl = float(np.mean(d) / (sdd / math.sqrt(len(d)))) if sdd > 0 else None
        fo_n, fo_s = np.zeros(NF), np.zeros(NF)
        for u, v in c['units'].items():
            if u in u_fold:
                fo_n[u_fold[u]] += v[0]
                fo_s[u_fold[u]] += v[1]
        big = fo_n >= 10
        dvals = [v for v in c['days'].values() if v[0] > 0]
        rid = c['id'] if c['id'].startswith('B|') else 'B|' + c['id']
        rows.append(dict(id=c['id'], reg_id=rid, group=c['group'], rule=_rule_of(c), n=int(n), net=float(s), mean=mean, sd=sd, skew=skew, kurt=kurt,
                         p=float(p[i]), ci90=[float(lo[i]), float(hi[i])], t_boot=float(mean / omega[i]) if omega[i] > 0 else 0.0,
                         t_unit=cluster_t_ratio(SB[i], NB[i]), t_day=cluster_t_ratio([v[1] for v in dvals], [v[0] for v in dvals]),
                         days=len(dvals), units=int((NB[i] > 0).sum()), placebo_diff=float(np.mean(d)) if d else None, placebo_units=len(d),
                         z_placebo=z_pl, placebo_n=int(sum(v[2] for v in us)), stress_net=float(c['stressSum']),
                         stress_mean=float(c['stressSum'] / n), gross=float(c['gross']), fees=float(c['fees']), breaches=int(c['breaches']),
                         rule_breaches=rule_br[_rule_of(c)], fold_share=float((fo_s[big] > 0).mean()) if big.any() else None, folds_big=int(big.sum()),
                         usd_per_hour=s / pool_hours if pool_hours else None, usd_per_live_hour=s / live_hours_all if live_hours_all else None))
    rej = bh_m([r['p'] for r in rows], alpha, m_total)
    gates = Counter()
    for r, rj in zip(rows, rej):
        r['bh'] = bool(rj)
        g = {'BH': r['bh'], 'entries>=100': r['n'] >= 100, 'days>=30': r['days'] >= 30, 'mean>0': r['mean'] > 0,
             'folds>=60%': r['fold_share'] is not None and r['fold_share'] >= 0.6, 'stress net>0': r['stress_net'] > 0,
             'rule breaches=0': r['rule_breaches'] == 0}
        r['flag'] = bool(all(g.values()))
        r['gates_failed'] = [k for k, v in g.items() if not v]
        for k, v in g.items():
            gates[k] += int(v)
        gates['vs placebo z>=1.645'] += int(finite(r['z_placebo']) and r['z_placebo'] >= 1.645)
        gates['all'] += int(r['flag'])
    # DSR with family B's own trial count (N_raw of B); SR0's variance across the cells holding >= 100 entries.
    srs = [r['mean'] / r['sd'] for r in rows if r['n'] >= 100 and r['sd'] > 0]
    if len(srs) < 2:
        srs = [r['mean'] / r['sd'] for r in rows if r['n'] >= 2 and r['sd'] > 0]
    v_sr = float(np.var(srs, ddof=1)) if len(srs) > 1 else 0.0
    n_t = max(len(rows), 2)
    sr0 = math.sqrt(v_sr) * ((1 - EULER) * norm_ppf(1 - 1 / n_t) + EULER * norm_ppf(1 - 1 / (n_t * math.e))) if v_sr > 0 else 0.0
    for r in rows:
        sr = r['mean'] / r['sd'] if r['sd'] > 0 else 0.0
        den = 1 - r['skew'] * sr + (r['kurt'] - 1) / 4 * sr * sr
        r['sr'] = sr
        r['dsr'] = norm_cdf((sr - sr0) * math.sqrt(max(r['n'] - 1, 1)) / math.sqrt(den)) if den > 0 and r['n'] > 1 else None
    summ = {'design_size': design, 'bh_m': m_total, 'cells_with_entries': len(rows), 'cells_total': len(fam_b['cells']), 'gates': dict(gates),
            'bh_rejections': int(rej.sum()), 'flagged': [r['reg_id'] for r in rows if r['flag']], 'diagnostics': fam_b.get('diagnostics'),
            'stratum': fam_b.get('stratum'), 'sr0': sr0, 'v_sr': v_sr, 'v_sr_cells': len(srs), 'entries': int(sum(r['n'] for r in rows))}
    return rows, summ


def _level_key(v):
    try:
        return (0, float(v), '')
    except (TypeError, ValueError):
        return (1, 0.0, str(v))


def _rule_of(c):
    """A family B trading rule: the reading's group plus the exit (the context is only a cut of its entries)."""
    g, cid = c.get('group') or '', c['id']
    if g and cid.startswith(g + '|'):
        rest = cid[len(g) + 1:]
        return g + '|' + rest.rsplit('|', 1)[-1]
    parts = cid.split('|')
    return '|'.join(parts[:-2] + parts[-1:]) if len(parts) > 2 else cid


def render(a, s, cells, f1, prod, loser_rows, prod_runs, fb_rows, meta, M, t_last, pools):
    L = []
    pool_txt = ','.join(pools)
    L.append(f"## Tennis TA sweep, stage {s['stage']}, pool {pool_txt} (run {s['run']})")
    L.append(f"Evidence: {meta.get('evidence', '-')}. sha {str(meta.get('sha') or '-')[:10]}, {s['sim_version']}, data version {s['data_version']}. "
             f"Days {M[0]['day']} to {M[-1]['day']} UTC "
             f"({fmt_eastern(M[0]['start'], '%b %d %I:%M %p')} to {fmt_eastern(t_last, '%b %d %I:%M %p')}).")
    L.append('')
    L.append('### Run mechanics')
    sl = s['slicing']
    L.append(f"- Slicing: {sl['shards']} shard(s) x sub-slices {sl['subShards']} = {sl['files']} file(s) over {sl['units']} unit(s), cut at unit edges "
             f"only (Monday 05:00 UTC weeks; a Slam fortnight is one unit), so {sl['statement']}. Every (k, j) was present exactly once with one "
             f"run, stage, pool, sim version and data version before anything was scored.")
    cov = '; '.join(f"{k}: history {c['first'] or '-'} to {c['last'] or '-'}, {c['withFile']} of {c['spanDays']} swept days with a file"
                    + (f" (missing {', '.join(c['missing'][:8])}{', ...' if len(c['missing']) > 8 else ''})" if c['missing'] else '')
                    for k, c in s['coverage'].items()) or 'no per-series coverage in the shard metas'
    L.append(f"- Coverage: {cov}. {s['owned_matches']} owned matches, {s['owned_no_published_start']} without a published start (unit and pool "
             f"from the earliest market-line time); in the pool {s['matches']} with a tape ({s['no_tape']} without one left out), "
             f"{s['pool_no_published_start']} of them without a published start.")
    fb = s['family_b']
    L.append(f"- N_raw: family A {s['n_raw']['A']} cells ({s['f1_cells']} F1 cells screened, {s['stick_cells']} measuring-stick cells logged, never "
             f"screened)" + (f"; family B {s['n_raw']['B']} cells with entries (design {fb['design_size']}, its own BH family)" if fb else '; family B not run') + '.')
    L.append(f"- Hours: pool {s['pool_hours']:,.0f} h (from {s['pool_hours_source']}: pool units minus the 24 h embargo windows of sealed units, "
             f"clipped to the data span {s['data_span'][0]} to {s['data_span'][1]}, {s['data_span_source']}; {s['pool_hours_unclipped']:,.0f} h unclipped); "
             f"live-match {s['live_hours']['all']:,.0f} h (close minus the published start; a match without one gets its series' median).")
    pb = s['pbo']
    L.append(f"- Folds: {len(s['folds'])} monthly folds by the month of each unit's last day (a unit is never split)"
             + (f"; CSCV drops fold {pb['dropped_fold']} to make the count even" if pb and pb.get('dropped_fold') else '') + '.')
    bf = s['bh_floor']
    L.append(f"- Bootstrap: stationary over {s['units']} units (mean block {a.block:g} unit), B = {a.boot}, seed {a.seed}; p = (c + 1) / (B + 1), so the "
             f"smallest p is {bf['p_min']:.1e} and BH at q = {a.alpha} rejects nothing unless at least {bf['A_cells_at_floor_needed']} of the "
             f"{bf['A_m']} F1 cells sit at that floor" + (f" ({bf['B_cells_at_floor_needed']} of family B's {bf['B_m']})" if fb else '') + '.')
    L.append('')
    L.append('### Family A (the production rulebook)')
    L.append(f"Production (by value: every override at production's default{', the ratchet off on H' if s['stratum'] == 'H' else ''}; momentum 1c, "
             f"flow 0.2, opponent 1c, window 60 s; end loser cut on, tennis-only pacer): config {s['production_config'] or '-'}")
    for p in s['production']:
        L.append(f"- {p['entries']} entries, net {usd(p['net'])}, {usd(p['mean'])} a match (90% CI {usd(p['ci90'][0])} to {usd(p['ci90'][1])}), "
                 f"p = {f4(p['p'], '.4f')}; F2 {usd(p['f2_net'])}; vs placebo {usd(p.get('placebo_diff'))} a match (p = {f4(p.get('p_placebo'), '.4f')}); "
                 f"day t {f4(p['t_day'], '.2f')} (vs placebo {f4(p.get('t_day_placebo'), '.2f')}); {usd(p['usd_per_hour'])}/h over 24 h, "
                 f"{usd(p['usd_per_live_hour'])} per live-match hour; breaches {p['breaches']} (config {p['config_breaches']})")
    if not s['production']:
        L.append('- not in this stage\'s grid')
    if s['sticks']:
        L.append('')
        L.append('Measuring sticks (reported only: never screened, never in BH, SPA, StepM, DSR or N_eff):')
        L.append('| stick | entries | net | $/match | 90% CI | p | vs production $/match | $/h | $/live h | breaches |')
        L.append('|---|---|---|---|---|---|---|---|---|---|')
        for p in s['sticks']:
            L.append(f"| {md(p['cell'].rsplit('|', 3)[0])} | {p['entries']} | {usd(p['net'])} | {f4(p['mean'])} | {f4(p['ci90'][0], '.3f')}..{f4(p['ci90'][1], '.3f')} | "
                     f"{f4(p['p'])} | {f4(p['vs_production'])} | {usd(p['usd_per_hour'])} | {usd(p['usd_per_live_hour'])} | {p['breaches']} |")
    L.append('')
    g = s['gates_A']
    L.append(f"Screen: BH q = {a.alpha} rejects {s['bh_rejections']} of {s['f1_cells']} F1 cells; gates passed: "
             + ', '.join(f'{k} {g.get(k, 0)}' for k in ('BH', 'entries>=100', 'days>=30', 'mean>0', 'folds>=60%', 'F2 net>0', 'config breaches=0'))
             + f"; {g.get('all', 0)} pass every discovery condition.")
    if s['breach_configs']:
        L.append(f"{len(s['breach_configs'])} config(s) had a settlement breach in some cell of some arm, so none of their cells can pass: "
                 + ', '.join(s['breach_configs'][:8]) + (', ...' if len(s['breach_configs']) > 8 else '') + '.')
    if s['spa']:
        sp = s['spa']
        L.append(f"SPA (consistent) over {sp['models']} models: T = {sp['T']:.2f}, p = {sp['p_consistent']:.4f}, best {sp['best']}. "
                 f"StepM (alpha {sp['stepm_alpha']}) rejects {len(sp['stepm_rejected'])}.")
    od = s['onc']
    L.append(f"N_eff = {s['n_eff']} (ONC over {s['onc_cells']} F1 cells with >= {a.onc_min} entries, {s['onc_distinct']} distinct per-match vectors"
             + (f", {s['onc_dropped']} beyond the cap left out" if s['onc_dropped'] else '')
             + (f"; base scan k = 2..{od['k_hi']} ({od['scanned']} k tried, k-means on {od['kmeans_dims']} components keeping "
                f"{od['kmeans_variance_kept']:.1%} of the variance, silhouettes exact): best k {od['best_k']} (quality {od['best_q']:.2f})"
                f"{', refinement kept' if od.get('refined') else ', refinement not kept'}" if od.get('best_k') else '') + ').')
    for w_ in od.get('warnings') or []:
        L.append(f"**Warning (ONC):** {w_}.")
    if pb:
        L.append(f"PBO (CSCV, {pb['folds']} folds, {pb['combos']} splits): {pb['pbo']:.2f}.")
    L.append(f"DSR reference SR0 = {s['sr0']:.4f} per match ({s['v_sr_source']}: {s['v_sr']:.6f}), N = N_eff.")
    L.append('')
    top = sorted(f1, key=lambda i: (not cells[i]['flag'], cells[i]['p'], -cells[i]['mean']))[:25]
    L.append('| cell | entries | days | net | $/match | 90% CI | p | BH | F2 net | vs placebo | day t | day t vs placebo | folds+ | $/h | $/live h | DSR |')
    L.append('|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|')
    for i in top:
        c = cells[i]
        L.append(f"| {md(c['cell'].replace('A|s1|', ''))} | {c['entries']} | {c['days']} | {usd(c['net'])} | {c['mean']:.4f} | {c['ci90'][0]:.3f}..{c['ci90'][1]:.3f} | "
                 f"{c['p']:.4f} | {'yes' if c['bh'] else 'no'} | {usd(c['f2_net'])} | {f4(c.get('placebo_diff'))} (p {f4(c.get('p_placebo'), '.4f')}) | "
                 f"{f4(c['t_day'], '.2f')} | {f4(c.get('t_day_placebo'), '.2f')} | {'-' if c['fold_share'] is None else format(c['fold_share'], '.0%')} | "
                 f"{usd(c['usd_per_hour'])} | {usd(c['usd_per_live_hour'])} | {f4(c.get('dsr'), '.2f')} |")
    L.append('')
    sv = s['sensitivity']
    L.append(f"Knob sensitivity (section 5 rule: {sv['rule']}; baseline {sv['baseline'] or '-'}, from {sv.get('baseline_source')}; a config "
             f"enters a knob's levels when it differs from the baseline, by value, in that knob alone):")
    for k in sv['ranking'] + [k for k in sv['knobs'] if k not in sv['ranking']]:
        v = sv['knobs'][k]
        L.append(f"- {k}{' (R only: a lead, never ranked)' if v['r_only'] else ''}: "
                 + ', '.join(f"{lv}{'*' if lv == v['baseline_level'] else ''}: {x:.4f}" for lv, x in v['levels'].items()) + f" (range {v['range']:.4f})")
    if not sv['knobs']:
        L.append('- no knob is moved alone from the baseline in this run')
    extra = ([f"{sv['multi_knob']} config(s) move two or more knobs (pairwise / factorial)"] if sv['multi_knob'] else []) \
        + ([f"{len(sv['not_knobs'])} config(s) differ in a non-knob setting"] if sv['not_knobs'] else [])
    L.append(f"- Ranked ({len(sv['ranking'])}): {', '.join(sv['ranking']) or 'none'}. A2 (the 729-config factorial): "
             + (f"runs on {', '.join(sv['top6'])}." if sv['a2_runs'] else f"does not run ({sv.get('a2_reason')}).")
             + (' ' + ' and '.join(extra) + ': not in the ranking.' if extra else ''))
    if s['sensitivity_factorial']:
        L.append("Threshold factorial main effects (descriptive: mean net a match by level, averaged over the other thresholds): "
                 + '; '.join(f"{k}: " + ', '.join(f"{lv}: {x:.4f}" for lv, x in v['levels'].items()) + f" (range {v['range']:.4f})"
                             for k, v in s['sensitivity_factorial'].items()) + '.')
    L.append('')
    L.append('Biggest losers (production, F1):')
    for r_ in [x for x in loser_rows if x['run'] in prod_runs][:12]:
        sig = '+'.join(n for b, n in ((1, 'momentum'), (2, 'flow'), (4, 'depth'), (8, 'opponent')) if r_['signals'] & b) or 'none'
        L.append(f"- {r_['tour']} {r_['phase']} {r_['leg']} -> {r_['exit']}, {r_['bucket']}c, signals {sig}: {r_['n']} trades, {usd(r_['net'])} ({r_['win']:.0%} won)")
    if fb:
        L.append('')
        L.append('### Family B (TA-Lib event study, sterile)')
        gb = fb['gates']
        L.append(f"{fb['cells_with_entries']} cells with entries ({fb.get('entries', 0)} entries) of a design of {fb['design_size']} (stratum {fb['stratum']}); "
                 f"BH at q = {a.alpha} over the design (m = {fb['bh_m']}, its own family) rejects {fb['bh_rejections']}. Gates passed: "
                 + ', '.join(f'{k} {gb.get(k, 0)}' for k in ('BH', 'entries>=100', 'days>=30', 'mean>0', 'folds>=60%', 'stress net>0', 'rule breaches=0', 'vs placebo z>=1.645'))
                 + f"; {gb.get('all', 0)} pass every discovery condition. Values are net $ per entry after fees; the bootstrap is the family A one "
                 f"(the same units and resamples); the placebo comparison is the paired per-unit difference of means.")
        L.append(f"DSR: SR0 = {fb['sr0']:.4f} per entry (variance across the {fb.get('v_sr_cells', 0)} cells with >= 100 entries), N = {fb['cells_with_entries']} (family B's N_raw).")
        dg = fb.get('diagnostics') or {}
        if dg:
            L.append('Diagnostics: ' + ', '.join(f'{k} {v}' for k, v in list(dg.items())[:12]) + '.')
        L.append('')
        L.append('| cell | entries | days | units | net | $/entry | 90% CI | p | BH | unit t | vs placebo (z) | stress net | folds+ | breaches | DSR |')
        L.append('|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|')
        for r_ in sorted(fb_rows, key=lambda r: (not r['flag'], r['p'], -r['mean']))[:25]:
            L.append(f"| {md(r_['reg_id'])} | {r_['n']} | {r_['days']} | {r_['units']} | {usd(r_['net'])} | {r_['mean']:.4f} | {r_['ci90'][0]:.3f}..{r_['ci90'][1]:.3f} | "
                     f"{r_['p']:.4f} | {'yes' if r_['bh'] else 'no'} | {f4(r_['t_unit'], '.2f')} | {f4(r_['placebo_diff'])} ({f4(r_['z_placebo'], '.2f')}) | "
                     f"{usd(r_['stress_net'])} | {'-' if r_['fold_share'] is None else format(r_['fold_share'], '.0%')} | {r_['rule_breaches']} | {f4(r_['dsr'], '.2f')} |")
    return L


if __name__ == '__main__':
    main()
