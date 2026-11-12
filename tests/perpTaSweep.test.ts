import './tmpScope'; // one temp folder per run, removed at exit
import assert from 'node:assert/strict';
import { test } from 'node:test';
import fs from 'fs';
import os from 'os';
import path from 'path';
import { COLS, outcomes, fundingCum, pool, readJsonlGz, writeJsonlGz, atrUnit, POLICIES, POLICIES_R2, POLICIES_R3, POLICIES_ALL, EXITS, type Grid, type Policy, type Costs } from '../research/perpTaSweep';

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
  assert.equal(POLICIES_R2.length, 36);
  assert.ok(POLICIES_R2.every((p) => p.entry && /^(MP5|MP15|ML15):/.test(p.id)));
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

// A seeded random walk (perp = spot) with a few missing minutes, for the scan tests.
function walk(n: number, seed: number, vol = 0.0015): Grid {
  const g = flat(n);
  let x = seed >>> 0, p = 100;
  const rnd = () => { x = (x * 1664525 + 1013904223) >>> 0; return x / 2 ** 32; };
  for (let i = 0; i < n; i++) {
    const o = p, c = o * Math.exp((rnd() - 0.5) * 2 * vol), h = Math.max(o, c) * (1 + rnd() * vol), l = Math.min(o, c) * (1 - rnd() * vol);
    for (const [k, v] of [['so', o], ['sh', h], ['sl', l], ['sc', c], ['po', o], ['ph', h], ['pl', l], ['pc', c]] as const) g.c[k][i] = v;
    p = c;
  }
  for (const i of [7000, 7001, 23456]) g.c.valid[i] = 0;
  for (let i = 0; i < n; i += 480) g.c.fund[i] = (rnd() - 0.4) * 2e-4;
  return g;
}

test('perp TA round 3: the block-skipping exit scan gives exactly the minute-by-minute results', () => {
  const n = 40_000, g = walk(n, 7), u = atrUnit(g, n);
  const pols = [...POLICIES_R3.filter((_, k) => k % 3 === 0 || k < 12), ...POLICIES_R2.filter((_, k) => k % 7 === 0)];
  const a = outcomes(g, n, u, COSTS, pols), b = outcomes(g, n, u, COSTS, pols, { noSkip: true });
  let trades = 0;
  for (let k = 0; k < a.net.length; k++) {
    for (let i = 0; i < n; i++) {
      const x = a.net[k][i], y = b.net[k][i];
      if (x !== x || y !== y) assert.ok(x !== x && y !== y, `policy ${k} minute ${i}: ${x} vs ${y}`);
      else { assert.equal(x, y); trades++; }
      if (a.exit[k][i] !== b.exit[k][i] || a.hold[k][i] !== b.hold[k][i]) assert.fail(`policy ${k} minute ${i}: exit ${a.exit[k][i]} vs ${b.exit[k][i]}`);
    }
    assert.deepEqual(a.fills[k], b.fills[k]);
  }
  assert.ok(trades > 100_000, `${trades} trades compared`);
});

test('perp TA round 3: exits sized in 1h / 4h ATRs; ML60 rests 0.25 x the 1-hour ATR off', () => {
  assert.equal(POLICIES, POLICIES_R3);
  assert.equal(POLICIES.length, 36);
  assert.ok(POLICIES.every((p) => p.entry && (p.tf === 60 || p.tf === 240) && !p.trail && /^(MP15|ML15|ML60):[HD]/.test(p.id)));
  assert.equal(new Set(POLICIES_ALL.map((p) => p.id)).size, POLICIES_ALL.length, 'policy ids are unique across rounds');
  const n = 20_000, g = walk(n, 11), u15 = atrUnit(g, n), u60 = atrUnit(g, n, 60), u240 = atrUnit(g, n, 240);
  assert.ok(u60[5000] > u15[5000] && u240[5000] > u60[5000], 'longer bars, wider ATR');
  // A tf-60 policy is the same policy run on the 1-hour ATR; ML60's offset reads the 1-hour ATR too.
  const h = POLICIES_R3.find((p) => p.id === 'ML60:HS1T2')!;
  const x = outcomes(g, n, u15, COSTS, [h]);
  const y = outcomes(g, n, u60, COSTS, [{ ...h, tf: undefined, entry: { ...h.entry!, tf: undefined } }]);
  for (let i = 0; i < n; i++) if (!(Number.isNaN(x.net[0][i]) && Number.isNaN(y.net[0][i]))) assert.equal(x.net[0][i], y.net[0][i]);
  // ML15 with a 1-hour exit: the offset stays in 15-minute ATRs (entry tf absent = 15), not the exit's.
  const m = POLICIES_R3.find((p) => p.id === 'ML15:HS1T2')!;
  const same = (a: Float32Array, b: Float32Array) => a.every((v, i) => (Number.isNaN(v) && Number.isNaN(b[i])) || v === b[i]);
  const z = outcomes(g, n, u15, COSTS, [m, { ...m, entry: { ...m.entry!, tf: 15 } }, { ...m, entry: { ...m.entry!, tf: 60 } }]);
  assert.ok(same(z.net[0], z.net[2]) && same(z.net[1], z.net[3]), 'ML15 = an explicit 15-minute offset');
  assert.ok(!same(z.net[0], z.net[4]), 'ML15 differs from the same order 0.25 x the 1-hour ATR off');
  assert.ok(z.fills[0].filled > z.fills[4].filled, 'a nearer limit fills more often');
});

