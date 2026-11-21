"""Lockout replay of a rule (AMENDMENT-3.md): the calls a rule would really make one after another on one coin, with the 15-minute lockout of
PREREG.md (after a call at minute e no new call on that coin before minute e + 15), scored at the 15-minute horizon.

The sweep counts every admitted row, so neighbouring rows of a burst are counted as separate calls with overlapping outcomes. The replay takes the first
row of a burst, then waits 15 minutes: these are the calls whose outcomes do not overlap, the ones a forward test and a trader would see.
"""
import numpy as np

from dirsweep import features as F
from dirsweep import grid as G


class Replayer:
    """One coin's grid with its readings cached per lookback, so many rules can be replayed cheaply."""

    def __init__(self, m: dict, step: float, pre: dict = None, nd: int = G.ND, day_off: int = None):
        self.m, self.step, self.nd = m, step, nd
        self.pre = pre or F.prepare(m)
        n = m['n']
        self.day_off = (m['t0'] // G.DAY - G.DAY0) if day_off is None else day_off
        gcs = self.pre['gcs']
        fut = np.zeros(n, bool)
        last = n - 1 - G.EDGE
        if last >= 0:
            e = np.arange(0, last + 1)
            fut[e] = (gcs[e + G.EDGE + 1] - gcs[e + 1]) == 0
        self.fut = fut
        self.day = np.arange(n) // 1440 + self.day_off
        self._codes = {}

    def codes(self, k: int) -> dict:
        if k not in self._codes:
            self._codes[k] = F.codes(self.m, k, self.pre)
        return self._codes[k]

    def rows(self, rid: int) -> tuple:
        """Rows where rule `rid` makes a call (a reading defined from the past alone and an observable outcome, as in hist.cell_arrays), and the sign
        (+1 / -1) of the last-k-minute move at each row."""
        cell, _ = divmod(int(rid), 2)
        ik, iz, ia, ir, ip = G.unpack(cell)
        c = self.codes(G.K[ik])
        phase = np.zeros(15, bool)
        phase[list(G.PHASES[ip])] = True
        use = c['ok'] & self.fut & (self.day >= 0) & (self.day < self.nd) & (c['zc'] >= iz) & (c['ac'] >= ia) & (c['rc'] >= ir) & phase[c['mq']]
        return np.flatnonzero(use), c['sgn']

    def replay(self, rid: int, lo_day: int, hi_day: int, horizon: int = 15, minutes: int = 15) -> dict:
        """Per-day counts over days [lo_day, hi_day): calls made, decided calls and calls right (side of `rid`), after the lockout. The lockout runs over
        the whole stretch, so a burst that straddles the start day is entered as it would be in a continuous run."""
        rows, sgn = self.rows(rid)
        rows = lockout(rows, minutes)
        nday = hi_day - lo_day
        out = {'calls': np.zeros(nday), 'decided': np.zeros(nday), 'right': np.zeros(nday)}
        if not len(rows):
            return out
        d = self.day[rows]
        keep = (d >= lo_day) & (d < hi_day)
        rows, d = rows[keep], d[keep] - lo_day
        o = np.asarray(self.m['o'], float)
        mv = (o[rows + horizon] - o[rows]) / self.step
        dec = np.abs(mv) >= G.FLAT
        fade_right = np.sign(mv) == -sgn[rows]
        right = dec & (fade_right if int(rid) % 2 == 0 else ~fade_right)
        out['calls'] = np.bincount(d, minlength=nday).astype(float)
        out['decided'] = np.bincount(d[dec], minlength=nday).astype(float)
        out['right'] = np.bincount(d[right], minlength=nday).astype(float)
        return out


def rule_rows(m: dict, rid: int, pre: dict = None, nd: int = G.ND, day_off: int = None) -> tuple:
    rp = Replayer(m, 0.01, pre, nd, day_off)
    rows, sgn = rp.rows(rid)
    return rows, sgn, rp.day


def lockout(rows: np.ndarray, minutes: int = 15) -> np.ndarray:
    """Greedy in time order: keep a row only if it is at least `minutes` after the last kept row."""
    keep, last = [], -10 ** 12
    for e in rows.tolist():
        if e - last >= minutes:
            keep.append(e)
            last = e
    return np.asarray(keep, dtype=np.int64)


def replay(m: dict, step: float, rid: int, lo_day: int, hi_day: int, pre: dict = None, horizon: int = 15, minutes: int = 15, nd: int = G.ND) -> dict:
    return Replayer(m, step, pre, nd).replay(rid, lo_day, hi_day, horizon, minutes)
