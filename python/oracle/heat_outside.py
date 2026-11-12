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

OR-XD FULL (Amendment 3 in prereg/OR-XD.md; all optional, off unless a contract file or directory is given):
  python3 -m oracle.heat_outside coin ... [--xd-dir D | --metrics F --premium F --premium-stamp F --mark F --funding F --agg-spot-dir D --agg-perp-dir D --book F]
  python3 -m oracle.heat_outside cut --dir D        (drop every row at/after HEAT_END from a raw/outside/binance/<COIN> folder)
Thirteen NEW league readings from the DATA CONTRACT files (raw/outside/binance/<COIN>/), computed by full_values / full_readings:
  LS:Global z  LS:TopPos z  LS:TopPosChg60  LS:TopAcc z        metrics (known at S + 5 min, carried 10 min), real level
  PREM:PredFund  PREM:PredMinusLast                            premium_1m + premium_stamp.json + funding, real level
  WHALE:Net15  WHALE:Count60  WHALE:Sweep   (spot)             agg_spot/<YYYY-MM>.parquet; Net15 and Sweep are DIRECTION readings
  WHALEP:Net15 WHALEP:Count60 WHALEP:Sweep  (perp)             agg_perp/...; on a twin buy and sell swap on the flipped minutes
  BOOKP:Imb1                                                    bookdepth_1pct, real level
plus the information-only references REF:Sweep500 / REFP:Sweep500 ($500k sweep state; never in the league). Every new reading is a pair
condition, so the engine's pair scan runs every reading against every other (new x new, new x lite). A reading whose input is missing is
skipped with a recorded reason (meta xd_full.skipped_reasons); a row at or after HEAT_END is refused. The five lite readings above are untouched.

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
import warnings

import numpy as np
import pandas as pd

from oracle import heat
from oracle.common import DAY, MIN, ms

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


def _check_frame(df: pd.DataFrame, cols: tuple, kind: str, label: str, tcol: str = 'ts') -> pd.DataFrame:
    """The checks of read_checked on a frame: columns present, a numeric tcol in ms of 13 digits, no row at or after HEAT_END."""
    miss = [c for c in cols if c not in df.columns]
    if miss:
        raise SystemExit(f'{label}: {kind} file lacks column(s) {miss}')
    ts = pd.to_numeric(df[tcol], errors='coerce')
    if ts.isna().any():
        raise SystemExit(f'{label}: {int(ts.isna().sum()):,} rows with no numeric {tcol}')
    ts = ts.to_numpy(np.int64)
    if len(ts) and not ((ts >= 10 ** 12) & (ts < 10 ** 13)).all():
        raise SystemExit(f'{label}: {tcol} must be milliseconds of 13 digits (this one holds {len(str(int(ts[0])))} digits at row 1)')
    late = int((ts >= HEAT_END).sum())
    if late:
        raise SystemExit(f'{label}: {late:,} rows at or after {pd.Timestamp(HEAT_END, unit="ms")}: the heat tables stop there; cut the file first')
    df = df.copy()
    df[tcol] = ts
    return df


def read_checked(path: str, cols: tuple, kind: str, tcol: str = 'ts') -> pd.DataFrame:
    """A CSV with tcol ('ts') in ms of 13 digits (a seconds or microseconds stamp is refused) and no row at or after
    HEAT_END (strict, as heat.load_minutes: the workflow cuts the file first)."""
    _no_doge(path)
    return _check_frame(pd.read_csv(path), cols, kind, path, tcol)


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


def direction_coupling(vals: dict, close: np.ndarray, gap: np.ndarray, a_hi: int, names=None) -> dict:
    """Pearson correlation, on A rows, of each league reading's value with the PAST 5 / 15 / 60 minute return (bps) of
    the coin: how much of the reading is the move that just happened."""
    c = np.where(gap, np.nan, np.asarray(close, float))
    out = {}
    for name in (LEAGUE if names is None else names):
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


# ======================================================================================================================
# OR-XD full (Amendment 3): readings from the DATA CONTRACT files only (raw/outside/binance/<COIN>/): Binance metrics (LS),
# premium index + funding (PREM), spot / perp aggTrade reducers (WHALE, WHALEP), perp bookDepth (BOOKP). The five lite
# readings above are unchanged. Every value is used at row i only when its known time is at or before the close of row i
# (the decision time; the entry is the next minute's open); a rolling window is by time with >= 80% presence.
# ======================================================================================================================
HOUR = 60 * MIN
FULL_LEAGUE = ['LS:Global z', 'LS:TopPos z', 'LS:TopPosChg60', 'LS:TopAcc z', 'PREM:PredFund', 'PREM:PredMinusLast',
               'WHALE:Net15', 'WHALE:Count60', 'WHALE:Sweep', 'WHALEP:Net15', 'WHALEP:Count60', 'WHALEP:Sweep', 'BOOKP:Imb1']
FULL_REFS = ['REF:Sweep500', 'REFP:Sweep500']          # the $500k sweep state: information only, never chosen, never in the league
FULL_FAMILY = {'LS:Global z': 'LS', 'LS:TopPos z': 'LS', 'LS:TopPosChg60': 'LS', 'LS:TopAcc z': 'LS', 'PREM:PredFund': 'PREM',
               'PREM:PredMinusLast': 'PREM', 'WHALE:Net15': 'WHALE', 'WHALE:Count60': 'WHALE', 'WHALE:Sweep': 'WHALE',
               'WHALEP:Net15': 'WHALEP', 'WHALEP:Count60': 'WHALEP', 'WHALEP:Sweep': 'WHALEP', 'BOOKP:Imb1': 'BOOKP'}
FULL_DIRECTION = ('WHALE:Net15', 'WHALE:Sweep', 'WHALEP:Net15', 'WHALEP:Sweep', 'REF:Sweep500', 'REFP:Sweep500')   # swapped on a twin's flipped minutes
FULL_STATE = ('WHALE:Sweep', 'WHALEP:Sweep')            # three-state readings (sell sweep / none / buy sweep), not zones
SWEEP_LEVELS = ['sell sweep', 'none', 'buy sweep']
LS_KNOWN = 5 * MIN              # a metrics row's snapshot instant S (true time, after the create_time convention) is known at S + 5 min
LS_WIN = 288                    # 24 h of 5-minute snapshots: the window [S - 24 h, S)
LS_GAP_SLOTS = 12               # a gap of more than 1 hour between snapshots (more than 12 slots) blanks the next LS_WIN slots
LS_CHG = 12                     # 60 minutes of snapshots
PREM_CAP = 5e-4                 # the +-0.05% clamp of Binance's funding formula
PREM_INTEREST_8H = 1e-4         # I = 0.01% per 8 hours, scaled to the symbol's interval
PREM_SD_N = 90                  # settlements in the sd of settlement-to-settlement changes
WHALE_EDGES = [1000.0 * 20000.0 ** (k / 23) for k in range(24)]      # USD 1,000 ... 20,000,000 (the reducer's edges E_k)
WHALE_Q = 0.001                 # F = the smallest edge whose trailing share of trades at or above it is <= 0.1%
WHALE_DAYS = 30
WHALE_BASE_DAYS = 7
SWEEP_BARS = 5                  # the sweep state looks at the last 5 minutes (the row itself and 4 before)
SWEEP_MIN_A = 100               # a sweep state needs this many buy and this many sell rows on A, else it is skipped (data sufficiency, not a pass bar)
BOOK_CARRY = CARRY
FULL_CONSTANTS = {'ls_known_ms': LS_KNOWN, 'ls_carry_ms': CARRY, 'ls_window_snapshots': LS_WIN, 'ls_change_snapshots': LS_CHG,
                  'prem_cap': PREM_CAP, 'prem_interest_per_8h': PREM_INTEREST_8H, 'prem_sd_settlements': PREM_SD_N,
                  'whale_edges_usd': [round(e, 2) for e in WHALE_EDGES], 'whale_share_q': WHALE_Q, 'whale_days': WHALE_DAYS,
                  'whale_baseline_days': WHALE_BASE_DAYS, 'sweep_minutes': SWEEP_BARS, 'sweep_main_usd': 1_000_000, 'sweep_ref_usd': 500_000,
                  'sweep_min_a_rows_per_side': SWEEP_MIN_A, 'book_carry_ms': BOOK_CARRY, 'presence': PRESENCE,
                  'min_a_values': MIN_A, 'min_a_days': MIN_A_DAYS, 'zone_q': heat.ZONE_Q}


