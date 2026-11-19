"""Does the Kalshi 15-minute quote lag the coin's own spot price? RESEARCH ONLY.

The market-wide stage (marketbase) read the quote 3, 7 and 11 minutes into the window as close to fair for one week (YES -1.0c, NO +0.1c
before the fee, each about one standard error from zero). This stage asks whether the coin's spot, which anyone can read for free, adds to
that price. For every settled 15-minute BTC, ETH, SOL and XRP market it takes the same three quotes and the Coinbase 1-minute spot closed at
that moment, and builds two probabilities that the market ends YES if the coin were a driftless random walk:

    model       Phi( ln(spot / strike)        / (sigma * sqrt(minutes left)) )
    model_open  Phi( ln(spot / spot at open)  / (sigma * sqrt(minutes left)) )

sigma is the root mean square of the coin's 1-minute log returns over the hour before (a gap in the minute data counts as that many minutes);
minutes left run from the spot minute used (up to MAX_SPOT_AGE seconds before the quote) to the close. Coinbase is not the index the strike
comes from, and a constant basis b between them moves z of `model` by b / (sigma * sqrt(minutes left)): a basis of one or two basis points can
by itself move p by several cents and fill a gap cell. `model_open` uses only Coinbase's own move since the window opened, so a constant basis
cancels (and the basis noise at the open is added). A gap cell therefore uses the probability LESS favourable to the side (YES: the lower of
the two; NO: the higher), so a side counts as cheap only when both models say so.

It reads no trip file, no order and no account; it makes no order and changes nothing. Only public endpoints are called (Kalshi markets and
candlesticks, Coinbase 1-minute candles), so the log may print the full tables.

What each number means:
  brier     the mean squared error of model, model_open and the market's own mid (bid + ask) / 2 as forecasts of the outcome, over the rows
            with a two-sided quote (diff = model - mid, diff_open = model_open - mid: below zero means the spot model forecasts better than the
            market); *_better_days = days on which that model's mean was lower, out of the days with at least DAY_ROWS rows
  calibration  per probability bin of each forecast: rows, the mean forecast, and the share that ended YES (a calibrated forecast has the two
            equal); bins under MIN_CELL rows are not printed
  cells     as in marketbase (win_pct, cost_c, edge_c, fee_c, net_c, edge_days, net_days; the day counts need DAY_ROWS rows a day, and
            rows_by_day says how many each day had), by side and by gap = the less favourable model probability of that side minus what a taker
            pays for it (YES: min(model, model_open) - ask; NO: bid - max(model, model_open))
  basis_bps per coin, the median and spread of ln(Coinbase spot at the window's open / strike) in basis points
  counts    per coin, the rows that could not be built and why (no_strike, odd_strike, no_quote, no_spot, no_open_spot, no_vol, crossed) and
            the quotes with an empty side; rows = rows attempted and used per coin. The run stops when a coin loses more than MAX_LOST_SHARE
            of its rows to anything but a crossed quote, or a coin lacks minutes of spot on a full day.
Fixed in advance as the test: the cells gap>=+0.05 for YES and for NO (all offsets, all coins); the cuts by gap, offset and coin are for reading.
The week this is first run on is a first look, not the test: the test is the same two cells on days after it, with net_c above zero on most
days and at least DAY_ROWS rows a day. No standard error is printed: rows are three per market and the four coins move together, so read
edge_c against about one cent of noise per 2,500 independent markets.
Not modelled: Kalshi may settle on an average of the index over the last minute (the horizon is then a little shorter); the quote is the
close of a one-minute candle, not a fill, and is up to marketbase.MAX_QUOTE_AGE seconds old if a minute has no candle; the fee is per
contract, so a one-contract order pays up to a cent more and net_c is a little optimistic.
"""
import bisect
import collections
import math
import statistics
import tempfile
import time

from . import marketbase, outcomes, paths
from .anatomy import MIN_CELL

COIN = {'KXBTC15M': 'BTC', 'KXETH15M': 'ETH', 'KXSOL15M': 'SOL', 'KXXRP15M': 'XRP'}
VOL_WINDOW = 3600               # seconds of 1-minute returns behind sigma
MIN_RETURNS = 30                # fewer returns than this in the hour and the row has no sigma (a quiet or missing stretch)
MAX_SPOT_AGE = 90               # seconds: the spot minute used must have closed within this long before the quote
MIN_DAY_SPOT_SHARE = 0.9        # share of a full UTC day's 1440 spot minutes a coin must have, or the run stops (a table built on holes is not kept)
MAX_LOST_SHARE = 0.05           # share of a coin's quote rows that may fail to build (not counting crossed quotes) before the run stops
DAY_ROWS = 20                   # rows a day must have in a cell to count toward its day counts (marketbase counts days from 3 rows)
GAP_EDGES = (-0.10, -0.05, 0.0, 0.05, 0.10)
PRIMARY = 0.05                  # the gap the test is fixed on
BINS = 10
STRIKE_TYPES = (None, 'greater', 'greater_or_equal')


