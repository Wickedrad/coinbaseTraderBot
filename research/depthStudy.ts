// How Kalshi's order book behaves on the recorded days, as the inputs of a depth simulator for the history replay
// (Steven, Oct 29: simulate the full depth the recordings show in the history, which keeps only one quote a minute).
//
// The recordings hold every book snapshot, every change at every price level and every trade. For each contract this
// rebuilds the book and measures, against the two things the history also knows (minutes to close, and where the
// minute's quote stands: its mid), what the history lacks:
//   - the shape: the spread, the size at each level behind the best price, the levels quoted within 10 cents, and walls
//     (the biggest level, how big against the median level, and how far from the best price);
//   - the flow, as a queue-reactive model calibrates it (Huang, Lehalle and Rosenbaum 2015): at each distance from the
//     best price and each queue size, how often orders are added, cancelled and traded, per second spent in that state;
//   - the trades: how many a minute, their sizes, and how often they take the bid or the ask;
//   - the same trades split by where the mid goes over the next quarter-minute (down, flat, up): the flow that moves
//     the price is the flow that fills a resting order just before the price moves against it (adverse selection).
//   - per ASSET (BTC, ETH, SOL, XRP), and inside each asset per causal STRESS bucket (Nov 22, schema 2 of the model file): the same
//     shape cells and flow tables, keyed by asset, and by how much the contract has been moving over its last three completed
//     minutes (research/history/depthSim.ts minuteStress: the mean absolute change of its minute mid, cut at the asset's own
//     terciles); the pooled tables stay exactly as they were, `byAsset` is added next to them. The same definition of stress
//     runs in the simulator on a twin day's quotes, so a book is conditioned on what the history knows at its time and nothing later.
//   - the share of 15 s instants at which a book had an empty side or was crossed or locked (`gapShare`, after the contract was first
//     quoted), and over WHOLE lives (open to close, the judge's slots) the mean share of a life that was not quoted at all, with the
//     slots before the first quote (`lives`, per asset and pooled): what the judge's quotedShare feature sees. The simulator draws the
//     empty side only for what the twin's own unquoted lead (its first candle ends a minute after the open) does not already cover.
//
// What the simulator reads of this (research/history/depthSim.ts `play`): from a shape row only levelQuoted, levelFilledP50 and P90,
// tradesPerMin.mean, tradeSize p50 and p90, takerYesShare, topChangesPerMin.mean and gapShare, and the asset block's stress edges and
// `lives`. The flow rows (pooled, per asset and per stress), `informed`, `byMove` (behind USE_NEXT_MOVE, off) and `fit` are written and
// backed off, but not played.
// Read-only; prints aggregates and writes the tables to --out for the simulator to be fitted from.
//
//   node --import tsx research/depthStudy.ts --recordings data/recordings [--days 2026-10-25,2026-10-26] [--out depth_study.json]

import fs from 'fs';
import path from 'path';
import { OrderBook } from '../bot/marketdata/orderBook';
import { recordingFiles, recordingLines } from '../bot/marketdata/recordingFiles';

/** Markets the replays leave out (REPLAY_EXCLUDE, DOGE by default) are not studied either. */
const EXCLUDE = (() => { const v = process.env.REPLAY_EXCLUDE ?? 'DOGE'; return v ? new RegExp(v) : undefined; })();
import { assetOfTicker, DEPTH_ASSETS, minuteMidCents, minuteStress, moveOf, PX, STRESS_GRID, stressBin, ticksFrom, MIN_FLOW_SECONDS, MIN_SHAPE_SAMPLES, type LifeStats } from './history/depthSim';
import { DEPTH_MODEL_SCHEMA } from './history/depthModelVersion';

const MIN = 60_000;
const SAMPLE_MS = 15_000;
const LEVELS = 10;

/** Minutes to close and mid (cents) buckets: what the history knows about a contract at each minute. */
export const TAU_EDGES = [1, 3, 6, 10, 15, 60, Infinity];
export const MID_EDGES = [10, 25, 40, 60, 75, 90, 101];
/** Queue sizes (contracts) for the queue-reactive intensities. */
export const Q_EDGES = [1, 10, 50, 200, 1000, Infinity];
/** The bucket of x: the first edge above it (the last bucket past every edge). A plain loop: it runs for every event of a recorded day. */
const bucket = (edges: number[], x: number) => { for (let i = 0; i < edges.length; i++) if (x < edges[i]) return i; return edges.length - 1; };
const label = (edges: number[], i: number, unit = '') => `${i === 0 ? 0 : edges[i - 1]}-${edges[i] === Infinity ? '' : edges[i]}${unit}`;

/** A running sample of values, summarised as quantiles. The sorted copy is kept until the next add (a summary asks for three quantiles,
 *  and a Float64Array sorts numerically ~10x faster than an array with a comparator: the fit step's report sorts every cell several times). */
class Dist {
  xs: number[] = [];
  private sorted?: Float64Array;
  add(x: number) { if (Number.isFinite(x)) { this.xs.push(x); this.sorted = undefined; } }
  /** Every value of `o` (a cell merged into a coarser one). A loop: a spread of millions of values overflows the stack. */
  addAll(o: Dist) { const n = o.xs.length; for (let i = 0; i < n; i++) this.xs.push(o.xs[i]); if (n) this.sorted = undefined; }
  q(p: number): number { if (!this.xs.length) return NaN; const s = (this.sorted ??= Float64Array.from(this.xs).sort()); return s[Math.min(s.length - 1, Math.floor(p * s.length))]; }
  mean(): number { return this.xs.length ? this.xs.reduce((a, b) => a + b, 0) / this.xs.length : NaN; }
  summary() { return { n: this.xs.length, mean: +this.mean().toFixed(3), p10: this.q(0.1), p50: this.q(0.5), p90: this.q(0.9) }; }
}

