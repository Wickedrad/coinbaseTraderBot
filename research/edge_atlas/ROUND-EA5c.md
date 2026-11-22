# Round EA-5c: daily brackets, and Steven's day-type rule (recorded days only)

Written Sun Nov 22 2026, about 9:30 AM EST / 14:30 UTC. Follows round 5b (ROUND-EA5b.md). Same rules: recorded days only, nothing waits for a future day, paper only, no order, no bot change, day-cluster intervals.

Two jobs this round. Steven tapped "Other contract families" (8:02 AM EST / 13:02 UTC), and two minutes later wrote: "if edge is found on some days/trades but not others investigate the difference and then see if they still perform on the same types of days or trades, if they do save them as only for that specific type" (8:04 AM EST / 13:04 UTC).

## Result

**Daily brackets: no edge.** 14 weather-high series, 4 weather-low series and Brent daily (19 series, 200 days each, May 6 to Nov 21, the last 12 hours of every market, 1-minute candles) lose 4 to 7 cents a contract on resting buys that fill. No row had a check-block lower bound above zero, and none was positive in all three blocks. Gross if every order filled is +0.2 to +7.8c on a handful of rows; the fills are adverse, as everywhere else.

**Day types: one typed rule found in about 40,000 typed tests, and it is thin.** It is kept, as Steven asked, only for its day type and flagged preliminary (see the registry in `typed_rules.md`):

> BTC and ETH 15-minute markets. A resting YES buy at the best bid, price 90 to 97 cents, placed in minutes 6 to 9, cancelled at minute 14, held to settlement, **only on a day after a day whose share of YES settlements was low** (at or below 47.5%, the bottom third of the build days).

| Block (days) | On that day type: net c per fill (day-cluster lower bound), fills | Same rule on the other days |
|---|---|---|
| Build, Apr 13 to Jul 24 (34 days of the type) | +1.72c (+0.06), 759 | not used |
| Check, Jul 25 to Sep 13 (15 days) | +3.19c (+0.40), 389 | +0.09c (-1.73), 882 |
| Clean, Sep 14 to Nov 4 (16 days) | +1.31c (-1.19), 358 | -1.60c (-3.61), 873 |

It passed every test written in advance (positive lower bound in build and check, positive in clean, better than the other days by at least a quarter of a cent in both later blocks). What keeps it from being called an edge: the clean interval crosses zero, the label-shift placebo finds one typed rule by chance in about 6% of runs of this data set (p = 0.06), it is one of about 40,000 typed tests across ten data sets, and it is worth well under $0.10 an hour (about 22 fills on one of these days at about 13 cents a fill, on roughly a third of days). Nothing near $2.60 an hour.

Read again, unchanged, on BTC and ETH separately and on the four other 15-minute families, it holds its sign in BTC and ETH and does not carry to the others (table below), so it stays saved for BTC and ETH 15-minute only.

No other data set produced a typed rule: the hourly ladders (2,268 tests), oil, silver and gas (4,032), FX (4,680), alt coins (4,032), Brent, platinum and yields (5,040), and the four daily groups (3,302 to 5,616 each) found none, and their placebos found none either.

## Does the typed rule travel? (read once, fixed in advance, on every other 15-minute data set)

Steven's rule has two halves: find the difference, then see whether it still performs on the same type. The second half, run on the rule exactly as found (YES buy at the best bid, 90 to 97 cents, from minute 6, after a low-YES-share day), reading it again on BTC and ETH separately and on the four other 15-minute families. No re-search, no tuning (run 45031919616, same cut point as BTC/ETH: previous-day YES share at or below the family's own bottom third of build days). Net cents per fill on the typed days, build | check | clean, with the other days of the same family for check | clean:

| Data set (typed days in build / check / clean) | Typed days | Other days, check / clean |
|---|---|---|
| BTC alone (34 / 15 / 16) | +1.17 / +3.65 / +0.15 (404, 183, 170 fills; check lower bound +1.04, clean -3.18) | -0.29 / -0.26 |
| ETH alone (34 / 15 / 16) | +2.33 / +2.78 / +2.35 (355, 206, 188 fills; build lower bound +0.28, check -0.89, clean -1.26) | +0.41 / -2.87 |
| Oil, silver, gas (9 / 4 / 4) | -0.38 / +0.76 / -1.86 (160, 89, 108 fills) | -5.90 / -0.49 |
| FX (7 / 6 / 6) | -1.47 / -1.90 / -5.94 (117, 225, 204 fills) | -1.25 / -4.85 |
| Alt coins NEAR, HYPE, ZEC (8 / 4 / 5) | +1.78 / -7.92 / +1.86 (280, 154, 154 fills) | -2.68 / -2.00 |
| Brent, platinum, yields (8 / 2 / 3) | +3.00 / -1.88 / -1.84 (42, 41, 55 fills) | -2.57 / +0.18 |

Read: it does not travel. In BTC and ETH separately the sign holds in all three blocks (the BTC clean block is only +0.15c, ETH carries it), but BTC's own interval is wide and ETH's check and clean intervals cross zero. In the four other families the typed days are negative in at least one of check and clean, beat the other days in one block and lose in the next, and have only 2 to 6 days of the type per block (these families have 25 to 30 days in all), so this read has little power: it cannot rule the rule out there, it just gives no sign of it. The rule stays saved for BTC and ETH 15-minute only.

