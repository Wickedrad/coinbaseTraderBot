// The plan's ratchet and its end rule (pipeline plan, Stage 0; Steven's decisions 3 and 13, approved Nov 11, 8:03 AM EST /
// 13:03 UTC). For positions opened by the plan's rules (bot/plan/planPositions.ts), behind PLAN_RULES (off by default, paper and
// live alike). Pure: no I/O. The engine (bot/engine.ts, paper and live) and the replay (research/backtest.ts) run this same
// function.
//
// One ratchet for every position (Steven, Nov 11 8:53-8:58 AM EST / 13:53-13:58 UTC): arming, the stop and its trail are the
// profit ratchet's (bot/strategy/profitRatchet.ts ratchetStep), in dollars for the whole position after both fees, the same
// numbers as every other position's (RATCHET_ARM_USD 1.50, RATCHET_STOP_MIN_USD 1.00, RATCHET_TRAIL_USD 0.50). Until then they
// were cents a contract (PLAN_RATCHET_ARM_C / PLAN_RATCHET_TRAIL_C, retired). What this file adds is the plan's own sale and
// end rule. Prices are side terms in dollars (a YES position's YES price, a NO position's NO price).
//   held-side bid   the YES bid for a YES position, the NO bid (1 - the YES ask) for a NO position
//   net at bid      what the whole position nets sold at that bid: count x (bid - entry price - entry fee a contract) less the
//                   taker exit fee on the whole order (Kalshi rounds each order's fee up to the cent), with THE cost basis of
//                   the open contracts (openSidePrice / openEntryFee, bot/oms/positions.ts): netProfitAtBid's number
//   trade net       the ratchet's measure: net at bid plus what partial sales of the position banked since it opened (the
//                   answer given to Steven, Nov 11 9:10 AM EST / 14:10 UTC: a thin bid that took part of it is no drop);
//                   the same as net at bid until a partial sale
//   fee floor price the lowest tick price whose net is at least 0: break-even after both fees
//   break-even      the trade's smallest net at or above $0 on the price grid (planBreakEvenUsd: banked plus the rest at the
//                   lowest price that does not leave the trade under $0): every position's ratchet gets the same one, a plan
//                   position's and any other's, so there is one stop. It counts only once the best is above it
//                   (ratchetStopFor): a stop at the arming net would sell on the tick it arms
//   arm             trade net >= armUsd: best = trade net, stop = max(stopMinUsd, best - trailUsd), never under the break-even
//   raise           while armed, each evaluation on the rule's clock: best = max(best, trade net), stop = max(stop,
//                   stopMinUsd, best - trailUsd, the break-even). The stop is never lowered (asserted).
//   add             a position that grew (an add on the same side) starts its ratchet and any sale under way afresh, as the
//                   profit ratchet of every other position does: the added lot's spread and fees are no drop
//   sell            armed and trade net <= stop: one reduce-only immediate-or-cancel sale of the whole position at a limit of the
//                   bid less 2 ticks (Stage 0: "sales at bid minus 2 ticks"), never below 1 tick. A bid already under the
//                   fee floor price when it triggers (a price gap) still sells, and the gap is listed with its shortfall.
//   retry           a try that leaves the position open (unfilled or part filled) counts as failed and the sale goes again
//                   at the next evaluation; at 3 failed tries an alert is raised and the limit is the bid less 3 ticks. A
//                   sale decided but never sent (the kill switch's 30 s throttle, a risk-gateway refusal) is not a failed
//                   try: it goes again as a resend. Every armed try whose bid is under the fee floor price is listed as a
//                   gap, a retry's as well as the first: the event when it is decided, the state's list once it goes out
//                   (planMarkTried).
//   clock           'tick': every evaluation of the market. 'minute': arm, raise and sell are decided only on the first
//                   evaluation after each minute close, at that evaluation's bid (the rule was proven on one-minute data);
//                   a sale once decided, and its retries, do not wait for the clock.
//   end rule        Stage 0, "settle only in profit": in the last tenth of the contract's window (90 s of a 15-minute
//                   contract, 6 minutes of an hourly one; the window measured as STRATEGY_SHARE_WINDOW_MAX_SEC measures it)
//                   a position whose net at bid is below 0 is sold the same way, on every evaluation. A position in profit
//                   rides: the end rule never sells a winner (the ratchet still runs). An end-rule sale whose try failed is
//                   called off once the position is back at or above break-even after fees (plan_end_rule_cancel), so its
//                   retries never sell a winner either.
//   loser cut       Stage 0, "cut losers early" (E05; Steven, Nov 11 6:56 PM EST / 23:56 UTC: "10c a contract"): on the rule's
//                   clock, a position whose held-side bid is PLAN_LOSER_CUT_C (10c) or more under its entry price (openSidePrice,
//                   before fees), or whose trade net is at or under minus PLAN_LOSER_CUT_USD (off by default), is sold the same
//                   way as the ratchet's sale. Either set to 0 turns that measure off. A cut whose try failed is called off once
//                   the position is back at or above break-even after fees (plan_loser_cut_cancel), as the end rule's is. Until a
//                   hot spot's own dip line is tested, every plan position gets the same cut; a rule may pass its own
//                   (PlanTag.settings.loserCut / loserCutOpen / loserCutLate / loserCutUsd).
//   cut by time     Steven, Nov 12 1:01 AM EST / 06:01 UTC: on price prediction contracts the price cut scales with the
//                   window. At the open it allows a larger loss (PLAN_LOSER_CUT_OPEN_C, 20c), sliding in a straight line to
//                   PLAN_LOSER_CUT_C (10c) once 60% of the window is gone, then to PLAN_LOSER_CUT_LATE_C (3c) at 85%, and
//                   stays there; from 90% the end rule sells anything not in profit, and the heat lane enters nothing
//                   (bot/heat/heatLane.ts). The window is the end rule's (windowSec); without one the cut is the flat
//                   PLAN_LOSER_CUT_C. planLoserCutAt is the line.
// The ratchet sale, the loser cut and the end rule are the plan's own rules: they are not held by STRATEGY_NO_EXIT_BEFORE_CLOSE_SEC. The hold
// exit (bot/strategy/holdExit.ts) sells plan positions too (Steven, Nov 11 8:52 AM EST / 13:52 UTC): whichever fires first.

