"""OR-HM2 Part 4: structural chart patterns (python/oracle/heat_patterns.py; design prereg/OR-HM2-part4.md, build plan
section 3). Synthetic minutes and bar paths only; SPLITS patched where labels or splits are read; procs 1.

  no repaint       cut the series, replace the future with noise (and once with a forward-filled gap): every code of
                   every chart reading at bars closed by the cut, the pivots confirmed by the cut, the provisional extreme
                   and every instance event known by the cut are unchanged; a whole-series kernel and pivots dated at
                   their extreme bar FAIL the same check (the negative controls)
  planted          HS, inverse HS, double top and a symmetrical triangle through planted pivots: found with the planted
                   pivots (+- 1 bar), neckline / lines and height, the break at the first close across the planted trigger
  noise            a random-walk coin and its coin-flip twin form patterns at the same rate; tbi is near the mean p_rw
  parity           the window reader (last 3,000 bars) gives the full run's codes at the window's last bar
  format, kernel, stage, CLI
"""
import gzip
import hashlib
import json
import os

import numpy as np
import pandas as pd
import pytest

from oracle import heat
from oracle import heat_patterns as hp
from oracle.common import DAY, MIN, ms

START = ms('2024-03-01')


# ------------------------------------------------------------------------------------------------------------ helpers
def _minutes(days, seed=0, start=START, grid=0.01, scale=4e-4):
    """A random walk of 1-minute bars on a price grid, with volatility clustering and a daily cycle (heat.load_minutes'
    dict)."""
    rng = np.random.default_rng(seed)
    n = days * 1440
    tod = 1.0 + 0.5 * np.sin(2 * np.pi * (np.arange(n) % 1440) / 1440.0)
    vol = np.exp(0.6 * np.convolve(rng.normal(0, 1, n), np.ones(720) / np.sqrt(720), 'same'))
    r = rng.standard_t(4, n) * scale * tod * vol
    return _from_returns(r, rng, start, grid)


def _reverting(days, seed, half_life=15.0):
    """Minutes whose log price is pulled back toward its level with a 15-minute half-life (an Ornstein-Uhlenbeck
    path): planted mean reversion at 15 minutes."""
    rng = np.random.default_rng(seed)
    r = rng.standard_t(4, days * 1440) * 4e-4
    th = np.log(2.0) / half_life
    lp = np.empty(len(r))
    x = 0.0
    for t in range(len(r)):
        x += r[t] - th * x
        lp[t] = x
    return _from_returns(np.diff(np.r_[0.0, lp]), rng, START, 0.01)


def _from_returns(r, rng, start, grid, c0=100.0):
    n = len(r)
    c = np.round(c0 * np.exp(np.cumsum(r)) / grid) * grid
    o = np.r_[np.round(c0 / grid) * grid, c[:-1]]
    w = np.abs(rng.normal(0, 2e-4, n))
    h = np.round(np.maximum(o, c) * (1 + w) / grid) * grid
    l = np.round(np.minimum(o, c) * (1 - w) / grid) * grid
    v = rng.uniform(1, 2, n)
    gap = np.zeros(n, bool)
    return {'t0': int(start), 'n': n, 'o': o, 'h': np.maximum(h, np.maximum(o, c)), 'l': np.minimum(l, np.minimum(o, c)), 'c': c, 'v': v,
            'tb': None, 'gap': gap, 'tick': heat.tick_bps(c, gap), 'bad_rows': 0}


def _future_noise(m, cut, seed, gap=0):
    """m with every minute from `cut` on replaced by a new random walk from the close at cut - 1 (same grid); gap > 0:
    first a forward-filled outage of that many minutes."""
    rng = np.random.default_rng([99, seed])
    out = {k: (v.copy() if isinstance(v, np.ndarray) else v) for k, v in m.items()}
    n = m['n']
    c_prev = m['c'][cut - 1]
    g = min(gap, n - cut)
    if g:
        for x in ('o', 'h', 'l', 'c'):
            out[x][cut:cut + g] = c_prev
        out['v'][cut:cut + g] = 0.0
        out['gap'][cut:cut + g] = True
    k = n - cut - g
    if k > 0:
        f = _from_returns(rng.standard_t(4, k) * 6e-4, rng, m['t0'], 0.01, c0=c_prev)
        for x in ('o', 'h', 'l', 'c', 'v'):
            out[x][cut + g:] = f[x]
        out['o'][cut + g] = c_prev
        out['h'][cut + g] = max(out['h'][cut + g], c_prev)
        out['l'][cut + g] = min(out['l'][cut + g], c_prev)
    out['tick'] = heat.tick_bps(out['c'], out['gap'])
    return out


def _run(m, tfs, a_hi, edges=None):
    """run_tf for each timeframe on the engine's tick units; readings with the given parameter edges (computed from
    these runs when None). Returns (runs, readings by name, edges, step)."""
    mu = hp.units(m, a_hi)
    runs = {k: hp.run_tf(mu, k) for k in tfs}
    if edges is None:
        tabs = {f'{k}m:{fr}': x['tab'] for k in tfs for fr, x in runs[k]['frames'].items()}
        fbs = {f'{k}m': runs[k]['fb'] for k in tfs}
        edges, _ = hp.param_edges(tabs, fbs, (0, a_hi))
    R = {}
    for k in tfs:
        rr, _ = hp.tf_readings(runs[k], edges)
        R.update({x['name']: x for x in rr})
    return runs, R, edges, mu.get('step')


def _events_known(T: pd.DataFrame, cut_bar: int) -> set:
    """Every event of every (passing) instance that is known at the close of bar cut_bar - 1."""
    out = set()
    for r in T[T['near'] == 0].itertuples(index=False):
        if r.start >= cut_bar:
            continue
        key = (r.pattern, int(r.orient), int(r.tid), int(r.j0), int(r.start))
        out.add(key + ('start',))
        for col in ('formed', 'brk', 'retest', 'fail', 'tgt_bar', 'half_bar'):
            b = int(getattr(r, col))
            if 0 <= b < cut_bar:
                out.add(key + (col, b, int(r.dir) if col == 'brk' else 0))
        if 0 <= r.end < cut_bar:
            out.add(key + ('end', int(r.end), int(r.why)))
    return out


