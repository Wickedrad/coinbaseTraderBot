"""OR-HM2 part 2: the learner (python/oracle/prereg/OR-HM2.md, Part 2; build plan section 3). It changes no line of
oracle.heat and no stored table; oracle.heat_hm2 (the series job) calls it.

  python3 -m oracle.heat_hm2_learn paths --tree <out>/trees/ALL_h15.json [--min-readings 3] [--out paths.json]

What one series (a coin or a no-signal twin, the identical pipeline) learns, per model and horizon:
  models    TA: the engine's readings (heat.build_readings: TA-Lib on the coin's own bars, daily dominance, the 4-hour
            block) plus the ZS:<name> event state of each of their zone readings. ALL: every reading of the series (the
            engine's, the clock and every new reading of heat_xdata) plus the ZS state of every zone reading. ALL minus
            TA is what cross-referencing the other data adds.
  rows      the scan's A entries (every 7th valid row of 2020-2024) with a valid label at H; no 2025 row and no label that
            reads a 2025 price is ever in a fit (learn() stops on one). No tuning and no second check period.
  features  the reading's level index at the decision row (heat.read_state: the last closed bar of its timeframe),
            unknown = NaN (minus the neutral level's index for an ordinal reading). Zone, sign, breadth and z-zone (dominance, daily markets) codes are ordinal; clock,
            position, pattern, ZS and every other state is categorical. ZS:<name>: the side-aware event that fired on
            the zone reading's last closed bar (heat_xdata.zs_codes: none / very low / low falling in / low recovering /
            high rising in / high cooling / very high).
  fit       LightGBM 4.5.0, L2 regression on the direction sign (-1, 0, +1) with init_score = A's base mean sign, so a
            leaf is a shift in mean sign (x 50 = odds points). heat_hm2.LGB_PARAMS, 300 rounds, seed 20261111 + H.
            The Dataset is built from 100,000-row float32 chunks of the int8 codes (dataset(): LightGBM's own matrix
            loader step by step); an ordinal value is centred on its neutral level (value_offset).
  trees     dump_model() JSON plus an 'hm2' block (feature names, levels, encoding, init score), so the bot evaluates
            the call with tree_eval (pure numpy, no LightGBM); tested equal to booster.predict.
  call      GBM.<model><H> (k = 1): the score at every minute of both splits in five zones at A's quantiles of the
            score (ZONE_Q); NA on a forward-filled minute. Its own A odds per zone give each zone's direction; its B
            numbers (call_stats) score the call on 2025. heat_hm2.remeasure then measures it in the league's units.
  paths     every root-to-leaf path of the A-trained trees as a rule: predicates on one feature merged into a level
            set, missing-value routing as the level 'NA'. The scan form maps a ZS condition onto its zone reading's
            levels (an event fixes the zone it lands in), so the scan can measure it: rules naming three readings
            become triples (heat_hm2.scan_triples (b)), two readings mark learner_path on the pair.
  usage     LightGBM's pred_contrib on 20,000 seeded 2025 minutes only (the A entries are the training rows): mean
            contribution by reading level and mean |contribution| by reading, TA function (all timeframes and settings
            together), family and partner group, in odds points. The model's view, not evidence: the twins' stand
            beside it in the league.
  cards     the raw inputs of the per-TA-function usage cards: the settings x timeframe grid (each zone's own state
            odds on A and on B in its A direction per horizon, fade or follow of the extreme zones, the strongest
            horizon) and the best partner per data family from the candidate pool (by iheat_B, with iota_with_call).
Coin minutes 2020-01-01 to 2025-12-31 only. A MAP on coin price, not a Kalshi-price result. NEVER DOGE.
"""
import argparse
import gzip
import hashlib
import json
import math
import os
import re
import time

import numba as nb
import numpy as np
import pandas as pd

from oracle import heat
from oracle import heat_hm2 as hm
from oracle import heat_xdata as xd
from oracle.common import MIN
from oracle.heat_pack import indicator

MODELS = ('TA', 'ALL')
X_CHUNK = 100_000               # rows per float32 chunk handed to lightgbm.Dataset
SCORE_CHUNK = 200_000           # rows per chunk of the per-minute score
N_CONTRIB = 20_000              # seeded B minutes of the contributions
CONTRIB_SEED = [20261111, 2]    # the seed heat_hm2._learner draws them with (same minutes either way)
ODDS = 50.0                     # mean sign -> odds points
ZERO_T = 1e-35                  # LightGBM's kZeroThreshold (a value within it is "zero" for missing_type Zero)
TREE_SCHEMA = 'oracle-heat-hm2-tree-1'
HM2_PREFIX = tuple(p for p, _ in hm.FAMILY_PREFIX)
SIGN_LV = ['below 0', 'above 0']
# a ZS event level -> the zone the reading lands in (None: no event, any zone)
ZS_ZONE = {'none': None, 'very low': 'very low', 'low (falling in)': 'low', 'low (recovering)': 'low', 'high (rising in)': 'high',
           'high (cooling)': 'high', 'very high': 'very high'}
# the partner groups of a usage card (OR-HM2, Lessons): TA, cross-coin, volatility, flow, perp and open interest,
# position and clock, macro, dominance and daily markets (plus each inventory family found)
CARD_GROUP = {'cross': 'cross-coin', 'cross-coin': 'cross-coin', 'vol': 'volatility', 'volatility': 'volatility', 'flow': 'flow',
              'perp': 'perp and open interest', 'oi': 'perp and open interest', 'open interest': 'perp and open interest',
              'position': 'position and clock', 'clock': 'position and clock', 'macro': 'macro', 'dmkt': 'dominance and daily markets',
              'daily markets': 'dominance and daily markets', 'idx': 'dominance and daily markets', 'btcdom': 'dominance and daily markets',
              'context': 'dominance and daily markets', 'cb': 'coinbase', 'coinbase': 'coinbase', 'book': 'book', 'model': 'model',
              'zs': 'TA', 'zone side': 'TA'}
EXTREME = {'very low': 1, 'very high': -1}       # the zone's fade direction: very low fades up, very high fades down
_TF = re.compile(r'^(\d+)m:')
_SET1 = re.compile(r'(?<=[A-Za-z])(\d+(?:[/.]\d+)*)(?=$|[ >]|pos$)')     # RSI14, PERCENTB20/2.5, STOCH14 K>D, KC20pos
_SET2 = re.compile(r'(?<=[A-Za-z0-9])_(\d+(?:[/.]\d+)*)$')               # T3_5


def _log_none(*a, **k):
    pass


