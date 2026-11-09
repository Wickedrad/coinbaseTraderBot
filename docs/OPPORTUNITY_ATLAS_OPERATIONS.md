# Conditional Opportunity Atlas: offline and paper operation

The owner's current objective is **reliable advance movement followed by a
fee-net sale using the existing dynamic hourly profit clock**. Start with
[advance movement and profit-taking](OPPORTUNITY_ATLAS_PROFIT_OBJECTIVE.md).
The older joint settlement workflow below remains a separate diagnostic;
settlement wins and its payout calibration are not the movement learning target.

This release supplies the data-to-query research workflow. It does **not** include
a qualified trading model. It never submits orders, changes the bot's parameters,
promotes a production model, deploys, or merges. The existing bot, TA network,
SNNs, setup traders, exits and risk gateway keep their existing call sites.

## Run the software demonstration

```sh
npm run research:opportunity-product -- demo --out research/out/opportunity-product-demo-v1
npm run research:opportunity-product -- status --product research/out/opportunity-product-demo-v1/study/product.json
```

Use a new output directory for each run. The demonstration generates synthetic
index prints, venue terms, quotes and reported settlements. It assembles 740
observations, compares continuous joint MLP, joint GBDT and linear candidates,
performs conditional ablations, exports a registry artifact and logs a paper query.
Its planted interaction is a software check. Its short synthetic audit must remain
unqualified and its paper recommendation must abstain. Generated datasets, model
weights and recordings stay under the ignored `research/out` directory.

The older `research:opportunity-history`, `research:opportunity-features`,
`research:opportunity-decisions`, `research:opportunity-atlas` and
`research:opportunity-joint` commands remain available. The competing-risk learner
answers exchange-spot target/stop questions on a one-minute grid. Its output is
separate from the official-index contract probabilities introduced here.

## Use existing observed recordings

Fresh historical acquisition remains **tvdatafeed only**. These commands read
already-stored bot recordings; they do not download market data from another
provider. Native recordings may be `.jsonl`, `.jsonl.gz` or `.mdc`, using the
repository's existing recording reader.

```sh
npm run research:opportunity-product -- recordings \
  --recordings data/recordings \
  --config research/opportunity/examples/prospective-recording-import.json \
  --out research/out/atlas-recording-inputs-v1
npm run research:opportunity-product -- assemble \
  --spec research/out/atlas-recording-inputs-v1/spec.json \
  --out research/out/atlas-contract-dataset-v1
```

The importer reads observed `market`, `index`, `candles`, `book`, `delta`, `perp`,
`dominance`, `gap` and `result` messages. It accepts only index messages explicitly
marked `src: kalshi` for official contract reconstruction. It excludes `hist`,
`synth` and proxy data,
never invokes the historical replay's synthetic price bridge, and never builds
ticks from minute OHLC. An unspecified historical candle provider is recorded as
unspecified; a recording is not tvdatafeed provenance or independent proof that a
provider published the prices. Conflicting index corrections require an audit.

Closed 1m candles drive the existing TA feature functions on 1m, 5m, 15m, 1h, 4h
and 1d. The frame's timestamp is the actual recorded arrival used for the query.
Every derived group is conservatively available no earlier than its input's
recorded arrival. Forming candles are excluded; gaps reset the existing minute
feature provider. BTC-relative returns use observed index marks. Missing daily
dominance, funding, open interest, taker flow and other unavailable observations
remain missing. Additional historical daily context can be supplied through the
existing audited feature builder, without a hindsight source splice.
Observed native dominance snapshots and perp funding/open-interest snapshots are
also exposed directly to their conditional feature families. They retain actual
arrival times, a 60-second source-age limit and missing masks. Per-contract marks
require a recorded contract size before conversion to per-coin premium; unknown
units never become a spot premium. These snapshots are not relabeled as daily TV
or exchange-published history. Crypto and perps SNNs consume their existing input
mappings separately, then join only same-time states with both provenances.

Terms carry a basis as well as their source hash. Recorded venue strikes use
`recorded-contract`; a missing Up/Down strike may be reconstructed from the
then-known opening index average as `computed-opening-index`, available no earlier
than that query. Manually supplied terms default to `declared-contract`. Declared
or reconstructed terms can support research labels but cannot qualify an artifact
for paper entry until the venue terms are recorded and the study is rebuilt.
Some older DOGE messages call `B` range tickers `greater`. The importer uses the
existing venue range-ticker rule with the recorded lower/upper bounds, and counts
the canonicalized messages. It does not invent a missing range bound.

