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

import { accuracyBucket, accuracyGroup, ACCURACY_BUCKETS, type AccuracyGroup } from '../strategy/accuracyGate';
import { clamp, logit, sigmoid } from '../util/num';
import { readJson, writeJsonAtomic } from '../util/persist';

export interface MarketAnchorConfig {
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
}

export const DEFAULT_MARKET_ANCHOR: MarketAnchorConfig = { enabled: false, prior: 0.5, priorSd: 0.5, window: 400, maxW: 1.5 };

interface Snap { a: number; d: number; tau: number }
interface Row { a: number; d: number; y: 0 | 1 }
export interface MarketAnchorState { rows: Record<string, Row[]> }

const PENDING_MAX_AGE_MS = 3 * 3_600_000;
const SAVE_EVERY_MS = 60_000;
const seriesOf = (ticker: string) => ticker.split('-')[0];
const L = (p: number) => logit(clamp(p, 1e-4, 1 - 1e-4));

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
  /** Log loss sums of the anchored, raw and market prices at the scored snapshots (status, replay report). */
  readonly score = { n: 0, anchored: 0, raw: 0, market: 0 };

  constructor(readonly cfg: MarketAnchorConfig, private readonly file?: string, private readonly now: () => number = Date.now) {
    this.st = (file && readJson<MarketAnchorState>(file, { quarantine: true })) || { rows: {} };
    if (!this.st.rows || typeof this.st.rows !== 'object') this.st.rows = {};
  }

  private key(ticker: string, tauSec: number): { group: AccuracyGroup; b: number } {
    const group = accuracyGroup(ticker);
    const bs = ACCURACY_BUCKETS[group];
    // Outside the buckets: the nearest one (before the first: the first; in the last 90 s: the last).
    const b = accuracyBucket(group, tauSec) ?? (tauSec > bs[0][1] ? 0 : bs.length - 1);
    return { group, b };
  }

  /** The bucket's weight on the bot's disagreement with the market. */
  weight(ticker: string, tauSec: number): number {
    if (this.cfg.fixedW !== undefined) return this.cfg.fixedW;
    const { group, b } = this.key(ticker, tauSec);
    return this.cfg.bySeries ? this.wOf(`${group}:${seriesOf(ticker)}:${b}`, this.wOf(`${group}:${b}`, this.cfg.prior)) : this.wOf(`${group}:${b}`, this.cfg.prior);
  }

  private wOf(k: string, prior: number): number {
    let w = this.weights.get(k);
    if (w === undefined) {
      w = fitAnchorWeight(this.st.rows[k] ?? [], prior, this.cfg.priorSd, this.cfg.maxW);
      this.weights.set(k, w);
    }
    return w;
  }

  /** The anchored price (the raw price when the anchor is off). */
  price(ticker: string, tauSec: number, pMarket: number, pBot: number): number {
    if (!this.cfg.enabled) return pBot;
    const a = L(pMarket);
    return clamp(sigmoid(a + this.weight(ticker, tauSec) * (L(pBot) - a)), 0.001, 0.999);
  }

  /** One evaluation: kept when it is the nearest yet to the middle of its bucket (as the accuracy gate keeps them). */
  observe(ticker: string, tauSec: number, pMarket: number, pBot: number): void {
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
        const w = this.weight(ticker, (ACCURACY_BUCKETS[e.group][b][0] + ACCURACY_BUCKETS[e.group][b][1]) / 2);
        const ll = (z: number) => { const p = clamp(sigmoid(z), 1e-4, 1 - 1e-4); return y ? -Math.log(p) : -Math.log(1 - p); };
        this.score.n++; this.score.anchored += ll(s.a + w * s.d); this.score.raw += ll(s.a + s.d); this.score.market += ll(s.a);
        let d = s.d;
        if (this.cfg.shuffle && rows.length) { this.shuffleSeed = (this.shuffleSeed * 16807) % 2147483647; const j = this.shuffleSeed % rows.length; d = rows[j].d; rows[j].d = s.d; }
        rows.push({ a: s.a, d, y });
        if (rows.length > this.cfg.window) rows.splice(0, rows.length - this.cfg.window);
        this.weights.delete(k);
        if (this.cfg.bySeries) {
          const ks = `${e.group}:${seriesOf(ticker)}:${b}`;
          const sr = (this.st.rows[ks] ??= []);
          sr.push({ a: s.a, d, y });
          if (sr.length > this.cfg.window) sr.splice(0, sr.length - this.cfg.window);
        }
        // Every series weight of the bucket leans on the bucket's: refit them all.
        for (const key of [...this.weights.keys()]) if (key.startsWith(`${e.group}:`) && key.endsWith(`:${b}`)) this.weights.delete(key);
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
    writeJsonAtomic(this.file, this.st);
    this.lastSave = this.now();
    this.dirty = false;
  }

  status() {
    const groups = Object.fromEntries((Object.keys(ACCURACY_BUCKETS) as AccuracyGroup[]).map((g) => [g, ACCURACY_BUCKETS[g].map(([lo, hi], b) => {
      const k = `${g}:${b}`;
      return { lo, hi, n: (this.st.rows[k] ?? []).length, w: +(this.cfg.fixedW ?? this.weights.get(k) ?? fitAnchorWeight(this.st.rows[k] ?? [], this.cfg.prior, this.cfg.priorSd, this.cfg.maxW)).toFixed(3) };
    })]));
    const series = this.cfg.bySeries ? Object.fromEntries(Object.keys(this.st.rows).filter((k) => k.split(':').length === 3).map((k) => {
      const [g, se, b] = k.split(':');
      return [k, { n: this.st.rows[k].length, w: +this.wOf(k, this.wOf(`${g}:${b}`, this.cfg.prior)).toFixed(3), series: se }];
    })) : undefined;
    const s = this.score;
    const m = (x: number) => (s.n ? +(x / s.n).toFixed(5) : null);
    return { enabled: this.cfg.enabled, fixedW: this.cfg.fixedW ?? null, prior: this.cfg.prior, scored: s.n, llAnchored: m(s.anchored), llRaw: m(s.raw), llMarket: m(s.market), groups, series };
  }
}
