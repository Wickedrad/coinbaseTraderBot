# Codex handoff: rebuild the historical learning pipeline toward conditional price-path intelligence

Repository: `Wickedrad/coinbaseTraderBot`. Start from the latest `main` and apply the
`opportunity_atlas_v1.patch` supplied with this handoff on a **new branch**.
Never push or merge into `main` without explicit user review. No credentials, API keys,
server access, model promotion, or live trading changes are authorized by this handoff.

## Owner's target architecture

The owner's edge is estimating **when** a crypto asset is likely to change direction or
price, **how far**, and **how long the opportunity remains exploitable**, on multiple
horizons. TA-Lib is a vocabulary, not a set of fixed strategy rules. Deep one-minute
history (from the earliest available asset month, BTC and ETH 2017) is the evidence.
Each indicator must have smooth conditional effects on future price-path distributions;
other indicators, their order of arrival, volatility, regime, asset, BTC.D/USDT.D,
trading session and time to market close can fundamentally change those effects.
Learn conditional relationships directly, not additive yes/no indicator votes.
Retain only relationships with incremental out-of-sample predictive and **fee-net**
execution value. The SNN contributes temporally evolving state/learned history; the
astrocyte-like governor presently controls excitability and plasticity, NOT proof of
selective predictive-memory pruning. Infer no signal edge from its neuroscience label.

## Work staged in patch

- Streaming 1m path extrema/return labels for 5m..24h on fully completed candle windows.
- Incremental 15m RSI/MACD/Bollinger/ATR from closed 1m bars.
- Raw, past-completed TradingView daily BTC.D and USDT.D, never hindsight source splice.
- DST-aware existing session labels and cyclic New York time.
- A smooth RSI response conditioned on learned continuous MACD, bands, daily dominance,
  session and time-of-day neighbourhoods; numerical interaction curves.
- Strict chronological train/development/final partitions, with purged crossing spans.
- Development-only feature retention tests; final validation remains untouched.
- Serialized trained sufficient statistics, provenance and a read-only offline predictor.
- Tests and a separate CLI; absolutely no live or existing model call sites changed.

## Mandatory follow-on tasks (do not infer these are implemented)

1. **Audit the patch on real repository HEAD.** `npm ci`, `npm run check`, run
   `npm run research:opportunity-atlas -- --history <local history dir> --assets BTC --max-minutes 400000`
   on a sample. Verify estimates against direct 1m lookahead on a small fixture.
2. **Reversal ontology and path labels.** Implement a variety of parameterized,
   volatility-relative reversal/continuation definitions (preceding drift, turn,
   sustain), time to first significant move, first-hit target vs stop, MFE/MAE,
   exit fill/cost assumptions, censoring and ambiguous OHLC order handling.
   Test against small hand-calculated paths and random synthetic series.
3. **Broaden feature provider.** Use existing `taNet.ts` feature schemas and
   `taNetContext.ts`, proper multi-timeframe closed-bar as-of joins and 1m
   microstructure. Include BTC.D / USDT.D data quality, publication latency,
   BTC-vs-alt context, futures funding/open interest (where historically available)
   and exchange/session calendars. Never interpolate future price into an earlier bar.
4. **Model and selection.** Compare structured smooth response surfaces to
   gradient-boosted joint path heads and SNN temporal embeddings. Measure conditional
   incremental lift over *the full parent model*, not merely one indicator's marginal
   correlation. Use purged rolling-origin training, weekly/day-block evidence,
   multiple-testing controls, regime shifts and frozen truly final dates.
5. **SNN integration.** Evaluate S5 vs S6 versus simpler temporal baselines;
   prefer learned state embeddings/causal readouts to the present binary perps gate.
   Only consolidate/forget contextual memory when validated forecasts improve.
6. **Read-only consumer contract.** Build a query interface returning calibrated
   direction/target/horizon distributions, expected movement, risk and uncertainty.
   Shadow-log predictions at entry and during open paper trades; do NOT let a predicted
   target alone bypass hard risk controls.
7. **Execution and deployment.** Repair and verify replay/live fidelity gaps,
   auto-training promotion policy, perps replay availability, model version sync and
   all venue-specific fills before contemplating a live enable switch.

## Acceptance requirements

- Source provenance and known-at timestamps are attached to every feature and label.
- No feature computed from an unfinished higher-timeframe candle.
- All possible direction, horizon, target and stop labels are evaluated consistently.
- Missing data fails closed for affected relationships and does not create false bars.
- A relationship that doesn't add reliable **out-of-sample** value can receive zero
  influence; relationships with genuine *conditional* value survive marginal culling.
