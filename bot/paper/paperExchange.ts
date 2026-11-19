// Paper exchange implementing the same ExchangeGateway as live Kalshi, so
// paper/shadow trading runs the identical OMS, risk and reconciliation code.
//
// Fill realism (conservative by design):
//  - IOC/FOK orders walk the visible book and pay taker fees.
//  - Resting orders join the BACK of their price level (queue ahead = visible
//    size at that price when placed).
//  - Resting orders fill only when public trades print: a trade at a price
//    through ours fills us up to the trade's size (a 1-contract print cannot
//    fill a 20-contract order: until Oct 23 it filled the whole order, which
//    overstated paper volume once orders grew to $10); a trade at our price
//    first consumes the queue ahead. Book changes alone never fill us.
//  - Only trades the exchange printed after the order was placed can fill it
//    (by the trade's own time stamp). Market data can reach the bot late: on
//    Oct 5-6 Kalshi trades arrived minutes behind, and quotes priced on live
//    Coinbase prices were filled by those old trades - profits a real exchange
//    could never have given.
//  - Post-only orders that would cross are rejected, like the exchange, and so is reduce-only on an order that is
//    not immediate-or-cancel (Kalshi accepts it on IOC orders only).
//  - No bankroll refills. Drawdowns stay visible.

import crypto from 'crypto';
import { EventEmitter } from 'events';
import { orderFee, type FeeSchedule } from '../fees';
import type { OrderBook } from '../marketdata/orderBook';
import {
  CreateOrderRequest, ExchangeFill, ExchangeGateway, ExchangeOrder, ExchangePosition, OrderRejectedError,
} from '../kalshi/types';
import { readJson, writeJsonAtomic } from '../util/persist';
import type { SettlementRecord } from '../recon/kalshiCheck';

interface PaperOrder extends ExchangeOrder {
  queueAhead: number;
  postOnly: boolean;
  reduceOnly: boolean;
  expirationTime?: number;
  count: number;
  /** When the order was placed (the paper clock); orders saved before this field fill as before. */
  placedTs?: number;
}

/** Kalshi stamps trades in whole seconds: a trade stamped up to this long before an order may still follow it. */
const TRADE_TS_SLACK_MS = 1000;

/** The paper account's result against all the money put into it (PaperExchange.poolResult), in dollars. */
export interface PaperPoolResult {
  /** Starting balance plus top-ups. */
  funded: number;
  /** Cash added by training refills. */
  refilled: number;
  /** funded + refilled. */
  putIn: number;
  /** Cash, resting-order holds included. */
  cash: number;
  /** Cost of the contracts held. */
  openCost: number;
  /** cash + openCost. */
  worth: number;
  /** worth - putIn: negative when the account holds less than was put into it. */
  result: number;
}

interface PaperState {
  balance: number;
  /** Cash put into the paper account so far (raising PAPER_BANKROLL_USD tops it up by the difference). */
  funded?: number;
  /** Cash added by training refills (capital exhaustion), total. */
  refilled?: number;
  positions: Record<string, number>;
  fills: ExchangeFill[];
  orders: PaperOrder[];
  /** Per market: cost basis of the YES / NO contracts held and fees paid (as Kalshi reports them). */
  basis?: Record<string, { yesCost: number; noCost: number; fees: number }>;
  /** Settlement records in Kalshi's shape (last 2 days), for the Kalshi check. */
  settlements?: SettlementRecord[];
}

/** Finished orders kept (state file and lookups): those updated within the hour, newest 500. */
const KEEP_ORDERS_MS = 3_600_000, KEEP_ORDERS = 500;
/** Fills kept: the last day, newest 2,000 (reconciliation replays from 10 minutes before the newest fill). */
const KEEP_FILLS_MS = 86_400_000, KEEP_FILLS = 2000;
/** How long the size our own taker orders took from a level stays missing from the (recorded / public) book we see:
 *  the public book never shows our paper takes, so without this a thin level could be bought again and again
 *  (Nov 1: the replay's KXDOGE hourly range profits). New size added at the level after our take counts at once. */
export const TAKEN_REPLENISH_MS = Number(process.env.PAPER_TAKEN_REPLENISH_MS ?? 60_000);

