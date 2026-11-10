# Verifying the edge taught by the Oracle

The new forward trial uses the saved Oracle response tables and learned importance directly. It does not substitute the small recorded-input MLP study, refit weights, or use settlement wins as the profit target. All capture, paper execution and evaluation runs on GitHub; Lightsail and live trading remain untouched.

## What is locked

The full-history tables come from run `42643723640`, and importance from `42667008829`. Their metadata identities, binary hashes, layouts, vocabulary and training cutoff are checked before prediction. Forecasts include the model identity, actual publication time, feature origin, acquisition time, exact future target, probabilities, missing axes and active curve count. Each forecast is fsynced and printed to the public Actions log before any subsequent book is consumed.

Fresh minute history comes only from **tvdatafeed**, requesting `BINANCE:*USDT` and the existing daily dominance symbols. This is an explicit provider-transfer study from the original archived Binance candles. No source is relabeled. The 5,000-bar limit does not warm every daily or 4-hour indicator; unsupported axes and their curves stay unavailable. Revisions to used closed OHLC quarantine the affected asset. No missing minute or intraminute path is invented.

The price target is anchored at the last completed minute, exactly as in Oracle training. Actual publication lag shortens the remaining lead and is recorded. Future labels use the exact later minute close. Terminal up/sideways/down probabilities are scored against that original target. An additional path analysis checks which direction first confirms a sustained move on two closed minutes after publication. A later terminal reversal cannot erase an early correct direction in this path diagnostic. Missing paths remain unavailable; no-move cases are retained as misses for both rankings. These minute labels cannot certify intraminute reversal onset.

Those future closes establish sustained support relative to the feature anchor; they cannot prove the move began after publication within that minute. Paper P/L instead begins at the actual observed entry ask after publication. The two claims remain separate.

## Contracts and the $200 accounts

A 15-minute forecast can open a paper position only when its target fits before the contract's sale deadline. This trial uses monotone hourly threshold contracts for those entries. The one-hour forecast remains a price forecast; a shorter active contract cannot borrow that horizon. Active 15-minute contracts require a trained shorter-window forecast and are not admitted by pretending the saved 15-minute horizon is shorter.

Seven predeclared accounts each begin with $200: learned importance, uniform curves, historical class prior, reversed learned ranking, always up, always down and seeded random direction. They receive the same observed books and risk limits: $20 including fees per position, 40 contracts per position and five simultaneous positions. The primary is the learned-importance account, fixed before outcomes. Direction ranking is studied without an arbitrary 60% admission cutoff; the full three-class probabilities remain visible.

The native paper exchange buys at observed asks and sells at observed bids with actual displayed depth and the native rounded fee formula. A positive net take can be as small as one cent. Credits accumulate through the existing hourly pacer; $4.50 is not required from an individual trade. Positions are sold at the sale deadline, including losses, if executable depth exists. Contracts expiring after the capture ends cannot open new positions. Missing exits remain funded and unresolved; no settlement payout or bankroll refill is assumed.

Public series fee types, scheduled changes and event overrides are captured. The maintained published schedule is used, and a current PDF refresh is attempted. If its endpoint does not refresh, the rates remain explicitly marked as cached assumptions. This does not stop direction measurement, but it prevents a claim that every fee term was freshly verified.

## How the assessment decides

The assessment independently reconstructs each outcome from the first-observed raw tvdatafeed receipts and rejects missing, duplicated or inconsistent outcome records. It checks every fill against same-arrival book depth, recomputes fees and the entire cash/basis ledger, and reconciles the saved account. It then applies a fixed-fill sensitivity of one cent adverse price on both entry and exit, with fees recalculated at those prices. This is cost stress, not invented fills at a new price.

Early sustained-direction ranking gain is compared with the frozen prior. Terminal-close log loss and calibration are separate diagnostics. Overlapping minute predictions are not treated as independent: the first forecast per asset in each UTC-hour group is selected by time, and a group is omitted from inference if its target interval overlaps the preceding selected group. Assets in the same interval stay grouped. Forecast and outcome counts remain fully reported.