def prep_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """metrics.csv.gz (S = the TRUE snapshot instant in ms after the create_time convention, one row per S). S is ceiled to the
    5-minute grid (never earlier), a repeated S keeps its last row, sorted by S; a row at or after HEAT_END is refused."""
    d = _check_frame(df, ('S', 'count_long_short_ratio', 'sum_toptrader_long_short_ratio', 'count_toptrader_long_short_ratio'), 'metrics', 'metrics', 'S')
    d['S'] = _ceil_div(d['S'].to_numpy(np.int64), SNAP) * SNAP
    return d.sort_values('S', kind='stable').drop_duplicates('S', keep='last').reset_index(drop=True)


def prep_premium(df: pd.DataFrame, who: str = 'premium') -> pd.DataFrame:
    d = _check_frame(df, ('ts', 'c'), who, who)
    return d.sort_values('ts', kind='stable').drop_duplicates('ts', keep='last').reset_index(drop=True)


def prep_funding(df: pd.DataFrame) -> pd.DataFrame:
    """funding.csv.gz: Ts = calc_time floored to its minute (the settlement instant), rate = last_funding_rate; one row per Ts."""
    d = _check_frame(df, ('calc_time', 'last_funding_rate'), 'funding', 'funding', 'calc_time')
    d['Ts'] = d['calc_time'].to_numpy(np.int64) // MIN * MIN
    d['rate'] = pd.to_numeric(d['last_funding_rate'], errors='coerce')
    d = d.sort_values('Ts', kind='stable').drop_duplicates('Ts', keep='last')
    return d[np.isfinite(d['rate'])].reset_index(drop=True)


def prep_book(df: pd.DataFrame) -> pd.DataFrame:
    d = _check_frame(df, ('ts', 'bid_1pct', 'ask_1pct'), 'bookdepth', 'bookdepth')
    return d.sort_values('ts', kind='stable').drop_duplicates('ts', keep='last').reset_index(drop=True)


def premium_delay(stamp) -> int:
    """Extra minutes of delay from premium_stamp.json (a path or the dict): 1 when the stamp test says the NEXT minute fits
    better, 0 when the same minute does. Accepts the keys fits (the fetch job's) / fit / best / winner / result / verdict ('same' | 'next') or
    extra_delay_minutes / delay_minutes. _Skip when the file does not say (nothing is guessed)."""
    if isinstance(stamp, (str, os.PathLike)):
        _no_doge(stamp)
        with open(stamp) as f:
            stamp = json.load(f)
    if not isinstance(stamp, dict):
        raise _Skip('premium_stamp.json is not an object')
    if stamp.get('resolved') is False:
        raise _Skip('the premium stamp test did not resolve')
    for dk in ('extra_delay_minutes', 'delay_minutes'):          # extra_delay_minutes: outside_reduce.premium_stamp_test's key
        if isinstance(stamp.get(dk), (int, float)) and not isinstance(stamp.get(dk), bool):
            return 1 if stamp[dk] >= 1 else 0
    for k in ('fits', 'fit', 'best', 'winner', 'result', 'verdict'):     # fits: outside_reduce.premium_stamp_test's key
        v = stamp.get(k)
        if isinstance(v, str):
            v = v.strip().lower()
            if v.startswith('next'):
                return 1
            if v.startswith('same'):
                return 0
    raise _Skip('premium_stamp.json holds no fit (same | next)')


