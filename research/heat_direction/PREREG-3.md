# DS: sweeping the literature's findings across all history, with a perfect-hindsight oracle (pre-registration)

Written 2026-11-19 5:55 PM EST / 22:55 UTC, before any rule of this family is scored. Research only: no order, no bot change, no protected heat curve.
Steven, 5:30 PM EST / 22:30 UTC: "Use Scite to research the best way to determine market direction and then from your findings there conduct the loops as sweeps across the historical data to both find and test edge, fine-tune that edge to the max that we can reasonably achieve."
Steven, 5:35 PM EST / 22:35 UTC: "Use a perfect Oracle to sweep the findings in the historical data as well."
Literature: LITERATURE-DS.md (Scite, 14 papers verified). Earlier rules that still hold: PREREG.md (definition of a call, the 15-minute move, the flat band, BTC and ETH only), AMENDMENT-1.md (twin gate), PREREG-2.md (H2, finished: its unseen days are spent for its two candidates). This file replaces the 9-of-10 rubric for this family, as Steven's new words ask for an edge and its best reasonable size, not a score of 9.

## 1. Question and what counts

Q1. Does a transparent rule, chosen only from days before the days it is scored on, call the next 15 minutes of BTC and ETH better than chance, in every market regime since 2020, after paying for having searched 40,320 rules?
Q2. What is the largest edge that survives that, and how large will it be on days nobody has read?
The size we carry forward is the nested out-of-sample hit rate (section 4), never the in-sample best.

## 2. Data, windows, and the days that are not clean

