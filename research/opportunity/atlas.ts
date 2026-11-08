/**
 * Research-only conditional opportunity atlas.
 *
 * Decisions are made AFTER a completed one-minute candle. Labels are resolved
 * only after H subsequent, contiguous one-minute candles. No live order code
 * imports this module. Never fit, select and judge a feature on the same dates.
 */
export const ATLAS_SCHEMA = 'opportunity-atlas-v1';
export const HORIZONS_MIN = [5, 15, 30, 60, 120, 240, 480, 1440] as const;
export type HorizonMin = typeof HORIZONS_MIN[number];
const MINUTE = 60_000;
const ATLAS_GROUPS = ['macd', 'bands', 'session', 'time', 'dominance', 'macd_bands', 'macd_session'] as const;
export type AtlasGroup = typeof ATLAS_GROUPS[number];

export interface MinuteCandle { ts: number; o: number; h: number; l: number; c: number; v: number }
export interface AtlasFeatures {
  rsi: number;
  macdBps: number;
  bbPctB: number;
  atrBps: number;
  session: string;
  etHour: number; // continuous 0..24, learned with wraparound rather than a trading-time gate
  btcdDailyChange: number;
  usdtdDailyChange: number;
  /** The timestamp of the LAST fully completed source candle, never the forming candle. */
  knownAt: number;
}
export interface OpportunityEntry { ts: number; asset: string; price: number; f: AtlasFeatures }
export interface Outcome {
  entry: OpportunityEntry;
  horizonMin: HorizonMin;
  resolvedAt: number;
  /** Close-to-close direction and return. NOT a trade fill, reversal-onset or net P&L label. */
  up: boolean;
  returnBps: number;
  maxUpBps: number;
  maxDownBps: number;
  /** ATR-based touch rates; the order of target and stop touches is NOT known here. */
  upOneAtr: boolean;
  downOneAtr: boolean;
}

class Extrema {
  private high: Array<[number, number]> = [];
  private low: Array<[number, number]> = [];
  private hiHead = 0;
  private loHead = 0;
  clear(): void { this.high = []; this.low = []; this.hiHead = 0; this.loHead = 0; }
  add(i: number, b: MinuteCandle, n: number): void {
    while (this.high.length > this.hiHead && this.high[this.high.length - 1][1] <= b.h) this.high.pop();
    while (this.low.length > this.loHead && this.low[this.low.length - 1][1] >= b.l) this.low.pop();
    this.high.push([i, b.h]); this.low.push([i, b.l]);
    while (this.high[this.hiHead][0] <= i - n) this.hiHead++;
    while (this.low[this.loHead][0] <= i - n) this.loHead++;
    if (this.hiHead > 2048) { this.high = this.high.slice(this.hiHead); this.hiHead = 0; }
    if (this.loHead > 2048) { this.low = this.low.slice(this.loHead); this.loHead = 0; }
  }
  hi(): number { return this.high[this.hiHead][1]; }
  lo(): number { return this.low[this.loHead][1]; }
}

/** Streaming exact future-window extrema, O(number of horizons) per minute. */
export class OpportunityLabeler {
  private lastTs = -Infinity;
  private i = -1;
  private pending = new Map<number, OpportunityEntry>();
  private extrema = HORIZONS_MIN.map(() => new Extrema());
  gaps = 0;
  reset(): void {
    this.i = -1;
    this.pending.clear();
    for (const e of this.extrema) e.clear();
  }
  /** `entry` may only refer to the close of THIS minute, after all feature candles have closed. */
  push(b: MinuteCandle, entry?: OpportunityEntry): Outcome[] {
    if (!(b.ts > this.lastTs)) throw new Error('non-increasing one-minute timestamps');
    if (Number.isFinite(this.lastTs) && b.ts !== this.lastTs + MINUTE) { this.gaps++; this.reset(); }
    this.lastTs = b.ts;
    this.i++;
    const out: Outcome[] = [];
    for (let h = 0; h < HORIZONS_MIN.length; h++) {
      const n = HORIZONS_MIN[h];
      const q = this.extrema[h];
      q.add(this.i, b, n);
      const e = this.pending.get(this.i - n);
      if (!e) continue;
      const maxUpBps = 10_000 * Math.log(q.hi() / e.price);
      const maxDownBps = 10_000 * Math.log(e.price / q.lo());
      const returnBps = 10_000 * Math.log(b.c / e.price);
      const t = e.f.atrBps;
      out.push({ entry: e, horizonMin: n, resolvedAt: b.ts + MINUTE, up: returnBps > 0,
        returnBps, maxUpBps, maxDownBps, upOneAtr: t > 0 && maxUpBps >= t, downOneAtr: t > 0 && maxDownBps >= t });
    }
    this.pending.delete(this.i - HORIZONS_MIN[HORIZONS_MIN.length - 1]);
    if (entry) {
      if (entry.ts !== b.ts + MINUTE || entry.price !== b.c || entry.f.knownAt > entry.ts) throw new Error('entry/feature lookahead');
      this.pending.set(this.i, entry);
    }
    return out;
  }
}

