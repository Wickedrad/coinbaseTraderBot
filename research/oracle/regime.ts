// Regime v1 context for the oracle-setups exporter (prereg python/oracle/prereg/OR-H1.md "Features: Context" and
// "Mining: matched base rate"; SPEC.md 2a): the RV60 tercile and the 60-minute trend bucket, causal, per minute.
//
// Ported from research/perpTaRegime.ts on origin/claude/project-thread-9040i4 (spotFromCsv, percentile, rv60,
// rvTerciles; that file is not on this branch), which matches research/regime.py (origin/claude/project-thread-79ntof,
// regime-v1.1) on 57,600 of 57,600 test minutes. Added here: z60 and its trend bucket (regime.py rv_series / label),
// tercilesFromRv (rvTerciles without recomputing RV60), and a cut-off on spotFromCsv so no row at or after the
// study's end is parsed.
//
// Label at minute i (the instant t0 + i min, the open of bar i) uses only bars that closed by then (bars i-1 and earlier):
//   RV60    sqrt(sum of squared 1-minute log returns of the bars opened in [i-60, i-1]); a return needs the bar before it;
//           NA under 50 returns, and no label at all when bar i-1 is missing (regime.py labels t only after bar t-1)
//   q33/67  33.33 / 66.67 percentiles (numpy linear interpolation) of every labelled RV60 in the 30 days ending at the
//           previous 00:00 UTC; NA when those labels span fewer than 7 distinct UTC days
//   tercile 0 LOW (RV60 < q33), 1 MID (q33 <= RV60 < q67), 2 HIGH (RV60 >= q67), -1 NA
//   z60     ln(close[i-1] / close[i-61]) / RV60 (NaN without bar i-61 or RV60); regime.py trend FLAT |z| < 1,
//           TREND 1..2, STRONG > 2; signed here: 0 STRONG down, 1 TREND down, 2 FLAT, 3 TREND up, 4 STRONG up, -1 NA
// So a decision made at the END of grid minute i (instant t0 + (i + 1) min) reads label index i + 1.

import fs from 'fs';
import readline from 'readline';

const MIN = 60_000;
const DAY = 86_400_000;
const LOOKBACK_DAYS = 30, MIN_DAYS = 7, MIN_RETURNS = 50;

/** The coin's spot bars on the grid's minutes from its Binance 1m CSV (ts,o,h,l,c,...; ts in ms or s), as regime.py
 *  read_closes: rows with ts > 0 and close > 0, ts floored to the minute. undefined when the file is missing.
 *  The CSV is time-sorted (research/history/binanceVision.ts): parsing stops at the first row at or after minute n. */
export async function spotFromCsv(file: string, t0: number, n: number): Promise<{ has: Uint8Array; close: Float64Array } | undefined> {
  if (!fs.existsSync(file)) return undefined;
  const has = new Uint8Array(n), close = new Float64Array(n), end = t0 + n * MIN;
  const input = fs.createReadStream(file);
  const rl = readline.createInterface({ input, crlfDelay: Infinity });
  for await (const line of rl) {
    if (!line || line.startsWith('ts')) continue;
    const f = line.split(','), ts0 = Number(f[0]), c = Number(f[4]);
    if (!(ts0 > 0)) continue;
    let ts = Math.trunc(ts0 > 1e11 ? ts0 : ts0 * 1000);
    ts -= ts % MIN;
    if (ts >= end) break;
    if (!(c > 0)) continue;
    const i = (ts - t0) / MIN;
    if (i >= 0 && i < n) { has[i] = 1; close[i] = c; }
  }
  rl.close(); input.destroy();
  return { has, close };
}

/** numpy.percentile(x, q) with linear interpolation; xs ascending. */
export function percentile(xs: Float64Array, q: number): number {
  const n = xs.length;
  if (!n) return NaN;
  const pos = ((n - 1) * q) / 100, lo = Math.floor(pos), hi = Math.min(lo + 1, n - 1);
  return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo);
}

