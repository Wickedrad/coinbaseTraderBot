"""Loss anatomy: where the paper heat lane's money goes, cut seven cheap ways over every scored trip in the work folder. RESEARCH ONLY.

No model tokens and no candle fetch: it reads only the nightly trip files (W/days/trips-DAY.jsonl) and prints aggregates, so the
public log learns nothing a per-trade file would. What keeps one trade's result out of the log:
  - a cell is printed only with MIN_CELL or more trips; smaller cells are only counted in `suppressed_trips`, and when those leave
    fewer than MIN_CELL trips unprinted the smallest printed cell is withheld too (all minus the printed cells is never a handful);
  - the resolved groups (win_pct, px_c, edge_c; hold, net_h) print only with MIN_CELL resolved trips, and the dollar group only
    when the unresolved rest of the cell is empty or MIN_CELL strong (net minus net_h would be the rest's result);
  - a day with fewer than MIN_CELL scored trips is left out of every number, so two runs' lines differ by whole days;
  - every dollar sum is printed on a $5 grid, so the difference of two printed numbers (two cells of two cuts that differ by one
    trade, or two runs) names a trade's result only to within the grid, about the size of the trades themselves. The counts are exact,
    so the presence of such a trade can be inferred; its dollars cannot, beyond that bound;
  - no cut is nested in another (price and side are separate cuts, not a price-by-side table), and the stage has no input that
    moves a cell's edges.
It decides nothing and registers nothing: it shows which cheap lever (price, side, exit rule, hold
time, entry taker or maker, call age, coin and kind) carries the loss, and on how many days each cell was negative, so a lever that
only one day produced is visible as that.

What each number means (all in dollars, per cell):
  net      the trips' own P&L after fees (the logged result, or the fills' when none was logged)
  fees     entry plus exit fees paid
  pre      net + fees: what the trips made before any fee
  fee_pct  fees as a share of the stake filled
  win_pct  share of the trips whose side settled a winner, among trips whose market resolved
  px_c     the mean entry price of those same trips, in cents
  edge_c   win_pct minus px_c in cents: the settlement edge of the entries before fees and before any exit
  hold     the P&L the same trips would have had held to settlement (count * (payout - entry price) - entry fee), on resolved trips
  net_h    the actual net of those same trips, so hold - net_h is what the exits gave away (negative: the exits did better than holding)
  neg_days "days with a negative cell net / days the cell had at least DAY_MIN trips"
"""
import collections
import math
import statistics

MIN_CELL = 10      # a cell with fewer trips is not printed; a day with fewer scored trips is left out of everything
DAY_MIN = 3        # a day counts toward neg_days with at least this many trips in the cell
GRID = 5           # every dollar sum is printed rounded to a multiple of this

PX_EDGES = (0.20, 0.35, 0.50, 0.65, 0.80)
HOLD_EDGES = (30, 120, 300, 900)         # seconds from entry to close
AGE_EDGES = (5, 15, 30)                  # seconds from the bar close to the entry


def _bucket(x, edges, unit=''):
    if x is None:
        return 'unknown'
    lo = None
    for e in edges:
        if x < e:
            return ('<%s%s' % (e, unit)) if lo is None else ('%s-%s%s' % (lo, e, unit))
        lo = e
    return '>=%s%s' % (edges[-1], unit)


def _publish(cells):
    """(the cells to print, the trips left unprinted): cells under MIN_CELL are not printed; if the unprinted trips would then be
    fewer than MIN_CELL (but not none), the smallest printed cell goes with them."""
    shown = {k: c for k, c in cells.items() if c.n >= MIN_CELL}
    hidden = sum(c.n for c in cells.values() if c.n < MIN_CELL)
    if 0 < hidden < MIN_CELL and shown:
        hidden += shown.pop(min(shown, key=lambda k: shown[k].n)).n
    return shown, hidden


def _d(x):
    """A dollar sum on the GRID (round half up), as a number."""
    return int(math.floor(x / GRID + 0.5)) * GRID


