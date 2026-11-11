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
  pools (C9)  the matchList rows of the pool named by --pool are scored: 'disc' (H-DEV: start-era matches with a published
              start closing before DEV_TO, any choice stage), 'old' (stratum H0, stage 2 finalists only) or 'hold' (H-HOLD:
              matches starting from HOLD_FROM, stage 'hold' only: a frozen spec list scored once, C10). 'nostart',
              'embargo' (Jul 31 and the matches straddling DEV_TO) and the other pools' rows are left out and counted by pool
              in the coverage section; 'check' and the hash-sealed units are retired. Pools are per match; units stay
              Monday 05:00 UTC weeks for the bootstrap and the slicing, and a pool's hours are its units cut to its window
              (pool_window). The era edges come from the shard metas (meta.era), else this file's copy of
              research/tennisTaSweep.ts's constants; H-HOLD and its 6 fold edges from research/registry.py (H_HOLD, ho1_fill).
              matchList fold (1..6 on a hold match, else null) must equal the registry's edges (fold_problems).
  universe    family A: every owned match of the pool with a tape (a match the config did not trade counts 0). A cell
              = config x arm x tour x phase x price bucket of the entry (an "all" level on each axis); arms F1, F2, coin
              (the config's coin-flip placebo) and stick (measuring sticks: scored and logged, never screened or counted
              as hypotheses). Realized net after fees is the only score.
  bootstrap   stationary bootstrap over the time-ordered tournament-week units (A2: blocks are whole units, mean block
              length --block units, B = --boot) for every CI and p-value; p = (1 + #exceedances) / (B + 1), never 0
  screen      BH at q = --alpha over the F1 cells (family A) and, as its own family, over family B's design; then the
              section 6 conditions: >= 100 entries on >= 30 match-days, mean > 0, >= 60% of monthly folds with 10+
              entries positive, net positive under F2 (B: the stress column), zero settlement breaches for the CONFIG
              (A: any breach in any cell of any arm of the config fails every cell of it; B: the reading's exit rule)
  folds       months of each unit's last day (the Sunday before its Monday 05:00 UTC end): a unit is never split. A hold
              run uses the 6 HO-1 folds instead, by each match's UTC day at the registry's edges.
  placebo     A: per-unit paired difference against the config's coin arm, same bootstrap; B: paired per-unit difference
              of mean net per entry (cell minus placebo, units where both have entries) with a paired z
  day t       the match-day clustered t of section 6, kept as a descriptive column (A2), vs zero and vs the placebo
  ONC         N_eff = clusters of the per-match P&L correlation (distance sqrt((1 - rho) / 2)) over the F1 cells with
              >= --onc-min entries (Lopez de Prado clusterKMeansTop: k-means base over k = 2..n - 1 with no cap by
              default, every k to 40 and a 10% geometric grid above refined around the best, scored by the silhouette t
              on the exact distances; the below-mean clusters are re-clustered and the result is kept only if the mean
              cluster t rises). The k range, the scan and a warning when a cap binds or k = 2 wins go to summary.json
              (onc) and report.md
  SPA/StepM   Hansen SPA (consistent) and Romano-Wolf StepM over the ONC medoids + each cluster's best cell + production
              + every flagged cell
  DSR         deflated Sharpe at N_eff on per-match Sharpe with the per-match skew and kurtosis. SR0 is per tour universe
              (all, ATP, WTA): its variance is taken across the N_eff cluster-mean series, each Sharpe over that
              universe's matches, and a cell's DSR uses the SR0 of its own universe (the one its SR is over). Family B:
              per-entry Sharpe at its own trial count.
  production  the config whose overrides equal production's spec by value (H: the ratchet off), not by id
  sensitivity section 5: range of mean net per match across a knob's levels, a config counting for a knob when it differs
              from the baseline (--baseline, else meta.baseline, else production) by value in that A1 knob alone; ranked
              by range, ties by the section 5 order, over each config's F1 all/all/all cell on the scored pool; A2 runs
              only if stage 2 on H-DISC ranks six knobs
  PBO         CSCV over the folds for the stage's config selection (the 'all' cells)
  $/h         net / pool wall-clock hours (pool units clipped to the data span, embargoed hours left out) and net /
              live-match hours (A7: close minus the published start; a match without one gets its series' median, else
              the pool's, else --live-median-hours; a pool with no published start at all and no --live-median-hours,
              i.e. H0, has no $/live-hour figure, said in report.md)
  registry    C7 / C11: report/registry-v1-<run>.jsonl, rows of the project registry v1 (research/registry.py, loaded
              from --registry-py; every row passes its validate() before anything is written). Family A: one row per config
              x arm (arm = the spec id, env = its overrides; the production F1 config is the control, other F1 configs are
              candidates against it, a config's F2 / F0 arm is its neighbour and its coin arm its placebo (placebo_for = the
              config's F1 arm), both against the config's F1 row, measuring sticks are controls). Family B: one row per
              reading x exit (its 'all' context; the other contexts in by_cell), a candidate against its own placebo row when
              the export carries per-day placebo sums. hours = the $/h denominator, contract_type 'tennis' and the modules
              each row changes (spec_modules), base 'tennis-ta@<sha>' and base_defaults (the overrides every spec shares that
              differ from production), data.replay_version (meta.replayVersion, else research/history/historyReplay.ts) and
              data.engine 'replay'. Families tennis-ta-A / tennis-ta-B for the start-era history (H), suffixed -H0 / -R for
              the other strata (reg_families). A disc (or H0) run is a dev-choice run: flags ['dev-choice'] and by_day over
              the pool's UTC match days, none in H-HOLD (refused otherwise). A hold run: by_day over every H-HOLD day (0 on a
              day without a trade), by_tercile {'ATP'|'WTA': {pnl, hours}} (the tours as the RV-tercile stand-in, hours =
              the tour's live-match hours), then the registry's ho1_fill fills each paired row's heldout block and each
              candidate's verdict is its ho1_pass; report.md scores each candidate per fold, per tour and against its placebo.
  one test    Amendment 4 (the contract; /mnt/project-files/tennis-ta/preregistration.md): the shard files' 'window' block
              (contract C12: one row per window arm '<config>|window' / '<config>|coinwindow' and leg, per-event instance
              and window counts n / w and twin counts tn / tw, the item 8 histograms, phases, end-rule count and asks)
              gives every hot spot (config x leg; 'both' = the legs pooled per event) its window rate, random rate, gap,
              cluster-robust SE by match (gap_stats, item 6, the same arithmetic as research/tennisTaWindow.ts gapStats),
              z = gap / SE and PASS = gap >= 2 x SE. A disc run writes the league (league.md: the top 40 by z, the
              production config's legs and the sticks; league.csv and league.json: every row with every information
              column; hold-batch-candidate.json: the 10 hottest family A hot spots by z, ties by gap, the batch a person
              copies to research/tennis-ta/hold-batch.json). A hold run with a batch (meta.batch, else the plan's, else
              research/tennis-ta/hold-batch.json) scores each member on the hold pool and writes hold-league.md /
              hold-league.json ('direction found' on a pass; the folds, tours, item 8 columns and the HO-1 money table as
              information). Registry rows (item 10): one per hot spot, arm '<config>|window|<leg>', data.metric
              window_gap (by_day and by_tercile hold the gap, never $), its coin placebo '|coinwindow|<leg>' as placebo_for,
              and on the read the registry's one-test heldout block. The HO-1 money bars, the discovery screen, SPA, DSR
              and PBO stay as information: nothing but the one test cuts a hot spot, and nothing in the report cuts a row.

Usage: tennis_ta_report.py --shards DIR --pool disc|old|hold --run RUN_ID --out DIR --registry-py registry.py --sha SHA
       [--plan prep/plan.json] [--units models/tennis-ta/state/units.json] [--boot 2000] [--block 1] [--seed 20261105]
       [--baseline CONFIG] [--ref DRIVE_FOLDER] [--live-median-hours H|SERIES=H,...|summary.json] [--no-registry (local runs: no rows)]
"""
import argparse
import gzip
import hashlib
import importlib.util
import json
import math
import os
import re
import sys
import warnings
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta

import numpy as np

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
DEFAULT_UNITS = os.path.join(REPO, 'models', 'tennis-ta', 'state', 'units.json')
PHASES = ['pre', 'e20', 'p1', 'p2', 'p3']
BUCKETS = ['8-15', '15-25', '75-85', '85-92', 'other']
ARMS = ('F0', 'F1', 'F2', 'coin', 'window', 'coinwindow')  # the P&L arms and the one test's window arms (Amendment 4)
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
# The era edges of research/tennisTaSweep.ts (C9; tests/test_tennis_ta_report.py holds them to it). Kalshi's tennis match
# history starts HISTORY_FROM; units starting before START_ERA_FROM are pool 'old' (stratum H0: no published start, the
# older "advances past the round" settlement rule, a different product). In the start era a match needs a published start
# (else 'nostart'); it is 'disc' (H-DEV) when it closes before DEV_TO, 'hold' (H-HOLD) when it starts from HOLD_FROM, and
# 'embargo' in between (Jul 31 and the matches straddling DEV_TO). START_ERA_FROM was pinned from the weekly inventory
# (Nov 11, run 43067646856: the week of 2026-04-20); a run's own edges are read from its shard metas (meta.era) and these
# are only the fallback.
HISTORY_FROM = ms_of('2025-06-18T00:00:00Z')
START_ERA_FROM = ms_of('2026-04-20T05:00:00Z')  # pinned Nov 11 from the weekly inventory (run 43067646856)
DEV_TO = ms_of('2026-07-31T00:00:00Z')
HOLD_FROM = ms_of('2026-08-01T00:00:00Z')
DEFAULT_ERA = {'historyFrom': HISTORY_FROM, 'startEraFrom': START_ERA_FROM, 'devTo': DEV_TO, 'holdFrom': HOLD_FROM, 'cutoff': HARD_CUTOFF}
# The pools of research/tennisTaSweep.ts (C9): the A3 hash seal and the dev-check pool are retired (the contiguous hold block
# replaces them; the old era needs no seal, nothing is chosen there), and the unit table's legacy `sealed` flags are ignored.
POOL_NAMES = ('old', 'nostart', 'disc', 'embargo', 'hold', 'out')
# Stages: '1' and '2' choose settings on H-DEV (pool disc; 'old' = H0 stress at stage 2); 'hold' scores a frozen spec list
# (research/tennis-ta/hold-specs.json) once on H-HOLD (C10).
HOLD_STAGE = 'hold'
# C7 (registry v1 rows)
REG_THREAD = 'tennis-ta'
REG_FAMILY_A = 'tennis-ta-A'
REG_FAMILY_B = 'tennis-ta-B'
PLACEBO_SEED = 20261105
# code_epoch = simVersion + '; REPLAY_VERSION=<n>; ' + CODE_EPOCH_TAIL, n read from the history replay the sweep built its days
# with (research/history/historyReplay.ts, next to this file), so the rows follow the code when the replay version moves.
CODE_EPOCH_TAIL = 'main with #290-#292; #279 and #287 merged in'
HISTORY_REPLAY_TS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'history', 'historyReplay.ts')
DRIVE_RUNS = 'gdrive:kalshi-bot-archive/models/tennis-ta/runs'
# HO-1 (registry README, project-wide from 22:30 UTC Nov 5): settings are chosen only on H-DEV; H-HOLD is scored once, in
# 6 consecutive folds. The registry module's own H_HOLD wins when it is loaded (this copy is the fallback).
HO1_HOLD = ('2026-08-01', '2026-11-04')
HO1_FOLDS = 6
# Registry flags per pool (C11): an H-DEV choice run is 'dev-choice' (counted, never scored as held out; its by_day stops
# before H-HOLD), H0 is a dev-side stress test of stage 2 finalists, a hold run carries no dev-choice flag.
DEV_FLAG = 'dev-choice'
REG_BASE = 'tennis-ta'
REG_ENGINE = 'replay'
# The bot module each setting belongs to (C7 modules; the contract-type ledger adds results over disjoint module sets).
# Production's end loser cut and the harness loser stop are exits, the pacer is the pacer, the bankroll is sizing; every
# other TENNIS_* key is the tennis rulebook (tennis-ta). Stress adversaries and decision-clock offsets change no module, so
# a run that moves only those measures the rulebook itself (tennis-ta).
MODULE_KEYS = {'TENNIS_END_LOSER_CUT': 'exits', 'HARNESS_LOSER_STOP': 'exits', 'HARNESS_PACER': 'pacer', 'HARNESS_BANKROLL': 'sizing'}


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


def z_json(z):
    """A z for JSON and CSV: JSON has no infinity (json.dumps writes the non-standard Infinity, or refuses it), so an infinite
    z (SE 0 with a gap, gap_stats) is spelt '+inf' / '-inf'; a finite z stays a number, none stays None."""
    if z is None or isinstance(z, str):
        return z
    z = float(z)
    return z if math.isfinite(z) else None if math.isnan(z) else '+inf' if z > 0 else '-inf'


def spell_inf(o):
    """o with every infinite float spelt '+inf' / '-inf' (z_json): the one test's files and registry rows, where an infinite z
    (SE 0 with a gap) must survive the JSON (clean() would write null)."""
    if isinstance(o, dict):
        return {k: spell_inf(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [spell_inf(v) for v in o]
    if isinstance(o, (float, np.floating)) and math.isinf(float(o)):
        return z_json(o)
    return o


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
                                     for k in ('overrides', 'fill', 'placebo', 'stick', 'offsetMs', 'window')):
                p.append(f'run {rid}: its overrides, fill, placebo, stick, offset or window flag differ across the shard files')
    cfg_ov, twins = {}, {}
    for rid in sorted(ref):
        r = ref[rid]
        if r['stick']:
            continue
        parts = rid.rsplit('|', 1)
        win = r.get('window') is True
        want = (('coinwindow' if r.get('placebo') == 'coin' else 'window') if win
                else 'coin' if r.get('placebo') == 'coin' else (r.get('fill') or 'F1'))
        if len(parts) != 2 or parts[1] not in ARMS:
            p.append(f"run {rid}: a non-stick run's id must end in its arm (|F0, |F1, |F2 or |coin; |window or |coinwindow for the one "
                     f"test's window arms, Amendment 4) so its arms link to one config (a measuring stick carries stick: true)")
            continue
        if parts[1] != want:
            runs_what = {'coin': 'the coin placebo', 'window': 'a window arm (window: true)',
                         'coinwindow': "a window arm's coin placebo (window: true, placebo coin)"}.get(want, 'fill ' + want)
            p.append(f"run {rid}: its id names arm {parts[1]} but it runs {runs_what}")
        ov = json.dumps(r['overrides'], sort_keys=True)
        if parts[0] in cfg_ov and cfg_ov[parts[0]][0] != ov:
            p.append(f'config {parts[0]}: its arms {cfg_ov[parts[0]][1]} and {rid} run different overrides')
        cfg_ov.setdefault(parts[0], (ov, rid))
        moved = [k for k in STICK_KEYS if k in r['overrides'] and ov_val(r['overrides'], k) != knob_val(k, STICK_KEYS[k])]
        if moved:
            p.append(f"run {rid}: moves {', '.join(moved)} (a stress adversary or measuring setting, never a hypothesis) but is not a "
                     f"measuring stick: mark it stick: true")
        if want not in ('coin', 'window', 'coinwindow'):  # a window arm trades nothing: never a twin of its F1 arm
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


def era_of(raw):
    """A run's era edges (meta.era / plan.era: ISO strings, research/tennisTaSweep.ts eraEdges) as ms; DEFAULT_ERA's
    values for anything missing or unreadable."""
    out = dict(DEFAULT_ERA)
    for k in out:
        v = (raw or {}).get(k) if isinstance(raw, dict) else None
        if isinstance(v, str):
            try:
                out[k] = ms_of(v)
            except ValueError:
                pass
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            out[k] = int(v)
    return out


def era_text(era, h_hold=HO1_HOLD):
    """The C9 era rule, stated with a run's edges."""
    d = lambda t: datetime.fromtimestamp(t / 1000, timezone.utc).strftime('%Y-%m-%d %H:%M UTC')  # noqa: E731
    return (f"history from {d(era['historyFrom'])} to the cutoff {d(era['cutoff'])}; units starting before {d(era['startEraFrom'])} are "
            f"pool old (stratum H0: no published start and the older advances-past-the-round settlement, a different product, a "
            f"stress test for stage 2 finalists only); from then a match needs a published start (else nostart: excluded and "
            f"counted); disc = H-DEV, the start-era matches closing before {d(era['devTo'])}; hold = H-HOLD, the matches starting "
            f"from {d(era['holdFrom'])} (start and close before the cutoff; scored on the UTC days {h_hold[0]} to {h_hold[1]} in "
            f"{HO1_FOLDS} folds, once per frozen spec list); embargo = the start-era matches in between (never scored)")


def unit_pools(u, era=None):
    """The pools a unit's matches can fall in (C9: pools are per match; units stay Monday 05:00 UTC weeks for the
    bootstrap and the slicing): {'out'} when it starts at or after the cutoff or ends by the history's start; {'old'}
    before the start era; else the start-era pools whose time it reaches: 'disc' when it starts before DEV_TO, 'embargo'
    when it reaches [DEV_TO, HOLD_FROM), 'hold' when it ends after HOLD_FROM. A unit's legacy `sealed` flag is ignored."""
    e = era or DEFAULT_ERA
    if u['start'] >= e['cutoff'] or u['end'] <= e['historyFrom']:
        return {'out'}
    if u['start'] < e['startEraFrom']:
        return {'old'}
    out = set()
    if u['start'] < e['devTo']:
        out.add('disc')
    if u['start'] < e['holdFrom'] and u['end'] > e['devTo']:
        out.add('embargo')
    if u['end'] > e['holdFrom']:
        out.add('hold')
    return out


def pool_window(pool, era=None, h_hold=HO1_HOLD):
    """[lo, hi) of wall-clock time a pool's hours come from, within its units: old = the old-era units' whole span, disc =
    up to DEV_TO, hold = HOLD_FROM to the end of H-HOLD's last UTC day (a hold match starting on a later UTC day, in the
    two hours before the cutoff, is not an H-HOLD match), each cut to the history and the cutoff."""
    e = era or DEFAULT_ERA
    if pool == 'disc':
        return e['historyFrom'], min(e['devTo'], e['cutoff'])
    if pool == 'hold':
        return max(e['holdFrom'], e['historyFrom']), min(day_ms(h_hold[1]) + DAY_MS, e['cutoff'])
    return e['historyFrom'], e['cutoff']


def ho1_fold_edges(h_hold=HO1_HOLD, k=HO1_FOLDS):
    """HO-1's fold edges, as research/registry.py ho1_fill cuts them: span = the hold's days, edge i = first day +
    round(i * span / k) days (Python's round, as the registry), the last fold running to the hold's last day. -> k
    (first day, last day) pairs, ISO."""
    from datetime import date
    d0, d1 = date.fromisoformat(h_hold[0]), date.fromisoformat(h_hold[1])
    span = (d1 - d0).days + 1
    edges = [d0 + timedelta(days=round(i * span / k)) for i in range(k + 1)]
    out = [(edges[i].isoformat(), (edges[i + 1] - timedelta(days=1)).isoformat()) for i in range(k)]
    out[-1] = (out[-1][0], d1.isoformat())
    return out


def ho1_fold_of(day, edges):
    """The HO-1 fold (1..k) of a UTC day, None outside H-HOLD."""
    for i, (a, b) in enumerate(edges):
        if a <= day <= b:
            return i + 1
    return None


def hold_days(h_hold=HO1_HOLD):
    from datetime import date
    d0, d1 = date.fromisoformat(h_hold[0]), date.fromisoformat(h_hold[1])
    return [(d0 + timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)]


def fold_problems(matches, edges):
    """matchList rows whose `fold` (C9: 1..6 for a hold match, by the registry's edges; null otherwise) disagrees with the
    registry's edges. A row without the key is not checked (an older sweep); a hold match on a UTC day after H-HOLD (it
    starts in the two hours before the cutoff) is no H-HOLD match, is left out of the hold score, and its fold is not read."""
    p = []
    lo, hi = edges[0][0], edges[-1][1]
    for m in matches:
        if 'fold' not in m:
            continue
        day = str(m.get('day'))
        if m.get('pool') == 'hold':
            if not (lo <= day <= hi):
                continue
            want = ho1_fold_of(day, edges)
        else:
            want = None
        got = m['fold']
        if isinstance(got, bool) or got != want:
            p.append(f"{m.get('event')} (pool {m.get('pool')}, day {day}): fold {json.dumps(got)}, the registry's edges give {json.dumps(want)}")
    return p


def hold_list_problems(runs, stratum='H'):
    """A hold run's frozen spec list, checked as stage 2's (C10): exactly one production-default F1 config (the control);
    every other config with an F1 run (a candidate) also runs its coin placebo and its F2 neighbour; no coin or F2 arm
    without its config's F1. Measuring sticks may ride along. Empty = sound."""
    p, arms = [], defaultdict(dict)
    for rid, r in runs.items():
        if r['stick']:
            continue
        cfg, _, tag = rid.rpartition('|')
        arms[cfg][tag] = r
    prod = [cfg for cfg, a in arms.items() if 'F1' in a and is_production(a['F1']['overrides'], stratum)]
    if len(prod) != 1:
        p.append(f"{len(prod)} F1 config(s) equal production by value ({', '.join(prod[:3]) or 'none'}): a hold list needs exactly one "
                 f"production-default F1 control")
    for cfg, a in sorted(arms.items()):
        if 'F1' not in a:
            p.append(f"config {cfg}: arm(s) {', '.join(sorted(a))} without its F1 run")
        elif cfg not in prod:
            miss = [t for t in ('coin', 'F2') if t not in a]
            if miss:
                p.append(f"candidate {cfg}|F1: no {' and no '.join(miss)} arm (a hold candidate is scored with its coin placebo and its F2 neighbour)")
    if not any(cfg not in prod and 'F1' in a for cfg, a in arms.items()):
        p.append('no candidate: the hold list holds the control only')
    return p


def pool_refusal(pools, stage=None, shard_pool=None):
    """Why --pool cannot be scored (None when it can). One pool a run (C10): 'disc' (H-DEV, any choice stage), 'old' (H0)
    at stage 2, 'hold' (H-HOLD) at stage 'hold' only (a frozen spec list, scored once); 'nostart', 'embargo' and 'out' are
    never scored."""
    bad = [p for p in pools if p not in POOL_NAMES]
    if bad or not pools:
        return f"unknown pool(s) {', '.join(bad) or '(none)'}: pools are {', '.join(POOL_NAMES)} (C9: 'check' and the hash-sealed units are retired; H-HOLD is pool 'hold')"
    if len(pools) != 1:
        return f"one pool per run ({', '.join(pools)} given): H-DEV, H-HOLD and the old era (H0) are never pooled"
    p = pools[0]
    if p in ('nostart', 'embargo', 'out'):
        return (f"pool '{p}' is never scored ('nostart' matches are excluded and counted in every run's coverage; embargoed and "
                f"out matches are streamed past)")
    if p == 'old' and stage is not None and str(stage) != '2':
        return f"pool 'old' (stratum H0) is a stress test for stage 2 finalists only, these shards are stage {stage}"
    if p == 'hold' and stage is not None and str(stage) != HOLD_STAGE:
        return (f"pool 'hold' (H-HOLD) is scored only by stage '{HOLD_STAGE}' (a frozen spec list, research/tennis-ta/hold-specs.json, "
                f"scored once), these shards are stage {stage}")
    if p != 'hold' and stage is not None and str(stage) == HOLD_STAGE:
        return f"stage '{HOLD_STAGE}' scores pool 'hold' only, not pool '{p}'"
    if shard_pool is not None and str(shard_pool) != p:
        return f"--pool {p} but the shards were swept for pool {shard_pool}"
    return None


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


def pool_spans_from_table(table, pools, only, era=None, h_hold=HO1_HOLD):
    """Fallback when neither the plan nor the shard metas carry poolSpans (research/tennisTaSweep.ts poolSpans): each
    swept unit of the pool cut to the pool's window (pool_window)."""
    e = era or DEFAULT_ERA
    out = []
    for p in pools:
        lo, hi = pool_window(p, e, h_hold)
        for u in table:
            if p in unit_pools(u, e) and u['id'] in only:
                iv = subtract(max(u['start'], lo), min(u['end'], hi), [])
                out.append({'unit': u['id'], 'start': u['start'], 'end': u['end'], 'intervals': [list(x) for x in iv],
                            'hours': sum(b - a for a, b in iv) / HOUR_MS})
    return out


def clip_spans(spans, lo, hi):
    """Spans with every interval cut to [lo, hi) (a sweep's whole-unit span of a unit straddling DEV_TO or HOLD_FROM keeps
    only its pool's part)."""
    out = []
    for s in spans:
        iv = [[max(a, lo), min(b, hi)] for a, b in s['intervals'] if min(b, hi) > max(a, lo)]
        out.append(dict(s, intervals=iv, hours=sum(b - a for a, b in iv) / HOUR_MS))
    return out


def clipped_hours(spans, lo, hi):
    return sum(max(0, min(b, hi) - max(a, lo)) for s in spans for a, b in s['intervals']) / HOUR_MS


# ---------------------------------------------------------------------------------------------------------------------
# Reading and checking the shard set

def ep_columns(rows, cols):
    """Episode rows (lists in meta.episodeCols order) as numpy columns."""
    n = len(rows)
    if not n:
        return {'m': np.zeros(0, dtype=np.int64), 'k': np.zeros(0, dtype=np.int64), 't': np.zeros(0), 'hold': np.zeros(0), 'px': np.zeros(0), 'pnl': np.zeros(0),
                'sig': np.zeros(0, dtype=np.int64), 'br': np.zeros(0, dtype=np.int64), 'ph': np.zeros(0, dtype='<U4'),
                'leg': np.zeros(0, dtype='<U4'), 'x': np.zeros(0, dtype='<U4')}
    d = dict(zip(cols, zip(*rows)))
    z = (0,) * n

    def num(c, dt):
        return np.asarray([0 if v is None else v for v in d.get(c, z)], dtype=dt)
    return {'m': num('m', np.int64), 'k': num('k', np.int64), 't': num('t', np.float64), 'hold': num('hold', np.float64), 'px': num('px', np.float64),
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
                   'stick': r.get('stick') is True or rid in sticks, 'offsetMs': r.get('offsetMs'), 'window': r.get('window') is True,
                   'pnl': np.asarray(pnl, dtype=np.float64), 'ep': ep}
    fb = d.get('familyB')
    events = [m.get('event') for m in ml]
    # The one test's blocks (contract C12): 'window' (family A's window arms) and 'familyBWindow' (family B's readings).
    win, fbw = d.get('window'), d.get('familyBWindow')
    win_keys, fbw_keys = (), ()
    if win is not None:
        wp, win_keys = check_window_block(name, win, events, 'window')
        problems += wp
    if fbw is not None:
        if win is None:
            problems.append(f'{name}: a familyBWindow block without the window block its rows index into')
        else:
            wp, fbw_keys = check_window_block(name, fbw, events, 'familyBWindow')
            problems += wp
    if win is None and any(r['window'] for r in rd.values()):
        problems.append(f"{name}: window arm(s) ({', '.join(sorted(k for k, r in rd.items() if r['window'])[:3])}) but no window block (C12)")
    b_diag = (fb.get('diagnostics') or {}) if isinstance(fb, dict) else {}
    info = {'file': name, 'meta': meta, 'events': events, 'run_ids': tuple(sorted(rd)), 'has_b': fb is not None,
            'b_design': fb.get('designSize') if isinstance(fb, dict) else None, 'b_stratum': fb.get('stratum') if isinstance(fb, dict) else None,
            'b_tours': b_diag.get('tours'), 'b_phases': (b_diag.get('settings') or {}).get('phasesInDesign'),
            'row_units': {m.get('unit') for m in ml}, 'b_units': ({u for c in fb.get('cells', []) for u in (c.get('units') or {})} if isinstance(fb, dict) else set()),
            'has_window': win is not None, 'window_version': win.get('version') if isinstance(win, dict) else None, 'window_keys': win_keys,
            'has_fbw': fbw is not None, 'fbw_keys': fbw_keys, 'problems': problems}
    return info, {'matches': ml, 'runs': rd, 'familyB': fb, 'window': win, 'familyBWindow': fbw}


CONSISTENT = ('run', 'stage', 'pool', 'simVersion', 'dataVersion', 'families', 'shards')
CONSISTENT_IF_SET = ('requestSha', 'unitsSha', 'stratum', 'era', 'replayVersion', 'specsHash', 'windowVersion', 'batchHash', 'leagueRun')
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
    # The one test's blocks (C12): the window block in every file or in none, one version, the same rows (window arms x
    # legs, family B readings) in every file.
    has_w = [bool(i.get('has_window')) for i in infos]
    if any(has_w) and not all(has_w):
        p.append('the window block (C12) is in some shard files and not in others: ' + ', '.join(i['file'] for i in infos if not i.get('has_window'))[:300])
    if len({i.get('window_version') for i in infos if i.get('has_window')}) > 1:
        p.append('the window block version differs across the shard files')
    for i in infos[1:]:
        if i.get('has_window') and ref.get('has_window') and i.get('window_keys') != ref.get('window_keys'):
            p.append(f"{i['file']}: its window rows differ from {ref['file']}")
        if bool(i.get('has_fbw')) != bool(ref.get('has_fbw')) or (i.get('has_fbw') and i.get('fbw_keys') != ref.get('fbw_keys')):
            p.append(f"{i['file']}: its familyBWindow rows differ from {ref['file']}")

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
    era = era_of(metas[0].get('era') or (plan or {}).get('era'))
    swept = sorted(unit_file, key=lambda u: by_id[u]['start'])
    for a_, b_ in zip(swept, swept[1:]):
        gap = [u['id'] for u in table if by_id[a_]['start'] < u['start'] < by_id[b_]['start'] and pool in unit_pools(u, era)]
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
            if plan.get('era') is not None and m.get('era') is not None and era_of(m['era']) != era_of(plan['era']):
                p.append(f"{i['file']}: meta.era (the pool edges it was swept with) differs from the plan's")
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
                                    'breaches': 0, 'gross': 0.0, 'fees': 0.0, 'stressSum': 0.0, 'units': {}, 'days': {},
                                    'day_cols': None, 'markets': 0, 'placeboMarkets': 0, 'has_markets': True}
                order.append(cid)
            elif acc['group'] != c.get('group'):
                problems.append(f"familyB cell {cid}: group {c.get('group')} in one shard, {acc['group']} in another")
            for k in ('n', 'sum', 'sumSq', 'sum3', 'sum4', 'breaches', 'gross', 'fees', 'stressSum'):
                acc[k] += c.get(k) or 0
            # Distinct markets with a real / placebo entry (FamilyBCell.markets): a match is owned by one slice, so they add.
            acc['has_markets'] = acc['has_markets'] and 'markets' in c and 'placeboMarkets' in c
            acc['markets'] += c.get('markets') or 0
            acc['placeboMarkets'] += c.get('placeboMarkets') or 0
            for u, v in (c.get('units') or {}).items():
                cur = acc['units'].setdefault(u, [0, 0.0, 0, 0.0])
                for q in range(4):
                    cur[q] += v[q] if q < len(v) and v[q] is not None else 0
            for dd, v in (c.get('days') or {}).items():
                # [entries, net] (FamilyBCell.days); [entries, net, placebo entries, placebo net] when the export carries
                # per-day placebo sums, which the registry's placebo row needs (day_placebo: every day row had them).
                cur = acc['days'].setdefault(dd, [0, 0.0, 0, 0.0])
                for q in range(4):
                    cur[q] += v[q] if q < len(v) and v[q] is not None else 0
                acc['day_cols'] = len(v) if acc['day_cols'] is None else min(acc['day_cols'], len(v))
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
                                        'stick': r['stick'], 'offsetMs': r.get('offsetMs'), 'window': r.get('window', False), 'pnl': [],
                                        'ep': defaultdict(list)})
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
        cols = [c['day_cols'] for c in b_cells if c['day_cols'] is not None]
        fam_b = {'stratum': fbs[0].get('stratum'), 'designSize': design_b(infos)[0], 'diagnostics': diag, 'cells': b_cells,
                 # per-day placebo sums in every day row of the export (the registry's family B placebo rows need them)
                 'day_placebo': bool(cols) and min(cols) >= 4}
    # The one test's blocks (C12), every file's in slice order: the row arrays index into the merged event list.
    wparts = [(datas[i]['window'], datas[i].get('familyBWindow')) for i in order if datas[i].get('window') is not None]
    wd = merge_window(wparts) if wparts else None
    metas = [infos[i]['meta'] for i in order]
    return {'matches': matches, 'runs': runs, 'familyB': fam_b, 'metas': metas, 'files': [infos[i]['file'] for i in order], 'window': wd}


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

