# Loss review: code triage and the fee-per-stake ledger

Research only. Nothing here is imported by the bot, the heat reader or the oracle, and `python/` never reaches the server
(`deploy/deploy-scope.ts` RESEARCH_ONLY), so a merge of this folder skips the bot deploy.

Part of the loss-to-rule loop (plan: the Claude Doc "Loss-to-rule loop: automatic loss review and sweeps", Nov 12 2026;
files in the project folder `loss-review/`). This folder is steps 1 and 2: the trip economics, the ordered loser classes
and the fee ledger that includes winners. The model review (steps 3 to 5), the registry, the sweeps and the shadow runs
come later and read these outputs.

## Run

```
PYTHONPATH=python python3 -m lossreview.cli TRIPS.csv --out DIR
PYTHONPATH=python python3 -m unittest discover -s python/lossreview/tests
LOSSREVIEW_TRIPS=TRIPS.csv PYTHONPATH=python python3 -m unittest discover -s python/lossreview/tests   # adds the Nov 12 regression
```

`TRIPS.csv` has the columns of `trips-joined.csv` from the Nov 12 loser study (one row per heat round trip). The output
`triage.csv` is per-trade data: **this repository is public, so it goes to private Drive or the project folder, never into a
commit or a job log.** Only `report.md` aggregates may be printed.

## What it computes

- **Economics for every trip** (winners too): entry fee (bot/fees.ts, ported in `fees.py`), the exit price that explains
  the trip's own P&L and its exit fee, gross before fees, fees, fee share of stake. The Nov 12 file reproduces the study:
  entry fees $108.48, fees about $209.6, gross about -$26.
- **Ordered class for every loser**, dollars to the primary class only: FIDELITY, OTHER_LANE, FEE_ONLY, CUT_THEN_WON,
  SOLD_THEN_WON, RIGHT_THEN_REVERSED, WRONG_SIDE, UNEXPLAINED, UNKNOWN_DATA (definitions in `triage.py`). Tags
  (cheap, big_count, late_entry, hourly, no_side, pair_call, reach_unproven, unreconciled) never carry dollars.
  LUCK_WITHIN_NOISE waits for the call ledger's ex-ante estimate. WRONG_SIDE and the *_THEN_WON classes are hindsight
  labels, never features.
- **Column registry** (`schema.py`): every column is tagged with when it is known (call, order, plus 60 s, close).
  `validate_feature` refuses any hypothesis that cites a column known after the order, and marks the lane's curve
  columns (rank, heat, weight, call key and so on) as a curve edit, which needs Steven's explicit word.
- **Input checks**: count times price paid must explain the stake (catches a YES price used for a NO buy), and a NO buy
  must be priced at 1 minus the YES-terms plan price.

## Known limits

- `best_bid_held` is a one-minute extreme and is missing on some trips; the classes then use the bids sampled at entry,
  +1, +2 and +5 minutes and tag `reach_unproven`.
- A trip with more than one sale is explained by one exit price only approximately (tag `unreconciled` above $1).
- The first input is the Nov 12 file (13.8 hours, one bearish regime); the builder that fills the same columns from the
  audit log, fills and candles comes next and must keep the available_at tags and a truncate-at-call recompute test.
