# Round 17: is there a law in how the fractal's time stretches?

Asked Nov 21, 2026, 11:26 PM EST / Nov 22, 04:26 UTC. TradingView BTC.D, recorded days through 2026-11-21.
Parent = Jun 19 2016 to Feb 26 2017 (36 weeks). Child = Dec 10 2017 to today (467 weeks). Weekly closes (weeks ending Sunday).
The plan (PLAN.md) was written and attacked by two critics before any test was run.

## Answer

A pattern can be seen, but it is not a clock, and it gives no date. Nothing below is a timing call or a stand-down.

1. Every pace below is measured on the settled, hand-picked anchors. An alignment that is given no anchors agrees with
   them on the late legs (end of the consolidation, today on the parent's top) and not on the early ones (section 5).
2. On those anchors the pace was 1 in the waterfall, 5 in the rise after it, then about 21 for three stretches in a
   row if the top is the June 2025 high (34 on the last one if the top is today). A jump, then a plateau.
3. One description passed the planned test: the pace rises along the structure (consistent with, on five hand-picked
   stretches). It is a statement about position, not a clock, so no date can be read from it. No volatility,
   market-size or direction-change clock passed. On five stretches "later in the structure" and "later in a market that
   moves less each year" cannot be told apart.
4. All three waterfalls on record ran at one speed, but all three are from 2016-18, in the same volatile market. How
   fast or how long a waterfall would run in today's quiet market is untested, so the old speed is not a template.
5. Run forward week by week with nothing supplied from hindsight, the model gives no usable reading today. With the
   amplitude fixed from hindsight it has read "the child is on the parent's top" since July 2023: it cannot tell an
   early top from a late one, so it cannot time the top.
6. No coin, pair or macro chart follows the BTC.D time map better than nearby maps.

## 1. Units and method

- logit BTC.D = log(BTC value / value of everything else). A fall of 0.25 logit in a week means BTC lost 22% against
  everything else that week. This unit treats a move at 96% and a move at 60% alike.
- Pace = child weeks per parent week over a matched stretch. Magnification = child move / parent move, in logit.
- Method taken from the literature on aligning two records whose clock runs at an unknown, changing rate (sediment and
  ice cores: Lisiecki and Lisiecki 2002, Lin et al. 2014, Hagen et al. 2020), with the warnings from the time-warping
  literature that a flexible alignment fits almost anything unless it is scored against look-alikes with the same freedom
  (Keogh and Pazzani 2001, Theiler et al. 1992), and the market time-deformation literature (Ane and Geman 2000,
  Glattfelder et al. 2011), which says the market's clock is activity or volatility. Limit: each reference was checked to
  exist (Crossref); the summaries are from memory, because the literature tool's free quota ran out mid-search.

## 2. The time map on the settled anchors (m1_landmarks.py)

| stretch | parent | child | parent wk | child wk | pace | parent BTC.D | child BTC.D | magnification |
|---|---|---|---|---|---|---|---|---|
| waterfall | Jun 19 to Jul 24 2016 | Dec 10 2017 to Jan 14 2018 | 5 | 5 | 1.0 | 98.41 to 95.19 | 67.39 to 36.83 | 1.11 |
| rise | Jul 24 to Nov 20 2016 | Jan 14 2018 to Sep 8 2019 | 17 | 86 | 5.1 | 95.19 to 97.19 | 36.83 to 71.70 | 2.64 |
| mid-structure fall | Nov 20 to Dec 18 2016 | Sep 8 2019 to May 16 2021 | 4 | 88 | 22.0 | 97.19 to 95.11 | 71.70 to 40.82 | 2.26 |
| sideways consolidation | Dec 18 2016 to Jan 15 2017 | May 16 2021 to Dec 11 2022 | 4 | 82 | 20.5 | 95.11 to 94.91 | 40.82 to 40.80 | flat |
| rise to the top, to the Jun 22 2025 high | Jan 15 to Feb 26 2017 | Dec 11 2022 to Jun 22 2025 | 6 | 132 | 22.0 | 94.91 to 95.96 | 40.80 to 65.72 | 4.20 |
| rise to the top, to today | Jan 15 to Feb 26 2017 | Dec 11 2022 to Nov 22 2026 | 6 | 206 | 34.3 | 94.91 to 95.96 | 40.80 to 59.18 | 3.06 |

The end of the consolidation is a zone (Nov 13 2022 to Jan 8 2023); moving it across the zone changes the fourth pace to
19.5 to 21.5 and the fifth to 21.3 to 22.7 (Jun 2025 high) or 33.7 to 35.0 (today).

What the table shows:
- The pace is 1, then 5, then about 21 for three stretches in a row if the top is the June 2025 high: a jump, then a
  plateau, not a steady rise. If the top is now, the last pace is 34 and grows by one sixth every week that passes.
- The sizes do not scale by one number either (1.1, 2.6, 2.3, flat, 3 to 4). The child repeats the parent's order of
  legs, not its proportions.
- Measured in BTC.D's own elapsed variance instead of weeks, the child used 0.5, 1.7, 22, 6.6 and 7 to 10 times the
  parent's amount over the five stretches. A volatility clock does not make the two line up (description only; this form
  is circular as a test and was dropped by the plan critics).