## What differs between day types (the "investigate the difference" part)

The mean resting-buy rule (every rule pooled) by day type, net cents per fill, build | check | clean:

- **Weekends are worse, in all three blocks, in every family that trades them.** BTC and ETH 15-minute: -4.0 | -3.4 | -3.0 on weekends against -3.0 | -2.8 | -2.6 on weekdays. Oil, silver, gas: -4.8 | -3.4 | -3.9 against -2.8 | -2.9 | -2.8 (1,200 to 2,500 fills). FX: -7.5 | -5.8 | -6.3 against -4.3 | -3.1 | -3.1. Brent, platinum, yields: -13.6 | -7.8 | -7.3 against -4.6 | -3.8 | -3.6 (about 500 fills). Alt coins and the hourly ladders show no weekend gap. This is a type to avoid, not an edge: it only trims the loss.
- **The previous day's surprise, volume, spread and YES share do not separate the mean rule.** On BTC/ETH every level sits within about half a cent of -3c in every block; the same holds elsewhere. The one typed rule above is a pocket inside the 90 to 97 cent bucket, not a day type that lifts every rule.
- **Weather:** no weekday or previous-day type lifts the loss; the lows and Brent are worst (-5 to -7c).

## How it was read

- `python/subminute/daytypes.py` (tests in `tests/test_daytypes.py`, 47 subminute tests pass; stages `dtk15`, `dtread`, `famdaily` in heat-direction.yml). Trades are already typed by pockets.py (side, price bucket, placement minutes, coin). The new part types the DAYS, each from information known before the day opens: weekend or weekday; and the previous day's mean |settle - first-minutes mid| (surprise), contracts per window and YES spread (each against the mean of the 14 days before it, because volume and spread drift), and YES share. Cut points are the terciles of the build days only.
- Three blocks in time order, none used twice: build (first half of the days) scores, check (next quarter) judges, clean (last quarter) is read once. A typed rule needs a day-cluster lower bound above zero in build (300 fills) and check (150 fills), a positive mean in clean (100 fills), and to beat the same rule on the other days by 0.25c or more in both check and clean.
- Placebo: the same search on the day labels slid by a random number of days (200 slides): how many typed rules appear by chance, with the streaks and frequencies of the labels kept and the dates lost.
- One design fault was found and fixed after the first BTC/ETH read: volume and spread terciles cut on the build days left whole levels empty in later blocks (volume drifts), so those two labels now use the previous day against the mean of the 14 days before it. The BTC/ETH typed rule did not depend on those labels (its label, YES share, did not change); the placebo p moved from 0.035 to 0.06 with the fixed labels. Both are reported.
- Daily brackets: `kalshiHistory.ts --max-candle-min 720` keeps the last 12 hours of 1-minute candles of every settled market (Kalshi's candle API offers only 1, 60 and 1,440-minute bars), up to 1,500 markets a series; `fampockets.py --kind daily` reads them with placement minutes 1 to 120, 120 to 360, 360 to 600 and 600 to 700 and a cancel at minute 600 or 719. No maker fee on these series (not in the fee schedule's non-standard list). Candles kept on Drive raw/oracle-history/kalshi/<SERIES>, tables on Drive models/subminute/famdaily/<group> and models/subminute/daytypes/<group>.

## Daily brackets, by group (net c per fill, every rule of the group pooled, build | check | clean)

| Group | YES side | NO side | Rows with fills (at least 150 in check and clean) | Check lower bound above 0 |
|---|---|---|---|---|
| Highs: LAX, MIA, DEN, SFO, AUS | -3.2 / -3.7 / -5.1 | -4.4 / -5.7 / -4.5 | 12 of 60 | 0 |
| Highs: ATL, SEA, MIN, DAL, PHX | -3.2 / -4.9 / -4.2 | -4.4 / -5.1 / -6.5 | 16 of 68 | 0 |
| Highs: LV, DC, SATX, NOLA | -3.7 / -4.5 / -5.7 | -6.5 / -6.8 / -8.5 | 1 of 58 | 0 |
| Lows (NYC, CHI, AUS, ATL) and Brent daily | -4.6 / -5.2 / -5.7 | -5.8 / -7.2 / -4.9 | 3 of 72 | 0 |

Weather is thin: 1,500 to 4,000 fills a block per group, so intervals are wide (several cents), and a small edge could hide. Nothing in the point estimates points to one.

## What it means

- Same answer as rounds 2 to 5b: a resting buy gets filled mostly when the market is moving against it. Daily brackets are no exception, and they are thinner and worse.
- Steven's rule works as a filter: it turned up one pocket (the 90 to 97 cent YES buy after a down day) that held in three blocks, saved with its type, and showed that the loss is larger on weekends. It did not turn a loss into a gain anywhere else.
- Not run: bracket-sum arbitrage (hourly grids hold ladders only, stale-book risk from round 5a), oracle strips, a forecast-versus-quote read on weather (needs a forecast history), the 15-minute families' lag.

## Code and runs

Commits 3ba1cf58, 04cd5c50, 48e6dd53, 8695c034 on PR #365. Runs: 45026190707 (famdaily fetch, maps, day types; dtk15), 45030594167 (day types with the fixed labels on every kept data set), and 45031919616 (the transfer read of the one typed rule, commit 8695c034). Registry of saved typed rules: `typed_rules.md`.
