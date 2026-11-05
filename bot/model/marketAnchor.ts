// Market anchor (the owner, Nov 2: "we need this solved"): the bot's price starts from the market's own price and
// moves away from it only as far as the bot's disagreement has been right before.
//
// Why: over the last 500 settled windows the meta-model's price lost to Kalshi's calibrated mid (Diebold-Mariano
// p ~1e-4) and the accuracy gate closed every hourly bucket. Every price stage (math fair value, meta-model, SNN, TA
// tilt) is anchored on the math fair value, a worse forecaster than the mid, so each stage's errors carry straight
// into the entry edge, and the entries that look best are the ones the market already priced (adverse selection).
//
// The anchored price, per time-to-close bucket b (the accuracy gate's buckets):
//     logit p = logit p_mkt + w_b (logit p_bot - logit p_mkt)
// w_b = 0 is the market itself, 1 the bot's raw price. w_b is the bot's disagreement's track record: an offset
// logistic regression of the settled results on that disagreement, over the bucket's last settled markets, with a
// normal prior (MARKET_ANCHOR_PRIOR, sd MARKET_ANCHOR_PRIOR_SD) so a thin record stays near it. Fitted on settled
// markets only (every label comes after its prediction), the same in paper, live and the backtester.
// MARKET_ANCHOR_W fixes w for every bucket (lab arms); MARKET_ANCHOR_SHUFFLE (lab placebo) fits on results
// paired with another market's disagreement, which carries no information.

import fs from 'fs';
import zlib from 'zlib';
import { accuracyBucket, accuracyGroup, ACCURACY_BUCKETS, type AccuracyGroup } from '../strategy/accuracyGate';
import { clamp, logit, sigmoid } from '../util/num';
import { readJson, writeJsonAtomic } from '../util/persist';

export interface MarketAnchorConfig {
  /** Books wider than this (YES dollars) are ignored by the anchor: no learning, raw price (MARKET_ANCHOR_MAX_SPREAD; 0 = off). */
  maxSpread?: number;
  enabled: boolean;
  /** Fixed weight for every bucket (lab); undefined = learned. */
  fixedW?: number;
  /** Prior mean and sd of w. */
  prior: number;
  priorSd: number;
  /** Settled markets kept per bucket. */
  window: number;
  /** Largest w allowed (more than 1 = the bot's disagreement scaled up). */
  maxW: number;
  /** Lab placebo: fit on disagreements paired with another market's result. */
  shuffle?: boolean;
  /** Also learn w per series (KXDOGE, KXBTCD, KXBTC15M, ...) inside each bucket, its prior the bucket's own w
   *  (the owner's dynamics rule, Nov 2: a price that works only in some conditions is gated to them). */
  bySeries?: boolean;
  /** A learned w below this counts as 0 (the market's price, no trade on the disagreement): a bucket or series whose
   *  record barely earns any weight stays out instead of trading on a sliver (refinement, Nov 4). */
  minW?: number;
  /** Anchor on the raw mid instead of the calibrated mid: at w = 0 the price is exactly the mid, so the market
   *  calibration's own tilt opens no trades (MARKET_ANCHOR_RAW_MID). */
  rawMid?: boolean;
  /** Separate weights for disagreements that pull the price toward 0.5 (fading the market's favourite) and away from
   *  it (MARKET_ANCHOR_SPLIT, Nov 5: on the fixed base every anchor loss sat in NO longshots, the largest
   *  fade-the-favourite calls); each direction's prior is the bucket's own weight. */
  split?: boolean;
  /** Wild regime (MARKET_ANCHOR_WILD_RATIO, 0 = off; Nov 5: on the Oct 29 crash the raw price made +$466 and the mid
   *  lagged, while the anchor had learned w ~0 from the calm days before): when the coin's pricing volatility runs this
   *  many times its slow average (MARKET_ANCHOR_WILD_HALF_LIFE_H), the weight is wildW (MARKET_ANCHOR_WILD_W, 1 = the
   *  bot's own price). */
  wildRatio?: number;
  wildW?: number;
  wildHalfLifeH?: number;
  /** Lab placebo (MARKET_ANCHOR_WILD_PLACEBO): wild in random coin-hours with this probability instead of by volatility. */
  wildPlacebo?: number;
  /** Research: regime v1 labels (regime.py's labels.csv[.gz]); when set, the wild regime is the HIGH RV tercile at that
   *  minute instead of the vol ratio (pre-registered Nov 5). A minute without a label (NA) is not wild. */
  wildLabels?: string;
}

