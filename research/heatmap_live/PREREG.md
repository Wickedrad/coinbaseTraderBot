# Heat maps vs the bot on live Kalshi: rules fixed before any result is read

Written Wed Nov 11, 2026, 11:10 AM EST (16:10 UTC), before the capture started. Thread "Test weighted heat maps on live Kalshi". Research only: nothing here changes the bot.

## Question

Steven, Nov 11, 9:48 AM EST (14:48 UTC): do the weighted heat maps pick better trades than the bot's current paper strategy, on real live Kalshi data?

"The heat maps" are ChatGPT's frozen Atlas tables (GitHub runs 42643723640 and 42667008829): per coin, a 15-minute and a 60-minute up/down call from 28 TA readings and their 378 pairs. Nothing is refitted or tuned during the test.

## What is captured (GitHub runner, public data only)

- Coins: BTC, ETH, SOL, XRP. No DOGE.
- Calls: every closed Binance minute (the source the tables were built on), warmed with 100 days of minutes so all 28 readings exist. Daily dominance readings come from TradingView; if that source fails the two readings are left out and the call records how many readings it used.
- Books: the public Kalshi order book, about every 10 seconds, for each coin's current 15-minute contract (KX{coin}15M) and the 4 hourly strikes nearest the money (KX{coin}D). A strike once watched is kept until it closes.
- Code: `captureCli.ts`. Segments of up to 3 hours end at 14:25 UTC and every 3 hours from there, so data is in before the 9:30 AM EST reads.

## Entries (derived from the captured calls and books by the scorer)

All entries are $10 at the ask of the called side, from the first book seen after the call is published (within 20 seconds). Rules shared by every contender, copied from the bot's own entry rules:

- 15-minute contract: 840 to 300 seconds before close. Hourly contract: 3300 to 600 seconds before close.
- The side bought must cost 10c to 90c and the book must be two-sided.
- A call with no contract or book that fits counts as "no entry" and is reported, never dropped silently.

Contenders:

1. **15-minute map on 15-minute contracts.** UP buys YES, DOWN buys NO.
2. **1-hour map on hourly contracts.** The strike is the watched one whose YES mid is nearest 50c at that moment. UP buys YES, DOWN buys NO.
3. **15-minute map with the 1-hour map as context** (Steven, Nov 11, 10:29 AM EST): contender 1 split by whether the 1-hour call agrees with the 15-minute call.
4. **The bot.** Each opening fill of the paper bot on these series (a fill that increases the position), side as filled, at the fill's own time. Scored two ways: re-priced at the ask like the others ($10), and at the bot's own fill price and size.

Primary count: one entry per contract per contender, the first that qualifies. Secondary count: every qualifying minute (heat maps) or every opening fill (bot).

## Score: the one test (project standard since Nov 11, 8:17 AM EST)

- Contracts bought: C = floor($10 / ask), at least 1.
- Level: the lowest price on the contract's grid at which selling C contracts nets at least the entry cost plus both taker fees plus 1c per contract. Fees are Kalshi's formula as in `bot/fees.ts` (0.07 x C x P x (1 - P), rounded up to the cent per order).
- Profit window: the called side's best bid stays at or above the level for at least 60 seconds of consecutive book samples (no gap over 25 seconds), starting after entry and ending before the last 90 seconds of a 15-minute contract or the last 6 minutes of an hourly one.
- Window rate = share of entries with a profit window. Entries whose book record has a hole over 60 seconds before the deadline are "incomplete" and left out for every contender alike.

Each contender is compared with controls on its own contracts and minutes:

- **Random side, same minute and contract** (the plan's "random entries in the same contracts and hours"): the average of the called side and the opposite side. This is the gap that decides "direction found".
- **The coin's usual side** (the map's constant prior for that coin and horizon), same minute: shows whether the map adds anything to always betting the usual way. A market that drifts one way flatters any mostly-one-way caller; this control removes that.
- **Same side, random minute** in the entry window of the same contract: shows whether the timing of the entry matters (used for the bot, whose entries are not on a fixed minute).

Chance wobble: bootstrap over time slots (all four coins in one 15-minute slot, or one hour, move together, so the slot is the unit). A contender "finds direction" when its gap over random side is at least twice its own standard error. The heat maps "pick better than the bot" when their gap is larger than the bot's by at least twice the standard error of the difference. Smaller differences are reported as "no clear difference".

Reported for information, never judged: time to the window, its length, the worst dip before it, results with the bid size at least C, results by coin, agreement of sides on contracts both entered, and each side's result at the bot's real fill prices.

## When results are read (Steven, Nov 11, 10:22 AM EST / 15:22 UTC)

- First look: Thu Nov 12, 9:30 AM EST (14:30 UTC), on everything captured since the start. An early look on under one day of data.
- The call: Thu Nov 19, 9:30 AM EST (14:30 UTC), on the 7 full days from the first look.
- No sealed weeks. No other scored read in between; health counts (how many calls and books were captured) are checked daily.
- The bot's entries come from its daily log on Google Drive, which arrives the morning after each day ends, so the bot side of each read runs through the last finished UTC day.

## Limits stated up front

- The bot is a two-sided maker: it rests buy orders on both sides and its side is whichever one the market fills. Its entries are therefore not "calls" in the same sense, and its real fill prices are better than the ask. Both views are shown.
- The maps were fitted on all history through Oct 13, 2026, so only days after their Nov 9 freeze are unseen. Every captured day is.
- ChatGPT's own two short live trials (Nov 9-10) found no edge over its controls, and the maps never gave any side more than 40%.
- Our own heat map (the oracle thread's league, due Fri Nov 13) joins as another contender from the day its hot spots are frozen, under the same rules.
- Public repo: only totals are published from the bot's log. No log rows leave the private job.