The importer creates both YES and NO examples for every configured event at each
eligible observation, independent of the bot's setup detectors. Add up/down move,
reversal and continuation definitions to the config to cover the intended ontology.
`thresholdBps` sets a fixed price-bps move; `thresholdAtr` instead multiplies the
then-known entry ATR. Use exactly one. A reversal/continuation also needs a
preceding window and either `priorDriftBps` or `priorDriftAtr`. The ATR is measured
from actual completed spot bars, with its own definition and known-at timestamp;
it is not an official-index ATR silently reconstructed from spot.

Each quote carries side, best bid/ask, available size, arrival and explicit dollar
cost assumptions. NO quotes complement the opposite YES side. The example fees
are assumptions to replace with venue-appropriate measured values. A quote is
not a fill. The input cap stops new observations while continuing the selected
contracts' index/result collection through close plus five minutes; later results
remain unconfirmed. Existing reader tolerance of torn recording lines remains;
missing path/settlement coverage still fails closed.
Existing recordings do not consistently preserve all websocket gap/sequence
events. Economic examples therefore require a fresh observed book snapshot;
delta-only reconstructed books cannot establish executable quote evidence.

For long studies, `sampleEveryMs` fixes a per-asset sampling cadence in advance
and `maximumContractsPerAsset` limits contracts at each sample using only current
index distance. The example uses one daily sample per asset and three nearby
contracts. Choose the schedule before inspecting outcomes, and retain examples
of both 15m and hourly geometry where those are the questions being validated.
Index output and assembly stream from disk; assembly keeps only predeclared
decision/prior/settlement windows in memory. Defaults cap 20,000 decisions,
two million retained index prints per asset and 20 million candidate matrix cells.
Use sparser predetermined sampling or separately registered studies to fit the
available hardware. A cap or missing historical period is reported, not treated
as coverage of an entire archive.

For another data collector, write the same receipt-checked spec and JSONL files.
The exported TypeScript interfaces in `productCli.ts` document the formats:
`AssemblySpec`, `RecordedDecision`, `OfficialPrint`, `TimedPriceContract` and
`TimelyMoveDefinition`. The spec uses relative filenames plus SHA-256 receipts.
Prints include both event time and actual arrival time. Terms and results must be
observed, rather than fabricated from the future price path. A contract's
settlement reference must match the exact index source. A stable SHA identifies
the input contents; it does not authenticate a vendor.

## Outcome definitions

The contract learner jointly models four outcomes: neither timely move nor payout,
timely move only, payout only, and both. Its three conditional heads estimate
`P(move)`, `P(pays | move)` and `P(pays | no move)`. The resulting four probabilities
sum to one. `P(move and pays)` is learned through this conditional factorization,
not calculated by assuming independent marginal events.

Movement is evaluated on a one-second grid anchored to the query arrival, ending
at the exact close minus execution buffer. A threshold crossing must finish its
configured sustain interval before that deadline. A reversal also requires
opposite preceding log drift; continuation requires aligned drift. Missing prior
or future required observations censor the label. Unobserved fractions of the
last second are outside this declared event definition. Price moves and extrema
use arithmetic price bps; preceding drift uses log bps.

Settlement reuses `IndexTracker.settlement`: the last available print at or before
each of the sixty official second marks ending at close, with the existing 3s
maximum print age. `updown` and `greater` pay YES at equality, a `between` range
includes its lower boundary and excludes its upper boundary, and `less` excludes
its cap. Incomplete index coverage is missing, never a synthetic NO label.
Reconstruction is distinguished from a reported exchange result. Disagreement
is quarantined; a merely reconstructed label cannot count as a confirmed result.
The earliest required observation/result arrival determines label availability,
rather than the later time at which an archive was processed.

## Causal SNN inputs and comparisons

`captureSnnState` reads the existing `SnnNetwork` synchronously. It does not step,
score, tag, settle or train it. It pools actual encoder/hidden rates, predictive
coding latents and errors, and observes readout, salience and governor values.
Unknown calibration metrics remain null. It does not use the contract feature
pool whose distance multiplier would erase state at an at-the-money strike.

Snapshots include version, stage flags, input-source hash, checkpoint hash, checkpoint availability,
training-through, input-known-at, state time and observed/forward-paper basis.
Future-trained checkpoints, stale states and mislabeled S5/S6 configurations are
rejected. These provenance declarations must come from the collector; file mtime
does not establish them. Hashes, IDs and raw timestamps stay out of numeric inputs.
The domain is explicit: crypto and perps networks cannot be silently exchanged.
Representation identity also includes the starting checkpoint and its availability
time; matching network parameters alone cannot substitute a different lineage.
`combineSnnStates` can join both isolated networks at the same causal time with
separate provenance and column names. A model trained with both requires both.
`trainedThrough` describes weight learning; running state and grading history
still advance causally while weights are frozen, as in the existing network.
Their latest observed arrivals are included in `inputKnownAt`.

