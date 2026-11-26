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

### Part 3, amendment 1 (written Nov 25 9:29 PM EST / 2026-11-26T02:29Z, after the first read)

- Time stamp. Part 3 was committed at Nov 25 9:27 PM EST (Nov 26 02:27 UTC) in commit 84eb611, before the read. The
  "9:35 PM EST / 02:35 UTC" in its heading was my estimate and was a few minutes ahead; the trigger file's time was too.
- First read: run 45742546147, read at Nov 26 02:27 UTC. 6,446 active programs (all of the liquidity type, $639,268 in
  period rewards), 1,827 upcoming ($163,310), 559 schedules. Rows on a BTC, ETH, SOL or XRP series: 0 active,
  0 upcoming, 0 schedules. VERDICT by the first closing line: CLOSED, no crypto 15-minute or hourly market is in a
  liquidity program.
- A closing line that was wrong as written and was not used: "the smallest Target Size is more than the pool can post".
  The Target Size is the depth the whole side of the book must reach for a snapshot to count, not what one account
  must post. An account's share is its own size over the qualifying size.
- Added for a second read, as information only and not part of the test: a wider scan (any series with a crypto word
  anywhere in its ticker, or a crypto schedule category), the schedules by category, and the best-case dollars the same
  pool could collect on any market's program (share = size / target, before any fill loss). It cannot change the
  verdict above, which is about the contracts the bot trades.

### Part 3, amendment 2 (written Nov 25 9:40 PM EST / 2026-11-26T02:40Z, after the second read)

- Second read (information only): run 45742720230, read at Nov 26 02:29 UTC. Schedules by category: Financials 165,
  Economics 99, Entertainment 84, Elections 73, Politics 55, Sports 38, Science and Technology 37, Climate and
  Weather 8; none is Crypto. The wide ticker scan matched three series, all false matches on letters inside other
  words (KXHEGSETHIMPEACH, KXIAETHANOL, KXRPRESPRIMARY). Every program's target size is 1,000 contracts. Reward per
  market per day: least $3.23, median $14.29, most $142.86. Best case for 200 contracts a side (share 0.2) on any
  market: $28.57 a day, $1.19 an hour, before any fill loss (KXONIONACT); next about $0.84 an hour (KXRT).
- The verdict is unchanged: CLOSED for the contracts the bot trades. The non-crypto figures are context, not a proposal.

## Part 1: the one test on the lane's own calls (written Nov 25 2026, 9:40 PM EST / Nov 26 02:40 UTC, before any read)

Question (Steven, Nov 11): can the curves "detect direction, sustaining for atleast 1 minute or long enough for an
exit to take place in profit", on the Kalshi contract? Plan-v4 job J06 (approved Nov 14) asked for this and has no run
on record.

