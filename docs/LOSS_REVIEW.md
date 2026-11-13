# Loss review: from every paper loss to a verified loss-prevention rule

Research only. Nothing here is imported by the bot, the heat reader or the oracle, and `python/`, `tests/`, `docs/` and
`.github/` never reach the server (`deploy/deploy-scope.ts` RESEARCH_ONLY), so a merge of this loop skips the bot deploy.
**The loop never edits the heat curves and never changes the bot.** Its end product is a promotion PR in the style of the
size dial (#346: off / log / on), written for the owner's word.

Plan: the Claude Doc "Loss-to-rule loop: automatic loss review and sweeps" (Nov 12 2026). Standing rules it keeps:
nothing sells under entry plus both fees unless it can't be helped (loser cut, end-of-window exit); the lane keeps trading
often (skip rules may not remove more than 15% of the un-ruled trips per hour); a curve edit needs the owner's explicit word;
live stays off; per-trade data stays private (this repository is public: rows go to Drive, logs print aggregates only).

## The loop

| # | Step | Who | Code |
| - | ---- | --- | ---- |
| 1 | Trip file for the day: every heat round trip rebuilt from the bot's own fills, plan sales and settlement, with actual fees, maker or taker, and each sale flagged against the break-even floor | code | `builder.py`, `nightly.py`, `paths.py`, `outcomes.py` |
| 2 | Economics and ordered loser class (dollars to one class only), fee ledger over winners too | code | `triage.py`, `ledger.py` |
| 3 | Tags for each reviewable loser from a closed vocabulary | Haiku 5.5 | `forms.py`, `prompts.py` |
| 4 | Hypotheses per loss class: one ex-ante feature, one lever, at most 12 thresholds and 2 neighbor features | Sonnet 5.5 | `forms.py`, `prompts.py` |
| 5 | Adversary and a blind winner control (does the rule hit winners as often as losers?) | Sonnet 5.5 + code | `prompts.py` (`control_stats`), `rules.py` |
| 6 | Registry ("our TA list"): every hypothesis is a trial, the count only goes up | code | `registry.py` |
| 7 | Educated sweep: score each threshold on days **after** the losses that generated it, against one placebo per lever | code | `sweep.py`, `stats.py` |
| 8 | Offline shadow: the frozen rule flags every night's trips, unseen days pile up | code | `shadow.py` |
| 9 | Promotion PR (off / log / on) for the owner when shadow shows a gain over its placebo | Claude, owner decides | by hand |
| 10 | Weekly audit of verdicts and the whole registry | Opus 5.5 | routine |

The model steps only propose; `forms.validate_hypothesis` and `rules.validate_rule` decide what is admitted. A hypothesis may
cite only columns known at order time or earlier (`schema.ex_ante`); outcome columns (P&L, the bid path after the entry,
the spot after the entry minute, the result) are shown to a reviewer in a separate block and can never be features.
A rule on a curve column (`rank`, `heat`, `weight`, `call_key`, ...) is a **curve edit**: it can be swept but cannot enter
shadow until the owner says so (`Registry.owner_ok`).

## Data path (no server contact)

`drive-archive.yml` copies each finished UTC day's audit log to Drive (its cron says 07:20 UTC, but GitHub started the run between
14:10 and 17:39 UTC on Nov 3 to 12). `loss-review.yml` therefore runs when that archive run completes on main (and on a 20:30 UTC
= 3:30 PM EST safety-net cron, or on demand): it builds yesterday UTC, pulls the day before, the day and the day after, runs `nightly.py`, and puts `trips-DAY.jsonl`
(per-trade: private), `agg-DAY.json` and `report-DAY.md` (aggregates) under `derived/loss-review/days` on Drive. The log prints
aggregates only, and a dollar figure is printed only for a cell of 5 trips or more (a cell of one is a trade); the full table is
in the private report on Drive. A day with audit records but no heat trip writes empty files (a notice, not a failure); a day
with no audit on Drive, or no record at all, fails the run. The day-after file only supplies settlements that land just after midnight; the result is also read from
Kalshi's public market endpoint.

