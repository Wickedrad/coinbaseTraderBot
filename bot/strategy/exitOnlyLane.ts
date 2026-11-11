// The exit-only lane (E06). The Kalshi feed is current and the market's book fresh, but the market cannot be priced this tick:
// the settlement index is stale, its volatility is still warming up (120 one-second returns: about 2 minutes after every
// restart or deploy), the strike is unknown, the book is one-sided or there is no fair value. Quoting stops; a held position
// still gets the exits already armed that need no model: the take-profit trailing its best, the quota floor (PACER_FLOOR), the
// profit ratchet's stop (RATCHET, bot/strategy/profitRatchet.ts) and the hunt's armed stop (ConfluenceRatchetExit.armed). The final minute and the settle-in-profit rule hold them as in a full
// evaluation. No model exit (the loser cut), no quota snipe, no entry or quote goes out here. Feed lag and a stale book never
// reach the lane: they halt everything. One plan for the engine (bot/engine.ts, paper and live alike) and the replay
// (research/backtest.ts); each sends it through its own risk check, judged against the book's mid (laneFairValue).

import type { RiskLimits, StrategyConfig } from '../config';
import type { FeeSchedule } from '../fees';
import type { ConfluenceRatchetExit, HuntArmed } from './exitPolicies';
import { decide, ridesToSettlement, shareWindowSec, type MarketView, type OrderPlan, type StrategyOutput } from './fairValueStrategy';
import type { RatchetReading } from './profitRatchet';

type Level = { price: number; size: number };

/** The held side's bid (side terms): the YES bid for YES held, 1 - the YES ask for NO held; undefined when flat or missing. */
export function heldSideBid(position: number, bid: Level | undefined, ask: Level | undefined): number | undefined {
  if (position > 0) return bid?.price;
  if (position < 0) return ask ? Math.round((1 - ask.price) * 1e4) / 1e4 : undefined;
  return undefined;
}

/** The lane's view of a held position, or undefined when there is nothing to sell into (flat, or no bid for the held side).
 *  pYes is the lane's fair value for the risk gateway: the book's mid, or the held side's touch on a one-sided book (YES
 *  terms). Nothing in it can size an entry: no bankroll, no order room, the entry window shut. */
export function exitOnlyView(i: {
  ticker: string; position: number; bid: Level | undefined; ask: Level | undefined; now: number; openTime: number; closeTime: number; tickSize: number; fees: FeeSchedule;
  strategy: Pick<StrategyConfig, 'noExitBeforeCloseSec' | 'noExitBeforeCloseFrac' | 'shareWindowMaxSec'>; risk: Pick<RiskLimits, 'minSidePrice' | 'noEntryBeforeCloseSec'>;
  entrySidePrice: number | undefined; entryFeePerContract: number | undefined; profitPeakSidePrice: number | undefined; takeProfitBenched: string | undefined;
  /** openBankedUsd: what partial sales of the position banked since it opened (the profit ratchet measures the trade). */
  bankedUsd?: number;
}): MarketView | undefined {
  if (Math.abs(i.position) < 1e-9 || heldSideBid(i.position, i.bid, i.ask) === undefined) return undefined;
  const pYes = i.bid && i.ask ? (i.bid.price + i.ask.price) / 2 : i.position > 0 ? i.bid!.price : i.ask!.price;
  const tauSec = (i.closeTime - i.now) / 1000;
  const S = i.strategy;
  return {
    ticker: i.ticker, pYes, bestBid: i.bid, bestAsk: i.ask, position: i.position, bankroll: 0,
    maxOrderRiskUsd: 0, maxContracts: 0, minSidePrice: i.risk.minSidePrice, tauSec, noEntryBeforeCloseSec: i.risk.noEntryBeforeCloseSec, fastMove: false,
    tickSize: i.tickSize, fees: i.fees, nowSec: Math.floor(i.now / 1000), closeSec: Math.floor(i.closeTime / 1000),
    entrySidePrice: i.entrySidePrice !== undefined && i.entrySidePrice > 0 && i.entrySidePrice < 1 ? i.entrySidePrice : undefined,
    entryFeePerContract: i.entryFeePerContract,
    ...(i.bankedUsd ? { bankedUsd: i.bankedUsd } : {}),
    profitPeakSidePrice: i.profitPeakSidePrice,
    ...(i.takeProfitBenched ? { takeProfitBenched: i.takeProfitBenched } : {}),
    entryWindowOpen: false, exitWindowOpen: tauSec > S.noExitBeforeCloseSec,
    settleShare: ((w) => w !== undefined && tauSec <= S.noExitBeforeCloseFrac * w)(shareWindowSec(i.openTime, i.closeTime, S.shareWindowMaxSec)),
  };
}

