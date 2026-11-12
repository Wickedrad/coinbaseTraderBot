"""Live reader of the OR-HM1 heat-map readings (python/oracle/prereg/OR-HM1.md): a window of 1-minute bars in, the
event keys that fire at the last closed minute out, in the same spelling as the tables' `key` column
(`15m:RSI14=very low`, `1m:KVO>sig=below` ...).

It uses the engine's own vocabulary (oracle.heat_vocab), bucket and event rules (oracle.heat), and the zone edges
and price step stored in a coin's meta.json, so a level means live what it meant in the tables. Nothing here reads
or changes a heat table.

  grid(df)                 complete 1-minute grid from a UTC midnight to the last closed minute (gaps forward-filled)
  tf_codes(m, k, ...)      every reading's level codes on timeframe k (the last `window` bars, or the whole grid)
  active_keys(m, meta)     the keys firing at the grid's last minute close, per timeframe whose bar closed there
  events_at(R, rows)       the engine's event rows of a reading inside a row range (for parity checks)

Window. The first 250 bars of a timeframe carry no reading (WARM), the longest normalisation is a 500-bar z-score,
500 bars after a long outage are unused, and EMA / Wilder style lines remember older bars with a weight that decays.
WINDOW_BARS = 3000 bars per timeframe is the default (3000 one-hour bars = 125 days of minutes); the parity job
(heat_parity) measures how often a window gives the full-history level.

Entry convention of the tables: the reading is known at its bar's close; the measured entry is the next minute's open.
NEVER DOGE (a table for it does not exist).
"""
import json
import math
import os

import numpy as np
import pandas as pd

from oracle import heat
from oracle.common import DAY, MIN

WINDOW_BARS = 3000
STALE_BACK = heat.STALE_LONG[0] + heat.STALE_LONG[1] + heat.STALE + 2     # bars before the window whose gaps still matter


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


def _units(b: dict, step) -> dict:
    """The bars in whole price steps (heat.tick_units with the table's stored step): ties inside TA-Lib are then exact.
    Prices on a finer grid than the table's refine the unit by powers of ten; no stored step -> bars as they are."""
    if not step:
        return b
    step = float(step)
    on = lambda a, st: bool(np.abs(a / st - np.round(a / st)).max() <= 1e-4)
    for _ in range(6):
        if all(on(b[x], step) for x in ('o', 'h', 'l', 'c')):
            break
        step /= 10.0
    out = dict(b)
    for x in ('o', 'h', 'l', 'c'):
        out[x] = np.round(b[x] / step)
    return out


def tf_codes(m: dict, k: int, edges: dict = None, step=None, window: int = WINDOW_BARS, a_rows: tuple = None, want_bases: set = None) -> tuple:
    """Level codes of every reading on timeframe k, for the last `window` complete bars of the grid (window None: all).
    Returns (readings, edges_used, first_bar): readings as in heat.build_readings ({'name', 'k', 'codes', 'levels',
    'zones' | 'every' | 'cond', 'base'}), codes[i] belonging to bar first_bar + i.

    edges: {reading name: the four zone edges} from meta.json. edges None (parity only): the zone edges are taken from
    this grid's rows a_rows = (lo, hi), the way the engine takes them from split A.
    want_bases: only these reading names (without the level); None = all."""
    from oracle.heat_vocab import sign_codes, vocabulary
    nb = m['n'] // k
    s = 0 if window is None else max(0, nb - int(window))
    sub = {x: (None if m[x] is None else m[x][s * k:nb * k]) for x in ('o', 'h', 'l', 'c', 'v', 'tb')}
    sub['n'] = (nb - s) * k
    b = heat.resample(_units(sub, step), k)
    V, C, _ = vocabulary(b)
    g0 = max(0, s - STALE_BACK)                                    # gaps shortly before the window still make bars stale
    gb = m['gap'][g0 * k:nb * k].reshape(nb - g0, k).any(1)
    stale = pd.Series(gb.astype(np.float32)).rolling(heat.STALE + 1, min_periods=1).max().to_numpy() > 0
    run = pd.Series(gb.astype(np.int64)).groupby(np.cumsum(~gb)).cumsum().to_numpy()
    stale |= pd.Series((run > heat.STALE_LONG[0]).astype(np.float32)).rolling(heat.STALE_LONG[1] + 1, min_periods=1).max().to_numpy() > 0
    stale = stale[s - g0:]
    out, used = [], {}
    if a_rows is not None:
        bar_rows = (s + np.arange(nb - s)) * k + k - 1
        inA = (bar_rows >= a_rows[0]) & (bar_rows < a_rows[1])
    for vi in range(len(V)):
        name, typ, zero, x = V[vi]
        V[vi] = None                                                # (a whole-history series is large: drop it once used)
        full = f'{k}m:{name}'
        if want_bases is not None and full not in want_bases:
            continue
        x[stale] = np.nan
        if edges is None:
            xa = x[inA]
            xa = xa[np.isfinite(xa)]
            if len(xa) < 1000:
                continue
            zq = np.quantile(xa, heat.ZONE_Q)
            zq = [float(q) for q in zq] if zq[1] < zq[2] else None
        else:
            zq = edges.get(full)
        if zq is not None:
            used[full] = list(zq)
            out.append({'name': full, 'k': k, 'codes': heat.bucket(x, zq), 'levels': heat.ZONES, 'base': full, 'type': typ, 'zones': True})
        if zero:
            out.append({'name': full + ' sign', 'k': k, 'codes': sign_codes(x), 'levels': ['below 0', 'above 0'], 'base': full, 'type': typ})
    for name, codes, levels, every in C:
        full = f'{k}m:{name}'
        if want_bases is not None and full not in want_bases:
            continue
        codes[stale] = -1
        out.append({'name': full, 'k': k, 'codes': codes, 'levels': levels, 'base': full, 'every': every, 'cond': not every})
    return out, used, s


