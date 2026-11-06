/**
 * Failure diagnosis SNN-H1 (lead information) and its placebos: the per-column fair-value gap (fair value minus the
 * Kalshi mid, cents) by minute, so a replay can feed the SNN the gap from `shiftMs` earlier instead of the current one.
 *   shift 0       -> arm G (the current gap)
 *   shift 60 s    -> the 1-minute stale-input check (a speed edge should fade)
 *   shift >= 7 d  -> placebo (same distribution, no information about this contract)
 * The tape outlives one replay call (weekly chunks, chained jobs): it serializes into the checkpoint file.
 */
export interface GapTapeJson { shiftMs: number; cols: Record<string, [number, number][]> }

export class GapTape {
  private readonly cols = new Map<string, Map<number, number>>();
  constructor(readonly shiftMs: number) {}

  static from(j: GapTapeJson | undefined, shiftMs: number): GapTape {
    const t = new GapTape(shiftMs);
    if (j && j.shiftMs === shiftMs) for (const [k, rows] of Object.entries(j.cols)) t.cols.set(k, new Map(rows));
    return t;
  }

  /** Record the current gap of a column (the last value in a minute wins) and return the gap the SNN is fed. */
  feed(key: string, ts: number, gap: number | undefined): number | undefined {
    if (this.shiftMs <= 0) return gap;
    const minute = Math.floor(ts / 60_000);
    let m = this.cols.get(key);
    if (!m) { m = new Map(); this.cols.set(key, m); }
    if (gap !== undefined && Number.isFinite(gap)) m.set(minute, gap);
    return m.get(Math.floor((ts - this.shiftMs) / 60_000));
  }

  /** Drop minutes older than the shift plus a day. */
  prune(now: number): void {
    const keep = Math.floor((now - this.shiftMs - 86_400_000) / 60_000);
    for (const m of this.cols.values()) for (const k of m.keys()) if (k < keep) m.delete(k);
  }

  toJSON(): GapTapeJson {
    return { shiftMs: this.shiftMs, cols: Object.fromEntries([...this.cols].map(([k, m]) => [k, [...m]])) };
  }
}
