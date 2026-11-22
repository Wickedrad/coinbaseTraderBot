import assert from 'node:assert/strict';
import fs from 'fs';
import path from 'path';
import zlib from 'zlib';
import { test } from 'node:test';
import { spawnSync } from 'node:child_process';
import crypto from 'crypto';
import {
  assertDisjoint, assertModelFitDays, assertHeldOut, auc, CONFIRM_DAYS, checkDepthModelReuse, checkReal15m, collectSweep, corrMatrix, dayRows, discriminate, discriminatePerDay, FEATURE_CODE_VERSION, FEATURES, fastRows, filledDayRows, followDiag, isBlind, loadRealSide,
  judgeSweepRows, loadDepthParamsFile, MIN_CUSTOM_JUDGED_DAYS, MIN_DAY_LIVES, MIN_SWEEP_LIVES, outcome, parseDays, parseFailedSteps, prepDay, prepReport, prepStatus, quantile, quantiles3, real15mError, real15mTag,
  REAL15M_VERSION, realMetaDiff, resolveSplit, resolveSweepFit, restrictLine, rowBuilder, runSweep, type Row, SPLITS, stageVerdict, stressAuc, sweepShardName, topCorrDiffs, twinSource, type SweepCollected,
} from '../research/historyTwin';
import {
  CEM_SD_FLOOR, cemStep, clipParams, describeParams, eliteOf, eliteStats, fromSpace, generationCandidates, latinHypercube, mergeShards, parentsFrom, parseShard, rankResults, shardRange,
  SWEEP_VERSION, toSpace, type SweepShardFile,
} from '../research/history/depthParamSearch';
import { DEFAULT_DEPTH_SIM_PARAMS, DEPTH_PARAM_NAMES, DEPTH_PARAM_SPACE, readDepthModel, resolveDepthSimParams, type DepthModel, type DepthSimParams } from '../research/history/depthSim';
import { depthModelNote, depthPicksNote, depthSims, fillDayFile, simulatorLine } from '../research/goLiveTally';
import { DEPTH_MODEL_SCHEMA } from '../research/history/depthModelVersion';
import { synthModel, synthRequoteDay, writeEventsGz } from './twinSweepSynth';
import { tmpDir } from './helpers';
import { depthStudy } from '../research/depthStudy';
import { synthRecording, writeRecording } from './depthStudySynth';

const D0 = Date.UTC(2026, 9, 28);
const MIN = 60_000;

test('auc ranks perfectly separated scores 1, reversed 0, ties 0.5', () => {
  assert.equal(auc([0.1, 0.2, 0.8, 0.9], [0, 0, 1, 1]), 1);
  assert.equal(auc([0.9, 0.8, 0.2, 0.1], [0, 0, 1, 1]), 0);
  assert.equal(auc([0.5, 0.5, 0.5, 0.5], [0, 1, 0, 1]), 0.5);
});

/** Rows whose feature 0 is drawn around `shift`, the rest noise, over three days. */
function rows(src: string, shift: number, seed: number): Row[] {
  let s = seed; const r = () => ((s = (Math.imul(s, 1664525) + 1013904223) >>> 0) / 4294967296) - 0.5;
  return Array.from({ length: 300 }, (_, i) => ({ day: `2026-10-2${i % 3}`, ticker: `T${i}`, src, f: FEATURES.map((_, j) => (j === 0 ? shift : 0) + r()) }));
}

test('the adversary finds a real difference and scores identical sources near 0.5', () => {
  const real = rows('real', 0, 1);
  assert.ok(discriminate(real, rows('twin', 0.6, 2), FEATURES.map((_, j) => j)) > 0.8, 'a shifted feature is found');
  const same = discriminate(real, rows('twin', 0, 3), FEATURES.map((_, j) => j));
  assert.ok(Math.abs(same - 0.5) < 0.08, `same source scores ${same}`);
});

test('outcome: an identical twin has zero error and an interval around 0; a kinder one does not', () => {
  const real = new Map([...Array(50).keys()].map((k) => [k, { pnl: (k % 7) - 3, contracts: 2 }] as const));
  const same = outcome(real, real);
  assert.equal(same.rmse, 0); assert.ok(same.lo <= 0 && same.hi >= 0);
  const kind = outcome(real, new Map([...real].map(([k, v]) => [k, { ...v, pnl: v.pnl + 1 }])));
  assert.ok(kind.lo > 0, 'a twin a dollar kinder every window is caught');
});

test('dayRows reads a contract life from book snapshots and deltas alike', async () => {
  const dir = tmpDir();
  const open = D0 + 60 * MIN, close = open + 15 * MIN, tk = 'KXBTC15M-TEST';
  const ev: object[] = [{ t: open - MIN, k: 'market', ticker: tk, series: 'KXBTC15M', asset: 'BTC', openTime: open, closeTime: close }];
  for (let t = open - MIN; t <= close; t += 5000) {
    ev.push({ t, k: 'index', asset: 'BTC', value: 70000 + Math.sin(t / 60000) * 20 });
    const mid = 0.5 + Math.sin(t / 60000) * 0.1;
    ev.push({ t, k: 'book', ticker: tk, bids: [{ price: +(mid - 0.01).toFixed(2), size: 100 }], asks: [{ price: +(mid + 0.01).toFixed(2), size: 120 }] });
  }
  ev.push({ t: close + 1000, k: 'result', ticker: tk, result: 'yes' });
  const f = path.join(dir, 'md-2026-10-28.jsonl.gz');
  fs.writeFileSync(f, zlib.gzipSync(ev.map((e) => JSON.stringify(e)).join('\n') + '\n'));
  const out = await dayRows(f, '2026-10-28', 'real', new Map([[tk, 'yes']]));
  assert.equal(out.length, 1);
  const r = out[0].f;
  assert.ok(Math.abs(r[FEATURES.indexOf('spreadC')] - 2) < 0.6, `spread ${r[0]}`);
  assert.ok(r[FEATURES.indexOf('followIx')] > 0.5, 'the mid follows the index');
  assert.ok(Number.isFinite(r[FEATURES.indexOf('brierT5')]));
});

test('requoteBetween with a lag moves the quote only part of the way', async () => {
  const { requoteBetween } = await import('../research/history/historyReplay');
  const d0 = D0, MINS = 1440 * 4;
  const ixs = new Float64Array(MINS).fill(70000), sgs = new Float64Array(MINS).fill(0.0003);
  // The index jumps up 0.2% at the second print of minute 60.
  for (let i = 60 * 4 + 1; i < MINS; i++) ixs[i] = 70140;
  const m = { ticker: 'T', kind: 'updown' as never, strike: 70000, cap: null, closeTime: d0 + 70 * MIN };
  const run = (lag?: { gInf: number; tauSec: number }) => { const ev: any[] = []; requoteBetween(ev, m, 0.49, 0.51, d0 + 60 * MIN, d0 + 61 * MIN, d0, ixs, sgs, lag); return ev.at(-1)?.bids[0].price as number; };
  const free = run(), lagged = run({ gInf: 0.29, tauSec: 3.9 }), instant = run({ gInf: 1, tauSec: 1e-6 });
  assert.ok(free > 0.5, `the free quote moves up (${free})`);
  assert.equal(instant, free, 'a full, instant lag is the old behaviour');
  assert.ok(lagged > 0.49 && lagged < free, `the lagged quote moves less (${lagged} vs ${free})`);
});

// ---------------------------------------------------------------------------------------------------------------
// The harness (Nov 22): real-day prep, the split, the diagnostics, the report-only stress adversary.

const DAY = '2026-11-13';
const T0 = Date.UTC(2026, 10, 13);
const BTC = 'KXBTC15M-26NOV131200-00', ETH = 'KXETH15M-26NOV131200-00', DOGE = 'KXDOGE15M-26NOV131200-00', HOUR = 'KXBTCD-26NOV1313-T70000', SOLOLD = 'KXSOL15M-26NOV122345-00';

/** A raw recorded day: three 15-minute contracts (one DOGE), an hourly one, a 15-minute one listed the day before (no market
 *  record here), the index, and the kinds of line with no ticker. Returns the file and its lines. */
function rawDay(dir: string, day = DAY): { file: string; lines: string[] } {
  const t0 = Date.parse(`${day}T00:00:00Z`);
  const open = t0 + 12 * 3_600_000, close = open + 15 * MIN;
  const mk = (ticker: string, series: string, asset: string, c = close) => ({ t: open - MIN, k: 'market', ticker, series, asset, openTime: open, closeTime: c });
  const ev: object[] = [mk(BTC, 'KXBTC15M', 'BTC'), mk(ETH, 'KXETH15M', 'ETH'), mk(DOGE, 'KXDOGE15M', 'DOGE'), mk(HOUR, 'KXBTCD', 'BTC', open + 3_600_000)];
  ev.push({ t: open - MIN, k: 'spot_book', asset: 'BTC', b: [[70000, 1]], a: [[70001, 1]], ts: open - MIN });
  ev.push({ t: open - MIN, k: 'candles', asset: 'BTC', tf: '15m', rows: [[1, 2, 3, 4, 5, 6]], ts: open - MIN });
  ev.push({ t: open - MIN, k: 'dominance', usdtd: 5, btcd: 55, ts: open - MIN });
  ev.push({ t: open - MIN, k: 'snn', dirs: [], c: { [DOGE]: 0.5 } });
  ev.push({ t: open - MIN, k: 'gap' });
  for (let t = open - MIN; t <= close; t += 5000) {
    ev.push({ t, k: 'index', asset: 'BTC', value: 70000 + Math.sin(t / 60000) * 20 });
    ev.push({ t, k: 'index', asset: 'DOGE', value: 0.2 });
    const mid = 0.5 + Math.sin(t / 60000) * 0.1;
    for (const tk of [BTC, ETH, DOGE, HOUR, SOLOLD]) ev.push({ t, k: 'book', ticker: tk, bids: [{ price: +(mid - 0.01).toFixed(2), size: 100 }], asks: [{ price: +(mid + 0.01).toFixed(2), size: 120 }] });
    if ((t - open) % 15_000 === 0) for (const tk of [BTC, DOGE, HOUR]) { ev.push({ t: t + 1, k: 'delta', ticker: tk, side: 'yes', price: 0.4, delta: 5 }); ev.push({ t: t + 2, k: 'trade', ticker: tk, price: 0.5, count: 3, takerSide: 'yes', ts: t + 2 }); }
  }
  ev.push({ t: open + 7 * MIN, k: 'alive', tickers: [BTC, HOUR, DOGE, ETH] });
  ev.push({ t: open + 8 * MIN, k: 'alive', tickers: [HOUR, DOGE] });
  for (const tk of [BTC, ETH, DOGE, HOUR]) ev.push({ t: close + 1000, k: 'lifecycle', ticker: tk, result: 'yes' });
  for (const tk of [BTC, ETH, DOGE, HOUR, SOLOLD]) ev.push({ t: close + 2000, k: 'result', ticker: tk, result: 'yes' });
  const lines = ev.map((e) => JSON.stringify(e));
  const file = path.join(dir, `md-${day}.jsonl.gz`);
  fs.writeFileSync(file, zlib.gzipSync(lines.join('\n') + '\n'));
  return { file, lines };
}
const readLines = (file: string) => zlib.gunzipSync(fs.readFileSync(file)).toString('utf8').split('\n').filter(Boolean);

test('prep keeps the 15-minute contracts (not DOGE), the index and the results, and nothing else', async () => {
  const dir = tmpDir(), out = path.join(dir, 'out');
  const { file, lines } = rawDay(dir);
  const m = await prepDay(file, out, DAY);
  const kept = readLines(path.join(out, `md-${DAY}.jsonl.gz`)).map((l) => JSON.parse(l));
  const tickers = new Set(kept.filter((e) => e.ticker).map((e) => e.ticker as string));
  assert.deepEqual([...tickers].sort(), [BTC, ETH, SOLOLD].sort(), 'only the 15-minute, non-DOGE contracts (one with no market record this day)');
  assert.ok(!kept.some((e) => e.ticker === DOGE || e.ticker === HOUR), 'no DOGE, no hourly');
  assert.deepEqual(kept.filter((e) => e.k === 'result').map((e) => e.ticker).sort(), [BTC, ETH, SOLOLD].sort(), 'their results stay, the others go');
  assert.equal(kept.filter((e) => e.k === 'lifecycle').length, 2);
  assert.equal(kept.filter((e) => e.k === 'market').length, 2);
  // Every index print stays (DOGE's too: a line with no ticker), and the other lines nothing in the replays reads go.
  assert.equal(kept.filter((e) => e.k === 'index').length, lines.filter((l) => l.includes('"k":"index"')).length);
  for (const k of ['candles', 'dominance', 'snn', 'gap']) assert.equal(kept.filter((e) => e.k === k).length, 1, `${k} kept`);
  assert.ok(!kept.some((e) => e.k === 'spot_book'), 'the spot book is dropped');
  // A line listing several tickers is filtered to the kept ones, and dropped when none is left.
  const alive = kept.filter((e) => e.k === 'alive');
  assert.equal(alive.length, 1);
  assert.deepEqual(alive[0].tickers, [BTC, ETH]);
  // The kept lines are the raw lines, in order.
  const want = lines.filter((l) => !/"k":"spot_book"/.test(l) && !l.includes(DOGE) && !l.includes(HOUR) && !l.includes('"k":"alive"'));
  const got = readLines(path.join(out, `md-${DAY}.jsonl.gz`)).filter((l) => !l.includes('"k":"alive"'));
  assert.deepEqual(got.filter((l) => !l.includes('"k":"snn"')), want.filter((l) => !l.includes('"k":"snn"')));
  // meta.json: what the workflow prints and the next prep reads.
  const meta = JSON.parse(fs.readFileSync(path.join(out, 'meta.json'), 'utf8'));
  assert.deepEqual(meta, m);
  assert.equal(meta.day, DAY); assert.equal(meta.version, real15mTag()); assert.ok(meta.version.startsWith(REAL15M_VERSION));
  assert.equal(meta.contracts, 3); assert.equal(meta.markets, 2); assert.equal(meta.rawLines, lines.length); assert.equal(meta.events, kept.length);
  assert.equal(meta.sourceBytes, fs.statSync(file).size); assert.equal(meta.bytes, fs.statSync(path.join(out, `md-${DAY}.jsonl.gz`)).size);
  assert.ok(Number.isFinite(meta.seconds) && meta.seconds >= 0);
  assert.equal(meta.sha256, crypto.createHash('sha256').update(fs.readFileSync(path.join(out, `md-${DAY}.jsonl.gz`))).digest('hex'));
});

test('prep reads the same contract lives as the raw day does, and gives the same bytes twice', async () => {
  const dir = tmpDir();
  const { file } = rawDay(dir);
  const a = await prepDay(file, path.join(dir, 'a'), DAY), b = await prepDay(file, path.join(dir, 'b'), DAY);
  assert.equal(a.sha256, b.sha256, 'one input, one output');
  const raw = await dayRows(file, DAY, 'real', new Map([[BTC, 'yes'], [ETH, 'yes']]));
  const cut = await dayRows(path.join(dir, 'a', `md-${DAY}.jsonl.gz`), DAY, 'real', new Map([[BTC, 'yes'], [ETH, 'yes']]));
  assert.equal(raw.length, 2);
  assert.deepEqual(cut, raw, 'the judge sees the same rows on the reduced day');
});

test('prep refuses a day with no 15-minute contract or no index, and leaves nothing that reads as done', async () => {
  const dir = tmpDir();
  const f1 = path.join(dir, 'md-2026-11-13.jsonl.gz');
  fs.writeFileSync(f1, zlib.gzipSync(JSON.stringify({ t: T0, k: 'index', asset: 'BTC', value: 1 }) + '\n' + JSON.stringify({ t: T0, k: 'book', ticker: HOUR, bids: [], asks: [] }) + '\n'));
  await assert.rejects(prepDay(f1, path.join(dir, 'o1'), DAY), /no 15-minute contract/);
  assert.equal(prepStatus(path.join(dir, 'o1'), DAY, true), 'absent');
  const f2 = path.join(dir, 'md-2026-11-14.jsonl.gz');
  fs.writeFileSync(f2, zlib.gzipSync(JSON.stringify({ t: T0, k: 'book', ticker: BTC, bids: [], asks: [] }) + '\n'));
  await assert.rejects(prepDay(f2, path.join(dir, 'o2'), '2026-11-14'), /no index print/);
  await assert.rejects(prepDay(f2, path.join(dir, 'o3'), 'yesterday'), /not a YYYY-MM-DD day/);
});

test('prep is idempotent by version tag: current is skipped, another tag or day is stale, no meta is absent', async () => {
  const dir = tmpDir(), out = path.join(dir, 'out');
  const { file } = rawDay(dir);
  assert.equal(prepStatus(out, DAY), 'absent');
  await prepDay(file, out, DAY);
  assert.equal(prepStatus(out, DAY), 'current');
  assert.equal(prepStatus(out, DAY, true), 'current');
  assert.equal(prepStatus(out, '2026-11-14'), 'stale', 'meta of another day');
  const mf = path.join(out, 'meta.json'), meta = JSON.parse(fs.readFileSync(mf, 'utf8'));
  fs.writeFileSync(mf, JSON.stringify({ ...meta, version: 'r15m-0|exclude=DOGE' }));
  assert.equal(prepStatus(out, DAY), 'stale', 'an older restriction is made again');
  fs.writeFileSync(mf, JSON.stringify({ ...meta, exclude: 'x', version: `${REAL15M_VERSION}|exclude=x` }));
  assert.equal(prepStatus(out, DAY), 'stale', 'another exclusion pattern is another restriction');
  fs.writeFileSync(mf, JSON.stringify({ ...meta, bytes: meta.bytes + 1 }));
  assert.equal(prepStatus(out, DAY), 'current', 'meta alone says current');
  assert.equal(prepStatus(out, DAY, true), 'stale', 'but the file must be the size meta recorded');
  fs.rmSync(mf);
  assert.equal(prepStatus(out, DAY), 'absent', 'a day file without meta.json is an unfinished prep');
  // The CLI: exit 0 when current (the workflow skips), 11 when it must prepare, text with counts only.
  await prepDay(file, out, DAY);
  const run = (day: string) => spawnSync(process.execPath, ['--import', 'tsx', 'research/historyTwin.ts', '--stage', 'prep-status', '--out', out, '--day', day], { encoding: 'utf8' });
  assert.equal(run(DAY).status, 0); assert.match(run(DAY).stdout, /already on Drive.*skipped/);
  assert.equal(run('2026-11-14').status, 11);
});

test('the prep stage prints counts, seconds and sizes only', async () => {
  const dir = tmpDir(), out = path.join(dir, 'out');
  rawDay(dir);
  const r = spawnSync(process.execPath, ['--import', 'tsx', 'research/historyTwin.ts', '--stage', 'prep', '--raw', dir, '--day', DAY, '--out', out], { encoding: 'utf8' });
  assert.equal(r.status, 0, r.stderr);
  assert.match(r.stdout, /\[twin\] prep 2026-11-13: 3 contracts \(2 market records\), \d+ of \d+ lines kept/);
  assert.ok(!/KX[A-Z]+15M|KXBTCD/.test(r.stdout), 'no ticker names in the log');
  assert.equal(prepStatus(out, DAY, true), 'current');
});

