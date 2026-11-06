# Oracle setups: build spec (interfaces between the pieces)

Study design and pass rules: `python/oracle/prereg/OR-H1.md` (frozen before any result). This file fixes the code
interfaces so the pieces can be built in parallel. Times are UTC ms unless named otherwise. NEVER DOGE.

Constants (python/oracle/common.py, mirrored in research/oracle/oracleExport.ts):
```
DEV_END   = 2026-08-01T00:00Z   (no mining / confirmation code loads a row whose decision t >= DEV_END - horizon)
HOLD_FROM = 2026-08-01T00:00Z ; HOLD_TO = 2026-11-05T00:00Z (exclusive) ; LOCKBOX L1 2026-11-06T05:00Z.. never read
SPLITS = {perp:   A 2020-01-01..2025-01-01, B 2025-01-01..2026-08-01,
          pp15/pp60: A 2026-04-18..2026-06-15, B 2026-06-15..2026-08-01,
          tennis: A 2026-04-27T05:00..2026-06-22, B 2026-06-22..2026-07-31}   (half-open [from, to))
FOLDS (HO-1) = Aug 1, Aug 17, Sep 2, Sep 18, Oct 4, Oct 20 .. Nov 5 (exclusive)
SIZE  = {perp: 300 USD notional, pp15/pp60: 20 USD stake (max 250 contracts), tennis: 10 USD (max 100 contracts)}
SIZE2 = {perp: 1000, pp: 10, tennis: 20}    (sensitivity only)
TARGET_USD = 5.0
```

## 1. Part directory ("oracle-part-1"): what every builder writes and the miner/scorer reads
One directory per (contract type, scope): `perp-BTC/`, `pp15-ETH/`, `pp60-SOL/`, `tennis-ATP/` ... Plain `.npy` files
(numpy format v1.0, little-endian, C order) plus `meta.json`. Rows = decisions, sorted by `t`, all splits included
(the HO-1 rows are written but no builder prints any statistic from t >= DEV_END).

| file | dtype / shape | meaning |
|---|---|---|
| meta.json | json | `{schema:'oracle-part-1', ct, scope, assets:[..], sides:['L','S'] or ['Y','N'], horizons:[15,60] or [15] or [60], size_usd, size2_usd, step_min, code_sha, n, features:[{name, kind:'state'|'bucket', levels:[int..], desc}], strata_desc, notes}` |
| t.npy | int64 (n,) | decision time (ms): the instant the decision is made; every feature uses data closed at or before it |
| group.npy | int64 (n,) | cluster id: perp = UTC day index; Kalshi = market index (within part); tennis = event index |
| asset.npy | int8 (n,) | index into meta.assets (perp/pp parts: always 0) |
| X.npy | int8 (n, F) | feature states in meta.features order; `state` features are -1/0/+1 (0 = neutral / NA); `bucket` features are 0..L-1 with -1 = NA |
| rv.npy | int8 (n,) | RV60 tercile at the decision (0 LOW, 1 MID, 2 HIGH, -1 NA; regime v1 method, causal); tennis: -1 |
| hour.npy | int8 (n,) | UTC hour of t |
| stratum_{s}.npy | int16 (n,) | matched-baseline stratum per side s (prereg strata), -1 = not tradable |
| ok_{s}{h}.npy | uint8 (n,) | 1 = side s tradable at this decision with horizon h (price band, two-sided book, full horizon inside data) |
| hit_{s}{h}.npy | uint8 (n,) | 1 = the primary +$5 take-profit filled (or a ride to settlement netted >= $5) within h |
| trade_{s}{h}.npy | float32 (n,) | realized net $ at SIZE under the primary exit (fees, spread, funding, losers included); NaN if not ok |
| best_{s}{h}.npy | float32 (n,) | hindsight best net $ at SIZE at a tradable price within h |
| hold_{s}{h}.npy | uint16 (n,) | minutes from the decision to the exit (or settlement) under the primary exit |
| hit2_/trade2_{s}{h}.npy | as above | at SIZE2 (sensitivity only) |
| tradeLat_{s}{h}.npy | float32 | primary exit, entry one decision step later (latency adversary) |
| tradeCost_{s}{h}.npy | float32 | primary exit with cost stress (perp +5 bps per leg; Kalshi +1c on the entry price) |
| bestbps_{s}{h}.npy | float32 | perp only: best net bps (re-threshold at any notional) |

`s` is the side letter, `h` the horizon in minutes, e.g. `trade_L60.npy`, `hit_Y15.npy`.

## 2. Builders
### 2a. research/oracle/oracleExport.ts (TypeScript; reuses research/perpTaSweep.ts and research/perpTaModules.ts)
`node --import tsx research/oracle/oracleExport.ts --grid data/grids/BTC.bin --history <dir with binance-1h/<X>/1h.csv> --cache-dir <modcache> --out parts [--spot-from 2026-04-12] [--spot-to 2026-11-05] [--max-minutes N (tests)]`
- Writes `parts/perp-<A>/` (decisions at every 5-minute close i = 5k+4, entry at the perp open of minute i+1, sides L/S,
  horizons 15 and 60) and `parts/spot-<A>/` (every minute in [spot-from, spot-to): `t_end.npy` int64 = end of the minute,
  `X.npy` int8 with the same feature list, `close.npy` float64 spot close, `rv60.npy` float32 = sqrt(sum r^2) over the
  last 60 one-minute log returns, `rv.npy` int8 tercile, `meta.json`).
