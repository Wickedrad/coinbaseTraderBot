# Conditional Opportunity Atlas — historical discovery architecture

## Required data source and setup

All new data acquisition must use **tvdatafeed**. The dedicated research command
fetches the explicitly selected venue's one-minute spot bars and CRYPTOCAP daily
BTC.D/USDT.D. It never falls back to an exchange downloader or another venue.
The existing live/server TradingView helper and training pipeline are unchanged.

```bash
python3 -m venv data/opportunity-tv-env
data/opportunity-tv-env/bin/python -m pip install -r research/opportunity/requirements-tvdatafeed.txt
TV_PYTHON="$PWD/data/opportunity-tv-env/bin/python" npm run research:opportunity-history -- \
  --out data/opportunity-history --assets BTC,ETH --bars 5000
```

`TV_PYTHON` or `--python` selects an already prepared interpreter; the command does
not install dependencies or request credentials. The bridge uses the repository's
existing UTC timestamp conversion and bounded tvdatafeed retry helper, with no login.
The tested upstream commit is pinned in the requirements file. Windows users can
select their venv's `Scripts/python.exe` with `--python`.

**History limitation:** tvdatafeed's client limits each request to 5,000 bars. A
one-minute fetch supplies roughly 3.5 recent days, not minute history back to 2017.
An already accumulated tvdatafeed archive is needed for earlier minutes. Do not
silently fill missing coverage from another provider. The August Binance sample
checks later in this document are prior validation only, not the approved source for
new collection. No market data or credentials are bundled into Git.

`--exchange COINBASE --quote USD` is the default spot identity. Selecting another
venue/quote is explicit and writes a distinct `tvdatafeed-<exchange>` namespace;
changing an existing series' symbol/quote is refused. New data goes to the isolated
`data/opportunity-history/`, with spot at `tvdatafeed-coinbase/<ASSET>/1m.csv` and
indices at `tradingview/<INDEX>/1d.csv`.

`--from` and `--through` specify the required coverage, with through exclusive. They
**audit availability**, not historical pagination parameters to the upstream client.
By default, the required window ends at the last completed minute when acquisition
starts and spans 4,999 minutes for a 5,000-bar request, allowing for one forming bar.
Daily coverage includes two prior completed days so a change is known at the first
minute. Forming candles are excluded. Misaligned/invalid/duplicate rows are rejected,
gaps remain gaps, and null index volume returned to the importer is counted and
stored as zero only as an unused placeholder. The upstream client can itself encode
unavailable volume as zero, so index volume is not treated as an observed feature.
No prices are interpolated.

A raw provider receipt records client identity, plan, required window and returned
rows. Each imported series has a venue/symbol/content-hash provenance sidecar.
Repeat fetches merge only the same verified series. Unknown or modified existing
files are not overwritten. Each run saves a coverage snapshot and updates
`tvdatafeed-coverage.json`. Exit status 1 means incomplete coverage or a fetch/import
error, including partial upstream failures; other successfully fetched series are
retained. The process has a two-minute limit and a 32 MiB response limit.
Acquisition/import currently uses the existing in-memory merge helper; do not assume
it is suitable for merging a multi-year minute archive in one process.

## Scope and atlas command

This contains **Phase 1, an opt-in path-label dataset, and an offline multi-timeframe
feature provider**, research-only. It does
not modify the trading engine, live strategy gates, SNN checkpoints, model promotion,
or deployment. It is not evidence of a profitable strategy.

The atlas CLI now defaults to the tvdatafeed history directory and source. Set
chronological cuts inside your actual collected coverage; no cut dates are inferred
from the quality of predictions. For example, after setting the two variables:

```bash
npm run research:opportunity-atlas -- --history data/opportunity-history \
  --source tvdatafeed-coinbase --assets BTC,ETH \
  --train-before "${ATLAS_TRAIN_BEFORE:?Set a covered training cut in UTC}" \
  --final-from "${ATLAS_FINAL_FROM:?Set a covered final cut in UTC}" \
  --out research/out/opportunity-atlas.json
```

