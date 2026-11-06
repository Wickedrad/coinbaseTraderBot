# OR-AMEND-1: every confirmed setup trials on HO-1 (descriptive); lockbox L1 selection rule (amends OR-H1 and OR-H2)

Owner instruction (Steven, 2026-11-06 14:03 UTC / 9:03 AM EST), verbatim:
> "After it concludes we need to figure out why losers are losing and regardless let all of them trial on real unseen data."

Written 2026-11-06, before any HO-1 number of any oracle-setups contract type exists. At the time of writing: OR-H1 run
42176343914 froze zero setups (confirmed on discovery B: perp 439, pp15 400, pp60 320, tennis 242; none survived BHY at
q 0.10), so no pre-registered HO-1 opening has happened; the OR-H2 perp-rev run 42231227389 is mining. This file is
committed with the code that applies it (python/oracle/ho1.py `--all-confirmed`, python/oracle/losers.py) and is frozen
before that code computes any HO-1 number. Never compared to paper trading. NEVER DOGE.

## 1. All confirmed setups trial on HO-1 (descriptive, not a pre-registered test)
- Per contract type, every setup in the miner's confirm.jsonl (not only frozen.json) is scored on HO-1 (Aug 1 - Nov 4 2026,
  96 days), each traded and judged exactly as a frozen setup: the same per-setup evaluation (one position at a time per
  asset / event, the primary exit), the matched random-entry placebo (8 seeds), the six 16-day folds, the RV terciles (tennis:
  tours), registry ho1_pass, hit rate vs the matched base, and BHY at q 0.10 at m = every confirmed setup of the type.
- This is a **descriptive trial**. HO-1 is no longer a clean final test for these setups: every confirmed setup has now
  seen HO-1, and choosing among them by their HO-1 numbers is selection on HO-1. No HO-1 result of this mode is a
  pre-registered pass, and none of it may enter a rulebook directly.
- Registry rows: thread `oracle-setups`, family `oracle-<ct>-allconf-v1` (not the pre-registered family `oracle-<ct>-v1`),
  role candidate (one per setup, each with its placebo row and the flat control), flags `all-confirmed` and
  `DEV:all-confirmed-descriptive` (the registry's DEV: prefix keeps the rows out of the validated ledger). No book row.
- Consequence for the pre-registered path: once a contract type's confirmed setups have all seen HO-1, a later
  pre-registered frozen opening of that type is no longer clean and is refused by the workflow (the ledger
  models/oracle-setups/ho1/openings.jsonl records the all-confirmed opening under its own key, mode `all-confirmed`). An
  all-confirmed opening is never blocked by, and never consumes, a pre-registered frozen opening; when a run froze setups,
  its pre-registered frozen file is opened first: the workflow refuses an all-confirmed opening of a type whose run froze
  one or more setups while the ledger holds no frozen opening of that type.
- One all-confirmed opening per contract type (it fixes the lockbox candidates). A retry is allowed only when the earlier
  all-confirmed opening is of the same confirm.jsonl, its run has completed, and it wrote no lockbox_candidates.json (it
  failed before the selection); the retry is logged with `retry_of`.

## 2. Lockbox L1 selection rule (fixed here, before any HO-1 number)
- Per contract type, the candidates are the setups that pass the HO-1 rules in the all-confirmed trial **before BHY**:
  registry ho1_pass (>= 90 days, >= 4 of 6 folds won, worst fold >= -$0.50/h, >= 2 of 3 strata with >= 100 h won, worst
  stratum >= -$0.50/h, beats its placebo), beats its matched placebo, and HO-1 hit rate above the matched base.
- They are ranked by HO-1 $/h (ties by setup id) and the **top 10** go to lockbox L1. ho1.py `--all-confirmed` writes
  exactly this selection to `lockbox_candidates.json` (with this file's SHA-256). Nothing else is added or removed later.
- Lockbox L1: the decisions whose **whole horizon lies inside 2026-11-06T05:00Z to 2026-11-13T05:00Z** (half-open), the
  same convention as every other split (python/oracle/common.py `split_of`: a row belongs to a window only if its decision
  and decision + h minutes both fall inside it; for Kalshi and tennis the contract's horizon as `split_of` applies it). A
  decision whose horizon ends after 2026-11-13T05:00Z is not an L1 row, by rule. Positions held to settlement (Kalshi, tennis)
  are scored with their settlement, whenever it lands.
- L1 is read **once, no earlier than 2026-11-14T05:00Z** (24 h after L1 ends, so that every L1 exit, contract close and
  settlement has landed). If a data source does not yet cover every L1 row's exit and settlement then, the read waits until
  it does; it is never done in part and never repeated. No row of L1 is read before then, by any job or person.
- Pass on L1: the setup, traded exactly as on HO-1 (same exit, size, one position at a time per asset / event), must
  (a) beat its matched random-entry placebo (8 seeds) on L1 $, and (b) win at least **4 of the 7** L1 days (a day =
  05:00Z to 05:00Z, by decision time; won = the setup's net $ that day > $0; a day without trades is not won).
- **Only lockbox passers can enter rulebooks**, ranked by L1 $/h, each with the exit it was scored with.

## 3. Loser study (descriptive)
python/oracle/losers.py: for every confirmed setup, its trades (the confirmation step's trade simulation) split into
winners (trade $ > 0) and losers, on discovery B rows (horizon ends before DEV_END) and, once HO-1 is opened for every
confirmed setup of the type, on HO-1 rows reported separately: loser share, mean loser $, exit kind, the share of losers
whose hindsight best within h reached $0 / $1 / half the target / the target (an upper bound: path order vs the stop is
ignored), hold minutes, the feature states / RV tercile / hour bucket over-represented among losers, and an upper-bound
"take-profit at 25 / 50 / 75 % of the target" table. Nothing in it selects or re-ranks a setup; any new rule it suggests is a
new hypothesis for data after the lockbox.
