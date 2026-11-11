import assert from 'node:assert/strict';
import { test } from 'node:test';
import { COLS, EXITS, NZ, type Grid, type Candidate, type Prim } from '../research/perpTaSweep';
import { NONE } from '../research/perpTaModules';
import { decayCoin, decayReport, topGroups, bootIdx, est, DECAY, type RoundIn } from '../research/perpTaDecay';

const MPD = 1440;

test('perp TA decay: the top groups are the report\'s (non-forecast, by discovery excess t)', () => {
  const c = (a: string, t: number, diagnostic = false) => ({ a, rule: `r${t}`, mode: 'follow', pol: 'T15', side: 'long', cond: 'all', disc: { n: 100, mean: 0, tExc: t }, diagnostic }) as unknown as Candidate;
  const top = topGroups([c('BTC', 1), c('ETH', 5, true), c('SOL', 3), c('XRP', 4)], 2);
  assert.deepEqual(top.map((x) => x.a), ['XRP', 'SOL']);
});

test('perp TA decay: bootstrap SE and the paired difference', () => {
  const days = 200, boots = bootIdx(days, 500, 5, 3);
  const den = new Array(days).fill(10), num = Array.from({ length: days }, (_, j) => 10 * (j % 2 ? 2 : 0));
  const e = est(num, den, boots);
  assert.equal(e.mean, 1); assert.ok(e.se > 0 && e.se < 0.2, String(e.se)); assert.equal(e.n, 2000);
  const same = est(num, den, boots, { num, den });
  assert.equal(same.mean, 0); assert.equal(same.se, 0);
});

test('perp TA decay: a planted 3-minute edge shows at d = 0, is gone by d = 15, and its placebo is flat', () => {
  // Jul 2023 .. Jun 2025 (discovery from the grid start, validation 2024-01-01 .. 2025-06-30), a noisy flat market. Every
  // 180 minutes on average a signal fires at a random minute (a fixed time of day would survive whole-day shifts); the
  // next 3 minutes rise 6 bps each (18 bps), then nothing.
  const t0 = Date.UTC(2023, 6, 1), n = (DECAY.seal - t0) / 60_000;
  const c = Object.fromEntries(COLS.map((k) => [k, new Float32Array(n)])) as Grid['c'];
  let seed = 9, x = Math.log(100);
  const rnd = () => ((seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0) / 4294967296);
  const s = new Int8Array(n);
  let last = -1000;
  for (let i = 0; i < n; i++) {
    const prev = Math.exp(x), sig = rnd() < 1 / 180 && i - last > 30;
    if (sig) { s[i] = 1; last = i; }
    const k = i - last;
    x += (k >= 1 && k <= 3 ? 6e-4 : 0) + 4e-4 * (rnd() - 0.5);
    const p = Math.exp(x);
    for (const [o, h, l, cl] of [['so', 'sh', 'sl', 'sc'], ['po', 'ph', 'pl', 'pc']] as const) { c[o][i] = prev; c[cl][i] = p; c[h][i] = Math.max(p, prev) * 1.0001; c[l][i] = Math.min(p, prev) * 0.9999; }
    c.valid[i] = 1; c.sv[i] = 1;
  }
  const g: Grid = { asset: 'BTC', t0, n, c, fundRaw: new Float32Array(n) };
  const prims: Prim[] = [{ id: 'sig', fam: 'sig', m: 1, s }];
  const cond = new Uint8Array(n * NZ).fill(NONE);
  const T15 = EXITS.find((p) => p.id === 'T15')!;
  const cand = { a: 'BTC', rule: 'sig', mode: 'follow', pol: 'T15', side: 'long', cond: 'all', disc: { n: 0, mean: 0, tExc: 9 }, diagnostic: false, policyDef: T15, val: { n: 0, mean: 0, exc: 0 } } as unknown as Candidate;
  const round = (): RoundIn => ({ round: 1, run: 'test', cands: [cand], header: { costs: { takerBps: 12, makerBps: 5, halfSpreadBps: 2, ttBps: 1 }, policies: EXITS, seal: '2025-07-01T00:00:00.000Z', validFrom: '2024-01-01T00:00:00.000Z' } });
  const first = decayCoin(g, [round()], { prims, cond, log: () => undefined });
  assert.equal(first.cells.length, 1); assert.equal(first.cells[0].replicated, false);
  cand.disc.n = first.cells[0].discReplicated.n; cand.disc.mean = first.cells[0].discReplicated.mean;
  const co = decayCoin(g, [round()], { prims, cond, log: () => undefined });
  const cell = co.cells[0];
  assert.equal(cell.replicated, true); assert.equal(co.days, 547); assert.equal(cell.shifts, DECAY.shifts);
  const m = (a: { n: number[]; exc: number[] }) => a.exc.reduce((p, q) => p + q, 0) / a.n.reduce((p, q) => p + q, 0);
  const e0 = m(cell.arm[0]), e15 = m(cell.arm[DECAY.delays.indexOf(15)]), p0 = m(cell.placebo[0]);
  assert.ok(e0 > 14 && e0 < 22, `d=0 excess ${e0}`);
  assert.ok(Math.abs(e15) < 3, `d=15 excess ${e15}`);
  assert.ok(Math.abs(p0) < 3, `placebo excess ${p0}`);
  assert.ok(cell.arm[0].n.reduce((p, q) => p + q, 0) > 3000, 'about 7 signals a day for 547 days');
  const rep = decayReport([co]);
  assert.equal(rep.rounds.length, 1);
  const r = rep.rounds[0];
  assert.equal(r.P0, true); assert.ok(r.drop15.mean > 10);
  assert.match(r.verdict, /SUPPORTED|FALSIFIED/);
  assert.match(rep.md, /Round 1/);
});
