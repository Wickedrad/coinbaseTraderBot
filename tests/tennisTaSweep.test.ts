import assert from 'node:assert/strict';
import fs from 'fs';
import os from 'os';
import path from 'path';
import zlib from 'zlib';
import { test } from 'node:test';
import { buildHistoryReplay } from '../research/history/historyReplay';
import { SignalStudy } from '../research/tennisTaSignals';
import {
  CHECK_FROM, cmdRun, HARD_CUTOFF, LOCKBOX_FROM, SIM_VERSION, SUB_SHARDS, checkShards, lockboxOf, lockboxes, mondayEdge, parseRequest, partition,
  planUnits, poolOf, poolSpans, prepare, readShardMeta, requestUnits, shardFile, specsFor, stage1Specs, unitOf, unitPool, validateStage2Specs,
  verifyUnits, type Prep, type ShardMeta, type ShardOut, type Unit,
} from '../research/tennisTaSweep';
import { writeTaHistory } from './tennisTaFixture';

const DAY = 86_400_000, H = 3_600_000;
const UNITS_FILE = path.join(path.dirname(new URL(import.meta.url).pathname), '..', 'models', 'tennis-ta', 'state', 'units.json');
const unitsText = fs.readFileSync(UNITS_FILE, 'utf8');
const units: Unit[] = JSON.parse(unitsText);
const byId = new Map(units.map((u) => [u.id, u]));
const disc = units.filter((u) => unitPool(u) === 'disc');
const tmp = () => fs.mkdtempSync(path.join(os.tmpdir(), 'tta-sweep-'));

test('the committed unit table is sound: contiguous Monday 05:00 UTC edges, seals as the hash gives them', () => {
  assert.deepEqual(verifyUnits(units), []);
  const broken = units.map((u) => ({ ...u }));
  broken[3].sealed = !broken[3].sealed;
  broken[5].end += H;
  const p = verifyUnits(broken);
  assert.ok(p.some((x) => x.includes(broken[3].id) && x.includes('seal hash')));
  assert.ok(p.some((x) => x.includes(broken[5].id) && x.includes('Monday')));
  assert.equal(disc.length, 44);
});

test('partition: contiguous, non-empty, balanced, deterministic', () => {
  assert.deepEqual(partition([1, 1, 1, 1, 1, 1, 1, 1], 4), [2, 2, 2, 2]);
  assert.deepEqual(partition([3, 1, 1, 1], 2), [1, 3]);
  assert.deepEqual(partition([1, 2], 4), [1, 1]);
  assert.deepEqual(partition([], 3), []);
  const w = [7, 7, 21, 7, 7, 7, 14, 7, 7, 7, 7];
  const l = partition(w, 4);
  assert.equal(l.reduce((a, b) => a + b, 0), w.length);
  assert.ok(l.every((x) => x > 0));
  assert.deepEqual(partition(w, 4), l);
});

test('plan: shards and sub-slices cut at unit edges, every disc unit once, from/to per C5', () => {
  const sel = requestUnits(units, 'disc', '2024-12-23', '2026-03-31');
  assert.deepEqual(sel.map((u) => u.id), disc.map((u) => u.id));
  const plan = planUnits(sel, 8);
  assert.equal(plan.length, 8);
  assert.deepEqual(plan.flatMap((e) => e.units), disc.map((u) => u.id));
  const days = plan.map((e) => e.units.reduce((s, id) => s + (byId.get(id)!.end - byId.get(id)!.start) / DAY, 0));
  assert.ok(Math.max(...days) - Math.min(...days) <= 28, `balanced by unit length: ${days.join(',')}`);
  for (const e of plan) {
    const us = e.units.map((id) => byId.get(id)!);
    assert.equal(e.from, us[0].startDay, 'from = the first unit start day');
    const lastEnd = new Date(us[us.length - 1].end).toISOString().slice(0, 10);
    assert.equal(e.to, new Date(Date.parse(lastEnd) + DAY).toISOString().slice(0, 10), 'to = the day after the last unit end');
    // Every owned start: in [from 00:00, to 00:00) and in a unit of the list. A unit's whole span is inside the range.
    for (const u of us) assert.ok(u.start >= Date.parse(e.from) && u.end <= Date.parse(e.to));
    // Units in a slice are in order (contiguous in the pool; sealed units between them are streamed past).
    for (let i = 1; i < us.length; i++) assert.ok(us[i].start > us[i - 1].start);
    const sub = planUnits(us, SUB_SHARDS);
    assert.ok(sub.length >= 1 && sub.length <= SUB_SHARDS);
    assert.deepEqual(sub.flatMap((s) => s.units), e.units, 'sub-slices partition the shard by whole units');
    assert.deepEqual(sub.map((s) => s.k), sub.map((_, i) => i));
  }
  // A Slam (one unit of 2+ weeks) is never split.
  const slam = disc.find((u) => u.slam)!;
  assert.equal(plan.filter((e) => e.units.includes(slam.id)).length, 1);
  // Matches of a sealed unit between two slice units are never owned: their unit is not in any list.
  assert.ok(!plan.some((e) => e.units.some((id) => byId.get(id)!.sealed)));
});

