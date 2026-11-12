"""OR-HM2 part 2, the learner (python/oracle/heat_hm2_learn.py; build plan section 3): no 2025 row (and no label that
reads a 2025 price) is ever in a fit, the model's 2025 call on pure noise is a coin flip (coin and twin), a planted
three-reading rule comes back as a leaf path naming the planted readings (and the scan measures it with iota3 > 0),
the fits are deterministic, the tree JSON reproduces LightGBM's scores, the chunked Dataset equals LightGBM's own
loader, the contributions come from 2025 minutes only, the leaf paths follow LightGBM's decision rules (ZS states mapped
onto their zone reading), the features and the call are causal, the usage cards' raw inputs (the kept share from the
pair scan's per-reading tally), and heat_hm2.run_series runs the learner (coin and twin) and hands its merged rules to
the triple scan. Synthetic minutes, SPLITS patched, procs 1."""
import gzip
import json
import types

import numpy as np
import pandas as pd
import pytest

from oracle import heat
from oracle import heat_hm2 as hm
from oracle import heat_hm2_learn as hl
from oracle import heat_xdata as xd
from oracle.common import DAY, MIN


def _splits(monkeypatch, a_days: int, b_days: int) -> int:
    start = heat.HEAT_END - (a_days + b_days) * DAY
    monkeypatch.setattr(heat, 'SPLITS', {'A': (start, start + a_days * DAY), 'B': (start + a_days * DAY, heat.HEAT_END)})
    return start


def _csv(path, start, days, seed=0):
    """A random walk of 1-minute bars (open = the previous close)."""
    rng = np.random.default_rng(seed)
    n = days * 1440
    c = 100 * np.exp(np.cumsum(rng.normal(0, 8e-4, n)))
    o = np.r_[100, c[:-1]]
    w = np.abs(rng.normal(0, 3e-4, n))
    v = rng.uniform(1, 2, n)
    pd.DataFrame({'ts': start + np.arange(n) * MIN, 'o': o, 'h': np.maximum(o, c) * (1 + w), 'l': np.minimum(o, c) * (1 - w), 'c': c, 'v': v,
                  'tb': v * rng.uniform(0.3, 0.7, n)}).to_csv(path, index=False)


def _zone(name, x, k, a_bars, **kw):
    xa = x[:a_bars]
    e = np.quantile(xa[np.isfinite(xa)], heat.ZONE_Q)
    return dict({'name': name, 'k': k, 'codes': heat.bucket(x, e), 'levels': heat.ZONES, 'base': name, 'zones': True, 'type': 'osc'}, **kw)


