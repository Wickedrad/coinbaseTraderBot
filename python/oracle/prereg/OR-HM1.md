# OR-HM1: heat strips and confluence matrix on coin price (design, written before any result)

Written 2026-11-11 ~04:00 UTC (Nov 10 11:00 PM EST). Thread "Find $5 trade setups with a perfect-hindsight oracle".
Steven's spec (Nov 11 03:06 / 03:22 UTC): a weighted linear heat map per TA reading (how often x how big a move within
5/15/30/60 minutes), the full TA-Lib vocabulary with candlestick patterns and a few parameter settings, a pairwise (and
triple) matrix with BTC.D and USDT.D moves as parameters. Exits he wants later: sell at first profit after fees, cut
losers early, settle only in profit. NEVER DOGE. Never compared to paper. Nothing at or after DEV_END (2026-08-01) is
loaded: HO-1 (Aug 1 - Nov 4) and the lockbox stay closed. This is a MAP, not a validated rule; hot spots go on to be
scored on real Kalshi prices and fees under the edge-iteration pipeline's bars.

## Data
Binance spot 1-minute bars (raw/perp-ta-history/<A>/binance-1m/<A>/1m.csv on Drive) for BTC, ETH, SOL, XRP from
2020-01-01 (SOL from its listing) to 2026-07-31 23:00 UTC. BTC.D and USDT.D: TradingView daily closes in
research/btcd_fractal/data (a day's change is known only after that UTC day closes). Gaps are forward-filled for the
indicators; a minute whose own bar or any of the next 60 is a gap is never an event.

## Readings (python/oracle/heat.py READINGS; computed on 1m, 5m, 15m and 1h bars, known at the bar's close)
About 44 indicator readings per timeframe with a few parameter settings (RSI 2/7/14/21, Stochastic and its cross,
StochRSI, Williams %R, CCI, MFI, ADX x DI, Aroon, MACD 12/26/9 and 5/35/5, ROC z, CMO, Ultimate, BOP, TRIX, Bollinger
20/2 and 20/2.5 and width, close vs EMA 9/21/50/200, EMA 9/21 and 50/200 crosses, SAR, KAMA, T3, Donchian 20, Ichimoku
cloud, rolling-VWAP distance, NATR regime, volume surge, taker-buy share, OBV divergence, ADOSC, regression slope,
z-score, HT trend mode, runs of up/down bars, bar size in ATR) plus all 61 TA-Lib candlestick patterns (bull / bear).
Context: BTC.D and USDT.D previous-day change (down / flat / up at 0.5%) and 5-day change, and the UTC 4-hour block.
Each reading has a few levels. An EVENT is the first bar close at which a level holds (a pattern: every bar it fires).

## What is measured per (coin, reading level, horizon h in 5/15/30/60)
From the entry close of each event: the move to h (bps), the best move up and down within h, and Steven's bracket:
did price touch +X before -X within h (X = 10, 25, 50 bps; same-minute ties count as losses). Against the base rate =
every valid minute of the same split. Direction = the sign of the excess move. Reported: events, events/day, days,
excess move (bps), day-clustered t, up share, best move toward / against, bracket win rates vs base.

HEAT (Steven's "how often x how big"): events per day x excess move in bps (bps of drift per day). Also bracket heat:
events/day x 2 x X x (win rate - base win rate). CHANCE HEAT: the same events shifted by a whole random number of days
(>= 30, 8 seeds, circular inside the split): the heat a reading gets by chance. The shift keeps time of day, so a
purely time-of-day effect shows chance heat close to its heat (by design: it is a control for the hour). Shown beside every heat.

## Matrix
Pairs: per coin, the 120 single levels with the largest |t| on split A (any horizon), each paired with the others and
with every context level (BTC.D, USDT.D, hour block). A pair's event = a minute where one level's event happens while
the other level holds. Triples: the 40 hottest pairs on A x the same candidate list.

## Splits and the check (no held-out data)
Build A = 2020-01-01 .. 2025-01-01, check B = 2025-01-01 .. 2026-08-01 (the perp SPLITS). A hot spot is a level with
|t_A| >= 3 and at least 30 events on A. On B: does the excess keep its sign, and how big is the heat. Reported: the
share of A hot spots that replicate on B (same sign, t_B >= 2 in A's direction) vs the share among the chance (shifted)
events, the rank correlation of A and B heat, and BHY at q 0.10 over the A hot spots' one-sided B p-values. The league
table ranks by B heat among those that replicate. Nothing is chosen on B beyond this table.

## Next (not this run)
Hot spots that replicate are scored on real Kalshi 15-minute and hourly prices with Steven's exits (sell at the first
bid that clears fees, the OR-H3 loser cut, settle only in profit) on discovery data, then HO-1 + placebo once under the
pipeline doc's bars. Known limits: overlapping minutes are clustered by day only; daily dominance is coarse (Binance has
no intraday BTC.D); the candlestick definitions are TA-Lib's.

---

# Amendment 1 (written 2026-11-11 05:35 UTC, Nov 11 12:35 AM EST, before any result of the amended code on real data)

**Why.** The first run (GitHub run 42953796892, commit d9f92ba) finished and two independent reviews of its code were
made (four lenses on Nov 11 ~04:00 UTC, two more ~05:20 UTC; findings in /mnt/project-files/oracle-setups/review/).
They found no price lookahead and correct labels, but showed on PURE-NOISE series that the first design reports heat
where there is none. **Disclosure:** the author saw the first run's league (top rows: XRP 1-minute oversold readings,
+1 to +4 bps). It was never reported to Steven and is void. Every change below comes from the reviewers' noise
simulations, their reading of Steven's spec and their robustness tests, not from which readings ranked. The data, the
coins, the splits (A 2020-01-01..2025-01-01, B 2025-01-01..2026-08-01), the horizons and DEV_END are unchanged.