test('requestUnits: [from, to] must cover the start of every disc unit it touches; units starting by `to` are whole', () => {
  assert.throws(() => requestUnits(units, 'disc', '2025-01-01', '2026-03-31'), /does not cover the start of disc unit W-2024-12-30/);
  const sel = requestUnits(units, 'disc', '2025-03-03', '2025-03-04');
  assert.deepEqual(sel.map((u) => u.id), ['W-2025-03-03']);
  assert.equal(planUnits(sel, 8)[0].to, '2025-03-11');
  assert.throws(() => requestUnits(units, 'disc', '2026-04-02', '2026-04-03'), /holds no disc unit/);
});

test('poolOf: start and close before the cutoff, lockbox ids, embargo, sealed, check', () => {
  const w = byId.get('W-2025-03-10')!;
  assert.equal(w.sealed, false);
  const s = w.start + 2 * DAY;
  assert.equal(poolOf(s, s + 3 * H, units), 'disc');
  assert.equal(unitOf(s, units), 'W-2025-03-10');
  // The close is tested too: a match starting before the cutoff but closing at or after it is out.
  const late = HARD_CUTOFF - H;
  assert.equal(poolOf(late, HARD_CUTOFF + H, units), 'out');
  assert.equal(poolOf(late, HARD_CUTOFF, units), 'out');
  assert.equal(poolOf(HARD_CUTOFF, HARD_CUTOFF + H, units), 'out');
  // Lockbox ids: a [start, end) table anchored at LOCKBOX_FROM in 7-day steps.
  assert.equal(lockboxOf(LOCKBOX_FROM - 1), undefined);
  assert.equal(lockboxOf(LOCKBOX_FROM), 'L1');
  assert.equal(lockboxOf(LOCKBOX_FROM + 7 * DAY - 1), 'L1');
  assert.equal(lockboxOf(LOCKBOX_FROM + 7 * DAY), 'L2');
  assert.deepEqual(lockboxes(LOCKBOX_FROM + 8 * DAY).map((l) => [l.id, l.start - LOCKBOX_FROM, l.end - LOCKBOX_FROM]), [['L1', 0, 7 * DAY], ['L2', 7 * DAY, 14 * DAY]]);
  // With a later cutoff (a future round), a match reaching a lockbox week is out unless every week it reaches is opened.
  const cutoff = LOCKBOX_FROM + 30 * DAY;
  const wk = byId.get('W-2026-11-09')!; // holds L1's tail and L2's head; sealed or not, only its pool changes
  const opened = new Set<string>([wk.id]);
  const a = LOCKBOX_FROM + 3 * DAY + 12 * H; // Nov 9 17:00 UTC, in L1
  assert.equal(poolOf(a, a + 3 * H, units, opened, cutoff), 'out');
  assert.equal(poolOf(a, a + 3 * H, units, new Set([...opened, 'L1']), cutoff), 'check');
  const b = LOCKBOX_FROM + 7 * DAY - H; // starts in L1, closes in L2
  assert.equal(poolOf(b, b + 3 * H, units, new Set([...opened, 'L1']), cutoff), 'out');
  assert.equal(poolOf(b, b + 3 * H, units, new Set([...opened, 'L1', 'L2']), cutoff), 'check');
  // Sealed units, embargo windows on both sides, dev-check after CHECK_FROM.
  const sealed = units.find((u) => u.sealed && u.start < CHECK_FROM && !u.slam)!;
  assert.equal(poolOf(sealed.start + DAY, sealed.start + DAY + 3 * H, units), 'sealed');
  assert.equal(poolOf(sealed.start - 2 * H, sealed.start, units), 'embargo');
  assert.equal(poolOf(sealed.end + 23 * H, sealed.end + 26 * H, units), 'embargo');
  assert.equal(poolOf(sealed.start, sealed.start + H, units, new Set([sealed.id])), unitPool(sealed, new Set([sealed.id])));
  const chk = units.find((u) => !u.sealed && u.start >= CHECK_FROM && u.start < HARD_CUTOFF && !units.some((x) => x.sealed && (x.end === u.start)))!;
  assert.equal(poolOf(chk.start + 2 * DAY, chk.start + 2 * DAY + 3 * H, units), 'check');
});