# ----------------------------------------------------------------------------------------------- names and features
def is_ta_name(name: str) -> bool:
    """An engine reading's name (heat.build_readings: '<k>m:...' vocabulary readings and the context states), not a new
    family's, a clock state's, a ZS state's or a model's."""
    return not name.startswith(HM2_PREFIX) and name not in hm.CLOCK


def is_ta(R: dict) -> bool:
    """The TA model's readings: an engine reading (no 'family' of its own and an engine name), or a kept reading one of
    whose aliases is one (the copy merge keeps the first name, so an engine reading may live on under a new name)."""
    own = not R.get('family') and is_ta_name(R['name'])
    return own or any(is_ta_name(a) and _TF.match(a) for a in R.get('aliases', []))


def ta_parts(name: str):
    """'15m:RSI14' -> ('RSI', '14', '15m'); '1m:PERCENTB20/2.5' -> ('PERCENTB', '20/2.5', '1m'); '5m:STOCH14 K>D' ->
    ('STOCH K>D', '14', '5m'); '1m:C-T3_5' -> ('C-T3', '5', '1m'); '60m:CDL:DOJI' -> ('CDL:DOJI', '', '60m'). The
    function is heat_pack.indicator (no timeframe, no ' sign', no level) with the settings stripped. None for a name
    that is not a TA-Lib vocabulary reading."""
    if not _TF.match(name) or name.startswith(HM2_PREFIX):
        return None
    tf = name.split(':', 1)[0]
    ind = indicator(name)
    sets = _SET1.findall(ind)
    fn = _SET1.sub('', ind)
    m2 = _SET2.search(fn)
    if m2:
        sets.append(m2.group(1))
        fn = fn[:m2.start()]
    return fn, '/'.join(sets), tf


def ta_function(name: str):
    p = ta_parts(name)
    return p[0] if p else None


def is_ordinal(R: dict) -> bool:
    """Zone, sign, breadth and z-zone (dominance, daily markets) codes are ordinal; every other state is categorical."""
    lv = list(R['levels'])
    return bool(R.get('zones')) or lv == SIGN_LV or R['name'].startswith('X:Breadth') or lv == list(heat.DOM_LV)


def card_group(R: dict, fam: str = None) -> str:
    """The partner group of a reading on a usage card."""
    if is_ta(R):
        if R.get('ctx'):
            return 'position and clock' if R['name'].startswith('UTC') else 'dominance and daily markets'
        return 'TA'
    f = R.get('family') or fam or hm.family_of(R)
    return CARD_GROUP.get(f, f)


def feature_set(ctx, model: str) -> dict:
    """The features of a model, in a fixed order: the model's readings (ctx order), then ZS:<name> for each of their
    zone readings. Cached on the context. Each feature: name, the reading dict (the zone reading for a ZS state), zs,
    levels, categorical, family, partner group, the TA functions of its names (kept and aliases), zs_of."""
    cache = ctx.__dict__.setdefault('_hl_fs', {})
    if model in cache:
        return cache[model]
    if model not in MODELS:
        raise SystemExit(f'model {model}: want one of {MODELS}')
    fam = {nm: f for nm, f in zip(ctx.names, ctx.fam)}
    rd = [R for R in ctx.readings if model == 'ALL' or is_ta(R)]
    feats = []
    for R in rd:
        names = [R['name']] + list(R.get('aliases', []))
        cat = not is_ordinal(R)
        feats.append({'name': R['name'], 'R': R, 'zs': False, 'levels': list(R['levels']), 'cat': cat, 'offset': 0 if cat else value_offset(R['levels']),
                      'family': fam[R['name']], 'group': card_group(R, fam[R['name']]), 'funcs': sorted({f for f in map(ta_function, names) if f}),
                      'zs_of': None})
    for R in rd:
        if R.get('zones'):
            names = [R['name']] + list(R.get('aliases', []))
            feats.append({'name': f'ZS:{R["name"]}', 'R': R, 'zs': True, 'levels': list(xd.ZS_LEVELS), 'cat': True, 'offset': 0, 'family': 'zone side',
                          'group': card_group(R, fam[R['name']]), 'funcs': sorted({f for f in map(ta_function, names) if f}), 'zs_of': R['name']})
    for F in feats:
        if len(F['levels']) > 127:
            raise SystemExit(f'{F["name"]}: more than 127 levels')
    fs = {'model': model, 'feats': feats, 'names': [F['name'] for F in feats], 'cat_idx': [i for i, F in enumerate(feats) if F['cat']],
          'offset': np.array([F['offset'] for F in feats], np.float32)}
    cache[model] = fs
    return fs


def feature_codes(F: dict, rows: np.ndarray) -> np.ndarray:
    """int8 level index of one feature at minute rows (-1 = unknown). A reading: heat.read_state. A ZS state: the zone
    event on the reading's last closed bar, from that bar's and the bar before's codes through heat_xdata.zs_codes
    (so it equals heat.read_state of heat_xdata.zs_readings without building the whole ZS series)."""
    R = F['R']
    if not F['zs']:
        return heat.read_state(R, rows)
    codes, k = R['codes'], R['k']
    bi = (np.asarray(rows, np.int64) + 1) // k - 1
    ok = (bi >= 0) & (bi < len(codes))
    cur = np.full(len(bi), -1, np.int8)
    cur[ok] = codes[bi[ok]]
    okp = ok & (bi >= 1)
    prev = np.full(len(bi), -1, np.int8)
    prev[okp] = codes[bi[okp] - 1]
    # zs_codes reads each element against the one before: interleaved (prev, cur), the odd positions are the answer
    return xd.zs_codes(np.stack([prev, cur], 1).ravel())[1::2].copy()


def features(ctx, model: str, rows: np.ndarray, cols=None) -> np.ndarray:
    """int8 [rows, features] of the model (or of the feature indices cols): level index, -1 = unknown (the scan's code
    matrix minus 1, plus the ZS states)."""
    fs = feature_set(ctx, model)
    idx = range(len(fs['feats'])) if cols is None else cols
    rows = np.asarray(rows, np.int64)
    X = np.empty((len(rows), len(idx)), np.int8)
    for c, j in enumerate(idx):
        X[:, c] = feature_codes(fs['feats'][j], rows)
    return X


def value_offset(levels) -> int:
    """The value LightGBM sees for an ordinal reading is its level index minus its neutral level's ('mid', 'flat'; 0
    when it has none, as a sign reading): the common level is then 0, which LightGBM keeps out of its bin-construction
    sample (a sparse sample of a few hundred MB instead of a few GB on a real series). Order, and so every split, is
    unchanged. Categorical values are the level index."""
    for i, lv in enumerate(levels):
        if lv in heat.NEUTRAL or lv == 'flat':
            return i
    return 0