export class PaperExchange extends EventEmitter implements ExchangeGateway {
  readonly name = 'paper';
  private st: PaperState;
  private saveTimer: NodeJS.Timeout | null = null;
  /** Lookups by exchange id and client id, and the resting orders alone: every public trade print is
   *  matched against resting orders, which used to mean a scan of every order kept (up to 4,000). */
  private readonly byId = new Map<string, PaperOrder>();
  private readonly byClientId = new Map<string, PaperOrder>();
  private readonly resting = new Map<string, PaperOrder>();
  /** Size our taker fills removed from a book level (ticker|side|price): see TAKEN_REPLENISH_MS. */
  private readonly taken = new Map<string, { size: number; taken: number; ts: number }>();
  /** Taker contracts asked for, filled, and refused because the level was already taken by us. */
  readonly takerStats: { asked: number; filled: number; blocked: number; bySeries: Record<string, { asked: number; filled: number; blocked: number }>; staleRetake: number; staleBySeries: Record<string, number> } = { asked: 0, filled: 0, blocked: 0, bySeries: {}, staleRetake: 0, staleBySeries: {} };
  /** The level's displayed size when we last took from it (kept after the replenish window): a take from a level the
   *  book still shows at that same size takes liquidity our earlier take already removed in the real market. */
  private readonly lastTake = new Map<string, { size: number; ts: number }>();

  constructor(
    /** State file; undefined = in-memory only (backtests). */
    private readonly file: string | undefined,
    startingBalance: number,
    private readonly books: (ticker: string) => OrderBook | undefined,
    private readonly feesFor: (ticker: string) => FeeSchedule,
    private readonly now: () => number = Date.now,
    /** Explicit research override; existing callers retain the current replenish policy. */
    private readonly takenReplenishMs: number = TAKEN_REPLENISH_MS,
  ) {
    super();
    if (!Number.isSafeInteger(takenReplenishMs) || takenReplenishMs < 0) throw new Error('invalid paper liquidity replenish interval');
    this.st = (file && readJson<PaperState>(file, { quarantine: true })) || { balance: startingBalance, funded: startingBalance, positions: {}, fills: [], orders: [] };
    // Accounts created before `funded` was recorded started with the old $20 default.
    const funded = this.st.funded ?? 20;
    if (startingBalance > funded) {
      this.st.balance += startingBalance - funded;
      this.st.funded = startingBalance;
      this.save();
    } else this.st.funded = funded;
    for (const o of this.st.orders) this.index(o);
  }

  private index(o: PaperOrder): void {
    this.byId.set(o.orderId, o);
    if (o.clientOrderId) this.byClientId.set(o.clientOrderId, o);
    if (o.status === 'resting') this.resting.set(o.orderId, o); else this.resting.delete(o.orderId);
  }

  /** Cash put into the paper account (the configured starting balance, after any top-ups). */
  get funded(): number { return this.st.funded ?? 0; }

  /** What the account has made, which its cash does not show: a training refill adds cash, so the balance can climb while
   *  the bot loses. Worth = cash (what resting orders hold included) + the cost of what it holds; result = worth less all
   *  the money put in (the starting balance and its top-ups, and every refill). Counted from the account's current book,
   *  whose `funded` and `refilled` counters start when its state file was created (a file older than the counters is
   *  assumed to have started with $20), and the held contracts are valued at cost, not at the market. */
  poolResult(): PaperPoolResult {
    const cents = (x: number): number => Math.round(x * 100) / 100 + 0; // + 0: no -0
    let openCost = 0;
    for (const [ticker, b] of Object.entries(this.st.basis ?? {})) {
      if (Math.abs(this.st.positions[ticker] ?? 0) > 1e-9) openCost += b.yesCost + b.noCost;
    }
    const funded = this.st.funded ?? 0, refilled = this.st.refilled ?? 0;
    const cash = this.st.balance, worth = cash + openCost, putIn = funded + refilled;
    return { funded: cents(funded), refilled: cents(refilled), putIn: cents(putIn), cash: cents(cash), openCost: cents(openCost), worth: cents(worth), result: cents(worth - putIn) };
  }

  /** Training refill after capital exhaustion (bot/training/supervisor.ts): add cash, tracked separately. */
  refill(amount: number): void {
    if (!(amount > 0)) return;
    this.st.balance += amount;
    this.st.refilled = (this.st.refilled ?? 0) + amount;
    this.save();
  }