test('poolSpans: every pool unit, embargo windows left out of the hours', () => {
  const spans = poolSpans(units, 'disc');
  assert.deepEqual(spans.map((s) => s.unit), disc.map((u) => u.id));
  const sealedStarts = new Set(units.filter((u) => u.sealed).map((u) => u.start)), sealedEnds = new Set(units.filter((u) => u.sealed).map((u) => u.end));
  for (const s of spans) {
    const full = (s.end - s.start) / H;
    const cut = (sealedStarts.has(s.end) ? 24 : 0) + (sealedEnds.has(s.start) ? 24 : 0);
    assert.equal(s.hours, full - cut, s.unit);
    // A match starting in a counted interval is in the pool; one in a cut window is embargoed.
    for (const [a] of s.intervals) assert.equal(poolOf(a, a + H, units), 'disc');
  }
  const total = spans.reduce((x, s) => x + s.hours, 0);
  assert.ok(total < disc.reduce((x, u) => x + (u.end - u.start) / H, 0));
});

test('stage1Specs: 81 configs x F1/F2/coin + 2 sticks, ratchet off everywhere, sticks flagged', () => {
  const s = stage1Specs();
  assert.equal(s.length, 245);
  assert.equal(new Set(s.map((x) => x.id)).size, 245);
  assert.ok(s.every((x) => x.overrides.TENNIS_TRAIL_RATCHET === false));
  assert.ok(s.every((x) => !('HARNESS_LOSER_CUT' in x.overrides)));
  assert.equal(s.filter((x) => x.fill === 'F1' && !x.placebo && !x.stick).length, 81);
  assert.equal(s.filter((x) => x.fill === 'F2').length, 81);
  assert.equal(s.filter((x) => x.placebo === 'coin').length, 81);
  const sticks = s.filter((x) => x.stick);
  assert.deepEqual(sticks.map((x) => x.id), ['A|s1|prod|settlehold|F1', 'A|s1|prod|nopacer|F1']);
  assert.equal(sticks[0].overrides.TENNIS_END_LOSER_CUT, false);
  assert.equal(sticks[1].overrides.HARNESS_PACER, 'off');
  assert.ok(!('TENNIS_END_LOSER_CUT' in sticks[1].overrides));
  assert.ok(s.every((x) => /^A\|s1\|/.test(x.id) && Number(x.overrides.TENNIS_CONF_WINDOW_SEC) >= 60));
  assert.throws(() => specsFor('1', 'R'), /H design/);
});