interface Cell {
  samples: number; spread: Dist; quotedLevels: Dist; depth10: Dist; wallSize: Dist; wallRatio: Dist; wallOffset: Dist;
  levelSize: Dist[]; levelFilled: Dist[]; tradesPerMin: Dist; tradeSize: Dist; takerYes: number; trades: number; deltasPerMin: Dist;
  /** How often a minute the best bid's or ask's PRICE changes (Nov 2 twin: real 324 a minute, the fill-in 55). */
  topChangesPerMin: Dist;
  /** Per quarter-minute, by where the mid went over it (0 down, 1 flat, 2 up): how many, their trades and YES takers. */
  byMove: Array<{ segs: number; trades: number; yes: number }>;
  /** The 15 s instants (after the contract was first quoted) at which a side of the book was empty (`oneSided`, keyed by the mid the
   *  contract was last quoted at), and those with a crossed or locked book (`crossed`, among `samples`): the judge's quotedShare. */
  oneSided: number; crossed: number;
}
const newCell = (): Cell => ({ samples: 0, spread: new Dist(), quotedLevels: new Dist(), depth10: new Dist(), wallSize: new Dist(), wallRatio: new Dist(), wallOffset: new Dist(),
  levelSize: Array.from({ length: LEVELS }, () => new Dist()), levelFilled: Array.from({ length: LEVELS }, () => new Dist()), tradesPerMin: new Dist(), tradeSize: new Dist(), takerYes: 0, trades: 0, deltasPerMin: new Dist(), topChangesPerMin: new Dist(),
  byMove: [0, 1, 2].map(() => ({ segs: 0, trades: 0, yes: 0 })), oneSided: 0, crossed: 0 });
/** `src` added into `dst` (the finest cells are accumulated once and merged into the coarser tables at the end: one update per event). */
function mergeCell(dst: Cell, src: Cell): void {
  dst.samples += src.samples; dst.takerYes += src.takerYes; dst.trades += src.trades; dst.oneSided += src.oneSided; dst.crossed += src.crossed;
  for (const k of ['spread', 'quotedLevels', 'depth10', 'wallSize', 'wallRatio', 'wallOffset', 'tradesPerMin', 'tradeSize', 'deltasPerMin', 'topChangesPerMin'] as const) dst[k].addAll(src[k]);
  for (let i = 0; i < LEVELS; i++) { dst.levelSize[i].addAll(src.levelSize[i]); dst.levelFilled[i].addAll(src.levelFilled[i]); }
  for (let k = 0; k < 3; k++) { dst.byMove[k].segs += src.byMove[k].segs; dst.byMove[k].trades += src.byMove[k].trades; dst.byMove[k].yes += src.byMove[k].yes; }
}

/** Queue-reactive counts: per (distance from best in ticks, queue size bucket), events and seconds spent there. */
interface Qr { seconds: number; add: number; cancel: number; trade: number; addSize: Dist; cancelSize: Dist }
const newQr = (): Qr => ({ seconds: 0, add: 0, cancel: 0, trade: 0, addSize: new Dist(), cancelSize: new Dist() });
function mergeQr(dst: Qr, src: Qr): void { dst.seconds += src.seconds; dst.add += src.add; dst.cancel += src.cancel; dst.trade += src.trade; dst.addSize.addAll(src.addSize); dst.cancelSize.addAll(src.cancelSize); }

// The tables are accumulated at their finest key, by small integers (no string per event), and merged into the coarser ones at the end:
// asset (the four assets of DEPTH_ASSETS, then one more for any other, which only the pooled tables see) x the stress grid bin of
// research/history/depthSim.ts STRESS_GRID (and one more for "no stress yet") x the study's own cell. The asset's stress buckets are
// cut at that asset's terciles once every sample is in, so the study makes one pass over a recorded day, as before.
const NA = DEPTH_ASSETS.length, NF = STRESS_GRID.length + 1, NOS = NF, NS = NF + 1;
const NT = TAU_EDGES.length, NM = MID_EDGES.length, NO = LEVELS + 1, NQ = Q_EDGES.length;
/** The keys of the finest tables: (asset, stress bin, minutes-to-close bucket, mid bucket) and (asset, stress bin, offset, queue bucket). */
const cellIx = (a: number, f: number, ti: number, mi: number) => ((a * NS + f) * NT + ti) * NM + mi;
const qrIx = (a: number, f: number, off: number, qi: number) => ((a * NS + f) * NO + off) * NQ + qi;
/** Fewest samples an asset needs before its stress terciles are cut (under it: no stress rows, only the asset's own). */
const MIN_STRESS_SAMPLES = 90;

