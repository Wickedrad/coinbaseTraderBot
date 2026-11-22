# Round EA-5b: do resting buys earn on Kalshi's other 15-minute families? (recorded days only)

Written Sun Nov 22 2026, about 6:15 AM EST / 11:15 UTC. Follows round 5a (ROUND-EA5.md). Same rules: recorded days only, nothing waits for a future day, paper only, no order, no bot change, day-cluster intervals. Steven's bar (1:35 AM EST / 06:35 UTC): $2.60 an hour counts as edge.

## Result

**No edge in any of the 14 other 15-minute families.** A resting buy at the best bid of its side, held to settlement, with no maker fee, loses about 3 cents a contract after fills on average in every family, the same size as on BTC and ETH. Of the 14 series, 0 had a rule with a positive lower bound on the build days that stayed positive on the check days (altcoins: 5 of 665 rules had a positive build bound, all five were negative on the check days, -3.6c on average). Across all rules and series, the day-cluster lower bound was above zero on the check block for only 2 of about 775 rows with enough fills (about 19 would be expected by chance at a one-sided 2.5%), and both were negative or flat on the clean block. The one pattern that repeats is the NO side doing better than the YES side on the alt coins (about -1c against about -4.5c), which is the same shape as the BTC hourly NO lead that turned out to be weather.

| Group (series) | Days / windows | Contracts a window | Check block net c per fill: YES / NO side, all rules | Clean block: YES / NO | Rules with check bound above 0 | Passes |
|---|---|---|---|---|---|---|
| WTI | 60 / 4,222 | 79,700 | -1.66 / -2.87 | -2.77 / -1.66 | 0 | 0 |
| Silver | 51 / 3,819 | 48,400 | -2.33 / -2.59 | -3.86 / -0.73 | 0 | 0 |
| Natural gas | 60 / 4,222 | 19,900 | -4.21 / -3.75 | -2.10 / -5.82 | 0 | 0 |
| EURUSD | 51 / 3,940 | 6,700 | -4.30 / -2.14 | -3.28 / -2.64 | 0 | 0 |
| USDJPY | 51 / 3,937 | 5,700 | -3.03 / -2.89 | -3.17 / -3.45 | 0 | 0 |
| GBPUSD | 51 / 3,940 | 5,600 | -3.56 / -2.99 | -1.18 / -5.09 | 0 | 0 |
| AUDUSD | 39 / 3,007 | 3,700 | -0.94 / -5.07 | -3.42 / -2.75 | 0 | 0 (1 row positive in all three blocks, check bound -5.0 to +6.8) |
| NEAR | 49 / 4,502 | 27,100 | -7.17 / +0.04 | -4.02 / -1.21 | 1 (NO 90-97c from minute 9: +2.3c, bound +0.07, build -2.3c, clean -1.4c) | 0 |
| HYPE | 49 / 4,502 | 34,600 | -4.44 / -1.35 | -3.15 / -2.23 | 0 | 0 |
| Zcash | 49 / 4,502 | 30,900 | -3.73 / -1.75 | -3.14 / -1.85 | 0 | 0 |
| Brent | 32 / 2,199 | 6,500 | -2.57 / -3.69 | -1.86 / -4.69 | 0 | 0 |
| Platinum | 51 / 3,792 | 6,800 | -5.05 / -3.07 | -5.37 / -1.95 | 0 | 0 |
| 30-year yield | 24 / 1,173 | 1,600 | -1.78 / -8.53 | -0.88 / -8.19 | 0 | 0 |
| 5-year yield | 24 / 1,178 | 1,100 | -2.39 / -5.91 | +1.53 / -8.38 | 0 | 0 |

Per group, pooling its series ("ALL" rows): mean over every rule of the check block, oil, silver, gas -2.95c; FX -2.92c; alt coins -2.91c; Brent, platinum, yields -3.99c. The block dates are in the table below. Net c is per contract filled, 72 rules (two sides, nine price buckets, four placement minute ranges) at cancel minute 14, read the conservative way (a fill needs the opposite quote to trade strictly through the order).