  private save(): void {
    if (!this.file || this.saveTimer) return;
    // Debounced, compact, not fsynced: the simulated exchange is not the system of record.
    this.saveTimer = setTimeout(() => {
      this.saveTimer = null;
      this.prune();
      writeJsonAtomic(this.file!, this.st, { compact: true });
    }, 1000);
    this.saveTimer.unref();
  }

  /** Drop finished orders and old fills nothing can ask for again (the state file is rewritten whole). */
  private prune(): void {
    const now = this.now();
    if (this.st.orders.length > this.resting.size + 50) {
      const keep = this.st.orders.filter((o) => o.status === 'resting' || now - (o.updatedTs ?? 0) < KEEP_ORDERS_MS);
      const finished = keep.filter((o) => o.status !== 'resting');
      const drop = new Set(finished.slice(0, Math.max(0, finished.length - KEEP_ORDERS)));
      const next = keep.filter((o) => !drop.has(o));
      if (next.length !== this.st.orders.length) {
        const kept = new Set(next);
        for (const o of this.st.orders) if (!kept.has(o)) { this.byId.delete(o.orderId); if (o.clientOrderId) this.byClientId.delete(o.clientOrderId); this.resting.delete(o.orderId); }
        this.st.orders = next;
      }
    }
    const f = this.st.fills;
    if (f.length && (f.length > KEEP_FILLS || f[0].ts < now - KEEP_FILLS_MS)) {
      let i = Math.max(0, f.length - KEEP_FILLS);
      while (i < f.length && f[i].ts < now - KEEP_FILLS_MS) i++;
      this.st.fills = f.slice(i);
    }
  }

  /** Write pending state now (shutdown). */
  flush(): void {
    if (this.saveTimer) { clearTimeout(this.saveTimer); this.saveTimer = null; }
    if (this.file) { this.prune(); writeJsonAtomic(this.file, this.st, { compact: true }); }
  }

