import assert from 'node:assert/strict';
import { test } from 'node:test';
import { cryptoValues, l0Width, popSpec } from '../bot/snn/inputs';
import { GapTape } from '../research/gapTape';

test('lead inputs widen crypto L0 only when asked', () => {
  const base = l0Width('crypto');
  assert.equal(l0Width('crypto', 'G'), base + 8);
  assert.equal(l0Width('crypto', 'P'), base + 16);
  assert.equal(l0Width('tennis', 'G'), l0Width('tennis'));
  assert.deepEqual(popSpec('crypto', 'G').slice(-1).map((x) => x.name), ['fv_gap_c']);
  const v = cryptoValues(15, { perp_premium_coin_bps: 3, perp_ret_diff_1m_z: -1 }, { fvGap: 2.5 });
  assert.equal(v.fv_gap_c, 2.5);
  assert.equal(v.perp_premium_coin_bps, 3);
  assert.equal(v.perp_ret_diff_1m_z, -1);
});

test('gap tape feeds the gap from shiftMs earlier and survives serialization', () => {
  const t = new GapTape(120_000);
  assert.equal(t.feed('BTC-15m', 0, 1), undefined);
  assert.equal(t.feed('BTC-15m', 60_000, 2), undefined);
  assert.equal(t.feed('BTC-15m', 120_000, 3), 1);
  const u = GapTape.from(JSON.parse(JSON.stringify(t.toJSON())), 120_000);
  assert.equal(u.feed('BTC-15m', 180_000, 4), 2);
  assert.equal(GapTape.from(t.toJSON(), 60_000).feed('BTC-15m', 180_000, 4), undefined); // other shift: start over
  assert.equal(new GapTape(0).feed('BTC-15m', 0, 7), 7);
  u.prune(120_000 + 86_400_000 + 120_000 + 60_000);
  assert.equal(u.feed('BTC-15m', 240_000, 5), undefined);
});
