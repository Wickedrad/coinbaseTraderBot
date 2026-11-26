# Round EA-6: fresh days for the saved typed rule, SOL and XRP, days before April, and the hourly lean (recorded days only)

Written Wed Nov 25 2026 between about 8:45 PM EST (01:45 UTC) and 9:48 PM EST (02:48 UTC), as the runs landed. Follows round 5c (ROUND-EA5c.md). Same rules: recorded days only, paper only, no order, no bot change, day-cluster intervals, nothing waits for a future day. Pre-registered in PREREG-EA6.md before each read. Steven's word that started it: "Resume and Continue until 10:30 PM" (8:11 PM EST / 01:11 UTC).

## Result

**T1 is a filter that loses less, not a profit; it does not travel to SOL and XRP; the hourly lean did not clear its bar. Nothing was ordered and nothing in the bot changed.**

- **T1 on days it never saw.** Fresh days Nov 5 to Nov 25: typed days -0.87c a fill (9 days, 180 fills), CONTRADICTED, retired at 8:35 PM EST / 01:35 UTC. Days before the build (Mar 1 to Apr 12, which Kalshi still lists): +2.01c (7 days, 101 fills), SUPPORTED by one fill over the floor. Pooled over all 64 unseen days: **+0.17c a fill** (lower bound -2.62c, 281 fills), 1.16c above the other days, so the pre-registered pooled rule put T1 back to PRELIMINARY at 9:36 PM EST / 02:36 UTC. The typed days beat the other days in every block (0.9c to 3.1c), but their own level on unseen days is about zero: about 3 cents per typed day, far under $0.10 an hour and nowhere near $2.60.
- **ETH alone** has been positive in all five blocks (unseen +2.85c on 136 fills, lower bound -1.12c) and BTC alone is not (-2.35c): reported, not saved (picked after the fresh read).
- **SOL and XRP 15-minute (89 days):** T1 DOES NOT CARRY (check typed +0.04c against +0.25c on other days, clean typed -2.22c). The day-type search found 0 typed rules in 3,024 tests.
- **Hourly lean, Nov 23 to Nov 25:** the sign is back (YES -2.8c, NO mid +2.8c edge; +1.2c net) but three days cannot pass; the lane NO side and lane 15-minute NO beat the market's by about 6c on 2 lane days (H7b and H7c met), H7a cannot be tested (hourly YES is off). The condition for asking Steven for a change is not met. No ask.

## 1. The saved typed rule T1 on days it never saw (Nov 5 to Nov 25, 21 days)

T1: BTC and ETH 15-minute, resting YES buy at the best bid, 90 to 97 cents, placed in minutes 6 to 9, cancelled at minute 14, held to settlement, only after a day whose YES share was at or below 0.4754 (the build cut). Nothing was searched or tuned; the rule and its verdict were written down before the days were read (job dtfresh, run 45734547381, fresh.py).

The same run re-read the three original blocks, and ALL scope reproduced them exactly (+1.72c, +3.19c, +1.31c; BTC alone +1.17 / +3.65 / +0.15c, ETH alone +2.33 / +2.78 / +2.35c), so the plumbing is the same and the fresh read is usable.

| Block (typed days) | Typed days: net c per fill (day-cluster lower bound), fills | Same rule on the other days |
|---|---|---|
| Build, Apr 13 to Jul 24 (34) | +1.72c (+0.06), 759 | not used |
| Check, Jul 25 to Sep 13 (15) | +3.19c (+0.40), 389 | +0.09c (-1.73), 882 |
| Clean, Sep 14 to Nov 4 (16) | +1.31c (-1.19), 358 | -1.60c (-3.61), 873 |
| **Fresh, Nov 5 to Nov 25 (9 of 21)** | **-0.87c (-4.91), 180** | -1.79c (-6.11), 272 |

Pre-registered verdict: **CONTRADICTED** (the typed mean is at or below zero). Details:

- All 21 fresh days together lost 1.43c a fill (452 fills); the typed days did 0.92c better than the others, which is the right direction, but both are negative.
- A random pick of 9 of the 21 fresh days does as well or better 39% of the time (permutation p 0.39), so the typed pick adds nothing visible on this block.
- BTC alone: -4.13c (9 days, 90 fills, lower bound -9.27c, p 0.75). ETH alone: +2.39c (90 fills, lower bound -3.43c, p 0.14). ETH has been positive in all four blocks now; its intervals cross zero in each block but the first.
- Nine typed days is a short block, so the interval is wide (the lower bound of -4.9c says little). The honest reading is that the one look the rule had at days it never saw did not support it, which is what the pre-registered verdict retires it for. It is not a proof that there was never an edge.
- The mean of every resting-buy rule on the fresh days sits at about -2.0c for every day type (weekend -2.16c over 6 days, weekday -2.02c over 15 days): the loss is a little smaller than in the earlier blocks (-2.6c to -3.0c), and the weekend gap shrank to 0.14c.

