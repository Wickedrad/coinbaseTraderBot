/** Read-only adapter for the bot's existing fee-aware hourly profit rules. */
import type { FeeSchedule } from '../../bot/fees';
import { HourlyQuotaPacer, quotaCall, validZone, type PacerConfig } from '../../bot/risk/quotaPacer';
import { positionNetAtBid, shareWindowSec } from '../../bot/strategy/fairValueStrategy';
import { digest, stamp } from './contractDataset';
import type { TimedPriceContract } from './contractTiming';

export interface ProfitPolicy {
  pacer: PacerConfig;
  finalProfitFraction: number; shareWindowMaxSec: number; saleBufferMs: number;
  maximumQuoteAgeMs: number; minimumLeadMs: number;
}
/** Already-computed realized P/L delta, including fees; never an account total or a second settlement total. */
export interface RealizedCredit { id: string; at: number; knownAt: number; netUsdDelta: number }
export interface ProfitFeeSnapshot {
  knownAt: number; effectiveFrom: number; validUntil: number | null; sourceSha256: string; verified: boolean;
  schedule: Required<FeeSchedule>;
}
export interface ProfitQuote {
  ticker: string; side: 'yes' | 'no'; at: number; knownAt: number; sourceSha256: string;
  bid: number; bidSize: number; tickSize: number; slippagePerContract: number;
}
export interface ProfitPosition { ticker: string; side: 'yes' | 'no'; quantity: number; averageEntryCost: number }
const count = (n: number) => Number.isFinite(n) && n >= 0 && Math.abs(n * 100 - Math.round(n * 100)) < 1e-7;
const hash = (s: string) => /^[a-f0-9]{64}$/.test(s);