test('stage 2 specs: validated, ratchet forced off on H, clear failures', () => {
  const ok = validateStage2Specs([
    { id: 'A|s2|a|F1', overrides: { TENNIS_ENTRY_MIN_SIGNALS_PRE: 0 }, fill: 'F1' },
    { id: 'A|s2|a|coin', overrides: { TENNIS_ENTRY_MIN_SIGNALS_PRE: 0 }, fill: 'F1', placebo: 'coin' },
    { id: 'A|s2|prod|settlehold|F1', overrides: { TENNIS_END_LOSER_CUT: false }, fill: 'F1', stick: true, offsetMs: 2500 },
  ]);
  assert.equal(ok.length, 3);
  assert.ok(ok.every((x) => x.overrides.TENNIS_TRAIL_RATCHET === false));
  assert.equal(ok[2].stick, true);
  assert.equal(ok[2].offsetMs, 2500);
  assert.equal(validateStage2Specs([{ id: 'A|s2|r', overrides: {}, fill: 'F1' }], 'R')[0].overrides.TENNIS_TRAIL_RATCHET, undefined);
  const bad = (x: unknown, re: RegExp) => assert.throws(() => validateStage2Specs(x), re);
  bad({}, /JSON array/);
  bad([], /empty/);
  bad([{ id: 'A|s1|x', overrides: {}, fill: 'F1' }], /starting 'A\|s2\|'/);
  bad([{ id: 'A|s2|x', overrides: {}, fill: 'F1' }, { id: 'A|s2|x', overrides: {}, fill: 'F2' }], /duplicate id/);
  bad([{ id: 'A|s2|x', overrides: {}, fill: 'F3' }], /fill must be/);
  bad([{ id: 'A|s2|x', overrides: {}, fill: 'F1', placebo: 'shift' }], /placebo/);
  bad([{ id: 'A|s2|x', overrides: { HARNESS_LOSER_CUT: false }, fill: 'F1' }], /HARNESS_LOSER_CUT no longer exists/);
  bad([{ id: 'A|s2|x', overrides: { TENNIS_TRAIL_RATCHET: true }, fill: 'F1' }], /must be off on H/);
  bad([{ id: 'A|s2|x', overrides: { conf: 1 }, fill: 'F1' }], /not a TENNIS_\*/);
  bad([{ id: 'A|s2|x', overrides: { TENNIS_CONF_FLOW: [1] }, fill: 'F1' }], /string, finite number or boolean/);
  bad([{ id: 'A|s2|x', overrides: {}, fill: 'F1', extra: 1 }], /unknown key extra/);
  const dir = tmp();
  assert.throws(() => specsFor('2', 'H', path.join(dir, 'stage2-specs.json')), /does not exist/);
  fs.writeFileSync(path.join(dir, 'stage2-specs.json'), '[{"id": "A|s2|x", "overrides": {}, "fill": "F1"}]');
  assert.equal(specsFor('2', 'H', path.join(dir, 'stage2-specs.json')).length, 1);
  fs.writeFileSync(path.join(dir, 'bad.json'), '[{');
  assert.throws(() => specsFor('2', 'H', path.join(dir, 'bad.json')), /not valid JSON/);
  assert.throws(() => specsFor('3', 'H'), /stage must be/);
});

test('requests: pool disc only, defaults, unknown keys refused', () => {
  const r = parseRequest({ stage: 1 }, units);
  assert.deepEqual(r, { stage: '1', pool: 'disc', from: '2024-12-23', to: '2026-03-31', shards: 8, familyB: false });
  assert.throws(() => parseRequest({ stage: '1', pool: 'check' }, units), /openings-ledger entry/);
  assert.throws(() => parseRequest({ stage: '1', pool: 'sealed' }, units), /openings-ledger entry/);
  assert.throws(() => parseRequest({ stage: '1', pool: 'disc,check' }, units), /pool must be 'disc'/);
  assert.throws(() => parseRequest({ stage: '1', familyb: true }, units), /unknown key familyb/);
  assert.throws(() => parseRequest({ stage: '1', familyB: 'yes' }, units), /familyB must be/);
  assert.throws(() => parseRequest({ stage: '1', from: '2025-02-30' }, units), /from must be/);
  assert.throws(() => parseRequest({ stage: '1', shards: 0 }, units), /shards/);
  assert.throws(() => parseRequest({ stage: '4' }, units), /stage must be/);
});

function prepOf(req: object, specs?: string): Prep {
  return prepare(JSON.stringify(req), unitsText, specs);
}

test('prepare: plan, sub-plans and expected files; refuses a request that cuts a unit or lacks stage 2 specs', () => {
  const p = prepOf({ stage: '1', pool: 'disc', from: '2024-12-23', to: '2026-03-31', shards: 8, familyB: true });
  assert.equal(p.configs, 245);
  assert.equal(p.plan.length, 8);
  assert.equal(p.subPlans.length, 8);
  assert.deepEqual(p.units, disc.map((u) => u.id));
  assert.equal(p.expected.length, p.subPlans.reduce((s, x) => s + x.length, 0));
  assert.equal(new Set(p.expected).size, p.expected.length);
  assert.equal(p.expected[0], shardFile('1', 0, 0));
  assert.deepEqual(p.subPlans.flat().flatMap((s) => s.units), p.units);
  assert.equal(p.poolSpans.length, 44);
  assert.equal(p.familyB, true);
  assert.equal(p.simVersion, SIM_VERSION);
  assert.throws(() => prepOf({ stage: '1', from: '2025-01-01', to: '2026-03-31' }), /W-2024-12-30/);
  assert.throws(() => prepOf({ stage: '2' }, path.join(tmp(), 'none.json')), /stage 2 reads its spec list/);
  assert.throws(() => prepare(JSON.stringify({ stage: '1' }), JSON.stringify(units.map((u, i) => (i === 7 ? { ...u, sealed: !u.sealed } : u)))), /seal hash/);
});

