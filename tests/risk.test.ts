import assert from 'node:assert/strict';
import path from 'path';
import { test } from 'node:test';
import { DEFAULT_FEES } from '../bot/fees';
import { loadConfig, type RiskLimits } from '../bot/config';
import type { OrderIntent } from '../bot/oms/oms';
import { marketWorstLoss } from '../bot/risk/exposure';
import { KillSwitch } from '../bot/risk/killSwitch';
import { newRiskRoomUsd, RiskContext, RiskGateway, tennisLimits, waterfallLimits } from '../bot/risk/riskGateway';
import { tmpAudit, tmpDir } from './helpers';

const limits: RiskLimits = {
  maxContractsPerOrder: 10, maxOrderRiskFrac: 0.02, maxWindowRiskFrac: 0.03, maxTotalRiskFrac: 0.1,
  dailyLossLimitFrac: 0.05, dailyLossLimitUsd: 50, minSidePrice: 0.1, maxOrdersPerMinute: 30, maxOpenOrders: 10,
  maxBookAgeMs: 5000, maxFeedLagMs: 3000, maxIndexAgeMs: 3000, noEntryBeforeCloseSec: 15, maxConsecutiveOrderErrors: 5,
};

const intent = (o: Partial<OrderIntent> = {}): OrderIntent => ({
  ticker: 'T', asset: 'BTC', windowCloseTs: 1_000_000, side: 'bid', price: 0.45, count: 4,
  timeInForce: 'good_till_canceled', postOnly: true, reduceOnly: false, purpose: 'quote',
  fairValue: 0.5, modelId: 'm', decisionId: 'd', ...o,
});

const ctx = (o: Partial<RiskContext> = {}): RiskContext => ({
  now: 0, mode: 'paper', killEngaged: false, haltReasons: [], bankroll: 200, dailyPnl: 0,
  bookUsable: true, bestBid: 0.44, bestAsk: 0.47, indexFresh: true, marketCloseTs: 600_000, tickSize: 0.01,
  fees: DEFAULT_FEES, position: 0, marketRiskNow: 0, marketRiskWith: 1.8, windowRisk: 0, totalRisk: 0,
  ordersLastMinute: 0, openOrders: 0, modelLiveBlockers: [], ...o,
});

const gw = new RiskGateway(limits);

test('accepts a sane, positive-edge maker order', () => {
  const d = gw.check(intent(), ctx());
  assert.deepEqual(d.reasons, []);
  assert.equal(d.ok, true);
});

test('an entry costing more than the free cash is refused; exits are not', () => {
  const i = intent();
  const cost = i.count * (i.side === 'bid' ? i.price : 1 - i.price);
  assert.ok(gw.check(i, ctx({ freeCash: cost + 1 })).ok);
  const d = gw.check(i, ctx({ freeCash: cost / 2 }));
  assert.equal(d.ok, false);
  assert.match(d.reasons.join(';'), /free cash/);
  assert.ok(gw.check(intent({ side: 'ask', reduceOnly: true, purpose: 'exit', timeInForce: 'immediate_or_cancel', postOnly: false, price: 0.4, count: 1 }), ctx({ freeCash: 0, position: 2 })).ok);
});

test('the per-order contract cap holds new risk; an exit of a position larger than the cap goes out', () => {
  // Cap 10. A position of 30 (three 10-contract entries) sells in one reduce-only order; selling more than held is refused.
  const exit = (count: number) => intent({ side: 'ask', reduceOnly: true, purpose: 'exit', timeInForce: 'immediate_or_cancel', postOnly: false, price: 0.44, count });
  assert.deepEqual(gw.check(exit(30), ctx({ position: 30 })).reasons, []);
  assert.equal(gw.check(exit(31), ctx({ position: 30 })).ok, false);
  // A resting post-only exit the size of the position, too.
  assert.ok(gw.check(intent({ side: 'ask', purpose: 'exit', price: 0.48, count: 30 }), ctx({ position: 30 })).ok);
  // New risk over the cap is still refused.
  assert.match(gw.check(intent({ count: 11 }), ctx()).reasons.join(';'), /count 11 > max 10/);
});

