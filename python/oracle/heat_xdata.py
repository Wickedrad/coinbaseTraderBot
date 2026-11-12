"""OR-HM2: the extra data and the new readings (python/oracle/prereg/OR-HM2.md; build plan section 1).

  python3 -m oracle.heat_xdata inventory --listing <dir of <COIN>.json, or one {coin: [...]} .json> --dom <research/btcd_fractal/data>
                                        [--out inventory.json]
  python3 -m oracle.heat_xdata stamps <csv> [<csv> ...] [--cut] [--daily]
  python3 -m oracle.heat_xdata funding-check --spot <1m.csv> --perp <um 1m.csv> --funding <funding.csv> [--out <json>]

Every reading here is causal: its value at row i uses only what is KNOWN at row i's close, t0 + (i + 1) minutes (the
entry is the next minute's open). When a row of an extra file becomes known (OR-HM2, Data):
  bars (perp, Coinbase, BTCDOM; stamped at their open)   stamp + their length
  funding (ts = calc_time)                                calc_time + 1 minute (at row i only when calc_time <= the open of minute i)
  open interest (ts = create_time)                        create_time + 5 minutes, carried at most 10 minutes
  daily markets                                           stamp + 24 hours (a daily bar never closes later than that)
  calendar                                                a scheduled event in advance; an unscheduled one from the close of
                                                          its own minute (ts + 1 minute)
  order book snapshot                                     its stamp; NA when over 5 minutes old

Contents:
  load_extra / known_ms        the strict loaders (13-digit ms, nothing at or after HEAT_END, never DOGE)
  inventory / ts_span          the preflight's source inventory: every source feeds a family or carries its written reason
  funding_stamp_check          the funding stamp is the settlement time, not the start of the period it pays for
  joint_flip                   one coin flip per absolute minute, applied to every price path of a twin job
  on_grid / other_on_grid      extra minute bars and the other coins on the job coin's grid
  zone / state / stale_rows    the engine's reading dict, A-only zone edges, the engine's stale rule on every window read
  *_readings, extra_readings   the new readings: Position, Clock, Cross-coin, Volatility, Flow, Perp, Open interest, Daily
                               markets, BTCDOM, Coinbase, Book, Macro
  zs_readings                  the learner's side-aware zone events (ZS:<name>)
  merge_aliases                readings that are copies under two names become one reading with aliases
  levels_at                    the same levels at the last closed minute of a live window (stored edges and norm tables)
A twin flips directions only: the levels that are not a direction (basis level, funding, open interest changes, BTCDOM,
daily markets, macro, position, clock, book) are computed from the real data. NEVER DOGE.
"""
import argparse
import json
import math
import os
import sys

import numpy as np
import pandas as pd

from oracle import heat
from oracle.common import DAY, MIN, ms

HOUR = 60 * MIN
COINS = ['BTC', 'ETH', 'SOL', 'XRP']                         # never DOGE
MS_LO = ms('2019-01-01')                                      # the earliest stamp an extra minute-like file may hold
MS_DIGITS = (10 ** 12, 10 ** 13)                              # a 13-digit millisecond stamp
MAIN_HMAX = 60                                                # the main grid's longest horizon (where split A's rows end)
MIN_A = 1000                                                  # A values a zone reading needs (the engine's rule)
SD_DAY = 1440                                                 # the 1-day window of the return sd
BAR_LEN = {'perp1m': MIN, 'cb1m': MIN, 'idx1h': HOUR}
FUND_KNOWN = MIN
FUND_MAX_AGE = 9 * HOUR                                       # a settlement older than this (a hole in the file) gives NA
OI_KNOWN = 5 * MIN
OI_CARRY = 10 * MIN
OI_MIN_SHARE = 0.9                                            # known share of the day before that the OI sd needs
BOOK_MAX_AGE = 5 * MIN
DAILY_KNOWN = DAY
DMKT_MAX_AGE = 5 * DAY                                        # weekends and holidays; an older last bar gives NA
DMKT_NAMES = ['ETH.D', 'OTHERS.D', 'USDC.D', 'TOTAL', 'TOTAL2', 'TOTAL3', 'DXY', 'SPX', 'US10Y', 'USDJPY', 'EURUSD', 'GBPUSD', 'USDCNY']
R830_KINDS = ('CPI', 'NFP', 'PPI')
MACRO_LV = ['none', '30-1 before', '0-14 after', '15-59 after', '60-239 after']
POS_LV = {'POS:QPos': [f'm{i:02d}' for i in range(15)], 'POS:QPhase': ['m00-04', 'm05-09', 'm10-14'],
          'POS:HourQ': ['h00-14', 'h15-29', 'h30-44', 'h45-59']}
BREADTH_LV = ['3 down', '2 down', '1 down', 'mid', '1 up', '2 up', '3 up']
JUMP_LV = ['none', 'up', 'down']
FUNDCLOCK_LV = ['under 15m', '15-60m', '1-4h', '4-8h']
PXQUAD_LV = ['new longs', 'short covering', 'new shorts', 'long liquidation']
ZS_LEVELS = ['none', 'very low', 'low (falling in)', 'low (recovering)', 'high (rising in)', 'high (cooling)', 'very high']
MERGE_AGREE = 0.995
FLIP_ORIGIN = ms('2019-01-01')                                # minutes before a job coin's first minute take a second stream from here
PREFIX_FAMILY = [('POS:', 'position'), ('X.', 'cross'), ('X:', 'cross'), ('VOL:', 'vol'), ('FLOW:', 'flow'), ('PERP:', 'perp'),
                 ('OI:', 'oi'), ('DMKT:', 'dmkt'), ('IDX:', 'idx'), ('CB:', 'cb'), ('BOOK:', 'book'), ('MACRO:', 'macro'), ('ZS:', 'zs'),
                 ('GBM.', 'model')]
CLOCK_NAMES = ('UTC1h', 'NY30m', 'Weekday')


def _no_doge(*xs):
    for x in xs:
        if x is not None and 'DOGE' in str(x).upper():
            raise SystemExit(f'NEVER DOGE: {x}')


# ------------------------------------------------------------------------------------------------------------ loaders
KIND_COLS = {'perp1m': ['o', 'h', 'l', 'c', 'v'], 'cb1m': ['o', 'h', 'l', 'c', 'v'], 'idx1h': ['o', 'h', 'l', 'c'],
             'funding': ['rate'], 'oi': ['oi'], 'daily': ['c'], 'book': [], 'calendar': ['ts_utc', 'kind', 'scheduled']}
BOOK_COLS = [('bid_depth_1pct', 'ask_depth_1pct'), ('bid_1pct', 'ask_1pct'), ('bids_1pct', 'asks_1pct'), ('bid_depth', 'ask_depth'), ('bid', 'ask')]


def known_ms(kind: str, ts, scheduled=None) -> np.ndarray:
    """The time (ms) each row of an extra file becomes known. A value is used at row i only when known_ms <= the close
    of row i (t0 + (i + 1) min). Calendar: a scheduled event is known in advance (0); an unscheduled one from the close
    of its own minute."""
    ts = np.asarray(ts, np.int64)
    if kind in BAR_LEN:
        return ts + BAR_LEN[kind]
    if kind == 'funding':
        return ts + FUND_KNOWN
    if kind == 'oi':
        return ts + OI_KNOWN
    if kind == 'daily':
        return ts + DAILY_KNOWN
    if kind == 'book':
        return ts.copy()
    if kind == 'calendar':
        sch = np.ones(len(ts), bool) if scheduled is None else np.asarray(scheduled, bool)
        return np.where(sch, np.int64(0), ts + MIN)
    raise ValueError(f'unknown kind {kind}')


def _check_ms(ts: np.ndarray, path: str):
    """Refuse a time column that is not 13-digit milliseconds (seconds would pass the HEAT_END cut with their 2026
    rows; microseconds would lose all of 2025)."""
    if len(ts) == 0:
        return
    t = np.asarray(ts, float)
    bad = ~np.isfinite(t) | (t != np.round(t)) | (t < MS_DIGITS[0]) | (t >= MS_DIGITS[1])
    if bad.any():
        raise SystemExit(f'{path}: {int(bad.sum()):,} time stamps are not 13-digit milliseconds (first {t[bad][:3].tolist()})')


def _calendar(df: pd.DataFrame, path: str) -> pd.DataFrame:
    """ts_utc (ISO) -> ms; the ET date and time must give the same UTC instant (daylight saving followed); the ET day's
    bounds in ms for MACRO:ReleaseDay."""
    ny = 'America/New_York'
    tms = lambda x: int(round(pd.Timestamp(x).timestamp() * 1000))
    ts = np.array([tms(pd.Timestamp(x).tz_convert('UTC') if pd.Timestamp(x).tzinfo else pd.Timestamp(x).tz_localize('UTC')) for x in df['ts_utc']], np.int64)
    if {'date_et', 'time_et'} <= set(df.columns):
        lt = np.array([tms(pd.Timestamp(f'{d} {t}').tz_localize(ny)) for d, t in zip(df['date_et'], df['time_et'])], np.int64)
        if (lt != ts).any():
            raise SystemExit(f'{path}: {int((lt != ts).sum())} rows whose ET date and time do not give their ts_utc (daylight saving)')
        dates = [pd.Timestamp(d) for d in df['date_et']]
    else:
        dates = [pd.Timestamp(int(t), unit='ms', tz='UTC').tz_convert(ny).tz_localize(None).normalize() for t in ts]
    day_lo = np.array([tms(d.tz_localize(ny)) for d in dates], np.int64)                  # the ET day's midnight (23 / 25-hour days kept)
    day_hi = np.array([tms((d + pd.Timedelta(days=1)).tz_localize(ny)) for d in dates], np.int64)
    sch = df['scheduled'].map(lambda x: str(x).strip().lower() in ('true', '1', 'yes')).to_numpy(bool)
    out = pd.DataFrame({'ts': ts, 'kind': df['kind'].astype(str).str.strip().to_numpy(), 'scheduled': sch, 'day_lo': day_lo, 'day_hi': day_hi})
    for c in ('date_et', 'time_et', 'source'):
        if c in df.columns:
            out[c] = df[c].to_numpy()
    return out