# ---------------------------------------------------------------------------------------------------- no repainting
NR_DAYS, NR_TFS = 24, [5, 15, 60]


@pytest.fixture(scope='module')
def nr_base():
    m = _minutes(NR_DAYS, seed=3)
    a_hi = m['n'] * 2 // 3
    runs, R, edges, step = _run(m, NR_TFS, a_hi)
    return m, a_hi, runs, R, edges, step


def _check_no_repaint(base, m2, cut):
    m, a_hi, runs, R, edges, step = base
    runs2, R2, _, step2 = _run(m2, NR_TFS, a_hi, edges)
    assert step2 == step
    bad = []
    for name, x in R.items():
        b = cut // x['k']
        if not np.array_equal(x['codes'][:b], R2[name]['codes'][:b]):
            j = int(np.flatnonzero(x['codes'][:b] != R2[name]['codes'][:b])[0])
            bad.append((name, j, b))
    assert not bad, f'{len(bad)} readings repaint before the cut, e.g. {bad[:5]}'
    for k in NR_TFS:
        cb = cut // k
        for fr, x in runs[k]['frames'].items():
            y = runs2[k]['frames'][fr]
            if 'zz' in x:
                z, z2 = x['zz'], y['zz']
                kz, kz2 = z['pc'] < cb, z2['pc'] < cb
                assert kz.sum() == kz2.sum(), f'{k}m {fr}: pivots confirmed by the cut differ'
                for c in ('pb', 'pp', 'pt', 'pc'):
                    assert np.array_equal(z[c][kz], z2[c][kz2]), f'{k}m {fr}: pivot {c}'
                for c in ('d', 'xb', 'xp', 'npb'):
                    assert np.array_equal(z[c][:cb], z2[c][:cb], equal_nan=True), f'{k}m {fr}: provisional {c}'
            e1, e2 = _events_known(x['tab'], cb), _events_known(y['tab'], cb)
            assert e1 == e2, f'{k}m {fr}: instance events known by the cut differ ({len(e1 ^ e2)}: {sorted(e1 ^ e2)[:3]})'


@pytest.mark.parametrize('cut_day,seed,gap', [(13.3, 1, 0), (13.3, 2, 0), (17.71, 3, 0), (17.71, 4, 0), (21.05, 5, 0), (21.05, 6, 0),
                                              (19.5, 11, 400)])
def test_no_repaint(nr_base, cut_day, seed, gap):
    """Three cuts x two noise draws, and once a forward-filled outage right after the cut (not on any bar's edge)."""
    m = nr_base[0]
    cut = int(cut_day * 1440) + (3 if gap else 7)
    _check_no_repaint(nr_base, _future_noise(m, cut, seed, gap=gap), cut)


def _whole_series_kernel(c):
    """A non-causal reading (the negative control): one Gaussian Nadaraya-Watson smoother fitted to the whole series,
    its bandwidth chosen by leave-one-out CV over every bar (LMW's procedure applied once, not per window); code 1 where
    the smooth rises, 0 where it falls (LMW's extrema are the sign changes of this slope)."""
    c = np.asarray(c, float) - float(np.mean(c))
    best = None
    for h in (3.0, 5.0, 8.0, 13.0):                       # (LMW's grid of bar bandwidths, coarser)
        d = np.arange(-int(4 * h), int(4 * h) + 1, dtype=float)
        w = np.exp(-0.5 * (d / h) ** 2)
        num = np.convolve(c, w, 'same')
        den = np.convolve(np.ones_like(c), w, 'same')
        loo = (num - c) / (den - 1.0)
        cv = float(((c - loo) ** 2).sum())
        if best is None or cv < best[0]:
            best = (cv, num / den)
    return np.r_[0, (np.diff(best[1]) > 0).astype(np.int8)].astype(np.int8)


NR_CASES = [(13.3, 1, 0), (13.3, 2, 0), (17.71, 3, 0), (17.71, 4, 0), (21.05, 5, 0), (21.05, 6, 0), (19.5, 11, 400)]


def test_negative_controls_fail(nr_base):
    """The same perturbations catch repainting: a whole-series kernel and pivots dated at their extreme bar each change
    a code at a bar closed before the cut (in at least one of the no-repaint test's cases, on any timeframe and swing
    size, which is how the no-repaint test would fail), while the zigzag's own rule (a pivot at its confirmation bar)
    never does."""
    m, a_hi = nr_base[0], nr_base[1]
    mu = hp.units(m, a_hi)
    fails_kernel = fails_pivot = 0
    for cut_day, seed, gap in NR_CASES:
        cut = int(cut_day * 1440) + (3 if gap else 7)
        mu2 = hp.units(_future_noise(m, cut, seed, gap=gap), a_hi)
        for k in NR_TFS:
            cb = cut // k
            fb, fb2 = hp.frame_bars(mu, k), hp.frame_bars(mu2, k)
            k1, k2 = _whole_series_kernel(fb['c']), _whole_series_kernel(fb2['c'])
            fails_kernel += int(not np.array_equal(k1[:cb], k2[:cb]))
            for r in hp.Z_R:
                z1, z2 = hp.zigzag(fb, r), hp.zigzag(fb2, r)
                p1, p2 = np.zeros(fb['nb'], np.int8), np.zeros(fb2['nb'], np.int8)
                p1[z1['pb']] = z1['pt']
                p2[z2['pb']] = z2['pt']
                fails_pivot += int(not np.array_equal(p1[:cb], p2[:cb]))
                q1, q2 = np.zeros(fb['nb'], np.int8), np.zeros(fb2['nb'], np.int8)
                q1[z1['pc']] = z1['pt']
                q2[z2['pc']] = z2['pt']
                assert np.array_equal(q1[:cb], q2[:cb]), f'{k}m z{r}: pivots at their confirmation bar repaint'
    assert fails_kernel >= 1, 'a whole-series kernel passed the no-repaint check: the test cannot see repainting'
    assert fails_pivot >= 1, 'pivots dated at their extreme bar passed the no-repaint check: the test cannot see repainting'


