# J22 and J06 — frozen job cards (draft; execution has not started)

Repository: `Wickedrad/coinbaseTraderBot`. Date: November 15, 2026 (EST = UTC−05:00). Source of numeric conditions: owner's November 14 profit-plan brief. This card MUST NOT replace `ralph/pins.json` or `python/ralph_eval/**`; both are protected and require explicit owner approval.

## J22 — FIRST: daily directional consistency

**Risk / state:** R0 / queued. **Purpose:** Before spending on fee levers, determine whether the frozen **Oracle heat lane** chooses a direction that achieves an executable fee-net sellable price window more often than same-contract, same-minute random side. Do not score the old maker-pricer or Atlas curves as if they are the Oracle heat lane.

**Private inputs (one row per frozen ex-ante selected opportunity; not just winning fills):**

- `private/scored-YYYY-MM-DD.jsonl` from an independently parity-tested one-test scorer. Required columns: `day` (UTC YYYY-MM-DD), `asset` (BTC/ETH/SOL/XRP), `kind` (`15m` or `hourly`), `side` (`yes`/`no`), `h` (15/60), `ticker` (private contract identifier), `asof_ms` (UTC milliseconds, ex-ante), `status` (`scored` / `incomplete` / other), `called_window` (bool/nullable), `opposite_window` (bool/nullable), `slot_ms` (UTC cluster boundary), optional `regime` (known at entry), `pack_sha`, `source_mode` (`forward` or `historical_shadow`).
- `private/coverage.json`: `full_days` list attested by the independent capture verifier, with provenance for timestamp continuity, book freshness, every eligible contract/coin and hourly strikes; source hashes and curve pack identity. An all-candidate log including no books, skipped calls, and quote gaps, so omission cannot inflate success.
- `--start-day`: **fixed before outcomes are inspected**, at the start of the prospective 12-consecutive-UTC-day window; earliest actual date depends on archived full-book coverage. The local script never discovers the most favorable 12 days.

**Output (public, aggregate-only):** `j22-direction-scoreboard.json`: `schema`, `job`, `trial_count`, `start_utc`, `end_utc_inclusive`, `scorable_days`, `full_book_missing_days`, `daily_positive`, `daily_required`, `positive_days_condition`, `overall` with `gap`, `se`, `mde_gap`, `clusters`, `n`, `daily[]` with public cells >=5 only, and `splits[]` by coin, side, kind and (if supplied) regime. No tickers, calls, private paths or single trades in public output. A separate private row file remains outside GitHub.

**Calculation:** for each eligible ex-ante call, `called = 1` if the called side passes the one test, else `0`; `opposite = 1` if the opposite side passes. Same-minute random-side expectation is `(called+opposite)/2`. Paired difference is `called-(called+opposite)/2`. On each full-book UTC day, average that difference across eligible first-contract observations. A day is positive only if the paired difference is strictly >0. **Owner-approved consistency gate: ≥9 positive days of 12 full-book days, with no coin/side clearly negative.** The numeric criterion for “clearly negative” is not yet pinned—show interval estimates descriptively and require a protected evaluator pin before a binding result. Report all missing/incomplete/excluded calls, denominators, and shared-book covariance. This job is not enough on its own to satisfy Stage D: J06 must also sign the 2×SE direction result.

**Errors versus failing evidence:** missing source, incomplete day, unverified book, a missing counterfactual side, a curve pack mismatch, a changing policy or less than 12 complete days = **blocked/underpowered**, not a negative-direction result. A properly measured 12-day outcome with <9 positive days is a **numeric fail**, but only the protected grader may record that verdict. Any subgroup with low support is `insufficient_support`, not “non-negative.”

**Stop / safety / token:** code-only R0 plus one correctness critic, 0 external model calls required for running a deterministic script. STOP, timeouts, lease and budget are checked by the future runner; report MDE and `trial_count:1` before any scoring run. No additional look beyond the registered date. No curve edits and no server reads from this job card.

## J06 — SECOND: unseen-2026 historical direction, in actual Kalshi contract terms

**Risk / state:** R0 / queued, **data-blocked until a qualifying historical book source is confirmed**. **Purpose:** Test the frozen Oracle heat curves' actual direction calls on 2026-08-01 00:00 UTC through 2026-11-04 23:59 UTC. These dates are after the OR-HM1 heat model's 2025 fitting period, but replaying them now is *retrospective historical shadow*, not contemporaneously published forward evidence. Do not confuse this Oracle pack with Atlas models trained through October 2026.

**Required private inputs:**

1. `calls-YYYY-MM-DD.jsonl`: pre-decision `asof_ms`, `bar_close_ms`, `ticker`, `asset`, `kind`, `h`, `side`, `call_key`, `rank`, `pack_sha`, `source_mode`, `selector_verified=true`. These are recomputed using the **frozen** OR-HM1 heat pack; ensure the row's computed features are closed before `asof_ms`, and no later information chooses the call or strike. Hourly nearest-50c selection must be checked against *all contemporaneous eligible strikes*, not only selected fills.
2. `markets-YYYY-MM-DD.jsonl`: `ticker`, `asset`, `kind`, `open_ms`, `close_ms`, `tick`, `price_ranges` (optional only if a valid uniform tick is supplied), contract fee type and effective schedule; the exact market IDs stay private.
3. `books-YYYY-MM-DD.jsonl` plus the next-day close tail: `ticker`, `t_ms`, `yb`, `ya`, `ybs`, `yas` (best YES bid/ask + displayed depth); timestamps at receipt; quote gaps and reconnects explicitly attested. No synthetic/interpolated quote or guaranteed maker fill.
4. `coverage.json`: independent verifier's list of **full-book UTC days**, contract universe completeness, replay source SHA, fee schedule and market-price-grid provenance. Missing data never becomes a 0 or a 1. Private Drive storage and server allowlist must be approved by owner; no per-trade rows in the public repository.