export interface ExitOnlyPlan {
  plan: StrategyOutput;
  /** The hunt's reading (undefined: no hunt on the position). */
  hunt?: HuntArmed;
  /** The hunt's stop sale, when it goes out (first in plan.place). */
  huntPlan?: OrderPlan;
  /** The quota floor's sale, when it goes out. */
  floorSale?: OrderPlan;
  /** The profit ratchet's sale, when it goes out (it may carry the quota floor's label when both sell). */
  ratchetSale?: OrderPlan;
}

/** What the lane sells for a held position (`view`: exitOnlyView). `exits`: the exit policy runs the built-in exits (the
 *  take-profit); `hunt`: the position's hunt when hunt mode may run; `pacerFloor`: its armed floor (undefined with
 *  PACER_FLOOR off). Only immediate-or-cancel reduce-only exits come out: decide() runs armed-only with entries off. */
export function exitOnlyPlan(view: MarketView, strategy: StrategyConfig, o: { why: string; exits: boolean; hunt?: ConfluenceRatchetExit; pacerUsd?: number; pacerFloor?: number; ratchet?: RatchetReading }): ExitOnlyPlan {
  // The hunt is read, not updated: its stop does not walk, and a judgement that needs the model waits for the data.
  const hunt = o.hunt?.armed({ position: view.position, sideBid: heldSideBid(view.position, view.bestBid, view.bestAsk), tick: view.tickSize });
  const hunting = hunt?.hunting === true;
  const plan = decide(view, strategy, { exits: o.exits && !hunting, entries: false, armedOnly: true, pacerUsd: o.pacerUsd, ...(o.pacerFloor !== undefined ? { pacerFloor: o.pacerFloor } : {}), ...(o.ratchet ? { ratchet: o.ratchet } : {}) });
  const floorSale = plan.place.find((p) => p.purpose === 'exit' && p.why.startsWith('quota snipe'));
  // The profit ratchet's stop sells the whole position as the quota floor does.
  const ratchetSale = plan.place.find((p) => p.purpose === 'exit' && p.liquidation?.ratchet === true);
  let huntPlan: OrderPlan | undefined, huntHeld: string | undefined;
  if (hunt?.plan && (view.exitWindowOpen === false || ridesToSettlement(view))) {
    huntHeld = view.exitWindowOpen === false ? `hunting: stop ${hunt.plan.stop} held, ${Math.round(view.tauSec)} s to the close` : `hunting: stop ${hunt.plan.stop} held: in profit in the last share of the window, riding to settlement`;
  } else if (hunt?.plan && !floorSale && !ratchetSale) {
    // A quota floor or profit ratchet sale liquidates the position: the hunt's stop order would only double it.
    huntPlan = { side: hunt.plan.side, price: hunt.plan.price, count: hunt.plan.count, timeInForce: 'immediate_or_cancel', postOnly: false, reduceOnly: true, purpose: 'exit', edge: 0, why: `confluence ratchet stop ${hunt.plan.stop}` };
    plan.place.unshift(huntPlan);
  }
  if (hunting) plan.notes.push(huntHeld ?? `hunting: stop ${hunt?.stop ?? 'forming'}`);
  if (hunt?.note) plan.notes.push(hunt.note);
  plan.notes.unshift(`exit-only lane (${o.why}): only exits already armed (take-profit, quota floor, profit ratchet, hunt stop); no model exit, no entry`);
  plan.place = plan.place.filter((p) => p.purpose === 'exit' && p.reduceOnly && p.timeInForce === 'immediate_or_cancel');
  return { plan, hunt, huntPlan, ...(floorSale ? { floorSale } : {}), ...(ratchetSale ? { ratchetSale } : {}) };
}
