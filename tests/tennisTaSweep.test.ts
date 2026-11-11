import assert from 'node:assert/strict';
import { spawnSync } from 'child_process';
import crypto from 'crypto';
import fs from 'fs';
import os from 'os';
import path from 'path';
import zlib from 'zlib';
import { test } from 'node:test';
import { REPLAY_VERSION, TENNIS_CLOSE_SCAN_DAYS, buildHistoryReplay, noTennisSkips, tennisBegin, tennisLineHead } from '../research/history/historyReplay';
import { SignalStudy } from '../research/tennisTaSignals';
import {
  ARMS, CLOSE_TAIL_DAYS, DEV_TO, FULL_BOOK_FROM, H_HOLD, HARD_CUTOFF, HARNESS_RULES, HISTORY_FROM, HOLD_BATCH, HOLD_BATCH_MAX, HOLD_FOLDS, HOLD_FROM, LOCKBOX_FROM, OPENINGS_LEDGER,
  POOLS, SIM_VERSION, SLAMS, START_ERA_FROM, SUB_SHARDS, armOf, assertPool, buildUnits, candleIndex, canonicalSpecs, checkShards, cmdRun, configKeys, configOf,
  holdBatchFile, holdFold, mergeSpecParts, replaySkipsOf, specPartOf, sumTennisSkips, holdFoldEdges, holdFolds, lockboxOf, lockboxes, mondayEdge, parseOpenings, parseRequest, partition, planUnits, poolInterval, poolOf,
  poolRefusal, poolSpans, poolUnitsOf, prepare, readShardMeta, readShardParts, recordedPoolOf, requestUnits, runTags, shardFile, slamUnits, specsFor, specsHash, stage1Specs,
  STICK_KEYS, tourOf, unitOf, unitPools, validateHoldBatch, validateStage2Specs, verifyUnits, windowArmsOf, windowBlockProblems,
  type Pool, type Prep, type ShardBlocks, type ShardMeta, type ShardOut, type SweepSpec, type Unit,
} from '../research/tennisTaSweep';
import { HIST_EDGES, ORDER_USD, PLACEBO_SEED, SETTLE_FRAC, TWINS, WINDOW_VERSION, WindowAgg, eligibleMinutes, minuteCandles } from '../research/tennisTaWindow';
import { writeTaHistory, writeTaRecording } from './tennisTaFixture';

const DAY = 86_400_000, H = 3_600_000, MIN = 60_000;
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
  // C9 pools over the committed table: history from 2025-06-18, the start era from Apr 20 (pinned from the inventory), H-DEV to
  // Jul 31 00:00 UTC, H-HOLD from Aug 1 00:00 UTC to the cutoff. W-2026-07-27 holds both disc and hold time.
  const count = (pool: Pool) => units.filter((u) => unitPools(u).includes(pool)).length;
  assert.deepEqual((['out', 'old', 'disc', 'embargo', 'hold'] as Pool[]).map(count), [23, 39, 12, 1, 13]);
  assert.deepEqual(unitPools(byId.get('W-2026-07-27')!), ['disc', 'embargo', 'hold']);
  assert.deepEqual([disc[0].id, disc[disc.length - 1].id], ['W-2026-04-20', 'W-2026-07-27']);
  assert.deepEqual([old[0].id, old[old.length - 1].id], ['W-2025-06-16', 'W-2026-04-13']);
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
  const sel = requestUnits(units, 'disc', '2026-04-20', '2026-07-30');
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
  // The old pool cuts the same way (39 units into 8 shards, balanced by unit length).
  const op = planUnits(requestUnits(units, 'old', '2025-06-16', '2026-04-19'), 8);
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
  assert.throws(() => requestUnits(units, 'old', '2025-06-17', '2026-04-19'), /does not cover the start of old unit W-2025-06-16/);
  assert.deepEqual(requestUnits(units, 'old', '2025-06-16', '2026-04-19').map((u) => u.id), old.map((u) => u.id));
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
  // START_ERA_FROM (a unit edge): a match starting 1 ms before it is old (the last old unit, W-2026-04-13) whatever its
  // close or published start; one starting at it is in the start era.
  assert.equal(pool(START_ERA_FROM - 1, START_ERA_FROM + 3 * H), 'old');
  assert.equal(pool(START_ERA_FROM - 1, START_ERA_FROM + 3 * H, false), 'old');
  assert.equal(unitOf(START_ERA_FROM - 1, units), 'W-2026-04-13');
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