- The parent's mid-structure fall is a one-day index step on TradingView (Dec 16 2016), so the pace of 22 on that stretch
  compares 88 real weeks with a data event.

## 3. How fast each leg ran (description only; m6_leg_speeds.py, leg_speeds.png)

| leg | weeks | move (logit) | speed (logit a week) | fastest 4 weeks | market value at the start |
|---|---|---|---|---|---|
| July 2016 waterfall (parent) | 5 | -1.138 | -0.228 | -1.011 | $12.1bn |
| 2017 waterfall after the parent's top | 12 | -2.526 | -0.210 | -1.403 | $19.9bn |
| 2017-18 waterfall (child) | 5 | -1.266 | -0.253 | -1.166 | $379bn |
| not a waterfall: 2021 fall, sharp part (Jan 3 to May 16 2021) | 19 | -1.236 | -0.065 | -0.469 | |
| not a waterfall: Jun to Sep 2025 drop | 12 | -0.337 | -0.028 | -0.209 | |
| parent rise after the July 2016 waterfall | 17 | | +0.033 | | |
| parent rise to the top | 6 | | +0.041 | | |
| child rise 2018 to 2019 | 86 | | +0.017 | | |
| child rise to the Jun 22 2025 high | 132 | | +0.008 | | |

- The three waterfalls: BTC lost 19% to 22% a week against everything else, in markets of $12bn, $20bn and $379bn. The
  child's waterfall took the parent's five weeks. (The 2017 waterfall includes three index-step days; with them taken
  out it is -2.02 logit, -0.168 a week.)
- All three are from one era, June 2016 to January 2018, when BTC.D's daily volatility was 0.03 to 0.06. The child's
  waterfall began under seven months after the parent's last one ended (May 21 to Dec 10 2017). So "the waterfall was
  not stretched" may mean no more than "it happened in the same market". The market grew 31 times between the first
  and the third, but volatility, the thing that sets how fast the chart moves, stayed high.
- There has been no waterfall in the quiet market since. Whether one would run at 0.2 logit a week, or last 5 to 12
  weeks, is untested. A real waterfall now could be slower than all three, so the old speed must not be used to judge
  whether one has started.
- The 2021 fall ran at about a quarter of the waterfall speed and the 2025 drop at about an eighth. That fits keeping
  them off the waterfall list. The 2021 fall began from volatility like the 2017 waterfall's (0.031 against 0.028) and
  was still three times slower, so starting volatility alone does not make a waterfall; the 2025 drop began from a much
  quieter market (0.013).
- Every 4-week fall of 0.5 logit or more on record (BTC down 39% against the rest in four weeks) ended between May 2014
  and Jan 14 2018. There are seven; none since. The largest since is -0.469 (2021). The 0.5 cut-off was picked after
  seeing the data.
- The stretch is not spread evenly: rises ran 2 to 5 times slower in the child than in the parent, the mid-structure
  fall and the consolidation took about 20 times longer, and the one waterfall the child has had was not slower.
- Limit: three events, one of them in the child, and its pace of 1.0 comes straight from the anchors.

BTC.D's own daily movement has shrunk over the years (median 13-week volatility of daily logit changes, index-step days
out): 0.048 in 2016, 0.050 in 2017, 0.030 in 2018, 0.020 in 2019, 0.019 in 2020, 0.031 in 2021, 0.015 in 2022, 0.011 in
2023, 0.014 in 2024, 0.016 in 2025, 0.009 in 2026. This is the plain description of the stretch: the chart moves less per
day, so a structure takes longer to draw. It is a description, not a tested law (section 4 tests the volatility clock and
it fails on length).

