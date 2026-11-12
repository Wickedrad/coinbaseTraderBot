// Heat entry lane: the decision and the lane's own book (edge plan E01 / E07, decisions 6, 8 and 11).
//
// The curve reader publishes, once a minute and per coin, the rows of the direction table that fired at the last
// closed bar. This file turns them into entries:
//   1. per coin and horizon, ONE decided call: the hottest row now firing (a pair or triple replaces the single it
//      refines, even when ranked beyond HEAT_TOP_N, and one calling against that single is skipped unless
//      HEAT_PAIR_CONFLICT=pair; nothing is averaged; a row's other names are the same event, never a second vote);
//   2. the 60-minute call is the hour's direction for the coin: it sizes (or blocks) a 15-minute contract entry
//      inside that hour and it is what the perps side asks for;
//   3. a 15-minute call buys the called side of the coin's 15-minute contract, a 60-minute call the hourly strike
//      nearest 50c, each at most once per call, one entry per coin, two heat positions in all (the hottest at heat
//      size, the next at ORDER_USD_MIN), the book's first trips flat at ORDER_USD_MIN, and in live a loss budget;
//   4. the 240-minute and 1440-minute calls (the perp packs) are the perps' only: the 4 hours' call opens a perps heat
//      setup and is its context, the day's call is direction context for every perps heat entry. They never open a
//      Kalshi contract (no contract runs 4 hours or a day); each is ruled on once and recorded as "perps context".
//
// decideHeat is pure: no file, no clock, no config lookup. The time, the markets as the engine shows them, the
// order band, the entry windows and the book state all come in as inputs, so a replay decides exactly as the server
// does. HeatLane wraps it with the saved state and is what the engine and the perps side talk to. The lane sends
// nothing itself: the engine places each plan through placeChecked, in paper and live alike. The only thing that
// differs by mode is the pilot loss budget, which stops entries in live only.

import { logger } from '../util/log';
import { EPS, clamp, round } from '../util/num';
import { writeJsonAtomic } from '../util/persist';
import {
  heatWindowKey, loadHeatState, pruneHeatState, syncHeatBook,
  type HeatLaneState, type HeatPositionLookup, type HeatSyncResult,
} from './heatBook';
import type {
  HeatCallRow, HeatConfig, HeatContext, HeatDecided, HeatDirection, HeatMarketView, HeatOpen, HeatPlan, HeatSkip, HeatSnapshot,
} from './types';

export { emptyHeatState, syncHeatBook, pruneHeatState, heatWindowKey, HEAT_UNFILLED_DROP_MS, HEAT_ACTED_KEEP_MS } from './heatBook';
export type { HeatLaneState, HeatPositionView, HeatPositionLookup, HeatSyncResult, HeatClosed, HeatWindowLoss } from './heatBook';

const log = logger('heat');

const MIN_MS = 60_000;
/** The hour's direction holds for the hour its curve measured. */
const HOUR_MS = 60 * MIN_MS;
/** The 60-minute call is always decided, traded or not: it is the context of the 15-minute contract and the perps. */
const CONTEXT_H = 60;
/** The perps' own horizons (the perp packs): the 4 hours' call and the day's call. Never a Kalshi contract. */
const FOUR_H = 240;
const DAY_H = 1440;
/** Where each horizon's direction is kept in the book and how long it holds: for the horizon its curve measured. */
const CONTEXT_OF: Record<number, { field: 'context' | 'four' | 'day'; ms: number }> = {
  [CONTEXT_H]: { field: 'context', ms: HOUR_MS },
  [FOUR_H]: { field: 'four', ms: FOUR_H * MIN_MS },
  [DAY_H]: { field: 'day', ms: DAY_H * MIN_MS },
};
/** How many ruled calls status() shows. */
const LAST_CALLS = 12;

/** The engine's entry windows, under the names its strategy settings already use (so it can pass them as they are). */
export interface HeatWindows {
  /** 15-minute contract: [earliest, latest] seconds before close. */
  entryWindowUpdown: [number, number];
  /** Hourly contract: [earliest, latest] seconds before close. */
  entryWindowHourly: [number, number];
  /** Hourly contract: only while its YES mid is inside this band. */
  hourlyMidBand: [number, number];
}

/** What the engine hands the lane with every decision, besides the time, the calls and the markets. */
export interface HeatDecideOpts {
  /** The order band in dollars (ORDER_USD_MIN, ORDER_USD_MAX). */
  orderMin: number;
  orderMax: number;
  /** RISK_MIN_SIDE_PRICE: the called side must cost between this and one minus this. */
  minSide: number;
  /** Live book: the pilot loss budget stops entries. Paper only reports it. */
  live: boolean;
  windows: HeatWindows;
  /** A reason no heat entry may go out now (a halt, the soft pause, no exit owner). Every call still gets its
   *  record, as a skip with this reason. */
  entriesBlocked?: string;
  /** The plan's loser cut by price (PLAN_LOSER_CUT_C, dollars a contract) that heat positions get: a market whose spread is
   *  already that wide is not entered, because the cut would sell the position at the first look (bought at the ask, the
   *  bid already that far under). Unset or 0: no such check. */
  cutSpread?: number;
}

export interface HeatDecideInput extends HeatDecideOpts {
  now: number;
  cfg: HeatConfig;
  snapshot: HeatSnapshot | undefined;
  markets: HeatMarketView[];
  /** Read only: decideHeat never changes it. */
  state: HeatLaneState;
}