The registered research acceptance requires at least 20 non-overlapping, same-protocol forward trials, adequate non-overlapping direction groups, a positive grouped direction-gain bound, positive stressed paper returns and positive paired stressed gain over **every** fixed control. Failed trials, unresolved positions and unverified traded fee terms block qualification. Use the complete preregistered cohort; choosing winning run IDs invalidates the inference. Each trial is a separate fixed $200 experiment, not a refill of a single account. Bootstrap intervals are approximate and market-specific. Even a supported paper edge does not prove private venue fills and never auto-promotes a live model.

## Commands

The initial run's forecast engine and primary account were committed before launch. Its sustained-direction/stressed-profit assessment criteria were committed at `2026-11-10T02:20:51Z` (`9b8330b`), during collection but before the first 15-minute target matured and before any outcome review. Keep that timing distinction in the evidence record. Subsequent trials on this source lock both the engine and assessment before collection.

Start a short source/protocol probe (it cannot qualify as edge evidence):

```sh
gh workflow run atlas-recordings.yml --ref main -f oracle_edge=true -f edge_cycles=2
```

Start a locked trial long enough to observe both horizons:

```sh
gh workflow run atlas-recordings.yml --ref main -f oracle_edge=true -f edge_cycles=72
```

Choose the collection duration before launch. Contract close must fall at least one minute before the planned collection end, and the forecast must fit before close minus 30 seconds. A 72-minute run started late in the hour can have no eligible entries. Use a separately registered 90-minute protocol when needed to include the following hourly close; never pool trials with different durations or implementations.

The run produces `atlas-oracle-edge` with registration, forecast publications, raw tvdatafeed receipts, books, fee evidence, outcomes, fills and account reports. Current workflow versions automatically assess locked trials. A short probe has no matured 15-minute or one-hour outcomes.

Assess completed locked trial artifacts without recollecting or refitting:

```sh
gh workflow run atlas-recordings.yml --ref main -f oracle_edge=true -f source_run=RUN_ID
```

For a complete same-protocol cohort, supply its run IDs separated by commas. The evaluator rejects changed models, policies, implementation, overlapping trial periods, changed artifacts and backdated forecasts. The assessment artifact is `atlas-oracle-edge-assessment`.

## First forward result

