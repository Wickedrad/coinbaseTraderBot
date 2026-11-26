# Audit path: three reads on recorded days (pre-registration)

Owner's word: Steven chose "Run all three, pause tuning" on Nov 25 2026, 9:19 PM EST (Nov 26 02:19 UTC).
Source of the plan: the audit "Bot audit against the $4.50 an hour goal" (sections "The path forward" and
"Decisions needed from you"). Research only: no order, no bot change, paper only, recorded days and public pages only,
nothing waits for a future day. DOGE is excluded. The repo is public, so jobs print aggregates and public data only.

Each part below is committed before its job first opens the data it reads. A part is not edited after its first read;
anything learned later goes into a dated "Amendment" block under it, with the reason.

Whose lines these are. Step 1's pass level (the gap over random at least twice its own standard error) and its +1c
margin are the edge-pipeline thread's reading of Steven's Nov 11 standard, not his words; if he says "any amount above
random", that is used. The lines of steps 2 and 3 are the audit thread's own. He was told he can ask for the numbers
with no line at all.

## Part 3: Kalshi's live reward programs (written Nov 25 2026, 9:35 PM EST / Nov 26 02:35 UTC, before the first read)

Question. Do Kalshi's reward programs pay resting orders on the crypto contracts enough to matter for a $200 pool?

Data. One read of the public API from a GitHub runner, no account:
`GET /trade-api/v2/incentive_programs` (status active, and upcoming) and `GET /trade-api/v2/incentive_schedules`,
on api.elections.kalshi.com with external-api.kalshi.com as the fallback. Program rules as read on Nov 25 2026 from
help.kalshi.com article 13823851 (Liquidity Incentive Program): one book snapshot a second; a snapshot counts only when
resting size reaches the Target Size on both the yes and the no side; an order that helps reach the Target Size scores
size x discount factor ^ ticks below the Reference Price; a side's scores are normalized to shares; reward = share of
the period score x period reward x share of snapshots that counted; a market's program pays nothing under $1.00.

What is reported. Counts and dollars of active programs by type; the series with the largest rewards (context); and
every row for the series of BTC, ETH, SOL and XRP (15-minute, hourly and daily ladders, and any other crypto series):
type, reward per period and per day in dollars, period length, target size, discount factor, cap per account, dates.
The same for the schedules.

The test, fixed now.
- Size the pool can post: two-sided resting orders cost about $1 a contract pair near 50c, so $200 posts at most
  200 contracts on each side of one market, or 50 on each side of four coins at once.
- Best-case share of a market's reward for size s on both sides = min(1, s / Target Size). It is a ceiling: it assumes
  the orders sit at the Reference Price for the whole period and that the rest of the book just reaches the target.
- Reward ceiling = that share x the period reward, counted as zero where it is under $1.00 for a market's program.
- Cost: what resting orders lose when they fill, 1.7c to 2.9c a filled contract on the days measured in the edge atlas
  rounds 2 to 4 (ROUND-EA2.md, ROUND-EA4.md). The fill rate is not known from this read.
- CLOSED if no crypto 15-minute or hourly market is in a liquidity program (active, upcoming or scheduled), or if the
  smallest Target Size is more than the pool can post on both sides (more than 200 contracts).
- CLOSED if the reward ceiling summed over all crypto markets is under $1 an hour ($24 a day) before any fill loss.
- OPEN (worth a costed second look, not a pass) if the ceiling is $1 an hour or more. Then the next read prices the
  fill loss and the real share from the recorded one-second books, and only that read can pass (at least $1 an hour
  after the fill loss).

Run: `python3 -m auditpath.rewards` in `python/`, workflow `.github/workflows/audit-path-rewards.yml`, started by a
push that changes `research/audit_path/RUN-REWARDS`.

## Part 1: the one test on the lane's own calls (to be written and committed before its first read)

## Part 2: the last three minutes of the 15-minute window (to be written and committed before its first read)