/** A plan with the contract's close time, which the book needs when the entry is recorded as sent. */
export type HeatLanePlan = HeatPlan & { closeTs: number };

export interface HeatDecideResult {
  /** The calls ruled on in this pass (not claimed before). Each has exactly one plan or one skip, same coin and horizon. */
  decided: HeatDecided[];
  /** Entries to send, hottest first. */
  plans: HeatLanePlan[];
  skips: HeatSkip[];
  /** Hour contexts to store: every fresh coin's 60-minute call now firing, traded or not. */
  contexts: HeatContext[];
  /** Every fresh coin's decided call now inside the entry lag, claimed or not (what `fired` serves the perps side). */
  calls: HeatDecided[];
  /** Claims to add to the book: call key to bar close, one per entry of `decided`. */
  acted: Record<string, number>;
  /** Why the file or a coin gave nothing (status text). */
  notes: string[];
}

/** The key a call is claimed under: one coin, one horizon, one bar. */
export function heatCallKey(asset: string, h: number, barClose: number): string {
  return `${asset}:${h}:${barClose}`;
}

/** How many of the coin's rows the weight is measured over: the traded batch (HEAT_TOP_N), never more than the pack lists. */
export function heatBatch(of: number, topN: number): number {
  return topN > 0 ? Math.min(topN, of) : of;
}

/** Heat weight by rank (E07): 1 for the hottest tenth of the batch, falling in a straight line to 0 at its last row. */
export function heatWeight(rank: number, of: number, topN: number): number {
  const n = heatBatch(of, topN);
  // n / 10, not 0.1 * n: 0.1 * 30 is a hair over 3 in floating point and would round up to 4.
  const peak = Math.max(1, Math.ceil(n / 10));
  return n <= peak ? 1 : clamp((n - rank) / (n - peak), 0, 1);
}

/** The stake in dollars: heat size only for the hottest slot once the flat phase is over, else ORDER_USD_MIN. */
export function heatStake(weight: number, slot: 1 | 2, trips: number, cfg: Pick<HeatConfig, 'sizing' | 'flatTrips'>, orderMin: number, orderMax: number): number {
  return cfg.sizing && slot === 1 && trips >= cfg.flatTrips ? orderMin + weight * (Math.max(orderMax, orderMin) - orderMin) : orderMin;
}

/** DOGE is not traded anywhere in this project, whatever the settings list. */
const isDoge = (asset: string): boolean => asset.trim().toUpperCase().startsWith('DOGE');

/** The horizons the lane decides calls at: the contracts' (HEAT_HORIZONS), the hour (always: the 15-minute contract's
 *  context and the perps'), and while the perps hook is on, the 4 hours and (unless HEAT_PERPS_DAILY=off) the day. */
export function heatReadHorizons(cfg: Pick<HeatConfig, 'horizons' | 'perps' | 'perpsDaily'>): number[] {
  const perps = cfg.perps === 'off' ? [] : [FOUR_H, ...(cfg.perpsDaily === 'off' ? [] : [DAY_H])];
  return [...new Set([...cfg.horizons, CONTEXT_H, ...perps])].sort((a, b) => a - b);
}

/** Why a call at this horizon never opens a Kalshi contract, or undefined for the contracts' horizons. The 240- and
 *  1440-minute calls are the perps' (no contract runs that long), whatever HEAT_HORIZONS says. */
export function perpsContextOnly(h: number): string | undefined {
  if (h === FOUR_H) return 'perps context: the 4-hour call is for the perps (a 4h heat setup and its context), no Kalshi contract trades it';
  if (h === DAY_H) return 'perps context: the daily call is the perps\' direction for the day, no Kalshi contract trades it';
  return undefined;
}

const KIND_ORDER: Record<HeatCallRow['kind'], number> = { single: 0, pair: 1, triple: 2 };
/** Hotter first: the lower rank; equal ranks by heat, then by key so the choice never depends on the file's order. */
const hotter = (a: HeatCallRow, b: HeatCallRow): number => a.rank - b.rank || b.heat - a.heat || (a.key < b.key ? -1 : a.key > b.key ? 1 : 0);

/** One row per event, hottest first. A row that shares a name with a hotter row (its key or one of its aliases) is
 *  the same event under another reading (identical samples): it is one bet, so it is not counted again. */
function oneRowPerEvent(rows: HeatCallRow[]): HeatCallRow[] {
  const seen = new Set<string>();
  const out: HeatCallRow[] = [];
  for (const r of [...rows].sort(hotter)) {
    const names = [r.key, ...(r.aliases ?? [])];
    if (names.some((n) => seen.has(n))) continue;
    for (const n of names) seen.add(n);
    out.push(r);
  }
  return out;
}

/** Finer first (a triple before a pair), then the higher heat: the order refinements of one trigger replace in. */
const finerThenHeat = (a: HeatCallRow, b: HeatCallRow): number => KIND_ORDER[b.kind] - KIND_ORDER[a.kind] || b.heat - a.heat || hotter(a, b);

/** A coin's decided call from the rows now firing at one horizon (Addendum 2's pair rule). The decided single is the
 *  hottest firing single inside the batch (`topN`, 0 = every row). The firing pairs and triples whose trigger (`trig`) is
 *  that single, under its key or one of its aliases, refine it: the finest and hottest of them replaces it whatever its
 *  own rank, and the replacement keeps the hotter of the two ranks (the single was already good enough to trade). A pair
 *  on any other trigger stands on its own, inside the batch only. The hottest of these wins; nothing is averaged.
 *  `single` on the result names the single a refinement replaced, so the caller can see a pair calling against it.
 *  Undefined when nothing inside the batch fired. */
