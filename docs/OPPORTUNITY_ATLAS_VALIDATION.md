# Opportunity Atlas local validation

Branch: `feature/conditional-opportunity-atlas`, based on
`ef26c3679040b41c7b554e30cf44b350c049dc2e`. This validates research code, not
trading eligibility. No bot consumers, promotion hooks or deployment were added.

## Automated checks

The two focused files are `tests/opportunityAtlas.test.ts` and
`tests/opportunityPaths.test.ts`. They cover 28 cases including direct future-window
comparisons, both sides and all configured grids/horizons, same-bar ambiguity,
gap opens, costs on both legs, failed/confirmed turn runs, prefix immutability,
causal lookbacks, split purging, censoring, invalid inputs, CLI cleanup and a check
that enabling path export preserves the Phase 1 fits and scores exactly.

```bash
node --import tsx --test tests/opportunityAtlas.test.ts tests/opportunityPaths.test.ts
npm run typecheck
npm run build
```

The completed `npm run check` run passed **1,142 tests**, with zero failures,
zero cancellations and zero skips, including all 28 focused atlas tests.
Typecheck and the production build also passed. These results are local validation;
GitHub CI, deployment and model promotion were not invoked.

## Synthetic dataset export

A 5,000-minute stream with all default grids produced 43,200 label rows for 300
decisions: 144 combinations per decision, 2,862 censored rows and 4,878 purged
rows. The run took about three seconds and peaked around 145 MB RSS on this
machine. JSONL output was 68.8 MiB; neither time nor RSS is a scaling guarantee.
Output must be budgeted before exporting years of dense grid combinations.

## Observed BTC and ETH sample

The existing Binance downloader fetched the August 2017 BTCUSDT and ETHUSDT
one-minute spot archives from `data.binance.vision`. Each archive was verified
against its required published SHA-256 checksum before use. Source URLs, hashes
and downloader summaries are retained locally at
`data/atlas-history-sample/sample-provenance.json` (ignored, not committed).

Each asset contains 21,360 contiguous candles from 2017-08-17 04:00 UTC through
2017-08-31 23:59 UTC, with zero malformed rows and zero time gaps. No dominance
history was supplied for this sample; the dominance fit remains empty.

```bash
npm run research:opportunity-atlas -- --history data/atlas-history-sample \
  --source binance-1m --assets BTC,ETH --max-minutes 400000 \
  --train-before 2017-08-22 --final-from 2017-08-27 \
  --out /tmp/atlas-real-report.json --path-labels /tmp/atlas-real-paths.jsonl \
  --path-targets-atr 1 --path-stops-atr 1 \
  --path-fee-bps 4 --path-half-spread-bps 1 --path-slippage-bps 2
```

This produced 44,512 rows from 1,391 decisions per asset: 640 end-of-input
censored rows, 1,216 purged rows and 14 ambiguous first-hit cases. All horizons
had train/development/final observations. An independent scan of the original CSV
candles also matched target/stop times and MFE/MAE for 170 sampled completed rows.
None of the Phase 1 relationships was
retained; this sample does not meet the required independent-week evidence.
Assumed costs are illustrative and are not measurements of fees or fills.

## Still unverified

The sample does not validate historical predictive skill, calibration, profitability,
execution fidelity, independent episode counts or regime stability. The existing
Drive archive is not authenticated to this workspace. Its longer minute-history
coverage remains uninspected. A later tvdatafeed acquisition (below) has now supplied
actual dominance history independently of Drive. No validation claim extends to the
unimplemented full feature provider, path prediction heads, SNN integration, or
model selection/promotion stages.


## Tvdatafeed acquisition increment

All acquisition in this increment used tvdatafeed 2.1.0 from the pinned upstream
commit `e6f6aaa7de439ac6e454d9b26d2760ded8dc4923`. The isolated Python environment
was installed with TLS verification retained. No exchange downloader, venue fallback,
TradingView login, deployment or trading consumer was used.

The real no-login bridge fetched `COINBASE:BTCUSD` and `COINBASE:ETHUSD` at one-minute
resolution and daily `CRYPTOCAP:BTC.D` / `CRYPTOCAP:USDT.D`. It discarded forming
candles. The merged minute cache contained 5,004 bars per asset from
2026-11-04 18:15 UTC through the close at 2026-11-08 05:39 UTC. Actual daily coverage
began at 2014-04-01 for BTC.D and 2015-03-08 for USDT.D. Receipts, hashes and coverage
reports are retained in the ignored `data/opportunity-history/` directory.

