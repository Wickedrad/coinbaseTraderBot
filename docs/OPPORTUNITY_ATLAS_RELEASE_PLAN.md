# Opportunity Atlas release acceptance

The owner clarified that the predictive requirement is reliable advance movement.
Normal profit-taking uses the existing dynamic $4.50/hour clock and maintained
Kalshi fee schedule. Settlement prediction is a separate diagnostic; profitable
positions may use the configured final-window exception. See
[the updated objective and commands](OPPORTUNITY_ATLAS_PROFIT_OBJECTIVE.md).

The subsequent full-history request adds an
[every-minute Oracle-first block study](OPPORTUNITY_ATLAS_ORACLE_BLOCKS.md), followed
by separately frozen quarterly prediction folds for 15-minute and one-hour
up/sideways/down outcomes. It preserves the fresh November 9 holdout and reports
native SNN and executable contract-profit evidence separately.

The owner authorized continuous implementation through a finished product. The
core workflow merged in PR #306; PR #307 verifies the recorded-input follow-up.
PR #308 adds the independent advance-movement objective and reuses the existing
fee-aware profit clock through a read-only adapter.
Intermediate components do not require separate approval.
The owner subsequently authorized main merges. Deployment and live entry changes
still require approval; research merges use `[skip deploy]` to avoid a server restart.
Data work and training run on GitHub runners, without Lightsail access.

The release target is a usable offline/paper research product with the complete
data-to-forecast-to-position-query path, explicit validation evidence and no bypass
of the bot's risk gateway. Software completion and qualified trained models are
reported separately; neither tests nor synthetic demonstrations establish an edge.

## Required software

- [x] Audited minute data, source identity and causal multi-timeframe features.
- [x] Minute decisions, observed path labels and exact remaining-minute horizons.
- [x] Initial joint competing-risk candidate with purged studies and diagnostics.
- [x] Read-only causal SNN state/embedding capture and consistent feature encoding.
- [x] Official-index settlement and timely-move joint labels with missing-data rules.
- [x] Smooth joint candidate and same-period comparison with the tree candidate.
- [x] Purged calibration, independent evidence, full-parent ablations and retention
      records that preserve suppressed relationship evidence.
- [x] Artifact registry and exact-contract query with temporal/source/schema checks.
- [x] Paper entry/hold/reduce/exit evaluation from probabilities, quotes and costs.
- [x] End-to-end recording/replay/study/query/status commands and operating guide.
- [x] Regression, causal invariants, failure cases and end-to-end verification.
- [x] Independent advance-movement labels/models, movement-only S5/S6 comparison,
      actual forecast-publication lead and native profit-clock/fee exit queries.

## Qualification

The original `legacy-pre2025-frozen2026-v1` study remains separately identified.
The owner authorized `prospective-2026-11-09-v1`: earlier 2026 data may be used for
development, and observations from November 9 onward are a fresh holdout. Reused
2026 data is no longer unseen validation evidence. A forecast must also follow
the actual publication of its artifact; a calendar boundary cannot backdate it.
Existing archives retain their declared provider identity. Fresh acquisition
remains tvdatafeed-only. Official ticks and SNN states are not invented from OHLC.

