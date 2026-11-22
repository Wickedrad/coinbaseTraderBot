# Round EA-4: SOL and XRP on their own, and the hourly ladders (recorded days only)

Written Sun Nov 22 2026, 3:45 AM EST / 08:45 UTC. Order from the coordinator (Nov 22, 1:59 AM EST / 06:59 UTC): SOL and XRP and the hourly series through the 1-second grids first, then oracle strips, other contract families last. Same rules as before: recorded days only, nothing waits for a future day, paper only, no order, no bot change, day-cluster intervals, build days pick and check days judge. Steven's bar (1:35 AM EST / 06:35 UTC): $2.60 an hour counts as edge.

## Result

**No edge after fees in any of it.** One lead looked real for about an hour (BTC hourly ladder, resting NO buys) and died on 202 days of Kalshi's own candles. Nothing here reaches $2.60 an hour; the best candle cell is $0.04 to $0.06 an hour on its build days and negative on its check days.

| Question | Answer |
|---|---|
| 4a. Is the 15-minute book late by seconds, coin by coin (Nov 11-20, 1-second grids)? | No. Information R2 at most 0.11% for every coin (median about 0). Sold-after-H follow/flip cells: 0 positive of about 2,070 per coin (follow -3.3 to -3.8c). Held to settlement follow -0.6 to -2.1c. Best build cell judged on the check days: BTC +1.49c (-0.07 to +3.05), ETH -1.28, SOL -2.54, XRP -4.75 |
| 4a. Do resting buys earn per coin (360 rules, no selection, opt / pess queue)? | BTC +0.09 / -0.97c, ETH -1.09 / -1.70, SOL -1.35 / -1.94, XRP -0.28 / -1.02 per fill. Best build rule on check: BTC +2.35c (-5.4 to +10.1), ETH -4.28, SOL -3.92, XRP -0.82 |
| 4a. Does a pick on three coins travel to the fourth (all 210 ways of also holding out 4 of the 10 days)? | No: -1.3 to -2.4c (opt), -1.3 to -3.1c (pess), below the average rule in 7 of 8 cases. BTC+ETH against SOL+XRP on the same days looks like +1.4c / +3.4c and goes to -0.6c once days are held out: shared day weather, not a market effect |
| 4b. Are the hourly ladders recorded? | Yes, with books and trades (Nov 18): KXBTCD 218 markets, 57.0M deltas, 486k trades; KXETHD 180 / 14.9M / 29k; KXSOLD 180 / 10.1M / 10k; KXXRPD 128 / 2.0M / 3.4k; range brackets KXBTC 221 (33.8k trades), KXETH 190, KXXRP 125. A market lives 60 minutes (median). Maker fee 0 on these series. Reduced to 1-second grids for all ten recorded days (about 13 minutes a day, 11 MB a day) |
| 4b. Is the hourly book late by seconds? | No. Information R2 median 0.04% (ETH) to 0.13% (BTC), best 0.27% to 0.46%. Sold-after-H: 0 positive cells in all four coins (follow -3.5 to -4.7c). Held to settlement, follow -0.4c BTC, -0.7c ETH, +0.2c SOL, +2.4c XRP (544 thin XRP cells, none passes the build floor so none is judged; the XRP book has about 93k two-sided seconds). Best build cells on the check days: BTC +13.0c becomes -3.1c (-10.9 to +4.7), ETH +7.2c becomes -1.4c, SOL +3.1c becomes +4.1c (-5.4 to +13.7) |
| 4b. Do hourly resting buys earn on the ten full-depth days? | BTC yes at first sight, others no (below) |
| 4b. Do they keep earning on Kalshi's own hourly candles, Apr 13 to Nov 6 (202 days, BTC and ETH, about 19,300 nearest-strike markets each)? | **No.** 1,860 cells with fills, 1 with a positive build lower bound, 0 that survive the check days; check mean over all cells -2.31c |

## The BTC lead that did not hold

On the ten full-depth days (build Nov 11-16, check Nov 17-20), BTC hourly, resting NO buy:

- Best on build (NO 70-80c, placed minutes 30-50, cancelled at minute 55, index guard, first in queue): build +4.85c, check **+6.83c** per fill (day interval +3.5 to +10.1 at z = 1.96, about +1.6 to +12 with the t value for 4 days), 189 fills, 4 of 4 days positive, +6.42c under the stress fee. Under the pessimistic queue the best build rule (NO 80-90c, cancel minute 40) read +2.25c (-3.3 to +7.8), 2 of 4 days positive. ETH -5.3 / -6.0c and SOL -5.4 / -5.7c on the same rules; XRP no rule with fills.
- Round 2's test on the same coin, every way of holding out 4 of the 10 days (210 splits): the picked rule on the held-out days reads **+0.85c** (opt, 60% of splits positive, all rules +0.60c) and -0.45c (pess, 50%, all rules -0.92c). ETH -2.3c (16% positive), SOL -4.2c (20%). A pick made on six days barely beats the average rule on the other four. The pick made on ETH and SOL and read on BTC (leave out BTC) reads +2.49c opt / +1.91c pess (82% / 72% of splits positive), leave-out-ETH -2.0 / -0.8, leave-out-SOL -9.0 / -7.1.
- Without any selection, NO rules beat YES rules in every coin by 5 to 7c on those ten days: BTC NO +3.20c / YES -2.03c (opt), +1.53c / -3.62c (pess); ETH -0.12 / -5.09; SOL -4.56 / -11.58. The most picked BTC rule by day, Nov 11-20, c per fill: +10.4, +14.1, +10.2, -1.5, +1.0, -3.2, +1.8, +8.5, +7.6, +8.9 (about 46 fills a day at an average price of 0.72, so 13 contracts a fill at a $10 stake: about $0.74 a fill and about $1.4 an hour in-sample for that picked rule; the average of all NO rules, +3.2c opt / +1.5c pess, is about $0.8 / $0.4 an hour).

A side gap that big in every coin, on ten days that share one market, is what a drifting market looks like. The candles say whether it was drift.

## The 202 days of candles (python/subminute/hrpockets.py, stage hrpocket)

Kalshi's own 1-minute YES bid/ask candles of the hourly ladders (Drive raw/oracle-history/kalshi/KXBTCD and KXETHD, close days Apr 13 to Nov 6; about 94 markets a day per coin, the strikes nearest the money; 5,047 BTC and 6,132 ETH windows carry crossed quotes from the historical tier, which are read as no quote). Pockets.py's scoring pointed at 60-minute windows: a resting buy at the best bid of its side, fee 0, held to settlement, fill read off the candles after the order ('thru', the conservative reading). 1,860 cells (side, price bucket, placement minutes 1-10 / 10-30 / 30-50, cancel minute 40 / 55 / 59, coin, six-hour block). Build Apr 13 to Jul 31 (110 days), check Aug 1 to Oct 31 (92 days).

- The map (all coins, all hours, longest rest, 54 cells of side x price bucket x placement): all 54 have a negative check mean; the mean over all 1,860 cells with check fills is -2.31c per fill. NO 50-90c placed from minute 30: check -3.24, -2.34, -1.55, -1.72, -0.94c (mean -1.96c); YES 50-90c: -2.71, -1.94, -1.76, -0.61, -0.17c (mean -1.44c). **There is no NO-over-YES gap over 202 days**: the 5 to 7c gap of the ten recorded days was weather.
- The gross premium before fill selection exists (check, orders if all had filled: NO 70-80c +1.74c, NO 80-90c +1.55c, YES 80-90c +2.66c) and adverse selection takes it back, the same shape as the 15-minute series.
- The only cell with a positive build lower bound: YES 90-97c placed minutes 30-50, 06-12 UTC, cancel minute 40, both coins: build +2.95c (+0.69 to +5.21, 358 fills), check **-1.42c** (-4.79 to +1.94, 424 fills), $0.042 an hour on build and -$0.028 an hour on check. No survivors, so the queue-aware replay on the full-depth days did not run.
- The candle fill reading ('thru') was 1 to 2c harsher than the exact replay in round 3 (NO favourite 60-70c: -2.2c on candles, -0.5 to +0.3c on the replay). Giving every cell that much back leaves the hourly NO 70-90c cells at about zero, not at +2.60 an hour.

## What it means

- No lag at second resolution in any coin or series; no resting-buy pocket near $2.60 an hour in the 15-minute or hourly crypto series, by coin or pooled, on held-out days, coins or blocks.
- Two things in this round looked positive and both were the same ten days: the same-days pair transfer of 4a and the BTC hourly NO buy of 4b. Both vanish when days are held out (4a) or when 202 more days are read (4b). Ten recorded days of full books are too few to pick a rule on; the candle history is the one place with enough days.
- Open on recorded data: the oracle strips on Kalshi prices (plan step 4), static arbitrage inside one ladder or bracket set in the recorded books (a higher strike bid above a lower strike ask; bracket sums), and series other than crypto (need candles on Drive).

Code: `python/subminute/coins.py` (coin-by-coin lag and maker, leave-one-coin-out, within-coin hold-out, structure by side and bucket), `inventory.py`, `hourly.py`, `hrpockets.py`, `grid.py --hourly`; stages `dsmdcoin`, `dsmdinv`, `hrgrid`, `hrcoin`, `hrpocket`. Tables on Drive models/subminute/{coins,hourly,hrpockets,hgrids}. GitHub runs 44997236004 (coins), 44999675104 (hourly grids), 45002488883 (hourly coin by coin), 45003272173 (hourly candles).