export function decideCall(asset: string, h: number, firing: HeatCallRow[], topN = 0): HeatDecided | undefined {
  const events = oneRowPerEvent(firing);
  const inBatch = (r: HeatCallRow) => topN <= 0 || r.rank <= topN;
  const single = events.find((r) => r.kind === 'single' && inBatch(r));
  const own = new Set(single ? [single.key, ...(single.aliases ?? [])] : []);
  const refines = (r: HeatCallRow) => r.kind !== 'single' && r.trig !== undefined && own.has(r.trig);
  const refiner = events.filter(refines).sort(finerThenHeat)[0];
  const lead = single && refiner ? { ...refiner, rank: Math.min(single.rank, refiner.rank) } : single;
  // A pair or triple of another trigger: the hottest inside the batch, refined in turn by a finer row of its own trigger.
  const loose = events.filter((r) => r.kind !== 'single' && !refines(r) && inBatch(r));
  let row = lead;
  for (const r of loose) if (!row || hotter(r, row) < 0) row = r;
  if (!row) return undefined;
  if (row !== lead) {
    const pick = row;
    row = loose.filter((r) => KIND_ORDER[r.kind] > KIND_ORDER[pick.kind] && r.trig !== undefined && r.trig === pick.trig).sort(finerThenHeat)[0] ?? pick;
  }
  const chosen = row;
  // The rows that took part: everything inside the batch, and the refinements of the decided single beyond it.
  const counted = events.filter((r) => inBatch(r) || refines(r));
  return {
    asset, h, row: chosen, fired: counted.length, against: counted.filter((r) => r.dir !== chosen.dir).length,
    ...(chosen === lead && refiner ? { single } : {}),
  };
}

/** Why a decided call is not traded although it fired: its refinement calls against the single it replaced and
 *  HEAT_PAIR_CONFLICT says skip. */
function pairConflict(c: HeatDecided, cfg: HeatConfig): string | undefined {
  if (!c.single || c.single.dir === c.row.dir || cfg.pairConflict === 'pair') return undefined;
  const word = (d: 1 | -1) => (d > 0 ? 'up' : 'down');
  return `pair against single: ${c.row.key} calls ${word(c.row.dir)}, its single ${c.single.key} ${word(c.single.dir)} (HEAT_PAIR_CONFLICT skip)`;
}

/** A call that fired on a coin the reader cannot vouch for right now: recorded, never traded, never a context. */
type UnfitCall = HeatDecided & { why: string };

/** Read the snapshot: per coin and horizon the decided call, split into coins that are fresh and coins that are not.
 *  Never throws; a file or coin that cannot be used becomes a note. */
export function readHeatCalls(now: number, cfg: HeatConfig, snap: HeatSnapshot | undefined): { fresh: HeatDecided[]; unfit: UnfitCall[]; notes: string[] } {
  const fresh: HeatDecided[] = [];
  const unfit: UnfitCall[] = [];
  const notes: string[] = [];
  if (!snap) return { fresh, unfit, notes: ['no calls file'] };
  const secs = (ms: number) => Math.round(ms / 1000);
  // A file this old means the reader stopped: nothing in it is read, not even for the record.
  if (now - snap.writtenAt > 2 * cfg.maxAgeSec * 1000) {
    return { fresh, unfit, notes: [`calls file ignored: written ${secs(now - snap.writtenAt)} s ago (limit ${2 * cfg.maxAgeSec} s)`] };
  }
  const horizons = heatReadHorizons(cfg);
  const lagMs = cfg.entryLagSec * 1000;
  for (const asset of cfg.assets) {
    if (isDoge(asset)) { notes.push(`${asset}: not traded (no DOGE)`); continue; }
    const coin = snap.coins.get(asset);
    if (!coin) { notes.push(`${asset}: not in the calls file`); continue; }
    const why = !coin.ok ? `reader not ok${coin.why ? `: ${coin.why}` : ''}`
      : now - coin.asOf > cfg.maxAgeSec * 1000 ? `calls stale: last minute closed ${secs(now - coin.asOf)} s ago (limit ${cfg.maxAgeSec} s)`
      : undefined;
    if (why) notes.push(`${asset}: ${why}`);
    for (const h of horizons) {
      // Every row inside the lag: the batch (HEAT_TOP_N) is applied by decideCall, since a refining pair may sit beyond it.
      const firing = (coin.calls ?? []).filter((r) => r.h === h && now - r.barClose >= 0 && now - r.barClose <= lagMs);
      const call = decideCall(asset, h, firing, cfg.topN);
      if (!call) continue;
      // A pair against its single is no direction at all: recorded and skipped, never a context, never served to the perps.
      const reason = why ?? pairConflict(call, cfg);
      if (reason) unfit.push({ ...call, why: reason }); else fresh.push(call);
    }
  }
  return { fresh, unfit, notes };
}

/** The direction a decided call stands for: it holds for the horizon its curve measured, from its bar close (the hour
 *  for a 60-minute call, 4 hours for a 240-minute call, a day for a 1440-minute call). */
function contextOf(c: HeatDecided, ms: number): HeatContext {
  const { row } = c;
  return { asset: c.asset, dir: row.dir, key: row.key, rank: row.rank, of: row.of, heat: row.heat, barClose: row.barClose, until: row.barClose + ms };
}
const hourContext = (c: HeatDecided): HeatContext => contextOf(c, HOUR_MS);