def _num(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def view(r):
    """The fields a cell needs, from one trip row (None where the row does not say)."""
    net, fees = _num(r.get('pnl')), _num(r.get('fees'))
    if net is None:
        return None
    fees = fees or 0.0
    px, cnt, fee_in = _num(r.get('entry_fill_px')), _num(r.get('count_filled')), _num(r.get('entry_fee')) or 0.0
    win = r.get('side_settles_win')
    win = win if isinstance(win, bool) else None
    hold = None
    if win is not None and px is not None and cnt is not None and cnt > 0:
        hold = cnt * ((1.0 if win else 0.0) - px) - fee_in
    return {'net': net, 'fees': fees, 'stake': _num(r.get('stake_filled')) or 0.0, 'px': px, 'win': win, 'hold': hold,
            'exit': r.get('exit_event') or 'unknown', 'side': r.get('side') or 'unknown', 'taker': r.get('entry_taker'),
            'kind': r.get('kind') or 'unknown', 'coin': r.get('coin') or 'unknown', 'hold_s': _num(r.get('hold_s')),
            'age': _num(r.get('call_age_s'))}


def labels(v):
    """The label of this trip in each cut."""
    px_b = _bucket(v['px'], PX_EDGES)
    return {
        'exit': v['exit'],
        'side': v['side'],
        'px': px_b,
        'kind_coin': '%s:%s' % (v['kind'], v['coin']),
        'hold_s': _bucket(v['hold_s'], HOLD_EDGES, 's'),
        'entry': 'unknown' if v['taker'] is None else ('taker' if v['taker'] else 'maker'),
        'call_age_s': _bucket(v['age'], AGE_EDGES, 's'),
    }


CUTS = ('exit', 'side', 'px', 'kind_coin', 'hold_s', 'entry', 'call_age_s')


class Cell:
    def __init__(self):
        self.n = 0
        self.net = self.fees = self.stake = 0.0
        self.res = self.wins = 0
        self.px_res = 0.0
        self.n_hold = 0
        self.hold = self.net_h = 0.0
        self.by_day = collections.defaultdict(lambda: [0, 0.0])

    def add(self, day, v):
        self.n += 1
        self.net += v['net']
        self.fees += v['fees']
        self.stake += v['stake']
        d = self.by_day[day]
        d[0] += 1
        d[1] += v['net']
        if v['win'] is not None and v['px'] is not None:
            self.res += 1
            self.wins += 1 if v['win'] else 0
            self.px_res += v['px']
        if v['hold'] is not None:
            self.n_hold += 1
            self.hold += v['hold']
            self.net_h += v['net']

    def out(self):
        c = {'n': self.n, 'net': _d(self.net), 'fees': _d(self.fees), 'pre': _d(self.net + self.fees)}
        if self.stake > 0:
            c['fee_pct'] = round(100.0 * self.fees / self.stake, 1)
        # The resolved groups print only with MIN_CELL trips behind them, and (for the dollar group) with the unresolved rest of the
        # cell either empty or MIN_CELL strong: net minus net_h would otherwise be the rest's result.
        if self.res >= MIN_CELL:
            win, px = self.wins / self.res, self.px_res / self.res
            c.update({'n_res': self.res, 'win_pct': round(100 * win, 1), 'px_c': round(100 * px, 1), 'edge_c': round(100 * (win - px), 1)})
        rest = self.n - self.n_hold
        if self.n_hold >= MIN_CELL and (rest == 0 or rest >= MIN_CELL):
            c.update({'n_hold': self.n_hold, 'hold': _d(self.hold), 'net_h': _d(self.net_h)})
        days = [d for d in self.by_day.values() if d[0] >= DAY_MIN]
        c['neg_days'] = '%d/%d' % (sum(1 for d in days if d[1] < 0), len(days))
        return c


def report(w):
    """The aggregate report over every scored trip of every day in W (the fidelity-flagged and unscored trips stay out). A day with
    fewer than MIN_CELL scored trips is left out of every number, so two lines of two runs differ by whole days of MIN_CELL trips or
    more (the logs are public and kept)."""
    from . import daily
    days = daily.load_days(w, scoring=True)
    total = Cell()
    cuts = {name: collections.defaultdict(Cell) for name in CUTS}
    per_day, kept, short = [], 0, 0
    for day in sorted(days):
        rows = [v for v in (view(r) for r in days[day]) if v is not None]
        if not rows:
            continue
        if len(rows) < MIN_CELL:
            short += 1
            continue
        kept += len(rows)
        dc = Cell()
        for v in rows:
            dc.add(day, v)
            total.add(day, v)
            for name, lab in labels(v).items():
                cuts[name][lab].add(day, v)
        per_day.append({'day': day, 'n': dc.n, 'net': _d(dc.net), 'fees': _d(dc.fees), 'pre': _d(dc.net + dc.fees)})
    out_cuts, suppressed = {}, {}
    for name in CUTS:
        shown, hidden = _publish(cuts[name])
        out_cuts[name] = {lab: c.out() for lab, c in sorted(shown.items())}
        suppressed[name] = hidden
    nets = [d['net'] for d in per_day]
    return {'days_used': len(per_day), 'days_short': short, 'trips': kept, 'floor': MIN_CELL, 'grid': GRID,
            'all': total.out() if total.n else {}, 'per_day': per_day,
            'day_net_median': statistics.median(nets) if nets else None,
            'cuts': out_cuts, 'suppressed_trips': suppressed,
            'note': 'aggregates only; dollar sums on a $%d grid; a cell under the floor is withheld; hold = same trips held to settlement' % GRID}
