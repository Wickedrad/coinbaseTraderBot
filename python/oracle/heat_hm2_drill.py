"""OR-HM2 Part 3: what separates the winners (python/oracle/prereg/OR-HM2-part3.md; build plan
/mnt/project-files/direction-research/oracle-hm2/OR-HM2-part3-build.md). It changes no line of oracle.heat, of the
HM2 modules or of any stored table: it imports them.

  python3 -m oracle.heat_hm2_drill units  --direction <direction_all.csv.gz> --direction-long <long direction_all.csv.gz>
                                          --packs research/oracle_heat/latest --hm2-pack <hm2_pack.json> --out units.json
  python3 -m oracle.heat_hm2_drill coin   <heat_hm2's data flags> --units units.json --hm2-series <dir> --out <dir>
                                          [--part i/S] [--blocks a-b] [--procs 4] [--twin-units all|quarter] [--shards <dir>] [--no-chart]
  python3 -m oracle.heat_hm2_drill bench  <the same data flags> --units units.json --hm2-series <dir> --n-units 200 --out <dir>
  python3 -m oracle.heat_hm2_drill league --inputs <dir> --units units.json --out <dir> [--hm2-pack f] [--hm2-live-meta f]
                                          [--hm2-league <dir>] [--stamp text] [--merge-only gate_rows.json]
  python3 -m oracle.heat_hm2_drill parity --asset A <data flags> --units units.json --gates gate_rows.json --out <dir> [--days 3]

A unit is one call (a coin and an event key that fires at a minute close; entry at the next minute's open): an HM1
event level, an HM1 pack cell (pair, triple or clock cell, the pair pack's fire rule), an HM2 pack row (the onset of
its joint state, or a GBM zone). Each unit's instances are its fires on valid rows of A (2020-2024, a seeded sample of
A_CAP when there are more) and of B (2025, all). Per instance and horizon (1, 5, 15, 30, 60, 240): right / wrong /
flat in the unit's A direction, the move, the profit proxy (Kalshi cents per contract at 1-60, clipped at +-50c gross;
perp bps after 25 bps at 240), take / cut / time. Every parameter known at the decision close (the engine and HM2
readings, the GBM readings, the unit's own instance features) splits the instances by level; per level the lift over
the parameter's other known levels on three tracks (right in odds points, move in bps, profit), with a day- and a
week-clustered t: the weaker |t| ranks (z_adj, Bonferroni inside the parameter). Chosen on A, the top TOP_B of every
list are scored on B; the drill follows A's top TOP_FULL (finer curve, depth 2 inside the take gate, the loser
profile). The twins run the identical procedure on the same unit keys. No pass bar filters a unit, a parameter or a
level: marks are columns, the twins stand beside every count. A map on coin price, not a Kalshi-price result. NEVER
DOGE.
"""
import argparse
import contextlib
import gzip
import hashlib
import importlib
import importlib.util
import json
import math
import os
import re
import time
import zlib

import numba as nb
import numpy as np
import pandas as pd

from oracle import heat
from oracle import heat_hm2 as hm
from oracle.common import MIN

# ---------------------------------------------------------------------------------------- constants (OR-HM2 Part 3)
A_CAP = 25_000
H_ALL = [1, 5, 15, 30, 60, 240]
PACK_H = [15, 60, 240]
TRACKS = ('right', 'move', 'profit')
MODES = ('take', 'skip')
LISTS = ('main', 'insample')
TOP_B = 25
TOP_FULL = 5
DEPTH2_TRACKS = ('right', 'profit')
DEPTH2_H = [15, 60, 240]
DEPTH2_MIN = (300, 30)
DEPTH2_TOP = 5
FLOOR_A = (30, 30)
FLOOR_B = (30, 20)
PCT_BINS = 200
PCT_NA = 255
CURVE_BINS = 10
F11, F25 = 11, 25
M11, M25 = (1 << F11) - 1, (1 << F25) - 1
Q_MOVE = 0.5
CLIP = 4000.0
KALSHI_RT_C = 4.5
C_PER_SIGMA = 40.0
TAU = {1: 10, 5: 10, 15: 10, 30: 30, 60: 30}
TAKE_X = 2.0
CUT_X = 2.0
MIN_STEPS = 2
PERP_RT_BPS = 25.0
PERP_STOP_ATR = 2.0
PERP_MIN_STOP = 50.0
PI_C_CLIP = 50.0
Q_PI_C = 0.05
PROFIT_UNIT = {1: 'pi_c', 5: 'pi_c', 15: 'pi_c', 30: 'pi_c', 60: 'pi_c', 240: 'pi_bps'}
OFF_M = int(round(CLIP / Q_MOVE))                                      # 8,000: a move or a 240 pi packs as 0..16,000
OFF_PC = int(round((PI_C_CLIP + KALSHI_RT_C) / Q_PI_C))                # 1,090: pi_c packs as 0..2,000
WEEK = 7
IN_SAMPLE = re.compile(r'^(GBM\.|OWN:Agree@)')
SINCE_EDGES = [1, 3, 10, 30, 100]
ORDER_W = 30
ORDER_EDGES = [0, 1, 2, 5]
COINCIDE_EDGES = [0, 2, 5, 10, 20]
AGREE_EDGES = [-5, -2, 1, 4]
BODY_EDGES = [-0.6, -0.2, 0.2, 0.6]
LAST_WINDOW = 1440
SIGMA_MIN = 720                    # 1-minute returns the 1-day sd needs (half the day); fewer: NaN (no profit proxy)
PACK_LISTS = {'take_right': 40, 'take_profit': 20, 'skip_right': 20, 'skip_profit': 10, 'other_units': 20, 'gate2': 10}
PER_CALL = 3
PER_PARAM = 3
JACCARD = 0.8
BLOCK_UNIT_DAYS = 100_000
LOSER_TOP = 10
Z_BINS = [2.0, 3.0, 4.0, 5.0]
QUARTER_SEED = [20261111, 3]
HM1_PACKS = ('traded_pack.json', 'pair_pack.json', 'clock_pack.json', 'perp_pack.json', 'perp_pair_pack.json')
GATE_KINDS = ('gate', 'gate2')
COINS = ['BTC', 'ETH', 'SOL', 'XRP']                                   # never DOGE
SCHEMA_UNITS = 'oracle-heat-hm2-drill-units-1'
SCHEMA_SERIES = 'oracle-heat-hm2-drill-1'
SCHEMA_SUMMARY = 'oracle-heat-hm2-drill-summary-1'
SCHEMA_LEAGUE = 'oracle-heat-hm2-drill-league-1'
SCHEMA_GATES = 'oracle-heat-hm2-drill-gates-1'
SCHEMA_BENCH = 'oracle-heat-hm2-drill-bench-1'
SCHEMA_PARITY = 'oracle-heat-hm2-drill-parity-1'
LIVE_MIN = 0.995

Q5 = ['q1', 'q2', 'q3', 'q4', 'q5']
SINCE_LV = ['1', '2-3', '4-10', '11-30', '31-100', 'over 100', 'none']
ORDER_LV = ['0 (first)', '1', '2', '3-5', '6 or more']
LAST_LV = ['right', 'wrong', 'flat', 'none']
COINCIDE_LV = ['0', '1-2', '3-5', '6-10', '11-20', '21 or more']
AGREE_LV = ['5 or more against', '4-2 against', '1 against to 1 for', '2-4 for', '5 or more for']
BODY_LV = ['-1 to -0.6', '-0.6 to -0.2', '-0.2 to 0.2', '0.2 to 0.6', '0.6 to 1']
OWN_SPECS = ([('OWN:Depth', Q5), ('OWN:Depth.c1', Q5), ('OWN:Depth.c2', Q5), ('OWN:Since', SINCE_LV), ('OWN:Order', ORDER_LV)] +
             [(f'OWN:Last@{H}', LAST_LV) for H in H_ALL] + [('OWN:Coincide', COINCIDE_LV)] + [(f'OWN:Agree@{H}', AGREE_LV) for H in H_ALL] +
             [('OWN:BarRange', Q5), ('OWN:BarVol', Q5), ('OWN:BarBody', BODY_LV), ('OWN:Step', Q5)])
CHART_OWN = ['height', 'span', 'sym', 'slope', 'pre', 'bvol', 'bdist', 'tdist', 'age']        # Part 4's p.<name> columns
CHART_Q = ['height', 'span', 'sym', 'slope', 'pre', 'bvol', 'bdist']                            # quintiles of the pattern's A instances
TDIST_LV, TDIST_EDGES = ['past target', '0-1', '1-2', '2-4', 'over 4'], [0.0, 1.0, 2.0, 4.0]
AGE_LV, AGE_EDGES = ['0', '1-2', '3-5', '6-10', '11-20'], [0, 2, 5, 10]

# packed fields of one instance (pack_weights): 22 counts of 11 bits (4 per float64) and 12 sums of 25 bits (2 per float64)
NW = 12
CT_N, CT_N240, CT_PI, CT_PI240 = 0, 1, 2, 3
CT_OF = np.array([(CT_N240 if hi == 5 else CT_N) if tr < 2 else (CT_PI240 if hi == 5 else CT_PI) for hi in range(6) for tr in range(3)])
HI_OF = np.repeat(np.arange(6), 3)
TR_OF = np.tile(np.arange(3), 6)
SCALE = np.array([50.0, 1.0, 1.0] * 6)                         # right: mean sign -> odds points (50 x (share right - share wrong))
PK = {2: 0, 4: 1, 5: 2}                                        # horizon index -> take / cut field (15, 60, 240)
REC = ['level', 'z', 'lift_A', 't_A', 't_day_A', 't_week_A', 'G_day_A', 'G_week_A', 'n_A', 'days_A', 'weeks_A', 'rest_n_A', 'rest_days_A',
       'mean_A', 'mean_rest_A', 'right_A', 'wrong_A', 'week_weaker_A', 'n_B', 'days_B', 'weeks_B', 'rest_n_B', 'rest_days_B', 'lift_B', 't_B',
       't_day_B', 't_week_B', 'mean_B', 'mean_rest_B', 'right_B', 'wrong_B', 'week_weaker_B', 'Ls', 'take_A', 'cut_A', 'take_B', 'cut_B', 'specific_A']
RI = {k: i for i, k in enumerate(REC)}
LREC = ['level', 'score', 'ratio_A', 'ratio_B', 'bad_A', 'good_A', 'bad_B', 'good_B', 't_A', 'n_A']
LI = {k: i for i, k in enumerate(LREC)}


def _log_none(*a, **k):
    pass


_clean = hm._clean
_refuse_doge = hm._refuse_doge
_rss_mb = hm._rss_mb


def _crc(key: str) -> int:
    return zlib.crc32(str(key).encode()) & 0xFFFFFFFF


def _dump(obj, path: str, gz: bool = False, indent=None) -> str:
    op = gzip.open if gz else open
    with op(path, 'wt') as f:
        json.dump(_clean(obj), f, allow_nan=False, indent=indent)
    return path


def _read_json(p: str):
    if not p or not os.path.isfile(p):
        return None
    op = gzip.open if p.endswith('.gz') else open
    with op(p, 'rt') as f:
        return json.load(f)


def _fork_map(fn, items, procs: int, done: list = None) -> list:
    """(Pre-run audit W3) heat._pmap for the drill, failing fast: fork workers (they inherit _D and heat._W as under
    multiprocessing.Pool) through concurrent.futures.ProcessPoolExecutor, results in the order of items. A worker
    that dies (an OOM kill) raises BrokenProcessPool at once instead of hanging Pool.map until the job's time limit.
    Serial when procs <= 1 or fewer than 2 items. done: when given, (item, result) of every finished item is appended
    as it finishes, so a caller can keep what was finished before a broken pool."""
    items = list(items)
    if procs <= 1 or len(items) < 2:
        res = []
        for x in items:
            r = fn(x)
            res.append(r)
            if done is not None:
                done.append((x, r))
        return res
    import concurrent.futures as cf
    import multiprocessing as mp
    res = [None] * len(items)
    with cf.ProcessPoolExecutor(min(int(procs), len(items)), mp_context=mp.get_context('fork')) as ex:
        futs = {ex.submit(fn, x): i for i, x in enumerate(items)}
        try:
            for f in cf.as_completed(futs):
                i = futs[f]
                res[i] = f.result()
                if done is not None:
                    done.append((items[i], res[i]))
        except BaseException:
            for f in futs:
                f.cancel()
            raise
    return res


def _write_csv(df: pd.DataFrame, path: str) -> str:
    return hm._write_csv(df, path)


def _tf_name(name: str) -> str:
    m = re.match(r'^(\d+)m:', name)
    return f'{m.group(1)}m' if m else ''


# ============================================================================================================ units
def _hm1_coin(c) -> bool:
    return '~' not in str(c) and 'twin' not in str(c).lower()


def _norm_conds(conds) -> list:
    out = []
    for c in conds or []:
        name, lv = c[0], c[1]
        out.append([str(name), [str(x) for x in (lv if isinstance(lv, (list, tuple)) else [lv])]])
    return out


def _unit(coin, kind, key, tier, src, when=None, conds=None, aliases=(), extra=None) -> dict:
    u = {'id': f'{coin}|{kind}|{key}', 'coin': coin, 'kind': kind, 'key': key, 'tier': int(tier), 'source': [src], 'aliases': sorted(set(aliases))}
    if when is not None:
        u['when'] = when
    if conds is not None:
        u['conds'] = _norm_conds(conds)
    if extra:
        u.update(extra)
    return u


