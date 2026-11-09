# Full-history Oracle, then frozen-block prediction

The owner's November 9 request is an Oracle-first pass through the full existing
minute archive, followed by unseen-to-model walk-forward blocks. The targets are
price up, sideways or down over 15 minutes and one hour. The existing fee-aware
profit clock remains responsible for contract sales.

Every valid minute is processed, replacing the earlier roughly daily feature
sampling. BTC/ETH start in 2017; other assets start later. The raw archive is
preserved, audited and quarantined without shifting off-grid timestamps. Missing
minutes, indicator warm-up and unfinished future windows do not become invented
observations or sideways labels. Original provider identity remains attached.
There is no fresh acquisition, Drive recopy or Lightsail work. New historical
acquisition remains tvdatafeed-only.

## Two separate passes

1. **Oracle answers.** Record actual terminal direction, return and maximum future
   upward/downward excursions at 15 and 60 minutes. Future values are targets only,
   never indicator inputs. Save quarterly sufficient-statistic tables, source
   receipts and feature checkpoints. Indicators and pending future windows continue
   across quarters. All registered descriptive curves are kept; statistical
   retention is not required to record what happened.
2. **Frozen-block prediction.** Replay causal inputs and freeze the matrix before
   each new quarter. Only earlier completed quarters supply training statistics,
   with a one-hour label embargo. Predict every eligible minute after at least
   365 calendar days of earlier history. Compare three-way probabilities against
   the earlier class-frequency baseline: log loss, Brier, accuracy, confusion
   counts and a prespecified 0.60 confidence diagnostic. Changing later Oracle
   answers cannot change an earlier forecast.

Chronological blocks are sequential within each asset; five assets run independently
on parallel GitHub runners. Memory is bounded by quarterly tables and a frozen
cumulative model rather than historical row count. Quarterly tables survive a
later block failure. Feature checkpoints document continuity, not a complete
resume protocol for pending labels. The all-history matrix is saved separately
after the historical forecasts and never predicts its own earlier training dates.
These folds are unseen to their particular model; reused history remains development
evidence rather than a fresh prospective trial.

## Continuous spectrum

The matrix records 28 axes and all 406 single/pair response surfaces:

- RSI, MACD histogram/ATR, centered Bollinger position and ATR basis points on
  completed 1m, 5m, 15m, 1h, 4h and daily bars.
- Causal BTC.D and USDT.D daily log changes, with an extra one-day availability
  lag. Missing/stale context stays unknown.
- Cyclic New York hour and weekday using the existing DST-aware clock.

The existing incremental indicator formulas are reused at explicit closed-bar
periods. Smooth transforms use 17 storage knots. Evidence is softly allocated to
adjacent knots, with periodic wrapping and continuous inference interpolation.
These knots are storage coordinates, not trading triggers. Tables retain effective
evidence, up/sideways/down frequencies, return moments and future excursions;
raw observed ranges are recorded per block.

Sideways means terminal return inside
`max(1bp, 0.25 * current completed 15m ATRbps * sqrt(horizon/15))`. This causal
definition is registered before labels and is separate from fees/profit.
The predictor uses a fixed equal mixture of available single/pair frequencies,
each shrunk by 100 observations toward the historical class prior. This empirical
matrix does not claim exhaustive higher-order relationships or all TA-Lib inputs.
Exact observed Oracle answers do not make a learned relationship a guaranteed
future law. The separate walk tests its predictive usefulness.

## Study and execution boundaries

`oracle-full-history-2026-11-09-v1` is a separate owner-authorized registration for
this request. It permits earlier history through November 8 with a one-hour
embargo before the unchanged November 9 future holdout. Older registrations are
preserved. Final outcomes and crossing labels are excluded.

The minute archive lacks native subsecond SNN tapes, historical funding/open
interest and contract books/fills throughout 2017 onward. This run does not
invent these inputs, upsample prices into second ticks, claim native SNN training
or turn spot returns into Kalshi profit. Existing native S5/S6 studies remain
separate. Minute OHLC also cannot establish within-minute target/stop order.

Contract profit must be verified using observed side bids, depth, actual entry
cost, as-of Kalshi fees and the existing dynamic $4.50/hour clock and final-window
rules. Movement prediction and fee-net sale performance are separate claims.
Live callers, risk sizing, orders, deployment and promotion are unchanged.

## Run and inspect

```sh
gh workflow run atlas-research.yml --ref feature/atlas-oracle-blocks \
  -f archive_run=42522123037 -f oracle_blocks=true
```

GitHub reads the fixed raw artifact once and shares the audited derivative with
five asset jobs. Each completes its Oracle pass before its walk. There is no
observation cap or sparse spacing.

Artifacts `atlas-oracle-result-BTC`, `-ETH`, `-SOL`, `-XRP`, `-DOGE` contain:

- `oracle/registration.json`, quarterly `manifest.json`/`matrix.f64.gz`, continuity
  checkpoints and a report with complete counts and input/source hashes.
- `walk/report.json` with frozen model hashes, training clocks and quarter scores.
- `walk/model.json` and the hashed `full-history-model.f64.gz`.
- `walk/relationship-spectra.csv.gz`: all occupied fitted spectrum cells, with
  raw coordinates, effective evidence, three-way frequencies and mean excursions.

`atlas-oracle-summary` pools same-quarter assets into time blocks for exploratory
predictive-gain comparisons. Quarter bootstrap intervals retain their independent,
stable-block assumption and establish no production qualification.

```sh
npm run research:opportunity-oracle -- oracle --archive /tmp/audited \
  --asset BTC --out research/out/full-BTC/oracle
npm run research:opportunity-oracle -- walk --archive /tmp/audited \
  --asset BTC --oracle research/out/full-BTC/oracle --out research/out/full-BTC/walk
npm run research:opportunity-oracle -- query --model research/out/full-BTC/walk/model.json \
  --request /tmp/current-oracle-features.json
```

Read-only queries supply asset, exact source, as-of/features-known clocks, layout,
15m/60m horizon and the raw 28-axis vector. They reject changed model bytes or
metadata, incompatible sources/layouts and backdated/future features. Returned
frequencies have no independent calibration or executable-profit claim and
cannot enable entries.