def test_intrabar_and_window_pivots():
    """A bar that makes a peak and confirms it by its own close never gets the next trough at its own low; the zigzag on
    a later window, once synchronised, has the full run's pivots."""
    n = 400
    c = 1000.0 + 0.05 * np.sin(np.arange(n))
    h, l = c + 0.5, c - 0.5
    c[300] = 1001.0                                      # bar 300: high 1010, close 1001 (peak confirmed on its own bar)
    h[300], l[300] = 1010.0, 1000.0
    c[301:] = 1001.0 - 0.05 * np.arange(1, n - 300)
    h[301:], l[301:] = c[301:] + 0.5, c[301:] - 0.5
    S = hp.atr_prior(h, l, c, np.zeros(n, bool))
    pb, pp, pt, pc, *_ = hp._zigzag(h, l, c, S, np.zeros(n, bool), 2.0)
    j = int(np.flatnonzero((pb == 300) & (pt == 1))[0])
    assert pc[j] == 300
    assert j + 1 >= len(pb) or pp[j + 1] != l[300] or pb[j + 1] != 300
    # window against full run on noise: same pivots after the window's zigzag has synchronised
    m = _minutes(20, seed=8)
    mu = hp.units(m, m['n'])
    full = hp.frame_bars(mu, 5)
    win = hp.frame_bars(mu, 5, 2000)
    zf, zw = hp.zigzag(full, 2), hp.zigzag(win, 2)
    assert np.array_equal(full['S'][2000:][200:], win['S'][200:])            # the fixed-order ATR sum: exact
    late = zw['pc'] + 2000 > 3500
    lf = zf['pc'] > 3500
    assert np.array_equal(zw['pb'][late] + 2000, zf['pb'][lf]) and np.array_equal(zw['pp'][late], zf['pp'][lf])


# --------------------------------------------------------------------------------------------------------- planted
def _bars_from_anchors(anchors, warm=300, seed=0, base=1000.0, noise=0.03, tail=60, wick=0.3):
    """15-minute bars along straight lines between (bar, close) anchors after `warm` quiet bars; highs and lows =
    the bar's open / close range plus a wick. Returns a frame_bars-like dict."""
    rng = np.random.default_rng(seed)
    xs = [0, warm] + [warm + b for b, _ in anchors]
    ys = [base, base] + [p for _, p in anchors]
    nb = xs[-1] + tail
    c = np.interp(np.arange(nb), xs, ys)
    c[xs[-1]:] = ys[-1] + (ys[-1] - ys[-2]) / max(xs[-1] - xs[-2], 1) * np.arange(nb - xs[-1])
    c = c + rng.normal(0, noise, nb)
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) + wick
    l = np.minimum(o, c) - wick
    stale = np.zeros(nb, bool)
    fb = {'k': 15, 's': 0, 'e': nb, 'nb': nb, 'o': o, 'h': h, 'l': l, 'c': c, 'v': np.ones(nb), 'stale': stale, 'step': None, 't0': START}
    fb['S'] = hp.atr_prior(h, l, c, stale)
    fb['row'] = np.arange(nb, dtype=np.int64) * 15 + 14
    return fb, [warm + b for b, _ in anchors]


def _mirror(fb):
    out = dict(fb)
    out['h'], out['l'], out['c'], out['o'] = 2000.0 - fb['l'], 2000.0 - fb['h'], 2000.0 - fb['c'], 2000.0 - fb['o']
    out['S'] = hp.atr_prior(out['h'], out['l'], out['c'], out['stale'])
    return out


def _find(tab, pattern, bars, tol=1):
    """The passing instance of `pattern` whose pivots are at the planted bars (+- tol)."""
    k = len(bars)
    for i, r in tab[(tab['pattern'] == pattern) & (tab['near'] == 0)].iterrows():
        got = [int(r[f'piv{u}_bar']) for u in range(1, k + 1)]
        if all(abs(a - b) <= tol for a, b in zip(got, bars)):
            return r
    return None


def _first_cross(c, line, start, below=True):
    for t in range(start, len(c)):
        if (c[t] < line(t)) if below else (c[t] > line(t)):
            return t
    return None


# (anchors: bar after the warm-up, close), the pattern, its pivot anchors (index into anchors), the trigger
PLANTED = {
    'HS': ([(20, 1010.0), (35, 1003.0), (55, 1018.0), (75, 1003.0), (90, 1010.0), (130, 990.0)], [0, 1, 2, 3, 4]),
    'DTOP': ([(20, 1010.0), (35, 1002.0), (50, 1010.0), (90, 990.0)], [0, 1, 2]),
    'SYMTRI': ([(20, 1012.0), (40, 1000.0), (60, 1009.0), (78, 1003.0), (94, 1006.5), (130, 990.0)], [0, 1, 2, 3, 4]),
}


