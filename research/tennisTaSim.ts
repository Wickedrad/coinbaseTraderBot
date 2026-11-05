// Tennis TA rulebook trial, family A and the match grids (pre-registration: /mnt/project-files/tennis-ta/preregistration.md).
//
// One pass over a stretch of tennis replay days (Kalshi history built by research/history/historyReplay.ts tennisEvents, or
// the bot's recordings cut to tennis lines by research/tennisTaData.ts) runs MANY configs of the production tennis strategy
// in lock-step: market data (books, tape, results) is shared, each config has its own trackers, orders and positions.
//
// What it mirrors from production (bot/engine.ts tennisTick): decisions every 5 s through decideMatch with
// TennisProfitRules (settleFrac 0.30, here with the loser window cut on: Steven's "never hold to settlement unless in
// profit", which production lacks, audit I117), quotes only from books no older than 5 s, flow over confWindowSec from the
// tape, avgEntry = -netCash/yes, netAtBid and costPer with bot/fees.ts (tennis pays maker and taker fees, each fill rounded
// up to the cent), the per-order / per-match / total tennis caps through tennisSize on a fixed $200 bankroll (no
// compounding: a sterile sweep), resting orders cancelled when no longer planned, GTC orders expiring at min(1 h, close).
// The quota pacer (Amendment 1, A6): each config runs its own HourlyQuotaPacer at the production PACER_* settings, fed by
// its own tennis fills and settlements, plus QuotaFloors (PACER_FLOOR riding, PACER_FLOOR_TICKS 8), and decideMatch gets
// pacerUsd / floorMode / floors / floorTicks as bot/engine.ts:1416-1418 passes them. Production's pacer also sees crypto
// and perps, which a tennis replay cannot reproduce; HARNESS_PACER=off is the sensitivity arm.
// What it does not: the riskScale / optimal-f scaling and equity guard (persisted state), feed-lag and sports halts, the
// curve gate (a no-op under the default SINUOUS_EXIT=cross), the fair model and SNN features (no fairA is passed).
//
// Output per config: realized net per match over EVERY owned match in finish order (0 for a match it did not trade,
// aligned with SweepResult.matchList), the per-day totals, and one Episode per position (entry to flat or settlement)
// with its phase, price, signal combination and exit leg: the loser table's rows.
//
// Fill models: F0 = bot/paper/paperExchange.ts semantics (orders act at once, 1 s trade-stamp slack, a print AT our price
// eats the queue shown when we joined, then fills); F1 (primary) = orders act 1 s after the decision, a resting order fills
// only on a later print strictly THROUGH its price (up to the print's size; a print without a taker side never fills it),
// IOC orders execute 1 s later against the book then; F2 = F1 plus one tick of slippage on every taker exit.
//
// Settlement audit: every position that reaches settlement is checked against the rule as of the last decision (in profit
// after fees and inside the match's last 30%, or the match decided at 97c); anything else is a breach, counted per config.

import { loadConfig, paperEnv, type TennisConfig } from '../bot/config';
import { orderFee } from '../bot/fees';
import { contractKind } from '../bot/model/fairValue';
import type { OrderBook } from '../bot/marketdata/orderBook';
import { marketWorstLoss } from '../bot/risk/exposure';
import { HourlyQuotaPacer, QuotaFloors, type PacerConfig, type PacerFloorMode } from '../bot/risk/quotaPacer';
import type { FeeSchedule } from '../bot/fees';
import { positionNetAtBid } from '../bot/strategy/fairValueStrategy';
import { decideMatch, MatchTracker, type MatchMarket, type TennisPlan, type TennisProfitRules } from '../bot/tennis/tennisStrategy';
import { readRecordings, ReplayState, type LineFilter, type RecEvent } from './replay';
import type { ConfigDay, ConfigRun, MatchGrid } from './tennisTaTypes';

/** Tennis match series: quadratic_with_maker_fees, multiplier 1 (Kalshi GET /series/fee_changes, since 2025-11-15). */
export const FEES: FeeSchedule = { takerMultiplier: 1, makerMultiplier: 1 };
const DEC_MS = 5000;
const BOOK_AGE_MS = 5000;
const TAKEN_REPLENISH_MS = 60_000;
const DAY = 86_400_000;
const DECIDED = 0.97;
/** A recorded score older than this is not passed to the strategy (the free feed polls about every 14 min). */
const SCORE_MAX_AGE_MS = 15 * 60_000;

export type FillModel = 'F0' | 'F1' | 'F2';

export interface SimSpec {
  id: string;
  /** Env-style overrides of production (TENNIS_*, PACER_*), plus harness rules: HARNESS_LOSER_STOP (fraction of cost,
   *  0 = off), HARNESS_LOSER_CUT (default true), HARNESS_BANKROLL (default 200), HARNESS_PACER ('tennis' default, 'off'),
   *  HARNESS_LATENCY_MS (added to the fill model's latency), HARNESS_FEE_MULT (fees x this, stress). */
  overrides: Record<string, string | number | boolean>;
  fill: FillModel;
  placebo?: 'coin';
  /** Decision clock phase (noise-floor runs): ms after every 5 s boundary, 0..4999. */
  offsetMs?: number;
}

