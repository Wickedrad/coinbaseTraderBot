# Round EA-6: fresh days for the saved typed rule, SOL and XRP, days before April, and the hourly lean (recorded days only)

Written Wed Nov 25 2026, about 8:45 PM EST / 01:45 UTC; results filled in as the runs landed (see the stamps). Follows round 5c (ROUND-EA5c.md). Same rules: recorded days only, paper only, no order, no bot change, day-cluster intervals, nothing waits for a future day. Pre-registered in PREREG-EA6.md before each read. Steven's word that started it: "Resume and Continue until 10:30 PM" (8:11 PM EST / 01:11 UTC).

## Result

RESULT_PLACEHOLDER

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

What it changes: the T1 line of `typed_rules.md` now reads RETIRED, with this table. Nothing else changed; nothing was running on it.

## 2. The hourly lean, a second unseen block (Nov 23 to Nov 25; zero model tokens)

Pre-registered in PREREG-EA6.md part 2, read on main with `loss-review-stages.yml` (ladder run 45734554471, marketbase run 45735214200, anatomy run 45735969899). The Nov 12-18 lean failed to repeat on Nov 19-22; this block asks whether it comes back.

- Hourly ladders, 3 days: YES edge -2.8c (se 2.6c, net -3.8c, positive on 1 of 3 days); NO mid-price net +1.2c (edge +2.8c, se 4.0c, positive on 2 of 3 days). H6 sign check passes; the se bar and the five-day rule cannot be met with three days, so it is not a pass.
- 15-minute markets, 4 coins, 3 days (1,152 markets): held to settlement, NO side -0.2c a contract after fees, YES side -3.0c. Near fair, as in Nov 19-22.
- The lane (the paper bot): anatomy found trades for 2 of the 3 days (the archive did not yet hold Nov 25). 623 trips, net -$260 (fees $525, before fees +$265); the Nov 19-22 block lost $2,090 in 3 days.
  - H7a (lane hourly YES edge below -3c): not testable. Hourly YES entries have been off in paper since Nov 20 21:11 UTC, so there are no trades; it cannot pass.
  - H7b (lane NO side above +2c on a majority of days): met on 2 of 2 days (276 trips, edge +7.0c, net +$100 after $195 fees).
  - H7c (lane 15-minute NO above the market's 15-minute NO by 2c): met (lane +7.0c on 199 trips against market +0.9c), on 2 days of the lane against 3 of the market.
  - The 15-minute YES side lost $360 on 347 trips (edge +0.3c, fees $330); the loser cuts lost $1,080 on 224 trips (held to settlement they lost $805).
- Read: across the three blocks the hourly YES lean and the NO mid lean point the same way again in this one (-2.9c YES, +2.0c NO mid pooled over 14 days, about +0.4c net after fees), but only one of three blocks cleared its own threshold and the effect is smaller than the fee. The pre-registered condition for asking Steven for a change (hourly YES negative and NO positive with H7a to c all passing) is NOT met, because H7a cannot pass while hourly YES is off. No ask. Two days of lane trades do not show the Nov 20 changes worked.

SX_PLACEHOLDER

BACK_PLACEHOLDER

## What was not done

No order, no bot change, no protected heat-curve edit, no phase 2, no future-day test. T1 was never in the bot. Everything here is aggregates on recorded days; candles for the new days are kept on Drive (raw/oracle-history/kalshi) and the tables at models/subminute/fresh/k15, models/subminute/fresh/k15back and models/subminute/daytypes/solxrp.

## Code and runs

`python/subminute/fresh.py` (new; `--back` for the backward block) with `tests/test_fresh.py` (52 subminute tests pass); workflows `heat-direction.yml` (job dtfresh), `dtsx.yml` and `dtback.yml` (own workflows so the long downloads run side by side). Commits 93548914 and b768ee65 (pre-registration), b81d2494 (fresh.py and dtfresh), c71a8996 (dtsx), a56345c8 and debaa780 (dtback). Runs: 45734547381 (fresh), 45736634631 (SOL and XRP), 45737405497 (backward), 45734554471, 45735214200 and 45735969899 (hourly lean).