import { orderFee, type FeeSchedule } from '../fees';
import { assertStopNotLowered, ratchetStep, type RatchetSettings, type RatchetState } from '../strategy/profitRatchet';

export type PlanClock = 'tick' | 'minute';

/** A position's ratchet settings: the profit ratchet's, in dollars for the whole position, and the rule's clock. A rule may pass
 *  its own tested values; what it leaves out is the profit ratchet's (RATCHET_ARM_USD, RATCHET_STOP_MIN_USD, RATCHET_TRAIL_USD). */
export interface PlanRatchetSettings extends RatchetSettings {
  clock: PlanClock;
  /** The loser cut by price (PLAN_LOSER_CUT_C, dollars a contract): sold once the held side's bid is this far or more under
   *  the entry price. 0 or unset: off. */
  loserCut?: number;
  /** The price cut at the window's open (PLAN_LOSER_CUT_OPEN_C, dollars a contract): the cut slides from this to `loserCut`
   *  at 60% of the window (planLoserCutAt). Unset: `loserCut` (no scaling before 60%). */
  loserCutOpen?: number;
  /** The price cut from 85% of the window (PLAN_LOSER_CUT_LATE_C): the cut slides from `loserCut` at 60% to this. Unset:
   *  `loserCut`. */
  loserCutLate?: number;
  /** The loser cut by dollars (PLAN_LOSER_CUT_USD): sold once the trade's net after both fees is at or under minus this. 0 or
   *  unset: off. */
  loserCutUsd?: number;
}

/** PLAN_RULES (bot/config.ts). */
export interface PlanConfig {
  /** PLAN_RULES (default false, the same in paper and live): positions opened by plan rules get this ratchet, loser cut and end
   *  rule, and the pacer only reports pace for them. Off, every position is managed as before, tagged or not. */
  enabled: boolean;
  /** PLAN_LOSER_CUT_C as dollars a contract (default 0.10): the loser cut by price at 60% of the window; 0 = off. */
  loserCut: number;
  /** PLAN_LOSER_CUT_OPEN_C (default 0.20): the price cut at the window's open. */
  loserCutOpen: number;
  /** PLAN_LOSER_CUT_LATE_C (default 0.03): the price cut from 85% of the window. */
  loserCutLate: number;
  /** PLAN_LOSER_CUT_USD (default 0 = off): the loser cut by the trade's net after fees, dollars for the whole position. */
  loserCutUsd: number;
}