- Pair and higher-order interactions are learned rather than assumed additive.
- Final holdouts are not recycled for iterative development.
- New models remain paper-only until independently verified and explicitly approved.

## Current branch progress after the handoff

The original Phase 1 patch was applied on `feature/conditional-opportunity-atlas`
and audited against main `ef26c3679040b41c7b554e30cf44b350c049dc2e`.
Phase 1 passed 1,128 local repository tests with no skips, typecheck, build and a
400,000-minute synthetic CLI run. At that initial audit, actual BTC/ETH history was not available locally. A later
label-validation run downloaded checksum-verified August 2017 BTC/ETH samples
from Binance. Google Drive access remains a prerequisite for inspecting the
existing archive and its dominance series; see OPPORTUNITY_ATLAS_VALIDATION.md.

The next increment adds `research/opportunity/pathLabels.ts` and an opt-in
`--path-labels` export in the same history CLI. It implements configured long/short
ATR target/stop grids, causal preceding-drift reversal/continuation definitions,
consecutive-close confirmation, first-touch minute intervals, gap-stop pricing,
explicit ambiguous-bar lower bounds, assumed transaction costs, split purging and
censored horizons. It preserves Phase 1 fits and scores; it does not add trading
consumers, model promotion, or modify existing TA/SNN modules. See the architecture
document for exact definitions, units, assumptions and data-volume limits.

This is the label-generation portion of follow-on task 2. It is not completion of
the broader learning architecture: generalized causal features, rigorous model
selection, calibrated path heads, SNN integration, episode evidence and executable
venue validation still require implementation and independent historical checks.

The completed local check after this increment passed 1,142 tests without skips,
plus typecheck and build. The real BTC/ETH sample yielded 44,512 path-label rows;
170 sampled completed rows matched independent direct scans of the source candles.
No relationships were validated on this short sample and no models were promoted.

## Owner data-source requirement

All future data acquisition for this work must use tvdatafeed. Do not silently
substitute Binance archives, Coinbase downloads or other providers. Verify the
available symbols, intervals, timestamp semantics and actual historical coverage;
report missing coverage rather than assuming tvdatafeed can recover minute data
back to 2017. Previously completed Binance sample checks retain their recorded
provenance; they are not tvdatafeed validation and do not satisfy this requirement.


## Tvdatafeed workflow now implemented

`npm run research:opportunity-history` acquires explicit one-minute spot and daily
BTC.D/USDT.D through the isolated `tvFetch.py` bridge. It reuses the existing UTC
conversion and bounded retry helper and preserves the server/live TradingView
modules. It records requested versus actual coverage, excludes forming candles,
retains provider receipts, rejects provider/venue/content mismatches and returns
nonzero for missing coverage. The atlas CLI now defaults to `data/opportunity-history`
and `tvdatafeed-coinbase`, verifies input provenance and hashes, and carries the
correct source through reports and path exports.

Real no-login tvdatafeed acquisition and recent-window atlas export succeeded. A
2017 minute-history request correctly remained incomplete; a client request's 5,000-bar
limit is not historical pagination. Do not substitute other providers. See the
architecture document for installation and the validation report for exact observed
coverage and the distinction between current checks and the previous full suite.


## Existing server archive inspection via GitHub Actions

The owner confirmed that server access is through GitHub Actions only and requested
continuation of the archive check. The existing `Server diagnostics` workflow now
has an `atlas_inventory=true` mode on this feature branch. It uses the workflow's
existing Lightsail credentials to send `archiveInventory.py` on SSH stdin, reads only
history CSV header/tail metadata, and uploads `atlas-archive-inventory` on the runner.
Every existing diagnostics, repair and study job is excluded in this mode, even if
other flags are set. It does not read bot.env/keys/logs/model state, write server
files, acquire data, change the running bot or deploy a release. CSV folder names
and sidecar declarations identify candidates, not verified source provenance.


The read-only inventory run 42480623621 succeeded; all pre-existing jobs were skipped.
It found 73 TradingView/tvspot CSVs in the canonical store and raw export location,
but no one-minute files there. Daily/hourly/four-hour data exists; the earlier-minute
archive remains unlocated. Do not infer minute coverage or provider verification
from coarse bars/folder names. Full scope, timestamps and run link are in the
validation report. No server changes, model promotion, main merge or bot deployment
were performed. The feature branch is now pushed for review.
