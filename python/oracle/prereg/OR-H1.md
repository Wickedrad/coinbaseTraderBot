# OR-H1: perfect-hindsight $5 oracle and the setups that precede it (pre-registration)

Thread "Find $5 trade setups with a perfect-hindsight oracle" (Steven, 2026-11-06 01:55 UTC / Nov 5 8:55 PM EST).
Written 2026-11-06 03:20 UTC (Nov 5 10:20 PM EST), before any label, feature or result of this study existed.
Registry thread `oracle-setups`, families `oracle-perp-v1`, `oracle-pp15-v1`, `oracle-pp60-v1`, `oracle-tennis-v1`.

## Hypothesis (one, falsifiable)
For at least one contract type, there is a setup (a conjunction of at most three pre-entry feature states: TA-Lib
indicators, the bot's analyzer rules / book rules / confluences, contract state) whose entries
1. reach +$5 net of fees within the horizon more often than matched random entries (hit-rate uplift > 0), AND
2. make money as a real trade (take-profit at +$5 net, otherwise the pre-registered exit below, after fees and losers),
   more than matched random entries do,
and this survives a single HO-1 scoring on Aug 1 - Nov 4 2026 against a matched random-entry placebo.
Falsified for a contract type if no frozen setup of that type passes HO-1 (rules below).

## Sizes ($5 per trade at the bot's default size)
| contract type | size | +$5 net means |
|---|---|---|
| Perpetual | $300 notional (PERP_PAPER_BALANCE_USD 100 x PERP_MAX_LEVERAGE 3) | 166.7 bps net |
| Price Prediction | $20 stake (ORDER_USD_MAX), C = min(floor(20/ask), 250) | ~+25% net |
| Tennis | $10 order (TENNIS_ORDER_FRAC 0.05 x $200), C = min(floor(10/ask), 100) | ~+50% net |
Sensitivity only (never selected on): perp $150 (SETUP_MAX_ASSET_LEVERAGE 1.5) and $1,000; PP $10; tennis $20.
Every row stores the hindsight best move (perp: net bps; Kalshi: best net $ at the primary size) so other sizes can be
re-thresholded without a re-run.

## Data (reused, nothing rebuilt)
- Perpetual: Drive derived/perp-ta/grids/<A>.bin (research/perpTaSweep.ts readGrid; Binance spot 1m for TA, Binance
  USD-M 1m for fills, Kalshi funding model). BTC/ETH from 2020-01-01, XRP 2020-01-07, SOL 2020-09-15, to 2026-11-04 23:59 UTC.
- Price Prediction 15-minute: Drive raw/kalshi-history/kalshi/KX<A>15M (real 1-minute YES bid/ask candles), Apr 13 -
  Nov 4 2026, loaded with python/allpairs/data.py load_kalshi (minute 0 dropped, two-sided books only, legacy cents repaired).
- Price Prediction hourly (the 1 h horizon): KX{BTC,ETH,SOL}D settled markets backfilled from Kalshi's public API on a
  runner, Apr 13 - Nov 4 2026, the 4 strikes nearest spot at the window's open (the live catalog rule). No XRP hourly series exists.
- Tennis: Drive raw/tennis-history/kalshi/{KXATPMATCH,KXWTAMATCH}.tar.gz (1-minute candles + taker tape). Start era only
  (markets with a start time, from 2026-04-27 05:00 UTC). The 2025-06-18 to 2026-04-26 era is a different product: not used.
- NEVER DOGE. Nothing from the lockbox (Nov 6-13) or after Nov 4 23:59 UTC is read.

## Decision times, entries, labels, exits
Times are decision instants; features use only bars closed at or before the decision; the entry fills after it.
- Perpetual: every 5-minute close (end of minute i = 5k+4). Taker entry at the next perp minute's open + 12 bps +
  half spread (BTC 0.19, ETH 0.22, SOL 1.23, XRP 1.94 bps). Long and short. Funding at the Kalshi 00/08/16 New York
  instants with per-coin offsets (1.66 / 1.19 / 0.14 / 1.57 bps per 8 h).
  Exit (primary): resting maker take-profit at the price that nets +$5 after entry costs, maker 5 bps and a 2 bps
  funding buffer (fills when the bar trades 1 bp through it); otherwise a taker exit at the close of minute i+H.
  No stop (the horizon bounds the loss). Label hit_H = the take-profit filled within H minutes (H = 15, 60).
- Price Prediction: every candle minute inside the bot's entry window (15-minute: 840-300 s before close, k = 1..10;
  hourly: 3300-600 s, k = 5..50, mid in [0.10, 0.90]). Taker buy YES at the ask or NO at 1 - bid, side price in
  [0.10, 0.90], fee 0.07 C P (1-P) rounded up to the cent (bot/fees.ts). Exit (primary): sell at the bid at the first
  minute where the net after both fees is >= $5 while outside the last 10% of the window; otherwise at the final candle
  ride to settlement if the position is in profit at the bid there, else sell at that bid ("no hold to settlement unless
  in profit"). hit = take-profit filled or the ride settled at >= $5 net. 15-minute contracts give the 15 m horizon;
  hourly contracts give the 1 h horizon (their remaining life is <= 55 minutes).
- Tennis: every candle minute from 30 minutes before the start to the close, spread <= 3c (TENNIS_MAX_SPREAD), side
  ask in [0.05, 0.95], YES and NO of each market, taker. Exit (primary): take-profit at the bid when net >= $5 within H;
  otherwise sell at the bid at minute k+H; if the market closes inside the horizon, ride to settlement only if in profit
  at the last candle, else sell at that bid.
- Also stored per row: best_H = hindsight best net at a tradable price within H (perp: limit fill at the extreme less 1 bp;
  Kalshi: the best bid sale or the settlement), and the minutes held under the primary exit.

## Features (strictly before entry)
- Spot TA (perp and Price Prediction), Binance spot 1m: the 117 classic + 4 perp primitives of research/perpTaSweep.ts
  buildPrims, and research/perpTaModules.ts modulePrims: every analyzer rule / book rule on 5m-1d, the 13 confluences,
  the net vote, conviction, TA-Lib's 22 key candlestick patterns + cdl_net + 10 TA-Lib indicator states on 15m and 1h,
  the character class and Hilbert trend mode. Excluded as leaky: TA Net / Librarian / cross-graph forecasts, the
  Librarian strategy and TA Net volatility conditions, setup_model.json scores, rule_book.json votes, MODEL_SKILL.
  Thresholds that need fitting use data before 2026-08-01 only.
- Contract state (Price Prediction): side price bucket, seconds to close, spread, mid change over 1/3/5 minutes, spot
  distance to strike in sigma units, fair value minus side mid, recent contract volume.
- Tennis: TA-Lib (RSI14, STOCH 14/3/3, WILLR14, CCI14, Bollinger %B 20/2, MACD histogram, LINEARREG_SLOPE14, MOM10,
  ADX14 with +DI/-DI) on the market's 1-minute mid, mid change over 1/3/5/15 minutes, the other market's change, taker
  flow imbalance and trade count over 5 minutes from the tape, spread, price bucket, the production underdog
  (0.08-0.25) and favourite (0.75-0.92) bands, time from start, tour.
- Context (all): hour-of-day bucket, weekend, RV60 tercile (regime v1 method, causal), 60-minute trend bucket.

## Splits
| type | discovery A (mine) | discovery B (confirm) | HO-1 (score once) |
|---|---|---|---|
| Perpetual | 2020-01-01 .. 2024-12-31 | 2025-01-01 .. 2026-07-31 | 2026-08-01 .. 11-04 |
| Price Prediction 15m / 1h | 2026-04-18 .. 06-14 | 2026-06-15 .. 07-31 | 2026-08-01 .. 11-04 |
| Tennis | 2026-04-27 .. 06-21 | 2026-06-22 .. 07-30 | 2026-08-01 .. 11-04 |
A decision belongs to a split only if its whole horizon (and, for Kalshi, its contract's close) ends inside it.
The mining and confirmation code never loads a row at or after 2026-08-01 00:00 UTC.

## Mining (discovery A only)
- Items = feature states with support >= 1% of discovery-A decisions. Setups = single items, all pairs of items from
  different features, and triples grown from the best 500 pairs (beam). Separately per contract type x scope (each
  asset, and all assets pooled; tennis: each tour and pooled) x horizon x side. Every evaluated conjunction is counted (N_raw).
- Matched base rate: strata = perp (hour bucket x RV tercile); Price Prediction (side price bucket x seconds-to-close
  bucket x RV tercile); tennis (side price bucket x match phase). uplift(S) = mean over S's rows of (outcome - stratum
  mean of all decisions), for the trade $ and for the hit flag.
- Keep S only if n >= 300 decisions, mean trade $ > 0, hit uplift > 0. Rank by the trade-$ uplift t with a deflated
  sample size (overlapping horizons: n x 5/H for perps; distinct contracts / matches for Kalshi). Drop a setup whose
  firing set overlaps a better one's by Jaccard > 0.5. Keep the top 40 per (scope, horizon, side).

## Confirmation (discovery B) and freeze
- Each kept setup is traded exactly: one position at a time per asset (skip while busy), primary exit, by-day $ with
  0 on days without trades. Tests (stationary bootstrap of daily $, mean block 5 days, 2,000 draws): p_ev for mean
  daily $ > 0, and p_up for daily $ minus the matched random-entry placebo's daily $ (8 seeds: each trade replaced by a
  random decision from the same stratum and day) > 0. p = max(p_ev, p_up). Also hit rate above the matched base on B.