**Exact one-test:** A selected market has two-sided book and legal entry window. Buy at the first recorded touch no more than 20s after decision, with a $10 theoretical stake (`contracts=max(1,floor(10/side_ask))`, price 10c–90c). Using the true price grid, find the lowest exit bid at which selling the full size pays the purchase price, the entry and exit taker fees, **plus 1 cent per contract**. The called side's *best bid* must hold at/above that level for **at least 60 continuous seconds** after entry, with sampled gaps ≤25s, before the final 90s of a 15-minute contract or the final six minutes of an hourly contract. Any book gap >60s before deadline = **incomplete**. The depth-adequate version is reported, not binding. Use `research/heatmap_live/score.ts` and `bot/fees.ts` as parity reference, not an independently changed grader.

**Same-minute random-side control:** score the opposite side on the exact same market and quote stream and compare `called − (called+opposite)/2`. Bootstrap the entire set of coins within each common 15m/hourly *time slot* together (not independent fills). Primary numeric gate: **positive gap ≥2 × its standard error**, with eligible denominators and the predeclared source cut. Report early price-window timing, length, wrong-way dip, 15m versus hourly, coin/side/regime, and the difference from persistent-side prior separately; these diagnostics cannot substitute for the required gate.

**Outputs:** per-day private scored rows; aggregate public `j06-history.json` with n, slot-cluster count, `called_rate`, `random_side_rate`, paired gap, bootstrap SE, `mde_gap=2*SE`, `above_2se` diagnostic, coverage days, per-coin/side/kind splits if n≥5, provenance/fee verification booleans, trial count = 1, and blocker reasons. Do not print private paths, ticker, per-trade fees or individual histories in public output.

**Errors versus fails:** missing August–November historical bid/ask snapshots, unable to reproduce authentic historic contract listings and strikes, synthetic replay books, unverified fee type, incorrect price grid, missing hours or matched controls → **blocked_on_owner(data)**. Complete eligible records with measured gap <2×SE → **numeric fail** (protected grader only). Too few slot groups → **underpowered**. A model cannot promote itself.

**Stop / tokens:** one R0 code-maker plus one correctness critic. No token-consuming subagents are dispatched by the scripts. STOP, approved caps, one lease, trial ledger and fixed look are future-runner responsibilities. A second candidate with changed heat rank, timestamp, entry selector or fee assumption is **another counted trial**, not a “retry of the same test.”

### Source alignment and evidence gap

- `research/heatmap_live/PREREG.md` and `score.ts` contain the existing one-test definition. Its current scorer is research, not necessarily the final protected evaluator; do not swap it silently into `python/ralph_eval`.
- `python/heat_reader/reader.py` already writes `heat_calls-YYYY-MM-DD.jsonl`; the records are raw fired signals, *not* necessarily complete ex-ante chosen Kalshi contracts. An adapter must match the heat-lane's selection and archived market catalog. User's brief says the server retains only 14 days, making S1 archival urgent.
- `python/lossreview/builder.py` and `schema.py` already define private trip rows, pre-order versus post-order columns and fidelity flags. A trip-only dataset omits unfilled calls and negative controls; **J06/J22 must draw denominators from the whole eligible call+book stream**.
- Only roughly 3.5 full-book recorded days after Nov 10 are confirmed by the supplied brief. Whether a separate 2026 Aug–Nov *true Kalshi order-book* archive exists is unknown. The 121-day historical replay manifest previously inspected is NOT proof that 10-second quotes and both sides existed with sufficient continuity. The historical J06 proposal is blocked until data quality is demonstrated.

### Draft-only usage, when independently approved for execution

The example commands are **templates only** and were not executed:

```sh
# Run from repository root; PRIVATE paths stay on a runner/local/private Drive sync, NOT inside GitHub.
PYTHONPATH=python python3 -m ralph.j06_window --day YYYY-MM-DD \
  --calls PRIVATE/calls.jsonl --markets PRIVATE/markets.jsonl --books PRIVATE/books.jsonl \
  --private-output PRIVATE/scored-YYYY-MM-DD.jsonl --public-output PUBLIC/j06-day.json

PYTHONPATH=python python3 -m ralph.j06_rollup --scores PRIVATE/scored-*.jsonl \
  --coverage PRIVATE/coverage.json --from-day 2026-08-01 --through-day 2026-11-04 \
  --public-output PUBLIC/j06-history.json

PYTHONPATH=python python3 -m ralph.j22_scoreboard --scores PRIVATE/scored-*.jsonl \
  --coverage PRIVATE/coverage.json --start-day YYYY-MM-DD \
  --public-output PUBLIC/j22-direction-scoreboard.json
```

All Python commands shown in a shell must expand `scored-*.jsonl` **inside the private workspace**, not the repository. A future protected runner should validate source hashes, as-of selection and fee parity, and lock trial identity before invoking any statistic; these diagnostics are deliberately insufficient for a binding Stage D pass.