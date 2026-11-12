"""OR-XD lite: outside-derivatives readings for the OR-HM1 heat engine (python/oracle/prereg/OR-XD.md).

  python3 -m oracle.heat_outside coin --asset BTC --spot S --perp P --oi O --out out/BTC [--twin 1] [--procs 4] [--perp-lag 1]
  python3 -m oracle.heat league --inputs out --out out/league          (heat.league, unchanged)

Five NEW readings (all 1-minute, 5-zone value readings, decision at the close of the minute, nothing later is read):
  CVDP:Div15        perp net taker share over 15 minutes minus the spot net taker share over the same 15 minutes
  CVDP:PxDiv60      absorption: the 60-minute perp net taker flow (z-scored) where price moved the other way, else 0
  LIQMAP:DistAbove  distance (in 60-minute realised volatility) to the nearest modelled short-liquidation cluster above
  LIQMAP:DistBelow  ... to the nearest modelled long-liquidation cluster below
  LIQMAP:Skew       ln of modelled short-liq notional within +2% over long-liq notional within -2%
LIQMAP is a MODEL of where leveraged positions would liquidate (built from open-interest CONTRACT changes, priced on the path in
use, so a twin does not inherit the real price move), not data. An OI snapshot stamped ts is known at ts + 10 minutes.
REFERENCE ONLY (not in the league): CVDP:15 (perp net share) and REF:FlowTB15 (spot taker-buy share), used for the
near-duplicate measurement.

The OR-HM1 engine runs unchanged (heat.run_coin): only heat.build_readings is replaced for the duration of the call by
a builder that returns these readings (as pair conditions too, so new x new pairs are tested), and heat.make_twin is
wrapped to remember the twin seed. Output tables and meta.json keep the OR-HM1 schema (heat.league reads them
unchanged); meta.json gains: near_duplicates, direction_coupling, constants, model, reading_share, xd_input.
Never loads a minute or OI row at or after HEAT_END (a file that holds one is refused). NEVER DOGE.

OPTIONAL HOOK FOR OR-HM2 (hm2_outside_readings, off unless heat_hm2 is run with --outside): the same five readings, computed with the
same frozen constants and functions (xd_values, xd_readings), as extra single readings for the OR-HM2 pair scan and learner. Research
only: nothing here is live-ready (the bot has no perp taker-flow or OI-history feed), the hook never imports heat_xdata (it is handed
the Zoner and uses only z.zone / z.skipped), it refuses with a reason instead of guessing (no taker-buy column, no oi_usd, the
alignment or OI-clock guard, fewer than MIN_A / MIN_A_DAYS), it has its own OI known-time rule (stamp + 10 minutes, not OR-HM2's
load_extra + 5 minutes), it reads the raw OI rows (clean_oi picks among the rows of one stamp), builds a twin by the pre-registered
OR-XD twin rule (twin spot x the real perp / spot ratio; NOT HM2's joint-flipped perp) and has no perp-lag variant. See the
amendment in prereg/OR-XD.md.
"""
import argparse
import json
import math
import os
import time

import numpy as np
import pandas as pd

from oracle import heat
from oracle.common import DAY, MIN

HEAT_END = heat.HEAT_END

# ------------------------------------------------------------------------------------------------ frozen constants
LEAGUE = ['CVDP:Div15', 'CVDP:PxDiv60', 'LIQMAP:DistAbove', 'LIQMAP:DistBelow', 'LIQMAP:Skew']
REFS = ['CVDP:15', 'REF:FlowTB15']
FAMILY = {'CVDP:Div15': 'CVDP', 'CVDP:PxDiv60': 'CVDP', 'LIQMAP:DistAbove': 'LIQMAP', 'LIQMAP:DistBelow': 'LIQMAP', 'LIQMAP:Skew': 'LIQMAP'}
SNAP = 5 * MIN                  # one Binance metrics snapshot
KNOWN = 10 * MIN                # a snapshot stamped ts is the snapshot instant S = ts + 5 min at the latest (new create_time
                                # convention) and is known at S + 5 min = ts + 10 min (design 2.2; the conservative clock)
CARRY = 10 * MIN                # a model state is used for at most this long after its known time
GAP_MAX = 15 * MIN              # a gap between snapshots longer than this: no step, the next row only sets the baseline
EXPIRE = 30 * DAY               # 8,640 five-minute steps
LEVERAGE = (10, 25, 50, 100)
WEIGHTS = (0.4, 0.3, 0.2, 0.1)
MAINT = 0.005                   # one maintenance margin for every coin (Binance's real brackets are not used)
BUCKET = 1.001                  # price buckets of 0.1%
LNB = math.log(BUCKET)
CLUSTER_SHARE = float(os.environ.get('XD_CLUSTER_SHARE', '0.02'))   # a cluster: a bucket with >= this share of the latest OI value (frozen 0.02; Amendment 1 adds a 0.01 variant)
SKEW_BAND = 0.02
SKEW_EPS = 0.001                # of the OI value
RENORM = 1e-6
PRESENCE = 0.8                  # every rolling window needs this share of its minutes present
SD_WIN = 1440
MIN_A = 1000
MIN_A_DAYS = 30                 # ... on at least this many distinct days of A, else the reading is skipped
MISSING_TB_MAX = 0.001          # more rows than this share with volume but an empty tb: the file is refused
CONSTANTS = {'leverage': list(LEVERAGE), 'weights': list(WEIGHTS), 'maintenance_margin': MAINT, 'bucket_ratio': BUCKET,
             'cluster_share_of_oi': CLUSTER_SHARE, 'expire_days': 30, 'skew_band': SKEW_BAND, 'skew_eps_share_of_oi': SKEW_EPS,
             'snapshot_ms': SNAP, 'known_ms': KNOWN, 'carry_ms': CARRY, 'min_a_days': MIN_A_DAYS, 'snapshot_gap_max_ms': GAP_MAX, 'presence': PRESENCE, 'sd_window': SD_WIN,
             'zone_q': heat.ZONE_Q, 'min_a_values': MIN_A, 'renorm_below': RENORM}


# ---------------------------------------------------------------------------------------------------------- loaders
def _no_doge(*xs):
    for x in xs:
        if x is not None and 'DOGE' in str(x).upper():
            raise SystemExit('NEVER DOGE')


def read_checked(path: str, cols: tuple, kind: str) -> pd.DataFrame:
    """A CSV with 'ts' in ms of 13 digits (a seconds or microseconds stamp is refused) and no row at or after
    HEAT_END (strict, as heat.load_minutes: the workflow cuts the file first)."""
    _no_doge(path)
    df = pd.read_csv(path)
    miss = [c for c in cols if c not in df.columns]
    if miss:
        raise SystemExit(f'{path}: {kind} file lacks column(s) {miss}')
    ts = pd.to_numeric(df['ts'], errors='coerce')
    if ts.isna().any():
        raise SystemExit(f'{path}: {int(ts.isna().sum()):,} rows with no numeric ts')
    ts = ts.to_numpy(np.int64)
    if len(ts) and not ((ts >= 10 ** 12) & (ts < 10 ** 13)).all():
        raise SystemExit(f'{path}: ts must be milliseconds of 13 digits (this one holds {len(str(int(ts[0])))} digits at row 1)')
    late = int((ts >= HEAT_END).sum())
    if late:
        raise SystemExit(f'{path}: {late:,} rows at or after {pd.Timestamp(HEAT_END, unit="ms")}: the heat tables stop there; cut the file first')
    df['ts'] = ts
    return df


