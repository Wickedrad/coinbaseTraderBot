# Round 10 plan: continue iterating (pre-registered 2026-11-02 15:05 UTC / 10:05 AM EST, before any round-10 number was computed)

Owner, 14:52 UTC / 9:52 AM EST: "Continue iterations." Rounds 8-9 (ROUND8_PLAN.md, ROUND9_PLAN.md, out8/, out9/) left the five-signal
logistic (fixed5: usdtd_vsma30w, ethbtc_fromhi52w, btc_dd_ath, btcusd_ret13w, m2_yoy) as the only thing with defensible out-of-sample
skill for a 5+ point BTC.D fall within 26 weeks, every regime machine and every conditional candidate at a tie or a loss, and three
open questions that could change what the forecast means or reads: (1) which kind of fall is being forecast, an alt season or a BTC
crash; (2) whether a better liquidity input exists than US M2 alone; (3) the one feature that actually transferred in round 8 (the
26-week over 104-week BTC.D vol ratio, registered wrongly in round 9 as 13/52) and a clock decoy with power. Round 10 tests exactly
these, through the same harness (study8_common.py) and the round-9 paired protocol (study9_candidates.py), with the same rules:
point in time (filtered only, labels withheld until their horizon has passed, every fitted object fitted on the training window
only), pre-registered criteria evaluated as written, an adversary for every number, aggregates only, times in US Eastern and UTC
from the data's last bar, no network inside a module (fetch.py runs on the GitHub runner before every study). Nothing touches the bot.

## New data (fetch.py, GitHub runner only; a series that does not answer is simply absent and the module says so)
CNM2, EUM2, JPM2, GBM2 (other M2 stocks, monthly), USDCNY, EURUSD, USDJPY, GBPUSD (to put them in USD), FEDBS (Fed balance sheet),
RRP (overnight reverse repo), TGA (Treasury general account), USDC.D and STABLES (stablecoin float). The existing M2 is US M2 with a
6-week publication lag (study8_common.M2_LAG_DAYS); every new monthly series gets the same lag, weekly Fed series a 7-day lag, daily
market series no lag.

## [1] altled: which kind of fall is being forecast (study10_altled.py, budget 8 min on 4 cores, under 3 min with --fast)

QUESTION. Round 8 asked whether the waterfalls are one regime: BTC.D falls when alts rise (2017, 2021: an alt season) and when BTC
falls faster than alts (mid 2022: a crash). The bot cares about the first. Does the five-signal skill come from alt seasons, from
crashes, or both, and what does today read for an alt season specifically?

DESIGN. Weekly panel. For every bar t with fall5_26w = 1 find the first later bar c within 26 weeks where BTC.D <= BTC.D(t) - 5
(the crossing). Classify the window [t, c]: ALT-LED if TOTAL3 in USD at c is at or above its level at t (alts held or gained while
BTC.D fell), CRASH-LED otherwise. Second discriminator reported beside it: ETH/BTC at c above its level at t (ETH-led). Targets:
alt5_26w (fall5_26w and alt-led), crash5_26w (fall5_26w and crash-led); both withheld 26 weeks like the parent label; the partial
current week enters no label. Print positive weeks and episodes per target per era (2019-20, 2021-22, 2023-26) and the 2016-18
episodes for context. Models through study8_common.walk_forward (refit 13 weeks, label lag 26): fixed5 fitted on alt5_26w; fixed5
fitted on crash5_26w; fixed5 fitted on fall5_26w (the round-8 model, unchanged) scored against alt5_26w and against crash5_26w on
common rows; M2 alone and the readiness rule the same way. Report AUC pooled, by era, era-stratified, fresh-start; Brier vs the
target's training base; the paired difference (generic model's AUC on alt-led minus on crash-led, 26-week block and episode bands);
readiness precision on each kind; today's reading of each fitted model.

SUCCESS (pre-registered). (a) Identifiability gate: alt5_26w has at least 4 positive episodes out of sample 2019-26, else the trial
reports "not identifiable" and stops at description. (b) fixed5 fitted on alt5_26w clears its shifted-target null p95 pooled and the
within-era dwell-time permutation null at p < 0.05 in at least two eras. (c) The forecast content is called alt-specific only if the
generic model's AUC on alt-led exceeds its AUC on crash-led by at least 0.10 with both the block and the episode band above 0 AND the
random-reassignment null below is beaten; crash-specific by the mirror rule; otherwise "both kinds".

ADVERSARY. 200 shifted-target draws per target through the whole procedure; within-era dwell-time permutations (300 per era, the last
era enumerated); episode leave-one-out with 26-week run-ups; the sub-era decoy of study9_checks; and the reassignment null: 200
random relabellings of the fall episodes into alt-led and crash-led with the real counts, the generic model's alt-minus-crash AUC
difference recomputed each time, the real difference must beat the p95.

LEAKAGE. The window classification reads TOTAL3 and ETH/BTC only inside [t, c], which lies inside the 26-week label horizon the label
already waits for; truncation test at 20 random Sundays on features, labels and predictions; the provisional bar in no label.

TODAY. Readings of every fitted model on the last complete Sunday; the kind of the last three falls (Jun 2025, Jun 2022, Jan 2021)
printed with their TOTAL3 and ETH/BTC changes.