@pytest.mark.parametrize('pattern', ['HS', 'IHS', 'DTOP', 'DBOT', 'SYMTRI'])
def test_planted(pattern):
    src = {'IHS': 'HS', 'DBOT': 'DTOP'}.get(pattern, pattern)
    anchors, piv = PLANTED[src]
    fb, abars = _bars_from_anchors(anchors, seed=len(pattern))
    mir = pattern in ('IHS', 'DBOT')
    if mir:
        fb = _mirror(fb)
    zz, st, bos, tab = hp.detect_zz(fb, 2)
    bars = [abars[i] for i in piv]
    r = _find(tab, pattern, bars)
    assert r is not None, f'{pattern} not found at {bars}: {tab[tab["pattern"] == pattern][["piv1_bar", "piv2_bar", "piv3_bar", "piv4_bar", "piv5_bar"]].head()}'
    # the planted pivots' prices are the bars' extremes there (top orientation: peaks at highs; mirrored: negated)
    sg = -1.0 if mir else 1.0
    for u, b in enumerate(bars):
        b_got = int(r[f'piv{u + 1}_bar'])
        want = (fb['h'] if (u % 2 == 0) != mir else fb['l'])[b_got]
        assert r[f'piv{u + 1}_px'] == pytest.approx(want), f'pivot {u + 1}'
    q = [sg * r[f'piv{u + 1}_px'] for u in range(len(bars))]          # pivot prices in the top orientation
    bb = [int(r[f'piv{u + 1}_bar']) for u in range(len(bars))]
    cq = sg * fb['c']
    if src == 'HS':
        s = (q[3] - q[1]) / (bb[3] - bb[1])
        if s > 0:
            line, ts = (lambda t: q[1] + s * (t - bb[1])), s
        else:
            line, ts = (lambda t: q[3]), 0.0                           # a falling neckline: the trigger is the second trough
        assert r['hgt_B'] == pytest.approx(q[2] - (q[1] + s * (bb[2] - bb[1])), rel=1e-9)
        assert sg * r['trig_slope'] == pytest.approx(ts, rel=0.02, abs=1e-12)
    elif src == 'DTOP':
        line = lambda t: q[1]
        assert r['hgt_B'] == pytest.approx(0.5 * (q[0] + q[2]) - q[1], rel=1e-9)
    else:
        sl = (q[3] - q[1]) / (bb[3] - bb[1])
        line = lambda t: q[1] + sl * (t - bb[1])
        x = np.array([bb[0], bb[2], bb[4]], float)
        y = np.array([q[0], q[2], q[4]])
        fit = np.polyfit(x, y, 1)
        assert sg * r['trig_slope'] == pytest.approx(sl, rel=0.02)
        if np.isfinite(r['ups']):
            assert sg * r['ups'] == pytest.approx(fit[0], rel=0.02)
        assert r['hdn'] == pytest.approx(np.polyval(fit, bb[0]) - line(bb[0]), rel=1e-6)
    # the break: the first close across the planted trigger at or after the forming start (the textbook side)
    want = _first_cross(cq, line, int(r['start']), below=True)
    assert int(r['brk']) == want, f'{pattern}: break at {r["brk"]}, the first close across the trigger is {want}'
    assert int(r['dir']) == (1 if mir else -1)
    assert r['formed'] < 0 or r['formed'] < r['brk']                   # formed never after a break
    # the engine reading shows it at that bar
    R, info = hp.frame_readings(fb, tab, 'z2', None, st, bos)
    ev = {x['name']: x for x in R}[f'15m:CHART.z2.{pattern}']
    assert ev['levels'][ev['codes'][want]] == ('break up' if mir else 'break down')


def test_planted_provisional_break_and_near_miss():
    """An HS with a rising neckline that sits closer than r ATR below S2's top breaks before S2 is confirmed (no
    'formed' first, the invalidation is S2's admissible bound); a double top whose second peak misses the peak
    tolerance by a hair (too low: it never passes while forming) is a near miss with that check named, in no reading."""
    anchors = [(20, 1010.0), (35, 1000.0), (55, 1018.0), (75, 1003.0), (90, 1007.5), (130, 990.0)]
    fb, ab = _bars_from_anchors(anchors, seed=4, noise=0.0)
    zz, st, bos, tab = hp.detect_zz(fb, 4)
    r = _find(tab, 'HS', ab[:5], tol=1)
    assert r is not None
    assert r['brk'] >= 0 and r['dir'] == -1 and r['formed'] < 0 and r['lastc'] < 0
    conf = zz['pc'][(zz['pb'] == r['piv5_bar']) & (zz['pt'] > 0)]
    assert not len(conf) or conf[0] > r['brk']
    assert np.isfinite(r['up_tb']) and r['up_tb'] >= r['piv5_px']
    # near miss: the second top too low by a hair (0.21 d below the first)
    p0, v = 1010.0, 1002.0
    dl = 0.21 * (0.5 * (2 * p0 + 0.6) - (v - 0.3)) / (1 + 0.21 / 2)
    fb, ab = _bars_from_anchors([(20, p0), (35, v), (50, p0 - dl), (90, 990.0)], seed=5, noise=0.0)
    zz, st, bos, tab = hp.detect_zz(fb, 2)
    nm = tab[(tab['pattern'] == 'DTOP') & (tab['near'] == 1) & (tab['piv3_bar'] == ab[2])]
    assert len(nm) == 1 and nm['check'].iat[0] == 'peak_diff' and 0 < nm['margin'].iat[0] < 0.05
    assert not len(tab[(tab['pattern'] == 'DTOP') & (tab['near'] == 0) & (tab['piv3_bar'] == ab[2])])
    R, info = hp.frame_readings(fb, tab, 'z2', None, st, bos)
    ev = {x['name']: x for x in R}['15m:CHART.z2.DTOP']
    assert ev['codes'][nm['formed'].iat[0]] == 0


def test_structure_and_bos():
    """Higher highs and higher lows give STRUCT up; the first close above the last confirmed peak is a BOS up, below
    the last trough while up a CHoCH down; each pivot is broken once."""
    anchors = [(20, 1010.0), (35, 1004.0), (55, 1016.0), (70, 1009.0), (90, 1022.0), (110, 1015.0), (130, 1026.0), (170, 1000.0)]
    fb, ab = _bars_from_anchors(anchors, seed=2, noise=0.0)
    zz = hp.zigzag(fb, 2)
    st, bos = hp.structure(fb, zz)
    assert (st[ab[5]:ab[6]] == 0).all()                                   # up
    assert (bos == 1).sum() >= 1 and (bos == 4).sum() >= 1
    last_tr = zz['pp'][(zz['pt'] < 0) & (zz['pc'] < ab[7])][-1]
    t = int(np.flatnonzero(bos == 4)[0])
    assert fb['c'][t] < last_tr and (fb['c'][ab[6]:t] >= last_tr).all()


# ---------------------------------------------------------------------------------------------------------- noise
@pytest.fixture
def splits(monkeypatch):
    def set_(t0, days, a_days):
        monkeypatch.setattr(heat, 'SPLITS', {'A': (t0, t0 + a_days * DAY), 'B': (t0 + a_days * DAY, t0 + days * DAY)})
        monkeypatch.setattr(heat, 'HEAT_END', t0 + days * DAY)
    return set_


