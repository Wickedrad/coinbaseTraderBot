import assert from 'node:assert/strict';
import { test } from 'node:test';
import { loadConfig, type StrategyConfig } from '../bot/config';
import { DEFAULT_FEES } from '../bot/fees';
import { decide, type MarketView } from '../bot/strategy/fairValueStrategy';
import type { OrderIntent } from '../bot/oms/oms';
import { RiskGateway, type RiskContext } from '../bot/risk/riskGateway';
import { seriesBlocked, seriesEdgeAdd, seriesOf } from '../bot/strategy/seriesRules';

const env = { DASHBOARD_TOKEN: 'x'.repeat(32) };

test('series rules: off by default, parsed from SERIES_EDGE_ADD / SERIES_NO_ENTRY', () => {
  const d = loadConfig(env).strategy;
  assert.deepEqual(d.seriesEdgeAdd, {});
  assert.deepEqual(d.seriesNoEntry, []);
  assert.equal(seriesEdgeAdd(d, 'KXBTCD-26OCT2802-T80799.99'), 0);
  assert.equal(seriesBlocked(d, 'KXBTCD-26OCT2802-T80799.99'), false);
  const s = loadConfig({ ...env, SERIES_EDGE_ADD: 'KXBTCD:0.03, kxethd:0.02', SERIES_NO_ENTRY: 'KXDOGE15M' }).strategy;
  assert.equal(seriesEdgeAdd(s, 'KXBTCD-26OCT2802-T80799.99'), 0.03);
  assert.equal(seriesEdgeAdd(s, 'KXETHD-26OCT2809-T2334.99'), 0.02);
  assert.equal(seriesEdgeAdd(s, 'KXBTC15M-26OCT272115-15'), 0);
  assert.equal(seriesBlocked(s, 'KXDOGE15M-26OCT280315-15'), true);
  assert.equal(seriesBlocked(s, 'KXDOGE-26OCT2807-B0.077'), false);
  assert.equal(seriesOf('KXSOL15M-26OCT280315-15'), 'KXSOL15M');
  assert.throws(() => loadConfig({ ...env, SERIES_EDGE_ADD: 'KXBTCD:2' }));
  assert.throws(() => loadConfig({ ...env, SERIES_EDGE_ADD: 'KXBTCD' }));
});

test('RISK_MAX_SIDE_PRICE: unset keeps the symmetric band; set, it caps new risk only', () => {
  assert.equal(loadConfig(env).risk.maxSidePrice, undefined);
  assert.equal(loadConfig({ ...env, RISK_MAX_SIDE_PRICE: '0.8' }).risk.maxSidePrice, 0.8);
  const base = loadConfig({ ...env, STRATEGY_CADENCE: 'continuous' }).strategy;
  const cfg: StrategyConfig = { ...base, style: 'both', minEdge: 0.02, takerBuffer: 0.01, inventorySkewPerContract: 0, volSeasonality: false };
  const view = (o: Partial<MarketView> = {}): MarketView => ({
    ticker: 'KXBTCD-X', pYes: 0.97, bestBid: { price: 0.84, size: 50 }, bestAsk: { price: 0.85, size: 50 }, position: 0,
    bankroll: 200, maxOrderRiskUsd: 10, maxContracts: 10, minSidePrice: 0.1, tauSec: 400, noEntryBeforeCloseSec: 15,
    fastMove: false, tickSize: 0.01, fees: DEFAULT_FEES, nowSec: 1000, closeSec: 1400, ...o,
  });
  // Without the cap the strategy buys YES at 0.85 (fair 0.97); with a 0.80 cap it buys nothing new.
  const free = decide(view(), cfg);
  assert.ok(free.place.some((p) => p.side === 'bid' && p.purpose !== 'exit'));
  const capped = decide(view({ maxSidePrice: 0.8 }), cfg);
  assert.equal(capped.place.filter((p) => p.side === 'bid').length, 0);
  // A short YES position (held NO) still gets its unwind bid above the cap.
  const unwind = decide(view({ maxSidePrice: 0.8, position: -5, pYes: 0.9 }), { ...cfg, style: 'maker' });
  const bid = unwind.place.find((p) => p.side === 'bid');
  assert.ok(bid && bid.count >= 5, 'the unwind of the held NO stays quoted');
  // The gateway refuses new risk above the cap and lets reductions through.
  const limits = { ...loadConfig({ ...env, RISK_MAX_SIDE_PRICE: '0.8' }).risk, maxOrderRiskFrac: 0.05, maxWindowRiskFrac: 0.1, maxTotalRiskFrac: 0.25 };
  const g = new RiskGateway(limits);
  const intent = (o: Partial<OrderIntent> = {}): OrderIntent => ({
    ticker: 'T', asset: 'BTC', windowCloseTs: 1_000_000, side: 'bid', price: 0.85, count: 2,
    timeInForce: 'good_till_canceled', postOnly: true, reduceOnly: false, purpose: 'quote', fairValue: 0.95, modelId: 'm', decisionId: 'd', ...o,
  });
  const ctx = (o: Partial<RiskContext> = {}): RiskContext => ({
    now: 0, mode: 'paper', killEngaged: false, haltReasons: [], bankroll: 200, dailyPnl: 0,
    bookUsable: true, bestBid: 0.84, bestAsk: 0.86, indexFresh: true, marketCloseTs: 600_000, tickSize: 0.01,
    fees: DEFAULT_FEES, position: 0, marketRiskNow: 0, marketRiskWith: 1.8, windowRisk: 0, totalRisk: 0,
    ordersLastMinute: 0, openOrders: 0, modelLiveBlockers: [], ...o,
  });
  const d = g.check(intent(), ctx());
  assert.equal(d.ok, false);
  assert.ok(d.reasons.some((r) => r.includes('above 0.8')), d.reasons.join('; '));
  assert.ok(new RiskGateway({ ...limits, maxSidePrice: undefined }).check(intent(), ctx()).reasons.every((r) => !r.includes('above')));
  assert.ok(!g.check(intent({ side: 'bid', reduceOnly: true, purpose: 'exit', timeInForce: 'immediate_or_cancel', postOnly: false, price: 0.86 }), ctx({ position: -2 })).reasons.some((r) => r.includes('above')));
});
