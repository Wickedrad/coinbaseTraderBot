// The per-order stake for a Kalshi crypto entry or maker quote: one function for the engine, the backtester and the
// sweeps, so a replay sizes orders exactly as the bot does (phase 2 of the dynamic-scaling plan, Oct 28).
//
//   maxOrderRiskUsd = min(tier.orderFrac x bankroll x sizeMult x riskScale, optimal f cap x bankroll)
//
//   sizeMult   the session's size factor x the regime weight (Compensator, else the playbook): market conditions.
//              Above 1 it grows the dollar stake only: contracts per order never pass RISK_MAX_CONTRACTS_PER_ORDER.
//   riskScale  the loss-aware scale (EquityGuard: full size at break-even, shrinking with net losses)
//   optimal f  the growth-optimal stake the bot's own settled trades support, at a bootstrap quantile
//              (bot/strategy/optimalF.ts): the measured edge, with a margin for how uncertain it is. Infinity until
//              there are enough trades; paper floors it so evidence keeps coming.
//
// Kelly then sizes inside that budget from the trade's own edge (bot/sizing/kelly.ts). The order band (ORDER_USD_MIN /
// ORDER_USD_MAX, $10-$20 since Steven's choice on Oct 30, paper and live) replaces the budget: the budget is the band's top
// and the strategy clamps Kelly's stake into the band. The paper order size (PAPER_ORDER_FRAC / PAPER_ORDER_USD, off by
// default since the owner's choice on Oct 28: paper sizes like live) replaces all of it when set. BAND_SIZE_MULT (Steven,
// Nov 5) lets sizeMult scale the band and the paper size too: shrink (never above the top) or scale (up to BAND_SIZE_MAX).
import { floorCount } from '../util/num';

export interface OrderBudgetInput {
  bankroll: number;
  /** The tier's per-order fraction of the bankroll. */
  orderFrac: number;
  /** Session size factor x regime weight. */
  sizeMult: number;
  /** Loss-aware risk scale. */
  riskScale: number;
  /** Optimal f cap in dollars (Infinity = none). */
  fCapUsd: number;
  /** Paper's fixed order size in dollars (0 = paper sizes like live). */
  paperOrderUsd: number;
  /** The order band in dollars (orderBand(); undefined = off). */
  bandUsd?: { min: number; max: number };
  maxContractsPerOrder: number;
  /** BAND_SIZE_MULT: whether sizeMult scales the band and the paper order size (off = it does not). */
  bandSizeMult?: 'off' | 'shrink' | 'scale';
  /** BAND_SIZE_MAX: the top factor for bandSizeMult 'scale'. */
  bandSizeMax?: number;
}

/** The factor the band and the paper order size take from sizeMult (1 = unchanged). */
export function bandFactor(sizeMult: number, mode: 'off' | 'shrink' | 'scale' = 'off', max = 1.5): number {
  if (mode === 'off' || !Number.isFinite(sizeMult)) return 1;
  const m = Math.max(0, sizeMult);
  return mode === 'shrink' ? Math.min(1, m) : Math.min(m, Math.max(1, max));
}

const cents = (x: number) => Math.round(x * 100) / 100;

export interface OrderBudget {
  maxOrderRiskUsd: number;
  maxContracts: number;
  /** Set only while a paper order size is in use. */
  fixedOrderUsd?: number;
  /** Set only while the order band is in use: the strategy clamps the sized stake into it. */
  band?: { min: number; max: number };
  /** What bound the stake: tier (the tier x factors), optimal_f, paper, or band. */
  boundBy: 'tier' | 'optimal_f' | 'paper' | 'band';
}

/** The order band from ORDER_USD_MIN / ORDER_USD_MAX: undefined when the minimum is 0 (off); the top never below the
 *  minimum. */
export function orderBand(minUsd: number | undefined, maxUsd: number | undefined): { min: number; max: number } | undefined {
  const min = Math.max(0, minUsd ?? 0);
  return min > 0 ? { min, max: Math.max(min, maxUsd ?? 0) } : undefined;
}

export function orderBudget(i: OrderBudgetInput): OrderBudget {
  const k = bandFactor(i.sizeMult, i.bandSizeMult, i.bandSizeMax);
  if (i.paperOrderUsd > 0) {
    const usd = cents(i.paperOrderUsd * k);
    return { maxOrderRiskUsd: usd, maxContracts: floorCount(i.maxContractsPerOrder), ...(usd > 0 ? { fixedOrderUsd: usd } : {}), boundBy: 'paper' };
  }
  if (i.bandUsd && i.bandUsd.min > 0) {
    // A session or regime that sizes to 0 places nothing (no band left to clamp into).
    if (!(k > 0)) return { maxOrderRiskUsd: 0, maxContracts: 0, boundBy: 'band' };
    const band = k === 1 ? i.bandUsd : { min: cents(i.bandUsd.min * k), max: cents(i.bandUsd.max * k) };
    return { maxOrderRiskUsd: band.max, maxContracts: floorCount(i.maxContractsPerOrder), band, boundBy: 'band' };
  }
  const tierUsd = i.orderFrac * i.bankroll * i.sizeMult * i.riskScale;
  const capped = Number.isFinite(i.fCapUsd) && i.fCapUsd < tierUsd;
  return { maxOrderRiskUsd: capped ? i.fCapUsd : tierUsd, maxContracts: floorCount(i.maxContractsPerOrder * Math.min(1, i.sizeMult)), boundBy: capped ? 'optimal_f' : 'tier' };
}