Tvdatafeed inputs are verified against their provenance sidecar and content hash
before fitting, including any daily indices present. Missing daily indices remain
unknown. Programmatic `buildAtlas` retains its original read-only default for older
callers; use `source: 'tvdatafeed-coinbase'` for the new store. Historical sample reads
may explicitly pass `--source binance-1m`; this never authorizes new Binance downloads.
The program does not assert that a short, complete sample is enough to validate a
relationship: the development-week and sample-size requirements still apply.

The command streams entire 1m spot files per asset, with bounded label windows. It samples features
only after every fully completed 15-minute candle and measures 5, 15, 30, 60, 120, 240,
480 and 1440-minute **subsequent** price paths from the observed 1m highs/lows/closes.
Missing 1m timestamps invalidate pending labels; they are never filled with fictional prices.
Daily BTC.D and USDT.D changes become known only after the corresponding daily close;
no history value is backfilled into its own forming candle. The initial trainer reads raw
TradingView daily index rows rather than applying cross-source scaling estimated from
future overlaps. Missing/stale dominance remains
unknown rather than guessed from later data. Sessions reuse the existing DST-aware clock.

The first feature set is a **narrow prototype**, not the intended full feature universe:
15-minute RSI, MACD histogram, Bollinger %B, ATR, continuous cyclic New York hour, session, daily BTC.D and USDT.D
changes. RSI is represented as a smoothed conditional probability curve. The candidate
context groups `macd`, `bands`, `session`, `time`, `dominance`, `macd_bands`, `macd_session`
condition RSI jointly instead of voting on indicator thresholds. Bins are a statistical
approximation, NOT entry rules. A group is selected only on the configured development interval using a
conservative week-block gain bound; the configured final interval is reserved for
untouched evaluation. The original study defaults remain 2025 development and 2026 final.
The holdout must not be re-used to choose or adjust candidate groups.

**Important limits:** The Phase 1 fitted probability report still models close-to-close
direction and maximum excursions/ATR touch frequencies. The separate path dataset below
adds reversal and first-touch labels, but these are not fitted or calibrated prediction
heads yet. Neither output supplies fee-net executable returns, fill probability, or a
trained trade manager. Reported probabilities are NOT approved for live trading.

## Optional path-label dataset

```bash
npm run research:opportunity-atlas -- --history data/opportunity-history --source tvdatafeed-coinbase --assets BTC,ETH \
  --train-before "${ATLAS_TRAIN_BEFORE:?Set a covered training cut in UTC}" \
  --final-from "${ATLAS_FINAL_FROM:?Set a covered final cut in UTC}" \
  --out research/out/opportunity-atlas.json \
  --path-labels research/out/opportunity-paths.jsonl \
  --path-targets-atr 0.5,1,2 --path-stops-atr 0.5,1,2 \
  --path-fee-bps 4 --path-half-spread-bps 1 --path-slippage-bps 2
```

The cost numbers above are illustrative assumptions, not measured venue fees or fills.
Each defaults to zero and is written explicitly into the dataset. `--path-labels` is
opt-in: without it the existing Phase 1 fit and report are unchanged. A JSONL metadata
record captures input source, partitions, grids, definitions and costs. Subsequent rows
are `opportunity-path-labels-v1` observations; the report references their file and
counts. Incomplete runs do not publish a partial label file. Outputs must be outside
the input history directory and the labels must differ from the report path.

`research/opportunity/pathLabels.ts` shares the existing completed-candle feature
stream. For each decision it evaluates both long and short across all configured
target/stop pairs and all eight horizons (5 minutes to 24 hours). ATR is frozen at the
entry: a target is `entry * (1 + direction * targetAtr * atrBps / 10000)` and the stop
is the opposite move. The price grids are label definitions, not trading rules.

- Future paths exclude the entry candle. MFE and MAE are nonnegative simple returns
  in basis points relative to the entry over the observed prefix, including the full
  horizon even after a hypothetical barrier exit. They are not log returns; Phase 1's
  original extrema fields remain log returns. First target and first stop minutes
  are recorded separately. Touch times identify a one-minute interval, not an invented
  tick time. The candle open orders gap touches; unfavorable stops use the gap open,
  while favorable targets conservatively use their limit price.
