// Regime v1 RV60 terciles (research/regime.py on the meta plan branch, spec /mnt/project-files/registry/regime-v1-spec.md)
// on a perp TA grid's spot bars, for the held-out standard HO-1 (README of the project registry, Nov 5 2026): a result's
// held-out $/h must hold in at least 2 of the 3 RV terciles.
//
// Label at minute i (bar open t0 + i min) uses only bars that closed by then (bars i-1 and earlier):
//   RV60    sqrt(sum of squared 1-minute log returns of the bars opened in [i-60, i-1]); a return needs the bar before it;
//           NA under 50 returns, and no label at all when bar i-1 is missing (regime.py labels t only after bar t-1)
//   q33/67  33.33 / 66.67 percentiles (numpy linear interpolation) of every labelled RV60 in the 30 days ending at the
//           previous 00:00 UTC; NA when those labels span fewer than 7 distinct UTC days
//   tercile 0 LOW (RV60 < q33), 1 MID (q33 <= RV60 < q67), 2 HIGH (RV60 >= q67), -1 NA
// Spot bars: spotFromCsv reads the coin's Binance 1-minute CSV exactly as regime.py read_closes does (every row with a
// positive close is a bar; float64). Without it the grid is used: it fills a minute with no spot bar with the previous
// close at zero volume, so a zero-volume minute that is not valid counts as a hole (a real zero-volume spot bar with no
// perp bar is lost too), and its closes are Float32.

import fs from 'fs';
import readline from 'readline';

const MIN = 60_000;
const DAY = 86_400_000;
const LOOKBACK_DAYS = 30, MIN_DAYS = 7, MIN_RETURNS = 50;

/** The coin's spot bars on the grid's minutes from its Binance 1m CSV (ts,o,h,l,c,...; ts in ms or s), as regime.py
 *  read_closes: rows with ts > 0 and close > 0, ts floored to the minute. undefined when the file is missing. */
export async function spotFromCsv(file: string, t0: number, n: number): Promise<{ has: Uint8Array; close: Float64Array } | undefined> {
  if (!fs.existsSync(file)) return undefined;
  const has = new Uint8Array(n), close = new Float64Array(n);
  const rl = readline.createInterface({ input: fs.createReadStream(file), crlfDelay: Infinity });
  for await (const line of rl) {
    if (!line || line.startsWith('ts')) continue;
    const f = line.split(','), ts0 = Number(f[0]), c = Number(f[4]);
    if (!(ts0 > 0) || !(c > 0)) continue;
    let ts = Math.trunc(ts0 > 1e11 ? ts0 : ts0 * 1000);
    ts -= ts % MIN;
    const i = (ts - t0) / MIN;
    if (i >= 0 && i < n) { has[i] = 1; close[i] = c; }
  }
  return { has, close };
}

/** numpy.percentile(x, q) with linear interpolation; xs ascending. */
export function percentile(xs: Float64Array, q: number): number {
  const n = xs.length;
  if (!n) return NaN;
  const pos = ((n - 1) * q) / 100, lo = Math.floor(pos), hi = Math.min(lo + 1, n - 1);
  return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo);
}

/** RV60 per minute (NaN = NA or no label). bar(i): whether minute i has a spot bar; close(i) its close. */
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

/** Tercile per minute in [from, to) (Int8Array over the whole grid; -1 outside or NA). */
export function rvTerciles(t0: number, n: number, bar: (i: number) => boolean, close: (i: number) => number, from = 0, to = n): Int8Array {
  const rv = rv60(n, bar, close), ter = new Int8Array(n).fill(-1);
  const idxOf = (t: number) => Math.ceil((t - t0) / MIN);
  for (let day0 = Math.floor((t0 + Math.max(0, from) * MIN) / DAY) * DAY; day0 < t0 + to * MIN; day0 += DAY) {
    const a = Math.max(0, idxOf(day0 - LOOKBACK_DAYS * DAY)), b = Math.max(0, Math.min(n, idxOf(day0)));
    const vals: number[] = [], days = new Set<number>();
    for (let i = a; i < b; i++) if (rv[i] === rv[i]) { vals.push(rv[i]); days.add(Math.floor((t0 + i * MIN) / DAY)); }
    let q33 = NaN, q67 = NaN;
    if (days.size >= MIN_DAYS) { const xs = Float64Array.from(vals).sort(); q33 = percentile(xs, 100 / 3); q67 = percentile(xs, 200 / 3); }
    const s = Math.max(from, idxOf(day0)), e = Math.min(to, idxOf(day0 + DAY));
    for (let i = s; i < e; i++) {
      const r = rv[i];
      if (!(r === r) || !(q33 === q33)) continue;
      ter[i] = r < q33 ? 0 : r < q67 ? 1 : 2;
    }
  }
  return ter;
}
