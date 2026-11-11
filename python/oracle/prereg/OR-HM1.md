# OR-HM1: heat strips and confluence matrix on coin price (design, written before any result)

Written 2026-11-11 ~04:00 UTC (Nov 10 11:00 PM EST). Thread "Find $5 trade setups with a perfect-hindsight oracle".
Steven's spec (Nov 11 03:06 / 03:22 UTC): a weighted linear heat map per TA reading (how often x how big a move within
5/15/30/60 minutes), the full TA-Lib vocabulary with candlestick patterns and a few parameter settings, a pairwise (and
triple) matrix with BTC.D and USDT.D moves as parameters. Exits he wants later: sell at first profit after fees, cut
losers early, settle only in profit. NEVER DOGE. Never compared to paper. Nothing at or after DEV_END (2026-08-01) is
loaded: HO-1 (Aug 1 - Nov 4) and the lockbox stay closed. This is a MAP, not a validated rule; hot spots go on to be
scored on real Kalshi prices and fees under the edge-iteration pipeline's bars.

## Data
Binance spot 1-minute bars (raw/perp-ta-history/<A>/binance-1m/<A>/1m.csv on Drive) for BTC, ETH, SOL, XRP from
2020-01-01 (SOL from its listing) to 2026-07-31 23:00 UTC. BTC.D and USDT.D: TradingView daily closes in
research/btcd_fractal/data (a day's change is known only after that UTC day closes). Gaps are forward-filled for the
indicators; a minute whose own bar or any of the next 60 is a gap is never an event.

## Readings (python/oracle/heat.py READINGS; computed on 1m, 5m, 15m and 1h bars, known at the bar's close)
About 44 indicator readings per timeframe with a few parameter settings (RSI 2/7/14/21, Stochastic and its cross,
StochRSI, Williams %R, CCI, MFI, ADX x DI, Aroon, MACD 12/26/9 and 5/35/5, ROC z, CMO, Ultimate, BOP, TRIX, Bollinger
20/2 and 20/2.5 and width, close vs EMA 9/21/50/200, EMA 9/21 and 50/200 crosses, SAR, KAMA, T3, Donchian 20, Ichimoku
cloud, rolling-VWAP distance, NATR regime, volume surge, taker-buy share, OBV divergence, ADOSC, regression slope,
z-score, HT trend mode, runs of up/down bars, bar size in ATR) plus all 61 TA-Lib candlestick patterns (bull / bear).
Context: BTC.D and USDT.D previous-day change (down / flat / up at 0.5%) and 5-day change, and the UTC 4-hour block.
Each reading has a few levels. An EVENT is the first bar close at which a level holds (a pattern: every bar it fires).

## What is measured per (coin, reading level, horizon h in 5/15/30/60)
From the entry close of each event: the move to h (bps), the best move up and down within h, and Steven's bracket:
did price touch +X before -X within h (X = 10, 25, 50 bps; same-minute ties count as losses). Against the base rate =
every valid minute of the same split. Direction = the sign of the excess move. Reported: events, events/day, days,
excess move (bps), day-clustered t, up share, best move toward / against, bracket win rates vs base.

HEAT (Steven's "how often x how big"): events per day x excess move in bps (bps of drift per day). Also bracket heat:
events/day x 2 x X x (win rate - base win rate). CHANCE HEAT: the same events shifted by a whole random number of days
(>= 30, 8 seeds, circular inside the split): the heat a reading gets by chance. The shift keeps time of day, so a
purely time-of-day effect shows chance heat close to its heat (by design: it is a control for the hour). Shown beside every heat.

## Matrix
Pairs: per coin, the 120 single levels with the largest |t| on split A (any horizon), each paired with the others and
with every context level (BTC.D, USDT.D, hour block). A pair's event = a minute where one level's event happens while
the other level holds. Triples: the 40 hottest pairs on A x the same candidate list.

## Splits and the check (no held-out data)
Build A = 2020-01-01 .. 2025-01-01, check B = 2025-01-01 .. 2026-08-01 (the perp SPLITS). A hot spot is a level with
|t_A| >= 3 and at least 30 events on A. On B: does the excess keep its sign, and how big is the heat. Reported: the
share of A hot spots that replicate on B (same sign, t_B >= 2 in A's direction) vs the share among the chance (shifted)
events, the rank correlation of A and B heat, and BHY at q 0.10 over the A hot spots' one-sided B p-values. The league
table ranks by B heat among those that replicate. Nothing is chosen on B beyond this table.

## Next (not this run)
Hot spots that replicate are scored on real Kalshi 15-minute and hourly prices with Steven's exits (sell at the first
bid that clears fees, the OR-H3 loser cut, settle only in profit) on discovery data, then HO-1 + placebo once under the
pipeline doc's bars. Known limits: overlapping minutes are clustered by day only; daily dominance is coarse (Binance has
no intraday BTC.D); the candlestick definitions are TA-Lib's.