type TwoSided = HeatMarketView & { yesBid: number; yesAsk: number };
/** A bid and an ask, both real prices and not crossed: without both there is no touch to trade at and no mid. */
const twoSided = (m: HeatMarketView): m is TwoSided =>
  m.yesBid !== undefined && m.yesAsk !== undefined && m.yesBid > 0 && m.yesAsk < 1 && m.yesAsk > m.yesBid;
const yesMid = (m: TwoSided): number => (m.yesBid + m.yesAsk) / 2;
const tauSec = (m: HeatMarketView, now: number): number => (m.closeTs - now) / 1000;
const inWindow = (tau: number, [earliest, latest]: [number, number]): boolean => tau <= earliest && tau >= latest;
const byCloseThenTicker = (a: HeatMarketView, b: HeatMarketView): number => a.closeTs - b.closeTs || (a.ticker < b.ticker ? -1 : a.ticker > b.ticker ? 1 : 0);
const kindOf = (h: number): '15m' | 'hourly' | undefined => (h === 15 ? '15m' : h === 60 ? 'hourly' : undefined);

/** The contract's window in seconds for the re-entry rule: open to close, at most the contract kind's own length
 *  (an hourly strike can be listed long before its hour). */
function windowSec(m: HeatMarketView): number {
  const full = m.kind === '15m' ? 900 : 3600;
  const own = m.openTs !== undefined ? (m.closeTs - m.openTs) / 1000 : full;
  return own > 0 ? Math.min(own, full) : full;
}

/** The contract a call trades: the coin's 15-minute market inside its entry window, or for the hour the strike whose
 *  YES mid is nearest 50c among those inside the hourly window and mid band. */
function pickMarket(asset: string, h: number, markets: HeatMarketView[], now: number, w: HeatWindows): { market?: HeatMarketView; why?: string } {
  const kind = kindOf(h);
  if (!kind) return { why: `no contract trades the ${h}-minute horizon` };
  const mine = markets.filter((m) => m.asset === asset && m.kind === kind);
  if (kind === '15m') {
    const open = mine.filter((m) => inWindow(tauSec(m, now), w.entryWindowUpdown)).sort(byCloseThenTicker);
    return open[0] ? { market: open[0] } : { why: `no ${asset} 15m market inside the entry window (${w.entryWindowUpdown[0]}..${w.entryWindowUpdown[1]} s to close)` };
  }
  const open = mine.filter((m) => inWindow(tauSec(m, now), w.entryWindowHourly));
  if (!open.length) return { why: `no ${asset} hourly market inside the entry window (${w.entryWindowHourly[0]}..${w.entryWindowHourly[1]} s to close)` };
  const [lo, hi] = w.hourlyMidBand;
  // Distance from 50c in whole millionths, so 0.45 and 0.55 tie instead of differing by a rounding hair.
  const off = (m: TwoSided) => Math.round(Math.abs(yesMid(m) - 0.5) * 1e6);
  const priced = open.filter(twoSided).filter((m) => yesMid(m) >= lo - EPS && yesMid(m) <= hi + EPS).sort((a, b) => off(a) - off(b) || byCloseThenTicker(a, b));
  return priced[0] ? { market: priced[0] } : { why: `no ${asset} hourly market with a two-sided book and a mid inside ${lo.toFixed(2)}..${hi.toFixed(2)}` };
}

/** What one contract of the called side costs at the touch: the YES ask, or one minus the YES bid for NO. */
const sideCostOf = (m: TwoSided, side: 'yes' | 'no'): number => round(side === 'yes' ? m.yesAsk : 1 - m.yesBid, 4);

/** Re-entry after a loss (Steven, Nov 11 6:59 PM EST / 23:59 UTC; his card 7:05 PM EST / 00:05 UTC): a window the lane left
 *  at a loss is entered again only on a call whose bar closed after that loss (the TA judged again; the call's side may be
 *  the other one), while more than half of the window is left, at most HEAT_REENTRIES_15M / HEAT_REENTRIES_HOURLY times,
 *  and not once its losses reach HEAT_REENTRY_LOSS_STOP of one order. Undefined when it may go. */
function reentryBlock(m: TwoSided, i: HeatDecideInput, barClose: number): string | undefined {
  const l = i.state.losses?.[heatWindowKey(m.asset, m.kind, m.closeTs)];
  if (!l) {
    // A loss recorded before the count (a file from an older build): the old rule, not entered again.
    return i.state.lossTickers[m.ticker] !== undefined ? 'the lane left this contract at a loss (recorded before re-entries were counted)' : undefined;
  }
  const what = m.kind === '15m' ? 'this 15-minute contract' : 'this hourly window';
  const cap = m.kind === '15m' ? i.cfg.reentries15m : i.cfg.reentriesHourly;
  const env = m.kind === '15m' ? 'HEAT_REENTRIES_15M' : 'HEAT_REENTRIES_HOURLY';
  if (l.n > cap) return `the lane left ${what} at a loss ${l.n} times: ${cap} re-entries after a loss at most (${env})`;
  const stop = i.cfg.reentryLossStop * l.stake;
  if (i.cfg.reentryLossStop > 0 && l.usd >= stop - EPS) {
    return `the lane's losses in ${what} ($${l.usd.toFixed(2)}) reached ${Math.round(i.cfg.reentryLossStop * 100)}% of one order ($${stop.toFixed(2)} of $${l.stake.toFixed(2)}, HEAT_REENTRY_LOSS_STOP)`;
  }
  if (tauSec(m, i.now) <= windowSec(m) / 2) return `a re-entry after a loss needs more than half of the window left (${Math.round(tauSec(m, i.now))} s of ${windowSec(m)} s)`;
  if (barClose <= l.at) return 'the call\'s bar closed before the lane\'s last loss in this window: a re-entry needs a call made after it';
  return undefined;
}