The rules below are the ones written on Nov 11 for the same test (`research/heatmap_live/PREREG.md`, section "Score:
the one test"), restated for Kalshi's one-minute history as the project standard does ("one full minute whose lowest
bid stays at or above the level"). Nothing is fitted or tuned in this part.

### The entry and its price (the same rule for the called entry and for every control)

- T0 = the minute boundary of the entry. For a lane trip: the trip's order time (`order_t`, else `entry_t`) rounded
  down to the minute, which is the bar close the call was made on (the lane acts within 45 s of it). For a replayed
  call: the call's bar close.
- Quote at T0 = the close of Kalshi's one-minute candle that ends at T0 (YES bid, YES ask). It must be two-sided
  (0 < bid < ask < 1; an ask of 1c or less on an empty book is not a quote).
- Side cost p: YES costs the YES ask; NO costs 1 minus the YES bid. p must be 10c to 90c (the lane's own band,
  `RISK_MIN_SIDE_PRICE`).
- Contracts C = floor($10 / p), at least 1.
- Level L = the lowest whole-cent price b (at most 99c) with C x b - fee(C, b) >= C x p + fee(C, p) + 1c x C, where
  fee is Kalshi's taker fee, 0.07 x C x P x (1 - P) rounded up to the cent per order (`bot/fees.ts`). If no price
  reaches it, the entry has no window (it stays in the count).
- Profit window = at least one candle that starts at or after T0 and ends no later than the deadline, whose lowest side
  bid is at or above L. Side bid low: YES = the candle's YES bid low; NO = 1 minus its YES ask high. Deadline: 90 s
  before the close of a 15-minute contract (so the last candle that counts ends 2 minutes before the close), 6 minutes
  before the close of an hourly one.
- An entry with no candle ending at T0, or a quote that fails the rules above, is "not scored" and is counted in its
  own line, for the called entry and the controls alike. A minute with no candle between T0 and the deadline cannot
  hold a window; the share of entries with such a gap is printed.
- Window rate = share of scored entries with a profit window.

### Controls, on the same contracts and minutes

- Random side, same minute and contract: the average of the called side and the opposite side at T0. Gap G = called
  rate minus that average, over entries where both sides are scored. This is the gap that decides "direction found",
  as in the Nov 11 rules.
- Same side at a random minute of the same contract: the same side at every minute boundary of the contract's entry
  window (15-minute: 840 to 300 s before close; hourly: 3300 to 600 s), each priced and scored by the rule above; the
  control is the mean over those minutes. This is the comparison named in the audit. It is reported beside G with its
  own error and is NOT the deciding gap, for two reasons known before this read: it measures the timing of the entry
  (it read about +8 points for every contender on Nov 19, because early entries have more minutes left), and it
  cannot see a direction that holds for the whole contract (the same side wins at the other minutes too).
- The usual side: the side this coin and contract type was called most often in the sample, at the same minute. It
  shows whether the calls add anything to always betting one way in a market that drifted. Information.

### Counting, error and the line

- Primary count: one entry per contract, the first that qualifies. Secondary count: every entry.
- Error: bootstrap over time slots (a slot = one contract close time; every coin's entries on contracts closing at
  that time are drawn together), 2,000 draws, fixed seed 20261125.
- "Direction found" = G at least twice its own standard error, on the primary count. That level and the +1c margin
  are the pipeline thread's reading, not Steven's words. So the plain sign is always reported too: "above random by
  any amount" or not.
- If the same-side-random-minute gap passes and G does not, it is reported as timing, not direction. If the primary
  and secondary counts disagree, or parts A and B disagree, that is reported as mixed and the call is Steven's.
  The parts are never pooled.

### Reported beside it, as information, never judged

- Cents per contract after fees, for the called entries and for each control: sold at the side bid close one minute
  after T0 (both fees), and held to settlement (entry fee only; result from Kalshi's own settlement). Turned into
  dollars an hour as: cents per contract x contracts per entry x entries per hour over the hours covered.
- Splits by contract type, coin, side and week; the median minutes to the first window; the share of entries by side.
- For part A only: the same test at the lane's own fill price and size (level from `entry_fill_px` and
  `count_filled`; candles from the first minute boundary at or after the fill), and the lane's realized cents per
  contract from the trips.

### Part A: the lane's own paper entries since Nov 12

- Data: the loss review's trip files on Drive (`derived/loss-review/days/trips-DAY.jsonl`, private), every row of lane
  'heat' with a ticker, a side and a time, for Nov 12 through the last day on Drive when the job runs. Trips the
  builder flagged (`fidelity_flag`) are kept, since the call is what is tested, and their count is printed.
- Prices: Kalshi's public one-minute candles for each traded ticker (`lossreview.paths.market_and_candles`).
- These days were read before for other questions (the loss review, loop 0056). They were never used to build the
  curves (built on 2020 to 2024, checked on 2025), and this test has not been run on them.

### Part B: the curve calls replayed over Aug 1 to Nov 4, 2026

- Calls: the deployed pack (`research/oracle_heat/latest/`: traded_pack.json, pair_pack.json, live_meta.json; their
  sha256 are printed) read by the reader's own code (`python/heat_reader`, `read_coin`, window 3000, the deployed
  filters) at every minute close from Aug 1 00:00 UTC to Nov 4 23:59 UTC on Binance one-minute bars, for BTC and ETH
  (the coins whose 15-minute history is on Drive for these days). Bars before Aug 1 are used only to warm up the
  indicators. The decided call per coin and horizon (15 and 60 minutes) is the lane's own rule (`decideCall` in
  `bot/heat/heatLane.ts`, top 10) on the rows that fire at that bar close.