interface SimOrder {
  id: number; ticker: string; side: 'bid' | 'ask'; price: number; remaining: number; initial: number;
  postOnly: boolean; reduceOnly: boolean; ioc: boolean; placedTs: number; activeTs: number; queueAhead: number; expiry: number; leg: TennisPlan['leg']; entryCounted: boolean;
}
interface Pos { yes: number; netCash: number; fees: number }
interface EventAcc { pnl: number; gross: number; fees: number; entries: number; traded: boolean; breaches: number; legs: Record<string, number>; eps: Episode[] }
/** One position from its first entry fill to flat (or settlement): a loser-table row. */
export interface Episode {
  /** Match index into SweepResult.matchList; ticker index in the match's sorted tickers (0 = market A). */
  m: number; k: number;
  /** Entry time (ms), entry leg, first fill price, most contracts held. */
  t: number; leg: string; px: number; n: number;
  /** Match phase at entry: pre, e20 (first 20 min live), p1 / p2 / p3 (in-play progress tercile). */
  ph: string;
  /** Confluence signals at the last decision before entry: momentum 1, flow 2, depth 4, opponent 8. */
  sig: number;
  /** Exit leg (or settle / drop), seconds held, realized net after fees. */
  x: string; hold: number; pnl: number;
  /** Settlement-rule breach. */
  br?: 1;
}
interface OpenEp { event: string; ticker: string; t: number; leg: string; px: number; n: number; ph: string; sig: number; base: number }
/** One owned match, in the order every config finished it. */
export interface MatchInfo { event: string; series: string; day: string; start: number; close: number; tickers: string[]; trades: number; unresolved: boolean; resultA?: 0 | 1 }
export type SimRun = ConfigRun & { pnl: number[]; episodes: Episode[] };
const sigBits = (s: { momentum: boolean; flow: boolean; depth: boolean; crossMarket: boolean }) => (+s.momentum) | (+s.flow << 1) | (+s.depth << 2) | (+s.crossMarket << 3);

const r2 = (x: number) => Math.round(x * 100) / 100;
const r4 = (x: number) => Math.round(x * 10_000) / 10_000;
const dayOf = (t: number) => new Date(t).toISOString().slice(0, 10);

/** A tennis config from env-style overrides on top of production defaults (the server sets no TENNIS_* key besides
 *  TENNIS_LIVE, deploy/bot.env.template). */
export function tennisConfigOf(overrides: Record<string, string | number | boolean>): TennisConfig {
  return configOf(overrides).tennis;
}
function configOf(overrides: Record<string, string | number | boolean>) {
  const env: Record<string, string> = {};
  for (const [k, v] of Object.entries(overrides)) if (k.startsWith('TENNIS_') || k.startsWith('PACER')) env[k] = String(v);
  return loadConfig(paperEnv(env));
}

