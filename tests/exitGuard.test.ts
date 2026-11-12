import assert from 'node:assert/strict';
import { test } from 'node:test';
import { EXIT_GUARD_MS, exitInFlight, exitInFlightWhy, isExitOrder, type GuardOrder } from '../bot/oms/exitGuard';

// The in-flight exit guard (the answer given to Steven, Nov 11 9:10 AM EST / 14:10 UTC): no new exit on a market while an exit
// of ours sent there less than 2 s ago is still travelling or has fills the books have not got yet.
const T0 = 1_700_000_000_000;
const ioc = (o: Partial<GuardOrder> = {}): GuardOrder => ({
  ticker: 'T', purpose: 'exit', reduceOnly: true, timeInForce: 'immediate_or_cancel', state: 'PENDING_NEW', createdTs: T0, filledCount: 0, exchangeFillCount: 0, ...o,
});

test('exit guard: an exit sent less than 2 s ago and not finished holds the next one back; at 2 s it lets go', () => {
  assert.equal(EXIT_GUARD_MS, 2000);
  const o = ioc();
  assert.equal(exitInFlight([o], 'T', T0), o);
  assert.equal(exitInFlight([o], 'T', T0 + 1999), o);
  assert.equal(exitInFlight([o], 'T', T0 + 2000), undefined, 'a lost acknowledgement or fill must not hold every exit back');
  assert.equal(exitInFlight([ioc({ state: 'UNKNOWN' })], 'T', T0 + 500)?.state, 'UNKNOWN');
  assert.equal(exitInFlight([ioc({ state: 'ACKED' })], 'T', T0 + 500)?.state, 'ACKED', 'an immediate order acknowledged, not yet finished');
  assert.equal(exitInFlight([ioc({ state: 'PARTIALLY_FILLED', exchangeFillCount: 4, filledCount: 4 })], 'T', T0 + 500)?.state, 'PARTIALLY_FILLED');
  assert.equal(exitInFlight([o], 'U', T0 + 500), undefined, 'another market is not held');
  assert.match(exitInFlightWhy(o, T0 + 1200), /^exit in flight: the exit order sent 1\.2 s ago has not finished yet; no new exit for up to 2 s after it$/);
});

test('exit guard: a filled exit whose fills are not booked yet holds; once they are booked it does not', () => {
  // Live: the REST acknowledgement says FILLED 4 before the websocket fill reaches the books.
  const unbooked = ioc({ state: 'FILLED', exchangeFillCount: 4, filledCount: 0 });
  assert.equal(exitInFlight([unbooked], 'T', T0 + 800), unbooked);
  assert.match(exitInFlightWhy(unbooked, T0 + 800), /has fills not booked yet \(0 of 4 booked\)/);
  assert.equal(exitInFlight([ioc({ state: 'FILLED', exchangeFillCount: 4, filledCount: 2 })], 'T', T0 + 800)?.filledCount, 2, 'part booked');
  assert.equal(exitInFlight([ioc({ state: 'FILLED', exchangeFillCount: 4, filledCount: 4 })], 'T', T0 + 800), undefined, 'booked: done');
  assert.equal(exitInFlight([ioc({ state: 'FILLED', exchangeFillCount: 4, filledCount: 0 })], 'T', T0 + 2000), undefined, 'after 2 s it lets go');
  // An immediate order that filled nothing and finished (the bid was pulled), or was rejected: nothing to wait for.
  assert.equal(exitInFlight([ioc({ state: 'CANCELED' })], 'T', T0 + 300), undefined);
  assert.equal(exitInFlight([ioc({ state: 'REJECTED' })], 'T', T0 + 300), undefined);
  assert.equal(exitInFlight([ioc({ state: 'CANCELED', exchangeFillCount: 3, filledCount: 0 })], 'T', T0 + 300)?.state, 'CANCELED', 'canceled after a fill not booked yet');
});

test('exit guard: a resting sell acknowledged is not travelling; entries and quotes never hold an exit back', () => {
  // The exit curve's resting sell (or the hunt's wall ask), acknowledged: it rests, the next exit decides as before.
  assert.equal(exitInFlight([ioc({ timeInForce: 'good_till_canceled', state: 'ACKED' })], 'T', T0 + 300), undefined);
  assert.equal(exitInFlight([ioc({ timeInForce: 'good_till_canceled', state: 'PARTIALLY_FILLED', exchangeFillCount: 2, filledCount: 2 })], 'T', T0 + 300), undefined);
  assert.ok(exitInFlight([ioc({ timeInForce: 'good_till_canceled', state: 'PENDING_NEW' })], 'T', T0 + 300), 'not acknowledged yet');
  assert.ok(exitInFlight([ioc({ timeInForce: 'good_till_canceled', state: 'ACKED', exchangeFillCount: 2, filledCount: 0 })], 'T', T0 + 300), 'its fills not booked');
  // What counts as an exit: purpose exit, or anything reduce-only.
  assert.equal(isExitOrder({ purpose: 'exit', reduceOnly: false }), true);
  assert.equal(isExitOrder({ purpose: 'quote', reduceOnly: true }), true);
  assert.equal(isExitOrder({ purpose: 'entry', reduceOnly: false }), false);
  assert.equal(exitInFlight([ioc({ purpose: 'entry', reduceOnly: false })], 'T', T0 + 300), undefined);
  assert.equal(exitInFlight([ioc({ purpose: 'quote', reduceOnly: false, timeInForce: 'good_till_canceled' })], 'T', T0 + 300), undefined);
  // The first one that holds is named, among finished ones.
  const held = ioc({ createdTs: T0 + 100 });
  assert.equal(exitInFlight([ioc({ state: 'FILLED', exchangeFillCount: 1, filledCount: 1 }), held], 'T', T0 + 300), held);
});