A request for the August 2017 minute span correctly exited 1 with 21,360 missing
minutes per asset; it did not relabel the recent bars as historical coverage. A
subsequent recent-window request encountered intermittent no-data responses. Reusing
`deploy/tv_history.py`'s existing bounded two-attempt helper resolved the request;
all four required series then had zero missing bars in the requested window.
Raw receipts and per-run coverage snapshots distinguish requests from
actual availability. The original 2017 coverage result was also saved at
`/tmp/atlas-tv-2017-coverage.json` before refreshing the latest report.

The real imported tvdatafeed store was exercised with the atlas CLI, using
`--train-before 2026-11-06T04:15:00Z --final-from 2026-11-07T04:15:00Z` solely for
a recent-window data-flow smoke test. Both assets had observations in all three
partitions at all eight horizons, populated daily-dominance fits, zero time gaps
and zero malformed rows. The export produced 9,600 path rows, with 636 censored
and 1,216 purged rows. No relationships were retained on this short sample. This
is not a historical backtest, a replacement research split plan, or predictive
validation; do not use these diagnostic cut dates to recycle a frozen final holdout.

The focused atlas/provider tests plus adjacent history, index-series and session-clock
suites passed **62 tests**, zero failures/skips. The tests include mocked transport
cases for outages/coverage/provenance as well as a direct Python-bridge test; they are
separate from the real network request described above. The previous 1,142-test full
run applies to the earlier path-label increment; it was not rerun for this provider
increment. Current typecheck and production build also passed.

Earlier minute history still requires an accumulated tvdatafeed archive. A fresh
5,000-bar request cannot reconstruct the 2017 minute study. The real daily download
removes the missing-dominance prerequisite for that era, but does not supply the
missing historical price minutes.


## Read-only Lightsail archive inventory

The owner confirmed GitHub Actions as the existing server access route. A new
`atlas_inventory=true` mode on the feature branch's existing `Server diagnostics`
workflow succeeded in run 42480623621:
https://github.com/Wickedrad/coinbaseTraderBot/actions/runs/42480623621

Only `atlas-inventory` ran; `diagnose`, `adversary`, `kalshi-repair` and `ta-study`
were all skipped. The script was sent on SSH stdin, ran at low priority, sampled
at most 16 KiB from each CSV end, and did not copy scripts to the server or change
bot files, services, configuration, models or orders. Credentials stayed on the
GitHub runner. The workflow passed actionlint 1.7.12 (official archive SHA-256
verified). The atlas/inventory tests passed 45 cases with zero skips/failures;
current typecheck passed. This is not another full-suite or deployment claim.

Scope: canonical `~/bot/data/history/<source>/<asset>/<timeframe>.csv`, plus
recognized raw exports immediately under `~/bot/data/incoming/tradingview`.
The root existed, discovery was not truncated, and 73 CSV files matched:

| Stored source | Timeframes and counts |
| --- | --- |
| tradingview | 9 daily, 9 four-hour, 8 hourly |
| tvspot | 5 daily, 20 four-hour, 20 hourly, 2 fifteen-minute |

No one-minute CSVs were found in these locations, including no tvdatafeed minute
candidates. This does not prove that no other server folder or external archive
contains minutes. Relevant observed timestamp spans (open times, UTC) included:

| Series | First | Last |
| --- | --- | --- |
| BTC.D daily | 2014-04-01 | 2026-10-07 |
| USDT.D daily | 2015-03-08 | 2026-10-07 |
| BTC hourly | 2026-03-30 | 2026-10-24 12:00 |
| BTC four-hour | 2024-07-12 04:00 | 2026-10-25 12:00 |
| ETH daily | 2016-05-23 | 2026-10-30 |
| ETH hourly | 2026-03-30 | 2026-10-24 12:00 |
| ETH four-hour | 2024-07-12 04:00 | 2026-10-25 12:00 |

These are bounded header/tail metadata observations, not full candle validation or
cryptographic provider verification. Directory names and optional sidecar declarations
are explicitly treated as source evidence, not verified provenance. None of the
server data was fitted or promoted. Coarser bars cannot be expanded into genuine
historical one-minute observations for the 2017 atlas study.

