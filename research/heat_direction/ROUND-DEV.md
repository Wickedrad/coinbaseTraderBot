# DEV rounds, 2026-11-19 (research only: no order, no bot change, VAL untouched)

Run 44610081188 (commit e2491d2f): cut test v2 passed on BTC and ETH (16 cuts each, 0 mismatches; v1's 16 "mismatches" per coin
were the order of same-row events only, calls were identical). DEV rounds: 604 trials in 666 s, 6 rounds, round 6 stalled.
Per-check detail: run 44612561909 (`inspect`, DEV only). Aggregates only; BTC and ETH, 15-minute direction, 2026-01-01 to 2026-06-30 (181 days).

| round | group | hit | calls | day-cluster lower bound | best naive rule on the same calls | gap | checks passed |
|---|---|---|---|---|---|---|---|
| 1 | G1 bars (round 0) | 52.45% | 28,679 | 51.89% | fade15 52.47% | -0.02 pt | 4 (2,5,6,7) |
| 2 | G2 admission (top 5, share B >= 54, 10k n) | 54.86% | 10,961 | 53.88% | fade1 54.88% | -0.02 pt | 6 (2,4,5,6,7,8) |
| 3 | G3 combiner | no change | | | | | 6 |
| 4 | G4 TA precedes (conf 5, inv 5) | 55.17% | 9,402 | 54.13% | fade15 55.17% | -0.00 pt | 8 (1,2,4..9) |
| 5 | G5 entry delay 2 min | 55.25% | 9,411 | 54.18% | fade15 54.80% | +0.45 pt | 8 |
| 6 | G2+G4 again (stalled) | 55.45% | 10,336 | 54.42% | fade15 55.16% | +0.28 pt | 8 |

Round 6 best spec: top_n 5, share A >= 54, share B >= 54, combiner hottest, lag 2, TA precedes (conf 5, inv 5, pool 20), lockout 15.
Round 6 checks: 1 level 55.45 pass; 2 lower bound 54.42 pass; **3 beats best naive rule: +0.28 pt, needs +2.0, fail**; 4 BTC 55.17 / ETH 55.83 pass;
5 weeks 96% pass; 6 folds 55.7 / 55.9 / 54.8 pass; 7 UP 56.2 / DOWN 55.2 pass; 8 one minute late 54.65 pass; 9 TA confirms +6.2 pt pass;
**10 TA invalidates +0.28 pt, needs +3.0 and invalidated hit <= 50%, fail.**

## What it says
1. The heat map's side is the fade of the last 15-minute move. On the same calls the best naive rule ties the candidate in every round
   (gap -0.02 to +0.45 pt against the +2.0 pt the pre-registration requires), so no setting of the frozen grid can pass check 3.
2. Timing is what tuning found, and the baseline is higher than expected: fading the last 15-minute move at ANY minute of DEV already hits
   52.2% on BTC and 52.8% on ETH (about 260,000 decided minutes each; run 44613920175). The round 0 events (52.45%) are no better than random minutes.
   The tuned admission (top 5, share >= 54) lifts the fade to 55.2 to 55.5%, about +3 pts of timing, at about 57 calls a day.
   Month by month the every-minute fade runs 50.6 to 52.4% (BTC) and 50.8 to 53.2% (ETH) in the warm-up months 2025-06 to 2025-12, and 51.7 to 52.7% (BTC)
   and 52.3 to 53.5% (ETH) in the DEV months 2026-01 to 2026-06: positive in all 26 coin-months, drifting up over time, never near a coin flip.
   Where the heat side differs from the fade side (about 5% of admitted calls) heat is right 52.8% in round 6 (528 calls), 55.1% in round 5 (423), 57.1% in round 2 (161):
   small samples, not significant after 604 trials of selection.
3. TA that precedes the call confirms it by 6 to 8 pts (passes); TA invalidation carries no information (0 pt).
4. The loop selected on DEV with 604 trials, so these hit rates are optimistic; no VAL minute was read.

## VAL step
Amendment 1 would send rounds 2, 4, 5, 6 to VAL once each. All four fail required check 3 on DEV by about 2 pts, so a pass bit is not expected.
Not run: waiting for Steven's choice (stop, test the timing-plus-fade idea under a new pre-registration, or spend the four looks).