test('fails closed on unknown bankroll, stale data, halts and kill switch', () => {
  assert.equal(gw.check(intent(), ctx({ bankroll: undefined })).ok, false);
  assert.equal(gw.check(intent(), ctx({ bookUsable: false })).ok, false);
  assert.equal(gw.check(intent(), ctx({ indexFresh: false })).ok, false);
  assert.equal(gw.check(intent(), ctx({ haltReasons: ['recon'] })).ok, false);
  assert.equal(gw.check(intent(), ctx({ killEngaged: true })).ok, false);
  assert.equal(gw.check(intent(), ctx({ bestBid: undefined })).ok, false);
});

test('kill switch: only the engine\'s marked exit passes, and only reduce-only immediate-or-cancel', () => {
  const exit = intent({ side: 'ask', price: 0.44, count: 2, reduceOnly: true, postOnly: false, timeInForce: 'immediate_or_cancel', purpose: 'exit' });
  assert.deepEqual(gw.check(exit, ctx({ killEngaged: true, position: 2 })).reasons, ['kill switch engaged'], 'an unmarked exit is refused');
  assert.ok(gw.check(exit, ctx({ killEngaged: true, killExit: true, position: 2 })).ok, 'the marked exit passes');
  assert.equal(gw.check(intent(), ctx({ killEngaged: true, killExit: true })).ok, false, 'never an entry');
  const resting = intent({ side: 'ask', price: 0.47, count: 2, reduceOnly: false, postOnly: true, timeInForce: 'good_till_canceled', purpose: 'exit' });
  assert.equal(gw.check(resting, ctx({ killEngaged: true, killExit: true, position: 2 })).ok, false, 'never a resting order');
});

test('rejects orders with no fee-net edge (price collar vs fair value)', () => {
  const d = gw.check(intent({ price: 0.5, fairValue: 0.5 }), ctx({ bestAsk: 0.52 }));
  assert.equal(d.ok, false);
  assert.ok(d.reasons.some((r) => r.includes('no fee-net edge')));
  // Taker at 0.47 with fv 0.48: 1c edge < 2c taker fee on 1 contract.
  assert.equal(gw.check(intent({ price: 0.47, count: 1, postOnly: false, timeInForce: 'immediate_or_cancel', fairValue: 0.48 }), ctx()).ok, false);
});

test('rejects longshots, bad ticks, oversize, and near-close entries', () => {
  assert.equal(gw.check(intent({ price: 0.05, fairValue: 0.2 }), ctx({ bestBid: 0.04, bestAsk: 0.07 })).ok, false);
  assert.equal(gw.check(intent({ price: 0.455 }), ctx()).ok, false);
  assert.equal(gw.check(intent({ count: 11 }), ctx()).ok, false);
  assert.equal(gw.check(intent(), ctx({ now: 590_000 })).ok, false);
  assert.equal(gw.check(intent({ price: 0.47 }), ctx()).ok, false); // post-only would cross
});

test('a resting take-profit that only reduces the position is not a longshot purchase', () => {
  // Long 4 YES; resting ask at 0.95 (= buying NO at 5c) only closes the position.
  const tp = intent({ side: 'ask', price: 0.95, fairValue: 0.9 });
  const book = { bestBid: 0.93, bestAsk: 0.96, marketRiskWith: 0 };
  assert.equal(gw.check(tp, ctx({ ...book, position: 4 })).ok, true);
  assert.equal(gw.check(tp, ctx({ ...book, position: 0 })).ok, false, 'flat: a 5c NO purchase is a longshot');
  assert.equal(gw.check({ ...tp, count: 5 }, ctx({ ...book, position: 4 })).ok, false, 'more than the position flips it');
});

test('capital thresholds: per-order, per-window, total', () => {
  assert.equal(gw.check(intent({ count: 10 }), ctx({ marketRiskWith: 4.5 })).ok, false); // $4.50 > 2% of $200
  assert.equal(gw.check(intent(), ctx({ windowRisk: 5 })).ok, false); // 5 + 1.8 > $6
  assert.equal(gw.check(intent(), ctx({ totalRisk: 19 })).ok, false);
});