test('stage1Specs: 81 configs x F1/F2/coin/window/coinwindow + 2 sticks x F1/window, ratchet off everywhere, sticks flagged', () => {
  const s = stage1Specs();
  assert.equal(s.length, 409);
  assert.equal(new Set(s.map((x) => x.id)).size, 409);
  assert.ok(s.every((x) => x.overrides.TENNIS_TRAIL_RATCHET === false));
  assert.ok(s.every((x) => !('HARNESS_LOSER_CUT' in x.overrides)));
  assert.equal(s.filter((x) => x.fill === 'F1' && !x.placebo && !x.stick && !x.window).length, 81);
  assert.equal(s.filter((x) => x.fill === 'F2').length, 81);
  assert.equal(s.filter((x) => x.placebo === 'coin' && !x.window).length, 81);
  // The one test (Amendment 4): every grid config's window arm and the window arm's coin placebo, fill F1 by convention.
  const win = s.filter((x) => x.window && !x.placebo && !x.stick), coinWin = s.filter((x) => x.window && x.placebo === 'coin');
  assert.equal(win.length, 81);
  assert.equal(coinWin.length, 81);
  assert.ok([...win, ...coinWin].every((x) => x.fill === 'F1'));
  assert.ok(win.every((x) => x.id.endsWith('|window') && s.some((y) => y.id === `${configOf(x.id)}|F1` && JSON.stringify(y.overrides) === JSON.stringify(x.overrides))));
  assert.ok(coinWin.every((x) => x.id.endsWith('|coinwindow') && s.some((y) => y.id === `${configOf(x.id)}|window`)));
  // The sticks: each under F1 and as a window arm.
  const sticks = s.filter((x) => x.stick);
  assert.deepEqual(sticks.map((x) => x.id), ['A|s1|prod|settlehold|F1', 'A|s1|prod|settlehold|window', 'A|s1|prod|nopacer|F1', 'A|s1|prod|nopacer|window']);
  assert.deepEqual(sticks.map((x) => x.window ?? false), [false, true, false, true]);
  assert.equal(sticks[0].overrides.TENNIS_END_LOSER_CUT, false);
  assert.deepEqual(sticks[1].overrides, sticks[0].overrides);
  assert.equal(sticks[2].overrides.HARNESS_PACER, 'off');
  assert.ok(!('TENNIS_END_LOSER_CUT' in sticks[2].overrides));
  assert.ok(sticks.every((x) => x.placebo === undefined));
  assert.ok(s.every((x) => /^A\|s1\|/.test(x.id) && Number(x.overrides.TENNIS_CONF_WINDOW_SEC) >= 60));
  // Every stage 1 id carries its arm, as stage 2's must; the arm is what the spec's fields say (armOf) and configOf strips it.
  assert.deepEqual([...ARMS], ['F0', 'F1', 'F2', 'coin', 'window', 'coinwindow']);
  assert.ok(s.every((x) => x.id.endsWith(`|${armOf(x)}`) && ARMS.includes(armOf(x) as typeof ARMS[number]) && `${configOf(x.id)}|${armOf(x)}` === x.id));
  assert.equal(configOf('A|s1|m0.01|f0.2|o0.01|w60|coinwindow'), 'A|s1|m0.01|f0.2|o0.01|w60');
  assert.equal(configOf('A|s1|prod|settlehold'), 'A|s1|prod|settlehold');
  assert.equal(s.filter((x) => configOf(x.id) === 'A|s1|m0.01|f0.2|o0.01|w60').length, 5);
  assert.ok(s.some((x) => x.id === 'A|s1|m0.01|f0.2|o0.01|w60|F1'), 'production\'s grid point (the registry control)');
  assert.ok(s.some((x) => x.id === 'A|s1|m0.01|f0.2|o0.01|w60|window'), 'production\'s grid point under the one test');
  // The runs[] tags carry the window flag (the report reads the arm from the id and the flag from the run).
  assert.deepEqual(runTags(s).get('A|s1|m0.01|f0.2|o0.01|w60|window'), { window: true });
  assert.deepEqual(runTags(s).get('A|s1|prod|nopacer|window'), { stick: true, window: true });
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
  bad([{ id: 'A|s2|nopacer|F1', overrides: { HARNESS_PACER: 'off' }, fill: 'F1', stick: true }], /a measuring stick's id is 'A\|s2\|prod\|<name>\|<arm>'/);
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
  // The window arms (Amendment 4): |window is fill F1 with window: true, |coinwindow its coin placebo; a config's |F1 and
  // |window arms are two arms, not twins; a coinwindow arm needs the config's window arm; the id names the arm.
  const w1 = { id: 'A|s2|w|F1', overrides: { TENNIS_CONF_FLOW: 0.4 }, fill: 'F1' };
  const ww = { id: 'A|s2|w|window', overrides: { TENNIS_CONF_FLOW: 0.4 }, fill: 'F1', window: true };
  const wc = { id: 'A|s2|w|coinwindow', overrides: { TENNIS_CONF_FLOW: 0.4 }, fill: 'F1', placebo: 'coin', window: true };
  const wok = validateStage2Specs([w1, ww, wc, { id: 'A|s2|prod|settlehold|window', overrides: { TENNIS_END_LOSER_CUT: false }, fill: 'F1', stick: true, window: true }]);
  assert.deepEqual(wok.map((x) => [x.id, x.window ?? false, x.placebo ?? null, x.stick ?? false]), [['A|s2|w|F1', false, null, false], ['A|s2|w|window', true, null, false], ['A|s2|w|coinwindow', true, 'coin', false], ['A|s2|prod|settlehold|window', true, null, true]]);
  assert.deepEqual(validateStage2Specs([ww]).map((x) => x.id), ['A|s2|w|window'], 'a window arm stands alone');
  bad([{ ...ww, window: 'yes' }], /window must be true when set/);
  bad([{ ...ww, fill: 'F2', id: 'A|s2|w|window' }], /a window arm runs fill F1/);
  bad([{ ...ww, window: undefined }], /id ends \|window but the spec is fill F1 \(\|F1\)/);
  bad([{ ...w1, id: 'A|s2|w|window' }], /id ends \|window but the spec is fill F1/);
  bad([{ ...ww, id: 'A|s2|w|F1' }], /id ends \|F1 but the spec is a window arm \(\|window\)/);
  bad([{ ...wc, id: 'A|s2|w|coin' }], /id ends \|coin but the spec is the window arm's coin placebo \(\|coinwindow\)/);
  bad([{ ...wc, id: 'A|s2|w|window' }], /id ends \|window but the spec is the window arm's coin placebo/);
  bad([wc], /its config has no window arm \(A\|s2\|w\|window\)/);
  bad([ww, { ...wc, overrides: { TENNIS_CONF_FLOW: 0.05 } }], /A\|s2\|w\|coinwindow: overrides differ from A\|s2\|w\|window's/);
  bad([ww, { ...ww, id: 'A|s2|w2|window' }], /runs exactly as A\|s2\|w\|window/);
  bad([{ ...ww, id: 'A|s2|prod|x|window' }], /are measuring sticks/);
  bad([{ ...wc, id: 'A|s2|prod|x|coinwindow', stick: true }], /a measuring stick has no placebo arm/);
  // The canonical form carries the window flag (the |F1 and |window arms of one config are two specs).
  assert.notEqual(canonicalSpecs([ww as SweepSpec]), canonicalSpecs([{ ...ww, id: 'A|s2|w|F1', window: undefined } as SweepSpec]));
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
out = {'stickKeys': rep.STICK_KEYS, 'arms': list(getattr(rep, 'ARMS', ())), 'lists': {}}
for f in sorted(os.listdir(sys.argv[2])):
    info, data = rep.read_shard(os.path.join(sys.argv[2], f))
    out['lists'][f[:-len('.json.gz')]] = info['problems'] + rep.check_runs([data['runs']], info['meta'].get('stratum') or 'H')
print(json.dumps(out))
`;

/** The arms research/tennis_ta_report.py knows (its ARMS): until it learns the window arms (Amendment 4), the lists piped
 *  through its check_runs leave them out. */
function reportArms(): string[] {
  const r = spawnSync('python3', ['-I', '-c', `import importlib.util, json, sys
spec = importlib.util.spec_from_file_location('tennis_ta_report', sys.argv[1]); rep = importlib.util.module_from_spec(spec); spec.loader.exec_module(rep)
print(json.dumps(list(getattr(rep, 'ARMS', ()))))`, path.join(REPO, 'research', 'tennis_ta_report.py')], { encoding: 'utf8' });
  try { return JSON.parse(r.stdout) as string[]; } catch { return []; }
}

function reportCheckRuns(lists: Record<string, { specs: SweepSpec[]; stratum: 'H' | 'R' }>): { status: number | null; out?: { stickKeys: Record<string, unknown>; arms: string[]; lists: Record<string, string[]> }; err: string } {
  const dir = tmp(), shards = path.join(dir, 'shards');
  fs.mkdirSync(shards);
  for (const [name, { specs, stratum }] of Object.entries(lists)) {
    const tags = runTags(specs);
    // ConfigSim.run()'s fields (tennisTaSim.ts), then cmdRun's tags.
    const runs = specs.map((s) => ({ id: s.id, overrides: s.overrides, fill: s.fill, ...(s.placebo ? { placebo: s.placebo } : {}), stratum, days: [], pnl: [], episodes: [], ...tags.get(s.id) }));
    const meta = { stratum, sticks: specs.filter((s) => s.stick).map((s) => s.id) };
    // cmdRun's 'window' block (contract C12) over the empty match list: both legs' rows of every window arm, no instance.
    const eventIndex = new Map<string, number>();
    const rows = specs.filter((s) => s.window).flatMap((s) => ['underdog', 'fav'].map((leg) => new WindowAgg(s.id, leg, eventIndex).row()));
    const window = { version: WINDOW_VERSION, settleFrac: SETTLE_FRAC, orderUsd: ORDER_USD, twins: TWINS, seed: PLACEBO_SEED, events: [], rows };
    fs.writeFileSync(path.join(shards, `${name}.json.gz`), zlib.gzipSync(JSON.stringify({ meta, matchList: [], runs, window })));
  }
  return checkRunsDir(shards);
}

/** read_shard + check_runs of research/tennis_ta_report.py on every shard file in a directory. */
function checkRunsDir(shards: string): { status: number | null; out?: { stickKeys: Record<string, unknown>; arms: string[]; lists: Record<string, string[]> }; err: string } {
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
  // The window arms (Amendment 4) go through check_runs: the report knows them (its ARMS), and the piped lists carry them.
  assert.deepEqual(reportArms().filter((a) => a === 'window' || a === 'coinwindow'), ['window', 'coinwindow'], 'research/tennis_ta_report.py ARMS must know the window arms');
  const accepted = {
    stage1: { specs: stage1Specs(), stratum: 'H' as const },
    windows: { specs: validateStage2Specs([...cfg('w', { TENNIS_CONF_FLOW: 0.4 }, ['F1', 'F2', 'coin']),
      { id: 'A|s2|w|window', overrides: { TENNIS_CONF_FLOW: 0.4 }, fill: 'F1', window: true }, { id: 'A|s2|w|coinwindow', overrides: { TENNIS_CONF_FLOW: 0.4 }, fill: 'F1', placebo: 'coin', window: true }]), stratum: 'H' as const },
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
  assert.deepEqual(r, { stage: '1', pool: 'disc', from: '2026-04-20', to: '2026-07-30', shards: 8, familyB: false });
  assert.deepEqual(parseRequest({ stage: '2', pool: 'old' }, units), { stage: '2', pool: 'old', from: '2025-06-16', to: '2026-04-19', shards: 8, familyB: false });
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

function prepOf(req: object, specs?: string, openings?: string, stage2?: string): Prep {
  return prepare(JSON.stringify(req), unitsText, specs, { openings, stage2Path: stage2 });
}

/** A stage 2 list: one config under F1 and as a window arm (the one test), and a noise-floor stick. */
function specFile(): string {
  const f = path.join(tmp(), 'stage2-specs.json');
  const loose = { TENNIS_ENTRY_MIN_SIGNALS_PRE: 0, TENNIS_ENTRY_MIN_SIGNALS_LIVE: 0, TENNIS_FAV_ENTRY_MIN_SIGNALS: 0 };
  fs.writeFileSync(f, JSON.stringify([
    { id: 'A|s2|loose|F1', overrides: loose, fill: 'F1' },
    { id: 'A|s2|loose|window', overrides: loose, fill: 'F1', window: true },
    { id: 'A|s2|prod|nopacer|F1', overrides: { HARNESS_PACER: 'off' }, fill: 'F1', stick: true, offsetMs: 1500 },
  ]));
  return f;
}

/** A batch of the one read (Amendment 4 item 7): three hot spots off a league run, three stage 1 grid configs (production's
 *  grid point, one 'both', one 'fav'); a measuring stick is never one (validateHoldBatch refuses it). */
const BATCH = {
  league_run: '19876543210',
  batch: [{ id: 'A|s1|m0.01|f0.2|o0.01|w60', leg: 'underdog' }, { id: 'A|s1|m0.02|f0.4|o0.02|w300', leg: 'both' }, { id: 'A|s1|m0.005|f0.05|o0.005|w120', leg: 'fav' }],
};
/** What the read runs for BATCH: each config's |window and |F1 arms, in batch order, nothing else. */
const BATCH_IDS = ['A|s1|m0.01|f0.2|o0.01|w60|window', 'A|s1|m0.01|f0.2|o0.01|w60|F1', 'A|s1|m0.02|f0.4|o0.02|w300|window', 'A|s1|m0.02|f0.4|o0.02|w300|F1', 'A|s1|m0.005|f0.05|o0.005|w120|window', 'A|s1|m0.005|f0.05|o0.005|w120|F1'];

function batchFile(obj: unknown = BATCH, text?: string): string {
  const f = path.join(tmp(), 'hold-batch.json');
  fs.writeFileSync(f, text ?? JSON.stringify(obj));
  return f;
}
const fileHash = (f: string) => crypto.createHash('sha256').update(fs.readFileSync(f)).digest('hex');

test('prepare: plan, sub-plans and expected files; refuses a request that cuts a unit, names another pool or lacks stage 2 specs', () => {
  const p = prepOf({ stage: '1', pool: 'disc', from: '2026-04-20', to: '2026-07-30', shards: 8, familyB: true });
  assert.equal(p.configs, 409);
  assert.equal(p.windowVersion, WINDOW_VERSION);
  assert.deepEqual([p.batchHash, p.leagueRun, p.batch], [undefined, undefined, undefined]);
  assert.equal(p.plan.length, 8);
  assert.equal(p.subPlans.length, 8);
  assert.deepEqual(p.units, disc.map((u) => u.id));
  assert.equal(p.expected.length, p.subPlans.reduce((s, x) => s + x.length, 0));
  assert.equal(new Set(p.expected).size, p.expected.length);
  assert.equal(p.expected[0], shardFile('1', 0, 0));
  assert.deepEqual(p.subPlans.flat().flatMap((s) => s.units), p.units);
  assert.equal(p.poolSpans.length, 12);
  assert.equal(p.poolSpans.reduce((x, s) => x + s.hours, 0), (DEV_TO - START_ERA_FROM) / H);
  assert.equal(p.familyB, true);
  assert.equal(p.simVersion, SIM_VERSION);
  assert.equal(p.replayVersion, REPLAY_VERSION);
  // Pinned: the replay version the tennis history is built with (9 since the Nov 5 strike-cap merge; a bump means every
  // registry row's data.replay_version moves, so the README's number moves with it).
  assert.equal(p.replayVersion, 9);
  assert.equal(p.stratumLabel, 'H');
  assert.deepEqual(p.era, { historyFrom: '2025-06-18T00:00:00.000Z', startEraFrom: '2026-04-20T05:00:00.000Z', devTo: '2026-07-31T00:00:00.000Z', holdFrom: '2026-08-01T00:00:00.000Z', cutoff: '2026-11-05T02:00:00.000Z' });
  assert.deepEqual(p.holdFolds, holdFolds());
  assert.deepEqual(p.poolUnits, { out: 23, old: 39, disc: 12, embargo: 1, hold: 13 });
  assert.equal(p.specsHash, specsHash(stage1Specs()));
  assert.deepEqual(p.specIds, stage1Specs().map((x) => x.id));
  assert.equal(p.openingsRead, undefined);
  // The old pool (stage 2 finalists): the same from/to rule, stratum H0.
  const specs = specFile();
  const po = prepOf({ stage: '2', pool: 'old', shards: 4 }, specs);
  assert.deepEqual([po.pool, po.stratumLabel, po.units.length, po.plan.length], ['old', 'H0', 39, 4]);
  assert.ok(po.poolSpans.every((s) => unitPools(byId.get(s.unit)!).includes('old')));
  assert.throws(() => prepOf({ stage: '2', pool: 'old', from: '2025-06-25', to: '2026-04-19' }, specs), /W-2025-06-23/);
  // Refusals: a cut unit, every other pool, old at stage 1, missing stage 2 specs, a damaged unit table.
  assert.throws(() => prepOf({ stage: '1', from: '2026-05-20', to: '2026-07-30' }), /RG-2026-05-18/);
  for (const pool of ['check', 'sealed']) assert.throws(() => prepOf({ stage: '2', pool }, specs), /no longer exists/);
  for (const pool of ['nostart', 'embargo', 'out']) assert.throws(() => prepOf({ stage: '2', pool }, specs), /never scored/);
  assert.throws(() => prepOf({ stage: '2', pool: 'hold' }, specs), /scored only by stage 'hold'/);
  assert.throws(() => prepOf({ stage: '1', pool: 'old' }), /stage 2 finalists only/);
  assert.throws(() => prepOf({ stage: '2' }, path.join(tmp(), 'none.json')), /stage 2 reads its spec list/);
  assert.throws(() => prepare(JSON.stringify({ stage: '1' }), JSON.stringify(units.map((u, i) => (i === 7 ? { ...u, end: u.end + H } : u)))), /Monday 05:00 UTC/);
});

test('prepare, stage hold: the batch read once on the whole hold block (Amendment 4 item 7); a batch already in the ledger is refused', () => {
  const f = batchFile();
  const p = prepOf({ stage: 'hold', shards: 4 }, f, '');
  assert.deepEqual([p.stage, p.pool, p.stratumLabel, p.configs, p.openingsRead], ['hold', 'hold', 'H', 6, 0]);
  assert.deepEqual(p.units, hold.map((u) => u.id));
  assert.equal(p.plan.length, 4);
  assert.equal(p.expected[0], 'a-shold-0-0.json.gz');
  assert.equal(p.poolSpans.reduce((x, s) => x + s.hours, 0), 96 * 24 + 2);
  // What the read runs: each batch config's |window and |F1 arms, nothing else, in batch order.
  assert.deepEqual(p.specIds, BATCH_IDS);
  const b = validateHoldBatch(BATCH);
  assert.deepEqual([b.leagueRun, b.batch], ['19876543210', BATCH.batch]);
  assert.deepEqual(b.specs.map((x) => x.id), BATCH_IDS);
  assert.ok(b.specs.every((x) => x.fill === 'F1' && x.placebo === undefined && x.overrides.TENNIS_TRAIL_RATCHET === false));
  assert.deepEqual(b.specs.map((x) => x.window ?? false), [true, false, true, false, true, false]);
  assert.ok(b.specs.every((x) => !x.stick));
  assert.deepEqual(b.specs[0].overrides, stage1Specs().find((x) => x.id === BATCH_IDS[0])!.overrides);
  assert.equal(p.specsHash, specsHash(b.specs));
  assert.deepEqual([p.leagueRun, p.batch, p.windowVersion], ['19876543210', BATCH.batch, WINDOW_VERSION]);
  // The batch's identity is the file's sha256 (the file as pushed, listed in the registry and the calendar): re-spacing
  // it is a new batch, though the same arms run.
  assert.equal(p.batchHash, fileHash(f));
  assert.match(p.batchHash!, /^[0-9a-f]{64}$/);
  const f2 = batchFile(undefined, JSON.stringify(BATCH, null, 2));
  assert.notEqual(prepOf({ stage: 'hold' }, f2, '').batchHash, p.batchHash);
  assert.equal(prepOf({ stage: 'hold' }, f2, '').specsHash, p.specsHash);
  // The openings ledger: required, read strictly, keyed by the batch hash, and a hash already in it is refused.
  assert.throws(() => prepOf({ stage: 'hold' }, f), /stage hold needs the openings ledger/);
  const row = (hash: string, run = '41') => JSON.stringify({ hash, run, ts: '2026-11-06T03:00:00Z', ids: p.specIds, pool: 'hold' });
  assert.throws(() => prepOf({ stage: 'hold' }, f, `${row('ab'.repeat(32))}\n${row(p.batchHash!)}\n`), /the batch .* was already read on H-HOLD \(run 41, 2026-11-06T03:00:00Z\)/);
  assert.equal(prepOf({ stage: 'hold' }, f, `${row('ab'.repeat(32))}\n\n`).openingsRead, 1);
  assert.equal(prepOf({ stage: 'hold' }, f, `${row(p.specsHash)}\n`).openingsRead, 1, 'the ledger is keyed by the batch file hash, not the spec hash');
  assert.throws(() => prepOf({ stage: 'hold' }, f, `${row('ab'.repeat(32))}\n{"hash": 1}\n`), /line 2: not an object with a string hash/);
  assert.throws(() => prepOf({ stage: 'hold' }, f, '{"hash": "x"\n'), /line 1: not JSON/);
  assert.deepEqual(parseOpenings(`${row('cd')}\n`).map((x) => x.hash), ['cd']);
  assert.ok(canonicalSpecs(b.specs).startsWith('[["A|s1|m0.005|f0.05|o0.005|w120|F1","F1",null,false,0,false,'));
  // A stage 2 hot spot resolves against the stage 2 spec list: its own |window arm when the list has one, else its F1
  // arm as a window arm.
  const s2 = specFile();
  const pb = prepOf({ stage: 'hold' }, batchFile({ league_run: '1', batch: [{ id: 'A|s2|loose', leg: 'fav' }] }), '', s2);
  assert.deepEqual([pb.specIds, pb.configs], [['A|s2|loose|window', 'A|s2|loose|F1'], 2]);
  const sl = holdBatchFile(batchFile({ league_run: '1', batch: [{ id: 'A|s2|loose', leg: 'fav' }] }), s2);
  assert.deepEqual([sl.specs[0].window, sl.specs[0].fill, sl.specs[0].overrides], [true, 'F1', sl.specs[1].overrides]);
  assert.equal(sl.hash.length, 64);
  // Hold refusals: not the whole block, family B, another pool, a missing or invalid batch.
  assert.throws(() => prepOf({ stage: 'hold', from: '2026-08-03' }, f, ''), /whole of H-HOLD/);
  assert.throws(() => prepOf({ stage: 'hold', familyB: true }, f, ''), /discovery design/);
  assert.throws(() => prepOf({ stage: 'hold', pool: 'disc' }, f, ''), /scores pool 'hold'/);
  assert.throws(() => prepOf({ stage: 'hold' }, path.join(tmp(), 'none.json'), ''), /stage hold reads its batch from .*, which does not exist/);
  assert.throws(() => prepOf({ stage: 'hold' }, batchFile(undefined, '{'), ''), /not valid JSON/);
  assert.throws(() => prepOf({ stage: 'hold' }, batchFile({ league_run: '1', batch: [] }), ''), /batch is empty/);
  assert.equal(HOLD_BATCH, 'research/tennis-ta/hold-batch.json');
  assert.equal(HOLD_BATCH_MAX, 10);
});

test('validateHoldBatch: at most 10 hot spots, config ids without an arm, legs underdog / fav / both, each once, resolvable', () => {
  const bad = (x: unknown, re: RegExp) => assert.throws(() => validateHoldBatch(x, []), re);
  const one = (id: string, leg = 'underdog') => ({ league_run: '7', batch: [{ id, leg }] });
  // A measuring stick is never a hot spot (C4, Amendment 4 item 1): refused at prep, on stage 1 and on a stage 2 list alike.
  bad(one('A|s1|prod|nopacer', 'both'), /A\|s1\|prod\|nopacer is a measuring stick .*it cannot be read on H-HOLD/);
  bad(one('A|s1|prod|settlehold'), /is a measuring stick/);
  assert.throws(() => validateHoldBatch(one('A|s2|prod|settlehold'), validateStage2Specs([{ id: 'A|s2|prod|settlehold|F1', overrides: { TENNIS_END_LOSER_CUT: false }, fill: 'F1', stick: true }])), /A\|s2\|prod\|settlehold is a measuring stick/);
  bad([], /expected a JSON object/);
  bad({ league_run: '7', batch: [{ id: 'A|s1|m0.01|f0.2|o0.01|w60', leg: 'fav' }], extra: 1 }, /unknown key extra/);
  bad({ batch: [] }, /league_run must be the league run's GitHub run id/);
  bad({ league_run: 'run 1', batch: [] }, /league_run must be/);
  bad({ league_run: '7' }, /batch must be an array/);
  bad({ league_run: '7', batch: Array.from({ length: 11 }, (_, i) => ({ id: configOf(stage1Specs()[i * 5].id), leg: 'fav' })) }, /names 11 hot spots: at most 10/);
  bad(one('A|s1|m0.01|f0.2|o0.01|w60|window'), /ends with an arm: a hot spot is a config \(A\|s1\|m0.01\|f0.2\|o0.01\|w60\)/);
  bad(one('A|s1|m0.01|f0.2|o0.01|w60|F1'), /ends with an arm/);
  bad(one('A|s1|m0.01|f0.2|o0.01|w60', 'underdogs'), /leg must be 'underdog', 'fav' or 'both'/);
  bad({ league_run: '7', batch: [{ id: 'A|s1|m0.01|f0.2|o0.01|w60', leg: 'fav' }, { id: 'A|s1|m0.01|f0.2|o0.01|w60', leg: 'fav' }] }, /is listed twice/);
  bad(one('A|s1|m0.03|f0.2|o0.01|w60'), /is not a stage 1 grid config or measuring stick/);
  bad(one('A|hold|loose'), /must start 'A\|s1\|'/);
  bad({ league_run: '7', batch: [{ id: 'A|s1|m0.01|f0.2|o0.01|w60', leg: 'fav', note: 'x' }] }, /unknown key note/);
  bad({ league_run: '7', batch: [7] }, /not an object/);
  bad(one('A|s2|loose'), /is not a stage 2 config/);
  assert.throws(() => validateHoldBatch(one('A|s2|loose'), path.join(tmp(), 'none.json')), /names a stage 2 config but the stage 2 spec list cannot be read: stage 2 reads its spec list from/);
  // A config listed with two legs runs once (its two arms); the two hot spots share them.
  const two = validateHoldBatch({ league_run: '7', batch: [{ id: 'A|s1|m0.01|f0.2|o0.01|w60', leg: 'underdog' }, { id: 'A|s1|m0.01|f0.2|o0.01|w60', leg: 'fav' }] }, []);
  assert.deepEqual([two.specs.length, two.batch.length], [2, 2]);
  // The stage 2 list resolves a stage 2 hot spot by its F1 arm, with its own window arm when it has one.
  const s2 = validateStage2Specs([{ id: 'A|s2|w|F1', overrides: { TENNIS_CONF_FLOW: 0.4 }, fill: 'F1' }, { id: 'A|s2|w|window', overrides: { TENNIS_CONF_FLOW: 0.4 }, fill: 'F1', window: true }]);
  assert.deepEqual(validateHoldBatch(one('A|s2|w'), s2).specs.map((x) => [x.id, x.window ?? false]), [['A|s2|w|window', true], ['A|s2|w|F1', false]]);
  assert.deepEqual(validateHoldBatch(one('A|s2|w'), s2.slice(0, 1)).specs.map((x) => [x.id, x.window ?? false]), [['A|s2|w|window', true], ['A|s2|w|F1', false]]);
});

function metaOf(p: Prep, k: number, j: number, over: Partial<ShardMeta> = {}): ShardMeta {
  const s = p.subPlans[k][j];
  return {
    simVersion: SIM_VERSION, stage: p.stage, pool: p.pool, run: '42', k, j, shards: p.plan.length, subShards: p.subPlans[k].length, from: s.from, to: s.to,
    units: s.units, dataVersion: 'KXATPMATCH:sha256:aa,KXWTAMATCH:sha256:bb', requestSha: p.requestSha, families: p.familyB ? ['A', 'B'] : ['A'], unitsSha: p.unitsSha,
    replayVersion: p.replayVersion, specsHash: p.specsHash, windowVersion: p.windowVersion, ...(p.batchHash !== undefined ? { batchHash: p.batchHash } : {}),
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
  assert.equal(good.summary.units, 12);
  assert.deepEqual([good.summary.replayVersion, good.summary.specsHash], [REPLAY_VERSION, p.specsHash]);
  assert.equal(good.summary.matches, 10 * p.expected.length);
  assert.equal(good.summary.noPublishedStart, p.expected.length);
  assert.deepEqual(good.summary.pools, { disc: { matches: 9 * p.expected.length, units: 12 }, nostart: { matches: p.expected.length, units: p.expected.length } });
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
  assert.ok(checkShards(p, [...p.expected], sv, '42').problems.some((x) => x.includes(`simVersion "tennis-ta-sim/2", expected "${SIM_VERSION}"`)));
  // Another replay version (a slice built its days on another history replay) or another spec list.
  const rv = all();
  rv[0].meta.replayVersion = 7;
  assert.ok(checkShards(p, [...p.expected], rv, '42').problems.some((x) => x.includes(`replayVersion 7, expected ${REPLAY_VERSION}`)));
  assert.ok(checkShards(p, [...p.expected], rv, '42').problems.some((x) => x.includes('replayVersion 7, expected 9')));
  assert.ok(checkShards(p, [...p.expected], rv, '42').problems.some((x) => x.startsWith('replayVersion differs')));
  // Every shard carries the one test's 'window' block at one version (contract C12).
  const wv = all();
  wv[0].meta.windowVersion = 'tennis-ta-window/0';
  assert.ok(checkShards(p, [...p.expected], wv, '42').problems.some((x) => x.includes('windowVersion "tennis-ta-window/0", expected "tennis-ta-window/1"')));
  assert.ok(checkShards(p, [...p.expected], wv, '42').problems.some((x) => x.startsWith('windowVersion differs')));
  assert.equal(good.summary.windowVersion, WINDOW_VERSION);
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
  const ph = prepOf({ stage: 'hold', shards: 3 }, batchFile(), '');
  const hm = ph.expected.map((f) => { const m = /a-shold-(\d+)-(\d+)/.exec(f)!; return { file: f, meta: metaOf(ph, Number(m[1]), Number(m[2]), { coverage: { ...metaOf(ph, 0, 0).coverage, pools: { hold: { matches: 3, units: 1 } } } }) }; });
  const hc = checkShards(ph, [...ph.expected], hm, '42');
  assert.deepEqual(hc.problems, []);
  assert.deepEqual([hc.summary.stage, hc.summary.pool, hc.summary.units, hc.summary.batchHash], ['hold', 'hold', 13, ph.batchHash]);
  // A hold shard that ran another batch than the one prep checked against the ledger fails.
  hm[1].meta.batchHash = 'ee'.repeat(32);
  const hb = checkShards(ph, [...ph.expected], hm, '42').problems;
  assert.ok(hb.some((x) => x.includes(`batchHash "${'ee'.repeat(32)}", expected "${ph.batchHash}"`)) && hb.some((x) => x.startsWith('batchHash differs')));
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
  // readShardParts: any top-level members in one pass, the others (runs, the bulk) streamed past unbuffered, a member
  // the file lacks left out, the kept bytes bounded.
  const w = { version: WINDOW_VERSION, events: [{ event: 'E0' }], rows: [] };
  const k = path.join(dir, 'parts.json.gz');
  fs.writeFileSync(k, zlib.gzipSync(JSON.stringify({ meta, matchList: big.slice(0, 3), runs: big, scalar: 7, s: 'x,y}"', window: w, t: true, last: null })));
  assert.deepEqual(await readShardParts(k, ['window', 'meta', 'scalar', 's', 'absent', 't', 'last']), { meta, window: w, scalar: 7, s: 'x,y}"', t: true, last: null });
  assert.deepEqual(await readShardParts(k, ['matchList']), { matchList: big.slice(0, 3) });
  assert.deepEqual(await readShardParts(k, ['meta'], 1000), { meta }, 'the bound counts the kept members only');
  await assert.rejects(readShardParts(k, ['runs'], 1000), /runs member\(s\) are longer than 1000 bytes/);
  await assert.rejects(readShardParts(g, ['window']), /not a shard file/);
  const cut = path.join(dir, 'cut2.json.gz');
  fs.writeFileSync(cut, zlib.gzipSync('{"meta":{},"runs":[1,2],"window":{"rows":[{'));
  await assert.rejects(readShardParts(cut, ['window']), /the window object never closes/);
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

async function sliceRun(familyB: boolean, extra: Record<string, string> = {}): Promise<{ prep: Prep; out: ShardOut; file: string; replay: string; specs: string }> {
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
    'sub-shards': String(prep.subPlans[0].length), out: file, ...extra });
  return { prep, out: JSON.parse(zlib.gunzipSync(fs.readFileSync(file)).toString('utf8')) as ShardOut, file, replay, specs };
}

test('merge: a sub-slice run in configs parts (--spec-part i/n) and merged is the file one process writes', async () => {
  const whole = await sliceRun(true);
  const p0 = await sliceRun(true, { 'spec-part': '0/2' }), p1 = await sliceRun(true, { 'spec-part': '1/2' });
  // Part 0 runs configs 0 and 2 and family B; part 1 runs config 1 and no family B; both list every config in the meta.
  assert.deepEqual(p0.out.runs.map((r) => r.id), [whole.out.runs[0].id, whole.out.runs[2].id]);
  assert.deepEqual(p1.out.runs.map((r) => r.id), [whole.out.runs[1].id]);
  assert.ok(p0.out.familyB && !p1.out.familyB && !p1.out.familyBWindow);
  assert.deepEqual([p0.out.meta.specPart, p1.out.meta.specPart], [{ i: 0, n: 2 }, { i: 1, n: 2 }]);
  assert.deepEqual([p0.out.meta.configs, p1.out.meta.configs, p1.out.meta.specsHash, p1.out.meta.families], [3, 3, whole.out.meta.specsHash, ['A', 'B']]);
  const merged = mergeSpecParts([p1.out, p0.out]);
  const strip = (o: ShardOut) => JSON.parse(JSON.stringify({ ...o, meta: { ...o.meta, ms: 0, written_utc: '', written_eastern: '', specParts: undefined } }));
  assert.equal(merged.meta.specParts, 2);
  assert.equal(merged.meta.specPart, undefined);
  assert.deepEqual(strip(merged), strip(whole.out));
  // A part on its own never passes the report gate; a merge refuses a missing, doubled or foreign part.
  assert.ok(checkShards(whole.prep, [...whole.prep.expected], [{ file: whole.prep.expected[0], meta: p0.out.meta }], '42').problems.some((x) => x.includes('not merged')));
  assert.equal(checkShards(whole.prep, [...whole.prep.expected], [{ file: whole.prep.expected[0], meta: merged.meta }], '42').problems.length, 0);
  assert.throws(() => mergeSpecParts([p0.out]), /1 file\(s\) for a split into 2/);
  assert.throws(() => mergeSpecParts([p0.out, p0.out]), /part 0 given twice/);
  assert.throws(() => mergeSpecParts([p0.out, whole.out]), /not a part of a spec split/);
  assert.throws(() => mergeSpecParts([p0.out, { ...p1.out, matchList: p1.out.matchList.slice(1) }]), /another matchList/);
  assert.throws(() => mergeSpecParts([p0.out, { ...p1.out, meta: { ...p1.out.meta, specsHash: 'x' } }]), /specsHash/);
  assert.equal(specPartOf(undefined), undefined);
  assert.deepEqual(specPartOf('3/4'), { i: 3, n: 4 });
  for (const bad of ['4/4', '1/0', '-1/2', 'a/b', '1']) assert.throws(() => specPartOf(bad), /expected i\/n/);
});

test('replay: a tennis match closing days after it begins is replayed; what cannot be replayed is counted by reason', async () => {
  const dir = tmp(), hist = path.join(dir, 'hist'), replay = path.join(dir, 'replay');
  writeTaHistory(hist, 3, [DISC_DAY]); // M1 11:00, M2 14:00, M3 17:00 UTC on Jul 14, each closing 150 min after its start
  const kal = path.join(hist, 'kalshi', 'KXATPMATCH');
  type Line = { ticker: string; event: string; openTime: number; closeTime: number; startTime?: number; result?: string; candles: Array<{ ts: number }> };
  const read = (f: string) => fs.readFileSync(f, 'utf8').split('\n').filter(Boolean).map((l) => JSON.parse(l) as Line);
  const lines = read(path.join(kal, `${DISC_DAY}.jsonl`)), tapes = read(path.join(kal, 'trades', `${DISC_DAY}.jsonl`)) as unknown as Array<{ ticker: string }>;
  const put = (day: string, ls: unknown[], trades: unknown[] = []) => {
    fs.writeFileSync(path.join(kal, `${day}.jsonl`), ls.map((x) => JSON.stringify(x)).join('\n') + '\n');
    if (trades.length) fs.writeFileSync(path.join(kal, 'trades', `${day}.jsonl`), trades.map((x) => JSON.stringify(x)).join('\n') + '\n');
  };
  const ev = (e: string) => lines.filter((m) => m.event.endsWith(e));
  // M1 postponed: it closes 3 days later (filed under Jul 17); M3 published a start after its close; M2-A stored twice
  // (a shorter copy on Jul 15); a traded market without candles, one without a result, and one closing 6 days after it
  // began (beyond the scan) beside them.
  const late = Date.parse('2026-07-17T13:30:00Z');
  put('2026-07-17', ev('M1').map((m) => ({ ...m, closeTime: late })), tapes.filter((t) => t.ticker.includes('M1-')));
  const m3 = ev('M3').map((m) => ({ ...m, startTime: m.closeTime + 3_600_000 }));
  const m2 = ev('M2');
  const base = { series: 'KXATPMATCH', openTime: Date.parse('2026-07-13T12:00:00Z'), startTime: Date.parse('2026-07-14T19:00:00Z'), closeTime: Date.parse('2026-07-14T21:00:00Z'), strike: null, cap: null };
  put(DISC_DAY, [...m2, ...m3, { ...base, ticker: 'KXATPMATCH-X-NC', event: 'KXATPMATCH-X', result: 'yes', candles: [] }, { ...base, ticker: 'KXATPMATCH-X-NR', event: 'KXATPMATCH-X', candles: m2[0].candles },
    { ...base, ticker: 'KXATPMATCH-X-UT', event: 'KXATPMATCH-X', result: 'no', candles: [], noVolume: true }], tapes.filter((t) => !t.ticker.includes('M1-')));
  put('2026-07-15', [{ ...m2[0], candles: m2[0].candles.slice(0, 20) }]);
  put('2026-07-20', [{ ...base, ticker: 'KXATPMATCH-Y-LATE', event: 'KXATPMATCH-Y', closeTime: Date.parse('2026-07-20T12:00:00Z'), result: 'yes', candles: m2[0].candles }]);
  await buildHistoryReplay({ historyDir: hist, outDir: replay, assets: [], fromDay: '2026-07-13', toDay: '2026-07-21', tennisSeries: ['KXATPMATCH'], log: () => {} });
  const manifest = JSON.parse(fs.readFileSync(path.join(replay, 'replay-manifest.json'), 'utf8')) as { tennis: Record<string, number>; tennisSkips: Record<string, unknown> };
  assert.equal(manifest.tennis[DISC_DAY], 6);
  assert.deepEqual(manifest.tennisSkips[DISC_DAY], { noCandles: 1, noResult: 1, dup: 1, lateClose: 0, startAfterClose: 2 });
  assert.deepEqual(manifest.tennisSkips['2026-07-20'], { ...noTennisSkips(), lateClose: 1 });
  assert.deepEqual(manifest.tennisSkips['2026-07-15'], noTennisSkips());
  const recs = (day: string) => zlib.gunzipSync(fs.readFileSync(path.join(replay, `md-${day}.jsonl.gz`))).toString('utf8').split('\n').filter(Boolean).map((l) => JSON.parse(l) as Record<string, unknown>);
  const d14 = recs(DISC_DAY);
  const mk = (t: string) => d14.find((r) => r.k === 'market' && r.ticker === t);
  assert.ok(mk(ev('M1')[0].ticker), 'the postponed match is listed on its begin day');
  assert.equal(mk(ev('M1')[0].ticker)!.closeTime, late);
  assert.equal(mk(m3[0].ticker)!.startTime, undefined, 'a start after the close is no start');
  assert.equal(d14.filter((r) => r.k === 'market' && r.ticker === m2[0].ticker).length, 1, 'a ticker stored twice is replayed once');
  // The longest line was kept: the Jul 14 line's quotes reach past the 20 minutes the Jul 15 copy has.
  const lastBook = Math.max(...d14.filter((r) => r.k === 'book' && r.ticker === m2[0].ticker).map((r) => r.t as number));
  assert.ok(lastBook > m2[0].candles[20].ts);
  assert.ok(!d14.some((r) => String(r.ticker ?? '').startsWith('KXATPMATCH-X-') || String(r.ticker ?? '').startsWith('KXATPMATCH-Y-')));
  assert.ok(recs('2026-07-17').some((r) => r.k === 'result' && r.ticker === ev('M1')[0].ticker), 'its result comes on its close day');
  // The sweep's view: the manifest's counts over the days a slice reads, and the union over shards in the check summary.
  const rs = replaySkipsOf(replay, '2026-07-12', '2026-07-21');
  assert.deepEqual(rs.unbuilt, ['2026-07-12']);
  assert.deepEqual(sumTennisSkips(Object.values(rs.byDay)), { noCandles: 1, noResult: 1, dup: 1, lateClose: 1, startAfterClose: 2 });
  // The head reader and the begin rule the scan uses.
  const h = tennisLineHead(JSON.stringify(lines[0]))!;
  assert.deepEqual([h.ticker, h.firstCandle, h.untraded, h.result], [lines[0].ticker, lines[0].candles[0].ts, false, lines[0].result]);
  assert.equal(tennisLineHead(JSON.stringify({ ...base, ticker: 'U', candles: [], noVolume: true }))!.untraded, true);
  assert.equal(tennisBegin({ openTime: 0, closeTime: 100 * MIN, startTime: 60 * MIN, firstCandle: 10 * MIN }), 30 * MIN);
  assert.equal(tennisBegin({ openTime: 0, closeTime: 100 * MIN, startTime: 100 * MIN, firstCandle: 50 * MIN }), 20 * MIN);
  assert.equal(tennisBegin({ openTime: 40 * MIN, closeTime: 100 * MIN, firstCandle: 50 * MIN }), 40 * MIN);
});

test('run: one sub-slice end to end on the fixture writes a C4 shard file the report gate accepts; nostart labelled and counted', async () => {
  const { prep, out, file, replay, specs } = await sliceRun(false);
  const m = out.meta;
  assert.equal(m.simVersion, 'tennis-ta-sim/4');
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
  assert.deepEqual(out.runs.map((r) => [r.id, r.stick ?? false, r.window ?? false, r.overrides.TENNIS_TRAIL_RATCHET, r.offsetMs]),
    [['A|s2|loose|F1', false, false, false, undefined], ['A|s2|loose|window', false, true, false, undefined], ['A|s2|prod|nopacer|F1', true, false, false, 1500]]);
  assert.ok(out.runs.filter((r) => !r.window).every((r) => r.pnl.length === 3));
  assert.ok(out.runs.every((r) => !('instances' in r)), 'the window instances live in the window block, aggregated, not in runs[]');
  assert.equal(out.familyB, undefined);
  // The one test's block (contract C12): the slice's events in matchList order with their end rule, one row per window arm
  // and leg (empty rows included: the report pools the legs into 'both' itself), and the candle index behind them.
  const wb = out.window;
  assert.deepEqual([wb.version, wb.settleFrac, wb.orderUsd, wb.twins, wb.seed], [WINDOW_VERSION, 0.3, 10, 3, 20261105]);
  assert.deepEqual(wb.events.map((e) => [e.event, e.series, e.tour, e.unit, e.day]), out.matchList.map((x) => [x.event, x.series, 'ATP', x.unit, x.day]));
  assert.ok(wb.events.every((e, i) => e.start === out.matchList[i].start && e.close === out.matchList[i].close && e.endRule <= e.close && e.endRule > e.start), JSON.stringify(wb.events));
  assert.deepEqual(wb.rows.map((r) => [r.id, r.leg]), [['A|s2|loose|window', 'underdog'], ['A|s2|loose|window', 'fav']]);
  for (const r of wb.rows) {
    assert.deepEqual([r.n.length, r.w.length, r.tn.length, r.tw.length], [3, 3, 3, 3]);
    assert.deepEqual(Object.keys(r.byPhase), ['pre', 'e20', 'p1', 'p2', 'p3']);
    assert.deepEqual([r.hist.tWin.length, r.hist.lenWin.length, r.hist.dip.length, r.hist.held.length], [HIST_EDGES.tWin.length + 1, HIST_EDGES.lenWin.length + 1, HIST_EDGES.dip.length + 1, HIST_EDGES.held.length + 1]);
    assert.equal(r.asks[0], r.n.reduce((s, x) => s + x, 0));
    assert.ok(r.w.every((w, i) => w <= r.n[i]) && r.tw.every((w, i) => w <= r.tn[i]) && r.endNoWin <= r.asks[0]);
  }
  assert.deepEqual([m.windowVersion, m.windowArms, m.windowRows, m.candleMarkets, m.batchHash], [WINDOW_VERSION, 1, 2, 6, undefined]);
  // The candle index's minutes and the substitutions of a close for a missing low (information): the fixture stores no low.
  assert.ok(typeof m.candleMinutes === 'number' && m.candleMinutes > 0 && m.candlesNoLow === m.candleMinutes, JSON.stringify([m.candleMinutes, m.candlesNoLow]));
  assert.equal(typeof m.windowInstances, 'number');
  assert.equal(out.familyBWindow, undefined);
  const meta = await readShardMeta(file);
  assert.deepEqual(meta, m);
  // The report reads the file's runs (offsetMs included) and its check_runs gate passes them.
  if (spawnSync('python3', ['-I', '-c', 'import numpy, scipy'], { encoding: 'utf8' }).status === 0) {
    const cr = checkRunsDir(path.dirname(file));
    assert.equal(cr.status, 0, cr.err.slice(-2000));
    const key = prep.expected[0].replace(/\.json\.gz$/, '');
    // The report knows the window arms (Amendment 4, its ARMS): the file's window arm and its block pass its gate.
    assert.ok(cr.out!.arms.includes('window'), 'research/tennis_ta_report.py ARMS must know the window arms');
    assert.deepEqual(cr.out!.lists, { [key]: [] });
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
  assert.deepEqual([o.window.version, o.window.events, o.window.rows.map((r) => [r.id, r.leg, r.n, r.asks])], [WINDOW_VERSION, [], [['A|s2|loose|window', 'underdog', [], [0, 0]], ['A|s2|loose|window', 'fav', [], [0, 0]]]]);
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
  const specs = batchFile();
  const base = { replay, from: '2026-07-27', to: '2026-08-04', 'units-list': 'W-2026-07-27', units: UNITS_FILE };
  const read = (f: string) => JSON.parse(zlib.gunzipSync(fs.readFileSync(f)).toString('utf8')) as ShardOut;
  const h = path.join(dir, 'a-shold-0-0.json.gz');
  await cmdRun({ ...base, stage: 'hold', specs, out: h }); // pool defaults to hold at stage hold
  const ho = read(h);
  assert.deepEqual([ho.meta.stage, ho.meta.pool, ho.meta.replayVersion, ho.meta.specsHash], ['hold', 'hold', REPLAY_VERSION, specsHash(validateHoldBatch(BATCH).specs)]);
  // The read's identity: the batch file's hash, the league run and the hot spots, with every window arm's rows.
  assert.deepEqual([ho.meta.batchHash, ho.meta.leagueRun, ho.meta.batch, ho.meta.windowVersion, ho.meta.windowArms], [fileHash(specs), '19876543210', BATCH.batch, WINDOW_VERSION, 3]);
  assert.deepEqual(ho.window.rows.map((r) => [r.id, r.leg]), BATCH_IDS.filter((id) => id.endsWith('|window')).flatMap((id) => [[id, 'underdog'], [id, 'fav']]));
  assert.deepEqual(ho.window.events.map((e) => e.event), ho.matchList.map((x) => x.event));
  // The window gate at stage hold (checkShards, before the ledger step): every batch member's |window rows in the file,
  // or the problem names the member and the file fails before the opening is recorded.
  const hp = { specIds: BATCH_IDS, windowVersion: WINDOW_VERSION, stage: 'hold' as const };
  assert.deepEqual(windowArmsOf(BATCH_IDS), BATCH_IDS.filter((id) => id.endsWith('|window')));
  const hblocks: ShardBlocks = { events: ho.matchList.map((x) => x.event), window: ho.window };
  assert.deepEqual(windowBlockProblems('a-shold-0-0.json.gz', hp, ho.meta, hblocks), []);
  const cut = { ...ho.window, rows: ho.window.rows.filter((r) => r.id !== 'A|s1|m0.005|f0.05|o0.005|w120|window') };
  const why = " (a batch member's read: every member's |window rows must be in every file before the opening is recorded)";
  assert.deepEqual(windowBlockProblems('a-shold-0-0.json.gz', hp, { ...ho.meta, windowRows: cut.rows.length }, { ...hblocks, window: cut }), [
    `a-shold-0-0.json.gz: window block row A|s1|m0.005|f0.05|o0.005|w120|window / underdog missing${why}`, `a-shold-0-0.json.gz: window block row A|s1|m0.005|f0.05|o0.005|w120|window / fav missing${why}`,
  ]);
  assert.match(String(ho.meta.evidence), /H-HOLD/);
  assert.deepEqual(ho.meta.holdFolds, holdFolds());
  assert.deepEqual(ho.matchList.map((x) => [x.event, x.day, x.pool, x.fold]), [
    ['KXATPMATCH-20260802M1', '2026-08-02', 'hold', 1], ['KXATPMATCH-20260802M2', '2026-08-02', 'nostart', null], ['KXATPMATCH-20260802M3', '2026-08-02', 'hold', 1],
  ]);
  assert.deepEqual(ho.meta.coverage.pools, { hold: { matches: 2, units: 1 }, nostart: { matches: 1, units: 1 } });
  assert.deepEqual(ho.runs.map((r) => r.id), BATCH_IDS);
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
  const parts = await readShardParts(file, ['meta', 'matchList', 'window', 'familyBWindow']);
  assert.deepEqual(parts.meta, out.meta);
  assert.deepEqual(parts.familyBWindow, out.familyBWindow);
  const blocks: ShardBlocks = { events: (parts.matchList as Array<{ event: string }>).map((m) => m.event), window: parts.window, familyBWindow: parts.familyBWindow };
  assert.deepEqual(checkShards(prep, [...prep.expected], [{ file: prep.expected[0], meta: parts.meta as ShardMeta, blocks }], '42').problems, []);
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

test('check: the window block (C12) is gated by the sweep\'s check itself, before a hold run\'s opening is recorded', async () => {
  const { prep, out, file } = await sliceRun(false);
  const parts = await readShardParts(file, ['meta', 'matchList', 'window', 'familyBWindow']);
  assert.deepEqual([parts.meta, parts.window, parts.familyBWindow], [out.meta, out.window, undefined]);
  const blocksOf = (o: ShardOut): ShardBlocks => ({ events: o.matchList.map((m) => m.event), window: o.window, ...(o.familyBWindow ? { familyBWindow: o.familyBWindow } : {}) });
  const check = (o: ShardOut) => checkShards(prep, [...prep.expected], [{ file: prep.expected[0], meta: o.meta, blocks: blocksOf(o) }], '42');
  const good = check(out);
  assert.deepEqual(good.problems, []);
  assert.deepEqual([good.summary.windowArms, good.summary.windowBlocks, good.summary.windowInstances], [1, 1, out.meta.windowInstances]);
  // Without the blocks only the meta is checked (the command always reads them; the summary says how many it read).
  assert.equal(checkShards(prep, [...prep.expected], [{ file: prep.expected[0], meta: out.meta }], '42').summary.windowBlocks, 0);
  const clone = () => JSON.parse(JSON.stringify(out)) as ShardOut;
  const broken = (f: (o: ShardOut) => void, re: RegExp) => { const o = clone(); f(o); const pr = check(o).problems; assert.ok(pr.some((x) => re.test(x)), `${re}: ${JSON.stringify(pr)}`); };
  broken((o) => { delete (o as Partial<ShardOut>).window; }, /no window block with events and rows \(C12\): the plan's 1 window arm\(s\) have no rows/);
  broken((o) => { o.window.version = 'tennis-ta-window/0'; }, /window block version "tennis-ta-window\/0", expected "tennis-ta-window\/1"/);
  broken((o) => { o.window.seed = 1; }, /window block seed 1, the one test's is 20261105/);
  broken((o) => { o.window.settleFrac = 0.25; }, /window block settleFrac 0\.25, the one test's is 0\.3/);
  broken((o) => { o.window.events.reverse(); }, /events are not in matchList order \(first at index 0\)/);
  broken((o) => { o.window.events.pop(); }, /lists 2 event\(s\) for a matchList of 3/);
  broken((o) => { o.window.events[1].endRule = o.window.events[1].close + 1; }, /event 1 \("KXATPMATCH-20260714M2"\) lacks an event, tour, day, start, close or an end rule at or before its close/);
  broken((o) => { o.window.rows.pop(); }, /window block row A\|s2\|loose\|window \/ fav missing$/);
  broken((o) => { o.window.rows.push({ ...o.window.rows[0] }); }, /row "A\|s2\|loose\|window" \/ underdog: appears twice/);
  broken((o) => { o.window.rows.push({ ...o.window.rows[0], id: 'A|s2|other|window' }); }, /row "A\|s2\|other\|window" \/ underdog: not a window arm of the plan/);
  broken((o) => { (o.window.rows[0] as { leg: string }).leg = 'both'; }, /row "A\|s2\|loose\|window" \/ both: no id, or a leg that is not underdog or fav/);
  broken((o) => { o.window.rows[0].n.push(0); }, /row "A\|s2\|loose\|window" \/ underdog: n is not a list of counts over the 3 event\(s\)/);
  broken((o) => { o.window.rows[0].tw = [-1, 0, 0]; }, /tw is not a list of counts/);
  broken((o) => { o.window.rows[0].w = o.window.rows[0].n.map((x) => x + 1); }, /more windows than instances on an event/);
  broken((o) => { o.window.rows[0].hist.dip.pop(); }, /hist is not \{tWin, lenWin, dip, held\} counts over the HIST_EDGES bins/);
  broken((o) => { delete o.window.rows[0].byPhase.p3; }, /byPhase is not \{pre, e20, p1, p2, p3: \[n, w\]\}/);
  broken((o) => { (o.window.rows[0] as { endNoWin: unknown }).endNoWin = '0'; }, /endNoWin is not a count/);
  broken((o) => { o.window.rows[0].asks = [1] as unknown as [number, number]; }, /asks is not \[n, sum of asks\]/);
  broken((o) => { o.meta.windowRows = 1; }, /meta\.windowRows 1, the block has 2 row\(s\)/);
  broken((o) => { o.meta.windowArms = 2; }, /meta\.windowArms 2, the plan has 1 window arm\(s\)/);
  broken((o) => { o.matchList.pop(); }, /matchList has 2 match\(es\), meta\.coverage\.matches says 3/);
  broken((o) => { o.familyBWindow = { version: WINDOW_VERSION, rows: [{ ...o.window.rows[0], id: 'rsi|1m|up', leg: undefined, n: [1, 2, 3, 4] }] } as unknown as ShardOut['familyBWindow']; },
    /familyBWindow block row "rsi\|1m\|up": n is not a list of counts over the 3 event\(s\)/);
  broken((o) => { o.familyBWindow = { version: 'tennis-ta-window/0', rows: [] }; }, /familyBWindow block version "tennis-ta-window\/0" differs from the window block's/);
  broken((o) => { o.meta.familyBWindowRows = 3; }, /meta\.familyBWindowRows is set but the file has no familyBWindow block/);
  // A well-formed file passes with every row intact, so the gate is on the shape, never on a number.
  const zero = clone();
  for (const r of zero.window.rows) { r.w = r.w.map(() => 0); r.tw = r.tw.map(() => 0); }
  assert.deepEqual(check(zero).problems, []);
  // The check command as the workflow runs it before the ledger step: exit 0 and the summary on the good set; exit 1
  // with the problem in --out when a file's block lacks a row (here: the rows of the plan's one window arm). The
  // fixture's history has no complete-download record, so the file gets the one a finished download writes (the
  // history gate has its own tests): the window gate is what runs here.
  const dir = path.dirname(file), listing = path.join(dir, 'listed.txt'), planFile = path.join(dir, 'plan.json'), outFile = path.join(dir, 'shards-check.json');
  fs.writeFileSync(listing, prep.expected.join('\n') + '\n');
  fs.writeFileSync(planFile, JSON.stringify(prep));
  const listed = (o: ShardOut) => { const c = o.meta.coverage.series!.KXATPMATCH; c.listed = { from: c.need!.from, to: c.need!.to }; return o; };
  const run = () => spawnSync('node', ['--import', 'tsx', path.join(REPO, 'research', 'tennisTaSweep.ts'), 'check', '--dir', dir, '--listing', listing, '--prep', planFile, '--run', '42', '--out', outFile], { encoding: 'utf8', cwd: REPO });
  fs.writeFileSync(file, zlib.gzipSync(JSON.stringify(listed(clone()))));
  const ok = run();
  assert.equal(ok.status, 0, ok.stderr.slice(-2000));
  const okOut = JSON.parse(fs.readFileSync(outFile, 'utf8')) as { problems: string[]; windowBlocks: number; windowArms: number };
  assert.deepEqual([okOut.problems, okOut.windowBlocks, okOut.windowArms], [[], 1, 1]);
  assert.match(ok.stdout, /window block \(C12\): 1 arm\(s\) x 2 legs in the plan, read in 1 of 1 file\(s\)/);
  const bad = listed(clone());
  bad.window.rows = [];
  fs.writeFileSync(file, zlib.gzipSync(JSON.stringify(bad)));
  const fail = run();
  assert.equal(fail.status, 1);
  assert.match(fail.stderr, /::error::.*window block row A\|s2\|loose\|window \/ underdog missing/);
  const failOut = JSON.parse(fs.readFileSync(outFile, 'utf8')) as { problems: string[] };
  assert.ok(failOut.problems.some((x) => x.endsWith('window block row A|s2|loose|window / fav missing')) && failOut.problems.some((x) => x.includes('meta.windowRows 2, the block has 0 row(s)')), JSON.stringify(failOut.problems));
});

test('run on R: a recorded match before FULL_BOOK_FROM (practice, Amendment 4 item 9) is never owned, only counted', async () => {
  const dir = tmp(), rec = path.join(dir, 'rec');
  // KXATPMATCH-R1: start Jul 14 10:00 UTC (unit W-2026-07-13), close a week on. By the H rules its times are disc; on R
  // it is practice (the bot's recordings before the Nov 10 book fix), and the run's admit() must label it so.
  const plan = writeTaRecording(rec, '2026-07-14');
  const pm = { start: plan.start, close: plan.start + 7 * DAY, startPublished: true };
  assert.deepEqual([poolOf(pm, units), recordedPoolOf(pm, units), unitOf(plan.start, units)], ['disc', 'practice', 'W-2026-07-13']);
  const out = path.join(dir, 'r.json.gz');
  await cmdRun({ replay: rec, stratum: 'R', from: '2026-07-13', to: '2026-07-21', 'units-list': 'W-2026-07-13', stage: '2', specs: specFile(), pool: 'disc', units: UNITS_FILE, out });
  const o = JSON.parse(zlib.gunzipSync(fs.readFileSync(out)).toString('utf8')) as ShardOut;
  assert.deepEqual([o.meta.stratum, o.meta.stratumLabel, o.meta.lookbackDays, o.meta.evidence], ['R', 'R', 7, 'recorded books']);
  // Nothing of the practice match reaches the file: no matchList row, episode, P&L, window event or instance.
  assert.deepEqual(o.matchList, []);
  assert.deepEqual(o.meta.coverage.pools, { disc: { matches: 0, units: 0 }, nostart: { matches: 0, units: 0 }, practice: { matches: 1, units: 1 } });
  assert.deepEqual([o.meta.coverage.matches, o.meta.matches, o.meta.windowInstances], [0, 0, 0]);
  assert.ok(o.runs.every((r) => r.pnl.length === 0 && r.episodes.length === 0), JSON.stringify(o.runs.map((r) => [r.id, r.pnl.length, r.episodes.length])));
  assert.deepEqual([o.window.events, o.window.rows.map((r) => [r.id, r.leg, r.n, r.asks, r.endNoWin])], [[], [['A|s2|loose|window', 'underdog', [], [0, 0], 0], ['A|s2|loose|window', 'fav', [], [0, 0], 0]]]);
  // The same recording swept by a unit list without its unit counts nothing: the practice count is of the slice's own.
  const other = path.join(dir, 'other.json.gz');
  await cmdRun({ replay: rec, stratum: 'R', from: '2026-07-13', to: '2026-07-21', 'units-list': 'WIM-2026-06-29', stage: '2', specs: specFile(), pool: 'disc', units: UNITS_FILE, out: other });
  assert.deepEqual((JSON.parse(zlib.gunzipSync(fs.readFileSync(other)).toString('utf8')) as ShardOut).meta.coverage.pools, { disc: { matches: 0, units: 0 }, nostart: { matches: 0, units: 0 }, practice: { matches: 0, units: 0 } });
  // An H run reports no practice count (Kalshi's own history is unaffected).
  const { out: h } = await sliceRun(false);
  assert.equal(h.meta.coverage.pools!.practice, undefined);
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

/** A workflow file as data (PyYAML; its `on` key, which YAML 1.1 reads as true, back under 'on'). */
function yamlOf(file: string): unknown {
  const r = spawnSync('python3', ['-I', '-c', 'import json, sys, yaml\nd = yaml.safe_load(open(sys.argv[1]))\nif True in d: d["on"] = d.pop(True)\nprint(json.dumps(d))', file], { encoding: 'utf8' });
  assert.equal(r.status, 0, r.stderr);
  return JSON.parse(r.stdout);
}

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
  assert.deepEqual(on, { push: { branches: ['claude/project-thread-7817be'], paths: ['research/tennis-ta/sweep-request.json'] } });
  const text = fs.readFileSync(wf, 'utf8');
  assert.ok(!text.includes('trials.jsonl'), 'the interim ledger append is gone');
  // The report job is the reusable .github/workflows/tennis-ta-report.yml, called with the sweep's own run and commit
  // (the rescore workflow calls it too, with a finished run's).
  const doc = yamlOf(wf) as { jobs: Record<string, Record<string, unknown>>; permissions: Record<string, string> };
  assert.deepEqual(doc.jobs.report, {
    needs: ['prep', 'shard'], if: "${{ !cancelled() && needs.prep.result == 'success' && needs.shard.result == 'success' }}",
    uses: './.github/workflows/tennis-ta-report.yml',
    with: { run_id: '${{ github.run_id }}', sweep_sha: '${{ github.sha }}', pool: '${{ needs.prep.outputs.pool }}', stage: '${{ needs.prep.outputs.stage }}' },
    secrets: 'inherit',
  });
  assert.deepEqual(doc.permissions, { contents: 'write', actions: 'read' });
  const rf = path.join(REPO, '.github', 'workflows', 'tennis-ta-report.yml');
  const rr = ymlCheck(rf);
  assert.equal(rr.status, 0, `${rr.err}\n${(rr.out?.problems ?? []).join('\n')}`);
  assert.ok(runBlocks + rr.out!.runBlocks >= 15);
  assert.deepEqual(Object.keys((rr.out!.on as { workflow_call: { inputs: object } }).workflow_call.inputs), ['run_id', 'sweep_sha', 'pool', 'stage']);
  const report = rr.out!.jobs.report;
  const idx = (re: RegExp) => report.findIndex((s) => re.test(s.name));
  const body = (re: RegExp) => report[idx(re)]?.run ?? '';
  // registry.py from main, else the registry thread's branch; passed to the report with the commit sha.
  assert.match(body(/^Registry module/), /refs\/heads\/main:refs\/remotes\/origin\/main/);
  assert.match(body(/^Registry module/), /claude\/project-thread-79ntof/);
  assert.match(body(/^Registry module/), /git show "\$SRC:research\/registry\.py" > \/tmp\/registry\.py/);
  assert.match(body(/^Report$/), /--registry-py \/tmp\/registry\.py --sha "\$SWEEP_SHA" --report-sha "\$GITHUB_SHA"/);
  assert.match(body(/^Registry rows valid/), /python3 -I \/tmp\/registry\.py validate "\$ROWS"/);
  assert.match(body(/^Registry rows valid/), /contract_type == "tennis"/);
  const up = body(/^Registry upload/);
  assert.match(up, /rclone copyto "\$ROWS" "gdrive:kalshi-bot-archive\/registry\/shards\/tennis-ta\/\$RUN\.jsonl"/);
  assert.match(up, /\.problems \| length\) == 0/);
  // Order: registry module, completeness check, report, validation, keep, upload, then the commit comment.
  const order = [/^Registry module/, /^Shards/, /^Report$/, /^Registry rows valid/, /^Keep the report/, /^Registry upload/, /^Report as a commit comment/].map(idx);
  assert.ok(order.every((x) => x >= 0), JSON.stringify(order));
  assert.deepEqual([...order].sort((a, b) => a - b), order);
  assert.match(body(/^Report as a commit comment/), /commits\/\$SWEEP_SHA\/comments/);
  // The registry rows file marks a run scored, so the Keep step uploads it last.
  assert.match(body(/^Keep the report/), /rclone copy report "\$R" --exclude "registry-v1-\$RUN\.jsonl"\n\s*rclone copyto "report\/registry-v1-\$RUN\.jsonl" "\$R\/registry-v1-\$RUN\.jsonl"/);
  assert.ok(!fs.readFileSync(rf, 'utf8').includes('$GITHUB_RUN_ID'), 'the report names its run by input only');
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
  // The completeness check (the sweep's own, before the ledger step) is the C12 window gate: a broken block never
  // reaches the append.
  assert.match(body(/^Shards/), /node --import tsx research\/tennisTaSweep\.ts check --dir shards --listing listed\.txt --prep prep\/plan\.json --run "\$RUN" --out report\/shards-check\.json/);
  assert.match(report[idx(/^Shards/)].name, /window block whole/);
  assert.match(body(/^Shards/), /window block[\s\S]*before the ledger step/);
  assert.ok(body(/^Openings ledger/).includes(`LEDGER=${OPENINGS_LEDGER}`));
  assert.match(body(/^Openings ledger/), /\{hash: \$h, run: \$r, ts: \$ts, ids: \$p\[0\]\.specIds, pool: "hold"\}/);
  // Amendment 4: the blind-open is keyed by the batch file's hash, and a disc run's report carries the league.
  assert.match(body(/^Openings ledger/), /jq -r '\.batchHash \/\/ ""' prep\/plan\.json/);
  assert.ok(!body(/^Openings ledger/).includes('.specsHash'));
  assert.match(body(/^Report$/), /league\.md league\.csv league\.json/);
  assert.match(body(/^Report$/), /\[ "\$POOL" = disc \]/);
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
  const rr = ymlCheck(path.join(REPO, '.github', 'workflows', 'tennis-ta-report.yml'));
  const readStep = step('prep', /^Openings ledger/), appendStep = rr.out!.jobs.report.find((s) => /^Openings ledger/.test(s.name))!.run!;
  const dir = tmp(), bin = path.join(dir, 'bin'), drive = path.join(dir, 'drive'), work = path.join(dir, 'work');
  fs.mkdirSync(bin); fs.mkdirSync(path.join(drive, 'kalshi-bot-archive', 'models', 'tennis-ta'), { recursive: true }); fs.mkdirSync(path.join(work, 'prep'), { recursive: true });
  fs.writeFileSync(path.join(bin, 'rclone'), FAKE_RCLONE, { mode: 0o755 });
  const ledger = path.join(drive, 'kalshi-bot-archive', 'models', 'tennis-ta', 'state', 'openings.jsonl');
  const run = (script: string, env: Record<string, string> = {}) => spawnSync('bash', ['-c', script], { cwd: work, encoding: 'utf8', env: { ...process.env, PATH: `${bin}:${process.env.PATH}`, FAKE_DRIVE: drive, ...env } });
  // prep, no ledger yet (no state/ folder): read as empty, and prep accepts the hold list.
  let x = run(readStep);
  assert.equal(x.status, 0, x.stderr);
  assert.equal(fs.readFileSync(path.join(work, 'prep', 'openings.jsonl'), 'utf8'), '');
  const f = batchFile();
  const p = prepare(JSON.stringify({ stage: 'hold' }), unitsText, f, { openings: fs.readFileSync(path.join(work, 'prep', 'openings.jsonl'), 'utf8') });
  fs.writeFileSync(path.join(work, 'prep', 'plan.json'), JSON.stringify(p));
  // A Drive that cannot be read fails the read (never "not opened").
  x = run(readStep, { FAKE_DRIVE_DOWN: '1' });
  assert.notEqual(x.status, 0);
  // report: a disc run records nothing; the hold run appends {hash, run, ts, ids, pool} once.
  x = run(appendStep, { STAGE: '1', RUN: '100' });
  assert.equal(x.status, 0, x.stderr);
  assert.ok(!fs.existsSync(ledger));
  x = run(appendStep, { STAGE: 'hold', RUN: '100' });
  assert.equal(x.status, 0, x.stderr + x.stdout);
  const rows = () => fs.readFileSync(ledger, 'utf8').split('\n').filter(Boolean).map((l) => JSON.parse(l) as Record<string, unknown>);
  assert.deepEqual(rows().map((o) => [o.hash, o.run, o.ids, o.pool, Object.keys(o).sort()]), [[p.batchHash, '100', p.specIds, 'hold', ['hash', 'ids', 'pool', 'run', 'ts']]]);
  assert.match(String(rows()[0].ts), /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/);
  // A re-run of the report job keeps the one row (idempotent by run id).
  x = run(appendStep, { STAGE: 'hold', RUN: '100' });
  assert.equal(x.status, 0, x.stderr);
  assert.match(x.stdout, /already in the ledger/);
  assert.equal(rows().length, 1);
  // prep now reads the row and refuses the list; another run of it fails in the report job too.
  x = run(readStep);
  assert.equal(x.status, 0, x.stderr);
  assert.throws(() => prepare(JSON.stringify({ stage: 'hold' }), unitsText, f, { openings: fs.readFileSync(path.join(work, 'prep', 'openings.jsonl'), 'utf8') }), /already read on H-HOLD \(run 100,/);
  x = run(appendStep, { STAGE: 'hold', RUN: '101' });
  assert.notEqual(x.status, 0);
  assert.match(x.stdout, /already opened on H-HOLD by run 100/);
  assert.equal(rows().length, 1);
  // Another list appends after a ledger line without its newline; a damaged ledger is never overwritten.
  fs.writeFileSync(ledger, fs.readFileSync(ledger, 'utf8').trimEnd());
  const p2 = { ...p, batchHash: 'ab'.repeat(32), specIds: ['A|s1|m0.02|f0.4|o0.02|w300|window', 'A|s1|m0.02|f0.4|o0.02|w300|F1'] };
  fs.writeFileSync(path.join(work, 'prep', 'plan.json'), JSON.stringify(p2));
  x = run(appendStep, { STAGE: 'hold', RUN: '102' });
  assert.equal(x.status, 0, x.stderr + x.stdout);
  assert.deepEqual(rows().map((o) => [o.hash, o.run]), [[p.batchHash, '100'], ['ab'.repeat(32), '102']]);
  // The ledger naming this run with another batch fails; a plan without a batch hash (not a hold plan) records nothing.
  fs.writeFileSync(path.join(work, 'prep', 'plan.json'), JSON.stringify({ ...p2, batchHash: 'cd'.repeat(32) }));
  x = run(appendStep, { STAGE: 'hold', RUN: '102' });
  assert.notEqual(x.status, 0);
  assert.match(x.stdout, /holds run 102 with another batch/);
  fs.writeFileSync(path.join(work, 'prep', 'plan.json'), JSON.stringify({ ...p2, batchHash: undefined }));
  x = run(appendStep, { STAGE: 'hold', RUN: '104' });
  assert.notEqual(x.status, 0);
  assert.match(x.stdout, /no batch hash/);
  assert.equal(rows().length, 2);
  fs.writeFileSync(ledger, '{"hash": "x"}\n{broken\n');
  x = run(appendStep, { STAGE: 'hold', RUN: '103' });
  assert.notEqual(x.status, 0);
  assert.equal(fs.readFileSync(ledger, 'utf8'), '{"hash": "x"}\n{broken\n');
});

test('workflow rescore: a finished, complete, unscored sweep run is scored again by the same report job', (t) => {
  const probe = spawnSync('python3', ['-I', '-c', 'import yaml'], { encoding: 'utf8' });
  if (probe.status !== 0 || spawnSync('jq', ['--version']).status !== 0) { t.skip('python3 with PyYAML, or jq, is not available'); return; }
  const wf = path.join(REPO, '.github', 'workflows', 'tennis-ta-rescore.yml');
  const r = ymlCheck(wf);
  assert.equal(r.status, 0, `${r.err}\n${(r.out?.problems ?? []).join('\n')}`);
  const doc = yamlOf(wf) as { on: unknown; concurrency: unknown; permissions: unknown; jobs: Record<string, Record<string, unknown>> };
  assert.deepEqual(doc.on, { push: { branches: ['claude/project-thread-7817be'], paths: ['research/tennis-ta/rescore-request.json'] } });
  // The sweep's concurrency group: a rescore waits for a running sweep.
  assert.deepEqual(doc.concurrency, (yamlOf(path.join(REPO, '.github', 'workflows', 'tennis-ta-sweep.yml')) as { concurrency: unknown }).concurrency);
  assert.deepEqual(doc.permissions, { contents: 'write', actions: 'read' });
  assert.deepEqual(doc.jobs.report, {
    needs: 'resolve', uses: './.github/workflows/tennis-ta-report.yml', secrets: 'inherit',
    with: { run_id: '${{ needs.resolve.outputs.run_id }}', sweep_sha: '${{ needs.resolve.outputs.sweep_sha }}', pool: '${{ needs.resolve.outputs.pool }}', stage: '${{ needs.resolve.outputs.stage }}' },
  });
  const steps = r.out!.jobs.resolve, at = (re: RegExp) => steps.findIndex((s) => re.test(s.name));
  assert.ok(at(/^Request and the run it names$/) < at(/^Not scored yet$/) && at(/^Not scored yet$/) < at(/^Pool and stage/));
  // The request step against a stand-in gh: only a completed tennis TA sweep of this branch whose shard legs all
  // succeeded passes, and it hands on the run id and the sweep's commit.
  const dir = tmp(), bin = path.join(dir, 'bin'), work = path.join(dir, 'work');
  fs.mkdirSync(bin); fs.mkdirSync(path.join(work, 'research', 'tennis-ta'), { recursive: true });
  fs.writeFileSync(path.join(bin, 'gh'), `#!/usr/bin/env bash
case "$2" in
  */jobs*) printf '%s\\n' "$FAKE_JOBS" ;;
  *) printf '%s\\n' "$FAKE_RUN" ;;
esac
`, { mode: 0o755 });
  const sha = 'ab'.repeat(20);
  const runJson = (o: Record<string, string> = {}) => JSON.stringify({ path: '.github/workflows/tennis-ta-sweep.yml', head_branch: 'claude/project-thread-7817be', status: 'completed', head_sha: sha, ...o });
  const go = (run: unknown, fakeRun: string, jobs = 'shard 0 (a)\tsuccess\nshard 1 (b)\tsuccess\nprep\tsuccess') => {
    fs.writeFileSync(path.join(work, 'research', 'tennis-ta', 'rescore-request.json'), JSON.stringify({ run, note: 'test' }));
    const out = path.join(dir, `out-${Math.random()}`);
    const x = spawnSync('bash', ['-c', steps[at(/^Request and the run it names$/)].run!], { cwd: work, encoding: 'utf8',
      env: { ...process.env, PATH: `${bin}:${process.env.PATH}`, FAKE_RUN: fakeRun, FAKE_JOBS: jobs, GITHUB_OUTPUT: out, GITHUB_REPOSITORY: 'o/r', GITHUB_REF_NAME: 'claude/project-thread-7817be', GITHUB_SHA: 'cd'.repeat(20) } });
    return { status: x.status, text: x.stdout + x.stderr, out: fs.existsSync(out) ? fs.readFileSync(out, 'utf8') : '' };
  };
  let x = go('43077154976', runJson());
  assert.equal(x.status, 0, x.text);
  assert.equal(x.out, `run_id=43077154976\nsweep_sha=${sha}\n`);
  x = go(43077154976, runJson());
  assert.equal(x.status, 0, x.text);
  assert.notEqual(go('12a', runJson()).status, 0);
  x = go('1', runJson({ path: '.github/workflows/tennis-ta-data.yml' }));
  assert.ok(x.status !== 0 && /not a tennis TA sweep/.test(x.text), x.text);
  x = go('1', runJson({ status: 'in_progress' }));
  assert.ok(x.status !== 0 && /only a finished sweep/.test(x.text), x.text);
  x = go('1', runJson({ head_branch: 'main' }));
  assert.ok(x.status !== 0 && /swept branch main/.test(x.text), x.text);
  x = go('1', runJson(), 'shard 0 (a)\tsuccess\nshard 1 (b)\tfailure');
  assert.ok(x.status !== 0 && /shard 1 \(b\)/.test(x.text), x.text);
  x = go('1', runJson(), 'prep\tfailure');
  assert.ok(x.status !== 0 && /0 shard leg/.test(x.text), x.text);
});

test('practice (Amendment 4 item 9): recorded matches before FULL_BOOK_FROM are pool practice, never requestable or scored', () => {
  assert.equal(FULL_BOOK_FROM, Date.parse('2026-11-10T03:44:00Z'));
  assert.ok(POOLS.includes('practice'));
  const m = (start: number) => ({ start, close: start + 3 * H, startPublished: true });
  // A recorded match before the book fix is practice whatever the H rules would say of its time; from the fix on, the H
  // rules apply (under the Nov 5 cutoff every later match is out until a later cutoff opens its lockbox week).
  assert.equal(recordedPoolOf(m(Date.parse('2026-10-25T14:00:00Z')), units), 'practice');
  assert.equal(poolOf(m(Date.parse('2026-10-25T14:00:00Z')), units), 'hold');
  assert.equal(recordedPoolOf(m(Date.parse('2026-07-14T14:00:00Z')), units), 'practice');
  assert.equal(recordedPoolOf(m(FULL_BOOK_FROM - 1), units), 'practice');
  assert.equal(recordedPoolOf(m(FULL_BOOK_FROM), units), poolOf(m(FULL_BOOK_FROM), units));
  assert.equal(recordedPoolOf(m(FULL_BOOK_FROM), units), 'out');
  assert.match(poolRefusal('practice')!, /never scored[\s\S]*practice data/);
  assert.throws(() => parseRequest({ stage: '1', pool: 'practice' }, units), /pool 'practice' is never scored/);
  assert.throws(() => assertPool('practice', '2'), /practice data/);
  for (const u of units) assert.equal(poolInterval(u, 'practice'), undefined);
  assert.ok(units.every((u) => !unitPools(u).includes('practice')));
  assert.equal(tourOf('KXWTAMATCH'), 'WTA');
  assert.equal(tourOf('KXATPMATCH'), 'ATP');
});

test('candleIndex: the window rule\'s view of every market the slice reads, parsed once from the history day files', () => {
  const dir = tmp(), hist = path.join(dir, 'hist');
  writeTaHistory(hist, 3, ['2026-07-14']);
  const series = path.join(hist, 'kalshi', 'KXATPMATCH');
  const idx = candleIndex([series], '2026-07-13', '2026-07-21', 1);
  assert.equal(idx.size, 6);
  const lines = fs.readFileSync(path.join(series, '2026-07-14.jsonl'), 'utf8').split('\n').filter(Boolean).map((l) => JSON.parse(l) as { ticker: string; closeTime: number; candles: Parameters<typeof minuteCandles>[0] });
  for (const m of lines) {
    const mc = idx.get(m.ticker)!;
    assert.deepEqual(mc, minuteCandles(m.candles, m.closeTime));
    assert.ok(mc.length > 1 && mc.every((c, i) => (i === 0 || c.ts > mc[i - 1].ts) && c.ts <= m.closeTime && c.twoSided), m.ticker);
    assert.ok(eligibleMinutes(mc, m.closeTime).length > 0);
  }
  // The span the slice reads: from its first day minus the lookback to its last day plus the close tail.
  assert.equal(candleIndex([series], '2026-07-17', '2026-07-21', 1).size, 0);
  assert.equal(candleIndex([series], '2026-07-15', '2026-07-21', 1).size, 6, 'the lookback day');
  // Closes read up to CLOSE_TAIL_DAYS after the slice's end (the replay's close scan plus a day): the markets close Jul 14.
  const endBefore = (k: number) => new Date(Date.parse('2026-07-14') - k * DAY).toISOString().slice(0, 10);
  assert.equal(CLOSE_TAIL_DAYS, TENNIS_CLOSE_SCAN_DAYS + 1);
  assert.equal(candleIndex([series], '2026-07-01', endBefore(CLOSE_TAIL_DAYS - 1), 1).size, 6, 'the close tail');
  assert.equal(candleIndex([series], '2026-07-01', endBefore(CLOSE_TAIL_DAYS), 1).size, 0);
  // A ticker stored on two lines keeps the line with the most candles, whichever day file comes first.
  const one = lines[0];
  fs.writeFileSync(path.join(series, '2026-07-13.jsonl'), `${JSON.stringify({ ...one, candles: one.candles.slice(0, 3) })}\n${JSON.stringify({ ...lines[1], candles: [] })}\n`);
  const idx2 = candleIndex([series], '2026-07-13', '2026-07-21', 1);
  assert.deepEqual(idx2.get(one.ticker), minuteCandles(one.candles, one.closeTime));
  assert.deepEqual(idx2.get(lines[1].ticker), minuteCandles(lines[1].candles, lines[1].closeTime));
  assert.equal(candleIndex([path.join(hist, 'kalshi', 'NONE')], '2026-07-13', '2026-07-21').size, 0);
});
