/** Independent audit of saved paper fills against their actual public-book and fee receipts. */
import { orderFee, type FeeSchedule } from '../../bot/fees';
export interface SavedEdgeFill { at: number; ticker: string; side: 'yes' | 'no'; action: 'entry' | 'exit'; sidePrice: number; quantity: number; fee: number }
export interface SavedEdgeBook { contract: { ticker: string }; quote: { knownAt: number; bids: Array<{ price: number; size: number }>; asks: Array<{ price: number; size: number }> }; fees: { schedule: FeeSchedule } }
export function auditEdgeLedger(fills: SavedEdgeFill[], books: SavedEdgeBook[], adverse = 0.01) {
  const receipts = new Map(books.map((b) => [`${b.contract.ticker}:${b.quote.knownAt}`, b]));
  const held = new Map<string, { side: string; quantity: number; basis: number }>();
  let cash = 200, feesPaid = 0, realized = 0, stressCost = 0, lastAt = 0;
  for (const f of fills) {
    if (!Number.isFinite(f.quantity) || f.quantity <= 0 || f.at < lastAt || !['entry', 'exit'].includes(f.action) || !['yes', 'no'].includes(f.side)) throw new Error('invalid fill quantity, side or order'); lastAt = f.at;
    const b = receipts.get(`${f.ticker}:${f.at}`); if (!b) throw new Error('fill lacks same-arrival book evidence');
    const buy = f.action === 'entry', yes = f.side === 'yes', levels = buy === yes ? b.quote.asks : b.quote.bids;
    const level = levels.find((l) => Math.abs((yes ? l.price : 1 - l.price) - f.sidePrice) < 1e-9);
    if (!level || f.quantity > level.size + 1e-8) throw new Error('fill price or quantity exceeds observed depth');
    const fee = orderFee(f.quantity, buy ? f.sidePrice : 1 - f.sidePrice, true, b.fees.schedule);
    if (Math.abs(fee - f.fee) > 1e-7) throw new Error('fill fee differs from recorded native schedule'); feesPaid += fee;
    if (buy) {
      const p = held.get(f.ticker) ?? { side: f.side, quantity: 0, basis: 0 };
      if (p.side !== f.side) throw new Error('unrecorded exposure flip');
      const cost = f.quantity * f.sidePrice + fee; cash -= cost; p.quantity += f.quantity; p.basis += cost; held.set(f.ticker, p);
    } else {
      const p = held.get(f.ticker); if (!p || p.side !== f.side || p.quantity + 1e-8 < f.quantity) throw new Error('sale exceeds funded position');
      const basis = p.basis * f.quantity / p.quantity, proceeds = f.quantity * f.sidePrice - fee; cash += proceeds; realized += proceeds - basis;
      p.quantity -= f.quantity; p.basis -= basis; if (p.quantity < 1e-9) held.delete(f.ticker);
    }
    if (cash < -1e-6) throw new Error('paper account used unfunded capital');
    const price = Math.max(0, Math.min(1, f.sidePrice + (buy ? 1 : -1) * adverse));
    stressCost += f.quantity * Math.abs(price - f.sidePrice) + orderFee(f.quantity, buy ? price : 1 - price, true, b.fees.schedule) - fee;
  }
  return { endingCash: cash, paidFees: feesPaid, realized, openBasis: [...held.values()].reduce((s, p) => s + p.basis, 0), unresolved: held.size, stressCost };
}