test('daily loss limit rejects and asks to trip the kill switch', () => {
  const d = gw.check(intent(), ctx({ dailyPnl: -10 }));
  assert.equal(d.ok, false);
  assert.ok(d.tripKill);
});

test('reduce-only exits are allowed during a halt but must reduce', () => {
  const exit = intent({ side: 'ask', price: 0.44, count: 2, reduceOnly: true, postOnly: false, timeInForce: 'immediate_or_cancel', purpose: 'exit' });
  assert.equal(gw.check(exit, ctx({ position: 3, haltReasons: ['recon'] })).ok, true);
  assert.equal(gw.check(exit, ctx({ position: -3 })).ok, false);
  assert.equal(gw.check({ ...exit, count: 5 }, ctx({ position: 3 })).ok, false);
  assert.equal(gw.check({ ...exit, timeInForce: 'good_till_canceled' }, ctx({ position: 3 })).ok, false);
});

test('live mode refuses new risk from an unvalidated model, never an exit', () => {
  assert.equal(gw.check(intent(), ctx({ mode: 'live', modelLiveBlockers: ['no validation'] })).ok, false);
  // An immediate-or-cancel reduce-only sell, and a resting post-only sell of what is held, both go out.
  const ioc = intent({ side: 'ask', price: 0.44, count: 2, reduceOnly: true, postOnly: false, timeInForce: 'immediate_or_cancel', purpose: 'exit' });
  assert.deepEqual(gw.check(ioc, ctx({ mode: 'live', modelLiveBlockers: ['no validation'], position: 3 })).reasons, []);
  const rest = intent({ side: 'ask', price: 0.55, count: 3, purpose: 'exit', fairValue: 0.7 });
  assert.deepEqual(gw.check(rest, ctx({ mode: 'live', modelLiveBlockers: ['no validation'], position: 3, bestBid: 0.45, bestAsk: 0.6 })).reasons, []);
});

test('by default the model\'s validation never gates a live binary order (LIVE_ALLOW_UNVALIDATED_MODEL, the owner\'s choice)', () => {
  assert.equal(loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(32) }).liveAllowUnvalidated, true);
  assert.equal(loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(32), LIVE_ALLOW_UNVALIDATED_MODEL: 'false' }).liveAllowUnvalidated, false);
});

test('an exception inside a check rejects (fail closed)', () => {
  const bad = new Proxy(ctx(), { get: (t, k) => { if (k === 'fees') throw new Error('boom'); return (t as any)[k]; } });
  const d = gw.check(intent(), bad);
  assert.equal(d.ok, false);
});

test('worst-case exposure includes resting orders at the corners', () => {
  // Long 5 YES bought at 0.40 (cash -2): worst case NO -> -2.
  const pos = { yes: 5, netCash: -2, fees: 0 };
  assert.ok(Math.abs(marketWorstLoss(pos, [], DEFAULT_FEES) - 2) < 1e-9);
  // Plus a resting bid for 5 @ 0.45: if it fills and NO wins, lose another 2.25.
  const withBid = marketWorstLoss(pos, [{ ticker: 'T', side: 'bid', price: 0.45, remaining: 5, isTaker: false }], DEFAULT_FEES);
  assert.ok(Math.abs(withBid - 4.25) < 1e-9);
  // A resting ask (sell YES @ 0.6) reduces the NO-case loss; worst case unchanged at 2.
  const withAsk = marketWorstLoss(pos, [{ ticker: 'T', side: 'ask', price: 0.6, remaining: 5, isTaker: false }], DEFAULT_FEES);
  assert.ok(Math.abs(withAsk - 2) < 1e-9);
});

test('kill switch persists across restarts and cancels orders on engage', async () => {
  const file = path.join(tmpDir(), 'kill.json');
  const audit = tmpAudit();
  let cancelled = 0;
  const k = new KillSwitch(file, audit);
  k.bindCancelAll(async () => { cancelled++; });
  await k.engage('test', 'unit');
  assert.equal(cancelled, 1);
  const k2 = new KillSwitch(file, audit);
  assert.equal(k2.engaged, true);
  k2.reset('tester');
  assert.equal(new KillSwitch(file, audit).engaged, false);
});