test('fit days and judged days must be disjoint: the assert, the split and the stage exit code', () => {
  assertDisjoint(['2026-11-11'], ['2026-11-13']);
  assert.throws(() => assertDisjoint(['2026-11-11', '2026-11-12'], ['2026-11-13', '2026-11-12']), /overlap.*2026-11-12/);
  assert.throws(() => assertDisjoint(['2026-11-11'], ['2026-11-11']), /fit day must never be judged/);
  // The pre-registered splits are disjoint, and a named split refuses lists that are not its own.
  for (const name of ['dev', 'confirm'] as const) { const sp = resolveSplit(name); assert.deepEqual(sp.fit, [...SPLITS[name].fit]); assertDisjoint(sp.fit, sp.judge); }
  assert.deepEqual(resolveSplit('dev').judge, ['2026-11-13', '2026-11-14', '2026-11-16', '2026-11-17']);
  assert.equal(resolveSplit('confirm').fit.length, 7);
  assert.deepEqual(resolveSplit('confirm').judge, ['2026-11-18', '2026-11-19', '2026-11-20']);
  assert.ok(!SPLITS.dev.judge.some((d) => (SPLITS.confirm.judge as readonly string[]).includes(d)), 'dev and confirm judge different days');
  assert.throws(() => resolveSplit('dev', '2026-11-11,2026-11-12', ''), /not the split's own/);
  assert.throws(() => resolveSplit('custom', '2026-11-11,2026-11-12', '2026-11-12'), /overlap/);
  assert.throws(() => resolveSplit('custom', '', '2026-11-12'), /no fit days/);
  assert.throws(() => resolveSplit('custom', '2026-11-11', ''), /no judged days/);
  assert.throws(() => resolveSplit('weekly'), /unknown split/);
  assert.deepEqual(resolveSplit('custom', '2026-11-11', '2026-11-13, 2026-11-14', '2026-11-12,2026-11-13').warm, ['2026-11-12'], 'a warm-up day that is judged is not a warm-up day');
  assert.deepEqual(parseDays('2026-11-11, 2026-11-12,2026-11-11'), ['2026-11-11', '2026-11-12']);
  assert.throws(() => parseDays('2026-02-30'), /not a YYYY-MM-DD day/);
  assert.throws(() => parseDays('11-13'), /not a YYYY-MM-DD day/);
  // The stage exits non-zero on an overlap, zero on a clean split, and writes the split the later stages read.
  const out = path.join(tmpDir(), 'twin');
  const run = (...a: string[]) => spawnSync(process.execPath, ['--import', 'tsx', 'research/historyTwin.ts', '--stage', 'split', '--out', out, ...a], { encoding: 'utf8' });
  const bad = run('--split', 'custom', '--fit-days', '2026-11-11,2026-11-13', '--judge-days', '2026-11-13');
  assert.notEqual(bad.status, 0); assert.match(bad.stderr, /overlap/);
  assert.ok(!fs.existsSync(path.join(out, 'split.json')), 'nothing written for a bad split');
  const ok = run('--split', 'custom', '--fit-days', '2026-11-11', '--judge-days', '2026-11-13,2026-11-14');
  assert.equal(ok.status, 0, ok.stderr);
  assert.deepEqual(JSON.parse(fs.readFileSync(path.join(out, 'split.json'), 'utf8')).judge, ['2026-11-13', '2026-11-14']);
});

test('the depth model must have been fitted on fit days only', () => {
  const dir = tmpDir(), f = path.join(dir, 'depth_model.json');
  const split = { fit: ['2026-11-11', '2026-11-12'], judge: ['2026-11-13'] };
  fs.writeFileSync(f, JSON.stringify({ days: ['2026-11-11', '2026-11-12'] }));
  assertModelFitDays(f, split);
  fs.writeFileSync(f, JSON.stringify({ days: ['2026-11-11', '2026-11-13'] }));
  assert.throws(() => assertModelFitDays(f, split), /overlap.*2026-11-13/);
  fs.writeFileSync(f, JSON.stringify({ days: ['2026-11-11', '2026-11-20'] }));
  assert.throws(() => assertModelFitDays(f, split), /outside the fit set/);
  fs.writeFileSync(f, JSON.stringify({}));
  assert.throws(() => assertModelFitDays(f, split), /does not record/);
});

test('the per-asset blocks and the stress rows come out of the same fit: the fit-day check covers them, and a model file the simulator could not read is refused with it', async () => {
  // a real study output (a synthetic recording of two assets of different scale) with the days the fit step records
  const rec = path.join(tmpDir(), 'md-2026-11-11.jsonl.gz');
  writeRecording(rec, synthRecording([{ name: 'BTC', size: 4000, trades: 30 }, { name: 'ETH', size: 200, trades: 3 }], { perClass: 3 }).events);
  const fit = await depthStudy([rec], '15m');
  const split = { fit: ['2026-11-11', '2026-11-12', '2026-11-15'], judge: ['2026-11-13', '2026-11-14'] };
  const f = path.join(tmpDir(), 'depth_model.json');
  const write = (m: unknown) => fs.writeFileSync(f, JSON.stringify(m));
  const model = { days: ['2026-11-11', '2026-11-12'], ...fit };
  assert.ok(model.byAsset.BTC.shape.some((r) => r.si !== undefined) && model.byAsset.BTC.stress, 'the study wrote stress rows and edges');
  write(model); assertModelFitDays(f, split);
  assert.ok(readDepthModel(f), 'and the model reads');
  // a judged day among the days it was fitted on: refused, blocks or not
  write({ ...model, days: ['2026-11-11', '2026-11-13'] });
  assert.throws(() => assertModelFitDays(f, split), /overlap.*2026-11-13/);
  write({ ...model, days: ['2026-11-11', '2026-11-18'] });
  assert.throws(() => assertModelFitDays(f, split), /outside the fit set: 2026-11-18/);
  write({ ...model, days: undefined });
  assert.throws(() => assertModelFitDays(f, split), /does not record/);
  // blocks the simulator cannot read as they were meant
  const { schema: _s, ...noSchema } = model;
  write(noSchema); assert.throws(() => assertModelFitDays(f, split), /need schema 2 or more/);
  write({ ...model, schema: 3 }); assert.throws(() => assertModelFitDays(f, split), /refit it with this code/);
  write({ ...model, byAsset: { ...model.byAsset, BTC: { ...model.byAsset.BTC, stress: undefined } } }); assert.throws(() => assertModelFitDays(f, split), /stress rows but no ascending stress edges/);
  // an old pooled-only model (no schema, no blocks) is still a fit-day-checked model
  write({ days: ['2026-11-11'], shape: fit.shape, flow: fit.flow }); assertModelFitDays(f, split);
});

test('the workflow spells out the same splits and the prep limits', () => {
  const y = fs.readFileSync('.github/workflows/history-twin.yml', 'utf8');
  for (const name of ['dev', 'confirm'] as const) for (const k of ['fit', 'judge'] as const) assert.ok(y.includes(SPLITS[name][k].join(',')), `${name} ${k} list in the workflow`);
  const job = (name: string) => { const lines = y.split('\n'); const at = lines.indexOf(`  ${name}:`); assert.ok(at >= 0, name); const end = lines.findIndex((l, i) => i > at && /^  \S/.test(l)); return lines.slice(at, end < 0 ? undefined : end).join('\n'); };
  const prep = job('prep');
  assert.match(prep, /max-parallel: 7\b/); assert.match(prep, /timeout-minutes: 340\b/); assert.match(prep, /environment: production/);
  assert.match(prep, /drive_lab\.sh recording/); assert.match(prep, /drive_lab\.sh put "derived\/twin-real15m\//);
  for (const k of ['prep_days', 'force_prep', 'fit_days', 'judge_days', 'warm_day', 'split', 'confirm_look_note']) assert.match(y, new RegExp(`\\n      ${k}:`), `input ${k}`);
  assert.match(job('build'), /if: .*inputs\.prep_days == ''/, 'a dispatch with prep_days does not run the build');
  assert.match(job('reverdict'), /if: .*inputs\.prep_days == ''/, 'nor the re-verdict');
  assert.match(job('prep-plan'), /if: .*inputs\.prep_days != ''/, 'it runs prep');
  assert.match(job('backtest'), /if: .*inputs\.backtests/, 'the backtest legs only on request');
  // The 8-job rule holds per thread: prep and build share one group (never together), every matrix is at most 7 wide, so a
  // re-verdict beside them makes 8.
  for (const m of y.matchAll(/max-parallel: (\d+)/g)) assert.ok(Number(m[1]) <= 7, `max-parallel ${m[1]} is over 7`);
  assert.equal([...y.matchAll(/max-parallel: 7\b/g)].length, 3, 'the prep, the backtest and the sweep matrices are each 7 wide (the sweep is its own dispatch, never beside the others)');
  const groups = [...y.matchAll(/^  group: (.*)$/gm)].map((m) => m[1]);
  assert.equal(groups.length, 1, 'one concurrency group expression');
  assert.match(groups[0], /history-twin-\$\{\{ inputs\.reverdict_run && 'reverdict' \|\| 'heavy' \}\}/, 'prep and build are one group, the re-verdict another');
  assert.ok(!/inputs\.prep_days && 'prep'/.test(y), 'the prep no longer has a group of its own');
});

test('real days missing from the cache name the days and the input to run', () => {
  const dir = tmpDir();
  fs.writeFileSync(path.join(dir, 'md-2026-11-11.jsonl.gz'), 'x');
  fs.writeFileSync(path.join(dir, 'meta-2026-11-11.json'), JSON.stringify({ day: '2026-11-11', version: real15mTag(), bytes: 1 }));
  fs.writeFileSync(path.join(dir, 'md-2026-11-12.jsonl.gz'), 'x');
  fs.writeFileSync(path.join(dir, 'meta-2026-11-12.json'), JSON.stringify({ day: '2026-11-12', version: 'r15m-0|exclude=DOGE', bytes: 1 }));
  const c = checkReal15m(dir, ['2026-11-11', '2026-11-12', '2026-11-13']);
  assert.deepEqual(c, { ok: ['2026-11-11'], stale: ['2026-11-12'], missing: ['2026-11-13'] });
  const err = real15mError(c)!;
  assert.match(err, /missing on Drive.*2026-11-13/); assert.match(err, /another version: 2026-11-12/); assert.match(err, /prep_days=2026-11-12,2026-11-13 force_prep=true/);
  assert.equal(real15mError({ missing: [], stale: [] }), undefined);
  assert.match(real15mError({ missing: ['2026-11-13'], stale: [] })!, /prep_days=2026-11-13(?! force)/);
});

test('the requote days come from Drive only while its manifest is this code\'s replay version', () => {
  const dir = tmpDir();
  const put = (version: number | undefined, days: string[]) => {
    for (const f of fs.readdirSync(dir)) fs.rmSync(path.join(dir, f));
    if (version !== undefined) fs.writeFileSync(path.join(dir, 'replay-manifest.json'), JSON.stringify({ version, days: {} }));
    for (const d of days) fs.writeFileSync(path.join(dir, `md-${d}.jsonl.gz`), 'x');
  };
  const want = ['2026-11-13', '2026-11-14'];
  put(9, want);
  assert.deepEqual(twinSource(dir, want, 9), { manifestVersion: 9, drive: want, regen: [], reason: '' });
  put(9, ['2026-11-13']);
  const part = twinSource(dir, want, 9);
  assert.deepEqual(part.drive, ['2026-11-13']); assert.deepEqual(part.regen, ['2026-11-14']); assert.match(part.reason, /not on Drive: 2026-11-14/);
  put(8, want);
  const old = twinSource(dir, want, 9);
  assert.deepEqual(old.drive, []); assert.deepEqual(old.regen, want); assert.match(old.reason, /version 8.*REPLAY_VERSION is 9/);
  put(undefined, want);
  assert.deepEqual(twinSource(dir, want, 9).regen, want);
});

test('quantiles and the correlation gaps, on fixed arrays', () => {
  const v = Array.from({ length: 11 }, (_, i) => i + 1);
  assert.equal(quantile(v, 0.1), 2); assert.equal(quantile(v, 0.5), 6); assert.equal(quantile(v, 0.9), 10);
  assert.equal(quantile([4, NaN, 1, Infinity, 3], 0.5), 3, 'only finite values count');
  assert.equal(quantile([1, 2], 0.5), 1.5, 'interpolated');
  assert.ok(Number.isNaN(quantile([], 0.5)));
  const mk = (day: string, f0: number, f1: number, i: number): Row => ({ day, ticker: `T${i}`, src: 'x', f: FEATURES.map((_, j) => (j === 0 ? f0 : j === 1 ? f1 : j === 2 ? (i % 2 === 0 ? 1 : 0) : 0)) });
  const base = Array.from({ length: 40 }, (_, i) => i - 20);
  const real = base.map((x, i) => mk('2026-11-13', x, x, i)), twin = base.map((x, i) => mk('2026-11-13', x, -x, i));
  const q3 = quantiles3(real, 0), want3 = [-16.1, -0.5, 15.1];
  q3.forEach((x, k) => assert.ok(Math.abs(x - want3[k]) < 1e-9, `quantiles3[${k}] ${x}`));
  const m = corrMatrix(real);
  assert.ok(Math.abs(m[0][1] - 1) < 1e-12 && Math.abs(m[1][0] - 1) < 1e-12 && m[0][0] === 1);
  assert.equal(m[0][2] > -0.5, true);
  assert.equal(m[3][4], 0, 'a constant column correlates 0');
  const top = topCorrDiffs(real, twin, 10);
  assert.equal(top.length, 10);
  assert.deepEqual([top[0].a, top[0].b], [FEATURES[0], FEATURES[1]]);
  assert.ok(Math.abs(top[0].real - 1) < 1e-12 && Math.abs(top[0].twin + 1) < 1e-12 && Math.abs(top[0].diff - 2) < 1e-12);
  for (let i = 1; i < top.length; i++) assert.ok(top[i - 1].diff >= top[i].diff, 'largest first');
  assert.deepEqual(topCorrDiffs(real, real, 3).map((g) => g.diff), [0, 0, 0], 'identical rows have no gap');
  // The same two arrays give the same list every time.
  assert.deepEqual(topCorrDiffs(real, twin, 10), top);
});

test('the stress adversary is deterministic, finds a shifted twin and sees what the logistic one cannot', () => {
  const all = FEATURES.map((_, j) => j);
  const real = rows('real', 0, 11), shifted = rows('twin', 0.7, 12);
  const a = stressAuc(real, shifted, all), b = stressAuc(real, shifted, all);
  assert.equal(a, b, 'same input twice, same AUC');
  assert.ok(a > 0.85, `a shifted feature is found (${a})`);
  const same = stressAuc(real, rows('twin', 0, 13), all);
  assert.ok(Math.abs(same - 0.5) < 0.1, `the same source scores ${same}`);
  // Same marginals, different joint shape: real fills all four quadrants of (f0, f1), the twin only two of them.
  let s = 5; const r = () => ((s = (Math.imul(s, 1664525) + 1013904223) >>> 0) / 4294967296);
  const quad = (src: string, both: boolean): Row[] => Array.from({ length: 1200 }, (_, i) => { const u = r() * 0.5, v = r() * 0.5, sg = r() < 0.5 ? 1 : -1; return { day: `2026-10-2${i % 3}`, ticker: `Q${i}`, src, f: FEATURES.map((_, j) => (j === 0 ? sg * u : j === 1 ? (both ? (r() < 0.5 ? 1 : -1) : sg) * v : r() - 0.5)) }; });
  const qr = quad('real', true), qt = quad('twin', false);
  assert.ok(discriminate(qr, qt, all) < 0.58, 'the logistic adversary is blind to it');
  const st = stressAuc(qr, qt, all);
  assert.ok(st > 0.68, `the tree adversary sees it (${st})`);
});

test('AUC by judged day uses the headline AUC\'s own folds', () => {
  const all = FEATURES.map((_, j) => j);
  const real = rows('real', 0, 21), twin = rows('twin', 0.5, 22);
  const p = discriminatePerDay(real, twin, all);
  assert.equal(p.auc, discriminate(real, twin, all), 'the pooled AUC is the headline AUC');
  assert.deepEqual(p.byDay.map((d) => d.day), ['2026-10-20', '2026-10-21', '2026-10-22']);
  for (const d of p.byDay) { assert.ok(d.auc !== null && d.auc > 0.6 && d.auc <= 1, `${d.day} ${d.auc}`); assert.equal(d.real, 100); assert.equal(d.twin, 100); }
  const oneSided = discriminatePerDay(real, twin.filter((x) => x.day !== '2026-10-22'), all);
  assert.equal(oneSided.byDay.find((d) => d.day === '2026-10-22')?.auc, null, 'a day with one source only has no AUC of its own');
});

/** Capture what the verdict prints. */
async function verdictLines(out: string, look?: { n?: number; note: string }): Promise<{ lines: string[]; report: Record<string, any> }> {
  const lines: string[] = [], was = console.log;
  console.log = (...a: unknown[]) => { lines.push(a.join(' ')); };
  try { const report = await stageVerdict(out, look); return { lines, report }; } finally { console.log = was; }
}
/** A folder of judged features: requote and depth twins of the real rows, with a split on record. */
function verdictDir(name: 'dev' | 'confirm', twinRows: (real: Row[]) => Row[], windows = false): string {
  const out = tmpDir();
  const real = rows('real', 0, 31), twin = twinRows(real);
  fs.writeFileSync(path.join(out, 'features-real.json'), JSON.stringify(real));
  fs.writeFileSync(path.join(out, 'features-requote.json'), JSON.stringify(twin.map((x) => ({ ...x, src: 'requote' }))));
  fs.writeFileSync(path.join(out, 'features-depth.json'), JSON.stringify(twin.map((x) => ({ ...x, src: 'depth' }))));
  fs.writeFileSync(path.join(out, 'split.json'), JSON.stringify({ name, fit: name === 'dev' ? ['2026-10-17', '2026-10-18'] : ['2026-10-14', '2026-10-15', '2026-10-17'], judge: ['2026-10-20', '2026-10-21', '2026-10-22'], warm: [] }));
  if (windows) {
    const w = JSON.stringify([...Array(30).keys()].map((k) => [T0 + k * 15 * MIN, { pnl: (k % 5) - 2, contracts: 2 }]));
    for (const f of ['real', 'placebo', 'depth', 'requote']) fs.writeFileSync(path.join(out, `windows-${f}.json`), w);
  }
  return out;
}

test('the dev verdict prints the diagnostics block beside every old line, and the stress AUC changes nothing', async () => {
  const out = verdictDir('dev', () => rows('twin', 0.4, 32));
  const { lines, report } = await verdictLines(out);
  const has = (re: RegExp) => lines.filter((l) => re.test(l));
  assert.equal(has(/^\[twin\] adversary sanity, real vs real/).length, 1);
  for (const src of ['requote', 'depth']) {
    assert.equal(has(new RegExp(`^\\[twin\\] ${src}: adversary AUC`)).length, 1);
    assert.equal(has(new RegExp(`^\\[twin\\] ${src}: gives it away most`)).length, 1);
    assert.equal(has(new RegExp(`^\\[twin\\] ${src}: every feature`)).length, 1);
    assert.equal(has(new RegExp(`^\\[twin\\] ${src}: by regime`)).length, 1);
    assert.equal(has(new RegExp(`^\\[twin\\] ${src}: (PASS|FAIL)`)).length, 1);
    assert.equal(has(new RegExp(`^\\[twin\\] ${src}: AUC by judged day`)).length, 1);
    assert.equal(has(new RegExp(`^\\[twin\\] STRESS ${src}: .*AUC 0\\.\\d{3}`)).length, 1);
    const q = has(new RegExp(`^\\[twin\\] ${src} quantiles `));
    assert.equal(q.length, FEATURES.length, 'one line per feature');
    assert.match(q[0], /p10\/p50\/p90: all real [^|]+ twin [^|]+\| calm real [^|]+ twin [^|]+\| normal real [^|]+ twin [^|]+\| volatile real/);
    const g = has(new RegExp(`^\\[twin\\] ${src} correlation gap #`));
    assert.equal(g.length, 10); assert.match(g[0], /#1: \w+ ~ \w+: real -?\d\.\d\d, twin -?\d\.\d\d \(diff \d\.\d\d\)/);
  }
  assert.match(has(/^\[twin\] requote: AUC by judged day/)[0], /2026-10-20 0\.\d{3} \(100 real\/100 twin\); 2026-10-21/);
  assert.ok(!lines.some((l) => /CONFIRM LOOK/.test(l)));
  assert.deepEqual(Object.keys(report.twins.depth.checks), ['indistinguishable', 'noBias', 'errorWithinNoise', 'sameActivity']);
  assert.ok(report.twins.depth.stress > 0.7 && report.twins.depth.auc > 0.7);
  const saved = JSON.parse(fs.readFileSync(path.join(out, 'verdict.json'), 'utf8'));
  assert.ok(saved.twins.depth.quantiles.spreadC.calm.real.length === 3 && saved.twins.depth.corrGaps.length === 10 && saved.twins.depth.aucByDay.length === 3);
});

test('a high STRESS AUC never decides pass or fail', async () => {
  // Rows the logistic adversary cannot tell apart but the tree adversary can; windows identical to the real ones.
  let s = 9; const r = () => ((s = (Math.imul(s, 1664525) + 1013904223) >>> 0) / 4294967296);
  const quad = (both: boolean): Row[] => Array.from({ length: 1200 }, (_, i) => { const u = r() * 0.5, v = r() * 0.5, sg = r() < 0.5 ? 1 : -1; return { day: `2026-10-2${i % 3}`, ticker: `Q${i}`, src: 'x', f: FEATURES.map((_, j) => (j === 0 ? sg * u : j === 1 ? (both ? (r() < 0.5 ? 1 : -1) : sg) * v : r() - 0.5)) }; });
  const out = tmpDir();
  fs.writeFileSync(path.join(out, 'features-real.json'), JSON.stringify(quad(true)));
  fs.writeFileSync(path.join(out, 'features-depth.json'), JSON.stringify(quad(false)));
  const w = JSON.stringify([...Array(30).keys()].map((k) => [T0 + k * 15 * MIN, { pnl: (k % 5) - 2, contracts: 2 }]));
  for (const f of ['real', 'placebo', 'depth']) fs.writeFileSync(path.join(out, `windows-${f}.json`), w);
  const { lines, report } = await verdictLines(out);
  const t = report.twins.depth;
  assert.ok(t.stress > 0.68, `stress ${t.stress}`);
  assert.ok(t.auc <= 0.6, `the headline AUC ${t.auc}`);
  assert.equal(t.pass, true, 'the pass bar is the four old checks');
  assert.ok(lines.some((l) => /^\[twin\] depth: PASS/.test(l)) && lines.some((l) => /^\[twin\] STRESS depth: /.test(l)));
});

test('the confirm verdict prints only the checks, the AUCs and day counts, and the look; a verdict without its note throws', async () => {
  const out = verdictDir('confirm', () => rows('twin', 0.4, 33), true);
  // Every look is numbered and logged: a verdict on the confirm days without its note prints and writes nothing.
  await assert.rejects(stageVerdict(out), /confirm look note/);
  assert.ok(!fs.existsSync(path.join(out, 'verdict.json')), 'nothing written when the look is refused');
  const quiet = await verdictLines(out, { n: 1, note: 'first look' });
  const text = quiet.lines.join('\n');
  for (const banned of ['quantiles', 'correlation gap', 'AUC by judged day', 'gives it away', 'every feature', 'by regime', 'sanity', 'placebo', 'backtest P&L', 'follow', 'lives, trades/min']) assert.ok(!text.includes(banned), `no "${banned}" on a confirm verdict`);
  assert.ok(quiet.lines.includes('[twin] confirm split: 3 fit day(s), 3 judged day(s); 300 real contract lives'), quiet.lines[0]);
  for (const src of ['requote', 'depth']) {
    assert.equal(quiet.lines.filter((l) => l.startsWith(`[twin] ${src}: adversary AUC`)).length, 1);
    assert.equal(quiet.lines.filter((l) => l.startsWith(`[twin] STRESS ${src}: `)).length, 1);
    assert.equal(quiet.lines.filter((l) => new RegExp(`^\\[twin\\] ${src}: (PASS|FAIL) `).test(l)).length, 1);
  }
  assert.ok(quiet.lines.includes('[twin] CONFIRM LOOK #1: first look'));
  assert.equal(quiet.lines.length, 1 + 2 * 3 + 1, 'nothing else');
  const saved = JSON.parse(fs.readFileSync(path.join(out, 'verdict.json'), 'utf8'));
  assert.ok(saved.twins.depth.checks && typeof saved.twins.depth.stress === 'number' && !('quantiles' in saved.twins.depth) && !('features' in saved.twins.depth) && !('regimes' in saved.twins.depth) && !('corrGaps' in saved.twins.depth), 'verdict.json holds no tables either');
  assert.deepEqual(saved.split, { name: 'confirm', fit: 3, judge: 3 });
  // Another look is another number.
  const looked = await verdictLines(out, { n: 2, note: 'after round 3' });
  assert.ok(looked.lines.includes('[twin] CONFIRM LOOK #2: after round 3'));
  assert.equal(looked.lines.length, 1 + 2 * 3 + 1);
  assert.equal(JSON.parse(fs.readFileSync(path.join(out, 'verdict.json'), 'utf8')).look.n, 2, 'verdict.json records the look');
  // A dev verdict never prints a confirm look.
  const dev = verdictDir('dev', () => rows('twin', 0.4, 34));
  assert.ok(!(await verdictLines(dev, { n: 1, note: 'x' })).lines.some((l) => /CONFIRM LOOK/.test(l)));
});

test('verdict, features and match refuse a split whose fit and judged days overlap', async () => {
  const out = verdictDir('dev', () => rows('twin', 0, 35));
  fs.writeFileSync(path.join(out, 'split.json'), JSON.stringify({ name: 'dev', fit: ['2026-10-20'], judge: ['2026-10-20', '2026-10-21'], warm: [] }));
  await assert.rejects(stageVerdict(out), /overlap/);
  const r = spawnSync(process.execPath, ['--import', 'tsx', 'research/historyTwin.ts', '--stage', 'features', '--out', out, '--days', '2026-10-20', '--dirs', 'real=x'], { encoding: 'utf8' });
  assert.notEqual(r.status, 0); assert.match(r.stderr, /overlap/);
});

// ---------------------------------------------------------------------------------------------------------------
// Fix round 1: the confirm days are held out, a look needs its note, a custom split judges 2+ days, the 8-job rule,
// blind backtest legs, the reports. The workflow's own shell steps are run here (stubbed Drive, gh and node).

const ROOT = process.cwd();
const wf = () => fs.readFileSync(path.join(ROOT, '.github/workflows/history-twin.yml'), 'utf8');

/** The dedented `run: |` script of the first step whose name starts with `name` (a block scalar, read off the text). */
function stepScript(y: string, name: string): string {
  const lines = y.split('\n');
  const at = lines.findIndex((l) => new RegExp(`^\\s*- name: ${name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}`).test(l));
  assert.ok(at >= 0, `step "${name}" not found`);
  const ind = lines[at].search(/\S/) + 2;
  const run = lines.findIndex((l, i) => i > at && l === `${' '.repeat(ind)}run: |`);
  assert.ok(run > at, `step "${name}" has no run block`);
  const out: string[] = [];
  for (let i = run + 1; i < lines.length; i++) {
    if (lines[i].trim() && lines[i].search(/\S/) <= ind) break;
    out.push(lines[i].slice(ind + 2));
  }
  return out.join('\n');
}
/** Every `run: |` block of the workflow (for a syntax check). */
function allRunScripts(y: string): Array<{ at: number; script: string }> {
  const lines = y.split('\n'), out: Array<{ at: number; script: string }> = [];
  for (let i = 0; i < lines.length; i++) {
    const m = /^(\s*)run: \|\s*$/.exec(lines[i]);
    if (!m) continue;
    const ind = m[1].length, body: string[] = [];
    for (let k = i + 1; k < lines.length; k++) { if (lines[k].trim() && lines[k].search(/\S/) <= ind) break; body.push(lines[k].slice(ind + 2)); }
    out.push({ at: i + 1, script: body.join('\n') });
  }
  return out;
}
const bash = (script: string, env: Record<string, string>, cwd = ROOT) => spawnSync('bash', ['-c', script], { cwd, env: { PATH: process.env.PATH ?? '', HOME: process.env.HOME ?? '', ...env }, encoding: 'utf8' });

test('every shell step of the workflow is valid bash', () => {
  const scripts = allRunScripts(wf());
  assert.ok(scripts.length >= 25, `${scripts.length} run blocks`);
  for (const { at, script } of scripts) {
    const r = spawnSync('bash', ['-n'], { input: script.replace(/\$\{\{.*?\}\}/g, 'X'), encoding: 'utf8' });
    assert.equal(r.status, 0, `run block at line ${at}: ${r.stderr}`);
  }
});

test('the confirm days are held out: no dev or custom split, fit, judged or warm-up list may name them', () => {
  assert.deepEqual([...CONFIRM_DAYS], ['2026-11-18', '2026-11-19', '2026-11-20']);
  // custom judging a confirm day, a confirm day in the fit days of a dev-judging custom split, a confirm warm-up day on dev
  assert.throws(() => resolveSplit('custom', '2026-11-11', '2026-11-18,2026-11-19'), /confirm days.*split=confirm/);
  assert.throws(() => resolveSplit('custom', '2026-11-11', '2026-11-18'), /confirm days/);
  assert.throws(() => resolveSplit('custom', '2026-11-18', '2026-11-13,2026-11-14'), /confirm days.*2026-11-18/);
  assert.throws(() => resolveSplit('custom', '2026-11-11,2026-11-19,2026-11-20', '2026-11-13,2026-11-14'), /confirm days/);
  assert.throws(() => resolveSplit('dev', '', '', '2026-11-18'), /confirm days.*warm-up/);
  assert.throws(() => resolveSplit('dev', '', '', '2026-11-19'), /confirm days/);
  assert.throws(() => resolveSplit('custom', '2026-11-11', '2026-11-13,2026-11-14', '2026-11-20'), /confirm days/);
  // a dev list passed with a confirm day in it is not the dev split's own either
  assert.throws(() => resolveSplit('dev', '2026-11-11,2026-11-12,2026-11-18', ''), /not the split's own/);
  // split=confirm itself is fine, and a warm-up confirm day is just a judged day there
  assert.deepEqual(resolveSplit('confirm').judge, [...CONFIRM_DAYS]);
  assert.deepEqual(resolveSplit('confirm', '', '', '2026-11-18,2026-11-17').warm, ['2026-11-17']);
  assert.deepEqual(resolveSplit('custom', '2026-11-11', '2026-11-13,2026-11-17', '2026-11-12').warm, ['2026-11-12'], 'ordinary custom splits still work');
  // the assert itself (what the stages call on a split.json they read)
  assertHeldOut({ name: 'confirm', fit: ['2026-11-11'], judge: [...CONFIRM_DAYS] });
  assertHeldOut({ name: 'dev', fit: ['2026-11-11'], judge: ['2026-11-13'], warm: ['2026-11-12'] }, ['2026-11-14']);
  assert.throws(() => assertHeldOut({ name: 'dev', fit: ['2026-11-11'], judge: ['2026-11-13'] }, ['2026-11-18']), /confirm days \(2026-11-18\)/, 'a stage asked to read a confirm day');
  assert.throws(() => assertHeldOut({ name: 'custom', fit: ['2026-11-11', '2026-11-20'], judge: ['2026-11-13', '2026-11-14'], warm: [] }), /2026-11-20/);
  // blindness follows the days, not the name
  assert.equal(isBlind({ name: 'confirm', judge: ['x'] }), true);
  assert.equal(isBlind({ name: 'custom', judge: ['2026-11-19'] }), true);
  assert.equal(isBlind({ name: 'dev', judge: ['2026-11-13'] }, ['2026-11-20']), true);
  assert.equal(isBlind(undefined, ['2026-11-18']), true);
  assert.equal(isBlind({ name: 'dev', judge: ['2026-11-13'] }, ['2026-11-14']), false);
  assert.equal(isBlind(undefined), false);
  // the stage: exit code and nothing written
  const out = path.join(tmpDir(), 'twin');
  const run = (...a: string[]) => spawnSync(process.execPath, ['--import', 'tsx', 'research/historyTwin.ts', '--stage', 'split', '--out', out, ...a], { encoding: 'utf8' });
  const bad = run('--split', 'custom', '--fit-days', '2026-11-11', '--judge-days', '2026-11-18,2026-11-19');
  assert.notEqual(bad.status, 0); assert.match(bad.stderr, /\[twin\] ERROR: .*confirm days/);
  assert.ok(!fs.existsSync(path.join(out, 'split.json')));
  const warmBad = run('--split', 'dev', '--warm-days', '2026-11-18');
  assert.notEqual(warmBad.status, 0); assert.match(warmBad.stderr, /confirm days/);
  const conf = run('--split', 'confirm');
  assert.equal(conf.status, 0, conf.stderr);
  assert.match(conf.stdout, /split confirm: 7 fit day\(s\), 3 judged day\(s\)/); assert.ok(!/2026-11-1\d/.test(conf.stdout), 'counts only on the confirm split');
});

test('a custom split judges at least 2 days: with one, leave-one-day-out runs no fold and the AUC is a flat 0.500', () => {
  assert.equal(MIN_CUSTOM_JUDGED_DAYS, 2);
  assert.throws(() => resolveSplit('custom', '2026-11-11,2026-11-12', '2026-11-13'), /at least 2 judged days \(3 or more recommended\), got 1/);
  assert.throws(() => resolveSplit('custom', '2026-11-11', '2026-11-13,2026-11-13'), /at least 2 judged days/, 'a repeated day is one day');
  assert.deepEqual(resolveSplit('custom', '2026-11-11,2026-11-12', '2026-11-13,2026-11-14,2026-11-16').judge.length, 3);
  assert.equal(resolveSplit('custom', '2026-11-11', '2026-11-13,2026-11-14').judge.length, 2);
  assert.equal(resolveSplit('dev').judge.length, 4);
  // WHY: a trivially separable twin scores 0.5 with one judged day and 1.0 with two (the judge itself is not changed).
  const all = FEATURES.map((_, j) => j);
  const mk = (src: string, shift: number, days: string[]): Row[] => Array.from({ length: 120 }, (_, i) => ({ day: days[i % days.length], ticker: `T${i}`, src, f: FEATURES.map((_, j) => (j === 0 ? shift : 0) + ((i * 37 + j * 11) % 17) / 17 - 0.5) }));
  assert.equal(discriminate(mk('real', 0, ['2026-11-13']), mk('twin', 5, ['2026-11-13']), all), 0.5);
  assert.ok(discriminate(mk('real', 0, ['2026-11-13', '2026-11-14']), mk('twin', 5, ['2026-11-13', '2026-11-14']), all) > 0.99);
});

/** The split step of the workflow, run for real: the same probes as resolveSplit, the same answers. */
function splitStep(env: Record<string, string>): { ok: boolean; out: Record<string, string>; text: string } {
  const tmp = tmpDir(), gh = path.join(tmp, 'gh_output');
  fs.writeFileSync(gh, '');
  const r = bash(stepScript(wf(), 'The split'), { SPLIT: 'dev', FIT_IN: '', JUDGE_IN: '', WARM_IN: '', NOTE: '', BACKTESTS: 'false', MODEL_DRIVE: '', GITHUB_OUTPUT: gh, RUNNER_TEMP: tmp, ...env });
  const out = Object.fromEntries(fs.readFileSync(gh, 'utf8').split('\n').filter(Boolean).map((l) => [l.slice(0, l.indexOf('=')), l.slice(l.indexOf('=') + 1)]));
  return { ok: r.status === 0, out, text: `${r.stdout}${r.stderr}` };
}

test('the workflow split step refuses what resolveSplit refuses (confirm days, one judged day, no note) and accepts what it accepts', () => {
  const probes: Array<{ env: Record<string, string>; args: [string, string, string, string] }> = [
    { env: { SPLIT: 'dev' }, args: ['dev', '', '', ''] },
    { env: { SPLIT: 'confirm', NOTE: 'round 3 final' }, args: ['confirm', '', '', ''] },
    { env: { SPLIT: 'custom', FIT_IN: '2026-11-11,2026-11-12', JUDGE_IN: '2026-11-13,2026-11-14,2026-11-16' }, args: ['custom', '2026-11-11,2026-11-12', '2026-11-13,2026-11-14,2026-11-16', ''] },
    { env: { SPLIT: 'custom', FIT_IN: '2026-11-11,2026-11-12', JUDGE_IN: '2026-11-13' }, args: ['custom', '2026-11-11,2026-11-12', '2026-11-13', ''] },
    { env: { SPLIT: 'custom', FIT_IN: '2026-11-11', JUDGE_IN: '2026-11-18,2026-11-19,2026-11-20' }, args: ['custom', '2026-11-11', '2026-11-18,2026-11-19,2026-11-20', ''] },
    { env: { SPLIT: 'custom', FIT_IN: '2026-11-11', JUDGE_IN: '2026-11-13,2026-11-19' }, args: ['custom', '2026-11-11', '2026-11-13,2026-11-19', ''] },
    { env: { SPLIT: 'custom', FIT_IN: '2026-11-11,2026-11-18', JUDGE_IN: '2026-11-13,2026-11-14' }, args: ['custom', '2026-11-11,2026-11-18', '2026-11-13,2026-11-14', ''] },
    { env: { SPLIT: 'dev', WARM_IN: '2026-11-18' }, args: ['dev', '', '', '2026-11-18'] },
    { env: { SPLIT: 'custom', FIT_IN: '2026-11-11', JUDGE_IN: '2026-11-13,2026-11-14', WARM_IN: '2026-11-20' }, args: ['custom', '2026-11-11', '2026-11-13,2026-11-14', '2026-11-20'] },
    { env: { SPLIT: 'custom', FIT_IN: '2026-11-11,2026-11-13', JUDGE_IN: '2026-11-13,2026-11-14' }, args: ['custom', '2026-11-11,2026-11-13', '2026-11-13,2026-11-14', ''] },
    { env: { SPLIT: 'custom', FIT_IN: '', JUDGE_IN: '2026-11-13,2026-11-14' }, args: ['custom', '', '2026-11-13,2026-11-14', ''] },
  ];
  for (const p of probes) {
    let want = true; try { resolveSplit(...p.args); } catch { want = false; }
    const got = splitStep(p.env);
    assert.equal(got.ok, want, `${JSON.stringify(p.env)}: workflow ${got.ok ? 'accepts' : 'refuses'}, resolveSplit ${want ? 'accepts' : 'refuses'}: ${got.text.slice(0, 300)}`);
  }
  // the messages a dispatcher reads
  assert.match(splitStep({ SPLIT: 'custom', FIT_IN: '2026-11-11', JUDGE_IN: '2026-11-13,2026-11-19' }).text, /confirm days .* read only through split=confirm with a confirm_look_note: 2026-11-19 cannot be a fit, judged or warm-up day/);
  assert.match(splitStep({ SPLIT: 'custom', FIT_IN: '2026-11-11', JUDGE_IN: '2026-11-13' }).text, /at least 2 judged days \(3 or more recommended\), got 1/);
  // the look note: no note, a blank note, a note of control characters: no run, before any day is pulled
  for (const note of ['', '   ', ' \t \n ']) { const r = splitStep({ SPLIT: 'confirm', NOTE: note }); assert.equal(r.ok, false); assert.match(r.text, /split=confirm needs confirm_look_note/); }
  // outputs of an accepted split; warm-up days: the day before each judged day that is not itself judged
  const dev = splitStep({ SPLIT: 'dev', BACKTESTS: 'true', MODEL_DRIVE: 'm1' });
  assert.equal(dev.out.warm, '2026-11-12,2026-11-15', dev.text);
  assert.equal(dev.out.judge, SPLITS.dev.judge.join(',')); assert.equal(dev.out.fit, SPLITS.dev.fit.join(','));
  assert.equal(splitStep({ SPLIT: 'confirm', NOTE: 'n', BACKTESTS: 'true', MODEL_DRIVE: 'm1' }).out.warm, '2026-11-17', 'the confirm round warms up on 2026-11-17 (a fit day)');
  assert.equal(splitStep({ SPLIT: 'dev', BACKTESTS: 'true', MODEL_DRIVE: 'm1', WARM_IN: '2026-11-12, 2026-11-13' }).out.warm, '2026-11-12', 'a warm day that is judged is not a warm-up day');
  // every failure leaves a '[twin] ERROR:' line in build.log (what the commit comment keeps)
  const tmp = tmpDir(); fs.writeFileSync(path.join(tmp, 'o'), '');
  bash(stepScript(wf(), 'The split'), { SPLIT: 'confirm', NOTE: '', FIT_IN: '', JUDGE_IN: '', WARM_IN: '', BACKTESTS: 'false', MODEL_DRIVE: '', GITHUB_OUTPUT: path.join(tmp, 'o'), RUNNER_TEMP: tmp });
  assert.match(fs.readFileSync(path.join(tmp, 'build.log'), 'utf8'), /^\[twin\] ERROR: split=confirm needs confirm_look_note/m);
});

test('twin-look.sh numbers a look, logs it, and refuses a note that is blank once control characters are stripped', () => {
  const drive = tmpDir(), work = tmpDir(), lab = path.join(work, 'lab.sh');
  fs.writeFileSync(lab, `#!/usr/bin/env bash
case "$1" in
  get) [ -d "$STUB_DRIVE/$2" ] && [ -n "$(ls -A "$STUB_DRIVE/$2")" ] || exit 3; mkdir -p "$3"; cp -r "$STUB_DRIVE/$2/." "$3/";;
  put) mkdir -p "$STUB_DRIVE/$2"; cp -r "$3/." "$STUB_DRIVE/$2/";;
esac
`);
  const look = (note: string, run = '1') => spawnSync('bash', ['.github/scripts/twin-look.sh', note], { cwd: ROOT, env: { PATH: process.env.PATH ?? '', DRIVE_LAB: lab, STUB_DRIVE: drive, GITHUB_RUN_ID: run, GITHUB_RUN_ATTEMPT: '1' }, encoding: 'utf8' });
  const files = () => fs.existsSync(path.join(drive, 'derived/twin-confirm-looks')) ? fs.readdirSync(path.join(drive, 'derived/twin-confirm-looks')).sort() : [];
  for (const blank of ['', '   ', '\t\n  \r ', '\u007f ']) { const r = look(blank); assert.notEqual(r.status, 0, JSON.stringify(blank)); assert.match(r.stderr, /needs a confirm_look_note/); assert.equal(r.stdout, ''); }
  assert.deepEqual(files(), [], 'a refused note logs nothing');
  const a = look('round 1 final', '501'); assert.equal(a.status, 0, a.stderr); assert.equal(a.stdout.trim(), '1');
  const b = look('  second\tlook\n', '502'); assert.equal(b.status, 0, b.stderr); assert.equal(b.stdout.trim(), '2');
  assert.deepEqual(files(), ['look-001-501-1.txt', 'look-002-502-1.txt']);
  const text = fs.readFileSync(path.join(drive, 'derived/twin-confirm-looks/look-002-502-1.txt'), 'utf8');
  assert.match(text, /^look 2\nrun 502 attempt 1\nat \d{4}-\d\d-\d\dT[\d:]+Z UTC\nnote second look\n$/, 'control characters are spaces, the ends are trimmed');
  const long = look('x'.repeat(300), '503'); assert.equal(long.stdout.trim(), '3');
  assert.equal(fs.readFileSync(path.join(drive, 'derived/twin-confirm-looks/look-003-503-1.txt'), 'utf8').split('\n')[3], `note ${'x'.repeat(200)}`);
});

test('the build workflow numbers the confirm look just before the confirm days are read, and fails without a note', () => {
  const y = wf();
  const at = (name: string) => y.indexOf(`- name: ${name}`);
  assert.ok(at('Number this confirm look') > at('The depth model, fitted on the FIT days only'), 'a failed fit or a missing day burns no look number');
  assert.ok(at('Number this confirm look') < at('Match, fill in, and describe every contract both ways'), 'and it comes before the first read of a confirm day');
  assert.ok(!/neither numbered nor logged/.test(y), 'no more unlogged looks');
  // the look step, run with a stub Drive: confirm without a note fails with a [twin] ERROR line; with a note it numbers
  const drive = tmpDir(), work = tmpDir(), lab = path.join(work, 'lab.sh'), tmp = tmpDir(), gh = path.join(tmp, 'out');
  fs.writeFileSync(lab, `#!/usr/bin/env bash\ncase "$1" in\n  get) exit 3;;\n  put) mkdir -p "$STUB_DRIVE/$2"; cp -r "$3/." "$STUB_DRIVE/$2/";;\nesac\n`);
  const step = (env: Record<string, string>) => { fs.writeFileSync(gh, ''); return bash(stepScript(y, 'Number this confirm look'), { GITHUB_OUTPUT: gh, RUNNER_TEMP: tmp, DRIVE_LAB: lab, STUB_DRIVE: drive, GITHUB_RUN_ID: '9', ...env }); };
  const nope = step({ SPLIT: 'confirm', NOTE: '  ' });
  assert.notEqual(nope.status, 0); assert.match(fs.readFileSync(path.join(tmp, 'build.log'), 'utf8'), /\[twin\] ERROR: .*confirm look was not numbered/);
  const yes = step({ SPLIT: 'confirm', NOTE: 'the one look' });
  assert.equal(yes.status, 0, yes.stderr); assert.equal(fs.readFileSync(gh, 'utf8').trim(), 'n=1');
  assert.match(fs.readFileSync(path.join(tmp, 'build.log'), 'utf8'), /\[twin\] CONFIRM LOOK #1 logged on Drive/);
  const dev = step({ SPLIT: 'dev', NOTE: '' });
  assert.equal(dev.status, 0, dev.stderr); assert.equal(fs.readFileSync(gh, 'utf8').trim(), 'n=', 'a dev run numbers nothing');
  assert.deepEqual(fs.readdirSync(path.join(drive, 'derived/twin-confirm-looks')), ['look-001-9-1.txt'], 'one look, one file');
});

test('the confirm backtest legs are blind: no [fidelity] line, no per-window file in an artifact', () => {
  const y = wf();
  assert.ok(!/upload-artifact|download-artifact/.test(y), 'no artifacts at all: this repository is public');
  const job = (name: string) => { const lines = y.split('\n'); const i = lines.indexOf(`  ${name}:`); const e = lines.findIndex((l, k) => k > i && /^  \S/.test(l)); return lines.slice(i, e < 0 ? undefined : e).join('\n'); };
  assert.match(job('backtest'), /SPLIT: \$\{\{ needs\.build\.outputs\.split \}\}/, 'the backtest job knows the split');
  assert.match(job('backtest'), /simulated\/history-twin\/\$\{\{ github\.run_id \}\}\/windows\/twin-\$\{\{ matrix\.how \}\}-p\$\{\{ matrix\.part \}\}/, 'per-window P&L goes to Drive');
  assert.match(job('verdict'), /history-twin\/\$\{\{ github\.run_id \}\}\/windows/, 'the verdict reads it from Drive');
  assert.match(job('verdict'), /environment: production/, 'with the Drive secret');
  // run the step with a stub node that prints what replayFidelity prints: on confirm none of it may reach the log
  const work = tmpDir(), bin = path.join(work, 'bin'), ws = path.join(work, 'ws'), tmp = path.join(work, 'tmp');
  fs.mkdirSync(bin); fs.mkdirSync(tmp);
  for (const x of ['2026-11-17', '2026-11-18', '2026-11-19']) for (const how of ['depth']) { fs.mkdirSync(path.join(ws, 'data/twin', how), { recursive: true }); fs.writeFileSync(path.join(ws, 'data/twin', how, `md-${x}.jsonl.gz`), 'x'); }
  fs.writeFileSync(path.join(bin, 'node'), `#!/usr/bin/env bash
out=; name=; for ((i=1;i<=$#;i++)); do case "\${!i}" in --out) j=$((i+1)); out=\${!j};; --name) j=$((i+1)); name=\${!j};; esac; done
if [ -n "$STUB_NODE_FAIL" ]; then echo "[fidelity] secret: 41 fills, 17 contracts"; echo "Error: boom in a day"; exit 1; fi
echo "[fidelity] day: 123 entry evaluations, 45 orders sent, 6 fills, 7 contracts"
echo "[fidelity] day: 9 settled positions; traded hours 13h to 15h (13:3 14:4)"
echo "[fidelity] day windows: 11-18T12:00 2ct $4.20"
mkdir -p "$out"; echo '[]' > "$out/windows-$name.json"
`, { mode: 0o755 });
  const run = (split: string, extra: Record<string, string> = {}) => bash(stepScript(y, 'Backtest'), { PATH: `${bin}:${process.env.PATH}`, SPLIT: split, DAYS: split === 'confirm' ? '2026-11-18,2026-11-19' : '2026-11-18,2026-11-19', PARTS: '2', HOW: 'depth', PART: '0', GITHUB_WORKSPACE: ws, RUNNER_TEMP: tmp, ...extra }, ws);
  const blind = run('confirm');
  assert.equal(blind.status, 0, blind.stderr);
  const both = `${blind.stdout}${blind.stderr}`;
  assert.ok(!/\[fidelity\]|entry evaluations|fills|contracts|settled|\$4\.20/.test(both), `nothing of the mechanics on a confirm split: ${both}`);
  assert.match(both, /\[twin\] confirm backtest depth part 0: 1 of 1 day\(s\) done/);
  assert.ok(fs.existsSync(path.join(tmp, 'out', 'windows-depth-p0-2026-11-18.json')), 'the per-window file is still made (for Drive)');
  assert.ok(fs.existsSync(path.join(tmp, 'bt-2026-11-18.log')) && /entry evaluations/.test(fs.readFileSync(path.join(tmp, 'bt-2026-11-18.log'), 'utf8')), 'the lines stay in the runner\'s own log file');
  const open = run('dev');
  assert.match(`${open.stdout}`, /\[fidelity\] day: 123 entry evaluations/, 'a dev split still prints them');
  assert.ok(!/ windows: /.test(open.stdout));
  const failed = run('confirm', { STUB_NODE_FAIL: '1' });
  assert.notEqual(failed.status, 0);
  assert.ok(!/\[fidelity\]|41 fills|17 contracts/.test(`${failed.stdout}${failed.stderr}`), 'a failing confirm leg prints no mechanics either');
  assert.match(failed.stdout, /failed \(exit 1\); the log is withheld on the confirm split: Error: boom/);
});

test('a failure leaves its reason in the commit comment, which keeps the framing lines before the last ones', () => {
  const y = wf();
  const tmp = tmpDir(), bin = path.join(tmp, 'bin'); fs.mkdirSync(bin);
  const sent = path.join(tmp, 'sent.md');
  fs.writeFileSync(path.join(bin, 'gh'), `#!/usr/bin/env bash\nfor a in "$@"; do case "$a" in body=@*) cp "\${a#body=@}" "$GH_OUT";; esac; done\n`, { mode: 0o755 });
  const report = (log: string[] | undefined) => {
    if (log) fs.writeFileSync(path.join(tmp, 'build.log'), log.join('\n') + '\n'); else fs.rmSync(path.join(tmp, 'build.log'), { force: true });
    fs.rmSync(sent, { force: true });
    const script = stepScript(y, 'Report (commit comment; RUNBOOK').replace(/\$\{\{ github\.run_id \}\}/g, '77').replace(/\$\{\{ job\.status \}\}/g, 'failure').replace(/\$\{\{ github\.repository \}\}/g, 'o/r').replace(/\$\{\{ github\.sha \}\}/g, 'abc');
    const r = bash(script, { PATH: `${bin}:${process.env.PATH}`, RUNNER_TEMP: tmp, GH_OUT: sent, GH_TOKEN: 't', GITHUB_SHA: '0123456789abcdef' });
    assert.equal(r.status, 0, r.stderr);
    return fs.readFileSync(sent, 'utf8');
  };
  // 300 table lines after the framing lines: the split, the real days and the requote source are still in the comment
  const log = ['[twin] split input dev: 3 fit day(s), 4 judged day(s), warm-up for backtests: none', '[twin] real 15-minute days from Drive: 7 day(s), 9 MB', '[twin] requote source: 4 of 4 day(s) from Drive', '[kalshi-replay-data] progress'];
  for (let i = 0; i < 300; i++) log.push(`[twin] real 2026-11-13 table line ${i}`);
  log.push('[twin] ERROR: real 15-minute days missing on Drive (derived/twin-real15m): 2026-11-13. Dispatch this workflow with prep_days=2026-11-13 first.', 'not a twin line');
  const c = report(log);
  assert.match(c, /^History twin build, run 77 \(failure\), on commit 01234567\n/);
  for (const want of ['split input dev', 'real 15-minute days from Drive', 'requote source', 'ERROR: real 15-minute days missing on Drive']) assert.ok(c.includes(want), want);
  assert.ok(c.includes('table line 299') && !c.includes('table line 100\n'), 'and only the last lines of the tables');
  assert.ok(c.split('\n').length < 90 && !c.includes('not a twin line'));
  // a build that failed before its first log line says so, instead of an empty block
  assert.match(report(undefined), /no \[twin\] lines: the build failed before its first logging step/);
});

test('the prep report: one DONE or NOT DONE line per day from each day\'s commit mark', async () => {
  const dir = tmpDir(), marks = path.join(tmpDir(), 'marks');
  const { file } = rawDay(dir);
  await prepDay(file, path.join(marks, DAY), DAY);
  fs.mkdirSync(path.join(marks, '2026-11-14'), { recursive: true });
  fs.mkdirSync(path.join(marks, '2026-11-15'), { recursive: true });
  fs.writeFileSync(path.join(marks, '2026-11-15', 'meta.json'), JSON.stringify({ day: '2026-11-15', version: 'r15m-0|exclude=DOGE', bytes: 1 }));
  const r = prepReport(marks, [DAY, '2026-11-14', '2026-11-15']);
  assert.deepEqual(r.done, [DAY]); assert.deepEqual(r.notDone, ['2026-11-14', '2026-11-15']);
  assert.match(r.lines[0], /^\[twin\] prep 2026-11-13: DONE; 3 contracts \(2 market records\), \d+ of \d+ lines kept .*sha256 [0-9a-f]{12}$/);
  assert.match(r.lines[1], /^\[twin\] prep 2026-11-14: NOT DONE; no meta\.json on Drive/);
  assert.match(r.lines[2], /^\[twin\] prep 2026-11-15: NOT DONE; meta\.json is for another day or made by another version.*force_prep=true/);
  assert.equal(r.lines[3], '[twin] prep report: 1 of 3 day(s) done; not done: 2026-11-14, 2026-11-15');
  assert.ok(!r.lines.some((l) => /KX[A-Z]+15M/.test(l)), 'counts only');
  const cli = spawnSync(process.execPath, ['--import', 'tsx', 'research/historyTwin.ts', '--stage', 'prep-report', '--dir', marks, '--days', DAY], { encoding: 'utf8' });
  assert.equal(cli.status, 0, cli.stderr); assert.match(cli.stdout, /prep 2026-11-13: DONE;[^\n]*\n\[twin\] prep report: 1 of 1 day\(s\) done\n$/);
  // the workflow: one report job after the prep matrix, posting one comment
  const y = wf();
  const lines = y.split('\n'), at = lines.indexOf('  prep-report:'), end = lines.findIndex((l, i) => i > at && /^  \S/.test(l)), block = lines.slice(at, end).join('\n');
  assert.match(block, /needs: \[prep-plan, prep\]/); assert.match(block, /if: \$\{\{ always\(\) && needs\.prep-plan\.result == 'success' \}\}/);
  assert.match(block, /--stage prep-report/); assert.match(block, /commits\/\$\{\{ github\.sha \}\}\/comments/); assert.match(block, /environment: production/);
});

test('the stages read blind whenever a confirm day is read, whatever the split is called', async () => {
  // features, no split on record: a confirm day prints the count line only, a dev day prints its per-day activity too
  const dir = tmpDir();
  rawDay(dir, '2026-11-18'); rawDay(dir, '2026-11-13');
  const feat = (day: string, split?: object) => {
    const out = path.join(tmpDir(), 'twin'); fs.mkdirSync(out, { recursive: true });
    if (split) fs.writeFileSync(path.join(out, 'split.json'), JSON.stringify(split));
    return spawnSync(process.execPath, ['--import', 'tsx', 'research/historyTwin.ts', '--stage', 'features', '--out', out, '--days', day, '--dirs', `real=${dir}`, '--extra-days', '2026-11-19,2026-11-12', '--extra-dir', dir], { encoding: 'utf8' });
  };
  const confirm = feat('2026-11-18');
  assert.equal(confirm.status, 0, confirm.stderr);
  assert.match(confirm.stdout, /features real: \d+ contract lives over 1 day\(s\)/);
  assert.ok(!/lives, trades\/min|follow|not judged/.test(confirm.stdout), `nothing per day for a confirm day: ${confirm.stdout}`);
  const dev = feat('2026-11-13');
  assert.equal(dev.status, 0, dev.stderr);
  assert.match(dev.stdout, /real 2026-11-13: \d+ lives, trades\/min/);
  assert.ok(!/2026-11-19/.test(dev.stdout), 'a confirm day is never printed as a not-judged extra day');
  // a dev split on record that asks a stage to read a confirm day is refused
  const bad = feat('2026-11-18', { name: 'dev', fit: ['2026-11-11'], judge: ['2026-11-13'], warm: [] });
  assert.notEqual(bad.status, 0); assert.match(bad.stderr, /confirm days \(2026-11-18\)/);
  // verdict: a split.json that is not called confirm but judges a confirm day is refused outright; rows of a confirm day with no
  // split on record are a look, and need its note
  const out = verdictDir('dev', () => rows('twin', 0.4, 36));
  fs.writeFileSync(path.join(out, 'split.json'), JSON.stringify({ name: 'custom', fit: ['2026-11-11'], judge: ['2026-11-18', '2026-11-19'], warm: [] }));
  await assert.rejects(stageVerdict(out), /confirm days.*split=confirm/);
  fs.rmSync(path.join(out, 'split.json'));
  const confirmRows = (src: string) => rows(src, src === 'real' ? 0 : 0.4, src === 'real' ? 37 : 38).map((r, i) => ({ ...r, src, day: `2026-11-${18 + (i % 3)}` }));
  for (const src of ['real', 'requote', 'depth']) fs.writeFileSync(path.join(out, `features-${src}.json`), JSON.stringify(confirmRows(src)));
  await assert.rejects(stageVerdict(out), /confirm look note/);
  const looked = await verdictLines(out, { n: 4, note: 'rows of the confirm days, no split file' });
  assert.ok(looked.lines.includes('[twin] CONFIRM LOOK #4: rows of the confirm days, no split file'));
  assert.ok(!looked.lines.some((l) => /quantiles|correlation gap|gives it away|every feature/.test(l)), 'blind by the days');
});

test('the verdict labels the feature values as medians, and the stages report a failure as one [twin] ERROR line', () => {
  const src = fs.readFileSync(path.join(ROOT, 'research/historyTwin.ts'), 'utf8');
  assert.match(src, /every feature \(AUC, real median\/twin median\)/); assert.match(src, /real median \$\{e\.real\}, twin median \$\{e\.twin\}/);
  assert.ok(!/real vs twin mean/.test(src), 'the old label said mean, the numbers are medians');
  const r = spawnSync(process.execPath, ['--import', 'tsx', 'research/historyTwin.ts', '--stage', 'real15m-check', '--dir', tmpDir(), '--days', '2026-11-13'], { encoding: 'utf8' });
  assert.notEqual(r.status, 0);
  assert.match(r.stdout, /^\[twin\] real 15-minute days: 0\/1 present/);
  assert.match(r.stderr, /^\[twin\] ERROR: real 15-minute days missing on Drive \(derived\/twin-real15m\): 2026-11-13\. Dispatch this workflow with prep_days=2026-11-13 first/, 'the first stderr line is the reason');
});

test('the depth fit keeps its own output: a failure names its cause, and the cells are not cut at 40 lines', () => {
  const y = wf();
  const step = stepScript(y, 'The depth model, fitted');
  assert.match(step, /depth\.log/); assert.match(step, /head -70/); assert.ok(!/head -40/.test(step));
  // run it with a stub node that fails: the reason (the last lines of its output) is in build.log as a [twin] ERROR
  const work = tmpDir(), bin = path.join(work, 'bin'), ws = path.join(work, 'ws'), tmp = path.join(work, 'tmp');
  fs.mkdirSync(bin); fs.mkdirSync(tmp); fs.mkdirSync(path.join(ws, 'data/twin-real15m'), { recursive: true });
  fs.mkdirSync(path.join(ws, '.github/scripts'), { recursive: true }); fs.copyFileSync(path.join(ROOT, '.github/scripts/twin-lib.sh'), path.join(ws, '.github/scripts/twin-lib.sh'));
  fs.writeFileSync(path.join(bin, 'node'), `#!/usr/bin/env bash\nif [ -n "$STUB_FAIL" ]; then echo "[depth] 3 day(s): x"; echo "Error: no whole recorded days"; exit 1; fi\nmkdir -p data/models; echo '{"days":[]}' > data/models/depth_model.json\necho "[depth] 3 day(s): a..b"; for i in $(seq 1 49); do echo "  tau$i mid$i n=$i spread p50 1"; done\n`, { mode: 0o755 });
  const env = { PATH: `${bin}:${process.env.PATH}`, FIT: '2026-11-11,2026-11-12', RUNNER_TEMP: tmp, GITHUB_WORKSPACE: ws };
  const bad = bash(stepScript(y, 'The depth model, fitted'), { ...env, STUB_FAIL: '1' }, ws);
  assert.notEqual(bad.status, 0);
  assert.match(fs.readFileSync(path.join(tmp, 'build.log'), 'utf8'), /\[twin\] ERROR: depth fit failed \(exit 1\) on the fit days 2026-11-11,2026-11-12; last lines: .*Error: no whole recorded days/);
  fs.rmSync(path.join(tmp, 'build.log'));
  const good = bash(stepScript(y, 'The depth model, fitted'), env, ws);
  assert.equal(good.status, 0, good.stderr);
  assert.equal(fs.readFileSync(path.join(tmp, 'build.log'), 'utf8').split('\n').filter((l) => /depth cell/.test(l)).length, 49, 'all 49 cells');
});

// ---------------------------------------------------------------------------------------------------------------
// Fix round 2: the confirm backtest legs print no byte count, a failure outside the build comment still says where and why,
// and a run whose backtest matrix is not whole is not a verdict. The workflow's own steps again (stubbed Drive, gh, node).

/** A workspace for a step that runs from the repo's checkout: twin-lib.sh in place, a stub bin dir first on the PATH. */
function stepWs(): { ws: string; bin: string; tmp: string } {
  const work = tmpDir(), ws = path.join(work, 'ws'), bin = path.join(work, 'bin'), tmp = path.join(work, 'tmp');
  for (const d of [bin, tmp, path.join(ws, '.github/scripts'), path.join(ws, 'deploy'), path.join(ws, 'data/twin')]) fs.mkdirSync(d, { recursive: true });
  fs.copyFileSync(path.join(ROOT, '.github/scripts/twin-lib.sh'), path.join(ws, '.github/scripts/twin-lib.sh'));
  return { ws, bin, tmp };
}
const expr = (script: string, v: Record<string, string> = {}) => script
  .replace(/\$\{\{ github\.run_id \}\}/g, v.run ?? '77').replace(/\$\{\{ job\.status \}\}/g, v.status ?? 'failure').replace(/\$\{\{ github\.repository \}\}/g, 'o/r')
  .replace(/\$\{\{ github\.sha \}\}/g, 'abc').replace(/\$\{\{ matrix\.how \}\}/g, v.how ?? 'depth').replace(/\$\{\{ matrix\.part \}\}/g, v.part ?? '0')
  .replace(/\$\{\{ inputs\.reverdict_run \}\}/g, '55');
/** A stub gh: a commit comment (-F body=@FILE) is copied to $GH_OUT, a jobs listing is $JOBS_JSON. */
const stubGh = (bin: string) => fs.writeFileSync(path.join(bin, 'gh'), `#!/usr/bin/env bash
for a in "$@"; do case "$a" in body=@*) cp "\${a#body=@}" "$GH_OUT"; exit 0;; esac; done
case "$*" in *"/jobs"*) if [ -n "$JOBS_JSON" ]; then cat "$JOBS_JSON"; else exit 1; fi;; esac
`, { mode: 0o755 });
const job = (name: string, ...steps: Array<[string, string]>) => ({ name, conclusion: steps.some(([, c]) => c === 'failure') ? 'failure' : 'success', steps: steps.map(([n, c]) => ({ name: n, conclusion: c })) });

test('the confirm backtest legs print no byte count of the per-window files kept on Drive (a size per day and source is check 4\'s quantity)', () => {
  const y = wf();
  const { ws, bin, tmp } = stepWs();
  // a drive_lab.sh that prints what the real one prints: 'kept on Drive: NAME (Total size: 3.4 KiB (3482 Byte))'
  fs.writeFileSync(path.join(ws, 'deploy/drive_lab.sh'), `#!/usr/bin/env bash
echo "$@" >> "$STUB_CALLS"
[ -z "$STUB_PUT_FAIL" ] || { echo "ERROR : windows-depth-p0-2026-11-18.json: Failed to copy: 403 (Total size: 3482 Byte)" >&2; exit 1; }
echo "kept on Drive: $2 (Total size: 3.400 KiB (3482 Byte))"
`, { mode: 0o755 });
  fs.mkdirSync(path.join(tmp, 'out'), { recursive: true }); fs.writeFileSync(path.join(tmp, 'out/windows-depth-p0-2026-11-18.json'), '[]');
  const calls = path.join(tmp, 'calls.txt');
  const run = (split: string, extra: Record<string, string> = {}) => { fs.rmSync(calls, { force: true }); return bash(expr(stepScript(y, 'Keep the per-window P&L on Drive')), { PATH: `${bin}:${process.env.PATH}`, SPLIT: split, RUNNER_TEMP: tmp, STUB_CALLS: calls, ...extra }, ws); };
  const blind = run('confirm');
  assert.equal(blind.status, 0, blind.stderr);
  const both = `${blind.stdout}${blind.stderr}`;
  assert.ok(!/3482|Total size|KiB|Byte|kept on Drive: simulated/.test(both), `no byte count of a confirm day on a confirm split: ${both}`);
  assert.match(both, /\[twin\] confirm window files kept on Drive \(sizes withheld on the confirm split\)/);
  assert.match(fs.readFileSync(calls, 'utf8'), /^put simulated\/history-twin\/77\/windows\/twin-depth-p0 /, 'the files are still kept on Drive');
  // a failing put on a confirm leg: the reason's class, not the put's output (which could carry a size)
  const failed = run('confirm', { STUB_PUT_FAIL: '1' });
  assert.notEqual(failed.status, 0);
  assert.ok(!/3482|Total size|Byte/.test(`${failed.stdout}${failed.stderr}`), `a failed confirm put prints no size either: ${failed.stdout}`);
  assert.match(failed.stdout, /\[twin\] confirm window files NOT kept on Drive \(drive_lab\.sh put exit 1\); its output is withheld on the confirm split/);
  assert.ok(!/Failed to copy|403|windows-depth/.test(`${failed.stdout}${failed.stderr}`), 'not even the put\'s error line: an rclone error can carry a size');
  // dev and custom keep the stock line
  const dev = run('dev');
  assert.equal(dev.status, 0, dev.stderr); assert.match(dev.stdout, /kept on Drive: simulated\/history-twin\/77\/windows\/twin-depth-p0 \(Total size: 3\.400 KiB \(3482 Byte\)\)/);
  // no per-window file: nothing to keep, nothing printed about sizes
  fs.rmSync(path.join(tmp, 'out'), { recursive: true });
  const none = run('confirm'); assert.equal(none.status, 0, none.stderr); assert.match(none.stdout, /no per-window file in this part/);
  // and no other step prints the real days' sizes on a confirm split
  assert.match(y, /\[ "\$SPLIT" = confirm \] \|\| du -sh \$T\/\* \| cat/);
});

/** The verdict job's Verdict step, run for real with a stub node: windows files from the legs, the job result, the split. */
function verdictStep(opts: { split: string; backtests?: boolean; result?: string; judged?: string[]; have?: Record<string, string[]>; parts?: number; fast?: string }) {
  const y = wf(), { ws, bin, tmp } = stepWs();
  const judged = opts.judged ?? ['2026-11-13', '2026-11-14', '2026-11-16'];
  const have = opts.have ?? { real: judged, placebo: judged, requote: judged, depth: judged };
  for (const [how, days] of Object.entries(have)) days.forEach((d, i) => {
    const dir = path.join(tmp, 'in', `twin-${how}-p${i}`); fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(path.join(dir, `windows-${how}-p${i}-${d}.json`), JSON.stringify([[`w${i}a`, 1.5], [`w${i}b`, -2]]));
  });
  fs.mkdirSync(path.join(tmp, 'in'), { recursive: true });
  const mark = path.join(tmp, 'node-called');
  fs.writeFileSync(path.join(bin, 'node'), `#!/usr/bin/env bash\ntouch "${mark}"\nmkdir -p data/twin; echo '{"paired":[]}' > data/twin/verdict.json\nls data/twin/windows-*.json 2>/dev/null | wc -l | sed 's/^ */[twin] stub verdict saw windows files: /'\necho "[twin] depth: adversary AUC 0.55"\n`, { mode: 0o755 });
  const r = bash(stepScript(y, 'Verdict'), { PATH: `${bin}:${process.env.PATH}`, RUNNER_TEMP: tmp, LOOK_N: '', LOOK_NOTE: '', BACKTESTS: opts.backtests === false ? 'false' : 'true', BT_RESULT: opts.result ?? 'success', JUDGED: judged.join(','), SPLIT: opts.split, ...(opts.fast === undefined ? {} : { FAST: opts.fast }) }, ws);
  const log = fs.existsSync(path.join(tmp, 'verdict.log')) ? fs.readFileSync(path.join(tmp, 'verdict.log'), 'utf8') : '';
  return { r, log, nodeCalled: fs.existsSync(mark), ws, tmp, out: `${r.stdout}${r.stderr}` };
}

test('a run whose backtest matrix has a red job, or a lost part, is not a verdict: the verdict job fails with a [twin] ERROR before any PASS/FAIL', () => {
  // whole: all four sources hold a file for every judged day; the stage runs (with the windows files in place) and the lines are kept in verdict.log
  const ok = verdictStep({ split: 'dev' });
  assert.equal(ok.r.status, 0, ok.out);
  for (const how of ['real', 'placebo', 'requote', 'depth']) assert.match(ok.log, new RegExp(`\\[twin\\] backtest legs ${how}: 3 of 3 judged day\\(s\\) have a per-window file, 6 window\\(s\\)`));
  assert.match(ok.log, /stub verdict saw windows files: 4/); assert.ok(ok.nodeCalled);
  assert.ok(ok.log.indexOf('backtest legs real') < ok.log.indexOf('adversary AUC'), 'the legs lines are kept (the stage output is appended, not written over them)');
  // a red backtest job (any leg), even when every file happens to be there: no verdict
  const red = verdictStep({ split: 'dev', result: 'failure' });
  assert.notEqual(red.r.status, 0); assert.equal(red.nodeCalled, false, 'the verdict stage never ran: no PASS/FAIL');
  assert.match(red.log, /^\[twin\] ERROR: backtest legs incomplete \(backtest jobs: failure; per-window day files real\/placebo\/requote\/depth = 3\/3\/3\/3 of 3\): checks 2-4 are not valid and no PASS\/FAIL is printed\. Re-dispatch once/m);
  // a lost twin part with the matrix reported green (a leg that exited 0 without a file): counted, and named by source
  const lostTwin = verdictStep({ split: 'dev', have: { real: ['2026-11-13', '2026-11-14', '2026-11-16'], placebo: ['2026-11-13', '2026-11-14', '2026-11-16'], requote: ['2026-11-13', '2026-11-14', '2026-11-16'], depth: ['2026-11-13', '2026-11-14'] } });
  assert.notEqual(lostTwin.r.status, 0); assert.equal(lostTwin.nodeCalled, false);
  assert.match(lostTwin.log, /\[twin\] ERROR: backtest legs incomplete \(backtest jobs: success; per-window day files real\/placebo\/requote\/depth = 3\/3\/3\/2 of 3\)/);
  // a lost PLACEBO part would loosen check 3 (its rmse is inflated by the missing real P&L): also refused
  const lostPlacebo = verdictStep({ split: 'dev', have: { real: ['2026-11-13', '2026-11-14', '2026-11-16'], placebo: ['2026-11-13', '2026-11-14'], requote: ['2026-11-13', '2026-11-14', '2026-11-16'], depth: ['2026-11-13', '2026-11-14', '2026-11-16'] } });
  assert.notEqual(lostPlacebo.r.status, 0); assert.match(lostPlacebo.log, /= 3\/2\/3\/3 of 3\)/);
  // every part lost (nothing on Drive): 0/0/0/0
  const none = verdictStep({ split: 'dev', result: 'failure', have: {} });
  assert.match(none.log, /= 0\/0\/0\/0 of 3\)/); assert.equal(none.nodeCalled, false);
  // a file for a day that was not judged does not stand in for a judged day
  const wrongDay = verdictStep({ split: 'dev', judged: ['2026-11-13', '2026-11-14'], have: { real: ['2026-11-13', '2026-11-16'], placebo: ['2026-11-13', '2026-11-14'], requote: ['2026-11-13', '2026-11-14'], depth: ['2026-11-13', '2026-11-14'] } });
  assert.match(wrongDay.log, /= 1\/2\/2\/2 of 2\)/);
  // no backtests: no guard, no legs lines, the stage runs as before
  const plain = verdictStep({ split: 'dev', backtests: false, result: 'skipped', have: {} });
  assert.equal(plain.r.status, 0, plain.out); assert.ok(plain.nodeCalled); assert.ok(!/backtest legs/.test(plain.log));
  // the confirm split: day-file counts only, no window count per source (check 4's own quantity), also in the error
  const confirm = verdictStep({ split: 'confirm', judged: ['2026-11-18', '2026-11-19', '2026-11-20'] });
  assert.equal(confirm.r.status, 0, confirm.out);
  assert.match(confirm.out, /\[twin\] backtest legs depth: 3 of 3 judged day\(s\) have a per-window file\n/);
  assert.ok(!/window\(s\)/.test(confirm.out), `no window counts on a confirm split: ${confirm.out}`);
  const confirmRed = verdictStep({ split: 'confirm', result: 'failure', judged: ['2026-11-18', '2026-11-19', '2026-11-20'] });
  assert.notEqual(confirmRed.r.status, 0); assert.ok(!/window\(s\)/.test(confirmRed.out) && !/-?\d+\.\d\d\b/.test(confirmRed.log.replace(/0\.55/g, '')));
});

test('the verdict and re-verdict comments say so, and where the job stopped, when no [twin] line exists', () => {
  const y = wf(), { bin, tmp } = stepWs();
  stubGh(bin);
  const sent = path.join(tmp, 'sent.md'), jobs = path.join(tmp, 'jobs.json');
  const lines = y.split('\n'), reverdict = lines.slice(lines.indexOf('  reverdict:')).join('\n');
  const report = (src: string, log: string | undefined, jobList: unknown[] | undefined) => {
    if (log !== undefined) fs.writeFileSync(path.join(tmp, 'verdict.log'), log); else fs.rmSync(path.join(tmp, 'verdict.log'), { force: true });
    if (jobList) fs.writeFileSync(jobs, JSON.stringify({ jobs: jobList }));
    fs.rmSync(sent, { force: true });
    const r = bash(expr(stepScript(src, 'Report (commit comment)')), { PATH: `${bin}:${process.env.PATH}`, RUNNER_TEMP: tmp, GH_OUT: sent, GH_TOKEN: 't', JOBS_JSON: jobList ? jobs : '' }, ROOT);
    assert.equal(r.status, 0, r.stderr);
    return fs.readFileSync(sent, 'utf8');
  };
  // the verdict job failed in its cache restore: no verdict.log; the comment names the step instead of an empty block
  const verdictJobs = [job('build', ['Report', 'success']), job('verdict', ['Set up job', 'success'], ['Restore dependencies', 'success'], ['actions/cache/restore@v4', 'failure'], ['Verdict', 'skipped'])];
  assert.match(report(y, undefined, verdictJobs), /^History twin verdict, run 77 \(failure\)\n\n```\n\(no \[twin\] lines: the verdict job failed before its Verdict step, at step "actions\/cache\/restore@v4"; the reason is an annotation of the run: gh run view 77\)\n```\n$/);
  // jobs that cannot be listed: still not an empty block
  assert.match(report(y, undefined, undefined), /\(no \[twin\] lines: the verdict job failed before its Verdict step; the reason is an annotation of the run: gh run view 77\)/);
  // with a log: the log, as before (features lines left out)
  const full = report(y, '[twin] ERROR: backtest legs incomplete (x)\n[twin] features real: 3\n', verdictJobs);
  assert.ok(full.includes('[twin] ERROR: backtest legs incomplete (x)') && !full.includes('features real') && !full.includes('no [twin] lines'));
  // the re-verdict job: the same fallback, found by its own job name, and it may list the run's jobs
  assert.match(reverdict, /permissions:\n      contents: write\n      actions: read/);
  assert.match(report(reverdict, undefined, [job('reverdict', ['The judged features in place', 'failure'])]), /^History twin re-verdict of run 55 \(run 77, failure\)\n\n```\n\(no \[twin\] lines: the re-verdict job failed before its Verdict step, at step "The judged features in place"; /);
});

test('twin_failed_steps names the failed step of each matching job, and never fails', () => {
  const { bin, tmp } = stepWs(); stubGh(bin);
  const jobs = path.join(tmp, 'jobs.json');
  fs.writeFileSync(jobs, JSON.stringify({ jobs: [
    job('prep-plan', ['Which days', 'failure']), job('prep (2026-11-13)', ['Already on Drive with this version tag?', 'success'], ['The raw day from Drive (recordings/)', 'failure'], ['Reduce it', 'skipped']),
    job('prep (2026-11-14)', ['Reduce it', 'success']), job('prep (2026-11-15)', ['Reduce it', 'failure'], ['Keep it on Drive', 'failure']), job('prep-report', ['Install', 'failure']),
  ] }));
  const run = (env: Record<string, string>) => spawnSync('bash', ['-c', 'source .github/scripts/twin-lib.sh; twin_failed_steps 77 o/r \'^prep \\(\'; echo "rc=$?"'], { cwd: ROOT, env: { PATH: `${bin}:${process.env.PATH}`, HOME: process.env.HOME ?? '', ...env }, encoding: 'utf8' });
  assert.equal(run({ JOBS_JSON: jobs }).stdout, 'prep (2026-11-13)\tThe raw day from Drive (recordings/)\nprep (2026-11-15)\tReduce it\nrc=0\n', 'prep-plan and prep-report are not prep days; only the first failed step of a job');
  assert.equal(run({ JOBS_JSON: '' }).stdout, 'rc=0\n', 'jobs that cannot be listed: nothing, and no failure');
});

test('the prep report says which step a failed day stopped at, from the run\'s jobs, and a failed day is never DONE', async () => {
  // the stage and the file it reads
  assert.deepEqual(parseFailedSteps('2026-11-13\tThe raw day from Drive\nnot a line\n2026-11-14\tKeep it\x07 on Drive\n'), { '2026-11-13': 'The raw day from Drive', '2026-11-14': 'Keep it  on Drive' });
  const dir = tmpDir(), marks = path.join(tmpDir(), 'marks'), { file } = rawDay(dir);
  await prepDay(file, path.join(marks, DAY), DAY);
  for (const d of ['2026-11-14', '2026-11-15']) fs.mkdirSync(path.join(marks, d), { recursive: true });
  const r = prepReport(marks, [DAY, '2026-11-14', '2026-11-15'], { [DAY]: 'Keep it on Drive (derived/twin-real15m; copy only)', '2026-11-14': 'The raw day from Drive (recordings/; the compact .mdc form is decoded)' });
  assert.deepEqual(r.done, []); assert.equal(r.notDone.length, 3);
  assert.match(r.lines[0], /^\[twin\] prep 2026-11-13: NOT DONE; the prep job failed at step "Keep it on Drive[^"]*" \(its reason is an annotation of this run: gh run view <run id>\); Drive holds a current meta\.json that may be from an earlier prep: prep it again with force_prep=true$/);
  assert.match(r.lines[1], /NOT DONE; the prep job failed at step "The raw day from Drive[^"]*" .*; no meta\.json on Drive$/);
  assert.match(r.lines[2], /NOT DONE; no meta\.json on Drive: the prep job failed, timed out or was cancelled \(its reason is an annotation of this run: gh run view <run id>\)$/);
  assert.equal(r.lines[3], '[twin] prep report: 0 of 3 day(s) done; not done: 2026-11-13, 2026-11-14, 2026-11-15');
  // the workflow's prep-report step, run end to end: a stub Drive (marks), a stub gh (the run's jobs), the real stage
  const y = wf(), { ws, bin, tmp } = stepWs(); stubGh(bin);
  fs.symlinkSync(path.join(ROOT, 'research'), path.join(ws, 'research')); fs.symlinkSync(path.join(ROOT, 'node_modules'), path.join(ws, 'node_modules'));
  const drive = tmpDir(); fs.mkdirSync(path.join(drive, 'derived/twin-real15m', DAY), { recursive: true });
  fs.copyFileSync(path.join(marks, DAY, 'meta.json'), path.join(drive, 'derived/twin-real15m', DAY, 'meta.json'));
  fs.writeFileSync(path.join(ws, 'deploy/drive_lab.sh'), `#!/usr/bin/env bash\ncase "$1" in get) [ -d "$STUB_DRIVE/$2" ] || exit 3; mkdir -p "$3"; cp -r "$STUB_DRIVE/$2/." "$3/";; esac\n`, { mode: 0o755 });
  const jobs = path.join(tmp, 'jobs.json');
  fs.writeFileSync(jobs, JSON.stringify({ jobs: [job('prep-plan', ['Which days', 'success']), job('prep (2026-11-13)', ['Keep it on Drive (derived/twin-real15m; copy only)', 'success']), job('prep (2026-11-14)', ['The raw day from Drive (recordings/; the compact .mdc form is decoded)', 'failure']), job('prep (2026-11-15)', ['Reduce it', 'success'])] }));
  const sent = path.join(tmp, 'sent.md');
  const rr = bash(expr(stepScript(y, 'Each day\'s commit mark from Drive')), { PATH: `${bin}:${process.env.PATH}`, RUNNER_TEMP: tmp, GH_OUT: sent, GH_TOKEN: 't', JOBS_JSON: jobs, GITHUB_SHA: '0123456789abcdef', STUB_DRIVE: drive, DAYS: JSON.stringify([DAY, '2026-11-14', '2026-11-15']), PREP_RESULT: 'failure' }, ws);
  assert.equal(rr.status, 0, `${rr.stdout}${rr.stderr}`);
  const c = fs.readFileSync(sent, 'utf8');
  assert.match(c, /^History twin prep, run 77 \(prep jobs: failure\), on commit /);
  assert.match(c, /\[twin\] prep 2026-11-13: DONE; /, 'a current mark and a green job is done');
  assert.match(c, /\[twin\] prep 2026-11-14: NOT DONE; the prep job failed at step "The raw day from Drive/, 'the step the day stopped at');
  assert.match(c, /\[twin\] prep 2026-11-15: NOT DONE; no meta\.json on Drive: the prep job failed, timed out or was cancelled/, 'a green job with no mark is still not done, without a step');
  assert.match(c, /\[twin\] prep report: 1 of 3 day\(s\) done; not done: 2026-11-14, 2026-11-15/);
  // the report job may list the run's jobs
  const lines = y.split('\n'), at = lines.indexOf('  prep-report:'), block = lines.slice(at, lines.findIndex((l, i) => i > at && /^  \S/.test(l))).join('\n');
  assert.match(block, /actions: read/);
});

test('a refused prep dispatch says why in a commit comment (prep-plan), and the prep jobs fail through twin_fail', () => {
  const y = wf(), { ws, bin, tmp } = stepWs(); stubGh(bin);
  const plan = (days: string) => { const gh = path.join(tmp, 'gh_out'); fs.writeFileSync(gh, ''); fs.rmSync(path.join(tmp, 'plan.log'), { force: true }); const r = bash(stepScript(y, 'Which days'), { PREP_DAYS: days, GITHUB_OUTPUT: gh, RUNNER_TEMP: tmp }, ws); return { ok: r.status === 0, out: fs.readFileSync(gh, 'utf8'), log: fs.existsSync(path.join(tmp, 'plan.log')) ? fs.readFileSync(path.join(tmp, 'plan.log'), 'utf8') : '', text: `${r.stdout}${r.stderr}` }; };
  const good = plan('2020-01-01, 2020-01-02,2020-01-01');
  assert.ok(good.ok, good.text); assert.equal(good.out.trim(), 'days=["2020-01-01","2020-01-02"]');
  const tomorrow = new Date(Date.now() + 2 * 86_400_000).toISOString().slice(0, 10);
  for (const [days, want] of [
    ['2026-11-31', /prep_days: '2026-11-31' is not a YYYY-MM-DD day/], ['foo,2020-01-01', /prep_days: 'foo' is not a YYYY-MM-DD day/], [tomorrow, /is not a whole recorded day yet/],
    [',', /prep_days names no day/], [Array.from({ length: 32 }, (_, i) => new Date(Date.UTC(2020, 0, 1 + i)).toISOString().slice(0, 10)).join(','), /at most 31 days per prep dispatch \(prep_days names 32\)/],
  ] as Array<[string, RegExp]>) {
    const r = plan(days); assert.equal(r.ok, false, days); assert.match(r.log, new RegExp(`^\\[twin\\] ERROR: .*${want.source}`, 'm')); assert.match(r.text, /::error::/);
  }
  // the report step of prep-plan: the plan's reason is the comment (prep and prep-report are skipped, so it is the only one)
  const sent = path.join(tmp, 'sent.md');
  const send = () => { fs.rmSync(sent, { force: true }); const r = bash(expr(stepScript(y, 'Report a refused dispatch')), { PATH: `${bin}:${process.env.PATH}`, RUNNER_TEMP: tmp, GH_OUT: sent, GH_GITHUB_SHA: '', GITHUB_SHA: '0123456789abcdef', GH_TOKEN: 't' }, ws); assert.equal(r.status, 0, r.stderr); return fs.readFileSync(sent, 'utf8'); };
  plan('2026-11-31');
  assert.match(send(), /^History twin prep plan, run 77 \(failure\), on commit 01234567: no prep ran\n\n```\n\[twin\] ERROR: prep_days: '2026-11-31' is not a YYYY-MM-DD day[^\n]*\n```\n$/);
  fs.rmSync(path.join(tmp, 'plan.log'));
  assert.match(send(), /\(no \[twin\] ERROR line: the plan failed before it checked the days; read the run's annotations: gh run view 77\)/);
  // a token with characters that could break the comment is neutralised
  assert.match(plan('a`b`c').log, /prep_days: 'a\?b\?c' is not a YYYY-MM-DD day/);
  // the prep jobs: no plain echo ::error:: left in them (twin_fail: the reason is in the job's log file as well)
  const lines = y.split('\n'), at = lines.indexOf('  prep:'), block = lines.slice(at, lines.findIndex((l, i) => i > at && /^  \S/.test(l))).join('\n');
  assert.ok(!/echo "::error::/.test(block) && /twin_fail "prep \$DAY: no recording for \$DAY on Drive/.test(block), 'a prep day that has no recording fails through twin_fail');
  // plan job permissions: contents write is only for that comment
  assert.match(y.split('\n').slice(lines.indexOf('  prep-plan:'), at).join('\n'), /permissions:\n      contents: write/);
});

// ---------------------------------------------------------------------------------------------------------------
// The depth simulator sweep (H2): the in-stream features, the FIT-days-only gate, the judge, the candidate search, the stage and the
// workflow's sweep jobs. Synthetic days only (tests/twinSweepSynth.ts): nothing here reads a recording.

const FIT_DAYS = [...SPLITS.dev.fit];
const DEV_JUDGED = [...SPLITS.dev.judge];
const gunzipLines = (f: string) => zlib.gunzipSync(fs.readFileSync(f)).toString('utf8').split('\n').filter(Boolean);
const resultsOfEvents = (evs: ReadonlyArray<Record<string, any>>) => new Map(evs.filter((e) => e.k === 'result').map((e) => [String(e.ticker), String(e.result)] as const));

test('in-stream rows equal the file route exactly (fillDayFile, then dayRows), and a sweep leaves no global behind', async () => {
  const day = '2026-11-12', evs = synthRequoteDay({ day, assets: ['BTC', 'ETH'], windows: 4, seed: 3 }) as Array<Record<string, any>>;
  const dir = tmpDir(), src = path.join(dir, `md-${day}.jsonl.gz`);
  writeEventsGz(src, evs);
  const results = resultsOfEvents(evs);
  assert.ok(results.size >= 8, 'a day of contracts with results');
  const own = synthModel({ days: FIT_DAYS });
  const withBlock = { ...own, params: { revertS: 20, tradeRateMult: 1.4 } };
  const cand: Partial<DepthSimParams> = { revertS: 4, stepSd: 0.2, flickBasePerSec: 1.5, sweepPrints: 5, withinSd: 0.4, activitySd: 1.1, capMult: 2, flickBackMinMs: 10, flickBackSpanMs: 300, tradeRateMult: 1.7, tradeSizeMult: 0.6, levelSizeMult: 1.8 };
  const keepFew = new Set([...results.keys()].slice(0, 5));
  const cases: Array<[string, typeof own, Partial<DepthSimParams> | undefined, ReadonlySet<string> | undefined]> = [
    ['defaults', own, undefined, undefined], ['a candidate', own, cand, undefined], ["the model's own block", withBlock, undefined, undefined], ['the block, then a candidate over it', withBlock, cand, undefined], ['a candidate and a keep set', own, cand, keepFew],
  ];
  const followBefore = JSON.stringify(Object.keys(followDiag));
  for (const [i, [label, model, params, keep]] of cases.entries()) {
    const dst = path.join(dir, `filled-${i}.jsonl.gz`);
    await fillDayFile(src, dst, { how: 'depth' }, model, params);
    const viaFile = await dayRows(dst, day, 'depth', results, keep, false);
    const sims = depthSims.length;
    const emitted: Array<Record<string, any>> = [];
    const live = await filledDayRows(evs, day, 'depth', results, model, params, { keep, diag: false, sink: (x) => emitted.push(x) });
    assert.equal(depthSims.length, sims, `${label}: the global simulator list did not grow`);
    assert.deepEqual(emitted, gunzipLines(dst).map((l) => JSON.parse(l)), `${label}: the in-stream route emits the very records the file route wrote, the tail the fill-in releases at the end included`);
    assert.ok(viaFile.length >= (keep ? 5 : 8) - 1, `${label}: ${viaFile.length} contract lives`);
    assert.deepEqual(live.rows, viaFile, `${label}: the in-stream rows are the file route's, number for number (a -0 told from a 0, a NaN from a number)`);
    assert.equal(live.events, gunzipLines(dst).length, `${label}: every emitted record went into the features`);
    assert.ok(live.sim.trades > 0 && live.sim.seconds > 0, `${label}: the fill-in's activity is reported`);
  }
  assert.equal(JSON.stringify(Object.keys(followDiag)), followBefore, 'diag false: the global follow diagnostics are not fed');
  // an async source reads the same as an array
  async function* stream() { for (const e of evs) yield e; }
  const a = await filledDayRows(stream(), day, 'depth', results, own, cand, { diag: false }), b = await filledDayRows(evs, day, 'depth', results, own, cand, { diag: false });
  assert.deepEqual(a.rows, b.rows);
  // the parameters matter: a candidate's rows are not the defaults'
  assert.notDeepEqual((await filledDayRows(evs, day, 'depth', results, own, cand, { diag: false })).rows, (await filledDayRows(evs, day, 'depth', results, own, undefined, { diag: false })).rows);
  // the row builder is what both routes share: pushed by hand it makes the same rows
  const rb = rowBuilder(day, 'depth', results, undefined, false);
  for (const e of evs) rb.push(e);
  assert.ok(rb.finish().length >= 8);
});

test('a sweep reads the dev split\'s FIT days only: a DEV day, a CONFIRM day, another day, another split or one day are refused', async () => {
  assert.deepEqual(resolveSweepFit('dev', FIT_DAYS.join(',')), FIT_DAYS);
  assert.deepEqual(resolveSweepFit('dev', '2026-11-12, 2026-11-11'), ['2026-11-12', '2026-11-11'], 'two of the three FIT days are enough');
  for (const [split, days, want] of [
    ['dev', `${FIT_DAYS.join(',')},2026-11-13`, /overlap.*2026-11-13/], ['dev', '2026-11-11,2026-11-14', /overlap.*2026-11-14/], ['dev', '2026-11-16,2026-11-17,2026-11-11', /overlap/],
    ['dev', '2026-11-11,2026-11-18', /confirm days.*2026-11-18/], ['dev', '2026-11-19,2026-11-20', /confirm days/], ['dev', '2026-11-11,2026-11-10', /not FIT days of the dev split: 2026-11-10/],
    ['dev', '2026-11-11,2026-11-21', /not FIT days of the dev split: 2026-11-21/], ['dev', '2026-11-11', /at least 2 fit days, got 1/], ['dev', '', /needs --fit-days/], ['dev', '2026-11-31,2026-11-11', /not a YYYY-MM-DD day/],
    ['confirm', FIT_DAYS.join(','), /split "confirm" is refused/], ['custom', FIT_DAYS.join(','), /split "custom" is refused/], ['weekly', FIT_DAYS.join(','), /refused/], ['', FIT_DAYS.join(','), /refused/],
  ] as Array<[string, string, RegExp]>) assert.throws(() => resolveSweepFit(split, days), want, `${split} ${days}`);
  // The stage refuses before it reads anything: no file of these paths exists. Every refusal names the days, never a count of rows.
  const dirs = { twinDir: path.join(tmpDir(), 'none'), realDir: path.join(tmpDir(), 'none'), modelFile: path.join(tmpDir(), 'none.json'), gen: 0, shard: 0, shards: 1, perShard: 1, out: tmpDir() };
  for (const [split, days, want] of [['confirm', FIT_DAYS.join(','), /split "confirm" is refused/], ['dev', '2026-11-11,2026-11-13', /overlap.*2026-11-13/], ['dev', '2026-11-11,2026-11-19', /confirm days/], ['dev', '2026-11-11,2026-11-12,2026-11-10', /not FIT days/]] as Array<[string, string, RegExp]>) {
    await assert.rejects(runSweep({ ...dirs, split, fitDays: days }), want, `${split} ${days}`);
    assert.deepEqual(fs.readdirSync(dirs.out), [], 'nothing written for a refused sweep');
  }
  // the command line: the same refusals, a non-zero exit, and the reason as the first stderr line
  const run = (...a: string[]) => spawnSync(process.execPath, ['--import', 'tsx', 'research/historyTwin.ts', '--stage', 'sweep', '--twin-requote', dirs.twinDir, '--real', dirs.realDir, '--depth-model', dirs.modelFile, '--out', dirs.out, ...a], { encoding: 'utf8' });
  const conf = run('--split', 'confirm', '--fit-days', FIT_DAYS.join(','), '--gen', '0');
  assert.notEqual(conf.status, 0); assert.match(conf.stderr, /^\[twin\] ERROR: a sweep reads the dev split's FIT days only: split "confirm" is refused/);
  const devDay = run('--fit-days', '2026-11-11,2026-11-13', '--gen', '0');
  assert.notEqual(devDay.status, 0); assert.match(devDay.stderr, /^\[twin\] ERROR: fit days and judged days overlap.*2026-11-13/);
  assert.match(run('--fit-days', FIT_DAYS.join(','), '--gen', '1.5').stderr, /--gen must be a whole number/);
  assert.match(run('--fit-days', FIT_DAYS.join(','), '--shard', '7/7').stderr, /shard 7 is not in 0\.\.6/);
  assert.match(spawnSync(process.execPath, ['--import', 'tsx', 'research/historyTwin.ts', '--stage', 'sweep', '--fit-days', FIT_DAYS.join(',')], { encoding: 'utf8' }).stderr, /sweep needs --twin-requote/);
});

test('a sweep refuses a depth model fitted on a DEV or CONFIRM day, and real days made by another version', async () => {
  const fx = await sweepFixture();
  const bad = path.join(tmpDir(), 'depth_model.json');
  for (const [days, want] of [[[...FIT_DAYS, '2026-11-13'], /overlap.*2026-11-13/], [[...FIT_DAYS, '2026-11-19'], /outside the fit set|overlap/], [['2026-11-11', '2026-11-10'], /outside the fit set: 2026-11-10/], [[], /does not record the days/]] as Array<[string[], RegExp]>) {
    fs.writeFileSync(bad, JSON.stringify(synthModel({ days })));
    await assert.rejects(runSweep({ ...fx.opts, modelFile: bad, out: tmpDir() }), want, days.join(','));
  }
  // a real day whose meta names another version is stale: the sweep names the prep dispatch to run, as the build does
  const stale = tmpDir(); for (const f of fs.readdirSync(fx.real)) fs.copyFileSync(path.join(fx.real, f), path.join(stale, f));
  fs.writeFileSync(path.join(stale, 'meta-2026-11-12.json'), JSON.stringify({ day: '2026-11-12', version: 'r15m-0|exclude=DOGE', bytes: 1 }));
  await assert.rejects(runSweep({ ...fx.opts, realDir: stale, out: tmpDir() }), /another version: 2026-11-12.*prep_days=2026-11-12 force_prep=true/);
  await assert.rejects(runSweep({ ...fx.opts, twinDir: tmpDir(), out: tmpDir() }), /needs the requote day and the cached real day of 2026-11-11 \(twin missing/);
  await assert.rejects(runSweep({ ...fx.opts, perShard: 0, out: tmpDir() }), /--candidates \(per shard\) must be a whole number from 1 to 500/);
  await assert.rejects(runSweep({ ...fx.opts, perShard: 501, out: tmpDir() }), /from 1 to 500/);
  await assert.rejects(runSweep({ ...fx.opts, gen: 1, out: tmpDir() }), /generation 1 needs --parents/);
});

test('the sweep\'s judge is the verdict\'s: the same loss, feature AUCs and regime AUCs; a short twin is loss 1, never 0.5', async () => {
  // the dev verdict over the same rows (300 real, a twin shifted on feature 0)
  const out = verdictDir('dev', () => rows('twin', 0.4, 32));
  const real: Row[] = JSON.parse(fs.readFileSync(path.join(out, 'features-real.json'), 'utf8')), twin: Row[] = JSON.parse(fs.readFileSync(path.join(out, 'features-depth.json'), 'utf8'));
  const { report } = await verdictLines(out);
  const v = report.twins.depth, j = judgeSweepRows(real, twin);
  assert.equal(+j.loss.toFixed(3), v.auc, 'the loss is the verdict\'s all-feature leave-one-day-out AUC');
  assert.equal(j.loss, +discriminate(real, twin, FEATURES.map((_, k) => k)).toFixed(6), 'and it is discriminate()\'s number, to the sixth place');
  assert.deepEqual(Object.keys(j.features), [...FEATURES], 'every one of the 13 features');
  for (const f of v.features as Array<{ name: string; auc: number }>) assert.ok(Math.abs(j.features[f.name] - f.auc) <= 0.0006, `${f.name}: ${j.features[f.name]} against the verdict's ${f.auc}`);
  for (const g of ['calm', 'normal', 'volatile']) { const a = v.regimes[g].auc; assert.ok(a === null ? j.regimes[g] === null : Math.abs((j.regimes[g] as number) - a) <= 0.0006, `regime ${g}`); }
  assert.equal(j.top3.length, 3); assert.equal(j.top3[0].name, 'spreadC', 'the shifted feature gives the twin away first');
  assert.ok(j.loss > 0.7 && !j.note);
  // the same rows twice score a flat 0.5, and a twin of nothing, or of a few rows, is not 0.5
  const same = judgeSweepRows(real, real.map((r) => ({ ...r, src: 'twin' })));
  assert.equal(same.loss, 0.5);
  for (const t of [[], twin.slice(0, MIN_SWEEP_LIVES - 1), twin.slice(0, Math.floor(real.length / 2) - 1)]) { const r = judgeSweepRows(real, t); assert.equal(r.loss, 1, `${t.length} twin lives`); assert.match(r.note!, /not judged/); assert.deepEqual(r.features, {}); }
  assert.equal(judgeSweepRows(real, twin.slice(0, Math.ceil(real.length / 2))).note, undefined, 'half the real lives is enough');
  assert.throws(() => judgeSweepRows(real.slice(0, MIN_SWEEP_LIVES - 1), twin), /the real FIT rows hold 19 lives/);
  // a candidate that breaks the adversary (NaN features) is not judged either
  const nan = twin.map((r) => ({ ...r, f: r.f.map(() => NaN) }));
  assert.ok(Number.isFinite(judgeSweepRows(real, nan).loss));
});

test('the judge refuses a day with no lives on either side: a flat 0.5 from skipped folds is never a score (per-day coverage)', () => {
  // 100 real and 100 twin lives on each of three days; the twin is fully separable on feature 0 (true AUC 1.0)
  const real = rows('real', 0, 1), twin = rows('twin', 5, 2), days = [...new Set(real.map((r) => r.day))].sort();
  assert.equal(days.length, 3);
  const onDay = (rs: Row[], ...ds: string[]) => rs.filter((r) => ds.includes(r.day));
  assert.ok(judgeSweepRows(real, twin).loss > 0.99, 'the whole set: the separable twin is found');
  // (1) real rows on ONE day only (twin on all three): every fold is skipped or single-class and the AUC came out 0.5; now a refusal
  assert.throws(() => judgeSweepRows(onDay(real, days[0]), twin), /real FIT rows are on 1 day\(s\) \(at least 2 are needed.*flat 0\.5\): refusing to judge/);
  // (2) a real day below the floor (one day thin)
  const thinReal = [...onDay(real, days[0], days[1]), ...onDay(real, days[2]).slice(0, MIN_DAY_LIVES - 1)];
  assert.ok(thinReal.length >= MIN_SWEEP_LIVES);
  assert.throws(() => judgeSweepRows(thinReal, twin), new RegExp(`fewer than ${MIN_DAY_LIVES} real lives \\(${days[2]} ${MIN_DAY_LIVES - 1}\\)`));
  // (3) twin rows on ONE day only: real on A, B, C against twin on C (and A and B have none): loss 1 with a note, never 0.5
  const oneTwinDay = judgeSweepRows(real, [...onDay(twin, days[2]), ...onDay(twin, days[2]).map((r, i) => ({ ...r, ticker: `X${i}` }))]);
  assert.equal(oneTwinDay.loss, 1); assert.match(oneTwinDay.note!, /a FIT day has no twin lives \(2026-10-20 0 twin against 100 real, 2026-10-21 0 twin against 100 real; at least 5 needed\): not judged/);
  assert.deepEqual(oneTwinDay.features, {}); assert.deepEqual(oneTwinDay.top3, []);
  // (4) real on days A and B against twin on day C only
  const ab = judgeSweepRows(onDay(real, days[0], days[1]), onDay(twin, days[2]));
  assert.equal(ab.loss, 1); assert.match(ab.note!, /no twin lives/); assert.notEqual(ab.loss, 0.5);
  // (5) one day short of twin lives (fewer than the floor), the others whole: still refused with a note, and it names the day
  const short = judgeSweepRows(real, [...onDay(twin, days[0], days[1]), ...onDay(twin, days[2]).slice(0, MIN_DAY_LIVES - 1)]);
  assert.equal(short.loss, 1); assert.match(short.note!, new RegExp(`${days[2]} ${MIN_DAY_LIVES - 1} twin against 100 real`));
  // (6) exactly the floor on a day is enough, and the judge then scores the separable twin high, not 0.5
  const edge = judgeSweepRows(real, [...onDay(twin, days[0], days[1]), ...onDay(twin, days[2]).slice(0, MIN_DAY_LIVES)]);
  assert.equal(edge.note, undefined); assert.ok(edge.loss > 0.9, `${edge.loss}`);
  // no input of any shape above made a 0.5 out of a separable twin
  for (const loss of [oneTwinDay.loss, ab.loss, short.loss]) assert.notEqual(loss, 0.5);
});

test('generation 0 is the defaults plus a Latin hypercube: seeded, in bounds, one point in every stratum', () => {
  const a = generationCandidates(0, 40), b = generationCandidates(0, 40);
  assert.deepEqual(a, b, 'the same inputs give the same candidates on every shard');
  assert.equal(a.length, 40); assert.deepEqual(a[0], { ...DEFAULT_DEPTH_SIM_PARAMS }, 'candidate 0 is today\'s defaults');
  assert.notDeepEqual(generationCandidates(0, 41).slice(1, 6), a.slice(1, 6), 'another population is another sample');
  assert.deepEqual(generationCandidates(0, 1), [{ ...DEFAULT_DEPTH_SIM_PARAMS }], 'a population of one is the defaults');
  for (const p of a) for (const n of DEPTH_PARAM_NAMES) {
    const s = DEPTH_PARAM_SPACE[n];
    assert.ok(Number.isFinite(p[n]) && p[n] >= s.lo && p[n] <= s.hi, `${n} ${p[n]} in [${s.lo}, ${s.hi}]`);
    if (s.int) assert.equal(p[n], Math.round(p[n]), `${n} is a whole number`);
  }
  // the sample (candidates 1..39): each parameter's range, in the sampling space, is cut in 39 strata and each is used once
  const lhs = a.slice(1);
  for (const n of DEPTH_PARAM_NAMES) {
    if (DEPTH_PARAM_SPACE[n].int) continue;
    const lo = toSpace(n, DEPTH_PARAM_SPACE[n].lo), r = toSpace(n, DEPTH_PARAM_SPACE[n].hi) - lo;
    const strata = lhs.map((p) => Math.min(lhs.length - 1, Math.floor(((toSpace(n, p[n]) - lo) / r) * lhs.length))).sort((x, y) => x - y);
    assert.deepEqual(strata, lhs.map((_, i) => i), `${n}: every stratum exactly once`);
  }
  // log-scaled parameters are sampled in log space: about half the sample is below the geometric mean of the bounds
  const geo = Math.sqrt(DEPTH_PARAM_SPACE.revertS.lo * DEPTH_PARAM_SPACE.revertS.hi);
  assert.ok(Math.abs(lhs.filter((p) => p.revertS < geo).length - lhs.length / 2) <= 1, 'log scale: half the draws below the geometric mean');
  assert.throws(() => generationCandidates(-1, 5), /generation must be a whole number of at least 0/); assert.throws(() => generationCandidates(0, 0), /at least one candidate/);
  assert.throws(() => generationCandidates(1, 5), /generation 1 needs a parents file/);
  // clipping and the transformed space round-trip
  const wild = clipParams({ ...DEFAULT_DEPTH_SIM_PARAMS, revertS: 1e9, stepSd: 1e-9, sweepPrints: 2.4, tradeRateMult: 0 });
  const near = (x: number, y: number) => Math.abs(x - y) <= 1e-12 * Math.abs(y);
  assert.ok(near(wild.revertS, DEPTH_PARAM_SPACE.revertS.hi) && wild.revertS <= DEPTH_PARAM_SPACE.revertS.hi, 'clipped to the upper bound, never past it'); assert.ok(near(wild.stepSd, DEPTH_PARAM_SPACE.stepSd.lo) && wild.stepSd >= DEPTH_PARAM_SPACE.stepSd.lo);
  assert.equal(wild.sweepPrints, 2); assert.ok(near(wild.tradeRateMult, DEPTH_PARAM_SPACE.tradeRateMult.lo) && wild.tradeRateMult >= DEPTH_PARAM_SPACE.tradeRateMult.lo);
  for (const n of DEPTH_PARAM_NAMES) assert.ok(Math.abs(fromSpace(n, toSpace(n, DEFAULT_DEPTH_SIM_PARAMS[n])) - DEFAULT_DEPTH_SIM_PARAMS[n]) < 1e-9, `${n} round-trips`);
});

/** A loss with a known best point: the distance to `target` in the sampling space, each parameter by its own range. */
function bowl(target: DepthSimParams) {
  return (p: DepthSimParams) => Math.sqrt(DEPTH_PARAM_NAMES.reduce((a, n) => a + ((toSpace(n, p[n]) - toSpace(n, target[n])) / (toSpace(n, DEPTH_PARAM_SPACE[n].hi) - toSpace(n, DEPTH_PARAM_SPACE[n].lo))) ** 2, 0));
}

test('cross-entropy generations: seeded, in bounds, centred on the elite, shrinking, and moving toward a better loss', () => {
  const target = clipParams(Object.fromEntries(DEPTH_PARAM_NAMES.map((n) => [n, fromSpace(n, (toSpace(n, DEPTH_PARAM_SPACE[n].lo) + 2 * toSpace(n, DEPTH_PARAM_SPACE[n].hi)) / 3)])) as unknown as DepthSimParams);
  const loss = bowl(target), pop = 60;
  const judged = (cs: DepthSimParams[]) => cs.map((params) => ({ params, loss: loss(params) }));
  let parents = judged(generationCandidates(0, pop));
  const best0 = Math.min(...parents.map((p) => p.loss)), median = (xs: number[]) => [...xs].sort((a, b) => a - b)[Math.floor(xs.length / 2)];
  const med0 = median(parents.map((p) => p.loss));
  // one step: deterministic, a different population from the previous generation's, every parameter inside its bounds
  const g1 = generationCandidates(1, pop, parents), again = generationCandidates(1, pop, parents);
  assert.deepEqual(g1, again); assert.notDeepEqual(g1, generationCandidates(2, pop, parents), 'another generation is another draw');
  assert.equal(g1.length, pop);
  for (const p of g1) for (const n of DEPTH_PARAM_NAMES) { const s = DEPTH_PARAM_SPACE[n]; assert.ok(p[n] >= s.lo && p[n] <= s.hi, `${n} ${p[n]}`); if (s.int) assert.equal(p[n], Math.round(p[n])); }
  // candidate 0 is the elite's mean (in the sampling space); the elite is the best 20 percent
  const elite = eliteOf(parents), st = eliteStats(elite);
  assert.equal(elite.length, Math.ceil(0.2 * pop)); assert.ok(elite.every((e) => e.loss <= median(parents.map((p) => p.loss))));
  assert.ok(Math.max(...elite.map((e) => e.loss)) <= [...parents].sort((x, y) => x.loss - y.loss)[elite.length - 1].loss + 1e-12);
  for (const n of DEPTH_PARAM_NAMES) assert.ok(Math.abs(toSpace(n, g1[0][n]) - st.mean[n]) <= (DEPTH_PARAM_SPACE[n].int ? 0.5 : 1e-9), `${n}: candidate 0 is the elite mean`);
  // the draws move toward the elite: closer to the elite mean than the first generation's sample was
  const centre = g1[0], spread = (cs: DepthSimParams[]) => cs.reduce((a, p) => a + DEPTH_PARAM_NAMES.reduce((s, n) => s + ((toSpace(n, p[n]) - toSpace(n, centre[n])) / (toSpace(n, DEPTH_PARAM_SPACE[n].hi) - toSpace(n, DEPTH_PARAM_SPACE[n].lo))) ** 2, 0), 0) / cs.length;
  assert.ok(spread(g1) < 0.5 * spread(generationCandidates(0, pop)), `generation 1 sits closer to the elite mean (${spread(g1).toFixed(3)} against ${spread(generationCandidates(0, pop)).toFixed(3)})`);
  assert.ok(loss(g1[0]) < med0, 'the elite mean beats the median of the first sample');
  // four steps: the median loss falls each time and the best ends below where the sample started
  let prevMed = med0; let best = best0;
  for (let g = 1; g <= 4; g++) {
    const cs = generationCandidates(g, pop, parents); parents = judged(cs);
    const m = median(parents.map((p) => p.loss)); assert.ok(m < prevMed, `generation ${g}: median loss ${m.toFixed(4)} below ${prevMed.toFixed(4)}`); prevMed = m;
    best = Math.min(best, ...parents.map((p) => p.loss));
  }
  assert.ok(best < 0.7 * best0, `the best loss fell from ${best0.toFixed(4)} to ${best.toFixed(4)}`);
  // an elite.json's entries are used whole (frac 1); the same parents as a plain list are cut to their best 20 percent
  assert.deepEqual(generationCandidates(1, 10, elite, 1), generationCandidates(1, 10, elite, 1));
  assert.notDeepEqual(generationCandidates(1, 10, parents, 1), generationCandidates(1, 10, parents));
});

test('a generation whose elite agrees does not collapse to a point, and a lone parent or no judged parent is handled', () => {
  const same = { params: { ...DEFAULT_DEPTH_SIM_PARAMS }, loss: 0.6 };
  const g = cemStep([same, { ...same, loss: 0.61 }, { ...same, loss: 0.9 }], 30, 7, 0.7);
  for (const n of DEPTH_PARAM_NAMES) assert.ok(Math.abs(g[0][n] - DEFAULT_DEPTH_SIM_PARAMS[n]) <= 1e-9 * DEFAULT_DEPTH_SIM_PARAMS[n], `${n}: candidate 0 is the elite mean (the defaults, all parents agree)`);
  for (const n of DEPTH_PARAM_NAMES.filter((k) => !DEPTH_PARAM_SPACE[k].int)) {
    const r = toSpace(n, DEPTH_PARAM_SPACE[n].hi) - toSpace(n, DEPTH_PARAM_SPACE[n].lo), xs = g.slice(1).map((p) => toSpace(n, p[n]));
    const m = xs.reduce((a, b) => a + b, 0) / xs.length, sd = Math.sqrt(xs.reduce((a, b) => a + (b - m) ** 2, 0) / xs.length);
    assert.ok(sd > 0.5 * CEM_SD_FLOOR * r, `${n}: the draws keep a spread of the floor (${(sd / r).toFixed(4)} of the range)`);
  }
  assert.equal(cemStep([same], 3, 1, 1).length, 3, 'one judged parent still gives a generation');
  assert.throws(() => cemStep([{ params: {}, loss: NaN }], 3, 1), /no judged candidate/);
  // unjudged (NaN) and 1-loss parents: the finite ones rank first
  assert.deepEqual(eliteOf([{ loss: NaN, id: 1 }, { loss: 0.7, id: 2 }, { loss: 0.6, id: 3 }, { loss: 1, id: 4 }, { loss: 0.8, id: 5 }], 0.4).map((x) => x.id), [3, 2]);
});

test('the shard split covers every candidate exactly once, in order, and shards differ by at most one', () => {
  for (const total of [1, 2, 7, 8, 13, 56, 70, 100, 3500]) for (let k = 1; k <= 7; k++) {
    const seen: number[] = [], sizes: number[] = [];
    for (let i = 0; i < k; i++) { const [lo, hi] = shardRange(total, k, i); assert.ok(lo <= hi); for (let c = lo; c < hi; c++) seen.push(c); sizes.push(hi - lo); }
    assert.deepEqual(seen, Array.from({ length: total }, (_, c) => c), `${total} candidates over ${k} shards`);
    assert.ok(Math.max(...sizes) - Math.min(...sizes) <= 1);
  }
  for (let k = 1; k <= 7; k++) for (const per of [1, 3, 10, 500]) for (let i = 0; i < k; i++) assert.deepEqual(shardRange(k * per, k, i), [i * per, (i + 1) * per], 'the workflow\'s population is shards x per-shard: each shard holds exactly its own per-shard block');
  assert.deepEqual(parseShard('0/7'), { shard: 0, shards: 7 }); assert.deepEqual(parseShard(' 6/7 '), { shard: 6, shards: 7 });
  for (const bad of ['7/7', '1', 'a/b', '0/0', '-1/3', '1/2/3', '']) assert.throws(() => parseShard(bad), /--shard must look like|not in 0\.\.|whole number of at least 1/, bad);
  assert.throws(() => shardRange(10, 0, 0), /whole number of at least 1/); assert.throws(() => shardRange(10, 3, 3), /not in 0\.\.2/); assert.throws(() => shardRange(10, 2.5, 0), /whole number/);
});

test('parents and params files are checked: known names, finite losses, a sweep best.json made on the FIT days only', async () => {
  // parentsFrom: a plain list (the best 20 percent is the elite) or an elite.json (used whole)
  const ok = { params: { revertS: 12 }, loss: 0.7 };
  assert.equal(parentsFrom([ok, ok]).frac, 0.2); assert.equal(parentsFrom({ kind: 'sweep-elite', elite: [ok] }).frac, 1);
  assert.deepEqual(parentsFrom([ok]).parents[0].params, { ...DEFAULT_DEPTH_SIM_PARAMS, revertS: 12 }, 'a partial block is merged over the defaults');
  for (const [bad, want] of [
    [[], /holds no candidates/], [{}, /holds no candidates/], [null, /holds no candidates/], [[{ params: { revertS: 12 } }], /entry 0 has no params and numeric loss/], [[{ loss: 0.5 }], /entry 0/],
    [[{ params: { revertz: 12 }, loss: 0.5 }], /unknown/i], [[{ params: { revertS: -3 }, loss: 0.5 }], /revertS/], [[{ params: { revertS: NaN }, loss: 0.5 }], /revertS/], [[ok, { params: {}, loss: '0.5' }], /entry 1/],
  ] as Array<[unknown, RegExp]>) assert.throws(() => parentsFrom(bad), want, JSON.stringify(bad));
  // loadDepthParamsFile
  const fx = await sweepFixture(), best = JSON.parse(fs.readFileSync(path.join(fx.collected, 'best.json'), 'utf8'));
  const dir = tmpDir(), put = (j: unknown, raw?: string) => { const f = path.join(dir, `p${fs.readdirSync(dir).length}.json`); fs.writeFileSync(f, raw ?? JSON.stringify(j)); return f; };
  const good = loadDepthParamsFile(path.join(fx.collected, 'best.json'));
  assert.deepEqual(good.params, best.params); assert.equal(good.gen, 0); assert.equal(good.loss, best.loss); assert.deepEqual(good.fitDays, FIT_DAYS);
  for (const [mod, want] of [
    [{ kind: 'sweep-elite' }, /is not a sweep-1 sweep best\.json/], [{ version: 'sweep-0' }, /is not a sweep-1 sweep best\.json/], [{ split: 'confirm' }, /was not made on the dev split/], [{ split: 'custom' }, /was not made on the dev split/],
    [{ fitDays: [...FIT_DAYS, '2026-11-13'] }, /overlap.*2026-11-13/], [{ fitDays: ['2026-11-11', '2026-11-18'] }, /confirm days/], [{ fitDays: ['2026-11-11'] }, /at least 2 fit days/], [{ fitDays: 'x' }, /needs --fit-days/],
    [{ params: undefined }, /no params and loss/], [{ loss: 'x' }, /no params and loss/], [{ params: { ...best.params, nope: 1 } }, /unknown/i], [{ params: { ...best.params, revertS: 0 } }, /revertS/], [{ params: { ...best.params, stepSd: -1 } }, /stepSd/],
  ] as Array<[Record<string, unknown>, RegExp]>) assert.throws(() => loadDepthParamsFile(put({ ...best, ...mod })), want, JSON.stringify(mod));
  assert.throws(() => loadDepthParamsFile(put(null, 'not json')), /not readable JSON/); assert.throws(() => loadDepthParamsFile(path.join(dir, 'missing.json')), /not readable JSON/);
});

// A small synthetic world for the stage tests: three FIT days of requote records, the same days filled in with the DEFAULT parameters
// as the "real" days (so candidate 0, the defaults, must score exactly 0.5), a depth model that records the FIT days, 2 shards x 3
// candidates of generation 0 judged and merged. Built once, on first use.
interface SweepFixture { root: string; twin: string; real: string; modelFile: string; shardsDir: string; collected: string; shards: number; per: number; opts: Parameters<typeof runSweep>[0] }
let fixtureOnce: Promise<SweepFixture> | undefined;
const sweepFixture = (): Promise<SweepFixture> => (fixtureOnce ??= buildSweepFixture());
async function buildSweepFixture(): Promise<SweepFixture> {
  const root = tmpDir(), twin = path.join(root, 'twin'), real = path.join(root, 'real'), shardsDir = path.join(root, 'shards'), collected = path.join(root, 'collected');
  for (const d of [twin, real]) fs.mkdirSync(d);
  const modelFile = path.join(root, 'depth_model.json');
  fs.writeFileSync(modelFile, JSON.stringify(synthModel({ days: FIT_DAYS })));
  const model = readDepthModel(modelFile)!;
  for (const [i, d] of FIT_DAYS.entries()) {
    writeEventsGz(path.join(twin, `md-${d}.jsonl.gz`), synthRequoteDay({ day: d, assets: ['BTC', 'ETH', 'SOL'], windows: 3, seed: 10 + i }));
    await fillDayFile(path.join(twin, `md-${d}.jsonl.gz`), path.join(real, `md-${d}.jsonl.gz`), { how: 'depth' }, model);
    fs.writeFileSync(path.join(real, `meta-${d}.json`), JSON.stringify({ day: d, version: real15mTag(), bytes: fs.statSync(path.join(real, `md-${d}.jsonl.gz`)).size }));
  }
  const opts = { split: 'dev', fitDays: FIT_DAYS.join(','), twinDir: twin, realDir: real, modelFile, gen: 0, shard: 0, shards: 2, perShard: 3, out: shardsDir, log: () => {} };
  for (const shard of [0, 1]) await runSweep({ ...opts, shard });
  const r = spawnSync(process.execPath, ['--import', 'tsx', 'research/historyTwin.ts', '--stage', 'sweep-collect', '--dir', shardsDir, '--gen', '0', '--shards', '2', '--candidates', '3', '--out', collected], { encoding: 'utf8' });
  assert.equal(r.status, 0, `${r.stdout}${r.stderr}`);
  return { root, twin, real, modelFile, shardsDir, collected, shards: 2, per: 3, opts };
}
const readJson = (f: string) => JSON.parse(fs.readFileSync(f, 'utf8'));
const noSeconds = (rs: Array<Record<string, any>>) => rs.map(({ seconds: _s, ...x }) => x);

test('a sweep refuses a FIT day whose requote tickers match no real lives (or only a few): a flat 0.5 for every candidate is never collected', async () => {
  // three FIT days of 15 requote contracts each (3 assets x 5 windows); the real day of `bad` is made from other contracts or from fewer of them
  const world = async (bad: string, realOf: Partial<Parameters<typeof synthRequoteDay>[0]> | undefined) => {
    const root = tmpDir(), twin = path.join(root, 'twin'), real = path.join(root, 'real'), out = path.join(root, 'out');
    for (const d of [twin, real]) fs.mkdirSync(d);
    const modelFile = path.join(root, 'depth_model.json');
    fs.writeFileSync(modelFile, JSON.stringify(synthModel({ days: FIT_DAYS })));
    const model = readDepthModel(modelFile)!;
    for (const [i, d] of FIT_DAYS.entries()) {
      const spec = { day: d, assets: ['BTC', 'ETH', 'SOL'], windows: 5, seed: 20 + i };
      writeEventsGz(path.join(twin, `md-${d}.jsonl.gz`), synthRequoteDay(spec));
      const src = d === bad && realOf ? path.join(root, `other-${d}.jsonl.gz`) : path.join(twin, `md-${d}.jsonl.gz`);
      if (d === bad && realOf) writeEventsGz(src, synthRequoteDay({ ...spec, ...realOf }));
      await fillDayFile(src, path.join(real, `md-${d}.jsonl.gz`), { how: 'depth' }, model);
      fs.writeFileSync(path.join(real, `meta-${d}.json`), JSON.stringify({ day: d, version: real15mTag(), bytes: fs.statSync(path.join(real, `md-${d}.jsonl.gz`)).size }));
    }
    return { split: 'dev', fitDays: FIT_DAYS.join(','), twinDir: twin, realDir: real, modelFile, gen: 0, shard: 0, shards: 1, perShard: 2, out, log: () => {} } as Parameters<typeof runSweep>[0];
  };
  // control: every real day made from its own requote day is judged (candidate 0 = the defaults on days the defaults made: exactly 0.5, by the real folds)
  const ok = await runSweep(await world('', undefined));
  assert.equal(ok.complete, true); assert.equal(ok.results[0].loss, 0.5); assert.equal(ok.results[0].realRows, 45);
  // a real day with none of the requote day's contracts: 30 lives are left in all (above the pooled floor of 20), so only the per-day guard sees it
  const none = await world('2026-11-12', { assets: ['XRP', 'LTC', 'ADA'] });
  await assert.rejects(runSweep(none), /the real FIT day\(s\) 2026-11-12 \(0 lives\) hold fewer than 5 contract lives that the requote day also has.*tickers do not match.*every candidate would read AUC 0\.5/);
  assert.ok(!fs.existsSync(none.out), 'nothing was written for the refused sweep');
  // a real day with only 3 of its 15 contracts, and two such days named together
  const thin = await world('2026-11-15', { windows: 1 });
  await assert.rejects(runSweep(thin), /the real FIT day\(s\) 2026-11-15 \(3 lives\) hold fewer than 5/);
  assert.ok(MIN_DAY_LIVES === 5, 'the floor the messages and the tests name');
});

test('a synthetic sweep end to end: shards judged on the FIT days, the defaults score 0.5 on a day they made, merged, the next generation, a rerun', async () => {
  const fx = await sweepFixture();
  const cands = generationCandidates(0, 6);
  const shardFiles: SweepShardFile[] = [0, 1].map((s) => readJson(path.join(fx.shardsDir, sweepShardName(0, s, 2))));
  for (const [s, f] of shardFiles.entries()) {
    assert.equal(f.kind, 'sweep-shard'); assert.equal(f.version, SWEEP_VERSION); assert.equal(f.complete, true); assert.equal(f.population, 6);
    assert.deepEqual(f.fitDays, FIT_DAYS); assert.deepEqual(f.modelDays, FIT_DAYS, 'the shard records the days its depth model was fitted on');
    assert.deepEqual(f.results.map((r) => r.index), [3 * s, 3 * s + 1, 3 * s + 2], 'a shard judges its own slice');
    for (const r of f.results) {
      assert.deepEqual(r.params, cands[r.index], `candidate ${r.index} is the generation's candidate ${r.index}`);
      assert.equal(r.realRows, 27); assert.equal(r.twinRows, 27); assert.deepEqual(Object.keys(r.features), [...FEATURES]); assert.equal(r.top3.length, 3);
      assert.ok(r.loss >= 0 && r.loss <= 1 && Number.isFinite(r.seconds));
    }
    assert.ok(!/KX[A-Z]+15M|KXBTC|T\d{2}:\d{2}/.test(JSON.stringify(f)), 'a shard file holds numbers and parameter names, no ticker');
  }
  const all = shardFiles.flatMap((f) => f.results);
  assert.equal(all.find((r) => r.index === 0)!.loss, 0.5, 'the defaults on days the defaults made: nothing to tell');
  for (const r of all.filter((x) => x.index > 0)) assert.ok(r.loss > 0.6, `candidate ${r.index}: ${r.loss}`);
  // the merge: best.json, elite.json, results.json
  const best = readJson(path.join(fx.collected, 'best.json')), elite = readJson(path.join(fx.collected, 'elite.json')), results = readJson(path.join(fx.collected, 'results.json'));
  assert.equal(best.kind, 'sweep-best'); assert.equal(best.index, 0); assert.equal(best.loss, 0.5); assert.deepEqual(best.params, { ...DEFAULT_DEPTH_SIM_PARAMS }); assert.equal(best.defaultLoss, 0.5);
  assert.equal(best.split, 'dev'); assert.deepEqual(best.fitDays, FIT_DAYS); assert.equal(best.evaluated, 6); assert.equal(best.gen, 0);
  assert.equal(elite.kind, 'sweep-elite'); assert.equal(elite.elite.length, 2); assert.deepEqual(elite.elite.map((e: { index: number }) => e.index), rankResults(all).slice(0, 2).map((r) => r.index));
  assert.deepEqual(results.results.map((r: { index: number }) => r.index), rankResults(all).map((r) => r.index));
  for (const f of ['best.json', 'elite.json', 'results.json']) assert.ok(fs.statSync(path.join(fx.collected, f)).size < 20_000, `${f} is small`);
  // the same shard again: the same numbers (only the clock differs)
  const rerun = await runSweep({ ...fx.opts, shard: 0, out: tmpDir() });
  assert.deepEqual(noSeconds(rerun.results as any), noSeconds(shardFiles[0].results as any), 'a rerun gives the same results, candidate by candidate');
  // generation 1 from the elite: the cross-entropy step, the slice of its shard, parents read as the whole elite
  const logs: string[] = [];
  const g1 = await runSweep({ ...fx.opts, gen: 1, shard: 1, parentsFile: path.join(fx.collected, 'elite.json'), out: tmpDir(), log: (l) => logs.push(l) });
  const want = generationCandidates(1, 6, parentsFrom(elite).parents, 1);
  assert.deepEqual(g1.results.map((r) => r.params), want.slice(3, 6)); assert.deepEqual(g1.results.map((r) => r.index), [3, 4, 5]); assert.equal(g1.gen, 1);
  assert.ok(logs.some((l) => /^\[twin\] sweep g1 shard 1\/2: candidates 3\.\.5 of 6 \(3 here\), 3 FIT day\(s\), 27 real lives/.test(l)));
  assert.ok(logs.every((l) => !/KX[A-Z]/.test(l)), 'the log carries numbers only');
  // generation 0 with a parents file ignores it, and says so
  const l0: string[] = []; await runSweep({ ...fx.opts, shard: 0, perShard: 1, shards: 1, parentsFile: path.join(fx.collected, 'elite.json'), out: tmpDir(), log: (l) => l0.push(l) });
  assert.ok(l0.some((l) => /generation 0 takes no parents/.test(l)));
});

test('a shard that ran out of time is kept as incomplete, and the merge refuses an incomplete, missing, mixed or mis-sliced generation', async () => {
  const fx = await sweepFixture();
  const cut = await runSweep({ ...fx.opts, shard: 0, budgetMin: 0, out: tmpDir(), log: () => {} });
  assert.equal(cut.complete, false); assert.deepEqual(cut.results, []);
  const dir = tmpDir(), put = (name: string, j: unknown) => fs.writeFileSync(path.join(dir, name), JSON.stringify(j));
  const s0: SweepShardFile = readJson(path.join(fx.shardsDir, sweepShardName(0, 0, 2))), s1: SweepShardFile = readJson(path.join(fx.shardsDir, sweepShardName(0, 1, 2)));
  const collect = (partial = false) => collectSweep(dir, { gen: 0, shards: 2, perShard: 3, partial });
  assert.throws(() => collect(), /no shard file for generation 0/);
  put(sweepShardName(0, 0, 2), s0);
  // a shard with no file: the refusal names the candidates and the shard, and what to do (a red job re-runs under its run id; a partial collect is a dispatch input of the run that runs the shards, never a re-collect)
  assert.throws(() => collect(), /3 of 6 candidates are missing \(3, 4, 5\); no result file for shard 1: a red shard job \(crashed, timed out\): gh run rerun RUN --failed\. A green but incomplete shard \(budget stop\): a re-run fails the same way; dispatch again with fewer sweep_candidates, or with sweep_partial=true on that dispatch \(a finished run cannot be re-collected as partial\)/);
  try { collect(); assert.fail('refused'); } catch (e) { const first = String((e as Error).message).split('\n')[0]; assert.ok(`[twin] ERROR: ${first}`.length <= 400, `the whole reason fits the 400 characters a commit comment keeps (${first.length})`); assert.ok(!/or collect it with partial|re-dispatch/.test(first), 'no advice that reads as a post-hoc collect'); }
  const part = collect(true); assert.match(part.lines[0], /3 of 6 candidates judged by 1 shard\(s\) \(3 missing: partial\)/); assert.equal((part.best as any).evaluated, 3);
  assert.ok(part.lines.includes('[twin] sweep g0: shard 1 has no result file (its job failed before its first candidate)'), 'a partial collect lists the shard with no file');
  put(sweepShardName(0, 1, 2), { ...s1, complete: false, results: s1.results.slice(0, 2) });
  assert.throws(() => collect(), /shard 1 is not complete \(2 of 3 candidates\): a red shard job .*gh run rerun RUN --failed.*sweep_partial=true on that dispatch/);
  const part2 = collect(true); assert.equal((part2.results as any).results.length, 5);
  assert.ok(part2.lines.includes('[twin] sweep g0: shard 1 incomplete: 2 of 3 candidates judged (it stopped at its budget, or its job failed)'), 'a partial collect lists the incomplete shard (a green job that stopped at its budget is one)');
  assert.ok(!part2.lines.some((l) => /has no result file/.test(l)), 'a shard with a file is not "no file"');
  put(sweepShardName(0, 1, 2), cut); // an empty incomplete shard beside a whole one
  assert.throws(() => collect(), /shard 0 is not complete \(0 of 3 candidates\)/);
  put(sweepShardName(0, 1, 2), s1);
  const whole = collect(); assert.match(whole.lines[0], /^\[twin\] sweep g0: 6 of 6 candidates judged by 2 shard\(s\); best loss 0\.5000 \(c0\)/); assert.match(whole.lines[1], /the defaults \(c0\) score 0\.5000; no candidate beat them/);
  assert.equal(whole.lines.filter((l) => /^\[twin\] sweep top \d: c\d+ loss/.test(l)).length, 5, 'the top 5 are printed');
  // the exact best parameters, every digit, on one line: what a promotion to the code defaults pastes (the 4-digit lines are for reading)
  put(sweepShardName(0, 1, 2), { ...s1, results: s1.results.map((r) => (r.index === 4 ? { ...r, loss: 0.1 } : r)) });
  const win = collect(), exactLines = win.lines.filter((l) => l.startsWith('[twin] sweep best params exact'));
  assert.equal(exactLines.length, 1, 'one line');
  const em = /^\[twin\] sweep best params exact \(g0 c4, loss 0\.1000\): (\{.*\})$/.exec(exactLines[0]);
  assert.ok(em, exactLines[0]);
  const exactParams = JSON.parse(em![1]), winner = (win.best as { params: DepthSimParams }).params;
  assert.deepEqual(exactParams, winner, 'to the last digit: the JSON reads back as the very same numbers');
  assert.deepEqual(exactParams, generationCandidates(0, 6)[4], 'and they are candidate 4\'s');
  assert.deepEqual(resolveDepthSimParams(exactParams), winner, 'a valid parameter set, as the code defaults would hold it');
  assert.ok(DEPTH_PARAM_NAMES.some((n) => describeParams(winner).includes(`${n} ${+winner[n].toPrecision(4)}`) && +winner[n].toPrecision(4) !== winner[n]), 'the 4-digit lines round it: that is why the exact line exists');
  assert.ok(Object.keys(exactParams).length === DEPTH_PARAM_NAMES.length && !/KX[A-Z]|\$/.test(exactLines[0]), 'all 13, names and numbers only');
  put(sweepShardName(0, 1, 2), s1);
  // numbers and parameter names only
  assert.ok(whole.lines.every((l) => /^\[twin\] sweep/.test(l) && !/KX[A-Z]|\$/.test(l)));
  // mixed generations, fit days, models, slices
  assert.throws(() => collectSweep(dir, { gen: 0, shards: 3, perShard: 3 }), /no shard file for generation 0/, 'another shard count finds no file of that name');
  assert.throws(() => collectSweep(dir, { gen: 1, shards: 2, perShard: 3 }), /no shard file for generation 1/, 'nor does another generation');
  put(sweepShardName(0, 1, 2), { ...s1, fitDays: ['2026-11-11', '2026-11-12'] });
  assert.throws(() => collect(), /different fit days or depth models/);
  for (const [mod, want] of [
    [{ fitDays: [...FIT_DAYS, '2026-11-13'], }, /overlap.*2026-11-13/], [{ modelDays: [...FIT_DAYS, '2026-11-14'] }, /overlap.*2026-11-14/], [{ modelDays: ['2026-11-11', '2026-11-10'] }, /outside the fit set: 2026-11-10/], [{ modelDays: [] }, /does not record the days/],
    [{ version: 'sweep-0' }, /is not a sweep-1 shard/], [{ kind: 'sweep-best' }, /is not a sweep-1 shard/], [{ perShard: 4 }, /is not generation 0/],
  ] as Array<[Partial<SweepShardFile>, RegExp]>) { put(sweepShardName(0, 0, 2), { ...s0, ...mod }); put(sweepShardName(0, 1, 2), { ...s1, ...mod }); assert.throws(() => collect(), want, JSON.stringify(mod)); }
  put(sweepShardName(0, 0, 2), s0); put(sweepShardName(0, 1, 2), { ...s1, shard: 0 }); // a file that claims another shard's slice
  assert.throws(() => collect(), /candidate 3 \(generation 0\) does not belong to shard 0 of generation 0/);
  put(sweepShardName(0, 1, 2), { ...s1, results: s1.results.map((r) => ({ ...r, gen: 1 })) });
  assert.throws(() => collect(), /does not belong to shard 1 of generation 0/);
  put(sweepShardName(0, 1, 2), { ...s1, results: [...s1.results, s0.results[0]] });
  assert.throws(() => collect(), /candidate 0 \(generation 0\) does not belong to shard 1 of generation 0/);
  // two files covering the same candidates: the merge names it
  assert.throws(() => mergeShards([s0, { ...s1, shard: 0 }], { gen: 0, shards: 2, perShard: 3 }), /does not belong to shard 0/);
  assert.throws(() => mergeShards([s0, s0], { gen: 0, shards: 2, perShard: 3 }), /appears twice/);
});

test('the depth fill-in takes a sweep\'s best.json (--depth-params), logs every parameter it used, and refuses it where it must', async () => {
  const fx = await sweepFixture(), work = tmpDir();
  const day = '2026-11-13', src = path.join(work, 'src'); fs.mkdirSync(src);
  writeEventsGz(path.join(src, `md-${day}.jsonl.gz`), synthRequoteDay({ day, assets: ['BTC', 'ETH'], windows: 3, seed: 5 }));
  const cand = generationCandidates(0, 6)[2];
  const best = { ...readJson(path.join(fx.collected, 'best.json')), index: 2, loss: 0.9, params: cand };
  const bestFile = path.join(work, 'best.json'); fs.writeFileSync(bestFile, JSON.stringify(best));
  const fill = (dst: string, ...a: string[]) => spawnSync(process.execPath, ['--import', 'tsx', 'research/historyTwin.ts', '--stage', 'fill', '--src', src, '--dst', path.join(work, dst), '--how', 'depth', '--depth-model', fx.modelFile, ...a], { encoding: 'utf8' });
  const plain = fill('plain'), tuned = fill('tuned', '--depth-params', bestFile);
  assert.equal(plain.status, 0, plain.stderr); assert.equal(tuned.status, 0, tuned.stderr);
  // the defaults as the code has them (read from DEFAULT_DEPTH_SIM_PARAMS, not spelled out: a promotion of a sweep's winners changes them)
  assert.ok(plain.stdout.split('\n').includes(`[twin] depth simulator parameters (defaults, as in the code): ${describeParams(DEFAULT_DEPTH_SIM_PARAMS)}`), plain.stdout);
  assert.equal(describeParams(DEFAULT_DEPTH_SIM_PARAMS).split(', ').length, DEPTH_PARAM_NAMES.length, 'all of them, one name each');
  const used = /\[twin\] depth simulator parameters \(sweep best, generation 0, loss 0\.9, fitted on FIT days only\): (.*)/.exec(tuned.stdout);
  assert.ok(used, tuned.stdout); assert.equal(used![1], describeParams(cand), 'the log names every parameter and the value used');
  assert.equal(used![1].split(', ').length, DEPTH_PARAM_NAMES.length);
  const name = `md-${day}.jsonl.gz`, lines = (d: string) => gunzipLines(path.join(work, d, name));
  assert.notDeepEqual(lines('tuned'), lines('plain'), 'the sweep\'s parameters move the filled day');
  const model = readDepthModel(fx.modelFile)!;
  await fillDayFile(path.join(src, name), path.join(work, 'inproc.jsonl.gz'), { how: 'depth' }, model, cand);
  assert.deepEqual(lines('tuned'), gunzipLines(path.join(work, 'inproc.jsonl.gz')), 'the stage fills in as the library does with those params');
  // a split on record: dev takes them; a confirm split and a split that judges a day the sweep fitted on do not
  const split = (sp: object) => { const f = path.join(work, `split-${fs.readdirSync(work).length}.json`); fs.writeFileSync(f, JSON.stringify(sp)); return f; };
  const dev = fill('dev', '--depth-params', bestFile, '--split-file', split({ name: 'dev', fit: FIT_DAYS, judge: DEV_JUDGED, warm: [] }));
  assert.equal(dev.status, 0, dev.stderr); assert.match(dev.stdout, /depth model fitted on fit days only/);
  const conf = fill('c', '--depth-params', bestFile, '--split-file', split({ name: 'confirm', fit: [...SPLITS.confirm.fit], judge: [...SPLITS.confirm.judge], warm: [] }));
  assert.notEqual(conf.status, 0); assert.match(conf.stderr, /^\[twin\] ERROR: depth_params_run is for dev and custom dispatches: the confirm run uses the code defaults/m);
  assert.equal(fill('c2', '--split-file', split({ name: 'confirm', fit: [...SPLITS.confirm.fit], judge: [...SPLITS.confirm.judge], warm: [] })).status, 0, 'a confirm fill-in without sweep params is the usual one');
  const small = path.join(work, 'small_model.json'); fs.writeFileSync(small, JSON.stringify(synthModel({ days: ['2026-11-11', '2026-11-12'] })));
  const leak = spawnSync(process.execPath, ['--import', 'tsx', 'research/historyTwin.ts', '--stage', 'fill', '--src', src, '--dst', path.join(work, 'l'), '--how', 'depth', '--depth-model', small, '--depth-params', bestFile, '--split-file', split({ name: 'custom', fit: ['2026-11-11', '2026-11-12'], judge: ['2026-11-15', '2026-11-13'], warm: [] })], { encoding: 'utf8' });
  assert.notEqual(leak.status, 0); assert.match(leak.stderr, /fit days and judged days overlap.*2026-11-15/, 'params fitted on 11-15 do not go to a split that judges it');
  // a file that is not a sweep's best, or was made on days outside the FIT days
  for (const [mod, want] of [[{ kind: 'sweep-elite' }, /is not a sweep-1 sweep best\.json/], [{ fitDays: [...FIT_DAYS, '2026-11-13'] }, /overlap.*2026-11-13/], [{ split: 'confirm' }, /was not made on the dev split/], [{ params: { ...cand, bogus: 1 } }, /unknown/i]] as Array<[object, RegExp]>) {
    const bad = fill('bad', '--depth-params', split({ ...best, ...mod })); assert.notEqual(bad.status, 0); assert.match(bad.stderr, new RegExp(`^\\[twin\\] ERROR: .*${want.source}`, 'm'), JSON.stringify(mod));
  }
  // a model with its own params block: logged as such, and a sweep's params go over it
  const blockModel = path.join(work, 'block_model.json'); fs.writeFileSync(blockModel, JSON.stringify({ ...synthModel({ days: FIT_DAYS }), params: { revertS: 25 } }));
  const own = spawnSync(process.execPath, ['--import', 'tsx', 'research/historyTwin.ts', '--stage', 'fill', '--src', src, '--dst', path.join(work, 'own'), '--how', 'depth', '--depth-model', blockModel], { encoding: 'utf8' });
  assert.match(own.stdout, /parameters \(the model's own params block\): revertS 25, /);
});

// ---------------------------------------------------------------------------------------------------------------
// The workflow's sweep jobs (sweep-plan, sweep, sweep-collect) and depth_params_run: the text held to the code's FIT days, and the
// jobs' own steps run with stubbed Drive, gh and node.

const jobText = (y: string, name: string): string => { const lines = y.split('\n'), at = lines.indexOf(`  ${name}:`); assert.ok(at >= 0, `job ${name}`); const end = lines.findIndex((l, i) => i > at && /^  \S/.test(l)); return lines.slice(at, end < 0 ? undefined : end).join('\n'); };
const stubDrive = (ws: string) => fs.writeFileSync(path.join(ws, 'deploy/drive_lab.sh'), `#!/usr/bin/env bash
[ -n "\${STUB_CALLS:-}" ] && echo "$*" >> "$STUB_CALLS"
case "$1" in
  get) [ -d "$STUB_DRIVE/$2" ] || exit 3; mkdir -p "$3"; cp -r "$STUB_DRIVE/$2/." "$3/";;
  put) dst="$STUB_DRIVE/$2"; src="$3"; shift 3; mkdir -p "$dst"
       while [ $# -gt 0 ]; do if [ "$1" = --include ]; then for f in "$src"/$2; do [ -f "$f" ] && cp "$f" "$dst/"; done; shift; fi; shift; done;;
esac
`, { mode: 0o755 });
/** A workspace for the steps that run the real stage: the repo's research code and node_modules linked in. */
function stageWs() { const w = stepWs(); fs.symlinkSync(path.join(ROOT, 'research'), path.join(w.ws, 'research')); fs.symlinkSync(path.join(ROOT, 'node_modules'), path.join(w.ws, 'node_modules')); stubDrive(w.ws); stubGh(w.bin); return w; }

test('the sweep jobs are wired as the brief says: dispatch-only, exclusive, 7 wide, 340 minutes, production, one heavy group, FIT days only', () => {
  const y = wf(), plan = jobText(y, 'sweep-plan'), shard = jobText(y, 'sweep'), collect = jobText(y, 'sweep-collect');
  assert.match(plan, /if: .*github\.event_name == 'workflow_dispatch' && inputs\.sweep_gen != ''/);
  assert.match(shard, /needs: sweep-plan/); assert.match(shard, /if: .*needs\.sweep-plan\.result == 'success'/); assert.match(shard, /environment: production/); assert.match(shard, /timeout-minutes: 340\b/);
  assert.match(shard, /max-parallel: 7\b/); assert.match(shard, /fail-fast: false/); assert.match(shard, /shard: \$\{\{ fromJSON\(needs\.sweep-plan\.outputs\.shards\) \}\}/);
  assert.match(collect, /needs: \[sweep-plan, sweep\]/); assert.match(collect, /if: .*always\(\) && needs\.sweep-plan\.result == 'success'/); assert.match(collect, /environment: production/); assert.match(collect, /actions: read/);
  // a sweep dispatch runs none of the other jobs, and they run none of its
  for (const j of ['prep-plan', 'build', 'reverdict']) assert.match(jobText(y, j), /inputs\.sweep_gen == ''/, `${j} does not run on a sweep dispatch`);
  assert.match(jobText(y, 'reverdict'), /inputs\.reverdict_run != '' && inputs\.sweep_gen == ''/);
  // the days of a sweep are the dev FIT days, spelled out once and held to SPLITS; no input can change them, and no DEV or CONFIRM day is named
  assert.match(shard, new RegExp(`\\n      FIT: ${SPLITS.dev.fit.join(',')}\\n`), 'the FIT env is SPLITS.dev.fit');
  const all = `${plan}\n${shard}\n${collect}`;
  for (const d of [...DEV_JUDGED, ...CONFIRM_DAYS]) assert.ok(!all.includes(d), `the sweep jobs do not name ${d}`);
  assert.ok(!/inputs\.(fit_days|judge_days|warm_day|prep_days|model_drive|lag_arms|backtests|confirm_look_note)/.test(`${shard}\n${collect}`), 'the shards and the collect read no day or split input');
  assert.match(plan, /SPLIT: \$\{\{ inputs\.split \|\| 'dev' \}\}/);
  assert.match(shard, /--stage sweep --split dev --fit-days "\$FIT"/); assert.match(shard, /--depth-model data\/models\/depth_model\.json/);
  assert.ok(!/--stage (match|fill|features|verdict|backtest)/.test(shard), 'a shard runs the sweep stage only: no judged day is matched, filled in or read');
  assert.ok(!/derived\/twin-real15m"? data|recordings\//.test(shard.replace(/derived\/twin-real15m\/\$d/g, '')), 'the shards read the prepped FIT days, never a raw recording');
  // Drive is copy only, and the real days are read from the prep's cache
  assert.ok(!/rclone (sync|move|moveto|delete|deletefile|purge|rmdir|cleanup|rcat)|drive_lab\.sh (rm|delete|purge|sync|move)|--delete|--purge/.test(all), 'no delete, sync or move on Drive');
  assert.deepEqual([...all.matchAll(/drive_lab\.sh (\w+)/g)].map((m) => m[1]).filter((v, i, a) => a.indexOf(v) === i).sort(), ['get', 'put']);
  assert.ok(!/upload-artifact|actions\/cache\/save/.test(all), 'no artifact and no cache write: the repository is public');
  // inputs
  const ins = y.slice(y.indexOf('workflow_dispatch:'), y.indexOf('\npermissions:'));
  for (const k of ['sweep_gen', 'sweep_candidates', 'sweep_shards', 'sweep_parents_run', 'sweep_partial', 'depth_params_run']) assert.match(ins, new RegExp(`\\n      ${k}:\\n        description: `), `input ${k} is documented`);
  assert.ok([...ins.matchAll(/^      [a-z_]+:$/gm)].length <= 25, 'GitHub takes at most 25 dispatch inputs');
  // the header documents it
  const head = y.slice(0, y.indexOf('\non:'));
  for (const w of ['THE SWEEP (sweep_gen', "RUNBOOK 'The depth simulator sweep'", 'FIT days only', 'depth_params_run=RUN', 'sweep_parents_run', 'simulated/history-twin-sweep/RUN', 'best.json, elite.json', 'one concurrency group']) assert.ok(head.includes(w), `the header says: ${w}`);
  assert.ok(y.includes("group: history-twin-${{ inputs.reverdict_run && 'reverdict' || 'heavy' }}"), 'a sweep is in the heavy group with prep and build');
});

const hasYaml = spawnSync('python3', ['-c', 'import yaml'], { encoding: 'utf8' }).status === 0;
test('the workflow is valid YAML and the sweep jobs parse as the text tests read them', { skip: hasYaml ? false : 'python3 with PyYAML is not installed here' }, () => {
  const r = spawnSync('python3', ['-I', '-c', 'import yaml,json,sys; print(json.dumps(yaml.safe_load(open(sys.argv[1]))))', path.join(ROOT, '.github/workflows/history-twin.yml')], { encoding: 'utf8' });
  assert.equal(r.status, 0, r.stderr);
  const d = JSON.parse(r.stdout), on = d.true ?? d.on, jobs = d.jobs as Record<string, any>;
  assert.deepEqual(Object.keys(jobs), ['prep-plan', 'prep', 'prep-report', 'build', 'backtest', 'verdict', 'reverdict', 'sweep-plan', 'sweep', 'sweep-collect']);
  assert.equal(jobs.sweep.strategy['max-parallel'], 7); assert.equal(jobs.sweep['timeout-minutes'], 340); assert.equal(jobs.sweep.environment, 'production'); assert.equal(jobs.sweep.needs, 'sweep-plan');
  assert.match(jobs.sweep.strategy.matrix.shard, /fromJSON\(needs\.sweep-plan\.outputs\.shards\)/); assert.deepEqual(jobs['sweep-collect'].needs, ['sweep-plan', 'sweep']);
  for (const [n, j] of Object.entries(jobs)) if (j.strategy) assert.ok(j.strategy['max-parallel'] <= 7, `${n} runs at most 7 at once`);
  assert.deepEqual(Object.keys(jobs['sweep-plan'].outputs), ['gen', 'shards', 'shard_count', 'per', 'parents']);
  const ins = on.workflow_dispatch.inputs;
  for (const k of ['sweep_gen', 'sweep_candidates', 'sweep_shards', 'sweep_parents_run', 'sweep_partial', 'depth_params_run']) assert.ok(ins[k]?.description, k);
  assert.equal(ins.sweep_gen.default, ''); assert.equal(ins.sweep_candidates.default, '8'); assert.equal(ins.sweep_shards.default, '7'); assert.equal(ins.sweep_partial.type, 'boolean'); assert.equal(ins.depth_params_run.default, '');
  assert.ok(Object.keys(ins).length <= 25);
  const names = (j: string) => (jobs[j].steps as Array<{ name?: string }>).map((s) => s.name ?? '').filter(Boolean);
  assert.equal(new Set(names('sweep')).size, names('sweep').length, 'step names are unique within the shard job'); assert.ok(names('sweep').length >= 10);
  for (const j of ['sweep-plan', 'sweep', 'sweep-collect']) for (const s of jobs[j].steps) assert.ok(!('continue-on-error' in s), 'no step hides its failure');
});

test('sweep-plan accepts a clean dispatch and refuses every other: a sweep is exclusive, dev only, 1 to 7 shards of 1 to 500, parents from generation 1', () => {
  const y = wf(), { ws, tmp } = stageWs();
  const plan = (env: Record<string, string>) => {
    const gh = path.join(tmp, 'gh_out'); fs.writeFileSync(gh, ''); fs.rmSync(path.join(tmp, 'plan.log'), { force: true });
    const r = bash(stepScript(y, 'Which generation'), { SWEEP_GEN: '0', CANDIDATES: '8', SHARDS: '7', PARENTS_RUN: '', PREP_DAYS: '', REVERDICT_RUN: '', SPLIT: 'dev', DEPTH_PARAMS_RUN: '', GITHUB_OUTPUT: gh, RUNNER_TEMP: tmp, ...env }, ws);
    const log = fs.existsSync(path.join(tmp, 'plan.log')) ? fs.readFileSync(path.join(tmp, 'plan.log'), 'utf8') : '';
    return { ok: r.status === 0, out: Object.fromEntries(fs.readFileSync(gh, 'utf8').split('\n').filter(Boolean).map((l) => [l.slice(0, l.indexOf('=')), l.slice(l.indexOf('=') + 1)])), log, text: `${r.stdout}${r.stderr}` };
  };
  const g0 = plan({});
  assert.ok(g0.ok, g0.text); assert.deepEqual(g0.out, { gen: '0', per: '8', shard_count: '7', parents: '', shards: '[0,1,2,3,4,5,6]' });
  assert.match(g0.text, /\[twin\] sweep plan: generation 0, 7 shard\(s\) x 8 candidate\(s\) = 56 candidate\(s\) on the FIT days only\n/);
  const g3 = plan({ SWEEP_GEN: '03', CANDIDATES: '010', SHARDS: '3', PARENTS_RUN: '123456' });
  assert.ok(g3.ok, g3.text); assert.deepEqual(g3.out, { gen: '3', per: '10', shard_count: '3', parents: '123456', shards: '[0,1,2]' }, 'leading zeros are numbers, not octal');
  assert.match(g3.text, /generation 3, 3 shard\(s\) x 10 candidate\(s\) = 30 candidate\(s\) on the FIT days only, parents from run 123456/);
  assert.ok(plan({ CANDIDATES: '500', SHARDS: '1' }).ok); assert.ok(plan({ CANDIDATES: '1' }).ok);
  for (const [env, want] of [
    [{ PREP_DAYS: '2026-11-11' }, /sweep_gen is exclusive with prep_days and reverdict_run/], [{ REVERDICT_RUN: '5' }, /sweep_gen is exclusive with prep_days and reverdict_run/],
    [{ SPLIT: 'confirm' }, /a sweep reads the dev split's FIT days only: split=confirm is refused/], [{ SPLIT: 'custom' }, /split=custom is refused/], [{ SPLIT: 'x`y`z' }, /split=x\?y\?z is refused/],
    [{ DEPTH_PARAMS_RUN: '5' }, /depth_params_run belongs to a normal dev dispatch/],
    [{ SWEEP_GEN: 'abc' }, /sweep_gen must be a whole number from 0 to 99/], [{ SWEEP_GEN: '100' }, /sweep_gen must be a whole number from 0 to 99/], [{ SWEEP_GEN: '-1' }, /sweep_gen must be a whole number/], [{ SWEEP_GEN: '1.5', PARENTS_RUN: '3' }, /sweep_gen must be a whole number/],
    [{ CANDIDATES: '0' }, /sweep_candidates \(per shard\) must be a whole number from 1 to 500, got '0'/], [{ CANDIDATES: '501' }, /from 1 to 500, got '501'/], [{ CANDIDATES: '1000' }, /from 1 to 500/], [{ CANDIDATES: 'many' }, /from 1 to 500, got 'many'/], [{ CANDIDATES: '' }, /from 1 to 500/],
    [{ SHARDS: '0' }, /sweep_shards must be a whole number from 1 to 7/], [{ SHARDS: '8' }, /sweep_shards must be a whole number from 1 to 7 .* got '8'/], [{ SHARDS: '10' }, /from 1 to 7/], [{ SHARDS: 'all' }, /from 1 to 7/],
    [{ PARENTS_RUN: '99' }, /sweep_parents_run is for generation 1 and later/], [{ SWEEP_GEN: '1', PARENTS_RUN: '' }, /generation 1 needs sweep_parents_run/], [{ SWEEP_GEN: '2', PARENTS_RUN: 'run-9' }, /generation 2 needs sweep_parents_run/],
  ] as Array<[Record<string, string>, RegExp]>) {
    const r = plan(env); assert.equal(r.ok, false, JSON.stringify(env)); assert.match(r.log, new RegExp(`^\\[twin\\] ERROR: .*${want.source}`, 'm'), JSON.stringify(env)); assert.match(r.text, /::error::/); assert.deepEqual(r.out, {}, 'a refused plan sets no output');
  }
  // the refusal's comment: the plan's reason is the comment; nothing else ran
  const sent = path.join(tmp, 'sent.md'), bin = path.join(path.dirname(tmp), 'bin');
  plan({ SHARDS: '9' });
  const rep = bash(expr(stepScript(y, 'Report a refused sweep dispatch')), { PATH: `${bin}:${process.env.PATH}`, RUNNER_TEMP: tmp, GH_OUT: sent, GITHUB_SHA: '0123456789abcdef', GH_TOKEN: 't' }, ws);
  assert.equal(rep.status, 0, rep.stderr); assert.match(fs.readFileSync(sent, 'utf8'), /^History twin sweep plan, run 77 \(failure\), on commit 01234567: no sweep ran\n\n```\n\[twin\] ERROR: sweep_shards must be a whole number from 1 to 7[^\n]*\n```\n$/);
  assert.match(jobText(y, 'sweep-plan'), /permissions:\n      contents: write/);
});

test('the shard job\'s judge step passes the shard, the slice, the parents and what is left of the 340 minutes; its Drive step keeps shard files only, copy only', () => {
  const y = wf(), { ws, bin, tmp } = stageWs();
  fs.writeFileSync(path.join(bin, 'node'), '#!/usr/bin/env bash\nprintf \'%s\\n\' "$*" >> "$STUB_ARGS"\necho "[twin] stub sweep"\nexit "${STUB_RC:-0}"\n', { mode: 0o755 });
  const args = path.join(tmp, 'args.txt'), now = () => Math.floor(Date.now() / 1000);
  const judge = (env: Record<string, string>) => { fs.rmSync(args, { force: true }); fs.rmSync(path.join(tmp, 'build.log'), { force: true }); return bash(stepScript(y, 'Judge this shard'), { PATH: `${bin}:${process.env.PATH}`, FIT: SPLITS.dev.fit.join(','), GEN: '0', SHARD: '3', SHARDS: '7', PER: '10', JOB_START: String(now() - 20 * 60), RUNNER_TEMP: tmp, STUB_ARGS: args, ...env }, ws); };
  const g0 = judge({});
  assert.equal(g0.status, 0, g0.stderr);
  const a0 = fs.readFileSync(args, 'utf8').trim();
  assert.match(a0, /^--import tsx research\/historyTwin\.ts --stage sweep --split dev --fit-days 2026-11-11,2026-11-12,2026-11-15 --twin-requote data\/replay-src --real data\/twin-real15m --depth-model data\/models\/depth_model\.json --gen 0 --shard 3\/7 --candidates 10 --budget-min \d+ --out data\/sweep$/);
  const budget = Number(/--budget-min (\d+)/.exec(a0)![1]); assert.ok(budget >= 293 && budget <= 295, `a job 20 minutes old has about 295 minutes to start candidates in (${budget})`);
  assert.ok(!/--parents/.test(a0), 'generation 0 has no parents');
  assert.match(fs.readFileSync(path.join(tmp, 'build.log'), 'utf8'), /\[twin\] stub sweep/, 'the stage\'s lines go to the job log file');
  const g2 = judge({ GEN: '2', SHARD: '0', SHARDS: '1', PER: '500' });
  assert.match(fs.readFileSync(args, 'utf8'), /--gen 2 --shard 0\/1 --candidates 500 --parents data\/sweep-parents\/elite\.json --budget-min \d+ --out data\/sweep/);
  const late = judge({ JOB_START: String(now() - 320 * 60) });
  assert.notEqual(late.status, 0); assert.ok(!fs.existsSync(args), 'no time left: the stage is not started');
  assert.match(fs.readFileSync(path.join(tmp, 'build.log'), 'utf8'), /^\[twin\] ERROR: no time left for the sweep: the steps before it took 320 minutes of the 340$/m);
  assert.notEqual(judge({ STUB_RC: '3' }).status, 0, 'a failing stage fails the step (the shard file kept so far is uploaded by the step after it)');
  assert.equal(g2.status, 0);
  // the Drive step: copy only, always, and only the shard files
  const calls = path.join(tmp, 'calls.txt'), drive = tmpDir();
  const keep = (extra: Record<string, string> = {}) => { fs.rmSync(calls, { force: true }); return bash(expr(stepScript(y, 'Keep this shard\'s results on Drive')), { PATH: `${bin}:${process.env.PATH}`, STUB_CALLS: calls, STUB_DRIVE: drive, RUNNER_TEMP: tmp, ...extra }, ws); };
  assert.match(jobText(y, 'sweep'), /Keep this shard's results on Drive[^\n]*\n\s+if: \$\{\{ always\(\) \}\}/);
  const none = keep(); assert.equal(none.status, 0); assert.match(none.stdout, /no shard file to keep/); assert.ok(!fs.existsSync(calls), 'nothing to keep, nothing put');
  fs.mkdirSync(path.join(ws, 'data/sweep'), { recursive: true }); fs.writeFileSync(path.join(ws, 'data/sweep/sweep-g0-shard3of7.json'), '{}'); fs.writeFileSync(path.join(ws, 'data/sweep/sweep-g0-shard3of7.json.tmp'), 'x'); fs.writeFileSync(path.join(ws, 'data/sweep/other.json'), 'x');
  const some = keep(); assert.equal(some.status, 0, some.stderr);
  assert.equal(fs.readFileSync(calls, 'utf8').trim(), "put simulated/history-twin-sweep/77/shards data/sweep --include sweep-g*-shard*.json");
  assert.deepEqual(fs.readdirSync(path.join(drive, 'simulated/history-twin-sweep/77/shards')), ['sweep-g0-shard3of7.json'], 'only the shard file went up, never its .tmp');
});

test('sweep-collect: merges the shards from Drive, keeps best.json, elite.json and results.json, says the next dispatch; an incomplete generation is refused', async () => {
  const fx = await sweepFixture(), y = wf(), { ws, bin, tmp } = stageWs();
  const sent = path.join(tmp, 'sent.md'), drive = tmpDir(), runDir = path.join(drive, 'simulated/history-twin-sweep/55');
  const seed = (files: string[]) => { fs.rmSync(drive, { recursive: true, force: true }); if (files.length) fs.mkdirSync(path.join(runDir, 'shards'), { recursive: true }); for (const f of files) fs.copyFileSync(path.join(fx.shardsDir, f), path.join(runDir, 'shards', f)); };
  const run = (env: Record<string, string> = {}) => { fs.rmSync(sent, { force: true }); fs.rmSync(path.join(tmp, 'collect.log'), { force: true }); fs.rmSync(path.join(tmp, 'collected'), { recursive: true, force: true }); fs.rmSync(path.join(tmp, 'shards'), { recursive: true, force: true });
    return bash(expr(stepScript(y, 'Merge the shards, keep best.json'), { run: '55' }), { PATH: `${bin}:${process.env.PATH}`, RUNNER_TEMP: tmp, GH_OUT: sent, JOBS_JSON: '', STUB_DRIVE: drive, GEN: '0', SHARDS: '2', PER: '3', SWEEP_RESULT: 'success', PARTIAL: 'false', RUN: '55', REPO: 'o/r', REF: 'main', SHA: '0123456789abcdef', GH_TOKEN: 't', ...env }, ws); };
  const s0 = sweepShardName(0, 0, 2), s1 = sweepShardName(0, 1, 2);
  // a whole generation
  seed([s0, s1]);
  const ok = run();
  assert.equal(ok.status, 0, `${ok.stdout}${ok.stderr}`);
  assert.deepEqual(fs.readdirSync(runDir).sort(), ['best.json', 'elite.json', 'results.json', 'shards'], 'best, elite and results beside the shards');
  const log = fs.readFileSync(path.join(tmp, 'collect.log'), 'utf8');
  assert.match(log, /^\[twin\] sweep g0: 6 of 6 candidates judged by 2 shard\(s\); best loss 0\.5000 \(c0\), median /m);
  assert.equal([...log.matchAll(/^\[twin\] sweep top \d: c\d+ loss/gm)].length, 5);
  assert.match(log, /^\[twin\] kept on Drive: simulated\/history-twin-sweep\/55\/\{best,elite,results\}\.json \(shard jobs: success\)$/m);
  assert.match(log, /^\[twin\] NEXT GENERATION: gh workflow run history-twin\.yml -R o\/r --ref main -f sweep_gen=1 -f sweep_parents_run=55 -f sweep_candidates=3 -f sweep_shards=2$/m);
  assert.match(log, /^\[twin\] DEV VERDICT of this generation's best: gh workflow run history-twin\.yml -R o\/r --ref main -f split=dev -f depth_params_run=55$/m);
  // the same verdict on the fast route (H3 fix round 1: a model copies the printed command, so the hand-off must offer the 1 h path): depth_params_run is this SWEEP's id, the two reuse inputs are build run ids and optional
  assert.match(log, /^\[twin\] DEV VERDICT, fast \(RUNBOOK 3\.2\.1, about 1 h\): gh workflow run history-twin\.yml -R o\/r --ref main -f split=dev -f fast=true -f depth_params_run=55 \[-f real_features_run=BUILD_RUN -f depth_model_run=BUILD_RUN\]$/m);
  assert.equal([...log.matchAll(/^\[twin\] DEV VERDICT/gm)].length, 2, 'the plain line stays and one fast line follows it');
  const c = fs.readFileSync(sent, 'utf8');
  assert.match(c, /^History twin sweep, generation 0, run 55 \(shard jobs: success, collect: done\), on commit 01234567\n\n```\n\[twin\] sweep g0:/); assert.match(c, /```\n$/);
  assert.ok(!/KX[A-Z]|\$[0-9]/.test(c), 'the comment holds numbers and parameter names only');
  assert.match(c, /^\[twin\] DEV VERDICT, fast \(RUNBOOK 3\.2\.1, about 1 h\): .* -f fast=true -f depth_params_run=55 /m, 'the comment carries the fast verdict command too');
  // what it kept is what the fill-in reads
  assert.deepEqual(readJson(path.join(runDir, 'best.json')), readJson(path.join(fx.collected, 'best.json')));
  assert.doesNotThrow(() => loadDepthParamsFile(path.join(runDir, 'best.json')));
  // the exact best parameters survive into the comment whole (the comment cuts a line at 800 characters, and this line is about 450): paste-ready
  seed([s0, s1]); fs.writeFileSync(path.join(runDir, 'shards', s1), JSON.stringify({ ...readJson(path.join(fx.shardsDir, s1)), results: readJson(path.join(fx.shardsDir, s1)).results.map((r: { index: number }) => (r.index === 4 ? { ...r, loss: 0.1 } : r)) }));
  const long = run();
  assert.equal(long.status, 0, `${long.stdout}${long.stderr}`);
  const lc = fs.readFileSync(sent, 'utf8'), lm = /^\[twin\] sweep best params exact \(g0 c4, loss 0\.1000\): (\{.*\})$/m.exec(lc);
  assert.ok(lm && lm[0].length > 400, `the exact line is longer than the old 400-character cut (${lm?.[0].length})`);
  assert.deepEqual(JSON.parse(lm![1]), readJson(path.join(runDir, 'best.json')).params, 'the comment holds the very numbers best.json holds on Drive');
  assert.deepEqual(JSON.parse(lm![1]), generationCandidates(0, 6)[4]);
  // a missing shard: refused, nothing kept as best, the reason and the missing candidates in the comment
  seed([s0]);
  const miss = run({ SWEEP_RESULT: 'failure' });
  assert.notEqual(miss.status, 0);
  assert.deepEqual(fs.readdirSync(runDir).sort(), ['shards'], 'nothing is kept as best.json or elite.json');
  const mc = fs.readFileSync(sent, 'utf8');
  assert.match(mc, /^History twin sweep, generation 0, run 55 \(shard jobs: failure, collect: failed\)/); assert.match(mc, /\[twin\] ERROR: .*3 of 6 candidates are missing \(3, 4, 5\); no result file for shard 1: a red shard job/); assert.match(mc, /\[twin\] ERROR: the sweep was not collected \(shard jobs: failure\); nothing was kept as best\.json or elite\.json/);
  assert.ok(!/NEXT GENERATION/.test(mc), 'no next dispatch for a generation that is not whole');
  // the exact way out, with this run's id: a red shard job re-runs under the same run id; a finished run is never re-collected as partial
  assert.match(mc, /^\[twin\] RECOVER, a shard job that crashed or timed out \(red job\): gh run rerun 55 -R o\/r --failed \(same run id, same candidates; the collect job runs again after it\)$/m);
  assert.match(mc, /^\[twin\] RECOVER, a shard that stopped at its budget \(green job, incomplete; the lines above name it\): a re-run fails the same way\. Dispatch the generation again with fewer sweep_candidates \(now 3 per shard\), or with sweep_partial=true, which the dispatch that runs the shards must carry\.$/m);
  assert.match(mc, /^\[twin\] RECOVER, there is no way to re-collect a finished run as partial\.$/m);
  assert.ok(mc.split('\n').every((l) => l.length <= 400), 'no comment line is cut by the 400-character limit');
  // ... unless it is collected as partial (sweep_partial)
  const part = run({ SWEEP_RESULT: 'failure', PARTIAL: 'true' });
  assert.equal(part.status, 0, `${part.stdout}${part.stderr}`); assert.match(fs.readFileSync(sent, 'utf8'), /3 of 6 candidates judged by 1 shard\(s\) \(3 missing: partial\)/); assert.ok(fs.existsSync(path.join(runDir, 'best.json')));
  assert.ok(!/RECOVER/.test(fs.readFileSync(sent, 'utf8')), 'a partial collect that worked has nothing to recover');
  // a GREEN shard job that stopped at its budget leaves an incomplete file: the same refusal, naming the shard, even though no job is red
  seed([s0]); fs.writeFileSync(path.join(runDir, 'shards', s1), JSON.stringify({ ...readJson(path.join(fx.shardsDir, s1)), complete: false, results: readJson(path.join(fx.shardsDir, s1)).results.slice(0, 2) }));
  const green = run({ SWEEP_RESULT: 'success' });
  assert.notEqual(green.status, 0);
  const gc = fs.readFileSync(sent, 'utf8');
  assert.match(gc, /^History twin sweep, generation 0, run 55 \(shard jobs: success, collect: failed\)/);
  assert.match(gc, /\[twin\] ERROR: shard 1 is not complete \(2 of 3 candidates\): a red shard job/); assert.match(gc, /^\[twin\] RECOVER, a shard that stopped at its budget \(green job, incomplete; the lines above name it\)/m);
  assert.ok(!fs.existsSync(path.join(runDir, 'best.json')), 'nothing kept as best.json');
  const greenPart = run({ SWEEP_RESULT: 'success', PARTIAL: 'true' });
  assert.equal(greenPart.status, 0, `${greenPart.stdout}${greenPart.stderr}`); assert.match(fs.readFileSync(sent, 'utf8'), /^\[twin\] sweep g0: shard 1 incomplete: 2 of 3 candidates judged \(it stopped at its budget, or its job failed\)$/m);
  // no shard on Drive at all
  seed([]);
  const none = run({ SWEEP_RESULT: 'failure' });
  assert.notEqual(none.status, 0); assert.match(fs.readFileSync(sent, 'utf8'), /\[twin\] ERROR: no shard results on Drive for run 55: every shard failed before its first candidate/);
  // a shard file from a sweep that read a DEV day is not collected
  const tampered = tmpDir(); fs.mkdirSync(path.join(drive, 'simulated/history-twin-sweep/55/shards'), { recursive: true });
  for (const f of [s0, s1]) fs.writeFileSync(path.join(drive, 'simulated/history-twin-sweep/55/shards', f), JSON.stringify({ ...readJson(path.join(fx.shardsDir, f)), fitDays: [...FIT_DAYS, '2026-11-13'] }));
  const bad = run({ SWEEP_RESULT: 'success' });
  assert.notEqual(bad.status, 0); assert.match(fs.readFileSync(sent, 'utf8'), /\[twin\] ERROR: fit days and judged days overlap.*2026-11-13/); assert.ok(!fs.existsSync(path.join(drive, 'simulated/history-twin-sweep/55/best.json')));
  assert.ok(!/RECOVER/.test(fs.readFileSync(sent, 'utf8')), 'a refused fit day is not a lost shard: no advice to re-run');
  void tampered;
});

test('depth_params_run: dev and custom dispatches only, a run id, best.json read from Drive, handed to every depth fill-in', () => {
  const y = wf();
  // the split step
  assert.equal(splitStep({ SPLIT: 'dev', DEPTH_PARAMS_RUN: '55' }).ok, true); assert.equal(splitStep({ SPLIT: 'custom', FIT_IN: '2026-11-11', JUDGE_IN: '2026-11-13,2026-11-14', DEPTH_PARAMS_RUN: '55' }).ok, true);
  const conf = splitStep({ SPLIT: 'confirm', NOTE: 'a look', DEPTH_PARAMS_RUN: '55' });
  assert.equal(conf.ok, false); assert.match(conf.text, /depth_params_run is for dev and custom dispatches: split=confirm uses the code defaults, so promote the sweep's params to the defaults through a reviewed code change first/);
  assert.equal(splitStep({ SPLIT: 'confirm', NOTE: 'a look' }).ok, true, 'a confirm dispatch without it is the usual one');
  for (const bad of ['abc', '5;rm', '-1', '5 6']) { const r = splitStep({ SPLIT: 'dev', DEPTH_PARAMS_RUN: bad }); assert.equal(r.ok, false, bad); assert.match(r.text, /depth_params_run must be a run id \(digits only\)/); }
  // the Drive step
  const { ws, bin, tmp } = stageWs(), drive = tmpDir();
  const fetch = (run: string) => { fs.rmSync(path.join(ws, 'data/sweep'), { recursive: true, force: true }); fs.rmSync(path.join(tmp, 'build.log'), { force: true }); return bash(stepScript(y, 'The depth simulator parameters of a sweep'), { PATH: `${bin}:${process.env.PATH}`, RUN: run, RUNNER_TEMP: tmp, STUB_DRIVE: drive }, ws); };
  const bad = fetch('abc'); assert.notEqual(bad.status, 0); assert.match(fs.readFileSync(path.join(tmp, 'build.log'), 'utf8'), /^\[twin\] ERROR: depth_params_run must be a run id \(digits only\)$/m);
  const gone = fetch('55'); assert.notEqual(gone.status, 0); assert.match(fs.readFileSync(path.join(tmp, 'build.log'), 'utf8'), /^\[twin\] ERROR: depth_params_run 55: no sweep on Drive \(simulated\/history-twin-sweep\/55\)/m);
  fs.mkdirSync(path.join(drive, 'simulated/history-twin-sweep/55/shards'), { recursive: true });
  const nobest = fetch('55'); assert.notEqual(nobest.status, 0); assert.match(fs.readFileSync(path.join(tmp, 'build.log'), 'utf8'), /^\[twin\] ERROR: depth_params_run 55: no best\.json in simulated\/history-twin-sweep\/55 \(the sweep's collect job did not finish\)$/m);
  fs.writeFileSync(path.join(drive, 'simulated/history-twin-sweep/55/best.json'), '{"kind":"sweep-best"}');
  const ok = fetch('55'); assert.equal(ok.status, 0, ok.stderr); assert.ok(fs.existsSync(path.join(ws, 'data/sweep/best.json'))); assert.match(fs.readFileSync(path.join(tmp, 'build.log'), 'utf8'), /^\[twin\] depth params from sweep run 55 \(best\.json read from Drive\)$/m);
  assert.match(jobText(y, 'build'), /- name: The depth simulator parameters of a sweep \(depth_params_run\)\n\s+if: \$\{\{ inputs\.depth_params_run != '' \}\}/);
  // the match-and-fill step hands --depth-params to every depth fill-in (the judged days' and the lag arm's), and only when asked
  const wsn = stageWs(); fs.writeFileSync(path.join(wsn.bin, 'node'), '#!/usr/bin/env bash\nprintf \'%s\\n\' "$*" >> "$STUB_ARGS"\necho "[twin] stub"\n', { mode: 0o755 }); fs.writeFileSync(path.join(wsn.ws, 'data/twin/x'), 'x');
  const args = path.join(wsn.tmp, 'a.txt');
  const fill = (run: string) => { fs.rmSync(args, { force: true }); const r = bash(stepScript(y, 'Match, fill in, and describe'), { PATH: `${wsn.bin}:${process.env.PATH}`, SPLIT: 'dev', FIT: SPLITS.dev.fit.join(','), JUDGE: DEV_JUDGED.join(','), WARM: '2026-11-12', NEED: '2026-11-13', LAG: 'true', DEPTH_PARAMS_RUN: run, RUNNER_TEMP: wsn.tmp, STUB_ARGS: args }, wsn.ws); assert.equal(r.status, 0, `${r.stdout}${r.stderr}`); return fs.readFileSync(args, 'utf8').split('\n').filter((l) => /--stage fill/.test(l)); };
  const withRun = fill('55'), without = fill('');
  assert.equal(withRun.length, 2); assert.ok(withRun.every((l) => / --depth-model data\/models\/depth_model\.json --split-file data\/twin\/split\.json --depth-params data\/sweep\/best\.json$/.test(l)), withRun.join('\n'));
  assert.equal(without.length, 2); assert.ok(without.every((l) => !/--depth-params/.test(l)), 'no run, no flag');
  // the params are kept with the simulated twin on Drive (data/sweep is linked into it)
  assert.match(stepScript(y, 'Keep the simulated twin on Drive'), /\[ -d data\/sweep \] && ln -s "\$GITHUB_WORKSPACE\/data\/sweep" "\$S\/sweep"/);
});

// ---------------------------------------------------------------------------------------------------------------
// The fast dev run (H3: workflow input fast, real_features_run, depth_model_run; RUNBOOK 3.2.1). Synthetic days only
// (tests/twinSweepSynth.ts): the stage `fastrows` is run in its own process on the same days as the full route's three stages
// (match, fill, features) and the files and the [twin] lines are held equal, number for number.
// ---- H3 begin ----

const FAST_FIT = ['2026-11-11', '2026-11-12'], FAST_JUDGE = ['2026-11-13', '2026-11-14'];
const twinCli = (...a: string[]) => spawnSync(process.execPath, ['--import', 'tsx', 'research/historyTwin.ts', ...a], { encoding: 'utf8' });
const okCli = (...a: string[]): string => { const r = twinCli(...a); assert.equal(r.status, 0, `--stage ${a[1]}: ${r.stdout}${r.stderr}`); return r.stdout; };
const sha256Of = (f: string) => crypto.createHash('sha256').update(fs.readFileSync(f)).digest('hex');
const tw = (s: string) => s.split('\n').filter((l) => l.startsWith('[twin]'));

interface FastWorld { root: string; real: string; twin: string; modelFile: string }
/** The real days are depth fill-ins of a day of three assets (a contract the twin does not hold, another seed: the real side is not
 *  the twin), each with the meta file the prep leaves (its sha256); the requote days (the twin) hold BTC and ETH on the judged days. */
async function fastWorld(): Promise<FastWorld> {
  const root = tmpDir(), real = path.join(root, 'real15m'), twin = path.join(root, 'replay-src');
  for (const d of [real, twin]) fs.mkdirSync(d);
  const modelFile = path.join(root, 'depth_model.json');
  fs.writeFileSync(modelFile, JSON.stringify({ ...synthModel({ days: FAST_FIT }), schema: DEPTH_MODEL_SCHEMA }));
  const lib = readDepthModel(modelFile)!;
  for (const [i, d] of [...FAST_FIT, ...FAST_JUDGE].entries()) {
    const raw = path.join(root, `raw-${d}.jsonl.gz`), f = path.join(real, `md-${d}.jsonl.gz`);
    writeEventsGz(raw, synthRequoteDay({ day: d, assets: ['BTC', 'ETH', 'SOL'], windows: 4, seed: 40 + i }));
    await fillDayFile(raw, f, { how: 'depth' }, lib);
    fs.writeFileSync(path.join(real, `meta-${d}.json`), JSON.stringify({ day: d, version: real15mTag(), sha256: sha256Of(f) }));
    if (FAST_JUDGE.includes(d)) writeEventsGz(path.join(twin, `md-${d}.jsonl.gz`), synthRequoteDay({ day: d, assets: ['BTC', 'ETH'], windows: 4, seed: 3 + i }));
  }
  return { root, real, twin, modelFile };
}
const splitArgs = (out: string, fit = FAST_FIT, judge = FAST_JUDGE) => ['--stage', 'split', '--split', 'custom', '--fit-days', fit.join(','), '--judge-days', judge.join(','), '--warm-days', '', '--out', out];
/** The full route: split, match, fill, features (the workflow's step, with the same arguments). Returns the [twin] lines of match, fill and features. */
function fullRoute(w: FastWorld, out: string, paramsFile?: string): string[] {
  fs.mkdirSync(out, { recursive: true });
  const J = FAST_JUDGE.join(',');
  okCli(...splitArgs(out));
  return [
    ...tw(okCli('--stage', 'match', '--real', w.real, '--twin', w.twin, '--days', J, '--warm-days', '', '--out', out)),
    ...tw(okCli('--stage', 'fill', '--src', `${out}/requote`, '--dst', `${out}/depth`, '--how', 'depth', '--depth-model', w.modelFile, '--split-file', `${out}/split.json`, ...(paramsFile ? ['--depth-params', paramsFile] : []))),
    ...tw(okCli('--stage', 'features', '--dirs', `real=${out}/real,requote=${out}/requote,depth=${out}/depth`, '--days', J, '--extra-days', FAST_FIT.join(','), '--extra-dir', w.real, '--real15m', w.real, '--out', out)),
  ];
}
const fastArgs = (w: FastWorld, out: string, ...more: string[]) => ['--stage', 'fastrows', '--real', w.real, '--twin', w.twin, '--days', FAST_JUDGE.join(','), '--depth-model', w.modelFile, '--out', out, ...more];
function fastRoute(w: FastWorld, out: string, ...more: string[]): string[] {
  fs.mkdirSync(out, { recursive: true });
  okCli(...splitArgs(out));
  return tw(okCli(...fastArgs(w, out, ...more)));
}
const READ = ['features-real.json', 'features-requote.json', 'features-depth.json', 'paired.json', 'split.json', 'real-meta.json', 'real-activity.json'];
const FAST_ONLY = /^\[twin\] (fast: |depth fill-in: \d+ day\(s\) built in-stream)/;
/** The full route's own lines that say a file was written (the fast route writes no filled day), and the directory in a line. */
const FILL_WRITTEN = /^\[twin\] depth fill-in written for \d+ day\(s\)$/;
const sameLines = (full: string[], fast: string[], fullOut: string, fastOut: string) => {
  const norm = (l: string, out: string) => l.split(out).join('OUT');
  assert.deepEqual(fast.filter((l) => !FAST_ONLY.test(l)).map((l) => norm(l, fastOut)), full.filter((l) => !FILL_WRITTEN.test(l)).map((l) => norm(l, fullOut)));
};

const bestFileOf = (dir: string, params: Partial<DepthSimParams>) => {
  const f = path.join(dir, 'best.json');
  fs.writeFileSync(f, JSON.stringify({ kind: 'sweep-best', version: SWEEP_VERSION, split: 'dev', fitDays: FIT_DAYS, gen: 0, index: 2, loss: 0.9, params }));
  return f;
};

test('fastrows gives the full route\'s files and [twin] lines, number for number, with and without a sweep\'s --depth-params, and writes no filled day', async () => {
  const w = await fastWorld();
  const best = bestFileOf(w.root, generationCandidates(0, 6)[2]);
  const seen: Record<string, Row[]> = {};
  for (const [label, params] of [['defaults', undefined], ['a sweep best.json', best]] as Array<[string, string | undefined]>) {
    const full = path.join(w.root, `full-${label.length}`), fast = path.join(w.root, `fast-${label.length}`), more = params ? ['--depth-params', params] : [];
    const fullLines = fullRoute(w, full, params), fastLines = fastRoute(w, fast, ...more);
    for (const f of READ) assert.ok(fs.existsSync(path.join(fast, f)), `${label}: ${f} is written`);
    for (const f of READ) assert.equal(fs.readFileSync(path.join(fast, f), 'utf8'), fs.readFileSync(path.join(full, f), 'utf8'), `${label}: ${f} has the same bytes as the full route's`);
    assert.deepEqual(fs.readdirSync(path.join(fast, 'requote')), fs.readdirSync(path.join(full, 'requote')));
    for (const f of fs.readdirSync(path.join(full, 'requote'))) assert.equal(sha256Of(path.join(fast, 'requote', f)), sha256Of(path.join(full, 'requote', f)));
    assert.ok(!fs.existsSync(path.join(fast, 'depth')) && !fs.existsSync(path.join(fast, 'real')), `${label}: no filled day and no restricted real day is written`);
    sameLines(fullLines, fastLines, full, fast);
    // not vacuous: every source has lives on both judged days, the real side is not the twin, and the real side holds contracts the twin does not
    const rows = (f: string): Row[] => JSON.parse(fs.readFileSync(path.join(fast, f), 'utf8'));
    for (const s of ['real', 'requote', 'depth']) { const r = rows(`features-${s}.json`); assert.ok(r.length >= 12, `${label}: ${s} has ${r.length} lives`); for (const d of FAST_JUDGE) assert.ok(r.some((x) => x.day === d), `${s} ${d}`); }
    const paired = JSON.parse(fs.readFileSync(path.join(fast, 'paired.json'), 'utf8'));
    assert.ok(paired.length === 2 && paired.every((p: any) => p.both >= 8 && p.onlyReal15m >= 4), `${label}: paired ${JSON.stringify(paired.map((p: any) => [p.both, p.onlyReal15m]))}`);
    assert.notDeepEqual(rows('features-real.json').map((r) => r.f), rows('features-depth.json').map((r) => r.f));
    // the lines the verdict job and the report read: the match lines, the model and parameters, the simulator, features per source, the activity and follow lines
    for (const re of [/^\[twin\] 2026-11-13: /, /^\[twin\] depth model fitted on fit days only/, /^\[twin\] depth simulator parameters \(/, /\/depth simulator: /, /^\[twin\] features real: /, /^\[twin\] features depth: /, /^\[twin\] real 2026-11-12 \(not judged\): /, /^\[twin\] real follow /, /^\[twin\] depth 2026-11-14: /]) assert.ok(fastLines.some((l) => re.test(l)), `${label}: a line ${re}`);
    // the fast lines: a step each, in seconds
    const fl = fastLines.filter((l) => /^\[twin\] fast: /.test(l));
    assert.deepEqual(fl.map((l) => l.replace(/ \d+ s$/, '')), ['[twin] fast: real rows built', '[twin] fast: requote rows', '[twin] fast: depth rows']);
    assert.ok(fl.every((l) => / \d+ s$/.test(l)));
    seen[label] = rows('features-depth.json');
  }
  // the sweep's parameters are honoured by the in-stream route as by the file route (equal files above), and they move the rows
  assert.notDeepEqual(seen['a sweep best.json'], seen.defaults);
  // and a split that judges a day the sweep fitted on refuses them in the fast route too, as the fill stage does
  const bad = path.join(w.root, 'bad'); fs.mkdirSync(bad);
  okCli(...splitArgs(bad, FAST_FIT, ['2026-11-13', '2026-11-15']));
  const r = twinCli(...fastArgs(w, bad, '--depth-params', best).map((a) => (a === FAST_JUDGE.join(',') ? '2026-11-13,2026-11-15' : a)));
  assert.notEqual(r.status, 0); assert.match(r.stderr, /^\[twin\] ERROR: .*overlap.*2026-11-15/m);
});

// The feature code's version. FEATURE_CODE_VERSION is part of the key of a cached real side (real-meta.json): a real side built by other
// feature code is refused. This holds the version to the code: the normalised text (no comments, one space) of everything a real day's rows
// and paired mechanics go through, hashed, per version. An edit to that code that is not followed by a bump (and a new line here) fails.
const FEATURE_CODE_PINS: Record<string, string> = { f1: 'ff43690a4994481b' };
function featureCodeHash(): string {
  const src = fs.readFileSync(path.join(ROOT, 'research/historyTwin.ts'), 'utf8');
  const between = (a: string, b: string) => { const i = src.indexOf(a), j = src.indexOf(b, i + a.length); assert.ok(i >= 0 && j > i, `the feature code region ${a} .. ${b} is not found: rename it here too`); return src.slice(i, j); };
  const regions = [
    between('const MIN = 60_000, SLOT = 15_000;', 'const dayFile ='), between('async function* events(', 'async function writeGz('), between('async function tickersOf(', '// The split: FIT days'),
    between('export interface Paired {', '/** The per-day line the match stage prints'), between('export const FEATURES = [', 'async function resultsOf('),
    fs.readFileSync(path.join(ROOT, 'bot/marketdata/orderBook.ts'), 'utf8'),
  ];
  const norm = (t: string) => t.replace(/export const FEATURE_CODE_VERSION = '[^']*';/, '').replace(/\/\*[\s\S]*?\*\//g, ' ').replace(/\/\/[^\n]*/g, ' ').replace(/\s+/g, ' ').trim();
  return crypto.createHash('sha256').update(regions.map(norm).join('\n#\n')).digest('hex').slice(0, 16);
}
test('FEATURE_CODE_VERSION is tied to the feature code: an edit to rowBuilder, the paired mechanics or the order book must come with a bump', () => {
  assert.match(FEATURE_CODE_VERSION, /^[a-z0-9]+$/);
  const h = featureCodeHash();
  assert.equal(FEATURE_CODE_PINS[FEATURE_CODE_VERSION], h, `the feature code now hashes to ${h}, version ${FEATURE_CODE_VERSION} was pinned to ${FEATURE_CODE_PINS[FEATURE_CODE_VERSION]}: if the change alters a real day's rows or paired mechanics, bump FEATURE_CODE_VERSION in research/historyTwin.ts (every cached real side is then refused) and pin the new version here with this hash; if it does not, say so in the commit and pin the same version to the new hash`);
  assert.equal(new Set(Object.values(FEATURE_CODE_PINS)).size, Object.keys(FEATURE_CODE_PINS).length, 'two versions never share a hash');
});

test('restrictLine keeps what the restricted day keeps: a kept ticker, no ticker; drops the others, and thins a list of tickers', () => {
  const keep = new Set(['A', 'B']);
  assert.equal(restrictLine('{"t":1,"k":"book","ticker":"A"}', keep), '{"t":1,"k":"book","ticker":"A"}\n');
  assert.equal(restrictLine('{"t":1,"k":"book","ticker":"C"}', keep), undefined);
  assert.equal(restrictLine('{"t":1,"k":"index","asset":"BTC","value":5}', keep), '{"t":1,"k":"index","asset":"BTC","value":5}\n');
  assert.equal(restrictLine('{"t":1,"k":"alive","tickers":["A","C","B"]}', keep), '{"t":1,"k":"alive","tickers":["A","B"]}\n');
  assert.equal(restrictLine('{"t":1,"k":"alive","tickers":["C"]}', keep), undefined);
  assert.equal(restrictLine('{"t":1,"k":"alive","tickers":["A"', keep), undefined, 'a cut line that lists tickers is dropped');
});

const copyFiles = (from: string, to: string, names: string[]) => { fs.mkdirSync(to, { recursive: true }); for (const n of names) fs.copyFileSync(path.join(from, n), path.join(to, n)); };
const REAL_SIDE = ['features-real.json', 'paired.json', 'real-meta.json', 'real-activity.json'];
const metaFilesOnly = (w: FastWorld, name: string) => { const d = path.join(w.root, name); fs.mkdirSync(d); copyFiles(w.real, d, fs.readdirSync(w.real).filter((f) => f.startsWith('meta-'))); return d; };
const readJ = (f: string) => JSON.parse(fs.readFileSync(f, 'utf8'));
/** fastRows in this process: the lines it prints, and the files it writes in `out` (its split.json made by the split stage). */
async function fastHere(w: FastWorld, out: string, realCache: string | undefined, o: { realDir?: string; twinDir?: string } = {}): Promise<string[]> {
  const lines: string[] = [];
  await fastRows({ out, realDir: o.realDir ?? w.real, twinDir: o.twinDir ?? w.twin, days: FAST_JUDGE, modelFile: w.modelFile, realCache, realRun: realCache ? '4242' : undefined, log: (l) => lines.push(l) });
  return lines;
}

test('real_features_run: a real side kept by an earlier run is reused with the real days gone, gives the fresh build\'s files and lines, and chains', async () => {
  const w = await fastWorld(), full = path.join(w.root, 'full'), fullLines = fullRoute(w, full);
  // what "Keep the judged features" leaves of a run: made by the FULL route's features stage (--real15m), read by the fast route
  const cache = path.join(w.root, 'cache'); copyFiles(full, cache, REAL_SIDE);
  const meta = readJ(path.join(cache, 'real-meta.json')) as RealMetaT;
  assert.deepEqual([meta.judged, meta.fit, meta.real15m, meta.featureCode], [FAST_JUDGE, FAST_FIT, real15mTag(), FEATURE_CODE_VERSION]);
  assert.ok(FAST_JUDGE.every((d) => meta.days[d].real === sha256Of(path.join(w.real, `md-${d}.jsonl.gz`)) && meta.days[d].twin === sha256Of(path.join(w.twin, `md-${d}.jsonl.gz`))) && FAST_FIT.every((d) => meta.days[d].real.length === 64));
  const act = readJ(path.join(cache, 'real-activity.json'));
  assert.ok(act.days.some((d: any) => d.label === '2026-11-12 (not judged)') && act.days.some((d: any) => d.label === '2026-11-13') && act.follow.length > 0, 'the activity of the judged days and the fit days, and the follow diagnostics');
  const out = path.join(w.root, 'reuse'); fs.mkdirSync(out); okCli(...splitArgs(out));
  const lines = await fastHere(w, out, cache, { realDir: metaFilesOnly(w, 'real-meta-only') }); // the real recordings are not there: nothing reads them
  for (const f of ['features-real.json', 'features-requote.json', 'features-depth.json', 'paired.json', 'split.json', 'real-activity.json']) assert.equal(fs.readFileSync(path.join(out, f), 'utf8'), fs.readFileSync(path.join(full, f), 'utf8'), `${f} equals the full route's, bytes`);
  const kept = readJ(path.join(out, 'real-meta.json')); assert.equal(kept.reusedFrom, '4242'); delete kept.reusedFrom; assert.deepEqual(kept, meta);
  sameLines(fullLines, lines, full, out);
  assert.deepEqual(lines.filter((l) => /^\[twin\] fast: /.test(l)).map((l) => l.replace(/ \d+ s$/, '')), ['[twin] fast: real rows reused', '[twin] fast: requote rows', '[twin] fast: depth rows']);
  // the reused side can itself be reused (the sidecars of a reusing run are the files of the next one)
  const cache2 = path.join(w.root, 'cache2'); copyFiles(out, cache2, REAL_SIDE);
  const out2 = path.join(w.root, 'reuse2'); fs.mkdirSync(out2); okCli(...splitArgs(out2));
  await fastHere(w, out2, cache2, { realDir: metaFilesOnly(w, 'real-meta-only2') });
  assert.equal(fs.readFileSync(path.join(out2, 'features-real.json'), 'utf8'), fs.readFileSync(path.join(full, 'features-real.json'), 'utf8'));
  // the stage, in its own process: the same files, and the log says reused
  const cli = path.join(w.root, 'reuse-cli'); fs.mkdirSync(cli); okCli(...splitArgs(cli));
  const r = tw(okCli(...fastArgs({ ...w, real: metaFilesOnly(w, 'real-meta-only3') }, cli, '--real-cache', cache, '--real-run', '4242')));
  assert.ok(r.some((l) => /^\[twin\] fast: real rows reused \d+ s$/.test(l)));
  assert.equal(fs.readFileSync(path.join(cli, 'features-depth.json'), 'utf8'), fs.readFileSync(path.join(full, 'features-depth.json'), 'utf8'));
});

type RealMetaT = { version: number; judged: string[]; fit: string[]; real15m: string; featureCode: string; days: Record<string, { real: string; twin?: string }>; reusedFrom?: string };

test('real_features_run is refused, with what differs, unless it was built for exactly these judged days, fit days, real days tag, feature code, prepped real days and requote days', async () => {
  const w = await fastWorld(), full = path.join(w.root, 'full'); fullRoute(w, full);
  const cache = path.join(w.root, 'cache'); copyFiles(full, cache, REAL_SIDE);
  const meta = readJ(path.join(cache, 'real-meta.json')) as RealMetaT;
  const out = path.join(w.root, 'out'); fs.mkdirSync(out); okCli(...splitArgs(out));
  const withMeta = (name: string, edit: (m: RealMetaT) => void) => { const d = path.join(w.root, name); copyFiles(cache, d, REAL_SIDE); const m = structuredClone(meta); edit(m); fs.writeFileSync(path.join(d, 'real-meta.json'), JSON.stringify(m)); return d; };
  const refused = async (cacheDir: string, re: RegExp, o: { realDir?: string; twinDir?: string } = {}) => {
    await assert.rejects(fastHere(w, out, cacheDir, { realDir: metaFilesOnly(w, `bare-${fs.readdirSync(w.root).length}`), ...o }), (e: Error) => { assert.match(e.message, re); return true; });
  };
  const head = (had: string, now: string, what: string) => new RegExp(`^real_features_run 4242 was built for ${had}, not these \\(${now}\\): it differs in ${what}\\. Leave real_features_run empty to parse the real days again$`);
  // each aspect of the key, one at a time
  await refused(withMeta('judged', (m) => { m.judged = ['2026-11-13']; }), head('judged days 2026-11-13', 'judged days 2026-11-13,2026-11-14', 'judged days'));
  await refused(withMeta('fit', (m) => { m.fit = ['2026-11-11']; }), head('fit days 2026-11-11', 'fit days 2026-11-11,2026-11-12', 'fit days'));
  await refused(withMeta('tag', (m) => { m.real15m = 'r15m-0|exclude=DOGE'; }), head('real days tag r15m-0\\|exclude=DOGE', `real days tag ${real15mTag().replace('|', '\\|')}`, 'real days tag'));
  await refused(withMeta('code', (m) => { m.featureCode = 'f0'; }), head('feature code f0', `feature code ${FEATURE_CODE_VERSION}`, 'feature code'));
  await refused(withMeta('format', (m) => { m.version = 99; }), head('real-meta\\.json format 99', 'format 1', 'sidecar format'));
  // the days themselves: a prepped real day made again (its meta's sha256 is another), a requote day made again, a sha that was never recorded
  const other = path.join(w.root, 'real-other'); fs.mkdirSync(other); copyFiles(w.real, other, fs.readdirSync(w.real).filter((f) => f.startsWith('meta-')));
  fs.writeFileSync(path.join(other, 'meta-2026-11-14.json'), JSON.stringify({ ...readJ(path.join(w.real, 'meta-2026-11-14.json')), sha256: 'a'.repeat(64) }));
  await refused(cache, /^real_features_run 4242 was built for prepped real day\(s\) 2026-11-14 as they were then, not these \(those days as they are now \(sha256 differs or is not recorded\)\): it differs in prepped real days\./, { realDir: other });
  const twinOther = path.join(w.root, 'twin-other'); fs.mkdirSync(twinOther);
  writeEventsGz(path.join(twinOther, 'md-2026-11-13.jsonl.gz'), synthRequoteDay({ day: '2026-11-13', assets: ['BTC', 'ETH'], windows: 4, seed: 99 }));
  fs.copyFileSync(path.join(w.twin, 'md-2026-11-14.jsonl.gz'), path.join(twinOther, 'md-2026-11-14.jsonl.gz'));
  await refused(cache, /^real_features_run 4242 was built for requote day\(s\) 2026-11-13 as they were then, not these .*: it differs in requote days\./, { twinDir: twinOther });
  await refused(withMeta('nosha', (m) => { m.days = {}; }), /it differs in prepped real days \/ requote days\./);
  await refused(withMeta('nosha2', (m) => { for (const d of Object.keys(m.days)) m.days[d].real = ''; }), /it differs in prepped real days\./);
  // several at once are all named
  await refused(withMeta('many', (m) => { m.featureCode = 'f0'; m.judged = ['2026-11-14']; }), /^real_features_run 4242 was built for judged days 2026-11-14; feature code f0, not these \(judged days 2026-11-13,2026-11-14; feature code f1\): it differs in judged days \/ feature code\./);
  // an old run (no sidecar), a copy that is not complete, and damaged copies are refused, not guessed
  const old = path.join(w.root, 'old'); copyFiles(cache, old, ['features-real.json', 'paired.json']);
  await refused(old, /^real_features_run 4242 has no real-meta\.json, real-activity\.json: it was made before the fast route kept its real side \(or it read the confirm days\), and an old run is never guessed at\. Dispatch a dev run with this code/);
  const nofeat = path.join(w.root, 'nofeat'); copyFiles(cache, nofeat, ['real-meta.json', 'real-activity.json', 'paired.json']);
  await refused(nofeat, /^real_features_run 4242 has no features-real\.json: its judged features are not complete on Drive/);
  const junk = path.join(w.root, 'junk'); copyFiles(cache, junk, REAL_SIDE); fs.writeFileSync(path.join(junk, 'real-activity.json'), '{not json');
  await refused(junk, /^real_features_run 4242: real-activity\.json is not readable JSON/);
  const shape = path.join(w.root, 'shape'); copyFiles(cache, shape, REAL_SIDE); fs.writeFileSync(path.join(shape, 'real-meta.json'), JSON.stringify({ version: 1 }));
  await refused(shape, /^real_features_run 4242: real-meta\.json or real-activity\.json is not what this code writes/);
  const stray = path.join(w.root, 'stray'); copyFiles(cache, stray, REAL_SIDE); fs.writeFileSync(path.join(stray, 'features-real.json'), JSON.stringify([...readJ(path.join(cache, 'features-real.json')), { day: '2026-11-12', ticker: 'X', src: 'real', f: [] }]));
  await refused(stray, /^real_features_run 4242: features-real\.json holds rows of day\(s\) that are not judged here: 2026-11-12/);
  const nopair = path.join(w.root, 'nopair'); copyFiles(cache, nopair, REAL_SIDE); fs.writeFileSync(path.join(nopair, 'paired.json'), JSON.stringify(readJ(path.join(cache, 'paired.json')).slice(1)));
  await refused(nopair, /^real_features_run 4242: paired\.json has no entry for 2026-11-13/);
  // refused before anything of the real side is written: the out folder holds no features-real.json of a refused run
  assert.ok(!fs.existsSync(path.join(out, 'features-real.json')), 'a refused cache leaves no real rows behind');
  // the stage: one [twin] ERROR line, a failed exit
  const stale = withMeta('stale-cli', (m) => { m.featureCode = 'f0'; });
  const r = twinCli(...fastArgs({ ...w, real: metaFilesOnly(w, 'bare-cli') }, out, '--real-cache', stale, '--real-run', '4242'));
  assert.notEqual(r.status, 0); assert.match(r.stderr, new RegExp(`^\\[twin\\] ERROR: real_features_run 4242 was built for feature code f0, not these \\(feature code ${FEATURE_CODE_VERSION}\\)`, 'm'));
  // realMetaDiff on its own: equal keys differ in nothing; a reusedFrom note is not part of the key
  assert.deepEqual(realMetaDiff(meta, { ...structuredClone(meta), reusedFrom: '9' } as never), []);
  assert.throws(() => loadRealSide(cache, { ...meta, judged: [] } as never, '7'), /real_features_run 7 was built for judged days 2026-11-13,2026-11-14, not these \(judged days \)/);
});

test('fast is for dev and custom splits only: a split that reads a confirm day, a day list that is not the split\'s judged days, and a missing split are refused', async () => {
  const w = await fastWorld(), out = path.join(w.root, 'out'); fs.mkdirSync(out);
  const run = (days: string[]) => fastRows({ out, realDir: w.real, twinDir: w.twin, days, modelFile: w.modelFile, log: () => {} });
  await assert.rejects(run(FAST_JUDGE), /no split in .*split\.json: --stage split first/);
  fs.writeFileSync(path.join(out, 'split.json'), JSON.stringify({ name: 'confirm', fit: [...SPLITS.confirm.fit], judge: [...SPLITS.confirm.judge], warm: [] }));
  await assert.rejects(run([...SPLITS.confirm.judge]), /fast=true is for dev and custom splits only: a run that reads a confirm day stays on the audited full path/);
  fs.writeFileSync(path.join(out, 'split.json'), JSON.stringify({ name: 'custom', fit: FAST_FIT, judge: ['2026-11-13', '2026-11-18'], warm: [] }));
  await assert.rejects(run(['2026-11-13', '2026-11-18']), /the confirm days \(2026-11-18\) are read only through split=confirm with a confirm_look_note/, 'a custom split that names a confirm day is the held-out rule\'s refusal');
  fs.writeFileSync(path.join(out, 'split.json'), JSON.stringify({ name: 'custom', fit: FAST_FIT, judge: FAST_JUDGE, warm: [] }));
  await assert.rejects(run(['2026-11-13', '2026-11-18']), /confirm day/i);
  await assert.rejects(run(['2026-11-13']), /the fast rows are for the split's judged days \(2026-11-13,2026-11-14\), got 2026-11-13/);
  // a fit day that overlaps a judged day, and a judged day with no recording
  fs.writeFileSync(path.join(out, 'split.json'), JSON.stringify({ name: 'custom', fit: [...FAST_FIT, '2026-11-13'], judge: FAST_JUDGE, warm: [] }));
  await assert.rejects(run(FAST_JUDGE), /overlap.*2026-11-13/);
  fs.writeFileSync(path.join(out, 'split.json'), JSON.stringify({ name: 'custom', fit: FAST_FIT, judge: FAST_JUDGE, warm: [] }));
  const gone = path.join(w.root, 'twin-one'); fs.mkdirSync(gone); fs.copyFileSync(path.join(w.twin, 'md-2026-11-13.jsonl.gz'), path.join(gone, 'md-2026-11-13.jsonl.gz'));
  await assert.rejects(fastRows({ out, realDir: w.real, twinDir: gone, days: FAST_JUDGE, modelFile: w.modelFile, log: () => {} }), /judged day\(s\) without a real recording or a twin: 2026-11-14/);
  // a model fitted on a judged day is refused as the fill stage refuses it (the fit-days assert is the one the fast route runs first)
  const leaky = path.join(w.root, 'leaky.json'); fs.writeFileSync(leaky, JSON.stringify(synthModel({ days: [...FAST_FIT, '2026-11-14'] })));
  await assert.rejects(fastRows({ out, realDir: w.real, twinDir: w.twin, days: FAST_JUDGE, modelFile: leaky, log: () => {} }), /overlap.*2026-11-14/);
  // a fit day with no cached real recording stops the build when its activity line is asked for (the full route skips it silently; the fast one says so)
  const noFit = path.join(w.root, 'real-nofit'); fs.mkdirSync(noFit); copyFiles(w.real, noFit, fs.readdirSync(w.real).filter((f) => !f.includes('2026-11-12')));
  await assert.rejects(fastRows({ out, realDir: noFit, twinDir: w.twin, days: FAST_JUDGE, modelFile: w.modelFile, log: () => {} }), /the fast run needs the cached real FIT day 2026-11-12 in .*dispatch prep_days=2026-11-12 first/);
});

test('depth_model_run: a model an earlier run fitted is reused only when it records exactly these fit days, the current study version and, if known, these real days\' tag', () => {
  const dir = tmpDir(), split = { fit: FAST_FIT, judge: FAST_JUDGE };
  const thr = (fn: () => unknown, re: RegExp) => assert.throws(fn, (e: Error) => { assert.match(e.message, re); return true; });
  const put = (name: string, o: Record<string, unknown>) => { const f = path.join(dir, `${name}.json`); fs.writeFileSync(f, JSON.stringify({ ...synthModel({ days: FAST_FIT }), schema: DEPTH_MODEL_SCHEMA, ...o })); return f; };
  const meta = path.join(dir, 'real-meta.json'); fs.writeFileSync(meta, JSON.stringify({ real15m: real15mTag() }));
  const line = (f: string, m?: string) => checkDepthModelReuse(f, split, { run: '321', metaFile: m });
  assert.equal(line(put('ok', {}), meta), `[twin] depth model reused from run 321: fitted on 2026-11-11 2026-11-12 (exactly the fit days), schema ${DEPTH_MODEL_SCHEMA}; real days tag ${real15mTag()}`);
  assert.match(line(put('ok2', {})), /schema \d+; no real-meta\.json beside it, so the real days' tag it was fitted from is not recorded$/);
  fs.writeFileSync(path.join(dir, 'junk-meta.json'), '{no'); assert.match(line(put('ok3', {}), path.join(dir, 'junk-meta.json')), /not recorded$/, 'an unreadable meta is "not recorded", not a refusal');
  assert.match(line(put('order', { days: [...FAST_FIT].reverse() }), meta), /^\[twin\] depth model reused from run 321: fitted on 2026-11-11 2026-11-12 \(exactly/, 'the order of the days does not matter');
  // the study's version: no schema reads as 0, another number, a number written as text
  const noSchema = path.join(dir, 'noschema.json'); fs.writeFileSync(noSchema, JSON.stringify(synthModel({ days: FAST_FIT })));
  thr(() => line(noSchema, meta), new RegExp(`^depth_model_run 321: the model has schema 0 \\(none recorded\\), this code reads schema ${DEPTH_MODEL_SCHEMA}: the depth study or the simulator changed since it was fitted, so it is not reused\\. Leave depth_model_run empty to fit it again$`));
  thr(() => line(put('next', { schema: DEPTH_MODEL_SCHEMA + 1 }), meta), new RegExp(`the model has schema ${DEPTH_MODEL_SCHEMA + 1}, this code reads schema ${DEPTH_MODEL_SCHEMA}`));
  thr(() => line(put('text', { schema: String(DEPTH_MODEL_SCHEMA) }), meta), /the model has schema 0/);
  // the days: fewer (a subset), more (a day outside the fit days), a judged day, none recorded
  thr(() => line(put('subset', { days: ['2026-11-11'] }), meta), /^depth_model_run 321: the model was fitted on 2026-11-11, not exactly the fit days 2026-11-11, 2026-11-12\./);
  thr(() => line(put('extra', { days: [...FAST_FIT, '2026-11-15'] }), meta), /^depth_model_run 321: the depth model was fitted on days outside the fit set: 2026-11-15/);
  thr(() => line(put('judged', { days: [...FAST_FIT, '2026-11-13'] }), meta), /^depth_model_run 321: .*overlap.*2026-11-13/);
  thr(() => line(put('nodays', { days: [] }), meta), /does not record the days it was fitted on/);
  // the real days' tag it was fitted from, and an unreadable model
  fs.writeFileSync(path.join(dir, 'old-meta.json'), JSON.stringify({ real15m: 'r15m-0|exclude=DOGE' }));
  thr(() => line(put('tag', {}), path.join(dir, 'old-meta.json')), new RegExp(`^depth_model_run 321: the model was fitted from real days tagged r15m-0\\|exclude=DOGE, these are tagged ${real15mTag().replace('|', '\\|')}`));
  fs.writeFileSync(path.join(dir, 'bad.json'), 'not json'); thr(() => line(path.join(dir, 'bad.json'), meta), /^depth_model_run 321: .*bad\.json is not readable JSON/);
  // the stage the workflow runs
  const sp = path.join(dir, 'split.json'); fs.writeFileSync(sp, JSON.stringify({ name: 'custom', fit: FAST_FIT, judge: FAST_JUDGE, warm: [] }));
  const ok = twinCli('--stage', 'depth-model-check', '--depth-model', put('cli', {}), '--split-file', sp, '--run', '321', '--model-meta', meta);
  assert.equal(ok.status, 0, ok.stderr); assert.match(ok.stdout, /^\[twin\] depth model reused from run 321: fitted on 2026-11-11 2026-11-12 \(exactly the fit days\)/);
  const bad = twinCli('--stage', 'depth-model-check', '--depth-model', noSchema, '--split-file', sp, '--run', '321');
  assert.notEqual(bad.status, 0); assert.match(bad.stderr, /^\[twin\] ERROR: depth_model_run 321: the model has schema 0 \(none recorded\)/m);
  fs.writeFileSync(sp, JSON.stringify({ name: 'confirm', fit: [...SPLITS.confirm.fit], judge: [...SPLITS.confirm.judge], warm: [] }));
  assert.equal(twinCli('--stage', 'depth-model-check', '--depth-model', put('cli2', { days: [...SPLITS.confirm.fit] }), '--split-file', sp, '--run', '321').status, 0, 'a confirm split\'s own check is the same one (the workflow refuses fast on confirm before it gets here)');
});

// The workflow side of the fast run: the split step's refusals, which step runs when, and the new steps run with a stubbed Drive and node.

test('the split step: fast is for dev and custom only, never with the backtests or the lag arms, and the two reuse inputs are fast only and run ids', () => {
  const custom = { SPLIT: 'custom', FIT_IN: '2026-11-11,2026-11-12', JUDGE_IN: '2026-11-13,2026-11-14' };
  const refused = (env: Record<string, string>, re: RegExp) => { const r = splitStep(env); assert.equal(r.ok, false, JSON.stringify(env)); assert.match(r.text, re); };
  // accepted: dev and custom, each with and without the reuse inputs; the output the later steps read says fast
  for (const base of [{ SPLIT: 'dev' }, custom]) {
    const plain = splitStep({ ...base, FAST: 'true' });
    assert.equal(plain.ok, true, plain.text); assert.equal(plain.out.fast, 'true'); assert.match(plain.text, /^\[twin\] fast run: no filled day is written; real rows built from the real days, depth model fitted here$/m);
    const both = splitStep({ ...base, FAST: 'true', REAL_FEATURES_RUN: '12', DEPTH_MODEL_RUN: '34', DEPTH_PARAMS_RUN: '56' });
    assert.equal(both.ok, true, both.text); assert.match(both.text, /^\[twin\] fast run: no filled day is written; real rows reused from run 12, depth model reused from run 34$/m);
    const one = splitStep({ ...base, FAST: 'true', DEPTH_MODEL_RUN: '34' }); assert.match(one.text, /real rows built from the real days, depth model reused from run 34$/m);
    assert.equal(splitStep({ ...base, FAST: 'false' }).out.fast, 'false'); assert.equal(splitStep(base).out.fast, 'false', 'a push (no inputs): not fast');
    assert.ok(!/fast run/.test(splitStep(base).text), 'the full route says nothing of the fast one');
  }
  // refused
  refused({ SPLIT: 'confirm', NOTE: 'a look', FAST: 'true' }, /::error::fast=true is for split dev or custom only: the confirm split stays on the audited full path \(leave fast off for split=confirm\)/);
  refused({ SPLIT: 'dev', FAST: 'true', BACKTESTS: 'true', MODEL_DRIVE: 'm1' }, /::error::fast=true cannot run the backtest legs \(it writes no filled day for them to read\)/);
  refused({ SPLIT: 'dev', FAST: 'true', LAG_ARMS: 'true' }, /::error::fast=true does not build the lag arms/);
  refused({ SPLIT: 'dev', REAL_FEATURES_RUN: '12' }, /::error::real_features_run and depth_model_run are for fast=true runs only: set fast=true, or leave them empty/);
  refused({ SPLIT: 'dev', DEPTH_MODEL_RUN: '12' }, /::error::real_features_run and depth_model_run are for fast=true runs only/);
  refused({ SPLIT: 'confirm', NOTE: 'a look', DEPTH_MODEL_RUN: '12' }, /for fast=true runs only/);
  for (const bad of ['abc', '5;rm', '-1', '5 6', '../x', '1e3']) {
    refused({ SPLIT: 'dev', FAST: 'true', REAL_FEATURES_RUN: bad }, /::error::real_features_run must be a run id \(digits only\)/);
    refused({ SPLIT: 'dev', FAST: 'true', DEPTH_MODEL_RUN: bad }, /::error::depth_model_run must be a run id \(digits only\)/);
  }
  // the full route's own refusals are untouched
  assert.equal(splitStep({ SPLIT: 'confirm', NOTE: 'a look' }).ok, true); assert.equal(splitStep({ SPLIT: 'dev', BACKTESTS: 'true', MODEL_DRIVE: 'm1', LAG_ARMS: 'true' }).ok, true, 'backtests and lag arms stay available on the full route');
});

test('the workflow wires the fast run: inputs, which step runs for each input, one heavy group, at most 7 wide, and the verdict job is unchanged but for a timing line', { skip: hasYaml ? false : 'python3 with PyYAML is not installed here' }, () => {
  const r = spawnSync('python3', ['-I', '-c', 'import yaml,json,sys; print(json.dumps(yaml.safe_load(open(sys.argv[1]))))', path.join(ROOT, '.github/workflows/history-twin.yml')], { encoding: 'utf8' });
  assert.equal(r.status, 0, r.stderr);
  const d = JSON.parse(r.stdout), on = d.true ?? d.on, jobs = d.jobs as Record<string, any>, ins = on.workflow_dispatch.inputs;
  assert.equal(ins.fast.type, 'boolean'); assert.equal(ins.fast.default, false);
  for (const k of ['real_features_run', 'depth_model_run']) { assert.equal(ins[k].default, ''); assert.equal(ins[k].required, false); assert.match(ins[k].description, /^fast only/); }
  assert.ok(Object.keys(ins).length <= 25, `${Object.keys(ins).length} inputs (GitHub allows 25)`);
  assert.match(d.concurrency.group, /'heavy'/); assert.equal(d.concurrency['cancel-in-progress'], false);
  for (const [n, j] of Object.entries(jobs) as Array<[string, any]>) if (j.strategy) assert.ok(j.strategy['max-parallel'] <= 7, `${n} runs at most 7 at once`);
  assert.equal(jobs.build.outputs.fast, '${{ steps.split.outputs.fast }}');
  const steps = jobs.build.steps as Array<{ name?: string; if?: string; env?: Record<string, string>; id?: string }>;
  const named = (re: RegExp) => { const m = steps.filter((x) => re.test(x.name ?? '')); assert.equal(m.length, 1, `one step ${re}: ${m.length}`); return m[0]; };
  assert.equal(new Set(steps.map((x) => x.name ?? '').filter(Boolean)).size, steps.filter((x) => x.name).length, 'step names are unique in the build job');
  const fit = named(/^The depth model, fitted/), reuse = named(/^The depth model, reused/), realSide = named(/^The real side of an earlier run/), match = named(/^Match, fill in/), fastRowsStep = named(/^Fast rows/), keep = named(/^Keep the judged features/);
  // every expression is `a OP 'x' [&&|| ...]` over the split step's fast output and the inputs: evaluate it for every dispatch
  const evalIf = (e: string | undefined, fastOut: string, v: Record<string, string>): boolean => {
    if (e === undefined) return true;
    const m = /^\$\{\{ (.*) \}\}$/.exec(e); assert.ok(m, `an if of the ${'${{ }}'} form: ${e}`);
    const js = m![1].replace(/steps\.split\.outputs\.fast/g, JSON.stringify(fastOut)).replace(/inputs\.([a-z_]+)/g, (_, k) => { assert.ok(k in ins, `input ${k} exists`); return JSON.stringify(v[k] ?? ''); });
    assert.ok(/^[\s"'!=&|a-z0-9_.-]+$/i.test(js), `only comparisons: ${js}`);
    return new Function(`return (${js});`)() as boolean;
  };
  for (const fast of ['true', 'false']) for (const model of ['', '55']) for (const real of ['', '66']) {
    if (fast !== 'true' && (model || real)) continue; // the split step refuses these
    const v = { depth_model_run: model, real_features_run: real }, on_ = (s: { if?: string }) => evalIf(s.if, fast, v);
    assert.equal(on_(fit) !== on_(reuse), true, `fast ${fast}, model run '${model}': exactly one of the fit and the reuse runs`);
    assert.equal(on_(reuse), fast === 'true' && model !== ''); assert.equal(on_(fit), !(fast === 'true' && model !== ''));
    assert.equal(on_(realSide), fast === 'true' && real !== '', `the real side is read from Drive only for fast with real_features_run (${fast}, '${real}')`);
    assert.equal(on_(match) !== on_(fastRowsStep), true, 'the full route or the fast rows, never both and never neither'); assert.equal(on_(fastRowsStep), fast === 'true');
    assert.equal(on_(keep), true, 'the judged files are kept either way');
  }
  // a push has no inputs at all: the empty string, and the full route
  assert.equal(evalIf(match.if, 'false', {}), true); assert.equal(evalIf(fit.if, 'false', {}), true); assert.equal(evalIf(reuse.if, 'false', {}), false);
  // the order: the model and the real side before the rows, the rows after the match step's place, the keep step after both routes
  const at = (x: object) => steps.indexOf(x as never);
  assert.ok(at(fit) < at(reuse) && at(reuse) < at(fastRowsStep) && at(realSide) < at(fastRowsStep) && at(match) < at(fastRowsStep) && at(fastRowsStep) < at(keep));
  // the same job set, as before
  assert.deepEqual(Object.keys(jobs), ['prep-plan', 'prep', 'prep-report', 'build', 'backtest', 'verdict', 'reverdict', 'sweep-plan', 'sweep', 'sweep-collect']);
  assert.equal(jobs.verdict.steps.find((x: any) => x.name === 'Verdict').env.FAST, '${{ needs.build.outputs.fast }}');
  // the fast run's own Drive steps read only: no put, no delete, no sync, no move
  for (const st of [reuse, realSide]) { const text = stepScript(wf(), st.name!); assert.ok(/drive_lab\.sh get /.test(text) && !/drive_lab\.sh (put|delete|purge|sync|move)|rclone (sync|delete|purge|move|deletefile)/.test(text), st.name); }
  // the commit comment keeps the new framing lines
  assert.match(stepScript(wf(), 'Report (commit comment; RUNBOOK'), /FRAME='[^']*depth model reused\|real side\|fast/);
});

test('the depth model reuse step: copy-only Drive reads of that run, the stage\'s check before the model is used, timing lines; a bad run id never reaches a path', () => {
  const y = wf(), { ws, bin, tmp } = stageWs(), drive = tmpDir(), calls = path.join(tmp, 'calls.txt');
  const step = stepScript(y, 'The depth model, reused from an earlier run');
  fs.writeFileSync(path.join(ws, 'data/twin/split.json'), JSON.stringify({ name: 'custom', fit: FAST_FIT, judge: FAST_JUDGE, warm: [] }));
  const model = (o: object) => { const d = path.join(drive, 'simulated/history-twin/55/models'); fs.mkdirSync(d, { recursive: true }); fs.writeFileSync(path.join(d, 'depth_model.json'), JSON.stringify({ ...synthModel({ days: FAST_FIT }), schema: DEPTH_MODEL_SCHEMA, ...o })); };
  const metaOnDrive = (tag?: string) => { const d = path.join(drive, 'simulated/history-twin/55/twinlite'); fs.rmSync(d, { recursive: true, force: true }); if (tag) { fs.mkdirSync(d, { recursive: true }); fs.writeFileSync(path.join(d, 'real-meta.json'), JSON.stringify({ real15m: tag })); } };
  const run = (id: string) => { for (const f of [calls, path.join(tmp, 'build.log')]) fs.rmSync(f, { force: true }); fs.rmSync(path.join(ws, 'data/models'), { recursive: true, force: true }); fs.rmSync(path.join(ws, 'data/model-src'), { recursive: true, force: true }); fs.rmSync(path.join(ws, 'data/model-meta'), { recursive: true, force: true });
    const r = bash(step, { PATH: `${bin}:${process.env.PATH}`, RUN: id, FAST: 'true', JOB_START: String(Math.floor(Date.now() / 1000) - 300), RUNNER_TEMP: tmp, STUB_DRIVE: drive, STUB_CALLS: calls }, ws);
    const log = fs.existsSync(path.join(tmp, 'build.log')) ? fs.readFileSync(path.join(tmp, 'build.log'), 'utf8') : '', c = fs.existsSync(calls) ? fs.readFileSync(calls, 'utf8') : '';
    return { r, log, calls: c, out: `${r.stdout}${r.stderr}`, model: fs.existsSync(path.join(ws, 'data/models/depth_model.json')) }; };
  // an id that is not digits: no Drive call at all
  for (const bad of ['abc', '5;rm -rf x', '../55', '']) { const r = run(bad); assert.notEqual(r.r.status, 0, bad); assert.match(r.log, /^\[twin\] ERROR: depth_model_run must be a run id \(digits only\)$/m); assert.equal(r.calls, '', `no Drive call for "${bad}"`); }
  // nothing on Drive for that run
  const none = run('56'); assert.notEqual(none.r.status, 0); assert.match(none.log, /^\[twin\] ERROR: depth_model_run 56: no depth model on Drive \(simulated\/history-twin\/56\/models\)/m); assert.ok(!none.model);
  // a model of another study version, or fitted on other days: refused by the check, never copied to where the run reads its model
  model({ schema: DEPTH_MODEL_SCHEMA + 1 }); metaOnDrive(real15mTag());
  const old = run('55'); assert.notEqual(old.r.status, 0); assert.match(old.log, /^\[twin\] ERROR: depth_model_run 55: the model has schema \d+, this code reads schema \d+/m); assert.ok(!old.model, 'a refused model is not copied'); assert.ok(!/fast: depth model reused/.test(old.log));
  model({ days: ['2026-11-11'] }); assert.match(run('55').log, /^\[twin\] ERROR: depth_model_run 55: the model was fitted on 2026-11-11, not exactly the fit days/m);
  model({ days: [...FAST_FIT, '2026-11-13'] }); const leak = run('55'); assert.notEqual(leak.r.status, 0); assert.match(leak.log, /^\[twin\] ERROR: depth_model_run 55: .*overlap.*2026-11-13/m); assert.ok(!leak.model);
  model({}); metaOnDrive('r15m-0|exclude=DOGE'); const tag = run('55'); assert.notEqual(tag.r.status, 0); assert.match(tag.log, /^\[twin\] ERROR: depth_model_run 55: the model was fitted from real days tagged r15m-0\|exclude=DOGE/m);
  // a good one: the check line, the model in place, the two timing lines (set-up = the seconds since the job began)
  metaOnDrive(real15mTag()); const ok = run('55');
  assert.equal(ok.r.status, 0, ok.out); assert.ok(ok.model);
  assert.equal(fs.readFileSync(path.join(ws, 'data/models/depth_model.json'), 'utf8'), fs.readFileSync(path.join(drive, 'simulated/history-twin/55/models/depth_model.json'), 'utf8'));
  assert.match(ok.log, new RegExp(`^\\[twin\\] depth model reused from run 55: fitted on 2026-11-11 2026-11-12 \\(exactly the fit days\\), schema ${DEPTH_MODEL_SCHEMA}; real days tag r15m-1\\|exclude=DOGE$`, 'm'));
  const setup = /^\[twin\] fast: set-up (\d+) s$/m.exec(ok.log); assert.ok(setup && +setup[1] >= 299 && +setup[1] <= 330, `set-up ${setup?.[1]}`); assert.match(ok.log, /^\[twin\] fast: depth model reused \d+ s$/m);
  // no real-meta.json on that run: the model is still checked (days, schema), and the line says the tag is not recorded
  metaOnDrive(); assert.match(run('55').log, /schema \d+; no real-meta\.json beside it, so the real days' tag it was fitted from is not recorded$/m);
  // Drive is only read, only that run's folders, only the files named
  const lines = ok.calls.split('\n').filter(Boolean);
  assert.deepEqual(lines.map((l) => l.split(' ').slice(0, 2).join(' ')), ['get simulated/history-twin/55/models', 'get simulated/history-twin/55/twinlite']);
  assert.ok(lines.every((l) => / --include (depth_model|real-meta)\.json$/.test(l)));
});

test('the real side step: copy-only read of that run\'s twinlite files into data/real-cache; a bad id or a run with nothing there stops it with a reason', () => {
  const y = wf(), { ws, bin, tmp } = stageWs(), drive = tmpDir(), calls = path.join(tmp, 'calls.txt'), step = stepScript(y, 'The real side of an earlier run');
  const run = (id: string) => { for (const f of [calls, path.join(tmp, 'build.log')]) fs.rmSync(f, { force: true }); fs.rmSync(path.join(ws, 'data/real-cache'), { recursive: true, force: true });
    const r = bash(step, { PATH: `${bin}:${process.env.PATH}`, RUN: id, RUNNER_TEMP: tmp, STUB_DRIVE: drive, STUB_CALLS: calls }, ws);
    return { r, log: fs.existsSync(path.join(tmp, 'build.log')) ? fs.readFileSync(path.join(tmp, 'build.log'), 'utf8') : '', calls: fs.existsSync(calls) ? fs.readFileSync(calls, 'utf8') : '' }; };
  for (const bad of ['abc', '1 2', '../1', '']) { const r = run(bad); assert.notEqual(r.r.status, 0); assert.match(r.log, /^\[twin\] ERROR: real_features_run must be a run id \(digits only\)$/m); assert.equal(r.calls, ''); }
  const none = run('77'); assert.notEqual(none.r.status, 0); assert.match(none.log, /^\[twin\] ERROR: real_features_run 77: no judged features on Drive \(simulated\/history-twin\/77\/twinlite\)/m);
  const d = path.join(drive, 'simulated/history-twin/77/twinlite'); fs.mkdirSync(d, { recursive: true });
  for (const f of REAL_SIDE) fs.writeFileSync(path.join(d, f), '[]');
  const ok = run('77'); assert.equal(ok.r.status, 0, `${ok.r.stdout}${ok.r.stderr}`);
  assert.deepEqual(fs.readdirSync(path.join(ws, 'data/real-cache')).sort(), [...REAL_SIDE].sort());
  assert.match(ok.log, /^\[twin\] real side of run 77 read from Drive: 4 file\(s\)$/m);
  assert.equal(ok.calls.trim(), 'get simulated/history-twin/77/twinlite data/real-cache --include features-real.json --include real-meta.json --include real-activity.json --include paired.json');
});

test('the fast rows step passes the model, the sweep\'s params and the reused real side on to the stage, and only when they were asked for', () => {
  const y = wf(), wsn = stageWs(), args = path.join(wsn.tmp, 'a.txt'), step = stepScript(y, 'Fast rows');
  fs.writeFileSync(path.join(wsn.bin, 'node'), '#!/usr/bin/env bash\nprintf \'%s\\n\' "$*" >> "$STUB_ARGS"\necho "[twin] stub fast"\n', { mode: 0o755 });
  const run = (env: Record<string, string>) => { fs.rmSync(args, { force: true }); const r = bash(step, { PATH: `${wsn.bin}:${process.env.PATH}`, JUDGE: FAST_JUDGE.join(','), DEPTH_PARAMS_RUN: '', REAL_FEATURES_RUN: '', RUNNER_TEMP: wsn.tmp, STUB_ARGS: args, ...env }, wsn.ws); assert.equal(r.status, 0, `${r.stdout}${r.stderr}`); return fs.readFileSync(args, 'utf8').trim().split('\n'); };
  const base = `--import tsx research/historyTwin.ts --stage fastrows --real data/twin-real15m --twin data/replay-src --days ${FAST_JUDGE.join(',')} --depth-model data/models/depth_model.json --out data/twin`;
  assert.deepEqual(run({}), [base]);
  assert.deepEqual(run({ DEPTH_PARAMS_RUN: '55' }), [`${base} --depth-params data/sweep/best.json`]);
  assert.deepEqual(run({ REAL_FEATURES_RUN: '66' }), [`${base} --real-cache data/real-cache --real-run 66`]);
  assert.deepEqual(run({ DEPTH_PARAMS_RUN: '55', REAL_FEATURES_RUN: '66' }), [`${base} --depth-params data/sweep/best.json --real-cache data/real-cache --real-run 66`]);
  // the lines of the stage reach the log the report reads
  assert.match(fs.readFileSync(path.join(wsn.tmp, 'build.log'), 'utf8'), /\[twin\] fast rows from \d\d:\d\d UTC\n\[twin\] stub fast/);
});

test('the judged files kept for the verdict job include the real side\'s sidecars when there are any; the fit step and the verdict print their seconds on a fast run only', () => {
  const y = wf(), { ws } = stageWs(), keep = stepScript(y, 'Keep the judged features');
  const put = (names: string[]) => { fs.rmSync(path.join(ws, 'data/twin'), { recursive: true, force: true }); fs.rmSync(path.join(ws, 'data/twinlite'), { recursive: true, force: true }); fs.mkdirSync(path.join(ws, 'data/twin'), { recursive: true }); for (const n of names) fs.writeFileSync(path.join(ws, 'data/twin', n), '{}'); const r = bash(keep, {}, ws); return { r, kept: fs.existsSync(path.join(ws, 'data/twinlite')) ? fs.readdirSync(path.join(ws, 'data/twinlite')).sort() : [] }; };
  const core = ['paired.json', 'features-real.json', 'features-requote.json', 'features-depth.json', 'split.json', 'twin-source.json'];
  const withSide = put([...core, 'real-meta.json', 'real-activity.json', 'verdict-junk.txt']); assert.equal(withSide.r.status, 0, withSide.r.stderr);
  assert.deepEqual(withSide.kept, [...core, 'real-meta.json', 'real-activity.json'].sort());
  const blind = put(core); assert.equal(blind.r.status, 0, blind.r.stderr); assert.deepEqual(blind.kept, [...core].sort(), 'a confirm run writes no sidecar and keeps none');
  // the fit step: its seconds on a fast run, nothing on the full route
  const work = tmpDir(), bin = path.join(work, 'bin'), fws = path.join(work, 'ws'), tmp = path.join(work, 'tmp');
  fs.mkdirSync(bin); fs.mkdirSync(tmp); fs.mkdirSync(path.join(fws, 'data/twin-real15m'), { recursive: true }); fs.mkdirSync(path.join(fws, '.github/scripts'), { recursive: true }); fs.copyFileSync(path.join(ROOT, '.github/scripts/twin-lib.sh'), path.join(fws, '.github/scripts/twin-lib.sh'));
  fs.writeFileSync(path.join(bin, 'node'), '#!/usr/bin/env bash\nmkdir -p data/models; echo \'{"days":[]}\' > data/models/depth_model.json\necho "[depth] 3 day(s): a..b"\n', { mode: 0o755 });
  const fit = (env: Record<string, string>) => { fs.rmSync(path.join(tmp, 'build.log'), { force: true }); const r = bash(stepScript(y, 'The depth model, fitted'), { PATH: `${bin}:${process.env.PATH}`, FIT: '2026-11-11,2026-11-12', RUNNER_TEMP: tmp, GITHUB_WORKSPACE: fws, ...env }, fws); assert.equal(r.status, 0, r.stderr); return fs.readFileSync(path.join(tmp, 'build.log'), 'utf8'); };
  const fast = fit({ FAST: 'true', JOB_START: String(Math.floor(Date.now() / 1000) - 120) });
  const su = /^\[twin\] fast: set-up (\d+) s$/m.exec(fast); assert.ok(su && +su[1] >= 119 && +su[1] <= 150, `set-up ${su?.[1]}`); assert.match(fast, /^\[twin\] fast: depth model fitted \d+ s$/m);
  assert.ok(!/fast: /.test(fit({ FAST: 'false' })) && !/fast: /.test(fit({})), 'the full route prints no fast line');
  assert.match(fit({ FAST: 'true' }), /^\[twin\] fast: set-up 0 s$/m, 'no job clock (an old runner): zero, never a failure');
  // the verdict job: one more line, on a fast run only, after the stage's own lines
  const v = verdictStep({ split: 'dev', backtests: false, result: 'skipped', have: {}, fast: 'true' }); assert.equal(v.r.status, 0, v.out);
  assert.match(v.log, /\[twin\] depth: adversary AUC 0\.55\n\[twin\] fast: verdict \d+ s\n/);
  for (const f of ['false', '']) assert.ok(!/fast: verdict/.test(verdictStep({ split: 'dev', backtests: false, result: 'skipped', have: {}, fast: f }).log), `FAST='${f}'`);
  assert.ok(!/fast: verdict/.test(verdictStep({ split: 'dev', backtests: false, result: 'skipped', have: {} }).log), 'no FAST variable at all');
});
// ---- H3 end ----
test('the fill stage says which depth model it plays (schema and assets, or a WARNING for a pooled-only one) and which rows fed the books, and the build comment keeps both', async () => {
  const work = tmpDir(), day = '2026-11-13', src = path.join(work, 'src');
  fs.mkdirSync(src);
  writeEventsGz(path.join(src, `md-${day}.jsonl.gz`), synthRequoteDay({ day, assets: ['BTC', 'ETH'], windows: 2, seed: 5 }));
  const run = (name: string, model: object) => {
    const f = path.join(work, `${name}.json`); fs.writeFileSync(f, JSON.stringify(model));
    const r = spawnSync(process.execPath, ['--import', 'tsx', 'research/historyTwin.ts', '--stage', 'fill', '--src', src, '--dst', path.join(work, name), '--how', 'depth', '--depth-model', f], { encoding: 'utf8' });
    assert.equal(r.status, 0, r.stderr);
    return r.stdout.split('\n').filter((l) => l.startsWith('[twin]'));
  };
  const picks = (lines: string[]) => /simulator: .*; books drawn from stress rows (\d+)\/(\d+)\/(\d+), asset rows (\d+), pooled rows (\d+) \((\d+) of an asset with no block\)$/.exec(lines.find((l) => /simulator: /.test(l))!)!.slice(1).map(Number);
  // an old, pooled-only model (a study of before schema 2, or a stale study on the ref): the warning, and every book from the pooled rows
  const pooled = synthModel();
  const old = run('old', pooled);
  assert.ok(old.includes('[twin] WARNING: the depth model is pooled only (schema 0): no asset or stress rows, every book comes from the pooled rows (the depth study on this ref may be an old copy)'), old.join('\n'));
  assert.ok(!old.some((l) => /^\[twin\] depth model schema/.test(l)));
  const [s0, s1, s2, a0, p0, u0] = picks(old);
  assert.deepEqual([s0, s1, s2, a0], [0, 0, 0, 0]);
  assert.ok(p0 > 100 && p0 === u0, 'all of them from pooled rows, none of them from an asset that had a block');
  // a model with a BTC block: the schema line names it, BTC's books come from its rows, ETH's (no block) from the pooled rows
  const blocked = run('blocked', { ...pooled, schema: 2, byAsset: { BTC: { shape: pooled.shape, flow: pooled.flow } } });
  assert.ok(blocked.includes('[twin] depth model schema 2, assets BTC'), blocked.join('\n'));
  assert.ok(!blocked.some((l) => /WARNING/.test(l)));
  const [b0, b1, b2, ba, bp, bu] = picks(blocked);
  assert.ok(ba > 50 && bu > 50 && bp === bu && b0 + b1 + b2 === 0, `${[b0, b1, b2, ba, bp, bu]}`);
  assert.equal(ba + bu, p0, 'every anchor of the day is counted once, from an asset row or a pooled row');
  // the in-stream route (the sweep's, and the fast run's) reports the same counts per day, for the one simulator its day used
  const model = { ...pooled, schema: 2, byAsset: { BTC: { shape: pooled.shape, flow: pooled.flow } } } as unknown as DepthModel;
  const day2 = await filledDayRows(synthRequoteDay({ day, assets: ['BTC', 'ETH'], windows: 2, seed: 5 }), day, 'depth', new Map(), model, undefined, { diag: false });
  assert.deepEqual([day2.picks.stress, day2.picks.asset, day2.picks.pooled, day2.picks.unblocked], [[0, 0, 0], ba, 0, bu], 'filledDayRows says which rows fed the day');
  assert.equal(depthPicksNote([day2.picks, day2.picks]), `books drawn from stress rows 0/0/0, asset rows ${2 * ba}, pooled rows ${2 * bu} (${2 * bu} of an asset with no block)`, 'and the note sums days');
  // ... and the line the in-stream route prints is the one the file route printed, byte for byte: the same function builds both (a fast run's comment carries `books drawn from` too)
  const fileLine = blocked.find((l) => / simulator: /.test(l))!;
  assert.equal(simulatorLine(path.join(work, 'blocked'), [day2.sim], [day2.picks]), fileLine, 'the in-stream route\'s simulator line equals the file route\'s');
  assert.equal(depthModelNote(model), blocked.find((l) => /^\[twin\] depth model schema/.test(l)), 'and so does the model line: one function says which model is played');
  // the workflow's build comment keeps the framing lines first: the schema line and the warning are among them
  const frame = new RegExp(/FRAME='([^']+)'/.exec(fs.readFileSync('.github/workflows/history-twin.yml', 'utf8'))![1]);
  assert.ok(frame.test('[twin] depth model schema 2, assets BTC ETH SOL XRP') && frame.test(old.find((l) => /WARNING/.test(l))!) && frame.test('[twin] depth model: asset BTC: 9 samples'), 'the framing lines');
  // a fast run that reuses a model fits nothing, so it has no asset lines: the line that names the run to read them in is a framing line too (and the fitted line of a run that fits)
  assert.ok(frame.test('[twin] depth model reused from run 123456: fitted on 2026-11-11 2026-11-12 2026-11-15 (exactly the fit days), schema 2; real days tag r15m-1') && frame.test('[twin] depth model fitted on fit days only (checked against the split\'s 3 fit and 4 judged day(s))'), 'the reuse line and the fitted line');
  assert.ok(!frame.test(old.find((l) => /simulator: /.test(l))!), 'the simulator line is a detail line, not a framing one');
});

test('every stage that plays the depth model for the judged days says which model and which rows (a fast run reads no asset lines: these two are its R1 signs)', () => {
  // The fill stage (full route) and, where there is one, the stage `--stage fastrows` dispatches to (the in-stream route) must print the model line and the simulator line
  // the RUNBOOK (3.0 check 1b, 3.2.1) tells the reader to look for. A route that built the days without them would read as a stale ref or give no sign of the model at all.
  const src = fs.readFileSync('research/historyTwin.ts', 'utf8');
  const stageFn = (stage: string) => { const m = new RegExp(`if \\(stage === '${stage}'\\) return (\\w+)\\(`).exec(src); return m ? m[1] : undefined; };
  const body = (fn: string) => { const i = src.indexOf(`async function ${fn}(`); assert.ok(i >= 0, `${fn} exists`); const j = src.indexOf('\n}\n', i); return src.slice(i, j); };
  const stages = ['fill', 'fastrows'].map((s) => [s, stageFn(s)] as const).filter(([, fn]) => fn);
  assert.ok(stages.some(([s]) => s === 'fill'), 'the fill stage is dispatched');
  for (const [s, fn] of stages) {
    // a stage may hand over to the function that does the work (stageFastRows -> fastRows): its text counts, one level down
    const b0 = body(fn!), b = [b0, ...[...b0.matchAll(/\b(\w+)\(/g)].map((m) => m[1]).filter((n, i, a) => a.indexOf(n) === i && n !== fn && src.includes(`async function ${n}(`)).map(body)].join('\n');
    // The model line is printed by depthFillSetup, which both routes call before they play a day (the one place that checks and logs the depth side).
    assert.ok(/depthModelNote\(/.test(b) || (/depthFillSetup\(/.test(b) && /depthModelNote\(/.test(body('depthFillSetup'))), `stage ${s} prints depthModelNote(the model it plays), itself or through depthFillSetup`);
    assert.match(b, /simulatorLine\(/, `stage ${s} prints simulatorLine(...) with the days' picks, not its own copy of the line`);
  }
});

test('the dev verdict reads the twin by asset (report only): lives and medians per asset, real against twin; the confirm verdict prints none of it, and the checks do not move', async () => {
  // BTC is 10x busier and deeper than ETH in the real rows; the twin has one scale for both
  const ix = (n: string) => FEATURES.indexOf(n as (typeof FEATURES)[number]);
  const build = (src: string, scale: (a: string) => number, seed: number): Row[] => rows(src, 0, seed).map((r, i) => {
    const a = i % 2 ? 'BTC' : 'ETH', f = [...r.f];
    f[ix('tradesPerMin')] = 300 * scale(a) * (1 + 0.1 * f[ix('tradesPerMin')]); f[ix('depth10')] = 6 + Math.log(scale(a)) + 0.1 * f[ix('depth10')]; f[ix('tradeSize')] = 1 + 0.1 * f[ix('tradeSize')];
    return { ...r, ticker: `KX${a}15M-26OCT${20 + (i % 3)}${String(i).padStart(4, '0')}`, f };
  });
  const real = build('real', (a) => (a === 'BTC' ? 10 : 1), 41), twin = build('twin', () => 3, 42);
  const dir = (name: 'dev' | 'confirm') => { const out = verdictDir(name, () => twin); fs.writeFileSync(path.join(out, 'features-real.json'), JSON.stringify(real)); for (const s of ['requote', 'depth']) fs.writeFileSync(path.join(out, `features-${s}.json`), JSON.stringify(twin.map((x) => ({ ...x, src: s })))); return out; };
  const dev = await verdictLines(dir('dev'));
  for (const src of ['requote', 'depth']) {
    const l = dev.lines.filter((x) => x.startsWith(`[twin] ${src} by asset `));
    assert.equal(l.length, 2, 'BTC and ETH only: SOL and XRP have no lives');
    const btc = l.find((x) => x.includes('by asset BTC'))!, eth = l.find((x) => x.includes('by asset ETH'))!;
    const re = /^\[twin\] \w+ by asset (BTC|ETH): lives 150 real\/150 twin; medians real\/twin tradesPerMin ([\d.]+)\/([\d.]+), depth10 ([\d.]+)\/([\d.]+), tradeSize ([\d.]+)\/([\d.]+); AUC [01]\.\d{3} \(report only\)$/;
    const [, , bt, bw, bd, bdw] = re.exec(btc)!.map(Number), [, , et, ew] = re.exec(eth)!.map(Number);
    assert.ok(bt > 2500 && bt < 3500 && bw > 800 && bw < 1000, `BTC real ${bt}, twin ${bw}: 3,000 against the twin's 900`);
    assert.ok(et > 250 && et < 350 && ew > 800 && ew < 1000, `ETH real ${et}, twin ${ew}`);
    assert.ok(bd > bdw && bd - 6 > 2 && Math.abs(bdw - (6 + Math.log(3))) < 0.2, `depth10 (log1p): BTC real ${bd}, twin ${bdw}`);
    assert.ok(btc.length < 300 && !/KX[A-Z]|\$/.test(btc), 'short, counts and numbers only');
    assert.ok(dev.lines.findIndex((x) => x === btc) > dev.lines.findIndex((x) => x.startsWith(`[twin] ${src}: by regime`)), 'after the by-regime line');
  }
  // report only: the checks and the AUC are those of the same rows without the asset lines (the headline AUC is computed over every row)
  assert.deepEqual(Object.keys(dev.report.twins.depth.checks), ['indistinguishable', 'noBias', 'errorWithinNoise', 'sameActivity']);
  assert.ok(dev.report.twins.depth.auc > 0.9);
  const conf = await verdictLines(dir('confirm'), { n: 1, note: 'a look' });
  assert.ok(!conf.lines.some((l) => /by asset|tradesPerMin|depth10/.test(l)), 'blind: no per-asset line on a confirm verdict');
});
