// The plan's one written ratchet and its end rule (pipeline plan, Stage 0; Steven's decisions 3 and 13, approved Nov 11,
// 8:03 AM EST / 13:03 UTC). For positions opened by the plan's rules (bot/plan/planPositions.ts), behind PLAN_RULES (off by
// default, paper and live alike). Pure: no I/O. The engine (bot/engine.ts, paper and live) and the replay
// (research/backtest.ts) run this same function.
//
// Everything is per contract. Prices are side terms in dollars (a YES position's YES price, a NO position's NO price); the
// settings are in cents.
//   held-side bid   the YES bid for a YES position, the NO bid (1 - the YES ask) for a NO position
//   net at bid      bid - entry price - entry fee a contract - the taker exit fee a contract at that bid (the whole position
//                   sold there: Kalshi rounds each order's fee up to the cent), with THE cost basis of the open contracts
//                   (openSidePrice / openEntryFee, bot/oms/positions.ts)
//   fee floor price the lowest tick price whose net is at least 0: break-even after both fees
//   arm             net at bid >= armC: peak = bid, floor = max(fee floor price, peak - trailC)
//   raise           while armed, each evaluation on the rule's clock: peak = max(peak, bid),
//                   floor = max(floor, fee floor price, peak - trailC). The floor is never lowered (asserted).
//   sell            armed and bid <= floor: one reduce-only immediate-or-cancel sale of the whole position at a limit of the
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
// The ratchet sale and the end rule are the plan's own rules: they are not held by STRATEGY_NO_EXIT_BEFORE_CLOSE_SEC.

import { orderFee, type FeeSchedule } from '../fees';

export type PlanClock = 'tick' | 'minute';

/** A position's ratchet settings, in cents a contract. Each frozen rule passes its own tested values. */
export interface PlanRatchetSettings {
  armC: number;
  trailC: number;
  clock: PlanClock;
}

/** PLAN_RULES and the default ratchet settings (bot/config.ts). */
export interface PlanConfig {
  /** PLAN_RULES (default false, the same in paper and live): positions opened by plan rules get this ratchet and end rule, and
   *  the pacer only reports pace for them. Off, every position is managed as before, tagged or not. */
  enabled: boolean;
  /** PLAN_RATCHET_ARM_C (6) and PLAN_RATCHET_TRAIL_C (8): the settings a tagged position gets when its rule passes none.
   *  UNTESTED placeholders: no replay has tested them; each frozen rule passes its own tested values. */
  armC: number;
  trailC: number;
}

/** A price gap: the bid that triggered an armed sale was already under the fee floor price. */
export interface PlanGap {
  at: number;
  bid: number;
  /** null: no price under $1 breaks even. */
  feeFloor: number | null;
  /** How far under the fee floor price the bid was, in cents a contract (null: no break-even price). */
  shortfallC: number | null;
  /** Net at that bid, dollars a contract. */
  net: number | null;
}

/** A sale decided (the ratchet's or the end rule's), retried until the position is flat. */
export interface PlanSelling {
  kind: 'ratchet' | 'end';
  since: number;
  /** Tries sent so far. */
  tries: number;
  /** When the last try was sent; unset once it is accounted for. */
  lastTryAt?: number;
  /** The 3-failed-tries alert went out. */
  alerted?: boolean;
}