The full inventory metadata is retained in the run's `atlas-archive-inventory`
artifact (seven-day retention) and locally at
`/workspace/scratch/atlas-inventory-42480623621/atlas-archive-inventory.json`.


## Read-only Google Drive inventory through GitHub Actions

Run 42481866272 succeeded using the existing `RCLONE_CONF` binding entirely on the
GitHub runner:
https://github.com/Wickedrad/coinbaseTraderBot/actions/runs/42481866272

The configured `gdrive:kalshi-bot-archive` and the owner's explicitly linked folder
`14aszEScwaC7yGPqGXZ17SoZ8sBTPPs-J` were both accessible. Each listing returned the
same 77 history-file metadata entries in the checked namespaces, with no listing
errors or truncation. These are two access routes to matching inventory, not 154
independent files. The checked folders were `raw/history/binance-1m`,
`raw/server-history/tradingview` and `raw/server-history/tvspot`.

- 72 files used TradingView/tvspot directory layouts; no minute-named file was found
  in these namespaces. File naming is evidence, not cryptographic provider verification.
- Five minute CSVs existed under the explicitly non-TV `binance-1m` namespace:
  BTC, ETH, SOL, XRP and DOGE. Only their names/sizes/modification metadata were listed;
  candle date coverage and file contents were not inspected. These files were not
  downloaded or used for training because the owner's tvdatafeed-only requirement
  remains in force.
- Only `atlas-drive-inventory` ran. The SSH inventory and every diagnostics, repair,
  adversary and study job were skipped. There was no Lightsail access, Drive upload,
  data-file download, bot restart, model promotion, main merge or bot deployment.

The workflow passed actionlint; nine inventory/Drive tests and current typecheck
passed. The metadata artifact is `atlas-drive-inventory` (seven-day retention), also
saved locally at
`/workspace/scratch/atlas-drive-inventory-42481866272/atlas-drive-inventory.json`.
The Drive helper uses only `rclone lsjson`, bounds directory discovery, separates
provider evidence, and retains partial listing errors rather than interpreting an
unreadable directory as absent history. OAuth configuration remains on the runner
and is excluded from artifacts/logs. No new credentials were requested.


## Broader archived-source discovery after the Yahoo clarification

The owner noted that some existing history came from Yahoo Finance rather than
tvdatafeed. The read-only inventories were broadened to retain all canonical
server CSV timeframes and known Drive market-history namespaces, including Yahoo.
This changes discovery only; no provider was relabeled, no archived price file was
copied into training, and the acquisition module remains tvdatafeed-only.

- Server run 42482262887 succeeded with only `atlas-inventory` active:
  https://github.com/Wickedrad/coinbaseTraderBot/actions/runs/42482262887
- Drive run 42482260857 succeeded with only `atlas-drive-inventory` active:
  https://github.com/Wickedrad/coinbaseTraderBot/actions/runs/42482260857

The server inventory found 201 canonical CSVs across binance (69), binance-index (1),
bot-index (3), coinbase (50), tradingview (26), tvspot (47) and yahoo (5). Both Drive
access routes found the same 210 metadata entries in their checked namespaces,
including five Yahoo daily files at `raw/server-history/yahoo/<ASSET>/1d.csv`.
Neither inventory was truncated; Drive reported no listing errors. Differences
between the server and its archive are retained rather than assumed away.

Observed Yahoo-labelled server CSV timestamp spans (daily candle opens, UTC):

| Asset | First open | Last open |
| --- | --- | --- |
| BTC | 2016-09-07 | 2026-09-07 |
| ETH | 2017-11-09 | 2026-09-07 |
| XRP | 2017-11-09 | 2026-09-07 |
| DOGE | 2018-09-07 | 2026-09-07 |
| SOL | 2020-04-10 | 2026-09-07 |

These are metadata/header-tail checks, not full content or provider verification.
Daily history can be considered for future long-term context with its source and
known-at semantics preserved, but cannot supply observed one-minute paths. No
training-source policy was silently relaxed. The 51 atlas/inventory tests passed
without skips/failures, as did current typecheck and workflow linting.


## Search for minute history independent of provider

The owner requested a provider-independent search, mentioning possible Coinbase
history. The inventory was extended to inspect actual timestamp spacing, including
generic and nested CSV filenames. Strict ISO and numeric epoch timestamps are
normalized; intervals are measured within each bounded sample, never across the
unsampled middle. Only metadata/dates/counts leave the Actions job, not price rows.

