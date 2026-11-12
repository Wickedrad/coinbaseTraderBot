"""OR-XD fetch round: build our own Binance history (runs on GitHub runners; this container's proxy refuses the archive).

    python -m oracle.outside_fetch preflight --out FILE
    python -m oracle.outside_fetch small --asset BTC --out DIR
    python -m oracle.outside_fetch agg --asset BTC --market spot --year 2024 --out DIR [--months 01,02] [--put-cmd CMD]
                                       [--skip-existing FILE_LIST]

Data contract (Drive raw/outside/binance/<COIN>/ and raw/outside/binance/BTCDOM/): metrics.csv.gz, premium_1m / mark_1m /
index_1m.csv.gz, premium_stamp.json, um_1m.csv.gz, funding.csv.gz, bookdepth_1pct.csv.gz, agg_spot|agg_perp/<YYYY-MM>.parquet,
BTCDOM/idx1h.csv.gz, manifest.json. All times UTC milliseconds. Reductions live in oracle/outside_reduce.py.

Rules: the repo is PUBLIC, so nothing here prints or commits market rows (counts, first/last stamps and byte totals only);
zips are streamed to a temp file and deleted; NEVER DOGE (any asset outside BTC, ETH, SOL, XRP, BTCDOM is refused).
Times in docs: EST = UTC - 5 h.
"""
from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
import zipfile
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from oracle import outside_reduce as red

S3 = 'https://s3-ap-northeast-1.amazonaws.com/data.binance.vision'
FILES = 'https://data.binance.vision/'
COINS = ('BTC', 'ETH', 'SOL', 'XRP')
ASSETS = COINS + ('BTCDOM',)
BOOKDEPTH_FROM = '2023-01-01'
AMB_MAX_FRAC = 0.01
UM = 'data/futures/um'
SPOT = 'data/spot'


# --- guards ------------------------------------------------------------------------------------------------------------
def symbol_of(asset: str) -> str:
    a = asset.upper()
    if 'DOGE' in a or a not in ASSETS:
        raise SystemExit(f'refused asset {asset!r}: only {", ".join(ASSETS)} (never DOGE)')
    return f'{a}USDT'


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def log(*a) -> None:
    print(*a, flush=True)


# --- network (monkeypatched in the tests) ------------------------------------------------------------------------------
_session = None


def _sess():
    global _session
    if _session is None:
        import requests
        _session = requests.Session()
        _session.headers['User-Agent'] = 'oracle-outside-fetch/1'
    return _session


def _retry(fn, what: str, tries: int = 6):
    for i in range(tries):
        try:
            return fn()
        except NotFound:
            raise
        except Exception as e:                                           # noqa: BLE001 - network is noisy
            if i == tries - 1:
                raise RuntimeError(f'{what}: giving up after {tries} tries: {type(e).__name__}') from e
            time.sleep(min(60, 2 ** i))


class NotFound(Exception):
    pass


def list_prefix(prefix: str) -> list[dict]:
    """S3 listing of every key under prefix (marker paging). Rows: key, size, etag, last_modified. No data files."""
    out: list[dict] = []
    marker = ''
    while True:
        def page():
            r = _sess().get(S3, params={'prefix': prefix, 'marker': marker, 'max-keys': 1000}, timeout=60)
            r.raise_for_status()
            return r.text
        text = _retry(page, f'list {prefix}')
        root = ET.fromstring(text)
        ns = re.match(r'\{.*\}', root.tag)
        p = ns.group(0) if ns else ''
        last = None
        for c in root.findall(f'{p}Contents'):
            key = c.findtext(f'{p}Key')
            last = key
            if not key or not key.endswith('.zip'):
                continue
            out.append({'key': key, 'size': int(c.findtext(f'{p}Size') or 0), 'etag': (c.findtext(f'{p}ETag') or '').strip('"'),
                        'last_modified': c.findtext(f'{p}LastModified') or ''})
        if (root.findtext(f'{p}IsTruncated') or '').lower() != 'true' or last is None:
            return out
        marker = last


