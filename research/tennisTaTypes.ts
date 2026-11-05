// Shared shapes of the tennis TA rulebook trial (pre-registration: /mnt/project-files/tennis-ta/preregistration.md).
// research/tennisTaSim.ts (family A: the production strategy over a config grid), research/tennisTaSignals.ts (family B:
// TA-Lib readings of the price path as a sterile event study), research/tennisTaStats.ts (clustered statistics, BH,
// CSCV) and research/tennisTaSweep.ts (the CLI the workflow runs) all speak these.

/** One match's quotes on a 1-second grid, built causally while the replay streams (no lookahead: index i holds the book
 *  as it stood at t0 + i*1000 after every event stamped <= that time). Market A = the event's markets sorted by ticker [0]. */
export interface MatchGrid {
  event: string;
  series: string;
  /** Data stratum: 'H' Kalshi history (one-level synthesized book), 'R' the bot's recordings (real depth). */
  stratum: 'H' | 'R';
  tickers: [string, string];
  /** Published start (ms) if known, else the first sample. */
  start: number;
  /** UTC day of `start` (YYYY-MM-DD): the cluster for inference. */
  day: string;
  /** First sample time (ms) and sample count; step is 1000 ms. */
  t0: number;
  n: number;
  /** Best bid / ask of each market (NaN where the book was not usable: older than 5 s, crossed or empty). */
  bidA: Float64Array; askA: Float64Array; bidB: Float64Array; askB: Float64Array;
  /** Contracts traded in the second ending at each sample: YES-taker and NO-taker counts per market. */
  yesVolA: Float64Array; noVolA: Float64Array; yesVolB: Float64Array; noVolB: Float64Array;
  /** Top-3 depth imbalance of each market (NaN without a book; always 0 on H, whose book is one symmetric level). */
  imbA: Float64Array; imbB: Float64Array;
  /** Match progress 0..1 per sample from the production clock (bot/tennis/tennisStrategy.ts MatchTracker.progress, no
   *  score on H; R uses recorded scores when present). 0 before the match is live. */
  progress: Float64Array;
  /** Index of the first live sample (-1 if never live). */
  liveIdx: number;
  /** Settlement of market A: 1 = player A won, 0 = lost. */
  resultA: 0 | 1;
  /** Index after which no order may be placed (the market's close, or the grid end). */
  closeIdx: number;
}

/** Per-cell accumulator with match-day clusters, kept online: matches arrive in start order inside a slice, so a cell's
 *  running day sum is flushed into the totals when the day changes. Folds are calendar months (YYYY-MM). */
export interface ClusterStats {
  /** Entries, sum of net $ per entry, sum of squares of per-entry net. */
  n: number; sum: number; sumSq: number;
  /** Day clusters: count, and sum over clusters of (cluster sum)^2 and of (cluster n)^2 and (cluster n * cluster sum). */
  clusters: number; cSumSq: number; cNSq: number; cNSum: number;
}

export interface CellResult {
  /** Stable id: family, reading, bar, trigger, direction, context, exit (e.g. "B|RSI14|30s|exitLow|follow|p15-35:mid:trend|tp30sl30"). */
  id: string;
  family: 'A' | 'B';
  /** Hypothesis group for one-representative-per-group reporting (B: reading+bar+trigger+direction). */
  group: string;
  total: ClusterStats;
  /** By fold (YYYY-MM). */
  folds: Record<string, ClusterStats>;
  /** The same cell under the stress fill model (F2), totals only. */
  stress?: ClusterStats;
  /** The cell's placebo (B: the signal shifted within the match; A: coin-flip confluence) totals, same entry rule. */
  placebo?: ClusterStats;
  /** Per-day paired difference against the placebo (same days). */
  pairDiff?: PairDiff;
  /** Settlement-rule breaches (positions that reached settlement not in profit after fees or before the last 30%). */
  breaches: number;
  /** Gross $ (before fees) and fees $, totals. */
  gross: number; fees: number;
}

/** Family A: one config's evaluation over a slice, per match-day (merged across slices by the report). */
export interface ConfigDay {
  day: string;
  matches: number;
  /** Matches where the config traded at all. */
  traded: number;
  entries: number;
  pnl: number;
  gross: number;
  fees: number;
  breaches: number;
  unresolved: number;
  /** Fills by leg. */
  legs: Record<string, number>;
}

export interface ConfigRun {
  id: string;
  /** The knobs that differ from production (env-style names: TENNIS_CONF_FLOW etc., plus HARNESS_* for harness rules). */
  overrides: Record<string, string | number | boolean>;
  fill: 'F0' | 'F1' | 'F2';
  placebo?: 'coin';
  stratum: 'H' | 'R';
  days: ConfigDay[];
}

/** Per-day paired difference (a cell's day sum minus its placebo's day sum, both over the same match-days). */
export interface PairDiff { clusters: number; sum: number; sumSq: number }

export const emptyStats = (): ClusterStats => ({ n: 0, sum: 0, sumSq: 0, clusters: 0, cSumSq: 0, cNSq: 0, cNSum: 0 });

/** Online accumulator for one cell: per-entry values tagged with their match-day; a day's cluster is flushed into the
 *  totals (and its month's fold) when a later day arrives or at flush(). Days must arrive in non-decreasing order. */
export class ClusterAcc {
  readonly total = emptyStats();
  readonly folds: Record<string, ClusterStats> = {};
  private day = '';
  private dn = 0;
  private ds = 0;
  add(x: number, day: string): void {
    if (day !== this.day) { this.flush(); this.day = day; }
    this.dn++; this.ds += x;
    this.total.n++; this.total.sum += x; this.total.sumSq += x * x;
    const f = (this.folds[day.slice(0, 7)] ??= emptyStats());
    f.n++; f.sum += x; f.sumSq += x * x;
  }
  /** Close the current day's cluster. */
  flush(): void {
    if (!this.dn) return;
    for (const s of [this.total, (this.folds[this.day.slice(0, 7)] ??= emptyStats())]) {
      s.clusters++; s.cSumSq += this.ds * this.ds; s.cNSq += this.dn * this.dn; s.cNSum += this.dn * this.ds;
    }
    this.dn = 0; this.ds = 0;
  }
}

/** Merge b into a (clusters from different slices never share a day: slices are whole days). */
export function mergeStats(a: ClusterStats, b: ClusterStats): ClusterStats {
  a.n += b.n; a.sum += b.sum; a.sumSq += b.sumSq; a.clusters += b.clusters; a.cSumSq += b.cSumSq; a.cNSq += b.cNSq; a.cNSum += b.cNSum;
  return a;
}