function metaOf(p: Prep, k: number, j: number, over: Partial<ShardMeta> = {}): ShardMeta {
  const s = p.subPlans[k][j];
  return {
    simVersion: SIM_VERSION, stage: p.stage, pool: p.pool, run: '42', k, j, shards: p.plan.length, subShards: p.subPlans[k].length, from: s.from, to: s.to,
    units: s.units, dataVersion: 'KXATPMATCH:sha256:aa,KXWTAMATCH:sha256:bb', requestSha: p.requestSha, families: p.familyB ? ['A', 'B'] : ['A'], unitsSha: p.unitsSha,
    coverage: { span: [s.from, s.to], series: { KXATPMATCH: { first: '2025-02-20', last: '2026-11-04', files: 600, spanDays: 7, withFile: 7, withTrades: 7, missing: [] } }, matches: 10, noPublishedStart: 1, noPublishedStartEvents: ['E'] },
    ...over,
  };
}

test('checkShards: the full set passes; missing, duplicate, extra, mixed data version or wrong slice fail', () => {
  const p = prepOf({ stage: '1', shards: 2 });
  const all = () => p.expected.map((f) => { const m = /a-s1-(\d+)-(\d+)/.exec(f)!; return { file: f, meta: metaOf(p, Number(m[1]), Number(m[2])) }; });
  const good = checkShards(p, [...p.expected], all(), '42');
  assert.deepEqual(good.problems, []);
  assert.equal(good.summary.units, 44);
  assert.equal(good.summary.matches, 10 * p.expected.length);
  assert.equal(good.summary.noPublishedStart, p.expected.length);
  // Missing on Drive and not copied.
  const miss = checkShards(p, p.expected.slice(1), all().slice(1), '42');
  assert.ok(miss.problems.some((x) => x.startsWith(`${p.expected[0]}: missing on Drive`)));
  assert.ok(miss.problems.some((x) => x.includes('swept by no shard')));
  // Two copies of one name on Drive (rclone copies only one of them).
  assert.ok(checkShards(p, [...p.expected, p.expected[2]], all(), '42').problems.some((x) => x.includes('2 copies')));
  // A file the plan does not name.
  assert.ok(checkShards(p, [...p.expected, 'a-s1-9-0.json.gz'], all(), '42').problems.some((x) => x.includes('not in the plan')));
  // Mixed data versions, another run, another request.
  const mixed = all();
  mixed[3].meta.dataVersion = 'KXATPMATCH:sha256:cc,KXWTAMATCH:sha256:bb';
  assert.ok(checkShards(p, [...p.expected], mixed, '42').problems.some((x) => x.startsWith('dataVersion differs')));
  assert.ok(checkShards(p, [...p.expected], all(), '43').problems.some((x) => x.includes('run "42"')));
  const unv = all();
  for (const m of unv) m.meta.dataVersion = 'unversioned';
  assert.ok(checkShards(p, [...p.expected], unv, '42').problems.some((x) => x.includes('no data version')));
  const req = all();
  req[0].meta.requestSha = 'x';
  assert.ok(checkShards(p, [...p.expected], req, '42').problems.some((x) => x.includes('requestSha')));
  // A slice whose units differ from the plan.
  const sw = all();
  sw[1].meta.units = [...sw[0].meta.units];
  const pr = checkShards(p, [...p.expected], sw, '42').problems;
  assert.ok(pr.some((x) => x.includes(': units ')));
  assert.ok(pr.some((x) => x.includes('also swept by')));
  // Family B planned but absent.
  const pb = prepOf({ stage: '1', shards: 1, familyB: true });
  const noB = pb.expected.map((f, j) => ({ file: f, meta: metaOf(pb, 0, j, { families: ['A'] }) }));
  assert.ok(checkShards(pb, [...pb.expected], noB, '42').problems.some((x) => x.includes('family B missing')));
});

