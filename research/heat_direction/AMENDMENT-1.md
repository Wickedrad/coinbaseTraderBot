# Amendment 1 to the heat direction loop pre-registration: data, grid, selection, hashes

Written 2026-11-19 14:54 EST / 19:54 UTC, before round 0 and before any candidate is scored. It fills in what PREREG.md (sha256 `628c2b7d42b4c0fa414c762e977773613897c18e5711a8ad2bbee7c3796406d3`, commit 2a1a1745) left to this amendment. It changes no threshold and no check. Where the two differ on the build window, this amendment wins (section 7).

## 1. Data coverage (measured, stage `coverage`, run 44602505248)

Binance spot 1-minute bars on Drive (raw/perp-ta-history/<coin>/binance-1m): BTC and ETH run from 2019-09-01 00:00 to 2026-11-04 23:59 UTC with no missing minute in any month from 2025-07 on. The `coverage` stage reads the `ts` column only.

- DEV: 2026-01-01 to 2026-06-30 (181 days). Three two-month folds: Jan-Feb, Mar-Apr, May-Jun.
- VAL: 2026-07-01 to 2026-10-31 (123 days, four full calendar months), VAL_END = 2026-11-01 exclusive.
- Not used by anyone: 2026-11-01 to 2026-11-04 (on file, partial month) and every day after the file ends. The file stops at Nov 4, so FINAL data is fetched after the freeze (public Binance daily files, one top-up job) and read once, on the FINAL evaluation date.
- Warm-up history only (scores nothing): 2025-06-01 to the scope's start. No scope ever loads a minute at or after its own end (guards.history_limit).
- Never DOGE. SOL and XRP are computed for the report and never scored.

## 2. The level universe

