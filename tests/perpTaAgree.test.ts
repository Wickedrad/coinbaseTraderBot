import assert from 'node:assert/strict';
import { test } from 'node:test';
import { COLS, type Grid, type Prim } from '../research/perpTaSweep';
import { subGrid, withSpot, agreeOne, isTaker } from '../research/perpTaAgree';

const T0 = Date.UTC(2024, 0, 1), MIN = 60_000;
function grid(n: number): Grid {
  const c = Object.fromEntries(COLS.map((k) => [k, new Float32Array(n)])) as Grid['c'];
  for (let i = 0; i < n; i++) { for (const k of ['so', 'sh', 'sl', 'sc', 'po', 'ph', 'pl', 'pc'] as const) c[k][i] = 100 + i; c.sv[i] = 1; c.stb[i] = 0.5; c.valid[i] = 1; }
  return { asset: 'TEST', t0: T0, n, c, fundRaw: new Float32Array(n) };
}

test('perp TA agree: a sub-grid keeps the minutes; Coinbase candles replace spot, a no-trade minute is flat, a long hole is invalid', () => {
  const g = grid(3000), s = subGrid(g, T0 + 1440 * MIN, T0 + 2880 * MIN);
  assert.deepEqual([s.t0, s.n, s.c.sc[0], s.c.pc[1439]], [T0 + 1440 * MIN, 1440, 1540, 2979]);
  const cs = [];
  for (let i = 0; i < 1440; i++) if (i !== 10 && !(i >= 100 && i < 200)) cs.push({ ts: s.t0 + i * MIN, o: 1, h: 2, l: 0.5, c: 1.5, v: 3 });
  const w = withSpot(s, cs, 60);
  assert.deepEqual([w.matched, w.flat, w.holes], [1339, 61, 40]);
  assert.deepEqual([w.g.c.sc[10], w.g.c.sv[10], w.g.c.valid[10]], [1.5, 0, 1], 'a minute without a trade: flat at the last close');
  assert.equal(w.g.c.valid[160], 0, 'more than an hour without a candle: not valid');
  assert.ok(Number.isNaN(w.g.c.stb[0]), 'no taker-buy split on Coinbase candles');
  assert.equal(w.g.c.pc[5], s.c.pc[5], 'perp columns untouched');
  assert.equal(s.c.sc[10], 1550, 'the Binance grid is not changed');
  assert.ok(isTaker('tflow3@1m') && !isTaker('engulf@15m'));
});

test('perp TA agree: trigger recall / precision within one bar, same direction; state agreement where either reads nonzero', () => {
  const n = 600, valid = new Float32Array(n).fill(1);
  const mk = (on: Array<[number, number]>): Prim => { const s = new Int8Array(n / 5); for (const [k, v] of on) s[k] = v; return { id: 'x@5m', fam: 'x', m: 5, s }; };
  const a = mk([[10, 1], [30, -1], [60, 1]]);
  const b = mk([[11, 1], [30, 1], [90, -1]]); // one bar late (match), wrong side (no), and an extra one
  const r = agreeOne(a, b, valid, valid, n, 0, n);
  assert.deepEqual([r.nB, r.nC], [3, 3]);
  assert.equal(r.recall, +(1 / 3).toFixed(4));
  assert.equal(r.precision, +(1 / 3).toFixed(4));
  assert.equal(r.state, 0, 'no bar reads the same nonzero value on both');
  const same = agreeOne(a, a, valid, valid, n, 0, n);
  assert.deepEqual([same.recall, same.precision, same.state], [1, 1, 1]);
  // Only triggers inside the window count.
  const win = agreeOne(a, b, valid, valid, n, 0, 100);
  assert.deepEqual([win.nB, win.nC, win.recall], [1, 1, 1]);
});