/** What the anchor reads of the coin at an evaluation: its pricing volatility (any unit, the same each time). */
export interface AnchorContext { asset: string; sigma: number }

export const DEFAULT_MARKET_ANCHOR: MarketAnchorConfig = { enabled: false, prior: 0.5, priorSd: 0.5, window: 400, maxW: 1.5 };

interface Snap { a: number; d: number; tau: number }
interface Row { a: number; d: number; y: 0 | 1 }
export interface MarketAnchorState { rows: Record<string, Row[]>; /** Slow pricing-vol averages (wild regime), kept across restarts. */ vol?: Record<string, { v: number; first: number; last: number }> }

const PENDING_MAX_AGE_MS = 3 * 3_600_000;
const SAVE_EVERY_MS = 60_000;
const seriesOf = (ticker: string) => ticker.split('-')[0];
const L = (p: number) => logit(clamp(p, 1e-4, 1 - 1e-4));

/** The direction suffix of a disagreement: ':t' toward 0.5 (logit a and d of opposite signs), ':a' away. */
const dirOf = (a: number, d: number) => (a * d < 0 ? ':t' : ':a');

/** MAP fit of w: maximise sum log-lik(y | sigmoid(a + w d)) - (w - prior)^2 / (2 sd^2), Newton steps, clipped. */
export function fitAnchorWeight(rows: ReadonlyArray<Row>, prior: number, priorSd: number, maxW: number): number {
  let w = prior;
  const lam = 1 / (priorSd * priorSd);
  for (let it = 0; it < 30; it++) {
    let g = -lam * (w - prior), h = -lam;
    for (const r of rows) {
      const p = sigmoid(r.a + w * r.d);
      g += (r.y - p) * r.d;
      h -= p * (1 - p) * r.d * r.d;
    }
    const step = g / h;
    w = clamp(w - step, 0, maxW);
    if (Math.abs(step) < 1e-6) break;
  }
  return w;
}

export class MarketAnchor {
  private readonly pending = new Map<string, { group: AccuracyGroup; snaps: Array<Snap | undefined>; lastTs: number }>();
  private readonly weights = new Map<string, number>();
  private st: MarketAnchorState;
  private lastSave = 0;
  private lastPrune = 0;
  private dirty = false;
  private shuffleSeed = 1;
  /** Slow average of each coin's pricing volatility (wild regime), with when it started and was last fed. */
  private readonly slowVol = new Map<string, { v: number; first: number; last: number }>();
  readonly wild = { evals: 0, wild: 0 };
  /** Log loss sums of the anchored, raw and market prices at the scored snapshots (status, replay report). */
  readonly score = { n: 0, anchored: 0, raw: 0, market: 0 };

  constructor(readonly cfg: MarketAnchorConfig, private readonly file?: string, private readonly now: () => number = Date.now) {
    this.st = (file && readJson<MarketAnchorState>(file, { quarantine: true })) || { rows: {} };
    if (!this.st.rows || typeof this.st.rows !== 'object') this.st.rows = {};
    // A restart keeps each coin's slow vol average, so the wild regime is not blind for its first 6 h (bot audit, Nov 5).
    for (const [k, e] of Object.entries(this.st.vol ?? {})) if (e && e.v > 0 && Number.isFinite(e.first) && Number.isFinite(e.last)) this.slowVol.set(k, { ...e });
  }