GitHub run [42538058087](https://github.com/Wickedrad/coinbaseTraderBot/actions/runs/42538058087)
processed the located multi-year archive: 21,070,767 usable minute rows, 14,618
decision frames, 192,932 path labels and eight purged rolling evaluation folds.
BTC/ETH begin in 2017; other assets start later. Off-grid BTC/ETH rows are preserved
in raw inputs and excluded in a receipt-checked derived copy, without shifting
their timestamps. The first tree fit did not show reliable gain over geometry:
exploratory weekly log-loss gain -0.01388, interval [-0.03719, 0.00635].

The fixed smooth/tree comparison completed on the same 14,618 decision frames.
The smooth full-context candidate was generally worse; neither family established
predictive or economic qualification.

The archived recording probe confirmed official Kalshi index messages, native
Coinbase 1m candle arrays, recorded strikes, and both 15m/hourly contracts.
GitHub run [42549662484](https://github.com/Wickedrad/coinbaseTraderBot/actions/runs/42549662484)
completed the bounded contract/S5/S6 path on 105,519,127 observed events across
14.58 hours: 3,876 complete base outcomes and 3,804 matched SNN outcomes per
variant. All 1,080 historical paper queries abstained. The first sample has only
19 distinct training settlement events, so its heads remain fallback priors;
the fixed 20-event fitting minimum is preserved. Its audit has one week and no
confirmed results or executable quotes. This is successful software verification,
not evidence for learned contract relationships or profit. Prefix checks establish
selected observed hours, not complete-archive coverage or fill fidelity.
All data processing and training use GitHub runners. No model is live-qualified.

The expanded fixed-prefix run
[42568366333](https://github.com/Wickedrad/coinbaseTraderBot/actions/runs/42568366333)
adds October 24 and 27 before the training cutoff, preserving all model settings,
audit dates and the final boundary. It completed 5,340 base outcomes and 5,244 per
SNN variant across 19.99 observed hours. All three contract heads now fit actual
models, with 66 distinct training events in the base and 64 per SNN variant.
All three candidate families were exercised; trees won the selection window.
No indicator/SNN family was retained. The audit has one week, two confirmed events,
zero executable quotes and insufficient conditional calibration. All 1,080
historical paper queries abstained; there is no forward-trial evidence yet.

The preceding recording source and workflow revision passed GitHub CI
[42568299149](https://github.com/Wickedrad/coinbaseTraderBot/actions/runs/42568299149):
1,243 tests, zero failures/skips, typecheck and build. Windows packaging and CodeQL
also passed. The final evidence update changes documentation only.

The movement-only replay
[42583415334](https://github.com/Wickedrad/coinbaseTraderBot/actions/runs/42583415334)
reuses those archived inputs without consuming settlement results or payout
models. Physical queries are deduplicated across sides/strikes: 1,550 complete
base movement examples and 1,526 per SNN variant. Smooth, tree and temporal-linear
heads all fit real data; trees won selection, with 65 distinct base training events
and 63 per SNN variant. No conditional feature family had sufficient independent
retention evidence. The supported audit cohort contains 74 rows in one week;
movement predictive gain and calibration remain unqualified. All 918 retrospective
queries remain unsupported/unqualified, with zero forward observations.

The movement source `a84af4197fe27447245b277fa2f813d4fb2a9aed` passed GitHub CI
[42583417179](https://github.com/Wickedrad/coinbaseTraderBot/actions/runs/42583417179):
1,257 tests, zero failures/skips, typecheck and production build. Windows
packaging and all CodeQL languages passed. The subsequent evidence changes
only documentation; no executable source differs from that tested revision.

The movement evidence and exact source CI results are recorded in
[OPPORTUNITY_ATLAS_MOVEMENT_VALIDATION.json](OPPORTUNITY_ATLAS_MOVEMENT_VALIDATION.json).
Settlement wins and executable quotes do not gate movement qualification; actual
sale/fill performance remains a separate claim.

The software checklist is separate from these unfulfilled evidence requirements:

- [ ] Adequate observed training/development coverage under an approved study plan.
- [ ] Independent advance-movement predictive/calibration and conditional S5/S6 evidence.
- [ ] Measured venue fill/replay fidelity and a completed forward paper trial.
- [ ] Owner-approved production integration, deployment and live enablement.

See [the operating guide](OPPORTUNITY_ATLAS_OPERATIONS.md) for formats, commands,
causal assumptions, uncertainty semantics, abstention and current data constraints.

## Final review

The final result must include reproducible commands, data/code/model hashes,
validation and ablation reports, explicit capability/readiness status, and one
reviewable PR. Deployment/live enablement require owner approval of that concrete
result. No intermediate milestone may be represented as the completed system.
