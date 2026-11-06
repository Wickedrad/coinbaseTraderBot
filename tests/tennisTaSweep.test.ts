import assert from 'node:assert/strict';
import { spawnSync } from 'child_process';
import fs from 'fs';
import os from 'os';
import path from 'path';
import zlib from 'zlib';
import { test } from 'node:test';
import { REPLAY_VERSION, buildHistoryReplay } from '../research/history/historyReplay';
import { SignalStudy } from '../research/tennisTaSignals';
import {
  DEV_TO, H_HOLD, HARD_CUTOFF, HARNESS_RULES, HISTORY_FROM, HOLD_FOLDS, HOLD_FROM, HOLD_SPECS, LOCKBOX_FROM, OPENINGS_LEDGER, SIM_VERSION, SLAMS, START_ERA_FROM,
  SUB_SHARDS, assertPool, buildUnits, canonicalSpecs, checkShards, cmdRun, configKeys, holdFold, holdFoldEdges, holdFolds, lockboxOf, lockboxes, mondayEdge,
  parseOpenings, parseRequest, partition, planUnits, poolInterval, poolOf, poolSpans, poolUnitsOf, prepare, readShardMeta, requestUnits, runTags, shardFile,
  slamUnits, specsFor, specsHash, stage1Specs, STICK_KEYS, unitOf, unitPools, validateHoldSpecs, validateStage2Specs, verifyUnits,
  type Pool, type Prep, type ShardMeta, type ShardOut, type SweepSpec, type Unit,
} from '../research/tennisTaSweep';
import { writeTaHistory } from './tennisTaFixture';

const DAY = 86_400_000, H = 3_600_000;
const REPO = path.join(path.dirname(new URL(import.meta.url).pathname), '..');
const UNITS_FILE = path.join(REPO, 'models', 'tennis-ta', 'state', 'units.json');
const unitsText = fs.readFileSync(UNITS_FILE, 'utf8');
const units: Unit[] = JSON.parse(unitsText);
const byId = new Map(units.map((u) => [u.id, u]));
const disc = poolUnitsOf(units, 'disc');
const old = poolUnitsOf(units, 'old');
const hold = poolUnitsOf(units, 'hold');
const tmp = () => fs.mkdtempSync(path.join(os.tmpdir(), 'tta-sweep-'));

test('the committed unit table is sound: contiguous Monday 05:00 UTC edges; its legacy seal flags are ignored', () => {
  assert.deepEqual(verifyUnits(units), []);
  const broken = units.map((u) => ({ ...u }));
  broken[3].sealed = !broken[3].sealed; // the retired A3 seal (C9): no longer read
  broken[5].end += H;
  const p = verifyUnits(broken);
  assert.ok(!p.some((x) => x.startsWith(`${broken[3].id}:`)), p.join('\n'));
  assert.ok(p.some((x) => x.includes(broken[5].id) && x.includes('Monday')));
  assert.ok(buildUnits('2026-07-01', '2026-08-31').every((u) => !('sealed' in u)));
  // C9 pools over the committed table: history from 2025-06-18, the start era from the placeholder Apr 27, H-DEV to
  // Jul 31 00:00 UTC, H-HOLD from Aug 1 00:00 UTC to the cutoff. W-2026-07-27 holds both disc and hold time.
  const count = (pool: Pool) => units.filter((u) => unitPools(u).includes(pool)).length;
  assert.deepEqual((['out', 'old', 'disc', 'embargo', 'hold'] as Pool[]).map(count), [23, 40, 11, 1, 13]);
  assert.deepEqual(unitPools(byId.get('W-2026-07-27')!), ['disc', 'embargo', 'hold']);
  assert.deepEqual([disc[0].id, disc[disc.length - 1].id], ['W-2026-04-27', 'W-2026-07-27']);
  assert.deepEqual([old[0].id, old[old.length - 1].id], ['W-2025-06-16', 'W-2026-04-20']);
  assert.deepEqual([hold[0].id, hold[hold.length - 1].id], ['W-2026-07-27', 'W-2026-11-02']);
  // The start era begins at a unit start (Monday 05:00 UTC), so no unit straddles the old and start eras; H-DEV and
  // H-HOLD are UTC days (registry.py's H_HOLD), with the embargo day between them.
  assert.equal(mondayEdge(START_ERA_FROM), START_ERA_FROM);
  assert.ok(units.some((u) => u.start === START_ERA_FROM));
  assert.ok(START_ERA_FROM < DEV_TO && DEV_TO < HOLD_FROM && HOLD_FROM < HARD_CUTOFF);
  assert.equal(new Date(DEV_TO).toISOString(), '2026-07-31T00:00:00.000Z');
  assert.equal(new Date(HOLD_FROM).toISOString(), '2026-08-01T00:00:00.000Z');
  assert.equal(HOLD_FROM, Date.parse(`${H_HOLD[0]}T00:00:00Z`));
  assert.equal(new Date(HISTORY_FROM).toISOString(), '2025-06-18T00:00:00.000Z');
});

test('verifyUnits: Grand Slam placement against SLAMS (one unit each, never split, never cut by the table edge)', () => {
  // SLAMS itself: Monday 05:00 UTC edges, the draw inside its unit, no two Slam units overlapping.
  const slams = slamUnits();
  assert.equal(slams.length, SLAMS.length);
  for (const s of slams) {
    assert.ok(mondayEdge(s.start) === s.start && mondayEdge(s.end) === s.end, s.name);
    assert.ok(s.start <= Date.parse(s.first) + 12 * H && Date.parse(s.final) + DAY <= s.end, `${s.name} ${s.first}: the draw lies inside its unit`);
  }
  for (let i = 1; i < slams.length; i++) assert.ok(slams[i].start >= slams[i - 1].end, `${slams[i].name} ${slams[i].first} overlaps the Slam before it`);
  for (const s of slams.filter((x) => x.start >= units[0].start && x.end <= units[units.length - 1].end)) {
    assert.ok(units.some((u) => u.slam === s.name && u.start === s.start && u.end === s.end), `${s.name} ${s.first} is one unit of the committed table`);
  }
  // A Slam split into week units (each with its right seal) is refused.
  const ao = units.findIndex((u) => u.slam === 'AO');
  const a = units[ao];
  const weeks: Unit[] = [];
  for (let t = a.start; t < a.end; t += 7 * DAY) { const d = new Date(t).toISOString().slice(0, 10); weeks.push({ id: `W-${d}`, start: t, end: t + 7 * DAY, startDay: d }); }
  const split = verifyUnits([...units.slice(0, ao), ...weeks, ...units.slice(ao + 1)]);
  assert.ok(split.some((x) => x.includes(`W-${a.startDay}`) && x.includes('overlapping Grand Slam AO')), split.join('\n'));
  assert.ok(split.some((x) => x.startsWith('Grand Slam AO') && x.includes('not in the table as one unit')));
  // A table that starts inside a Slam passes the calendar comparison over its own span, but not the SLAMS check.
  const cut = buildUnits(new Date(a.start + 8 * DAY).toISOString().slice(0, 10), '2025-03-31'); // a day of the Slam's second week
  assert.deepEqual([cut[0].slam, cut[0].start], ['AO', a.start + 7 * DAY]);
  const pc = verifyUnits(cut);
  assert.ok(pc.some((x) => x.includes(cut[0].id) && x.includes('no Grand Slam AO in SLAMS')), pc.join('\n'));
  assert.ok(pc.some((x) => x.includes('the table starts or ends inside it')));
  // A week unit relabelled as a Slam.
  const fake = units.map((u) => ({ ...u }));
  const w = fake.findIndex((u) => u.id === 'W-2026-07-13');
  fake[w] = { ...fake[w], slam: 'WIM', id: 'WIM-2026-07-13' };
  assert.ok(verifyUnits(fake).some((x) => x.includes('WIM-2026-07-13') && x.includes('no Grand Slam WIM in SLAMS')));
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
  const sel = requestUnits(units, 'disc', '2026-04-27', '2026-07-30');
  assert.deepEqual(sel.map((u) => u.id), disc.map((u) => u.id));
  const plan = planUnits(sel, 8);
  assert.equal(plan.length, 8);
  assert.deepEqual(plan.flatMap((e) => e.units), disc.map((u) => u.id));
  for (const e of plan) {
    const us = e.units.map((id) => byId.get(id)!);
    assert.equal(e.from, us[0].startDay, 'from = the first unit start day');
    const lastEnd = new Date(us[us.length - 1].end).toISOString().slice(0, 10);
    assert.equal(e.to, new Date(Date.parse(lastEnd) + DAY).toISOString().slice(0, 10), 'to = the day after the last unit end');
    // Every owned start: in [from 00:00, to 00:00) and in a unit of the list. A unit's whole span is inside the range.
    for (const u of us) assert.ok(u.start >= Date.parse(e.from) && u.end <= Date.parse(e.to));
    for (let i = 1; i < us.length; i++) assert.ok(us[i].start > us[i - 1].start);
    const sub = planUnits(us, SUB_SHARDS);
    assert.ok(sub.length >= 1 && sub.length <= SUB_SHARDS);
    assert.deepEqual(sub.flatMap((s) => s.units), e.units, 'sub-slices partition the shard by whole units');
    assert.deepEqual(sub.map((s) => s.k), sub.map((_, i) => i));
  }
  // A Slam (one unit of 2+ weeks) is never split.
  for (const slam of disc.filter((u) => u.slam)) assert.equal(plan.filter((e) => e.units.includes(slam.id)).length, 1);
  // The old pool cuts the same way (40 units into 8 shards, balanced by unit length).
  const op = planUnits(requestUnits(units, 'old', '2025-06-16', '2026-04-26'), 8);
  assert.deepEqual(op.flatMap((e) => e.units), old.map((u) => u.id));
  const od = op.map((e) => e.units.reduce((s, id) => s + (byId.get(id)!.end - byId.get(id)!.start) / DAY, 0));
  assert.ok(Math.max(...od) - Math.min(...od) <= 28, `balanced by unit length: ${od.join(',')}`);
  // The hold block too (13 units, the USO 2026 Slam one of them, whole).
  const hp = planUnits(requestUnits(units, 'hold', '2026-07-27', H_HOLD[1]), 8);
  assert.deepEqual(hp.flatMap((e) => e.units), hold.map((u) => u.id));
  assert.equal(hp.filter((e) => e.units.includes('USO-2026-08-24')).length, 1);
});

test('requestUnits: [from, to] must cover the start of every pool unit it touches; units starting by `to` are whole', () => {
  assert.throws(() => requestUnits(units, 'disc', '2026-05-20', '2026-07-30'), /does not cover the start of disc unit RG-2026-05-18/);
  const sel = requestUnits(units, 'disc', '2026-07-13', '2026-07-14');
  assert.deepEqual(sel.map((u) => u.id), ['W-2026-07-13']);
  assert.equal(planUnits(sel, 8)[0].to, '2026-07-21');
  assert.throws(() => requestUnits(units, 'disc', '2026-08-04', '2026-09-16'), /holds no disc unit/);
  // W-2026-07-27 holds disc time (Jul 27 05:00 to Jul 31 00:00) and hold time (Aug 1 00:00 to Aug 3 05:00): both pools
  // sweep it whole, each owning its own matches.
  assert.deepEqual(requestUnits(units, 'disc', '2026-07-27', '2026-07-30').map((u) => u.id), ['W-2026-07-27']);
  assert.throws(() => requestUnits(units, 'hold', '2026-08-01', H_HOLD[1]), /does not cover the start of hold unit W-2026-07-27/);
  assert.deepEqual(requestUnits(units, 'hold', '2026-07-27', H_HOLD[1]).map((u) => u.id), hold.map((u) => u.id));
  // The same rule on the old pool; a start-era span holds no old unit.
  assert.throws(() => requestUnits(units, 'old', '2025-06-17', '2026-04-26'), /does not cover the start of old unit W-2025-06-16/);
  assert.deepEqual(requestUnits(units, 'old', '2025-06-16', '2026-04-26').map((u) => u.id), old.map((u) => u.id));
  assert.throws(() => requestUnits(units, 'old', '2026-05-18', '2026-07-30'), /holds no old unit/);
});