- If both barriers are touched with the open between them, the label is `ambiguous`.
  Its `netReturnBps` is a stop-first lower bound with `payoffBasis` explicitly set to
  `ambiguous-lower-bound`. It is not silently counted as an identified stop or target.
- Parameterized close-based turn definitions use only a contiguous preceding window
  known at the decision. The defaults are a 15-minute drift of at least 0.5 ATR with
  a 0.5 ATR turn sustained for three closes, and a 60-minute drift of at least one ATR
  with a one ATR turn sustained for five closes. Drift opposite the queried direction
  defines reversal context, aligned drift defines continuation, and smaller drift is
  neutral. A confirmed run's first close is `onsetMinute`; its last required close is
  `confirmedMinute`. Failed candidate runs reset. An unavailable preceding window is
  unknown, never replaced with future observations. These are entry-anchored definitions,
  not an assertion that every local extremum is an observable reversal.
- Gaps, end-of-input and the processing cap emit unfinished horizons with an explicit
  censor reason and observed-minute count. Missing subsequent prices cannot produce a
  negative event label or a horizon-close payoff. Previously observed barrier hits
  remain available, but full-horizon MFE/MAE stay censored. Unknown or unresolved turn
  outcomes are null. Empty future windows contain no invented prices or hit times.
- Every row carries entry features, their aggregate known-at timestamp, source,
  planned end, observed-through time, actual label known-at, partition and cost assumptions. The **planned full
  horizon** determines split purging even for early hits or censored prefixes. `purged`
  rows are retained for audit and must be excluded from fitting/scoring. A gap is only
  known when the next observed candle exposes it; this detection time can also purge
  a label whose information would arrive after its partition boundary. Censored rows
  must not be treated as complete observations. Overlapping rows are dependent; counts
  are not independent episodes or a statistical significance claim.
- Hypothetical unit-position payoffs apply adverse half-spread plus slippage on each
  leg and fees on entry and exit notionals. Barriers use observed underlying prices;
  otherwise a completed horizon exits at its final close. No funding, borrow, venue
  collateral, quote availability, queue position or actual order-fill model is implied.
  `payoffAvailable` means this stated assumption can be evaluated, not that a real fill
  was observed. These are spot-path labels and do not model Kalshi option payoffs.

The labeler holds only the configured maximum lookback/horizon (at most 24 hours),
shares barrier state across horizons and streams output with bounded write buffering.
Disk output scales with all grid combinations: the default grid produces 144 rows per
decision, so start with a minute cap or a single target/stop pair before exporting years.
No path dataset is consumed by the live bot, SNNs, Phase 1 selector or promotion pipeline.

## Offline multi-timeframe features

`research/opportunity/features.ts` implements the first part of the generalized
feature schema. It reuses `tfState` and `tfFeatures` from the existing TA modules,
including their TA-Lib vocabulary, across 1m, 5m, 15m, 1h, 4h and 1d. It does not
call the rule-vote evaluator, load a fitted model, inspect outcomes, or change any
live caller. The schema is `opportunity-features-v1`, with the reused TA schema and
actual indicator engine recorded separately. This is not an existing TaNet model's
input vector: its windows, timeframe coverage and context are explicitly different.

`CausalAtlasFeatures.push` accepts strictly increasing, valid observed minutes.
Only complete consecutive UTC-aligned buckets enter TA. A stream beginning in the
middle of a bucket withholds that bucket. A timestamp gap clears all minute-derived
windows and pending buckets; independently supplied daily context remains separate.
This deliberately favors missing features over indicators spanning an outage.
Rolling windows are bounded to 1,440 minute bars, 288 five-minute bars, 256 fifteen-minute
bars, 280 hourly/four-hourly bars and 250 daily bars. The intraday windows cover a
full UTC day for the shared session VWAP calculation. Shared 4h feature options omit
SMA200 and VWAP, as in the existing TA vocabulary.