/** One-minute history -> completed 15-minute Wilder RSI, MACD, Bollinger and ATR. */
export class FifteenMinuteIndicators {
  private first = -Infinity;
  private count = 0;
  private aggregate?: MinuteCandle;
  private lastClose = NaN;
  private seen = 0;
  private gain = 0;
  private loss = 0;
  private trueRange = 0;
  private atr = NaN;
  private ema12 = NaN;
  private ema26 = NaN;
  private signal = NaN;
  private seed12 = 0;
  private seed26 = 0;
  private seedSignal = 0;
  private signalN = 0;
  private last20: number[] = [];
  reset(): void {
    this.first = -Infinity; this.count = 0; this.aggregate = undefined; this.lastClose = NaN;
    this.seen = 0; this.gain = this.loss = this.trueRange = 0; this.atr = this.ema12 = this.ema26 = this.signal = NaN;
    this.seed12 = this.seed26 = this.seedSignal = this.signalN = 0; this.last20 = [];
  }
  push(b: MinuteCandle): Omit<AtlasFeatures, 'session' | 'etHour' | 'btcdDailyChange' | 'usdtdDailyChange' | 'knownAt'> | undefined {
    const start = Math.floor(b.ts / (15 * MINUTE)) * (15 * MINUTE);
    if (start !== this.first) {
      this.first = start; this.count = 0;
      this.aggregate = { ...b, ts: start };
    } else if (this.aggregate) {
      this.aggregate.h = Math.max(this.aggregate.h, b.h);
      this.aggregate.l = Math.min(this.aggregate.l, b.l);
      this.aggregate.c = b.c;
      this.aggregate.v += b.v;
    }
    this.count++;
    if (this.count !== 15 || !this.aggregate || b.ts + MINUTE !== start + 15 * MINUTE) return undefined;
    const c = this.aggregate.c;
    const prior = this.lastClose;
    this.seen++;
    if (Number.isFinite(prior)) {
      const d = c - prior;
      const g = Math.max(0, d), l = Math.max(0, -d);
      const tr = Math.max(this.aggregate.h - this.aggregate.l, Math.abs(this.aggregate.h - prior), Math.abs(this.aggregate.l - prior));
      if (this.seen <= 15) { this.gain += g; this.loss += l; this.trueRange += tr; if (this.seen === 15) { this.gain /= 14; this.loss /= 14; this.atr = this.trueRange / 14; } }
      else { this.gain = (13 * this.gain + g) / 14; this.loss = (13 * this.loss + l) / 14; this.atr = (13 * this.atr + tr) / 14; }
    }
    this.lastClose = c;
    if (this.seen <= 12) { this.seed12 += c; if (this.seen === 12) this.ema12 = this.seed12 / 12; }
    else this.ema12 += (2 / 13) * (c - this.ema12);
    if (this.seen <= 26) { this.seed26 += c; if (this.seen === 26) this.ema26 = this.seed26 / 26; }
    else this.ema26 += (2 / 27) * (c - this.ema26);
    let macd = NaN;
    if (Number.isFinite(this.ema12) && Number.isFinite(this.ema26)) {
      const line = this.ema12 - this.ema26;
      this.signalN++;
      if (this.signalN <= 9) { this.seedSignal += line; if (this.signalN === 9) this.signal = this.seedSignal / 9; }
      else this.signal += 0.2 * (line - this.signal);
      if (Number.isFinite(this.signal)) macd = (line - this.signal) / c * 10_000;
    }
    this.last20.push(c);
    if (this.last20.length > 20) this.last20.shift();
    let bb = NaN;
    if (this.last20.length === 20) {
      const mean = this.last20.reduce((s, x) => s + x, 0) / 20;
      const dev = Math.sqrt(this.last20.reduce((s, x) => s + (x - mean) ** 2, 0) / 20);
      bb = dev > 0 ? (c - (mean - 2 * dev)) / (4 * dev) : 0.5;
    }
    const rsi = this.seen >= 15 ? this.loss === 0 ? (this.gain === 0 ? 50 : 100) : 100 - 100 / (1 + this.gain / this.loss) : NaN;
    return { rsi, macdBps: macd, bbPctB: bb, atrBps: this.atr > 0 ? 10_000 * this.atr / c : NaN };
  }
}

