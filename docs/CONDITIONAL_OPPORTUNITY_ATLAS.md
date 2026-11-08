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

This contains **Phase 1 plus an opt-in path-label dataset**, research-only. It does
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
2. **Generalized feature schema:** multi-timeframe full TA-Lib, derivatives funding/open
   interest, session timing, cross-lead, SNN state and dominance with explicit known-at
   timestamps. Every feature must use completed source candles as of its decision time.
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
