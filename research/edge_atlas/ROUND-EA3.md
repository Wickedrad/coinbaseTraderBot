# Round EA-3: more pockets like the NO-favourite resting buy (recorded days only)

Written Sun Nov 22 2026, 1:59 AM EST / 06:59 UTC. Steven (Nov 22, 1:35 AM EST / 06:35 UTC): $2.60 an hour counts as edge, "look for more like this". The coordinator's note: test every candidate on held-out recorded days first, and the NO-favourite pocket itself needs a larger recorded sample. Same rules as before: recorded days only, nothing waits for a future day, paper only, no order, no bot change.

## What was run

`python/subminute/pockets.py`, stage `dspocket` on GitHub (about 3 minutes, aggregates only). A resting buy at the bid of its side, no maker fee, held to settlement, searched over:

- side (YES or NO), price bucket of the order (10c wide, 10-20c up to 90-97c), placement range in the window (minutes 1-3, 3-6, 6-9, 9-12), cancel minute (10 or 14), coin (BTC, ETH, both), six-hour block of the UTC day (or all of it): 2,160 cells, 1,687 with at least 300 fills in the build block.
- Three recorded blocks, none used twice: build = Kalshi's own 15-minute candles Apr 13 to Jul 31 (110 days, BTC and ETH, 40,000 windows); check = the same candles Aug 1 to Oct 31 (92 days); clean = the bot's own full-depth recordings Nov 11 to 20 (10 days, BTC, ETH, SOL and XRP; SOL and XRP were never in the build or the check), replayed with the queue-aware simulation of `maker.py` under both queue models.
- A fill is read off the candles after the order: 'thru' = the lowest YES ask (for a YES buy) went strictly under our price, the conservative reading; 'touch' = it reached our price. Dollars an hour = net dollars at a $10 stake over the 24 hours of each recorded day.

## Result 1: the whole map is negative, and the Nov 11-16 pocket is not in the earlier 202 days

Every side x bucket x placement cell at the longest rest (72 cells, both coins, all hours), 'thru' fills, net cents per filled contract:

- Build days: 67 of 72 cells are negative, the average is about -3c. Check days: 66 of 72 are negative. The map's typical cell loses 2 to 5 cents per fill: a resting buy that gets filled is mostly one the market then moved through.
- Before fill selection, the favourites do carry a small, steady premium. The same orders if every one had filled earn, per contract, for NO at 50-80c: +0.5c to +3.4c in both blocks, 16 cells of 16 positive on build and on check (for example NO 60-70c at minute 1: +2.25c on 110 build days, +0.98c on 92 check days; minute 3: +2.13c and +1.63c). YES at 70-90c is the same sign (+0.4c to +2.8c, 8 of 8 positive on both). Nov 11-16 (+5.1c) was the high end of that range, Nov 17-20 (+1.1c) the low end.
- After fill selection the NO-favourite pocket is not positive on the larger sample: NO 60-70c placed at minute 1: build -1.71c, check -2.18c (95% -3.90 to -0.45c, 4,617 fills); minute 3: -2.29c and -2.29c (-4.13 to -0.45c). The exact replay on Nov 17-20 gave -0.5c to +0.3c per fill. Three measurements, none above zero.

So the premium the pocket was drawing on is real (about 1 to 2.5 cents a contract on favourites), and the maker's adverse selection takes about as much back: 1c in the exact replay, about 3c in the candle reading, which is the harsher of the two because it only fills an order when the price goes through it.

## Result 2: what the search keeps

Of the 1,687 cells with fills, 6 had a build-day lower bound above zero (the 95% interval of net per fill on the 110 days). All six are buys of YES at 90-97c placed late in the window (from minute 6) and mostly in the 06-12 UTC block. Their check days (net cents per fill, 'thru', 95% interval, dollars an hour at $10):

