# DS frequency frontier: the edge holds when the rule is made to call 10 times as often (research only: no order, no bot change)

Run 44637991215 (commit a3304197, stage `dsfloor`, real coins and 3 no-signal twins, about 2 minutes a job), 2026-11-19 6:40 PM EST / 23:40 UTC. The rules for it were frozen in AMENDMENT-3.md before it ran. Search days only (2020-01-01 to 2026-10-31); nothing from 2026-11-01 was read.

## Result in four lines

1. **Raising the floor from 3 to 60 decided calls a day costs about one point of hit rate and buys 10 times the calls.** Out of sample (each rule chosen only from earlier half-years, scored on the next one), the hit rate is 56.1% at floor 3 and 55.3% at floor 60, on 163,304 decided calls at floor 60, while the best always-on rule gets 52.19%.
2. **Every check of PREREG-3.md passes at floors 10 to 60**, including E8 (the call frequency that failed at floor 3) and the three-twin gate; the twins stay at 49.7% to 50.8%. At floor 6 the twin gate fails (one twin 51.05%), so floor 6 does not qualify.
3. **E9 (the lockout test, one call per 15 minutes per coin) passes at every floor**: at floor 60 the calls that do not overlap hit 55.03% (97.5% lower bound 54.66%) at 47.7 decided calls a day.
4. **The chooser fixed in AMENDMENT-3.md picks floor 60** (largest lockout excess a day, 2.40, of the three qualifying floors 30, 40 and 60). Its FINAL needs 4 whole weeks for about 1,300 expected decided calls. Nothing here is "edge shown on days nobody read" yet: that is the FINAL.

## The frontier (real coins)

| floor | nested hit % | decided calls | 97.5% lower bound | always-on rule % | E1-E6, E8 | E7 (twins %) | E9 lockout hit % | lockout calls/day | lockout excess/day | weeks | qualifies |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 3 | 56.13 | 17,177 | 55.19 | 52.19 | YYYYYYn | yes (50.5/50.3/50.5) | 56.06 | 7.7 | 0.464 | >8 | no |
| 6 | 56.12 | 19,652 | 55.22 | 52.19 | YYYYYYn | NO (50.4/50.4/51.1) | 56.03 | 8.5 | 0.513 | >8 | no |
| 10 | 56.45 | 23,536 | 55.61 | 52.19 | YYYYYYY | yes (50.1/50.8/50.6) | 56.37 | 10.0 | 0.638 | >8 | no |
| 15 | 56.07 | 32,966 | 55.35 | 52.19 | YYYYYYY | yes (49.7/49.9/50.4) | 56.07 | 13.7 | 0.831 | >8 | no |
| 20 | 55.66 | 45,062 | 55.02 | 52.19 | YYYYYYY | yes (50.0/49.8/49.9) | 55.56 | 17.4 | 0.970 | >8 | no |
| 30 | 55.51 | 79,407 | 55.03 | 52.19 | YYYYYYY | yes (50.4/50.8/50.1) | 55.38 | 28.4 | 1.528 | 8 | **yes** |
| 40 | 55.28 | 108,265 | 54.85 | 52.19 | YYYYYYY | yes (49.9/50.5/50.4) | 55.11 | 36.7 | 1.874 | 4 | **yes** |
| 60 | 55.29 | 163,304 | 54.92 | 52.19 | YYYYYYY | yes (49.9/50.2/50.0) | 55.03 | 47.7 | 2.401 | 4 | **yes** |

E1-E6, E8 letters in order E1, E2, E3, E4, E5, E6, E8 (Y = pass). "weeks" = whole ISO weeks for about 1,000 expected decided calls at the frozen rule's lockout rate in 2026 (>8 = more than the cap). The Reality Check p is 0.0005 (the smallest the 2,000 resamples can give) and PBO is 0.0 at floors 6 to 60 (0.196 at floor 3); the always-on benchmark is 52.19% everywhere, so the paired gain over it is +3.1 to +4.3 points with 90% lower bounds of +2.8 to +3.7.

## The rule the chooser picked (floor 60)

fade the last 30 minutes' move when it is at least 0.75 sigma, taker flow (a) at least 0.10 in the direction of the move, any relative volume, and only in the first two minutes of each quarter hour (phase q01); the call is "price will go back" over the next 15 minutes. In sample on all 14 half-years: 55.78% on 157,364 decided calls, 63 a day before the lockout and 46.6 a day with it in 2026, BTC 55.94% and ETH 55.64%. Out of sample by test block (2022H1 to 2026 Jul-Oct): 53.6, 56.7, 56.9, 56.1, 55.2, 55.5, 54.9, 54.9, 55.4, 54.2. With the lockout: 53.6, 55.9, 56.8, 56.1, 54.8, 55.1, 54.8, 54.9, 55.1, 54.2; BTC 54.97% and ETH 55.09%. The two lowest blocks are the first test block (2022H1, 53.6%) and the last (2026 Jul-Oct, 54.2%, not clean).

Neighbouring floors pick different rules (floor 40: the same shape with taker flow 0.15; floor 30: k10, z 1.25, taker 0.05, relative volume 1.0; floors 10 to 20: k3 to k5 with a relative-volume filter), all fades with the quarter-hour phase filter, so the effect does not hang on one parameter set.

## What this does not show

- **It is not out of sample for the choice of floor.** The floor was picked from these numbers (best of eight, chosen by a rule fixed beforehand); the best-of-eight optimism is small next to a 5-point gap to the twins, but it exists. The floor list also stops at 60 and the lockout excess is still rising there: the grid was fixed before the result and is not extended after it.
- **The data has one source.** Every number above comes from the one Binance minute file on Drive. The FINAL fetches the exchange's own daily files fresh, so it checks the data path as well as the rule. Before that, a plumbing check compares one search day from those files with the Drive file.
- **No fees, spread, slippage or Kalshi prices.** A 55% hit rate on a 15-minute direction is a statement about direction, not about profit. Phase 2 (execution into profit) is not started and needs Steven's word.
- The test block 2026 Jul-Oct carries the earlier H2 reads (PREREG-3.md section 2). Every number here uses it as one ordinary block.
- The oddity worth a look: a 54-58% hit rate, steady across 14 half-years and both coins, at a 15-minute horizon on the two most traded coins, is larger and steadier than one expects. The twins say the search itself does not create it; they cannot say whether the source file is right. The FINAL can.

## Next (AMENDMENT-3.md sections 5 and 6)

1. Plumbing check on a search day (the exchange's daily file against the Drive file; the scorer on the last four search weeks, for plumbing only).
2. FREEZE-DS.json with the floor-60 rule, its always-on control, W = 4, the first and last FINAL day and the sha256 of PREREG-3.md, AMENDMENT-3.md, every file of `python/dirsweep` and the frontier results, committed before any FINAL day is fetched.
3. FINAL: four whole ISO weeks starting on the first Monday at least 2 days after the freeze commit; read once, after the weeks end. If the commit lands by 7:00 PM EST on Friday 2026-11-20 (00:00 UTC Saturday 2026-11-21), that is Monday 2026-11-23 to Sunday 2026-12-20, read on 2026-12-22.
4. Pass bar (unchanged): at least 800 decided calls, hit at least 53.0%, day-cluster 97.5% lower bound above 50%, BTC and ETH each at least 51.0%.
