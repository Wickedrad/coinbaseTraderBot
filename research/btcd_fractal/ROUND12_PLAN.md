# Round 12: head-and-shoulders timing (pre-registered 2026-11-02 17:27 UTC / 12:27 PM EST)

Steven (17:21 UTC / 12:21 PM EST): "look at the head and shoulders on BTC.D from 2024-25 to now as well as an inverse
head and shoulders around the same time on USDT.D, both of which the right shoulder is still in play; it may help with
determining a time frame. ETH/USD I believe has one too."

Question: once a head-and-shoulders (H&S) pattern's right shoulder is in play, does it say WHEN the neckline breaks and
WHEN the measured move completes, better than the base rates the forecast already carries? The pattern's target is a
by-product; the time frame is the claim under test.

Module: `study12_hs.py` -> `out12/hs/results.json` (+ charts). Data: `research/btcd_fractal/data` (TradingView daily,
weekly closes W-SUN; ETHUSD = ETHBTC x BTCUSD). Series under the claim: BTC.D (2014-04 on; `BTCD_SPLICED` as well when
present, for 2013-18 coverage), USDT.D (2015-03 on), ETHUSD (2016-06 on). For sample size the same detector runs on
TOTAL3, ETH.D, OTHERS.D, TOTAL2, TOTAL, BTCUSD: the timing lore is not series-specific, and a law that only holds on the
three named series is a selection, not a law.

## [1] Detector (fixed before the current pattern's dates are looked at)
- Zigzag pivots on weekly closes, reversal threshold in log space (logit for dominance shares) at two sizes,
  r in {0.08, 0.15}, so small and large patterns are both seen.
- A top pattern = pivots S1 (peak), T1 (trough), H (peak), T2 (trough), S2 (peak) in sequence with H above both shoulders;
  shoulders within tolerance |S1 - S2| <= 0.5 x (H - neckline at S2); neckline = the line through T1 and T2, its rise
  over the pattern span at most 0.5 x head height; right-shoulder span (H -> S2) between 1/3 and 3 x the left (S1 -> H).
  Inverse pattern = the mirror image.
- Point in time: a pivot exists only once the reversal of size r from it has printed. "In play" at week t: S2 confirmed
  and no close beyond the neckline yet. "Break" = first weekly close beyond the neckline after S2. "Target" = neckline at
  the break +/- head height (measured move). "Completion" = first close beyond the target. "Fail" = close beyond S2
  before the break, or no break within 78 weeks of S2.
- Every pattern is recorded at the week it became in play, then what followed. No look-ahead in detection.

## [2] Timing laws (each a candidate time-frame rule)
- T1 symmetry: weeks S2 -> break ~ weeks S1 -> T1 (the left shoulder's fall).
- T2 shoulder symmetry: weeks H -> S2 ~ weeks S1 -> H (to time S2 while the right shoulder is still forming).
- T3 decline duration: weeks break -> target ~ weeks H -> T2; alternative: 0.5 x the pattern span S1 -> S2.
- Each law: predicted date against the actual date on every completed pattern (error in weeks), beside (a) the naive
  baseline (the expanding median of the same quantity across patterns known by then) and (b) the same law on placebo
  series (IAAFT surrogates and matched random walks per series, the same detector, >= 40 placebos per series). A law
  whose real-pattern errors are not smaller than its placebo errors (one-sided rank test, p < 0.05 pooled) is the
  detector's artefact, not information.
- Rates: in-play patterns that break within 13/26/52 weeks; breaks that reach the target within 26/52 weeks; against
  the base rate of an equal move over the same horizon without a pattern (same series, same era) and against placebos.

## [3] The current patterns (reported after [1]-[2] are fixed)
BTC.D 2024-26 top (S1, T1, H, T2, S2 dates and levels as the detector finds them at both r; if it finds none, say so
and show the nearest pivot structure), USDT.D inverse, ETHUSD (either kind). For each: in-play status, neckline today,
measured-move target, and the time frame each law gives (break week, completion week) with the historical error band
from [2]. The joint reading: BTC.D down with USDT.D up at the same time is a stables-gaining fall, the rare kind in
round 10 (14 of 16 falls since 2016 were alt-led): say what the two patterns together imply for the fall's kind.

## [4] Criteria (pre-registered)
A timing law is "supported" only if (i) its median absolute error beats the naive baseline by >= 2 weeks on >= 10 real
completed patterns pooled, (ii) it beats the placebo distribution (p < 0.05), (iii) the direction holds in >= 2 of 3
eras (2013-18, 2019-22, 2023-26). Otherwise "not supported": the H&S gives a target, not a time frame beyond the base
rates. Either way the current patterns' numbers are reported with the honest band. Multiple comparisons (2 thresholds x
9 series x 3 laws) are stated, and the pooled test is the one that counts.

Adversary: a leakage hunter (do pivots use future data? is S2 confirmed with the same r that found it? does "in play"
use the break to define itself?) and a skeptic (are the "patterns" the zigzag's sampling of noise? is the placebo
family fair? are the laws' baselines honest?). Runtime target < 25 min on 4 CPUs. Full run on the GitHub runner
(`btcd-fractal.yml`, round 12).