## What the reviews found (v1), each with its fix
1. Entry at the signal bar's own close: bid-ask bounce made 35% of 1-minute rows hot on noise. **Entry is now the next
   minute's open**; the move entered one minute later is reported beside every row.
2. Coarse price steps (XRP, SOL in their cheap years; a step is up to 5 bps): rounding alone made 10-50% of cells hot,
   and the next open does not cure it (it usually equals the last close). **A hot spot's move must be at least one price
   step of the coin on A, and again on B** (step = smallest non-zero close-to-close change of the last day). A move
   within 1.5 steps counts as flat for the odds. Prices go into TA-Lib in whole steps so ties are exact.
3. Bracket heat (+X before -X) was positive on 79% of noise rows: it measures volatility. Brackets are now net of the
   losing side and against the base, a column, not a ranking.
4. The t ignored the base rate's own noise and was far too small for frequent levels; it now uses each day's influence
   on (event mean - base mean). Bars use the t distribution with (days - 1) degrees of freedom: hot on A = two-sided
   p <= 0.0027 (t = 3 under a normal), at least 30 events on at least 30 days; replicate on B = one-sided p <= 0.0228
   in A's direction, at least 30 events on at least 20 days.
5. B heat was unsigned (rank correlation 0.5 on noise). **B heat is signed in A's direction**; chance gives zero.
6. Heat counted overlapping windows (a 1-minute level firing 300 times a day at a 60-minute horizon). **Heat = distinct
   H-minute clock windows per day that hold an event x the move** (windows per day <= 1440 / H).
7. The day shift wrapped on a non-whole number of days. It now shifts whole days (per-level seeds): the "time-of-day
   part" of each single.
8. Pairs and triples re-counted their parent (one planted effect gave 213 replicating rows, 208 of them children).
   **A pair is now a trigger event split by the level of a second reading (a relationship curve). A cell counts only if
   it beats the trigger's OTHER events (lift, one-sided p <= 0.0228 on A) and its p on B is the larger of its own p and
   its lift's p.** Triples: a hot pair cell split by a third reading, same rule against the pair cell's other events.
9. No chance yardstick for counts. **Every coin is also run as a no-signal twin** (each minute keeps its size, range,
   volume and time and gets a coin-flip direction): the same pipeline, reported beside every count. BHY (q 0.10) is
   applied inside each kind (single, pair, triple) and track over the hot rows' B p-values.
10. Readings right after a data gap were artifacts of the forward fill: a bar holding a filled minute and the 100 bars
    after it carry no reading; an event needs a known, different previous level; broken rows (blank, zero, high below
    low) become gaps; a split with under 90% valid minutes stops the job.
