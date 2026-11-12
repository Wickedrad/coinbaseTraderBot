# OR-HM2 Part 4: structural chart patterns in the weighted curves (design, written before any result)

Written 2026-11-11 ~23:55 UTC (6:55 PM EST). Thread "Find unseen TA confluence via oracle". This is Part 4 of OR-HM2
(python/oracle/prereg/OR-HM2.md; build plan OR-HM2-build-plan.md). It adds one module, its tests and a workflow
stage. It changes no line of heat.py, heat_vocab.py, heat_live.py, heat_xdata.py or heat_hm2.py, and no stored table,
hash, league or pack.

Steven, Nov 11 23:36 UTC (6:36 PM EST): "And further more there should be head and shoulders and inverse head and
shoulders and other structural patterns used in the weighted curves."

Steven, Nov 11 23:33 UTC (6:33 PM EST), the request behind Part 3: "what is the difference between the instances of one
particular pattern or TA or whatever it happens to be that is right more often and/or makes more in profit than the
ones that don't." Part 4 therefore gives every pattern instance its measurements, so the Part 3 drill can ask that
question of patterns too.

The standing rules stay. NEVER DOGE. Coin minutes 2020-01-01 to 2025-12-31 only: build on 2020-2024 (A), check on 2025
(B), and no minute of 2026 is loaded. No pass bar cuts a row: rank, do not gate (sample floors only). The no-signal
twins stand beside every count; marks are columns. Compute runs on GitHub runners (at most 10 jobs at once, 360
minutes per job). Times in Eastern and UTC. Every loser is studied. A pattern that works only under a condition is
kept as a gated row (the pattern and its gate), not dropped.

## What had been seen when this was written
- HM1's league, packs and add-ons (OR-HM1.md, Amendments 1-7). None of them holds a chart pattern: the vocabulary has
  TA-Lib's 61 candlestick patterns only, and it left out TA-Lib's ZIGZAG and FRACTAL because they place a pivot at its
  extreme bar, which is known only after later bars (OR-HM1 Amendment 1, point 13).
- The round 12 study (research/btcd_fractal/ROUND12_PLAN.md, study12_hs.py, out12/hs/results.json): head and shoulders
  on weekly closes of daily TradingView series (BTC.D, USDT.D, ETHUSD and six others), zigzag reversals of 8% and 15%.
  63 real patterns; 42 in play at their confirmation, 21 already through the neckline at the close that confirmed the
  right shoulder. A move of one head height within 26 weeks: 34% of 41 real patterns, 26% matched base, 32% of 6,070
  placebo patterns (IAAFT and matched walks); within 52 weeks 50%, 40% and 46%. None of the four timing laws was
  supported. Reading: the real patterns beat the base about as much as patterns found in noise do, on few independent
  cases.
- No Part 4 code exists. No pattern has been detected on coin minutes or on a twin. No HM2 result exists. Part 3 (the
  winners-versus-losers drill) is being designed beside this; its file did not exist when this was written.

Where an earlier result shaped a choice, this text says so: round 12's tolerances are reused, its 21 patterns that broke
at the confirming close shaped the provisional-pivot rule (Swing points, 3), and its placebo result is why every
pattern row stands beside the twins' rows for the same pattern and frame.

## Why
The weighted curves (HM1's heat strips: per reading level, windows per day × odds points, share right, minutes held,
against the twins) cover indicators and candlesticks. A candlestick is one to five bars. A chart pattern is a shape of
several swings: three peaks with the middle one highest, two equal lows, converging trend lines. Traders draw these by
eye, so they need exact definitions on swing points before the engine can count them, and the swing points must not
repaint.

## Literature, and what is taken from it
- **Lo, Mamaysky and Wang (2000), "Foundations of technical analysis" (Journal of Finance 55(4)).** Smooth each rolling
  window of prices with a Nadaraya-Watson kernel regression (bandwidth 0.3 × the cross-validated one, chosen by eye
  with practitioners), find the extrema of the smooth, map each to the raw price within one day, and test ten
  patterns on five consecutive extrema E1..E5: HS (E1 a maximum, E3 above E1 and E5, E1 and E5 within 1.5% of their
  average, E2 and E4 within 1.5%), IHS (mirror), broadening tops and bottoms (E1 < E3 < E5, E2 > E4), triangle tops and
  bottoms (E1 > E3 > E5, E2 < E4), rectangle tops and bottoms (tops within 0.75%, bottoms within 0.75%, lowest top above
  highest bottom), double tops and bottoms (E1 and the highest later maximum within 1.5%, at least 22 days apart).
  Windows of l + d = 35 + 3 days: the last extremum must fall on day l, so a pattern is detected d days after it
  completes and returns are measured from the window's end. Taken: the ten definitions (literal, as a check frame)
  and the lag idea.
- **Savin, Weller and Zvingelis (2007), "The predictive power of head-and-shoulders price patterns in the U.S. stock
  market" (Journal of Financial Econometrics 5(2)).** LMW's method on 63-day windows, with the bandwidth at 1, 1.5, 2
  and 2.5 × the cross-validated one (not LMW's 0.3), plus Bulkowski-calibrated restrictions: shoulders within 4% of
  their average, troughs within 4% (R4a, R5a); the mean of the two shoulder heights (each shoulder over its own
  trough, E1 - E2 and E5 - E4) between 0.25 and 0.7 of the head's height over the troughs' mean (R6, R7); head at
  least 3% of price above the troughs' mean (R8); the longest spacing between consecutive extrema at most 1.2 × their
  mean spacing (R9); and the neckline crossing: price must fall below the neckline on its way to the next extremum.
  Result (checked against the paper, review): very little support for HS as a stand-alone strategy after costs; a
  risk-adjusted 5-7% a year as a tilt of a portfolio, which "rests in part on its identification of negative momentum
  stocks" (the prior trend matters: the `pre` parameter). Taken: R6/R7 (shoulder heights against the head, here
  measured from the neckline, which is the same when the neckline is flat), the neckline crossing as the signal, and
  their literal HS rule as a check variant.
- **Bulkowski (Encyclopedia of Chart Patterns; thepatternsite.com).** Practitioner rules from thousands of patterns.
  HS top: shoulders near the same price and distance from the head; confirmation is a close below an up-sloping
  neckline, or below the right armpit when the neckline slopes down; target = head height below the breakout (his
  current measure rule scales the height by the share of patterns that reach it, 51% for HS tops, so the catalogue
  also records the half-height target). Flags:
  a steep pole, a short (under 3 weeks) rectangle tilted against the trend between near-parallel lines, target = pole
  height added to the flag's far side. Symmetrical triangles: one line touched at least three times and the other at
  least twice, breakout on average 74% of the way to the apex, heavy breakout volume helps. Taken: the confirmation
  rules, the touch counts, the measure rules, the pole and flag shape, and the parameters he finds matter (breakout
  volume, prior trend, tightness), which become Part 3 columns, not filters.