def fetch_zip(key: str, size: int, dest: str) -> str:
    """Download one archive file to dest (resumes with Range), verify the size, return its sha256."""
    url = FILES + key

    def go():
        have = os.path.getsize(dest) if os.path.exists(dest) else 0
        if size and have > size:
            os.remove(dest)
            have = 0
        if size and have == size:
            return
        hdr = {'Range': f'bytes={have}-'} if have else {}
        with _sess().get(url, stream=True, headers=hdr, timeout=(20, 120)) as r:
            if r.status_code == 404:
                raise NotFound(key)
            r.raise_for_status()
            mode = 'ab' if (have and r.status_code == 206) else 'wb'
            with open(dest, mode) as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
        if size and os.path.getsize(dest) != size:
            raise IOError('size mismatch')
    try:
        _retry(go, f'download {key}')
    except RuntimeError:
        if os.path.exists(dest):
            os.remove(dest)
        raise
    if size and os.path.getsize(dest) != size:
        raise RuntimeError(f'{key}: size {os.path.getsize(dest)} != listed {size}')
    h = hashlib.sha256()
    with open(dest, 'rb') as f:
        for b in iter(lambda: f.read(1 << 22), b''):
            h.update(b)
    return h.hexdigest()


# --- key helpers -------------------------------------------------------------------------------------------------------
def date_of(key: str) -> str:
    m = re.search(r'(\d{4}-\d{2}(?:-\d{2})?)\.zip$', key)
    return m.group(1) if m else ''


def plan_months(monthly: list[dict], daily: list[dict]) -> list[dict]:
    """Monthly files, plus the daily files of every month that has no monthly file (the current month)."""
    have = {date_of(e['key']) for e in monthly}
    extra = [e for e in daily if date_of(e['key'])[:7] not in have]
    return sorted(monthly + extra, key=lambda e: e['key'])


def kline_prefix(base: str, kind: str, sym: str, interval: str | None, freq: str) -> str:
    tail = f'{interval}/' if interval else ''
    return f'{base}/{freq}/{kind}/{sym}/{tail}'


def listing(base: str, kind: str, sym: str, interval: str | None, both: bool = True) -> list[dict]:
    monthly = list_prefix(kind_prefix(base, kind, sym, interval, 'monthly'))
    if not both:
        return sorted(monthly, key=lambda e: e['key'])
    return plan_months(monthly, list_prefix(kind_prefix(base, kind, sym, interval, 'daily')))


def kind_prefix(base: str, kind: str, sym: str, interval: str | None, freq: str) -> str:
    return kline_prefix(base, kind, sym, interval, freq)


# --- preflight ---------------------------------------------------------------------------------------------------------
def _summ(entries: list[dict]) -> dict:
    if not entries:
        return {'files': 0, 'bytes': 0, 'first': None, 'last': None}
    ds = sorted(date_of(e['key']) for e in entries)
    return {'files': len(entries), 'bytes': int(sum(e['size'] for e in entries)), 'first': ds[0], 'last': ds[-1],
            'largest_bytes': int(max(e['size'] for e in entries))}


def preflight(out: str) -> dict:
    res: dict = {'generated_at': now_utc(), 'source': S3, 'assets': {}}
    for a in ASSETS:
        sym = symbol_of(a)
        ds: dict = {}
        if a == 'BTCDOM':
            ds['idx1h'] = _summ(listing(UM, 'klines', sym, '1h'))
        else:
            ds['metrics_daily'] = _summ(list_prefix(f'{UM}/daily/metrics/{sym}/'))
            for kind in ('klines', 'premiumIndexKlines', 'markPriceKlines', 'indexPriceKlines'):
                ds[f'{kind}_1m'] = _summ(listing(UM, kind, sym, '1m'))
            ds['fundingRate_monthly'] = _summ(list_prefix(f'{UM}/monthly/fundingRate/{sym}/'))
            ds['bookDepth_daily'] = _summ(list_prefix(f'{UM}/daily/bookDepth/{sym}/'))
            agg: dict = {}
            for market, base in (('spot', SPOT), ('perp', UM)):
                es = listing(base, 'aggTrades', sym, None)
                per_year: dict = {}
                for e in es:
                    y = date_of(e['key'])[:4]
                    d = per_year.setdefault(y, {'files': 0, 'bytes': 0, 'largest_bytes': 0})
                    d['files'] += 1
                    d['bytes'] += e['size']
                    d['largest_bytes'] = max(d['largest_bytes'], e['size'])
                agg[market] = {'summary': _summ(es), 'per_year': per_year}
            ds['aggTrades'] = agg
        res['assets'][a] = ds
        log('preflight', a, 'done')
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, 'w') as f:
        json.dump(res, f, indent=1, sort_keys=True)
    return res