```sh
npm run research:opportunity-product -- snn-replay \
  --tape research/out/observed-inputs.tape \
  --domain crypto \
  --study-policy prospective-2026-11-09-v1 \
  --out research/out/atlas-snn-states-v1
```

This reuses the repository's observed-input SNN tape format and emits S5/S6 JSONL
states. Both variants receive the same calls. For holds up to three seconds the
adapter advances previously observed inputs before the next observation. Longer
input gaps clear transient state, held inputs and pending direction/contract tags
while preserving learned weights. Missing horizon prices cannot grade old calls.
The gap policy is part of state/model compatibility. Learning
in the observed-recording study also requires a price no older than three seconds.
The source tape omits stale columns; replay clears their pending calls, masks the
unavailable state and conservatively pauses learning until required inputs return.
The legacy replay default is unchanged. This policy is explicit in provenance and
required for retained SNN state to qualify. Learning
freezes at the selected registered study's training cutoff; no future settlement
trains an earlier state. The default legacy study still uses the pre-2025 cutoff.
The adapter starts from a fresh network and does not transplant today's weights
into a historical study. Its report records gaps and the tape's content hash.
Legacy tapes round step/score timestamps down to the second while settlement
timestamps retain milliseconds. The adapter delays rounded calls by a full second
by default, records that lag, and rejects backwards arrival order. Only an
independently verified exact-clock tape should use `--input-lag-ms 0`. Models
require the same declared input clock at query time. This conservative replay
does not claim byte parity with the legacy rounded-time execution.
It cannot determine from the tape bytes alone whether the tape's upstream builder
used real or simulated inputs: use only tapes with independently checked source
receipts. No qualified SNN claim is made from an unaudited tape.

Attach one variant's states through the recording config's `snnStates` array or
direct `RecordedDecision.snn`. The latest state must already have arrived and be
within 2s of the decision; otherwise that SNN context is unavailable. The base
TA/contract models can operate with no SNN. A suppressed SNN has zero influence
and is not required for the reduced model's queries.

Run separate studies with S5 and S6 attached, preserving the same base frames,
terms, quotes, index evidence, labels and period plan. Then:

```sh
npm run research:opportunity-product -- compare-snn \
  --s5-product research/out/atlas-s5-study/product.json \
  --s5-dataset research/out/atlas-s5-dataset \
  --s6-product research/out/atlas-s6-study/product.json \
  --s6-dataset research/out/atlas-s6-dataset \
  --out research/out/atlas-snn-comparison-v1
```

The comparison uses identical supported audit queries and compares both variants
with a simpler baseline. S6 must add predictive and fee-net value beyond S5 to
justify plasticity. Unsupported evidence cannot qualify either variant. This
checks SNN contribution to the Atlas; it does not rewrite or prune cortical
weights, or mistake the existing governor for validated selective memory.

## Study and retention

```sh
npm run research:opportunity-product -- study \
  --dataset research/out/atlas-contract-dataset-v1 \
  --plan research/opportunity/examples/prospective-study-plan.json \
  --policy research/opportunity/examples/paper-policy.json \
  --out research/out/atlas-contract-study-v1
```

The approved `prospective-2026-11-09-v1` study fits before October 29, 2026, uses
distinct stopping, beta calibration, family/group selection and independent audit
roles before November 9, and withholds outcomes from November 9 onward. Its
example plan has too few independent weeks to qualify a model. Use the matching
`prospective-recording-import.json` or `prospective-prefix-import.json` when
building its input dataset. The older `frozen-study-plan.json` remains a separate
pre-2025/2025/frozen-2026 study; its results cannot be relabeled as prospective.
A row's full planned contract span and actual label availability must
fit its role. All snapshots of an asset/index/settlement event share one unit of
weight; dense sampling or more ladder strikes cannot manufacture independent
evidence. Training-only variable selection preserves interaction-only inputs.
Normalization and hyperparameters never read selection/audit columns or labels.

