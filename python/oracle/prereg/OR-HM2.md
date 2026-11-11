# OR-HM2: confluence discovery across all data (design, written before any result)

Written 2026-11-11 ~23:30 UTC (6:30 PM EST). Thread "Find unseen TA confluence via oracle". This is the next amendment of
the oracle design (python/oracle/prereg/OR-HM1.md). It adds modules and a workflow. It changes no line of heat.py and no
stored table, hash, league or pack of run 43030435253.

Steven, Nov 11 22:26 UTC (5:26 PM EST): "We can try all of the what we haven't tried yet but I want our focus to be on
perfect Oracle runs to teach TA-lib usage in finding direction. It should cross reference any data it has to search for
some edge through confluence that is otherwise unseen."

The standing rules stay as they are. NEVER DOGE. Coin minutes 2020-01-01 to 2025-12-31 only: build on 2020-2024 (A),
check on 2025 (B), and no minute of 2026 is loaded. No pass bar cuts a reading or a cell: rank, do not gate (sample
floors only). The no-signal twins (each minute's direction replaced by a coin flip, same pipeline) are the chance
scale beside every count; significance marks are columns, never filters. No sealed test weeks. Heavy compute runs on
GitHub Actions runners (at most 10 jobs at once for this thread), never on the bot server. Times in Eastern and UTC. The
later test on Kalshi prices (does the called direction hold at least 1 minute, so an exit in profit is possible,
against random entries) is not part of this run.

## What had been seen when this was written
- The league of run 43030435253: 19,055 event levels; direction kept on 2025 in 70-79% of them, twins 50%.
- The pair pack: 1,011,763 stored pair cells per horizon.
- The clock add-on: the clock adds little.
- The long horizons: 240 minutes kept direction 69.6%, twin 51.1%.
- The direction-research report (/mnt/project-files/direction-research/report.md).

No HM2 code exists. Nothing of an all-pairs scan or a learner has been computed on real or twin minutes. The only HM2
number is a timing of numpy bincounts on random arrays: 6.5 ms per pair at 450,000 entries and 63.5 ms at 3.16 million,
on a 4-core 2.1 GHz Xeon.

Where an HM1 result shaped a choice, this text says so: the 240-minute horizon is in because the perp lane trades it,
and the clock is in as a cheap state even though it added little on its own. No reading, level or cell was chosen
because it ranked in HM1.

## Why: what HM1 cannot see
HM1's pair and triple stage crossed only 170 triggers per coin with every reading: the 40 strongest event levels per
timeframe on A, plus 10 context levels. It stored a relationship only when one of its cells was hot on A (Amendment 3:
"the full cross is about 10^9 cells"). Five kinds of confluence are therefore unseen:
1. Two readings that are each quiet alone but call direction together (a joint state whose parts are flat).
2. Two readings neither of which is a top trigger.
3. Two states held at the same minute, with no event of either. The tables pair an event with a state.
4. Any data beyond the coin's own bars and daily dominance:
   - the other three coins;
   - the minute's place in the Kalshi quarter hour;
   - the volatility regime;
   - rolling taker flow;
   - the perpetual's basis and funding;
   - the US release calendar.
5. More than three readings at once.

## How this design was chosen
Two independent designs were written and scored from 1 to 5 on each point (25 at most):
- **A**: an exhaustive scan of every pair of readings, plus a fixed number of triples.
- **B**: shallow boosted trees that learn how readings combine, read out as rules.

| design | finds unseen confluence | honesty | use to the bot | compute | effort on the engine | total |
|---|---|---|---|---|---|---|
| A, scan | 4.5 | 4.5 | 4 | 3.5 | 3.5 | 20 |
| B, learner | 3.5 | 3.5 | 4 | 4 | 2.5 | 17.5 |

The scan wins on what matters most. It measures every pair exactly, including joint states whose parts are flat alone.
Greedy trees cannot find those, because a tree splits only on a reading that helps on its own.

The learner wins on reach and on teaching. One rule can hold up to three readings, and many weak readings add up into
one call. It also shows how much the model leans on each TA function.

This design takes the scan as its base and grafts the learner on where it earns its place:
- It proposes triples, which the scan then measures with the same counts.
- Its call is scored as one more reading.
- Its per-reading contributions feed the TA-Lib usage cards.

Three parts of B are left out:
- Its second check on 2023-2024. The owner's rule is one check, on 2025.
- Its own Shapley-interaction code. The scan measures every pair's interaction directly.
- Its 68 cross-coin zone codes. A compact cross-coin set is used instead.

## Data (all cut at 2026-01-01 00:00 UTC, Dec 31 7:00 PM EST)
| source | what | where |
|---|---|---|
| Coin minutes | Binance spot 1-minute bars of all four coins, in every job (the other three feed the cross-coin readings) | Drive raw/perp-ta-history/<A>/binance-1m/<A>/1m.csv |
| Perpetual minutes | Binance USD-M perpetual 1-minute bars of the job's coin | Drive raw/perp-ta-history/<A>/binance-um/<A>/1m.csv |
| Funding | settled funding rates of the job's coin | Drive raw/perp-ta-history/<A>/binance-funding/<A>/funding.csv |
| Dominance | BTC.D and USDT.D daily closes, as in HM1 | research/btcd_fractal/data |
| Daily markets (review) | the other daily series held beside dominance: crypto ETH.D, OTHERS.D, USDC.D, TOTAL, TOTAL2, TOTAL3 (stamped 00:00 UTC) and DXY, SPX, US10Y, USDJPY, EURUSD, GBPUSD, USDCNY (stamped at their own session open: 21:00-23:00 UTC for FX and rates, 13:30/14:30 UTC for SPX) | research/btcd_fractal/data/<NAME>_1d.csv |
| Open interest (review) | Binance USD-M open interest of the job's coin, every 5 minutes (ts = metrics create_time; BTC from Sep 2020, ETH, SOL and XRP from Dec 2021) | Drive raw/perp-ta-history/<A>/binance-oi/<A>/oi.csv |
| Found by the inventory (review) | BTCDOM hourly index (binance-index, from Jun 2021), Coinbase 1-minute bars (coinbase-1m) and order book snapshots (from 2023), each used only if the preflight inventory finds it for 2020-2025 | Drive raw/perp-ta-history/... |
| Release calendar | 262 events from the BLS archive pages and the Fed calendars, with ET and UTC times: CPI 71, jobs 71, PPI 70, FOMC 50 (including the three unscheduled 2020 statements: Mar 3 10:00 AM ET, Mar 15 5:00 PM ET, Mar 23 8:00 AM ET). A `scheduled` column (False for those three) is added before the file is committed | python/oracle/calendars/macro_calendar_2020_2025.csv |
| Main run metas | zone edges and price step of each coin, so they can be asserted and used for the other coins' readings | Drive models/oracle-heat/runs/43030435253/<COIN>/meta.json |
| HM1 league files | pairs files for the "seen in league" column; the packs the bot loads (traded, pair, clock, perp, perp pair); direction_all for the usage cards' own call by level | Drive league/pairs/pairs_<COIN>.csv.gz and direction_all.csv.gz; repo research/oracle_heat/latest/*_pack.json |

**How the cut is enforced.** The workflow's awk drops any coin, perp, funding or open-interest row at or after
HEAT_END, and the strict loaders refuse one (heat.load_minutes and a new load_extra). Funding rows count by their
calc_time, open-interest rows by their create_time, and calendar rows by their UTC time. Every time column is checked
to be milliseconds (13 digits, between 2019-01-01 and HEAT_END) before the cut: a file stamped in seconds would pass
the awk cut with its 2026 rows, and one in microseconds would lose all of 2025. A daily row whose known time (below)
is at or after HEAT_END is dropped at load.

**When each source is known (review).** Each row is used from the first decision close at or after its known time:
- coin, perp, Coinbase and BTCDOM bars (stamped at their open): stamp + their length, as the engine's bars;
- funding: calc_time + 1 minute, so at row i only when calc_time ≤ the open of minute i. The preflight checks the stamp
  is the settlement time and not the start of the period it pays for: the rate stamped T must follow the mean basis
  over the 8 hours before T more closely than over the 8 hours after (on A rows), or the run stops;
- open interest: create_time + 5 minutes (one whole period later: whether create_time opens or closes its 5-minute
  window is not verified), carried at most 10 minutes;
- daily markets: stamp + 24 hours. A daily bar is stamped at its own session's open and never closes later than that.
  HM1's day rule ((ts // day) × day, read after that UTC day closes) is safe for the 00:00 UTC crypto series, but on
  DXY, US10Y and the FX series (stamped 21:00-23:00 UTC) it would read a bar about 22 hours before it closes;
- calendar: a scheduled event is known in advance; an unscheduled one only from its own minute.

**Not used in this run:**
- the long/short ratios (not in the stored oi.csv: ts, oi, oi_usd);
- the premium index (not held; the basis is computed from the perp and spot closes);
- the spot trade count (not in the stored 1-minute CSVs: ts, o, h, l, c, v, tb);
- M2, CNM2, EUM2, GBM2, JPM2, FEDBS, TGA and RRP: their stamps are period dates, not release times (a month's M2 is
  published weeks after its stamp), so any reading of them would leak;
- STABLES (starts May 2025: no build rows); BTCD_CAP, BTCD_CMC, BTCD_SPLICED (copies of BTC.D); BTCUSD and ETHBTC
  daily (the minute bars hold them).

**Unchecked sources and the inventory (review).** Whether the perp, funding, open-interest, BTCDOM, Coinbase and order
book files are on Drive has not been checked from here. The test job first lists every source folder under
raw/perp-ta-history/<A>/ for the four coins and every file in research/btcd_fractal/data. Each source it finds must
either feed a family of this design or have a line under "Not used" with its reason, written in this file before the
full run ("cross reference any data it has"). A missing perp, funding or open-interest file stops the run. No family
is dropped silently: dropping one needs a written note in this file before a re-run.

## Readings
All readings are bar codes known at the close of the decision row i. The entry is the next minute's open, o[i+1].
Each reading is the engine's dict {'name', 'k', 'codes', 'levels', 'base'} with its flags, so heat.read_state,
event_levels and level_events work on it unchanged.

1. **The engine's readings.** build_readings gives 1,350 per coin:
   - 624 zone readings of 5 levels;
   - 408 sign readings;
   - 68 two-state and categorical readings;
   - 244 candlestick readings, read as their level on the last closed bar;
   - 6 context readings.

   Their zone edges are asserted equal to the main run's meta.json, as heat_long.edges_check does: <COIN>/meta.json
   for the coin and <COIN>-twinN/meta.json for twin N (the twins use the same seeds, so their bars are HM1's twins). A
   difference stops the job.
2. **New readings**, fixed now (table below): 54 per coin, plus 3 open-interest and 13 daily-market readings (review),
   plus 2 BTCDOM, 3 Coinbase and 1 order book reading when the inventory finds those files.
   - Value readings get 5 zones at the A quantiles 2/10/90/98% (ZONE_Q) of all A rows. Their norm tables also come
     from A rows only.
   - The engine's stale rule applies to every window a reading reads. A window that holds a forward-filled minute, or
     falls in the 100 bars after one (500 after a long outage), gives "no reading" (NA).
   - Names carry their family as a prefix, so the league can group them.
3. **Copies merged.** Readings whose codes agree on at least 99.5% of the A entries where both are known become one
   reading, with their aliases listed (RSI14 and CMO14 are the known case). A twin applies the same rule to its own
   codes. Near-copies (RSI14 and RSI21, PERCENTB and ZSCORE20 ...) stay separate readings; the lists collapse their
   rows (What is reported, 3).
4. **Learner only.** For each zone reading there is a state `ZS:<name>`: the event that fired on its last closed bar
   (none, very low, low falling in, low recovering, high rising in, high cooling, very high). A rule can then say
   "15m RSI14 low, recovering" without doubling the scan.

| family | readings and exact definition (all k = 1 unless noted) |
|---|---|
| Position | `POS:QPos` (15 levels m00-m14), `POS:QPhase` (m00-04 / m05-09 / m10-14) and `POS:HourQ` (4 levels), all of the entry minute: (i+1) % 15 and ((i+1) % 60) // 15. ET and UTC give the same values. m14 is the last minute before a Kalshi quarter-hour mark (:00, :15, :30, :45). |
| Clock | `UTC1h`, `NY30m` (daylight saving followed) and `Weekday`, from heat_clock.clock_readings. Each keeps its own k and is the state of the entry minute. |
| Cross-coin (each other coin O) | `X.O:R1z`, `X.O:R5z`, `X.O:R15z`: O's log return over the last 1, 5 or 15 minutes ending at close i, ÷ (sd of O's 1-minute log returns over the 1,440 minutes ending there × √k).<br>`X.O:Gap5`, `X.O:Gap15`: the sum of the last 5 or 15 one-minute residuals of own return − β × O's return, ÷ (residual sd × √k). β is the OLS slope over the 1,440 minutes ending at close i.<br>`X.O:RSI14`, `X.O:TakerBuy`: O's own 1-minute engine readings, zoned with O's main-run edges (on a twin, O's twin edges). They are computed directly with the engine's steps and tested equal to heat_live.tf_codes on O's full grid.<br>`X:Breadth5`, `X:Breadth15`: the number of the other three coins up by more than 1.5 of their price steps over the last 5 or 15 minutes, minus the number down (−3 to +3). It is NA before SOL's first minute (2020-08-12 00:00 UTC, Aug 11 8:00 PM EDT), as are all of SOL's readings. |
| Volatility (own path) | `VOL:RV1d`, `VOL:RV7d`: root of the sum of squared 1-minute log returns over the 1,440 or 10,080 minutes ending at close i.<br>`VOL:RVratio`: the last 60 minutes' RV ÷ the last day's, × √24.<br>`VOL:RVclock`: the last 60 minutes' RV ÷ its A median for the same hour of the week.<br>`VOL:VoV7d`: sd of log hourly RV over the last 168 completed hours.<br>`VOL:Busy`: volume since 00:00 UTC ÷ its A median at the same minute of the day.<br>`VOL:Semi60`: (up semivariance − down semivariance) ÷ total, last 60 minutes.<br>`VOL:Jump1`, `VOL:Jump5`: none / up / down, for a last 1- or 5-minute move beyond 4 × the sd of the prior 60 one-minute returns × √k. |
| Flow (rolling, every minute) | `FLOW:TB5`, `FLOW:TB15`, `FLOW:TB60`: taker-buy volume ÷ volume over the last 5, 15 or 60 minutes.<br>`FLOW:Stretch5`, `FLOW:Stretch15`, `FLOW:Stretch60`: k-minute log return ÷ (1-day sd of 1-minute returns × √k).<br>`FLOW:VolZ15`: z of the last 15 minutes' volume against the last day's 15-minute volumes.<br>The vocabulary's own bars change only on bar closes, so these differ from it. The research report's "taker-driven stretch" (s12 #2) is the pair Stretch × TB, which the scan measures. |
| Perp | `PERP:Basis`: (perp close − spot close) ÷ spot close, in bps.<br>`PERP:BasisChg15`: its change over 15 minutes.<br>`PERP:Lead1`, `PERP:Lead5`: perp log return − spot log return over 1 or 5 minutes, in bps.<br>`PERP:FundZ`: the last settled funding rate ÷ the sd of the 90 settlements before it. It is known from calc_time + 1 minute: at row i only when calc_time ≤ the open of minute i.<br>`PERP:FundClock`: under 15 minutes, 15-60 minutes, 1-4 hours or 4-8 hours to the next settlement. The next settlement is the last one plus the gap between the last two, so it is known at close i. The usual schedule is 00:00 / 08:00 / 16:00 UTC (7:00 PM / 3:00 AM / 11:00 AM EST). |
| Open interest (review) | `OI:Chg15`, `OI:Chg60`: log change of open interest over the last 15 or 60 minutes of known readings ÷ the sd of that change over the day before.<br>`OI:PxQuad60`: price up or down (beyond 1.5 price steps, else NA) × open interest up or down over the last 60 minutes: 4 levels (new longs, short covering, new shorts, long liquidation). NA before the file's first row and where the last known reading is over 10 minutes old. |
| Daily markets (review) | `DMKT:<NAME>1d` for ETH.D, OTHERS.D, USDC.D, TOTAL, TOTAL2, TOTAL3, DXY, SPX, US10Y, USDJPY, EURUSD, GBPUSD and USDCNY: the last known bar's change ÷ the series' own daily sd over the 60 bars before it, in HM1's five dominance levels (z edges −1.5 / −0.5 / 0.5 / 1.5). Known from stamp + 24 hours (Data). |
| Found by the inventory (review) | `IDX:BTCDOM1h`, `IDX:BTCDOM4h`: log change of Binance's BTCDOM index over the last 1 or 4 closed hours ÷ its 30-day sd of that change (k = 60).<br>`CB:Lead1`, `CB:Lead5`: Coinbase log return − Binance log return of the same coin over 1 or 5 minutes, in bps; `CB:PremChg15`: the change of log(Coinbase close ÷ Binance close) over 15 minutes. Changes only: the level mixes the USD/USDT rate in.<br>`BOOK:Imb`: (bid depth − ask depth) within 1% of the mid ÷ their sum, from the last snapshot stamped at or before close i, NA when it is over 5 minutes old. |
| Macro | `MACRO:R830`: none; 30 to 1 minutes before; 0-14, 15-59 or 60-239 minutes after an 8:30 AM ET CPI, jobs or PPI release (13:30 UTC in winter, 12:30 UTC in summer). All windows are of the entry minute.<br>`MACRO:FOMC`: the same windows around a 2:00 PM ET statement (19:00 / 18:00 UTC). The unscheduled 2020 statements (at their own times) get only "after" levels, because they were not known in advance.<br>`MACRO:ReleaseDay`: none / release day (the ET day holds an 8:30 release or an FOMC statement). For an unscheduled statement the day counts as a release day only from its own minute. |

**What the twin flips and what stays real (review: one joint coin flip).** A twin flips each minute's direction with one
seeded sequence, indexed by the absolute minute, and applies it to every price path the job reads:
- the job's coin (exactly heat.make_twin(m, seed), so its bars equal HM1's twin of that seed);
- the other three coins (for BTC, ETH and XRP, whose grids start at the same minute, this is exactly HM1's twin of the
  same seed; SOL as another coin takes the flips of its own minutes, and minutes before a job coin's first minute take
  a second seeded stream);
