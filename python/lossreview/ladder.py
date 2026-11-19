"""Are the Kalshi hourly strike ladders priced fairly, and do their thin strikes lag the coin's spot? RESEARCH ONLY.

The 15-minute check (marketbase, spotgap) found the quote close to fair and no lag behind the coin's spot at one-minute resolution. The
lane's worst edge was on the hourly ladders (hourly SOL -9.2c, hourly BTC -5.3c), which those stages do not cover. Each hour Kalshi lists a
ladder of "will the coin be above K at the top of the hour" markets (KXBTCD, KXETHD, KXSOLD, KXXRPD). This stage reads every settled ladder
event of the DAYS UTC days it is given, keeps the NEAREST strikes to the coin's spot (the others sit near 0 or 1, outside the lane's 0.2
to 0.8 range, and cost a candle request each), and takes three quotes per kept market, OFFSETS seconds into the 3,600 s window, with the
Coinbase 1-minute spot closed at that moment. Strikes are chosen from the spot at the FIRST offset only, so the choice uses nothing that
happens later. It reads no trip file, no order and no account; it makes no order and changes nothing. Only public endpoints are called
(Kalshi markets and candlesticks, Coinbase 1-minute candles), so the log may print the full tables.

Two spot-based signals per quote row, both from the driftless random-walk probability the market ends YES,
    p = Phi( ln(spot / strike) / (sigma * sqrt(minutes left)) )      (sigma: RMS of the 1-minute log returns of the hour before):
    lvl  the level gap   YES: p - ask;  NO: bid - p              (what spot says the side is worth minus what a taker pays; a constant basis
                         between Coinbase and the index the strike uses moves it: at 30 minutes left one basis point is about 0.1 of z)
    adj  the missing-adjustment gap, from the quote BACK seconds earlier:  q = mid_before + (p_now - p_before), both p with the same sigma,
                         and the gap is   YES: q - ask;  NO: bid - q.  It asks whether the market moved as far as spot did over the last
                         five minutes; a constant basis cancels in p_now - p_before. (Literature context: a one-minute change in a benchmark
                         probability moved prediction-market prices about 0.64-for-one, the rest arriving as drift over the next minutes,
                         most in thin markets: arXiv 10.48550/arxiv.2606.07811, abstract read only.)

What each number means (per cell, held to settlement, fee 0.07 * p * (1 - p) per contract, no exit fee):
  n, markets  rows (three per kept market) and distinct markets; rows of one hour (all coins, all strikes) are close to one observation
  win_pct, cost_c, edge_c, fee_c, net_c   as in marketbase (edge_c = win share - price paid, before the fee)
  edge_days / net_days   days with a positive edge / net_c, of the days with at least DAY_ROWS rows; rows_by_day says how many each had
  hours, se_c   distinct close hours in the cell, and the standard error of edge_c in cents with rows CLUSTERED by close hour (strikes and
                coins of one hour share one price path), so it is the noise to read edge_c against; none under two hours; with few hours
                the error is itself badly estimated, so a test needs at least MIN_HOURS of them
  quote:fresh / quote:old   every cell above is also cut by the age of the quote read: at most FRESH seconds since its candle ended, or older
                (a thin strike with no candle for a minute may have a stale quote that a spot move has already made wrong; a gap cell that
                holds only on old quotes is not tradable)
  brier / calibration   as in spotgap: model (p), adj (q) and the market mid as forecasts of the outcome, over rows with a two-sided quote
  survey  per series: markets listed, events, strikes per event, strike types, minutes from open to close, the fields of a market, the markets kept, and (top level) how
          many 1-minute candles the kept markets had: what the ladders look like, in case this first run shows a shape the stage did not expect
Fixed in advance as the test, to be read on days AFTER the first run: the cells adj>=+0.05 for YES and for NO (all offsets, all coins); the cells
lvl>=+0.05 are the same test on the level gap. A cell passes when net_c is above +1 cent, positive on most days with DAY_ROWS rows, over at least
400 rows in at least MIN_HOURS (30) close hours, edge_c is above two se_c, AND the same cell cut to fresh quotes (|quote:fresh) is positive too. The week this is first run on is a first look. The cuts by gap, offset, coin and price band are for reading.
Not modelled: the strike is of an index and spot is Coinbase's; Kalshi may settle on an average of the last minute; a quote is the close of a
one-minute candle, up to MAX_QUOTE_AGE seconds old, not a fill; strikes far from the spot are not read; the fee is per contract, so a
one-contract order pays up to a cent more.
"""
import collections
import datetime
import math
import statistics
import tempfile
import time

