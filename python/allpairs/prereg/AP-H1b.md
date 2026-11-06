# Pre-registration AP-H1b: lead_btc's gain is the candle-touch maker fill rule on wide books, not lead information

Written 2026-11-06 00:00 UTC (Nov 5 7:00 PM EST). At that time the HO-1 card of run 42127527423 had **not** been
posted or read: no lead_btc or keep_crossed HO-1 number was known. Source: the institutional-research diagnosis of
the all-pairs family (/mnt/project-files/institutional-methods/failure-diagnoses.md, "All-pairs entry/exit payoff
matrix"), with the operational choices below fixed here, before any result.

## Hypothesis
lead_btc's walk-forward gain (+$0.74/h, run 42100397043) comes from the candle-touch maker fill rule on books wider
than 10c, not from lead information. BTC/ETH 1-minute returns are already in the Kalshi quote by the bar close.

## Quantities (all on H-HOLD Aug 1-Nov 4 2026, HO-1 folds, one fit per arm on Apr 18-Jul 29)
- **Paired gain G(rule)** = $/h of lead_btc minus $/h of keep_crossed (config `base`, the same hash da11163cef), both
  under the same fill rule, on the same held-out hours.
- **G_base**: both configs under the base arm. It is taken from the follow-up run's own re-run of the two base arms,
  which must reproduce run 42127527423's base arms exactly (the same $/h, trades and folds). If they don't, the
  batch is void.
- **G_strict**: both configs under the new `strict` arm, which changes only one thing: `strict_maker` (a maker
  entry or exit fills only when the next minute trades through our price, not on a touch). Fees, slippage and
  spread caps are unchanged.
- **Wide-book share W**: the share of lead_btc's base-arm |P&L| from entries on books wider than 10c (ask minus bid
  at the decision minute, logged per trade). This is the registry's G1b measure.
- **Placebo gain P** = $/h of lead_btc minus $/h of lead_shift24 (the base arm for both). lead_shift24 is lead_btc
  with every lead feature taken from the same minute 24 hours earlier: the same distribution, with no information
  about the window.
- **Noise unit**: $0.92/h (2x noise, from the diagnosis).
- **CIs**: 24-hour block bootstrap of the paired hourly differences (the engine's block_bootstrap_mean, 2,000 draws).

## Predictions
- **P1**: G_strict <= 0.5 x G_base, and W >= 50%.
- **P2a** (mid response): on live-tier minutes, the Kalshi mid's response to the lagged BTC return has |t| < 2.
  Read from the shared mid-response job (H-B SHARED-MIDLAG), not from a separate regression here.
- **P2b** (skill on tight books). The all-pairs entry model predicts the dollar value of a position, not P(YES), so
  the skill test uses a settlement classifier instead:
  - Two LightGBM classifiers of P(settle YES) are fitted on H-DEV decision minutes, with keep_crossed features and
    with lead_btc features.
  - Each is scored on H-HOLD decision minutes whose book is 10c wide or less.
  - The score is Brier skill against the FLB-corrected mid. The FLB map is an isotonic map of mid to P(YES),
    fitted on H-DEV only.
  - The skill change is dBSS = BSS(lead) - BSS(base). P2b holds if dBSS lies within +/-0.002 (TOST at 5%, day-block
    standard errors).
- **P3**: P lies within +/-$0.92/h (90% CI inside the band).

## Decision rule
- **Falsified** if any of these holds:
  - G_strict >= $0.92/h with W < 50%;
  - the P2a slope has t >= 3;
  - dBSS > 0 with Diebold-Mariano p < 0.05 (per-window Brier differences, day-block HAC);
  - P > $0.92/h with its 95% CI above 0.
- **Confirmed** if P1, P2a, P2b and P3 all hold.
- **Undecided** otherwise. An equivalence test that is too wide to decide (underpowered) counts as undecided, not as
  support.
- **No gain to explain.** If G_base <= 0, the gain has vanished under HO-1. P1 is then moot, and that is reported.
  P2 and P3 are still scored as information.

## Runs (GitHub, all-pairs.yml, after runs 42127527423 and 42127586982 drain)
- **Study jobs (6):** configs {base, lead_btc, lead_shift24} x arms {base, strict}, under `--protocol ho1`.
- **Skill job (1):** the two classifiers for P2b. It runs on the same data and fits on H-DEV only.
- **Report (1):** G_base, G_strict, W, P, dBSS, P&L by spread bucket (<=5c, 5-10c, >10c) and by fill type (taker,
  maker), and by tier (historical before Sep 12, live from Sep 12).
- **Lockboxes:** L1 (Nov 6 05:00-Nov 13 05:00 UTC) and L2 are never loaded.
- **Logging:** each trade logs entry spread, fill type, the model's predicted value, the decision mid and the tier.
  Logging must not change any result, which the reproduction check above verifies.
- **Queued, not dropped:** hurdle_lcb and stale_quote.

## Amendment 1 (2026-11-06 00:25 UTC / Nov 5 7:25 PM EST: after the HO-1 card of run 42127527423, before any follow-up result)
- **G_base = 0.** In run 42127527423, lead_btc's base arm had 0 trades, and so did keep_crossed's (config `base`,
  da11163cef). In both, the hurdle was off in all 6 folds: no hurdle paid on the H-DEV validation days. So the
  "No gain to explain" branch applies: P1 is moot, and W is undefined because there are no trades.
- **Dropped:** the strict arm for base and lead_btc, and their base-arm re-runs. G_strict is moot, and an arm with 0
  trades cannot show whether the new logging changes results. The logging check moves to maker_only base and tight,
  which must reproduce run 42127527423 exactly (see AP-H2). If they don't, the batch is void.
- **P3:** P = lead_btc base $/h (0, from run 42127527423) - lead_shift24 base $/h (follow-up). It is read as
  information, with the same band and the 24-hour block bootstrap of the paired hourly differences.
- **P2b specification**, fixed here:
  - **Rows:** every YES-side decision minute k >= 1 with a two-sided book, of BTC, ETH, SOL and XRP windows.
  - **Fit:** on H-DEV, Apr 18 to Jul 29, using the run's training filters (min_real_frac 0.8, max_crossed 99).
  - **Score:** on H-HOLD, Aug 1 to Nov 4, on minutes whose book is 10c wide or less at the decision minute.
  - **Features:** the same as the configs, base.json against lead_btc.json.
  - **Model:** LightGBM, binary objective. num_leaves 31, learning_rate 0.05, min_data_in_leaf 500, feature_fraction
    0.8, bagging 0.8 every round, lambda_l2 1.0, seed 7.
  - **Rounds:** at most 2,000, with early stopping (50 rounds) on the last 10 H-DEV days after a 1-day embargo.
  - **FLB map:** an isotonic map of YES mid to settlement, fitted on the same H-DEV rows.
  - **Score difference:** dBSS = (BS_base - BS_lead) / BS_ref, where BS_ref is the Brier score of the FLB-mapped mid on
    the scored minutes.
  - **Standard error:** from daily sums of the per-minute differences. It is the ratio estimator's Newey-West variance
    across the held-out days, with Bartlett weights and lag 3.
  - **TOST:** P2b holds if the 90% CI lies inside +/-0.002.
  - **Diebold-Mariano:** two-sided p from the same t. The falsifier is dBSS > 0 with p < 0.05.
- **Verdict:** P1 is moot, so AP-H1b cannot reach "Confirmed". It is reported as "no gain to explain", with P2a, P2b
  and P3 as information. If a falsifier on P2a, P2b or P3 fires, it is reported as evidence of lead information that the
  all-pairs policy did not turn into a tradable gain.
