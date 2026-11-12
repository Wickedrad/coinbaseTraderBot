"""Capture books in held-side terms. Prices are integers in 1e-4 dollars, sizes are contracts.

A capture row is {t, k, x, yb, ya}: t = request start, k = response end (runner clock, ms), x = ticker, yb = YES bids
high to low, ya = YES asks low to high (1 minus a NO bid), at most 3 levels each, [price dollars, size contracts].
Held side YES: bids = yb, asks = ya. Held side NO: the NO bid is 1 minus the YES ask, so bids = 1 - ya, asks = 1 - yb.
"""
from __future__ import annotations

import glob
import gzip
import io
import json
import os
import re
from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from . import UNIT

Level = Tuple[int, float]


@dataclass(frozen=True)
class Sample:
    t: int
    k: int
    x: str
    yb: Tuple[Level, ...]
    ya: Tuple[Level, ...]


@dataclass(frozen=True)
class HeldBook:
    bids: Tuple[Level, ...]   # high to low
    asks: Tuple[Level, ...]   # low to high


def u(price: float) -> int:
    return int(round(float(price) * UNIT))


def held_book(s: Sample, side: str) -> HeldBook:
    if side == 'yes':
        return HeldBook(s.yb, s.ya)
    return HeldBook(tuple((UNIT - p, z) for p, z in s.ya), tuple((UNIT - p, z) for p, z in s.yb))


class Grid:
    """A market's valid prices as bands (start, end, step) in YES-price units; edges belong to both neighbours."""

    def __init__(self, bands: List[Tuple[int, int, int]]):
        self.bands = sorted(bands)

    @classmethod
    def from_market(cls, m: Optional[dict]) -> 'Grid':
        bands: List[Tuple[int, int, int]] = []
        for b in (m or {}).get('priceRanges') or []:
            try:
                s, e, st = u(b['start']), u(b['end']), u(b['step'])
            except (KeyError, TypeError, ValueError):
                bands = []
                break
            if st > 0 and e > s:
                bands.append((s, e, st))
        if bands:
            return cls(bands)
        try:
            st = u((m or {}).get('tickSize') or 0.01)
        except (TypeError, ValueError):
            st = 100
        return cls([(0, UNIT, st if st > 0 else 100)])

    def step_above(self, p: int) -> int:
        """Step of the band that contains the interval just above p."""
        for s, e, st in self.bands:
            if s <= p < e:
                return st
        return self.bands[-1][2]

    def step_below(self, p: int) -> int:
        for s, e, st in self.bands:
            if s < p <= e:
                return st
        return self.bands[0][2]


class HeldGrid:
    """Tick steps in held-side price terms (a NO price p is the YES price 1 - p, so up and down swap)."""

    def __init__(self, grid: Grid, side: str):
        self.grid, self.side = grid, side

    def up(self, p: int) -> int:
        return self.grid.step_above(p) if self.side == 'yes' else self.grid.step_below(UNIT - p)

    def down(self, p: int) -> int:
        return self.grid.step_below(p) if self.side == 'yes' else self.grid.step_above(UNIT - p)


def series_of(ticker: str) -> str:
    return ticker.split('-')[0]


def kind_of(ticker: str, market: Optional[dict] = None) -> str:
    if market and market.get('kind') in ('15m', 'hourly'):
        return market['kind']
    return '15m' if series_of(ticker).endswith('15M') else 'hourly'


_MON = {m: i + 1 for i, m in enumerate(['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'])}
_CLOSE_RE = re.compile(r'^(\d{2})([A-Z]{3})(\d{2})(\d{2})(\d{2})?$')


def close_ms(ticker: str, market: Optional[dict] = None) -> Optional[int]:
    """Contract close in epoch ms: the market row's closeTime, else parsed from the ticker (ET, winter offset only)."""
    if market and market.get('closeTime'):
        return int(market['closeTime'])
    parts = ticker.split('-')
    if len(parts) < 2:
        return None
    m = _CLOSE_RE.match(parts[1])
    if not m or m.group(2) not in _MON or _MON[m.group(2)] not in (11, 12, 1, 2):
        return None
    yy, mon, dd, hh, mm = 2000 + int(m.group(1)), _MON[m.group(2)], int(m.group(3)), int(m.group(4)), int(m.group(5) or 0)
    try:
        local = datetime(yy, mon, dd, hh, mm, tzinfo=timezone.utc)
    except ValueError:
        return None
    return int((local + timedelta(hours=5)).timestamp() * 1000)


