"""The readings of PREREG-3.md section 3, per entry row e, from the grid of `oracle.heat_live.grid` (o h l c v tb gap, one row per minute).

Everything at row e uses the open of minute e and the bars e-k..e-1 (and, for sigma and mean volume, minutes e-1440..e-1): nothing later.
`codes` is the only place readings are made; `cut_test` rebuilds them on a truncated grid and demands the same numbers (PREREG-3.md section 7).
"""
import numpy as np

from dirsweep import grid as G


def _cum(x):
    return np.concatenate([[0.0], np.cumsum(x, dtype=np.float64)])


def prepare(m: dict) -> dict:
    """Cumulative sums shared by every lookback."""
    if m.get('tb') is None:
        raise ValueError('the taker-buy volume (tb) is needed for the flow filter')
    return {'vcs': _cum(m['v']), 'tbcs': _cum(m['tb']), 'gcs': np.concatenate([[0], np.cumsum(m['gap'].astype(np.int64))])}


def codes(m: dict, k: int, pre: dict = None) -> dict:
    """Per row (length n): ok (a call can be made from the past alone), sgn (sign of the move, +1/-1), zc, ac, rc (threshold counts) and mq.
    Rows before MIN_ROW, rows with a gap minute in [e-60, e], a trailing window with more than MAX_GAP_W gap minutes, a zero move,
    a zero sigma or no volume are not ok."""
    pre = pre or prepare(m)
    n, o = m['n'], np.asarray(m['o'], float)
    out = {x: np.zeros(n, np.int8) for x in ('sgn', 'zc', 'ac', 'rc', 'mq')}
    ok = np.zeros(n, bool)
    if n <= G.MIN_ROW:
        return dict(out, ok=ok)
    e = np.arange(G.MIN_ROW, n)
    M = np.zeros(n)
    M[k:] = o[k:] - o[:-k]
    css = _cum(M * M)
    sig2 = (css[e] - css[e - G.W]) / G.W
    vcs, tbcs, gcs = pre['vcs'], pre['tbcs'], pre['gcs']
    vk = vcs[e] - vcs[e - k]
    tbk = tbcs[e] - tbcs[e - k]
    meanv = (vcs[e] - vcs[e - G.W]) / G.W
    past_gaps = gcs[e + 1] - gcs[e - G.EDGE]
    win_gaps = gcs[e] - gcs[e - G.W]
    Me = M[e]
    with np.errstate(divide='ignore', invalid='ignore'):
        good = (past_gaps == 0) & (win_gaps <= G.MAX_GAP_W) & (Me != 0) & (sig2 > 0) & (vk > 0) & (meanv > 0) & np.isfinite(Me)
        sgn = np.sign(Me)
        z = np.abs(Me) / np.sqrt(sig2)
        imb = (2.0 * tbk - vk) / vk
        a = sgn * imb
        rv = vk / (k * meanv)
    good &= np.isfinite(z) & np.isfinite(a) & np.isfinite(rv)
    ok[e] = good
    out['sgn'][e] = np.where(good, sgn, 0).astype(np.int8)
    out['zc'][e] = np.where(good, np.searchsorted(G.TZ, np.where(good, z, 0.0), side='right'), 0)
    out['ac'][e] = np.where(good, np.searchsorted(G.TA, np.where(good, a, 0.0), side='right'), 0)
    out['rc'][e] = np.where(good, np.searchsorted(G.TR, np.where(good, rv, 0.0), side='right'), 0)
    out['mq'][e] = (e % 60) % 15
    return dict(out, ok=ok)


def cut_test(m: dict, ks=G.K, cuts=12, seed=20261125, lookahead=None) -> dict:
    """Truncate the grid at `cuts` random rows, rebuild the readings of every lookback on rows before the cut, and compare with the full
    build. `lookahead` (tests only) is a function applied to the full build's codes to plant a one-bar leak and prove this test sees it."""
    n = m['n']
    rng = np.random.default_rng(seed)
    pts = sorted(int(x) for x in rng.integers(G.MIN_ROW + 10, n - 5, cuts))
    full_pre = prepare(m)
    mism, compared = 0, 0
    for k in ks:
        full = codes(m, k, full_pre)
        if lookahead is not None:
            full = lookahead(m, k, full)
        for c in pts:
            part = {x: (np.asarray(m[x])[:c] if hasattr(m[x], '__len__') and not isinstance(m[x], (int, float)) else m[x])
                    for x in ('o', 'h', 'l', 'c', 'v', 'tb', 'gap')}
            part.update(n=c, t0=m['t0'])
            sub = codes(part, k)
            for x in ('ok', 'sgn', 'zc', 'ac', 'rc', 'mq'):
                a, b = np.asarray(full[x])[:c], np.asarray(sub[x])
                mism += int((a != b).sum())
            compared += c
    return {'cuts': pts, 'rows_compared': compared, 'mismatches': mism, 'ok': mism == 0}
