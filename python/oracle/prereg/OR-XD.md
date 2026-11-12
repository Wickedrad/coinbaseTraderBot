# OR-XD (lite pass): outside derivatives readings for the heat curves (design, written before any run on real data)

Written 2026-11-12 ~08:15 UTC (Nov 12 03:15 AM EST; EST = UTC-5). **Revised 2026-11-12 ~08:45 UTC (03:45 AM EST) after code
review** (the model is driven by CONTRACTS, the OI clock is ts + 10 minutes, carry 10 minutes, the perp-lag rule, the
alignment guards, the PxDiv60 restart, the skip rules; every changed sentence below is marked "(revised)"). Both versions were
written BEFORE any run of this code on real data and BEFORE any number of split B (2025) from it. The only runs so far
are on synthetic series made by the tests. Design
background: /mnt/project-files/outside-data/OR-XD-design.md. Engine: OR-HM1 with Amendments 1 to 3 (python/oracle/heat.py,
prereg/OR-HM1.md), unchanged. Code: python/oracle/heat_outside.py, tests python/oracle/tests/test_heat_outside.py,
workflow .github/workflows/outside-xd.yml (push tag [xd-lite]). NEVER DOGE.

## What this pass is
The league of OR-HM1 (single, pair and triple event levels, build 2020-2024 = split A, check 2025 = split B, the
no-signal twins as the chance scale) run on FIVE new readings built from data that is ALREADY on the project's Google
Drive, read inside GitHub Actions, and only before 2026-01-01. The league is information. The only standard a hot cell
meets is the one test that comes later (the edge-iteration pipeline on real Kalshi prices and fees). **This pass adds no
pass bars, no sealed weeks and no new thresholds**; OR-HM1's own hot / replicate / BHY rules apply as they are.

## Data (Drive raw/perp-ta-history/<A>/, A in BTC, ETH, SOL, XRP)
- binance-1m/<A>/1m.csv: spot 1-minute bars `ts,o,h,l,c,v,tb` (ts = ms of the minute OPEN; tb = taker-buy base volume).
- binance-um/<A>/1m.csv: USD-M perpetual 1-minute bars, same columns.
- binance-oi/<A>/oi.csv: `ts,oi,oi_usd`, Binance 5-minute metrics (ts = create_time ms). BTC from 2020-09-01, the others
  from 2021-12-01. Both `oi` (contracts) and `oi_usd` are read; the model uses `oi` (below), `oi_usd` only for the clock check.