/** Why this market cannot take the entry, or undefined when it qualifies. */
function marketBlock(m: TwoSided, side: 'yes' | 'no', i: HeatDecideInput, barClose: number): string | undefined {
  const cost = sideCostOf(m, side);
  if (cost < i.minSide - EPS || cost > 1 - i.minSide + EPS) return `the ${side} side costs ${cost.toFixed(2)}, outside ${i.minSide.toFixed(2)}..${(1 - i.minSide).toFixed(2)}`;
  const spread = round(m.yesAsk - m.yesBid, 4);
  if (i.cutSpread !== undefined && i.cutSpread > 0 && spread >= i.cutSpread - EPS) {
    return `the spread (${Math.round(spread * 100)}c) is at or above the loser cut (${Math.round(i.cutSpread * 100)}c, PLAN_LOSER_CUT_C): the cut would sell the position at once`;
  }
  // A position of any lane blocks: the lane never adds to one and never flips one.
  if (Math.abs(m.position) > EPS) return `the market already holds a position (${m.position})`;
  if (i.state.open.some((o) => o.ticker === m.ticker)) return 'a heat entry on this contract is already out';
  if (m.blocked) return m.blocked;
  const again = reentryBlock(m, i, barClose);
  if (again) return again;
  if (i.state.traded?.[m.ticker] !== undefined && tauSec(m, i.now) <= windowSec(m) / 2) return 'already traded this contract and no more than half of its window is left';
  return undefined;
}

interface Candidate {
  call: HeatDecided;
  market: TwoSided;
  side: 'yes' | 'no';
  weight: number;
  context: HeatPlan['context'];
}

/** The lane's decision for one moment. Pure: reads its inputs, returns what to send, what was passed over and why,
 *  and what the book should remember (hour contexts, claims). It never changes `state`. */