# ---------------------------------------------------------------------------------------------------------------------
# The one test (Amendment 4): the shard files' 'window' block (contract C12), gap_stats as research/tennisTaWindow.ts
# gapStats computes it (item 6), the league (item 7), the information columns (item 8), the batch of the read and the
# registry's one-test rows (item 10). No other statistical bar exists: everything that is not the one test is information.

WINDOW_VERSION = 'tennis-ta-window/1'
WINDOW_ARMS = ('window', 'coinwindow')
HOLD_LEGS = ('underdog', 'fav', 'both')
HOLD_BATCH_FILE = os.path.join(REPO, 'research', 'tennis-ta', 'hold-batch.json')
HOLD_BATCH_MAX = 10
TWINS = 3              # twins an instance (item 5); a coin side with no eligible minute draws no twin (drawTwins), so a row's tn_i can fall short of TWINS x n_i
STICK_ID = re.compile(r'^A\|s[12]\|prod\|')   # a measuring stick's config id (the sweep's stage1Specs sticks / S2_STICK): reported, never a hot spot of the batch (item 1, C4)
ONE_TEST_K = 2.0       # PASS = gap >= ONE_TEST_K x SE (item 6)
LEAGUE_TOP = 40        # league.md shows the top 40 by z (league.csv / league.json hold every row)
HIST_EDGES = {'tWin': [1, 2, 3, 5, 10, 15, 30, 60, 120], 'lenWin': [1, 2, 3, 5, 10, 20, 40],
              'dip': [0, -0.01, -0.02, -0.03, -0.05, -0.08, -0.12, -0.20], 'held': [0, 1, 2, 5, 10, 20, 40, 80]}
HIST_KEYS = ('tWin', 'lenWin', 'dip', 'held')
HIST_NAMES = {'tWin': 'minutes to the window', 'lenWin': 'window length (minutes at or above the level)',
              'dip': 'wrong-way dip before the window (lowest bid minus entry, $)', 'held': 'minutes held at or above the level'}
CALENDAR = '/mnt/project-files/registry/edge-pipeline/calendar.md'
ONE_TEST_RULE = ('hot spot = one config and one leg (underdog, fav, or both pooled); instance = the first decision at which '
                 "production's decideMatch emits the leg's entry plan for a flat market, a taker buy of the called market at its ask, "
                 'C = max(1, floor($10 / ask)); level L = entry + both taker fees + 1c a contract; window = the first one-minute '
                 "candle of the called market starting at or after the entry (a full minute after the buy, Amendment 4a), ending at or before the end rule (latched progress 1 - 0.30, else "
                 'the close), two-sided, with its lowest bid >= L; three random twins per instance (same match, same UTC hour, the '
                 'instance\'s own called market, Amendment 4a); gap = window rate - random rate, SE cluster-robust by match (item 6: d_i = w_i/n_i - '
                 'tw_i/tn_i, gap = sum(n_i d_i) / sum(n_i), SE = sqrt(sum(n_i^2 (d_i - gap)^2)) / sum(n_i)); PASS = gap >= 2 x SE; '
                 'z = gap / SE (as research/tennisTaWindow.ts gapStats), no z without an instance, a twin '
                 'or a contributing match, or on SE 0 (the chance wobble cannot be measured, Amendment 4a)')


def gap_stats(n, w, tn, tw, twins=TWINS):
    """Amendment 4 item 6, exactly as research/tennisTaWindow.ts gapStats: over the matches i (array index) with n_i > 0 and
    tn_i > 0, d_i = w_i / n_i - tw_i / tn_i, gap = sum(n_i d_i) / sum(n_i), SE = sqrt(sum(n_i^2 (d_i - gap)^2)) / sum(n_i),
    z = gap / SE (None without a contributing match or on SE 0, Amendment 4a item 2, as the TS), PASS = gap >= 2 x SE
    (with a z). rate = w / n and random = tw / tn over every match (NaN on 0). Arrays of unequal length pad with 0. matches = the
    matches with an instance, clustered = those that contribute a d_i. Beside them: rate_weighted = sum(w_i) / sum(n_i) and
    random_weighted = sum(n_i tw_i / tn_i) / sum(n_i) over the contributing matches, so that gap = rate_weighted -
    random_weighted exactly (the registry's one-test block carries these two, one_test_block); the pooled rate - random
    equals that gap only when every instance drew `twins` twins and every match with an instance has one. twins_short =
    sum(max(0, twins n_i - tn_i)), the twins the instances drew short of `twins` each (item 5: a coin side with no eligible
    minute draws none), over events_short matches (information: it says when the pooled difference is not the gap)."""
    L = max(len(n), len(w), len(tn), len(tw))
    N = W = TN = TW = 0
    sum_n = sum_nd = sum_w = sum_r = 0.0
    ds = []
    matches = twins_short = events_short = 0
    for i in range(L):
        ni = n[i] if i < len(n) else 0
        wi = w[i] if i < len(w) else 0
        tni = tn[i] if i < len(tn) else 0
        twi = tw[i] if i < len(tw) else 0
        N += ni
        W += wi
        TN += tni
        TW += twi
        if ni > 0:
            matches += 1
            if tni < twins * ni:
                events_short += 1
                twins_short += twins * ni - tni
        if ni > 0 and tni > 0:
            d = wi / ni - twi / tni
            ds.append((ni, d))
            sum_n += ni
            sum_nd += ni * d
            sum_w += wi
            sum_r += ni * (twi / tni)
    nan = float('nan')
    rate = W / N if N > 0 else nan
    random = TW / TN if TN > 0 else nan
    out = {'n': N, 'w': W, 'tn': TN, 'tw': TW, 'rate': rate, 'random': random, 'matches': matches, 'clustered': len(ds),
           'twins_short': twins_short, 'events_short': events_short}
    if not ds:
        out.update(gap=nan, se=nan, z=None, rate_weighted=nan, random_weighted=nan, **{'pass': False})
        return out
    gap = sum_nd / sum_n
    out.update(rate_weighted=sum_w / sum_n, random_weighted=sum_r / sum_n)
    ss = 0.0
    for ni, d in ds:
        ss += ni * ni * (d - gap) * (d - gap)
    se = math.sqrt(ss) / sum_n
    # As research/tennisTaWindow.ts gapStats: z = gap / SE when SE > 0; None on SE 0 (one contributing match, or identical d_i:
    # the chance wobble cannot be measured, Amendment 4a item 2; the registry refuses se 0 too). PASS = gap >= 2 x SE with a z.
    z = gap / se if se > 0 else None
    out.update(gap=gap, se=se, z=z, **{'pass': z is not None and gap >= ONE_TEST_K * se})
    return out


def window_arm_of(rid):
    """(config, arm) of a window-arm run id ('<config>|window' or '<config>|coinwindow'); None for any other id."""
    cfg, _, arm = str(rid).rpartition('|')
    return (cfg, arm) if arm in WINDOW_ARMS and cfg else None


def hist_bins(edges):
    """The bin labels of a HIST_EDGES list (ascending: < e0, [e0, e1), ..., >= last; dip's descending list: > 0,
    (-0.01, 0], ..., <= -0.20), one per count of a row's hist array."""
    desc = len(edges) > 1 and edges[1] < edges[0]
    out = []
    for k in range(len(edges) + 1):
        if k == 0:
            out.append(f'>{edges[0]:g}' if desc else f'<{edges[0]:g}')
        elif k == len(edges):
            out.append(f'<={edges[-1]:g}' if desc else f'>={edges[-1]:g}')
        else:
            out.append(f'{edges[k]:g}..{edges[k - 1]:g}' if desc else f'{edges[k - 1]:g}..{edges[k]:g}')
    return out


def hist_quantile(edges, counts, q):
    """The bin (its label) holding the q-quantile of a binned sample: the first bin at which the cumulative count reaches
    q x total; None when the histogram is empty. The bins are the resolution the shard files keep (C12), so the quartiles
    are bins, not numbers."""
    labels = hist_bins(edges)
    total = sum(counts)
    if total <= 0:
        return None
    target = q * total
    acc = 0
    for k, c in enumerate(counts[:len(labels)]):
        acc += c
        if acc >= target:
            return labels[k]
    return labels[min(len(counts), len(labels)) - 1]


def hist_summary(kind, counts):
    edges = HIST_EDGES[kind]
    counts = [int(c) for c in counts]
    return {'bins': hist_bins(edges), 'counts': counts, 'total': sum(counts), 'q1': hist_quantile(edges, counts, 0.25),
            'median': hist_quantile(edges, counts, 0.5), 'q3': hist_quantile(edges, counts, 0.75)}


