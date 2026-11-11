# Oracle setups: run log (aggregates only)

| run | what | result |
|---|---|---|
| 42176343914 | OR-H1 perp / pp15 / pp60 / tennis | confirmed 439 / 400 / 320 / 242, BHY passes 0, frozen 0 |
| 42231227389 | OR-H2 perp-rev, M 30/60/100/170 bps, h 5/15/60 | N_raw 32.3M, confirmed 468 (all h=60, M 100/170), BHY passes 0, frozen 0; random entries net -23 to -29 bps per trade (taker costs); no 5 / 15 minute cell had a setup with mean trade $ > 0 |
| 42953796892 | OR-HM1 heat map, first run (oracle-heat.yml; BTC ETH SOL XRP, 2020-01..2026-07, 425 readings) | PROVISIONAL (under review, to be re-run): singles 13,400 level x horizon cells tested on A, 1,067 hot (|t|>=3), 223 replicate on B; excess moves of the most frequent hot spots are 1-4 bps over 30-60 min |

Next: all-confirmed HO-1 done for both runs (pp15 10 + pp60 10 lockbox candidates; perp, tennis, perp-rev none). OR-H3 loser cut for Price Prediction. Lockbox read after 2026-11-14T05:00Z.

Nov 11: OR-H3 loser-cut search dispatched ([oracle-cut], labels from parts run 42176343914; discovery A/B only, no HO-1 opening).