- the job coin's perpetual and Coinbase minutes.

Taker-buy volume is swapped on flipped minutes, as the engine does. The TA, volatility, flow, cross-coin, lead and
open-interest-quadrant readings are then computed by the same code from the flipped paths. With independent flips
(the draft's plan), the real ETH path would move against the twin's BTC path at random. The cross-coin cells would then
fill unlike the real coin's, and the twins would not be a like-for-like scale for the family this run is about. A
joint flip keeps every minute's co-movement and still leaves no memory: the next minute's sign is a fresh coin flip
for every coin.

Levels that are not a direction stay real: the basis level and its 15-minute change, funding, open interest changes,
BTCDOM, dominance, daily markets, macro, position and clock. A flipped perp and spot would let the basis level wander
without bound. These are context that knows nothing of the twin's coin flips, so any link from them to the twin's
direction is chance.

## Entries and labels
- **A entries:** every 7th valid row of A (row % 7 == 0), about 376,000 per coin. Seven shares no factor with 5, 15, 30
  or 60, so every quarter-hour position gets the same share.
- **B entries:** every valid minute of 2025, about 525,000 per coin. The counts and windows per day are then what a
  reader firing each minute would see.
- **Horizons 1, 5, 15, 30 and 60:** the engine's labels (dead band 1.5 price steps, holds 0-60 minutes) on the engine's
  Grid (HMAX = 60). A's rows therefore end where the main tables' did, at 2024-12-31 23:00 UTC (6:00 PM EST).
- **Horizon 240:** heat_long's int16 label function with the horizon 240 alone, on its own Grid.
  - Its A rows end 240 minutes before 2025: 2024-12-31 20:00 UTC (3:00 PM EST). So no A label reads a 2025 price.
  - Its B rows end 240 minutes before 2026.
  - An entry counts at 240 only if it is a valid row of that grid.
- **Base:** every valid row of the split, as in the engine. The odds mean what they mean in the league.

## Part 1: the scan
**Pairs: every pair of readings with a different base**, about 900,000 per coin (870,000 before the review added 16
to 22 readings). The engine's rule applies: a zone reading and the sign reading of the same series and timeframe are
one series and are not paired. The same indicator on two timeframes is a pair.

At each entry, the two states give a cell. A **confluence cell** is one where both readings hold a known level that is
not neutral ('mid' or 'none'). The other cells are counted too, because the fit in point 2 below needs the whole table.
They are not ranked, by the engine's rule that a neutral level is neither an event nor a condition.

**Counting, all exact:**
- **Key and bincounts.** Each pair gets one int32 key per entry, (cell, day). A and B entries are counted together, with
  one count bincount and four weighted bincounts. The weights pack whole-number fields into a float64: 12 bits per
  count and 17 bits per hold sum, and every bin stays below 2^53.
  - Weight 1: up and down at 1 and 5 minutes.
  - Weight 2: up and down at 15 and 30 minutes.
  - Weight 3: up and down at 60 and 240 minutes.
  - Weight 4: the 240-minute count, and the holdU and holdD sums of the 60-minute grid (0-60 each; a day's sum is
    under 86,400 < 2^17). The 240-minute holds would need 19 bits, so they are not packed; the re-measure gives them.

  These per-cell, per-day sums give every number below. That includes the day-clustered t, computed with heat._clu's
  algebra (each day's influence on the cell mean minus the base mean, and the effective day count).
- **Neutral-level shortcut.** Of the two readings, the one with fewer non-neutral entries leads. Only entries where it
  is non-neutral or NA are counted. Its neutral cells are then the other reading's own per-day totals, counted once
  per reading, minus the counted cells.
  - These are whole numbers, so the result is identical, and a test checks it.
  - The shortcut cuts the work to the share of entries where a zone reading leaves 'mid' (about a fifth).
  - Pairs of two sign readings have no neutral level and are counted in full.
- **Windows per day on B.** For each horizon H, take the bitwise OR of 1 << cell over each H-minute clock window, then a
  count per cell. A pair with more than 64 confluence cells uses np.unique instead.

**Per cell, split and horizon:**
1. **Basics.**
   - n, days, and the share going up, flat and down.
   - Odds = 50 × (mean sign − base mean sign), in the league's odds points, with its day-clustered t.
   - Share right and share over base, in the cell's direction.
   - Minutes held in that direction, and over base.
   - Windows per day (B).
2. **Interaction ι** ("more than the parts").
   - Fit the log-linear model [ab][ay][by] to the table N[a level, b level, outcome up/flat/down] over the entries where
     both readings are known, by iterative proportional fitting (30 rounds at most). In this model each reading
     shifts the outcome on its own, the two readings may go together, and there is no joint term.
   - ι = 50 × (observed mean sign − fitted mean sign), in odds points.
   - t_ι = that difference ÷ the cell's own day-clustered SE.
   - Each split is fitted on its own table.
   - **Second scale (review).** "No joint term" depends on the scale. [ab][ay][by] is multiplicative in the odds. Two
     readings that each carry a real call, and add up on the probability scale, leave a ι of a fixed sign that repeats
     on B. A coin-flip twin has no calls at all, so it cannot show this. So ι_add is also fitted: the mean sign as a
     main effect of a's level plus one of b's level (weighted least squares by backfitting, 30 rounds, same table).
     ι_add = 50 × (observed − fitted) on that scale.
   - **iota_robust** = the one of ι and ι_add nearer zero when they share a sign, else 0. It is a measure, not a pass
     mark: every cell keeps its row and both ι columns. iheat (What is reported, 2) and the triple choice use it.
3. **Lift over each part, lift_min.**
   - Take the cell's odds minus the odds of a's level with b at any other known level. Do the same with a and b
     swapped. lift_min is the smaller of the two, with its day-clustered t.
   - This is what HM1's lift measures, so a row can be compared with the pair pack.
4. **Columns beside ι:**
   - odds_fit;
   - iota_naive = odds − odds_a − odds_b;
   - each part's own state odds and t on A (its effect over all A entries);
   - `parts_hot`: how many parts reach |t_A| ≥ 3 alone;
   - `part_tmax`;
   - `assoc`: Cramér's V of the two readings on A;
   - `families`;
   - `learner_path`: a learner rule holds this pair;
   - `seen_in_league` (review: provenance, not significance): `pack` if either part's level is in a pack the bot
     already loads (traded_pack, pair_pack, clock_pack, perp_pack, perp_pair_pack, as committed under
     research/oracle_heat/latest/); `stored` if the two readings were stored together as an HM1 relationship (pair
     tables of run 43030435253); `none` otherwise. A state level matches HM1's event keys of the same level ('low'
     matches 'low (falling in)' and 'low (recovering)'). The draft matched against direction_all, which lists every
     event level, so almost no cell could have been "none". The label goes by reading names, so a twin's cells get the
     same labels as the real coin's.
5. **Signing.**
   - d = the sign of the cell's odds on A, and dι = the sign of iota_robust on A (0 on A: the cell has no interaction
     direction, and its iheat_B is 0). B numbers are multiplied by them.
   - `iota_with_call` says whether dι = d. If yes, the joint state pushes the call further than its parts do. If no, it
     holds the call back, which is a pause lesson.