- Lightsail run 42486277606 succeeded and sampled 201 CSVs in the checked history
  store. No 60-second intervals were observed, including among its 50 Coinbase
  files. Coinbase samples showed hourly/daily spacing.
  https://github.com/Wickedrad/coinbaseTraderBot/actions/runs/42486277606
- Drive run 42486274726 succeeded. It listed 210 files in the configured project
  archive and content-probed 63 CSVs before the four-minute budget expired. All five
  minute-named files and all 46 Coinbase CSVs were probed first. There were no sample
  errors. None of the Coinbase samples showed 60-second spacing. The other CSVs and
  linked-folder alias were not content-probed after the budget expired; this is not
  a claim of exhaustive absence outside the checked scope.
  https://github.com/Wickedrad/coinbaseTraderBot/actions/runs/42486274726

The following existing Drive files all had strictly 60-second intervals in their
head and tail samples. Their observed endpoint spans were identical: 2026-04-01
00:00 UTC through the bar opening at 2026-11-06 23:59 UTC.

| Archive path | Size (bytes) | Sampled 60-second intervals |
| --- | ---: | ---: |
| raw/history/binance-1m/BTC/1m.csv | 20,188,864 | 507 |
| raw/history/binance-1m/ETH/1m.csv | 19,532,663 | 530 |
| raw/history/binance-1m/SOL/1m.csv | 17,361,820 | 610 |
| raw/history/binance-1m/XRP/1m.csv | 17,978,393 | 574 |
| raw/history/binance-1m/DOGE/1m.csv | 18,554,354 | 562 |

These are located existing minute archives, stored under the Binance namespace.
This is not cryptographic provider verification, a complete CSV audit, proof of
continuity throughout the unsampled interval, or 2017 minute coverage. No new
exchange data was fetched and no training/model promotion was run. The sampled
archive bytes were read through rclone on the runner; full price CSVs were not
copied to this workspace or included in artifacts. Both runs skipped every
non-inventory job. The 54 atlas/inventory tests passed with no skips/failures;
current typecheck and workflow linting passed. No bot files or service state were
changed and main was not merged.

## Fully copied archive and offline multi-timeframe features

The owner's instruction to continue enabled copying the located existing market
archive for offline work. No new Binance/Yahoo market-data download was performed;
fresh acquisition remains tvdatafeed-only. The original path declarations remain
Binance, Yahoo and TradingView rather than being relabeled as tvdatafeed.

Actions run **42489751110** succeeded with only `atlas-archive-export` active:
https://github.com/Wickedrad/coinbaseTraderBot/actions/runs/42489751110

This exclusive mode uses existing RCLONE_CONF to read five fixed minute paths from
`raw/history` and seven fixed daily paths from `raw/server-history`. Credentials
stay outside the artifact and are removed from runner temporary storage. It does
not connect to Lightsail, run a trainer, modify Drive files or deploy. The artifact
`atlas-history-archive` has seven-day retention; the original files remain on Drive.

**Off since Nov 11, 2026 (8:05 AM EST / 13:05 UTC):** `diagnose.yml` no longer uploads `atlas-history-archive` (this repository is public); the copy stays on the runner and only study results are saved.

The exported archive is local at `data/opportunity-archive-42489751110` (ignored by
Git). `archiveAudit.py` hashes exact bytes and streams every canonical OHLCV row.
The metadata-only [audit](OPPORTUNITY_ATLAS_ARCHIVE_AUDIT.json) is committed.

All five minute files contain **316,800** rows each, for **1,584,000** total:
2026-04-01 00:00 through 2026-11-06 23:59 UTC (candle opens). Each has zero invalid
OHLCV/taker-volume rows, timestamp duplicates/reversals, off-grid opens or gaps.
All seven context files also pass content/order checks. BTC.D has one three-day
gap; the audit preserves it. All twelve downloaded file hashes match the runner
audit. These checks establish content consistency/coverage, not independently
authenticated provider identity or proof of historical publication availability.

The next implementation adds an independent causal feature provider reusing
`tfState`, `tfFeatures`, their TA-Lib keys and the existing clock/session functions.
It supplies six minute-derived timeframes, observed microstructure and separate
daily-source groups with explicit lag/freshness assumptions. No existing bot source
files, live callers, promotion code or training pipeline were changed. See the
architecture document for windows, warmup, missing-volume masks and gap behavior.