def load_extra(path: str, kind: str, strict: bool = True) -> pd.DataFrame:
    """One extra file as a DataFrame sorted by ts (ms), with its known time in 'known'.

    kind: 'perp1m' / 'cb1m' (ts, o, h, l, c, v[, tb]), 'idx1h' (BTCDOM: ts, o, h, l, c[, v]), 'funding' (ts = calc_time,
    rate), 'oi' (ts = create_time, oi[, oi_usd]), 'daily' (ts, c[, o, h, l, v]; research/btcd_fractal/data), 'book' (ts
    and the bid / ask depth within 1% of the mid) or 'calendar' (date_et, time_et, ts_utc, kind, scheduled).
    Refuses a path naming DOGE and a time column that is not 13-digit milliseconds. strict: refuses any row at or after
    HEAT_END (the workflow cuts the file first) or before 2019-01-01; otherwise drops them. 'daily': a bar whose known
    time (stamp + 24 h) is at or after HEAT_END is always dropped (the shared daily files run past it by design).
    Broken rows (empty or non-positive prices, a high below the open or close ...) are dropped and counted."""
    _no_doge(path)
    if kind not in KIND_COLS:
        raise ValueError(f'unknown kind {kind}')
    df = pd.read_csv(path)
    if kind == 'calendar':
        miss = [c for c in KIND_COLS[kind] if c not in df.columns]
        if miss:
            raise SystemExit(f'{path}: no column {miss}')
        df = _calendar(df, path)
    elif 'ts' not in df.columns:
        raise SystemExit(f'{path}: no ts column')
    attrs = {'kind': kind, 'path': str(path), 'rows_in': int(len(df))}
    ts = pd.to_numeric(df['ts'], errors='coerce').to_numpy(float)
    keep = np.isfinite(ts)
    _check_ms(ts[keep], path)
    df = df[keep].copy()
    df['ts'] = ts[keep].astype(np.int64)
    if kind == 'daily':
        late = (df['ts'].to_numpy() + DAILY_KNOWN) >= heat.HEAT_END
        attrs['dropped_late'] = int(late.sum())
        df = df[~late]
    else:
        early = df['ts'].to_numpy() < MS_LO
        late = df['ts'].to_numpy() >= heat.HEAT_END
        if strict and (late.any() or early.any()):
            raise SystemExit(f'{path}: {int(late.sum()):,} rows at or after {pd.Timestamp(heat.HEAT_END, unit="ms")} and {int(early.sum()):,} '
                             f'before 2019-01-01: cut the file first')
        attrs['dropped_late'] = int(late.sum())
        df = df[~late & ~early]
    if kind == 'book':
        pair = next((p for p in BOOK_COLS if set(p) <= set(df.columns)), None)
        if pair is None:
            raise SystemExit(f'{path}: no bid / ask depth columns (one of {BOOK_COLS})')
        df = df.rename(columns={pair[0]: 'bid', pair[1]: 'ask'})
        need = ['bid', 'ask']
    elif kind == 'calendar':
        need = []
    else:
        need = KIND_COLS[kind]
        miss = [c for c in need if c not in df.columns]
        if miss:
            raise SystemExit(f'{path}: no column {miss}')
    with np.errstate(invalid='ignore'):
        x = df[need].apply(pd.to_numeric, errors='coerce').to_numpy(float) if need else np.zeros((len(df), 0))
        bad = ~np.isfinite(x).all(1)
        if kind in ('perp1m', 'cb1m', 'idx1h'):
            px = df[['o', 'h', 'l', 'c']].apply(pd.to_numeric, errors='coerce').to_numpy(float)
            bad |= (px <= 0).any(1) | (px[:, 1] < px.max(1)) | (px[:, 2] > px.min(1))
            if kind != 'idx1h':
                bad |= df['v'].to_numpy(float) < 0
        elif kind in ('oi', 'daily'):
            bad |= x[:, 0] <= 0
        elif kind == 'book':
            bad |= (x < 0).any(1) | (x.sum(1) <= 0)
    attrs['bad_rows'] = int(bad.sum())
    df = df[~bad].sort_values('ts', kind='stable').drop_duplicates('ts').reset_index(drop=True)
    for c in need + [c for c in ('tb', 'oi_usd', 'o', 'h', 'l', 'v') if c in df.columns and c not in need]:
        df[c] = pd.to_numeric(df[c], errors='coerce').astype(float)
    df['known'] = known_ms(kind, df['ts'].to_numpy(), df['scheduled'].to_numpy() if kind == 'calendar' else None)
    df.attrs.update(attrs)
    return df


def ts_span(path: str, col: int = 0) -> dict:
    """First and last data-row stamps of a CSV (read from the file's two ends, not the whole file) and whether both are
    13-digit milliseconds. For the preflight: a seconds file would keep its 2026 rows through the awk cut."""
    with open(path, 'rb') as f:
        f.readline()
        first = f.readline().decode().strip()
        f.seek(0, 2)
        size = f.tell()
        f.seek(max(0, size - 65536))
        tail = [x for x in f.read().decode(errors='replace').splitlines() if x.strip()]
    last = tail[-1] if tail else ''
    out = {'path': path, 'first': None, 'last': None, 'ms13': False}
    try:
        a, b = int(float(first.split(',')[col])), int(float(last.split(',')[col]))
    except (ValueError, IndexError):
        return out
    out.update(first=a, last=b, ms13=all(MS_DIGITS[0] <= x < MS_DIGITS[1] for x in (a, b)),
               first_utc=str(pd.Timestamp(a, unit='ms')) if MS_DIGITS[0] <= a < MS_DIGITS[1] else None,
               last_utc=str(pd.Timestamp(b, unit='ms')) if MS_DIGITS[0] <= b < MS_DIGITS[1] else None)
    return out


# ---------------------------------------------------------------------------------------------------------- inventory
REQUIRED = {'binance-1m': '1m.csv', 'binance-um': '1m.csv', 'binance-funding': 'funding.csv', 'binance-oi': 'oi.csv'}
SOURCE_FAMILY = {
    'binance-1m': ('coin', 'Binance spot 1-minute bars of the four coins: the engine readings, VOL, FLOW and the cross-coin readings'),
    'binance-um': ('perp', 'Binance USD-M perpetual 1-minute bars: PERP:Basis, BasisChg15, Lead1, Lead5'),
    'binance-funding': ('perp', 'settled funding rates (ts = calc_time): PERP:FundZ, FundClock'),
    'binance-oi': ('oi', 'open interest every 5 minutes (ts = create_time): OI:Chg15, Chg60, PxQuad60'),
    'binance-index': ('idx', 'Binance BTCDOM hourly index: IDX:BTCDOM1h, BTCDOM4h'),
    'coinbase-1m': ('cb', 'Coinbase 1-minute bars: CB:Lead1, Lead5, PremChg15'),
    'coinbase': ('cb', 'Coinbase bars: the 1-minute file feeds CB:Lead1, Lead5, PremChg15'),
}
SOURCE_NOT_USED = {
    'binance-1h': 'hourly spot bars of the four coins: the 1-minute bars hold them',
    'binance': 'Binance spot bars of other timeframes: the 1-minute bars hold them',
}
BOOK_WORDS = ('book', 'depth')
DAILY_ROLE = {**{n: ('dmkt', f'daily markets: DMKT:{n}1d') for n in DMKT_NAMES},
              'BTC.D': ('dominance', 'HM1 context readings (heat.context_readings): BTC.D 1d / 5d, Dom 1d'),
              'USDT.D': ('dominance', 'HM1 context readings (heat.context_readings): USDT.D 1d / 5d, Dom 1d')}
DAILY_NOT_USED = {**{n: 'stamps are period dates, not release times: any reading of them would leak'
                     for n in ('M2', 'CNM2', 'EUM2', 'GBM2', 'JPM2', 'FEDBS', 'TGA', 'RRP')},
                  'STABLES': 'starts May 2025: no build rows',
                  **{n: 'a copy of BTC.D' for n in ('BTCD_CAP', 'BTCD_CMC', 'BTCD_SPLICED')},
                  'BTCUSD': 'the 1-minute bars hold it', 'ETHBTC': 'the 1-minute bars hold it'}
DOM_OTHER_FILES = {'caps_report.json': 'a report on the dominance sources, not a series',
                   'cmc_raw_sample.json': 'a raw sample of a dominance source, not a series'}
BOOKKEEPING = ('manifest.json', 'checked.json')


def _is_bookkeeping(name: str) -> bool:
    """Download bookkeeping at the top of a coin folder: manifest.json, checked.json and the per-source download
    manifests (binance-manifest-<source>.json). They list what was downloaded, they hold no series."""
    return name in BOOKKEEPING or (name.endswith('.json') and 'manifest' in name.lower())


def _entries(x) -> list:
    """rclone lsjson entries (dicts with Path / IsDir) or plain paths -> relative file paths."""
    out = []
    for e in x or []:
        if isinstance(e, dict):
            if e.get('IsDir'):
                continue
            p = e.get('Path') or e.get('Name')
        else:
            p = str(e)
        if p:
            out.append(p.strip('/'))
    return sorted(set(out))


def inventory(drive_listing: dict, dom_dir) -> dict:
    """The preflight's source inventory (OR-HM2, Data: "Unchecked sources and the inventory").

    drive_listing: {coin: the listing of raw/perp-ta-history/<coin>/ (rclone lsjson -R entries, or relative paths)}.
    dom_dir: research/btcd_fractal/data (a directory, or a list of its file names).
    Every source folder and every daily file is mapped to the family it feeds or to its "Not used" reason. An unmapped
    source, or a missing coin, perp, funding or open-interest file of any of the four coins, makes ok False (the
    preflight stops). Inventory-found families (BTCDOM, Coinbase minutes, order book) are listed under 'found'."""
    out = {'sources': [], 'daily': [], 'missing': [], 'unmapped': [], 'found': {'btcdom': [], 'cb': {}, 'book': {}}, 'ok': False}
    for coin in COINS:
        files = _entries((drive_listing or {}).get(coin))
        have = set(files)
        for fam, name in REQUIRED.items():
            if f'{fam}/{coin}/{name}' not in have:
                out['missing'].append(f'raw/perp-ta-history/{coin}/{fam}/{coin}/{name}')
        by_folder = {}
        for p in files:
            by_folder.setdefault(p.split('/', 1)[0] if '/' in p else '.', []).append(p)
        for folder, fs in sorted(by_folder.items()):
            row = {'coin': coin, 'folder': folder, 'files': len(fs)}
            key = folder.lower()
            if folder == '.':
                row.update(family=None, reason='files at the top of the coin folder: ' + ', '.join(os.path.basename(f) for f in fs[:5]))
                stray = [f for f in fs if not _is_bookkeeping(os.path.basename(f))]
                if stray:
                    out['unmapped'] += [f'{coin}/{f}' for f in stray]
                    row['reason'] = None
            elif 'DOGE' in folder.upper():
                row.update(family=None, reason='never DOGE: not read')
            elif key in SOURCE_FAMILY:
                fam, why = SOURCE_FAMILY[key]
                used = [f for f in fs if 'DOGE' not in f.upper() and f.endswith('.csv') and (
                    (fam in ('coin', 'perp', 'oi') and f in (f'{folder}/{coin}/{REQUIRED.get(key, "")}',))
                    or (fam == 'idx' and f.endswith('BTCDOM/1h.csv'))
                    or (fam == 'cb' and f == f'{folder}/{coin}/1m.csv'))]
                if fam == 'cb' and not used:
                    row.update(family=None, reason='Coinbase bars of other timeframes, no 1-minute file: the Binance minutes hold them')
                else:
                    row.update(family=fam, reason=why, used=used)
                    if fam == 'idx':
                        out['found']['btcdom'] += [f'{coin}/{f}' for f in used]
                    elif fam == 'cb':
                        out['found']['cb'][coin] = f'{coin}/{used[0]}'
                row['not_used'] = sorted(set(fs) - set(row.get('used', [])))
            elif key in SOURCE_NOT_USED:
                row.update(family=None, reason=SOURCE_NOT_USED[key])
            elif any(w in key for w in BOOK_WORDS):
                used = [f for f in fs if f.endswith('.csv') and f'/{coin}/' in f'/{f}']
                row.update(family='book' if used else None, reason='order book snapshots: BOOK:Imb' if used else None, used=used)
                if used:
                    out['found']['book'][coin] = f'{coin}/{used[0]}'
                else:
                    out['unmapped'].append(f'{coin}/{folder}')
            else:
                row.update(family=None, reason=None)
                out['unmapped'].append(f'{coin}/{folder}')
            out['sources'].append(row)
    names = sorted(os.listdir(dom_dir)) if isinstance(dom_dir, str) and os.path.isdir(dom_dir) else sorted(dom_dir or [])
    for f in names:
        nm = f[:-len('_1d.csv')] if f.endswith('_1d.csv') else None
        if nm in DAILY_ROLE:
            fam, why = DAILY_ROLE[nm]
        elif nm in DAILY_NOT_USED:
            fam, why = None, DAILY_NOT_USED[nm]
        elif f in DOM_OTHER_FILES:
            fam, why = None, DOM_OTHER_FILES[f]
        else:
            fam, why = None, None
            out['unmapped'].append(f'research/btcd_fractal/data/{f}')
        out['daily'].append({'file': f, 'family': fam, 'reason': why})
    have_daily = {d['file'] for d in out['daily']}
    out['missing'] += [f'research/btcd_fractal/data/{n}_1d.csv' for n in DMKT_NAMES if f'{n}_1d.csv' not in have_daily]
    out['found']['btcdom'] = sorted(set(out['found']['btcdom']))
    out['ok'] = not out['missing'] and not out['unmapped']
    return out


