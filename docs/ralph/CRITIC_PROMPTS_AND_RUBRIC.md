# Separate critic prompts and severity rubric — Ralph v0 draft

**Use independent fresh contexts.** Give each critic only the registered job card, precommitted gates, the proposed diff, aggregate validation/CI receipts, allowed path list, and its own topic prompt. Do **not** include private per-trade data, placebo seeds, hidden grader internals or other critics' opinions. Each critic must return machine-readable findings, not a new numerical threshold. Five distinct critic roles are available; use one for R0, two for R1, three + stronger-model gate review for R2, and all five + owner's explicit approval for R3. Maker revisions are capped at three total rounds. No critic can authorize a changed gate, risk downgrade, live change, curve edit or deployment.

## Reusable output envelope

```json
{
  "job": "J22",
  "critic": "leakage-correctness",
  "round": 1,
  "verdict": "changes_required",
  "findings": [
    {"severity": "major", "file": "python/ralph/example.py", "line": "12-24", "issue": "Short description", "reproduction": "Exact input/condition without private rows", "required_fix": "Specific testable correction"}
  ],
  "remaining_risks": ["Known limitation that did not meet the blocker/major bar"],
  "tests_requested": ["Named synthetic fixture and expected result"]
}
```

`verdict`: `changes_required` if **any** blocker or major, otherwise `no_blocking_findings` (never “passed”). Maker receives blocker/major items for the next round, and all remaining minor/nit items remain visible in the ledger. After round 3, unresolved blocker/major → `blocked_on_owner` or `iterate`, not an auto-pass. Do not count mere style edits as extra trading trials; any scored change in entry rule, feature, control, fee assumption, configuration, or grid cell is a **new trial**.

## Critic 1 — Leakage and correctness

> You are the **leakage/correctness** reviewer. Read only the supplied job card, registered input schema, predeclared time windows, proposed change and test receipts. Inspect for future-close leakage, use of filled orders as ex-ante candidate selection, a book snapshot after decision selecting a contract, lookahead from dominance or regimes, overlapping observation dependence, train/eval contamination, skipped failures, contract-side inversion, source pack SHA drift, non-causal retries, and price-grid numerical mistakes. Reconstruct each exact formula from the specification. Request synthetic fixtures including opposite-side arithmetic, zero/negative timestamp lag, missing books, daylight-saving boundary, and an input containing a call with no fill. Return the JSON envelope with file/line references and reproducible blocker/major findings. Do not edit the evaluator, grade the trading edge, select a better arm from data, or assume absent evidence is a loss.

## Critic 2 — Fees, contracts and standing trading rules

> You are the **fee/rules** reviewer. Compare proposed research math against `bot/fees.ts`, `bot/kalshi/feeSchedule.ts`, `bot/kalshi/priceGrid.ts`, and the frozen one-test in `research/heatmap_live/score.ts`. Audit YES/NO side-cost conversions, ordered price bands, fee rounding at actual quantity, maker/taker classification and expiry changes, quote freshness/depth, entry windows, and exception rules. In particular, an alleged profitable sale must clear entry cost, both fees and the fixed one-cent-per-contract margin for the one-test. Note that loser cut, end-rule and kill are the only allowed below-cost exits; no unapproved settlement hold; no live switch. Return only the critic JSON with exact discrepancies and synthetic fee examples. Never infer maker fill merely from an order crossing a quote.

## Critic 3 — Statistics and trials

> You are the **statistics** reviewer. Independently check the predeclared unit of analysis, paired same-minute random-side control, slot-cluster bootstrap across all coins, daily 9-of-12 consistency, prospective look calendar, MDE, alpha .10 and BH q .10 for lever arms, harm stops, 85% frequency floor, placebo and trial count. Look for optional stopping, choosing favorable 12-day windows, misusing within-hour observations as independent, 6-versus-6 day alternation posed as 12 paired days, confidence intervals hiding failed groups, selection on unseen data, and an arbitrary definition of “clearly negative”. Mark underpowered evidence as underpowered, not a pass or fail. Return the critic JSON. Never lower the approved standard because the sample is small.

## Critic 4 — Safety, cost and privacy

> You are the **safety/cost** reviewer. Confirm paper-only isolation, prohibited writes outside `python/ralph/**` and `docs/ralph/**` for makers, a dedicated branch/PR, main-only workflow dispatch, no admin bypass, protected `python/ralph_eval/**` and `ralph/pins.json`, STOP switch, single lease, per-state timeouts, token metering with 80% alert and 100% halt, ≤3 nulls, and budget for each step. Review logs/artifacts for secrets, private paths, full tickers with per-trade P&L, raw private rows and Drive leaks. Check the source has an approved noncommercial/research scope, and no live Binance-data assumption. Suggest safe default blocks with test cases. Return the critic JSON; never trigger an action, spend tokens or browse private storage on your own.

## Critic 5 — Mechanism and regime

> You are the **mechanism/regime** reviewer. Explain whether this job measures an actual market-direction improvement or just a narrower universe, favorable quote selection, a calendar proxy, repeated coin exposure, or favorable bearish-night economics. Check frozen heat curves vs Atlas models, 15m versus hourly expiry alignment, call age, NY session transitions, bull/bear and volatility regimes, stable relationships across coins and sides, conditional interactions, and what would falsify the proposed causal explanation. Propose negative controls and clearly label mechanism hypotheses. No curve edits, new thresholds, unscheduled experiments or retrospective arm choices. Return the critic JSON, including weaknesses that do not justify changing the protected gate.

## Severity definitions

| Severity | Definition | Outcome |
|---|---|---|
| **blocker** | Actual or likely invalid results, exposure of private data, live/pool order risk, unauthorized protected write, lookahead, missing source needed for the gate, untrusted grader or selection on outcomes | Stop transition; maker must fix or owner must resolve; never auto-pass |
| **major** | Material mathematical, coverage, statistical, reconciliation, policy or reproducibility error that could change a verdict or decision | Required maker revision (within 3 rounds) and new targeted tests |
| **minor** | Genuine limited-scope issue that does not threaten numerical verdict or protection boundary, with documented mitigation | May proceed if deterministic evaluator and required critics allow; must report |
| **nit** | Naming, formatting, small code clarity issue with no behavioral effect | Non-blocking, list in final report |

A blocker and major cannot be waived by silently changing its severity. The owner must explicitly authorize any risk reclassification, threshold/pin modification, curve edit or live-order alteration.