| Group | Build | Check | Clean |
|---|---|---|---|
| Oil, silver, gas | Sep 23 to Oct 22 | Oct 23 to Nov 6 | Nov 7 to Nov 21 |
| FX | Sep 23 to Oct 21 | Oct 22 to Nov 5 | Nov 6 to Nov 20 |
| Alt coins | Oct 5 to Oct 28 | Oct 29 to Nov 9 | Nov 10 to Nov 22 |
| Brent, platinum, yields | Sep 23 to Oct 24 | Oct 25 to Nov 7 | Nov 8 to Nov 21 |

## How it was read (python/subminute/fampockets.py, stages famcandles and famread)

- The survey (round 5b, run 45008474098) listed 16,775 Kalshi series, probed the hourly and daily finance-like ones and the 15-minute ones outside the crypto four, and kept those not in the fee schedule's non-standard list (no maker fee) with volume. DOGE is excluded by rule.
- famcandles pulled Kalshi's own public 1-minute candles for the newest settled markets of each series (up to 60 days, up to 4,500 markets a series; Brent came back with 32 days and the two yield series with 24) and kept them on Drive at raw/oracle-history/kalshi/KX<A>15M (4 groups, about 35 to 60 minutes each on separate runners). famread reads them back without fetching.
- The scoring is pockets.py's, unchanged: a resting buy at the best bid of its side, placed in minutes 1 to 12 at the first book that is two-sided and priced in the bucket, cancelled at minute 10 or 14, held to settlement, no maker fee, $10 stake, a fill read off the next candles. Three blocks in time order, none used for two jobs: build the first half of the days (rules scored here), check the next quarter (rules with a positive build bound judged here), clean the last quarter (read once). Intervals are day-cluster (z = 1.96).
- A pass needed the check lower bound above zero with at least 150 fills, and a positive point estimate in build and clean.
- The side flip is the placebo: the same price and minute on the other side (YES against NO) and the mean over every rule, all of which are blind to anything but price and minute.

## What it means

- Same answer as BTC, ETH, SOL, XRP and the hourly ladders (rounds 2 to 5a): a resting buy gets filled mostly when the market is moving against it, so the gross that would be earned if every order filled (2 to 9 cents on many rows) turns into about -3c on the orders that do fill. Fees are not the reason: this is the no-maker-fee case.
- The alt-coin NO side is the one regularity: -1.0c (check) and -1.8c (clean) against -5.1c and -3.4c for the YES side, and two NO rows (30 to 50c, from minute 3) positive in all three blocks of the pooled alt coins at +0.0 to +1.5c, with check intervals that reach 2 to 3.5 cents below zero. Not an edge. It is also the same direction as the BTC hourly NO lead, which was ten days of weather, so it could be the same shape and is worth one look on the alt coins' own longer history, not more.
- The candle reading is 1 to 2 cents harsher than the exact queue-aware replay of recorded books (round 2 on BTC and ETH: -1.7c to -2.4c against about -3c on candles). Even adding that back leaves every family at about -1c or worse.
- Not run: the daily weather brackets (about 40 hours a market, a different window design), the 15-minute families' lag against their own index (no sub-minute books are recorded for them, only candles), bracket arbitrage and the oracle strips.

## Code and runs

`python/subminute/fampockets.py` (tests in `python/subminute/tests/test_fampockets.py`, 41 subminute tests pass), stages `famcandles` (GitHub run 45010514806, commit 14161fb3) and `famread` (run 45015780192, commit c3ef7332 code, f7d91661 trigger) in `.github/workflows/heat-direction.yml`. Candles on Drive raw/oracle-history/kalshi/KX<A>15M for WTI, SILVER, NATGAS, EURUSD, USDJPY, GBPUSD, AUDUSD, NEAR, HYPE, ZEC, BRENT, PLATINUM, 30YRRATE, 5YRRATE. Tables on Drive models/subminute/fampockets/<group> (fampockets.json, the whole map per asset).
