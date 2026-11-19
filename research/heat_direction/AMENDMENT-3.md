# Amendment 3 to the DS pre-registration: the frequency frontier, the lockout test (E9) and a FINAL sized to the rule

Written 2026-11-19 6:35 PM EST / 23:35 UTC, after the first DS run was read (ROUND-DS.md) and before any floor above 3 is scored. Research only: no order, no bot change, no protected heat curve. It changes how the FINAL of PREREG-3.md section 8 is sized and which rule goes into it. It changes no threshold of E1 to E8, no rule of the grid, and no scoring of a rule. PREREG-3.md sha256 `c3b9b51e4200440b532de817483b80f9379d57ee2a1f4fa9ae38dd1325bbe9cf` stands.

## 1. Why, in plain words

The first run (ROUND-DS.md) found that a transparent rule, chosen only from earlier days, called the next 15 minutes right 56.13% of the time on 17,177 decided calls out of sample, and that three no-signal twins gave 50.4%. E8 failed: the frozen rule makes 4.55 decided calls a day and E8 asked for 10. Section 8 of PREREG-3.md has a design error of mine: four whole weeks and at least 800 decided calls need 28.6 calls a day, which no rule that selective can make. Two questions are left open by that, and this amendment answers them before they are scored:
1. How does the out-of-sample hit rate fall as the rule is forced to call more often (the frequency frontier)?
2. Which rule, if any, goes into a FINAL that can end in a reasonable time, and how long must that FINAL be?

## 2. What was known when this was written (so nobody reads more into it than is there)

- The floor-3 result of PREREG-3.md (nested 56.13%, E1 to E7 pass, E8 fails, the frozen rule, the S2 league with 139 survivors against 27, 0 and 0 on the twins) was read before this was written. The floors 6 and above, the lockout numbers and E9 had not been computed on real data. The synthetic smoke test of the code (random data, no signal) was run to test the plumbing only.
- The list of floors differs from the one sketched in ROUND-DS.md section 7 (6, 10, 20, 30, 50): it is 3, 6, 10, 15, 20, 30, 40, 60, fixed here, finer, before any is scored.
- The nested number at each floor is out of sample for the choice of rule inside that floor. The choice of the floor itself (section 5) is made on those numbers, so the chosen floor's nested number carries a best-of-eight optimism. It is reported as such. The only confirmation is the FINAL on days nobody has read.
- The test block 2026 Jul-Oct is not clean (PREREG-3.md section 2); it counts as one ordinary block here too.

## 3. The frequency frontier (S1b)

For each floor F in {3, 6, 10, 15, 20, 30, 40, 60} (decided calls a day, both coins pooled, averaged over the days of the window being scored), the whole of PREREG-3.md section 4 is repeated with F in place of the eligibility of 3 a day: selection on the training days, the Reality Check set of eligible rules, the blocks that count for a rule in PBO, the final rule on all 14 blocks, and the benchmark. Nothing else changes: same 40,320 rules, same blocks, same purge, same score (p - 1.96 x SE), same tie-break, same seeds (20261123, 20261124), same twins (seeds 1 to 3). Real coins (twin 0) and the three twins are run at every floor.