export function decideHeat(i: HeatDecideInput): HeatDecideResult {
  const { now, cfg, state } = i;
  const { fresh, unfit, notes } = readHeatCalls(now, cfg, i.snapshot);
  const res: HeatDecideResult = { decided: [], plans: [], skips: [], contexts: [], calls: fresh, acted: {}, notes };

  // The hour's direction first: a 15-minute call decided in the same minute is sized by this minute's hour call.
  const context: Record<string, HeatContext> = { ...state.context };
  for (const c of fresh) {
    if (c.h !== CONTEXT_H) continue;
    const ctx = hourContext(c);
    res.contexts.push(ctx);
    const had = context[c.asset];
    if (!had || ctx.barClose >= had.barClose) context[c.asset] = ctx;
  }

  // The switch is the engine's to read, but a lane that is off must not plan entries whoever calls it.
  const entriesBlocked = i.entriesBlocked ?? (cfg.enabled ? undefined : 'heat lane off (HEAT_LANE)');
  const claimed = (c: HeatDecided) => state.acted[heatCallKey(c.asset, c.h, c.row.barClose)] !== undefined;
  const rule = (c: HeatDecided) => {
    res.decided.push({ asset: c.asset, h: c.h, row: c.row, fired: c.fired, against: c.against, ...(c.single ? { single: c.single } : {}) });
    res.acted[heatCallKey(c.asset, c.h, c.row.barClose)] = c.row.barClose;
  };
  const skip = (c: HeatDecided, reason: string, ticker?: string) => {
    res.skips.push({ asset: c.asset, h: c.h, ...(ticker ? { ticker } : {}), key: c.row.key, reason });
  };

  for (const c of unfit) {
    if (claimed(c)) continue;
    rule(c);
    skip(c, entriesBlocked ?? c.why);
  }

  const openCount = state.open.length;
  const flat = state.trips < cfg.flatTrips;
  // Decision 11: one position at a time until the book has its first trips. Decision 8 after that.
  const maxOpen = flat ? Math.min(1, cfg.maxOpen) : cfg.maxOpen;
  const free = Math.max(0, maxOpen - openCount);
  const noRoom = flat
    ? `flat phase (${state.trips} of ${cfg.flatTrips} trips done): one heat position at a time`
    : `${openCount} heat positions open (HEAT_MAX_OPEN ${cfg.maxOpen})`;
  const pilotSpent = i.live && cfg.pilotLossUsd > 0 && state.pnl <= -cfg.pilotLossUsd;

  // Each fresh call the lane has not ruled on yet: passed over with a reason, or a candidate for this minute.
  const candidates: Candidate[] = [];
  for (const c of fresh) {
    if (claimed(c)) continue;
    rule(c);
    // The 4 hours' and the day's calls are the perps' (their direction is kept above): ruled on and recorded, never traded here.
    const perpsOnly = perpsContextOnly(c.h);
    if (perpsOnly) { skip(c, perpsOnly); continue; }
    if (entriesBlocked) { skip(c, entriesBlocked); continue; }
    if (!cfg.horizons.includes(c.h)) { skip(c, `the ${c.h}-minute call is context only (HEAT_HORIZONS)`); continue; }
    if (pilotSpent) { skip(c, `pilot budget spent: heat P&L ${state.pnl.toFixed(2)}, limit -${cfg.pilotLossUsd.toFixed(2)} (HEAT_PILOT_LOSS_USD)`); continue; }
    if (state.open.filter((o) => o.asset === c.asset).length >= cfg.maxPerCoin) { skip(c, `${c.asset} already has an open heat position`); continue; }
    const lastExit = state.lastExit[c.asset];
    if (lastExit !== undefined && now - lastExit < cfg.cooldownSec * 1000) {
      skip(c, `cooldown: ${c.asset} left a heat position ${Math.round((now - lastExit) / 1000)} s ago (wait ${cfg.cooldownSec} s)`);
      continue;
    }
    if (free === 0) { skip(c, noRoom); continue; }
    const { market, why } = pickMarket(c.asset, c.h, i.markets, now, i.windows);
    if (!market) { skip(c, why ?? 'no market'); continue; }
    const side: 'yes' | 'no' = c.row.dir > 0 ? 'yes' : 'no';
    // The hour's direction acts on the 15-minute contract only: the hourly contract IS the hour's call.
    const hour = context[c.asset];
    const ctx: HeatPlan['context'] = c.h !== 15 || cfg.context === 'off' ? 'n/a'
      : !hour || now >= hour.until ? 'none'
      : hour.dir === c.row.dir ? 'agree' : 'against';
    if (ctx === 'against' && cfg.context === 'block') { skip(c, `the hour's direction is against it (${hour!.key}, HEAT_CONTEXT block)`, market.ticker); continue; }
    if (!twoSided(market)) { skip(c, 'no two-sided book', market.ticker); continue; }
    const blocked = marketBlock(market, side, i, c.row.barClose);
    if (blocked) { skip(c, blocked, market.ticker); continue; }
    const base = heatWeight(c.row.rank, c.row.of, cfg.topN);
    const weight = ctx === 'agree' ? Math.min(1, base + cfg.contextBoost) : ctx === 'against' ? 0 : base;
    candidates.push({ call: c, market, side, weight, context: ctx });
  }

  // One entry per coin a minute: the hotter of its 15-minute and hourly candidates, the 15-minute contract on a tie.
  const best = new Map<string, Candidate>();
  for (const cand of candidates) {
    const had = best.get(cand.call.asset);
    const wins = !had || cand.weight > had.weight + EPS || (Math.abs(cand.weight - had.weight) <= EPS && cand.call.h < had.call.h);
    const loser = wins ? had : cand;
    if (wins) best.set(cand.call.asset, cand);
    if (loser) skip(loser.call, `${loser.call.asset} has a hotter call this minute (one entry per coin)`, loser.market.ticker);
  }

  // Decision 8: the hottest coin first; ties by the better rank, then by the order the coins are listed in.
  const order = (asset: string) => cfg.assets.indexOf(asset);
  const ranked = [...best.values()].sort((a, b) =>
    (Math.abs(b.weight - a.weight) > EPS ? b.weight - a.weight : 0) || a.call.row.rank - b.call.row.rank || order(a.call.asset) - order(b.call.asset));
  ranked.forEach((cand, j) => {
    const { call: c, market: m, side } = cand;
    if (j >= free) {
      skip(c, flat ? `${noRoom}; ${ranked[0].call.asset} is hotter` : `no slot left this minute (HEAT_MAX_OPEN ${cfg.maxOpen}): hotter calls first`, m.ticker);
      return;
    }
    // Slot 1 is the hottest plan of an empty book; anything opened beside another heat position is slot 2.
    const slot: 1 | 2 = openCount === 0 && j === 0 ? 1 : 2;
    const stake = heatStake(cand.weight, slot, state.trips, cfg, i.orderMin, i.orderMax);
    const sideCost = sideCostOf(m, side);
    const fair = clamp(yesMid(m) + (c.row.dir * c.row.odds) / 100, 0.01, 0.99);
    res.plans.push({
      asset: c.asset, ticker: m.ticker, kind: m.kind, h: c.h, side,
      price: side === 'yes' ? m.yesAsk : m.yesBid,
      sideCost,
      // Whole contracts, at least one: the stake is a target, the count is what it buys at the touch.
      count: Math.max(1, Math.floor(stake / sideCost + EPS)),
      stakeUsd: round(stake, 2),
      weight: round(cand.weight, 4),
      slot,
      context: cand.context,
      fair: round(fair, 4),
      ruleId: `heat:${i.snapshot?.run ?? ''}:${c.asset}:h${c.h}:${c.row.key}`,
      row: c.row,
      why: `heat ${c.asset} ${m.kind} ${c.row.dir > 0 ? 'up' : 'down'} ${c.row.key} rank ${c.row.rank}/${heatBatch(c.row.of, cfg.topN)} ctx ${cand.context}`,
      closeTs: m.closeTs,
    });
  });
  return res;
}

/** One ruled call as status() shows it. */
export interface HeatCallStatus {
  at: number;
  asset: string;
  h: number;
  key: string;
  dir: 1 | -1;
  rank: number;
  of: number;
  barClose: number;
  fired: number;
  against: number;
  outcome: 'plan' | 'skip';
  ticker?: string;
  reason?: string;
}

export interface HeatLaneStatus {
  open: HeatOpen[];
  trips: number;
  wins: number;
  pnl: number;
  /** Decision 11: on while the book has fewer than `of` finished trips. */
  flat: { on: boolean; trips: number; of: number };
  /** Decision 6: the live loss budget. `left` is null when the budget is off; `enforced` is false in paper. */
  pilot: { lossUsd: number; left: number | null; spent: boolean; enforced: boolean };
  /** The hour's direction per coin, while it holds. */
  context: HeatContext[];
  /** The 4 hours' and the day's direction per coin (the perps' context), while each holds. */
  four: HeatContext[];
  day: HeatContext[];
  lastCalls: HeatCallStatus[];
  /** Why the file or a coin gave nothing at the last look. */
  notes: string[];
}

