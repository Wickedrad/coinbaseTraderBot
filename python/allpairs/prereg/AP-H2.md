# Pre-registration AP-H2: maker_only's 10c-cap HO-1 pass is the candle-touch maker fill, not an edge that survives queue position

Written 2026-11-06 00:25 UTC (Nov 5 7:25 PM EST). This is after the HO-1 card of run 42127527423, which is where the claim
comes from, and before any tight_strict result exists. Decision rule, mechanism readouts and multiple-testing position
agreed with the institutional-research thread (00:06 UTC Nov 6).

## Source
In run 42127527423, maker_only under the tight arm (no entry on a book wider than 10c) was HO-1 scored on H-HOLD,
Aug 1 to Nov 4 2026, in 6 folds of 16 days, with one fit on Apr 18 to Jul 29:
- **Result:** +$0.53/h on 433 trades. It won 5 of 6 folds, and its worst fold was -$0.35/h.
- **RV terciles:** LOW +0.06, MID +0.94, HIGH +0.49 $/h.
- **Placebo:** it beats its random-entry and shuffled-label placebos.
- **95% CI:** [-0.10, +1.18] $/h.

maker_only's base arm made -$0.43/h and its stress arm -$0.47/h; both fail.

## Multiple-testing position
- This is 1 HO-1 pass in the 21 arms of run 42127527423 (7 configs x base, stress, tight).
- An arm with no edge passes HO-1's checks by luck at roughly 5-10%. At 21 arms, about one false pass is expected.
- The report gives the BHY-adjusted p of each of the 21 arms. Per arm, p is one-sided (mean daily P&L > 0) on its 96
  held-out days, from a Newey-West t with Bartlett weights and lag 3. An arm with no trade gets p = 1.

## Hypothesis
The gain comes from the base fill rule's touch fills, which a real queue would often not get. Under that rule a resting
bid fills when the next minute's lowest ask comes down to it. The prediction is that the gain disappears under strict
fills, where the ask must trade one tick through the bid.

## Quantities
All are on H-HOLD, on the HO-1 folds, with one fit per arm on Apr 18 to Jul 29.
- **T**: maker_only tight $/h, re-run in the follow-up batch. It must reproduce run 42127527423 exactly: the same $/h,
  trades, fold $/h and hourly P&L. If it doesn't, the batch is void.
- **T_s**: maker_only `tight_strict` $/h. The arm is tight plus `strict_maker`: a maker entry or exit fills only when the
  next minute trades a tick through our price. Fees, slippage and the 10c cap are unchanged. Its hurdle and model are
  chosen on H-DEV, as for every arm.
- **Artefact share S** = (T - T_s) / T.
- **D** = T - T_s on paired hourly differences, with a 24-hour block bootstrap CI (block_bootstrap_mean, 2,000 draws).
- **Folds kept**: the number of the 6 folds in which tight_strict's $/h is above 0, the same sign as T.

## Decision rule
- **Supported** if S >= 50% (T_s <= 0.5 x T), or if T_s <= 0.
- **Falsified**: the edge survives strict fills. This needs both T_s > 0.5 x T and tight_strict above 0 in at least 4 of
  6 folds.
- **Inconclusive** otherwise.
- The HO-1 verdict of tight_strict is reported alongside.

## Mechanism readouts (same batch, information only)
- **Fill-count ratio** (strict over touch), two ways:
  - maker fills of tight_strict divided by maker fills of tight;
  - within tight's own chosen maker entries, the share that would also have filled under the strict rule.
- **Per-fill markout** for each rule, at +60 s and +300 s. It is measured from the end of the fill minute: the side mid
  at t(i+2) and at t(i+6), minus the entry price, per contract. It is left out past the window's last quote, and the
  count with a markout is shown.
- **Gain by side and price bucket**: the side price paid, under 25c, 25-75c and over 75c, for YES and NO entries.
  - Kalshi makers are known to earn on favourites (Burgi, Deng and Whelan). A maker that buys NO at 80c is selling a YES
    longshot, so both are the over-75c bucket here.
  - If a surviving gain sits there, it is the maker side of the favourite-longshot bias. That is a real mechanism, not an
    artefact, and it is tagged as the next hypothesis, not as a pass.
- **P&L by entry spread** (<=5c, 5-10c, >10c), by fill type and by tier (historical before Sep 12, live from Sep 12).

## What a result can and cannot do
- Whatever tight_strict shows, this H-HOLD pass cannot be credited from H-HOLD. It was singled out after the read, and
  maker fills are a depth mechanism that candles do not record.
- tight_strict on H-HOLD can only weaken the pass.
- The route to the contract ledger runs through two tests:
  - first, the recorded tier: the bot's recorded books from Oct 21 to Nov 5 02:00 UTC, with queue-aware fills;
  - then lockbox L2 (Nov 13-20), pre-registered before Nov 13 05:00 UTC (Nov 13 00:00 EST).
- If AP-H2 is supported, the next step is a queue-aware maker rule tested on the recorded tier (never bench).

## Runs
The batch is all-pairs.yml under `--protocol ho1`, run as one follow-up together with AP-H1b's.
- Study jobs:
  - {maker_only, lead_shift24} x {base, stress, tight, tight_strict}. base, stress and tight always run in this
    workflow.
  - maker_only base and tight must reproduce run 42127527423.
- Skill job: AP-H1b's P2b.
- Report:
  - the AP-H1b and AP-H2 quantities;
  - the BHY table of the 21 arms of run 42127527423, read from Drive;
  - the reproduction check.
- Lockboxes L1 (Nov 6 05:00 to Nov 13 05:00 UTC) and L2 are never loaded.
