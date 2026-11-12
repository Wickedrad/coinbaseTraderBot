# Advance movement and the existing profit clock

The owner's November 9 clarification makes reliable advance price movement the
Atlas's primary objective. A contract normally earns money through a sale at a
higher side bid after fees. Its eventual YES/NO settlement is a secondary
diagnostic and the configured profitable late-window exception.

The existing bot already implements the execution rules. The Atlas reuses them:

- `bot/risk/quotaPacer.ts`: $4.50/hour, $108 per cycle, anchored at 10 AM New York
  time by default. The current hour, realized fee-net P/L and remaining hours
  determine the active slice. The default `slices` mode does not stack missed
  hours into one oversized target. Ahead of pace it retains a minimum take.
- `bot/fees.ts` and `bot/kalshi/feeSchedule.ts`: maintained series/event fee terms,
  published rates and account rounding. Exit fees are calculated for the actual
  quantity and side price. Entry fees belong in the open position's cost basis.
- `positionNetAtBid`, `quotaCall` and `shareWindowSec`: current liquidation P/L,
  quota takes/floors, and the capped trading window used for the late exception.

The example profit policy matches repository defaults, including the existing
higher-target quota floor. It is not a claim about the running server's settings.
A future runtime adapter must pass its actual configuration and verified fee
snapshot. Existing live callers and the fee refresher remain unchanged.

## Learning target

`labelTimelyMovement` observes only the future price path through the normal sale
deadline. It measures the configured significant move from the decision price,
its first sustained threshold time, lead time, MFE and MAE. The default minimum
lead is five seconds; a move reaching its threshold sooner does not earn advance
prediction credit. Reversal and continuation definitions still require their
causal preceding drift and configured sustain.

The deadline is the earlier of the input's execution deadline and the contract
close less the explicit sale buffer (30 seconds in the example). The profitable
late-window exception is separate: the default last 90 seconds of a 15-minute
window or six minutes of an hourly window. It does not truncate the movement
forecast horizon or make a currently unprofitable position a settlement hold.
Listing a ladder a day early cannot extend that exception to its whole last hour.
Deadline, lead and sustain are explicit parts of the target definition.

No settlement-window prints, reported outcome, contract win label, quote or
profit credit is needed to label or validate a movement. Missing path coverage
remains unavailable, not a false negative. Both YES/NO sides and ladder strikes
for the same physical query are deduplicated. Its numeric inputs contain causal
TA, optional SNN state, market context and movement geometry; they exclude payout
labels, strikes, contract side and the profit clock's urgency.

The study compares smooth, tree and temporal-linear movement heads, with separate
training, stopping, beta calibration, selection and audit windows. Conditional
full-parent retention uses predictive price-path gain. It does not require an
indicator to predict settlement wins or fee-net settlement returns. Same-period
S5/S6 comparisons also use movement outcomes. Independent calibration-group
frequency bands retain their stated stable, independent-week assumption; they
are not individual-probability confidence intervals.

The November 9 holdout remains excluded from development. New artifacts have a
distinct objective/schema; older joint settlement artifacts are not rebranded
as validated movement detectors. Published model time and genuine forward-capture
checks remain enforced. A movement-supported result informs the existing entry,
fee and risk controls; movement probability is not used as a contract fair price.

## Profit exit queries

`evaluateProfitExit` evaluates a caller-reported open position using an as-of
side bid, available depth, fee snapshot, realized P/L credits and risk allowance.
It uses the production quota clock instead of recreating its time/P&L formula.

For example, 40 contracts bought at $0.50 with $0.70 entry fees have an average
cost of $0.5175. A $0.65 sale receives $26 less $0.64 exit fees: $4.66 net.
The $4.50 slice can therefore take that profit. A smaller current need can lower
the required sale price. It never enlarges the risk-approved position to make an
otherwise unreachable dollar target possible.

Existing higher-target floor and group verdicts can be supplied by their current
owners. Partial depth produces a partial recommendation and reports its own
quantity-specific rounded fee; no realized credit is invented before a fill.
Credits use `netUsdDelta`: the realized, fee-adjusted increment already computed
by position accounting. A cumulative account total or a settlement total already
credited through partial exits must not be added again.
Risk reductions stay independent of model confidence. A profitable position can
ride inside the final share. An unprofitable position continues through existing sale/stop management; at the
normal sale deadline the adapter seeks a reduction rather than a settlement hold.
Settlement value is not its hold criterion.
These are read-only recommendations, not orders or fills.

The legacy strategy also has a configurable unconditional final no-exit window.
This research adapter does not enable that window as a reason to hold a losing
position. Its live configuration/caller integration remains a separate approval
step; this release changes no running exit behavior.

## Run on GitHub

**Off since Nov 11, 2026 (8:05 AM EST / 13:05 UTC):** both commands below are gone (`atlas-movement.yml` deleted, `movement_only` removed): `atlas-movement-study` bundled rows built from the bot's recordings and this repository is public.

The completed observed study's input receipts and frozen SNN states can be reused.
The movement workflow ignores its settlement datasets and fitted payout models:

```sh
gh workflow run atlas-movement.yml --ref main -f source_run=42568366333
# Equivalent path through the existing recordings workflow:
gh workflow run atlas-recordings.yml --ref main -f study_run=42568366333 -f movement_only=true
```

The artifact is `atlas-movement-study`. Its registration is written before labels;
it contains the new datasets, model/source hashes, selection/audit reports,
movement-only SNN comparison and explicit retrospective shadow forecasts.
This performs no Drive recopy, native SNN replay, Lightsail access or deployment.
Fresh historical acquisition remains tvdatafeed-only.

`npm run research:opportunity-movement --` also exposes `assemble`, `study`,
`query`, `shadow` and `exit`. Use `--policy` for the explicit profit policy.
Forward shadow capture requires an already-published product and current requests
before their movement deadlines. Request/inference/publication lag is bounded to
one second, with fresh index and SNN clocks. A receipt records publication after
the atomic forecast-file rename. Forward lead is scored from that publication
time, so computation or delivery lag cannot earn advance credit from an older
feature timestamp. Late publication is explicitly ineligible.
Historical replay requires `--historical-audit`
and never contributes forward evidence. Profit and fill-performance evidence is
reported separately from movement reliability.

## Observed verification

GitHub run [42583415334](https://github.com/Wickedrad/coinbaseTraderBot/actions/runs/42583415334)
completed this movement-only path on the archived inputs. It produced 1,550
complete deduplicated base examples and 1,526 for each SNN variant. All three
candidate families fitted; trees won selection. The audit contains only one
independent week, so neither movement reliability nor a conditional/SNN edge is
established. All 918 retrospective queries stayed unsupported or unqualified.
No replay was counted as forward evidence. See
[the validation record](OPPORTUNITY_ATLAS_MOVEMENT_VALIDATION.json) for source,
artifact, model, coverage and CI receipts.
