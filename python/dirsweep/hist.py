"""Per-day histograms of the reading cells and the hindsight outcome at each horizon (PREREG-3.md sections 3 and 5).

`cell_arrays(m, step, horizon, nd, day_off)` returns, for one coin and one horizon, four (N_CELLS, nd) arrays:
  ncall  rows where the rule's reading is defined and the outcome minute is observable (called rows)
  ndec   of those, rows whose move over `horizon` minutes is at least 1.5 steps (decided)
  cf     of the decided, rows where the FADE side is right (the follow side is right on ndec - cf)
  sbps   sum over called rows of the fade side's aligned move in basis points of the entry open
A cell is (lookback, z, a, r, phase set); 'z >= threshold' cells are cumulative: the joint histogram over the threshold counts is reverse-summed.
"""
import numpy as np

from dirsweep import features as F
from dirsweep import grid as G

NCELL_RAW = G.NZ * G.NA * G.NR * 15


def _cumulate(a: np.ndarray) -> np.ndarray:
    """(nd, NZ, NA, NR, 15) joint counts -> (PER_K, nd) rule cells: '>= threshold' on z, a, r and the phase sets summed."""
    for ax in (1, 2, 3):
        a = np.flip(np.cumsum(np.flip(a, ax), axis=ax), ax)
    sets = np.stack([a[..., list(p)].sum(-1) for p in G.PHASES], axis=-1)      # (nd, NZ, NA, NR, NP)
    return sets.reshape(a.shape[0], G.PER_K).T


def cell_arrays(m: dict, step: float, horizon: int, nd: int = G.ND, day_off: int = None, ks=G.K, pre: dict = None, row_hi: int = None) -> dict:
    n = m['n']
    day_off = (m['t0'] // G.DAY - G.DAY0) if day_off is None else day_off
    pre = pre or F.prepare(m)
    o = np.asarray(m['o'], float)
    gcs = pre['gcs']
    e_all = np.arange(n)
    # observable: no gap minute in (e, e+60] and the outcome minute exists (PREREG-3.md section 2)
    fut = np.zeros(n, bool)
    last = n - 1 - G.EDGE
    if last >= 0:
        e = np.arange(0, last + 1)
        fut[e] = (gcs[e + G.EDGE + 1] - gcs[e + 1]) == 0
    day = e_all // 1440 + day_off
    inwin = (day >= 0) & (day < nd)
    if row_hi is not None:
        inwin &= e_all < row_hi
    mv = np.zeros(n)
    hi = n - horizon
    mv[:hi] = (o[horizon:] - o[:hi]) / step
    dec = np.abs(mv) >= G.FLAT
    bps = np.zeros(n)
    bps[:hi] = (o[horizon:] - o[:hi]) / o[:hi] * 1e4
    out = {x: np.zeros((G.N_CELLS, nd), np.float32 if x == 'sbps' else np.int32) for x in ('ncall', 'ndec', 'cf', 'sbps')}
    for ik, k in enumerate(ks):
        c = F.codes(m, k, pre)
        use = c['ok'] & fut & inwin
        if not use.any():
            continue
        joint = (((c['zc'].astype(np.int64) * G.NA + c['ac']) * G.NR + c['rc']) * 15 + c['mq'])
        flat = day.astype(np.int64) * NCELL_RAW + joint
        sg = c['sgn'].astype(np.int64)
        fade_right = dec & (np.sign(mv).astype(np.int64) == -sg)
        size = nd * NCELL_RAW
        sl = slice(ik * G.PER_K, (ik + 1) * G.PER_K)
        sel = flat[use]
        shape = (nd, G.NZ, G.NA, G.NR, 15)
        out['ncall'][sl] = _cumulate(np.bincount(sel, minlength=size).reshape(shape)).astype(np.int32)
        out['ndec'][sl] = _cumulate(np.bincount(flat[use & dec], minlength=size).reshape(shape)).astype(np.int32)
        out['cf'][sl] = _cumulate(np.bincount(flat[use & fade_right], minlength=size).reshape(shape)).astype(np.int32)
        w = (-sg * bps)[use]
        out['sbps'][sl] = _cumulate(np.bincount(sel, weights=w, minlength=size).reshape(shape)).astype(np.float32)
    return out


def add(a: dict, b: dict) -> dict:
    """Sum two coins (same shapes)."""
    return {x: a[x] + b[x] for x in a}