def _on_grid(ts, vals, t0: int, n: int):
    """vals placed at the minute rows of the grid; NaN where there is none; (array, off-grid count)."""
    ts = np.asarray(ts, np.int64)
    off = ts - t0
    on = (off >= 0) & (off % MIN == 0) & (off < n * MIN)
    out = np.full(n, np.nan)
    out[off[on] // MIN] = np.asarray(vals, float)[on]
    return out, int(((off % MIN != 0) & (off >= 0) & (off < n * MIN)).sum())


# ---------------------------------------------------------------------------------------------------------------- LS
def ls_slots(met: pd.DataFrame):
    """The three LS value series on the 5-minute snapshot slots s0 + j * 5 min (NaN where there is none), before the known-time
    mapping. x = ln(ratio); z over the 288 snapshots BEFORE the row ([S - 24 h, S): the row itself is not in its own window), >= 80%
    present; the 60-minute change needs the snapshot exactly 60 minutes earlier and is divided by the sd of the 60-minute changes
    of the previous 24 h."""
    S = met['S'].to_numpy(np.int64)
    s0 = int(S[0])
    K = int((S[-1] - s0) // SNAP) + 1
    idx = (S - s0) // SNAP
    mc = _min_count(LS_WIN)

    def x_of(col):
        v = pd.to_numeric(met[col], errors='coerce').to_numpy(float)
        x = np.full(K, np.nan)
        with np.errstate(invalid='ignore', divide='ignore'):
            x[idx] = np.where(v > 0, np.log(v), np.nan)
        return x

    def zs(x):
        s, k = roll_sum(x, LS_WIN, mc)
        with np.errstate(invalid='ignore', divide='ignore'):
            mu = lag(s / k, 1)
        sd = lag(roll_sd(x, LS_WIN, mc), 1)
        with np.errstate(invalid='ignore', divide='ignore'):
            return np.where(sd > 0, (x - mu) / sd, np.nan)

    xg, xp, xa = x_of('count_long_short_ratio'), x_of('sum_toptrader_long_short_ratio'), x_of('count_toptrader_long_short_ratio')
    d = xp - lag(xp, LS_CHG)
    sd = lag(roll_sd(d, LS_WIN, mc), 1)
    with np.errstate(invalid='ignore', divide='ignore'):
        chg = np.where(sd > 0, d / sd, np.nan)
    # design 2.1 gap rule: after a gap of more than 1 hour between snapshots the readings are NA until a whole window (288 snapshots)
    # has passed since the first snapshot after the gap
    blk = np.zeros(K, bool)
    present = np.unique(idx)
    for g in np.flatnonzero(np.diff(present) > LS_GAP_SLOTS) + 1:
        blk[present[g]:present[g] + LS_WIN] = True
    out = {'LS:Global z': zs(xg), 'LS:TopPos z': zs(xp), 'LS:TopPosChg60': chg, 'LS:TopAcc z': zs(xa)}
    return s0, {k: np.where(blk, np.nan, v) for k, v in out.items()}


def carry_rows(series, s0: int, delay: int, carry: int, t0: int, n: int, step: int = SNAP) -> np.ndarray:
    """A slot series (slot j = the instant s0 + j * step, known at that instant + delay) on the minute rows: row i takes the
    latest slot whose known time is at or before the row's CLOSE (t0 + (i + 1) min), and an earlier slot while the age (close minus
    known time) is at most `carry`; NaN beyond. A slot known exactly at the close counts; one millisecond later does not."""
    series = np.asarray(series, float)
    K = len(series)
    close = int(t0) + (np.arange(n, dtype=np.int64) + 1) * MIN
    j = (close - delay - s0) // step
    out = np.full(n, np.nan)
    for q in range(int(carry // step) + 2):
        jq = j - q
        age = close - (s0 + jq * step + delay)
        ok = (jq >= 0) & (jq < K) & (age <= carry) & np.isnan(out)
        val = series[np.clip(jq, 0, K - 1)]
        take = ok & np.isfinite(val)
        out[take] = val[take]
    return out


# -------------------------------------------------------------------------------------------------------------- PREM
def prem_series(prem: pd.DataFrame, fund: pd.DataFrame, t0: int, n: int, delay: int = 0):
    """PREM:PredFund and PREM:PredMinusLast on the minute rows, and the reconstruction error against the next settled rate.

    Row j (bar j opens at o_j, closes o_j + 1 min) sees the last settlement k with calc_time_k <= o_j (a settlement is known at its
    calc time + 1 minute, so the bar that opens at it is the first to know it) and the premium closes of the n = (o_j - Ts_k) / 1 min + 1
    bars since Ts_k (calc_time floored to its minute),
    bar p (p = 1..n) weighted p; P = sum(p * premium_p) / sum(p) over the bars present (>= 80% of n, and bar j itself present);
    I = 0.01% x N / 8 with N the interval in hours between the last two settlements; F = clamp(I, P - 0.05%, P + 0.05%) (= P + clamp(I - P, ...) but exact: in-band F is I itself).
    PredMinusLast = (F - rate_k) / sd of the settlement-to-settlement rate changes over the 90 settlements ending at k (>= 72
    changes). NaN when the settlement is more than 1.5 intervals old. delay (0 or 1 minute, premium_stamp.json) moves every
    row later by that many minutes. Old formula only: the 2025-09-18 '8/N' regime is not applied; the error of both is in info."""
    Ts = fund['Ts'].to_numpy(np.int64)
    calc = fund['calc_time'].to_numpy(np.int64)
    rate = fund['rate'].to_numpy(float)
    info = {'settlements': int(len(Ts)), 'delay_min': int(delay)}
    nan = np.full(n, np.nan)
    if len(Ts) < 3:
        return nan, nan, dict(info, note='fewer than 3 settlements')
    gaps = np.diff(Ts)
    Nh = np.r_[np.nan, np.round(gaps / HOUR)]
    okN = np.r_[False, (np.abs(gaps - np.round(gaps / HOUR) * HOUR) <= 2 * MIN) & np.isin(np.round(gaps / HOUR), (1, 2, 4, 8))]
    Nh = np.where(okN, Nh, np.nan)
    Ik = PREM_INTEREST_8H * Nh / 8.0
    ch = np.r_[np.nan, np.diff(rate)]
    ch[~okN] = np.nan
    sd_set = roll_sd(ch, PREM_SD_N, _min_count(PREM_SD_N))
    # the window is by TIME too: the 90 changes must cover >= 80% of the span from settlement k-90 to k (a missing month, a gap > 1.5 h
    # inside it, makes the sd NA until a whole window has passed)
    good_dur = np.r_[0.0, np.cumsum(np.where(okN[1:], gaps, 0.0))]
    span = np.full(len(Ts), np.nan)
    if len(Ts) > PREM_SD_N:
        span[PREM_SD_N:] = (Ts[PREM_SD_N:] - Ts[:-PREM_SD_N]).astype(float)
        cover = np.full(len(Ts), np.nan)
        cover[PREM_SD_N:] = (good_dur[PREM_SD_N:len(Ts)] - good_dur[:len(Ts) - PREM_SD_N])
        sd_set = np.where(cover >= PRESENCE * span - 1e-9, sd_set, np.nan)
    else:
        sd_set = np.full(len(Ts), np.nan)
    o = int(t0) + np.arange(n, dtype=np.int64) * MIN
    seg = np.searchsorted(calc, o, side='right') - 1          # calc_time + 1 min <= the close of this bar  <=>  calc_time <= its open
    segc = np.clip(seg, 0, len(Ts) - 1)
    pv, off_grid = _on_grid(prem['ts'].to_numpy(np.int64), prem['c'].to_numpy(float), t0, n)
    info['premium_off_grid_rows'] = off_grid
    fin = np.isfinite(pv)
    valid = (seg >= 0) & np.isfinite(Nh[segc]) & ((o - Ts[segc]) <= 1.5 * np.where(np.isfinite(Nh[segc]), Nh[segc], 0) * HOUR)
    pos = (o - Ts[segc]) // MIN + 1
    use = fin & valid
    pvz = np.where(fin, pv, 0.0)
    CA = np.r_[0.0, np.cumsum(np.where(use, pos * pvz, 0.0))]
    CW = np.r_[0.0, np.cumsum(np.where(use, pos, 0.0))]
    CF = np.r_[0.0, np.cumsum(use.astype(float))]
    j = np.arange(n)
    sr_raw = (Ts[segc] - int(t0)) // MIN
    sr = np.maximum(sr_raw, 0)
    num, den, cnt = CA[j + 1] - CA[sr], CW[j + 1] - CW[sr], CF[j + 1] - CF[sr]
    # The bar that opens at Ts_k belongs to the PREVIOUS segment when calc_time_k is not on the minute (calc > its open): the sums above
    # gave it that segment's weight. Inside segment k it is bar 1 (weight 1): swap its contribution.
    fix = (sr_raw >= 0) & (sr_raw < n) & (seg >= 0)
    c0 = np.clip(sr, 0, n - 1)
    num = np.where(fix, num - (CA[c0 + 1] - CA[c0]) + np.where(fin[c0], pvz[c0], 0.0), num)
    den = np.where(fix, den - (CW[c0 + 1] - CW[c0]) + fin[c0], den)
    cnt = np.where(fix, cnt - (CF[c0 + 1] - CF[c0]) + fin[c0], cnt)
    with np.errstate(invalid='ignore', divide='ignore'):
        P = np.where(use & (cnt >= np.ceil(PRESENCE * pos - 1e-9)) & (den > 0), num / den, np.nan)
        # in-band values equal I exactly (clip I into P +- cap; P + clip(I - P) would carry rounding noise in I +- ulp)
        F = np.where(np.isfinite(P), np.clip(Ik[segc], P - PREM_CAP, P + PREM_CAP), np.nan)
        sdv = sd_set[segc]
        PML = np.where(sdv > 0, (F - rate[segc]) / sdv, np.nan)
    # reconstruction error: the prediction on the last bar of an interval against the rate settled at its end
    rec = {}
    kk = np.arange(1, len(Ts))
    jb = (Ts[kk] - MIN - int(t0)) // MIN
    ok = (jb >= 0) & (jb < n)
    kk, jb = kk[ok], jb[ok]
    f = F[jb]
    good = np.isfinite(f)
    kk, jb, f = kk[good], jb[good], f[good]
    err_old = f - rate[kk]
    err_new = f * Nh[kk] / 8.0 - rate[kk]
    year = pd.to_datetime(Ts[kk], unit='ms').year.to_numpy()
    for y in np.unique(year):
        s = year == y
        a, b = np.abs(err_old[s]), np.abs(err_new[s])
        b = b[np.isfinite(b)]
        rec[str(int(y))] = {'n': int(s.sum()), 'median_abs_old': float(np.median(a)), 'p99_abs_old': float(np.quantile(a, 0.99)),
                            'median_abs_new_8_over_N': float(np.median(b)) if len(b) else None,
                            'p99_abs_new_8_over_N': float(np.quantile(b, 0.99)) if len(b) else None}
    info['reconstruction_error_by_year'] = rec
    info['interval_hours_seen'] = {str(int(h)): int((Nh == h).sum()) for h in np.unique(Nh[np.isfinite(Nh)])}
    if 'funding_interval_hours' in fund.columns:
        fh = pd.to_numeric(fund['funding_interval_hours'], errors='coerce').to_numpy(float)
        info['interval_column_mismatch'] = int((np.isfinite(Nh) & np.isfinite(fh) & (Nh != fh)).sum())
    return lag(F, delay), lag(PML, delay), info


# ------------------------------------------------------------------------------------------------------------- WHALE
class AggStore:
    """The per-minute aggTrade reducer files <dir>/<YYYY-MM>.parquet (agg_spot / agg_perp) on a minute grid (t0, n). A month with a
    file is PRESENT (a minute without a row there is a minute without trades: zeros); a month without one is NaN. A DAY with no
    trade at all (BTC, ETH, SOL and XRP never have one) is a hole in the data, not a quiet day: it is absent too (NaN, not 0).
    A file for a month at or after HEAT_END, or a row at or after it, is refused. ts is the minute OPEN in ms (a microsecond stamp,
    above 1e14, is converted). Every file is read once per call (a group of columns together), not once per column."""

    def __init__(self, directory: str, t0: int, n: int, who: str = 'agg'):
        import re
        _no_doge(directory)
        self.t0, self.n, self.who, self.cache, self._us = int(t0), int(n), who, {}, set()
        self.files = []
        if not os.path.isdir(directory):
            raise _Skip(f'{who}: no directory {directory}')
        for f in sorted(os.listdir(directory)):
            mt = re.fullmatch(r'(\d{4})-(\d{2})\.parquet', f)
            if not mt:
                continue
            y, mo = int(mt.group(1)), int(mt.group(2))
            a = ms(f'{y}-{mo:02d}-01')
            b = ms(f'{y + (mo == 12)}-{mo % 12 + 1:02d}-01')
            if a >= HEAT_END:
                raise SystemExit(f'{os.path.join(directory, f)}: month at or after {pd.Timestamp(HEAT_END, unit="ms")}: the heat tables stop there; cut the files first')
            self.files.append((os.path.join(directory, f), a, b))
        self.month_present = np.zeros(self.n, bool)
        for _, a, b in self.files:
            self.month_present[max(0, (a - self.t0) // MIN):max(0, min(self.n, (b - self.t0) // MIN))] = True
        if not self.files:
            raise _Skip(f'{who}: no <YYYY-MM>.parquet file in {directory}')
        self.day_aligned = (self.t0 % DAY == 0) and (self.n % 1440 == 0)
        self._day_tot = None
        self._present = None

    @property
    def us_files(self) -> int:
        return len(self._us)

    def _tables(self, names):
        """(path, ts in ms of the minutes, pyarrow table of ts + names) per month file, each file read once and checked."""
        import pyarrow.parquet as pq
        for path, a, b in self.files:
            tab = pq.read_table(path, columns=['ts'] + [x for x in names if x != 'ts'])
            ts = tab.column('ts').to_numpy().astype(np.int64)
            if len(ts) and ts.max() > 10 ** 14:
                ts = ts // 1000
                self._us.add(path)
            if len(ts) and not ((ts >= 10 ** 12) & (ts < 10 ** 13)).all():
                raise SystemExit(f'{path}: ts must be milliseconds of 13 digits')
            if len(ts) and int(ts.max()) >= HEAT_END:
                raise SystemExit(f'{path}: {int((ts >= HEAT_END).sum()):,} rows at or after {pd.Timestamp(HEAT_END, unit="ms")}: the heat tables stop there; cut the file first')
            if len(ts) and (ts % MIN != 0).any():
                raise SystemExit(f'{path}: ts is not on whole minutes')
            yield path, ts, tab

    def _load(self, names) -> dict:
        """Raw columns on the grid (float64; NaN in absent months, 0 in a present minute without a row), one pass over the files."""
        out = {nm: np.where(self.month_present, 0.0, np.nan) for nm in names}
        for path, ts, tab in self._tables(names):
            off = ts - self.t0
            on = (off >= 0) & (off < self.n * MIN)
            for nm in names:
                out[nm][off[on] // MIN] = tab.column(nm).to_numpy(zero_copy_only=False).astype(float)[on]
        return out

    def day_sums(self, names) -> np.ndarray:
        """(days, len(names)) per-day sums of the columns in ONE pass over the files (a day or month without a row sums to 0)."""
        if not self.day_aligned:
            raise SystemExit('the grid is not whole days')
        nd = self.n // 1440
        out = np.zeros((nd, len(names)))
        for path, ts, tab in self._tables(names):
            d = (ts - self.t0) // DAY
            on = (ts >= self.t0) & (d < nd)
            for q, nm in enumerate(names):
                v = np.nan_to_num(tab.column(nm).to_numpy(zero_copy_only=False).astype(float))
                out[:, q] += np.bincount(d[on], weights=v[on], minlength=nd)[:nd]
        return out

    @property
    def day_tot(self):
        """Trades per day (None when the grid is not whole days)."""
        if self._day_tot is None and self.day_aligned:
            self._day_tot = self.day_sums(['n_buy', 'n_sell']).sum(1)
        return self._day_tot

    @property
    def present(self) -> np.ndarray:
        """Minutes with data: the month has a file AND the day has at least one trade."""
        if self._present is None:
            dt = self.day_tot
            self._present = self.month_present.copy() if dt is None else self.month_present & np.repeat(dt > 0, 1440)
        return self._present

    def cols(self, names) -> dict:
        """Several columns on the grid (see col), the uncached ones read together in one pass."""
        out = {nm: self.cache[nm] for nm in names if nm in self.cache}
        need = [nm for nm in dict.fromkeys(names) if nm not in out]
        if need:
            pres = self.present
            for nm, v in self._load(need).items():
                out[nm] = np.where(pres, v, np.nan)
                if nm in ('n_buy', 'n_sell', 'usd_buy', 'usd_sell', 'sw_b_1m', 'sw_s_1m', 'sw_b_500k', 'sw_s_500k'):
                    self.cache[nm] = out[nm]
        return out

    def col(self, name: str) -> np.ndarray:
        """One column on the grid (float64; NaN in absent months and days, 0 in a present minute without a row)."""
        return self.cols([name])[name]

    def after_hole(self, days: int) -> np.ndarray:
        """True on the rows within `days` days after the end of a hole (a run of absent minutes longer than 1 hour that follows data):
        the design's gap rule, 'NA until a whole window has passed'. A stretch of absence before the first data is no hole."""
        pres = self.present
        n = len(pres)
        out = np.zeros(n, bool)
        if not pres.any():
            return out
        first = int(np.argmax(pres))
        ab = ~pres
        ab[:first] = False
        d = np.diff(np.r_[0, ab.astype(np.int8), 0])
        st, en = np.flatnonzero(d == 1), np.flatnonzero(d == -1)           # runs [st, en)
        for a, e in zip(st, en):
            if e - a > 60 and e < n:
                out[e:e + days * 1440] = True
        return out


def whale_edges_by_day(store: AggStore):
    """F per decision day: the index k of the smallest edge E_k whose share of trades at or above it, over the 30 days FULLY BEFORE
    the day, is <= 0.1% (>= 24 of the 30 days present); -1 when there is none. Also the realised share of each day at its own k."""
    nd = store.n // 1440
    if store.n % 1440:
        raise SystemExit('the grid is not whole days')
    tot = store.day_tot
    pres = tot > 0
    names = [f'{c}_ge_{k}' for k in range(len(WHALE_EDGES)) for c in ('nb', 'ns')]
    sums = store.day_sums(names)                                  # one pass over the files for all 48 columns
    cnt = sums[:, 0::2] + sums[:, 1::2]
    cnt = np.where(pres[:, None], cnt, 0.0)
    totz = np.where(pres, tot, 0.0)
    cs_t = np.r_[0.0, np.cumsum(totz)]
    cs_c = np.vstack([np.zeros((1, cnt.shape[1])), np.cumsum(cnt, 0)])
    cs_p = np.r_[0, np.cumsum(pres)]
    kstar = np.full(nd, -1, np.int64)
    need = int(math.ceil(PRESENCE * WHALE_DAYS - 1e-9))
    seen = np.cumsum(pres) > 0
    cs_h = np.r_[0, np.cumsum(~pres & seen)]                      # days without trades after the first data day: holes
    for D in range(WHALE_DAYS, nd):
        if cs_p[D] - cs_p[D - WHALE_DAYS] < need:
            continue
        if cs_h[D] - cs_h[D - WHALE_DAYS] > 0:                    # gap rule: no F until 30 whole days have passed since a hole
            continue
        t = cs_t[D] - cs_t[D - WHALE_DAYS]
        if t <= 0:
            continue
        share = (cs_c[D] - cs_c[D - WHALE_DAYS]) / t
        hit = np.flatnonzero(share <= WHALE_Q)
        if len(hit):
            kstar[D] = hit[0]
    real = np.full(nd, np.nan)
    sel = kstar >= 0
    real[sel] = cnt[np.flatnonzero(sel), kstar[sel]] / np.where(totz[sel] > 0, totz[sel], np.nan)
    return kstar, real, pres


def sweep_state(b, s, present, signs=None):
    """+1 buy sweep / -1 sell sweep / 0 none in the last 5 minutes (the row and 4 before; NaN until a whole, >= 80% present, window).
    b, s: per-minute count of seconds whose same-side sum reached the threshold. Both sides in the window: the later minute wins; the
    same minute: 0. signs (a twin): buy and sell swapped on the minutes where the sign is -1. Returns (state, same-minute count)."""
    b, s = np.nan_to_num(np.asarray(b, float)) > 0, np.nan_to_num(np.asarray(s, float)) > 0
    if signs is not None:
        b, s = np.where(signs > 0, b, s), np.where(signs > 0, s, b)
    n = len(b)
    idx = np.arange(n)
    lb = np.maximum.accumulate(np.where(b, idx, -10 ** 9))
    ls = np.maximum.accumulate(np.where(s, idx, -10 ** 9))
    inb, ins = idx - lb <= SWEEP_BARS - 1, idx - ls <= SWEEP_BARS - 1
    st = np.zeros(n)
    st[inb & ~ins] = 1.0
    st[ins & ~inb] = -1.0
    both = inb & ins
    st[both & (lb > ls)] = 1.0
    st[both & (ls > lb)] = -1.0
    tie = both & (lb == ls)
    pres, _ = roll_sum(np.where(present, 1.0, np.nan), SWEEP_BARS, _min_count(SWEEP_BARS))
    st[~np.isfinite(pres)] = np.nan
    return st, int(tie.sum())


def whale_values(store: AggStore, signs=None, prefix: str = 'WHALE'):
    """The three WHALE readings of one market ('WHALE' spot, 'WHALEP' perp) plus the $500k sweep reference, and their info."""
    kstar, real, pres_day = whale_edges_by_day(store)
    kmin = np.repeat(kstar, 1440)
    n = store.n
    mc15, mc60 = _min_count(15), _min_count(60)
    after7 = store.after_hole(WHALE_BASE_DAYS)                     # gap rule: Count60 is NA for 7 days after a data hole
    tot_usd = store.col('usd_buy') + store.col('usd_sell')
    tot15, _ = roll_sum(tot_usd, 15, mc15)
    net15, cnt60 = np.full(n, np.nan), np.full(n, np.nan)
    for k in np.unique(kmin[kmin >= 0]):
        rows = np.flatnonzero(kmin == k)
        g = store.cols([f'ub_ge_{k}', f'us_ge_{k}', f'nb_ge_{k}', f'ns_ge_{k}'])
        net = g[f'ub_ge_{k}'] - g[f'us_ge_{k}']
        if signs is not None:
            net = net * signs                       # a flipped minute swaps buy and sell: the net notional changes sign
        s15, _ = roll_sum(net, 15, mc15)
        net15[rows] = _ratio(s15, tot15)[rows]
        c60, _ = roll_sum(g[f'nb_ge_{k}'] + g[f'ns_ge_{k}'], 60, mc60)      # a count: the sides are not told apart, no flip
        base = np.full((WHALE_BASE_DAYS, len(rows)), np.nan)
        for j in range(1, WHALE_BASE_DAYS + 1):
            r = rows - 1440 * j
            ok = r >= 0
            base[j - 1, ok] = c60[r[ok]]
        good = np.isfinite(base).sum(0)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            med, sd = np.nanmedian(base, 0), np.nanstd(base, 0, ddof=1)
        z = (c60[rows] - med) / np.maximum(sd, 1.0)
        z[good < int(math.ceil(PRESENCE * WHALE_BASE_DAYS - 1e-9))] = np.nan
        z[after7[rows]] = np.nan
        cnt60[rows] = z
    out = {f'{prefix}:Net15': net15, f'{prefix}:Count60': cnt60}
    ties = {}
    for tag, nm in (('1m', f'{prefix}:Sweep'), ('500k', ('REF:Sweep500' if prefix == 'WHALE' else 'REFP:Sweep500'))):
        out[nm], ties[nm] = sweep_state(store.col(f'sw_b_{tag}'), store.col(f'sw_s_{tag}'), store.present, signs)
    ok = np.isfinite(real)
    info = {'f_days_with_value': int(ok.sum()), 'f_edge_index_counts': {str(int(k)): int((kstar == k).sum()) for k in np.unique(kstar)},
            'realised_share_of_trades_at_f': {'median': float(np.median(real[ok])) if ok.any() else None,
                                              'p05': float(np.quantile(real[ok], 0.05)) if ok.any() else None,
                                              'p95': float(np.quantile(real[ok], 0.95)) if ok.any() else None},
            'sweep_same_minute_both_sides': ties, 'us_files': store.us_files}
    return out, info, real


# ------------------------------------------------------------------------------------------------------------- the rest
def book_imbalance(book: pd.DataFrame, t0: int, n: int) -> np.ndarray:
    """(bid_1pct - ask_1pct) / (bid_1pct + ask_1pct) from the latest bookDepth stamp known at the row's close (ts is already shifted
    one spacing later by the fetch job); carried at most 10 minutes."""
    ts = book['ts'].to_numpy(np.int64)
    b, a = (pd.to_numeric(book[c], errors='coerce').to_numpy(float) for c in ('bid_1pct', 'ask_1pct'))
    with np.errstate(invalid='ignore', divide='ignore'):
        imb = np.where((b + a > 0) & np.isfinite(b) & np.isfinite(a) & (b >= 0) & (a >= 0), (b - a) / (b + a), np.nan)
    if not len(ts):
        return np.full(n, np.nan)
    close = int(t0) + (np.arange(n, dtype=np.int64) + 1) * MIN
    j = np.searchsorted(ts, close, side='right') - 1
    jc = np.clip(j, 0, max(len(ts) - 1, 0))
    ok = (j >= 0) & (close - ts[jc] <= BOOK_CARRY)
    return np.where(ok, imb[jc], np.nan)


def metrics_clock_info(met: pd.DataFrame, mark: pd.DataFrame, t0: int, n: int) -> dict:
    """Information only (the fetch job's labelling is the check): per year, the median |ln(implied price) - ln(mark open)| at S and at S + 5 min."""
    if not {'sum_open_interest', 'sum_open_interest_value'} <= set(met.columns) or 'o' not in mark.columns:
        return {'note': 'metrics lacks sum_open_interest / sum_open_interest_value, or mark lacks o'}
    mo, _ = _on_grid(mark['ts'].to_numpy(np.int64), mark['o'].to_numpy(float), t0, n)
    S = met['S'].to_numpy(np.int64)
    oi, oiv = (pd.to_numeric(met[c], errors='coerce').to_numpy(float) for c in ('sum_open_interest', 'sum_open_interest_value'))
    with np.errstate(invalid='ignore', divide='ignore'):
        imp = np.log(oiv / oi)
    out = {}
    year = pd.to_datetime(S, unit='ms').year.to_numpy()
    for off in (0, SNAP):
        r = (S + off - int(t0)) // MIN
        ok = (r >= 0) & (r < n)
        with np.errstate(invalid='ignore', divide='ignore'):
            e = np.abs(imp - np.log(np.where(ok, mo[np.clip(r, 0, n - 1)], np.nan)))
        for y in np.unique(year):
            v = e[(year == y) & np.isfinite(e)]
            out.setdefault(str(int(y)), {})[f'median_abs_log_gap_at_S+{off // MIN}min'] = float(np.median(v)) if len(v) else None
    return out


def _agg(x, m, who):
    return x if isinstance(x, AggStore) else AggStore(x, m['t0'], m['n'], who)


def full_values(sp: dict, pp: dict = None, *, metrics=None, premium=None, premium_stamp=None, funding=None, mark=None,
                agg_spot=None, agg_perp=None, book=None, signs=None) -> dict:
    """Every NEW value series per minute row on the spot grid (NaN where there is no reading yet), before the stale rule and the
    zones. sp: the spot bars (t0, n, gap, c); pp: the perp bars on the same grid (only its gap is read, for WHALEP); the inputs are
    the DATA CONTRACT frames (prepared here: metrics / premium / funding / book frames from the csv.gz files, mark = mark_1m frame,
    premium_stamp = the dict or path of premium_stamp.json, agg_spot / agg_perp = an AggStore or a directory of <YYYY-MM>.parquet).
    A family whose input is missing or unusable is skipped with a reason (never guessed); a row at or after HEAT_END is refused
    (SystemExit). signs: a twin's per-minute coin flips (twin_signs): the direction readings (Net15, Sweep) swap buy and sell on the
    flipped minutes; the level readings (LS, PREM, Count60, BOOKP) do not change.
    Returns {'values': {name: series}, 'skipped': {name: reason}, 'info': {...}, 'gap': spot gap, 'gap_perp': perp gap or None}."""
    t0, n = int(sp['t0']), int(sp['n'])
    vals, skipped, info = {}, {}, {}
    signs = None if signs is None else np.asarray(signs, float)
    gap = np.asarray(sp['gap'], bool)
    gap_perp = None if pp is None else np.asarray(pp['gap'], bool)

    def skip(names, why):
        for nm in names:
            skipped[nm] = why

    LS = [x for x in FULL_LEAGUE if x.startswith('LS:')]
    PR = ['PREM:PredFund', 'PREM:PredMinusLast']
    try:                                                              # ---- LS
        if metrics is None:
            raise _Skip('no metrics file')
        met = prep_metrics(metrics)
        if not len(met):
            raise _Skip('metrics holds no rows')
        s0, ser = ls_slots(met)
        for nm in LS:
            vals[nm] = carry_rows(ser[nm], s0, LS_KNOWN, CARRY, t0, n)
        info['metrics'] = {'rows': int(len(met)), 'first': str(pd.Timestamp(int(met['S'].iloc[0]), unit='ms')),
                           'last': str(pd.Timestamp(int(met['S'].iloc[-1]), unit='ms')), 'known_rule': 'S + 5 min, carried at most 10 min'}
        if 'conv' in met.columns:
            info['metrics']['conv_counts'] = {str(k): int(v) for k, v in met['conv'].value_counts().items()}
        if mark is not None:
            info['metrics']['clock_vs_mark_by_year'] = metrics_clock_info(met, prep_premium(mark, 'mark'), t0, n)
    except _Skip as e:
        skip(LS, str(e))
    try:                                                              # ---- PREM
        why = [w for w, v in (('premium', premium), ('premium_stamp', premium_stamp), ('funding', funding)) if v is None]
        if why:
            raise _Skip('no ' + ' / '.join(why))
        delay = premium_delay(premium_stamp)
        vals['PREM:PredFund'], vals['PREM:PredMinusLast'], pinfo = prem_series(prep_premium(premium), prep_funding(funding), t0, n, delay)
        info['prem'] = pinfo
    except _Skip as e:
        skip(PR, str(e))
    for tag, ag, g, prefix in (('spot', agg_spot, gap, 'WHALE'), ('perp', agg_perp, gap if gap_perp is None else gap | gap_perp, 'WHALEP')):
        names = [f'{prefix}:Net15', f'{prefix}:Count60', f'{prefix}:Sweep']
        try:                                                          # ---- WHALE / WHALEP
            if ag is None:
                raise _Skip(f'no agg_{tag} directory')
            store = _agg(ag, sp, f'agg_{tag}')
            v, winfo, _ = whale_values(store, signs, prefix)
            vals.update(v)
            info[f'whale_{tag}'] = winfo
        except _Skip as e:
            skip(names, str(e))
        except KeyError as e:
            skip(names, f'agg_{tag}: a column is missing ({e})')
        except Exception as e:                                         # a reducer file that pyarrow cannot give the column of
            if type(e).__name__ in ('ArrowInvalid', 'ArrowKeyError'):
                skip(names, f'agg_{tag}: {type(e).__name__}: {e}')
            else:
                raise
    try:                                                              # ---- BOOKP
        if book is None:
            raise _Skip('no bookdepth file')
        bk = prep_book(book)
        vals['BOOKP:Imb1'] = book_imbalance(bk, t0, n)
        sp_ms = float(np.median(np.diff(bk['ts'].to_numpy(np.int64)))) if len(bk) > 2 else None
        info['book'] = {'rows': int(len(bk)), 'median_spacing_ms': sp_ms, 'first': str(pd.Timestamp(int(bk['ts'].iloc[0]), unit='ms')) if len(bk) else None}
    except _Skip as e:
        skip(['BOOKP:Imb1'], str(e))
    return {'values': vals, 'skipped': skipped, 'info': info, 'gap': gap, 'gap_perp': gap_perp}


def stale_full(name: str, gap: np.ndarray, gap_perp=None) -> np.ndarray:
    """The engine's stale rule on the reading's window (W rows) of the spot grid, and of the perp bars for the perp readings."""
    W = {'Net15': 15, 'Count60': 60, 'Sweep': SWEEP_BARS, 'Sweep500': SWEEP_BARS}.get(name.split(':')[1], 1)
    g = gap if (gap_perp is None or not name.startswith(('WHALEP', 'REFP'))) else gap | gap_perp
    return stale_rows(g, W)


def zone_why(x, a_hi: int, t0: int = None) -> str:
    xa = np.asarray(x, float)[:a_hi]
    fin = np.isfinite(xa)
    if fin.sum() < MIN_A:
        return f'fewer than {MIN_A:,} finite values on A ({int(fin.sum()):,})'
    nd = len(np.unique((int(t0) + np.flatnonzero(fin) * MIN) // DAY)) if t0 is not None else None
    if nd is not None and nd < MIN_A_DAYS:
        return f'values on {nd} distinct days of A, fewer than {MIN_A_DAYS}'
    return 'the inner zones are empty (edges collapse)'


def state_reading(name: str, x, a_hi: int, family: str, t0: int = None, fixed: bool = False):
    """A three-state reading (-1 sell sweep / 0 none / +1 buy sweep) as an engine reading, or (None, reason): needs MIN_A finite
    values on MIN_A_DAYS days of A and SWEEP_MIN_A rows of each side on A (data sufficiency; no zone edges)."""
    x = np.asarray(x, float)
    xa = x[:a_hi]
    fin = np.isfinite(xa)
    if not fixed:                                           # (stored edges / parity: no A rows are looked at, as for the zones)
        if fin.sum() < MIN_A:
            return None, f'fewer than {MIN_A:,} finite values on A ({int(fin.sum()):,})'
        if t0 is not None:
            nd = len(np.unique((int(t0) + np.flatnonzero(fin) * MIN) // DAY))
            if nd < MIN_A_DAYS:
                return None, f'values on {nd} distinct days of A, fewer than {MIN_A_DAYS}'
        nb, ns = int((xa == 1).sum()), int((xa == -1).sum())
        if nb < SWEEP_MIN_A or ns < SWEEP_MIN_A:
            return None, f'sweep rows on A: {nb:,} buy / {ns:,} sell, fewer than {SWEEP_MIN_A} on a side'
    codes = np.where(np.isfinite(x), x + 1, -1).astype(np.int8)
    return {'name': name, 'k': 1, 'codes': codes, 'levels': SWEEP_LEVELS, 'base': name, 'type': 'xd', 'family': family, 'cond': True}, None


def full_readings(sp: dict, pp: dict, a_hi: int, edges: dict = None, keep: bool = False, skip=(), signs=None, **inputs) -> dict:
    """The new league readings (full_values' inputs as keywords), as xd_readings makes the lite ones: the stale rule, then five zones
    from A's rows (WHALE:Sweep / WHALEP:Sweep: three states). edges: fixed zone edges by name (a name without one is skipped); skip:
    names left out whatever their values (a twin follows its real coin's skips). Returns {'readings', 'edges', 'skipped' (names),
    'reasons' {name: why}, 'values' (keep: the stale-masked series, references included), 'gap', 'info'}."""
    X = full_values(sp, pp, signs=signs, **inputs)
    gapc, gp = X['gap'], X['gap_perp']
    out = {'readings': [], 'edges': {}, 'skipped': [], 'reasons': dict(X['skipped']), 'values': {}, 'gap': gapc, 'info': X['info']}
    for name in FULL_LEAGUE + FULL_REFS:
        if name not in X['values']:
            if name in FULL_LEAGUE:
                out['skipped'].append(name)
            continue
        x = np.array(X['values'][name], float)
        x[stale_full(name, gapc, gp)] = np.nan
        if keep:
            out['values'][name] = x
        if name not in FULL_LEAGUE:
            continue
        if name in skip:
            out['skipped'].append(name)
            out['reasons'][name] = 'skipped for the real coin, so for its twins (OR-XD twin rule)'
            continue
        if name in FULL_STATE:
            if edges is not None and name not in edges:
                out['skipped'].append(name)
                out['reasons'][name] = 'no stored edge'
                continue
            R, why = state_reading(name, x, a_hi, FULL_FAMILY[name], sp.get('t0'), fixed=edges is not None)
            e = []
        else:
            e = None
            if edges is not None:
                e = edges.get(name)
                if e is None:
                    out['skipped'].append(name)
                    out['reasons'][name] = 'no stored edge'
                    continue
            R, e = zone(name, x, a_hi, FULL_FAMILY[name], e, sp.get('t0'))
            why = None if R is not None else zone_why(x, a_hi, sp.get('t0'))
        if R is None:
            out['skipped'].append(name)
            out['reasons'][name] = why
            continue
        out['readings'].append(R)
        out['edges'][name] = e
    for nm in out['skipped']:
        out['reasons'].setdefault(nm, 'skipped')
    return out


def full_near_duplicates(vals: dict, a_hi: int, lite_vals: dict = None, stride: int = 7) -> dict:
    """Spearman rank correlation on A rows (every `stride`-th row, with both values) of every pair that holds at least one NEW
    reading or the $500k reference: the new readings among themselves and against the lite readings and references."""
    from scipy.stats import spearmanr
    allv = dict(lite_vals or {})
    allv.update(vals)
    new = [x for x in FULL_LEAGUE + FULL_REFS if x in vals]
    names = [x for x in allv]
    out = {}
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if a not in new and b not in new:
                continue
            x, y = allv[a][:a_hi:stride], allv[b][:a_hi:stride]
            ok = np.isfinite(x) & np.isfinite(y)
            out[f'{a} ~ {b}'] = {'spearman': _fin(spearmanr(x[ok], y[ok])[0]) if ok.sum() > 30 and x[ok].std() > 0 and y[ok].std() > 0 else None, 'n': int(ok.sum())}
    return out


def full_direction_coupling(vals: dict, close: np.ndarray, gap: np.ndarray, a_hi: int) -> dict:
    """direction_coupling for the new readings (A rows): Pearson with the past 5 / 15 / 60 minute return."""
    return direction_coupling({k: v for k, v in vals.items() if k in FULL_LEAGUE or k in FULL_REFS}, close, gap, a_hi,
                              names=[k for k in FULL_LEAGUE + FULL_REFS if k in vals])


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


def _hm2_lite_readings(m, perp, oi, a_hi, z, log=print, info=None, real=None, perp_frame=None, twin=None, seed=None) -> list:
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


HM2_FULL_INPUTS = ('metrics', 'premium', 'premium_stamp', 'funding', 'mark', 'agg_spot', 'agg_perp', 'book')


def hm2_outside_readings(m, perp, oi, a_hi, z, log=print, info=None, real=None, perp_frame=None, twin=None, seed=None, *,
                         metrics=None, premium=None, premium_stamp=None, funding=None, mark=None, agg_spot=None, agg_perp=None, book=None) -> list:
    """The OR-XD readings as extra single readings for OR-HM2, ONE call for all families. Without the keyword inputs this is exactly the
    five-reading hook (_hm2_lite_readings: its docstring above describes m, perp, oi, a_hi, z, real, perp_frame, twin, seed and info).

    The keyword inputs (all optional, the DATA CONTRACT files of raw/outside/binance/<COIN>/) add the Amendment 3 readings through
    full_values / the same Zoner calls: metrics (frame of metrics.csv.gz) -> LS:Global z, LS:TopPos z, LS:TopPosChg60, LS:TopAcc z;
    premium (premium_1m frame) + premium_stamp (premium_stamp.json: dict or path) + funding (funding frame) -> PREM:PredFund,
    PREM:PredMinusLast; agg_spot / agg_perp (an AggStore, or the directory of <YYYY-MM>.parquet) -> WHALE:* / WHALEP:*;
    book (bookdepth_1pct frame) -> BOOKP:Imb1; mark (mark_1m frame) -> information only. A reading whose input is missing or fails
    is skipped with a recorded reason (info['skipped'][name]; z.skipped); a row at or after HEAT_END is refused (info['refused']['full']).
    The twin rule: Net15 and Sweep swap buy and sell on the minutes the twin's coin flip (twin_signs(n, seed)) flips; LS, PREM, Count60
    and BOOKP are real-level. A twin follows its real coin's skips. WHALE:Sweep / WHALEP:Sweep are three-state: they need
    z.state(name, x, levels, stale=, family=) (x = -1 / 0 / +1 / NaN, levels = SWEEP_LEVELS), skipped with a reason when the Zoner has
    none. Every reading carries research_only. info gains 'full' (near_duplicates, direction_coupling, reading_share, input info,
    constants)."""
    inputs = {'metrics': metrics, 'premium': premium, 'premium_stamp': premium_stamp, 'funding': funding, 'mark': mark,
              'agg_spot': agg_spot, 'agg_perp': agg_perp, 'book': book}
    out = _hm2_lite_readings(m, perp, oi, a_hi, z, log, info, real, perp_frame, twin, seed)
    if all(v is None for v in inputs.values()):
        return out
    want = info is not None
    finfo = info if want else {}
    if twin is None:
        twin = seed is not None
    if twin and seed is None:
        raise ValueError('a twin needs its seed')
    fixed = getattr(z, 'fixed', None)
    real = real or {}
    reasons = finfo.setdefault('skipped', {})
    refused = finfo.setdefault('refused', {})
    signs = twin_signs(int(m['n']), int(seed)) if twin else None
    gp = lambda p: {'gap': np.asarray(p['gap'], bool)} if p is not None and p.get('gap') is not None else None

    def skip(name, why):
        reasons[name] = why
        sk = getattr(z, 'skipped', None)
        if sk is not None and name not in sk:
            sk.append(name)

    def done():
        finfo['readings'] = [R['name'] for R in out]
        return out

    try:
        X = full_values(m, gp(real.get('perp') if twin else perp) or gp(perp), signs=signs, **inputs)
    except SystemExit as e:
        refused['full'] = str(e)
        for name in FULL_LEAGUE:
            skip(name, 'refused: ' + str(e))
        log(f'  XD hook (full): refused ({e})')
        return done()
    gapc = X['gap']
    inherited = set()
    if twin and fixed is None:
        rm = real.get('m') or m
        inherited = set(full_readings(rm, gp(real.get('perp')), a_hi, **inputs)['skipped'])
    t0 = m.get('t0')
    vals, new = {}, []
    for name in FULL_LEAGUE + FULL_REFS:
        if name in X['values']:
            x = np.array(X['values'][name], float)
            st = stale_full(name, gapc, X['gap_perp'])
            x[st] = np.nan
            vals[name] = x
    for name in FULL_LEAGUE:
        if name in X['skipped']:
            skip(name, X['skipped'][name])
            continue
        if name in inherited:
            skip(name, 'skipped for the real coin, so for its twins (OR-XD twin rule)')
            continue
        x, st = vals[name], stale_full(name, gapc, X['gap_perp'])
        fam = FULL_FAMILY[name].lower()
        if name in FULL_STATE:
            why = None
            if fixed is None:
                _, why = state_reading(name, x, a_hi, fam, t0)
            if why:
                skip(name, why)
                continue
            if getattr(z, 'state', None) is None:
                skip(name, 'the Zoner has no state method for a three-state reading')
                continue
            R = z.state(name, X['values'][name], SWEEP_LEVELS, stale=st, family=fam)
        else:
            if fixed is None:
                fin = np.isfinite(x[:a_hi])
                if int(fin.sum()) < MIN_A:
                    skip(name, f'fewer than {MIN_A:,} finite values on A ({int(fin.sum()):,})')
                    continue
                nd = len(np.unique((int(t0) + np.flatnonzero(fin) * MIN) // DAY))
                if nd < MIN_A_DAYS:
                    skip(name, f'values on {nd} distinct days of A, fewer than {MIN_A_DAYS}')
                    continue
            R = z.zone(name, X['values'][name], stale=st, family=fam)
        if R is None:
            reasons[name] = 'no stored edge' if fixed is not None else 'the inner zones are empty (edges collapse)'
            continue
        R['research_only'] = True
        out.append(R)
        new.append(name)
    log(f'  XD hook (full): {len(new)} readings {new}, skipped { {k: v for k, v in reasons.items() if k in FULL_LEAGUE} }; research only')
    if want:
        try:
            nd_ = full_near_duplicates(vals, a_hi)
        except ImportError:
            nd_ = None
        finfo['full'] = {'near_duplicates': nd_, 'direction_coupling': full_direction_coupling(vals, m['c'], gapc, a_hi),
                         'reading_share': reading_share(vals, a_hi), 'input': X['info'], 'constants': FULL_CONSTANTS, 'twin': bool(twin),
                         'edges': {R['name']: list(R['edges']) for R in out if R['name'] in new and R.get('edges') is not None}}
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


def load_full_inputs(metrics=None, premium=None, premium_stamp=None, mark=None, funding=None, agg_spot_dir=None, agg_perp_dir=None, book=None) -> dict:
    """The optional DATA CONTRACT files for full_values: {'inputs': keyword arguments for full_values, 'files': {name: path or the reason it is
    missing}}. A path that is not given or does not exist is a missing input (its readings are skipped with a reason); a file that holds a
    row at or after HEAT_END, lacks a column or has a bad stamp is refused (SystemExit)."""
    _no_doge(metrics, premium, premium_stamp, mark, funding, agg_spot_dir, agg_perp_dir, book)
    inputs, files = {}, {}

    def have(name, p, isdir=False):
        ok = p and (os.path.isdir(p) if isdir else os.path.isfile(p))
        files[name] = p if ok else ('not given' if not p else f'not found: {p}')
        return bool(ok)

    if have('metrics', metrics):
        inputs['metrics'] = read_checked(metrics, ('S', 'count_long_short_ratio', 'sum_toptrader_long_short_ratio', 'count_toptrader_long_short_ratio'), 'metrics', 'S')
    if have('premium', premium):
        inputs['premium'] = read_checked(premium, ('ts', 'c'), 'premium', 'ts')
    if have('premium_stamp', premium_stamp):
        with open(premium_stamp) as f:
            inputs['premium_stamp'] = json.load(f)
    if have('mark', mark):
        inputs['mark'] = read_checked(mark, ('ts', 'o', 'c'), 'mark', 'ts')
    if have('funding', funding):
        inputs['funding'] = read_checked(funding, ('calc_time', 'last_funding_rate'), 'funding', 'calc_time')
    if have('book', book):
        inputs['book'] = read_checked(book, ('ts', 'bid_1pct', 'ask_1pct'), 'bookdepth', 'ts')
    if have('agg_spot', agg_spot_dir, True):
        inputs['agg_spot'] = agg_spot_dir
    if have('agg_perp', agg_perp_dir, True):
        inputs['agg_perp'] = agg_perp_dir
    return {'inputs': inputs, 'files': files}


def run_coin_outside(asset: str, spot_csv: str, perp_csv: str, oi_csv: str, out: str, twin: int = 0, procs: int = 0, log=print,
                     end: int = heat.HEAT_END, perp_lag: int = 0, metrics: str = None, premium: str = None, premium_stamp: str = None,
                     mark: str = None, funding: str = None, agg_spot_dir: str = None, agg_perp_dir: str = None, book: str = None) -> dict:
    """heat.run_coin with the OR-XD readings in place of OR-HM1's vocabulary (see the module doc). perp_lag: minutes by which
    every perp input is seen late (0 in this archive-only pass; 1 and 5 for the robustness reruns). Returns meta.json's dict."""
    _no_doge(asset, spot_csv, perp_csv, oi_csv, out)
    fx = load_full_inputs(metrics, premium, premium_stamp, mark, funding, agg_spot_dir, agg_perp_dir, book)
    use_full = bool(fx['inputs'])                 # the full readings run when at least one contract file or directory is given
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
        fres, fskip, xfull = None, set(), None
        if use_full:
            fsigns = None if ctx.seed is None else twin_signs(m['n'], ctx.seed)
            if ctx.seed is not None:
                fskip = set(full_readings(real, pg, a_hi, **fx['inputs'])['skipped'])
            fres = full_readings(m, pp, a_hi, keep=True, skip=fskip, signs=fsigns, **fx['inputs'])
            fv = fres['values']
            xfull = {'near_duplicates': full_near_duplicates(fv, a_hi, vals), 'direction_coupling': full_direction_coupling(fv, m['c'], fres['gap'], a_hi),
                     'reading_share': reading_share(fv, a_hi), 'constants': FULL_CONSTANTS, 'input': fres['info'], 'files': fx['files'],
                     'skipped': fres['skipped'], 'skipped_reasons': fres['reasons'], 'skipped_inherited_from_real_coin': sorted(fskip),
                     'readings': [r['name'] for r in fres['readings']], 'twin_seed': ctx.seed,
                     'perp_lag_applied': False, 'edges_from': f'quantiles {list(heat.ZONE_Q)} of the {a_hi:,} rows of split A'}
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
        if xfull is not None:
            ctx.extras['xd_full'] = xfull
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
        if fres is not None:
            log(f'  XD full: {len(fres["readings"])} readings {[r["name"] for r in fres["readings"]]}, skipped {fres["reasons"] if fres["skipped"] else {}}; files {fx["files"]}')
            return res['readings'] + fres['readings'], heat.Rows(), {**res['edges'], **fres['edges']}, [], None
        return res['readings'], heat.Rows(), res['edges'], [], None

    heat.build_readings, heat.make_twin = build, make_twin
    try:
        meta = heat.run_coin(asset, spot_csv, '', out, end=end, twin=twin, procs=procs, log=log)
    finally:
        heat.build_readings, heat.make_twin = orig_build, orig_twin
    meta.update(ctx.extras)
    meta['study'] = 'OR-XD lite + full' if use_full else 'OR-XD lite'
    with open(os.path.join(out, 'meta.json'), 'w') as f:
        json.dump(meta, f, indent=1)
    return meta


def cut_dir(directory: str, end: int = HEAT_END, log=print) -> dict:
    """Cut a raw/outside/binance/<COIN>/ folder at `end` (HEAT_END) before any reader sees it: rows at or after it are dropped from every
    csv.gz of the contract (metrics by S, funding by calc_time, the others by ts) and every agg_spot / agg_perp month file at or
    after the month of `end` is deleted (an earlier month file is rewritten only when it holds a later row). Returns {file: rows dropped}."""
    _no_doge(directory)
    cols = {'metrics.csv.gz': 'S', 'premium_1m.csv.gz': 'ts', 'mark_1m.csv.gz': 'ts', 'index_1m.csv.gz': 'ts', 'um_1m.csv.gz': 'ts',
            'funding.csv.gz': 'calc_time', 'bookdepth_1pct.csv.gz': 'ts', 'BTCDOM/idx1h.csv.gz': 'ts', 'idx1h.csv.gz': 'ts'}
    dropped = {}
    for rel, tc in cols.items():
        p = os.path.join(directory, rel)
        if not os.path.isfile(p):
            continue
        df = pd.read_csv(p)
        keep = pd.to_numeric(df[tc], errors='coerce') < end
        if not keep.all():
            df[keep].to_csv(p, index=False, compression='gzip')
        dropped[rel] = int((~keep).sum())
    for sub in ('agg_spot', 'agg_perp'):
        d = os.path.join(directory, sub)
        if not os.path.isdir(d):
            continue
        import pyarrow.parquet as pq
        for f in sorted(os.listdir(d)):
            if not f.endswith('.parquet'):
                continue
            p = os.path.join(d, f)
            if f[:7] >= pd.Timestamp(end, unit='ms').strftime('%Y-%m'):
                os.remove(p)
                dropped[f'{sub}/{f}'] = -1
                continue
            t = pq.read_table(p)
            ts = t.column('ts').to_numpy().astype(np.int64)
            ts = np.where(ts > 10 ** 14, ts // 1000, ts)
            if (ts >= end).any():
                pq.write_table(t.filter(ts < end), p)
                dropped[f'{sub}/{f}'] = int((ts >= end).sum())
    log(f'cut at {pd.Timestamp(end, unit="ms")}: ' + (str(dropped) if dropped else 'nothing to drop'))
    return dropped


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
    a.add_argument('--xd-dir', help='a raw/outside/binance/<COIN> folder: fills every contract input below that is not given explicitly')
    a.add_argument('--metrics', help='metrics.csv.gz (S, stamp, conv, ...): LS readings')
    a.add_argument('--premium', help='premium_1m.csv.gz: PREM readings (needs --premium-stamp and --funding)')
    a.add_argument('--premium-stamp', help='premium_stamp.json: the stamp test (same | next)')
    a.add_argument('--mark', help='mark_1m.csv.gz: information only (metrics clock check)')
    a.add_argument('--funding', help='funding.csv.gz: PREM readings')
    a.add_argument('--agg-spot-dir', help='agg_spot/ (<YYYY-MM>.parquet): WHALE readings')
    a.add_argument('--agg-perp-dir', help='agg_perp/ (<YYYY-MM>.parquet): WHALEP readings')
    a.add_argument('--book', help='bookdepth_1pct.csv.gz: BOOKP:Imb1')
    c = sp.add_parser('cut', help='cut a raw/outside/binance/<COIN> folder at HEAT_END (2026-01-01 UTC)')
    c.add_argument('--dir', required=True)
    x = ap.parse_args(argv)
    if x.cmd == 'cut':
        cut_dir(x.dir)
        return
    d = x.xd_dir
    pick = lambda v, rel: v or (os.path.join(d, rel) if d else None)
    mt = run_coin_outside(x.asset, x.spot, x.perp, x.oi, x.out, twin=x.twin, procs=x.procs, perp_lag=x.perp_lag,
                          metrics=pick(x.metrics, 'metrics.csv.gz'), premium=pick(x.premium, 'premium_1m.csv.gz'),
                          premium_stamp=pick(x.premium_stamp, 'premium_stamp.json'), mark=pick(x.mark, 'mark_1m.csv.gz'),
                          funding=pick(x.funding, 'funding.csv.gz'), agg_spot_dir=pick(x.agg_spot_dir, 'agg_spot'),
                          agg_perp_dir=pick(x.agg_perp_dir, 'agg_perp'), book=pick(x.book, 'bookdepth_1pct.csv.gz'))
    print(json.dumps({k: v for k, v in mt.items() if k not in ('base', 'edges', 'reading_share')}, indent=1, default=str))


if __name__ == '__main__':
    main()
