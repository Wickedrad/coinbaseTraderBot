# Verifying the edge taught by the Oracle

The new forward trial uses the saved Oracle response tables and learned importance directly. It does not substitute the small recorded-input MLP study, refit weights, or use settlement wins as the profit target. All capture, paper execution and evaluation runs on GitHub; Lightsail and live trading remain untouched.

## What is locked

The full-history tables come from run `42643723640`, and importance from `42667008829`. Their metadata identities, binary hashes, layouts, vocabulary and training cutoff are checked before prediction. Forecasts include the model identity, actual publication time, feature origin, acquisition time, exact future target, probabilities, missing axes and active curve count. Each forecast is fsynced and printed to the public Actions log before any subsequent book is consumed.

Fresh minute history comes only from **tvdatafeed**, requesting `BINANCE:*USDT` and the existing daily dominance symbols. This is an explicit provider-transfer study from the original archived Binance candles. No source is relabeled. The 5,000-bar limit does not warm every daily or 4-hour indicator; unsupported axes and their curves stay unavailable. Revisions to used closed OHLC quarantine the affected asset. No missing minute or intraminute path is invented.

The price target is anchored at the last completed minute, exactly as in Oracle training. Actual publication lag shortens the remaining lead and is recorded. Future labels use the exact later minute close. Terminal up/sideways/down probabilities are scored against that original target. An additional path analysis checks which direction first confirms a sustained move on two closed minutes after publication. A later terminal reversal cannot erase an early correct direction in this path diagnostic. Missing paths remain unavailable; no-move cases are retained as misses for both rankings. These minute labels cannot certify intraminute reversal onset.

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

Start a short source/protocol probe (it cannot qualify as edge evidence):

```sh
gh workflow run atlas-recordings.yml --ref main -f oracle_edge=true -f edge_cycles=2
```

Start a locked trial long enough to observe both horizons:

```sh
gh workflow run atlas-recordings.yml --ref main -f oracle_edge=true -f edge_cycles=72
```

The run produces `atlas-oracle-edge` with registration, forecast publications, raw tvdatafeed receipts, books, fee evidence, outcomes, fills and account reports. Current workflow versions automatically assess locked trials. A short probe has no matured 15-minute or one-hour outcomes.

Assess completed locked trial artifacts without recollecting or refitting:

```sh
gh workflow run atlas-recordings.yml --ref main -f oracle_edge=true -f source_run=RUN_ID
```

For a complete same-protocol cohort, supply its run IDs separated by commas. The evaluator rejects changed models, policies, implementation, overlapping trial periods, changed artifacts and backdated forecasts. The assessment artifact is `atlas-oracle-edge-assessment`.