def clean_oi(df: pd.DataFrame, pp: dict = None):
    """Snapshots (ts, oi, oi_usd) with a finite positive oi (contracts) and oi_usd. Each stamp is CEILED to the 5-minute grid
    (an off-grid stamp 02:35:02 counts as 02:40: a snapshot is never used earlier than its stamp), then one row per grid
    stamp is kept: with the perp bars pp given, the row whose implied price oi_usd / oi is closest to the perp open at ts or
    ts + 5 min, else the last row of the file. Sorted by ts. Returns (frame, info)."""
    d = df[['ts', 'oi', 'oi_usd']].copy()
    for c in ('oi', 'oi_usd'):
        d[c] = pd.to_numeric(d[c], errors='coerce')
    n0 = len(d)
    d = d[np.isfinite(d['oi']) & (d['oi'] > 0) & np.isfinite(d['oi_usd']) & (d['oi_usd'] > 0)].copy()
    info = {'oi_rows_read': int(n0), 'oi_rows_unusable': int(n0 - len(d))}
    ts = d['ts'].to_numpy(np.int64)
    info['oi_off_grid_rows'] = int((ts % SNAP != 0).sum())
    d['ts'] = _ceil_div(ts, SNAP) * SNAP
    d['_err'] = 0.0
    if pp is not None and len(d):
        implied = np.log(d['oi_usd'].to_numpy() / d['oi'].to_numpy())
        e0, e1 = (np.abs(implied - np.log(_open_at(pp, d['ts'].to_numpy() + off))) for off in (0, SNAP))
        err = np.fmin(e0, e1)
        d['_err'] = np.where(np.isfinite(err), err, np.inf)
        d = d.sort_values(['ts', '_err'], kind='stable').drop_duplicates('ts', keep='first')
    else:
        d = d.drop_duplicates('ts', keep='last')
    info['oi_duplicates_dropped'] = int(len(ts) - len(d))
    d = d.drop(columns='_err').sort_values('ts')
    return d.reset_index(drop=True), info


def _open_at(pp: dict, t) -> np.ndarray:
    """The perp open at the minute starting at each t (ms); NaN off the grid, in a gap or before the first bar."""
    t = np.asarray(t, np.int64)
    i = (t - int(pp['t0'])) // MIN
    ok = (t >= pp['t0']) & ((t - int(pp['t0'])) % MIN == 0) & (i < pp['n'])
    ii = np.clip(i, 0, pp['n'] - 1)
    return np.where(ok & ~pp['gap'][ii], np.asarray(pp['o'], float)[ii], np.nan)


