# DS sweep result: nested walk-forward over 40,320 rules and the hindsight oracle, 2020 to Oct 2026 (research only: no order, no bot change)

Run 44634307853 (commit caad315e, 6:03 PM EST / 23:03 UTC; written 6:20 PM EST / 23:20 UTC). Frozen rules: PREREG-3.md (sha256 c3b9b51e4200440b532de817483b80f9379d57ee2a1f4fa9ae38dd1325bbe9cf), LITERATURE-DS.md. Data: Binance spot 1-minute bars, BTC and ETH, 2020-01-01 to 2026-10-31 (2 warm-up days before). Nothing at or after 2026-11-01 was read. Real coins and 3 no-signal twins, four jobs. Aggregates and rule parameters only. Full tables: `research/heat_direction/ds/tables-real.md`, Drive `models/heat-direction-loop/ds-twin0` to `ds-twin3`.

## Result in four lines

1. **A strong, selective edge showed up out of sample.** Walk-forward (each rule chosen only from earlier days, scored on the next half year): **56.13% hit on 17,177 decided calls**, day-cluster 97.5% lower bound **55.19%**, every one of the 10 test blocks between 54.3% and 58.2%, BTC 56.11% and ETH 56.16%. The best always-on rule chosen the same way hit 52.19% (+3.95 points, 90% lower bound +3.31).
2. **The three no-signal twins found nothing:** 50.48%, 50.33%, 50.51% through the identical procedure. The Reality Check max t is 43.2 on the real data against a 95% bootstrap level of 4.5.
3. **By the letter of PREREG-3 the verdict is "no edge shown", because E8 fails:** the frozen rule fires 4.55 decided calls a day, the bar was 10. E1 to E7 all pass (E7 judged from the three twins below). This is a frequency failure, not a hit-rate failure, and I am not rewriting the verdict.
4. **A flaw in my own pre-registration, found now, before any FINAL day was read:** FINAL needs at least 800 decided calls in four weeks, which is 28.6 calls a day. The frozen rule would give about 127. No selective rule can pass FINAL as written, so the next step is a frozen amendment (section 7), not a FINAL look.

## S1 verdict (PREREG-3.md section 4)

| input | bar | real data | pass |
|---|---|---|---|
| E1 nested pooled hit | >= 53.0% | **56.13%** (N 17,177) | yes |
| E2 day-cluster 97.5% lower bound | > 51.0% | **55.19%** | yes |
| E3 test blocks above 50%, none below 48% | >= 8 of 10 | **10 of 10**, range 54.3% to 58.2% | yes |
| E4 Reality Check (studentised max over all eligible rules, 2,000 stationary-bootstrap resamples, seed 20261123) | p < 0.05 | **p = 0.0005** (max t 43.2; bootstrap 95% level 4.53; 17,306 eligible cells) | yes |
| E5 minus best unfiltered rule, paired day bootstrap (seed 20261124) | >= +1.0 pt and 90% lower bound > 0 | **+3.95 pt**, 90% bound +3.31 | yes |
| E6 probability of backtest overfitting (3,432 splits) | <= 0.30 | **0.196** | yes |
| E7 twin gate (3 twins, nested pooled hit) | each within 49.0% to 51.0% | 50.48%, 50.33%, 50.51% | yes |
| E8 frozen rule decided calls per day | >= 10 overall and >= 5 in the last block | **4.55** overall, 5.79 in the last block | **no** |

Twins in full (same procedure, same code): nested hit 50.48% / 50.33% / 50.51%; Reality Check p 0.45 / 0.17 / 0.10 (none significant); PBO 0.45 / 0.40 / 0.11; paired difference to benchmark +0.5, +0.4, +0.5 pt with negative lower bounds; E1 to E5 all false in every twin.

## The 10 walk-forward folds (rule chosen on earlier days only)