GitHub run [42740737188](https://github.com/Wickedrad/coinbaseTraderBot/actions/runs/42740737188) published **720 forecasts** from the frozen tables and importance. All 72 tvdatafeed acquisitions succeeded, with no used OHLC revisions; all five assets produced both forecasts each cycle. It captured 2,996 books, 2,995 nonempty: 618 were two-sided and 2,377 had asks only. The exact later closes graded 285 fifteen-minute and 60 one-hour forecasts. Another 365 remained pending and ten target closes were outside the last acquired prices; no outcomes were invented.

The first-sustained-direction hit rate was **48.1% versus 41.4% for the prior** at 15 minutes, and **21.7% versus 41.7%** at one hour. These are descriptive rates across heavily overlapping forecasts. Only two and one non-overlapping UTC-hour groups were available, respectively. The grouped 15-minute gain was zero. This does not establish reliable direction gain.

Every account began with $200. The ledger was independently reconciled to the observed books and native fees:

| Account | Ending cash | Realized sale net | Unresolved positions | Stressed cash change |
| --- | ---: | ---: | ---: | ---: |
| Learned importance | $188.35 | +$0.07 | 4 | −$13.12 |
| Uniform curves | $188.35 | +$0.07 | 4 | −$13.12 |
| Historical prior | $188.35 | +$0.07 | 4 | −$13.12 |
| Reversed learned ranking | $201.28 | +$1.28 | 0 | −$1.70 |
| Always up | $188.35 | +$0.07 | 4 | −$13.12 |
| Always down | $201.28 | +$1.28 | 0 | −$1.70 |
| Seeded random | $189.22 | +$0.53 | 4 | −$14.37 |

Cash excludes funded unresolved exposure; its change is **not** a fully realized account return. No exit or settlement payout is imputed. The learned account made one positive sale, paid $0.90 total fees and retained $11.72 of unresolved entry basis. Its behavior matched the prior/uniform/up controls during eligible entries. No account reached the hourly goal. Fees remained cached-rate assumptions. The assessment verdict is **`edge-not-established`**; there is no promotion.

The original collector selected from only the first 100 open markets. That page mixed hourly and later contracts and omitted nearer strikes; BTC's first selected strike was $82,899.99 against a $74,960 feature anchor. This is an execution-study limitation, not proof about the unobserved nearer contracts. The final source filters the close window, reads every page, saves listing receipts and refuses partial selections. A separate short engineering probe verifies that correction; its outcomes cannot be pooled with the original trial. Implementation hashes enforce that separation. The frozen Oracle tables and importance are unchanged.

The corrected probe, run [42749966754](https://github.com/Wickedrad/coinbaseTraderBot/actions/runs/42749966754), published 20 forecasts and captured **99 two-sided books out of 99**, with no acquisition, request, revision or listing failures. It saved 20 market-page receipts. BTC's selected strike was $74,599.99 against a $74,649.37 anchor. BTC, ETH, SOL and XRP had eligible hourly terms; DOGE had none and remained price-only. The two-minute probe has no matured horizon outcomes or eligible entries and is explicitly excluded from edge qualification.

Input coverage was partial: BTC/ETH/SOL/XRP used 23 axes and 276 curves each; DOGE used 20 axes and 210 curves. The missing higher-timeframe inputs remain unavailable. One flat return also exposed JavaScript negative-zero serialization in the independent check. The checker now compares JSON representations, with a regression case, and reproduces the unchanged first-trial results.

Exact source IDs, artifact hashes, assessment, fee assumptions and software checks are recorded in [the validation record](OPPORTUNITY_ATLAS_ORACLE_EDGE_VALIDATION.json). The first result supplies neither qualified native SNN evidence nor a verified tradable edge.

Final source `99bfcae4dbd4787de6ba2209a136f0b5c7de9af7` passed GitHub CI [42749913829](https://github.com/Wickedrad/coinbaseTraderBot/actions/runs/42749913829): **1,321 tests, zero failures/skips**, TypeScript and production build. All four CodeQL languages, 21 focused local tests and workflow lint passed. Final-source assessment [42750390525](https://github.com/Wickedrad/coinbaseTraderBot/actions/runs/42750390525) successfully reproduces the unchanged first-trial result. The closing evidence update changes documentation only.

Production provenance: concurrent PR #298 merged and deployed `c630fa8` during this work, and published trainer release `439913306`, before PR #311 merged. PR #311 used `[skip deploy] [skip ci]` and performed neither action. Final CI tested merge `d3b08e0` against that concurrent main revision; all executable files in the Oracle merge match that tested tree. The initial November 8 production baseline must not be interpreted as the global state at completion.

The corrected separate **90-minute** forward trial is [42751926270](https://github.com/Wickedrad/coinbaseTraderBot/actions/runs/42751926270), launched on merged source `9703627`. It was still running when this record was updated. Its predictions, outcomes and paper accounts will be assessed automatically; no result or edge is claimed in advance.

## Fifteen-second executable-profit labels

`profitWindowStudy` in the assessment now exports paired up/down opportunity labels for each published forecast using the first eligible two-sided contract book, $20 maximum entry cost, at most 40 contracts, and the existing native fees. An exit must have enough displayed best-price depth for the entire hypothetical entry and at least $0.01 net after entry and exit fees. Four nominal five-second observations spanning at least 15 seconds can confirm an observed window; gaps over 7.5 seconds break confirmation. This sampled support is not proof of uninterrupted liquidity or an actual fill. A later reversal does not erase an observed window. The bot need not wait 15 seconds before selling.

The label deadline is the earlier of the forecast horizon and the exact contract close minus 30 seconds. It records the actual remaining window, including shorter active contracts, without reinterpreting terminal Oracle probabilities as short-window confidence or changing the funded accounts' entry rules. Both directions, missing entries, pending targets and incomplete coverage are retained. These overlapping counterfactual labels must not be summed as $200 portfolio profit. They form a separate training target; no newly trained or calibrated profit-window model is claimed. Original terminal scores and registered edge acceptance remain unchanged. The $4.50 hourly goal remains an account objective, never an individual label hurdle.

The owner authorized merge and deployment for paper observation. Manual deployment with `paper_only=true` checks configured `TRADING_MODE=paper` before upload or activation, verifies the running process afterwards, and fails if a different mode is configured; it does not rewrite environment settings. Research collection, label processing and training remain on GitHub, and no Oracle forecast is added to live entry call sites by this release.