At each floor the report gives E1 to E6 and E8 as PREREG-3.md defines them (E8 stays at 10 decided calls a day overall and 5 in the last block), and E7 from the three twins at that floor (each twin's nested pooled hit within 49.0% to 51.0%). A floor at which some test block has no eligible rule has no pooled nested result and fails E1 to E3 and E9.

## 4. E9: the lockout replay

The sweep counts every row where a rule speaks, so a burst of neighbouring minutes is many calls with overlapping outcomes. A trader and a forward test see one call, then wait 15 minutes. For each floor, every fold's selected rule is replayed on its own test block with the 15-minute lockout of PREREG.md (after a call at minute e no new call on that coin before minute e + 15; the lockout runs over the whole stretch, so a burst straddling the first day of a block is entered as in a continuous run), per coin, scored at 15 minutes with the same flat band. The replays are pooled over the 10 test blocks and both coins.

- E9 = the lockout pooled hit >= 53.0% and its day-cluster 97.5% lower bound > 51.0% (the E1 and E2 numbers, on the calls that do not overlap).
- Reported: lockout decided calls a day, the lockout excess a day = decided calls a day x (hit - 0.5), by block and by coin.
- The frozen rule of each floor is replayed the same way over all days: decided calls a day overall and in period C (2026-01-01 to 2026-10-31), hit by block.

The replay code is `python/dirsweep/replay.py`; its test shows that with no lockout it reproduces the sweep's histograms exactly.

## 5. One FINAL candidate, chosen by a rule fixed now

A floor qualifies when all of these hold on the real data:
1. E1 to E6, E8 and E9 pass.
2. E7 passes at that floor (all three twins within 49.0% to 51.0%).
3. The frozen rule of that floor, with the lockout, makes d decided calls a day in period C and W = ceil(1000 / (7 d)) is at most 8 whole weeks.

Among qualifying floors the candidate is the one with the largest lockout excess a day (section 4); a tie goes to the lower floor. Its frozen rule is the FINAL candidate. The rule is applied by `python -m dirsweep.stage choose` on the saved results; nobody picks by eye.

If no floor qualifies, the result is written as "no edge shown at a frequency that can be tested in eight weeks", the table of all floors is reported in full, and no FINAL is run. The pre-registered verdict of PREREG-3.md for floor 3 (E8 fails) is not changed by this amendment either way.

## 6. The FINAL, as changed

PREREG-3.md section 8 stands except:
- Candidates: the one rule of section 5. The S2 survivor is dropped as a FINAL candidate: its history (52.3% to 53.0% hit) lies below the 53.0% bar it would be tested against, and the oracle heat metric favours frequent weak rules. Its league and survivor counts stay in the report as the oracle result. The always-on fade rule that is the benchmark of E5 for the chosen floor is scored on the same FINAL days and reported, not judged.
- Length: W whole ISO weeks (section 5), W between 1 and 8, W = ceil(1000 / (7 d)), d the chosen frozen rule's lockout decided calls a day in period C. The expected number of decided calls is then about 1,000.
- Start: unchanged, the first Monday at least 2 days after the commit that writes FREEZE-DS.json. The faster alternative of using days since 2026-11-01 that no DS stage has read was considered and rejected: whether anybody has glanced at those days cannot be proved, and a forward test needs the clock to start after the freeze.
- Pass: unchanged. At least 800 decided calls, hit >= 53.0%, day-cluster 97.5% lower bound > 50%, BTC and ETH each >= 51.0%, calls made with the 15-minute lockout per coin. Fewer than 800 decided calls is a fail, not a reason to extend. One look, at the end of week W.
- FREEZE-DS.json is written by the commit that also holds the output of `choose`, with the sha256 of PREREG-3.md, this file, every file of `python/dirsweep`, the rule (rule id and its description), W, and the first and last day of the FINAL, before any FINAL day is fetched.
- Data: Binance public daily 1-minute files for BTCUSDT and ETHUSDT from two days before the first Monday to the last Sunday, fetched by a top-up job after the weeks end. The two warm-up days score nothing. The scorer is committed with the freeze, so it is hashed too.
- A pass is still only "direction edge shown on days nobody read". It does not start phase 2 (execution into profit, fees, Kalshi prices), which needs Steven's word.

## 7. Not in this amendment

- S3 (the TA-Lib vocabulary): needs its own amendment, AMENDMENT-4, written before it is scored. PREREG-3.md section 6 named this file for it; the frontier came first.
- Horizons 30 and 60 as S1 targets, other coins, any change to the grid, any use of Kalshi prices or fees.
- Any order, any bot-code change, any change to a protected heat curve.

## 8. Compute and outputs

GitHub runner, no model tokens: the stage `dsfloor`, four jobs (twin 0 to 3), one `HEATLOOP ds` line per floor, aggregates and rule parameters only; `floors-twin<N>.json` goes to Drive `models/heat-direction-loop/dsfloor-twin<N>`. A local synthetic run of the same command took about two minutes and 3 GB.

## 9. Known limits

Everything in PREREG-3.md section 9. Also: the choice among eight floors is a selection (section 2); the lockout greedily keeps the first row of a burst, which is a fair stand-in for a trader but not the only way to place calls; period C is the base for the call rate and call rates drift between years (one fold's rule went from 3.1 to 10.8 calls a day), so d is an estimate and the 800-call bar is the safety margin; Binance bars only: no fees, spread, slippage or Kalshi price is in any number here.