| test block | rule chosen from earlier days | its hit on the days it was chosen from % | **hit on the test block %** | decided calls | per day | BTC / ETH % | best always-on rule on the same block % |
|---|---|---|---|---|---|---|---|
| 2022H1 | fade k3 z1.25 a0.15 r1.25 q01 | 58.0 | **55.8** | 2,697 | 14.9 | 57.1 / 54.4 | 51.4 |
| 2022H2 | fade k3 z1.5 a0.15 r1.25 q01 | 57.8 | **57.3** | 1,695 | 9.2 | 57.9 / 57.1 | 53.0 |
| 2023H1 | fade k3 z1.5 a0.2 r1 q01 | 57.8 | **57.7** | 1,521 | 8.4 | 58.8 / 56.9 | 53.2 |
| 2023H2 | fade k3 z1.5 a0.2 r1 q01 | 57.8 | **55.6** | 2,573 | 14.0 | 56.1 / 55.0 | 52.6 |
| 2024H1 | fade k3 z1.25 a0.2 r2 q01 | 58.1 | **58.2** | 1,532 | 8.4 | 57.3 / 59.3 | 51.8 |
| 2024H2 | fade k3 z1.25 a0.2 r2 q01 | 58.1 | **55.2** | 1,974 | 10.7 | 53.9 / 56.8 | 51.6 |
| 2025H1 | fade k5 z1.5 a0.15 r2 q01 | 57.9 | **55.5** | 1,914 | 10.6 | 55.2 / 56.0 | 51.8 |
| 2025H2 | fade k5 z1.25 a0.2 r2 q0 | 58.0 | **55.6** | 974 | 5.3 | 55.6 / 55.8 | 51.6 |
| 2026H1 | fade k3 z1.25 a0.2 r2 q0 | 57.9 | **56.7** | 966 | 5.3 | 58.6 / 54.7 | 52.7 |
| 2026 Jul-Oct (not clean, see limits) | fade k30 z0.75 a0.4 r0 q014 | 58.4 | **54.3** | 1,331 | 10.8 | 52.9 / 56.7 | 52.2 |
| **pooled** | | about 58 | **56.13** | 17,177 | | **56.11 / 56.16** | 52.19 |

Reading: "fade k3 z1.25 a0.2 r2 q01" = bet against the last 3 minutes' move when that move is at least 1.25 times its normal size, the taker flow (aggressive buyers or sellers) was at least 0.2 in the move's direction, volume was at least 2 times normal, and the entry minute is the 1st or 2nd of a quarter hour. Nine of the ten folds chose almost the same rule (k 3 or 5, taker flow 0.15 to 0.2, volume 1 to 2 times normal, quarter-hour start); the tenth chose a longer-lookback rule. The chosen rule looked about 58% on the days it was picked from and about 56% on the next days: honest shrinkage of about 2 points, the same size H2 showed (1.1 to 2.1).

## The rule frozen on all 14 blocks (not a test result: it was chosen with every block)

fade, k = 3 minutes, z >= 1.0, taker flow >= 0.2, relative volume >= 2.0, first minute of the quarter hour (q0). In-sample 57.80% on 11,360 decided calls, lower bound 56.81%, BTC 57.90% and ETH 57.70%, **4.55 decided calls a day** (5.79 in the last block). Hit by block (in-sample, so optimistic): 57.9, 59.3, 49.5, 58.2, 55.5, 60.6, 54.8, 60.2, 60.3, 56.8, 57.9, 58.6, 56.7, 60.4. One block (2021H1) is at 49.5%. The nested number above (56.13%) is the one to carry, not 57.8%.
Top 10 by training score on all blocks are all the same family: fade, k 3 to 5, taker flow 0.05 to 0.3, volume 2 to 3 times normal, q0 or q014, 3.0 to 6.5 calls a day.

## S2: the perfect-hindsight oracle (same readings, 5, 15, 30, 60 minutes)