The full data-flow validation was:

```bash
npm run research:opportunity-features -- \
  --archive data/opportunity-archive-42489751110 --assets BTC,ETH,SOL,XRP,DOGE \
  --every-minutes 240 --out research/out/opportunity-features-archive-42489751110.json
```

It read all **1,584,000 minutes** and produced availability diagnostics for **6,600
frames**, sampling every four hours rather than computing every default 15-minute
snapshot. It used the native `talib` engine. Every input and code hash was checked
again before publishing the report. The metadata-only
[feature report](OPPORTUNITY_ATLAS_FEATURE_VALIDATION.json) records exact hashes,
parameters, bar counts and per-group status/null counts. Each asset has 1,320 frames
and zero minute gaps. Spot daily TA becomes ready after 30 completed days (1,141
ready frames per asset). Daily Yahoo context is stale in the last 342 frames per
asset; BTC.D and USDT.D are stale in the last 162, with their numeric features null.
No later daily data is backfilled into these periods.

Verification:

- Broader focused run: **90 tests passed**, zero failures/skips, covering Atlas,
  path labels, acquisition, archive inventory/audit, features, sessions, existing
  TA network training/row-cache contracts and native TA-Lib/TradingView behavior.
- Final feature suite after the microstructure provenance adjustment: **8 tests
  passed**, zero failures/skips, including completed daily candles and future-suffix
  poisoning. This includes the additional daily-close test added after the broader
  run started. These two counts overlap and must not be added together.
- Current typecheck, production build, workflow lint and diff whitespace checks passed.
- A real BTC JSONL pilot at the default 15-minute cadence read 1,500 minutes and
  exported 100 frames; every group's known-at time was at or before its decision.
- The previous 1,142-test whole-repository result documented earlier predates these
  archive/feature additions; a fresh whole-repository CI result is not claimed.

This is data/feature validation only. No price-path outcomes were scored, no Atlas
relationships were fitted/selected, and the original **2026 final holdout remains
frozen**. Existing TA regression tests train only their own temporary synthetic
fixtures, not these archived minute prices. Generalized path heads, conditional
selection, SNN integration and economic validation remain pending. Nothing was
merged into main, deployed or enabled for live trading.

## Contract-window timing clarification

The owner required time-to-move forecasts to match each price-prediction contract:
an hourly setup alone cannot justify a 15-minute entry; a later fresh short-window
forecast can make the same evolving setup relevant. `contractTiming.ts` implements
the offline query/assessment contract for the future learner. It uses actual
remaining time, exact strike/index/averaging terms, explicit execution buffer,
current forecast time and continuous timing/settlement/joint probabilities.
It does not substitute a nominal hourly/quarter-hour probability for an exact
deadline or multiply marginal event probabilities. Confidence policies are explicit;
entry price, fees, fill quality, SNN wiring and trained forecast generation remain
outside this helper. `liveEntryAllowed` is always false.

Current verification for this increment:

```bash
node --import tsx --test tests/opportunity*.test.ts tests/fairValue.test.ts
npm run typecheck
```

**86 tests passed**, zero failures/skips, including nine new timing tests. They
cover hourly context versus a quarter-hour question, a fresh later short forecast,
nine minutes remaining in contracts of different nominal lengths, fractional-minute
execution buffers and averaging windows, strike/side/index/proxy mismatches, stale
and future evidence, weak uncertainty bounds, missing calibration metadata and
multiple-model ambiguity. Forecasts and calibration references in these tests are
explicitly synthetic. No learned probability, trading edge or SNN correctness is
established by this fixture. Contract geometry is immutable and stale feature frames
are refused rather than moved forward in time.

The preceding feature commit `3eaddf539a912247ad0ef34e08e9d04f23891daa` also completed
whole-repository GitHub CI: **1,180 tests passed**, zero failures/skips, plus
typecheck and production build. Run:
https://github.com/Wickedrad/coinbaseTraderBot/actions/runs/42491152911
Its CodeQL and Windows packaging checks passed as well. That CI result belongs to
the preceding commit; it does not claim that CI has already rerun the new timing
increment. No live modules, data-source policy, holdout dates or deployments changed.

## Joined minute-decision dataset after merge

