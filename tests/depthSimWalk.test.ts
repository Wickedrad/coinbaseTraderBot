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
  // From bid 50c / ask 52c to a mid of 47c (bid ~46c): the bids at 50, 49, 48 and 47c go, each in full, in trade-sized
  // prints (at most 25 a level, the last taking the rest).
  const prices = trades.map((e) => Math.round((e.price as number) * 100));
  assert.deepEqual([...new Set(prices)], [50, 49, 48, 47]);
  for (const c of [50, 49, 48, 47]) assert.equal(trades.filter((e) => Math.round((e.price as number) * 100) === c).reduce((a, e) => a + (e.count as number), 0), 100);
  assert.ok(trades.length > 4 && trades.length <= 100);
  assert.ok(trades.every((e) => e.takerSide === 'no' && e.t > t && e.t < t + MIN));
  // A flat next quote walks nowhere.
  const flat = new DepthSim(model).play('U', t, 0.5, 0.52, t + MIN, t + 30 * MIN, 0.51);
  assert.equal(flat.filter((e) => e.k === 'trade').length, 0);
});

test('informed flow: with every measured trade on the side the price went, the trades before a fall are NO takers', () => {
  const busy: DepthModel = { ...model, shape: [{ ...model.shape[0], tradesPerMin: { n: 1, mean: 60, p10: 60, p50: 60, p90: 60 } }], informed: { n: 5000, agree: 1 } };
  const t = 1_000_000 * MIN;
  const ev = new DepthSim(busy).play('V', t, 0.5, 0.52, t + MIN, t + 30 * MIN, 0.5);
  const trades = ev.filter((e) => e.k === 'trade');
  assert.ok(trades.length > 20);
  assert.ok(trades.every((e) => e.takerSide === 'no'));
});

test('sizes go back to the measured shape and the best price flickers at the measured rate', () => {
  const t = 1_000_000 * MIN;
  // Adds far outpacing cancels at the top used to drift the queue up to the cap; the pull keeps it near its draw.
  const flow = [0, 1, 2, 3, 4, 5].map((qi) => ({ offset: 0, qi, seconds: 1000, addPerSec: 2, cancelPerSec: 0.1, addSize: { n: 1, mean: 50, p10: 50, p50: 50, p90: 50 }, cancelSize: q }));
  const busy: DepthModel = { ...model, shape: [{ ...model.shape[0], topChangesPerMin: { n: 1, mean: 300, p10: 300, p50: 300, p90: 300 } }], flow };
  const sim = new DepthSim(busy);
  const ev = sim.play('W', t, 0.5, 0.52, t + 15_000, t + 30 * MIN, 0.51);
  const top = new Map<number, number>();
  for (const e of ev) if (e.k === 'book') for (const l of e.bids as Array<{ price: number; size: number }>) top.set(Math.round(l.price * 1000), l.size);
  else if (e.k === 'delta' && e.side === 'bid') { const p = Math.round((e.price as number) * 1000); top.set(p, (top.get(p) ?? 0) + (e.delta as number)); }
  assert.ok((top.get(500) ?? 0) < 400, `top bid ${top.get(500)}`);
  // ~(300/60 - 0.9)/2 = 2 flickers a second over 15 s.
  assert.ok(sim.stats.flickers >= 15 && sim.stats.flickers <= 50, `flickers ${sim.stats.flickers}`);
});