/** RV60 per label index (NaN = NA or no label). bar(i): whether minute i has a spot bar; close(i) its close. */
export function rv60(n: number, bar: (i: number) => boolean, close: (i: number) => number): Float64Array {
  const rv = new Float64Array(n).fill(NaN);
  const r2 = new Float64Array(n).fill(NaN); // squared return of bar j (needs bar j-1)
  for (let j = 1; j < n; j++) if (bar(j) && bar(j - 1)) { const r = Math.log(close(j) / close(j - 1)); r2[j] = r * r; }
  let ss = 0, cnt = 0;
  for (let i = 1; i < n; i++) {
    // window: returns of bars i-60 .. i-1
    const add = i - 1, drop = i - 61;
    if (r2[add] === r2[add]) { ss += r2[add]; cnt++; }
    if (drop >= 0 && r2[drop] === r2[drop]) { ss -= r2[drop]; cnt--; }
    if (!bar(i - 1) || cnt < MIN_RETURNS) continue;
    rv[i] = Math.sqrt(Math.max(ss, 0));
  }
  return rv;
}

/** Tercile per label index in [from, to) from an rv60() series (-1 outside or NA). Same arithmetic as rvTerciles. */
export function tercilesFromRv(t0: number, rv: Float64Array, from = 0, to = rv.length): Int8Array {
  const n = rv.length, ter = new Int8Array(n).fill(-1);
  const idxOf = (t: number) => Math.ceil((t - t0) / MIN);
  for (let day0 = Math.floor((t0 + Math.max(0, from) * MIN) / DAY) * DAY; day0 < t0 + to * MIN; day0 += DAY) {
    const a = Math.max(0, idxOf(day0 - LOOKBACK_DAYS * DAY)), b = Math.max(0, Math.min(n, idxOf(day0)));
    let cnt = 0, days = 0, lastDay = NaN;
    for (let i = a; i < b; i++) if (rv[i] === rv[i]) { cnt++; const d = Math.floor((t0 + i * MIN) / DAY); if (d !== lastDay) { days++; lastDay = d; } }
    let q33 = NaN, q67 = NaN;
    if (days >= MIN_DAYS) {
      const xs = new Float64Array(cnt);
      let k = 0;
      for (let i = a; i < b; i++) if (rv[i] === rv[i]) xs[k++] = rv[i];
      xs.sort();
      q33 = percentile(xs, 100 / 3); q67 = percentile(xs, 200 / 3);
    }
    const s = Math.max(from, idxOf(day0)), e = Math.min(to, idxOf(day0 + DAY));
    for (let i = s; i < e; i++) {
      const r = rv[i];
      if (!(r === r) || !(q33 === q33)) continue;
      ter[i] = r < q33 ? 0 : r < q67 ? 1 : 2;
    }
  }
  return ter;
}

/** Tercile per minute in [from, to) (Int8Array over the whole grid; -1 outside or NA). The perpTaRegime.ts signature. */
export function rvTerciles(t0: number, n: number, bar: (i: number) => boolean, close: (i: number) => number, from = 0, to = n): Int8Array {
  return tercilesFromRv(t0, rv60(n, bar, close), from, to);
}

/** z60 per label index: ln(close[i-1] / close[i-61]) / RV60[i] (regime.py: needs bar i-61 and RV60 > 0). */
export function z60(rv: Float64Array, bar: (i: number) => boolean, close: (i: number) => number): Float64Array {
  const z = new Float64Array(rv.length).fill(NaN);
  for (let i = 61; i < rv.length; i++) {
    const r = rv[i];
    if (!(r > 0) || !bar(i - 61)) continue;
    z[i] = Math.log(close(i - 1) / close(i - 61)) / r;
  }
  return z;
}

export const TREND_LEVELS = ['STRONG_DOWN', 'TREND_DOWN', 'FLAT', 'TREND_UP', 'STRONG_UP'];

/** regime.py's trend bucket (FLAT |z| < 1, TREND |z| <= 2, STRONG above) with the sign of z: 0..4, -1 NA. */
export function trendBucket(z: number): number {
  if (!(z === z)) return -1;
  const a = Math.abs(z);
  if (a < 1) return 2;
  return a <= 2 ? (z > 0 ? 3 : 1) : (z > 0 ? 4 : 0);
}