# ------------------------------------------------------------------------------------------------------- grids, flips
def split_rows(t0: int, n: int, s: str = 'A', hmax: int = MAIN_HMAX) -> tuple:
    """(lo, hi) minute rows of split s on a grid starting at t0, as heat.Grid takes them (hmax 60: the main grid)."""
    a, b = heat.SPLITS[s]
    lo = max(0, int(np.ceil((a - t0) / MIN)) - 1)
    hi = max(lo, min(int((b - hmax * MIN - t0) // MIN), n))
    return lo, hi


def on_grid(m: dict, df: pd.DataFrame, cols=('o', 'h', 'l', 'c', 'v', 'tb')) -> dict:
    """Minute bars of an extra file (perp, Coinbase) on m's grid (t0, n): a missing minute or a minute before the
    file's first row is a gap; gaps after the first row are forward-filled (o = h = l = c = the last close, volume 0),
    rows before it are NaN. Returns {'t0', 'n', 'gap', 'first', <cols>} (tb None when the file has none)."""
    t0, n = int(m['t0']), int(m['n'])
    ts = df['ts'].to_numpy(np.int64)
    off = ts - t0
    keep = (off >= 0) & (off % MIN == 0) & (off < n * MIN)
    pos = (off[keep] // MIN).astype(np.int64)
    d = df[keep]
    gap = np.ones(n, bool)
    gap[pos] = False
    first = int(pos.min()) if len(pos) else n
    c = np.full(n, np.nan)
    c[pos] = d['c'].to_numpy(float)
    c = pd.Series(c).ffill().to_numpy()
    out = {'t0': t0, 'n': n, 'gap': gap, 'first': first, 'c': c, 'off_grid': int((~keep & (off >= 0) & (off < n * MIN)).sum())}
    for x in ('o', 'h', 'l'):
        if x in cols:
            a = c.copy()
            a[pos] = d[x].to_numpy(float)
            out[x] = a
    for x in ('v', 'tb'):
        if x in cols:
            if x not in d.columns:
                out[x] = None
                continue
            a = np.zeros(n)
            a[pos] = d[x].fillna(0).to_numpy(float)
            a[:first] = np.nan
            out[x] = a
    return out


def other_on_grid(m: dict, mo: dict) -> dict:
    """Another coin's minute arrays on this grid: own row i holds O's minute at the same UTC time (row i - off, off =
    (mo['t0'] - m['t0']) // MIN); NaN (gap True) before O's first minute and after its last. On a twin, mo is first
    passed through joint_flip."""
    off = (int(mo['t0']) - int(m['t0'])) // MIN
    n = int(m['n'])
    out = {'t0': m['t0'], 'n': n, 'off': off}
    for x in ('o', 'h', 'l', 'c', 'v', 'tb', 'tick'):
        if mo.get(x) is None:
            out[x] = None
            continue
        out[x] = shift(np.asarray(mo[x], float), off, n, np.nan)
    out['gap'] = shift(np.asarray(mo['gap'], bool), off, n, True)
    return out


def shift(x: np.ndarray, off: int, n: int, fill):
    """x on a grid whose row 0 is this grid's row `off` -> this grid's n rows (fill outside)."""
    out = np.full(n, fill, dtype=np.asarray(x).dtype)
    lo, hi = max(0, off), min(n, off + len(x))
    if hi > lo:
        out[lo:hi] = x[lo - off:hi - off]
    return out


def _flip_bars(m: dict, s: np.ndarray) -> dict:
    """heat.make_twin's algebra with a given sign per minute (bit for bit the engine's when s is its sequence). A series
    with NaN before its first row (perp, Coinbase) is flipped from its first finite close on."""
    c = m['c']
    fin = np.isfinite(c)
    f = int(np.argmax(fin)) if fin.any() else len(c)
    if f > 0:
        sub = {x: (m[x][f:] if isinstance(m.get(x), np.ndarray) and len(m[x]) == len(c) else m.get(x)) for x in m}
        sub['n'] = len(c) - f
        tw = _flip_bars(sub, s[f:]) if f < len(c) else sub
        out = dict(m)
        for x in ('o', 'h', 'l', 'c', 'tb'):
            if m.get(x) is not None:
                out[x] = np.r_[np.full(f, np.nan), tw[x]]
        return out
    n = len(c)
    prev = np.r_[c[0], c[:-1]]
    with np.errstate(divide='ignore', invalid='ignore'):
        rc, ro, rh, rl = (np.log(m[x] / prev) for x in ('c', 'o', 'h', 'l'))
        c2 = np.exp(np.log(c[0]) + np.cumsum(s * rc))
        p2 = np.r_[c2[0], c2[:-1]]
        out = dict(m)
        sig = lambda x: np.round(x * 10.0 ** (11 - np.floor(np.log10(x)))) / 10.0 ** (11 - np.floor(np.log10(x)))
        out['c'] = sig(c2)
        out['o'] = sig(p2 * np.exp(s * ro))
        out['h'] = np.maximum(sig(p2 * np.exp(np.where(s > 0, rh, -rl))), np.maximum(out['o'], out['c']))
        out['l'] = np.minimum(sig(p2 * np.exp(np.where(s > 0, rl, -rh))), np.minimum(out['o'], out['c']))
    if m.get('tb') is not None:
        out['tb'] = np.where(s > 0, m['tb'], m['v'] - m['tb'])
    assert len(s) == n
    return out


class JointFlip:
    """One seeded coin flip per ABSOLUTE minute (OR-HM2, "one joint coin flip"). On the job coin's minutes it is
    heat.make_twin's own sequence (rng([20261111, seed]), first sign +1), so the job coin's twin is make_twin(m, seed)
    bit for bit, and a coin whose grid starts and ends with the job coin's gets exactly HM1's twin of the same seed.
    Minutes before the job coin's first minute take a second stream (rng([20261111, seed, 1]), indexed from
    2019-01-01), minutes after its last a third (rng([20261111, seed, 2])). Calling it on a minutes dict (another coin,
    the perp or Coinbase bars on any grid) flips that path with the same signs, taker volume swapped on flipped minutes."""

    def __init__(self, seed: int, t0_job: int, n_job: int):
        self.seed, self.t0, self.n = int(seed), int(t0_job), int(n_job)
        rng = np.random.default_rng([20261111, self.seed])
        self.s = rng.choice(np.array([-1.0, 1.0]), self.n)
        self.s[0] = 1.0
        self._pre = self._post = None

    def signs(self, t0: int, n: int) -> np.ndarray:
        if (int(t0) - self.t0) % MIN:
            raise ValueError('a grid off the minute')
        a = (int(t0) - self.t0) // MIN + np.arange(int(n), dtype=np.int64)
        out = np.empty(int(n))
        inj = (a >= 0) & (a < self.n)
        out[inj] = self.s[a[inj]]
        if (a < 0).any():
            if self._pre is None:
                npre = (self.t0 - FLIP_ORIGIN) // MIN
                if npre <= 0:
                    raise ValueError('a job coin starting before 2019-01-01')
                self._pre = np.random.default_rng([20261111, self.seed, 1]).choice(np.array([-1.0, 1.0]), int(npre))
            j = (self.t0 - FLIP_ORIGIN) // MIN + a[a < 0]
            if (j < 0).any():
                raise ValueError('a minute before 2019-01-01')
            out[a < 0] = self._pre[j]
        if (a >= self.n).any():
            npost = max(0, (heat.HEAT_END - self.t0) // MIN - self.n) + 31 * 1440
            if self._post is None:
                self._post = np.random.default_rng([20261111, self.seed, 2]).choice(np.array([-1.0, 1.0]), int(npost))
            j = a[a >= self.n] - self.n
            if (j >= len(self._post)).any():
                raise ValueError('a minute past HEAT_END')
            out[a >= self.n] = self._post[j]
        return out

    def twin_of(self, mo: dict) -> dict:
        return _flip_bars(mo, self.signs(mo['t0'], mo['n']))

    __call__ = twin_of


def joint_flip(seed: int, t0_job: int, n_job: int) -> JointFlip:
    """The job coin's heat.make_twin sign sequence indexed by absolute minute (see JointFlip)."""
    return JointFlip(seed, t0_job, n_job)


def other_meta_key(other: str, twin: int, m: dict, mo: dict):
    """Which main-run meta.json zones another coin's direct readings (X.O:RSI14, X.O:TakerBuy): '<O>' on a real job;
    on twin N '<O>-twinN' when O's grid is the job coin's (same first minute and length: the joint flip is then HM1's
    twin of O, bit for bit); otherwise None, and the edges come from O's own (flipped) A bars."""
    _no_doge(other)
    if not twin:
        return other
    return f'{other}-twin{int(twin)}' if (int(mo['t0']), int(mo['n'])) == (int(m['t0']), int(m['n'])) else None


# ------------------------------------------------------------------------------------------- rolling sums, stale rule
def roll_sum(x, W: int, min_count: int = None):
    """Sum over the W rows ending at each row from cumsums (the value at row i reads rows i-W+1..i only). NaN until
    a whole window exists, and where the window holds fewer than min_count finite values (default: all W).
    Returns (sum, count of finite values)."""
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


def lag(x: np.ndarray, k: int) -> np.ndarray:
    """x[i - k] at row i (NaN for the first k rows)."""
    x = np.asarray(x, float)
    return np.r_[np.full(min(k, len(x)), np.nan), x[:len(x) - k]] if k > 0 else x


def _runlen(gap: np.ndarray) -> np.ndarray:
    """Length of the gap run ending at each row (the engine's groupby formula, in numpy: heat_vocab._runs)."""
    cs = np.cumsum(np.asarray(gap, bool), dtype=np.int64)
    return cs - np.maximum.accumulate(np.where(np.asarray(gap, bool), 0, cs))


def stale_rows(gap, W=1) -> np.ndarray:
    """The engine's stale rule on a window: True where the W rows ending at the row (W may be per row) hold a
    forward-filled row, or the window starts within heat.STALE rows after one, or within STALE_LONG[1] rows after a gap
    run longer than STALE_LONG[0]. W = 1 is heat.build_readings' own rule for a bar."""
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


def _lr(c) -> np.ndarray:
    with np.errstate(divide='ignore', invalid='ignore'):
        return np.r_[np.nan, np.diff(np.log(np.asarray(c, float)))]


def _logc(c) -> np.ndarray:
    with np.errstate(divide='ignore', invalid='ignore'):
        return np.log(np.asarray(c, float))


def _closes(m: dict) -> np.ndarray:
    """Close time (ms) of every row of a grid: t0 + (i + 1) min (= the entry minute's open)."""
    return int(m['t0']) + (np.arange(int(m['n']), dtype=np.int64) + 1) * MIN


def _tick(m: dict) -> np.ndarray:
    return np.asarray(m['tick'], float) if m.get('tick') is not None else heat.tick_bps(m['c'], m['gap']).astype(float)


def _last_known(known: np.ndarray, t: np.ndarray) -> np.ndarray:
    """Index of the last row with known <= t (-1: none)."""
    return np.searchsorted(np.asarray(known, np.int64), np.asarray(t, np.int64), side='right') - 1


# ---------------------------------------------------------------------------------------------------- reading dicts
def zone(name: str, x, a_hi: int, stale=None, typ: str = 'hm2', family: str = '', k: int = 1, edges=None) -> tuple:
    """A five-zone value reading: edges at ZONE_Q of the finite values of A's bars (bar close row < a_hi) unless given,
    codes from heat.bucket, NA where stale. Returns (reading, edges), or (None, None) when A holds fewer than 1,000
    values or the inner zones would be empty (the engine's rule)."""
    x = np.array(x, float, copy=True)
    if stale is not None:
        x[np.asarray(stale, bool)] = np.nan
    if edges is None:
        bar_rows = np.arange(len(x)) * k + k - 1
        xa = x[bar_rows < a_hi]
        xa = xa[np.isfinite(xa)]
        if len(xa) < MIN_A:
            return None, None
        zq = np.quantile(xa, heat.ZONE_Q)
        if not zq[1] < zq[2]:
            return None, None
        edges = [float(q) for q in zq]
    R = {'name': name, 'k': int(k), 'codes': heat.bucket(x, edges), 'levels': heat.ZONES, 'base': name, 'type': typ, 'zones': True,
         'family': family, 'edges': [float(e) for e in edges]}
    return R, R['edges']


def state(name: str, codes, levels, family: str, k: int = 1, held: bool = True, every: bool = False) -> dict:
    """A categorical state reading ('ctx': True). held: a condition that holds for a while ('state': the engine's
    level_events then samples it at every 15-minute close, as the dominance states); otherwise its events are onsets.
    every: an event that fires on its own bar (a jump), as a candlestick pattern."""
    R = {'name': name, 'k': int(k), 'codes': np.asarray(codes, np.int8), 'levels': list(levels), 'base': name, 'ctx': True, 'family': family}
    if held:
        R['state'] = True
    if every:
        R['every'], R['cond'] = True, False
    return R


class Zoner:
    """Collects the readings of one call: zone edges from A rows (a_hi) or the fixed ones given (live / parity / tests:
    a name without a fixed edge is skipped), norm tables likewise, and the names skipped."""

    def __init__(self, a_hi: int, edges: dict = None, norms: dict = None, keep_values: bool = False):
        self.a_hi, self.fixed, self.norms_in, self.keep = int(a_hi), edges, norms, keep_values
        self.R, self.edges, self.norms, self.skipped, self.values = [], {}, {}, [], {}

    def zone(self, name, x, stale=None, family='', k=1):
        if self.keep:
            v = np.array(x, float, copy=True)
            if stale is not None:
                v[np.asarray(stale, bool)] = np.nan
            self.values[name] = v
        e = None
        if self.fixed is not None:
            e = self.fixed.get(name)
            if e is None:
                self.skipped.append(name)
                return None
        R, e = zone(name, x, self.a_hi, stale, family=family, k=k, edges=e)
        if R is None:
            self.skipped.append(name)
            return None
        self.R.append(R)
        self.edges[name] = e
        return R

    def zone_codes(self, name, codes, edges, family, k=1, typ='osc'):
        """A zone reading whose codes were bucketed elsewhere (the other coins' engine readings)."""
        R = {'name': name, 'k': int(k), 'codes': np.asarray(codes, np.int8), 'levels': heat.ZONES, 'base': name, 'type': typ, 'zones': True,
             'family': family, 'edges': [float(e) for e in edges]}
        self.R.append(R)
        self.edges[name] = R['edges']
        return R

    def state(self, name, codes, levels, family, k=1, held=True, every=False):
        R = state(name, codes, levels, family, k, held, every)
        self.R.append(R)
        return R

    def norm(self, name: str, compute) -> np.ndarray:
        if self.norms_in is not None and name in self.norms_in:
            t = np.array([np.nan if v is None else float(v) for v in self.norms_in[name]])
        else:
            t = np.asarray(compute(), float)
        self.norms[name] = [None if not np.isfinite(v) else float(v) for v in t]
        return t


def _z(z, a_hi):
    return z if z is not None else Zoner(a_hi)


def family_of(R: dict) -> str:
    """A reading's family: its own 'family', else the engine's (pattern, context, or the vocabulary's value type)."""
    if R.get('family'):
        return R['family']
    nm = R['name']
    for p, f in PREFIX_FAMILY:
        if nm.startswith(p):
            return f
    if nm in CLOCK_NAMES:
        return 'clock'
    if ':CDL:' in nm:
        return 'pattern'
    if R.get('ctx'):
        return 'context'
    return R.get('type') or 'state'


# --------------------------------------------------------------------------------------------------- the new readings
def position_readings(m: dict, z: Zoner = None) -> list:
    """POS:QPos (m00-m14), POS:QPhase and POS:HourQ of the ENTRY minute (i + 1): its place in the Kalshi quarter hour
    (m14 is the last minute before :00 / :15 / :30 / :45) and in the hour. Whole-hour offsets: ET and UTC agree."""
    z = _z(z, 0)
    e = int(m['t0']) // MIN + np.arange(int(m['n']), dtype=np.int64) + 1          # the entry minute, absolute
    q = (e % 15).astype(np.int8)
    z.state('POS:QPos', q, POS_LV['POS:QPos'], 'position', held=False)
    z.state('POS:QPhase', q // 5, POS_LV['POS:QPhase'], 'position', held=False)
    z.state('POS:HourQ', ((e % 60) // 15).astype(np.int8), POS_LV['POS:HourQ'], 'position', held=False)
    return z.R[-3:]


def clock_readings(m: dict, z: Zoner = None) -> list:
    """UTC1h, NY30m (daylight saving followed) and Weekday: heat_clock.clock_readings unchanged (each keeps its own k;
    the state of the entry minute)."""
    from oracle import heat_clock
    z = _z(z, 0)
    out = []
    for R in heat_clock.clock_readings(m):
        R = dict(R, family='clock')
        z.R.append(R)
        out.append(R)
    return out


def _retz(c, gap, k: int) -> np.ndarray:
    """k-minute log return / (sd of the 1-minute log returns over the 1,440 minutes ending there x sqrt k); NA where
    the 1,441 closes read are stale."""
    lc = _logc(c)
    sd = roll_sd(_lr(c), SD_DAY)
    with np.errstate(divide='ignore', invalid='ignore'):
        x = (lc - lag(lc, k)) / (sd * math.sqrt(k))
    x[stale_rows(gap, SD_DAY + 1)] = np.nan
    return x


def _direction(c, gap, tick, k: int) -> np.ndarray:
    """+1 / -1 / 0 for a k-minute move beyond / within 1.5 price steps (heat.TICK_DEAD), -2 = NA."""
    lc = _logc(c)
    with np.errstate(invalid='ignore'):
        r = (lc - lag(lc, k)) * 1e4
        dead = heat.TICK_DEAD * np.asarray(tick, float)
        d = np.where(r > dead, 1, np.where(r < -dead, -1, 0)).astype(np.int8)
    d[~np.isfinite(r) | ~np.isfinite(dead) | stale_rows(gap, k + 1)] = -2
    return d


def other_direct(mo: dict, meta: dict = None, edges: dict = None, names=('RSI14', 'TakerBuy')) -> dict:
    """The other coin's own 1-minute RSI14 and TakerBuy codes on ITS grid, computed directly with the engine's steps
    (heat.build_readings at k = 1: the bars in whole price steps, TA-Lib, heat_vocab's WARM and flat-14 masks, the stale
    rule, heat.bucket). Edges: `edges` ({'1m:RSI14': [...]}), else meta['edges'] (O's main-run meta.json, or its
    <O>-twinN meta on a twin whose grid starts with the job coin's), else O's own A bars (heat_live.tf_codes' rule).
    The price unit: meta['price_step'] when given, else heat.tick_units on O's A rows.
    Returns {'1m:<name>': (codes, edges)} (a name without edges or enough A bars is left out)."""
    import talib
    from oracle import heat_live
    from oracle.heat_vocab import WARM
    lo, hi = split_rows(mo['t0'], mo['n'])
    step = (meta or {}).get('price_step')
    mu = heat_live._units({x: mo[x] for x in ('o', 'h', 'l', 'c')}, step) if step else heat.tick_units(mo, hi)
    h, l, c = mu['h'], mu['l'], mu['c']
    v, tb = mo['v'], mo.get('tb')
    n = len(c)
    flat14 = (pd.Series(h).rolling(14, min_periods=1).max() - pd.Series(l).rolling(14, min_periods=1).min()).to_numpy() <= 0
    warm = (np.arange(n) < WARM) | flat14
    stale = stale_rows(mo['gap'], 1)
    src = (edges or {}) if edges is not None else (meta or {}).get('edges')
    out = {}
    with np.errstate(all='ignore'):
        for nm in names:
            if nm == 'RSI14':
                x = np.asarray(talib.RSI(c, 14), float)
            elif nm == 'TakerBuy':
                if tb is None:
                    continue
                x = np.where(v > 0, tb / np.where(v > 0, v, 1), np.nan)
            else:
                raise ValueError(nm)
            x = np.where(np.isfinite(x) & ~warm, x, np.nan).astype(np.float32)
            x[stale] = np.nan
            full = f'1m:{nm}'
            if src is not None:
                zq = src.get(full)
                if zq is None:
                    continue
            else:
                xa = x[lo:hi]
                xa = xa[np.isfinite(xa)]
                if len(xa) < MIN_A:
                    continue
                zq = np.quantile(xa, heat.ZONE_Q)
                if not zq[1] < zq[2]:
                    continue
            zq = [float(q) for q in zq]
            out[full] = (heat.bucket(x, zq), zq)
    return out


def cross_readings(m: dict, others: dict, other_metas: dict = None, a_hi: int = 0, z: Zoner = None) -> list:
    """Per other coin O: X.O:R1z / R5z / R15z (O's k-minute log return / (its 1-day sd of 1-minute returns x sqrt k)),
    X.O:Gap5 / Gap15 (the last k one-minute residuals of own return - beta x O's return, summed, / (residual sd x sqrt
    k); beta the OLS slope over the 1,440 minutes ending at close i), X.O:RSI14 and X.O:TakerBuy (O's own 1-minute
    engine readings, zoned with O's edges). Then X:Breadth5 / Breadth15: the other coins up by more than 1.5 of their
    price steps over the last 5 / 15 minutes minus those down (-3 .. +3), NA while any of them is unknown (before SOL's
    first minute). O's values are computed on O's own grid and moved to this grid by the UTC minute."""
    z = _z(z, a_hi)
    start = len(z.R)
    n = int(m['n'])
    lc = _logc(m['c'])
    y = _lr(m['c'])
    gap = np.asarray(m['gap'], bool)
    dirs = {5: [], 15: []}
    for O in sorted(others):
        _no_doge(O)
        mo = others[O]
        off = (int(mo['t0']) - int(m['t0'])) // MIN
        for k in (1, 5, 15):
            z.zone(f'X.{O}:R{k}z', shift(_retz(mo['c'], mo['gap'], k), off, n, np.nan), family='cross')
        og = other_on_grid(m, mo)
        x = _lr(og['c'])
        g2 = gap | og['gap']
        ok = np.isfinite(x) & np.isfinite(y)
        xx, yy = np.where(ok, x, np.nan), np.where(ok, y, np.nan)
        sx, _ = roll_sum(xx, SD_DAY)
        sy, _ = roll_sum(yy, SD_DAY)
        sxy, _ = roll_sum(xx * yy, SD_DAY)
        sxx, _ = roll_sum(xx * xx, SD_DAY)
        syy, _ = roll_sum(yy * yy, SD_DAY)
        with np.errstate(divide='ignore', invalid='ignore'):
            Sxx, Sxy, Syy = sxx - sx * sx / SD_DAY, sxy - sx * sy / SD_DAY, syy - sy * sy / SD_DAY
            beta = Sxy / Sxx
            sres = np.sqrt(np.maximum((Syy - beta * Sxy) / (SD_DAY - 2), 0.0))
            lo_ = _logc(og['c'])
            for k in (5, 15):
                gk = ((lc - lag(lc, k)) - beta * (lo_ - lag(lo_, k))) / (sres * math.sqrt(k))
                z.zone(f'X.{O}:Gap{k}', gk, stale_rows(g2, SD_DAY + 1), family='cross')
        fixed = None if z.fixed is None else {f'1m:{nm}': z.fixed[f'X.{O}:{nm}'] for nm in ('RSI14', 'TakerBuy') if f'X.{O}:{nm}' in z.fixed}
        got = other_direct(mo, (other_metas or {}).get(O), fixed)
        for nm in ('RSI14', 'TakerBuy'):
            if f'1m:{nm}' in got:
                codes, e = got[f'1m:{nm}']
                z.zone_codes(f'X.{O}:{nm}', shift(codes, off, n, np.int8(-1)), e, 'cross')
            else:
                z.skipped.append(f'X.{O}:{nm}')
        tk = _tick(mo)
        for k in (5, 15):
            dirs[k].append(shift(_direction(mo['c'], mo['gap'], tk, k), off, n, np.int8(-2)))
    for k in (5, 15):
        if not dirs[k]:
            continue
        D = np.array(dirs[k])
        b = D.sum(0).astype(np.int64)
        codes = np.where((D == -2).any(0), -1, np.clip(b + 3, 0, 6)).astype(np.int8)
        z.state(f'X:Breadth{k}', codes, BREADTH_LV, 'cross', held=False)
    return z.R[start:]


def _hour_of_week(t: np.ndarray) -> np.ndarray:
    """Monday 00:00 UTC = 0 .. Sunday 23:00 = 167 (1970-01-01 was a Thursday)."""
    t = np.asarray(t, np.int64)
    return (((t // DAY) + 3) % 7) * 24 + (t % DAY) // HOUR


def _group_median(x: np.ndarray, grp: np.ndarray, G: int) -> np.ndarray:
    ok = np.isfinite(x)
    s = pd.Series(x[ok]).groupby(grp[ok]).median()
    out = np.full(G, np.nan)
    out[s.index.to_numpy(np.int64)] = s.to_numpy(float)
    return out


def vol_readings(m: dict, a_hi: int = 0, z: Zoner = None) -> list:
    """VOL:RV1d, RV7d (root of the summed squared 1-minute log returns over 1,440 / 10,080 minutes), RVratio (last 60
    minutes' RV / the last day's x sqrt 24), RVclock (last 60 minutes' RV / its A median for the same UTC hour of the
    week, the hour of the decision minute), VoV7d (sd of log hourly RV over the last 168 completed UTC hours), Busy
    (volume since 00:00 UTC / its A median at the same minute of the day), Semi60 ((up - down semivariance) / total,
    last 60 minutes), Jump1 / Jump5 (a last 1- or 5-minute move beyond 4 x the sd of the prior 60 one-minute returns x
    sqrt k: up / down / none)."""
    z = _z(z, a_hi)
    start = len(z.R)
    n, t0 = int(m['n']), int(m['t0'])
    gap = np.asarray(m['gap'], bool)
    lr = _lr(m['c'])
    lr2 = lr * lr
    rv60 = np.sqrt(roll_sum(lr2, 60)[0])
    rv1d = np.sqrt(roll_sum(lr2, SD_DAY)[0])
    z.zone('VOL:RV1d', rv1d, stale_rows(gap, SD_DAY + 1), family='vol')
    z.zone('VOL:RV7d', np.sqrt(roll_sum(lr2, 7 * SD_DAY)[0]), stale_rows(gap, 7 * SD_DAY + 1), family='vol')
    with np.errstate(divide='ignore', invalid='ignore'):
        z.zone('VOL:RVratio', rv60 / rv1d * math.sqrt(24), stale_rows(gap, SD_DAY + 1), family='vol')
        st60 = stale_rows(gap, 61)
        how = _hour_of_week(t0 + np.arange(n, dtype=np.int64) * MIN)
        a = min(int(a_hi), n)
        nt = z.norm('VOL:RVclock', lambda: _group_median(np.where(st60, np.nan, rv60)[:a], how[:a], 168))
        z.zone('VOL:RVclock', rv60 / nt[how], st60, family='vol')
        # hourly RV of each completed UTC hour, its log sd over the last 168 hours, then held until the next hour closes
        nh = n // 60
        e = np.arange(nh) * 60 + 59
        rvh = rv60[e]
        lrv = np.where(rvh > 0, np.log(rvh), np.nan)
        vov = roll_sd(lrv, 168)
        vov[stale_rows(gap, 168 * 60 + 1)[e]] = np.nan
        hi_ = (np.arange(n) + 1) // 60 - 1
        vv = np.where(hi_ >= 0, vov[np.clip(hi_, 0, max(nh - 1, 0))] if nh else np.nan, np.nan)
        z.zone('VOL:VoV7d', vv, family='vol')
        # volume since 00:00 UTC against its A median at the same minute of the day
        mod = ((t0 // MIN) + np.arange(n, dtype=np.int64)) % 1440
        v = np.asarray(m['v'], float)
        cv = np.cumsum(v)
        day0 = np.arange(n) - mod
        busy = cv - np.where(day0 > 0, cv[np.maximum(day0 - 1, 0)], 0.0)
        busy[day0 < 0] = np.nan                                     # a grid not starting at midnight: no whole day yet
        stb = stale_rows(gap, mod + 1)
        nb = z.norm('VOL:Busy', lambda: _group_median(np.where(stb, np.nan, busy)[:a], mod[:a], 1440))
        z.zone('VOL:Busy', np.where(nb[mod] > 0, busy / nb[mod], np.nan), stb, family='vol')
        up = roll_sum(np.where(np.isnan(lr), np.nan, np.where(lr > 0, lr2, 0.0)), 60)[0]
        dn = roll_sum(np.where(np.isnan(lr), np.nan, np.where(lr < 0, lr2, 0.0)), 60)[0]
        tot = up + dn
        z.zone('VOL:Semi60', np.where(tot > 0, (up - dn) / tot, np.nan), st60, family='vol')
        lc = _logc(m['c'])
        sd60 = roll_sd(lr, 60)
        for k in (1, 5):
            mv = lc - lag(lc, k)
            thr = 4 * lag(sd60, k) * math.sqrt(k)
            codes = np.where(mv > thr, 1, np.where(mv < -thr, 2, 0)).astype(np.int8)
            codes[~np.isfinite(mv) | ~np.isfinite(thr) | stale_rows(gap, k + 61)] = -1
            z.state(f'VOL:Jump{k}', codes, JUMP_LV, 'vol', held=False, every=True)
    return z.R[start:]


def _lagged_sum(x: np.ndarray, step: int, count: int) -> np.ndarray:
    """Sum of x[i - step], x[i - 2 step], .., x[i - count x step] at each row (NaN when any is unknown)."""
    n = len(x)
    out = np.full(n, np.nan)
    for r in range(step):
        col = x[r::step]
        s, _ = roll_sum(col, count)
        out[r::step] = lag(s, 1)[:len(col)]
    return out


def flow_readings(m: dict, a_hi: int = 0, z: Zoner = None) -> list:
    """FLOW:TB5 / TB15 / TB60 (taker-buy volume / volume over the last k minutes; NA without taker volume), Stretch5 /
    15 / 60 (k-minute log return / (1-day sd of 1-minute returns x sqrt k)) and VolZ15 (the last 15 minutes' volume as a
    z against the 96 fifteen-minute volumes of the day before it). Rolling every minute: the vocabulary's own bars
    change only on bar closes."""
    z = _z(z, a_hi)
    start = len(z.R)
    gap = np.asarray(m['gap'], bool)
    v = np.asarray(m['v'], float)
    if m.get('tb') is not None:
        tb = np.asarray(m['tb'], float)
        for k in (5, 15, 60):
            sv, _ = roll_sum(v, k)
            st, _ = roll_sum(tb, k)
            with np.errstate(divide='ignore', invalid='ignore'):
                z.zone(f'FLOW:TB{k}', np.where(sv > 0, st / sv, np.nan), stale_rows(gap, k), family='flow')
    for k in (5, 15, 60):
        z.zone(f'FLOW:Stretch{k}', _retz(m['c'], gap, k), family='flow')
    v15, _ = roll_sum(v, 15)
    s1 = _lagged_sum(v15, 15, 96)
    s2 = _lagged_sum(v15 * v15, 15, 96)
    with np.errstate(divide='ignore', invalid='ignore'):
        sd = np.sqrt(np.maximum((s2 - s1 * s1 / 96) / 95, 0.0))
        z.zone('FLOW:VolZ15', (v15 - s1 / 96) / sd, stale_rows(gap, 15 * 97), family='flow')
    return z.R[start:]


def fund_on_grid(m: dict, fund: pd.DataFrame) -> dict:
    """Per row: the last settlement known at the row's close (calc_time + 1 minute <= close, i.e. calc_time <= the open
    of minute i) as a z (rate / sd of the 90 settlements before it), the minutes to the next settlement (the last plus
    the gap between the last two), and the settlement's age. NaN when none is known or the last is over 9 hours old."""
    n = int(m['n'])
    close = _closes(m)
    T = fund['ts'].to_numpy(np.int64)
    r = fund['rate'].to_numpy(float)
    sd = pd.Series(r).rolling(90, min_periods=90).std().shift(1).to_numpy()
    with np.errstate(divide='ignore', invalid='ignore'):
        zj = r / sd
    j = _last_known(fund['known'].to_numpy(np.int64), close)
    ok = j >= 0
    jj = np.clip(j, 0, max(len(T) - 1, 0))
    age = np.where(ok, close - T[jj], np.iinfo(np.int64).max)
    ok &= age <= FUND_MAX_AGE
    zz = np.where(ok, zj[jj] if len(T) else np.nan, np.nan)
    nxt = np.where(ok & (j >= 1), T[jj] + (T[jj] - T[np.clip(j - 1, 0, None)]) if len(T) else 0, -1)
    dt = np.where(ok & (j >= 1), nxt - close, -1).astype(np.int64)
    return {'z': zz, 'to_next': dt, 'n': n}


def perp_readings(m: dict, m_real: dict, perp: dict, perp_real: dict, fund: pd.DataFrame, a_hi: int = 0, z: Zoner = None) -> list:
    """PERP:Basis ((perp close - spot close) / spot close, bps) and BasisChg15 (its 15-minute change) from the REAL spot
    and perp closes (also on a twin: a flipped perp and spot would let the level wander); Lead1 / Lead5 (perp log
    return - spot log return, bps) from m and perp (flipped on a twin); FundZ (the last settled rate / the sd of the 90
    settlements before it) and FundClock (time to the next settlement: under 15 minutes, 15-60 minutes, 1-4 hours,
    4-8 hours) from the real funding file."""
    z = _z(z, a_hi)
    start = len(z.R)
    if perp is not None:
        sc, pc = np.asarray(m_real['c'], float), np.asarray(perp_real['c'], float)
        g_real = np.asarray(m_real['gap'], bool) | np.asarray(perp_real['gap'], bool)
        with np.errstate(divide='ignore', invalid='ignore'):
            bas = (pc - sc) / sc * 1e4
        z.zone('PERP:Basis', bas, stale_rows(g_real, 1), family='perp')
        z.zone('PERP:BasisChg15', bas - lag(bas, 15), stale_rows(g_real, 16), family='perp')
        g2 = np.asarray(m['gap'], bool) | np.asarray(perp['gap'], bool)
        ls, lp = _logc(m['c']), _logc(perp['c'])
        for k in (1, 5):
            z.zone(f'PERP:Lead{k}', ((lp - lag(lp, k)) - (ls - lag(ls, k))) * 1e4, stale_rows(g2, k + 1), family='perp')
    if fund is not None:
        f = fund_on_grid(m, fund)
        z.zone('PERP:FundZ', f['z'], family='perp')
        d = f['to_next']
        codes = np.select([d < 0, d < 15 * MIN, d < 60 * MIN, d < 240 * MIN, d <= 480 * MIN], [-1, 0, 1, 2, 3], -1).astype(np.int8)
        z.state('PERP:FundClock', codes, FUNDCLOCK_LV, 'perp', held=False)
    return z.R[start:]


def oi_on_grid(m: dict, oi: pd.DataFrame) -> np.ndarray:
    """log open interest per row: the last reading known at the row's close (create_time + 5 minutes), carried at most
    10 minutes after it became known; NaN before the file's first row."""
    close = _closes(m)
    j = _last_known(oi['known'].to_numpy(np.int64), close)
    ok = j >= 0
    jj = np.clip(j, 0, max(len(oi) - 1, 0))
    kn = oi['known'].to_numpy(np.int64)
    ok &= np.where(ok, close - (kn[jj] if len(oi) else 0), OI_CARRY + 1) <= OI_CARRY
    with np.errstate(divide='ignore'):
        lo = np.log(oi['oi'].to_numpy(float)) if len(oi) else np.zeros(0)
    return np.where(ok, lo[jj] if len(oi) else np.nan, np.nan)


def oi_readings(m: dict, oi: pd.DataFrame, a_hi: int = 0, z: Zoner = None, m_real: dict = None) -> list:
    """OI:Chg15 / Chg60: the log change of open interest over the last 15 / 60 minutes of known readings / the sd of
    that change over the day before (at least 90% of it known). OI:PxQuad60: price up / down over the last 60 minutes
    (beyond 1.5 price steps, from m: flipped on a twin) x open interest up / down (real): new longs, short covering,
    new shorts, long liquidation; NA otherwise."""
    z = _z(z, a_hi)
    start = len(z.R)
    L = oi_on_grid(m, oi)
    for k in (15, 60):
        ch = L - lag(L, k)
        sd = lag(roll_sd(ch, SD_DAY, int(OI_MIN_SHARE * SD_DAY)), 1)
        with np.errstate(divide='ignore', invalid='ignore'):
            z.zone(f'OI:Chg{k}', ch / sd, family='oi')
    lc = _logc(m['c'])
    with np.errstate(invalid='ignore'):
        px = (lc - lag(lc, 60)) * 1e4
        dead = heat.TICK_DEAD * _tick(m)
        o60 = L - lag(L, 60)
        pu, pdn = px > dead, px < -dead
        codes = np.select([pu & (o60 > 0), pu & (o60 < 0), pdn & (o60 > 0), pdn & (o60 < 0)], [0, 1, 2, 3], -1).astype(np.int8)
    codes[stale_rows(m['gap'], 61) | ~np.isfinite(px)] = -1
    z.state('OI:PxQuad60', codes, PXQUAD_LV, 'oi', held=False)
    return z.R[start:]


def _daily_frame(dom, name: str):
    """A daily series: from a dict of frames (live) or research/btcd_fractal/data/<NAME>_1d.csv (load_extra 'daily')."""
    if isinstance(dom, dict):
        d = dom.get(name)
        if d is None:
            return None
        if 'known' not in d.columns:
            d = d.copy()
            d['known'] = known_ms('daily', d['ts'].to_numpy(np.int64))
            d = d[d['known'] < heat.HEAT_END]
        return d
    if not dom:
        return None
    f = os.path.join(dom, f'{name}_1d.csv')
    return load_extra(f, 'daily') if os.path.exists(f) else None


def daily_readings(m: dict, dom, names=DMKT_NAMES, z: Zoner = None, missing: list = None) -> list:
    """DMKT:<NAME>1d: the change of the last bar KNOWN at the row (stamp + 24 hours: a bar stamped at its session's
    open, 21:00-23:00 UTC for FX and rates, is never read before it closes) / the series' own sd of the 60 bar changes
    before it, in HM1's five dominance levels (heat.DOM_Z). A held row-level state (k = 1); NA when the last known bar
    is over 5 days old."""
    z = _z(z, 0)
    start = len(z.R)
    close = _closes(m)
    for nm in names:
        _no_doge(nm)
        d = _daily_frame(dom, nm)
        if d is None or not len(d):
            if missing is not None:
                missing.append(f'daily:{nm}')
            continue
        c = d['c'].to_numpy(float)
        r1 = pd.Series(c / np.r_[np.nan, c[:-1]] - 1)
        sd = r1.rolling(60, min_periods=40).std().shift(1).to_numpy()
        with np.errstate(divide='ignore', invalid='ignore'):
            zz = r1.to_numpy() / sd
        kn = d['known'].to_numpy(np.int64)
        j = _last_known(kn, close)
        ok = j >= 0
        jj = np.clip(j, 0, len(d) - 1)
        ok &= (close - kn[jj]) <= DMKT_MAX_AGE
        z.state(f'DMKT:{nm}1d', heat.bucket(np.where(ok, zz[jj], np.nan), heat.DOM_Z), heat.DOM_LV, 'dmkt', held=True)
    return z.R[start:]


def _hourly(m: dict, df: pd.DataFrame) -> tuple:
    """An hourly series on its own complete hourly index (forward-filled, gap mask), and the index of each of the
    grid's hour bars in it (-1: outside)."""
    ts = df['ts'].to_numpy(np.int64)
    ts, c = ts[ts % HOUR == 0], df['c'].to_numpy(float)[ts % HOUR == 0]
    if not len(ts):
        return np.zeros(0), np.zeros(0, bool), np.full(int(m['n']) // 60, -1, np.int64)
    h0 = int(ts[0])
    nh = int((ts[-1] - h0) // HOUR) + 1
    pos = (ts - h0) // HOUR
    gap = np.ones(nh, bool)
    gap[pos] = False
    ch = np.full(nh, np.nan)
    ch[pos] = c
    ch = pd.Series(ch).ffill().to_numpy()
    bars = (int(m['t0']) + np.arange(int(m['n']) // 60, dtype=np.int64) * HOUR - h0) // HOUR
    bars[(bars < 0) | (bars >= nh)] = -1
    return ch, gap, bars


def inventory_readings(m: dict, found: dict, a_hi: int = 0, z: Zoner = None, not_found: list = None) -> list:
    """The families the inventory finds (each only when its file is given):
      IDX:BTCDOM1h / BTCDOM4h (k = 60): the log change of BTCDOM over the last 1 / 4 closed hours / its 30-day sd of
        that change (computed on BTCDOM's own hourly series; a bar is known at its close, stamp + 1 hour);
      CB:Lead1 / Lead5: Coinbase log return - Binance log return of the same coin over 1 / 5 minutes, bps; CB:PremChg15:
        the 15-minute change of log(Coinbase close / Binance close), bps (changes only: the level mixes the USD/USDT
        rate in). found['cb'] is on this grid (flipped with m on a twin);
      BOOK:Imb: (bid depth - ask depth) / their sum within 1% of the mid, from the last snapshot stamped at or before
        close i; NA when it is over 5 minutes old (real on a twin: a book is not a direction)."""
    z = _z(z, a_hi)
    start = len(z.R)
    found = found or {}
    nf = not_found if not_found is not None else []
    bd = found.get('btcdom')
    if bd is not None and len(bd):
        ch, gh, bars = _hourly(m, bd)
        lc = _logc(ch)
        for k, nm in ((1, 'IDX:BTCDOM1h'), (4, 'IDX:BTCDOM4h')):
            chg = lc - lag(lc, k)
            with np.errstate(divide='ignore', invalid='ignore'):
                zz = chg / roll_sd(chg, 720)
            zz[stale_rows(gh, 720 + k)] = np.nan
            z.zone(nm, np.where(bars >= 0, zz[np.maximum(bars, 0)], np.nan), family='idx', k=60)
    else:
        nf += ['IDX:BTCDOM1h', 'IDX:BTCDOM4h']
    cb = found.get('cb')
    if cb is not None:
        g2 = np.asarray(m['gap'], bool) | np.asarray(cb['gap'], bool)
        lb, lcb = _logc(m['c']), _logc(cb['c'])
        for k, nm in ((1, 'CB:Lead1'), (5, 'CB:Lead5'), (15, 'CB:PremChg15')):
            z.zone(nm, ((lcb - lag(lcb, k)) - (lb - lag(lb, k))) * 1e4, stale_rows(g2, k + 1), family='cb')
    else:
        nf += ['CB:Lead1', 'CB:Lead5', 'CB:PremChg15']
    bk = found.get('book')
    if bk is not None and len(bk):
        close = _closes(m)
        T = bk['ts'].to_numpy(np.int64)
        j = _last_known(bk['known'].to_numpy(np.int64), close)
        ok = j >= 0
        jj = np.clip(j, 0, len(bk) - 1)
        ok &= (close - T[jj]) <= BOOK_MAX_AGE
        b, a = bk['bid'].to_numpy(float), bk['ask'].to_numpy(float)
        z.zone('BOOK:Imb', np.where(ok, ((b - a) / (b + a))[jj], np.nan), family='book')
    else:
        nf += ['BOOK:Imb']
    return z.R[start:]


def macro_readings(m: dict, cal: pd.DataFrame, z: Zoner = None) -> list:
    """MACRO:R830: none / 30 to 1 minutes before / 0-14, 15-59, 60-239 minutes after an 8:30 AM ET CPI, jobs or PPI
    release; MACRO:FOMC: the same windows around an FOMC statement (unscheduled ones get only the "after" levels, from
    the close of their own minute); MACRO:ReleaseDay: none / release day (the ET day holds a release or a statement; an
    unscheduled statement's day only from the close of its minute). All windows are of the entry minute (it opens at
    the close of row i); event times are UTC instants (ET with daylight saving, checked at load)."""
    z = _z(z, 0)
    start = len(z.R)
    t0, n = int(m['t0']), int(m['n'])

    def fill(arr, a, b, code):
        """rows whose entry minute opens in [a, b)"""
        i0 = max(0, -(-(int(a) - t0) // MIN) - 1)
        i1 = min(n, -(-(int(b) - t0) // MIN) - 1)
        if i1 > i0:
            arr[i0:i1] = code

    rday = np.zeros(n, np.int8)
    for nm, kinds in (('MACRO:R830', R830_KINDS), ('MACRO:FOMC', ('FOMC',))):
        arr = np.zeros(n, np.int8)
        ev = cal[cal['kind'].isin(kinds)].sort_values('ts') if cal is not None else cal
        rows = list(ev[['ts', 'known', 'scheduled', 'day_lo', 'day_hi']].itertuples(index=False)) if ev is not None else []
        for ts, kn, sch, lo, hi in rows:
            if sch:
                fill(arr, ts - 30 * MIN, ts, 1)
        for ts, kn, sch, lo, hi in rows:
            for code, a, b in ((2, 0, 15), (3, 15, 60), (4, 60, 240)):
                fill(arr, max(ts + a * MIN, kn), ts + b * MIN, code)
            fill(rday, max(lo, kn), hi, 1)
        z.state(nm, arr, MACRO_LV, 'macro', held=False)
    z.state('MACRO:ReleaseDay', rday, ['none', 'release day'], 'macro', held=True)
    return z.R[start:]


def extra_readings(m: dict, g, others: dict = None, other_metas: dict = None, perp=None, fund: pd.DataFrame = None, oi: pd.DataFrame = None,
                   cal: pd.DataFrame = None, dom_dir=None, found: dict = None, real: dict = None, log=print, asset: str = None,
                   edges: dict = None, norms: dict = None, daily_names=DMKT_NAMES, info: dict = None) -> tuple:
    """Every new reading of OR-HM2 for one series (the job coin, or its twin).

    m: the job coin's minutes (heat.load_minutes; heat.make_twin(m, seed) on a twin). g: its heat.Grid, or split A's
    end row (zone edges and norm tables come from rows before g.sp['A'].hi only). others: {O: minutes on O's own grid}
    (passed through joint_flip on a twin). other_metas: {O: main-run meta of O (edges, price_step), or None for edges
    from O's own A bars}. perp: the perp's minutes on this grid (on_grid; flipped on a twin; a DataFrame from load_extra
    is put on the grid here). fund / oi / cal: load_extra frames. dom_dir: research/btcd_fractal/data (or {NAME: frame}).
    found: {'btcdom': frame, 'cb': Coinbase minutes on this grid (flipped on a twin), 'book': frame}, each optional.
    real: {'m': real minutes, 'perp': real perp on this grid} on a twin (the basis is a real level).
    edges / norms: fixed tables (live, parity): a reading without a stored edge is skipped.
    info (out): 'not_found' (inventory families absent), 'skipped' (no edges or too few A values), 'values' when
    info['keep_values'] is set.

    Returns (readings, edges, norms, missing): missing lists the planned inputs that are absent (the caller stops)."""
    if asset:
        _no_doge(asset)
    a_hi = g.sp['A'].hi if hasattr(g, 'sp') else int(g or 0)
    info = info if info is not None else {}
    z = Zoner(a_hi, edges, norms, keep_values=bool(info.get('keep_values')))
    missing, not_found = [], []
    others = dict(others or {})
    for O in others:
        _no_doge(O)
    if asset:
        missing += [f'coin:{O}' for O in COINS if O != asset and O not in others]
    if isinstance(perp, pd.DataFrame):
        perp = on_grid(m, perp)
    real = real or {}
    m_real = real.get('m') or m
    perp_real = real.get('perp') if real.get('perp') is not None else perp
    if isinstance(perp_real, pd.DataFrame):
        perp_real = on_grid(m_real, perp_real)
    position_readings(m, z)
    clock_readings(m, z)
    if others:
        cross_readings(m, others, other_metas, a_hi, z)
    vol_readings(m, a_hi, z)
    flow_readings(m, a_hi, z)
    if perp is None:
        missing.append('perp')
    if fund is None:
        missing.append('funding')
    perp_readings(m, m_real, perp, perp_real, fund, a_hi, z)
    if oi is None:
        missing.append('oi')
    else:
        oi_readings(m, oi, a_hi, z)
    daily_readings(m, dom_dir, daily_names, z, missing)
    inventory_readings(m, found, a_hi, z, not_found)
    if cal is None:
        missing.append('calendar')
    else:
        macro_readings(m, cal, z)
    info.update(not_found=not_found, skipped=list(z.skipped))
    if z.keep:
        info['values'] = z.values
    log(f'  hm2 extra readings: {len(z.R)} ({", ".join(f"{f} {c}" for f, c in pd.Series([R["family"] for R in z.R]).value_counts().sort_index().items())}); '
        f'skipped {len(z.skipped)}; not found {not_found}; missing {missing}')
    return z.R, z.edges, z.norms, missing


def load_inputs(asset: str, m_real: dict, twin: int = 0, other_csvs: dict = None, perp_csv: str = None, fund_csv: str = None,
                oi_csv: str = None, cal_csv: str = None, found_paths: dict = None, end: int = None, log=print) -> dict:
    """The extra inputs of one series, ready for extra_readings(m, g, **out['kwargs']): the other coins' minutes
    (heat.load_minutes, strict), the perp and Coinbase minutes on the job grid, the funding, open-interest, calendar,
    BTCDOM and book frames (load_extra, strict). On a twin (twin = seed) every price path (the other coins, the perp,
    Coinbase) goes through the joint flip of the job coin's grid; the real perp is kept for the basis. The job coin's
    own twin is heat.make_twin(m_real, seed) (the joint flip gives the same, bit for bit)."""
    _no_doge(asset, *(other_csvs or {}).keys(), *(other_csvs or {}).values(), perp_csv, fund_csv, oi_csv, *(found_paths or {}).values())
    flip = joint_flip(twin, m_real['t0'], m_real['n']) if twin else None
    end = heat.HEAT_END if end is None else end
    others = {}
    for O, p in (other_csvs or {}).items():
        mo = heat.load_minutes(p, end=end)
        others[O] = flip(mo) if flip else mo
    perp_real = on_grid(m_real, load_extra(perp_csv, 'perp1m')) if perp_csv else None
    found_paths = found_paths or {}
    fd = {}
    if found_paths.get('btcdom'):
        fd['btcdom'] = load_extra(found_paths['btcdom'], 'idx1h')
    if found_paths.get('cb'):
        cb = on_grid(m_real, load_extra(found_paths['cb'], 'cb1m'))
        fd['cb'] = flip(cb) if flip else cb
    if found_paths.get('book'):
        fd['book'] = load_extra(found_paths['book'], 'book')
    kw = {'others': others, 'perp': flip(perp_real) if (flip and perp_real is not None) else perp_real,
          'fund': load_extra(fund_csv, 'funding') if fund_csv else None, 'oi': load_extra(oi_csv, 'oi') if oi_csv else None,
          'cal': load_extra(cal_csv, 'calendar') if cal_csv else None, 'found': fd, 'real': {'m': m_real, 'perp': perp_real}, 'asset': asset}
    log(f'{asset}{"~twin" + str(twin) if twin else ""}: extra inputs ' + ', '.join(f'{k} {"yes" if kw[k] is not None else "no"}' for k in ('perp', 'fund', 'oi', 'cal'))
        + f'; others {sorted(others)}; found {sorted(fd)}')
    return {'kwargs': kw, 'flip': flip}


# ------------------------------------------------------------------------------------------- funding stamp convention
def funding_stamp_check(fund: pd.DataFrame, basis: np.ndarray, a_hi: int, t0: int, stop: bool = True) -> dict:
    """The rate stamped T must follow the mean basis over [T - 8 h, T) more closely than over [T, T + 8 h) (on A rows):
    the stamp is the settlement, not the start of the period it pays for. basis: the REAL basis per row of a grid
    starting at t0 (bps). stop: SystemExit when the check fails or cannot be made."""
    basis = np.asarray(basis, float)
    n = min(len(basis), int(a_hi))
    f = np.isfinite(basis[:n])
    cs = np.r_[0.0, np.cumsum(np.where(f, basis[:n], 0.0))]
    cn = np.r_[0, np.cumsum(f)]
    T = fund['ts'].to_numpy(np.int64)
    r = fund['rate'].to_numpy(float)
    W = 8 * 60

    def mean(lo):
        lo = np.asarray(lo, np.int64)
        ok = (lo >= 0) & (lo + W <= n)
        lo_c = np.clip(lo, 0, max(n - W, 0))
        k = cn[lo_c + W] - cn[lo_c]
        with np.errstate(invalid='ignore', divide='ignore'):
            return np.where(ok & (k >= W // 2), (cs[lo_c + W] - cs[lo_c]) / k, np.nan)
    first = -(-(T - int(t0)) // MIN)                                      # the first row whose minute opens at or after T
    before, after = mean(first - W), mean(first)
    ok = np.isfinite(before) & np.isfinite(after) & np.isfinite(r)
    out = {'n': int(ok.sum())}
    if ok.sum() >= 30:
        cb = float(np.corrcoef(r[ok], before[ok])[0, 1])
        ca = float(np.corrcoef(r[ok], after[ok])[0, 1])
        out.update(corr_before=cb, corr_after=ca, ok=bool(cb > ca))
    else:
        out.update(corr_before=None, corr_after=None, ok=False)
    if stop and not out['ok']:
        raise SystemExit(f'funding stamp check failed: {out} (the rate stamped T must follow the basis over the 8 hours BEFORE T)')
    return out


# ------------------------------------------------------------------------------------------- learner states, copies
def zs_codes(codes: np.ndarray) -> np.ndarray:
    """The side-aware zone event on each bar (ZS_LEVELS; heat.event_levels' order and heat.level_events' rule: a level
    entered from a known, different level), 'none' on a known bar without one, -1 where the zone is unknown."""
    codes = np.asarray(codes, np.int8)
    prev = np.r_[np.int8(-1), codes[:-1]]
    out = np.where(codes >= 0, 0, -1).astype(np.int8)
    st = (codes >= 0) & (prev >= 0) & (codes != prev)
    out[st & (codes == 0)] = 1
    out[st & (codes == 1) & (prev > 1)] = 2
    out[st & (codes == 1) & (prev < 1)] = 3
    out[st & (codes == 3) & (prev < 3)] = 4
    out[st & (codes == 3) & (prev > 3)] = 5
    out[st & (codes == 4)] = 6
    return out


def zs_readings(readings: list) -> list:
    """Learner only (OR-HM2, Readings 4): ZS:<name> per zone reading, the event that fired on its last closed bar."""
    return [{'name': f'ZS:{R["name"]}', 'k': R['k'], 'codes': zs_codes(R['codes']), 'levels': ZS_LEVELS, 'base': R['base'], 'family': 'zs',
             'learner_only': True, 'every': True, 'cond': False} for R in readings if R.get('zones')]


def merge_aliases(readings: list, rows, agree: float = MERGE_AGREE, min_n: int = heat.MIN_EVENTS, screen: int = 4000, seed: int = 20261111) -> tuple:
    """Copies merged (OR-HM2, Readings 3): two readings with the same levels whose codes (heat.read_state at the A
    entries `rows`) agree on at least `agree` of the entries where both are known and at least one is not neutral become
    one reading, the first by name keeping the row and listing the other in 'aliases' (and its base in 'alias_bases',
    so the scan never pairs a reading with its own copy's series). Entries where both are neutral do not count: two
    rare patterns are 'none' together on almost every minute without being copies. A seeded sample of the entries
    screens the candidates; every merge is decided on all entries. Greedy against the kept readings, in name order.
    Returns (kept readings, {kept name: [alias names]}). The series job (heat_hm2.make_ctx, which Parts 3 and 4 reuse)
    merges with heat_hm2.merge_aliases, the same rule on its entry code matrix; this one serves callers that hold only
    reading dicts."""
    rows = np.asarray(rows, np.int64)
    rng = np.random.default_rng(seed)
    samp = np.sort(rng.choice(rows, screen, replace=False)) if len(rows) > screen else rows
    order = sorted(range(len(readings)), key=lambda i: readings[i]['name'])
    groups = {}
    for i in order:
        groups.setdefault(tuple(readings[i]['levels']), []).append(i)
    alias_of = {}
    for lv, idx in groups.items():
        neutral = np.array([x in heat.NEUTRAL for x in lv] + [True])        # the last slot: unknown (-1)
        reps, M = [], np.zeros((0, len(samp)), np.int8)
        for i in idx:
            cs = heat.read_state(readings[i], samp)
            hit = None
            if len(reps):
                known = (M >= 0) & (cs >= 0)[None, :]
                inf = known & (~neutral[M] | ~neutral[cs][None, :])
                k = inf.sum(1)
                a = ((M == cs[None, :]) & inf).sum(1)
                with np.errstate(invalid='ignore', divide='ignore'):
                    cand = np.nonzero((k == 0) | (a >= (agree - 0.03) * k))[0]
                for c in cand:
                    j = reps[c]
                    x, y = heat.read_state(readings[i], rows), heat.read_state(readings[j], rows)
                    inf_all = (x >= 0) & (y >= 0) & (~neutral[x] | ~neutral[y])
                    nk = int(inf_all.sum())
                    if nk >= min_n and int((x[inf_all] == y[inf_all]).sum()) >= agree * nk:
                        hit = j
                        break
            if hit is None:
                reps.append(i)
                M = np.vstack([M, cs[None, :]])
            else:
                alias_of[i] = hit
    aliases = {}
    for i, j in alias_of.items():
        aliases.setdefault(readings[j]['name'], []).append(readings[i]['name'])
    kept = []
    for i, R in enumerate(readings):
        if i in alias_of:
            continue
        if R['name'] in aliases:
            R = dict(R, aliases=sorted(aliases[R['name']]),
                     alias_bases=sorted({readings[a]['base'] for a, b in alias_of.items() if b == i} - {R['base']}))
        kept.append(R)
    return kept, {k: sorted(v) for k, v in aliases.items()}


# ---------------------------------------------------------------------------------------------------------------- live
LIVE_MIN_MINUTES = 7 * SD_DAY + 2 * SD_DAY + 600                   # RV7d and VoV7d with their stale margin, and a spare day


def levels_at(win: dict, hm2_meta: dict, names=None, others: dict = None, perp=None, fund: pd.DataFrame = None, oi: pd.DataFrame = None,
              daily=None, found: dict = None, cal: pd.DataFrame = None) -> dict:
    """Live: the level of every new reading at the LAST closed minute of a window of minutes (heat_live.grid of the
    job coin; at least LIVE_MIN_MINUTES long), computed by the same code with the stored edges and norm tables
    (hm2_meta: {'edges', 'norms', 'other_metas': {O: {'edges', 'price_step'}}}). others: {O: grid of O over the same
    window}; daily: {NAME: frame of daily closes} or the directory. Returns {name: level, or None (no reading)}."""
    R, _, _, _ = extra_readings(win, 0, others=others, other_metas=hm2_meta.get('other_metas'), perp=perp, fund=fund, oi=oi, cal=cal,
                                dom_dir=daily, found=found, edges=hm2_meta.get('edges', {}), norms=hm2_meta.get('norms', {}), log=lambda *a: None)
    last = np.array([int(win['n']) - 1])
    out = {}
    for r in R:
        if names is not None and r['name'] not in names:
            continue
        c = int(heat.read_state(r, last)[0])
        out[r['name']] = r['levels'][c] if c >= 0 else None
    for nm in names or ():
        out.setdefault(nm, None)
    return out


# ----------------------------------------------------------------------------------------------------------------- CLI
def _listing(path: str) -> dict:
    """--listing: a directory of <COIN>.json files (rclone lsjson -R of raw/perp-ta-history/<COIN>/), or one JSON file
    {coin: [...]}."""
    if os.path.isdir(path):
        out = {}
        for f in sorted(os.listdir(path)):
            if f.endswith('.json'):
                with open(os.path.join(path, f)) as fh:
                    out[f[:-5]] = json.load(fh)
        return out
    with open(path) as fh:
        return json.load(fh)


def main(argv=None):
    ap = argparse.ArgumentParser(description='OR-HM2 extra-data preflight')
    sub = ap.add_subparsers(dest='cmd', required=True)
    a = sub.add_parser('inventory')
    a.add_argument('--listing', required=True)
    a.add_argument('--dom', required=True)
    a.add_argument('--out', default='')
    s = sub.add_parser('stamps')
    s.add_argument('files', nargs='+')
    s.add_argument('--cut', action='store_true', help='also require the last stamp before HEAT_END (after the awk cut)')
    s.add_argument('--daily', action='store_true', help='a daily series: 13 digits only (it starts before 2019 and runs past HEAT_END)')
    f = sub.add_parser('funding-check')
    f.add_argument('--spot', required=True)
    f.add_argument('--perp', required=True)
    f.add_argument('--funding', required=True)
    f.add_argument('--out', default='')
    x = ap.parse_args(argv)
    if x.cmd == 'inventory':
        inv = inventory(_listing(x.listing), x.dom)
        txt = json.dumps(inv, indent=1)
        if x.out:
            with open(x.out, 'w') as fh:
                fh.write(txt)
        for r in inv['sources']:
            print(f"{r['coin']:4s} {r['folder']:18s} {r['files']:4d} files  {r.get('family') or '-':10s} {r.get('reason') or 'UNMAPPED'}")
        for r in inv['daily']:
            print(f"daily {r['file']:24s} {r.get('family') or '-':10s} {r.get('reason') or 'UNMAPPED'}")
        print('found:', json.dumps(inv['found']))
        if not inv['ok']:
            print('missing:', inv['missing'], '\nunmapped (needs a family or a written "Not used" line in OR-HM2.md):', inv['unmapped'])
            raise SystemExit('inventory: a planned file is missing or a source is unmapped')
        print('inventory ok')
    elif x.cmd == 'stamps':
        bad = []
        for p in x.files:
            _no_doge(p)
            sp = ts_span(p)
            ok = sp['ms13'] and (x.daily or (sp['first'] >= MS_LO and (not x.cut or sp['last'] < heat.HEAT_END)))
            print(f"{p}: first {sp['first']} ({sp.get('first_utc')}), last {sp['last']} ({sp.get('last_utc')}): {'ok' if ok else 'NOT 13-digit ms in range'}")
            if not ok:
                bad.append(p)
        if bad:
            raise SystemExit(f'time stamps: {bad}')
    else:
        _no_doge(x.spot, x.perp, x.funding)
        m = heat.load_minutes(x.spot)
        perp = on_grid(m, load_extra(x.perp, 'perp1m'))
        with np.errstate(invalid='ignore', divide='ignore'):
            bas = (perp['c'] - m['c']) / m['c'] * 1e4
        bas[stale_rows(m['gap'] | perp['gap'], 1)] = np.nan
        out = funding_stamp_check(load_extra(x.funding, 'funding'), bas, split_rows(m['t0'], m['n'])[1], m['t0'], stop=False)
        print('funding stamp check:', json.dumps(out))
        if x.out:
            with open(x.out, 'w') as fh:
                json.dump(out, fh, indent=1)
        if not out['ok']:
            raise SystemExit('funding stamp check failed: the rate stamped T must follow the basis over the 8 hours before T')


if __name__ == '__main__':
    main(sys.argv[1:])
