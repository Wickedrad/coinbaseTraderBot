# Round 8 brief: rethink the alt-season (BTC.D waterfall) forecast

Written 2026-11-02 for the people and agents working on `research/btcd_fractal/`. Everything in this folder is
research: it does not touch the bot. The owner (Steven) asked, on 2026-11-02 08:23 UTC:

> Take your time with this. Rethink the whole thing; run trials until we can iterate to something that is closer to
> the truth. What have we asked vs what haven't we asked, how can this puzzle be solved? Is there an algorithm or a
> system of algorithms that dynamically can scale or read this data into some logic that may give a forecast?
> Could we use: hidden Markov models, Gaussian mixture / clustering regimes, topological data analysis and path
> signatures, Hamilton regime-switching models?

## The puzzle

BTC dominance (BTC.D, Bitcoin's share of total crypto market cap) falls hard in an "alt season": -25 to -30 points
in a few months. Three such waterfalls are in the data: Nov 2016 to May 2017 (97 to 66, 182 days), Dec 2017 to
Jan 2018 (67 to 37, 35 days), Jan 2021 to May 2021 (70 to 41, 133 days). Nine smaller falls of 5+ points exist
since 2016 (Apr 2018, Sep 2018, Sep 2019, May 2020, Jun 2022, Jun 2025 among them). Today (2 Nov 2026) BTC.D is
60.5%, BTC is 37% under its Oct 2025 high of 124.7k, 925 days after the Apr 2024 halving.

The owner's thesis (docs/FRACTAL.md): the 2018-to-now path replays the 2016-17 cycle slowed and compressed, and
the final waterfall is still to come. He expects an alt season to last about 3 months once it starts. He wants a
forecast: is it coming, how far off, how long.

## Standing rules (the owner's, for every experiment)

1. Point in time. A reading for week t uses only data up to t. HMM/regime models forecast from FILTERED posteriors
   (forward pass to t), never smoothed or Viterbi-decoded states, which use the future. Scalers, PCA, cluster
   centres, thresholds: fitted on the training window only, refit on the schedule.
2. Walk-forward. Expanding window, first forecast 2019-01 (weekly) or as early as the model allows at daily scale;
   refit every 13 weeks; labels need their full horizon of future to be known before they enter training.
3. Adversary for everything. Shifted targets (circular shift by 26+ weeks, 100+ draws) through the WHOLE procedure
   including selection; placebo series (IAAFT / block shuffle / matched random walk); decoy signals offered to any
   selector; held-out eras (2019-20, 2021-22, 2023-26). A gain that fails its adversary is iterated, never dropped.
4. Dynamics rule. If something works in some conditions and not others, build the condition in (regime switch,
   gating, scaling); do not cut it. But every conditional addition must be tested under the conditions it targets
   before it goes anywhere near the bot.
5. Heavy compute runs on GitHub runners (ubuntu-latest, 4 cores, 90 min budget for the whole workflow), not the
   trading server. Keep a module under ~20 minutes with its nulls. The repo is public: print aggregates only.
6. Report times as both US Eastern and UTC. Report honestly: a failed trial is a result.

## Data (research/btcd_fractal/data/*_1d.csv, columns ts(ms),o,h,l,c,v; TradingView daily closes; fetch.py)

| Series | From | Note |
| --- | --- | --- |
| BTC.D | 2014-04-01 | pct, the target series |
| USDT.D | 2015-03-08 | pct; near zero before 2017 |
| TOTAL, TOTAL2, OTHERS.D | 2014-03/04 | USD caps; OTHERS.D pct (ex top 10) |
| TOTAL3, ETH.D | 2017-07-14 | TOTAL3 = cap ex BTC and ETH; ETH.D pct |
| BTCUSD | 2013-02-21 | |
| ETHBTC | 2016-06-25 | |
| DXY, US10Y | 2007 / 2005 | daily, weekdays |
| SPX | 2016-07-01 | weekdays |
| M2 | 1959 (monthly) | US M2, use with a 6-week publication lag |

Halvings: 2012-11-28, 2016-07-09, 2020-05-11, 2024-04-20 (next assumed 2028-04-15).

## What has been asked, and what was found (rounds 1-7; code study.py .. study7.py, results out*/)

1. Does 2018-now replay 2016-17 under a dynamic time warp with a re-levelled map? The warp puts today at the
   parent's 10 Dec 2017 week (the relief-rally top before the final waterfall) in 62% of 188 settings and has sat
   there since Feb 2023. As a forecaster it is 1.3-4x worse than no-change and not better than placebo parents.
   A local re-fit gives a weak 26-week move-size correlation (0.65 in sample, p 0.02-0.15 vs placebos).
2. Time dilation (child weeks per parent week): ~2x through 2021, 12-15x since; no law (by stage kind, progress,
   slope, speed) is significant against placebo parents. Local dilation is driven by BTC.D's own activity and,
   non-significantly, by M2 growth; not by halving phase or BTC drawdown.
3. Readiness (what preceded the three big waterfalls): every one began with BTC within 5% of its all-time high and
   M2 growing (+5-21% y/y). Of 14 point-in-time inputs only BTC drawdown and M2 y/y keep their sign in all three
   eras and beat a shifted-target null. A 14-input similarity-to-past-starts score has no precision.
4. Timing the 2021 waterfall out of sample from 2019-20 data: fractal clocks miss by 33-125 weeks; a plain halving
   clock (halving + 37 weeks) missed by 4 weeks, but over all 5+ point falls it beats random anchors only weakly
   (p 0.15) and its 2025 calls caught only a small rotation.
5. The same walk on USDT.D, TOTAL3, ETH/BTC: all sit at their parent's end; only BTC.D's beats placebos. Before
   each waterfall start ETH/BTC had risen 61% and TOTAL3 75% over the prior 26 weeks (today -2% / +3%); USDT.D rose
   into every start. TOTAL3 and ETH/BTC move with BTC.D in the same week (no lead); USDT.D has no lead.
6. The oracle trial (study7.py): in sample, 23 signals reach IC 0.56 with the next-13-week BTC.D logit change,
   carried by M2 and BTC blocks. Out of sample from 2019 (greedy selection refit every 13 weeks): the 13-week
   direction model INVERTS (IC -0.19; picks random-walk decoys at chance); P(5+ point fall within 13 weeks) AUC
   0.43; P(5+ point fall within 26 weeks) AUC 0.70 (0.75 / 0.75 / 0.72 by era) vs shifted-target null median 0.49,
   p95 0.69, p 0.05. That model reads 13% today (base rate 25%); it read 89-97% in Oct 2020 - Jan 2021.
   Most-picked signals: M2 y/y, BTC drawdown, ETH/BTC vs 52w high, BTC.D vs 52w high, USDT.D vs 30w mean.

## What has NOT been asked (seed list; the rethink panel should go beyond it)

- State, not date. Every round asked "when" as a point on a template. Nobody asked what STATE the market is in and
  what the transition hazard out of it is (HMM / Hamilton switching / semi-Markov durations).
- Switching coefficients. Round 7's sign inversion is what a Markov-switching regression models directly: the
  relationship between (M2, BTC drawdown, ETH/BTC) and the next BTC.D move flips with the regime.
- Sample size. Three big events at weekly scale cannot identify much. The owner's own premise (the market is
  fractal, self-similar) implies the same regime grammar at daily scale with hundreds of "mini waterfalls". Nobody
  has tested whether a regime model learned at daily scale transfers to weekly. If it does, the premise gains
  support and the forecast gains data; if not, the premise loses.