The rows of research/oracle_heat/latest/league_direction.csv.gz (sha256 `1931ecbca4a7da1e0e1f5ba38b677d8fcbe6d9381f9e92407d5046123a3d62b7`, the OR-HM1 league run 43030435253 / 43051083126, build 2020-2024, check 2025, no 2026 minute in it). It holds each row's cross-year numbers (share_A, share_B, n_A, n_B, odds, heat). Filter: coin BTC or ETH, h = 15, reading bars 1m, 5m, 15m or 60m. Rows that are the same event under two names (identical sample and numbers, e.g. RSI14 and CMO14) are one row with aliases, by the rule of oracle.heat_pack. `rank_coin` = rank by oheat_B inside the coin, ties by key. Zone edges and the price step come from each coin's meta.json of the league coin run (Drive models/oracle-heat/runs/43030435253/<coin>/meta.json, checked against the table's sha256 in live_meta.json, `efd5e4490ecfa348f7a8c3e9f941c29af899f67e230bc4484486c7595747cd24`). The file is the 5,000 hottest rows by 2025 heat, so every 2025 number in it is flattered; the loop admits on the cross-year columns and the held-out days decide.

## 3. Round 0 (calibration, DEV only, never sent to VAL)

The live lane's current settings without any Kalshi condition: coins BTC and ETH, horizon 15, all four reading bars, `top_n` 10 by rank_coin, combiner hottest (the best-ranked firing row), lockout 15, lag 0, no TA layer. Round 0 also prints the call count per coin per day, the ten naive rules, the causality cut test and the twin gate. It sets nothing.

## 4. The frozen grid (the only values the optimizer may try)

| Group | Parameter | Values | Count |
|---|---|---|---|
| G1 reading bars | tfs | (1m), (5m), (1m,5m), (1m,5m,15m,60m) | 4 |
| G2 admission | top_n x min_share_A x min_share_B x min_n_B | {5,10,20,40,80} x {0,52,53,54} x {0,52,53,54} x {0,5000,10000} | 240 |
| G3 combiner | hottest, or vote with k in {2,3,5} and margin in {1,2} | | 7 |
| G4 TA layer | confirm in {none, precedes k, follows j} with k, j in {5,15,30}; invalidate in {none, k in {5,15,30}}; TA pool (top rows by rank across all four bars, any family) in {20,40} when a TA mode is on | | 55 |
| G5 entry delay | lag in {0,1,2} minutes | | 3 |

Fixed: coins BTC and ETH, horizon 15, lockout 15, tables and edges as in section 2. Procedure (coordinate descent, nothing else): round r sweeps group r with every other group at its best so far; rounds 1 to 5 take G1 to G5; round 6 sweeps G2 then G4 once more. Trial budget: 4 + 240 + 7 + 55 + 3 + 240 + 55 = 604 DEV evaluations plus round 0. Every trial is logged and printed beside any pass.

TA semantics (PREREG section 3 made exact). A confirmer or invalidator is a pool row of a different indicator family of the same coin (family = the indicator name from oracle.heat_pack.indicator with its trailing parameters stripped, so RSI7 and RSI14 are one family; decided 19:59 UTC before round 0, implemented as heatloop.calls.family). Its event at entry row r is known at the end of minute r-1. Precedes / invalidates look at pool events with entry row in [e-k, e] for a call at entry row e: a confirmer with the call's side labels the call confirmed (it is still made); an opposing pool row drops it, and the dropped call is scored as if made (check 10). Follows: the base call at e0 lapses; the call is made at the first pool event with the call's side at an entry row in (e0, e0+j], its side the base side, entry that row (plus lag), lockout from there; the made calls are the confirmed set and the lapsed base calls, scored as if made at e0 with no lockout of their own, are the unconfirmed set (check 9).

## 5. Selection and what the optimizer sees

- Each round scores every trial on DEV with the same ten checks (blocks = the three folds, weeks = the 25 full ISO weeks, floors unchanged). A trial is eligible only with at least 800 decided calls and 300 per coin.
- Best trial = most checks passed on DEV, then the larger check-2 lower bound, then the fewer non-default fields, then the lexicographically smaller spec hash. Nothing else is looked at, and no VAL number enters it.
- The best trial of each round, if it improves on the round's start, goes to VAL once. The loop sees one bit (pass or not). Six rounds mean at most six looks, the budget PREREG section 4 states.
- Random-side twin draws: 200, seed 20261120. No-signal twins: OR-HM1 twin ids 1, 2, 3 per coin (heat.make_twin seeds).
- The cut test (PREREG section 2) is implemented as: truncate the raw file after at least 12 cut minutes (the last minute of the first and last day of every block plus random minutes), rebuild every reading from the truncated file with the same code and compare every call with entry before the cut. This covers well over 500 random calls and every boundary-day call; a single mismatch voids the run.

## 6. The hash list at the freeze

At the freeze the stage writes `FREEZE.json` with the sha256 of: the candidate spec; league_direction.csv.gz; the coin meta.json files; python/oracle (git tree hash of the commit the run used); python/heatloop (rubric, calls, events, guards, the stage); this amendment and PREREG.md. The FINAL stage recomputes them and refuses on any difference.

## 7. Changes to PREREG.md section 6

- Item 7 "build window (2020 to 2025)" is dropped. Re-building the tables is a multi-hour league job and was never needed for a call rule; the tables stay as they are. The delay (G5) stays.
- The ranking said 5m bars look best on the cross-year numbers (shA 55.0, shB 54.3 for BTC/ETH at 15 minutes). The traded pack holds almost no 5m rows (1 BTC, 0 ETH at 15 minutes) because it ranks by heat, which favours the frequent 1m levels. The universe in section 2 holds 38 BTC and 90 ETH 5m rows at 15 minutes, which is why G1 and the universe use the league file, not the pack.

## 8. Power table (research/heat_direction/rubric_power.py, 3,000 sims per scenario)

Pass rate per look, VAL window / FINAL window: no edge 0.07% / 0.10%; real edge .53 with TA adding nothing 2.3% / 2.0%; edge .55 with TA adding nothing 5.3% / 5.8% (core 8 pass 36% / 35%); edge .55 with TA adding value 39% / 40%; edge .57 with TA adding value 85% / 81%. Round 0 measures the real call count and this table is re-run with it before any VAL look.

## 9. Implementation notes, written 2026-11-19 15:10 EST / 20:10 UTC, before round 0 (they fix details; no threshold or check changes)

- DEV folds for check 6 are the three pairs of calendar months (Jan-Feb, Mar-Apr, May-Jun), not equal thirds of the days. VAL blocks are the four calendar months.
- The "non-default fields" tie-break counts the fields that differ from the round 0 spec (all four bars, top 10, hottest, no TA, lag 0).
- A trial goes to VAL only if it is eligible and strictly better than the round's start: more checks passed, or the same number and a strictly larger check-2 lower bound.
- Stall (PREREG section 6): two rounds in a row where the round's best has no more checks than the round's start and under 0.3 points more pooled DEV hit rate stop the DEV rounds.
- The DEV rounds run in one process that loads DEV event files only. The VAL looks are separate runs, taken in round order, stopping at the first pass bit; the twin gate runs inside the look before the ten checks, and a gate failure uses no look. The look prints one bit and a hash prefix; the per-check table goes to a private Drive file.
- Event files: each coin's grid is loaded from 2025-06-01 up to the scope's end (a DEV file holds no VAL minute), the readings are computed over that whole grid, and the event keys of the whole universe (aliases included) are stored with their entry rows from 120 minutes before the scope's first minute. Calls before the scope's first minute are never scored. A call whose 15-minute outcome would reach the end of the loaded grid is dropped, never clipped.
- Twin gate: each of the six twins (ids 1, 2, 3 for each coin) is scored alone on the scope's days (one coin's calls); each must score 2/10 or less and sit within 3 day-cluster standard errors of 50%. The random-side draws reuse the candidate's own calls with a random side on every call (and on every dropped or lapsed call).
- The TA pool is the best-ranked rows (by rank_coin) of the coin at 15 minutes across all four bar sizes, aliases included, 20 or 40 rows.
- Zone edges and the price step come from each coin's meta.json on Drive. live_meta.json (in the repo, hash-checked above) holds a subset of the readings; the smoke stage checks that the two agree where both have a reading.