| Cell | Build | Check | Clean replay, BTC+ETH (opt / pess) | Clean replay, SOL+XRP (opt / pess) |
|---|---|---|---|---|
| ALL, 06-12 UTC, min 6-9, cancel 10 | +2.65c | +1.74c (-0.13 to +3.60), $0.042/h | +0.33c / +0.14c (98 fills) | +0.11c / -0.08c |
| ALL, 06-12 UTC, min 6-9, cancel 14 | +2.65c | +1.59c (-0.32 to +3.50), $0.040/h | +0.33c / +0.14c | +0.30c / +0.21c |
| ALL, 06-12 UTC, min 9-12, cancel 10 | +2.42c | +0.89c (-1.40 to +3.18), $0.015/h | +2.09c / +1.69c (74 / 69 fills, -3.9 to +8.0) | +0.53c / -0.04c |
| ETH, 06-12 UTC, min 9-12, cancel 14 | +2.99c | +0.24c (-2.43 to +2.91), $0.004/h | -0.20c / -0.26c | not run |
| ALL, 06-12 UTC, min 9-12, cancel 14 | +2.17c | -0.18c (-2.11 to +1.76) | not run (check below zero) | |
| ETH, all hours, min 9-12, cancel 10 | +2.24c | -0.63c (-2.55 to +1.30) | not run | |

- Four of the six were above zero on the check days; none has a check-day interval clear of zero. The mean of the six on the check days is +0.6c, against -2.7c for all cells. On the clean days every estimate is between -0.3c and +2.1c with intervals of about plus or minus 6c (under 100 fills a cell), and the two coins never seen in the build (SOL, XRP) are +0.1c to +0.5c with the first-in-line queue and -0.1c to +0.2c with the whole queue ahead.
- The same family shows without the hour slicing in the map above: YES 90-97c placed from minute 3: build +0.51c, check +1.75c (-0.44 to +3.94, 716 fills, $0.059/h); from minute 6: +0.33c and +0.20c ($0.022/h); NO 90-97c from minute 6: +0.25c and +0.31c ($0.028/h). These three are the only cells of the 72 that are above zero on both blocks, and each has an interval across zero.
- Hours-of-day slicing is the weakest part: of 2,160 cells, a handful clearing a 95% bar in the build block is about what noise gives, and the six that did are one family (the same orders under different cancel times and coin slices), not six independent pockets.

## Dollars an hour: nothing close to $2.60

- Best cell on the check days: $0.04 an hour. The three map cells that are above zero on both blocks add up to about $0.11 an hour. On the clean replay: $0.00 to $0.07 an hour per cell.
- Ceiling: 4 coins x 4 windows an hour = 16 windows an hour. At a $10 stake a fill is about 11 to 15 contracts, so $2.60 an hour needs about +1.1c net on every one of those 16 windows (or +0.55c at a $20 stake). The premium on favourites is 1 to 2.5c before fill selection; resting buys give most of it back. The 90-97c family clears the +1.1c bar on the check days (+1.7c), but it only places an order in a few windows an hour.

## Verdict for round 3

No pocket of resting buys in this family gets near $2.60 an hour on held-out recorded days. The NO-favourite pocket of Nov 11-16 does not survive the 202 earlier days (net -2.2c with candle fills, -0.5c to +0.3c with the exact replay). What the data does show is small and consistent: favourites at the bid carry about +1 to +2.5c a contract before fill selection, and the cleanest net survivor is buying YES (or NO) at 90-97c from minute 3 to 9, worth about +0.2c to +1.7c per fill and about $0.02 to $0.06 an hour, with every interval across zero. That is the same premium round 1 found as a taker (YES 90-98c, minutes 5-9, +0.9c, about $4 a day).

## Caveats

- The candle fill reading and the exact replay bracket the truth; neither observes our own queue position. The clean replay has under 100 fills a cell, so its intervals are wide (plus or minus 6c).
- Best-of-1,687 cells: a pocket that clears the build bar has to be judged on days it never saw, as done here, and still not trusted at an interval across zero.
- Candles come in two tiers (before and after the API's historical cutoff, early September); about 4% of historical-tier minutes are crossed quotes and are dropped as no book.
- BTC and ETH only on the long history (no SOL or XRP candles on Drive); SOL and XRP are covered only by the 10 full-depth days.
