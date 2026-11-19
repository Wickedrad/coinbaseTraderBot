"""Which days the loop may read (PREREG.md section 4). The league tables never saw a 2026 minute (oracle.heat.HEAT_END) and
this loop never refits them. DEV is open to everything, VAL only to the one-bit look, FINAL only after a verified freeze.

    scope('dev')    2026-01-01 .. 2026-06-30
    scope('val')    2026-07-01 .. VAL_END (the last full month on file, set in Amendment 1); needs HEATLOOP_VAL=1
    scope('final')  after the freeze; needs a freeze file whose hashes verify (written by the freeze stage, not here)

A reader asks `window(lo_ms, hi_ms, scope)` before it uses a minute; a request outside the scope raises, it is never clipped.
"""
import datetime as dt
import os

MIN = 60_000
DAY = 86_400_000


def ms(day: str) -> int:
    return int(dt.datetime.strptime(day, '%Y-%m-%d').replace(tzinfo=dt.timezone.utc).timestamp() * 1000)


HEAT_END = ms('2026-01-01')       # the tables stop here (python/oracle/heat.py)
DEV = (ms('2026-01-01'), ms('2026-07-01'))      # [lo, hi) the optimizer sees every number
VAL_START = ms('2026-07-01')
VAL_END = None                    # exclusive end of the last full calendar month on file; Amendment 1 sets it before round 0
WARMUP_START = ms('2025-06-01')   # readings need a warm-up; these minutes are table-era days and score nothing


class OutOfScope(Exception):
    pass


def scope_range(name: str, val_end=None, final=None) -> tuple:
    """(lo, hi) in ms, hi exclusive, of the days scope `name` may SCORE."""
    if name == 'dev':
        return DEV
    if name == 'val':
        ve = VAL_END if val_end is None else val_end
        if ve is None:
            raise OutOfScope('VAL_END is not set (Amendment 1 sets it before round 0)')
        if os.environ.get('HEATLOOP_VAL') != '1':
            raise OutOfScope('VAL is read only by the one-bit look (HEATLOOP_VAL=1)')
        return (VAL_START, ve)
    if name == 'final':
        if final is None:
            raise OutOfScope('FINAL needs a verified freeze')
        return final
    raise OutOfScope(f'unknown scope {name!r}')


def window(lo: int, hi: int, name: str, val_end=None, final=None) -> tuple:
    """Check that [lo, hi) lies inside scope `name`'s scoring range (readings may also use WARMUP_START..lo as history)."""
    a, b = scope_range(name, val_end, final)
    if lo >= hi:
        raise OutOfScope(f'empty window {lo}..{hi}')
    if lo < a or hi > b:
        raise OutOfScope(f'window {lo}..{hi} is outside scope {name} {a}..{b}')
    return lo, hi


def history_limit(name: str, val_end=None, final=None) -> int:
    """The last minute (exclusive) a reader may LOAD for scope `name`: nothing later than the scope's end is ever read,
    so a DEV run cannot see a VAL minute even as history for a later bar."""
    return scope_range(name, val_end, final)[1]