**Triples.** The number is fixed, they are chosen on A only, and the twins use the same rule. Every cell of a scanned
triple is written.
- **(a) From pair cells.**
  - Take the 120 confluence pair cells with the largest |iota_robust| ÷ SE on A at 15, 60 or 240 minutes. Each must
    have at least 2,000 A entries, and at most 3 may come from one reading. This is a compute cap chosen on A only,
    not a pass mark.
  - Each cell becomes an in/out flag, crossed with every reading: about 158,000 triples per coin.
  - ι is what the third reading adds inside the pair cell.
- **(b) From the learner.**
  - Take every leaf path of the learner's A-trained trees (Part 2) that names three different readings: about 5,000 to
    10,000 per coin.
  - Measure the 2×2×2 table of its three conditions.
  - ι3 is measured against the model with every two-way term among the conditions and each condition's own effect on
    the outcome. lift_min is taken over each member.

## Part 2: the learner (grafted from design B)
1. **Models.** For each coin, series and horizon (1, 5, 15, 60, 240) there are two models:
   - **TA**: the engine's 1,350 readings plus the ZS states. This is what TA-Lib on the coin's own bars, with daily
     dominance and the 4-hour block, can say.
   - **ALL**: every reading of this design.

   ALL minus TA is what cross-referencing the other data adds.
