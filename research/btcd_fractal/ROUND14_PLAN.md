# Round 14: Steven's July-2016 fractal (pre-registered 2026-11-02 20:36 UTC / 3:36 PM EST)

Steven, doc comment 2026-11-02 20:27 UTC (3:27 PM EST), on the round-11 series chart: "the waterfall event I spoke
about is still incorrect; it would have been about mid July in 2016 from the waterfall event that correlates to the
actual waterfall event in 2017-2018. then the central hump and subsequent breakdown from the 2018 bottom to the fall in
2021 correlates to the bottom of the July 2016 waterfall to the rise and subsequent fall in about mid December 2016. This
information is the direct fractal I'm witnessing."

His mapping is a different scale from rounds 1-11 (parent 2016-17 -> child 2018-now). Parent: BTC.D from the July 2016
waterfall through the rise and the mid-December 2016 fall, then on to the end of 2017. Child: the 2017-18 waterfall,
the 2018 bottom, the central hump, the 2021 fall, then on to today. Question: where does his mapping put today in the
parent, what came next in the parent, and does the mapping carry information beyond chance?

Facts checked before this plan (weekly closes, W-SUN):
- TradingView CRYPTOCAP:BTC.D (what Steven and the bot read): waterfall 97.80 (2016-07-10) -> 95.19 (2016-07-24); rise to
  97.19 (2016-11-20); fall to 95.11 (2016-12-18); 94.91 (2017-01-15); 95.96 (2017-02-26); the 2017 waterfall from March
  (83.67 on 2017-04-02, 54.14 on 2017-07-16). Child: 67.39 (2017-12-10), 36.83 (2018-01-14), 71.70 (2019-09-08), 70.35
  (2021-01-03), 40.82 (2021-05-16), 39.36 (2022-01-16), 65.72 (2025-06-22), 60.50 (2026-11-01).
- The 2016-12-16 drop on TradingView (97.09 -> 95.06 in one day) is an index step: TradingView's TOTAL2 rose 75% that day
  (0.373 -> 0.652 bn USD) while BTCUSD rose 0.7%; CoinMarketCap dominance rose that week (86.26 -> 86.48), peaked at
  87.57 (2016-12-25) and fell to 84.81 (2017-01-15). The 2016-07-12 drop is partly the same (TOTAL2 +52% that day), but
  CoinMarketCap also shows a real July dip (83.56 on 2016-07-03 -> 79.64 on 2016-07-24).
- Steady clock: (P1 2016-07-24 <-> C1 2018-01-14) and (P3 2016-12-18 <-> C3 2021-05-16) = 174 child weeks per 21 parent
  weeks (8.3:1); at that pace today maps to 2017-08-13 (after the 2017 waterfall). Matching the child's 2025-06-22 top to
  the parent's 2017-02-26 top needs 21.4:1 since 2021.

## Series (logit of the share throughout)
- TV: TradingView BTC.D, data/BTC.D_1d.csv. Primary: Steven's series.
- TVc: TV with index steps removed. A day d in 2014-04-01..2018-12-31 is a step when |dTV(d) - dCMC(d)| >= 0.75
  percentage points and the TOTAL2 log change minus the BTCUSD log change is >= 0.20 in the direction that moves BTC.D
  the same way as the TV-CMC gap (alt index up -> BTC.D down, and the reverse). On step days logit TVc moves by
  CoinMarketCap's logit change; on other days by TradingView's. Every step day is listed with its sizes.
- CMC: CoinMarketCap global dominance, data/BTCD_CMC_1d.csv (canonical, round 11).

## Anchors (rules applied to each series; Steven's words in brackets; no tuning after the run)
- P1 [the bottom of the July 2016 waterfall] = min weekly close in 2016-07-01..2016-08-31.
- P0 [the waterfall's top] = max weekly close in the 8 weeks before P1.
- P2 [the rise] = max weekly close in (P1, 2017-01-31].
- P3 [the subsequent fall, about mid-December 2016] = min weekly close in (P2, P2 + 4 weeks].
- C1 [the 2018 bottom] = min weekly close in 2018-01-01..2018-03-31.
- C0 [the 2017-18 waterfall's top] = max weekly close in the 8 weeks before C1.
- C3 [the fall in 2021] = min weekly close in 2021-01-01..2021-06-30.
- C2 [the central hump] = max weekly close in (C1, C3).
- The parent ends at C0 - 1 week (2017-12-03), so it never contains the child. Expected on TV: P0 2016-06-19, P1
  2016-07-24, P2 2016-11-20, P3 2016-12-18, C0 2017-12-10, C1 2018-01-14, C2 2019-09-08, C3 2021-05-16.
- Variants (the robustness family, not the primary): C2' = the other hump (TV: 2021-01-03; on a series whose primary
  C2 is the 2021 spike, the 2019 hump = max in (C1, 2020-06-30]); C3' = min weekly close in 2021-07-01..2022-06-30;
  P3' = min weekly close in (P2, P2 + 8 weeks]; each anchor jittered by -2..+2 weeks (all single-anchor jitters).

## Placement (reported regardless of the tests)
- Anchored DTW on weekly logit closes. The path is forced through (P0,C0), (P1,C1), (P2,C2), (P3,C3); each segment is
  aligned by DTW; after (P3,C3) the alignment is open-ended at today's child week (the parent end free within
  (P3, 2017-12-03]). Level map: child logit = a + b * parent logit, (a, b) least squares on the four anchor pairs,
  b clipped to [0.35, 2.5] (rounds 1-11's clamp). Steps: child +1 / parent +1 / both; a run of child-only steps is
  capped at `cap` child weeks per parent week (primary cap 32); parent-only steps cost a penalty equal to the median
  squared residual of the anchored part.
- Shape variant: the same alignment on z-scored logit levels within each anchored segment, and for the open part the
  parent's logit z-scored over (P3, 2017-03-05] (up to the start of the parent's 2017 waterfall, defined below) and the
  child's over (C3, today].
