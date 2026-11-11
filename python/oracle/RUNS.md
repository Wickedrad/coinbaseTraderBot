# Oracle setups: run log (aggregates only)

| run | what | result |
|---|---|---|
| 42176343914 | OR-H1 perp / pp15 / pp60 / tennis | confirmed 439 / 400 / 320 / 242, BHY passes 0, frozen 0 |
| 42231227389 | OR-H2 perp-rev, M 30/60/100/170 bps, h 5/15/60 | N_raw 32.3M, confirmed 468 (all h=60, M 100/170), BHY passes 0, frozen 0; random entries net -23 to -29 bps per trade (taker costs); no 5 / 15 minute cell had a setup with mean trade $ > 0 |
| 42953796892 | OR-HM1 heat map, first run (oracle-heat.yml; BTC ETH SOL XRP, 2020-01..2026-07, 425 readings) | VOID (two reviews found the design reports heat on pure noise: bid-ask bounce, price-step rounding, unsigned B heat, children re-counting their parent; see OR-HM1.md Amendment 1). Never reported. |
| 42956696751 | OR-H3 loser cut, arm search (pp15, pp60; 80 arms per type; A choose, B confirm; discovery only) | frozen 0 for both types: falsified at discovery, nothing opens. Every cut level loses MORE than no cut (the best cut arm is $45-$208/day worse than control on B). The three entry filters lose less than control (pp15 +$298 to +$355/day, pp60 +$70 to +$115/day on B, p vs control <= 0.026) but stay negative: pp15 best -$615/day, pp60 best -$127/day (matched random entries, taker fills at top of book). |

Next: all-confirmed HO-1 done for both runs (pp15 10 + pp60 10 lockbox candidates; perp, tennis, perp-rev none). OR-H3 loser cut for Price Prediction. Lockbox read after 2026-11-14T05:00Z.

Nov 11: OR-H3 loser-cut search done (run 42956696751, report models/oracle-setups/runs/42956696751/cut/report-cut.md). Reading: selling a loser at the bid does not rescue random entries; what helps is not entering (cheap side, falling side, out-of-the-money side). The heat map (OR-HM1 Amendment 1) is the search for WHEN to enter.

Nov 11: OR-HM1 second run 43026335764 (Amendments 1 and 2 in prereg/OR-HM1.md; commit 52c7f16). Build 2020-2024, check 2025; no minute at or after 2026-01-01 is read (the workflow cuts the file, the loader refuses a later minute). Three no-signal twins per coin. Each series' table sha256 is in its meta.json, the league summary and league.md, and is appended to the registry calendar (/mnt/project-files/registry/edge-pipeline/calendar.md) and to this file after the run.