/** Seeded RNG (mulberry32) and a string hash for seeds. */
export function rng(seed: number): () => number {
  let a = seed >>> 0;
  return () => { a = (a + 0x6d2b79f5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}
export function hash32(s: string): number { let h = 2166136261; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return h >>> 0; }

/** One config's orders, positions and per-match results. */
export class ConfigSim {
  readonly cfg: TennisConfig;
  readonly rules: TennisProfitRules;
  readonly bankroll: number;
  readonly latency: number;
  readonly slipTicks: number;
  readonly offset: number;
  readonly trackers = new Map<string, MatchTracker>();
  readonly pos = new Map<string, Pos>();
  /** Resting orders by ticker. */
  readonly resting = new Map<string, SimOrder[]>();
  pending: SimOrder[] = [];
  readonly taken = new Map<string, { taken: number; ts: number }>();
  /** Whether a held position may ride to settlement, as of the last decision (per ticker). */
  readonly rideOk = new Map<string, boolean>();
  readonly events = new Map<string, EventAcc>();
  readonly days = new Map<string, ConfigDay>();
  /** Net per owned match in finish order (0 = not traded) and the closed positions. */
  readonly matchPnl: number[] = [];
  readonly episodes: Episode[] = [];
  private readonly open = new Map<string, OpenEp>();
  /** Last confluence reading per ticker (bits). */
  private readonly lastSig = new Map<string, number>();
  /** Shared by the sweep: each live match's phase label at the last decision, and each market's fee schedule. */
  phaseOf: Map<string, string> = new Map();
  feeFor: (ticker: string) => FeeSchedule = () => FEES;
  readonly pacerCfg: PacerConfig;
  readonly floorMode: PacerFloorMode;
  readonly floorTicks: number;
  readonly usePacer: boolean;
  pacer?: HourlyQuotaPacer;
  readonly floors = new QuotaFloors();
  readonly feeMult: number;
  private nextId = 1;
  private readonly coin?: () => number;
  private readonly rates = new Map<string, { n: number; m: number; f: number; d: number; c: number }>();

  constructor(readonly spec: SimSpec) {
    const full = configOf(spec.overrides);
    this.cfg = full.tennis;
    this.pacerCfg = full.strategy.pacer;
    this.floorMode = full.strategy.pacer.floor;
    this.floorTicks = full.strategy.pacer.floorTicks;
    this.usePacer = String(spec.overrides.HARNESS_PACER ?? 'tennis') !== 'off' && full.strategy.pacer.enabled;
    this.feeMult = Number(spec.overrides.HARNESS_FEE_MULT ?? 1);
    const loserStop = Number(spec.overrides.HARNESS_LOSER_STOP ?? 0);
    const cut = spec.overrides.HARNESS_LOSER_CUT;
    this.rules = { settleFrac: this.cfg.settleFrac, loserWindowCut: cut !== false && cut !== 'false', decidedPx: DECIDED, loserStopFrac: loserStop > 0 ? loserStop : undefined };
    this.bankroll = Number(spec.overrides.HARNESS_BANKROLL ?? 200);
    this.latency = (spec.fill === 'F0' ? 0 : 1000) + Math.max(0, Number(spec.overrides.HARNESS_LATENCY_MS ?? 0));
    this.slipTicks = spec.fill === 'F2' ? 1 : 0;
    this.offset = Math.max(0, Math.min(DEC_MS - 1, spec.offsetMs ?? 0));
    if (spec.placebo === 'coin') this.coin = rng(hash32(spec.id));
  }

  tracker(event: string): MatchTracker {
    let t = this.trackers.get(event);
    if (!t) {
      t = new MatchTracker(event, this.cfg);
      if (this.coin) {
        // Placebo: each signal replaced by a coin flip at the real signal's firing rate so far on this market.
        const coin = this.coin;
        t.signalHook = (sig, ticker) => {
          let r = this.rates.get(ticker);
          if (!r) { r = { n: 0, m: 0, f: 0, d: 0, c: 0 }; this.rates.set(ticker, r); }
          r.n++; r.m += +sig.momentum; r.f += +sig.flow; r.d += +sig.depth; r.c += +sig.crossMarket;
          const momentum = coin() < r.m / r.n, flow = coin() < r.f / r.n, depth = coin() < r.d / r.n, crossMarket = coin() < r.c / r.n;
          const out = { score: [momentum, flow, depth, crossMarket].filter(Boolean).length, momentum, flow, depth, crossMarket };
          this.lastSig.set(ticker, sigBits(out));
          return out;
        };
      } else {
        t.signalHook = (sig, ticker) => { this.lastSig.set(ticker, sigBits(sig)); return sig; };
      }
      this.trackers.set(event, t);
    }
    return t;
  }

  /** Anything held or working on this ticker? */
  busy(ticker: string): boolean { return this.pos.has(ticker) || (this.resting.get(ticker)?.length ?? 0) > 0 || this.pending.some((o) => o.ticker === ticker); }

  private p(ticker: string): Pos { let x = this.pos.get(ticker); if (!x) { x = { yes: 0, netCash: 0, fees: 0 }; this.pos.set(ticker, x); } return x; }

  ev(event: string): EventAcc { let e = this.events.get(event); if (!e) { e = { pnl: 0, gross: 0, fees: 0, entries: 0, traded: false, breaches: 0, legs: {}, eps: [] }; this.events.set(event, e); } return e; }

  /** The market's fees (the stress multiplier applied). */
  fees(ticker: string): FeeSchedule {
    const f = this.feeFor(ticker);
    return this.feeMult === 1 ? f : { ...f, takerMultiplier: f.takerMultiplier * this.feeMult, makerMultiplier: f.makerMultiplier * this.feeMult };
  }

  /** The profit rules for a decision at `now`: the pacer's need and floors as the engine passes them. */
  rulesAt(now: number): TennisProfitRules {
    if (!this.usePacer) return this.rules;
    this.pacer ??= new HourlyQuotaPacer(this.pacerCfg, now);
    return { ...this.rules, pacerUsd: this.pacer.neededUsd(now), floorMode: this.floorMode, floors: this.floors, floorTicks: this.floorTicks };
  }

  /** Close a ticker's open position record. */
  private closeEp(ticker: string, x: string, realized: number, ts: number, breach: boolean): void {
    const o = this.open.get(ticker);
    if (!o) return;
    this.open.delete(ticker);
    const ep: Episode = { m: -1, k: -1, t: o.t, leg: o.leg, px: o.px, n: o.n, ph: o.ph, sig: o.sig, x, hold: Math.round((ts - o.t) / 1000), pnl: r4(realized - o.base) };
    if (breach) ep.br = 1;
    (this.events.get(o.event) ?? this.ev(o.event)).eps.push(Object.assign(ep, { k: -1, ticker } as unknown as Episode));
  }

  /** Worst-case loss of a market: position plus resting and pending orders (bot/risk/exposure.ts). */
  worst(ticker: string): number {
    const p = this.pos.get(ticker);
    const rest = [...(this.resting.get(ticker) ?? []), ...this.pending.filter((o) => o.ticker === ticker)].map((o) => ({ ticker, side: o.side, price: o.price, remaining: o.remaining, isTaker: false }));
    if (!p && !rest.length) return 0;
    return marketWorstLoss(p ? { yes: p.yes, netCash: p.netCash, fees: p.fees } : undefined, rest, this.fees(ticker));
  }

  /** Tickers this config holds or works orders on. */
  tickers(): string[] { return [...new Set([...this.pos.keys(), ...this.resting.keys(), ...this.pending.map((o) => o.ticker)])]; }

  fill(o: SimOrder, n: number, price: number, isTaker: boolean, event: string, ts: number): void {
    n = r2(Math.min(n, o.remaining));
    if (n <= 0) return;
    const p = this.p(o.ticker);
    const fee = orderFee(n, price, isTaker, this.fees(o.ticker));
    const before = p.yes, base = p.netCash - p.fees;
    if (o.side === 'bid') { p.yes = r2(p.yes + n); p.netCash -= n * price; } else { p.yes = r2(p.yes - n); p.netCash += n * price; }
    p.fees += fee;
    o.remaining = r2(o.remaining - n);
    this.pacer?.onFill({ ticker: o.ticker, side: o.side, count: n, price }, fee, p, ts);
    if (before <= 1e-9 && p.yes > 1e-9) this.open.set(o.ticker, { event, ticker: o.ticker, t: ts, leg: o.leg, px: price, n: p.yes, ph: this.phaseOf.get(event) ?? 'pre', sig: this.lastSig.get(o.ticker) ?? 0, base });
    else if (p.yes > 1e-9) { const op = this.open.get(o.ticker); if (op && p.yes > op.n) op.n = p.yes; }
    if (before > 1e-9 && p.yes <= 1e-9) { this.closeEp(o.ticker, o.leg, p.netCash - p.fees, ts, false); this.floors.forget(o.ticker); }
    const e = this.ev(event);
    e.traded = true;
    e.legs[o.leg] = (e.legs[o.leg] ?? 0) + 1;
    if (!o.entryCounted && o.side === 'bid' && (o.leg === 'underdog_entry' || o.leg === 'fav_entry')) { e.entries++; o.entryCounted = true; }
  }

  /** Taker execution: walk the opposite side of the visible book (what we took in the last minute still missing). */
  private take(o: SimOrder, book: OrderBook, now: number, event: string): void {
    const levels = o.side === 'bid' ? book.snapshot(50).asks : book.snapshot(50).bids;
    const bookSide = o.side === 'bid' ? 'ask' : 'bid';
    for (const lvl of levels) {
      if (o.remaining <= 1e-9) break;
      const through = o.side === 'bid' ? lvl.price <= o.price + 1e-9 : lvl.price >= o.price - 1e-9;
      if (!through) break;
      const key = `${o.ticker}|${bookSide}|${lvl.price}`;
      let e = this.taken.get(key);
      if (e && now - e.ts >= TAKEN_REPLENISH_MS) { this.taken.delete(key); e = undefined; }
      const avail = e ? Math.max(0, lvl.size - e.taken) : lvl.size;
      const n = Math.min(avail, o.remaining);
      if (n <= 1e-9) continue;
      // F2: taker exits one tick worse than the level.
      const px = o.side === 'ask' && o.reduceOnly && this.slipTicks ? Math.max(0.01, r4(lvl.price - 0.01 * this.slipTicks)) : lvl.price;
      this.fill(o, n, px, true, event, now);
      this.taken.set(key, { taken: (e?.taken ?? 0) + n, ts: now });
    }
    if (this.taken.size > 2000) for (const [k, v] of this.taken) if (now - v.ts >= TAKEN_REPLENISH_MS) this.taken.delete(k);
  }

  /** Place one plan (the engine's checks, simplified: tick snapping, post-only cross, reduce-only, market close). */
  place(pl: TennisPlan, book: OrderBook | undefined, now: number, closeTime: number, event: string, tick: number): void {
    if (now >= closeTime - 1000 || !book) return;
    const price = r4(pl.side === 'bid' ? Math.floor(pl.price / tick + 1e-9) * tick : Math.ceil(pl.price / tick - 1e-9) * tick);
    if (!(price >= 0.01 - 1e-9 && price <= 0.99 + 1e-9)) return;
    let count = r2(pl.count);
    if (pl.reduceOnly) {
      const p = this.pos.get(pl.ticker);
      if (pl.side !== 'ask' || !p || p.yes <= 0) return;
      count = Math.min(count, p.yes);
    }
    if (count <= 0) return;
    const ioc = pl.timeInForce === 'immediate_or_cancel';
    if (pl.reduceOnly && !ioc) return;
    const bb = book.bestBid(), ba = book.bestAsk();
    const crosses = pl.side === 'bid' ? ba !== undefined && price >= ba.price - 1e-9 : bb !== undefined && price <= bb.price + 1e-9;
    if (pl.postOnly && crosses) return;
    const o: SimOrder = { id: this.nextId++, ticker: pl.ticker, side: pl.side, price, remaining: count, initial: count, postOnly: pl.postOnly, reduceOnly: pl.reduceOnly, ioc, placedTs: now, activeTs: now + this.latency, queueAhead: 0, expiry: Math.min(now + 3_600_000, closeTime - 1000), leg: pl.leg, entryCounted: false };
    if (this.latency > 0) { this.pending.push(o); return; }
    this.activate(o, book, now, event);
  }

  /** An order reaches the exchange: takers execute against the book now; GTC rests behind what the level shows. */
  activate(o: SimOrder, book: OrderBook | undefined, now: number, event: string): void {
    if (!book) return;
    if (o.reduceOnly) { const p = this.pos.get(o.ticker); o.remaining = Math.min(o.remaining, Math.max(0, p?.yes ?? 0)); if (o.remaining <= 0) return; }
    const bb = book.bestBid(), ba = book.bestAsk();
    const crosses = o.side === 'bid' ? ba !== undefined && o.price >= ba.price - 1e-9 : bb !== undefined && o.price <= bb.price + 1e-9;
    if (o.postOnly && crosses) return; // the market moved into it during the latency: rejected, as post-only is
    if (crosses) this.take(o, book, now, event);
    if (o.remaining <= 1e-9 || o.ioc) return;
    o.queueAhead = book.sizeAt(o.side, o.price);
    const list = this.resting.get(o.ticker);
    if (list) list.push(o); else this.resting.set(o.ticker, [o]);
  }

  /** A print on the tape: our resting orders fill (F0: at-price prints eat the queue first; F1/F2: only prints through). */
  onTrade(ticker: string, price: number, count: number, takerSide: 'yes' | 'no' | undefined, ts: number, event: string): void {
    const list = this.resting.get(ticker);
    if (!list?.length) return;
    let remaining = count;
    const strict = this.spec.fill !== 'F0';
    const cands = list.filter((o) => (strict ? o.activeTs <= ts : o.placedTs <= ts + 1000) && o.expiry > ts
      && (o.side === 'bid' ? takerSide !== 'yes' && price <= o.price + 1e-9 : takerSide !== 'no' && price >= o.price - 1e-9))
      .sort((a, b) => (a.side === 'bid' ? b.price - a.price : a.price - b.price));
    for (const o of cands) {
      if (remaining <= 1e-9) break;
      const through = o.side === 'bid' ? price < o.price - 1e-9 : price > o.price + 1e-9;
      if (strict && (!through || takerSide === undefined)) continue;
      if (!through) {
        const eat = Math.min(o.queueAhead, remaining);
        o.queueAhead -= eat; remaining -= eat;
        if (o.queueAhead > 1e-9 || remaining <= 1e-9) continue;
      }
      const n = Math.min(o.remaining, remaining);
      remaining -= n;
      this.fill(o, n, o.price, false, event, ts);
    }
    this.prune(ticker);
  }

  private prune(ticker: string): void {
    const list = this.resting.get(ticker);
    if (!list) return;
    const keep = list.filter((o) => o.remaining > 1e-9);
    if (keep.length) this.resting.set(ticker, keep); else this.resting.delete(ticker);
  }

  /** Pending orders whose latency has passed reach the exchange. */
  activateDue(now: number, books: (t: string) => OrderBook | undefined, eventOf: (t: string) => string): void {
    if (!this.pending.length) return;
    const due = this.pending.filter((o) => o.activeTs <= now);
    if (!due.length) return;
    this.pending = this.pending.filter((o) => o.activeTs > now);
    for (const o of due) this.activate(o, books(o.ticker), o.activeTs, eventOf(o.ticker));
  }

  /** Expired resting orders leave the book. */
  expire(now: number): void {
    for (const [t, list] of this.resting) if (list.some((o) => o.expiry <= now)) { const keep = list.filter((o) => o.expiry > now); if (keep.length) this.resting.set(t, keep); else this.resting.delete(t); }
  }

  cancel(ticker: string, keep: (o: SimOrder) => boolean): void {
    const list = this.resting.get(ticker);
    if (!list) return;
    const k = list.filter(keep);
    if (k.length) this.resting.set(ticker, k); else this.resting.delete(ticker);
  }

  /** Settle a market: payout, realized P&L into its match, the settlement-rule audit. */
  settle(ticker: string, result: 'yes' | 'no', event: string, ts: number): void {
    this.resting.delete(ticker);
    this.pending = this.pending.filter((o) => o.ticker !== ticker);
    this.floors.forget(ticker);
    const p = this.pos.get(ticker);
    if (!p) return;
    const e = this.ev(event);
    const breach = p.yes > 1e-9 && !this.rideOk.get(ticker);
    if (breach) e.breaches++;
    const payout = result === 'yes' ? p.yes : 0;
    const realized = p.netCash + payout - p.fees;
    e.pnl += realized;
    e.gross += p.netCash + payout;
    e.fees += p.fees;
    this.pacer?.onSettled(ticker, realized, ts);
    if (p.yes > 1e-9) this.closeEp(ticker, 'settle', realized, ts, breach);
    this.pos.delete(ticker);
    this.rideOk.delete(ticker);
  }

  /** Close a match into its day (an unresolved match's open positions are dropped and counted). */
  finish(event: string, tickers: string[], day: string, unresolved: boolean, ts: number, owned = true): void {
    for (const t of tickers) {
      this.resting.delete(t);
      this.pending = this.pending.filter((o) => o.ticker !== t);
      this.floors.forget(t);
      const p = this.pos.get(t);
      if (p) {
        const e = this.ev(event);
        e.pnl += p.netCash - p.fees; e.gross += p.netCash; e.fees += p.fees;
        if (p.yes > 1e-9) { e.breaches++; this.closeEp(t, 'drop', p.netCash - p.fees, ts, true); }
        this.pos.delete(t);
      }
      this.open.delete(t);
      this.rideOk.delete(t);
      this.lastSig.delete(t);
    }
    const e = this.events.get(event);
    this.trackers.delete(event);
    this.events.delete(event);
    if (!owned) return;
    const m = this.matchPnl.length;
    this.matchPnl.push(e ? r4(e.pnl) : 0);
    if (e) for (const ep of e.eps) { const t = (ep as unknown as { ticker: string }).ticker; delete (ep as unknown as { ticker?: string }).ticker; ep.m = m; ep.k = tickers.indexOf(t); this.episodes.push(ep); }
    let d = this.days.get(day);
    if (!d) { d = { day, matches: 0, traded: 0, entries: 0, pnl: 0, gross: 0, fees: 0, breaches: 0, unresolved: 0, legs: {} }; this.days.set(day, d); }
    d.matches++;
    if (unresolved) d.unresolved++;
    if (!e) return;
    if (e.traded) d.traded++;
    d.entries += e.entries; d.pnl += e.pnl; d.gross += e.gross; d.fees += e.fees; d.breaches += e.breaches;
    for (const [k, v] of Object.entries(e.legs)) d.legs[k] = (d.legs[k] ?? 0) + v;
  }

  run(stratum: 'H' | 'R'): SimRun {
    const days = [...this.days.values()].sort((a, b) => a.day.localeCompare(b.day)).map((d) => ({ ...d, pnl: r4(d.pnl), gross: r4(d.gross), fees: r4(d.fees) }));
    return { id: this.spec.id, overrides: this.spec.overrides, fill: this.spec.fill, ...(this.spec.placebo ? { placebo: this.spec.placebo } : {}), stratum, days, pnl: this.matchPnl, episodes: this.episodes };
  }
}

/** The lines a tennis sweep reads: match markets, their books, deltas, trades, results, alive marks and scores. */
export function tennisOnly(): LineFilter {
  const matches = new Set<string>();
  const TICKER = /"ticker":"([^"]+)"/;
  return (k, line) => {
    switch (k) {
      case 'market':
        try { const m = JSON.parse(line); if ((m.kind ?? contractKind(m.series ?? '')) === 'match') { matches.add(m.ticker); return true; } } catch { /* torn line */ }
        return false;
      case 'book': case 'delta': case 'trade': case 'result':
        return matches.has(TICKER.exec(line)?.[1] ?? '');
      case 'alive': case 'tennis_score':
        return true;
      default:
        return false;
    }
  };
}