```
PYTHONPATH=python python3 -m lossreview.nightly --day 2026-11-12 --audit-dir DIR --out DIR [--no-net]
PYTHONPATH=python python3 -m unittest discover -s python/lossreview/tests -t python
PYTHONPATH=python python3 -m lossreview.cli TRIPS.csv --out DIR     # the older CSV entry (the Nov 12 study file)
LOSSREVIEW_TRIPS=TRIPS.csv ... unittest ...                         # adds the Nov 12 regression
```

## What the trip file holds

- **Ex-ante block** (known at the call or the order): coin, kind, side, curve columns, the PLAN's price, count and stake
  (`entry_px`, `count`, `stake`; the `*_plan` duplicates), window position, call age. **Fill block** (known once the entry
  filled, a minute later): the actual entry price, count and stake (`entry_fill_px`, `count_filled`, `stake_filled`), fee, taker
  or maker. A hypothesis can lean on the plan and never on the fill; `order_t` (the order cannot be later than its first fill)
  is the cutoff for anything "known at the order" and is not itself a feature. **Outcome block**: P&L,
  exit rule and each sale leg, the bid path, the result. `schema.COLUMNS` tags every column with when it is known;
  `outcomes.py` keeps the spot of the last closed minute before the entry (`spot_pre_*`, clean) apart from the entry
  minute's close (`spot_entry`, a leak).
- **Break-even floor per sale.** Each sale leg carries `below_breakeven` (net of entry price, its share of the entry fee and its
  own fee) and its plan rule. Sales under the line from a rule other than the loser cut or the end rule are defects for the
  exit owner (`defect_sale`, `defect_dollars`): they are reported, never swept.
- **Fidelity.** A trip whose fills do not explain its logged P&L (within $0.10), a fill logged twice (same trade id, or the
  same day present as a plain and a gzipped file), an orphan fill, or a remainder held to the end whose result is not known yet
  (`unresolved`, finished from Kalshi's public market record by `builder.resolve_payout`) is flagged and kept out of every sweep
  (class FIDELITY). A sale leg is matched to its plan event from 5 s after to 180 s before the fill (the engine writes the event
  right after it sends the sale); a trip that sold part and held the rest ends as `settled`.

## The sweep's rules of evidence

- One class at a time; dollars go to one class only; day-0 classes are post hoc and are never evidence.
- Scored only on days strictly after the last day that generated the hypothesis (a hypothesis with no generating days is
  refused). Each candidate (a threshold, or a tail or quartile of a neighbor feature) is a trial.
- Fixed looks: a hypothesis is read once at 4, once at 8 and once at 12 scoring days, always the first N days after the
  generating ones, and never nightly (so there is no optional stopping). The p-value of a look carries a Bonferroni correction
  over the candidates that can pass the floor times the three looks; Benjamini-Hochberg (q = 0.1) then runs across the
  registry, whose family size is the 56 trials of the earlier levers study plus every registered item.
- One control per lever: a skip is compared with a random skip of the same count, a dial with the same multiplier on trips of
  the same price bucket (exact expectation, not a draw). The test is the day-pooled gap with its own standard error (days are
  the independent windows, a one-sided Student t with days - 1 degrees of freedom) **and** a positive absolute gain: beating
  the placebo while losing money is not a pass. At least 4 days and 100 flagged trips. A skip rule must leave 85% of the trips:
  a candidate that cannot (judged from the features alone, before any scoring) is dropped, and a dial multiplier under 0.25 is
  a skip in disguise and is refused.
- Maker, strike and exit levers cannot be priced from the trip file: the sweep writes a replay request for the owner of that
  replay (`replay_request`), one control per lever, same rule about days.
- First-order dollars only (a skip removes the trip, a dial scales it). Integer contract counts, fee rounding and the effect of
  trading less on the lane's own state are checked in shadow and by the promotion PR's differential test.

## Known limits

- `best_bid_held` is a one-minute extreme from public candles; the classes use the bids sampled at entry, +1, +2 and +5 minutes
  when it is missing and tag `reach_unproven`. A sale leg's price is the actual fill; the plan event's bid is only context.
- A trip row written before Nov 12 carries the book's running total in its logged `pnl`: the builder then takes P&L from the
  fills (`pnl_source: fills`).
- Reading the first days gives one bearish regime: nothing found in them is evidence about other regimes, which is what the
  scoring days after the generating losses are for.
