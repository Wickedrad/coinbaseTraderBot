"""Market-wide calibration of the Kalshi 15-minute crypto contracts, from PUBLIC market data only. RESEARCH ONLY.

The anatomy stage showed that the paper heat lane's YES entries settled about 4 cents under their price on every day of a week and
its NO entries about 4 cents over, and the lane's trips are not a random sample of markets. This stage asks the same question of
EVERY settled 15-minute BTC, ETH, SOL and XRP market: at a fixed time into the window, what did a taker pay for YES (the ask) and
for NO (one minus the YES bid), and how often did that side settle a winner? It reads no trip file, no order and no account;
it makes no order and changes nothing. Only public endpoints are called (the markets list and the 1-minute candlesticks), so the
log may print the full tables.

What each number means (per cell, before and after the entry fee, for one contract held to settlement):
  n         quote rows in the cell (three per market: the quote after OFFSETS seconds of the window, so rows of one market are
            not independent); markets = distinct settled markets read
  win_pct   share of the rows whose side settled a winner
  cost_c    the mean price a taker paid for the side, in cents (YES: ask; NO: one minus the YES bid), spread included
  edge_c    win_pct minus cost_c: the settlement edge of buying that side at that moment, before any fee
  fee_c     the mean taker entry fee, 0.07 * p * (1 - p) in cents; net_c = edge_c - fee_c is held to settlement, no exit fee
  edge_days / net_days   days with a positive edge / positive net_c, out of the days with at least DAY_MIN rows in the cell
A result of 0 for edge_c in every price band is a fair market; a YES edge below zero by day after day, with NO above, is a
market-level YES overpricing the lane could take or leave.
"""
import collections
import datetime
import time

from . import outcomes, paths
from .anatomy import DAY_MIN, MIN_CELL, PX_EDGES, _bucket

SERIES = ('KXBTC15M', 'KXETH15M', 'KXSOL15M', 'KXXRP15M')
OFFSETS = (180, 420, 660)       # seconds after the window opens (the window is the 900 s that end at the close time)
WINDOW = 900
PAGE = 1000
MAX_ERROR_SHARE = 0.02          # candle requests that may fail before the run stops (a table built on holes is not kept)
PAUSE = 0.05
MAX_QUOTE_AGE = 120             # seconds: a quote older than this at the offset is not used (quiet minutes with no candle)
EXPECTED_PER_DAY = 96           # settled markets a series has on a full UTC day (one per 15 minutes)
MIN_DAY_SHARE = 0.5             # a full day with fewer than this share of them stops the run: the list is truncated or past the live window


def day_bounds(day, days):
    """(first epoch second, end epoch second, [day labels]) of the DAYS UTC days that end with DAY (inclusive)."""
    end = datetime.datetime.strptime(day, '%Y-%m-%d').replace(tzinfo=datetime.timezone.utc) + datetime.timedelta(days=1)
    start = end - datetime.timedelta(days=days)
    labels = [(start + datetime.timedelta(days=i)).strftime('%Y-%m-%d') for i in range(days)]
    return int(start.timestamp()), int(end.timestamp()), labels


def list_settled(series, t0, t1):
    """Every settled market of SERIES that closed in [t0, t1): the markets list, followed by its cursor."""
    out, seen, cursor = [], set(), ''
    while True:
        # the API bounds are widened by a second each way (they may be exclusive); report() filters on the exact close time
        url = '%s/markets?series_ticker=%s&status=settled&min_close_ts=%d&max_close_ts=%d&limit=%d%s' % (
            paths.KALSHI, series, t0 - 1, t1, PAGE, ('&cursor=' + cursor) if cursor else '')
        r = paths.get(url)
        if not isinstance(r, dict) or ('error' in r and len(r) == 1):
            raise RuntimeError('marketbase: the markets list for %s failed (%s)' % (series, (r or {}).get('error') if isinstance(r, dict) else r))
        for m in r.get('markets') or []:
            if m.get('ticker') not in seen:
                seen.add(m.get('ticker'))
                out.append(m)
        cursor = r.get('cursor') or ''
        if not cursor:
            return out
        time.sleep(PAUSE)