The owner merged PR #304 at main `5a53910ca5d517af2f73fe9c8d4ea26bea209bdf` and
authorized continuation. This increment uses a new branch,
`feature/atlas-minute-decision-dataset`. It joins the causal feature exporter to
the existing path labeler at one-minute decisions. Per-entry horizons include exact
minutes remaining to reference quarter-hour/hour boundaries. These are study clocks,
not listed contracts or official settlement labels. Existing Phase 1 callers retain
their original behavior. No bot/TA/SNN, deployment, parameter or pipeline files changed.

Local checks passed:

```bash
node --import tsx --test tests/opportunity*.test.ts tests/fairValue.test.ts
npm run typecheck
npm run build
```

**96 tests passed**, no failures or skips. New coverage includes keyed minute
observations, exact remaining-time labels, sparse-cadence processing of intervening
minutes, separate asset lifecycles, raw ATR warmup/gap reset/precision, variable
horizon schedules, output transaction cleanup, TV provenance requirements, and
selected-source/asset auditing. Final-boundary tests change all later prices and
assert identical exported pre-final targets; they also cover a cut inside a minute.

The preceding timing commit `4af48cc344ee25297b7df565fb64deff321182c8` completed
GitHub CI with **1,189 tests passed**, no failures or skips:
https://github.com/Wickedrad/coinbaseTraderBot/actions/runs/42494828180
That validates the merged base; it is not a completed CI result for this new dataset
increment. The new draft PR will run the repository checks again.

The retained `data/atlas-history-sample` BTC/ETH files were copied locally, without
new provider requests, into an audited study wrapper. Each contains 21,360 valid
minute rows, 2017-08-17 04:00 through 2017-08-31 23:59 UTC. Existing archived Yahoo
and raw TradingView daily context was copied with its identity preserved. This is
a two-asset sample, not a complete five-asset or multi-year minute archive. No claim
of independent provider authentication or historical publication vintages is made.

Three real-data exports succeeded:

| Run | Input | Decisions | Spot-path labels |
| --- | --- | ---: | ---: |
| Retained 2017 BTC/ETH pilot | First 1,500 minutes per asset | 3,000 | 39,240 |
| Archived 2026 BTC final-feature audit | First 60 minutes | 60 | 0 |
| Retained tvdatafeed BTC/ETH final-feature audit | First 40 minutes per asset | 80 | 0 |

The 2017 command used default one-minute cadence, reference periods 15/60 minutes,
base horizons 5/15/60/240/1440, one target/stop ATR pair and explicitly zero assumed
costs. Each asset retained 13 scale-warmup observations and scheduled 1,487 entries.
Each produced 19,620 labels, including 3,520 censored by the processing cap. All
labels belong to the original training period; censored rows are not complete
negative events. This 25-hour pilot does not warm minute-derived 30-day TA; missing
higher-timeframe history remains explicit. Daily source context is joined separately.

An independent Python source scan checked all 3,000 decision timestamps/causal
group metadata, every one of the 39,240 decision/label joins, and both output hashes.
It directly recalculated MFE/MAE, barrier-touch minutes/order, hypothetical exits,
zero-cost payoffs and label known-at timestamps for 128 completed rows across the
source candles. All matched. Across the pilot, labels covered every integer horizon
from one to 60 minutes, plus 240 and 1,440 minutes, without rounding a longer horizon.
The full source/code hashes also matched. These are data/label checks, not prediction
scoring or financial performance evidence.

The 2026 audits marked every observation `reserved-final` and emitted zero future
labels. The TV audit used only the already collected store, preserved its sidecars
and passed the existing identity/content-hash verifier. No fresh acquisition was
needed; future collection remains tvdatafeed-only. No final prices were used for
model fitting, selection or outcome scoring. The reference-window labels remain
spot-price outcomes and do not infer official averaged-index contract payouts.

Metadata-only evidence, including all three manifests and the independent-check
summary, is committed in
[OPPORTUNITY_ATLAS_DECISION_VALIDATION.json](OPPORTUNITY_ATLAS_DECISION_VALIDATION.json).
Raw datasets remain ignored under `research/out/`. The bundles have distinct keyed
decision/path schemas, input/output hashes, code hashes and transactional publication.
No SNN embeddings were fabricated, and the SNN input/output wiring is still unchanged.
The next stages are the joint horizon-conditioned learner, calibration/validation,
causal SNN state integration and official-index contract labels. This increment
does not assert that the complete intelligent trading system is ready.

## Initial joint path learner after merge