/** A price gap: the bid that triggered an armed sale was already under the fee floor price. */
export interface PlanGap {
  at: number;
  bid: number;
  /** null: no price under $1 breaks even. */
  feeFloor: number | null;
  /** How far under the fee floor price the bid was, in cents a contract (null: no break-even price). */
  shortfallC: number | null;
  /** Net at that bid, dollars for the whole position. */
  net: number | null;
}

/** A sale decided (the ratchet's or the end rule's), retried until the position is flat. */
export type PlanSaleKind = 'ratchet' | 'cut' | 'end';

/** The sale's name in notes and alerts. */
export const planSaleLabel = (k: PlanSaleKind): string => (k === 'end' ? 'end rule' : k === 'cut' ? 'loser cut' : 'ratchet');

export interface PlanSelling {
  kind: PlanSaleKind;
  since: number;
  /** Tries sent so far. */
  tries: number;
  /** When the last try was sent; unset once it is accounted for. */
  lastTryAt?: number;
  /** The 3-failed-tries alert went out. */
  alerted?: boolean;
}

/** The profit ratchet's state (armed, best and stop in dollars for the whole position) and the plan's sale. */
export interface PlanRatchetState extends RatchetState {
  failedTries: number;
  /** The armed tries that went out with the bid under the fee floor price (planMarkTried lists them). */
  gaps: PlanGap[];
  /** The minute clock: the minute (ms / 60 000, floored) of the last evaluation it saw. */
  lastMinute?: number;
  selling?: PlanSelling;
  /** Contracts held at the last evaluation: more now is an add, and the ratchet starts afresh. */
  size?: number;
}

export const freshPlanState = (): PlanRatchetState => ({ armed: false, failedTries: 0, gaps: [] });

/** Stage 0: sales at the bid less 2 ticks; after 3 failed tries an alert and the bid less 3 ticks. */
export const PLAN_SALE_TICKS = 2;
export const PLAN_ESCALATED_SALE_TICKS = 3;
export const PLAN_ALERT_AFTER_FAILED_TRIES = 3;
/** The end rule's share of the contract's window (the last tenth). */
export const PLAN_END_FRAC = 0.1;

const EPS = 1e-9;
const r4 = (x: number) => Math.round(x * 1e4) / 1e4;
/** Dollars with their sign: +$1.62, -$0.37. */
const usd = (x: number) => `${x < 0 ? '-' : '+'}$${Math.abs(x).toFixed(2)}`;

type Level = { price: number; size?: number };

/** The held side's bid (side terms): the YES bid for YES held, 1 - the YES ask for NO held; undefined when flat or missing. */
export function planSideBid(position: number, bid: Level | undefined, ask: Level | undefined): number | undefined {
  if (position > 0) return bid?.price;
  if (position < 0) return ask ? r4(1 - ask.price) : undefined;
  return undefined;
}

/** Net at a side price, dollars a contract: price - entry price - entry fee - the taker fee a contract of selling `count` there. */
export function planNetAt(count: number, price: number, entryPrice: number, entryFee: number, fees?: FeeSchedule): number {
  return price - entryPrice - entryFee - orderFee(count, price, true, fees) / count;
}

/** The lowest tick price whose net is at least 0 (break-even after both fees); undefined when no price under $1 does. */
export function planFeeFloorPrice(count: number, entryPrice: number, entryFee: number, tick: number, fees?: FeeSchedule): number | undefined {
  if (!(count > 0) || !(tick > 0) || !Number.isFinite(entryPrice)) return undefined;
  const last = Math.round(1 / tick) - 1;
  for (let k = Math.max(1, Math.floor((entryPrice + entryFee) / tick - EPS)); k <= last; k++) {
    const p = r4(k * tick);
    if (planNetAt(count, p, entryPrice, entryFee, fees) >= -EPS) return p;
  }
  return undefined;
}