2. **Rows.** The scan's A entries with a valid label, about 376,000. No 2025 row is ever in a fit. There is no second
   check period and no tuning.
3. **Fit.**
   - LightGBM 4.5.0, L2 regression on the direction sign (−1, 0, +1), with init_score = A's base mean sign. A leaf is
     then a shift in mean sign (× 50 = odds points).
   - Settings, fixed here: 300 trees, max_depth 3, num_leaves 8, learning_rate 0.05, min_data_in_leaf 3000,
     lambda_l2 10, feature_fraction 0.5, bagging_fraction 0.5 every round, max_bin 15, max_cat_threshold 8, cat_smooth
     50, min_data_per_group 3000, deterministic, force_row_wise, 4 threads, seed 20261111 + H.
   - Zone, sign and breadth codes are ordinal (NA = missing). Clock, position, pattern and other categorical codes are
     categorical.
4. **The call as a reading.** `GBM.TA{H}` and `GBM.ALL{H}` (k = 1) are the model's score at every minute of both splits,
   in 5 zones at the A quantiles of the score.
   - They go through event_levels, level_events and g.full like any engine reading: singles at onset, and held
     states, in the league's units.
   - Their direction is measured (their own A odds), not assumed.
5. **Rules to triples.** The leaf paths feed Part 1 (b).
6. **Usage.** LightGBM's own per-row contributions (pred_contrib) on 20,000 seeded B minutes give the numbers below
   (review: the draft also used 20,000 A entries, but those are the rows the trees were fit on, and their neighbours
   share features and overlapping labels, so their contributions are in-sample; they are dropped). Contributions are
   the model's view, not evidence; the twins' contributions stand beside them:
   - the mean contribution of each reading level, in odds points;
   - the mean absolute contribution of each reading;
   - the mean absolute contribution of each TA function, with all of its timeframes and settings together.
