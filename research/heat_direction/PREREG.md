# Heat map direction loop, phase 1: what "9/10" means

Written 2026-11-19 14:35 EST / 19:35 UTC, revised after two critic rounds at 14:45 EST / 19:45 UTC, before any candidate is scored. Research only: no bot change, no order, tap and live stay off.
Steven's words (19:25 UTC): evaluator-optimizer loops on the heat map parameters "until it passes a 9/10 score on predicting direction within some time frame, including TA that follows or precedes and either signals direction further or invalidates". Phase 1 is direction only (his 19:28 UTC note). Execution, fees and exits are phase 2.

## 1. Plain reading

9/10 means 9 of 10 pre-set pass/fail checks, and checks 1, 2 and 3 must be among the nine, scored by code on days the optimizer never saw. It does not mean 90% accuracy. The literature puts the best honest direction hit rates at 52 to 63%, and the league's stable levels sit at 53 to 55%. A 90% hit rate is not on the table, and a loop told to chase it would fit noise.

## 2. The call and its outcome

- A candidate is a frozen call rule (a JSON spec): which levels are admitted, how firing levels combine into one call per coin, the optional TA layer, the lockout.
- Scored coins: BTC and ETH. SOL and XRP are computed and reported, never scored (their direction flipped between the build years and 2025 in the league; see direction-ranking-2026-11-19.md).
- Data: Binance spot 1-minute bars (the heat map's own substrate), UTC. No Kalshi quote, price, fee or fill is used in phase 1.
- Causality rule. A call with entry minute t is a function of bars that closed at or before minute t-1, and nothing later. Entry price = open of minute t (the OR-HM1 convention). The evaluator proves it: it truncates the raw 1-minute file after minute t-1, rebuilds the readings from that truncated file (no cached features) and must produce the same call, for at least 500 random calls plus every call on the first and last day of each block. A single mismatch voids the run.
- One call per coin per 15 minutes (lockout), so calls never overlap.
- Time frame (scored): 15 minutes. Move = open of minute t+15 minus open of minute t. A price step is the engine's own tick for the coin (heat.tick_units, OR-HM1). Right = move agrees with the call and is at least 1.5 steps; wrong = opposite and at least 1.5 steps; anything smaller is flat, excluded and counted. The flat share is printed with every score and a share above 5% voids the run (a sanity guard; it may never trip, which is fine). The 30-minute read is printed for context and not scored.
- Hit rate = right / (right + wrong).

## 3. The ten checks (1 point each, thresholds fixed now)

Scored on the pooled held-out set (section 4). A missed sample floor scores that check 0, never a pass by default. Checks 1, 2 and 3 are required: fewer than all three means no pass whatever the total.

| # | Check | Pass when | Floor |
|---|-------|-----------|-------|
| 1 | Level (required) | pooled hit rate >= 55.0% | 800 decided calls |
| 2 | Not luck (required) | 97.5% one-sided lower bound > 50.0%, day-cluster bootstrap (2,000 resamples, seed 20261119) | 800 |
| 3 | Beats naive (required) | hit rate minus the best of ten naive side rules at the same call times >= 2.0 points: follow the last 1, 5, 15 or 60 minute move, fade it (eight rules), always UP, always DOWN | 800 |
| 4 | Both coins | BTC >= 53.0% and ETH >= 53.0% | 300 each |
| 5 | Weeks | hit rate > 50.0% in >= 65% of full ISO weeks (Monday to Sunday UTC); a full week with fewer than 20 decided calls counts as failed, never dropped | 8 full weeks |
| 6 | Blocks | hit rate > 50.0% in every held-out block (calendar month in VAL, equal fourths of the window in FINAL); a block under its floor scores 0 | 150 per block |
| 7 | Both sides | UP calls >= 52.0% and DOWN calls >= 52.0% | 150 each |
| 8 | One minute late | same calls, entry one minute later (open of t+1, outcome at t+16): pooled >= 53.0% | 800 |
| 9 | TA confirms | calls the TA layer confirms hit >= 3.0 points above calls it does not, and the 90% one-sided day-cluster lower bound of that difference is above 0 | 150 each |
| 10 | TA invalidates | calls the TA layer invalidates (scored as if made at their own entry minute, under the same one-per-15-minutes lockout) hit <= 50.0%, at least 3.0 points below the calls it keeps, with the same cluster lower bound above 0 | 150 invalidated |

Why 55.0%: with an entry at 50 cents the Kalshi taker fee is 1.75 cents a contract, so holding to settlement breaks even near 51.75%. 55% leaves about 3 points of room for the spread and for exits, which are phase 2. Passing this rubric is necessary for a profit, not sufficient: the quote's own mid is the real competitor and the spot-gap tests found no lag.

Naive rules note: follow and fade of one move are complements, so the ten rules are really four distances (the 1, 5, 15 and 60 minute move) plus the always-UP/DOWN pair. They are all listed so nothing cheaper can pass for a signal.

"TA that follows or precedes", built from the oracle's relationship readings, under the causality rule:
- Precedes: a confirming reading from a different family fired the same way within k minutes up to t-1; the call is made at t. It confirms that call (check 9).
- Follows: the base call lapses and a new call is made at the confirmation minute t' (its own entry, decided from bars up to t'-1, outcome measured from t'). It is never a filter applied to an earlier call. A lapsed base call starts no lockout; the follow call starts its 15 minutes at t'. For check 9 the follow calls are the confirmed set and the lapsed base calls, scored as if made at their own minute, are the unconfirmed set.
- Invalidates: an opposing reading within k minutes up to t-1 drops the call at t. A reading that appears after t cannot drop it. The dropped call is scored as if made at t (check 10). A later reading may produce a new call at its own minute.
A candidate with no TA layer scores 0 on checks 9 and 10, so it can reach 8 at most. The core 8 (checks 1 to 8) is printed beside the total on DEV only (see section 4), so a real direction edge that TA does not improve is visible as "8/8 core, 0/2 TA" and is not buried.

## 4. Data and who sees what

- Tables (levels, directions, weights) come from the league: build 2020 to 2024, check 2025, no 2026 minute in them. The loop never refits a table on a 2026 minute. The direction ranking used league files only. The Aug to Oct 2026 verdicts (HO-1) were read for context and set no scope and no threshold; even so, the 15 minute and BTC/ETH choices were made by people who had seen those verdicts, so VAL is held out from the optimizer and is not virgin to the project.
- DEV (the optimizer sees every number): 2026-01-01 to 2026-06-30, scored in three two-month folds.
- VAL (held out): 2026-07-01 to the last full calendar month on file, scored pooled. The evaluator writes the per-check VAL table to a private Drive file. During the loop the logs and the director see one bit per round for the one candidate DEV picked: pass (9 or more including checks 1, 2 and 3, and the twin gate) or not. The bit decides freeze or continue and nothing else: the next round is chosen from DEV only, never from VAL. The per-check table is read once, when the loop stops (a pass or a stall), and after that VAL is spent. At most one VAL look per candidate and 6 in all, because reuse of a held-out set inflates its score (Feldman 2019, arXiv 1905.10360: the error bound degrades from the order of sqrt(log k / n) to sqrt(k / n) for k adaptive looks; Nakkiran 2018, arXiv 1809.05596) and picking the best of many trials inflates it too (Bailey et al., The Probability of Backtest Overfitting, SSRN 2326253). Every trial is counted and printed beside any pass.
- The grid (every parameter and its values), the candidate budget, the twin seeds and the thresholds above are frozen in Amendment 1, with a hash, before round 0. The exact last day on file is recorded there too. If a month is missing, that block is dropped and the floors stay.
- FINAL decides, once. At the freeze everything that can change a call is hashed: the candidate spec, the league tables and meta files it reads, the oracle readings code (git commit), the evaluator code and the files holding the bars above. The evaluator verifies every hash before FINAL is scored and a mismatch voids the run. One calendar window is fixed: whole ISO weeks starting the first Monday after the freeze, long enough that the DEV call rate gives about 900 decided calls (at least 8 weeks, at most 16). It is evaluated once, on its last day, with the same ten checks, no peeking before. No second candidate is run on those days. If FINAL fails, phase 1 ends as a negative result for that candidate; a new candidate needs new days and Steven's word, and its trial count carries over.
- This is not a sealed week: nothing is locked away or waited out beyond the one fixed window; it is count-only feedback plus a freeze.

## 5. Evaluator self-test (the twin gate, not a point)

Before round 0, and for every candidate before it is sent to VAL: the rule is run on the held-out days of the three no-signal twins per coin (OR-HM1: every bar keeps its size and place, its direction is a coin flip), and a random-side rule with the same call times is drawn 200 times. Every twin (seeds fixed in Amendment 1) must score 2/10 or less and have a pooled hit rate inside 50 +/- 3 day-cluster standard errors (six twins, so about 1.6% false failure by chance); the random-side draws must score 2/10 or less in at least 95% of draws. If not, the pipeline leaks or the rubric is too loose, and every pass is void until fixed.

Simulation (research/heat_direction/rubric_power.py, 3,000 sims per scenario, 4 calls per coin per day; it models calendar weeks and months, a day effect (sd 3 points), BTC/ETH outcomes that share the hour (correlation about 0.6), a 93% overlap between on-time and late entry, ten naive rules clustered the same way, the required checks, cluster bounds on checks 9 and 10 and the FINAL window). Pass rate per look, VAL window / FINAL window: no edge 0.07% / 0.10% (0.40% over 6 independent VAL looks; FINAL is one look); real edge .53 with TA adding nothing 2.3% / 2.0%; edge .55 with TA adding nothing 5.3% / 5.8% (the core 8 pass 36% / 35%); edge .55 with TA adding value 39% / 40%; edge .57 with TA adding value 85% / 81%. So the bar is very hard to clear by luck, and a modest edge (.55) clears it only about 4 times in 10 even when TA helps. It is a model, not a measurement: round 0 measures the real call count and amendment 1 copies the table.

## 6. The loop

- Optimizer: a scripted search over the frozen grid on a GitHub runner (no model tokens). Evaluator: code. Critic: one single-angle Sonnet pass per round aimed at leakage and overfit, only when a candidate reaches 8 or more on DEV. Opus only if a critic finds something delicate. Scite when a round needs context.
- Round 0: the live lane's current settings (top 10 single levels by rank, 15 and 60 minute horizons, pair conflict skip, context size) replayed on DEV, VAL not touched; plus the ten naive rules, the causality test and the twin gate. This calibrates call counts and checks the evaluator.
- Focus order (from direction-only evidence, direction-ranking-2026-11-19.md): 1 coin scope BTC and ETH; 2 horizon 15 minutes (30 context); 3 reading bars 5m and 1m; 4 admission (cross-year share and sample thresholds, one level per near-duplicate family); 5 combiner (hottest single vs top-k vote, margin, 60-minute context agree only); 6 TA layer (confirm precedes or follows, invalidate), the least supported lever, so the likeliest first failure; 7 entry delay and build window (2020 to 2025, still no 2026 minute); 8 simplify: the final candidate is the one with the fewest free parameters among equals.
- Stop: a candidate gets the VAL pass bit (freeze it, then FINAL); or 6 rounds; or a stall (two rounds in a row with no gain in DEV total and under 0.3 points of DEV pooled hit rate). A stall is reported as a result with the VAL table of the last candidate read once. It is likely.
- On a FINAL pass of 9 or more: report to Steven that direction has an edge on unseen days and ask for his word on phase 2. Nothing goes into the bot or the protected heat curves without his explicit word and a logged deploy.