/** Builds a MatchGrid while the replay streams: one sample a second, the book as it stood then. */
class GridBuilder {
  t0 = 0;
  n = 0;
  readonly cols: number[][] = Array.from({ length: 10 }, () => []);
  readonly prog: number[] = [];
  progress = 0;
  liveIdx = -1;
  readonly vol = [0, 0, 0, 0];
  sample(t: number, books: Array<OrderBook | undefined>, usable: (b: OrderBook | undefined) => boolean): void {
    if (!this.n) this.t0 = t;
    const q = (b: OrderBook | undefined) => (usable(b) ? [b!.bestBid()?.price ?? NaN, b!.bestAsk()?.price ?? NaN, b!.imbalance(3)] : [NaN, NaN, NaN]);
    const [ba, aa, ia] = q(books[0]);
    const [bb, ab, ib] = q(books[1]);
    const row = [ba, aa, bb, ab, this.vol[0], this.vol[1], this.vol[2], this.vol[3], ia, ib];
    for (let k = 0; k < 10; k++) this.cols[k].push(row[k]);
    this.prog.push(this.progress);
    this.vol.fill(0);
    this.n++;
  }
  build(ev: LiveEvent, stratum: 'H' | 'R', resultA: 0 | 1): MatchGrid {
    const f = (k: number) => Float64Array.from(this.cols[k]);
    const closeIdx = Math.max(0, Math.min(this.n - 1, Math.floor((ev.closeTime - this.t0) / 1000)));
    return { event: ev.event, series: ev.series, stratum, tickers: [ev.tickers[0], ev.tickers[1]], start: ev.start, day: ev.day, t0: this.t0, n: this.n,
      bidA: f(0), askA: f(1), bidB: f(2), askB: f(3), yesVolA: f(4), noVolA: f(5), yesVolB: f(6), noVolB: f(7), imbA: f(8), imbB: f(9),
      progress: Float64Array.from(this.prog), liveIdx: this.liveIdx, resultA, closeIdx };
  }
}

