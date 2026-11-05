// Tennis TA rulebook trial, family A and the match grids (pre-registration: /mnt/project-files/tennis-ta/preregistration.md,
// section 4 as restated by Amendments 1 (A6) and 3).
//
// One pass over a stretch of tennis replay days (Kalshi history built by research/history/historyReplay.ts tennisEvents, or
// the bot's recordings cut to tennis lines by research/tennisTaData.ts) runs MANY configs of the production tennis strategy
// in lock-step: market data (books, tape, results) is shared, each config has its own trackers, orders and positions.
//
// What it mirrors from production (bot/engine.ts tennisTick): decisions every 5 s through decideMatch with the
// TennisProfitRules the engine builds (pacerUsd, settleFrac, endLoserCut, endEntryMargin, floorMode, floors, floorTicks):
// the after-fee ride in the last 30% of the match, the end loser cut (TENNIS_END_LOSER_CUT, leg end_cut) and the entry block
// before it, the quota snipe. Each market gets avgEntry = -netCash/yes, netAtBid (positionNetAtBid) and breakEven
// (breakEvenExit) on the position's round-trip cost basis (fees - netCash)/yes with that market's fee schedule, as the engine
// computes them; quotes only from books the engine would use (no older than RISK_MAX_BOOK_AGE_MS, not crossed); flow over
// confWindowSec from the tape; the strategy gets the event's published start (none when Kalshi gave none: the tracker then
// detects the start from the price) and the EARLIEST of its markets' closes. Fees per fill with bot/fees.ts (tennis pays
// maker and taker fees, each fill rounded up to the cent); the per-order / per-match / total tennis caps through tennisSize
// on a fixed $200 bankroll (no compounding: a sterile sweep); resting orders cancelled when no longer planned; GTC orders
// expiring at min(1 h, their market's close - 1 s).
// The quota pacer (Amendment 1, A6): each config runs its own HourlyQuotaPacer at the production PACER_* settings, fed by
// its own tennis fills and settlements (and the drops of matches that never settle), plus QuotaFloors. Production's pacer
// also sees crypto and perps, which a tennis replay cannot reproduce; HARNESS_PACER=off is the sensitivity arm. The pacer,
// the risk caps and the placebo reservoir live as long as the run: the sweep cuts runs at unit edges (Amendment 3), so they
// restart only there.
// What it does not: the riskScale / optimal-f scaling and equity guard (persisted state), feed-lag and sports halts, the
// curve gate (a no-op under the default SINUOUS_EXIT=cross), the fair model and SNN features (no fairA is passed).
//
// Recorded books (stratum R): production marks every intact book alive each second while the Kalshi socket has had a
// message in the last 12 s (its pings keep a quiet socket alive), invalidates every book on a disconnect, and re-snapshots
// only on (re)subscribe. The recordings carry neither the pings nor the disconnects, so a pre-pass over the same files
// (feedTimeline) rebuilds the feed's outages, per day file:
//  - a day that shows the feed's liveness (a heartbeat line, kind 'hb', which a tennis cut may keep for every second of
//    raw-file activity; or the socket's lines of other markets, as a raw recording has): every silence of the socket's
//    lines (book, delta, trade, lifecycle) and heartbeats longer than 12 s is an outage;
//  - a blind day (the tennis cut without heartbeats, as research/tennisTaData.ts writes it today; production writes no
//    heartbeat kind): a tennis silence is a quiet market, not a disconnect, unless it ends in a resubscribe, i.e. snapshots
//    of at least two already-snapshotted books within RESYNC_WINDOW_MS of the line that ends it (a reconnect or a restart).
// In an outage books are marked alive only up to 12 s after its last line (so unusable 17 s after it, as production's
// books go stale once the socket falls silent) and are invalidated at its end: no quote, no fill, until the next snapshot.
// A blind outage is known once it ends; the pre-pass gives the sim the disconnect production itself knew of at the time
// (no market data comes from it), and dates it from the last tennis line, which is conservative. Settlements come from
// 'result' lines and from Kalshi's lifecycle lines (determined / settled with a result), the first one per market. A
// recorded match's market line is written when the bot first lists it (up to 36 h before the start), so R reads
// lookbackDays before fromDay.
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
// Settlement audit (Amendment 3): a position held into settlement is a breach unless, at the config's last decision before
// it, the match was in its last settleFrac share by the progress production's ride rule reads (MatchTracker.progress) AND
// the position's net at the bid after fees was above zero. The verdict is refreshed at every decision for every held market
// and dropped whenever a position opens or goes flat, so a position no decision has judged is a breach. A position still
// open when its match never settles is dropped and counted as a breach too. With TENNIS_END_LOSER_CUT=false (the
// settle-hold measuring stick) breaches are expected, and counted.
//
// Coin placebo (Amendment 3): every confluence evaluation is answered with one whole past reading (all four signals
// together) drawn at random from a reservoir of the same config's real readings on OTHER matches strictly earlier in time;
// the current real reading joins the reservoir only after the clock has moved past it (an empty reservoir answers no
// signal). The placebo never sees the reading it replaces, keeps the joint firing distribution, and breaks the timing.
// Amendment 3 is drafted and goes into the pre-registration before the stage 1 counting run; until it does, the registered
// text (section 7, Placebo A: a coin flip per signal at the match's firing rate) differs from this control.

import { loadConfig, paperEnv, type TennisConfig } from '../bot/config';
import { orderFee } from '../bot/fees';
import { contractKind } from '../bot/model/fairValue';
import type { OrderBook } from '../bot/marketdata/orderBook';
import { marketWorstLoss } from '../bot/risk/exposure';
import { HourlyQuotaPacer, QuotaFloors, type PacerConfig, type PacerFloorMode } from '../bot/risk/quotaPacer';
import type { FeeSchedule } from '../bot/fees';
import { breakEvenExit, positionNetAtBid } from '../bot/strategy/fairValueStrategy';
import { recordingFiles, recordingLines } from '../bot/marketdata/recordingFiles';
import { decideMatch, MatchTracker, type MatchMarket, type TennisPlan, type TennisProfitRules } from '../bot/tennis/tennisStrategy';
import { readRecordings, ReplayState, type LineFilter, type RecEvent } from './replay';
import type { ConfigDay, ConfigRun, MatchGrid } from './tennisTaTypes';