A snapshot is available after each observed minute close. Its immutable groups
carry source path, exact input SHA256, first/last contributing candle opens, latest
known-at time, bar count, timeframe, availability status and numeric values.
Individual values remain null until their own warmup completes; `ready` means the
shared TA state exists (at least 30 closed bars), not that every indicator is finite.
Entire missing/stale groups have null values. Spot daily TA therefore needs 30 complete
days of contiguous minute observations. No daily bars are fabricated from coarser
Yahoo prices. The clock carries a code-source reference rather than an input-data
hash; report-level code hashes identify its implementation and the TA implementation.
Provenance fields are metadata, not predictive numeric inputs.

`AsOfDailyFeatures` joins each daily source independently at `open + 24h + lag`.
The default lag is an additional 24 hours, with a maximum age of two days after
that assumed availability time. Historical publication times are **unverified**;
this is a recorded conservative timing assumption, not proof of actual historical
availability. Lookup works for backwards queries, never uses an unfinished/future
suffix, and restarts the indicator prefix after a daily timestamp gap. Archived Yahoo
asset context, TradingView BTC.D and TradingView USDT.D keep distinct namespaces;
there is no hindsight cross-source scaling. Yahoo volume conventions are unverified
and its volume features are source-specific. CRYPTOCAP volume is treated as an
unobserved placeholder: volume/profile/divergence/breakout derivatives are null.
Funding, open interest, SNN state and cross-asset lead/lag are still unimplemented.

Minute microstructure includes close-to-close/open log returns, range fraction,
close location and observed taker imbalance. Missing taker-buy volume stays null,
distinct from an observed zero. No spread, order-book depth or fill quality is inferred
from OHLCV. BTC-versus-alt identity and the existing DST-aware clock/session features
are descriptive inputs rather than trading gates.

The dedicated command reads an exported, audited archive layout:

```bash
npm run research:opportunity-features -- \
  --archive data/opportunity-archive-42489751110 --assets BTC,ETH,SOL,XRP,DOGE \
  --out research/out/opportunity-features.json
```

The archive contains `archive-validation.json` and `history/<source>/<asset>/<tf>.csv`.
The CLI verifies each selected input's audited readiness and exact hash before and
after replay, and records source-code hashes checked for changes during the run.
Absent daily inputs yield explicit missing groups; a present but invalid/modified
audited input fails. Optional `--max-minutes 50000` bounds each asset; the default
processes its whole file. Snapshots are sampled at UTC closes every 15 minutes by
default (`--every-minutes`). Optional `--frames research/out/opportunity-features.jsonl`
exports the actual groups for later joins by asset and decision timestamp; without it,
only availability/count diagnostics are saved. JSONL output may be large. Reports and
frames must be outside the input archive. Files are published only after a successful
run. No fitting, label scoring or relationship selection occurs in this command.

The existing archived Binance-labelled files were located at the owner's request
to search minute history regardless of provider. They retain that identity; copying
an existing archive is separate from new provider acquisition, which remains
tvdatafeed-only. The 2026 archive overlaps the original frozen final period. Its
data/feature validation does not authorize moving the split or fitting/tuning on it.

## Contract duration, forecast timing and remaining life

The owner explicitly requires contract-aware timing: a likely reversal within an
hour can inform an hourly contract, but an hourly forecast alone cannot justify a
15-minute entry. As the setup unfolds, the system must recompute a short-window
conditional forecast; a fresh high-confidence move within the actual remaining
contract time can then become relevant. Nominal duration and remaining life are
different: a 15-minute contract entered six minutes after opening has nine minutes
left. An hourly contract with nine minutes left has the same immediate deadline,
while its strike, opening reference and lifetime context can differ.

The new research-only `contractTiming.ts` makes this requirement explicit:

