import assert from 'node:assert/strict';
import fs from 'fs';
import path from 'path';
import { test } from 'node:test';
import { OrderRejectedError, OrderStateUnknownError } from '../bot/kalshi/types';
import { Oms, OrderIntent } from '../bot/oms/oms';
import { canTransition } from '../bot/oms/orderState';
import { openBankedUsd, openEntryFee, openSidePrice, PositionBook as Book } from '../bot/oms/positions';
import { DEFAULT_FEES } from '../bot/fees';
import { FakeGateway } from './fakeGateway';
import { tmpAudit, tmpDir } from './helpers';

function mk(gw: FakeGateway, statePath = path.join(tmpDir(), 'oms.json')) {
  return new Oms({ gateway: gw, audit: tmpAudit(), statePath, feesFor: () => DEFAULT_FEES, sleep: async () => undefined });
}

const intent = (over: Partial<OrderIntent> = {}): OrderIntent => ({
  ticker: 'KXBTC15M-X', asset: 'BTC', windowCloseTs: 10_000_000, side: 'bid', price: 0.45, count: 5,
  timeInForce: 'good_till_canceled', postOnly: true, reduceOnly: false, purpose: 'quote',
  fairValue: 0.5, modelId: 'test', decisionId: 'd1', ...over,
});

test('state machine forbids leaving terminal states', () => {
  assert.equal(canTransition('FILLED', 'ACKED'), false);
  assert.equal(canTransition('CANCELED', 'PARTIALLY_FILLED'), false);
  assert.equal(canTransition('ACKED', 'PARTIALLY_FILLED'), true);
});

test('acceptance is not a fill: position unchanged until a fill arrives', async () => {
  const gw = new FakeGateway();
  const oms = mk(gw);
  const rec = await oms.submit(intent());
  assert.equal(rec.state, 'ACKED');
  assert.equal(oms.positions.position('KXBTC15M-X'), 0);
  oms.onFill({ tradeId: 't1', orderId: rec.orderId!, ticker: rec.ticker, side: 'bid', count: 2, price: 0.45, isTaker: false, ts: 1 });
  assert.equal(rec.state, 'PARTIALLY_FILLED');
  assert.equal(oms.positions.position('KXBTC15M-X'), 2);
  oms.onFill({ tradeId: 't2', orderId: rec.orderId!, ticker: rec.ticker, side: 'bid', count: 3, price: 0.45, isTaker: false, ts: 2 });
  assert.equal(rec.state, 'FILLED');
  assert.equal(oms.positions.position('KXBTC15M-X'), 5);
});

test('duplicate fills (WS + REST replay) are applied once', async () => {
  const gw = new FakeGateway();
  const oms = mk(gw);
  const rec = await oms.submit(intent());
  const f = { tradeId: 'dup', orderId: rec.orderId!, ticker: rec.ticker, side: 'bid' as const, count: 1, price: 0.45, isTaker: false, ts: 1 };
  assert.equal(oms.onFill(f), true);
  assert.equal(oms.onFill(f), false);
  assert.equal(oms.positions.position(rec.ticker), 1);
});

test('timeout that actually landed is resolved by client_order_id query, never resent', async () => {
  const gw = new FakeGateway();
  gw.onCreate = () => 'land-then-throw';
  const oms = mk(gw);
  const rec = await oms.submit(intent());
  assert.equal(gw.creates.length, 1, 'no second create');
  assert.equal(gw.orders.length, 1);
  assert.equal(rec.state, 'ACKED');
  assert.equal(rec.orderId, 'ex-1');
});

test('timeout that never landed is resent with the SAME client_order_id', async () => {
  const gw = new FakeGateway();
  gw.onCreate = (req, n) => (n === 1 ? new OrderStateUnknownError('network') : gw.accept(req));
  const oms = mk(gw);
  const rec = await oms.submit(intent());
  assert.equal(gw.creates.length, 2);
  assert.equal(gw.creates[0].clientOrderId, gw.creates[1].clientOrderId);
  assert.equal(rec.state, 'ACKED');
});

test('definitive rejection moves to REJECTED and counts consecutive errors', async () => {
  const gw = new FakeGateway();
  gw.onCreate = () => new OrderRejectedError('HTTP 400: bad', 400, 'invalid');
  const oms = mk(gw);
  let errs = 0;
  oms.on('order_error', (n: number) => { errs = n; });
  const rec = await oms.submit(intent());
  await oms.submit(intent());
  assert.equal(rec.state, 'REJECTED');
  assert.equal(errs, 2);
});