11. Candlestick patterns: every firing is an event (v1 dropped repeats); none on a bar with no range or no volume;
    doji-type patterns are named "fires", not "bull"; Hikkake confirmation bars are their own event.

## What the spec review added
12. **Two tracks.** Move: excess move in bps (how big). Odds: the shift in P(up) - P(down), in points of probability
    (what a Kalshi contract pays on). Each has its own t, heat and league. For scale only: about 2.75 points is the
    break-even shift on a 50c contract held to settlement (fee 1.75c + 1c half spread).
13. **The full vocabulary** (python/oracle/heat_vocab.py): every TA-Lib 0.8.3 function that yields a signal, about 156
    value series and 17 two-state readings per timeframe plus the 61 patterns, several settings each; the functions left
    out (exact duplicates, math operators, FRACTAL and ZIGZAG which mark a pivot only after later bars) are listed in
    meta.json. Each value series is normalised (by ATR, NATR, its own rolling spread ...) so one set of edges fits all
    years. Edges come from split A only.
14. **The curve** (the linear heat map): each value series in 16 cells at fixed quantiles of its split-A distribution
    (1, 2.5, 5, 10, 20 ... 80, 90, 95, 97.5, 99%), read at every bar close: excess move and odds shift per cell.
15. **Events**: entering the bottom 2%, the 2-10% zone, the 90-98% zone or the top 2% (the inner zones separately when
    entered from outside and from the extreme: falling in / recovering, rising in / cooling), a flip of sign, a
    two-state flip, a pattern.
16. **Dominance and clock are states, not moments**: read at every 15-minute close while they hold. BTC.D / USDT.D
    1-day and 5-day change divided by the series' own daily volatility of the 60 days before (five levels, z edges
    -1.5 / -0.5 / 0.5 / 1.5), the two 1-day directions together (four quadrants) and the UTC 4-hour block. Every event
    level is split by these states; the 40 hottest triggers per timeframe (by abs t on A, + 10 context states) are split
    by every reading.
17. **Every TA by heat** (league_ta): each reading as a whole, cold ones too: act in every non-overlapping window in
    the direction its current cell showed on A, scored on B (chance gives zero, t about standard normal).
18. Outputs for the viewer: curves, event strips, relationship curves and the leagues in one compact file.

## Known limits (stated, not fixed in this run)
The fixed 5/15/30/60-minute windows start at the event, not on Kalshi's clock (:00/:15/:30/:45): only 15m and 1h
readings sit on the contract clock; the Kalshi scoring step handles the clock with real contract prices. Sizes are in
bps, not in units of volatility, so heat favours volatile coins and years. Dominance is daily (no intraday series is
held); USDT.D's daily change is close to the market's own previous-day direction with the sign flipped. The 1-minute
files on Drive begin 2020-01-01, so 2017-2019 is not in this run. The twin removes direction, so it cannot show the
rounding artifact of item 2 (the price-step rule covers that). Zone and cell edges use all of split A (in-sample on A,
clean on B). Day clustering treats days as independent.

## Unchanged
A MAP, not a validated rule. Nothing at or after 2026-08-01 is read; HO-1 and the lockbox stay closed; never compared
to paper; NEVER DOGE. Hot spots that replicate go on to Kalshi prices and fees under the edge-iteration pipeline.

---

# Amendment 2 (drafted 2026-11-11 06:50 UTC, final 13:10 UTC, Nov 11 8:10 AM EST, before any result of the amended code on real data)

**Why.** Two things happened before the Amendment 1 code ever ran on real data. (a) The edge iteration pipeline
(/mnt/project-files/plans/edge-iteration-pipeline.md, written Nov 11 06:25 UTC; Steven has not approved it yet) set data
rules for heat tables: a cut-off date, a stored table hash, loaders that refuse a later minute, and per cell the usual
wrong-way dip and the share right. (b) A third independent review of the Amendment 1 code (Nov 11 05:50-07:05 UTC;
findings in /mnt/project-files/oracle-setups/review/review3.json) ran it on synthetic series: pure noise, coarse price
steps, one planted effect. Two of its four lenses finished (causality, statistics). **The robustness lens, the lens on
conformance to Steven's spec and the second-opinion pass on the findings did not finish** (the session's usage credits
ran out); the author re-ran the statistics reviewer's planted and coarse-step series against the fixes instead (below). **No Amendment 1 or 2 code has produced a real-data result.** The only real-data run is the void first
run (42953796892). Disclosure repeated: that run read coin minutes through 2026-07-31 and the author saw its top rows.
Nothing below was chosen from them, and they must not be used to shortlist cells or pick settings later.