Family selection uses common supported selection rows. Full-parent leave-one-
family-out comparisons test TA, SNN, dominance, clock, micro/cross-asset and daily
context. Paired fixed UTC seven-day blocks and a joint Holm correction cover
predictive and fee-net tests, counting all three possible selected parent families.
Unsupported families have zero influence in a new
reduced fit; their parent/ablation evidence remains in the retention ledger for
later reconsideration. This is reversible consolidation of the Atlas's feature
influence, not deletion of its source memories. Hyperparameter searching beyond
these fixed candidates requires registering additional trials/validation periods.

The final reduced model is locked before its audit. Audit qualification compares
it with the simpler geometry baseline on at least eight weekly blocks, requires
positive predictive and fee-net lower bootstrap bounds and controlled one-sided
tests, enough observed quotes and confirmed settlement events, and sufficient
calibration coverage. Week bootstrap/sign-flip evidence assumes suitably
independent/exchangeable blocks; regime changes can invalidate it. A weak study
exports its reasons and abstains. No artifact auto-promotes a bot model.

Independent audit calibration groups use fixed probability deciles per supported
contract/event geometry. Hoeffding bands over weekly group frequencies include
a simultaneous correction across the predeclared groups/components and two SNN variants. These are
bands for average frequency under independent, stable week groups, **not** a
guarantee about each individual conditional probability. Fewer than eight weeks
or 50 events in the queried group yields `[0, 1]` and no calibration reference.
The conservative width can require substantially more history to support high
confidence. The separate conditional movement mixture returns expected terminal,
favorable/adverse bps and empirical terminal quantiles from training analogs.
Those quantiles describe path dispersion and have no movement calibration claim.

## Query and manage paper positions

```sh
npm run research:opportunity-product -- query \
  --product research/out/atlas-contract-study-v1/product.json \
  --observation research/out/current-observation.json
npm run research:opportunity-product -- shadow \
  --product research/out/atlas-contract-study-v1/product.json \
  --requests research/out/paper-requests.jsonl \
  --policy research/opportunity/examples/paper-policy.json \
  --out research/out/atlas-paper-shadow-v1
```

Each request contains an observation, fresh quote or null, caller-reported
position or null, and caller-approved quantity/risk-dollar allowances. The schema
is `PaperRequest` in `productCli.ts`. Shadow output logs the immutable observation
ID, artifact/model version, forecasts, uncertainty basis, quote, position and
entry/hold/reduce/exit recommendation. Recommendations are not fills; the logger
does not invent an inventory or realized P&L from them.

The registry requires a named content-addressed product. It verifies model,
study, calibration and movement IDs, source/schema/SNN compatibility, trained
geometry coverage, availability and calibration freshness. A model cannot be
selected because it returns the highest confidence. `forward-paper` requires
actual artifact publication before the query; `--historical-audit` explicitly
uses the simulated audit cutoff and makes no historical-publication claim.
Forward shadow logging additionally requires capture within five seconds of the
request and publication before expiry. Each row records its wall-clock capture
time and mode; retrospective requests cannot be published as a forward trial.

A selected input that was always observed during training cannot become silently
missing at query time. The registry abstains for that unseen missingness pattern;
mean imputation alone cannot create confidence for an unavailable relationship.
The execution buffer is part of exact target support, and frame age must remain
inside its training range. A model fitted on current frames cannot silently accept
an older snapshot or a different movement deadline. Refit earlier artifacts with
the current support metadata before querying them with the updated registry.

An hourly direction forecast stays context for a 15m contract. The fresh query
must match this ticker, strike/range, side, index, averaging rule, direction,
event definition and exact remaining-time deadline. Neither a nominal TA
timeframe nor a stale forecast's countdown can substitute for that question.

Paper entry requires exact timing support, a qualified calibration reference,
fee-net lower edge, quote depth and the caller's risk allowance. For an open
position, hold value is the future expected payout net of settlement cost;
liquidation value is the current bid net of exit cost. Entry cost is sunk in
that comparison. Reductions respect visible bid size and a zero allowance can
require reduction even with no forecast. Missing forecasts/quotes abstain and
leave existing external risk controls responsible for the position. There is
no route around the risk gateway or into an order client.

## Current data and release readiness

Drive's `raw/laptop-history` namespace contains the older minute archive, with
BTC/ETH starting August 17, 2017, and all five assets extending through October
12, 2026. The derived archive contains 21,070,767 valid minute rows. Each of
BTC/ETH has 21,602 off-grid rows that are retained unchanged in the raw archive
and excluded without time shifting in the derived copy. Hashes establish which
bytes were used, not independent provider authentication. Gaps remain gaps.
Stored Yahoo daily context, TradingView BTC.D/USDT.D and four funding series are
available; absent/stale features remain null. Funding uses an explicit 60-second
publication assumption, not a verified exchange publication timestamp.