# --- small -------------------------------------------------------------------------------------------------------------
class Manifest:
    def __init__(self):
        self.entries: list[dict] = []
        self.datasets: dict = {}

    def add(self, e: dict, sha: str, rows: int, extra: dict | None = None) -> None:
        d = {'key': e['key'], 'bytes': e['size'], 'etag': e['etag'], 'last_modified': e['last_modified'], 'sha256': sha,
             'downloaded_at': now_utc(), 'rows': int(rows)}
        if extra:
            d.update(extra)
        self.entries.append(d)

    def dataset(self, name: str, first, last, rows: int) -> None:
        self.datasets[name] = {'first': first, 'last': last, 'rows': int(rows)}

    def write(self, path: str, asset: str) -> None:
        with open(path, 'w') as f:
            json.dump({'asset': asset, 'generated_at': now_utc(), 'datasets': self.datasets, 'entries': self.entries}, f, indent=1)


def _read_member(path: str) -> bytes:
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if not n.endswith('/')]
        if len(names) != 1:
            raise RuntimeError(f'{os.path.basename(path)}: expected one member, got {len(names)}')
        return z.read(names[0])


def _fetch_parse(e: dict, work: str, parse):
    """Download one zip, parse it, delete it. Returns (entry, sha, parsed)."""
    p = os.path.join(work, re.sub(r'[^A-Za-z0-9._-]', '_', e['key']))
    try:
        sha = fetch_zip(e['key'], e['size'], p)
        return e, sha, parse(p)
    finally:
        if os.path.exists(p):
            os.remove(p)


def _fetch_all(entries: list[dict], work: str, parse, workers: int = 8) -> list:
    if not entries:
        return []
    with ThreadPoolExecutor(workers) as ex:
        return list(ex.map(lambda e: _fetch_parse(e, work, parse), entries))


def write_gz_csv(df: pd.DataFrame, path: str) -> None:
    with gzip.open(path, 'wt', newline='', compresslevel=6) as f:
        df.to_csv(f, index=False, lineterminator='\n')


def _klines(entries, work, keep, man: Manifest) -> pd.DataFrame:
    res = _fetch_all(entries, work, lambda p: red.read_klines_csv(_read_member(p), keep))
    frames = []
    for e, sha, df in res:
        man.add(e, sha, len(df))
        frames.append(df)
    if not frames:
        return pd.DataFrame({c: np.array([], dtype=np.int64 if c == 'ts' else np.float64) for c in keep})
    df = pd.concat(frames, ignore_index=True)
    return df.drop_duplicates('ts', keep='last').sort_values('ts', kind='stable').reset_index(drop=True)


def _ds(man: Manifest, name: str, df: pd.DataFrame, tcol: str = 'ts') -> None:
    if len(df):
        man.dataset(name, int(df[tcol].iloc[0]), int(df[tcol].iloc[-1]), len(df))
    else:
        man.dataset(name, None, None, 0)