- The calls table is written and its sha256 printed BEFORE any Kalshi price is joined to it. Making the calls reads
  no Kalshi price.
- Entries: a 15-minute call enters the KX<COIN>15M contract whose close is 300 to 840 s after T0. A 60-minute call
  enters the hourly contract (KX<COIN>D) closing 600 to 3300 s after T0, on the strike whose YES mid at T0 is nearest
  50c among strikes with a two-sided quote. If the hourly history on Drive does not hold the strikes near the money,
  the hourly half is reported as not available and is not replaced by anything else.
- Not replayed (stated, not hidden): the lane's stateful gates (one entry per coin a minute, the open-position cap,
  the re-entry limits, the hour-context setting, the spread-against-loser-cut gate). The primary count (first
  qualifying call per contract) is the closest stateless match to them.
- Prices: the Kalshi one-minute history on Drive (`raw/kalshi-history/kalshi/KX<COIN>15M`, and
  `raw/oracle-history/kalshi/KX<COIN>D` for the hourly half). Known caveat: on the oldest markets an empty ask is
  stored as 1c; the two-sided rule above leaves those minutes unscored.
- Read log: these are the pipeline's HO-1 days. One line is added to
  `/mnt/project-files/registry/edge-pipeline/calendar.md` before the join job starts, and it counts as one read for
  this frozen rule (the deployed pack and the lane's settings). It is not re-read after any change.
- Books on these days were thinner than since Nov 10. The share of entries not scored for a one-sided or missing
  quote is printed, by month.

Run: `python3 -m auditpath.onetest` in `python/` (part A: workflow `.github/workflows/audit-path-onetest.yml`, started
by a push that changes `research/audit_path/RUN-ONETEST`; part B: `.github/workflows/audit-path-replay.yml`, started by
`research/audit_path/RUN-REPLAY`). Jobs print aggregates only; trip rows, call rows and Binance rows stay on Drive.

### Part 1, amendment 1 (written Nov 25 9:55 PM EST / Nov 26 02:55 UTC, BEFORE the first read: how the code reads the rules above)

Two independent critics checked the code against this part; where the text left room, the reading taken is:
- Candle prices are rounded to whole cents for the cost, the band, C and the level.
- "Direction found" also needs G above zero (it matters only if G and its error are both zero).
- The primary count is the first entry per contract whose called side is scored; contracts with no scored entry are
  counted and printed.
- The final word is "mixed" whenever the primary and secondary words differ.
- The same-side-random-minute control includes the entry's own minute; its value is the mean over the scored minutes.
- Sold after one minute: a bid of zero is a sale at 0c (the side is worthless there); a missing candle is "no exit" and
  is left out of that average.
- Hours for dollars an hour = UTC days with at least one entry x 24.
- A split cell with under 10 scored entries is counted but not rated.
- The fill-price variant uses the trip's order time as the fill time (at or before the real fill); information only.
- The candles of the traded tickers are kept on private Drive between runs, not in an Actions cache.

### Part 1, amendment 1a (written Nov 25 10:19 PM EST / Nov 26 03:19 UTC, after a failed run that printed no result)

Part A's first run (run 45745559632) stopped with a division by zero before printing anything: a paper trip can record
a fill of less than one contract, and the lane's realized cents per contract divided by the whole-contract count (0).
No number from the test was printed or seen. The fix reads the recorded count as it is (a trip with no count is left
out of that one figure). The rules above are unchanged, and the rerun is the same first read.

### Part 1, amendment 2 (written Nov 25 10:02 PM EST / Nov 26 03:02 UTC, BEFORE part B's calls are made: how the replay reads the rules above)

Two independent critics checked the replay against part B; where the text left room, the reading taken is:
- A minute close is the close time: 00:00 through 23:59 UTC of each day, 1,440 a day, Aug 1 through Nov 4.
- The firing rows and the decided call come from the lane's real code (parseHeatCalls, readHeatCalls and decideCall in
  `bot/heat/heatLane.ts`, run through `research/audit_path/decideCalls.ts`), with the code's default settings (top 10,
  lag 45 s, a pair against its single is skipped). The server's own bot.env cannot be read from the repo.
