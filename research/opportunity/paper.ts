/** Dollar-per-contract paper policy. Produces recommendations only; no exchange/order imports. */
import type { ContractPathForecast } from './contractTiming';
import { assessContractTiming } from './contractTiming';
import type { ContractObservation } from './contractDataset';

export interface PaperQuote {
  ticker: string; side: 'yes' | 'no'; at: number; knownAt: number;
  bid: number | null; ask: number | null; bidSize: number; askSize: number;
  entryFee: number; exitFee: number; settlementFee: number; slippage: number;
  sourceSha256: string;
}
export interface PaperPolicy {
  minimumMoveLowerBound: number; minimumJointLowerBound: number; minimumEntryEdge: number;
  maximumQuoteAgeMs: number; maximumPosition: number;
}
export interface PaperPosition { ticker: string; side: 'yes' | 'no'; quantity: number; averageEntryCost: number }
export interface PaperDecision {
  researchOnly: true; liveEntryAllowed: false; action: 'abstain' | 'wait' | 'enter' | 'hold' | 'reduce' | 'exit';
  reason: string; quantityChange: number; targetQuantity: number; modelId: string | null;
  entryEdgeLower: number | null; holdValueLower: number | null; liquidationValue: number | null;
}
export function validatePaperPolicy(p: PaperPolicy) {
  if (!Number.isFinite(p.minimumMoveLowerBound) || p.minimumMoveLowerBound <= 0.5 || p.minimumMoveLowerBound > 1 ||
      !Number.isFinite(p.minimumJointLowerBound) || p.minimumJointLowerBound < 0 || p.minimumJointLowerBound > 1 ||
      !Number.isFinite(p.minimumEntryEdge) || p.minimumEntryEdge < 0 ||
      !Number.isSafeInteger(p.maximumQuoteAgeMs) || p.maximumQuoteAgeMs < 0 ||
      !Number.isSafeInteger(p.maximumPosition) || p.maximumPosition < 0) throw new Error('invalid explicit paper policy');
}
export function quoteAvailable(q: PaperQuote, o: ContractObservation, maximumAgeMs: number) {
  return q.ticker === o.query.contract.ticker && q.side === o.query.side &&
    Number.isSafeInteger(q.at) && Number.isSafeInteger(q.knownAt) && q.at <= q.knownAt && q.knownAt <= o.query.asOf &&
    o.query.asOf - q.at <= maximumAgeMs && q.at >= o.query.contract.openTime &&
    /^[a-f0-9]{64}$/.test(q.sourceSha256) &&
    [q.entryFee, q.exitFee, q.settlementFee, q.slippage].every((v) => Number.isFinite(v) && v >= 0) &&
    [q.bidSize, q.askSize].every((v) => Number.isSafeInteger(v) && v >= 0) &&
    [q.bid, q.ask].every((v) => v === null || (Number.isFinite(v) && v >= 0 && v <= 1)) &&
    (q.bid === null || q.ask === null || q.bid <= q.ask);
}
/** `riskApprovedQuantity` and `remainingRiskDollars` are supplied by the caller's risk
 * controls. Forecast strength never grants a larger allowance. Entry costs are sunk
 * when comparing holding an existing position with selling it now. */
export function evaluatePaperPosition(o: ContractObservation, forecast: ContractPathForecast | null, quote: PaperQuote | null,
  position: PaperPosition | null, policy: PaperPolicy,
  allowance: { riskApprovedQuantity: number; remainingRiskDollars: number }): PaperDecision {
  validatePaperPolicy(policy);
  const qty = position?.quantity ?? 0;
  if (!Number.isSafeInteger(qty) || qty < 0 || (position && (position.ticker !== o.query.contract.ticker || position.side !== o.query.side ||
      !Number.isFinite(position.averageEntryCost) || position.averageEntryCost < 0)) ||
      !Number.isSafeInteger(allowance.riskApprovedQuantity) || allowance.riskApprovedQuantity < 0 ||
      !Number.isFinite(allowance.remainingRiskDollars) || allowance.remainingRiskDollars < 0) throw new Error('invalid position/risk allowance');
  const out: PaperDecision = { researchOnly: true, liveEntryAllowed: false, action: 'abstain', reason: 'qualified exact-contract forecast unavailable',
    quantityChange: 0, targetQuantity: qty, modelId: forecast?.modelId ?? null,
    entryEdgeLower: null, holdValueLower: null, liquidationValue: null };
  if (!quote || !quoteAvailable(quote, o, policy.maximumQuoteAgeMs)) return { ...out, reason: 'fresh compatible quote, depth and explicit costs required' };
  const capacity = Math.min(policy.maximumPosition, allowance.riskApprovedQuantity);
  const liquidate = quote.bid === null ? null : quote.bid - quote.exitFee - quote.slippage;
  out.liquidationValue = liquidate;
  if (qty > capacity) {
    if (liquidate === null || quote.bidSize === 0) return { ...out, reason: 'risk reduction required; liquidation quote unavailable' };
    const sell = Math.min(qty - capacity, quote.bidSize);
    return { ...out, action: sell === qty ? 'exit' : 'reduce', reason: 'caller risk allowance requires reduction', quantityChange: -sell, targetQuantity: qty - sell };
  }
  const assessment = assessContractTiming(o.query, forecast ? [forecast] : [], policy);
  if (!assessment.calibrationRef || !assessment.sidePays || !assessment.forecastId) return out;
  const pays = assessment.sidePays;
  out.holdValueLower = pays.lower - quote.settlementFee;
  if (qty) {
    if (liquidate !== null && pays.upper - quote.settlementFee < liquidate && quote.bidSize > 0) {
      const sell = Math.min(qty, quote.bidSize);
      return { ...out, action: sell === qty ? 'exit' : 'reduce', reason: 'liquidation exceeds even the upper hold estimate', quantityChange: -sell, targetQuantity: qty - sell };
    }
    return { ...out, action: 'hold', reason: liquidate === null ? 'liquidation unavailable; no increase proposed' :
      out.holdValueLower > liquidate ? 'lower hold estimate exceeds liquidation' : 'hold/liquidate uncertainty overlaps; no increase proposed' };
  }
  if (quote.ask === null || quote.askSize === 0) return { ...out, action: 'wait', reason: 'entry quote/depth unavailable' };
  const cost = quote.ask + quote.entryFee + quote.slippage;
  out.entryEdgeLower = pays.lower - quote.settlementFee - cost;
  if (assessment.status !== 'timing-supported' || out.entryEdgeLower < policy.minimumEntryEdge) return { ...out, action: 'wait', reason: 'timing confidence or fee-net lower edge insufficient' };
  const buy = Math.min(capacity, quote.askSize, cost > 0 ? Math.floor(allowance.remainingRiskDollars / cost) : capacity);
  return buy > 0 ? { ...out, action: 'enter', reason: 'paper timing, edge, depth and caller risk allowance satisfied', quantityChange: buy, targetQuantity: buy }
    : { ...out, action: 'wait', reason: 'caller risk allowance/depth permits no entry' };
}