def candles_of(market, series):
    """The 1-minute candlesticks of the window, or None when the request failed."""
    close = paths.iso_epoch(market['close_time'])
    url = '%s/series/%s/markets/%s/candlesticks?start_ts=%d&end_ts=%d&period_interval=1' % (
        paths.KALSHI, series, market['ticker'], close - WINDOW - 60, close + 60)
    r = paths.get(url)
    if not isinstance(r, dict) or 'error' in r:
        return None
    return sorted(r.get('candlesticks') or [], key=lambda c: c.get('end_period_ts') or 0)


def quote_at(candles, t):
    """(YES bid, YES ask) in dollars at the close of the last candle that ended at or before t and no more than MAX_QUOTE_AGE seconds
    before it, or (None, None)."""
    last = None
    for c in candles:
        if (c.get('end_period_ts') or 0) <= t:
            last = c
        else:
            break
    if last is None or t - (last.get('end_period_ts') or 0) > MAX_QUOTE_AGE:
        return None, None
    return outcomes._px(last.get('yes_bid'), 'close'), outcomes._px(last.get('yes_ask'), 'close')


def rows_of(market, candles):
    """The quote rows of one settled market: (offset, side, cost, won) for YES at the ask and NO at one minus the bid."""
    result = market.get('result')
    if result not in ('yes', 'no'):
        return []
    close = paths.iso_epoch(market['close_time'])
    rows = []
    for off in OFFSETS:
        bid, ask = quote_at(candles, close - WINDOW + off)
        if bid is not None and ask is not None and bid > ask:
            continue                                  # a crossed quote is not one a taker saw
        if ask is not None and 0 < ask < 1:           # an empty ask is 1.00 (or missing): nothing to buy
            rows.append((off, 'yes', ask, result == 'yes'))
        if bid is not None and 0 < bid < 1:           # an empty bid is 0.00 (or missing): nothing to sell into
            rows.append((off, 'no', round(1 - bid, 6), result == 'no'))
    return rows


class Cell:
    def __init__(self):
        self.n = self.wins = 0
        self.cost = self.fee = 0.0
        self.by_day = collections.defaultdict(lambda: [0, 0, 0.0, 0.0])
        self.markets = set()

    def add(self, day, cost, won, ticker):
        fee = 0.07 * cost * (1 - cost)
        self.n += 1
        self.wins += 1 if won else 0
        self.cost += cost
        self.fee += fee
        d = self.by_day[day]
        d[0] += 1
        d[1] += 1 if won else 0
        d[2] += cost
        d[3] += fee
        self.markets.add(ticker)

    def out(self):
        win, cost, fee = self.wins / self.n, self.cost / self.n, self.fee / self.n
        days = [d for d in self.by_day.values() if d[0] >= DAY_MIN]
        return {'n': self.n, 'markets': len(self.markets), 'win_pct': round(100 * win, 1), 'cost_c': round(100 * cost, 1),
                'edge_c': round(100 * (win - cost), 1), 'fee_c': round(100 * fee, 2), 'net_c': round(100 * (win - cost - fee), 1),
                'edge_days': '%d/%d' % (sum(1 for d in days if d[1] - d[2] > 1e-9), len(days)),
                'net_days': '%d/%d' % (sum(1 for d in days if d[1] - d[2] - d[3] > 1e-9), len(days))}


def labels(off, side, cost, series):
    """The cells a quote row belongs to: the side alone, the side in the lane's price range, and the side by price band, offset
    and series."""
    mid = 0.2 <= cost < 0.8
    out = [(side, 'all'), (side, 'band:' + _bucket(cost, PX_EDGES)), (side, 'offset:%ds' % off), (side, 'series:' + series)]
    if mid:
        out.append((side, 'mid(0.2-0.8)'))
    return out