- A pair or triple that calls against the single it refines is skipped by the lane. It stays in the table with a flag
  and is not an entry in the join.
- The reader runs with its own pinned wheels (`python/heat_reader/requirements.txt`). Warm-up: about 152 days of bars
  before Aug 1.
- 16 shards (BTC and ETH, eight 12-day blocks) each print the sha256 of their file; the join prints one hash over all
  rows before it opens any Kalshi file.
- Read-log line 11 was added to `/mnt/project-files/registry/edge-pipeline/calendar.md` before the push.

### Part 1, amendment 3 (written Nov 25 10:15 PM EST / Nov 26 03:15 UTC, BEFORE part B's join is run: how the join reads the rules above)

Two independent critics and a re-check went over the join (`python/auditpath/joincalls.py`); where the text left room,
the reading taken is:
- Hours for dollars an hour = UTC days with at least one analysed entry x 24 (as part A); the calendar days and the days
  with an entry are both printed.
- "The hourly history does not hold the strikes near the money" is decided by one number fixed here, before the read:
  the hourly half is available when at least half of the 60-minute calls have a two-sided strike whose YES mid at T0 is
  10c to 90c. The counts are printed either way. When it is not available, the hourly entries leave the printed analysis;
  their own analysis is stored on private Drive and is not read unless Steven asks for it (that would be a second read).
- The day files are named by the close day, so the Nov 5 files are pulled too: the calls of Nov 4 after 23:45 enter
  contracts that close on Nov 5. For the 15-minute folders, raw/oracle-history may supply only the Nov 5 file, and
  only where raw/kalshi-history lacks it; the number of files from each source is printed.
- Strike choice uses whole-cent mids (as amendment 1); a tie goes to the lower strike.
- Every shard row with a skip flag is dropped before the hash; the one hash over all kept rows is printed before any
  Kalshi file is opened.

### Part 1, note after part B's read (written Nov 25 11:05 PM EST / Nov 26 04:05 UTC; changes nothing above)

Part B's join ran once (run 45751841770, job 139681224248, Nov 26 03:56 to 04:00 UTC). It printed the calls hash
first (1b6b61bc..., 143,386 rows, 16 shards) and then every result line. The step then ended with exit code 1: its
last command, `grep -v '^AUDITPATH '`, found no other line, and under `set -o pipefail` that is a failure. So the
next step, which keeps the aggregate JSON on private Drive, was skipped and the runner removed the file. The hourly
half was available (68.7% of the 60-minute calls had a strike with a YES mid of 10c to 90c, line 0.50), so no
hourly-only analysis was held back. The printed lines are the record of the read. The join is not run again: a rerun
would be a second read of HO-1. The tidy-up command is fixed in this commit in the join and part A workflows; neither
starts a run on this change.

## Part 2: the last three minutes of the 15-minute window (written Nov 25 2026, 9:40 PM EST / Nov 26 02:40 UTC, before any read)

Question. The 15-minute contract settles YES when the 60-second average of the index before the close is at or above
the average before the open. In the last minute part of that average is already known. Can a buyer who works out the
odds from it second by second beat the recorded ask after the fee?