- `contractTimingQuery` binds an as-of feature frame to the exact asset, ticker,
  opening/closing timestamps, known strike/range terms, settlement index and
  averaging window. It supplies continuous remaining-time/lifetime geometry for
  future learners, plus an explicit execution buffer and an exact effect deadline.
  The query clock can be between minute closes; it records the last feature-frame
  timestamp and age. The default maximum frame age is one minute and can be
  explicitly configured. Future or older-than-policy frames are refused.
- A forecast for a later horizon remains contextual evidence. It is not rounded,
  interpolated or substituted for a shorter deadline. An old hourly probability
  does not become a fresh short-window probability just because time has elapsed.
  Context probabilities retain direction, event definition and absolute deadline.
- `assessContractTiming` requires a fresh exact-contract, exact-deadline forecast
  for timing support. It distinguishes the probability of the directional event
  by the deadline, the selected YES/NO side paying under the actual settlement
  terms, and their **joint** probability. It does not multiply marginals or equate
  a spot target touch/spot close with the official averaged-index settlement.
- Confidence lower-bound requirements are explicit caller-specified research
  policy, not fixed RSI/MACD votes. Timing and joint thresholds are separate; there
  is no universal requirement that a trade have an 80% settlement-win probability.
  `timing-supported` only describes the supplied timing policy. Quotes, fees,
  fill quality, expected value and hard execution/risk checks remain separate.
- A missing calibration reference produces `unvalidated`; invalid probabilities,
  future/stale inputs or mismatched terms cannot supply exact timing support.
  The reference is metadata for the future model loader, not verified calibration
  evidence created by this helper. Multiple matching models require validated
  upstream aggregation; this helper never picks the highest confidence after the fact.

The predictive horizon is distinct from a TA candle timeframe. A learner can read
1m/5m/15m/1h states jointly to predict a move in the next seven minutes. It need not
wait for a particular candle size or require a fixed checklist of indicator votes.
SNN state/readouts must eventually participate in this same contract/window query,
rather than using only the current nominal 15/60-minute column selection. Existing
SNN callers, inputs, outputs and live entry logic are unchanged by this increment.

This module accepts forecast outputs; it does not generate them, train a model,
authenticate calibration artifacts or wire the SNN. Its tests use explicitly
synthetic forecasts. Every assessment sets `researchOnly: true` and
`liveEntryAllowed: false`, including `timing-supported` results. This is the first
consumer-contract portion of the architecture, not proof that a trained system
can identify these opportunities.

Future training must also sample decisions inside contracts and label their exact
remaining-time/settlement questions. The existing Phase 1 trainer still anchors
entries at completed 15-minute candles and its fixed horizon labels are spot paths;
they are not automatically exact remaining-time contract labels. The independent
feature CLI can sample every minute (`--every-minutes 1`). Neither those entry
labels nor the production SNN readouts were silently repurposed by this helper.

## Module routing and implementation sequence

| Existing module | Required next change | Evidence required |
| --- | --- | --- |
| `bot/ta/taNet.ts`, `research/trainTaNet.ts` | Multi-horizon conditional path heads, not only 1h/4h direction/vol. Extend 1m-derived context without leaking future bars. | OOS calibration and target/horizon skill |
| `bot/ta/taNetContext.ts`, `research/history/dominanceReplay.ts` | Distinguish observed BTC.D/USDT.D, estimated dominance, BTCDOM proxy, and as-of freshness; model BTC vs alt conditional effects. | Ablation gains per era/asset |
| `research/taStudy.ts`, `research/oracleCull.ts` | Generalize this atlas to continuous feature responses; select conditional and incremental predictive gain, not only marginal hindsight-oracle correlation. | Purged walk-forward, multiple-test control |
| `bot/snn/network.ts`, `bot/snn/column.ts`, `bot/snn/params.ts` | Expose state embeddings/history and test S5 vs S6; add relevance/retention only if predictive value improves. Do not mistake governor G for selective memory pruning. | Same-period ablation against non-SNN baseline |
| `research/trainSetupModel.ts`, `bot/setups/detectors.ts` | Generate broad historical states independent of hand-selected detector events; train path/payoff surfaces. Detectors may remain as explainable candidates, not universal discovery gates. | OOS comparison with current detector-gated model |
| `bot/setups/features.ts`, `bot/setups/setupModel.ts` | Accept calibrated path surfaces, feature interactions, target/horizon estimates and confidence; avoid percentile-only economic decisions. | Predictive/financial OOS assessment |
| `bot/setups/setupTrader.ts`, `bot/setups/exits.ts` | Paper-shadow recalculation during a trade; compare hold/partial/exit conditional value. Hard execution and risk limits remain. | Replay/Paper vs live execution-fidelity tests |
| `bot/model/sessions.ts`, `bot/model/sessionRisk.ts` | Retain clock/session features; learn nuanced interaction with direction, time-to-move, liquidity and horizon rather than only fixed session multipliers. | Session-by-session OOS and cost sensitivity |
| `research/history/historyReplay.ts`, `research/replayFidelity.ts` | Keep reconstructed intraminute bridge separate from observed OHLC; do not train pre-close forecasts on minute close or simulated future. | Execution-fidelity + causal feature tests |
| `research/pipeline.ts`, `research/laptopTrain.ts`, `bot/autotrain.ts` | New phased step only after verified atlas data, bounded resource use, model provenance, OOS challenger gates and no uncontrolled promotion. | CI + version compatibility + unattended-run tests |

