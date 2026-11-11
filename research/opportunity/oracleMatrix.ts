/** Descriptive future answers and continuous, empirical pair response surfaces.
 * Oracle labels never enter feature construction. No execution or settlement model. */
import { FifteenMinuteIndicators, type AtlasFeatures, type MinuteCandle, type OpportunityEntry, type Outcome } from './atlas';
import { zoneTime } from '../../bot/model/sessions';
import { digest } from './contractDataset';

export const ORACLE_SCHEMA = 'opportunity-oracle-blocks-v1';
export const ORACLE_PERIODS = [1, 5, 15, 60, 240, 1440] as const;
export const ORACLE_HORIZONS = [15, 60] as const;
export const ORACLE_KNOTS = 17;
export const ORACLE_EMBARGO_MS = 3600000;
export interface OracleAxis { name: string; transform: 'rsi' | 'atan' | 'log-atan' | 'day' | 'week'; scale: number }
export const ORACLE_AXES: OracleAxis[] = [
  ...ORACLE_PERIODS.flatMap((p): OracleAxis[] => [
    { name: `m${p}:rsi`, transform: 'rsi', scale: 100 },
    { name: `m${p}:macd_hist_atr`, transform: 'atan', scale: 1 },
    { name: `m${p}:bb_position`, transform: 'atan', scale: 1 },
    { name: `m${p}:atr_bps`, transform: 'log-atan', scale: 2 },
  ]),
  { name: 'btcd:daily_log_change', transform: 'atan', scale: 0.01 },
  { name: 'usdtd:daily_log_change', transform: 'atan', scale: 0.01 },
  { name: 'clock:ny_hour', transform: 'day', scale: 24 },
  { name: 'clock:ny_weekday', transform: 'week', scale: 7 },
];
export const ORACLE_STATS = ['weight', 'up', 'sideways', 'return_bps', 'return_bps_squared', 'max_up_bps', 'max_down_bps'] as const;
const S = ORACLE_STATS.length, K = ORACLE_KNOTS;
export interface OracleSurface { name: string; a: number; b: number | null; offset: number; cells: number }
let layoutSize = S;
export const ORACLE_SURFACES: OracleSurface[] = [];
for (let a = 0; a < ORACLE_AXES.length; a++) for (let b = a; b < ORACLE_AXES.length; b++) {
  const single = a === b, cells = single ? K : K * K;
  ORACLE_SURFACES.push({ name: ORACLE_AXES[a].name + (single ? '' : ` x ${ORACLE_AXES[b].name}`), a, b: single ? null : b, cells, offset: layoutSize });
  layoutSize += cells * S;
}
export const ORACLE_HORIZON_SIZE = layoutSize;
export const ORACLE_LAYOUT_ID = digest([ORACLE_AXES, ORACLE_SURFACES, ORACLE_STATS, ORACLE_HORIZONS, K]);
ORACLE_AXES.forEach(Object.freeze); Object.freeze(ORACLE_AXES);
ORACLE_SURFACES.forEach(Object.freeze); Object.freeze(ORACLE_SURFACES);
const MIN = 60000;
const cycle = (a: OracleAxis) => a.transform === 'day' || a.transform === 'week';
export function oracleCoordinate(raw: number, a: OracleAxis) {
  if (!Number.isFinite(raw)) return NaN;
  if (cycle(a)) return ((raw / a.scale) % 1 + 1) % 1;
  return a.transform === 'rsi' ? Math.max(0, Math.min(1, raw / a.scale))
    : 0.5 + Math.atan(a.transform === 'log-atan' ? Math.log(Math.max(Number.MIN_VALUE, raw)) / a.scale : raw / a.scale) / Math.PI;
}
export function oracleRawCoordinate(x: number, a: OracleAxis) {
  if (cycle(a) || a.transform === 'rsi') return x * a.scale;
  const z = Math.tan((x - 0.5) * Math.PI) * a.scale;
  return a.transform === 'log-atan' ? Math.exp(z) : z;
}
export interface OracleCoordinates { lo: Int16Array; hi: Int16Array; fraction: Float64Array }
export function oracleCoordinates(raw: readonly number[]): OracleCoordinates {
  if (raw.length !== ORACLE_AXES.length) throw new Error('Oracle feature vocabulary differs');
  const lo = new Int16Array(raw.length), hi = new Int16Array(raw.length), fraction = new Float64Array(raw.length);
  for (let j = 0; j < raw.length; j++) {
    const x = oracleCoordinate(raw[j], ORACLE_AXES[j]);
    if (!Number.isFinite(x)) { lo[j] = hi[j] = -1; continue; }
    const z = x * (K - 1); lo[j] = Math.min(K - 1, Math.floor(z));
    hi[j] = cycle(ORACLE_AXES[j]) ? (lo[j] + 1) % (K - 1) : Math.min(K - 1, lo[j] + 1);
    fraction[j] = z - lo[j];
  }
  return { lo, hi, fraction };
}
/** Quarter names are storage boundaries, never feature reset points. */
export function oracleQuarter(at: number) {
  const d = new Date(at), month = Math.floor(d.getUTCMonth() / 3) * 3, year = d.getUTCFullYear();
  return { id: `${year}-Q${month / 3 + 1}`, from: Date.UTC(year, month, 1), through: Date.UTC(year, month + 3, 1) };
}
export class OracleFeatures {
  private indicators = ORACLE_PERIODS.map((p) => new FifteenMinuteIndicators(p));
  private latest: Array<ReturnType<FifteenMinuteIndicators['push']>> = ORACLE_PERIODS.map(() => undefined);
  lastOpen = -1; gaps = 0;
  push(b: MinuteCandle, dominance: [number, number] = [NaN, NaN]) {
    if (b.ts <= this.lastOpen) throw new Error('unordered Oracle input');
    if (this.lastOpen >= 0 && b.ts !== this.lastOpen + MIN) {
      this.gaps++; this.indicators.forEach((i) => i.reset()); this.latest.fill(undefined);
    }
    this.lastOpen = b.ts;
    const raw: number[] = [];
    for (const [j, i] of this.indicators.entries()) {
      const update = i.push(b); if (update) this.latest[j] = update;
      const v = this.latest[j]; raw.push(v?.rsi ?? NaN, v ? v.macdBps / v.atrBps : NaN, v ? v.bbPctB - 0.5 : NaN, v?.atrBps ?? NaN);
    }
    const at = b.ts + MIN, ny = zoneTime(at, 'America/New_York');
    raw.push(...dominance, ny.minutes / 60, ny.weekday + ny.minutes / 1440);
    const v = this.latest[2];
    return { raw, coordinates: oracleCoordinates(raw), atrBps: v?.atrBps ?? NaN, at };
  }
  checkpoint() { return { lastOpen: this.lastOpen, gaps: this.gaps, indicators: this.indicators, latest: this.latest }; }
}
export interface OracleAnswer {
  at: number; knownAt: number; horizon: 15 | 60; neutralBps: number;
  category: 0 | 1 | 2; returnBps: number; maxUpBps: number; maxDownBps: number;
}
export function oracleAnswer(o: Outcome): OracleAnswer {
  if (!(ORACLE_HORIZONS as readonly number[]).includes(o.horizonMin) || !(o.entry.f.atrBps > 0)) throw new Error('invalid Oracle answer');
  const neutralBps = Math.max(1, 0.25 * o.entry.f.atrBps * Math.sqrt(o.horizonMin / 15));
  return { at: o.entry.ts, knownAt: o.resolvedAt, horizon: o.horizonMin as 15 | 60, neutralBps,
    category: o.returnBps > neutralBps ? 0 : o.returnBps < -neutralBps ? 2 : 1,
    returnBps: o.returnBps, maxUpBps: o.maxUpBps, maxDownBps: o.maxDownBps };
}
export interface OracleEntry extends OpportunityEntry { coordinates: OracleCoordinates; raw: number[]; predictions?: Record<number, OraclePrediction> }
export interface OraclePrediction { p: number[]; baseline: number[]; trainedThrough: number; trainingRows: number }
export function oracleEntry(asset: string, b: MinuteCandle, f: ReturnType<OracleFeatures['push']>): OracleEntry | undefined {
  if (!(f.atrBps > 0)) return;
  return { asset, ts: f.at, price: b.c, raw: f.raw, coordinates: f.coordinates,
    f: { atrBps: f.atrBps, knownAt: f.at } as AtlasFeatures };
}
function addCell(data: Float64Array, off: number, w: number, y: OracleAnswer) {
  data[off] += w; data[off + 1] += w * Number(y.category === 0); data[off + 2] += w * Number(y.category === 1);
  data[off + 3] += w * y.returnBps; data[off + 4] += w * y.returnBps ** 2;
  data[off + 5] += w * y.maxUpBps; data[off + 6] += w * y.maxDownBps;
}
/** All registered single axes and all pair interactions are retained as descriptive
 * answers. Soft storage/interpolation is continuous; missing axes earn no cells. */
