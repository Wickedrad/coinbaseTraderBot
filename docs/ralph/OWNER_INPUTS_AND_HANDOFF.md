# Owner inputs, availability and first handoff

## What repository code already supplies (read-only GitHub review, Nov 15, 2026)

- `python/oracle/heat.py`, `python/oracle/heat_pack.py`, `python/oracle/heat_pairs.py`, `python/oracle/prereg/OR-HM1.md`: the frozen heat-study vocabulary, 1/5/15/30/60-minute direction measurements, pair/triple relationships, 2020–2025 fitting/check boundaries and pack provenance. Avoid confusing this with earlier Atlas 406-curve models.
- `python/heat_reader/reader.py`, `docs/HEAT_READER.md`: one-minute writer of the daily `heat_calls-YYYY-MM-DD.jsonl` file and the latest atomically published `HeatCallsFile`. Raw calls **do not themselves establish** chosen contract, filled entry, full book availability or exit window.
- `bot/heat/types.ts`, `bot/heat/heatLane.ts`, `bot/heat/heatBook.ts`, `docs/HEAT_LANE.md`: Kalshi heat lane's contract selection and plan ownership. Heat is one IOC taker entry at touch; the plan handles exits. Compare live branch's actual source and config only with explicit owner/server access.
- `research/heatmap_live/score.ts`, `research/heatmap_live/PREREG.md`: **canonical existing 'one test' research code**: first ask, $10 stake, fees/grid, best bid held 60 seconds, no >25s sample gap, >60s record gap = incomplete, contract-specific sale deadlines, same-minute random-side control and time-slot bootstrap.
- `python/lossreview/builder.py`, `schema.py`, `daily.py`, `docs/LOSS_REVIEW.md`: private trip reconstruction, `ex-ante` feature registry and fidelity flags; daily trip documents are not denominators for all possible calls. The loss-review budget and weekly review are not a replacement for Ralph's protected evaluator.
- `bot/fees.ts`: effective taker fee mechanics and balance-grid rounding. **Do not hardcode a universal maker fee of zero for every series/date** without fee-type provenance.

## Exactly what the owner should locate (do not paste raw rows or keys into public chat)

| Dataset / receipt | Required columns or evidence | Time coverage | Why | Availability |
|---|---|---|---|---|
| Frozen heat model provenance | Curve `run`, `pack_sha`, effective modeling cutoff, pack files and hash receipts | OR-HM1 frozen as of Nov 11, 2026 | Ensure J06 historical observations were not used to fit/select curves | Oracle source code present; exact private pack hashes need owner |
| Heat call archive | UTC `writtenAt`, per coin `asOf`, `calls[]`: `barClose`, `h`, `dir`, `rank`, `key`, `tf`, `kind`, pack SHA, `ok` | Nov 11 forward; historical Aug 1–Nov 4 must be replayed causally | Entire call denominator, not just fills | Server reportedly keeps 14 days; S1 priority; private Drive archive unverified |
| Contract catalog | Ticker kept private; asset, 15m/hourly kind, `open_ms`, `close_ms`, tick/`price_ranges`, strikes, fee type/effective date | Aug 1–Nov 4 for J06; each forward day for J22 | Valid contract and nearest-50c strike selection at time of call | Unconfirmed |
| Timestamped Kalshi books | UTC `t_ms`, YES bid/ask and depth (`yb`, `ya`, `ybs`, `yas`), reconnect/gap markers, snapshot provenance | **Full Aug 1–Nov 4 if J06 is to bind**; 12 full forward days for J22 | Real, saleable 60s fee-net windows | **Critical unverified blocker**; brief confirms only ~3.5 full-book days since Nov 10 |
| Full-day health attestations | For each UTC date and eligible coin/contract: coverage completeness, duplicate/missing time ranges, source SHA | Fixed pre-registered period | Prevent choosing only successful/recorded opportunities | Not verified; code cannot self-attest |
| Historical fee schedules | Per series/event effective-dated fee rate, multiplier, member balance precision, grid at execution time | Same as quote archive | Ensure 1c-over-both-fees one-test is valid | Current implementation exists; historical schedule validation needed |
| Private trip/audit files | Ex-ante call/order, actual fill price/count/fee, plan sale, P&L, `fidelity_flag`, loss reason | Existing daily loss-review folder, Nov 11 onward | J00/J07/J02a economics/parity, not J06 denominator | Private Drive; not read or copied in this chat |
| Paper cash and deposits | Initial pool, every refill/deposit, realized fee-net P&L, open funded positions | Oct 9 onward, frozen $200 study from owner's chosen start | Judge P&L against money put in, not dashboard cash | Only aggregates in brief, full recon unverified |
| Clock and session/regime labels | UTC ms, Eastern local time, asset, regime label known *as of* timestamp, source version | Aug–Nov historical and future | J22 breakdown, avoid future-regime leakage | Market-clock exists; per-call archival label not yet verified |
| Model/critic usage allowance | Weekly token ceiling and exact Tuesday reset time, whether strongest-model usage requires separate permission | Current and upcoming runs | Avoid unauthorised Claude spend; ChatGPT has no visibility into Claude limits | Open item |
| Protected storage and code permissions | Writable private ledger destination, GitHub branch/PR rights, Drive folder ID, STOP owner, who pins evaluator | Before Ralph mutates anything | Durable single source of truth and risk class review | GitHub read confirmed; write previously 403; Drive write unverified |