test('not enough cash and a missing location attestation are reported apart, never counted toward the kill switch', async () => {
  const gw = new FakeGateway();
  const replies = [
    new OrderRejectedError('HTTP 400: {"error":{"code":"insufficient_balance","message":"insufficient balance"}}', 400, 'insufficient_balance'),
    new OrderRejectedError('HTTP 403: {"error":{"code":"Your_location_attestation_for_API_trading_is_missing_or_expired."}}', 403, 'Your_location_attestation_for_API_trading_is_missing_or_expired.'),
  ];
  let n = 0;
  gw.onCreate = () => replies[n++ % 2];
  const oms = mk(gw);
  let errs = 0, cash = 0, blocked = 0;
  oms.on('order_error', () => { errs++; });
  oms.on('insufficient_balance', () => { cash++; });
  oms.on('account_blocked', () => { blocked++; });
  for (let i = 0; i < 6; i++) await oms.submit(intent());
  assert.equal(errs, 0);
  assert.equal(cash, 3);
  assert.equal(blocked, 3);
});

test('client_order_id is persisted before the order is sent and state survives restart', async () => {
  const gw = new FakeGateway();
  const file = path.join(tmpDir(), 'oms.json');
  let persistedBeforeSend = false;
  gw.onCreate = (req) => {
    persistedBeforeSend = fs.readFileSync(file, 'utf8').includes(req.clientOrderId);
    return gw.accept(req);
  };
  const oms = mk(gw, file);
  const rec = await oms.submit(intent());
  assert.ok(persistedBeforeSend);
  oms.flush(); // later transitions are coalesced; shutdown flushes them
  const reloaded = mk(gw, file);
  assert.equal(reloaded.get(rec.clientOrderId)?.state, 'ACKED');
});

test('cancel requested before ack is honoured on ack; exits tracked until confirmed', async () => {
  const gw = new FakeGateway();
  const oms = mk(gw);
  const rec = await oms.submit(intent());
  await oms.cancel(rec.clientOrderId, 'test');
  assert.equal(rec.state, 'CANCELED');
  assert.deepEqual(gw.cancels, ['ex-1']);
});

test('cancelAll also cancels exchange orders the OMS does not know', async () => {
  const gw = new FakeGateway();
  const oms = mk(gw);
  gw.accept({ ticker: 'X', side: 'bid', count: 1, price: 0.3, timeInForce: 'good_till_canceled', postOnly: true, reduceOnly: false, selfTradePrevention: 'taker_at_cross', clientOrderId: 'foreign' });
  await oms.cancelAll('kill');
  assert.ok(gw.cancels.includes('ex-1'));
});

test('live (leaveExternalOrders): cancelAll cancels the bot\'s own orders and leaves the operator\'s alone', async () => {
  const gw = new FakeGateway();
  const oms = new Oms({ gateway: gw, audit: tmpAudit(), statePath: path.join(tmpDir(), 'oms.json'), feesFor: () => DEFAULT_FEES, sleep: async () => undefined, leaveExternalOrders: true });
  gw.accept({ ticker: 'X', side: 'ask', count: 4, price: 0.7, timeInForce: 'good_till_canceled', postOnly: false, reduceOnly: false, selfTradePrevention: 'taker_at_cross', clientOrderId: 'placed-on-kalshi' });
  const ours = await oms.submit(intent());
  await oms.cancelAll('shutdown (SIGTERM)');
  assert.deepEqual(gw.cancels.filter((id) => id === 'ex-1'), [], 'the operator\'s order stays');
  assert.ok(gw.cancels.includes(ours.orderId!));
  assert.equal(gw.orders.find((o) => o.orderId === 'ex-1')!.status, 'resting');
});

test('settlement realizes fee-inclusive PnL', async () => {
  const gw = new FakeGateway();
  const oms = mk(gw);
  const rec = await oms.submit(intent({ side: 'bid', price: 0.4, count: 10 }));
  oms.onFill({ tradeId: 'a', orderId: rec.orderId!, ticker: rec.ticker, side: 'bid', count: 10, price: 0.4, isTaker: true, fee: 0.17, ts: 1 });
  const m = oms.settle(rec.ticker, 'yes')!;
  assert.ok(Math.abs(m.realized! - (10 - 4 - 0.17)) < 1e-9);
  assert.equal(oms.positions.position(rec.ticker), 0);
});