def as_float(X: np.ndarray, offset=None) -> np.ndarray:
    """int8 level codes (-1 = unknown) -> LightGBM's float32 values: code - offset, NaN for unknown. A float array is
    taken to be values already and passes unchanged."""
    if np.issubdtype(X.dtype, np.floating):
        return X
    f = X.astype(np.float32)
    if offset is not None:
        f -= offset
    f[X < 0] = np.nan
    return f


# ------------------------------------------------------------------------------------------------------------ rows
def b_start_row(ctx) -> int:
    """The row of the first 2025 minute: a label that reads its price (or any later one) is not an A label."""
    return int((heat.SPLITS['B'][0] - ctx.m['t0']) // MIN)


def train_rows(ctx, H: int) -> tuple:
    """(rows, y): the A entries with a valid label at H and their direction sign. 1-60 minutes: the A entries (valid rows
    of the engine's Grid, HMAX 60); 240: those that are valid rows of the 240 grid's split A (its rows end 240 minutes
    before 2025)."""
    if H not in hm.H_SCAN:
        raise SystemExit(f'horizon {H}: want one of {hm.H_SCAN}')
    rows = ctx.rows[ctx.split == 0]
    if H == 240:
        rows = rows[np.isin(rows, ctx.g240.sp['A'].rows)]
        y = ctx.lab240['sg240'][rows]
    else:
        y = ctx.lab[f'sg{H}'][rows]
    b0 = b_start_row(ctx)
    if len(rows) and int(rows.max()) + H > b0 - 1:
        raise SystemExit(f'train_rows: an A label at {H} minutes would read a 2025 price (row {int(rows.max())}, first 2025 row {b0})')
    return rows, y.astype(np.float32)


def contrib_rows(ctx, n: int = N_CONTRIB) -> np.ndarray:
    """The seeded 2025 minutes of the contributions: valid rows of split B only."""
    rB = ctx.g.sp['B'].rows
    rows = np.sort(np.random.default_rng(CONTRIB_SEED).choice(rB, min(n, len(rB)), replace=False))
    assert not len(rows) or rows.min() >= b_start_row(ctx) - 1, 'contribution rows outside 2025'
    return rows


def dataset(X8: np.ndarray, pos: np.ndarray, offset: np.ndarray, y: np.ndarray, init: np.ndarray, cat_idx: list, params: dict):
    """lightgbm.Dataset of the rows X8[pos], built in X_CHUNK-row float32 chunks so the float32 copy of the whole matrix
    never exists. The steps of LightGBM's own matrix loader (LGBM_DatasetCreateFromMat) through its C API, with the
    full parameter string as that loader gets it (seed, min_data_in_leaf for the feature pre-filter, max_bin ...): its
    sample of bin_construct_sample_cnt rows (LGBM_SampleIndices), the sample's non-zero and unknown values per column
    (LGBM_DatasetCreateFromSampledColumn), then every row (LGBM_DatasetPushRows). The result is the Dataset LightGBM
    builds from the whole float32 matrix (tested bit for bit through the fitted model)."""
    import ctypes
    import lightgbm as lgb
    from lightgbm import basic as B
    n, F = len(pos), X8.shape[1]
    prm = dict(params, categorical_column=sorted(cat_idx))         # as Dataset._lazy_init passes the categorical list
    pstr = B._c_str(B._param_dict_to_str(prm))
    cnt = B._get_sample_count(n, B._param_dict_to_str(prm))
    idx = np.empty(cnt, np.int32)
    got = ctypes.c_int32(0)
    B._safe_call(B._LIB.LGBM_SampleIndices(ctypes.c_int32(n), pstr, idx.ctypes.data_as(ctypes.POINTER(ctypes.c_int32)), ctypes.byref(got)))
    idx = idx[:got.value]
    S = X8[pos[idx]]                                                    # int8: one column at a time becomes float64 below
    ar = np.arange(len(idx), dtype=np.int32)
    vals, rws = [], []
    for j in range(F):
        c = as_float(S[:, j], offset[j]).astype(np.float64)
        keep = (np.abs(c) > ZERO_T) | np.isnan(c)                       # LightGBM keeps the non-zero and the unknown sampled values
        vals.append(np.ascontiguousarray(c[keep]))
        rws.append(np.ascontiguousarray(ar[keep]))
    del S
    vp = (ctypes.POINTER(ctypes.c_double) * F)()
    ip = (ctypes.POINTER(ctypes.c_int32) * F)()
    for j in range(F):
        vp[j] = vals[j].ctypes.data_as(ctypes.POINTER(ctypes.c_double))
        ip[j] = rws[j].ctypes.data_as(ctypes.POINTER(ctypes.c_int32))
    per = np.array([len(v) for v in vals], np.int32)
    handle = ctypes.c_void_p()
    B._safe_call(B._LIB.LGBM_DatasetCreateFromSampledColumn(
        ctypes.cast(vp, ctypes.POINTER(ctypes.POINTER(ctypes.c_double))), ctypes.cast(ip, ctypes.POINTER(ctypes.POINTER(ctypes.c_int32))),
        ctypes.c_int32(F), per.ctypes.data_as(ctypes.POINTER(ctypes.c_int32)), ctypes.c_int32(len(idx)), ctypes.c_int32(n), ctypes.c_int64(n),
        pstr, ctypes.byref(handle)))
    del vals, rws, vp, ip
    for s in range(0, n, X_CHUNK):
        ch = np.ascontiguousarray(as_float(X8[pos[s:s + X_CHUNK]], offset), dtype=np.float32)
        B._safe_call(B._LIB.LGBM_DatasetPushRows(handle, ch.ctypes.data_as(ctypes.POINTER(ctypes.c_float)), ctypes.c_int(B._C_API_DTYPE_FLOAT32),
                                                 ctypes.c_int32(len(ch)), ctypes.c_int32(F), ctypes.c_int32(s)))
    ds = lgb.Dataset(None, params=prm, free_raw_data=True)
    ds._handle = handle
    ds.set_label(y)
    ds.set_init_score(init)
    ds.set_feature_name([f'f{i:04d}' for i in range(F)])
    return ds


# ---------------------------------------------------------------------------------------------------------- the fit
def _a_codes(ctx, model: str) -> tuple:
    """(A entry rows, int8 features of the model there), cached for one model at a time (the matrix is the learner's
    largest array)."""
    c = ctx.__dict__.get('_hl_X')
    if c is None or c[0] != model:
        ctx.__dict__['_hl_X'] = None
        rA = ctx.rows[ctx.split == 0]
        c = (model, rA, features(ctx, model, rA))
        ctx.__dict__['_hl_X'] = c
    return c[1], c[2]


def drop_cache(ctx) -> None:
    """Free the learner's cached matrices (call after the last fit of a series)."""
    for k in ('_hl_X', '_hl_fs'):
        ctx.__dict__.pop(k, None)


def learn(ctx, model: str, H: int, params: dict = None, rounds: int = None) -> tuple:
    """Fit one model at one horizon on the A entries with a valid label (no 2025 row, no label that reads a 2025 price:
    a stop otherwise). Returns (booster, used reading names, tree JSON). The booster carries `hm2`: the feature meta
    the other functions of this module read (gbm_reading, contributions)."""
    import lightgbm as lgb
    t0 = time.time()
    fs = feature_set(ctx, model)
    rows, y = train_rows(ctx, H)
    rA, XA = _a_codes(ctx, model)
    pos = np.searchsorted(rA, rows)
    assert np.array_equal(rA[pos], rows) and np.all(ctx.split[np.searchsorted(ctx.rows, rows)] == 0), 'a training row that is not an A entry'
    hi = hm.H_SCAN.index(H)
    init = float(ctx.base[0]['bms'][hi])
    if not math.isfinite(init):
        raise SystemExit(f'{ctx.label}: no A base at {H} minutes')
    prm = dict(hm.LGB_PARAMS if params is None else params)
    prm['seed'] = hm.LGB_SEED + int(H)
    ds = dataset(XA, pos, fs['offset'], y, np.full(len(rows), init), fs['cat_idx'], prm)
    booster = lgb.train(prm, ds, num_boost_round=hm.LGB_ROUNDS if rounds is None else int(rounds))
    del ds
    tj = booster.dump_model()
    split = booster.feature_importance('split')
    used = [fs['names'][i] for i in np.flatnonzero(split > 0)]
    tj['hm2'] = {'schema': TREE_SCHEMA, 'label': ctx.label, 'twin': int(ctx.twin), 'model': model, 'h': int(H), 'init_score': init,
                 'rounds': int(booster.num_trees()), 'seed': prm['seed'], 'rows': int(len(rows)), 'last_row': int(rows.max()) if len(rows) else None,
                 'first_2025_row': b_start_row(ctx), 'lightgbm': lgb.__version__, 'params': hm._clean(prm),
                 'encoding': 'feature value = the level index (0-based) of the reading at the decision row (heat.read_state: its last closed bar) '
                             'minus the feature offset (an ordinal reading\'s neutral level; 0 for a categorical one), NaN = unknown; ZS:<name> = '
                             'the zone event on that bar (heat_xdata.ZS_LEVELS). score = init_score + the trees (tree_eval).',
                 'features': [{'name': F['name'], 'k': int(F['R']['k']), 'levels': F['levels'], 'categorical': F['cat'], 'offset': int(F['offset']),
                               'family': F['family'],
                               'zs_of': F['zs_of'], 'aliases': list(F['R'].get('aliases', [])) if not F['zs'] else []} for F in fs['feats']],
                 'used': used, 'seconds': round(time.time() - t0, 1)}
    _check_json(tj)
    booster.hm2 = {'model': model, 'h': int(H), 'names': fs['names'], 'funcs': [F['funcs'] for F in fs['feats']],
                   'family': [F['family'] for F in fs['feats']], 'group': [F['group'] for F in fs['feats']],
                   'levels': [F['levels'] for F in fs['feats']], 'offset': fs['offset'], 'init_score': init, 'tree_json': tj, 'rows': rows,
                   'label': ctx.label}
    return booster, used, tj


def _check_json(x) -> None:
    """The tree JSON is written with allow_nan False: no NaN or inf anywhere."""
    json.dumps(x, allow_nan=False)


# --------------------------------------------------------------------------------------------------- tree evaluation
def compile_trees(tree_json: dict, cols: dict = None) -> dict:
    """The dumped trees as flat arrays. Internal nodes 0..; a child < 0 is the leaf -(child + 1). cols: feature index ->
    column of the matrix that will be evaluated (default: the same index)."""
    feat, thr, kind, dleft, mtype, left, right, catoff, catlen, cats, leafval, roots = [], [], [], [], [], [], [], [], [], [], [], []
    MT = {'None': 0, 'Zero': 1, 'NaN': 2}

    def node(d):
        if 'leaf_value' in d or 'split_feature' not in d:
            leafval.append(float(d['leaf_value']))
            return -len(leafval)
        i = len(feat)
        f = int(d['split_feature'])
        feat.append(cols[f] if cols is not None else f)
        dleft.append(bool(d.get('default_left', False)))
        mtype.append(MT[d.get('missing_type', 'None')])
        left.append(0)
        right.append(0)
        if d['decision_type'] == '==':
            kind.append(1)
            thr.append(np.nan)
            cs = [int(x) for x in str(d['threshold']).split('||') if x != '']
            n = (max(cs) + 1) if cs else 0
            catoff.append(len(cats))
            catlen.append(n)
            bits = [False] * n
            for x in cs:
                bits[x] = True
            cats.extend(bits)
        elif d['decision_type'] == '<=':
            kind.append(0)
            thr.append(float(d['threshold']))
            catoff.append(0)
            catlen.append(0)
        else:
            raise SystemExit(f'tree node with decision_type {d["decision_type"]}')
        left[i] = node(d['left_child'])
        right[i] = node(d['right_child'])
        return i

    for t in tree_json['tree_info']:
        roots.append(node(t['tree_structure']))
    A = lambda x, dt: np.asarray(x, dt) if len(x) else np.zeros(0, dt)
    return {'feat': A(feat, np.int64), 'thr': A(thr, np.float64), 'kind': A(kind, np.int8), 'dleft': A(dleft, np.bool_), 'mtype': A(mtype, np.int8),
            'left': A(left, np.int64), 'right': A(right, np.int64), 'catoff': A(catoff, np.int64), 'catlen': A(catlen, np.int64),
            'cats': A(cats, np.bool_), 'leaf': A(leafval, np.float64), 'roots': A(roots, np.int64)}


def used_features(tree_json: dict) -> list:
    """Feature indices with at least one split, sorted."""
    return sorted({int(f) for f in compile_trees(tree_json)['feat']})


def _walk(T: dict, X: np.ndarray) -> np.ndarray:
    """The trees on X (float64, NaN = unknown), vectorised over rows, one tree at a time and summed in tree order (as
    LightGBM sums them). LightGBM's decisions: numerical - NaN is 0.0 unless the node's missing type is NaN; a missing
    value (NaN for type NaN, |x| <= 1e-35 for type Zero) takes the default side, else x <= threshold goes left;
    categorical - NaN or a negative value goes right, else left when the category is in the node's set."""
    n = len(X)
    out = np.zeros(n)
    ar = np.arange(n)
    for r in T['roots']:
        node = np.full(n, r, np.int64)
        act = ar[node >= 0]
        while len(act):
            nd = node[act]
            x = X[act, T['feat'][nd]]
            isn = np.isnan(x)
            mt = T['mtype'][nd]
            xz = np.where(isn & (mt != 2), 0.0, x)
            miss = ((mt == 1) & (np.abs(xz) <= ZERO_T)) | ((mt == 2) & isn)
            with np.errstate(invalid='ignore'):
                num = np.where(miss, T['dleft'][nd], xz <= T['thr'][nd])
                iv = np.where(isn | (x < 0), -1, np.trunc(np.nan_to_num(x, nan=-1.0))).astype(np.int64)
            ok = (iv >= 0) & (iv < T['catlen'][nd])
            cat = np.zeros(len(nd), bool)
            cat[ok] = T['cats'][T['catoff'][nd][ok] + iv[ok]]
            go = np.where(T['kind'][nd] == 0, num, cat)
            node[act] = np.where(go, T['left'][nd], T['right'][nd])
            act = act[node[act] >= 0]
        out += T['leaf'][-node - 1]
    return out


def tree_offsets(tree_json: dict) -> np.ndarray:
    """Each feature's value offset (the hm2 block; 0 when absent)."""
    feats = tree_json.get('hm2', {}).get('features') or []
    return np.array([float(F.get('offset', 0)) for F in feats], np.float64) if feats else None


def tree_eval(tree_json: dict, X: np.ndarray, with_init: bool = False) -> np.ndarray:
    """Pure numpy evaluator of the dumped trees (for the bot and the tests). X [rows, features]: integer level codes
    (-1 = unknown; the hm2 block's offsets turn them into LightGBM's values), or floats already in LightGBM's values
    (what booster.predict gets; NaN = unknown). Returns LightGBM's raw score (booster.predict), plus the A base mean
    sign (the fit's init_score) with with_init: then the model's mean sign, whose shift x 50 is in odds points."""
    X = np.asarray(X)
    if np.issubdtype(X.dtype, np.floating):
        Xf = X.astype(np.float64)
    else:
        off = tree_offsets(tree_json)
        Xf = X.astype(np.float64) - (off if off is not None else 0.0)
        Xf[X < 0] = np.nan
    s = _walk(compile_trees(tree_json), Xf)
    if with_init:
        s = s + float(tree_json.get('hm2', {}).get('init_score', 0.0))
    return s


@nb.njit(cache=True)
def _nb_walk(X, feat, thr, kind, dleft, mtype, left, right, catoff, catlen, cats, leaf, roots, out):
    """_walk compiled (rows outer, trees inner, summed in tree order): the per-minute score of the GBM reading."""
    for i in range(X.shape[0]):
        s = 0.0
        for t in range(roots.shape[0]):
            node = roots[t]
            while node >= 0:
                x = X[i, feat[node]]
                isn = np.isnan(x)
                if kind[node] == 0:
                    mt = mtype[node]
                    if isn and mt != 2:
                        x = 0.0
                    if (mt == 1 and abs(x) <= 1e-35) or (mt == 2 and isn):
                        go = dleft[node]
                    else:
                        go = x <= thr[node]
                else:
                    go = False
                    if not isn and x >= 0:
                        iv = int(x)
                        if iv < catlen[node]:
                            go = cats[catoff[node] + iv]
                node = left[node] if go else right[node]
            s += leaf[-node - 1]
        out[i] = s


def score_rows(ctx, model: str, tree_json: dict, rows: np.ndarray) -> np.ndarray:
    """The model's raw score at minute rows, in SCORE_CHUNK chunks, reading only the features the trees use. NaN where
    the minute is forward-filled (a gap) or every used reading is unknown."""
    fs = feature_set(ctx, model)
    used = used_features(tree_json)
    off = fs['offset'][used]
    T = compile_trees(tree_json, {f: c for c, f in enumerate(used)})
    rows = np.asarray(rows, np.int64)
    out = np.full(len(rows), np.nan)
    gap = ctx.m['gap']
    for s in range(0, len(rows), SCORE_CHUNK):
        r = rows[s:s + SCORE_CHUNK]
        U = features(ctx, model, r, used)
        Xf = as_float(U, off).astype(np.float64)
        v = np.empty(len(r))
        _nb_walk(Xf, T['feat'], T['thr'], T['kind'], T['dleft'], T['mtype'], T['left'], T['right'], T['catoff'], T['catlen'], T['cats'], T['leaf'],
                 T['roots'], v)
        bad = gap[r] | ((U < 0).all(1) if len(used) else np.zeros(len(r), bool))
        v[bad] = np.nan
        out[s:s + SCORE_CHUNK] = v
    return out


# --------------------------------------------------------------------------------------------- the call as a reading
def gbm_reading(ctx, booster, model: str, H: int) -> tuple:
    """GBM.<model><H> (k = 1): the score at every minute of the grid (both splits) in five zones at A's quantiles of the
    score (ZONE_Q over the rows of split A, heat_xdata.zone), NA on a forward-filled minute. A model without a split
    (a constant score) gives a reading that is 'mid' wherever known (no event). Returns (reading, edges); the reading
    carries `call` (call_stats: each zone's direction from its own A odds and its 2025 numbers), also kept on
    booster.hm2['call'] so contributions() reports it."""
    tj = booster.hm2['tree_json'] if hasattr(booster, 'hm2') else booster.dump_model()
    name = f'GBM.{model}{H}'
    score = score_rows(ctx, model, tj, np.arange(ctx.m['n']))
    R, edges = xd.zone(name, score, ctx.g.sp['A'].hi, typ='gbm', family='model')
    if R is None:
        codes = np.where(np.isfinite(score), 2, -1).astype(np.int8)
        R = {'name': name, 'k': 1, 'codes': codes, 'levels': heat.ZONES, 'base': name, 'type': 'gbm', 'zones': True, 'family': 'model',
             'edges': None, 'degenerate': True}
        edges = None
    R.update(model=model, h=int(H), used=len(used_features(tj)))
    R['call'] = call_stats(ctx, R, H)
    if hasattr(booster, 'hm2'):
        booster.hm2['call'] = R['call']
    return R, edges


def call_stats(ctx, R: dict, H: int) -> dict:
    """The call of a zone reading scored with the scan's entries and statistics (heat_hm2._stats: odds = 50 x (mean sign
    - base mean sign) with the day-clustered t). Per level and horizon: n, odds and t on A and B. Each non-neutral zone's
    direction is the sign of its own A odds at H; on B the call is right when the move goes that way: hit_B = right /
    (right + wrong) over the non-flat B entries of the non-neutral zones (0.5 = no call), and odds_B_dir = the B odds
    in the A direction."""
    L = len(R['levels'])
    code = heat.read_state(R, ctx.rows).astype(np.int64) + 1
    P = hm._bins(code * ctx.ND + ctx.day, ctx.W, (L + 1) * ctx.ND).reshape(5, L + 1, ctx.ND)
    st = {k: v[..., 0] for k, v in hm._stats(P[:, 1:, None, :], ctx, lift=False).items()}          # (2, 6, L)
    hi = hm.H_SCAN.index(H)
    d = np.sign(np.nan_to_num(st['odds'][0, hi]))
    out = {'name': R['name'], 'h': int(H), 'levels': list(R['levels']), 'dir_A': d.astype(int).tolist()}
    for si, sn in ((0, 'A'), (1, 'B')):
        n, pu, pdn = (np.nan_to_num(st[k][si, hi]) for k in ('n', 'p_up', 'p_dn'))
        right = np.where(d > 0, n * pu, n * pdn)
        wrong = np.where(d > 0, n * pdn, n * pu)
        use = (d != 0) & np.array([lv not in heat.NEUTRAL for lv in R['levels']])
        rt, wt = float(right[use].sum()), float(wrong[use].sum())
        out[f'hit_{sn}'] = rt / (rt + wt) if rt + wt > 0 else None
        out[f'n_call_{sn}'] = int(n[use].sum())
        out[f'odds_{sn}_dir'] = (st['odds'][si, hi] * d).tolist()
        out[f't_{sn}_dir'] = (st['t'][si, hi] * d).tolist()
        out[f'n_{sn}'] = n.astype(int).tolist()
    out['by_h'] = {'h': list(hm.H_SCAN), **{f'{k}_{sn}': st[k][si].T.tolist() for k in ('odds', 't', 'n') for si, sn in ((0, 'A'), (1, 'B'))}}
    return hm._clean(out)


# ---------------------------------------------------------------------------------------------------- the leaf paths
def _branch_sets(d: dict, L: int, off: float = 0.0):
    """(left set, right set) of a node over the level indices 0..L-1 and -1 (unknown), by LightGBM's decision rules
    on the values (level index - offset)."""
    dom = list(range(L)) + [-1]
    mt = d.get('missing_type', 'None')
    dl = bool(d.get('default_left', False))
    left = set()
    if d['decision_type'] == '==':
        cs = {int(x) for x in str(d['threshold']).split('||') if x != ''}
        left = {v for v in dom if v >= 0 and v in cs}
    else:
        thr = float(d['threshold'])
        for v in dom:
            x = 0.0 if (v < 0 and mt != 'NaN') else (math.nan if v < 0 else float(v) - off)
            if (mt == 'Zero' and abs(x) <= ZERO_T) or (mt == 'NaN' and v < 0):
                go = dl
            else:
                go = x <= thr
            if go:
                left.add(v)
    return left, set(dom) - left


def _rule_form(sets: dict, feats: list) -> tuple:
    """(scan form, tree form, exact) of one path's level sets {feature: set of level indices, -1 = unknown}. The tree
    form names the features (ZS states included); the scan form maps a ZS condition onto its zone reading (the zones
    its events land in; an event set that holds 'none' does not fix the zone and is left out) and intersects it with
    the reading's own condition. A condition that keeps every level and the unknown is no condition."""
    def lv_list(levels, s):
        return [levels[v] for v in sorted(x for x in s if x >= 0)] + (['NA'] if -1 in s else [])
    tree, scan, exact = [], {}, True
    for f in sorted(sets, key=lambda i: feats[i]['name']):
        F, s = feats[f], sets[f]
        L = len(F['levels'])
        if s >= set(range(L)) | {-1}:
            continue
        tree.append([F['name'], lv_list(F['levels'], s)])
        if F.get('zs_of'):
            exact = False
            zl = list(heat.ZONES)
            if any(F['levels'][v] == 'none' for v in s if v >= 0):
                continue
            z = {zl.index(ZS_ZONE[F['levels'][v]]) for v in s if v >= 0} | ({-1} if -1 in s else set())
            nm, levels = F['zs_of'], zl
        else:
            z, nm, levels = s, F['name'], F['levels']
        old = scan.get(nm, (set(range(len(levels))) | {-1}, levels))[0]
        scan[nm] = (old & z, levels)
    out = []
    for nm in sorted(scan):
        s, levels = scan[nm]
        if s >= set(range(len(levels))) | {-1}:
            continue
        out.append([nm, lv_list(levels, s)])
    return out, tree, exact


def leaf_paths(tree_json: dict) -> list:
    """Every root-to-leaf path of the dumped trees as a rule. Predicates on one feature merge into a level set; the
    missing-value routing becomes the level 'NA'. Identical rules (same scan form) from several leaves are one rule.
    Each rule: conds (the scan form, [[reading, [levels]], ...], what heat_hm2 measures), conds_tree (the trees' own
    predicates, ZS states included), exact (the two agree), n_readings, leaves, trees (the first 20), leaf_count (the
    training rows that reached its leaves), odds (50 x the first leaf's value) and odds_sum (50 x the sum over its
    leaves: what the model adds there in odds points). A path with no condition (a tree of one leaf) is no rule."""
    meta = tree_json.get('hm2', {})
    feats = meta.get('features') or [{'name': n, 'levels': None, 'zs_of': None} for n in tree_json['feature_names']]
    nlev = [len(F['levels']) if F.get('levels') else None for F in feats]
    rules = {}

    def walk(d, sets, t):
        if 'split_feature' not in d:
            if not sets:
                return
            scan, tree, exact = _rule_form(sets, feats)
            if not scan:
                return
            key = json.dumps(scan)
            r = rules.get(key)
            v = float(d['leaf_value'])
            if r is None:
                rules[key] = {'conds': scan, 'conds_tree': tree, 'exact': exact, 'n_readings': len(scan), 'leaves': 1, 'trees': [t],
                              'leaf_count': int(d.get('leaf_count', 0)), 'odds': ODDS * v, 'odds_sum': ODDS * v}
            else:
                r['leaves'] += 1
                r['exact'] = r['exact'] and exact
                if len(r['trees']) < 20 and r['trees'][-1] != t:
                    r['trees'].append(t)
                r['leaf_count'] += int(d.get('leaf_count', 0))
                r['odds_sum'] += ODDS * v
            return
        f = int(d['split_feature'])
        L = nlev[f]
        if L is None:
            raise SystemExit('leaf_paths: the tree JSON has no hm2 feature levels')
        ls, rs = _branch_sets(d, L, float(feats[f].get('offset', 0)))
        dom = set(range(L)) | {-1}
        for side, child in ((ls, d['left_child']), (rs, d['right_child'])):
            s2 = dict(sets)
            s2[f] = s2.get(f, dom) & side
            if s2[f]:
                walk(child, s2, t)

    for t in tree_json['tree_info']:
        walk(t['tree_structure'], {}, int(t.get('tree_index', 0)))
    return list(rules.values())


def merge_paths(paths: list) -> list:
    """Rules of several fits (each with 'model' and 'h') as one list: an identical scan form is one rule with its
    sources [[model, h, leaves, odds_sum], ...] (the scan then measures it once)."""
    out = {}
    for p in paths:
        key = json.dumps(p['conds'])
        src = [p.get('model'), p.get('h'), p['leaves'], round(p['odds_sum'], 6)]
        if key not in out:
            out[key] = dict(p, sources=[src])
        else:
            q = out[key]
            q['sources'].append(src)
            q['leaves'] += p['leaves']
            q['leaf_count'] += p['leaf_count']
            q['exact'] = q['exact'] and p['exact']
    return list(out.values())


# --------------------------------------------------------------------------------------------------------- the usage
def contributions(booster, X: np.ndarray, meta: dict = None) -> dict:
    """LightGBM's pred_contrib on X (the features of seeded 2025 minutes: contrib_rows), in odds points (x 50): per used
    reading the mean contribution of each of its levels ('NA' = unknown) and its mean |contribution|; per TA function
    (heat_pack.indicator with the settings stripped; a merged reading counts for the function of each of its names, a
    ZS state for its zone reading's), per family and per partner group the mean |sum of its readings' contributions|
    (contributions add up, so a group's is the sum of its members'). Also the call (gbm_reading's call_stats) when the
    booster has one. The model's view, not evidence."""
    meta = meta or booster.hm2
    X = np.asarray(X)
    if np.issubdtype(X.dtype, np.floating):
        raise SystemExit('contributions: X must be the level codes of features() (int8, -1 = unknown)')
    C = booster.predict(as_float(X, meta['offset']), pred_contrib=True)
    n = len(X)
    names = meta['names']
    used = np.flatnonzero(np.abs(C[:, :-1]).sum(0) > 0)
    codes = X.astype(np.int64)
    by_reading, by_level = {}, {}
    for j in used:
        c = C[:, j] * ODDS
        by_reading[names[j]] = {'mean_abs': float(np.abs(c).mean()), 'mean': float(c.mean()), 'family': meta['family'][j], 'group': meta['group'][j],
                                'funcs': meta['funcs'][j]}
        lv = {}
        for v in np.unique(codes[:, j]):
            sel = codes[:, j] == v
            lv['NA' if v < 0 else meta['levels'][j][v]] = {'n': int(sel.sum()), 'mean': float(c[sel].mean())}
        by_level[names[j]] = lv

    def grouped(keys_of) -> dict:
        acc = {}
        for j in used:
            for k in keys_of(j):
                acc.setdefault(k, []).append(j)
        out = {}
        for k, js in sorted(acc.items()):
            s = C[:, js].sum(1) * ODDS
            out[k] = {'mean_abs': float(np.abs(s).mean()), 'mean': float(s.mean()), 'readings': len(js)}
        return out
    res = {'rows': int(n), 'split': 'B', 'units': 'odds points (50 x mean sign)', 'model': meta.get('model'), 'h': meta.get('h'),
           'expected': float(C[0, -1] * ODDS) if n else None, 'used': int(len(used)),
           'by_reading': by_reading, 'by_level': by_level,
           'by_function': grouped(lambda j: meta['funcs'][j]), 'by_family': grouped(lambda j: [meta['family'][j]]),
           'by_group': grouped(lambda j: [meta['group'][j]])}
    if meta.get('call') is not None:
        res['call'] = meta['call']
    return hm._clean(res)


# ----------------------------------------------------------------------------------------------- the usage cards
def card_grid(ctx) -> dict:
    """Raw inputs of each TA function's settings x timeframe grid: for every engine vocabulary reading (and each alias,
    with its kept reading's numbers) its function, setting and timeframe, and per non-neutral level and horizon
    (H_SCAN) its own state odds, t and n on A (the scan's part effects) and on B in its A direction. Per zone or sign
    reading: fade or follow of the extreme zones (very low fading = up, very high fading = down; for a sign reading
    'above 0' up = follow) at each horizon, the horizon where it is strongest on A (largest mean |t_A| of the extreme
    levels: chosen on A only) and on B (largest mean B odds in the A direction)."""
    out = {}
    for j, R in enumerate(ctx.readings):
        names = [R['name']] + list(R.get('aliases', []))
        lv = [i for i, x in enumerate(R['levels']) if x not in heat.NEUTRAL]
        if not lv or not any(ta_parts(nm) for nm in names):
            continue
        po, pt, pn = ctx.parts['odds'][j], ctx.parts['t'][j], ctx.parts['n'][j]       # (2, 6, L)
        kind = 'zone' if R.get('zones') else 'sign' if list(R['levels']) == SIGN_LV else 'pattern' if R.get('every') else 'state'
        d = np.sign(np.nan_to_num(po[0][:, lv]))                                        # (6, levels)
        sq = {'kind': kind, 'levels': [R['levels'][i] for i in lv], 'h': list(hm.H_SCAN),
              'odds_A': po[0][:, lv].T, 't_A': pt[0][:, lv].T, 'n_A': pn[0][:, lv].T,
              'odds_B_dir': (po[1][:, lv] * d).T, 't_B_dir': (pt[1][:, lv] * d).T, 'n_B': pn[1][:, lv].T, 'dir_A': d.T.astype(int)}
        ext = [c for c, i in enumerate(lv) if R['levels'][i] in EXTREME or (kind == 'sign' and R['levels'][i] == 'above 0')]
        if kind in ('zone', 'sign') and ext:
            ff = {}
            for c in ext:
                nm = sq['levels'][c]
                fade = EXTREME.get(nm, -1)                                              # 'above 0': fading is down
                ff[nm] = ['fade' if x == fade else 'follow' if x == -fade else None for x in d[:, c]]
            sq['fade_follow'] = ff
            with np.errstate(invalid='ignore'):
                sa = np.nanmean(np.abs(pt[0][:, [lv[c] for c in ext]]), 1)
                sb = np.nanmean((po[1][:, lv] * d)[:, ext], 1)
            sq['best_h_A'] = int(hm.H_SCAN[int(np.nanargmax(sa))]) if np.isfinite(sa).any() else None
            sq['best_h_B'] = int(hm.H_SCAN[int(np.nanargmax(sb))]) if np.isfinite(sb).any() else None
        for a, nm in enumerate(names):
            p = ta_parts(nm)
            if p is None:
                continue
            fn, setting, tf = p
            row = dict(sq, reading=nm, setting=setting, tf=tf, sign_reading=nm.endswith(' sign'))
            if a:
                row['alias_of'] = R['name']
            out.setdefault(fn, []).append(row)
    return hm._clean({fn: sorted(v, key=lambda r: (int(r['tf'][:-1]), r['setting'], r['reading'])) for fn, v in sorted(out.items())})


def card_partners(ctx, cands: pd.DataFrame) -> list:
    """Raw inputs of each TA function's best partner per data family: among the pair cells of the candidate pool (the
    scan's best cells per horizon and measure, as heat_hm2 keeps them), per (function, partner group, horizon) the cell
    with the largest iheat_B where one reading is a TA vocabulary reading of the function and the other is the partner:
    reading, level, direction, iota_with_call (False: the partner flips the call, a stand-aside lesson), iota_robust_B,
    odds_B, wd_B, n_B, key and seen_in_league. A function or group with no cell in the pool has no entry."""
    if cands is None or not len(cands):
        return []
    df = cands[cands['kind'] == 'pair'].drop_duplicates(['key', 'h'])
    best = {}
    for r in df.itertuples(index=False):
        v = float(r.iheat_B)
        if not math.isfinite(v):
            continue
        ia, ib = int(r.ia), int(r.ib)
        for me, la, ot, lo in ((ia, int(r.la), ib, int(r.lb)), (ib, int(r.lb), ia, int(r.la))):
            R, P = ctx.readings[me], ctx.readings[ot]
            fns = sorted({f for f in map(ta_function, [R['name']] + list(R.get('aliases', []))) if f})
            grp = card_group(P, ctx.fam[ot])
            for fn in fns:
                k = (fn, grp, int(r.h))
                if k not in best or v > best[k]['iheat_B']:
                    best[k] = {'func': fn, 'group': grp, 'h': int(r.h), 'reading': R['name'], 'level': R['levels'][la], 'partner': P['name'],
                               'partner_level': P['levels'][lo], 'partner_family': ctx.fam[ot], 'dir': int(r.dir), 'iota_with_call': bool(r.iota_with_call),
                               'iheat_B': v, 'iota_robust_B': float(getattr(r, 'iota_robust_B', np.nan)), 'odds_B': float(getattr(r, 'odds_B', np.nan)),
                               'wd_B': float(getattr(r, 'wd_B', np.nan)), 'n_B': int(getattr(r, 'n_B', 0)), 'key': r.key,
                               'seen_in_league': getattr(r, 'seen_in_league', None)}
    return hm._clean([best[k] for k in sorted(best)])


def card_inputs(ctx, cands: pd.DataFrame = None) -> dict:
    """Both raw inputs of the usage cards for one series (the league puts each beside the twins' median and range)."""
    return {'schema': 'oracle-heat-hm2-cards-1', 'label': ctx.label, 'twin': int(ctx.twin), 'grid': card_grid(ctx),
            'partners': card_partners(ctx, cands)}


# ---------------------------------------------------------------------------------------------------- the whole part
def run_learner(ctx, out: str = '', log=print, models=MODELS, horizons=None, n_contrib: int = N_CONTRIB) -> dict:
    """Part 2 for one series (a coin or a twin: the identical pipeline). For each model and horizon (LEARN_H): the fit
    on the A entries, the GBM reading, the leaf paths and the contributions on seeded 2025 minutes. Returns
    heat_hm2._learner's dict ({'gbm', 'paths', 'usage', 'trees', 'version'}) with the paths of all fits merged
    (merge_paths: one rule per scan form, with its sources) and 'calls' ({model+H: call_stats}). With out: the trees
    (<out>/trees/<model>_h<H>.json, allow_nan False) and learner_paths.json.gz."""
    import lightgbm
    log = log or _log_none
    horizons = list(hm.LEARN_H if horizons is None else horizons)
    res = {'gbm': [], 'paths': [], 'usage': {}, 'trees': {}, 'version': lightgbm.__version__, 'calls': {}}
    if out:
        os.makedirs(os.path.join(out, 'trees'), exist_ok=True)
    rows = contrib_rows(ctx, n_contrib)
    raw = []
    for model in models:
        XB = features(ctx, model, rows)
        for H in horizons:
            t = time.time()
            booster, used, tj = learn(ctx, model, H)
            R, _ = gbm_reading(ctx, booster, model, H)
            res['gbm'].append(R)
            res['calls'][f'{model}{H}'] = R['call']
            if out:
                p = os.path.join(out, 'trees', f'{model}_h{H}.json')
                with open(p, 'w') as f:
                    json.dump(tj, f, allow_nan=False)
                with open(p, 'rb') as f:
                    sha = hashlib.sha256(f.read()).hexdigest()
                res['trees'][f'{model}_h{H}'] = {'file': os.path.relpath(p, out), 'sha256': sha, 'used': list(used)}
            raw += [dict(rule, model=model, h=H) for rule in leaf_paths(tj)]
            res['usage'][f'{model}{H}'] = contributions(booster, XB)
            c = R['call']
            log(f'  learner {ctx.label} {model} h{H}: {len(used)} readings used, B call {c.get("hit_B")} on {c.get("n_call_B")} entries '
                f'({time.time() - t:.0f}s, {hm._rss_mb()} MB)')
            del booster
        del XB
        ctx.__dict__.pop('_hl_X', None)
    res['paths'] = merge_paths(raw)
    if out:
        with gzip.open(os.path.join(out, 'learner_paths.json.gz'), 'wt') as f:
            json.dump(hm._clean(res['paths']), f, allow_nan=False)
    log(f'  learner {ctx.label}: {len(raw):,} leaf rules, {len(res["paths"]):,} distinct, '
        f'{sum(p["n_readings"] == 3 for p in res["paths"]):,} of three readings')
    drop_cache(ctx)
    return res


# --------------------------------------------------------------------------------------------------------------- CLI
def main(argv=None):
    ap = argparse.ArgumentParser(prog='oracle.heat_hm2_learn')
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('paths')
    p.add_argument('--tree', required=True)
    p.add_argument('--min-readings', type=int, default=1)
    p.add_argument('--out', default='')
    a = ap.parse_args(argv)
    with open(a.tree) as f:
        tj = json.load(f)
    rules = [r for r in leaf_paths(tj) if r['n_readings'] >= a.min_readings]
    rules.sort(key=lambda r: -abs(r['odds_sum']))
    txt = json.dumps(hm._clean(rules), indent=1, allow_nan=False)
    if a.out:
        with open(a.out, 'w') as f:
            f.write(txt)
    print(txt if not a.out else f'{len(rules)} rules -> {a.out}')


if __name__ == '__main__':
    main()