GitHub run `42538058087` exported 14,618 sparse causal decision frames and 192,932
path labels and fitted eight purged multi-era folds. The initial tree candidate
did not reliably beat the simpler geometry baseline. The smooth comparison is
an exploratory development study on the exact same exported dataset. Neither
result establishes official-contract or economic qualification.

The October 21 recording prefix contained 32,570 official Kalshi index messages,
native Coinbase candle arrays, recorded strikes and 15m/hourly contracts. That
probe sampled books and is diagnostic. The separate bounded engineering study
keeps every public book snapshot/delta within selected prefixes, rejects proxy/
synthetic inputs, and checks hashes before SNN replay. Full original days, venue
fills and upstream websocket gap fidelity remain unverified.

All heavy data processing and fitting run on GitHub, without contacting Lightsail:

```sh
gh workflow run atlas-research.yml --ref main \
  -f dataset_run=42538058087 -f study_policy=prospective-2026-11-09-v1
gh workflow run atlas-recordings.yml --ref main -f expand_training=true
# Reuse all six public-prefix artifacts when investigating a later processing step:
gh workflow run atlas-recordings.yml --ref main -f source_run=42543176283
# Add two fixed pre-cutoff days while reusing the original six prefixes:
gh workflow run atlas-recordings.yml --ref main -f source_run=42543176283 -f expand_training=true
# After a complete replay, reuse its checked datasets for a model-only refit:
gh workflow run atlas-recordings.yml --ref main -f study_run=COMPLETED_RECORDING_RUN
```

The first command reuses a checked `atlas-history-study` artifact for the fixed
smooth/tree comparison. Artifacts have finite retention; after expiry create a
fresh export with `diagnose.yml`'s explicit Atlas archive options and provide its
run ID. The second reads fixed bounded prefixes from existing Drive recordings,
fits exact-contract candidates and compares S5/S6 on identical observations. Its
short sample cannot satisfy the eight-week evidence gates. Outputs are research
artifacts, never production model files. No source secrets enter those artifacts.
The prefix-specific plan audits November 6 and uses November 7 for explicitly
retrospective post-audit paper queries. Those queries are not prospective paper
observations, regardless of whether a model would have entered.

The initial six-prefix run, `42549662484`, completed with 3,876 complete base
outcomes and 3,804 matched SNN outcomes per variant. It has only 19 distinct
training settlement events, below the learner's fixed 20-event minimum, so its
contract heads remain fallback priors. All 1,080 historical paper queries abstain;
the one-week audit has no executable quote or confirmed-result evidence.
`expand_training=true` adds fixed October 24 and 27 archive prefixes before the
October 29 training cutoff. It preserves the model parameters, selection/audit
windows and November 9 final boundary. With `source_run`, only the two additional
prefixes are copied; if either fails, the study cannot silently use the old six.
This extends development coverage and cannot establish independent qualification.

The expanded run `42568366333` completed on the same tested source with all three
contract heads fitted. It processed 140,129,400 events across 19.99 observed hours,
producing 5,340 complete base outcomes (201 distinct asset/settlement events) and
5,244 complete outcomes per matched SNN variant. The base has 66 distinct training
events; the SNN variants have 64. The selected tree models retain no indicator/SNN
family because evidence remains insufficient. Their audit spans one week with two
confirmed events and zero executable quotes; a conditional calibration head also
remains unsupported. All 1,080 retrospective paper queries abstain.

Download the checked artifact to inspect the real fitted product without another
archive copy or fit:

```sh
gh run download 42568366333 --name atlas-recording-study --dir research/out/atlas-observed-42568366333
npm run research:opportunity-product -- status --product research/out/atlas-observed-42568366333/base/study/product.json
```

The artifact expires on February 7, 2027. After prefix-cache expiry, omit
`source_run` and keep `expand_training=true` to copy all eight fixed archived
prefixes on GitHub. Source/model/dataset hashes, actual fitted head types and
current-code validation are recorded in `OPPORTUNITY_ATLAS_PRODUCT_VALIDATION.json`.

The owner authorized the separate prospective study and main merges. Use a merge
commit subject containing `[skip deploy]`; deployment and automatic trainer
publishing skip that push. Windows package smoke checks use a local synthetic ZIP
and exclude history downloads; fresh Atlas acquisition stays tvdatafeed-only.
Deployment/live enablement still require approval. Models stay paper-only, and
unsupported queries abstain. New holdout observations must follow real artifact
publication; no retrospective prediction may be counted as a forward result.