interface LiveEvent {
  event: string; tickers: string[]; day: string; start: number; closeTime: number; series: string;
  owned: boolean; done: boolean;
  /** Prints seen on its markets (0 = no tape: excluded from the history universe by the report). */
  trades: number;
  grid?: GridBuilder;
  /** A production-default tracker: the grid's progress clock. */
  clock: MatchTracker;
}

export interface SweepOpts {
  dir: string;
  fromDay: string;
  /** Last day whose matches (by start) this run owns; the reader goes on a day further so late matches finish. */
  toDay: string;
  stratum: 'H' | 'R';
  specs: SimSpec[];
  /** Pool membership on top of [fromDay, toDay]: sealed / dev units, the lockbox exclusion, the hard cutoff. */
  admit?: (m: { event: string; series: string; start: number; closeTime: number }) => boolean;
  /** Fee schedule of a series at a time (fee changes); FEES when unset. */
  feeAt?: (series: string, t: number) => FeeSchedule;
  /** Every completed two-market match grid, in non-decreasing day order (family B). */
  onGrid?: (g: MatchGrid) => void;
  log?: (m: string) => void;
}

export interface SweepResult { runs: SimRun[]; matchList: MatchInfo[]; matches: number; oneLegged: number; unresolved: number; events: number; decisions: number; ms: number }