def _pack_count(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return int(round(v)) if math.isfinite(v) else None


def _pack_block(r: dict) -> dict:
    """(Pre-run audit C3) An HM2 pack row's own call at its h, stored on the unit as {'pack': {str(h): {dir,
    onset_dir_A, n_A, n_B}}} (n_A / n_B: the row's onset counts) so the series job can compare the drill's fire rule
    with the pack's (check_pack). A column only: nothing is filtered or flipped by it. {} when the row has no h."""
    if r.get('h') is None:
        return {}
    on = r.get('onset') if isinstance(r.get('onset'), dict) else {}
    od = r.get('onset_dir_A')
    return {'pack': {str(int(r['h'])): {'dir': None if r.get('dir') is None else int(r['dir']), 'onset_dir_A': None if od is None else int(od),
                                        'n_A': _pack_count(on.get('n_A')), 'n_B': _pack_count(on.get('n_B'))}}}


def build_units(direction: str, direction_long: str = '', packs_dir: str = '', hm2_pack=None, coins=COINS, chart: bool = None) -> dict:
    """The unit list per coin (schema oracle-heat-hm2-drill-units-1, with sha256). Tier 1: the calls of the five HM1
    packs (singles of traded_pack and perp_pack as event levels; pair, triple and clock cells of pair_pack and
    clock_pack and the 240-minute rows of perp_pair_pack with their `when` and `conds`); tier 2: the HM2 pack's rows
    (pair / triple: the onset of the joint state; model: a GBM zone); tier 3: every other HM1 event level with a sample
    on both periods, ordered by HM1's A numbers at 15 minutes (A events x odds_A; never a B number). A key listed twice
    runs once (the first place wins); pack aliases are kept. Records the sha256 of hm2_pack.json's non-gate rows.
    Part 4's chart events enter as one family entry, expanded in the series job. Refuses DOGE."""
    from oracle import heat_hm2_league as hl
    _refuse_doge(direction, direction_long, packs_dir, *coins)
    D = []
    for p in (direction, direction_long):
        if p:
            d = pd.read_csv(p, low_memory=False)
            D.append(d)
    D = pd.concat(D, ignore_index=True) if D else pd.DataFrame(columns=['coin', 'kind', 'key', 'h', 'dir', 'n_A', 'n_B', 'odds_A'])
    D = D[D['coin'].map(_hm1_coin)]
    _refuse_doge(*D['coin'].astype(str).unique())
    if 'kind' in D:
        D = D[D['kind'].astype(str) == 'single']
    packs = {}
    for nm in HM1_PACKS:
        pk = _read_json(os.path.join(packs_dir, nm)) if packs_dir else None
        if pk is not None:
            packs[nm] = pk
    pack = _read_json(hm2_pack) if isinstance(hm2_pack, str) else hm2_pack
    out = {'schema': SCHEMA_UNITS, 'coins': {}, 'packs': sorted(packs), 'hm2_pack': bool(pack),
           'hm2_nongate_sha256': hl.non_gate_sha(pack) if pack else None, 'hm2_tier2_sha256': hl.tier2_sha(pack) if pack else None,
           'tier3_order': 'HM1 A numbers at 15 minutes: n_A x odds_A',
           'chart': {'loaded': bool(chart if chart is not None else importlib.util.find_spec('oracle.heat_patterns')),
                     'rule': "Part 4's chart event readings ('every') become units of kind 'chart' in the series job (tier 3; tier 2 if a "
                             "pack holds them), with the engine's sample floors"}}
    for coin in coins:
        _refuse_doge(coin)
        seen = {}

        def put(u):
            k = (u['kind'], u['key'])
            if k in seen:
                v = seen[k]
                v['source'] = sorted(set(v['source']) | set(u['source']))
                v['aliases'] = sorted(set(v['aliases']) | set(u['aliases']))
                if u.get('pack'):                   # an HM2 pack key listed at several h: one pack block per h
                    v['pack'] = {**u['pack'], **v.get('pack', {})}
                return
            seen[k] = u

        for nm in HM1_PACKS:
            pk = packs.get(nm)
            if not pk:
                continue
            for r in pk.get('rows', []):
                if r.get('coin') != coin:
                    continue
                if nm == 'perp_pair_pack.json' and int(r.get('h', 0)) != 240:
                    continue
                if 'when' in r:
                    put(_unit(coin, 'cell', r['key'], 1, nm, when=r['when'], conds=r.get('conds'), aliases=r.get('aliases', [])))
                else:
                    put(_unit(coin, 'level', r['key'], 1, nm, aliases=r.get('aliases', [])))
        if pack:
            for r in pack.get('rows', []):
                if r.get('coin') != coin or r.get('kind') in GATE_KINDS:
                    continue
                pb = _pack_block(r)                     # (pre-run audit C3) the pack's own call, for check_pack
                if r.get('kind') == 'model':
                    put(_unit(coin, 'model', r['key'], 2, 'hm2_pack.json', aliases=r.get('aliases', []), extra=pb))
                else:
                    put(_unit(coin, 'hm2', r['key'], 2, 'hm2_pack.json', conds=r.get('conds'), aliases=r.get('aliases', []),
                              extra={'hm2_kind': r.get('kind'), **pb}))
        x = D[D['coin'] == coin]
        lg = {}
        for r in x.itertuples(index=False):
            lg.setdefault(r.key, {})[str(int(r.h))] = {'dir': int(r.dir), 'n_A': int(r.n_A), 'n_B': int(r.n_B) if r.n_B == r.n_B else None}
        h15 = x[x['h'] == 15]
        score = dict(zip(h15['key'], h15['n_A'].astype(float) * h15['odds_A'].astype(float)))
        keys = sorted(set(x['key']), key=lambda k: (k not in score, -score.get(k, 0.0), k))
        for k in keys:
            put(_unit(coin, 'level', k, 3, 'direction_all'))
        units = list(seen.values())
        for i, u in enumerate(units):
            u['order'] = i
            if u['kind'] == 'level' and u['key'] in lg:
                u['league'] = lg[u['key']]
        out['coins'][coin] = units
    out['sha256'] = hashlib.sha256(json.dumps(_clean(out['coins']), sort_keys=True, allow_nan=False).encode()).hexdigest()
    return out


def quarter_subset(units: list) -> set:
    """The twin fallback's units (fixed now): tier 1 and 2, plus a seeded quarter of tier 3 (the same on every twin).
    (Pre-run audit F2/C6) The quarter depends only on the units file and on unit ids, never on a series' own chart
    units: the seeded permutation runs over the tier 3 units that are not of kind 'chart' (the units file's list, the
    same on the coin and every twin); a chart unit is in the quarter when zlib.crc32(id) % 4 == 0, whatever the
    other chart units of that series are."""
    t3 = [u['id'] for u in units if int(u['tier']) >= 3 and u.get('kind') != 'chart']
    rng = np.random.default_rng(QUARTER_SEED)
    pick = set(np.asarray(t3, dtype=object)[rng.permutation(len(t3))[:int(math.ceil(len(t3) / 4))]]) if t3 else set()
    pick |= {u['id'] for u in units if int(u['tier']) >= 3 and u.get('kind') == 'chart' and zlib.crc32(u['id'].encode()) % 4 == 0}
    return {u['id'] for u in units if int(u['tier']) < 3} | pick


def _find_reading(ctx, name: str):
    if name in ctx.byname:
        return ctx.readings[ctx.byname[name]]
    for att in ('gbm_byname', 'chart_byname', 'extra_readings'):
        d = getattr(ctx, att, None) or {}
        if name in d:
            return d[name]
    return None


def parse_key(ctx, key: str) -> tuple:
    """'<reading>=<label>' -> (reading dict, lv, side) as heat.event_levels defines it (a plain level name: side 0).
    Unknown: KeyError."""
    name, label = key.rsplit('=', 1)
    R = _find_reading(ctx, name)
    if R is None:
        raise KeyError(f'unknown reading {name!r} in {key!r}')
    for lv, side, lab in heat.event_levels(R):
        if lab == label:
            return R, int(lv), int(side)
    if label in R['levels']:
        return R, int(R['levels'].index(label)), 0
    raise KeyError(f'unknown level {label!r} of {name!r}')


def _cond_mask(ctx, conds, rows) -> np.ndarray:
    ok = np.ones(len(rows), bool)
    for name, lvs in conds:
        R = _find_reading(ctx, name)
        if R is None:
            raise KeyError(f'unknown reading {name!r} in a condition')
        want = []
        for x in lvs:
            if x == 'NA':
                continue
            if x not in R['levels']:
                raise KeyError(f'unknown level {x!r} of {name!r}')
            want.append(R['levels'].index(x))
        c = heat.read_state(R, rows)
        ok &= np.isin(c, want) | (('NA' in lvs) & (c < 0))
    return ok


def unit_rows(ctx, unit: dict) -> np.ndarray:
    """Every fire of the unit on the full minute grid (sorted rows). Single: heat.level_events. Pair or triple cell:
    the trigger's rows where every condition holds its level at the last closed bar of its own timeframe. HM2 cell:
    heat_hm2.onset_rows(joint_mask). GBM zone and chart event: level_events of that reading."""
    kind = unit['kind']
    if kind in ('level', 'model', 'chart'):
        R, lv, side = parse_key(ctx, unit['key'])
        rows = heat.level_events(R, lv, side)
    elif kind == 'cell':
        R, lv, side = parse_key(ctx, unit['when'])
        rows = heat.level_events(R, lv, side)
        rows = rows[_cond_mask(ctx, unit['conds'], rows)]
    elif kind == 'hm2':
        for name, _ in unit['conds']:
            if _find_reading(ctx, name) is None:
                raise KeyError(f'unknown reading {name!r}')
        rr = np.arange(ctx.m['n'])
        ok, known = hm.joint_mask(ctx, unit['conds'], rr, with_known=True) if all(n in ctx.byname for n, _ in unit['conds']) else \
            (_cond_mask(ctx, unit['conds'], rr), np.ones(len(rr), bool))
        rows = hm.onset_rows(ok, known)
    else:
        raise KeyError(f'unknown unit kind {kind!r}')
    rows = np.unique(np.asarray(rows, np.int64))
    return rows[(rows >= 0) & (rows < ctx.m['n'])]


def unit_readings(ctx, unit: dict) -> list:
    """The readings a unit is made of (trigger first), as reading dicts."""
    if unit['kind'] in ('level', 'model', 'chart'):
        return [parse_key(ctx, unit['key'])[0]]
    out = []
    if unit['kind'] == 'cell':
        out.append(parse_key(ctx, unit['when'])[0])
    for name, _ in unit.get('conds', []):
        R = _find_reading(ctx, name)
        if R is not None:
            out.append(R)
    return out


def unit_k(ctx, unit: dict) -> int:
    """The unit's own timeframe in minutes: the trigger's (a held 'state' reading samples every 15 minutes); an HM2
    cell's onset is read on its fastest reading's bars."""
    Rs = unit_readings(ctx, unit)
    if not Rs:
        return 1
    if unit['kind'] == 'hm2':
        return int(min(int(R['k']) for R in Rs))
    R = Rs[0]
    return 15 if R.get('state') else int(R['k'])


def _ok240(ctx):
    if getattr(ctx, 'ok240', None) is None:
        a = np.zeros(ctx.m['n'], bool)
        a[ctx.g240.sp['A'].rows] = True
        b = np.zeros(ctx.m['n'], bool)
        b[ctx.g240.sp['B'].rows] = True
        ctx.ok240A, ctx.ok240B, ctx.ok240 = a, b, a | b
    return ctx.ok240


def directions(ctx, rowsA: np.ndarray) -> tuple:
    """The league's rule (review): at each H, d = the sign of (mean sign over all A instances - the base mean sign of
    split A), the 240 grid's base at 240 (instances valid on that grid). An exact 0 or no instance: +1, flagged.
    Returns (d int8 (6,), flag bool (6,), x float (6,): mean sign - base, n (6,))."""
    _ok240(ctx)
    d, fl, xs, ns = np.ones(6, np.int8), np.zeros(6, bool), np.zeros(6), np.zeros(6, np.int64)
    for hi, H in enumerate(H_ALL):
        if H < 240:
            s = ctx.lab[f'sg{H}'][rowsA]
            b = ctx.g.sp['A'].base[H]['msign'] if ctx.g.sp['A'].N else 0.0
        else:
            r4 = rowsA[ctx.ok240A[rowsA]]
            s = ctx.lab240['sg240'][r4]
            b = ctx.g240.sp['A'].base[240]['msign'] if ctx.g240.sp['A'].N else 0.0
        ns[hi] = len(s)
        x = float(s.astype(np.float64).mean()) - b if len(s) else 0.0
        xs[hi] = x
        if x < 0:
            d[hi] = -1
        elif x == 0 or not len(s):
            fl[hi] = True
    return d, fl, xs, ns


def _cap(rA: np.ndarray, key: str) -> np.ndarray:
    if len(rA) <= A_CAP:
        return rA
    rng = np.random.default_rng(_crc(key))
    return rA[np.sort(rng.choice(len(rA), A_CAP, replace=False))]


class Inst:
    """One unit's instances: rows (capped A, then every B), split (0 / 1), the unit's own day axis (day, G distinct
    days, A days first: sd of them), its 7-day blocks per split (dweek, nweek), v240, the directions d (6,), the A
    instances before the cap (rA_all), every fire on the full grid (fires), packed weights W (12, n), own parameter
    codes, the bases a parameter must not share."""


def _finish(ctx, x) -> 'Inst':
    gday = ctx.g.day[x.rows]
    x.day_u, x.day = np.unique(gday, return_inverse=True)
    x.day = x.day.astype(np.int64)
    x.G = int(len(x.day_u))
    dB = ctx.g.sp['B'].d0
    x.sd = int((x.day_u < dB).sum())
    sp = np.where(x.day_u < dB, 0, 1)
    wk = np.where(sp == 0, (x.day_u - ctx.g.sp['A'].d0) // WEEK, (x.day_u - dB) // WEEK) + sp * 10 ** 6
    _, x.dweek = np.unique(wk, return_inverse=True)
    x.dweek = x.dweek.astype(np.int64)
    x.nweek = int(x.dweek.max() + 1) if x.G else 0
    x.v240 = _ok240(ctx)[x.rows]
    x.nA = int((x.split == 0).sum())
    return x


def split_instances(ctx, unit: dict, rows: np.ndarray, d=None) -> Inst:
    """rowsA_all and rowsB (g.in_split), the 240 validity, rowsA capped at A_CAP by a seeded uniform sample (seed =
    zlib.crc32(key): the same on twins and reruns), the unit's own day axis (A and B on one axis) and its weeks."""
    g = ctx.g
    rA_all = g.in_split(rows, 'A')
    rB = g.in_split(rows, 'B')
    rA = _cap(rA_all, unit['key'])
    x = Inst()
    x.unit, x.fires, x.rA_all = unit, rows, rA_all
    x.rows = np.r_[rA, rB].astype(np.int64)
    x.split = np.r_[np.zeros(len(rA), np.int8), np.ones(len(rB), np.int8)]
    x.capped = bool(len(rA) < len(rA_all))
    if d is None:
        x.d, x.dflag, x.dx, x.dn = directions(ctx, rA_all)
    else:
        x.d, x.dflag, x.dx, x.dn = d
    x.nB_all = int(len(rB))
    return _finish(ctx, x)


def sub_instances(ctx, x: Inst, mask: np.ndarray, extra_bases=()) -> Inst:
    """The unit's instances where `mask` holds (depth 2): the same directions, own codes and weights, its own day axis."""
    y = Inst()
    y.unit, y.fires, y.rA_all = x.unit, x.fires, x.rA_all
    y.rows, y.split = x.rows[mask], x.split[mask]
    y.capped, y.d, y.dflag, y.dx, y.dn = x.capped, x.d, x.dflag, x.dx, x.dn
    y.W = x.W[:, mask]
    y.own = {k: v[mask] for k, v in x.own.items()}
    y.bases = set(x.bases) | set(extra_bases)
    y.k = x.k
    y.nB_all = int((y.split == 1).sum())
    return _finish(ctx, y)


def check_league(units: list, insts: dict, ctx) -> dict:
    """HM1 singles on the real coins: uncapped n_A, n_B and d against the league's direction tables (expected 0
    differences). insts: unit id -> Inst."""
    out = {'checked': 0, 'n_differ': 0, 'd_differ': 0, 'examples': []}
    _ok240(ctx)
    for u in units:
        lg = u.get('league')
        x = insts.get(u['id'])
        if not lg or x is None:
            continue
        for hs, v in lg.items():
            H = int(hs)
            if H not in H_ALL:
                continue
            hi = H_ALL.index(H)
            nA = int(len(x.rA_all)) if H < 240 else int(ctx.ok240A[x.rA_all].sum())
            rB = ctx.g.in_split(x.fires, 'B')
            nB = int(len(rB)) if H < 240 else int(ctx.ok240B[rB].sum())
            out['checked'] += 1
            bad_n = nA != v['n_A'] or (v.get('n_B') is not None and nB != v['n_B'])
            bad_d = int(x.d[hi]) != int(v['dir'])
            out['n_differ'] += bad_n
            out['d_differ'] += bad_d
            if (bad_n or bad_d) and len(out['examples']) < 20:
                out['examples'].append({'id': u['id'], 'h': H, 'n_A': [nA, v['n_A']], 'n_B': [nB, v.get('n_B')], 'dir': [int(x.d[hi]), v['dir']]})
    return out


def check_pack(units: list, insts: dict, ctx) -> dict:
    """(Pre-run audit C3 a/b) HM2 pack calls ('hm2' and 'model' units) on the real coins, modelled on check_league:
    at each pack h, the drill's uncapped A instance count and B instance count against the pack row's onset n_A /
    n_B, and the drill's direction d against the pack row's onset_dir_A (the onset's own A direction; a model row
    has none, so only its counts are compared) and, apart, against the pack row's dir. Informational: it filters,
    flips and stops nothing. 240 is included: HM2 counts the 240 onsets on the same h240() grid the drill's ctx.g240
    is (heat_hm2._full_both: g240.full(g240.in_split(rows, split))), which ctx.ok240A / ok240B select as in
    check_league. insts: unit id -> Inst, or a function unit -> Inst (built when needed, so a series job never holds
    every pack unit's instances at once)."""
    out = {'checked': 0, 'n_A_differ': 0, 'n_B_differ': 0, 'onset_dir_checked': 0, 'onset_dir_differ': 0, 'pack_dir_differ': 0,
           'by_h': {}, 'examples': []}
    _ok240(ctx)
    for u in units:
        pk = u.get('pack')
        if not pk or u.get('kind') not in ('hm2', 'model'):
            continue
        x = insts(u) if callable(insts) else insts.get(u['id'])
        if x is None:
            continue
        rB = ctx.g.in_split(x.fires, 'B')
        for hs, v in sorted(pk.items(), key=lambda kv: int(kv[0])):
            H = int(hs)
            if H not in H_ALL:
                continue
            hi = H_ALL.index(H)
            nA = int(len(x.rA_all)) if H < 240 else int(ctx.ok240A[x.rA_all].sum())
            nB = int(len(rB)) if H < 240 else int(ctx.ok240B[rB].sum())
            d = int(x.d[hi])
            bh = out['by_h'].setdefault(str(H), {'checked': 0, 'n_A_differ': 0, 'n_B_differ': 0, 'onset_dir_differ': 0, 'pack_dir_differ': 0})
            out['checked'] += 1
            bh['checked'] += 1
            bad_a = v.get('n_A') is not None and nA != int(v['n_A'])
            bad_b = v.get('n_B') is not None and nB != int(v['n_B'])
            bad_od = v.get('onset_dir_A') is not None and d != int(v['onset_dir_A'])
            bad_pd = v.get('dir') is not None and d != int(v['dir'])
            out['onset_dir_checked'] += v.get('onset_dir_A') is not None
            for k, b in (('n_A_differ', bad_a), ('n_B_differ', bad_b), ('onset_dir_differ', bad_od), ('pack_dir_differ', bad_pd)):
                out[k] += int(b)
                bh[k] += int(b)
            if (bad_a or bad_b or bad_od) and len(out['examples']) < 10:
                out['examples'].append({'id': u['id'], 'h': H, 'n_A': [nA, v.get('n_A')], 'n_B': [nB, v.get('n_B')], 'dir': [d, v.get('onset_dir_A')],
                                        'pack_dir': v.get('dir')})
    return out


# ========================================================================================================= outcomes
def sigma_1d(m: dict) -> np.ndarray:
    """sd of 1-minute log returns (bps) over the 1,440 minutes ending at each close (cumsums; a forward-filled minute
    and the one after it are left out; NaN with fewer than SIGMA_MIN returns in the window)."""
    c, gap = np.asarray(m['c'], float), np.asarray(m['gap'], bool)
    n = len(c)
    r = np.r_[np.nan, np.diff(np.log(c))]
    bad = gap | np.r_[True, gap[:-1]]
    r[bad] = np.nan
    ok = np.isfinite(r)
    x = np.where(ok, r, 0.0)
    W = 1440

    def roll(a):
        cs = np.r_[0.0, np.cumsum(a)]
        i = np.arange(1, n + 1)
        return cs[i] - cs[np.maximum(i - W, 0)]
    N, S1, S2 = roll(ok.astype(float)), roll(x), roll(x * x)
    with np.errstate(invalid='ignore', divide='ignore'):
        var = (S2 - S1 * S1 / N) / (N - 1)
    sd = np.sqrt(np.maximum(var, 0.0)) * 1e4
    sd[N < SIGMA_MIN] = np.nan
    return sd.astype(np.float32)


def atr4h_bps(m: dict) -> np.ndarray:
    """Wilder ATR14 (talib.ATR, as the bot's atrOf) of completed 4-hour bars aligned to 00/04/08/12/16/20 UTC, in bps of
    that bar's close, known at each minute close (the last completed bar). NaN before 15 bars."""
    import talib
    n = int(m['n'])
    a0 = int(m['t0']) // MIN
    start = (-a0) % 240
    nb_ = (n - start) // 240 if n > start else 0
    out = np.full(n, np.nan, np.float32)
    if nb_ < 15:
        return out
    sl = slice(start, start + nb_ * 240)
    h = np.asarray(m['h'], float)[sl].reshape(nb_, 240).max(1)
    lo = np.asarray(m['l'], float)[sl].reshape(nb_, 240).min(1)
    c = np.asarray(m['c'], float)[sl].reshape(nb_, 240)[:, -1]
    atr = talib.ATR(h, lo, c, 14) / c * 1e4
    rows = np.arange(n)
    j = (rows - start + 1) // 240 - 1
    ok = (rows >= start) & (j >= 0)
    out[ok] = atr[np.minimum(j[ok], nb_ - 1)]
    return out


@nb.njit(cache=True)
def _nb_proxy(o, h, l, c, ok, sig, tick, atr, H, d, perp, tau, pi, pic, kind, jx):
    """The bot's exit on minute closes (review: the FIRST take or cut ends the trade). 1-60: F = C = 2 x cost (at least
    2 price steps), exit at the first close x_j >= F (take) or x_j <= -C (cut), else at x_H; pi = exit - cost, pi_c =
    clip(exit x 40 / (sigma sqrt tau), +-50) - 4.5. 240: no take; the stop C = max(50, 2 x ATR4h) is checked on each
    minute's adverse extreme and filled at the stop, or at the minute's open when it opens beyond it; 25 bps."""
    n = c.shape[0]
    sq = math.sqrt(tau)
    for i in range(n):
        if not ok[i] or i + H >= n:
            continue
        e = o[i + 1]
        if not (e > 0):
            continue
        if perp:
            a = atr[i]
            if not (a == a):
                continue
            C = max(PERP_MIN_STOP, PERP_STOP_ATR * a)
            k = 3
            jj = H
            ex = 0.0
            for j in range(1, H + 1):
                r = i + j
                if j >= 2:
                    xo = d * (o[r] / e - 1.0) * 1e4
                    if xo <= -C:
                        ex = xo
                        k = 2
                        jj = j
                        break
                adv = l[r] if d > 0 else h[r]
                xa = d * (adv / e - 1.0) * 1e4
                if xa <= -C:
                    ex = -C
                    k = 2
                    jj = j
                    break
            if k == 3:
                ex = d * (c[i + H] / e - 1.0) * 1e4
            pi[i] = ex - PERP_RT_BPS
            kind[i] = k
            jx[i] = jj
        else:
            s = sig[i]
            if not (s == s) or s <= 0:
                continue
            cost = KALSHI_RT_C / C_PER_SIGMA * s * sq
            F = max(TAKE_X * cost, MIN_STEPS * tick[i])
            Cc = max(CUT_X * cost, MIN_STEPS * tick[i])
            k = 3
            jj = H
            ex = 0.0
            for j in range(1, H + 1):
                x = d * (c[i + j] / e - 1.0) * 1e4
                if x >= F:
                    ex = x
                    k = 1
                    jj = j
                    break
                if x <= -Cc:
                    ex = x
                    k = 2
                    jj = j
                    break
            if k == 3:
                ex = d * (c[i + H] / e - 1.0) * 1e4
            pi[i] = ex - cost
            fac = C_PER_SIGMA / (s * sq)
            g = ex * fac
            if g > PI_C_CLIP:
                g = PI_C_CLIP
            elif g < -PI_C_CLIP:
                g = -PI_C_CLIP
            pic[i] = g - KALSHI_RT_C
            kind[i] = k
            jx[i] = jj


def proxy_path(o, h, l, c, i: int, H: int, d: int, sigma: float = np.nan, tick: float = 0.0, atr: float = np.nan) -> dict:
    """The proxy of one row on hand-built bars (tests): {'pi', 'pi_c', 'kind', 'j'}."""
    n = len(c)
    arr = lambda a: np.asarray(a, np.float64)
    pi, pic = np.full(n, np.nan), np.full(n, np.nan)
    kind, jx = np.zeros(n, np.int8), np.zeros(n, np.int16)
    ok = np.zeros(n, np.bool_)
    ok[i] = True
    _nb_proxy(arr(o), arr(h), arr(l), arr(c), ok, np.full(n, sigma), np.full(n, tick), np.full(n, atr), int(H), float(d), H == 240,
              float(TAU.get(H, 10)), pi, pic, kind, jx)
    return {'pi': float(pi[i]), 'pi_c': float(pic[i]), 'kind': int(kind[i]), 'j': int(jx[i])}


def proxy_table(ctx) -> dict:
    """Per H and direction (d = +1, -1) on every valid row (the main grid's valid rows at 1-60, the 240 grid's at 240):
    pi (float32 bps after cost), pi_c (cents after cost, 1-60), kind (1 take, 2 cut, 3 time), j (the exit minute); sigma
    and the 4-hour ATR. Computed once per series."""
    m = ctx.m
    n = int(m['n'])
    sig = sigma_1d(m)
    atr = atr4h_bps(m)
    tick = np.asarray(ctx.lab['tick'], np.float64)
    o, h, l, c = (np.asarray(m[x], np.float64) for x in ('o', 'h', 'l', 'c'))
    pt = {'pi': np.full((6, 2, n), np.nan, np.float32), 'pi_c': np.full((5, 2, n), np.nan, np.float32),
          'kind': np.zeros((6, 2, n), np.int8), 'j': np.zeros((6, 2, n), np.int16), 'sigma': sig, 'atr': atr}
    for hi, H in enumerate(H_ALL):
        perp = H == 240
        ok = np.asarray(ctx.lab240['valid'] if perp else ctx.lab['valid'], np.bool_)
        tau = float(TAU.get(H, 10))
        for di, d in enumerate((1.0, -1.0)):
            pi, pic = np.full(n, np.nan), np.full(n, np.nan)
            kind, jx = np.zeros(n, np.int8), np.zeros(n, np.int16)
            _nb_proxy(o, h, l, c, ok, sig.astype(np.float64), tick, atr.astype(np.float64), H, d, perp, tau, pi, pic, kind, jx)
            pt['pi'][hi, di] = pi
            if not perp:
                pt['pi_c'][hi, di] = pic
            pt['kind'][hi, di] = kind
            pt['j'][hi, di] = jx
    return pt


def inst_vals(ctx, x: Inst, pt: dict = None) -> dict:
    """Per instance and horizon, in the unit's direction: y (+1 right / -1 wrong / 0 flat or not valid), ok (valid at
    H), move (bps), best, dip, retL, hold, pok (the profit proxy exists), prof (pi_c at 1-60, pi bps at 240), pi (bps),
    kind, j."""
    pt = pt if pt is not None else ctx.pt
    r = x.rows
    N = len(r)
    V = {k: np.zeros((6, N), t) for k, t in (('y', np.int8), ('ok', bool), ('pok', bool), ('kind', np.int8), ('j', np.int16), ('hold', np.int16))}
    for k in ('move', 'best', 'dip', 'retL', 'prof', 'pi'):
        V[k] = np.full((6, N), np.nan, np.float32)
    for hi, H in enumerate(H_ALL):
        lab = ctx.lab240 if H == 240 else ctx.lab
        d = int(x.d[hi])
        ok = x.v240 if H == 240 else np.ones(N, bool)
        V['ok'][hi] = ok
        V['y'][hi] = np.where(ok, lab[f'sg{H}'][r] * d, 0)
        V['move'][hi] = np.where(ok, lab[f'ret{H}'][r] * d, np.nan)
        V['best'][hi] = np.where(ok, lab[f'up{H}'][r] if d > 0 else -lab[f'dn{H}'][r], np.nan)
        V['dip'][hi] = np.where(ok, lab[f'dipU{H}'][r] if d > 0 else -lab[f'dipD{H}'][r], np.nan)
        V['retL'][hi] = np.where(ok, lab[f'retL{H}'][r] * d, np.nan)
        V['hold'][hi] = np.where(ok, (lab['holdU'] if d > 0 else lab['holdD'])[r], 0)
        di = 0 if d > 0 else 1
        p = pt['pi'][hi, di, r]
        pok = ok & np.isfinite(p)
        V['pok'][hi] = pok
        V['pi'][hi] = np.where(pok, p, np.nan)
        V['prof'][hi] = np.where(pok, pt['pi_c'][hi, di, r] if hi < 5 else p, np.nan)
        V['kind'][hi] = np.where(pok, pt['kind'][hi, di, r], 0)
        V['j'][hi] = np.where(pok, pt['j'][hi, di, r], 0)
    return V


def pack_weights(x: Inst, V: dict) -> tuple:
    """The 22 count fields (n, n240, n with a profit proxy at 1-60 and at 240, right and wrong at 6 H, take and cut at
    15/60/240; 11 bits each, 4 per float64) and the 12 sums (move at 6 H in 0.5 bps steps clipped at +-4,000; profit:
    pi_c in 0.05c steps at 1-60, pi in 0.5 bps steps clipped at +-4,000 at 240; offset to whole numbers; 25 bits, 2 per
    float64): W (12, n). A field is 0 for an instance that has no value there (its count is 0 too). Asserts every
    field's per-day sum below 2^bits and every word below 2^53. Returns (W, clipped count)."""
    N = len(x.rows)
    if not np.array_equal(V['pok'][:5].min(0), V['pok'][:5].max(0)):
        raise SystemExit('pack_weights: the profit proxy exists at some of 1-60 minutes and not at others (one count field holds them)')
    cf = np.zeros((22, N), np.int64)
    cf[0] = 1
    cf[1] = V['ok'][5]
    cf[2] = V['pok'][2]
    cf[3] = V['pok'][5]
    for hi in range(6):
        cf[4 + 2 * hi] = V['y'][hi] > 0
        cf[5 + 2 * hi] = V['y'][hi] < 0
    for hi, k in PK.items():
        cf[16 + 2 * k] = V['pok'][hi] & (V['kind'][hi] == 1)
        cf[17 + 2 * k] = V['pok'][hi] & (V['kind'][hi] == 2)
    sf = np.zeros((12, N), np.int64)
    clipped = 0
    for hi in range(6):
        mv = np.nan_to_num(V['move'][hi].astype(np.float64))
        clipped += int((np.abs(mv) > CLIP).sum())
        sf[hi] = np.where(V['ok'][hi], np.rint(np.clip(mv, -CLIP, CLIP) / Q_MOVE).astype(np.int64) + OFF_M, 0)
        pf = np.nan_to_num(V['prof'][hi].astype(np.float64))
        if hi < 5:
            q = np.rint(np.clip(pf, -PI_C_CLIP - KALSHI_RT_C, PI_C_CLIP - KALSHI_RT_C) / Q_PI_C).astype(np.int64) + OFF_PC
        else:
            clipped += int((np.abs(pf) > CLIP).sum())
            q = np.rint(np.clip(pf, -CLIP, CLIP) / Q_MOVE).astype(np.int64) + OFF_M
        sf[6 + hi] = np.where(V['pok'][hi], q, 0)
    if N:
        per_day = np.bincount(x.day)
        if per_day.max() > M11:
            raise SystemExit(f'pack_weights: {per_day.max()} instances on one day overflow an 11-bit field')
        for f in range(12):
            if np.bincount(x.day, sf[f].astype(np.float64)).max() > M25:
                raise SystemExit('pack_weights: a 25-bit sum overflows on one day')
    W = np.zeros((NW, N))
    for w in range(6):
        for s in range(4):
            f = 4 * w + s
            if f < 22:
                W[w] += cf[f].astype(np.float64) * float(1 << (F11 * s))
    for w in range(6):
        W[6 + w] = sf[2 * w].astype(np.float64) + sf[2 * w + 1].astype(np.float64) * float(1 << F25)
    assert np.all(W < 2.0 ** 53)
    return W, clipped


# ======================================================================================================= parameters
ZONE_AT = np.array([int(round(q * PCT_BINS)) for q in heat.ZONE_Q])     # 4, 20, 180, 196


def pct_code(x, a_mask, zq=None) -> tuple:
    """The 200-bin A-quantile code (uint8: 0..199, PCT_NA where unknown) of a value series and its 199 edges; None when
    A holds fewer than 1,000 values. A value on an edge goes to the side heat.bucket puts it on (below the zone mid:
    the lower bin, else the upper), so zone_of_pct(code) equals the engine's zone code on every bar."""
    x = np.asarray(x, float)
    xa = x[np.asarray(a_mask, bool)]
    xa = xa[np.isfinite(xa)]
    if len(xa) < 1000:
        return None, None
    E = np.quantile(xa, np.arange(1, PCT_BINS) / PCT_BINS)
    zq = np.quantile(xa, heat.ZONE_Q) if zq is None else np.asarray(zq, float)
    lo, hi = np.full(len(E), -np.inf), np.full(len(E), np.inf)          # the zone edges sit exactly at bins 4, 20, 180, 196
    for a, pos in enumerate(ZONE_AT - 1):
        lo[pos:] = np.maximum(lo[pos:], zq[a])
        hi[:pos + 1] = np.minimum(hi[:pos + 1], zq[a])
    E = np.maximum.accumulate(np.clip(E, lo, hi))
    mid = (zq[0] + zq[-1]) / 2
    with np.errstate(invalid='ignore'):
        code = np.where(x < mid, np.searchsorted(E, x, 'left'), np.searchsorted(E, x, 'right'))
    code = np.where(np.isfinite(x), code, PCT_NA).astype(np.uint8)
    return code, E


def zone_of_pct(code) -> np.ndarray:
    c = np.asarray(code).astype(np.int64)
    z = (c[..., None] >= ZONE_AT).sum(-1).astype(np.int8)
    return np.where(c == PCT_NA, -1, z).astype(np.int8)


@contextlib.contextmanager
def capture_raw(store: dict):
    """Wraps heat_xdata.zone (the module global Zoner.zone calls) during heat_hm2.base(): each new value reading's raw
    array becomes its 200-bin code at once (A-only quantiles from the bars before a_hi, NA where stale), so no float
    copy is held (review). Readings made by Zoner.zone_codes (X.O:RSI14, X.O:TakerBuy) have no raw series and keep
    their 5 zones. Restores the global in finally."""
    from oracle import heat_xdata as xd
    orig = xd.zone

    def wrapped(name, x, a_hi, stale=None, typ='hm2', family='', k=1, edges=None):
        R, e = orig(name, x, a_hi, stale, typ, family, k, edges)
        if R is not None and edges is None:
            v = np.array(x, float, copy=True)
            if stale is not None:
                v[np.asarray(stale, bool)] = np.nan
            bar_rows = np.arange(len(v)) * k + k - 1
            code, E = pct_code(v, bar_rows < a_hi, e)
            if code is not None:
                store[name] = (code, int(k), E)
        return R, e
    xd.zone = wrapped
    try:
        yield store
    finally:
        xd.zone = orig


def engine_pct(ctx, names=None, log=_log_none) -> dict:
    """The engine's value series rebuilt as heat.build_readings makes them (heat_vocab.vocabulary on heat.tick_units at
    A's end and heat.resample, one timeframe at a time; the same stale masks), each coded at once into 200 bins from
    split A's bars: {series name: (code, k, edges)}. names: only these series (None: every zone series)."""
    from oracle.heat_vocab import vocabulary
    m, g = ctx.m, ctx.g
    spA = g.sp['A']
    mu = heat.tick_units(m, spA.hi)
    out = {}
    for k in heat.TFS:
        b = heat.resample(mu, k)
        V, C, _ = vocabulary(b)
        del C
        nb_ = len(b['c'])
        gb = m['gap'][:nb_ * k].reshape(nb_, k).any(1)
        stale = pd.Series(gb.astype(np.float32)).rolling(heat.STALE + 1, min_periods=1).max().to_numpy() > 0
        run = pd.Series(gb.astype(np.int64)).groupby(np.cumsum(~gb)).cumsum().to_numpy()
        stale |= pd.Series((run > heat.STALE_LONG[0]).astype(np.float32)).rolling(heat.STALE_LONG[1] + 1, min_periods=1).max().to_numpy() > 0
        bar_rows = np.arange(nb_) * k + k - 1
        inA = (bar_rows >= spA.lo) & (bar_rows < spA.hi)
        for vi in range(len(V)):
            name, typ, zero, x = V[vi]
            V[vi] = None
            full = f'{k}m:{name}'
            if names is not None and full not in names:
                continue
            x = np.asarray(x, float)
            x[stale] = np.nan
            code, E = pct_code(x, inA)
            if code is not None:
                out[full] = (code, int(k), E)
        del V, b
        heat._trim()
        log(f'  pct codes {k}m: {sum(1 for v in out.values() if v[1] == k)} series')
    return out


def raw_pct(ctx, raw: dict) -> dict:
    """Synthetic or captured value series {name: (x on the reading's bar grid, k)} coded with HM2's A rule (bars
    before split A's end)."""
    out = {}
    for name, (x, k) in raw.items():
        bar_rows = np.arange(len(x)) * int(k) + int(k) - 1
        R = ctx.readings[ctx.byname[name]] if name in ctx.byname else None
        zq = R.get('edges') if R is not None else None
        code, E = pct_code(np.asarray(x, float), bar_rows < ctx.g.sp['A'].hi, zq)
        if code is not None:
            out[name] = (code, int(k), E)
    return out


def check_pct(ctx, pct: dict) -> dict:
    """Bucketing each 200-bin code at ZONE_Q must give the reading's zone codes on every bar: the job stops otherwise."""
    bad, checked = [], 0
    for R in ctx.readings:
        if not R.get('zones') or R['name'] not in pct:
            continue
        code, k, _ = pct[R['name']]
        z = zone_of_pct(code)
        n = min(len(z), len(R['codes']))
        checked += 1
        if not np.array_equal(z[:n], np.asarray(R['codes'][:n], np.int8)):
            bad.append(R['name'])
    if bad:
        raise SystemExit(f'pct codes differ from the zone codes on {len(bad)} readings: {bad[:5]}')
    return {'checked': checked, 'series': len(pct)}


class Param:
    """A candidate parameter: a reading (codes on its bar grid, read with heat.read_state) or an own parameter (codes
    per unit at its instances). list: 'main', or 'insample' (GBM.* and OWN:Agree@*: fit on A)."""

    def __init__(self, name, levels, family, k=1, codes=None, base=None, own=False, R=None):
        self.name, self.levels, self.L, self.family, self.k = name, list(levels), len(levels), family, int(k)
        self.codes, self.base, self.own, self.R = codes, base or name, bool(own), R
        self.list = 'insample' if IN_SAMPLE.match(name) else 'main'
        self.fn = _card_name(name, family)


def _card_name(name: str, family: str) -> str:
    """The card a parameter or a unit's reading belongs to: the TA function (HM2's usage-card rule), the candlestick
    pattern, the chart pattern or the data family."""
    from oracle import heat_hm2_learn as hl
    if name.startswith('OWN:'):
        return 'own:' + name.split(':', 1)[1].split('@')[0].split('.')[0]
    if ':CHART.' in name:
        cp = _chart_parts(name)
        return 'chart:' + (cp[2] if cp else name.split(':', 1)[1])
    fn = hl.ta_function(name) if hl.is_ta_name(name) else None
    return fn if fn else f'family:{family}'


def series_params(ctx) -> list:
    """Every parameter of the series, in a fixed order: the engine and HM2 readings (after the copy merge), the chart
    readings (Part 4, when loaded), the GBM readings (in-sample list), then the own parameters."""
    P = []
    for R in ctx.readings:
        P.append(Param(R['name'], R['levels'], hm.family_of(R), R['k'], R['codes'], R.get('base'), R=R))
    for R in getattr(ctx, 'chart', []) or []:
        P.append(Param(R['name'], R['levels'], 'chart', R['k'], R['codes'], R.get('base'), R=R))
    for R in getattr(ctx, 'gbm', []) or []:
        P.append(Param(R['name'], R['levels'], 'model', R['k'], R['codes'], R.get('base'), R=R))
    for name, lv in OWN_SPECS:
        P.append(Param(name, lv, 'own', own=True))
    if getattr(ctx, 'chart_cat', None) is not None:
        for nm in CHART_OWN:
            P.append(Param(f'OWN:chart.{nm}', TDIST_LV if nm == 'tdist' else AGE_LV if nm == 'age' else Q5, 'own', own=True))
    return P


def params_for(ctx, unit: dict) -> list:
    """The parameters that may split a unit: all of series_params except those sharing a base with one of the unit's
    readings (one base: the engine's rule)."""
    bases = {R.get('base', R['name']) for R in unit_readings(ctx, unit)}
    return [p for p in ctx.params if p.own or p.base not in bases]


def load_gbm(ctx, hm2_series: str = '', log=_log_none) -> list:
    """The 10 GBM readings (GBM.TA{H}, GBM.ALL{H}): from <hm2_series>/gbm_codes.npz (t0 and n must equal the grid's), or
    rescored from the stored trees with heat_hm2_learn.score_rows and the trees' own zone edges."""
    out = []
    if not hm2_series:
        return out
    p = os.path.join(hm2_series, 'gbm_codes.npz')
    mk = lambda name, codes: {'name': name, 'k': 1, 'codes': np.asarray(codes, np.int8), 'levels': list(heat.ZONES), 'base': name, 'type': 'gbm',
                              'zones': True, 'family': 'model'}
    if os.path.isfile(p):
        z = np.load(p)
        if int(z['t0']) != int(ctx.m['t0']) or int(z['n']) != int(ctx.m['n']):
            raise SystemExit(f'gbm_codes.npz is of another grid ({int(z["t0"])}, {int(z["n"])})')
        for nm in sorted(k for k in z.files if k.startswith('GBM.')):
            out.append(mk(nm, z[nm]))
        log(f'  GBM readings from gbm_codes.npz: {len(out)}')
        return out
    from oracle import heat_hm2_learn as hl
    td = os.path.join(hm2_series, 'trees')
    for f in sorted(os.listdir(td)) if os.path.isdir(td) else []:
        tj = _read_json(os.path.join(td, f))
        if not tj or 'hm2' not in tj:
            continue
        zn = tj['hm2'].get('zone') or {}
        model, H = f[:-5].split('_h')
        name = zn.get('name') or f'GBM.{model}{H}'
        score = hl.score_rows(ctx, model, tj, np.arange(ctx.m['n']))
        e = zn.get('edges')
        codes = heat.bucket(score, e) if e else np.where(np.isfinite(score), 2, -1).astype(np.int8)
        out.append(mk(name, codes))
    log(f'  GBM readings rescored from the trees: {len(out)}')
    return out


def chart_readings(ctx, log=_log_none) -> dict:
    """Part 4's readings on this series through Part 4's own builder, when oracle.heat_patterns is present:
    series_readings(ctx) -> (readings, catalogue) when it has one (the catalogue: a DataFrame with frame, pattern,
    event_row and the instance's own columns, for chart_own), else pattern_readings(minutes) -> readings (no catalogue:
    the chart units' own shape columns are NA, said in meta). Absent or failing: no chart readings, the reason in meta
    (the rest of the drill runs)."""
    ctx.chart, ctx.chart_byname, ctx.chart_cat = [], {}, None
    try:
        hp = importlib.import_module('oracle.heat_patterns')
    except ImportError:
        return {'loaded': False, 'why': 'oracle.heat_patterns is not present'}
    try:
        if hasattr(hp, 'series_readings'):
            R, cat = hp.series_readings(ctx)
            how = 'series_readings'
        elif hasattr(hp, 'pattern_readings'):
            R, cat = hp.pattern_readings(ctx.m, log=log)[0], None
            how = 'pattern_readings (no catalogue: the chart units\' own columns are NA)'
        else:
            return {'loaded': False, 'why': 'oracle.heat_patterns has neither series_readings nor pattern_readings'}
    except Exception as e:                                            # Part 4's builder failing must not stop the drill
        log(f'  WARNING chart readings failed: {type(e).__name__}: {e}')
        return {'loaded': False, 'why': f'{type(e).__name__}: {e}'}
    ctx.chart = [dict(R_, family=R_.get('family') or 'chart') for R_ in R]
    ctx.chart_byname = {x['name']: x for x in ctx.chart}
    ctx.chart_cat = cat
    log(f'  chart readings: {len(ctx.chart)} ({how})')
    return {'loaded': True, 'how': how, 'readings': len(ctx.chart), 'catalogue_rows': None if cat is None else int(len(cat))}


def _chart_parts(key: str):
    """'60m:CHART.z4.HS=break up' -> ('60m', 'z4', 'HS'); '15m:CHART.K.LMW.HS=...' -> ('15m', 'K', 'LMW.HS'); None for a
    name that is not a chart event reading."""
    m = re.match(r'^(\d+m):CHART\.([^.=]+)\.([^=]+?)(=.*)?$', key)
    if not m or m.group(3).endswith('.state') or '.p.' in f'.{m.group(3)}.' or m.group(3) in ('STRUCT', 'BOS', 'ANY', 'BIAS'):
        return None
    return m.group(1), m.group(2), m.group(3)


def chart_own(cat: pd.DataFrame, tf: str, frame: str, pattern: str, rows: np.ndarray, rowsA: np.ndarray) -> dict:
    """(Part 4 review item 7) A chart unit's own shape columns from Part 4's catalogue, joined by (frame, pattern, event
    row), not from the frame-level p.<name> readings (which can show another pattern's instance on a collision bar).
    The frame matches '<tf>:<frame>', '<tf>.<frame>' or '<frame>' (with a 'tf' column equal to tf when the catalogue
    has one). height, span, sym, slope, pre, bvol, bdist at the quintiles of the pattern's own A instances (the unit's
    A fires, rowsA, uncapped); tdist and age at fixed levels. Returns {OWN:chart.<name>: (codes at rows, edges)}."""
    fr = cat['frame'].astype(str)
    c = cat[fr.isin([f'{tf}:{frame}', f'{tf}.{frame}', frame]) & (cat['pattern'].astype(str) == pattern)]
    if 'tf' in c and fr[c.index].eq(frame).any():
        c = c[(c['tf'].astype(str) == tf) | ~fr[c.index].eq(frame)]
    pos = pd.Series(np.arange(len(c)), index=c['event_row'].to_numpy(np.int64))
    pos = pos[~pos.index.duplicated(keep='first')]
    out = {}
    for nm in CHART_OWN:
        if nm not in c:
            continue
        col = c[nm].to_numpy(float)

        def at(rr):
            idx = pos.reindex(np.asarray(rr, np.int64)).to_numpy()
            v = np.full(len(rr), np.nan)
            got = np.isfinite(idx)
            v[got] = col[idx[got].astype(np.int64)]
            return v
        v = at(rows)
        if nm in CHART_Q:
            va = at(rowsA)
            va = va[np.isfinite(va)]
            if len(va) < 5:
                out[f'OWN:chart.{nm}'] = (np.full(len(rows), -1, np.int8), None)
                continue
            e = np.quantile(va, [0.2, 0.4, 0.6, 0.8])
            out[f'OWN:chart.{nm}'] = (np.where(np.isfinite(v), np.searchsorted(e, v, 'right'), -1).astype(np.int8), [float(q) for q in e])
        else:
            if nm == 'tdist':                                         # past target (< 0), 0-1, 1-2, 2-4, over 4
                code = np.where(v < 0, 0, np.searchsorted(np.asarray(TDIST_EDGES[1:], float), v, 'left') + 1)
            else:                                                     # age in bars: 0, 1-2, 3-5, 6-10, 11-20 (and over)
                code = np.searchsorted(np.asarray(AGE_EDGES, float), v, 'left')
            out[f'OWN:chart.{nm}'] = (np.where(np.isfinite(v), np.minimum(code, 4), -1).astype(np.int8), None)
    return out


class FireIndex:
    """Over every HM1 event level of the coin: count (int16, how many fire at each row) and dirsum (int16 (6, n), the
    sum of their A directions), the directions computed in this job (the same on a twin); levels: (reading index, lv,
    side) -> {'key', 'd', 'flag', 'n_A'}."""


def _is_hm1(R: dict) -> bool:
    from oracle import heat_hm2_learn as hl
    return hl.is_ta(R)


def fire_index(ctx, log=_log_none) -> FireIndex:
    n = int(ctx.m['n'])
    fi = FireIndex()
    fi.count = np.zeros(n, np.int16)
    fi.dirsum = np.zeros((6, n), np.int16)
    fi.levels = {}
    for j, R in enumerate(ctx.readings):
        if not _is_hm1(R):
            continue
        for lv, side, label in heat.event_levels(R):
            rows = heat.level_events(R, lv, side)
            rows = rows[(rows >= 0) & (rows < n)]
            d, fl, _, ns = directions(ctx, ctx.g.in_split(rows, 'A'))
            fi.count[rows] += 1
            fi.dirsum[:, rows] += d[:, None].astype(np.int16)
            fi.levels[(j, int(lv), int(side))] = {'key': f'{R["name"]}={label}', 'd': d, 'flag': fl, 'n_A': int(ns[0])}
    log(f'  fire index: {len(fi.levels):,} HM1 event levels')
    return fi


def _bars(ctx, k: int) -> dict:
    """The own timeframe's bars (tick units at A's end, heat.resample): range / ATR14 (talib, Wilder), volume / the
    mean of the 20 bars before, body (close - open) / range."""
    import talib
    cache = ctx.__dict__.setdefault('_drill_bars', {})
    if k in cache:
        return cache[k]
    if '_drill_mu' not in ctx.__dict__:
        ctx._drill_mu = heat.tick_units(ctx.m, ctx.g.sp['A'].hi)
    b = heat.resample(ctx._drill_mu, k)
    o, h, l, c, v = (np.asarray(b[x], float) for x in ('o', 'h', 'l', 'c', 'v'))
    rng = h - l
    with np.errstate(invalid='ignore', divide='ignore'):
        atr = talib.ATR(h, l, c, 14)
        ra = rng / atr
        prev = pd.Series(v).rolling(20, min_periods=20).mean().shift(1).to_numpy()
        vr = v / prev
        body = np.where(rng > 0, (c - o) / rng, np.nan)
    out = {'range': ra, 'vol': vr, 'body': body}
    cache[k] = out
    return out


def _q5_code(vals: np.ndarray, valsA: np.ndarray) -> tuple:
    va = valsA[np.isfinite(valsA)]
    if len(va) < 5:
        return np.full(len(vals), -1, np.int8), None
    e = np.quantile(va, [0.2, 0.4, 0.6, 0.8])
    return np.where(np.isfinite(vals), np.searchsorted(e, vals, 'right'), -1).astype(np.int8), [float(q) for q in e]


def _at_bars(arr: np.ndarray, rows: np.ndarray, k: int) -> np.ndarray:
    bi = (rows + 1) // k - 1
    out = np.full(len(rows), np.nan)
    ok = (bi >= 0) & (bi < len(arr))
    out[ok] = arr[bi[ok]]
    return out


def _self_fire(ctx, x: Inst) -> tuple:
    """The unit's own contribution to the fire index (its own event level and its aliases': the trigger of a cell)."""
    fi = ctx.fi
    keys = []
    u = x.unit
    if u['kind'] in ('level', 'cell'):
        keys.append(u['key'] if u['kind'] == 'level' else u['when'])
        if u['kind'] == 'level':
            keys += list(u.get('aliases', []))
    seen, c, ds = set(), 0, np.zeros(6, np.int64)
    for k in keys:
        try:
            R, lv, side = parse_key(ctx, k)
        except KeyError:
            continue
        j = ctx.byname.get(R['name'])
        t = (j, lv, side)
        if j is None or t in seen or t not in fi.levels:
            continue
        seen.add(t)
        c += 1
        ds += fi.levels[t]['d'].astype(np.int64)
    return c, ds


def own_params(ctx, x: Inst) -> tuple:
    """The unit's own instance features at its instances: {name: int8 codes (-1 = NA)} and {name: edges} (A quintile
    edges from every A instance, for the live meta). OWN:Depth (the 200-bin code of the unit's own series at the event
    bar; .c1/.c2 for a cell's value conditions), Since and Order (bars of the own timeframe; every fire at or before the
    row), Last@H (the previous fire whose window had closed, r + H <= i, within 1,440 minutes), Coincide and Agree@H
    (the fire index less the unit's own fire), BarRange, BarVol, BarBody (the own timeframe's event bar), Step."""
    u, fires, rows, k = x.unit, x.fires, x.rows, x.k
    nA_all = x.rA_all
    codes, edges = {}, {}
    fb = (fires + 1) // k - 1

    def at(rr):
        pos = np.searchsorted(fires, rr)
        return pos, (rr + 1) // k - 1
    # Since / Order: on every fire at or before the row
    for rr, tgt in ((rows, 'x'),):
        pos, ib = at(rr)
        prev = pos - 1
        since = np.where(prev >= 0, ib - fb[np.maximum(prev, 0)], -1)
        c = np.searchsorted(np.asarray(SINCE_EDGES), since, 'left')
        codes['OWN:Since'] = np.where(prev >= 0, c, 6).astype(np.int8)
        lo = np.searchsorted(fb, ib - ORDER_W, 'left')
        cnt = pos - lo
        codes['OWN:Order'] = np.searchsorted(np.asarray(ORDER_EDGES), cnt, 'left').astype(np.int8)
    # Last@H
    for hi, H in enumerate(H_ALL):
        lab = ctx.lab240 if H == 240 else ctx.lab
        vf = fires[np.asarray(lab['valid'], bool)[fires]]
        j = np.searchsorted(vf, rows - H, 'right') - 1
        r = vf[np.maximum(j, 0)] if len(vf) else np.zeros(len(rows), np.int64)
        ok = (j >= 0) & (rows - r <= LAST_WINDOW) if len(vf) else np.zeros(len(rows), bool)
        y = lab[f'sg{H}'][r] * int(x.d[hi]) if len(vf) else np.zeros(len(rows))
        codes[f'OWN:Last@{H}'] = np.where(ok, np.where(y > 0, 0, np.where(y < 0, 1, 2)), 3).astype(np.int8)
    # Coincide / Agree
    sc, sd_ = _self_fire(ctx, x)
    cnt = ctx.fi.count[rows].astype(np.int64) - sc
    codes['OWN:Coincide'] = np.searchsorted(np.asarray(COINCIDE_EDGES), np.maximum(cnt, 0), 'left').astype(np.int8)
    for hi, H in enumerate(H_ALL):
        a = (ctx.fi.dirsum[hi, rows].astype(np.int64) - sd_[hi]) * int(x.d[hi])
        codes[f'OWN:Agree@{H}'] = np.searchsorted(np.asarray(AGREE_EDGES), a, 'left').astype(np.int8)
    # the bar
    bars = _bars(ctx, k)
    for nm, key in (('OWN:BarRange', 'range'), ('OWN:BarVol', 'vol')):
        codes[nm], edges[nm] = _q5_code(_at_bars(bars[key], rows, k), _at_bars(bars[key], nA_all, k))
    body = _at_bars(bars['body'], rows, k)
    codes['OWN:BarBody'] = np.where(np.isfinite(body), np.searchsorted(np.asarray(BODY_EDGES), body, 'left'), -1).astype(np.int8)
    tick = np.asarray(ctx.lab['tick'], float)
    codes['OWN:Step'], edges['OWN:Step'] = _q5_code(tick[rows], tick[nA_all])
    # Depth: the unit's own value series
    vals = []                                                         # trigger, then the conditions in order
    for R in unit_readings(ctx, u):
        b = R.get('base', R['name'])
        vals.append(b if b in ctx.pct and (R.get('zones') or R['levels'] == ['below 0', 'above 0']) else None)
    names = ['OWN:Depth', 'OWN:Depth.c1', 'OWN:Depth.c2']
    for i, nm in enumerate(names):
        b = vals[i] if i < len(vals) else None
        if b is None:
            codes[nm] = np.full(len(rows), -1, np.int8)
            continue
        code, kk, _ = ctx.pct[b]
        f = lambda rr: np.where(_at_bars(code.astype(np.float64), rr, kk) == PCT_NA, np.nan, _at_bars(code.astype(np.float64), rr, kk))
        codes[nm], edges[nm] = _q5_code(f(rows), f(nA_all))
    # chart units: their own shape columns from Part 4's catalogue
    cat = getattr(ctx, 'chart_cat', None)
    if cat is not None:
        for nm in CHART_OWN:
            codes[f'OWN:chart.{nm}'] = np.full(len(rows), -1, np.int8)
        cp = _chart_parts(u['key']) if u['kind'] == 'chart' else None
        if cp:
            for nm, (cd, e) in chart_own(cat, *cp, rows, nA_all).items():
                codes[nm] = cd
                edges[nm] = e
    return codes, edges


# ========================================================================================================== the scan
@nb.njit(cache=True)
def _q2(Vl, Cl, T, N, A1, A2, A3, a, b, n, rest, j0, j1):
    """sum over clusters of psi^2, psi = the level's own part minus the rest's part (heat.Grid.cells' lift), written as
    sums of products: the level's terms over its occupied clusters, the rest's from the unit sums A1, A2, A3."""
    own2 = 0.0
    cross = 0.0
    corr = 0.0
    G = 0
    for j in range(j0, j1):
        c = Cl[j]
        if c <= 0:
            continue
        v = Vl[j]
        G += 1
        own = (v - a * c) / n
        D = T[j] - b * N[j]
        e = v - b * c
        oth = (D - e) / rest
        own2 += own * own
        cross += own * oth
        corr += -2.0 * D * e + e * e
    oth2 = (A1 - 2.0 * b * A2 + b * b * A3 + corr) / (rest * rest)
    q = own2 - 2.0 * cross + oth2
    if q < 0.0:
        q = 0.0
    return q, G


@nb.njit(cache=True)
def _nb_cells(bins, off, G, L, dayoff, sd, dweek, cnt, days, rdays, weeks, rw, tc, mu, mur, sed, sew):
    """Per unit, known level and split: the counts, days, rest days and weeks of the four count types; right / wrong at
    6 H; take / cut at 15, 60, 240; and for each of the 18 lifts (3 tracks x 6 H) the level's mean, the rest's mean and
    the clustered variance of the lift by day and by 7-day block. NA (level L) sits outside the rest."""
    U = G.shape[0]
    for u in range(U):
        g = G[u]
        b0 = off[u]
        do = dayoff[u]
        CF = np.zeros((22, L, g))
        SF = np.zeros((12, L, g))
        for l in range(L):
            for j in range(g):
                idx = b0 + l * g + j
                for w in range(6):
                    v = np.int64(bins[w, idx])
                    if v == 0:
                        continue
                    for s in range(4):
                        f = 4 * w + s
                        if f < 22:
                            CF[f, l, j] = (v >> (11 * s)) & 2047
                for w in range(6):
                    v = np.int64(bins[6 + w, idx])
                    if v == 0:
                        continue
                    SF[2 * w, l, j] = v & 33554431
                    SF[2 * w + 1, l, j] = (v >> 25) & 33554431
        wk = dweek[do:do + g]
        Vd = np.zeros((L, g))
        Cd = np.zeros((L, g))
        Tj = np.zeros(g)
        Nj = np.zeros(g)
        for s in range(2):
            j0 = 0 if s == 0 else sd[u]
            j1 = sd[u] if s == 0 else g
            if j1 <= j0:
                continue
            w0 = wk[j0]
            nw = wk[j1 - 1] + 1 - w0
            Vw = np.zeros((L, nw))
            Cw = np.zeros((L, nw))
            Tw = np.zeros(nw)
            Nw = np.zeros(nw)
            for ct in range(4):
                for j in range(j0, j1):
                    Nj[j] = 0.0
                    for l in range(L):
                        Nj[j] += CF[ct, l, j]
                for l in range(L):
                    c = 0.0
                    dd = 0
                    rd = 0
                    for w in range(nw):
                        Cw[0, w] = 0.0
                    for j in range(j0, j1):
                        x = CF[ct, l, j]
                        c += x
                        if x > 0:
                            dd += 1
                            Cw[0, wk[j] - w0] = 1.0
                        if Nj[j] - x > 0:
                            rd += 1
                    nwl = 0
                    for w in range(nw):
                        if Cw[0, w] > 0:
                            nwl += 1
                    cnt[u, l, s, ct] = c
                    days[u, l, s, ct] = dd
                    rdays[u, l, s, ct] = rd
                    weeks[u, l, s, ct] = nwl
            for l in range(L):
                for hi in range(6):
                    a = 0.0
                    b = 0.0
                    for j in range(j0, j1):
                        a += CF[4 + 2 * hi, l, j]
                        b += CF[5 + 2 * hi, l, j]
                    rw[u, l, s, hi, 0] = a
                    rw[u, l, s, hi, 1] = b
                for k in range(3):
                    a = 0.0
                    b = 0.0
                    for j in range(j0, j1):
                        a += CF[16 + 2 * k, l, j]
                        b += CF[17 + 2 * k, l, j]
                    tc[u, l, s, k, 0] = a
                    tc[u, l, s, k, 1] = b
            for hi in range(6):
                for tr in range(3):
                    li = hi * 3 + tr
                    if tr < 2:
                        ct = 1 if hi == 5 else 0
                    else:
                        ct = 3 if hi == 5 else 2
                    Ttot = 0.0
                    Ntot = 0.0
                    for l in range(L):
                        for j in range(j0, j1):
                            c = CF[ct, l, j]
                            Cd[l, j] = c
                            if tr == 0:
                                v = CF[4 + 2 * hi, l, j] - CF[5 + 2 * hi, l, j]
                            elif tr == 1:
                                v = (SF[hi, l, j] - 8000.0 * c) * 0.5
                            elif hi < 5:
                                v = (SF[6 + hi, l, j] - 1090.0 * c) * 0.05
                            else:
                                v = (SF[11, l, j] - 8000.0 * c) * 0.5
                            Vd[l, j] = v
                            Ttot += v
                            Ntot += c
                    if Ntot <= 0:
                        for l in range(L):
                            mu[u, l, s, li] = np.nan
                            mur[u, l, s, li] = np.nan
                            sed[u, l, s, li] = np.nan
                            sew[u, l, s, li] = np.nan
                        continue
                    m = Ttot / Ntot
                    for w in range(nw):
                        Tw[w] = 0.0
                        Nw[w] = 0.0
                        for l in range(L):
                            Vw[l, w] = 0.0
                            Cw[l, w] = 0.0
                    A1 = 0.0
                    A2 = 0.0
                    A3 = 0.0
                    for j in range(j0, j1):
                        Tj[j] = 0.0
                        Nj[j] = 0.0
                        w = wk[j] - w0
                        for l in range(L):
                            v = Vd[l, j] - m * Cd[l, j]
                            Vd[l, j] = v
                            Tj[j] += v
                            Nj[j] += Cd[l, j]
                            Vw[l, w] += v
                            Cw[l, w] += Cd[l, j]
                        Tw[w] += Tj[j]
                        Nw[w] += Nj[j]
                        A1 += Tj[j] * Tj[j]
                        A2 += Tj[j] * Nj[j]
                        A3 += Nj[j] * Nj[j]
                    W1 = 0.0
                    W2 = 0.0
                    W3 = 0.0
                    for w in range(nw):
                        W1 += Tw[w] * Tw[w]
                        W2 += Tw[w] * Nw[w]
                        W3 += Nw[w] * Nw[w]
                    for l in range(L):
                        n = 0.0
                        S = 0.0
                        for j in range(j0, j1):
                            n += Cd[l, j]
                            S += Vd[l, j]
                        rest = Ntot - n
                        if n <= 0 or rest <= 0:
                            mu[u, l, s, li] = (S / n + m) if n > 0 else np.nan
                            mur[u, l, s, li] = np.nan
                            sed[u, l, s, li] = np.nan
                            sew[u, l, s, li] = np.nan
                            continue
                        a = S / n
                        b = -S / rest                        # the centred total is 0: the rest's sum is -S
                        mu[u, l, s, li] = a + m
                        mur[u, l, s, li] = b + m
                        q, Gc = _q2(Vd[l], Cd[l], Tj, Nj, A1, A2, A3, a, b, n, rest, j0, j1)
                        sed[u, l, s, li] = math.sqrt(q * Gc / (Gc - 1)) if Gc > 1 else np.nan
                        q, Gc = _q2(Vw[l], Cw[l], Tw, Nw, W1, W2, W3, a, b, n, rest, 0, nw)
                        sew[u, l, s, li] = math.sqrt(q * Gc / (Gc - 1)) if Gc > 1 else np.nan


def cells_direct(V: np.ndarray, C: np.ndarray, cl: np.ndarray) -> dict:
    """The reference (tests): per level of V, C ((L, D) per-day value sums and counts over known levels) the lift of
    the level over the rest and its clustered variance in the direct per-cluster form (cl: the cluster of each day)."""
    L, D = V.shape
    K = int(cl.max()) + 1
    Vk = np.zeros((L, K))
    Ck = np.zeros((L, K))
    for j in range(D):
        Vk[:, cl[j]] += V[:, j]
        Ck[:, cl[j]] += C[:, j]
    out = {'mu': np.full(L, np.nan), 'mur': np.full(L, np.nan), 'se': np.full(L, np.nan), 'G': np.zeros(L, int)}
    Tk, Nk = Vk.sum(0), Ck.sum(0)
    for l in range(L):
        n, S = Ck[l].sum(), Vk[l].sum()
        rest, Sr = Nk.sum() - n, Tk.sum() - S
        if n <= 0 or rest <= 0:
            continue
        mu, mur = S / n, Sr / rest
        own = (Vk[l] - mu * Ck[l]) / n
        oth = ((Tk - Vk[l]) - mur * (Nk - Ck[l])) / rest
        psi = own - oth
        G = int((Ck[l] > 0).sum())
        out['mu'][l], out['mur'][l], out['G'][l] = mu, mur, G
        out['se'][l] = math.sqrt((psi ** 2).sum() * G / (G - 1)) if G > 1 else np.nan
    return out


def block_bins(L: int, unit_days: int) -> int:
    """Bins of one bincount for a parameter of L levels on a block of unit_days (NA has its own bin)."""
    return int((L + 1) * unit_days)


def z_adj(t_day, G_day, t_wk, G_wk, L) -> tuple:
    """The smaller |t| of day and week (review), its two-sided p from the t distribution with that clustering's count
    - 1 degrees of freedom, Bonferroni over the parameter's L levels with a sample, back to a normal quantile.
    Returns (z, t of the weaker clustering, its count, week_is_weaker)."""
    from scipy.special import ndtri_exp
    from scipy.stats import t as tdist
    t_day, t_wk = np.asarray(t_day, float), np.asarray(t_wk, float)
    ad, aw = np.abs(t_day), np.abs(t_wk)
    wk = aw < ad
    t = np.where(wk, t_wk, t_day)
    G = np.where(wk, np.asarray(G_wk, float), np.asarray(G_day, float))
    bad = ~(np.isfinite(ad) & np.isfinite(aw)) | (G < 2)
    t = np.where(bad, np.nan, t)
    df = np.maximum(G - 1, 1)
    with np.errstate(all='ignore'):
        logp = np.log(2.0) + tdist.logsf(np.abs(np.nan_to_num(t)), df)
        logp = np.minimum(0.0, logp + np.log(np.maximum(np.asarray(L, float), 1.0)))
        z = -ndtri_exp(logp - np.log(2.0))
    z = np.where(bad, np.nan, z)
    return z, t, G, wk


class TopK:
    """The best K offers per cell of `shape` (ranked by z; an earlier parameter keeps its place on a tie)."""

    def __init__(self, shape, K, nf):
        self.z = np.full(tuple(shape) + (K,), -np.inf)
        self.p = np.full(tuple(shape) + (K,), -1, np.int32)
        self.r = np.full(tuple(shape) + (K, nf), np.nan, np.float32)

    def offer(self, z, pid, rec):
        z = np.where(np.isfinite(z), z, -np.inf)
        slot = self.z.argmin(-1)
        cur = np.take_along_axis(self.z, slot[..., None], -1)[..., 0]
        upd = z > cur
        if not upd.any():
            return
        ix = np.nonzero(upd)
        s = slot[ix]
        self.z[ix + (s,)] = z[ix]
        self.p[ix + (s,)] = pid if np.isscalar(pid) else np.asarray(pid)[ix]
        self.r[ix + (s,)] = rec[ix]

    def order(self):
        return np.lexsort((self.p, -self.z), axis=-1)


class SummaryCounts:
    """Mergeable persistence counts over every parameter with a ranked level: per (h, track, mode, list, family, tier,
    specific_A bin, weaker clustering, fallback subset, z_adj bin): [ranked, kept, not thin, kept and not thin, t_B >=
    2]. Exact across blocks, parts and series of one kind."""
    FIELDS = ['ranked', 'kept', 'nonthin', 'kept_nonthin', 'tb2']
    KEY = ['h', 'track', 'mode', 'list', 'family', 'tier', 'spec', 'weaker', 'subset', 'zbin']

    def __init__(self):
        self.c = {}

    def add_arrays(self, keys: np.ndarray, vals: np.ndarray, fam: str, lst: str):
        """keys: int (n, 8) of (h, track, mode, tier, spec, weaker, subset, zbin); vals (n, 5)."""
        if not len(keys):
            return
        u, inv = np.unique(keys, axis=0, return_inverse=True)
        s = np.zeros((len(u), vals.shape[1]), np.int64)
        np.add.at(s, inv.ravel(), vals.astype(np.int64))
        for k, v in zip(map(tuple, u.tolist()), s.tolist()):
            kk = (k[0], k[1], k[2], lst, fam, k[3], k[4], k[5], k[6], k[7])
            o = self.c.get(kk)
            self.c[kk] = v if o is None else [a + b for a, b in zip(o, v)]

    def merge(self, o: 'SummaryCounts') -> 'SummaryCounts':
        for k, v in o.c.items():
            a = self.c.get(k)
            self.c[k] = list(v) if a is None else [x + y for x, y in zip(a, v)]
        return self

    def to_json(self) -> dict:
        return {'schema': SCHEMA_SUMMARY, 'key': self.KEY, 'fields': self.FIELDS, 'rows': [list(k) + list(v) for k, v in sorted(self.c.items())]}

    @classmethod
    def from_json(cls, j: dict) -> 'SummaryCounts':
        s = cls()
        nk = len(cls.KEY)
        for r in j.get('rows', []):
            s.c[tuple(r[:nk])] = list(r[nk:])
        return s

    def frame(self) -> pd.DataFrame:
        if not self.c:
            return pd.DataFrame(columns=self.KEY + self.FIELDS)
        return pd.DataFrame([list(k) + list(v) for k, v in self.c.items()], columns=self.KEY + self.FIELDS)


class ShardWriter:
    """Per (unit, H, parameter, track): the take and the skip level with A and B lift, t, z_adj and n (float16; int32
    unit and parameter ids), one drill_NNNNN.npz per block. Real coins only; a no-op on twins."""
    FIELDS = ['level', 'z', 'lift_A', 't_A', 'n_A', 'lift_B', 't_B', 'n_B']

    def __init__(self, out_dir: str, enabled: bool):
        self.dir, self.enabled = out_dir, bool(enabled and out_dir)
        self.buf, self.pid = [], []
        if self.enabled:
            os.makedirs(out_dir, exist_ok=True)

    def add(self, pid: int, rec: np.ndarray):
        if self.enabled:
            idx = [RI[f] for f in self.FIELDS]
            self.buf.append(rec[..., idx].astype(np.float16))
            self.pid.append(pid)

    def flush(self, bid: int, unit_ids: list, params: list) -> int:
        if not self.enabled or not self.buf:
            self.buf, self.pid = [], []
            return 0
        p = os.path.join(self.dir, f'drill_{bid:05d}.npz')
        np.savez(p, rec=np.stack(self.buf), pid=np.asarray(self.pid, np.int32), units=np.array(unit_ids), params=np.array([q.name for q in params]),
                 fields=np.array(self.FIELDS), horizons=np.array(H_ALL), tracks=np.array(TRACKS), modes=np.array(MODES))
        self.buf, self.pid = [], []
        return os.path.getsize(p)


class ScanOut:
    pass


def _param_codes(p: Param, rows: np.ndarray, own: dict, bi_cache: dict) -> np.ndarray:
    if p.own:
        return own.get(p.name)
    k = p.k
    if k not in bi_cache:
        bi_cache[k] = (rows + 1) // k - 1
    bi = bi_cache[k]
    out = np.full(len(rows), -1, np.int64)
    ok = (bi >= 0) & (bi < len(p.codes))
    out[ok] = p.codes[bi[ok]]
    return out


def _spec_rows(ctx) -> list:
    """The rows the all-minutes effects read, once per series: per split (HM2's A entries; every valid B row) and H, the
    rows (the 240 grid's valid ones at 240), the four value series (sign, move, profit of an up call, of a down call;
    0 where not finite) and their finite masks (an identical mask is shared; None when every value is finite). Freed
    after specific_all (the effects are cached per parameter)."""
    if getattr(ctx, '_drill_specrows', None) is not None:
        return ctx._drill_specrows
    _ok240(ctx)
    rowsA = ctx.rows[ctx.split == 0] if getattr(ctx, 'rows', None) is not None else ctx.g.sp['A'].rows[::hm.A_STRIDE]
    out = []
    for si, rows in ((0, rowsA), (1, ctx.g.sp['B'].rows)):
        per = []
        for hi, H in enumerate(H_ALL):
            sel = (ctx.ok240A if si == 0 else ctx.ok240B)[rows] if H == 240 else None
            r = rows if sel is None else rows[sel]
            lab = ctx.lab240 if H == 240 else ctx.lab
            pk = 'pi_c' if hi < 5 else 'pi'
            raw = [lab[f'sg{H}'][r].astype(np.float64), lab[f'ret{H}'][r].astype(np.float64), ctx.pt[pk][hi, 0, r].astype(np.float64),
                   ctx.pt[pk][hi, 1, r].astype(np.float64)]
            masks, mi = [], []
            for v in raw:
                f = np.isfinite(v)
                j = next((k for k, m in enumerate(masks) if np.array_equal(m, f)), None)
                if j is None:
                    masks.append(f)
                    j = len(masks) - 1
                mi.append(j)
            vals = np.stack([np.where(np.isfinite(v), v, 0.0) for v in raw])
            per.append({'sel': sel, 'vals': vals, 'masks': [None if m.all() else m.astype(np.float64) for m in masks], 'mi': mi})
        out.append((rows, per))
    ctx._drill_specrows = out
    return out


def _spec(ctx, p: Param) -> np.ndarray:
    """(review) The reading's own effect by level over its other known levels on every valid B row of the coin (and
    on HM2's A entries for specific_A), per H, for the sign (right), the move and the profit proxy (pi_c / pi) of
    either direction: float (2, L, 6, 4) in raw units (mean sign, bps, cents / bps), NaN without a sample. Cached."""
    cache = ctx.__dict__.setdefault('_drill_spec', {})
    if p.name in cache:
        return cache[p.name]
    out = np.full((2, p.L, 6, 4), np.nan)
    if p.R is None:
        cache[p.name] = out
        return out
    L = p.L
    for si, (rows, per) in enumerate(_spec_rows(ctx)):
        cd = heat.read_state(p.R, rows).astype(np.int64)
        cd = np.where(cd >= 0, cd, L)                                 # NA: its own bin, outside the rest
        for hi, q in enumerate(per):
            c = cd if q['sel'] is None else cd[q['sel']]
            ns = [np.bincount(c, m, minlength=L + 1)[:L].astype(np.float64) for m in q['masks']]
            for t in range(4):
                n = ns[q['mi'][t]]
                S = np.bincount(c, q['vals'][t], minlength=L + 1)[:L]
                with np.errstate(all='ignore'):
                    out[si, :, hi, t] = S / n - (S.sum() - S) / (n.sum() - n)
    cache[p.name] = out
    return out


def _spec_job(i: int):
    return _spec(_D['ctx'], _D['params'][i])


def specific_all(ctx, params: list, procs: int = 1) -> dict:
    """_spec for each reading parameter (own parameters: none; fork workers over parameters), and the check against
    heat_hm2.part_effects on the right track: the level's odds over the base on B equal the part's (max abs
    difference in meta)."""
    out, diff = {}, 0.0
    idx = [i for i, p in enumerate(params) if not p.own and p.R is not None]
    _spec_rows(ctx)
    _D.clear()
    _D.update(ctx=ctx, params=params)
    res = _fork_map(_spec_job, idx, procs)
    _D.clear()
    cache = ctx.__dict__.setdefault('_drill_spec', {})
    for i, r in zip(idx, res):
        out[params[i].name] = cache[params[i].name] = r
    ctx._drill_specrows = None
    parts = getattr(ctx, 'parts', None)
    if parts:
        rows = ctx.g.sp['B'].rows
        for j, R in enumerate(ctx.readings[:50]):
            cd = heat.read_state(R, rows).astype(np.int64)
            for hi, H in enumerate(H_ALL[:5]):
                kn = cd >= 0
                n = np.bincount(cd[kn], minlength=len(R['levels'])).astype(float)
                S = np.bincount(cd[kn], ctx.lab[f'sg{H}'][rows][kn].astype(float), minlength=len(R['levels']))
                with np.errstate(all='ignore'):
                    odds = 50 * (S / n - ctx.g.sp['B'].base[H]['msign'])
                po = np.asarray(parts['odds'][j])[1, hi]
                ok = np.isfinite(odds) & np.isfinite(po) & (n >= 30)
                if ok.any():
                    diff = max(diff, float(np.abs(odds[ok] - po[ok]).max()))
    ctx.part_check = diff
    return out


def _cells(codes, L, uo, day, W, G, sd, dayoff, dweek) -> dict:
    """One parameter over a block: key = unit offset + (code or the NA bin) x G_u + day, 12 bincounts of the packed
    weights, then the kernel. Returns the kernel's arrays (U, L, 2, ...)."""
    U = len(G)
    stride = (L + 1) * G
    off = np.r_[0, np.cumsum(stride)[:-1]].astype(np.int64)
    size = int(stride.sum())
    key = off[uo] + np.where(codes < 0, L, codes) * G[uo] + day
    bins = np.empty((NW, size))
    for f in range(NW):
        bins[f] = np.bincount(key, W[f], minlength=size)
    o = {k: np.zeros((U, L, 2, 4)) for k in ('cnt', 'days', 'rdays', 'weeks')}
    o['rw'] = np.zeros((U, L, 2, 6, 2))
    o['tc'] = np.zeros((U, L, 2, 3, 2))
    for k in ('mu', 'mur', 'sed', 'sew'):
        o[k] = np.full((U, L, 2, 18), np.nan)
    _nb_cells(bins, off, G, L, dayoff, sd, dweek, o['cnt'], o['days'], o['rdays'], o['weeks'], o['rw'], o['tc'], o['mu'], o['mur'],
              o['sed'], o['sew'])
    return o


def level_cells(insts: list, codes: np.ndarray, L: int) -> dict:
    """The packed path for one parameter's codes (concatenated over insts, -1 = NA): the kernel's arrays (tests and
    the bench compare them with cells_direct)."""
    G = np.array([x.G for x in insts], np.int64)
    uo = np.repeat(np.arange(len(insts)), [len(x.rows) for x in insts])
    return _cells(np.asarray(codes, np.int64), int(L), uo, np.concatenate([x.day for x in insts]), np.concatenate([x.W for x in insts], axis=1), G,
                  np.array([x.sd for x in insts], np.int64), np.r_[0, np.cumsum(G)[:-1]].astype(np.int64),
                  np.concatenate([x.dweek for x in insts]).astype(np.int64))


def scan(ctx, insts: list, params: list, summ: SummaryCounts = None, writer: ShardWriter = None, losers: bool = True, top: int = TOP_B,
         excl: np.ndarray = None) -> ScanOut:
    """One block of units (or of depth-2 subsets): per parameter one gather (read_state's rule) or the own codes, key =
    unit offset + (code or NA bin) x G_u + day, 12 bincounts of the packed weights, then _nb_cells. Every parameter's
    best take and skip level per (unit, H, track) on A (z_adj; floors FLOOR_A for the level and the rest) with its B
    numbers; the top `top` per list (main / insample) are kept; every parameter goes to the summary counts and the
    shards; the loser candidates (main list) to their own top lists."""
    U = len(insts)
    so = ScanOut()
    so.tops = {lst: TopK((U, 18, 2), top, len(REC)) for lst in LISTS}
    so.los = TopK((U, 6), LOSER_TOP, len(LREC))
    so.lct = TopK((U, 3), LOSER_TOP, len(LREC))
    so.n_params = 0
    if not U:
        return so
    lens = np.array([len(x.rows) for x in insts])
    rows = np.concatenate([x.rows for x in insts])
    uo = np.repeat(np.arange(U), lens)
    day = np.concatenate([x.day for x in insts])
    W = np.concatenate([x.W for x in insts], axis=1)
    G = np.array([x.G for x in insts], np.int64)
    sd = np.array([x.sd for x in insts], np.int64)
    dayoff = np.r_[0, np.cumsum(G)[:-1]].astype(np.int64)
    dweek = np.concatenate([x.dweek for x in insts]).astype(np.int64)
    dvec = np.stack([x.d for x in insts]).astype(np.float64)                       # (U, 6)
    tiers = np.array([int(x.unit.get('tier', 3)) for x in insts])
    subset = np.array([bool(x.unit.get('subset', True)) for x in insts])
    own_names = {p.name for p in params if p.own}
    own = {nm: np.concatenate([x.own.get(nm, np.full(len(x.rows), -1, np.int8)) for x in insts]).astype(np.int64) for nm in own_names}
    bi_cache = {}
    if excl is None:
        excl = np.zeros((U, len(params)), bool)
        for ui, x in enumerate(insts):
            for pi_, p in enumerate(params):
                excl[ui, pi_] = (not p.own) and p.base in x.bases
    for pid, p in enumerate(params):
        codes = _param_codes(p, rows, own, bi_cache)
        if codes is None or not (codes >= 0).any():
            continue
        L = p.L
        o = _cells(codes, L, uo, day, W, G, sd, dayoff, dweek)
        rec, zr, D = _derive(o, L)
        rec[..., RI['specific_A']] = _specific_A(ctx, p, rec, dvec)
        ex = excl[:, pid]
        zr[ex] = -np.inf
        so.tops[p.list].offer(zr, pid, rec)
        so.n_params += 1
        if summ is not None:
            _summ_add(summ, p, rec, zr, tiers, subset)
        if writer is not None:
            writer.add(pid, np.where(ex[:, None, None, None], np.nan, rec))
        if losers and p.list == 'main':
            _loser_offer(so, pid, D, o, ex)
    return so


def _derive(o: dict, L: int) -> tuple:
    """From the kernel's arrays: per (unit, 18 lifts, mode) the best level on A and its record (REC), the ranking key,
    and the per-level arrays the loser lists read."""
    U = o['cnt'].shape[0]
    n = o['cnt'][..., CT_OF]                                         # (U, L, 2, 18)
    dd, rd, wk = o['days'][..., CT_OF], o['rdays'][..., CT_OF], o['weeks'][..., CT_OF]
    rest = n.sum(1, keepdims=True) - n
    diff = o['mu'] - o['mur']
    with np.errstate(all='ignore'):
        lift = diff * SCALE
        t_day = np.where(o['sed'] > 0, diff / o['sed'], np.nan)
        t_wk = np.where(o['sew'] > 0, diff / o['sew'], np.nan)
        rs = o['rw'][..., HI_OF, :] / np.maximum(o['cnt'][..., CT_OF], 1)[..., None]             # (U, L, 2, 18, 2) share right / wrong
        ntc = o['cnt'][..., [CT_PI, CT_PI, CT_PI240]]
        tcs = o['tc'] / np.maximum(ntc, 1)[..., None]                                            # (U, L, 2, 3, 2)
    fa = (n[:, :, 0] >= FLOOR_A[0]) & (dd[:, :, 0] >= FLOOR_A[1]) & (rest[:, :, 0] >= FLOOR_A[0]) & (rd[:, :, 0] >= FLOOR_A[1])
    Ls = fa.sum(1)                                                    # (U, 18)
    z, tw, Gw, wkw = z_adj(t_day[:, :, 0], dd[:, :, 0], t_wk[:, :, 0], wk[:, :, 0], np.broadcast_to(Ls[:, None, :], fa.shape))
    zB, twB, GwB, wkB = z_adj(t_day[:, :, 1], dd[:, :, 1], t_wk[:, :, 1], wk[:, :, 1], 1)
    key = np.where(fa & np.isfinite(z), z + 1e-6 * np.minimum(np.abs(np.nan_to_num(tw)), 50.0) / 50.0, -np.inf)
    lA = lift[:, :, 0]
    rec = np.full((U, 18, 2, len(REC)), np.nan, np.float32)
    zr = np.full((U, 18, 2), -np.inf)
    tc_li = np.full((U, L, 2, 18, 2), np.nan)
    for hi, k in PK.items():
        for tr in range(3):
            tc_li[:, :, :, hi * 3 + tr] = tcs[:, :, :, k]
    for mi, sgn in enumerate((1.0, -1.0)):
        kk = np.where(lA * sgn > 0, key, -np.inf)
        best = kk.argmax(1)                                           # (U, 18)
        zr[:, :, mi] = np.take_along_axis(kk, best[:, None, :], 1)[:, 0]
        g = lambda a: np.take_along_axis(a, best[:, None, :], 1)[:, 0]
        cols = {'level': best.astype(float), 'z': g(z), 'lift_A': g(lA), 't_A': g(tw), 't_day_A': g(t_day[:, :, 0]), 't_week_A': g(t_wk[:, :, 0]),
                'G_day_A': g(dd[:, :, 0]), 'G_week_A': g(wk[:, :, 0]), 'n_A': g(n[:, :, 0]), 'days_A': g(dd[:, :, 0]), 'weeks_A': g(wk[:, :, 0]),
                'rest_n_A': g(rest[:, :, 0]), 'rest_days_A': g(rd[:, :, 0]), 'mean_A': g(o['mu'][:, :, 0] * SCALE),
                'mean_rest_A': g(o['mur'][:, :, 0] * SCALE), 'right_A': g(rs[:, :, 0, :, 0]), 'wrong_A': g(rs[:, :, 0, :, 1]),
                'week_weaker_A': g(wkw.astype(float)), 'n_B': g(n[:, :, 1]), 'days_B': g(dd[:, :, 1]), 'weeks_B': g(wk[:, :, 1]),
                'rest_n_B': g(rest[:, :, 1]), 'rest_days_B': g(rd[:, :, 1]), 'lift_B': g(lift[:, :, 1]), 't_B': g(twB),
                't_day_B': g(t_day[:, :, 1]), 't_week_B': g(t_wk[:, :, 1]), 'mean_B': g(o['mu'][:, :, 1] * SCALE),
                'mean_rest_B': g(o['mur'][:, :, 1] * SCALE), 'right_B': g(rs[:, :, 1, :, 0]), 'wrong_B': g(rs[:, :, 1, :, 1]),
                'week_weaker_B': g(wkB.astype(float)), 'Ls': Ls.astype(float), 'take_A': g(tc_li[:, :, 0, :, 0]), 'cut_A': g(tc_li[:, :, 0, :, 1]),
                'take_B': g(tc_li[:, :, 1, :, 0]), 'cut_B': g(tc_li[:, :, 1, :, 1])}
        for kname, v in cols.items():
            rec[:, :, mi, RI[kname]] = v
    rec[np.broadcast_to(~np.isfinite(zr)[..., None], rec.shape)] = np.nan
    D = {'fa': fa, 'tw': tw, 'n': n, 'dd': dd}
    return rec, zr, D


def _specific_A(ctx, p: Param, rec: np.ndarray, dvec: np.ndarray) -> np.ndarray:
    """specific_A per (unit, lift, mode): the lift on A minus the same level's lift over HM2's A entries, in A's mode."""
    if p.own or p.R is None:
        return np.full(rec.shape[:3], np.nan, np.float32)
    sp = _spec(ctx, p)[0]                                            # (L, 6, 4)
    lv = rec[..., RI['level']]
    ok = np.isfinite(lv)
    li = np.clip(np.nan_to_num(lv).astype(np.int64), 0, p.L - 1)
    out = np.full(rec.shape[:3], np.nan)
    for x in range(18):
        hi, tr = x // 3, x % 3
        for mi, sgn in enumerate((1.0, -1.0)):
            d = dvec[:, hi]
            l_ = li[:, x, mi]
            if tr == 0:
                al = sp[l_, hi, 0] * d * 50.0
            elif tr == 1:
                al = sp[l_, hi, 1] * d
            else:
                al = np.where(d > 0, sp[l_, hi, 2], sp[l_, hi, 3])
            out[:, x, mi] = sgn * (rec[:, x, mi, RI['lift_A']] - al)
    return np.where(ok, out, np.nan).astype(np.float32)


def _summ_add(summ: SummaryCounts, p: Param, rec: np.ndarray, zr: np.ndarray, tiers: np.ndarray, subset: np.ndarray):
    ok = np.isfinite(zr)
    if not ok.any():
        return
    u, x, mi = np.nonzero(ok)
    r = rec[u, x, mi]
    sgn = np.where(mi == 0, 1.0, -1.0)
    lB = r[:, RI['lift_B']] * sgn
    kept = lB > 0
    thin = ~((r[:, RI['n_B']] >= FLOOR_B[0]) & (r[:, RI['days_B']] >= FLOOR_B[1]) & (r[:, RI['rest_n_B']] >= FLOOR_B[0]) &
             (r[:, RI['rest_days_B']] >= FLOOR_B[1]))
    tb2 = np.nan_to_num(r[:, RI['t_B']] * sgn) >= 2
    spec = r[:, RI['specific_A']]
    sb = np.where(np.isfinite(spec), np.where(spec > 0, 1, 0), 2)
    zb = np.searchsorted(np.asarray(Z_BINS), np.nan_to_num(r[:, RI['z']]), 'right')
    keys = np.stack([HI_OF[x], TR_OF[x], mi, tiers[u], sb, np.nan_to_num(r[:, RI['week_weaker_A']]).astype(int), subset[u].astype(int), zb], 1)
    vals = np.stack([np.ones(len(u)), kept, ~thin, kept & ~thin, tb2], 1)
    summ.add_arrays(keys.astype(np.int64), vals, p.family, p.list)


def _loser_offer(so: ScanOut, pid: int, D: dict, o: dict, ex: np.ndarray):
    """The levels most over-represented among wrong against right instances (A ratio, +0.5 / +1 smoothing as in
    losers.py), ordered by the level's negative odds t (the skip list); and at 15, 60, 240 among cuts against takes
    (ordered by the A ratio)."""
    rw = o['rw']                                                     # (U, L, 2, 6, 2)
    U, L = rw.shape[:2]
    tot = rw.sum(1, keepdims=True)
    with np.errstate(all='ignore'):
        ratio = ((rw[..., 1] + 0.5) / (tot[..., 1] + 1)) / ((rw[..., 0] + 0.5) / (tot[..., 0] + 1))      # (U, L, 2, 6)
    fa, tw, n = D['fa'], D['tw'], D['n']
    for l in range(L):
        rec = np.full((U, 6, len(LREC)), np.nan, np.float32)
        li = np.arange(6) * 3                                        # the right track's lifts
        t = tw[:, l][:, li]                                          # (U, 6)
        ok = fa[:, l][:, li] & (ratio[:, l, 0] > 1) & np.isfinite(t) & ~ex[:, None]
        sc = np.where(ok, -t, -np.inf)
        rec[..., LI['level']] = l
        rec[..., LI['score']] = sc
        rec[..., LI['ratio_A']] = ratio[:, l, 0]
        rec[..., LI['ratio_B']] = ratio[:, l, 1]
        rec[..., LI['bad_A']], rec[..., LI['good_A']] = rw[:, l, 0, :, 1], rw[:, l, 0, :, 0]
        rec[..., LI['bad_B']], rec[..., LI['good_B']] = rw[:, l, 1, :, 1], rw[:, l, 1, :, 0]
        rec[..., LI['t_A']] = t
        rec[..., LI['n_A']] = n[:, l, 0][:, li]
        so.los.offer(sc, pid, rec)
    tc = o['tc']                                                     # (U, L, 2, 3, 2)
    tt = tc.sum(1, keepdims=True)
    with np.errstate(all='ignore'):
        rc = ((tc[..., 1] + 0.5) / (tt[..., 1] + 1)) / ((tc[..., 0] + 0.5) / (tt[..., 0] + 1))        # (U, L, 2, 3)
    for l in range(L):
        rec = np.full((U, 3, len(LREC)), np.nan, np.float32)
        lip = np.array([2 * 3 + 2, 4 * 3 + 2, 5 * 3 + 2])           # the profit track's lifts at 15, 60, 240
        ok = fa[:, l][:, lip] & (rc[:, l, 0] > 1) & ~ex[:, None]
        sc = np.where(ok, rc[:, l, 0], -np.inf)
        rec[..., LI['level']] = l
        rec[..., LI['score']] = sc
        rec[..., LI['ratio_A']] = rc[:, l, 0]
        rec[..., LI['ratio_B']] = rc[:, l, 1]
        rec[..., LI['bad_A']], rec[..., LI['good_A']] = tc[:, l, 0, :, 1], tc[:, l, 0, :, 0]
        rec[..., LI['bad_B']], rec[..., LI['good_B']] = tc[:, l, 1, :, 1], tc[:, l, 1, :, 0]
        rec[..., LI['t_A']] = tw[:, l][:, lip]
        rec[..., LI['n_A']] = n[:, l, 0][:, lip]
        so.lct.offer(sc, pid, rec)


def rank_lists(so: ScanOut, insts: list, params: list, ctx=None) -> pd.DataFrame:
    """Per unit, H, track and mode, for the 'main' list and the 'insample' list apart: the top TOP_B parameters by
    z_adj on A with their B numbers signed in A's mode (lift_B_mode, t_B_mode), kept, thin, t_B >= 2."""
    out = []
    for lst, T in so.tops.items():
        order = T.order()
        z = np.take_along_axis(T.z, order, -1)
        pidx = np.take_along_axis(T.p, order, -1)
        rec = np.take_along_axis(T.r, order[..., None], -2)
        u, x, mi, k = np.nonzero(np.isfinite(z))
        if not len(u):
            continue
        r = rec[u, x, mi, k]
        df = pd.DataFrame(r, columns=REC)
        df.insert(0, 'rank', k + 1)
        df.insert(0, 'list', lst)
        df.insert(0, 'mode', np.array(MODES)[mi])
        df.insert(0, 'track', np.array(TRACKS)[TR_OF[x]])
        df.insert(0, 'h', np.array(H_ALL)[HI_OF[x]])
        df.insert(0, 'uix', u)
        P = pidx[u, x, mi, k]
        df['pid'] = P
        df['param'] = [params[i].name for i in P]
        df['family'] = [params[i].family for i in P]
        df['fn'] = [params[i].fn for i in P]
        df['level_label'] = [params[i].levels[int(lv)] for i, lv in zip(P, r[:, RI['level']])]
        out.append(df)
    if not out:
        return pd.DataFrame()
    df = pd.concat(out, ignore_index=True)
    sgn = np.where(df['mode'] == 'take', 1.0, -1.0)
    df['lift_B_mode'] = df['lift_B'] * sgn
    df['t_B_mode'] = df['t_B'] * sgn
    df['lift_A_mode'] = df['lift_A'] * sgn
    df['kept'] = df['lift_B_mode'] > 0
    df['thin'] = ~((df['n_B'] >= FLOOR_B[0]) & (df['days_B'] >= FLOOR_B[1]) & (df['rest_n_B'] >= FLOOR_B[0]) & (df['rest_days_B'] >= FLOOR_B[1]))
    df['tb2'] = df['t_B_mode'].fillna(0) >= 2
    df['unit'] = [insts[i].unit['id'] for i in df['uix']]
    return df


# ========================================================================================================= the drill
def _wd(rows: np.ndarray, H: int, ndays: float) -> float:
    if not len(rows):
        return 0.0
    w = (rows + 1) // H
    return float(len(np.unique(w))) / ndays


def _deff(vals: np.ndarray, gate: np.ndarray, rest: np.ndarray, cl: np.ndarray) -> float:
    """The effective number of clusters of the lift (gate mean - rest mean): (sum psi^2)^2 / sum psi^4 (direct form)."""
    if gate.sum() == 0 or rest.sum() == 0:
        return np.nan
    K = int(cl.max()) + 1 if len(cl) else 1
    Sg = np.bincount(cl[gate], vals[gate], minlength=K)
    Cg = np.bincount(cl[gate], minlength=K).astype(float)
    Sr = np.bincount(cl[rest], vals[rest], minlength=K)
    Cr = np.bincount(cl[rest], minlength=K).astype(float)
    n, r = Cg.sum(), Cr.sum()
    a, b = Sg.sum() / n, Sr.sum() / r
    psi = (Sg - a * Cg) / n - (Sr - b * Cr) / r
    q2, q4 = float((psi ** 2).sum()), float((psi ** 4).sum())
    G = int((Cg > 0).sum())
    return min(float(G), q2 * q2 / q4) if q4 > 0 else float(G)


def _track_vals(V: dict, hi: int, tr: int) -> tuple:
    """(values, valid) of a track at a horizon: right (+1 / -1 / 0, x 50 = odds), move (bps), profit (pi_c / pi)."""
    if tr == 0:
        return V['y'][hi].astype(np.float64) * 50.0, V['ok'][hi]
    if tr == 1:
        return V['move'][hi].astype(np.float64), V['ok'][hi]
    return V['prof'][hi].astype(np.float64), V['pok'][hi]


def remeasure(ctx, x: Inst, V: dict, sel: pd.DataFrame, params: list) -> pd.DataFrame:
    """Lean (review): for each selected row (parameter, level, H, track, mode) of the unit's top TOP_B, the gate and the
    rest on B: exact windows per day (np.unique of (row + 1) // H), gheat_B = the smaller of the two x the lift signed
    in A's mode (the pair pack's lheat rule), what the gate does to the call (the gated call's odds, profit and windows
    per day against the ungated call's), the gated set's hold, best, dip, retL and take / cut shares; deff (direct form,
    day and week) of the A lift; specific_B (the lift minus the level's lift over all B minutes). The B-instance
    Jaccard between gated sets collapses near-copies into aliases."""
    if not len(sel):
        return sel
    sel = sel.reset_index(drop=True)
    isA, isB = x.split == 0, x.split == 1
    ndB = {H: (ctx.g240 if H == 240 else ctx.g).sp['B'].ndays for H in H_ALL}
    cols = {k: np.full(len(sel), np.nan) for k in ('wd_B', 'rest_wd_B', 'gheat_B', 'call_odds_B', 'call_prof_B', 'call_wd_B', 'gated_odds_B',
                                                     'gated_prof_B', 'gated_wd_B', 'hold_B', 'best_B', 'dip_B', 'retL_B', 'take_share_B',
                                                     'cut_share_B', 'deff_day_A', 'deff_week_A', 'specific_B', 'pi_B', 'pi_c_B')}
    bits = {}
    cache = {}
    wkA = x.dweek[x.day]
    for i, r in enumerate(sel.itertuples(index=False)):
        p = params[int(r.pid)]
        if p.name not in cache:
            cache[p.name] = _param_codes(p, x.rows, {k: v.astype(np.int64) for k, v in x.own.items()}, {})
        cd = cache[p.name]
        lv = int(r.level)
        gate, known = cd == lv, cd >= 0
        rest = known & ~gate
        hi, tr = H_ALL.index(int(r.h)), TRACKS.index(r.track)
        H = int(r.h)
        vals, ok = _track_vals(V, hi, tr)
        ok = ok & np.isfinite(vals)
        sgn = 1.0 if r.mode == 'take' else -1.0
        gB, rB, cB = gate & isB & ok, rest & isB & ok, isB & ok
        gated = gate if r.mode == 'take' else ~gate
        xB = gated & isB & ok
        wd_g, wd_r = _wd(x.rows[gB], H, ndB[H]), _wd(x.rows[rB], H, ndB[H])
        cols['wd_B'][i], cols['rest_wd_B'][i] = wd_g, wd_r
        lb = float(r.lift_B) * sgn if r.lift_B == r.lift_B else np.nan
        cols['gheat_B'][i] = min(wd_g, wd_r) * lb if lb == lb else np.nan
        yv = V['y'][hi].astype(np.float64) * 50.0
        oky = V['ok'][hi]
        mean = lambda a, m: float(a[m].mean()) if m.any() else np.nan
        cols['call_odds_B'][i] = mean(yv, isB & oky)
        cols['gated_odds_B'][i] = mean(yv, gated & isB & oky)
        pf, pok = V['prof'][hi].astype(np.float64), V['pok'][hi]
        cols['call_prof_B'][i] = mean(pf, isB & pok)
        cols['gated_prof_B'][i] = mean(pf, gated & isB & pok)
        cols['pi_B'][i] = mean(V['pi'][hi].astype(np.float64), gated & isB & pok)
        cols['pi_c_B'][i] = mean(pf, gated & isB & pok) if hi < 5 else np.nan
        cols['call_wd_B'][i] = _wd(x.rows[cB], H, ndB[H])
        cols['gated_wd_B'][i] = _wd(x.rows[xB], H, ndB[H])
        cols['hold_B'][i] = mean(V['hold'][hi].astype(np.float64), xB)
        cols['best_B'][i] = mean(V['best'][hi].astype(np.float64), xB)
        cols['dip_B'][i] = mean(V['dip'][hi].astype(np.float64), xB)
        cols['retL_B'][i] = mean(V['retL'][hi].astype(np.float64), xB)
        kk = V['kind'][hi]
        cols['take_share_B'][i] = mean((kk == 1).astype(float), gated & isB & pok)
        cols['cut_share_B'][i] = mean((kk == 2).astype(float), gated & isB & pok)
        gA, rA = gate & isA & ok, rest & isA & ok
        v0 = np.nan_to_num(vals)
        cols['deff_day_A'][i] = _deff(v0, gA, rA, x.day)
        cols['deff_week_A'][i] = _deff(v0, gA, rA, wkA)
        if not p.own and p.R is not None:
            sp = _spec(ctx, p)[1]
            d = float(x.d[hi])
            al = sp[lv, hi, 0] * d * 50.0 if tr == 0 else sp[lv, hi, 1] * d if tr == 1 else sp[lv, hi, 2 if d > 0 else 3]
            cols['specific_B'][i] = sgn * (float(r.lift_B) - al) if al == al else np.nan
        bits[i] = gB
    for k, v in cols.items():
        sel[k] = v
    # aliases: gated B sets overlapping JACCARD or more (within one list of the unit), the higher-ranked row keeps them
    sel['alias_of'] = -1
    sel['aliases'] = ''
    for _, idx in sel.groupby(['h', 'track', 'mode', 'list']).groups.items():
        idx = sorted(idx, key=lambda j: sel.at[j, 'rank'])
        M = np.stack([bits[sel.index.get_loc(j)] for j in idx]).astype(np.float64)
        inter = M @ M.T
        sz = M.sum(1)
        with np.errstate(all='ignore'):
            J = inter / (sz[:, None] + sz[None, :] - inter)
        for a in range(len(idx)):
            if sel.at[idx[a], 'alias_of'] != -1:
                continue
            al = []
            for b in range(a + 1, len(idx)):
                if sel.at[idx[b], 'alias_of'] == -1 and J[a, b] >= JACCARD:
                    sel.at[idx[b], 'alias_of'] = int(sel.at[idx[a], 'rank'])
                    al.append(f"{sel.at[idx[b], 'param']}={sel.at[idx[b], 'level_label']}")
            sel.at[idx[a], 'aliases'] = '|'.join(al)
    return sel


def curve(ctx, x: Inst, V: dict, p: Param, hi: int, why: str = 'A') -> dict:
    """The finer curve: a value parameter binned at the deciles of its 200-bin code among the unit's A instances (B
    on A's edges), a categorical one by its own levels; per bin, A and B: n, days, share right / wrong / flat, odds,
    move, profit (pi_c or pi), take / cut / time shares, minutes held, best and dip; the zone edges marked. drill = 'A'
    (A's top TOP_FULL) or 'B' (top TOP_B kept with t_B >= 2: picked on B, never counted in the chance table)."""
    H = H_ALL[hi]
    pct = ctx.pct.get(p.base) if (not p.own and p.R is not None and (p.R.get('zones') or p.levels == ['below 0', 'above 0'])) else None
    if pct is not None:
        code, k, _ = pct
        c = _at_bars(code.astype(np.float64), x.rows, k)
        c[c == PCT_NA] = np.nan
        ca = c[(x.split == 0) & np.isfinite(c)]
        if len(ca) < CURVE_BINS:
            return None
        e = np.unique(np.quantile(ca, np.arange(1, CURVE_BINS) / CURVE_BINS))
        b = np.where(np.isfinite(c), np.searchsorted(e, c, 'right'), -1)
        nb_ = len(e) + 1
        lo = np.r_[0, np.ceil(e)].astype(int)
        hi_ = np.r_[np.ceil(e) - 1, PCT_BINS - 1].astype(int)
        labels = [f'pct {lo[i] / 2:.1f}-{(hi_[i] + 1) / 2:.1f}%' for i in range(nb_)]
        zones = [[int(zone_of_pct(np.array([lo[i]]))[0]), int(zone_of_pct(np.array([max(lo[i], hi_[i])]))[0])] for i in range(nb_)]
        kind = 'value'
    else:
        cd = _param_codes(p, x.rows, {kk: v.astype(np.int64) for kk, v in x.own.items()}, {})
        b = cd
        nb_ = p.L
        labels = list(p.levels)
        zones = None
        e = None
        kind = 'levels'
    out = {'param': p.name, 'h': H, 'drill': why, 'kind': kind, 'bins': labels, 'edges': None if e is None else [float(v) for v in e],
           'zones': zones, 'zone_names': list(heat.ZONES)}
    for si, s in ((0, 'A'), (1, 'B')):
        m = (x.split == si) & (b >= 0)
        bb = b[m].astype(np.int64)
        okH = V['ok'][hi][m]
        n = np.bincount(bb[okH], minlength=nb_)[:nb_].astype(float)
        y = V['y'][hi][m]
        right = np.bincount(bb, (y > 0) & okH, minlength=nb_)[:nb_]
        wrong = np.bincount(bb, (y < 0) & okH, minlength=nb_)[:nb_]
        days = np.array([len(np.unique(x.day[m][bb == i])) for i in range(nb_)])
        pok = V['pok'][hi][m]
        npk = np.bincount(bb[pok], minlength=nb_)[:nb_].astype(float)
        sm = lambda arr, okm: np.bincount(bb[okm], np.nan_to_num(arr[m][okm].astype(np.float64)), minlength=nb_)[:nb_]
        with np.errstate(all='ignore'):
            o = {'n': n.astype(int).tolist(), 'days': days.tolist(), 'right': (right / n).tolist(), 'wrong': (wrong / n).tolist(),
                 'flat': ((n - right - wrong) / n).tolist(), 'odds': (50 * (right - wrong) / n).tolist(),
                 'move': (sm(V['move'][hi], okH) / n).tolist(), 'profit': (sm(V['prof'][hi], pok) / npk).tolist(),
                 'take': (np.bincount(bb, (V['kind'][hi][m] == 1) & pok, minlength=nb_)[:nb_] / npk).tolist(),
                 'cut': (np.bincount(bb, (V['kind'][hi][m] == 2) & pok, minlength=nb_)[:nb_] / npk).tolist(),
                 'time': (np.bincount(bb, (V['kind'][hi][m] == 3) & pok, minlength=nb_)[:nb_] / npk).tolist(),
                 'hold': (sm(V['hold'][hi], okH) / n).tolist(), 'best': (sm(V['best'][hi], okH) / n).tolist(),
                 'dip': (sm(V['dip'][hi], okH) / n).tolist()}
        out[s] = o
    out['shape'] = curve_shape(out['A']['odds'], out['A']['n'])
    return out


def curve_shape(y, n) -> str:
    """threshold (one step carries most of the range), slope (monotone in rank), tail (an end bin stands apart), flat or
    mixed (fixed now: no tuning after a result)."""
    y = np.asarray(y, float)
    ok = np.isfinite(y) & (np.asarray(n) > 0)
    y = y[ok]
    if len(y) < 3:
        return 'too few bins'
    rng = y.max() - y.min()
    if rng <= 0:
        return 'flat'
    st = np.abs(np.diff(y))
    from scipy.stats import spearmanr
    rho = spearmanr(np.arange(len(y)), y)[0] if len(y) > 2 else 0.0
    ends = max(abs(y[0] - np.median(y[1:])), abs(y[-1] - np.median(y[:-1])))
    if st.max() >= 0.6 * rng and 0 < int(st.argmax()) < len(st) - 1:
        return 'threshold'
    if ends >= 0.6 * rng and np.ptp(y[1:-1]) <= 0.4 * rng:
        return 'tail'
    if abs(rho) >= 0.7:
        return 'slope'
    return 'mixed'


def loser_profile(ctx, x: Inst, V: dict, so: ScanOut, ui: int, params: list) -> dict:
    """Per horizon: the right / wrong / flat x take / cut / time table (A, B); the wrong instances' path (mean dip
    before the best point, minutes to the cut, the share that never closed a minute on the called side); the 10 levels
    most over-represented among wrong against right on A, ordered by their negative odds t, with A and B ratios; at 15,
    60 and 240 also among cuts against takes; one line in words."""
    out = {}
    for hi, H in enumerate(H_ALL):
        o = {}
        for si, s in ((0, 'A'), (1, 'B')):
            m = (x.split == si) & V['ok'][hi]
            y, kd = V['y'][hi][m], V['kind'][hi][m]
            tab = {}
            for on, oc in (('right', y > 0), ('wrong', y < 0), ('flat', y == 0)):
                tab[on] = {kn: int((oc & (kd == kv)).sum()) for kn, kv in (('take', 1), ('cut', 2), ('time', 3), ('none', 0))}
            o[f'table_{s}'] = tab
            w = m & (V['y'][hi] < 0)
            jj = V['j'][hi][w & (V['kind'][hi] == 2)]
            o[f'wrong_{s}'] = {'n': int(w.sum()), 'dip': float(np.nanmean(V['dip'][hi][w])) if w.any() else None,
                               'minutes_to_cut': float(jj.mean()) if len(jj) else None,
                               'held_0_share': float((V['hold'][hi][w] == 0).mean()) if w.any() else None}
        T = so.los
        order = T.order()[ui, hi]
        lv = []
        for k in order:
            if not np.isfinite(T.z[ui, hi, k]):
                continue
            r = T.r[ui, hi, k]
            p = params[int(T.p[ui, hi, k])]
            lv.append({'param': p.name, 'level': p.levels[int(r[LI['level']])], 'ratio_A': float(r[LI['ratio_A']]), 'ratio_B': float(r[LI['ratio_B']]),
                       't_A': float(r[LI['t_A']]), 'wrong_A': int(r[LI['bad_A']]), 'right_A': int(r[LI['good_A']]),
                       'wrong_B': int(np.nan_to_num(r[LI['bad_B']])), 'right_B': int(np.nan_to_num(r[LI['good_B']])),
                       'kept': bool(r[LI['ratio_B']] > 1)})
        o['wrong_levels'] = lv
        if hi in PK:
            T2 = so.lct
            k2 = PK[hi]
            cl = []
            for k in T2.order()[ui, k2]:
                if not np.isfinite(T2.z[ui, k2, k]):
                    continue
                r = T2.r[ui, k2, k]
                p = params[int(T2.p[ui, k2, k])]
                cl.append({'param': p.name, 'level': p.levels[int(r[LI['level']])], 'ratio_A': float(r[LI['ratio_A']]),
                           'ratio_B': float(r[LI['ratio_B']]), 'cut_A': int(r[LI['bad_A']]), 'take_A': int(r[LI['good_A']]),
                           'kept': bool(r[LI['ratio_B']] > 1)})
            o['cut_levels'] = cl
        if lv:
            t0 = lv[0]
            o['words'] = (f"wrong {H}-minute calls of {unit_words(x.unit)} are {t0['ratio_A']:.1f} times as common when "
                          f"{param_words(t0['param'], t0['level'])} (A {t0['ratio_A']:.2f}, B {t0['ratio_B']:.2f})")
        out[str(H)] = o
    return out


def depth2_subs(ctx, insts: list, T: pd.DataFrame, params: list) -> list:
    """The depth-2 subsets: inside the take gate of the right and of the profit track at 15, 60 and 240 minutes (A's
    top 1 of the main list; deduplicated, at most 6 per unit) with DEPTH2_MIN instances on A at the winning level."""
    subs = []
    if not len(T):
        return subs
    t1 = T[(T['list'] == 'main') & (T['rank'] == 1) & (T['mode'] == 'take') & T['track'].isin(DEPTH2_TRACKS) & T['h'].isin(DEPTH2_H)]
    for ui, g in t1.groupby('uix'):
        x = insts[int(ui)]
        done = {}
        for r in g.itertuples(index=False):
            k = (int(r.pid), int(r.level))
            done.setdefault(k, []).append((int(r.h), r.track))
        for (pid, lv), origins in done.items():
            p = params[pid]
            cd = _param_codes(p, x.rows, {kk: v.astype(np.int64) for kk, v in x.own.items()}, {})
            m = cd == lv
            nA = int((m & (x.split == 0)).sum())
            dA = int(len(np.unique(x.day[m & (x.split == 0)])))
            if nA < DEPTH2_MIN[0] or dA < DEPTH2_MIN[1]:
                subs.append({'uix': int(ui), 'pid': pid, 'level': lv, 'origins': origins, 'inst': None, 'n_A': nA, 'days_A': dA})
                continue
            y = sub_instances(ctx, x, m, extra_bases=() if p.own else (p.base,))
            subs.append({'uix': int(ui), 'pid': pid, 'level': lv, 'origins': origins, 'inst': y, 'n_A': nA, 'days_A': dA})
    return subs


def depth2_rows(ctx, subs: list, so2: ScanOut, params: list, insts: list, Vs: dict) -> pd.DataFrame:
    """Per depth-2 subset and origin (H, track): the top DEPTH2_TOP take levels inside the gate (A ranking, main list)
    with A and B numbers; the top 1 is the path "unit, p1 = l1, p2 = l2", scored on B against the gate's other
    instances (its lift) and against the call (the path's mean minus the call's on B)."""
    live = [s for s in subs if s['inst'] is not None]
    if not live:
        return pd.DataFrame()
    df = rank_lists(so2, [s['inst'] for s in live], params)
    if not len(df):
        return df
    df = df[(df['list'] == 'main') & (df['mode'] == 'take') & (df['rank'] <= DEPTH2_TOP)].copy()
    rows = []
    for si, s in enumerate(live):
        x = insts[s['uix']]
        p1 = params[s['pid']]
        for (H, tr) in s['origins']:
            g = df[(df['uix'] == si) & (df['h'] == H) & (df['track'] == tr)].sort_values('rank')
            for r in g.itertuples(index=False):
                row = r._asdict()
                row.update(uix=s['uix'], unit=x.unit['id'], p1=p1.name, l1=p1.levels[s['level']], origin_h=H, origin_track=tr, path=r.rank == 1)
                if r.rank == 1:
                    V = Vs[s['uix']]
                    hi, ti = H_ALL.index(H), TRACKS.index(tr)
                    vals, ok = _track_vals(V, hi, ti)
                    cd1 = _param_codes(p1, x.rows, {kk: v.astype(np.int64) for kk, v in x.own.items()}, {})
                    p2 = params[int(r.pid)]
                    cd2 = _param_codes(p2, x.rows, {kk: v.astype(np.int64) for kk, v in x.own.items()}, {})
                    isB = (x.split == 1) & ok & np.isfinite(vals)
                    path = isB & (cd1 == s['level']) & (cd2 == int(r.level))
                    row['path_B_n'] = int(path.sum())
                    row['path_B_mean'] = float(vals[path].mean()) if path.any() else np.nan
                    row['call_B_mean'] = float(vals[isB].mean()) if isB.any() else np.nan
                    row['path_over_call_B'] = row['path_B_mean'] - row['call_B_mean']
                    row['path_kept'] = bool(r.lift_B > 0)
                    # (review fix) the path's gate heat on B, the one-condition rule (remeasure): the smaller of the
                    # windows per day of the path and of the gate's other instances, x the lift on B (take mode)
                    rest = isB & (cd1 == s['level']) & (cd2 >= 0) & (cd2 != int(r.level))
                    ndB = (ctx.g240 if H == 240 else ctx.g).sp['B'].ndays
                    lb = float(getattr(r, 'lift_B_mode', r.lift_B))
                    row['gheat_B'] = min(_wd(x.rows[path], H, ndB), _wd(x.rows[rest], H, ndB)) * lb if lb == lb else np.nan
                rows.append(row)
    return pd.DataFrame(rows)


# ============================================================================================================= words
def param_words(name: str, level: str) -> str:
    from oracle import heat_hm2_league as hl
    if name.startswith('OWN:'):
        nm = name[4:]
        if nm == 'Since':
            return f'the call last fired {level} bars of its own timeframe before' if level != 'none' else 'the call had not fired before'
        if nm == 'Order':
            return f'the call fired {level} times in the 30 bars before'
        if nm.startswith('Last@'):
            return f"the call's previous closed {nm[5:]}-minute window went {level}"
        if nm == 'Coincide':
            return f'{level} other event levels fire at the same close'
        if nm.startswith('Agree@'):
            return f'the co-firing levels\' {nm[6:]}-minute directions are {level} the call'
        if nm.startswith('Depth'):
            return f"the call's own value is in its {level} quintile (of the call's A instances)"
        if nm == 'BarRange':
            return f"the event bar's range over ATR14 is in its {level} quintile"
        if nm == 'BarVol':
            return f"the event bar's volume over the 20 bars before is in its {level} quintile"
        if nm == 'BarBody':
            return f"the event bar's body over its range is {level}"
        if nm == 'Step':
            return f"the coin's price step is in its {level} quintile"
        if nm.startswith('chart.'):
            return f"the pattern's own {nm[6:]} is {level}"
        return f'{nm} {level}'
    return hl.level_words(name, level)


def unit_words(u: dict) -> str:
    from oracle import heat_hm2_league as hl
    if u['kind'] in ('level', 'model', 'chart'):
        nm, lv = u['key'].rsplit('=', 1)
        return hl.level_words(nm, lv)
    if u['kind'] == 'cell':
        nm, lv = u['when'].rsplit('=', 1)
        return hl.level_words(nm, lv) + ' while ' + hl.cond_words(u['conds'])
    return hl.cond_words(u.get('conds', []))


def in_words(row, twin_best=None) -> str:
    """One sentence per list row; clock and position levels in Eastern and UTC; the twin unit's best number for the
    same list."""
    g = row.get if isinstance(row, dict) else (lambda k, d=None: getattr(row, k, d))
    H, tr, mode = int(g('h')), g('track'), g('mode')
    unit = g('unit_words') or g('unit')
    what = {'right': 'odds points', 'move': 'bps', 'profit': 'cents per contract' if H < 240 else 'bps after cost'}[tr]
    verb = 'do better' if mode == 'take' else 'do worse'
    txt = (f"{H}-minute calls of {unit} {verb} when {param_words(g('param'), g('level_label'))}: "
           f"{tr} lift A {float(g('lift_A_mode')):+.2f} {what} (t {float(g('t_A')) * (1 if mode == 'take' else -1):+.1f}), "
           f"B {float(g('lift_B_mode')):+.2f} (t {float(np.nan_to_num(g('t_B_mode'))):+.1f})")
    if twin_best is not None and twin_best == twin_best:
        txt += f" (twins' best for this list: B {float(twin_best):+.2f})"
    return txt + '.'


# ============================================================================================================ series
_D = {}


def _prepare(ctx, raw: dict = None, gbm=(), hm2_series: str = '', engine: bool = True, log=_log_none, procs: int = 1,
             chart: bool = True) -> dict:
    """After heat_hm2.base (or make_ctx): drop HM2's entry matrices (the drill does not read them), the 200-bin codes
    (engine series rebuilt, HM2 series captured or given), the GBM readings, the proxy table, the fire index, the
    parameters and the all-minutes effects. Returns stage seconds."""
    sec = {}
    t = time.time()
    for k in ('C', 'W', 'T', 'Wt', '_icache'):
        if k in ctx.__dict__:
            setattr(ctx, k, None)
    heat._trim()
    ctx.pct = {}
    if engine:
        names = {R['name'] for R in ctx.readings if R.get('zones') and not R.get('family') and re.match(r'^\d+m:', R['name'])}
        ctx.pct.update(engine_pct(ctx, names, log))
    if raw:
        cap = {k: v for k, v in raw.items() if isinstance(v, tuple) and len(v) == 3}
        given = {k: v for k, v in raw.items() if not (isinstance(v, tuple) and len(v) == 3)}
        ctx.pct.update(cap)
        ctx.pct.update(raw_pct(ctx, given))
    ctx.pct_check = check_pct(ctx, ctx.pct)
    sec['pct'] = round(time.time() - t, 1)
    t = time.time()
    ctx.gbm = list(gbm) if gbm else load_gbm(ctx, hm2_series, log)
    ctx.gbm_byname = {R['name']: R for R in ctx.gbm}
    if hasattr(ctx, 'chart'):
        ctx.chart_info = {'loaded': bool(ctx.chart), 'how': 'given'}
    elif chart:
        ctx.chart_info = chart_readings(ctx, log)
    else:
        ctx.chart, ctx.chart_byname, ctx.chart_cat = [], {}, None
        ctx.chart_info = {'loaded': False, 'why': 'off (--no-chart)'}
    sec['gbm'] = round(time.time() - t, 1)
    t = time.time()
    ctx.pt = proxy_table(ctx)
    sec['proxy'] = round(time.time() - t, 1)
    t = time.time()
    _ok240(ctx)
    ctx.fi = fire_index(ctx, log)
    sec['fire_index'] = round(time.time() - t, 1)
    t = time.time()
    ctx.params = series_params(ctx)
    specific_all(ctx, ctx.params, procs)
    sec['specific'] = round(time.time() - t, 1)
    return sec


def make_drill_ctx(m: dict, readings: list, raw: dict = None, gbm=(), asset: str = 'X', twin: int = 0, lab=None, g=None, lab240=None, g240=None,
                   chart=None, log=_log_none):
    """The series context from minutes and readings (tests, bench): heat_hm2.make_ctx, then the drill's extras. raw:
    {reading name: (value series on its bar grid, k)} for the 200-bin codes (or captured (code, k, edges)). chart:
    {'readings', 'catalogue'} of Part 4 (none when not given)."""
    ctx = hm.make_ctx(m, readings, asset, twin, lab=lab, g=g, lab240=lab240, g240=g240, log=log)
    ctx.m_real = m
    ctx.chart, ctx.chart_cat = (chart or {}).get('readings', []), (chart or {}).get('catalogue')      # Part 4 only when given
    ctx.chart_byname = {R['name']: R for R in ctx.chart}
    ctx.drill_sec = _prepare(ctx, raw, gbm, engine=False, log=log)
    return ctx


def prepare_units(ctx, units: list, log=_log_none, strict: bool = True) -> tuple:
    """Each unit's fires; identical fire rows run once (the first in list order) and carry the others as aliases;
    unknown keys are listed (strict: the job stops). Returns (kept units with 'rows', unknown)."""
    seen, kept, unknown = {}, [], []
    for u in units:
        try:
            rows = unit_rows(ctx, u)
        except KeyError as e:
            unknown.append({'id': u['id'], 'why': str(e)})
            continue
        h = hashlib.sha1(rows.tobytes()).hexdigest()
        if h in seen:
            v = seen[h]
            v['aliases'] = sorted(set(v.get('aliases', [])) | {u['key']} | set(u.get('aliases', [])))
            v.setdefault('copies', []).append(u['id'])
            continue
        u = dict(u)
        u['rows'] = rows
        seen[h] = u
        kept.append(u)
    if unknown:
        log(f'  {len(unknown)} unit keys unknown on this series: {unknown[:3]}')
        if strict:
            raise SystemExit(f'{len(unknown)} unknown unit keys, e.g. {unknown[:3]}')
    return kept, unknown


def chart_units(ctx, coin: str) -> list:
    """Part 4's chart event levels as units (tier 3 after the HM1 levels), with the engine's sample floors."""
    out = []
    for R in getattr(ctx, 'chart', []) or []:
        if not R.get('every'):
            continue
        for lv, side, label in heat.event_levels(R):
            rows = heat.level_events(R, lv, side)
            rA, rB = ctx.g.in_split(rows, 'A'), ctx.g.in_split(rows, 'B')
            if len(rA) < FLOOR_A[0] or len(np.unique(ctx.g.day[rA])) < FLOOR_A[1] or len(rB) < FLOOR_B[0] or len(np.unique(ctx.g.day[rB])) < FLOOR_B[1]:
                continue
            out.append(_unit(coin, 'chart', f'{R["name"]}={label}', 3, 'chart'))
    return out


def plan_blocks(ctx, units: list, part=(0, 1)) -> list:
    """The unit list of this part (S parts of about equal capped instance count, in list order: tier 1 first) cut
    into blocks of at most BLOCK_UNIT_DAYS unit-days. Returns [[unit index, ...], ...]."""
    g = ctx.g
    cnt, ud = [], []
    for u in units:
        rA = g.in_split(u['rows'], 'A')
        rB = g.in_split(u['rows'], 'B')
        r = np.r_[_cap(rA, u['key']), rB]
        cnt.append(len(r))
        ud.append(len(np.unique(g.day[r])))
    pi, S = part
    cs = np.cumsum(cnt)
    tot = cs[-1] if len(cs) else 0
    lo, hi = tot * pi / S, tot * (pi + 1) / S
    mine = [i for i in range(len(units)) if (cs[i] - cnt[i] / 2.0 >= lo) and (cs[i] - cnt[i] / 2.0 < hi or pi == S - 1)]
    blocks, cur, used = [], [], 0
    for i in mine:
        if ud[i] == 0:
            continue
        if cur and used + ud[i] > BLOCK_UNIT_DAYS:
            blocks.append(cur)
            cur, used = [], 0
        cur.append(i)
        used += ud[i]
    if cur:
        blocks.append(cur)
    return blocks


def _make_inst(ctx, u: dict) -> Inst:
    x = split_instances(ctx, u, u['rows'])
    x.k = unit_k(ctx, u)
    x.bases = {R.get('base', R['name']) for R in unit_readings(ctx, u)}
    x.own, x.own_edges = own_params(ctx, x)
    V = inst_vals(ctx, x)
    x.W, x.clipped = pack_weights(x, V)
    return x


def _unit_row(ctx, x: Inst, V: dict) -> list:
    """The call's own numbers per horizon (A and B, in its A direction)."""
    rows = []
    u = x.unit
    for hi, H in enumerate(H_ALL):
        r = {'unit': u['id'], 'coin': u['coin'], 'kind': u['kind'], 'key': u['key'], 'tier': u.get('tier'), 'subset': bool(u.get('subset', True)),
             'aliases': '|'.join(u.get('aliases', [])), 'h': H, 'dir': int(x.d[hi]), 'dir_flag': bool(x.dflag[hi]), 'n_A_all': int(x.dn[hi]),
             'capped': x.capped, 'k': x.k, 'fn': _unit_fn(ctx, u), 'unit_family': _unit_family(ctx, u), 'words': unit_words(u)}
        for si, s in ((0, 'A'), (1, 'B')):
            m = (x.split == si) & V['ok'][hi]
            pm = (x.split == si) & V['pok'][hi]
            y = V['y'][hi][m]
            r[f'n_{s}'] = int(m.sum())
            r[f'days_{s}'] = int(len(np.unique(x.day[m])))
            r[f'odds_{s}'] = float(50 * y.mean()) if len(y) else np.nan
            r[f'share_{s}'] = float((y > 0).mean() * 100) if len(y) else np.nan
            r[f'move_{s}'] = float(np.nanmean(V['move'][hi][m])) if m.any() else np.nan
            r[f'prof_{s}'] = float(np.nanmean(V['prof'][hi][pm])) if pm.any() else np.nan
            r[f'take_{s}'] = float((V['kind'][hi][pm] == 1).mean()) if pm.any() else np.nan
            r[f'cut_{s}'] = float((V['kind'][hi][pm] == 2).mean()) if pm.any() else np.nan
        sp = (ctx.g240 if H == 240 else ctx.g).sp['B']
        mB = (x.split == 1) & V['ok'][hi]
        r['wd_B'] = _wd(x.rows[mB], H, sp.ndays)
        rows.append(r)
    return rows


def _unit_fn(ctx, u: dict) -> str:
    """The card of a unit: its trigger reading's TA function, candlestick or chart pattern, or data family (an HM2
    cell: its first condition's reading), by the name in the unit's key."""
    try:
        Rs = unit_readings(ctx, u)
    except KeyError:
        Rs = []
    if not Rs:
        return 'family:unknown'
    kind = u['kind']
    name = u['key'] if kind in ('level', 'model', 'chart') else u['when'] if kind == 'cell' else u['conds'][0][0] + '='
    return _card_name(name.rsplit('=', 1)[0], hm.family_of(Rs[0]))           # the unit's own name (a copy-merged reading keeps its key)


def _unit_family(ctx, u: dict) -> str:
    try:
        Rs = unit_readings(ctx, u)
    except KeyError:
        return 'unknown'
    if not Rs:
        return 'unknown'
    return hm.family_of(Rs[0])


def _block_job(bid: int) -> dict:
    """One block: instances, the depth-1 scan, the lists, the re-measure, curves, depth 2 (one scan over every unit's
    gates), the loser profiles; writes the block's files and returns its summary."""
    ctx, units, blocks, params, out = _D['ctx'], _D['units'], _D['blocks'], _D['params'], _D['out']
    t0 = time.time()
    insts = [_make_inst(ctx, units[i]) for i in blocks[bid]]
    summ = SummaryCounts()
    writer = ShardWriter(_D.get('shards', ''), _D.get('real', False))
    so = scan(ctx, insts, params, summ, writer)
    shard_bytes = writer.flush(bid, [x.unit['id'] for x in insts], params)
    T = rank_lists(so, insts, params)
    Vs = {i: inst_vals(ctx, x) for i, x in enumerate(insts)}
    # the re-measure of every listed row
    parts = []
    for ui, g in (T.groupby('uix') if len(T) else []):
        parts.append(remeasure(ctx, insts[int(ui)], Vs[int(ui)], g, params))
    T = pd.concat(parts, ignore_index=True) if parts else T
    if len(T):
        T['drill'] = np.where((T['list'] == 'main') & (T['rank'] <= TOP_FULL), 'A', np.where(T['kept'] & T['tb2'], 'B', ''))
    # depth 2: one scan over every unit's take gates
    subs = depth2_subs(ctx, insts, T, params)
    live = [s['inst'] for s in subs if s['inst'] is not None]
    so2 = scan(ctx, live, params, None, None, losers=False, top=DEPTH2_TOP) if live else None
    D2 = depth2_rows(ctx, subs, so2, params, insts, Vs) if so2 is not None else pd.DataFrame()
    # per unit: the call, curves, the loser profile, words
    U, drill, L_rows = [], {}, []
    for ui, x in enumerate(insts):
        V = Vs[ui]
        U += _unit_row(ctx, x, V)
        d = {'unit': x.unit['id'], 'key': x.unit['key'], 'kind': x.unit['kind'], 'tier': x.unit.get('tier'), 'aliases': x.unit.get('aliases', []),
             'dir': x.d.tolist(), 'own_edges': x.own_edges, 'k': x.k, 'curves': [], 'depth2': [], 'losers': None}
        if len(T):
            mine = T[T['uix'] == ui]
            want = {}
            for r in mine[mine['drill'] != ''].itertuples(index=False):
                if r.drill == 'A' and getattr(r, 'list') != 'main':
                    continue
                k = (int(r.pid), H_ALL.index(int(r.h)))
                want[k] = 'A' if (r.drill == 'A' or want.get(k) == 'A') else 'B'
            for (pid, hi), why in sorted(want.items()):
                c = curve(ctx, x, V, params[pid], hi, why)
                if c is not None:
                    d['curves'].append(c)
        lp = loser_profile(ctx, x, V, so, ui, params)
        d['losers'] = lp
        for H, o in lp.items():
            for rank, lv in enumerate(o['wrong_levels'], 1):
                L_rows.append({'unit': x.unit['id'], 'h': int(H), 'list': 'wrong', 'rank': rank, **lv})
            for rank, lv in enumerate(o.get('cut_levels', []), 1):
                L_rows.append({'unit': x.unit['id'], 'h': int(H), 'list': 'cut', 'rank': rank, **lv})
        if len(D2):
            d['depth2'] = _clean(D2[D2['uix'] == ui].drop(columns=['uix'], errors='ignore').to_dict('records'))
        d['depth2_skipped'] = [{'p1': params[s['pid']].name, 'l1': params[s['pid']].levels[s['level']], 'n_A': s['n_A'], 'days_A': s['days_A']}
                               for s in subs if s['uix'] == ui and s['inst'] is None]
        drill[x.unit['id']] = d
    if len(T):
        T.insert(0, 'coin', _D['label'])
        T['twin'] = _D['twin']
        T['tier'] = [insts[i].unit.get('tier') for i in T['uix']]
        T['subset'] = [bool(insts[i].unit.get('subset', True)) for i in T['uix']]
        T['unit_kind'] = [insts[i].unit['kind'] for i in T['uix']]
        fns = {i: _unit_fn(ctx, insts[i].unit) for i in set(T['uix'])}
        T['unit_fn'] = [fns[i] for i in T['uix']]
        T['unit_family'] = [_unit_family(ctx, insts[i].unit) for i in T['uix']]
        T['unit_words'] = [unit_words(insts[i].unit) for i in T['uix']]
        T['dir'] = [int(insts[i].d[H_ALL.index(int(h))]) for i, h in zip(T['uix'], T['h'])]
        T = T.drop(columns=['uix'])
    Ud = pd.DataFrame(U)
    if len(Ud):
        Ud.insert(0, 'series', _D['label'])
        Ud['twin'] = _D['twin']
    if len(D2):
        D2 = D2.drop(columns=['uix'], errors='ignore')
        D2.insert(0, 'series', _D['label'])
        D2['twin'] = _D['twin']
    Ld = pd.DataFrame(L_rows)
    if len(Ld):
        Ld.insert(0, 'series', _D['label'])
        Ld['twin'] = _D['twin']
    pre = os.path.join(out, f'b{bid:05d}')
    sha = _write_csv(T, pre + '_top.csv.gz')
    # (pre-run audit W2) the slim copy the league's readers need (rank 1 of either list, the main list's top TOP_FULL):
    # the same rows and columns as the full table, which stays as it is
    T1 = T[((T['list'] == 'main') & (T['rank'] <= TOP_FULL)) | (T['rank'] == 1)] if len(T) else T
    sha1 = _write_csv(T1, pre + '_top1.csv.gz')
    _write_csv(Ud, pre + '_units.csv.gz')
    _write_csv(Ld, pre + '_losers.csv.gz')
    _write_csv(D2, pre + '_depth2.csv.gz')
    _dump(drill, pre + '_drill.json.gz', gz=True)
    _dump(summ.to_json(), pre + '_summary.json')
    clipped = int(sum(x.clipped for x in insts))
    return {'block': bid, 'units': len(insts), 'instances': int(sum(len(x.rows) for x in insts)), 'unit_days': int(sum(x.G for x in insts)),
            'params': so.n_params, 'top_sha256': sha, 'shard_bytes': shard_bytes, 'clipped': clipped, 'seconds': round(time.time() - t0, 1),
            'depth2_subsets': len(live), 'top1_sha256': sha1, 'top1_rows': int(len(T1))}


def _block_files(out: str, shards: str, bid: int) -> list:
    pre = f'b{bid:05d}_'
    fs = [os.path.join(out, f) for f in (sorted(os.listdir(out)) if os.path.isdir(out) else []) if f.startswith(pre)]
    sp = os.path.join(shards, f'drill_{bid:05d}.npz') if shards else ''
    return fs + ([sp] if sp and os.path.isfile(sp) else [])


def _drop_block_files(out: str, shards: str, bid: int):
    """A failed block's partial files go, so nothing on disk names a block meta.json does not list as done."""
    for p in _block_files(out, shards, bid):
        with contextlib.suppress(OSError):
            os.remove(p)


def _block_safe(bid: int) -> dict:
    """(Pre-run audit W4) _block_job, with an exception recorded instead of raised: the block is reported as failed
    (its partial files removed) and becomes one of meta.json's blocks_missing; every other block's result is kept."""
    try:
        t0 = time.time()
        print(f'  block {bid}: start ({len(_D["blocks"][bid])} units, rss {_rss_mb()} MB)', flush=True)
        r = _block_job(bid)
        print(f'  block {bid}: done in {time.time() - t0:.0f}s, {r.get("instances")} instances, rss {_rss_mb()} MB', flush=True)
        return r
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f'::warning::drill block {bid} failed: {e!r}\n{tb}', flush=True)
        _drop_block_files(_D.get('out', ''), _D.get('shards', ''), bid)
        return {'block': bid, 'error': repr(e), 'traceback': tb[-4000:]}


def _parse_blocks(s: str):
    if not s:
        return None
    out = set()
    for part in s.split(','):
        if '-' in part:
            a, b = part.split('-')
            out |= set(range(int(a), int(b) + 1))
        elif part:
            out.add(int(part))
    return sorted(out)


def series_ctx(asset: str, csv: str, twin: int = 0, procs: int = 0, hm2_series: str = '', chart: bool = True, log=print, **data_kw) -> tuple:
    """The drill context of one series from its data (capture_raw + heat_hm2.base(), then the drill's extras):
    returns (ctx, seconds per stage)."""
    procs = procs or min(4, os.cpu_count() or 1)
    t, sec, store = time.time(), {}, {}
    with capture_raw(store):
        ctx = hm.base(asset, csv, log=log, **{k: v for k, v in data_kw.items() if k in ('other_csvs', 'perp_csv', 'fund_csv', 'oi_csv', 'cal_csv',
                                                                                         'dom', 'found', 'main_meta', 'twin', 'other_metas',
                                                                                         'xdata')} | {'twin': twin})
    sec['base'] = round(time.time() - t, 1)
    sec.update(_prepare(ctx, store, (), hm2_series, engine=True, log=log, procs=procs, chart=chart))
    return ctx, sec


def run_series(asset: str, csv: str, out: str, units, twin: int = 0, procs: int = 0, part=(0, 1), blocks=None, twin_units: str = 'all',
               hm2_series: str = '', shards: str = '', ctx=None, raw: dict = None, max_units: int = None, strict: bool = True, log=print,
               chart: bool = True, **data_kw) -> dict:
    """One series (a coin or a twin): capture_raw + heat_hm2.base() -> drop HM2's entry matrices -> pct codes -> GBM
    readings -> proxy table -> directions of every HM1 level and the fire index -> this part's units (tiers in order;
    `blocks` to rerun) -> per block (fork workers over blocks): instances, own parameters, scan, lists, re-measure,
    specific, curves, depth 2, loser profiles -> files after each block. meta.json (schema oracle-heat-hm2-drill-1):
    units sha, blocks done, A_CAP, clipped counts, the league check, seconds per stage, peak RSS, the top tables'
    sha256. ctx: a ready drill context (tests)."""
    _refuse_doge(asset, csv)
    os.makedirs(out, exist_ok=True)
    procs = procs or min(4, os.cpu_count() or 1)
    t_start, sec = time.time(), {}
    U = _read_json(units) if isinstance(units, str) else units
    if U is None or U.get('schema') != SCHEMA_UNITS:
        raise SystemExit('units: not an oracle-heat-hm2-drill-units-1 file')
    if ctx is None:
        ctx, s0 = series_ctx(asset, csv, twin=twin, procs=procs, hm2_series=hm2_series, chart=chart, log=log, **data_kw)
        sec.update(s0)
    label = ctx.label
    coin = asset
    ulist = [dict(u) for u in U['coins'].get(coin, [])]
    if not ulist:
        raise SystemExit(f'{coin}: no units in the unit list')
    ulist += [u for u in chart_units(ctx, coin) if u['id'] not in {v['id'] for v in ulist}]
    sub = quarter_subset(ulist)
    for u in ulist:
        u['subset'] = u['id'] in sub
    if twin and twin_units == 'quarter':
        ulist = [u for u in ulist if u['subset']]
    if max_units:
        ulist = ulist[:max_units]
    t = time.time()
    # (pre-run audit W6/F5) real coins stay strict; a twin lists the unit keys it cannot resolve and carries on (a
    # unit with no reading on a twin has no fires there: it is absent from that twin, nothing is tuned toward the coin)
    kept, unknown = prepare_units(ctx, ulist, log, strict=strict and not twin)
    if unknown:
        log(f'{label}: {len(unknown)} unit keys unknown on this series (kept running): {[x["id"] for x in unknown]}')
    sec['units'] = round(time.time() - t, 1)
    bl = plan_blocks(ctx, kept, part)
    todo = list(range(len(bl))) if blocks is None else [b for b in blocks if b < len(bl)]
    shards = shards or os.path.join(out, 'shards')
    _D.clear()
    _D.update(ctx=ctx, units=kept, blocks=bl, params=ctx.params, out=out, label=label, twin=int(twin), real=bool(ctx.real), shards=shards)
    mp = os.path.join(out, 'meta.json')
    old = _read_json(mp) if blocks is not None else None
    done = {int(r['block']): r for r in (old or {}).get('blocks_done', [])}
    t = time.time()
    # (pre-run audit W3/W4) a failed block is recorded (blocks_failed, blocks_missing), the other blocks are kept; a
    # killed worker breaks the pool at once (BrokenProcessPool): what finished before is written to meta.json, the rest
    # is missing, and the job then stops
    fin, pool_error = [], None
    rss_before = _rss_mb()
    log(f'{label}: {len(todo)} blocks on {procs} workers; the process holds {rss_before} MB before the blocks')
    try:
        _fork_map(_block_safe, todo, procs, done=fin)
    except Exception as e:                  # BrokenProcessPool (an OOM kill) or another pool failure
        pool_error = repr(e)
        log(f'::error::{label}: the block pool failed: {pool_error}; {len(fin)} of {len(todo)} blocks finished')
    sec['blocks'] = round(time.time() - t, 1)
    failed = []
    fin_ids = {int(b) for b, _ in fin}
    for b, r in fin:
        if r is None or 'error' in r:
            failed.append({'block': int(b), 'error': (r or {}).get('error', 'no result'), 'traceback': (r or {}).get('traceback')})
            done.pop(int(b), None)
        else:
            done[int(r['block'])] = r
    for b in todo:                          # a block the broken pool never finished: no file of it may stay
        if int(b) not in fin_ids:
            _drop_block_files(out, shards, int(b))
            done.pop(int(b), None)
            failed.append({'block': int(b), 'error': pool_error or 'not run', 'traceback': None})
    for f in failed:
        log(f'::warning::{label}: block {f["block"]} missing: {f["error"]}')
    unk_ids = [x['id'] for x in unknown]
    meta = {'schema': SCHEMA_SERIES, 'asset': asset, 'label': label, 'twin': int(twin), 'real': bool(ctx.real), 'part': list(part),
            'units_sha256': U.get('sha256'), 'hm2_nongate_sha256': U.get('hm2_nongate_sha256'), 'twin_units': twin_units,
            'units': {'listed': len(ulist), 'run': len(kept), 'unknown': unknown, 'copies': sum(len(u.get('copies', [])) for u in kept),
                      'tiers': {str(t_): sum(1 for u in kept if int(u['tier']) == t_) for t_ in (1, 2, 3)},
                      'unknown_n': len(unknown), 'unknown_eg': unk_ids[:20], 'strict': bool(strict and not twin)},
            'blocks_total': len(bl), 'blocks_done': [done[k] for k in sorted(done)], 'blocks_missing': [b for b in range(len(bl)) if b not in done],
            'block_units': [[kept[i]['id'] for i in b] for b in bl],
            'A_CAP': A_CAP, 'clipped': int(sum(r['clipped'] for r in done.values())), 'league_check': None,
            'pct': getattr(ctx, 'pct_check', None), 'part_effects_check_max_abs_odds': getattr(ctx, 'part_check', None),
            'gbm': [R['name'] for R in ctx.gbm], 'chart': getattr(ctx, 'chart_info', None), 'params': len(ctx.params),
            'param_names': [p.name for p in ctx.params], 'horizons': H_ALL, 'tracks': list(TRACKS),
            'splits': {s: [str(pd.Timestamp(a, unit='ms')), str(pd.Timestamp(b, unit='ms'))] for s, (a, b) in heat.SPLITS.items()},
            'table_sha256': hashlib.sha256(''.join(done[k]['top_sha256'] or '' for k in sorted(done)).encode()).hexdigest(),
            'blocks_failed': failed, 'pool_error': pool_error, 'pack_check': None,
            'seconds': {**sec, **getattr(ctx, 'drill_sec', {})}, 'seconds_total': round(time.time() - t_start, 1), 'peak_rss_mb': _rss_mb(),
            'rss_before_blocks_mb': rss_before, 'procs': int(procs)}
    _dump(meta, mp, indent=1)               # (W4) on disk before the checks: a failing check never loses the blocks
    if pool_error is not None:
        raise SystemExit(f'{label}: the block pool failed ({pool_error}); meta.json lists {len(meta["blocks_missing"])} missing blocks')
    if not twin:
        insts = {}
        try:
            for u in kept[:2000]:
                if u.get('league'):
                    insts[u['id']] = split_instances(ctx, u, u['rows'])
            lc = check_league(kept, insts, ctx)
            log(f'{label}: league check: {lc["checked"]} rows, {lc["n_differ"]} counts and {lc["d_differ"]} directions differ')
        except Exception as e:
            lc = {'error': repr(e)}
            log(f'::warning::{label}: league check failed: {e!r}')
        meta['league_check'] = lc
        del insts
        try:                                # (pre-run audit C3) the HM2 pack's calls against the drill's fire rule
            pc = check_pack(kept, lambda u: split_instances(ctx, u, u['rows']), ctx)     # one unit's instances at a time
            log(f'{label}: pack check: {pc["checked"]} rows, n_A {pc["n_A_differ"]}, n_B {pc["n_B_differ"]}, onset direction '
                f'{pc["onset_dir_differ"]} of {pc["onset_dir_checked"]} and pack direction {pc["pack_dir_differ"]} differ')
        except Exception as e:
            pc = {'error': repr(e)}
            log(f'::warning::{label}: pack check failed: {e!r}')
        meta['pack_check'] = pc
        meta['seconds_total'] = round(time.time() - t_start, 1)
        meta['peak_rss_mb'] = _rss_mb()
        _dump(meta, mp, indent=1)
    log(f'{label}: {len(kept)} units in {len(bl)} blocks ({len(todo)} run, {len(failed)} failed) in {meta["seconds_total"]}s, '
        f'peak {meta["peak_rss_mb"]} MB')
    return meta


def _exit_if_blocks_failed(meta: dict) -> None:
    """(post-audit review of W4) run_series keeps a failed block's record in meta.json and returns; the series job
    must still exit non-zero so the run shows the series is incomplete (the workflow moves the shards and puts the
    small files first, then fails the step)."""
    f = meta.get('blocks_failed') or []
    if f:
        raise SystemExit(f'{meta.get("label")}: {len(f)} blocks failed: {[int(x["block"]) for x in f]} '
                         f'(meta.json lists them under blocks_failed and blocks_missing)')


def bench(asset: str, csv: str, out: str, units, n_units: int = 200, procs: int = 0, hm2_series: str = '', log=print, chart: bool = True,
          **data_kw) -> dict:
    """BTC: n_units units stratified by timeframe and kind, every parameter, the depth-2 drill; prints ms per
    instance-parameter, projected minutes per series at S = 1, 2, 3, peak RSS and the projected shard size. A block's
    seconds are one worker's; the series job runs its part's blocks on `procs` workers, so a part's block time is its
    worker time over min(procs, the part's blocks), the blocks from the units' days (BLOCK_UNIT_DAYS)."""
    os.makedirs(out, exist_ok=True)
    procs = procs or min(4, os.cpu_count() or 1)          # as run_series (the series job passes --procs 4)
    U = _read_json(units) if isinstance(units, str) else units
    ul = U['coins'][asset]
    by = {}
    for u in ul:
        tf = _tf_name(u.get('when') or u['key'])
        by.setdefault((u['kind'], tf), []).append(u)
    rng = np.random.default_rng(20261111)
    pick = []
    keys = sorted(by)
    while len(pick) < min(n_units, len(ul)):
        for k in keys:
            if by[k] and len(pick) < n_units:
                pick.append(by[k].pop(int(rng.integers(len(by[k])))))
    sub = {**U, 'coins': {asset: pick}}
    t = time.time()
    twin = int(data_kw.pop('twin', 0) or 0)
    ctx, s0 = series_ctx(asset, csv, twin=twin, procs=procs, hm2_series=hm2_series, chart=chart, log=log, **data_kw)
    meta = run_series(asset, csv, out, sub, twin=twin, procs=procs, hm2_series=hm2_series, ctx=ctx, strict=False, log=log, chart=chart, **data_kw)
    meta['seconds'] = {**s0, **meta['seconds']}
    inst = sum(r['instances'] for r in meta['blocks_done'])
    wsec = sum(r['seconds'] for r in meta['blocks_done'])
    ms_ip = 1000.0 * wsec / max(inst * meta['params'], 1)
    # the whole series as its job would hold it (every unit, Part 4's chart units too): capped instances and unit-days,
    # so the sample scales by instances (the block time goes with them), not by its share of the units
    full = [dict(u) for u in ul]
    ids = {u['id'] for u in full}
    full += [u for u in chart_units(ctx, asset) if u['id'] not in ids]
    kept_all, unk_all = prepare_units(ctx, full, log, strict=False)      # (pre-run audit W6) the unknown keys of the whole unit set
    inst_all = unit_days = 0
    for u in kept_all:
        r_ = np.r_[_cap(ctx.g.in_split(u['rows'], 'A'), u['key']), ctx.g.in_split(u['rows'], 'B')]
        inst_all += len(r_)
        unit_days += len(np.unique(ctx.g.day[r_]))
    del kept_all
    scale = inst_all / max(inst, 1)
    base_min = sum(v for k, v in meta['seconds'].items() if k != 'blocks') / 60.0
    worker_min = wsec / 60.0 * scale                     # every unit's block time, one worker

    def workers(S):
        return int(min(procs, max(1, math.ceil(unit_days / S / BLOCK_UNIT_DAYS))))

    def wall(S):
        return base_min + worker_min / S / workers(S)
    shard = sum(r['shard_bytes'] for r in meta['blocks_done']) * scale
    res = {'schema': SCHEMA_BENCH, 'asset': asset, 'units_run': len(pick), 'units_total': len(full), 'instances': inst, 'params': meta['params'],
           'ms_per_instance_param': round(ms_ip, 6), 'base_minutes': round(base_min, 1), 'worker_minutes': round(worker_min, 1),
           'unit_days': int(unit_days), 'workers': {str(S): workers(S) for S in (1, 2, 3)},
           'projected_minutes': {str(S): round(wall(S), 1) for S in (1, 2, 3)},
           'parts_needed': next((S for S in range(1, 65) if wall(S) <= 300.0), 64), 'projected_shard_gb': round(shard / 1e9, 2),
           'peak_rss_mb': _rss_mb(), 'rss_before_blocks_mb': meta.get('rss_before_blocks_mb'), 'procs': int(procs), 'blocks_total_run': meta['blocks_total'],
           'seconds': round(time.time() - t, 1), 'instances_total': int(inst_all),
           'units_unknown': len(unk_all), 'units_unknown_eg': unk_all[:5],
           # (post-audit review of W4) a bench block that failed is out of ms_per_instance_param: listed, never silent
           'blocks_failed': [int(f['block']) for f in meta.get('blocks_failed', [])], 'blocks_total': meta['blocks_total']}
    if res['blocks_failed']:
        log(f'::warning::bench: {len(res["blocks_failed"])} of {meta["blocks_total"]} blocks failed {res["blocks_failed"]}; '
            f'the projection is over the other blocks')
    _dump(res, os.path.join(out, 'bench.json'), indent=1)
    log(json.dumps(res, indent=1))
    return res


# ============================================================================================================ league
def find_series(inputs: str) -> dict:
    """{label: [dir, ...]} of every drill series meta.json (schema oracle-heat-hm2-drill-1) under inputs."""
    out = {}
    for root, dirs, files in os.walk(os.path.abspath(inputs)):
        dirs[:] = sorted(d for d in dirs if d not in ('shards', 'league'))
        if 'meta.json' not in files:
            continue
        mt = _read_json(os.path.join(root, 'meta.json'))
        if not isinstance(mt, dict) or mt.get('schema') != SCHEMA_SERIES:
            continue
        _refuse_doge(mt.get('label'), mt.get('asset'), root)
        out.setdefault(str(mt['label']), []).append((root, mt))
    return out


def _cat(dirs: list, suffix: str) -> pd.DataFrame:
    fr = []
    for d, _ in dirs:
        for f in sorted(os.listdir(d)):
            if f.endswith(suffix):
                try:
                    x = pd.read_csv(os.path.join(d, f), low_memory=False)
                except pd.errors.EmptyDataError:
                    continue
                if len(x):
                    fr.append(x)
    return pd.concat(fr, ignore_index=True) if fr else pd.DataFrame()


def load_league_inputs(inputs: str, log=_log_none) -> dict:
    S = find_series(inputs)
    out = {'series': {}, 'top': [], 'units': [], 'losers': [], 'depth2': [], 'summ': {}, 'coverage': {}}
    for label, dirs in sorted(S.items()):
        mt = dirs[0][1]
        miss = []
        for d, m in dirs:
            if m.get('blocks_missing'):
                miss.append({'dir': d, 'missing': m['blocks_missing']})
        out['coverage'][label] = {'parts': [m.get('part') for _, m in dirs], 'missing': miss}
        if miss:
            log(f'  WARNING {label}: missing blocks {miss}')
        out['series'][label] = {'asset': mt['asset'], 'twin': int(mt['twin']), 'twin_units': mt.get('twin_units', 'all'), 'metas': [m for _, m in dirs]}
        for k, suf in (('top', '_top.csv.gz'), ('units', '_units.csv.gz'), ('losers', '_losers.csv.gz'), ('depth2', '_depth2.csv.gz')):
            x = _cat(dirs, suf)
            if len(x):
                x['series'] = label
                x['asset'] = mt['asset']
                x['twin'] = int(mt['twin'])
                out[k].append(x)
        sm = SummaryCounts()
        for d, _ in dirs:
            for f in sorted(os.listdir(d)):
                if f.endswith('_summary.json'):
                    sm.merge(SummaryCounts.from_json(_read_json(os.path.join(d, f))))
        out['summ'][label] = sm
    for k in ('top', 'units', 'losers', 'depth2'):
        out[k] = pd.concat(out[k], ignore_index=True) if out[k] else pd.DataFrame()
    return out


def _med_range(v: list) -> dict:
    v = [float(x) for x in v if x is not None and x == x]
    if not v:
        return {'median': None, 'min': None, 'max': None, 'sets': 0}
    return {'median': float(np.median(v)), 'min': float(min(v)), 'max': float(max(v)), 'sets': len(v)}


def _share(a, b):
    return float(a) / float(b) if b else None


def chance_metrics(top1: pd.DataFrame) -> dict:
    """Counts of one series' A top-1 rows of one (H, track, mode, list): units ranked, top-1 z_adj, kept share on B,
    t_B >= 2 share, gate heat p99 and max."""
    x = top1
    n = len(x)
    gh = x['gheat_B'].dropna().to_numpy() if 'gheat_B' in x else np.array([])
    return {'units': int(n), 'z_median': float(x['z'].median()) if n else None, 'z_p90': float(x['z'].quantile(0.9)) if n else None,
            'kept': _share(int(x['kept'].sum()), n), 'kept_nonthin': _share(int((x['kept'] & ~x['thin']).sum()), int((~x['thin']).sum())),
            'tb2': _share(int(x['tb2'].sum()), n), 'gheat_p99': float(np.quantile(gh, 0.99)) if len(gh) else None,
            'gheat_max': float(gh.max()) if len(gh) else None, 'sd_t_day_B': float(np.nanstd(x['t_day_B'].to_numpy() *
                                                                                              np.where(x['mode'] == 'take', 1, -1))) if n > 2 else None}


def chance_table(L: dict, same_units: bool = False) -> dict:
    """Per H, track and mode (main list; the in-sample list apart): real (per coin and pooled) against the twins'
    median and range of every count; by tier and by clustering; 'drill B' curves are never counted. same_units: under
    the twin fallback every count is on the same units on both sides (tier 1 and 2 plus the seeded quarter)."""
    T = L['top']
    out = {}
    if not len(T):
        return out
    t1 = T[T['rank'] == 1].copy()
    if same_units:
        t1 = t1[t1['subset'].astype(bool)]
    ser = L['series']
    assets = sorted({v['asset'] for v in ser.values()})
    for (h, tr, mode, lst), g in t1.groupby(['h', 'track', 'mode', 'list']):
        key = f'{int(h)}|{tr}|{mode}|{lst}'
        o = {'coins': {}, 'pooled': {}}
        real = g[g['twin'] == 0]
        tw = g[g['twin'] != 0]
        o['pooled']['real'] = chance_metrics(real)
        per_seed = [chance_metrics(y) for _, y in tw.groupby('twin')]
        o['pooled']['twins'] = {k: _med_range([m[k] for m in per_seed]) for k in (per_seed[0] if per_seed else {})}
        tmax = max([m['gheat_max'] for m in per_seed if m['gheat_max'] is not None], default=None)
        o['pooled']['above_twin_max'] = int((real['gheat_B'] > tmax).sum()) if tmax is not None else None
        for a in assets:
            r = real[real['asset'] == a]
            ts = [chance_metrics(y) for _, y in tw[tw['asset'] == a].groupby('twin')]
            o['coins'][a] = {'real': chance_metrics(r), 'twins': {k: _med_range([m[k] for m in ts]) for k in (ts[0] if ts else {})}}
        o['by_tier'] = {str(t_): {'real': chance_metrics(real[real['tier'] == t_]),
                                  'twins': _med_range([chance_metrics(y)['kept'] for _, y in tw[tw['tier'] == t_].groupby('twin')])}
                        for t_ in sorted(g['tier'].dropna().unique())}
        o['by_clustering'] = {('week' if w else 'day'): {'real': chance_metrics(real[real['week_weaker_A'] == w]),
                                                         'twins_kept': _med_range([chance_metrics(y)['kept'] for _, y in
                                                                                   tw[tw['week_weaker_A'] == w].groupby('twin')])}
                              for w in (0, 1)}
        out[key] = o
    # depth-2 paths and the loser profile's top level
    D2 = L['depth2']
    if len(D2) and 'path' in D2:
        p = D2[D2['path'].astype(bool)]
        for (h, tr), g in p.groupby(['origin_h', 'origin_track']):
            real = g[g['twin'] == 0]
            seeds = [float(y['path_kept'].mean()) for _, y in g[g['twin'] != 0].groupby('twin')]
            out[f'{int(h)}|{tr}|depth2'] = {'real_kept': float(real['path_kept'].mean()) if len(real) else None, 'twins_kept': _med_range(seeds),
                                            'units': int(len(real))}
    Lo = L['losers']
    if len(Lo):
        top = Lo[(Lo['rank'] == 1) & (Lo['list'] == 'wrong')]
        for h, g in top.groupby('h'):
            real = g[g['twin'] == 0]
            seeds = [float(y['kept'].astype(bool).mean()) for _, y in g[g['twin'] != 0].groupby('twin')]
            out[f'{int(h)}|loser_top'] = {'real_kept': float(real['kept'].astype(bool).mean()) if len(real) else None, 'twins_kept': _med_range(seeds)}
    return out


def persistence(L: dict) -> dict:
    """The kept share by A z_adj bin (under 2, 2-3, 3-4, 4-5, 5 and over), for all separators, by family and by
    specific_A (at or under 0, over 0), real (pooled) against the twins' median and range (per seed, pooled)."""
    out = {}
    fr = []
    for label, sm in L['summ'].items():
        f = sm.frame()
        if len(f):
            f['twin'] = L['series'][label]['twin']
            fr.append(f)
    if not fr:
        return out
    F = pd.concat(fr, ignore_index=True)
    F = F[F['list'] == 'main']
    zl = ['under 2', '2-3', '3-4', '4-5', '5 and over']

    def curve_of(x, by=None):
        res = {}
        for keys, g in (x.groupby(by) if by else [('all', x)]):
            real = g[g['twin'] == 0].groupby('zbin')[['ranked', 'kept']].sum()
            tw = g[g['twin'] != 0].groupby(['twin', 'zbin'])[['ranked', 'kept']].sum()
            row = {}
            for zb in range(5):
                r = real.loc[zb] if zb in real.index else None
                seeds = [float(tw.loc[(t_, zb), 'kept'] / tw.loc[(t_, zb), 'ranked']) for t_ in sorted({i[0] for i in tw.index})
                         if (t_, zb) in tw.index and tw.loc[(t_, zb), 'ranked'] > 0]
                row[zl[zb]] = {'real_n': int(r['ranked']) if r is not None else 0,
                               'real_kept': float(r['kept'] / r['ranked']) if r is not None and r['ranked'] else None, 'twins': _med_range(seeds)}
            res[str(keys)] = row
        return res
    for (h, tr, mode), g in F.groupby(['h', 'track', 'mode']):
        k = f'{H_ALL[int(h)]}|{TRACKS[int(tr)]}|{MODES[int(mode)]}'
        out[k] = {'all': curve_of(g)['all'], 'by_family': curve_of(g, 'family'),
                  'by_specific_A': curve_of(g.assign(sp=g['spec'].map({0: 'at or under 0', 1: 'over 0', 2: 'NA'})), 'sp')}
    return out


def twin_marks(real: pd.DataFrame, tw: pd.DataFrame, same_units: bool = False) -> tuple:
    """(review fix) The "above the twins' maximum" mark of real rows against the twin rows of the same list, on the same
    units on both sides. Without the twin fallback the twins ran every unit: the max is over all the list's twin rows.
    Under it (same_units: the twins ran tier 1 and 2 plus a seeded quarter of tier 3) the max is over the twins' rows
    of those units only, and only the real rows of those units (column 'subset') are marked against it; the real
    coin's other units get no max mark (None) and are marked against the twins' p99 instead (Part 3 review: "the real
    coin's other units carry the twins' p99 per unit, not the maximum"). Returns (above_max, above_p99, mark) arrays
    aligned with real: mark is 'max', 'p99' or '' (no twin rows)."""
    v = real['gheat_B'].to_numpy(float)
    sub = real['subset'].astype(bool).to_numpy() if (same_units and 'subset' in real) else np.ones(len(real), bool)
    t = tw[tw['subset'].astype(bool)] if (same_units and 'subset' in tw) else tw
    tv = t['gheat_B'].to_numpy(float)
    tv = tv[np.isfinite(tv)]
    above_max = np.full(len(real), None, dtype=object)
    above_p99 = np.full(len(real), None, dtype=object)
    mark = np.full(len(real), '', dtype=object)
    if not len(tv):
        return above_max, above_p99, mark
    tmax, tp99 = float(tv.max()), float(np.quantile(tv, 0.99))
    for i in range(len(real)):
        if sub[i]:
            above_max[i], mark[i] = bool(v[i] > tmax), 'max'
        else:
            above_p99[i], mark[i] = bool(v[i] > tp99), 'p99'
    return above_max, above_p99, mark


def league_views(L: dict, per_call: int = PER_CALL, per_param: int = PER_PARAM, n: int = 40, same_units: bool = False) -> pd.DataFrame:
    """Per H and track (right, move, profit): units ranked by the gate heat on B of their A-chosen top-1 take gate, and
    a second list by their top-1 skip gate (main list), at most per_call rows per call and per_param per parameter,
    near-copies collapsed (alias_of); above_twin_max against the twins' max of the same list, on the same units on
    both sides (twin_marks: under the twin fallback, units outside the seeded quarter carry above_twin_p99 instead)."""
    T = L['top']
    if not len(T):
        return pd.DataFrame()
    t1 = T[(T['rank'] == 1) & (T['list'] == 'main') & (T.get('alias_of', -1) == -1)].copy()
    rows = []
    for (h, tr, mode), g in t1.groupby(['h', 'track', 'mode']):
        real = g[g['twin'] == 0].sort_values('gheat_B', ascending=False)
        am, ap, mk = twin_marks(real, g[g['twin'] != 0], same_units)
        pc, pp, k = {}, {}, 0
        for i, r in enumerate(real.itertuples(index=False)):
            if k >= n:
                break
            if pc.get((r.asset, r.unit), 0) >= per_call or pp.get(r.param, 0) >= per_param:
                continue
            pc[(r.asset, r.unit)] = pc.get((r.asset, r.unit), 0) + 1
            pp[r.param] = pp.get(r.param, 0) + 1
            k += 1
            d = r._asdict()
            d['above_twin_max'], d['above_twin_p99'], d['twin_mark'] = am[i], ap[i], mk[i]
            d['list_rank'] = k
            rows.append(d)
    return pd.DataFrame(rows)


def family_table(L: dict) -> pd.DataFrame:
    """Per family: the share of units whose top-1 separator (main, take, right) is in it and the share of those that
    kept on B, real against the twins."""
    T = L['top']
    if not len(T):
        return pd.DataFrame()
    t1 = T[(T['rank'] == 1) & (T['list'] == 'main') & (T['mode'] == 'take') & (T['track'] == 'right')]
    rows = []
    for (h, fam), g in t1.groupby(['h', 'family']):
        tot = t1[t1['h'] == h]
        r = g[g['twin'] == 0]
        nr = int((tot['twin'] == 0).sum())
        seeds = [len(y) / max(int((tot['twin'] == t_).sum()), 1) for t_, y in g[g['twin'] != 0].groupby('twin')]
        rows.append({'h': int(h), 'family': fam, 'real_share': len(r) / nr if nr else None, 'real_kept': float(r['kept'].mean()) if len(r) else None,
                     'twins_share': _med_range(seeds)['median'], 'twins_kept': float(g[g['twin'] != 0]['kept'].mean()) if (g['twin'] != 0).any() else None})
    return pd.DataFrame(rows)


def _curve_shapes(inputs_drill: dict) -> dict:
    out = {}
    for label, dj in inputs_drill.items():
        for uid, d in dj.items():
            for c in d.get('curves', []):
                out[(label, uid, c['param'], int(c['h']))] = c
    return out


def _real_curves(curves: dict) -> pd.DataFrame:
    """The real series' curves (labels without '~twin') as rows (unit, param, shape), one per curve."""
    rows = [(k[1], k[2], c.get('shape')) for k, c in (curves or {}).items() if k[0] and '~' not in str(k[0])]
    return pd.DataFrame(rows, columns=['unit', 'param', 'shape'])


def ta_cards(T: pd.DataFrame, curves: dict = None, top: int = 10) -> list:
    """(review) One card per TA function (HM2's usage-card name rule: RSI14 -> RSI), candlestick pattern, chart pattern
    and data family of the unit, over all its units, levels, settings, timeframes, coins and the six horizons. Per
    track (right and profit first): the separators most often top 5 on A across its units, each with the share of those
    units where it kept on B with t_B >= 2, its median B lift, its curves' most common shape (the real series' curves;
    a tie goes to the first name in sort order), the twins' median and range of the same share; the skip levels the
    same way; the units behind each line. Each unit counts once per card line. Grouped operations over the whole table
    (one pass per statistic, not one per line: the league holds millions of top rows)."""
    if not len(T):
        return []
    x = T[(T['list'] == 'main') & (T['rank'] <= TOP_FULL)]
    x = x[x['unit_fn'].notna()].reset_index(drop=True)
    if not len(x):
        return []
    K = ['unit_fn', 'track', 'mode', 'param']
    units_real = x[x['twin'] == 0].groupby('unit_fn')['unit'].nunique()
    y = x[x['track'].isin(('right', 'profit', 'move')) & x['mode'].isin(MODES) & x['param'].notna()]
    rl = y[y['twin'] == 0]
    R = rl.drop_duplicates(K + ['asset', 'unit'])                                  # each unit once per line (its first row)
    G = rl[rl['kept'] & rl['tb2']].drop_duplicates(K + ['asset', 'unit'])
    W = y[y['twin'] != 0].drop_duplicates(K + ['twin', 'asset', 'unit'])
    n_real = R.groupby(K).size()
    n_good = G.groupby(K).size()
    med = R.groupby(K)['lift_B_mode'].median()
    seeds = {}
    if len(W):
        ws = (W['kept'] & W['tb2']).astype(float).groupby([W[k] for k in K] + [W['twin']]).mean()
        for key, v in ws.items():
            seeds.setdefault(key[:-1], []).append(float(v))
    lv = R[K].assign(lv=R['level_label'].astype(str)).drop_duplicates().sort_values(K + ['lv'], kind='stable')
    lv = lv.groupby(K).head(5).groupby(K)['lv'].agg(list)
    ui = R[K + ['unit']].drop_duplicates().sort_values(K + ['unit'], kind='stable')
    ui = ui.groupby(K).head(20).groupby(K)['unit'].agg(list)
    C = _real_curves(curves)
    shape = {}
    if len(C) and len(R):
        C['shape'] = C['shape'].map(lambda v: '\x00none' if v is None else str(v))
        J = R[K + ['unit']].drop_duplicates().merge(C, on=['unit', 'param'], how='inner')
        if len(J):
            cnt = J.groupby(K + ['shape']).size().rename('n').reset_index().sort_values(K + ['n', 'shape'], ascending=[True] * 4 + [False, True],
                                                                                          kind='stable')
            for r in cnt.drop_duplicates(K).itertuples(index=False):
                shape[(r.unit_fn, r.track, r.mode, r.param)] = None if r.shape == '\x00none' else r.shape
    lines = {}
    for key, n in n_real.items():
        lines.setdefault(key[:3], []).append({
            'param': key[3], 'units': int(n), 'kept_tb2_share': _share(int(n_good.get(key, 0)), int(n)), 'median_lift_B': float(med[key]),
            'shape': shape.get(key), 'twins': _med_range(seeds.get(key, [])), 'levels': lv.get(key, []), 'unit_ids': ui.get(key, [])})
    for key in seeds:                                       # a line the twins have and the real coin has not
        if key not in n_real.index:
            lines.setdefault(key[:3], []).append({'param': key[3], 'units': 0, 'kept_tb2_share': None, 'median_lift_B': None, 'shape': None,
                                                  'twins': _med_range(seeds[key]), 'levels': [], 'unit_ids': []})
    cards = []
    for fn in sorted(x['unit_fn'].unique(), key=str):
        card = {'card': fn, 'units_real': int(units_real.get(fn, 0)), 'tracks': {}}
        for tr in ('right', 'profit', 'move'):
            for mode in MODES:
                ln = sorted(lines.get((fn, tr, mode), []), key=lambda d: (-d['units'], d['param']))
                card['tracks'][f'{tr}|{mode}'] = ln[:top]
        cards.append(card)
    cards.sort(key=lambda c: (-c['units_real'], c['card']))
    return cards


def column_cards(T: pd.DataFrame, curves: dict = None) -> list:
    """(review) One card per parameter (column): the units for which it is top 5 on A, the share of them where it kept
    on B with t_B >= 2, real against the twins' median and range, by family of the unit and by horizon; the level that
    helps (most frequent take level) and the one that hurts (most frequent skip level); its curve pooled over those units
    (instance-weighted, A and B, by decile rank). Columns clear of the highest twin set first; none left out."""
    curves = curves or {}
    if not len(T):
        return []
    x = T[(T['list'] == 'main') & (T['rank'] <= TOP_FULL)]
    by_param = {}
    for k, c in curves.items():                             # the real series' curves, by parameter (one pass)
        if k[0] and not str(k[0]).count('~'):
            by_param.setdefault(k[2], []).append(c)
    out = []
    for prm, g in x.groupby('param'):
        real = g[g['twin'] == 0]
        ru = real.drop_duplicates(['asset', 'unit', 'h', 'track', 'mode'])
        share = _share(int((ru['kept'] & ru['tb2']).sum()), len(ru))
        seeds = []
        for t_, w in g[g['twin'] != 0].groupby('twin'):
            wu = w.drop_duplicates(['asset', 'unit', 'h', 'track', 'mode'])
            seeds.append(_share(int((wu['kept'] & wu['tb2']).sum()), len(wu)))
        tw = _med_range(seeds)
        helps = real[real['mode'] == 'take']['level_label'].astype(str).value_counts()
        hurts = real[real['mode'] == 'skip']['level_label'].astype(str).value_counts()
        by = {}
        for (fam, h), z in ru.groupby(['unit_family', 'h']):
            by[f'{fam}|{int(h)}'] = {'units': int(len(z)), 'kept_tb2_share': _share(int((z['kept'] & z['tb2']).sum()), len(z))}
        pooled = {}
        cs = by_param.get(prm, [])
        for s in ('A', 'B'):
            nb_ = max((len(c[s]['n']) for c in cs), default=0)
            n = np.zeros(nb_)
            od = np.zeros(nb_)
            for c in cs:
                nn = np.asarray(c[s]['n'], float)
                oo = np.nan_to_num(np.asarray(c[s]['odds'], float))
                n[:len(nn)] += nn
                od[:len(nn)] += nn * oo
            with np.errstate(all='ignore'):
                pooled[s] = {'n': n.tolist(), 'odds': (od / n).tolist()}
        out.append({'param': prm, 'family': str(g['family'].iloc[0]), 'units_top5': int(ru['unit'].nunique()), 'kept_tb2_share': share, 'twins': tw,
                    'clear_of_twins': bool(share is not None and tw['max'] is not None and share > tw['max']),
                    'helps': helps.index[0] if len(helps) else None, 'hurts': hurts.index[0] if len(hurts) else None, 'by_family_h': by,
                    'pooled_curve': pooled})
    out.sort(key=lambda c: (not c['clear_of_twins'], -(c['kept_tb2_share'] or 0), c['param']))
    return out


def gate_rows(T: pd.DataFrame, Ud: pd.DataFrame, D2: pd.DataFrame = None, lists: dict = PACK_LISTS, same_units: bool = False) -> list:
    """Pack rows of kind 'gate' (one condition) and 'gate2' (the depth-2 path) per real coin and PACK_H by PACK_LISTS:
    on the calls the bot loads (tier 1 and 2): the top 40 take gates by right-track gate heat, the top 20 by
    profit-track gate heat, the top 20 skip gates (right) and the top 10 (profit); gated calls of other units: the top
    20 by right-track gate heat; depth-2 paths: the top 10 by gate heat (depth2_rows' gheat_B: the one-condition rule on
    the path and the gate's other instances); at most PER_CALL rows per call in each list.
    Fire rule: a gate row fires when its `when` call fires at a minute close and every condition holds its level at the
    last closed bar of its own timeframe (own parameters from the call's own fire history); a take row enters at the
    next minute's open, a skip row blocks the call at that close. above_twin_max: against the max of the coin's twins
    over the same list (the same tier filter, track and mode) on the same units (twin_marks: under the twin fallback,
    real units outside the seeded quarter carry above_twin_p99 instead)."""
    rows = []
    if not len(T):
        return rows
    t1 = T[(T['twin'] == 0) & (T['list'] == 'main') & (T['rank'] == 1) & T['h'].isin(PACK_H)].copy()
    twin1 = T[(T['twin'] != 0) & (T['list'] == 'main') & (T['rank'] == 1) & T['h'].isin(PACK_H)]
    calls = {}
    if len(Ud):
        for r in Ud[Ud['twin'] == 0].itertuples(index=False):
            calls[(r.unit, int(r.h))] = r

    def mk(r, kind, lst, conds, extra=None):
        c = calls.get((r.unit, int(r.h)))
        sgn = 1 if r.mode == 'take' else -1
        row = {'coin': r.asset, 'h': int(r.h), 'kind': kind, 'list': lst, 'key': f"{r.unit.split('|', 2)[2]} | " + ' & '.join(f'{n}={"|".join(lv)}' for n, lv in conds),
               'when': {'key': r.unit.split('|', 2)[2], 'kind': r.unit_kind, 'unit': r.unit}, 'conds': conds, 'mode': r.mode, 'track': r.track,
               'dir': int(r.dir), 'call': 'up' if r.dir > 0 else 'down', 'fire': 'when call fires and every condition holds; take: enter next open; skip: block',
               'n': None if c is None else int(c.n_B), 'odds': None if c is None else float(c.odds_B), 'wd': None if c is None else float(c.wd_B),
               'lift_A': float(r.lift_A_mode), 'lift_B': float(r.lift_B_mode), 't_lift_A': float(r.t_day_A) * sgn,
               't_lift_B': float(r.t_day_B) * sgn if r.t_day_B == r.t_day_B else None, 't_week_A': float(r.t_week_A) * sgn,
               't_week_B': float(r.t_week_B) * sgn if r.t_week_B == r.t_week_B else None, 'z_adj_A': float(r.z), 'rank_A': int(r.rank),
               'specific_B': None if r.specific_B != r.specific_B else float(r.specific_B), 'gheat_B': float(r.gheat_B),
               'call_B': {'odds': float(r.call_odds_B), 'prof': float(r.call_prof_B), 'wd': float(r.call_wd_B)},
               'gated_B': {'odds': float(r.gated_odds_B), 'prof': float(r.gated_prof_B), 'wd': float(r.gated_wd_B)},
               'pi_B': float(r.pi_B), 'pi_c_B': None if r.pi_c_B != r.pi_c_B else float(r.pi_c_B), 'take_B': float(r.take_share_B),
               'cut_B': float(r.cut_share_B), 'hold': float(r.hold_B), 'dip': float(r.dip_B), 'move': None, 'family': r.family,
               'aliases': [a for a in str(r.aliases or '').split('|') if a and a != 'nan'], 'tier': int(r.tier),
               'above_twin_max': None, 'above_twin_p99': None, 'twin_mark': '', 'live_ready': False, 'live_ready_why': ['parity not run'],
               'profit_unit': PROFIT_UNIT[int(r.h)]}
        if extra:
            row.update(extra)
        return row
    for a in sorted(t1['asset'].unique()):
        for h in PACK_H:
            g = t1[(t1['asset'] == a) & (t1['h'] == h)]
            spec = [('take_right', g['tier'] <= 2, 'right', 'take'), ('take_profit', g['tier'] <= 2, 'profit', 'take'),
                    ('skip_right', g['tier'] <= 2, 'right', 'skip'), ('skip_profit', g['tier'] <= 2, 'profit', 'skip'),
                    ('other_units', g['tier'] > 2, 'right', 'take')]
            gt = twin1[(twin1['asset'] == a) & (twin1['h'] == h)]
            for lst, sel, tr, mode in spec:
                y = g[sel & (g['track'] == tr) & (g['mode'] == mode)].sort_values('gheat_B', ascending=False)
                tsel = (gt['tier'] <= 2) if lst != 'other_units' else (gt['tier'] > 2)
                am, ap, mkd = twin_marks(y, gt[tsel & (gt['track'] == tr) & (gt['mode'] == mode)], same_units)
                pc, k = {}, 0
                for i, r in enumerate(y.itertuples(index=False)):
                    if k >= lists[lst]:
                        break
                    if pc.get(r.unit, 0) >= PER_CALL:
                        continue
                    pc[r.unit] = pc.get(r.unit, 0) + 1
                    k += 1
                    rows.append(mk(r, 'gate', lst, [[r.param, [str(r.level_label)]]], {'above_twin_max': am[i], 'above_twin_p99': ap[i], 'twin_mark': mkd[i]}))
            if D2 is not None and len(D2) and 'path' in D2:
                p = D2[(D2['twin'] == 0) & (D2['asset'] == a) & D2['path'].astype(bool) & (D2['origin_h'] == h)].copy()
                if len(p):
                    p['gh'] = p['gheat_B'] if 'gheat_B' in p else np.nan          # (review fix) ranked by gate heat, not lift
                    pc, k = {}, 0
                    for r in p.sort_values(['gh', 'lift_B_mode'], ascending=False, na_position='last').itertuples(index=False):
                        if k >= lists['gate2']:
                            break
                        if pc.get(r.unit, 0) >= PER_CALL:
                            continue
                        pc[r.unit] = pc.get(r.unit, 0) + 1
                        k += 1
                        conds = [[r.p1, [str(r.l1)]], [r.param, [str(r.level_label)]]]
                        rows.append({'coin': a, 'h': int(h), 'kind': 'gate2', 'list': 'gate2', 'key': f"{r.unit.split('|', 2)[2]} | {r.p1}={r.l1} & {r.param}={r.level_label}",
                                     'when': {'key': r.unit.split('|', 2)[2], 'unit': r.unit}, 'conds': conds, 'mode': 'take', 'track': r.origin_track,
                                     'fire': 'when call fires and every condition holds; enter next open', 'lift_A': float(r.lift_A_mode),
                                     'lift_B': float(r.lift_B_mode), 't_lift_A': float(r.t_day_A), 'z_adj_A': float(r.z), 'rank_A': 1,
                                     'path_over_call_B': None if r.path_over_call_B != r.path_over_call_B else float(r.path_over_call_B),
                                     'path_B_n': int(r.path_B_n), 'gheat_B': None if r.gh != r.gh else float(r.gh), 'family': r.family,
                                     'live_ready': False, 'live_ready_why': ['parity not run'],
                                     'profit_unit': PROFIT_UNIT[int(h)]})
    return _clean(rows)


def _parity_files(d: str) -> dict:
    """{COIN: parity summary} from a directory of <COIN>/parity.json (a job's artifacts) or <COIN>.json (the copies the
    parity-commit jobs keep under research/oracle_heat/hm2/[part3/]parity/). Twins never have one; DOGE is refused."""
    out = {}
    if not d or not os.path.isdir(d):
        return out
    for f in sorted(os.listdir(d)):
        c, p = None, None
        if os.path.isfile(os.path.join(d, f, 'parity.json')):
            c, p = f, os.path.join(d, f, 'parity.json')
        elif f.endswith('.json') and f[:-5].isupper() and f[:-5].isalpha():
            c, p = f[:-5], os.path.join(d, f)
        if c is None or 'twin' in c.lower():
            continue
        _refuse_doge(c)
        out[c] = _read_json(p)
    return out


def set_gate_live_ready(pack: dict, parities: dict, hm2_parities: dict = None, feeds=None, live_min: float = None) -> dict:
    """live_ready on Part 3's gate rows (kinds gate, gate2; every other row is left byte-identical). A row is live ready
    when (1) its own conditions (OWN:...) reached live_min of the checked minutes on its coin's drill parity.json (matched
    by key and h); (2) every other condition's reading reached live_min on HM2's parity of the coin (its new readings,
    engine readings and GBM calls; a chart reading has no live reader yet, so it is 'not checked'); (3) a call from
    hm2_pack.json (unit kinds hm2 and model) is itself live ready there; and (4) the bot has the feeds its readings need
    (heat_hm2_league.needed_feeds). live_ready_why lists what is missing."""
    from oracle import heat_hm2_league as hl
    feeds = set(hl.DEFAULT_FEEDS if feeds is None else feeds)
    live_min = hl.LIVE_MIN if live_min is None else live_min
    hm2_parities = hm2_parities or {}
    gbm_used = {f'GBM.{mdl}{h}': list(t.get('used') or []) for mm in (pack.get('models') or {}).values() for mdl, byh in mm.items()
                for h, t in byh.items()}
    hm2_rows = {(r.get('coin'), r.get('key'), r.get('h')): r for r in pack.get('rows', []) if r.get('kind') not in hl.GATE_KINDS}
    own = {}
    for c, p in parities.items():
        for x in (p or {}).get('rows', []):
            own[(c, x.get('key'), x.get('h'))] = x
    rows, n_ready = [], 0
    for r in pack.get('rows', []):
        if r.get('kind') not in hl.GATE_KINDS:
            rows.append(r)
            continue
        r = dict(r)
        why, c = [], r.get('coin')
        conds = r.get('conds') or []
        if any(str(n).startswith('OWN:') for n, _ in conds):
            x = own.get((c, r.get('key'), r.get('h')))
            if c not in parities:
                why.append('no drill parity for this coin')
            elif x is None or x.get('parity') is None:
                why.append('own conditions: not checked')
            elif x['parity'] < live_min:
                why.append(f'own conditions: parity {x["parity"]:.4f}')
        names = [str(n) for n, _ in conds if not str(n).startswith('OWN:')]
        hp = hm2_parities.get(c)
        allr = {**((hp or {}).get('readings') or {}), **((hp or {}).get('engine') or {}), **((hp or {}).get('gbm') or {})}
        for n in names:
            a = (allr.get(n) or {}).get('agreement')
            if a is None:
                why.append(f'{n}: not checked' if hp is not None else f'{n}: no HM2 parity for this coin')
            elif a < live_min:
                why.append(f'{n}: parity {a:.4f}')
        w = r.get('when') or {}
        ukind = w.get('kind') or (str(w.get('unit', '')).split('|')[1] if str(w.get('unit', '')).count('|') >= 2 else None)
        if ukind in ('hm2', 'model'):
            hr = hm2_rows.get((c, w.get('key'), r.get('h')))
            if hr is None:
                why.append('the call is not in hm2_pack.json')
            elif not hr.get('live_ready'):
                why.append('the call is not live ready in hm2_pack.json')
            else:
                names += list(hr.get('readings') or [])
        why += [f'no {x} feed' for x in sorted(hl.needed_feeds(names, gbm_used) - feeds)]
        r['live_ready'], r['live_ready_why'] = not why, why
        n_ready += not why
        rows.append(r)
    pack = dict(pack, rows=rows)
    pack['part3_live_reader_parity'] = {'live_min': live_min, 'feeds': sorted(feeds), 'gate_rows_live_ready': n_ready,
                                        'coins': {c: {'rows': len((p or {}).get('rows', []))} for c, p in parities.items()},
                                        'hm2_parity_coins': sorted(hm2_parities)}
    return pack


def merge_gates(pack: dict, rows: list, part3: dict = None) -> dict:
    """Adds the gate rows to hm2_pack.json with a `part3` block; earlier gate rows are replaced and every other row
    stays byte-identical (heat_hm2_league.merge_gate_rows asserts it)."""
    from oracle import heat_hm2_league as hl
    return hl.merge_gate_rows(pack, {'rows': rows, 'part3': part3} if part3 is not None else rows)


def part3_live_meta(rows: list, drill: dict) -> dict:
    """Per coin: the own parameters' quintile edges of every pack row's unit, the A directions table for OWN:Agree
    (each row's call direction), and the own-parameter rules (for own_levels_at)."""
    out = {'schema': 'oracle-heat-hm2-drill-live-1', 'rules': {
        'Since': {'edges': SINCE_EDGES, 'levels': SINCE_LV}, 'Order': {'window': ORDER_W, 'edges': ORDER_EDGES, 'levels': ORDER_LV},
        'Last': {'window': LAST_WINDOW, 'levels': LAST_LV}, 'Coincide': {'edges': COINCIDE_EDGES, 'levels': COINCIDE_LV},
        'Agree': {'edges': AGREE_EDGES, 'levels': AGREE_LV}, 'BarBody': {'edges': BODY_EDGES, 'levels': BODY_LV},
        'quintiles': 'np.searchsorted(edges, value, "right")'}, 'coins': {}}
    for r in rows:
        uid = (r.get('when') or {}).get('unit')
        d = drill.get(uid) if uid else None
        if d is None:
            continue
        c = out['coins'].setdefault(r['coin'], {})
        c[uid] = {'k': d.get('k'), 'dir': d.get('dir'), 'own_edges': d.get('own_edges')}
    return _clean(out)


def league(inputs: str, units: str, out: str, stamp: str = '', hm2_pack: str = '', hm2_live_meta: str = '', hm2_league: str = '',
           merge_only: str = '', log=print) -> dict:
    """Reads every series' small files (all parts and blocks), checks coverage, stops if hm2_pack.json's non-gate rows
    changed since the units were built, and writes league.md, summary.json, cards.md, profiles_pack.json.gz,
    gates_all.csv.gz, gate_rows.json; merges the gate rows into hm2_pack.json, the part3 block into hm2_live_meta.json
    and the Part 3 section into the HM2 league.md (the pack's live_meta_sha256 then names the new live meta). merge_only:
    re-applies gate_rows.json to a rewritten hm2_pack.json (and its `live` block to hm2_live_meta.json when given) and
    does nothing else."""
    from oracle import heat_hm2_league as hl
    os.makedirs(out, exist_ok=True)
    if merge_only:
        g = _read_json(merge_only)
        pack = _read_json(hm2_pack)
        if pack is None:
            raise SystemExit('--merge-only needs --hm2-pack')
        pack = hl.merge_gate_rows(pack, g, log=log)
        lm = _read_json(hm2_live_meta) if hm2_live_meta else None
        if lm is not None and isinstance(g, dict) and g.get('live') and hl.gates_merged(pack):       # the part3 live block returns with its rows
            lm['part3'] = g['live']
            pack['live_meta_sha256'] = hl._dump(lm, hm2_live_meta, indent=None)
        _dump(pack, hm2_pack, indent=1)
        log(f'merge-only: {len(g.get("rows", g) if isinstance(g, dict) else g)} gate rows into {hm2_pack}')
        return {'merged': True}
    U = _read_json(units)
    pack = _read_json(hm2_pack) if hm2_pack else None
    if pack is not None and U.get('hm2_tier2_sha256') and hl.tier2_sha(pack) != U['hm2_tier2_sha256']:
        raise SystemExit("hm2_pack.json's non-gate rows changed since drill-units: tier 2 would be stale")
    if pack is not None and not U.get('hm2_tier2_sha256') and U.get('hm2_nongate_sha256') and hl.non_gate_sha(pack) != U['hm2_nongate_sha256']:
        raise SystemExit("hm2_pack.json's non-gate rows changed since drill-units: tier 2 would be stale")
    L = load_league_inputs(inputs, log)
    if not L['series']:          # as HM2's league: no drill series, no league (the earlier gate rows stay in hm2_pack.json)
        raise SystemExit(f'{inputs}: no drill series outputs (meta.json of schema {SCHEMA_SERIES}); hm2_pack.json and its gate rows are left as they are')
    same = any(v['twin_units'] == 'quarter' for v in L['series'].values() if v['twin'])
    drill = {}
    S_dirs = find_series(inputs)
    for label, v in L['series'].items():
        for d, _ in S_dirs[label]:
            for f in sorted(os.listdir(d)):
                if f.endswith('_drill.json.gz'):
                    drill.setdefault(label, {}).update(_read_json(os.path.join(d, f)) or {})
    curves = _curve_shapes(drill)
    chance = chance_table(L, same)
    pers = persistence(L)
    views = league_views(L, same_units=same)
    fam = family_table(L)
    tc = ta_cards(L['top'], curves)
    cc = column_cards(L['top'], curves)
    rows = gate_rows(L['top'], L['units'], L['depth2'], same_units=same)
    real_drill = {}
    for label, dj in drill.items():
        if not L['series'][label]['twin']:
            real_drill.update(dj)
    part3 = {'schema': SCHEMA_GATES, 'stamp': stamp, 'units_sha256': U.get('sha256'), 'hm2_tier2_sha256': U.get('hm2_tier2_sha256'),
             'hm2_nongate_sha256': U.get('hm2_nongate_sha256'), 'list_rule': PACK_LISTS, 'per_call': PER_CALL,
             'fire': 'a gate row fires when its `when` call fires at a minute close and every condition holds its level at the last closed bar of its '
                     'own timeframe (own parameters from the call\'s own fire history); take: enter at the next minute\'s open; skip: block the call',
             'chance': {k: v.get('pooled') for k, v in chance.items() if isinstance(v, dict) and 'pooled' in v}}
    live3 = part3_live_meta(rows, real_drill)
    # gate_rows.json carries the rows, the pack's part3 block and the live meta's part3 block: a later HM2 league
    # (--gates) or --merge-only puts all three back
    _dump({'rows': rows, 'part3': part3, 'live': live3}, os.path.join(out, 'gate_rows.json'), indent=1)
    T = L['top']
    if len(T):
        ga = T[(T['twin'] == 0) & (T['rank'] == 1)]
        _write_csv(ga, os.path.join(out, 'gates_all.csv.gz'))
    prof = {uid: d for uid, d in real_drill.items() if int(d.get('tier') or 3) <= 2}
    _dump(prof, os.path.join(out, 'profiles_pack.json.gz'), gz=True)
    summary = {'schema': SCHEMA_LEAGUE, 'stamp': stamp, 'series': {k: {kk: vv for kk, vv in v.items() if kk != 'metas'} for k, v in L['series'].items()},
               'coverage': L['coverage'], 'same_units': same, 'chance': chance, 'persistence': pers,
               'family': fam.to_dict('records') if len(fam) else [], 'gate_rows': len(rows), 'cards': len(tc), 'columns': len(cc)}
    _dump(summary, os.path.join(out, 'summary.json'), indent=1)
    _dump({'ta_cards': tc, 'column_cards': cc}, os.path.join(out, 'cards.json.gz'), gz=True)
    md = league_md(summary, views, tc, cc)
    with open(os.path.join(out, 'league.md'), 'w') as f:
        f.write(md)
    with open(os.path.join(out, 'cards.md'), 'w') as f:
        f.write(cards_md(tc, cc))
    if pack is not None:
        pack = merge_gates(pack, rows, part3)
        if hm2_live_meta:
            lm = _read_json(hm2_live_meta) or {}
            lm['part3'] = live3
            pack['live_meta_sha256'] = hl._dump(lm, hm2_live_meta, indent=None)       # the pack names the live meta it goes with
        _dump(pack, hm2_pack, indent=1)
        if hm2_league and os.path.isfile(os.path.join(hm2_league, 'league.md')):
            hl.upsert_section(os.path.join(hm2_league, 'league.md'), 'part3', hl.part3_section(pack))
    log(f'league: {len(L["series"])} series, {len(rows)} gate rows')
    return summary


def league_md(summary: dict, views: pd.DataFrame, tc: list, cc: list) -> str:
    f = lambda v, p=2: '' if v is None or (isinstance(v, float) and not math.isfinite(v)) else f'{v:.{p}f}'
    md = ['# OR-HM2 Part 3: what separates the winners', '', f"Stamp: {summary.get('stamp')}. Every count stands beside the no-signal twins "
          "(median and range); a count is evidence only when it stands clear of the highest twin set. No pass bar filters a row.", '',
          '## Chance table (A top-1 gates, main list)', '', '| H | track | mode | units | kept real | kept twins (median, range) | t_B>=2 real | twins | '
          'gate heat max real | twins max |', '|---|---|---|---|---|---|---|---|---|---|']
    for k, v in sorted(summary['chance'].items()):
        if not isinstance(v, dict) or 'pooled' not in v or not k.endswith('|main'):
            continue
        h, tr, mode, _ = k.split('|')
        r, t = v['pooled']['real'], v['pooled'].get('twins', {})
        kt, tb = t.get('kept', {}), t.get('tb2', {})
        gm = t.get('gheat_max', {})
        md.append(f"| {h} | {tr} | {mode} | {r['units']} | {f(r['kept'])} | {f(kt.get('median'))} ({f(kt.get('min'))}-{f(kt.get('max'))}) | "
                  f"{f(r['tb2'])} | {f(tb.get('median'))} | {f(r['gheat_max'])} | {f(gm.get('max'))} |")
    md += ['', '## The league (gate heat on B of the A-chosen top-1 gate)', '']
    if len(views):
        for (h, tr, mode), g in views.groupby(['h', 'track', 'mode']):
            md += [f'### {h} minutes, {tr}, {mode}', '', '| # | coin | call | separator | level | lift A | lift B | t B | gate heat | specific B | above twins |',
                   '|---|---|---|---|---|---|---|---|---|---|---|']
            for r in g.head(10).itertuples(index=False):
                md.append(f'| {r.list_rank} | {r.asset} | {r.unit_words} | {r.param} | {r.level_label} | {f(r.lift_A_mode)} | {f(r.lift_B_mode)} | '
                          f'{f(r.t_B_mode, 1)} | {f(r.gheat_B)} | {f(r.specific_B)} | {r.above_twin_max if r.twin_mark != "p99" else f"p99: {r.above_twin_p99}"} |')
            md.append('')
    md += ['## Family table', '', '| H | family | share real | kept real | share twins | kept twins |', '|---|---|---|---|---|---|']
    for r in summary.get('family', []):
        md.append(f"| {r['h']} | {r['family']} | {f(r['real_share'])} | {f(r['real_kept'])} | {f(r['twins_share'])} | {f(r['twins_kept'])} |")
    md += ['', f'TA, pattern and column cards: cards.md ({len(tc)} cards, {len(cc)} columns).', '']
    return '\n'.join(md)


def cards_md(tc: list, cc: list) -> str:
    f = lambda v: '' if v is None else f'{v:.2f}'
    md = ['# Part 3 cards', '', '## TA, pattern and family cards', '']
    for c in tc[:200]:
        md += [f"### {c['card']} ({c['units_real']} units)", '']
        for k, lines in c['tracks'].items():
            if not lines:
                continue
            md.append(f'**{k}**: ' + '; '.join(f"{ln['param']} ({ln['units']} units, kept with t_B>=2 {f(ln['kept_tb2_share'])}, twins "
                                                f"{f(ln['twins']['median'])}, shape {ln['shape']})" for ln in lines[:5]))
        md.append('')
    md += ['## Column cards', '', '| column | family | units top 5 | kept t_B>=2 | twins median | twins max | clear | helps | hurts |',
           '|---|---|---|---|---|---|---|---|---|']
    for c in cc:
        md.append(f"| {c['param']} | {c['family']} | {c['units_top5']} | {f(c['kept_tb2_share'])} | {f(c['twins']['median'])} | {f(c['twins']['max'])} | "
                  f"{c['clear_of_twins']} | {c['helps']} | {c['hurts']} |")
    return '\n'.join(md) + '\n'


# ============================================================================================================== live
def own_levels_at(fires: np.ndarray, win: dict, meta: dict, unit: dict = None) -> dict:
    """Live: the own parameters at the last closed minute of `win` (minute arrays o, h, l, c, v, gap of a window that
    ends at that close) from the call's fires in the window (rows of the window, sorted, the last one = the window's
    last row when the call fires now). meta: {'k', 'dir' (6), 'own_edges'}. Coincide and Agree need every HM1 level's
    fires and come from the live reader's fire index (not here); Depth from the 200-bin tables of the live meta."""
    n = len(win['c'])
    i = n - 1
    k = int(meta.get('k') or 1)
    d = np.asarray(meta['dir'], int)
    fires = np.asarray(fires, np.int64)
    fires = fires[fires <= i]
    out = {}
    fb = (fires + 1) // k - 1
    ib = (i + 1) // k - 1
    pos = int(np.searchsorted(fires, i))
    if pos > 0:
        since = ib - fb[pos - 1]
        out['OWN:Since'] = SINCE_LV[int(np.searchsorted(np.asarray(SINCE_EDGES), since, 'left'))]
    else:                                                             # no fire in a window longer than the last edge: over it
        out['OWN:Since'] = 'over 100' if ib > SINCE_EDGES[-1] else 'none'
    cnt = pos - int(np.searchsorted(fb, ib - ORDER_W, 'left'))
    out['OWN:Order'] = ORDER_LV[int(np.searchsorted(np.asarray(ORDER_EDGES), cnt, 'left'))]
    c, o = np.asarray(win['c'], float), np.asarray(win['o'], float)
    gap = np.asarray(win.get('gap', np.zeros(n, bool)), bool)
    tick = heat.tick_bps(c, gap)
    for hi, H in enumerate(H_ALL):
        cand = fires[fires <= i - H]
        lv = 'none'
        if len(cand):
            r = int(cand[-1])
            if i - r <= LAST_WINDOW and r + H < n and r + 1 < n and not gap[r:r + H + 1].any():
                ret = (c[r + H] / o[r + 1] - 1) * 1e4
                dead = heat.TICK_DEAD * tick[r]
                y = (np.sign(ret) if abs(ret) > dead else 0) * d[hi]
                lv = 'right' if y > 0 else 'wrong' if y < 0 else 'flat'
        out[f'OWN:Last@{H}'] = lv
    import talib
    nb_ = n // k
    sl = slice(n - nb_ * k, n)
    rs = lambda a, f: f(np.asarray(a, float)[sl].reshape(nb_, k), 1) if k > 1 else np.asarray(a, float)[sl]
    bo = np.asarray(win['o'], float)[sl].reshape(nb_, k)[:, 0] if k > 1 else o[sl]
    bh, bl = rs(win['h'], np.max), rs(win['l'], np.min)
    bc = np.asarray(win['c'], float)[sl].reshape(nb_, k)[:, -1] if k > 1 else c[sl]
    bv = rs(win['v'], np.sum)
    ed = meta.get('own_edges') or {}
    if (i + 1) % k == 0 and nb_ >= 21:
        rng = bh[-1] - bl[-1]
        atr = talib.ATR(bh, bl, bc, 14)[-1]
        if ed.get('OWN:BarRange') and atr > 0:
            out['OWN:BarRange'] = Q5[int(np.searchsorted(np.asarray(ed['OWN:BarRange']), rng / atr, 'right'))]
        pv = bv[-21:-1].mean()
        if ed.get('OWN:BarVol') and pv > 0:
            out['OWN:BarVol'] = Q5[int(np.searchsorted(np.asarray(ed['OWN:BarVol']), bv[-1] / pv, 'right'))]
        if rng > 0:
            out['OWN:BarBody'] = BODY_LV[int(np.searchsorted(np.asarray(BODY_EDGES), (bc[-1] - bo[-1]) / rng, 'left'))]
    if ed.get('OWN:Step'):
        out['OWN:Step'] = Q5[int(np.searchsorted(np.asarray(ed['OWN:Step']), tick[i], 'right'))]
    return out


def own_history_levels(ctx, x: Inst) -> dict:
    """The own parameters' level labels at each instance (history side of the parity)."""
    out = {}
    for nm, lv in OWN_SPECS:
        if nm in x.own:
            out[nm] = [lv[c] if c >= 0 else None for c in x.own[nm]]
    return out


def parity(asset: str, csv: str, units, gates: str, out: str, days: int = 3, log=print, **data_kw) -> dict:
    """Dec 29-31, 2025: own_levels_at on a window of minutes against the history codes, for every own condition of every
    gate row of the coin (engine and HM2 conditions: HM2's own parity, heat_hm2_league parity). Writes parity.json."""
    os.makedirs(out, exist_ok=True)
    G = _read_json(gates) or {}
    rows = [r for r in (G.get('rows', G) if isinstance(G, dict) else G) if r.get('coin') == asset]
    U = _read_json(units) if isinstance(units, str) else units
    store = {}
    with capture_raw(store):
        ctx = hm.base(asset, csv, log=log, **{k: v for k, v in data_kw.items() if k in ('other_csvs', 'perp_csv', 'fund_csv', 'oi_csv', 'cal_csv', 'dom',
                                                                                         'found', 'main_meta', 'twin', 'other_metas', 'xdata')})
    _prepare(ctx, store, (), '', engine=False, log=log, procs=4, chart=False)
    byid = {u['id']: u for u in U['coins'].get(asset, [])}
    t_end = int(ctx.m['n'])
    lo = t_end - days * 1440
    res = {'schema': SCHEMA_PARITY, 'asset': asset, 'rows': []}
    for r in rows:
        uid = (r.get('when') or {}).get('unit')
        u = byid.get(uid)
        own = [c for c in r.get('conds', []) if c[0].startswith('OWN:')]
        if u is None or not own:
            continue
        u = dict(u)
        u['rows'] = unit_rows(ctx, u)
        x = split_instances(ctx, u, u['rows'])
        x.k = unit_k(ctx, u)
        x.bases = set()
        x.own, x.own_edges = own_params(ctx, x)
        meta = {'k': x.k, 'dir': x.d.tolist(), 'own_edges': x.own_edges}
        hist = own_history_levels(ctx, x)
        sel = np.flatnonzero(x.rows >= lo)
        W = max(3000, 300 * x.k)
        agree, tot = 0, 0
        for j in sel:
            i = int(x.rows[j])
            a = max(0, i - W + 1)
            win = {kk: np.asarray(ctx.m[kk])[a:i + 1] for kk in ('o', 'h', 'l', 'c', 'v', 'gap')}
            f = u['rows'][(u['rows'] >= a) & (u['rows'] <= i)] - a
            live = own_levels_at(f, win, meta)
            for nm, _ in own:
                if nm in live and nm in hist:
                    tot += 1
                    agree += live[nm] == hist[nm][j]
        res['rows'].append({'key': r.get('key'), 'h': r.get('h'), 'minutes': int(tot), 'parity': agree / tot if tot else None})
    _dump(res, os.path.join(out, 'parity.json'), indent=1)
    return res


# =============================================================================================================== CLI
def main(argv=None):
    ap = argparse.ArgumentParser(prog='oracle.heat_hm2_drill')
    sub = ap.add_subparsers(dest='cmd', required=True)
    u = sub.add_parser('units')
    u.add_argument('--direction', required=True)
    u.add_argument('--direction-long', default='')
    u.add_argument('--packs', default='')
    u.add_argument('--hm2-pack', default='')
    u.add_argument('--out', required=True)
    c = sub.add_parser('coin')
    hm._inputs(c)
    c.add_argument('--units', required=True)
    c.add_argument('--hm2-series', default='')
    c.add_argument('--out', required=True)
    c.add_argument('--part', default='0/1')
    c.add_argument('--blocks', default='')
    c.add_argument('--twin-units', default='all', choices=('all', 'quarter'))
    c.add_argument('--shards', default='')
    c.add_argument('--no-chart', action='store_true')                # skip Part 4's chart readings and units
    b = sub.add_parser('bench')
    hm._inputs(b)
    b.add_argument('--units', required=True)
    b.add_argument('--hm2-series', default='')
    b.add_argument('--n-units', type=int, default=200)
    b.add_argument('--no-chart', action='store_true')
    b.add_argument('--out', required=True)
    lg = sub.add_parser('league')
    lg.add_argument('--inputs', default='')
    lg.add_argument('--units', default='')
    lg.add_argument('--hm2-pack', default='')
    lg.add_argument('--hm2-live-meta', default='')
    lg.add_argument('--hm2-league', default='')
    lg.add_argument('--out', required=True)
    lg.add_argument('--stamp', default='')
    lg.add_argument('--merge-only', default='')
    lg.add_argument('--parts', type=int, default=0)                # S of the drill parts tag (0: whatever the metas say)
    lg.add_argument('--allow-partial', action='store_true')       # [heat-hm2-drill-partial]: an incomplete set is labelled, not refused (the completeness check is the league batch)
    pr = sub.add_parser('parity')
    hm._inputs(pr)
    pr.add_argument('--units', required=True)
    pr.add_argument('--gates', required=True)
    pr.add_argument('--days', type=int, default=3)
    pr.add_argument('--out', required=True)
    lr = sub.add_parser('live-ready')
    lr.add_argument('--pack', required=True)
    lr.add_argument('--parity', required=True)                     # the drill parity files: <dir>/<COIN>/parity.json or <dir>/<COIN>.json
    lr.add_argument('--hm2-parity', default='')                    # HM2's parity files (the other conditions' readings)
    lr.add_argument('--feeds', default='')                         # default: heat_hm2_league.DEFAULT_FEEDS
    lr.add_argument('--out', default='')
    a = ap.parse_args(argv)
    if a.cmd == 'units':
        res = build_units(a.direction, a.direction_long, a.packs, a.hm2_pack or None)
        _dump(res, a.out, indent=None)
        print(json.dumps({'coins': {k: len(v) for k, v in res['coins'].items()}, 'sha256': res['sha256']}))
    elif a.cmd == 'coin':
        kw = hm._kw(a)
        pi, S = (int(x) for x in a.part.split('/'))
        if not 0 <= pi < S:
            raise SystemExit(f'--part {a.part}: want i/S with 0 <= i < S')
        kw.pop('twin', None)
        mt = run_series(a.asset, a.csv, a.out, a.units, twin=a.twin, procs=a.procs, part=(pi, S), blocks=_parse_blocks(a.blocks),
                        twin_units=a.twin_units, hm2_series=a.hm2_series, shards=a.shards, chart=not a.no_chart, **kw)
        print(json.dumps({k: v for k, v in mt.items() if k not in ('blocks_done', 'block_units', 'param_names')}, indent=1))
        _exit_if_blocks_failed(mt)
    elif a.cmd == 'bench':
        kw = hm._kw(a)
        bench(a.asset, a.csv, a.out, a.units, a.n_units, a.procs, a.hm2_series, chart=not a.no_chart, **kw)
    elif a.cmd == 'league':
        league(a.inputs, a.units, a.out, a.stamp, a.hm2_pack, a.hm2_live_meta, a.hm2_league, a.merge_only)
    elif a.cmd == 'live-ready':
        pack = _read_json(a.pack)
        if pack is None:
            raise SystemExit(f'{a.pack}: no pack')
        par = _parity_files(a.parity)
        if not par:
            raise SystemExit(f'{a.parity}: no drill parity file')
        pack = set_gate_live_ready(pack, par, _parity_files(a.hm2_parity), tuple(x for x in a.feeds.split(',') if x) if a.feeds else None)
        _dump(pack, a.out or a.pack, indent=1)
        g = [r for r in pack['rows'] if r.get('kind') in ('gate', 'gate2')]
        print(f'{a.out or a.pack}: {sum(bool(r.get("live_ready")) for r in g):,} of {len(g):,} gate rows live ready (drill parity of {sorted(par)}, '
              f'HM2 parity of {sorted(_parity_files(a.hm2_parity))})')
    else:
        kw = hm._kw(a)
        parity(a.asset, a.csv, a.units, a.gates, a.out, a.days, **kw)


if __name__ == '__main__':
    main()