def _counts(m, tfs):
    mu = hp.units(m, m['n'])
    out, fbs, tabs = {}, {}, {}
    for k in tfs:
        run = hp.run_tf(mu, k, want={'z2', 'z4'})
        fbs[k] = run['fb']
        for fr, x in run['frames'].items():
            T = x['tab']
            tabs[f'{k}m:{fr}'] = T
            for p, g in T[T['near'] == 0].groupby('pattern'):
                out[(f'{k}m:{fr}', p)] = len(g)
    return out, fbs, tabs, mu


def test_noise_frequencies_like_twin(splits):
    days = 300
    m = _minutes(days, seed=21)
    splits(m['t0'], days, 200)
    tw = heat.make_twin(m, 1)
    c1, fb1, tab1, mu1 = _counts(m, [5, 15])
    c2, fb2, tab2, mu2 = _counts(tw, [5, 15])
    tested = 0
    for key in sorted(set(c1) | set(c2)):
        a, b = c1.get(key, 0), c2.get(key, 0)
        if min(a, b) >= 200:
            tested += 1
            assert 0.8 <= a / b <= 1.25, f'{key}: coin {a} against twin {b}'
    assert tested >= 20
    # tbi (minute closes, both barriers) against the mean p_rw on decided breaks: pooled within 2 points, and within 4
    # points per frame with at least 1,000 (overlapping instances share their path, so a frame's breaks are not
    # independent: on a pure random walk a frame of about 300 breaks scatters by +- 6 points)
    mu = {'c': mu1['c'], 'h': mu1['h'], 'l': mu1['l'], 'n': mu1['n'], 't0': mu1['t0'], 'step': mu1.get('step')}
    n_frames, allb = 0, []
    for key, T in tab1.items():
        cat = hp.catalogue_frame(key, T, fb1[int(key.split('m')[0])], mu)
        b = cat[cat['event'].isin(['break up', 'break down']) & cat['tbi'].notna()]
        allb.append(b)
        if len(b) >= 1000:
            n_frames += 1
            assert abs(b['tbi'].mean() - b['p_rw'].mean()) <= 0.04, f'{key}: tbi {b["tbi"].mean():.3f}, mean p_rw {b["p_rw"].mean():.3f}'
    b = pd.concat(allb)
    assert len(b) >= 5000 and abs(b['tbi'].mean() - b['p_rw'].mean()) <= 0.02
    assert n_frames >= 2


def test_mean_reversion_positive_control(splits):
    """A coin with planted mean reversion at 15 minutes forms more double tops, double bottoms and rectangles at 15m z2
    than its twin."""
    days = 40
    m = _reverting(days, seed=31)
    splits(m['t0'], days, 30)
    tw = heat.make_twin(m, 1)
    c1, *_ = _counts(m, [15])
    c2, *_ = _counts(tw, [15])
    pats = ['DTOP', 'DBOT', 'RECT']
    a = sum(c1.get(('15m:z2', p), 0) for p in pats)
    b = sum(c2.get(('15m:z2', p), 0) for p in pats)
    assert a > 1.2 * b, f'mean-reverting coin {a} against twin {b}'