- Features: buildPrims (all 121) + modulePrims (forecasts NOT passed; drop any prim id starting `tanet`, `lib_`, `xg_`;
  keep the analyzer / book / confluence / ta_net / conv / TA-Lib readings) with discoveryEnd = DEV_END, value = stateAt(p, i);
  context buckets: character class and HT trend mode (module hourly arrays, last closed hour), hour bucket (6 x 4 h),
  weekend, RV tercile, 60-minute trend bucket (z60 regime v1: FLAT/TREND/STRONG x sign).
- Labels via outcomes() with a constant unit (bps) and policies {sl: 9999, tp: TP(size), max: h}: TP(size) = 1e4*5/size
  + takerBps + halfSpreadBps + makerBps + 2. hit = the trade left before its time stop (with no stop, an early exit is the TP).
  trade $ = net bps / 1e4 * size. best = max favourable limit fill in the hold window (extreme / (1 + 1 bp)) net of the same costs.
  Per-coin costs: half spread {BTC .19, ETH .22, SOL 1.23, XRP 1.94} bps, funding offset {1.66, 1.19, .14, 1.57} bps / 8 h.
- Regime v1 RV terciles: port research/perpTaRegime.ts from origin/claude/project-thread-9040i4 into research/oracle/regime.ts.
### 2b. python/oracle/pp.py (reuses python/allpairs: data.load_kalshi, features.side_quotes, fees)
`python3 -m python.oracle.pp --kind 15|60 --history <dir with kalshi/KX<A>15M or KX<A>D> --spot parts/spot-<A> --asset BTC --out parts`
Writes `parts/pp15-<A>/` or `parts/pp60-<A>/`, sides Y/N, horizon [15] or [60]. Decisions k inside the entry window
(15: k = 1..10; 60: k = 5..50 and YES mid in [0.10, 0.90]); t = open + 60 s * k (python/allpairs convention, quote = candle
close at t); spot features joined at the spot minute whose END equals t. Exit and labels per the prereg (take-profit at the
bid outside the last 10%; else at the final candle ride if in profit, else sell at the bid). Contract features:
side-price bucket (0.1-wide), tau bucket, spread bucket, mid change 1/3/5 min, z = ln(S/K)/(sigma sqrt(tau)) bucket,
fair - side mid bucket, last-5-minute volume bucket. Strata: side price bucket x tau bucket (3) x RV tercile.
### 2c. python/oracle/tennis.py
`python3 -m python.oracle.tennis --tar <KXATPMATCH.tar.gz> --tour ATP --out parts` -> `parts/tennis-ATP/` (sides Y/N per
market, horizons 15 and 60, group = event). Start era only (market start >= 2026-04-27T05:00Z, close < 2026-11-05T00:00Z).
### 2d. research/oracle/hourlyBackfill.ts
Downloads settled KX{BTC,ETH,SOL}D markets for [from, to) from Kalshi's public API (research/history/kalshiHistory.ts
plumbing, 10 req/s, resumable with a time budget) keeping per hourly event only the 4 strikes nearest the Binance spot
close at (close - 60 min) (spot from the grid), and writes kalshiHistory-format `<out>/KX<A>D/<closeDay>.jsonl` with
1-minute candles for the last 70 minutes, so `load_kalshi(n=60, series_fmt='KX{asset}D')` reads it.

## 3. Miner: python/oracle/mine.py (numpy + numba)
`python3 -m python.oracle.mine --ct perp --parts <dir> --out out/perp [--top 40] [--beam 500]`
Loads only rows whose horizon ends before DEV_END (assert). Stage 1 on split A, stage 2 on split B, freeze. Writes:
`stage1.jsonl.gz`, `confirm.jsonl`, `frozen.json` (+ `frozen.sha256`), `report.md` (aggregates only), `lift/<scope>-<s><h>.csv`
(single-item lift table), `instances/<scope>-<s><h>.csv.gz` (every discovery decision with hit = 1 and its feature states,
the "list of instances"), `base_rates.json`. Pooled scope = the sum of per-part sufficient statistics (never concatenate
perps in memory).
Setup JSON: `{id, ct, scope, side, h, items:[{f, v}], rank, dev:{A:{n, hit, base_hit, ev, uplift, t}, B:{trades, days, usd_day, hit, base_hit, p_ev, p_up, p}}}`
## 4. HO-1 scorer: python/oracle/ho1.py
`python3 -m python.oracle.ho1 --frozen frozen.json --parts <dir> --labels <regime labels.csv.gz> --out out/ho1 --run <id> --code-sha <sha>`
Writes registry rows (thread `oracle-setups`, family `oracle-<ct>-v1`, contract_type perpetual | price_prediction |
tennis, roles candidate / control (flat) / placebo, by_day on all 96 HO-1 days with zeros, by_tercile, data.source
'history', data.metric 'usd'), validated with research/registry.py (from origin/claude/project-thread-79ntof), plus
`ho1.md`. Book rows per contract type. Nothing is re-selected.
## 5. Workflow: .github/workflows/oracle-setups.yml
Push-triggered on branch claude/project-thread-nvd096. Tags in the head commit message: `[oracle]` builds parts and mines;
`[oracle-parts:perp,pp15,pp60,tennis]`; `[oracle-assets:BTC,ETH,SOL,XRP]`; `[oracle-mine:<run>]` re-mines an earlier run's
parts; `[protocol:ho1] [ho1-from:<run>]` opens HO-1 once for that run's frozen.json. <= 10 concurrent jobs. Results to
Drive `models/oracle-setups/runs/<run>/...`; an aggregates-only card as a commit comment (public repo).