def small(asset: str, out: str, workers: int = 8) -> dict:
    sym = symbol_of(asset)
    os.makedirs(out, exist_ok=True)
    man = Manifest()
    report: dict = {'asset': asset}
    with tempfile.TemporaryDirectory() as work:
        if asset == 'BTCDOM':
            idx = _klines(listing(UM, 'klines', sym, '1h'), work, ['ts', 'o', 'h', 'l', 'c', 'v'], man)
            write_gz_csv(idx, os.path.join(out, 'idx1h.csv.gz'))
            _ds(man, 'idx1h', idx)
            man.write(os.path.join(out, 'manifest.json'), asset)
            report['idx1h_rows'] = len(idx)
            log(asset, 'idx1h rows', len(idx), 'first/last', *( [int(idx.ts.iloc[0]), int(idx.ts.iloc[-1])] if len(idx) else ['-', '-']))
            return report

        um = _klines(listing(UM, 'klines', sym, '1m'), work, ['ts', 'o', 'h', 'l', 'c', 'v', 'tb'], man)
        mark = _klines(listing(UM, 'markPriceKlines', sym, '1m'), work, ['ts', 'o', 'h', 'l', 'c'], man)
        index = _klines(listing(UM, 'indexPriceKlines', sym, '1m'), work, ['ts', 'o', 'h', 'l', 'c'], man)
        prem = _klines(listing(UM, 'premiumIndexKlines', sym, '1m'), work, ['ts', 'o', 'h', 'l', 'c'], man)
        for name, df in (('um_1m', um), ('mark_1m', mark), ('index_1m', index), ('premium_1m', prem)):
            write_gz_csv(df, os.path.join(out, f'{name}.csv.gz'))
            _ds(man, name, df)
            log(asset, name, 'rows', len(df), 'first/last', *([int(df.ts.iloc[0]), int(df.ts.iloc[-1])] if len(df) else ['-', '-']))

        # premium stamp test (the job fails if it does not resolve)
        st = red.premium_stamp_test(prem, um, index)
        with open(os.path.join(out, 'premium_stamp.json'), 'w') as f:
            json.dump(st, f, indent=1)
        log(asset, 'premium stamp test', {k: st[k] for k in ('fits', 'resolved', 'corr_same', 'corr_next')})
        report['premium_stamp'] = st

        # funding (monthly only)
        fres = _fetch_all(sorted(list_prefix(f'{UM}/monthly/fundingRate/{sym}/'), key=lambda e: e['key']), work,
                          lambda p: red.read_funding_csv(_read_member(p)), workers)
        fr = []
        for e, sha, df in fres:
            man.add(e, sha, len(df))
            fr.append(df)
        fund = (pd.concat(fr, ignore_index=True).drop_duplicates('calc_time', keep='last').sort_values('calc_time')
                if fr else pd.DataFrame(columns=['calc_time', 'funding_interval_hours', 'last_funding_rate']))
        write_gz_csv(fund, os.path.join(out, 'funding.csv.gz'))
        _ds(man, 'funding', fund, 'calc_time')
        log(asset, 'funding rows', len(fund))

        # metrics (daily) with the create_time convention
        ments = sorted(list_prefix(f'{UM}/daily/metrics/{sym}/'), key=lambda e: e['key'])
        mres = _fetch_all(ments, work, lambda p: red.read_metrics_csv(_read_member(p)), workers)
        um_grid, mark_grid = red.make_um_grid(um), red.make_mark_grid(mark)
        labels: dict = {}
        days = []
        for e, sha, df in mres:
            fname = os.path.basename(e['key'])
            lab = red.label_day(df, um_grid, mark_grid) if len(df) else {'conv': 'amb'}
            labels[fname] = lab
            days.append((fname, df, lab['conv']))
            man.add(e, sha, len(df), {'conv': lab['conv']})
        table = red.build_metrics_table(days, mark_grid)
        write_gz_csv(table, os.path.join(out, 'metrics.csv.gz'))
        _ds(man, 'metrics', table, 'S')
        rep = red.amb_report(labels)
        report['metrics'] = rep
        log(asset, 'metrics rows', len(table), 'days', len(ments), 'conv report', json.dumps(rep))
        with open(os.path.join(out, 'metrics_convention.json'), 'w') as f:
            keep = ('conv', 'single_test', 'a', 'b', 'r_left', 'r_right', 'gap_t', 'gap_t5')
            fin = lambda x: None if isinstance(x, float) and not np.isfinite(x) else x
            json.dump({'report': rep, 'days': {k: {c: fin(v.get(c)) for c in keep} for k, v in sorted(labels.items())}}, f)

        # bookDepth (daily, 2023+)
        bents = [e for e in sorted(list_prefix(f'{UM}/daily/bookDepth/{sym}/'), key=lambda e: e['key'])
                 if date_of(e['key']) >= BOOKDEPTH_FROM]
        bres = _fetch_all(bents, work, lambda p: red.bookdepth_reshape(_read_member(p)), workers)
        bf = []
        spacings = []
        for e, sha, (df, sp) in bres:
            man.add(e, sha, len(df), {'spacing_ms': sp})
            spacings.append(sp)
            bf.append(df)
        book = (pd.concat(bf, ignore_index=True).drop_duplicates('ts', keep='last').sort_values('ts')
                if bf else pd.DataFrame({'ts': np.array([], dtype=np.int64), 'bid_1pct': [], 'ask_1pct': []}))
        write_gz_csv(book, os.path.join(out, 'bookdepth_1pct.csv.gz'))
        _ds(man, 'bookdepth_1pct', book)
        man.datasets['bookdepth_1pct']['spacing_ms_median'] = int(np.median(spacings)) if spacings else None
        log(asset, 'bookdepth rows', len(book), 'files', len(bents), 'median spacing ms', man.datasets['bookdepth_1pct']['spacing_ms_median'])

    man.write(os.path.join(out, 'manifest.json'), asset)

    # fail loudly (after everything is written, so the files can be inspected)
    problems = []
    for name in ('A', 'B'):
        r = rep[name]
        if r['frac'] > AMB_MAX_FRAC:
            problems.append(f'{asset}: {r["amb"]} of {r["days"]} {name} days ambiguous ({r["frac"]:.2%} > {AMB_MAX_FRAC:.0%})')
    if not st['resolved']:
        problems.append(f'{asset}: premium stamp test unresolved {st["corr_same"]:.3f} vs {st["corr_next"]:.3f}')
    if problems:
        for p in problems:
            log('::error::' + p)
        raise SystemExit('; '.join(problems))
    return report