/** Tennis match series: quadratic_with_maker_fees, multiplier 1 (Kalshi GET /series/fee_changes, since 2025-11-15). */
export const FEES: FeeSchedule = { takerMultiplier: 1, makerMultiplier: 1 };
const DEC_MS = 5000;
const TAKEN_REPLENISH_MS = 60_000;
const DAY = 86_400_000;
/** Production marks books alive only while the socket has had a message within this long (bot/marketdata/marketData.ts). */
export const FEED_SILENCE_MS = 12_000;
/** Blind R days: a tennis silence is an outage when resubscribe snapshots follow the line that ends it this soon. */
export const RESYNC_WINDOW_MS = 15_000;
/** The heartbeat kind a tennis cut may keep (one line per second of raw-file activity); production writes none. */
export const HEARTBEAT_KIND = 'hb';
/** A recorded score older than this is not passed to the strategy (the free feed polls about every 14 min). */
const SCORE_MAX_AGE_MS = 15 * 60_000;
/** A match grid starts at most this long before the published start (R lists a match up to 36 h ahead). */
const GRID_PRE_MS = 3 * 3_600_000;
/** Coin placebo: readings kept per config. */
export const PLACEBO_RESERVOIR = 4096;
/** Lifecycle lines that settle a market (bot/engine.ts and bot/main.ts settle on these). */
const SETTLING = /settle|determin/i;

export type FillModel = 'F0' | 'F1' | 'F2';

export interface SimSpec {
  id: string;
  /** Env-style overrides of production (TENNIS_*, PACER_*), plus harness rules: HARNESS_LOSER_STOP (research loser stop,
   *  a fraction of the open lot's cost, 0 = off), HARNESS_BANKROLL (default 200), HARNESS_PACER ('tennis' default, 'off'),
   *  HARNESS_LATENCY_MS (added to the fill model's latency), HARNESS_FEE_MULT (fees x this, stress). With no override the
   *  config is production's defaults exactly (TENNIS_END_LOSER_CUT on; the settle-hold stick sets it false). */
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
/** A market's position: the round-trip book as production keeps it (never reset until settlement), and the open lot's own
 *  cash and fees (reset when a flat position opens) for the research loser stop's cost. */
export interface Pos { yes: number; netCash: number; fees: number; lotCash: number; lotFees: number }
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
/** One owned match, in the order every config finished it. `start` is the published start, else the earliest market-line
 *  time (bookkeeping only: ownership, day, unit); `startPublished` says which. */
export interface MatchInfo { event: string; series: string; day: string; start: number; startPublished: boolean; close: number; tickers: string[]; trades: number; unresolved: boolean; resultA?: 0 | 1 }
export type SimRun = ConfigRun & { pnl: number[]; episodes: Episode[] };
type Sig = { score: number; momentum: boolean; flow: boolean; depth: boolean; crossMarket: boolean };
export const sigBits = (s: Omit<Sig, 'score'>) => (+s.momentum) | (+s.flow << 1) | (+s.depth << 2) | (+s.crossMarket << 3);
export const sigOf = (b: number): Sig => {
  const momentum = (b & 1) !== 0, flow = (b & 2) !== 0, depth = (b & 4) !== 0, crossMarket = (b & 8) !== 0;
  return { score: +momentum + +flow + +depth + +crossMarket, momentum, flow, depth, crossMarket };
};

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

/** The coin placebo's memory (Amendment 3): a uniform reservoir sample (Algorithm R, PLACEBO_RESERVOIR readings) of one
 *  config's real confluence readings, each with the match it came from. A reading waits in `pending` until the clock has
 *  moved past it; a draw for a match never returns one of that match's own readings. */
export class PlaceboReservoir {
  private readonly bits = new Uint8Array(PLACEBO_RESERVOIR);
  private readonly evs: string[] = [];
  private readonly per = new Map<string, number>();
  private size = 0;
  private seen = 0;
  private pending: Array<{ ts: number; event: string; bits: number }> = [];
  private head = 0;
  constructor(private readonly rnd: () => number) {}

  /** One evaluation for `event` at `now` whose real reading is `real` (bits): first the draw, then the reading is queued. */
  draw(event: string, now: number, real: number): number {
    while (this.head < this.pending.length && this.pending[this.head].ts < now) this.offer(this.pending[this.head++]);
    if (this.head > 4096 && this.head * 2 > this.pending.length) { this.pending = this.pending.slice(this.head); this.head = 0; }
    let out = 0;
    const other = this.size - (this.per.get(event) ?? 0);
    if (other > 0) {
      if (other * 64 >= this.size) {
        // Uniform over the other matches' readings by rejection (at most 64 tries expected).
        for (;;) { const i = Math.floor(this.rnd() * this.size); if (this.evs[i] !== event) { out = this.bits[i]; break; } }
      } else {
        let k = Math.floor(this.rnd() * other);
        for (let i = 0; i < this.size; i++) if (this.evs[i] !== event && k-- === 0) { out = this.bits[i]; break; }
      }
    }
    this.pending.push({ ts: now, event, bits: real });
    return out;
  }

  /** Readings in the reservoir (for tests). */
  get count(): number { return this.size; }

  private offer(x: { event: string; bits: number }): void {
    this.seen++;
    let i: number;
    if (this.size < PLACEBO_RESERVOIR) i = this.size++;
    else {
      i = Math.floor(this.rnd() * this.seen);
      if (i >= PLACEBO_RESERVOIR) return;
      const old = this.evs[i], c = (this.per.get(old) ?? 1) - 1;
      if (c > 0) this.per.set(old, c); else this.per.delete(old);
    }
    this.bits[i] = x.bits;
    this.evs[i] = x.event;
    this.per.set(x.event, (this.per.get(x.event) ?? 0) + 1);
  }
}

/** The fields the engine fills on a held market (bot/engine.ts tennisTick), plus the research loser stop's cost. */
export type HeldFields = Pick<MatchMarket, 'position' | 'avgEntry' | 'netAtBid' | 'breakEven' | 'costPer'>;

/** One config's orders, positions and per-match results. */
export class ConfigSim {
  readonly cfg: TennisConfig;
  readonly bankroll: number;
  readonly latency: number;
  readonly slipTicks: number;
  readonly offset: number;
  /** Research loser stop (HARNESS_LOSER_STOP), undefined when off. */
  readonly loserStopFrac?: number;
  readonly trackers = new Map<string, MatchTracker>();
  readonly pos = new Map<string, Pos>();
  /** Resting orders by ticker. */
  readonly resting = new Map<string, SimOrder[]>();
  pending: SimOrder[] = [];
  readonly taken = new Map<string, { taken: number; ts: number }>();
  /** Whether a held position may ride to settlement, as of the last decision (per ticker). Absent = may not. */
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
  /** The coin placebo's reservoir (placebo configs only). */
  readonly placebo?: PlaceboReservoir;
  private nextId = 1;
  private readonly beCache = new Map<string, { key: string; be: number | undefined }>();

