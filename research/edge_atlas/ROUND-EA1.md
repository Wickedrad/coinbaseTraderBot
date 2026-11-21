# Edge atlas, round 1: the direction rule and every spot feature, scored on Kalshi's own recorded quotes (Nov 21 2026, 12:46 PM EST / 17:46 UTC)

Recorded days only (Steven, Nov 21 12:06 and 12:09 PM EST): Kalshi 15-minute BTC and ETH windows Apr 13 to Nov 3 2026, 40,056 windows with real bid, ask and settlement, plus Binance 1-minute bars. Build Apr 13 to Jul 31, check Aug 1 to Oct 31, clean Nov 1 to 3. All money is net dollars per contract after the taker fee on a $10 stake. GitHub runs 44928660380, 44929259543, 44929906164, 44930891187 (stages dsrecent, dskalshi, dsatlas); code python/dirsweep/{kscore,kfair,kinfo}.py.

## Result
**No edge after fees in this family.** Kalshi's quote already holds what the 1-minute spot data knows, and the taker fee plus spread (about 2.5 cents round trip at 50 cents) is larger than anything found.

| Question | Answer |
|---|---|
| Frozen direction rule (31574) on coin direction, Nov 1-19 (never used to pick it) | 56.4% on 793 calls, lower bound 52.7% (misses the old 800-call bar by 7) |
| Same rule priced on the real contract, Apr 13 to Nov 3 (205 days, 9,528 calls) | wins 50.8% at an average entry of 49.8c: **-0.7c per contract** (95% range -1.9 to +0.5c); delay of one more minute -0.9c |
| Placebos on the same calls | random side -2.3c, flipped side -3.9c; unfiltered same-phase fade -1.6c |
| Where the coin-direction hit goes | spot score of these calls 54.1%; same window from its open 51.7 to 52.8%; with the 60-second averages the contract settles on 50.8 to 52.1%; recorded settlement 50.2 to 51.4%. The sweep measured from the call minute with instant prices, the contract measures the whole window on averaged prices: about 3 of the 4 points were measurement, not edge |
| Do all the spot features add to the quote? (boosted residual of the quote, 18 features incl. hour of day, flow, the other coin; fitted on build) | log-loss 0.4737 to 0.4732 on check (0.1%), 0.4834 to 0.4829 on clean. Traded against the ask at 3c edge: 373 trades on check, +2.6c (range -3.2 to +8.3c); no trades at 6c |
| Win rate by price bucket, no model, 60 cells | mid prices lose 3 to 4c, longshots (ask 2-10c) lose 1.1c, one cell has a positive build lower bound: buy YES at an ask of 90-98c in minutes 5-9, +0.8c build, +0.95c check, -1.4c on 3 clean days (n=130). That is about $0.10 per $10 trade, about $4 a day across both coins, with a $9 loss on 6% of trades: not a path to $4.50/h |

A first spot-against-quote model (kfair.py) used Kalshi's strike, which sits a median $45 below Binance on BTC, so it was weak and its "adds nothing" is not relied on; the residual test above uses the move since the window open from the same grid and replaces it.

## What it means
- Direction calls on 15-minute crypto contracts cannot reach the target on these quotes: it takes a spot signal worth more than the fee, and the quote already prices the spot.
- Earlier threads reached the same answer by other routes (all-pairs HO-1, market anchor and favourite-longshot, ChatGPT maps, SNN lag at one-minute resolution). This round adds that the sweep's own 55% did not survive the contract's definition of the window.
- The unfinished gap named in those threads is sub-minute: whether Kalshi's book lags the spot by seconds, and maker (zero-fee on these series) favourite buys. Both need the bot's recorded full-depth books, Nov 10 03:44 UTC onward (about 1.7 GB a day).