/** What decide() hands the engine: the decision plus anything worth one operator alert. */
export type HeatLaneDecision = HeatDecideResult & { alerts: string[] };

/** The lane as the engine and the perps side see it: the decision with the saved book behind it. With a file the
 *  state is loaded at start and saved on every change (atomic write); without one it lives in memory (tests, replays). */
export class HeatLane implements HeatDirection {
  private readonly st: HeatLaneState;
  /** Each coin's latest decided call per horizon (`asset:h`). The engine's claim marks a call as acted on for the
   *  Kalshi entry; the perps side still has to see it, so it is remembered here apart from the claims. */
  private readonly latest = new Map<string, HeatDecided>();
  /** Close times of the plans from the last decision, for a plan that reaches sent() without its own. */
  private planClose = new Map<string, number>();
  private lastCalls: HeatCallStatus[] = [];
  private notes: string[] = [];
  private live = false;
  private pilotAlerted = false;

  /** The perps side's view of the lane. Never throws: a failure reads as "no direction". */
  readonly direction: HeatDirection = {
    hour: (asset, now) => { try { return this.hour(asset, now); } catch { return undefined; } },
    fired: (asset, h, now) => { try { return this.fired(asset, h, now); } catch { return undefined; } },
    four: (asset, now) => { try { return this.four(asset, now); } catch { return undefined; } },
    day: (asset, now) => { try { return this.day(asset, now); } catch { return undefined; } },
  };

  constructor(private readonly cfg: HeatConfig, private readonly file?: string) {
    this.st = loadHeatState(file);
  }

  /** The cheap look the engine takes every second, before it builds any market view: stores the contexts (hour, 4 hours,
   *  day) and the latest calls, and returns the calls now firing that have not been ruled on yet. */
  pending(now: number, snapshot: HeatSnapshot | undefined): HeatDecided[] {
    const { fresh, unfit, notes } = readHeatCalls(now, this.cfg, snapshot);
    this.notes = notes;
    if (this.remember(fresh)) this.save();
    return [...fresh, ...unfit].filter((c) => this.st.acted[heatCallKey(c.asset, c.h, c.row.barClose)] === undefined);
  }

  /** Decide this moment's entries. Every call ruled on is claimed here, so the next tick does not act on it again;
   *  the hour contexts are stored whether anything trades or not. */
  decide(now: number, snapshot: HeatSnapshot | undefined, markets: HeatMarketView[], o: HeatDecideOpts): HeatLaneDecision {
    this.live = o.live;
    const res = decideHeat({ ...o, now, cfg: this.cfg, snapshot, markets, state: this.st });
    this.notes = res.notes;
    let changed = this.remember(res.calls);
    for (const [key, barClose] of Object.entries(res.acted)) { this.st.acted[key] = barClose; changed = true; }
    this.planClose = new Map(res.plans.map((p) => [p.ticker, p.closeTs]));
    for (const d of res.decided) {
      // The 240- and 1440-minute calls fire again minute after minute and are shown as `four` and `day`: kept out here so
      // they never push the Kalshi lane's own rulings out of the last calls.
      if (perpsContextOnly(d.h)) continue;
      const plan = res.plans.find((p) => p.asset === d.asset && p.h === d.h);
      const skip = res.skips.find((s) => s.asset === d.asset && s.h === d.h);
      this.lastCalls.push({
        at: now, asset: d.asset, h: d.h, key: d.row.key, dir: d.row.dir, rank: d.row.rank, of: d.row.of, barClose: d.row.barClose, fired: d.fired, against: d.against,
        outcome: plan ? 'plan' : 'skip', ...(plan ? { ticker: plan.ticker } : skip?.ticker ? { ticker: skip.ticker } : {}), ...(plan ? {} : { reason: skip?.reason }),
      });
    }
    if (this.lastCalls.length > LAST_CALLS) this.lastCalls.splice(0, this.lastCalls.length - LAST_CALLS);
    // One alert when the live budget is found spent, and again only if the book came back above it and fell again.
    const alerts: string[] = [];
    const spent = this.pilotSpent();
    if (spent && o.live && !this.pilotAlerted) {
      alerts.push(`heat lane: pilot budget spent (heat P&L ${this.st.pnl.toFixed(2)}, limit -${this.cfg.pilotLossUsd.toFixed(2)}), no new heat entries in live`);
    }
    this.pilotAlerted = spent && o.live;
    if (pruneHeatState(this.st, now)) changed = true;
    if (changed) this.save();
    return { ...res, alerts };
  }

  /** The engine is about to send this plan's order: the lane holds the ticker from here. `cash0` and `fees0` are the
   *  market's net cash and fees in the position book right now; the round trip's result is the change from them. */
  sent(plan: HeatPlan & { closeTs?: number }, now: number, cash0: number, fees0: number): void {
    // An entry already recorded on the ticker carries the round trip's starting cash: it stays.
    if (this.st.open.some((o) => o.ticker === plan.ticker)) return;
    // A plan built by hand may not carry the close time. The contract cannot outlive its kind's window from now, so
    // that bound keeps a loss on it remembered for as long as the contract can still be entered.
    const closeTs = plan.closeTs ?? this.planClose.get(plan.ticker) ?? now + (plan.kind === '15m' ? 15 : 60) * MIN_MS;
    this.st.open.push({
      ticker: plan.ticker, asset: plan.asset, kind: plan.kind, side: plan.side, ruleId: plan.ruleId, h: plan.h,
      sentAt: now, stakeUsd: plan.stakeUsd, closeTs, cash0, fees0,
    });
    this.save();
  }

