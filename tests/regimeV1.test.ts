import { test } from 'node:test';
import assert from 'node:assert/strict';
import { RegimeV1, percentileSorted, rv60 } from '../bot/model/regimeV1.ts';

const MIN = 60_000, DAY = 86_400_000;

test('percentile matches numpy linear interpolation', () => {
  assert.equal(percentileSorted([1, 2, 3, 4], 50), 2.5);
  assert.ok(Math.abs(percentileSorted([0, 10], 100 / 3) - 10 / 3) < 1e-12);
});

test('rv60 needs 50 returns and uses only closes before t', () => {
  const c = new Map<number, number>();
  for (let k = 0; k <= 61; k++) c.set(k * MIN, 100 * Math.exp(0.001 * (k % 2)));
  const v = rv60(c, 61 * MIN);
  assert.ok(Math.abs(v - Math.sqrt(60) * 0.001) < 1e-9);
  c.set(61 * MIN, 1e9); // the close of minute t itself must not matter
  assert.equal(rv60(c, 61 * MIN), v);
  const sparse = new Map([[0, 100], [MIN, 101]]);
  assert.ok(Number.isNaN(rv60(sparse, 2 * MIN)));
});

test('tercile is NA before 7 days, then HIGH in a vol burst', () => {
  const r = new RegimeV1();
  let p = 100, seed = 1;
  const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647) - 0.5;
  const end = 9 * DAY;
  for (let t = 0; t < end; t += MIN) {
    const burst = t > end - 3 * 3600_000 ? 10 : 1;
    p *= Math.exp(0.001 * burst * rnd());
    r.feedClose('BTC', t, p);
    if (t === 6 * DAY) assert.equal(r.label('BTC', t + MIN).tercile, 'NA');
  }
  const l = r.label('BTC', end);
  assert.equal(l.tercile, 'HIGH');
  assert.ok(l.q33 < l.q67);
});