def check_window_block(name, block, ml_events, kind='window'):
    """Problems with one shard file's 'window' (or 'familyBWindow') block (C12): events (the slice's, in matchList order:
    at least the matchList's rows, each with its event) and rows with per-event count arrays no longer than the events,
    hist counts of HIST_EDGES' bins, byPhase, endNoWin and asks. Returns (problems, the sorted (id, leg) row keys)."""
    p = []
    if not isinstance(block, dict) or not isinstance(block.get('rows'), list):
        return [f'{name}: the {kind} block is not an object with rows'], ()
    if kind == 'window':
        ev = block.get('events')
        if not isinstance(ev, list) or len(ev) < len(ml_events) or any(not isinstance(e, dict) or not e.get('event') for e in ev):
            return [f"{name}: the window block's events are not a list of at least the matchList's {len(ml_events)} events"], ()
        bad = [i for i, e in enumerate(ml_events) if ev[i].get('event') != e]
        if bad:
            p.append(f"{name}: the window block's events are not in matchList order (first at index {bad[0]})")
        if block.get('version') != WINDOW_VERSION:
            p.append(f"{name}: window block version {block.get('version')!r}, this report reads {WINDOW_VERSION}")
        n_ev = len(ev)
    else:
        n_ev = None
    keys = []
    for r in block['rows']:
        rid = r.get('id') if isinstance(r, dict) else None
        if not isinstance(rid, str) or not rid:
            p.append(f'{name}: a {kind} row has no id')
            continue
        leg = r.get('leg')
        key = (rid, leg)
        if key in keys:
            p.append(f'{name}: {kind} row {rid} / {leg} appears twice')
        keys.append(key)
        at = f'{name}: {kind} row {rid}' + (f' / {leg}' if leg is not None else '')
        for k in ('n', 'w', 'tn', 'tw'):
            v = r.get(k)
            if not isinstance(v, list) or (n_ev is not None and len(v) > n_ev) \
                    or any(isinstance(x, bool) or not isinstance(x, (int, float)) or x < 0 for x in v):
                p.append(f'{at}: {k} is not a list of counts over the events')
        h = r.get('hist')
        if not isinstance(h, dict) or any(not isinstance(h.get(k), list) or len(h[k]) != len(HIST_EDGES[k]) + 1 for k in HIST_KEYS):
            p.append(f'{at}: hist is not {{tWin, lenWin, dip, held}} counts over the HIST_EDGES bins')
        bp = r.get('byPhase')
        if not isinstance(bp, dict) or any(not (isinstance(v, list) and len(v) == 2) for v in bp.values()):
            p.append(f'{at}: byPhase is not {{phase: [n, w]}}')
        if isinstance(r.get('endNoWin'), bool) or not isinstance(r.get('endNoWin'), (int, float)):
            p.append(f'{at}: endNoWin is not a count')
        asks = r.get('asks')
        if not (isinstance(asks, list) and len(asks) == 2 and all(isinstance(x, (int, float)) for x in asks)):
            p.append(f'{at}: asks is not [n, sum of asks]')
    return p, tuple(sorted(keys, key=lambda k: (k[0], str(k[1]))))


def merge_window(parts):
    """parts: per shard file in slice order, (its 'window' block, its 'familyBWindow' block or None) -> the run's one-test
    data: events (every file's, in order; the row arrays index into it), rows {(id, leg): row} with the per-event arrays
    laid end to end (0 where a file has no row) and hist / byPhase / endNoWin / asks added, family B rows the same way
    (rows_b; they index into the same events), and the block's constants from the first file."""
    events, rows, rows_b = [], {}, {}

    def acc(store, row, off, n_ev):
        key = (str(row['id']), row.get('leg'))
        r = store.get(key)
        if r is None:
            r = store[key] = {'id': str(row['id']), 'leg': row.get('leg'), 'n': [], 'w': [], 'tn': [], 'tw': [],
                              'hist': {k: [0] * (len(HIST_EDGES[k]) + 1) for k in HIST_KEYS}, 'byPhase': {ph: [0, 0] for ph in PHASES},
                              'endNoWin': 0, 'asks': [0.0, 0.0]}
        for k in ('n', 'w', 'tn', 'tw'):
            arr = r[k]
            arr.extend([0] * (off - len(arr)))
            vals = list(row.get(k) or [])[:n_ev]
            arr.extend(vals + [0] * (n_ev - len(vals)))
        for k in HIST_KEYS:
            for i, v in enumerate((row.get('hist') or {}).get(k) or []):
                if i < len(r['hist'][k]):
                    r['hist'][k][i] += v
        for ph, v in (row.get('byPhase') or {}).items():
            cur = r['byPhase'].setdefault(ph, [0, 0])
            cur[0] += v[0]
            cur[1] += v[1]
        r['endNoWin'] += row.get('endNoWin') or 0
        a_ = row.get('asks') or [0, 0]
        r['asks'][0] += a_[0]
        r['asks'][1] += a_[1]

    first = None
    for win, fbw in parts:
        off = len(events)
        ev = win['events']
        events.extend(ev)
        for row in win['rows']:
            acc(rows, row, off, len(ev))
        for row in (fbw or {}).get('rows') or []:
            acc(rows_b, row, off, len(ev))
        first = first or win
    for store in (rows, rows_b):
        for r in store.values():
            for k in ('n', 'w', 'tn', 'tw'):
                r[k].extend([0] * (len(events) - len(r[k])))
    consts = {k: first.get(k) for k in ('version', 'settleFrac', 'orderUsd', 'twins', 'seed')} if first else {}
    return dict(consts, events=events, rows=rows, rows_b=rows_b)


def pool_window_rows(rows, rid, leg='both'):
    """The 'both' row of a config: the legs' rows pooled (n / w / tn / tw add per event, hist / byPhase / endNoWin / asks
    add), as research/tennisTaWindow.ts poolRows."""
    L = max([len(r['n']) for r in rows] + [0])
    out = {'id': rid, 'leg': leg, 'hist': {k: [0] * (len(HIST_EDGES[k]) + 1) for k in HIST_KEYS}, 'byPhase': {ph: [0, 0] for ph in PHASES},
           'endNoWin': 0, 'asks': [0.0, 0.0]}
    for k in ('n', 'w', 'tn', 'tw'):
        arr = [0] * L
        for r in rows:
            for i, v in enumerate(r[k]):
                arr[i] += v
        out[k] = arr
    for r in rows:
        for k in HIST_KEYS:
            for i, v in enumerate(r['hist'][k]):
                out['hist'][k][i] += v
        for ph, v in r['byPhase'].items():
            cur = out['byPhase'].setdefault(ph, [0, 0])
            cur[0] += v[0]
            cur[1] += v[1]
        out['endNoWin'] += r['endNoWin']
        out['asks'][0] += r['asks'][0]
        out['asks'][1] += r['asks'][1]
    return out


def one_test_of(row, idx, events, fold_of=None, twins=TWINS):
    """One hot spot's one test over the events at indices idx (the scored pool's matches): gap_stats, then the item 8
    information: by tour, by UTC match day, by HO-1 fold (a hold run, nothing judged), the binned minutes to the window,
    window length, wrong-way dip and minutes held, the phases, the share resolved by the end rule or the close without a
    window and the mean entry ask. The histograms, phases, end-rule share and asks are the row's totals over every
    instance the arm recorded in the slices (C12 keeps them per row, not per event; n_all says how many), the counts and
    the test are over the pool's matches only."""
    def pick(key, sel):
        return [row[key][i] for i in sel]

    def sub(sel):
        return gap_stats(*(pick(k, sel) for k in ('n', 'w', 'tn', 'tw')), twins=twins)
    g = sub(idx)
    tours = {t: sub([i for i in idx if events[i].get('tour') == t]) for t in ('ATP', 'WTA')}
    days = defaultdict(list)
    for i in idx:
        days[str(events[i].get('day'))].append(i)
    by_day = {d: {k: v[k] for k in ('n', 'w', 'tn', 'tw', 'gap')} for d, sel in sorted(days.items()) for v in [sub(sel)]}
    by_fold = None
    if fold_of is not None:
        fsel = defaultdict(list)
        for i in idx:
            f = fold_of(str(events[i].get('day')))
            if f is not None:
                fsel[f].append(i)
        by_fold = {str(f): sub(fsel.get(f, [])) for f in range(1, HO1_FOLDS + 1)}
    n_all = sum(row['n'])
    return dict(g, n_all=n_all, by_tour=tours, by_day=by_day, by_fold=by_fold,
                hist={k: hist_summary(k, row['hist'][k]) for k in HIST_KEYS},
                by_phase={ph: {'n': int(v[0]), 'w': int(v[1]), 'rate': (v[1] / v[0]) if v[0] else None} for ph, v in row['byPhase'].items()},
                end_no_window=row['endNoWin'], end_no_window_share=(row['endNoWin'] / n_all) if n_all else None,
                mean_ask=(row['asks'][1] / row['asks'][0]) if row['asks'][0] else None)


def rank_league(rows):
    """The league order (item 7): by z, ties by gap; rows without a z last (by gap, then id and leg). Sets rank."""
    def key(r):
        z, g = r.get('z'), r.get('gap')
        return (z is None, -(z if z is not None else 0.0), -(g if finite(g) else -1e18), str(r['id']), str(r.get('leg')))
    rows.sort(key=key)
    for i, r in enumerate(rows):
        r['rank'] = i + 1
    return rows


def league_table(wd, idx, runs, cells, by_id, fold_of=None):
    """Family A's league rows: one per hot spot (config x leg, 'both' = the two legs pooled per event) from the merged
    'window' rows, each with its coin placebo's own one test (the |coinwindow row of the same config and leg) and the
    after-fee P&L per entry of the config's production exits (the F1 and F2 all/all/all cells, or the stick's F1 cell)."""
    twins = int(wd.get('twins') or TWINS)
    configs = {}
    for (rid, leg), row in wd['rows'].items():
        wa = window_arm_of(rid)
        if not wa or leg not in ('underdog', 'fav'):
            continue
        cfg, arm = wa
        configs.setdefault(cfg, {'window': {}, 'coinwindow': {}})[arm][leg] = row
    out = []
    for cfg in sorted(configs):
        c = configs[cfg]
        if not c['window']:
            continue
        legs = dict(c['window'])
        legs['both'] = pool_window_rows(list(c['window'].values()), f'{cfg}|window', 'both')
        coins = dict(c['coinwindow'])
        if coins:
            coins['both'] = pool_window_rows(list(c['coinwindow'].values()), f'{cfg}|coinwindow', 'both')
        stick = bool((runs.get(f'{cfg}|window') or {}).get('stick'))
        f1 = cells[by_id[(cfg, 'F1', 'all', 'all', 'all')]] if (cfg, 'F1', 'all', 'all', 'all') in by_id \
            else cells[by_id[(f'{cfg}|F1', 'stick', 'all', 'all', 'all')]] if (f'{cfg}|F1', 'stick', 'all', 'all', 'all') in by_id else None
        f2 = cells[by_id[(cfg, 'F2', 'all', 'all', 'all')]] if (cfg, 'F2', 'all', 'all', 'all') in by_id else None
        pnl = {k: ({'arm': x['run'], 'entries': x['entries'], 'net': x['net'], 'per_entry': (x['net'] / x['entries']) if x['entries'] else None}
                   if x is not None else None) for k, x in (('f1', f1), ('f2', f2))}
        for leg in HOLD_LEGS:
            if leg not in legs:
                continue
            ot = one_test_of(legs[leg], idx, wd['events'], fold_of, twins)
            coin = None
            if leg in coins:
                cg = one_test_of(coins[leg], idx, wd['events'], fold_of, twins)
                coin = {k: cg[k] for k in ('n', 'w', 'tn', 'tw', 'rate', 'random', 'gap', 'se', 'z', 'pass', 'matches', 'clustered', 'twins_short',
                                           'events_short', 'rate_weighted', 'random_weighted', 'n_all', 'by_tour', 'by_day')}
                coin['id'] = f'{cfg}|coinwindow'
            out.append(dict({'family': 'A', 'id': f'{cfg}|window', 'config': cfg, 'leg': leg, 'hot_spot': f'{cfg}|{leg}', 'stick': stick,
                             'production': False}, **ot, coin=coin, f1=pnl['f1'], f2=pnl['f2']))
    return rank_league(out)


def league_table_b(wd, idx, fold_of=None):
    """Family B's league rows (its own table): one per reading x bar x direction row of the 'familyBWindow' blocks."""
    out = []
    for (rid, leg), row in sorted(wd['rows_b'].items(), key=lambda kv: (kv[0][0], str(kv[0][1]))):
        ot = one_test_of(row, idx, wd['events'], fold_of, int(wd.get('twins') or TWINS))
        out.append(dict({'family': 'B', 'id': rid, 'config': rid, 'leg': leg, 'hot_spot': rid if leg is None else f'{rid}|{leg}', 'stick': False,
                         'production': False}, **ot, coin=None, f1=None, f2=None))
    return rank_league(out)


def batch_candidate(league_a, run_id):
    """The batch for the read (item 7): the HOLD_BATCH_MAX hottest family A hot spots by z on the league (ties by gap),
    as research/tennis-ta/hold-batch.json takes them ({league_run, batch: [{id, leg}]} and nothing else: the sweep's
    validateHoldBatch refuses any other key), with this league's run id. A measuring stick is never one of them: a hot
    spot is a config of the gradient matrix (item 1) and a stick is reported, never screened or counted (C4); the sticks
    stay in the league as information. Only a disc run writes it (item 7: the league runs on H-DEV only)."""
    hot = [r for r in league_a if r.get('z') is not None and not r.get('stick')][:HOLD_BATCH_MAX]
    return {'league_run': str(run_id), 'batch': [{'id': r['config'], 'leg': r['leg']} for r in hot]}


def no_z_why(r):
    """Why a row has no z: no instance, no twin, no contributing match (no match with both), or SE 0 (Amendment 4a item 2)."""
    return ('no instance' if not r['n'] else 'no twin' if not r['tn'] else 'no contributing match (no match with both an instance and a twin)'
            if not r['clustered'] else 'SE 0: the per-match differences do not vary (one contributing match, or identical ones), so the chance wobble cannot be measured')


def twins_short_note(r):
    """The twin shortfall of a row, named beside its figures (item 5: an instance whose coin side had no eligible minute drew
    fewer than TWINS twins); then the pooled rates' difference is not the item 6 gap, and the registry block's rates are
    item 6's weighted ones (one_test_block). '' when every instance drew its TWINS twins."""
    k = int(r.get('twins_short') or 0)
    if not k:
        return ''
    note = f"; {k} twin(s) short of {TWINS} an instance over {int(r.get('events_short') or 0)} match(es)"
    if finite(r.get('gap')) and finite(r.get('rate')) and finite(r.get('random')):
        note += (f", so the pooled rate - random ({r['rate'] - r['random']:+.4f}) is not the gap: the registry block's rates are item 6's "
                 f"weighted ones")
    return note


def one_test_verdict(r, read=False, pool='disc'):
    """The verdict text of a hot spot's row: the one test's figures; on the read, 'direction found' when it passes; on a
    scored pool that is neither the league's (disc) nor the read's (hold), information only (item 7)."""
    if r.get('z') is None:
        figs = f"n {int(r['n'])}, windows {int(r['w'])}, twins {int(r['tn'])} / {int(r['tw'])}: no z ({no_z_why(r)})"
        return ('not found: ' if read else 'one test (information, no read): ') + figs + twins_short_note(r)
    figs = (f"n {int(r['n'])}, windows {int(r['w'])} (rate {r['rate']:.3f}), twins {int(r['tn'])} / {int(r['tw'])} (random {r['random']:.3f}), "
            f"gap {r['gap']:+.4f}, SE {r['se']:.4f}, z {_zf(r)}, {'gap >= 2 x SE' if r['pass'] else 'gap < 2 x SE'}") + twins_short_note(r)
    if read:
        return ('direction found: ' if r['pass'] else 'not found: ') + figs
    if pool == 'disc':
        return 'one test (league, information: the read is stage hold): ' + figs
    return f'one test (information: pool {pool} has no league, the league is pool disc; the read is stage hold): ' + figs


def one_test_block(r, days, rv, hot_spot):
    """The registry's one-test heldout block of a row of the read (research/registry.py validate: standard 'one-test',
    finite window_rate, random_rate, se, n, twins >= 0, gap = window_rate - random_rate within 1e-6; the registry
    recomputes pass as window_rate - random_rate >= 2 x se, and that recomputed verdict is the one it uses). So the block's
    rates are item 6's: window_rate = windows over instances and random_rate = the instance-weighted twin rate, both over
    the matches with an instance and a twin (gap_stats rate_weighted / random_weighted), whose difference IS the item 6
    cluster-weighted gap the row's own pass is judged on; the registry therefore judges by the amendment's gap and SE and
    agrees with the row by construction. They equal the pooled rates (windows / instances, twin windows / twins) whenever
    every instance drew TWINS twins and every match with an instance has a twin; the pooled rates, the twin shortfall and
    the match counts stand beside them as information (window_rate_pooled, random_rate_pooled, twins_short, matches,
    clustered; raw.one_test has them too). Without a contributing match (no z) the block carries the pooled rates, their
    difference and se 0, which the registry's one_test_pass refuses as the row's own verdict does."""
    pooled_rate = r['rate'] if finite(r['rate']) else 0.0
    pooled_random = r['random'] if finite(r['random']) else 0.0
    if finite(r.get('gap')) and finite(r.get('rate_weighted')) and finite(r.get('random_weighted')):
        rate, random, gap = r['rate_weighted'], r['random_weighted'], r['gap']
    else:
        rate, random, gap = pooled_rate, pooled_random, pooled_rate - pooled_random
    se = r['se'] if finite(r['se']) else 0.0
    h = {'standard': 'one-test', 'tier': 'history', 'days': len(days), 'window_rate': rate, 'random_rate': random, 'gap': gap, 'se': se,
         'n': int(r['n']), 'twins': int(r['tn']), 'pass': bool(r['pass']), 'hot_spot': hot_spot, 'horizon': 'match',
         'rates': 'item 6: instance-weighted over the matches with a twin, so gap = window_rate - random_rate is the cluster-weighted gap',
         'window_rate_pooled': pooled_rate, 'random_rate_pooled': pooled_random, 'twins_short': int(r.get('twins_short') or 0),
         'matches': int(r['matches']), 'clustered': int(r['clustered'])}
    if rv is not None:
        h['replay_version'] = rv
    return h


def hold_batch_of(meta, plan=None, path=HOLD_BATCH_FILE):
    """Stage hold's batch (Amendment 4 item 7) -> {batch, source, league_run, hash, league_pool} or {problem}: the shard
    metas' batch (the sweep stores the validated batch there with batchHash and leagueRun), else the plan's, else the
    checkout's research/tennis-ta/hold-batch.json; None when there is none (a hold run of the retired frozen-list design).
    league_pool = the pool of the league the batch was read off when the source states it (meta / plan leaguePool, the
    file's league_pool; None otherwise: the sweep's batch file admits league_run and batch only), checked by
    hold_batch_problems (item 7: the league runs on pool disc only)."""
    for src, m in (('the shard metas (meta.batch)', meta or {}), ('the plan', plan or {})):
        if isinstance(m, dict) and m.get('batch') is not None:
            return {'batch': m['batch'], 'source': src, 'league_run': m.get('leagueRun'), 'hash': m.get('batchHash'), 'league_pool': m.get('leaguePool')}
    if os.path.exists(path):
        try:
            with open(path, 'rb') as fh:
                buf = fh.read()
            raw = json.loads(buf)
        except (OSError, ValueError) as e:
            return {'problem': f'{path}: unreadable ({e})'}
        if not isinstance(raw, dict):
            return {'problem': f'{path}: not a JSON object {{league_run, batch}}'}
        return {'batch': raw.get('batch'), 'source': path, 'league_run': raw.get('league_run'), 'hash': hashlib.sha256(buf).hexdigest(),
                'league_pool': raw.get('league_pool')}
    return None


def hold_batch_problems(batch, runs, wd, league_pool=None):
    """A hold run's batch against its runs and 'window' rows (empty = sound): at most HOLD_BATCH_MAX members {id, leg}, the
    id a config without an arm and never a measuring stick (item 1: a hot spot is a config of the gradient matrix; C4: a
    stick is never screened or counted), the leg underdog / fav / both, no (id, leg) twice, each config's |window run
    (window: true, with both legs' rows in the window block) and |F1 run present; a league pool the source states must
    be 'disc' (item 7: the league runs on H-DEV only)."""
    p = []
    if league_pool is not None and str(league_pool) != 'disc':
        p.append(f"the batch was read off a pool {league_pool} league: the league runs on H-DEV (pool disc) only (item 7)")
    if not isinstance(batch, list):
        return p + ['the batch is not a list of {id, leg}']
    if not batch:
        p.append('the batch is empty: the read needs at least one hot spot')
    if len(batch) > HOLD_BATCH_MAX:
        p.append(f'the batch names {len(batch)} hot spots: at most {HOLD_BATCH_MAX} (the {HOLD_BATCH_MAX} hottest family A hot spots by z on the league)')
    seen = set()
    for i, m in enumerate(batch):
        at = f'batch[{i}]'
        if not isinstance(m, dict) or not isinstance(m.get('id'), str) or m.get('leg') not in HOLD_LEGS:
            p.append(f'{at}: not {{id: <config without its arm>, leg: underdog | fav | both}}: {json.dumps(m)[:120]}')
            continue
        cid, leg = m['id'], m['leg']
        if cid.rpartition('|')[2] in ARMS:
            p.append(f'{at}: {cid} ends with an arm: a hot spot is a config and a leg')
            continue
        if STICK_ID.match(cid) or (runs.get(f'{cid}|window') or {}).get('stick'):
            p.append(f'{at}: {cid} is a measuring stick: reported, never screened or counted (C4), never a hot spot of the batch (item 1: a '
                     f'config of the gradient matrix); the sticks stand in the league as information')
            continue
        if (cid, leg) in seen:
            p.append(f'{at}: {cid} / {leg} is listed twice')
        seen.add((cid, leg))
        wr = runs.get(f'{cid}|window')
        if wr is None or not wr.get('window'):
            p.append(f"{at}: {cid}: no {cid}|window run (window: true) in the shards: the read runs each batch config's |window and |F1 arms")
        elif wd is None or any((f'{cid}|window', lg) not in wd['rows'] for lg in ('underdog', 'fav')):
            p.append(f"{at}: {cid}: the window block has no rows for {cid}|window (both legs)")
        if f'{cid}|F1' not in runs:
            p.append(f'{at}: {cid}: no {cid}|F1 run in the shards (the production P&L reported beside the read)')
    return p


