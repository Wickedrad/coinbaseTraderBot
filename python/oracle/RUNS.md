# Oracle setups: run log (aggregates only)

| run | what | result |
|---|---|---|
| 42176343914 | OR-H1 perp / pp15 / pp60 / tennis | confirmed 439 / 400 / 320 / 242, BHY passes 0, frozen 0 |
| 42231227389 | OR-H2 perp-rev, M 30/60/100/170 bps, h 5/15/60 | N_raw 32.3M, confirmed 468 (all h=60, M 100/170), BHY passes 0, frozen 0; random entries net -23 to -29 bps per trade (taker costs); no 5 / 15 minute cell had a setup with mean trade $ > 0 |
| 42953796892 | OR-HM1 heat map, first run (oracle-heat.yml; BTC ETH SOL XRP, 2020-01..2026-07, 425 readings) | VOID (two reviews found the design reports heat on pure noise: bid-ask bounce, price-step rounding, unsigned B heat, children re-counting their parent; see OR-HM1.md Amendment 1). Never reported. |
| 42956696751 | OR-H3 loser cut, arm search (pp15, pp60; 80 arms per type; A choose, B confirm; discovery only) | frozen 0 for both types: falsified at discovery, nothing opens. Every cut level loses MORE than no cut (the best cut arm is $45-$208/day worse than control on B). The three entry filters lose less than control (pp15 +$298 to +$355/day, pp60 +$70 to +$115/day on B, p vs control <= 0.026) but stay negative: pp15 best -$615/day, pp60 best -$127/day (matched random entries, taker fills at top of book). |

Next: all-confirmed HO-1 done for both runs (pp15 10 + pp60 10 lockbox candidates; perp, tennis, perp-rev none). OR-H3 loser cut for Price Prediction. Lockbox read after 2026-11-14T05:00Z.

Nov 11: OR-H3 loser-cut search done (run 42956696751, report models/oracle-setups/runs/42956696751/cut/report-cut.md). Reading: selling a loser at the bid does not rescue random entries; what helps is not entering (cheap side, falling side, out-of-the-money side). The heat map (OR-HM1 Amendment 1) is the search for WHEN to enter.

Nov 11: OR-HM1 second run 43026335764 (Amendments 1 and 2 in prereg/OR-HM1.md; commit 52c7f16) was CANCELLED before its league was built and no result of it was read: Steven's direction at 13:17 UTC (detect direction that holds at least a minute; no pass bars) led to Amendment 3 (1-minute horizon, minutes held, direction league with nothing cut), and the third run replaces it (dispatched by the commit that adds this note). The data rule is the same: Build 2020-2024, check 2025; no minute at or after 2026-01-01 is read (the workflow cuts the file, the loader refuses a later minute). Three no-signal twins per coin. Each series' table sha256 is in its meta.json, the league summary and league.md, and is appended to the registry calendar (/mnt/project-files/registry/edge-pipeline/calendar.md) and to this file after the run.

Nov 11: OR-HM1 third run is 43030435253 (Amendment 3, commit b8d0e29). All eight coin jobs finished (15:05 UTC, 10:05 AM EST) and stored their tables on Drive. Its league step failed twice in "Drive setup" before reading a table (the runner could not install rclone: the listed package was gone from the mirror). No league result of it existed or was seen. The commit that adds this note gives Drive setup a refresh-and-retry and the workflow a league-only tag; the league is built from the stored tables of run 43030435253 with the same engine code. No coin minute file is read again.

Nov 11: OR-HM1 third run 43030435253: league built at 15:59 UTC (10:59 AM EST) by the league-only run 43051083126 (commit c0ddecb; heat.py unchanged since b8d0e29). Direction league, every event level, nothing cut: 19,055 levels on the four coins; share that kept the build-years direction on 2025 at 1 / 5 / 15 / 30 / 60 minutes: 0.70 / 0.77 / 0.79 / 0.78 / 0.76 (the three no-signal twins per coin, 57,046 levels: 0.50 at every horizon); t on 2025 of 2 or more: 0.28 / 0.35 / 0.38 / 0.33 / 0.25 (twins 0.02). Coin price only, 2020-2025; not a Kalshi-price result. Table hashes (sha256 of each heat.csv.gz, unzipped):

| series | table sha256 |
|---|---|
| BTC | `9d1ccb72747bc124153fc40e2fa9847351aaa08e7ef5285be4c6535c08d0f87d` |
| BTC twin1 | `b4937c5de30caa5ac248a3e6560746900048cc00782e162663b3fac9074f8f75` |
| BTC twin2 | `a3b45b893447da34ac1722e73a360b07086343cca9f9e70bbe12f883d770b8d9` |
| BTC twin3 | `c30b4afb1f96781cee9abcdb1f2677faf91e1d8f01c1a1659c4584062f5e2e9c` |
| ETH | `9fe17794ba5fbbed13d787f1de81cf99f79c77604f28fb9526460adc074415d2` |
| ETH twin1 | `8f0a2c8d6fbd438d290e33c3d41c18b51be914906427717dad7bcdc29d4e89ee` |
| ETH twin2 | `2a8b4cab14d32c90b2225ce0afb9c48fe531b8981a6c7ad782792259f591d666` |
| ETH twin3 | `bc2119d54a90f90f57fd988353d536ce2277935e188419482f46917fab2ba088` |
| SOL | `a377481930b89890b819b9b8248d222e64978599d02d0e4176437f24de332aad` |
| SOL twin1 | `6404bf4ada7cd1dd6af3bf3c08d716af9c750c19fd4625e12b66674e6e07602d` |
| SOL twin2 | `d9b9b5f27e023a4cb75cde9f9d2447c722022750c45d5122de0e89f7da16833b` |
| SOL twin3 | `9164b2c2588891dac73f1f90cd3691f3a7eb5bd9c3120053033a0cd5da7676be` |
| XRP | `3699259117c03e54eed509802208a55d643748ee8b40fe2655a348fe7567fc75` |
| XRP twin1 | `e339acec7d510050cd71a8ea044988352991121b788621ab774af59039db7f4c` |
| XRP twin2 | `e15a9eec9b69e1049d9eb927369d0e93abd98e8c1081783bd219d1ca1d9a5760` |
| XRP twin3 | `c095147bb4efd57f47f203268f8b33b43abf6cd9cf433fd9303ada8e276dc418` |

Nov 11: OR-HM1 add-ons on the stored run 43030435253 (no stored table changed). Clock (Amendment 6, run 43061625967, 12:24 PM EST / 17:24 UTC): the UTC hour, New York half hour and weekday add little against the twin (clock_pack.json). Long horizons (Amendment 7, run 43070798519, 1:03 PM EST / 18:03 UTC): 240 and 1440 minutes, same zone edges as the main tables; direction kept on 2025 69.6% and 66.5% (twins 51.1% and 51.0%); perp_pack.json and perp_pair_pack.json; long tables on Drive under models/oracle-heat/runs/43030435253/long/.