- **Rink (2025), "The role of technical chart patterns in the early Bitcoin market" (Financial Innovation).** Mt.Gox
  trades April 2011 to September 2013, hourly bars, LMW's five bullish patterns (and their bearish mirrors) on rolling
  72-hour windows at 0.3 × the cross-validated bandwidth, the pattern completed exactly at hour 60 (so that a pattern
  is counted once) and the neckline crossed within the last 12. Buy signals came with more than 53% abnormal volume and
  higher returns on the traders' signal trades. Taken: the intraday window (72 bars, last extremum at bar 60). Its
  market (early, thin, retail, long-only) is not ours.
- **Kuna (2025, Charles University bachelor thesis), candlesticks across crypto datasets:** 8 of 41 candlestick
  patterns showed predictive potential, two of them against their textbook direction. A reminder that direction must
  be measured, not assumed; the engine already does so. One review search (Nov 12, 2026 UTC) found no other study of
  structural chart patterns on crypto minute or hourly bars; Part 4 has no outside intraday result to lean on.

## Swing points without repainting
1. **The zigzag (the main swing detector).** Per frame (a timeframe and a size r): a(t) = the mean true range of the
   100 bars before bar t (a plain mean, so a window gives the same number as the full series). Peaks are priced at
   the bar high, troughs at the bar low. While rising, the running high is tracked; a peak is CONFIRMED at the first
   bar t whose close is at least r × a(t) below it. Falling is the mirror. A bar may set a new extreme and confirm it
   in the same bar only through its close (the close is the bar's last price, so the order is real). This is round
   12's point-in-time zigzag (study12_hs._zigzag), changed in two ways: highs and lows instead of closes, and a
   threshold in ATR instead of a fixed percentage.
   - **Intrabar order (review).** Round 12 restarted the new leg at the confirming close. With highs and lows, the
     order of a bar's high and low is unknown, so the new leg's running extreme starts from the bars AFTER the
     confirmed pivot's extreme bar: when a peak is confirmed at bar t, the falling leg's running low is the lowest low
     of the bars after the peak's bar up to t, or c[t] when the peak's bar is t itself. A trough is therefore never
     placed at the low of the bar that made the peak (that low may have come first). Mirror for troughs.
   - **Exact threshold (review).** On a coin's tick-unit bars every price is a whole number, so the 100-bar sum of
     true ranges S(t) is an exact integer (int64), and the test is 100 × (running high - c[t]) ≥ r × S(t) in integers.
     On a series off a grid (the twins' 12-digit prices) S(t) is a direct sum of the same 100 values in the same
     order, never a difference of cumulative sums, so a window and the full run compare the same float numbers.
   - **Start and gaps.** The zigzag starts undecided (as round 12) at the first bar with a known a(t). A stale bar
     (Timeframes) resets it to undecided and ends every alive instance of the frame at that bar (no later event; the
     codes already written stay); it restarts at the first bar that is not stale (by then a(t) reads no gap bar).
2. **What is known at bar t.** The pivots confirmed at or before t (each with its extreme bar and its confirmation bar),
   the direction of the current leg, and its running extreme (the PROVISIONAL pivot). Nothing else. A confirmed pivot
   never moves or disappears later. TA-Lib's ZIGZAG and FRACTAL return the pivot on its extreme bar, which is why the
   vocabulary left them out; here a pivot exists only from its confirmation bar.
3. **When a pattern exists, and the signal.** A template names k consecutive pivots. A pattern instance exists from the
   bar at which its first k - 1 pivots are confirmed and the running extreme of the current leg, taken as the last
   pivot, passes every check ("forming"). It is "formed" when that last pivot is confirmed. The trade signal is the
   first bar close beyond the neckline or boundary, at or after the bar the pattern began to form, with every check
   passing on the last pivot as it stands at that bar (confirmed or provisional). Entry is the next minute's open, as
   in the engine. Round 12 found a third of its patterns already through the neckline at the close that confirmed the
   right shoulder (the reversal r was larger than the drop to the neckline); waiting for the zigzag would have
   reported those breaks late. With the provisional rule the break is reported at its own close, and still uses no
   later bar. Rules that keep this exact (review):
   - An instance is dated at its first event bar. Every pivot carries both its extreme bar and its confirmation bar;
     a trigger line is drawn only from the bar its pivots were confirmed (the viewer follows this).
   - "Formed" fires only when the last pivot is confirmed before any break; a break while it is provisional is followed
     by retest, target and failure only.
   - An instance that stops passing its checks after it began forming ends and never comes back. When the running
     extreme passes the farthest admissible price (an overrun), the instance ends at that bar; the wrong-way break
     fires there only if the bar's close is beyond that price too.
   - The invalidation level is frozen at the break bar.
   - Nothing once emitted is withdrawn: precedence (Pattern set) is decided at each bar among the instances that share
     the same last pivot, and a later, larger pattern never removes an earlier one's codes.
4. **The proof.** A test cuts each synthetic series at five bars, replaces everything after the cut with fresh noise
   (three draws), recomputes every pattern reading, and requires the codes of every bar that closed at or before the
   cut to be unchanged, for every reading, frame and timeframe (Tests, 1). It also requires the pivot lists confirmed
   by the cut, and every instance field known by the cut, to be unchanged. A negative control runs the same test on a
   kernel smoother fitted once to the whole series and requires it to FAIL, so the test is shown to catch repainting.
   A second negative control places a pivot at its extreme bar (TA-Lib's ZIGZAG convention) and must also fail.
5. **The kernel method (LMW), compared.** A Nadaraya-Watson smoother is two-sided: the smoothed value at bar s uses bars
   after s. Fitted once to a whole series (as many re-implementations do), its extrema use the future, so patterns
   appear at bars before their data. LMW avoid this with rolling windows and the lag d, measuring returns from the
   window's end; in that form the detection is causal. It still redraws the past: an extremum at a given bar can be in
   one window's smooth and not in the next one's, the bandwidth is re-chosen per window by cross-validation, the 0.3
   factor was picked by eye on daily stocks, and the cost is per window rather than per bar.
6. **Which is used, and why.** The ATR zigzag is the main detector: causal by construction, linear in bars, one
   parameter r that is exactly the size axis Steven wants to see, a streaming state that a live reader can carry
   forward exactly, and the detector round 12 already tested point in time. The kernel method runs too, in its causal
   rolling form with LMW's literal definitions, on three timeframes (frame K below), so the literature's own detector
   has its own curves beside ours. It never feeds the main frames.

## Timeframes and swing scales
- **Timeframes:** 5, 15, 60 and 240 minutes. Bars are heat.resample of the engine's tick-unit bars, aligned to UTC
  midnight like the engine's, so 4-hour bars close at 00, 04, 08, 12, 16 and 20 UTC (7 PM, 11 PM, 3 AM, 7 AM, 11 AM and
  3 PM EST; one hour later in EDT). A bar that holds a forward-filled minute, and the engine's STALE / STALE_LONG bars
  after it, carry no reading; a stale bar ends every alive instance at that bar (Swing points, 1: dropping the
  instance would erase codes already written, which is repainting). The first 250 bars carry none. On 4-hour bars the
  engine's rule is heavy: one forward-filled minute blanks the next 100 bars (about 17 days), an outage over 14 bars
  (56 hours) the next 500 (about 83 days). The rule is kept as the engine's; the bench prints the stale share of
  every timeframe on A and B, and the anatomy table carries it, so a thin 4-hour frame is seen, not hidden.
- **1-minute bars are left out.** ATR grows about as the square root of the bar length, so a 1-minute swing of 8 ATR is
  about a 5-minute swing of 3.6 ATR (covered by the 5-minute frames), and the smaller 1-minute swings are a few price
  steps on XRP and SOL in their cheap years and sit inside bid-ask bounce. A 1-minute frame can be added later if the
  5-minute r = 2 rows lead the scale map.
- **Sizes:** r = 2, 4 and 8 ATR on every timeframe: 12 zigzag frames, named `z2`, `z4`, `z8`. In units of the 1-hour
  ATR they span about 0.6 (5m z2) to 16 (4h z8), each size seen at two or three bar resolutions. That grid is the scale
  map of What is reported.
- **Kernel frames (`K`):** 15, 60 and 240 minutes, LMW's literal method (Readings, 6).
- **Expected leg lengths (a guide only; the bench prints the real ones).** For a driftless random walk the mean time to
  a reversal of R is R² / σ² bars, and a bar's true range averages about 1.6 σ. So a leg of r ATR lasts about
  2.6 r² bars: 10, 41 and 164 bars for r = 2, 4, 8. In time: 5m about 50 minutes, 3.4 hours and 14 hours; 4h about 1.7,
  7 and 27 days. A five-pivot pattern spans four legs. At 4h z8 a coin forms a few dozen five-pivot windows in six
  years: few cases (Known limits).

## The pattern set
**Common rules.** Each template is written for the top; its mirror (the bottom) is the same rule on the price path
turned upside down (highs and lows swap). Pivots are consecutive in the frame's zigzag.
- **Duration:** first pivot to last pivot at least 2 bars per leg and at most L_MAX = 20 r² bars (80, 320 and 1,280
  bars for r = 2, 4, 8, about twice the mean span of four random-walk legs).
- **Size:** every leg is at least r × ATR by construction; the pattern's height h must be at least r × a at the bar it
  forms. Height in ATR is a parameter.
- **Life:** no break within EXPIRE = min(100, max(10, span / 2)) bars after the bar the instance formed (its last
  pivot's confirmation bar) ends the instance silently. A forming instance (last pivot provisional) ends when its
  checks stop passing or when its first pivot is more than L_MAX bars back. After a break, retest, target and failure
  are watched for POST = min(100, max(20, span)) bars. So every instance lives at most L_MAX + EXPIRE + POST bars from
  its first pivot, and nothing extends that (no extra touch, no continuation).
- **Events** (each at most once per instance): formed; break up / break down (the first close beyond the trigger level
  on that side); retest (within 20 bars of the break, a bar whose extreme comes back within 0.25 × a of the trigger
  line and whose close stays on the break side, before any close back through it); failure (after a break, a close
  beyond the invalidation level: the break went the wrong way); target (after a break, a bar whose extreme reaches the
  measured-move target before failure).
- **Before the textbook break,** a close beyond the invalidation level is the wrong-way break ("break up" for an HS
  top). While the last pivot is provisional, the invalidation level is the farthest price it may reach with every check
  still passing (for HS, the highest admissible right shoulder); once it is confirmed, it is that pivot. Both are known
  at the bar.
- **Lines through a provisional pivot (review).** For the line patterns (triangles, wedges, rectangle, broadening) the
  line fitted through a provisional E5 moves with price, so a close beyond it is not a break. While E5 is provisional,
  the break on E5's side is a close beyond the farthest price E5 may reach with every check passing (as for HS), and
  the break on the other side uses the line through confirmed pivots only. Once E5 is confirmed both lines are fixed.
  Every trigger line of every template is thus made of confirmed pivots, or is an admissibility bound.
- **Overlapping instances (review).** Every pivot set that passes is an instance; there is no duplicate guard in the
  readings. (A guard that suppresses a candidate because an earlier one is alive chains: whether the third set fires
  depends on whether the second was suppressed by the first, so a window that starts after the first gives other
  codes than the full run.) A set that shares at least k - 2 pivots with an earlier alive passing set of the same
  pattern is flagged `cont` in the catalogue, computed from all passing sets whether or not they were flagged, and the
  anatomy table counts the distinct (unflagged) instances beside the total. Same-bar events of overlapping instances
  collapse by the readings' priority rule.
- **Outcome base (review).** The chance of reaching a target before an invalidation level is set by geometry alone in
  a driftless walk: p_rw = d_inv ÷ (d_inv + d_tgt), the distances from the break close to the invalidation level and
  to the target. Each broken instance carries p_rw and `tbi`: whether a minute close reaches the target before a
  minute close reaches the invalidation level (both on closes, so the two barriers are judged alike; no time limit but
  the end of the instance's split, NA if neither is reached by then). Every `tbi` share is shown beside its mean p_rw
  and beside the twins' share. This is round 12's equal-move base in the engine's terms. (The `target` event, which a
  bar's extreme can trigger, is a moment for the curves, not this comparison.)
- **Direction is measured, not assumed.** Every pattern has both break levels. The textbook direction (HS: down) is a
  column, and the league shows how often the textbook was right.
- **Near misses.** Pivot sets that fail exactly one check are tracked by the same code and kept in the catalogue with
  the failed check and its margin. They never enter a reading. The drill can then ask whether a check matters.

**Pivot templates** (h = height; NL = neckline; touch tolerance and slopes in units of the pattern's own height):

| pattern | pivots | checks | trigger | invalidation | target |
|---|---|---|---|---|---|
| `HS` head and shoulders top; `IHS` its mirror | S1 T1 H T2 S2 (peak first) | NL through T1, T2; h = H - NL(H) > 0. Mean shoulder height above NL in [0.25, 0.7] h, each above NL (Savin R6, R7); the head at least 0.2 h above the higher shoulder (Bulkowski's head "perched atop"). \|S1 - S2\| ≤ 0.5 h, NL rise from S1 to S2 ≤ 0.5 h, right span ÷ left span (H to S2 over S1 to H) in [1/3, 3] (round 12) | close below NL when NL rises, below the T2 level when NL falls (Bulkowski) | highest admissible S2, then S2 | trigger at the break - h |
| `DTOP` double top; `DBOT` | P1 V P2 | d = mean(P1, P2) - V; \|P1 - P2\| ≤ 0.2 d; P1 to P2 at least 8 bars; not at a bar where a TRITOP passing on the same last pivot holds (decided bar by bar; an earlier DTOP is never removed) | close below V | highest admissible P2, then max(P1, P2) | V - d |
| `TRITOP` triple top; `TRIBOT` | P1 V1 P2 V2 P3 | d = mean peaks - mean valleys; peaks' range ≤ 0.2 d; \|V1 - V2\| ≤ 0.4 d; leg spacing ratios in [1/3, 3]. Takes precedence over the double tops inside it; a set that passes both this and HS is an HS | close below min(V1, V2) | highest admissible P3, then the highest peak | trigger - d |
| `ASCTRI`, `DESCTRI`, `SYMTRI` triangles; `RISWEDGE`, `FALWEDGE` wedges; `RECT` rectangle; `BROADTOP`, `BROADBOT` broadening | E1..E5, either type first (3 touches on one line, 2 on the other) | upper line U by least squares through the peaks, lower L through the troughs; H0 = U - L at E1 > 0; every pivot within 0.15 H0 of its line; su, sl = each line's rise over the span ÷ H0. ASCTRI \|su\| ≤ 0.15, sl ≥ 0.3. DESCTRI \|sl\| ≤ 0.15, su ≤ -0.3. SYMTRI su < -0.15, sl > 0.15. RISWEDGE su > 0.15, sl ≥ su + 0.15. FALWEDGE sl < -0.15, su ≤ sl - 0.15. RECT \|su\|, \|sl\| ≤ 0.15. Broadening su > 0.15, sl < -0.15, named by E1's type (LMW). The bands do not overlap. Converging lines must meet after E5, and the break must come before the apex | close above U(t) (up), below L(t) (down) | the opposite line | break price ± H0 (broadening: ± the height at E5) |
| `CUP` cup and handle; `INVCUP` | R1 B R2 HL (HL = the handle low) | D = min(R1, R2) - B; \|R1 - R2\| ≤ 0.2 D; R1 to R2 at least 20 bars; B in the middle half of the cup; the cup's closes fit a quadratic with curvature > 0 and R² ≥ 0.6 (a U, not a V); handle depth R2 - HL ≤ 0.5 D and in the cup's upper half; handle length ≤ half the cup's | close above R2 | close below B + 0.5 D; after the break, below HL | R2 + D |
| `ABCD.BULL`, `ABCD.BEAR` | A B C D | bull: A peak. BC ÷ AB in [0.382, 0.886]; CD ÷ AB in [0.9, 1.1] (the PRZ); CD's bars ÷ AB's bars in [0.5, 2] | "formed" when a bar's low first brings D into the PRZ; break up = the zigzag confirms D inside the PRZ | close below the PRZ (CD = 1.1 AB); after the break, below D | D + 0.618 (C - D) |
| `HARM.BULL`, `HARM.BEAR` (Gartley, bat, butterfly, crab) | X A B C D | bull: X trough. b = AB ÷ XA, c = BC ÷ AB in [0.382, 0.886], d = AD ÷ XA. Gartley b 0.618, d 0.786; bat b 0.382-0.5, d 0.886; butterfly b 0.786, d 1.27-1.618; crab b 0.382-0.618, d 1.618; point values ± 0.03. The variant is a column | as ABCD, with the variant's D band | close beyond the band's far edge + 0.03 XA; after the break, beyond D | D + 0.618 (A - D) |

**Bar templates** (shapes that a single zigzag size cannot see as pivots):
- **`BULLFLAG`, `BEARFLAG`, `BULLPEN`, `BEARPEN`.** Pole: the current zigzag leg from its confirmed trough L0 to its
  running (or just confirmed) high P0, at least 2 r × a tall and rising at least 0.5 a per bar. Flag: the bars after
  P0, 3 to 20 of them, with no new high above P0, retracing more than 0 and at most half the pole. Lines: least squares
  of the flag bars' highs (upper) and lows (lower), fitted on the bars before the current one. Flag: both slopes
  between -0.5 and +0.1 × the pole's slope (flat or tilted against the pole) and within 0.25 × the pole's slope of each
  other (parallel). Pennant: upper slope < 0 < lower slope, each at most half the pole's. Tight: every flag bar within
  0.5 a of its line. Pennant takes precedence. Forming with 3-4 bars, formed at 5. Break up: close above the upper
  line extended to the bar; break down: close below the lower line. Failure: after the up break, a close below the
  flag's low. Target: the flag's low + the pole (Bulkowski). More than 20 bars without a break ends it. Bear: mirror.
- **`ROUNDBOT`, `ROUNDTOP`.** R1 a confirmed peak, B the low after it, no confirmed peak since B. The closes from R1 to
  the bar fit a quadratic with curvature > 0, R² ≥ 0.8 and its vertex in the middle 60% of the span; span at least 20
  bars; R1 - B ≥ 2 r × a. Formed when B is confirmed with every check passing. Break up: close above R1. Break down:
  close below a confirmed B. Failure: after the break, a close below the midpoint of R1 and B. Target: R1 + (R1 - B).
  A cup has a handle (R2 and HL); a rounding bottom has none, so the two never share an instance.

**Structure** (on every zigzag frame):
- **`STRUCT`** (a state): from the last two confirmed peaks and troughs, `up` (higher high and higher low), `down`,
  `expanding` (higher high, lower low) or `contracting` (lower high, higher low). Unknown until two of each exist.
- **`BOS`** (an event): the first close above the last confirmed peak or below the last confirmed trough (each pivot
  can be broken once): `CHoCH up` / `CHoCH down` when it goes against an `up` or `down` STRUCT, `BOS up` / `BOS down`
  otherwise (with the trend, or when STRUCT is expanding, contracting or unknown) (the crypto "break of structure" and
  "change of character"). BOS is also the shapeless control of the breaks: an HS break down is a close below a recent
  swing level with a shape around it, and each pattern break row is shown beside the BOS row of the same frame and
  direction (What is reported, 1), so the curves say whether the shape adds anything to a plain swing break.

**Left out, with reasons:** diamonds (a broadening followed by a triangle; both parts are readings, and nine-pivot
shapes are rare); complex head and shoulders (several shoulders; no fixed rule); bump-and-run (a trend-line steepness
rule with no fixed anchor); island reversals and gaps (crypto trades around the clock); V-tops and spikes (no rule
beyond one large leg, which the vocabulary's bar-size readings and the zigzag legs already cover); channels (STRUCT,
RECT and the vocabulary's regression readings); three drives and wave counts (count-dependent); Adam-and-Eve
variants (shape subtypes of double tops; the symmetry parameter carries the idea).

That is 26 patterns plus STRUCT and BOS per zigzag frame. All thresholds above are fixed here, before any detection on
coin or twin minutes. They come from the literature, from round 12, or from the random-walk leg lengths, and they are
definitions, not pass bars: no row is cut after it is measured.

## Readings in the engine's format
Every reading is the engine's dict {'name', 'k', 'codes', 'levels', 'base', ...} on its timeframe's bar grid (k = 5,
15, 60 or 240), codes known at the bar's close, -1 where stale or unknown. So heat.read_state, event_levels and
level_events work on them unchanged, and so do the HM2 pair kernel and the Part 3 drill. Family `chart`.

1. **Event readings**, one per pattern and frame: `{k}m:CHART.{frame}.{P}` (for example `60m:CHART.z4.HS`), flag
   'every' (as a candlestick: each bar it fires is an event). Levels: none, formed, break up, break down, retest,
   failure, target. Two instances firing on one bar: break > failure > target > retest > formed, then the older
   instance; the hidden events are counted in meta.
2. **State readings**: `{k}m:CHART.{frame}.{P}.state`, a categorical condition. Levels: none, forming, formed, broken
   up, broken down, broken both, target reached, failed. "Broken" holds for STATE_N = 20 bars after the break unless
   the target or a failure comes first; "target reached" and "failed" hold for 20 bars. Priority across instances:
   broken > failed > target reached > formed > forming.
3. **Structure**: `{k}m:CHART.{frame}.STRUCT` (a categorical condition) and `{k}m:CHART.{frame}.BOS` ('every').
4. **Compact readings** (for the pair scan): `{k}m:CHART.{frame}.ANY` ('every'): none, `<P> up` and `<P> down` for each
   pattern's break, `several up`, `several down`, `conflict`; and `{k}m:CHART.{frame}.BIAS` (a condition) from the
   instances in a broken state: none, up 1, up 2+, down 1, down 2+, mixed.
5. **Parameters** (for the pair scan and as other units' conditions in the Part 3 drill):
   `{k}m:CHART.{frame}.p.<name>`, conditions with no neutral level, describing the frame's current instance (the one
   with the latest event within 20 bars; ties by the event priority, then the older instance), NA otherwise. When two
   patterns of one frame have events on the same bar, this reading shows one of them, so it is not a pattern's own
   column (review): a chart unit's own shape columns come from the catalogue (What is reported, 9), where every event
   row carries its instance id and the instance's values, and the meta counts per frame the bars where the shown
   instance differs from another event's instance on that bar.
   - `height`: the pattern's height ÷ a;
   - `span`: bars from the first to the last pivot;
   - `sym`: symmetry from 0 to 1 (HS: the mean of 1 - \|S1 - S2\| ÷ 0.5 h and 1 - \|log(right span ÷ left span)\| ÷ log 3;
     double and triple tops: 1 - peak spread ÷ its limit; triangles and wedges: leg spacing; cups: rim and bottom
     placement; NA for flags);
   - `slope`: the trigger line's rise over the span ÷ the height, signed;
   - `pre`: the move into the first pivot from the far extreme of the min(2 × span, 500) bars before it, ÷ a
     (Bulkowski's prior trend; the cap keeps the live window bounded, Live reader);
   - `bvol`: the break bar's volume ÷ the mean bar volume of the pattern;
   - `bdist`: how far the break bar closed beyond the trigger, ÷ a;
   - `tdist`: distance from the close to the target, ÷ a, in the break direction;
   - `age`: bars since the break.

   height, span, sym, slope, pre, bvol and bdist get five levels at the quintiles of split A's instances (one value
   per instance, pooled over the frame's patterns; the edges go to meta). The value of an instance is the one known
   at its first break (at "formed" if it never broke, at its last forming bar if neither), and an instance is an A
   instance when that bar's row is in A. tdist has fixed levels (past target, 0-1, 1-2, 2-4, over 4 ATR) and age too
   (0, 1-2, 3-5, 6-10, 11-20 bars).
6. **Kernel frames** `K` on 15, 60 and 240 minutes: LMW's ten patterns with their own names (`CHART.K.LMW.HS`, IHS,
   BTOP, BBOT, TTOP, TBOT, RTOP, RBOT, DTOP, DBOT) and Savin's HS and IHS (`LMW.HS.SWZ`, `LMW.IHS.SWZ`, with R4a-R9 and
   the neckline crossing). Rink's intraday form: each window of 72 bars is smoothed with a Gaussian Nadaraya-Watson
   kernel at 0.3 × the leave-one-out cross-validated bandwidth (grid of 20 values from 0.5 to 20 bars; a CV tie goes to
   the smaller bandwidth); the SWZ variant uses 1.0 × the cross-validated bandwidth, their own base multiple (review:
   0.3 is LMW's factor, not theirs; their 1.5, 2 and 2.5 multiples are left out). Extrema of the smooth are mapped to
   the raw high or low within one bar; the pattern's five extrema must end at the window's bar 60 (for DTOP and DBOT:
   the first extremum of the window and the highest later maximum, or lowest later minimum, which must be at bar 60).
   It is "formed" at the window's last bar (a 12-bar lag). Rink's bar-60 rule alone does not make a pattern appear
   once: the next window is smoothed again and can move an extremum by a bar, so the same shape can end at bar 60
   twice (review). A class reported within the previous 12 bars with every extremum within 2 bars of the new one is the
   same instance (a window-local memory of 84 bars, so parity holds). The break is the first close beyond its
   neckline or boundary at or after that bar (a crossing inside the lag fires the break at the window's last bar,
   flagged; Rink requires the crossing inside the 12 bars, kept as a column). Tolerances in percent of price as
   published; double tops at least 10 bars apart (Rink's hourly choice). Event and state readings, ANY, BIAS and the
   nine parameters as above.
7. **Bases.** Every reading of a frame shares the base `{k}m:CHART.{frame}`, so the pair scan never pairs a frame's
   readings with each other (they are one detector). Parameter readings get their own name as base, so the drill can
   split a pattern's events by its own parameters.
8. **Counts.** Per zigzag frame: 26 event + 26 state + STRUCT + BOS + ANY + BIAS + 9 parameters = 65 readings, 780 over
   12 frames. Per kernel frame: 12 + 12 + 2 + 9 = 35, 105 over 3. 885 readings per coin. The pair scan uses only the
   compact set: ANY, BIAS, STRUCT and BOS of each zigzag frame and ANY and BIAS of each kernel frame, 54 readings.
   The meta lists the sha256 of every reading's codes, so Part 3, which rebuilds the readings with the same call
   (heat_patterns.pattern_readings), can check it has the same ones.
9. **Copies.** Agreement of 99.5% over A entries where both are known would merge any two rare readings, because both
   say "none" almost everywhere. HM2's code already counts agreement only where at least one of the two is off its
   neutral level (heat_hm2.merge_aliases, checked at review), so Part 4 calls it unchanged on its own readings, and no
   message to the HM2 lane is needed.

**Entries, labels and horizons.** The engine's and HM2's: next minute's open, dead band of 1.5 price steps, horizons
1, 5, 15, 30 and 60 on the 60-minute grid and 240 on its own grid (A rows end 240 minutes before 2025). An event of a
4-hour reading enters at the minute after its bar's close, like any other event.

## Twins
The joint coin-flip twins of OR-HM2 (seeds 1, 2, 3; each minute's direction a coin flip; size, range, volume and time
kept) run the identical detectors, frames, readings, statistics and catalogue on their own bars. Random walks form
head and shoulders, flags and triangles too; that is the chance scale beside each pattern's curve. The twins' pattern
edges (parameter quintiles) are their own, as for every other reading. Volume is real on a twin, so the break-volume
parameter is chance there. Chart readings use the job coin's own bars only.

## What is reported
1. **Pattern curves** (the weighted curves). For every event level of every pattern and frame, through
   heat.level_events and g.full (g240.full at 240): per horizon, events, days, windows per day, share right on A and
   B and over base, odds points and day-clustered t, heat (windows per day × odds on B, signed by A's direction),
   minutes held and over base, best move, usual dip, retL (entered a minute later), move in price steps. State levels
   are also measured held (every minute the state holds). Beside each row: the same row on the three twins (median and
   range), the textbook direction, and for a break level the BOS row of the same frame and direction with the
   difference in odds (`shape_lift`, a column: does the shape add to a plain swing break?).
2. **Scale map.** Per pattern and event: B heat and share right on a 4 × 3 grid (timeframe × r), the kernel row
   beside, each with the twins' best for the same cell. This is how the owner sees which scale matters.
3. **Anatomy and chance table.** Per pattern and frame, real against the twins' median and range: instances per day on
   A and B (distinct and with continuations), share that broke (and which way), share that failed, reached the target
   (and the half target) before the invalidation or expired, `tbi` minus the mean p_rw, median span and height,
   collisions hidden, the stale share of the timeframe. A frequency far from the twins' says the coin's swings are not
   a coin flip at that scale (for example more double tops where prices mean-revert), which is information in itself.
   **The family (review).** Patterns × frames × levels × horizons (and the pairs) are one large multiple-testing
   family. Per horizon and kind (chart, chart_held, chart_param, chart pairs), the table prints the number of rows with
   a sample and the number carrying each mark (hot on A, replicated on B, BHY, above the twins' max) on the coin and
   on each twin, run identically. That count against the twins' counts is the evidence; no mark removes a row.
4. **Parameter curves.** Per pattern, frame and break level, the odds at 15, 60 and 240 minutes by quintile of each
   parameter (that pattern's own A quintiles), from the catalogue's instances, beside the twins'.
5. **Losers.** Per pattern, frame and event level (every level, not only the breaks) at 15, 60 and 240 minutes: the
   instances that went the wrong way, against those that went right: counts, parameter medians, p_rw, and how the
   losers ended (failure, retest, stall = neither failure nor target within the horizon), beside the twins' same
   table. Every instance goes to the Part 3 drill.
6. **Pairs (gated dynamics).** The 54 compact readings, each paired with every engine and HM2 reading of another base
   and with the compact readings of other frames: about 79,000 pairs per coin, with HM2's kernel, measures (oheat,
   iheat with iota_robust, lheat), lists (40 / 40 / 20, at most 3 rows per reading, near-copies collapsed) and twins.
   A pattern that works only under a condition (an HS break while the 4-hour STRUCT is down; a flag break on high
   volume) is kept as that gated row. A pattern's own frame is never its gate (same base).
7. **Lists and the league section.** A "Chart patterns" section of the HM2 league, in this order: the chance table, the
   scale map, the singles lists (per coin and horizon, the 40 best by heat and the 20 best by share over base at 0.2
   windows a day or more, at most 3 rows per pattern), the pair lists, the parameter curves of the listed rows, the
   loser tables, and each coin's top rows in words with the twins' best, for example: "1h, swings of 4 ATR, head and
   shoulders, neckline broken: down, 54% right on 2025 at 60 minutes, 0.3 windows a day (twins' best: 52%, 0.3)".
   Every level with a sample is a row of chart_all.csv.gz; the floors (30 events on 30 days of A, 30 on 20 days of B)
   decide only which rows enter the ranked lists, and the rows under them are counted and kept. Marks (hot on A,
   replicated on B, BHY at q 0.10 within kind and horizon, above the twins' max) are columns.
8. **Pack.** research/oracle_heat/latest/chart_pack.json (schema `oracle-heat-chart-pack-1`, allow_nan False) with its
   own chart_live_meta.json: the singles and pair lists at 15, 60 and 240 minutes, each row with frame, pattern,
   event, conds, fire = onset (entry at the next minute's open), the twins' scale, above_twin_max and live_ready. It
   touches no other pack.
9. **Catalogue for the viewer and for Part 3.** Every instance (an instance id; pivots with price and the UTC ms of
   both their extreme bar and their confirmation bar; lines as two end points and the bar from which each is known;
   events with bars and times in UTC and Eastern and the minute row of each; target, half target, invalidation, p_rw,
   parameters as known at each event, near-miss check, `cont`, height in price steps, and outcomes: the engine labels
   at the event row, the target and the half target reached before the invalidation within 60, 240 and 1,440 minutes,
   best and worst move in ATR within 240 minutes; any outcome window that crosses the end of its split is NA). Part 3
   joins its chart units' rows to this by (frame, pattern, event row) and takes their own shape columns from it, with
   that pattern's own A quintiles. The full catalogue goes to Drive. The repo gets, per pattern and frame on each real coin, one winner and one
   loser from 2025 and one twin example, each with the frame's bars from 20 bars before the first pivot to 40 after the
   break, so the viewer can draw the chart, the lines and the outcome.

## Compute and job placement
**Per series (one coin or one twin), estimated; the bench measures it.**

| stage | work | time | memory |
|---|---|---|---|
| bars and ATR | 4 timeframes: about 631,000 / 210,000 / 53,000 / 13,000 bars | under 1 min | small |
| zigzag | 12 frames, one numba pass each (linear in bars) | seconds | small |
| kernel frames | about 276,000 windows × 20 bandwidths × 72² as BLAS products | about 1 min | +0.5 GB in chunks |
| templates | at each new pivot, the k-pivot sets ending there are checked (vectorised over all pivots); each candidate is then followed bar by bar over its life (at most about 1,500 bars) in numba | 1-3 min | small |
| flags, rounding, structure | bar loops in numba with running sums | 1-2 min | small |
| readings, parameters | 885 int8 arrays on their bar grids | 1 min | +0.3 GB |
| singles | 885 readings × about 6 levels × 2 splits × 2 grids; events are rare | about 5 min | |
| pairs | about 79,000 pairs on HM2's kernel; the chart reading leads (few non-neutral entries) | 5-20 min | |
| re-measure, catalogue, outcomes, writes | top 200 per horizon and measure; every instance, written frame by frame (near misses and continuations can make 5m z2 hold several hundred thousand rows; the bench prints the count) | about 5 min | +0.5 GB |
| **total** | | **20-35 min** | **+2 GB** (no copy of HM2's 1.3 GB code matrix or its totals) |

**Placement.** The pattern stage reads only what an HM2 series job already holds (minutes, labels, both grids, the
readings, the entries and their code matrix) and writes under its own folder. Its numbers do not depend on where it
runs, and it changes no HM2 output.
- **Route A (preferred):** a stage at the very end of each HM2 series job, after HM2's meta.json is written (review:
  any earlier, and a change to ctx could reach HM2's own files), behind a `--patterns` flag. It runs only in a job
  that runs HM2's re-measure: the whole series (S = 1), or the `finish` job after a `--part i/S` split; the part jobs
  never run it. It adds 20-35 minutes to a job of 75-125 (well under the 330-minute timeout) and about 40 to 70
  minutes of wall time over the two waves (16 jobs, max-parallel 9). If the bench projects HM2's job plus the stage
  over 300 minutes, route B is used. This needs one call and one flag in heat_hm2.py, made by the HM2 lane before its
  full run.
- **Route B (if HM2's full run is pushed without the hook):** its own tagged run, `[heat-hm2-patterns:43030435253]`,
  with the same 16-job matrix at max-parallel 9. Each job rebuilds HM2's base (about 14 minutes) and runs the stage:
  about 1.5 to 2 hours of wall time and 12 runner-hours. Under the one-study-at-a-time rule, it waits until no other
  oracle-hm2 run is in progress.
- **League:** the chart section is built by its own league step from each series' small files (chart summary counts,
  candidates, chart_heat.csv.gz, anatomy, catalogue samples) and is committed with the HM2 league or after it.

## Live reader and parity
- **Window reader:** `heat_patterns.levels_at(window, chart_live_meta, names)` runs the same code on the last 3,000
  bars of each timeframe (heat_live's WINDOW_BARS; 5m: 10.4 days of minutes, 15m: 31 days, 1h: 125 days, 4h: 500
  days), plus heat_live's STALE_BACK bars before them for the gap mask. The oldest bar a code at bar t can read, at
  r = 8 (review: the draft's 2,500 did not hold `pre`, which read back 2 × span = up to 2,560 bars before the first
  pivot): STATE_N 20 + POST 100 + EXPIRE 100 + L_MAX 1,280 to the first pivot, + `pre` 500, + about 500 bars for the
  zigzag to synchronise, + the 100-bar ATR = about 2,600 bars. It returns the codes at the last closed bar of each
  timeframe. The ATR sum is exact, the kernel is window-local (with its 12-bar repeat memory), no instance depends on
  another (no duplicate guard), and every instance's life is bounded, so a window agrees with the full run once its
  zigzag has synchronised. The bot must hold 500 days of minutes for the 4-hour frames, or use the stream reader.
- **Why a window synchronises.** Two zigzag runs that start at different bars are the same run from the first bar at
  which they are on the same leg with the same running extreme, because the update reads only that bar, the state and
  a(t), and a(t) reads only the 100 bars before t. In practice that happens within two or three legs (at most about 500
  bars at r = 8). This is an argument, not a proof: the parity job measures the rate.
- **Stream reader (exact):** `heat_patterns.PatternStream`, a state that can be saved as JSON and updated bar by bar,
  seeded from the full history. On the same feed it is exact by construction. It is offered to the bot lane; the window
  reader is the check.
- **Parity job:** on Dec 29-31, 2025 (Dec 28, 7 PM EST to Dec 31, 7 PM EST), every chart reading of the pack's rows from
  a window against the full run. A row is live_ready at 99.5% agreement or more and when the bot has its minute feed.
  As in HM1, a live feed from another exchange will not always give the same pivots.

## Tests (synthetic minutes, patched SPLITS, procs = 1)
1. **No repainting.** Five cut points per series, three noise draws after each cut, and once a forward-filled gap
   right after the cut: the codes of every chart reading (event, state, structure, compact, parameter, kernel) for
   every bar closed at or before the cut are unchanged; the pivots confirmed by the cut are unchanged, and the
   provisional extreme at the cut is unchanged; every instance field known by the cut is unchanged. Negative controls:
   a kernel smoother fitted once to the whole series, and pivots dated at their extreme bar, each fail the same test.
   Also: a bar that sets a peak and confirms it by its own close never gets the next trough at its own low; the
   integer threshold gives the same pivots on a window and the full series.
2. **Planted patterns.** For each of the 26 patterns, STRUCT, BOS and the LMW frame: a path through planted pivots (with
   small noise and 300 warm-up bars) is found with the planted pivots (± 1 bar), the planted neckline or lines (slope
   within 2%), the planted height, and the break exactly at the first bar whose close crosses the planted trigger. An
   HS whose neckline is closer to S2 than r × ATR breaks before S2 is confirmed: the break comes at its own bar, and
   "formed" never comes before it or after it. A triangle whose E5 is provisional never breaks on E5's side through
   the line fitted through E5, only beyond E5's admissible bound. A planted pattern that misses one check by a hair
   appears as a near miss with that check named. A planted run of overlapping triangles gives one distinct instance and
   flagged continuations, and the same codes from a window that starts inside the run. A planted kernel pattern is
   reported once even when the next window's smooth moves an extremum by a bar. The same paths through minutes and
   heat.resample give the same instances on the 15m and 4h grids.
3. **Noise.** A random-walk coin (volatility clustering and a daily cycle) and its twin: per pattern and frame with at
   least 200 instances, the coin's frequency ÷ the twin's lies in [0.8, 1.25]; the share of pattern levels that keep
   their A direction on B lies in 0.45-0.55; under 1% of levels have \|t_B\| ≥ 3; the target-before-invalidation share
   (`tbi`, decided instances) lies within 4 points of the mean p_rw for every pattern and frame with at least 200
   breaks. Positive control: a coin
   with planted mean reversion at 15 minutes forms more double tops, double bottoms and rectangles at 15m z2 than its
   twin.
4. **Parity.** On a 700-day synthetic history (the 4h window alone is 500 days), levels_at on a 3,000-bar window
   equals the full run at 300 sampled bar closes per timeframe in the last 30 days for at least 99.5% of codes of every
   reading; PatternStream seeded at day 550 equals the full run on days 550-700 exactly.
5. **Engine format.** Every reading has its keys and flags; heat.read_state, event_levels and level_events run on it
   and give the expected levels; names hold no ' | ', '\x1f' or '='; a frame's readings share a base, parameters have
   their own.
6. **Kernel frames.** The vectorised windows equal a direct per-window Nadaraya-Watson and cross-validation on 50
   windows to 1e-9; a hand-made extrema sequence gives each LMW class; a pattern is reported once (the bar-60 rule).
7. **Splits and outcomes.** No A instance's outcome reads a 2025 minute; no row reads 2026; the parameter edges use A
   instances only.
8. **HM2 untouched.** On the synthetic fixture, run_series with and without `--patterns` writes byte-identical HM2
   files (meta.json compared without its timing and memory fields: seconds, seconds_total, peak_rss_mb), and ctx's
   readings, extra_readings and caches are as HM2 left them. A `--part i/S` job never runs the stage. Two runs of the
   stage give the same catalogue hash.

## Known limits
- **Subjective definitions.** Chart patterns are drawn by eye; any rule is one reading of them. The thresholds are fixed
  here, before any result, from the literature, round 12 and random-walk leg lengths. Near misses (one check failed)
  and the parameters let the drill see whether a rule matters; the definitions are not tuned after a result.
- **Scale choice.** Three ATR sizes on four timeframes overlap (a 5m swing of 8 ATR is about a 15m swing of 4.6). The
  same move can show as a 15m z4 head and shoulders and a 1h z2 double top. The near-copy collapse handles the lists,
  but the scale map's cells are not independent.
- **Few cases at large scales.** At 4h z8 a coin makes a few dozen five-pivot windows in six years and 2025 holds a
  handful; most such rows fall under the floor and are shown with their counts only. Rows of the same pattern on
  overlapping frames are close relatives.
- **Short horizons.** Textbook targets on 1-hour and 4-hour patterns take days. The curves stop at 240 minutes; the
  catalogue's "target before invalidation within 1,440 minutes" is the only longer view.
- **The earlier null result.** Round 12 found that real head and shoulders on dominance and price series did not beat
  patterns found in noise. That was weekly data with 63 patterns; this is intraday with many more, but the same
  outcome is the expected one, and the twins are there to show it.
- **What the twins cannot judge.** Coin-flip twins have no bid-ask bounce and no price-step rounding: retL and the move
  in price steps are the guards. A real coin's pattern frequency differs from the twin's wherever its swings are not a
  coin flip; that is reported, not removed.
- **The kernel frames** use LMW's percent tolerances, set for daily stocks: on 15-minute bars 1.5% is several ATR and
  accepts loose shapes; on 4-hour bars Savin's 3% head is about two to three ATR. They are a literal check, not tuned.
- **Parity.** Window parity is measured, not proven; the stream reader is exact on the same feed. Binance spot bars
  only; a Coinbase feed will differ at times (about 91% signal agreement in an earlier check). A 4-hour frame needs
  500 days of minutes in the window.
- **Thin 4-hour frames.** The engine's stale rule (100 bars after a forward-filled minute, 500 after a long outage)
  costs 17 to 83 days of 4-hour readings per gap. The bench and the anatomy table show how much.
- **Pattern parameters at collisions.** The frame-level parameter readings show one instance per bar; a chart unit's
  own columns come from the catalogue instead.
- **Many rows.** 885 readings, about 6 levels each, 6 horizons: the twins' max is the yardstick, not t.
- **Not in the learner.** Chart readings do not enter HM2's GBM models (HM2's models are fixed in OR-HM2.md). They can
  join a later fit if the curves show they matter.

## Unchanged
heat.py and every HM1 table, hash, league and pack; OR-HM2's design, readings, pairs, learner, lists and pack; the data
cut (no 2026 minute), the entry, the dead band, the twins (seeds 1-3), the sample floors; NEVER DOGE. A map on coin
price, not a validated rule.

## Next (not this run)
- A 1-minute frame if the 5-minute r = 2 rows lead the scale map; patterns on the other coins' bars as cross-coin
  readings (BTC's 1-hour structure as a reading for ETH).
- Chart readings in a learner fit, if Part 4's curves or pairs stand clear of the twins.
- The Kalshi test of OR-HM2's Next applies to chart rows like any other.

## What the review changed (adversarial review, 2026-11-12 ~00:15 UTC, Nov 11 7:15 PM EST; before any Part 4 code or result)
1. **Repainting closed.** "An instance whose bars include a stale bar is dropped" would have erased codes already
   written; a stale bar now ends the alive instances at that bar and resets the zigzag. The new leg after a pivot
   starts from the bars after the pivot's bar, so no trough sits at the low of the bar that made the peak (intrabar
   order unknown). "Formed" fires only before a break; an instance that stops passing ends for good; an overrun ends a
   forming instance; the invalidation level is frozen at the break; precedence (TRITOP, HS, DTOP) is decided per bar
   and never withdraws a code. A second negative control (pivots at their extreme bar) joins the no-repaint test.
2. **Lines through a moving pivot.** Triangles, wedges, rectangles and broadening patterns fitted a line through the
   provisional E5, so a "break" on that side was the pivot moving with price. That side now breaks only beyond E5's
   admissible bound; every trigger line is made of confirmed pivots.
3. **Window parity.** The duplicate guard chained (whether an instance fired depended on an older, suppressed one), so a
   window could not match the full run; it is removed from the readings and kept as a catalogue flag (`cont`). `pre`
   read up to 2,560 bars back and broke the 2,500-bar window; it is capped at 500 bars and the window is 3,000 bars
   (heat_live's own), with the lookback bound written out. The ATR threshold is an exact integer comparison on tick
   units and a fixed-order sum off a grid. The kernel frame gets a 12-bar repeat rule, because re-smoothing can end the
   same shape at bar 60 twice. Parity history 700 days.
4. **Chance.** Each break carries p_rw, the random-walk odds of target before invalidation from its own geometry, and
   `tbi` (both barriers on minute closes) is shown against it and the twins: round 12's equal-move base. Each break
   row stands beside the same frame's BOS row (`shape_lift`): does the shape add to a plain swing break? The chance
   table prints the size of the multiple-testing family and the marked-row counts per horizon and kind on the coin and
   each twin; no mark removes a row. Losers cover every event level.
5. **Definitions checked against the sources.** SWZ: bandwidth multiples 1-2.5 × CV (the SWZ frame now uses 1.0, not
   LMW's 0.3), R6/R7 measured from each shoulder's own trough (adaptation stated), R9 is "longest spacing ≤ 1.2 × the
   mean", and their result is a portfolio tilt partly from negative momentum, not a stand-alone edge. Bulkowski's HS
   confirmation rule confirmed; his 51% measure rule added as the half target. Rink: the crossing must come in the 12
   bars (kept as a column). Kuna is not daily-only. STRUCT/BOS: CHoCH only against an up or down structure. Parameter
   values are dated at the first break, with A membership by that row.
6. **Fit with HM2 and Part 3.** HM2's merge rule already counts agreement off the neutral level, so no message is
   needed. Route A's hook moves after HM2's meta.json, runs only in S = 1 or `finish` jobs, never copies HM2's code
   matrix or totals, and the byte-identity test ignores timing fields. The frame-level parameter readings can show
   another pattern's instance on a collision bar, so Part 3 takes a chart unit's own shape columns from the catalogue
   (event row to instance id); reading code hashes go to meta for Part 3's rebuild.
7. **Data and compute.** The 4-hour stale cost (17-83 days per gap under the engine's rule) is printed by the bench and
   the anatomy table; the catalogue is written frame by frame; memory estimate +2 GB.
