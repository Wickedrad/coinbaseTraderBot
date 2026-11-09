# Opportunity Atlas release acceptance

The owner authorized continuous implementation through a finished product. Work
continues on PR #306; intermediate components do not require separate approval.
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

The archived recording probe confirmed official Kalshi index messages, native
Coinbase 1m candle arrays, recorded strikes, and both 15m/hourly contracts. Prefix
checks establish selected observed minutes, not complete-archive coverage or fill
fidelity. The bounded contract/S5/S6 engineering study and smooth historical
comparison use GitHub runners. No trained model is qualified for live trading.

The software checklist is separate from these unfulfilled evidence requirements:

- [ ] Adequate observed training/development coverage under an approved study plan.
- [ ] Independent predictive, conditional, S5/S6 and fee-net qualification.
- [ ] Measured venue fill/replay fidelity and a completed forward paper trial.
- [ ] Owner-approved production integration, deployment and live enablement.

See [the operating guide](OPPORTUNITY_ATLAS_OPERATIONS.md) for formats, commands,
causal assumptions, uncertainty semantics, abstention and current data constraints.

## Final review

The final result must include reproducible commands, data/code/model hashes,
validation and ablation reports, explicit capability/readiness status, and one
reviewable PR. Deployment/live enablement require owner approval of that concrete
result. No intermediate milestone may be represented as the completed system.