def tabulate(rows_by_series):
    """{series: [(day, ticker, [(offset, side, cost, won), ...]), ...]} to the printed report."""
    cells = collections.defaultdict(Cell)
    markets = {}
    for series, items in rows_by_series.items():
        markets[series] = len(items)
        for day, ticker, rows in items:
            for off, side, cost, won in rows:
                for key in labels(off, side, cost, series):
                    cells[key].add(day, cost, won, ticker)
    table = {}
    for (side, cut), c in sorted(cells.items()):
        if c.n >= MIN_CELL:
            table.setdefault(side, {})[cut] = c.out()
    return {'markets': markets, 'cells': table}


def report(w, day, days=7, now=None, check_coverage=True):
    """The calibration of every settled 15-minute market that closed in the DAYS UTC days ending with DAY. W is unused (kept for the
    stage interface): nothing is read from or written to the work folder.

    The table stops with an error rather than print holes: a markets list that fails, more than MAX_ERROR_SHARE of the candle
    requests failing, or (CHECK_COVERAGE) a series that has no market at all, or a full UTC day with under MIN_DAY_SHARE of the
    EXPECTED_PER_DAY markets (a truncated list, or a day older than what the live API still holds). A day that has not ended yet is
    listed under partial_days and is not checked."""
    now = time.time() if now is None else now
    t0, t1, labels_ = day_bounds(day, days)
    rows_by_series, per_day, calls, failed, odd = {}, {}, 0, 0, 0
    for series in SERIES:
        items, counts = [], collections.Counter()
        for m in list_settled(series, t0, t1):
            if not m.get('ticker') or not m.get('close_time'):
                continue
            close = paths.iso_epoch(m['close_time'])
            if not (t0 <= close < t1):
                continue
            d = datetime.datetime.fromtimestamp(close, datetime.timezone.utc).strftime('%Y-%m-%d')
            counts[d] += 1
            if m.get('open_time') and abs(close - paths.iso_epoch(m['open_time']) - WINDOW) > 60:
                odd += 1                                  # opened earlier or closed early: the quote offsets are not 3, 7, 11 minutes in
            calls += 1
            c = candles_of(m, series)
            time.sleep(PAUSE)
            if c is None:
                failed += 1
                if failed > max(5, MAX_ERROR_SHARE * max(calls, 1)):
                    raise RuntimeError('marketbase: %d of %d candle requests failed; stopping' % (failed, calls))
                continue
            items.append((d, m['ticker'], rows_of(m, c)))
        rows_by_series[series] = items
        per_day[series] = {lab: counts.get(lab, 0) for lab in labels_}
    day_end = {lab: t0 + 86400 * (k + 1) for k, lab in enumerate(labels_)}
    partial = [lab for lab in labels_ if day_end[lab] > now]
    if check_coverage:
        for series in SERIES:
            if not any(per_day[series].values()):
                raise RuntimeError('marketbase: no settled %s market in %s..%s (a day older than the live API holds?)' % (series, labels_[0], labels_[-1]))
            for lab in labels_:
                if lab not in partial and per_day[series][lab] < MIN_DAY_SHARE * EXPECTED_PER_DAY:
                    raise RuntimeError('marketbase: only %d settled %s markets on %s (expected about %d): the list is truncated' % (
                        per_day[series][lab], series, lab, EXPECTED_PER_DAY))
    out = tabulate(rows_by_series)
    out.update({'days': labels_, 'partial_days': partial, 'markets_per_day': per_day, 'odd_windows': odd, 'offsets_s': list(OFFSETS),
                'candle_requests': calls, 'candle_failures': failed,
                'note': 'public market data; rows are up to three quotes per market, so not independent; edge = win share - price paid, held '
                        'to settlement, taker spread included; the fee is per contract (a one-contract order pays up to a cent more)'})
    return out