The owner merged PR #305 at `5ad1c74a076cd0b60bd78c0a29a99481a173e037` and asked
to continue. Work on `feature/atlas-joint-path-learner` adds a dataset reader,
competing-risk tree learner, purged internal walk-forward study, conditional
calibration and read-only integer-minute forecast queries. Existing tree training,
tree inference and calibration implementations are reused; no bot/SNN/parameter,
deployment or existing training-pipeline files changed.

Current local verification:

```bash
node --import tsx --test tests/opportunity*.test.ts tests/treesFill.test.ts tests/relaxed.test.ts tests/model.test.ts
npm run typecheck
npm run build
```

**140 tests passed**, zero failures/skips, including ten new joint-learner tests.
Coverage includes planted conditional learning, coherent nested cause curves,
serialized prediction parity, model corruption/cycles, chronological stage and
full-span purging, right censoring without fake survival, hash/join validation,
future-column/schema rejection, exact reconstruction of interned inputs, and final
label refusal after forged metadata hashes. Changing evaluation labels/columns
leaves the fitted model and calibrator unchanged. The original 2025 development
period and 2026 final period are excluded from internal fitting by timestamps,
independently of input partition claims.

Three real-data commands completed using the already exported datasets:

```bash
npm run research:opportunity-joint -- \
  --dataset research/out/opportunity-decisions-2017-v1 \
  --out research/out/opportunity-joint-2017-smoke-v2 --smoke-test --trees 16 --depth 2
npm run research:opportunity-joint -- \
  --dataset research/out/opportunity-decisions-2017-v1 \
  --out research/out/opportunity-joint-2017-default-v2
npm run research:opportunity-joint -- \
  --dataset research/out/opportunity-decisions-final-audit-v1 \
  --out research/out/opportunity-joint-final-refusal-v2 --smoke-test
```

The 2017 smoke run fitted one joint/geometry model pair from 1,384 training
entry/side/grid episodes (11,208 at-risk minutes), with 476 completed evaluation
episodes. It used 633 training-varying encoded inputs, a maximum risk horizon of
60 minutes, and four supported BTC/ETH long/short one-ATR grid combinations.
Fitting/stopping/calibration/evaluation windows and one-hour embargoes all remained
inside the original 2017 training period. Censoring contributes only observed risk
prefixes; alternate horizons do not multiply episodes.

Internal smoke multiclass log loss was 0.78337 versus 0.82028 for the geometry
baseline; multiclass Brier was 0.52737. These values are plumbing diagnostics from
one short interval, not financial performance or robust skill evidence. Two of the
three conditional calibration heads remain `insufficient` (event and ambiguity);
only the clear target/stop head accepted its conditional fit. There is one weekly
evaluation block, so the block confidence summary is null. The short sample also
cannot warm the complete long-timeframe vocabulary during fitting. No global
calibration approval, feature-retention decision, SNN competence or trading edge is
established by this run.

The normal study correctly reported `blocked-insufficient-history-or-rows` on the
25-hour pilot. Its default multi-day windows were not silently shortened. The
2026-only dataset also produced the blocked report, with no fitted model artifact
and no encoded final input features. No final outcome label was read or scored.

Saved-model checks then generated 72 forecasts from twelve actual BTC/ETH decision
frames (both sides, horizons 1/9/60 minutes). Every probability was finite, within
0..1, and normalized; first-hit cumulative probabilities increased with horizon
while no-hit survival decreased. One- and nine-minute queries exactly matched the
corresponding prefixes of the 60-minute curve. Artifact content ID/hash and current
source hashes matched. Model availability is a simulated replay cutoff, not proof
of a historically published model or real execution latency.

All artifacts retain `researchOnly: true`, `liveEntryAllowed: false` and
`calibrationRef: null`. The order-ambiguity range is not a statistical confidence
interval, and these spot barrier probabilities are not official averaged-index
contract settlement or reversal/terminal-price forecasts. The new learner has no
live consumers or promotion route.

Metadata-only reports and inference checks are committed in
[OPPORTUNITY_ATLAS_JOINT_VALIDATION.json](OPPORTUNITY_ATLAS_JOINT_VALIDATION.json).
Weights/raw study files remain ignored under `research/out/`. New collection remains
tvdatafeed-only; this increment made no provider data requests. Smooth-surface/SNN
comparisons, causal SNN integration, full-parent conditional selection, multi-era
calibration, official settlement labels and economic validation remain pending.
