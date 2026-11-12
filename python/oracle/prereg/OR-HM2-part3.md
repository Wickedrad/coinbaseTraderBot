# OR-HM2 Part 3: what separates the winners (design, written before any result)

Written 2026-11-11 ~23:55 UTC (6:55 PM EST). An addition to OR-HM2 (python/oracle/prereg/OR-HM2.md and the build plan
/mnt/project-files/direction-research/oracle-hm2/OR-HM2-build-plan.md). It adds one module, its tests, jobs in the HM2
workflow and rows in the HM2 league and pack. It changes no line of heat.py, of the HM2 design or of the HM2 modules
being built, and no stored table, hash, league or pack of run 43030435253.

Steven, Nov 11 23:33 UTC (6:33 PM EST): "Also with the data so far for the Oracle taught TA curves we should be asking
what is the difference between the instances of one particular pattern or TA or whatever it happens to be that is right
more often and/or makes more in profit than the ones that don't. Whatever that parameter may be should be investigated
further for each column or row that ends up displaying this difference."

The standing rules stay as they are. NEVER DOGE. Coin minutes 2020-01-01 to 2025-12-31 only: choose on 2020-2024 (A),
score on 2025 (B), and no minute of 2026 is loaded. No pass bar cuts a unit, a parameter or a level: rank, and show the
no-signal twins beside every count as the chance scale (sample floors only; marks are columns). No sealed test weeks.
Heavy compute runs on GitHub Actions runners (at most 10 jobs at once, 360 minutes per job), never on the bot server.
Times in Eastern and UTC. Study every loser. A part that wins only under some conditions is kept and gated to those
conditions ("add dynamics"); it is never cut unless it is invalidated.

## What had been seen when this was written
- The league of run 43030435253: 19,055 event levels with a sample on both periods (4,926 to 4,939 per coin pass the A
  floor); direction kept on 2025 in 70-79% of them by horizon, the twins 50%.
- The pair pack: cells hot on A only; the lift over the trigger's other events kept its sign on 2025 in 69.2% (15 min)
  and 64.8% (60 min) of cells, the twins 50.0%.
- The clock add-on (adds little), the long horizons (240 minutes kept direction 69.6%, twin 51.1%).
- The packs the bot loads: traded_pack 480 rows (409 coin-key units), pair_pack 447 (438), clock_pack 377 (333),
  perp_pack 467 (462), perp_pair_pack 430 (430).
- The research report (/mnt/project-files/direction-research/report.md), the bot's exit and fee settings
  (.env.example: hold exit at +$1.50 net, ratchet arming at $1.50, stake $10-20, perp taker fee 12 bps a side, perp
  stop 2 x ATR and at least 50 bps).
- The HM2 design. No HM2 code has run on real minutes, and no Part 3 code exists. No number in this text is a Part 3
  result.

Where an earlier result shaped a choice, this text says so: the cap on build-year instances per unit (point 6 of
Units) exists because the 1-minute levels carry most of the instances; the pack horizons 15, 60 and 240 are the ones
the bot trades. Two ideas of the report's "not tried" list are special cases of this study and are measured for every
unit, not chosen: "keep only fades of taker-driven stretches" (the flow readings as separators) and "pause fades around
news" (the macro readings as separators).

## The question in the engine's terms
A call of the league fires many times. Some of its instances are right and some are wrong; some make money under the
bot's exit and some do not. Steven asks what differs between the two groups, at the moment of entry, and wants every
column that shows a difference followed further.

HM1 asked this once, narrowly. Its pair stage split 170 triggers per coin by every TA reading, and stored a
relationship only when a cell was hot on A. HM2's scan crosses states with states at sampled minutes, not the
instances of a call. Neither looks at every call, at the new data of HM2, at features of the instance itself (how
deep inside its zone, how long since it last fired, first or repeat), or at profit as an outcome. Part 3 does, for
every call, with nothing gated.

## Units (requirement 1)
1. **A unit** is one call: a coin and an event key that fires at a minute close. Its **instances** are the minute
   rows where it fires, with entry at the next minute's open, exactly as the league measured it. Every unit is studied
   at the six horizons 1, 5, 15, 30, 60 and 240 minutes (one pass gives all six). 1440 minutes is not studied (it is
   context, not a trigger).
2. **Kinds of unit:**

| kind | fires at | source | units |
|---|---|---|---|
| HM1 event level | heat.level_events of the level (onset, side-aware; a pattern every bar it fires) | league direction table of run 43030435253 (main and long) | 19,055 |
| HM1 pair or triple cell | the trigger's event while every condition holds its level at its last closed bar (the pair pack's fire rule) | pair_pack, clock_pack, perp_pair_pack (240-minute rows) | about 970 |
| HM2 cell or model zone | the onset of the joint state (HM2's xonset); a GBM zone through event_levels | hm2_pack.json, once HM2's league has written it | about 1,000-1,300 |

   Singles already in traded_pack or perp_pack are HM1 event levels and are not counted twice. In all, about 21,000
   units, about 5,300 per coin, plus Part 4's chart events if Part 4 has landed (Candidate parameters, below).
3. **Copies run once.** Keys that are the same event under two names (identical instance rows, as in HM1's aliases)
   run once and carry their aliases.
4. **Direction.** For each unit and horizon, d = the sign of the unit's odds on A over all its A instances: its A mean
   sign minus the base mean sign of split A at H (the 240 grid's base at 240). That is the league's rule
   (heat._direction reads d_odds, the odds over the base, not the raw mean sign; review). An exact 0 is +1 and flagged.
   Every outcome below is read in d, and every B number is signed in it. For HM1 units the job checks that d equals
   the league's direction and prints the count that differ (expected 0).
5. **Twins.** Each twin runs the same unit list by key: the twin's own events of the same level, its own conditions,
   its own A direction. So every real unit has a like-for-like chance unit.
6. **Cap on A instances (compute, fixed now).** A unit with more than A_CAP = 25,000 instances on A keeps a seeded
   uniform sample of 25,000 (seed from the key, the same on twins and reruns); every unit keeps all its B instances.
   Directions, quintile edges and the "time since" and "order" parameters use all A instances. The cap touches mainly
   1-minute levels, which fire tens of times a day; 25,000 instances still give a share-right standard error near 0.3
   points for an even split. It is a compute cap, not a pass mark.
7. **Order, and how all units are covered.** The unit list is fixed once, in this order:
   - tier 1: the calls the bot loads now (traded_pack, pair_pack, clock_pack, perp_pack and perp_pair_pack at 240);
   - tier 2: the HM2 pack's rows (after HM2's league);
   - tier 3: every other event level, in the order of HM1's heat on A at 15 minutes (A numbers only, review: if a
     block were ever missing, B would have played no part in which units ran). This order selects nothing.

   A series job processes the list in blocks and writes each block when it finishes. If the bench projects more than
   300 minutes per job, the list is split into S parts of equal instance count, tier 1 first, and the part-1 jobs of
   all 16 series run first. So the bot's calls and their chance scale finish first. The league lists, per series, the
   blocks done and warns about any missing; a missing block is rerun with `--blocks`. No unit is left out.

## Outcomes per instance (requirement 2)
All from the engine's labels (entry o[i+1]; the 60-minute grid for 1 to 60, heat_long's 240-minute grid for 240; a
row counts at 240 only if it is a valid row of that grid).

