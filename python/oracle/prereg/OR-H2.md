# OR-H2: reversal oracle on spot TA, traded on perpetuals (pre-registration, amends OR-H1 for the perp book)

Steven, 2026-11-06 13:38 UTC (8:38 AM EST): every red and green candle is profit; solve (1) accurately time a reversal on the
shortest reliable span, (2) size the move to net $5 after fees, (3) exit and repeat. First find TA (RSI, Bollinger, ...) that
detects a momentary change of direction, on spot data, to trade the perpetuals. Price Prediction contracts use bigger swings or
full reversals. Target $100 per 24 h, not necessarily $5 per trade.
Written 2026-11-06 14:00 UTC, before any H2 label or result exists. OR-H1's selection / HO-1 / registry rules apply unchanged
(discovery A/B split, BHY q 0.10, one HO-1 opening per contract type per frozen file, matched placebo, no DOGE, no lockbox).
Registry families: oracle-perp-rev-v1, oracle-pp-rev-v1.

## Hypothesis (one, falsifiable)
There is a spot TA state, or a conjunction of at most three, that precedes a reversal of at least M bps within h minutes
(before an adverse move of S bps) more often than matched random decisions, with a gross edge that exceeds round-trip costs,
for some (M, h) on BTC, ETH, SOL or XRP. Falsified if no frozen setup passes HO-1 for any cell.

## Reversal labels (triple barrier, per decision, per side)
Decision every 5-minute close (as OR-H1). Long: take-profit at +M bps net before a stop at -S bps, within h minutes. Short mirrored.
Ladder M in {30, 60, 100, 170} net bps, S = M/2, h in {5, 15, 60} minutes (5 min only for M <= 60), shortest reliable span first.
Exit = resting maker take-profit (trade-through 1 bp), stop at the stop price (or a worse open), else taker at the horizon.
Costs as OR-H1 (taker 12 + half spread in, maker 5 out, funding offsets). hit = take-profit filled. trade = net bps.
Sizing (the "how big" answer, recorded not selected on): notional N(M) = min($300, $5 / (M/1e4)); net $ per trade = N x net bps.
At the $300 cap (PERP_MAX_LEVERAGE 3 x $100) a $5 net trade needs M >= 167 bps; smaller swings pay proportionally less
($1.20 at 40 bps). The study reports $/trade and trades/day per cell so the $100/day target can be read off.

## Features (spot only, closed bars, strictly before the decision)
OR-H1's list (buildPrims + analyzer / book rules / confluences / TA-Lib patterns and indicators; no forecast models) plus
reversal-specific states built from 1m / 5m / 15m spot bars: RSI(14) beyond 70/30 and 80/20, Bollinger %B outside 0/1 and a
close back inside the band, Stochastic 14/3/3 crossing out of 80/20, Williams %R, CCI +-100/200, distance from the 12/48-bar high
or low in ATR units, bars since that extreme, candle reversal patterns, volume / taker-flow spike at the extreme.
Excluded: anything computed from bars after the decision; setup_model / rule_book scores; MODEL_SKILL; forecast heads.

## Mining, confirmation, HO-1
Unchanged from OR-H1 (matched strata hour x RV tercile, residual-trick uplift on split A, exact trade sim and bootstrap on
split B, BHY q 0.10 over every confirmed setup in the contract type, freeze, one HO-1 opening). The ledger is per contract type,
so perp-rev uses its own family and contract-type key `perp-rev` (the OR-H1 perp opening stays unopened).
Price Prediction swings (hourly contracts, bigger moves / full reversals): same labels with the contract's net $5 target; see OR-H1.

## Reported beside every cell
Gross edge in bps over matched random, precision vs base rate, trades/day, $/trade at the sized notional, projected $/day,
features one bar early (lookahead check), +1 minute latency, +5 bps cost stress.