export function validateProfitPolicy(p: ProfitPolicy) {
  const c = p.pacer;
  if (!c || typeof c.enabled !== 'boolean' || typeof c.group !== 'boolean' || !['slices', 'cumulative', 'rolling_hour'].includes(c.mode) ||
      !['off', 'targets', 'riding'].includes(c.floor) || !validZone(c.tz) ||
      !Number.isInteger(c.anchorHour) || c.anchorHour < 0 || c.anchorHour > 23 || !Number.isInteger(c.anchorMinute) || c.anchorMinute < 0 || c.anchorMinute > 59 ||
      ![c.hourlyUsd, c.minTakeUsd, c.maxTargetUsd, c.floorTicks].every((v) => Number.isFinite(v) && v >= 0) || c.maxTargetUsd < c.minTakeUsd ||
      !Number.isFinite(p.finalProfitFraction) || p.finalProfitFraction < 0 || p.finalProfitFraction >= 1 ||
      ![p.shareWindowMaxSec, p.saleBufferMs, p.maximumQuoteAgeMs, p.minimumLeadMs].every(stamp) || p.minimumLeadMs < 1000 || p.minimumLeadMs > 3600000 ||
      p.maximumQuoteAgeMs > 60000 || p.saleBufferMs > 86400000) throw new Error('invalid profit policy');
}
/** Only timing/lead definitions enter the movement target. P/L and fees cannot raise its confidence. */
export const movementTargetPolicy = (p: ProfitPolicy) => ({ saleBufferMs: p.saleBufferMs, minimumLeadMs: p.minimumLeadMs });
export function profitExitBy(c: Pick<TimedPriceContract, 'openTime' | 'closeTime'>, p: ProfitPolicy) {
  validateProfitPolicy(p);
  const span = shareWindowSec(c.openTime, c.closeTime, p.shareWindowMaxSec);
  if (!span || !stamp(c.openTime) || !stamp(c.closeTime)) throw new Error('invalid profit contract window');
  return c.closeTime - p.saleBufferMs;
}
/** Reuse the production clock; credits are actual caller-reported net results, never hypothetical fills. */
export function profitClock(p: ProfitPolicy, credits: RealizedCredit[], now: number) {
  validateProfitPolicy(p);
  if (!stamp(now) || credits.length > 100000) throw new Error('invalid profit clock');
  const ids = new Set<string>(); let last = 0;
  for (const c of credits) {
    if (!c.id || ids.has(c.id) || !stamp(c.at) || !stamp(c.knownAt) || c.at > c.knownAt || c.knownAt > now || c.knownAt < last || !Number.isFinite(c.netUsdDelta)) throw new Error('duplicate, future or unordered realized P/L credit');
    ids.add(c.id); last = c.knownAt;
  }
  const pacer = new HourlyQuotaPacer(p.pacer, credits[0]?.knownAt ?? now);
  for (const c of credits) pacer.record(c.netUsdDelta, c.knownAt);
  return { asOf: now, configurationSha256: digest(p.pacer), status: pacer.status(now), neededUsd: pacer.neededUsd(now) ?? null };
}
function validateFees(f: ProfitFeeSnapshot, at: number) {
  const s = f.schedule;
  return stamp(f.knownAt) && f.knownAt <= at && stamp(f.effectiveFrom) && f.effectiveFrom <= at &&
    (f.validUntil === null || (stamp(f.validUntil) && f.validUntil > at)) && hash(f.sourceSha256) && typeof f.verified === 'boolean' &&
    !!s && [s.takerMultiplier, s.makerMultiplier, s.takerRate, s.makerRate].every((v) => Number.isFinite(v) && v >= 0) &&
    s.takerRate < 1 && s.makerRate < 1 && [0.01, 0.0001].includes(s.balancePrecision);
}
/** Exactly the live position P/L helper, with entry fees already included in the basis. */
export function profitAtSideBid(position: ProfitPosition, bid: number, fees: FeeSchedule, slippage = 0, quantity = position.quantity) {
  const price = Math.max(0, Math.floor((bid - slippage) * 10000 + 1e-8) / 10000);
  return positionNetAtBid(position.side === 'yes' ? quantity : -quantity, position.averageEntryCost,
    position.side === 'yes' ? { price } : undefined, position.side === 'no' ? { price: 1 - price } : undefined, fees)!;
}
/** A cash target changes the required sale price, never the caller's risk-approved size. */
export function profitTargetPrice(position: ProfitPosition, neededUsd: number, tick: number, fees: FeeSchedule, slippage = 0): number | null {
  if (!count(position.quantity) || position.quantity <= 0 || !Number.isFinite(position.averageEntryCost) || position.averageEntryCost < 0 ||
      !Number.isFinite(neededUsd) || neededUsd < 0 || !Number.isFinite(tick) || tick < 0.0001 || tick >= 1 ||
      !Number.isFinite(slippage) || slippage < 0 || slippage >= 1) throw new Error('invalid profit target');
  const steps = Math.floor((1 - tick + 1e-10) / tick);
  for (let k = Math.max(1, Math.ceil(position.averageEntryCost / tick)); k <= steps; k++) {
    const price = Math.round(k * tick * 10000) / 10000;
    if (profitAtSideBid(position, price, fees, slippage) >= neededUsd - 1e-9) return price;
  }
  return null;
}
export interface ProfitExitRequest {
  asOf: number; contract: TimedPriceContract; position: ProfitPosition; quote: ProfitQuote | null;
  fees: ProfitFeeSnapshot; credits: RealizedCredit[]; riskApprovedQuantity: number;
  floor?: { usd: number; knownAt: number }; higherTarget?: string;
  group?: { knownAt: number; sell: boolean; sumUsd: number; members: number };
}
export function evaluateProfitExit(r: ProfitExitRequest, p: ProfitPolicy) {
  validateProfitPolicy(p);
  const pos = r.position, now = r.asOf, q = r.quote;
  if (!stamp(now) || !count(pos.quantity) || pos.quantity <= 0 || !count(r.riskApprovedQuantity) ||
      pos.ticker !== r.contract.ticker || !['yes', 'no'].includes(pos.side) || !Number.isFinite(pos.averageEntryCost) || pos.averageEntryCost < 0 ||
      (r.floor && (!Number.isFinite(r.floor.usd) || r.floor.usd < 0 || !stamp(r.floor.knownAt) || r.floor.knownAt > now)) ||
      (r.group && (!stamp(r.group.knownAt) || r.group.knownAt > now || now - r.group.knownAt > p.maximumQuoteAgeMs ||
        typeof r.group.sell !== 'boolean' || !Number.isFinite(r.group.sumUsd) || r.group.sumUsd < 0 || !Number.isInteger(r.group.members) || r.group.members < 1))) throw new Error('invalid profit exit request');
  const clock = profitClock(p, r.credits, now), normalExitBy = profitExitBy(r.contract, p);
  const out = { researchOnly: true as const, liveEntryAllowed: false as const, action: 'unavailable' as 'unavailable' | 'manage' | 'hold-for-profit' | 'ride-profitable-final-window' | 'reduce' | 'exit',
    reason: 'fresh side bid/depth and an as-of fee schedule required', clock, normalExitBy, quantityToSell: 0,
    positionNetAtTouch: null as number | null, executableNetNow: null as number | null, targetSideBid: null as number | null,
    availableDepthQuantity: 0, netForRecommendedSale: null as number | null,
    armFloorUsd: null as number | null, feeSourceSha256: r.fees.sourceSha256,
    basis: 'Caller position/realized credits; current quoted liquidation and recommendations are not fills' };
  if (now < r.contract.openTime || now >= r.contract.closeTime) return { ...out, reason: 'contract inactive; no pre-settlement sale can be asserted' };
  if (!q || q.ticker !== pos.ticker || q.side !== pos.side || !stamp(q.at) || !stamp(q.knownAt) || q.at > q.knownAt || q.knownAt > now ||
      now - q.at > p.maximumQuoteAgeMs || !hash(q.sourceSha256) || !Number.isFinite(q.bid) || !(q.bid >= 0 && q.bid <= 1) || !count(q.bidSize) || q.bidSize === 0 ||
      !Number.isFinite(q.tickSize) || q.tickSize < 0.0001 || q.tickSize >= 1 || !Number.isFinite(q.slippagePerContract) || q.slippagePerContract < 0 || q.slippagePerContract >= 1 || !validateFees(r.fees, now)) return out;
  const depth = Math.min(pos.quantity, q.bidSize), net = profitAtSideBid(pos, q.bid, r.fees.schedule, q.slippagePerContract);
  out.positionNetAtTouch = net; out.executableNetNow = profitAtSideBid(pos, q.bid, r.fees.schedule, q.slippagePerContract, depth); out.availableDepthQuantity = depth;
  const sell = (reason: string, quantity = depth) => ({ ...out, action: quantity >= pos.quantity - 1e-9 ? 'exit' as const : 'reduce' as const, reason, quantityToSell: quantity,
    netForRecommendedSale: profitAtSideBid(pos, q.bid, r.fees.schedule, q.slippagePerContract, quantity) });
  if (pos.quantity > r.riskApprovedQuantity) return sell('caller risk allowance requires reduction', Math.min(depth, pos.quantity - r.riskApprovedQuantity));
  if (!r.fees.verified) return { ...out, action: 'manage' as const, reason: 'fee terms not verified: continue existing risk/exits; no profit claim or settlement hold' };
  if (clock.neededUsd !== null) out.targetSideBid = profitTargetPrice(pos, clock.neededUsd, q.tickSize, r.fees.schedule, q.slippagePerContract);
  const share = shareWindowSec(r.contract.openTime, r.contract.closeTime, p.shareWindowMaxSec)! * p.finalProfitFraction * 1000;
  const finalWindow = p.finalProfitFraction > 0 && now >= r.contract.closeTime - share;
  if (finalWindow && net > 1e-9 && out.executableNetNow > 1e-9) return { ...out, action: 'ride-profitable-final-window' as const, reason: 'in profit after entry/exit fees inside the configured final share' };
  if (now >= normalExitBy && net <= 1e-9) return sell('normal sale deadline reached without a net profit; seek a sale rather than assume settlement');
  const higher = p.pacer.floor === 'off' ? undefined : r.higherTarget;
  const call = quotaCall(net, clock.neededUsd ?? undefined, p.pacer.enabled ? r.floor?.usd : undefined, higher,
    p.pacer.floorTicks * q.tickSize * pos.quantity, q.tickSize * pos.quantity);
  if (call.sell) return sell(call.sell === 'snipe' ? 'net liquidation profit covers the current hourly slice' : 'net profit fell through the existing quota floor');
  if (p.pacer.enabled && p.pacer.group && r.group?.sell && net > 1e-9 && higher === undefined) return sell('the existing SnipeGroup verdict calls for this profitable position to be sold');
  if (call.arm !== undefined) out.armFloorUsd = call.arm;
  return { ...out, action: net > 0 ? 'hold-for-profit' as const : 'manage' as const,
    reason: call.arm !== undefined ? 'a higher existing target is active; quota becomes its profit floor' :
      net > 0 ? 'below the current cash target; existing profit-taking rules continue' : 'existing loss/stop controls continue; settlement value is not the hold criterion' };
}