- Family: series {TV, TVc, CMC} x level map {affine, shape} x cap {16, 32, 64} x anchor sets {primary, C2', C3',
  P3' (where it differs), 40 single-anchor jitters}. Report today's parent week for the primary setting and the family
  p10 / p50 / p90, per series and pooled.
- Robustness (T1): share of the TV family within +-4 parent weeks of the TV family median; "robust" at >= 80%.
- The steady-clock reading (straight line through (P1,C1) and (P3,C3)) beside it.
- Read-out from the placement: the parent's next waterfall (the first parent week after the placed week from which the
  parent falls >= 15 points within the next 16 weeks; on TV expected about 2017-03-05), its start and low in parent
  weeks, translated to child weeks with three clocks (the local DTW slope over the last 52 child weeks, the 2021-today
  average, the 2018-2021 steady 8.3:1). Level projection through (a, b) is reported as a diagnostic and flagged when the
  parent's move exceeds the child's whole logit range (expected: it does; the parent's 2017 waterfall is about twice the
  child's largest logit move).

## Tests (pre-registered; TV is the verdict series, TVc and CMC are reported beside it)
- T2 Shape evidence. Statistic D = mean squared residual of the open part (child (C3, today] against the aligned
  parent) under the primary setting. Placebo parents, each given the same freedom Steven had: its anchors are searched
  (P1 among its 3 deepest local minima in the parent's first 30 weeks, P0 by the same 8-week rule, P2 among the 3
  highest local maxima after P1 within 30 weeks, P3 by the 4-week rule) to minimise the anchored part's cost against the
  real child (C0..C3); then D of its open part is computed exactly as for the real parent, and the real parent is scored
  with the same search (Steven's own anchors reported beside). Families, 200 each unless fewer exist: (a) IAAFT of TV's
  weekly logit 2014-04..2017-12-03; (b) 8-week block bootstrap of the same; (c) random walks matched to its logit
  increment sd; (d) offset windows of TV (every start 2014-04..2016-04 with the parent's length); (e) CMC and OTHERS.D
  windows with the parent's length (other series); (f) the time-reversed TV parent (one series, its percentile reported).
  Pass: real D below the placebo 5th percentile in >= 4 of the 5 families (a)-(e), and (f) worse than the real parent.
- T3 Walk-forward since the 2021 fall. For each child week t from C3 + 26 weeks to the last week with a known 26-week
  label (step 1 week), using child data up to t only: place t (primary setting); the fractal's probability p(t) = share
  of the TV family whose placed week is within h(t) parent weeks before the parent's next waterfall start, h(t) = 26 /
  local clock(t); target fall5_26w on TV BTC.D (round 8's definition: the min of the next 26 weekly closes <= close - 5
  points). Score: Brier against (i) the expanding climatology (point in time) and (ii) fixed5's out-of-sample
  predictions on the same weeks (out8/honest or out9/candidates); 26-week block bootstrap q05 / q95; placebo: the same
  walk-forward with 40 placebo parents per family (a)-(d), their Brier improvement over climatology, p95.
  Pass ("forecast supported"): Brier better than climatology with block q05 > 0 AND above the placebo p95. The
  placement path p50(t) from 2021-11 to today is reported with BTC.D's path.
- T0 Data. The index-step list for 2014-2018 and which anchors sit within 1 week of a step; T1-T3 rerun on TVc and CMC.

## Verdicts
- Placement: "robust" or "fragile" (T1), with today's parent week on each series.
- Shape: "supported" or "not supported" (T2), with the family percentiles.
- Forecast: "supported" or "not supported" (T3), with the Brier numbers.
- Reported regardless: placement, the parent's next waterfall and the three clock translations, the steady-clock
  reading, the index-step audit, Steven's anchors scored with and without the search.
Multiple comparisons: three tests on one verdict series; T2 needs 4 of 5 families; TVc and CMC never rescue a TV fail.
Nothing in bot/ changes; the engine (bot/macro/fractalEngine.ts) is Steven's call.