# --- agg ---------------------------------------------------------------------------------------------------------------
def read_agg_zip(path: str, reducer: red.AggReducer | None = None, block_size: int = 64 << 20) -> red.AggReducer:
    """Stream one aggTrades zip through pyarrow's CSV reader in blocks. Never extracts to disk."""
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.csv as pcsv
    reducer = reducer or red.AggReducer()
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if not n.endswith('/')]
        if len(names) != 1:
            raise RuntimeError(f'{os.path.basename(path)}: expected one member')
        with z.open(names[0]) as f:
            first = f.readline()
        header = red.has_header(first)
        ncols = len(first.split(b','))
        cols = (red.AGG_SPOT_COLS if ncols >= 8 else red.AGG_UM_COLS)[:ncols]
        with z.open(names[0]) as f:
            ropt = pcsv.ReadOptions(block_size=block_size, column_names=None if header else cols)
            if header:
                ropt = pcsv.ReadOptions(block_size=block_size)
            copt = pcsv.ConvertOptions(
                include_columns=['price', 'quantity', 'transact_time', 'is_buyer_maker'],
                column_types={'price': pa.float64(), 'quantity': pa.float64(), 'transact_time': pa.int64(),
                              'is_buyer_maker': pa.string()})
            rd = pcsv.open_csv(f, read_options=ropt, convert_options=copt)
            for batch in rd:
                if batch.num_rows == 0:
                    continue
                bm = pc.equal(pc.utf8_lower(batch.column('is_buyer_maker')), 'true').to_numpy(zero_copy_only=False)
                reducer.feed(batch.column('transact_time').to_numpy(zero_copy_only=False),
                             batch.column('price').to_numpy(zero_copy_only=False),
                             batch.column('quantity').to_numpy(zero_copy_only=False), bm)
    return reducer


def write_agg_parquet(df: pd.DataFrame, path: str, meta: dict) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq
    tbl = pa.Table.from_pandas(df, preserve_index=False)
    tbl = tbl.replace_schema_metadata({**(tbl.schema.metadata or {}), b'outside_source': json.dumps(meta).encode()})
    pq.write_table(tbl, path, compression='zstd')


def load_skip(path: str | None) -> set[str]:
    if not path or not os.path.exists(path):
        return set()
    return {ln.strip().strip('/') for ln in open(path) if ln.strip()}