  constructor(readonly spec: SimSpec) {
    if ('HARNESS_LOSER_CUT' in spec.overrides) throw new Error(`${spec.id}: HARNESS_LOSER_CUT no longer exists (the settle-hold stick is TENNIS_END_LOSER_CUT=false)`);
    const full = configOf(spec.overrides);
    this.cfg = full.tennis;
    this.pacerCfg = full.strategy.pacer;
    this.floorMode = full.strategy.pacer.floor;
    this.floorTicks = full.strategy.pacer.floorTicks;
    this.usePacer = String(spec.overrides.HARNESS_PACER ?? 'tennis') !== 'off' && full.strategy.pacer.enabled;
    this.feeMult = Number(spec.overrides.HARNESS_FEE_MULT ?? 1);
    const loserStop = Number(spec.overrides.HARNESS_LOSER_STOP ?? 0);
    this.loserStopFrac = loserStop > 0 ? loserStop : undefined;
    this.bankroll = Number(spec.overrides.HARNESS_BANKROLL ?? 200);
    this.latency = (spec.fill === 'F0' ? 0 : 1000) + Math.max(0, Number(spec.overrides.HARNESS_LATENCY_MS ?? 0));
    this.slipTicks = spec.fill === 'F2' ? 1 : 0;
    this.offset = Math.max(0, Math.min(DEC_MS - 1, spec.offsetMs ?? 0));
    if (spec.placebo === 'coin') this.placebo = new PlaceboReservoir(rng(hash32(spec.id)));
  }

  tracker(event: string): MatchTracker {
    let t = this.trackers.get(event);
    if (!t) {
      t = new MatchTracker(event, this.cfg);
      const res = this.placebo;
      if (res) {
        // Placebo: a whole past reading of another match replaces the real one (drawn before the real one is queued).
        t.signalHook = (sig, ticker, now) => { const b = res.draw(event, now, sigBits(sig)); this.lastSig.set(ticker, b); return sigOf(b); };
      } else {
        t.signalHook = (sig, ticker) => { this.lastSig.set(ticker, sigBits(sig)); return sig; };
      }
      this.trackers.set(event, t);
    }
    return t;
  }

  /** Anything held or working on this ticker? */
  busy(ticker: string): boolean { return this.pos.has(ticker) || (this.resting.get(ticker)?.length ?? 0) > 0 || this.pending.some((o) => o.ticker === ticker); }

  private p(ticker: string): Pos { let x = this.pos.get(ticker); if (!x) { x = { yes: 0, netCash: 0, fees: 0, lotCash: 0, lotFees: 0 }; this.pos.set(ticker, x); } return x; }

  ev(event: string): EventAcc { let e = this.events.get(event); if (!e) { e = { pnl: 0, gross: 0, fees: 0, entries: 0, traded: false, breaches: 0, legs: {}, eps: [] }; this.events.set(event, e); } return e; }

  /** The market's fees (the stress multiplier applied). */
  fees(ticker: string): FeeSchedule {
    const f = this.feeFor(ticker);
    return this.feeMult === 1 ? f : { ...f, takerMultiplier: f.takerMultiplier * this.feeMult, makerMultiplier: f.makerMultiplier * this.feeMult };
  }

  /** The profit rules for a decision at `now`, as bot/engine.ts tennisTick passes them (plus the research loser stop). */
  rulesAt(now: number): TennisProfitRules {
    let pacerUsd: number | undefined;
    if (this.usePacer) {
      this.pacer ??= new HourlyQuotaPacer(this.pacerCfg, now);
      pacerUsd = this.pacer.neededUsd(now);
    }
    return { pacerUsd, settleFrac: this.cfg.settleFrac, endLoserCut: this.cfg.endLoserCut, endEntryMargin: this.cfg.endEntryMargin, floorMode: this.floorMode, floors: this.floors, floorTicks: this.floorTicks, loserStopFrac: this.loserStopFrac };
  }

  /** A held market's fields as the engine computes them: avgEntry = -netCash/yes, netAtBid and breakEven on the round-trip
   *  cost basis (fees - netCash)/yes with this market's (stressed) fee schedule; costPer from the open lot alone, only for
   *  the research loser stop and only when positive. Undefined when flat. */
  held(ticker: string, bid: { price: number } | undefined, ask: { price: number } | undefined): HeldFields | undefined {
    const p = this.pos.get(ticker);
    const yes = p?.yes ?? 0;
    if (!p || !(yes > 0)) return undefined;
    const fees = this.fees(ticker);
    const cost = (p.fees - p.netCash) / yes;
    const key = `${yes}|${p.netCash}|${p.fees}|${fees.takerMultiplier}`;
    let be = this.beCache.get(ticker);
    if (!be || be.key !== key) { be = { key, be: breakEvenExit(yes, cost, fees) }; this.beCache.set(ticker, be); }
    const out: HeldFields = { position: yes, avgEntry: -p.netCash / yes, netAtBid: positionNetAtBid(yes, cost, bid, ask, fees), breakEven: be.be };
    if (this.loserStopFrac !== undefined) { const lot = (p.lotFees - p.lotCash) / yes; if (lot > 1e-9) out.costPer = lot; }
    return out;
  }