def perp_on_grid(m: dict, df: pd.DataFrame) -> dict:
    """The perp minute bars on m's grid (t0, n). A missing minute, a minute before the file's first row and a broken row
    (as heat.load_minutes: empty or non-positive price, high below the others; also a row with volume but an EMPTY tb) is a
    gap; a gap after the first row is forward-filled (o = h = l = c = the last close, volume 0); before the first row prices
    are NaN."""
    t0, n = int(m['t0']), int(m['n'])
    ts = df['ts'].to_numpy(np.int64)
    off = ts - t0
    on = (off >= 0) & (off % MIN == 0) & (off < n * MIN)
    d = df[on]
    px = d[['o', 'h', 'l', 'c']].to_numpy(float)
    v, tbv = d['v'].to_numpy(float), d['tb'].to_numpy(float)
    with np.errstate(invalid='ignore'):
        bad = (~np.isfinite(px).all(1) | ~np.isfinite(v) | (px <= 0).any(1) | (px[:, 1] < px.max(1)) | (px[:, 2] > px.min(1))
               | ((v > 0) & ~np.isfinite(tbv)))
    d = d[~bad].drop_duplicates('ts').sort_values('ts')
    pos = ((d['ts'].to_numpy() - t0) // MIN).astype(np.int64)
    gap = np.ones(n, bool)
    gap[pos] = False
    first = int(pos.min()) if len(pos) else n
    c = np.full(n, np.nan)
    c[pos] = d['c'].to_numpy(float)
    c = pd.Series(c).ffill().to_numpy()
    out = {'t0': t0, 'n': n, 'gap': gap, 'first': first, 'c': c, 'bad_rows': int(bad.sum()), 'off_grid': int((~on).sum())}
    for x in ('o', 'h', 'l'):
        a = c.copy()
        a[pos] = d[x].to_numpy(float)
        out[x] = a
    v = np.zeros(n)
    v[pos] = d['v'].to_numpy(float)
    tb = np.zeros(n)
    tb[pos] = d['tb'].fillna(0).to_numpy(float)
    out['v'], out['tb'] = v, tb
    return out


def lag_perp(pp: dict, k: int) -> dict:
    """The perp bars seen k minutes late (row i holds bar i - k; the first k rows are gaps). The live-lag rule of the design
    (a provisional +1 minute on every feed-fed input) and the +5 minute robustness rerun use this; k = 0 is this pass's
    archive-only default."""
    if k <= 0:
        return pp
    out = dict(pp)
    for x in ('o', 'h', 'l', 'c'):
        out[x] = lag(pp[x], k)
    for x in ('v', 'tb'):
        out[x] = np.r_[np.zeros(k), np.asarray(pp[x], float)[:len(pp[x]) - k]]
    out['gap'] = np.r_[np.ones(k, bool), np.asarray(pp['gap'], bool)[:len(pp['gap']) - k]]
    out['first'] = int(pp['first']) + k
    return out


def _corr(x, y):
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 1000 or x[ok].std() == 0 or y[ok].std() == 0:
        return None, int(ok.sum())
    return float(np.corrcoef(x[ok], y[ok])[0, 1]), int(ok.sum())


def check_alignment(sp: dict, pp: dict) -> dict:
    """Is the perp file on the spot's clock (ts = the minute OPEN in both)? corr(perp 1-minute log return at row i, spot return
    at row i + l) for l = -1, 0, +1 on rows where neither side is a gap: l = 0 must be above 0.5 and above twice both
    others, else SystemExit (a perp file stamped one minute early would feed every reading one minute of the future)."""
    ok = ~(np.asarray(sp['gap'], bool) | np.asarray(pp['gap'], bool))
    with np.errstate(invalid='ignore', divide='ignore'):
        rs = np.diff(np.log(np.where(ok, np.asarray(sp['c'], float), np.nan)), prepend=np.nan)
        rp = np.diff(np.log(np.where(ok, np.asarray(pp['c'], float), np.nan)), prepend=np.nan)
    n = len(rs)
    r = {}
    for l in (-1, 0, 1):
        r[l], cnt = _corr(rp[max(0, -l):n - max(0, l)], rs[max(0, l):n - max(0, -l)])
    out = {'r_m1': r[-1], 'r_0': r[0], 'r_p1': r[1], 'rows': cnt}
    if r[0] is None or r[-1] is None or r[1] is None:
        out['checked'] = False
        return out
    out['checked'] = True
    if not (r[0] > 0.5 and r[0] > 2 * max(abs(r[-1]), abs(r[1]))):
        raise SystemExit(f'perp file is not on the spot clock (return correlation at lag -1 / 0 / +1 minute: {r[-1]:.3f} / {r[0]:.3f} / {r[1]:.3f}): '
                         'check that ts is the minute OPEN in both files')
    return out


def check_oi_clock(oi: pd.DataFrame, pp: dict) -> dict:
    """The design's test (b): the median |ln(implied price oi_usd / oi) - ln(perp open at ts + off)| for off = 0, 5, 10, 15
    minutes. The snapshot reflects the instant ts (old convention) or ts + 5 min (new); the model takes S = ts + 5 min and
    knows it at ts + 10 min. If the implied price clearly matches a later open (10 or 15 min: less than half the error at
    0 and 5), the stamps are earlier than the clock assumes and the run is refused."""
    ts = oi['ts'].to_numpy(np.int64)
    implied = np.log(oi['oi_usd'].to_numpy() / oi['oi'].to_numpy())
    med = {}
    for off in (0, 5, 10, 15):
        e = np.abs(implied - np.log(_open_at(pp, ts + off * MIN)))
        e = e[np.isfinite(e)]
        med[off] = float(np.median(e)) if len(e) >= 1000 else None
    out = {'median_abs_log_diff_by_offset_min': {str(k): v for k, v in med.items()}, 'checked': all(v is not None for v in med.values())}
    if out['checked']:
        best = min(med, key=med.get)
        out['best_offset_min'] = best
        if best >= 10 and med[best] < 0.5 * min(med[0], med[5]):
            raise SystemExit(f'OI stamps look {best} minutes earlier than the model clock allows (implied price matches the perp open at ts + {best} min '
                             f'best: {med}); check the create_time convention before use')
    return out


def twin_signs(n: int, seed: int) -> np.ndarray:
    """heat.make_twin's own coin flips (the same call, so the same sequence)."""
    rng = np.random.default_rng([20261111, int(seed)])
    s = rng.choice(np.array([-1.0, 1.0]), int(n))
    s[0] = 1.0
    return s


def twin_perp(pp: dict, spot_real: dict, spot_twin: dict, s: np.ndarray) -> dict:
    """The perp path of a twin: the twin spot's o / h / l / c times the REAL perp / spot close ratio of the same minute (the
    real basis is kept), the perp taker volume flipped with the SAME signs as the spot's (make_twin's rule)."""
    with np.errstate(invalid='ignore', divide='ignore'):
        ratio = pp['c'] / np.asarray(spot_real['c'], float)
    out = dict(pp)
    for x in ('o', 'h', 'l', 'c'):
        out[x] = np.asarray(spot_twin[x], float) * ratio
    out['tb'] = np.where(s > 0, pp['tb'], pp['v'] - pp['tb'])
    return out


# ------------------------------------------------------------------------------------------------------ rolling helpers
def roll_sum(x, W: int, min_count: int = None):
    """Sum over the W rows ending at each row (cumsums: row i reads rows i-W+1..i only). NaN until a whole window exists and
    where the window holds fewer than min_count finite values (default W). Returns (sum, count of finite values)."""
    x = np.asarray(x, float)
    n = len(x)
    f = np.isfinite(x)
    cs = np.r_[0.0, np.cumsum(np.where(f, x, 0.0))]
    cf = np.r_[0, np.cumsum(f)]
    s = np.full(n, np.nan)
    k = np.zeros(n, np.int64)
    W = int(W)
    if n >= W:
        i = np.arange(W - 1, n)
        s[W - 1:] = cs[i + 1] - cs[i + 1 - W]
        k[W - 1:] = cf[i + 1] - cf[i + 1 - W]
    s[k < (W if min_count is None else min_count)] = np.nan
    return s, k


def roll_sd(x, W: int, min_count: int = None) -> np.ndarray:
    """Standard deviation (ddof 1) over the W rows ending at each row (see roll_sum)."""
    s1, k = roll_sum(x, W, min_count)
    s2, _ = roll_sum(np.asarray(x, float) ** 2, W, min_count)
    with np.errstate(invalid='ignore', divide='ignore'):
        var = (s2 - s1 * s1 / k) / (k - 1)
    return np.sqrt(np.maximum(var, 0.0))


def lag(x, k: int) -> np.ndarray:
    """x[i - k] at row i (NaN for the first k rows)."""
    x = np.asarray(x, float)
    if k <= 0:
        return x
    return np.full(len(x), np.nan) if k >= len(x) else np.r_[np.full(k, np.nan), x[:len(x) - k]]


def _runlen(gap: np.ndarray) -> np.ndarray:
    cs = np.cumsum(np.asarray(gap, bool), dtype=np.int64)
    return cs - np.maximum.accumulate(np.where(np.asarray(gap, bool), 0, cs))


def stale_rows(gap, W=1) -> np.ndarray:
    """The engine's stale rule on a window: True where the W rows ending at the row hold a forward-filled row, or the window
    starts within heat.STALE rows after one, or within STALE_LONG[1] rows after a gap run longer than STALE_LONG[0]."""
    gap = np.asarray(gap, bool)
    n = len(gap)
    i = np.arange(n)
    W = np.broadcast_to(np.asarray(W, np.int64), (n,))
    cg = np.r_[0, np.cumsum(gap)]
    lng = _runlen(gap) > heat.STALE_LONG[0]
    cl = np.r_[0, np.cumsum(lng)]
    lo1 = np.maximum(0, i - W + 1 - heat.STALE)
    lo2 = np.maximum(0, i - W + 1 - heat.STALE_LONG[1])
    return ((cg[i + 1] - cg[lo1]) > 0) | ((cl[i + 1] - cl[lo2]) > 0)


def _min_count(W: int) -> int:
    return int(math.ceil(PRESENCE * W - 1e-9))


def _ratio(num, den):
    with np.errstate(invalid='ignore', divide='ignore'):
        return np.where(den > 0, num / den, np.nan)


# ----------------------------------------------------------------------------------------- the liquidation-map model
def _ceil_div(a, b):
    return -((-a) // b)


class LiqModel:
    """A model of where open interest would liquidate, driven by CONTRACTS (the 'oi' column; the USD column would carry the
    price move into the model), advanced on the 5-minute OI snapshots in order of their KNOWN time. A snapshot stamped ts
    (ceiled to the 5-minute grid) is taken at S = ts + 5 min and known at T = S + 5 min = ts + 10 min (the conservative clock of
    design 2.2). State: notional (stored, times a global scale S) per 0.1% price bucket on the long-liquidation side and on the
    short-liquidation side, a generation per bucket, and a ledger of additions for expiry.

    pp: perp bars on the grid {t0, n, o, h, l, c, v, tb}; oi: DataFrame ts, oi (clean_oi). run() fills the per-minute arrays
    dist_up, dist_dn (bps to the nearest cluster, NaN: none) and skew; a hook(k, model) is called after every step (for tests)."""

    def __init__(self, pp: dict, oi: pd.DataFrame, hook=None):
        self.pp, self.hook = pp, hook
        self.t0, self.n = int(pp['t0']), int(pp['n'])
        self.ts = oi['ts'].to_numpy(np.int64)
        self.q = oi['oi'].to_numpy(float)                    # contracts
        self.Ss = self.ts + SNAP                             # the snapshot instant
        self.T = self.ts + KNOWN                             # known from here on
        c = np.asarray(pp['c'], float)
        fin = c[np.isfinite(c)]
        if not len(fin):
            raise SystemExit('perp file holds no price on the grid')
        lo = min(float(np.min(np.where(np.isfinite(pp['l']), pp['l'], np.inf))), float(fin.min()))
        hi = max(float(np.max(np.where(np.isfinite(pp['h']), pp['h'], -np.inf))), float(fin.max()))
        self.lo_b = int(math.floor(math.log(lo * 0.85) / LNB))
        self.hi_b = int(math.ceil(math.log(hi * 1.2) / LNB))
        self.nb = self.hi_b - self.lo_b + 1
        if self.nb > 400_000:
            raise SystemExit(f'perp price range too wide for 0.1% buckets: {self.nb:,}')
        self.bp = np.exp((np.arange(self.nb) + self.lo_b) * LNB)          # price of each bucket
        self.long = np.zeros(self.nb)
        self.short = np.zeros(self.nb)
        self.glong = np.zeros(self.nb, np.int64)
        self.gshort = np.zeros(self.nb, np.int64)
        self.S = 1.0
        L = np.array(LEVERAGE, float)
        self.w = np.array(WEIGHTS, float)
        self.mult_long = 1 - 1 / L + MAINT
        self.mult_short = 1 + 1 / L - MAINT
        K = len(self.ts)
        self.end = (self.Ss - self.t0) // MIN                # rows < end[k] are complete at S_k
        ee = np.clip(self.end - 1, 0, self.n - 1)
        px = np.where((self.end - 1 >= 0) & (self.end - 1 < self.n), c[ee], np.nan)
        self.val = self.q * px                               # latest OI value in USD at S_k, on the path in use
        self.led_t = np.zeros(K, np.int64)
        self.led_b = np.zeros((K, 8), np.int64)
        self.led_g = np.zeros((K, 8), np.int64)
        self.led_a = np.zeros((K, 8))
        self.cnt = self.lp = 0
        self._shares = []
        self.stats = {'snapshots': int(K), 'steps_add': 0, 'steps_scale': 0, 'steps_skipped_gap': 0, 'renorms': 0, 'expired_rows': 0,
                      'blocks_with_short_cluster': 0, 'blocks_with_long_cluster': 0, 'blocks': 0, 'sum_short_clusters': 0, 'sum_long_clusters': 0}
        self.dist_up = np.full(self.n, np.nan)
        self.dist_dn = np.full(self.n, np.nan)
        self.skew = np.full(self.n, np.nan)

    # ------------------------------------------------------------------------------------------------ buckets
    def bidx(self, price) -> np.ndarray:
        b = np.floor(np.log(price) / LNB + 0.5).astype(np.int64) - self.lo_b
        return np.clip(b, 0, self.nb - 1)

    def actual(self):
        return self.long * self.S, self.short * self.S

    # ---------------------------------------------------------------------------------------------------- steps
    def _traverse(self, a: int, b: int):
        """Delete what the perp traded through in rows [a, b): long-liq buckets at or above the lowest low, short-liq at or below the highest high."""
        if b <= a:
            return
        lo = self._lmin[a:b].min()
        hi = self._hmax[a:b].max()
        if np.isfinite(lo):
            i0 = int(np.searchsorted(self.bp, lo, 'left'))
            if i0 < self.nb:
                self.long[i0:] = 0.0
                self.glong[i0:] += 1
        if np.isfinite(hi):
            i1 = int(np.searchsorted(self.bp, hi, 'right'))
            if i1 > 0:
                self.short[:i1] = 0.0
                self.gshort[:i1] += 1

    def _expire(self, Tk: int):
        r1 = int(np.searchsorted(self.led_t[:self.cnt], Tk - EXPIRE, 'right'))
        if r1 <= self.lp:
            return
        sl = slice(self.lp, r1)
        B, G, A = self.led_b[sl], self.led_g[sl], self.led_a[sl]
        for arr, gen, cols in ((self.long, self.glong, slice(0, 4)), (self.short, self.gshort, slice(4, 8))):
            b, g, a = B[:, cols].ravel(), G[:, cols].ravel(), A[:, cols].ravel()
            ok = gen[b] == g
            if ok.any():
                np.subtract.at(arr, b[ok], a[ok])
                ub = np.unique(b[ok])
                arr[ub] = np.maximum(arr[ub], 0.0)
        self.stats['expired_rows'] += r1 - self.lp
        self.lp = r1

    def _add(self, k: int, dq: float, e: int):
        """dq new contracts at snapshot k: notional dq * p, p = the perp close of the last minute before S_k (row e); the
        long / short split is the perp taker-buy share of the OI interval [S_k - 5 min, S_k)."""
        p = float(self.pp['c'][e])
        d = dq * p
        a = max(0, _ceil_div(int(self.Ss[k]) - SNAP - self.t0, MIN))
        sv = float(self.pp['v'][a:e + 1].sum())
        f = float(self.pp['tb'][a:e + 1].sum()) / sv if sv > 0 else 0.5
        f = min(1.0, max(0.0, f))
        lb = self.bidx(p * self.mult_long)
        sb = self.bidx(p * self.mult_short)
        al = d * f * self.w / self.S
        as_ = d * (1 - f) * self.w / self.S
        self.long[lb] += al
        self.short[sb] += as_
        r = self.cnt
        self.led_t[r] = self.T[k]
        self.led_b[r, :4], self.led_b[r, 4:] = lb, sb
        self.led_g[r, :4], self.led_g[r, 4:] = self.glong[lb], self.gshort[sb]
        self.led_a[r, :4], self.led_a[r, 4:] = al, as_
        self.cnt += 1
        self.stats['steps_add'] += 1

    def _scale(self, factor: float):
        self.S *= factor
        self.stats['steps_scale'] += 1
        if self.S < RENORM:
            s = self.S
            self.long *= s
            self.short *= s
            self.led_a[self.lp:self.cnt] *= s
            self.S = 1.0
            self.stats['renorms'] += 1

    # ------------------------------------------------------------------------------------------------- readings
    def rows_of(self, k: int):
        """Minute rows decided at a close in [T_k, min(T_(k+1), T_k + CARRY)]: the rows that read snapshot k's state."""
        K = len(self.T)
        r0 = max(0, _ceil_div(int(self.T[k]) - self.t0, MIN) - 1)
        r1 = (int(self.T[k]) + CARRY - self.t0) // MIN          # exclusive: rows i < r1 close at or before T_k + CARRY
        if k + 1 < K:
            r1 = min(r1, max(0, _ceil_div(int(self.T[k + 1]) - self.t0, MIN) - 1))
        return r0, min(r1, self.n)

    def _readings(self, k: int):
        r0, r1 = self.rows_of(k)
        if r1 <= r0 or not np.isfinite(self.val[k]):
            return
        P = np.asarray(self.pp['c'][r0:r1], float)
        ok = np.isfinite(P) & (P > 0)
        lg, sh = self.actual()
        thr = CLUSTER_SHARE * self.val[k]
        isl, iss = np.flatnonzero(lg >= thr), np.flatnonzero(sh >= thr)
        st = self.stats
        st['blocks'] += 1
        st['blocks_with_short_cluster'] += int(len(iss) > 0)
        st['blocks_with_long_cluster'] += int(len(isl) > 0)
        st['sum_short_clusters'] += int(len(iss))
        st['sum_long_clusters'] += int(len(isl))
        if k % 50 == 0:
            self._shares.append(float(max(lg.max(), sh.max()) / self.val[k]))
        Pq = np.where(ok, P, 1.0)
        # what the price traded through in rows [end_k, i] (after the last traverse) is gone already at row i
        a = min(max(0, int(self.end[k])), r0)
        Pd = np.minimum(Pq, np.minimum.accumulate(self._lmin[a:r1])[r0 - a:])
        Pu = np.maximum(Pq, np.maximum.accumulate(self._hmax[a:r1])[r0 - a:])
        up = np.full(len(P), np.nan)
        dn = np.full(len(P), np.nan)
        if len(iss):
            cp = self.bp[iss]
            pos = np.searchsorted(cp, Pu, 'right')
            up = np.where(pos < len(cp), (cp[np.minimum(pos, len(cp) - 1)] - Pq) / Pq * 1e4, np.nan)
        if len(isl):
            cp = self.bp[isl]
            pos = np.searchsorted(cp, Pd, 'left') - 1
            dn = np.where(pos >= 0, (Pq - cp[np.maximum(pos, 0)]) / Pq * 1e4, np.nan)
        cs_s = np.r_[0.0, np.cumsum(sh)]
        cs_l = np.r_[0.0, np.cumsum(lg)]
        s_up = np.maximum(cs_s[np.searchsorted(self.bp, Pq * (1 + SKEW_BAND), 'right')] - cs_s[np.searchsorted(self.bp, Pu, 'right')], 0.0)
        s_dn = np.maximum(cs_l[np.searchsorted(self.bp, Pd, 'left')] - cs_l[np.searchsorted(self.bp, Pq * (1 - SKEW_BAND), 'left')], 0.0)
        e = SKEW_EPS * self.val[k]
        sk = np.log((s_up + e) / (s_dn + e))
        self.dist_up[r0:r1] = np.where(ok, up, np.nan)
        self.dist_dn[r0:r1] = np.where(ok, dn, np.nan)
        self.skew[r0:r1] = np.where(ok, sk, np.nan)

    # ------------------------------------------------------------------------------------------------------ run
    def run(self):
        pp, t0, n = self.pp, self.t0, self.n
        self._lmin = np.where(np.isfinite(pp['l']), pp['l'], np.inf)
        self._hmax = np.where(np.isfinite(pp['h']), pp['h'], -np.inf)
        K = len(self.T)
        end = self.end
        for k in range(K):
            Tk = int(self.T[k])
            if (Tk - t0) // MIN - 1 >= n:
                break                                # nothing of the grid is left to decide
            base_only = k == 0 or int(self.ts[k] - self.ts[k - 1]) > GAP_MAX
            if k > 0:                                # the price of [S_(k-1), S_k) is known long before T_k
                self._traverse(max(0, _ceil_div(int(self.Ss[k - 1]) - t0, MIN)), int(min(n, end[k])))
            self._expire(Tk)
            e = int(end[k]) - 1
            if base_only:
                if k > 0:
                    self.stats['steps_skipped_gap'] += 1
            else:
                dq = float(self.q[k] - self.q[k - 1])
                if dq > 0 and 0 <= e < n and np.isfinite(pp['c'][e]):
                    self._add(k, dq, e)
                elif dq < 0:
                    self._scale(min(1.0, max(0.0, 1.0 + dq / float(self.q[k - 1]))))
            self._readings(k)
            if self.hook is not None:
                self.hook(k, self)
        if self._shares:
            sh = np.array(self._shares)
            self.stats.update({'bucket_share_of_oi_max': float(sh.max()), 'bucket_share_of_oi_p99': float(np.quantile(sh, 0.99)),
                               'bucket_share_of_oi_median': float(np.median(sh)), 'bucket_share_samples': int(len(sh))})
        return self


# --------------------------------------------------------------------------------------------------------- readings
def zone(name: str, x, a_hi: int, family: str, edges=None, t0: int = None):
    """A five-zone value reading: edges at heat.ZONE_Q of the finite values of A's rows (row < a_hi) unless given, codes
    from heat.bucket. (reading, edges), or (None, None) when A holds fewer than MIN_A values (on fewer than MIN_A_DAYS distinct
    days when t0, the grid start, is given) or the inner zones would be empty (the engine's rule). 'cond': the reading is also a
    pair condition (new x new pairs)."""
    x = np.asarray(x, float)
    if edges is None:
        xa = x[:a_hi]
        fin = np.isfinite(xa)
        xa = xa[fin]
        if len(xa) < MIN_A:
            return None, None
        if t0 is not None and len(np.unique((int(t0) + np.flatnonzero(fin) * MIN) // DAY)) < MIN_A_DAYS:
            return None, None
        zq = np.quantile(xa, heat.ZONE_Q)
        if not zq[1] < zq[2]:
            return None, None
        edges = [float(q) for q in zq]
    R = {'name': name, 'k': 1, 'codes': heat.bucket(x, edges), 'levels': heat.ZONES, 'base': name, 'type': 'xd', 'zones': True,
         'family': family, 'edges': [float(e) for e in edges], 'cond': True}
    return R, R['edges']


def xd_values(sp: dict, pp: dict, oi: pd.DataFrame, model_hook=None) -> dict:
    """Every value series (per minute row; NaN where there is no reading yet) before the stale rule and the zones.
    sp: the spot bars {c, v, tb, gap, tick, n, t0}; pp: the perp bars on the same grid (perp_on_grid, or twin_perp of it)."""
    gapc = np.asarray(sp['gap'], bool) | np.asarray(pp['gap'], bool)
    nanm = lambda a: np.where(gapc, np.nan, np.asarray(a, float))
    fs = nanm(2 * np.asarray(sp['tb'], float) - np.asarray(sp['v'], float))
    vs = nanm(sp['v'])
    fp = nanm(2 * np.asarray(pp['tb'], float) - np.asarray(pp['v'], float))
    vp = nanm(pp['v'])
    mc15 = _min_count(15)
    sum_fs, _ = roll_sum(fs, 15, mc15)
    sum_vs, _ = roll_sum(vs, 15, mc15)
    sum_fp, _ = roll_sum(fp, 15, mc15)
    sum_vp, _ = roll_sum(vp, 15, mc15)
    sum_tbs, _ = roll_sum(nanm(sp['tb']), 15, mc15)
    net_s, net_p = _ratio(sum_fs, sum_vs), _ratio(sum_fp, sum_vp)
    vals = {'CVDP:Div15': net_p - net_s, 'CVDP:15': net_p, 'REF:FlowTB15': _ratio(sum_tbs, sum_vs)}
    # absorption: 60-minute perp net taker flow against the sd of that flow over the 1,440 minutes ending one minute earlier
    net60, _ = roll_sum(fp, 60, _min_count(60))
    sd = lag(roll_sd(net60, SD_WIN, _min_count(SD_WIN)), 1)
    with np.errstate(invalid='ignore', divide='ignore'):
        z60 = np.where(sd > 0, net60 / sd, np.nan)
    cp = np.where(gapc, np.nan, np.asarray(pp['c'], float))
    with np.errstate(invalid='ignore', divide='ignore'):
        lc = np.log(cp)
        r60 = (lc - lag(lc, 60)) * 1e4
    dead = heat.TICK_DEAD * np.asarray(sp['tick'], float)
    with np.errstate(invalid='ignore'):
        disagree = (np.sign(z60) != np.sign(r60)) & (np.abs(r60) > dead)
    vals['CVDP:PxDiv60'] = np.where(np.isfinite(z60) & np.isfinite(r60), np.where(disagree, z60, 0.0), np.nan)
    # the liquidation-map model
    mdl = LiqModel(pp, oi, hook=model_hook).run()
    with np.errstate(invalid='ignore', divide='ignore'):
        ret = (lc - lag(lc, 1)) * 1e4
    rv60 = np.sqrt(roll_sum(ret ** 2, 60, _min_count(60))[0])
    rv60 = np.where(rv60 > 0, rv60, np.nan)
    vals['LIQMAP:DistAbove'] = mdl.dist_up / rv60
    vals['LIQMAP:DistBelow'] = mdl.dist_dn / rv60
    vals['LIQMAP:Skew'] = mdl.skew
    return {'values': vals, 'gap': gapc, 'model': mdl.stats, 'rv60': rv60, 'dist_bps': {'up': mdl.dist_up, 'dn': mdl.dist_dn}}


def _recent(flag, L: int) -> np.ndarray:
    """True where flag was set in one of the last L + 1 rows (the row itself included)."""
    cs = np.r_[0, np.cumsum(np.asarray(flag, bool))]
    i = np.arange(len(cs) - 1)
    return (cs[i + 1] - cs[np.maximum(0, i - L)]) > 0


def stale_for(name: str, gapc: np.ndarray) -> np.ndarray:
    """The engine's stale rule for the reading's window W, plus (design 2.1) for CVDP:PxDiv60: after a gap run longer than an
    hour the reading is NA until its whole normalising history, 60 + 1,440 minutes, has passed."""
    if name in ('CVDP:Div15', 'CVDP:15', 'REF:FlowTB15'):
        return stale_rows(gapc, 15)
    st = stale_rows(gapc, 60)
    if name == 'CVDP:PxDiv60':
        st = st | _recent(_runlen(gapc) > 60, 60 + SD_WIN)
    return st


def xd_readings(sp: dict, pp: dict, oi: pd.DataFrame, a_hi: int, edges: dict = None, keep: bool = False, model_hook=None,
                skip=()) -> dict:
    """The five league readings. edges: fixed zone edges by name (a name without one is skipped; tests and parity), else from
    the A rows (row < a_hi); skip: names left out whatever their values (a twin follows its real coin's skips). Returns {'readings', 'edges', 'skipped', 'model', 'gap', 'values' (keep: the stale-masked value
    series, references included)}."""
    X = xd_values(sp, pp, oi, model_hook)
    gapc = X['gap']
    out = {'readings': [], 'edges': {}, 'skipped': [], 'model': X['model'], 'values': {}, 'gap': gapc}
    for name in LEAGUE + REFS:
        x = np.array(X['values'][name], float)
        x[stale_for(name, gapc)] = np.nan
        if keep:
            out['values'][name] = x
        if name not in LEAGUE:
            continue
        if name in skip:
            out['skipped'].append(name)
            continue
        e = None
        if edges is not None:
            e = edges.get(name)
            if e is None:
                out['skipped'].append(name)
                continue
        R, e = zone(name, x, a_hi, FAMILY[name], e, sp.get('t0'))
        if R is None:
            out['skipped'].append(name)
            continue
        out['readings'].append(R)
        out['edges'][name] = e
    return out


# ----------------------------------------------------------------------------------------------------------- measures
def _fin(x):
    return None if x is None or not np.isfinite(x) else float(x)


def near_duplicates(vals: dict, a_hi: int) -> dict:
    """Spearman rank correlation, on split A's rows with both values, of every pair of the two reference series and the
    league's CVDP readings."""
    from scipy.stats import spearmanr
    names = ['CVDP:Div15', 'CVDP:PxDiv60', 'CVDP:15', 'REF:FlowTB15']
    out = {}
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            x, y = vals[a][:a_hi], vals[b][:a_hi]
            ok = np.isfinite(x) & np.isfinite(y)
            out[f'{a} ~ {b}'] = {'spearman': _fin(spearmanr(x[ok], y[ok])[0]) if ok.sum() > 30 else None, 'n': int(ok.sum())}
    return out


def direction_coupling(vals: dict, close: np.ndarray, gap: np.ndarray, a_hi: int) -> dict:
    """Pearson correlation, on A rows, of each league reading's value with the PAST 5 / 15 / 60 minute return (bps) of
    the coin: how much of the reading is the move that just happened."""
    c = np.where(gap, np.nan, np.asarray(close, float))
    out = {}
    for name in LEAGUE:
        if name not in vals:
            continue
        out[name] = {}
        for H in (5, 15, 60):
            with np.errstate(invalid='ignore', divide='ignore'):
                r = (c / lag(c, H) - 1) * 1e4
            x, y = vals[name][:a_hi], r[:a_hi]
            ok = np.isfinite(x) & np.isfinite(y)
            good = ok.sum() > 30 and x[ok].std() > 0 and y[ok].std() > 0
            out[name][str(H)] = {'pearson': _fin(np.corrcoef(x[ok], y[ok])[0, 1]) if good else None, 'n': int(ok.sum())}
    return out


def reading_share(vals: dict, a_hi: int) -> dict:
    return {name: {'all': float(np.isfinite(v).mean()), 'A': float(np.isfinite(v[:a_hi]).mean()) if a_hi else None,
                   'B': float(np.isfinite(v[a_hi:]).mean()) if a_hi < len(v) else None} for name, v in vals.items()}


# ------------------------------------------------------------------------------------------- the OR-HM2 hook (research only)
# An optional adapter that lets the OR-HM2 pair scan and learner use the five league readings as extra single readings
# (families 'cvdp' and 'liqmap'). Nothing here runs unless heat_hm2 is started with --outside. It imports nothing from
# heat_xdata (the Zoner it is given is duck-typed on z.zone(...) and z.skipped), so this module works without OR-HM2.
# The readings are RESEARCH ONLY (reading dict and meta flag 'research_only'): they need a perpetual taker-flow feed and an
# open-interest feed that the bot does not have, and the Binance Vision terms (OR-XD, open gate) forbid live use of the data.
class _Skip(Exception):
    """An input the hook refuses (recorded as a reason; the readings that need it are skipped, the run goes on)."""


def _hm2_perp(perp: dict, who: str) -> dict:
    """HM2's on-grid perp minutes (heat_xdata.on_grid: o, h, l, c, v, tb, gap, first; NaN v / tb before the first row; on a
    twin already joint-flipped) in the convention of perp_on_grid (zero v / tb before the first row; the gap mask, the
    forward-filled prices and the zero volume on gap minutes are the same in both). _Skip when a column is missing: no
    taker-buy column means no CVDP and no long / short split, and nothing is guessed."""
    if perp is None:
        raise _Skip(f'{who}: no perp minutes')
    n = int(perp['n'])
    for x in ('o', 'h', 'l', 'c', 'v', 'tb', 'gap'):
        if perp.get(x) is None:
            raise _Skip(f'{who}: the perp has no {"taker-buy volume (tb)" if x == "tb" else x}')
        if len(perp[x]) != n:
            raise _Skip(f'{who}: the perp column {x} is not on the grid')
    out = {'t0': int(perp['t0']), 'n': n, 'gap': np.array(perp['gap'], bool), 'first': int(perp.get('first', 0)), 'bad_rows': 0,
           'off_grid': int(perp.get('off_grid', 0))}
    for x in ('o', 'h', 'l', 'c'):
        out[x] = np.array(perp[x], float)
    for x in ('v', 'tb'):
        a = np.array(perp[x], float)
        out[x] = np.where(np.isfinite(a), a, 0.0)
    live = ~out['gap'] & (out['v'] > 0)
    if live.any() and not (out['tb'][live] != 0).any():
        raise _Skip(f'{who}: the perp taker-buy volume is zero on every bar with volume (an empty tb column)')
    return out


def _mark_tb_gaps(pp: dict, rows: np.ndarray) -> dict:
    """Minutes whose perp bar has volume but an EMPTY tb cell are broken bars (heat_outside.perp_on_grid's rule), made exactly as the
    standalone run makes them: the gap mask is set, v / tb are zeroed, and the bar's own prices are replaced by the last close of
    a GOOD bar before it (o = h = l = c, chained across consecutive marked rows and over the minutes missing from the file; NaN
    before the first good bar, where `first` moves up to). LiqModel reads h / l / c on every row, gap rows included, so leaving
    the marked bar's own prices in place would move its traversal and its buckets."""
    rows = np.unique(np.asarray(rows, np.int64))
    if not len(rows):
        return pp
    out = dict(pp)
    good = ~np.asarray(pp['gap'], bool)
    good[rows] = False
    c = pd.Series(np.where(good, np.asarray(pp['c'], float), np.nan)).ffill().to_numpy()
    for x in ('o', 'h', 'l', 'c'):
        a = c.copy()
        a[good] = np.asarray(pp[x], float)[good]
        out[x] = a
    out['gap'] = ~good
    out['first'] = int(np.argmax(good)) if good.any() else int(pp['n'])
    out['v'], out['tb'] = np.array(pp['v'], float), np.array(pp['tb'], float)
    out['v'][rows] = 0.0
    out['tb'][rows] = 0.0
    return out


def hm2_outside_readings(m, perp, oi, a_hi, z, log=print, info=None, real=None, perp_frame=None, twin=None, seed=None) -> list:
    """The five league readings of OR-XD (CVDP:Div15, CVDP:PxDiv60, LIQMAP:DistAbove, LIQMAP:DistBelow, LIQMAP:Skew) as extra
    single readings for OR-HM2, registered through z.zone (families 'cvdp' and 'liqmap'). Returns the readings registered.

    m: the job coin's minutes (heat.load_minutes; heat.make_twin on a twin). perp: the REAL perp on m's grid as HM2 holds it
    (heat_xdata.on_grid). On a twin the pre-registered OR-XD twin rule is used, NOT HM2's joint-flipped perp: the perp path is the
    twin SPOT o / h / l / c times the REAL perp / spot close ratio of the same minute (the real basis is kept; twin_perp) and its
    taker-buy volume is flipped with the same coin flips as the spot (twin_signs(n, seed), which are heat.make_twin's and HM2's
    joint-flip signs), so the chance scale of these five readings is the one OR-XD froze. The joint-flipped perp (its basis
    random-walks) is ignored. oi: the open-interest rows (ts, oi, oi_usd), ALL of them: HM2 passes the raw file rows, because
    clean_oi must see the duplicates of one stamp to pick the row whose implied price is closest to the perp (a frame that
    heat_xdata.load_extra has already reduced to the first row of each stamp works but picks differently). A 'known' column is
    ignored: the OR-XD clock is used (each stamp ceiled to the 5-minute grid, snapshot instant S = ts + 5 minutes, known at
    ts + 10 minutes; LiqModel). OI stays REAL on a twin and the model is driven by its CONTRACTS. a_hi: split A's end row. z:
    duck-typed on z.zone(name, x, stale=, family=) and z.skipped (a list; a name skipped here is appended); z.fixed (the stored
    edges of a live / parity call) when it has one: then no A rows are looked at.

    real: {'m': real minutes, 'perp': real perp on the grid} (HM2's extra_readings argument; required on a twin, where it replaces
    m and perp as the inputs of the guards and of the OI row pick). The input guards (the perp on the spot's clock, the OI clock)
    and the OI row pick read the REAL spot and perp, as the standalone run does. seed: the twin's seed (a twin is a call with a
    seed; ValueError when a twin has none). perp_frame: the load_extra frame of the real perp file (optional): the rows with
    volume but an empty tb are broken bars (gaps with the last close carried forward, as perp_on_grid makes them) and a file with
    more than MISSING_TB_MAX of them is refused (on_grid has already turned an empty cell into 0). twin: True / False, else
    a twin when a seed is given.

    Nothing is guessed and nothing stops the run: an input that is missing or fails a guard skips the readings that need it with a
    recorded reason (the perp: all five; the OI: the three LIQMAP readings). A name is skipped as heat_outside.zone does (fewer than
    MIN_A values or values on fewer than MIN_A_DAYS days of A, empty inner zones), a twin follows its real coin's skips, and the
    constants are the frozen ones. info (out): readings, skipped {name: reason}, refused {input: reason}, edges, model,
    near_duplicates, direction_coupling, reading_share, constants, xd_input."""
    want = info is not None                     # the measures below cost a few Spearman correlations: only for a caller that reads them
    info = info if want else {}
    za = getattr(z, 'a_hi', None)
    if za is not None and int(za) != int(a_hi):
        raise ValueError(f'a_hi {a_hi} differs from the Zoner\'s {za}')
    fixed = getattr(z, 'fixed', None)
    real = real or {}
    real_m = real.get('m') or m
    if twin is None:
        twin = seed is not None
    if twin and (seed is None or real.get('m') is None or real.get('perp') is None):
        raise ValueError('a twin needs its seed and the real minutes and real perp (the OR-XD twin rule builds the perp path from the twin spot and the real perp)')
    real_perp = real['perp'] if twin else perp                  # the REAL perp; on a twin the perp argument (HM2's joint-flipped one) is not used
    refused, reasons, out = {}, {}, []
    info.update(readings=[], skipped=reasons, refused=refused, twin=bool(twin), constants=CONSTANTS)

    def skip(name, why):
        reasons[name] = why
        sk = getattr(z, 'skipped', None)
        if sk is not None and name not in sk:
            sk.append(name)

    def done():
        info['readings'] = [R['name'] for R in out]
        return out

    # ---- the perp: all five readings need its bars and its taker-buy volume
    try:
        pg = _hm2_perp(real_perp, 'real perp' if twin else 'perp')          # the REAL perp: the guards and the OI row pick read it, and a twin is built from it
        if (pg['t0'], pg['n']) != (int(m['t0']), int(m['n'])):
            raise _Skip('the perp is not on the job coin\'s grid')
        tbm = None
        if perp_frame is not None:
            if not {'v', 'tb'} <= set(perp_frame.columns):
                raise _Skip('the perp file has no taker-buy volume column (tb)')
            nbad = missing_tb(perp_frame)
            tbm = {'perp_rows': int(len(perp_frame)), 'perp_missing_tb': nbad}
            if nbad > MISSING_TB_MAX * max(1, len(perp_frame)):
                raise _Skip(f'perp file: {nbad:,} of {len(perp_frame):,} rows have volume but an empty tb (refused above {100 * MISSING_TB_MAX:.1f}%)')
            bad = ((pd.to_numeric(perp_frame['v'], errors='coerce') > 0) & pd.to_numeric(perp_frame['tb'], errors='coerce').isna()).to_numpy()
            off = perp_frame['ts'].to_numpy(np.int64)[bad] - int(m['t0'])
            off = off[off % MIN == 0]                                      # (an off-grid stamp is no row of the grid)
            rows = off // MIN
            rows = rows[(rows >= 0) & (rows < int(m['n']))].astype(np.int64)
            pg = _mark_tb_gaps(pg, rows)
        align = check_alignment(real_m, pg)
        if twin:                                                           # OR-XD twin rule: twin spot x the real perp / spot ratio, tb flipped with the spot's signs
            pp = twin_perp(pg, real_m, m, twin_signs(int(m['n']), int(seed)))
        else:
            pp = pg
    except _Skip as e:
        refused['perp'] = str(e)
    except SystemExit as e:
        refused['perp'] = f'perp/spot clock guard: {e}'
    if 'perp' in refused:
        for name in LEAGUE:
            skip(name, 'refused: ' + refused['perp'])
        log(f'  XD hook: refused, no readings ({refused["perp"]})')
        return done()
    # ---- the OI: the three LIQMAP readings need it (CVDP does not)
    oi_df, oi_info, oi_clock, liq_why = None, {}, None, None
    if oi is None:
        liq_why = 'no open-interest frame'
    elif not {'ts', 'oi'} <= set(oi.columns):
        liq_why = 'the open-interest frame lacks ts / oi'
    elif 'oi_usd' not in oi.columns:
        liq_why = 'oi_usd is missing (the clean step, the duplicate pick and the OI clock guard need it)'
    elif len(oi) and int(np.max(oi['ts'].to_numpy(np.int64))) >= HEAT_END:
        liq_why = f'an OI row at or after {pd.Timestamp(HEAT_END, unit="ms")}'
    else:
        oi_df, oi_info = clean_oi(oi[['ts', 'oi', 'oi_usd']], pg)
        if not len(oi_df):
            liq_why = 'no usable OI row (a finite positive oi and oi_usd)'
        else:
            try:
                oi_clock = check_oi_clock(oi_df, pg)
            except SystemExit as e:
                liq_why = f'OI clock guard: {e}'
    if liq_why:
        refused['oi'] = liq_why
    model_oi = oi_df if not liq_why else pd.DataFrame({'ts': np.zeros(0, np.int64), 'oi': np.zeros(0), 'oi_usd': np.zeros(0)})
    # ---- the values, the stale rule, the zones
    X = xd_values(m, pp, model_oi)
    gapc = X['gap']
    vals, stale = {}, {}
    for name in LEAGUE + REFS:
        stale[name] = stale_for(name, gapc)
        x = np.array(X['values'][name], float)
        x[stale[name]] = np.nan
        vals[name] = x
    inherited = set()
    if twin and fixed is None:                  # a twin follows its real coin: a reading skipped for the real coin is skipped for its twins
        inherited = set(xd_readings(real_m, pg, model_oi, a_hi)['skipped'])
    t0 = m.get('t0')
    for name in LEAGUE:
        if liq_why and FAMILY[name] == 'LIQMAP':
            skip(name, 'refused: ' + liq_why)
            continue
        if name in inherited:
            skip(name, 'skipped for the real coin, so for its twins (OR-XD twin rule)')
            continue
        if fixed is None:                       # heat_outside.zone's rule: MIN_A values on at least MIN_A_DAYS days of A (z.zone enforces the first)
            fin = np.isfinite(vals[name][:a_hi])
            if int(fin.sum()) < MIN_A:
                skip(name, f'fewer than {MIN_A:,} finite values on A ({int(fin.sum()):,})')
                continue
            nd = len(np.unique((int(t0) + np.flatnonzero(fin) * MIN) // DAY))
            if nd < MIN_A_DAYS:
                skip(name, f'values on {nd} distinct days of A, fewer than {MIN_A_DAYS}')
                continue
        R = z.zone(name, X['values'][name], stale=stale[name], family=FAMILY[name].lower())
        if R is None:
            reasons[name] = 'no stored edge' if fixed is not None else 'the inner zones are empty (edges collapse)'
            continue
        R['research_only'] = True
        out.append(R)
    sk = X['model']
    log(f'  XD hook: {len(out)} readings {[R["name"] for R in out]}, skipped {reasons}; {sk["snapshots"]:,} OI snapshots ({sk["steps_add"]:,} adds, '
        f'{sk["steps_scale"]:,} scales); research only')
    # ---- what was measured (information only)
    if not want:
        return done()
    mdl = dict(X['model'])
    if oi_df is not None and len(oi_df):
        mdl.update(oi_rows=int(len(oi_df)), oi_first=str(pd.Timestamp(int(oi_df['ts'].iloc[0]), unit='ms')),
                   oi_last=str(pd.Timestamp(int(oi_df['ts'].iloc[-1]), unit='ms')))
    info['model'] = mdl
    try:
        info['near_duplicates'] = near_duplicates(vals, a_hi)
    except ImportError:
        info['near_duplicates'] = None
    info['direction_coupling'] = direction_coupling(vals, m['c'], gapc, a_hi)
    info['reading_share'] = reading_share(vals, a_hi)
    info['edges'] = {R['name']: list(R['edges']) for R in out}
    info['xd_input'] = {'perp_first_row': int(pg['first']), 'perp_gaps': int(pg['gap'].sum()), 'spot_gaps': int(np.asarray(m['gap']).sum()),
                        'either_gap': int(gapc.sum()), 'twin': bool(twin), 'twin_seed': None if seed is None else int(seed),
                        'twin_rule': 'OR-XD: twin spot x the real perp / spot close ratio, tb flipped with the spot\'s signs' if twin else None,
                        'perp_lag_min': 0, 'perp_spot_alignment': align, 'oi_clock': oi_clock,
                        'oi_frame_rows': None if oi is None else int(len(oi)), 'oi_known_rule': 'ts ceiled to 5 minutes + 10 minutes (the frame\'s own known column is not used)',
                        'edges_from': 'the stored edges of the Zoner' if fixed is not None else f'quantiles {list(heat.ZONE_Q)} of the {a_hi:,} rows of split A',
                        **({} if tbm is None else tbm), **oi_info}
    return done()


# -------------------------------------------------------------------------------------------------------------- runner
class _Ctx:
    seed = None
    real = None
    extras = None


def missing_tb(df: pd.DataFrame) -> int:
    """Rows with volume but an EMPTY taker-buy cell (the history writer emits '' for a bar with no taker-buy volume)."""
    v, tb = pd.to_numeric(df['v'], errors='coerce'), pd.to_numeric(df['tb'], errors='coerce')
    return int(((v > 0) & tb.isna()).sum())


def run_coin_outside(asset: str, spot_csv: str, perp_csv: str, oi_csv: str, out: str, twin: int = 0, procs: int = 0, log=print,
                     end: int = heat.HEAT_END, perp_lag: int = 0) -> dict:
    """heat.run_coin with the OR-XD readings in place of OR-HM1's vocabulary (see the module doc). perp_lag: minutes by which
    every perp input is seen late (0 in this archive-only pass; 1 and 5 for the robustness reruns). Returns meta.json's dict."""
    _no_doge(asset, spot_csv, perp_csv, oi_csv, out)
    if perp_lag < 0:
        raise SystemExit('perp_lag must be >= 0')
    spot_df = read_checked(spot_csv, ('ts', 'o', 'h', 'l', 'c', 'v', 'tb'), 'spot')          # refusals first (heat.load_minutes reads it itself)
    perp_df = read_checked(perp_csv, ('ts', 'o', 'h', 'l', 'c', 'v', 'tb'), 'perp')
    oi_raw = read_checked(oi_csv, ('ts', 'oi', 'oi_usd'), 'OI')
    miss = {'spot_missing_tb': missing_tb(spot_df), 'perp_missing_tb': missing_tb(perp_df)}
    for nm, df in (('spot', spot_df), ('perp', perp_df)):
        if miss[f'{nm}_missing_tb'] > MISSING_TB_MAX * max(1, len(df)):
            raise SystemExit(f'{nm} file: {miss[nm + "_missing_tb"]:,} of {len(df):,} rows have volume but an empty tb (taker-buy); refused above {100 * MISSING_TB_MAX:.1f}%')
    miss['spot_rows'], miss['perp_rows'] = int(len(spot_df)), int(len(perp_df))
    del spot_df
    ctx = _Ctx()
    ctx.extras = {}
    orig_build, orig_twin = heat.build_readings, heat.make_twin

    def make_twin(m, seed):
        ctx.seed, ctx.real = int(seed), m
        return orig_twin(m, seed)

    def build(m, g, dom, log=print):
        t = time.time()
        real = ctx.real if ctx.seed is not None else m
        pg = perp_on_grid(real, perp_df)                      # the REAL perp bars at lag 0
        align = check_alignment(real, pg)
        oi_df, oi_info = clean_oi(oi_raw, pg)
        oi_clock = check_oi_clock(oi_df, pg)
        a_hi = g.sp['A'].hi
        skip = set()
        if ctx.seed is None:
            pp = lag_perp(pg, perp_lag)
        else:
            # the twin follows its real coin: a reading skipped for the real coin is skipped for the twin (same families)
            skip = set(xd_readings(real, lag_perp(pg, perp_lag), oi_df, a_hi)['skipped'])
            pp = lag_perp(twin_perp(pg, real, m, twin_signs(m['n'], ctx.seed)), perp_lag)
        res = xd_readings(m, pp, oi_df, a_hi, keep=True, skip=skip)
        vals = res['values']
        ctx.extras = {
            'near_duplicates': near_duplicates(vals, a_hi),
            'direction_coupling': direction_coupling(vals, m['c'], res['gap'], a_hi),
            'reading_share': reading_share(vals, a_hi),
            'constants': CONSTANTS,
            'model': {**res['model'], 'oi_rows': int(len(oi_df)),
                      'oi_first': str(pd.Timestamp(int(oi_df['ts'].iloc[0]), unit='ms')) if len(oi_df) else None,
                      'oi_last': str(pd.Timestamp(int(oi_df['ts'].iloc[-1]), unit='ms')) if len(oi_df) else None},
            'xd_input': {'perp_first_row': int(pg['first']), 'perp_gaps': int(pg['gap'].sum()), 'perp_bad_rows': pg['bad_rows'],
                         'perp_off_grid_rows': pg['off_grid'], 'spot_gaps': int(m['gap'].sum()), 'either_gap': int(res['gap'].sum()),
                         'twin_seed': ctx.seed, 'perp_lag_min': int(perp_lag), 'perp_spot_alignment': align, 'oi_clock': oi_clock,
                         **oi_info, **miss},
            'skipped_readings': res['skipped'],
            'skipped_inherited_from_real_coin': sorted(skip),
        }
        sk = res['model']
        log(f'  XD: {len(res["readings"])} readings {[r["name"] for r in res["readings"]]}, skipped {res["skipped"]}; '
            f'{sk["snapshots"]:,} OI snapshots ({sk["steps_add"]:,} adds, {sk["steps_scale"]:,} scales, {sk["steps_skipped_gap"]:,} gap steps, '
            f'{sk["renorms"]} renorms); blocks with a short / long cluster: {sk["blocks_with_short_cluster"]:,} / {sk["blocks_with_long_cluster"]:,} '
            f'of {sk["blocks"]:,}; largest bucket share of OI {100 * sk.get("bucket_share_of_oi_max", float("nan")):.2f}% '
            f'(p99 {100 * sk.get("bucket_share_of_oi_p99", float("nan")):.2f}%); {time.time() - t:.0f}s')
        log(f'  XD: perp/spot alignment r(-1,0,+1) = {align["r_m1"]}, {align["r_0"]}, {align["r_p1"]}; OI clock {oi_clock}; '
            f'OI duplicates dropped {oi_info["oi_duplicates_dropped"]}, off-grid {oi_info["oi_off_grid_rows"]}; perp lag {perp_lag} min')
        for nm, sh in ctx.extras['reading_share'].items():
            log(f'  XD: {nm}: a value on {100 * sh["all"]:.1f}% of rows')
        return res['readings'], heat.Rows(), res['edges'], [], None

    heat.build_readings, heat.make_twin = build, make_twin
    try:
        meta = heat.run_coin(asset, spot_csv, '', out, end=end, twin=twin, procs=procs, log=log)
    finally:
        heat.build_readings, heat.make_twin = orig_build, orig_twin
    meta.update(ctx.extras)
    meta['study'] = 'OR-XD lite'
    with open(os.path.join(out, 'meta.json'), 'w') as f:
        json.dump(meta, f, indent=1)
    return meta


def main(argv=None):
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest='cmd', required=True)
    a = sp.add_parser('coin')
    a.add_argument('--asset', required=True)
    a.add_argument('--spot', required=True)
    a.add_argument('--perp', required=True)
    a.add_argument('--oi', required=True)
    a.add_argument('--out', required=True)
    a.add_argument('--twin', type=int, default=0)
    a.add_argument('--procs', type=int, default=0)
    a.add_argument('--perp-lag', type=int, default=0, help='minutes by which every perp input is seen late (robustness reruns: 1, 5)')
    x = ap.parse_args(argv)
    mt = run_coin_outside(x.asset, x.spot, x.perp, x.oi, x.out, twin=x.twin, procs=x.procs, perp_lag=x.perp_lag)
    print(json.dumps({k: v for k, v in mt.items() if k not in ('base', 'edges', 'reading_share')}, indent=1, default=str))


if __name__ == '__main__':
    main()