from . import marketbase, outcomes, paths, spotgap
from .anatomy import MIN_CELL

SERIES = ('KXBTCD', 'KXETHD', 'KXSOLD', 'KXXRPD')
COIN = {'KXBTCD': 'BTC', 'KXETHD': 'ETH', 'KXSOLD': 'SOL', 'KXXRPD': 'XRP'}
WINDOW = 3600
OFFSETS = (600, 1500, 2400)         # seconds into the hour: 10, 25 and 40 minutes
BACK = 300                          # the earlier quote of the missing-adjustment gap
MIN_HOURS = 30                      # close hours a cell needs before its standard error counts for a pass (documented; the stage prints hours)
NEAREST = 4                         # strikes kept per event: the closest to the spot at the first offset
MAX_QUOTE_AGE = 180                 # seconds: a thin strike may have no candle for a few minutes
FRESH = 60                          # seconds: a quote this young or younger is 'fresh'; the pre-set cells are also cut fresh / old
EXPECTED_PER_DAY = 24               # ladder events a full UTC day has per series
MIN_DAY_SHARE = 0.5                 # a full day with fewer events than this share of them stops the run
MAX_CHOSEN = 4000                   # kept markets (one candle request each) above which the run stops: the runner has 30 minutes
MAX_ERROR_SHARE = marketbase.MAX_ERROR_SHARE
PRIMARY = spotgap.PRIMARY
DAY_ROWS = spotgap.DAY_ROWS
MAX_LOST_SHARE = spotgap.MAX_LOST_SHARE
BINS = spotgap.BINS


def survey(listed):
    """What the listed ladder markets of one series look like: counts, strikes per event, strike types, open to close minutes, a market's fields."""
    events = collections.defaultdict(list)
    types, spans = collections.Counter(), []
    for m in listed:
        events[m.get('close_time')].append(m)
        types[m.get('strike_type')] += 1
        if m.get('open_time') and m.get('close_time'):
            spans.append((paths.iso_epoch(m['close_time']) - paths.iso_epoch(m['open_time'])) / 60.0)
    per = sorted(len(v) for v in events.values())
    out = {'markets': len(listed), 'events': len(events), 'strike_types': dict(types)}
    if per:
        out['strikes_per_event'] = {'min': per[0], 'median': statistics.median(per), 'max': per[-1]}
    if spans:
        out['minutes_open'] = {'min': round(min(spans), 1), 'median': round(statistics.median(spans), 1), 'max': round(max(spans), 1)}
    if listed:
        out['fields'] = sorted(listed[0])
    return out


def select(listed, spot, counts):
    """The NEAREST strikes of every event to the spot at the first offset: [(market, strike)]. What cannot be used is counted in COUNTS."""
    by_event = collections.defaultdict(list)
    for m in listed:
        if m.get('result') not in ('yes', 'no'):
            counts['no_result'] += 1
            continue
        counts['strike_type:%s' % m.get('strike_type')] += 1
        if m.get('strike_type') not in spotgap.STRIKE_TYPES:
            counts['odd_strike'] += 1
            continue
        strike = outcomes._f(m.get('floor_strike'))
        if not strike or strike <= 0:
            counts['no_strike'] += 1
            continue
        by_event[paths.iso_epoch(m['close_time'])].append((m, strike))
    chosen = []
    for close, ms in sorted(by_event.items()):
        px, age = spot.last_closed(close - WINDOW + OFFSETS[0])
        if px is None or age > spotgap.MAX_SPOT_AGE:
            counts['event_no_spot'] += 1
            continue
        ms.sort(key=lambda x: (abs(math.log(px / x[1])), x[0]['ticker']))
        chosen.extend(ms[:NEAREST])
    return chosen