def _readings(m, g):
    """Causal readings of the coin's own path (1- and 15-minute zones of 3/10-bar returns, the sign of the 5-bar
    return), a new-family zone and a categorical position state with an unknown stretch: on a random walk none of them
    knows the next move."""
    c = np.log(m['c'])
    out = []
    for k in (1, 15):
        nb = m['n'] // k
        cb = c[k - 1::k][:nb]
        a_bars = g.sp['A'].hi // k
        for L in (3, 10):
            out.append(_zone(f'{k}m:R{L}', np.r_[np.full(L, np.nan), cb[L:] - cb[:-L]], k, a_bars))
        x = np.r_[np.full(5, np.nan), cb[5:] - cb[:-5]]
        out.append({'name': f'{k}m:R5 sign', 'k': k, 'codes': np.where(np.isfinite(x), (x > 0).astype(np.int8), -1).astype(np.int8),
                    'levels': ['below 0', 'above 0'], 'base': f'{k}m:R5', 'type': 'osc'})
    r30 = np.r_[np.full(30, np.nan), c[30:] - c[:-30]]
    out.append(_zone('FLOW:Stretch30', r30, 1, g.sp['A'].hi, family='flow'))
    q = ((m['t0'] // MIN + np.arange(m['n']) + 1) % 15).astype(np.int8)
    q[3000:4500] = -1
    out.append({'name': 'POS:QPos', 'k': 1, 'codes': q, 'levels': [f'm{i:02d}' for i in range(15)], 'base': 'POS:QPos', 'ctx': True,
                'family': 'position'})
    return out


def _ctx(m, R, lab=None, lab240=None, twin=0):
    lab = heat.labels(m) if lab is None else lab
    g = heat.Grid(m, lab)
    if lab240 is None:
        with hm.h240():
            lab240 = heat.labels(m)
    with hm.h240():
        g240 = heat.Grid(m, lab240)
    return hm.make_ctx(m, R, 'X', twin, lab=lab, g=g, lab240=lab240, g240=g240, log=lambda *a: None)


def _noise_ctx(tmp_path, monkeypatch, a_days=90, b_days=30, seed=11, twin=0):
    start = _splits(monkeypatch, a_days, b_days)
    f = tmp_path / 'x.csv'
    if not f.exists():
        _csv(f, start, a_days + b_days, seed)
    m = heat.load_minutes(str(f))
    if twin:
        m = heat.make_twin(m, twin)
    lab = heat.labels(m)
    return _ctx(m, _readings(m, heat.Grid(m, lab)), lab=lab, twin=twin)


# ------------------------------------------------------------------------------------------- no 2025 row in a fit
def test_training_never_sees_a_B_row(tmp_path, monkeypatch):
    """Every training row is an A entry whose label ends before the first 2025 minute (at 240 minutes too), the guard
    stops a fit that would read one, and replacing every 2025 label and every reading's 2025 bars with noise leaves
    each fitted model identical bit for bit. The contribution minutes are 2025 minutes only."""
    ctx = _noise_ctx(tmp_path, monkeypatch)
    b0 = hl.b_start_row(ctx)
    assert b0 == (heat.SPLITS['B'][0] - ctx.m['t0']) // MIN
    rng = np.random.default_rng(3)
    lab2, l2402 = dict(ctx.lab), dict(ctx.lab240)
    late = np.arange(ctx.m['n']) >= ctx.g.sp['A'].hi
    for H in hm.H_MAIN:
        lab2[f'sg{H}'] = np.where(late, rng.integers(-1, 2, ctx.m['n']), ctx.lab[f'sg{H}']).astype(np.int8)
    l2402['sg240'] = np.where(late, rng.integers(-1, 2, ctx.m['n']), ctx.lab240['sg240']).astype(np.int8)
    R2 = []
    for R in ctx.readings:
        R = dict(R)
        close = np.arange(len(R['codes'])) * R['k'] + R['k'] - 1
        R['codes'] = np.where(close >= b0 - 1, rng.integers(-1, len(R['levels']), len(R['codes'])), R['codes']).astype(np.int8)
        R2.append(R)
    ctx2 = _ctx(ctx.m, R2, lab=lab2, lab240=l2402)
    for H in hm.LEARN_H:
        for model in hl.MODELS:
            b1, used, tj = hl.learn(ctx, model, H)
            rows = b1.hm2['rows']
            assert np.all(np.isin(rows, ctx.rows[ctx.split == 0])) and rows.max() + H <= b0 - 1
            assert tj['hm2']['last_row'] + H < tj['hm2']['first_2025_row']
            if H == 240:
                assert np.all(np.isin(rows, ctx.g240.sp['A'].rows)) and rows.max() < ctx.g240.sp['A'].hi
            b2, _, _ = hl.learn(ctx2, model, H)
            assert b1.model_to_string() == b2.model_to_string(), (model, H)
    # the guard: an entry of 2025 passed off as an A entry stops the fit
    bad = types.SimpleNamespace(**{**ctx.__dict__, 'split': ctx.split.copy()})
    bad.split[np.flatnonzero(ctx.split == 1)[0]] = 0
    with pytest.raises(SystemExit, match='2025'):
        hl.train_rows(bad, 15)
    cr = hl.contrib_rows(ctx)
    assert len(cr) == min(hl.N_CONTRIB, ctx.g.sp['B'].N) and cr.min() >= b0 - 1 and np.all(np.isin(cr, ctx.g.sp['B'].rows))


# ------------------------------------------------------------------------------------------------- pure noise
def test_pure_noise_B_call_near_half(tmp_path, monkeypatch):
    """A random walk and its coin-flip twin through the identical pipeline (run_learner): at every horizon and for
    both models the 2025 call is right on 45-55% of its non-flat entries and no zone has |t_B| >= 3 in its A direction.
    The series files are written (trees with the hm2 block, allow_nan False; the merged paths) and the result has
    heat_hm2._learner's shape."""
    for tw in (0, 1):
        ctx = _noise_ctx(tmp_path, monkeypatch, twin=tw)
        out = tmp_path / f'out{tw}'
        res = hl.run_learner(ctx, str(out), log=None)
        assert set(res) >= {'gbm', 'paths', 'usage', 'trees', 'version'} and len(res['gbm']) == 2 * len(hm.LEARN_H)
        for R in res['gbm']:
            c = R['call']
            assert R['name'] == f'GBM.{R["model"]}{R["h"]}' and R['k'] == 1 and len(R['codes']) == ctx.m['n']
            if c['n_call_B']:
                assert 0.45 <= c['hit_B'] <= 0.55, (tw, R['name'], c['hit_B'])
            t = np.array([x for x in c['t_B_dir'] if x is not None])
            assert np.all(np.abs(t) < 3), (tw, R['name'], t)
            assert np.all(R['codes'][ctx.m['gap']] == -1)
        for key, tr in res['trees'].items():
            with open(out / tr['file']) as f:
                tj = json.load(f)
            assert tj['hm2']['schema'] == hl.TREE_SCHEMA and tj['hm2']['twin'] == tw and tj['hm2']['used'] == tr['used']
        with gzip.open(out / 'learner_paths.json.gz', 'rt') as f:
            paths = json.load(f)
        assert len(paths) == len(res['paths']) and all(p['sources'] for p in paths)
        assert len({json.dumps(p['conds']) for p in paths}) == len(paths)
        u = res['usage']['ALL15']
        assert u['split'] == 'B' and u['rows'] == len(hl.contrib_rows(ctx)) and 'call' in u


# --------------------------------------------------------------------------------------------- a planted rule
def test_planted_rule_is_a_leaf_path(tmp_path, monkeypatch):
    """Three readings that call direction only together (S1 on, S2 on, S3 high or very high -> up 80%, else a coin
    flip), among noise readings: the three-reading leaf path with the largest positive shift names exactly the planted
    readings with the planted levels, its rule goes through heat_hm2's measure_path with iota3 > 0 on A and on B, and
    the model's 2025 call beats a coin flip. Fixed LightGBM settings: A has 300 days so min_data_in_leaf 3,000 leaves
    room for a depth-3 path."""
    start = _splits(monkeypatch, 300, 30)
    f = tmp_path / 'x.csv'
    _csv(f, start, 330, seed=5)
    m = heat.load_minutes(str(f))
    lab = heat.labels(m)
    with hm.h240():
        l240 = heat.labels(m)
    rng = np.random.default_rng(9)
    n = m['n']
    s1 = (rng.random(n) < 0.7).astype(np.int8)
    s2 = (rng.random(n) < 0.7).astype(np.int8)
    s3 = rng.choice(5, n, p=[0.05, 0.1, 0.15, 0.35, 0.35]).astype(np.int8)
    allin = (s1 == 1) & (s2 == 1) & (s3 >= 3)
    p = np.where(allin, 0.8, 0.5)
    for H in hm.H_MAIN:
        lab[f'sg{H}'] = np.where(rng.random(n) < p, 1, -1).astype(np.int8)
    l240['sg240'] = np.where(rng.random(n) < p, 1, -1).astype(np.int8)
    R = _readings(m, heat.Grid(m, lab))
    R += [{'name': 'S1', 'k': 1, 'codes': s1, 'levels': ['off', 'on'], 'base': 'S1', 'ctx': True, 'state': True},
          {'name': 'S2', 'k': 1, 'codes': s2, 'levels': ['off', 'on'], 'base': 'S2', 'ctx': True, 'state': True},
          {'name': 'S3', 'k': 1, 'codes': s3, 'levels': heat.ZONES, 'base': 'S3', 'zones': True}]
    ctx = _ctx(m, R, lab=lab, lab240=l240)
    b, used, tj = hl.learn(ctx, 'ALL', 15)
    assert {'S1', 'S2', 'S3'} <= set(used)
    three = [r for r in hl.leaf_paths(tj) if r['n_readings'] == 3]
    best = max(three, key=lambda r: r['odds_sum'])
    cd = dict((k, set(v)) for k, v in best['conds'])
    assert set(cd) == {'S1', 'S2', 'S3'} and best['odds_sum'] > 0, best
    assert 'on' in cd['S1'] and 'off' not in cd['S1'] and 'on' in cd['S2'] and 'off' not in cd['S2']
    assert {'high', 'very high'} <= cd['S3'] and not cd['S3'] & {'very low', 'low', 'mid'}
    st = hm.measure_path(ctx, best['conds'])['st'][0]                     # (split, horizon, stat)
    hi = hm.H_SCAN.index(15)
    assert st[0, hi, hm.SI['iota']] > 0 and st[1, hi, hm.SI['iota']] > 0
    Rg, edges = hl.gbm_reading(ctx, b, 'ALL', 15)
    assert edges is not None and Rg['call']['hit_B'] > 0.55
    # the scan form is what heat_hm2 runs: run_series' filter and _set_learner_paths take the rule
    hm._set_learner_paths(ctx, [dict(best, model='ALL', h=15)])
    i1, i2 = ctx.byname['S1'], ctx.byname['S2']
    assert (min(i1, i2), max(i1, i2)) in ctx.lp
    # end to end: run_series hands the merged three-reading rules to the triple scan (b), which measures the planted
    # rule once (both models found it) with iota3 > 0 on A and on B, and marks the planted pairs learner_path (the
    # scan's re-measure, tested in test_heat_hm2_scan, is stubbed: it is most of the time on 330 days)
    monkeypatch.setattr(hm, 'LEARN_H', [15])
    monkeypatch.setattr(hm, 'remeasure', lambda *a, **k: (heat.Rows(), pd.DataFrame(columns=['kind', 'h', 'measure', 'key1', 'key2', 'jaccard'])))
    mt = hm.run_series('X', 'x.csv', str(tmp_path / 'series'), ctx=ctx, procs=1, log=lambda *a: None)
    assert mt['triples']['paths'] >= 1
    with gzip.open(tmp_path / 'series' / 'learner_paths.json.gz', 'rt') as f:
        src = {json.dumps(p['conds']): p['sources'] for p in json.load(f)}
    assert {s[0] for s in src[json.dumps(best['conds'])]} == {'TA', 'ALL'}
    c = pd.read_csv(tmp_path / 'series' / 'candidates.csv.gz', low_memory=False)
    planted = ' & '.join(f'{r}={"|".join(lv)}' for r, lv in best['conds'])
    p = c[(c.source == 'path') & (c.key == planted) & (c.h == 15)]
    assert len(p) and (p.iota_A > 0).all() and (p.iota_B > 0).all() and p.drop_duplicates(['key', 'h', 'measure']).shape[0] == len(p)
    lp = c[(c.kind == 'pair') & c.key.str.startswith('S1=on & S2=on')]
    assert len(lp) and lp.learner_path.all()


# ----------------------------------------------------------------------------------------- the fit and its JSON
def test_learner_deterministic_and_tree_json(tmp_path, monkeypatch):
    """Two fits are equal bit for bit; the chunked Dataset (small chunks forced) gives the model LightGBM's own loader
    gives from the whole float32 matrix; tree_eval (numpy, from the JSON after a round trip) and the compiled per-minute
    scorer equal booster.predict to 1e-9 on rows with unknown ordinal and categorical values; heat_hm2._learner (the
    series job's caller) runs on this module."""
    import lightgbm as lgb
    ctx = _noise_ctx(tmp_path, monkeypatch)
    monkeypatch.setattr(hl, 'X_CHUNK', 7000)
    for model, H in (('ALL', 15), ('TA', 240)):
        b1, u1, tj1 = hl.learn(ctx, model, H)
        b2, u2, tj2 = hl.learn(ctx, model, H)
        assert b1.model_to_string() == b2.model_to_string() and u1 == u2
        fs = hl.feature_set(ctx, model)
        rows, y = hl.train_rows(ctx, H)
        X = hl.features(ctx, model, rows)
        prm = dict(hm.LGB_PARAMS, seed=hm.LGB_SEED + H)
        init = float(ctx.base[0]['bms'][hm.H_SCAN.index(H)])
        ds = lgb.Dataset(hl.as_float(X, fs['offset']), label=y, init_score=np.full(len(rows), init), categorical_feature=fs['cat_idx'],
                         feature_name=[f'f{i:04d}' for i in range(X.shape[1])], params=prm)
        assert lgb.train(prm, ds, num_boost_round=hm.LGB_ROUNDS).model_to_string() == b1.model_to_string()
        # rows with unknowns: the POS:QPos stretch (categorical) and the readings' warm-up (ordinal)
        ev = np.r_[np.arange(0, 5000, 7), hl.contrib_rows(ctx, 3000)]
        Xe = hl.features(ctx, model, ev)
        assert (Xe < 0).any()
        p = b1.predict(hl.as_float(Xe, fs['offset']))
        tj = json.loads(json.dumps(tj1, allow_nan=False))
        assert np.abs(hl.tree_eval(tj, Xe) - p).max() < 1e-9
        assert np.abs(hl.tree_eval(tj, hl.as_float(Xe, fs['offset'])) - p).max() < 1e-9
        assert np.abs(hl.tree_eval(tj, Xe, with_init=True) - p - init).max() < 1e-9
        sc = hl.score_rows(ctx, model, tj1, ev)
        ok = np.isfinite(sc)
        assert ok.sum() > 0.9 * len(ev) and np.abs(sc[ok] - p[ok]).max() < 1e-9
        assert np.all(np.isnan(sc[ctx.m['gap'][ev]]))
    monkeypatch.setattr(hm, 'LEARN_H', [15])
    res = hm._learner(ctx, str(tmp_path / 'series'), lambda *a: None)
    assert [R['name'] for R in res['gbm']] == ['GBM.TA15', 'GBM.ALL15'] and set(res['usage']) == {'TA15', 'ALL15'}
    assert (tmp_path / 'series' / 'trees' / 'ALL_h15.json').exists()


def test_contributions_on_2025_minutes(tmp_path, monkeypatch):
    """pred_contrib on the seeded 2025 minutes: in odds points, per reading and level; a function's and a group's
    numbers are those of the sum of their readings' contributions (a ZS state counts for its zone reading's function);
    the call rides along."""
    ctx = _noise_ctx(tmp_path, monkeypatch)
    b, used, tj = hl.learn(ctx, 'ALL', 60)
    hl.gbm_reading(ctx, b, 'ALL', 60)
    rows = hl.contrib_rows(ctx, 4000)
    X = hl.features(ctx, 'ALL', rows)
    u = hl.contributions(b, X)
    C = b.predict(hl.as_float(X, hl.feature_set(ctx, 'ALL')['offset']), pred_contrib=True) * hl.ODDS
    names = hl.feature_set(ctx, 'ALL')['names']
    assert u['rows'] == len(rows) and u['split'] == 'B' and u['call']['name'] == 'GBM.ALL60'
    assert set(u['by_reading']) == {names[j] for j in np.flatnonzero(np.abs(C[:, :-1]).sum(0) > 0)}
    for nm, r in u['by_reading'].items():
        j = names.index(nm)
        assert abs(r['mean_abs'] - np.abs(C[:, j]).mean()) < 1e-9
        lv = u['by_level'][nm]
        assert sum(v['n'] for v in lv.values()) == len(rows)
    for fn, r in u['by_function'].items():
        js = [j for j, F in enumerate(hl.feature_set(ctx, 'ALL')['feats']) if fn in F['funcs'] and names[j] in u['by_reading']]
        assert len(js) == r['readings'] and abs(r['mean_abs'] - np.abs(C[:, js].sum(1)).mean()) < 1e-9
    with pytest.raises(SystemExit):
        hl.contributions(b, hl.as_float(X))


# --------------------------------------------------------------------------------------------- features and paths
def test_feature_sets_and_names(tmp_path, monkeypatch):
    """TA holds the engine readings and their ZS states, ALL every reading; ordinal / categorical by kind; the value
    offset centres an ordinal reading on its neutral level; a ZS code equals heat.read_state of heat_xdata.zs_readings;
    the TA function names."""
    ctx = _noise_ctx(tmp_path, monkeypatch)
    ta, al = hl.feature_set(ctx, 'TA'), hl.feature_set(ctx, 'ALL')
    assert 'FLOW:Stretch30' not in ta['names'] and 'POS:QPos' not in ta['names'] and 'ZS:FLOW:Stretch30' not in ta['names']
    assert {'FLOW:Stretch30', 'POS:QPos', 'ZS:FLOW:Stretch30', 'ZS:1m:R3', '15m:R5 sign'} <= set(al['names'])
    assert set(ta['names']) < set(al['names'])
    cat = {al['names'][i] for i in al['cat_idx']}
    assert 'POS:QPos' in cat and 'ZS:1m:R3' in cat and '1m:R3' not in cat and '1m:R5 sign' not in cat
    F = {x['name']: x for x in al['feats']}
    assert F['1m:R3']['offset'] == 2 and F['1m:R5 sign']['offset'] == 0 and F['POS:QPos']['offset'] == 0
    assert hl.value_offset(xd.BREADTH_LV) == 3 and hl.value_offset(heat.DOM_LV) == 2
    assert hl.is_ordinal({'name': 'X:Breadth5', 'levels': xd.BREADTH_LV}) and hl.is_ordinal({'name': 'DMKT:SPX1d', 'levels': heat.DOM_LV})
    rows = np.r_[np.arange(0, 3000), hl.contrib_rows(ctx, 2000)]
    zs = {R['name']: R for R in xd.zs_readings(ctx.readings)}
    for nm in ('ZS:1m:R3', 'ZS:15m:R10', 'ZS:FLOW:Stretch30'):
        assert np.array_equal(hl.feature_codes(F[nm], rows), heat.read_state(zs[nm], rows))
    X = hl.features(ctx, 'ALL', rows)
    j = al['names'].index('1m:R10')
    assert np.array_equal(X[:, j], heat.read_state(F['1m:R10']['R'], rows))
    v = hl.as_float(X, al['offset'])
    assert np.all(np.isnan(v[X < 0])) and np.allclose(v[:, j][X[:, j] >= 0], X[:, j][X[:, j] >= 0] - 2)
    cases = {'15m:RSI14': ('RSI', '14', '15m'), '1m:PERCENTB20/2.5': ('PERCENTB', '20/2.5', '1m'), '5m:STOCH14 K>D': ('STOCH K>D', '14', '5m'),
             '1m:C-T3_5': ('C-T3', '5', '1m'), '60m:CDL:3BLACKCROWS': ('CDL:3BLACKCROWS', '', '60m'), '1m:SWAK_2PHP20': ('SWAK_2PHP', '20', '1m'),
             '1m:ACCBANDS20pos': ('ACCBANDSpos', '20', '1m'), '1m:MACDh12/26/9': ('MACDh', '12/26/9', '1m'), '15m:RSI14 sign': ('RSI', '14', '15m'),
             '1m:EMA50>EMA200': ('EMA>EMA', '50/200', '1m'), '1m:C-EMA200': ('C-EMA', '200', '1m')}
    for nm, want in cases.items():
        assert hl.ta_parts(nm) == want, nm
    for nm in ('X.BTC:RSI14', 'ZS:15m:RSI14', 'BTC.D 1d', 'UTC4h', 'POS:QPos', 'GBM.TA15'):
        assert hl.ta_parts(nm) is None
    assert hl.is_ta({'name': 'X.BTC:R5z', 'family': 'cross', 'aliases': ['15m:RSI14']})
    assert not hl.is_ta({'name': 'UTC1h', 'family': 'clock'}) and hl.is_ta({'name': 'UTC4h', 'ctx': True})


def _node(f, thr, dt='<=', dl=False, mt='NaN', left=None, right=None):
    return {'split_feature': f, 'threshold': thr, 'decision_type': dt, 'default_left': dl, 'missing_type': mt, 'left_child': left, 'right_child': right}


def _leaf(v, c=100):
    return {'leaf_value': v, 'leaf_count': c}


def test_leaf_paths_follow_lightgbm_rules():
    """Hand-made trees: a numerical split (values = level - offset) with NaN routed by default_left, one with missing
    type None (unknown = value 0 = the neutral level), one with type Zero (the neutral level takes the default side),
    a categorical split (unknown goes right), predicates on one feature merged into a level set, a ZS condition mapped
    onto its zone reading (a set holding 'none' dropped from the scan form), identical rules merged; tree_eval agrees
    with the paths' level sets."""
    feats = [{'name': 'A', 'levels': heat.ZONES, 'offset': 2, 'zs_of': None}, {'name': 'P', 'levels': ['m0', 'm1', 'm2', 'm3'], 'offset': 0, 'zs_of': None},
             {'name': 'ZS:A', 'levels': xd.ZS_LEVELS, 'offset': 0, 'zs_of': 'A'}, {'name': 'B', 'levels': ['x', 'y', 'z'], 'offset': 1, 'zs_of': None}]
    t0 = _node(0, 0.5, dl=True, left=_node(0, -1.5, mt='NaN', dl=True, left=_leaf(0.1), right=_leaf(0.2)),             # A <= mid, NA left
               right=_node(1, '1||3', dt='==', left=_leaf(0.3), right=_leaf(0.4)))
    t1 = _node(3, 1e-35, mt='None', left=_leaf(-0.1), right=_node(3, 1e-35, mt='Zero', dl=False, left=_leaf(0.5), right=_leaf(0.6)))
    t2 = _node(2, '1||2', dt='==', left=_node(0, 0.5, mt='NaN', dl=True, left=_leaf(0.7), right=_leaf(0.8)), right=_leaf(0.9))
    t3 = _node(2, '6', dt='==', left=_node(1, '0', dt='==', left=_leaf(0.01), right=_leaf(0.02)), right=_leaf(0.03))
    tj = {'feature_names': ['f0', 'f1', 'f2', 'f3'], 'tree_info': [{'tree_index': i, 'tree_structure': t} for i, t in enumerate((t0, t1, t2, t3))],
          'hm2': {'features': feats}}
    P = {json.dumps(r['conds_tree']): r for r in hl.leaf_paths(tj)}
    get = lambda conds: P[json.dumps(conds)]
    assert get([['A', ['very low', 'NA']]])['odds'] == pytest.approx(5.0)                # value -2 <= -1.5, NaN default left at both nodes
    assert get([['A', ['low', 'mid']]])['odds'] == pytest.approx(10.0)
    assert get([['A', ['high', 'very high'], ], ['P', ['m1', 'm3']]])['odds'] == pytest.approx(15.0)
    assert get([['A', ['high', 'very high']], ['P', ['m0', 'm2', 'NA']]])['odds'] == pytest.approx(20.0)
    assert get([['B', ['x', 'y', 'NA']]])['odds'] == pytest.approx(-5.0)                 # missing type None: unknown is value 0 = 'y'
    r = get([['B', ['z']]])                                                             # type Zero below: 'y' (value 0) took the default (right) side
    assert r['odds_sum'] == pytest.approx(50.0 * 0.6) and r['leaves'] == 1
    r = get([['A', ['very low', 'low', 'mid', 'NA']], ['ZS:A', ['very low', 'low (falling in)']]])
    assert r['conds'] == [['A', ['very low', 'low']]] and not r['exact']                   # ZS mapped onto A's zones and intersected
    assert all(json.dumps(x['conds_tree']) != json.dumps([['ZS:A', ['none', 'low (recovering)', 'high (rising in)', 'high (cooling)', 'very high', 'NA']]])
               for x in hl.leaf_paths(tj))                                                 # holds 'none': no scan condition, no rule
    # a ZS event that contradicts its own zone's condition (A high or very high, yet A's last bar fell into very low or
    # low): no minute reaches that leaf, so it is no rule (an empty level set would scan an empty cell)
    assert all(lv for x in hl.leaf_paths(tj) for _, lv in x['conds'])
    assert json.dumps([['A', ['high', 'very high']], ['ZS:A', ['very low', 'low (falling in)']]]) not in P
    r = get([['P', ['m0']], ['ZS:A', ['very high']]])
    assert r['conds'] == [['A', ['very high']], ['P', ['m0']]] and r['n_readings'] == 2
    # tree_eval agrees with the level sets: a row in each path's set lands on that leaf. t1's leaf 0.5 is out of reach
    # (only 'z' gets past its None-type root, and 'z' is not zero at the Zero node); 'y' (value 0) and unknown go left
    codes = np.array([[0, 1, 0, 0], [-1, 1, 0, 2], [3, 3, 6, 1], [4, -1, 0, -1]], np.int8)
    want = np.array([0.1 + -0.1 + 0.9 + 0.03, 0.1 + 0.6 + 0.9 + 0.03, 0.3 + -0.1 + 0.9 + 0.02, 0.4 + -0.1 + 0.9 + 0.03])
    assert np.allclose(hl.tree_eval(tj, codes), want)
    # tree by tree: the leaf a row lands on (tree_eval) is the one rule whose tree-form level sets hold the row
    hits = 0
    for t in tj['tree_info']:
        one = dict(tj, tree_info=[t])
        v = hl.tree_eval(one, codes)
        rules = hl.leaf_paths(one)
        for i, row in enumerate(codes):
            lv = {F['name']: ('NA' if row[j] < 0 else F['levels'][row[j]]) for j, F in enumerate(feats)}
            got = [x for x in rules if all(lv[nm] in s for nm, s in x['conds_tree'])]
            assert len(got) <= 1 and all(x['odds'] == pytest.approx(50.0 * v[i]) for x in got), (t['tree_index'], i, got, v[i])
            hits += len(got)
    assert hits == 9                                                                     # t0 4, t1 4, t3 1 (t2 and the rest of t3 hold ZS none)
    m = hl.merge_paths([dict(x, model='TA', h=15) for x in hl.leaf_paths(tj)] + [dict(x, model='ALL', h=60) for x in hl.leaf_paths(tj)])
    assert len(m) == len(hl.leaf_paths(tj)) and all(len(x['sources']) == 2 for x in m)


# ----------------------------------------------------------------------------------------------- usage cards
def test_card_inputs():
    """The settings x timeframe grid (fade or follow by the A direction of the extreme zones, the strongest horizon on A
    and on B, an alias listed with its kept reading's numbers) and the best partner per (function, group, horizon) by
    iheat_B from the candidate pool."""
    L = 5
    odds = np.zeros((2, 6, L))
    t = np.zeros((2, 6, L))
    odds[0, :, 0], odds[0, :, 4] = 2.0, 1.5             # very low up (fade), very high up (follow)
    odds[1, :, 0], odds[1, :, 4] = [0.5, 1, 3, 1, 0.5, 0.2], [-0.5, 0, 1, 2, 0, 0]
    t[0, :, 0], t[0, :, 4] = [1, 2, 3, 6, 2, 1], [1, 1, 1, 1, 1, 1]
    zr = lambda nm, **k: dict({'name': nm, 'k': 15, 'levels': heat.ZONES, 'zones': True}, **k)
    readings = [zr('15m:RSI14', aliases=['15m:CMO14']), zr('1m:RSI7'), zr('FLOW:TB5', family='flow'), {'name': 'POS:QPos', 'k': 1, 'levels': ['m00', 'm14'],
                                                                                                         'family': 'position'}]
    parts = {'odds': [odds, -odds, odds, np.zeros((2, 6, 2))], 't': [t, t, t, np.zeros((2, 6, 2))], 'n': [np.full((2, 6, L), 100.0)] * 3 + [np.ones((2, 6, 2))]}
    ctx = types.SimpleNamespace(readings=readings, parts=parts, fam=['osc', 'osc', 'flow', 'position'], label='X', twin=0)
    g = hl.card_grid(ctx)
    assert set(g) == {'RSI', 'CMO'} and [r['reading'] for r in g['RSI']] == ['1m:RSI7', '15m:RSI14'] and g['CMO'][0]['alias_of'] == '15m:RSI14'
    r = g['RSI'][1]
    assert r['setting'] == '14' and r['tf'] == '15m' and r['kind'] == 'zone'
    assert r['fade_follow']['very low'] == ['fade'] * 6 and r['fade_follow']['very high'] == ['follow'] * 6
    assert r['best_h_A'] == 30 and r['best_h_B'] == 15
    assert g['RSI'][0]['fade_follow']['very low'] == ['follow'] * 6                      # the 1m RSI7 runs the other way
    assert r['odds_B_dir'][0] == [0.5, 1, 3, 1, 0.5, 0.2]
    cands = pd.DataFrame([
        {'kind': 'pair', 'key': 'a', 'h': 15, 'ia': 0, 'la': 0, 'ib': 2, 'lb': 4, 'iheat_B': 3.0, 'dir': 1, 'iota_with_call': True, 'iota_robust_B': 1.0,
         'odds_B': 2.0, 'wd_B': 1.5, 'n_B': 80, 'seen_in_league': 'none'},
        {'kind': 'pair', 'key': 'b', 'h': 15, 'ia': 0, 'la': 4, 'ib': 2, 'lb': 0, 'iheat_B': 5.0, 'dir': -1, 'iota_with_call': False, 'iota_robust_B': -1.0,
         'odds_B': 1.0, 'wd_B': 2.5, 'n_B': 90, 'seen_in_league': 'none'},
        {'kind': 'pair', 'key': 'c', 'h': 15, 'ia': 1, 'la': 0, 'ib': 3, 'lb': 1, 'iheat_B': 1.0, 'dir': 1, 'iota_with_call': True, 'iota_robust_B': 1.0,
         'odds_B': 2.0, 'wd_B': 1.5, 'n_B': 80, 'seen_in_league': 'stored'},
        {'kind': 'triple', 'key': 'd', 'h': 15, 'ia': 0, 'la': 0, 'ib': 3, 'lb': 1, 'iheat_B': 9.0, 'dir': 1, 'iota_with_call': True, 'iota_robust_B': 1.0,
         'odds_B': 2.0, 'wd_B': 1.5, 'n_B': 80, 'seen_in_league': 'none'}])
    p = {(x['func'], x['group'], x['h']): x for x in hl.card_partners(ctx, cands)}
    assert set(p) == {('RSI', 'flow', 15), ('CMO', 'flow', 15), ('RSI', 'position and clock', 15)}
    x = p[('RSI', 'flow', 15)]
    assert x['key'] == 'b' and x['level'] == 'very high' and x['partner'] == 'FLOW:TB5' and x['partner_level'] == 'very low' and not x['iota_with_call']
    assert p[('RSI', 'position and clock', 15)]['reading'] == '1m:RSI7'
    ci = hl.card_inputs(ctx, cands)
    assert ci['schema'] == 'oracle-heat-hm2-cards-1' and json.dumps(ci, allow_nan=False)


# ------------------------------------------------------------------------------------------------ cut the future
def test_learner_features_and_call_are_causal(tmp_path, monkeypatch):
    """Cut the future (OR-HM2 Tests 1, the learner's part): with the trees fixed, the features of both models (the ZS
    states included) and the per-minute score at rows <= t are unchanged when every reading's bars that close after t
    are replaced by noise, at 5 cut points (two in A, three in 2025); for a cut in 2025 the GBM call's zone edges (A
    minutes only) and its codes at rows <= t are unchanged too. The noise does reach the rows after t."""
    ctx = _noise_ctx(tmp_path, monkeypatch)
    b, used, tj = hl.learn(ctx, 'ALL', 15)
    R0, e0 = hl.gbm_reading(ctx, b, 'ALL', 15)
    assert e0 is not None and used
    n, a_hi = ctx.m['n'], ctx.g.sp['A'].hi
    rng = np.random.default_rng(4)
    for t in (n // 7, a_hi // 2, a_hi + 1000, (a_hi + n) // 2, n - 500):
        R2 = []
        for R in ctx.readings:
            R = dict(R)
            close = np.arange(len(R['codes'])) * R['k'] + R['k'] - 1
            R['codes'] = np.where(close > t, rng.integers(-1, len(R['levels']), len(R['codes'])), R['codes']).astype(np.int8)
            R2.append(R)
        c2 = types.SimpleNamespace(**{k: v for k, v in ctx.__dict__.items() if not k.startswith('_hl')})
        c2.readings = R2
        rows, after = np.arange(max(0, t - 3000), t + 1), np.arange(t + 1, min(n, t + 3001))
        for model in hl.MODELS:
            assert np.array_equal(hl.features(ctx, model, rows), hl.features(c2, model, rows)), (t, model)
            assert not np.array_equal(hl.features(ctx, model, after), hl.features(c2, model, after)), (t, model)
        assert np.array_equal(hl.score_rows(ctx, 'ALL', tj, rows), hl.score_rows(c2, 'ALL', tj, rows), equal_nan=True), t
        if t >= a_hi:
            R2g, e2 = hl.gbm_reading(c2, b, 'ALL', 15)
            assert e2 == e0 and np.array_equal(R2g['codes'][:t + 1], R0['codes'][:t + 1]), t


# ----------------------------------------------------------------------------------- the kept share and the series
def test_card_kept_share_from_the_scan(tmp_path, monkeypatch):
    """The pair scan's per-reading tally (heat_hm2.SummaryCounts.rk): each pair cell with a sample counts once for each
    of its two readings, so the readings' sums are twice the 'all' stratum's counts (cells, iota and iota_robust kept,
    with the call); two halves of the pairs merge (through to_json / from_json) into exactly the one-job tally; and
    card_kept's numbers per TA function are the sums over the function's readings, its shares kept / n."""
    ctx = _noise_ctx(tmp_path, monkeypatch)

    def scan(part):
        summ = {'pair': hm.SummaryCounts(ctx.families), 'triple': hm.SummaryCounts(ctx.families)}
        hm.scan_pairs(ctx, 1, hm.ShardWriter('', False), summ, hm.Candidates(), part=part, log=None)
        return summ['pair']
    one = scan((0, 1))
    assert one.rk.shape[1] == len(ctx.readings) and one.rk.sum() > 0
    C = dict(zip(hm.SummaryCounts.COUNTS, np.moveaxis(one.c[:, 0], -1, 0)))
    R = dict(zip(hm.SummaryCounts.RK, np.moveaxis(one.rk.sum(1), -1, 0)))
    for k in hm.SummaryCounts.RK:
        assert np.array_equal(R[k], 2 * C[k]), k
    halves = hm.SummaryCounts.from_json(json.loads(json.dumps(scan((0, 2)).to_json(), allow_nan=False)))
    halves.merge(hm.SummaryCounts.from_json(json.loads(json.dumps(scan((1, 2)).to_json(), allow_nan=False))))
    assert np.array_equal(halves.rk, one.rk) and halves.to_json() == one.to_json()
    k = hl.card_kept(ctx, one.to_json())
    assert k == hl.card_kept(ctx, one)
    ci = {c: i for i, c in enumerate(hm.SummaryCounts.RK)}
    fns = {}
    for j, Rd in enumerate(ctx.readings):
        for fn in {f for f in map(hl.ta_function, [Rd['name']] + list(Rd.get('aliases', []))) if f}:
            fns.setdefault(fn, []).append(j)
    assert set(k['by_function']) == set(fns) and 'FLOW:Stretch30' not in k['by_reading'] and 'POS:QPos' not in k['by_reading']
    for fn, js in fns.items():
        tot = one.rk[:, js].sum(1)
        e = k['by_function'][fn]
        assert np.array_equal(np.array(e['counts']), tot) and e['readings'] == [ctx.names[j] for j in js]
        want = np.where(tot[:, ci['robust_n']] > 0, tot[:, ci['robust_kept']] / np.maximum(tot[:, ci['robust_n']], 1), np.nan)
        got = np.array([np.nan if x is None else x for x in e['share_robust_kept']], float)
        assert np.allclose(got, want, equal_nan=True)


def test_series_runs_the_learner(tmp_path, monkeypatch):
    """heat_hm2.run_series with the learner on (LEARN_H patched to [15]): both models' trees with the call's zone edges
    (tree_eval on the reading's features, bucketed at those edges, gives the GBM reading's codes), the merged leaf rules
    (each scan form once, so the triple scan measures every three-reading rule once), the GBM calls re-measured as
    singles and held states, usage.json with the 2025 contributions and the call, and cards.json.gz with the grid, the
    partners from the candidates and the kept share from the summary counts. A twin writes the same files."""
    monkeypatch.setattr(hm, 'LEARN_H', [15])
    for tw in (0, 1):
        ctx = _noise_ctx(tmp_path, monkeypatch, twin=tw)
        out = tmp_path / f's{tw}'
        mt = hm.run_series('X', 'x.csv', str(out), ctx=ctx, procs=1, log=lambda *a: None)
        assert set(mt['learner']['trees']) == {'TA_h15', 'ALL_h15'} and mt['twin'] == tw
        rows = np.arange(ctx.m['n'])
        for key, tr in mt['learner']['trees'].items():
            tj = json.load(open(out / tr['file']))
            z = tj['hm2']['zone']
            assert z['name'] == f'GBM.{tj["hm2"]["model"]}15' and z['edges'] == tr['edges'] and tj['hm2']['twin'] == tw
            assert tj['hm2']['params'] == hm._clean(dict(hm.LGB_PARAMS, seed=hm.LGB_SEED + 15)) and tj['hm2']['rounds'] <= hm.LGB_ROUNDS
            if z['edges'] is not None:
                sc = hl.score_rows(ctx, tj['hm2']['model'], tj, rows)
                ev = np.r_[np.arange(0, ctx.m['n'], 97), hl.contrib_rows(ctx, 2000)]
                X = hl.features(ctx, tj['hm2']['model'], ev)
                assert np.abs(hl.tree_eval(tj, X) - sc[ev])[np.isfinite(sc[ev])].max() < 1e-9
                Rz, ez = xd.zone(z['name'], sc, ctx.g.sp['A'].hi)              # the stored edges: A quantiles of the JSON's score
                assert ez == z['edges'] and ez == [float(q) for q in np.quantile(sc[:ctx.g.sp['A'].hi][np.isfinite(sc[:ctx.g.sp['A'].hi])],
                                                                                heat.ZONE_Q)]
        z = np.load(out / hl.GBM_CODES_FILE)
        assert set(z.files) == {'t0', 'n', 'GBM.TA15', 'GBM.ALL15'} and int(z['n']) == ctx.m['n'] and z['GBM.ALL15'].dtype == np.int8
        for key, tr in mt['learner']['trees'].items():
            tj = json.load(open(out / tr['file']))
            if tr['edges'] is not None:
                sc = hl.score_rows(ctx, tj['hm2']['model'], tj, rows)
                assert np.array_equal(z[tj['hm2']['zone']['name']], np.where(np.isfinite(sc), heat.bucket(sc, tr['edges']), -1))
        with gzip.open(out / 'learner_paths.json.gz', 'rt') as f:
            paths = json.load(f)
        assert mt['learner']['paths'] == len(paths) and len({json.dumps(p['conds']) for p in paths}) == len(paths)
        three = [p for p in paths if len({r for r, _ in p['conds']}) == 3]
        assert mt['triples']['paths'] == len(three)
        u = json.load(open(out / 'usage.json'))
        assert set(u) == {'TA15', 'ALL15'} and all(v['split'] == 'B' and v['call']['h'] == 15 for v in u.values())
        h = pd.read_csv(out / 'heat.csv.gz', low_memory=False)
        g = h[h.source == 'model']
        assert set(g.kind) == {'single', 'xstate'} and g.key.str.startswith('GBM.').all() and {'A', 'B'} <= set(g.split)
        assert {k.split('=')[0] for k in g.key} == {'GBM.TA15', 'GBM.ALL15'}
        with gzip.open(out / hl.CARDS_FILE, 'rt') as f:
            cards = json.load(f)
        assert cards['schema'] == 'oracle-heat-hm2-cards-1' and cards['twin'] == tw and {'grid', 'partners', 'kept'} <= set(cards)
        assert set(cards['grid']) == {'R'} and {(r['tf'], r['setting'], r['kind']) for r in cards['grid']['R']} == {
            (tf, st, kd) for tf in ('1m', '15m') for st, kd in (('3', 'zone'), ('10', 'zone'), ('5', 'sign'))}
        assert set(cards['kept']['by_function']) == {'R'}
        sj = json.load(open(out / 'summary_counts.json'))
        assert cards['kept'] == hl.card_kept(ctx, sj['pair'])


def test_part_split_learner_path(tmp_path, monkeypatch):
    """With --part i/S the learner runs once, in the finish job, after the parts scanned their pairs: the merged pair
    candidates get the same learner_path as the one-job run (the re-measure is stubbed: the scan's own test covers it)."""
    monkeypatch.setattr(hm, 'LEARN_H', [15])
    monkeypatch.setattr(hm, 'remeasure', lambda *a, **k: (heat.Rows(), pd.DataFrame(columns=['kind', 'h', 'measure', 'key1', 'key2', 'jaccard'])))
    ctx = _noise_ctx(tmp_path, monkeypatch)
    q = lambda *a: None
    hm.run_series('X', 'x.csv', str(tmp_path / 'one'), ctx=ctx, procs=1, log=q)
    for i in (0, 1):
        hm.run_series('X', 'x.csv', str(tmp_path / f'p{i}'), ctx=ctx, procs=1, part=(i, 2), log=q)
    hm.run_series('X', 'x.csv', str(tmp_path / 'fin'), ctx=ctx, procs=1, parts_dirs=[str(tmp_path / 'p0'), str(tmp_path / 'p1')], log=q)
    c1 = pd.read_csv(tmp_path / 'one' / 'candidates.csv.gz', low_memory=False)
    c0 = pd.read_csv(tmp_path / 'p0' / 'candidates.csv.gz', low_memory=False)
    c2 = pd.read_csv(tmp_path / 'fin' / 'candidates.csv.gz', low_memory=False)
    pr = lambda c: c[c.kind == 'pair'].sort_values(['h', 'measure', 'key']).reset_index(drop=True)
    assert pr(c1).learner_path.any() and not pr(c0).learner_path.any()
    assert pr(c1)[['h', 'measure', 'key', 'learner_path']].equals(pr(c2)[['h', 'measure', 'key', 'learner_path']])
    with gzip.open(tmp_path / 'one' / hl.CARDS_FILE, 'rt') as f1, gzip.open(tmp_path / 'fin' / hl.CARDS_FILE, 'rt') as f2:
        assert json.load(f1)['kept'] == json.load(f2)['kept']