  async createOrder(req: CreateOrderRequest): Promise<ExchangeOrder> {
    if (this.byClientId.has(req.clientOrderId)) {
      throw new OrderRejectedError('duplicate client_order_id', 409, 'duplicate');
    }
    // Like Kalshi (and the live REST client): reduce-only is accepted on immediate-or-cancel orders only.
    if (req.reduceOnly && req.timeInForce !== 'immediate_or_cancel') throw new OrderRejectedError('reduce_only is only accepted with immediate_or_cancel', 400, 'invalid_order');
    const book = this.books(req.ticker);
    if (!book) throw new OrderRejectedError('unknown market', 404, 'market_not_found');
    const o: PaperOrder = {
      orderId: crypto.randomUUID(),
      clientOrderId: req.clientOrderId,
      ticker: req.ticker,
      side: req.side,
      price: req.price,
      status: 'resting',
      fillCount: 0,
      remainingCount: req.count,
      initialCount: req.count,
      count: req.count,
      feesPaid: 0,
      queueAhead: 0,
      postOnly: req.postOnly,
      reduceOnly: req.reduceOnly,
      expirationTime: req.expirationTime,
      updatedTs: this.now(),
      placedTs: this.now(),
    };
    const bestBid = book.bestBid();
    const bestAsk = book.bestAsk();
    const crosses = req.side === 'bid' ? bestAsk !== undefined && req.price >= bestAsk.price : bestBid !== undefined && req.price <= bestBid.price;
    if (req.postOnly && crosses) throw new OrderRejectedError('post only order would cross', 400, 'post_only_cross');
    if (req.reduceOnly) {
      const pos = this.st.positions[req.ticker] ?? 0;
      const reduces = req.side === 'ask' ? pos > 0 : pos < 0;
      if (!reduces) throw new OrderRejectedError('reduce only would increase position', 400, 'reduce_only');
      o.remainingCount = Math.min(o.remainingCount, Math.abs(pos));
    }
    // Like Kalshi: an order's opening part is checked against the cash not already held by resting orders (closing
    // what is held needs no cash).
    const cost = (req.side === 'bid' ? req.price : 1 - req.price) * this.opening(req.ticker, req.side, req.count);
    if (!req.reduceOnly && cost > this.available() + 1e-9) throw new OrderRejectedError('insufficient_balance', 400, 'insufficient_balance');

    this.st.orders.push(o);
    this.index(o);
    if (crosses) {
      // Taker: walk the opposite side of the visible book.
      const levels = req.side === 'bid' ? book.snapshot(50).asks : book.snapshot(50).bids;
      const bookSide = req.side === 'bid' ? 'ask' : 'bid';
      const ser = (this.takerStats.bySeries[req.ticker.split('-')[0]] ??= { asked: 0, filled: 0, blocked: 0 });
      this.takerStats.asked += o.remainingCount; ser.asked += o.remainingCount;
      for (const lvl of levels) {
        if (o.remainingCount <= 1e-9) break;
        const through = req.side === 'bid' ? lvl.price <= req.price : lvl.price >= req.price;
        if (!through) break;
        const key = `${req.ticker}|${bookSide}|${lvl.price}`;
        let e = this.taken.get(key);
        if (e && (this.takenReplenishMs <= 0 || this.now() - e.ts >= this.takenReplenishMs)) { this.taken.delete(key); e = undefined; }
        // What we took is still missing from the level (size added since then is real); conservative while the
        // recorded level shrinks, since the public book never knew our take.
        const avail = e ? Math.max(0, lvl.size - e.taken) : lvl.size;
        const blocked = Math.min(lvl.size, o.remainingCount) - Math.min(avail, o.remainingCount);
        this.takerStats.blocked += blocked; ser.blocked += blocked;
        const n = Math.min(avail, o.remainingCount);
        if (n <= 1e-9) continue;
        // Audit (Nov 5, the replay's snipe volume): the level shows the very size it showed at our last take, so the
        // book has not changed there since; the real level would still be short what we took.
        const lt = this.lastTake.get(key);
        if (!e && lt && Math.abs(lt.size - lvl.size) < 1e-9 && this.now() - lt.ts < 600_000) { this.takerStats.staleRetake += n; this.takerStats.staleBySeries[req.ticker.split('-')[0]] = (this.takerStats.staleBySeries[req.ticker.split('-')[0]] ?? 0) + n; }
        this.lastTake.set(key, { size: lvl.size, ts: this.now() });
        if (this.lastTake.size > 20000) for (const [k, v] of this.lastTake) if (this.now() - v.ts >= 600_000) this.lastTake.delete(k);
        this.fill(o, n, lvl.price, true);
        this.takerStats.filled += n; ser.filled += n;
        if (this.takenReplenishMs > 0) this.taken.set(key, { size: lvl.size, taken: (e?.taken ?? 0) + n, ts: this.now() });
      }
      if (this.taken.size > 5000) for (const [k, v] of this.taken) if (this.now() - v.ts >= this.takenReplenishMs) this.taken.delete(k);
    }
    if (o.remainingCount > 1e-9) {
      if (req.timeInForce === 'good_till_canceled') {
        o.queueAhead = book.sizeAt(req.side, req.price);
      } else {
        o.status = o.fillCount > 0 ? 'executed' : 'canceled';
        this.resting.delete(o.orderId);
        if (req.timeInForce === 'fill_or_kill' && o.fillCount > 0) throw new Error('FOK partial fill in paper sim');
        o.remainingCount = 0;
      }
    }
    o.updatedTs = this.now();
    this.save();
    return { ...o };
  }

  async cancelOrder(orderId: string): Promise<void> {
    const o = this.byId.get(orderId);
    if (!o || o.status !== 'resting') return;
    o.status = 'canceled';
    this.resting.delete(orderId);
    o.remainingCount = 0;
    o.updatedTs = this.now();
    this.save();
    this.emit('order', { ...o });
  }

  async getOrder(orderId: string): Promise<ExchangeOrder | undefined> {
    const o = this.byId.get(orderId);
    return o ? { ...o } : undefined;
  }

  async findOrderByClientId(clientOrderId: string): Promise<ExchangeOrder | undefined> {
    const o = this.byClientId.get(clientOrderId);
    return o ? { ...o } : undefined;
  }

  async getOpenOrders(): Promise<ExchangeOrder[]> {
    this.expire();
    return [...this.resting.values()].map((o) => ({ ...o }));
  }

  async getFills(sinceTs: number): Promise<ExchangeFill[]> {
    return this.st.fills.filter((f) => f.ts >= sinceTs);
  }