test('perp TA registry v1: trial ids match registry.py make_id; rows carry the schema fields', async () => {
  const { makeId, regRow, controlArm, pyDumps } = await import('../research/perpTaRegistry');
  // registry.py make_id('perp-ta', 'perp-ta-rulebook', 'random-entries:run-123', 'abc', []) (computed with the Python tool).
  assert.equal(makeId('perp-ta', 'perp-ta-rulebook', controlArm('123'), 'abc', []), 'a827be194cb37621');
  assert.equal(pyDumps(['a', ['b'], null, [], { z: 'é', a: 1 }]), '["a", ["b"], null, [], {"a": 1, "z": "\\u00e9"}]');
  const r = regRow({ arm: 'blind:x:all', role: 'candidate', control: 'c', codeSha: 's', byDay: { '2025-07-02': -1, '2025-07-01': 2 } });
  assert.deepEqual(r.data, { source: 'history', days: ['2025-07-01', '2025-07-02'], doge: false, benches: 'own' });
  for (const k of ['trial_id', 'thread', 'family', 'arm', 'role', 'code_sha', 'data', 'by_day'] as const) assert.ok(k in r, k);
});

test('perp TA registry: rows carry contract type perpetual and the modules; the backfill converts legacy rows and fills v1 shards', async () => {
  const { regRow, regModules, backfill, controlArm } = await import('../research/perpTaRegistry');
  const blind = regRow({ arm: 'blind:x:all', role: 'candidate', control: 'c', codeSha: 's', heldOut: true, byDay: { '2025-07-01': 1, '2025-07-02': 0 } });
  assert.equal(blind.contract_type, 'perpetual');
  assert.equal(blind.held_out, true);
  assert.equal(blind.hours, 48);
  assert.ok(blind.modules.includes('perp-exits') && blind.modules.includes('ta-net') && blind.modules.includes('ta-conviction'));
  assert.deepEqual([...blind.module_roles.changes, ...blind.module_roles.reads].sort(), blind.modules);
  assert.ok(!regModules(1).modules.includes('ta-conviction'), 'round 1 read no conviction');
  assert.equal(regRow({ arm: 'a', role: 'control', codeSha: 's' }).held_out, false);
  assert.equal(regRow({ arm: 'a', role: 'control', codeSha: 's' }).hours, undefined);

  // Legacy rows (before registry v1): round 1 has no round field; the study names the run it studied.
  const base = { thread: 'perp-ta-rulebook', run: '11', sha: 'sha1', at_utc: '2026-11-05T15:00:00.000Z' };
  const legacy = {
    'perp-ta-run-11.jsonl': [{ ...base, kind: 'run', n_raw: 5, funnel: { '+validation': 0 } }, { ...base, kind: 'group', group: 'g', pol: 'p', cond: 'c', verdict: 'fails validation' }],
    'perp-ta-study-run-12.jsonl': [{ thread: 'perp-ta-rulebook', kind: 'study', run: '12', sha: 'sha2', of_sweep_run: '11', at_utc: base.at_utc, n_raw: 5, n_eff: 2, spa_validation_p: 0.9 }],
    'perp-ta-run-13.jsonl': [{ ...base, run: '13', kind: 'run', round: 3 }],
    'perp-ta-blind-run-15.jsonl': [{ thread: 'perp-ta-rulebook', kind: 'blind-test', run: '15', sha: 'sha4', frozen_from_run: '11', set_hash: 'abcdef0123456789', n_candidates: 3, at_utc: base.at_utc, verdict: { rulebook: { pass: false, why: ['no gain'] }, passersRulebook: { pass: true, why: [] } } }],
  };
  // A v1 shard written before the contract fields (round 3's sweep run 13, already on Drive) and one already complete.
  const strip = (r: object) => { const o: Record<string, unknown> = { ...r }; for (const k of ['contract_type', 'modules', 'module_roles', 'held_out', 'hours']) delete o[k]; return o; };
  const ctl13 = regRow({ arm: controlArm('13'), role: 'control', codeSha: 'sha1' });
  const old13 = [strip(ctl13), strip(regRow({ arm: 'r3:sweep:run-13', role: 'candidate', control: ctl13.trial_id, codeSha: 'sha1' }))];
  const done = [regRow({ arm: 'study:of-run-13', role: 'candidate', codeSha: 'sha3' })];
  // A v1 blind shard missing the fields: the judged rulebook is held out, the passers' (chosen on the sealed block) is not.
  const bd2 = { '2025-07-01': 1 };
  const blindOld = [strip(regRow({ arm: 'blind:x:all', role: 'candidate', codeSha: 's', byDay: bd2 })), strip(regRow({ arm: 'blind:x:passers', role: 'candidate', codeSha: 's', byDay: bd2 }))];
  const { out, log } = backfill(legacy, { 'run-13.jsonl': old13, 'study-run-14.jsonl': done as unknown as Record<string, unknown>[], 'blind-run-16.jsonl': blindOld });
  assert.deepEqual(out['blind-run-16.jsonl'].map((r) => r.held_out), [true, false]);
  delete out['blind-run-16.jsonl'];
  assert.deepEqual(Object.keys(out).sort(), ['blind-run-15.jsonl', 'run-11.jsonl', 'run-13.jsonl', 'study-run-12.jsonl']);
  const [bf, ba, bp] = out['blind-run-15.jsonl'];
  assert.deepEqual([bf.arm, ba.arm, bp.arm], ['blind:abcdef012345:flat', 'blind:abcdef012345:all', 'blind:abcdef012345:passers']);
  assert.ok(ba.control === bf.trial_id && bp.control === bf.trial_id && !ba.held_out && !bp.held_out);
  assert.match(ba.verdict ?? '', /^no gain \(legacy row/);
  assert.ok(log.some((l) => /perp-ta-run-13.jsonl: run-13.jsonl already a v1 shard, skipped/.test(l)));
  const [ctl, run, grp] = out['run-11.jsonl'];
  assert.equal(ctl.arm, 'random-entries:run-11');
  assert.equal(run.arm, 'r1:sweep:run-11');
  assert.equal(grp.arm, 'r1:run-11:g|p|c');
  assert.equal(run.control, ctl.trial_id);
  assert.equal(grp.control, ctl.trial_id);
  // Same trial id as the current writer gives the same record; the record is kept under raw; ts is when the trial ran.
  assert.equal(run.trial_id, regRow({ arm: 'r1:sweep:run-11', role: 'candidate', codeSha: 'sha1' }).trial_id);
  assert.equal(run.raw?.n_raw, 5);
  assert.equal(run.ts, base.at_utc);
  assert.equal(run.code_epoch, 'perp-minute-sim sha1 (perp-ta round 1)');
  for (const r of [ctl, run, grp, ...out['study-run-12.jsonl']]) {
    assert.equal(r.contract_type, 'perpetual');
    assert.ok(!r.modules.includes('ta-conviction'), `${r.arm}: round 1`);
    assert.equal(r.held_out, false);
  }
  assert.equal(out['study-run-12.jsonl'][0].arm, 'study:of-run-11');
  // The v1 shard keeps its trial ids and fields and gains the contract fields (round 3: conviction read).
  assert.deepEqual(out['run-13.jsonl'].map((r) => r.trial_id), old13.map((r) => r.trial_id));
  for (const r of out['run-13.jsonl']) { assert.equal(r.contract_type, 'perpetual'); assert.ok(r.modules.includes('ta-conviction')); assert.ok(r.code_epoch?.startsWith('perp-minute-sim sha1')); }
  assert.ok(log.some((l) => /study-run-14.jsonl: complete, left as is/.test(l)));
});