/** The fee break-even of the ratchet's stop, dollars: the trade's smallest net at or above $0 on the price grid, the rest sold
 *  at the lowest tick price where what partial sales banked (`bankedUsd`) plus the rest's net is not under $0. $0 when no price
 *  breaks even, or when even the lowest price leaves the trade at $0 or more (nothing to guard). Every position's ratchet, a
 *  plan position's or any other's, gets this same number (bot/engine.ts, research/backtest.ts): one stop. */
export function planBreakEvenUsd(count: number, entryPrice: number | undefined, entryFee: number, bankedUsd: number, tick: number, fees?: FeeSchedule): number {
  if (!(count > 0) || !(tick > 0) || entryPrice === undefined || !Number.isFinite(entryPrice)) return 0;
  const last = Math.round(1 / tick) - 1;
  for (let k = 1; k <= last; k++) {
    const v = bankedUsd + count * planNetAt(count, r4(k * tick), entryPrice, entryFee, fees);
    if (v >= -EPS) return k === 1 ? 0 : r4(Math.max(0, v));
  }
  return 0;
}

/** The cut by time's points (Steven, Nov 12 06:01 UTC): `loserCut` once 60% of the window is gone, `loserCutLate` from 85%. */
export const PLAN_CUT_MID_FRAC = 0.6;
export const PLAN_CUT_LATE_FRAC = 0.85;

/** The price cut in force now, dollars a contract (0 = off), and the share of the window gone (unset without a window):
 *  `loserCutOpen` at the open, a straight line to `loserCut` at 60%, another to `loserCutLate` at 85%, flat after. A cut of
 *  0 (PLAN_LOSER_CUT_C=0) turns the price cut off at every point. A window the market was listed before (an hourly strike
 *  listed early, tau over the window) counts as just opened. */
export function planLoserCutAt(s: Pick<PlanRatchetSettings, 'loserCut' | 'loserCutOpen' | 'loserCutLate'>, tauSec: number, windowSec: number | undefined): { cut: number; elapsed?: number } {
  const mid = s.loserCut ?? 0;
  if (!(mid > 0)) return { cut: 0 };
  if (windowSec === undefined || !(windowSec > 0) || !Number.isFinite(tauSec)) return { cut: mid };
  const open = s.loserCutOpen ?? mid, late = s.loserCutLate ?? mid;
  const f = Math.min(1, Math.max(0, 1 - tauSec / windowSec));
  const cut = f <= PLAN_CUT_MID_FRAC ? open + (mid - open) * (f / PLAN_CUT_MID_FRAC)
    : f <= PLAN_CUT_LATE_FRAC ? mid + (late - mid) * ((f - PLAN_CUT_MID_FRAC) / (PLAN_CUT_LATE_FRAC - PLAN_CUT_MID_FRAC))
    : late;
  return { cut: r4(cut), elapsed: Math.round(f * 1000) / 1000 };
}

/** In the last tenth of the window (`windowSec`: shareWindowSec, bot/strategy/fairValueStrategy.ts). */
export function planEndWindow(tauSec: number, windowSec: number | undefined): boolean {
  return windowSec !== undefined && windowSec > 0 && tauSec <= PLAN_END_FRAC * windowSec + EPS;
}

/** The stop is never lowered: throws if a computation would (the profit ratchet's assertion). */
export const assertPlanStopNotLowered = assertStopNotLowered;

export type PlanEventName = 'plan_ratchet_arm' | 'plan_ratchet_raise' | 'plan_ratchet_sell' | 'plan_ratchet_gap' | 'plan_ratchet_retry' | 'plan_loser_cut_sell' | 'plan_loser_cut_cancel' | 'plan_end_rule_sell' | 'plan_end_rule_cancel';

