# Round 17 plan: is there a law in how the fractal's time stretches?

Asked Nov 21, 2026, 11:26 PM EST / Nov 22, 04:26 UTC: run the fractal forward on the weekly timeframe, parent
against child, and see whether a pattern can be discerned in the dynamic stretching and squeezing of time. Cross
reference the matched days on other assets and key charts. Research the best way to measure it first, then run it
in loops with critic agents. Written BEFORE any of the new tests were run.

## What is being measured
- Series: TradingView BTC.D. Parent = Jun 19 2016 to Feb 26 2017 (its top), 36 weeks. Child = Dec 10 2017 to today,
  467 weeks. Child on weekly closes (weeks ending Sunday). Parent on weekly closes for the tables, and on daily
  closes inside the alignment, because one parent week is 20 to 35 child weeks late in the map.
- The time map g: parent date -> child date, monotone. Pace = child weeks per parent week = slope of g.
- Settled anchors (Reading 1): P 2016-06-19, 07-24, 11-20, 12-18, 2017-01-15, 02-26 <-> C 2017-12-10, 2018-01-14,
  2019-09-08, 2021-05-16, end of the 2021-22 sideways consolidation (Nov 13 2022 to Jan 8 2023), top (two readings
  kept side by side: the Jun 22 2025 high, and today). Paces so far: 1.0, 5.1, 22, about 20, then 21 to 35.
- Known data problem: the parent's mid-structure fall is one TradingView index step (Dec 16 2016); other step days
  2016-10-09, 2017-04-02, 05-07, 05-09, 07-14.

## What the literature says (existence of each reference checked; summaries partly from memory)
- Aligning two records whose clock runs at an unknown, changing rate is the stratigraphy problem: Lisiecki and
  Lisiecki 2002 (dynamic programming with a penalty on rate changes), Lin et al. 2014 (hidden Markov alignment that
  returns a posterior band for the map), Hagen et al. 2020 (dynamic time warping with constraints, tested on
  perturbed and synthetic records). Dynamic time warping alone returns one path and can align almost anything, so the
  score means nothing without a null that has the same freedom (Keogh and Pazzani 2001; Theiler et al. 1992).
- Time deformation in markets: Clark 1973, Mandelbrot-Fisher-Calvet 1997 (trading time), Ane and Geman 2000
  (transaction clock), directional-change intrinsic time (Glattfelder et al. 2011: the time a move takes grows with
  about the square of its size). All of these say the clock is volatility or activity, not a smooth calendar law.
- Log-periodic self-similarity (Sornette 1998; Feigenbaum and Freund 1996; Drozdz et al. 1999) is the one school
  that claims a geometric clock; main criticisms are many free parameters and fits chosen after the fact.
- Few visually chosen events: count the whole search (White 2000; Sullivan et al. 1999).

## Measures (fixed list)
M1. Landmark map. The stretch table on the settled anchors: weeks, pace, size of the BTC.D move in logit units,
    magnification, realised variance (daily and weekly), roughness = realised variance / (net move squared).
M2. Anchor-free alignment (Lin-style hidden Markov model). Observed: child weekly logit BTC.D. Hidden: position on
    the parent (daily grid) and a speed level (parent days per child week, 16 log-spaced levels 0.05 to 10, sticky
    random walk with switch probability q). Advance per week ~ Poisson(speed). Emission: Gaussian around
    a + b * parent logit (a, b, sd fitted by EM). Start pinned at the waterfall start; end free; the parent runs
    three weeks past its top (to Mar 19 2017) so the model can say "past the top". Primary q = 0.05; q = 0.02 and
    0.10 and a log (instead of logit) scale reported as sensitivities, all shown.
    Outputs: posterior map with an 80% band, posterior pace per child week, how many of the five anchors fall in
    the band, where today sits on the parent.
    Null with the same freedom and the same pipeline: (a) placebo parents = 37-week windows of BTC.D from 2014 to
    mid 2016 and of other dominance series (ETH.D, OTHERS.D, USDT.D), each run through the identical fit;
    (b) phase-randomised surrogates of the parent; (c) the parent time-reversed. Statistic: fitted log-likelihood
    per week. p = share of nulls that fit the child as well.
M3. Run forward in real time. Forward filter only (week j uses data to week j; a, b, sd refitted on data to j every
    13 weeks). Record the filtered position and pace each week from Jan 2019. At each week predict the BTC.D change
    over the next 13 and 26 weeks by carrying the state along the parent; score against what happened (recorded
    weeks only) and against the same forecast from placebo parents and from no-change.
