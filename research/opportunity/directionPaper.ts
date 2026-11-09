/** Isolated cash-funded direction paper account. Never constructs a live exchange. */
import { PaperExchange } from '../../bot/paper/paperExchange';
import { OrderBook } from '../../bot/marketdata/orderBook';
import { orderFee, type FeeSchedule } from '../../bot/fees';
import { HourlyQuotaPacer } from '../../bot/risk/quotaPacer';
import type { ExchangeFill } from '../../bot/kalshi/types';
import { profitAtSideBid, validateProfitPolicy, type ProfitPolicy } from './profitExit';
import { stamp } from './contractDataset';
import type { TimedPriceContract } from './contractTiming';

export interface DirectionPaperPolicy {
  startingCash: number; maximumPositionCost: number; maximumContracts: number; maximumOpenPositions: number;
  minimumNetTakeUsd: number; targetContractRoi: number; minimumSignalProbability: number;
  maximumQuoteAgeMs: number; maximumSignalAgeMs: number; saleBufferMs: number;
  targetUnderlyingReturn?: number;
}
export interface PaperFeeTerms {
  schedule: FeeSchedule; knownAt: number; effectiveFrom: number; sourceSha256: string;
  basis: 'observed-as-of' | 'assumed-schedule';
}
export interface DirectionPaperSignal {
  id: string; modelId: string; asOf: number; producedAt: number; featuresKnownAt: number;
  byAt: number; direction: 'up' | 'down'; probability: number;
}
export interface SnapshotEvidence {
  ticker: string; at: number; knownAt: number; sourceSha256: string;
  bids: Array<{ price: number; size: number }>; asks: Array<{ price: number; size: number }>;
  underlying?: { price: number; knownAt: number };
}
interface Position { contract: TimedPriceContract; side: 'yes' | 'no'; quantity: number; basis: number; entryNotional: number; entryUnderlying: number | null; direction: 'up' | 'down' }
const hash = (s: string) => /^[a-f0-9]{64}$/.test(s);
export function validateDirectionPaperPolicy(p: DirectionPaperPolicy) {
  if (![p.startingCash, p.maximumPositionCost, p.minimumNetTakeUsd].every((n) => Number.isFinite(n) && n > 0) || p.maximumPositionCost > p.startingCash ||
      !Number.isSafeInteger(p.maximumContracts) || p.maximumContracts < 1 || !Number.isSafeInteger(p.maximumOpenPositions) || p.maximumOpenPositions < 1 ||
      !Number.isFinite(p.targetContractRoi) || p.targetContractRoi < 0 || p.targetContractRoi > 1 || !Number.isFinite(p.minimumSignalProbability) ||
      p.minimumSignalProbability < 0 || p.minimumSignalProbability > 1 || ![p.maximumQuoteAgeMs, p.maximumSignalAgeMs, p.saleBufferMs].every(stamp) ||
      (p.targetUnderlyingReturn !== undefined && (!Number.isFinite(p.targetUnderlyingReturn) || p.targetUnderlyingReturn < 0 || p.targetUnderlyingReturn > 1))) throw new Error('invalid direction paper policy');
}
export class DirectionPaperAccount {
  private now = 0; private count = 0; private expectedCash: number;
  private readonly books = new Map<string, OrderBook>();
  private readonly fees = new Map<string, PaperFeeTerms>();
  private readonly positions = new Map<string, Position>();
  private readonly context = new Map<string, { kind: 'entry' | 'exit'; contract: TimedPriceContract; side: 'yes' | 'no'; underlying: number | null; reason: string; direction?: 'up' | 'down' }>();
  private readonly seenQuotes = new Set<string>();
  private readonly exchange: PaperExchange;
  private readonly pacer: HourlyQuotaPacer;
  readonly fills: Array<Record<string, unknown>> = []; readonly sales: Array<Record<string, unknown>> = [];
  readonly hourly = new Map<number, { netUsd: number; sales: number }>();
  readonly decisions: Record<string, number> = {};
  private feeAssumptionsUsed = false;
  constructor(readonly policy: DirectionPaperPolicy, profitPolicy: ProfitPolicy, at: number) {
    validateDirectionPaperPolicy(policy); validateProfitPolicy(profitPolicy); if (!stamp(at)) throw new Error('invalid paper clock'); this.now = at;
    this.expectedCash = policy.startingCash;
    this.pacer = new HourlyQuotaPacer(profitPolicy.pacer, at);
    // In-memory state; never refill. Consumed depth is not restored by a timer.
    this.exchange = new PaperExchange(undefined, policy.startingCash, (t) => this.books.get(t), (t) => this.fees.get(t)!.schedule,
      () => this.now, Number.MAX_SAFE_INTEGER);
    this.exchange.on('fill', (f: ExchangeFill) => this.filled(f));
  }
  private outcome(reason: string) { this.decisions[reason] = (this.decisions[reason] ?? 0) + 1; return reason; }
  private filled(f: ExchangeFill) {
    const c = this.context.get(f.clientOrderId ?? ''); if (!c || f.fee === undefined) throw new Error('paper fill lacks accounting context');
    const sidePrice = c.side === 'yes' ? f.price : 1 - f.price;
    if (c.kind === 'entry') {
      const p = this.positions.get(f.ticker) ?? { contract: c.contract, side: c.side, quantity: 0, basis: 0, entryNotional: 0, entryUnderlying: c.underlying, direction: c.direction! };
      if (p.side !== c.side) throw new Error('paper account cannot silently flip exposure');
      p.quantity += f.count; p.basis += f.count * sidePrice + f.fee; p.entryNotional += f.count * sidePrice;
      this.expectedCash -= f.count * sidePrice + f.fee; this.positions.set(f.ticker, p);
    } else {
      const p = this.positions.get(f.ticker); if (!p || f.count > p.quantity + 1e-9) throw new Error('paper close exceeds held position');
      const fraction = f.count / p.quantity, basis = p.basis * fraction, entryNotional = p.entryNotional * fraction;
      const proceeds = f.count * sidePrice - f.fee, net = proceeds - basis;
      this.expectedCash += proceeds; this.pacer.record(net, f.ts);
      const h = Math.floor(f.ts / 3600000), old = this.hourly.get(h) ?? { netUsd: 0, sales: 0 }; old.netUsd += net; old.sales++; this.hourly.set(h, old);
      this.sales.push({ at: f.ts, ticker: f.ticker, side: p.side, quantity: f.count, sidePrice, fee: f.fee, entryBasisUsd: basis, netUsd: net,
        grossContractRoi: f.count * sidePrice / entryNotional - 1, netContractRoi: net / basis,
        underlyingMoveBps: p.entryUnderlying && c.underlying ? (c.underlying / p.entryUnderlying - 1) * 10000 : null,
        direction: p.direction, reason: c.reason });
      p.quantity -= f.count; p.basis -= basis; p.entryNotional -= entryNotional;
      if (p.quantity < 1e-9) this.positions.delete(f.ticker);
    }
    if (this.exchange.cash() < -1e-7 || Math.abs(this.exchange.cash() - this.expectedCash) > 1e-6) throw new Error('paper cash/fee/basis reconciliation failed');
    this.fills.push({ at: f.ts, ticker: f.ticker, side: c.side, action: c.kind, quantity: f.count, sidePrice, fee: f.fee, cashAfter: this.exchange.cash() });
  }
  async observe(contract: TimedPriceContract, q: SnapshotEvidence, fees: PaperFeeTerms, signal: DirectionPaperSignal | null) {
    if (!stamp(q.knownAt) || q.knownAt < this.now) throw new Error('paper arrivals are not ordered'); this.now = q.knownAt;
    if (![contract.openTime, contract.closeTime, contract.termsKnownAt].every(stamp) || contract.termsKnownAt > this.now || contract.closeTime <= contract.openTime) return this.outcome('unavailable-contract-terms');
    if (q.ticker !== contract.ticker || !stamp(q.at) || q.at > this.now || this.now - q.at > this.policy.maximumQuoteAgeMs || !hash(q.sourceSha256) ||
        [...q.bids, ...q.asks].some((l) => !Number.isFinite(l.price) || l.price <= 0 || l.price >= 1 || !Number.isFinite(l.size) || l.size < 0 || Math.abs(l.size * 100 - Math.round(l.size * 100)) > 1e-6)) return this.outcome('unavailable-book');
    const quoteKey = `${q.ticker}:${q.at}:${q.sourceSha256}`;
    if (this.seenQuotes.has(quoteKey)) return this.outcome('duplicate-book'); this.seenQuotes.add(quoteKey);
    const f = fees.schedule;
    if (!hash(fees.sourceSha256) || !stamp(fees.effectiveFrom) || fees.effectiveFrom > this.now || !stamp(fees.knownAt) ||
        !['observed-as-of', 'assumed-schedule'].includes(fees.basis) || (fees.basis === 'observed-as-of' && fees.knownAt > this.now) ||
        ![f.takerMultiplier, f.makerMultiplier, f.takerRate ?? 0.07, f.makerRate ?? 0.0175].every((v) => Number.isFinite(v) && v >= 0) ||
        ![0.01, 0.0001].includes(f.balancePrecision ?? 0.01)) return this.outcome('unavailable-fees');
    this.feeAssumptionsUsed ||= fees.basis === 'assumed-schedule'; this.fees.set(q.ticker, fees);
    const book = this.books.get(q.ticker) ?? new OrderBook(q.ticker); book.applySnapshot(q, q.at); this.books.set(q.ticker, book);
    if (!book.isUsable(this.now, this.policy.maximumQuoteAgeMs)) return this.outcome('unavailable-book');
    const index = q.underlying && stamp(q.underlying.knownAt) && q.underlying.knownAt <= this.now && this.now - q.underlying.knownAt <= 3000 && Number.isFinite(q.underlying.price) && q.underlying.price > 0 ? q.underlying.price : null;
    const held = this.positions.get(q.ticker);
    if (held) {
      const old = held.contract;
      if (old.asset !== contract.asset || old.openTime !== contract.openTime || old.closeTime !== contract.closeTime || old.settlementReference !== contract.settlementReference ||
          old.terms.kind !== contract.terms.kind || old.terms.strike !== contract.terms.strike || old.terms.cap !== contract.terms.cap) return this.outcome('changed-held-contract-terms');
      if (this.now >= contract.closeTime) return this.outcome('expired-unresolved-exposure');
      const level = held.side === 'yes' ? book.bestBid() : book.bestAsk(); if (!level) return this.outcome('no-exit-depth');
      const bid = held.side === 'yes' ? level.price : 1 - level.price, depth = Math.min(held.quantity, level.size);
      const basis = held.basis / held.quantity, net = profitAtSideBid({ ticker: q.ticker, side: held.side, quantity: held.quantity, averageEntryCost: basis }, bid, f, 0, depth);
      const roi = bid / (held.entryNotional / held.quantity) - 1;
      const underlyingReached = this.policy.targetUnderlyingReturn === undefined || (held.entryUnderlying !== null && index !== null &&
        (index / held.entryUnderlying - 1) * (held.direction === 'up' ? 1 : -1) >= this.policy.targetUnderlyingReturn - 1e-9);
      const deadline = this.now >= contract.closeTime - this.policy.saleBufferMs;
      if (!deadline && !(net >= this.policy.minimumNetTakeUsd - 1e-9 && roi >= this.policy.targetContractRoi - 1e-9 && underlyingReached)) return this.outcome('manage');
      const client = `direction-exit-${++this.count}`;
      this.context.set(client, { kind: 'exit', contract, side: held.side, underlying: index, reason: deadline ? 'sale-deadline' : 'small-fee-net-take' });
      await this.exchange.createOrder({ ticker: q.ticker, side: held.side === 'yes' ? 'ask' : 'bid', price: level.price, count: depth,
        timeInForce: 'immediate_or_cancel', postOnly: false, reduceOnly: true, selfTradePrevention: 'taker_at_cross', clientOrderId: client });
      this.context.delete(client); return this.outcome('exit-attempt');
    }
    if (this.now < contract.openTime || this.now >= contract.closeTime - this.policy.saleBufferMs) return this.outcome('inactive-entry');
    if (!signal || !signal.id || !hash(signal.modelId) || !['up', 'down'].includes(signal.direction) || signal.probability < this.policy.minimumSignalProbability || !Number.isFinite(signal.probability) || signal.probability > 1 ||
        !stamp(signal.asOf) || !stamp(signal.producedAt) || !stamp(signal.featuresKnownAt) || !stamp(signal.byAt) || signal.featuresKnownAt > signal.asOf || signal.asOf > signal.producedAt || signal.producedAt > this.now ||
        this.now - signal.asOf > this.policy.maximumSignalAgeMs || signal.byAt > contract.closeTime - this.policy.saleBufferMs || signal.byAt <= this.now) return this.outcome('unavailable-direction-signal');
    const kind = contract.terms.kind; if (!['updown', 'greater', 'less'].includes(kind)) return this.outcome('nonmonotone-contract');
    const side = (signal.direction === 'up') !== (kind === 'less') ? 'yes' : 'no';
    if (this.positions.size >= this.policy.maximumOpenPositions) return this.outcome('position-limit');
    const level = side === 'yes' ? book.bestAsk() : book.bestBid(); if (!level) return this.outcome('no-entry-depth');
    const price = side === 'yes' ? level.price : 1 - level.price, budget = Math.min(this.policy.maximumPositionCost, this.exchange.cash());
    let quantity = Math.min(this.policy.maximumContracts, Math.floor(level.size), Math.floor(budget / price));
    while (quantity > 0 && quantity * price + orderFee(quantity, price, true, f) > budget + 1e-9) quantity--;
    if (!quantity) return this.outcome('insufficient-funded-risk-budget');
    const client = `direction-entry-${++this.count}`; this.context.set(client, { kind: 'entry', contract, side, underlying: index, reason: 'direction-only-paper-entry', direction: signal.direction });
    await this.exchange.createOrder({ ticker: q.ticker, side: side === 'yes' ? 'bid' : 'ask', price: level.price, count: quantity,
      timeInForce: 'immediate_or_cancel', postOnly: false, reduceOnly: false, selfTradePrevention: 'taker_at_cross', clientOrderId: client });
    this.context.delete(client); return this.outcome('entry-attempt');
  }
  report() {
    const net = this.sales.reduce((n, s) => n + Number(s.netUsd), 0);
    return { startingCash: this.policy.startingCash, endingCash: this.exchange.cash(), simulatedNetRealizedUsd: net, paidFees: this.fills.reduce((n, f) => n + Number(f.fee), 0),
      remainingCostBasisUsd: [...this.positions.values()].reduce((n, p) => n + p.basis, 0), unresolvedPositions: [...this.positions].map(([ticker, p]) => ({ ticker, quantity: p.quantity, side: p.side, basis: p.basis })),
      hourly: [...this.hourly].map(([hour, p]) => ({ from: hour * 3600000, ...p, goalMet: p.netUsd >= 4.5 - 1e-9 })), pacer: this.pacer.status(this.now),
      fills: this.fills.length, sales: this.sales.length, decisions: this.decisions, noRefills: true, liquidityReplenishedByTimer: false,
      feeAsOfVerified: !this.feeAssumptionsUsed, liveEntryAllowed: false, researchOnly: true, actualVenueProfitVerified: false,
      interpretation: 'Conservative snapshot-taker paper account, not real venue fills; unresolved exposure is not settled or counted as profit' };
  }
}