- BHY at q = 0.10 over every setup confirmed within the contract type. Survivors freeze, at most 10 per (type, scope),
  ranked by discovery-B $/day. The frozen file's SHA-256 is logged in models/oracle-setups/ho1/openings.jsonl before
  any HO-1 number is computed. Nothing is re-selected after the opening.

## HO-1 (once per frozen file)
Per frozen setup and per contract-type book (all frozen setups of the type, ranked, one position at a time per asset;
perps one $300 position at a time across all coins): by_day over all 96 days (zeros included), regime v1 terciles at
entry (gdrive registry/regime-v1/fc05ea81.../labels.csv.gz; tennis: tour), control = flat, placebo = the matched
random-entry placebo above (8 seeds averaged). Pass (research/registry.py ho1_pass): >= 90 days, >= 4 of 6 16-day folds
won, worst fold >= -$0.50/h, >= 2 of 3 terciles with >= 100 h won, worst tercile >= -$0.50/h, beats the placebo; plus BHY
within the family (m = frozen setups of the type; also reported at m = every confirmed setup) and hit rate above the
matched base on HO-1. Only passing setups go into the rulebooks, ranked by HO-1 $/h.

## Adversary (reported beside every result)
Features one bar staler (should hold), features one bar early (a lookahead check: should jump), +1 minute entry latency,
cost stress (perp +5 bps a leg; Kalshi +1c on entry), and the matched random-entry placebo.

## Known limits
History fills on Binance USD-M, not Kalshi's perp book (15-minute tracking error ~21 bps on SOL/XRP); Kalshi history
has top-of-book only; tennis books are candle-level; live exits (pacer, take-profit floors) would pre-empt a +$5
take-profit unless the setup's tagged exit bypasses them, so the rulebook hook must run exactly the exit scored here.