- BTC and ETH, Binance spot 1-minute bars from Drive (`raw/perp-ta-history/binance-1m/<coin>/1m.csv`: `ts, o, h, l, c, v, tb`), made into a complete minute grid by `oracle.heat_live.grid` (a missing minute is forward-filled with volume 0 and flagged as a gap). No other data. Never DOGE.
- SEARCH days: 2020-01-01 up to but not including 2026-11-01 (or the first day on file, if later). A reader loads nothing at or after 2026-11-01; the code asserts it. 2026-11-01 onward is read only by the FINAL stage (section 8).
- Blocks (14): calendar halves 2020H1 to 2026H1 (13) and 2026 Jul 1 to Oct 31.
- Oracle periods for section 5: A = 2020-01-01 to 2024-12-31 (build), B = 2025 (check), C = 2026-01-01 to 2026-10-31 (final check).
- Disclosure, so nobody reads more into it than is there: the two H2 candidates' per-check tables on 2026-07-01 to 2026-10-31 and the every-minute naive rates there (fade1 50.53%, fade5 51.32%, fade15 51.87%, fade60 52.44%) have been read. This family is a different one (no heat-map events), but those four months are not clean. They count as one ordinary block and carry no confirmation weight.
- A call, its entry row, the 15-minute move, the flat band and "decided" are as PREREG.md: the call at entry minute e uses only bars closed at or before minute e-1 and the open of minute e; move_h = (open[e+h] - open[e]) / step; step = 0.01 for BTC and ETH (the table's price step, `research/oracle_heat/latest/live_meta.json`); right = move agrees with the call and is at least 1.5 steps, wrong = it disagrees by at least 1.5 steps, anything smaller is flat and not decided. Primary horizon h = 15. Oracle strips (section 5) also use h = 5, 30, 60.
- A row e is scored only if no gap minute lies in [e-60, e+60] and the 1,440-minute window below has at most 72 gap minutes.

## 3. The rule grid (40,320 rules, fixed)

A rule is (side, k, z, a, r, phase). Let M = open[e] - open[e-k]; call the sign of M "the move". A row with M = 0 makes no call.

| part | definition | values |
|---|---|---|
| side | fade = against the move, follow = with it | fade, follow |
| k | lookback in minutes | 1, 2, 3, 5, 10, 15, 30, 60 |
| z | size filter: abs(M) / sigma_k >= z, where sigma_k is the root mean square of the k-minute moves M(j) for j in [e-1440, e-1] (strictly past) | off, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0 |
| a | taker-flow filter: sign(M) x (2 x sum tb - sum v) / sum v over the k closed bars e-k..e-1 must be >= a (taker flow in the direction of the move; needs sum v > 0) | off, 0, 0.05, 0.10, 0.15, 0.20, 0.30, 0.40 |
| r | relative volume: (sum v over e-k..e-1) / (k x mean v over [e-1440, e-1]) >= r | off, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0 |
| phase | minute of the hour of e, mod 15 | all {0..14}; q0 {0}; q01 {0,1}; q014 {14,0,1}; mid {3..11} |

8 x 9 x 8 x 7 x 5 x 2 = 40,320. Each rule fires at every row it admits (no lockout inside the sweep); outcomes overlap, so every standard error is clustered by UTC day, both coins pooled. A rule is eligible in a window only if it averages at least 3 decided calls per day there.
For the same admitted rows, fade and follow right counts add up to the decided count, so both sides are computed from one table.
Why these parts: side and k from items 1 and 3 of LITERATURE-DS.md, z from item 4, a from item 1 (reversal after taker-driven moves), r from item 3, phase from item 2. Order-book depth, BTC-to-ETH lead-lag and order imbalance beyond one bar are not in the grid (items 5, 7, 2).

## 4. Stage S1: the nested walk-forward sweep (horizon 15)

For each of the 10 test blocks t = 2022H1, 2022H2, ..., 2026 Jul-Oct (block index 4 to 13):
1. Training days = all days of the blocks before t, minus the last day of block t-1 (purge).
2. Every eligible rule is scored on the training days: p = right / decided, pooled; cluster-robust standard error from the day sums; score = p - 1.96 x SE for fade, (1 - p) - 1.96 x SE for follow.
3. The rule with the largest score is selected. Ties: fewer active filters (z, a, r not off, phase not all), then rule id order.
4. The selected rule is scored on block t's days. Nothing from block t was read for the choice.
5. Benchmark: the unfiltered rule (z, a, r off, phase all) with the best training score among the 16 (side, k) is scored on block t the same way.

Nested out-of-sample result = the selected rules' calls on their test blocks, pooled (10 blocks). The final rule is chosen the same way on all 14 blocks (no test block left) and frozen with its in-sample numbers beside the nested ones.

Verdict inputs, all fixed now:
- E1 nested pooled hit rate >= 53.0%.
- E2 its day-cluster 97.5% lower bound > 51.0%.
- E3 at least 8 of the 10 test blocks above 50% and none below 48.0%.
- E4 Reality Check, studentised maximum over all eligible rules of the full-sample excess over 50% (stationary bootstrap of days, mean block 5 days, 2,000 resamples, seed 20261123, recentred): p < 0.05.
- E5 nested pooled hit minus the benchmark's nested pooled hit >= +1.0 point, with a paired day-bootstrap (2,000 resamples, seed 20261124) 90% lower bound > 0.
- E6 probability of backtest overfitting (combinatorial symmetric cross-validation over the 14 blocks, all 3,432 splits into 7 and 7, rule performance = pooled hit over eligible blocks): PBO <= 0.30.
- E7 twin gate: the identical nested procedure on 3 no-signal twins (`oracle.heat.make_twin`, seeds 1 to 3, both coins): every twin's nested pooled hit within 49.0% to 51.0%.
- E8 the frozen final rule averages >= 10 decided calls per day (both coins, over SEARCH) and >= 5 per day in the last block.
EDGE FOUND = E1 to E8 all pass. If any fails, the report says which, and S1 closes as "no edge shown".
Also reported, not judged: nested hit by block and by coin; selected rules per fold; the hit of the frozen rule in each block; the top 10 rules by training score on all 14 blocks.

## 5. Stage S2: the perfect-hindsight oracle strips, league and matrix for the same readings

The oracle of Steven's spec (Nov 10) for these readings: for every minute of history, record in hindsight what price did next at 5, 15, 30 and 60 minutes, per reading cell, and keep every instance. This is the same grid as section 3, with four horizons. Per cell and horizon: called rows, decided rows, right count of the fade side, and the sum of the fade side's aligned move in basis points of price (aligned = move x -sign(M) / open x 10,000). It is not the TA-Lib engine of python/oracle/heat.py; it applies the same definitions (hindsight outcome per minute, a strip per reading, a pair matrix, heat = how often times how big, proof on later years) to the readings in section 3.
- Heat of a cell = calls per day x mean aligned bps per call (follow = the negative). Eligible: at least 1 decided call per day in A. League = top 25 cells by heat in A for each horizon, with their B and C numbers.
- Survivor = in the top 50 by heat in A for its horizon, and in B mean aligned bps > 0 with day-cluster 90% lower bound > 0, and in C mean aligned bps > 0.
- Matrix: for k = 15, h = 15, phase all: the fade hit rate and mean aligned bps for each pair of z x a, z x r, a x r, and z x phase, in A, B, C.
- The same procedure runs on the 3 twins. The league is credible only if the real data has at least 3 survivors and more than 3 times the largest twin count. If not, S2 closes as "league not credible" and its cells are not carried forward.

## 6. Not in this pre-registration

S3, the TA-Lib vocabulary (indicators with parameters, candlestick patterns, pairs and triples with the fade state) is run only after a frozen amendment, AMENDMENT-3.md, written before it is scored. The OR-HM2 oracle already swept TA-Lib singles, pairs and triples over this history and found one signal, to fade a price stretch; S3 asks whether anything refines the fade rule found here. Nothing is added to the grid of section 3 after any score is seen.

## 7. Compute and outputs

GitHub runner, no model tokens. Real and the 3 twins run as four jobs; one `HEATLOOP ds <json>` line per result, aggregates and rule parameters only. Per-block tables, the league and the matrix go to Drive `models/heat-direction-loop/ds` and to research/heat_direction/ROUND-DS.md. The causality (cut) test: truncate the file at 12 random rows, rebuild every feature for rows before the cut, and require equality with the full build.

## 8. Freeze and FINAL (the days nobody has read)

- Candidates: the S1 frozen rule, and at most one S2 survivor (the largest A heat that survived; the pre-run choice is by that rule, not by looking at C beyond the survivor test). Both are written to FREEZE-DS.json with the sha256 of this file, the code and the grid before FINAL data is fetched.
- FINAL days: four whole ISO weeks (Monday to Sunday UTC), starting on the first Monday at least 2 days after the freeze commit, fetched from Binance public daily files by a top-up job after those weeks end, read once.
- Scored as PREREG.md calls with a 15-minute lockout per coin. Pass for a candidate: at least 800 decided calls, hit >= 53.0%, day-cluster 97.5% lower bound > 50%, BTC and ETH each >= 51.0%. One FINAL look per candidate, at most 2.
- A pass is "direction edge shown on days nobody read". It does not start phase 2 (execution into profit); that needs Steven's word.

## 9. Known limits

Overlapping outcomes (clustered by day); two coins that move together (pooled by day, so one cluster); a fixed step of 0.01 makes the flat band negligible at every price level, so the flat share is about 0.4%; 2026 Jul-Oct is not clean (section 2); a 1-minute bar hides the order of trades inside it; the coin is not the Kalshi contract, and fees are ignored here.