| outcome | definition |
|---|---|
| right / wrong / flat | the sign of the move to H in d; a move within 1.5 price steps is flat (the engine's dead band) |
| move | d x ret_H, in bps toward the call |
| best favourable move | d > 0: up_H; d < 0: -dn_H (bps) |
| worst adverse move first | the usual dip before the best point: d > 0: dipU_H; d < 0: -dipD_H (bps, the loser-cut view) |
| minutes held | d > 0: holdU; d < 0: holdD (consecutive minute closes beyond the dead band on the called side; 0-60, and 0-240 on the 240 grid) |
| profit proxy pi | below (bps after cost) and pi_c (cents per contract at 50c) |

**The profit proxy.** It copies the bot's exit on coin minute closes: sell at the first profit after a fee-sized move,
cut losers early, otherwise leave at the horizon.
- **Cost.** A Kalshi round trip with an early exit costs about 4.5c at 50c (taker fee 1.75c each way and a 1c spread;
  report, "What it costs"). An at-the-money binary with tau minutes left moves about 40c per sigma x sqrt(tau) of coin
  move (report, "The digital-option maths"). So cost_H = 4.5 / 40 x sigma x sqrt(tau) bps, where sigma is the sd of
  1-minute log returns over the 1,440 minutes ending at the decision close (known at entry), tau = 10 minutes for the
  15-minute contract (H = 1, 5, 15) and 30 minutes for the hourly contract (H = 30, 60): the middle of the bot's entry
  windows (840-300 s and 3,300-600 s before close). For BTC at 2025's daily volatility (sigma about 6 bps), cost is
  about 2.1 bps at 15 minutes and 3.7 bps at 60.
- **Take.** F = 2 x cost_H, and at least 2 price steps. The hold exit sells at +$1.50 net of both fees; on a $15-20
  stake at 50c that is the contract moving about twice the round-trip cost.
- **Cut.** C = 2 x cost_H, and at least 2 price steps: the bracket is symmetric, about 9c at 50c, inside OR-H3's
  3-20c grid. Steven's spec: "cut losers early".
- **Rule.** Walk the minute closes c[i+1] .. c[i+H] as x_j = d x (c[i+j] / o[i+1] - 1) x 1e4. The trade ends at the
  FIRST j where x_j >= F (a take) or x_j <= -C (a cut), whichever comes first; if neither, it exits at x_H. (Review:
  the draft searched the whole path for a take before looking for a cut, so a take late in the window hid an earlier
  cut: an outcome read past the exit.) pi = exit move - cost_H. Closes, not highs and lows: the hold exit needs the
  profit to last (10 s, the last 3 s in a row), and the owner's test is "sustaining for at least 1 minute". H = 1 is
  one close: pi = x_1 - cost.
- **240 minutes (the perp lane).** No take (the heat perp setups have no target and no trail), a stop at C = the larger
  of 50 bps and 2 x the 4-hour ATR14 (Wilder) at entry (PERP_STOP_ATR_MULT, PERP_MIN_STOP_BPS; 4-hour bars aligned to
  00/04/08/12/16/20 UTC, the last completed one), else exit at the 240-minute close; cost = 2 x 12 bps + 1 bp spread =
  25 bps. The stop is exchange-side and fills inside the minute (.env.example), so it is checked on each minute's
  adverse extreme (the low of a long, the high of a short) and filled at the stop, or at the minute's open when the
  minute opens beyond it (review: closes would miss stops that the bot takes).
- **Exit kind** per instance: take, cut or time. pi and the kind depend only on (row, H, d), so they are computed once
  per series for both directions (about 3.2 million rows x 6 horizons x 2) and looked up per unit.
- **How it maps to Kalshi later.** pi_c = pi x 40 / (sigma x sqrt(tau)) is the proxy in cents per contract for an
  at-the-money contract, its gross part clipped to +-50c (a contract near 50c cannot move further), so pi_c lies in
  [-54.5, 45.5]; it is a measure, not a price. The proxy ignores the contract's own clock (windows start at the
  event, not at :00/:15/:30/:45), the 60-second settlement average, the spread away from 50c and the quote's own
  reaction to the coin (the papers in the report find the mid already holds most of it). So it ranks; it does not price.
  The later one test on recorded Kalshi asks (since the Nov 10 order-book fix) takes the gated call and the same call
  ungated on the same contracts, with the plan exits, against random entries.
- **Which unit the profit track ranks (review).** At 1-60 minutes (the Kalshi lanes) the profit track ranks pi_c; at
  240 (the perp lane, P&L in bps of notional) it ranks pi in bps. In bps, a level that only picks high-volatility
  minutes raises the mean of any call that has an edge (the same odds on bigger moves) without separating its
  winners, and every volatility reading would head the profit lists of every call. A Kalshi contract pays in cents
  per sigma of coin move, which pi_c measures. pi in bps stays a column at 1-60.

## Candidate parameters (requirement 3)
Every column known at the decision close of the instance, read at the instance row with heat.read_state (the last
closed bar of the parameter's own timeframe at or before the row's close). About 1,440 per unit.

