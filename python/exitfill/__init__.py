"""Resting-exit fill probe for the heat lane (research only; nothing here touches the bot or the heat curves).

Question: the heat lane sells with a reduce-only IOC at the bid minus two ticks, so both legs pay the taker fee. If a
resting sell had been placed at the same moment instead, would it have filled, how fast, at what price, and what
would the fallback IOC have cost? The answer is measured on the public YES books of the heat shadow capture
(top 3 levels about every 10 s) joined to the paper exits. The rules below are frozen before the first run; see
README.md. Only aggregates leave the runner.
"""

# Every read of a capture day must start at or after this instant (Steven's rule: nothing before Nov 10 03:44 UTC).
FLOOR_ISO = '2026-11-10T03:44:00Z'
HORIZONS_S = (30, 60, 120)          # how long a resting order is left before the fallback IOC
PLACEMENT_SLACK_MS = 1000           # a resting order is assumed live this long after the decision (a slack, NOT a measured latency)
GAP_MS = 25000                      # a book sample older than this, or a hole longer than this, drops the event-horizon
NEAR_CLOSE_MS = 5000                # drop when the horizon ends within this of the contract close
FLOOR_TICKS = 2                     # the bot's IOC limit is the bid minus this many ticks (planRatchet)
UNIT = 10000                        # prices are integers in 1e-4 dollars
VARIANTS = ('JOIN_ASK', 'INSIDE', 'BID_PLUS_1C')
RULES = ('strict', 'touch')         # book-implied stricter / looser fill evidence
MAKER_MULTS = (0.0, 1.0)            # published maker multiplier on these series is 0; 1 is the stress line
T0_SHIFTS_MS = (-5000, -2000, 0, 2000, 5000)   # clock-offset sensitivity (primary cell only)
OTHER_T0_SHIFTS_MS = (-2000, -1000, 0)         # closed_utc is a truncated record time
PRIMARY = ('ratchet', 'INSIDE', 60, 'strict')  # the one headline cell, declared before the first run
BOOT_N = 2000
BOOT_SEED = 20261112
BLOCK_MS = 900000                   # cluster blocks for the bootstrap: 15-minute clock blocks