test('readShardMeta reads the head of a gzip shard file without the rest', async () => {
  const dir = tmp();
  const meta = { simVersion: SIM_VERSION, note: 'braces } ] { [ and "quotes" \\ inside', nested: { a: [1, { b: 2 }] } };
  const f = path.join(dir, 'a-s1-0-0.json.gz');
  const big = Array.from({ length: 20_000 }, (_, i) => ({ event: `E${i}`, x: 'y'.repeat(50) }));
  fs.writeFileSync(f, zlib.gzipSync(JSON.stringify({ meta, matchList: big, runs: [] })));
  assert.deepEqual(await readShardMeta(f), meta);
  const g = path.join(dir, 'other.json.gz');
  fs.writeFileSync(g, zlib.gzipSync(JSON.stringify({ runs: [], meta })));
  await assert.rejects(readShardMeta(g), /not a shard file/);
  const h = path.join(dir, 'cut.json.gz');
  fs.writeFileSync(h, zlib.gzipSync('{"meta":{"a":[1,2'));
  await assert.rejects(readShardMeta(h), /never closes/);
});

test('mondayEdge: Monday 05:00 UTC at or before t', () => {
  const m = Date.parse('2025-03-10T05:00:00Z');
  assert.equal(mondayEdge(m), m);
  assert.equal(mondayEdge(m - 1), m - 7 * DAY);
  assert.equal(mondayEdge(m + 6 * DAY + 23 * H), m);
});

async function sliceRun(familyB: boolean): Promise<{ prep: Prep; out: ShardOut; file: string; replay: string; specs: string }> {
  const dir = tmp(), hist = path.join(dir, 'hist'), replay = path.join(dir, 'replay');
  writeTaHistory(hist); // three KXATPMATCH matches on 2026-03-02 (unit W-2026-03-02, disc)
  await buildHistoryReplay({ historyDir: hist, outDir: replay, assets: [], fromDay: '2026-03-01', toDay: '2026-03-03', tennisSeries: ['KXATPMATCH'], log: () => {} });
  const specs = path.join(dir, 'stage2-specs.json'), reqFile = path.join(dir, 'sweep-request.json');
  fs.writeFileSync(specs, JSON.stringify([
    { id: 'A|s2|loose|F1', overrides: { TENNIS_ENTRY_MIN_SIGNALS_PRE: 0, TENNIS_ENTRY_MIN_SIGNALS_LIVE: 0, TENNIS_FAV_ENTRY_MIN_SIGNALS: 0 }, fill: 'F1' },
    { id: 'A|s2|prod|nopacer|F1', overrides: { HARNESS_PACER: 'off' }, fill: 'F1', stick: true },
  ]));
  const reqText = JSON.stringify({ stage: '2', from: '2026-03-02', to: '2026-03-02', shards: 1, familyB });
  fs.writeFileSync(reqFile, reqText);
  const prep = prepare(reqText, unitsText, specs);
  assert.deepEqual(prep.plan, [{ k: 0, from: '2026-03-02', to: '2026-03-10', units: ['W-2026-03-02'] }]);
  const sub = prep.subPlans[0][0];
  const file = path.join(dir, 'shards', prep.expected[0]);
  await cmdRun({ replay, hist: path.join(hist, 'kalshi'), series: 'KXATPMATCH', from: sub.from, to: sub.to, 'units-list': sub.units.join(','), stage: '2', specs,
    pool: 'disc', units: UNITS_FILE, 'family-b': String(familyB), request: reqFile, 'data-version': 'KXATPMATCH:sha256:test', run: '42', k: '0', j: '0', shards: '1',
    'sub-shards': String(prep.subPlans[0].length), out: file });
  return { prep, out: JSON.parse(zlib.gunzipSync(fs.readFileSync(file)).toString('utf8')) as ShardOut, file, replay, specs };
}