def rows_of(market, strike, candles, spot, counts):
    """The quote rows of one kept market: dicts of offset, bid, ask, p, the earlier mid and p (None when that quote or spot is missing) and
    whether it ended YES. What cannot be built is counted in COUNTS (per quote: no_quote, crossed, no_spot, no_vol; no_prev: the row is kept
    without the missing-adjustment gap)."""
    close = paths.iso_epoch(market['close_time'])
    yes = market.get('result') == 'yes'
    rows = []
    for off in OFFSETS:
        t = close - WINDOW + off
        bid, ask = marketbase.quote_at(candles, t, MAX_QUOTE_AGE)
        if bid is None or ask is None:
            counts['no_quote'] += 1
            continue
        if bid > ask:
            counts['crossed'] += 1
            continue
        px, age = spot.last_closed(t)
        if px is None or age > spotgap.MAX_SPOT_AGE:
            counts['no_spot'] += 1
            continue
        sg = spot.sigma(t)
        p = spotgap.model_p(px, strike, sg, (close - t + age) / 60.0)
        if p is None:
            counts['no_vol'] += 1
            continue
        mid0 = p0 = None
        b0, a0 = marketbase.quote_at(candles, t - BACK, MAX_QUOTE_AGE)
        px0, age0 = spot.last_closed(t - BACK)
        if b0 is not None and a0 is not None and 0 < b0 <= a0 < 1 and px0 is not None and age0 <= spotgap.MAX_SPOT_AGE:
            p0 = spotgap.model_p(px0, strike, sg, (close - (t - BACK) + age0) / 60.0)
            mid0 = (b0 + a0) / 2.0
        if p0 is None:
            counts['no_prev'] += 1
        counts['empty_bid'] += 1 if bid <= 0 else 0
        counts['empty_ask'] += 1 if ask >= 1 else 0
        rows.append({'off': off, 'bid': bid, 'ask': ask, 'p': p, 'mid0': mid0, 'p0': p0, 'yes': yes, 'age': quote_age(candles, t)})
    return rows


def quote_age(candles, t):
    """Seconds from the end of the last candle at or before T to T, or None without one (the age of the quote quote_at reads)."""
    last = None
    for c in candles:
        if (c.get('end_period_ts') or 0) <= t:
            last = c
        else:
            break
    return None if last is None else t - (last.get('end_period_ts') or 0)


def forecast(r):
    """The missing-adjustment forecast q = mid before + the model's move since, kept inside [0, 1], or None without the earlier quote."""
    if r['p0'] is None:
        return None
    return min(1.0, max(0.0, r['mid0'] + r['p'] - r['p0']))


def gaps(r):
    """{'lvl': (YES gap, NO gap), 'adj': (...)} of a row; adj is absent without the earlier quote."""
    out = {'lvl': (r['p'] - r['ask'], r['bid'] - r['p'])}
    q = forecast(r)
    if q is not None:
        out['adj'] = (q - r['ask'], r['bid'] - q)
    return out


def is_fresh(r):
    return r['age'] is not None and r['age'] <= FRESH


