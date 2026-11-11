"""Synthetic fixtures for the tennis part builder (oracle/tennis.py, SPEC 2c) and its tests. Nothing here is real data.

Writes Kalshi tennis history in the layout of the Drive tarball raw/tennis-history/kalshi/<SERIES>.tar.gz
(.github/workflows/tennis-ta-data.yml on branch 7817be: `tar --sort=name --mtime=@0 -C data/tennis/kalshi <SERIES>`):
  <SERIES>/<UTC close day>.jsonl          one KalshiHistMarket per line (research/history/kalshiHistory.ts): ticker, series,
                                          event, openTime, closeTime, strike, cap, result, settlement, volume, title,
                                          startTime, candles [{ts = candle END ms, bidO/H/L/C, askO/H/L/C, last, volume, oi}]
  <SERIES>/trades/<UTC close day>.jsonl   {ticker, trades: [[ts ms, yesPrice, count, takerSide 1 = YES / 0 = NO]]}
  <SERIES>/.index.json                    the downloader's index (not read by the builder)

    cd python && python3 -m oracle.fixtures_tennis --out /tmp/tf/KXATPMATCH.tar.gz --tour ATP --start 2026-05-04 --days 2
"""
from __future__ import annotations

import argparse
import io
import json
import os
import tarfile
from datetime import datetime, timezone

import numpy as np

from .common import MIN, ms

SERIES = {'ATP': 'KXATPMATCH', 'WTA': 'KXWTAMATCH'}


def day_of(t_ms: int) -> str:
    return datetime.fromtimestamp(t_ms / 1000, tz=timezone.utc).strftime('%Y-%m-%d')


def candle(ts: int, bid, ask, volume: float = 10.0) -> dict:
    """A 1-minute candle ending at ts with flat OHLC at its close quote (None = that side of the book is empty)."""
    c = {'ts': int(ts)}
    for side, v in (('bid', bid), ('ask', ask)):
        for f in 'OHLC':
            c[f'{side}{f}'] = None if v is None else round(float(v), 4)
    c['last'] = None if bid is None or ask is None else round((bid + ask) / 2, 4)
    c['volume'] = float(volume)
    c['oi'] = 100.0
    return c


def market_line(ticker: str, series: str, event: str, open_ms: int, close_ms: int, start_ms, result: str, candles: list,
                title: str | None = None) -> dict:
    m = {'ticker': ticker, 'series': series, 'event': event, 'openTime': int(open_ms), 'closeTime': int(close_ms), 'strike': None,
         'cap': None, 'result': result, 'settlement': 1.0 if result == 'yes' else 0.0 if result == 'no' else None,
         'volume': 1000.0, 'title': title or f'Will {ticker.rsplit("-", 1)[-1]} win the match?'}
    if start_ms is not None:
        m['startTime'] = int(start_ms)
    m['candles'] = candles
    return m


def scripted_market(ticker: str, series: str, event: str, start_ms: int, close_ms: int, quotes: dict, result: str,
                    open_ms: int | None = None, no_start: bool = False, title: str | None = None) -> dict:
    """A market whose candles are given by `quotes`: {minute offset from the start: (bid, ask) | (bid, None) | None}; the
    candle ending at start + offset min carries that close quote (None = a candle with an empty book); an offset missing
    from `quotes` has no candle (an empty minute)."""
    cs = [candle(start_ms + off * MIN, *(q if q is not None else (None, None))) for off, q in sorted(quotes.items())]
    return market_line(ticker, series, event, open_ms if open_ms is not None else start_ms - 2 * 86_400_000, close_ms,
                       None if no_start else start_ms, result, cs, title)


def mirror(quotes: dict) -> dict:
    """The other market of a match: YES bid/ask = 1 - this market's YES ask/bid."""
    out = {}
    for off, q in quotes.items():
        if q is None:
            out[off] = None
        else:
            out[off] = (None if q[1] is None else round(1 - q[1], 4), None if q[0] is None else round(1 - q[0], 4))
    return out


def flat(lo: int, hi: int, q) -> dict:
    return {k: q for k in range(lo, hi + 1)}


def tape_line(ticker: str, trades) -> dict:
    return {'ticker': ticker, 'trades': [[int(t), round(float(p), 4), float(c), int(s)] for t, p, c, s in trades]}


