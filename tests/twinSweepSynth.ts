// Synthetic days and a synthetic depth model for the depth-simulator sweep's tests and its benchmark (no recordings are
// needed, nothing is random: every number comes from a seeded generator). Not a test file itself (the test runner only picks up
// *.test.ts).
import crypto from 'crypto';
import fs from 'fs';
import zlib from 'zlib';
import type { DepthModel, ShapeCell } from '../research/history/depthSim';
import type { Ev } from '../research/goLiveTally';

export const MIN = 60_000;

/** A seeded uniform generator (mulberry32). */
export function seeded(seed: number): () => number {
  let a = seed >>> 0;
  return () => { a = (a + 0x6d2b79f5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}
const gauss = (u: () => number) => Math.sqrt(-2 * Math.log(Math.max(u(), 1e-12))) * Math.cos(2 * Math.PI * u());

export interface SynthDay { day: string; assets?: string[]; windows?: number; startHour?: number; seed?: number; resultFor?: (ticker: string) => 'yes' | 'no' }

/** A requote day as research/kalshiReplayData.ts writes it: per asset an index print every 15 s, per 15-minute contract a market
 *  record, a quote every 15 s from its open to its close (one level, 100 a side, whole cents; some contracts drift into the
 *  tails below 10 and above 90 cents), the minute's trade, and the result. In time order, the index before the quotes. */
export function synthRequoteDay(o: SynthDay): Ev[] {
  const assets = o.assets ?? ['BTC', 'ETH'], windows = o.windows ?? 4, d0 = Date.parse(`${o.day}T00:00:00Z`), first = d0 + (o.startHour ?? 6) * 3_600_000;
  const dd = o.day.slice(8, 10), u = seeded(o.seed ?? 1);
  const out: Ev[] = [];
  const lastClose = first + windows * 15 * MIN;
  for (const a of assets) {
    const base = a === 'BTC' ? 70_000 : a === 'ETH' ? 3_500 : 150, ix = new Map<number, number>();
    let v = base;
    for (let t = first - 2 * MIN; t <= lastClose + 30_000; t += 15_000) { v *= 1 + 0.0004 * gauss(u); ix.set(t, v); out.push({ t, k: 'index', asset: a, value: +v.toFixed(2), ts: t, src: 'kalshi', hist: 1 } as Ev); }
    for (let w = 0; w < windows; w++) {
      const open = first + w * 15 * MIN, close = open + 15 * MIN, hh = String(new Date(open).getUTCHours()).padStart(2, '0'), mm = String(new Date(open).getUTCMinutes()).padStart(2, '0');
      const ticker = `KX${a}15M-26NOV${dd}${hh}${mm}-00`, strike = ix.get(open) ?? base;
      // a drift that takes every third contract into a tail
      const drift = (w % 3 === 2 ? 1 : 0.15) * (u() < 0.5 ? -1 : 1) * 3;
      out.push({ t: open - MIN, k: 'market', ticker, series: `KX${a}15M`, asset: a, openTime: open, closeTime: close, strike, cap: null, kind: 'updown', event: ticker.slice(0, -3), tickSize: 0.01, hist: 1 } as Ev);
      for (let t = open, k = 0; t <= close; t += 15_000, k++) {
        const x = ((ix.get(t) ?? strike) - strike) / strike * 2500 + drift * (k / 60) + 0.15 * gauss(u);
        const mid = 1 / (1 + Math.exp(-x)), bid = Math.min(0.97, Math.max(0.01, Math.floor(mid * 100) / 100)), w2 = u() < 0.25 ? 0.02 : 0.01, ask = Math.min(0.99, +(bid + w2).toFixed(2));
        out.push({ t, k: 'book', ticker, bids: [{ price: bid, size: 100 }], asks: [{ price: ask, size: 100 }], ts: t } as Ev);
        if (t % MIN === 0 && t < close) out.push({ t, k: 'trade', ticker, price: bid, count: 9 + Math.floor(u() * 20), ts: t - 1 } as Ev);
      }
      out.push({ t: close + 1000, k: 'result', ticker, result: o.resultFor ? o.resultFor(ticker) : ((ix.get(close) ?? strike) >= strike ? 'yes' : 'no') } as Ev);
    }
  }
  // time order, the first-made record first at the same time (the index is made before the quotes it moves)
  return out.map((e, i) => [e, i] as const).sort((x, y) => x[0].t - y[0].t || x[1] - y[1]).map((x) => x[0]);
}

export function writeEventsGz(file: string, evs: readonly object[]): void {
  fs.writeFileSync(file, zlib.gzipSync(evs.map((e) => JSON.stringify(e)).join('\n') + '\n'));
}

/** A depth model with every cell the simulator looks up (7 x 7 buckets), as research/depthStudy.ts shapes it. `trades` and
 *  `topChanges`: the measured trades a contract-minute and best-price changes a minute (the rates the benchmark runs at). */
export function synthModel(o: { trades?: number; topChanges?: number; days?: string[] } = {}): DepthModel {
  const trades = o.trades ?? 90, topChanges = o.topChanges ?? 300;
  const quant = (p50: number, p90: number, mean = p50) => ({ n: 200, mean, p10: Math.max(1, Math.round(p50 / 2)), p50, p90 });
  const shape: ShapeCell[] = [];
  for (let ti = 0; ti < 7; ti++) for (let mi = 0; mi < 7; mi++) {
    const k = 1 + 0.25 * mi + 0.1 * ti, tails = mi === 0 || mi === 6;
    const p50 = [60, 80, 100, 130, 150, 170, 190, 210, 230, 250].map((x) => Math.round(x * k * (tails ? 0.5 : 1)));
    shape.push({
      ti, mi, samples: 400,
      levelQuoted: [1, 0.97, 0.92, 0.85, 0.75, 0.65, 0.55, 0.45, 0.35, 0.3],
      levelFilledP50: p50, levelFilledP90: p50.map((x) => x * 7),
      tradesPerMin: quant(Math.round(trades * 0.8), Math.round(trades * 2), trades), tradeSize: quant(4, 30, 9),
      takerYesShare: 0.4 + 0.03 * mi, topChangesPerMin: quant(topChanges, Math.round(topChanges * 1.5), topChanges),
      byMove: [{ segs: 100, tradesPerSec: trades / 60 * 1.2, takerYesShare: 0.3 }, { segs: 100, tradesPerSec: trades / 60 * 0.8, takerYesShare: 0.5 }, { segs: 100, tradesPerSec: trades / 60 * 1.2, takerYesShare: 0.7 }],
    });
  }
  const flow = [];
  for (let offset = 0; offset < 10; offset++) for (let qi = 0; qi < 6; qi++) flow.push({ offset, qi, seconds: 3600, addPerSec: 0.05, cancelPerSec: 0.04, addSize: quant(10, 40), cancelSize: quant(8, 30) });
  return { days: o.days ?? ['2026-11-11', '2026-11-12', '2026-11-15'], shape, flow, informed: { n: 5000, agree: 0.56 } };
}

/** sha256 of an event stream, number by number: a -0 is told from a 0 (JSON would print both as 0). */
export function eventsHash(evs: readonly unknown[]): string {
  const h = crypto.createHash('sha256');
  const rep = (_k: string, v: unknown) => (typeof v === 'number' && Object.is(v, -0) ? '-0' : v);
  for (const e of evs) h.update(JSON.stringify(e, rep) + '\n');
  return h.digest('hex');
}

/** DepthSim.play called quote by quote as research/goLiveTally.ts streamFiller does it (each quote played up to the contract's
 *  next one, the next quote's mid passed along), the emitted records in call order. `Sim` is the class (the current one, or the
 *  base commit's copy for the parity test). */
export function playAnchors(Sim: new (m: DepthModel, p?: never) => { play: (...a: any[]) => Array<Record<string, unknown>>; stats: Record<string, number> }, events: readonly Ev[], model: DepthModel): { out: Array<Record<string, unknown>>; stats: Record<string, number> } {
  const sim = new Sim(model), close = new Map<string, number>(), books = new Map<string, Ev[]>();
  for (const e of events) {
    if (e.k === 'market') close.set(e.ticker!, Number(e.closeTime));
    else if (e.k === 'book') { const l = books.get(e.ticker!) ?? []; l.push(e); books.set(e.ticker!, l); }
  }
  const out: Array<Record<string, unknown>> = [];
  for (const [tk, bs] of books) for (let i = 0; i < bs.length; i++) {
    const e = bs[i], nx = bs[i + 1];
    out.push(...sim.play(tk, e.t, e.bids![0].price, e.asks![0].price, nx ? nx.t : e.t + 15_000, close.get(tk)!, nx ? (nx.bids![0].price + nx.asks![0].price) / 2 : undefined));
  }
  return { out, stats: { ...sim.stats } };
}
