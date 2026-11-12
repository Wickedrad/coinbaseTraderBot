/** Observed-OHLC research labels, never a fill simulator or an order signal. */
import { HORIZONS_MIN, type MinuteCandle, type OpportunityEntry } from './atlas';

export const PATH_LABEL_SCHEMA = 'opportunity-path-labels-v1';
const MIN = 60_000;
export interface ReversalDefinition {
  id: string;
  lookbackMin: number;
  precedingDriftAtr: number;
  turnAtr: number;
  sustainMin: number;
}
export interface PathCosts {
  feePerSideBps: number;
  halfSpreadBps: number;
  slippagePerSideBps: number;
}
export interface PathLabelConfig {
  source: string;
  trainBefore: number;
  finalFrom: number;
  horizonsMin: number[];
  targetsAtr: number[];
  stopsAtr: number[];
  reversals: ReversalDefinition[];
  costs: PathCosts;
}
export function defaultPathConfig(source: string, trainBefore: number, finalFrom: number): PathLabelConfig {
  return { source, trainBefore, finalFrom, horizonsMin: [...HORIZONS_MIN],
    targetsAtr: [0.5, 1, 2], stopsAtr: [0.5, 1, 2],
    reversals: [
      { id: 'fast', lookbackMin: 15, precedingDriftAtr: 0.5, turnAtr: 0.5, sustainMin: 3 },
      { id: 'slow', lookbackMin: 60, precedingDriftAtr: 1, turnAtr: 1, sustainMin: 5 },
    ], costs: { feePerSideBps: 0, halfSpreadBps: 0, slippagePerSideBps: 0 } };
}
export type CensorReason = 'gap' | 'end-of-input' | 'processing-limit';
export type PathPartition = 'train' | 'development' | 'final' | 'purged';
export function pathPartition(entryAt: number, plannedThrough: number, config: Pick<PathLabelConfig, 'trainBefore' | 'finalFrom'>): PathPartition {
  if (entryAt < config.trainBefore) return plannedThrough <= config.trainBefore ? 'train' : 'purged';
  if (entryAt < config.finalFrom) return plannedThrough <= config.finalFrom ? 'development' : 'purged';
  return 'final';
}
export interface ReversalLabel extends ReversalDefinition {
  priorMoveAtr: number | null;
  context: 'reversal' | 'continuation' | 'neutral' | 'unknown';
  onsetMinute: number | null;
  confirmedMinute: number | null;
  /** Null when the preceding window is unavailable or future observation is censored. */
  occurred: boolean | null;
}
/** Minimal causal entry contract; generalized datasets keep full features in a separate keyed row. */
export interface PathEntry {
  ts: number; asset: string; price: number; f: { atrBps: number; knownAt: number };
}
export interface PathLabel<E extends PathEntry = OpportunityEntry> {
  schema: typeof PATH_LABEL_SCHEMA;
  entry: E;
  side: 'long' | 'short';
  horizonMin: number;
  targetAtr: number;
  stopAtr: number;
  targetPrice: number;
  stopPrice: number;
  observedMinutes: number;
  censorReason: CensorReason | null;
  partition: PathPartition;
  provenance: { source: string; priceBasis: 'observed-one-minute-ohlc';
    featuresKnownAt: number; futureStartsAt: number; plannedThrough: number; observedThrough: number; labelKnownAt: number;
    costAssumptions: PathCosts; execution: 'hypothetical-unit-position'; ambiguity: 'stop-first-lower-bound' };
  firstTargetMinute: number | null;
  firstStopMinute: number | null;
  firstHit: 'target' | 'stop' | 'ambiguous' | 'none';
  firstHitMinute: number | null;
  /** The touch occurred somewhere inside this minute; no sub-minute precision is implied. */
  firstHitWindow: { startsAt: number; knownAt: number } | null;
  mfeBps: number;
  maeBps: number;
  /** False for censored paths without an observed barrier hit. */
  payoffAvailable: boolean;
  payoffBasis: 'barrier' | 'horizon-close' | 'ambiguous-lower-bound' | 'unavailable';
  exitPrice: number | null;
  grossReturnBps: number | null;
  netReturnBps: number | null;
  reversals: ReversalLabel[];
}
interface ReversalState {
  definition: ReversalDefinition;
  priorMoveAtr: number | null;
  context: ReversalLabel['context'];
  run: number;
  onset: number | null;
  confirmed: number | null;
}
interface BarrierState {
  targetAtr: number;
  stopAtr: number;
  targetPrice: number;
  stopPrice: number;
  targetMinute: number | null;
  stopMinute: number | null;
  hit: PathLabel['firstHit'];
  hitMinute: number | null;
  exit: number | null;
}
interface SideState { direction: 1 | -1; barriers: BarrierState[]; reversals: ReversalState[] }
interface Pending<E extends PathEntry> {
  entry: E;
  observed: number;
  lastClose: number;
  high: number;
  low: number;
  sides: SideState[];
  nextHorizon: number;
  horizonsMin: number[];
}
function integer(n: number, max: number): boolean { return Number.isInteger(n) && n > 0 && n <= max; }
function validate(config: PathLabelConfig): void {
  if (!config.source || !Number.isFinite(config.trainBefore) || !Number.isFinite(config.finalFrom) || config.trainBefore >= config.finalFrom) throw new Error('invalid path source or chronological partitions');
  const unique = (xs: number[]) => new Set(xs).size === xs.length;
  if (!config.horizonsMin.length || !unique(config.horizonsMin) || config.horizonsMin.some((h, i, a) => !integer(h, 1440) || (i > 0 && h <= a[i - 1]))) throw new Error('path horizons must be unique increasing integer minutes, at most 1440');
  for (const xs of [config.targetsAtr, config.stopsAtr]) {
    if (!xs.length || xs.length > 8 || !unique(xs) || xs.some((x) => !Number.isFinite(x) || x <= 0 || x > 10)) throw new Error('path target/stop grids must have 1..8 unique ATR multiples in (0, 10]');
  }
  if (!config.reversals.length || config.reversals.length > 8 || new Set(config.reversals.map((d) => d.id)).size !== config.reversals.length) throw new Error('path reversal definitions must have unique ids');
  for (const d of config.reversals) {
    if (!d.id || !integer(d.lookbackMin, 1440) || !integer(d.sustainMin, 1440) || ![d.precedingDriftAtr, d.turnAtr].every((x) => Number.isFinite(x) && x > 0)) throw new Error('invalid path reversal definition');
  }
  if (Object.values(config.costs).length !== 3 || ![config.costs.feePerSideBps, config.costs.halfSpreadBps, config.costs.slippagePerSideBps].every((x) => Number.isFinite(x) && x >= 0 && x < 1000)) throw new Error('invalid path cost assumptions');
}
/** Simple unit-position returns: adverse spread/slippage on both legs, fees on both notionals.
 * No funding, borrow, queue, market impact or venue collateral model is asserted. */
