import { test } from 'node:test';
import assert from 'node:assert/strict';
import { QuoteLagHold } from '../bot/strategy/quoteLagHold';
import type { StrategyOutput } from '../bot/strategy/fairValueStrategy';

const cfg = { theta: 0.1, windowSec: 10, maxSec: 60 };
const order = (side: 'bid' | 'ask', price: number, extra: Record<string, unknown> = {}) =>
  ({ side, price, count: 5, timeInForce: 'immediate_or_cancel', postOnly: false, reduceOnly: false, purpose: 'entry', ...extra }) as unknown as StrategyOutput['place'][number];
const plan = (...p: StrategyOutput['place']): StrategyOutput => ({ place: p, cancel: [], notes: [] });

function jumpUp(h: QuoteLagHold, t0: number) {
  for (let s = 0; s <= 10; s++) h.record('T', t0 + s * 1000, s < 10 ? 0.5 : 0.65, 0.5); // fair +15c, mid flat
}

test('holds the side the gap is against, keeps the favoured side and reductions', () => {
  const h = new QuoteLagHold(cfg);
  jumpUp(h, 0);
  assert.equal(h.against('T', 10_000), 'no');
  const p = plan(order('ask', 0.5), order('bid', 0.51), order('ask', 0.5, { reduceOnly: true }));
  assert.equal(h.apply(p, 'T', 10_000, 0), 1);
  assert.deepEqual(p.place.map((x) => x.side), ['bid', 'ask']);
  const r = plan(order('ask', 0.5));
  assert.equal(h.apply(r, 'T', 10_000, 10), 0); // selling YES we hold reduces the position
});

test('no hold without a gap, when the quote followed, or past the cap', () => {
  const h = new QuoteLagHold(cfg);
  for (let s = 0; s <= 10; s++) h.record('T', s * 1000, s < 10 ? 0.5 : 0.65, s < 10 ? 0.5 : 0.64);
  assert.equal(h.against('T', 10_000), undefined);
  const g = new QuoteLagHold(cfg);
  jumpUp(g, 0);
  assert.equal(g.apply(plan(order('ask', 0.5)), 'T', 10_000, 0), 1);
  for (let s = 11; s <= 71; s++) g.record('T', s * 1000, 0.65 + (s - 10) * 0.003, 0.5); // gap keeps open
  assert.equal(g.apply(plan(order('ask', 0.5)), 'T', 71_000, 0), 0); // 61 s since the hold began
});

test('no sample about a window ago -> no hold', () => {
  const h = new QuoteLagHold(cfg);
  h.record('T', 0, 0.5, 0.5); h.record('T', 30_000, 0.7, 0.5);
  assert.equal(h.against('T', 30_000), undefined);
});
