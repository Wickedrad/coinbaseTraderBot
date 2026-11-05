# All-pairs entry/exit payoff matrices

Steven's ask (2026-11-05): replace post-hoc reflection on single trades with dense counterfactual labels. Every 15-minute
Kalshi window becomes an upper-triangular matrix P[i, j] of the net P&L of entering at minute i and exiting at minute
j > i (column N = settlement), an exit policy is learned from those matrices by backward induction, entry labels follow
that exit policy, and every candidate is judged out of sample against placebos and a deflated Sharpe gate.

## Pieces

| File | What it does |
|---|---|
| `fees.py` | Kalshi fees, an exact port of `bot/fees.ts` (taker 0.07·C·P(1−P), maker 0.0175·M·C·P(1−P), rounded up to the cent grid). Tested against the published fee table. |
| `data.py` | Loads Kalshi's own 1-minute candles (Drive `raw/history/kalshi/KX<ASSET>15M`) and Binance 1-minute bars. DOGE is dropped whatever is asked. |
| `features.py` | X_t from information known at t only: returns, realized vol, RSI, Bollinger width/%b, MACD velocity, OU residual, volume z, range; strike distance in vol units, digital fair value and its gap to the quote, spread, mid changes, minutes left. Extra features are safe expressions (`bbw20 * tau_frac`). |
| `matrix.py` | `compute_all_pairs_pnl_matrix` (Steven's blueprint, with the real fees) and the batched `all_pairs`: taker/maker entry × taker/maker exit. Maker fills need the other side to reach our price in the next minute's candle. |
| `snell.py` | The exit policy: Longstaff–Schwartz backward induction with LightGBM continuation values, cross-fitted, under the settlement rule (never settle unless the last 10% and in profit; `end_rule='bot'` mirrors the bot's ride rule). Also the hindsight envelope (report only) and the naive hold. |
| `policy.py` | Entry rows labelled by the exit policy's realized P&L (never max over j), the entry model, the trading simulation (one position per window), random-entry and shuffled-label placebos. |
| `validate.py` | Purged walk-forward folds, PSR / deflated Sharpe, block bootstrap. |
| `synthetic.py` | Digital Black–Scholes pricer calibrated on real 15-minute mids and spreads, for windows with no real quotes (hourly): reported apart, never gated. |
| `run.py` | One arm (base, stress, placebo, synth15, synth1h), any subset of folds (`--part/--parts`), and `combine`. |
| `report.py` | The Diagnostic Summary Card and the gate (target, CI, DSR, placebos, stress, champion); trial ledger and champion on Drive. |
| `fake.py` | A fake history with a planted quote lag, for tests and smoke runs. |

## Run

On GitHub: `.github/workflows/all-pairs.yml` (a push to the thread branch whose message has `[all-pairs]`, or a dispatch
once on main). Locally:

    cd python
    python -m allpairs.fake --out /tmp/fake --days 30
    python -m allpairs.run --history /tmp/fake --arm base --out /tmp/base.json
    python -m unittest discover -s allpairs/tests -t .

## Hypothesis loop

A hypothesis is a copy of `hypotheses/base.json` with one change: an `extra_features` expression or an execution
parameter (`costs`, `exit.end_rule`, `entry.entry_minutes`, hurdles). Each scored configuration is a trial in the
deflated Sharpe; it replaces the champion only when the card's gate passes.
