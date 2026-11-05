import { test } from 'node:test';
import assert from 'node:assert/strict';
import { applyTaVeto, taVetoReasons, type TaVetoConfig } from '../bot/model/taVeto';

const off: TaVetoConfig = { ofi: NaN, conf: NaN, intensity: NaN, min: 1 };
const order = (side: 'bid' | 'ask', purpose = 'entry', why = 'take', reduceOnly = false) => ({ side, price: 0.4, reduceOnly, purpose, why });

test('TA veto: off unless a threshold is set', () => {
  const plan = { place: [order('bid')], notes: [] as string[] };
  assert.equal(applyTaVeto(plan, off, { ofi_30s: 5 }), 0);
  assert.equal(plan.place.length, 1);
});

test('TA veto: order flow for the bought side skips it, against it keeps it; exits always pass', () => {
  const c = { ...off, ofi: 0 };
  assert.deepEqual(taVetoReasons(c, 'yes', { ofi_30s: 0.3 }).length, 1);
  assert.deepEqual(taVetoReasons(c, 'no', { ofi_30s: 0.3 }).length, 0);
  const plan = { place: [order('bid'), order('ask'), order('ask', 'exit', 'x', true), order('bid', 'quote', 'requote')], notes: [] as string[] };
  assert.equal(applyTaVeto(plan, c, { ofi_30s: 0.3 }), 1);
  assert.deepEqual(plan.place.map((o) => o.side + o.purpose), ['askentry', 'askexit', 'bidquote']);
});

test('TA veto: min needs that many signals; reverse flips them; intensity is unsided', () => {
  const c = { ...off, ofi: 0, conf: 0, intensity: 10, min: 2 };
  assert.equal(taVetoReasons(c, 'yes', { ofi_30s: 1, conf_count: -1, trade_intensity_60s: 9 }).length, 1);
  assert.equal(taVetoReasons(c, 'yes', { ofi_30s: 1, conf_count: 2, trade_intensity_60s: 9 }).length, 2);
  assert.equal(taVetoReasons({ ...c, reverse: true }, 'yes', { ofi_30s: -1, conf_count: -2, trade_intensity_60s: 9 }).length, 3);
});

test('TA veto: random control skips about its share', () => {
  let kept = 0;
  for (let i = 0; i < 2000; i++) { const plan = { place: [order('bid')], notes: [] as string[] }; applyTaVeto(plan, { ...off, random: 0.3 }, {}); kept += plan.place.length; }
  assert.ok(kept > 1300 && kept < 1500, `kept ${kept}`);
});
