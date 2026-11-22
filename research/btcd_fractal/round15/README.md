# Round 15 (Nov 21 2026, 6:50 PM EST / 23:50 UTC): the 8.3:1 pace with USDT.D near its record

Data: research/btcd_fractal/data through the Nov 21 daily bar (run 44962005842, commit 4ed4201).

- `study14_tv_nov21.*`: round 14's study (study14_july2016.py, unchanged) re-run on that data. Today (week ending Nov 15) -> Mar 5 2017, T1 0.936.
- `make_exstables.py` + `study14_exstables_nov21.*`: the same study on BTC.D / (1 - (USDT.D + USDC.D)/100). Also Mar 5 2017.
- `pace_loop.py` -> `pace_*.json`: segment paces, the parent's 2017 path at 1:1 / 4.75:1 / 8.3:1, the rolling 8.3:1 start date and its hit test.
- `usdt_loops.py` -> `usdt_loops_nov21.json`: USDT.D against its records, the stablecoin pull on TradingView BTC.D, BTC.D down-legs since 2017 and USDT.D swing tops.
- `verify/`: the independent check's scripts (raw-file recomputation of the USDT.D and leg figures).

Write-up: the Round 15 section of https://claude.ai/artifact/AF6LEX56SztiGjqUCa5D45
