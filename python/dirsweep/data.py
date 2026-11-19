"""Loading the SEARCH history (PREREG-3.md section 2). Nothing at or after 2026-11-01 is ever read here: the final stage fetches its own days."""
import numpy as np

from dirsweep import grid as G

WARM_DAYS = 2          # bars of 2019-12-30 and -31 are read only so that the first scored day (2020-01-01) has its 1,440-minute window; no row before 2020-01-01 is scored


def guard(m: dict) -> dict:
    """The grid must end at or before the end of the SEARCH window (the pre-registration's own limit) and start on a UTC midnight."""
    end = m['t0'] + m['n'] * G.MIN
    if end > G.SEARCH_END:
        raise AssertionError(f'a minute at or after {G.SEARCH_END} is in the grid (ends {end})')
    if m['t0'] % G.DAY:
        raise AssertionError('the grid does not start on a UTC midnight')
    return m


def load(csv: str, twin: int = 0) -> dict:
    """The 1-minute grid of one coin for the SEARCH window plus its warm-up days; a twin (1 to 3) is the no-signal copy of the same bars."""
    from heatloop import events
    from oracle import heat, heat_live
    df = events.read_bars(csv, G.SEARCH_START - WARM_DAYS * G.DAY, G.SEARCH_END)
    m = guard(heat_live.grid(df, end_ms=G.SEARCH_END))
    if m.get('tb') is None:
        raise ValueError('the file has no taker-buy volume (tb)')
    if twin:
        m = guard(heat.make_twin(m, int(twin)))
    return m


def info(m: dict) -> dict:
    day_off = m['t0'] // G.DAY - G.DAY0
    lo = max(0, -day_off) * 1440
    gaps = int(np.asarray(m['gap'])[lo:].sum())
    return {'first_day': int(day_off), 'rows': int(m['n']), 'gap_minutes': gaps, 'gap_share': round(gaps / max(1, m['n'] - lo), 6),
            'last_open_ms': int(m['t0'] + (m['n'] - 1) * G.MIN)}