What it changed at the time: the T1 line of `typed_rules.md` was set to RETIRED (8:35 PM EST / 01:35 UTC). Part 4 below then put it back to preliminary by the pre-registered pooled rule; both steps are on the record.

## 2. The hourly lean, a second unseen block (Nov 23 to Nov 25; zero model tokens)

Pre-registered in PREREG-EA6.md part 2, read on main with `loss-review-stages.yml` (ladder run 45734554471, marketbase run 45735214200, anatomy run 45735969899). The Nov 12-18 lean failed to repeat on Nov 19-22; this block asks whether it comes back.

- Hourly ladders, 3 days: YES edge -2.8c (se 2.6c, net -3.8c, positive on 1 of 3 days); NO mid-price net +1.2c (edge +2.8c, se 4.0c, positive on 2 of 3 days). H6 sign check passes; the se bar and the five-day rule cannot be met with three days, so it is not a pass.
- 15-minute markets, 4 coins, 3 days (1,152 markets): held to settlement, NO side -0.2c a contract after fees, YES side -3.0c. Near fair, as in Nov 19-22.
- The lane (the paper bot): anatomy found trades for 2 of the 3 days (the archive did not yet hold Nov 25). 623 trips, net -$260 (fees $525, before fees +$265); the Nov 19-22 block lost $2,090 in 3 days.
  - H7a (lane hourly YES edge below -3c): not testable. Hourly YES entries have been off in paper since Nov 20 21:11 UTC, so there are no trades; it cannot pass.
  - H7b (lane NO side above +2c on a majority of days): met on 2 of 2 days (276 trips, edge +7.0c, net +$100 after $195 fees).
  - H7c (lane 15-minute NO above the market's 15-minute NO by 2c): met (lane +7.0c on 199 trips against market +0.9c), on 2 days of the lane against 3 of the market.
  - The 15-minute YES side lost $360 on 347 trips (edge +0.3c, fees $330); the loser cuts lost $1,080 on 224 trips (held to settlement they lost $805).
- Read: the hourly YES lean and the NO mid lean point the same way again in this block (-2.9c YES, +2.0c NO mid pooled over 14 days, about +0.4c net after fees), but only one of three blocks cleared its own threshold, and fees take most of it. The pre-registered condition for asking Steven for a change (hourly YES negative and NO positive with H7a to c all passing) is NOT met, because H7a cannot pass while hourly YES is off. No ask. Two days of lane trades do not show the Nov 20 changes worked.

## 3. T1 on SOL and XRP 15-minute (job dtsx, run 45736634631; PREREG-EA6.md part 3)

Kalshi's 15-minute candles for SOL and XRP, read only: 89 days, Aug 30 to Nov 26 (the cap of 9,000 markets a series; Nov 26 is a part day), kept on Drive at raw/oracle-history/kalshi/KXSOL15M and KXXRP15M. Build Aug 30 to Oct 12 (44 days), check Oct 13 to Nov 3 (22), clean Nov 4 to Nov 26 (23). The day-type search as in round 5c: 3,024 typed tests, 0 typed rules, label-shift placebo mean 0.01 rules (p 1.0). The fixed rule T1 at the pair's own bottom-third cut (previous-day YES share at or below 0.4896). Net cents per fill, typed days against the other days (days, fills):

| Scope | Build | Check | Clean |
|---|---|---|---|
| SOL and XRP (ALL) typed | +0.60c (15d, 427) | +0.04c (9d, 224) | -2.22c (13d, 324) |
| SOL and XRP (ALL) other days | +1.65c (28d, 723) | +0.25c (13d, 326) | -1.79c (9d, 190) |
| SOL alone, typed | +1.76c (15d, 243) | +1.49c (9d, 107) | -1.87c (13d, 165) |
| XRP alone, typed | -0.93c (9d, 184) | -1.29c (9d, 117) | -2.57c (13d, 159) |

Pre-registered verdict: **DOES NOT CARRY.** It needed the typed mean above zero and at least 0.25c above the other days in both check and clean with 100 or more fills each: check is 0.21c below the other days and clean is negative. Weekends were worse again (every rule pooled: -3.1c, -3.1c, -2.6c against -2.6c, -2.7c, -2.2c on weekdays), the fifth data set to show it. The scope line of T1 in `typed_rules.md` now says BTC and ETH only, not SOL, not XRP.

## 4. The recorded days before April, and all the days it never saw pooled (job dtback, PREREG-EA6.md part 4)

Written down before the days were fetched (8:40 PM EST / 01:40 UTC): the Kalshi API still lists BTC and ETH 15-minute markets back to Dec 16 2025, so the rule could be read once on days before the first day the earlier rounds kept. The 40-minute download (run 45737405497) reached Mar 1 to Apr 12 (43 days, both coins); a Dec 16 to Feb 28 stretch of about 74 days is listed but not downloaded (about 6,700 markets a coin are left for a later run). The first two attempts at the read step stopped on my own mistakes (a shell pipe under pipefail, then a day-completeness line that treated every Thursday as short, because Thursdays have fewer markets listed). Both were fixed from market counts alone, with a note in the pre-registration before the rule was read on any backward day; the third attempt read the numbers once (run 45743157839).

| Block (typed days) | Typed days: net c per fill (day-cluster lower bound), fills | Same rule on the other days |
|---|---|---|
| Build, Apr 13 to Jul 24 (35 now, 34 before) | +1.86c (+0.23), 782 | -0.54c (-2.20), 1,580 |
| Check, Jul 25 to Sep 13 (15) | +3.19c (+0.40), 389 | +0.09c (-1.73), 882 |
| Clean, Sep 14 to Nov 4 (16) | +1.31c (-1.19), 358 | -1.60c (-3.61), 873 |
| **Fresh, Nov 5 to Nov 25 (9 of 21)** | -0.87c (-4.91), 180 | -1.79c (-6.11), 272 |
| **Back, Mar 1 to Apr 12 (7 of 43)** | +2.01c (-1.17), 101 | -0.64c (-2.53), 624 |
| **Pooled unseen, fresh + back (16 of 64)** | **+0.17c (-2.62), 281** | -0.99c (-2.84), 896 |

Verdicts, as pre-registered:
- BACK, ALL: SUPPORTED (typed mean above zero, 101 fills against a floor of 100, 2.65c above the other back days). Weak support: 7 typed days, the permutation check says a random pick of 7 of the 43 days does as well 12% of the time, and BTC alone is +0.56c (55 fills) while ETH alone is +3.76c (46 fills, under its floor).
- POOLED UNSEEN, ALL: typed mean +0.17c, 281 fills (floor 250), 1.16c above the other unseen days. All three conditions hold, so T1 goes from RETIRED back to PRELIMINARY in `typed_rules.md`.
- ETH alone (named in advance, reported not saved): +3.76c on the back days (46 fills), +2.39c on the fresh days (90), +2.85c pooled (136 fills, lower bound -1.12c) against BTC alone -2.35c pooled (145 fills). ETH has been positive in all five blocks.
- Plumbing: the check, clean and fresh numbers reproduce exactly. The build block moved from +1.72c to +1.86c because April 13 now has a previous day (April 12) and became a typed day (35 days, 782 fills), and the build tercile cut moved from 0.4754 to 0.4740; no day outside the build block changed type.

How to read it, without flattering the rule: the day type is consistent, since the typed days beat the other days by 0.9c to 3.1c in every block of five (6 counting the pool). The level is the problem. On days the rule never saw, the typed days earn +0.17c a fill with a lower bound of -2.6c: about 3 cents per typed day at 17 fills a typed day, on a third of the days. That is a smaller loss than the other days, not a profit, and nowhere near $2.60 an hour. The one honest use of T1 is as a filter that tells which days the same buy loses less. The placebo p of 0.06 and the roughly 40,000 typed tests it was picked from still stand.


## What was not done

No order, no bot change, no protected heat-curve edit, no phase 2, no future-day test. T1 was never in the bot. Everything here is aggregates on recorded days; candles for the new days are kept on Drive (raw/oracle-history/kalshi) and the tables at models/subminute/fresh/k15, models/subminute/fresh/k15back and models/subminute/daytypes/solxrp.

## Code and runs

`python/subminute/fresh.py` (new; `--back` for the backward block) with `tests/test_fresh.py` (52 subminute tests pass); workflows `heat-direction.yml` (job dtfresh), `dtsx.yml` and `dtback.yml` (own workflows so the long downloads run side by side). Commits 93548914 and b768ee65 (pre-registration), b81d2494 (fresh.py and dtfresh), c71a8996 (dtsx), a56345c8 and debaa780 (dtback). Runs: 45734547381 (fresh), 45736634631 (SOL and XRP), 45737405497 (backward), 45734554471, 45735214200 and 45735969899 (hourly lean).