class Spot:
    """One coin's Coinbase 1-minute candles [start, low, high, open, close, volume], with the lookups the model needs."""

    def __init__(self, rows):
        self.rows = sorted((r for r in rows if outcomes._f(r[4]) and outcomes._f(r[4]) > 0), key=lambda r: r[0])
        self.starts = [r[0] for r in self.rows]

    def count_between(self, a, b):
        """Minutes that start in [a, b)."""
        return bisect.bisect_left(self.starts, b) - bisect.bisect_left(self.starts, a)

    def last_closed(self, t):
        """(close, seconds since it closed) of the last minute that closed at or before t, or (None, None)."""
        i = bisect.bisect_right(self.starts, t - 60) - 1
        if i < 0:
            return None, None
        return outcomes._f(self.rows[i][4]), t - (self.rows[i][0] + 60)

    def sigma(self, t):
        """The per-minute root mean square log return of the minutes that closed in (t - VOL_WINDOW, t], or None with fewer than
        MIN_RETURNS returns. A return across a gap is divided by the square root of the minutes it spans."""
        lo = bisect.bisect_right(self.starts, t - VOL_WINDOW - 60)
        hi = bisect.bisect_right(self.starts, t - 60)
        rs = []
        for i in range(lo + 1, hi):
            gap = (self.starts[i] - self.starts[i - 1]) / 60.0
            if gap > 0:
                rs.append(math.log(outcomes._f(self.rows[i][4]) / outcomes._f(self.rows[i - 1][4])) / math.sqrt(gap))
        if len(rs) < MIN_RETURNS:
            return None
        s = math.sqrt(sum(r * r for r in rs) / len(rs))
        return s if s > 0 else None


def phi(z):
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def model_p(spot_px, ref, sigma, minutes_left):
    """The probability the market ends YES under a driftless random walk, with REF the level the spot must end at or above, or None."""
    if not (spot_px and ref and sigma and minutes_left and minutes_left > 0) or spot_px <= 0 or ref <= 0 or sigma <= 0:
        return None
    return phi(math.log(spot_px / ref) / (sigma * math.sqrt(minutes_left)))


def rows_of(market, candles, spot, counts):
    """The quote rows of one settled market: dicts of offset, bid, ask, the two model probabilities and whether it ended YES. What
    cannot be built is counted in COUNTS (per market: no_result, odd_strike, no_strike; per quote: no_quote, crossed, no_spot,
    no_open_spot, no_vol; empty_bid and empty_ask note a quote with an empty side, which still makes a row for the other side)."""
    result = market.get('result')
    if result not in ('yes', 'no'):
        counts['no_result'] += 1
        return []
    counts['strike_type:%s' % market.get('strike_type')] += 1
    if market.get('strike_type') not in STRIKE_TYPES:
        counts['odd_strike'] += 1
        return []
    strike = outcomes._f(market.get('floor_strike'))
    if not strike or strike <= 0:
        counts['no_strike'] += 1
        return []
    close = paths.iso_epoch(market['close_time'])
    open_px, open_age = spot.last_closed(close - marketbase.WINDOW)
    rows = []
    for off in marketbase.OFFSETS:
        t = close - marketbase.WINDOW + off
        bid, ask = marketbase.quote_at(candles, t)
        if bid is None or ask is None:
            counts['no_quote'] += 1
            continue
        if bid > ask:
            counts['crossed'] += 1
            continue
        px, age = spot.last_closed(t)
        if px is None or age > MAX_SPOT_AGE:
            counts['no_spot'] += 1
            continue
        if open_px is None or open_age > MAX_SPOT_AGE:
            counts['no_open_spot'] += 1
            continue
        sg = spot.sigma(t)
        left = (close - t + age) / 60.0         # from the spot minute used to the close
        p, p_open = model_p(px, strike, sg, left), model_p(px, open_px, sg, left)
        if p is None or p_open is None:
            counts['no_vol'] += 1
            continue
        counts['empty_bid'] += 1 if bid <= 0 else 0
        counts['empty_ask'] += 1 if ask >= 1 else 0
        rows.append({'off': off, 'bid': bid, 'ask': ask, 'p': p, 'p_open': p_open, 'yes': result == 'yes'})
    return rows


