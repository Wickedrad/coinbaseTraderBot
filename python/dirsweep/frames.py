"""The two functions of the FINAL's data path, copied unchanged from `heatloop.events.read_bars` and `oracle.heat_live.grid` (as of the commit named in
FREEZE-DS.json) so that a later edit of those shared modules cannot change a FINAL number: this file is hashed with the rest of `python/dirsweep`.
`tests/test_frames.py` pins what they return on a fixed frame. The sweep itself read the originals; `stage final --plumbing` checks that the two give
identical grids on the search days.
"""
import numpy as np
import pandas as pd

MIN = 60_000
DAY = 86_400_000


def read_bars(csv: str, lo_ms: int, hi_ms: int, chunk: int = 250_000) -> pd.DataFrame:
    """The rows of the 1-minute file with lo_ms <= ts < hi_ms, read in chunks. The file is time-ordered: reading stops at the first
    chunk that starts at or after hi_ms, and a row at or after hi_ms is dropped the moment its chunk is read, so no later
    minute stays in memory (guards.history_limit)."""
    cols = pd.read_csv(csv, nrows=0).columns
    use = [c for c in ('ts', 'o', 'h', 'l', 'c', 'v', 'tb') if c in cols]
    parts, last = [], None
    with pd.read_csv(csv, usecols=use, chunksize=chunk) as reader:
        for df in reader:
            if not df['ts'].is_monotonic_increasing or (last is not None and int(df['ts'].iloc[0]) < last):
                raise ValueError('the 1-minute file is not time-ordered')
            last = int(df['ts'].iloc[-1])
            if int(df['ts'].iloc[0]) >= hi_ms:
                break
            parts.append(df[(df['ts'] >= lo_ms) & (df['ts'] < hi_ms)])
    if not parts:
        raise ValueError(f'no minute in [{lo_ms}, {hi_ms})')
    out = pd.concat(parts, ignore_index=True)
    if len(out) and int(out['ts'].max()) >= hi_ms:
        raise AssertionError('a minute at or after the scope end was loaded')
    return out


def grid(df: pd.DataFrame, end_ms: int = None) -> dict:
    """Complete 1-minute grid from the first UTC midnight on or after the first row to end_ms (exclusive; default: one
    minute after the last row = the close of the last closed minute). ts = the minute's open time in ms. A missing
    minute or a broken row is a gap: forward-filled, volume 0 (as heat.load_minutes). The last day may be partial."""
    df = df.copy()
    end = int(df['ts'].max()) + MIN if end_ms is None else int(end_ms)
    df = df[df['ts'] < end]
    px = df[['o', 'h', 'l', 'c']].to_numpy(float)
    with np.errstate(invalid='ignore'):
        bad = ~np.isfinite(px).all(1) | ~np.isfinite(df['v'].to_numpy(float)) | (px <= 0).any(1) | (px[:, 1] < px.max(1)) | (px[:, 2] > px.min(1))
    df = df[~bad].drop_duplicates('ts').sort_values('ts')
    if df.empty:
        raise ValueError('no usable minute rows')
    t0 = int(-(-int(df['ts'].iloc[0]) // DAY) * DAY)
    df = df[df['ts'] >= t0]
    n = int((end - t0) // MIN)
    if n <= 0 or df.empty:
        raise ValueError('the window holds no whole minute after a UTC midnight')
    pos = ((df['ts'].to_numpy() - t0) // MIN).astype(np.int64)
    gap = np.ones(n, bool)
    gap[pos] = False
    c = np.full(n, np.nan)
    c[pos] = df['c'].to_numpy(float)
    c = pd.Series(c).ffill().bfill().to_numpy()
    o, h, l = c.copy(), c.copy(), c.copy()
    o[pos], h[pos], l[pos] = df['o'].to_numpy(float), df['h'].to_numpy(float), df['l'].to_numpy(float)
    v = np.zeros(n)
    v[pos] = df['v'].fillna(0).to_numpy(float)
    tb = None
    if 'tb' in df.columns:
        tb = np.zeros(n)
        tb[pos] = df['tb'].fillna(0).to_numpy(float)
    return {'t0': t0, 'n': n, 'o': o, 'h': h, 'l': l, 'c': c, 'v': v, 'tb': tb, 'gap': gap}
