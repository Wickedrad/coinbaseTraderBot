"""The curve reader that runs beside the bot (thread "Test weighted heat maps on live Kalshi", Nov 11 2026).

Once a minute, for each coin: bring the coin's Binance spot 1-minute bars up to date, ask the oracle engine
(python/oracle/heat_live.py, the code that built the heat tables) which event keys fire at the last closed minute,
join them with the traded pack and write the calls file the bot reads (HeatCallsFile in bot/heat/types.ts).
The bot never runs this code and this code never talks to Kalshi: the file is the whole contract.

Run from the python/ folder: python3 -m heat_reader [--once]. Settings: docs/HEAT_READER.md. NEVER DOGE.
"""
import os

# One thread per numeric library. The engine works on 3,000 bars a timeframe, so more threads buy no time, and each
# extra thread of OpenBLAS keeps its own buffers: on a small server that is memory the bot needs. Set before numpy
# is imported anywhere in this package; a value the operator set is left alone.
for _name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ.setdefault(_name, '1')

MIN = 60_000
DAY = 86_400_000