  private key(ticker: string, tauSec: number): { group: AccuracyGroup; b: number } {
    const group = accuracyGroup(ticker);
    const bs = ACCURACY_BUCKETS[group];
    // Outside the buckets: the nearest one (before the first: the first; in the last 90 s: the last).
    const b = accuracyBucket(group, tauSec) ?? (tauSec > bs[0][1] ? 0 : bs.length - 1);
    return { group, b };
  }

  /** The bucket's weight on the bot's disagreement with the market (dir: ':t' / ':a' when split, from the price). */
  weight(ticker: string, tauSec: number, dir = ''): number {
    if (this.cfg.fixedW !== undefined) return this.cfg.fixedW;
    const { group, b } = this.key(ticker, tauSec);
    const sfx = this.cfg.split ? dir : '';
    let wb = this.wOf(`${group}:${b}`, this.cfg.prior);
    if (sfx) wb = this.wOf(`${group}:${b}${sfx}`, wb);
    const w = this.cfg.bySeries ? this.wOf(`${group}:${seriesOf(ticker)}:${b}${sfx}`, wb) : wb;
    return this.cfg.minW !== undefined && w < this.cfg.minW ? 0 : w;
  }

  private wOf(k: string, prior: number): number {
    let w = this.weights.get(k);
    if (w === undefined) {
      w = fitAnchorWeight(this.st.rows[k] ?? [], prior, this.cfg.priorSd, this.cfg.maxW);
      this.weights.set(k, w);
    }
    return w;
  }

  /** Feed the coin's pricing volatility into its slow average (once a minute at most). */
  private feedVol(ctx: AnchorContext): void {
    if (!(ctx.sigma > 0) || !Number.isFinite(ctx.sigma)) return;
    const t = this.now(), e = this.slowVol.get(ctx.asset);
    if (!e) { this.slowVol.set(ctx.asset, { v: ctx.sigma, first: t, last: t }); return; }
    if (t - e.last < 60_000) return;
    const hl = (this.cfg.wildHalfLifeH ?? 48) * 3_600_000;
    e.v += (1 - Math.pow(0.5, (t - e.last) / hl)) * (ctx.sigma - e.v);
    e.last = t;
    if ((this.cfg.wildRatio ?? 0) > 0) { this.dirty = true; this.save(); }
  }

  /** True when the coin's volatility runs wildRatio times its slow average (after 6 h of history). */
  isWild(ctx?: AnchorContext): boolean {
    const r = this.cfg.wildRatio ?? 0;
    const labels = this.cfg.wildLabels;
    if (!(r > 0) && !labels || !ctx) return false;
    const pl = this.cfg.wildPlacebo ?? 0;
    if (pl > 0) {
      let h = 2166136261;
      for (const ch of `${ctx.asset}:${Math.floor(this.now() / 3_600_000)}`) h = Math.imul(h ^ ch.charCodeAt(0), 16777619);
      return ((h >>> 0) % 10_000) / 10_000 < pl;
    }
    if (labels) return regimeHigh(labels, ctx.asset, this.now());
    const e = this.slowVol.get(ctx.asset);
    return !!e && this.now() - e.first >= 6 * 3_600_000 && e.v > 0 && ctx.sigma >= r * e.v;
  }

  /** The anchored price (the raw price when the anchor is off). */
  price(ticker: string, tauSec: number, pMarket: number, pBot: number, ctx?: AnchorContext): number {
    if (!this.cfg.enabled) return pBot;
    const a = L(pMarket), d = L(pBot) - a;
    let w = this.weight(ticker, tauSec, dirOf(a, d));
    if ((this.cfg.wildRatio ?? 0) > 0) {
      this.wild.evals++;
      if (this.isWild(ctx)) { this.wild.wild++; w = this.cfg.wildW ?? 1; }
    }
    return clamp(sigmoid(a + w * d), 0.001, 0.999);
  }

