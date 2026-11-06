# Pre-registration META-A1 (meta plan thread). Registered 00:10 UTC Nov 6 2026 (7:10 PM EST Nov 5), before any job runs.
Source: /mnt/project-files/institutional-methods/failure-diagnoses.md, "Hypothesis META-A1". Steven's rule of Nov 5 22:48 UTC.

## Hypothesis
Neither the math fair value nor the meta-model price adds information to the Kalshi mid recalibrated for the
favourite-longshot bias (FLB). Entries are chosen by forecast error, so a larger disagreement or a higher
STRATEGY_MIN_EDGE does not raise realized edge per contract.
Null: the price beats the calibrated mid on H-HOLD and pays its costs.

## Data and splits (HO-1)
- Series: BTC, ETH, SOL, XRP Kalshi price-prediction markets; no DOGE; decision rows with books 10c wide or less.
- H-DEV Apr 18 to Jul 31 2026: the only data used for any fit or choice (mid calibration, meta model, cut shares).
- H-HOLD Aug 1 to Nov 4 2026, ending 23:59 UTC Nov 4, in 6 consecutive folds of 16 days. Read once.
- Every run prints its first and last day. A day after Nov 4 voids the run. Lockboxes L1 (Nov 6 05:00 to
  Nov 13 05:00 UTC) and L2 are never read. F-CHECK (Nov 5 02:00 to Nov 6 02:00 UTC) is simulator validation only.
- Regime: regime v1 RV terciles (registry/regime-v1/fc05ea8.../labels.csv.gz).

## Code pin
The shared harness benched-jobs.yml on claude/project-thread-g22fyz, at the single post-round-11 commit that lands the
harness additions (meta per-entry rows included). Its sha is written into this file as an addendum before Wave A is
dispatched, and is never changed after that. REPLAY_VERSION is 8 or later (8 tonight; the #299 v9 confirmation comes
later, before any freeze).

## Arms (MODEL_SKILL=false on all, DOGE out)
- base: harness defaults.
- ME06: STRATEGY_MIN_EDGE=0.06.
- ME10: STRATEGY_MIN_EDGE=0.10.
- PSKIP (Wave B only): RS_SKIP_MARKETS = ME10's trade-cut share measured in Wave A on H-DEV.

## Waves
- Wave A (dispatched after round 11 frees its runners, about 03:30 UTC Nov 6): one mode=dev run with base, ME06 and
  ME10, on H-DEV only. Output: ME10's trade-cut share. No H-HOLD number is produced.
- Wave B (scored once on H-HOLD):
  - B1, fill-free: trainMetaModel trained before Aug 1 (--holdout-from 1785542400000). Reports skill
    S = LL(mid_cal) - LL(price) for the math fair value and the meta price, by fold, tercile and asset, with a
    day-block bootstrap and DM (clustered by event). Also reports the mean signed gap (price minus mid) and the
    NO share of entries by fold, tercile and price bucket.
  - B2: one mode=full harness run with base, ME06, ME10 and PSKIP.
- Placebos: the price shuffled within hour and series (K=8), the price shifted by 24 h, and PSKIP.

## Predictions (pre-registered)
- S has an upper 95% bound below 0.002 nats, and S <= 0 in at least 4 of 6 folds.
- The slope of realized edge per contract on |price - mid_cal| is <= 0.
- ME10 minus base per contract is within 2x the paired SD, and does not beat PSKIP.
- The calibrated mid beats the raw mid, which measures the FLB on our series.

## Falsified if any one holds
- S > 0 with its lower bound > 0 in at least 4 of 6 folds AND at least 2 of 3 terciles.
- The slope > 0 with its CI excluding 0.
- ME10 beats both base and PSKIP by more than 2x the paired noise SD.
An inconclusive S is recorded as underpowered, not as support.

## Recording
- Registry family "meta-a1" on thread meta, base "benched-lab@<pinned sha>" with base_defaults.
- Wave A rows are flagged dev-choice. BHY within the family, and no blocking flags.
- An adversarial evaluator (Opus 5.5 high) reviews before anything is recorded as a verdict.
- A recorded-tier check runs in batch 4 only if the P&L sign is ambiguous.

## Follow-ups (fixed now)
- If the levers thread's NO-bias fix passes its own test, META-A1 is re-run on that base.
- If falsified: do not bench. Test META-I1 next (maker-only exits plus a thresholded stop vs the current rule and a
  random-time exit placebo, entry-locked H-HOLD replays, within the 10% rule).
- If skill shows in one tercile only: gate on that tercile, pre-registered on H-DEV.
- GitHub cost: about 21 runner-jobs over two waves of at most about 10.