M4. Laws for the pace (fixed list, each must be able to fail):
    L0 constant pace. L1 pace grows exponentially along the parent. L2 own-volatility clock (elapsed realised
    variance of BTC.D). L3 BTC-price volatility clock. L4 market size (log of total market value, child over
    parent). L5 directional-change count on BTC.D (intrinsic time). Placebo clocks: SPX, DXY, EURUSD variance.
    Tests: (i) leave-one-stretch-out error of the log duration over the five stretches, for both readings of the
    top; clock laws in two forms: "explains" (clock elapsed inside the stretch) and "predicts" (clock rate known
    at the stretch's first week only). (ii) Week level: rank correlation between M2's posterior pace and each
    clock's trailing 26-week rate, block-bootstrap band, compared with the placebo clocks. (iii) The general law
    outside the fractal: over every BTC.D swing 2014-2026 (zigzag at 2, 3 and 4 times trailing weekly volatility),
    does volatility known at the swing's start predict how long the swing takes; fitted on swings that ended before
    2021, scored on swings after.
M5. Cross-reference. For the anchors and for month-spaced points on the M2 map: BTC, alts without stablecoins,
    ETH/BTC, USDT.D, total market, XRP, XLM, DOGE, LTC (in USD and against BTC): move over each matched stretch in
    parent and child, direction agreement. Independent M2 maps fitted on BTC price and ETH/BTC: do they slow down
    and speed up in the same child weeks as the BTC.D map (correlation of posterior paces, block bootstrap)?

## Rules
Recorded days only; every hold-out is historical. A law counts only if it beats L0 and the placebo clocks out of
sample; otherwise the answer is "no law found, order of events only". No date is read off any clock unless a law
passes, and then only as a range conditional on the clock's rate. Only the three actual waterfall events count as
waterfalls. Any probability reading is shown next to the 1.96% act line.

## Loop
Evaluator-optimizer, at most three rounds. Critics are single-angle and report blocker or major problems only:
plan critics (statistics; fit to the question) before any run; a number checker that reruns the code and an
interpretation critic after the run; one final check.

## Revision after the plan critics (before any test was run)
Two critics read the plan (statistics, Opus; fit to the question, Sonnet). Changes taken:
1. The "explains" form of the volatility clock is dropped as circular (variance adds up with length). Clock laws are
   tested only with a rate measured over the 26 weeks that end the week before a stretch starts. The stretch table
   still shows elapsed clock per stretch, as description only.
2. M2 nulls now share the model's freedom and the hindsight search: (a) child-side surrogates with the parent held
   fixed (amplitude-adjusted phase-randomised levels, and block-bootstrapped weekly changes), (b) placebo parents
   from every series that is a log value ratio and ends before the child starts (BTC.D and OTHERS.D before the
   parent, LTC, XRP, DOGE, XLM, ETH against BTC), each scanned over start dates and both orientations with the best
   window kept, (c) the rank of the true parent window among all same-length windows of BTC.D before Dec 2017.
   The statistic is the log-likelihood gain per week over a flat fit. b is kept positive and inside a fixed range.
3. The emission is made robust (5% outlier floor) because the parent has one-day index steps; the fit is shown with
   the steps in (the chart as read) and with the steps taken out.
4. The parent runs six weeks past its top in the primary fit (three and twelve weeks as sensitivities).
5. M3 is labelled in-sample as far as the choice of parent goes; its skill counts only against the same forecast
   made on child surrogates.
6. The five-stretch law table gets one family-wide exact permutation test (120 orderings, best law of the whole
   family), and a winning law is worded "consistent with, on five hand-picked stretches", never "law".
7. Week-level pace against a clock is compared with the same number from child surrogates, because the model reads
   pace from the child's own moves.
8. The swing-duration study (M4 iii) is dropped: it is true of any random walk and says nothing about the fractal.
9. M5 becomes a matched-day table with every chart that exists in both eras (coverage listed, gaps marked n/a,
   USDT.D not used in the parent era), key macro charts added (DXY, SPX, US 10-year, M2), and one test per asset:
   does the BTC.D map carry to that asset better than nearby maps. Separate maps fitted on trending prices are
   dropped (two trends align trivially).
10. Added measure M6 (description): speed of each leg in logit per week, waterfalls against the other falls and
    rises, parent and child.
