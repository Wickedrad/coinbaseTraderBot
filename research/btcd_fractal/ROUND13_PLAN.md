# Round 13: the refinement stage (pre-registered 2026-11-02 18:58 UTC / 1:58 PM EST)

Steven's standing rule (17:51 UTC / 12:51 PM EST): when iteration plateaus after exhaustive attempts, look at where the
model still fails and add slight nuance dynamics fitted to those conditions, one final pass, before the work counts as done.

The plateau: rounds 8-10 found nothing that beats the five-signal logistic (fixed5: USDT.D vs its 30-week mean, ETH/BTC
vs its 52-week high, BTC drawdown from its true ATH, BTC 13-week return, US M2 y/y; P(5+ point BTC.D fall within 26
weeks), AUC 0.92 out of sample); the fractal (rounds 1-7, 11) and the head-and-shoulders timing laws (round 12) fail
their adversaries.

## Where fixed5 fails (out of sample 2019-2026; inventory from out8/honest, 186 sampled weeks)
- A. Post-season overconfidence. Weeks with BTC.D at least 15 points below its trailing 104-week high carry 49.5% of
  the Brier loss on 29% of the weeks: mean p 0.43 against a realized rate of 0.19 (May 2021 - Jun 2022: p 0.6-0.9 for a
  year while BTC.D sat at 40-47 with two small crash-led falls). The condition mixes mid-season weeks (2017 and early
  2021, where the falls continued: rate 1.00 in 2015-17) with post-season weeks (2018: 0.21; 2021-22: 0.23).
- B. Pre-season alarms. p above 0.5 with no fall while BTC.D sat within 3 points of its 52-week high: 7.5% of the loss
  (Dec 2019, Feb 2020, Feb-Mar 2025).
- C. Under-called onsets. Fall weeks with p below 0.35: 5.6% of the loss (Aug-Sep 2019, p 0.29-0.33).
- D. Crash-led falls: no information (round 10; 6 training positives).
- Under Steven's loss (missed season catastrophic; 50:1, act above 2%): no fall week was missed (lowest p on a fall week
  0.29); the model stood down in 11 of 186 sampled weeks (Apr 2019, Nov 2022 - Mar 2023, Oct 2023), none followed by a
  fall. The go/no-go is settled; this pass targets sizing (calibration: Brier, log loss) and onset timing.

## Candidates (slight, condition-gated adjustments to fixed5; fitted point in time with the round-8 harness:
## expanding window, refit every 13 weeks, label lag 26 weeks, study8_common.walk_forward)
- R1 season state (failure A). Inside the post-season condition (BTC.D at least 15 points below its trailing 104-week
  high, point in time) the term is BTC.D's rise from its trailing 13-week low, in points; zero outside. One extra
  coefficient. Expected sign negative (a base built after a big fall = the season is over).
- R1b (alternative form, reported beside R1, not adopted on its own): inside the same condition, log(1 + weeks since
  the trailing 104-week high); zero outside.
- R2 recency weighting (era drift behind A and B). The same five inputs, logistic fit with sample weights
  0.5 ** (age_weeks / 156).
- R3 calibration map (overconfidence behind A and B; ranking unchanged by construction). A two-parameter logistic
  recalibration of fixed5's logit, fitted on fixed5's own earlier out-of-sample predictions whose labels are known at
  the forecast date (26-week label lag), refit every 13 weeks, active from the first date with at least 52 such
  predictions (fixed5 unchanged before that).
- R4 overextension at highs (failure C and the timing of B). Inside the fresh-start condition (BTC.D within 3 points of
  its 13-week high, study8_common.fresh_mask) the term is BTC.D's 8-week change, in points; zero outside. Expected sign
  positive (an overextended dominance at a fresh high reverts).
- R+ the combination of the candidates that pass on their own (evaluated once, only if two or more pass).

## Criteria (pre-registered; on the common out-of-sample rows against fixed5, paired; 26-week block bootstrap and
## episode bootstrap, 1000 draws each)
- (i) pooled Brier improvement >= 0.005 with block-bootstrap q05 > 0, and log-loss improvement >= 0.01;
- (ii) no era (2019-20, 2021-22, 2023-26) worse by more than 0.005 Brier;
- (iii) under its condition (the dynamics rule): inside the candidate's target weeks the Brier improvement is >= 0.01
  with q05 > 0, and outside them the change is no worse than -0.003 (R1, R1b: condition A weeks; R4: fresh-start weeks;
  R2, R3: the union of the A and B weeks);
- (iv) adversary: the real improvement beats the 95th percentile of a matched placebo (R1, R1b, R4: the same term with
  the condition replaced by random blocks of equal total length, 200 draws; R2: weights built from a randomly permuted
  age, 200 draws; R3: the calibration map fitted on time-shuffled past predictions, 200 draws) AND the shift null
  (labels shifted by at least 26 weeks) at p < 0.05;
- (v) Steven's constraint: no out-of-sample fall week drops below 2% (the 50:1 threshold), and pooled AUC does not fall
  by more than 0.01.
Verdict per candidate: "adopted" (all five pass: it joins the forecast reading), "condition note" ((iii) and (v) pass
but (i) or (iv) fails: reported as a conditional adjustment, kept, not adopted), "not supported" (otherwise, with the
failing criterion and why). Nothing is benched; a failing nuance is reported with the reason it fails.
Multiple comparisons: 5 candidates (+1 combination) x 5 criteria; (iv) carries the family's protection, and the
verdicts are read jointly.

## Reported regardless
Today's reading under each candidate and the combination; the failure inventory re-scored (A, B, C weeks) for every
candidate; the decision record at 50:1 (misses, stand-down weeks) per candidate; the probability path through May 2021
- Jun 2022 and Dec 2019 - Feb 2020 per candidate (chart).

Module: study13_refine.py -> out13/refine/results.json (+ charts). Workflow btcd-fractal.yml round 13 (runner).
Adversary in the build: a leakage hunter (conditions and terms point in time; R3's calibration set only labels known at
the forecast date; the placebo blocks must not see outcomes) and a skeptic (one 2021-22 post-season episode out of
sample: is R1 identified? the episode bootstrap must drop it; is (iii)'s outside band honest?).