interface Contract { ticker: string; close: number; book: OrderBook; lastSample: number; minute: number; deltas: number; trades: number; seen: Set<string>; tops?: number; lastTop?: string;
  /** The quarter-minute since the last sample: where the mid stood and its cell, and its trades so far. */
  seg?: { mid: number; cell: Cell }; segTrades: number; segYes: number;
  /** Trades waiting for the mid a minute later (informed flow): time, YES taker, the mid at the trade. */
  waiting?: Array<{ t: number; yes: boolean; mid: number }>;
  /** The asset (an index into DEPTH_ASSETS; NA: another one) and the contract's open time (ms; for the first-quote diagnostic). */
  asset: number; open?: number;
  /** The minute mids (cents, by minute number: the quote at the minute stamp) the stress reads, the minute the cached stress bin is for,
   *  that bin, whether the contract has been quoted (two-sided and uncrossed) at a sample yet, and the mid it was last quoted at. */
  mm: Map<number, number>; sMin: number; sFine: number; quoted: boolean; lastMid?: number;
  /** The contract's life, in the judge's slots (every 15 s from its open to its close): the slots counted, those not quoted (no book yet,
   *  an empty side, crossed or locked), and the slots before the first quote. */
  lifeSlots: number; lifeUnq: number; lead: number }
/** Trades alike to one already seen in the same second (time, price, size and side; the recordings keep no trade id). Kept:
 *  trades are stamped in whole seconds, so on a busy book most are separate trades, not the recorder counting one twice. */
export const tradeCount = { all: 0, repeated: 0 };
/** Informed flow (Nov 2): of the trades after which the mid had moved a minute later, how many took the side the price
 *  went (a YES taker before a rise, a NO taker before a fall). Half is blind flow; the depth fill-in plays the excess. */
export const informed = { n: 0, agree: 0 };
const INFORMED_MS = 60_000;

type Side = 'bid' | 'ask';
/** The book's levels on one side, best first, as [price in tenths of a cent, size]. */
function sideLevels(b: OrderBook, side: Side): Array<[number, number]> {
  const s = b.snapshot(100);
  return (side === 'bid' ? s.bids : s.asks).map((l) => [Math.round(l.price * PX), l.size]);
}

/** Which contracts a study measures: every up/down and 15-minute contract ('all'), or only the 15-minute ones ('15m': the
 *  deep history builds only those, and the hourly books are deeper and busier; Nov 3 twin: a model fitted on all of them
 *  gave the 15-minute fill-in tops ~25x the real ones and ~3x their trades). */
export type StudySeries = 'all' | '15m';
const is15m = (series: string | undefined, ticker: string) => /15M/.test(series ?? '') || /15M-/.test(ticker);

export function depthStudy(files: string[], series: StudySeries = 'all'): Promise<ReturnType<typeof report>> {
  return run(files, series);
}

/** What the report needs besides the cells: per asset the stress histogram (samples by grid bin), medians' samples and the first-quote delays. */
interface Extras { stressHist: number[][]; trades: Dist[]; depth10: Dist[]; firstQuote: Dist[];
  /** Per asset: the lives counted, the sum of their unquoted shares and of their leads (slots before the first quote). */
  lives: Array<{ n: number; unq: number; lead: number }> }
/** Fewest lives an asset needs before its `lives` stats are written (under it the asset has none and the pooled ones stand in). */
const MIN_LIVES = 10;
/** The judge's own floor: a life with fewer quoted slots than this is not a row (research/historyTwin.ts rowBuilder). */
const MIN_QUOTED_SLOTS = 20;