test('poolOf: every pool (out, old, nostart, disc, embargo, hold) at every edge (C9)', () => {
  const pool = (start: number, close = start + 3 * H, startPublished = true, opened?: Set<string>, cutoff?: number) => poolOf({ start, close, startPublished }, units, opened, cutoff);
  // disc (H-DEV): a start-era match closing before DEV_TO (Jul 31 00:00 UTC); nostart without a published start.
  const w = byId.get('W-2026-07-13')!;
  assert.equal(pool(w.start + 2 * DAY), 'disc');
  assert.equal(pool(w.start + 2 * DAY, undefined, false), 'nostart');
  assert.equal(unitOf(w.start + 2 * DAY, units), 'W-2026-07-13');
  // DEV_TO: a match closing 1 ms before it is disc, one closing at it (or after) is embargo (Jul 31 and straddlers).
  assert.equal(pool(DEV_TO - 3 * H, DEV_TO - 1), 'disc');
  assert.equal(pool(DEV_TO - 3 * H, DEV_TO), 'embargo');
  assert.equal(pool(DEV_TO - H, DEV_TO + 2 * H), 'embargo'); // starts Jul 30 23:00, closes Jul 31 02:00
  assert.equal(pool(DEV_TO - H, DEV_TO + 2 * H, false), 'nostart');
  assert.equal(pool(DEV_TO + 12 * H), 'embargo'); // the whole of Jul 31
  // HOLD_FROM: a match starting 1 ms before it is embargo whatever its close; one starting at it is hold (H-HOLD).
  assert.equal(pool(HOLD_FROM - 1, HOLD_FROM + 3 * H), 'embargo');
  assert.equal(pool(HOLD_FROM - 2 * H, HOLD_FROM + H), 'embargo'); // starts Jul 31 22:00, closes Aug 1 01:00
  assert.equal(pool(HOLD_FROM), 'hold');
  assert.equal(pool(HOLD_FROM, undefined, false), 'nostart');
  // A malformed match closing before it starts takes the earlier of its times: never disc or hold across an edge.
  assert.equal(pool(HOLD_FROM + H, DEV_TO - H), 'embargo');
  // The straddling unit W-2026-07-27 holds all three: its matches are pooled by their own times.
  const st = byId.get('W-2026-07-27')!;
  assert.deepEqual([st.start + DAY, DEV_TO + H, HOLD_FROM + DAY].map((t) => [unitOf(t, units), pool(t)]), [['W-2026-07-27', 'disc'], ['W-2026-07-27', 'embargo'], ['W-2026-07-27', 'hold']]);
  // HARD_CUTOFF (Nov 5 02:00 UTC): a hold match must start and close before it.
  assert.equal(pool(HARD_CUTOFF - 3 * H, HARD_CUTOFF - 1), 'hold');
  assert.equal(pool(HARD_CUTOFF - 3 * H, HARD_CUTOFF), 'out');
  assert.equal(pool(HARD_CUTOFF - H, HARD_CUTOFF + H), 'out');
  assert.equal(pool(HARD_CUTOFF, HARD_CUTOFF + H), 'out');
  assert.equal(pool(HARD_CUTOFF - 1, HARD_CUTOFF - 1), 'hold');
  // START_ERA_FROM (a unit edge): a match starting 1 ms before it is old (the last old unit, W-2026-04-20) whatever its
  // close or published start; one starting at it is in the start era.
  assert.equal(pool(START_ERA_FROM - 1, START_ERA_FROM + 3 * H), 'old');
  assert.equal(pool(START_ERA_FROM - 1, START_ERA_FROM + 3 * H, false), 'old');
  assert.equal(unitOf(START_ERA_FROM - 1, units), 'W-2026-04-20');
  assert.equal(pool(START_ERA_FROM), 'disc');
  assert.equal(pool(START_ERA_FROM, undefined, false), 'nostart');
  // old: before the start era a published start does not matter (Kalshi published none then); no seal any more.
  assert.equal(pool(byId.get('W-2025-06-23')!.start + 2 * DAY, undefined, false), 'old');
  assert.equal(pool(byId.get('W-2026-03-02')!.start + 2 * DAY), 'old');
  // HISTORY_FROM: W-2025-06-16 straddles the history start (it was sealed under A3; C9 has no seal).
  assert.equal(pool(HISTORY_FROM - 1), 'out');
  assert.equal(pool(HISTORY_FROM), 'old');
  assert.equal(byId.get('W-2025-06-16')!.sealed, true);
  assert.equal(unitPools(byId.get('W-2025-06-09')!)[0], 'out');
  // Outside the unit table.
  const after = units[units.length - 1].end + DAY;
  assert.equal(poolOf({ start: after, close: after + H, startPublished: true }, units, new Set(['L1', 'L2', 'L3', 'L4']), Infinity), 'out');
  // Lockbox ids: a [start, end) table anchored at LOCKBOX_FROM in 7-day steps.
  assert.equal(lockboxOf(LOCKBOX_FROM - 1), undefined);
  assert.equal(lockboxOf(LOCKBOX_FROM), 'L1');
  assert.equal(lockboxOf(LOCKBOX_FROM + 7 * DAY - 1), 'L1');
  assert.equal(lockboxOf(LOCKBOX_FROM + 7 * DAY), 'L2');
  assert.deepEqual(lockboxes(LOCKBOX_FROM + 8 * DAY).map((l) => [l.id, l.start - LOCKBOX_FROM, l.end - LOCKBOX_FROM]), [['L1', 0, 7 * DAY], ['L2', 7 * DAY, 14 * DAY]]);
  // With a later cutoff (a future round), a match reaching a lockbox week is out unless every week it reaches is opened.
  const cutoff = LOCKBOX_FROM + 30 * DAY;
  const a = LOCKBOX_FROM + 3 * DAY + 12 * H; // Nov 9 17:00 UTC, in L1
  assert.equal(pool(a, a + 3 * H, true, new Set(), cutoff), 'out');
  assert.equal(pool(a, a + 3 * H, true, new Set(['L1']), cutoff), 'hold');
  assert.equal(pool(a, a + 3 * H, false, new Set(['L1']), cutoff), 'nostart');
  const b = LOCKBOX_FROM + 7 * DAY - H; // starts in L1, closes in L2
  assert.equal(pool(b, b + 3 * H, true, new Set(['L1']), cutoff), 'out');
  assert.equal(pool(b, b + 3 * H, true, new Set(['L1', 'L2']), cutoff), 'hold');
});

test('poolSpans: the pool\'s part of every unit, cut to the history, H-DEV or H-HOLD; the embargo day in no pool', () => {
  const sum = (sp: Array<{ hours: number }>) => sp.reduce((x, s) => x + s.hours, 0);
  const d = poolSpans(units, 'disc'), h = poolSpans(units, 'hold'), o = poolSpans(units, 'old');
  assert.deepEqual(d.map((s) => s.unit), disc.map((u) => u.id));
  assert.deepEqual(h.map((s) => s.unit), hold.map((u) => u.id));
  assert.deepEqual(o.map((s) => s.unit), old.map((u) => u.id));
  // disc: Apr 27 05:00 to Jul 31 00:00 UTC; hold: Aug 1 00:00 to Nov 5 02:00 UTC (96 days and 2 h); the embargo day between.
  assert.equal(sum(d), (DEV_TO - START_ERA_FROM) / H);
  assert.equal(sum(h), (HARD_CUTOFF - HOLD_FROM) / H);
  assert.equal(sum(h), 96 * 24 + 2);
  const st = 'W-2026-07-27';
  assert.deepEqual(d.find((s) => s.unit === st)!.intervals, [[byId.get(st)!.start, DEV_TO]]);
  assert.deepEqual(h.find((s) => s.unit === st)!.intervals, [[HOLD_FROM, byId.get(st)!.end]]);
  assert.deepEqual(h[h.length - 1].intervals, [[byId.get('W-2026-11-02')!.start, HARD_CUTOFF]]);
  // Every hour of a span holds the pool: a 1 h match starting there (published) is in it, one without a start is nostart.
  for (const [pool, sp] of [['disc', d], ['hold', h]] as const) for (const s of sp) for (const [a, b] of s.intervals) for (let t = a; t + H < b; t += 6 * H) {
    assert.equal(poolOf({ start: t, close: t + H, startPublished: true }, units), pool, `${s.unit} ${new Date(t).toISOString()}`);
    assert.equal(poolOf({ start: t, close: t + H, startPublished: false }, units), 'nostart');
  }
  for (const s of o) for (const [a] of s.intervals) assert.equal(poolOf({ start: a, close: a + H, startPublished: false }, units), 'old');
  // The old unit straddling the history start counts from HISTORY_FROM only.
  assert.equal(o[0].intervals[0][0], HISTORY_FROM);
  assert.equal(sum(o), (START_ERA_FROM - HISTORY_FROM) / H);
  // The embargo day is the one interval between H-DEV and H-HOLD; 'nostart' and 'out' have no time of their own.
  assert.deepEqual(poolSpans(units, 'embargo').map((s) => [s.unit, s.intervals, s.hours]), [[st, [[DEV_TO, HOLD_FROM]], 24]]);
  assert.deepEqual(poolInterval(byId.get(st)!, 'embargo'), [DEV_TO, HOLD_FROM]);
  for (const pool of ['nostart', 'out'] as Pool[]) assert.deepEqual(poolSpans(units, pool), []);
  assert.equal(sum(d) + sum(poolSpans(units, 'embargo')) + sum(h), (HARD_CUTOFF - START_ERA_FROM) / H);
  assert.deepEqual(poolSpans(units, 'hold', HARD_CUTOFF, new Set([st])).map((s) => s.unit), [st]);
});

test('HO-1 folds: six consecutive folds over H-HOLD with registry.py\'s edges, the last one holding Nov 4', () => {
  assert.deepEqual(H_HOLD, ['2026-08-01', '2026-11-04']);
  assert.equal(HOLD_FOLDS, 6);
  assert.deepEqual(holdFoldEdges(), ['2026-08-01', '2026-08-17', '2026-09-02', '2026-09-18', '2026-10-04', '2026-10-20', '2026-11-05']);
  assert.deepEqual(holdFolds().map((f) => [f.fold, f.from, f.to]), [[1, '2026-08-01', '2026-08-16'], [2, '2026-08-17', '2026-09-01'], [3, '2026-09-02', '2026-09-17'],
    [4, '2026-09-18', '2026-10-03'], [5, '2026-10-04', '2026-10-19'], [6, '2026-10-20', '2026-11-04']]);
  const days: string[] = [];
  for (let t = Date.parse(H_HOLD[0]); t <= Date.parse(H_HOLD[1]); t += DAY) days.push(new Date(t).toISOString().slice(0, 10));
  assert.equal(days.length, 96);
  const f = days.map(holdFold);
  assert.ok(f.every((x, i) => x !== null && (i === 0 || x >= f[i - 1]!)), 'folds are consecutive');
  assert.deepEqual([1, 2, 3, 4, 5, 6].map((k) => f.filter((x) => x === k).length), [16, 16, 16, 16, 16, 16]);
  assert.deepEqual([holdFold('2026-07-31'), holdFold('2026-11-05'), holdFold('2026-11-04'), holdFold('2026-08-01')], [null, null, 6, 1]);
  // The same mapping as research/registry.py: its H_HOLD and edge formula reproduced in Python for every hold day, and its
  // own ho1_fill seeing each fold of ours as exactly one of its folds (and all 96 days as six).
  const reg = process.env.TENNIS_TA_REGISTRY_PY ?? '/tmp/registry.py';
  if (!fs.existsSync(reg)) return; // the report job fetches it there; locally set TENNIS_TA_REGISTRY_PY
  const py = `
import importlib.util, json, sys
from datetime import date, timedelta
spec = importlib.util.spec_from_file_location('registry', sys.argv[1])
reg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reg)
d0, d1 = date.fromisoformat(reg.H_HOLD[0]), date.fromisoformat(reg.H_HOLD[1])
span = (d1 - d0).days + 1
edges = [d0 + timedelta(days=round(i * span / 6)) for i in range(7)]
fold = {}
d = d0
while d <= d1:
    k = [i for i in range(6) if edges[i] <= d < edges[i + 1]]
    fold[d.isoformat()] = k[0] + 1 if k else (6 if d == d1 else None)
    d += timedelta(days=1)
ours = json.loads(sys.argv[2])
def probe(ds):
    c = {'trial_id': 'c', 'role': 'control', 'family': 'f', 'arm': 'c', 'data': {'source': 'history'}, 'by_day': {x: 0.0 for x in ds}}
    r = {'trial_id': 'r', 'role': 'candidate', 'control': 'c', 'family': 'f', 'arm': 'r', 'data': {'source': 'history'}, 'by_day': {x: 1.0 for x in ds}}
    reg.ho1_fill([c, r])
    return r['heldout']
per = [probe([x for x, k in ours.items() if k == f]) for f in range(1, 7)]
allh = probe(list(ours) + ['2026-07-31', '2026-11-05'])
print(json.dumps({'hold': list(reg.H_HOLD), 'fold': fold, 'perFold': [[h['days'], h['folds']] for h in per], 'all': [allh['days'], allh['folds']]}))
`;
  const ours = Object.fromEntries(days.map((x, i) => [x, f[i]]));
  const r = spawnSync('python3', ['-I', '-c', py, reg, JSON.stringify(ours)], { encoding: 'utf8' });
  assert.equal(r.status, 0, r.stderr.slice(-2000));
  const out = JSON.parse(r.stdout) as { hold: string[]; fold: Record<string, number | null>; perFold: number[][]; all: number[] };
  assert.deepEqual(out.hold, [...H_HOLD]);
  for (const x of days) assert.equal(holdFold(x), out.fold[x], x);
  assert.deepEqual(out.perFold, [[16, 1], [16, 1], [16, 1], [16, 1], [16, 1], [16, 1]]);
  assert.deepEqual(out.all, [96, 6]);
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
  // Every stage 1 id carries its arm, as stage 2's must.
  assert.ok(s.every((x) => x.id.endsWith(x.placebo ? '|coin' : `|${x.fill}`)));
  assert.ok(s.some((x) => x.id === 'A|s1|m0.01|f0.2|o0.01|w60|F1'), 'production\'s grid point (the registry control)');
  assert.throws(() => specsFor('1', 'R'), /H design/);
});

