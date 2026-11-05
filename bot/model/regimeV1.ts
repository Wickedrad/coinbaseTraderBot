// TypeScript mirror of the shared regime v1 spec (frozen 15:45 UTC Nov 5,
// /mnt/project-files/registry/regime-v1-spec.md). Only the RV tercile and
// the z60 trend score are mirrored here: gate tests use the tercile.
//
// RV60  = sqrt(sum r_i^2) over the last 60 closed 1-minute log returns
//         (needs >= 50 returns, else NA). Not annualized.
// q33/q67 = linear-interpolated 33.33/66.67 percentiles of every minute
//         RV60 for the asset over the 30 days ending at the previous
//         00:00 UTC, recomputed once per UTC day. NA when those values lie
//         on fewer than 7 distinct UTC days.
// Label at minute t uses data up to the close of minute t-1 only.

export type Tercile = 'LOW' | 'MID' | 'HIGH' | 'NA';

const MIN = 60_000;
const DAY = 86_400_000;

/** Linear-interpolated percentile (numpy default) of a sorted array. */
export function percentileSorted(sorted: number[], q: number): number {
  if (sorted.length === 0) return NaN;
  const pos = (q / 100) * (sorted.length - 1);
  const lo = Math.floor(pos), hi = Math.ceil(pos);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
}

/** RV60 from the closes of the 61 minutes ending at minute t-1 (keys are minute-start ms). */
export function rv60(closes: Map<number, number>, t: number): number {
  let sum = 0, n = 0;
  for (let k = 1; k <= 60; k++) {
    const a = closes.get(t - k * MIN), b = closes.get(t - (k + 1) * MIN);
    if (a === undefined || b === undefined || a <= 0 || b <= 0) continue;
    const r = Math.log(a / b);
    sum += r * r; n++;
  }
  return n >= 50 ? Math.sqrt(sum) : NaN;
}

interface AssetState {
  closes: Map<number, number>;   // minute start -> close
  rv: { t: number; v: number }[]; // minute RV60 history (t = label minute)
  firstT: number;
  cutDay: number;                 // UTC day start the cut points belong to
  q33: number; q67: number;
}

/** Streaming per-asset tracker. Feed each closed 1-minute candle in time order. */
export class RegimeV1 {
  private s = new Map<string, AssetState>();

  private st(asset: string): AssetState {
    let a = this.s.get(asset);
    if (!a) { a = { closes: new Map(), rv: [], firstT: NaN, cutDay: NaN, q33: NaN, q67: NaN }; this.s.set(asset, a); }
    return a;
  }

  /** Record the close of the minute starting at `t` (ms). */
  feedClose(asset: string, t: number, close: number): void {
    const a = this.st(asset);
    const m = Math.floor(t / MIN) * MIN;
    if (Number.isNaN(a.firstT)) a.firstT = m;
    a.closes.set(m, close);
    // RV60 labelled at minute m+1 uses closes up to minute m.
    const v = rv60(a.closes, m + MIN);
    if (!Number.isNaN(v)) a.rv.push({ t: m + MIN, v });
    // Keep 31 days of RV values and 62 minutes of closes.
    const keepRv = m - 31 * DAY;
    let drop = 0;
    while (drop < a.rv.length && a.rv[drop].t < keepRv) drop++;
    if (drop > 0) a.rv.splice(0, drop);
    a.closes.delete(m - 62 * MIN);
  }

  private cuts(a: AssetState, day: number): void {
    if (a.cutDay === day) return;
    a.cutDay = day;
    a.q33 = a.q67 = NaN;
    const from = day - 30 * DAY;
    const win = a.rv.filter(x => x.t >= from && x.t < day);
    // NA unless RV60 values lie on at least 7 distinct UTC days of the window (regime.py's rule).
    if (new Set(win.map(x => Math.floor(x.t / DAY))).size < 7) return;
    const vals = win.map(x => x.v).sort((x, y) => x - y);
    a.q33 = percentileSorted(vals, 100 / 3);
    a.q67 = percentileSorted(vals, 200 / 3);
  }

  /** Label for minute `t` (ms; uses data up to the close of minute t-1). */
  label(asset: string, t: number): { tercile: Tercile; rv60: number; q33: number; q67: number; z60: number } {
    const a = this.s.get(asset);
    const m = Math.floor(t / MIN) * MIN;
    if (!a) return { tercile: 'NA', rv60: NaN, q33: NaN, q67: NaN, z60: NaN };
    this.cuts(a, Math.floor(m / DAY) * DAY);
    const v = rv60(a.closes, m);
    const c1 = a.closes.get(m - MIN), c61 = a.closes.get(m - 61 * MIN);
    const z60 = c1 && c61 && v > 0 ? Math.log(c1 / c61) / v : NaN;
    let tercile: Tercile = 'NA';
    if (!Number.isNaN(v) && !Number.isNaN(a.q33)) tercile = v < a.q33 ? 'LOW' : v < a.q67 ? 'MID' : 'HIGH';
    return { tercile, rv60: v, q33: a.q33, q67: a.q67, z60 };
  }
}