- Credibility: **credible.** Survivors across the four horizons: real 139 (40 / 35 / 30 / 34 at 5 / 15 / 30 / 60 minutes), twins 27, 0 and 0. Real is above the pre-registered bar (at least 3 and more than 3 times the largest twin count, 81).
- Heat (calls per day x mean aligned basis points) is dominated by wide, always-on rules because they fire about 2,000 to 2,800 decided times a day: the league is fade rules with k 5 to 30, taker flow >= 0 to 0.1, no size or volume filter, 52 to 53% hit, +0.2 to +0.7 bp per call gross in every period A, B, C. Example, the 15-minute league survivor with the largest A heat: fade k15 with taker flow >= 0, A / B / C hit 52.97 / 52.33 / 52.70%, mean +0.524 / +0.298 / +0.268 bp per call, 1,983 decided calls a day. The largest survivor across horizons is at 30 minutes (fade k10, no filters, hit 52.06 / 51.49 / 51.68%, +0.528 / +0.241 / +0.345 bp, heat 1,508 bp a day).
- So the hindsight oracle finds a broad, thin edge (about 52 to 53% and under a basis point per call, below any round-trip cost) and the walk-forward finds a narrow, thick one (about 56% on 5 to 15 calls a day). They agree on the side (fade the last few minutes after taker-driven moves) and on the quarter-hour clock.
- Pair matrix (lookback 15, 15 minutes, fade side; cells are A / B / C = 2020 to 2024, 2025, 2026 Jan to Oct): the hit rate climbs with the size filter and the taker-flow filter. Unfiltered 52.3 / 51.6 / 52.2%; z >= 1.5 alone 54.8 / 53.7 / 55.1%; z >= 1.5 with taker flow >= 0.4 gives 55.8 / 57.1 / 57.0%. Very large moves work better in the later periods (z >= 2.5, no other filter: 54.0 / 54.2 / 56.7%; with taker flow >= 0.4: 52.2 / 58.4 / 59.2%), so the 2020 to 2024 numbers understate recent behaviour at the extremes. The clock helps: z >= 1.5 at the start of a quarter hour (q01) 55.3 / 55.1 / 55.7%. Mean aligned basis points turn negative for z >= 2 at minute q0 (-2.7 to -3.9 bp in A) while the hit rate stays above 50%: big moves reverse more often than not, but when they continue they continue far. For a contract that pays a fixed amount on direction only, the hit rate is what counts. All 236 cells are in `ds/tables-real.md`.

## Problems found and what they change

1. **E8 and the FINAL size do not fit a selective rule** (above). The pre-registered FINAL (section 8: at least 800 decided calls in four whole ISO weeks) needs 28.6 calls a day. At 4.55 a day, 800 calls would take 176 days. This is a design error of mine, found before FINAL data was fetched.
2. **Frequency drifts.** The last fold's rule fired 3.1 times a day in its training years and 10.8 a day in 2026 Jul-Oct. A rule's call rate in the past is not a promise of its call rate ahead.
3. **The oracle league ranks by heat, so it prefers frequent weak rules.** Heat was pre-registered; it is a poor guide to per-call edge.
4. **Disclosure that still holds:** 2026 Jul-Oct is not clean (the H2 per-check tables on those days were read); it counts as one ordinary block and carries no confirmation weight. Without it the nine earlier folds pool to 56.29% (15,846 calls); the last fold alone is 54.32% (1,331 calls).
5. Notes from the single-angle critic (no blocker or major): the reading requires volume > 0 for every rule, not only the taker-flow filter (a few non-gap zero-volume rows); S2 has no purge between A and B (about one hour of outcomes); both are negligible and are as pre-registered where the pre-registration speaks.

## What is and is not shown

Shown: on Binance 1-minute bars, a rule family that fades taker-driven short moves at the start of a quarter hour called the next 15 minutes right about 56% of the time, out of sample, in both coins, in every half year since 2022, and a no-signal copy of the same bars gives 50.4%.
Not shown: that this holds on days nobody has read (FINAL is untouched); that it holds at the entry price a 15-minute Kalshi contract would offer; that it clears any fee, spread or fill problem (phase 2, not started, and it needs Steven's word); that a rule with 5 to 15 calls a day is enough volume.

## 7. Next, proposed and not yet run

AMENDMENT-3.md, frozen before it is scored: (a) the **frequency frontier**: the same nested procedure repeated with the eligibility floor raised from 3 to 6, 10, 20, 30 and 50 decided calls a day (E1 to E7 re-judged at each floor, same twins, same seeds), to show how fast the hit rate falls as the rule fires more often; (b) a **FINAL sized to its rule** (whole ISO weeks until the expected decided calls reach 800, with the floor chosen in (a) so that this is at most 8 weeks), replacing the fixed four weeks; (c) the freeze file written only after (a). Cost: GitHub only, about 5 minutes a run. S3 (TA-Lib vocabulary) stays out until its own amendment.