export interface AtlasStats { n: number; up: number; ret: number; mfeUp: number; mfeDown: number; upAtr: number; downAtr: number }
type Stats = AtlasStats;
export interface AtlasFitSnapshot { overall: AtlasStats; rsi: Array<[number, AtlasStats]>; groups: Array<[AtlasGroup, Array<[string, AtlasStats]>]> }
const fresh = (): Stats => ({ n: 0, up: 0, ret: 0, mfeUp: 0, mfeDown: 0, upAtr: 0, downAtr: 0 });
const record = (s: Stats, o: Outcome) => { s.n++; s.up += Number(o.up); s.ret += o.returnBps; s.mfeUp += o.maxUpBps; s.mfeDown += o.maxDownBps; s.upAtr += Number(o.upOneAtr); s.downAtr += Number(o.downOneAtr); };
const bin = (rsi: number): number => Math.max(0, Math.min(20, Math.floor(rsi / 5)));
/** Coarse *storage* coordinates; prediction uses Gaussian interpolation across neighbours.
 * These are not trigger thresholds. Sparse contexts shrink to the RSI-only parent. */
const clamp = (x: number, lo: number, hi: number): number => Math.max(lo, Math.min(hi, x));
// A compact kernel reaches zero at its support boundary, so changing the set of
// neighbouring storage cells cannot introduce a prediction discontinuity.
const kernel = (distance: number, radius: number): number => Math.abs(distance) >= radius ? 0
  : Math.exp(-0.5 * distance * distance) * (1 + Math.cos(Math.PI * distance / radius)) / 2;