/** Phase label of a match from its clock: pre, e20 (first 20 min live), then the in-play progress tercile. */
export function phaseLabel(liveSince: number | undefined, now: number, progress: number): string {
  if (liveSince === undefined) return 'pre';
  if (now - liveSince < 20 * 60_000) return 'e20';
  return progress < 1 / 3 ? 'p1' : progress < 2 / 3 ? 'p2' : 'p3';
}

/** Run every spec over the owned matches of [fromDay, toDay]. */
export async function runSweep(o: SweepOpts): Promise<SweepResult> {
  const t0 = Date.now();
  const log = o.log ?? (() => {});
  const st = new ReplayState();
  const sims = o.specs.map((s) => new ConfigSim(s));
  const phaseOf = new Map<string, string>();
  const seriesOf = new Map<string, string>();
  const feeFor = (ticker: string) => (o.feeAt ? o.feeAt(seriesOf.get(ticker) ?? '', st.now) : FEES);
  for (const sim of sims) { sim.phaseOf = phaseOf; sim.feeFor = feeFor; }
  const matchList: MatchInfo[] = [];
  const defaultCfg = tennisConfigOf({});
  const live = new Map<string, LiveEvent>();
  const evOfTicker = new Map<string, string>();
  const ownFrom = Date.parse(o.fromDay), ownTo = Date.parse(o.toDay) + DAY;
  const readFrom = new Date(ownFrom - DAY).toISOString().slice(0, 10), readTo = new Date(ownTo + DAY).toISOString().slice(0, 10);
  // One decision clock per phase offset (production: one clock, every 5 s).
  const byOffset = new Map<number, ConfigSim[]>();
  for (const s of sims) byOffset.set(s.offset, [...(byOffset.get(s.offset) ?? []), s]);
  const clocks = [...byOffset.keys()].sort((a, b) => a - b).map((off) => ({ off, next: Infinity, sims: byOffset.get(off)! }));
  const firstOff = clocks[0]?.off ?? 0;
  let nextSec = Infinity;
  let matches = 0, oneLegged = 0, unresolvedN = 0, events = 0, decisions = 0, liveOwned = 0;
  const gridQueue: MatchGrid[] = [];
  const isUsable = (b: OrderBook | undefined, now: number) => {
    if (!b) return false;
    // Production marks every book alive each second while the socket is up (bot/marketdata/marketData.ts); the
    // recordings do not carry those marks, so a recorded book counts as current. History carries its own alive marks.
    if (o.stratum === 'R') b.markAlive(now);
    return b.isUsable(now, BOOK_AGE_MS);
  };
  const eventOf = (t: string) => evOfTicker.get(t) ?? t.slice(0, t.lastIndexOf('-'));
  const books = (t: string) => st.books.get(t);

  const releaseGrids = (now: number) => {
    if (!o.onGrid || !gridQueue.length) return;
    gridQueue.sort((a, b) => a.day.localeCompare(b.day) || a.start - b.start);
    // A day's matches are released once every match that started that day has had 36 h to finish.
    while (gridQueue.length && Date.parse(gridQueue[0].day) + DAY + 36 * 3_600_000 <= now) o.onGrid(gridQueue.shift()!);
  };

  const flowOf = (ticker: string, now: number, windowSec: number): number | undefined => {
    const tr = st.features.micro.get(ticker)?.tradesIn(now, windowSec * 1000) ?? [];
    let tot = 0, sig = 0;
    for (const x of tr) { tot += x.count; sig += x.signed; }
    return tot > 0 ? sig / tot : undefined;
  };

  const decide = (now: number, cl: { off: number; sims: ConfigSim[] }) => {
    for (const ev of live.values()) {
      if (!ev.owned || ev.done || now >= ev.closeTime) continue;
      // The market as every config sees it (positions added per config).
      const base = ev.tickers.map((t) => {
        const b = st.books.get(t);
        const ok = isUsable(b, now);
        return { t, b: ok ? b : undefined, bb: ok ? b!.bestBid() : undefined, ba: ok ? b!.bestAsk() : undefined, title: st.markets.get(t)?.title };
      });
      const plain: MatchMarket[] = base.map((x) => ({ ticker: x.t, title: x.title, position: 0, quote: { bid: x.bb?.price, ask: x.ba?.price, bidSize: x.bb?.size, askSize: x.ba?.size }, book: x.b }));
      // Recorded books: the live score as the feed last gave it (production passes the feed's latest; none on history).
      const sc = o.stratum === 'R' ? st.tennisScores.get(ev.event) : undefined;
      const score = sc && now - sc.ts <= SCORE_MAX_AGE_MS ? sc : undefined;
      if (cl.off === firstOff) {
        ev.clock.observe({ event: ev.event, now, startTime: ev.start, markets: plain, closeTime: ev.closeTime, score });
        const prog = ev.clock.liveSince !== undefined ? ev.clock.progress(now, plain) : 0;
        phaseOf.set(ev.event, phaseLabel(ev.clock.liveSince, now, prog));
        if (ev.grid) { ev.grid.progress = prog; if (ev.grid.liveIdx < 0 && ev.clock.liveSince !== undefined) ev.grid.liveIdx = Math.max(0, ev.grid.n - 1); }
      }
      const tick = st.markets.get(ev.tickers[0])?.tickSize ?? 0.01;
      const flows = new Map<number, Array<number | undefined>>();
      const pA0 = MatchTracker.probability(plain);
      const decided = pA0 !== undefined && (pA0 >= DECIDED - 1e-9 || pA0 <= 1 - DECIDED + 1e-9);
      for (const sim of cl.sims) {
        const w = sim.cfg.confWindowSec;
        let fl = flows.get(w);
        if (!fl) { fl = ev.tickers.map((t) => flowOf(t, now, w)); flows.set(w, fl); }
        const markets: MatchMarket[] = base.map((x, i) => {
          const p = sim.pos.get(x.t);
          const yes = p?.yes ?? 0;
          if (!(yes > 0)) return { ...plain[i], flow: fl![i] };
          const costPer = (p!.fees - p!.netCash) / yes;
          return { ...plain[i], flow: fl![i], position: yes, avgEntry: -p!.netCash / yes, costPer, netAtBid: positionNetAtBid(yes, costPer, x.bb, x.ba, sim.fees(x.t)) };
        });
        const held = sim.tickers();
        const tennisRisk = held.length ? held.reduce((s, t) => s + sim.worst(t), 0) : 0;
        const matchRisk = held.length ? ev.tickers.reduce((s, t) => s + (held.includes(t) ? sim.worst(t) : 0), 0) : 0;
        const tr = sim.tracker(ev.event);
        const out = decideMatch(tr, { event: ev.event, now, startTime: ev.start, markets, closeTime: ev.closeTime, score }, sim.cfg, { bankroll: sim.bankroll, tennisRisk, matchRisk }, tick, sim.rulesAt(now));
        decisions++;
        // The settlement audit: may each held position ride, by the rule as of now?
        if (markets.some((m) => m.position > 0)) {
          const prog = tr.liveSince !== undefined ? tr.progress(now, markets) : 0;
          for (const m of markets) if (m.position > 0) sim.rideOk.set(m.ticker, (prog >= 1 - sim.cfg.settleFrac - 1e-9 || decided) && (m.netAtBid ?? -1) > 1e-9);
        }
        if (!out.plans.length && !held.some((t) => ev.tickers.includes(t))) continue;
        // Order sync: cancel resting orders no longer planned, place the new ones.
        const same = (p: TennisPlan, x: SimOrder) => p.ticker === x.ticker && p.side === x.side && Math.abs(p.price - x.price) < 1e-9 && Math.abs(p.count - x.remaining) < 0.02;
        for (const t of ev.tickers) sim.cancel(t, (x) => out.plans.some((p) => same(p, x)));
        for (const p of out.plans) {
          if ((sim.resting.get(p.ticker) ?? []).some((x) => same(p, x)) || sim.pending.some((x) => same(p, x))) continue;
          sim.place(p, st.books.get(p.ticker), now, ev.closeTime, ev.event, tick);
        }
      }
    }
  };

  const sampleGrids = (t: number) => {
    for (const ev of live.values()) {
      if (!ev.owned || ev.done || !ev.grid || ev.tickers.length < 2 || t > ev.closeTime) continue;
      ev.grid.sample(t, [st.books.get(ev.tickers[0]), st.books.get(ev.tickers[1])], (b) => isUsable(b, t));
    }
  };

  const finishEvent = (ev: LiveEvent, unresolved: boolean, ts: number) => {
    if (ev.done) return;
    ev.done = true;
    if (ev.owned) {
      liveOwned--;
      matches++;
      if (ev.tickers.length < 2) oneLegged++;
      if (unresolved) unresolvedN++;
      for (const sim of sims) sim.finish(ev.event, ev.tickers, ev.day, unresolved, ts);
      const rA = st.results.get(ev.tickers[0]);
      matchList.push({ event: ev.event, series: ev.series, day: ev.day, start: ev.start, close: ev.closeTime, tickers: ev.tickers, trades: ev.trades, unresolved, ...(rA ? { resultA: rA === 'yes' ? 1 as const : 0 as const } : {}) });
      if (ev.grid && ev.tickers.length >= 2 && rA) gridQueue.push(ev.grid.build(ev, o.stratum, rA === 'yes' ? 1 : 0));
    } else {
      // Not owned (outside the slice, or out of the pool): configs never traded it; drop any state.
      for (const sim of sims) sim.finish(ev.event, ev.tickers, ev.day, unresolved, ts, false);
    }
    phaseOf.delete(ev.event);
    for (const t of ev.tickers) { st.forget(t); st.results.delete(t); evOfTicker.delete(t); seriesOf.delete(t); }
    live.delete(ev.event);
  };

  for await (const e of readRecordings(o.dir, '', readFrom, readTo, tennisOnly()) as AsyncIterable<RecEvent>) {
    if (e.k === 'skip') continue;
    // Clocks up to this event: grid seconds, then each decision clock (orders that came due reach the exchange first).
    if (liveOwned > 0) {
      for (;;) {
        let cl = clocks[0];
        for (const c of clocks) if (c.next < cl.next) cl = c;
        const tDec = cl ? cl.next : Infinity;
        if (Math.min(tDec, nextSec) > e.t) break;
        if (nextSec <= tDec) { sampleGrids(nextSec); nextSec += 1000; continue; }
        for (const sim of cl.sims) { sim.activateDue(tDec, books, eventOf); sim.expire(tDec); }
        decide(tDec, cl);
        cl.next += DEC_MS;
      }
    }
    for (const sim of sims) sim.activateDue(e.t, books, eventOf);
    st.apply(e);
    events++;
    switch (e.k) {
      case 'market': {
        const m = st.markets.get(e.ticker);
        if (!m || m.kind !== 'match') break;
        const event = m.event ?? e.ticker.slice(0, e.ticker.lastIndexOf('-'));
        evOfTicker.set(e.ticker, event);
        seriesOf.set(e.ticker, m.series);
        let ev = live.get(event);
        if (!ev) {
          const start = m.startTime ?? e.t;
          const owned = start >= ownFrom && start < ownTo && (o.admit?.({ event, series: m.series, start, closeTime: m.closeTime }) ?? true);
          ev = { event, tickers: [], day: dayOf(start), start, closeTime: m.closeTime, series: m.series, owned, done: false, trades: 0, clock: new MatchTracker(event, defaultCfg), grid: o.onGrid && owned ? new GridBuilder() : undefined };
          live.set(event, ev);
          if (owned) {
            if (liveOwned === 0) {
              for (const c of clocks) c.next = Math.ceil((e.t - c.off) / DEC_MS) * DEC_MS + c.off;
              nextSec = Math.ceil(e.t / 1000) * 1000;
            }
            liveOwned++;
          }
        }
        if (!ev.tickers.includes(e.ticker)) { ev.tickers.push(e.ticker); ev.tickers.sort(); }
        ev.closeTime = Math.max(ev.closeTime, m.closeTime);
        break;
      }
      case 'trade': {
        const ev = live.get(evOfTicker.get(e.ticker) ?? '');
        if (!ev?.owned || ev.done) break;
        ev.trades++;
        const ts = e.ts ?? e.t;
        for (const sim of sims) sim.onTrade(e.ticker, e.price, e.count, e.takerSide, ts, ev.event);
        if (ev.grid) { const i = ev.tickers.indexOf(e.ticker); if (i === 0 || i === 1) ev.grid.vol[i * 2 + (e.takerSide === 'yes' ? 0 : 1)] += e.count; }
        break;
      }
      case 'result': {
        const ev = live.get(evOfTicker.get(e.ticker) ?? '');
        if (!ev) break;
        if (ev.owned) for (const sim of sims) sim.settle(e.ticker, e.result, ev.event, e.t);
        if (ev.tickers.every((t) => st.results.has(t))) finishEvent(ev, false, e.t);
        break;
      }
      default:
        break;
    }
    if (events % 20_000 === 0) {
      // A match long past its close without a result is finished as unresolved (its open positions counted).
      for (const ev of [...live.values()]) if (e.t > ev.closeTime + 2 * DAY) finishEvent(ev, true, e.t);
      releaseGrids(e.t);
    }
  }
  for (const ev of [...live.values()]) finishEvent(ev, true, st.now);
  if (o.onGrid) { gridQueue.sort((a, b) => a.day.localeCompare(b.day) || a.start - b.start); for (const g of gridQueue.splice(0)) o.onGrid(g); }
  log(`sweep ${o.fromDay}..${o.toDay} (${o.stratum}): ${matches} matches (${oneLegged} one-legged, ${unresolvedN} unresolved), ${o.specs.length} configs, ${decisions} decisions, ${((Date.now() - t0) / 1000).toFixed(0)} s`);
  return { runs: sims.map((s) => s.run(o.stratum)), matchList, matches, oneLegged, unresolved: unresolvedN, events, decisions, ms: Date.now() - t0 };
}
