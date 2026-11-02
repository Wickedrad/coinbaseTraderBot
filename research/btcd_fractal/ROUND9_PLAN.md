# Round 9 plan: iterate under the dynamics rule (pre-registered 2026-11-02 12:20 UTC / 7:20 AM EST, before the round-8 full run was read)

Round 8 (ROUND8_PLAN.md, out8/) built the system of algorithms the owner asked about and attacked it. After the leakage hunters
and skeptics, the smoke runs say: no look-ahead anywhere; nothing beats the five-signal logistic (fixed5, pooled AUC 0.92 on
fall5_26w); the stratified base rate, the sigma-unit HMM transfer, the Markov-switching TVTP hazard, the Weibull hazard and the
TDA/signature families each lose or tie against fixed5 once increments are paired, nulls keep dwell times and eras are scored
within themselves; the fractal thesis legs read 0 pass / 2 fail / 1 not identifiable. The owner's rule is to iterate, not cut:
a gain that fails its adversary is tested again under the condition it failed. Round 8 left three such candidates and two
unanswered checks. Round 9 tests exactly those, through the same harness (study8_common.py), with the same point-in-time rules
(filtered only, labels withheld until their horizon has passed, every fitted object fitted on the training window only) and the
same contract (results.json with oos / null / today / series / notes; at most 60 printed lines; no network; times in US Eastern
and UTC taken from the data's last bar).

## [1] candidates: three additions to fixed5, one protocol (study9_candidates.py, budget 12 min on 4 cores, under 3 min with --fast)

QUESTION. Does any of the three things round 8 flagged add forecast content to fixed5 for a 5+ point BTC.D fall within 26 weeks,
under the condition in which it seemed to work, or is each of them era structure, continuation credit or selection?

CANDIDATES (fixed before the run; no others may be added after seeing results):
- C1 gated halving clock. Round 8: days_since_halving alone scores 0.915 in 2021-22 (one event) and 0.39 / 0.70 in the other eras;
  halving sin/cos inverted the Weibull hazard in 2023-26; fixed5 loses to the clock in 2021-22 (0.82 vs 0.92). Condition: the clock
  is allowed to matter only while the readiness gate is on (BTC within 5% of its true all-time high on weekly closes AND M2 y/y > 0,
  6-week publication lag). Terms added to fixed5: gate, gate x sin(phase), gate x cos(phase) with phase = 2 pi x days_since_halving / 1460.
  Also the plain clock terms without the gate (the un-conditioned version) so the gate's effect is a paired comparison.
- C2 BTC.D vol ratio. Round 8 multiscale: of seven sigma-unit features only the vol ratio transferred from 5-21 days to 91 days
  (marginal AUC 0.85 at s = 91) and alone it scored 0.80 pooled / 0.75 within-era, above the 7-feature classifier. Term: log of the
  trailing 13-week realized vol of weekly logit increments over the trailing 52-week realized vol (both ending at t). Report its sign
  at every refit and its marginal AUC at daily scale (5, 21 days) and weekly (13 w) so the transfer claim is checked on the same rows.
- C3 USDT.D -> BTC.D Levy area. Round 8 tda_sig: one of 15 depth-2 areas, data-chosen; pooled increment -0.009 (tie) but
  mean-of-era +0.07 (+0.15 in 2021-22, +0.07 in 2023-26), family-wise shift null p 0.38. Term: the 26-week area between the
  standardised USDT.D log-level path and the BTC.D logit path, exactly as study8_tda_sig.py defines it (import or copy the function;
  do not redefine it).

DESIGN. Weekly panel from study8_common (features, targets, walk_forward with refit_weeks 13 and label_lag 26, first forecast
2019-01-06 or the first date every comparator can forecast, scored on common rows). Models: fixed5 (reference, study8_baselines.SIGNALS);
fixed5 + C1 (gated and un-gated versions); fixed5 + C2; fixed5 + C3; fixed5 + all three; and each candidate alone. Readiness-on rows
and readiness-off rows are scored separately for C1 (the conditional's own target conditions). Every number is reported pooled, by era
(2019-20, 2021-22, 2023-26), era-stratified (within-era pairs only), on fresh-start rows (onset credit, not continuation) and with
Brier against the training-window base rate by era.

SUCCESS (all four, per candidate, pre-registered): (i) paired 26-week block-bootstrap AUC difference against fixed5 on common rows
with q05 > 0 and point estimate >= +0.03 pooled; (ii) no era with a paired difference below -0.02; (iii) the fresh-start paired
difference >= 0 (a candidate that only adds continuation credit fails); (iv) the within-era dwell-time permutation null (the episode
and gap block permutation of study8_honest, applied through the whole procedure) rejects at p < 0.05 in at least two eras for the
candidate model's era-stratified AUC. A candidate that passes (i)-(iv) is a sixth signal; one that passes only under its gate is a
conditional signal and is reported with the gate; anything else is recorded as "not supported under its condition" with the numbers.

ADVERSARY. (a) For C1: 200 decoy clocks with a random anchor date (uniform over 2009-2016) and the same 1460-day period, each run
through the whole procedure (gate and un-gated); the real anchor must beat the decoys' p95 in 2021-22 AND pooled, else the 2021 timing
is one event matched by chance. (b) For C2 and C3: 200 shifted-target nulls through the whole procedure and the within-era
permutation null above; a decoy feature built as a 26-week rolling statistic of a matched random walk (same autocorrelation as the
candidate, measured and printed) to show what a persistent nuisance feature scores. (c) For every candidate: episode leave-one-out
(drop each of the 12 label episodes with its 26-week run-up) and the minimum increment with the episode that caused it.
(d) The all-three model against the sum of the parts: if the joint gain exceeds the sum of single gains, say which pairs interact.

LEAKAGE CHECKS. Truncation test at 20 random dates (features and predictions identical before the cut); the ATH anchor for the
readiness gate uses the full BTCUSD history (study8_honest.ath_drawdown); the Levy area uses increments up to t only; the vol ratio
uses closes up to t only; the partial current week is provisional and in no training label; days_since_halving uses only past halvings
plus the published next date (2028-04-15) for phase, never a date learned from the data.

TODAY. Every model's reading on the last complete Sunday with each candidate's current value, the readiness gate's state and distance
(points of BTC rally to within 5% of the ATH; M2 y/y vs 0), the fixed5 reading under +/-1 sd of each input, printed as a spread.

## [2] checks: the two questions round 8 did not answer (study9_checks.py, budget 6 min on 4 cores, under 2 min with --fast)

QUESTION A (reverse walk-forward). Are the learned relationships cycle-specific? Train fixed5, M2-only, M2 + ETH/BTC and the
readiness rule on 2019-01-06..last complete Sunday only (labels lagged 26 weeks as always) and score them on 2016-06..2018-12 (the
era holding the Nov 2016 and Dec 2017 waterfalls, never in training). Report AUC on fall5_26w and fall10_26w, Brier vs the 2019+ base
rate, and the reading on the three big-event peak weeks (2016-11-20, 2017-12-10 reversed-era; 2021-01-03 is in training). Null: 200
shifted-target draws of the 2016-18 labels (>= 26 weeks) scored by the same frozen models. SUCCESS: AUC above the null p95 for fixed5
and for M2-only; a model that ranks 2016-18 at chance is cycle-specific and its forward number is one cycle's fit.

QUESTION B (what would change the forecast; the decision threshold). No fitting beyond fixed5 and the readiness gate. (1) For each
fixed5 input, the move from today's value to its value at each of the three big-event peaks and the fixed5 reading if that one input
alone were there (the rest at today); (2) the historical lead from the readiness gate switching on to the start of the next 5+ point
fall (every gate-on spell since 2014 on weekly closes: lead in weeks, or "no fall within 52 weeks"), as a Kaplan-Meier curve and its
median; (3) the calendar falsifiers of ROUND8_PLAN.md read on today's data (BTC.D weekly close above 65.7; the 2 Nov 2027 deadline;
a 5+ fall starting outside the engine's window) with their state; (4) a decision table: for cost ratios of a missed alt season to a
false alarm of 1, 2, 5, 10 and 20, the probability threshold above which acting is worth it (threshold = 1 / (1 + ratio)), and which
of the round-8 forecast object's readings (fixed5, in-support spread ends) clear it. SUCCESS: none, this is a report; the numbers go
into the doc's "what would move the reading" paragraph.

## What round 9 does not do
No new model families. No re-specification of round-8 criteria. No change to study8_common.py or study8_baselines.py. Nothing
touches the bot. A candidate that passes becomes a sixth signal only after the owner reads it; a conditional that passes is
written with its gate, per the dynamics rule.
