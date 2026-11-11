// Shared shapes of the tennis TA rulebook trial (pre-registration: /mnt/project-files/tennis-ta/preregistration.md).
// research/tennisTaSim.ts (family A: the production strategy over a config grid, and the match grids),
// research/tennisTaSignals.ts (family B: TA-Lib readings of the price path as a sterile event study, exported as
// FamilyBExport) and research/tennisTaSweep.ts (the CLI the workflow runs, which writes both into the shard files) speak
// these.

import type { MinuteCandles } from './tennisTaWindow';

/** One match's quotes on a 1-second grid, built causally while the replay streams (no lookahead: index i holds the book
 *  as it stood at t0 + i*1000 after every event stamped <= that time). Market A = the event's markets sorted by ticker [0]. */
export interface MatchGrid {
  event: string;
  series: string;
  /** Data stratum: 'H' Kalshi history (one-level synthesized book), 'R' the bot's recordings (real depth). */
  stratum: 'H' | 'R';
  tickers: [string, string];
  /** Published start (ms) if known, else the earliest market-line time (bookkeeping; startPublished says which). */
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
  /** Production's latched progress per sample (MatchTracker.progressHigh of the production-default clock, which the end
   *  loser cut and the entry block read; research/tennisTaSim.ts sets it on every grid, GridWithHigh). Family B reads it
   *  when present, else latches `progress` itself (research/tennisTaSignals.ts latchedProgress). */
  progressHigh?: Float64Array;
  /** Index of the first live sample (-1 if never live). */
  liveIdx: number;
  /** Settlement of market A: 1 = player A won, 0 = lost. */
  resultA: 0 | 1;
  /** Index after which no order may be placed (the market's close, or the grid end). */
  closeIdx: number;
  /** Tournament-week unit holding the match's start (models/tennis-ta/state/units.json id), set by the sweep before family B
   *  reads the grid: research/tennisTaSignals.ts SignalStudy.addMatch throws without it. */
  unit?: string;
  /** True when `start` is Kalshi's published start, false when it is the earliest market-line time (bookkeeping only). */
  startPublished?: boolean;
  /** Window mode (Amendment 4, research/tennisTaWindow.ts): the window rule's view of each market's Kalshi minute candles
   *  (SweepOpts.candlesOf through the sim: the first stored candle dropped, ending at or before the market's close; [] for a
   *  market without candles), set before onGrid delivers the grid when the sweep supplies candlesOf; absent otherwise. */
  candles?: { a: MinuteCandles; b: MinuteCandles };
}

/** Family B (research/tennisTaSignals.ts): one cell of the entry-locked event study, totals over a slice. Every value is
 *  dollars of net profit after fees per entry (one entry = one position of the cell: a taker buy and its exit or
 *  settlement). Real entries only, except the placebo columns of `units`. */
export interface FamilyBCell {
  /** "B|<reading>|<bar>|<trigger>|<follow|fade>|<context>|<exit>", e.g. "B|RSI14L|1m|exitExt|follow|all|tp30sl30". */
  id: string;
  /** The hypothesis group: the id without context and exit ("B|RSI14L|1m|exitExt|follow"). */
  group: string;
  /** Entries and the first four raw moments of net per entry (skew / kurtosis come from sum3 / sum4). */
  n: number; sum: number; sumSq: number; sum3: number; sum4: number;
  /** Positions held to settlement without being in profit after fees in the last share of the match. */
  breaches: number;
  /** Gross (before fees) and fees, totals. */
  gross: number; fees: number;
  /** Total net under the stress: every sale one tick lower and every fee at the stressed fee multiplier (diagnostics say
   *  which); settlement payouts unchanged. */
  stressSum: number;
  /** Per tournament-week unit: [entries, net sum, placebo entries, placebo net sum]. Compare per-unit MEANS (sum / n against
   *  placebo sum / placebo n), never sums: the two arms do not make the same number of entries. */
  units: Record<string, [number, number, number, number]>;
  /** Per UTC match-day (of the match start): [entries, net sum, placebo entries, placebo net sum]. Months (folds) are the
   *  days' YYYY-MM. The placebo columns give the registry's family B placebo row its by_day (C7). */
  days: Record<string, [number, number, number, number]>;
  /** Distinct markets (match x side) with a real entry, and with a placebo entry (the registry rows' `markets`, C7). A
   *  match is owned by one slice, so the counts add over slices. */
  markets: number; placeboMarkets: number;
}

/** Family B's part of a sweep shard file: one SignalStudy over one slice (one stratum, never H and R together). */
export interface FamilyBExport {
  stratum: 'H' | 'R';
  /** Cells in the design, fired or not (the BH m of family B for this stratum). */
  designSize: number;
  diagnostics: Record<string, unknown>;
  /** Every cell with a real or a placebo entry, in design order. */
  cells: FamilyBCell[];
}

// ---- Legacy: the shapes below (ClusterStats, CellResult, PairDiff, ClusterAcc, emptyStats, mergeStats) are read only by
// research/tennisTaStats.ts and tests/tennisTaStats.test.ts, which the report rewrite removes; family B no longer produces
// CellResult (it exports FamilyBExport above, whose placebo comparison is by per-unit means, not PairDiff's day sums).
// ConfigDay and ConfigRun stay: the sim uses them.

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
  /** Legacy (day sums): measures how many entries each arm made rather than edge when the arms' counts differ. */
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
  /** Window mode (Amendment 4, research/tennisTaSim.ts SimSpec.window): the run traded nothing; its signal instances are
   *  SimRun.instances (pnl all 0, no entry, no episode). */
  window?: true;
  stratum: 'H' | 'R';
  days: ConfigDay[];
}

/** Legacy: per-day paired difference of SUMS (a cell's day sum minus its placebo's day sum). Not used by family B any more:
 *  compare per-unit means (FamilyBCell.units) instead. */
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