  async getPositions(): Promise<ExchangePosition[]> {
    return Object.entries(this.st.positions).filter(([, v]) => Math.abs(v) > 1e-9).map(([ticker, position]) => ({ ticker, position }));
  }

  /** Cash Kalshi would report: the account's cash less what resting orders hold (a resting buy's cost is held until it
   *  fills or is canceled, as GET /portfolio/balance shows it; Engine.freeCash relies on that). */
  async getBalance(): Promise<number> {
    return this.available();
  }

  /** The account's cash including what resting orders hold (for equity: a hold is still the account's money). */
  cash(): number {
    return this.st.balance;
  }

  /** Read-only preview for research takers: own earlier takes remain absent until
   * displayed depth increases or the configured replenishment interval expires. */
  availableTakerQuantity(ticker: string, bookSide: 'bid' | 'ask', price: number, displayed: number): number {
    const taken = this.taken.get(`${ticker}|${bookSide}|${price}`);
    return !taken || this.takenReplenishMs <= 0 || this.now() - taken.ts >= this.takenReplenishMs
      ? displayed : Math.max(0, displayed - taken.taken);
  }

  /** What resting orders hold: the cost of each one's opening part. Orders that only close a held position hold nothing. */
  held(): number {
    const cover = new Map<string, number>();
    let h = 0;
    for (const o of this.resting.values()) {
      if (o.reduceOnly || o.remainingCount <= 1e-9) continue;
      const k = `${o.ticker}|${o.side}`;
      const pos = this.st.positions[o.ticker] ?? 0;
      const left = cover.get(k) ?? Math.max(0, o.side === 'ask' ? pos : -pos);
      const closing = Math.min(left, o.remainingCount);
      cover.set(k, left - closing);
      h += (o.side === 'bid' ? o.price : 1 - o.price) * (o.remainingCount - closing);
    }
    return h;
  }

  private available(): number {
    return this.st.balance - this.held();
  }

  /** The part of a new order that opens exposure, after what resting orders on the same side already close. */
  private opening(ticker: string, side: 'bid' | 'ask', count: number): number {
    const pos = this.st.positions[ticker] ?? 0;
    let cover = Math.max(0, side === 'ask' ? pos : -pos);
    for (const o of this.resting.values()) if (o.ticker === ticker && o.side === side && !o.reduceOnly) cover -= o.remainingCount;
    return Math.max(0, count - Math.max(0, cover));
  }

  /** Public trade print from market data; `tradeTs` is the exchange's time stamp of the trade. */
  onTrade(ticker: string, price: number, count: number, takerSide: 'yes' | 'no' | undefined, tradeTs?: number): void {
    let changed = this.expire();
    let remaining = count;
    // A YES-taker lifts asks; a NO-taker hits YES bids. Unknown side: match by price only.
    // A trade printed before an order existed neither fills it nor eats its queue.
    const after = (o: PaperOrder) => tradeTs === undefined || !Number.isFinite(tradeTs) || o.placedTs === undefined || o.placedTs <= tradeTs + TRADE_TS_SLACK_MS;
    const candidates = [...this.resting.values()]
      .filter((o) => o.ticker === ticker && after(o))
      .filter((o) => (o.side === 'bid' ? takerSide !== 'yes' && price <= o.price + 1e-9 : takerSide !== 'no' && price >= o.price - 1e-9))
      .sort((a, b) => (a.side === 'bid' ? b.price - a.price : a.price - b.price));
    for (const o of candidates) {
      if (remaining <= 1e-9) break;
      const through = o.side === 'bid' ? price < o.price - 1e-9 : price > o.price + 1e-9;
      changed = true;
      if (through) {
        const n = Math.min(o.remainingCount, remaining);
        remaining -= n;
        this.fill(o, n, o.price, false);
        continue;
      }
      const eatQueue = Math.min(o.queueAhead, remaining);
      o.queueAhead -= eatQueue;
      remaining -= eatQueue;
      if (o.queueAhead <= 1e-9 && remaining > 1e-9) {
        const n = Math.min(o.remainingCount, remaining);
        remaining -= n;
        this.fill(o, n, o.price, false);
      }
    }
    if (changed) this.save();
  }

  async getSettlements(sinceTs: number): Promise<SettlementRecord[]> {
    return (this.st.settlements ?? []).filter((r) => r.ts >= sinceTs);
  }

