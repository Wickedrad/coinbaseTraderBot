# Direction learning, continuous spectra, and the $200 paper study

The objective is to predict a sufficiently sustained price move before the relevant sale deadline. Predicting a contract's settlement result is a separate problem. Small positive after-fee sales can accumulate toward the existing $4.50 hourly goal. Falling behind that goal does not increase model confidence or position risk.

## What the earlier “60% confidence” meant

The original full-history Oracle fitted historical terminal-close **up / sideways / down** frequencies. It interpolates neighboring storage knots continuously, shrinks each curve toward the historical class prior with 100 effective observations, then averages available curves and one prior with equal importance. With all inputs available, each of 406 curves plus the prior receives 1/407 of the mixture.

The 60% diagnostic meant `max(P(up), P(sideways), P(down)) >= 0.60`. It was a model point probability. It was not a confidence interval, an independently established 60% success rate, a sustained-move probability, or a profit probability. The original all-history walk had no forecasts reaching that threshold. Calibration must compare predictions made from earlier data with the observed frequency of their exact later targets.

## Spectrum audit and learned importance

The saved five-asset audit checks all **4,060** curves: 406 relationships × two horizons × five assets. Every curve contains weighted observations and passes numerical continuity checks. The audit also independently reconstructs the ensemble. This verifies the stored ranges and inference mathematics; it does not establish that every relationship has predictive value.

`spectrumViewer.html` opens an asset's saved `model.json` and `full-history-model.f64.gz`, checks their identities, and displays single-axis curves and pair heatmaps with interpolated probabilities and effective support. An optional `importance.json` from the new iteration displays learned mixture importance. The inspector works locally in a browser without uploading data.

The importance iteration keeps the original terminal target and the same 406 curves so its comparison is interpretable. It learns each curve's influence from **earlier-quarter** prediction loss relative to the class prior. It freezes both the curve tables and importance before forecasting the next quarter, with the existing one-hour label embargo. All observed minutes are replayed. The formula and settings are registered before the run; the final period is not used for tuning. Every curve remains available as descriptive evidence, including curves that receive little predictive influence.

The sustained-move decoders are a separate iteration. They consume the existing broader TA/context vocabulary, with optional native SNN state, and fit continuous nonlinear interactions. Their fitted feature names, weights, model identity, calibration table and held-period scores are exported. They do not silently relabel the original terminal-direction matrix as a sustained-move model.

## Native SNN inputs, training and outputs

The GitHub job reuses the actual observed one-second crypto and perps tapes. It does not invent second bars from the 2017–2026 minute history. S5 and S6 receive identical observations. A distinct `direction-inputs-only-v1` identity prevents these states from being substituted for the older replay that consumed contract scoring/settlement messages.

The replay ignores contract SCORE and SETTLE operations. Native direction heads learn whether price is higher at their native horizon; S6 also exercises its existing plasticity and predictive-coding learning. The exported native model contains real column arrays and readout weights. A separate receipt compares those weights with their actual initialization and records the training cutoff. Gaps over three seconds clear transients and pending labels while preserving learned weights. Missing observed prices are masked. No labels after October 28 train the native networks.

The movement decoder learns whether an observed move of **0.25, 0.5 or 1 entry ATR** begins with at least five seconds of lead, remains sustained for five seconds, and occurs before the exact contract's sale deadline. Its labels use the observed Kalshi reference index and do not require settlement, a profitable contract, or $4.50 from one signal. The native endpoint readout and this sustained-move decoder have different targets and are reported separately. Native contract-readout calibration is not treated as movement confidence. Book-derived microstructure in the legacy tapes inherits their empty-snapshot and missing-gap limitations; observed-price freshness alone does not certify those book features.

The four saved checkpoints changed 30 native direction heads in total; S6 changed 80 column arrays, while all contract readouts stayed unchanged. The short prefixes do not supply mature four-hour labels for the perps four-hour heads. S5 leaves its column arrays fixed by design.

The registered fitting, stopping, calibration, selection and audit periods remain separate. These earlier 2026 dates are reused historical development data. **November 9 onward remains the fresh prospective holdout.** Limited observed prefixes and one audit week cannot establish a reliable trading edge.

## Which price movement measures real profit?

Use the underlying coin for predictive evidence; use the contract's executable prices and actual fees for P/L:

`net sale = quantity × (exit bid − entry ask) − entry fees − exit fees`.

For example, 20 contracts bought at $0.40 and sold at $0.42 gross $0.40, but lose $0.29 with the standard rounded taker fees. Selling at $0.45 instead nets $0.31. The same underlying move can produce different contract returns because strike, spread, time remaining and displayed depth differ.