async function run(files: string[], series: StudySeries = 'all') {
  tradeCount.all = 0; tradeCount.repeated = 0; informed.n = 0; informed.agree = 0;
  const cells: Array<Cell | undefined> = new Array((NA + 1) * NS * NT * NM);
  const qrs: Array<Qr | undefined> = new Array((NA + 1) * NS * NO * NQ);
  const ex: Extras = { stressHist: Array.from({ length: NA + 1 }, () => new Array(NF).fill(0)), trades: Array.from({ length: NA + 1 }, () => new Dist()), depth10: Array.from({ length: NA + 1 }, () => new Dist()), firstQuote: Array.from({ length: NA + 1 }, () => new Dist()),
    lives: Array.from({ length: NA + 1 }, () => ({ n: 0, unq: 0, lead: 0 })) };
  const cellOf = (a: number, f: number, tau: number, mid: number) => { const k = cellIx(a, f, bucket(TAU_EDGES, tau), bucket(MID_EDGES, mid)); return (cells[k] ??= newCell()); };
  const qrOf = (a: number, f: number, off: number, q: number) => { const k = qrIx(a, f, Math.min(off, LEVELS), bucket(Q_EDGES, q)); return (qrs[k] ??= newQr()); };
  const contracts = new Map<string, Contract>();
  const state = (c: Contract, t: number) => {
    const bb = c.book.bestBid(), ba = c.book.bestAsk();
    if (!bb || !ba) return undefined;
    return { tau: (c.close - t) / MIN, mid: minuteMidCents(Math.round(bb.price * PX), Math.round(ba.price * PX)) };
  };
  /** The contract's stress grid bin at `t` (NOS: none yet): from the minute mids stamped at or before t (research/history/depthSim.ts minuteStress). */
  const stressFine = (c: Contract, t: number): number => {
    const m = Math.floor(t / MIN);
    if (c.sMin !== m) { const v = minuteStress((k) => c.mm.get(k), m); c.sFine = v === undefined ? NOS : stressBin(v); c.sMin = m; }
    return c.sFine;
  };
  const sample = (c: Contract, t: number) => {
    const bb = c.book.bestBid(), ba = c.book.bestAsk();
    const s = state(c, t);
    const bT = bb ? Math.round(bb.price * PX) : 0, aT = ba ? Math.round(ba.price * PX) : 0;
    const valid = !!s && bT >= 1 && aT <= PX - 1 && aT > bT;
    // The life's slots, as the judge counts them: every 15 s from the open to the close, quoted or not. The instants before the contract's
    // first sample (no book yet) are unquoted too; `lead` is the slots before its first quote.
    if (c.open !== undefined && t >= c.open && t <= c.close) {
      if (c.lifeSlots === 0 && t > c.open) { const n = Math.round((t - c.open) / SAMPLE_MS); c.lifeSlots += n; c.lifeUnq += n; c.lead += n; }
      c.lifeSlots++;
      if (!valid) { c.lifeUnq++; if (!c.quoted) c.lead++; }
    }
    // The minute mid at a minute stamp: the quote at that instant (a two-sided, uncrossed book), what the stress will read from now on.
    if (valid && t % MIN === 0) { const m = t / MIN; c.mm.set(m, s!.mid); c.mm.delete(m - 6); c.sMin = -1; }
    const f = stressFine(c, t);
    // The quarter-minute that ends here: its trades, by where the mid went over it.
    if (c.seg && s) { const m = c.seg.cell.byMove[moveOf(c.seg.mid, s.mid)]; m.segs++; m.trades += c.segTrades; m.yes += c.segYes; }
    c.segTrades = 0; c.segYes = 0;
    c.seg = s && s.tau >= 0 ? { mid: s.mid, cell: cellOf(c.asset, f, s.tau, s.mid) } : undefined;
    if (!s) {
      // An empty side at this instant, counted where the contract was last quoted (never before its first quote: that stretch is the
      // requote layer's, the history has no quote yet).
      const tau = (c.close - t) / MIN;
      if (c.lastMid !== undefined && tau >= 0) cellOf(c.asset, f, tau, c.lastMid).oneSided++;
      return;
    }
    if (s.tau < 0) return;
    const cell = c.seg!.cell;
    cell.samples++;
    if (c.asset <= NA && f < NF) ex.stressHist[c.asset][f]++;
    if (valid) {
      c.lastMid = s.mid;
      if (!c.quoted) { c.quoted = true; if (c.open !== undefined) ex.firstQuote[c.asset].add(Math.max(0, Math.round((t - c.open) / SAMPLE_MS))); }
    } else cell.crossed++;
    const bids = sideLevels(c.book, 'bid'), asks = sideLevels(c.book, 'ask');
    cell.spread.add((asks[0][0] - bids[0][0]) / 10);
    for (const lv of [bids, asks]) {
      const best = lv[0][0];
      // Each sample stands for SAMPLE_MS at each distance and queue size: the intensities' denominators.
      const atAll = new Map(lv.map(([p, v]) => [ticksFrom(p, best), v]));
      for (let off = 0; off < LEVELS; off++) qrOf(c.asset, f, off, atAll.get(off) ?? 0).seconds += SAMPLE_MS / 1000;
      const near = lv.filter(([p]) => ticksFrom(p, best) < LEVELS);
      cell.quotedLevels.add(near.length);
      const d10 = near.reduce((a, [, v]) => a + v, 0);
      cell.depth10.add(d10); ex.depth10[c.asset].add(d10);
      const at = new Map(near.map(([p, v]) => [ticksFrom(p, best), v]));
      for (let off = 0; off < LEVELS; off++) { const v = at.get(off) ?? 0; cell.levelSize[off].add(v); if (v > 0) cell.levelFilled[off].add(v); }
      const sizes = near.map(([, v]) => v).sort((a, b) => a - b);
      const med = sizes[Math.floor(sizes.length / 2)] || 1;
      const wall = near.reduce((m, x) => (x[1] > m[1] ? x : m), near[0]);
      cell.wallSize.add(wall[1]); cell.wallRatio.add(wall[1] / med); cell.wallOffset.add(ticksFrom(wall[0], best));
    }
  };
  /** A contract's life is over: its unquoted share and lead join its asset's (a life the judge would not make a row of, with fewer than
   *  MIN_QUOTED_SLOTS quoted slots or none counted, is left out). */
  const endLife = (c: Contract) => {
    if (c.lifeSlots === 0 || c.lifeSlots - c.lifeUnq < MIN_QUOTED_SLOTS) return;
    const l = ex.lives[c.asset];
    l.n++; l.unq += c.lifeUnq / c.lifeSlots; l.lead += c.lead;
  };
  const touchTop = (c: Contract) => { const b = c.book.bestBid(), a = c.book.bestAsk(); const k = `${b?.price}|${a?.price}`; if (k !== c.lastTop) { c.tops = (c.tops ?? 0) + 1; c.lastTop = k; } };
  const minuteEnd = (c: Contract, t: number) => {
    const s = state(c, t);
    if (s && s.tau >= 0) { const cell = cellOf(c.asset, stressFine(c, t), s.tau, s.mid); cell.tradesPerMin.add(c.trades); cell.deltasPerMin.add(c.deltas); cell.topChangesPerMin.add(c.tops ?? 0); ex.trades[c.asset].add(c.trades); }
    c.trades = 0; c.deltas = 0; c.tops = 0; c.seen.clear();
  };

  for (const file of files) {
    for await (const line of recordingLines(file)) {
      if (!line) continue;
      let e: Record<string, any>;
      try { e = JSON.parse(line); } catch { continue; }
      const t: number = e.t ?? e.ts;
      if (e.k === 'market' && e.ticker && e.closeTime && !EXCLUDE?.test(e.ticker) && (series === '15m' ? is15m(e.series, e.ticker) : e.kind === 'updown' || /15M/.test(e.series ?? ''))) {
        if (!contracts.has(e.ticker)) {
          const a = assetOfTicker(e.ticker), open = Number(e.openTime);
          contracts.set(e.ticker, { ticker: e.ticker, close: Number(e.closeTime), book: new OrderBook(e.ticker), lastSample: 0, minute: 0, deltas: 0, trades: 0, seen: new Set(), segTrades: 0, segYes: 0,
            asset: a === undefined ? NA : DEPTH_ASSETS.indexOf(a as (typeof DEPTH_ASSETS)[number]), open: Number.isFinite(open) && open > 0 ? open : undefined, mm: new Map(), sMin: -1, sFine: NOS, quoted: false, lifeSlots: 0, lifeUnq: 0, lead: 0 });
        }
        continue;
      }
      const c = e.ticker ? contracts.get(e.ticker) : undefined;
      if (!c) continue;
      if (t > c.close) { if (c.minute) minuteEnd(c, c.close - 1); endLife(c); contracts.delete(c.ticker); continue; }
      // The contract's samples and minutes up to this event, on the book as it stood.
      while (c.lastSample && c.lastSample + SAMPLE_MS <= t) { c.lastSample += SAMPLE_MS; sample(c, c.lastSample); }
      // The trades a minute old: did the mid go the taker's way?
      if (c.waiting?.length && c.waiting[0].t + INFORMED_MS <= t) {
        const bb = c.book.bestBid(), ba = c.book.bestAsk();
        while (c.waiting.length && c.waiting[0].t + INFORMED_MS <= t) {
          const w = c.waiting.shift()!;
          if (!bb || !ba || !(ba.price > bb.price)) continue;
          const d = (bb.price + ba.price) / 2 - w.mid;
          if (Math.abs(d) < 0.0049) continue;
          informed.n++; if ((d > 0) === w.yes) informed.agree++;
        }
      }
      const m = Math.floor(t / MIN);
      if (c.minute && m > c.minute) minuteEnd(c, c.minute * MIN + MIN - 1);
      c.minute = m;
      if (e.k === 'book') {
        c.book.applySnapshot({ bids: e.bids ?? [], asks: e.asks ?? [] }, t);
        touchTop(c);
        if (!c.lastSample) c.lastSample = Math.ceil(t / SAMPLE_MS) * SAMPLE_MS - SAMPLE_MS;
      } else if (e.k === 'delta' && (e.side === 'bid' || e.side === 'ask')) {
        const side = e.side as Side;
        const top = side === 'bid' ? c.book.bestBid() : c.book.bestAsk();
        const p = Math.round(Number(e.price) * PX), d = Number(e.delta);
        if (top && Number.isFinite(d) && d !== 0) {
          const best = Math.round(top.price * PX);
          // A level better than the best is a new best (distance 0); the queue is the level's size before the change.
          const off = (side === 'bid' ? p >= best : p <= best) ? 0 : ticksFrom(p, best);
          const before = c.book.sizeAt(side, Number(e.price));
          const cell = qrOf(c.asset, stressFine(c, t), off, before);
          if (d > 0) { cell.add++; cell.addSize.add(d); } else { cell.cancel++; cell.cancelSize.add(-d); }
        }
        c.book.applyDelta(side, Number(e.price), d, t);
        c.deltas++;
        touchTop(c);
      } else if (e.k === 'trade') {
        const id = String(e.trade_id ?? `${e.ts}|${e.price}|${e.count}|${e.takerSide}`);
        tradeCount.all++;
        if (c.seen.has(id)) tradeCount.repeated++;
        c.seen.add(id);
        const s = state(c, t), f = stressFine(c, t);
        if (s) { const cell = cellOf(c.asset, f, s.tau, s.mid); cell.trades++; cell.tradeSize.add(Number(e.count)); if (e.takerSide === 'yes') cell.takerYes++; }
        c.segTrades++; if (e.takerSide === 'yes') c.segYes++;
        { const bb = c.book.bestBid(), ba = c.book.bestAsk(); if (bb && ba && ba.price > bb.price && (e.takerSide === 'yes' || e.takerSide === 'no')) (c.waiting ??= []).push({ t, yes: e.takerSide === 'yes', mid: (bb.price + ba.price) / 2 }); }
        // The trade takes the best level on the side it hits: the queue-reactive model's market orders.
        const side: Side = e.takerSide === 'yes' ? 'ask' : 'bid';
        const best = side === 'ask' ? c.book.bestAsk() : c.book.bestBid();
        if (best) qrOf(c.asset, f, 0, best.size).trade++;
        c.trades++;
      }
    }
  }
  // The last minute of contracts no later event closed (their final minute: no event after the close).
  for (const c of contracts.values()) { if (c.minute) minuteEnd(c, Math.min(c.minute * MIN + MIN - 1, c.close - 1)); endLife(c); }
  return report(cells, qrs, ex);
}

