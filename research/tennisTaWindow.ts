// Steven's one test for tennis (preregistration Amendment 4, /mnt/project-files/tennis-ta/preregistration.md): can a hot
// spot detect direction, sustaining long enough for an exit to take place in profit? A signal instance is a taker buy of
// the called market at its ask then, C = max(1, floor($10 / ask)) contracts; its level L is the smallest whole cent at which
// a taker sale of the C contracts returns the entry, both taker fees and one cent a contract; its window is the first
// one-minute candle of that market ending after the entry, at or before the match's end rule (production's latched
// progress reaching 1 - 0.30, else the close), whose lowest YES bid is at or above L on a two-sided book. Every instance
// gets three twins: entries at random eligible minutes of the same match in the same UTC clock hour (the whole eligible
// span when that hour holds fewer than 5), on a side drawn by a fair coin, bought at the candle's close ask, judged by the
// same rule. gap = window rate - twin rate, with a cluster-robust (by match) standard error; PASS = gap >= 2 SE.
//
// This module is the core the sweep (research/tennisTaSim.ts, family A), the signal study (research/tennisTaSignals.ts,
// family B) and the report (research/tennis_ta_report.py) share: the candle view, the level, the window rule, the twins,
// the per-row aggregate (contract C12 of the shard file) and the one test's arithmetic (gapStats). It imports nothing of
// the sim (the sim imports it), so the sim's seed helpers are copied here and pinned by a test.
//
// Shard row shape (contract C12, 'window' block of a shard file; family B rows under 'familyBWindow'):
//   { id, leg?, n[], w[], tn[], tw[] (per event index), hist { tWin[], lenWin[], dip[], held[] } (counts per HIST_EDGES
//     bin), byPhase { pre, e20, p1, p2, p3: [n, w] }, endNoWin, asks: [n, sumAsk] }

import { takerFee, type FeeSchedule } from '../bot/fees';
import type { KalshiCandle } from './history/kalshiHistory';

export const WINDOW_VERSION = 'tennis-ta-window/1';
/** The end rule's settle fraction: the end rule fires when production's latched progress reaches 1 - SETTLE_FRAC. */
export const SETTLE_FRAC = 0.30;
/** Dollars of each instance (C = max(1, floor(ORDER_USD / ask)) contracts). */
export const ORDER_USD = 10;
/** Twins drawn per instance. */
export const TWINS = 3;
/** A clock hour with fewer eligible minutes than this gives its twins the whole eligible span of the match. */
export const TWIN_HOUR_MIN = 5;
/** The twins' eligible ask band. */
export const TWIN_ASK_LO = 0.05;
export const TWIN_ASK_HI = 0.95;
/** The twins' base seed; must equal research/tennisTaSim.ts PLACEBO_SEED (tests/tennisTaWindow.test.ts asserts it). */
export const PLACEBO_SEED = 20261105;
/** The tennis fee schedule of the one test: taker multiplier 1, each fee rounded up to the cent (bot/fees.ts takerFee with
 *  a 0.01 balance grid, whatever KALSHI_BALANCE_PRECISION says). makerMultiplier 1 as research/tennisTaSim.ts FEES. */
export const WINDOW_FEES: FeeSchedule = { takerMultiplier: 1, makerMultiplier: 1, balancePrecision: 0.01 };

/** Histogram edges of the row's hist counts. Bins of an ascending list (tWin, lenWin, held): [< e0, [e0, e1), ..., >= last],
 *  i.e. bin k holds e(k-1) <= v < e(k). dip's edges run downward (a dip is the lowest bid minus the entry ask, 0 or
 *  negative nearly always), and its bins are the same rule applied to -v and -edges: bin 0 holds dip > 0 (the bid never
 *  went below the entry ask), bin 1 holds -0.01 < dip <= 0, bin 2 holds -0.02 < dip <= -0.01, ..., the last holds
 *  dip <= -0.20. histBin computes the index; a NaN (an instance without a candle) is in no bin. */