def _fires(R: dict, i: int = -1) -> list:
    """Level names of reading R whose event fires at bar i (heat.level_events for one bar)."""
    codes = R['codes']
    cur = int(codes[i])
    prev = int(codes[i - 1]) if len(codes) > 1 and (i == -1 or i > 0) else -1
    out = []
    for lv, side, lname in heat.event_levels(R):
        if cur != lv:
            continue
        if not R.get('every'):
            if prev == lv or prev < 0 or (side > 0 and not prev < lv) or (side < 0 and not prev > lv):
                continue
        out.append(lname)
    return out


def events_at(R: dict, lo: int, hi: int) -> list:
    """(minute row, key) of every event of reading R (whole-grid codes) with lo <= row < hi: the engine's own rule."""
    out = []
    for lv, side, lname in heat.event_levels(R):
        rows = heat.level_events(R, lv, side)
        for r in rows[(rows >= lo) & (rows < hi)]:
            out.append((int(r), f'{R["name"]}={lname}'))
    return out


def dominance_levels(dom: dict, day_ms: int) -> dict:
    """Levels of the dominance states known during UTC day `day_ms` (from the last COMPLETED day's close), as
    heat.context_readings. dom: {'BTC.D': Series or DataFrame(ts, c) of daily closes, 'USDT.D': ...}; a missing series
    or too little history gives no level. Returns {reading name: level}."""
    out, up = {}, {}
    last = int(day_ms) // DAY * DAY - DAY                                  # the last completed UTC day
    for sym in ('BTC.D', 'USDT.D'):
        d = dom.get(sym) if dom else None
        if d is None:
            continue
        if isinstance(d, pd.DataFrame):
            d = d[['ts', 'c']].drop_duplicates('ts').set_index('ts')['c']
        d = d.copy()
        d.index = (d.index // DAY) * DAY
        d = d.groupby(level=0).last()
        d = d[d.index <= last]
        if d.empty:
            continue
        d = d.reindex(np.arange(int(d.index.min()), last + DAY, DAY))
        r1 = d / d.shift(1) - 1
        sd = r1.rolling(60, min_periods=40).std().shift(1)
        z = {'1d': r1 / sd, '5d': (d / d.shift(5) - 1) / (sd * math.sqrt(5))}
        for nm in ('1d', '5d'):
            code = int(heat.bucket(np.array([z[nm].iloc[-1]], float), heat.DOM_Z)[0])
            if code >= 0:
                out[f'{sym} {nm}'] = heat.DOM_LV[code]
        up[sym] = float(r1.iloc[-1])
    if len(up) == 2 and all(math.isfinite(x) for x in up.values()):
        out['Dom 1d'] = ['BTC.D down, USDT.D down', 'BTC.D down, USDT.D up', 'BTC.D up, USDT.D down', 'BTC.D up, USDT.D up'][
            (up['BTC.D'] > 0) * 2 + (up['USDT.D'] > 0)]
    return out


def active_keys(m: dict, meta: dict, want: set = None, dom: dict = None, window: int = WINDOW_BARS, tfs=None, levels: bool = False,
                states: set = None) -> dict:
    """The event keys that fire at the close of the grid's last minute.

    m: grid(...) of one coin, ending at the last closed minute. meta: that coin's meta.json (edges, price_step).
    want: only these keys (the tables' `key` spelling); None = every key. dom: daily dominance closes for the context
    states (optional). Only timeframes whose bar closes at this minute are computed. levels=True also returns the level
    every computed reading holds now. states: reading names of ANY timeframe (a pair row's `conds`, e.g. '60m:ADX14',
    '5m:MOM10 sign', 'UTC4h') whose level at the last CLOSED bar of their own timeframe is wanted, whether or not that
    bar closes at this minute: the engine's heat.read_state, what a pair or triple cell conditions on.

    Returns {'ts': close time in ms (= the entry minute's open), 'closed': [timeframes], 'events': [keys],
             'no_reading': [timeframes whose last bar is stale after a data gap], 'levels': {reading: level},
             'states': {reading: level, or None when it has no reading now}}."""
    n, t0 = m['n'], m['t0']
    ts = t0 + n * MIN
    edges, step = meta.get('edges', {}), meta.get('price_step')
    bases = None if want is None else {k.rsplit('=', 1)[0] for k in want}
    bases = None if bases is None else bases | {b[:-5] for b in bases if b.endswith(' sign')}
    ev, closed, dead, lv_now = [], [], [], {}
    st = None if states is None else {s: None for s in states}
    for k in (tfs or heat.TFS):
        if n // k < 2:
            continue
        closes = n % k == 0
        sb = set() if st is None else {(s[:-5] if s.endswith(' sign') else s) for s in st if s.startswith(f'{k}m:')}
        if not closes and not sb:
            continue
        wb = (None if bases is None else bases | sb) if closes else sb
        R, _, _ = tf_codes(m, k, edges, step, window, want_bases=wb)   # the bars of k complete at this minute: the last one is the last closed bar
        if closes:
            closed.append(k)
            if m['gap'][n - k:n].any():
                dead.append(k)
        for r in R:
            if closes:
                for lname in _fires(r):
                    ev.append(f'{r["name"]}={lname}')
                if levels and r['codes'][-1] >= 0:
                    lv_now[r['name']] = r['levels'][int(r['codes'][-1])]
            if st is not None and r['name'] in st and r['codes'][-1] >= 0:
                st[r['name']] = r['levels'][int(r['codes'][-1])]
    want_ctx = st is not None and any(not s[:1].isdigit() for s in st)
    if n % 15 == 0 or want_ctx:
        ctx = {'UTC4h': f'{4 * ((n // 240) % 6):02d}-{4 * ((n // 240) % 6) + 4:02d}'}
        ctx.update(dominance_levels(dom, ts) if dom else {})
        for name, lv in ctx.items():
            if n % 15 == 0:                                         # context states fire on every 15-minute close while they hold
                if lv not in heat.NEUTRAL:
                    ev.append(f'{name}={lv}')
                if levels:
                    lv_now[name] = lv
            if st is not None and name in st:
                st[name] = lv
    fine = set() if st is None else {s for s in st if s in ('UTC1h', 'NY30m', 'Weekday')}
    fine |= {k.split('=', 1)[0] for k in (want or ()) if k.split('=', 1)[0] in ('UTC1h', 'NY30m', 'Weekday')}
    if fine:                                                        # the finer clock of oracle.heat_clock (not in the tables' own vocabulary)
        from oracle.heat_clock import levels_at
        for name, lv in levels_at(ts).items():
            if st is not None and name in st:
                st[name] = lv
            if n % 15 == 0 and want is not None and f'{name}={lv}' in want:
                ev.append(f'{name}={lv}')                           # a clock level on its own: only when asked for
    if want is not None:
        ev = [k for k in ev if k in want]
    out = {'ts': int(ts), 'closed': closed, 'events': sorted(set(ev)), 'no_reading': dead}
    if levels:
        out['levels'] = lv_now
    if st is not None:
        out['states'] = st
    return out


def load_meta(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def main():
    """python3 -m oracle.heat_live --minutes <1m.csv: ts,o,h,l,c,v[,tb]> --meta <meta.json> [--want <json list of keys>]
    Prints the keys firing at the last closed minute of the file."""
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--minutes', required=True)
    ap.add_argument('--meta', required=True)
    ap.add_argument('--want', default='')
    ap.add_argument('--window', type=int, default=WINDOW_BARS)
    ap.add_argument('--levels', action='store_true')
    a = ap.parse_args()
    if 'DOGE' in os.path.basename(a.minutes).upper() or 'DOGE' in os.path.basename(os.path.dirname(os.path.abspath(a.meta))).upper():
        raise SystemExit('never DOGE')
    want = set(json.load(open(a.want))) if a.want else None
    df = pd.read_csv(a.minutes)
    need = (a.window + 1) * 60 * MIN + 2 * DAY
    df = df[df['ts'] >= int(df['ts'].max()) - need]
    print(json.dumps(active_keys(grid(df), load_meta(a.meta), want=want, window=a.window, levels=a.levels)))


if __name__ == '__main__':
    main()