# ---------------------------------------------------------------------------------------------------------- parity
def test_window_parity():
    """levels_at's detectors on the last 3,000 bars of each timeframe give the full run's codes at the window's last
    bar, at sampled bar closes of the last days of a long history (every reading, every timeframe)."""
    days = 520
    m = _minutes(days, seed=41, scale=3e-4)
    mu = hp.units(m, m['n'] // 2)
    step = mu.get('step')
    rng = np.random.default_rng(5)
    agree, total, known, worst = 0, 0, 0, {}
    for k, n_samp in ((5, 6), (15, 6), (60, 6), (240, 6)):
        run = hp.run_tf(mu, k)
        tabs = {f'{k}m:{fr}': x['tab'] for fr, x in run['frames'].items()}
        edges, _ = hp.param_edges(tabs, {f'{k}m': run['fb']}, (0, m['n'] // 2))
        full, _ = hp.tf_readings(run, edges)
        nb = run['fb']['nb']
        ends = np.sort(rng.choice(np.arange(max(nb - 30 * 1440 // k, hp.LIVE_WINDOW - 1), nb), n_samp, replace=False))
        for e in ends:
            cut = {x: (v[:(e + 1) * k] if isinstance(v, np.ndarray) else v) for x, v in m.items()}
            cut['n'] = (e + 1) * k
            W = hp.window_readings(cut, step, edges, hp.LIVE_WINDOW, tfs=[k])[k]
            assert W['nb'] == e + 1 and W['s'] == e + 1 - hp.LIVE_WINDOW
            wr = {x['name']: x for x in W['readings']}
            for R in full:
                ok = int(R['codes'][e] == wr[R['name']]['codes'][-1])
                agree += ok
                total += 1
                known += int(R['codes'][e] >= 0)
                if not ok:
                    worst[R['name']] = worst.get(R['name'], 0) + 1
    assert known > 0.5 * total                                              # the codes compared are mostly not NA
    assert agree / total >= 0.995, f'window parity {agree / total:.4f}; misses {sorted(worst.items(), key=lambda x: -x[1])[:8]}'


def test_levels_at_from_minute_rows():
    """levels_at on a DataFrame of minute rows (heat_live.grid) returns a level or None per reading at the last closed
    bar of each timeframe."""
    m = _minutes(14, seed=2)
    df = pd.DataFrame({'ts': m['t0'] + np.arange(m['n']) * MIN, 'o': m['o'], 'h': m['h'], 'l': m['l'], 'c': m['c'], 'v': m['v']})
    meta = {'price_step': 0.01, 'edges': {}}
    out = hp.levels_at(df, meta, names=['5m:CHART.z2.HS', '15m:CHART.z4.STRUCT', '15m:CHART.K.ANY'])
    assert set(out) == {'5m:CHART.z2.HS', '15m:CHART.z4.STRUCT', '15m:CHART.K.ANY'}
    assert all(v is None or isinstance(v, str) for v in out.values())


# ---------------------------------------------------------------------------------------------- format and kernel
def test_engine_format_and_compact(splits):
    days = 30
    m = _minutes(days, seed=6)
    splits(m['t0'], days, 20)
    R, edges, inst, meta = hp.pattern_readings(m, log=lambda *a: None, tfs=[15, 60])
    names = [x['name'] for x in R]
    assert len(names) == len(set(names))
    for x in R:
        assert set(x) >= {'name', 'k', 'codes', 'levels', 'base', 'family', 'every', 'cond'} and x['family'] == 'chart'
        assert x['every'] != x['cond'] and x['codes'].dtype == np.int8
        assert all(s not in x['name'] for s in (' | ', '\x1f', '='))
        assert x['codes'].max() < len(x['levels']) and x['codes'].min() >= -1
        assert (x['codes'][:hp.WARM_BARS] == -1).all()
        heat.read_state(x, np.arange(0, m['n'], 7))
        for lv, side, lname in heat.event_levels(x):
            heat.level_events(x, lv, side)
        if '.p.' in x['name']:
            assert x['base'] == x['name']
        else:
            assert x['base'] == x['name'].split('.')[0] + '.' + x['name'].split('.')[1]
    per_z = 26 * 2 + 4 + 9
    per_k = 12 * 2 + 2 + 9
    assert len(R) == 2 * (3 * per_z + per_k)
    # all timeframes: 885 readings, 54 compact
    full = len(hp.PAT_TFS) * 3 * per_z + len(hp.K_TFS) * per_k
    assert full == 885
    comp = [f'{k}m:CHART.{fr}.{x}' for k, fr, r in hp.frames() for x in (('ANY', 'BIAS', 'STRUCT', 'BOS') if fr != 'K' else ('ANY', 'BIAS'))]
    assert len(comp) == 54
    assert [x['name'] for x in hp.compact(R)] == [c for c in comp if c in set(names)]
    json.dumps(meta, allow_nan=True)
    assert set(meta['sha256']) == set(names)


def test_kernel_vectorised_equals_direct():
    rng = np.random.default_rng(3)
    c = np.cumsum(rng.normal(0, 1, 400)) + 100.0
    ends = np.arange(100, 150, dtype=np.int64)
    loo, sm, sw = hp.kernel_mats()
    hs, Y, Y2 = hp._ksmooth(c, ends, loo, sm, sw)
    X = np.stack([c[e - hp.K_WIN + 1:e + 1] for e in ends])
    hs2, Yb, Y2b = hp.kernel_smooth_blas(X)
    assert np.array_equal(hs, hs2)
    assert np.abs(Y - Yb).max() < 1e-9 and np.abs(Y2 - Y2b).max() < 1e-9
    # a direct per-window Nadaraya-Watson with leave-one-out CV
    idx = np.arange(hp.K_WIN, dtype=float)
    for w in range(0, len(ends), 7):
        x = X[w] - X[w].mean()
        cvs = []
        for h in hp.K_GRID:
            K = np.exp(-0.5 * ((idx[:, None] - idx[None, :]) / h) ** 2)
            np.fill_diagonal(K, 0.0)
            cvs.append(((x - (K @ x) / K.sum(1)) ** 2).sum())
        g = int(np.argmin(cvs))
        assert g == hs[w]
        K = np.exp(-0.5 * ((idx[:, None] - idx[None, :]) / (hp.K_FACTOR * hp.K_GRID[g])) ** 2)
        assert np.abs((K @ x) / K.sum(1) - Y[w]).max() < 1e-9


def test_kernel_reported_once_and_window_local():
    """Each kernel instance is reported once (the 12-bar repeat rule), and a kernel instance depends only on its own
    window: the same detections on a later start."""
    m = _minutes(30, seed=12)
    mu = hp.units(m, m['n'])
    fb = hp.frame_bars(mu, 15)
    info, tab = hp.detect_k(fb)
    assert len(tab)
    for p, g in tab.groupby('pattern'):
        st = g['start'].to_numpy()
        ne = 2 if p in ('LMW.DTOP', 'LMW.DBOT') else 5
        ex = g[[f'ext{u}' for u in range(1, ne + 1)]].to_numpy()
        for i in range(len(g)):
            same = (st < st[i]) & (st >= st[i] - hp.K_REPEAT) & (np.abs(ex - ex[i]).max(1) <= hp.K_REPEAT_TOL)
            assert not same.any(), f'{p}: the instance at {st[i]} repeats an earlier one'
    fb2 = hp.frame_bars(mu, 15, 1000)
    info2, tab2 = hp.detect_k(fb2)
    late = tab[tab['start'] >= 1400][['pattern', 'start', 'brk', 'dir']].reset_index(drop=True)
    t2 = tab2.assign(start=tab2['start'] + 1000, brk=np.where(tab2['brk'] >= 0, tab2['brk'] + 1000, -1))
    late2 = t2[t2['start'] >= 1400][['pattern', 'start', 'brk', 'dir']].reset_index(drop=True)
    pd.testing.assert_frame_equal(late, late2, check_dtype=False)


# ------------------------------------------------------------------------------------------------ catalogue and stage
def test_catalogue_splits_and_outcomes(splits):
    """No A outcome reads a 2025 (split B) minute: every window that crosses A's end is NA; tbi is decided by minute
    closes; the join key of Part 3 finds the reading's own instance first."""
    days = 30
    m = _minutes(days, seed=9)
    splits(m['t0'], days, 20)
    R, edges, inst, meta = hp.pattern_readings(m, log=lambda *a: None, tfs=[5, 15])
    lab = heat.labels(m)
    cat = hp.catalogue(inst, lab, None)
    b0 = 20 * 1440
    a = cat[cat['split'] == 'A']
    for H in (60, 240, 1440):
        crosses = a['event_row'] + H >= b0
        assert a.loc[crosses, f'tgt{H}'].isna().all() and a.loc[crosses, f'half{H}'].isna().all()
    for H in hp.LAB_H:
        assert a.loc[a['event_row'] + H >= b0, f'ret{H}'].isna().all()
    assert (a['tbi_row'] < b0).all()
    assert ((a['best240_atr'].isna()) | (a['event_row'] + 240 < b0)).all()
    # edges from A instances only: moving B's prices does not move them
    m2 = _future_noise(m, b0 + 5, 3)
    R2, edges2, inst2, meta2 = hp.pattern_readings(m2, log=lambda *a: None, tfs=[5, 15])
    assert edges2 == edges
    # Part 3's join (first row per frame, pattern, event_row) is the instance the event reading shows
    by = {x['name']: x for x in R}
    first = cat[cat['near'] == 0].drop_duplicates(['frame', 'pattern', 'event_row'])
    for r in first.sample(min(300, len(first)), random_state=1).itertuples():
        x = by[f'{r.tf}:CHART.{r.fr}.{r.pattern}']
        lv = x['levels'][x['codes'][r.event_bar]] if x['codes'][r.event_bar] >= 0 else None
        if lv is not None and r.event != 'half target':
            assert lv == r.event


def _hm2_ctx(tmp_path, days=45, a_days=30):
    from oracle import heat_hm2 as hm
    start = heat.HEAT_END - days * DAY
    m = _minutes(days, seed=17, start=start)
    lab = heat.labels(m)
    g = heat.Grid(m, lab)
    c = np.log(m['c'])
    R = []
    for k in (1, 15):
        nb = m['n'] // k
        cb = c[k - 1::k][:nb]
        x = np.r_[np.full(10, np.nan), cb[10:] - cb[:-10]]
        e = np.quantile(x[:g.sp['A'].hi // k][np.isfinite(x[:g.sp['A'].hi // k])], heat.ZONE_Q)
        R.append({'name': f'{k}m:R10', 'k': k, 'codes': heat.bucket(x, e), 'levels': heat.ZONES, 'base': f'{k}m:R10', 'zones': True, 'type': 'osc'})
    return hm.make_ctx(m, R, 'X', 0, lab=lab, g=g, log=lambda *a: None)


def test_stage_hook_leaves_ctx_untouched(tmp_path, monkeypatch):
    days, a_days = 56, 32                                   # B >= 20 days: cells pass the floors and the re-measure runs
    start = heat.HEAT_END - days * DAY
    monkeypatch.setattr(heat, 'SPLITS', {'A': (start, start + a_days * DAY), 'B': (start + a_days * DAY, heat.HEAT_END)})
    ctx = _hm2_ctx(tmp_path, days, a_days)
    ctx.extra_readings = {'BASE:LastCandle': {'name': 'BASE:LastCandle'}}
    before = {k: id(v) for k, v in ctx.__dict__.items()}
    keys = set(ctx.__dict__)
    csum = hashlib.sha256(np.asarray(ctx.C).tobytes()).hexdigest()
    names = list(ctx.names)
    out = str(tmp_path / 'patterns')
    meta = hp.stage(ctx, out, procs=1, log=lambda *a: None)
    assert set(ctx.__dict__) == keys and all(id(ctx.__dict__[k]) == v for k, v in before.items())
    assert hashlib.sha256(np.asarray(ctx.C).tobytes()).hexdigest() == csum and ctx.names == names
    assert list(ctx.extra_readings) == ['BASE:LastCandle']
    for f in ('meta.json', 'chart_heat.csv.gz', 'chart_summary_counts.json', 'chart_candidates.csv.gz', 'anatomy.csv.gz', 'losers.csv.gz',
              'instances.csv.gz', 'examples.json', 'live_meta.json', 'chart_near_copies.csv.gz'):
        assert os.path.isfile(os.path.join(out, f)), f
    with open(os.path.join(out, 'meta.json')) as f:
        mj = json.load(f)
    assert mj['schema'] == 'oracle-heat-chart-1' and len(mj['sha256']) == 885
    # (review fix; design item 9) HM2's copy merge on the compact readings: kept plus merged names are the 54
    assert len(mj['compact']) + sum(len(v) for v in mj['compact_aliases'].values()) == 54
    sha = hashlib.sha256()
    with gzip.open(os.path.join(out, 'chart_heat.csv.gz'), 'rb') as f:
        sha.update(f.read())
    assert sha.hexdigest() == mj['table_sha256']
    h = pd.read_csv(os.path.join(out, 'chart_heat.csv.gz'), low_memory=False)
    assert {'chart', 'chart_held', 'chart_bos'} <= set(h['kind'])
    assert 'baseline' not in set(h['kind'])
    assert h.loc[h['kind'] == 'chart', 'shape_lift'].notna().any()
    cand = hp._read_csv(os.path.join(out, 'chart_candidates.csv.gz'))
    assert len(cand) and cand['key'].str.contains(':CHART.', regex=False).all()
    assert h['kind'].isin(['xstate', 'xonset']).any()                     # HM2's re-measure of the chart candidates
    # the drill's entry: readings and a catalogue joined on (frame, pattern, event_row)
    R, cat = hp.series_readings(ctx)
    assert len(R) == 885 and {'frame', 'pattern', 'event_row'} <= set(cat.columns) and set(hp.PARAMS) <= set(cat.columns)
    assert (cat['frame'].str.contains(':')).all()
    assert set(ctx.__dict__) == keys


def test_twin_identity(splits):
    """A twin's readings are the detectors on heat.make_twin's own bars (the identical pipeline)."""
    days = 20
    m = _minutes(days, seed=13)
    splits(m['t0'], days, 14)
    tw = heat.make_twin(m, 2)
    R, edges, inst, meta = hp.pattern_readings(tw, log=lambda *a: None, tfs=[15])
    mu = hp.units(tw, int((heat.SPLITS['A'][1] - heat.HMAX * MIN - tw['t0']) // MIN))
    zz, st, bos, tab = hp.detect_zz(hp.frame_bars(mu, 15), 4)
    pd.testing.assert_frame_equal(inst['15m:z4'].reset_index(drop=True), tab.reset_index(drop=True))


def test_never_doge(tmp_path):
    with pytest.raises(SystemExit):
        hp.main(['readings', '--csv', str(tmp_path / 'DOGE.csv'), '--out', str(tmp_path / 'o')])
    with pytest.raises(SystemExit):
        hp.main(['coin', '--asset', 'DOGE', '--csv', str(tmp_path / 'x.csv'), '--out', str(tmp_path / 'o')])


def _no_timing(x):
    if isinstance(x, dict):
        return {k: _no_timing(v) for k, v in x.items() if 'seconds' not in k and k != 'peak_rss_mb'}
    return x


def _series_files(d) -> dict:
    """HM2's series files by name, compared by content: gzip text unzipped (its header holds a time), npz arrays,
    JSON parsed, meta.json without its timing, memory and shard-path fields."""
    out = {}
    for root, dirs, files in os.walk(d):
        dirs[:] = [x for x in dirs if x not in ('patterns', 'shards')]
        for f in files:
            p = os.path.join(root, f)
            rel = os.path.relpath(p, d)
            if f.endswith('.gz'):
                with gzip.open(p, 'rb') as fh:
                    out[rel] = fh.read()
            elif f.endswith('.npz'):
                with np.load(p, allow_pickle=False) as z:
                    out[rel] = {k: z[k].tobytes() for k in z.files}
            elif f.endswith('.json'):
                with open(p) as fh:
                    j = json.load(fh)
                if f == 'meta.json':
                    j = _no_timing(j)
                    j.pop('shards', None)
                out[rel] = j
            else:
                with open(p, 'rb') as fh:
                    out[rel] = fh.read()
    return out


def test_hm2_untouched(tmp_path, monkeypatch):
    """Route A (OR-HM2-part4 build plan section 2): heat_hm2.run_series(patterns=True) writes HM2's files exactly as
    without the flag (meta.json without its timing, memory and shard-path fields), then the stage's files under
    <out>/patterns (its chart shards under <shards>/patterns); a --part i/S job never runs the stage; a failing stage
    leaves HM2's files and the return alone and writes patterns/error.txt; the CLI has the flag on coin and finish."""
    from oracle import heat_hm2 as hm
    days, a_days = 56, 32
    start = heat.HEAT_END - days * DAY
    monkeypatch.setattr(heat, 'SPLITS', {'A': (start, start + a_days * DAY), 'B': (start + a_days * DAY, heat.HEAT_END)})
    quiet = lambda *a: None                                               # noqa: E731
    runs = {}
    for flag in (False, True):
        ctx = _hm2_ctx(tmp_path, days, a_days)
        out = str(tmp_path / f'hm2_{int(flag)}')
        runs[flag] = hm.run_series('X', 'x.csv', out, ctx=ctx, procs=1, learn=False, shards=str(tmp_path / f'shards_{int(flag)}'), patterns=flag,
                                   log=quiet)
    a, b = _series_files(tmp_path / 'hm2_0'), _series_files(tmp_path / 'hm2_1')
    assert set(a) == set(b) and {'meta.json', 'heat.csv.gz', 'candidates.csv.gz', 'summary_counts.json'} <= set(a)
    for k in a:
        assert a[k] == b[k], k
    assert not os.path.exists(tmp_path / 'hm2_0' / 'patterns')
    pm = json.load(open(tmp_path / 'hm2_1' / 'patterns' / 'meta.json'))
    assert pm['schema'] == 'oracle-heat-chart-1' and pm['table_sha256'] and pm['part'] == [0, 1]
    assert os.path.isdir(tmp_path / 'shards_1' / 'patterns') and not os.path.exists(tmp_path / 'hm2_1' / 'patterns' / 'shards')
    # a --part job never runs the stage
    called = []
    monkeypatch.setattr(hp, 'stage', lambda *x, **k: called.append(1))
    hm.run_series('X', 'x.csv', str(tmp_path / 'part'), ctx=_hm2_ctx(tmp_path, days, a_days), procs=1, learn=False, part=(0, 2), patterns=True, log=quiet)
    assert not called and not os.path.exists(tmp_path / 'part' / 'patterns')

    def boom(*x, **k):
        raise RuntimeError('planted stage failure')
    monkeypatch.setattr(hp, 'stage', boom)
    logs = []
    mt = hm.run_series('X', 'x.csv', str(tmp_path / 'fail'), ctx=_hm2_ctx(tmp_path, days, a_days), procs=1, learn=False, patterns=True,
                       log=lambda *x: logs.append(' '.join(map(str, x))))
    assert mt['schema'] == 'oracle-heat-hm2-1' and os.path.isfile(tmp_path / 'fail' / 'meta.json')
    assert 'planted stage failure' in open(tmp_path / 'fail' / 'patterns' / 'error.txt').read()
    assert any(x.startswith('::warning::') and 'Part 4' in x for x in logs)
    with pytest.raises(SystemExit):                                       # the flag is on coin and finish; DOGE still refused
        hm.main(['coin', '--asset', 'DOGE', '--csv', 'x.csv', '--out', str(tmp_path / 'd'), '--patterns'])
    with pytest.raises(SystemExit) as e:
        hm.main(['finish', '--help'])
    assert e.value.code == 0


def test_frame_without_instances(splits):
    """A frame with no instance at all (the 8-ATR zigzag on 4-hour bars of a short series, as on the end-to-end smoke
    run's 90 days) gives a numeric empty table: its edges are None, its readings exist (all 'none' / NA) and the
    catalogue holds no row of it."""
    days = 30
    m = _minutes(days, seed=21)
    splits(m['t0'], days, 20)
    R, edges, inst, meta = hp.pattern_readings(m, log=lambda *a: None, tfs=[240])
    T = inst['240m:z8']
    assert len(T) == 0 and all(np.issubdtype(T[c].dtype, np.number) for c in hp._ICOLS + hp._FCOLS)
    assert all(v is None for v in edges['240m:z8'].values())
    assert any(r['name'].startswith('240m:CHART.z8.') for r in R)
    lab = heat.labels(m)
    from oracle import heat_hm2 as hm
    with hm.h240():
        lab240 = heat.labels(m)
    cat = hp.catalogue(inst, lab, lab240, slim=True)
    assert not (cat['frame'] == '240m:z8').any() and len(cat) > 0