test('position book: the open contracts\' cost at the average, apart from earlier exits; through zero the other side opens', () => {
  const b = new Book();
  const f = (side: 'bid' | 'ask', count: number, price: number, fee: number) => b.applyFill({ ticker: 'X', side, count, price, fee });
  const at = () => [+openSidePrice(b.get('X'))!.toFixed(4), +openEntryFee(b.get('X'))!.toFixed(4)];
  f('bid', 10, 0.4, 0.1);
  f('bid', 10, 0.5, 0.1);
  assert.deepEqual(at(), [0.45, 0.01], 'two buys: the average');
  f('ask', 5, 0.7, 0.05);
  assert.deepEqual(at(), [0.45, 0.01], 'a profitable partial exit leaves the rest at its own cost (net cash would read 0.22)');
  f('ask', 20, 0.6, 0.2);
  const x = b.get('X')!;
  assert.equal(x.yes, -5);
  assert.deepEqual(at(), [0.4, 0.01], 'through zero: 5 NO at 0.40 (YES sold at 0.60), their share of the fee');
  f('bid', 5, 0.3, 0.05);
  assert.deepEqual([b.get('X')!.openCost, b.get('X')!.openFees, openSidePrice(b.get('X'))], [0, 0, undefined], 'flat');
  // A position saved before the open cost was kept reads net cash, as before, and keeps the average from its next fill.
  const old = new Book([{ ticker: 'O', closeTs: 0, asset: '', yes: 10, netCash: -4, fees: 0.1, settled: false }]);
  assert.deepEqual([openSidePrice(old.get('O')), openEntryFee(old.get('O'))], [0.4, 0.01]);
  old.applyFill({ ticker: 'O', side: 'ask', count: 5, price: 0.6, fee: 0.05 });
  assert.deepEqual([+openSidePrice(old.get('O'))!.toFixed(4), +openEntryFee(old.get('O'))!.toFixed(4)], [0.4, 0.01]);
  b.applyFill({ ticker: 'S', side: 'bid', count: 3, price: 0.2, fee: 0 });
  b.settle('S', 'no', 1);
  assert.deepEqual([b.get('S')!.openCost, b.get('S')!.openFees], [0, 0]);
});

test('position book: what partial sales of the open position banked since it opened, after fees; flat or through zero starts again at 0', () => {
  // The trade's profit (the answer given to Steven, Nov 11 9:10 AM EST / 14:10 UTC): banked plus the rest at the bid.
  const b = new Book();
  const f = (side: 'bid' | 'ask', count: number, price: number, fee: number) => b.applyFill({ ticker: 'X', side, count, price, fee });
  const banked = () => Math.round(openBankedUsd(b.get('X')) * 1e4) / 1e4;
  f('bid', 10, 0.4, 0.17);
  assert.equal(banked(), 0, 'nothing sold yet');
  // 4 sold at 0.59 for a 7c fee: 4 x (0.59 - 0.40) less 4/10 of the 17c entry fee less the 7c exit fee.
  f('ask', 4, 0.59, 0.07);
  assert.equal(banked(), 0.622);
  // Adding to the position keeps what was banked; the next sale banks against the new average.
  f('bid', 2, 0.46, 0.03);
  const avg = openSidePrice(b.get('X'))!;
  assert.equal(Math.round(avg * 1e4) / 1e4, 0.415, '6 at 0.40 and 2 at 0.46');
  f('ask', 3, 0.6, 0.05);
  const fee3 = (0.102 + 0.03) * (3 / 8);
  assert.equal(banked(), Math.round((0.622 + 3 * (0.6 - 0.415) - fee3 - 0.05) * 1e4) / 1e4);
  // Flat: nothing banked on the next position.
  f('ask', 5, 0.55, 0.05);
  assert.equal(b.get('X')!.yes, 0);
  assert.equal(banked(), 0);
  assert.equal(b.get('X')!.openBanked, 0);
  // A NO position: 10 NO at 0.30 (YES sold at 0.70); 5 bought back at a YES ask of 0.55 sells NO at 0.45.
  f('ask', 10, 0.7, 0.15);
  f('bid', 5, 0.55, 0.09);
  assert.equal(banked(), Math.round((5 * (0.45 - 0.3) - 0.075 - 0.09) * 1e4) / 1e4);
  // Through zero: the fill that closes the NO side opens a YES side with nothing banked.
  f('bid', 8, 0.5, 0.14);
  assert.equal(b.get('X')!.yes, 3);
  assert.equal(banked(), 0);
  // A position saved before Nov 11 has none (read as 0) until its next partial sale.
  const old = new Book([{ ticker: 'O', closeTs: 0, asset: '', yes: 10, netCash: -4, fees: 0.17, openCost: 4, openFees: 0.17, settled: false }]);
  assert.equal(openBankedUsd(old.get('O')), 0);
  old.applyFill({ ticker: 'O', side: 'ask', count: 4, price: 0.59, fee: 0.07 });
  assert.equal(Math.round(openBankedUsd(old.get('O')) * 1e4) / 1e4, 0.622);
  b.settle('X', 'yes', 1);
  assert.equal(openBankedUsd(b.get('X')), 0);
});
