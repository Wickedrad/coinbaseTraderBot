import assert from 'node:assert/strict';
import { test } from 'node:test';
import fs from 'fs';
import os from 'os';
import path from 'path';
import { COLS, outcomes, fundingCum, pool, readJsonlGz, writeJsonlGz, POLICIES, POLICIES_R2, EXITS, type Grid, type Policy, type Costs } from '../research/perpTaSweep';

// A flat perp at 100 for n minutes; tests then move single bars.
function flat(n: number): Grid {
  const c = Object.fromEntries(COLS.map((k) => [k, new Float32Array(n)])) as Grid['c'];
  for (const k of ['so', 'sh', 'sl', 'sc', 'po', 'ph', 'pl', 'pc'] as const) c[k].fill(100);
  c.valid.fill(1);
  return { asset: 'TEST', t0: Date.UTC(2021, 0, 1), n, c, fundRaw: new Float32Array(n) };
}
const COSTS: Costs = { takerBps: 12, makerBps: 5, halfSpreadBps: 2, ttBps: 1 };
const unit = (n: number) => new Float32Array(n).fill(0.01); // 1% ATR
const near = (a: number, b: number, tol = 0.01) => assert.ok(Math.abs(a - b) <= tol, `${a} vs ${b}`);
const peg = (over: Partial<Policy> = {}): Policy => ({ id: 'MP5:x', sl: 1, tp: 1, max: 5, entry: { kind: 'peg', w: 5 }, ...over });

test('perp TA round 2: a pegged maker entry fills only when the perp trades through the touch, at the touch, paying maker', () => {
  const g = flat(30);
  g.c.pl[2] = 99.95; // the bid after minute 1 is 100 x (1 - 2 bps) = 99.98; 99.95 is through it by more than 1 bp
  const o = outcomes(g, 30, unit(30), COSTS, [peg()]);
  // Long decided at the end of minute 0: fills in minute 2 at 99.98, stop 98.98 not reached, target 100.98 never;
  // time exit at the close of minute 2 + 5 - 1 = 6 (taker: 12 + 2).
  near(o.net[0][0], (100 / 99.98 - 1) * 1e4 - 5 - 14);
  assert.equal(o.exit[0][0], 6);
  assert.equal(o.hold[0][0], 5);
  // A bare touch (less than 1 bp through) does not fill: minute 1's low 99.975 vs 99.98 x 0.9999 = 99.970.
  const t = flat(30); t.c.pl[1] = 99.975;
  const ot = outcomes(t, 30, unit(30), COSTS, [peg()]);
  assert.ok(Number.isNaN(ot.net[0][0]));
  assert.equal(ot.exit[0][0], 5, 'unfilled: the order rests until the end of minute i + w');
  assert.deepEqual(ot.fills[0].tried > 0 && ot.fills[0].filled === 0, true);
  // Short mirror: the ask 100.02, filled when the high trades through it.
  const s = flat(30); s.c.ph[2] = 100.05;
  const os_ = outcomes(s, 30, unit(30), COSTS, [peg()]);
  near(os_.net[1][0], -(100 / 100.02 - 1) * 1e4 - 5 - 14);
});

