/** Offline feature vocabulary. No fitting, rule votes, model loading or order consumers. */
import { TIMEFRAMES, TF_MS, tfState } from '../../bot/ta/analyzer';
import type { Candle } from '../../bot/ta/indicators';
import type { Timeframe } from '../../bot/ta/knowledge';
import { TANET_SCHEMA, TANET_D1_BARS, TANET_H1_BARS, TANET_M15_BARS, TF_OPTS, tfFeatures } from '../../bot/ta/taNet';
import { taEngine } from '../../bot/ta/talib';
import { marketClockFeatures, sessionAt, type SessionKey } from '../../bot/model/sessions';

export const ATLAS_FEATURE_SCHEMA = 'opportunity-features-v1';
const MIN = 60000, DAY = 86400000;
const OPTIONS = Object.fromEntries(TF_OPTS.map(([tf, , opts]) => [tf, opts]));
const optsFor = (tf: Timeframe) => OPTIONS[tf] ?? { sma200: true, vwap: true };
// Intraday VWAP needs the whole current UTC session, even at its last minute.
const windowFor = (tf: Timeframe) => tf === '1m' ? 1440 : tf === '5m' ? 288 : tf === '1d' ? TANET_D1_BARS : tf === '15m' ? TANET_M15_BARS : TANET_H1_BARS;
export const ATLAS_FEATURE_WINDOWS = Object.fromEntries(TIMEFRAMES.map((tf) => [tf, windowFor(tf)]));
export interface FeatureSource { source: string; sha256: string | null }
export interface FeatureGroup extends FeatureSource {
  timeframe: Timeframe | 'clock' | 'micro'; status: 'ready' | 'warming' | 'missing' | 'stale';
  bars: number; firstOpen: number | null; lastOpen: number | null; knownAt: number | null;
  publicationLagMs: number; timing: string;
  values: Readonly<Record<string, number | null>>;
}
export interface AtlasFeatureFrame {
  schema: typeof ATLAS_FEATURE_SCHEMA; taSchema: string; engine: string;
  asset: string; decisionAt: number; session: SessionKey; gapsSeen: number;
  groups: Readonly<Record<string, Readonly<FeatureGroup>>>;
}
function finiteValues(values: Record<string, number>): Readonly<Record<string, number | null>> {
  return Object.freeze(Object.fromEntries(Object.entries(values).map(([k, v]) => [k, Number.isFinite(v) ? v : null])));
}
function valid(c: Candle, interval: number) {
  return [c.ts, c.o, c.h, c.l, c.c, c.v].every(Number.isFinite) && c.ts >= 0 && c.ts % interval === 0 &&
    Math.min(c.o, c.h, c.l, c.c) > 0 && c.h >= Math.max(c.o, c.c) && c.l <= Math.min(c.o, c.c) && c.v >= 0 &&
    (c.tb === undefined || (Number.isFinite(c.tb) && c.tb >= 0 && c.tb <= c.v + 1e-9));
}
function taGroup(tf: Timeframe, bars: Candle[], source: FeatureSource, lag = 0, timing = 'observed candle close; zero additional publication lag assumed'): Readonly<FeatureGroup> {
  const state = tfState(tf, bars), values: Record<string, number> = {};
  tfFeatures('', state, values, optsFor(tf));
  // tfFeatures' shared convention adds an underscore after its prefix.
  const unprefixed = Object.fromEntries(Object.entries(values).map(([k, v]) => [k.slice(1), v]));
  unprefixed.log_return_1bar = bars.length > 1 ? Math.log(bars.at(-1)!.c / bars.at(-2)!.c) : NaN;
  return Object.freeze({ ...source, timeframe: tf, status: state ? 'ready' : bars.length ? 'warming' : 'missing', bars: bars.length,
    firstOpen: bars[0]?.ts ?? null, lastOpen: bars.at(-1)?.ts ?? null,
    knownAt: bars.length ? bars.at(-1)!.ts + TF_MS[tf] + lag : null,
    publicationLagMs: lag, timing, values: finiteValues(unprefixed) });
}

/** Independent daily source; no source splicing, backwards fill or price/volume imputation. */
export class AsOfDailyFeatures {
  private readonly bars: Candle[];
  private cached?: { index: number; group: Readonly<FeatureGroup> };
  constructor(bars: Candle[], readonly source: FeatureSource, readonly lagMs = DAY, readonly maxAgeMs = 2 * DAY,
    readonly volumeObserved = true) {
    if (!Number.isFinite(lagMs) || lagMs < 0 || !Number.isFinite(maxAgeMs) || maxAgeMs < 0 ||
        bars.some((c, i) => !valid(c, DAY) || (i > 0 && c.ts <= bars[i - 1].ts))) throw new Error('invalid daily series or availability policy');
    this.bars = bars.map((c) => ({ ...c }));
  }
  at(decisionAt: number): Readonly<FeatureGroup> {
    if (!Number.isFinite(decisionAt)) throw new Error('invalid decision time');
    let lo = 0, hi = this.bars.length;
    while (lo < hi) {
      const mid = (lo + hi) >>> 1;
      if (this.bars[mid].ts + DAY + this.lagMs <= decisionAt) lo = mid + 1; else hi = mid;
    }
    const index = lo - 1;
    if (this.cached?.index !== index) {
      let start = Math.max(0, index - TANET_D1_BARS + 1);
      for (let j = index; j > start; j--) if (this.bars[j].ts - this.bars[j - 1].ts !== DAY) { start = j; break; }
      const prefix = index < 0 ? [] : this.bars.slice(start, index + 1);
      let group = taGroup('1d', prefix, this.source, this.lagMs, 'daily close plus configured publication lag; historical publication time unverified');
      if (!this.volumeObserved) {
        // CRYPTOCAP volume is a provider placeholder, not an observed trade-flow feature.
        const values = { ...group.values };
        for (const key of Object.keys(values)) if (/obv|cmf|mfi|vol_ratio|vp_|tl_adosc|^h?div$|^breakout$/i.test(key)) values[key] = null;
        group = Object.freeze({ ...group, values: Object.freeze(values) });
      }
      this.cached = { index, group };
    }
    const group = this.cached.group;
    if (group.knownAt !== null && decisionAt - group.knownAt > this.maxAgeMs) {
      return Object.freeze({ ...group, status: 'stale', values: Object.freeze(Object.fromEntries(Object.keys(group.values).map((k) => [k, null]))) });
    }
    return group;
  }
}

