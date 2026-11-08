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