export const HIST_EDGES: { tWin: number[]; lenWin: number[]; dip: number[]; held: number[] } = {
  tWin: [1, 2, 3, 5, 10, 15, 30, 60, 120],
  lenWin: [1, 2, 3, 5, 10, 20, 40],
  dip: [0, -0.01, -0.02, -0.03, -0.05, -0.08, -0.12, -0.20],
  held: [0, 1, 2, 5, 10, 20, 40, 80],
};

const MIN = 60_000;
const HOUR = 3_600_000;
/** Tolerance of the whole-cent and whole-minute comparisons (prices are parsed decimals, times are exact). */
const EPS = 1e-9;

// ---- Seeds: copies of research/tennisTaSim.ts rng / hash32 ----------------------------------------------------------
// The sim imports this module, so they cannot be imported from there. They MUST stay identical to the sim's (the twins'
// seeds are preregistered as hash32(event | config | leg | entry minute) with PLACEBO_SEED, the same hash the coin placebo
// uses); tests/tennisTaWindow.test.ts asserts equality with the sim's exports.

/** Seeded RNG (mulberry32). */
export function rng(seed: number): () => number {
  let a = seed >>> 0;
  return () => { a = (a + 0x6d2b79f5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}
/** FNV-1a string hash for seeds. */
export function hash32(s: string): number { let h = 2166136261; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return h >>> 0; }
/** The twins' seed of one instance: PLACEBO_SEED combined with hash32(seedKey) the way the coin placebo combines its spec id
 *  (research/tennisTaSim.ts: rng((PLACEBO_SEED ^ hash32(spec.id)) >>> 0)). seedKey = `${event}|${config}|${leg}|${entry minute}`. */
export function twinSeed(seedKey: string): number { return (PLACEBO_SEED ^ hash32(seedKey)) >>> 0; }

// ---- Candles ---------------------------------------------------------------------------------------------------------

/** One Kalshi minute of a market, as the window rule reads it. */
export interface MinuteCandle {
  /** END of the minute, ms. */
  ts: number;
  /** The minute's lowest YES bid, dollars (Amendment 4 item 4). Kalshi's history stores the low (kalshiHistory.ts
   *  parseCandle); when a stored candle has no low but a close (the test fixtures store closes only) the close stands in,
   *  which can only overstate the low (close >= low) and so the window rate, and minuteCandles counts the substitution in
   *  the MinuteCandleStats it is handed so a run can refuse or print it. NaN when neither is stored (never a window, in no
   *  dip). */
  bidL: number;
  /** The minute's closing YES bid and ask, dollars (NaN when not stored). */
  bidC: number;
  askC: number;
  /** The closing book is two-sided: 0 < bidC < askC < 1. A minute that is not is never a window nor an eligible twin minute. */
  twoSided: boolean;
}
/** A market's minutes sorted by ts, the first stored candle dropped (research/history/historyReplay.ts skips the market's
 *  first candle: its quote is the listing's, before anyone traded), ending at or before the market's close only. */
export type MinuteCandles = MinuteCandle[];

/** What minuteCandles did with the stored candles it was handed, added to by every call that gets the same accumulator (a
 *  run's candle index passes one for all its markets): `candles` = minutes kept; `noLow` = kept minutes whose low was not
 *  stored and whose close stood in for it (0 on Kalshi's own history, which stores the low; every minute of a closes-only
 *  fixture). A scored run with noLow > 0 judged some windows on closes, not lows: the sweep writes the count to the shard
 *  meta and the report refuses or prints it. The core only makes it countable. */
export interface MinuteCandleStats { candles: number; noLow: number }
export const newMinuteCandleStats = (): MinuteCandleStats => ({ candles: 0, noLow: 0 });

/** The window rule's view of a market's stored candles (research/history/kalshiHistory.ts KalshiCandle, ts = the minute's
 *  END): the first stored candle dropped as historyReplay drops it (candles[0] of the stored order), candles ending after
 *  closeTime dropped, the rest sorted by ts. `stats`, when passed, counts the minutes kept and those whose low the close
 *  stood in for (MinuteCandleStats). */
export function minuteCandles(candles: KalshiCandle[], closeTime: number, stats?: MinuteCandleStats): MinuteCandles {
  const out: MinuteCandle[] = [];
  for (let i = 1; i < candles.length; i++) {
    const c = candles[i];
    if (!Number.isFinite(c.ts) || !(c.ts <= closeTime)) continue;
    const bidC = c.bidC ?? NaN, askC = c.askC ?? NaN;
    const lowStored = typeof c.bidL === 'number';
    const bidL = typeof c.bidL === 'number' ? c.bidL : bidC;
    if (stats) { stats.candles++; if (!lowStored && Number.isFinite(bidC)) stats.noLow++; }
    out.push({ ts: c.ts, bidL, bidC, askC, twoSided: bidC > 0 && askC > bidC && askC < 1 });
  }
  out.sort((a, b) => a.ts - b.ts);
  return out;
}

// ---- The instance: contracts and the level ---------------------------------------------------------------------------

/** Contracts of an instance: max(1, floor(orderUsd / ask)). Asks are whole cents, so the quotient is either a whole number or
 *  at least 1/99 away from one; the epsilon only absorbs the division's rounding. */
export function contractsFor(ask: number, orderUsd = ORDER_USD): number {
  if (!(ask > 0) || !(orderUsd > 0)) return 1;
  return Math.max(1, Math.floor(orderUsd / ask + EPS));
}

/** The level (Amendment 4 item 3), whole-cent dollars: the smallest whole cent L with
 *    L x C - takerFee(C, L) >= ask x C + takerFee(C, ask) + 0.01 x C
 *  (the entry, both taker fees, and one cent a contract), fees by bot/fees.ts takerFee on the tennis schedule, each rounded
 *  up to the cent. Computed in whole cents. A level above 0.99 can never be reached by a YES bid: such an instance (an ask
 *  of 0.98 or 0.99) never has a window, which is the rule's own verdict, not a hole. */
export function levelFor(ask: number, C: number, fees?: FeeSchedule): number {
  const f: FeeSchedule = { balancePrecision: 0.01, ...(fees ?? WINDOW_FEES) };
  const cents = (d: number) => Math.round(d * 100);
  const askc = cents(ask);
  const cost = askc * C + cents(takerFee(C, askc / 100, f)) + C;
  for (let lc = Math.max(1, askc); lc <= 10_000; lc++) if (lc * C - cents(takerFee(C, lc / 100, f)) >= cost) return lc / 100;
  throw new Error(`tennisTaWindow: no level for ask ${ask} x ${C}`);
}

// ---- The window ------------------------------------------------------------------------------------------------------

/** What became of one entry (an instance or a twin) under the window rule. The horizon is the market's minutes ending after
 *  the entry and at or before the end rule (and so at or before the close: MinuteCandles end there). */
export interface WindowOutcome {
  /** A window was found: a two-sided horizon minute with bidL >= level. */
  win: boolean;
  /** Minutes from the entry to the END of the window minute (fractional: entries sit on a 1 s grid), always >= 1: the window
   *  minute starts at or after the entry (Amendment 4a item 1), so the entry's own minute is never one. hist.tWin bin 0
   *  (< 1) stays empty. */
  tWin?: number;
  /** Consecutive minutes at or above the level from the window minute, inside the horizon (a missing minute or a minute
   *  below the level ends the run). */
  lenWin?: number;
  /** The wrong-way dip: the lowest bidL of the horizon minutes before the window minute (all horizon minutes when there is no
   *  window) minus the entry ask; NaN when there are none. */
  dip: number;
  /** Horizon minutes (two-sided) with bidL >= level, the window minute included. */
  held: number;
  /** 'window' at the window minute; 'end' when the end rule stopped the search before the market's minutes ran out (the
   *  market has a minute ending after endRuleTs); 'close' when the horizon ran to the market's last minute; 'none' when no
   *  minute ends after the entry at all. */
  resolvedBy: 'window' | 'end' | 'close' | 'none';
  /** The window minute's end, the end-rule time, or the last horizon minute's end. */
  resolvedAt?: number;
}

/** The window rule for one entry at entryTs on the market mc, bought at `ask`, with level `level` (whole-cent dollars), under
 *  the end rule at endRuleTs. */
export function windowOutcome(mc: MinuteCandles, entryTs: number, ask: number, level: number, endRuleTs: number): WindowOutcome {
  const lvl = level - EPS;
  let held = 0, winAt = -1, firstIdx = -1, lastIdx = -1, minBid = Infinity, later = false;
  for (let i = 0; i < mc.length; i++) {
    const c = mc[i];
    // Amendment 4a item 1: a full minute after the buy. A candle whose minute began before the entry (the entry's own minute)
    // is never a window and is not in the dip: its low covers time before the purchase.
    if (c.ts - MIN < entryTs) { if (c.ts > endRuleTs) { later = true; break; } continue; }
    if (c.ts > endRuleTs) { later = true; break; }
    if (firstIdx < 0) firstIdx = i;
    lastIdx = i;
    const at = c.twoSided && c.bidL >= lvl;
    if (at) held++;
    if (winAt < 0) { if (at) winAt = i; else if (Number.isFinite(c.bidL)) minBid = Math.min(minBid, c.bidL); }
  }
  const dip = minBid === Infinity ? NaN : minBid - ask;
  if (winAt >= 0) {
    let lenWin = 1;
    for (let i = winAt + 1; i <= lastIdx; i++) {
      const c = mc[i];
      if (c.ts - mc[i - 1].ts !== MIN || !(c.twoSided && c.bidL >= lvl)) break;
      lenWin++;
    }
    return { win: true, tWin: (mc[winAt].ts - entryTs) / MIN, lenWin, dip, held, resolvedBy: 'window', resolvedAt: mc[winAt].ts };
  }
  if (later) return { win: false, dip, held, resolvedBy: 'end', resolvedAt: endRuleTs };
  if (lastIdx >= 0) return { win: false, dip, held, resolvedBy: 'close', resolvedAt: mc[lastIdx].ts };
  return { win: false, dip: NaN, held: 0, resolvedBy: 'none' };
}

// ---- Twins -----------------------------------------------------------------------------------------------------------

/** The minutes a twin may be bought at (Amendment 4 item 5): a two-sided candle ending after the market's second stored
 *  candle (mc[0], the first stored one being dropped already) and at or before the end rule, with its close ask in [lo, hi]. */
export function eligibleMinutes(mc: MinuteCandles, endRuleTs: number, lo = TWIN_ASK_LO, hi = TWIN_ASK_HI): MinuteCandle[] {
  if (!mc.length) return [];
  const second = mc[0].ts;
  return mc.filter((c) => c.ts > second && c.ts <= endRuleTs && c.twoSided && c.askC >= lo - EPS && c.askC <= hi + EPS);
}

/** One random entry: side 'a' | 'b' (the event's two markets, mcA and mcB of drawTwins), bought at the candle's close ask at
 *  its end `ts`. */
export interface Twin { side: 'a' | 'b'; ts: number; ask: number; C: number; level: number; outcome: WindowOutcome }

/** The hour of the minute an entry at `ts` sits in, by that minute's END (an entry at 14:59:30 is in the minute ending
 *  15:00:00, hour 15). */
export function entryHour(ts: number): number { return Math.floor((Math.ceil(ts / MIN) * MIN) / HOUR); }

/** The twins of an instance at entryTs: `count` entries at random eligible minutes in the same UTC clock hour as the entry
 *  minute's end (the side's whole eligible span when the hour holds fewer than TWIN_HOUR_MIN of its eligible minutes), at
 *  that minute's close ask, judged by the window rule under the same end rule. The one test passes onSide = the instance's
 *  own called market (Amendment 4a item 3: "random minutes in the same contracts"; a coin-flip side would let any rule that
 *  buys favourites beat random from price level alone). Without onSide each twin's side is a fair coin. Deterministic in
 *  seedKey (twinSeed): per twin one draw for the coin (drawn even with onSide), one for the minute. A side with no eligible
 *  minute draws no twin (the function then returns fewer than `count`). */
export function drawTwins(mcA: MinuteCandles, mcB: MinuteCandles, entryTs: number, endRuleTs: number, seedKey: string, count = TWINS, orderUsd = ORDER_USD, onSide?: 'a' | 'b'): Twin[] {
  const r = rng(twinSeed(seedKey));
  const hour = entryHour(entryTs);
  const pool = (mc: MinuteCandles) => { const all = eligibleMinutes(mc, endRuleTs); const inHour = all.filter((c) => Math.floor(c.ts / HOUR) === hour); return inHour.length >= TWIN_HOUR_MIN ? inHour : all; };
  const pools = { a: pool(mcA), b: pool(mcB) };
  const out: Twin[] = [];
  for (let k = 0; k < count; k++) {
    const coin: 'a' | 'b' = r() < 0.5 ? 'a' : 'b';
    // Amendment 4a item 3: the instance's own contract when onSide is given (the coin is still drawn, so the minute draws
    // keep their place in the stream); the coin-flip side otherwise (a general helper, not the one test's yardstick).
    const side: 'a' | 'b' = onSide ?? coin;
    const u = r();
    const list = pools[side];
    if (!list.length) continue;
    const c = list[Math.min(list.length - 1, Math.floor(u * list.length))];
    const ask = c.askC, C = contractsFor(ask, orderUsd), level = levelFor(ask, C);
    out.push({ side, ts: c.ts, ask, C, level, outcome: windowOutcome(side === 'a' ? mcA : mcB, c.ts, ask, level, endRuleTs) });
  }
  return out;
}

// ---- Histograms ------------------------------------------------------------------------------------------------------

/** The bin of v among `edges` (HIST_EDGES): for ascending edges the count of edges <= v (bin 0 is v < e0, the last is
 *  v >= last); for descending edges (dip) the count of edges >= v. -1 for a NaN or infinite v (no bin). */
export function histBin(edges: readonly number[], v: number): number {
  if (!Number.isFinite(v)) return -1;
  const desc = edges.length > 1 && edges[1] < edges[0];
  let k = 0;
  for (const e of edges) { if (desc ? e >= v - EPS : e <= v + EPS) k++; else break; }
  return k;
}
const zeros = (edges: readonly number[]) => new Array<number>(edges.length + 1).fill(0);
const bump = (counts: number[], edges: readonly number[], v: number) => { const k = histBin(edges, v); if (k >= 0) counts[k]++; };

// ---- The row (contract C12) ------------------------------------------------------------------------------------------

/** One signal instance with its twins, as the sim (family A) or the signal study (family B) hands it to a WindowAgg. */
export interface WindowInstance {
  event: string;
  /** The called side: the event's market 'a' or 'b'. */
  side: 'a' | 'b';
  /** 'underdog' | 'fav' (family A); the reading's direction or '' (family B). */
  leg: 'underdog' | 'fav' | string;
  /** Entry time, ms. */
  t: number;
  ask: number;
  C: number;
  level: number;
  /** research/tennisTaSim.ts phaseLabel: pre | e20 | p1 | p2 | p3. */
  phase: string;
  /** Family A: the confluence bits of the decision, when known. */
  sig?: number;
  outcome: WindowOutcome;
  twins: Twin[];
}

/** A shard-file row (contract C12). Arrays are per event index of the shard's `events` list; 0 where the event had nothing. */
export interface WindowRow {
  id: string;
  leg?: string;
  /** Instances, windows, twin entries, twin windows per event. */
  n: number[]; w: number[]; tn: number[]; tw: number[];
  /** Counts per HIST_EDGES bin: tWin and lenWin over the windows, dip over the instances with a dip, held over all. tWin
   *  bin 0 (< 1 minute) stays empty since Amendment 4a item 1 (a window minute starts at or after the entry). */
  hist: { tWin: number[]; lenWin: number[]; dip: number[]; held: number[] };
  /** [instances, windows] per phase. */
  byPhase: Record<string, [number, number]>;
  /** Instances resolved by the end rule or the close without a window ('none', no minute at all, is not counted). */
  endNoWin: number;
  /** [instances, sum of entry asks]: the mean entry ask. */
  asks: [number, number];
}

const PHASES = ['pre', 'e20', 'p1', 'p2', 'p3'] as const;

/** The per-row aggregate: instances in, a C12 row out. eventIndex is the slice's event -> index map the caller owns (the
 *  shard's `events` order); it may grow while rows are fed, row() sizes its arrays to it. An event outside it is an error. */
export class WindowAgg {
  private readonly per = new Map<number, [number, number, number, number]>();
  private readonly hist = { tWin: zeros(HIST_EDGES.tWin), lenWin: zeros(HIST_EDGES.lenWin), dip: zeros(HIST_EDGES.dip), held: zeros(HIST_EDGES.held) };
  private readonly byPhase: Record<string, [number, number]> = Object.fromEntries(PHASES.map((p) => [p, [0, 0]]));
  private endNoWin = 0;
  private askN = 0;
  private askSum = 0;
  private maxIdx = -1;

  constructor(readonly id: string, readonly leg: string | undefined, private readonly eventIndex: Map<string, number>) {}

  add(inst: WindowInstance): void {
    const i = this.eventIndex.get(inst.event);
    if (i === undefined) throw new Error(`tennisTaWindow: event ${inst.event} is not in the event index of row ${this.id}`);
    this.maxIdx = Math.max(this.maxIdx, i);
    const o = inst.outcome, win = o.win ? 1 : 0;
    let tn = 0, tw = 0;
    for (const t of inst.twins) { tn++; if (t.outcome.win) tw++; }
    const p = this.per.get(i);
    if (p) { p[0]++; p[1] += win; p[2] += tn; p[3] += tw; } else this.per.set(i, [1, win, tn, tw]);
    if (o.win) { bump(this.hist.tWin, HIST_EDGES.tWin, o.tWin ?? NaN); bump(this.hist.lenWin, HIST_EDGES.lenWin, o.lenWin ?? NaN); }
    bump(this.hist.dip, HIST_EDGES.dip, o.dip);
    bump(this.hist.held, HIST_EDGES.held, o.held);
    const ph = this.byPhase[inst.phase] ?? (this.byPhase[inst.phase] = [0, 0]);
    ph[0]++; ph[1] += win;
    if (!o.win && (o.resolvedBy === 'end' || o.resolvedBy === 'close')) this.endNoWin++;
    this.askN++; this.askSum += inst.ask;
  }

  /** Instances fed so far. */
  get count(): number { return this.askN; }

  row(): WindowRow {
    const len = Math.max(this.eventIndex.size, this.maxIdx + 1);
    const n = new Array<number>(len).fill(0), w = n.slice(), tn = n.slice(), tw = n.slice();
    for (const [i, p] of this.per) { n[i] = p[0]; w[i] = p[1]; tn[i] = p[2]; tw[i] = p[3]; }
    return {
      id: this.id, ...(this.leg !== undefined ? { leg: this.leg } : {}), n, w, tn, tw,
      hist: { tWin: this.hist.tWin.slice(), lenWin: this.hist.lenWin.slice(), dip: this.hist.dip.slice(), held: this.hist.held.slice() },
      byPhase: Object.fromEntries(Object.entries(this.byPhase).map(([k, v]) => [k, [v[0], v[1]] as [number, number]])),
      endNoWin: this.endNoWin, asks: [this.askN, this.askSum],
    };
  }
}

/** Rows pooled into one (the 'both' row of a config: its two legs; n/w/tn/tw add per event, the rest add). Rows of different
 *  array lengths pad with 0 (a row fed before the event index grew). */
export function poolRows(id: string, rows: WindowRow[], leg?: string): WindowRow {
  const len = Math.max(0, ...rows.map((r) => r.n.length));
  const sum = (pick: (r: WindowRow) => number[]) => { const out = new Array<number>(len).fill(0); for (const r of rows) pick(r).forEach((v, i) => { out[i] += v; }); return out; };
  const hist = (k: keyof WindowRow['hist']) => { const out = zeros(HIST_EDGES[k]); for (const r of rows) r.hist[k].forEach((v, i) => { out[i] += v; }); return out; };
  const byPhase: Record<string, [number, number]> = Object.fromEntries(PHASES.map((p) => [p, [0, 0]]));
  for (const r of rows) for (const [k, v] of Object.entries(r.byPhase)) { const ph = byPhase[k] ?? (byPhase[k] = [0, 0]); ph[0] += v[0]; ph[1] += v[1]; }
  return {
    id, ...(leg !== undefined ? { leg } : {}), n: sum((r) => r.n), w: sum((r) => r.w), tn: sum((r) => r.tn), tw: sum((r) => r.tw),
    hist: { tWin: hist('tWin'), lenWin: hist('lenWin'), dip: hist('dip'), held: hist('held') },
    byPhase, endNoWin: rows.reduce((s, r) => s + r.endNoWin, 0), asks: [rows.reduce((s, r) => s + r.asks[0], 0), rows.reduce((s, r) => s + r.asks[1], 0)],
  };
}

// ---- The one test ----------------------------------------------------------------------------------------------------

export interface GapStats {
  /** Pooled instances, windows, twin entries, twin windows. */
  n: number; w: number; tn: number; tw: number;
  /** Window rate w / n and random rate tw / tn (NaN when the denominator is 0). */
  rate: number; random: number;
  /** gap = sum(n_i d_i) / sum(n_i) over the matches with instances and twins, d_i = w_i / n_i - tw_i / tn_i; equal to
   *  rate - random when every instance has the same number of twins. NaN without such a match. */
  gap: number;
  /** Cluster-robust by match: sqrt(sum(n_i^2 (d_i - gap)^2)) / sum(n_i). */
  se: number;
  /** z = gap / se when se > 0; null without a contributing match (no instance or no twin) or on SE 0 (one contributing match,
   *  or identical d_i: the chance wobble cannot be measured, Amendment 4a item 2). */
  z: number | null;
  /** PASS = gap >= 2 x SE, only with a z. */
  pass: boolean;
}

/** Amendment 4 item 6 on per-event arrays (a row's n, w, tn, tw, or those of several rows added). */
export function gapStats(n: number[], w: number[], tn: number[], tw: number[]): GapStats {
  const len = Math.max(n.length, w.length, tn.length, tw.length);
  const at = (a: number[], i: number) => a[i] ?? 0;
  let N = 0, W = 0, TN = 0, TW = 0, sumN = 0, sumND = 0;
  const ds: Array<[number, number]> = [];
  for (let i = 0; i < len; i++) {
    const ni = at(n, i), wi = at(w, i), tni = at(tn, i), twi = at(tw, i);
    N += ni; W += wi; TN += tni; TW += twi;
    if (ni > 0 && tni > 0) { const d = wi / ni - twi / tni; ds.push([ni, d]); sumN += ni; sumND += ni * d; }
  }
  const rate = N > 0 ? W / N : NaN, random = TN > 0 ? TW / TN : NaN;
  if (!ds.length) return { n: N, w: W, tn: TN, tw: TW, rate, random, gap: NaN, se: NaN, z: null, pass: false };
  const gap = sumND / sumN;
  let ss = 0;
  for (const [ni, d] of ds) ss += ni * ni * (d - gap) * (d - gap);
  const se = Math.sqrt(ss) / sumN;
  // Amendment 4a item 2: on SE 0 (one contributing match, or identical d_i) the gap's own chance wobble cannot be measured:
  // no z, no pass (the registry's one_test_pass refuses se 0 too).
  const z = se > 0 ? gap / se : null;
  return { n: N, w: W, tn: TN, tw: TW, rate, random, gap, se, z, pass: z !== null && gap >= 2 * se };
}

// ---- The end rule ----------------------------------------------------------------------------------------------------

/** The end-rule time of a match grid (samples at t0 + i x stepMs, research/tennisTaTypes.ts MatchGrid): the first sample at
 *  which production's latched progress (MatchTracker.progressHigh) reaches 1 - settleFrac, capped at the close; the close
 *  when it never does. */
export function endRuleTs(progressHigh: Float64Array, t0: number, stepMs: number, closeTime: number, settleFrac = SETTLE_FRAC): number {
  const bar = 1 - settleFrac - EPS;
  for (let i = 0; i < progressHigh.length; i++) if (progressHigh[i] >= bar) return Math.min(t0 + i * stepMs, closeTime);
  return closeTime;
}