## The data cut (stricter than the pipeline asks)
1. `HEAT_END` = 2026-01-01 UTC. Build A = 2020-01-01..2025-01-01, check B = 2025-01-01..2026-01-01. **No minute at or
   after 2026-01-01 is read**: the workflow cuts each 1-minute file before the engine starts, the loader stops the job if
   a later minute is in the file, and the dominance series are clamped to the same date. January 1 to March 31, 2026
   stays unread for the pipeline's Stage 2 read (because of the void run that read is labelled a screen). April 18 to
   July 31 is the choosing period on Kalshi prices. HO-1 (Aug 1 - Nov 4) and the lockbox stay closed.
2. **Table hash**: the sha256 of each series' table text (heat.csv.gz, unzipped) is in meta.json, the league summary,
   league.md, RUNS.md and the registry calendar (/mnt/project-files/registry/edge-pipeline/calendar.md), where every
   read is logged before it runs.
3. **Per cell** (curve cell, event level, pair and triple cell): the usual wrong-way dip (the average worst move against
   the side before the best point inside the window, for both sides), the share of events that went up and that went
   down (a move within 1.5 price steps is neither). The league shows share right and share right over the base.
4. A TA-Lib function that fails to load stops the job (v2 only listed it).

## What the third review found, each with its fix
5. **A pair cell was only tested against its trigger's other events, not against what the second reading does on its
   own.** One planted clock effect (drift up in UTC 08-12) produced 583 pair rows that passed BHY, all of them the
   clock restated. **A pair or triple cell must now beat BOTH parents on A and on B**: the trigger's other events (lift)
   and the second reading's own effect over all valid minutes while that level holds (second lift). Its B p-value is
   the largest of its own p and the two lifts' p. Its lift over the trigger must also be at least one price step on A.
6. **Trigger slots were taken by sub-step rounding artefacts** on coarse-step series (a huge t on a move smaller than
   one price step). A trigger's score now counts a horizon only if its move is at least one price step; a trigger with
   no such horizon is not taken.
7. **The t was too generous for event sets tied to volatility** (a few very volatile days carry the variance). The t
   distribution now uses the EFFECTIVE number of days, (sum psi^2)^2 / sum psi^4 over the per-day influences, capped at
   the day count, for the hot bar on A and for every p on B.
8. **One twin is one draw**: twin counts differed 2 to 8 times between seeds. **Each coin now has three twins**; the
   league reports the median twin set with the lowest and highest, applies BHY inside each (set, kind, track), and warns
   when a twin set is missing or partial.
9. Curve cells and the A-B rank agreement were not held to the price-step rule. The viewer hatches curve cells under
   one price step; the rank agreement uses only rows whose A move is at least one step.
10. The every-TA league's t was not standard normal on a coarse grid. A cell is now kept on B by its sample (30 events
    on 20 days), never by the size of its B move; a reading with zero variance has no t. On noise the t's spread is
    about 1.0 to 1.4, so read it against the twin rows, not against a normal table.
11. The "chance heat" column was a function of t on B and is dropped from the tables (the twin rows are the yardstick).
12. Not every hot relationship is written (150,000 per coin at most). The ones left out now stay in the BHY family as
    p = 1, so the cap cannot make the correction lighter.
13. Odds wording: the odds number is half the shift in P(up) - P(down), in points. It equals the shift in the chance of
    an up close only when no outcome is flat; on a coarse-step coin many 5-minute outcomes are flat, so the 2.75-point
    fee scale is loose there.
14. Causality lens: no lookahead found; labels match a brute-force recomputation bit for bit. Two small fixes: the price
    step used to put prices on a grid is now taken from split A's rows only (it was the whole file), and the twin no
    longer rescales a float-noise series (2^50 guard; twin prices are rounded to 12 significant digits). After a gap
    run longer than 14 bars, 500 bars carry no reading (it was 100: shorter than the longest normalisation window).