  /** The settlement audit at a decision: may each held market ride to settlement, by production's ride rule as of now? */
  audit(tr: MatchTracker, markets: MatchMarket[], now: number): void {
    if (!markets.some((m) => m.position > 0)) return;
    const frac = this.cfg.settleFrac;
    const prog = tr.liveSince !== undefined ? tr.progress(now, markets) : 0;
    const share = frac > 0 && prog >= 1 - frac - 1e-9;
    for (const m of markets) if (m.position > 0) this.rideOk.set(m.ticker, share && m.netAtBid !== undefined && m.netAtBid > 1e-9);
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
    const signed = o.side === 'bid' ? n : -n;
    const after = r2(before + signed);
    const opened = before <= 1e-9 && after > 1e-9, flat = before > 1e-9 && after <= 1e-9;
    if (opened) { p.lotCash = 0; p.lotFees = 0; }
    p.yes = after;
    p.netCash -= signed * price; p.lotCash -= signed * price;
    p.fees += fee; p.lotFees += fee;
    o.remaining = r2(o.remaining - n);
    // A position that opens or goes flat has no ride verdict until a decision judges it.
    if (opened || flat) this.rideOk.delete(o.ticker);
    this.pacer?.onFill({ ticker: o.ticker, side: o.side, count: n, price }, fee, p, ts);
    if (opened) this.open.set(o.ticker, { event, ticker: o.ticker, t: ts, leg: o.leg, px: price, n: p.yes, ph: this.phaseOf.get(event) ?? 'pre', sig: this.lastSig.get(o.ticker) ?? 0, base });
    else if (p.yes > 1e-9) { const op = this.open.get(o.ticker); if (op && p.yes > op.n) op.n = p.yes; }
    if (flat) { this.closeEp(o.ticker, o.leg, p.netCash - p.fees, ts, false); this.floors.forget(o.ticker); }
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

  /** Place one plan (the engine's checks, simplified: tick snapping, post-only cross, reduce-only, the market's close).
   *  `book` is the market's book only when usable (undefined: nothing is placed); `closeTime` is this market's close. */
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

  /** An order reaches the exchange: takers execute against the book now; GTC rests behind what the level shows. Without a
   *  usable book (stale, crossed, invalidated) the order is dropped: nothing is known to fill it against. */
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

  /** Pending orders whose latency has passed reach the exchange. `books(ticker, at)` gives the book only if usable at `at`. */
  activateDue(now: number, books: (t: string, at: number) => OrderBook | undefined, eventOf: (t: string) => string): void {
    if (!this.pending.length) return;
    const due = this.pending.filter((o) => o.activeTs <= now);
    if (!due.length) return;
    this.pending = this.pending.filter((o) => o.activeTs > now);
    for (const o of due) this.activate(o, books(o.ticker, o.activeTs), o.activeTs, eventOf(o.ticker));
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
    const ride = this.rideOk.get(ticker) === true;
    this.rideOk.delete(ticker);
    if (!p) return;
    const e = this.ev(event);
    const breach = p.yes > 1e-9 && !ride;
    if (breach) e.breaches++;
    const payout = result === 'yes' ? p.yes : 0;
    const realized = p.netCash + payout - p.fees;
    e.pnl += realized;
    e.gross += p.netCash + payout;
    e.fees += p.fees;
    this.pacer?.onSettled(ticker, realized, ts);
    if (p.yes > 1e-9) this.closeEp(ticker, 'settle', realized, ts, breach);
    this.pos.delete(ticker);
    this.beCache.delete(ticker);
  }

  /** Close a match into its day (an unresolved match's open positions are dropped, counted as breaches, and their realized
   *  P&L reaches the pacer as a settlement would). */
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
        this.pacer?.onSettled(t, p.netCash - p.fees, ts);
        this.pos.delete(t);
      }
      this.open.delete(t);
      this.rideOk.delete(t);
      this.lastSig.delete(t);
      this.beCache.delete(t);
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

const TICKER_RE = /"ticker":"([^"]+)"/;
const LINE_HEAD = /^\{"t":(-?\d+(?:\.\d+)?),"k":"([a-z_]+)"/;
/** Is a ticker's series a match series (cached per series)? */
function matchSeriesTest(): (ticker: string) => boolean {
  const kindOf = new Map<string, boolean>();
  return (t) => { const s = t.slice(0, Math.max(0, t.indexOf('-'))); let k = kindOf.get(s); if (k === undefined) { k = contractKind(s) === 'match'; kindOf.set(s, k); } return k; };
}

/** The lines a tennis sweep reads: match markets, their books, deltas, trades, results and lifecycle lines, alive marks and
 *  scores. A book, delta or trade line at or after `lostFrom` of a tennis match ticker whose market line was never read
 *  goes into `lost` (earlier lines belong to matches that began before the owned span: a lookback read meets those). */
export function tennisOnly(lost?: Set<string>, lostFrom = -Infinity): LineFilter {
  const matches = new Set<string>();
  const isMatchSeries = matchSeriesTest();
  return (k, line) => {
    switch (k) {
      case 'market':
        try { const m = JSON.parse(line); if ((m.kind ?? contractKind(m.series ?? '')) === 'match') { matches.add(m.ticker); return true; } } catch { /* torn line */ }
        return false;
      case 'book': case 'delta': case 'trade': case 'result': case 'lifecycle': {
        const t = TICKER_RE.exec(line)?.[1] ?? '';
        if (matches.has(t)) return true;
        if (lost && k !== 'result' && k !== 'lifecycle' && t && !lost.has(t) && isMatchSeries(t) && Number(LINE_HEAD.exec(line)?.[1] ?? NaN) >= lostFrom) lost.add(t);
        return false;
      }
      case 'alive': case 'tennis_score':
        return true;
      default:
        return false;
    }
  };
}

/** An outage of the recorded feed: books are marked alive only up to `from` + FEED_SILENCE_MS and are invalidated at
 *  `to` (the line that ended it). `blind`: a silence of tennis lines on a blind day, an outage by the resubscribe after it. */
export interface FeedGap { from: number; to: number; blind: boolean }
export interface FeedTimeline {
  /** Outages in time order (they never overlap). */
  gaps: FeedGap[];
  /** Day files that show the feed's liveness (heartbeat lines, or the socket's lines of non-tennis markets), and the blind
   *  ones (tennis lines only: a silence is an outage only when a resubscribe ends it). */
  liveDays: string[];
  blindDays: string[];
}

/** R: the recorded feed's outages over the day files [fromDay, toDay] (see the header: recorded books). The socket's
 *  lines are book, delta, trade and lifecycle lines of any market, plus heartbeat lines; nothing else (market lines come
 *  from REST polls, scores from another feed) proves the socket was up. */
export async function feedTimeline(dir: string, fromDay: string, toDay: string): Promise<FeedTimeline> {
  const files = recordingFiles(dir).filter((f) => f.day >= fromDay && f.day <= toDay);
  const isMatchSeries = matchSeriesTest();
  const liveDays = new Set<string>(), blindDays: string[] = [];
  const snapped = new Set<string>();
  type Cand = { from: number; to: number; fromDay: string; toDay: string; known: number; resynced?: Set<string> };
  const cands: Cand[] = [];
  let last = -Infinity, lastDay = '';
  for (const f of files) {
    let live = false;
    for await (const line of recordingLines(f.file)) {
      const h = LINE_HEAD.exec(line);
      if (!h) continue;
      const k = h[2];
      let ticker = '';
      if (k === HEARTBEAT_KIND) live = true;
      else if (k === 'book' || k === 'delta' || k === 'trade' || k === 'lifecycle') {
        ticker = TICKER_RE.exec(line)?.[1] ?? '';
        if (!isMatchSeries(ticker)) live = true;
      } else continue;
      const t = Number(h[1]);
      if (t - last > FEED_SILENCE_MS && Number.isFinite(last)) cands.push({ from: last, to: t, fromDay: lastDay, toDay: f.day, known: snapped.size });
      if (k === 'book') {
        // A snapshot of a book already snapshotted: a resubscribe (Kalshi snapshots only on subscribe).
        const c = cands[cands.length - 1];
        if (c && t <= c.to + RESYNC_WINDOW_MS && snapped.has(ticker)) (c.resynced ??= new Set()).add(ticker);
        snapped.add(ticker);
      }
      if (t > last) { last = t; lastDay = f.day; }
    }
    if (live) liveDays.add(f.day); else blindDays.push(f.day);
  }
  const gaps: FeedGap[] = [];
  for (const c of cands) {
    // A resubscribe re-snapshots every subscribed book; one book alone is a sequence-gap resnapshot, not an outage.
    if (liveDays.has(c.fromDay) && liveDays.has(c.toDay)) gaps.push({ from: c.from, to: c.to, blind: false });
    else if (c.known > 0 && (c.resynced?.size ?? 0) >= Math.min(2, c.known)) gaps.push({ from: c.from, to: c.to, blind: true });
  }
  return { gaps, liveDays: [...liveDays], blindDays };
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
    const closeIdx = Math.max(0, Math.min(this.n - 1, Math.floor((ev.closeMin - this.t0) / 1000)));
    const g: MatchGrid & { startPublished?: boolean } = { event: ev.event, series: ev.series, stratum, tickers: [ev.tickers[0], ev.tickers[1]], start: ev.start, startPublished: ev.startPublished, day: ev.day, t0: this.t0, n: this.n,
      bidA: f(0), askA: f(1), bidB: f(2), askB: f(3), yesVolA: f(4), noVolA: f(5), yesVolB: f(6), noVolB: f(7), imbA: f(8), imbB: f(9),
      progress: Float64Array.from(this.prog), liveIdx: this.liveIdx, resultA, closeIdx };
    return g;
  }
}