- Duration. "How long once started" has only three observations (35-182 days). Semi-Markov / hazard modelling of
  regime durations across scales could give a distribution, not a guess.
- Geometry. TDA (persistent homology on delay embeddings of the multi-series) and path signatures (iterated
  integrals of the path: lead-lag areas, curvature) as instability detectors or features, with the same adversaries.
- Volatility regimes. Waterfalls are high-volatility regimes of BTC.D and ETH/BTC; vol clustering precedes moves.
  No round used realized vol or vol-of-dominance as a state variable.
- Is "no forecast" the truth? A proper test that the best achievable skill is the base rate plus the two readiness
  conditions, and what honest claim follows.

## Baselines any new model must be judged against (weekly, 2019-2026 out of sample)

- Base rate: a 5+ point BTC.D fall within 26 weeks happens from 25% of weeks (10+ points: 9.6%); within 13 weeks 15%.
- Round 7 logistic: P(5+ point fall within 26 weeks) AUC 0.70, shifted-target null 0.49 (p95 0.69).
- Readiness rule: BTC within 5% of its high AND M2 y/y > 0: fires before all three big waterfalls; precision unknown
  on the small ones (compute it).
- Round 4 composite (sign-stable features): IC 0.33 pooled, fades to 0.09 in 2023-26.

## Module contract (for every new model, study8_<name>.py)

- `python3 research/btcd_fractal/study8_<name>.py --data research/btcd_fractal/data --out research/btcd_fractal/out8/<name> [--nulls N] [--fast]`
  `--fast` must finish in under 3 minutes (smoke test); the full run under ~20 minutes on 4 cores.
- Use `study8_common.py` for data, features, targets, the walk-forward harness, metrics and nulls (so every model is
  judged the same way). Add model-specific features in the module, not in common.
- Write `<out>/results.json` with: `oos` (metrics by era and pooled for targets `fall5_26w`, `fall10_26w`, `y13`
  and any model-specific outputs), `null` (the shifted-target distribution and p for each headline metric),
  `today` (the reading now and what drives it), `series` (the prediction / regime-probability series, thinned),
  `notes` (anything the reader must know). Print a summary of at most 60 lines. Charts to `<out>/*.png` optional.
- numpy / pandas / numba / matplotlib are on the runner; `hmmlearn` and `ripser` are pip-installable there; anything
  else must have a numpy fallback. No network access inside a module.
- Never use the future: see rule 1. Reviewers will look for it specifically.
