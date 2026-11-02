import { test } from 'node:test';
import assert from 'node:assert/strict';
import { snnPrice, VolRef, DEFAULT_SNN_PRICE } from '../bot/snn/priceAdjust';

test('snnPrice pulls toward the mid, blends at alpha, gates kinds and zero-k regimes', () => {
  const c = DEFAULT_SNN_PRICE;
  const r = snnPrice(0.5, 0.7, 0.5, 1, 'between', c); // normal: adj = 0.5 + 0.25*0.2 = 0.55; p = 0.75*0.5 + 0.25*0.55
  assert.ok(Math.abs(r.p - 0.5125) < 1e-9);
  assert.equal(snnPrice(0.5, 0.7, 0.5, 1, 'greater', c).p, 0.5);
  assert.equal(snnPrice(0.5, 0.7, 0.5, 2, 'between', { ...c, kHigh: 0 }).p, 0.5);
  assert.equal(snnPrice(0.5, undefined, 0.5, 1, 'between', c).p, 0.5);
});

test('VolRef is time-based', () => {
  const v = new VolRef();
  assert.equal(v.ratio('BTC', 1, 0), 1);
  assert.ok(v.ratio('BTC', 2, 1000) > 1.99); // one second later the one-day reference has barely moved
  assert.ok(v.ratio('BTC', 2, 1000 + 86_400_000 * 5) < 1.05);
});

test('vetoOnly keeps only moves toward the mid', () => {
  const c = { ...DEFAULT_SNN_PRICE, vetoOnly: true };
  assert.equal(snnPrice(0.6, 0.9, 0.5, 1, 'between', c).p, 0.6); // pushes away from mid: dropped
  assert.ok(snnPrice(0.6, 0.3, 0.5, 1, 'between', c).p < 0.6); // pulls toward mid: kept
});