test('kill switch: STOP ALL on a switch an automatic trip engaged marks it manual, persisted, the first cause kept; a reset clears it', async () => {
  const file = path.join(tmpDir(), 'kill.json');
  const audit = tmpAudit();
  const k = new KillSwitch(file, audit);
  await k.engage('5 consecutive order errors', 'oms');
  assert.equal(k.manual, false);
  await k.engage('operator STOP ALL', 'api:127.0.0.1');
  assert.equal(k.manual, true);
  const k2 = new KillSwitch(file, audit);
  assert.equal(k2.manual, true, 'survives a restart');
  assert.deepEqual([k2.status().source, k2.status().reason, k2.status().manualSource, k2.status().manualReason], ['oms', '5 consecutive order errors', 'api:127.0.0.1', 'operator STOP ALL']);
  // A later automatic trip does not undo it.
  await k2.engage('reconciliation break', 'recon');
  assert.equal(k2.manual, true);
  k2.reset('tester');
  assert.equal(k2.manual, false);
  assert.equal(new KillSwitch(file, audit).status().manualSource, undefined);
  await k2.engage('daily loss', 'risk');
  assert.equal(k2.manual, false, 'a fresh automatic trip after the reset is not manual');
});

test('order rate: new risk stops at 80% of the per-minute limit, exits may use all of it', () => {
  const exit = intent({ side: 'ask', reduceOnly: true, purpose: 'exit', timeInForce: 'immediate_or_cancel', postOnly: false, price: 0.44, count: 1 });
  assert.ok(gw.check(intent(), ctx({ ordersLastMinute: 23 })).ok);
  const d = gw.check(intent(), ctx({ ordersLastMinute: 24 }));
  assert.equal(d.ok, false);
  assert.match(d.reasons.join(';'), /order rate 24\/min at limit for new risk \(24; the rest is kept for exits\)/);
  assert.ok(gw.check(exit, ctx({ ordersLastMinute: 29, position: 2 })).ok, 'the reserve is there for the exit');
  assert.equal(gw.check(exit, ctx({ ordersLastMinute: 30, position: 2 })).ok, false, 'the limit itself still holds');
  // A limit too small to split keeps one order for new risk.
  assert.ok(new RiskGateway({ ...limits, maxOrdersPerMinute: 1 }).check(intent(), ctx()).ok);
});

test('order budget default: 120 a minute (96 for new risk), a fifth of Kalshi\'s Basic write budget; quotes live 20 s', () => {
  const cfg = loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(32) });
  assert.equal(cfg.risk.maxOrdersPerMinute, 120);
  assert.equal(cfg.strategy.orderTtlSec, 20);
  const def = new RiskGateway({ ...limits, maxOrdersPerMinute: cfg.risk.maxOrdersPerMinute });
  assert.ok(def.check(intent(), ctx({ ordersLastMinute: 95 })).ok);
  assert.match(def.check(intent(), ctx({ ordersLastMinute: 96 })).reasons.join(';'), /at limit for new risk \(96;/);
  // Kalshi Basic: 100 write tokens a second at 10 a write = 600 writes a minute; creates plus as many cancels fit 2.5 times over.
  assert.ok(2 * cfg.risk.maxOrdersPerMinute <= (100 / 10) * 60 / 2.5);
});