def is_skipped(skip: set[str], market: str, ym: str) -> bool:
    rel = f'agg_{market}/{ym}.parquet'
    return any(s == rel or s.endswith('/' + rel) for s in skip)


def run_put(cmd: str | None, path: str, market: str) -> None:
    if not cmd:
        return
    env = dict(os.environ, OUTSIDE_FILE=path, OUTSIDE_DIR=os.path.dirname(path), OUTSIDE_MARKET=market,
               OUTSIDE_REL=f'agg_{market}/{os.path.basename(path)}')
    r = subprocess.run(cmd, shell=True, env=env)
    if r.returncode != 0:
        raise RuntimeError(f'put-cmd failed with exit {r.returncode} for {os.path.basename(path)}')


GAP_DAY_MIN = 1430      # minutes; a calendar day of a monthly file with fewer is re-read from its daily file
DAY_MS = 86_400_000


def fill_gap_days(df: pd.DataFrame, ym: str, daily_by_day: dict, work: str, src: list) -> tuple[pd.DataFrame, list]:
    """Some monthly aggTrades zips miss whole days (seen: BTCUSDT perp 2022-08, 2022-09, 2022-11) although the daily
    zips for those days exist. Every day of the month with fewer than GAP_DAY_MIN minutes is reduced again from its
    daily zip; the daily result replaces the day only when it has MORE minutes. Days before a listing have no daily zip
    and stay as they are. Returns the patched frame and one record per day looked at (aggregates only)."""
    y, m = (int(x) for x in ym.split('-'))
    start = pd.Timestamp(year=y, month=m, day=1, tz='UTC')
    days = pd.date_range(start, start + pd.offsets.MonthBegin(1), freq='D', inclusive='left')
    fills: list[dict] = []
    counts = pd.Series(df['ts'].to_numpy() // DAY_MS).value_counts() if len(df) else pd.Series(dtype=np.int64)
    for d in days:
        di = int(d.value // 10**6 // DAY_MS)
        have = int(counts.get(di, 0))
        if have >= GAP_DAY_MIN:
            continue
        e = daily_by_day.get(d.strftime('%Y-%m-%d'))
        if e is None:
            if have:
                fills.append({'day': d.strftime('%Y-%m-%d'), 'monthly_minutes': have, 'daily_minutes': None, 'used': False})
            continue
        p = os.path.join(work, 'gap.zip')
        sha = fetch_zip(e['key'], e['size'], p)
        r = read_agg_zip(p)
        os.remove(p)
        ddf = r.finish()
        ddf = ddf[(ddf['ts'].to_numpy() // DAY_MS) == di]
        used = len(ddf) > have
        fills.append({'day': d.strftime('%Y-%m-%d'), 'monthly_minutes': have, 'daily_minutes': int(len(ddf)), 'used': used})
        src.append({'key': e['key'], 'bytes': e['size'], 'etag': e['etag'], 'last_modified': e['last_modified'], 'sha256': sha,
                    'downloaded_at': now_utc(), 'rows': r.rows, 'gap_fill_day': d.strftime('%Y-%m-%d'), 'used': used,
                    'unit': r.unit})
        if used:
            keep = (df['ts'].to_numpy() // DAY_MS) != di
            df = pd.concat([df[keep], ddf], ignore_index=True)
    if any(f['used'] for f in fills):
        df = df.sort_values('ts', kind='stable').reset_index(drop=True)[red.AGG_COLUMNS].astype(red.agg_dtypes())
    return df, fills


def agg(asset: str, market: str, year: int, out: str, months: list[str] | None = None, put_cmd: str | None = None,
        skip_file: str | None = None) -> list[str]:
    if asset == 'BTCDOM':
        raise SystemExit('BTCDOM has no aggTrades job')
    sym = symbol_of(asset)
    if market not in ('spot', 'perp'):
        raise SystemExit('--market must be spot or perp')
    base = SPOT if market == 'spot' else UM
    skip = load_skip(skip_file)
    monthly = list_prefix(f'{base}/monthly/aggTrades/{sym}/')
    daily = list_prefix(f'{base}/daily/aggTrades/{sym}/')
    plan = [e for e in plan_months(monthly, daily) if date_of(e['key']).startswith(f'{year}-')]
    daily_by_day = {date_of(e['key']): e for e in daily if date_of(e['key']).startswith(f'{year}-')}
    by_month: dict[str, list[dict]] = {}
    for e in plan:
        by_month.setdefault(date_of(e['key'])[:7], []).append(e)
    wanted = [f'{year}-{m}' for m in (months or [f'{i:02d}' for i in range(1, 13)])]
    mdir = os.path.join(out, f'agg_{market}')
    os.makedirs(mdir, exist_ok=True)
    done = []
    for ym in wanted:
        ents = by_month.get(ym)
        if not ents:
            log(asset, market, ym, 'no file in the archive: skipped')
            continue
        # a month built only from daily zips (current month) is partial: never skipped, so a rerun refreshes it
        has_monthly = any('/monthly/' in e['key'] for e in ents)
        if is_skipped(skip, market, ym):
            if has_monthly:
                log(asset, market, ym, 'already on Drive: skipped')
                continue
            log(asset, market, ym, 'on Drive but built from daily files only: rebuilt')
        t0 = time.time()
        reducer = red.AggReducer()
        src = []
        fills: list[dict] = []
        with tempfile.TemporaryDirectory() as work:
            for e in sorted(ents, key=lambda x: x['key']):
                p = os.path.join(work, 'f.zip')
                sha = fetch_zip(e['key'], e['size'], p)
                before = reducer.rows
                read_agg_zip(p, reducer)
                os.remove(p)
                src.append({'key': e['key'], 'bytes': e['size'], 'etag': e['etag'], 'last_modified': e['last_modified'],
                            'sha256': sha, 'downloaded_at': now_utc(), 'rows': reducer.rows - before})
            df = reducer.finish()
            if has_monthly:
                df, fills = fill_gap_days(df, ym, daily_by_day, work, src)
        path = os.path.join(mdir, f'{ym}.parquet')
        trades = int(sum(f['rows'] for f in src if not f.get('gap_fill_day'))) + int(
            sum(f['rows'] for f in src if f.get('gap_fill_day') and f.get('used')))
        write_agg_parquet(df, path, {'asset': asset, 'market': market, 'unit': reducer.unit, 'trades': trades, 'files': src,
                                     'gap_fill': fills, 'gap_fill_rule': f'day with < {GAP_DAY_MIN} minutes in the monthly '
                                     'file: its daily file is reduced and replaces the day when it has more minutes'})
        n_fill = sum(1 for f in fills if f['used'])
        log(asset, market, ym, 'trades', trades, 'minutes', len(df), 'unit', reducer.unit,
            'gap days', len(fills), 'filled from daily', n_fill,
            'first/last', int(df.ts.iloc[0]) if len(df) else '-', int(df.ts.iloc[-1]) if len(df) else '-', f'{time.time() - t0:.0f}s')
        run_put(put_cmd, path, market)
        os.remove(path)
        done.append(ym)
    return done


# --- cli ---------------------------------------------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog='outside_fetch')
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('preflight')
    p.add_argument('--out', required=True)
    p = sub.add_parser('small')
    p.add_argument('--asset', required=True)
    p.add_argument('--out', required=True)
    p = sub.add_parser('agg')
    p.add_argument('--asset', required=True)
    p.add_argument('--market', required=True, choices=['spot', 'perp'])
    p.add_argument('--year', required=True, type=int)
    p.add_argument('--out', required=True)
    p.add_argument('--months', default='')
    p.add_argument('--put-cmd', default=None)
    p.add_argument('--skip-existing', default=None)
    a = ap.parse_args(argv)
    if a.cmd == 'preflight':
        preflight(a.out)
    elif a.cmd == 'small':
        small(a.asset, a.out)
    else:
        months = [m.strip().zfill(2) for m in a.months.split(',') if m.strip()] or None
        agg(a.asset, a.market, a.year, a.out, months, a.put_cmd, a.skip_existing)
    return 0


if __name__ == '__main__':
    sys.exit(main())