## Further phases, not yet implemented

1. **Label ontology follow-up:** the optional dataset now supplies parameterized reversal/
   continuation, first-target/stop, excursions and censoring labels. Next validate these
   definitions on actual history, estimate independent episodes and model venue-specific
   executable fills before training or claiming profitable target/horizon predictions.
2. **Generalized feature schema follow-up:** the independent offline provider now
   supplies multi-timeframe TA, minute microstructure, daily-source freshness and
   session timing with explicit assumed known-at timestamps. Add derivatives funding/open
   interest, cross-lead, SNN state and verified historical publication timing. Join
   features to path labels without recycling final data for selection.
3. **Sparse joint nonlinear learner:** compare smooth basis splines, boosted trees and
   sequence/SNN encodings. Select useful interaction groups by *incremental*
   validated prediction and fee-net payoff, not standalone correlations. Keep suppressed
   relationship evidence for regime-dependent reactivation.
4. **Dynamic query interface:** output conditional path distributions and price target/horizon
   and time-to-hit curves with uncertainty. Continuously re-query in paper mode for open
   positions before any live order integration.
5. **Data provenance:** historical spot, Binance USD-M futures, funding, BTC.D/USDT.D,
   and existing Kalshi/perp recordings have different venues and availability dates.
   TradingView `tvdatafeed` (unofficial) is neither a guaranteed source of complete
   minute futures history nor a substitute for exchange archives; obtain rights and
   verify provenance/coverage before importing it.
6. **Promotion policy:** use development-only selection, purged future-label spans,
   independent final periods, regime/asset/session attribution and execution-fidelity
   reconciliation. Refuse unvalidated automatic live promotion.

## Design invariant

The bot must learn continuous, regime-/asset-/session-conditional relationships between
market features and the **distribution of future price paths**. Trade decisions are
subsequent queries of those relationships, not fixed TA threshold combinations.

## Verification in the real checkout

The supplied patch was audited against repository main at
`ef26c3679040b41c7b554e30cf44b350c049dc2e` without stand-ins.
The audit corrected discontinuities at numeric interpolation boundaries, made
as-of dominance lookup safe for backwards queries, and made the stored consumer
return null when its selected context is missing or RSI is invalid. Interpolation
uses Gaussian weights tapered continuously to zero at their support boundaries.
Minute rows with empty fields or timestamps off the minute grid are rejected.
The input stream is closed when the processing cap is reached. The default output
is the existing ignored `research/out/` directory.

Week-block lower bounds are heuristic diagnostics, not a guarantee of statistical
significance across all candidate groups and horizons. This prototype does not
provide executable returns, calibrated path distributions, rolling-origin
validation or full source/known-at provenance for every individual feature.
Do not use it as evidence of trading readiness.
