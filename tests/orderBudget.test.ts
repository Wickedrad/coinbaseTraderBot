import assert from 'node:assert/strict';
import { test } from 'node:test';
import { orderBand, orderBudget } from '../bot/sizing/orderBudget';

const base = { bankroll: 200, orderFrac: 0.02, sizeMult: 1, riskScale: 1, fCapUsd: Infinity, paperOrderUsd: 0, maxContractsPerOrder: 50 };

test('order budget: tier x session/regime x risk scale, capped by optimal f', () => {
  assert.deepEqual(orderBudget(base), { maxOrderRiskUsd: 4, maxContracts: 50, boundBy: 'tier' });
  const shrunk = orderBudget({ ...base, sizeMult: 0.5, riskScale: 0.5 });
  assert.equal(shrunk.maxOrderRiskUsd, 1);
  assert.equal(shrunk.maxContracts, 25);
  const capped = orderBudget({ ...base, fCapUsd: 2.5 });
  assert.equal(capped.maxOrderRiskUsd, 2.5);
  assert.equal(capped.boundBy, 'optimal_f');
  // A cap above the tier's stake changes nothing; a cap of 0 (no edge, live) stops the order.
  assert.equal(orderBudget({ ...base, fCapUsd: 10 }).boundBy, 'tier');
  assert.equal(orderBudget({ ...base, fCapUsd: 0 }).maxOrderRiskUsd, 0);
});

test('order budget: a paper order size replaces the rest', () => {
  const b = orderBudget({ ...base, paperOrderUsd: 20, sizeMult: 0.5, fCapUsd: 1 });
  assert.deepEqual(b, { maxOrderRiskUsd: 20, maxContracts: 50, fixedOrderUsd: 20, boundBy: 'paper' });
});

test('order budget: the order band (ORDER_USD_MIN / ORDER_USD_MAX, Steven Oct 30) replaces the tier, the scales and optimal f; a paper size wins', () => {
  assert.equal(orderBand(0, 20), undefined, 'a minimum of 0: off');
  assert.deepEqual(orderBand(10, 5), { min: 10, max: 10 }, 'the top never below the minimum');
  const b = orderBudget({ ...base, bandUsd: orderBand(10, 20), sizeMult: 0.5, riskScale: 0.25, fCapUsd: 0.5 });
  assert.deepEqual(b, { maxOrderRiskUsd: 20, maxContracts: 50, band: { min: 10, max: 20 }, boundBy: 'band' });
  assert.equal(orderBudget({ ...base, bandUsd: orderBand(10, 20), paperOrderUsd: 15 }).boundBy, 'paper');
});

test('BAND_SIZE_MULT: off ignores sizeMult; shrink never goes above the top; scale goes up to BAND_SIZE_MAX', () => {
  const b = { bankroll: 200, orderFrac: 0.02, riskScale: 1, fCapUsd: Infinity, paperOrderUsd: 0, bandUsd: { min: 10, max: 20 }, maxContractsPerOrder: 50 };
  assert.deepEqual(orderBudget({ ...b, sizeMult: 0.5 }).band, { min: 10, max: 20 });
  assert.deepEqual(orderBudget({ ...b, sizeMult: 0.5, bandSizeMult: 'shrink' }).band, { min: 5, max: 10 });
  assert.deepEqual(orderBudget({ ...b, sizeMult: 1.4, bandSizeMult: 'shrink' }).band, { min: 10, max: 20 });
  assert.deepEqual(orderBudget({ ...b, sizeMult: 1.4, bandSizeMult: 'scale' }).band, { min: 14, max: 28 });
  assert.deepEqual(orderBudget({ ...b, sizeMult: 2, bandSizeMult: 'scale', bandSizeMax: 1.5 }).band, { min: 15, max: 30 });
  const zero = orderBudget({ ...b, sizeMult: 0, bandSizeMult: 'shrink' });
  assert.equal(zero.maxOrderRiskUsd, 0);
  assert.equal(zero.maxContracts, 0);
  assert.equal(orderBudget({ ...b, paperOrderUsd: 20, sizeMult: 0.5, bandSizeMult: 'shrink' }).fixedOrderUsd, 10);
  assert.equal(orderBudget({ ...b, paperOrderUsd: 20, sizeMult: 0.5 }).fixedOrderUsd, 20);
});
