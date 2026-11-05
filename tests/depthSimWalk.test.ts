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

test('a quote that moves down takes the bids it moved through at its own time, with NO takers, and nothing before it', () => {
  const sim = new DepthSim(model);
  const t = 1_000_000 * MIN;
  const first = sim.play('T', t, 0.5, 0.52, t + 15_000, t + 30 * MIN, 0.47);
  // No trades ahead of the move: the next quote is not known to the book before its time.
  assert.equal(first.filter((e) => e.k === 'trade').length, 0);
  const ev = sim.play('T', t + 15_000, 0.47, 0.49, t + 30_000, t + 30 * MIN);
  const trades = ev.filter((e) => e.k === 'trade');
  // From bid 50c to 47c: the bids at 50, 49 and 48c go, each with a few trade-sized prints (at most 3), the rest pulled,
  // all at the new quote's time and before its book.
  const prices = trades.map((e) => Math.round((e.price as number) * 100));
  assert.deepEqual([...new Set(prices)], [50, 49, 48]);
  assert.ok(trades.length >= 3 && trades.length <= 9);
  assert.ok(trades.every((e) => e.takerSide === 'no' && e.t === t + 15_000));
  assert.ok(ev.findIndex((e) => e.k === 'book') > ev.findIndex((e) => e.k === 'trade'));
  // A flat quote takes nothing.
  const flat = new DepthSim(model);
  flat.play('U', t, 0.5, 0.52, t + 15_000, t + 30 * MIN);
  assert.equal(flat.play('U', t + 15_000, 0.5, 0.52, t + 30_000, t + 30 * MIN).filter((e) => e.k === 'trade').length, 0);
});

test('the trades before a quote do not know where the next quote goes', () => {
  const busy: DepthModel = { ...model, shape: [{ ...model.shape[0], tradesPerMin: { n: 1, mean: 60, p10: 60, p50: 60, p90: 60 } }], informed: { n: 5000, agree: 1 } };
  const t = 1_000_000 * MIN;
  const down = new DepthSim(busy).play('V', t, 0.5, 0.52, t + MIN, t + 30 * MIN, 0.3);
  const up = new DepthSim(busy).play('V', t, 0.5, 0.52, t + MIN, t + 30 * MIN, 0.7);
  assert.deepEqual(down, up);
  assert.ok(down.filter((e) => e.k === 'trade').length > 20);
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

test('the trade rate follows the history\'s minute volume before the quote (nothing ahead of time)', () => {
  const busy: DepthModel = { ...model, shape: [{ ...model.shape[0], tradesPerMin: { n: 1, mean: 60, p10: 60, p50: 60, p90: 60 }, tradeSize: { n: 1, mean: 2, p10: 2, p50: 2, p90: 2 } }] };
  const t = 1_000_000 * MIN;
  const n = (vol?: number) => new DepthSim(busy).play('W', t, 0.5, 0.52, t + 5 * MIN, t + 30 * MIN, undefined, vol).filter((e) => e.k === 'trade').length;
  // The cell expects 60 trades x 2 contracts = 120 contracts a minute.
  const quiet = n(0), usual = n(120), hot = n(600);
  assert.ok(quiet < usual / 3, `quiet ${quiet} vs usual ${usual}`);
  assert.ok(hot > usual * 2.5, `hot ${hot} vs usual ${usual}`);
  assert.ok(Math.abs(usual - 300) < 60, `usual ${usual} ~ 60 a minute for 5 minutes`);
});