interface LiveEvent {
  event: string; tickers: string[]; day: string; series: string;
  /** Ownership, day and unit key: the published start (the strategy's, below), else the first market line's time. A
   *  published start that arrives with a later market line, or moves, re-keys the match while it has not begun by
   *  either start; after that the key is fixed. */
  start: number; startPublished: boolean;
  /** The published start as the strategy gets it (production: the first of the event's markets, by ticker, that has one). */
  startTime?: number;
  /** Earliest market close (the strategy's closeTime, the decision stop) and latest (how long to wait for settlement). */
  closeMin: number; closeMax: number;
  owned: boolean; done: boolean;
  /** Prints seen on its markets (0 = no tape: excluded from the history universe by the report). */
  trades: number;
  /** Settled markets (the first result or settling lifecycle line of each). */
  results: Map<string, 'yes' | 'no'>;
  grid?: GridBuilder;
  /** A production-default tracker: the grid's progress clock and the phase labels. */
  clock: MatchTracker;
}

export interface SweepOpts {
  dir: string;
  /** Owned matches start in [fromDay 00:00 UTC, toDay 00:00 UTC) and pass admit(); the reader goes on to the end of toDay
   *  so late matches finish. */
  fromDay: string;
  toDay: string;
  stratum: 'H' | 'R';
  specs: SimSpec[];
  /** Pool membership on top of [fromDay, toDay): the slice's units, sealed / dev units, the lockbox exclusion, the hard
   *  cutoff. Asked again with the later close if a later market line of the match raises it, and with the new start when
   *  a later market line re-keys it (see MatchInfo.start). */
  admit?: (m: { event: string; series: string; start: number; closeTime: number }) => boolean;
  /** Fee schedule of a series at a time (fee changes); FEES when unset. */
  feeAt?: (series: string, t: number) => FeeSchedule;
  /** Every completed two-market match grid with market A's result, in non-decreasing day order (family B). A day is
   *  released once it is over and no owned match of that day or earlier is still live, or 36 h after it ended; a grid
   *  that finishes after its day was released is not delivered (SweepResult.lateGrids). */
  onGrid?: (g: MatchGrid) => void;
  log?: (m: string) => void;
  /** R: days before fromDay that are read too (from their start), so a match the bot listed up to 36 h before its start
   *  keeps its market line and its book snapshots (default 7). H reads one day before fromDay (history lists a match
   *  30 min before its start). */
  lookbackDays?: number;
}

export interface SweepResult {
  runs: SimRun[]; matchList: MatchInfo[]; matches: number; oneLegged: number; unresolved: number; events: number; decisions: number; ms: number;
  /** R: feed outages (feedTimeline) and their total length; those found on blind days by the resubscribe that ended them. */
  gaps: number; gapMs: number; blindGaps: number;
  /** R: day files read that show the feed's liveness, and blind ones (no heartbeat: tennis silences are not judged). */
  liveDays: number; blindDays: number;
  /** Tennis match tickers with book, delta or trade lines at or after fromDay but no market line in what was read (an
   *  owned match may be lost; a match begun before fromDay that has no market line in the read counts too). */
  lost: number;
  /** Grids not delivered to onGrid because their day had already been released (a match live over 36 h past its day). */
  lateGrids: number;
}