## Essential interpretation

- **August 1–November 4 may be unseen relative to the frozen OR-HM1 fitting window, but retrospective reconstruction in November is not a live forward forecast.** A real Kalshi book record with honest timestamps is necessary for J06's contract-level 'one test'. Historical spot prices or interpolated Kalshi bids cannot certify it.
- The confirmed one-test scorer in `research/heatmap_live/score.ts` belongs to an older capture and is a starting numerical reference, not the newly approved protected deterministic grader. **Parity-test every rule and fee detail** before approving the new runner.
- Stage D needs **both** the 2×SE paired gap and 9-of-12 consistency. With 3.5 days of full-book data, a J22 verdict cannot mature regardless of the model's sign accuracy.
- Prospective trial dates, SHA receipts and one-day embargo are registered before forward outcomes. Exploratory reads quarantine those same days as confirmation for the selected configuration.
- “No clearly negative coin/side” was approved as a principle but no significance threshold was specified. Do not fabricate one or silently convert “insufficient” into “not negative”. Ask the owner to pin the deterministic definition in the protected evaluator.
- Review outputs may contain publicly shareable *aggregate* numbers and cell counts of five or more. Raw tickers, private Drive paths, P&L trade rows, keys, credentials, and private agent messages stay outside GitHub artifacts and public chat.

## Usage/storage proposal, not an executed decision

- **Recommended:** a single `ralph-state` private branch or private Drive folder with append-only machine-readable ledger/events, plus PRs limited to `python/ralph/**` and `docs/ralph/**`. Ensure no row-level private data is committed even on the state branch of a public repo. All human-readable `ledger.md` releases contain aggregates only. A separate owner-controlled protected source stores `ralph/pins.json` and the evaluator.
- Current ChatGPT can produce local downloadable files in this conversation; it cannot assert that this folder is persistent across all chats. A GitHub branch write previously returned **HTTP 403**; it was not retried today. Drive destination/permissions have not been established, and no private Drive records were read during this plan.
- **Codex handoff:** attach this package to Codex with repo access and instruct it to open a PR (never a push to `main`), review existing code and adapt only under `python/ralph/**`, `docs/ralph/**`. The protected evaluator is **owner-only**. These scripts are drafts, and the runner must first add synthetic parity fixtures and source attestation.

## Three open decisions requested from owner

1. What is the Claude-side **weekly token budget**, and exactly **when Tuesday does it reset**? Please give the time in **EST and UTC** (EST = UTC−05:00 in November); do not use overage. This does not restrict ChatGPT's work now.
2. Is Binance-derived data authorized for **live trading use** after any necessary provider license/terms review, or is it still **research and paper only**? Until affirmative verification, only research/paper use is allowed.
3. Where do you want the durable Ralph **ledger, queue and verdicts** stored and synchronized between chats—private Drive folder or a protected repository state branch—and which connection should be authorized to write to it? GitHub branch creation was blocked by the current integration.

Optional urgent data clarification: Does your private Drive contain **actual timestamped, two-sided Kalshi order-book snapshots** for 2026-08-01 through 2026-11-04, or only candle/settlement/replay aggregates? This determines whether J06 can be evaluated as currently written. Do not upload per-trade book rows into public GitHub.