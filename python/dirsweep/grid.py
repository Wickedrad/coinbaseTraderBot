"""The constants of PREREG-3.md sections 2 and 3. Nothing here is tuned: change one and the pre-registration is void."""
import datetime as dt

import numpy as np

MIN = 60_000
DAY = 86_400_000


def ms(day: str) -> int:
    return int(dt.datetime.strptime(day, '%Y-%m-%d').replace(tzinfo=dt.timezone.utc).timestamp() * 1000)


SEARCH_START = ms('2020-01-01')
SEARCH_END = ms('2026-11-01')        # exclusive: nothing at or after it is read before the FINAL stage
DAY0 = SEARCH_START // DAY
ND = (SEARCH_END - SEARCH_START) // DAY
STEP = {'BTC': 0.01, 'ETH': 0.01}    # research/oracle_heat/latest/live_meta.json price_step
FLAT = 1.5                           # steps: a move under 1.5 steps is flat (PREREG.md)

K = (1, 2, 3, 5, 10, 15, 30, 60)
TZ = (0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0)
TA = (0.0, 0.05, 0.10, 0.15, 0.20, 0.30, 0.40)
TR = (0.75, 1.0, 1.25, 1.5, 2.0, 3.0)
PH_NAMES = ('all', 'q0', 'q01', 'q014', 'mid')
PHASES = (tuple(range(15)), (0,), (0, 1), (14, 0, 1), tuple(range(3, 12)))
HORIZONS = (5, 15, 30, 60)
W = 1440                             # trailing window of sigma and mean volume
MAX_GAP_W = 72                       # gap minutes allowed in that window
EDGE = 60                            # no gap minute within 60 minutes before, nor after, a scored row
MIN_ROW = W + max(K)                 # first row a feature can be read at

NZ, NA, NR, NP = len(TZ) + 1, len(TA) + 1, len(TR) + 1, len(PHASES)
PER_K = NZ * NA * NR * NP            # 2,520 cells per lookback
N_CELLS = len(K) * PER_K             # 20,160 cells; a rule is a cell and a side
N_RULES = 2 * N_CELLS                # 40,320


def cell(ik, iz, ia, ir, ip) -> int:
    return ik * PER_K + ((iz * NA + ia) * NR + ir) * NP + ip


def unpack(c: int) -> tuple:
    ik, r = divmod(int(c), PER_K)
    r, ip = divmod(r, NP)
    r, ir = divmod(r, NR)
    iz, ia = divmod(r, NA)
    return ik, iz, ia, ir, ip


def describe(rid: int) -> dict:
    """rule id = cell * 2 + side (0 fade, 1 follow) -> readable parameters."""
    c, side = divmod(int(rid), 2)
    ik, iz, ia, ir, ip = unpack(c)
    return {'side': ('fade', 'follow')[side], 'k': K[ik], 'z': 0.0 if iz == 0 else TZ[iz - 1], 'a': None if ia == 0 else TA[ia - 1],
            'r': 0.0 if ir == 0 else TR[ir - 1], 'phase': PH_NAMES[ip]}


def n_active(c) -> np.ndarray:
    """How many of z, a, r, phase are not 'off' (the tie-break of PREREG-3.md section 4)."""
    c = np.atleast_1d(np.asarray(c))
    r = c % PER_K
    ip = r % NP
    r = r // NP
    ir = r % NR
    r = r // NR
    ia = r % NA
    iz = r // NA
    return (iz > 0).astype(int) + (ia > 0) + (ir > 0) + (ip > 0)


def block_days() -> list:
    """The 14 blocks of PREREG-3.md section 2 as [lo_day, hi_day) offsets from SEARCH_START."""
    edges = []
    for y in range(2020, 2027):
        for mo in (1, 7):
            edges.append(ms(f'{y}-{mo:02d}-01'))
    edges.append(SEARCH_END)
    edges = [e for e in edges if e <= SEARCH_END]
    # halves 2020H1 .. 2026H1 end at 2026-07-01; the 14th block runs 2026-07-01 .. 2026-10-31
    cut = [e for e in edges if e <= ms('2026-07-01')]
    cut.append(SEARCH_END)
    return [((a - SEARCH_START) // DAY, (b - SEARCH_START) // DAY) for a, b in zip(cut[:-1], cut[1:])]


def period_days() -> dict:
    """Oracle periods of PREREG-3.md section 2: A = 2020..2024, B = 2025, C = 2026-01-01 .. 2026-10-31."""
    f = lambda a, b: ((ms(a) - SEARCH_START) // DAY, (ms(b) - SEARCH_START) // DAY)
    return {'A': f('2020-01-01', '2025-01-01'), 'B': f('2025-01-01', '2026-01-01'), 'C': f('2026-01-01', '2026-11-01')}