| family | parameters | levels |
|---|---|---|
| Engine readings | the 1,350 readings of build_readings (624 zone, 408 sign, 68 two-state and categorical, 244 candlestick, 6 context), after HM2's copy merge | their own levels |
| HM2 new readings | position (QPos, QPhase, HourQ), clock (UTC1h, NY30m, Weekday), cross-coin (21 per job plus Breadth5/15), volatility (9), flow (7), perp (6), open interest (3), daily markets (13), macro (3), and the inventory families found (up to 6): HM2's table, same code, same edges | their own levels |
| HM2 model call | GBM.TA{H} and GBM.ALL{H} for H in 1, 5, 15, 60, 240 (10 readings, 5 zones) | trained on A rows, so in-sample on A: ranked in the in-sample list (below), never in the main ranking |
| Own: depth | OWN:Depth: the event's own raw value inside its zone (how extreme), at the A quintiles of the unit's own instances. For a sign flip, the raw value after the flip. For a pair or HM2 cell, one Depth per value-reading condition. NA for two-state readings and single-valued patterns | 5 |
| Own: time since | OWN:Since: bars of the unit's own timeframe since its previous instance: 1, 2-3, 4-10, 11-30, 31-100, over 100, none | 7 |
| Own: order | OWN:Order: the unit's instances in the 30 bars of its own timeframe before this one: 0 (first), 1, 2, 3-5, 6 or more | 5 |
| Own: last outcome | OWN:Last@H: the outcome in d of the unit's previous instance whose window had closed (row r with r + H <= i), within the last 1,440 minutes: right, wrong, flat, none | 4 |
| Own: company | OWN:Coincide: how many other event levels of the coin fire at the same close (0, 1-2, 3-5, 6-10, 11-20, 21 or more; the unit and its aliases left out). OWN:Agree@H: those levels' A directions at H that agree with d minus those that disagree (5 or less against, 4-2 against, 1 against to 1 for, 2-4 for, 5 or more for). The directions are the ones this job computes for every HM1 level on its own A instances (the same procedure on a twin, which has no league table; on a real coin they equal the league's, checked). Agree is in-sample on A (each co-firing level's A direction was fit on outcomes that include this very minute) and goes to the in-sample list | 6, 5 |
| Own: the bar | OWN:BarRange (range of the event bar in its own timeframe / that timeframe's ATR14), OWN:BarVol (its volume / the mean of the 20 bars before), each at the A quintiles of the unit's instances; OWN:BarBody ((close - open) / range: -1 to -0.6, -0.6 to -0.2, -0.2 to 0.2, 0.2 to 0.6, 0.6 to 1) | 5 each |
| Own: price step | OWN:Step: the coin's price step in bps at the minute, at the A quintiles of the unit's instances (the rounding regime) | 5 |

Rules:
- A unit is never split by its own reading or the sign reading of the same series (one base, the engine's rule). For
  a pair or triple, by none of its readings' bases. The same indicator on another timeframe is a parameter.
- NA ("no reading": stale after a gap, before a file starts, OI before Sep 2020 or Dec 2021) is its own column in every
  table but never a winner level, and it is left out of "the rest".
- **The in-sample list (review).** The 10 GBM readings and OWN:Agree@H are ranked per unit in a list of their own
  (same kernel, same z_adj), and every one of them is scored on B. They never take a place in the main A ranking, the
  top-5 drill or depth 2: fit on A, their A z_adj would be inflated and would push honest parameters out of the
  drill. Their B numbers are clean and sit beside the main list's.
- **Left out, with the reason:**
  - the entry open versus the signal close (gap1): it is known only at the entry, not at the decision close;
  - membership of a pack: the packs were ranked on 2025, so a pack-based parameter would carry B into the choice on A;
  - HM2's learner-only ZS states: they restate the zone state plus "just entered", which Since and Order measure for
    the unit itself (about 624 more parameters for little new information);
  - funding, open interest and daily-market levels not yet known at the row (HM2's known-time rules apply unchanged).
- **Part 4's chart readings** (OR-HM2-part4-patterns.md, designed beside this text for this drill). If Part 4 has
  landed when Part 3 runs, its readings join through the same loading path: its event readings
  (`{k}m:CHART.{frame}.{P}`, 'every') give units of kind "chart event" (tier 3, after the HM1 levels; tier 2 if a pack
  holds them), with the same sample floors; its state, STRUCT, BIAS and ANY readings (about 400 per coin) are
  parameters; and its pattern parameters (`{k}m:CHART.{frame}.p.<name>`: height, span, sym, slope, pre, bvol, bdist,
  tdist, age) are the chart units' own columns, so a pattern's instances are split by their own shape. This adds about
  a third to the parameters and to the scan's time; the bench measures it. If Part 4 lands later, its units and
  parameters run as a follow-up with `--units chart`, with a note here first. Part 4's readings join only after Part
  4's own no-lookahead test has passed (a chart pattern confirmed bars after its first bar must be dated at the
  confirming close).
- **Finer values for the drill.** Every value series behind a zone reading (engine and HM2) also gets a 200-bin code
  (its A quantile in steps of 0.5%), uint8 per bar, built with the engine's own steps (tick units, resample, stale
  masks, A-only edges). The drill's curves read it. The zone code obtained from it at the ZONE_Q edges equals the
  engine's (a test). The other coins' X.O:RSI14 and X.O:TakerBuy are bucketed inside heat_xdata from O's own edges
  (no raw series reaches this job), so their curves use their 5 zones.

## The separation test (requirement 4)
Chosen on A only. Per unit, horizon and parameter, per known level l of the parameter (with "rest" = the unit's
instances at the parameter's other known levels):

**Three tracks**, each a lift of level l over the rest with a day-clustered and a week-clustered t:
1. **right**: odds = 50 x (share right - share wrong), in the league's odds points. Share right, share wrong, share
   flat and share right among decided instances are columns. The ranking uses odds, not share right, because a
   parameter that only removes flat outcomes (high volatility) raises share right and share wrong together without
   making the call any better.
2. **move**: mean move toward the call, bps.
3. **profit**: mean pi_c at 1-60 minutes (cents per contract after cost), mean pi at 240 (bps after cost); the other
   unit beside it (Outcomes, "Which unit the profit track ranks").

Each lift has a day-clustered t computed with the algebra of heat.Grid.cells' lift (each day's influence on the level's
mean minus the rest's mean) and the effective number of days (heat._clu); its p uses the t distribution with the
effective days minus 1, as the engine does.

**Week clusters too (review).** Slow parameters (daily markets, funding, open interest, BTCDOM, the volatility regime)
hold one level for days to weeks, and 240-minute windows cross midnight, so neighbouring days are not independent and
a day-clustered t overstates them: they would crowd the top of every unit's list. Each lift also gets a week-clustered
t (the same algebra on 7-day blocks of the unit's day axis: 261 blocks on A, 53 on B). z_adj, the ranking and the marks
use the smaller |t| of the two, with that clustering's count minus 1 as degrees of freedom; deff (fourth powers) is
computed exactly for the top 25 of each list and shown. For a fast parameter the two t agree.

**Summary score per parameter.** For each track: the best level's lift t made comparable across parameters with
different numbers of levels: z_adj = the normal z whose two-sided p is min(1, L x p), where p is the level's two-sided
p and L the parameter's levels with a sample (Bonferroni inside the parameter, so NY30m's 48 levels get no free
chances over a sign reading's 2). The best level with a positive lift is the
parameter's **take gate** (fire only there); the best with a negative lift is its **skip gate** (no entry there, a
loser cut). Each has its own z_adj. One summary score per parameter and track: sep_A = the larger of the two, with the
mode named.

**Ranking on A.** Per unit, horizon, track and mode, all parameters except the in-sample list are ranked by z_adj on A
(the in-sample list is ranked the same way, apart). The level must have 30 instances on 30 days of A and so must the
rest (the engine's floor); levels under it are counted and shown, not ranked. The kernel gives B numbers for every
parameter (A and B share one key), so the shards and the persistence curve hold every parameter, not only the top 25.

**Scoring on B.** For the top 25 parameters of each list (A's order), with A's winner level fixed:
- B: n, days, effective days, the level's odds / move / pi and the rest's, the lift signed in A's mode, its t;
- kept = the lift kept A's sign on B;
- windows per day of the level and of the rest (B), and the gate heat, gheat_B = the smaller of the two x the signed
  lift (windows per day x odds points, x bps for move, x pi_c cents or, at 240, bps for profit), the pair pack's
  lheat rule;
- what the gate does to the call: the gated call's odds, pi and windows per day on B against the ungated call's.
B numbers need 30 instances on 20 days of B; thinner rows are flagged "thin", not dropped.

**Is the separator about this call or about the market?** If level l is itself a call (for example "BTC's last 5
minutes very low" pushes every coin up), it lifts every up call in the same way. Column specific_B = the gate's lift on
B minus the same level's lift over all B minutes (the reading's own effect by level, over the rest of its levels), in A's
mode. Near zero: the separator restates its own call (still usable, but it is a pair, HM2's ground). Positive: the
level separates this call's winners more than it moves the market. A column and a stratum of the chance table, never a
filter. Own parameters have no all-minutes version: NA. Review: HM2's part_effects holds the sign track only, on its
entries, so the drill computes the all-minutes lift itself for all three tracks (right, move, profit) on every valid
B row of the coin from the labels and the proxy table, signed in d; part_effects is the check on the right track.
specific_A is the same on HM2's A entries (every 7th valid row).

**No significance gate.** z_adj, t and the marks (above the twins' max, kept on B, t_B >= 2) are columns and orders.
Every parameter keeps its row in the real coins' shards. The twins run the identical procedure (same units by key, same
cap, same seeds, same floors, same ranking) and are shown beside every count.

## Investigated further: the drill (requirement 5)
"Shows a difference" is read as a rank, not a bar: the drill runs on A's top parameters of every unit. Sample floors
only.

**(a) The finer curve.** For A's top 5 parameters of each list (unit, horizon, track, mode; about 40 distinct
parameters per unit): the parameter's value against the outcome. A value parameter is binned at the deciles of its
200-bin code among the unit's A instances (equal counts on A; B uses A's edges); a categorical one by its own levels
(NY30m and UTC1h with their Eastern and UTC labels). Per bin, A and B: n, days, share right / wrong / flat, odds, move,
pi, take / cut / time shares, minutes held, best favourable and worst adverse move, and the zone edges marked. This shows
where along the value the difference sits (a threshold, a slope, only the tail), which the 5 zones cannot.

Review, for Steven's "each column or row that ends up displaying this difference": every parameter in the top 25 of
any list (main or in-sample) that shows the difference on B (kept, with t_B >= 2 in A's mode) also gets its curve,
marked `drill = 'B'`. It was picked on B, so its B curve is not an out-of-sample check and it is not counted in the
chance table; the A-chosen top 5 (`drill = 'A'`) remain the test. Curves are bincounts on the unit's instances, so
this costs little.

**(b) Depth 2.** Inside the take gate of the right and of the profit track at 15, 60 and 240 minutes (A's top 1;
deduplicated, at most 6 per unit, usually 2-3): the unit's instances at the winning level, split again by every
parameter with the same kernel. Ranked on A by z_adj; the top 5 are kept with A and B numbers; the top 1 is the depth-2
path "unit, p1 = l1, p2 = l2", scored on B against the depth-1 gate's other instances and against the call. It needs
300 instances on 30 days of A at the winning level; units below are counted.

**Why depth stops at 2:**
- Sample. Most units have between a few thousand and 25,000 A instances (after the cap) and a fifth as many on B; a
  winning level often holds 10-30% of them, a second split another 10-30%. That leaves tens to a few hundred B
  instances, near the engine's floor of 30 on 20 days. A third split would fall under it for most units.
- Selection. One level is the best of about 1,440 parameters x 4 levels; depth 2 is the best of about 5 x 10^7 paths
  per unit. B stays an honest check, but A numbers at depth 3 would mean nothing.
- Compute. Each depth re-scans 1,440 parameters per path.
- Live use. A call plus two conditions is three readings, the depth of HM1's triples and of HM2's learner (max_depth
  3). Each reading needs live parity.
- Deeper conjunctions are the learner's job (OR-HM2 Part 2).

**(c) The loser profile** (Steven's standing rule: study every loser). Per unit and horizon, all six:
1. The outcome table, A and B: right / wrong / flat x take / cut / time. It shows how many wrong calls the exit still
   took in profit, and how many right calls were cut first.
2. The wrong instances' path: the mean worst adverse move before the best point, minutes to the cut, the share that
   never closed a minute on the called side (minutes held 0).
3. What the wrong instances share: the 10 levels most over-represented among wrong against right instances on A
   (ratio (wrong in level / wrong) / (right in level / right), smoothed +0.5 / +1 as in losers.py), ordered by the
   level's negative odds t (the skip list), each with its A and B ratio. At 15, 60 and 240, also the 10 levels most
   over-represented among cuts against takes.
4. One line in words, for example "wrong 15-minute calls of 15m RSI14 very low are 1.6 times as common when 1h ADX is
   very high (A 1.58, B 1.41)".

The top of each unit's skip list (the same ranking) feeds the pack's skip lists by the same rule as the take gates
(below). Nothing is removed from any existing pack.

## Outputs (requirement 6)
**1. The winner profile, per unit** (profiles_<COIN>.json.gz on Drive; the bot's calls also in the repo). Per horizon:
the call (direction, A and B numbers, the twin unit's numbers); for each track the take and skip lists (top 25 with A
and B numbers, day and week t, z_adj, rank, kept, specific_B, gate heat, aliases of near-copy parameters); the
in-sample list (all 10 GBM readings and OWN:Agree, A and B); the curves of the top 5 and of the `drill = 'B'`
parameters; the depth-2 path and its top 5; the loser profile. Rows in words for the league, with Eastern and UTC times wherever a
clock or position level appears, each with the twin unit's best number for the same list.

**2. The league view** (research/oracle_heat/hm2/part3/league.md, linked from the HM2 league). Per horizon and track
(right, move, profit): units ranked by the gate heat on B of their A-chosen top-1 take gate, and a second list by their
A-chosen top-1 skip gate. Columns: the call, the separator (parameter, level, family, specific_B), A and B lifts and
t, gate heat, what the gate does to the call's odds, pi and windows per day, the depth-2 path, and whether the row is
above the twins' maximum for the same list. At most 3 rows per call and per parameter in a list; near-copy parameters
(gated B instance sets overlapping 80% or more, Jaccard) collapse into aliases, the same on twins. A family table: per
family, the share of units whose top-1 separator is in it and the share of those that kept on B, real against twins.

**2b. The TA and pattern cards (review: Steven asks per "pattern or TA or whatever it happens to be").** One card per TA
function (the reading name without timeframe and settings, HM2's usage-card rule: RSI14 -> RSI, BBANDS20/2.5 -> BBANDS),
per candlestick pattern, per Part 4 chart pattern if loaded, and per HM2 family, over all its units (levels, settings,
timeframes, coins) and the six horizons. Per track (right and profit first): the separators that are top 5 on A most
often across its units, each with the share of those units where it kept on B and had t_B >= 2, its median B lift,
its curve's shape (threshold, slope, tail) where drilled, and the twins' median and range for the same count; the
skip levels the same way (the loser cuts of that TA); and the units behind each line. It answers "what is different
about the RSI calls (or the engulfing patterns) that are right, or that make money".

**2c. The column cards (review: "each column ... that ends up displaying this difference").** One card per parameter
(column): the units for which it is top 5 on A, the share of them where it kept on B with t_B >= 2, real against the
twins' median and range, by family of the unit and by horizon; the direction of its effect (which level helps,
which hurts); and its curve pooled over those units (instance-weighted, A and B, from the per-unit curves). A column
whose count stands clear of the highest twin set is listed first; no column is left out.

**3. The chance table** first in league.md (below, "Chance scale").

**4. Pack rows** in research/oracle_heat/latest/hm2_pack.json (the HM2 pack), kind 'gate' (one condition) or 'gate2'
(the depth-2 path). Per coin and horizon 15, 60 and 240:
- gates on the calls the bot loads (tier 1 and 2 units): the top 40 take gates by right-track gate heat, the top 20 by
  profit-track gate heat, the top 20 skip gates (right) and the top 10 (profit);
- gated calls of other units: the top 20 by right-track gate heat;
- depth-2 paths: the top 10 by gate heat;
- at most 3 rows per call in each list.

  Every pack unit's top-1 gates are also in gates_all.csv.gz (all tracks, modes and horizons), so a gate outside the
  lists is never lost.

  The gate rows are also written on their own to research/oracle_heat/hm2/part3/gate_rows.json (review: HM2's league
  writes hm2_pack.json whole, so a later HM2 league run would drop them; `league --merge-only` puts them back).
  drill-units records the sha256 of hm2_pack.json's non-gate rows; drill-league stops if they changed since (tier 2
  would be stale). Every HM2 pack loader must skip a kind it does not know (part of the hand-off).

Fields: pair_pack.json's (coin, h, key, dir, call, n, share, odds, t, wd, hold, dip, move, A and B) plus `when` (the
call's key and kind, and which pack holds it), `conds` [[parameter, [levels]]], `mode` (take | skip), `track`,
lift_A, lift_B, t_lift_A, t_lift_B (day), t_week_A, t_week_B, z_adj_A, rank_A, specific_B, gheat_B, the call's own
numbers on B beside the gated ones, pi_B and pi_c_B, take / cut shares, family, aliases, tier, above_twin_max,
live_ready. The profit track's lift is in pi_c at 15 and 60 and in bps at 240.

**Fire rule.** A gate row fires at a minute close when its `when` call fires at that close and every condition holds
its level at the last closed bar of its own timeframe (own parameters from the call's own fire history); a take row
then enters at the next minute's open, a skip row blocks the call at that close. The bot's heat lane reads it like a
pair refining its single (a loader behind its own switch, default off; the bot lane's work, not this run's).

**hm2_live_meta.json** gets a `part3` block per coin: the quintile and decile edges of the own and curve parameters of
every pack row, the 200-bin tables they need, the A directions table for OWN:Agree, and the own-parameter rules.
**live_ready** as in HM2: parity of every condition on Dec 29-31, 2025 on at least 99.5% of minutes, and the bot has
the feed.

## Chance scale (beside every count)
The twins (seeds 1, 2 and 3, HM2's joint coin flip) run the identical units, cap, kernel, ranking, drills and lists.
Per horizon and track, real against the twins' median and range:
- units with a ranked separator, and the distribution of the top-1 z_adj on A;
- the share of units whose A top-1 take gate kept its sign on B (a coin flip gives about one half), and the same for
  skip gates, depth-2 paths and the loser profile's top level;
- the share with t_B >= 2 in A's direction;
- the persistence curve: kept share by A z_adj bin (under 2, 2-3, 3-4, 4-5, 5 and over), for all separators, by
  family, and by specific_A (at or under 0, over 0);
- the 99th percentile and maximum of gate heat on B; units above the highest twin set's maximum;
- the same counts for the pack's lists;
- (review) every count also by tier (1, 2, 3), by clustering (the week t or the day t was the smaller), and for the
  in-sample list apart; curves marked `drill = 'B'` are never counted;
- (review) under the twin fallback (a seeded quarter of tier 3 on the twins), every real-against-twin count, maximum
  and "above the twins' maximum" mark is computed on the same units on both sides: tier 1 and 2 plus that same quarter
  of the real coin's tier 3. A maximum over more units runs higher, so a real list over all of tier 3 against a twin
  list over a quarter would look clear of chance too often. The real coin's other units carry the twins' p99 per
  unit, not the maximum.

Tier 1 and 2 units were chosen by HM1's and HM2's leagues on B numbers, so their call-level B numbers are not
out-of-sample; a lift inside a unit (level against the rest) is not biased by that choice, but the twins run the same
keys without it, which is why the counts are shown by tier.

A count is evidence only when it stands clear of the highest twin set. A real call has a direction and a twin unit does
not, so a separator that restates a second call, or a parameter whose levels shift volatility, can keep its sign more
often on real coins than on twins without separating this call's winners; specific_B and the odds track are the
guards, and the strata show them.

## Compute plan (requirement 7)
**Sizes per series (one coin or one twin), estimated.**
- Units about 5,300; parameters about 1,440; horizons 6; tracks 3.
- Instances: about 80-120 million on A before the cap (the 1,214 hottest levels at 15 minutes have a median of 55,000 A
  events), about 35-45 million after it; 18-25 million on B. About 60 million in all.
- Instance x parameter pairs: about 8.6 x 10^10.

**Kernel.** The HM1 pair job's vectorised bincount, on blocks of units:
- per parameter, one key per instance, key = level x G_u + day, where the unit's days are re-indexed to its own G_u
  distinct days (so a sparse unit's bins are no larger than its instances), offset by the unit; A and B in one key;
- (review) a block is cut by a budget of unit-days, not a count of units: at most 100,000 unit-days (about 45 dense
  units that fire on all 2,192 days, or hundreds of sparse ones). At 200 dense units a 48-level parameter (NY30m)
  would make 22 million bins per bincount, about 1.9 GB per worker for 11 of them; under the budget it is at most
  4.9 million bins (430 MB), and a 5-zone parameter 0.7 million. The bar index of each timeframe is computed once per
  block, so read_state is one gather per parameter;
- HM2's packing: per instance, whole-number fields packed into float64 weights (n, n240, right and wrong at 6
  horizons, take and cut at 15, 60 and 240: 20 fields of 11 bits, 4 per float64, 5 bincounts; a unit fires at most
  1,440 times a day), and move and profit at each horizon (move in 0.5 bps steps, clipped at +-4,000 bps; profit as
  pi_c in 0.05c steps at 1-60 and pi in 0.5 bps steps at 240), offset to whole numbers, 2 fields of 25 bits per
  float64 (6 bincounts). 11 bincounts per parameter; every bin stays below 2^53 (asserted);
- the clustered variance written as sums of products: the level's own part is nonzero only on the (level, day) cells
  that hold an instance, and the rest's part expands into three per-unit sums per lift (sum of S_d^2, of S_d C_d, of
  C_d^2), so only occupied cells cost anything. Day and week clusters both (second moments only); deff, which needs
  fourth powers, is computed in the direct form for the top 25 of each list. A numba kernel (numba is already in the
  oracle requirements) over the bincount output, 18 lifts (3 tracks x 6 horizons) per level;
- 4 fork workers over unit blocks (the context inherited, as heat._pmap does).

HM2's timing of numpy bincounts on random arrays gives about 2.9 ns per entry per bincount (6.5 ms per pair at
450,000 entries, five bincounts, on a 4-core 2.1 GHz Xeon). Bincounts alone: 8.6 x 10^10 pairs x 11 x 2.9 ns is about
46 minutes on one core, about 12-15 minutes on four.

| stage | time | memory |
|---|---|---|
| HM2's base(): minutes of all four coins, labels (60 and 240 grids), engine and HM2 readings, copy merge | 14 min | 6 GB, then HM2's entry matrices (code matrix, packed weights, reading totals, about 1.5-2 GB) are dropped in this process: the drill does not use them |
| 200-bin codes (the engine's vocabulary rebuilt one timeframe at a time; the 1-minute vocabulary holds about 4 GB of float series until it is coded), GBM readings from HM2's stored trees, the proxy table, the directions of every level and the fire index, units and their instances, own parameters | 20-30 min | +1.5 GB, transient +4 GB at the 1-minute vocabulary (bench) |
| depth-1 scan (11 bincounts and the variance kernel per pair, day and week clusters) | 35-70 min | +0.5-2 GB in the workers |
| depth 2 (about 0.4-1.0 of a scan) | 15-60 min | |
| re-measure of the top 25 (lean: the unit's label and proxy arrays gathered once, then bincounts by gate and split for holds, best, dip, retL, pi; exact windows per day by np.unique; deff), specific for all tracks, curves, loser profiles, writes | 15-25 min | |
| **total** | **about 1.7-3.3 hours** | **peak about 10-11 GB** |

Review: the draft's re-measure ran the engine's g.full on each gated set and its rest, per split and grid, for about
40 parameters x 5,300 units: about 1.7 million g.full calls of 5-20 ms, 3-9 hours per series on one core. g.full now
runs once per unit (the call itself, and the league check) and for the pack rows only.

**Jobs.** Part 3 cannot run inside HM2's series jobs: those take 75-125 minutes by HM2's own estimate (and may be split
if its bench projects over 300), the ceiling is 360, and the HM2 pack's units exist only after HM2's league. So Part 3
runs the same series (the four coins and the 12 twins) in its own jobs of the same workflow (oracle-hm2.yml), through
the same base() with the same readings and twins, after HM2's league:
- `drill-test`: the tests and a Drive preflight (HM2's series outputs, HM1's direction tables and packs, free space);
- `drill-units` builds the unit list once (all tiers);
- `drill-bench`: BTC, 200 units stratified by timeframe and kind, every parameter, one depth-2 drill: ms per
  instance-parameter, peak memory, projected minutes per series, free disk; about 40 minutes;
- `drill`: 16 series x S parts (S = 1 unless the bench projects over 300 minutes), max-parallel 9 (10 with CI), real
  coins first, timeout 330 minutes;
- `drill-league` (60 minutes): merges, writes the league, profiles and gate rows;
- `drill-parity`: live parity of the gates' conditions, after drill-league and never in the same push as a drill tag
  (review: its 4 jobs beside 9 drill jobs would put 13 up at once; the plan step refuses that combination).

Wall time at S = 1: two waves of 1.7-3.3 hours plus the units, test and league jobs, about 4-7.5 hours; about 30-55
runner-hours. **Fallback, fixed now:** if the bench projects more than 16 hours of wall time at the S it needs, the twins
run every tier-1 and tier-2 unit plus a seeded quarter of tier 3 (the same quarter on every twin), and the twin
columns are shown as shares, never as counts. The bench decides S; no design number changes after it.

**Drive.** The real coins write shards of the depth-1 scan (per unit, horizon, parameter and track: the take and skip
level with A and B lift, day and week t, z_adj and n; float16), about 3-4.5 GB per coin uncompressed (review: 5,300
units x 6 horizons x 1,440 parameters x 3 tracks is 137 million records of about 30 bytes; the draft's 1.5-3 GB was
low). The bench's projection replaces this. The twins keep only the small files (summary counts, top lists, drills,
profiles, meta), as in HM2.

## Tests (synthetic minutes, patched SPLITS, procs = 1)
1. **No lookahead.** Every own parameter, the 200-bin codes and the proxy cost at rows <= t are unchanged when the bars
   after t are replaced by noise (5 cut points). OWN:Last@H reads only instances whose window had closed (r + H <= i).
   The proxy of row i changes only with bars i+1 .. i+H. Since, Order, Coincide and Agree use only fires at or before
   the row.
2. **Counts.** The packed kernel's n, odds, move and profit lifts, day t and effective days equal heat.Grid.cells
   (lift=True) on the unit's events split by the parameter, to 1e-9 (move and profit within their quantum x n). The
   week t equals heat._clu's algebra with the 7-day block as the cluster, and the expanded sums-of-products variance
   equals the direct per-day form to 1e-9. No field overflows on a day of 1,440 instances at the clip values.
3. **The proxy.** Hand-built paths: take first, cut first, a cut early and a take later (it is a cut: review), neither
   (exit at H), H = 1, a flat path, the perp rule (no take, 2 x ATR stop, at least 50 bps, hit by a minute's low while
   every close stays above it, filled at the open when the minute gaps through), the cost from sigma and tau, the
   2-step minimum, pi_c inside [-54.5, 45.5].
4. **Pure noise.** A random-walk coin and its twin through the whole of Part 3: the share of A top-1 separators that
   kept their sign on B is within 0.45-0.55 on both; the sd of their B t is within 0.85-1.25; at most 1% of units are
   above the twin's maximum gate heat; the coin's kept share, t_B >= 2 share and persistence curve lie within 0.05 of
   the twin's.
5. **A planted separator.** On 1m:RSI14 = very low (up call), the next 15 minutes go up with probability 0.62 when
   FLOW:TB15 is above its A 70th percentile, 0.5 otherwise. FLOW:TB15 (or a reading listed as its alias) ranks first
   for the unit on A (right track), keeps its sign on B with t_B >= 2, and its curve rises within one decile of the
   planted 70% and is flat below it.
   Inside that level, POS:QPos m10-m14 adds 0.08 more and nothing outside it: depth 2 picks POS:QPos with those levels,
   while POS:QPos ranks low at depth 1. A planted loser level (VOL:Jump5 = down, the call wrong 70% of the time) heads
   the unit's loser profile and skip list. On twin 1 none of them stands above the twin's own 99th percentile.
6. **A planted second call, no joint effect.** A parameter level that pushes every minute up by the same amount: it
   ranks high for an up call, and its specific_B is within noise of zero on all three tracks.
7. **Twins and units.** The twins run the same unit keys with their own directions, cap and seeds; copies run once;
   the cap is seeded and repeatable; DOGE is refused; no row at or after 2026-01-01 is read. The directions follow the
   league's rule (odds over the base): a level whose raw mean sign is positive but below the base mean sign gets
   d = -1. The fire index on a twin uses the twin's own directions.
8. **(review) Slow parameter, volatility and in-sample guards.** (i) A daily-held parameter whose level flips by
   week, planted with a week-level shock and no per-instance effect: its day t is inflated and its week t is not, and
   it does not head the list. (ii) On a call with a planted odds edge, a parameter that only picks high-volatility
   minutes heads the move list in bps but not the profit list in pi_c. (iii) A GBM reading fit on the fixture's A rows
   never enters the main top 5 and is scored on B in the in-sample list. (iv) Under the twin fallback, the
   "above the twins' maximum" mark uses the same units on both sides.
9. **Outputs and live.** Gate rows have when, conds, mode and fire; JSON is written with allow_nan False; merging the
   gate rows leaves every other row of hm2_pack.json unchanged; `--merge-only` restores them after the pack is
   rewritten; a changed non-gate sha stops drill-league; the TA, pattern and column cards count every unit once per
   card; the live own-parameter reader equals the history codes on at least 99.5% of a synthetic window.

## Known limits
- **Selection inside about 1,440 parameters per unit.** A unit's best level is the best of about 5,800 levels per track
  and horizon; on noise the best z_adj is about 3.5. A's numbers for the winner are optimistic; B is the honest check
  per unit. The league and the pack then pick units by B gate heat, so their top B numbers run high too; so do the
  curves marked `drill = 'B'`. Depth 2 is the best of about 5 x 10^7 paths on A and is judged on B alone. The twins'
  maximum for the same list (on the same units) is the yardstick, and the Kalshi test is the check.
- **Overlap.** A 1-minute call fires minutes apart, so its windows overlap at 60 and 240 minutes; t is clustered by
  day and by week (the smaller |t| ranks), gate heat counts windows. One minute is an instance of many units at once, so separators of related calls
  restate each other; the lists cap rows per call and per parameter, and the profiles name related units.
- **Copies.** Near-copy parameters (RSI14 and RSI21, PERCENTB and ZSCORE20) show the same separator under several names;
  they collapse into aliases by gated B instances (80% Jaccard), the same on twins. Exact copies are merged before the
  scan (HM2's rule).
- **Slow parameters.** Dominance, daily markets, funding, open interest and the volatility regime change over days or
  years. Their levels can split a call's A instances by period, so a lift can be a difference between years; B is one
  year and may hold few of their levels. The week-clustered t keeps their lumps from posing as many independent days;
  effective days, weeks and B days are shown for every row. A lift that is a difference between years is still
  possible on A; B (one year) and the twins judge it.
- **In-sample columns on A.** The GBM readings were fit on A rows, and OWN:Agree and OWN:Last use the A directions.
  The GBM readings and OWN:Agree are ranked in the in-sample list, apart; OWN:Last stays in the main list (flipping d
  swaps its right and wrong levels with the outcome's, so the fit cannot create its lift). B is clean for all of them.
  The twins carry the same structure.
- **Tier 1 and 2 were chosen on B.** HM1's and HM2's leagues ranked the bot's calls by B numbers, so those calls' own
  B odds and pi run high. A lift inside a call is not biased by that choice; the counts are shown by tier.
- **What twins cannot judge.** A real call has a direction; a twin has none. A separator that restates its own call,
  or one that changes flat outcomes, can stand clear of the twins. specific_B and the odds track are the guards. Twins
  do not reproduce bid-ask bounce; the re-measure's move entered one minute later (retL) is a column. The move track
  is in bps, so a parameter that only picks volatile minutes lifts it for any call with an edge (and stands clear of
  twins, which have no edge); the profit track ranks pi_c at the Kalshi horizons for that reason, and the right
  track (odds) is immune.
- **The proxy** is coin price at minute closes (the perp stop at minute extremes) with a fixed tau, an at-the-money
  delta and the bot's take and cut in coin terms. It ignores the contract clock, the settlement average and the quote's own move. It ranks gates; it does
  not price them.
- **The cap** cuts the 1-minute calls' A sample to 25,000; their A t-values are lower than the full sample would give.
- **Depth 2 only**, for the reasons above. Data limits are HM2's (open interest from Sep 2020 / Dec 2021, BTCDOM from
  Jun 2021, SOL from 2020-08-12, 2025 has 32 release days and 8 FOMC days, Binance spot only).

## Unchanged
- heat.py and every stored table, hash, league and pack of run 43030435253; the HM2 design and its modules (Part 3
  reads them).
- The data cut (no 2026 minute), the entry (next minute's open), the dead band (1.5 price steps), the twins (seeds 1-3,
  joint flip), the sample floors (30 on 30 days of A, 30 on 20 days of B), NEVER DOGE.
- A map on coin price, not a validated rule.

## Next (not this run)
- The one test on recorded Kalshi asks: the gated call against the same call ungated and against random entries, the
  1-minute hold rate and the plan exits' P&L; the batch is fixed in the registry before the read.
- Gates that keep on B and pass that test become conditions in the heat lane (take rows) or loser cuts (skip rows),
  behind the lane's own switch, with Steven's approval.

## What the review changed (adversarial review, 2026-11-12 ~00:10 UTC, Nov 11 7:10 PM EST; before any Part 3 code or result)
1. **Lookahead in the profit outcome closed.** The draft's exit rule took the first take anywhere in the window before
   looking for a cut, so a take late in the window hid an earlier cut. The trade now ends at whichever comes first.
   The perp stop is exchange-side, so at 240 it is checked on minute extremes and filled at the stop, or at the open
   on a gap; closes would miss stops the bot takes.
2. **Direction rule matched to the league.** d is the sign of A's odds over the base (heat._direction's d_odds). The
   build's raw mean sign would have flipped weak calls and failed the league check.
3. **"Makes more in profit" in the right unit.** The profit track ranks pi_c (cents per contract, clipped to the
   contract's +-50c) at the Kalshi horizons and bps only at 240. In bps every volatility reading would head the
   profit list of every call with an edge, without separating its winners.
4. **Heat on noise.** A week-clustered t beside the day t, and the smaller one ranks, so slow parameters and windows
   that cross midnight do not inflate t. The GBM readings and OWN:Agree, fit on A, are ranked in an in-sample list
   apart and never fill the drill. The fire index uses directions this job computes, so twins run the identical
   procedure. Under the twin fallback the "above the twins' maximum" mark compares the same units on both sides.
   Counts are shown by tier, because tiers 1 and 2 were chosen on B. Tier 3 is ordered by A heat, not B.
5. **Steven's question answered per TA, pattern, row and column.** TA and pattern cards (per TA function, candlestick
   and chart pattern, HM2 family) and column cards (per parameter, with a pooled curve), real against twins.
   Parameters that end up showing the difference on B are drilled too, marked `drill = 'B'` and kept out of the
   chance counts.
6. **specific_B on all tracks.** HM2's part_effects has the sign track only, so the drill computes the all-minutes lift
   for right, move and profit itself.
7. **Fit with HM2.** Gate rows also go to their own file and `--merge-only` puts them back if HM2's league rewrites
   hm2_pack.json. drill-league stops if HM2's pack rows changed since the units were built, and pack loaders must
   skip unknown kinds. HM2's entry matrices are dropped in the drill's process. X.O readings have no raw series, so
   they get 5-zone curves.
8. **Compute.** Blocks are cut by unit-days, not by 200 units: a 48-level parameter on 200 dense units needed about
   1.9 GB per worker. The variance uses second moments over occupied cells, with deff exact for the top 25. The
   re-measure is lean: the draft's roughly 1.7 million g.full calls (3-9 core-hours per series) are gone. The
   1-minute vocabulary's transient 4 GB is in the memory line, and the shards are re-estimated at 3-4.5 GB per coin.
   drill-parity never runs beside the drill jobs (13 jobs would be up).
9. **Unchanged:** the units, outcomes, parameter families, floors, depth 2, twins, owner's rules and the HM2 design.
   No pass bar was added: apart from the two fixes (the exit rule and the direction rule), every change is a column, an
   order, a stratum, a list kept apart or a compute step.