def gaps(r):
    """(YES gap, NO gap) of a quote row: the model probability of the side LESS favourable to it, minus what a taker pays for it. YES
    pays the ask, so its gap is min(model, model_open) - ask; NO pays one minus the bid, so its probability is one minus the model's
    and its gap is (1 - max(model, model_open)) - (1 - bid) = bid - max(model, model_open)."""
    return min(r['p'], r['p_open']) - r['ask'], r['bid'] - max(r['p'], r['p_open'])


def gap_bucket(g):
    lo = None
    for e in GAP_EDGES:
        if g < e:
            return ('<%+.2f' % e) if lo is None else ('%+.2f..%+.2f' % (lo, e))
        lo = e
    return '>=%+.2f' % GAP_EDGES[-1]


def labels(off, gap, series):
    out = ['all', 'gap:' + gap_bucket(gap)]
    if gap >= PRIMARY:
        out += ['gap>=%+.2f' % PRIMARY, 'gap>=%+.2f|offset:%ds' % (PRIMARY, off), 'gap>=%+.2f|coin:%s' % (PRIMARY, COIN[series])]
    if gap >= 2 * PRIMARY:
        out.append('gap>=%+.2f' % (2 * PRIMARY))
    return out


class Cell(marketbase.Cell):
    """marketbase's cell, with a day counted from DAY_ROWS rows and the rows of each day printed."""
    day_min = DAY_ROWS

    def out(self):
        c = super().out()
        c['rows_by_day'] = {d: v[0] for d, v in sorted(self.by_day.items())}
        return c


class Score:
    """Brier score of the two model probabilities and of the market's mid over the rows added, in total and by day."""

    def __init__(self):
        self.n = 0
        self.model = self.open = self.mid = 0.0
        self.by_day = collections.defaultdict(lambda: [0, 0.0, 0.0, 0.0])

    def add(self, day, p, p_open, mid, yes):
        y = 1.0 if yes else 0.0
        m, o, k = (p - y) ** 2, (p_open - y) ** 2, (mid - y) ** 2
        self.n += 1
        self.model += m
        self.open += o
        self.mid += k
        d = self.by_day[day]
        d[0] += 1
        d[1] += m
        d[2] += o
        d[3] += k

    def out(self):
        days = [d for d in self.by_day.values() if d[0] >= DAY_ROWS]
        return {'n': self.n, 'model': round(self.model / self.n, 4), 'model_open': round(self.open / self.n, 4),
                'mid': round(self.mid / self.n, 4),
                'diff': round((self.model - self.mid) / self.n, 4), 'diff_open': round((self.open - self.mid) / self.n, 4),
                'model_better_days': '%d/%d' % (sum(1 for d in days if d[1] < d[3]), len(days)),
                'model_open_better_days': '%d/%d' % (sum(1 for d in days if d[2] < d[3]), len(days))}


def tabulate(items_by_series, spots):
    """{series: [(day, market, candles), ...]} to the printed report."""
    counts = collections.defaultdict(collections.Counter)
    cells = collections.defaultdict(Cell)
    scores = collections.defaultdict(Score)
    cal = collections.defaultdict(lambda: [0, 0.0, 0])         # (forecast name, bin): rows, summed forecast, rows that ended YES
    basis = collections.defaultdict(list)
    markets, attempted, used = {}, collections.Counter(), collections.Counter()
    for series, items in items_by_series.items():
        coin = COIN[series]
        markets[series] = len(items)
        spot = spots[series]
        for day, m, candles in items:
            strike = outcomes._f(m.get('floor_strike'))
            close = paths.iso_epoch(m['close_time'])
            px0, age0 = spot.last_closed(close - marketbase.WINDOW)
            if strike and strike > 0 and px0 is not None and age0 <= MAX_SPOT_AGE:
                basis[coin].append(1e4 * math.log(px0 / strike))
            if m.get('result') in ('yes', 'no'):
                attempted[coin] += len(marketbase.OFFSETS)
            rows = rows_of(m, candles, spot, counts[coin])
            used[coin] += len(rows)
            for r in rows:
                bid, ask, p, po, off = r['bid'], r['ask'], r['p'], r['p_open'], r['off']
                gap_yes, gap_no = gaps(r)
                if 0 < bid <= ask < 1:
                    mid = (bid + ask) / 2.0
                    for key in ('all', 'offset:%ds' % off):
                        scores[key].add(day, p, po, mid, r['yes'])
                    for name, x in (('model', p), ('model_open', po), ('mid', mid)):
                        c = cal[(name, min(int(x * BINS), BINS - 1))]
                        c[0] += 1
                        c[1] += x
                        c[2] += 1 if r['yes'] else 0
                if 0 < ask < 1:
                    for lab in labels(off, gap_yes, series):
                        cells[('yes', lab)].add(day, ask, r['yes'], m['ticker'])
                if 0 < bid < 1:
                    for lab in labels(off, gap_no, series):
                        cells[('no', lab)].add(day, round(1 - bid, 6), not r['yes'], m['ticker'])
    table, withheld = {}, 0
    for (side, lab), c in sorted(cells.items()):
        if c.n >= MIN_CELL:
            table.setdefault(side, {})[lab] = c.out()
        else:
            withheld += 1
    calibration = {}
    for (name, b), (n, s, y) in sorted(cal.items()):
        if n >= MIN_CELL:
            calibration.setdefault(name, {})['%.1f-%.1f' % (b / BINS, (b + 1) / BINS)] = {
                'n': n, 'forecast_pct': round(100 * s / n, 1), 'yes_pct': round(100 * y / n, 1)}
    return {'markets': markets, 'counts': {k: dict(sorted(v.items())) for k, v in sorted(counts.items())},
            'rows': {k: {'attempted': attempted[k], 'used': used[k]} for k in sorted(attempted)},
            'brier': {k: v.out() for k, v in sorted(scores.items()) if v.n},
            'calibration': calibration, 'cells': table, 'cells_under_floor': withheld,
            'basis_bps': {coin: {'n': len(v), 'median': round(statistics.median(v), 2), 'sd': round(statistics.pstdev(v), 2)}
                          for coin, v in sorted(basis.items()) if v}}