/** The asset's stress terciles from its histogram over the grid bins: the grid value each third of the samples ends at (the smallest grid
 *  value holding at least 1/3 and 2/3 of them), and the grid bin each of those is. Undefined while the asset has too few samples. */
export function stressTerciles(hist: readonly number[]): { edges: [number, number]; bins: [number, number]; n: number } | undefined {
  const n = hist.reduce((a, b) => a + b, 0);
  if (n < MIN_STRESS_SAMPLES) return undefined;
  const at = (share: number) => { let cum = 0; for (let f = 0; f < hist.length; f++) { cum += hist[f]; if (cum >= share * n - 1e-9) return f; } return hist.length - 1; };
  const b1 = at(1 / 3), b2 = at(2 / 3);
  const edge = (f: number) => STRESS_GRID[Math.min(f, STRESS_GRID.length - 1)];
  return { edges: [edge(b1), edge(b2)], bins: [b1, b2], n };
}

/** One shape row of the report (the pooled rows' format; an asset block's rows add `si` for a stress bucket). */
function shapeRow(c: Cell, ti: number, mi: number, si?: number) {
  return {
    ti, mi, ...(si !== undefined ? { si } : {}), tau: label(TAU_EDGES, ti, ' min'), mid: label(MID_EDGES, mi, 'c'), samples: c.samples,
    spread: c.spread.summary(), quotedLevels: c.quotedLevels.summary(), depth10: c.depth10.summary(),
    wallSize: c.wallSize.summary(), wallRatio: c.wallRatio.summary(), wallOffset: c.wallOffset.summary(),
    levelSizeP50: c.levelSize.map((d) => d.q(0.5)), levelSizeMean: c.levelSize.map((d) => +d.mean().toFixed(1)),
    // Where a level is quoted: how often, and its size's median and 90th percentile (the simulator draws from these).
    levelQuoted: c.levelFilled.map((d) => +(d.xs.length / Math.max(1, c.levelSize[0].xs.length)).toFixed(3)),
    levelFilledP50: c.levelFilled.map((d) => d.q(0.5)), levelFilledP90: c.levelFilled.map((d) => d.q(0.9)),
    tradesPerMin: c.tradesPerMin.summary(), deltasPerMin: c.deltasPerMin.summary(), topChangesPerMin: c.topChangesPerMin.summary(), tradeSize: c.tradeSize.summary(),
    takerYesShare: c.trades ? +(c.takerYes / c.trades).toFixed(3) : null,
    // The trade flow by where the mid goes over the quarter-minute (down, flat, up): its rate and its YES takers.
    byMove: c.byMove.map((m) => ({ segs: m.segs, tradesPerSec: m.segs ? +(m.trades / (m.segs * (SAMPLE_MS / 1000))).toFixed(4) : 0, takerYesShare: m.trades ? +(m.yes / m.trades).toFixed(3) : null })),
    // The 15 s instants with an empty side or a crossed book, among every instant the contract had been quoted at (an old model has none).
    gapShare: +((c.oneSided + c.crossed) / Math.max(1, c.samples + c.oneSided)).toFixed(4),
  };
}
/** One flow row (the pooled rows' format; `si` for a stress bucket of an asset block). */
function flowRow(q: Qr, off: number, qi: number, si?: number) {
  const per = (n: number) => +(n / q.seconds).toFixed(5);
  return { offset: off, qi, ...(si !== undefined ? { si } : {}), queue: label(Q_EDGES, qi), seconds: Math.round(q.seconds), addPerSec: per(q.add), cancelPerSec: per(q.cancel), tradePerSec: per(q.trade),
    addSize: q.addSize.summary(), cancelSize: q.cancelSize.summary() };
}
const byKey = (x: { ti: number; mi: number; si?: number }, y: { ti: number; mi: number; si?: number }) => x.ti - y.ti || x.mi - y.mi || (x.si ?? -1) - (y.si ?? -1);
const flowOrder = (a: { offset: number; qi: number; queue: string; si?: number }, b: { offset: number; qi: number; queue: string; si?: number }) => a.offset - b.offset || a.queue.localeCompare(b.queue) || (a.si ?? -1) - (b.si ?? -1);