def league_csv_row(r):
    """One flat league.csv row."""
    h = r['hist']
    out = {'family': r['family'], 'rank': r.get('rank'), 'hot_spot': r['hot_spot'], 'id': r['id'], 'config': r['config'], 'leg': r.get('leg'),
           'stick': r['stick'], 'production': r.get('production'), 'n': r['n'], 'w': r['w'], 'tn': r['tn'], 'tw': r['tw'], 'rate': r['rate'],
           'random': r['random'], 'gap': r['gap'], 'se': r['se'], 'z': r['z'], 'pass': r['pass'], 'matches': r['matches'],
           'clustered': r['clustered'], 'twins_short': r.get('twins_short'), 'events_short': r.get('events_short'),
           'rate_weighted': r.get('rate_weighted'), 'random_weighted': r.get('random_weighted'), 'n_all': r['n_all'], 'mean_ask': r['mean_ask'],
           't_win_q1': h['tWin']['q1'], 't_win_median': h['tWin']['median'], 't_win_q3': h['tWin']['q3'],
           'len_win_median': h['lenWin']['median'], 'dip_median': h['dip']['median'], 'held_median': h['held']['median'],
           'end_no_window': r['end_no_window'], 'end_no_window_share': r['end_no_window_share']}
    for ph in PHASES:
        v = r['by_phase'].get(ph) or {'n': 0, 'w': 0, 'rate': None}
        out[f'{ph}_n'], out[f'{ph}_w'], out[f'{ph}_rate'] = v['n'], v['w'], v['rate']
    for t in ('ATP', 'WTA'):
        v = r['by_tour'][t]
        for k in ('n', 'w', 'tn', 'tw', 'gap', 'se', 'z'):
            out[f'{t}_{k}'] = v[k]
    c = r.get('coin') or {}
    for k in ('n', 'w', 'tn', 'tw', 'gap', 'se', 'z'):
        out[f'coin_{k}'] = c.get(k)
    for k in ('f1', 'f2'):
        v = r.get(k) or {}
        out[f'{k}_entries'], out[f'{k}_net'], out[f'{k}_per_entry'] = v.get('entries'), v.get('net'), v.get('per_entry')
    if r.get('by_fold'):
        for f, v in sorted(r['by_fold'].items()):
            out[f'fold{f}_gap'], out[f'fold{f}_n'] = v['gap'], v['n']
    return {k: ('' if v is None or (isinstance(v, float) and math.isnan(v)) else z_json(v) if isinstance(v, float) and math.isinf(v) else v)
            for k, v in out.items()}


def _zf(r, k='z'):
    """z for a table: '+inf' / '-inf' for an infinite z (SE 0 with a gap, gap_stats), '-' for none."""
    v = r.get(k)
    if isinstance(v, str):
        return v
    return '-' if v is None or math.isnan(v) else '+inf' if v == math.inf else '-inf' if v == -math.inf else f'{v:.2f}'


def _gf(v, spec='+.4f'):
    return '-' if v is None or (isinstance(v, float) and not math.isfinite(v)) else format(v, spec)


def league_md_row(r):
    """One league.md table row of a hot spot."""
    h = r['hist']
    ph = '/'.join(('-' if (r['by_phase'].get(p) or {}).get('rate') is None else f"{r['by_phase'][p]['rate']:.2f}") for p in PHASES)
    tours = ' | '.join(f"{_gf(r['by_tour'][t]['gap'])} ({_zf(r['by_tour'][t])}, n {int(r['by_tour'][t]['n'])})" for t in ('ATP', 'WTA'))
    c = r.get('coin')
    coin = f"{_gf(c['gap'])} ({_zf(c)})" if c else '-'
    pnl = ' | '.join('-' if not r.get(k) or r[k]['per_entry'] is None else f"{r[k]['per_entry']:+.4f} ({r[k]['entries']})" for k in ('f1', 'f2'))
    tag = ' (stick)' if r['stick'] else ' (production)' if r.get('production') else ''
    return (f"| {r.get('rank', '-')} | {md(r['config'])}{tag} | {r.get('leg') or '-'} | {int(r['n'])} | {int(r['w'])} | {_gf(r['rate'], '.3f')} | "
            f"{int(r['tn'])} | {int(r['tw'])} | {int(r.get('twins_short') or 0)} | {_gf(r['random'], '.3f')} | {_gf(r['gap'])} | {_gf(r['se'], '.4f')} | {_zf(r)} | "
            f"{'yes' if r['pass'] else '-' if r['z'] is None else 'no'} | {r['matches']} ({r['clustered']}) | "
            f"{h['tWin']['q1'] or '-'} / {h['tWin']['median'] or '-'} / {h['tWin']['q3'] or '-'} | {h['lenWin']['median'] or '-'} | "
            f"{h['dip']['median'] or '-'} | {h['held']['median'] or '-'} | {_gf(r['end_no_window_share'], '.2f')} | {ph} | {tours} | {coin} | {pnl} |")


LEAGUE_HEAD = ('| rank | hot spot | leg | n | windows | rate | twins | twin windows | twins short | random | gap | SE | z | gap >= 2 SE | '
               'matches (clustered) | to window q1 / med / q3 (min) | window length (med, min) | dip (med, $) | held (med, min) | end rule, no window | '
               'pre/e20/p1/p2/p3 rate | ATP gap (z, n) | WTA gap (z, n) | coin gap (z) | F1 $/entry (n) | F2 $/entry (n) |')
LEAGUE_SEP = '|' + '---|' * 27


def render_league(s, league_a, league_b, cand, wd, pool_txt):
    """league.md: the one test's league of a disc run (item 7) and the batch a person copies for the read."""
    L = [f"## The one test's league (Amendment 4), run {s['run']}, pool {pool_txt} (H-DEV), stage {s['stage']}"]
    L.append(f"Rule: {ONE_TEST_RULE}. The league ranks hot spots by z, ties by gap; a hot spot without a z ranks last. Every other column "
             f"is information (item 8): nothing in it cuts a hot spot. Window block {wd.get('version')}, settle fraction {wd.get('settleFrac')}, "
             f"order ${wd.get('orderUsd')}, {wd.get('twins')} twins an instance, seed {wd.get('seed')}; {s['matches']} scored {pool_txt} matches "
             f"(the window block's events in the pool); histograms, phases, the end-rule share and the mean ask are over every instance the "
             f"arm recorded in the slices (n_all in league.csv), the counts and the test over the pool's matches. 'twins short' = the twins "
             f"the instances drew short of {TWINS} each (item 5: a coin side with no eligible minute draws none; information): when it is not 0, "
             f"the pooled rate - random is not the gap, which is item 6's cluster-weighted one (rate_weighted - random_weighted in league.csv). "
             f"The F1 / F2 columns are the config's production exits' after-fee P&L per entry over the pool (information). Every row is in "
             f"league.csv and league.json.")
    n_z = sum(1 for r in league_a if r['z'] is not None)
    L.append('')
    L.append(f"### Family A: {len(league_a)} hot spots ({len({r['config'] for r in league_a})} configs x legs), {n_z} with a z, "
             f"{sum(1 for r in league_a if r['pass'])} with gap >= 2 x SE; the top {LEAGUE_TOP} by z, then the production default config's legs "
             f"and the measuring sticks")
    L.append(LEAGUE_HEAD)
    L.append(LEAGUE_SEP)
    shown = set()
    for r in league_a[:LEAGUE_TOP]:
        L.append(league_md_row(r))
        shown.add(id(r))
    extra = [r for r in league_a if id(r) not in shown and (r.get('production') or r['stick'])]
    if extra:
        L.append(LEAGUE_SEP.replace('---', '...'))
        for r in extra:
            L.append(league_md_row(r))
    if not league_a:
        L.append('| - | no family A window row | | | | | | | | | | | | | | | | | | | | | | | | |')
    L.append('')
    if league_b:
        L.append(f"### Family B: {len(league_b)} hot spots (reading x bar x direction, SignalStudy's event sample), its own table; "
                 f"{sum(1 for r in league_b if r['z'] is not None)} with a z, {sum(1 for r in league_b if r['pass'])} with gap >= 2 x SE. "
                 f"Family B hot spots are not read on H-HOLD in this amendment.")
        L.append(LEAGUE_HEAD)
        L.append(LEAGUE_SEP)
        for r in league_b[:LEAGUE_TOP]:
            L.append(league_md_row(r))
        L.append('')
    else:
        L.append('### Family B: no familyBWindow rows in the shards (family B not run, or an older export).')
        L.append('')
    L.append('### The batch for the read (item 7)')
    L.append(f"hold-batch-candidate.json beside this file holds the {HOLD_BATCH_MAX} hottest family A hot spots by z (ties by gap), as "
             f"research/tennis-ta/hold-batch.json takes them, with this league's run id (league_run {s['run']}; measuring sticks are never "
             f"in it: a hot spot is a config of the gradient matrix, item 1, and a stick is reported, never screened or counted, C4): "
             + (', '.join(f"{m['id']} / {m['leg']}" for m in cand['batch']) if cand['batch'] else 'none (no hot spot has a z)') + '.')
    L.append(f"A person copies it to research/tennis-ta/hold-batch.json with the league run id, lists it in the registry and in the project "
             f"calendar ({CALENDAR}), and only then commits the hold request (stage hold, pool hold: one run on H-HOLD, refused by prep when "
             f"the batch hash is already in the openings ledger). A hot spot that passes on the read is 'direction found' for tennis.")
    return L


def render_hold_league(s, members, league_a, hold_score, ho1, f1_folds, h_hold, batch):
    """hold-league.md: the read's result per batch member (the one test on the hold pool), then information: the six folds,
    both tours, the item 8 columns, the coin placebo and the HO-1 money table."""
    L = [f"## The one read (Amendment 4 item 7): stage hold, run {s['run']}, batch {batch.get('hash') or '-'} off league run "
         f"{batch.get('league_run') or '-'} ({batch.get('source')})"]
    L.append(f"The one test on the hold pool (H-HOLD, {h_hold[0]} to {h_hold[1]}, {s['matches']} matches with a tape): PASS = gap >= 2 x SE, "
             f"clustered by match (item 6). A pass is 'direction found' for tennis; nothing else below judges a hot spot. Rule: {ONE_TEST_RULE}.")
    L.append('')
    L.append(f"'twins short' = the twins a member's instances drew short of {TWINS} each (item 5; information): when it is not 0 the pooled "
             f"rate - random is not the gap (item 6's cluster-weighted one), and the member's registry block carries item 6's weighted rates, "
             f"whose difference is that gap, so the registry's recomputed verdict is the one here.")
    L.append('| hot spot | leg | n | windows | rate | twins | twin windows | twins short | random | gap | SE | z | result |')
    L.append('|---|---|---|---|---|---|---|---|---|---|---|---|---|')
    for m in members:
        r = m['row']
        res = 'DIRECTION FOUND (gap >= 2 x SE)' if r['pass'] else ('no z: ' + no_z_why(r) if r['z'] is None else 'not found (gap < 2 x SE)')
        L.append(f"| {md(r['config'])} | {r['leg']} | {int(r['n'])} | {int(r['w'])} | {_gf(r['rate'], '.3f')} | {int(r['tn'])} | {int(r['tw'])} | "
                 f"{int(r.get('twins_short') or 0)} | {_gf(r['random'], '.3f')} | {_gf(r['gap'])} | {_gf(r['se'], '.4f')} | {_zf(r)} | {res} |")
    if not members:
        L.append('| - | no batch member scored | | | | | | | | | | | |')
    L.append('')
    L.append('### Information (item 8, nothing judged): the six 16-day HO-1 folds, gap (n instances / tn twins) per fold')
    L.append('| hot spot | leg | ' + ' | '.join(f'fold {k} ({f["from"]} to {f["to"]})' for k, f in enumerate(s['ho1_folds'], 1)) + ' |')
    L.append('|' + '---|' * (2 + len(s['ho1_folds'])))
    for m in members:
        r = m['row']
        L.append(f"| {md(r['config'])} | {r['leg']} | " + ' | '.join(f"{_gf(v['gap'])} ({int(v['n'])} / {int(v['tn'])})" for _, v in sorted((r.get('by_fold') or {}).items())) + ' |')
    L.append('')
    L.append('### Both tours (information): gap (z, n)')
    L.append('| hot spot | leg | ATP | WTA |')
    L.append('|---|---|---|---|')
    for m in members:
        r = m['row']
        L.append(f"| {md(r['config'])} | {r['leg']} | " + ' | '.join(f"{_gf(r['by_tour'][t]['gap'])} ({_zf(r['by_tour'][t])}, n {int(r['by_tour'][t]['n'])})" for t in ('ATP', 'WTA')) + ' |')
    L.append('')
    L.append('### Minutes to the window, window length, dip, minutes held, the end rule, the phases, the coin placebo, the production exits (information)')
    L.append(LEAGUE_HEAD.replace('| rank |', '| |'))
    L.append(LEAGUE_SEP)
    for m in members:
        L.append(league_md_row(dict(m['row'], rank='-')))
    other = [r for r in league_a if (r['config'], r['leg']) not in {(m['row']['config'], m['row']['leg']) for m in members}]
    if other:
        L.append('')
        L.append(f"The batch configs' other legs (information, not read; no registry row): " + '; '.join(
            f"{r['config']} / {r['leg']}: gap {_gf(r['gap'])}, SE {_gf(r['se'], '.4f')}, z {_zf(r)}, n {int(r['n'])}" for r in other) + '.')
    L.append('')
    L.append('### The HO-1 money table (information): the production exits of each batch config on H-HOLD, after fees')
    if hold_score and hold_score.get('candidates'):
        L.append(f"Paired against the production control {hold_score['control']} (in the batch): gain by fold as $/h over 24 h a day, folds won, "
                 f"the tours per live-match hour, the registry's HO-1 block (ho1_fill / ho1_pass) beside it. Nothing here judges a hot spot.")
        nf = len(s['ho1_folds'])
        L.append('| F1 arm | gain | $/h | ' + ' | '.join(f'fold {k + 1} $/h' for k in range(nf)) + ' | folds won | worst fold $/h | ATP $/live h | WTA $/live h | HO-1 (information) |')
        L.append('|' + '---|' * (8 + nf))
        for c in hold_score['candidates']:
            ho = c.get('ho1')
            ho_txt = ('pass' if ho['pass'] else f"fail: {ho['why']}") if ho else 'no registry block'
            L.append(f"| {md(c['arm'])} | {usd(c['gain'])} | {f4(c['gain_per_hour'])} | " + ' | '.join(f4(f['gain_per_hour']) for f in c['folds'])
                     + f" | {c['folds_won']}/{sum(1 for f in c['folds'] if f['days'])} | {f4(c['worst_fold_per_hour'])} | "
                     f"{f4(c['tours']['ATP']['gain_per_live_hour'])} | {f4(c['tours']['WTA']['gain_per_live_hour'])} | {md(ho_txt)} |")
    else:
        L.append("No production control in the batch (the read runs the batch configs' |window and |F1 arms only), so no paired HO-1 gain: "
                 "each F1 arm's own net by fold ($ after fees, and $/h over 24 h a day) and the registry's HO-1 block when it has one.")
    nf = len(s['ho1_folds'])
    L.append('')
    L.append('| F1 arm | net | entries | ' + ' | '.join(f'fold {k + 1} net ($/h)' for k in range(nf)) + ' | ATP net | WTA net | registry HO-1 block |')
    L.append('|' + '---|' * (6 + nf))
    for m in members:
        f = f1_folds.get(m['row']['config'])
        if not f:
            L.append(f"| {md(m['row']['config'] + '|F1')} | no F1 run | | " + ' | '.join('-' for _ in range(nf)) + ' | - | - | - |')
            continue
        ho = ho1.get(f['arm'])
        ho_txt = (f"{ho['heldout'].get('days')} days, {ho['heldout'].get('folds_won')}/{ho['heldout'].get('folds')} folds won, worst "
                  f"{f4(ho['heldout'].get('worst_fold_per_hour'))} $/h: ho1_pass {'PASS' if ho['pass'] else 'FAIL (' + ho['why'] + ')'}") if ho and ho.get('heldout') else 'none'
        L.append(f"| {md(f['arm'])} | {usd(f['net'])} | {f['entries']} | " + ' | '.join(f"{usd(x['net'])} ({f4(x['per_hour'])})" for x in f['folds'])
                 + f" | {usd(f['tours']['ATP'])} | {usd(f['tours']['WTA'])} | {md(ho_txt)} |")
    return L


def write_one_test_files(out, s, league_a, league_b, members, wd, pools, hold_run, batch, hold_score, h_hold, run_id, run_days, run_tour,
                         cells, by_id, day_set, fold_edges, ho1, reg_rows):
    """A disc run: league.md, league.csv, league.json and hold-batch-candidate.json (item 7: the league runs on H-DEV, pool
    disc, only; another scored pool's one test is information in summary.json and the registry rows, with no league file and
    no candidate). A hold run with a batch: hold-league.md and hold-league.json (the read's result per member, then
    information)."""
    pool_txt = ','.join(pools)
    consts = {k: wd.get(k) for k in ('version', 'settleFrac', 'orderUsd', 'twins', 'seed')}
    if not hold_run:
        if pools != ['disc']:
            return
        cand = batch_candidate(league_a, run_id)
        with open(os.path.join(out, 'hold-batch-candidate.json'), 'w') as fh:
            fh.write(json.dumps(cand, indent=2) + '\n')
        with open(os.path.join(out, 'league.json'), 'w') as fh:
            fh.write(dumps({'version': 'tennis-ta-league/1', 'run': str(run_id), 'pool': pool_txt, 'stage': s['stage'], 'window': consts,
                            'events': len(wd['events']), 'events_scored': s['one_test']['events_scored'], 'matches': s['matches'], 'rule': ONE_TEST_RULE,
                            'ranking': 'by z = gap / SE, ties by gap; rows without a z last', 'A': spell_inf(league_a), 'B': spell_inf(league_b),
                            'batch_candidate': cand}))
        import csv
        flat = [league_csv_row(r) for r in league_a + league_b]
        cols = []
        for r in flat:
            for k in r:
                if k not in cols:
                    cols.append(k)
        with open(os.path.join(out, 'league.csv'), 'w', newline='') as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            for r in flat:
                w.writerow(r)
        with open(os.path.join(out, 'league.md'), 'w') as fh:
            fh.write('\n'.join(render_league(s, league_a, league_b, cand, wd, pool_txt)) + '\n')
        return
    f1_folds = {}
    fold_days = [[d for d in day_set if ho1_fold_of(d, fold_edges) == k + 1] for k in range(len(fold_edges))]
    for m in members:
        rid = f"{m['id']}|F1"
        if rid not in run_days:
            continue
        rd = run_days[rid]
        i = by_id.get((m['id'], 'F1', 'all', 'all', 'all'))
        if i is None:
            i = by_id.get((rid, 'stick', 'all', 'all', 'all'))
        f1_folds[m['id']] = {'arm': rid, 'net': sum(rd.values()), 'entries': cells[i]['entries'] if i is not None else None,
                             'folds': [{'fold': k + 1, 'days': len(fd), 'net': sum(rd.get(d, 0.0) for d in fd),
                                        'per_hour': (sum(rd.get(d, 0.0) for d in fd) / (24.0 * len(fd))) if fd else None} for k, fd in enumerate(fold_days)],
                             'tours': run_tour[rid]}
    reg_by_arm = {r['arm']: r for r in (reg_rows or [])}
    with open(os.path.join(out, 'hold-league.json'), 'w') as fh:
        fh.write(dumps(spell_inf({'version': 'tennis-ta-league/1', 'run': str(run_id), 'pool': pool_txt, 'stage': s['stage'], 'window': consts, 'rule': ONE_TEST_RULE,
                        'batch': {k: batch.get(k) for k in ('source', 'league_run', 'hash')}, 'h_hold': list(h_hold), 'folds': s['ho1_folds'],
                        'members': [dict(m['row'], verdict=m['verdict'], direction_found=bool(m['row']['pass']), f1_money=f1_folds.get(m['id']),
                                         registry=(reg_by_arm.get(f"{m['id']}|window|{m['leg']}") or {}).get('heldout')) for m in members],
                        'other_legs': [r for r in league_a if (r['config'], r['leg']) not in {(m['id'], m['leg']) for m in members}],
                        'ho1_money': hold_score})))
    with open(os.path.join(out, 'hold-league.md'), 'w') as fh:
        fh.write('\n'.join(render_hold_league(s, members, league_a, hold_score, ho1, f1_folds, h_hold, batch)) + '\n')


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description='Tennis TA trial report: scores families A and B from a checked shard set.')
    ap.add_argument('--shards', required=True, help='directory of the shard files (gzip JSON)')
    ap.add_argument('--pool', default='disc', help="the pool to score: 'disc' (H-DEV), 'old' (stratum H0) at stage 2, or 'hold' (H-HOLD) at "
                                                   "stage 'hold'; it must be the shards' pool")
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
    ap.add_argument('--registry-py', default=None,
                    help="the project's research/registry.py (make_id, validate): required to write the registry rows (C7)")
    ap.add_argument('--sha', default=None, help='code_sha of the rows: the commit the run swept and scored ($GITHUB_SHA; default: that env var)')
    ap.add_argument('--report-sha', default=None,
                    help='the commit whose scoring code runs, when it is not the sweep\'s (a rescore, .github/workflows/tennis-ta-rescore.yml): '
                         'the rows keep code_sha = --sha (the code that produced the trades) and carry raw.report_sha')
    ap.add_argument('--ref', default=None, help=f'the rows\' ref (default: {DRIVE_RUNS}/<run>)')
    ap.add_argument('--no-registry', action='store_true', help='local runs only: score and report without writing registry rows')
    ap.add_argument('--hold-batch', default=HOLD_BATCH_FILE,
                    help="stage hold: the batch file read when the shard metas and the plan carry no batch (default research/tennis-ta/hold-batch.json "
                         "of the checkout, as the sweep stores it)")
    ap.add_argument('--live-median-hours', default=None,
                    help="live-match hours a match stands in for when its pool has no published start at all (H0): a number, "
                         "SERIES=HOURS,... or a start-era run's summary.json (its live_median_hours); without it such a pool's "
                         "$/live-hour figures are refused (n/a, stated in report.md)")
    return ap.parse_args(argv)