The workflow cuts every file at HEAT_END (2026-01-01 00:00 UTC = 1767225600000) with awk on column 1 BEFORE anything
computes on it and asserts the last row is before it; the loaders refuse a file with a row at or after HEAT_END anyway
(strict). A timestamp that is not 13 digits (milliseconds) is refused. DOGE is refused. A minute where the spot OR the perp
bar is missing (a gap, forward-filled) carries no reading, nor do the following minutes (below). (revised) A perp row with
volume but an EMPTY tb cell is a gap (an empty cell is not "all sell"); a file where more than 0.1% of the rows with volume have an
empty tb (spot or perp) is refused (below that, the engine's own spot loader still reads an empty spot tb as 0), and the counts are written to meta.json (xd_input). (revised) Two input guards run on the
real files before any reading: the perp file must be on the spot's clock (the correlation of 1-minute returns at lag 0 must be
above 0.5 and above twice the correlations at lags -1 and +1, else the run stops; a file stamped one minute early would be a minute
of look-ahead), and the OI file's implied price oi_usd / oi must not match the perp open 10 or 15 minutes after ts clearly better
(under half the error) than at ts or ts + 5 minutes (the design's test (b)); both results are written to meta.json.

## Splits
As OR-HM1: A = 2020-01-01..2024-12-31, B = 2025. Every zone edge is the quantile of split-A rows only (row before the
end of A), at least 1,000 finite values, else the reading is skipped for that coin and the league says so.

## Readings (all 1-minute, five zones by quantiles [0.02, 0.10, 0.90, 0.98] of A, decision at the CLOSE of the minute)
Family CVDP (cumulative-volume-delta perp vs spot):
1. **CVDP:Div15** = perp net taker share over the last 15 minutes minus the spot net taker share over the same 15
   minutes. Net share over N minutes = sum(2*tb - v) / sum(v) (NaN when sum(v) = 0). Row i uses minutes i-14..i.
2. **CVDP:PxDiv60** (absorption). net60 = sum over the last 60 minutes of (2*tb_perp - v_perp). z60 = net60 / sd, where sd
   is the standard deviation (n-1) of the rolling-60 net over the 1,440 minutes ENDING ONE MINUTE BEFORE row i (needs
   80% present). r60 = the perp 60-minute log return in bps. Value = z60 where sign(z60) != sign(r60) and |r60| > 1.5
   price steps (heat.TICK_DEAD times the engine's tick of the spot bars), else 0. Positive = taker buying while price
   fell, negative = taker selling while price rose, 0 = they agree. (revised) After a gap run longer than 60 minutes the reading
   is NA until its whole normalising history, 60 + 1,440 = 1,500 minutes, has passed (design 2.1), on top of the engine's stale rule.
Reference only (NOT in the league; for the near-duplicate measurement): CVDP:15 = perp net share over 15 minutes;
REF:FlowTB15 = spot tb / v over 15 minutes (the HM2 FLOW:TB15).

Family LIQMAP (a liquidation-map MODEL built from open interest, NOT data):
3. **LIQMAP:DistAbove**, 4. **LIQMAP:DistBelow**, 5. **LIQMAP:Skew** (definitions below).

(revised) Live-lag rule (design 2.1: a provisional +1 minute known-time delay on every feed-fed 1-minute input until the parity
shadow has measured p99 latency): this archive-only pass uses lag 0 on the perp bars (the Binance archive files are complete bars).
The code takes `--perp-lag K` (every perp input seen K minutes late; the perp bars, the perp close used as P, the highs and lows
of the traded-through rule); **every hot spot must be rerun with --perp-lag 1 and --perp-lag 5 before it counts for anything
live** (the lag-robustness rescoring of the design). The lag changes nothing in this pass's tables.

All five are pair conditions as well (new x new pairs). The TA-Lib vocabulary and candlestick patterns of OR-HM1 are not run in this pass.

### The liquidation-map model (constants FROZEN here, before any B number)
- Leverage tiers L = 10, 25, 50, 100 with weights 0.4, 0.3, 0.2, 0.1. Maintenance margin m = 0.005 for every coin (one fixed
  value, recorded in meta.json; Binance's real brackets are not used).
- Price buckets of 0.1%: bucket index b = round(ln(price) / ln(1.001)); a bucket's price is 1.001^b. A cluster is a bucket whose
  notional is at least 2% of the latest OI value in USD. Positions expire after 30 days (8,640 five-minute steps). Skew
  uses +-2% of price.
- (revised) **The OI clock.** Each stamp ts is first CEILED to the 5-minute grid (02:35:02 counts as 02:40). The snapshot instant is
  taken as S = ts + 5 minutes (the later of the two conventions Binance's create_time may follow) and the snapshot is KNOWN at
  T_k = S + 5 minutes = **ts + 10 minutes** (the design's rule "a row is known at S + 5 min" under its conservative reading). No
  snapshot is used before T_k. The earlier text of this file said ts + 5 minutes was safe whichever end the stamp marks: that was
  wrong for the new convention and is withdrawn. After the ceil, one row per grid stamp is kept: the row whose implied price
  oi_usd / oi is closest to the perp open at ts or ts + 5 minutes (else the last row of the file); the number dropped is written
  to meta.json.
- (revised) **The model is driven by CONTRACTS, not by USD.** At snapshot k, dq = oi_k - oi_(k-1) (the `oi` column; previous snapshot);
  the USD column would carry the price move into the model as phantom positions and would leak the real price into a twin. If the
  gap between the two snapshots is over 15 minutes the step is skipped and the row only sets the baseline. First, the buckets
  the perp price traded through since the previous snapshot are deleted: long-liquidation buckets with price >= the lowest
  low, and short-liquidation buckets with price <= the highest high, of the perp minutes in [S_(k-1), S_k) (a skipped step
  deletes too: the price did trade). Expired additions are removed (a ledger of additions: step, side, bucket, stored amount,
  bucket generation; an addition 30 days old is subtracted if its bucket's generation is unchanged, clamped at 0; a zeroed
  bucket gets a new generation). If dq > 0, a notional of dq * p is added at p = the perp CLOSE of the last minute before S_k
  (on a twin: the twin perp path), split by f = the perp taker-buy share (sum tb / sum v) of the OI interval [S_k - 5 min, S_k)
  into longs (fraction f) and shorts (1 - f); per tier, w * share goes into the LONG-liquidation bucket of price
  p * (1 - 1/L + m) and the SHORT-liquidation bucket of price p * (1 + 1/L - m). If dq < 0, ALL stored notional (both sides) is
  scaled by (1 + dq / oi_(k-1)) clipped to [0, 1] (one global scale factor S, renormalised when S < 1e-6). The "latest OI value in
  USD" of the cluster threshold and of e is oi_k * (the perp close at S_k) on the path in use.
- Readings at minute row i (decision at the close of i) use the state of the LAST snapshot with T_k <= close(i), carried at most
  **10 minutes** (revised from 15; design 2.2 "carry at most 10 min"; else NaN), and P = the perp CLOSE of minute i. (revised)
  Buckets the perp has traded through in the minutes after S_k up to and including row i (the running lowest low / highest
  high) are treated as already deleted at row i, not only at the next snapshot. rv60 = sqrt(sum of squared 1-minute perp log returns in bps over
  the last 60 minutes). **DistAbove** = (nearest short-liquidation cluster price strictly above P, minus P) / P * 1e4 bps,
  divided by rv60. **DistBelow** = (P minus the nearest long-liquidation cluster price strictly below P) / P * 1e4,
  divided by rv60. NaN when there is no such cluster or rv60 = 0. **Skew** = ln((S_up + e) / (S_dn + e)), S_up = short-
  liquidation notional in the buckets within (P, 1.02 P], S_dn = long-liquidation notional in [0.98 P, P), e = 0.001 times the
  OI value.
- Implementation choices not fixed by the text above (also frozen): the bucket array spans 0.85 x the lowest to 1.2 x the
  highest perp price of the path used; expiry is by TIME (an addition expires at the first snapshot 30 days or more after
  its own known time, which is 8,640 steps when no snapshot is missing); the cluster price is the bucket's price 1.001^b;
  the same threshold (2% of the OI value of snapshot k) is used for both sides.

## Known-time and gap rules (all readings)
- A minute row's reading reads only data closed at or before the close of that row. (revised) OI is used only from ts + 10 minutes.
  The unit tests cut the future (all inputs after a row replaced by noise, same fixed edges): every reading before the cut
  is unchanged, including cuts one minute before and exactly at a snapshot's known time.
- Every rolling window is defined by TIME and needs 80% of its minutes present, else NaN. A spot or perp gap minute is NaN for
  every reading and, through the engine's stale rule (heat.STALE = 100 minutes, 500 after a gap run longer than 14), for the
  window length W minutes after it plus those (W = 15 for Div15, W = 60 for the three LIQMAP readings; PxDiv60 also waits
  1,500 minutes after a gap run longer than 60 minutes, see above).
- (revised) OI known time: ts + 10 minutes after the grid ceil (see the model above); the unit tests cut the future with OI rows
  removed by that clock.

## Twins (the chance scale)
`--twin N` as OR-HM1: every minute's direction replaced by a coin flip s (rng [20261111, N], s[0] = +1; spot tb swapped with
v - tb where s < 0). The perp path of a twin is the twin SPOT open / high / low / close times the REAL perp / spot close ratio
of the same minute (the real basis is kept); the perp taker-buy volume is flipped with the SAME s (tb_p' = tb_p where s > 0,
else v_p - tb_p); OI is the real number of contracts (revised: contracts, so the twin's adds and scales follow the TWIN path and
not the real price). The LIQMAP model runs on that path. Output directories BTC, BTC-twin1 ... so
`python -m oracle.heat league` works unchanged (the direction league: the share of event levels that kept their A direction on B).

## Measured and written to meta.json (information, no bar)
- near_duplicates: Spearman rank correlation on A rows of CVDP:Div15, CVDP:PxDiv60, CVDP:15 and REF:FlowTB15 with each other.
- direction_coupling: Pearson correlation on A rows of each of the five readings' values with the PAST 5 / 15 / 60 minute return of the coin (bps).
- constants, model counters (snapshots, adds, scales, gap steps, renormalisations, share of snapshots with a short / long cluster),
  the share of rows with a value per reading.
- (revised) The model's largest bucket as a share of the OI value (max, median and 99th percentile over every 50th snapshot) and
  the share of snapshots with a cluster are written to meta.json (model), so a skip can be read from it. The synthetic probe
  found the largest bucket just under the frozen 2%, so on real data it is open whether the LIQMAP distance readings exist at all.
- (revised) A reading with fewer than 1,000 finite values on A, or with values on fewer than 30 distinct days of A, is skipped for
  that coin (for LIQMAP:DistAbove / DistBelow this depends on how often a bucket reaches the frozen 2% of OI); **the constants are
  not changed to rescue it**, and the skip is part of the result. A twin follows its real coin: a reading skipped for the real
  coin is skipped for all its twins (the twin run recomputes the real coin's skips; listed in meta.json as
  skipped_inherited_from_real_coin), so that the real coin and its twins have the same families in the league.

## NOT in this lite pass
PREM (perp-spot premium from a premium-index file), LS (long-short ratios), WHALE (top-trader positions) and BOOKP (book
pressure) need new Binance downloads: they are held by the owner's Gate 0. The Coinalyze readings need an API key. This pass
reads only the files already on Drive, only before 2026-01-01, and downloads nothing from any exchange.

## Open gate
The Binance Vision dataset terms (v1.0, Aug 26 2026) forbid live-trading use of the data: that is an OPEN GATE for any LIVE use of these
readings and for any new download. Until it is settled this pass is research on files already held, as OR-HM1 is.

## Unchanged
A MAP, not a validated rule. Nothing at or after 2026-01-01 is read (the OR-HM1 heat tables stop there); HO-1 stays closed; never compared to paper; no pass bars are added; no sealed weeks; NEVER DOGE. Hot cells that replicate go on to
Kalshi prices and fees under the edge-iteration pipeline. Known limits: the model is a MODEL (one fixed margin, fixed leverage
mix, OI changes split by the taker-buy share, positions never closed except by OI decreases, traded-through buckets and
expiry); a cluster at 2% of OI in one 0.1% bucket may be rare; day clustering treats days as independent (OR-HM1).

## Amendment 1 (Nov 12 2026, about 09:00 UTC / 04:00 AM EST; written before any league output of this study was read)
The first BTC-only run (GitHub run 43185586638, tag [xd-assets:BTC]) wrote its model statistics to meta.json before any
direction table was opened: the largest single bucket held a median 0.70% of OI, p99 1.39%, max 6.6% (the model's own state
over all rows, sampled every 50th snapshot; no return or direction was looked at), and only 1,934 of 559,904 five-minute
blocks held a short-liquidation cluster at the frozen 2% share (1,577 a long one). LIQMAP:DistAbove and LIQMAP:DistBelow were
therefore skipped for BTC and for its twins, exactly as the no-rescue rule says; **that result stands and is reported**.
Because the question "do liquidation clusters tell direction" cannot be asked at 2%, a second, **additional** variant is
added: the same model with the cluster share set to **1.0% of OI** (env XD_CLUSTER_SHARE=0.01, workflow tag [xd-cluster:0.01]),
its output kept apart (its own run id and Drive folder) and labelled "cluster 1.0%" everywhere. It does not replace the 2%
variant, no other constant changes, one value only (no search over shares), and its results are information beside the
frozen variant (two variants are two looks: say so when reading them). The 1.0% value is round, between the median and the
p99 of the largest-bucket share.

## Amendment 2 (Nov 12 2026, about 10:30 UTC / 05:30 AM EST; written before any run of the hook below on real data, and before any OR-HM2 number from it)
An optional hook lets the OR-HM2 pair scan and learner use the five league readings as extra single readings (families `cvdp` and
`liqmap`): `heat_outside.hm2_outside_readings`, switched on by `python -m oracle.heat_hm2 coin|finish|bench --outside` (workflow tag
`[hm2-outside]`, which also moves the outside study to its own Drive folder `<run>/hm2-outside/` and its league commit to
`research/oracle_heat/hm2/outside/`). **Off by default; with the flag off nothing in OR-HM2 changes.** This amendment adds no constant,
no pass bar, no sealed week and no zone change: the five readings, their frozen constants, the A-quantile zone edges, the 1,000-value /
30-day skip rule, the stale rule, the two input guards and the contracts-driven model are the ones above, computed by the same functions
(`xd_values`, `xd_readings`); the unit tests hold the hook equal to the standalone study on synthetic data (codes, edges, values),
including perp rows with an empty tb cell, duplicate OI stamps and a twin. The hook differs from the standalone run in these ways, and
they are stated here so that nobody reads an OR-HM2 number as an OR-XD one:
1. **OI.** The hook uses the OR-XD clock (each stamp ceiled to the 5-minute grid, known at ts + 10 minutes) and reads the RAW OI rows
   so that `clean_oi` picks among the rows of one stamp as defined above. OR-HM2's own OI readings use `load_extra` (first row of a stamp,
   known at ts + 5 minutes); that is unchanged and is not used for these five readings.
2. **Twins.** The twin of a HM2 job is the twin rule above, exactly: twin SPOT o / h / l / c times the REAL perp / spot close ratio, perp
   taker volume flipped with the spot's signs (the same signs as heat.make_twin and OR-HM2's joint flip on the job coin's grid, so the five
   readings share every coin flip with the other readings of that twin), OI real contracts, and a twin follows its real coin's skips. OR-HM2's
   joint-flipped perp (the perp's own path flipped, whose basis random-walks away from the real one) is NOT used for these five readings; on
   a constant basis the two agree, otherwise they do not. The chance scale of the five readings is therefore the one frozen above.
3. **No perp-lag variant.** The hook computes lag 0 only. The rule that every hot spot is rerun with `--perp-lag 1` and `--perp-lag 5`
   before it counts for anything live stands, and is done with the standalone workflow (`[xd-lite]`), not through the hook.
4. **Refusals stop the job.** An input the hook refuses (no taker-buy column, more than 0.1% of the perp rows with volume and an empty
   tb, the alignment guard, the OI clock guard, `oi_usd` missing) stops `heat_hm2 --outside` with the reason, as the standalone run stops;
   a reading skipped by the frozen rules (fewer than 1,000 values or 30 days on A) is skipped and listed in meta.json `outside.skipped`,
   as above. Perp rows with an empty tb are broken bars, made as `perp_on_grid` makes them (gap, last close carried forward).
5. **Chance scale of the pair scan.** An OR-HM2 study run with `--outside` has five more readings in its pair list (each paired with every
   other reading); its p-value histograms, BHY marks and twin maxima include those cells, so its pack marks are not the plain study's.
   It is therefore kept apart (point 6).
6. **Research only.** The five readings carry `research_only` in the reading dict and in meta.json. They never enter `hm2_pack.json` or
   `hm2_live_meta.json` (no pack row, GBM zone row, model entry or near-copy alias names one), the parity never checks them, their feeds
   (perpetual taker flow, open-interest history) are ones the bot does not have, Part 4's chart pairs never pair them, and the league
   commit of an `--outside` study goes under `research/oracle_heat/hm2/outside/`, never over `research/oracle_heat/latest/`. **Nothing from
   an `--outside` run counts for anything live**, and the Binance Vision terms (open gate above) still forbid any live use of the data.
Times in this file: UTC and EST (UTC-5).

## Amendment 3 (Nov 12 2026, 13:43 UTC / 08:43 AM EST: Steven's decision; written the same morning after it, BEFORE any number of the readings below exists)
Steven's word (Nov 12 2026 13:43 UTC / 8:43 AM EST): "Let's build our own historical data from Binance and run the Oracle that way, add the
results to the weighted heat curve matrix if there is an edge, even a slight one. Make sure we run all readings against all other
readings." So the study grows from the five lite readings to the readings below, built from our own copy of the Binance Vision
archive (Drive `raw/outside/binance/<COIN>/`, fetched on GitHub runners; nothing is downloaded from this container). The five lite
readings, their constants, their zones and the OI clock above are **unchanged** (the tests hold their values to a stored digest). No
sealed week, no new pass bar: the engine's own bars (hot on A, replication on B, twins) judge the new readings as they judge the
old; an "edge, even a slight one" means a cell that passes those bars, nothing looser. "All against all": every reading of this
study (the five lite + the new ones) is a pair condition for every other (`cond`), so the pair scan covers new x new and new x lite;
with `heat_hm2 --outside` they also pair with every OR-HM2 reading (Amendment 2's chance-scale note applies). Code: `full_values`,
`full_readings` in `python/oracle/heat_outside.py`; workflow tag `[xd-full]`.

**Data (one contract, written by the fetch jobs, read by the readings).** All times UTC ms (13 digits). Rows at or after 2026-01-01
are refused by every loader (`prep_*`, `AggStore`, `read_checked`: SystemExit) and cut by `heat_outside cut` before the engine runs;
2026 stays unread until the one-test window. A = 2020-01-01..2024-12-31 (zone edges, F, every skip rule), B = 2025.
`metrics.csv.gz` (S = the true snapshot instant after the create_time convention test, per the design 2.2; a reading's known time is
**S + 5 min**), `premium_1m.csv.gz` + `premium_stamp.json` (the stamp test: 'next' adds one minute of delay), `funding.csv.gz`,
`mark_1m.csv.gz` (information only), `um_1m.csv.gz` (convention test only), `agg_spot/` and `agg_perp/` (`<YYYY-MM>.parquet`, one row
per minute with trades), `bookdepth_1pct.csv.gz` (ts already shifted later by one spacing), `BTCDOM/idx1h.csv.gz` (a pass-through input
for OR-HM2, no reading here). A reading whose file is missing is skipped with a recorded reason; nothing is guessed.

**Common rules.** Decision at the close of minute row i (entry = the next minute's open); a value is used at row i only when its known
time is at or before that close (a value known exactly at the close counts, one millisecond later does not). Rolling windows are by
time with >= 80% of their minutes (or snapshots, or days, or settlements) present, else NA. Zones: edges at the 2 / 10 / 90 / 98% quantiles
of A's finite values (`zone`); a reading with fewer than 1,000 finite A values on fewer than 30 distinct days of A, or with collapsed inner
zones, is skipped and the reason recorded. Stale rule: the engine's (`stale_rows`) on the spot gap mask over the reading's window (W = 1 for
LS, PREM, BOOKP; 15, 60, 5 for Net15, Count60, Sweep), and for the perp readings (WHALEP) on the spot mask OR the perp mask. The
`--perp-lag` rerun does **not** apply to these readings (recorded: `perp_lag_applied: false`); the +5 minute lag rerun of any hot spot is
a separate, later step as for the lite readings.

**LS family (metrics; real level on twins, values stay real).** x = ln(ratio) of `count_long_short_ratio` (LS:Global z), `sum_toptrader_long_short_ratio`
(LS:TopPos z and LS:TopPosChg60), `count_toptrader_long_short_ratio` (LS:TopAcc z); a ratio <= 0 is NA. S is ceiled to the 5-minute grid.
`z = (x_S - mean) / sd` with mean and sd (ddof 1) over the 288 snapshots **before** S, i.e. [S - 24 h, S) (the row itself is not in its
window), >= 231 present. `LS:TopPosChg60 = (x_S - x_{S-60 min}) / sd` of the same 60-minute change over the 288 snapshots before S, >= 231
present; the snapshot exactly 60 minutes earlier must exist. Known at S + 5 min; a snapshot is used at the latest row whose close is at
or after that and for at most 10 more minutes (an earlier snapshot fills a missing latest one inside the same 10 minutes).

**PREM family (premium + funding; real level on twins).** Settlement k at calc_time_k, Ts_k = calc_time_k floored to its minute; the
settlement is known at calc_time + 1 min. Row j (bar opening at o_j) uses the last settlement with calc_time <= o_j and the premium
closes of the bars p = 1..n that opened at Ts_k + (p - 1) min up to and including bar j (n = (o_j - Ts_k) / 1 min + 1), weight p;
`P = sum(p * premium_p) / sum(p)` over present bars (>= 80% of n present, and bar j itself present; a bar is known at its close, plus
one minute if `premium_stamp.json` says 'next'). `I = 0.01% x N / 8` where N is the interval in hours between the last two settlements
(only 1, 2, 4 or 8 h gaps within 2 minutes count). **PREM:PredFund = F = clamp(I, P - 0.05%, P + 0.05%)** (the old formula; written so that F is exactly I whenever P is within 0.05% of it, with no rounding noise around I). The
2025-09-18 "(8/N)" regime cannot be verified from here and is **not applied**; instead the reconstruction error of both versions
(F against the next settled rate, at the last bar of each interval) is written per year to meta (`xd_full.input.prem.reconstruction_error_by_year`)
as information, and nothing is chosen on B. **PREM:PredMinusLast = (F - last settled rate) / sd** of the settlement-to-settlement rate changes
over the 90 settlements ending at the last known one (>= 72 changes present, ddof 1). NA when the last settlement is more than 1.5 intervals old. The bar that opens at Ts_k is bar p = 1 of interval k even when calc_time_k is a few ms past the minute. `premium_stamp.json` is read from the fetch job's keys `fits` ('same' | 'next' | 'unresolved') and `extra_delay_minutes`; unresolved skips the PREM readings.

**Gap rule (design 2.1, applied to the new readings).** After a hole longer than 1 hour the reading is NA until a whole window has passed:
LS (all four) for 288 snapshots after a gap of more than 1 hour between snapshots; PREM:PredMinusLast's 90-change window must cover >= 80% of
its time span with valid 1/2/4/8 h intervals (a missing month blanks it until 90 settlements have passed); WHALE F (and so every WHALE
reading of that day) for 30 days after a day without trades, and Count60 for 7 days after a hole. A day with no trade at all is a
hole (BTC, ETH, SOL, XRP never have one), not a quiet day: the reducer file's month being present does not make it present. This can
blank many rows after a missing daily archive file; it is the design's rule, not a tuning.

**WHALE / WHALEP families (aggTrade reducers; spot = WHALE, perp = WHALEP).** Edges E_k = 1000 x 20000^(k/23), k = 0..23 (USD 1,000 ..
20,000,000). **F** for decision day D = the smallest E_k whose share of trades with notional >= E_k, over the 30 days fully before D
(>= 24 of them with trades), is <= 0.1%; none -> NA. F is therefore known at the start of D and uses no row of D. A realised-share check
(median / 5% / 95% over days, 0.05%-0.2% expected) goes to meta as information. The windows below use the F of the **decision row's day**
for all their minutes. **Net15** = (sum of buy notional - sell notional of trades >= F over the 15 rows ending at i) / total notional
traded over the same 15 rows (>= 12 rows present). **Count60** = the count of trades >= F over the 60 rows ending at i, minus the median of
the same count at the same minute of day over the 7 days before (rows i - 1,440 j, j = 1..7, counted with the same F; >= 6 present),
divided by max(sd of those 7 counts, 1) (ddof 1; the floor of 1 trade avoids a zero divisor). **Sweep**: from the reducer's per-second
counts, state = +1 if a buy sweep (>= 1 second in a minute whose same-side notional sum >= $1M) occurred in the last 5 rows (the row and 4 before),
-1 for a sell sweep, 0 for none; both sides in the window: the later minute wins, the same minute gives 0 (counted in meta). The $500k version
(`REF:Sweep500`, `REFP:Sweep500`) is computed and reported (near-duplicate with the $1M state) and is **never chosen and never in the
league**. Sweep needs >= 100 buy and >= 100 sell rows on A (data sufficiency, not a pass bar), else it is skipped with that reason. Three
levels: sell sweep / none / buy sweep; the events are the entries into a sweep state.
Twins: **Net15 and Sweep are direction readings**: on the twin's flipped minutes (the signs of the twin's price flip, `twin_signs`) buy
and sell are swapped before the windows are formed; **Count60, LS, PREM, BOOKP are real level** (nothing flips). A twin follows its
real coin's skips.

**BOOKP family (bookDepth, perp; real level).** `BOOKP:Imb1 = (bid_1pct - ask_1pct) / (bid_1pct + ask_1pct)` from the latest stamp known at the
close (the file's ts is already one spacing later than the raw stamp), carried at most 10 minutes. From 2023-01-01 only (A has two years);
skipped with a reason when A holds too few values. The spacing is recorded in meta. `BTCDOM/idx1h` is only passed through to OR-HM2 (the
'idx1h' kind, known at ts + 1 h); no OR-XD reading is made of it.

**Measures (A rows only, information).** Spearman correlation (every 7th A row) of every pair that holds a new reading, a direction-coupling
Pearson with the past 5 / 15 / 60 minute return, the share of rows with a value, the input checks (conv counts, metrics implied price against the mark
price per year, F's realised share, PREM reconstruction error, sweep ties) all in meta `xd_full`. None of them is a gate.

**What does not change.** The 1,000-value / 30-day skip rule, the A-quantile zones, the twin count and seeds, the engine's bars, the research-only
marking of OR-HM2 readings (Amendment 2; the lead decides on packing after the results), and the Binance Vision terms gate for live use. NEVER DOGE.
Times in this file: UTC and EST (UTC-5).

## Run log
- 08:57 UTC: push with tags [xd-lite] (all four coins unless an assets tag is given)
- 09:12 UTC: push with tags [xd-lite] [xd-cluster:0.01] (all four coins unless an assets tag is given)
- 09:28 UTC: push with tags [xd-lite] [xd-lag:1] (all four coins unless an assets tag is given)
- 09:43 UTC: push with tags [xd-lite] [xd-lag:5] (all four coins unless an assets tag is given)
- 10:00 UTC: push with tags [xd-lite] [xd-cluster:0.01] again (same constants as run 43189441913; this repeat also writes xd_meta.json with the reading shares; no constant changed)
- 10:18 UTC: probe from a GitHub runner only (public endpoints, status codes, no secrets): tag [xd-probe]; the server variant is not run (waits for Steven's word)
- Nov 12, after 13:43 UTC / 08:43 AM EST: Amendment 3 written (nothing run yet); push with tags [xd-lite] [xd-full] once the contract files are on Drive (raw/outside/binance/<COIN>/)
- Nov 12 2026, 16:05 UTC / 11:05 AM EST: contract files complete on Drive (small run 43237144820; aggTrades runs 43237144820 + 43250762046, 2020-2026, gap days refilled from daily zips); first [xd-lite] [xd-full] run pushed, no number of these readings seen before it