test('run: one sub-slice end to end on the fixture writes a C4 shard file the report gate accepts', async () => {
  const { prep, out, file, replay, specs } = await sliceRun(false);
  const m = out.meta;
  assert.equal(m.simVersion, 'tennis-ta-sim/2');
  assert.deepEqual([m.stage, m.pool, m.run, m.k, m.j, m.shards, m.subShards, m.from, m.to], ['2', 'disc', '42', 0, 0, 1, 1, '2026-03-02', '2026-03-10']);
  assert.deepEqual(m.units, ['W-2026-03-02']);
  assert.deepEqual(m.families, ['A']);
  assert.equal(m.requestSha, prep.requestSha);
  assert.equal(m.dataVersion, 'KXATPMATCH:sha256:test');
  assert.equal(m.coverage.matches, 3);
  assert.equal(m.coverage.noPublishedStart, 0);
  assert.deepEqual(m.coverage.feed, { gaps: 0, gapMs: 0, blindGaps: 0, liveDays: 0, blindDays: 0, lateGrids: 0 });
  assert.equal(m.coverage.series!.KXATPMATCH.withFile, 1);
  assert.equal(m.coverage.series!.KXATPMATCH.spanDays, 8);
  assert.equal(out.matchList.length, 3);
  assert.ok(out.matchList.every((x) => x.pool === 'disc' && x.unit === 'W-2026-03-02' && x.startPublished === true));
  assert.deepEqual(out.runs.map((r) => [r.id, r.stick ?? false, r.overrides.TENNIS_TRAIL_RATCHET]), [['A|s2|loose|F1', false, false], ['A|s2|prod|nopacer|F1', true, false]]);
  assert.ok(out.runs.every((r) => r.pnl.length === 3));
  assert.equal(out.familyB, undefined);
  const meta = await readShardMeta(file);
  assert.deepEqual(meta, m);
  assert.deepEqual(checkShards(prep, [...prep.expected], [{ file: prep.expected[0], meta }], '42').problems, []);
  // A slice whose unit list leaves the fixture's unit out owns nothing.
  const other = path.join(path.dirname(file), 'other.json.gz');
  await cmdRun({ replay, from: '2026-03-02', to: '2026-03-10', 'units-list': 'W-2026-02-23', stage: '2', specs, pool: 'disc', units: UNITS_FILE, out: other });
  assert.equal((JSON.parse(zlib.gunzipSync(fs.readFileSync(other)).toString('utf8')) as ShardOut).matchList.length, 0);
  await assert.rejects(cmdRun({ replay, from: '2026-03-02', to: '2026-03-10', stage: '1', pool: 'check', units: UNITS_FILE, out: other }), /openings-ledger/);
});

test('run with familyB: one SignalStudy per sub-slice, grids tagged with unit and start, cells in the shard file', async (t) => {
  if (typeof (SignalStudy.prototype as unknown as { exportCells?: unknown }).exportCells !== 'function') {
    t.skip('SignalStudy.exportCells (contract C3) has not landed in research/tennisTaSignals.ts yet');
    return;
  }
  const { prep, out, file, replay, specs } = await sliceRun(true);
  assert.deepEqual(out.meta.families, ['A', 'B']);
  assert.ok(out.familyB && Array.isArray(out.familyB.cells));
  assert.equal(out.familyB!.stratum, 'H');
  for (const c of out.familyB!.cells) for (const u of Object.keys(c.units)) assert.equal(u, 'W-2026-03-02');
  assert.equal(out.meta.familyBStartMismatch, 0);
  assert.deepEqual(checkShards(prep, [...prep.expected], [{ file: prep.expected[0], meta: await readShardMeta(file) }], '42').problems, []);
  // A slice that owns no match (an embargoed or empty unit) still writes its family B export: the sweep gives the study
  // its stratum up front, since there is no grid to take it from.
  const empty = path.join(path.dirname(file), 'empty.json.gz');
  await cmdRun({ replay, from: '2026-03-02', to: '2026-03-10', 'units-list': 'W-2026-02-23', stage: '2', specs, pool: 'disc', units: UNITS_FILE, 'family-b': 'true', out: empty });
  const e = JSON.parse(zlib.gunzipSync(fs.readFileSync(empty)).toString('utf8')) as ShardOut;
  assert.equal(e.matchList.length, 0);
  assert.deepEqual(e.meta.families, ['A', 'B']);
  assert.equal(e.familyB!.stratum, 'H');
  assert.ok(e.familyB!.designSize > 0 && e.familyB!.cells.length === 0);
});