State at the start of each fall (13 weeks before: daily volatility; BTC.D's own move in logit). After-the-fact
description, not a signal:

| start | volatility | BTC.D move |
|---|---|---|
| July 2016 waterfall | 0.048 | +0.088 |
| 2017 waterfall after the top | 0.028 | +0.273 |
| 2017-18 waterfall | 0.064 | +0.582 |
| not a waterfall: 2021 fall from the Sep 2019 high | 0.028 | +0.593 |
| not a waterfall: 2021 fall, sharp part | 0.031 | +0.485 |
| not a waterfall: Jun to Sep 2025 drop | 0.013 | +0.171 |
| today (Nov 21 2026) | 0.0084 | -0.018 |

- Each waterfall began with BTC.D volatile and rising. That is not a trigger and carries no information on timing:
  the thresholds are simply the lowest of the three starts (picked after the fact), 82 of the 652 weeks since June 2014
  had the state (13%), and the 2021 fall began from it as well.
- The state has not been present since Aug 15 2021, and today's volatility is in the lowest 3% of all weeks since June
  2014 (the lowest was 0.0073 on Sep 6 2026). But every waterfall on record predates 2018, when BTC.D was more volatile
  all the time. So this says the market is different now. It does not say a waterfall is far off.

## 4. No clock sets the pace (m4_laws.py)

Each law says log(pace of a stretch) = a + b x (a reading known the week before the child's stretch starts). Scored by
leaving one stretch out and predicting it from the other four. Error is in log units: 0.69 is a miss by a factor of 2,
1.1 by a factor of 3.

| law | top = Jun 2025 high: error | rank match | top = today: error | rank match |
|---|---|---|---|---|
| L0 constant pace | 1.52 | | 1.62 | |
| L1 position along the parent (each stage slower) | 0.84 | 0.82 | 0.75 | 0.90 |
| L2 BTC.D's own volatility, prior 26 weeks | 1.22 | 0.87 | 1.12 | 0.90 |
| L3 BTC price volatility, prior 26 weeks | 1.44 | 0.87 | 1.44 | 0.90 |
| L4 market size | 1.89 | 0.05 | 1.93 | 0.20 |
| L5 directional changes per week (intrinsic time) | 1.37 | 0.87 | 1.26 | 0.90 |
| placebo: S&P 500 volatility | 1.35 | -0.87 | 1.20 | -0.90 |
| placebo: dollar index volatility | 4.77 | 0.21 | 4.98 | 0.00 |
| placebo: EUR/USD volatility | 2.92 | 0.21 | 3.14 | 0.00 |

- By the plan's rule L1 passes: it beats the constant pace and every placebo clock when a stretch is left out, and the
  planned family-wide exact permutation test (the five paces dealt out in all 120 orders, best law each time) gives
  p = 0.033 (Jun 2025 high) and 0.025 (today). As the plan requires, this is worded "consistent with a pace that rises
  along the structure, on five hand-picked stretches", not a law.
- What L1 is: position in the structure, not a clock. It gives no date. It still misses a left-out stretch by a factor
  of 2.1 to 2.3, and the table in section 2 is a jump and a plateau more than a steady rise. It must not be carried past
  the top (the settled rule), and nothing here tests it there.
- An extra check that was not in the plan weakens it further: 13.8% and 12.3% of 2,000 random trending series do as
  well as L1 (the drift and spread of those series were my choice). Five numbers in rising order are easy to "explain".
- The volatility clocks (L2, L3, L5) put the stretches in the right order but miss each length by a factor of 3 to 4,
  no better than S&P 500 volatility, which has nothing to do with BTC.D. They do not pass.
- Market size does not even order the stretches ($379bn, $622bn, $260bn, $2,130bn, $806bn at the five starts).
- Verdict: no clock passes, so no date is read off. The pace rose along the structure; on five stretches that cannot be
  told apart from "the market got quieter every year".

## 5. The fractal run forward, and an alignment with no anchors given (m2_align.py, m3_forward.py, time_map.png)

Model: the child's weekly closes are observed; hidden behind them is a position on the parent (daily) and a speed that
can change week to week (16 levels, 0.05 to 10 parent days per child week). One amplitude scale links child to parent.
No anchors are given except the shared start.

In hindsight (all data, the last week required to sit on the parent's top or past it):
- The amplitudes that give a sensible map (1.5 to 3.0) agree on the late part of the settled map and differ on the early
  part. At amplitude 2.3: end of the grey box (Jan 15 2017) lands on Feb 5 2023 (80% band Dec 25 2022 to Feb 26 2023;
  the settled anchor is Nov 13 2022 to Jan 8 2023). The parent's Nov 20 2016 high lands on Jan 31 2021, not Sep 8 2019:
  the model takes the January 2021 high as the top of the same hump. The parent's Dec 18 2016 lands on Mar 7 2021
  (settled: May 16 2021). The end of the July 2016 waterfall lands on Jul 29 2018 (settled: Jan 14 2018), because the
  parent is flat after its waterfall and the child was not.
- Today sits on the parent's daily high (Feb 24 2017, 96.09; the weekly-close top is Feb 26). Probability that the map
  is past the top: 0.00 at every amplitude from 2.0 up and in every variant (3, 6, 12 weeks of parent after the top;
  stickier or looser speed; log instead of logit). Reason: the parent fell at once after its top and the child has gone
  sideways for 74 weeks since its June 2025 high. This is "no post-top fall has started", not proof that the top is in.
- Without the requirement that the last week sits on the top, the best fit is degenerate: amplitude at the edge of the
  allowed range (4.5), the whole child laid on the parent's first three months. With the index-step days taken out of
  the parent the fit falls apart as well. The alignment leans on the parent's steps and on being told where it ends.

Run forward in real time (refit every 13 weeks from Jan 2019 on data to that week only):
- With the amplitude free, the real-time reading was degenerate (amplitude 3.5 to 4.5, at or near the edge of the
  allowed range, parked on Jul to Sep 2016) in every quarter from Jan 2020 to Jan 2023 and again from Jun 2025 to
  today. Only from Apr 2023 to Mar 2025 did it settle on a sensible amplitude (2.0 to 3.0).
- With the amplitude held at 2.3 (a value only hindsight supplies): the reading wandered through the 2018-21 hump
  (late Nov 2016 in Oct 2019, back to Oct 2016 through most of 2020, Aug 2016 in Apr 2021), then sat on the end of
  the grey box from Oct 2021 to Apr 2023, and has sat on the parent's top in every quarter from July 2023 to today.
- In July 2023 BTC.D was near 50%. It then rose to 65.72 and went sideways near 59 to 61. The real-time reading said
  "top" through all of it, because each refit lines the child's highest level so far up with the parent's top. So the
  run-forward cannot tell an early top from a late one. It recognised each fall only after the fall was complete, and it
  read "top" two years before the high.

Look-alike test for the automatic alignment: PENDING (m2_null.py, running).

## 6. Cross-reference: matched stretches on other charts (m5_matched_days.py)

Direction agreement = in how many of the five matched stretches the chart moved the same way in parent and child (top =
today reading; the Jun 2025 reading differs by at most one). "Follows the map" = the match of weekly changes along the
BTC.D map, and the share of 1,000 nearby maps (inner anchors moved up to a year) that match as well.

| chart | same direction | follows the map: match, share of nearby maps as good (Jun 2025 / today) |
|---|---|---|
| BTC.D itself (true by construction, see below) | 5 of 5 | 0.52, 0.004 / 0.50, 0.006 |
| BTC in USD | 3 of 5 | 0.38, 0.17 / 0.24, 0.37 |
| whole market value | 2 of 5 | 0.26, 0.18 / 0.17, 0.34 |
| alts without stablecoins | 4 of 5 | 0.10, 0.08 / 0.09, 0.10 |
| alts against BTC | 4 of 5 | 0.20, 0.15 / 0.19, 0.14 |
| ETH/BTC | 1 of 4 | 0.02, 0.17 / 0.06, 0.15 |
| OTHERS.D | 2 of 5 | 0.06, 0.28 / 0.08, 0.29 |
| XRP in USD | 0 of 5 | -0.02, 0.16 / 0.10, 0.08 |
| XRP/BTC | 3 of 5 | 0.33, 0.008 / 0.28, 0.095 |
| XLM in USD | 4 of 5 | 0.41, 0.13 / 0.44, 0.11 |
| XLM/BTC | 5 of 5 | 0.40, 0.08 / 0.34, 0.24 |
| DOGE in USD | 4 of 5 (3 on the Jun 2025 reading) | -0.18, 0.94 / -0.20, 0.95 |
| DOGE/BTC | 3 of 5 | -0.05, 0.66 / -0.11, 0.62 |
| LTC in USD | 2 of 5 (1 on the Jun 2025 reading) | -0.32, 0.82 / -0.34, 0.86 |
| LTC/BTC | 3 of 5 | 0.10, 0.09 / 0.02, 0.17 |
| US dollar index | 2 of 5 | 0.01, 0.17 / -0.05, 0.19 |
| S&P 500 | 3 of 4 | 0.09, 0.57 / 0.06, 0.64 |
| US 10-year yield | 1 of 5 | -0.03, 0.31 / -0.04, 0.37 |
| US M2 | 5 of 5 (it always rises) | 0.35, 0.008 / 0.37, 0.010 (a monthly series; not read as a finding) |

- BTC.D's own row is true by construction: the anchors were placed on BTC.D's turning points, so moving them makes
  BTC.D fit worse almost automatically. It only shows the test works. The finding is the negative one: no other chart
  follows the map better than nearby maps. Charts that are BTC.D turned over (alts against BTC) agree in direction by
  construction and still do not follow the map week by week.
- XRP/BTC reaches 0.008 on one reading and 0.095 on the other. With 18 charts tried, one such reading is about what
  chance gives (roughly a 13% chance that at least one of 18 reaches 0.008). Not a finding.
- XRP in USD: 0 of 5, but its parent-era moves were small (between -17% and +20% in each of the five stretches) while
  the child's were multiples (x7.8, x0.14, x5.5, x0.26, x2.4). XRP was close to flat while the parent drew its
  structure, so the direction count is mostly noise, not an opposite pattern.
- BTC's price does not carry over. In the consolidation the parent's BTC rose 4% and the child's fell 63% (the 2022
  bear market); in the rise after the waterfall the parent's BTC rose 10% and the child's fell 24%.
- Dollar, stocks, yields: no agreement beyond chance. The structure is BTC.D's own.
- Coverage: ETH/BTC and the S&P 500 series have no reading for the first parent stretch. USDT.D was not used in the
  parent era (under 0.5% of the market).

## 7. What this says about now

- No pace and no date can be carried past the top. The only pace-one leg the child has had came in 2017-18. Whether
  the next fall runs at the old waterfall speed or slower is open, so the thing to watch is the fall itself, by the
  tell already set in round 16 (a weekly BTC.D close under 57.79 with ETH/BTC rising and BTC.D without stablecoins
  falling), not a speed.
- "Roughly three months once it starts" matches the 2017 waterfall (12 weeks); the other two took 5. None of the three
  happened in a market as quiet as today's, so the record can neither confirm nor refute it.
- BTC.D today is flat and close to its quietest on record. That makes today unlike the start of each past waterfall,
  and equally unlike the whole era they happened in. It is not evidence that a waterfall is far off.
- The five-signal reading is 4.8% for a 5-point fall starting within 26 weeks, above the 1.96% act line at 50 to 1.
  It comes from the five-signal model of rounds 8 to 10, re-read for the week of Nov 15 2026 in round 15; it was not
  produced or retested in this round, and nothing in this round lowers it. This is not a stand-down.

## Limits

- Five stretches and three waterfalls, all picked by eye. Every pace, the plateau, the rising-pace result and the
  cross-reference rest on those anchors. Every test above is a description of that record.
- All three waterfalls are from 2016-18. Nothing here says how a waterfall behaves in today's quieter market.
- The parent's mid-structure fall is one index-step day, so the automatic alignment partly aligns to a data event.
- The real-time run refits the alignment, but the choice of parent was made with hindsight; no forecast was scored
  (earlier rounds found no forecast skill).
- The literature summaries are from memory; only the existence of each reference was checked.

## Files

PLAN.md (plan and revision), common.py, hmm.py, m1_landmarks.py, m2_align.py, m2_null.py, m3_forward.py, m4_laws.py,
m5_matched_days.py, m6_leg_speeds.py, charts.py, fetch_coins.py; results in the .json files beside them; charts
time_map.png and leg_speeds.png.