## The fixes re-checked on the reviewer's own series (synthetic, 300 days, by the author)
One planted clock effect: before, 583 pair rows passed BHY; after, 0 pairs and 0 triples pass and the planted level
itself still passes as a single (3 horizons; 1 unrelated single also passes). Pure noise on a 3.7 bps price step: 0 rows
pass BHY in any kind for the series and for two twins; replicating pairs 0 (move) and 4 (odds) against 0 and 2-3 in the
twins (before: 58 pairs and 101 triples replicated). Every-TA league on that noise: t on B at least 2 for 2.0% of
readings, at least 3 for 0.3%.

## Known limits (added)
The twin keeps each minute's size and flips its direction, so readings that depend on exact ties (several candlestick
patterns, the DM family, KVO, Aroon) do not fire alike on a twin of a coarse-step coin: the twin counts for those are
not like for like. Three twins give a median and a range, not a distribution. The second lift treats the second
reading's own effect as known (it is measured on every valid minute). The pipeline's walk-forward by year (tables from
earlier quarters only) and the 54% / 200-day / 4-of-5-years screen are Stage 2 work on top of these tables; this run is
the map with one build and one check period. Gap handling, broken rows and behaviour at full size (3 million minutes)
were reviewed for v1 and are covered by the tests, but not re-reviewed for this code by the unfinished robustness lens.

## Unchanged
Everything else in Amendment 1: next-minute entry, the price-step rule, two tracks, windows-per-day heat, the vocabulary,
the bars (hot on A two-sided p <= 0.0027, replicate on B one-sided p <= 0.0228, 30 events on 30 / 20 days), coin price
only, never compared to paper, NEVER DOGE. A MAP, not a validated rule.

---

# Amendment 3 (written 2026-11-11 13:35 UTC, Nov 11 8:35 AM EST, before any result of run 43026335764 or of this code was seen)

**Why.** Steven, Nov 11 13:17 UTC (8:17 AM EST): "the only thing that we need to know is if we can detect direction,
sustaining for at least 1 minute or long enough for an exit to take place in profit"; he does not trust the testing
thresholds ("cutting unnecessarily") and leaves after-fee profit to the bot's exits. The pipeline thread (13:29 UTC)
turned the league into a ranking with no pass bar; the hottest readings go on as a batch to one test on Kalshi prices.
Run 43026335764 (Amendments 1 and 2; 5/15/30/60 minutes) had started at 13:07 UTC. None of its results had been read
when this was written; the run of this amendment replaces it.

## What is added
1. **A 1-minute horizon.** HORIZONS = 1, 5, 15, 30, 60. Entry stays the next minute's open; the 1-minute read is that
   minute's close. Every statistic is computed for it as for the others (the "entered one minute later" column is zero
   at this horizon by construction).
2. **Minutes held.** Per event and side: how many consecutive minute closes, from the first one after entry, stay
   beyond the entry by more than the dead band (1.5 price steps); 0 = the first close is not on that side, 60 = the whole
   hour. Per cell the mean for each side; the league shows it in the reading's direction and against the same number
   over all valid minutes of the period (the base).
3. **The direction league: every event level, nothing cut.** A level is listed when it has a sample on both periods
   (30 events on 30 days of A, 30 events on 20 days of B). These are sample floors, not significance bars. Its
   direction is the sign of its odds on A; every B number is signed in that direction, so a level with no information
   scores about zero. Columns per horizon: windows per day, share right on A and B, share right over base, odds points,
   t, heat (windows per day x odds points: how often x how sure), minutes held and over base, best move, usual dip. Two
   orders: by heat, and by share right over base among levels that fire at least 0.2 windows a day. The marks of
   Amendments 1 and 2 (hot on A, replicates, BHY) stay as columns for information; they remove no row.
4. **The chance scale stays beside it and judges nothing.** Per horizon: the share of levels whose direction carried
   to B (a coin flip gives about one half), for the coins and for the no-signal twins, and the twins' best and 99th
   percentile heat and share right over base.

## Unchanged
The data (coin minutes 2020-01-01 to 2025-12-31; build 2020-2024, check 2025; no minute of 2026), the entry, the
price-step rule, the twins, the hash, the curves and the every-TA league. Pairs and triples are still built from the
triggers that are hot on A: that is a limit on compute (the full cross is about 10^9 cells), not a judgment on singles.
One more horizon makes each BHY family a quarter larger; BHY is now a column, not a gate.