7. **Twins.** Each twin gets the same models, rows, settings and readouts.
8. **Export.** The trees are exported as JSON (LightGBM dump_model), so the bot can evaluate the call without LightGBM.
   A test checks that the JSON gives the same score.

## What is reported
1. **Re-measure in the league's units.** In each series job, per horizon:
   - Take the best 200 confluence cells by each of oheat_B, iheat_B and lheat_B, plus the learner-path triples in the
     top 200 by the same measures.
   - Measure them again with g.full (g240.full at 240 minutes) on every minute, in two forms:
     - `xstate`: every minute the joint state holds;
     - `xonset`: the minute it starts to hold, a moment, like an event of the league.
   - The re-measure adds moves, best move, usual dip, touches, minutes held and retL (entered one minute later: the
     bid-ask bounce check of report s11).
2. **Heat.**
   - **oheat_B** = wd_B × odds_B·d: the cell's own call.
   - **iheat_B** = wd_B × iota_robust_B·dι: unseen confluence, how often × by how much the joint state beats its
     parts on both scales.
   - **lheat_B** = min(wd_B, rest_wd_B) × lift_min_B·d, with rest_wd_B = wd_B × rest_n_B / n_B (the pair pack's rule).
3. **Lists**, per coin and horizon (all six in the league; 15, 60 and 240 in the pack):
   - the 40 best by oheat_B, the 40 best by iheat_B and the 20 best by lheat_B;
   - at most 3 rows per reading in each list, with copies collapsed;
   - **near-copies collapsed (review).** Two candidate rows are the same event under two names when their B entry sets
     overlap by at least 80% (Jaccard, computed in the re-measure). Examples: "15m RSI14 low × X" and "15m RSI21 low × X",
     or the same pair seen through PERCENTB and ZSCORE20. The best keeps the row and the others become its aliases. HM1's
     Amendment 4 found such copies filling the top rows. This is a display rule, the same on twins, and no count
     changes.

   The only floor is the engine's sample: 30 entries on 30 days of A, and 30 on 20 days of B. The number of cells under
   the floor is printed. The marks are columns: hot on A, replicated on B, BHY at q 0.10 within kind and horizon (from
   a log-binned histogram of every cell's p, kept in the summary counts), and above the twins' max. That max is taken
   over the same list and slice of the three twins. Each listed row also carries move_steps_B (its re-measured B move ÷
   the price step) as a column, the HM1 price-step rule kept visible.
4. **The model call.** The GBM zone rows of both models are shown beside:
   - the twins' rows;
   - two baselines at matched windows per day: "bet against the last 1-minute candle" (what bid-ask bounce alone gives,
     which a coin-flip twin cannot rule out) and the league's best single level at that horizon;
   - ALL against TA.
5. **Lessons (TA-Lib usage):**
   - **Family table.** For each pair of families at 15, 60 and 240 minutes: confluence cells, and the share whose
     interaction kept its sign on B, minus the twins' share. The families are the vocabulary's types, pattern, context,
     position, clock, cross-coin, volatility, flow, perp, open interest, daily markets, macro and each inventory family
     found.
   - **A usage card per TA function.** It shows, each number beside the twins' median and range:
     - **how to read it (review):** a grid of its settings × timeframes (RSI 2/7/14/21 × 1m/5m/15m/1h ...). Each square
       gives the B odds of each zone in its A direction, whether the extreme zones fade or follow, and the horizon where
       it is strongest;
     - its own call by level (the direction league);
     - the model's mean contribution by level (B minutes);
     - **its best partner in each family (review)**: TA, cross-coin, volatility, flow, perp and open interest, position
       and clock, macro, dominance and daily markets. Each is ranked by iheat_B, with reading, level, direction and
       whether the partner strengthens the call or flips it (iota_with_call; a flip is a "stand aside" lesson);
     - the share of its pairs that kept their interaction, against the twins.
   - **Each coin's top rows in words**, in Eastern and UTC where a clock or position level is in the row, each with the
     twins' best number for the same list. For example: "15m RSI14 very high while BTC's last 5 minutes are very low:
     down, 57% right on 2025, 6 windows a day (twins' best: 53%, 4 windows)."
6. **Unseen slice (review: provenance only).** Every list is also shown for the cells with seen_in_league = none,
   ranked the same way. part_tmax stays a column. The draft's slice also required parts_hot = 0, which made a
   significance mark into a filter. The chance table splits its counts by part_tmax bin instead (Chance scale).

## Chance scale (beside every count)
**The twins.** Each coin gets seeds 1, 2 and 3 (make_twin(load_minutes(csv), seed), with the joint flip of the
Readings section), run with the identical command and --twin N. Everything matches the real run:
- the entries;
- the merge rule, applied to the twin's own codes;
- the triple choice, made on the twin's own A;
- the learner and its paths;
- the provenance labels (by reading names);
- the caps, the near-copy collapse and the re-measure.

**Per horizon, real against the twins' median and range:**
- confluence cells with a sample;
- the kept-direction share and the kept-interaction share (ι, ι_add and iota_robust). Across 12 million cells the
  kept-direction share mostly restates the singles (HM1's pair pack: 91.7% against 51%). The confluence evidence is
  the kept-interaction and lift shares;
- the share with t_ι_B ≥ 2;
- the persistence curve: the kept-interaction share by A |t_ι| bin (0-1, 1-2, 2-3, 3-4, ≥ 4), for all cells and by
  part_tmax bin (under 2, 2-3, 3 and over), so cells whose parts are quiet alone are seen as a stratum, not a filter;
- the 99th percentile and max of oheat, iheat and lheat;
- rows above the max of the coin's three twins;
- for the model call, the twins' GBM zone rows;
- for usage, the twins' mean absolute contribution per family.

A count is evidence only when it stands clear of the highest twin set. There are about 12 million cells per coin per
horizon, all correlated, so the twins' max is the yardstick, not t.

**What the twins cannot judge, and its guard (review).** A twin has no calls, so a ι that only reflects the scale of
two real calls would still stand clear of it. The guard is iota_robust (both scales must agree) and the planted
main-effects test (Tests, 4).

## Pack for the bot
The pack is research/oracle_heat/latest/hm2_pack.json (schema `oracle-heat-hm2-pack-1`, allow_nan False). It has its
own hm2_live_meta.json and does not touch live_meta.json or any other pack.

**Rows.** The lists of "What is reported" at 15 and 60 minutes (Kalshi 15-minute and hourly) and at 240 minutes (the
perp lane), plus the GBM zone rows. The fields are pair_pack.json's, plus:
- `kind` (pair, triple, model);
- `fire`: 'onset', the first minute close at which every condition holds, with entry at the next minute's open. The
  held numbers are columns.
- `conds` [[reading, [levels]]];
- iota_B, iota_add_B, iota_robust_B, t_iota_B, iheat_B, lift_min_B, lheat_B, iota_with_call;
- parts, parts_hot, part_tmax, seen_in_league, families, learner_path, aliases (near-copies), move_steps_B;
- retL_B, above_twin_max, iota_above_twin_max, live_ready.

**Pack level.** chance per horizon, the baselines, `models` {coin: {TA|ALL: {h: tree file, sha256, used readings}}}, and
the table hashes.

**hm2_live_meta.json.** Per coin:
- the price step;
- the zone edges of every reading behind a row: engine readings from meta.json, new readings from this run;
- the norm tables (RVclock, Busy);
- the other coins' edges that a cross-coin reading needs.

**live_ready.** A row is live_ready only when two things hold:
- The live reader computes its readings with parity on Dec 29-31, 2025, on at least 99.5% of minutes.
- The bot has its feed. Perp, funding and open interest need a Binance perpetual feed; macro needs a 2026 calendar;
  daily markets need their daily closes; Coinbase readings need a Coinbase minute feed.

The bot's heat_reader needs a loader for this schema behind its own switch, default off. That is the bot lane's work,
not this run's.

## Known limits
- **Many correlated cells.** There are about 12 million cells × 6 horizons per coin. The twins' max is the yardstick.
- **Optimistic top numbers.** The lists pick on one year (B), so their B numbers run high. The Kalshi test is the check.
- **ι's error, scale and redundancy.**
  - ι's SE ignores the error in the fitted parts.
  - Two readings that go together (high assoc) can show a sub-additive ι that only restates their overlap.
  - "More than the parts" depends on the scale. iota_robust needs two scales to agree, but a third scale could
    disagree with both. The twins cannot judge this (Chance scale).
- **The joint twin.** It keeps each minute's co-movement of the four coins but not the real lead-lag between them
  (that is the signal). Real levels (basis, funding, open interest, dominance, daily markets) are shown beside a flipped
  path, so their cells fill a little unlike the real coin's.
- **Provenance from packs chosen on 2025.** HM1's packs were ranked by B heat, so the "none" slice leans away from
  cells whose parts were strong on B. It is a label of what the bot already has, not a clean split.
- **The A stride** cuts A's power to a seventh. This matters most at 1 and 5 minutes.
- **What twins cannot catch.**
  - Twins break only the direction of the price paths. A leak in a context file would pass them; only the cut tests
    and the known-time rules catch it.
  - Coin-flip twins do not reproduce bid-ask bounce. The last-candle baseline and retL are the guards, and outcomes are
    last-trade prices.
- **The learner.**
  - Greedy trees miss pure XOR states. The scan covers those for pairs.
  - Leaves after the first trees fit residuals, so a path's own numbers can understate its role.
  - It splits on 5-zone codes only. Finer thresholds are missed, but every rule can be read live.
  - The GBM reading's A numbers are in-sample: a seventh of A's rows trained it, and the rows between share features
    and overlapping labels. B is its check.
- **Data.**
  - Whether the perp, funding, open-interest, BTCDOM, Coinbase and order book files are on Drive is unchecked (the
    inventory decides, with a written note).
  - Open interest starts Sep 2020 (BTC) and Dec 2021 (ETH, SOL, XRP); BTCDOM starts Jun 2021. Their cells have fewer A
    days.
  - Daily markets read a day-old close (stamp + 24 hours), so they are slow context, never a trigger.
  - 2025 has 32 release days and 8 FOMC days, so macro cells pool or fall under the floor.
  - Some 2025 releases were rescheduled at short notice after the shutdown.
  - SOL starts 2020-08-12.
  - The data is Binance spot only. Live bars from Coinbase agreed with Binance about 91% of the time in an earlier
    check.
- **Overlap.** Held-state cells overlap. Heat counts windows, and t is clustered by day.
- **Estimates and space.** Compute figures are estimates until the bench job reports. Review estimate of the cell
  shards: about 12 million cells × 2 splits × 6 horizons × about 16 float16 numbers is 3-6 GB per series. Sixteen
  series would be 50-100 GB, not the draft's 8-16 GB, and a runner has about 14 GB of free disk. So only the four real
  series write shards (12-24 GB on Drive). The twins run the identical search and keep only the small files
  (summary counts, histograms, candidates, re-measured rows). The chance scale reads nothing else.

## Compute and job plan
**Per series (one coin or one twin), estimated.** The bench job measures it first.

| stage | time | memory |
|---|---|---|
| own and three other coins' minutes, labels (60 and 240 grids), engine readings | 8 min | 4.5 GB |
| new readings, the other coins' RSI14 and TakerBuy, merge, entry code matrix | 6 min | +1.5 GB |
| pairs (about 900,000) on 4 fork workers | 25-75 min | |
| learner: 10 fits, calls at every minute, contributions | 15 min | +1.5 GB |
| triples (about 165,000) | 10 min | |
| re-measure (about 3,600 cells × 2 forms), writes, Drive put | 12 min | |
| **total** | **75-125 min** | **peak about 9 GB** |

Notes on the estimate:
- The pair range runs from A's measured rate without the neutral-level shortcut (75 min) to the expected rate with it.
  The timing covered the bincounts only. The windows bitmask (6 horizons), the two fits and the day-clustered t per
  cell are not in it, so the bench decides.
- The other coins' RSI14 and TakerBuy are computed directly with the engine's steps (review). heat_live.tf_codes would
  build the whole 1-minute vocabulary three times over (about 10 more minutes and 2-3 GB at its peak).
- The memory figure comes from the HM1 twin jobs (3.7-4.2 GB for the base) plus the uint8 entry code matrix (900,000
  entries × about 1,420 readings = 1.3 GB) and the learner's binned rows.
- **If the bench projects more than 300 minutes per series (review).** A hosted runner job cannot run longer than 360
  minutes, so the timeout cannot be "raised" past that. Each series then splits its pair list into S parts by pair
  index (`--part i/S`; the same split on twins). The summary counts and candidate heaps merge exactly in the league.
  Jobs grow to 16 × S, still at most 9 at once.

**Jobs** (ubuntu-latest, 4 vCPU, 16 GB):
- `test` (20 min): pytest, then a Drive preflight. It runs the source inventory (Data), checks every time column is
  milliseconds, checks the funding stamp convention, and checks Drive's free space: at least 3 × the bench's projected
  shard total, and 40 GB before a bench exists. Anything missing stops the run.
- **One study at a time (review).** A tagged run's own concurrency group means a second tagged push would run beside
  the first: 18 series jobs, over the 10-job limit. The plan step therefore stops when another oracle-hm2 run is in
  progress (gh run list --workflow oracle-hm2.yml --status in_progress).
- `series` (timeout 330 min): asset × twin 0-3 = 16 jobs, max-parallel 9, so at most 10 run at once with any CI. The
  include list puts the four real coins first, and every job runs under /usr/bin/time -v and logs free disk after each
  stage.
- `league` (60 min): runs if !cancelled(). It reads only the small files of each series (summary counts, candidates,
  re-measured rows, usage, trees, meta), warns when a twin set is missing, and commits the pack.

**Wall time.** Two waves of about 75-125 minutes, plus test and league: about 3 to 4.75 hours. A bench run comes first:
BTC only, the base, 3,000 random pairs and one learner fit, about 30 minutes. It reports ms per pair and peak memory,
and the series timeout is checked against it.

## Files and workflow tag
**New files only:**
- `python/oracle/heat_xdata.py`: loaders for the perp, funding, open-interest, daily-market, calendar and inventory-found
  files; the joint twin flip; the new readings; their live levels (levels_at).
- `python/oracle/heat_hm2.py`: the scan, the learner, the re-measure, the league and the pack. CLI: `coin`, `bench`,
  `league`, `parity`.
- `python/oracle/calendars/macro_calendar_2020_2025.csv`
- `python/oracle/requirements-hm2.txt`: requirements.txt plus lightgbm==4.5.0.
- `python/oracle/tests/test_heat_hm2.py`
- `python/oracle/prereg/OR-HM2.md`: this text, committed before any HM2 code runs on real minutes; results appended
  after.
- `.github/workflows/oracle-hm2.yml`

**Workflow trigger and tags.** It triggers on a push to claude/project-thread-kw7bc3. The tags go in the head commit's
message:
- `[heat-hm2-bench:43030435253]`
- `[heat-hm2:43030435253]`
- `[heat-hm2-league:43030435253]`
- `[heat-hm2-parity:43030435253]`

A tagged push gets its own concurrency group (oracle-hm2-<run id>), so later pushes never cancel it. Nothing runs rm -rf
on research/oracle_heat/latest.

**Where outputs go:**
- Drive, per series: models/oracle-heat/runs/43030435253/hm2/<COIN>[-twinN]/. It holds the summary counts,
  candidates, heat.csv.gz (re-measured rows in the tables' format), usage, trees and meta.json (schema
  `oracle-heat-hm2-1`, with table_sha256), and for the real coins only, the cell shards.
- Drive, league: .../hm2/league/.
- Branch: research/oracle_heat/hm2/ (league.md, summary.json, usage.md, trees) and research/oracle_heat/latest/
  (hm2_pack.json, hm2_live_meta.json).

## Tests (synthetic minutes, patched SPLITS, procs = 1)
1. **Cut the future.** For every new reading (cross-coin, perp, funding, open interest, daily markets, inventory
   families and macro included), the ZS states, the learner features and the GBM score, the codes at rows ≤ t stay the
   same when the inputs after t are replaced by noise. Each input is replaced alone (own coin, each other coin, perp,
   funding, open interest, each daily series, calendar) and all together. Checked at 5 cut points. A cross-coin code
   at own row i equals the other coin's code at the same UTC minute (offset sign tested with a later-starting coin).
2. **Entry-minute states and refusals.**
   - Position and clock codes at row i are those of minute i+1.
   - An unscheduled FOMC statement has no "before" level, and its day is not a release day before its own minute.
   - Funding is unknown until calc_time + 1 minute; open interest until create_time + 5 minutes. A funding file
     stamped at the start of its period fails the stamp check.
   - A daily bar stamped 23:00 UTC on day D is not used before 23:00 UTC on day D + 1.
   - A time column in seconds or microseconds is refused.
   - An extra file with a row at or after HEAT_END is refused, and DOGE is refused.
   - Every CPI, jobs and PPI row is a weekday at 08:30 ET; every scheduled FOMC row is at 14:00 ET.
3. **Counts.**
   - The packed bincounts equal g.cells on the sign track to 1e-9.
   - The neutral-level shortcut equals a direct count exactly.
   - The window bitmask equals the np.unique count.
   - The t equals heat._clu on the same entries.
4. **The fit.**
   - An exactly additive table gives |ι| < 1e-6 (and an exactly additive mean-sign table gives |ι_add| < 1e-6).
   - A planted XOR with flat margins gives ι, ι_add and iota_robust > 0 while both parts have |t| < 2.
   - **Planted main effects, no joint term (review).** Two associated readings each with a real call, once additive
     on the probability scale and once multiplicative in the odds. The kept-interaction share of iota_robust on B is
     within 0.45-0.55, and no iheat row is above the twin's max.
5. **Planted signals, end to end.**
   - A planted pair XOR ranks first on iheat and replicates on B.
   - A planted three-reading AND (1m RSI14 very low, POS:QPos m14, X.BTC:R5z very high) appears as a learner path and is
     measured as a triple with ι3 > 0.
   - On twin 1 neither stands above the twin's own 99th percentile.
6. **Pure noise** (a plain random-walk coin and its twin):
   - the kept-interaction share on B is within 0.45-0.55;
   - the sd of t_ι on A is within 0.85-1.2;
   - at most 5% of rows beat the twin's max;
   - the GBM zones have |t_B| < 3.
7. **Twin, learner and JSON.**
   - The twin's own bars equal heat.make_twin(m, seed). The other coins' bars on a common grid carry the same flips
     minute by minute. The real levels (basis, funding, open interest, dominance, daily markets, macro, position,
     clock) equal the coin's, and the twin builds its own TA edges, equal to HM1's twin meta.
   - Provenance labels are the same on the coin and its twin.
   - Two learner fits are equal bit for bit.
   - The tree JSON reproduces LightGBM's scores to 1e-9.
   - JSON is written with allow_nan False and has the schema keys.
8. **Grids.**
   - The main grid's zone edges equal the engine's.
   - The 240 grid's A rows end 240 minutes before 2025.
   - heat.HORIZONS and heat.HMAX are restored after the 240-minute block.

## Unchanged
- heat.py, and the stored tables, hashes, league and packs of run 43030435253.
- The data cut (no 2026 minute), the entry (next minute's open), the dead band (1.5 price steps), the twins (seeds 1-3),
  the sample floors, NEVER DOGE.
- A map on coin price, not a validated rule.

## Next (not this run)
- The one test on Kalshi prices: the 1-minute hold of the called side against random entries. Its batch is fixed in
  the registry before the read.
- The untried ideas of report s12 that are not oracle inputs: mid-price rescoring, outcomes on Coinbase, fair-value
  volatility.
- A second pass with the premium index (if it is fetched), the long/short ratios, and zone-side states in the scan, if
  the learner shows the ZS states matter.

## What the review changed (adversarial review, 2026-11-11 ~23:30 UTC, 6:30 PM EST; before any HM2 code or result)
1. **Leaks closed.** Every time column must be milliseconds: a file in seconds would pass the awk cut with its 2026
   rows. Daily markets are known only from stamp + 24 hours; HM1's day rule would read DXY, US10Y and FX bars about
   22 hours early. Funding is used at row i only when calc_time ≤ the open of minute i, and its stamp convention is
   checked against the basis. Open interest is known from create_time + 5 minutes. An unscheduled FOMC day is not a
   release day before its statement, and the three unscheduled statements keep their own times.
2. **Cross-reference all data.** Added open interest (3 readings) and 13 daily markets. Added a source inventory: every
   source found on Drive or in research/btcd_fractal/data feeds a family or gets a written reason, and BTCDOM
   hourly, Coinbase minutes and order book snapshots are used if found. The monthly and weekly macro series are
   excluded because their stamps are not release times.
3. **Twins.** One joint coin flip for all four coins (and the perp and Coinbase paths), so cross-coin cells fill as on
   the real coin. Twin edges are asserted against HM1's <COIN>-twinN meta; the draft's check against <COIN>/meta.json
   would have stopped all 12 twin jobs.
4. **Interaction scale.** Added ι_add (additive on the mean-sign scale) and iota_robust (both scales agree). iheat, dι
   and the triple choice use iota_robust, and a planted main-effects test was added. Twins cannot catch a ι that only
   reflects the scale.
5. **Owner's rules.** The unseen slice no longer filters on parts_hot (a significance mark). It is provenance only,
   and part_tmax becomes count strata.
6. **"Unseen" fixed.** seen_in_league now means the part is in a pack the bot loads or the pair was stored in HM1. The
   draft matched against direction_all, which lists every level, so its "none" slice would have been nearly empty.
7. **Copies under two names.** Near-copy rows (80% of B entries shared) collapse into aliases in the lists.
8. **No in-sample usage.** Learner contributions come from B minutes only, beside the twins' contributions.
9. **Teaching TA-Lib.** Each usage card gets a settings × timeframe grid (fade or follow, best horizon) and a best
   partner per data family, with stand-aside flips. Rows in words carry the twins' best.
10. **Compute.** Only real coins write cell shards; the draft's 8-16 GB was about 50-100 GB for 16 series. A series
    over 300 minutes splits its pairs across jobs, because the timeout cannot pass 360 minutes. The other coins'
    RSI14 and TakerBuy are computed directly, and only one tagged study runs at a time (10-job limit). BHY comes from
    a p histogram, and move_steps_B is a column.