  /** One evaluation: kept when it is the nearest yet to the middle of its bucket (as the accuracy gate keeps them). */
  observe(ticker: string, tauSec: number, pMarket: number, pBot: number, ctx?: AnchorContext): void {
    if (ctx && (this.cfg.wildRatio ?? 0) > 0) this.feedVol(ctx);
    if (!(pMarket >= 0.03 && pMarket <= 0.97) || !(pBot > 0.001 && pBot < 0.999)) return;
    const group = accuracyGroup(ticker);
    const b = accuracyBucket(group, tauSec);
    if (b === undefined) return;
    const t = this.now();
    let e = this.pending.get(ticker);
    if (!e) { e = { group, snaps: [], lastTs: t }; this.pending.set(ticker, e); }
    e.lastTs = t;
    const [lo, hi] = ACCURACY_BUCKETS[group][b];
    const c = (lo + hi) / 2;
    const cur = e.snaps[b];
    const a = L(pMarket);
    if (!cur || Math.abs(tauSec - c) < Math.abs(cur.tau - c)) e.snaps[b] = { a, d: L(pBot) - a, tau: tauSec };
  }

  settle(ticker: string, result: 'yes' | 'no'): void {
    const e = this.pending.get(ticker);
    if (e) {
      this.pending.delete(ticker);
      const y: 0 | 1 = result === 'yes' ? 1 : 0;
      e.snaps.forEach((s, b) => {
        if (!s) return;
        const k = `${e.group}:${b}`;
        const rows = (this.st.rows[k] ??= []);
        // Scored before the record learns from it (prequential), with the weight the price used.
        const sfx = this.cfg.split ? dirOf(s.a, s.d) : '';
        const w = this.weight(ticker, (ACCURACY_BUCKETS[e.group][b][0] + ACCURACY_BUCKETS[e.group][b][1]) / 2, sfx);
        const ll = (z: number) => { const p = clamp(sigmoid(z), 1e-4, 1 - 1e-4); return y ? -Math.log(p) : -Math.log(1 - p); };
        this.score.n++; this.score.anchored += ll(s.a + w * s.d); this.score.raw += ll(s.a + s.d); this.score.market += ll(s.a);
        let d = s.d;
        if (this.cfg.shuffle && rows.length) { this.shuffleSeed = (this.shuffleSeed * 16807) % 2147483647; const j = this.shuffleSeed % rows.length; d = rows[j].d; rows[j].d = s.d; }
        rows.push({ a: s.a, d, y });
        if (rows.length > this.cfg.window) rows.splice(0, rows.length - this.cfg.window);
        this.weights.delete(k);
        if (sfx) {
          const kd = `${e.group}:${b}${sfx}`;
          const dr = (this.st.rows[kd] ??= []);
          dr.push({ a: s.a, d, y });
          if (dr.length > this.cfg.window) dr.splice(0, dr.length - this.cfg.window);
        }
        if (this.cfg.bySeries) {
          const ks = `${e.group}:${seriesOf(ticker)}:${b}${sfx}`;
          const sr = (this.st.rows[ks] ??= []);
          sr.push({ a: s.a, d, y });
          if (sr.length > this.cfg.window) sr.splice(0, sr.length - this.cfg.window);
        }
        // Every series weight of the bucket leans on the bucket's: refit them all.
        for (const key of [...this.weights.keys()]) if (key.startsWith(`${e.group}:`) && /:(\d+)(:[ta])?$/.exec(key)?.[1] === String(b)) this.weights.delete(key);
      });
      this.dirty = true;
    }
    this.prune();
    this.save();
  }

  private prune(): void {
    const t = this.now();
    if (t - this.lastPrune < 600_000) return;
    this.lastPrune = t;
    for (const [k, e] of this.pending) if (t - e.lastTs > PENDING_MAX_AGE_MS) this.pending.delete(k);
  }