export function hypotheticalPayoff(entry: number, exit: number, direction: 1 | -1, costs: PathCosts): { grossReturnBps: number; netReturnBps: number } {
  const friction = (costs.halfSpreadBps + costs.slippagePerSideBps) / 10_000;
  const entryFill = entry * (1 + direction * friction), exitFill = exit * (1 - direction * friction);
  const fee = costs.feePerSideBps / 10_000 * (entryFill + exitFill);
  return { grossReturnBps: direction * (exit / entry - 1) * 10_000,
    netReturnBps: (direction * (exitFill - entryFill) - fee) / entryFill * 10_000 };
}

/** Bounded by the longest horizon/lookback, with one barrier grid per entry/side,
 * shared across horizons. Entry candle extrema never enter a forward label. */
export class PathLabeler<E extends PathEntry = OpportunityEntry> {
  private readonly config: PathLabelConfig;
  private lastTs = -Infinity;
  private pending: Pending<E>[] = [];
  private history = new Map<number, number>();
  private readonly maxLookback: number;
  private readonly maxHorizon: number;
  constructor(config: PathLabelConfig) {
    validate(config);
    this.config = structuredClone(config);
    this.maxLookback = Math.max(...config.reversals.map((d) => d.lookbackMin));
    this.maxHorizon = config.horizonsMin.at(-1)!;
  }
  push(b: MinuteCandle, entry?: E, horizonsMin?: readonly number[]): PathLabel<E>[] {
    if (!Number.isInteger(b.ts / MIN) || b.ts < 0 || ![b.o, b.h, b.l, b.c, b.v].every(Number.isFinite) || b.l <= 0 || b.h < Math.max(b.o, b.c) || b.l > Math.min(b.o, b.c) || b.v < 0) throw new Error('invalid path candle');
    if (b.ts <= this.lastTs) throw new Error('path candles must have strictly increasing timestamps');
    if (entry && (entry.ts !== b.ts + MIN || entry.price !== b.c || !Number.isFinite(entry.f.knownAt) || entry.f.knownAt > entry.ts || !(entry.f.atrBps > 0) || !Number.isFinite(entry.f.atrBps))) throw new Error('invalid or noncausal path entry');
    // Every configured price level must be positive, including short targets and long stops.
    if (entry && Math.max(...this.config.targetsAtr, ...this.config.stopsAtr) * entry.f.atrBps >= 10_000) throw new Error('path barrier would have non-positive price');
    if (horizonsMin && (!entry || !horizonsMin.length || horizonsMin.some((h, i) => !integer(h, this.maxHorizon) || (i > 0 && h <= horizonsMin[i - 1])))) throw new Error('entry horizons must be unique increasing minutes within the configured maximum');
    const out: PathLabel<E>[] = [];
    if (Number.isFinite(this.lastTs) && b.ts !== this.lastTs + MIN) {
      out.push(...this.finish('gap', b.ts + MIN));
      this.history.clear();
    }
    this.lastTs = b.ts;
    for (const p of this.pending) {
      p.observed++; p.lastClose = b.c;
      p.high = Math.max(p.high, b.h); p.low = Math.min(p.low, b.l);
      for (const s of p.sides) {
        this.advanceBarriers(p, s, b);
        for (const r of s.reversals) {
          if (r.confirmed !== null || r.context === 'neutral' || r.context === 'unknown') continue;
          const moveAtr = s.direction * (b.c / p.entry.price - 1) * 10_000 / p.entry.f.atrBps;
          if (moveAtr >= r.definition.turnAtr) {
            if (r.run++ === 0) r.onset = p.observed;
            if (r.run >= r.definition.sustainMin) r.confirmed = p.observed;
          } else { r.run = 0; r.onset = null; }
        }
      }
      if (p.observed === p.horizonsMin[p.nextHorizon]) {
        out.push(...this.rows(p, p.horizonsMin[p.nextHorizon], null));
        p.nextHorizon++;
      }
    }
    this.pending = this.pending.filter((p) => p.observed < p.horizonsMin.at(-1)!);
    if (entry) this.pending.push(this.start(entry, horizonsMin ?? this.config.horizonsMin));
    this.history.set(b.ts + MIN, b.c);
    for (const t of this.history.keys()) { if (t < b.ts + MIN - this.maxLookback * MIN) this.history.delete(t); else break; }
    return out;
  }
  /** Unfinished horizons are emitted once, never silently treated as negative events. */
  finish(reason: CensorReason = 'end-of-input', detectedAt?: number): PathLabel<E>[] {
    if (detectedAt !== undefined && !Number.isFinite(detectedAt)) throw new Error('invalid censor detection timestamp');
    const out = this.pending.flatMap((p) => p.horizonsMin.slice(p.nextHorizon).flatMap((h) => this.rows(p, h, reason, detectedAt)));
    this.pending = [];
    return out;
  }
  private start(entry: E, horizonsMin: readonly number[]): Pending<E> {
    const snapshot = structuredClone(entry);
    const sides = ([1, -1] as const).map((direction): SideState => ({ direction,
      barriers: this.config.targetsAtr.flatMap((targetAtr) => this.config.stopsAtr.map((stopAtr): BarrierState => ({
        targetAtr, stopAtr, targetPrice: entry.price * (1 + direction * targetAtr * entry.f.atrBps / 10_000),
        stopPrice: entry.price * (1 - direction * stopAtr * entry.f.atrBps / 10_000),
        targetMinute: null, stopMinute: null, hit: 'none', hitMinute: null, exit: null,
      }))),
      reversals: this.config.reversals.map((definition) => {
        const prior = this.history.get(entry.ts - definition.lookbackMin * MIN);
        const priorMoveAtr = prior === undefined ? null : direction * (entry.price / prior - 1) * 10_000 / entry.f.atrBps;
        const context = priorMoveAtr === null ? 'unknown' : priorMoveAtr <= -definition.precedingDriftAtr ? 'reversal'
          : priorMoveAtr >= definition.precedingDriftAtr ? 'continuation' : 'neutral';
        return { definition, priorMoveAtr, context, run: 0, onset: null, confirmed: null };
      }),
    }));
    return { entry: snapshot, observed: 0, lastClose: entry.price, high: entry.price, low: entry.price, sides, nextHorizon: 0, horizonsMin: [...horizonsMin] };
  }
  private advanceBarriers(p: Pending<E>, s: SideState, b: MinuteCandle): void {
    for (const q of s.barriers) {
      const target = s.direction === 1 ? b.h >= q.targetPrice : b.l <= q.targetPrice;
      const stop = s.direction === 1 ? b.l <= q.stopPrice : b.h >= q.stopPrice;
      if (target && q.targetMinute === null) q.targetMinute = p.observed;
      if (stop && q.stopMinute === null) q.stopMinute = p.observed;
      if (q.hit !== 'none' || (!target && !stop)) continue;
      const opensAtTarget = s.direction * (b.o - q.targetPrice) >= 0;
      const opensAtStop = s.direction * (b.o - q.stopPrice) <= 0;
      // Open is the first observed price. Gap stops fill at the worse open;
      // favorable gap targets conservatively fill at their limit, not the open.
      q.hit = opensAtTarget ? 'target' : opensAtStop ? 'stop' : target && stop ? 'ambiguous' : target ? 'target' : 'stop';
      q.hitMinute = p.observed;
      q.exit = q.hit === 'target' ? q.targetPrice : opensAtStop ? b.o : q.stopPrice;
    }
  }
  private rows(p: Pending<E>, horizonMin: number, censorReason: CensorReason | null, detectedAt?: number): PathLabel<E>[] {
    const plannedThrough = p.entry.ts + horizonMin * MIN;
    const observedThrough = p.entry.ts + p.observed * MIN;
    const labelKnownAt = Math.max(observedThrough, detectedAt ?? observedThrough);
    return p.sides.flatMap((s) => s.barriers.map((q): PathLabel<E> => {
      const exit = q.exit ?? (censorReason === null ? p.lastClose : null);
      const reversals = s.reversals.map((r): ReversalLabel => ({ ...r.definition,
        priorMoveAtr: r.priorMoveAtr, context: r.context,
        onsetMinute: r.confirmed === null ? null : r.onset, confirmedMinute: r.confirmed,
        occurred: r.context === 'unknown' ? null : r.confirmed !== null ? true : censorReason !== null ? null : false,
      }));
      return { schema: PATH_LABEL_SCHEMA, entry: structuredClone(p.entry), side: s.direction === 1 ? 'long' : 'short',
        horizonMin, targetAtr: q.targetAtr, stopAtr: q.stopAtr, targetPrice: q.targetPrice, stopPrice: q.stopPrice,
        observedMinutes: p.observed, censorReason,
        partition: pathPartition(p.entry.ts, Math.max(plannedThrough, labelKnownAt), this.config),
        provenance: { source: this.config.source, priceBasis: 'observed-one-minute-ohlc', featuresKnownAt: p.entry.f.knownAt,
          futureStartsAt: p.entry.ts, plannedThrough, observedThrough, labelKnownAt, costAssumptions: { ...this.config.costs },
          execution: 'hypothetical-unit-position', ambiguity: 'stop-first-lower-bound' },
        firstTargetMinute: q.targetMinute, firstStopMinute: q.stopMinute, firstHit: q.hit, firstHitMinute: q.hitMinute,
        firstHitWindow: q.hitMinute === null ? null : { startsAt: p.entry.ts + (q.hitMinute - 1) * MIN, knownAt: p.entry.ts + q.hitMinute * MIN },
        mfeBps: Math.max(0, s.direction * ((s.direction === 1 ? p.high : p.low) / p.entry.price - 1) * 10_000),
        maeBps: Math.max(0, -s.direction * ((s.direction === 1 ? p.low : p.high) / p.entry.price - 1) * 10_000),
        payoffAvailable: exit !== null,
        payoffBasis: exit === null ? 'unavailable' : q.hit === 'ambiguous' ? 'ambiguous-lower-bound' : q.hit !== 'none' ? 'barrier' : 'horizon-close', exitPrice: exit,
        ...(exit === null ? { grossReturnBps: null, netReturnBps: null } : hypotheticalPayoff(p.entry.price, exit, s.direction, this.config.costs)),
        reversals };
    }));
  }
}