def check_rows(out):
    """Stop when a coin lost more than MAX_LOST_SHARE of its quote rows to anything but a crossed quote: a table built on holes is not kept."""
    for coin, r in out['rows'].items():
        crossed = out['counts'].get(coin, {}).get('crossed', 0)
        lost = r['attempted'] - r['used'] - crossed
        if r['attempted'] and lost > MAX_LOST_SHARE * r['attempted']:
            raise RuntimeError('spotgap: %s lost %d of %d quote rows (%s)' % (coin, lost, r['attempted'], out['counts'].get(coin)))


def load_spots(t0, t1, days, cache, now):
    """{series: Spot} for the coins, covering the hour before the first window and the last window. Stops with an error when a
    coin's minutes cannot be fetched or a coin has under MIN_DAY_SPOT_SHARE of the 1440 minutes of a full UTC day (DAYS: the days
    of the run; a day that has not ended is not checked)."""
    a, b = t0 - marketbase.WINDOW - VOL_WINDOW - 120, t1 + 120
    out = {}
    for series in marketbase.SERIES:
        coin = COIN[series]
        rows = paths.spot_minutes(coin, a, b, cache)
        if not rows:
            raise RuntimeError('spotgap: the Coinbase minutes for %s could not be fetched' % coin)
        sp = Spot(rows)
        for k, lab in enumerate(days):
            d0 = t0 + 86400 * k
            if d0 + 86400 > now:
                continue
            have = sp.count_between(d0, d0 + 86400)
            if have < MIN_DAY_SPOT_SHARE * 1440:
                raise RuntimeError('spotgap: only %d of 1440 Coinbase minutes for %s on %s: the series has holes' % (have, coin, lab))
        out[series] = sp
    return out


def report(w, day, days=7, now=None, check_coverage=True, cache=None):
    """The spot-model test over every settled 15-minute market that closed in the DAYS UTC days ending with DAY (marketbase.read
    stops the run on a failed list, too many failed candle requests or holes in the coverage; load_spots on missing spot minutes;
    check_rows on quote rows that could not be built). W is unused (kept for the stage interface): nothing is read from or written to
    the work folder; the spot minutes are cached in a temporary folder (CACHE) of public data."""
    now = time.time() if now is None else now
    t0, t1, labs = marketbase.day_bounds(day, days)
    spots = load_spots(t0, t1, labs, cache or tempfile.mkdtemp(prefix='spotgap-'), now)
    got, meta = marketbase.read(day, days, now, check_coverage)
    out = tabulate(got, spots)
    check_rows(out)
    out.update({'days': meta['days'], 'partial_days': meta['partial_days'], 'markets_per_day': meta['markets_per_day'],
                'odd_windows': meta['odd_windows'], 'offsets_s': list(marketbase.OFFSETS), 'candle_requests': meta['candle_requests'],
                'candle_failures': meta['candle_failures'], 'primary_gap': PRIMARY,
                'note': 'public data (Kalshi, Coinbase); rows are up to three quotes per market and the four coins move together, so '
                        'not independent, and no standard error is printed; gap = the less favourable of two model probabilities of the '
                        'side minus its price; edge = win share - price paid, held to settlement, taker spread included; the fee is per '
                        'contract, so a one-contract order pays up to a cent more; Coinbase is a proxy for the index the strike uses'})
    return out