interface Bucket { bar: Candle; count: number }
/** Aggregates only complete, consecutive, UTC-aligned minutes; resets on any gap. */
export class CausalAtlasFeatures {
  private readonly closed = new Map<Timeframe, Candle[]>(TIMEFRAMES.map((tf) => [tf, []]));
  private readonly forming = new Map<Timeframe, Bucket>();
  private readonly cached = new Map<Timeframe, Readonly<FeatureGroup>>();
  private last?: Candle;
  private previousClose?: number;
  gaps = 0;
  constructor(readonly asset: string, readonly source: FeatureSource, readonly daily: Record<string, AsOfDailyFeatures> = {}) {}
  push(candle: Candle): void {
    if (!valid(candle, MIN) || (this.last && candle.ts <= this.last.ts)) throw new Error('minute candles must be valid and strictly increasing');
    const gap = this.last && candle.ts !== this.last.ts + MIN;
    if (gap) {
      this.gaps++;
      for (const bars of this.closed.values()) bars.length = 0;
      this.forming.clear(); this.cached.clear();
    }
    this.previousClose = gap ? undefined : this.last?.c;
    const c = { ...candle };
    this.last = c;
    for (const tf of TIMEFRAMES) {
      const interval = TF_MS[tf], start = Math.floor(c.ts / interval) * interval;
      let bucket = this.forming.get(tf);
      if (!bucket || bucket.bar.ts !== start) {
        bucket = c.ts === start ? { bar: { ...c }, count: 1 } : undefined;
        this.forming.delete(tf);
        if (bucket) this.forming.set(tf, bucket);
      } else {
        const b = bucket.bar;
        b.h = Math.max(b.h, c.h); b.l = Math.min(b.l, c.l); b.c = c.c; b.v += c.v;
        b.tb = b.tb === undefined || c.tb === undefined ? undefined : b.tb + c.tb;
        bucket.count++;
      }
      if (bucket && c.ts + MIN === start + interval && bucket.count === interval / MIN) {
        const bars = this.closed.get(tf)!;
        bars.push(bucket.bar); if (bars.length > windowFor(tf)) bars.shift();
        this.cached.delete(tf); this.forming.delete(tf);
      }
    }
  }
  snapshot(): AtlasFeatureFrame {
    if (!this.last) throw new Error('no observed closed minute');
    const c = this.last, decisionAt = c.ts + MIN;
    const groups: Record<string, Readonly<FeatureGroup>> = {};
    for (const tf of TIMEFRAMES) {
      let group = this.cached.get(tf);
      if (!group) { group = taGroup(tf, this.closed.get(tf)!, this.source); this.cached.set(tf, group); }
      groups[`spot_${tf}`] = group;
    }
    for (const [name, series] of Object.entries(this.daily)) groups[name] = series.at(decisionAt);
    groups.micro = Object.freeze({ ...this.source, timeframe: 'micro', status: 'ready', bars: this.previousClose === undefined ? 1 : 2,
      firstOpen: this.previousClose === undefined ? c.ts : c.ts - MIN, lastOpen: c.ts,
      knownAt: decisionAt, publicationLagMs: 0, timing: 'observed minute close; zero additional publication lag assumed',
      values: finiteValues({ log_return_1m: this.previousClose ? Math.log(c.c / this.previousClose) : NaN,
        log_close_open: Math.log(c.c / c.o), range_fraction: (c.h - c.l) / c.c,
        close_location: c.h > c.l ? (c.c - c.l) / (c.h - c.l) : NaN,
        taker_imbalance: c.tb !== undefined && c.v > 0 ? 2 * c.tb / c.v - 1 : NaN, is_btc: this.asset === 'BTC' ? 1 : 0 }) });
    groups.clock = Object.freeze({ source: 'bot/model/sessions.ts; see report code hashes', sha256: null, timeframe: 'clock', status: 'ready',
      bars: 0, firstOpen: null, lastOpen: null, knownAt: decisionAt, publicationLagMs: 0,
      timing: 'deterministic DST-aware calendar at decision time; exchange holidays unmodeled', values: finiteValues(marketClockFeatures(decisionAt)) });
    return Object.freeze({ schema: ATLAS_FEATURE_SCHEMA, taSchema: TANET_SCHEMA, engine: taEngine(), asset: this.asset,
      decisionAt, session: sessionAt(decisionAt), gapsSeen: this.gaps, groups: Object.freeze(groups) });
  }
}