Data. The one-second grids on Drive (`models/subminute/grids/grid-YYYY-MM-DD.npz`; BTC, ETH, SOL, XRP; per window and
second the YES bid, ask and sizes; per day and second Kalshi's settlement index `idx`; per window the strike and
Kalshi's own result). Nov 11 to 20 exist. Any later recorded day is built first by the same code
(`python3 -m subminute.grid` on `recordings/md-DAY.jsonl.gz`) in a job that reads no result; a day whose recording is
missing or fails to build is listed and left out.

The odds at second s (720 to 897 of the 900):
- Known part: the index at each second of the final 60 (seconds 840 to 899) that is already past, and the latest
  index x at s.
- The rest is a random walk from x with no drift and a one-second step size sigma = the standard deviation of the
  one-second index changes over the previous 600 seconds (at least 300 valid seconds, else no trade at s).
- The final average is then normal: mean = (sum of the known seconds + x times the seconds still to come) / 60;
  variance = sigma squared times the sum over pairs of the seconds still to come of the smaller of their two distances
  from s, divided by 3,600. P(YES) = the normal probability that the average is at or above the strike.
- Check on Nov 11 to 18 only, printed: how often "average of seconds 840 to 899 at or above the strike" matches
  Kalshi's result. If it matches under 97% of windows the job stops and reports that instead of trading on a wrong
  rule.

The trade:
- For each side: cost p (YES = ask, NO = 1 minus bid) from the book one second after s, contracts = the smaller of
  floor($20 / p) and the size shown at that price (at least 1, else no trade), fee = the taker fee on that order.
  Edge = that side's probability minus p minus the fee per contract.
- Buy the side with the larger edge at the first second where it is at least the margin m, at most one trade per
  window, held to settlement, paid by Kalshi's own result. Net = payoff minus cost minus fee.
- Skipped: a second whose book has not changed for 120 s (the lesson of round 5a; `subminute.ladder_arb.ages`), a
  one-sided or crossed book, a window with no strike, index or result.

Hold-out:
- Margin m is chosen on Nov 11 to 18 from 0, 1, 2, 3, 5, 8 and 12 cents: the one with the most net dollars among those
  with at least 100 fills (if none has 100, the one with the most fills). One m for all coins.
- It is scored once on Nov 19 through the last built day. No re-tuning on those days. Those days were read before for
  other ideas, never for this one.

Twins on the scoring days, same windows and seconds as the fills: a coin-flip side (mean of 20 seeds), and the
favourite (the side costing more than 50c). They show what trading at those moments earns without the odds.

Error: bootstrap over time slots (the four coins' windows closing at one time are drawn together), 2,000 draws, seed
20261125; plausible range = mean plus or minus 1.96 standard errors.

Pass line (the audit thread's own, as told to Steven): net cents per contract after fees with its whole plausible
range above zero, on at least 200 fills on the scoring days, and worth at least $1 an hour at these orders (net
dollars on the scoring days / the hours those days cover). Under 200 fills the result is "too thin to decide" and the
fill count is reported. A pass on Nov 19 and 20 alone is preliminary. A pass is a finding for Steven; trading it would
need his exceptions (decision 4 of the audit) and is not part of this read.

Reported as information: fills and net by coin, by day, by seconds left (180 to 121, 120 to 61, 60 to 0) and by
entry price band; the same with the book taken at s (no delay) and three seconds after s; dollars an hour at $10.

Run: `python3 -m auditpath.last3` in `python/`, workflow `.github/workflows/audit-path-last3.yml`, started by a push
that changes `research/audit_path/RUN-LAST3`. Aggregates only.

### Part 2, amendment 1 (written Nov 25 9:56 PM EST / Nov 26 02:56 UTC, BEFORE the first read: how the code reads the rules above)

Two independent critics checked the code against this part (the odds matched a brute-force calculation); where the
text left room, the reading taken is:
- Sigma is the sample standard deviation of the valid one-second index changes in the 600 seconds ending at s. The
  known seconds and the latest index use the last value carried forward within the day.
- "Unchanged for 120 s" means an age of 120 seconds or more at the book that is traded (one second after s).
- A locked book (bid equal to ask) is allowed; crossed means bid above ask.
- Net cents per contract is contract-weighted (net dollars / contracts). The bootstrap draws all time slots of the
  scored days, including slots with no fill.
- A window whose 15 minutes cross midnight UTC is skipped (its index is in the next day's file); the count is printed.
- The favourite twin takes the dearer side, YES on an exact tie. A twin side with no size shown is dropped.
- Dollars an hour = net dollars / (scored grid days x 24). The $10 figure re-runs the rule with a $10 order.
- A split cell with under 5 fills prints its count only.
- The command "choose" refuses any day outside Nov 11 to 18; "score" refuses any day at or before Nov 18 and reads the
  margin only from the committed file research/audit_path/FREEZE-LAST3.json.
- Order of the jobs: "choose" runs on the grids that exist. The grids of Nov 21 to 25 are built by a job that prints no
  price and no result. "score" runs once, after those builds end, on Nov 19 through the last day that built.