export class OracleMatrix {
  readonly data: Float64Array;
  trainedThrough = 0;
  constructor(data?: Float64Array) {
    if (data && (data.length !== ORACLE_HORIZON_SIZE * 2 || data.some((x) => !Number.isFinite(x)))) throw new Error('invalid Oracle matrix');
    this.data = data ?? new Float64Array(ORACLE_HORIZON_SIZE * 2);
  }
  add(y: OracleAnswer, c: OracleCoordinates, weight = 1) {
    const h = ORACLE_HORIZONS.indexOf(y.horizon), base = h * ORACLE_HORIZON_SIZE;
    if (h < 0 || ![0, 1, 2].includes(y.category) || ![y.returnBps, y.maxUpBps, y.maxDownBps, weight].every(Number.isFinite) || y.at + y.horizon * MIN !== y.knownAt) throw new Error('invalid resolved Oracle outcome');
    addCell(this.data, base, weight, y); this.trainedThrough = Math.max(this.trainedThrough, y.knownAt);
    const { lo, hi, fraction: t } = c;
    for (const s of ORACLE_SURFACES) {
      const a = s.a, b = s.b; if (lo[a] < 0 || (b !== null && lo[b] < 0)) continue;
      const off = base + s.offset;
      if (b === null) { addCell(this.data, off + lo[a] * S, weight * (1 - t[a]), y); addCell(this.data, off + hi[a] * S, weight * t[a], y); }
      else {
        addCell(this.data, off + (lo[a] * K + lo[b]) * S, weight * (1 - t[a]) * (1 - t[b]), y);
        addCell(this.data, off + (lo[a] * K + hi[b]) * S, weight * (1 - t[a]) * t[b], y);
        addCell(this.data, off + (hi[a] * K + lo[b]) * S, weight * t[a] * (1 - t[b]), y);
        addCell(this.data, off + (hi[a] * K + hi[b]) * S, weight * t[a] * t[b], y);
      }
    }
  }
  merge(other: OracleMatrix) { for (let i = 0; i < this.data.length; i++) this.data[i] += other.data[i]; this.trainedThrough = Math.max(this.trainedThrough, other.trainedThrough); }
  rows(h: 15 | 60) { return this.data[ORACLE_HORIZONS.indexOf(h) * ORACLE_HORIZON_SIZE]; }
  predict(h: 15 | 60, c: OracleCoordinates, asOf: number, priorStrength = 100): OraclePrediction {
    if (!(ORACLE_HORIZONS as readonly number[]).includes(h) || !Number.isSafeInteger(asOf) || this.trainedThrough + ORACLE_EMBARGO_MS > asOf || !(priorStrength > 0)) throw new Error('Oracle future labels cannot be used for a prediction');
    const base = ORACLE_HORIZONS.indexOf(h) * ORACLE_HORIZON_SIZE, d = this.data, n = d[base];
    const baseline = [(d[base + 1] + 0.5) / (n + 1.5), (d[base + 2] + 0.5) / (n + 1.5), (n - d[base + 1] - d[base + 2] + 0.5) / (n + 1.5)];
    const p = [...baseline], { lo, hi, fraction: t } = c;
    for (const s of ORACLE_SURFACES) {
      const a = s.a, b = s.b; if (lo[a] < 0 || (b !== null && lo[b] < 0)) continue;
      const off = base + s.offset; let mass = 0, up = 0, flat = 0;
      const read = (cell: number, w: number) => { const i = off + cell * S; mass += w * d[i]; up += w * d[i + 1]; flat += w * d[i + 2]; };
      if (b === null) { read(lo[a], 1 - t[a]); read(hi[a], t[a]); }
      else { read(lo[a] * K + lo[b], (1 - t[a]) * (1 - t[b])); read(lo[a] * K + hi[b], (1 - t[a]) * t[b]); read(hi[a] * K + lo[b], t[a] * (1 - t[b])); read(hi[a] * K + hi[b], t[a] * t[b]); }
      p[0] += (up + priorStrength * baseline[0]) / (mass + priorStrength);
      p[1] += (flat + priorStrength * baseline[1]) / (mass + priorStrength);
      p[2] += (Math.max(0, mass - up - flat) + priorStrength * baseline[2]) / (mass + priorStrength);
    }
    const total = p.reduce((a, b) => a + b, 0);
    return { p: p.map((x) => x / total), baseline, trainedThrough: this.trainedThrough, trainingRows: n };
  }
}