  /** Bring the book in line with the position book (every tick): opens, closes, settlements and the 30 s drop of an
   *  entry that filled nothing. `dropped` lists the tickers whose tag the engine must take off. */
  sync(now: number, positions: HeatPositionLookup): HeatSyncResult {
    const res = syncHeatBook(this.st, now, positions);
    const pruned = pruneHeatState(this.st, now);
    for (const c of res.closed) log.info(`round trip closed ${c.ticker} ${c.side} pnl ${c.pnl.toFixed(2)} (${c.settled ? 'settled' : 'sold'}); book ${this.st.trips} trips, ${this.st.wins} wins, pnl ${this.st.pnl.toFixed(2)}`);
    for (const t of res.dropped) log.info(`entry dropped ${t}: no position to show for it`);
    if (pruned || res.opened.length || res.closed.length || res.dropped.length) this.save();
    return res;
  }

  /** The entry on this ticker is known to have filled nothing (rejected, or cancelled unfilled): let go of it now
   *  instead of waiting 30 s. Returns whether an entry was dropped; one already seen open is never dropped here. */
  drop(ticker: string): boolean {
    const i = this.st.open.findIndex((o) => o.ticker === ticker && o.openedAt === undefined);
    if (i < 0) return false;
    this.st.open.splice(i, 1);
    this.save();
    return true;
  }

  /** True while the lane has an open or just-sent position on the ticker: no other lane may enter or quote it. */
  holds(ticker: string): boolean {
    return this.st.open.some((o) => o.ticker === ticker);
  }

  /** The hour's direction for a coin: its latest decided 60-minute call, while its hour lasts. */
  hour(asset: string, now: number): HeatContext | undefined {
    const c = this.st.context[asset];
    return c && now < c.until ? { ...c } : undefined;
  }

  /** The coin's decided call at this horizon while it is inside the entry lag. Reading it claims nothing. */
  fired(asset: string, h: number, now: number): HeatDecided | undefined {
    const d = this.latest.get(`${asset}:${h}`);
    if (!d) return undefined;
    const age = now - d.row.barClose;
    return age >= 0 && age <= this.cfg.entryLagSec * 1000 ? d : undefined;
  }

  /** The 4 hours' direction for a coin: its latest decided 240-minute call, until its bar close plus 240 minutes. */
  four(asset: string, now: number): HeatContext | undefined {
    const c = this.st.four?.[asset];
    return c && now < c.until ? { ...c } : undefined;
  }

  /** The day's direction for a coin: its latest decided 1440-minute call, until its bar close plus 1440 minutes. Nothing
   *  with HEAT_PERPS_DAILY=off, even a direction saved before the switch. */
  day(asset: string, now: number): HeatContext | undefined {
    if (this.cfg.perpsDaily === 'off') return undefined;
    const c = this.st.day?.[asset];
    return c && now < c.until ? { ...c } : undefined;
  }

  status(now: number): HeatLaneStatus {
    const { cfg, st } = this;
    return {
      open: st.open.map((o) => ({ ...o })),
      trips: st.trips, wins: st.wins, pnl: st.pnl,
      flat: { on: st.trips < cfg.flatTrips, trips: st.trips, of: cfg.flatTrips },
      pilot: {
        lossUsd: cfg.pilotLossUsd,
        left: cfg.pilotLossUsd > 0 ? round(Math.max(0, cfg.pilotLossUsd + st.pnl), 2) : null,
        spent: this.pilotSpent(),
        enforced: this.live,
      },
      context: Object.values(st.context).filter((c) => now < c.until).map((c) => ({ ...c })),
      four: Object.values(st.four ?? {}).filter((c) => now < c.until).map((c) => ({ ...c })),
      day: cfg.perpsDaily === 'off' ? [] : Object.values(st.day ?? {}).filter((c) => now < c.until).map((c) => ({ ...c })),
      lastCalls: this.lastCalls.map((c) => ({ ...c })),
      notes: [...this.notes],
    };
  }

  private pilotSpent(): boolean {
    return this.cfg.pilotLossUsd > 0 && this.st.pnl <= -this.cfg.pilotLossUsd;
  }

  /** Keep the latest calls (memory) and, from the fresh decided calls at 60, 240 and 1440 minutes, each coin's direction
   *  at that horizon (saved): the latest call wins, whichever side it calls. Returns whether the saved state changed. */
  private remember(calls: HeatDecided[]): boolean {
    for (const c of calls) {
      const had = this.latest.get(`${c.asset}:${c.h}`);
      if (!had || c.row.barClose >= had.row.barClose) this.latest.set(`${c.asset}:${c.h}`, c);
    }
    let changed = false;
    for (const c of calls) {
      const at = CONTEXT_OF[c.h];
      if (!at) continue;
      const ctx = contextOf(c, at.ms);
      const map = (this.st[at.field] ??= {});
      const had = map[ctx.asset];
      if (had && (had.barClose > ctx.barClose || (had.barClose === ctx.barClose && had.key === ctx.key && had.dir === ctx.dir))) continue;
      map[ctx.asset] = ctx;
      changed = true;
    }
    return changed;
  }

  private save(): void {
    if (this.file) writeJsonAtomic(this.file, this.st);
  }
}
