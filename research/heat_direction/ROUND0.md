# Round 0 result (DEV only; VAL not touched)

Run 44607359478 (commit f7344eea), 2026-11-19 20:23 UTC / 3:23 PM EST. Binance spot 1-minute bars, DEV = 2026-01-01 to 2026-06-30 (181 days). The live lane's current settings with no Kalshi condition: BTC and ETH, 15 minutes, all four bar sizes, top 10 levels per coin by rank, hottest combiner, lockout 15, lag 0, no TA layer. spec hash 5413803767761a24523d1712f23ab4874c2f9070305127e72b3760a6620b5740. PREREG.md sha256 628c2b7d42b4c0fa414c762e977773613897c18e5711a8ad2bbee7c3796406d3, AMENDMENT-1.md sha256 76cbd87d5b817348f84a1a5687d7b53680b7a5703852fc5bcea86d9ce1467f1f at the time of the run.

## Call volume (the number Amendment 1 said round 0 would measure)

28,740 calls, 28,679 decided (flat share 0.21%): BTC 77.2 and ETH 81.6 calls per coin per day, far above the 4 per coin per day the first power table assumed. Hot 1-minute levels fire dozens of times a day, so a 15-minute lockout leaves a call about every 18 minutes.

## Score: 4 of 10 (core 8: 4), required checks 1 to 3: 1 of 3

| # | Check | Value | Pass |
|---|-------|-------|------|
| 1 | Level >= 55.0% | 52.45% | no |
| 2 | Not luck (97.5% day-cluster lower bound > 50%) | 51.89% | yes |
| 3 | Beats best naive rule by 2.0 points | -0.02 points (best rule: fade the last 15 minute move, 52.47%) | no |
| 4 | Both coins >= 53% | BTC 52.25%, ETH 52.63% | no |
| 5 | Weeks > 50% in >= 65% of full ISO weeks | 88% of 25 weeks | yes |
| 6 | Every block > 50% (Jan-Feb, Mar-Apr, May-Jun) | 52.35%, 52.39%, 52.60% | yes |
| 7 | Both sides >= 52% | UP 52.27%, DOWN 52.66% | yes |
| 8 | One minute late >= 53% | 52.38% | no |
| 9, 10 | TA confirms / invalidates | no TA layer: 0 | no |

Naive rules at the same call times: fade the last 1, 5, 15, 60 minute move 51.98%, 52.19%, 52.47%, 52.08%; follow them 48.02%, 47.81%, 47.53%, 47.92%; always UP 50.02%, always DOWN 49.98%.

Reading: the lane's levels point the same way as "fade the last move". About 2.5 points above a coin flip is real and steady (every month, 88% of weeks, both sides, both coins) but it is the mean-reversion rule, not a separate edge, and it is 2.5 points short of the 55% bar. A 55% pooled hit rate and 2 points over the fade rule are what the optimizer has to find in the frozen grid.

## Twin gate (evaluator self-test): passed

Six no-signal twins (ids 1 to 3, BTC and ETH), each scored alone on DEV: 0 of 10 checks each; hit rates 50.54, 50.17, 49.95 (BTC) and 50.01, 49.96, 49.04 (ETH) with z of 1.26, 0.40, -0.12, 0.03, -0.09, -2.33 (limit 3). Random sides on the candidate's own call times, 200 draws, seed 20261120: 99% scored 2 or less (needed 95%), mean score 0.17, maximum 3.

## Power table re-run with 80 calls per coin per day (3,000 simulations per scenario; power_rate80.txt)

Pass rate per look, VAL window / FINAL window:

| Scenario | Pass | Core 8 pass |
|----------|------|-------------|
| no edge | 0.00% / 0.00% | 0.0% / 0.0% |
| edge .53, TA adds nothing | 0.00% / 0.00% | 1.1% / 1.4% |
| edge .55, TA adds nothing | 0.00% / 0.00% | 50.6% / 49.1% |
| edge .55, TA adds value | 54.7% / 52.7% | 54.7% / 52.7% |
| edge .57, TA adds value | 99.8% / 99.6% | 99.8% / 99.6% |

With this many calls the noise is small, so the 55% level (check 1) is the check that decides; "8 of 8 core" at a true .55 hit rate happens about half the time and then needs a TA layer worth about 3 points to reach 9. A layer that adds nothing cannot pass (8 at most), which is the question already put to Steven.