test('perp TA round 2: in the fill minute only the stop counts; a limit entry rests off the decision close', () => {
  const g = flat(30);
  g.c.pl[2] = 98; // fills at 99.98 and reaches the stop 98.98 in the same minute: stopped (taker)
  const o = outcomes(g, 30, unit(30), COSTS, [peg()]);
  near(o.net[0][0], (99.98 * 0.99 / 99.98 - 1) * 1e4 - 5 - 14);
  assert.deepEqual([o.exit[0][0], o.hold[0][0]], [2, 1]);
  // A resting limit filled in a minute that opened through the stop exits at that open, as a stop does on a gap later on.
  const gp = flat(200); gp.c.pc[1] = 99.8; gp.c.po[2] = 97; gp.c.pl[2] = 96.9; gp.c.ph[2] = 97; gp.c.pc[2] = 97;
  const og1 = outcomes(gp, 200, unit(200), COSTS, [{ id: 'ML15:S1T1', sl: 1, tp: 1, max: 120, entry: { kind: 'limit', w: 15, off: 0.25 } }]);
  near(og1.net[0][0], (97 / 99.75 - 1) * 1e4 - 5 - 14);
  assert.deepEqual([og1.exit[0][0], og1.hold[0][0]], [2, 1]);
  // A target touched in the fill minute is not credited: the trade runs on to its time exit.
  const t = flat(30); t.c.pl[2] = 99.95; t.c.ph[2] = 102;
  const ot = outcomes(t, 30, unit(30), COSTS, [peg()]);
  assert.equal(ot.exit[0][0], 6);
  // Limit 0.25 ATR below the decision close: 99.75, filled at 99.75 when the low reaches 99.75 x 0.9999.
  const l = flat(30); l.c.pl[2] = 99.95; l.c.pl[3] = 99.7;
  const lim: Policy = { id: 'ML15:x', sl: 1, tp: 0, max: 5, entry: { kind: 'limit', w: 15, off: 0.25 } };
  const ol = outcomes(l, 30, unit(30), COSTS, [lim]);
  near(ol.net[0][0], (100 / 99.75 - 1) * 1e4 - 5 - 14);
  assert.deepEqual([ol.exit[0][0], ol.hold[0][0]], [7, 5]);
  // A missing minute inside the window: no trade, and no order counted.
  const gap = flat(30); gap.c.valid[3] = 0;
  const og = outcomes(gap, 30, unit(30), COSTS, [peg()]);
  assert.ok(Number.isNaN(og.net[0][0]));
  assert.equal(og.exit[0][0], -1);
});

test('perp TA round 2: funding offset and stress apply at funding instants only; round 1 taker entries unchanged', () => {
  const g = flat(30);
  g.c.fund[3] = 1e-12; // an instant with a zero modelled rate
  g.c.fund[10] = 0.0001;
  const cum = fundingCum(g, 30, { ...COSTS, fundOffsetBps: 1.5, fundMult: 2 });
  near(cum[4] - cum[3], 0.0003, 1e-9);
  near(cum[11] - cum[10], (0.0001 + 0.00015) * 2, 1e-9);
  near(cum[30] - cum[11], 0, 1e-12);
  g.c.pl[2] = 99.95;
  const o = outcomes(g, 30, unit(30), { ...COSTS, fundOffsetBps: 1.5, fundMult: 2 }, [peg()]);
  // Long held through the end of minute 3 (filled in 2, out at the close of 6): pays 3 bps.
  near(o.net[0][0], (100 / 99.98 - 1) * 1e4 - 5 - 14 - 3);
  near((o.cum[o.exit[0][0]] - o.cum[o.exit[0][0] - o.hold[0][0] + 1]) * 1e4, 3, 1e-6);
  // Round 1: taker at the next open, half-spread both sides.
  const t = outcomes(flat(30), 30, unit(30), COSTS, [EXITS[0]]);
  near(t.net[0][0], -28);
  assert.deepEqual([t.exit[0][0], t.hold[0][0]], [5, 5]);
  assert.equal(POLICIES, POLICIES_R2);
  assert.equal(POLICIES.length, 36);
  assert.ok(POLICIES.every((p) => p.entry && /^(MP5|MP15|ML15):/.test(p.id)));
});

test('perp TA: pooled folds carry funding; round 1 records (8 fields) pool to zero funding', () => {
  const p = pool([[2, 10, 60, 1, 10, 4, 20, 50, 3, 5], [1, -2, 4, 0, 5, -1, 1, 25]], 0, 2);
  assert.equal(p.n, 3);
  near(p.mean, 8 / 3);
  near(p.fund, 1);
  near(p.fundAbs, 5 / 3);
});

test('perp TA: gzip lines are written in members and read back without one big string', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'perpta-'));
  const file = path.join(dir, 'x.jsonl.gz');
  const lines = Array.from({ length: 45_001 }, (_, k) => JSON.stringify({ k }));
  writeJsonlGz(file, lines);
  const back = readJsonlGz(file);
  assert.equal(back.length, lines.length);
  assert.equal(back[45_000], lines[45_000]);
  fs.rmSync(dir, { recursive: true, force: true });
});