def load_registry(path):
    """The project's registry module (research/registry.py, another thread's code) from a file: make_id and validate."""
    try:
        spec = importlib.util.spec_from_file_location('tennis_ta_registry_v1', path)
        if spec is None or spec.loader is None:
            raise ImportError('not a Python file')
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except Exception as e:  # noqa: BLE001 - any failure to load is the same refusal
        sys.exit(f'--registry-py {path}: cannot load it ({type(e).__name__}: {str(e)[:200]}): nothing is scored and no registry rows are written')
    for fn in ('make_id', 'validate'):
        if not callable(getattr(mod, fn, None)):
            sys.exit(f'--registry-py {path}: it has no {fn}(): nothing is scored and no registry rows are written')
    return mod


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
    pools = [p.strip() for p in a.pool.split(',') if p.strip()]
    refused = pool_refusal(pools)
    if refused:
        sys.exit(f'--pool {a.pool}: {refused}: nothing is scored and no registry rows are written')
    reg = load_registry(a.registry_py) if a.registry_py else None
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
    era = era_of(meta.get('era') or (plan or {}).get('era'))
    era_src = 'the shard metas' if meta.get('era') else 'the plan' if (plan or {}).get('era') else "the report's copy of the sweep's constants"
    stratum_label = stratum_label_of(stratum, pools)
    refused = pool_refusal(pools, stage, meta.get('pool'))
    if refused:
        sys.exit(f'--pool {a.pool}: {refused}: nothing is scored and no registry rows are written')
    hold_run = pools == ['hold']
    # H-HOLD as the registry defines it (its module's H_HOLD when loaded), and its HO-1 fold edges.
    h_hold = tuple(getattr(reg, 'H_HOLD', None) or HO1_HOLD) if reg is not None else HO1_HOLD
    fold_edges = ho1_fold_edges(h_hold)
    if hold_run:
        if reg is not None and not all(callable(getattr(reg, fn, None)) for fn in ('ho1_fill', 'ho1_pass')):
            sys.exit(f'--registry-py {a.registry_py}: it has no ho1_fill() / ho1_pass(): a hold run\'s rows need the registry\'s HO-1 '
                     f'heldout block: nothing is scored and no registry rows are written')
        if era['holdFrom'] != day_ms(h_hold[0]):
            sys.exit(f"the shards' HOLD_FROM ({day_of(era['holdFrom'])}) is not the registry's H-HOLD start ({h_hold[0]}): the pool "
                     f"'hold' would not be H-HOLD: nothing is scored and no registry rows are written")
    stated = (plan or {}).get('holdFolds') or meta.get('holdFolds')
    if stated is not None and [(str(f.get('from')), str(f.get('to'))) for f in stated] != fold_edges:
        theirs = ', '.join(f"{f.get('fold')}: {f.get('from')} to {f.get('to')}" for f in stated)
        ours = ', '.join(f'{i + 1}: {x} to {y}' for i, (x, y) in enumerate(fold_edges))
        sys.exit(f"the sweep's holdFolds ({theirs}) are not the registry's HO-1 folds ({ours}): nothing is scored and no registry rows "
                 f"are written")
    fold_bad = fold_problems(data['matches'], fold_edges)
    if fold_bad:
        for x in fold_bad[:20]:
            print(f'folds: {x}', file=sys.stderr)
        sys.exit(f"{len(fold_bad)} matchList fold(s) disagree with the registry's HO-1 fold edges ({', '.join(f'{i + 1}: {x} to {y}' for i, (x, y) in enumerate(fold_edges))}): "
                 f"nothing is scored and no registry rows are written")
    said = sorted({str(mt['stratumLabel']) for mt in metas if mt.get('stratumLabel')} - {stratum_label})
    if said:
        sys.exit(f"the shards say stratum {', '.join(said)} but stratum {stratum} on pool {','.join(pools)} is {stratum_label} "
                 f"(the sweep's stratumLabelOf): the registry family would be wrong: nothing is scored and no registry rows are written")
    try:
        live_given = parse_live_medians(a.live_median_hours)
    except (OSError, ValueError, TypeError, AttributeError) as e:
        sys.exit(f'--live-median-hours {a.live_median_hours}: {e}: nothing is scored and no registry rows are written')
    matches, runs, fam_b, wd = data['matches'], data['runs'], data['familyB'], data.get('window')
    batch = None
    if hold_run:
        # Amendment 4 item 7: the read runs the batch (the shard metas' batch, else the plan's, else the checkout's
        # research/tennis-ta/hold-batch.json); without one, the retired frozen-list design (C10) is checked as before.
        batch = hold_batch_of(meta, plan, a.hold_batch)
        if batch is not None and batch.get('problem'):
            sys.exit(f"stage hold: {batch['problem']}: nothing is scored and no registry rows are written")
        if batch is not None:
            hp = hold_batch_problems(batch['batch'], runs, wd, batch.get('league_pool'))
            if wd is None:
                hp.append("the shards carry no window block (C12): the read is the one test on the batch's |window arms")
            what = f"the hold batch ({batch['source']})"
        else:
            hp = hold_list_problems(runs, stratum)
            what = 'the frozen hold list (C10, validated like stage 2)'
        if hp:
            for x in hp[:40]:
                print(f'hold list: {x}', file=sys.stderr)
            sys.exit(f'{len(hp)} problem(s) with {what}: nothing is scored and no registry rows are written')
    if a.baseline and not any(not r['stick'] and r.get('placebo') != 'coin' and r.get('fill') == 'F1' and rid.rsplit('|', 1)[0] == a.baseline
                              for rid, r in runs.items()):
        sys.exit(f'--baseline {a.baseline}: no F1 config of that id in the shards (a config is a run id without its arm, e.g. A|s2|center): '
                 f'nothing is scored and no registry rows are written')
    rng = np.random.default_rng(a.seed)
    B = a.boot

    # ---- owned matches by pool (C6): only the requested pool is scored; 'nostart' (a start-era match without a published
    # start) and 'old' rows are excluded and counted here
    pool_matches = Counter(str(m.get('pool')) for m in matches)
    pool_units = defaultdict(set)
    for m in matches:
        pool_units[str(m.get('pool'))].add(m.get('unit'))
    by_pool = {p: {'matches': pool_matches[p], 'units': len(pool_units[p]), 'scored': p in pools}
               for p in sorted(pool_matches, key=lambda x: (POOL_NAMES.index(x) if x in POOL_NAMES else 99, x))}

    # ---- universe (family A): the pool's owned matches with a tape, in start order. A hold match on a UTC day after H-HOLD
    # (it starts in the two hours before the cutoff) is no H-HOLD match: left out and counted.
    in_pool = [i for i, m in enumerate(matches) if m.get('pool') in pools]
    hold_after = []
    if hold_run:
        hold_after = [i for i in in_pool if not (h_hold[0] <= str(matches[i].get('day')) <= h_hold[1])]
        in_pool = [i for i in in_pool if h_hold[0] <= str(matches[i].get('day')) <= h_hold[1]]
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
    if hold_run:
        # The HO-1 folds (the registry's edges) by each match's UTC day: H-HOLD's 6 consecutive folds, not months.
        folds = [str(i + 1) for i in range(len(fold_edges))]
        fidx = {f: i for i, f in enumerate(folds)}
        NF = len(folds)
        m_fold = np.array([ho1_fold_of(m['day'], fold_edges) - 1 for m in M])
    else:
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
        spans, spans_src = pool_spans_from_table(table, pools, set(swept_units), era, h_hold), 'the unit table'
    # Each span cut to the pool's window (C9: a unit straddling DEV_TO or HOLD_FROM gives each pool only its own part; the
    # embargo day and the matches straddling DEV_TO count in no pool's hours).
    win_lo, win_hi = pool_window(pools[0], era, h_hold)
    spans = clip_spans([s for s in spans if s['unit'] in unit_by_id and pools[0] in unit_pools(unit_by_id[s['unit']], era)], win_lo, win_hi)
    pool_hours = clipped_hours(spans, span_lo, span_hi)
    unclipped_hours = clipped_hours(spans, -1, 1 << 62)
    live_dur, live_medians, live_info = live_durations(M, live_given)
    live_hours = {t: (float(live_dur[univ[t]].sum()) if live_dur is not None else None) for t in tour_levels}
    no_start_pool = sum(1 for m in M if m.get('startPublished', True) is False)

    def per_hour(net, hours):
        return net / hours if hours else None

    W = stationary_weights(U, B, a.block, rng)

    # ---- family A cells
    cells = []          # summary rows
    unit_sums = []      # per cell, U
    day_sums = []       # per cell, days
    vec_store = {}      # cell index -> per-match vector (F1 cells with enough entries, for ONC / SPA)
    hourly = []
    run_info = {}       # run id -> config, arm, distinct markets traded in the pool
    match_net = {}      # run id -> per-match net over the scored matches (the all/all/all cell's vector)
    config_br = defaultdict(lambda: defaultdict(int))
    warn = 0
    for rid in sorted(runs):
        r = runs[rid]
        if r.get('window'):
            continue  # a window arm trades nothing (Amendment 4): its instances are the one test's, below, never P&L cells
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
        e_k = ep['k'][km] if 'k' in ep and len(ep['k']) == len(km) else np.zeros(len(e_m), dtype=np.int64)
        run_info[rid] = {'config': config, 'arm': arm, 'markets': len(set(zip(e_m.tolist(), e_k.tolist())))}
        e_pnl, e_ph, e_br = ep['pnl'][km], ep['ph'][km], ep['br'][km]
        e_bk = buckets_of(ep['px'][km])
        e_hour = eastern_hours(ep['t'][km] + 1000.0 * ep['hold'][km])
        e_tour = m_tour[e_m] if len(e_m) else np.zeros(0, dtype='<U3')
        config_br[config][arm] += int((e_br > 0).sum())
        ep_tot = np.bincount(e_m, weights=e_pnl, minlength=N) if len(e_m) else np.zeros(N)
        match_net[rid] = ep_tot
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
    n_eff, medoids, best_in, n_distinct, onc_labels = 0, [], [], 0, {}
    cl_series = []  # the N_eff cluster-mean per-match series (for SR0)
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
            cl_series.append(Xraw[idx].mean(axis=0))
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

    # ---- DSR at N_eff; SR0's variance across the N_eff cluster-mean series, per tour universe
    sr0, v_sr, cluster_srs = sr0_by_universe(cl_series, univ, n_eff)

    def dsr(sr, skew, kurt, T_, sr_0):
        den_ = 1 - skew * sr + (kurt - 1) / 4 * sr * sr
        return norm_cdf((sr - sr_0) * math.sqrt(max(T_ - 1, 1)) / math.sqrt(den_)) if den_ > 0 else None
    for i in set(spa_set) | set(prod):
        c = cells[i]
        c['sr'] = c['mean'] / c['sd'] if c['sd'] > 0 else 0.0
        c['sr0'] = sr0[c['tour']]
        c['dsr'] = dsr(c['sr'], c['skew'], c['kurt'], c['universe'], c['sr0'])

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
    sens['scope'] = (f"each config's F1 all/all/all cell (every tour, phase and price bucket, {N} scored {','.join(pools)} matches, "
                     f"stratum {stratum_label}, this run's {len(allc)} F1 configs only); F2, coin and stick arms and the tour / phase / "
                     f"bucket cells are not ranked; R-only knobs are reported as leads, never ranked; A2 is chosen only from stage 2 "
                     f"on H-DISC")
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
    day_fold = (lambda d: (lambda f: None if f is None else f - 1)(ho1_fold_of(d, fold_edges))) if hold_run else None
    fb_rows, fb_sum = score_family_b(fam_b, uidx, unit_by_id, fidx, W, a.alpha, pool_hours, live_hours['all'], day_fold) if fam_b else ([], None)

    # ---- per-run daily and per-tour nets over the scored matches (the registry rows and the hold score)
    run_days = {rid: dict(zip(days, (float(x) for x in np.bincount(m_day, weights=v, minlength=len(days))))) for rid, v in match_net.items()}
    tour_hours = {t: (float(live_dur[m_tour == t].sum()) if live_dur is not None else 0.0) for t in ('ATP', 'WTA')}
    run_tour = {rid: {t: float(v[m_tour == t].sum()) for t in ('ATP', 'WTA')} for rid, v in match_net.items()}
    configs_arms = defaultdict(dict)
    for rid, info in run_info.items():
        if info['arm'] != 'stick':
            configs_arms[info['config']][info['arm']] = rid
    prod_rid = configs_arms.get(prod_cfg, {}).get('F1') if prod_cfg else None

    # ---- registry rows (C7 / C11: registry v1, one row per config x arm of family A and per reading x exit of family B)
    from_d, to_d = min(m['day'] for m in M), max(m['day'] for m in M)
    days_eastern = [fmt_eastern(M[0]['start'], '%Y-%m-%d %H:%M'), fmt_eastern(t_last, '%Y-%m-%d %H:%M')]
    n_raw_a, n_raw_b = nC, len(fb_rows)
    gate = 'stage1-screen' if stage == '1' else 'ho1-hold' if hold_run else f'stage{stage}'
    if hold_run:
        # Every H-HOLD day the swept units reach (C11: by_day over every hold day, 0 on a day without a trade), so the
        # registry's ho1_fill counts all 96 days and cuts its 6 folds from them.
        swept_iv = [(unit_by_id[u]['start'], unit_by_id[u]['end']) for u in swept_units if u in unit_by_id]
        day_set = [d for d in hold_days(h_hold) if any(s_ < day_ms(d) + DAY_MS and e_ > day_ms(d) for s_, e_ in swept_iv)]
    else:
        # Every UTC match day of the pool's matches (with a tape or not) and every family B day.
        day_set = sorted({matches[i]['day'] for i in in_pool} | {d for c in b_cells for d in c['days']})
    hold_score = hold_scoring(cells, by_id, run_days, run_tour, tour_hours, configs_arms, prod_rid, day_set, fold_edges) if hold_run and prod_rid else None

    # ---- the one test (Amendment 4): every hot spot's gap, SE and z over the scored pool's matches (items 6 and 8); the
    # league (item 7) on a disc run, the read's result per batch member on a hold run
    league_a, league_b, members, one_test = [], [], [], {'run': False}
    if wd is not None:
        scored = {matches[i].get('event') for i in in_pool}
        w_idx = [i for i, e in enumerate(wd['events']) if e.get('event') in scored]
        fold_of = (lambda d: ho1_fold_of(d, fold_edges)) if hold_run else None
        league_a = league_table(wd, w_idx, runs, cells, by_id, fold_of)
        for r_ in league_a:
            r_['production'] = prod_cfg is not None and r_['config'] == prod_cfg
        league_b = league_table_b(wd, w_idx, fold_of)
        one_test = {'run': True, 'version': wd.get('version'), 'events': len(wd['events']), 'events_scored': len(w_idx), 'rows_a': len(league_a),
                    'rows_b': len(league_b), 'with_z': sum(1 for r_ in league_a if r_['z'] is not None), 'pass': sum(1 for r_ in league_a if r_['pass']),
                    'hottest': [r_['hot_spot'] for r_ in league_a[:3]], 'batch': None, 'rule': ONE_TEST_RULE,
                    # item 7: the league (and the batch candidate) runs on H-DEV only; pool old's one test is information
                    'league': pools == ['disc'], 'league_pool': 'disc',
                    'league_reason': None if pools == ['disc'] or hold_run else
                    f"the league runs on H-DEV (pool disc) only (item 7): pool {','.join(pools)}'s one test is information (no league files, no hold-batch-candidate.json)"}
        if hold_run and batch is not None:
            by_hs = {(r_['config'], r_['leg']): r_ for r_ in league_a}
            for m_ in batch['batch']:
                r_ = by_hs.get((m_['id'], m_['leg']))
                if r_ is not None:
                    members.append({'id': m_['id'], 'leg': m_['leg'], 'row': r_, 'verdict': one_test_verdict(r_, True)})
            one_test['batch'] = {'source': batch['source'], 'league_run': batch['league_run'], 'hash': batch['hash'],
                                 'members': [dict({k: m_['row'][k] for k in ('hot_spot', 'config', 'leg', 'n', 'w', 'tn', 'tw', 'rate', 'random', 'gap', 'se', 'z', 'pass',
                                                                              'twins_short', 'events_short', 'rate_weighted', 'random_weighted')},
                                                  verdict=m_['verdict'], direction_found=bool(m_['row']['pass'])) for m_ in members]}
    else:
        one_test['reason'] = ('the shards carry no window block (C12): no one test, no league'
                              + (' (an older sweep without window arms)' if not any(r_.get('window') for r_ in runs.values()) else ''))
    registry, reg_rows = None, None
    ho1, one_test_reg = {}, {}
    if a.no_registry:
        registry = {'written': False, 'reason': '--no-registry (a local run): no registry rows'}
    else:
        if reg is None:
            sys.exit('no --registry-py: the registry rows (C7) take their trial ids and checks from the project\'s research/registry.py '
                     '(make_id, validate), and none are invented here: nothing is written (pass --no-registry for a local run without rows)')
        sha = a.sha or os.environ.get('GITHUB_SHA')
        if not sha:
            sys.exit('no --sha (and no GITHUB_SHA): the registry rows need the code_sha the run swept and scored: nothing is written')
        swept = str(meta.get('sha') or '')
        hexsha = lambda x: len(x) == 40 and all(ch in '0123456789abcdef' for ch in x.lower())  # noqa: E731
        if hexsha(swept) and hexsha(sha) and swept.lower() != sha.lower():
            sys.exit(f'--sha {sha} but the shards were swept at {swept}: the rows would carry the wrong code_sha: nothing is written')
        rv, rv_src, rv_err = replay_version_of(meta)
        if rv_err:
            sys.exit(f'{rv_err}: nothing is written')
        epoch = code_epoch(sim_version, rv)
        fam_a, fam_b_name = reg_families(stratum_label)
        ref = a.ref or f'{DRIVE_RUNS}/{run_id}'
        rec = stratum == 'R'
        reg_data = {'source': 'recorded' if rec else 'history', 'books': 'recorded' if rec else 'synthetic', 'days': day_set, 'doge': False,
                    'copy': str(data_version), 'engine': REG_ENGINE}
        if not rec:
            reg_data['replay_version'] = rv
        # C11: an H-DEV choice run (disc, and the H0 stress of stage 2 finalists) is dev-choice and reads no H-HOLD day; a hold
        # run carries no dev-choice flag.
        reg_flags = [] if hold_run else [DEV_FLAG] + (['H0-stress'] if pools == ['old'] else [])
        base_name = f'{REG_BASE}@{sha}'
        base_defaults = shared_base_defaults([runs[rid]['overrides'] for rid in sorted(runs)])
        ts = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        common_raw = {'run': run_id, 'stage': stage, 'pool': ','.join(pools), 'stratum': stratum_label, 'sim_version': sim_version,
                      'evidence': meta.get('evidence'), 'days_utc': [from_d, to_d], 'days_eastern': days_eastern, 'doge_excluded': True}
        rescored_at = rescore_sha(a.report_sha, sha)
        if rescored_at:
            common_raw['report_sha'] = rescored_at
        a_runs = []
        for rid in sorted(runs):
            if runs[rid].get('window'):
                continue  # the one test's rows (w_runs) are built below
            info = run_info[rid]
            i = by_id[(info['config'], info['arm'], 'all', 'all', 'all')]
            c = cells[i]
            ch = hashlib.sha1(json.dumps({'overrides': c['overrides'], 'fill': c['fill'], 'placebo': c['placebo'], 'stick': c['arm'] == 'stick'},
                                         sort_keys=True).encode()).hexdigest()[:16]
            if c['arm'] == 'F1' and hold_run:
                # filled from the registry's HO-1 block after ho1_fill (candidates); the control is never scored
                verdict = 'HO-1 control (production, not scored)' if rid == prod_rid else 'HO-1 (pending)'
            elif c['arm'] == 'F1':
                verdict = 'flag' if c.get('flag') else 'no: ' + ', '.join(c.get('gates_failed') or [])
            else:
                verdict = {'stick': 'measuring stick (not screened)', 'coin': 'placebo (not screened)'}.get(c['arm'], 'neighbour (not screened)')
            raw = dict(common_raw, config=c['config'], arm=c['arm'], config_hash=ch, entries=c['entries'], matches=c['universe'],
                       net=round(c['net'], 6), mean_per_match=round(c['mean'], 6), usd_per_hour=c['usd_per_hour'],
                       usd_per_live_hour=c['usd_per_live_hour'], hourly_eastern=[round(float(x), 4) for x in hourly[i]],
                       gate='measuring stick (not screened)' if c['arm'] == 'stick' else gate, p_boot=c['p'], ci90=c['ci90'],
                       bh=c.get('bh'), p_placebo=c.get('p_placebo'), t_day=c['t_day'], breaches=c['breaches'],
                       config_breaches=c['config_breaches'], fold_share=c['fold_share'], dsr=c.get('dsr'), onc_cluster=onc_labels.get(i),
                       flagged_cells=sum(1 for j in f1 if cells[j]['config'] == c['config'] and cells[j]['flag']) if c['arm'] == 'F1' else None,
                       n_raw_cells=n_raw_a, n_eff=n_eff)
            ar = {'id': rid, 'config': info['config'], 'arm': info['arm'], 'overrides': runs[rid]['overrides'],
                  'production': info['arm'] == 'F1' and prod_cfg is not None and info['config'] == prod_cfg,
                  'by_day': run_days[rid], 'fills': c['entries'], 'markets': info['markets'], 'verdict': verdict, 'raw': raw}
            if hold_run:
                # C11: the project's stand-in for RV terciles on tennis (pending the meta plan): the tours over H-HOLD, each
                # with its hold matches' live-match hours.
                ar['by_tercile'] = {t: {'pnl': round(run_tour[rid][t], 6), 'hours': round(tour_hours[t], 6)} for t in ('ATP', 'WTA')}
            a_runs.append(ar)
        # Amendment 4 item 10: one row per hot spot of the league (arm '<config>|window|<leg>', the leg, by_day and by_tercile
        # of its gap, verdict = the one test's figures) and its coin placebo's row (placebo_for); on the read, rows of the
        # batch members only, each with the registry's one-test heldout block.
        w_runs = []
        if wd is not None:
            read_keys = {(m_['id'], m_['leg']) for m_ in members} if hold_run else None
            fin = lambda v: v if finite(v) else None  # noqa: E731

            def gap_or_0(v):
                return v if finite(v) else 0.0
            ot_keys = ('n', 'w', 'tn', 'tw', 'rate', 'random', 'gap', 'se', 'z', 'pass', 'matches', 'clustered', 'twins_short', 'events_short',
                       'rate_weighted', 'random_weighted', 'n_all')
            for r_ in league_a:
                if read_keys is not None and (r_['config'], r_['leg']) not in read_keys:
                    continue
                ov = runs[f"{r_['config']}|window"]['overrides']
                terc = {t: {'pnl': gap_or_0(v['gap']), 'hours': round(tour_hours[t], 6), 'gap': fin(v['gap']), 'se': fin(v['se']), 'z': v['z'],
                            'n': v['n'], 'w': v['w'], 'tn': v['tn'], 'tw': v['tw']} for t, v in r_['by_tour'].items()}
                raw = dict(common_raw, hot_spot=r_['hot_spot'], config=r_['config'], leg=r_['leg'], arm='window', stick=r_['stick'], rank=r_['rank'],
                           one_test={k: r_[k] for k in ot_keys}, by_fold=r_.get('by_fold'), hist=r_['hist'], by_phase=r_['by_phase'],
                           end_no_window=r_['end_no_window'], end_no_window_share=r_['end_no_window_share'], mean_ask=r_['mean_ask'],
                           coin=r_.get('coin'), f1=r_['f1'], f2=r_['f2'],
                           metric='window_gap: by_day and by_tercile.pnl hold the gap (window rate - random rate) of that day or tour, never $',
                           gate='one-test (the read)' if hold_run else 'league (information; the read is stage hold)' if pools == ['disc']
                           else f"one test (information: pool {','.join(pools)} has no league, item 7; the read is stage hold)")
                wr = {'id': f"{r_['config']}|window|{r_['leg']}", 'config': r_['config'], 'leg': r_['leg'], 'kind': 'window', 'overrides': ov,
                      'by_day': {d: v['gap'] for d, v in r_['by_day'].items() if finite(v['gap'])}, 'by_tercile': terc, 'fills': int(r_['n']),
                      'markets': int(r_['matches']), 'verdict': one_test_verdict(r_, hold_run, pools[0]), 'raw': raw,
                      'placebo_id': f"{r_['config']}|coinwindow|{r_['leg']}" if r_.get('coin') else None}
                if hold_run:
                    wr['heldout'] = one_test_block(r_, day_set, rv, r_['hot_spot'])
                w_runs.append(wr)
                c_ = r_.get('coin')
                if c_:
                    craw = dict(common_raw, hot_spot=r_['hot_spot'], config=r_['config'], leg=r_['leg'], arm='coinwindow', placebo='coin',
                                one_test={k: c_[k] for k in ot_keys}, metric='window_gap: by_day and by_tercile.pnl hold the gap, never $',
                                gate='coin placebo (information)')
                    w_runs.append({'id': wr['placebo_id'], 'config': r_['config'], 'leg': r_['leg'], 'kind': 'coinwindow',
                                   'overrides': (runs.get(f"{r_['config']}|coinwindow") or {}).get('overrides', ov),
                                   'by_day': {d: v['gap'] for d, v in c_['by_day'].items() if finite(v['gap'])},
                                   'by_tercile': {t: {'pnl': gap_or_0(v['gap']), 'hours': round(tour_hours[t], 6), 'gap': fin(v['gap']), 'se': fin(v['se']),
                                                      'z': v['z'], 'n': v['n'], 'w': v['w'], 'tn': v['tn'], 'tw': v['tw']} for t, v in c_['by_tour'].items()},
                                   'fills': int(c_['n']), 'markets': int(c_['matches']), 'placebo_for': wr['id'], 'raw': craw,
                                   'verdict': 'coin placebo of the one test (information): ' + one_test_verdict(c_).split(': ', 1)[1]})
        b_rules, b_notes = [], []
        if fam_b:
            fb_by_id = {r_['id']: r_ for r_ in fb_rows}
            rules = defaultdict(dict)
            for c in b_cells:
                rules[_rule_of(c)][_ctx_of(c)] = c
            for rule, ctxs in sorted(rules.items()):
                allc_b = ctxs.get('all')
                if allc_b is None:
                    b_notes.append(f'{rule}: no all-context cell in the export: no row')
                    continue
                sc = fb_by_id.get(allc_b['id'])
                if hold_run:
                    verdict = 'HO-1 (pending)'
                else:
                    verdict = ('flag' if sc['flag'] else 'no: ' + ', '.join(sc['gates_failed'])) if sc else 'no entries (placebo only)'
                raw = dict(common_raw, cell=allc_b['id'], entries=int(allc_b['n']), net=round(float(allc_b['sum']), 6),
                           mean_per_entry=round(sc['mean'], 6) if sc else None, p_boot=sc['p'] if sc else None, bh=sc['bh'] if sc else None,
                           z_placebo=sc['z_placebo'] if sc else None, placebo_diff=sc['placebo_diff'] if sc else None,
                           stress_net=sc['stress_net'] if sc else None, rule_breaches=sc['rule_breaches'] if sc else int(allc_b['breaches']),
                           usd_per_hour=sc['usd_per_hour'] if sc else None, gate=f'{gate}-B', design_size=fb_sum['design_size'],
                           flagged_contexts=sum(1 for x in ctxs.values() if fb_by_id.get(x['id'], {}).get('flag')), n_raw_cells=n_raw_b)
                placebo = None
                if fam_b.get('day_placebo'):
                    pn = int(sum(v[2] for v in allc_b['units'].values() if len(v) > 2))
                    placebo = {'by_day': {d: float(v[3]) for d, v in allc_b['days'].items()}, 'fills': pn,
                               'markets': int(allc_b['placeboMarkets']) if allc_b.get('has_markets') else None,
                               'raw': dict(common_raw, cell=allc_b['id'], placebo='circular shift (Amendment 3)', entries=pn,
                                           net=round(float(sum(v[3] for v in allc_b['units'].values() if len(v) > 3)), 6))}
                b_rules.append({'rule': rule, 'by_day': {d: float(v[1]) for d, v in allc_b['days'].items()},
                                'by_cell': {ctx: float(x['sum']) for ctx, x in ctxs.items() if ctx != 'all' and x['n'] > 0},
                                'fills': int(allc_b['n']), 'markets': int(allc_b['markets']) if allc_b.get('has_markets') else None,
                                'verdict': verdict, 'raw': raw, 'placebo': placebo})
            if not fam_b.get('day_placebo'):
                b_notes.append('family B placebo rows are not written: the export\'s day rows carry no placebo sums ([entries, net] only; '
                               'the per-unit placebo sums cannot give a by_day), so family B candidates have no control (G2:unpaired)')
            if hold_run:
                b_notes.append('family B rows carry no by_tercile (the export has no per-tour sums), so their HO-1 block cannot pass the '
                               'tercile test: family B is scored on H-HOLD for the record only')
        rows, problems, notes = registry_rows(reg.make_id, sha, day_set, pool_hours, reg_data, reg_flags, ref, epoch, ts, a_runs, b_rules,
                                              stratum, label=stratum_label, base=base_name, base_defaults=base_defaults, w_runs=w_runs)
        notes += b_notes
        if w_runs:
            notes.append(f"{len(w_runs)} one-test row(s) (Amendment 4 item 10: arm '<config>|window|<leg>' per hot spot and its coin placebo "
                         f"'<config>|coinwindow|<leg>' as placebo_for; data.metric window_gap: by_day and by_tercile hold the gap, never $, so the "
                         f"validator flags them G1:non-dollar-metric; data.regime_proxy tour)"
                         + (f"; the read's {sum(1 for x in w_runs if x.get('heldout'))} row(s) carry the registry's one-test heldout block"
                            if hold_run else '; no heldout block on a league run (the read is stage hold)'))
        if stratum_label != 'H':
            notes.append(f'stratum {stratum_label}: families {fam_a} / {fam_b_name}, apart from the start-era history families '
                         f'{REG_FAMILY_A} / {REG_FAMILY_B} (the strata are never pooled in a test, and the registry scores a family over '
                         f'the days its rows share)')
        if not hold_run:
            reads = [d for d in day_set if d >= h_hold[0]]
            if reads:
                problems.append(f'{len(reads)} by_day day(s) of this dev-choice run ({reads[0]} to {reads[-1]}) are in H-HOLD (from {h_hold[0]}): '
                                f'the registry would block the family (G0:dev-choice-reads-hold); a disc match closes before DEV_TO')
        else:
            if len(day_set) < len(hold_days(h_hold)):
                notes.append(f'the swept units reach {len(day_set)} of H-HOLD\'s {len(hold_days(h_hold))} days: HO-1 needs 90 held-out days')
            if hold_after:
                notes.append(f'{len(hold_after)} pool hold match(es) start on a UTC day after H-HOLD ({h_hold[1]}), in the hours before the '
                             f'cutoff: no H-HOLD match, left out of the score and the rows')
        notes.append(f"base {base_name}, base_defaults {json.dumps(base_defaults, sort_keys=True)} (the overrides every spec of the run "
                     f"shares that differ from production); data.replay_version {rv} ({rv_src}), data.engine {REG_ENGINE}")
        reg_rows = [json.loads(dumps(spell_inf(r))) for r in rows]  # an infinite z (SE 0 with a gap) spelt, not nulled
        ho1, one_test_reg = {}, {}
        if hold_run:
            # The registry's own HO-1 block (folds, terciles = tours, placebo, replay version) for every paired row; the read's
            # one-test rows keep their block (ho1_fill leaves standard 'one-test' as written) and the registry recomputes
            # their pass (one_test_pass): a difference from the row's own reading is its OT:declared-pass-differs flag.
            reg.ho1_fill(reg_rows)
            ct_of = getattr(reg, 'contract_type_of', lambda r: 'tennis')
            ot_pass = getattr(reg, 'one_test_pass', None)
            for r in reg_rows:
                if r.get('heldout') is None:
                    continue
                if r['heldout'].get('standard') == 'one-test':
                    ok, why = ot_pass(r['heldout']) if callable(ot_pass) else (None, 'the registry module has no one_test_pass')
                    one_test_reg[r['arm']] = {'pass': ok, 'why': why, 'declared': r['heldout'].get('pass'), 'heldout': r['heldout']}
                    continue
                ok, why = reg.ho1_pass(r['heldout'], ct_of(r), (r.get('data') or {}).get('engine'))
                ho1[r['arm']] = {'pass': bool(ok), 'why': why, 'heldout': r['heldout'], 'role': r['role'], 'family': r['family']}
                if r['role'] == 'candidate':
                    r['verdict'] = 'HO-1 pass' if ok else f'HO-1 fail: {why}'
            for r in reg_rows:
                if r.get('verdict') == 'HO-1 (pending)':
                    r['verdict'] = 'HO-1: no held-out block (no control to pair with)'
            reg_rows = [json.loads(dumps(r)) for r in reg_rows]
        vflags = Counter()
        for r in reg_rows:
            err, fl = reg.validate(r)
            if err:
                problems.append(f"{r.get('family')} {r.get('arm')}: {'; '.join(err)}")
            vflags.update(fl)
            if not hold_run and 'G0:dev-choice-reads-hold' in fl:
                problems.append(f"{r.get('family')} {r.get('arm')}: the validator flags G0:dev-choice-reads-hold")
        if problems:
            for x in problems[:40]:
                print(f'registry: {x}', file=sys.stderr)
            sys.exit(f'{len(problems)} problem(s) with the registry rows (research/registry.py validate): nothing is written')
        for x in notes:
            print(f'registry note: {x}', file=sys.stderr)
        ctrl = next((r['trial_id'] for r in reg_rows if r['family'] == fam_a and r['role'] == 'control' and r['arm'].endswith('|F1')
                     and r['arm'].rsplit('|', 1)[0] == prod_cfg), None)
        if hold_score is not None:
            for hc in hold_score['candidates']:
                hc['ho1'] = ho1.get(hc['arm'])
                hc['registry_differs'] = registry_fold_differences(hc, (ho1.get(hc['arm']) or {}).get('heldout'))
        registry = {'written': True, 'file': f'registry-v1-{run_id}.jsonl', 'rows': len(reg_rows),
                    'families': dict(Counter(r['family'] for r in reg_rows)), 'roles': dict(Counter(r['role'] for r in reg_rows)),
                    'control': ctrl, 'control_arm': f'{prod_cfg}|F1' if ctrl else None, 'code_sha': sha, 'code_epoch': epoch,
                    'replay_version': rv, 'replay_version_source': rv_src, 'family_a': fam_a,
                    'family_b': fam_b_name, 'base': base_name, 'base_defaults': base_defaults,
                    'days': len(day_set), 'hours': pool_hours, 'flags': reg_flags, 'validator_flags': dict(vflags), 'notes': notes,
                    'b_placebo_rows': bool(fam_b and fam_b.get('day_placebo')), 'ref': ref,
                    'ho1': ({arm: {k: v for k, v in x.items() if k != 'heldout'} for arm, x in ho1.items()} if hold_run else None),
                    'one_test_rows': len(w_runs), 'one_test': (one_test_reg if hold_run else None)}

    # ---- outputs (only now: everything above was checked)
    os.makedirs(a.out, exist_ok=True)
    if reg_rows is not None:
        with open(os.path.join(a.out, registry['file']), 'w') as fh:
            for r in reg_rows:
                fh.write(json.dumps(spell_inf(r), sort_keys=True, allow_nan=False) + '\n')
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
    replay_skips = replay_skips_of(metas)
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
    k_range = None
    if onc_diag.get('k_hi'):
        k_range = {'from': 2, 'to': onc_diag['k_hi'], 'n': onc_diag.get('n'), 'cap': onc_diag.get('k_cap'),
                   'grid': f'every k to {ONC_DENSE_K}, a geometric grid above (steps of at most {ONC_K_RATIO - 1:.0%}), the gaps next '
                           f'to the {ONC_REFINE_TOP} best filled in until adjacent', 'scanned': onc_diag.get('scanned')}
    league_files = (['league.md', 'league.csv', 'league.json', 'hold-batch-candidate.json'] if one_test['run'] and one_test.get('league')
                    else ['hold-league.md', 'hold-league.json'] if one_test['run'] and hold_run and batch is not None else [])
    summary = dict(run=run_id, pools=pools, stage=stage, sim_version=sim_version, data_version=data_version, files=data['files'],
                   one_test=dict(one_test, files=league_files),
                   era={k: datetime.fromtimestamp(v / 1000, timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ') for k, v in era.items()},
                   era_source=era_src, era_rule=era_text(era, h_hold), stratum_label=stratum_label, by_pool=by_pool, hold_run=hold_run,
                   h_hold=list(h_hold), ho1_folds=[{'fold': i + 1, 'from': x, 'to': y} for i, (x, y) in enumerate(fold_edges)],
                   hold=hold_summary(hold_score, hold_after, meta, plan, run_id, runs) if hold_run else None,
                   excluded={p: v['matches'] for p, v in by_pool.items() if not v['scored']},
                   slicing=slicing, coverage=coverage, owned_matches=owned, owned_no_published_start=owned_no_start, replay_skips=replay_skips,
                   matches=N, no_tape=no_tape, pool_no_published_start=no_start_pool, units=U, days=len(days), folds=folds,
                   pool_hours=pool_hours, pool_hours_unclipped=unclipped_hours, pool_hours_source=spans_src, data_span=[day_of(span_lo), day_of(span_hi - 1)],
                   data_span_source=span_src, live_hours=live_hours, live_hours_source=live_info['source'], live_estimated=live_info,
                   live_median_hours=live_medians, n_raw={'A': n_raw_a, 'B': n_raw_b}, f1_cells=len(f1),
                   stick_cells=len(sticks), bh_rejections=int(rej.sum()), gates_A=dict(gates_a), flagged=[cells[i]['cell'] for i in f1 if cells[i]['flag']],
                   n_eff=n_eff, onc_cells=len(onc_ids), onc_distinct=n_distinct, onc_dropped=dropped, spa=spa, sr0=sr0, v_sr=v_sr,
                   v_sr_clusters={t: len(v) for t, v in cluster_srs.items()},
                   v_sr_source=('the variance of per-match Sharpe across the ONC cluster-mean series, each Sharpe over that tour '
                                'universe\'s matches; a cell\'s DSR uses the SR0 of its own tour universe, the matches its SR is over'),
                   pbo=pbo, onc=dict(onc_diag, warnings=onc_warn, max_k_arg=a.onc_max_k, dim=a.onc_dim, n_init=a.onc_init, k_range=k_range),
                   registry=registry,
                   sensitivity=sens, sensitivity_factorial=sens_main, production=production, production_config=prod_cfg,
                   stratum=stratum, sticks=stick_rows, bh_floor=bh_floor, family_b=fb_sum,
                   config_breaches={k: dict(v) for k, v in config_br.items() if sum(v.values())},
                   breach_configs=sorted({cells[i]['config'] for i in f1 if cells[i]['config_breaches'] > 0}))
    with open(os.path.join(a.out, 'summary.json'), 'w') as fh:
        fh.write(dumps(summary, indent=1))
    if league_files:
        write_one_test_files(a.out, summary, league_a, league_b, members, wd, pools, hold_run, batch, hold_score, h_hold, run_id,
                             run_days, run_tour, cells, by_id, day_set, fold_edges, ho1, reg_rows)

    L = render(a, summary, cells, f1, prod, loser_rows, prod_runs, fb_rows, meta, M, t_last, pools)
    if summary['registry'] and summary['registry'].get('written'):
        print(f"registry: {summary['registry']['rows']} row(s) written to {os.path.join(a.out, summary['registry']['file'])}")
    with open(os.path.join(a.out, 'report.md'), 'w') as fh:
        fh.write('\n'.join(L) + '\n')
    print('\n'.join(L))


def score_family_b(fam_b, uidx, unit_by_id, fidx, W, alpha, pool_hours, live_hours_all, day_fold=None):
    """Family B cells (merged FamilyBCell, C2) scored with the same unit bootstrap; its own BH family and DSR trial count.
    Folds: the month of each unit's last day, or (day_fold: a hold run's HO-1 fold index of a UTC day) by day."""
    cells = [c for c in fam_b['cells'] if c['n'] > 0]
    design = int(fam_b.get('designSize') or 0)
    m_total = max(design, len(cells))
    U, NF, B = W.shape[1], len(fidx), W.shape[0]
    rows = []
    if not cells:
        return rows, {'design_size': design, 'bh_m': m_total, 'cells_with_entries': 0, 'cells_total': len(fam_b['cells']), 'gates': {}, 'flagged': [],
                      'diagnostics': fam_b.get('diagnostics'), 'stratum': fam_b.get('stratum'), 'sr0': 0.0, 'v_sr': 0.0, 'bh_rejections': 0}
    SB, NB = np.zeros((len(cells), U)), np.zeros((len(cells), U))
    u_fold = {u: fidx[unit_fold(unit_by_id[u])] for u in uidx} if day_fold is None else {}
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
        for u, v in (c['units'].items() if day_fold is None else ()):
            if u in u_fold:
                fo_n[u_fold[u]] += v[0]
                fo_s[u_fold[u]] += v[1]
        for dd, v in (c['days'].items() if day_fold is not None else ()):
            f = day_fold(dd)
            if f is not None:
                fo_n[f] += v[0]
                fo_s[f] += v[1]
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


def sr0_of(v, n_trials):
    """The DSR's SR0: sqrt(V[SR]) x the expected maximum of n_trials standard normals (Bailey and Lopez de Prado)."""
    if v <= 0:
        return 0.0
    n_t = max(n_trials, 2)
    return math.sqrt(v) * ((1 - EULER) * norm_ppf(1 - 1 / n_t) + EULER * norm_ppf(1 - 1 / (n_t * math.e)))


def sr0_by_universe(series, universes, n_trials):
    """SR0 per tour universe -> ({t: SR0}, {t: V[SR]}, {t: [SR]}). series: the cluster-mean per-match P&L series (each of
    length N); universes: {t: bool mask over the N matches}. One universe per SR0: each cluster series' Sharpe is taken
    over universe t's matches, the same matches a cell of tour t takes its own SR over, so a cell's DSR compares like with
    like; a cluster that never trades a universe has no variance there and is not a trial on it."""
    srs = {t: [] for t in universes}
    for x in series:
        x = np.asarray(x, dtype=np.float64)
        for t, mask in universes.items():
            s = x[mask]
            sd = s.std(ddof=1) if len(s) > 1 else 0.0
            if sd > 0:
                srs[t].append(float(s.mean() / sd))
    v_sr = {t: (float(np.var(v, ddof=1)) if len(v) > 1 else 0.0) for t, v in srs.items()}
    return {t: sr0_of(v, n_trials) for t, v in v_sr.items()}, v_sr, srs


def spec_modules(overrides, stratum='H'):
    """The bot modules a run changes (C7), from its overrides' difference with production by value, for every family A
    row (stick, F1, F2 / F0 and coin alike): production's end loser cut off (the settle-hold stick) or the harness loser
    stop -> exits, the pacer off -> pacer, the bankroll -> sizing, any other TENNIS_* key -> tennis-ta. Nothing moved, or
    only a stress adversary or a decision-clock offset, measures the tennis rulebook itself -> tennis-ta."""
    d = diff_keys(overrides, PROD_SPEC.get(stratum or 'H', {}))
    mods = {MODULE_KEYS[k] for k in d if k in MODULE_KEYS}
    if any(k.startswith('TENNIS_') and k not in MODULE_KEYS for k in d):
        mods.add('tennis-ta')
    return sorted(mods) or ['tennis-ta']


stick_modules = spec_modules  # the pass 1 name


def stratum_label_of(stratum, pools):
    """The sweep's stratumLabelOf (research/tennisTaSweep.ts): pool 'old' on history is H0, else the stratum."""
    return 'H0' if stratum == 'H' and list(pools) == ['old'] else stratum


def reg_families(label):
    """The registry families (A, B) of a run's stratum label. A family is one multiple-testing unit and the registry
    scores it over the days every row shares (registry.py merge), and the strata are never pooled in a test (section 2):
    history in the start era (H: disc, and check once it opens) keeps tennis-ta-A / tennis-ta-B; H0 (pool old, the older
    product) and R (recorded books) get their own, suffixed by the label."""
    label = str(label or 'H')
    if label == 'H':
        return REG_FAMILY_A, REG_FAMILY_B
    return f'{REG_FAMILY_A}-{label}', f'{REG_FAMILY_B}-{label}'


def replay_version(path=HISTORY_REPLAY_TS):
    """REPLAY_VERSION of the history replay the sweep built its days with (research/history/historyReplay.ts), or None."""
    try:
        with open(path) as fh:
            text = fh.read()
    except OSError:
        return None
    m = re.search(r'^export const REPLAY_VERSION\s*=\s*(\d+)\s*;', text, re.M)
    return int(m.group(1)) if m else None


REPLAY_SKIP_KEYS = ('noCandles', 'noResult', 'dup', 'lateClose', 'startAfterClose')


def replay_skips_of(metas):
    """The replay's skip counts (meta.coverage.replaySkips, research/history/historyReplay.ts TennisSkips) over the union of
    the replay days the shards read (a day read by two shards counts once), or None when no shard carries them."""
    by_day, unbuilt, seen, scan = {}, set(), False, set()
    for mt in metas:
        rs = (mt.get('coverage') or {}).get('replaySkips')
        if not isinstance(rs, dict):
            continue
        seen = True
        if rs.get('scanDays') is not None:
            scan.add(rs['scanDays'])
        for d, c in (rs.get('byDay') or {}).items():
            by_day.setdefault(d, c or {})
        unbuilt.update(rs.get('unbuilt') or [])
    if not seen:
        return None
    out = {k: int(sum(int((c or {}).get(k) or 0) for c in by_day.values())) for k in REPLAY_SKIP_KEYS}
    out.update(days=len(by_day), unbuilt=sorted(unbuilt - set(by_day)), scanDays='/'.join(str(x) for x in sorted(scan)) or '?')
    return out


def rescore_sha(report_sha, swept_sha):
    """The scoring commit of a rescore: report_sha when given and not the sweep's own commit, else None (a sweep's own report)."""
    r = str(report_sha or '').strip()
    if not r or r.lower() == str(swept_sha or '').strip().lower():
        return None
    return r


def code_epoch(sim_version, rv):
    return f'{sim_version}; REPLAY_VERSION={rv}; {CODE_EPOCH_TAIL}'


def replay_version_of(meta, path=HISTORY_REPLAY_TS):
    """The history replay's REPLAY_VERSION a run's days were built with -> (version, source, error). The shard metas'
    replayVersion (the sweep records it) when present, which must agree with research/history/historyReplay.ts when that
    is readable (the rows' code_sha is the sweep's, so they can only differ by a mistake); else the file's."""
    rel = os.path.relpath(path, REPO)
    code = replay_version(path)
    raw = meta.get('replayVersion', meta.get('replay_version'))
    if raw is not None:
        if isinstance(raw, bool) or not (isinstance(raw, int) or (isinstance(raw, str) and raw.strip().isdigit())):
            return None, None, f'meta.replayVersion {raw!r} is not a whole number'
        mv = int(raw)
        if code is not None and code != mv:
            return None, None, f'the shards were built with REPLAY_VERSION {mv} (meta.replayVersion) but {rel} sets {code}'
        return mv, 'the shard metas (meta.replayVersion)' + (f', the same as {rel}' if code is not None else ''), None
    if code is None:
        return None, None, (f'cannot read REPLAY_VERSION from {path} (the history replay the sweep built its days with) and the shard '
                            f'metas carry no replayVersion: the rows\' code_epoch and data.replay_version would be a guess')
    return code, rel, None


def shared_base_defaults(overrides_list):
    """C11 base_defaults: the overrides every spec of the run shares (same key, same value by value) that differ from
    production's default (a key the report has no default for counts as differing), e.g. {'TENNIS_TRAIL_RATCHET': False}
    on history. Values as the first spec writes them."""
    if not overrides_list:
        return {}
    first, out = overrides_list[0], {}
    for k in sorted(first):
        v = ov_val(first, k)
        if all(k in o and ov_val(o, k) == v for o in overrides_list[1:]) and (k not in KNOB_DEFAULTS or v != knob_val(k, KNOB_DEFAULTS[k])):
            out[k] = first[k]
    return out


def hold_scoring(cells, by_id, run_days, run_tour, tour_hours, configs_arms, prod_rid, day_set, fold_edges, hours_per_day=24.0):
    """A hold run's score of each candidate (every F1 config but the production control), the report's own figures beside
    the registry's HO-1 block: the paired gain against the control in each HO-1 fold as $/h over 24 h a day (as
    research/registry.py ho1_fill takes it), folds won, the worst fold, each tour's gain per live-match hour (the
    tercile stand-in), the paired placebo comparison (the gain against the control of the candidate and of its coin arm,
    and the per-unit bootstrap of candidate minus coin on the all/all/all cell) and the F2 neighbour's gain."""
    cd = run_days[prod_rid]
    fold_days = [[d for d in day_set if ho1_fold_of(d, fold_edges) == k + 1] for k in range(len(fold_edges))]
    out = []
    for cfg, arms in sorted(configs_arms.items()):
        rid = arms.get('F1')
        if rid is None or rid == prod_rid:
            continue
        rd = run_days[rid]
        g = {d: rd.get(d, 0.0) - cd.get(d, 0.0) for d in day_set}
        pl, f2 = arms.get('coin'), arms.get('F2')
        folds = []
        for k, fd in enumerate(fold_days):
            if not fd:
                folds.append({'fold': k + 1, 'from': fold_edges[k][0], 'to': fold_edges[k][1], 'days': 0, 'gain': 0.0, 'gain_per_hour': None})
                continue
            gain = sum(g[d] for d in fd)
            f = {'fold': k + 1, 'from': fold_edges[k][0], 'to': fold_edges[k][1], 'days': len(fd), 'gain': gain,
                 'gain_per_hour': gain / (hours_per_day * len(fd)), 'net_per_hour': sum(rd.get(d, 0.0) for d in fd) / (hours_per_day * len(fd))}
            if pl:
                f['vs_placebo_per_hour'] = sum(rd.get(d, 0.0) - run_days[pl].get(d, 0.0) for d in fd) / (hours_per_day * len(fd))
            if k == len(fold_days) - 1 and fold_edges[-1][1] in fd:
                # research/registry.py ho1_fill appends H-HOLD's last day to the last fold although its last edge already holds it:
                # the registry's figure for that fold (the day counted twice), kept to explain a difference
                f['gain_per_hour_registry'] = (gain + g[fold_edges[-1][1]]) / (hours_per_day * (len(fd) + 1))
            folds.append(f)
        fg = [f['gain_per_hour'] for f in folds if f['gain_per_hour'] is not None]
        total = sum(g.values())
        plac = None
        if pl:
            pg = sum(run_days[pl].get(d, 0.0) - cd.get(d, 0.0) for d in day_set)
            ca = cells[by_id[(cfg, 'F1', 'all', 'all', 'all')]]
            plac = {'arm': pl, 'gain': pg, 'beats': total > pg, 'diff': total - pg, 'diff_per_match': ca.get('placebo_diff'),
                    'p': ca.get('p_placebo'), 't_day': ca.get('t_day_placebo')}
        tours = {t: {'gain': run_tour[rid][t] - run_tour[prod_rid][t], 'hours': tour_hours[t],
                     'gain_per_live_hour': (run_tour[rid][t] - run_tour[prod_rid][t]) / tour_hours[t] if tour_hours[t] > 0 else None}
                 for t in ('ATP', 'WTA')}
        out.append({'config': cfg, 'arm': rid, 'gain': total, 'gain_per_hour': total / (hours_per_day * len(day_set)) if day_set else None,
                    'folds': folds, 'folds_won': sum(1 for x in fg if x > 0), 'worst_fold_per_hour': min(fg) if fg else None,
                    'tours': tours, 'placebo': plac,
                    'neighbour': {'arm': f2, 'gain': sum(run_days[f2].get(d, 0.0) - cd.get(d, 0.0) for d in day_set)} if f2 else None})
    return {'control': prod_rid, 'days': len(day_set), 'hours_per_day': hours_per_day,
            'folds': [{'fold': k + 1, 'from': a_, 'to': b_, 'days': len(fd)} for k, ((a_, b_), fd) in enumerate(zip(fold_edges, fold_days))],
            'candidates': out}


def hold_summary(score, hold_after, meta, plan, run_id, runs):
    """summary.json's hold block: the score and the frozen list it scored (C10: its hash, sha256 of the canonical spec
    list as the sweep's specsHash, from the shard metas or the plan, and its spec ids; the workflow appends the opening)."""
    sha = meta.get('specsHash') or (plan or {}).get('specsHash')
    return dict(score or {}, matches_after_hold=len(hold_after), specs_sha=sha, spec_ids=sorted(runs), run=str(run_id))


def registry_fold_differences(hc, h, tol=1e-9):
    """Where the registry's HO-1 block (ho1_fill) differs from the report's own fold figures for a candidate, and why
    when the registry's double count of H-HOLD's last day explains it."""
    if not isinstance(h, dict):
        return []
    out = []
    if h.get('folds_won') is not None and h['folds_won'] != hc['folds_won']:
        out.append(f"folds won: registry {h['folds_won']}, report {hc['folds_won']}")
    rw, mw = h.get('worst_fold_per_hour'), hc['worst_fold_per_hour']
    if finite(rw) and finite(mw) and abs(rw - mw) > tol:
        alt = [f.get('gain_per_hour_registry', f['gain_per_hour']) for f in hc['folds'] if f['gain_per_hour'] is not None]
        why = (' (the registry counts H-HOLD\'s last day twice in the last fold)'
               if alt and abs(min(alt) - rw) <= 1e-6 else '')
        out.append(f"worst fold: registry {rw:+.4f} $/h, report {mw:+.4f} $/h{why}")
    return out


def live_durations(M, pool_medians=None):
    """Live-match hours per pool match (A7: close minus the published start) and how they were found. A match without a
    published start gets its series' median over the pool's published matches; a series with none gets the pool's
    median over every series; a pool with none at all (H0: no match has one) takes pool_medians ({series or '*': h},
    --live-median-hours, a start-era run's live_median_hours), else live hours are not measured and every $/live-hour is
    refused (None). -> (durations or None, {series: measured median}, {estimated, by, source})."""
    live = np.array([max(0, m['close'] - m['start']) / HOUR_MS for m in M], dtype=float)
    published = np.array([m.get('startPublished', True) is not False for m in M], dtype=bool)
    series = np.array([m['series'] for m in M])
    medians = {str(s): float(np.median(live[(series == s) & published])) for s in sorted(set(series)) if ((series == s) & published).any()}
    est = int((~published).sum())
    info = {'estimated': est, 'by': {}, 'source': 'measured: close minus the published start'}
    if not est:
        return live, medians, info
    pool_med = float(np.median(live[published])) if published.any() else None
    given = {str(k): float(v) for k, v in (pool_medians or {}).items()}
    for s in sorted(set(series)):
        sel = (series == s) & ~published
        if not sel.any():
            continue
        if s in medians:
            live[sel], how = medians[s], 'its series\' median'
        elif pool_med is not None:
            live[sel], how = pool_med, 'the pool\'s median (its series has no published start)'
        elif s in given or '*' in given:
            live[sel], how = given.get(s, given.get('*')), '--live-median-hours'
        else:
            return None, medians, {'estimated': est, 'by': {}, 'source': (
                f"not measured: {est} of {len(M)} pool matches have no published start and {s} has no median to stand in "
                f"(pass --live-median-hours, e.g. a start-era run's summary.json live_median_hours)")}
        info['by'][str(s)] = {'matches': int(sel.sum()), 'hours_each': round(float(live[sel][0]), 4), 'from': how}
    info['source'] = (f"close minus the published start; {est} of {len(M)} pool matches without one estimated ("
                      + '; '.join(f"{s} {v['matches']} at {v['hours_each']:.2f} h, {v['from']}" for s, v in info['by'].items()) + ')')
    return live, medians, info


def parse_live_medians(spec):
    """--live-median-hours: a number (every series) or SERIES=HOURS,... (e.g. KXATPMATCH=1.9,KXWTAMATCH=1.6), or a
    summary.json whose live_median_hours to take. -> {series or '*': hours}."""
    if not spec:
        return {}
    if os.path.exists(spec):
        with open(spec) as fh:
            got = json.load(fh).get('live_median_hours') or {}
        out = {str(k): float(v) for k, v in got.items()}
    elif '=' in spec:
        out = {}
        for part in spec.split(','):
            k, _, v = part.partition('=')
            out[k.strip()] = float(v)
    else:
        out = {'*': float(spec)}
    if not out or not all(math.isfinite(v) and v > 0 for v in out.values()):
        raise ValueError(f'{spec!r}: no positive finite hours')
    return out


def full_days(by_day, day_set):
    """{day: $} over the run's whole day set (0 on a day without a trade), rounded to 1e-6 $."""
    out = {}
    for d in day_set:
        v = round(float(by_day.get(d, 0.0)), 6)
        out[d] = 0.0 if v == 0 else v
    return out


def registry_rows(make_id, sha, day_set, hours, data, flags, ref, epoch, ts, a_runs, b_rules, stratum='H', label=None, base=None,
                  base_defaults=None, w_runs=()):
    """The C7 registry v1 rows of one run -> (rows, problems, notes). Problems stop the write; notes are reported.
    a_runs: one per family A spec {id, config, arm (F0 / F1 / F2 / coin / stick), overrides, production (the F1 run of
    the config equal to production by value), by_day, fills, markets, verdict, raw}. b_rules: one per family B reading x
    exit {rule, by_day, by_cell, fills, markets (None when the export has no market counts), verdict, raw, placebo (None,
    or {by_day, fills, markets, raw})}. Roles: the production F1
    row is the control and every other F1 row a candidate against it; a config's F2 / F0 row is its neighbour and its
    coin row its placebo, both against the config's F1 row; measuring sticks are controls; a family B row is a candidate
    against its own placebo row. Every row: contract_type 'tennis', its modules, by_day over the whole day set. label: the
    stratum label (H, H0, R; default the stratum), which picks the families (reg_families). Family A modules come from
    each run's overrides against production (spec_modules), the same rule for sticks and hypotheses. C11: every row
    carries base ('tennis-ta@<sha>') and base_defaults when given; a placebo row names the arm it mimics (placebo_for: the
    config's F1 arm; family B: its reading x exit); an a_run's by_tercile (a hold run: {'ATP'|'WTA': {pnl, hours}}) is
    copied onto its row. w_runs (Amendment 4 item 10): one per hot spot {id ('<config>|window|<leg>'), config, leg, kind
    'window' | 'coinwindow', overrides, by_day (the gap per UTC match day), by_tercile ({'ATP'|'WTA': {pnl: the gap, hours, ...}}),
    fills (instances), markets (matches with an instance), verdict, raw, placebo_id (the coin placebo's id) | placebo_for
    (on a coinwindow row), heldout (the read's one-test block)}: a window row is a candidate whose control is its coin
    placebo row (role placebo, placebo_for the window row's arm, seed PLACEBO_SEED), data.metric 'window_gap' and
    data.regime_proxy 'tour'."""
    rows, problems, notes = [], [], []
    fam_a, fam_b = reg_families(label or stratum)
    day_set = sorted(day_set)
    days = set(day_set)
    for x in list(a_runs) + list(b_rules) + list(w_runs) + [b['placebo'] for b in b_rules if b.get('placebo')]:
        extra = set(x['by_day']) - days
        if extra:
            problems.append(f"{x.get('id') or x.get('rule')}: by_day names day(s) outside the run's day set: {sorted(extra)[:3]}")
    common = {'v': 1, 'ts': ts, 'thread': REG_THREAD, 'code_sha': sha, 'code_epoch': epoch, 'contract_type': 'tennis', 'data': data,
              'hours': float(hours), 'flags': list(flags), 'ref': ref}
    if base is not None:
        common.update(base=base, base_defaults=dict(base_defaults or {}))
    ids = {}

    def tid(family, arm, seed, env):
        return make_id(REG_THREAD, family, arm, sha, day_set, seed, [], env)
    f1_of = {r['config']: r for r in a_runs if r['arm'] == 'F1'}
    prods = [r for r in a_runs if r['arm'] == 'F1' and r.get('production')]
    if len(prods) > 1:
        problems.append(f"{len(prods)} F1 runs equal production by value ({', '.join(r['id'] for r in prods[:3])}): the control is ambiguous")
    prod = prods[0] if len(prods) == 1 else None
    for r in a_runs:
        seed = PLACEBO_SEED if r['arm'] == 'coin' else None
        ids[r['id']] = tid(fam_a, r['id'], seed, r['overrides'])
    if prod is None and any(r['arm'] == 'F1' for r in a_runs):
        notes.append('no F1 run equals production by value: the F1 candidates have no control (the registry flags them G2:unpaired)')
    for r in sorted(a_runs, key=lambda x: x['id']):
        arm = r['arm']
        row = dict(common, trial_id=ids[r['id']], family=fam_a, arm=r['id'], env=r['overrides'],
                   seed=PLACEBO_SEED if arm == 'coin' else None, modules=spec_modules(r['overrides'], stratum))
        if arm == 'stick':
            row.update(role='control')
        elif arm == 'F1':
            row.update(role='control' if r is prod else 'candidate')
            if r is not prod and prod is not None:
                row['control'] = ids[prod['id']]
        else:
            row.update(role='placebo' if arm == 'coin' else 'neighbour')
            f1 = f1_of.get(r['config'])
            if f1 is not None:
                row['control'] = ids[f1['id']]
                if arm == 'coin':
                    row['placebo_for'] = f1['id']
            else:
                notes.append(f"{r['id']}: its config has no F1 run, so the {'placebo' if arm == 'coin' else 'neighbour'} row has no control")
        row.update(by_day=full_days(r['by_day'], day_set), fills=int(r['fills']), markets=int(r['markets']), verdict=r['verdict'], raw=r['raw'])
        if r.get('by_tercile'):
            row['by_tercile'] = {k: {'pnl': float(v['pnl']), 'hours': float(v['hours'])} for k, v in sorted(r['by_tercile'].items())}
        rows.append(row)
    w_data = dict(data, metric='window_gap', regime_proxy='tour')
    for r in w_runs:
        ids[r['id']] = tid(fam_a, r['id'], PLACEBO_SEED if r['kind'] == 'coinwindow' else None, r['overrides'])
    for r in sorted(w_runs, key=lambda x: x['id']):
        coin = r['kind'] == 'coinwindow'
        row = dict(common, trial_id=ids[r['id']], family=fam_a, arm=r['id'], leg=r['leg'], env=r['overrides'], data=w_data,
                   seed=PLACEBO_SEED if coin else None, modules=spec_modules(r['overrides'], stratum), role='placebo' if coin else 'candidate')
        if coin:
            row['placebo_for'] = r['placebo_for']
        elif r.get('placebo_id') in ids:
            row['control'] = ids[r['placebo_id']]
        row.update(by_day=full_days(r['by_day'], day_set), fills=int(r['fills']), markets=int(r['markets']), verdict=r['verdict'], raw=r['raw'])
        if r.get('by_tercile'):
            row['by_tercile'] = {k: dict(v, pnl=float(v['pnl']), hours=float(v['hours'])) for k, v in sorted(r['by_tercile'].items())}
        if r.get('heldout'):
            row['heldout'] = dict(r['heldout'])
        rows.append(row)
    for b in sorted(b_rules, key=lambda x: x['rule']):
        row = dict(common, trial_id=tid(fam_b, b['rule'], None, {}), family=fam_b, arm=b['rule'], role='candidate', env={},
                   seed=None, modules=['tennis-ta'])
        pl = b.get('placebo')
        if pl is not None:
            parm = b['rule'] + '|placebo'
            prow = dict(common, trial_id=tid(fam_b, parm, PLACEBO_SEED, {}), family=fam_b, arm=parm, role='placebo', env={},
                        seed=PLACEBO_SEED, modules=['tennis-ta'], placebo_for=b['rule'], by_day=full_days(pl['by_day'], day_set), fills=int(pl['fills']),
                        verdict='placebo (not screened)', raw=pl['raw'])
            if pl.get('markets') is not None:
                prow['markets'] = int(pl['markets'])
            row['control'] = prow['trial_id']
            rows.append(prow)
        row.update(by_day=full_days(b['by_day'], day_set), fills=int(b['fills']), verdict=b['verdict'], raw=b['raw'])
        if b.get('markets') is not None:
            row['markets'] = int(b['markets'])
        if b.get('by_cell'):
            row['by_cell'] = {k: round(float(v), 6) for k, v in sorted(b['by_cell'].items())}
        rows.append(row)
    seen = Counter(r['trial_id'] for r in rows)
    dup = [k for k, v in seen.items() if v > 1]
    if dup:
        problems.append(f"{len(dup)} trial id(s) repeat (e.g. {dup[0]}: {', '.join(r['arm'] for r in rows if r['trial_id'] == dup[0])})")
    return rows, problems, notes


def _level_key(v):
    try:
        return (0, float(v), '')
    except (TypeError, ValueError):
        return (1, 0.0, str(v))


def _ctx_of(c):
    """A family B cell's context (the cut of its rule's entries: 'all', or phase:band:trend)."""
    g, cid = c.get('group') or '', c['id']
    if g and cid.startswith(g + '|'):
        return cid[len(g) + 1:].rsplit('|', 1)[0]
    parts = cid.split('|')
    return parts[-2] if len(parts) > 2 else ''


def _rule_of(c):
    """A family B trading rule: the reading's group plus the exit (the context is only a cut of its entries)."""
    g, cid = c.get('group') or '', c['id']
    if g and cid.startswith(g + '|'):
        rest = cid[len(g) + 1:]
        return g + '|' + rest.rsplit('|', 1)[-1]
    parts = cid.split('|')
    return '|'.join(parts[:-2] + parts[-1:]) if len(parts) > 2 else cid


def render_hold(s):
    """report.md's H-HOLD section: each candidate of the frozen list scored once against the production control."""
    h = s['hold']
    L = ['### H-HOLD score (HO-1, once per frozen spec list)']
    nd = len(hold_days(tuple(s['h_hold'])))
    L.append('Under Amendment 4 this section is information: the HO-1 money bars (ho1_pass, the folds, the tours, the placebo) cut nothing; '
             'the read is the one test on the batch (hold-league.md).')
    if not h.get('control'):
        L.append(f"- no production control among the run's F1 arms (a batch runs its configs' |window and |F1 arms only): no paired HO-1 "
                 f"score; {len(h.get('spec_ids') or [])} spec(s), hash {h.get('specs_sha') or 'not in the shard metas or the plan'}; the F1 arms' own "
                 f"P&L by fold is in hold-league.md")
        return L
    L.append(f"Frozen list: {len(h['spec_ids'])} spec(s), hash {h['specs_sha'] or 'not in the shard metas or the plan'}; control "
             f"{h['control']}; {h['days']} of H-HOLD's {nd} days ({s['h_hold'][0]} to {s['h_hold'][1]}). Each candidate is scored by its "
             f"paired gain over the control ($ after fees, candidate minus control by day), per fold as $/h over 24 h a day as "
             f"research/registry.py ho1_fill takes it; the tours stand in for the RV terciles (gain per live-match hour of that tour's "
             f"hold matches, at least 100 h to count); the placebo comparison is the candidate's gain against its coin arm's gain over "
             f"the same control (beats = larger), with the per-unit bootstrap p of candidate minus coin.")
    if not h['candidates']:
        L.append('- no candidate')
        return L
    nf = len(s['ho1_folds'])
    L.append('| candidate | gain | $/h | ' + ' | '.join(f'fold {k + 1} $/h' for k in range(nf))
             + ' | folds won | worst fold $/h | ATP $/live h | WTA $/live h | vs placebo | F2 gain | HO-1 |')
    L.append('|' + '---|' * (10 + nf))
    for c in h['candidates']:
        pl = c['placebo']
        pl_txt = (f"{usd(c['gain'])} vs {usd(pl['gain'])} ({'beats' if pl['beats'] else 'does not beat'}; p {f4(pl['p'], '.4f')})" if pl else 'no coin arm')
        ho = c.get('ho1')
        ho_txt = ('pass' if ho['pass'] else f"fail: {ho['why']}") if ho else 'no registry block'
        L.append(f"| {md(c['arm'])} | {usd(c['gain'])} | {f4(c['gain_per_hour'])} | "
                 + ' | '.join(f4(f['gain_per_hour']) for f in c['folds'])
                 + f" | {c['folds_won']}/{sum(1 for f in c['folds'] if f['days'])} | {f4(c['worst_fold_per_hour'])} | "
                 f"{f4(c['tours']['ATP']['gain_per_live_hour'])} ({c['tours']['ATP']['hours']:,.0f} h) | "
                 f"{f4(c['tours']['WTA']['gain_per_live_hour'])} ({c['tours']['WTA']['hours']:,.0f} h) | {pl_txt} | "
                 f"{usd((c['neighbour'] or {}).get('gain'))} | {md(ho_txt)} |")
    for c in h['candidates']:
        ho = c.get('ho1')
        if not ho:
            continue
        hb = ho['heldout']
        L.append(f"- {md(c['arm'])}: registry HO-1 block (ho1_fill): {hb.get('days')} days, {hb.get('folds_won')}/{hb.get('folds')} folds won, "
                 f"worst fold {f4(hb.get('worst_fold_per_hour'))} $/h, tours {hb.get('terciles_won', '-')}/{hb.get('terciles_covered', '-')} won "
                 f"(worst {f4(hb.get('worst_tercile_per_hour'))} $/h), beats placebo {hb.get('beats_placebo')}, replay version "
                 f"{hb.get('replay_version')}: ho1_pass {'PASS' if ho['pass'] else 'FAIL (' + ho['why'] + ')'}."
                 + (' Differs from the report: ' + '; '.join(c['registry_differs']) + '.' if c.get('registry_differs') else ''))
    return L


def render(a, s, cells, f1, prod, loser_rows, prod_runs, fb_rows, meta, M, t_last, pools):
    L = []
    pool_txt = ','.join(pools)
    L.append(f"## Tennis TA sweep, stage {s['stage']}, pool {pool_txt}, stratum {s['stratum_label']} (run {s['run']})")
    rescored_at = rescore_sha(getattr(a, 'report_sha', None), meta.get('sha'))
    L.append(f"Evidence: {meta.get('evidence', '-')}. sha {str(meta.get('sha') or '-')[:10]}, {s['sim_version']}, data version {s['data_version']}. "
             + (f"Scored at {rescored_at[:10]} (a rescore of the shards swept at {str(meta.get('sha'))[:10]}). " if rescored_at else '')
             + f"Days {M[0]['day']} to {M[-1]['day']} UTC "
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
    rsk = s.get('replay_skips')
    if rsk:
        L.append(f"- Replay: over {rsk['days']} read replay day(s), {rsk['noCandles'] + rsk['noResult'] + rsk['dup'] + rsk['lateClose']} stored traded market line(s) "
                 f"were not replayed ({rsk['noCandles']} without candles, {rsk['noResult']} without a yes/no result, {rsk['dup']} second line(s) of a ticker, "
                 f"{rsk['lateClose']} closing more than {rsk.get('scanDays', '?')} days after they began); {rsk['startAfterClose']} were replayed without a start "
                 f"(their published start was at or after their close), so they count under 'nostart'"
                 + (f"; {len(rsk['unbuilt'])} read day(s) were not in the replay manifest" if rsk['unbuilt'] else '') + '.')
    bp = s['by_pool']
    L.append("- Matches by pool (matchList): " + ', '.join(f"{p} {v['matches']} in {v['units']} unit(s)" + (' (scored)' if v['scored'] else ' (excluded, counted)')
                                                         for p, v in bp.items())
             + f". Only pool {pool_txt} is scored; the other pools' rows ({', '.join(repr(p) for p in bp if p not in s['pools']) or 'none'}) "
             + f"are left out of it. Era rule (C9, edges from {s['era_source']}): "
             + s['era_rule'] + '.')
    if s['hold_run'] and s['hold']['matches_after_hold']:
        L.append(f"- {s['hold']['matches_after_hold']} hold match(es) start on a UTC day after H-HOLD's last day ({s['h_hold'][1]}), in the hours "
                 f"before the cutoff: no H-HOLD match (the registry's H-HOLD ends {s['h_hold'][1]}), left out of the score and the rows.")
    fb = s['family_b']
    L.append(f"- N_raw: family A {s['n_raw']['A']} cells ({s['f1_cells']} F1 cells screened, {s['stick_cells']} measuring-stick cells logged, never "
             f"screened)" + (f"; family B {s['n_raw']['B']} cells with entries (design {fb['design_size']}, its own BH family)" if fb else '; family B not run') + '.')
    L.append(f"- Hours: pool {s['pool_hours']:,.0f} h (from {s['pool_hours_source']}: the pool's units cut to its window ("
             + ('H-HOLD, from HOLD_FROM to the end of its last UTC day' if s['hold_run'] else 'H-DEV, up to DEV_TO' if s['pools'] == ['disc']
                else 'the old-era units, whole')
             + f"; the embargo day Jul 31 counts in no pool), clipped to the data span {s['data_span'][0]} to {s['data_span'][1]}, {s['data_span_source']}; {s['pool_hours_unclipped']:,.0f} h unclipped); "
             + (f"live-match {s['live_hours']['all']:,.1f} h ({s['live_hours_source']})." if s['live_hours']['all'] is not None
                else f"live-match hours {s['live_hours_source']}, so every $/live-match-hour figure is n/a."))
    if s['live_hours']['all'] is None:
        L.append(f"**Warning (A7):** no $/live-match-hour figure in this run: live-match hours {s['live_hours_source']}.")
    pb = s['pbo']
    if s['hold_run']:
        L.append(f"- Folds: the {len(s['ho1_folds'])} HO-1 folds of H-HOLD ({s['h_hold'][0]} to {s['h_hold'][1]}), cut by each match's UTC day at "
                 f"research/registry.py's edges: " + ', '.join(f"{f['fold']}: {f['from']} to {f['to']}" for f in s['ho1_folds'])
                 + '; the fold share, PBO and every fold column below use them (the bootstrap still resamples whole units).')
    else:
        L.append(f"- Folds: {len(s['folds'])} monthly folds by the month of each unit's last day (a unit is never split)"
                 + (f"; CSCV drops fold {pb['dropped_fold']} to make the count even" if pb and pb.get('dropped_fold') else '') + '.')
    bf = s['bh_floor']
    L.append(f"- Bootstrap: stationary over {s['units']} units (mean block {a.block:g} unit), B = {a.boot}, seed {a.seed}; p = (c + 1) / (B + 1), so the "
             f"smallest p is {bf['p_min']:.1e} and BH at q = {a.alpha} rejects nothing unless at least {bf['A_cells_at_floor_needed']} of the "
             f"{bf['A_m']} F1 cells sit at that floor" + (f" ({bf['B_cells_at_floor_needed']} of family B's {bf['B_m']})" if fb else '') + '.')
    L.append('')
    ot = s.get('one_test') or {}
    L.append('### The one test (Amendment 4: the only statistical bar; everything else in this report is information)')
    if ot.get('run'):
        L.append(f"- Window block {ot.get('version')}: {ot['events_scored']} of its {ot['events']} events in pool {pool_txt}; {ot['rows_a']} family A hot "
                 f"spots (config x leg), {ot['with_z']} with a z, {ot['pass']} with gap >= 2 x SE; {ot['rows_b']} family B hot spots. "
                 + (f"The read (stage hold): {len((ot.get('batch') or {}).get('members') or [])} batch member(s) scored in hold-league.md; "
                    f"{sum(1 for m_ in (ot.get('batch') or {}).get('members') or [] if m_['direction_found'])} direction found."
                    if s['hold_run'] else f"The league (ranked by z, ties by gap; hottest {', '.join(ot['hottest']) or '-'}) is in league.md, "
                                          f"league.csv and league.json beside this report, the batch candidate in hold-batch-candidate.json "
                                          f"(the {HOLD_BATCH_MAX} hottest by z, measuring sticks excepted)." if ot.get('league')
                    else f"No league: {ot.get('league_reason')}; hottest {', '.join(ot['hottest']) or '-'}.")
                 + ' Rule: ' + ot.get('rule', '') + '.')
    else:
        L.append(f"- not run: {ot.get('reason', 'no window block')}.")
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
    if s['hold_run']:
        L += render_hold(s)
        L.append('')
        L.append('The discovery screen below is descriptive on H-HOLD (the settings were chosen on H-DEV; HO-1 above is information, '
                 'the one test on the batch is the read):')
    g = s['gates_A']
    L.append(f"Discovery screen (information under Amendment 4: no cell is cut by it, the one test is the only bar): BH q = {a.alpha} "
             f"rejects {s['bh_rejections']} of {s['f1_cells']} F1 cells; gates met: "
             + ', '.join(f'{k} {g.get(k, 0)}' for k in ('BH', 'entries>=100', 'days>=30', 'mean>0', 'folds>=60%', 'F2 net>0', 'config breaches=0'))
             + f"; {g.get('all', 0)} meet every discovery condition (information).")
    if s['breach_configs']:
        L.append(f"{len(s['breach_configs'])} config(s) had a settlement breach in some cell of some arm, so none of their cells meets the screen (information): "
                 + ', '.join(s['breach_configs'][:8]) + (', ...' if len(s['breach_configs']) > 8 else '') + '.')
    if s['spa']:
        sp = s['spa']
        L.append(f"SPA (consistent) over {sp['models']} models: T = {sp['T']:.2f}, p = {sp['p_consistent']:.4f}, best {sp['best']}. "
                 f"StepM (alpha {sp['stepm_alpha']}) rejects {len(sp['stepm_rejected'])}.")
    od = s['onc']
    kr = od.get('k_range')
    if kr:
        k_txt = (f"; k search range 2..{kr['to']}" + (f" (capped by --onc-max-k {kr['cap']}, below n - 1 = {kr['n'] - 1})" if kr['cap']
                                                       else f" = n - 1 of the {kr['n']} distinct vectors (no cap)")
                 + f": {kr['grid']}, {kr['scanned']} k tried, k-means on {od['kmeans_dims']} components keeping {od['kmeans_variance_kept']:.1%} "
                 f"of the variance, silhouettes exact")
        k_txt += (f"; best k {od['best_k']} (quality {od['best_q']:.2f}){', refinement kept' if od.get('refined') else ', refinement not kept'}"
                  if od.get('best_k') else '; no k gave a valid split')
    else:
        k_txt = '; ONC not run (fewer than 3 distinct vectors: N_eff = their count)'
    L.append(f"N_eff = {s['n_eff']} (ONC over {s['onc_cells']} F1 cells with >= {a.onc_min} entries, {s['onc_distinct']} distinct per-match vectors"
             + (f", {s['onc_dropped']} beyond the cap left out" if s['onc_dropped'] else '') + k_txt + ').')
    for w_ in od.get('warnings') or []:
        L.append(f"**Warning (ONC):** {w_}.")
    if pb:
        L.append(f"PBO (CSCV, {pb['folds']} folds, {pb['combos']} splits): {pb['pbo']:.2f}.")
    L.append("DSR reference SR0 per match, one per tour universe (" + s['v_sr_source'] + "): "
             + '; '.join(f"{t} {s['sr0'][t]:.4f} (V[SR] {s['v_sr'][t]:.6f} over {s['v_sr_clusters'][t]} cluster series)" for t in s['sr0'])
             + ", N = N_eff.")
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
    L.append(f"- Ranking scope: {sv.get('scope')}.")
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
    rg = s.get('registry') or {}
    L.append('')
    if rg.get('written'):
        L.append(f"Registry (C7, research/registry.py v1, validated): {rg['rows']} row(s) in {rg['file']} ("
                 + ', '.join(f'{k} {v}' for k, v in sorted(rg['families'].items())) + '; roles ' + ', '.join(f'{k} {v}' for k, v in sorted(rg['roles'].items()))
                 + f"), contract type tennis; control {rg['control_arm'] or 'none (no production F1 run)'}; by_day over {rg['days']} UTC "
                 + ('H-HOLD day(s)' if s['hold_run'] else 'match day(s), none in H-HOLD')
                 + f", hours {rg['hours']:,.1f} (the $/h denominator); code {str(rg['code_sha'])[:10]}, {rg['code_epoch']}; base {rg.get('base')}"
                 f" (base_defaults {json.dumps(rg.get('base_defaults') or {}, sort_keys=True)}); data.replay_version {rg['replay_version']}"
                 + (f"; flags {', '.join(rg['flags'])}" if rg['flags'] else '')
                 + (f"; validator flags {', '.join(f'{k} {v}' for k, v in sorted(rg['validator_flags'].items()))}" if rg['validator_flags'] else '') + '.')
        for x in rg.get('notes') or []:
            L.append(f"- {x}.")
        if s['hold_run']:
            L.append("- HO-1 verdicts (HO-1 pass / fail) and the discovery flags are information under Amendment 4; a hot spot's result is its "
                     "one-test row (direction found on a pass of the read).")
    else:
        L.append(f"Registry: no rows ({rg.get('reason', 'not written')}).")
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
