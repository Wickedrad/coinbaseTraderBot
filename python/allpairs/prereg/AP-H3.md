# Pre-registration AP-H3: maker_only's 10c-cap gain is a training-set effect, not an execution filter

Written 2026-11-06 01:23 UTC (Nov 5 8:23 PM EST). No AP-H3 cell has been fitted or scored. The design was framed with
the institutional-research thread at 01:18 UTC Nov 6. Its source is the AP-H2 follow-up, run 42139241813.

## Why
maker_only base and maker_only tight (no entry on a book wider than 10c) trade the same books. In base, 1,610 of
1,615 trades are on books of 5c or less. Yet base made -$0.43/h on H-HOLD and tight made +$0.53/h. The cap's
`max_spread` acts in two places:
- in **training**, the exit-model and entry-model fits only see positions on tight books;
- in **trading**, no entry is made on a wide book.

The hypothesis is that the gain comes from the first.

## Cells
All cells use config maker_only (hash 15126867b0). Two config keys are read with `.get`, so no existing hash changes:
- `costs.max_spread_train` caps the positions built for fitting: the exit models, the entry model and its shuffled
  refits.
- `costs.max_spread_trade` caps the positions that are simulated (validation hurdle and test).
- `max_spread` keeps meaning both.

| cell | train | trade |
|---|---|---|
| C_AA | all books | all books (= maker_only base) |
| C_TA | tight (<= 10c) | all books |
| C_AT | all books | tight |
| C_TT | tight | tight (= maker_only tight) |
| R (placebo) | a seeded random subsample of all-book training positions, the same count as C_TT's tight training positions | tight |

- R separates "tight-book data" from "less data".
- All five count as trials in N for the deflated Sharpe and for BHY.

## Quantities
- **Train effect** E_train = ((C_TA - C_AA) + (C_TT - C_AT)) / 2.
- **Trade effect** E_trade = ((C_AT - C_AA) + (C_TT - C_TA)) / 2.
- **Gain** G = C_TT - C_AA.
- **Trade-cap-only share** = (C_AT - C_AA) / G.
- **Placebo recovery** = (R - C_AA) / G.

All are in $/h. Paired differences use 24-hour block bootstrap CIs (block_bootstrap_mean, 2,000 draws).

## Predictions (hypothesis holds)
- **P1**: E_train >= E_trade.
- **P2**: C_TT beats R.
- **P3**: the placebo recovers less than half the gain: (R - C_AA) / G < 0.5.

## Decision rule
- **Falsified** if either holds:
  - the trade-cap-only cell carries at least 50% of the gain: (C_AT - C_AA) >= 0.5 x G;
  - the placebo matches train-tight: (R - C_AA) >= 0.5 x G.
- **Supported** if P1, P2 and P3 all hold, with G > 0.
- **Inconclusive** otherwise.
- **No gain.** If G <= 0 on a scoring tier, there is no gain to explain on that tier. That is reported, and nothing
  is supported there.

## Where it is decided and scored (never H-HOLD)
1. **Direction (dev-choice, not evidence).**
   - An inner purged walk-forward inside H-DEV, Apr 18 to Jul 31 2026: 60 days train, 2 days gap, 14 days test,
     giving 3 folds (tests Jun 19 to Jul 30).
   - All five cells are run there. Rows are flagged `dev-choice`, and nothing is chosen from H-HOLD.
2. **Recorded tier.**
   - One fit per cell on H-DEV (Apr 18 to Jul 29, the HO-1 training span). Each cell is scored on the bot's recorded
     books from Oct 21 to Nov 5 02:00 UTC (15 days) with queue-aware maker fills.
   - Leave-one-day-out for anything chosen on recorded days. Nothing is planned to be chosen there.
   - The registry's recorded-tier pass rules apply: at least 14 days, at least 60% of days won, worst day no worse than
     -$1/h, beats its placebo.
   - The recorded scorer is new work for this engine. Its fill rule is fixed in an amendment to this file before any
     recorded-tier result exists.
   - These dates sit inside H-HOLD's last 15 days, but the books are the bot's own recordings, a separate tier.
3. **Lockbox L2** (Nov 13 05:00 to Nov 20 05:00 UTC). A separate pre-registration, written before Nov 13 05:00 UTC
   (Nov 13 00:00 EST), names the cell and settings frozen from steps 1 and 2.

The current H-HOLD numbers (C_AA -0.43, C_TT +0.53 $/h) are the source of this hypothesis, not evidence for it. H-HOLD
can only weaken it.

## Readouts (information)
For every cell:
- P&L by side and price paid;
- mid-to-mid markouts from the fill;
- concentration: $/h without the top 5 and top 10 trades and the top 3 days, per-trade skew, and how many winners carry
  the total;
- training positions and trades.

The lockboxes L1 (Nov 6 05:00 to Nov 13 05:00 UTC) and L2 are never loaded before their gate.