function report(cells: Array<Cell | undefined>, qrs: Array<Qr | undefined>, ex: Extras) {
  const merged = <T extends Cell | Qr>(fresh: () => T, merge: (d: T, s: T) => void, parts: Array<T | undefined>): T | undefined => {
    const live = parts.filter((p): p is T => !!p);
    if (!live.length) return undefined;
    const out = fresh();
    for (const p of live) merge(out, p);
    return out;
  };
  const cellMerged = (as: number[], fs: number[], ti: number, mi: number) => merged(newCell, mergeCell, as.flatMap((a) => fs.map((f) => cells[cellIx(a, f, ti, mi)])));
  const qrMerged = (as: number[], fs: number[], off: number, qi: number) => merged(newQr, mergeQr, as.flatMap((a) => fs.map((f) => qrs[qrIx(a, f, off, qi)])));
  const allF = Array.from({ length: NS }, (_, f) => f);
  const allA = Array.from({ length: NA + 1 }, (_, a) => a);

  // The pooled tables: every asset, every stress (the report of before the asset dimension, in the same format).
  const shape: Array<ReturnType<typeof shapeRow>> = [];
  const flow: Array<ReturnType<typeof flowRow>> = [];
  for (let ti = 0; ti < NT; ti++) for (let mi = 0; mi < NM; mi++) { const c = cellMerged(allA, allF, ti, mi); if (c && c.samples >= MIN_SHAPE_SAMPLES) shape.push(shapeRow(c, ti, mi)); }
  for (let off = 0; off < NO; off++) for (let qi = 0; qi < NQ; qi++) { const q = qrMerged(allA, allF, off, qi); if (q && q.seconds > MIN_FLOW_SECONDS) flow.push(flowRow(q, off, qi)); }
  flow.sort(flowOrder);

  // Per asset: its own rows over all stress, and its rows by stress bucket (terciles of its own samples).
  const byAsset: Record<string, { shape: Array<ReturnType<typeof shapeRow>>; flow: Array<ReturnType<typeof flowRow>>; stress?: { edges: [number, number]; n: number }; lives?: LifeStats; fit: Record<string, number | null> }> = {};
  /** The real unquoted share of a life and the slots before the first quote, over the lives of these assets (none under MIN_LIVES). */
  const livesOf = (as: number[]): LifeStats | undefined => {
    const n = as.reduce((x, a) => x + ex.lives[a].n, 0);
    if (n < MIN_LIVES) return undefined;
    return { n, unquotedShare: +(as.reduce((x, a) => x + ex.lives[a].unq, 0) / n).toFixed(4), leadSlots: +(as.reduce((x, a) => x + ex.lives[a].lead, 0) / n).toFixed(2) };
  };
  for (let a = 0; a < NA; a++) {
    const tr = stressTerciles(ex.stressHist[a]);
    const buckets = [0, 1, 2].map((b) => allF.filter((f) => f < NF && tr && (b === 0 ? f <= tr.bins[0] : b === 1 ? f > tr.bins[0] && f <= tr.bins[1] : f > tr.bins[1])));
    const aShape: Array<ReturnType<typeof shapeRow>> = [], aFlow: Array<ReturnType<typeof flowRow>> = [];
    let stressRows = 0, stressFlow = 0, ownRows = 0, ownFlow = 0, toPooled = 0, toAsset = 0;
    for (let ti = 0; ti < NT; ti++) for (let mi = 0; mi < NM; mi++) {
      const own = cellMerged([a], allF, ti, mi);
      const pooledHas = shape.some((r) => r.ti === ti && r.mi === mi);
      if (own && own.samples >= MIN_SHAPE_SAMPLES) {
        aShape.push(shapeRow(own, ti, mi)); ownRows++;
        for (let b = 0; b < 3; b++) { const c = tr ? cellMerged([a], buckets[b], ti, mi) : undefined; if (c && c.samples >= MIN_SHAPE_SAMPLES) { aShape.push(shapeRow(c, ti, mi, b)); stressRows++; } else if (tr) toAsset++; }
      } else if (pooledHas) toPooled++;
    }
    for (let off = 0; off < NO; off++) for (let qi = 0; qi < NQ; qi++) {
      const own = qrMerged([a], allF, off, qi);
      if (own && own.seconds > MIN_FLOW_SECONDS) {
        aFlow.push(flowRow(own, off, qi)); ownFlow++;
        if (tr) for (let b = 0; b < 3; b++) { const q = qrMerged([a], buckets[b], off, qi); if (q && q.seconds > MIN_FLOW_SECONDS) { aFlow.push(flowRow(q, off, qi, b)); stressFlow++; } }
      }
    }
    if (!aShape.length) continue;
    aShape.sort(byKey); aFlow.sort(flowOrder);
    const samples = aShape.filter((r) => r.si === undefined).reduce((s, r) => s + r.samples, 0);
    const gaps = aShape.filter((r) => r.si === undefined).reduce((s, r) => s + (r.gapShare ?? 0) * r.samples, 0);
    const lives = livesOf([a]);
    byAsset[DEPTH_ASSETS[a]] = {
      shape: aShape, flow: aFlow, ...(tr ? { stress: { edges: tr.edges, n: tr.n } } : {}), ...(lives ? { lives } : {}),
      // What the fit measured for this asset, for the reader of the model file and the log lines (the simulator ignores it).
      fit: { samples, shapeRows: ownRows, stressRows, flowRows: ownFlow, stressFlowRows: stressFlow, backoffToPooled: toPooled, backoffStressToAsset: toAsset,
        tradesPerMinP50: ex.trades[a].xs.length ? ex.trades[a].q(0.5) : null, depth10P50: ex.depth10[a].xs.length ? ex.depth10[a].q(0.5) : null,
        firstQuoteSlotsP50: ex.firstQuote[a].xs.length ? ex.firstQuote[a].q(0.5) : null, gapShare: samples ? +(gaps / samples).toFixed(4) : null,
        unquotedShare: lives ? lives.unquotedShare : null, leadSlotsMean: lives?.leadSlots ?? null },
    };
  }
  const pooledLives = livesOf(allA);
  return { schema: DEPTH_MODEL_SCHEMA, shape, flow, informed: { n: informed.n, agree: informed.n ? +(informed.agree / informed.n).toFixed(4) : 0.5 }, byAsset, ...(pooledLives ? { lives: pooledLives } : {}) };
}