/** Phase label of a match from its clock: pre, e20 (first 20 min live), then the in-play progress tercile. */
export function phaseLabel(liveSince: number | undefined, now: number, progress: number): string {
  if (liveSince === undefined) return 'pre';
  if (now - liveSince < 20 * 60_000) return 'e20';
  return progress < 1 / 3 ? 'p1' : progress < 2 / 3 ? 'p2' : 'p3';
}

/** Run every spec over the owned matches of [fromDay, toDay). */
export async function runSweep(o: SweepOpts): Promise<SweepResult> {
  const t0 = Date.now();
  const log = o.log ?? (() => {});
  const ownFrom = Date.parse(o.fromDay), ownTo = Date.parse(o.toDay);
  if (!(ownTo > ownFrom)) throw new Error(`runSweep: toDay ${o.toDay} must be after fromDay ${o.fromDay} (owned starts are [fromDay, toDay))`);
  const lookback = o.stratum === 'R' ? Math.max(1, Math.ceil(o.lookbackDays ?? 7)) : 1;
  const readFrom = dayOf(ownFrom - lookback * DAY), readTo = o.toDay;
  const st = new ReplayState();
  const sims = o.specs.map((s) => new ConfigSim(s));
  const phaseOf = new Map<string, string>();
  const seriesOf = new Map<string, string>();
  const feeFor = (ticker: string) => (o.feeAt ? o.feeAt(seriesOf.get(ticker) ?? '', st.now) : FEES);
  for (const sim of sims) { sim.phaseOf = phaseOf; sim.feeFor = feeFor; }
  const matchList: MatchInfo[] = [];
  const full = configOf({});
  const defaultCfg = full.tennis;
  const bookAgeMs = full.risk.maxBookAgeMs;
  const live = new Map<string, LiveEvent>();
  const finished = new Set<string>();
  const evOfTicker = new Map<string, string>();
  // One decision clock per phase offset (production: one clock, every 5 s); offset 0 always runs, for the progress clock.
  const offsets = [...new Set([0, ...sims.map((s) => s.offset)])].sort((a, b) => a - b);
  const clocks = offsets.map((off) => ({ off, next: Infinity, sims: sims.filter((s) => s.offset === off) }));
  let nextSec = Infinity;
  let matches = 0, oneLegged = 0, unresolvedN = 0, events = 0, decisions = 0, liveOwned = 0, gaps = 0, gapMs = 0, blindGaps = 0, lateGrids = 0;
  const lost = new Set<string>();
  const gridQueue: MatchGrid[] = [];
  let releasedDay: string | undefined;
  // R: the feed's outages, rebuilt from the same files before the replay, and the alive mark set on each book.
  const feed = o.stratum === 'R' ? await feedTimeline(o.dir, readFrom, readTo) : undefined;
  const outages = feed?.gaps ?? [];
  let nextOutage = 0;
  /** The start of the outage `now` falls in (from < now <= to: its last tick still meets the books before it ends). */
  const outageAt = (now: number): number | undefined => {
    let lo = 0, hi = outages.length - 1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1, g = outages[mid];
      if (now <= g.from) hi = mid - 1; else if (now > g.to) lo = mid + 1; else return g.from;
    }
    return undefined;
  };
  const marks = new WeakMap<OrderBook, number>();
  const isUsable = (b: OrderBook | undefined, now: number) => {
    if (!b) return false;
    if (o.stratum === 'R') {
      // Production's alive timer: each second while the socket has had a message within 12 s (bot/marketdata/marketData.ts).
      const from = outageAt(now);
      const m = from === undefined ? now : Math.min(now, from + FEED_SILENCE_MS);
      if (m > (marks.get(b) ?? -Infinity)) { b.markAlive(m); marks.set(b, m); }
    }
    return b.isUsable(now, bookAgeMs);
  };
  const usableBook = (t: string, at: number) => { const b = st.books.get(t); return isUsable(b, at) ? b : undefined; };
  const eventOf = (t: string) => evOfTicker.get(t) ?? t.slice(0, t.lastIndexOf('-'));
  const closeOf = (t: string, ev: LiveEvent) => st.markets.get(t)?.closeTime ?? ev.closeMin;

  const releaseGrids = (now: number) => {
    if (!o.onGrid || !gridQueue.length) return;
    gridQueue.sort((a, b) => a.day.localeCompare(b.day) || a.start - b.start);
    // The earliest day of an owned match still live (its grid would come later).
    let liveDay: string | undefined;
    for (const ev of live.values()) if (ev.owned && !ev.done && ev.grid && (liveDay === undefined || ev.day < liveDay)) liveDay = ev.day;
    // A day is released once it is over and no owned match of that day or earlier is live, or 36 h after it ended.
    while (gridQueue.length) {
      const d = gridQueue[0].day, end = Date.parse(d) + DAY;
      if (!(now >= end + 36 * 3_600_000 || (now >= end && !(liveDay !== undefined && liveDay <= d)))) break;
      releasedDay = d;
      o.onGrid(gridQueue.shift()!);
    }
  };
  /** Queue a finished grid; one whose day was already released would break the day order and is counted instead. */
  const queueGrid = (g: MatchGrid) => {
    if (releasedDay !== undefined && g.day < releasedDay) { lateGrids++; return; }
    gridQueue.push(g);
  };

  const flowOf = (ticker: string, now: number, windowSec: number): number | undefined => {
    const tr = st.features.micro.get(ticker)?.tradesIn(now, windowSec * 1000) ?? [];
    let tot = 0, sig = 0;
    for (const x of tr) { tot += x.count; sig += x.signed; }
    return tot > 0 ? sig / tot : undefined;
  };

  const decide = (now: number, cl: { off: number; sims: ConfigSim[] }) => {
    for (const ev of live.values()) {
      // A match stops at its earliest close, or once a market settled (the match is decided).
      if (!ev.owned || ev.done || now >= ev.closeMin || ev.results.size) continue;
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
      const startTime = ev.startTime;
      if (cl.off === 0) {
        ev.clock.observe({ event: ev.event, now, startTime, markets: plain, closeTime: ev.closeMin, score });
        const prog = ev.clock.liveSince !== undefined ? ev.clock.progress(now, plain) : 0;
        phaseOf.set(ev.event, phaseLabel(ev.clock.liveSince, now, prog));
        if (ev.grid) { ev.grid.progress = prog; if (ev.grid.liveIdx < 0 && ev.clock.liveSince !== undefined) ev.grid.liveIdx = Math.max(0, ev.grid.n - 1); }
      }
      if (!cl.sims.length) continue;
      const tick = st.markets.get(ev.tickers[0])?.tickSize ?? 0.01;
      const flows = new Map<number, Array<number | undefined>>();
      for (const sim of cl.sims) {
        const w = sim.cfg.confWindowSec;
        let fl = flows.get(w);
        if (!fl) { fl = ev.tickers.map((t) => flowOf(t, now, w)); flows.set(w, fl); }
        const markets: MatchMarket[] = base.map((x, i) => {
          const h = sim.held(x.t, x.bb, x.ba);
          return h ? { ...plain[i], flow: fl![i], ...h } : { ...plain[i], flow: fl![i] };
        });
        const held = sim.tickers();
        const tennisRisk = held.length ? held.reduce((s, t) => s + sim.worst(t), 0) : 0;
        const matchRisk = held.length ? ev.tickers.reduce((s, t) => s + (held.includes(t) ? sim.worst(t) : 0), 0) : 0;
        const tr = sim.tracker(ev.event);
        const out = decideMatch(tr, { event: ev.event, now, startTime, markets, closeTime: ev.closeMin, score }, sim.cfg, { bankroll: sim.bankroll, tennisRisk, matchRisk }, tick, sim.rulesAt(now));
        decisions++;
        // The settlement audit: may each held position ride, by production's ride rule as of now?
        sim.audit(tr, markets, now);
        if (!out.plans.length && !held.some((t) => ev.tickers.includes(t))) continue;
        // Order sync (bot/engine.ts): cancel resting orders no longer planned, place the new ones.
        const same = (p: TennisPlan, x: SimOrder) => p.ticker === x.ticker && p.side === x.side && Math.abs(p.price - x.price) < 1e-9 && Math.abs(p.count - x.remaining) < 0.01 + 1e-9;
        for (const t of ev.tickers) sim.cancel(t, (x) => out.plans.some((p) => same(p, x)));
        for (const p of out.plans) {
          if ((sim.resting.get(p.ticker) ?? []).some((x) => same(p, x)) || sim.pending.some((x) => same(p, x))) continue;
          if (ev.results.has(p.ticker)) continue;
          sim.place(p, usableBook(p.ticker, now), now, closeOf(p.ticker, ev), ev.event, tick);
        }
      }
    }
  };

  const sampleGrids = (t: number) => {
    for (const ev of live.values()) {
      if (!ev.owned || ev.done || !ev.grid || ev.tickers.length < 2 || t > ev.closeMax) continue;
      if (ev.startTime !== undefined && t < ev.startTime - GRID_PRE_MS) continue;
      ev.grid.sample(t, [st.books.get(ev.tickers[0]), st.books.get(ev.tickers[1])], (b) => isUsable(b, t));
    }
  };

  const finishEvent = (ev: LiveEvent, unresolved: boolean, ts: number) => {
    if (ev.done) return;
    ev.done = true;
    finished.add(ev.event);
    if (ev.owned) {
      liveOwned--;
      matches++;
      if (ev.tickers.length < 2) oneLegged++;
      if (unresolved) unresolvedN++;
      for (const sim of sims) sim.finish(ev.event, ev.tickers, ev.day, unresolved, ts);
      const rA = ev.results.get(ev.tickers[0]);
      matchList.push({ event: ev.event, series: ev.series, day: ev.day, start: ev.start, startPublished: ev.startPublished, close: ev.closeMax, tickers: ev.tickers, trades: ev.trades, unresolved, ...(rA ? { resultA: rA === 'yes' ? 1 as const : 0 as const } : {}) });
      if (ev.grid && ev.tickers.length >= 2 && rA && ev.grid.n > 0) queueGrid(ev.grid.build(ev, o.stratum, rA === 'yes' ? 1 : 0));
    } else {
      // Not owned (outside the slice, or out of the pool): configs never traded it; drop any state.
      for (const sim of sims) sim.finish(ev.event, ev.tickers, ev.day, unresolved, ts, false);
    }
    phaseOf.delete(ev.event);
    for (const t of ev.tickers) { st.forget(t); st.results.delete(t); evOfTicker.delete(t); seriesOf.delete(t); }
    live.delete(ev.event);
  };

  /** Does a match with this start and close belong to the slice? */
  const ownable = (event: string, series: string, start: number, closeTime: number) =>
    start >= ownFrom && start < ownTo && (o.admit?.({ event, series, start, closeTime }) ?? true);
  /** A match joins the slice (when it is listed, or re-keyed into it); the clocks start with the first live one. */
  const own = (ev: LiveEvent, ts: number) => {
    if (ev.owned) return;
    ev.owned = true;
    ev.grid = o.onGrid ? new GridBuilder() : undefined;
    if (liveOwned === 0) {
      for (const c of clocks) c.next = Math.ceil((ts - c.off) / DEC_MS) * DEC_MS + c.off;
      nextSec = Math.ceil(ts / 1000) * 1000;
    }
    liveOwned++;
  };
  /** A match leaves the pool after all (a later market line raised its close past what admit() takes, or re-keyed it). */
  const disown = (ev: LiveEvent, ts: number) => {
    if (!ev.owned) return;
    ev.owned = false;
    ev.grid = undefined;
    liveOwned--;
    for (const sim of sims) sim.finish(ev.event, ev.tickers, ev.day, false, ts, false);
  };

  for await (const e of readRecordings(o.dir, '', readFrom, readTo, tennisOnly(lost, ownFrom)) as AsyncIterable<RecEvent>) {
    // Clocks up to this line: grid seconds, then each decision clock (orders that came due reach the exchange first).
    if (liveOwned > 0) {
      for (;;) {
        let cl = clocks[0];
        for (const c of clocks) if (c.next < cl.next) cl = c;
        const tDec = cl.next;
        if (Math.min(tDec, nextSec) > e.t) break;
        if (nextSec <= tDec) { sampleGrids(nextSec); nextSec += 1000; continue; }
        for (const sim of cl.sims) { sim.activateDue(tDec, usableBook, eventOf); sim.expire(tDec); }
        decide(tDec, cl);
        cl.next += DEC_MS;
      }
    }
    // Orders acting by now meet the books as they stood before this line (and before an outage it ends is read).
    for (const sim of sims) sim.activateDue(e.t, usableBook, eventOf);
    // An outage of the feed ends here: every book needs a new snapshot.
    while (nextOutage < outages.length && outages[nextOutage].to <= e.t) {
      const g = outages[nextOutage++];
      gaps++; gapMs += g.to - g.from;
      if (g.blind) blindGaps++;
      for (const b of st.books.values()) b.invalidate();
    }
    if (e.k === 'skip') continue;
    st.apply(e);
    events++;
    switch (e.k) {
      case 'market': {
        const m = st.markets.get(e.ticker);
        if (!m || m.kind !== 'match') break;
        const event = m.event ?? e.ticker.slice(0, e.ticker.lastIndexOf('-'));
        if (finished.has(event)) break; // a market line written again after the match was over (a restart)
        evOfTicker.set(e.ticker, event);
        seriesOf.set(e.ticker, m.series);
        let ev = live.get(event);
        if (!ev) {
          const start = m.startTime ?? e.t;
          ev = { event, tickers: [], day: dayOf(start), start, startPublished: m.startTime !== undefined, closeMin: m.closeTime, closeMax: m.closeTime, series: m.series, owned: false, done: false, trades: 0, results: new Map(),
            clock: new MatchTracker(event, defaultCfg) };
          live.set(event, ev);
          if (ownable(event, m.series, start, m.closeTime)) own(ev, e.t);
        }
        if (!ev.tickers.includes(e.ticker)) { ev.tickers.push(e.ticker); ev.tickers.sort(); }
        // Production reads the event's markets as they stand: the first (by ticker) with a start, the earliest close.
        const ms = ev.tickers.map((t) => st.markets.get(t)).filter((x): x is NonNullable<typeof x> => x !== undefined);
        ev.startTime = ms.find((x) => x.startTime)?.startTime;
        ev.closeMin = Math.min(...ms.map((x) => x.closeTime));
        const closeMax = Math.max(ev.closeMax, ...ms.map((x) => x.closeTime));
        const grew = closeMax > ev.closeMax;
        ev.closeMax = closeMax;
        // The published start came with a later line (a sibling market's), or moved: the match is re-keyed (start, day,
        // unit, ownership) while it has begun by neither start; after that its key is fixed.
        const pub = ev.startTime;
        const rekey = pub !== undefined && (!ev.startPublished || pub !== ev.start) && e.t < pub && (!ev.startPublished || e.t < ev.start);
        if (rekey) { ev.start = pub; ev.startPublished = true; ev.day = dayOf(pub); }
        if (rekey || (grew && ev.owned)) {
          const want = ownable(event, ev.series, ev.start, ev.closeMax);
          if (ev.owned && !want) disown(ev, e.t);
          else if (!ev.owned && want) own(ev, e.t);
          // Still owned with a new start: its grid starts over, as a match listed with that start would have it.
          else if (ev.owned && rekey && ev.grid && ev.grid.n > 0 && ev.clock.liveSince === undefined) ev.grid = new GridBuilder();
        }
        break;
      }
      case 'trade': {
        const ev = live.get(evOfTicker.get(e.ticker) ?? '');
        if (!ev?.owned || ev.done) break;
        ev.trades++;
        const ts = e.ts ?? e.t;
        if (!ev.results.has(e.ticker)) for (const sim of sims) sim.onTrade(e.ticker, e.price, e.count, e.takerSide, ts, ev.event);
        if (ev.grid) { const i = ev.tickers.indexOf(e.ticker); if (i === 0 || i === 1) ev.grid.vol[i * 2 + (e.takerSide === 'yes' ? 0 : 1)] += e.count; }
        break;
      }
      case 'result': case 'lifecycle': {
        // Settlement: a result line, or Kalshi's lifecycle line once the market is determined or settled; the first counts.
        if (e.result !== 'yes' && e.result !== 'no') break;
        if (e.k === 'lifecycle' && !SETTLING.test(String(e.event ?? ''))) break;
        const ev = live.get(evOfTicker.get(e.ticker) ?? '');
        if (!ev || ev.done || ev.results.has(e.ticker)) break;
        ev.results.set(e.ticker, e.result);
        if (ev.owned) for (const sim of sims) sim.settle(e.ticker, e.result, ev.event, e.t);
        if (ev.tickers.every((t) => ev.results.has(t))) finishEvent(ev, false, e.t);
        break;
      }
      default:
        break;
    }
    if (events % 20_000 === 0) {
      // A match long past its close without a result is finished as unresolved (its open positions counted).
      for (const ev of [...live.values()]) if (e.t > ev.closeMax + 2 * DAY) finishEvent(ev, true, e.t);
      releaseGrids(e.t);
    }
  }
  for (const ev of [...live.values()]) finishEvent(ev, true, st.now);
  if (o.onGrid) { gridQueue.sort((a, b) => a.day.localeCompare(b.day) || a.start - b.start); for (const g of gridQueue.splice(0)) o.onGrid(g); }
  if (lost.size) log(`sweep ${o.fromDay}..${o.toDay}: ${lost.size} tennis match tickers had book or trade lines from ${o.fromDay} on but no market line in what was read (lost)`);
  if (lateGrids) log(`sweep ${o.fromDay}..${o.toDay}: ${lateGrids} match grids finished after their day was released (not given to family B)`);
  if (feed?.blindDays.length) log(`sweep ${o.fromDay}..${o.toDay}: ${feed.blindDays.length} of ${feed.blindDays.length + feed.liveDays.length} recorded days carry no heartbeat: tennis silences there are outages only when a resubscribe ends them`);
  log(`sweep ${o.fromDay}..${o.toDay} (${o.stratum}): ${matches} matches (${oneLegged} one-legged, ${unresolvedN} unresolved, ${matchList.filter((m) => !m.startPublished).length} without a published start), ${o.specs.length} configs, ${decisions} decisions${o.stratum === 'R' ? `, ${gaps} feed outages (${(gapMs / 60_000).toFixed(0)} min, ${blindGaps} on blind days)` : ''}, ${((Date.now() - t0) / 1000).toFixed(0)} s`);
  return { runs: sims.map((s) => s.run(o.stratum)), matchList, matches, oneLegged, unresolved: unresolvedN, events, decisions, ms: Date.now() - t0, gaps, gapMs, blindGaps,
    liveDays: feed?.liveDays.length ?? 0, blindDays: feed?.blindDays.length ?? 0, lost: lost.size, lateGrids };
}
