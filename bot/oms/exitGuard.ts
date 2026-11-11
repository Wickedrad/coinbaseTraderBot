// The in-flight exit guard (the answer given to Steven, Nov 11 9:10 AM EST / 14:10 UTC). Live, an exit's REST acknowledgement
// can say it filled before the websocket fill reaches the books: until then the position still reads as held, and the next
// evaluation would sell it again. So no new exit order goes out on a market while an exit order of ours sent there less than
// EXIT_GUARD_MS (2 s) ago is still travelling (not acknowledged, or an immediate order not finished) or has fills the exchange
// reported that are not booked yet. After 2 s the guard lets go whatever the order's state: a lost fill must not hold every
// exit back. An acknowledged resting sell (the exit curve's, the hunt's wall ask) is not travelling and holds nothing back.
// Paper books its fills inside submit, before the acknowledgement, so the guard never holds there; the replay (research/
// backtest.ts) runs it on the exits its latency model still has travelling. The engine (paper and live alike) runs it on the
// OMS's records.

import { TERMINAL, type OrderPurpose, type OrderRecord } from './orderState';

/** How long after it is sent an exit order can hold the next one back (ms). */
export const EXIT_GUARD_MS = 2000;

/** An order that sells or buys back what is held: an exit, or anything reduce-only. */
export function isExitOrder(o: { purpose: OrderPurpose; reduceOnly: boolean }): boolean {
  return o.purpose === 'exit' || o.reduceOnly;
}

export type GuardOrder = Pick<OrderRecord, 'ticker' | 'purpose' | 'reduceOnly' | 'timeInForce' | 'state' | 'createdTs' | 'filledCount' | 'exchangeFillCount'>;

/** The exit order on `ticker` that holds a new exit back at `now` (undefined: none): sent less than `windowMs` ago and still
 *  travelling, or with fills the exchange reported that the books have not got yet. */
export function exitInFlight<T extends GuardOrder>(orders: Iterable<T>, ticker: string, now: number, windowMs = EXIT_GUARD_MS): T | undefined {
  for (const o of orders) {
    if (o.ticker !== ticker || !isExitOrder(o) || !(now - o.createdTs < windowMs)) continue;
    const unbooked = o.exchangeFillCount > o.filledCount + 1e-9;
    const travelling = !TERMINAL.has(o.state) && (o.timeInForce !== 'good_till_canceled' || o.state === 'PENDING_NEW' || o.state === 'UNKNOWN');
    if (unbooked || travelling) return o;
  }
  return undefined;
}

/** Why a new exit waits (for notes and the audit). */
export function exitInFlightWhy(o: GuardOrder, now: number): string {
  const age = Math.max(0, (now - o.createdTs) / 1000).toFixed(1);
  const what = o.exchangeFillCount > o.filledCount + 1e-9 ? `has fills not booked yet (${o.filledCount} of ${o.exchangeFillCount} booked)` : 'has not finished yet';
  return `exit in flight: the exit order sent ${age} s ago ${what}; no new exit for up to ${EXIT_GUARD_MS / 1000} s after it`;
}