/** One audit event (bot/engine.ts writes them under the audit kind 'plan'; the replay counts them). Prices in dollars, side terms. */
export interface PlanEvent {
  event: PlanEventName;
  ticker: string;
  side: 'yes' | 'no';
  ruleId: string;
  count: number;
  /** Held-side bid now (null: none). */
  bid: number | null;
  /** Net at that bid, dollars for the whole position held. */
  net: number | null;
  /** What partial sales of the position banked since it opened (set when not 0): net plus this is the trade's net, the
   *  ratchet's measure. */
  banked?: number;
  /** The ratchet's stop and best trade net since arming, dollars. */
  stop: number | null;
  best: number | null;
  /** The sale's limit (side terms), on a sale or retry. */
  limit: number | null;
  feeFloor: number | null;
  armUsd: number;
  stopMinUsd: number;
  trailUsd: number;
  clock: PlanClock;
  /** The loser cut's settings (set when on): dollars a contract under the entry price (at 60% of the window; at the open and
   *  from 85% when the cut scales), and dollars of trade net. */
  loserCut?: number;
  loserCutOpen?: number;
  loserCutLate?: number;
  loserCutUsd?: number;
  /** The entry price the price cut measures from (side terms), on a loser cut's sale. */
  entry?: number;
  /** On a loser cut's sale: the price cut in force (dollars a contract) and the share of the window gone (planLoserCutAt). */
  cutAt?: number;
  elapsed?: number;
  /** This evaluation (ms). */
  at: number;
  armedAt?: number;
  /** When the sale was decided (ms): a retry's first trigger. */
  since?: number;
  prevStop?: number;
  failedTries?: number;
  shortfallC?: number | null;
  tauSec?: number;
  /** A retry that counts no new failure: the try decided before it never went out (the kill switch's throttle, a refusal). */
  resend?: boolean;
  /** Set by the caller on an event that carries a sale's limit: whether that try went out (bot/engine.ts writes a resend
   *  only once one does). */
  sent?: boolean;
}

export interface PlanSale {
  /** An armed try whose bid is under the fee floor price: the gap planMarkTried lists once the try goes out. */
  gap?: PlanGap;
  /** The order in YES terms: a YES position sells YES (ask), a NO position buys YES (bid). */
  side: 'bid' | 'ask';
  price: number;
  /** The limit in side terms: the bid less 2 ticks (3 after 3 failed tries), at least 1 tick. */
  sideLimit: number;
  count: number;
  kind: PlanSaleKind;
  ticks: number;
  why: string;
}

export interface PlanStepInput {
  ticker: string;
  side: 'yes' | 'no';
  ruleId: string;
  /** Signed YES contracts held (+ YES, - NO). */
  position: number;
  bid: Level | undefined;
  ask: Level | undefined;
  /** openSidePrice / openEntryFee of the open position (bot/oms/positions.ts). */
  entryPrice: number | undefined;
  entryFeePerContract: number | undefined;
  /** openBankedUsd (bot/oms/positions.ts): what partial sales of the position banked since it opened; the ratchet measures
   *  this plus the net at the bid. 0 when not given. */
  bankedUsd?: number;
  fees?: FeeSchedule;
  tick: number;
  now: number;
  tauSec: number;
  /** The window the end rule's tenth measures (shareWindowSec). */
  windowSec: number | undefined;
  settings: PlanRatchetSettings;
  state: PlanRatchetState;
  /** An earlier sale order of ours is still working: wait for it (it is neither a failed try nor a new one). */
  orderInFlight?: boolean;
}

export interface PlanStepResult {
  state: PlanRatchetState;
  events: PlanEvent[];
  sale?: PlanSale;
  notes: string[];
  /** The 3-failed-tries alert, once a sale. */
  alert?: string;
}

/** One evaluation of a plan position: the retry of a sale under way, the ratchet on its clock, the loser cut on the same clock,
 *  then the end rule. The input state is not changed; the returned one replaces it. */
