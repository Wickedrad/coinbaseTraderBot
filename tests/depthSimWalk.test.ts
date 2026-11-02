import assert from 'node:assert/strict';
import { test } from 'node:test';
import { DepthSim, type DepthModel } from '../research/history/depthSim';

const MIN = 60_000;
const q = { n: 1, mean: 0, p10: 1, p50: 1, p90: 2 };
// A book with ten quoted levels of 100 a side, no other flow: only the walk to the next quote trades.
const model: DepthModel = {
  days: ['x'],
  shape: [{ ti: 0, mi: 0, samples: 1, levelQuoted: Array(10).fill(1), levelFilledP50: Array(10).fill(100), levelFilledP90: Array(10).fill(100), tradesPerMin: q, tradeSize: q, takerYesShare: 0.5 }],
  flow: [],
};

test('a quote that moves down walks through the bids in its way, each taken by NO takers, before the next anchor', () => {
  const sim = new DepthSim(model);
  const t = 1_000_000 * MIN;
  const ev = sim.play('T', t, 0.5, 0.52, t + MIN, t + 30 * MIN, 0.47);
  const trades = ev.filter((e) => e.k === 'trade');
  // From bid 50c / ask 52c to a mid of 47c (bid ~46c): the bids at 50, 49, 48 and 47c go, each in full.
  assert.deepEqual(trades.map((e) => Math.round((e.price as number) * 100)), [50, 49, 48, 47]);
  assert.ok(trades.every((e) => e.takerSide === 'no' && (e.count as number) === 100 && e.t > t && e.t < t + MIN));
  // A flat next quote walks nowhere.
  const flat = new DepthSim(model).play('U', t, 0.5, 0.52, t + MIN, t + 30 * MIN, 0.51);
  assert.equal(flat.filter((e) => e.k === 'trade').length, 0);
});
