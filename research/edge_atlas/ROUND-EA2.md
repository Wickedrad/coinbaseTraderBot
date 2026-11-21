# Round EA-2: is Kalshi's book late by seconds? (recorded days only)

Written Sat Nov 21 2026, 1:43 PM EST / 18:43 UTC; maker section added 2:12 PM EST / 19:12 UTC. Steven's rule (Nov 21, 12:09 PM EST / 17:09 UTC): nothing waits for future days; every test uses days that are already recorded, with the build days picking and the check days judging, both inside the recorded history.

## What was built

`python/subminute/` reduces the bot's own market-data recordings (md-DAY, about 1.7 GB gzip per day) to 1-second grids, about 7 MB per day, kept on Drive (`models/subminute/grids`):

- per 15-minute window of BTC, ETH, SOL, XRP and per second: best YES bid and ask with their sizes, taker volume by side, and the determined result (`lifecycle` event, about a second after the close);
- per coin and per second: the last Kalshi settlement index value (about 6 updates a second), the last value of the fast spot feed (up to 21 a second for BTC), and the perpetual's mid;
- from the second run: every taker trade of the 15-minute markets (time, price, size, side), for the maker simulation.

Ten recorded days, Nov 11 to Nov 20 (full books are only valid after the Nov 10 03:44 UTC fix). Build days Nov 11 to 16 (6), check days Nov 17 to 20 (4). 3,656 windows with a book, a settlement and 30 minutes of index before them.

Coverage on a typical day (Nov 16): 95 of 96 windows per coin have a result; a two-sided book in about 89% of seconds (the first 40 seconds of a window have no book: the bot sees the market about 40 seconds after it opens); the index has an update in 99.9% of seconds.

## Question 1: does the quote lag the index by seconds?

Alignment check first (the grids are aligned): the index's move over the last L seconds, in its own volatility units, explains the quote mid's move over the same L seconds with R^2 0.36 at L=1 s, 0.70 at L=5 s, 0.82 at L=30 s. The book follows the index inside the same second.

Information (slope fitted per price bucket on the build days, R^2 on the check days, entry delayed one second so a quote that is already gone is not counted): the index, the fast spot and the perpetual's mid explain at most 0.04% (R^2 = 3.9e-4) of the quote's next 2 to 30 seconds of movement. That is zero for trading purposes.

Trading (the first second in a range where the move over L seconds is at least 1.5, 2 or 3 units; buy the side the move points to at the ask 1, 2 or 3 seconds later; 7 L values x 3 thresholds x 3 ranges x 4 horizons x 3 delays x 3 signal sources = 2,260 cells with trades; the same trigger with the side flipped is the control):

| Exit | Mean net per contract, all cells, check days | Cells above zero | Best cell picked on build days, judged on check days |
|---|---|---|---|
| sold H seconds later (two taker fees) | follow -3.55c, flip -3.94c | 0 of 2,260 | build -1.3c, check -2.8c (95% interval -3.9c to -1.7c) |
| held to settlement (one taker fee) | follow -1.47c, flip -2.29c | 632 of 2,260 | build +3.0c (-0.2c to +6.2c), check -0.8c (-2.9c to +1.3c) |

Reading: a signal that points the right way is worth about 0.8c per contract over the flipped one, and the spread plus the taker fee cost about 2.3c. No cell survives the check days. The book is not late at one-second resolution; the earlier threads' 1-minute result holds at 1 second.

## Question 2: can a resting (maker) buy earn what adverse selection costs it?

Setup (`python/subminute/maker.py`, same ten days, same split): a buy order rests at the best bid of its side (YES bid, or NO bid = 1 - best YES ask) in one of five price buckets (50-60c up to 90-97c), placed at the first second of a range (60-180, 180-420 or 420-720 s into the window) where the bucket holds, cancelled at 600, 840 or 900 s. It fills when taker volume at its price has used up the queue ahead of it, or when a taker trade goes through its price. Two queue models bracket what cancellations ahead of us would do: `opt` (first in line) and `pess` (the whole visible size at the level sits ahead of us). A fill is held to settlement with no exit, and the maker fee is 0 (the crypto 15-minute series are not in Kalshi's non-standard fee table; a stress arm charges the 0.0175 rate anyway). A second variant cancels, or does not place, when the index has moved 1 volatility unit against the order over the last 10 s. 2 sides x 5 buckets x 3 placements x 3 cancels x 2 queue models x 2 guard settings = 360 rules, 168 per queue model with enough build-day fills (at least 200). Day-cluster intervals.

| Queue model | All 168 rules on check days: mean net per fill, rules above zero | Rule picked on build days | Build days (6) | Check days (4) |
|---|---|---|---|---|
| `opt` | -1.68c, 37 of 168 | buy NO at 60-70c, placed 60-180 s in, index guard on | +4.49c per fill (95% +1.6c to +7.4c), 954 fills, 6 of 6 days positive | -0.18c (-10.6c to +10.2c), 642 fills, 2 of 4 days positive, stress fee -0.62c |
| `opt` | same | same rule without the guard | +4.47c (+2.4c to +6.6c), 1,142 fills, 6 of 6 | +0.19c (-8.8c to +9.1c), 755 fills, 3 of 4, stress fee -0.25c |
| `pess` | -2.44c, 29 of 168 | buy NO at 80-90c, placed 60-180 s in, index guard on | +4.07c (-0.6c to +8.7c), 231 fills, 4 of 6 | -6.24c (-15.2c to +2.7c), 176 fills, 1 of 4, stress fee -6.57c |
| `pess` | same | buy NO at 60-70c, no guard, cancel 600 s | +3.91c (+1.9c to +5.9c), 1,111 fills, 6 of 6 | -0.46c (-9.6c to +8.6c), 736 fills, 2 of 4, stress fee -0.90c |

Reading:

- A resting buy does not earn on the check days. Across the rules, the mean net per fill is -1.7c with the optimistic queue and -2.4c with the pessimistic one, and 37 of 168 (opt) and 29 of 168 (pess) rules are above zero.
- The one pocket that looked real on the build days, buying the NO side as a 60-70c favourite early in the window, earned about +4.5c per fill on every build day and then -0.2c to +0.3c per fill on the check days. The same orders, had every one been filled, would have earned +5.1c to +5.4c on the build days and +1.1c on the check days: the pocket itself shrank between the two periods, and the fill selection (0.6c to 1.3c per fill lower than if all had filled, the adverse selection) took most of the rest.
- The index guard, which was meant to pull orders that are about to be picked off, changes nothing (+0.19c without, -0.18c with). That agrees with question 1: the index carries no usable information about the next quote moves.
- The check cannot rule out a gain either. With four check days the intervals are about 10c wide on each side, so the result is "no gain shown", not "zero proved". The best build-day cell is still the only candidate worth a second look, and the next look is on the same recorded days (pick on any six, judge on the other four, all 210 splits) to see whether the build-day gain was the Nov 11-16 market or a lasting pocket.
- The fills used here are a simulation: queue position, partial fills and cancellations ahead of us are bracketed by the two queue models, not observed. A real resting order would need the paper bot's own fills to confirm any number above.

Round 2 verdict: no edge after fees from the book being late by seconds (question 1) or from resting buys (question 2). Nothing in either study is a candidate for the bot as it stands.