def gap_labels(kind, off, gap, series, fresh=None):
    out = ['%s:%s' % (kind, spotgap.gap_bucket(gap))]
    if gap >= PRIMARY:
        base = '%s>=%+.2f' % (kind, PRIMARY)
        out += [base, '%s|offset:%ds' % (base, off), '%s|coin:%s' % (base, COIN[series])]
        if fresh is not None:
            out.append('%s|quote:%s' % (base, 'fresh' if fresh else 'old'))
    if gap >= 2 * PRIMARY:
        out.append('%s>=%+.2f' % (kind, 2 * PRIMARY))
    return out


class Cell(marketbase.Cell):
    """marketbase's cell with a day counted from DAY_ROWS rows, the rows of each day, and a standard error clustered by close hour."""
    day_min = DAY_ROWS

    def __init__(self):
        super().__init__()
        self.by_hour = collections.defaultdict(lambda: [0, 0.0])

    def add(self, day, cost, won, ticker, hour=None):
        super().add(day, cost, won, ticker)
        h = self.by_hour[hour]
        h[0] += 1
        h[1] += (1.0 if won else 0.0) - cost

    def out(self):
        c = super().out()
        c['rows_by_day'] = {d: v[0] for d, v in sorted(self.by_day.items())}
        g = len(self.by_hour)
        c['hours'] = g
        if g >= 2:
            mean = sum(v[1] for v in self.by_hour.values()) / self.n
            var = sum((v[1] - mean * v[0]) ** 2 for v in self.by_hour.values()) / (self.n * self.n) * g / (g - 1)
            c['se_c'] = round(100 * math.sqrt(var), 1)
        else:
            c['se_c'] = None
        return c


def tabulate(items_by_series, spots):
    """{series: [(day, market, strike, candles), ...]} of the kept markets to the printed report."""
    counts = collections.defaultdict(collections.Counter)
    cells = collections.defaultdict(Cell)
    scores = collections.defaultdict(spotgap.Score)
    cal = collections.defaultdict(lambda: [0, 0.0, 0])
    markets, attempted, used = {}, collections.Counter(), collections.Counter()
    for series, items in items_by_series.items():
        coin = COIN[series]
        markets[series] = len(items)
        for day, m, strike, candles in items:
            hour = paths.iso_epoch(m['close_time'])
            attempted[coin] += len(OFFSETS)
            rows = rows_of(m, strike, candles, spots[series], counts[coin])
            used[coin] += len(rows)
            for r in rows:
                bid, ask, off = r['bid'], r['ask'], r['off']
                g = gaps(r)
                fresh = is_fresh(r)
                age_cut = 'quote:fresh' if fresh else 'quote:old'
                if 0 < ask < 1:
                    for side, cut in marketbase.labels(off, 'yes', ask, series) + [('yes', age_cut)]:
                        cells[(side, cut)].add(day, ask, r['yes'], m['ticker'], hour)
                    for kind, (gy, _gn) in g.items():
                        for lab in gap_labels(kind, off, gy, series, fresh):
                            cells[('yes', lab)].add(day, ask, r['yes'], m['ticker'], hour)
                if 0 < bid < 1:
                    cost = round(1 - bid, 6)
                    for side, cut in marketbase.labels(off, 'no', cost, series) + [('no', age_cut)]:
                        cells[(side, cut)].add(day, cost, not r['yes'], m['ticker'], hour)
                    for kind, (_gy, gn) in g.items():
                        for lab in gap_labels(kind, off, gn, series, fresh):
                            cells[('no', lab)].add(day, cost, not r['yes'], m['ticker'], hour)
                q = forecast(r)
                if 0 < bid <= ask < 1:
                    mid = (bid + ask) / 2.0
                    for name, x in (('model', r['p']), ('adj', q), ('mid', mid)):
                        if x is not None:
                            c = cal[(name, min(int(x * BINS), BINS - 1))]
                            c[0] += 1
                            c[1] += x
                            c[2] += 1 if r['yes'] else 0
                    if q is not None:
                        for key in ('all', 'offset:%ds' % off):
                            scores[key].add(day, r['p'], q, mid, r['yes'])
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
    brier = {}
    for k, v in sorted(scores.items()):
        if v.n:
            o = v.out()
            brier[k] = {'n': o['n'], 'model': o['model'], 'adj': o['model_open'], 'mid': o['mid'], 'diff_model': o['diff'],
                        'diff_adj': o['diff_open'], 'model_better_days': o['model_better_days'], 'adj_better_days': o['model_open_better_days']}
    return {'markets': markets, 'counts': {k: dict(sorted(v.items())) for k, v in sorted(counts.items())},
            'rows': {k: {'attempted': attempted[k], 'used': used[k]} for k in sorted(attempted)},
            'brier': brier, 'calibration': calibration, 'cells': table, 'cells_under_floor': withheld}