test('a resting exit (the exit curve\'s post-only sell) that sells no more than is held is checked as an exit', () => {
  // Long 10 YES valued at 0.70: resting a sell at 0.55 has no edge against the model, yet it only reduces.
  const rest = intent({ side: 'ask', price: 0.55, count: 10, purpose: 'exit', fairValue: 0.7 });
  const c = ctx({ position: 10, bestBid: 0.45, bestAsk: 0.6, haltReasons: ['session edge'], freeCash: 0 });
  assert.deepEqual(gw.check(rest, c).reasons, []);
  // More than is held, or on the side that adds, or as a quote: new risk, refused for its missing edge.
  assert.match(gw.check({ ...rest, count: 12 }, { ...c, haltReasons: [] }).reasons.join(';'), /no fee-net edge/);
  assert.match(gw.check(rest, { ...c, position: -10, haltReasons: [] }).reasons.join(';'), /no fee-net edge/);
  assert.match(gw.check({ ...rest, purpose: 'quote' }, { ...c, haltReasons: [] }).reasons.join(';'), /no fee-net edge/);
  // Still post-only: one that would cross the bid is refused.
  assert.match(gw.check({ ...rest, price: 0.45 }, c).reasons.join(';'), /post-only ask would cross/);
});

test('RISK_SIZE_CAPS off (the default): no order, window or total cap; free cash, daily loss and stale data still refuse', () => {
  assert.equal(loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(32) }).risk.sizeCaps, false);
  assert.equal(loadConfig({ DASHBOARD_TOKEN: 'x'.repeat(32), RISK_SIZE_CAPS: 'true' }).risk.sizeCaps, true);
  const off = new RiskGateway({ ...limits, sizeCaps: false });
  // $4.50 order (> 2% of $200), window and total already past their caps: the caps refuse it, off lets it through.
  const big = intent({ count: 10 });
  const full = ctx({ windowRisk: 50, totalRisk: 150, marketRiskWith: 4.5 });
  assert.match(gw.check(big, full).reasons.join(';'), /order risk.*window risk.*total risk/);
  assert.deepEqual(off.check(big, full).reasons, []);
  assert.match(off.check(big, { ...full, freeCash: 1 }).reasons.join(';'), /free cash/);
  assert.match(off.check(big, { ...full, bookUsable: false }).reasons.join(';'), /order book stale/);
  const daily = off.check(big, { ...full, dailyPnl: -100 });
  assert.equal(daily.ok, false);
  assert.ok(daily.tripKill);
});

test('with RISK_SIZE_CAPS off, the tennis budget and the waterfall total still refuse; the risk room is the free cash', () => {
  const offLimits = { ...limits, sizeCaps: false };
  const off = new RiskGateway(offLimits);
  const big = intent({ count: 10 });
  // Tennis: per-order, per-match and total caps are its own hard budget.
  const T = { orderFrac: 0.02, maxMatchFrac: 0.05, maxTotalFrac: 0.25, underdogMin: 0.1 };
  const tl = tennisLimits(T, offLimits.minSidePrice);
  assert.equal(tl.sizeCaps, true);
  assert.match(off.check(big, ctx({ limitOverrides: tl, windowRisk: 50, totalRisk: 150, marketRiskWith: 4.5 })).reasons.join(';'), /order risk.*window risk.*total risk/);
  // Waterfall armed: total held to 12.5% of the bank; the order and window caps stay off.
  const wl = waterfallLimits({}, offLimits, 0.125);
  const d = off.check(big, ctx({ limitOverrides: wl, windowRisk: 50, totalRisk: 30, marketRiskWith: 4.5 }));
  assert.deepEqual(d.reasons.map((r) => r.split(' ')[0] + ' ' + r.split(' ')[1]), ['total risk']);
  assert.ok(off.check(big, ctx({ limitOverrides: wl, windowRisk: 50, totalRisk: 10, marketRiskWith: 4.5 })).ok);
  // With the caps on, the waterfall only lowers the total cap, as before.
  assert.deepEqual(waterfallLimits({}, limits, 0.125), { maxTotalRiskFrac: 0.1 });
  assert.deepEqual(waterfallLimits({}, { ...limits, maxTotalRiskFrac: 0.2 }, 0.125), { maxTotalRiskFrac: 0.125 });
  // Risk room (engine and backtest): window/total caps vs free cash only.
  assert.equal(newRiskRoomUsd(true, 0.03, 0.1, 200, 4, 0, 100), 2);
  assert.equal(newRiskRoomUsd(false, 0.03, 0.1, 200, 4, 0, 100), 100);
  assert.equal(newRiskRoomUsd(undefined, 0.03, 0.1, 200, 4, 0, 100), 2);
});