## [2] liquidity: is US M2 the right liquidity input (study10_liquidity.py, budget 10 min, under 3 min with --fast)

QUESTION. M2 y/y carries most of the five-signal skill and moves once per cycle. Is it standing in for broader liquidity, and does a
broader or faster measure read differently today?

CANDIDATES (fixed; each used in two ways, SWAP = in place of m2_yoy in fixed5, ADD = beside it; and ALONE):
- L1 global M2 y/y: log change over 52 weeks of US M2 + EU M2 x EURUSD + CN M2 / USDCNY + JP M2 / USDJPY (+ GB M2 x GBPUSD when
  present), each component lagged 6 weeks; requires at least 3 non-US components fetched, else "not available".
- L2 Fed balance sheet y/y (FEDBS, 7-day lag) and, when RRP and TGA are present, net liquidity = FEDBS - RRP - TGA, its 52-week and
  13-week log changes.
- L3 stablecoin float: (USDT.D + USDC.D) / 100 x TOTAL in USD (or STABLES when fetched), 13-week and 26-week log changes, no lag.
- L4 US M2 y/y lagged a further 13 weeks and a further 26 weeks (if older liquidity information scores as well, the publication lag
  is not binding; if better, the cycle reads slower than we use it).

DESIGN. Round-9 protocol from study9_candidates.py on common rows (every candidate model and fixed5 forecast on the same rows; the
first forecast date printed; a candidate whose history starts late shortens the rows and says so). Paired 26-week block and episode
bootstraps against fixed5, pooled, by era, era-stratified, fresh-start; Brier vs training base; within-era dwell-time permutation;
200 shifted-target draws through the procedure; sign of each candidate at every refit; Spearman of each candidate with m2_yoy on the
common rows (|rho| > 0.8 = the same information re-labelled, said in the summary).

SUCCESS (pre-registered, per candidate). ADD: the round-9 four criteria ((i) paired gain >= +0.03 with q05 > 0, (ii) no era below
-0.02, (iii) fresh-start gain >= 0, (iv) within-era permutation p < 0.05 in >= 2 eras on the increment's own null). SWAP: "better"
only if paired >= +0.03 with q05 > 0 and no era below -0.02; "equivalent" if the band contains 0 and |diff| < 0.03; else "worse".
A candidate that is better in SWAP form replaces M2 in the forecast object only after the owner reads it.

ADVERSARY. As round 9: shifted-target nulls through the whole procedure, decoy persistent features from matched random walks with
each candidate's autocorrelation (20 draws), episode leave-one-out with run-ups, within-era permutations; plus a placebo liquidity
series: US M2 y/y with its calendar shifted by 52 weeks (one cycle), which must NOT score as well as the real one.

LEAKAGE. Every monthly series carries the publication lag before any feature; FX conversions use closes up to t; truncation test on
features and predictions; the provisional bar in no label; a series absent on disk is reported, never imputed from another.

TODAY. Each candidate's current value and the readings of every SWAP / ADD model on the last complete Sunday, beside fixed5 (4.0%).

## [3] sixth: the vol ratio that transferred, and a clock decoy with power (study10_sixth.py, budget 6 min, under 2 min with --fast)

C2b: log of the trailing 26-week over the trailing 104-week realized vol of weekly BTC.D logit increments (the feature that
transferred in round 8's multiscale module at s = 91: 0.68 pooled / 0.82 in 2023-26 marginal on the round-9 rows), as a sixth signal
under the round-9 four criteria, and under a vol-compression gate (C2b x [C2b below its trailing 104-week 20th percentile], the
dynamics-rule conditional: "a compressed BTC.D precedes the fall"). Sign at every refit; fresh-start increment; daily-scale marginal
at 5, 21 and 91 days on the same rows.
Clock decoy with power: 200 clocks with a random PERIOD drawn uniformly from 600 to 2200 days, phase anchored at the first halving
(2012-11-28), sine and cosine terms, gated by readiness and un-gated, through the whole procedure; the real 1460-day gated clock's
increment over fixed5 must beat the random-period p95 pooled and in 2021-22. This replaces round 9's random-anchor test, which was
not identifiable (a sine-cosine pair is invariant to the anchor).
SUCCESS: round-9's four criteria for C2b and for the gated C2b; for the clock: beats the random-period p95 in both places. ADVERSARY:
as round 9 (shifted-target nulls through the procedure, matched-random-walk decoy features, episode leave-one-out, within-era
permutations). TODAY: fixed5 + C2b reading, the gate state, the clock's phase.

## [4] refresh: the forecast object as a living reading (no module; .github/workflows/btcd-fractal.yml round "refresh")
Every Monday 01:20 UTC (Sunday 8:20 PM EST) the workflow fetches the latest history and re-runs baselines, honest, forecast and
study9_checks with 50 nulls, commits out8/out9 and appends one line to research/btcd_fractal/forecast_log.csv (log_reading.py: date,
BTC.D, BTC.D ex-stablecoins, inputs, fixed5 / M2-only / M2+ETH/BTC readings, honest's in-support spread, the stack, readiness gate
and distance, falsifier states). No criteria; the log is read in the thread when the owner asks.

## What round 10 does not do
No new model families; no change to study8_*.py or study9_*.py; no re-specification of earlier criteria; nothing touches the bot.
A candidate that passes is reported with its numbers and waits for the owner.
