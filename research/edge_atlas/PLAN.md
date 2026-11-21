# Edge atlas: find edge of any type on recorded history, judged on Kalshi's own prices (plan, Nov 21 2026 12:40 PM EST / 17:40 UTC)

Steven, Nov 21 2026 (12:06 and 12:09 PM EST / 17:06 and 17:09 UTC): use loops and sweeps on historical data to find edge of any type; start from the
literature (Scite) and use the perfect oracle; the weighted heat map may need to be repopulated entirely. There is no test on a future day: every sweep and
every hold-out uses days that are already recorded, held out by time inside the history. Nothing here waits for anything. Research only: no order, no bot
change, no heat-curve change.

## What counts as an edge
A rule that, on Kalshi's recorded 15-minute quotes and settlements, earns more than zero **net dollars per contract after the taker fee** (python/allpairs/fees.py,
a port of bot/fees.ts), with the day-cluster 95% lower bound above zero in a block that was not used to choose it, and a positive point estimate in every
earlier block. Coin direction on its own is not an edge: Kalshi's quote may already hold it (the literature and OR-H1 both say it can). Every number comes
with its placebo: the same calls with the side flipped and with a random side, and no-signal twins of the sweep.

## Data on hand (Drive, read only)
- Binance spot 1-minute bars BTC, ETH, SOL, XRP from 2020, and the exchange's daily files to Nov 20 2026.
- Kalshi 15-minute candles with real bid and ask, KX{BTC,ETH,SOL,XRP}15M, close days 2026-04-13 to 2026-11-04 (206 days), with the recorded settlement.
- The bot's own recorded days (md-DAY) for what Kalshi's archive does not reach: Nov 5 onward, with the book.
- OR-HM1 oracle heat levels (BTC, ETH, SOL, XRP, 2020 to 2025, horizons 1 to 60 minutes) and the OR-H1 result (0 setups survive on Kalshi prices, Aug to Nov 4).

## The blocks (all inside recorded history)
- Build: Apr 13 to Jul 31 2026 for anything priced on Kalshi; 2020 to 2024 for anything that needs only the coin.
- Check: Aug 1 to Oct 31 2026 (coin-only work: 2025).
- Clean: Nov 1 to Nov 19 2026 (the frozen direction rule was never fitted on it). Nothing is tuned on a block after it has been used to judge.

## Steps, each a stage on GitHub, aggregates only
1. **The direction rule on quotes** (stage dskalshi, python/dirsweep/kscore.py): the frozen rule 31574, its follow side, an unfiltered control and a random
   side, entered at the first minute with a two-sided book and held to settlement. The question the coin-direction score cannot answer.
2. **Spot against quote** (python/dirsweep/kfair.py): a digital-option fair value from spot, strike and trailing volatility, nothing fitted. (a) Does quote
   plus model beat the quote alone on log-loss on the later part? (b) Does buying the side with at least 3, 6 or 10 cents of model edge earn after fees, by
   minute range?
3. **Quote structure**: realized frequency against ask by minute and price bucket (favourite and longshot bias), spread and maker economics (the 15-minute
   crypto series pay no maker fee, fees.py), cross-coin lead-lag (BTC to ETH) against the quote.
4. **Oracle strips**: the hindsight best side and minute per window, then which causes separate it from chance: the TA-Lib vocabulary with parameters,
   order-flow and jump signals, BTC.D and USDT.D moves, quarter-hour seasonality, confluence pairs and triples, each with twins; nested walk-forward.
5. **Repopulate the weighted heat map**: whatever survives steps 1 to 4 becomes a new pack (schema oracle-heat-pack-1: how often times how big, plus the dip
   before) built only from the build block, scored on check and clean. A research output, not a bot change.

## Starting points from the literature (all verified in Scite; LITERATURE-EA.md)
Large BTC moves reverse more at 1 to 4 hours; intraday momentum and reversal change with jumps and liquidity; order-flow imbalance predicts jumps; BTC to ETH
lead-lag depends on the state and intraday seasonality is robust; hourly BTC to ETH is barely exploitable; Kalshi's 15-minute quotes sit close to realized
rates and a similar book showed a null against a simple signal, so the null is the prior and the quote is the benchmark.

## Reporting
Each step ends with one line: the net cents per contract after fees with its interval, on build, check and clean, next to the placebo. If a step finds
nothing it says so and the next step starts. No bar is moved after a result is read. A pass is a lead for Steven to decide on, not a trade.