test('stage 2 specs: validated, ratchet forced off on H, clear failures', () => {
  const ok = validateStage2Specs([
    { id: 'A|s2|a|F1', overrides: { TENNIS_ENTRY_MIN_SIGNALS_PRE: 0 }, fill: 'F1' },
    { id: 'A|s2|a|F2', overrides: { TENNIS_ENTRY_MIN_SIGNALS_PRE: 0 }, fill: 'F2' },
    { id: 'A|s2|a|coin', overrides: { TENNIS_ENTRY_MIN_SIGNALS_PRE: 0 }, fill: 'F1', placebo: 'coin' },
    { id: 'A|s2|prod|settlehold|F1', overrides: { TENNIS_END_LOSER_CUT: false }, fill: 'F1', stick: true, offsetMs: 2500 },
  ]);
  assert.equal(ok.length, 4);
  assert.ok(ok.every((x) => x.overrides.TENNIS_TRAIL_RATCHET === false));
  assert.equal(ok[3].stick, true);
  assert.equal(ok[3].offsetMs, 2500);
  assert.equal(validateStage2Specs([{ id: 'A|s2|r|F0', overrides: {}, fill: 'F0' }], 'R')[0].overrides.TENNIS_TRAIL_RATCHET, undefined);
  const bad = (x: unknown, re: RegExp) => assert.throws(() => validateStage2Specs(x), re);
  bad({}, /JSON array/);
  bad([], /empty/);
  bad([{ id: 'A|s1|x|F1', overrides: {}, fill: 'F1' }], /starting 'A\|s2\|'/);
  bad([{ id: 'A|s2|x|F1', overrides: {}, fill: 'F1' }, { id: 'A|s2|x|F1', overrides: {}, fill: 'F1' }], /duplicate id/);
  bad([{ id: 'A|s2|x|F3', overrides: {}, fill: 'F3' }], /fill must be/);
  bad([{ id: 'A|s2|x|F1', overrides: {}, fill: 'F1', placebo: 'shift' }], /placebo/);
  bad([{ id: 'A|s2|x|F1', overrides: { HARNESS_LOSER_CUT: false }, fill: 'F1' }], /HARNESS_LOSER_CUT no longer exists/);
  bad([{ id: 'A|s2|x|F1', overrides: { TENNIS_TRAIL_RATCHET: true }, fill: 'F1' }], /must be off on H/);
  bad([{ id: 'A|s2|x|F1', overrides: { conf: 1 }, fill: 'F1' }], /not a TENNIS_\*/);
  bad([{ id: 'A|s2|x|F1', overrides: { TENNIS_CONF_FLOW: [1] }, fill: 'F1' }], /string, finite number or boolean/);
  bad([{ id: 'A|s2|x|F1', overrides: {}, fill: 'F1', extra: 1 }], /unknown key extra/);
  // The arm suffix agrees with fill and placebo; a config and an arm are both named.
  bad([{ id: 'A|s2|x', overrides: {}, fill: 'F1' }], /id must be 'A\|s2\|<config>\|<arm>' with the arm \|F1/);
  bad([{ id: 'A|s2|F1', overrides: {}, fill: 'F1' }], /id must be 'A\|s2\|<config>\|<arm>'/);
  bad([{ id: 'A|s2|x|F2', overrides: {}, fill: 'F1' }], /id ends \|F2 but the spec is fill F1 \(\|F1\)/);
  bad([{ id: 'A|s2|a|F1', overrides: { TENNIS_ENTRY_MIN_SIGNALS_PRE: 0 }, fill: 'F1' }, { id: 'A|s2|a|F1x', overrides: { TENNIS_ENTRY_MIN_SIGNALS_PRE: 0 }, fill: 'F1', placebo: 'coin' }], /with the arm \|coin/);
  bad([{ id: 'A|s2|x|F1', overrides: {}, fill: 'F1' }, { id: 'A|s2|x|coin', overrides: {}, fill: 'F2' }], /x\|coin/);
  // Sticks: stick: true and the 'A|s2|prod|<name>|<fill>' form go together; a stick has no placebo.
  bad([{ id: 'A|s2|prod|nopacer|F1', overrides: { HARNESS_PACER: 'off' }, fill: 'F1' }], /are measuring sticks: set stick: true/);
  bad([{ id: 'A|s2|nopacer|F1', overrides: { HARNESS_PACER: 'off' }, fill: 'F1', stick: true }], /a measuring stick's id is 'A\|s2\|prod\|<name>\|<fill>'/);
  bad([{ id: 'A|s2|prod|c|coin', overrides: {}, fill: 'F1', placebo: 'coin', stick: true }], /a measuring stick has no placebo arm/);
  // F2 and coin arms need their config's F1 arm, with the same overrides.
  bad([{ id: 'A|s2|a|coin', overrides: { TENNIS_ENTRY_MIN_SIGNALS_PRE: 0 }, fill: 'F1', placebo: 'coin' }], /its config has no F1 arm \(A\|s2\|a\|F1\)/);
  bad([{ id: 'A|s2|a|F1', overrides: { TENNIS_ENTRY_MIN_SIGNALS_PRE: 0 }, fill: 'F1' }, { id: 'A|s2|a|F2', overrides: { TENNIS_ENTRY_MIN_SIGNALS_PRE: 1 }, fill: 'F2' }], /A\|s2\|a\|F2: overrides differ from A\|s2\|a\|F1's/);
  // Every arm of a config (F0 too) runs the same overrides as written, value types included (the report compares JSON),
  // at one clock phase.
  const f1 = { id: 'A|s2|x|F1', overrides: { TENNIS_CONF_FLOW: 0.4 }, fill: 'F1' };
  bad([f1, { id: 'A|s2|x|F2', overrides: { TENNIS_CONF_FLOW: '0.4' }, fill: 'F2' }], /A\|s2\|x\|F2: overrides differ from A\|s2\|x\|F1's \(TENNIS_CONF_FLOW "0.4" vs 0.4\)/);
  bad([f1, { id: 'A|s2|x|F0', overrides: { TENNIS_CONF_FLOW: 0.05 }, fill: 'F0' }], /A\|s2\|x\|F0: overrides differ/);
  bad([{ id: 'A|s2|x|F0', overrides: { TENNIS_CONF_FLOW: 0.4 }, fill: 'F0' }, { id: 'A|s2|x|F2', overrides: { TENNIS_CONF_FLOW: 0.05 }, fill: 'F2' }], /no F1 arm[\s\S]*overrides differ from A\|s2\|x\|F0's/);
  bad([f1, { id: 'A|s2|x|coin', overrides: { TENNIS_CONF_FLOW: 0.4 }, fill: 'F1', placebo: 'coin', offsetMs: 1000 }], /offsetMs 1000 differs from A\|s2\|x\|F1's 0/);
  // The ratchet is written as the boolean false however a spec spells it, so a config's arms carry it alike.
  const r1 = validateStage2Specs([{ ...f1, overrides: { TENNIS_CONF_FLOW: 0.4, TENNIS_TRAIL_RATCHET: 'false' } }, { id: 'A|s2|x|coin', overrides: { TENNIS_CONF_FLOW: 0.4 }, fill: 'F1', placebo: 'coin' },
    { id: 'A|s2|x|F0', overrides: { TENNIS_CONF_FLOW: 0.4, TENNIS_TRAIL_RATCHET: '0' }, fill: 'F0' }]);
  assert.ok(r1.every((x) => x.overrides.TENNIS_TRAIL_RATCHET === false));
  // Stress adversaries and measuring settings are never hypotheses: only a stick moves one off its default.
  for (const [k, v] of [['HARNESS_LATENCY_MS', 500], ['HARNESS_FEE_MULT', 2], ['HARNESS_PACER', 'off'], ['HARNESS_BANKROLL', 400], ['TENNIS_END_LOSER_CUT', false], ['TENNIS_END_LOSER_CUT', '0']] as const)
    bad([{ id: 'A|s2|x|F1', overrides: { TENNIS_CONF_FLOW: 0.4, [k]: v }, fill: 'F1' }], new RegExp(`override ${k}=${JSON.stringify(v)} is a stress adversary or measuring setting`));
  assert.equal(validateStage2Specs([{ id: 'A|s2|x|F1', overrides: { TENNIS_CONF_FLOW: 0.4, HARNESS_FEE_MULT: '1', HARNESS_PACER: 'tennis' }, fill: 'F1' }]).length, 1);
  // A stick runs production plus measuring settings (and HARNESS_LOSER_STOP, the ratchet off on H, offsetMs) only.
  bad([{ id: 'A|s2|prod|x|F1', overrides: { TENNIS_CONF_FLOW: 0.4 }, fill: 'F1', stick: true }], /override TENNIS_CONF_FLOW is not a measuring setting/);
  bad([{ id: 'A|s2|prod|x|F1', overrides: { PACER_HOURLY_USD: 3, HARNESS_PACER: 'off' }, fill: 'F1', stick: true }], /override PACER_HOURLY_USD is not a measuring setting/);
  assert.throws(() => validateStage2Specs([{ id: 'A|s2|prod|x|F1', overrides: { TENNIS_TRAIL_RATCHET: false }, fill: 'F1', stick: true }], 'R'), /TENNIS_TRAIL_RATCHET is not a measuring setting/);
  assert.equal(validateStage2Specs([{ id: 'A|s2|prod|ls|F1', overrides: { HARNESS_LOSER_STOP: 0.5, TENNIS_TRAIL_RATCHET: false }, fill: 'F1', stick: true },
    { id: 'A|s2|prod|lat|F1', overrides: { HARNESS_LATENCY_MS: 500, HARNESS_FEE_MULT: 1.25 }, fill: 'F1', stick: true }]).length, 2);
  // Two hypotheses that differ only in the clock phase are a noise floor: sticks at production; identical arms are twins.
  bad([f1, { ...f1, id: 'A|s2|xph|F1', offsetMs: 2500 }], /A\|s2\|xph\|F1\): runs as A\|s2\|x\|F1 at another decision-clock offset only \(2500 ms, 0 ms there\)/);
  bad([{ id: 'A|s2|base|F1', overrides: {}, fill: 'F1' }, { id: 'A|s2|prod|ph0|F1', overrides: {}, fill: 'F1', stick: true }], /runs exactly as A\|s2\|base\|F1/);
  bad([{ id: 'A|s2|prod|a|F1', overrides: {}, fill: 'F1', stick: true, offsetMs: 1000 }, { id: 'A|s2|prod|b|F1', overrides: {}, fill: 'F1', stick: true, offsetMs: 1000 }], /runs exactly as A\|s2\|prod\|a\|F1/);
  const noise = validateStage2Specs([{ id: 'A|s2|base|F1', overrides: {}, fill: 'F1' }, ...[1000, 2000, 3000, 4000].map((off) => ({ id: `A|s2|prod|phase${off}|F1`, overrides: {}, fill: 'F1', stick: true, offsetMs: off }))]);
  assert.deepEqual(noise.map((x) => x.offsetMs ?? 0), [0, 1000, 2000, 3000, 4000]);
  // Unknown keys are listed whatever else is wrong; a key at its default (or outside what the sim runs) is refused.
  assert.throws(() => validateStage2Specs([{ id: 'A|s2|x|F1', overrides: { TENNIS_FOO_BAR: 1, HARNESS_PACER: 'x', HARNESS_FOO: 1 }, fill: 'F1' }]),
    (e: Error) => /TENNIS_FOO_BAR is not a key production's loadConfig reads/.test(e.message) && /HARNESS_PACER="x" must be/.test(e.message) && /HARNESS_FOO is not a harness rule/.test(e.message));
  bad([{ id: 'A|s2|x|F1', overrides: { TENNIS_CONF_FLOW: 0.2, TENNIS_CONF_MOMENTUM_CENTS: 0.02 }, fill: 'F1' }], /TENNIS_CONF_FLOW=0.2 changes nothing the sim runs/);
  bad([{ id: 'A|s2|x|F1', overrides: { TENNIS_CONF_FLOW: 0.2 }, fill: 'F1' }], /leave the simulated config at production's/);
  bad([{ id: 'A|s2|x|F1', overrides: { TENNIS_CONF_FLOW: 'abc' }, fill: 'F1' }], /loadConfig refuses the overrides/);
  bad([{ id: 'A|s2|prod|x|F1', overrides: { HARNESS_FEE_MULT: 2 }, fill: 'F1', stick: true }, { id: 'A|s2|prod|y|F1', overrides: { HARNESS_FEE_MULT: '2' }, fill: 'F1', stick: true }], /runs exactly as A\|s2\|prod\|x\|F1/);
  bad([{ id: 'A|s2|x|F1', overrides: { TENNIS_CONF_FLOW: 0.4 }, fill: 'F1' }, { id: 'A|s2|y|F1', overrides: { TENNIS_CONF_FLOW: '0.4' }, fill: 'F1' }], /runs exactly as A\|s2\|x\|F1/);
  const dir = tmp();
  assert.throws(() => specsFor('2', 'H', path.join(dir, 'stage2-specs.json')), /does not exist/);
  fs.writeFileSync(path.join(dir, 'stage2-specs.json'), '[{"id": "A|s2|x|F1", "overrides": {}, "fill": "F1"}]');
  assert.equal(specsFor('2', 'H', path.join(dir, 'stage2-specs.json')).length, 1);
  fs.writeFileSync(path.join(dir, 'bad.json'), '[{');
  assert.throws(() => specsFor('2', 'H', path.join(dir, 'bad.json')), /not valid JSON/);
  assert.throws(() => specsFor('3', 'H'), /stage must be/);
});

test('stage 2 keys: the TENNIS_* / PACER_* keys are bot/config.ts\'s, the HARNESS_* keys the sim\'s', () => {
  const config = fs.readFileSync(path.join(REPO, 'bot', 'config.ts'), 'utf8');
  const keys = configKeys();
  assert.ok(['TENNIS_CONF_FLOW', 'TENNIS_END_LOSER_CUT', 'TENNIS_TRAIL_RATCHET', 'TENNIS_END_ENTRY_MARGIN'].every((k) => keys.has(k)));
  // Every key loadConfig reads is named in bot/config.ts, and every key it names in quotes is read.
  for (const k of keys) assert.ok(new RegExp(`\\b${k}\\b`).test(config), `${k} is read but not named in bot/config.ts`);
  for (const m of config.matchAll(/'((?:TENNIS|PACER)_[A-Z0-9_]+)'/g)) assert.ok(keys.has(m[1]), `bot/config.ts names ${m[1]} but loadConfig does not read it`);
  // The harness rules are exactly the HARNESS_* keys the sim reads from a spec's overrides, and the ones SimSpec documents.
  const sim = fs.readFileSync(path.join(REPO, 'research', 'tennisTaSim.ts'), 'utf8');
  const reads = new Set([...sim.matchAll(/overrides\.(HARNESS_[A-Z0-9_]+)/g)].map((m) => m[1]));
  assert.deepEqual([...reads].sort(), Object.keys(HARNESS_RULES).sort());
  const doc = sim.slice(sim.indexOf('export interface SimSpec'), sim.indexOf('overrides: Record<string', sim.indexOf('export interface SimSpec')));
  for (const k of Object.keys(HARNESS_RULES)) assert.ok(doc.includes(k), `SimSpec does not document ${k}`);
});

// The report's own reading of a spec list: research/tennis_ta_report.py read_shard on a shard file whose runs[] are built
// as cmdRun builds them (the sim's run fields, then runTags), then check_runs, the fatal gate before anything is scored.
const CHECK_RUNS = `
import importlib.util, json, os, sys
spec = importlib.util.spec_from_file_location('tennis_ta_report', sys.argv[1])
rep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rep)
out = {'stickKeys': rep.STICK_KEYS, 'lists': {}}
for f in sorted(os.listdir(sys.argv[2])):
    info, data = rep.read_shard(os.path.join(sys.argv[2], f))
    out['lists'][f[:-len('.json.gz')]] = info['problems'] + rep.check_runs([data['runs']], info['meta'].get('stratum') or 'H')
print(json.dumps(out))
`;

function reportCheckRuns(lists: Record<string, { specs: SweepSpec[]; stratum: 'H' | 'R' }>): { status: number | null; out?: { stickKeys: Record<string, unknown>; lists: Record<string, string[]> }; err: string } {
  const dir = tmp(), shards = path.join(dir, 'shards');
  fs.mkdirSync(shards);
  for (const [name, { specs, stratum }] of Object.entries(lists)) {
    const tags = runTags(specs);
    // ConfigSim.run()'s fields (tennisTaSim.ts), then cmdRun's tags.
    const runs = specs.map((s) => ({ id: s.id, overrides: s.overrides, fill: s.fill, ...(s.placebo ? { placebo: s.placebo } : {}), stratum, days: [], pnl: [], episodes: [], ...tags.get(s.id) }));
    const meta = { stratum, sticks: specs.filter((s) => s.stick).map((s) => s.id) };
    fs.writeFileSync(path.join(shards, `${name}.json.gz`), zlib.gzipSync(JSON.stringify({ meta, matchList: [], runs })));
  }
  return checkRunsDir(shards);
}

/** read_shard + check_runs of research/tennis_ta_report.py on every shard file in a directory. */
function checkRunsDir(shards: string): { status: number | null; out?: { stickKeys: Record<string, unknown>; lists: Record<string, string[]> }; err: string } {
  const dir = tmp();
  fs.writeFileSync(path.join(dir, 'check_runs.py'), CHECK_RUNS);
  const r = spawnSync('python3', ['-I', path.join(dir, 'check_runs.py'), path.join(REPO, 'research', 'tennis_ta_report.py'), shards], { encoding: 'utf8' });
  let out;
  try { out = JSON.parse(r.stdout); } catch { /* none */ }
  return { status: r.status, out, err: r.stderr };
}

test('stage 2 specs the sweep accepts pass the report\'s check_runs; what it refuses there, the sweep refuses at prep', (t) => {
  const probe = spawnSync('python3', ['-I', '-c', 'import numpy, scipy'], { encoding: 'utf8' });
  if (probe.status !== 0) { t.skip('python3 with numpy and scipy is not available'); return; }
  const v = (x: unknown[], stratum: 'H' | 'R' = 'H') => ({ specs: validateStage2Specs(x, stratum), stratum });
  const cfg = (name: string, o: Record<string, unknown>, arms = ['F0', 'F1', 'F2', 'coin'], extra: Record<string, unknown> = {}) =>
    arms.map((a) => ({ id: `A|s2|${name}|${a}`, overrides: o, fill: a === 'coin' ? 'F1' : a, ...(a === 'coin' ? { placebo: 'coin' } : {}), ...extra }));
  const accepted = {
    stage1: { specs: stage1Specs(), stratum: 'H' as const },
    rich: v([...cfg('a', { TENNIS_ENTRY_MIN_SIGNALS_PRE: 0 }), ...cfg('b', { TENNIS_CONF_FLOW: 0.4, HARNESS_FEE_MULT: '1', HARNESS_LOSER_STOP: 0.5 }),
      ...cfg('c', { TENNIS_END_ENTRY_MARGIN: 0.1 }, ['F1', 'F2'], { offsetMs: 1500 }),
      { id: 'A|s2|prod|settlehold|F1', overrides: { TENNIS_END_LOSER_CUT: false }, fill: 'F1', stick: true, offsetMs: 2500 },
      { id: 'A|s2|prod|nopacer|F1', overrides: { HARNESS_PACER: 'off' }, fill: 'F1', stick: true },
      { id: 'A|s2|prod|stress|F2', overrides: { HARNESS_LATENCY_MS: 2000, HARNESS_FEE_MULT: 1.25 }, fill: 'F2', stick: true },
      { id: 'A|s2|prod|bank|F1', overrides: { HARNESS_BANKROLL: 400, HARNESS_LOSER_STOP: 0.5 }, fill: 'F1', stick: true }]),
    // The ratchet spelt 'false' in one arm and left unset in another (the sweep writes it as false in both).
    ratchet: v([{ id: 'A|s2|x|F1', overrides: { TENNIS_CONF_FLOW: 0.4, TENNIS_TRAIL_RATCHET: 'false' }, fill: 'F1' }, { id: 'A|s2|x|coin', overrides: { TENNIS_CONF_FLOW: 0.4 }, fill: 'F1', placebo: 'coin' }]),
    noise: v([{ id: 'A|s2|base|F1', overrides: {}, fill: 'F1' }, ...[1000, 2000, 3000, 4000].map((off) => ({ id: `A|s2|prod|phase${off}|F1`, overrides: {}, fill: 'F1', stick: true, offsetMs: off }))]),
    recorded: v([...cfg('r', {}, ['F0', 'F1', 'F2']), ...cfg('d', { TENNIS_CONF_FLOW: 0.4 }, ['F1', 'coin']), { id: 'A|s2|prod|hold|F1', overrides: { TENNIS_END_LOSER_CUT: false }, fill: 'F1', stick: true }], 'R'),
  };
  // The verifier's lists that check_runs refuses (H: the sweep would add the ratchet off where unset).
  const off = { TENNIS_TRAIL_RATCHET: false };
  const refused: Record<string, unknown[]> = {
    latency: [{ id: 'A|s2|lat|F1', overrides: { HARNESS_LATENCY_MS: 500, ...off }, fill: 'F1' }],
    feeMult: [{ id: 'A|s2|fee2|F1', overrides: { TENNIS_CONF_FLOW: 0.4, HARNESS_FEE_MULT: 2, ...off }, fill: 'F1' }],
    settleHold: [{ id: 'A|s2|hold|F1', overrides: { TENNIS_END_LOSER_CUT: false, ...off }, fill: 'F1' }],
    strNum: [{ id: 'A|s2|x|F1', overrides: { TENNIS_CONF_FLOW: 0.4, ...off }, fill: 'F1' }, { id: 'A|s2|x|F2', overrides: { TENNIS_CONF_FLOW: '0.4', ...off }, fill: 'F2' }],
    f0Differs: [{ id: 'A|s2|x|F1', overrides: { TENNIS_CONF_FLOW: 0.4, ...off }, fill: 'F1' }, { id: 'A|s2|x|F0', overrides: { TENNIS_CONF_FLOW: 0.05, ...off }, fill: 'F0' }],
  };
  for (const [k, l] of Object.entries(refused)) assert.throws(() => validateStage2Specs(l), /stage 2 specs: \d+ problem/, k);
  const r = reportCheckRuns({ ...accepted, ...Object.fromEntries(Object.entries(refused).map(([k, l]) => [`refused-${k}`, { specs: l as SweepSpec[], stratum: 'H' as const }])) });
  assert.equal(r.status, 0, r.err.slice(-2000));
  for (const k of Object.keys(accepted)) assert.deepEqual(r.out!.lists[k], [], k);
  for (const k of Object.keys(refused)) assert.ok(r.out!.lists[`refused-${k}`].length > 0, `check_runs accepts ${k}: the harness is not reading the runs`);
  // The sweep's stick keys are the report's.
  assert.deepEqual(r.out!.stickKeys, STICK_KEYS);
  // Each runs[] entry carries its spec's offsetMs (the report's twin and cross-file checks read it).
  assert.deepEqual(runTags(accepted.noise.specs).get('A|s2|prod|phase3000|F1'), { stick: true, offsetMs: 3000 });
  assert.deepEqual(runTags(accepted.noise.specs).get('A|s2|base|F1'), {});
});

test('requests: pool disc, old at stage 2, hold at stage hold only; defaults; other pools and unknown keys refused', () => {
  const r = parseRequest({ stage: 1 }, units);
  assert.deepEqual(r, { stage: '1', pool: 'disc', from: '2026-04-27', to: '2026-07-30', shards: 8, familyB: false });
  assert.deepEqual(parseRequest({ stage: '2', pool: 'old' }, units), { stage: '2', pool: 'old', from: '2025-06-16', to: '2026-04-26', shards: 8, familyB: false });
  assert.throws(() => parseRequest({ stage: '1', pool: 'old' }, units), /stress test for stage 2 finalists only/);
  // hold: stage hold only, the whole block, no family B.
  assert.deepEqual(parseRequest({ stage: 'hold' }, units), { stage: 'hold', pool: 'hold', from: '2026-07-27', to: '2026-11-04', shards: 8, familyB: false });
  assert.deepEqual(parseRequest({ stage: 'hold', pool: 'hold', from: '2026-07-27', to: '2026-11-04', shards: 4 }, units).shards, 4);
  for (const stage of ['1', '2']) assert.throws(() => parseRequest({ stage, pool: 'hold' }, units), /pool 'hold' \(H-HOLD, 2026-08-01 to 2026-11-04\) is scored only by stage 'hold'/);
  for (const pool of ['disc', 'old']) assert.throws(() => parseRequest({ stage: 'hold', pool }, units), /stage 'hold' scores pool 'hold' \(H-HOLD\) only/);
  assert.throws(() => parseRequest({ stage: 'hold', from: '2026-08-03' }, units), /scores the whole of H-HOLD once/);
  assert.throws(() => parseRequest({ stage: 'hold', to: '2026-10-19' }, units), /scores the whole of H-HOLD once/);
  assert.throws(() => parseRequest({ stage: 'hold', familyB: true }, units), /familyB is a discovery design/);
  // The retired pools, and those never scored.
  assert.throws(() => parseRequest({ stage: '1', pool: 'check' }, units), /pool 'check' no longer exists/);
  assert.throws(() => parseRequest({ stage: '2', pool: 'sealed' }, units), /pool 'sealed' no longer exists/);
  for (const pool of ['nostart', 'embargo', 'out']) assert.throws(() => parseRequest({ stage: '2', pool }, units), /is never scored/);
  assert.throws(() => parseRequest({ stage: '1', pool: 'disc,hold' }, units), /pool must be 'disc', 'old' \(stage 2\) or 'hold' \(stage hold\)/);
  assert.throws(() => parseRequest({ stage: '1', familyb: true }, units), /unknown key familyb/);
  assert.throws(() => parseRequest({ stage: '1', familyB: 'yes' }, units), /familyB must be/);
  assert.throws(() => parseRequest({ stage: '1', from: '2025-02-30' }, units), /from must be/);
  assert.throws(() => parseRequest({ stage: '1', from: '2026-07-01', to: '2026-06-01' }, units), /is after to/);
  assert.throws(() => parseRequest({ stage: '1', shards: 0 }, units), /shards/);
  assert.throws(() => parseRequest({ stage: '4' }, units), /stage must be 1, 2 or hold/);
  assert.equal(assertPool('old', '2'), 'old');
  assert.equal(assertPool('hold', 'hold'), 'hold');
  assert.throws(() => assertPool('old', '1'), /stage 2 finalists only/);
  assert.throws(() => assertPool('hold', '2'), /scored only by stage 'hold'/);
  assert.throws(() => assertPool('disc', 'hold'), /scores pool 'hold'/);
  assert.throws(() => assertPool('check'), /no longer exists/);
});

function prepOf(req: object, specs?: string, openings?: string): Prep {
  return prepare(JSON.stringify(req), unitsText, specs, { openings });
}

function specFile(): string {
  const f = path.join(tmp(), 'stage2-specs.json');
  fs.writeFileSync(f, JSON.stringify([
    { id: 'A|s2|loose|F1', overrides: { TENNIS_ENTRY_MIN_SIGNALS_PRE: 0, TENNIS_ENTRY_MIN_SIGNALS_LIVE: 0, TENNIS_FAV_ENTRY_MIN_SIGNALS: 0 }, fill: 'F1' },
    { id: 'A|s2|prod|nopacer|F1', overrides: { HARNESS_PACER: 'off' }, fill: 'F1', stick: true, offsetMs: 1500 },
  ]));
  return f;
}

/** A frozen hold list: one candidate with its F2 neighbour and coin placebo, and the production-default F1 control. */
const HOLD_LIST = [
  { id: 'A|hold|loose|F1', overrides: { TENNIS_ENTRY_MIN_SIGNALS_PRE: 0, TENNIS_CONF_FLOW: 0.4 }, fill: 'F1' },
  { id: 'A|hold|loose|F2', overrides: { TENNIS_ENTRY_MIN_SIGNALS_PRE: 0, TENNIS_CONF_FLOW: 0.4 }, fill: 'F2' },
  { id: 'A|hold|loose|coin', overrides: { TENNIS_ENTRY_MIN_SIGNALS_PRE: 0, TENNIS_CONF_FLOW: 0.4 }, fill: 'F1', placebo: 'coin' },
  { id: 'A|hold|prod|F1', overrides: {}, fill: 'F1' },
];

function holdFile(list: unknown = HOLD_LIST, text?: string): string {
  const f = path.join(tmp(), 'hold-specs.json');
  fs.writeFileSync(f, text ?? JSON.stringify(list));
  return f;
}

test('prepare: plan, sub-plans and expected files; refuses a request that cuts a unit, names another pool or lacks stage 2 specs', () => {
  const p = prepOf({ stage: '1', pool: 'disc', from: '2026-04-27', to: '2026-07-30', shards: 8, familyB: true });
  assert.equal(p.configs, 245);
  assert.equal(p.plan.length, 8);
  assert.equal(p.subPlans.length, 8);
  assert.deepEqual(p.units, disc.map((u) => u.id));
  assert.equal(p.expected.length, p.subPlans.reduce((s, x) => s + x.length, 0));
  assert.equal(new Set(p.expected).size, p.expected.length);
  assert.equal(p.expected[0], shardFile('1', 0, 0));
  assert.deepEqual(p.subPlans.flat().flatMap((s) => s.units), p.units);
  assert.equal(p.poolSpans.length, 11);
  assert.equal(p.poolSpans.reduce((x, s) => x + s.hours, 0), (DEV_TO - START_ERA_FROM) / H);
  assert.equal(p.familyB, true);
  assert.equal(p.simVersion, SIM_VERSION);
  assert.equal(p.replayVersion, REPLAY_VERSION);
  assert.equal(p.replayVersion, 8);
  assert.equal(p.stratumLabel, 'H');
  assert.deepEqual(p.era, { historyFrom: '2025-06-18T00:00:00.000Z', startEraFrom: '2026-04-27T05:00:00.000Z', devTo: '2026-07-31T00:00:00.000Z', holdFrom: '2026-08-01T00:00:00.000Z', cutoff: '2026-11-05T02:00:00.000Z' });
  assert.deepEqual(p.holdFolds, holdFolds());
  assert.deepEqual(p.poolUnits, { out: 23, old: 40, disc: 11, embargo: 1, hold: 13 });
  assert.equal(p.specsHash, specsHash(stage1Specs()));
  assert.deepEqual(p.specIds, stage1Specs().map((x) => x.id));
  assert.equal(p.openingsRead, undefined);
  // The old pool (stage 2 finalists): the same from/to rule, stratum H0.
  const specs = specFile();
  const po = prepOf({ stage: '2', pool: 'old', shards: 4 }, specs);
  assert.deepEqual([po.pool, po.stratumLabel, po.units.length, po.plan.length], ['old', 'H0', 40, 4]);
  assert.ok(po.poolSpans.every((s) => unitPools(byId.get(s.unit)!).includes('old')));
  assert.throws(() => prepOf({ stage: '2', pool: 'old', from: '2025-06-25', to: '2026-04-26' }, specs), /W-2025-06-23/);
  // Refusals: a cut unit, every other pool, old at stage 1, missing stage 2 specs, a damaged unit table.
  assert.throws(() => prepOf({ stage: '1', from: '2026-05-20', to: '2026-07-30' }), /RG-2026-05-18/);
  for (const pool of ['check', 'sealed']) assert.throws(() => prepOf({ stage: '2', pool }, specs), /no longer exists/);
  for (const pool of ['nostart', 'embargo', 'out']) assert.throws(() => prepOf({ stage: '2', pool }, specs), /never scored/);
  assert.throws(() => prepOf({ stage: '2', pool: 'hold' }, specs), /scored only by stage 'hold'/);
  assert.throws(() => prepOf({ stage: '1', pool: 'old' }), /stage 2 finalists only/);
  assert.throws(() => prepOf({ stage: '2' }, path.join(tmp(), 'none.json')), /stage 2 reads its spec list/);
  assert.throws(() => prepare(JSON.stringify({ stage: '1' }), JSON.stringify(units.map((u, i) => (i === 7 ? { ...u, end: u.end + H } : u)))), /Monday 05:00 UTC/);
});

test('prepare, stage hold: the frozen list scored once on the whole hold block; a reopened hash is refused', () => {
  const f = holdFile();
  const p = prepOf({ stage: 'hold', shards: 4 }, f, '');
  assert.deepEqual([p.stage, p.pool, p.stratumLabel, p.configs, p.openingsRead], ['hold', 'hold', 'H', 4, 0]);
  assert.deepEqual(p.units, hold.map((u) => u.id));
  assert.equal(p.plan.length, 4);
  assert.equal(p.expected[0], 'a-shold-0-0.json.gz');
  assert.equal(p.poolSpans.reduce((x, s) => x + s.hours, 0), 96 * 24 + 2);
  assert.deepEqual(p.specIds, HOLD_LIST.map((x) => x.id));
  const specs = validateHoldSpecs(HOLD_LIST);
  assert.equal(p.specsHash, specsHash(specs));
  assert.match(p.specsHash, /^[0-9a-f]{64}$/);
  // The openings ledger: required, read strictly, and a hash already in it is refused.
  assert.throws(() => prepOf({ stage: 'hold' }, f), /stage hold needs the openings ledger/);
  const row = (hash: string, run = '41') => JSON.stringify({ hash, run, ts: '2026-11-06T03:00:00Z', ids: p.specIds, pool: 'hold' });
  assert.throws(() => prepOf({ stage: 'hold' }, f, `${row('ab'.repeat(32))}\n${row(p.specsHash)}\n`), /was already opened on H-HOLD \(run 41, 2026-11-06T03:00:00Z\)/);
  assert.equal(prepOf({ stage: 'hold' }, f, `${row('ab'.repeat(32))}\n\n`).openingsRead, 1);
  assert.throws(() => prepOf({ stage: 'hold' }, f, `${row('ab'.repeat(32))}\n{"hash": 1}\n`), /line 2: not an object with a string hash/);
  assert.throws(() => prepOf({ stage: 'hold' }, f, '{"hash": "x"\n'), /line 1: not JSON/);
  assert.deepEqual(parseOpenings(`${row('cd')}\n`).map((x) => x.hash), ['cd']);
  // The hash is the list's canonical form: re-ordering, re-spacing and re-spelling a number keep it (still refused);
  // a changed value or a renamed arm is another list.
  const shuffled = [HOLD_LIST[3], HOLD_LIST[1], HOLD_LIST[0], HOLD_LIST[2]].map((x) => ({
    overrides: Object.fromEntries(Object.entries(x.overrides).reverse().map(([k, v]) => [k, k === 'TENNIS_CONF_FLOW' ? '0.40' : v])),
    ...Object.fromEntries(Object.entries(x).filter(([k]) => k !== 'overrides').reverse()),
  }));
  const f2 = holdFile(undefined, JSON.stringify(shuffled, null, 3));
  assert.equal(specsHash(validateHoldSpecs(shuffled)), p.specsHash);
  assert.throws(() => prepOf({ stage: 'hold' }, f2, row(p.specsHash)), /already opened/);
  const changed = HOLD_LIST.map((x) => (x.id.includes('loose') ? { ...x, overrides: { ...x.overrides, TENNIS_CONF_FLOW: 0.05 } } : x));
  assert.notEqual(specsHash(validateHoldSpecs(changed)), p.specsHash);
  assert.equal(prepOf({ stage: 'hold' }, holdFile(changed), row(p.specsHash)).openingsRead, 1);
  const renamed = HOLD_LIST.map((x) => ({ ...x, id: x.id.replace('|loose|', '|loose2|') }));
  assert.notEqual(specsHash(validateHoldSpecs(renamed)), p.specsHash);
  assert.ok(canonicalSpecs(specs).startsWith('[["A|hold|loose|F1","F1",null,false,0,'));
  // Hold refusals: not the whole block, family B, another pool, a missing or invalid list.
  assert.throws(() => prepOf({ stage: 'hold', from: '2026-08-03' }, f, ''), /whole of H-HOLD/);
  assert.throws(() => prepOf({ stage: 'hold', familyB: true }, f, ''), /discovery design/);
  assert.throws(() => prepOf({ stage: 'hold', pool: 'disc' }, f, ''), /scores pool 'hold'/);
  assert.throws(() => prepOf({ stage: 'hold' }, path.join(tmp(), 'none.json'), ''), /stage hold reads its frozen spec list from .*, which does not exist/);
  assert.throws(() => prepOf({ stage: 'hold' }, holdFile(HOLD_LIST.slice(0, 3)), ''), /no production-default F1 control/);
  assert.equal(HOLD_SPECS, 'research/tennis-ta/hold-specs.json');
});

test('validateHoldSpecs: stage 2\'s rules on A|hold| ids, one control, every candidate with its F2 neighbour and coin placebo', () => {
  const ok = validateHoldSpecs([...HOLD_LIST, { id: 'A|hold|loose|F0', overrides: { TENNIS_ENTRY_MIN_SIGNALS_PRE: 0, TENNIS_CONF_FLOW: 0.4 }, fill: 'F0' },
    { id: 'A|hold|prod|settlehold|F1', overrides: { TENNIS_END_LOSER_CUT: false }, fill: 'F1', stick: true }]);
  assert.equal(ok.length, 6);
  assert.ok(ok.every((x) => x.overrides.TENNIS_TRAIL_RATCHET === false));
  // A control with a harness rule written at its default is still production's.
  assert.equal(validateHoldSpecs([...HOLD_LIST.slice(0, 3), { id: 'A|hold|base|F1', overrides: { HARNESS_FEE_MULT: '1', HARNESS_LOSER_STOP: 0 }, fill: 'F1' }]).length, 4);
  const bad = (x: unknown[], re: RegExp) => assert.throws(() => validateHoldSpecs(x), re);
  bad(HOLD_LIST.slice(0, 3), /hold specs: 1 problem\(s\):\n  no production-default F1 control/);
  bad([HOLD_LIST[3]], /the list holds no candidate/);
  bad([HOLD_LIST[0], HOLD_LIST[2], HOLD_LIST[3]], /A\|hold\|loose\|F1: a hold candidate needs its F2 neighbour \(A\|hold\|loose\|F2\)/);
  bad([HOLD_LIST[0], HOLD_LIST[1], HOLD_LIST[3]], /needs its coin placebo \(A\|hold\|loose\|coin\)/);
  bad([HOLD_LIST[0], HOLD_LIST[3]], /needs its F2 neighbour \(A\|hold\|loose\|F2\) and coin placebo/);
  bad([...HOLD_LIST, { id: 'A|hold|x|F0', overrides: { TENNIS_CONF_FLOW: 0.05 }, fill: 'F0' }], /A\|hold\|x: a hold config needs its F1 arm/);
  // A control that is not production's (a harness rule moved, a clock phase) is a candidate without its arms.
  bad([...HOLD_LIST.slice(0, 3), { id: 'A|hold|base|F1', overrides: { HARNESS_LOSER_STOP: 0.5 }, fill: 'F1' }], /no production-default F1 control[\s\S]*A\|hold\|base\|F1: a hold candidate needs/);
  // Two controls are twins (the base rule), stage 2 ids and sticks without A|hold| are refused.
  bad([...HOLD_LIST, { id: 'A|hold|prod2|F1', overrides: {}, fill: 'F1' }], /runs exactly as A\|hold\|prod\|F1/);
  bad([{ ...HOLD_LIST[0], id: 'A|s2|loose|F1' }, ...HOLD_LIST.slice(1)], /id must be a string starting 'A\|hold\|'/);
  bad([...HOLD_LIST, { id: 'A|hold|prod|nopacer|F1', overrides: { HARNESS_PACER: 'off' }, fill: 'F1' }], /ids 'A\|hold\|prod\|<name>\|<arm>' are measuring sticks/);
  // Stage 2 keeps its own prefix and has no control rule.
  assert.equal(validateStage2Specs([{ id: 'A|s2|a|F1', overrides: { TENNIS_CONF_FLOW: 0.4 }, fill: 'F1' }]).length, 1);
  assert.throws(() => validateStage2Specs(HOLD_LIST), /stage 2 specs: \d+ problem[\s\S]*starting 'A\|s2\|'/);
});

function metaOf(p: Prep, k: number, j: number, over: Partial<ShardMeta> = {}): ShardMeta {
  const s = p.subPlans[k][j];
  return {
    simVersion: SIM_VERSION, stage: p.stage, pool: p.pool, run: '42', k, j, shards: p.plan.length, subShards: p.subPlans[k].length, from: s.from, to: s.to,
    units: s.units, dataVersion: 'KXATPMATCH:sha256:aa,KXWTAMATCH:sha256:bb', requestSha: p.requestSha, families: p.familyB ? ['A', 'B'] : ['A'], unitsSha: p.unitsSha,
    replayVersion: p.replayVersion, specsHash: p.specsHash,
    coverage: { span: [s.from, s.to], series: { KXATPMATCH: { first: '2025-06-20', last: '2026-11-04', files: 500, spanDays: 7, withFile: 7, withTrades: 7, missing: [] } }, matches: 10, noPublishedStart: 1, noPublishedStartEvents: ['E'],
      pools: { disc: { matches: 9, units: s.units.length }, nostart: { matches: 1, units: 1 } } },
    ...over,
  };
}

test('checkShards: the full set passes; missing, duplicate, extra, mixed data version or wrong slice fail', () => {
  const p = prepOf({ stage: '1', shards: 2 });
  const all = () => p.expected.map((f) => { const m = /a-s1-(\d+)-(\d+)/.exec(f)!; return { file: f, meta: metaOf(p, Number(m[1]), Number(m[2])) }; });
  const good = checkShards(p, [...p.expected], all(), '42');
  assert.deepEqual(good.problems, []);
  assert.equal(good.summary.units, 11);
  assert.deepEqual([good.summary.replayVersion, good.summary.specsHash], [REPLAY_VERSION, p.specsHash]);
  assert.equal(good.summary.matches, 10 * p.expected.length);
  assert.equal(good.summary.noPublishedStart, p.expected.length);
  assert.deepEqual(good.summary.pools, { disc: { matches: 9 * p.expected.length, units: 11 }, nostart: { matches: p.expected.length, units: p.expected.length } });
  // Missing on Drive and not copied.
  const miss = checkShards(p, p.expected.slice(1), all().slice(1), '42');
  assert.ok(miss.problems.some((x) => x.startsWith(`${p.expected[0]}: missing on Drive`)));
  assert.ok(miss.problems.some((x) => x.includes('swept by no shard')));
  // Two copies of one name on Drive (rclone copies only one of them).
  assert.ok(checkShards(p, [...p.expected, p.expected[2]], all(), '42').problems.some((x) => x.includes('2 copies')));
  // A file the plan does not name.
  assert.ok(checkShards(p, [...p.expected, 'a-s1-9-0.json.gz'], all(), '42').problems.some((x) => x.includes('not in the plan')));
  // Mixed data versions, another run, another request, another sim version.
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
  const sv = all();
  sv[0].meta.simVersion = 'tennis-ta-sim/2';
  assert.ok(checkShards(p, [...p.expected], sv, '42').problems.some((x) => x.includes('simVersion "tennis-ta-sim/2", expected "tennis-ta-sim/3"')));
  // Another replay version (a slice built its days on another history replay) or another spec list.
  const rv = all();
  rv[0].meta.replayVersion = 7;
  assert.ok(checkShards(p, [...p.expected], rv, '42').problems.some((x) => x.includes('replayVersion 7, expected 8')));
  assert.ok(checkShards(p, [...p.expected], rv, '42').problems.some((x) => x.startsWith('replayVersion differs')));
  const sh = all();
  sh[1].meta.specsHash = 'ff'.repeat(32);
  assert.ok(checkShards(p, [...p.expected], sh, '42').problems.some((x) => x.includes(`specsHash "${'ff'.repeat(32)}", expected "${p.specsHash}"`)));
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
  // A hold run's files (a-shold-<k>-<j>.json.gz) check the same way.
  const ph = prepOf({ stage: 'hold', shards: 3 }, holdFile(), '');
  const hm = ph.expected.map((f) => { const m = /a-shold-(\d+)-(\d+)/.exec(f)!; return { file: f, meta: metaOf(ph, Number(m[1]), Number(m[2]), { coverage: { ...metaOf(ph, 0, 0).coverage, pools: { hold: { matches: 3, units: 1 } } } }) }; });
  const hc = checkShards(ph, [...ph.expected], hm, '42');
  assert.deepEqual(hc.problems, []);
  assert.deepEqual([hc.summary.stage, hc.summary.pool, hc.summary.units], ['hold', 'hold', 13]);
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

/** The fixture's history with one match's published start removed (Kalshi gave none): its replay market line carries no
 *  startTime, so the sim places it by its earliest market-line time and marks startPublished false. */
function dropStart(hist: string, day: string, event: string): void {
  const f = path.join(hist, 'kalshi', 'KXATPMATCH', `${day}.jsonl`);
  const lines = fs.readFileSync(f, 'utf8').split('\n').filter(Boolean).map((l) => {
    const m = JSON.parse(l) as Record<string, unknown>;
    if (m.event === event) delete m.startTime;
    return JSON.stringify(m);
  });
  fs.writeFileSync(f, lines.join('\n') + '\n');
}

const DISC_DAY = '2026-07-14'; // unit W-2026-07-13 (disc: start era, closing before DEV_TO)

async function sliceRun(familyB: boolean): Promise<{ prep: Prep; out: ShardOut; file: string; replay: string; specs: string }> {
  const dir = tmp(), hist = path.join(dir, 'hist'), replay = path.join(dir, 'replay');
  writeTaHistory(hist, 3, [DISC_DAY]); // three KXATPMATCH matches on Jul 14
  dropStart(hist, DISC_DAY, 'KXATPMATCH-20260714M3');
  await buildHistoryReplay({ historyDir: hist, outDir: replay, assets: [], fromDay: '2026-07-12', toDay: '2026-07-16', tennisSeries: ['KXATPMATCH'], log: () => {} });
  const specs = specFile(), reqFile = path.join(dir, 'sweep-request.json');
  const reqText = JSON.stringify({ stage: '2', from: '2026-07-13', to: '2026-07-13', shards: 1, familyB });
  fs.writeFileSync(reqFile, reqText);
  const prep = prepare(reqText, unitsText, specs);
  assert.deepEqual(prep.plan, [{ k: 0, from: '2026-07-13', to: '2026-07-21', units: ['W-2026-07-13'] }]);
  const sub = prep.subPlans[0][0];
  const file = path.join(dir, 'shards', prep.expected[0]);
  await cmdRun({ replay, hist: path.join(hist, 'kalshi'), series: 'KXATPMATCH', from: sub.from, to: sub.to, 'units-list': sub.units.join(','), stage: '2', specs,
    pool: 'disc', units: UNITS_FILE, 'family-b': String(familyB), request: reqFile, 'data-version': 'KXATPMATCH:sha256:test', run: '42', k: '0', j: '0', shards: '1',
    'sub-shards': String(prep.subPlans[0].length), out: file });
  return { prep, out: JSON.parse(zlib.gunzipSync(fs.readFileSync(file)).toString('utf8')) as ShardOut, file, replay, specs };
}

test('run: one sub-slice end to end on the fixture writes a C4 shard file the report gate accepts; nostart labelled and counted', async () => {
  const { prep, out, file, replay, specs } = await sliceRun(false);
  const m = out.meta;
  assert.equal(m.simVersion, 'tennis-ta-sim/3');
  assert.equal(m.replayVersion, REPLAY_VERSION);
  assert.equal(m.specsHash, prep.specsHash);
  assert.deepEqual(m.era, prep.era);
  assert.deepEqual([m.stage, m.pool, m.run, m.k, m.j, m.shards, m.subShards, m.from, m.to], ['2', 'disc', '42', 0, 0, 1, 1, '2026-07-13', '2026-07-21']);
  assert.deepEqual(m.units, ['W-2026-07-13']);
  assert.deepEqual(m.families, ['A']);
  assert.equal(m.requestSha, prep.requestSha);
  assert.equal(m.dataVersion, 'KXATPMATCH:sha256:test');
  assert.equal(m.stratumLabel, 'H');
  assert.equal(m.lookbackDays, 1);
  assert.equal(m.coverage.matches, 3);
  assert.equal(m.coverage.noPublishedStart, 1);
  assert.deepEqual(m.coverage.noPublishedStartEvents, ['KXATPMATCH-20260714M3']);
  assert.deepEqual(m.coverage.pools, { disc: { matches: 2, units: 1 }, nostart: { matches: 1, units: 1 } });
  assert.deepEqual(m.coverage.feed, { gaps: 0, gapMs: 0, blindGaps: 0, liveDays: 0, blindDays: 0, lateGrids: 0 });
  assert.equal(m.coverage.series!.KXATPMATCH.withFile, 1);
  assert.equal(m.coverage.series!.KXATPMATCH.spanDays, 8);
  // The match without a published start ran with the others (admit() cannot tell) and is labelled for the report.
  assert.equal(out.matchList.length, 3);
  assert.deepEqual(out.matchList.map((x) => [x.event, x.pool, x.unit, x.startPublished, x.fold]), [
    ['KXATPMATCH-20260714M1', 'disc', 'W-2026-07-13', true, null], ['KXATPMATCH-20260714M2', 'disc', 'W-2026-07-13', true, null], ['KXATPMATCH-20260714M3', 'nostart', 'W-2026-07-13', false, null],
  ]);
  assert.deepEqual(out.runs.map((r) => [r.id, r.stick ?? false, r.overrides.TENNIS_TRAIL_RATCHET, r.offsetMs]), [['A|s2|loose|F1', false, false, undefined], ['A|s2|prod|nopacer|F1', true, false, 1500]]);
  assert.ok(out.runs.every((r) => r.pnl.length === 3));
  assert.equal(out.familyB, undefined);
  const meta = await readShardMeta(file);
  assert.deepEqual(meta, m);
  // The report reads the file's runs (offsetMs included) and its check_runs gate passes them.
  if (spawnSync('python3', ['-I', '-c', 'import numpy, scipy'], { encoding: 'utf8' }).status === 0) {
    const cr = checkRunsDir(path.dirname(file));
    assert.equal(cr.status, 0, cr.err.slice(-2000));
    assert.deepEqual(cr.out!.lists, { [prep.expected[0].replace(/\.json\.gz$/, '')]: [] });
  }
  const chk = checkShards(prep, [...prep.expected], [{ file: prep.expected[0], meta }], '42');
  assert.deepEqual(chk.problems, []);
  assert.deepEqual(chk.summary.pools, { disc: { matches: 2, units: 1 }, nostart: { matches: 1, units: 1 } });
  // A slice whose unit list leaves the fixture's unit out owns nothing.
  const other = path.join(path.dirname(file), 'other.json.gz');
  await cmdRun({ replay, from: '2026-07-13', to: '2026-07-21', 'units-list': 'WIM-2026-06-29', stage: '2', specs, pool: 'disc', units: UNITS_FILE, out: other });
  const o = JSON.parse(zlib.gunzipSync(fs.readFileSync(other)).toString('utf8')) as ShardOut;
  assert.equal(o.matchList.length, 0);
  assert.deepEqual(o.meta.coverage.pools, { disc: { matches: 0, units: 0 }, nostart: { matches: 0, units: 0 } });
  await assert.rejects(cmdRun({ replay, from: '2026-07-13', to: '2026-07-21', stage: '1', pool: 'check', units: UNITS_FILE, out: other }), /no longer exists/);
  await assert.rejects(cmdRun({ replay, from: '2026-07-13', to: '2026-07-21', stage: '2', specs, pool: 'hold', units: UNITS_FILE, out: other }), /scored only by stage 'hold'/);
  await assert.rejects(cmdRun({ replay, from: '2026-07-13', to: '2026-07-21', stage: '1', pool: 'old', units: UNITS_FILE, out: other }), /stage 2 finalists only/);
  await assert.rejects(cmdRun({ replay, from: '2026-07-13', to: '2026-07-21', stage: '2', specs, pool: 'nostart', units: UNITS_FILE, out: other }), /never scored/);
});

test('run on the old pool (stratum H0, stage 2): no published start is the norm there, every match stays old', async () => {
  const dir = tmp(), hist = path.join(dir, 'hist'), replay = path.join(dir, 'replay');
  writeTaHistory(hist); // three KXATPMATCH matches on 2026-03-02 (unit W-2026-03-02, old)
  dropStart(hist, '2026-03-02', 'KXATPMATCH-M2');
  await buildHistoryReplay({ historyDir: hist, outDir: replay, assets: [], fromDay: '2026-03-01', toDay: '2026-03-03', tennisSeries: ['KXATPMATCH'], log: () => {} });
  const specs = specFile();
  const prep = prepare(JSON.stringify({ stage: '2', pool: 'old', from: '2026-03-02', to: '2026-03-02', shards: 1 }), unitsText, specs);
  assert.equal(prep.stratumLabel, 'H0');
  const sub = prep.subPlans[0][0];
  const file = path.join(dir, 'a.json.gz');
  await cmdRun({ replay, from: sub.from, to: sub.to, 'units-list': sub.units.join(','), stage: '2', specs, pool: 'old', units: UNITS_FILE, out: file });
  const out = JSON.parse(zlib.gunzipSync(fs.readFileSync(file)).toString('utf8')) as ShardOut;
  assert.equal(out.meta.pool, 'old');
  assert.equal(out.meta.stratumLabel, 'H0');
  assert.match(String(out.meta.evidence), /H0/);
  assert.deepEqual(out.matchList.map((x) => [x.pool, x.startPublished]), [['old', true], ['old', false], ['old', true]]);
  assert.deepEqual(out.meta.coverage.pools, { old: { matches: 3, units: 1 }, nostart: { matches: 0, units: 0 } });
  // The same unit swept as disc owns nothing (its matches are old).
  const d = path.join(dir, 'd.json.gz');
  await cmdRun({ replay, from: sub.from, to: sub.to, 'units-list': sub.units.join(','), stage: '2', specs, pool: 'disc', units: UNITS_FILE, out: d });
  assert.equal((JSON.parse(zlib.gunzipSync(fs.readFileSync(d)).toString('utf8')) as ShardOut).matchList.length, 0);
});

test('run on the straddling unit W-2026-07-27: hold owns the Aug 2 matches (fold 1), disc the Jul 30 ones, Jul 31 neither', async () => {
  const dir = tmp(), hist = path.join(dir, 'hist'), replay = path.join(dir, 'replay');
  writeTaHistory(hist, 3, ['2026-07-30', '2026-07-31', '2026-08-02']);
  dropStart(hist, '2026-08-02', 'KXATPMATCH-20260802M2');
  await buildHistoryReplay({ historyDir: hist, outDir: replay, assets: [], fromDay: '2026-07-29', toDay: '2026-08-04', tennisSeries: ['KXATPMATCH'], log: () => {} });
  const specs = holdFile();
  const base = { replay, from: '2026-07-27', to: '2026-08-04', 'units-list': 'W-2026-07-27', units: UNITS_FILE };
  const read = (f: string) => JSON.parse(zlib.gunzipSync(fs.readFileSync(f)).toString('utf8')) as ShardOut;
  const h = path.join(dir, 'a-shold-0-0.json.gz');
  await cmdRun({ ...base, stage: 'hold', specs, out: h }); // pool defaults to hold at stage hold
  const ho = read(h);
  assert.deepEqual([ho.meta.stage, ho.meta.pool, ho.meta.replayVersion, ho.meta.specsHash], ['hold', 'hold', REPLAY_VERSION, specsHash(validateHoldSpecs(HOLD_LIST))]);
  assert.match(String(ho.meta.evidence), /H-HOLD/);
  assert.deepEqual(ho.meta.holdFolds, holdFolds());
  assert.deepEqual(ho.matchList.map((x) => [x.event, x.day, x.pool, x.fold]), [
    ['KXATPMATCH-20260802M1', '2026-08-02', 'hold', 1], ['KXATPMATCH-20260802M2', '2026-08-02', 'nostart', null], ['KXATPMATCH-20260802M3', '2026-08-02', 'hold', 1],
  ]);
  assert.deepEqual(ho.meta.coverage.pools, { hold: { matches: 2, units: 1 }, nostart: { matches: 1, units: 1 } });
  assert.deepEqual(ho.runs.map((r) => r.id), HOLD_LIST.map((x) => x.id));
  assert.deepEqual(ho.meta.poolSpans, poolSpans(units, 'hold', HARD_CUTOFF, new Set(['W-2026-07-27'])));
  // The same unit swept as disc (stage 2) owns the Jul 30 matches only; the Jul 31 ones are embargoed in both.
  const d = path.join(dir, 'd.json.gz');
  await cmdRun({ ...base, stage: '2', specs: specFile(), pool: 'disc', out: d });
  assert.deepEqual(read(d).matchList.map((x) => [x.day, x.pool, x.fold]), [['2026-07-30', 'disc', null], ['2026-07-30', 'disc', null], ['2026-07-30', 'disc', null]]);
  // Stage hold sweeps pool hold only, never with family B.
  await assert.rejects(cmdRun({ ...base, stage: 'hold', specs, pool: 'disc', out: d }), /scores pool 'hold'/);
  await assert.rejects(cmdRun({ ...base, stage: 'hold', specs, 'family-b': 'true', out: d }), /family B is a discovery design/);
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
  for (const c of out.familyB!.cells) for (const u of Object.keys(c.units)) assert.equal(u, 'W-2026-07-13');
  assert.equal(out.meta.familyBStartMismatch, 0);
  // The nostart match is left out of family B too.
  assert.equal(out.meta.familyBNoStart, 1);
  assert.deepEqual(checkShards(prep, [...prep.expected], [{ file: prep.expected[0], meta: await readShardMeta(file) }], '42').problems, []);
  // A slice that owns no match (an embargoed or empty unit) still writes its family B export: the sweep gives the study
  // its stratum up front, since there is no grid to take it from.
  const empty = path.join(path.dirname(file), 'empty.json.gz');
  await cmdRun({ replay, from: '2026-07-13', to: '2026-07-21', 'units-list': 'WIM-2026-06-29', stage: '2', specs, pool: 'disc', units: UNITS_FILE, 'family-b': 'true', out: empty });
  const e = JSON.parse(zlib.gunzipSync(fs.readFileSync(empty)).toString('utf8')) as ShardOut;
  assert.equal(e.matchList.length, 0);
  assert.deepEqual(e.meta.families, ['A', 'B']);
  assert.equal(e.familyB!.stratum, 'H');
  assert.ok(e.familyB!.designSize > 0 && e.familyB!.cells.length === 0);
});

// The workflow: PyYAML parses it and bash -n parses every run block (GitHub expressions replaced first). The same helper
// is kept for manual runs (python3 -I ymlcheck.py WORKFLOW.yml).
const YML_CHECK = `
import json, re, subprocess, sys
import yaml
doc = yaml.safe_load(open(sys.argv[1]))
jobs, problems, n = {}, [], 0
for jname, job in (doc.get('jobs') or {}).items():
    steps = []
    for i, st in enumerate(job.get('steps') or []):
        run = st.get('run')
        steps.append({'name': st.get('name') or st.get('uses') or f'step {i}', 'run': run})
        if run is None:
            continue
        n += 1
        r = subprocess.run(['bash', '-n'], input=re.sub(r'\\$\\{\\{.*?\\}\\}', 'GHA_EXPR', run), text=True, capture_output=True)
        if r.returncode:
            problems.append(jname + ' / ' + steps[-1]['name'] + ': ' + r.stderr.strip())
    jobs[jname] = steps
print(json.dumps({'on': doc.get('on', doc.get(True)), 'jobs': jobs, 'runBlocks': n, 'problems': problems}))
sys.exit(1 if problems else 0)
`;

function ymlCheck(file: string): { status: number | null; out?: { on: unknown; jobs: Record<string, Array<{ name: string; run: string | null }>>; runBlocks: number; problems: string[] }; err: string } {
  const dir = tmp();
  fs.writeFileSync(path.join(dir, 'ymlcheck.py'), YML_CHECK);
  const r = spawnSync('python3', ['-I', path.join(dir, 'ymlcheck.py'), file], { encoding: 'utf8' });
  let out;
  try { out = JSON.parse(r.stdout); } catch { /* none */ }
  return { status: r.status, out, err: r.stderr };
}

test('workflow: YAML parses, every run block parses in bash, the report job validates and uploads the registry rows', (t) => {
  const probe = spawnSync('python3', ['-I', '-c', 'import yaml'], { encoding: 'utf8' });
  if (probe.status !== 0) { t.skip('python3 with PyYAML is not available'); return; }
  const wf = path.join(REPO, '.github', 'workflows', 'tennis-ta-sweep.yml');
  const r = ymlCheck(wf);
  assert.equal(r.status, 0, `${r.err}\n${(r.out?.problems ?? []).join('\n')}`);
  const { jobs, runBlocks, on } = r.out!;
  assert.deepEqual(Object.keys(jobs), ['prep', 'shard', 'report']);
  assert.ok(runBlocks >= 15);
  assert.deepEqual(on, { push: { branches: ['claude/project-thread-7817be'], paths: ['research/tennis-ta/sweep-request.json'] } });
  const text = fs.readFileSync(wf, 'utf8');
  assert.ok(!text.includes('trials.jsonl'), 'the interim ledger append is gone');
  const report = jobs.report;
  const idx = (re: RegExp) => report.findIndex((s) => re.test(s.name));
  const body = (re: RegExp) => report[idx(re)]?.run ?? '';
  // registry.py from main, else the registry thread's branch; passed to the report with the commit sha.
  assert.match(body(/^Registry module/), /refs\/heads\/main:refs\/remotes\/origin\/main/);
  assert.match(body(/^Registry module/), /claude\/project-thread-79ntof/);
  assert.match(body(/^Registry module/), /git show "\$SRC:research\/registry\.py" > \/tmp\/registry\.py/);
  assert.match(body(/^Report$/), /--registry-py \/tmp\/registry\.py --sha "\$GITHUB_SHA"/);
  assert.match(body(/^Registry rows valid/), /python3 -I \/tmp\/registry\.py validate "\$ROWS"/);
  assert.match(body(/^Registry rows valid/), /contract_type == "tennis"/);
  const up = body(/^Registry upload/);
  assert.match(up, /rclone copyto "\$ROWS" "gdrive:kalshi-bot-archive\/registry\/shards\/tennis-ta\/\$RUN\.jsonl"/);
  assert.match(up, /\.problems \| length\) == 0/);
  // Order: registry module, completeness check, report, validation, keep, upload, then the commit comment.
  const order = [/^Registry module/, /^Shards/, /^Report$/, /^Registry rows valid/, /^Keep the report/, /^Registry upload/, /^Report as a commit comment/].map(idx);
  assert.ok(order.every((x) => x >= 0), JSON.stringify(order));
  assert.deepEqual([...order].sort((a, b) => a - b), order);
  assert.match(body(/^Report as a commit comment/), /commits\/\$GITHUB_SHA\/comments/);
  // The shard job builds replay days from the H lookback (1 day) on.
  assert.match(jobs.shard.find((s) => s.name === 'Replay days for the slice')!.run!, /date -u -d "\$FROM -1 day"/);
  // C10, prep: the openings ledger is read (Drive set up first) and handed to prep, which refuses a reopened hold list.
  const prep = jobs.prep, pidx = (re: RegExp) => prep.findIndex((s) => re.test(s.name));
  const porder = [/^Drive setup$/, /^Openings ledger/, /^Request and plan$/, /^Run id not already scored$/].map(pidx);
  assert.ok(porder.every((x) => x >= 0), JSON.stringify(porder));
  assert.deepEqual([...porder].sort((a, b) => a - b), porder);
  assert.match(prep[pidx(/^Request and plan$/)].run!, /prep --request research\/tennis-ta\/sweep-request\.json[\s\S]*--openings prep\/openings\.jsonl/);
  assert.ok(prep[pidx(/^Openings ledger/)].run!.includes(`LEDGER=${OPENINGS_LEDGER}`));
  // C10, report: the hold run's opening is appended after the completeness check and before the report reads anything.
  const lidx = idx(/^Openings ledger/);
  assert.ok(lidx > idx(/^Shards/) && lidx < idx(/^Report$/), `${lidx}`);
  assert.ok(body(/^Openings ledger/).includes(`LEDGER=${OPENINGS_LEDGER}`));
  assert.match(body(/^Openings ledger/), /\{hash: \$h, run: \$r, ts: \$ts, ids: \$p\[0\]\.specIds, pool: "hold"\}/);
  assert.match(text, /STAGE: \$\{\{ needs\.prep\.outputs\.stage \}\}/);
  // The helper catches a broken block.
  const broken = path.join(tmp(), 'broken.yml');
  fs.writeFileSync(broken, 'on: push\njobs:\n  a:\n    runs-on: x\n    steps:\n      - name: bad\n        run: |\n          if [ 1 ]; then echo\n');
  const b = ymlCheck(broken);
  assert.equal(b.status, 1);
  assert.ok(b.out!.problems.some((x) => x.startsWith('a / bad:')));
});

/** An rclone stand-in for the ledger steps: gdrive:<path> is <FAKE_DRIVE>/<path>; lsf --dirs-only / --files-only, cat and
 *  copyto, failing like rclone on a missing directory or file (and on every call when FAKE_DRIVE_DOWN is set). */
const FAKE_RCLONE = `#!/usr/bin/env bash
set -u
[ -n "\${FAKE_DRIVE_DOWN:-}" ] && { echo "Failed to create file system: couldn't connect" >&2; exit 1; }
map() { echo "$FAKE_DRIVE/\${1#gdrive:}"; }
cmd=$1; shift
case "$cmd" in
  lsf) d=$(map "$1"); [ -d "$d" ] || { echo "directory not found" >&2; exit 3; }
       for x in "$d"/*; do [ -e "$x" ] || continue; if [ "$2" = --dirs-only ]; then [ -d "$x" ] && echo "$(basename "$x")/"; else [ -f "$x" ] && basename "$x"; fi; done ;;
  cat) f=$(map "$1"); [ -f "$f" ] || { echo "object not found" >&2; exit 3; }; cat "$f" ;;
  copyto) t=$(map "$2"); mkdir -p "$(dirname "$t")"; cp "$1" "$t" ;;
  *) echo "unexpected rclone $cmd" >&2; exit 2 ;;
esac
`;

test('workflow ledger steps: prep reads the ledger strictly; the report job appends a hold run once, refusing a reopened list', (t) => {
  const probe = spawnSync('python3', ['-I', '-c', 'import yaml'], { encoding: 'utf8' });
  if (probe.status !== 0 || spawnSync('jq', ['--version']).status !== 0) { t.skip('python3 with PyYAML, or jq, is not available'); return; }
  const r = ymlCheck(path.join(REPO, '.github', 'workflows', 'tennis-ta-sweep.yml'));
  const step = (job: string, re: RegExp) => r.out!.jobs[job].find((s) => re.test(s.name))!.run!;
  const readStep = step('prep', /^Openings ledger/), appendStep = step('report', /^Openings ledger/);
  const dir = tmp(), bin = path.join(dir, 'bin'), drive = path.join(dir, 'drive'), work = path.join(dir, 'work');
  fs.mkdirSync(bin); fs.mkdirSync(path.join(drive, 'kalshi-bot-archive', 'models', 'tennis-ta'), { recursive: true }); fs.mkdirSync(path.join(work, 'prep'), { recursive: true });
  fs.writeFileSync(path.join(bin, 'rclone'), FAKE_RCLONE, { mode: 0o755 });
  const ledger = path.join(drive, 'kalshi-bot-archive', 'models', 'tennis-ta', 'state', 'openings.jsonl');
  const run = (script: string, env: Record<string, string> = {}) => spawnSync('bash', ['-c', script], { cwd: work, encoding: 'utf8', env: { ...process.env, PATH: `${bin}:${process.env.PATH}`, FAKE_DRIVE: drive, ...env } });
  // prep, no ledger yet (no state/ folder): read as empty, and prep accepts the hold list.
  let x = run(readStep);
  assert.equal(x.status, 0, x.stderr);
  assert.equal(fs.readFileSync(path.join(work, 'prep', 'openings.jsonl'), 'utf8'), '');
  const f = holdFile();
  const p = prepare(JSON.stringify({ stage: 'hold' }), unitsText, f, { openings: fs.readFileSync(path.join(work, 'prep', 'openings.jsonl'), 'utf8') });
  fs.writeFileSync(path.join(work, 'prep', 'plan.json'), JSON.stringify(p));
  // A Drive that cannot be read fails the read (never "not opened").
  x = run(readStep, { FAKE_DRIVE_DOWN: '1' });
  assert.notEqual(x.status, 0);
  // report: a disc run records nothing; the hold run appends {hash, run, ts, ids, pool} once.
  x = run(appendStep, { STAGE: '1', GITHUB_RUN_ID: '100' });
  assert.equal(x.status, 0, x.stderr);
  assert.ok(!fs.existsSync(ledger));
  x = run(appendStep, { STAGE: 'hold', GITHUB_RUN_ID: '100' });
  assert.equal(x.status, 0, x.stderr + x.stdout);
  const rows = () => fs.readFileSync(ledger, 'utf8').split('\n').filter(Boolean).map((l) => JSON.parse(l) as Record<string, unknown>);
  assert.deepEqual(rows().map((o) => [o.hash, o.run, o.ids, o.pool, Object.keys(o).sort()]), [[p.specsHash, '100', p.specIds, 'hold', ['hash', 'ids', 'pool', 'run', 'ts']]]);
  assert.match(String(rows()[0].ts), /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/);
  // A re-run of the report job keeps the one row (idempotent by run id).
  x = run(appendStep, { STAGE: 'hold', GITHUB_RUN_ID: '100' });
  assert.equal(x.status, 0, x.stderr);
  assert.match(x.stdout, /already in the ledger/);
  assert.equal(rows().length, 1);
  // prep now reads the row and refuses the list; another run of it fails in the report job too.
  x = run(readStep);
  assert.equal(x.status, 0, x.stderr);
  assert.throws(() => prepare(JSON.stringify({ stage: 'hold' }), unitsText, f, { openings: fs.readFileSync(path.join(work, 'prep', 'openings.jsonl'), 'utf8') }), /already opened on H-HOLD \(run 100,/);
  x = run(appendStep, { STAGE: 'hold', GITHUB_RUN_ID: '101' });
  assert.notEqual(x.status, 0);
  assert.match(x.stdout, /already opened on H-HOLD by run 100/);
  assert.equal(rows().length, 1);
  // Another list appends after a ledger line without its newline; a damaged ledger is never overwritten.
  fs.writeFileSync(ledger, fs.readFileSync(ledger, 'utf8').trimEnd());
  const p2 = { ...p, specsHash: 'ab'.repeat(32), specIds: ['A|hold|x|F1'] };
  fs.writeFileSync(path.join(work, 'prep', 'plan.json'), JSON.stringify(p2));
  x = run(appendStep, { STAGE: 'hold', GITHUB_RUN_ID: '102' });
  assert.equal(x.status, 0, x.stderr + x.stdout);
  assert.deepEqual(rows().map((o) => [o.hash, o.run]), [[p.specsHash, '100'], ['ab'.repeat(32), '102']]);
  // The ledger naming this run with another list fails.
  fs.writeFileSync(path.join(work, 'prep', 'plan.json'), JSON.stringify({ ...p2, specsHash: 'cd'.repeat(32) }));
  x = run(appendStep, { STAGE: 'hold', GITHUB_RUN_ID: '102' });
  assert.notEqual(x.status, 0);
  assert.match(x.stdout, /holds run 102 with another list/);
  fs.writeFileSync(ledger, '{"hash": "x"}\n{broken\n');
  x = run(appendStep, { STAGE: 'hold', GITHUB_RUN_ID: '103' });
  assert.notEqual(x.status, 0);
  assert.equal(fs.readFileSync(ledger, 'utf8'), '{"hash": "x"}\n{broken\n');
});