def check_rows(out):
    """Stop when a coin lost more than MAX_LOST_SHARE of its quote rows to missing spot or volatility: a table built on holes is not kept.
    A missing or crossed quote is not a hole in the data (a thin strike may have none), so it is only counted."""
    for coin, r in out['rows'].items():
        c = out['counts'].get(coin, {})
        lost = c.get('no_spot', 0) + c.get('no_vol', 0)
        if r['attempted'] and lost > MAX_LOST_SHARE * r['attempted']:
            raise RuntimeError('ladder: %s lost %d of %d quote rows to missing spot or volatility (%s)' % (coin, lost, r['attempted'], c))


def load_spots(t0, t1, days, cache, now, series):
    """{series: Spot} for the coins of SERIES, covering the hour of volatility before the first window and the last window; stops with an
    error when a coin's minutes cannot be fetched or a coin has under MIN_DAY_SPOT_SHARE of a full UTC day's 1440 minutes."""
    a, b = t0 - WINDOW - spotgap.VOL_WINDOW - BACK - 120, t1 + 120
    out = {}
    for s in series:
        rows = paths.spot_minutes(COIN[s], a, b, cache)
        if not rows:
            raise RuntimeError('ladder: the Coinbase minutes for %s could not be fetched' % COIN[s])
        sp = spotgap.Spot(rows)
        for k, lab in enumerate(days):
            d0 = t0 + 86400 * k
            if d0 + 86400 > now:
                continue
            have = sp.count_between(d0, d0 + 86400)
            if have < spotgap.MIN_DAY_SPOT_SHARE * 1440:
                raise RuntimeError('ladder: only %d of 1440 Coinbase minutes for %s on %s: the series has holes' % (have, COIN[s], lab))
        out[s] = sp
    return out