## Next (not this run)
Default batch, fixed here before any result is read (the pipeline thread may fix another rule in the registry before
the Kalshi read): for the 15-minute and the hourly contract, the 10 events with the most heat on B in the direction
league at the 15- and 60-minute horizon, one row per coin and event. The one test (pipeline doc, "The one test"): buy
the called side at the ask; a profit window is one full minute whose lowest bid stays at or above entry plus both fees
plus 1c; the window rate against random entries in the same contracts and hours. Horizon and contract type are picked
on Apr 18 to Jul 31, 2026; Aug 1 to Nov 4 is read once per pre-fixed batch.

---

# Amendment 4 (written 2026-11-11 16:06 UTC, Nov 11 11:06 AM EST, AFTER the league of run 43030435253 was read)

**Why.** Steven, Nov 11 15:49 UTC (10:49 AM EST): today's curves go into the bot's paper and live trading. The lane
that places the entries (another thread) needs the calls in a file it can load and a way to read the same levels live.
The league result was known when this was written (19,055 event levels; 79% kept their build-years direction on 2025
at 15 minutes, the no-signal twins 50%), so nothing below may be read as fixed in advance.

1. **Traded pack** (`python/oracle/heat_pack.py`, `research/oracle_heat/latest/traded_pack.json`). Per coin, for the
   15- and 60-minute horizon: the 40 event levels with the most heat on B and the 20 with the highest share right over
   base (at least 0.2 windows per day). No pass mark filters a row. **Readings that are the same event under two
   names are one row**: identical sample and identical numbers on both periods (RSI14 and CMO14; PERCENTB20/2,
   PERCENTB20/2.5 and ZSCORE20; close minus the typical, median and weighted price). This was chosen after seeing that
   the top rows held such copies; the literal top 10 of Amendment 3 (copies counted separately) stays in the file under
   `batch_amendment3_literal`, and `batch10` marks the ten hottest with copies counted once. The no-signal twins'
   scale for the same horizon is in the file (`chance`), and each row says whether its heat is above the twins' maximum.
2. **Live reader** (`python/oracle/heat_live.py`). The engine's vocabulary, bucket and event rules on a window of
   1-minute bars, with the zone edges and price step stored in the coin's meta.json. Default window 3,000 bars per
   timeframe. Tests: on a synthetic history it reproduces the engine's codes exactly on the whole grid, and a window
   gives the engine's keys (agreement at least 98.5%).
3. **Parity job** (`python/oracle/heat_parity.py`, workflow `oracle-heat-live.yml`). Per coin it recomputes every
   reading on 2020-2025 the engine's way, requires the zone edges to equal the ones in meta.json, writes the keys the
   engine fires in the last 3 days of 2025 (the fixture) and compares the live reader on a window with them. It reads
   coin minutes 2020-01-01 to 2025-12-31 only (same cut, same loader) and computes no label or return.

**Known limits.** The tables were built on Binance spot bars; a live feed from another exchange will not give the
same levels every time (an earlier check in this project: about 91% signal agreement between Binance and Coinbase
1-minute bars). The hottest 15- and 60-minute calls are close relatives (1-minute readings at an extreme, fading), so
ten of them are far fewer than ten independent bets. The pack is a map on coin price; the one test on Kalshi prices
has not been run.

**Parity result and two additions (2026-11-11 16:20 UTC, 11:20 AM EST).** Parity job 43054998730 on the real
2020-2025 minutes: all 624 zone edges per coin equal the ones in meta.json; on Dec 29-31, 2025 the live reader on a
3,000-bar window gives the engine's keys in 100% of cases on BTC and SOL, 99.92% on ETH and 99.65% on XRP. The one
indicator that differs is PVI (1- and 5-minute bars, ETH and XRP only on those days). PVI is a running product from
the first bar of the series, so the engine's value and a window's value are not the same number; the likely cause of
the different keys is rounding at the size the product reaches after six years (not checked further).
Additions, neither changes a table or a rank: (a) each pack row carries `live_parity` (False for a PVI row on any
coin) and the pack a `live_reader_parity` block; (b) `research/oracle_heat/latest/live_meta.json`, the zone edges
and price step behind the pack's rows at the tables' precision, so a reader on the server needs no Drive access.