/** The short lines the fit step logs per asset (counts and numbers only; the workflow prints them as `[twin] depth model:` lines). */
export function assetLines(r: ReturnType<typeof report>): string[] {
  return Object.entries(r.byAsset).map(([a, b]) => {
    const f = b.fit, num = (x: number | null) => (x === null ? 'n/a' : String(Math.round(x * 100) / 100));
    return `[depth] asset ${a}: ${f.samples} samples; rows ${f.shapeRows} + ${f.stressRows} stress (flow ${f.flowRows} + ${f.stressFlowRows}); stress edges ${b.stress ? b.stress.edges.join('/') + 'c' : 'none'}; back off to pooled ${f.backoffToPooled}, stress to asset ${f.backoffStressToAsset}; trades/min p50 ${num(f.tradesPerMinP50)}, depth10 p50 ${num(f.depth10P50)}; first quote ${num(f.firstQuoteSlotsP50)} slots after open; empty-side share ${num(f.gapShare === null ? null : f.gapShare * 100)}%; real unquoted ${num(f.unquotedShare === null ? null : f.unquotedShare * 100)}% of a life`;
  });
}

function cliArg(k: string, d: string): string { const i = process.argv.indexOf(`--${k}`); return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : d; }

async function main() {
  const rec = cliArg('recordings', 'data/recordings');
  const want = cliArg('days', '').split(',').filter(Boolean);
  const today = new Date().toISOString().slice(0, 10);
  const days = recordingFiles(rec).filter((d) => d.day < today && (!want.length || want.includes(d.day)));
  if (!days.length) throw new Error('no whole recorded days');
  const series = cliArg('series', 'all') as StudySeries;
  const r = await run(days.map((d) => d.file), series === '15m' ? '15m' : 'all');
  const out = cliArg('out', '');
  if (out) { fs.mkdirSync(path.dirname(path.resolve(out)), { recursive: true }); fs.writeFileSync(out, JSON.stringify({ days: days.map((d) => d.day), ...r }, null, 1)); }
  console.log(`[depth] ${days.length} day(s): ${days[0].day}..${days[days.length - 1].day}, contracts: ${series === '15m' ? '15-minute only' : 'all up/down'}, schema ${r.schema}`);
  // Per asset (counts and numbers only), first: the build's log filter keeps the first lines of the study's output.
  for (const l of assetLines(r)) console.log(l);
  // All cells together: the trade flow by where the mid went over the quarter-minute.
  const all = [0, 1, 2].map((k) => r.shape.reduce((m, c) => { const x = c.byMove[k]; return { segs: m.segs + x.segs, trades: m.trades + x.tradesPerSec * x.segs * (SAMPLE_MS / 1000), yes: m.yes + (x.takerYesShare ?? 0) * x.tradesPerSec * x.segs * (SAMPLE_MS / 1000) }; }, { segs: 0, trades: 0, yes: 0 }));
  console.log(`[depth] ${all.reduce((a, m) => a + m.segs, 0)} quarter-minutes, by the mid's move over them (down / flat / up): share ${all.map((m) => (m.segs / Math.max(1, all.reduce((a, x) => a + x.segs, 0))).toFixed(2)).join(' / ')}, trades/s ${all.map((m) => (m.trades / Math.max(1, m.segs * (SAMPLE_MS / 1000))).toFixed(2)).join(' / ')}, YES takers ${all.map((m) => (m.yes / Math.max(1, m.trades)).toFixed(2)).join(' / ')}`);
  console.log('[depth] shape by minutes to close and mid (each side; sizes in contracts, spread and offsets in ticks: 1c, or 0.1c below 10c and above 90c)');
  for (const s of r.shape) {
    console.log(`  ${s.tau.padEnd(9)} ${s.mid.padEnd(7)} n=${String(s.samples).padStart(6)}  spread p50 ${s.spread.p50} p90 ${s.spread.p90} | levels in 10 ticks ${s.quotedLevels.p50} | depth10 p50 ${s.depth10.p50} | wall ${s.wallSize.p50} (x${(+s.wallRatio.p50).toFixed(1)} median, ${s.wallOffset.p50} ticks back) | lvl0-4 quoted ${s.levelQuoted.slice(0, 5).join('/')} size p50 ${s.levelFilledP50.slice(0, 5).join('/')} p90 ${s.levelFilledP90.slice(0, 5).join('/')} | trades/min ${s.tradesPerMin.mean} size p50 ${s.tradeSize.p50} | changes/min ${s.deltasPerMin.mean} | top moves/min ${s.topChangesPerMin?.mean}`);
  }
  console.log(`[depth] informed flow: ${r.informed.n} trades after which the mid had moved a minute later, ${(100 * r.informed.agree).toFixed(1)}% took the side it went`);
  console.log(`[depth] trades: ${tradeCount.all} recorded, ${tradeCount.repeated} repeated (${tradeCount.all ? ((100 * tradeCount.repeated) / tradeCount.all).toFixed(1) : 0}%, kept: whole-second stamps, no trade id)`);
  console.log('[depth] queue-reactive flow (per second at each distance from best and queue size)');
  for (const f of r.flow) console.log(`  off ${String(f.offset).padStart(2)}t q ${f.queue.padEnd(9)} ${String(f.seconds).padStart(8)} s  add ${f.addPerSec} (p50 ${f.addSize.p50})  cancel ${f.cancelPerSec} (p50 ${f.cancelSize.p50})  trade ${f.tradePerSec}`);
}

if (process.argv[1] && import.meta.url?.endsWith(path.basename(process.argv[1]))) main().catch((e) => { console.error(e); process.exit(1); });
