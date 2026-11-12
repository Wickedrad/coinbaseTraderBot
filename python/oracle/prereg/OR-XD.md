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
A MAP, not a validated rule. Nothing at or after 2026-01-01 is read (the OR-HM1 heat tables stop there); HO-1 and the lockbox
stay closed; never compared to paper; no pass bars are added; no sealed weeks; NEVER DOGE. Hot cells that replicate go on to
Kalshi prices and fees under the edge-iteration pipeline. Known limits: the model is a MODEL (one fixed margin, fixed leverage
mix, OI changes split by the taker-buy share, positions never closed except by OI decreases, traded-through buckets and
expiry); a cluster at 2% of OI in one 0.1% bucket may be rare; day clustering treats days as independent (OR-HM1).