def read(day, days, now, check_coverage, cache):
    """Every settled ladder event that closed in the DAYS UTC days ending with DAY, its nearest strikes and their candles: ({series:
    [(day label, market, strike, candles)]}, spots, meta). Stops with an error rather than return holes: a markets list that fails,
    no series with any market at all, (CHECK_COVERAGE) a full UTC day with under MIN_DAY_SHARE of the EXPECTED_PER_DAY events in a
    series that has events, more kept markets than MAX_CHOSEN, or too many failed candle requests. The error carries the SURVEY."""
    t0, t1, labels_ = marketbase.day_bounds(day, days)
    listed, surveys, per_day = {}, {}, {}
    for series in SERIES:
        got = []
        for m in marketbase.list_settled(series, t0, t1):
            if m.get('ticker') and m.get('close_time') and t0 <= paths.iso_epoch(m['close_time']) < t1:
                got.append(m)
        listed[series] = got
        surveys[series] = survey(got)
        events = [set() for _ in labels_]
        for m in got:
            close = paths.iso_epoch(m['close_time'])
            events[(close - t0) // 86400].add(close)
        per_day[series] = {lab: len(events[k]) for k, lab in enumerate(labels_)}
    present = [s for s in SERIES if listed[s]]
    if not present:
        raise RuntimeError('ladder: no settled ladder market in %s..%s (survey %s)' % (labels_[0], labels_[-1], surveys))
    partial = [lab for k, lab in enumerate(labels_) if t0 + 86400 * (k + 1) > now]
    if check_coverage:
        for series in present:
            for lab in labels_:
                if lab not in partial and per_day[series][lab] < MIN_DAY_SHARE * EXPECTED_PER_DAY:
                    raise RuntimeError('ladder: only %d settled %s events on %s (expected about %d): the list is truncated (survey %s)' % (
                        per_day[series][lab], series, lab, EXPECTED_PER_DAY, surveys[series]))
    spots = load_spots(t0, t1, labels_, cache, now, present)
    chosen, select_counts = {}, {}
    for series in present:
        sc = collections.Counter()
        chosen[series] = select(listed[series], spots[series], sc)
        select_counts[COIN[series]] = dict(sorted(sc.items()))
        surveys[series]['kept_markets'] = len(chosen[series])
    total = sum(len(v) for v in chosen.values())
    if total > MAX_CHOSEN:
        raise RuntimeError('ladder: %d markets kept, more than %d: too many candle requests for one run (survey %s)' % (total, MAX_CHOSEN, surveys))
    got, calls, failed, seen = {}, 0, 0, []
    for series in present:
        items = []
        for m, strike in chosen[series]:
            calls += 1
            c = marketbase.candles_of(m, series, WINDOW, BACK + 60)
            time.sleep(marketbase.PAUSE)
            if c is None:
                failed += 1
                if failed > max(5, MAX_ERROR_SHARE * max(calls, 1)):
                    raise RuntimeError('ladder: %d of %d candle requests failed; stopping' % (failed, calls))
                continue
            seen.append(len(c))
            d = datetime.datetime.fromtimestamp(paths.iso_epoch(m['close_time']), datetime.timezone.utc).strftime('%Y-%m-%d')
            items.append((d, m, strike, c))
        got[series] = items
    meta = {'t0': t0, 't1': t1, 'days': labels_, 'partial_days': partial, 'events_per_day': per_day, 'survey': surveys,
            'select_counts': select_counts, 'candle_requests': calls, 'candle_failures': failed}
    if seen:
        meta['candles_per_kept_market'] = {'median': statistics.median(seen), 'min': min(seen), 'max': max(seen)}
    return got, spots, meta


def report(w, day, days=7, now=None, check_coverage=True, cache=None):
    """The ladder calibration and spot-lag test over every settled hourly ladder event that closed in the DAYS UTC days ending with DAY
    (read stops the run on a failed list, failed candle requests or holes in coverage; check_rows on rows lost to missing spot). W is
    unused (kept for the stage interface): nothing is read from or written to the work folder; the spot minutes are cached in a
    temporary folder (CACHE) of public data."""
    now = time.time() if now is None else now
    got, spots, meta = read(day, days, now, check_coverage, cache or tempfile.mkdtemp(prefix='ladder-'))
    out = tabulate(got, spots)
    check_rows(out)
    out.update({'days': meta['days'], 'partial_days': meta['partial_days'], 'events_per_day': meta['events_per_day'], 'survey': meta['survey'],
                'select_counts': meta['select_counts'], 'candles_per_kept_market': meta.get('candles_per_kept_market'), 'offsets_s': list(OFFSETS), 'back_s': BACK, 'nearest': NEAREST,
                'candle_requests': meta['candle_requests'], 'candle_failures': meta['candle_failures'], 'primary_gap': PRIMARY,
                'note': 'public data (Kalshi, Coinbase); the NEAREST strikes of each hourly event to the spot at the first offset; rows are '
                        'three quotes per market, strikes and coins of one hour move together, so read edge_c against se_c (clustered by '
                        'close hour); edge = win share - price paid, held to settlement, taker spread included; the fee is per contract, so '
                        'a one-contract order pays up to a cent more; Coinbase is a proxy for the index the strikes use'})
    return out