class TickerSeries:
    """The samples of one ticker, sorted by request start."""

    def __init__(self, samples: List[Sample]):
        self.s = sorted(samples, key=lambda x: (x.t, x.k))
        self.ts = [x.t for x in self.s]

    def last_k_at_or_before(self, ms: int) -> int:
        """Index of the last sample whose response ended at or before ms (what the bot could have known), or -1."""
        i = bisect_right(self.ts, ms) - 1
        while i >= 0 and self.s[i].k > ms:
            i -= 1
        return i

    def evidence(self, tp: int, te: int) -> List[Sample]:
        """Samples requested at or after tp whose response ended by te."""
        lo = bisect_right(self.ts, tp - 1)
        out = []
        for x in self.s[lo:]:
            if x.t > te:
                break
            if x.k <= te:
                out.append(x)
        return out

    def max_gap(self, i0: int, i1: int) -> int:
        worst = 0
        for a, b in zip(self.s[i0:i1], self.s[i0 + 1:i1 + 1]):
            worst = max(worst, b.t - a.t)
        return worst


@dataclass
class Capture:
    series: Dict[str, TickerSeries]
    markets: Dict[str, dict]
    stats: Dict[str, int]


def _open(path: str):
    return io.TextIOWrapper(gzip.open(path, 'rb'), encoding='utf-8') if path.endswith('.gz') else open(path, encoding='utf-8')


def _files(root: str, stem: str) -> List[str]:
    out = []
    for ext in ('.jsonl.gz', '.jsonl'):
        out += glob.glob(os.path.join(root, '**', stem + ext), recursive=True)
    return sorted(out)


def _levels(rows) -> Tuple[Level, ...]:
    return tuple((u(p), float(z)) for p, z in (rows or []))


def load_capture(dirs: List[str], t_from_ms: int, t_to_ms: int) -> Capture:
    """Reads ONLY books and markets files. Rows outside [from, to] by request start are dropped; (ticker, t) is deduped."""
    seen = set()
    by_tk: Dict[str, List[Sample]] = {}
    markets: Dict[str, dict] = {}
    st = {'books_files': 0, 'books_rows': 0, 'books_kept': 0, 'dup': 0, 'bad': 0, 'doge_skipped': 0, 'out_of_window': 0}
    for d in dirs:
        for f in _files(d, 'books'):
            st['books_files'] += 1
            with _open(f) as fh:
                for line in fh:
                    st['books_rows'] += 1
                    try:
                        r = json.loads(line)
                        t, k, x = int(r['t']), int(r['k']), str(r['x'])
                        if not t_from_ms <= t <= t_to_ms:
                            st['out_of_window'] += 1
                            continue
                        if 'DOGE' in x.upper():
                            st['doge_skipped'] += 1
                            continue
                        if (x, t) in seen:
                            st['dup'] += 1
                            continue
                        seen.add((x, t))
                        by_tk.setdefault(x, []).append(Sample(t, k, x, _levels(r.get('yb')), _levels(r.get('ya'))))
                        st['books_kept'] += 1
                    except (ValueError, KeyError, TypeError):
                        st['bad'] += 1
        for f in _files(d, 'markets'):
            with _open(f) as fh:
                for line in fh:
                    try:
                        r = json.loads(line)
                        tk = str(r['ticker'])
                    except (ValueError, KeyError, TypeError):
                        continue
                    if 'DOGE' in tk.upper():
                        continue
                    if tk not in markets or int(r.get('at') or 0) >= int(markets[tk].get('at') or 0):
                        markets[tk] = r
    return Capture({k: TickerSeries(v) for k, v in by_tk.items()}, markets, st)