def random_match(series: str, event: str, start_ms: int, length_min: int, rng: np.random.Generator, gap_p: float = 0.03,
                 one_sided_tail: int = 3, prints_per_min: int = 3):
    """A two-market match with a random-walk P(A wins) quoted in whole cents: candles from 60 minutes before the start to the
    close (a few empty minutes; the last minutes one-sided as a finished match's book is), 1-2c spreads, and a tape of
    a few prints a minute whose taker side follows the move. Returns ([market A, market B], [tape A, tape B])."""
    close = start_ms + length_min * MIN + 30_000
    p = float(rng.uniform(0.15, 0.85))
    win_a = bool(rng.random() < p)
    qa: dict = {}
    trades_a = []
    for off in range(-60, length_min + 1):
        live = off >= 0
        dp = rng.normal(0, 0.012 if live else 0.004)
        if off > length_min - 15:
            dp += ((0.99 if win_a else 0.01) - p) * 0.25
        p = min(0.97, max(0.03, p + dp))
        if off > length_min - one_sided_tail:
            qa[off] = (0.99, None) if win_a else (None, 0.01)
            continue
        if rng.random() < gap_p:
            continue
        w = 0.01 if rng.random() < 0.7 else 0.02
        b = min(0.97, max(0.01, round(p - 0.01, 2)))
        qa[off] = (b, round(b + w, 2))
        for _ in range(int(rng.integers(0, (prints_per_min if live else max(1, prints_per_min // 3)) + 1))):
            ts = start_ms + (off - 1) * MIN + int(rng.integers(0, 60_000))
            side = int(rng.random() < (0.7 if dp > 0 else 0.3))
            trades_a.append((ts, qa[off][1] if side else qa[off][0], int(rng.integers(1, 60)), side))
    qb = mirror(qa)
    trades_b = [(t, round(1 - px, 2), c, 1 - s) for t, px, c, s in trades_a]
    ra, rb = ('yes', 'no') if win_a else ('no', 'yes')
    ta, tb = f'{event}-AAA', f'{event}-BBB'
    ma = scripted_market(ta, series, event, start_ms, close, qa, ra)
    mb = scripted_market(tb, series, event, start_ms, close, qb, rb)
    return [ma, mb], [tape_line(ta, sorted(trades_a)), tape_line(tb, sorted(trades_b))]


def write_history(root: str, series: str, markets: list, tapes: list, extra_files: dict | None = None) -> str:
    """Write the extracted layout under <root>/<series>/ (day files by UTC close day) and return that directory.
    extra_files: {relative path under <series>/: text} written as given (e.g. a sentinel day file)."""
    d = os.path.join(root, series)
    os.makedirs(os.path.join(d, 'trades'), exist_ok=True)
    close_of = {m['ticker']: m['closeTime'] for m in markets}
    by_day: dict = {}
    for m in markets:
        by_day.setdefault(day_of(m['closeTime']), []).append(json.dumps(m))
    by_tday: dict = {}
    for tp in tapes:
        by_tday.setdefault(day_of(close_of[tp['ticker']]), []).append(json.dumps(tp))
    index = {'v': 1, 'files': {}}
    for day, lines in sorted(by_day.items()):
        text = '\n'.join(lines) + '\n'
        with open(os.path.join(d, f'{day}.jsonl'), 'w') as f:
            f.write(text)
        index['files'][f'{day}.jsonl'] = {'size': len(text.encode()), 'rows': [
            {k: v for k, v in json.loads(x).items() if k in ('ticker', 'openTime', 'closeTime', 'startTime')} for x in lines]}
    for day, lines in sorted(by_tday.items()):
        with open(os.path.join(d, 'trades', f'{day}.jsonl'), 'w') as f:
            f.write('\n'.join(lines) + '\n')
    if markets:
        index['listed'] = {'from': min(m['closeTime'] for m in markets), 'to': max(m['closeTime'] for m in markets)}
    with open(os.path.join(d, '.index.json'), 'w') as f:
        json.dump(index, f)
    for rel, text in (extra_files or {}).items():
        p = os.path.join(d, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'w') as f:
            f.write(text)
    return d


def write_tarball(series_dir: str, out_path: str) -> str:
    """<series>.tar.gz of an extracted series directory, member names <series>/..., sorted, mtime 0, owner 0 (as the
    workflow builds it)."""
    base = os.path.dirname(os.path.normpath(series_dir))
    series = os.path.basename(os.path.normpath(series_dir))
    names = []
    for dp, _, fs in os.walk(series_dir):
        for f in fs:
            names.append(os.path.relpath(os.path.join(dp, f), base))
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with tarfile.open(out_path, 'w:gz', format=tarfile.GNU_FORMAT) as tf:
        dirs = sorted({os.path.dirname(n) for n in names} | {series})
        for n in sorted(set(dirs) | set(names)):
            full = os.path.join(base, n)
            ti = tarfile.TarInfo(n.replace(os.sep, '/'))
            ti.mtime = 0; ti.uid = ti.gid = 0; ti.uname = ti.gname = ''
            if os.path.isdir(full):
                ti.type = tarfile.DIRTYPE; ti.mode = 0o755
                tf.addfile(ti)
            else:
                data = open(full, 'rb').read()
                ti.size = len(data); ti.mode = 0o644
                tf.addfile(ti, io.BytesIO(data))
    return out_path


def random_history(series: str, start_day: str, days: int, per_day: int = 4, seed: int = 1, prints_per_min: int = 3):
    """Random matches from start_day for `days` days, per_day of them spread over 10:00-22:00 UTC."""
    rng = np.random.default_rng(seed)
    markets, tapes = [], []
    d0 = ms(start_day)
    for d in range(days):
        for i in range(per_day):
            start = d0 + d * 86_400_000 + int((10 + 12 * i / per_day) * 3_600_000)
            ev = f'{series}-{day_of(start).replace("-", "")}M{i}'
            ms_, ts_ = random_match(series, ev, start, int(rng.integers(70, 180)), rng, prints_per_min=prints_per_min)
            markets += ms_; tapes += ts_
    return markets, tapes


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description='Write a synthetic tennis history tarball (oracle SPEC 2c fixtures).')
    ap.add_argument('--out', required=True, help='the .tar.gz to write (its directory also gets the extracted <SERIES>/)')
    ap.add_argument('--tour', default='ATP')
    ap.add_argument('--start', default='2026-05-04')
    ap.add_argument('--days', type=int, default=2)
    ap.add_argument('--per-day', type=int, default=4)
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--prints-per-min', type=int, default=3)
    a = ap.parse_args(argv)
    series = SERIES[a.tour.upper()]
    markets, tapes = random_history(series, a.start, a.days, a.per_day, a.seed, a.prints_per_min)
    root = os.path.join(os.path.dirname(os.path.abspath(a.out)), 'extracted')
    d = write_history(root, series, markets, tapes)
    write_tarball(d, a.out)
    print(f'wrote {len(markets)} markets ({len(markets) // 2} matches) to {a.out} (extracted copy {d})')


if __name__ == '__main__':
    main()