  private save(): void {
    if (!this.file || !this.dirty || this.now() - this.lastSave < SAVE_EVERY_MS) return;
    this.flush();
  }

  flush(): void {
    if (!this.file || !this.dirty) return;
    if (this.slowVol.size) this.st.vol = Object.fromEntries(this.slowVol);
    writeJsonAtomic(this.file, this.st);
    this.lastSave = this.now();
    this.dirty = false;
  }

  status() {
    const fit = (k: string, prior: number) => (this.cfg.fixedW !== undefined ? this.cfg.fixedW : this.wOf(k, prior));
    const groups = Object.fromEntries((Object.keys(ACCURACY_BUCKETS) as AccuracyGroup[]).map((g) => [g, ACCURACY_BUCKETS[g].map(([lo, hi], b) => {
      const k = `${g}:${b}`, w = fit(k, this.cfg.prior);
      const dir = this.cfg.split ? { toward: +fit(`${k}:t`, w).toFixed(3), nToward: (this.st.rows[`${k}:t`] ?? []).length, away: +fit(`${k}:a`, w).toFixed(3), nAway: (this.st.rows[`${k}:a`] ?? []).length } : {};
      return { lo, hi, n: (this.st.rows[k] ?? []).length, w: +w.toFixed(3), ...dir };
    })]));
    // Series keys: group:SERIES:bucket[:t|:a] (a series name is never all digits).
    const series = this.cfg.bySeries ? Object.fromEntries(Object.keys(this.st.rows).map((k) => [k, /^([^:]+):([^:]*[A-Za-z][^:]*):(\d+)(:[ta])?$/.exec(k)] as const).filter(([, m]) => m).map(([k, m]) => {
      const [, g, se, b, sfx] = m!;
      const wb = fit(`${g}:${b}`, this.cfg.prior);
      return [k, { n: this.st.rows[k].length, w: +fit(k, sfx ? fit(`${g}:${b}${sfx}`, wb) : wb).toFixed(3), series: se }];
    })) : undefined;
    const s = this.score;
    const m = (x: number) => (s.n ? +(x / s.n).toFixed(5) : null);
    const wild = (this.cfg.wildRatio ?? 0) > 0 || this.cfg.wildLabels ? { wildRatio: this.cfg.wildLabels ? 'regime-v1 HIGH' : this.cfg.wildRatio, wildShare: this.wild.evals ? +(this.wild.wild / this.wild.evals).toFixed(4) : null } : {};
    return { ...wild, enabled: this.cfg.enabled, fixedW: this.cfg.fixedW ?? null, prior: this.cfg.prior, scored: s.n, llAnchored: m(s.anchored), llRaw: m(s.raw), llMarket: m(s.market), groups, series };
  }
}

/** HIGH-tercile minutes per asset from a regime v1 labels file (ts_iso,asset,rv60,q33,q67,tercile,...), loaded once. */
const regimeFiles = new Map<string, Map<string, Set<number>>>();
export function regimeHigh(file: string, asset: string, nowMs: number): boolean {
  let m = regimeFiles.get(file);
  if (!m) {
    m = new Map();
    const buf = fs.readFileSync(file);
    const text = (file.endsWith('.gz') ? zlib.gunzipSync(buf) : buf).toString('utf8');
    for (const line of text.split('\n')) {
      const f = line.split(',');
      if (f[5] !== 'HIGH') continue;
      const t = Date.parse(f[0]);
      if (!Number.isFinite(t)) continue;
      const a = f[1].toUpperCase();
      let set = m.get(a); if (!set) m.set(a, (set = new Set()));
      set.add(t);
    }
    regimeFiles.set(file, m);
  }
  return m.get(asset.toUpperCase())?.has(Math.floor(nowMs / 60_000) * 60_000) ?? false;
}