The study compares separate $200 accounts for any positive fee-net take, 5% / 10% / 25% contract-price targets, and 5% / 10% / 25% underlying-price targets. Underlying thresholds are diagnostics and alternative exit policies, not direction-learning admission rules. Sales retain paired underlying returns so the two can be compared directly. The model must answer within the contract's remaining window; a one-hour forecast cannot open a shorter contract unless it also answers that shorter deadline.

Each account uses the native `PaperExchange`, pays quantity-dependent rounded fees at both ends, uses visible depth, limits each position to $20 including fees, and holds at most eight positions and 40 contracts per position. A whole-order target can be as small as one net cent; actual positive partial-sale amounts also count toward the hourly goal. There are no bankroll refills, timer-based depth replenishments, imputed contract marks or assumed settlement payouts. A deadline sale can realize a loss. Exposure without an observed sale remains funded and unresolved.

Historical websocket recordings do not reliably preserve every gap event, so this study uses **full snapshots at their actual arrival** for economic evidence. A separate maker-exit study can use actual later public trade prints between snapshots. It places an exit behind the visible initial queue and counts only queue depletion or trade-through volume, requires a strictly later exchange-second bucket, and cancels at the sale deadline. It currently requires an explicit zero maker fee, so fractional-fill rounding cannot turn a purportedly profitable resting sale into a loss. A crossed later snapshot alone never counts as a maker fill. Standard fees are explicitly marked as assumptions where archived per-series as-of schedules are unavailable. Paper results are not private venue fills or prospective forecasts published before the event.

## Results of this iteration

The full-history importance comparison replayed 18,066,248 fifteen-minute and 18,056,438 one-hour predictions. All five assets improved log loss against the same uniform mixture. Pooled **three-class** accuracy changed from 36.30% to 36.84% at 15 minutes and from 37.10% to 37.26% at one hour. No weighted directional forecast reached 60%. These are modest reused-history gains, not executable-profit or prospective reliability evidence. Minute predictions overlap heavily; their counts are not independent samples.

Native decoders fitted 435 variable TA/context inputs, or 1,577 / 1,579 with S5 / S6. Only 63–65 distinct asset/deadline training groups were available; overlapping windows and shared markets remain correlated. On the common 12-event audit cohort, mean log loss was 0.6863 for the geometry prior, 0.8798 for TA/context, 0.6812 with S5 and 0.7885 with S6. S5 did not beat the prior on the earlier selection cohort. Some linear controls produced near-certain probabilities with poor held-period loss. Fitting a calibration transform does not establish good calibration. **No model earns automatic promotion from these results.**

The archived cash study compared 132 separate $200 accounts: four predictors, eleven exit settings, and point-probability cutoffs of zero, 0.50 and 0.60. Zero is an explicitly unfiltered ranking diagnostic. It is not a confidence assertion. All 2,671 full snapshots had **empty bid and ask arrays**, including the 883 snapshots in the paper evaluation period. Although 1,849,924 later public trade prints were processed, no account opened a position without an observed entry book. Every account retained $200. Profit verification is marked `missing-executable-depth`.

The current official [WebSocket schema](https://docs.kalshi.com/websockets/orderbook-updates) uses `yes_dollars_fp` and `no_dollars_fp`. The repository parser read only older field names, which explains how valid messages could become empty recorded snapshots. The source fix now prefers the current fields, preserves legacy formats and fractional quantities, and records subscription gaps and disconnects. Research replay invalidates books on those recorded gaps. This cannot recover depth already discarded from historical recordings. The repair is staged in source; it is not deployed to the running bot.

A separate public GET-only GitHub capture records current REST books independently of Lightsail and the bot. It uses no account credentials, constructs no order client, and leaves all November 9 onward data outside iterative fitting. Its completed 16-minute run captured **927 books with depth**, including 871 with both sides, zero crossed books and zero failed requests. Its health report does not score price outcomes or claim forecasts were published. No new underlying OHLC history is fetched.

## Reproduction

Run the GitHub `atlas-research.yml` workflow with the original `results_run`, audited `prepared_run`, and `importance_iteration=true` for the full-history weighting comparison. Use `atlas-recordings.yml` with cached `study_run`, `source_run`, and `direction_iterations=true` for native training and cash paper accounts. A completed `direction_snapshot_run` can be reused without processing the public archives again. `direction_snapshot_only=true` prepares the snapshot/trade evidence once; `paper_native_run` replays new paper policies against already saved native weights without retraining.

Source, model and evidence identifiers are recorded in the validation JSON accompanying this document. The workflows upload research artifacts. No deployment or trainer promotion is performed; the running bot’s entry/exit behavior remains unchanged.

The final source passed **1,283 repository tests, zero failures and zero skips**, TypeScript and the production build on GitHub with CPU PyTorch installed. Workflow lint and the browser inspector checks also passed.