export function planStep(i: PlanStepInput): PlanStepResult {
  let s: PlanRatchetState = { ...i.state, gaps: [...i.state.gaps], ...(i.state.selling ? { selling: { ...i.state.selling } } : {}) };
  const count = Math.abs(i.position);
  // An add on the same side: the ratchet and any sale under way start afresh (the gaps listed and the minute clock stay).
  const grew = s.size !== undefined && count > s.size + EPS;
  if (grew) s = { ...freshPlanState(), gaps: s.gaps, ...(s.lastMinute !== undefined ? { lastMinute: s.lastMinute } : {}) };
  if (count > 1e-9) s.size = count;
  const out: PlanStepResult = { state: s, events: [], notes: grew ? ['plan ratchet: the position grew; its ratchet starts afresh'] : [] };
  if (!(count > 1e-9)) return out;
  const { armUsd, stopMinUsd, trailUsd, clock } = i.settings;
  const loserCut = i.settings.loserCut ?? 0;
  const loserCutUsd = i.settings.loserCutUsd ?? 0;
  const scaled = loserCut > 0 && ((i.settings.loserCutOpen ?? loserCut) !== loserCut || (i.settings.loserCutLate ?? loserCut) !== loserCut);
  // The price cut in force now (Steven, Nov 12: wider at the open, the flat 10c at 60% of the window, 3c from 85%).
  const cutNow = planLoserCutAt(i.settings, i.tauSec, i.windowSec);
  const tick = i.tick;
  const bid = planSideBid(i.position, i.bid, i.ask);
  const cost = i.entryPrice;
  const fee = i.entryFeePerContract ?? 0;
  // The whole position's net at the bid, dollars (netProfitAtBid's number): the one ratchet's measure.
  const net = bid !== undefined && cost !== undefined ? r4(count * planNetAt(count, bid, cost, fee, i.fees)) : undefined;
  // The trade's net, the ratchet's measure: the rest at the bid plus what partial sales banked. The end rule judges the rest.
  const banked = r4(i.bankedUsd ?? 0);
  const trade = net !== undefined ? r4(net + banked) : undefined;
  const bankedNote = Math.abs(banked) > 0.005 ? ` (${usd(banked)} banked by partial sales)` : '';
  const feeFloor = cost !== undefined ? planFeeFloorPrice(count, cost, fee, tick, i.fees) : undefined;
  const ev = (event: PlanEventName, x: Partial<PlanEvent> = {}): PlanEvent => {
    const e: PlanEvent = {
      event, ticker: i.ticker, side: i.side, ruleId: i.ruleId, count, bid: bid ?? null, net: net ?? null, ...(banked !== 0 ? { banked } : {}), stop: s.stop ?? null, best: s.best ?? null, limit: null,
      feeFloor: feeFloor ?? null, armUsd, stopMinUsd, trailUsd, clock, ...(loserCut > 0 ? { loserCut } : {}),
      ...(scaled ? { loserCutOpen: i.settings.loserCutOpen ?? loserCut, loserCutLate: i.settings.loserCutLate ?? loserCut } : {}), ...(loserCutUsd > 0 ? { loserCutUsd } : {}),
      at: i.now, tauSec: Math.round(i.tauSec * 10) / 10,
      ...(s.armedAt !== undefined ? { armedAt: s.armedAt } : {}), ...x,
    };
    out.events.push(e);
    return e;
  };
  const sell = (kind: PlanSaleKind, why: string): PlanSale => {
    const ticks = s.failedTries >= PLAN_ALERT_AFTER_FAILED_TRIES ? PLAN_ESCALATED_SALE_TICKS : PLAN_SALE_TICKS;
    const sideLimit = Math.max(tick, r4(bid! - ticks * tick));
    const yes = i.position > 0;
    out.sale = { side: yes ? 'ask' : 'bid', price: yes ? sideLimit : r4(1 - sideLimit), sideLimit, count, kind, ticks, why: `${why}; limit ${yes ? '' : 'NO '}${sideLimit.toFixed(2)} (bid less ${ticks} ticks)` };
    return out.sale;
  };
  const gap = (sale: PlanSale, resend = false): void => {
    // An armed try whose bid is already under the fee floor price (or with no break-even price at all): still sold, and
    // listed. The first try's and every retry's alike; the state lists it once the try goes out (planMarkTried).
    if (!s.armed || bid === undefined || (feeFloor !== undefined && bid >= feeFloor - EPS)) return;
    const shortfallC = feeFloor === undefined ? null : Math.round((feeFloor - bid) * 1e4) / 100;
    sale.gap = { at: i.now, bid, feeFloor: feeFloor ?? null, shortfallC, net: net ?? null };
    ev('plan_ratchet_gap', { shortfallC, limit: sale.sideLimit, ...(resend ? { resend } : {}) });
  };

  // 1. A sale under way goes again until the position is flat. A try that left it open failed (once counted, it is not again).
  if (s.selling) {
    const sel = s.selling;
    if (i.orderInFlight) { out.notes.push(`plan ${sel.kind} sale: an order is still working`); return out; }
    const failed = sel.lastTryAt !== undefined;
    if (failed) { s.failedTries++; sel.lastTryAt = undefined; }
    // A dollar cut whose trade (what partial sales banked plus the rest) is still at or under its line stays: calling it off
    // would only decide it again below, at every look, and its failed tries would never reach the alert.
    const cutStands = sel.kind === 'cut' && loserCutUsd > 0 && trade !== undefined && trade <= -loserCutUsd + EPS;
    if ((sel.kind === 'end' || sel.kind === 'cut') && net !== undefined && net >= -EPS && !cutStands) {
      // The end rule and the loser cut never sell a winner: back at or above break-even after both fees, the sale is called off
      // and the position is judged afresh below (the ratchet on its clock, the loser cut, then the end rule).
      delete s.selling;
      ev(sel.kind === 'end' ? 'plan_end_rule_cancel' : 'plan_loser_cut_cancel', { failedTries: s.failedTries, since: sel.since });
      out.notes.push(`plan ${planSaleLabel(sel.kind)}: back in profit after fees (net ${usd(net)} at bid ${bid!.toFixed(2)}): its sale is called off`);
    } else {
      if (bid === undefined) { out.notes.push(`plan ${planSaleLabel(sel.kind)} sale: no bid for the held side, waiting`); return out; }
      if (s.failedTries >= PLAN_ALERT_AFTER_FAILED_TRIES && !sel.alerted) {
        sel.alerted = true;
        out.alert = `Plan ${planSaleLabel(sel.kind)} sale of ${count} ${i.side.toUpperCase()} in ${i.ticker}: ${s.failedTries} failed tries; now selling at the bid less ${PLAN_ESCALATED_SALE_TICKS} ticks`;
      }
      const sale = sell(sel.kind, `plan ${planSaleLabel(sel.kind)} sale, try ${sel.tries + 1} (${s.failedTries} failed)`);
      gap(sale, !failed);
      ev('plan_ratchet_retry', { limit: sale.sideLimit, failedTries: s.failedTries, since: sel.since, ...(failed ? {} : { resend: true }) });
      return out;
    }
  }
  if (bid === undefined) { out.notes.push('plan position: no bid for the held side'); return out; }
  if (cost === undefined || net === undefined || trade === undefined) { out.notes.push('plan position: no cost basis'); return out; }

  // 2. The ratchet, on its clock.
  const minute = Math.floor(i.now / 60_000);
  let decide = clock === 'tick';
  if (clock === 'minute') {
    // The first sighting waits for the next minute close; after that, the first evaluation in each new minute decides.
    decide = s.lastMinute !== undefined && minute > s.lastMinute;
    if (s.lastMinute === undefined || minute > s.lastMinute) s.lastMinute = minute;
  }
  if (decide) {
    // The profit ratchet's core (bot/strategy/profitRatchet.ts): the same arm, stop, trail and fee break-even as every other
    // position's. Raise-only: ratchetStep throws before it would lower the stop.
    const breakEven = planBreakEvenUsd(count, cost, fee, banked, tick, i.fees);
    const r = ratchetStep({ armed: s.armed, armedAt: s.armedAt, best: s.best, stop: s.stop }, trade, i.settings, i.now, breakEven);
    s.armed = r.state.armed;
    if (r.state.armedAt !== undefined) s.armedAt = r.state.armedAt;
    if (r.state.best !== undefined) s.best = r.state.best;
    if (r.state.stop !== undefined) s.stop = r.state.stop;
    if (r.event === 'arm') ev('plan_ratchet_arm');
    else if (r.event === 'raise') ev('plan_ratchet_raise', { prevStop: r.prevStop });
    if (r.sell) {
      s.selling = { kind: 'ratchet', since: i.now, tries: 0 };
      const sale = sell('ratchet', `plan ratchet: net ${usd(trade)}${bankedNote} at bid ${bid.toFixed(2)} at or under its stop ${usd(s.stop!)} (best ${usd(s.best!)})`);
      gap(sale);
      ev('plan_ratchet_sell', { limit: sale.sideLimit, since: i.now });
      return out;
    }
  }
  if (s.armed) out.notes.push(`plan ratchet armed: bid ${bid.toFixed(2)}, net ${usd(trade)}${bankedNote}, stop ${usd(s.stop!)}, best ${usd(s.best!)}`);
  else out.notes.push(`plan ratchet: net ${usd(trade)}${bankedNote}, arms at ${usd(armUsd)} (${clock} clock)`);

  // 3. The loser cut, on the same clock: the bid the cut in force (planLoserCutAt: PLAN_LOSER_CUT_OPEN_C at the open, PLAN_LOSER_CUT_C
  //    at 60% of the window, PLAN_LOSER_CUT_LATE_C from 85%) or more under the entry price, or the trade's net at or under
  //    minus PLAN_LOSER_CUT_USD. Sold the way the ratchet's sale is.
  const cutLine = cutNow.cut > 0 ? r4(cost - cutNow.cut) : undefined;
  const cutC = (x: number) => `${Math.round(x * 1000) / 10}c`;
  const when = cutNow.elapsed !== undefined && scaled ? `, ${Math.round(cutNow.elapsed * 100)}% of the window gone` : '';
  if (decide) {
    const byPrice = cutLine !== undefined && bid <= cutLine + EPS;
    const byUsd = loserCutUsd > 0 && trade <= -loserCutUsd + EPS;
    if (byPrice || byUsd) {
      s.selling = { kind: 'cut', since: i.now, tries: 0 };
      const what = byPrice
        ? `bid ${bid.toFixed(2)} is ${Math.round((cost - bid) * 100)}c under the entry ${cost.toFixed(2)} (cut at ${cutC(cutNow.cut)}${when})`
        : `net ${usd(trade)}${bankedNote} at bid ${bid.toFixed(2)} at or under -$${loserCutUsd.toFixed(2)}`;
      const sale = sell('cut', `plan loser cut: ${what}`);
      gap(sale);
      ev('plan_loser_cut_sell', { limit: sale.sideLimit, since: i.now, entry: cost, ...(cutNow.cut > 0 ? { cutAt: cutNow.cut } : {}), ...(cutNow.elapsed !== undefined ? { elapsed: cutNow.elapsed } : {}) });
      return out;
    }
  }
  if (cutLine !== undefined || loserCutUsd > 0) {
    const lines = [cutLine !== undefined ? `bid at or under ${cutLine.toFixed(2)} (${cutC(cutNow.cut)}${when})` : '', loserCutUsd > 0 ? `net at or under -$${loserCutUsd.toFixed(2)}` : ''];
    out.notes.push(`plan loser cut: sells at ${lines.filter(Boolean).join(' or ')}`);
  }

  // 4. The end rule: out of profit in the last tenth of the window is sold; a winner rides.
  if (planEndWindow(i.tauSec, i.windowSec)) {
    if (net < -EPS) {
      s.selling = { kind: 'end', since: i.now, tries: 0 };
      const sale = sell('end', `plan end rule: ${Math.round(i.tauSec)} s to the close, net ${usd(net)} at bid ${bid.toFixed(2)}`);
      gap(sale);
      ev('plan_end_rule_sell', { limit: sale.sideLimit, since: i.now });
      return out;
    }
    out.notes.push(`plan end rule: ${Math.round(i.tauSec)} s to the close, in profit after fees: rides`);
  }
  return out;
}

/** The sale `planStep` returned went out (past the risk gateway, to the exchange): its result is judged at the next
 *  evaluation. A sale that did not go out is not marked, and goes again as a resend, not as a failed try. */
export function planMarkTried(state: PlanRatchetState, now: number, sale?: Pick<PlanSale, 'gap'>): PlanRatchetState {
  if (!state.selling) return state;
  return { ...state, ...(sale?.gap ? { gaps: [...state.gaps, sale.gap] } : {}), selling: { ...state.selling, tries: state.selling.tries + 1, lastTryAt: now } };
}