export interface PlanRatchetState {
  armed: boolean;
  armedAt?: number;
  peakBid?: number;
  floor?: number;
  failedTries: number;
  /** The armed tries that went out with the bid under the fee floor price (planMarkTried lists them). */
  gaps: PlanGap[];
  /** The minute clock: the minute (ms / 60 000, floored) of the last evaluation it saw. */
  lastMinute?: number;
  selling?: PlanSelling;
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

/** In the last tenth of the window (`windowSec`: shareWindowSec, bot/strategy/fairValueStrategy.ts). */
export function planEndWindow(tauSec: number, windowSec: number | undefined): boolean {
  return windowSec !== undefined && windowSec > 0 && tauSec <= PLAN_END_FRAC * windowSec + EPS;
}

/** The floor is never lowered: throws if a computation would. */
export function assertFloorNotLowered(prev: number | undefined, next: number | undefined): void {
  if (prev !== undefined && (next === undefined || next < prev - EPS)) throw new Error(`plan ratchet: floor lowered from ${prev} to ${next}`);
}

export type PlanEventName = 'plan_ratchet_arm' | 'plan_ratchet_raise' | 'plan_ratchet_sell' | 'plan_ratchet_gap' | 'plan_ratchet_retry' | 'plan_end_rule_sell' | 'plan_end_rule_cancel';

/** One audit event (bot/engine.ts writes them under the audit kind 'plan'; the replay counts them). Prices in dollars, side terms. */
export interface PlanEvent {
  event: PlanEventName;
  ticker: string;
  side: 'yes' | 'no';
  ruleId: string;
  count: number;
  /** Held-side bid now (null: none). */
  bid: number | null;
  /** Net at that bid, dollars a contract. */
  net: number | null;
  floor: number | null;
  /** The sale's limit (side terms), on a sale or retry. */
  limit: number | null;
  feeFloor: number | null;
  peak: number | null;
  armC: number;
  trailC: number;
  clock: PlanClock;
  /** This evaluation (ms). */
  at: number;
  armedAt?: number;
  /** When the sale was decided (ms): a retry's first trigger. */
  since?: number;
  prevFloor?: number;
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
  kind: 'ratchet' | 'end';
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

/** One evaluation of a plan position: the retry of a sale under way, the ratchet on its clock, then the end rule. The input
 *  state is not changed; the returned one replaces it. */
export function planStep(i: PlanStepInput): PlanStepResult {
  const s: PlanRatchetState = { ...i.state, gaps: [...i.state.gaps], ...(i.state.selling ? { selling: { ...i.state.selling } } : {}) };
  const out: PlanStepResult = { state: s, events: [], notes: [] };
  const count = Math.abs(i.position);
  if (!(count > 1e-9)) return out;
  const { armC, trailC, clock } = i.settings;
  const tick = i.tick;
  const bid = planSideBid(i.position, i.bid, i.ask);
  const cost = i.entryPrice;
  const fee = i.entryFeePerContract ?? 0;
  const net = bid !== undefined && cost !== undefined ? r4(planNetAt(count, bid, cost, fee, i.fees)) : undefined;
  const feeFloor = cost !== undefined ? planFeeFloorPrice(count, cost, fee, tick, i.fees) : undefined;
  const ev = (event: PlanEventName, x: Partial<PlanEvent> = {}): PlanEvent => {
    const e: PlanEvent = {
      event, ticker: i.ticker, side: i.side, ruleId: i.ruleId, count, bid: bid ?? null, net: net ?? null, floor: s.floor ?? null, limit: null,
      feeFloor: feeFloor ?? null, peak: s.peakBid ?? null, armC, trailC, clock, at: i.now, tauSec: Math.round(i.tauSec * 10) / 10,
      ...(s.armedAt !== undefined ? { armedAt: s.armedAt } : {}), ...x,
    };
    out.events.push(e);
    return e;
  };
  const sell = (kind: 'ratchet' | 'end', why: string): PlanSale => {
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
    if (sel.kind === 'end' && net !== undefined && net >= -EPS) {
      // The end rule never sells a winner: back at or above break-even after both fees, its sale is called off and the position
      // is judged afresh below (the ratchet on its clock, then the end rule).
      delete s.selling;
      ev('plan_end_rule_cancel', { failedTries: s.failedTries, since: sel.since });
      out.notes.push(`plan end rule: back in profit after fees (net ${(net * 100).toFixed(1)}c a contract at bid ${bid!.toFixed(2)}): its sale is called off`);
    } else {
      if (bid === undefined) { out.notes.push(`plan ${sel.kind} sale: no bid for the held side, waiting`); return out; }
      if (s.failedTries >= PLAN_ALERT_AFTER_FAILED_TRIES && !sel.alerted) {
        sel.alerted = true;
        out.alert = `Plan ${sel.kind === 'end' ? 'end rule' : 'ratchet'} sale of ${count} ${i.side.toUpperCase()} in ${i.ticker}: ${s.failedTries} failed tries; now selling at the bid less ${PLAN_ESCALATED_SALE_TICKS} ticks`;
      }
      const sale = sell(sel.kind, `plan ${sel.kind === 'end' ? 'end rule' : 'ratchet'} sale, try ${sel.tries + 1} (${s.failedTries} failed)`);
      gap(sale, !failed);
      ev('plan_ratchet_retry', { limit: sale.sideLimit, failedTries: s.failedTries, since: sel.since, ...(failed ? {} : { resend: true }) });
      return out;
    }
  }
  if (bid === undefined) { out.notes.push('plan position: no bid for the held side'); return out; }
  if (cost === undefined || net === undefined) { out.notes.push('plan position: no cost basis'); return out; }

  // 2. The ratchet, on its clock.
  const minute = Math.floor(i.now / 60_000);
  let decide = clock === 'tick';
  if (clock === 'minute') {
    // The first sighting waits for the next minute close; after that, the first evaluation in each new minute decides.
    decide = s.lastMinute !== undefined && minute > s.lastMinute;
    if (s.lastMinute === undefined || minute > s.lastMinute) s.lastMinute = minute;
  }
  const trail = trailC / 100;
  if (decide) {
    if (!s.armed) {
      if (net >= armC / 100 - EPS) {
        s.armed = true;
        s.armedAt = i.now;
        s.peakBid = bid;
        s.floor = r4(Math.max(feeFloor ?? -Infinity, bid - trail));
        ev('plan_ratchet_arm');
      }
    } else {
      const prev = s.floor;
      s.peakBid = Math.max(s.peakBid ?? bid, bid);
      const next = r4(Math.max(prev ?? -Infinity, feeFloor ?? -Infinity, s.peakBid - trail));
      assertFloorNotLowered(prev, next);
      s.floor = next;
      if (prev === undefined || next > prev + EPS) ev('plan_ratchet_raise', { prevFloor: prev });
    }
    if (s.armed && s.floor !== undefined && bid <= s.floor + EPS) {
      s.selling = { kind: 'ratchet', since: i.now, tries: 0 };
      const sale = sell('ratchet', `plan ratchet: bid ${bid.toFixed(2)} at or under its floor ${s.floor.toFixed(2)} (peak ${s.peakBid!.toFixed(2)}, net ${(net * 100).toFixed(1)}c a contract)`);
      gap(sale);
      ev('plan_ratchet_sell', { limit: sale.sideLimit, since: i.now });
      return out;
    }
  }
  if (s.armed) out.notes.push(`plan ratchet armed: bid ${bid.toFixed(2)}, floor ${s.floor!.toFixed(2)}, peak ${s.peakBid!.toFixed(2)}, net ${(net * 100).toFixed(1)}c`);
  else out.notes.push(`plan ratchet: net ${(net * 100).toFixed(1)}c a contract, arms at ${armC}c (${clock} clock)`);

  // 3. The end rule: out of profit in the last tenth of the window is sold; a winner rides.
  if (planEndWindow(i.tauSec, i.windowSec)) {
    if (net < -EPS) {
      s.selling = { kind: 'end', since: i.now, tries: 0 };
      const sale = sell('end', `plan end rule: ${Math.round(i.tauSec)} s to the close, net ${(net * 100).toFixed(1)}c a contract at bid ${bid.toFixed(2)}`);
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