  /** Settle a market in the paper account. */
  settle(ticker: string, result: 'yes' | 'no'): void {
    const pos = this.st.positions[ticker] ?? 0;
    const b = this.st.basis?.[ticker];
    if (Math.abs(pos) > 1e-9 || b) {
      const now = this.now();
      const rec: SettlementRecord = { ticker, result, yesCount: Math.max(0, pos), noCount: Math.max(0, -pos), yesCost: r6(b?.yesCost ?? 0), noCost: r6(b?.noCost ?? 0),
        revenue: pos > 0 && result === 'yes' ? pos : pos < 0 && result === 'no' ? -pos : 0, fees: r6(b?.fees ?? 0), ts: now };
      this.st.settlements = [...(this.st.settlements ?? []).filter((r) => r.ts >= now - 2 * 86_400_000), rec];
      if (this.st.basis) delete this.st.basis[ticker];
    }
    if (pos > 0 && result === 'yes') this.st.balance += pos;
    if (pos < 0 && result === 'no') this.st.balance += -pos;
    delete this.st.positions[ticker];
    for (const o of [...this.resting.values()]) {
      if (o.ticker === ticker) { o.status = 'canceled'; o.remainingCount = 0; this.resting.delete(o.orderId); this.emit('order', { ...o }); }
    }
    this.save();
  }

  private expire(): boolean {
    const nowSec = this.now() / 1000;
    let any = false;
    for (const o of [...this.resting.values()]) {
      if (o.expirationTime !== undefined && nowSec >= o.expirationTime) {
        o.status = 'canceled';
        this.resting.delete(o.orderId);
        o.lastUpdateReason = 'expired';
        o.remainingCount = 0;
        o.updatedTs = this.now();
        any = true;
        this.emit('order', { ...o });
      }
    }
    return any;
  }

  private fill(o: PaperOrder, count: number, price: number, isTaker: boolean): void {
    const n = Math.round(count * 100) / 100;
    if (n <= 0) return;
    const pos = this.st.positions[o.ticker] ?? 0;
    const fee = orderFee(n, o.side === 'bid' ? price : 1 - price, isTaker, this.feesFor(o.ticker));
    // Cost basis as Kalshi keeps it: opening adds the side's price; closing releases its share.
    const b = ((this.st.basis ??= {})[o.ticker] ??= { yesCost: 0, noCost: 0, fees: 0 });
    b.fees += fee;
    if (o.side === 'bid') {
      const closing = Math.min(n, Math.max(0, -pos));
      if (closing > 0) b.noCost *= (-pos - closing) / -pos;
      b.yesCost += (n - closing) * price;
    } else {
      const closing = Math.min(n, Math.max(0, pos));
      if (closing > 0) b.yesCost *= (pos - closing) / pos;
      b.noCost += (n - closing) * (1 - price);
    }
    // Kalshi collateral accounting: opening costs the side's price; closing releases it.
    if (o.side === 'bid') {
      const closing = Math.min(n, Math.max(0, -pos));
      this.st.balance += closing * (1 - price) - (n - closing) * price;
      this.st.positions[o.ticker] = Math.round((pos + n) * 100) / 100;
    } else {
      const closing = Math.min(n, Math.max(0, pos));
      this.st.balance += closing * price - (n - closing) * (1 - price);
      this.st.positions[o.ticker] = Math.round((pos - n) * 100) / 100;
    }
    this.st.balance -= fee;
    o.fillCount = Math.round((o.fillCount + n) * 100) / 100;
    o.remainingCount = Math.max(0, Math.round((o.remainingCount - n) * 100) / 100);
    o.feesPaid = (o.feesPaid ?? 0) + fee;
    o.averageFillPrice = price;
    if (o.remainingCount <= 1e-9) { o.status = 'executed'; this.resting.delete(o.orderId); }
    o.updatedTs = this.now();
    const f: ExchangeFill = {
      tradeId: crypto.randomUUID(), orderId: o.orderId, clientOrderId: o.clientOrderId, ticker: o.ticker,
      side: o.side, count: n, price, isTaker, fee, ts: this.now(),
    };
    this.st.fills.push(f);
    this.emit('fill', f);
    this.emit('order', { ...o });
  }
}

const r6 = (x: number) => Math.round(x * 1e6) / 1e6;