function coordinates(name: AtlasGroup, f: AtlasFeatures): { keys: number[]; raw: number[]; circular?: boolean; label?: string } | undefined {
  const macd = Number.isFinite(f.macdBps) && f.atrBps > 0 ? clamp(f.macdBps / f.atrBps / 0.1, -10, 10) : undefined;
  const bands = Number.isFinite(f.bbPctB) ? clamp(f.bbPctB / 0.2, -5, 10) : undefined;
  const btcd = Number.isFinite(f.btcdDailyChange) ? clamp(f.btcdDailyChange / 0.002, -10, 10) : undefined;
  const usdtd = Number.isFinite(f.usdtdDailyChange) ? clamp(f.usdtdDailyChange / 0.002, -10, 10) : undefined;
  const coord = (...raw: number[]) => ({ keys: raw.map(Math.round), raw });
  switch (name) {
    case 'macd': return macd === undefined ? undefined : coord(macd);
    case 'bands': return bands === undefined ? undefined : coord(bands);
    case 'session': return f.session ? { keys: [], raw: [], label: f.session } : undefined;
    case 'time': return Number.isFinite(f.etHour) ? { keys: [Math.round(f.etHour) % 24], raw: [f.etHour], circular: true } : undefined;
    case 'dominance': return btcd === undefined || usdtd === undefined ? undefined : coord(btcd, usdtd);
    case 'macd_bands': return macd === undefined || bands === undefined ? undefined : coord(macd, bands);
    case 'macd_session': return macd === undefined || !f.session ? undefined : { ...coord(macd), label: f.session };
  }
}
function keyOf(c: { keys: number[]; label?: string }): string { return `${c.label ?? ''}:${c.keys.join(',')}`; }
export function groupValue(name: AtlasGroup, f: AtlasFeatures): string | undefined {
  const c = coordinates(name, f);
  return c ? keyOf(c) : undefined;
}
function nearContexts(name: AtlasGroup, f: AtlasFeatures): Array<{ key: string; w: number }> {
  const c = coordinates(name, f);
  if (!c) return [];
  let options: Array<{ keys: number[]; w: number }> = [{ keys: [], w: 1 }];
  for (let j = 0; j < c.keys.length; j++) {
    const k = Math.floor(c.raw[j]);
    const next: typeof options = [];
    for (const b of options) for (let off = -1; off <= 2; off++) {
      const index = c.circular ? (k + off + 24) % 24 : k + off;
      // Use the actual floating-point value, not just its storage bin.
      // Cyclic hour 23.9 must approach hour 0 smoothly.
      const raw = c.raw[j];
      let distance = index - raw;
      if (c.circular) distance = ((distance + 36) % 24) - 12;
      next.push({ keys: [...b.keys, index], w: b.w * kernel(distance, 2) });
    }
    options = next;
  }
  return options.map((o) => ({ key: keyOf({ keys: o.keys, label: c.label }), w: o.w }));
}
export interface Prediction { pUp: number; expectedReturnBps: number; meanMaxUpBps: number; meanMaxDownBps: number; pUpOneAtr: number; pDownOneAtr: number; evidence: number }
class ConditionalFit {
  readonly overall = fresh();
  readonly rsi = new Map<number, Stats>();
  readonly pairs = new Map<AtlasGroup, Map<string, Stats>>(ATLAS_GROUPS.map((k) => [k, new Map()]));
  learn(o: Outcome): void {
    const f = o.entry.f;
    if (!Number.isFinite(f.rsi)) return;
    record(this.overall, o);
    const b = bin(f.rsi);
    let st = this.rsi.get(b); if (!st) this.rsi.set(b, (st = fresh())); record(st, o);
    for (const g of ATLAS_GROUPS) {
      const val = groupValue(g, f); if (!val) continue;
      const key = `${b}:${val}`, cells = this.pairs.get(g)!;
      let cell = cells.get(key); if (!cell) cells.set(key, (cell = fresh())); record(cell, o);
    }
  }
  private estimate(f: AtlasFeatures, group?: AtlasGroup): Prediction {
    const prior = this.overall;
    const centre = f.rsi / 5 - 0.5;
    const contexts = group ? nearContexts(group, f) : [];
    const usePair = contexts.length > 0;
    const map = group ? this.pairs.get(group)! : undefined;
    let n = 0, up = 0, ret = 0, hi = 0, lo = 0, atU = 0, atD = 0;
    // Smooth RSI and numeric context axes; time-of-day wraps cyclically.
    for (let k = Math.max(0, Math.ceil(centre - 4)); k <= Math.min(20, Math.floor(centre + 4)); k++) {
      const delta = (k * 5 + 2.5 - f.rsi) / 5;
      const wrsi = kernel(delta, 4);
      const cells = usePair ? contexts.map((c) => ({ s: map!.get(`${k}:${c.key}`), w: wrsi * c.w })) : [{ s: this.rsi.get(k), w: wrsi }];
      for (const { s, w } of cells) {
        if (!s) continue;
        n += w * s.n; up += w * s.up; ret += w * s.ret;
        hi += w * s.mfeUp; lo += w * s.mfeDown; atU += w * s.upAtr; atD += w * s.downAtr;
      }
    }
    // A pair must have evidence beyond its parent. Low-count estimates shrink to RSI alone.
    const p = usePair ? this.estimate(f) : undefined;
    const shrink = usePair ? 60 : 100;
    const pr = p ?? (prior.n ? { pUp: prior.up / prior.n, expectedReturnBps: prior.ret / prior.n, meanMaxUpBps: prior.mfeUp / prior.n, meanMaxDownBps: prior.mfeDown / prior.n, pUpOneAtr: prior.upAtr / prior.n, pDownOneAtr: prior.downAtr / prior.n, evidence: prior.n } : { pUp: 0.5, expectedReturnBps: 0, meanMaxUpBps: 0, meanMaxDownBps: 0, pUpOneAtr: 0, pDownOneAtr: 0, evidence: 0 });
    const blend = (x: number, y: number) => (x + shrink * y) / (n + shrink);
    return { pUp: blend(up, pr.pUp), expectedReturnBps: blend(ret, pr.expectedReturnBps),
      meanMaxUpBps: blend(hi, pr.meanMaxUpBps), meanMaxDownBps: blend(lo, pr.meanMaxDownBps),
      pUpOneAtr: blend(atU, pr.pUpOneAtr), pDownOneAtr: blend(atD, pr.pDownOneAtr), evidence: n };
  }
  predict(f: AtlasFeatures, group?: AtlasGroup): Prediction { return this.estimate(f, group); }
  snapshot(): AtlasFitSnapshot { return { overall: { ...this.overall }, rsi: [...this.rsi].map(([k, v]) => [k, { ...v }]),
    groups: [...this.pairs].map(([g, cells]) => [g, [...cells].map(([k, v]) => [k, { ...v }])]) }; }
  static fromSnapshot(s: AtlasFitSnapshot): ConditionalFit {
    const fit = new ConditionalFit();
    Object.assign(fit.overall, s.overall);
    for (const [k, v] of s.rsi) fit.rsi.set(k, { ...v });
    for (const [g, cells] of s.groups) {
      if (!fit.pairs.has(g)) throw new Error(`unknown atlas group: ${g}`);
      for (const [k, v] of cells) fit.pairs.get(g)!.set(k, { ...v });
    }
    return fit;
  }
  unconditionalUp(): number { return this.overall.n ? this.overall.up / this.overall.n : 0.5; }
  count(): number { return this.overall.n; }
}
interface WeeklyGain { n: number; sum: number }
class Score {
  count = 0; brier = 0;
  weeks = new Map<number, WeeklyGain>();
  accept(ts: number, actual: boolean, base: number, challenger: number): void {
    this.count++;
    const b0 = (Number(actual) - base) ** 2, b1 = (Number(actual) - challenger) ** 2;
    this.brier += b1;
    const week = Math.floor(ts / (7 * 86_400_000));
    const w = this.weeks.get(week) ?? { n: 0, sum: 0 }; w.n++; w.sum += b0 - b1; this.weeks.set(week, w);
  }
  verdict(): { n: number; weeks: number; brier: number | null; improvement: number | null; conservativeLower: number | null } {
    const ws = [...this.weeks.values()].map((w) => w.sum / w.n);
    const m = ws.reduce((s, x) => s + x, 0) / Math.max(1, ws.length);
    const variance = ws.reduce((s, x) => s + (x - m) ** 2, 0) / Math.max(1, ws.length - 1);
    // Heuristic week-block bound only; not a multiple-testing guarantee across groups/horizons.
    const lower = ws.length >= 2 ? m - 2.8 * Math.sqrt(variance / ws.length) : null;
    return { n: this.count, weeks: ws.length, brier: this.count ? this.brier / this.count : null,
      improvement: ws.length ? m : null, conservativeLower: lower };
  }
}
export interface AtlasConfig { trainBefore: number; finalFrom: number; minDevRows?: number; minDevWeeks?: number }
export interface AtlasReport { schema: string; asset: string; trainingEndsBefore: string; finalStarts: string; gaps: number; data?: { source: string; firstMinute: string | null; lastMinute: string | null; oneMinuteBars: number; candidates: number; malformedRows: number;
  provenance?: { provider: 'tvdatafeed'; spot: { sha256: string; receipt: string }; daily: Record<string, { sha256: string; receipt: string } | null> } }; horizons: Array<{
  horizonMin: number; train: number; retained: boolean; fit: AtlasFitSnapshot; dev: Record<string, unknown>; chosenGroup: AtlasGroup | null; final: Record<string, unknown>;
}> }
export class ConditionalOpportunityAtlas {
  private readonly fits = new Map<HorizonMin, ConditionalFit>(HORIZONS_MIN.map((h) => [h, new ConditionalFit()]));
  private readonly dev = new Map<HorizonMin, Map<AtlasGroup, Score>>(HORIZONS_MIN.map((h) => [h, new Map(ATLAS_GROUPS.map((g) => [g, new Score()]))]));
  private readonly final = new Map<HorizonMin, Map<AtlasGroup, Score>>(HORIZONS_MIN.map((h) => [h, new Map(ATLAS_GROUPS.map((g) => [g, new Score()]))]));
  private readonly devVsGlobal = new Map<HorizonMin, Map<AtlasGroup, Score>>(HORIZONS_MIN.map((h) => [h, new Map(ATLAS_GROUPS.map((g) => [g, new Score()]))]));
  private readonly finalVsGlobal = new Map<HorizonMin, Map<AtlasGroup, Score>>(HORIZONS_MIN.map((h) => [h, new Map(ATLAS_GROUPS.map((g) => [g, new Score()]))]));
  private readonly baselineDev = new Map<HorizonMin, Score>(HORIZONS_MIN.map((h) => [h, new Score()]));
  private readonly baselineFinal = new Map<HorizonMin, Score>(HORIZONS_MIN.map((h) => [h, new Score()]));
  constructor(readonly asset: string, readonly config: AtlasConfig) {
    if (!(config.trainBefore < config.finalFrom)) throw new Error('trainBefore must precede finalFrom');
  }
  accept(o: Outcome): void {
    if (o.entry.asset !== this.asset || !Number.isFinite(o.entry.f.rsi)) return;
    const { trainBefore, finalFrom } = this.config;
    const t = o.entry.ts;
    // All bars needed for a training label must have closed before the split.
    if (o.resolvedAt <= trainBefore && t < trainBefore) { this.fits.get(o.horizonMin)!.learn(o); return; }
    if (t < trainBefore || t < finalFrom && o.resolvedAt > finalFrom) return; // purge split-crossing samples
    const fit = this.fits.get(o.horizonMin)!;
    const p0 = fit.predict(o.entry.f).pUp;
    const uncond = fit.unconditionalUp();
    const base = t < finalFrom ? this.baselineDev.get(o.horizonMin)! : this.baselineFinal.get(o.horizonMin)!;
    base.accept(t, o.up, uncond, p0);
    const scores = t < finalFrom ? this.dev.get(o.horizonMin)! : this.final.get(o.horizonMin)!;
    const globalScores = t < finalFrom ? this.devVsGlobal.get(o.horizonMin)! : this.finalVsGlobal.get(o.horizonMin)!;
    for (const g of ATLAS_GROUPS) {
      const pred = fit.predict(o.entry.f, g).pUp;
      scores.get(g)!.accept(t, o.up, p0, pred);
      globalScores.get(g)!.accept(t, o.up, uncond, pred);
    }
  }
  predict(h: HorizonMin, features: AtlasFeatures, group?: AtlasGroup): Prediction { return this.fits.get(h)!.predict(features, group); }
  report(gaps = 0): AtlasReport {
    const horizons = HORIZONS_MIN.map((h) => {
      const validations = Object.fromEntries([...this.dev.get(h)!].map(([g, s]) => [g, s.verdict()]));
      const vsGlobal = Object.fromEntries([...this.devVsGlobal.get(h)!].map(([g, s]) => [g, s.verdict()]));
      const rsi = this.baselineDev.get(h)!.verdict();
      const rsiUseful = rsi.n >= (this.config.minDevRows ?? 500) && rsi.weeks >= (this.config.minDevWeeks ?? 12) && (rsi.conservativeLower ?? -Infinity) > 0;
      const good = ATLAS_GROUPS.filter((g) => {
        const v = validations[g];
        return v.n >= (this.config.minDevRows ?? 500) && v.weeks >= (this.config.minDevWeeks ?? 12) && (v.conservativeLower ?? -Infinity) > 0 && (vsGlobal[g].conservativeLower ?? -Infinity) > 0;
      });
      good.sort((a, b) => (validations[b].improvement ?? 0) - (validations[a].improvement ?? 0));
      const group = good[0] ?? null;
      return { horizonMin: h, train: this.fits.get(h)!.count(), retained: Boolean(group || rsiUseful),
        fit: this.fits.get(h)!.snapshot(), dev: { baseline: rsi, rsiRetained: rsiUseful, candidates: validations, candidatesVsGlobal: vsGlobal, retained: Boolean(group || rsiUseful) }, chosenGroup: group,
        final: { baseline: this.baselineFinal.get(h)!.verdict(), chosen: group ? this.final.get(h)!.get(group)!.verdict() : null,
          chosenVsGlobal: group ? this.finalVsGlobal.get(h)!.get(group)!.verdict() : null,
          // The final period must never be used to pick a group.
          interpretation: 'Diagnostic only; no automatic model promotion or order eligibility.' } };
    });
    return { schema: ATLAS_SCHEMA, asset: this.asset, trainingEndsBefore: new Date(this.config.trainBefore).toISOString(),
      finalStarts: new Date(this.config.finalFrom).toISOString(), gaps, horizons };
  }
}

/** Explicit offline consumer: returns null for unvalidated/unsupported relationships.
 * This is a historical predictive research object, NOT permission to place an order. */
export function predictStoredAtlas(report: AtlasReport, h: HorizonMin, features: AtlasFeatures): Prediction | null {
  if (report.schema !== ATLAS_SCHEMA) throw new Error('unsupported conditional atlas schema');
  const row = report.horizons.find((x) => x.horizonMin === h);
  if (!row?.retained || !Number.isFinite(features.rsi) || features.rsi < 0 || features.rsi > 100) return null;
  if (row.chosenGroup && !coordinates(row.chosenGroup, features)) return null;
  return ConditionalFit.fromSnapshot(row.fit).predict(features, row.chosenGroup ?? undefined);
}
